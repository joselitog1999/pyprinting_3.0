# -*- coding: utf-8 -*-
"""Calibración automática de λ con la fuga del 532 por el notch, en modo SÓLO MEDIR (paso 14b del bloque
A, DEC-040).

Diseño: metrología (`pyspectrum_A_ronda2/metrology.md` §1-§4), instrumentación (`instrumentation.md` §4),
GUI (`pyspectrum_A_ronda3/gui_design.md` §1.6, §2.3, §4.2, §4.4) y reconciliación D-01, D-02, D-05.

**Qué hace.** Por red (150 → 1200, nunca el espejo):
1. llega a λc siempre desde abajo (λc − δ y después λc), con el 532 cerrado;
2. toma el oscuro con el 532 cerrado, y cada llegada con el 532 abierto sólo durante los cuadros;
3. estima el centro de la línea (`core/spectral_line_fit.py`) y el residuo r = x̂ − p_SDK(λ_ref);
4. agrega llegadas de a una, desde el mínimo, hasta que u_A ≤ u objetivo o se llega al máximo (M secuencial);
5. hace una llegada más como control de deriva y, si se pidió, recorre la línea a ±0.35 W;
6. evalúa K1-K7 (PROVISORIOS) y guarda un registro PROPOSED con los crudos en un HDF5.

**Qué no hace.** Nunca escribe un offset: el puerto no tiene cómo (R4-C-5; SÓLO MEDIR hasta BANCO-40).
La corrección fina c_sw = −r̄ queda propuesta; aplicarla es una acción aparte del operador (D-04). Sin
px/paso medido no hay propuesta en pasos; con una S previa, O* = O₀ + round(−r/S), y escribirlo es la
transacción del paso 10.

**Exposición y tiempo (R4-D-4):** exposición fija `config.CAL_EXPOSURE_S` (0.10 s) y tope
`config.CAL_MAX_DURATION_S` (600 s) para la rutina completa. Al llegar al tope: se detiene, cierra el 532
y registra lo medido como CANCELADA.
"""
from __future__ import annotations

import hashlib
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Mapping, Optional, Sequence, Tuple

import numpy as np

import config
from core import spectral_line_fit as slf
from pyspectrum.calibration.repository import (CalibrationEntry, CalibrationKey, CalibrationRepository,
                                               CalibrationVerdict)

METHOD = "auto_offset_laser_leak_v1"
ESTIMATOR = "gauss+linear, window 3 FWHM, recentred; temporal rejection 5 sigma"
C_SW_CONVENTION = "lambda(p) = lambda_SDK(p + c_sw)"
CALIBRATABLE_GRATINGS = (1, 2)
# Por red: acercamiento δ (R2-met §2.2), u objetivo (K1) y tope del recorrido a ±0.35 W (K4)
GRATING_DEFAULTS = {1: {"delta_nm": 20.0, "u_target_px": 0.22, "walk_edge_px": 2.0},
                    2: {"delta_nm": 3.0, "u_target_px": 0.43, "walk_edge_px": 3.5}}
K3_MAX_S_REP_PX = 1.0
K4_CENTER_PX = 1.0
K6_CHI2 = (0.5, 2.0)
K7_FACTOR = 3.0
WALK_FRACTION = 0.35
MAX_INVALID_IN_A_ROW = 3
BAD_LINE_FLAGS = {"ASYMMETRIC", "WIDE", "EDGE", "SATURATED", "UNSETTLED"}


class CalibrationStopped(Exception):
    """Stop o E-STOP del operador."""


class CalibrationHardwareError(Exception):
    """El equipo no hizo lo pedido (movimiento, relectura, eje, obturador)."""


class _Deadline(Exception):
    pass


class _Abort(Exception):
    def __init__(self, reason: str, needs_seed: bool = False):
        super().__init__(reason)
        self.reason, self.needs_seed = reason, needs_seed


@dataclass(frozen=True)
class OffsetCalibrationConfig:
    grating: int
    lambda_ref_nm: float
    lambda_ref_source: str
    u_lambda_ref_nm: Optional[float] = None
    lambda_c_nm: Optional[float] = None            # None → lambda_ref_nm
    approach_delta_nm: Optional[float] = None      # None → 20 (150) / 3 (1200)
    frames_per_arrival: int = 5
    dark_frames: int = 5
    arrivals_per_iteration: int = 4
    arrivals_final_min: int = 9
    arrivals_final_max: int = 25
    u_target_px: Optional[float] = None            # None → 0.22 (150) / 0.43 (1200)
    roi_rows: Optional[Tuple[int, int]] = None     # None → traza ± 4 filas
    s_prior_px_per_step: Optional[float] = None
    walk: bool = True
    dry_run: bool = True                           # SÓLO MEDIR: el único modo del bloque A

    def __post_init__(self):
        if int(self.grating) not in CALIBRATABLE_GRATINGS:
            raise ValueError(f"La red {self.grating} no se calibra (sólo 1 y 2; la 3 es el espejo).")
        if self.dry_run is not True:
            raise ValueError("Sólo existe el modo SÓLO MEDIR hasta que BANCO-40 mida px/paso (R4-B 1).")
        if self.frames_per_arrival < 3 or self.dark_frames < 1:
            raise ValueError("Hacen falta al menos 3 cuadros por llegada (rechazo temporal).")
        if not (2 <= self.arrivals_final_min <= self.arrivals_final_max):
            raise ValueError("Llegadas finales: mínimo ≤ máximo, y al menos 2.")

    @property
    def delta_nm(self) -> float:
        return float(self.approach_delta_nm or GRATING_DEFAULTS[self.grating]["delta_nm"])

    @property
    def u_target(self) -> float:
        return float(self.u_target_px or GRATING_DEFAULTS[self.grating]["u_target_px"])


