# -*- coding: utf-8 -*-
"""
zero_order_service.py — Servicio de orden cero, el "espejo rápido" (paso 7 del bloque A, DEC-040)

El investigador pasa seguido del orden cero al primer orden (R4-A-3), así que la protección es
automática sobre el detector y no hay diálogo. Reemplaza a `ZeroOrderSafetyDialog` y a sus variantes
(el botón de Calibraciones y el dock legado).

Entrada (`enter_specular`, R2-inst §2.2): cada paso verifica su retorno y, si uno falla, **no se mueve la
red**. El resultado dice qué paso falló, con qué código y en qué estado quedó cada recurso (H-12).

| Paso | Qué hace |
| :-- | :--- |
| Z1 | toma la sesión de hardware, que pausa los Live registrados; con la E-STOP activa, se rechaza |
| Z2 | detiene la cámara: `abort_acquisition` si está adquiriendo, y espera IDLE leído |
| Z3 | ganancia EM a 0 |
| Z4 | la relee: tiene que ser 0 con retorno exitoso; si no, la ganancia es "desconocida" |
| Z5 | fija la exposición recordada del modo especular (D-18: sin tope; la primera de la sesión es `SPECULAR_DEFAULT_EXPOSURE_S`) |
| Z6 | cierra todos los obturadores, con confirmación (R4-B-3; un cierre no confirmado cuenta como abierto, DEC-036) |
| Z7 | mueve: orden cero, red espejo (posición 3), o una λc bajo el umbral |
| Z8 | relee red, λ y AtZeroOrder, y publica la condición leída en el interlock |

Salida (`leave_specular`, R2-inst §2.4):
- vuelve a la red y la λ de primer orden recordadas, o a las indicadas;
- relee y publica PRIMER ORDEN;
- restituye sola la exposición de primer orden (H-13, R4-D-2);
- **no** restituye la ganancia EM (R4-B-4). La GUI ofrece la pastilla "Restituir"; con un láser abierto
  pide confirmar el notch (H-05).

El Live se reanuda al final sólo si la ganancia 0 quedó confirmada (H-12). La saturación en orden cero se
informa y no aborta (D-06), con la escala amarilla/roja de H-21.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

from pyspectrum.drivers import specular_interlock as si
from pyspectrum.drivers.andor_ccd_driver import DRV_ACQUIRING, DRV_SUCCESS
from pyspectrum.drivers.shamrock_driver import DEVICE, GRATING_MIRROR, SHAMROCK_P2INVALID, SHAMROCK_SUCCESS

ADC_FULL_SCALE_COUNTS = 16383          # 14 bit, [DS-iXon] p. 2
SATURATION_WARN_FRAC = 0.50            # R2-inst §2.2, Z10
SATURATION_ALARM_FRAC = 0.80           # tope de recorte de check_saturation (R2-met §5.1), H-21

STEP_LABELS = {
    "session": "Sesión de hardware",
    "camera_idle": "Cámara detenida (IDLE leído)",
    "gain_zero": "Ganancia EM a 0",
    "gain_confirm": "Ganancia EM 0 (releída)",
    "exposure": "Exposición de orden cero",
    "shutters": "Obturadores cerrados (confirmado)",
    "move": "Movimiento del espectrógrafo",
    "readback": "Relectura del espectrógrafo",
    "target": "Destino",
}


@dataclass(frozen=True)
class StepRecord:
    key: str
    ok: bool
    detail: str = ""

    @property
    def label(self) -> str:
        return STEP_LABELS.get(self.key, self.key)


@dataclass(frozen=True)
class SpecularResult:
    ok: bool
    step_failed: Optional[str]
    code: Optional[int]
    detail: str
    gain_confirmed: Optional[int]
    exposure_real_s: Optional[float]
    shutters_closed: bool
    steps: Tuple[StepRecord, ...]
    final_state: Dict[str, str] = field(default_factory=dict)
    mode: str = si.UNKNOWN


def _default_close_all_shutters() -> bool:
    from core.nidaq import close_all_shutters
    return close_all_shutters()


def _default_open_shutter_names() -> List[str]:
    from core.nidaq import get_open_shutter_names
    return get_open_shutter_names()


def _default_flipper_high_power() -> bool:
    from core.nidaq import is_flipper_high_power
    return is_flipper_high_power()


def _default_session():
    from pyspectrum.modules.hardware_session import hardware_session
    return hardware_session


def _split_ret(value, default_ret=DRV_SUCCESS) -> Tuple[int, int]:
    """El simulador devuelve la ganancia como int; los drivers, como (ret, valor)."""
    if isinstance(value, (tuple, list)) and len(value) >= 2:
        return int(value[0]), int(value[1])
    return default_ret, int(value)


class ZeroOrderService:
    SESSION_NAME = "Orden cero"

    def __init__(self, camera, spectrometer, *, session=None,
                 close_all_shutters: Callable[[], bool] = _default_close_all_shutters,
                 get_open_shutter_names: Callable[[], List[str]] = _default_open_shutter_names,
                 is_flipper_high_power: Callable[[], bool] = _default_flipper_high_power,
                 interlock: Optional[si.SpecularInterlock] = None,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic,
                 idle_timeout_s: float = 0.5,
                 wavelength_tol_nm: float = 0.01):
        self.camera = camera
        self.spectrometer = spectrometer
        self._session = session
        self._close_all = close_all_shutters
        self._open_names = get_open_shutter_names
        self._high_power = is_flipper_high_power
        self._interlock = interlock
        self._sleep = sleep
        self._clock = clock
        self.idle_timeout_s = float(idle_timeout_s)
        self.wavelength_tol_nm = float(wavelength_tol_nm)
        try:
            from config import SPECULAR_DEFAULT_EXPOSURE_S
        except Exception:
            SPECULAR_DEFAULT_EXPOSURE_S = 0.1
        # Dos exposiciones recordadas por sesión (R4-D-2). La de primer orden se toma al entrar.
        self.exposure_by_mode: Dict[str, Optional[float]] = {"specular": float(SPECULAR_DEFAULT_EXPOSURE_S),
                                                             "first_order": None}
        self.return_target: Optional[Tuple[int, float]] = None
        self.gain_before_specular: Optional[int] = None

    # ── Dependencias ──────────────────────────────────────────────────────────
    @property
    def session(self):
        return self._session if self._session is not None else _default_session()

    @property
    def interlock(self) -> si.SpecularInterlock:
        return self._interlock if self._interlock is not None else si.get_interlock()

    # ── Lecturas ──────────────────────────────────────────────────────────────
    def _read_position(self) -> Tuple[Tuple[int, int], Tuple[int, float], Optional[Tuple[int, int]]]:
        g = self.spectrometer.ShamrockGetGrating(DEVICE)
        w = self.spectrometer.ShamrockGetWavelength(DEVICE)
        at_zero = None
        if hasattr(self.spectrometer, "ShamrockAtZeroOrder"):
            try:
                at_zero = self.spectrometer.ShamrockAtZeroOrder(DEVICE)
            except Exception:
                at_zero = None
        return g, w, at_zero

    def refresh_state(self) -> str:
        """Lee el Shamrock y publica la condición leída. Sólo lectura (lo usan el arranque y el panel)."""
        g, w, at_zero = self._read_position()
        mode = si.classify_reading(g, w, at_zero)
        self.interlock.publish(mode, f"leído: red {g[1]}, λc {w[1]}" if mode != si.UNKNOWN
                               else f"lectura fallida (red {g}, λ {w})")
        return mode

    def _read_gain(self) -> Tuple[int, int]:
        try:
            return _split_ret(self.camera.get_emccd_gain())
        except Exception:
            return (-1, -1)

    def _open_shutters(self) -> List[str]:
        try:
            return list(self._open_names())
        except Exception:
            return ["(estado desconocido)"]

    # ── Pasos comunes ─────────────────────────────────────────────────────────
    def _stop_camera(self) -> Tuple[bool, str, Optional[int]]:
        cam = self.camera
        status = cam.get_status_checked()[1] if hasattr(cam, "get_status_checked") else cam.get_status()
        if status == DRV_ACQUIRING:
            cam.abort_acquisition()
        deadline = self._clock() + self.idle_timeout_s
        while True:
            status = cam.get_status_checked()[1] if hasattr(cam, "get_status_checked") else cam.get_status()
            if status != DRV_ACQUIRING:
                return True, "IDLE leído", None
            if self._clock() >= deadline:
                return False, f"la cámara sigue adquiriendo después de {self.idle_timeout_s:.1f} s", DRV_ACQUIRING
            self._sleep(0.02)

    def _zero_and_confirm_gain(self, steps: List[StepRecord]) -> Tuple[bool, Optional[int], Optional[int], str]:
        """Z3 + Z4. Devuelve (ok, código, ganancia leída, detalle)."""
        ret = self.camera.set_emccd_gain(0)
        if ret != DRV_SUCCESS:
            steps.append(StepRecord("gain_zero", False, f"SetEMCCDGain(0) devolvió {ret}"))
            return False, ret, None, f"no se pudo poner la ganancia EM en 0 (código {ret}): no se movió la red"
        steps.append(StepRecord("gain_zero", True))
        ret, gain = self._read_gain()
        if ret != DRV_SUCCESS or gain != 0:
            why = f"ganancia leída {gain}, no 0" if ret == DRV_SUCCESS else f"relectura fallida (código {ret})"
            steps.append(StepRecord("gain_confirm", False, why))
            return False, ret, (gain if ret == DRV_SUCCESS else None), f"{why}: no se movió la red"
        steps.append(StepRecord("gain_confirm", True, "0 releído"))
        return True, None, 0, ""

    def _reconfirm_gain(self) -> bool:
        """Relee la ganancia antes de cada movimiento: una rotación de la torreta tarda segundos y la
        confirmación del interlock vence a los GAIN_ZERO_CONFIRMATION_MAX_AGE_S."""
        ret, gain = self._read_gain()
        return ret == DRV_SUCCESS and gain == 0

    def _result(self, ok, steps, *, step_failed=None, code=None, detail="", gain=None, exposure=None,
                shutters_closed=False, moved="no se movió", live="", gain_state=None) -> SpecularResult:
        final_state = {
            "red": moved,
            "live": live,
            "obturadores": ("cerrados" if shutters_closed else
                            ("sin cambios (" + ", ".join(self._open_shutters()) + " abierto)"
                             if self._open_shutters() else "sin cambios (cerrados)")),
            "ganancia": gain_state if gain_state is not None else ("0 confirmada" if gain == 0 else "desconocida"),
            "sesión": "libre" if not self.session.is_busy else f"tomada por {self.session.current_owner}",
        }
        return SpecularResult(ok=ok, step_failed=step_failed, code=code, detail=detail, gain_confirmed=gain,
                              exposure_real_s=exposure, shutters_closed=shutters_closed, steps=tuple(steps),
                              final_state=final_state, mode=self.interlock.mode)

    def _release(self, resume_live: bool) -> str:
        self.session.release_session(self.SESSION_NAME, restore_live=resume_live)
        return "reanudado" if resume_live else "detenido"

    # ── Entrada ───────────────────────────────────────────────────────────────
    def enter_specular(self, target: str = "zero_order", *, restart_live: bool = True,
                       grating: Optional[int] = None, wavelength_nm: Optional[float] = None) -> SpecularResult:
        """`target`: "zero_order" (red actual), "mirror" (posición 3) o "wavelength" (red y λc dadas)."""
        steps: List[StepRecord] = []
        if target not in ("zero_order", "mirror", "wavelength"):
            steps.append(StepRecord("target", False, f"destino {target!r} desconocido"))
            return self._result(False, steps, step_failed="target", detail=f"destino {target!r} desconocido")
        if target == "wavelength" and (grating is None or wavelength_nm is None):
            steps.append(StepRecord("target", False, "falta la red o la λc"))
            return self._result(False, steps, step_failed="target", detail="falta la red o la λc del destino")

        # Z1: sesión (rechazada con la E-STOP activa o con otra rutina)
        session = self.session
        if session.is_emergency_stopped or not session.acquire_session(self.SESSION_NAME, auto_pause_live=True):
            why = ("E-STOP activa: rearmá el sistema" if session.is_emergency_stopped
                   else f"hardware ocupado por '{session.current_owner}'")
            steps.append(StepRecord("session", False, why))
            return self._result(False, steps, step_failed="session", detail=why, live="sin cambios")
        steps.append(StepRecord("session", True))

        # Lo que se recuerda para volver (sólo si hoy es primer orden leído)
        g, w, at_zero = self._read_position()
        if si.classify_reading(g, w, at_zero) == si.FIRST_ORDER:
            self.return_target = (int(g[1]), float(w[1]))
            ret_gain, gain_now = self._read_gain()
            self.gain_before_specular = gain_now if ret_gain == DRV_SUCCESS else None
            try:
                self.exposure_by_mode["first_order"] = float(self.camera.get_exposure_time())
            except Exception:
                pass

        # Z2: cámara detenida
        ok, why, code = self._stop_camera()
        if not ok:
            steps.append(StepRecord("camera_idle", False, why))
            live = self._release(resume_live=False)
            return self._result(False, steps, step_failed="camera_idle", code=code,
                                detail=f"{why}: no se movió la red", live=live)
        steps.append(StepRecord("camera_idle", True, why))

        # Z3 + Z4: ganancia 0 confirmada
        ok, code, gain, detail = self._zero_and_confirm_gain(steps)
        if not ok:
            live = self._release(resume_live=False)
            # H-12: la ganancia queda "desconocida" (el valor leído va en el detalle)
            return self._result(False, steps, step_failed=steps[-1].key, code=code, detail=detail,
                                gain=None, live=live, gain_state="desconocida")

        # Z5: exposición recordada del modo especular (D-18)
        exposure = self.exposure_by_mode["specular"]
        ret = self.camera.set_exposure_time(exposure)
        real = None
        try:
            real = float(self.camera.get_exposure_time())
        except Exception:
            pass
        if ret != DRV_SUCCESS:
            steps.append(StepRecord("exposure", False, f"SetExposureTime devolvió {ret}"))
            live = self._release(resume_live=True)
            return self._result(False, steps, step_failed="exposure", code=ret, gain=0, live=live,
                                detail=f"no se pudo fijar la exposición de orden cero (código {ret}): no se movió la red")
        steps.append(StepRecord("exposure", True, f"real {real:.4f} s" if real is not None else ""))

        # Z6: obturadores
        try:
            closed = bool(self._close_all())
        except Exception as e:
            closed = False
            print(f"[Orden cero] close_all_shutters: {e}")
        if not closed:
            steps.append(StepRecord("shutters", False, "la placa no confirmó el cierre"))
            live = self._release(resume_live=True)
            return self._result(False, steps, step_failed="shutters", gain=0, exposure=real, live=live,
                                detail="el cierre de obturadores no se confirmó (cuenta como abierto): no se movió la red")
        steps.append(StepRecord("shutters", True))

        # Z7: movimiento (se reconfirma la ganancia antes de cada orden al Shamrock)
        code = self._move_to_specular(target, grating, wavelength_nm)
        if code != SHAMROCK_SUCCESS:
            steps.append(StepRecord("move", False, f"código {code}"))
            self.refresh_state()
            live = self._release(resume_live=True)
            return self._result(False, steps, step_failed="move", code=code, gain=0, exposure=real,
                                shutters_closed=True, moved="el movimiento falló", live=live,
                                detail=f"el espectrógrafo devolvió {code} al moverse")
        steps.append(StepRecord("move", True))

        # Z8: relectura y publicación
        g, w, at_zero = self._read_position()
        mode = si.classify_reading(g, w, at_zero)
        expected_ok = (mode == si.SPECULAR and (target != "mirror" or g[1] == GRATING_MIRROR))
        if not expected_ok:
            if mode != si.SPECULAR:
                self.interlock.publish(si.UNKNOWN, f"relectura tras orden cero: red {g}, λ {w}")
            steps.append(StepRecord("readback", False, f"red {g}, λ {w}"))
            live = self._release(resume_live=True)
            return self._result(False, steps, step_failed="readback", gain=0, exposure=real,
                                shutters_closed=True, moved="estado desconocido", live=live,
                                detail="la relectura no confirma la condición especular: la ganancia sigue bloqueada")
        self.interlock.publish(si.SPECULAR, f"espejo rápido ({target}): red {g[1]}, λc {w[1]}")
        steps.append(StepRecord("readback", True, f"red {g[1]}, λc {w[1]:.2f} nm"))

        live = self._release(resume_live=restart_live)
        return self._result(True, steps, gain=0, exposure=real, shutters_closed=True,
                            moved=f"especular (red {g[1]}, λc {w[1]:.2f} nm)", live=live)

    def _move_to_specular(self, target: str, grating: Optional[int], wavelength_nm: Optional[float]) -> int:
        spec = self.spectrometer
        if not self._reconfirm_gain():
            return SHAMROCK_P2INVALID     # la ganancia dejó de estar confirmada
        if target == "zero_order":
            return spec.goto_zero_order(DEVICE)
        if target == "mirror":
            return spec.ShamrockSetGrating(DEVICE, GRATING_MIRROR)
        ret_g, current = spec.ShamrockGetGrating(DEVICE)
        if ret_g != SHAMROCK_SUCCESS or int(current) != int(grating):
            ret = spec.ShamrockSetGrating(DEVICE, int(grating))
            if ret != SHAMROCK_SUCCESS:
                return ret
            if not self._reconfirm_gain():
                return SHAMROCK_P2INVALID
        return spec.ShamrockSetWavelength(DEVICE, float(wavelength_nm))

    # ── Salida ────────────────────────────────────────────────────────────────
    def leave_specular(self, grating: Optional[int] = None, wavelength_nm: Optional[float] = None) -> SpecularResult:
        steps: List[StepRecord] = []
        if grating is None or wavelength_nm is None:
            if self.return_target is None:
                steps.append(StepRecord("target", False, "sin destino recordado"))
                return self._result(False, steps, step_failed="target", gain_state="bloqueada en 0",
                                    detail="No hay un primer orden recordado: indicá red y λ para volver.")
            grating, wavelength_nm = self.return_target
        if si.classify(grating, wavelength_nm) != si.FIRST_ORDER:
            thr = si.specular_threshold_nm(grating) if grating != GRATING_MIRROR else math.inf
            why = f"red {grating}, λc {wavelength_nm} nm seguiría especular (umbral {thr:.1f} nm)"
            steps.append(StepRecord("target", False, why))
            return self._result(False, steps, step_failed="target", detail=why, gain_state="bloqueada en 0")
        steps.append(StepRecord("target", True, f"red {grating}, λc {wavelength_nm:.2f} nm"))

        session = self.session
        if session.is_emergency_stopped or not session.acquire_session(self.SESSION_NAME, auto_pause_live=True):
            why = ("E-STOP activa: rearmá el sistema" if session.is_emergency_stopped
                   else f"hardware ocupado por '{session.current_owner}'")
            steps.append(StepRecord("session", False, why))
            return self._result(False, steps, step_failed="session", detail=why, live="sin cambios",
                                gain_state="bloqueada en 0")
        steps.append(StepRecord("session", True))

        try:
            self.exposure_by_mode["specular"] = float(self.camera.get_exposure_time())
        except Exception:
            pass

        spec = self.spectrometer
        ret_g, current = spec.ShamrockGetGrating(DEVICE)
        code = SHAMROCK_SUCCESS
        if ret_g != SHAMROCK_SUCCESS or int(current) != int(grating):
            code = spec.ShamrockSetGrating(DEVICE, int(grating))
        if code == SHAMROCK_SUCCESS:
            code = spec.ShamrockSetWavelength(DEVICE, float(wavelength_nm))
        if code != SHAMROCK_SUCCESS:
            steps.append(StepRecord("move", False, f"código {code}"))
            self.refresh_state()
            live = self._release(resume_live=True)
            return self._result(False, steps, step_failed="move", code=code, moved="el movimiento falló",
                                live=live, gain_state="bloqueada en 0", detail=f"el espectrógrafo devolvió {code}")
        steps.append(StepRecord("move", True))

        g, w, at_zero = self._read_position()
        ok = (g[0] == SHAMROCK_SUCCESS and w[0] == SHAMROCK_SUCCESS and int(g[1]) == int(grating)
              and abs(float(w[1]) - float(wavelength_nm)) <= self.wavelength_tol_nm
              and not (at_zero is not None and at_zero[0] == SHAMROCK_SUCCESS and at_zero[1]))
        if not ok:
            self.interlock.publish(si.UNKNOWN, f"relectura al volver: red {g}, λ {w}")
            steps.append(StepRecord("readback", False, f"red {g}, λ {w}"))
            live = self._release(resume_live=True)
            return self._result(False, steps, step_failed="readback", moved="estado desconocido", live=live,
                                gain_state="bloqueada en 0",
                                detail="la relectura no coincide con el destino: la ganancia sigue bloqueada")
        self.interlock.publish(si.FIRST_ORDER, f"primer orden: red {g[1]}, λc {w[1]:.2f} nm")
        steps.append(StepRecord("readback", True, f"red {g[1]}, λc {w[1]:.2f} nm"))

        # Exposición de primer orden restituida sola; la ganancia no (R4-B-4)
        first = self.exposure_by_mode.get("first_order")
        if first is not None:
            self.camera.set_exposure_time(first)
            steps.append(StepRecord("exposure", True, f"primer orden {first:.4f} s"))
        live = self._release(resume_live=True)
        return self._result(True, steps, moved=f"primer orden (red {g[1]}, λc {w[1]:.2f} nm)", live=live,
                            gain_state="0 (no se restituye sola)")

    def move(self, grating: int, wavelength_nm: float, *, restart_live: bool = True) -> SpecularResult:
        """Todo cambio de red o λ desde la GUI: un destino especular entra por el espejo rápido; desde
        especular, un destino de primer orden sale por la salida protegida."""
        if si.classify(grating, wavelength_nm) != si.FIRST_ORDER:
            return self.enter_specular("wavelength", restart_live=restart_live, grating=grating,
                                       wavelength_nm=wavelength_nm)
        if self.interlock.mode != si.FIRST_ORDER:
            return self.leave_specular(grating, wavelength_nm)
        steps: List[StepRecord] = []
        spec = self.spectrometer
        ret_g, current = spec.ShamrockGetGrating(DEVICE)
        code = SHAMROCK_SUCCESS
        if ret_g != SHAMROCK_SUCCESS or int(current) != int(grating):
            code = spec.ShamrockSetGrating(DEVICE, int(grating))
        if code == SHAMROCK_SUCCESS:
            code = spec.ShamrockSetWavelength(DEVICE, float(wavelength_nm))
        steps.append(StepRecord("move", code == SHAMROCK_SUCCESS, f"código {code}"))
        mode = self.refresh_state()
        ok = code == SHAMROCK_SUCCESS and mode == si.FIRST_ORDER
        return self._result(ok, steps, step_failed=None if ok else "move", code=None if ok else code,
                            moved=f"red {grating}, λc {wavelength_nm:.2f} nm" if ok else "el movimiento falló",
                            live="sin cambios", gain_state="sin cambios",
                            detail="" if ok else f"el espectrógrafo devolvió {code}")

    # ── Informes para la GUI ──────────────────────────────────────────────────
    @staticmethod
    def saturation_level(frame, bias: Optional[float] = None) -> Tuple[float, str]:
        """Pico − bias como fracción del ADC de 14 bit, con la escala de H-21: "ok" < 50 % ≤ "warn" <
        80 % ≤ "alarm". Sólo informa (D-06)."""
        arr = np.asarray(frame, dtype=float)
        if arr.size == 0:
            return 0.0, "ok"
        b = float(np.median(arr)) if bias is None else float(bias)
        frac = max(0.0, (float(np.max(arr)) - b) / ADC_FULL_SCALE_COUNTS)
        level = "alarm" if frac >= SATURATION_ALARM_FRAC else ("warn" if frac >= SATURATION_WARN_FRAC else "ok")
        return frac, level

    def specular_light_report(self) -> Tuple[List[str], Optional[str]]:
        """Qué láseres están abiertos en especular. Con el filtro de densidad en alta, un aviso (R4-C-2:
        se avisa, no se bloquea). `is_flipper_high_power` es el último pulso enviado, no una medición."""
        names = self._open_shutters()
        warning = None
        if names and self.interlock.mode != si.FIRST_ORDER:
            try:
                high = bool(self._high_power())
            except Exception:
                high = True
            if high:
                warning = (f"Orden cero con {', '.join(names)} abierto y el filtro de densidad en potencia alta "
                           f"(último pulso enviado): toda la luz cae en la imagen de la ranura.")
        return names, warning

    def gain_restore_needs_notch_confirmation(self) -> bool:
        """H-05 / R4-D-1: restituir la ganancia con un láser abierto pide confirmar "notch puesto"."""
        return bool(self._open_shutters())


_SERVICE: Optional[ZeroOrderService] = None


def get_zero_order_service(camera=None, spectrometer=None) -> ZeroOrderService:
    """El servicio único del proceso: el panel, el dock de Calibraciones y el dock legado entran y salen
    del orden cero por el mismo objeto, así que comparten la red y la λ recordadas y las exposiciones por
    modo. Sin argumentos usa los drivers singleton; con otros drivers (tests) crea uno ligado a ellos."""
    global _SERVICE
    if camera is None:
        from pyspectrum.drivers.andor_ccd_driver import get_andor_ccd
        camera = get_andor_ccd()
    if spectrometer is None:
        from pyspectrum.drivers.shamrock_driver import get_shamrock
        spectrometer = get_shamrock()
    if _SERVICE is None or _SERVICE.camera is not camera or _SERVICE.spectrometer is not spectrometer:
        _SERVICE = ZeroOrderService(camera, spectrometer)
    return _SERVICE
