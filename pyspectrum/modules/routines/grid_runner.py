# -*- coding: utf-8 -*-
"""Primitivas comunes de las rutinas de grilla de PySpectrum (AND-1, parte 1; DEC-040; R4-K; C-54).

Crecimiento, dímeros, luminiscencia y el mapa hiperespectral hacen, por nodo, las mismas cosas: mover la
platina, conmutar la potencia, mover el espejo de detección, abrir un láser y exponer. Este módulo las
hace una sola vez, con las garantías del bloque A:

- **platina:** `wait_on_target` con tope. Si no confirma, se cierran los obturadores y la grilla se pausa
  (DEC-036); nunca "llegó" por timeout (C-54);
- **potencia** (`up_flipper` = baja, `down_flipper` = alta) y **espejo** (`flipper_notch532`): como el
  legado, con su asentamiento (0.5 s y 0.15 s). El espejo nunca se mueve con un láser de la rutina
  abierto. La posición inicial la confirma el operador (R4-K, P2);
- **láser:** apertura y cierre confirmados; un cierre sin confirmar cuenta como abierto y pausa. 0.5 s
  después de abrir, como el legado;
- **exposición:** `single_exposure`. Una falla es un nodo fallido (R4-K, P6), nunca un cuadro de ceros;
- **latido:** `heartbeat_tick()` en toda espera, sin argumento. Stop y E-STOP cortan cualquier espera en
  el tramo siguiente (≤ 50 ms).

Sin Qt: el hilo lo pone la rutina.
"""
from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Callable, Optional, Set, Tuple

import numpy as np

WAIT_TRANCHE_S = 0.05
POWER_SETTLE_S = 0.5          # legado: 0.5 s después de conmutar (crecimiento); dímeros usa 2 s
MIRROR_SETTLE_S = 0.15        # legado: 0.15 s después del pulso del espejo
LASER_SETTLE_S = 0.5          # legado: 0.5 s después de abrir el láser


class GridAbort(Exception):
    """Stop del operador o E-STOP."""


class GridSafetyPause(Exception):
    """Falla de seguridad (DEC-036): platina que no llega, obturador o conmutación sin confirmar. La grilla
    se pausa con los obturadores cerrados."""


class NodeFailed(Exception):
    """El nodo no se pudo medir (p. ej. la exposición falló). Se registra y la grilla sigue (R4-K, P6)."""


def _default_hw():
    from core import nidaq
    return SimpleNamespace(open_shutter=nidaq.open_shutter, close_shutter=nidaq.close_shutter,
                           close_all_shutters=nidaq.close_all_shutters, up_flipper=nidaq.up_flipper,
                           down_flipper=nidaq.down_flipper, flipper_notch532=nidaq.flipper_notch532)


def _default_tick():
    from pyspectrum.modules.step_glue_engine import heartbeat_tick
    return heartbeat_tick()


def _estopped() -> bool:
    try:
        from pyspectrum.modules.hardware_session import hardware_session
        return bool(hardware_session.is_emergency_stopped)
    except Exception:
        return False