@dataclass(frozen=True)
class AutoCalibrationPlan:
    """D-01. `operator_confirmed` lleva lo que el software no puede sensar."""
    configs: Tuple[OffsetCalibrationConfig, ...]
    reference_mode: Literal["notch_leak", "attenuated_no_notch"]
    operator_confirmed: frozenset

    @property
    def required_confirmations(self) -> Dict[str, str]:
        notch = ("notch_at_input", "el notch puesto a la entrada") if self.reference_mode == "notch_leak" \
            else ("notch_removed_attenuated", "el notch retirado y el 532 atenuado")
        return {notch[0]: notch[1], "detection_mirror_down": "el espejo de detección abajo"}


@dataclass
class Arrival:
    lambda_c_nm: float
    x_hat_px: float
    u_px: float
    r_px: float
    d_nm_per_px: float
    snr: float
    fwhm_px: float
    chi2_red: float
    flags: Tuple[str, ...]
    p_ref_px: float


@dataclass
class GratingCalibration:
    grating: int
    verdict: CalibrationVerdict
    reasons: List[str]
    checks: Dict[str, Tuple[Optional[bool], Any, Any]] = field(default_factory=dict)
    arrivals: List[Arrival] = field(default_factory=list)
    r_hw_px: float = float("nan")
    u_r_hw_px: float = float("nan")
    m_final: int = 0
    s_rep_px: float = float("nan")
    c_sw_px: float = float("nan")
    u_c_sw_px: float = float("nan")
    d_nm_per_px: float = float("nan")
    x_hat_px: float = float("nan")
    drift_check_px: Optional[float] = None
    walk: List[Dict[str, Any]] = field(default_factory=list)
    dispersion_sign_ok: Optional[bool] = None
    offset_read: Optional[int] = None
    detector_offset_read: Optional[int] = None
    proposed_offset: Optional[int] = None
    proposal_reason: str = ""
    flags: Tuple[str, ...] = ()
    needs_seed: bool = False
    raw_path: str = ""
    record_id: str = ""
    roi_rows: Optional[Tuple[int, int]] = None


@dataclass
class CalibrationRun:
    gratings: List[GratingCalibration] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    aborted: bool = False
    abort_reason: str = ""


# ── la rutina ──
class _Context:
    def __init__(self, port, plan, should_abort, clock, max_duration_s, on_progress):
        self.port, self.plan = port, plan
        self._should_abort = should_abort
        self.clock = clock
        self.t0 = clock()
        self.max_duration_s = float(max_duration_s)
        self.on_progress = on_progress or (lambda info: None)
        self.laser_open = False
        self.measured: List[Arrival] = []        # todas las llegadas válidas de la red en curso

    def check(self):
        if self._should_abort():
            raise CalibrationStopped("Detenida por el operador.")
        if self.clock() - self.t0 > self.max_duration_s:
            raise _Deadline()

    def laser(self, open_: bool):
        if open_ == self.laser_open and not open_:
            return
        ok = self.port.set_laser(open_)
        self.laser_open = bool(open_) and bool(ok)
        if open_ and not ok:
            raise CalibrationHardwareError("El obturador del 532 no confirmó la apertura.")

    def frames(self, n: int, rows, light: bool) -> np.ndarray:
        self.check()
        self.laser(light)
        try:
            data = self.port.acquire(n, config.CAL_EXPOSURE_S, rows, self._should_abort)
        finally:
            if light:
                self.laser(False)
        return np.asarray(data, dtype=np.float64)

    def approach(self, grating: int, lambda_c: float, delta: float):
        """Siempre desde abajo, y nunca con el 532 abierto."""
        self.check()
        self.laser(False)
        for target in (lambda_c - delta, lambda_c):
            err = self.port.move(grating, float(target))
            if err:
                raise CalibrationHardwareError(f"El espectrógrafo no fue a {target:.3f} nm: {err}")
            self.port.tick()

    def axis(self) -> np.ndarray:
        axis = np.asarray(self.port.read_axis(), dtype=np.float64)
        if axis.size != 1004 or not np.all(np.isfinite(axis)):
            raise CalibrationHardwareError("El eje λ del Shamrock no es confiable (tamaño o valores).")
        return axis


def _find_trace(img: np.ndarray, roi_rows: Optional[Tuple[int, int]]) -> Tuple[int, int]:
    if roi_rows is not None:
        return int(roi_rows[0]), int(roi_rows[1])
    rows_signal = (img - np.median(img)).sum(axis=1)
    trace = int(np.argmax(rows_signal))
    return max(0, trace - 4), min(img.shape[0], trace + 5)


def _settle_ok(per_frame: np.ndarray, est: slf.LineCenterResult) -> bool:
    """Confirmación óptica del asentamiento (R2-inst §4.4-4): el centro del primer y del último cuadro no
    se separa más de max(0.1 px, 3·√2·u de un cuadro). El 0.1 px solo dispararía con el ruido de un cuadro."""
    first = slf.estimate_line_center(per_frame[0], center_guess_px=est.center_px)
    last = slf.estimate_line_center(per_frame[-1], center_guess_px=est.center_px)
    if not (first.success and last.success):
        return True
    tol = max(0.1, 3.0 * math.sqrt(2.0) * max(first.u_center_px, last.u_center_px))
    return abs(last.center_px - first.center_px) <= tol


