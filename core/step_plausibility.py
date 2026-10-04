# -*- coding: utf-8 -*-
"""Topes de plausibilidad de los pasos entre nodos de la grilla (C-01 Ronda 4, R4-17 fase 5; `ronda2_architecture.md`
§4.7, §5.5; `c01_ronda4/experimentalist.md` §5; DEC-050).

Numpy puro, sin Qt. Son la **segunda barrera** de un paso (la primera es la validez: la época de cierre, la apertura y
la pausa o la parada). Sin el BS no hay T1 ni F1 ([INV-R4] 7); la validez descansa en la época y en la apertura, más
T2 y F2.

**Todos los valores son provisionales** hasta BANCO-65 C: [SUPUESTO] o [DERIVADO] en [EXP] §5.

- Deriva sobre P0 (`check_drift_correction`): T2 amplitud (sobre la imagen **cruda**: la normalización min-max borra
  la amplitud), T3 ancho, T4 borde, T5 paso, T6 acumulado (T6 pausa siempre).
- Autofoco (`check_autofocus`): F2 Pearson y relación señal/ruido del pico, F3 |Δz₂|, F4 paso, F5 borde.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, NamedTuple, Optional, Tuple

import numpy as np

STEP_MAX_REJECTIONS = 1          # un rechazo se repite una vez; la segunda falla pausa


@dataclass(frozen=True)
class StepLimits:
    # Deriva (T2-T6)
    drift_amp_snr_min: float = 10.0                       # T2: (máx − mediana)/σ_fondo, imagen cruda
    drift_amp_ratio_range: Tuple[float, float] = (0.5, 2.0)    # T2: × la amplitud de referencia
    drift_width_ratio_range: Tuple[float, float] = (0.7, 1.5)  # T3: × el ancho de referencia
    drift_edge_margin_um: float = 0.27                    # T4: ≈ w₀ (CIBION)
    drift_step_base_nm: float = 50.0                      # T5, por eje
    drift_step_rate_nm_s: float = 2.0
    drift_step_ceiling_nm: float = 500.0
    drift_cumulative_max_um: float = 3.0                  # T6: = margen de deriva del pre-flight; pausa siempre
    # Autofoco (F2-F5)
    af_pearson_min: float = 0.8                           # F2 [SUPUESTO]
    af_peak_snr_min: float = 10.0                         # F2
    af_dz2_max_nm: float = 50.0                           # F3
    af_step_base_nm: float = 100.0                        # F4 (SIN FUENTE para Z)
    af_step_rate_nm_s: float = 2.0
    af_step_ceiling_nm: float = 300.0
    af_edge_frac: float = 0.10                            # F5: fracción de la rampa en cada extremo


DEFAULT_LIMITS = StepLimits()


class DriftReference(NamedTuple):
    """Del primer escaneo aceptado de P0 en la grilla."""
    amplitude_v: float
    width_um: float


class PlausibilityVerdict(NamedTuple):
    ok: bool
    failed: Tuple[str, ...]          # p. ej. ("T5",) o ("F2",)
    values: Mapping[str, float]
    always_pause: bool               # T6
    reason: str = ""


def _robust_sigma(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=float).ravel()
    x = x[np.isfinite(x)]
    if x.size == 0:
        return float("nan")
    med = float(np.median(x))
    return 1.4826 * float(np.median(np.abs(x - med)))


def peak_snr(x: np.ndarray) -> float:
    """(máx − mediana)/σ, con σ robusta (MAD). Un perfil o una imagen oscuros dan ~3; un pico real, decenas."""
    x = np.asarray(x, dtype=float)
    if x.size == 0 or not np.all(np.isfinite(x)):
        return 0.0
    sigma = _robust_sigma(x)
    amp = float(np.max(x) - np.median(x))
    return amp / sigma if sigma > 0 else (float("inf") if amp > 0 else 0.0)


def spot_amplitude_width(image: np.ndarray, pixel_um: Tuple[float, float]) -> Tuple[float, float]:
    """Amplitud (máx − mediana, V) y ancho (σ de los segundos momentos de lo que supera el 30 % del pico, µm)."""
    img = np.asarray(image, dtype=float)
    base = float(np.median(img))
    z = img - base
    amp = float(np.max(z))
    if amp <= 0:
        return 0.0, float("nan")
    w = np.where(z >= 0.3 * amp, z, 0.0)
    total = float(w.sum())
    yy, xx = np.indices(w.shape)
    cy, cx = float((yy * w).sum() / total), float((xx * w).sum() / total)
    vy = float((((yy - cy) * pixel_um[1]) ** 2 * w).sum() / total)
    vx = float((((xx - cx) * pixel_um[0]) ** 2 * w).sum() / total)
    return amp, float(np.sqrt(0.5 * (vx + vy)))


def _allowed_step_nm(base: float, rate: float, ceiling: float, dt_s: float) -> float:
    return min(ceiling, base + rate * max(0.0, float(dt_s)))


def check_drift_correction(image_raw: np.ndarray, center_um: Tuple[float, float],
                           scan_box_um: Optional[Tuple[float, float, float, float]],
                           pixel_um: Optional[Tuple[float, float]], reference: Optional[DriftReference],
                           previous_um: Tuple[float, float], origin_um: Tuple[float, float], dt_s: float,
                           limits: StepLimits = DEFAULT_LIMITS) -> PlausibilityVerdict:
    """¿Se aplica la corrección de deriva? `scan_box_um` = (x_min, x_max, y_min, y_max); sin él no hay T4, y sin
    `pixel_um` no hay T3. Sin referencia, T2 sólo mira la relación señal/ruido y T3 no se evalúa."""
    failed, values = [], {}
    snr = peak_snr(image_raw)
    values["T2_snr"] = snr
    if snr < limits.drift_amp_snr_min:
        failed.append("T2")
    amp, width = spot_amplitude_width(image_raw, pixel_um or (1.0, 1.0))
    values["T2_amplitude_v"] = amp
    if reference is not None and reference.amplitude_v > 0:
        ratio = amp / reference.amplitude_v
        values["T2_ratio"] = ratio
        lo, hi = limits.drift_amp_ratio_range
        if not (lo <= ratio <= hi) and "T2" not in failed:
            failed.append("T2")
        if pixel_um is not None and np.isfinite(width) and reference.width_um > 0:
            wr = width / reference.width_um
            values["T3_width_ratio"] = wr
            lo, hi = limits.drift_width_ratio_range
            if not (lo <= wr <= hi):
                failed.append("T3")
    if scan_box_um is not None:
        x_min, x_max, y_min, y_max = scan_box_um
        edge = min(center_um[0] - x_min, x_max - center_um[0], center_um[1] - y_min, y_max - center_um[1])
        values["T4_edge_um"] = edge
        if edge < limits.drift_edge_margin_um:
            failed.append("T4")
    allowed = _allowed_step_nm(limits.drift_step_base_nm, limits.drift_step_rate_nm_s, limits.drift_step_ceiling_nm,
                               dt_s)
    step = max(abs(center_um[0] - previous_um[0]), abs(center_um[1] - previous_um[1])) * 1000.0
    values["T5_step_nm"], values["T5_allowed_nm"] = step, allowed
    if step > allowed:
        failed.append("T5")
    cumulative = max(abs(center_um[0] - origin_um[0]), abs(center_um[1] - origin_um[1]))
    values["T6_cumulative_um"] = cumulative
    always = cumulative > limits.drift_cumulative_max_um
    if always:
        failed.append("T6")
    reason = _reason(failed, values, {
        "T2": lambda v: f"T2 amplitud: S/R {v['T2_snr']:.1f}" + (f", × {v['T2_ratio']:.2f} de la referencia"
                                                                   if "T2_ratio" in v else ""),
        "T3": lambda v: f"T3 ancho: × {v['T3_width_ratio']:.2f} de la referencia",
        "T4": lambda v: f"T4 borde: a {v['T4_edge_um']:.2f} µm del borde del escaneo",
        "T5": lambda v: f"T5 paso: Δ = {v['T5_step_nm']:.0f} nm, permitido {v['T5_allowed_nm']:.0f} nm",
        "T6": lambda v: f"T6 acumulado: {v['T6_cumulative_um']:.2f} µm desde la referencia",
    })
    return PlausibilityVerdict(not failed, tuple(failed), values, always, reason)


def pearson_at_shift(profile: np.ndarray, lock_profile: np.ndarray, i_max: int) -> float:
    """Pearson entre el perfil nuevo corrido según el máximo de la correlación ("same") y el bloqueado, sobre la
    parte que se superpone (sin envolver)."""
    a = np.asarray(profile, dtype=float)
    b = np.asarray(lock_profile, dtype=float)
    n = min(a.size, b.size)
    if n < 3:
        return 0.0
    a, b = a[:n], b[:n]
    shift = int(i_max) - n // 2
    if shift >= 0:
        a2, b2 = a[shift:], b[:n - shift]
    else:
        a2, b2 = a[:n + shift], b[-shift:]
    if a2.size < 3 or np.std(a2) == 0 or np.std(b2) == 0:
        return 0.0
    return float(np.corrcoef(a2, b2)[0, 1])


def check_autofocus(profile: np.ndarray, lock_profile: np.ndarray, corr: np.ndarray, i_max: int,
                    dz2_um: Optional[float], dz_vs_last_um: Optional[float], dt_s: Optional[float],
                    limits: StepLimits = DEFAULT_LIMITS) -> PlausibilityVerdict:
    """¿Se aplica la corrección de Z? `dz2_um` (la segunda iteración) y `dz_vs_last_um` (contra el último autofoco
    aceptado) son None cuando todavía no se conocen; entonces F3 o F4 no se evalúan."""
    failed, values = [], {}
    r = pearson_at_shift(profile, lock_profile, i_max)
    snr = peak_snr(profile)
    values["F2_pearson"], values["F2_snr"] = r, snr
    if r < limits.af_pearson_min or snr < limits.af_peak_snr_min:
        failed.append("F2")
    if dz2_um is not None:
        values["F3_dz2_nm"] = abs(dz2_um) * 1000.0
        if values["F3_dz2_nm"] > limits.af_dz2_max_nm:
            failed.append("F3")
    if dz_vs_last_um is not None:
        allowed = _allowed_step_nm(limits.af_step_base_nm, limits.af_step_rate_nm_s, limits.af_step_ceiling_nm,
                                   dt_s or 0.0)
        values["F4_step_nm"], values["F4_allowed_nm"] = abs(dz_vs_last_um) * 1000.0, allowed
        if values["F4_step_nm"] > allowed:
            failed.append("F4")
    n = max(1, len(np.asarray(corr)))
    frac = float(i_max) / float(n)
    values["F5_argmax_frac"] = frac
    if frac < limits.af_edge_frac or frac > 1.0 - limits.af_edge_frac:
        failed.append("F5")
    reason = _reason(failed, values, {
        "F2": lambda v: f"F2 calidad: Pearson {v['F2_pearson']:.2f}, S/R del pico {v['F2_snr']:.1f}",
        "F3": lambda v: f"F3 coherencia: la segunda iteración corrige {v['F3_dz2_nm']:.0f} nm",
        "F4": lambda v: f"F4 paso: |Δz| = {v['F4_step_nm']:.0f} nm, permitido {v['F4_allowed_nm']:.0f} nm",
        "F5": lambda v: f"F5 borde: máximo al {100 * v['F5_argmax_frac']:.0f} % de la rampa",
    })
    return PlausibilityVerdict(not failed, tuple(failed), values, False, reason)


def _reason(failed, values, texts) -> str:
    return "; ".join(texts[k](values) for k in failed if k in texts)
