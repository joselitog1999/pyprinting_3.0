# -*- coding: utf-8 -*-
"""Centro de una línea espectral en píxeles y presupuesto de la calibración de λ (paso 14a del bloque A de
PySpectrum, DEC-040; diseño de metrología, `pyspectrum_A_ronda2/metrology.md` §2.1, §3.2, §5.1).

Módulo puro: sin Qt ni hardware.

- **Estimador:** gaussiana + fondo lineal, mínimos cuadrados sin ponderar, en ±3 FWHM, con la ventana
  recentrada una vez. En la simulación de metrología queda dentro del 5-10 % de la cota de Cramér-Rao, sin
  sesgo detectable, y es el único de los probados que no se sesga con un fondo inclinado.
- **No se usa** el despike espacial del repositorio (`core/sif_processor.py::filter_despike_median`):
  sobre una línea angosta marca píxeles del propio pico. Los rayos se rechazan en el tiempo, entre cuadros.
- **Unidades:** píxeles contados desde 0, λ en nm (en aire), cuentas del ADC con el oscuro restado.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Collection, List, Literal, Optional, Sequence, Tuple

import numpy as np
from scipy import stats
from scipy.ndimage import gaussian_filter1d, median_filter
from scipy.optimize import curve_fit

FWHM_PER_SIGMA = 2.0 * math.sqrt(2.0 * math.log(2.0))
MIN_SNR_CALIBRATE = 20.0


@dataclass(frozen=True)
class LineCenterResult:
    success: bool
    center_px: float
    u_center_px: float                 # max(u de la covarianza escalada, u de Tipo A entre cuadros)
    u_center_cov_px: float
    u_center_typeA_px: Optional[float]
    fwhm_px: float
    amplitude_counts: float
    background_counts: float           # en center_px
    background_slope_counts_per_px: float
    snr: float                         # amplitud / σ del residuo del ajuste
    chi2_red: float                    # NaN sin cuadros individuales (no hay σ por píxel)
    centroid_px: float                 # diagnóstico
    asymmetry_px: float                # center_px − centroid_px
    window_px: Tuple[int, int]
    flags: Tuple[str, ...]             # LOW_SNR, SATURATED, ASYMMETRIC, WIDE, EDGE, FIT_FAILED, NO_LINE, SEEDED_BY_OPERATOR


def _failed(flags, window=(0, 0)) -> LineCenterResult:
    nan = float("nan")
    return LineCenterResult(False, nan, nan, nan, None, nan, nan, nan, nan, nan, nan, nan, nan, window, tuple(flags))


def _model_linear(x, amp, x0, sigma, b0, b1, xref):
    return amp * np.exp(-0.5 * ((x - x0) / sigma) ** 2) + b0 + b1 * (x - xref)


def _fit(x, y, p0, background, xref):
    if background == "linear":
        f = lambda xx, a, c, s, b0, b1: _model_linear(xx, a, c, s, b0, b1, xref)
        p_init = p0
    else:
        f = lambda xx, a, c, s, b0: _model_linear(xx, a, c, s, b0, 0.0, xref)
        p_init = p0[:4]
    lower = [0.0, x[0], 0.3, -np.inf] + ([-np.inf] if background == "linear" else [])
    upper = [np.inf, x[-1], (x[-1] - x[0]), np.inf] + ([np.inf] if background == "linear" else [])
    popt, pcov = curve_fit(f, x, y, p0=p_init, bounds=(lower, upper), maxfev=5000)
    if background != "linear":
        popt = np.append(popt, 0.0)
        pcov = np.pad(pcov, ((0, 1), (0, 1)))
    return popt, pcov, f


def _coarse(profile, sigma_guess, lo, hi):
    width = int(max(15 * FWHM_PER_SIGMA * sigma_guess, 31)) | 1
    high = profile - median_filter(profile, size=width, mode="nearest")
    smooth = gaussian_filter1d(high, sigma_guess)
    idx = lo + int(np.argmax(smooth[lo:hi]))
    resid = smooth[lo:hi]
    mad = 1.4826 * np.median(np.abs(resid - np.median(resid)))
    # ruido de un píxel del pasa-altos sin suavizar: la altura del pico se compara contra él
    raw_mad = 1.4826 * np.median(np.abs(high[lo:hi] - np.median(high[lo:hi])))
    return idx, high, smooth, max(mad, 1e-12), max(raw_mad, 1e-12)


def estimate_line_center(profile_counts: np.ndarray, *,
                         center_guess_px: Optional[float] = None,
                         search_range_px: Optional[Tuple[int, int]] = None,
                         fwhm_guess_px: Optional[float] = None,
                         window_fwhm: float = 3.0,
                         background: Literal["linear", "constant"] = "linear",
                         edge_trim_px: int = 15,
                         min_snr_detect: float = 8.0,
                         reference_fwhm_px: Optional[float] = None,
                         per_frame_profiles: Optional[np.ndarray] = None,
                         saturated: bool = False,
                         seeded_by_operator: bool = False,
                         subtracted_variance_counts2: float = 0.0) -> LineCenterResult:
    """Centro de la línea con su incertidumbre y diagnósticos (R2-met §2.1). Nunca "corrige" nada: los
    diagnósticos levantan banderas. Sin línea, saturada o sin ajuste: `success=False` y centro NaN."""
    y = np.asarray(profile_counts, dtype=np.float64).ravel()
    n = y.size
    base_flags: List[str] = ["SEEDED_BY_OPERATOR"] if seeded_by_operator else []
    if saturated:
        return _failed(base_flags + ["SATURATED"])
    if n < 2 * edge_trim_px + 10 or not np.all(np.isfinite(y)):
        return _failed(base_flags + ["NO_LINE"])

    sigma_guess = (fwhm_guess_px / FWHM_PER_SIGMA) if fwhm_guess_px else 2.0
    lo, hi = edge_trim_px, n - edge_trim_px
    if search_range_px is not None:
        lo, hi = max(lo, int(search_range_px[0])), min(hi, int(search_range_px[1]) + 1)
    if hi - lo < 5:
        return _failed(base_flags + ["NO_LINE"])
    idx, high, smooth, noise_s, noise_raw = _coarse(y, sigma_guess, lo, hi)
    if center_guess_px is not None:
        idx = int(round(min(max(center_guess_px, lo), hi - 1)))
    detect_snr = smooth[idx] / noise_s
    if detect_snr < min_snr_detect or high[idx] <= 0:
        return _failed(base_flags + ["NO_LINE"], (lo, hi - 1))

    # FWHM inicial por segundo momento del pasa-altos alrededor del máximo
    if fwhm_guess_px is None:
        half = 8
        a, b = max(0, idx - half), min(n, idx + half + 1)
        w = np.clip(high[a:b], 0, None)
        xs = np.arange(a, b)
        if w.sum() > 0:
            mean = (w * xs).sum() / w.sum()
            sigma_guess = float(np.clip(math.sqrt(max((w * (xs - mean) ** 2).sum() / w.sum(), 0.25)), 0.6, 20))

    def window_around(c, s):
        half = max(4, int(math.ceil(window_fwhm * FWHM_PER_SIGMA * s)))
        a, b = max(0, int(math.floor(c)) - half), min(n, int(math.ceil(c)) + half + 1)
        return a, b

    try:
        a, b = window_around(idx, sigma_guess)
        x = np.arange(a, b, dtype=np.float64)
        p0 = [max(high[idx], 1e-6), float(idx), sigma_guess, float(np.median(y[a:b]) if b - a > 0 else 0.0), 0.0]
        p0[3] = float(min(y[a], y[b - 1]))
        popt, pcov, f = _fit(x, y[a:b], p0, background, float(idx))
        # ventana recentrada en x̂: una ventana descentrada trunca el fondo en forma asimétrica
        a, b = window_around(popt[1], popt[2])
        x = np.arange(a, b, dtype=np.float64)
        xref = float(popt[1])
        p1 = [popt[0], popt[1], popt[2], popt[3] + popt[4] * (xref - idx), popt[4]]
        popt, pcov, f = _fit(x, y[a:b], p1, background, xref)
    except (RuntimeError, ValueError):
        return _failed(base_flags + ["FIT_FAILED"], (lo, hi - 1))
    if not np.all(np.isfinite(pcov)):
        return _failed(base_flags + ["FIT_FAILED"], (a, b - 1))

    amp, x0, sig, b0, b1 = (float(v) for v in popt)
    fit_vals = _model_linear(x, amp, x0, sig, b0, b1, xref)
    resid = y[a:b] - fit_vals
    n_par = 5 if background == "linear" else 4
    dof = max(1, x.size - n_par)
    noise_fit = float(np.sqrt(np.sum(resid ** 2) / dof))
    u_cov = float(np.sqrt(pcov[1, 1]))           # curve_fit sin σ: la covarianza ya está escalada por χ²
    snr = amp / noise_fit if noise_fit > 0 else float("inf")

    chi2 = float("nan")
    u_typeA = None
    if per_frame_profiles is not None:
        frames = np.asarray(per_frame_profiles, dtype=np.float64)
        k = frames.shape[0]
        if k >= 2:
            # varianza entre cuadros agrupada en la ventana: con K = 5, la de cada píxel sola tiene ν = 4 e
            # infla χ² (E[σ²/s²] = ν/(ν − 2) = 2)
            # más la varianza de lo que se restó igual a todos los cuadros (el oscuro medio), que la varianza
            # entre cuadros no ve
            var_mean = float(frames[:, a:b].var(axis=0, ddof=1).mean()) / k + float(subtracted_variance_counts2)
            if var_mean > 0:
                chi2 = float(np.sum(resid ** 2) / var_mean / dof)
            centers = []
            for fr in frames:
                try:
                    pk, _, _ = _fit(x, fr[a:b], [amp, x0, sig, b0, b1], background, xref)
                    centers.append(pk[1])
                except (RuntimeError, ValueError):
                    pass
            if len(centers) >= 2:
                u_typeA = float(np.std(centers, ddof=1) / math.sqrt(len(centers)))
    u_center = max(u_cov, u_typeA) if u_typeA is not None else u_cov

    line_only = y[a:b] - (b0 + b1 * (x - xref))
    w = np.clip(line_only, 0, None)
    centroid = float((w * x).sum() / w.sum()) if w.sum() > 0 else float("nan")
    asym = x0 - centroid

    fwhm = FWHM_PER_SIGMA * sig
    flags = list(base_flags)
    if snr < MIN_SNR_CALIBRATE:
        flags.append("LOW_SNR")
    if np.isfinite(asym) and abs(asym) > max(0.1, 3.0 * u_center):
        flags.append("ASYMMETRIC")
    if reference_fwhm_px and fwhm > 1.5 * reference_fwhm_px:
        flags.append("WIDE")
    if x0 < edge_trim_px or x0 > n - 1 - edge_trim_px:
        flags.append("EDGE")
    return LineCenterResult(True, x0, u_center, u_cov, u_typeA, fwhm, amp, b0, b1, snr, chi2, centroid, asym,
                            (int(a), int(b - 1)), tuple(flags))


def reject_cosmic_rays_temporal(frames_counts: np.ndarray, *, n_sigma: float = 5.0,
                                noise_floor_counts: Optional[float] = None) -> Tuple[np.ndarray, np.ndarray]:
    """Media con recorte entre K ≥ 3 cuadros: se descarta todo valor que se aparte de la mediana del píxel
    más de n_sigma·max(σ_MAD, σ_piso). Devuelve (media recortada, máscara de rechazos)."""
    f = np.asarray(frames_counts, dtype=np.float64)
    if f.shape[0] < 3:
        raise ValueError("el rechazo temporal necesita al menos 3 cuadros")
    med = np.median(f, axis=0)
    dev = np.abs(f - med)
    mad = 1.4826 * np.median(dev, axis=0)
    floor = noise_floor_counts if noise_floor_counts is not None else 1.4826 * float(np.median(dev))
    thr = n_sigma * np.maximum(mad, max(floor, 1e-12))
    mask = dev > thr
    kept = np.where(mask, np.nan, f)
    mean = np.nanmean(kept, axis=0)
    mean = np.where(np.isfinite(mean), mean, med)
    return mean, mask


def check_saturation(raw_frames_counts: np.ndarray, *, adc_max_counts: int, max_fraction: float = 0.8) -> bool:
    """True si algún píxel crudo supera max_fraction del ADC (antes de sumar filas, R2-met §2.1 paso 3)."""
    return bool(np.max(raw_frames_counts) > max_fraction * adc_max_counts)


def calibration_residual_px(center_px: float, axis_nm: np.ndarray, lambda_ref_nm: float) -> Tuple[float, float]:
    """r = x̂ − p_SDK(λ_ref) y la dispersión local |dλ/dp| en x̂ (R2-met §1.2). El eje puede crecer o
    decrecer; ValueError si no es monótono o si λ_ref queda fuera."""
    axis = np.asarray(axis_nm, dtype=np.float64)
    d = np.diff(axis)
    if not (np.all(d > 0) or np.all(d < 0)):
        raise ValueError("el eje λ no es monótono")
    px = np.arange(axis.size, dtype=np.float64)
    if d[0] < 0:
        axis, px = axis[::-1], px[::-1]
    if not (axis[0] <= lambda_ref_nm <= axis[-1]):
        raise ValueError(f"λ_ref = {lambda_ref_nm} nm queda fuera del eje ({axis[0]:.2f}-{axis[-1]:.2f} nm)")
    p_ref = float(np.interp(lambda_ref_nm, axis, px))
    grad = np.gradient(np.asarray(axis_nm, dtype=np.float64))
    disp = float(abs(np.interp(center_px, np.arange(grad.size), grad)))
    return float(center_px - p_ref), disp


def pixel_of(axis_nm: np.ndarray, lambda_nm: float) -> float:
    """p_SDK(λ): inversa del eje por interpolación (creciente o decreciente)."""
    axis = np.asarray(axis_nm, dtype=np.float64)
    px = np.arange(axis.size, dtype=np.float64)
    if axis[-1] < axis[0]:
        axis, px = axis[::-1], px[::-1]
    return float(np.interp(lambda_nm, axis, px))


def combine_arrivals(residuals_px: Sequence[float]) -> Tuple[float, float, int, float]:
    """(media, u_A = s/√M, ν = M − 1, s_rep) de M llegadas con el mismo offset."""
    r = np.asarray(residuals_px, dtype=np.float64)
    m = r.size
    if m == 0:
        raise ValueError("sin llegadas")
    s = float(r.std(ddof=1)) if m > 1 else float("nan")
    return float(r.mean()), (s / math.sqrt(m) if m > 1 else float("nan")), m - 1, s


def propose_offset(*, r_px: float, s_px_per_step: Optional[float], current_offset: int) -> Optional[int]:
    """O* = O₀ + round(−r/S) (R2-met §1.5). Sin S medida (BANCO-40) no hay propuesta en pasos."""
    if s_px_per_step is None or not math.isfinite(s_px_per_step) or s_px_per_step == 0:
        return None
    return int(current_offset + round(-r_px / s_px_per_step))


# ── Presupuesto (R2-met §3.2) ──
@dataclass(frozen=True)
class BudgetRow:
    name: str
    gum_type: str                    # "A" o "B"
    distribution: str
    value: Optional[float]           # en px (o None: SIN VALOR)
    sensitivity: str
    contribution_px: Optional[float]
    dof: float                       # math.inf para tipo B
    label: str


def build_budget(*, u_noise_px: float, s_rep_px: float, n_arrivals: int, estimator_bias_px: float = 0.02,
                 software_correction_applied: bool = True, s_px_per_step: Optional[float] = None) -> List[BudgetRow]:
    """Presupuesto de c_sw con M llegadas. Los términos #5-#7 no tienen valor (SIN VALOR): mientras sea
    así, no se declara U (R2-met §3.2)."""
    m = max(1, int(n_arrivals))
    nu = float(max(1, m - 1))
    quant = 0.0 if software_correction_applied else (None if s_px_per_step is None else abs(s_px_per_step) / math.sqrt(12))
    return [
        BudgetRow("#1 ruido del estimador por llegada", "A", "normal", u_noise_px, "1/√M", u_noise_px / math.sqrt(m), nu,
                  "se mide"),
        BudgetRow("#2 repetibilidad de la torreta", "A", "normal", s_rep_px, "1/√M", s_rep_px / math.sqrt(m), nu,
                  "se mide"),
        BudgetRow("#3 sesgo del estimador", "B", "rectangular", estimator_bias_px, "1", estimator_bias_px / math.sqrt(3),
                  math.inf, "SIMULADO"),
        BudgetRow("#4 cuantización del offset", "B", "rectangular", quant, "1", quant, math.inf,
                  "0 con la corrección fina aplicada"),
        BudgetRow("#5 asimetría de la fuga por el notch", "B", "—", None, "1", None, math.inf, "SIN VALOR"),
        BudgetRow("#6 deriva térmica del espectrógrafo", "B", "—", None, "1", None, math.inf, "SIN VALOR (BANCO-A5)"),
        BudgetRow("#7 deriva de λ del láser", "B", "—", None, "1/D", None, math.inf, "SIN VALOR"),
    ]


def expanded_uncertainty(rows: Sequence[BudgetRow], p: float = 0.95) -> Optional[Tuple[float, float, float]]:
    """(u_c, ν_eff por Welch-Satterthwaite, k = t_p(ν_eff)). None si algún término no tiene valor."""
    if any(r.contribution_px is None for r in rows):
        return None
    contrib = [(float(r.contribution_px), r.dof) for r in rows]
    u_c = math.sqrt(sum(c ** 2 for c, _ in contrib))
    denom = sum(c ** 4 / nu for c, nu in contrib if math.isfinite(nu) and c > 0)
    nu_eff = (u_c ** 4 / denom) if denom > 0 else math.inf
    k = float(stats.t.ppf(0.5 + p / 2, nu_eff)) if math.isfinite(nu_eff) else float(stats.norm.ppf(0.5 + p / 2))
    return u_c, nu_eff, k