def _measure_arrival(ctx: _Context, cfg: OffsetCalibrationConfig, lambda_c: float, rows, dark_mean,
                     ref_fwhm, seed, store: List[Dict[str, Any]], retry: bool = True,
                     dark_var: float = 0.0) -> Optional[Arrival]:
    ctx.approach(cfg.grating, lambda_c, cfg.delta_nm)
    axis = ctx.axis()
    raw = ctx.frames(cfg.frames_per_arrival, rows, light=True)
    if slf.check_saturation(raw, adc_max_counts=_adc_max()):
        raise _Abort("Saturación con la exposición fija de 0.10 s: demasiada luz. ¿El filtro de densidad está "
                     "en potencia alta?")
    per_frame = (raw - dark_mean[None]).sum(axis=1)
    cleaned, _mask = slf.reject_cosmic_rays_temporal(per_frame)
    seeded = seed is not None and abs(lambda_c - cfg.lambda_ref_nm) < 1e-9
    est = slf.estimate_line_center(cleaned, per_frame_profiles=per_frame, reference_fwhm_px=ref_fwhm,
                                   center_guess_px=seed[0] if seeded else None,
                                   search_range_px=seed[1] if seeded else None, seeded_by_operator=seeded,
                                   subtracted_variance_counts2=dark_var)
    if not est.success:
        return None
    flags = est.flags
    if not _settle_ok(per_frame, est):
        if retry:
            return _measure_arrival(ctx, cfg, lambda_c, rows, dark_mean, ref_fwhm, seed, store, retry=False,
                                    dark_var=dark_var)
        flags = flags + ("UNSETTLED",)
    r, d = slf.calibration_residual_px(est.center_px, axis, cfg.lambda_ref_nm)
    arrival = Arrival(float(lambda_c), est.center_px, est.u_center_px, r, d, est.snr, est.fwhm_px,
                      est.chi2_red, flags, slf.pixel_of(axis, cfg.lambda_ref_nm))
    store.append({"lambda_c_nm": float(lambda_c), "axis": axis, "per_frame": per_frame.astype(np.float32),
                  "x_hat_px": est.center_px, "r_px": r, "profile": cleaned.astype(np.float32),
                  "window_px": est.window_px})
    return arrival


def _adc_max() -> int:
    from pyspectrum.drivers.andor_ccd_driver import ADC_MAX_COUNTS
    return int(ADC_MAX_COUNTS)


def _arrivals(ctx, cfg, lambda_c, rows, dark_mean, ref_fwhm, seed, store, *, n_min, n_max, u_target,
              out: List[Arrival], info) -> Tuple[float, float, int, float]:
    invalid = 0
    batch: List[Arrival] = []
    while True:
        if len(batch) >= n_min:
            mean, u_a, nu, s = slf.combine_arrivals([a.r_px for a in batch])
            if u_target is None or (math.isfinite(u_a) and u_a <= u_target) or len(batch) >= n_max:
                return mean, u_a, nu, s
        a = _measure_arrival(ctx, cfg, lambda_c, rows, dark_mean, ref_fwhm, seed, store,
                             dark_var=float(info.get("dark_var", 0.0)))
        if a is None:
            invalid += 1
            if invalid >= MAX_INVALID_IN_A_ROW:
                raise _Abort(f"Se perdió la línea: {invalid} llegadas seguidas sin ajuste en {lambda_c:.3f} nm.")
            continue
        invalid = 0
        batch.append(a)
        out.append(a)
        ctx.measured.append(a)
        ctx.on_progress(dict(info, arrival=a, n=len(batch), n_max=n_max, profile=store[-1]["profile"],
                             window_px=store[-1]["window_px"], lambda_c_nm=lambda_c))


