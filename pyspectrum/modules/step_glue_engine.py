# -*- coding: utf-8 -*-
"""
step_glue_engine.py — Motor de Step & Glue, sin Qt (paso 11 del bloque A, DEC-040)

Contrato de R2-arq §2.9 y §6.6 y de R2-inst §5, reconciliado en la Ronda 4 (D-09 a D-11, D-16 y D-17) y con
las respuestas R4-A-4, R4-B-5, R4-C-3 y R4-5.

- **`plan(request, spectrometer)`**, puro: centros ascendentes, para que cada ventana se aproxime desde
  abajo (R2-inst §4.3). Da la ventana usada (medida en el eje o nominal, DEC-033) y la duración estimada
  (D-16).
- **`preflight(...)`**: bloqueantes y advertencias; la forma de mostrarlos es de la GUI.
- **`run_windows(...)`**, por cada centro:
  - mueve por el servicio de orden cero y relee λ; nunca a un destino especular;
  - verifica el eje del Shamrock: nunca un eje falso;
  - toma **una** `single_exposure`, nunca el último cuadro del Live (R4-5);
  - **escribe la ventana a disco** y la entrega por `on_window`.

  Stop y E-STOP cortan en el tramo siguiente, y lo adquirido se entrega con `complete=False`. Un
  resultado incompleto no se cose solo (Ronda 3 §4.3).
- **Latido:** `heartbeat_tick` lo renueva mientras haya algún láser abierto, sin importar quién lo abrió, y
  **sin argumento** (R4-B-5, R4-C-3, D-09b, C-29). La rutina nunca abre ni cierra un láser.
- **Primera ventana sin luz** (G8): se pregunta con `on_no_signal`, sin descartar la ventana. La pausa
  sigue latiendo (D-17): una rutina en curso no se corta por el watchdog.
- **Cosido:** el de siempre (`sigmoidal_step_and_glue`), sin cambios de fórmula.
"""
from __future__ import annotations

import json
import math
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple

import numpy as np

from pyspectrum.calibration.halogen_lamp import (
    compute_step_centers, resolve_step_window_nm, sigmoidal_step_and_glue,
)
from pyspectrum.drivers import specular_interlock as si
from pyspectrum.drivers.andor_ccd_driver import (
    DETECTOR_HEIGHT_PX, DETECTOR_WIDTH_PX, READ_MODE_FVB, READ_MODE_IMAGE, READ_MODE_SINGLE_TRACK,
)
from pyspectrum.modules.acquisition import ExposureRequest, Frame, single_exposure

_SHAMROCK_SUCCESS = 20202
_DEVICE = 0
MIN_EXPOSURE_S = 1e-4
SETTLE_EXTRA_S = 0.3              # margen tras SetWavelength, PROVISORIO hasta BANCO-39 (R2-inst §4.4)
READOUT_ESTIMATE_S = 0.08         # lectura de un cuadro completo a 13 MHz (R2-inst §7.1)
WAVELENGTH_READBACK_TOL_NM = 0.01  # R2-inst §2.4
TICK_S = 0.1
# Luz presente en la primera ventana (G8): rango p1-p99 contra el ruido píxel a píxel. PROVISORIO: el umbral
# no está fijado en el diseño; lo ajusta BANCO-53. Sólo pausa y pregunta, nunca descarta.
NO_SIGNAL_RATIO = 10.0


def _max_routine_exposure_s() -> float:
    try:
        from config import MAX_ROUTINE_EXPOSURE_S
        return float(MAX_ROUTINE_EXPOSURE_S)
    except Exception:
        return 10.0


class StopReason(Enum):
    COMPLETED = "COMPLETED"
    USER_STOP = "USER_STOP"
    ESTOP = "ESTOP"
    MOTION_FAILED = "MOTION_FAILED"
    ACQUISITION_FAILED = "ACQUISITION_FAILED"
    DEVICE_LOST = "DEVICE_LOST"