class GridRunner:
    def __init__(self, camera=None, *, should_abort: Callable[[], bool] = lambda: False,
                 tick: Optional[Callable[[], None]] = None, hw=None, stage=None,
                 sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic,
                 move_timeout_s: Optional[float] = None, power_settle_s: float = POWER_SETTLE_S,
                 mirror_settle_s: float = MIRROR_SETTLE_S, laser_settle_s: float = LASER_SETTLE_S):
        from config import STAGE_SETTLE_TIMEOUT_S
        self.camera = camera
        self._should_abort = should_abort
        self.tick = tick or _default_tick()
        self.hw = hw or _default_hw()
        self._stage = stage
        self._sleep, self._clock = sleep, clock
        self.move_timeout_s = STAGE_SETTLE_TIMEOUT_S if move_timeout_s is None else float(move_timeout_s)
        self.power_settle_s, self.mirror_settle_s, self.laser_settle_s = power_settle_s, mirror_settle_s, laser_settle_s
        self.open_lasers: Set[str] = set()

    @property
    def stage(self):
        if self._stage is not None:
            return self._stage
        from config import pi
        return pi

    # ── control ──
    def aborted(self) -> bool:
        return bool(self._should_abort()) or _estopped()

    def check(self) -> None:
        if self.aborted():
            raise GridAbort("Detenida (Stop o E-STOP).")

    def wait(self, seconds: float) -> None:
        """Espera latiendo; Stop o E-STOP la cortan en el tramo siguiente."""
        remaining = max(0.0, float(seconds))
        while True:
            self.check()
            self.tick()
            if remaining <= 0:
                return
            step = min(WAIT_TRANCHE_S, remaining)
            self._sleep(step)
            remaining -= step

    def _pause(self, reason: str) -> None:
        try:
            self.hw.close_all_shutters()
        finally:
            self.open_lasers.clear()
        raise GridSafetyPause(reason)

    # ── platina ──
    def move_to(self, x_um: float, y_um: float, z_um: Optional[float] = None) -> Tuple[float, float, Optional[float]]:
        from config import clamp_axis_um, wait_on_target
        self.check()
        axes, targets = [1, 2], [clamp_axis_um(1, x_um), clamp_axis_um(2, y_um)]
        if z_um is not None:
            axes.append(3)
            targets.append(clamp_axis_um(3, z_um))
        if self.stage.MOV(axes, targets) is False:
            self._pause(f"La platina rechazó el movimiento a {tuple(round(t, 3) for t in targets)} µm.")
        if not wait_on_target(axes, timeout_s=self.move_timeout_s, on_tick=self.tick, stage=self.stage):
            self._pause(f"La platina no confirmó la llegada a {tuple(round(t, 3) for t in targets)} µm en "
                        f"{self.move_timeout_s:g} s: obturadores cerrados, grilla en pausa (DEC-036).")
        self.check()
        return targets[0], targets[1], (targets[2] if z_um is not None else None)

    # ── potencia, espejo y láser ──
    def set_power(self, level: str) -> None:
        if level not in ("low", "high"):
            raise ValueError(f"potencia {level!r}: 'low' o 'high'")
        self.check()
        ok = self.hw.up_flipper() if level == "low" else self.hw.down_flipper()
        if not ok:
            self._pause(f"El filtro de densidad no confirmó el pulso a potencia {'baja' if level == 'low' else 'alta'}.")
        self.wait(self.power_settle_s)

    def set_mirror(self, position: str) -> None:
        if position not in ("up", "down"):
            raise ValueError(f"espejo {position!r}: 'up' o 'down'")
        self.check()
        if self.open_lasers and not self.close_lasers():
            self._pause("No se confirmó el cierre del láser antes de mover el espejo.")
        if not self.hw.flipper_notch532(position):
            self._pause(f"El espejo de detección no confirmó el pulso a '{position}'.")
        self.wait(self.mirror_settle_s)

    def laser(self, name: str, open_: bool) -> None:
        if open_:
            self.check()
            if not self.hw.open_shutter(name):
                self._pause(f"El obturador de {name} no confirmó la apertura.")
            self.open_lasers.add(name)
            self.wait(self.laser_settle_s)
            return
        ok = self.hw.close_shutter(name)
        self.open_lasers.discard(name)
        if not ok:
            self._pause(f"El obturador de {name} no confirmó el cierre: cuenta como abierto (DEC-036).")

    def close_lasers(self) -> bool:
        ok = True
        for name in sorted(self.open_lasers):
            ok = bool(self.hw.close_shutter(name)) and ok
        self.open_lasers.clear()
        return ok

    # ── exposición ──
    def prepare_1d(self) -> Tuple[Tuple[int, ...], str, int]:
        """El modo con el que se mide un espectro 1D: Single-Track o FVB si la cámara está en uno de esos
        modos; desde Imagen pasa a FVB (una exposición 2D no es un espectro). Devuelve (forma, nombre, modo)."""
        from pyspectrum.drivers.andor_ccd_driver import READ_MODE_FVB, READ_MODE_SINGLE_TRACK
        mode = self.camera.get_read_mode() if hasattr(self.camera, "get_read_mode") else READ_MODE_FVB
        if mode == READ_MODE_SINGLE_TRACK:
            return (1004,), "Single-Track", READ_MODE_SINGLE_TRACK
        if mode != READ_MODE_FVB:
            self.camera.set_read_mode(READ_MODE_FVB)
        return (1004,), ("FVB" if mode == READ_MODE_FVB else "FVB (la cámara estaba en otro modo)"), READ_MODE_FVB

    def spectrum_1d(self, exposure_s: float) -> Tuple[np.ndarray, str]:
        """Un espectro 1D con una exposición real (modo de `prepare_1d`). Devuelve (espectro, modo)."""
        shape, name, _mode = self.prepare_1d()
        return self.expose(shape, exposure_s), name

    # ── Fondo del procedimiento (R4-N; DEC-040) ───────────────────────────
    def ensure_dark_1d(self, exposure_s: float, *, spectrometer, method: str, n_frames: int, store=None):
        """El fondo de la corrida con el modo de `spectrum_1d` y la exposición de la medición. Se reutiliza si
        las condiciones no cambiaron. Con "obturador cerrado" se toma solo y el obturador del espectrómetro
        vuelve a abrirse (verificado) antes de medir; con "todo apagado" nunca se toma solo: el operador lo
        toma antes con [Tomar fondo ahora]."""
        from pyspectrum.services import procedure_background as pb
        shape, _name, mode = self.prepare_1d()
        cond = pb.read_conditions(self.camera, shape, exposure_s=exposure_s, read_mode=mode)
        try:
            return pb.ensure_dark(self.camera, spectrometer, cond, method=method, n_frames=n_frames,
                                  expose=self.expose, store=store)
        except pb.DarkMissing as e:
            raise GridAbort(str(e))
        except pb.DarkError as e:
            raise GridAbort(f"No se pudo tomar el fondo: {e}")

    def take_dark_1d(self, exposure_s: float, *, spectrometer, method: str, n_frames: int, store=None):
        """Toma un fondo nuevo (siempre mide) y lo guarda en el almacén ([Tomar fondo ahora])."""
        from pyspectrum.services import procedure_background as pb
        shape, _name, mode = self.prepare_1d()
        cond = pb.read_conditions(self.camera, shape, exposure_s=exposure_s, read_mode=mode)
        try:
            return pb.take_dark(self.camera, spectrometer, cond, method=method, n_frames=n_frames,
                                expose=self.expose, store=store)
        except pb.DarkError as e:
            raise GridAbort(f"No se pudo tomar el fondo: {e}")

    def expose(self, shape, exposure_s: float) -> np.ndarray:
        """Una exposición real (R4-5). Stop/E-STOP → GridAbort; cualquier otra falla → NodeFailed."""
        from pyspectrum.modules.acquisition import ExposureRequest, Frame, single_exposure
        self.check()
        fr = single_exposure(self.camera, ExposureRequest(float(exposure_s), tuple(shape)),
                             should_abort=self._should_abort, on_tick=self.tick, is_estopped=_estopped)
        if isinstance(fr, Frame):
            return np.asarray(fr.data, dtype=np.float64)
        kind = getattr(fr.kind, "value", str(fr.kind))
        if kind in ("user_stop", "estop"):
            raise GridAbort("Detenida durante la exposición.")
        raise NodeFailed(f"La exposición falló: {fr.detail} ({kind}).")


def expected_1d_conditions(camera, exposure_s: float):
    """Las condiciones con las que `spectrum_1d` va a medir, sin tocar la cámara (para verificar el fondo
    antes de iniciar y para el estado de la fila "Fondo")."""
    from pyspectrum.drivers.andor_ccd_driver import READ_MODE_FVB, READ_MODE_SINGLE_TRACK
    from pyspectrum.services import procedure_background as pb
    try:
        mode = camera.get_read_mode()
    except Exception:
        mode = READ_MODE_FVB
    mode = READ_MODE_SINGLE_TRACK if mode == READ_MODE_SINGLE_TRACK else READ_MODE_FVB
    return pb.read_conditions(camera, (1004,), exposure_s=exposure_s, read_mode=mode)