def _evaluate(res: GratingCalibration, cfg: OffsetCalibrationConfig, verification: List[Arrival]) -> None:
    g = cfg.grating
    checks: Dict[str, Tuple[Optional[bool], Any, Any]] = {}
    checks["K1"] = (res.u_c_sw_px <= cfg.u_target, round(res.u_c_sw_px, 4), cfg.u_target)
    checks["K3"] = (res.s_rep_px <= K3_MAX_S_REP_PX, round(res.s_rep_px, 4), K3_MAX_S_REP_PX)
    if res.walk:
        edge_tol = GRATING_DEFAULTS[g]["walk_edge_px"]
        center_ok = res.drift_check_px is not None and abs(res.drift_check_px) <= K4_CENTER_PX
        edges_ok = all(abs(w["residual_px"]) <= edge_tol for w in res.walk)
        checks["K4"] = (bool(center_ok and edges_ok),
                        [round(w["residual_px"], 3) for w in res.walk], {"centro": K4_CENTER_PX, "±0.35 W": edge_tol})
        checks["K5"] = (res.dispersion_sign_ok, res.dispersion_sign_ok, "igual al eje del SDK")
    else:
        checks["K4"] = (None, None, "recorrido no pedido")
        checks["K5"] = (None, None, "recorrido no pedido")
    snr_min = min(a.snr for a in verification)
    bad = sorted({f for a in verification for f in a.flags if f in BAD_LINE_FLAGS})
    chi2 = [a.chi2_red for a in verification if math.isfinite(a.chi2_red)]
    chi2_med = float(np.median(chi2)) if chi2 else float("nan")
    k6 = snr_min >= slf.MIN_SNR_CALIBRATE and not bad and (not chi2 or K6_CHI2[0] <= chi2_med <= K6_CHI2[1])
    checks["K6"] = (bool(k6), {"snr_min": round(snr_min, 1), "banderas": bad, "chi2_mediana": round(chi2_med, 3)},
                    {"snr": slf.MIN_SNR_CALIBRATE, "chi2": K6_CHI2})
    if res.drift_check_px is None:
        checks["K7"] = (None, None, "sin control de deriva")
    else:
        checks["K7"] = (abs(res.drift_check_px) <= K7_FACTOR * res.s_rep_px, round(res.drift_check_px, 4),
                        f"3·s_rep = {K7_FACTOR * res.s_rep_px:.3f}")
    res.checks = checks
    names = {"K1": "incertidumbre de la corrección", "K3": "repetibilidad", "K4": "recorrido de la línea",
             "K5": "signo de la dispersión", "K6": "calidad de la línea", "K7": "deriva"}
    failed = [f"{k}: {names[k]} ({v[1]} contra {v[2]})" for k, v in checks.items() if v[0] is False]
    missing = [k for k, v in checks.items() if v[0] is None]
    if failed:
        res.verdict, res.reasons = CalibrationVerdict.RECHAZADA, failed
    elif missing:
        res.verdict = CalibrationVerdict.EN_SECO
        res.reasons = [f"SÓLO MEDIDA: residuo r = {res.r_hw_px:+.2f} ± {res.u_r_hw_px:.2f} px; sin evaluar "
                       f"{', '.join(missing)}"]
    else:
        res.verdict = CalibrationVerdict.ACEPTADA_CON_RESERVA
        res.reasons = ["CON RESERVA: U no declarada (faltan #5, #6 y #7); criterios PROVISORIOS"]


def _write_raw(data_dir: Optional[Path], grating: int, dark_mean, store, roi_rows) -> Tuple[str, str]:
    if data_dir is None or not store:
        return "", ""
    import h5py
    d = Path(data_dir)
    d.mkdir(parents=True, exist_ok=True)
    path = d / time.strftime(f"cal_%Y%m%d_%H%M%S_g{grating}.h5")
    k = 1
    while path.exists():
        path = d / time.strftime(f"cal_%Y%m%d_%H%M%S_g{grating}_{k}.h5")
        k += 1
    with h5py.File(path, "w") as f:
        f.attrs["grating"] = grating
        f.attrs["roi_rows"] = list(roi_rows) if roi_rows else []
        f.attrs["exposure_s"] = config.CAL_EXPOSURE_S
        f.create_dataset("dark_mean", data=np.asarray(dark_mean, dtype=np.float32), compression="gzip")
        for i, a in enumerate(store):
            grp = f.create_group(f"arrivals/{i:03d}")
            grp.attrs["lambda_c_nm"] = a["lambda_c_nm"]
            grp.attrs["x_hat_px"] = a["x_hat_px"]
            grp.attrs["r_px"] = a["r_px"]
            grp.create_dataset("axis_nm", data=a["axis"])
            grp.create_dataset("per_frame_profiles", data=a["per_frame"], compression="gzip")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return str(path), digest