@dataclass(frozen=True)
class StepGlueRequest:
    start_nm: float
    end_nm: float
    overlap_frac: float                 # 0 < solape < 1
    exposure_s: float                   # 1e-4 a MAX_ROUTINE_EXPOSURE_S (10 s, R4-4)
    read_mode: int                      # el vigente en la cámara (C-05)
    grating: int                        # leído del snapshot al armar el pedido (D-09a)
    em_gain: int                        # la del panel, en DAC (D-11)
    normalize_with_lamp: bool = False
    lamp_file: Optional[Path] = None
    use_optical_core: bool = False


@dataclass(frozen=True)
class StepGluePlan:
    centers: List[float]
    window_nm: float
    window_source: str
    grating: int
    estimated_duration_s: float
    frame_shape: Tuple[int, ...]


@dataclass
class PreflightReport:
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    mirror_warning: Optional[str] = None      # la única advertencia con diálogo (Ronda 3 §1.9.1)


@dataclass(frozen=True)
class WindowResult:
    index: int
    center_nm_requested: float
    center_nm_read: float
    wavelength_axis: np.ndarray
    data: np.ndarray
    spectrum_1d: np.ndarray
    exposure_s_actual: float
    frame_index: Optional[int]
    t_start: float
    t_end: float
    open_lasers: Tuple[str, ...]
    light_changed: bool
    path: Optional[Path]


@dataclass(frozen=True)
class StepGlueResult:
    windows: Tuple[WindowResult, ...]
    complete: bool
    stop_reason: StopReason
    detail: str
    plan: StepGluePlan
    glued: Optional[Tuple[np.ndarray, np.ndarray]]
    warnings: Tuple[str, ...] = ()


# ── Medición de la ventana (DEC-033) ─────────────────────────────────────────

def measured_window_nm(spectrometer) -> Optional[float]:
    """Ancho espectral real que cubre el detector, leído de la calibración del espectrógrafo en la posición
    actual. None si no se puede confiar en ella: geometría no verificada, código de error, o un eje no finito
    o degenerado (p. ej. espejo)."""
    if getattr(spectrometer, "geometry_verified", True) is False:
        return None
    try:
        if hasattr(spectrometer, "get_wavelength_axis_cubic"):
            ret, axis = spectrometer.get_wavelength_axis_cubic(_DEVICE, DETECTOR_WIDTH_PX)
        else:
            ret, axis = spectrometer.ShamrockGetCalibration(_DEVICE, DETECTOR_WIDTH_PX)
    except Exception as e:
        print(f"[Step & Glue] No se pudo leer la calibración para planificar: {e}")
        return None
    axis = np.asarray(axis, dtype=np.float64)
    if ret != _SHAMROCK_SUCCESS or axis.size < 2 or not np.all(np.isfinite(axis)):
        return None
    span = float(axis.max() - axis.min())
    return span if span > 0.0 else None


def frame_shape_for(read_mode: int) -> Tuple[int, ...]:
    if int(read_mode) == READ_MODE_IMAGE:
        return (DETECTOR_HEIGHT_PX, DETECTOR_WIDTH_PX)
    return (DETECTOR_WIDTH_PX,)


# ── plan y preflight ──────────────────────────────────────────────────────────

_MEASURE = object()


def plan(request: StepGlueRequest, spectrometer, measured_window=_MEASURE) -> StepGluePlan:
    """`measured_window`: la ventana medida por quien llama (None = no confiable); por defecto se mide acá."""
    measured = measured_window_nm(spectrometer) if measured_window is _MEASURE else measured_window
    window, source = resolve_step_window_nm(request.grating, DETECTOR_WIDTH_PX,
                                            use_optical_core=request.use_optical_core, window_nm=measured)
    # compute_step_centers recibe el solape como FRACCIÓN (0.20), aunque el parámetro se llame overlap_pct
    centers = compute_step_centers(request.start_nm, request.end_nm, float(request.overlap_frac),
                                   grating=request.grating, num_pixels=DETECTOR_WIDTH_PX,
                                   use_optical_core=request.use_optical_core, window_nm=measured)
    centers = sorted(float(c) for c in centers)
    per_window = SETTLE_EXTRA_S + float(request.exposure_s) + READOUT_ESTIMATE_S
    return StepGluePlan(centers, float(window), source, int(request.grating), len(centers) * per_window,
                        frame_shape_for(request.read_mode))


def _laser_nm(name: str) -> Optional[float]:
    m = re.match(r"\s*(\d+(?:\.\d+)?)", str(name))
    return float(m.group(1)) if m else None


def preflight(request: StepGlueRequest, the_plan: StepGluePlan, camera, spectrometer, *,
              mirror_position: str, open_shutters: Sequence[str]) -> PreflightReport:
    rep = PreflightReport()
    if camera is None or not getattr(camera, "available", True):
        rep.blockers.append("cámara no conectada: " + (getattr(camera, "unavailable_reason", "") or "sin motivo"))
    if spectrometer is None or not getattr(spectrometer, "available", True):
        rep.blockers.append("espectrógrafo no conectado: "
                            + (getattr(spectrometer, "unavailable_reason", "") or "sin motivo"))
    max_exp = _max_routine_exposure_s()
    if not (MIN_EXPOSURE_S <= float(request.exposure_s) <= max_exp):
        rep.blockers.append(f"exposición {request.exposure_s:g} s fuera de {MIN_EXPOSURE_S:g} s a {max_exp:g} s (R4-4)")
    if not (0.0 < float(request.overlap_frac) < 1.0):
        rep.blockers.append("el solape tiene que estar entre 0 y 100 %")
    if request.normalize_with_lamp and not request.lamp_file:
        rep.blockers.append("falta el archivo de lámpara; no se normaliza con un perfil sintético")
    if spectrometer is not None and getattr(spectrometer, "available", True):
        try:
            ret, g = spectrometer.ShamrockGetGrating(_DEVICE)
            if ret != _SHAMROCK_SUCCESS:
                rep.blockers.append(f"no se pudo leer la red (código {ret})")
            elif int(g) != int(request.grating):
                rep.blockers.append(f"la red cambió: el pedido es para la red {request.grating} y el equipo está en la {g}")
        except Exception as e:
            rep.blockers.append(f"no se pudo leer la red ({e})")
    for i, c in enumerate(the_plan.centers):
        if si.classify(request.grating, c) != si.FIRST_ORDER:
            rep.blockers.append(f"ventana {i + 1} en condición especular: λc {c:.1f} nm "
                                f"(umbral {si.specular_threshold_nm(request.grating):.1f} nm)")
            break
    if spectrometer is not None and getattr(spectrometer, "available", True) and hasattr(spectrometer, "ShamrockGetWavelengthLimits"):
        ret, lo, hi = spectrometer.ShamrockGetWavelengthLimits(_DEVICE, request.grating)
        if ret == _SHAMROCK_SUCCESS and math.isfinite(lo) and math.isfinite(hi) and hi > lo:
            outside = [c for c in the_plan.centers if not lo <= c <= hi]
            if outside:
                rep.blockers.append(f"{len(outside)} centro(s) fuera de los límites de la red "
                                    f"({lo:.0f}-{hi:.0f} nm)")
        else:
            rep.warnings.append("no se pudieron leer los límites de la red")
    if mirror_position != "down":
        rep.mirror_warning = ("El software no sabe dónde está el espejo de detección." if mirror_position == "unknown"
                              else "El software cree que el espejo de detección está ARRIBA: la luz no llega "
                                   "al espectrómetro.")
    if request.em_gain > 0:
        lo_nm = min(the_plan.centers) - the_plan.window_nm / 2 if the_plan.centers else request.start_nm
        hi_nm = max(the_plan.centers) + the_plan.window_nm / 2 if the_plan.centers else request.end_nm
        for name in open_shutters:
            nm = _laser_nm(name)
            if nm is not None and lo_nm <= nm <= hi_nm:
                rep.warnings.append(f"el barrido contiene {nm:.0f} nm, el láser {name} está abierto y la ganancia "
                                    f"EM es {request.em_gain} DAC: confirmá que el notch está puesto (H-06)")
    return rep