def _calibrate_grating(ctx: _Context, cfg: OffsetCalibrationConfig, seed) -> Tuple[GratingCalibration, Dict[str, Any], List]:
    port, g = ctx.port, cfg.grating
    ctx.measured = []
    res = GratingCalibration(g, CalibrationVerdict.CANCELADA, [])
    res.offset_read = port.read_grating_offset(g)
    res.detector_offset_read = port.read_detector_offset()
    lam = float(cfg.lambda_ref_nm)
    lc = float(cfg.lambda_c_nm or lam)
    store: List[Dict[str, Any]] = []
    extra: Dict[str, Any] = {"dark_mean": np.zeros((1, 1004))}
    info: Dict[str, Any] = {"grating": g, "lambda_c_nm": lc}
    try:
        # sonda: ¿hay luz y dónde está la traza? (R2-inst §4.1 K8)
        ctx.approach(g, lc, cfg.delta_nm)
        axis0 = ctx.axis()
        probe = ctx.frames(cfg.frames_per_arrival, None, light=True)
        if slf.check_saturation(probe, adc_max_counts=_adc_max()):
            raise _Abort("Saturación con la exposición fija de 0.10 s: demasiada luz. ¿El filtro de densidad "
                         "está en potencia alta?")
        img = probe.mean(axis=0)
        rows = _find_trace(img, cfg.roi_rows)
        res.roi_rows = rows
        seeded = seed is not None
        prof = img[rows[0]:rows[1]].sum(axis=0)
        est0 = slf.estimate_line_center(prof - np.median(prof), center_guess_px=seed[0] if seeded else None,
                                        search_range_px=seed[1] if seeded else None, seeded_by_operator=seeded)
        if not est0.success:
            raise _Abort("No se ve la línea de 532: ¿espejo de detección arriba, notch que no deja pasar nada o "
                         "láser apagado?", needs_seed=True)
        ref_fwhm = est0.fwhm_px
        dark = ctx.frames(cfg.dark_frames, rows, light=False)
        dark_mean = dark.mean(axis=0)
        extra["dark_mean"] = dark_mean
        # varianza del perfil de oscuro medio (suma de filas), que se resta igual a cada cuadro
        dark_var = (float(dark.sum(axis=1).var(axis=0, ddof=1).mean()) / dark.shape[0]) if dark.shape[0] > 1 else 0.0
        extra["dark_var"] = dark_var
        info["dark_var"] = dark_var
        # verificación con M secuencial en el offset vigente (en SÓLO MEDIR no hay otro)
        verification: List[Arrival] = []
        mean, u_a, nu, s_rep = _arrivals(ctx, cfg, lc, rows, dark_mean, ref_fwhm, seed, store,
                                         n_min=cfg.arrivals_final_min, n_max=cfg.arrivals_final_max,
                                         u_target=cfg.u_target, out=verification, info=info)
        res.arrivals = list(verification)
        res.r_hw_px, res.u_r_hw_px, res.m_final, res.s_rep_px = mean, u_a, len(verification), s_rep
        res.c_sw_px, res.u_c_sw_px = -mean, u_a
        res.x_hat_px = float(np.mean([a.x_hat_px for a in verification]))
        res.d_nm_per_px = float(np.mean([a.d_nm_per_px for a in verification]))
        # control de deriva con una llegada nueva
        drift: List[Arrival] = []
        _arrivals(ctx, cfg, lc, rows, dark_mean, ref_fwhm, seed, store, n_min=1, n_max=1, u_target=None,
                  out=drift, info=dict(info, stage="deriva"))
        res.arrivals += drift
        res.drift_check_px = drift[0].r_px - mean
        # recorrido de la línea a ±0.35 W, con la corrección fina aplicada
        if cfg.walk:
            width = float(port.window_nm(g))
            lcs, xs, preds = [lc], [res.x_hat_px], [float(np.mean([a.p_ref_px for a in verification]))]
            for frac in (-WALK_FRACTION, +WALK_FRACTION):
                lw = lam + frac * width
                pts: List[Arrival] = []
                m, u, _, _ = _arrivals(ctx, cfg, lw, rows, dark_mean, ref_fwhm, None, store,
                                       n_min=cfg.arrivals_per_iteration, n_max=cfg.arrivals_per_iteration,
                                       u_target=None, out=pts, info=dict(info, lambda_c_nm=lw, stage="recorrido"))
                res.arrivals += pts
                x_mean = float(np.mean([a.x_hat_px for a in pts]))
                res.walk.append({"lambda_c_nm": lw, "x_hat_px": x_mean, "residual_px": m + res.c_sw_px, "u_px": u,
                                 "M": len(pts)})
                lcs.append(lw)
                xs.append(x_mean)
                preds.append(float(np.mean([a.p_ref_px for a in pts])))
            slope_meas = np.polyfit(lcs, xs, 1)[0]
            slope_pred = np.polyfit(lcs, preds, 1)[0]
            res.dispersion_sign_ok = bool(np.sign(slope_meas) == np.sign(slope_pred))
        res.flags = tuple(sorted({f for a in res.arrivals for f in a.flags}))
        _evaluate(res, cfg, verification)
        res.proposed_offset = slf.propose_offset(r_px=res.r_hw_px, s_px_per_step=cfg.s_prior_px_per_step,
                                                 current_offset=int(res.offset_read))
        res.proposal_reason = ("propuesta con la S previa del archivo" if res.proposed_offset is not None else
                               "residuo medido; conversión a pasos pendiente: falta px/paso (BANCO-40)")
        del axis0
        return res, extra, store
    except CalibrationStopped:
        res.verdict = CalibrationVerdict.CANCELADA
        res.arrivals = list(ctx.measured)
        res.reasons = [f"cancelada tras {len(res.arrivals)} llegadas"]
        raise _Cancel(res, extra, store)
    except _Deadline:
        res.verdict = CalibrationVerdict.CANCELADA
        res.arrivals = list(ctx.measured)
        res.reasons = [f"tope de {int(ctx.max_duration_s)} s de la rutina (R4-D-4), tras {len(store)} llegadas; "
                       f"no aceptada"]
        raise _Cancel(res, extra, store)
    except (_Abort, CalibrationHardwareError) as e:
        res.verdict = CalibrationVerdict.RECHAZADA
        reason = e.reason if isinstance(e, _Abort) else f"falla del equipo: {e}"
        res.reasons = [reason]
        res.arrivals = list(ctx.measured)
        res.needs_seed = isinstance(e, _Abort) and e.needs_seed
        raise _Failed(res, extra, store, reason)


class _Cancel(Exception):
    def __init__(self, res, extra, store):
        self.res, self.extra, self.store = res, extra, store


class _Failed(Exception):
    def __init__(self, res, extra, store, reason):
        self.res, self.extra, self.store, self.reason = res, extra, store, reason


def _record(repo: CalibrationRepository, port, plan: AutoCalibrationPlan, cfg: OffsetCalibrationConfig,
            res: GratingCalibration, raw: Tuple[str, str]) -> None:
    ident = port.identity()
    key = None
    try:
        key = CalibrationKey(str(ident["serial"]), cfg.grating, float(port.grating_lines(cfg.grating)),
                             int(ident["entrance_port"]), int(ident["exit_port"]))
    except (KeyError, TypeError, ValueError):
        key = None
    det = port.detector_state() if hasattr(port, "detector_state") else {}
    rows = slf.build_budget(u_noise_px=float(np.median([a.u_px for a in res.arrivals])) if res.arrivals else float("nan"),
                            s_rep_px=res.s_rep_px, n_arrivals=max(1, res.m_final))
    expanded = slf.expanded_uncertainty(rows)
    belief = port.mirror_belief() if hasattr(port, "mirror_belief") else None
    values = {
        "dry_run": True, "verdict": res.verdict.value, "reasons": list(res.reasons),
        "checks": {k: {"ok": v[0], "value": v[1], "threshold": v[2]} for k, v in res.checks.items()},
        "estimator": ESTIMATOR, "provenance": "EXPERIMENTAL",
        "lambda_ref_nm": cfg.lambda_ref_nm, "lambda_ref_medium": "air", "lambda_ref_source": cfg.lambda_ref_source,
        "u_lambda_ref_nm": cfg.u_lambda_ref_nm,
        "declared_geometry": {"n_px": int(ident.get("n_px", 0)), "pixel_width_um": float(ident.get("pixel_um", 0.0))},
        "camera_serial": ident.get("camera_serial"),
        "slit_width_um": port.read_slit_um(), "roi_rows": list(res.roi_rows) if res.roi_rows else None,
        "filters": {"reference_mode": plan.reference_mode,
                    "notch": "puesto" if plan.reference_mode == "notch_leak" else "retirado",
                    "density_filter": "baja (lo fija la rutina)"},
        "operator_confirmed": sorted(plan.operator_confirmed),
        "detection_mirror_state": {"operator_confirmed": "detection_mirror_down" in plan.operator_confirmed,
                                   "software_belief": None if belief is None else belief},
        "exposure_s": config.CAL_EXPOSURE_S, "em_gain": det.get("em_gain"), "ccd_temperature_c": det.get("ccd_temp_c"),
        "ccd_temperature_status": det.get("temp_status"),
        "n_frames_per_arrival": cfg.frames_per_arrival, "n_dark_frames": cfg.dark_frames,
        "grating_offset_before": res.offset_read, "grating_offset_after": res.offset_read,
        "detector_offset_read": res.detector_offset_read,
        "offsets_tried": [{"O": res.offset_read, "r_mean_px": res.r_hw_px, "u_A_px": res.u_r_hw_px,
                           "M": res.m_final}] if res.m_final else [],
        "S_px_per_step": cfg.s_prior_px_per_step, "S_source": "previa" if cfg.s_prior_px_per_step else None,
        "lambda_c_nm": cfg.lambda_c_nm or cfg.lambda_ref_nm, "x_hat_px": res.x_hat_px,
        "r_hw_px": res.r_hw_px, "u_r_hw_px": res.u_r_hw_px, "M_final": res.m_final, "nu": max(0, res.m_final - 1),
        "s_rep_px": res.s_rep_px, "c_sw_px": res.c_sw_px, "u_c_sw_px": res.u_c_sw_px,
        "c_sw_convention": C_SW_CONVENTION, "D_nm_per_px": res.d_nm_per_px,
        "c_sw_nm": res.c_sw_px * res.d_nm_per_px if math.isfinite(res.c_sw_px) else None,
        "drift_check_px": res.drift_check_px, "walk": res.walk, "dispersion_sign_ok": res.dispersion_sign_ok,
        "flags": list(res.flags), "seeded_by_operator": "SEEDED_BY_OPERATOR" in res.flags,
        "arrivals_r_px": [a.r_px for a in res.arrivals],
        "budget": [{"name": r.name, "type": r.gum_type, "contribution_px": r.contribution_px, "label": r.label}
                   for r in rows],
        "U_px": None if expanded is None else expanded[2] * expanded[0],
        "proposed_offset": res.proposed_offset, "proposal_reason": res.proposal_reason,
        "needs_seed": res.needs_seed,
        "raw_data_path": raw[0] or None, "raw_data_sha256": raw[1] or None,
        "simulated": bool(getattr(port, "simulated", False)),
    }
    for k, v in list(values.items()):
        if isinstance(v, float) and not math.isfinite(v):
            values[k] = None
    entry = CalibrationEntry("PROPOSED", key, method=METHOD, note=f"red {cfg.grating}", values=values)
    repo.append(entry)
    res.record_id = entry.record_id


def run_auto_calibration(port, plan: AutoCalibrationPlan, repo: CalibrationRepository, *,
                         data_dir: Optional[Path] = None, should_abort: Callable[[], bool] = lambda: False,
                         clock: Callable[[], float] = time.monotonic,
                         on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
                         max_duration_s: Optional[float] = None,
                         seed: Optional[Mapping[int, Tuple[float, Tuple[int, int]]]] = None) -> CalibrationRun:
    """Corre la calibración SÓLO MEDIR por red. Nunca escribe al equipo; cada red empezada deja un registro."""
    run = CalibrationRun()
    missing = [text for key, text in plan.required_confirmations.items() if key not in plan.operator_confirmed]
    if missing:
        run.blockers = [f"Falta que el operador confirme: {m}." for m in missing]
        return run
    blockers, warnings = port.preflight()
    run.blockers, run.warnings = list(blockers), list(warnings)
    if run.blockers:
        return run
    err = port.begin()
    if err:
        run.blockers = [err]
        return run
    ctx = _Context(port, plan, should_abort, clock, max_duration_s or config.CAL_MAX_DURATION_S, on_progress)
    try:
        for cfg in sorted(plan.configs, key=lambda c: c.grating):
            try:
                res, extra, store = _calibrate_grating(ctx, cfg, (seed or {}).get(cfg.grating))
            except _Cancel as c:
                res, extra, store = c.res, c.extra, c.store
                run.aborted, run.abort_reason = True, res.reasons[0]
            except _Failed as f:
                res, extra, store = f.res, f.extra, f.store
                run.aborted, run.abort_reason = True, f.reason
            finally:
                try:
                    ctx.laser(False)
                except Exception:
                    pass
            raw = _write_raw(data_dir, cfg.grating, extra["dark_mean"], store, res.roi_rows)
            res.raw_path = raw[0]
            _record(repo, port, plan, cfg, res, raw)
            run.gratings.append(res)
            if run.aborted:
                break
    finally:
        try:
            port.set_laser(False)
        finally:
            port.end()
    return run