# ── latido ────────────────────────────────────────────────────────────────────

def _default_open():
    from core.nidaq import get_open_shutter_names
    return get_open_shutter_names()


def _default_heartbeat():
    from core.nidaq import heartbeat_shutter
    heartbeat_shutter()


def heartbeat_tick(get_open: Callable[[], List[str]] = _default_open,
                   heartbeat: Callable[..., None] = _default_heartbeat) -> Callable[[], None]:
    """Latido mientras haya algún láser abierto (R4-B-5, R4-C-3), siempre sin argumento (C-29)."""
    def tick():
        try:
            if get_open():
                heartbeat()
        except Exception as e:
            print(f"[Step & Glue] latido: {e}")
    return tick


# ── ejecución ─────────────────────────────────────────────────────────────────

def _has_signal(spec1d: np.ndarray) -> bool:
    x = np.asarray(spec1d, dtype=float)
    x = x[np.isfinite(x)]
    if x.size < 3:
        return False
    span = float(np.percentile(x, 99) - np.percentile(x, 1))
    noise = float(np.std(np.diff(x)) / math.sqrt(2.0))
    return span >= NO_SIGNAL_RATIO * max(noise, 1.0)


def _save_window(run_dir: Path, w_index: int, center_req: float, center_read: float, axis, data, frame: Frame,
                 open_lasers, light_changed, request: StepGlueRequest, the_plan: StepGluePlan,
                 correction: Optional[dict] = None) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / f"ventana_{w_index + 1:02d}_{center_req:.1f}nm.npz"
    meta = {"index": w_index, "center_nm_requested": center_req, "center_nm_read": center_read,
            "exposure_s_requested": request.exposure_s, "exposure_s_actual": frame.exposure_s_actual,
            "frame_index": frame.frame_index, "grating": request.grating, "read_mode": request.read_mode,
            "em_gain_dac": request.em_gain, "window_nm": the_plan.window_nm, "window_source": the_plan.window_source,
            "open_lasers": list(open_lasers), "light_changed": bool(light_changed),
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
    meta.update(correction or {})            # c_sw en el metadato de cada espectro (R3-gui §4.6)
    np.savez(path, wavelength=np.asarray(axis, dtype=np.float64), data=np.asarray(data),
             metadata=np.array(json.dumps(meta)))
    return path


def run_windows(the_plan: StepGluePlan, request: StepGlueRequest, camera, spectrometer, *, run_dir: Path,
                should_abort: Callable[[], bool], on_tick: Callable[[], None], is_estopped: Callable[[], bool],
                get_open: Callable[[], List[str]] = _default_open,
                on_window: Callable[[WindowResult], None] = lambda w: None,
                on_no_signal: Callable[[WindowResult], bool] = lambda w: True,
                on_progress: Callable[[int, int, float], None] = lambda i, n, frac: None,
                clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep,
                zero_order=None) -> StepGlueResult:
    """Recorre las ventanas del plan. Lo llama el worker de la rutina con la sesión ya tomada."""
    if zero_order is None:
        from pyspectrum.modules.zero_order_service import get_zero_order_service
        zero_order = get_zero_order_service(camera, spectrometer)
    windows: List[WindowResult] = []
    n = len(the_plan.centers)
    first_lasers: Optional[Tuple[str, ...]] = None
    # La red y su offset no cambian durante el barrido (sólo λc): una lectura al empezar alcanza.
    from pyspectrum.calibration.repository import spectrum_software_correction
    correction = spectrum_software_correction(spectrometer)

    def result(reason: StopReason, detail: str = "") -> StepGlueResult:
        complete = reason == StopReason.COMPLETED
        glued = None
        if complete and windows:
            glued = sigmoidal_step_and_glue([w.wavelength_axis for w in windows], [w.spectrum_1d for w in windows])
        return StepGlueResult(tuple(windows), complete, reason, detail, the_plan, glued)

    def stop_reason() -> Optional[StopReason]:
        if is_estopped():
            return StopReason.ESTOP
        if should_abort():
            return StopReason.USER_STOP
        return None

    for i, center in enumerate(the_plan.centers):
        r = stop_reason()
        if r:
            return result(r, "barrido detenido")
        on_progress(i, n, 0.0)

        # Movimiento por el servicio (nunca a un destino especular: el preflight lo bloquea) y relectura
        mv = zero_order.move(request.grating, center)
        if not mv.ok:
            return result(StopReason.MOTION_FAILED, f"ventana {i + 1}, λc {center:.2f} nm: {mv.detail} "
                                                    f"(código {mv.code})")
        ret_w, wl_read = spectrometer.ShamrockGetWavelength(_DEVICE)
        if ret_w != _SHAMROCK_SUCCESS or abs(float(wl_read) - center) > WAVELENGTH_READBACK_TOL_NM:
            return result(StopReason.MOTION_FAILED, f"ventana {i + 1}: se pidió {center:.2f} nm y se releyó "
                                                    f"{wl_read} (código {ret_w})")
        t_end_settle = clock() + SETTLE_EXTRA_S
        while clock() < t_end_settle:
            on_tick()
            r = stop_reason()
            if r:
                return result(r, "barrido detenido")
            sleep(min(TICK_S, t_end_settle - clock()))

        # Eje del Shamrock en esta posición, verificado
        ret_a, axis = spectrometer.get_wavelength_axis_cubic(_DEVICE, DETECTOR_WIDTH_PX)
        axis = np.asarray(axis, dtype=np.float64)
        if ret_a != _SHAMROCK_SUCCESS or axis.size != DETECTOR_WIDTH_PX or not np.all(np.isfinite(axis)):
            return result(StopReason.MOTION_FAILED, f"ventana {i + 1}: el eje λ del Shamrock no se pudo leer "
                                                    f"(código {ret_a}); no se usa un eje inventado")

        # Una exposición
        frame = single_exposure(camera, ExposureRequest(float(request.exposure_s), the_plan.frame_shape),
                                should_abort=should_abort, on_tick=on_tick, is_estopped=is_estopped, clock=clock)
        if not isinstance(frame, Frame):
            kind = getattr(frame.kind, "value", str(frame.kind))
            if kind == "user_stop":
                return result(StopReason.USER_STOP, f"ventana {i + 1} interrumpida (sin datos)")
            if kind == "estop":
                return result(StopReason.ESTOP, f"ventana {i + 1} interrumpida por la E-STOP (sin datos)")
            return result(StopReason.ACQUISITION_FAILED, f"ventana {i + 1}: {frame.detail} ({kind}, {frame.call})")
        data = np.asarray(frame.data)
        spec1d = data if data.ndim == 1 else np.mean(data, axis=0)

        lasers = tuple(get_open())
        if first_lasers is None:
            first_lasers = lasers
        changed = lasers != first_lasers
        path = _save_window(Path(run_dir), i, center, float(wl_read), axis, data, frame, lasers, changed,
                            request, the_plan, correction=correction)
        w = WindowResult(i, center, float(wl_read), axis, data, spec1d, frame.exposure_s_actual, frame.frame_index,
                         frame.t_start, frame.t_end, lasers, changed, path)
        windows.append(w)
        on_window(w)
        on_progress(i + 1, n, 1.0)

        # Luz presente en la primera ventana (G8)
        if i == 0 and not _has_signal(spec1d):
            if not on_no_signal(w):
                return result(StopReason.USER_STOP, "sin señal en la ventana 1 (¿espejo arriba o lámpara apagada?)")
    return result(StopReason.COMPLETED, f"{n} ventanas")