# ── el puerto contra el equipo real (o el simulador en SAFE_MODE) ──
class PySpectrumCalibrationPort:
    """Cámara (pylablib), Shamrock y el 532, con los servicios de los pasos 6-8. **No tiene ningún método
    que escriba un offset**: la calibración del bloque A es SÓLO MEDIR."""

    def __init__(self, camera, spectrometer, *, tick: Optional[Callable[[], None]] = None):
        from config import SHUTTERS
        from pyspectrum.modules.step_glue_engine import heartbeat_tick
        self.camera, self.spectrometer = camera, spectrometer
        self.laser_name = SHUTTERS[0]
        self._tick = tick or heartbeat_tick()
        self.simulated = bool(getattr(camera, "is_mock", False) or type(camera).__name__.startswith("_Mock"))

    # lecturas
    def _ok(self, ret) -> bool:
        from pyspectrum.drivers.shamrock_driver import SHAMROCK_SUCCESS
        return ret == SHAMROCK_SUCCESS

    def identity(self) -> Dict[str, Any]:
        from pyspectrum.drivers.shamrock_driver import DEVICE
        s = self.spectrometer
        ret_s, serial = s.ShamrockGetSerialNumber(DEVICE)
        ret_n, n_px = s.ShamrockGetNumberPixels(DEVICE)
        ret_w, width = s.ShamrockGetPixelWidth(DEVICE)
        ports = []
        for flipper in (1, 2):
            try:
                ret, port = s.ShamrockGetFlipper(DEVICE, flipper)
                ports.append(int(port) if self._ok(ret) else None)
            except Exception:
                ports.append(None)
        return {"serial": str(serial) if self._ok(ret_s) else None, "camera_serial": None,
                "n_px": int(n_px) if self._ok(ret_n) else None, "pixel_um": float(width) if self._ok(ret_w) else None,
                "entrance_port": ports[0], "exit_port": ports[1]}

    def grating_lines(self, g: int) -> Optional[float]:
        from pyspectrum.drivers.shamrock_driver import DEVICE
        info = self.spectrometer.ShamrockGetGratingInfo(DEVICE, g)
        return float(info[1]) if info and self._ok(info[0]) else None

    def read_grating_offset(self, g: int) -> Optional[int]:
        from pyspectrum.drivers.shamrock_driver import DEVICE
        ret, v = self.spectrometer.ShamrockGetGratingOffset(DEVICE, g)
        return int(v) if self._ok(ret) else None

    def read_detector_offset(self) -> Optional[int]:
        from pyspectrum.drivers.shamrock_driver import DEVICE
        ret, v = self.spectrometer.ShamrockGetDetectorOffset(DEVICE)
        return int(v) if self._ok(ret) else None

    def read_slit_um(self) -> Optional[float]:
        from pyspectrum.drivers.shamrock_driver import DEVICE, INPUT_SLIT_PORT
        s = self.spectrometer
        try:
            # driver real: get_slit (ShamrockGetAutoSlitWidth por dentro, como el legado); simulador: GetSlit
            reader = s.get_slit if hasattr(s, "get_slit") else s.ShamrockGetSlit
            ret, v = reader(DEVICE, INPUT_SLIT_PORT)
            return float(v) if self._ok(ret) else None
        except Exception:
            return None

    def detector_state(self) -> Dict[str, Any]:
        from pyspectrum.services.spectrometer_state import read_camera_state
        try:
            st = read_camera_state(self.camera)
            temp = st.get("temperature_c")
            gain = st.get("em_gain")
            return {"em_gain": getattr(gain, "value", None), "ccd_temp_c": getattr(temp, "value", None),
                    "temp_status": getattr(temp, "detail", None)}
        except Exception:
            return {}

    def mirror_belief(self) -> Optional[Dict[str, Any]]:
        from core.nidaq import get_detection_mirror_belief
        b = get_detection_mirror_belief()
        return {"position": b.position, "source": b.source}

    def window_nm(self, g: int) -> float:
        from pyspectrum.modules.step_glue_engine import measured_window_nm
        from pyspectrum.calibration.halogen_lamp import resolve_step_window_nm
        w = measured_window_nm(self.spectrometer)
        return float(w) if w else float(resolve_step_window_nm(g))

    # preparación (R2-inst §4.1: K2-K4, K6)
    def preflight(self) -> Tuple[List[str], List[str]]:
        from pyspectrum.drivers.andor_ccd_driver import DRV_SUCCESS, READ_MODE_IMAGE
        from core.nidaq import up_flipper, is_flipper_high_power
        blockers, warnings = [], []
        ident = self.identity()
        if ident["n_px"] != 1004 or ident["pixel_um"] is None or abs(ident["pixel_um"] - 8.0) > 1e-6:
            blockers.append(f"Geometría del detector no verificada: {ident['n_px']} px de {ident['pixel_um']} µm "
                            f"(se espera 1004 × 8.0).")
        try:
            ret = self.camera.set_emccd_gain(0)
            read = self.camera.get_emccd_gain()
            ret_r, gain = (read[0], read[1]) if isinstance(read, (tuple, list)) else (DRV_SUCCESS, read)
            if ret != DRV_SUCCESS or ret_r != DRV_SUCCESS or int(gain) != 0:
                blockers.append(f"Ganancia EM no confirmada en 0 (set {ret}, lectura {ret_r}: {gain}).")
        except Exception as e:
            blockers.append(f"Ganancia EM no confirmada en 0: {e}")
        try:
            if not up_flipper() or is_flipper_high_power():
                blockers.append("El filtro de densidad no quedó en potencia baja.")
        except Exception as e:
            blockers.append(f"Filtro de densidad: {e}")
        try:
            self.camera.set_acquisition_mode(1)
            self.camera.set_read_mode(READ_MODE_IMAGE)
        except Exception as e:
            blockers.append(f"No se pudo fijar el modo de la cámara: {e}")
        st = self.detector_state()
        if st.get("temp_status") not in (None, "stabilized") and "estab" not in str(st.get("temp_status", "")).lower():
            warnings.append("Calibración con el CCD sin estabilizar: el eje no depende del CCD, pero el bias sí.")
        if self.simulated:
            warnings.append("SIMULADOR (SAFE_MODE): el resultado no describe el equipo.")
        return blockers, warnings

    def begin(self) -> Optional[str]:
        from pyspectrum.services.spectrometer_shutter import open_spectrometer_shutter
        r = open_spectrometer_shutter(self.camera, self.spectrometer)
        return None if r.ok else f"El obturador del espectrómetro no abrió: {r.detail}"

    def end(self) -> None:
        from pyspectrum.services.spectrometer_shutter import close_spectrometer_shutter
        self.set_laser(False)
        close_spectrometer_shutter(self.camera, self.spectrometer)

    def tick(self) -> None:
        self._tick()

    # movimiento y adquisición
    def move(self, g: int, lambda_nm: float) -> Optional[str]:
        from pyspectrum.drivers.shamrock_driver import DEVICE
        from pyspectrum.modules.step_glue_engine import SETTLE_EXTRA_S, WAVELENGTH_READBACK_TOL_NM
        from pyspectrum.modules.zero_order_service import get_zero_order_service
        mv = get_zero_order_service(self.camera, self.spectrometer).move(int(g), float(lambda_nm))
        if not mv.ok:
            return f"{mv.detail} (código {mv.code})"
        ret, read = self.spectrometer.ShamrockGetWavelength(DEVICE)
        if not self._ok(ret) or abs(float(read) - float(lambda_nm)) > WAVELENGTH_READBACK_TOL_NM:
            return f"se pidió {lambda_nm:.3f} nm y se releyó {read} (código {ret})"
        t_end = time.monotonic() + SETTLE_EXTRA_S
        while time.monotonic() < t_end:
            self._tick()
            time.sleep(0.05)
        return None

    def read_axis(self) -> np.ndarray:
        from pyspectrum.drivers.shamrock_driver import DEVICE
        s = self.spectrometer
        if hasattr(s, "get_wavelength_axis_cubic"):
            ret, axis = s.get_wavelength_axis_cubic(DEVICE, 1004)
        else:
            ret, axis = s.ShamrockGetCalibration(DEVICE, 1004)
        if not self._ok(ret):
            raise CalibrationHardwareError(f"No se pudo leer el eje λ (código {ret}).")
        return np.asarray(axis, dtype=np.float64)

    def set_laser(self, open_: bool) -> bool:
        from core.nidaq import open_shutter, close_shutter
        return bool(open_shutter(self.laser_name) if open_ else close_shutter(self.laser_name))

    def acquire(self, n: int, exposure_s: float, rows, should_abort) -> np.ndarray:
        from pyspectrum.modules.acquisition import ExposureRequest, Frame, single_exposure
        from pyspectrum.modules.hardware_session import hardware_session
        r0, r1 = rows if rows is not None else (0, 1002)
        self.camera.set_image(1, 1, 1, 1004, r0 + 1, r1)
        out = []
        for _ in range(int(n)):
            fr = single_exposure(self.camera, ExposureRequest(float(exposure_s), (r1 - r0, 1004)),
                                 should_abort=should_abort, on_tick=self._tick,
                                 is_estopped=lambda: hardware_session.is_emergency_stopped)
            if not isinstance(fr, Frame):
                kind = getattr(fr.kind, "value", str(fr.kind))
                if kind in ("user_stop", "estop"):
                    raise CalibrationStopped("Detenida." if kind == "user_stop" else "E-STOP.")
                raise CalibrationHardwareError(f"No se pudo adquirir: {fr.detail} ({kind}).")
            out.append(np.asarray(fr.data, dtype=np.float64))
            self._tick()
        return np.stack(out)
