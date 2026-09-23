"""
core/lattice_disorder.py
========================
Motor físico-matemático de alta precisión para el análisis de desorden posicional
y parámetros de red en nanoestructuras periódicas (PyPrinting 3.0).

Fundamentos Teóricos:
1. Espacio Recíproco Continuo (NUFFT 2D):
   S(q_x, q_y) = (1/N) * |sum_j exp(-i (q_x x_j + q_y y_j))|^2
   Calculado de forma continua sobre las coordenadas directas en nanómetros sin
   discretización en histogramas, eliminando el piso de error de cuantización (14.4 nm).
2. Modelo Debye-Waller con Desacoplamiento de Vacancias:
   H(sigma, p) = H_0 * (1 - p)^2 * exp(-sigma^2 / (2 * sigma_char^2)) + H_diffuse
   donde p = f_vac es la fracción de vacancias y sigma es el desorden posicional univariado.
3. KDTree Bounded en Espacio Real:
   Mapeo de partículas al retículo ideal con cota superior distance_upper_bound = a/2.
   Cálculo de residuos cartesianos puros Delta x, Delta y (distribución normal no-sesgada).
4. Función de Distribución Radial g(r):
   Determinación de la función de correlación de pares y ancho del primer pico de vecinos.
5. Calibración Monte Carlo:
   Simulación estocástica acelerada con inyección controlada de vacancias y desorden térmico.
"""

import os
import math
import numpy as np
import pandas as pd
try:
    import cv2
except ImportError:
    cv2 = None
from scipy import ndimage
from scipy.spatial import cKDTree, Voronoi
from scipy.optimize import curve_fit
from scipy.signal import find_peaks, correlate2d
from collections import defaultdict
from typing import Tuple, Dict, Any, Optional, Callable, List, Set


# ==============================================================================
# 1. TRANSFORMADA DE FOURIER CONTINUA 2D (NUFFT) Y PERFILES ESPECTRALES
# ==============================================================================

def compute_structure_factor_2d(
    x: np.ndarray,
    y: np.ndarray,
    a_nominal: float = 450.0,
    n_bins: int = 256,
    f_max_factor: float = 2.5
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Calcula el Factor de Estructura Continuo 2D S(f_x, f_y) sobre coordenadas
    espaciales continuas (x, y) en nanómetros.

    Aprovecha la factorización tensorial del operador exponencial:
        exp(-2pi*i*(fx*x + fy*y)) = exp(-2pi*i*fy*y) * exp(-2pi*i*fx*x)
    permitiendo evaluar la grilla completa mediante una multiplicación matricial
    BLAS extremadamente veloz (~30 ms).

    Parámetros:
    -----------
    x, y : np.ndarray
        Coordenadas de las partículas en nanómetros (1D).
    a_nominal : float
        Período de red nominal esperado en nanómetros (ej. 450.0 nm).
    n_bins : int
        Número de muestras en cada eje del espacio de frecuencias.
    f_max_factor : float
        Límite del rango de frecuencias expresado como múltiplo de 1/a_nominal.

    Retorna:
    --------
    fx : np.ndarray (n_bins,) frecuencias espaciales horizontales [nm^-1].
    fy : np.ndarray (n_bins,) frecuencias espaciales verticales [nm^-1].
    S  : np.ndarray (n_bins, n_bins) densidad espectral de potencia S(fy, fx).
    """
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    N = len(x)
    if N == 0:
        raise ValueError("Se requiere al menos 1 punto para calcular el factor de estructura.")

    # Rango simétrico de frecuencias en torno al origen
    f_max = float(f_max_factor / a_nominal)
    fx = np.linspace(-f_max, f_max, n_bins)
    fy = np.linspace(-f_max, f_max, n_bins)

    # Matrices de fase complejas
    # Ex shape: (n_bins, N), Ey shape: (n_bins, N)
    Ex = np.exp(-2j * np.pi * np.outer(fx, x))
    Ey = np.exp(-2j * np.pi * np.outer(fy, y))

    # M = Ey @ Ex.T tiene forma (n_bins, n_bins)
    # M[k, l] = sum_j Ey[k, j] * Ex[l, j] = sum_j exp(-2pi*i*(fy_k*y_j + fx_l*x_j))
    M = np.matmul(Ey, Ex.T)
    S = (np.abs(M) ** 2) / float(N)

    return fx, fy, S


def extract_1d_profiles(
    S: np.ndarray,
    fx: np.ndarray,
    fy: np.ndarray,
    band_width_bins: int = 3
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Extrae los perfiles unidimensionales a lo largo de los ejes principales fx y fy
    integrando una banda transversal de ancho `band_width_bins` alrededor del eje cero.

    La integración transversal confiere robustez ante pequeñas desalineaciones angulares
    (< 0.5°), evitando la subestimación espuria del pico de Bragg.
    """
    n_bins_y, n_bins_x = S.shape
    iy_zero = np.argmin(np.abs(fy))
    ix_zero = np.argmin(np.abs(fx))

    # Definir rangos de banda transversal
    y_min = max(0, iy_zero - band_width_bins)
    y_max = min(n_bins_y, iy_zero + band_width_bins + 1)

    x_min = max(0, ix_zero - band_width_bins)
    x_max = min(n_bins_x, ix_zero + band_width_bins + 1)

    # Perfil a lo largo de fx promediando la banda de fy
    profile_x = np.mean(S[y_min:y_max, :], axis=0)

    # Perfil a lo largo de fy promediando la banda de fx
    profile_y = np.mean(S[:, x_min:x_max], axis=1)

    return fx, profile_x, fy, profile_y


def _gaussian_with_bg(f, H, f0, sigma_f, bg, slope):
    """Modelo de ajuste gaussiano con fondo lineal."""
    return H * np.exp(-((f - f0) ** 2) / (2.0 * sigma_f ** 2)) + bg + slope * (f - f0)


def fit_bragg_peak_1d(
    f: np.ndarray,
    profile: np.ndarray,
    a_nominal: float = 450.0,
    search_half_width_factor: float = 0.40,
    dc_cut_factor: float = 0.40,
    f_min: Optional[float] = None,
    f_max: Optional[float] = None,
    fixed_bg: Optional[float] = None
) -> Dict[str, Any]:
    """
    Ajusta el pico de Bragg principal (primer orden positivo) en un perfil 1D.

    Parámetros:
    -----------
    f : np.ndarray
        Eje de frecuencias espaciales [nm^-1].
    profile : np.ndarray
        Densidad espectral 1D integrada.
    a_nominal : float
        Período nominal esperado [nm].
    search_half_width_factor : float
        Fracción de 1/a_nominal para acotar la ventana de búsqueda del pico.
    dc_cut_factor : float
        Corte inferior para ignorar la componente continua DC.
    f_min, f_max : float, opcional
        Cotas explícitas de ROI visual. Si se definen, invalidan los factores automáticos.
    fixed_bg : float, opcional
        Valor fijo para la línea base de fondo.

    Retorna:
    --------
    Diccionario con parámetros ajustados: f0, a, height, fwhm, xi, bg, fit_curve, success.
    """
    f0_target = 1.0 / a_nominal
    if f_min is not None and f_max is not None:
        f_min_search = min(float(f_min), float(f_max))
        f_max_search = max(float(f_min), float(f_max))
        f_dc_cut = f_min_search
    else:
        f_min_search = f0_target * (1.0 - search_half_width_factor)
        f_max_search = f0_target * (1.0 + search_half_width_factor)
        f_dc_cut = f0_target * dc_cut_factor

    # Máscara de frecuencias positivas en la región de interés
    mask = (f >= max(f_dc_cut, f_min_search)) & (f <= f_max_search)
    f_roi = f[mask]
    p_roi = profile[mask]

    if len(f_roi) < 5:
        return {
            'success': False,
            'f0': f0_target,
            'a': a_nominal,
            'height': 0.0,
            'fwhm': 0.0,
            'sigma_f': 0.0,
            'xi': 0.0,
            'bg': 0.0,
            'fit_f': f_roi,
            'fit_curve': np.zeros_like(f_roi)
        }

    # Búsqueda del máximo inicial
    idx_max = np.argmax(p_roi)
    f0_init = f_roi[idx_max]
    H_init = p_roi[idx_max] - float(np.min(p_roi))
    bg_init = float(fixed_bg) if fixed_bg is not None else float(np.min(p_roi))
    sigma_f_init = f0_target * 0.10

    # Ajuste por mínimos cuadrados no lineales
    p0 = [max(H_init, 1e-3), f0_init, sigma_f_init, bg_init, 0.0]
    if fixed_bg is not None:
        bg_low = float(fixed_bg) - 1e-6
        bg_high = float(fixed_bg) + 1e-6
    else:
        bg_low = 0.0
        bg_high = np.inf

    bounds = (
        [0.0, f_min_search, 1e-6, bg_low, -np.inf],
        [np.inf, f_max_search, f0_target * 2.0, bg_high, np.inf]
    )

    try:
        popt, pcov = curve_fit(_gaussian_with_bg, f_roi, p_roi, p0=p0, bounds=bounds, maxfev=2000)
        H_fit, f0_fit, sigma_f_fit, bg_fit, slope_fit = popt
        success = True
    except Exception:
        # Respaldo por estimación de centroide si el ajuste no lineal falla
        H_fit = H_init
        f0_fit = f0_init
        sigma_f_fit = sigma_f_init
        bg_fit = bg_init
        slope_fit = 0.0
        success = False

    a_fit = 1.0 / abs(f0_fit) if f0_fit > 1e-9 else a_nominal
    fwhm = 2.35482 * abs(sigma_f_fit)
    xi = 1.0 / (2.0 * np.pi * fwhm) if fwhm > 1e-9 else 0.0

    fit_curve = _gaussian_with_bg(f_roi, H_fit, f0_fit, sigma_f_fit, bg_fit, slope_fit)

    return {
        'success': success,
        'f0': float(f0_fit),
        'a': float(a_fit),
        'height': float(H_fit),
        'fwhm': float(fwhm),
        'sigma_f': float(sigma_f_fit),
        'xi': float(xi),
        'bg': float(bg_fit),
        'fit_f': f_roi,
        'fit_curve': fit_curve
    }


def _double_gaussian_with_bg(f, H1, f1, s1, H2, f2, s2, bg, slope):
    """Modelo de doble gaussiana con fondo lineal para picos desdoblados / doublets."""
    return (H1 * np.exp(-((f - f1) ** 2) / (2.0 * s1 ** 2)) +
            H2 * np.exp(-((f - f2) ** 2) / (2.0 * s2 ** 2)) +
            bg + slope * (f - f1))


def fit_bragg_peak_double_gaussian(
    f: np.ndarray,
    profile: np.ndarray,
    a_nominal: float = 450.0,
    search_half_width_factor: float = 0.40,
    dc_cut_factor: float = 0.40,
    peak_selection_mode: str = 'highest',
    f_min: Optional[float] = None,
    f_max: Optional[float] = None,
    fixed_bg: Optional[float] = None
) -> Dict[str, Any]:
    """
    Ajusta un modelo de Doble Gaussiana sobre el perfil 1D para resolver picos
    desdoblados (doublets), hombros o satélites cristalográficos.

    Parámetros:
    -----------
    f : np.ndarray
        Frecuencias espaciales [nm^-1].
    profile : np.ndarray
        Densidad espectral 1D.
    a_nominal : float
        Período nominal esperado [nm].
    search_half_width_factor : float
        Fracción de 1/a_nominal para acotar la ventana de búsqueda.
    dc_cut_factor : float
        Corte inferior para ignorar la componente continua DC.
    peak_selection_mode : str
        'highest': elige como pico primario el de mayor amplitud.
        'closest_nominal': elige como primario el más cercano a 1/a_nominal.
    f_min, f_max : float, opcional
        Límites explícitos de ROI visuales en nm^-1.
    fixed_bg : float, opcional
        Línea base fija para el ajuste.

    Retorna:
    --------
    Diccionario con parámetros del pico primario y del secundario, curvas de ajuste y éxito.
    """
    f0_target = 1.0 / a_nominal
    if f_min is not None and f_max is not None:
        f_min_search = min(float(f_min), float(f_max))
        f_max_search = max(float(f_min), float(f_max))
        f_dc_cut = f_min_search
    else:
        f_min_search = f0_target * (1.0 - search_half_width_factor)
        f_max_search = f0_target * (1.0 + search_half_width_factor)
        f_dc_cut = f0_target * dc_cut_factor

    mask = (f >= max(f_dc_cut, f_min_search)) & (f <= f_max_search)
    f_roi = f[mask]
    p_roi = profile[mask]

    if len(f_roi) < 8:
        res_simple = fit_bragg_peak_1d(
            f, profile, a_nominal, search_half_width_factor, dc_cut_factor,
            f_min=f_min, f_max=f_max, fixed_bg=fixed_bg
        )
        res_simple['is_double_peak'] = False
        res_simple['secondary_peak'] = None
        res_simple['comp1_curve'] = None
        res_simple['comp2_curve'] = None
        res_simple['baseline_curve'] = None
        return res_simple

    peaks_indices, _ = find_peaks(p_roi, distance=max(2, len(f_roi) // 10))
    if len(peaks_indices) >= 2:
        top_two = sorted(peaks_indices, key=lambda idx: p_roi[idx], reverse=True)[:2]
        top_two.sort()
        f1_init, f2_init = f_roi[top_two[0]], f_roi[top_two[1]]
        H1_init, H2_init = p_roi[top_two[0]] - float(np.min(p_roi)), p_roi[top_two[1]] - float(np.min(p_roi))
    else:
        idx_max = np.argmax(p_roi)
        f1_init = f_roi[idx_max]
        H1_init = p_roi[idx_max] - float(np.min(p_roi))
        delta_f = f0_target * 0.08
        f2_init = f1_init + delta_f if (f1_init + delta_f < f_max_search) else (f1_init - delta_f)
        H2_init = H1_init * 0.4

    bg_init = float(fixed_bg) if fixed_bg is not None else float(np.min(p_roi))
    s1_init = f0_target * 0.08
    s2_init = f0_target * 0.08

    p0 = [max(H1_init, 1e-3), f1_init, s1_init, max(H2_init, 1e-3), f2_init, s2_init, bg_init, 0.0]

    if fixed_bg is not None:
        bg_low = float(fixed_bg) - 1e-6
        bg_high = float(fixed_bg) + 1e-6
    else:
        bg_low = 0.0
        bg_high = np.inf

    bounds = (
        [0.0, f_min_search, 1e-6, 0.0, f_min_search, 1e-6, bg_low, -np.inf],
        [np.inf, f_max_search, f0_target * 2.0, np.inf, f_max_search, f0_target * 2.0, bg_high, np.inf]
    )

    try:
        popt, _ = curve_fit(_double_gaussian_with_bg, f_roi, p_roi, p0=p0, bounds=bounds, maxfev=3000)
        H1_f, f1_f, s1_f, H2_f, f2_f, s2_f, bg_f, slope_f = popt
        success = True
    except Exception:
        simple_res = fit_bragg_peak_1d(
            f, profile, a_nominal, search_half_width_factor, dc_cut_factor,
            f_min=f_min, f_max=f_max, fixed_bg=fixed_bg
        )
        simple_res['is_double_peak'] = False
        simple_res['secondary_peak'] = None
        simple_res['comp1_curve'] = None
        simple_res['comp2_curve'] = None
        simple_res['baseline_curve'] = None
        return simple_res

    if peak_selection_mode == 'closest_nominal':
        if abs(f1_f - f0_target) <= abs(f2_f - f0_target):
            primary = (H1_f, f1_f, s1_f)
            secondary = (H2_f, f2_f, s2_f)
        else:
            primary = (H2_f, f2_f, s2_f)
            secondary = (H1_f, f1_f, s1_f)
    else:  # 'highest'
        if H1_f >= H2_f:
            primary = (H1_f, f1_f, s1_f)
            secondary = (H2_f, f2_f, s2_f)
        else:
            primary = (H2_f, f2_f, s2_f)
            secondary = (H1_f, f1_f, s1_f)

    H_pri, f0_pri, s_pri = primary
    H_sec, f0_sec, s_sec = secondary

    a_pri = 1.0 / abs(f0_pri) if f0_pri > 1e-9 else a_nominal
    a_sec = 1.0 / abs(f0_sec) if f0_sec > 1e-9 else a_nominal
    fwhm_pri = 2.35482 * abs(s_pri)
    fwhm_sec = 2.35482 * abs(s_sec)
    xi_pri = 1.0 / (2.0 * np.pi * fwhm_pri) if fwhm_pri > 1e-9 else 0.0

    fit_curve = _double_gaussian_with_bg(f_roi, H1_f, f1_f, s1_f, H2_f, f2_f, s2_f, bg_f, slope_f)
    comp1_curve = _gaussian_with_bg(f_roi, H1_f, f1_f, s1_f, bg_f, slope_f)
    comp2_curve = _gaussian_with_bg(f_roi, H2_f, f2_f, s2_f, bg_f, slope_f)
    baseline_curve = bg_f + slope_f * (f_roi - f0_target)

    return {
        'success': success,
        'is_double_peak': True,
        'peak_selection_mode': peak_selection_mode,
        'f0': float(f0_pri),
        'a': float(a_pri),
        'height': float(H_pri),
        'fwhm': float(fwhm_pri),
        'sigma_f': float(s_pri),
        'xi': float(xi_pri),
        'bg': float(bg_f),
        'fit_f': f_roi,
        'fit_curve': fit_curve,
        'comp1_curve': comp1_curve,
        'comp2_curve': comp2_curve,
        'baseline_curve': baseline_curve,
        'secondary_peak': {
            'f0': float(f0_sec),
            'a': float(a_sec),
            'height': float(H_sec),
            'fwhm': float(fwhm_sec),
            'sigma_f': float(s_sec),
            'xi': float(1.0 / (2.0 * np.pi * fwhm_sec) if fwhm_sec > 1e-9 else 0.0)
        }
    }


def extract_diagonal_profile(
    S: np.ndarray,
    fx: np.ndarray,
    fy: np.ndarray,
    band_width_bins: int = 2
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Extrae el perfil unidimensional a lo largo de la diagonal principal (45°: fx = fy)
    promediando una banda transversal de ancho `band_width_bins` perpendicular a la diagonal.

    El eje de frecuencia radial diagonal es f_diag = sqrt(2) * fx_pos para fx >= 0.
    """
    n_bins_y, n_bins_x = S.shape
    iy_zero = np.argmin(np.abs(fy))
    ix_zero = np.argmin(np.abs(fx))

    # Muestreo en el cuadrante positivo a 45 grados: (iy_zero + m, ix_zero + m)
    max_m = min(n_bins_y - 1 - iy_zero, n_bins_x - 1 - ix_zero)
    m_vals = np.arange(0, max_m + 1)

    f_diag = fx[ix_zero + m_vals] * np.sqrt(2.0)
    profile_diag = np.zeros(len(m_vals), dtype=np.float64)

    for idx, m in enumerate(m_vals):
        r0 = iy_zero + m
        c0 = ix_zero + m
        vals = []
        for k in range(-band_width_bins, band_width_bins + 1):
            r = r0 - k
            c = c0 + k
            if 0 <= r < n_bins_y and 0 <= c < n_bins_x:
                vals.append(S[r, c])
        profile_diag[idx] = np.mean(vals) if vals else S[r0, c0]

    return f_diag, profile_diag


def fit_secondary_bragg_peak_1d(
    f: np.ndarray,
    profile: np.ndarray,
    target_f: float,
    expected_order: float = 1.0,
    search_half_width_factor: float = 0.25,
    f_min: Optional[float] = None,
    f_max: Optional[float] = None,
    fixed_bg: Optional[float] = None
) -> Dict[str, Any]:
    """
    Ajusta un pico de Bragg secundario (diagonal u orden armónico superior) en un perfil 1D.

    Parámetros:
    -----------
    f : np.ndarray
        Eje de frecuencias espaciales [nm^-1].
    profile : np.ndarray
        Perfil espectral 1D integrado.
    target_f : float
        Frecuencia central nominal esperada [nm^-1].
    expected_order : float
        Orden armónico esperado (ej. 2.0 para 2do orden, sqrt(2) para diagonal)
        utilizado para calcular el período fundamental equivalente a = expected_order / f0.
    search_half_width_factor : float
        Ventana relativa de búsqueda en torno a target_f.
    f_min, f_max : float, opcional
        Límites explícitos de frecuencia [nm^-1] provenientes de reglas visuales de ROI.
    fixed_bg : float, opcional
        Línea base constante fija para el ajuste.
    """
    if target_f <= 1e-9:
        return {
            'success': False,
            'f0': 0.0,
            'a': 0.0,
            'height': 0.0,
            'fwhm': 0.0,
            'sigma_f': 0.0,
            'xi': 0.0,
            'bg': 0.0,
            'fit_f': np.array([]),
            'fit_curve': np.array([])
        }

    if f_min is not None and f_max is not None:
        f_min_search = min(float(f_min), float(f_max))
        f_max_search = max(float(f_min), float(f_max))
    else:
        f_min_search = target_f * (1.0 - search_half_width_factor)
        f_max_search = target_f * (1.0 + search_half_width_factor)

    mask = (f >= f_min_search) & (f <= f_max_search)
    f_roi = f[mask]
    p_roi = profile[mask]

    if len(f_roi) < 5:
        return {
            'success': False,
            'f0': float(target_f),
            'a': float(expected_order / target_f),
            'height': 0.0,
            'fwhm': 0.0,
            'sigma_f': 0.0,
            'xi': 0.0,
            'bg': 0.0,
            'fit_f': f_roi,
            'fit_curve': np.zeros_like(f_roi)
        }

    idx_max = np.argmax(p_roi)
    f0_init = f_roi[idx_max]
    bg_init = float(fixed_bg) if fixed_bg is not None else float(np.min(p_roi))
    H_init = p_roi[idx_max] - bg_init
    sigma_f_init = target_f * 0.08

    p0 = [max(H_init, 1e-3), f0_init, sigma_f_init, bg_init, 0.0]

    if fixed_bg is not None:
        bg_low = float(fixed_bg) - 1e-6
        bg_high = float(fixed_bg) + 1e-6
    else:
        bg_low = 0.0
        bg_high = np.inf

    bounds = (
        [0.0, f_min_search, 1e-6, bg_low, -np.inf],
        [np.inf, f_max_search, target_f, bg_high, np.inf]
    )

    try:
        popt, _ = curve_fit(_gaussian_with_bg, f_roi, p_roi, p0=p0, bounds=bounds, maxfev=2000)
        H_fit, f0_fit, sigma_f_fit, bg_fit, slope_fit = popt
        success = True
    except Exception:
        H_fit = H_init
        f0_fit = f0_init
        sigma_f_fit = sigma_f_init
        bg_fit = bg_init
        slope_fit = 0.0
        success = False

    a_fit = float(expected_order / abs(f0_fit)) if f0_fit > 1e-9 else 0.0
    fwhm = 2.35482 * abs(sigma_f_fit)
    xi = 1.0 / (2.0 * np.pi * fwhm) if fwhm > 1e-9 else 0.0
    fit_curve = _gaussian_with_bg(f_roi, H_fit, f0_fit, sigma_f_fit, bg_fit, slope_fit)

    return {
        'success': success,
        'f0': float(f0_fit),
        'a': float(a_fit),
        'height': float(H_fit),
        'fwhm': float(fwhm),
        'sigma_f': float(sigma_f_fit),
        'xi': float(xi),
        'bg': float(bg_fit),
        'fit_f': f_roi,
        'fit_curve': fit_curve
    }


def fit_secondary_bragg_peak_double_gaussian(
    f: np.ndarray,
    profile: np.ndarray,
    target_f: float,
    expected_order: float = 1.0,
    search_half_width_factor: float = 0.25,
    peak_selection_mode: str = 'highest',
    f_min: Optional[float] = None,
    f_max: Optional[float] = None,
    fixed_bg: Optional[float] = None
) -> Dict[str, Any]:
    """
    Ajusta un modelo de Doble Gaussiana con fondo lineal sobre un pico secundario
    (orden armónico superior [2,0], [0,2] o diagonal [1,1]) para resolver doublets o satélites.
    """
    if target_f <= 1e-9:
        return {
            'success': False,
            'is_double_peak': False,
            'f0': 0.0,
            'a': 0.0,
            'height': 0.0,
            'fwhm': 0.0,
            'sigma_f': 0.0,
            'xi': 0.0,
            'bg': 0.0,
            'fit_f': np.array([]),
            'fit_curve': np.array([]),
            'comp1_curve': None,
            'comp2_curve': None,
            'baseline_curve': None,
            'secondary_peak': None
        }

    if f_min is not None and f_max is not None:
        f_min_search = min(float(f_min), float(f_max))
        f_max_search = max(float(f_min), float(f_max))
    else:
        f_min_search = target_f * (1.0 - search_half_width_factor)
        f_max_search = target_f * (1.0 + search_half_width_factor)

    mask = (f >= f_min_search) & (f <= f_max_search)
    f_roi = f[mask]
    p_roi = profile[mask]

    if len(f_roi) < 8:
        res_simple = fit_secondary_bragg_peak_1d(
            f, profile, target_f, expected_order, search_half_width_factor,
            f_min=f_min, f_max=f_max, fixed_bg=fixed_bg
        )
        res_simple['is_double_peak'] = False
        res_simple['secondary_peak'] = None
        res_simple['comp1_curve'] = None
        res_simple['comp2_curve'] = None
        res_simple['baseline_curve'] = None
        return res_simple

    peaks_indices, _ = find_peaks(p_roi, distance=max(2, len(f_roi) // 10))
    if len(peaks_indices) >= 2:
        top_two = sorted(peaks_indices, key=lambda idx: p_roi[idx], reverse=True)[:2]
        top_two.sort()
        f1_init, f2_init = f_roi[top_two[0]], f_roi[top_two[1]]
        H1_init = p_roi[top_two[0]] - float(np.min(p_roi))
        H2_init = p_roi[top_two[1]] - float(np.min(p_roi))
    else:
        idx_max = np.argmax(p_roi)
        f1_init = f_roi[idx_max]
        H1_init = p_roi[idx_max] - float(np.min(p_roi))
        delta_f = target_f * 0.08
        f2_init = f1_init + delta_f if (f1_init + delta_f < f_max_search) else (f1_init - delta_f)
        H2_init = H1_init * 0.4

    bg_init = float(fixed_bg) if fixed_bg is not None else float(np.min(p_roi))
    s1_init = target_f * 0.08
    s2_init = target_f * 0.08

    p0 = [max(H1_init, 1e-3), f1_init, s1_init, max(H2_init, 1e-3), f2_init, s2_init, bg_init, 0.0]

    if fixed_bg is not None:
        bg_low = float(fixed_bg) - 1e-6
        bg_high = float(fixed_bg) + 1e-6
    else:
        bg_low = 0.0
        bg_high = np.inf

    bounds = (
        [0.0, f_min_search, 1e-6, 0.0, f_min_search, 1e-6, bg_low, -np.inf],
        [np.inf, f_max_search, target_f * 2.0, np.inf, f_max_search, target_f * 2.0, bg_high, np.inf]
    )

    try:
        popt, _ = curve_fit(_double_gaussian_with_bg, f_roi, p_roi, p0=p0, bounds=bounds, maxfev=3000)
        H1_f, f1_f, s1_f, H2_f, f2_f, s2_f, bg_f, slope_f = popt
        success = True
    except Exception:
        simple_res = fit_secondary_bragg_peak_1d(
            f, profile, target_f, expected_order, search_half_width_factor,
            f_min=f_min, f_max=f_max, fixed_bg=fixed_bg
        )
        simple_res['is_double_peak'] = False
        simple_res['secondary_peak'] = None
        simple_res['comp1_curve'] = None
        simple_res['comp2_curve'] = None
        simple_res['baseline_curve'] = None
        return simple_res

    if peak_selection_mode == 'closest_nominal':
        if abs(f1_f - target_f) <= abs(f2_f - target_f):
            primary = (H1_f, f1_f, s1_f)
            secondary = (H2_f, f2_f, s2_f)
        else:
            primary = (H2_f, f2_f, s2_f)
            secondary = (H1_f, f1_f, s1_f)
    else:  # 'highest'
        if H1_f >= H2_f:
            primary = (H1_f, f1_f, s1_f)
            secondary = (H2_f, f2_f, s2_f)
        else:
            primary = (H2_f, f2_f, s2_f)
            secondary = (H1_f, f1_f, s1_f)

    H_pri, f0_pri, s_pri = primary
    H_sec, f0_sec, s_sec = secondary

    a_pri = float(expected_order / abs(f0_pri)) if f0_pri > 1e-9 else 0.0
    a_sec = float(expected_order / abs(f0_sec)) if f0_sec > 1e-9 else 0.0
    fwhm_pri = 2.35482 * abs(s_pri)
    fwhm_sec = 2.35482 * abs(s_sec)
    xi_pri = 1.0 / (2.0 * np.pi * fwhm_pri) if fwhm_pri > 1e-9 else 0.0

    fit_curve = _double_gaussian_with_bg(f_roi, H1_f, f1_f, s1_f, H2_f, f2_f, s2_f, bg_f, slope_f)
    comp1_curve = _gaussian_with_bg(f_roi, H1_f, f1_f, s1_f, bg_f, slope_f)
    comp2_curve = _gaussian_with_bg(f_roi, H2_f, f2_f, s2_f, bg_f, slope_f)
    baseline_curve = bg_f + slope_f * (f_roi - target_f)

    return {
        'success': success,
        'is_double_peak': True,
        'peak_selection_mode': peak_selection_mode,
        'f0': float(f0_pri),
        'a': float(a_pri),
        'height': float(H_pri),
        'fwhm': float(fwhm_pri),
        'sigma_f': float(s_pri),
        'xi': float(xi_pri),
        'bg': float(bg_f),
        'fit_f': f_roi,
        'fit_curve': fit_curve,
        'comp1_curve': comp1_curve,
        'comp2_curve': comp2_curve,
        'baseline_curve': baseline_curve,
        'secondary_peak': {
            'f0': float(f0_sec),
            'a': float(a_sec),
            'height': float(H_sec),
            'fwhm': float(fwhm_sec),
            'sigma_f': float(s_sec),
            'xi': float(1.0 / (2.0 * np.pi * fwhm_sec) if fwhm_sec > 1e-9 else 0.0)
        }
    }


def measure_transversal_mosaic(
    S: np.ndarray,
    fx: np.ndarray,
    fy: np.ndarray,
    peak_f0: float,
    axis: str = 'x',
    half_window_factor: float = 0.35
) -> Dict[str, Any]:
    """
    Mide el corte transversal perpendicular al vector del pico de Bragg principal (1, 0) o (0, 1)
    para determinar el ancho transversal FWHM (Delta q_perp) y el ángulo de mosaico / curvatura:
        Delta theta [rad] = Delta q_perp / |G|
        Delta theta [deg] = Delta theta [rad] * (180 / pi)
    """
    if peak_f0 <= 1e-9:
        return {'success': False, 'fwhm_perp': 0.0, 'delta_theta_deg': 0.0, 'fit_f': np.array([]), 'profile': np.array([])}

    if axis == 'x':
        ix = np.argmin(np.abs(fx - peak_f0))
        c_min = max(0, ix - 1)
        c_max = min(S.shape[1], ix + 2)
        prof_trans = np.mean(S[:, c_min:c_max], axis=1)
        f_axis = fy
    else:
        iy = np.argmin(np.abs(fy - peak_f0))
        r_min = max(0, iy - 1)
        r_max = min(S.shape[0], iy + 2)
        prof_trans = np.mean(S[r_min:r_max, :], axis=0)
        f_axis = fx

    mask = np.abs(f_axis) <= (peak_f0 * half_window_factor)
    f_roi = f_axis[mask]
    p_roi = prof_trans[mask]

    if len(f_roi) < 5:
        return {'success': False, 'fwhm_perp': 0.0, 'delta_theta_deg': 0.0, 'fit_f': f_roi, 'profile': p_roi}

    H_init = np.max(p_roi) - np.min(p_roi)
    bg_init = float(np.min(p_roi))
    sigma_init = peak_f0 * 0.05

    p0 = [max(H_init, 1e-3), 0.0, sigma_init, bg_init, 0.0]
    bounds = (
        [0.0, -peak_f0 * 0.2, 1e-6, 0.0, -np.inf],
        [np.inf, peak_f0 * 0.2, peak_f0, np.inf, np.inf]
    )

    try:
        popt, _ = curve_fit(_gaussian_with_bg, f_roi, p_roi, p0=p0, bounds=bounds, maxfev=1500)
        H_fit, f0_fit, sigma_fit, bg_fit, slope_fit = popt
        fwhm_perp = 2.35482 * abs(sigma_fit)
        delta_theta_rad = fwhm_perp / peak_f0
        delta_theta_deg = float(np.degrees(delta_theta_rad))
        success = True
    except Exception:
        half_val = bg_init + H_init * 0.5
        above = f_roi[p_roi >= half_val]
        fwhm_perp = float(above[-1] - above[0]) if len(above) > 1 else 0.0
        delta_theta_deg = float(np.degrees(fwhm_perp / peak_f0)) if peak_f0 > 0 else 0.0
        success = False

    return {
        'success': success,
        'fwhm_perp': float(fwhm_perp),
        'delta_theta_deg': float(delta_theta_deg),
        'fit_f': f_roi,
        'profile': p_roi
    }


def analyze_reciprocal_space_2d(
    x: np.ndarray,
    y: np.ndarray,
    a_nominal: float = 450.0,
    n_bins: int = 256,
    band_width_bins: int = 3,
    dc_cut_factor: float = 0.35,
    use_double_peak: bool = False,
    peak_selection_mode: str = 'highest',
    peak_tuning: Optional[Dict[str, Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Ejecuta el análisis espectral 2D metrológico completo:
    1. Cálculo de NUFFT 2D continua y factor de estructura S(fx, fy).
    2. Extracción de cortes transversales 1D y ajuste gaussiano de picos de Bragg fundamentales (1, 0) y (0, 1)
       con soporte para simple o doble gaussiana (resolución de doublets/splitting).
    3. Extracción de corte diagonal 45° y ajuste del pico de orden cruzado (1, 1).
    4. Ajuste de picos armónicos de segundo orden (2, 0) y (0, 2) con soporte de simple/doble gaussiana.
    5. Medición de anchos transversales y cuantificación del mosaico angular / curvatura de escaneo.
    6. Verificación de ortogonalidad cristalográfica y cizallamiento (shear strain).
    7. Cuantificación del fondo difuso incoherente y relación señal/fondo (SBR).
    """
    fx, fy, S = compute_structure_factor_2d(x, y, a_nominal=a_nominal, n_bins=n_bins)
    _, prof_x, _, prof_y = extract_1d_profiles(S, fx, fy, band_width_bins=band_width_bins)

    t_x1 = (peak_tuning or {}).get('x_1st', {})
    t_y1 = (peak_tuning or {}).get('y_1st', {})
    t_diag = (peak_tuning or {}).get('diag', {})
    t_x2 = (peak_tuning or {}).get('x_2nd', {})
    t_y2 = (peak_tuning or {}).get('y_2nd', {})

    # 1. Picos Fundamentales de 1er Orden
    m_x1 = t_x1.get('model', 'double' if use_double_peak else 'single')
    if m_x1 == 'double':
        fit_x = fit_bragg_peak_double_gaussian(
            fx, prof_x, a_nominal=a_nominal, dc_cut_factor=dc_cut_factor,
            peak_selection_mode=t_x1.get('peak_selection_mode', peak_selection_mode),
            f_min=t_x1.get('f_min'), f_max=t_x1.get('f_max'), fixed_bg=t_x1.get('fixed_bg')
        )
    else:
        fit_x = fit_bragg_peak_1d(
            fx, prof_x, a_nominal=a_nominal, dc_cut_factor=dc_cut_factor,
            f_min=t_x1.get('f_min'), f_max=t_x1.get('f_max'), fixed_bg=t_x1.get('fixed_bg')
        )

    m_y1 = t_y1.get('model', 'double' if use_double_peak else 'single')
    if m_y1 == 'double':
        fit_y = fit_bragg_peak_double_gaussian(
            fy, prof_y, a_nominal=a_nominal, dc_cut_factor=dc_cut_factor,
            peak_selection_mode=t_y1.get('peak_selection_mode', peak_selection_mode),
            f_min=t_y1.get('f_min'), f_max=t_y1.get('f_max'), fixed_bg=t_y1.get('fixed_bg')
        )
    else:
        fit_y = fit_bragg_peak_1d(
            fy, prof_y, a_nominal=a_nominal, dc_cut_factor=dc_cut_factor,
            f_min=t_y1.get('f_min'), f_max=t_y1.get('f_max'), fixed_bg=t_y1.get('fixed_bg')
        )

    a_x = fit_x['a']
    a_y = fit_y['a']
    a_mean = (a_x + a_y) / 2.0
    anisotropy = a_x - a_y

    # 2. Perfil Diagonal 45° y Pico de Orden Cruzado (1, 1)
    f_diag, prof_diag = extract_diagonal_profile(S, fx, fy, band_width_bins=max(1, band_width_bins - 1))
    f10_val = fit_x['f0'] if fit_x['f0'] > 1e-9 else (1.0 / a_nominal)
    f01_val = fit_y['f0'] if fit_y['f0'] > 1e-9 else (1.0 / a_nominal)
    f_diag_target = float(np.sqrt(f10_val ** 2 + f01_val ** 2))

    m_diag = t_diag.get('model', 'double' if use_double_peak else 'single')
    if m_diag == 'double':
        fit_diag = fit_secondary_bragg_peak_double_gaussian(
            f_diag, prof_diag, target_f=f_diag_target, expected_order=np.sqrt(2.0),
            peak_selection_mode=t_diag.get('peak_selection_mode', peak_selection_mode),
            f_min=t_diag.get('f_min'), f_max=t_diag.get('f_max'), fixed_bg=t_diag.get('fixed_bg')
        )
    else:
        fit_diag = fit_secondary_bragg_peak_1d(
            f_diag, prof_diag, target_f=f_diag_target, expected_order=np.sqrt(2.0),
            f_min=t_diag.get('f_min'), f_max=t_diag.get('f_max'), fixed_bg=t_diag.get('fixed_bg')
        )

    # 3. Picos Armónicos de 2do Orden (2, 0) y (0, 2)
    m_x2 = t_x2.get('model', 'double' if use_double_peak else 'single')
    if m_x2 == 'double':
        fit_x_2nd = fit_secondary_bragg_peak_double_gaussian(
            fx, prof_x, target_f=2.0 * f10_val, expected_order=2.0,
            peak_selection_mode=t_x2.get('peak_selection_mode', peak_selection_mode),
            f_min=t_x2.get('f_min'), f_max=t_x2.get('f_max'), fixed_bg=t_x2.get('fixed_bg')
        )
    else:
        fit_x_2nd = fit_secondary_bragg_peak_1d(
            fx, prof_x, target_f=2.0 * f10_val, expected_order=2.0,
            f_min=t_x2.get('f_min'), f_max=t_x2.get('f_max'), fixed_bg=t_x2.get('fixed_bg')
        )

    m_y2 = t_y2.get('model', 'double' if use_double_peak else 'single')
    if m_y2 == 'double':
        fit_y_2nd = fit_secondary_bragg_peak_double_gaussian(
            fy, prof_y, target_f=2.0 * f01_val, expected_order=2.0,
            peak_selection_mode=t_y2.get('peak_selection_mode', peak_selection_mode),
            f_min=t_y2.get('f_min'), f_max=t_y2.get('f_max'), fixed_bg=t_y2.get('fixed_bg')
        )
    else:
        fit_y_2nd = fit_secondary_bragg_peak_1d(
            fy, prof_y, target_f=2.0 * f01_val, expected_order=2.0,
            f_min=t_y2.get('f_min'), f_max=t_y2.get('f_max'), fixed_bg=t_y2.get('fixed_bg')
        )

    # 4. Mosaico Angular Transversal
    mosaic_x = measure_transversal_mosaic(S, fx, fy, peak_f0=f10_val, axis='x')
    mosaic_y = measure_transversal_mosaic(S, fx, fy, peak_f0=f01_val, axis='y')

    # 5. Ángulo de Cizallamiento (Shear Strain)
    f11_meas = fit_diag['f0']
    if f10_val > 1e-9 and f01_val > 1e-9 and f11_meas > 1e-9:
        cos_gamma = np.clip((f11_meas ** 2 - f10_val ** 2 - f01_val ** 2) / (2.0 * f10_val * f01_val), -1.0, 1.0)
        shear_strain_deg = float(np.degrees(np.arcsin(cos_gamma)))
    else:
        shear_strain_deg = 0.0

    # 6. Fondo Difuso Incoherente y Relación Señal/Fondo (SBR)
    f0_ref = 1.0 / a_mean
    FX, FY = np.meshgrid(fx, fy)
    R = np.sqrt(FX ** 2 + FY ** 2)
    mask_diff = (R >= 0.40 * f0_ref) & (R <= 2.20 * f0_ref)
    I_diffuse = float(np.median(S[mask_diff])) if np.any(mask_diff) else 0.0
    sbr_x = float(fit_x['height'] / max(1e-9, I_diffuse))
    sbr_y = float(fit_y['height'] / max(1e-9, I_diffuse))
    sbr_mean = (sbr_x + sbr_y) / 2.0

    # Ratios de decaimiento Debye-Waller experimental y ratios paracristalinos
    H_mean_1 = (fit_x['height'] + fit_y['height']) / 2.0
    ratio_diag = float(fit_diag['height'] / max(1e-9, H_mean_1))
    ratio_order2_x = float(fit_x_2nd['height'] / max(1e-9, fit_x['height']))
    ratio_order2_y = float(fit_y_2nd['height'] / max(1e-9, fit_y['height']))
    paracrystal_ratio_x = float(fit_x_2nd['fwhm'] / max(1e-9, fit_x['fwhm']))
    paracrystal_ratio_y = float(fit_y_2nd['fwhm'] / max(1e-9, fit_y['fwhm']))

    res_dict = {
        # --- Campos Fundamentales 1er Orden (Retrocompatibilidad Estricta) ---
        'fx': fx,
        'fy': fy,
        'S': S,
        'profile_x': prof_x,
        'profile_y': prof_y,
        'fit_x': fit_x,
        'fit_y': fit_y,
        'a_x': a_x,
        'a_y': a_y,
        'a_mean': a_mean,
        'anisotropy': anisotropy,
        'Hx': fit_x['height'],
        'Hy': fit_y['height'],
        'H_mean': H_mean_1,
        'fwhm_x': fit_x['fwhm'],
        'fwhm_y': fit_y['fwhm'],
        'xi_x': fit_x['xi'],
        'xi_y': fit_y['xi'],

        # --- Jerarquía de Bragg Multi-Orden (Nuevo) ---
        'f_diag': f_diag,
        'profile_diag': prof_diag,
        'fit_diag': fit_diag,
        'a_diag': fit_diag['a'],
        'H_diag': fit_diag['height'],
        'ratio_diag': ratio_diag,
        'shear_strain_deg': shear_strain_deg,

        'fit_x_2nd': fit_x_2nd,
        'fit_y_2nd': fit_y_2nd,
        'a_x_2nd': fit_x_2nd['a'],
        'a_y_2nd': fit_y_2nd['a'],
        'H_x_2nd': fit_x_2nd['height'],
        'H_y_2nd': fit_y_2nd['height'],
        'ratio_order2_x': ratio_order2_x,
        'ratio_order2_y': ratio_order2_y,
        'paracrystal_ratio_x': paracrystal_ratio_x,
        'paracrystal_ratio_y': paracrystal_ratio_y,

        # --- Mosaico Angular y Fondo Difuso (Nuevo) ---
        'mosaic_x': mosaic_x,
        'mosaic_y': mosaic_y,
        'delta_theta_x_deg': mosaic_x['delta_theta_deg'],
        'delta_theta_y_deg': mosaic_y['delta_theta_deg'],
        'I_diffuse': I_diffuse,
        'sbr_x': sbr_x,
        'sbr_y': sbr_y,
        'sbr_mean': sbr_mean,
        'use_double_peak': use_double_peak,
        'peak_selection_mode': peak_selection_mode
    }

    # Cálculo y deducción de relaciones analíticas directas entre picos
    res_dict['analytical_relations'] = compute_analytical_bragg_relations(
        res_dict,
        a_nominal=a_nominal,
        n_total_particles=len(x)
    )

    return res_dict


def compute_analytical_bragg_relations(
    res_dict: Dict[str, Any],
    a_nominal: float = 450.0,
    n_total_particles: Optional[int] = None,
    anchor_wilson_to_h0: bool = False
) -> Dict[str, Any]:
    """
    Deduce las relaciones analíticas directas entre los picos de Bragg de Fourier
    (sin curvas de calibración Monte Carlo previas):

    1. Inversión analítica de sigma mediante el segundo armónico H2 / H1:
       sigma = (a / (2*pi*sqrt(3))) * sqrt(ln(H1 / H2))
       (Estándar de Oro analítico: cancela idénticamente el número de partículas N
        y la fracción de vacancias p).
    2. Inversión mediante el pico diagonal (1, 1) H_diag / H1:
       sigma = (a / (2*pi)) * sqrt(ln(H1 / H_diag))
       (Verificación cruzada de coherencia 2D).
    3. Razón frente al pico central H1 / H0:
       sigma = (a / (2*pi)) * sqrt(ln(H0 / H1))
       (Marcado explícitamente como inestable debido a iluminación parásita de fondo).
    4. Gráfico de Wilson (Wilson Plot):
       Regresión lineal ln(H) vs |G|^2 sobre los órdenes de Bragg observados.
       Si anchor_wilson_to_h0 es True, se ancla c_x = c_y = ln(H_0) en el origen.
       Pendiente m = -sigma^2  ==>  sigma_wilson = sqrt(-m).
       Ordenada c = ln((1-p)^2 * H0) ==> estimación analítica de vacancias p_est.
    5. Diagnóstico de Tipo de Desorden (Scherrer Tipo I vs Hosemann Paracristal Tipo II):
       Evaluación del ratio de anchos radiales FWHM_2 / FWHM_1.
    """
    a_x = float(res_dict.get('a_x', a_nominal))
    a_y = float(res_dict.get('a_y', a_nominal))
    a_mean = float(res_dict.get('a_mean', a_nominal))

    H1_x = float(res_dict.get('Hx', 0.0))
    H1_y = float(res_dict.get('Hy', 0.0))
    H1_mean = float(res_dict.get('H_mean', (H1_x + H1_y) / 2.0))

    H_diag = float(res_dict.get('H_diag', 0.0))
    H2_x = float(res_dict.get('H_x_2nd', 0.0))
    H2_y = float(res_dict.get('H_y_2nd', 0.0))
    H2_mean = (H2_x + H2_y) / 2.0

    # Extraer el pico central DC (H0)
    S = res_dict.get('S')
    fx = res_dict.get('fx')
    fy = res_dict.get('fy')
    if S is not None and fx is not None and fy is not None:
        FX, FY = np.meshgrid(fx, fy)
        R = np.sqrt(FX ** 2 + FY ** 2)
        f0_ref = 1.0 / max(1e-9, a_mean)
        mask_dc = R < 0.20 * f0_ref
        H0 = float(np.max(S[mask_dc])) if np.any(mask_dc) else float(S[len(fy) // 2, len(fx) // 2])
    else:
        H0 = float(res_dict.get('H0', 0.0))

    # Medición de amplitudes de spots 2D en S(fx, fy) para consistencia global
    G1_x = 2.0 * np.pi / max(1e-9, a_x)
    G1_y = 2.0 * np.pi / max(1e-9, a_y)
    G1_mean = 2.0 * np.pi / max(1e-9, a_mean)
    G_diag = np.sqrt(G1_x ** 2 + G1_y ** 2)
    G2_x = 4.0 * np.pi / max(1e-9, a_x)
    G2_y = 4.0 * np.pi / max(1e-9, a_y)

    if S is not None and fx is not None and fy is not None:
        f0_mean = 1.0 / max(1e-9, a_mean)
        def _get_peak_2d(tfx: float, tfy: float, rad_f: float = 0.18) -> float:
            dist = np.sqrt((FX - tfx) ** 2 + (FY - tfy) ** 2)
            m = dist < rad_f * f0_mean
            return float(np.max(S[m])) if np.any(m) else 1e-6

        s_00 = _get_peak_2d(0.0, 0.0, rad_f=0.25)
        s_10 = _get_peak_2d(1.0 / a_x, 0.0)
        s_01 = _get_peak_2d(0.0, 1.0 / a_y)
        s_11 = _get_peak_2d(1.0 / a_x, 1.0 / a_y)
        s_20 = _get_peak_2d(2.0 / a_x, 0.0)
        s_02 = _get_peak_2d(0.0, 2.0 / a_y)
    else:
        s_00 = H0
        s_10 = H1_x
        s_01 = H1_y
        s_11 = H_diag
        s_20 = H2_x
        s_02 = H2_y

    s_1_mean = (s_10 + s_01) / 2.0

    # 1. Inversión analítica H2 / H1 (Estándar de Oro)
    ratio_21_x = float(H2_x / max(1e-9, H1_x))
    ratio_21_y = float(H2_y / max(1e-9, H1_y))
    ratio_21_mean = float(H2_mean / max(1e-9, H1_mean))

    factor_h2h1_x = a_x / (2.0 * np.pi * np.sqrt(3.0))
    factor_h2h1_y = a_y / (2.0 * np.pi * np.sqrt(3.0))
    factor_h2h1_mean = a_mean / (2.0 * np.pi * np.sqrt(3.0))

    sigma_h2h1_x = float(factor_h2h1_x * np.sqrt(max(0.0, np.log(max(1e-12, 1.0 / max(1e-12, ratio_21_x)))))) if ratio_21_x < 1.0 else 0.0
    sigma_h2h1_y = float(factor_h2h1_y * np.sqrt(max(0.0, np.log(max(1e-12, 1.0 / max(1e-12, ratio_21_y)))))) if ratio_21_y < 1.0 else 0.0
    sigma_h2h1 = float(factor_h2h1_mean * np.sqrt(max(0.0, np.log(max(1e-12, 1.0 / max(1e-12, ratio_21_mean)))))) if ratio_21_mean < 1.0 else 0.0

    # 2. Inversión analítica H_diag / H1 (Coherencia 2D y Desglose por Eje X e Y)
    ratio_diag_x = float(s_11 / max(1e-9, s_10 if s_10 > 0 else H1_x))
    ratio_diag_y = float(s_11 / max(1e-9, s_01 if s_01 > 0 else H1_y))
    ratio_diag_2d = float(s_11 / max(1e-9, s_1_mean))

    factor_diag_x = a_x / (2.0 * np.pi)
    factor_diag_y = a_y / (2.0 * np.pi)
    factor_diag_mean = a_mean / (2.0 * np.pi)

    sigma_diag_x = float(factor_diag_x * np.sqrt(max(0.0, np.log(max(1e-12, 1.0 / max(1e-12, ratio_diag_x)))))) if ratio_diag_x < 1.0 else 0.0
    sigma_diag_y = float(factor_diag_y * np.sqrt(max(0.0, np.log(max(1e-12, 1.0 / max(1e-12, ratio_diag_y)))))) if ratio_diag_y < 1.0 else 0.0
    sigma_diag = float(factor_diag_mean * np.sqrt(max(0.0, np.log(max(1e-12, 1.0 / max(1e-12, ratio_diag_2d)))))) if ratio_diag_2d < 1.0 else 0.0

    # 3. Inversión frente al Pico Central DC H0 / H1 y H1 / H0 (Inestable)
    ratio_0_1x = float(H0 / max(1e-9, s_10 if s_10 > 0 else H1_x))
    ratio_0_1y = float(H0 / max(1e-9, s_01 if s_01 > 0 else H1_y))
    ratio_0_1mean = float(H0 / max(1e-9, H1_mean))

    ratio_10_x = float((s_10 if s_10 > 0 else H1_x) / max(1e-9, H0))
    ratio_10_y = float((s_01 if s_01 > 0 else H1_y) / max(1e-9, H0))
    ratio_10 = float(H1_mean / max(1e-9, H0))

    sigma_h1h0_x = float(factor_diag_x * np.sqrt(max(0.0, np.log(max(1e-12, ratio_0_1x))))) if ratio_0_1x > 1.0 else 0.0
    sigma_h1h0_y = float(factor_diag_y * np.sqrt(max(0.0, np.log(max(1e-12, ratio_0_1y))))) if ratio_0_1y > 1.0 else 0.0
    sigma_h1h0 = float(factor_diag_mean * np.sqrt(max(0.0, np.log(max(1e-12, ratio_0_1mean))))) if ratio_0_1mean > 1.0 else 0.0

    # 4. Gráfico de Wilson (Wilson Plot) - Global y Desglosado Anisótropo X / Y
    wilson_points = [
        {"name": "(1, 0) X", "G_sq": float(G1_x ** 2), "H": max(1e-6, s_10)},
        {"name": "(0, 1) Y", "G_sq": float(G1_y ** 2), "H": max(1e-6, s_01)},
        {"name": "(1, 1) Diag", "G_sq": float(G_diag ** 2), "H": max(1e-6, s_11)},
        {"name": "(2, 0) 2X", "G_sq": float(G2_x ** 2), "H": max(1e-6, s_20)},
        {"name": "(0, 2) 2Y", "G_sq": float(G2_y ** 2), "H": max(1e-6, s_02)},
    ]

    g_sq_arr = np.array([p["G_sq"] for p in wilson_points], dtype=np.float64)
    ln_h_arr = np.array([np.log(p["H"]) for p in wilson_points], dtype=np.float64)

    # Comprobar si el usuario solicita anclar el intercepto al pico central ln(H0)
    c_h0 = float(np.log(max(1e-6, H0 if H0 > 0 else s_00)))
    can_anchor = anchor_wilson_to_h0 and (H0 > 0 or s_00 > 0)

    # 4a. Ajuste Global / Multiorigen (Retrocompatibilidad)
    if can_anchor:
        sum_u_y = float(np.sum(g_sq_arr * (ln_h_arr - c_h0)))
        sum_u_sq = float(np.sum(g_sq_arr ** 2))
        slope_w = float(sum_u_y / max(1e-12, sum_u_sq))
        intercept_w = c_h0

        fit_vals = slope_w * g_sq_arr + intercept_w
        ss_tot = float(np.sum((ln_h_arr - np.mean(ln_h_arr)) ** 2))
        ss_res = float(np.sum((ln_h_arr - fit_vals) ** 2))
        r_squared_w = float(max(0.0, 1.0 - (ss_res / max(1e-12, ss_tot)))) if ss_tot > 1e-12 else 1.0
        sigma_wilson = float(np.sqrt(max(0.0, -slope_w)))

        n_ref = float(n_total_particles) if n_total_particles is not None else max(1.0, s_00)
        exp_c = np.exp(intercept_w)
        ratio_occ_sq = min(1.0, max(0.0, exp_c / max(1e-9, n_ref)))
        p_wilson_est = float(1.0 - np.sqrt(ratio_occ_sq))
    elif len(g_sq_arr) >= 3 and np.ptp(g_sq_arr) > 1e-12:
        poly = np.polyfit(g_sq_arr, ln_h_arr, 1)
        slope_w = float(poly[0])
        intercept_w = float(poly[1])

        fit_vals = slope_w * g_sq_arr + intercept_w
        ss_tot = float(np.sum((ln_h_arr - np.mean(ln_h_arr)) ** 2))
        ss_res = float(np.sum((ln_h_arr - fit_vals) ** 2))
        r_squared_w = float(1.0 - (ss_res / max(1e-12, ss_tot))) if ss_tot > 1e-12 else 1.0

        sigma_wilson = float(np.sqrt(max(0.0, -slope_w)))

        n_ref = float(n_total_particles) if n_total_particles is not None else max(1.0, s_00)
        exp_c = np.exp(intercept_w)
        ratio_occ_sq = min(1.0, max(0.0, exp_c / max(1e-9, n_ref)))
        p_wilson_est = float(1.0 - np.sqrt(ratio_occ_sq))
    else:
        slope_w = 0.0
        intercept_w = 0.0
        r_squared_w = 0.0
        sigma_wilson = sigma_h2h1
        p_wilson_est = 0.0

    g_sq_dense = np.linspace(0.0, float(np.max(g_sq_arr) * 1.15), 100)
    ln_h_dense = slope_w * g_sq_dense + intercept_w

    # 4b. Regresión Lineal Separada para Dimensión X
    g_sq_x = np.array([float(G1_x ** 2), float(G2_x ** 2)], dtype=np.float64)
    ln_h_x = np.array([float(np.log(max(1e-6, s_10))), float(np.log(max(1e-6, s_20)))], dtype=np.float64)
    delta_g_sq_x = g_sq_x[1] - g_sq_x[0]

    if can_anchor:
        u1_x, u2_x = g_sq_x[0], g_sq_x[1]
        y1_x, y2_x = ln_h_x[0], ln_h_x[1]
        sum_u_y_x = u1_x * (y1_x - c_h0) + u2_x * (y2_x - c_h0)
        sum_u_sq_x = u1_x ** 2 + u2_x ** 2
        slope_w_x = float(sum_u_y_x / max(1e-12, sum_u_sq_x))
        intercept_w_x = c_h0
        sigma_wilson_x = float(np.sqrt(max(0.0, -slope_w_x)))
        fit_x = slope_w_x * g_sq_x + c_h0
        ss_tot_x = float(np.sum((ln_h_x - np.mean(ln_h_x)) ** 2))
        ss_res_x = float(np.sum((ln_h_x - fit_x) ** 2))
        r_squared_w_x = float(max(0.0, 1.0 - (ss_res_x / max(1e-12, ss_tot_x)))) if ss_tot_x > 1e-12 else 1.0
        exp_c_x = float(np.exp(c_h0))
        n_ref = float(n_total_particles) if n_total_particles is not None else max(1.0, s_00)
        p_wilson_est_x = float(1.0 - np.sqrt(min(1.0, max(0.0, exp_c_x / max(1e-9, n_ref)))))
    elif abs(delta_g_sq_x) > 1e-12:
        slope_w_x = float((ln_h_x[1] - ln_h_x[0]) / delta_g_sq_x)
        intercept_w_x = float(ln_h_x[0] - slope_w_x * g_sq_x[0])
        sigma_wilson_x = float(np.sqrt(max(0.0, -slope_w_x)))
        r_squared_w_x = 1.0
        exp_c_x = float(np.exp(intercept_w_x))
        n_ref = float(n_total_particles) if n_total_particles is not None else max(1.0, s_00)
        p_wilson_est_x = float(1.0 - np.sqrt(min(1.0, max(0.0, exp_c_x / max(1e-9, n_ref)))))
    else:
        slope_w_x = slope_w
        intercept_w_x = intercept_w
        sigma_wilson_x = sigma_h2h1_x
        r_squared_w_x = 0.0
        exp_c_x = float(np.exp(intercept_w))
        p_wilson_est_x = p_wilson_est

    g_sq_dense_x = np.linspace(0.0, float(max(G2_x ** 2, G_diag ** 2) * 1.15), 100)
    fit_ln_h_x = slope_w_x * g_sq_dense_x + intercept_w_x

    # 4c. Regresión Lineal Separada para Dimensión Y
    g_sq_y = np.array([float(G1_y ** 2), float(G2_y ** 2)], dtype=np.float64)
    ln_h_y = np.array([float(np.log(max(1e-6, s_01))), float(np.log(max(1e-6, s_02)))], dtype=np.float64)
    delta_g_sq_y = g_sq_y[1] - g_sq_y[0]

    if can_anchor:
        u1_y, u2_y = g_sq_y[0], g_sq_y[1]
        y1_y, y2_y = ln_h_y[0], ln_h_y[1]
        sum_u_y_y = u1_y * (y1_y - c_h0) + u2_y * (y2_y - c_h0)
        sum_u_sq_y = u1_y ** 2 + u2_y ** 2
        slope_w_y = float(sum_u_y_y / max(1e-12, sum_u_sq_y))
        intercept_w_y = c_h0
        sigma_wilson_y = float(np.sqrt(max(0.0, -slope_w_y)))
        fit_y = slope_w_y * g_sq_y + c_h0
        ss_tot_y = float(np.sum((ln_h_y - np.mean(ln_h_y)) ** 2))
        ss_res_y = float(np.sum((ln_h_y - fit_y) ** 2))
        r_squared_w_y = float(max(0.0, 1.0 - (ss_res_y / max(1e-12, ss_tot_y)))) if ss_tot_y > 1e-12 else 1.0
        exp_c_y = float(np.exp(c_h0))
        n_ref = float(n_total_particles) if n_total_particles is not None else max(1.0, s_00)
        p_wilson_est_y = float(1.0 - np.sqrt(min(1.0, max(0.0, exp_c_y / max(1e-9, n_ref)))))
    elif abs(delta_g_sq_y) > 1e-12:
        slope_w_y = float((ln_h_y[1] - ln_h_y[0]) / delta_g_sq_y)
        intercept_w_y = float(ln_h_y[0] - slope_w_y * g_sq_y[0])
        sigma_wilson_y = float(np.sqrt(max(0.0, -slope_w_y)))
        r_squared_w_y = 1.0
        exp_c_y = float(np.exp(intercept_w_y))
        n_ref = float(n_total_particles) if n_total_particles is not None else max(1.0, s_00)
        p_wilson_est_y = float(1.0 - np.sqrt(min(1.0, max(0.0, exp_c_y / max(1e-9, n_ref)))))
    else:
        slope_w_y = slope_w
        intercept_w_y = intercept_w
        sigma_wilson_y = sigma_h2h1_y
        r_squared_w_y = 0.0
        exp_c_y = float(np.exp(intercept_w))
        p_wilson_est_y = p_wilson_est

    g_sq_dense_y = np.linspace(0.0, float(max(G2_y ** 2, G_diag ** 2) * 1.15), 100)
    fit_ln_h_y = slope_w_y * g_sq_dense_y + intercept_w_y

    # 4d. Deducción y Conclusiones Físicas de Pendientes e Interceptos
    delta_sigma = abs(sigma_wilson_x - sigma_wilson_y)
    aniso_ratio = float(sigma_wilson_x / max(1e-6, sigma_wilson_y))
    if delta_sigma <= 0.5 or (0.95 <= aniso_ratio <= 1.05):
        aniso_text = f"Isotropía posicional confirmada (σ_x ≈ σ_y, Δσ = {delta_sigma:.2f} nm). Fluctuaciones térmicas homogéneas en 2D."
    elif sigma_wilson_x > sigma_wilson_y:
        aniso_text = f"Anisotropía en X dominante (σ_x/σ_y = {aniso_ratio:.2f}, Δσ = {delta_sigma:.2f} nm). Jitter o deriva en barrido rápido X."
    else:
        # Guarda defensiva: aniso_ratio puede ser exactamente 0.0 (no sólo evitado por el
        # max(1e-6,...) del denominador de su propio cálculo) si sigma_wilson_x=0, p.ej. con
        # datos de red hexagonal/honeycomb cuyos picos de Bragg no caen en los ejes cartesianos
        # fx/fy asumidos por este análisis (ver DEC-012) y el ajuste Wilson-X degenera a pendiente nula.
        inv_aniso_ratio = 1.0 / max(1e-6, aniso_ratio)
        aniso_text = f"Anisotropía en Y dominante (σ_y/σ_x = {inv_aniso_ratio:.2f}, Δσ = {delta_sigma:.2f} nm). Deriva de platina o relajación ortogonal en Y."

    if can_anchor:
        intercept_text = f"Interceptos anclados a ln(H₀) = {c_h0:.2f} (I₀ = {H0:.2e}). Ajuste forzado en el origen (1 parámetro)."
        diff_x = abs(sigma_wilson_x - sigma_h2h1_x)
        diff_y = abs(sigma_wilson_y - sigma_h2h1_y)
        max_diff = max(diff_x, diff_y)
        if max_diff > 2.0:
            bg_text = f"Discrepancia frente a H₂/H₁ (Δσ_max = {max_diff:.2f} nm). Posible elevación de H₀ por fondo difuso o DC leakage."
        else:
            bg_text = f"Excelente concordancia entre H₀ y atenuación de Bragg (Δσ_max = {max_diff:.2f} nm). Fondo difuso limpio en q=0."
    else:
        delta_intercept = abs(intercept_w_x - intercept_w_y)
        if delta_intercept <= 0.20:
            intercept_text = f"Interceptos simétricos (c_x={intercept_w_x:.2f}, c_y={intercept_w_y:.2f}). Amplitud coherente en origen balanceada."
        else:
            intercept_text = f"Asimetría fotométrica en origen (|c_x - c_y| = {delta_intercept:.2f}). Astigmatismo óptico en PSF o contraste anisotrópico."

        i0_mean_eff = (exp_c_x + exp_c_y) / 2.0
        f_coherente = float(i0_mean_eff / max(1e-9, H0))
        if f_coherente < 0.90:
            bg_text = f"Atenuación Debye-Waller estática: e^c / H₀ = {f_coherente:.1%}. El {(1.0 - f_coherente)*100.0:.1f}% de H₀ corresponde a fondo difuso/autofluorescencia incoherente en q=0."
        else:
            bg_text = f"Coherencia central excelente (e^c / H₀ = {f_coherente:.1%}). Fondo difuso residual en q=0 es despreciable."

    vac_text = f"Vacancias estimadas: p_x = {p_wilson_est_x*100.0:.1f}%, p_y = {p_wilson_est_y*100.0:.1f}%."
    summary_concl = f"{aniso_text} | {intercept_text} | {bg_text}"

    # 5. Diagnóstico Paracristalino (Hosemann) - Global y Desglosado X / Y
    fwhm1_x = float(res_dict.get('fwhm_x', 0.0))
    fwhm1_y = float(res_dict.get('fwhm_y', 0.0))
    fwhm1_mean = (fwhm1_x + fwhm1_y) / 2.0

    fwhm2_x = float(res_dict.get('fit_x_2nd', {}).get('fwhm', 0.0))
    fwhm2_y = float(res_dict.get('fit_y_2nd', {}).get('fwhm', 0.0))
    fwhm2_mean = (fwhm2_x + fwhm2_y) / 2.0

    paracrystal_ratio_x = float(fwhm2_x / max(1e-9, fwhm1_x)) if fwhm1_x > 0 else 1.0
    paracrystal_ratio_y = float(fwhm2_y / max(1e-9, fwhm1_y)) if fwhm1_y > 0 else 1.0
    paracrystal_ratio = float(fwhm2_mean / max(1e-9, fwhm1_mean))

    is_type_1_x = paracrystal_ratio_x < 1.40
    is_type_1_y = paracrystal_ratio_y < 1.40
    type_x = "Tipo I (DW Puro)" if is_type_1_x else "Tipo II (Hosemann)"
    type_y = "Tipo I (DW Puro)" if is_type_1_y else "Tipo II (Hosemann)"

    if paracrystal_ratio < 1.40:
        disorder_type = "Tipo I (Debye-Waller Puro)"
        disorder_desc = "Memoria traslacional de red absoluta. Ancho radial limitado por Scherrer (Δq₂ ≈ Δq₁)."
        is_type_1 = True
    else:
        disorder_type = "Tipo II (Paracristal de Hosemann)"
        disorder_desc = "Desorden de espaciado acumulativo. El ancho crece con el orden armónico (Δq₂ > Δq₁)."
        is_type_1 = False

    # 6. Curvas de Decaimiento Debye-Waller - Global y Desglosadas X / Y
    q_norm_curve = np.linspace(0.5, 2.5, 120)
    dw_decay_theory = np.exp(- (q_norm_curve ** 2 - 1.0) * (G1_mean ** 2) * (sigma_h2h1 ** 2))
    dw_decay_x = np.exp(- (q_norm_curve ** 2 - 1.0) * (G1_x ** 2) * (sigma_h2h1_x ** 2))
    dw_decay_y = np.exp(- (q_norm_curve ** 2 - 1.0) * (G1_y ** 2) * (sigma_h2h1_y ** 2))

    points_q_ratio = np.array([1.0, float(np.sqrt(2.0)), 2.0])
    points_H_norm = np.array([
        1.0,
        float(H_diag / max(1e-9, H1_mean)),
        float(H2_mean / max(1e-9, H1_mean))
    ])

    return {
        'H1_x': H1_x,
        'H1_y': H1_y,
        'H1_mean': H1_mean,
        'H2_x': H2_x,
        'H2_y': H2_y,
        'H2_mean': H2_mean,
        'H_diag': H_diag,
        'H0': H0,

        'sigma_h2h1': sigma_h2h1,
        'sigma_h2h1_x': sigma_h2h1_x,
        'sigma_h2h1_y': sigma_h2h1_y,
        'ratio_21_mean': ratio_21_mean,
        'ratio_21_x': ratio_21_x,
        'ratio_21_y': ratio_21_y,

        'sigma_diag': sigma_diag,
        'sigma_diag_x': sigma_diag_x,
        'sigma_diag_y': sigma_diag_y,
        'ratio_diag': ratio_diag_2d,
        'ratio_diag_x': ratio_diag_x,
        'ratio_diag_y': ratio_diag_y,

        'sigma_h1h0': sigma_h1h0,
        'sigma_h1h0_x': sigma_h1h0_x,
        'sigma_h1h0_y': sigma_h1h0_y,
        'ratio_10': ratio_10,
        'ratio_10_x': ratio_10_x,
        'ratio_10_y': ratio_10_y,
        'ratio_0_1x': ratio_0_1x,
        'ratio_0_1y': ratio_0_1y,
        'ratio_0_1mean': ratio_0_1mean,
        'is_h1h0_unstable': True,

        'sigma_wilson': sigma_wilson,
        'r_squared_wilson': r_squared_w,
        'slope_wilson': slope_w,
        'intercept_wilson': intercept_w,
        'p_wilson_est': p_wilson_est,
        'anchor_wilson_to_h0': can_anchor,

        'sigma_wilson_x': sigma_wilson_x,
        'slope_wilson_x': slope_w_x,
        'intercept_wilson_x': intercept_w_x,
        'r_squared_wilson_x': r_squared_w_x,
        'p_wilson_est_x': p_wilson_est_x,

        'sigma_wilson_y': sigma_wilson_y,
        'slope_wilson_y': slope_w_y,
        'intercept_wilson_y': intercept_w_y,
        'r_squared_wilson_y': r_squared_w_y,
        'p_wilson_est_y': p_wilson_est_y,

        'wilson_data': {
            'anchor_wilson_to_h0': can_anchor,
            'g_sq': g_sq_arr,
            'ln_h': ln_h_arr,
            'names': [p["name"] for p in wilson_points],
            'fit_g_sq': g_sq_dense,
            'fit_ln_h': ln_h_dense,
            'points_raw': wilson_points,
            'x': {
                'g_sq': g_sq_x,
                'ln_h': ln_h_x,
                'names': ['(1, 0) X', '(2, 0) 2X'],
                'fit_g_sq': g_sq_dense_x,
                'fit_ln_h': fit_ln_h_x,
                'slope': slope_w_x,
                'intercept': intercept_w_x,
                'sigma': sigma_wilson_x,
                'r_squared': r_squared_w_x,
                'p_est': p_wilson_est_x,
                'i0_eff': exp_c_x
            },
            'y': {
                'g_sq': g_sq_y,
                'ln_h': ln_h_y,
                'names': ['(0, 1) Y', '(0, 2) 2Y'],
                'fit_g_sq': g_sq_dense_y,
                'fit_ln_h': fit_ln_h_y,
                'slope': slope_w_y,
                'intercept': intercept_w_y,
                'sigma': sigma_wilson_y,
                'r_squared': r_squared_w_y,
                'p_est': p_wilson_est_y,
                'i0_eff': exp_c_y
            },
            'diag': {
                'g_sq': float(G_diag ** 2),
                'ln_h': float(np.log(max(1e-6, s_11))),
                'name': '(1, 1) Diag'
            },
            'conclusions': {
                'anisotropy_ratio': aniso_ratio,
                'anisotropy_text': aniso_text,
                'intercept_text': intercept_text,
                'background_text': bg_text,
                'vacancies_text': vac_text,
                'summary': summary_concl
            }
        },

        'paracrystal_diagnosis': {
            'ratio_fwhm': paracrystal_ratio,
            'disorder_type': disorder_type,
            'is_type_1': is_type_1,
            'fwhm_order1': fwhm1_mean,
            'fwhm_order2': fwhm2_mean,
            'fwhm1_x': fwhm1_x,
            'fwhm2_x': fwhm2_x,
            'ratio_fwhm_x': paracrystal_ratio_x,
            'is_type_1_x': is_type_1_x,
            'disorder_type_x': type_x,
            'fwhm1_y': fwhm1_y,
            'fwhm2_y': fwhm2_y,
            'ratio_fwhm_y': paracrystal_ratio_y,
            'is_type_1_y': is_type_1_y,
            'disorder_type_y': type_y,
            'description': disorder_desc
        },

        'debye_waller_curve': {
            'q_norm': q_norm_curve,
            'H_theory': dw_decay_theory,
            'points_q': points_q_ratio,
            'points_H': points_H_norm,
            'labels': ['Orden 1', 'Diagonal (1,1)', 'Orden 2'],
            'x': {
                'q_norm': q_norm_curve,
                'H_theory': dw_decay_x,
                'points_q': np.array([1.0, 2.0]),
                'points_H': np.array([1.0, float(H2_x / max(1e-9, H1_x))]),
                'labels': ['(1,0) X', '(2,0) X']
            },
            'y': {
                'q_norm': q_norm_curve,
                'H_theory': dw_decay_y,
                'points_q': np.array([1.0, 2.0]),
                'points_H': np.array([1.0, float(H2_y / max(1e-9, H1_y))]),
                'labels': ['(0,1) Y', '(0,2) Y']
            },
            'diag': {
                'points_q': np.array([float(np.sqrt(2.0)), float(np.sqrt(2.0))]),
                'points_H': np.array([float(s_11 / max(1e-9, H1_x)), float(s_11 / max(1e-9, H1_y))]),
                'labels': ['Diag / H₁x', 'Diag / H₁y']
            }
        },

        'stability_comparison': {
            'methods': ['H2/H1 (Oro)', 'Diag (1,1)', 'Wilson Plot', 'H1/H0 (Inest.)'],
            'sigmas': [sigma_h2h1, sigma_diag, sigma_wilson, sigma_h1h0],
            'colors': ['#a6e3a1', '#cba6f7', '#89b4fa', '#f38ba8']
        }
    }


# ==============================================================================
# 2. ESPACIO REAL: KDTREE ACOTADO, AGLOMERADOS & FUNCIÓN DE DISTRIBUCIÓN RADIAL g(r)
# ==============================================================================

def find_optimal_grid_bounding_box(
    v_ix: np.ndarray,
    v_iy: np.ndarray,
    n_side: int,
    n_side_y: Optional[int] = None
) -> Tuple[int, int, int, int]:
    """
    Encuentra la posición óptima de la huella de red (n_side_x x n_side_y) en el espacio
    de índices cristalinos enteros (ix, iy) mediante maximización convolutiva 2D de ocupación.

    Garantiza que la grilla abarque la mayor cantidad posible de partículas reales impresas,
    eliminando el desplazamiento espurio de una fila o columna hacia el fondo vacío
    provocado por ruidos asimétricos en los bordes de la imagen confocal.

    Parámetros:
    -----------
    n_side : int
        Número de sitios en el eje X (retrocompatibilidad: también usado en Y si n_side_y es None).
    n_side_y : int, opcional
        Número de sitios en el eje Y. Si es None, se asume red cuadrada (n_side_y = n_side).

    Retorna:
    --------
    min_ix, max_ix, min_iy, max_iy : int
    """
    n_side_x = int(n_side)
    n_side_y = int(n_side_y) if n_side_y is not None else n_side_x

    if len(v_ix) == 0:
        return 0, n_side_x - 1, 0, n_side_y - 1

    min_x_idx, max_x_idx = int(np.min(v_ix)), int(np.max(v_ix))
    min_y_idx, max_y_idx = int(np.min(v_iy)), int(np.max(v_iy))
    span_x = max_x_idx - min_x_idx + 1
    span_y = max_y_idx - min_y_idx + 1

    if span_x < n_side_x or span_y < n_side_y:
        # Si el rango es menor que el tamaño nominal, centrar simétricamente
        pad_x = max(0, n_side_x - span_x)
        pad_y = max(0, n_side_y - span_y)
        min_ix = min_x_idx - pad_x // 2
        max_ix = min_ix + n_side_x - 1
        min_iy = min_y_idx - pad_y // 2
        max_iy = min_iy + n_side_y - 1
        return min_ix, max_ix, min_iy, max_iy

    # Construir matriz de presencia binaria de ocupación
    occ = np.zeros((span_x, span_y), dtype=int)
    for xi, yi in zip(v_ix, v_iy):
        occ[xi - min_x_idx, yi - min_y_idx] = 1

    kernel = np.ones((n_side_x, n_side_y), dtype=int)
    conv = correlate2d(occ, kernel, mode='valid')

    # Encontrar la ventana que maximiza la suma de partículas capturadas
    max_val = np.max(conv)
    best_positions = np.argwhere(conv == max_val)
    if len(best_positions) == 1:
        best_pos = best_positions[0]
    else:
        # En caso de empate, desempatar eligiendo la ventana cuyo centro esté más cerca
        # de la mediana de los índices de las partículas
        target_center_x = (float(np.median(v_ix)) - min_x_idx) - (n_side_x - 1) / 2.0
        target_center_y = (float(np.median(v_iy)) - min_y_idx) - (n_side_y - 1) / 2.0
        dists = [
            (pos[0] - target_center_x) ** 2 + (pos[1] - target_center_y) ** 2
            for pos in best_positions
        ]
        best_pos = best_positions[int(np.argmin(dists))]

    best_min_ix = min_x_idx + int(best_pos[0])
    best_min_iy = min_y_idx + int(best_pos[1])
    best_max_ix = best_min_ix + n_side_x - 1
    best_max_iy = best_min_iy + n_side_y - 1

    return best_min_ix, best_max_ix, best_min_iy, best_max_iy


def detect_clusters_and_chains(
    x: np.ndarray,
    y: np.ndarray,
    a: float = 500.0,
    photons: Optional[np.ndarray] = None,
    r_cluster_factor: float = 0.6,
    brightness_ratio_threshold: float = 1.8,
    a_nominal: Optional[float] = None,
    image_2d: Optional[np.ndarray] = None,
    locs_df: Any = None,
    scale_nm: float = 50.0,
    signature_dict: Optional[Dict[str, Any]] = None,
    tolerance_pct: float = 30.0,
    method: str = 'distance',
    laplacian_sigma_px: Optional[float] = None,
    laplacian_threshold_pct: float = 0.0,
    contour_threshold_pct: float = 20.0
) -> Dict[str, Any]:
    """
    Detecta aglomeraciones de partículas, dímeros, trímeros, cadenas ("gusanitos" en L o S)
    y spots individuales superpuestos por fotometría anómala o análisis morfológico laplaciano.

    Parámetros:
    -----------
    x, y : np.ndarray
        Coordenadas de las partículas en nanómetros.
    a : float
        Período de red nominal en nanómetros.
    photons : np.ndarray, opcional
        Emisión integrada / masa / fotones de cada partícula.
    r_cluster_factor : float
        Fracción del período de red para considerar dos partículas como aglomeradas (default 0.6*a).
    brightness_ratio_threshold : float
        Factor sobre la mediana de brillo para clasificar un spot como doble sobrepuesto (default 1.8x).
    image_2d : np.ndarray, opcional
        Imagen original 2D para análisis fotométrico de contornos y cálculo de estequiometría.
    locs_df : DataFrame, opcional
        DataFrame de localizaciones original con píxeles y fotones.
    scale_nm : float
        Escala nm/pixel.
    signature_dict : dict, opcional
        Firma calibrada del monómero (V0, A0, sigma_psf_px).
    tolerance_pct : float
        Margen de tolerancia estequiométrica (default 20.0%).
    method : str, opcional
        Método de detección: 'distance' (grafo KDTree + fotometría) o 'laplacian' (LoG morfológico).
    laplacian_sigma_px : float, opcional
        Ancho sigma en píxeles para el filtro LoG (si None, usa sigma_psf de la firma).
    laplacian_threshold_pct : float, opcional
        Umbral relativo para el cruce por cero laplaciano (defecto 0.0).

    Retorna:
    --------
    dict con la lista de clusters, clasificación geométrica, fotometría de contornos y estadísticas.
    """
    if a_nominal is not None:
        a = float(a_nominal)

    # Despacho al método alternativo Laplaciano (LoG) si está seleccionado y hay imagen
    if str(method).lower() in ('laplacian', 'log'):
        if image_2d is not None and locs_df is not None and len(locs_df) > 0:
            return detect_clusters_laplacian(
                image_2d=image_2d,
                locs_df=locs_df,
                scale_nm=scale_nm,
                a_nominal=a,
                sigma_psf_px=laplacian_sigma_px,
                laplacian_threshold_pct=laplacian_threshold_pct,
                signature_dict=signature_dict,
                tolerance_pct=tolerance_pct
            )
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    M = len(x)
    if M == 0:
        return {
            'clusters': [],
            'n_clusters': 0,
            'n_dimers': 0,
            'n_trimers': 0,
            'n_chains': 0,
            'n_superimposed': 0,
            'pair_lines': [],
            'cluster_particle_indices': set(),
            'signature': None
        }

    r_cluster = float(r_cluster_factor * a)
    pts = np.column_stack([x, y])
    tree = cKDTree(pts)
    pairs = list(tree.query_pairs(r=r_cluster))

    # Construir componentes conexas mediante Union-Find
    parent = list(range(M))
    def find(i):
        p = parent[i]
        while p != parent[p]:
            parent[p] = parent[parent[p]]
            p = parent[p]
        return p

    def union(i, j):
        root_i, root_j = find(i), find(j)
        if root_i != root_j:
            parent[root_i] = root_j

    for i, j in pairs:
        union(i, j)

    from collections import defaultdict
    comps = defaultdict(list)
    for i in range(M):
        comps[find(i)].append(i)

    # Mediana de fotones para evaluar spots sobrepuestos
    has_photons = photons is not None and len(photons) == M
    if has_photons:
        photons_arr = np.asarray(photons, dtype=np.float64)
        med_photons = float(np.median(photons_arr)) if len(photons_arr) > 0 else 1.0
    else:
        photons_arr = np.ones(M, dtype=np.float64)
        med_photons = 1.0

    # Calibrar firma monomérica automáticamente si hay imagen y no fue provista
    if signature_dict is None and image_2d is not None and locs_df is not None:
        try:
            signature_dict = calibrate_single_emitter_signature(
                image_2d, locs_df, scale_nm=scale_nm, a_nominal=a
            )
        except Exception:
            pass

    clusters_list = []
    cluster_idx = 1
    cluster_particle_indices = set()

    for root, members in comps.items():
        n_m = len(members)
        if n_m > 1:
            for m in members:
                cluster_particle_indices.add(m)
            sub_x = x[members]
            sub_y = y[members]
            sub_pts = np.column_stack([sub_x, sub_y])
            sub_photons = photons_arr[members]

            # Centro de masa ponderado por fotones
            total_w = np.sum(sub_photons)
            if total_w > 0:
                com_x = float(np.sum(sub_x * sub_photons) / total_w)
                com_y = float(np.sum(sub_y * sub_photons) / total_w)
            else:
                com_x = float(np.mean(sub_x))
                com_y = float(np.mean(sub_y))

            # Distancia mínima entre miembros
            sub_tree = cKDTree(sub_pts)
            dists, _ = sub_tree.query(sub_pts, k=2)
            min_d = float(np.min(dists[:, 1])) if dists.shape[1] > 1 else 0.0

            # Clasificación de la geometría del aglomerado
            if n_m == 2:
                c_type = "Dímero"
            elif n_m == 3:
                # Verificar ángulo entre vectores
                v1 = sub_pts[1] - sub_pts[0]
                v2 = sub_pts[2] - sub_pts[1]
                norm1, norm2 = np.linalg.norm(v1), np.linalg.norm(v2)
                if norm1 > 0 and norm2 > 0:
                    cos_theta = np.abs(np.dot(v1, v2) / (norm1 * norm2))
                    if cos_theta < 0.5:  # ~90 grados
                        c_type = "Trímero (L)"
                    else:
                        c_type = "Trímero (Lineal)"
                else:
                    c_type = "Trímero"
            else:
                c_type = f"Gusanito / Cadena ({n_m}p)"

            clusters_list.append({
                'id': cluster_idx,
                'type': c_type,
                'indices': members,
                'n_particles': n_m,
                'com_x': com_x,
                'com_y': com_y,
                'min_dist_nm': min_d,
                'mean_photons': float(np.mean(sub_photons)),
                'max_photons': float(np.max(sub_photons)),
                'ratio_photons': float(np.max(sub_photons) / med_photons) if med_photons > 0 else 1.0,
                'points': sub_pts
            })
            cluster_idx += 1
        elif n_m == 1 and has_photons:
            # Spot individual pero con brillo anómalo (> 1.8x mediana)
            idx = members[0]
            ratio = float(photons_arr[idx] / med_photons) if med_photons > 0 else 1.0
            if ratio >= brightness_ratio_threshold:
                clusters_list.append({
                    'id': cluster_idx,
                    'type': "Sobrepuesta (Brillante)",
                    'indices': [idx],
                    'n_particles': 1,
                    'com_x': float(x[idx]),
                    'com_y': float(y[idx]),
                    'min_dist_nm': 0.0,
                    'mean_photons': float(photons_arr[idx]),
                    'max_photons': float(photons_arr[idx]),
                    'ratio_photons': ratio,
                    'points': np.array([[x[idx], y[idx]]])
                })
                cluster_particle_indices.add(idx)
                cluster_idx += 1

    # Generar líneas de conexión para dibujar en el gráfico
    pair_lines = []
    for i, j in pairs:
        pair_lines.append((float(x[i]), float(y[i]), float(x[j]), float(y[j])))

    n_dimers = sum(1 for c in clusters_list if "Dímero" in c['type'])
    n_trimers = sum(1 for c in clusters_list if "Trímero" in c['type'])
    n_chains = sum(1 for c in clusters_list if "Gusanito" in c['type'] or "Cadena" in c['type'])
    n_super = sum(1 for c in clusters_list if "Sobrepuesta" in c['type'])

    res = {
        'clusters': clusters_list,
        'n_clusters': len(clusters_list),
        'n_dimers': n_dimers,
        'n_trimers': n_trimers,
        'n_chains': n_chains,
        'n_superimposed': n_super,
        'pair_lines': pair_lines,
        'cluster_particle_indices': cluster_particle_indices,
        'signature': None
    }

    # Análisis fotométrico de contornos si se cuenta con la imagen o localizaciones
    if image_2d is not None or locs_df is not None:
        res = analyze_photometric_contours(
            image_2d=image_2d,
            locs_df=locs_df,
            clusters_info=res,
            scale_nm=scale_nm,
            a_nominal=a,
            signature_dict=signature_dict,
            tolerance_pct=tolerance_pct,
            contour_threshold_pct=contour_threshold_pct
        )

    return res


def detect_clusters_laplacian(
    image_2d: np.ndarray,
    locs_df: Any,
    scale_nm: float = 50.0,
    a_nominal: float = 500.0,
    sigma_psf_px: Optional[float] = None,
    laplacian_threshold_pct: float = 0.0,
    signature_dict: Optional[Dict[str, Any]] = None,
    tolerance_pct: float = 30.0,
    min_component_area_px: int = 3
) -> Dict[str, Any]:
    """
    Detecta cúmulos y aglomeraciones mediante el operador Laplaciano de Gaussiana (LoG)
    y el mapeo morfológico de manchones de partículas.

    Fundamento Físico:
    - En una PSF difraccional gaussiana 2D, el Laplaciano negativo -∇²I > 0 define analíticamente
      la cuenca / manchón de la partícula con cruce por cero en r = √2 * sigma.
    - Para un monómero individual, el área teórica del manchón es A_lap,0 ≈ 2 * pi * sigma_psf_px².
    - Se proyectan las coordenadas detectadas (Picasso/Trackpy) a la imagen laplaciana:
      * Si un manchón contiene >= 2 partículas detectadas: se clasifica como Cúmulo Coalescente.
      * Si contiene 1 partícula pero su área laplaciana o fotones exceden la cota física monomérica (1 + tol),
        se clasifica como Cúmulo Sobrepuesto / Dímero no resuelto.
      * Si contiene 1 partícula de área normal, se clasifica como monómero aislado.

    Retorna:
    --------
    dict con estructura idéntica a detect_clusters_and_chains, incluyendo 'clusters', 'n_clusters',
    'pair_lines', 'cluster_particle_indices', 'laplacian_image', 'laplacian_mask', etc.
    """
    if image_2d is None or locs_df is None or len(locs_df) == 0:
        return {
            'clusters': [],
            'n_clusters': 0,
            'n_dimers': 0,
            'n_trimers': 0,
            'n_chains': 0,
            'n_superimposed': 0,
            'pair_lines': [],
            'cluster_particle_indices': set(),
            'signature': signature_dict,
            'method': 'laplacian'
        }

    img = np.asarray(image_2d, dtype=np.float64)
    if img.ndim == 3:
        img = img[0] if img.shape[0] < img.shape[2] else img[:, :, 0]
    H, W = img.shape[:2]

    # Extraer coordenadas
    if 'x_nm' in locs_df.columns and 'y_nm' in locs_df.columns:
        x_nm = locs_df['x_nm'].values.astype(float)
        y_nm = locs_df['y_nm'].values.astype(float)
    else:
        x_nm = locs_df['x'].values.astype(float) * scale_nm
        y_nm = locs_df['y'].values.astype(float) * scale_nm

    M = len(x_nm)
    if M == 0:
        return {
            'clusters': [],
            'n_clusters': 0,
            'n_dimers': 0,
            'n_trimers': 0,
            'n_chains': 0,
            'n_superimposed': 0,
            'pair_lines': [],
            'cluster_particle_indices': set(),
            'signature': signature_dict,
            'method': 'laplacian'
        }

    # Calibrar o resolver firma monomérica
    if signature_dict is None:
        try:
            signature_dict = calibrate_single_emitter_signature(
                img, locs_df, scale_nm=scale_nm, a_nominal=a_nominal
            )
        except Exception:
            signature_dict = None

    if signature_dict is not None:
        V0 = max(float(signature_dict.get('V0', 1000.0)), 1e-3)
        A0 = max(float(signature_dict.get('A0', 30.0)), 1e-3)
        sig_from_dict = signature_dict.get('sigma_psf_px', 139.0 / scale_nm)
    else:
        V0 = 1000.0
        A0 = 30.0
        sig_from_dict = 139.0 / scale_nm

    sigma_px = float(sigma_psf_px) if sigma_psf_px is not None else float(sig_from_dict)
    sigma_px = max(0.8, sigma_px)
    A_lap_0 = 2.0 * np.pi * (sigma_px ** 2)

    # 1. Calcular Laplaciano de Gaussiana (-∇²(G * I))
    log_img = -ndimage.gaussian_laplace(img, sigma=sigma_px)

    # 2. Binarizar por cruce por cero o porcentaje de pico
    if laplacian_threshold_pct <= 0.0:
        binary_mask = (log_img > 0.0)
    else:
        max_log = float(np.max(log_img))
        thresh = (laplacian_threshold_pct / 100.0) * max_log if max_log > 0 else 0.0
        binary_mask = (log_img > thresh)

    # Filtrar ruido de píxeles aislados mediante apertura morfológica
    binary_mask = ndimage.binary_opening(binary_mask, structure=np.ones((3, 3)))

    # 3. Etiquetar componentes conexas (manchones)
    labeled_mask, num_features = ndimage.label(binary_mask, structure=np.ones((3, 3)))

    # 4. Mapear partículas detectadas a manchones laplacianos
    particle_labels = np.zeros(M, dtype=int)
    for i in range(M):
        px_x = int(round(x_nm[i] / scale_nm))
        px_y = int(round(y_nm[i] / scale_nm))
        px_x = max(0, min(W - 1, px_x))
        px_y = max(0, min(H - 1, px_y))
        lbl = int(labeled_mask[px_y, px_x])

        if lbl == 0:
            # Buscar en vecindad de 5x5 por si el centroide cayó en el borde inmediato del cruce por cero
            ymin_n, ymax_n = max(0, px_y - 2), min(H, px_y + 3)
            xmin_n, xmax_n = max(0, px_x - 2), min(W, px_x + 3)
            sub_lbl = labeled_mask[ymin_n:ymax_n, xmin_n:xmax_n]
            nonzeros = sub_lbl[sub_lbl > 0]
            if len(nonzeros) > 0:
                vals, counts = np.unique(nonzeros, return_counts=True)
                lbl = int(vals[np.argmax(counts)])

        particle_labels[i] = lbl

    # Invertir mapeo: label -> lista de índices de partículas
    component_particles = defaultdict(list)
    for i, lbl in enumerate(particle_labels):
        if lbl > 0:
            component_particles[lbl].append(i)

    # Estimar área de monómero empírica de manchones que albergan exactamente 1 partícula
    single_areas = []
    for lbl, members in component_particles.items():
        if len(members) == 1:
            single_areas.append(float(np.sum(labeled_mask == lbl)))
    if len(single_areas) >= 3:
        A_lap_ref = float(np.median(single_areas))
    else:
        A_lap_ref = float(A_lap_0)

    clusters_list = []
    cluster_particle_indices = set()
    pair_lines = []
    cluster_idx = 1
    tol_factor = float(tolerance_pct / 100.0)

    for lbl, members in component_particles.items():
        n_det = len(members)
        comp_mask = (labeled_mask == lbl)
        comp_area_px = float(np.sum(comp_mask))

        if comp_area_px < min_component_area_px:
            continue

        yy, xx = np.where(comp_mask)
        ymin, ymax = max(0, int(np.min(yy)) - 2), min(H, int(np.max(yy)) + 3)
        xmin, xmax = max(0, int(np.min(xx)) - 2), min(W, int(np.max(xx)) + 3)

        patch = img[ymin:ymax, xmin:xmax]
        patch_mask = comp_mask[ymin:ymax, xmin:xmax]

        # Estimar fondo local en el perímetro del parche
        border = np.concatenate([patch[0, :], patch[-1, :], patch[:, 0], patch[:, -1]]) if patch.size > 0 else np.array([0.0])
        bg = float(np.percentile(border, 50)) if len(border) > 0 else 0.0
        sig = np.where(patch_mask, np.clip(patch - bg, 0, None), 0.0)
        v_omega = float(np.sum(sig))
        a_omega = float(comp_area_px)

        # Polígono de contorno en nanómetros
        contour_poly_nm = []
        if cv2 is not None:
            try:
                cnts, _ = cv2.findContours(comp_mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                if cnts:
                    largest = max(cnts, key=cv2.contourArea)
                    pts = largest.squeeze()
                    if pts.ndim == 2 and len(pts) > 2:
                        for pt in pts:
                            contour_poly_nm.append((float(pt[0] * scale_nm), float(pt[1] * scale_nm)))
            except Exception:
                pass

        is_cluster = False
        c_type = ""
        n_est = n_det
        status = 'OK'
        com_x = 0.0
        com_y = 0.0
        sub_pts = np.empty((0, 2))
        min_d = 0.0

        if n_det >= 2:
            is_cluster = True
            for m in members:
                cluster_particle_indices.add(m)
            sub_x = x_nm[members]
            sub_y = y_nm[members]
            sub_pts = np.column_stack([sub_x, sub_y])
            com_x = float(np.mean(sub_x))
            com_y = float(np.mean(sub_y))

            sub_tree = cKDTree(sub_pts)
            dists, _ = sub_tree.query(sub_pts, k=min(len(sub_pts), 2))
            min_d = float(np.min(dists[:, 1])) if dists.shape[1] > 1 else 0.0

            # Líneas de conexión
            for mi in range(len(members)):
                for mj in range(mi + 1, len(members)):
                    if np.hypot(sub_x[mi] - sub_x[mj], sub_y[mi] - sub_y[mj]) < 1.5 * a_nominal:
                        pair_lines.append((float(sub_x[mi]), float(sub_y[mi]), float(sub_x[mj]), float(sub_y[mj])))

            if n_det == 2:
                c_type = "Dímero (Laplaciano)"
            elif n_det == 3:
                c_type = "Trímero (Laplaciano)"
            else:
                c_type = f"Cúmulo Laplaciano ({n_det}p)"

            n_est_raw = max(2, int(round(v_omega / V0)))
            n_est = max(n_det, n_est_raw)
            lower_bound = n_det * (1.0 - tol_factor) * V0
            upper_bound = n_det * (1.0 + tol_factor) * V0
            if lower_bound <= v_omega <= upper_bound:
                status = 'OK'
            elif v_omega > upper_bound:
                status = 'UNDER_RESOLVED'
            else:
                status = 'OVER_DETECTED'

        elif n_det == 1:
            idx = members[0]
            ratio_area = a_omega / A_lap_ref if A_lap_ref > 0 else 1.0
            ratio_vol = v_omega / V0 if V0 > 0 else 1.0

            # Si el área del manchón laplaciano o el volumen superan la cota de tolerancia monomérica
            if ratio_area >= (1.0 + tol_factor) or ratio_vol >= (1.0 + tol_factor):
                is_cluster = True
                cluster_particle_indices.add(idx)
                com_x = float(x_nm[idx])
                com_y = float(y_nm[idx])
                sub_pts = np.array([[com_x, com_y]])
                min_d = 0.0
                c_type = "Sobrepuesta (Laplaciano)"
                n_est = max(2, int(round(max(ratio_vol, ratio_area))))
                status = 'UNDER_RESOLVED'

        if is_cluster:
            clusters_list.append({
                'id': cluster_idx,
                'cluster_id': cluster_idx,
                'type': c_type,
                'indices': sorted([int(m) for m in members]),
                'particle_indices': sorted([int(m) for m in members]),
                'n_particles': n_det,
                'n_det': n_det,
                'n_est': n_est,
                'com_x': com_x,
                'com_y': com_y,
                'min_dist_nm': min_d,
                'points': sub_pts,
                'v_omega': v_omega,
                'a_omega': a_omega,
                'ratio_v': float(v_omega / (max(1, n_det) * V0)) if V0 > 0 else 1.0,
                'ratio_a': float(a_omega / (max(1, n_det) * A_lap_ref)) if A_lap_ref > 0 else 1.0,
                'status': status,
                'contour_polygon_nm': contour_poly_nm,
                'patch_origin_px': (xmin, ymin),
                'patch': patch,
                'mask': patch_mask,
                'sigma_psf_px': sigma_px
            })
            cluster_idx += 1

    n_dimers = sum(1 for c in clusters_list if "Dímero" in c['type'])
    n_trimers = sum(1 for c in clusters_list if "Trímero" in c['type'])
    n_chains = sum(1 for c in clusters_list if "Cúmulo" in c['type'])
    n_super = sum(1 for c in clusters_list if "Sobrepuesta" in c['type'])

    n_under = sum(1 for c in clusters_list if c.get('status') == 'UNDER_RESOLVED')
    n_ok = sum(1 for c in clusters_list if c.get('status') == 'OK')
    n_over = sum(1 for c in clusters_list if c.get('status') == 'OVER_DETECTED')

    return {
        'clusters': clusters_list,
        'n_clusters': len(clusters_list),
        'n_dimers': n_dimers,
        'n_trimers': n_trimers,
        'n_chains': n_chains,
        'n_superimposed': n_super,
        'n_under_resolved': n_under,
        'n_ok_resolved': n_ok,
        'n_over_detected': n_over,
        'pair_lines': pair_lines,
        'cluster_particle_indices': cluster_particle_indices,
        'signature': signature_dict,
        'method': 'laplacian',
        'laplacian_image': log_img,
        'laplacian_mask': binary_mask,
        'laplacian_labels': labeled_mask
    }


def calibrate_from_psf_image(
    psf_img: np.ndarray,
    scale_nm: float = 50.0,
    laser_power_factor: float = 1.0,
    target_img_max: Optional[float] = None
) -> Dict[str, Any]:
    """
    Calibra de forma analítica y óptica los parámetros iniciales de detección para Trackpy,
    Picasso (LQ/MLE), la Deconvolución Richardson-Lucy y el Desacople Fotométrico
    a partir de una imagen confocal de nanopartícula única (psf.tiff).

    Parámetros:
    -----------
    psf_img : np.ndarray
        Matriz 2D de la PSF confocal (ej. 34x34 px).
    scale_nm : float
        Tamaño de píxel en nanómetros (por defecto 50.0 nm/px, estándar de laboratorio).
    laser_power_factor : float
        Factor multiplicador de potencia láser o escala de normalización de la PSF
        (por defecto 1.0).
    target_img_max : float, opcional
        Intensidad máxima de la imagen de muestra destino, para cálculo automático
        del factor de escala si la PSF está normalizada.

    Retorna:
    --------
    Dict con parámetros ópticos calibrados, volúmenes de emisión, gradientes y presets.
    """
    img = np.asarray(psf_img, dtype=np.float64)
    if img.ndim == 3:
        img = img[0] if img.shape[0] < img.shape[2] else img[:, :, 0]
    H, W = img.shape[:2]

    # Fondo estimado en los bordes
    border = np.concatenate([img[0, :], img[-1, :], img[:, 0], img[:, -1]])
    bg_init = float(np.median(border))

    # Ajuste Gaussiano 2D
    yy, xx = np.indices((H, W))
    coords = np.column_stack([xx.ravel(), yy.ravel()])

    def gauss2d(xy, b, A, x0, y0, sx, sy):
        return b + A * np.exp(-((xy[:, 0] - x0) ** 2 / (2.0 * sx ** 2) + (xy[:, 1] - y0) ** 2 / (2.0 * sy ** 2)))

    p0 = [bg_init, float(np.max(img) - bg_init), W / 2.0, H / 2.0, 2.0, 2.0]
    bounds = ([0.0, 0.0, 0.0, 0.0, 0.5, 0.5], [np.inf, np.inf, W, H, 20.0, 20.0])

    try:
        popt, _ = curve_fit(gauss2d, coords, img.ravel(), p0=p0, bounds=bounds, maxfev=1500)
        bg_fit, A_fit, x0_fit, y0_fit, sx_fit, sy_fit = popt
    except Exception:
        bg_fit = bg_init
        A_fit = float(np.max(img) - bg_init)
        x0_fit, y0_fit = W / 2.0, H / 2.0
        sx_fit, sy_fit = 2.13, 2.13

    sx_fit = abs(float(sx_fit))
    sy_fit = abs(float(sy_fit))
    sigma_psf_px = float(np.sqrt(sx_fit * sy_fit))
    sigma_psf_nm = float(sigma_psf_px * scale_nm)
    fwhm_px = float(2.35482 * sigma_psf_px)
    fwhm_nm = float(2.35482 * sigma_psf_nm)

    # Considerar normalización y potencia láser
    if target_img_max is not None and target_img_max > 0 and (A_fit + bg_fit) > 0:
        eff_factor = float(target_img_max / (A_fit + bg_fit))
    else:
        eff_factor = float(laser_power_factor)

    A_eff = float(A_fit * eff_factor)
    V0 = float(2.0 * np.pi * A_eff * (sigma_psf_px ** 2))
    A0 = float(np.pi * (2.0 * sigma_psf_px) ** 2)

    # Gradiente máximo en r = sigma
    max_gradient = float(A_eff / (sigma_psf_px * np.sqrt(np.e)))

    # Presets recomendados
    diam_suggested = int(2 * round(2.0 * sigma_psf_px) + 1)
    if diam_suggested % 2 == 0:
        diam_suggested += 1
    diam_suggested = max(3, diam_suggested)

    minmass_suggested = float(round(0.35 * V0, 3))
    separation_suggested = float(round(2.5 * sigma_psf_px, 1))

    box_size_suggested = diam_suggested
    min_net_grad_suggested = float(round(0.50 * max_gradient, 3))

    return {
        'sigma_psf_px': sigma_psf_px,
        'sigma_psf_nm': sigma_psf_nm,
        'sigma_x_px': sx_fit,
        'sigma_y_px': sy_fit,
        'fwhm_px': fwhm_px,
        'fwhm_nm': fwhm_nm,
        'A0_amp': float(A_fit),
        'A_eff': A_eff,
        'bg': float(bg_fit),
        'V0': V0,
        'A0': A0,
        'max_gradient': max_gradient,
        'scale_nm': scale_nm,
        'laser_power_factor': eff_factor,
        'trackpy': {
            'diameter': diam_suggested,
            'minmass': minmass_suggested,
            'separation': separation_suggested,
            'noise_size': 1.0,
            'percentile': 64
        },
        'picasso': {
            'box_size': box_size_suggested,
            'min_net_gradient': min_net_grad_suggested,
            'method': 'gausslq',
            'baseline': int(round(bg_fit * eff_factor))
        },
        'richardson_lucy': {
            'psf_sigma': float(round(sigma_psf_px, 2)),
            'iterations': 15
        },
        'monomer_signature': {
            'V0': float(V0),
            'A0': float(A0),
            'sigma_psf_px': float(sigma_psf_px),
            'sigma_psf_nm': float(sigma_psf_nm),
            'bg': float(bg_fit),
            'fwhm_nm': float(fwhm_nm)
        }
    }


def calibrate_single_emitter_signature(
    image_2d: Optional[np.ndarray],
    locs_df: Any,
    scale_nm: float = 50.0,
    a_nominal: float = 500.0,
    max_samples: int = 100
) -> Dict[str, Any]:
    """
    Calibra la firma fotométrica y el ancho difractivo de la PSF de monómeros individuales
    a partir de la mediana/media de partículas verificadas como aisladas (separación d > 0.70 * a_nominal).

    Retorna:
    --------
    dict con V0 (volumen mediano), A0 (área difractiva mediana),
    sigma_psf_px (ancho medio de PSF en píxeles), sigma_psf_nm, y estadísticas.
    """
    # Cota metrológica por defecto (Confocal 532 nm NA 1.4: sigma ~ 139 nm)
    def_sigma_nm = 139.0
    def_sigma_px = def_sigma_nm / max(scale_nm, 1.0)
    fallback_res = {
        'V0': 1000.0,
        'A0': float(np.pi * (2.0 * def_sigma_px) ** 2),
        'sigma_psf_px': float(def_sigma_px),
        'sigma_psf_nm': float(def_sigma_nm),
        'sigma_psf_median_px': float(def_sigma_px),
        'n_calibrated': 0,
        'bg_mean': 0.0,
        'is_fallback': True
    }

    if image_2d is None or locs_df is None or len(locs_df) == 0:
        return fallback_res

    # Coordenadas en nm y px
    if 'x_nm' in locs_df.columns and 'y_nm' in locs_df.columns:
        x_nm = locs_df['x_nm'].values.astype(float)
        y_nm = locs_df['y_nm'].values.astype(float)
    elif 'x' in locs_df.columns and 'y' in locs_df.columns:
        x_nm = (locs_df['x'].values * scale_nm).astype(float)
        y_nm = (locs_df['y'].values * scale_nm).astype(float)
    else:
        return fallback_res

    if 'x' in locs_df.columns and 'y' in locs_df.columns:
        x_px = locs_df['x'].values.astype(float)
        y_px = locs_df['y'].values.astype(float)
    else:
        x_px = x_nm / scale_nm
        y_px = y_nm / scale_nm

    M = len(x_nm)
    if M < 2:
        return fallback_res

    # Partículas aisladas (separadas > 0.70 * a_nominal de cualquier otra)
    tree = cKDTree(np.column_stack([x_nm, y_nm]))
    dists, _ = tree.query(np.column_stack([x_nm, y_nm]), k=2)
    isolated_mask = dists[:, 1] > (0.70 * a_nominal)
    isolated_indices = np.where(isolated_mask)[0]

    if len(isolated_indices) == 0:
        # Relajar a 0.50 * a si la red es densa
        isolated_mask = dists[:, 1] > (0.50 * a_nominal)
        isolated_indices = np.where(isolated_mask)[0]
        if len(isolated_indices) == 0:
            return fallback_res

    img = np.asarray(image_2d, dtype=float)
    H, W = img.shape[:2]

    # Tamaño del parche local: ~ 11x11 px
    half = max(4, int(round(1.5 * a_nominal / scale_nm / 3.0)))
    half = min(half, 8)

    v0_list = []
    a0_list = []
    sigma_list = []
    bg_list = []

    sample_indices = isolated_indices
    if len(sample_indices) > max_samples:
        np.random.seed(42)
        sample_indices = np.random.choice(sample_indices, size=max_samples, replace=False)

    for idx in sample_indices:
        px = int(round(x_px[idx]))
        py = int(round(y_px[idx]))
        if py - half < 0 or py + half + 1 > H or px - half < 0 or px + half + 1 > W:
            continue

        patch = img[py - half : py + half + 1, px - half : px + half + 1]
        border_px = np.concatenate([patch[0, :], patch[-1, :], patch[:, 0], patch[:, -1]])
        bg = float(np.percentile(border_px, 50))
        bg_list.append(bg)

        signal = np.clip(patch - bg, 0, None)
        vol = float(np.sum(signal))
        if vol <= 0:
            continue
        v0_list.append(vol)

        thresh = bg + 0.25 * float(np.max(signal))
        area = float(np.sum(patch > thresh))
        a0_list.append(area)

        yy, xx = np.indices(patch.shape)
        sigma_eff = None
        try:
            coords_local = np.column_stack([xx.ravel(), yy.ravel()])
            popt_g, _ = curve_fit(
                lambda xy, b, a, x0, y0, s: b + a * np.exp(-((xy[:, 0] - x0) ** 2 + (xy[:, 1] - y0) ** 2) / (2.0 * s ** 2)),
                coords_local, patch.ravel(),
                p0=[bg, float(np.ptp(patch)), float(half), float(half), 2.8],
                bounds=([0.0, 0.0, 0.0, 0.0, 0.5], [np.inf, np.inf, 2 * half, 2 * half, 10.0]),
                max_nfev=150
            )
            s_val = float(popt_g[4])
            if 0.5 <= s_val <= 10.0:
                sigma_eff = s_val
        except Exception:
            pass

        if sigma_eff is None:
            mx = np.sum(xx * signal) / vol
            my = np.sum(yy * signal) / vol
            var_x = np.sum(((xx - mx) ** 2) * signal) / vol
            var_y = np.sum(((yy - my) ** 2) * signal) / vol
            if var_x > 0 and var_y > 0:
                sigma_eff = float(np.sqrt((var_x + var_y) / 2.0))

        if sigma_eff is not None and 0.5 <= sigma_eff <= 10.0:
            sigma_list.append(sigma_eff)

    if len(v0_list) < 2 or len(sigma_list) < 2:
        return fallback_res

    V0 = float(np.median(v0_list))
    A0 = float(np.median(a0_list))
    # Usar ancho medio de PSF de las partículas verificadas como aisladas
    sigma_psf_mean = float(np.mean(sigma_list))
    sigma_psf_median = float(np.median(sigma_list))

    return {
        'V0': V0,
        'A0': A0,
        'sigma_psf_px': sigma_psf_mean,
        'sigma_psf_nm': sigma_psf_mean * scale_nm,
        'sigma_psf_median_px': sigma_psf_median,
        'n_calibrated': len(sigma_list),
        'bg_mean': float(np.mean(bg_list)) if bg_list else 0.0,
        'is_fallback': False
    }


def fit_multi_gaussian_roi(
    patch: np.ndarray,
    n_particles: int,
    sigma_psf_px: float,
    scale_nm: float = 50.0,
    origin_px: Tuple[float, float] = (0.0, 0.0),
    initial_seeds: Optional[List[Tuple[float, float]]] = None,
    mask: Optional[np.ndarray] = None,
    bg_filter_pct: float = 20.0,
    constrain_centers: bool = True,
    signature_dict: Optional[Dict[str, Any]] = None,
    tolerance_pct: float = 30.0
) -> List[Dict[str, Any]]:
    """
    Ajusta una mezcla de n-Gaussianas 2D sobre una región de interés (parche local)
    con el ancho óptico fijado al valor calibrado sigma = sigma_psf_px.

    Soporta:
    - Enmascaramiento estricto a cero fuera de la zona gráficamente marcada (mask).
    - Restricción geométrica de centros (x_k, y_k) al interior del contorno.
    - Cotas de amplitud/volumen físico con tolerancia estricta del 30% asumiendo
      nanopartículas idénticas (A0, V0).
    """
    patch = np.asarray(patch, dtype=float)
    H, W = patch.shape[:2]
    yy, xx = np.indices((H, W))
    coords = np.column_stack([xx.ravel(), yy.ravel()])

    # Validación y aplicación de máscara de contorno
    has_mask = False
    mask_bool = None
    if mask is not None:
        mask_arr = np.asarray(mask)
        if mask_arr.shape == (H, W):
            mask_bool = mask_arr.astype(bool)
            if np.any(mask_bool):
                has_mask = True

    border_px = np.concatenate([patch[0, :], patch[-1, :], patch[:, 0], patch[:, -1]])
    bg_init = float(np.percentile(border_px, 50))
    i_max_raw = float(np.max(patch))

    if has_mask:
        patch_masked = patch.copy()
        patch_masked[~mask_bool] = 0.0
        i_max = float(np.max(patch_masked))
        bg_cut = max(bg_init, (bg_filter_pct / 100.0) * i_max) if bg_filter_pct > 0 else bg_init
        signal = np.where(mask_bool, np.clip(patch - bg_cut, 0, None), 0.0)
        tot_signal = float(np.sum(signal))
        data_1d = signal.ravel()
        mask_flat = mask_bool.ravel()

        def multi_gaussian(xy, *params):
            bg = params[0]
            val = np.where(mask_flat, bg, 0.0)
            sig2_2 = 2.0 * (sigma_psf_px ** 2)
            for k in range(n_particles):
                xk = params[1 + 3 * k]
                yk = params[2 + 3 * k]
                Ik = params[3 + 3 * k]
                dx = xy[:, 0] - xk
                dy = xy[:, 1] - yk
                val += np.where(mask_flat, Ik * np.exp(-(dx * dx + dy * dy) / sig2_2), 0.0)
            return val
    else:
        signal = np.clip(patch - bg_init, 0, None)
        tot_signal = float(np.sum(signal))
        i_max = i_max_raw
        data_1d = patch.ravel()

        def multi_gaussian(xy, *params):
            bg = params[0]
            val = np.full(len(xy), bg, dtype=float)
            sig2_2 = 2.0 * (sigma_psf_px ** 2)
            for k in range(n_particles):
                xk = params[1 + 3 * k]
                yk = params[2 + 3 * k]
                Ik = params[3 + 3 * k]
                dx = xy[:, 0] - xk
                dy = xy[:, 1] - yk
                val += Ik * np.exp(-(dx * dx + dy * dy) / sig2_2)
            return val

    # Estimación de amplitud nominal monomérica A0 (partículas idénticas con tolerancia 30%)
    if has_mask:
        vol_total = float(np.sum(np.maximum(0.0, patch - bg_init) * mask_bool))
    else:
        vol_total = float(np.sum(np.maximum(0.0, patch - bg_init)))

    A_patch = (vol_total / max(n_particles, 1)) / (2.0 * np.pi * (sigma_psf_px ** 2))
    if A_patch <= 0:
        A_patch = max(float(i_max_raw) / max(n_particles, 1), 1e-3)

    A0_sig = None
    if signature_dict is not None:
        if 'A0_amp' in signature_dict and float(signature_dict['A0_amp']) > 0:
            A0_sig = float(signature_dict['A0_amp'])
        elif 'V0' in signature_dict and float(signature_dict['V0']) > 0:
            A0_sig = float(signature_dict['V0']) / (2.0 * np.pi * (sigma_psf_px ** 2))
        elif 'A0' in signature_dict and float(signature_dict['A0']) > 0 and 'sigma_psf_px' not in signature_dict:
            A0_sig = float(signature_dict['A0'])

    # Si la firma calibrada es compatible físicamente con el pico del parche
    # (n_particles * A0_sig debe ser capaz de alcanzar al menos el 80% del pico observado,
    #  y A0_sig no debe superar 2.5 veces A_patch):
    if A0_sig is not None and (A0_sig * n_particles >= 0.80 * i_max_raw) and (A0_sig <= 2.50 * A_patch):
        A0_nom = A0_sig
    else:
        A0_nom = A_patch

    tol_f = max(0.05, float(tolerance_pct) / 100.0)
    I_min = max(0.0, (1.0 - tol_f) * A0_nom)
    I_max = (1.0 + tol_f) * A0_nom
    I_est = float(np.clip(A0_nom, I_min, I_max))

    # Restricción espacial de centros
    if constrain_centers and has_mask:
        y_idx, x_idx = np.where(mask_bool)
        min_xc = max(0.0, float(np.min(x_idx)) - 0.5)
        max_xc = min(float(W), float(np.max(x_idx)) + 0.5)
        min_yc = max(0.0, float(np.min(y_idx)) - 0.5)
        max_yc = min(float(H), float(np.max(y_idx)) + 0.5)
    else:
        min_xc, max_xc = 0.0, float(W)
        min_yc, max_yc = 0.0, float(H)

    p0 = [0.0 if has_mask else bg_init]
    lb = [0.0]
    ub = [i_max * 0.5 if has_mask else i_max * 1.5]

    if initial_seeds is not None and len(initial_seeds) == n_particles:
        seeds = initial_seeds
    elif n_particles == 1:
        if tot_signal > 0:
            cx = float(np.sum(xx * signal) / tot_signal)
            cy = float(np.sum(yy * signal) / tot_signal)
        else:
            cx, cy = W / 2.0, H / 2.0
        seeds = [(cx, cy)]
    elif n_particles == 2:
        if tot_signal > 0:
            cx = float(np.sum(xx * signal) / tot_signal)
            cy = float(np.sum(yy * signal) / tot_signal)
            mu_xx = np.sum(((xx - cx) ** 2) * signal) / tot_signal
            mu_yy = np.sum(((yy - cy) ** 2) * signal) / tot_signal
            mu_xy = np.sum(((xx - cx) * (yy - cy)) * signal) / tot_signal
            cov = np.array([[mu_xx, mu_xy], [mu_xy, mu_yy]])
            eigvals, eigvecs = np.linalg.eigh(cov)
            v_main = eigvecs[:, 1]
        else:
            cx, cy = W / 2.0, H / 2.0
            v_main = np.array([1.0, 0.0])

        offset = 0.60 * sigma_psf_px
        seeds = [
            (cx - offset * v_main[0], cy - offset * v_main[1]),
            (cx + offset * v_main[0], cy + offset * v_main[1])
        ]
    else:
        if tot_signal > 0:
            cx = float(np.sum(xx * signal) / tot_signal)
            cy = float(np.sum(yy * signal) / tot_signal)
            mu_xx = np.sum(((xx - cx) ** 2) * signal) / tot_signal
            mu_yy = np.sum(((yy - cy) ** 2) * signal) / tot_signal
            mu_xy = np.sum(((xx - cx) * (yy - cy)) * signal) / tot_signal
            cov = np.array([[mu_xx, mu_xy], [mu_xy, mu_yy]])
            eigvals, eigvecs = np.linalg.eigh(cov)
            v_main = eigvecs[:, 1]
        else:
            cx, cy = W / 2.0, H / 2.0
            v_main = np.array([1.0, 0.0])

        offsets = np.linspace(-0.8 * sigma_psf_px * (n_particles - 1) / 2.0,
                              0.8 * sigma_psf_px * (n_particles - 1) / 2.0, n_particles)
        seeds = [(cx + off * v_main[0], cy + off * v_main[1]) for off in offsets]

    for (sx, sy) in seeds:
        sx_c = float(np.clip(sx, min_xc + 0.1, max_xc - 0.1))
        sy_c = float(np.clip(sy, min_yc + 0.1, max_yc - 0.1))
        p0.extend([sx_c, sy_c, I_est])
        lb.extend([min_xc, min_yc, I_min])
        ub.extend([max_xc, max_yc, I_max])

    try:
        popt, _ = curve_fit(
            multi_gaussian,
            coords,
            data_1d,
            p0=p0,
            bounds=(lb, ub),
            method='trf',
            max_nfev=350
        )
    except Exception:
        popt = p0

    bg_fitted = float(popt[0])
    results = []
    ox_px, oy_px = origin_px

    for k in range(n_particles):
        local_x = float(popt[1 + 3 * k])
        local_y = float(popt[2 + 3 * k])
        amp = float(popt[3 + 3 * k])
        global_px_x = ox_px + local_x
        global_px_y = oy_px + local_y
        global_nm_x = global_px_x * scale_nm
        global_nm_y = global_px_y * scale_nm
        photons_est = float(amp * 2.0 * np.pi * (sigma_psf_px ** 2))

        results.append({
            'x_nm': global_nm_x,
            'y_nm': global_nm_y,
            'x': global_px_x,
            'y': global_px_y,
            'local_x': local_x,
            'local_y': local_y,
            'amplitude': amp,
            'photons': photons_est,
            'mass': photons_est,
            'sigma_px': sigma_psf_px,
            'bg': bg_fitted
        })

    return results


def analyze_photometric_contours(
    image_2d: Optional[np.ndarray],
    locs_df: Any,
    clusters_info: Dict[str, Any],
    scale_nm: float = 50.0,
    a_nominal: float = 500.0,
    signature_dict: Optional[Dict[str, Any]] = None,
    tolerance_pct: float = 30.0,
    contour_threshold_pct: float = 20.0
) -> Dict[str, Any]:
    """
    Segmenta las regiones conexas de emisión alrededor de cada cúmulo,
    mide el volumen luminoso integrado V_omega y área A_omega,
    y evalúa la estequiometría estimada n_est vs detecciones n_det con tolerancia +/- tolerance_pct%.
    Por definición física, todo cúmulo está conformado por 2 o más partículas (N >= 2).
    """
    if clusters_info is None:
        return {'clusters': [], 'n_clusters': 0}

    clusters = clusters_info.get('clusters', [])
    if len(clusters) == 0:
        return clusters_info

    # Calibrar firma monómero automáticamente si no fue provista
    if signature_dict is None:
        signature_dict = calibrate_single_emitter_signature(
            image_2d, locs_df, scale_nm=scale_nm, a_nominal=a_nominal
        )

    V0 = max(float(signature_dict.get('V0', 1000.0)), 1e-3)
    A0 = max(float(signature_dict.get('A0', 30.0)), 1e-3)
    sigma_psf_px = float(signature_dict.get('sigma_psf_px', 2.8))

    has_img = image_2d is not None
    if has_img:
        img = np.asarray(image_2d, dtype=float)
        H, W = img.shape[:2]

    tol_factor = float(tolerance_pct / 100.0)

    for c in clusters:
        n_det = len(c.get('indices', []))
        c['n_det'] = n_det

        if not has_img:
            ratio_p = float(c.get('ratio_photons', 1.0))
            n_est = max(2, int(round(ratio_p))) if 'Sobrepuesta' in c.get('type', '') else max(2, n_det)
            c['v_omega'] = V0 * ratio_p
            c['a_omega'] = A0 * n_est
            c['ratio_v'] = ratio_p
            c['ratio_a'] = float(n_est)
            c['n_est'] = n_est
            c['contour_polygon_nm'] = []
            if n_det == n_est:
                c['status'] = 'OK'
            elif n_det < n_est:
                c['status'] = 'UNDER_RESOLVED'
            else:
                c['status'] = 'OVER_DETECTED'
            continue

        com_x = float(c.get('com_x', 0.0))
        com_y = float(c.get('com_y', 0.0))
        cx_px = com_x / scale_nm
        cy_px = com_y / scale_nm

        pts = c.get('points', None)
        if pts is not None and len(pts) > 1:
            d_max_nm = float(np.max(np.hypot(pts[:, 0] - com_x, pts[:, 1] - com_y)))
            half = int(np.ceil(d_max_nm / scale_nm + 2.5 * sigma_psf_px))
        else:
            half = int(np.ceil(3.0 * sigma_psf_px))
        half = max(half, 6)

        x_min = max(0, int(round(cx_px)) - half)
        x_max = min(W, int(round(cx_px)) + half + 1)
        y_min = max(0, int(round(cy_px)) - half)
        y_max = min(H, int(round(cy_px)) + half + 1)

        patch = img[y_min:y_max, x_min:x_max]
        if patch.size == 0:
            c['status'] = 'OK'
            continue

        border_px = np.concatenate([patch[0, :], patch[-1, :], patch[:, 0], patch[:, -1]])
        bg = float(np.percentile(border_px, 50))
        sig = np.clip(patch - bg, 0, None)
        v_omega = float(np.sum(sig))

        thresh_val = bg + (float(contour_threshold_pct) / 100.0) * float(np.max(sig)) if np.max(sig) > 0 else bg
        mask_binary = (patch > thresh_val).astype(np.uint8)
        a_omega = float(np.sum(mask_binary))

        mask_cnt = mask_binary.copy()
        contour_poly_nm = []
        if cv2 is not None:
            try:
                contours, _ = cv2.findContours(mask_binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                if contours:
                    largest_cnt = max(contours, key=cv2.contourArea)
                    mask_cnt = np.zeros_like(mask_binary)
                    cv2.drawContours(mask_cnt, [largest_cnt], -1, 1, -1)
                    cnt_pts = largest_cnt.squeeze()
                    if cnt_pts.ndim == 2:
                        for pt in cnt_pts:
                            px_glob = x_min + pt[0]
                            py_glob = y_min + pt[1]
                            contour_poly_nm.append((float(px_glob * scale_nm), float(py_glob * scale_nm)))
            except Exception:
                pass

        ratio_v = v_omega / V0
        ratio_a = a_omega / A0
        n_est_raw = max(2, int(round(ratio_v)))

        # Regla de tolerancia estequiométrica (+/- tolerance_pct%):
        lower_bound = n_det * (1.0 - tol_factor) * V0
        upper_bound = n_det * (1.0 + tol_factor) * V0

        if lower_bound <= v_omega <= upper_bound:
            n_est = max(2, n_det)
            status = 'OK'
        elif v_omega > upper_bound:
            n_est = max(max(2, n_det + 1), n_est_raw)
            status = 'UNDER_RESOLVED'
        else:
            n_est = max(2, min(n_det - 1, n_est_raw)) if n_det > 2 else 2
            status = 'OVER_DETECTED'

        c['v_omega'] = v_omega
        c['a_omega'] = a_omega
        c['ratio_v'] = ratio_v
        c['ratio_a'] = ratio_a
        c['n_est'] = n_est
        c['status'] = status
        c['contour_polygon_nm'] = contour_poly_nm
        c['patch_origin_px'] = (x_min, y_min)
        c['patch'] = patch
        c['mask'] = (mask_cnt > 0)
        c['sigma_psf_px'] = sigma_psf_px

    n_under = sum(1 for c in clusters if c.get('status') == 'UNDER_RESOLVED')
    n_ok = sum(1 for c in clusters if c.get('status') == 'OK')
    n_over = sum(1 for c in clusters if c.get('status') == 'OVER_DETECTED')

    clusters_info['n_under_resolved'] = n_under
    clusters_info['n_ok_resolved'] = n_ok
    clusters_info['n_over_detected'] = n_over
    clusters_info['signature'] = signature_dict

    return clusters_info


def create_manual_cluster(
    locs_df: Any,
    particle_indices: List[int],
    image_2d: Optional[np.ndarray],
    scale_nm: float = 50.0,
    a_nominal: float = 500.0,
    signature_dict: Optional[Dict[str, Any]] = None,
    tolerance_pct: float = 30.0,
    cluster_id: int = 1
) -> Dict[str, Any]:
    """
    Crea un cúmulo manual a partir de una lista de índices de partículas seleccionadas por el usuario.
    Calcula el centro de masa, el parche envolvente, el contorno fotométrico y la estequiometría.
    """
    sub_df = locs_df.loc[particle_indices]
    xs_nm = sub_df['x_nm'].values if 'x_nm' in sub_df else (sub_df['x'].values * scale_nm)
    ys_nm = sub_df['y_nm'].values if 'y_nm' in sub_df else (sub_df['y'].values * scale_nm)

    com_x = float(np.mean(xs_nm))
    com_y = float(np.mean(ys_nm))
    n_det = len(particle_indices)
    pts = np.column_stack([xs_nm, ys_nm])

    sigma_psf_px = 139.0 / scale_nm
    V0 = 1000.0
    A0 = 100.0
    if signature_dict is not None:
        sigma_psf_px = float(signature_dict.get('sigma_psf_px', sigma_psf_px))
        V0 = float(signature_dict.get('V0', V0))
        A0 = float(signature_dict.get('A0', A0))

    patch = None
    mask = None
    contour_poly_nm = []
    x_min, y_min = 0, 0
    v_omega = V0 * n_det
    a_omega = A0 * n_det

    if image_2d is not None and image_2d.size > 0:
        H, W = image_2d.shape[:2]
        cx_px = com_x / scale_nm
        cy_px = com_y / scale_nm
        d_max_nm = float(np.max(np.hypot(xs_nm - com_x, ys_nm - com_y))) if len(xs_nm) > 1 else 0.0
        half = int(np.ceil(d_max_nm / scale_nm + 2.5 * sigma_psf_px))
        half = max(half, 8)

        x_min = max(0, int(round(cx_px)) - half)
        x_max = min(W, int(round(cx_px)) + half + 1)
        y_min = max(0, int(round(cy_px)) - half)
        y_max = min(H, int(round(cy_px)) + half + 1)

        patch = image_2d[y_min:y_max, x_min:x_max]
        if patch.size > 0:
            border_px = np.concatenate([patch[0, :], patch[-1, :], patch[:, 0], patch[:, -1]])
            bg = float(np.percentile(border_px, 50))
            sig = np.clip(patch - bg, 0, None)
            v_omega = float(np.sum(sig))
            thresh_val = bg + 0.25 * float(np.max(sig)) if np.max(sig) > 0 else bg
            mask_binary = (patch > thresh_val).astype(np.uint8)
            a_omega = float(np.sum(mask_binary))
            mask_cnt = mask_binary.copy()

            try:
                import cv2
                contours, _ = cv2.findContours(mask_binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                if contours:
                    largest_cnt = max(contours, key=cv2.contourArea)
                    mask_cnt = np.zeros_like(mask_binary)
                    cv2.drawContours(mask_cnt, [largest_cnt], -1, 1, -1)
                    cnt_pts = largest_cnt.squeeze()
                    if cnt_pts.ndim == 2:
                        for pt in cnt_pts:
                            px_glob = x_min + pt[0]
                            py_glob = y_min + pt[1]
                            contour_poly_nm.append((float(px_glob * scale_nm), float(py_glob * scale_nm)))
            except Exception:
                pass
            mask = (mask_cnt > 0)

    ratio_v = v_omega / max(V0, 1e-3)
    ratio_a = a_omega / max(A0, 1e-3)
    n_est_raw = max(2, int(round(ratio_v)))

    tol_f = max(0.05, float(tolerance_pct) / 100.0)
    lower_bound = n_det * (1.0 - tol_f) * V0
    upper_bound = n_det * (1.0 + tol_f) * V0

    if lower_bound <= v_omega <= upper_bound:
        n_est = n_det
        status = 'OK'
    elif v_omega > upper_bound:
        n_est = max(n_det + 1, n_est_raw)
        status = 'UNDER_RESOLVED'
    else:
        n_est = max(2, min(n_det, n_est_raw))
        status = 'OVER_DETECTED'

    return {
        'id': cluster_id,
        'cluster_id': cluster_id,
        'type': 'Cúmulo Manual',
        'is_manual': True,
        'indices': sorted([int(i) for i in particle_indices]),
        'particle_indices': sorted([int(i) for i in particle_indices]),
        'n_det': len(particle_indices),
        'points': pts,
        'com_x': com_x,
        'com_y': com_y,
        'v_omega': v_omega,
        'a_omega': a_omega,
        'ratio_v': ratio_v,
        'ratio_a': ratio_a,
        'n_est': n_est,
        'status': status,
        'contour_polygon_nm': contour_poly_nm,
        'patch_origin_px': (x_min, y_min),
        'patch': patch,
        'mask': mask,
        'sigma_psf_px': sigma_psf_px
    }


def inspect_single_spot_photometry(
    image_2d: Optional[np.ndarray],
    x_nm: float,
    y_nm: float,
    signature_dict: Optional[Dict[str, Any]] = None,
    threshold_pct: float = 20.0,
    scale_nm: float = 50.0,
    a_nominal: float = 500.0
) -> Dict[str, Any]:
    """
    Inspecciona fotométricamente un punto candidato o 'punto sospechoso' en la imagen 2D.
    Extrae el parche local centrado en (x_nm, y_nm), calcula el fondo local, el pico,
    el umbral según threshold_pct, segmenta el contorno cerrado más próximo/relevante,
    y calcula el área A_omega, volumen luminoso integrado V_omega y sugiere el número
    de partículas n_suggested comparando con la firma monomérica calibrada (V0, A0).
    """
    def_sigma_nm = 139.0
    def_sigma_px = def_sigma_nm / max(scale_nm, 1.0)
    V0 = 1000.0
    # A0 unificado con A_lap_0 de detect_clusters_and_chains() (2*pi*sigma^2) —
    # decisión explícita del usuario: "el criterio usado en cúmulos está
    # perfecto, unificar con ese", en vez de la derivación analítica pura del
    # cruce por cero del LoG (que daría pi*(2*sigma)^2 = 4*pi*sigma^2 si se
    # tratara al parche como un blob gaussiano ya convolucionado). Ambos
    # métodos deben compartir la misma convención de área de referencia.
    A0 = float(2.0 * np.pi * def_sigma_px ** 2)
    sigma_psf_px = float(def_sigma_px)

    if signature_dict is not None:
        V0 = max(float(signature_dict.get('V0', V0)), 1e-3)
        A0 = max(float(signature_dict.get('A0', A0)), 1e-3)
        sigma_psf_px = float(signature_dict.get('sigma_psf_px', def_sigma_px))

    res_default: Dict[str, Any] = {
        'x_nm': float(x_nm),
        'y_nm': float(y_nm),
        'x_px': float(x_nm / scale_nm),
        'y_px': float(y_nm / scale_nm),
        'bg': 0.0,
        'peak': 1.0,
        'threshold_val': 0.2,
        'area_px': float(A0),
        'v_omega': float(V0),
        'ratio_v': 1.0,
        'ratio_a': 1.0,
        'n_suggested': 1,
        'contour_polygon_nm': [],
        'patch': None,
        'patch_origin_px': (0, 0),
        'sigma_psf_px': sigma_psf_px
    }

    if image_2d is None:
        return res_default

    img = np.asarray(image_2d, dtype=float)
    H, W = img.shape[:2]

    cx_px = x_nm / scale_nm
    cy_px = y_nm / scale_nm
    ix = int(round(cx_px))
    iy = int(round(cy_px))

    # Parche local proporcional al ancho óptico y espaciado de red
    half = max(8, int(round(2.5 * sigma_psf_px)))
    half = min(half, max(12, int(round(a_nominal / scale_nm))))

    x_min = max(0, ix - half)
    x_max = min(W, ix + half + 1)
    y_min = max(0, iy - half)
    y_max = min(H, iy + half + 1)

    patch = img[y_min:y_max, x_min:x_max]
    if patch.size < 9:
        return res_default

    # Estimación del fondo perimetral (para el peso fotométrico v_omega, igual que antes)
    border_px = np.concatenate([patch[0, :], patch[-1, :], patch[:, 0], patch[:, -1]])
    bg = float(np.median(border_px))
    peak = float(np.max(patch))

    # Segmentación por Laplaciano de Gaussiana (-∇²(G*I)), unificada con el
    # mismo criterio ya usado y validado en detect_clusters_and_chains() —
    # cruce por cero (threshold_pct<=0) o umbral porcentual del pico del LoG,
    # en vez del corte biseccional de intensidad plana anterior, que ignoraba
    # por completo la forma de la PSF calibrada.
    log_patch = -ndimage.gaussian_laplace(patch, sigma=sigma_psf_px)
    if threshold_pct <= 0.0:
        threshold_val = 0.0
        mask_binary = (log_patch > 0.0).astype(np.uint8)
    else:
        max_log = float(np.max(log_patch))
        threshold_val = (float(threshold_pct) / 100.0) * max_log if max_log > 0 else 0.0
        mask_binary = (log_patch > threshold_val).astype(np.uint8)

    contour_poly_nm: List[Tuple[float, float]] = []
    a_omega = float(np.sum(mask_binary))
    v_omega = float(np.sum(np.maximum(0.0, patch - bg) * mask_binary))

    try:
        import cv2
        contours, _ = cv2.findContours(mask_binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            center_x = cx_px - x_min
            center_y = cy_px - y_min
            best_cnt = None
            best_dist = 1e9

            for cnt in contours:
                dist = cv2.pointPolygonTest(cnt, (float(center_x), float(center_y)), True)
                if dist >= 0:
                    best_cnt = cnt
                    break
                else:
                    if abs(dist) < best_dist:
                        best_dist = abs(dist)
                        best_cnt = cnt

            if best_cnt is None:
                best_cnt = max(contours, key=cv2.contourArea)

            a_omega = float(cv2.contourArea(best_cnt))
            if a_omega < 1.0:
                a_omega = float(np.sum(mask_binary))

            mask_cnt = np.zeros_like(mask_binary)
            cv2.drawContours(mask_cnt, [best_cnt], -1, 1, -1)
            v_omega = float(np.sum(np.maximum(0.0, patch - bg) * mask_cnt))

            cnt_pts = best_cnt.squeeze()
            if cnt_pts.ndim == 2:
                for pt in cnt_pts:
                    px_glob = x_min + pt[0]
                    py_glob = y_min + pt[1]
                    contour_poly_nm.append((float(px_glob * scale_nm), float(py_glob * scale_nm)))
    except Exception:
        pass

    ratio_v = v_omega / V0
    ratio_a = a_omega / A0
    n_suggested = max(1, int(round(ratio_v)))
    if ratio_v >= 1.5 and n_suggested < 2:
        n_suggested = 2
    n_suggested = min(max(n_suggested, 1), 6)

    return {
        'x_nm': float(x_nm),
        'y_nm': float(y_nm),
        'x_px': float(cx_px),
        'y_px': float(cy_px),
        'bg': bg,
        'peak': peak,
        'threshold_val': threshold_val,
        'area_px': a_omega,
        'v_omega': v_omega,
        'vol_omega': v_omega,
        'ratio_v': ratio_v,
        'ratio_vol': ratio_v,
        'ratio_a': ratio_a,
        'ratio_area': ratio_a,
        'n_suggested': n_suggested,
        'contour_polygon_nm': contour_poly_nm,
        'patch': patch,
        'patch_origin_px': (x_min, y_min),
        'sigma_psf_px': sigma_psf_px,
        'mask': (mask_cnt > 0) if 'mask_cnt' in locals() else (mask_binary > 0)
    }



def resolve_clusters(
    x: np.ndarray,
    y: np.ndarray,
    clusters_info: Dict[str, Any],
    action: str = 'keep_nearest',
    a: float = 500.0,
    x0: float = 0.0,
    y0: float = 0.0,
    photons: Optional[np.ndarray] = None,
    target_cluster_id: Optional[int] = None,
    image_2d: Optional[np.ndarray] = None,
    signature_dict: Optional[Dict[str, Any]] = None,
    scale_nm: float = 50.0,
    tolerance_pct: float = 30.0,
    n_gaussians: Optional[int] = None,
    use_contour_mask: bool = True,
    bg_filter_pct: float = 20.0,
    constrain_centers: bool = True,
    initial_seeds: Optional[List[Tuple[float, float]]] = None
) -> Tuple[np.ndarray, np.ndarray, Optional[np.ndarray], List[int]]:
    """
    Aplica una regla de resolución y desacoplamiento sobre los aglomerados detectados.
    Permite operar individualmente (target_cluster_id) o en lote sobre todos los cúmulos.

    Acciones soportadas:
    - 'keep_nearest': Conserva únicamente la partícula más cercana al nodo ideal más próximo
      y descarta las partículas satélite/aglomeradas redundantes.
    - 'merge_com': Fusiona los miembros del aglomerado en su Centro de Masa (ponderado por fotones).
    - 'multi_gaussian': Desacopla spots sobrepuestos / aglomerados sub-resueltos mediante ajuste
      2D de n-Gaussianas con ancho óptico fijado al patrón calibrado sigma = sigma_psf.
    - 'keep_all': No modifica las partículas.

    Retorna:
    --------
    new_x, new_y, new_photons, discarded_indices
    """
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    M = len(x)
    has_photons = photons is not None and len(photons) == M
    photons_arr = np.asarray(photons, dtype=np.float64) if has_photons else None

    if action == 'keep_all' or not clusters_info.get('clusters'):
        return x.copy(), y.copy(), (photons_arr.copy() if has_photons else None), []

    clusters = clusters_info['clusters']
    discarded_indices: Set[int] = set()
    new_points_to_add: List[Tuple[float, float, float]] = []

    # Si se especificó un target_cluster_id, filtrar exclusivamente ese cúmulo
    target_clusters = [c for c in clusters if (c.get('id') == target_cluster_id or c.get('cluster_id') == target_cluster_id)] if target_cluster_id is not None else clusters

    for c in target_clusters:
        members = c.get('indices', c.get('particle_indices', []))

        if action == 'keep_nearest':
            if len(members) <= 1:
                continue
            best_m = members[0]
            best_dist = 1e12
            for m in members:
                mx, my = x[m], y[m]
                mix = np.round((mx - x0) / a)
                miy = np.round((my - y0) / a)
                d = np.hypot(mx - (x0 + mix * a), my - (y0 + miy * a))
                if d < best_dist:
                    best_dist = d
                    best_m = m
            for m in members:
                if m != best_m:
                    discarded_indices.add(m)

        elif action == 'merge_com':
            if len(members) <= 1:
                continue
            for m in members:
                discarded_indices.add(m)
            w_photons = float(np.sum(photons_arr[members])) if has_photons else 1.0
            new_points_to_add.append((c['com_x'], c['com_y'], w_photons))

        elif action == 'multi_gaussian':
            # Estimar número de partículas a desacoplar: por física de cúmulo debe ser sí o sí N >= 2
            n_target = max(2, int(c.get('n_est', len(members))))
            if n_gaussians is not None and (target_cluster_id is None or c.get('id') == target_cluster_id or c.get('cluster_id') == target_cluster_id):
                n_target = max(2, int(n_gaussians))
            n_target = min(max(n_target, 2), 8)

            # Obtener parche y ancho sigma_psf
            patch = c.get('patch', None)
            origin_px = c.get('patch_origin_px', (0, 0))
            sigma_psf_px = c.get('sigma_psf_px', None)
            mask = c.get('mask', None) if use_contour_mask else None

            if sigma_psf_px is None:
                if signature_dict is not None and 'sigma_psf_px' in signature_dict:
                    sigma_psf_px = float(signature_dict['sigma_psf_px'])
                else:
                    sigma_psf_px = 139.0 / max(scale_nm, 1.0)

            if patch is None and image_2d is not None:
                cx_px = c['com_x'] / scale_nm
                cy_px = c['com_y'] / scale_nm
                half = int(np.ceil(3.0 * sigma_psf_px))
                H_img, W_img = image_2d.shape[:2]
                x_min = max(0, int(round(cx_px)) - half)
                x_max = min(W_img, int(round(cx_px)) + half + 1)
                y_min = max(0, int(round(cy_px)) - half)
                y_max = min(H_img, int(round(cy_px)) + half + 1)
                patch = image_2d[y_min:y_max, x_min:x_max]
                origin_px = (x_min, y_min)

            if use_contour_mask and patch is not None and (mask is None or not np.any(mask)):
                poly_nm = c.get('contour_polygon_nm', [])
                if len(poly_nm) > 2 and cv2 is not None:
                    try:
                        mask_from_poly = np.zeros(patch.shape[:2], dtype=np.uint8)
                        pts_local = []
                        for px_nm, py_nm in poly_nm:
                            lx = (px_nm / scale_nm) - origin_px[0]
                            ly = (py_nm / scale_nm) - origin_px[1]
                            pts_local.append([int(round(lx)), int(round(ly))])
                        pts_arr = np.array([pts_local], dtype=np.int32)
                        cv2.fillPoly(mask_from_poly, pts_arr, 1)
                        if np.any(mask_from_poly > 0):
                            mask = (mask_from_poly > 0)
                    except Exception:
                        pass

            local_seeds = None
            if initial_seeds is not None and len(initial_seeds) >= 2 and (target_cluster_id is None or c.get('id') == target_cluster_id or c.get('cluster_id') == target_cluster_id):
                n_target = len(initial_seeds)
                local_seeds = []
                for sx_nm, sy_nm in initial_seeds:
                    lx = (sx_nm / scale_nm) - origin_px[0]
                    ly = (sy_nm / scale_nm) - origin_px[1]
                    local_seeds.append((lx, ly))

            if patch is not None and patch.size > 0:
                fitted = fit_multi_gaussian_roi(
                    patch=patch,
                    n_particles=n_target,
                    sigma_psf_px=sigma_psf_px,
                    scale_nm=scale_nm,
                    origin_px=origin_px,
                    initial_seeds=local_seeds,
                    mask=mask,
                    bg_filter_pct=bg_filter_pct,
                    constrain_centers=constrain_centers,
                    signature_dict=signature_dict,
                    tolerance_pct=tolerance_pct
                )
                for m in members:
                    discarded_indices.add(m)
                for f_em in fitted:
                    new_points_to_add.append((f_em['x_nm'], f_em['y_nm'], f_em['photons']))
            else:
                # Fallback sin imagen: separar levemente a lo largo de un eje nominal
                for m in members:
                    discarded_indices.add(m)
                w_phot = (float(np.sum(photons_arr[members])) if has_photons else 1.0) / n_target
                offsets = np.linspace(-0.35 * a, 0.35 * a, n_target)
                for off in offsets:
                    new_points_to_add.append((c['com_x'] + off, c['com_y'], w_phot))

    # Filtrar partículas originales que no fueron descartadas
    keep_mask = np.ones(M, dtype=bool)
    for idx in discarded_indices:
        keep_mask[idx] = False

    out_x = list(x[keep_mask])
    out_y = list(y[keep_mask])
    out_p = list(photons_arr[keep_mask]) if has_photons else None

    for px, py, pw in new_points_to_add:
        out_x.append(px)
        out_y.append(py)
        if has_photons and out_p is not None:
            out_p.append(pw)

    return (
        np.array(out_x, dtype=np.float64),
        np.array(out_y, dtype=np.float64),
        np.array(out_p, dtype=np.float64) if has_photons else None,
        sorted(list(discarded_indices))
    )


def resolve_clusters_dataframe(
    df: Any,
    clusters_info: Dict[str, Any],
    action: str = 'keep_nearest',
    a: float = 500.0,
    x0: float = 0.0,
    y0: float = 0.0,
    scale_nm: float = 50.0,
    target_cluster_id: Optional[int] = None,
    image_2d: Optional[np.ndarray] = None,
    signature_dict: Optional[Dict[str, Any]] = None,
    tolerance_pct: float = 30.0,
    n_gaussians: Optional[int] = None,
    use_contour_mask: bool = True,
    bg_filter_pct: float = 20.0,
    constrain_centers: bool = True,
    initial_seeds: Optional[List[Tuple[float, float]]] = None
) -> Tuple[Any, Dict[str, Any]]:
    """
    Aplica resolve_clusters sobre un DataFrame con coordenadas de localización.
    Soporta resolución individual por target_cluster_id o en lote sobre todos los aglomerados.
    """
    if df is None or len(df) == 0 or not clusters_info.get('clusters'):
        return (df.copy() if df is not None else None), {'clusters_resolved': 0, 'particles_removed': 0, 'particles_added': 0}

    x_nm = df['x_nm'].values
    y_nm = df['y_nm'].values
    photons = df['photons'].values if 'photons' in df.columns else (df['mass'].values if 'mass' in df.columns else None)

    new_x, new_y, new_photons, discarded_indices = resolve_clusters(
        x_nm, y_nm, clusters_info,
        action=action,
        a=a,
        x0=x0,
        y0=y0,
        photons=photons,
        target_cluster_id=target_cluster_id,
        image_2d=image_2d,
        signature_dict=signature_dict,
        scale_nm=scale_nm,
        tolerance_pct=tolerance_pct,
        n_gaussians=n_gaussians,
        use_contour_mask=use_contour_mask,
        bg_filter_pct=bg_filter_pct,
        constrain_centers=constrain_centers,
        initial_seeds=initial_seeds
    )

    n_orig_kept = len(df) - len(discarded_indices)
    n_added = len(new_x) - n_orig_kept

    if action == 'keep_nearest':
        df_out = df.drop(df.index[discarded_indices]).reset_index(drop=True)
    else:
        df_base = df.drop(df.index[discarded_indices]).reset_index(drop=True)
        new_records = [dict(row) for _, row in df_base.iterrows()]
        for i in range(n_orig_kept, len(new_x)):
            rec = {
                'x_nm': new_x[i],
                'y_nm': new_y[i],
                'x': new_x[i] / scale_nm,
                'y': new_y[i] / scale_nm
            }
            if new_photons is not None:
                if 'photons' in df.columns:
                    rec['photons'] = new_photons[i]
                if 'mass' in df.columns:
                    rec['mass'] = new_photons[i]
            # Rellenar otras columnas existentes con valores por defecto
            for col in df.columns:
                if col not in rec:
                    rec[col] = 0.0
            new_records.append(rec)
        import pandas as pd
        df_out = pd.DataFrame(new_records)

    n_resolved = 1 if target_cluster_id is not None else clusters_info.get('n_clusters', 0)
    stats = {
        'clusters_resolved': n_resolved,
        'particles_removed': len(discarded_indices),
        'particles_added': n_added
    }
    return df_out, stats


def resolve_single_spot_multi_gaussian(
    df: Any,
    spot_index: int,
    n_particles: int = 2,
    image_2d: Optional[np.ndarray] = None,
    signature_dict: Optional[Dict[str, Any]] = None,
    scale_nm: float = 50.0,
    a_nominal: float = 500.0,
    use_contour_mask: bool = True,
    bg_filter_pct: float = 20.0,
    constrain_centers: bool = True,
    tolerance_pct: float = 30.0,
    initial_seeds: Optional[List[Tuple[float, float]]] = None
) -> Tuple[Any, Dict[str, Any]]:
    """
    Desacopla un punto sospechoso específico (spot_index en df) ajustando n_particles Gaussianas
    con ancho óptico restringido a sigma_psf calibrado y máscara de contorno cerrada (resto a 0).
    Reemplaza la partícula spot_index por las n_particles resueltas y devuelve el nuevo DataFrame.
    """
    if df is None or len(df) == 0:
        return (df.copy() if df is not None else None), {'status': 'error', 'msg': 'DataFrame vacío'}

    if spot_index not in df.index:
        if 0 <= int(spot_index) < len(df):
            spot_index = df.index[int(spot_index)]
        else:
            return df.copy(), {'status': 'error', 'msg': f'Índice de partícula #{spot_index} inválido'}

    row = df.loc[spot_index]
    x_nm = float(row['x_nm']) if 'x_nm' in row else float(row['x'] * scale_nm)
    y_nm = float(row['y_nm']) if 'y_nm' in row else float(row['y'] * scale_nm)

    spot_info = inspect_single_spot_photometry(
        image_2d=image_2d,
        x_nm=x_nm,
        y_nm=y_nm,
        signature_dict=signature_dict,
        scale_nm=scale_nm,
        a_nominal=a_nominal
    )

    patch = spot_info.get('patch')
    origin_px = spot_info.get('patch_origin_px', (0, 0))
    sigma_psf_px = spot_info.get('sigma_psf_px', 139.0 / scale_nm)
    mask = spot_info.get('mask') if use_contour_mask else None
    if use_contour_mask and patch is not None and (mask is None or not np.any(mask)):
        poly_nm = spot_info.get('contour_polygon_nm', [])
        if len(poly_nm) > 2:
            try:
                import cv2
                mask_from_poly = np.zeros(patch.shape[:2], dtype=np.uint8)
                pts_local = []
                for px_nm, py_nm in poly_nm:
                    lx = (px_nm / scale_nm) - origin_px[0]
                    ly = (py_nm / scale_nm) - origin_px[1]
                    pts_local.append([int(round(lx)), int(round(ly))])
                pts_arr = np.array([pts_local], dtype=np.int32)
                cv2.fillPoly(mask_from_poly, pts_arr, 1)
                if np.any(mask_from_poly > 0):
                    mask = (mask_from_poly > 0)
            except Exception:
                pass

    # Por regla física, si se desacopla un spot sospechoso debe ser al menos en n >= 2 partículas
    n_fit = min(max(int(n_particles), 2), 8)
    local_seeds = None
    if initial_seeds is not None and len(initial_seeds) >= 2:
        n_fit = min(max(len(initial_seeds), 2), 8)
        local_seeds = []
        for sx_nm, sy_nm in initial_seeds:
            lx = (sx_nm / scale_nm) - origin_px[0]
            ly = (sy_nm / scale_nm) - origin_px[1]
            local_seeds.append((lx, ly))

    if patch is not None and patch.size > 0:
        fitted = fit_multi_gaussian_roi(
            patch=patch,
            n_particles=n_fit,
            sigma_psf_px=sigma_psf_px,
            scale_nm=scale_nm,
            origin_px=origin_px,
            initial_seeds=local_seeds,
            mask=mask,
            bg_filter_pct=bg_filter_pct,
            constrain_centers=constrain_centers,
            signature_dict=signature_dict,
            tolerance_pct=tolerance_pct
        )
    else:
        # Fallback sin imagen: separar levemente alrededor del punto
        fitted = []
        offsets = np.linspace(-0.25 * a_nominal, 0.25 * a_nominal, n_fit)
        phot_each = float(row.get('photons', 1000.0)) / n_fit
        for off in offsets:
            fitted.append({
                'x_nm': x_nm + off,
                'y_nm': y_nm,
                'x': (x_nm + off) / scale_nm,
                'y': y_nm / scale_nm,
                'photons': phot_each,
                'mass': phot_each
            })

    # Construir nuevo DataFrame: descartar spot_index y añadir los nuevos puntos
    df_base = df.drop(index=[spot_index]).reset_index(drop=True)
    new_records = [dict(r) for _, r in df_base.iterrows()]

    for f_em in fitted:
        rec = {
            'x_nm': float(f_em['x_nm']),
            'y_nm': float(f_em['y_nm']),
            'x': float(f_em['x']),
            'y': float(f_em['y'])
        }
        if 'photons' in df.columns:
            rec['photons'] = float(f_em.get('photons', 1000.0))
        if 'mass' in df.columns:
            rec['mass'] = float(f_em.get('mass', 1000.0))
        for col in df.columns:
            if col not in rec:
                rec[col] = 0.0
        new_records.append(rec)

    df_out = pd.DataFrame(new_records)
    stats = {
        'status': 'ok',
        'spot_index': spot_index,
        'n_fitted': len(fitted),
        'fitted_emitters': fitted
    }
    return df_out, stats


def analyze_real_space_kdtree(
    x: np.ndarray,
    y: np.ndarray,
    a: float,
    b: Optional[float] = None,
    n_side_x: Optional[int] = None,
    n_side_y: Optional[int] = None,
    n_side: Optional[int] = None,
    margin_percent: float = 10.0
) -> Dict[str, Any]:
    """
    Realiza el mapeo en espacio real mediante índices de red enteros con cota superior
    estricta (elipse normalizada de semiejes a/2, b/2), soportando redes rectangulares
    / anisótropas (a != b, N_x != N_y).

    Evita el error histórico de emparejamiento con vecinos a 450 nm ante vacancias
    y descompone los residuos en componentes cartesianas Delta x y Delta y, eliminando
    la subestimación del 34.5% provocada por std() sobre distancias euclidianas Rayleigh.

    Limitaciones Conocidas (no corregidas en esta versión, documentadas para uso informado):
    1. Cota Elipsoidal Conservadora: la elipse (dx/a)^2+(dy/b)^2<0.25 está estrictamente
       contenida en la celda de Wigner-Seitz rectangular real (|dx|<a/2, |dy|<b/2) —
       tangente sólo en los 4 puntos medios de los ejes. Esto garantiza CERO riesgo de
       emparejamiento cruzado con un nodo vecino (mejora sobre el bug histórico), pero
       excluye partículas correctamente emparejadas cerca de las esquinas de la celda
       (~21.5% del área de la celda) de sigma_x/sigma_y/Psi_T, sesgando ligeramente esas
       métricas a alto desorden (sigma_pos/min(a,b) >~ 15-20%, régimen cercano a fusión
       de Lindemann). Sesgo despreciable en el régimen de bajo desorden (< 5%).
    2. Rotación Rígida No Modelada: la fase (x0, y0) es una traslación pura; no se estima
       ni corrige una rotación de cuerpo rígido de la muestra respecto a los ejes de la
       cámara/platina. Una rotación de apenas 0.5-1° (tolerancia de montaje típica) puede
       inflar sigma_pos/gamma_lindemann de forma completamente espuria (confirmado
       numéricamente: ~20-100 nm de "desorden" fabricado a partir de rotación pura sin
       ruido real inyectado), y el efecto es proporcionalmente MAYOR cuanto más anisótropa
       es la red (a muy distinto de b). Si se sospecha una rotación de muestra, comparar
       contra `compute_quiver_and_strain`'s `omega` (que sí recupera el ángulo de rotación
       correctamente) antes de interpretar sigma_pos/gamma_lindemann como desorden real.

    Parámetros:
    -----------
    a : float
        Período de red nominal en X [nm].
    b : float, opcional
        Período de red nominal en Y [nm]. Si es None, se asume red isótropa (b = a).
    n_side_x, n_side_y : int, opcional
        Número de sitios nominales por eje. Si son None, se usa `n_side` (retrocompatibilidad)
        o se estima automáticamente a partir del span de datos.
    n_side : int, opcional
        Retrocompatibilidad: número de sitios por lado para redes cuadradas.
    """
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    M = len(x)
    if M == 0:
        raise ValueError("No hay coordenadas para analizar en espacio real.")

    b_val = float(b) if b is not None else float(a)

    # Estimar dimensiones de la red si no fueron provistas
    if n_side_x is None or n_side_x <= 0:
        if n_side is not None and n_side > 0:
            n_side_x = int(n_side)
        else:
            n_side_x = max(2, int(np.round(float(np.ptp(x)) / a)) + 1)
    if n_side_y is None or n_side_y <= 0:
        if n_side is not None and n_side > 0:
            n_side_y = int(n_side)
        else:
            n_side_y = max(2, int(np.round(float(np.ptp(y)) / b_val)) + 1)

    n_side_x = int(n_side_x)
    n_side_y = int(n_side_y)

    # 1. Estimación de Fase de Red Desacoplada (Media Circular de Fourier)
    # Encuentra la traslación exacta (x0, y0) del cristal independientemente
    # de si n_side_x/n_side_y son pares o impares, o de si la red está descentrada.
    x0 = (a / (2.0 * np.pi)) * float(np.angle(np.sum(np.exp(2j * np.pi * x / a))))
    y0 = (b_val / (2.0 * np.pi)) * float(np.angle(np.sum(np.exp(2j * np.pi * y / b_val))))

    # 2. Asignación de índices enteros de nodo (ix, iy) para cada partícula
    ix = np.round((x - x0) / a).astype(int)
    iy = np.round((y - y0) / b_val).astype(int)

    # Posición ideal del nodo más cercano para cada partícula
    x_ideal = x0 + ix * a
    y_ideal = y0 + iy * b_val

    # Residuos cartesianos y cota elipsoidal normalizada (bounded)
    d_x = x - x_ideal
    d_y = y - y_ideal
    dist_norm_sq = (d_x / a) ** 2 + (d_y / b_val) ** 2

    # Cota estricta: sólo considerar partículas dentro de la elipse normalizada de radio 0.5
    valid_mask = dist_norm_sq < 0.25
    valid_dx = d_x[valid_mask]
    valid_dy = d_y[valid_mask]

    # Desorden posicional cartesiano no-sesgado
    sigma_x = float(np.std(valid_dx, ddof=1)) if len(valid_dx) > 1 else 0.0
    sigma_y = float(np.std(valid_dy, ddof=1)) if len(valid_dy) > 1 else 0.0
    sigma_pos = float(np.sqrt((sigma_x ** 2 + sigma_y ** 2) / 2.0))

    # Parámetro de Lindemann: gamma_L = sigma_pos / min(a, b)
    # Parámetro de Lindemann combinado (mezcla sigma_pos isotrópico con el período más corto:
    # válido bajo desorden isotrópico; ver gamma_lindemann_x/y para el criterio por eje).
    gamma_lindemann = float(sigma_pos / min(a, b_val)) if min(a, b_val) > 1e-9 else 0.0
    gamma_lindemann_x = float(sigma_x / a) if a > 1e-9 else 0.0
    gamma_lindemann_y = float(sigma_y / b_val) if b_val > 1e-9 else 0.0

    # Orden Traslacional Real (Psi_T): fase de Bragg promediada sobre partículas válidas
    if len(valid_dx) > 0:
        x_valid_pts = x[valid_mask]
        y_valid_pts = y[valid_mask]
        psi_t_x = float(np.abs(np.mean(np.exp(2j * np.pi * x_valid_pts / a))))
        psi_t_y = float(np.abs(np.mean(np.exp(2j * np.pi * y_valid_pts / b_val))))
    else:
        psi_t_x = 0.0
        psi_t_y = 0.0

    # 3. Detección de Vacancias mediante Maximización Convolutiva 2D de Ocupación
    valid_ix = ix[valid_mask]
    valid_iy = iy[valid_mask]

    if len(valid_ix) > 0:
        min_ix, max_ix, min_iy, max_iy = find_optimal_grid_bounding_box(valid_ix, valid_iy, n_side_x, n_side_y)

        all_grid_coords = [
            (i, j) for i in range(min_ix, max_ix + 1) for j in range(min_iy, max_iy + 1)
        ]
        grid_set = set(all_grid_coords)

        # Partículas válidas que caen dentro de la grilla nominal óptima
        occupied_in_grid = set(
            (i, j) for i, j in zip(valid_ix, valid_iy) if (i, j) in grid_set
        )
        vacant_indices = [pt for pt in all_grid_coords if pt not in occupied_in_grid]

        # Partículas totales dentro vs fuera de la grilla
        in_grid_mask = np.array([(i, j) in grid_set for i, j in zip(ix, iy)], dtype=bool)
        particles_in_grid = int(np.sum(in_grid_mask))
        particles_outside_grid = int(M - particles_in_grid)

        # Detección de sobreposiciones (múltiples partículas en el mismo nodo)
        multi_occupied_count = int(np.sum(valid_mask & in_grid_mask) - len(occupied_in_grid))

        grid_points = np.array([[x0 + i * a, y0 + j * b_val] for i, j in all_grid_coords], dtype=np.float64)
        vacant_points = np.array([[x0 + i * a, y0 + j * b_val] for i, j in vacant_indices], dtype=np.float64) if vacant_indices else np.empty((0, 2))
        matched_grid_points = np.column_stack([x_ideal[valid_mask], y_ideal[valid_mask]])
        valid_data = np.column_stack([x[valid_mask], y[valid_mask]])

        N_total_sites = len(all_grid_coords)
        matched_count = len(occupied_in_grid)

        # 1. Vacancias Teóricas (Celdas Vacías en la Grilla Óptima Bounded)
        n_vac_teor = len(vacant_indices)
        f_vac_teor = float(n_vac_teor / N_total_sites) if N_total_sites > 0 else 0.0

        # 2. Vacancias Prácticas (Canónicas: Muestra dentro de ROI curada)
        # N_partículas_en_grilla = M (partículas activas dentro del ROI post-curación)
        n_vac_prac = max(0, N_total_sites - M)
        f_vac_prac = float(n_vac_prac / N_total_sites) if N_total_sites > 0 else 0.0

        # REGLA OBLIGATORIA: Asignar f_vac a las vacancias prácticas para todos los cálculos posteriores
        f_vac = f_vac_prac
        n_vac = n_vac_prac
    else:
        min_ix, max_ix, min_iy, max_iy = 0, n_side_x - 1, 0, n_side_y - 1
        grid_points = np.empty((0, 2))
        vacant_points = np.empty((0, 2))
        matched_grid_points = np.empty((0, 2))
        valid_data = np.empty((0, 2))
        N_total_sites = (n_side_x * n_side_y) if (n_side_x and n_side_y) else 0
        matched_count = 0
        n_vac_teor = N_total_sites
        f_vac_teor = 1.0
        n_vac_prac = max(0, N_total_sites - M)
        f_vac_prac = float(n_vac_prac / N_total_sites) if N_total_sites > 0 else 1.0
        n_vac = n_vac_prac
        f_vac = f_vac_prac
        particles_in_grid = 0
        particles_outside_grid = M
        multi_occupied_count = 0

    # Relación de partículas detectadas sobre sitios totales nominales
    detection_ratio = float(M / N_total_sites) if N_total_sites > 0 else 0.0
    excess_particles = bool(M > N_total_sites)

    # Verificación de consistencia física y metrológica: M + n_vac <= N_total_sites * (1 + margin_percent / 100)
    margin_factor = 1.0 + (margin_percent / 100.0)
    max_allowed = int(np.ceil(np.round(N_total_sites * margin_factor, 6))) if N_total_sites > 0 else 0
    consistency_sum = M + n_vac
    consistency_ok = bool(consistency_sum <= max_allowed)
    consistency_margin_ratio = float(consistency_sum / N_total_sites) if N_total_sites > 0 else 0.0

    consistency_msg = (
        f"Consistencia: Detectadas ({M}) + Vacancias ({n_vac}) = {consistency_sum} / {N_total_sites} "
        f"({consistency_margin_ratio:.2f} <= {margin_factor:.2f} [OK])"
    ) if consistency_ok else (
        f"[ALERTA] Consistencia: Detectadas ({M}) + Vacancias ({n_vac}) = {consistency_sum} > {max_allowed} "
        f"({consistency_margin_ratio:.2f} > {margin_factor:.2f}). "
        f"Hay {particles_outside_grid} fuera de grilla y {multi_occupied_count} sobreposiciones no depuradas."
    )

    excess_alert = (
        f"[ALERTA] Partículas detectadas ({M}) > Sitios nominales ({N_total_sites}). "
        f"Relación = {detection_ratio:.2f} > 1.0. "
        "Depure manualmente las partículas espurias o resuelva los aglomerados detectados."
    ) if excess_particles else ""

    return {
        'n_side': n_side_x,
        'n_side_x': n_side_x,
        'n_side_y': n_side_y,
        'a': float(a),
        'b': b_val,
        'is_anisotropic': bool(abs(float(a) - b_val) > 1e-6),
        'gamma_lindemann': gamma_lindemann,
        'gamma_lindemann_x': gamma_lindemann_x,
        'gamma_lindemann_y': gamma_lindemann_y,
        'psi_t_x': psi_t_x,
        'psi_t_y': psi_t_y,
        'N_total_sites': N_total_sites,
        'particles_detected': M,
        'particles_in_grid': particles_in_grid,
        'particles_outside_grid': particles_outside_grid,
        'multi_occupied_count': multi_occupied_count,
        'matched_count': matched_count,
        'N_occupied_sites': matched_count,
        'vacant_count': n_vac_prac,
        'n_vac_prac': n_vac_prac,
        'f_vac_prac': f_vac_prac,
        'f_vac_prac_percent': f_vac_prac * 100.0,
        'n_vac_teor': n_vac_teor,
        'f_vac_teor': f_vac_teor,
        'f_vac_teor_percent': f_vac_teor * 100.0,
        'f_vac': f_vac_prac,
        'f_vac_percent': f_vac_prac * 100.0,
        'detection_ratio': detection_ratio,
        'excess_particles': excess_particles,
        'excess_alert': excess_alert,
        'margin_percent': margin_percent,
        'consistency_ok': consistency_ok,
        'consistency_msg': consistency_msg,
        'consistency_sum': consistency_sum,
        'consistency_margin_ratio': consistency_margin_ratio,
        'max_allowed_particles': max_allowed,
        'min_ix': min_ix,
        'max_ix': max_ix,
        'min_iy': min_iy,
        'max_iy': max_iy,
        'x0': x0,
        'y0': y0,
        'sigma_x': sigma_x,
        'sigma_y': sigma_y,
        'sigma_pos': sigma_pos,
        'delta_x': valid_dx,
        'delta_y': valid_dy,
        'grid_points': grid_points,
        'vacant_points': vacant_points,
        'matched_grid_points': matched_grid_points,
        'matched_data_points': valid_data,
        'x_ideal': x_ideal,
        'y_ideal': y_ideal,
        'valid_mask': valid_mask,
        'ix': ix,
        'iy': iy
    }


# ==============================================================================
# 2.5 CRISTALOGRAFÍA EN ESPACIO REAL: ORDEN ORIENTACIONAL, TOPOLOGÍA
#     VORONOI/DELAUNAY Y CAMPO DE DEFORMACIÓN (QUIVER + STRAIN TENSOR)
# ==============================================================================

def compute_bond_orientational_order(
    x: np.ndarray,
    y: np.ndarray,
    k_neighbors: int = 4,
    lattice_type: str = 'rectangular',
    n_fold: Optional[int] = None
) -> Dict[str, Any]:
    """
    Calcula el orden orientacional de enlace (bond-orientational order) psi_4 y psi_6
    a partir de la triangulación de Delaunay de las posiciones (x, y):

        psi_n(j) = (1 / Z_j) * sum_{k=1}^{Z_j} exp(i * n * theta_jk)

    donde theta_jk = atan2(y_k - y_j, x_k - x_j) y Z_j es el número de vecinos de
    Delaunay de la partícula j. |psi_n| -> 1 indica orden perfecto local de simetría
    n-fold; |psi_n| -> 0 indica desorden orientacional total.

    Nota de Implementación (Degeneración de Delaunay en Redes Cuadradas/Rectangulares):
    La triangulación de Delaunay de una red cuadrada perfecta es geométricamente
    degenerada (4 puntos cocirculares por celda unitaria), lo que introduce aristas
    diagonales espurias de forma arbitraria y subestima psi_4 en ~50%. Se mitiga
    restringiendo, para cada partícula, los `k_neighbors` vecinos MÁS CERCANOS por
    distancia euclidiana (kNN vía cKDTree, no la lista de adyacencia de Delaunay),
    el estándar práctico de la literatura para bond-orientational order sobre redes
    de Bravais. Vectorizado: una sola consulta cKDTree.query(k=k_neighbors+1) sobre
    todas las partículas a la vez (~30x más rápido que un bucle Python por partícula).

    Nota Metrológica sobre `coordination`: al usar kNN de grado fijo, `coordination`
    es simplemente `k_neighbors` para toda partícula con al menos esa cantidad de
    vecinos (constante, no informativo de defectos topológicos reales). NO usar este
    campo para detectar vacancias/dislocaciones — para el número de coordinación
    topológico real (que sí varía en bordes y defectos), usar compute_voronoi_topology.

    Parámetros:
    -----------
    k_neighbors : int
        Número de vecinos más cercanos considerados por partícula para promediar
        psi_n. Por defecto 4 (red rectangular/cuadrada).
    lattice_type : str
        Etiqueta descriptiva de la simetría nominal de la red ('rectangular', 'hexagonal', ...).
    n_fold : int, opcional
        Si se especifica, calcula ADEMÁS el orden orientacional genérico psi_n (p.ej.
        n_fold=3 para el orden de enlace local de una red honeycomb, cuya simetría de
        enlace fundamental es 3-fold, no 4 ni 6-fold), bajo las claves psi_n_local/
        psi_n_mean/psi_n_phase_mean. psi4/psi6 siempre se calculan (retrocompatibilidad).
    """
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    N = len(x)
    k_cap = max(1, int(k_neighbors))

    if N < k_cap + 1:
        empty_result = {
            'psi4_local': np.zeros(N),
            'psi6_local': np.zeros(N),
            'psi4_mean': 0.0,
            'psi6_mean': 0.0,
            'psi4_phase_mean': 0.0,
            'psi6_phase_mean': 0.0,
            'coordination': np.zeros(N, dtype=int),
            'k_neighbors': k_neighbors,
            'lattice_type': lattice_type
        }
        if n_fold is not None:
            empty_result.update({
                'psi_n_local': np.zeros(N), 'psi_n_mean': 0.0,
                'psi_n_phase_mean': 0.0, 'n_fold': int(n_fold)
            })
        return empty_result

    points = np.column_stack([x, y])
    tree = cKDTree(points)
    _, neighbor_idx_full = tree.query(points, k=k_cap + 1)
    neighbor_idx = neighbor_idx_full[:, 1:]  # columna 0 es la propia partícula (dist=0)

    dxj = x[neighbor_idx] - x[:, None]
    dyj = y[neighbor_idx] - y[:, None]
    theta = np.arctan2(dyj, dxj)
    psi4_local = np.mean(np.exp(1j * 4.0 * theta), axis=1)
    psi6_local = np.mean(np.exp(1j * 6.0 * theta), axis=1)
    coordination = np.full(N, k_cap, dtype=int)

    result = {
        'psi4_local': np.abs(psi4_local),
        'psi6_local': np.abs(psi6_local),
        'psi4_local_complex': psi4_local,
        'psi6_local_complex': psi6_local,
        'psi4_mean': float(np.mean(np.abs(psi4_local))),
        'psi6_mean': float(np.mean(np.abs(psi6_local))),
        'psi4_phase_mean': float(np.angle(np.mean(psi4_local))),
        'psi6_phase_mean': float(np.angle(np.mean(psi6_local))),
        'coordination': coordination,
        'k_neighbors': k_neighbors,
        'lattice_type': lattice_type
    }

    if n_fold is not None:
        psi_n_local = np.mean(np.exp(1j * float(n_fold) * theta), axis=1)
        result.update({
            'psi_n_local': np.abs(psi_n_local),
            'psi_n_local_complex': psi_n_local,
            'psi_n_mean': float(np.mean(np.abs(psi_n_local))),
            'psi_n_phase_mean': float(np.angle(np.mean(psi_n_local))),
            'n_fold': int(n_fold)
        })

    return result


def _merge_close_polygon_vertices_xy(vx: list, vy: list, tol: float) -> int:
    """
    Cuenta los vértices de un polígono cerrado (listas Python planas, no ndarray:
    evita el overhead de dispatch de ufunc de NumPy sobre arreglos de 4-8 elementos)
    tras fusionar los consecutivos separados por menos de `tol`, colapsando los grupos
    numéricamente degenerados (ver nota en compute_voronoi_topology). Retorna sólo el
    conteo final (coordinación Z), que es todo lo que compute_voronoi_topology necesita.

    Implementación (invariante topológico de grafo cíclico, no un barrido secuencial
    con semilla fija): los k vértices forman un ciclo; se cuenta el número de aristas
    consecutivas (incluyendo el cierre k-1 -> 0) cuya longitud excede `tol` ("aristas
    reales"). Ese conteo es exactamente el número de vértices tras contraer cada arista
    corta, sin importar en qué índice del arreglo empiece o termine un grupo degenerado.
    Un barrido secuencial ingenuo con semilla en vertices[0] (versión previa de esta
    función) falla cuando un grupo degenerado de 3+ vértices cruza el límite de cierre
    del arreglo (índice k-1 -> 0): se detectó que esto ocurre con frecuencia real en
    redes honeycomb (no sólo como caso patológico raro), donde produjo Z=4 espurio en
    ~50% de las celdas internas bajo ruido posicional moderado (~3% del enlace) en vez
    del Z=3 correcto — ver DEC-012.
    """
    k = len(vx)
    if k <= 3 or tol <= 0.0:
        return k
    n_far_edges = 0
    for j in range(k):
        j2 = (j + 1) % k
        if math.hypot(vx[j] - vx[j2], vy[j] - vy[j2]) > tol:
            n_far_edges += 1
    return max(1, n_far_edges)


def compute_voronoi_topology(
    x: np.ndarray,
    y: np.ndarray,
    x_range: Optional[Tuple[float, float]] = None,
    y_range: Optional[Tuple[float, float]] = None,
    ideal_z: int = 4
) -> Dict[str, Any]:
    """
    Calcula la teselación de Voronoi de las posiciones (x, y) y determina el número
    de coordinación Z_j (lados del polígono) de cada partícula interna, identificando
    defectos topológicos (Z != ideal_z). ideal_z por defecto es 4 (red cuadrada/
    rectangular, defectos típicos en pares 3-5); usar ideal_z=6 para redes
    hexagonales/triangulares o ideal_z=3 para redes honeycomb (verificado
    numéricamente: la coordinación geométrica de Voronoi de un sitio honeycomb es 3,
    dominada por sus 3 vecinos de enlace, mucho más cercanos que el segundo anillo
    de la misma subred — no confundir con la coordinación de enlace química, que
    también es 3 mediante compute_bond_orientational_order, pero es un cálculo
    geométricamente independiente).

    Las celdas de borde (con vértices en el infinito, region=[-1, ...], o vértices fuera
    de [x_range, y_range]) se excluyen del cómputo de coordinación y de la fracción de
    defectos, ya que su geometría trunca artificialmente el conteo de lados.

    Nota de Implementación (Degeneración Numérica de Vértices en Redes Cuadradas/Rectangulares):
    En una red cuadrada/rectangular perfecta, 4 partículas son exactamente cocirculares en
    cada vértice de Voronoi (degeneración geométrica). Cualquier desorden posicional real
    (incluso sub-nanométrico) rompe la degeneración y separa ese vértice único en 2-3 vértices
    casi coincidentes, inflando espuriamente Z de 4 a 6-8. Se mitiga fusionando, para cada
    celda, los vértices consecutivos separados por menos del 10% de la distancia mediana al
    vecino más cercano del conjunto completo de partículas (escala física característica de
    la red, independiente de la geometría particular de cada celda).
    """
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    N = len(x)

    if N < 4:
        return {
            'coordination': np.zeros(N, dtype=int),
            'is_internal': np.zeros(N, dtype=bool),
            'defects_mask': np.zeros(N, dtype=bool),
            'n_internal': 0,
            'n_defects': 0,
            'f_defects': 0.0,
            'cell_areas': np.full(N, np.nan),
            'area_mean': 0.0,
            'area_std': 0.0,
            'area_cv': 0.0,
            'vor': None
        }

    points = np.column_stack([x, y])
    vor = Voronoi(points)

    # Escala física característica: distancia mediana al vecino más cercano
    nn_tree = cKDTree(points)
    nn_dist, _ = nn_tree.query(points, k=2)
    median_nn_dist = float(np.median(nn_dist[:, 1])) if N > 1 else 1.0
    # 20% (no 10%): calibrado empíricamente contra redes honeycomb, cuyas celdas
    # triangulares (3 vecinos, menos redundancia geométrica que las 4-8 restricciones
    # de una celda cuadrada) amplifican más el desplazamiento del vértice de Voronoi
    # por unidad de ruido posicional. 10% dejaba sin fusionar ~40-50% de los vértices
    # degenerados honeycomb bajo ruido moderado (~3% del enlace); 20% los resuelve sin
    # ocultar el defecto real de la prueba de regresión de vacancia (ver DEC-012).
    vertex_merge_tol = 0.20 * median_nn_dist

    x_lo, x_hi = x_range if x_range is not None else (float(np.min(x)), float(np.max(x)))
    y_lo, y_hi = y_range if y_range is not None else (float(np.min(y)), float(np.max(y)))

    coordination = np.zeros(N, dtype=int)
    is_internal = np.zeros(N, dtype=bool)
    cell_areas = np.full(N, np.nan)

    for i, region_index in enumerate(vor.point_region):
        region = vor.regions[region_index]
        if not region or -1 in region:
            continue  # Celda de borde con vértice(s) en el infinito

        vertices = vor.vertices[region]
        vx_arr, vy_arr = vertices[:, 0], vertices[:, 1]
        if vx_arr.min() < x_lo or vx_arr.max() > x_hi or vy_arr.min() < y_lo or vy_arr.max() > y_hi:
            continue

        is_internal[i] = True
        vx_l = vx_arr.tolist()
        vy_l = vy_arr.tolist()
        coordination[i] = _merge_close_polygon_vertices_xy(vx_l, vy_l, vertex_merge_tol)

        # Fórmula del área de Gauss (shoelace) sobre listas planas de Python: evita el
        # overhead de dispatch de np.roll/np.any sobre arreglos diminutos (4-8 elementos)
        k = len(vx_l)
        area_sum = 0.0
        for j in range(k):
            j2 = j + 1 if j + 1 < k else 0
            area_sum += vx_l[j] * vy_l[j2] - vx_l[j2] * vy_l[j]
        cell_areas[i] = 0.5 * abs(area_sum)

    defects_mask = is_internal & (coordination != ideal_z)
    n_internal = int(np.sum(is_internal))
    n_defects = int(np.sum(defects_mask))
    f_defects = float(n_defects / n_internal) if n_internal > 0 else 0.0

    valid_areas = cell_areas[is_internal]
    area_mean = float(np.mean(valid_areas)) if len(valid_areas) > 0 else 0.0
    area_std = float(np.std(valid_areas, ddof=1)) if len(valid_areas) > 1 else 0.0
    area_cv = float(area_std / area_mean) if area_mean > 1e-9 else 0.0

    return {
        'coordination': coordination,
        'ideal_z': ideal_z,
        'is_internal': is_internal,
        'defects_mask': defects_mask,
        'n_internal': n_internal,
        'n_defects': n_defects,
        'f_defects': f_defects,
        'cell_areas': cell_areas,
        'area_mean': area_mean,
        'area_std': area_std,
        'area_cv': area_cv,
        'vor': vor
    }


def compute_quiver_and_strain(
    x: np.ndarray,
    y: np.ndarray,
    x_ideal: np.ndarray,
    y_ideal: np.ndarray,
    valid_mask: np.ndarray
) -> Dict[str, Any]:
    """
    Retorna los vectores de desplazamiento (Delta x, Delta y) = (x - x_ideal, y - y_ideal)
    para graficar con Quiver, y ajusta por mínimos cuadrados una deformación afín:

        [Delta x]   [ exx        exy - omega ] [x_ideal]   [tx]
        [Delta y] = [ exy + omega   eyy       ] [y_ideal] + [ty]

    donde omega es la rotación de cuerpo rígido y exx, eyy, exy son las componentes
    del tensor de deformación (strain).

    Nota (Alcance Global, no Local): el ajuste se realiza sobre TODA la población de
    partículas válidas simultáneamente, produciendo un único tensor de deformación
    afín GLOBAL para el campo completo (apto para deriva de platina, calibración
    a/b, o distorsión de campo de lente). No es un mapa de deformación LOCAL: bajo
    desorden local no-correlacionado (térmico/de fabricación) con media nula, el
    ajuste converge a exx=eyy=exy=omega=0 aunque exista heterogeneidad de
    deformación real concentrada en defectos puntuales (vacancias, dislocaciones),
    que se promedia y desaparece en este ajuste de un solo tensor global.
    """
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    x_ideal = np.asarray(x_ideal, dtype=np.float64)
    y_ideal = np.asarray(y_ideal, dtype=np.float64)
    valid_mask = np.asarray(valid_mask, dtype=bool)

    dx = (x - x_ideal)[valid_mask]
    dy = (y - y_ideal)[valid_mask]
    xi = x_ideal[valid_mask]
    yi = y_ideal[valid_mask]
    n_valid = len(xi)

    if n_valid < 4:
        return {
            'dx': dx, 'dy': dy, 'x_ideal': xi, 'y_ideal': yi,
            'exx': 0.0, 'eyy': 0.0, 'exy': 0.0, 'omega': 0.0,
            'tx': 0.0, 'ty': 0.0, 'success': False
        }

    design_matrix = np.column_stack([xi, yi, np.ones(n_valid)])
    try:
        coef_x, _, _, _ = np.linalg.lstsq(design_matrix, dx, rcond=None)
        coef_y, _, _, _ = np.linalg.lstsq(design_matrix, dy, rcond=None)
        a11, a12, tx = coef_x
        a21, a22, ty = coef_y
        exx = float(a11)
        eyy = float(a22)
        exy = float((a12 + a21) / 2.0)
        omega = float((a21 - a12) / 2.0)
        success = True
    except Exception:
        exx = eyy = exy = omega = 0.0
        tx = ty = 0.0
        success = False

    return {
        'dx': dx, 'dy': dy, 'x_ideal': xi, 'y_ideal': yi,
        'exx': exx, 'eyy': eyy, 'exy': exy, 'omega': omega,
        'tx': float(tx), 'ty': float(ty), 'success': success
    }


# ==============================================================================
# 2.6 GENERALIZACIÓN CRISTALOGRÁFICA UNIVERSAL: TEMPLATE MATCHING PARA REDES
#     HEXAGONALES, HONEYCOMB Y GEOMETRÍAS COMPLEJAS (FASE 2)
# ==============================================================================
#
# Puente hacia core/lattice_generator.py (CrystalGridComposer/LatticeLayer/BasisAtom/
# BoundingGeometry): en vez de reimplementar la expansión de celdas, rotación,
# recorte por geometría envolvente y ordenamiento de trayectoria, este módulo
# reutiliza el motor cristalográfico ya validado del diseñador de redes, y añade
# el registro rígido (traslación + rotación) + emparejamiento KDTree con
# desacoplamiento de subredes necesario para el ANÁLISIS de muestras reales
# (a diferencia del diseñador, que sólo GENERA la plantilla ideal).
#
# Nota de Hallazgo (Corrección de Base Honeycomb — ver DEC-012):
# core/lattice_generator.py::LatticeLayer._default_basis_for_type() define la base
# honeycomb/graphene con coordenadas fraccionales u=1/3, v=2/3. Combinada con
# gamma_deg=60° (la convención que grid_generator.py aplica automáticamente a
# redes hexagonales/honeycomb), esto NO produce una coordinación de enlace de 3
# vecinos equidistantes: se verificó numéricamente que genera 4 distancias de
# enlace distintas (0.2a, 0.4a, 0.529a x2) en el primer vecindario, en vez de la
# geometría honeycomb correcta (exactamente 3 vecinos B a d = a/sqrt(3), luego 3
# vecinos A a d = a). La base fraccional correcta para esta convención de a1/a2
# (gamma=60°) es u=1/3, v=1/3 (verificado numéricamente: reproduce 3 vecinos
# equidistantes a a/sqrt(3) exactamente). Esta función usa la base corregida
# LOCALMENTE (sin modificar core/lattice_generator.py, fuera de alcance de esta
# misión) — se recomienda corregir el generador en un follow-up, dado que
# CrystalGridComposer también se usa para fabricar muestras reales vía
# grid_generator.py, y el defecto geométrico afectaría la red honeycomb impresa.

_HEXAGONAL_LATTICE_TYPES = ('hexagonal', 'triangular')
_HONEYCOMB_LATTICE_TYPES = ('honeycomb', 'graphene')
_LATTICE_TYPE_TO_GENERATOR = {
    'square': 'square',
    'rectangular': 'rectangular',
    'hexagonal': 'hexagonal',
    'triangular': 'hexagonal',
    'honeycomb': 'graphene',
    'graphene': 'graphene',
}


def _ideal_voronoi_coordination_for_type(lattice_type: str) -> int:
    """Coordinación geométrica de Voronoi ideal (número de lados de celda) esperada
    para cada familia de red, verificada numéricamente en redes sintéticas sin
    ruido: 4 (cuadrada/rectangular), 6 (hexagonal/triangular), 3 (honeycomb —
    dominada por los 3 vecinos de enlace más cercanos, mucho más próximos que
    el segundo anillo de la misma subred)."""
    lt = lattice_type.lower().strip()
    if lt in _HEXAGONAL_LATTICE_TYPES:
        return 6
    if lt in _HONEYCOMB_LATTICE_TYPES:
        return 3
    return 4


def generate_ideal_lattice_template(
    lattice_type: str,
    a: float,
    b: Optional[float] = None,
    gamma_deg: Optional[float] = None,
    boundary_type: str = 'hexagon',
    boundary_size_nm: float = 5000.0,
    boundary_width_nm: Optional[float] = None,
    boundary_height_nm: Optional[float] = None,
    rotation_deg: float = 0.0,
    center_x_nm: float = 0.0,
    center_y_nm: float = 0.0,
    u2: float = 1.0 / 3.0,
    v2: float = 1.0 / 3.0
) -> Dict[str, Any]:
    """
    Genera una plantilla de red ideal en espacio real [nm] usando el motor
    CrystalGridComposer de core/lattice_generator.py, recortada por una geometría
    envolvente (hexágono, círculo o rectángulo), para servir de referencia de
    registro rígido (template matching) contra partículas detectadas
    experimentalmente.

    Parámetros:
    -----------
    lattice_type : str
        'square', 'rectangular', 'hexagonal'/'triangular' (base monoatómica,
        gamma=60°), 'honeycomb'/'graphene' (base biatómica, gamma=60°).
    a, b : float
        Período(s) de red nominal [nm]. Para redes hexagonales/honeycomb, b se
        fija a `a` (celda unitaria de Bravais monoclínica-hexagonal, b=a por
        definición) independientemente del valor pasado.
    gamma_deg : float, opcional
        Ángulo entre a1 y a2. Si es None: 60° para familias hexagonal/honeycomb,
        90° en caso contrario (misma convención que grid_generator.py).
    boundary_type : str
        'hexagon', 'circle' o 'rectangle'.
    boundary_size_nm : float
        Radio (hexágono/círculo) o lado (rectángulo, cuando boundary_width_nm/
        boundary_height_nm no se especifican) de la geometría envolvente [nm].
    boundary_width_nm, boundary_height_nm : float, opcional
        Ancho (Lx) y alto (Ly) independientes de la envolvente rectangular [nm],
        sólo con efecto cuando boundary_type es 'rectangle'/'rectangular'/'square'.
        Si se omiten, ambos caen por defecto a boundary_size_nm (comportamiento
        idéntico al previo, envolvente cuadrada). Nota: por convención heredada
        de BoundingGeometry.is_inside() (core/lattice_generator.py), 'lx'/'ly'
        son anchos totales (semi-extensión = lx/2), mientras que 'radius'
        (hexágono/círculo) ya es una semi-extensión directa — para el mismo
        boundary_size_nm, la envolvente rectangular por defecto abarca la mitad
        del alcance lineal de la hexagonal/circular. Esta inconsistencia es
        preexistente y no se corrige aquí para no alterar recortes de sesiones/
        presets guardados que ya usan la opción rectangular.
    rotation_deg, center_x_nm, center_y_nm : float
        Rotación global y desplazamiento del centro de la plantilla ideal.
    u2, v2 : float, opcional
        Coordenada fraccional del segundo átomo de la base honeycomb/grafeno
        (Subred B), relativa a los vectores primitivos a1/a2. Por defecto
        (1/3, 1/3) — convención de laboratorio confirmada por el usuario (no
        (1/3, 2/3), que es el valor histórico de
        `core/lattice_generator.py::LatticeLayer._default_basis_for_type`,
        usado por el diseñador `grid_generator.py` — ambos archivos quedan
        deliberadamente desacoplados por ahora: este puente siempre construye
        su propia base explícita en vez de heredar el default de esa clase).
        Sin efecto para familias no-honeycomb (monoatómicas).

        ADVERTENCIA (ver DEC-012): `BoundingGeometry.is_inside()` (core/lattice_generator.py)
        evalúa el contorno envolvente SIEMPRE centrado en el origen (0,0), incluso cuando la
        red se traslada vía `offset_x`/`offset_y` (aplicado a los puntos ANTES del recorte, no
        al contorno). Se verificó numéricamente que un `center_x_nm`/`center_y_nm` de apenas
        ~1 nm puede alinear accidentalmente una fila completa de una red hexagonal exactamente
        con el borde recto del contorno, volcándola entera adentro/afuera del recorte y
        produciendo una plantilla con un centroide real muy distinto del solicitado (cientos
        de nm de diferencia) y un conteo de nodos distinto. **No usar `center_x_nm`/`center_y_nm`
        para pre-centrar la plantilla antes de `register_and_match_template`** — esa función ya
        realiza su propia alineación de centroides internamente; generar siempre la plantilla
        en el origen (valores por defecto) para ese flujo de trabajo.
    """
    try:
        from core.lattice_generator import LatticeLayer, BasisAtom, CrystalGridComposer
    except ImportError as e:
        raise ImportError(f"No se pudo importar core.lattice_generator: {e}")

    ltype_key = lattice_type.lower().strip()
    mapped_type = _LATTICE_TYPE_TO_GENERATOR.get(ltype_key, ltype_key)
    is_hex_family = ltype_key in _HEXAGONAL_LATTICE_TYPES or ltype_key in _HONEYCOMB_LATTICE_TYPES

    if is_hex_family:
        b_val = float(a)  # celda unitaria hexagonal: b = a por definición
        gamma_val = 60.0 if gamma_deg is None else float(gamma_deg)
    else:
        b_val = float(b) if b is not None else float(a)
        gamma_val = 90.0 if gamma_deg is None else float(gamma_deg)

    a_um = float(a) / 1000.0
    b_um = float(b_val) / 1000.0

    layer_kwargs = dict(
        name='template', lattice_type=mapped_type, a=a_um, b=b_um, gamma_deg=gamma_val,
        rotation_deg=float(rotation_deg),
        offset_x=float(center_x_nm) / 1000.0, offset_y=float(center_y_nm) / 1000.0
    )
    if ltype_key in _HONEYCOMB_LATTICE_TYPES:
        # Base parametrizada por u2/v2 (ver docstring) — convención de
        # laboratorio por defecto (1/3, 1/3), editable desde la GUI (Paquete 11).
        layer_kwargs['atoms'] = [
            BasisAtom(u=0.0, v=0.0, material_id=1, label='Subred A'),
            BasisAtom(u=float(u2), v=float(v2), material_id=2, label='Subred B')
        ]
    layer = LatticeLayer(**layer_kwargs)

    boundary_key = boundary_type.lower().strip()
    size_um = float(boundary_size_nm) / 1000.0
    if boundary_key in ('hexagon', 'hexagonal'):
        bshape = 'hexagon'
        bparams = {'radius': size_um}
    elif boundary_key in ('circle', 'circular'):
        bshape = 'circle'
        bparams = {'radius': size_um}
    elif boundary_key in ('rectangle', 'rectangular', 'square'):
        bshape = 'rectangle'
        lx_um = float(boundary_width_nm if boundary_width_nm is not None else boundary_size_nm) / 1000.0
        ly_um = float(boundary_height_nm if boundary_height_nm is not None else boundary_size_nm) / 1000.0
        bparams = {'lx': lx_um, 'ly': ly_um}
    else:
        bshape = 'circle'
        bparams = {'radius': size_um}

    composer = CrystalGridComposer()
    composer.layers = [layer]
    composer.bounding_shape = bshape
    composer.bounding_params = bparams
    composer.anchor_config.enabled = False
    composer.min_distance_um = 0.0
    composer.collision_tolerance_um = 1e-6

    result = composer.generate()
    nodes = result.get('nodes', [])

    ideal_z = _ideal_voronoi_coordination_for_type(ltype_key)

    if len(nodes) == 0:
        return {
            'x': np.array([]), 'y': np.array([]), 'sublattice_id': np.array([], dtype=int),
            'sublattice_labels': {}, 'a_nm': float(a), 'b_nm': b_val, 'gamma_deg': gamma_val,
            'lattice_type': ltype_key, 'n_points': 0, 'ideal_voronoi_coordination': ideal_z,
            'boundary_type': bshape, 'boundary_size_nm': float(boundary_size_nm)
        }

    x_nm = np.array([n['x'] * 1000.0 for n in nodes], dtype=np.float64)
    y_nm = np.array([n['y'] * 1000.0 for n in nodes], dtype=np.float64)
    sublattice_id = np.array([n['material_id'] for n in nodes], dtype=int)

    sublattice_labels: Dict[int, str] = {}
    for n in nodes:
        sublattice_labels.setdefault(int(n['material_id']), n.get('label', f"Subred {n['material_id']}"))

    return {
        'x': x_nm, 'y': y_nm, 'sublattice_id': sublattice_id,
        'sublattice_labels': sublattice_labels,
        'a_nm': float(a), 'b_nm': b_val, 'gamma_deg': gamma_val,
        'lattice_type': ltype_key, 'n_points': len(nodes),
        'ideal_voronoi_coordination': ideal_z,
        'boundary_type': bshape, 'boundary_size_nm': float(boundary_size_nm)
    }


def register_and_match_template(
    x_real: np.ndarray,
    y_real: np.ndarray,
    template_x: np.ndarray,
    template_y: np.ndarray,
    template_sublattice: Optional[np.ndarray] = None,
    max_dist_nm: Optional[float] = None,
    auto_rotate: bool = True,
    initial_rotation_deg: float = 0.0,
    rotation_search_range_deg: float = 15.0,
    rotation_search_coarse_step_deg: float = 1.0,
    rotation_search_fine_step_deg: float = 0.05
) -> Dict[str, Any]:
    """
    Registro rígido (rotación + traslación) de una plantilla ideal contra
    coordenadas reales detectadas, mediante búsqueda de rotación en 2 etapas
    (gruesa -> fina) para evitar mínimos locales de emparejamiento con vecinos
    adyacentes (riesgo real ante desorientación angular de montaje de muestra,
    ~1-5°: un optimizador local ingenuo puede quedar atrapado en un múltiplo
    del ángulo entre vecinos en vez del ángulo verdadero de desalineación).
    Tras fijar la rotación óptima, empareja cada partícula real con su nodo de
    plantilla más cercano (cota `max_dist_nm`) y desacopla el resultado por
    subred (A/B) para redes con base poli-atómica (honeycomb).

    Parámetros:
    -----------
    template_sublattice : np.ndarray, opcional
        Etiqueta de subred (entero) de cada nodo de `template_x`/`template_y`.
        Si es None, se asume una única subred (red de Bravais monoatómica).
    max_dist_nm : float, opcional
        Cota de emparejamiento. Si es None, se usa 0.5x la distancia mediana
        al vecino más cercano dentro de la plantilla.
    rotation_search_range_deg, rotation_search_coarse_step_deg :
        Ventana y paso de la búsqueda gruesa (barrido exhaustivo, no gradiente,
        para no caer en mínimos locales periódicos).
    rotation_search_fine_step_deg :
        Paso de refinamiento fino alrededor del mejor candidato grueso.
    """
    x_real = np.asarray(x_real, dtype=np.float64)
    y_real = np.asarray(y_real, dtype=np.float64)
    template_x = np.asarray(template_x, dtype=np.float64)
    template_y = np.asarray(template_y, dtype=np.float64)
    M = len(x_real)
    N_t = len(template_x)

    if M == 0 or N_t == 0:
        raise ValueError("Se requieren coordenadas reales y de plantilla no vacías para el registro.")

    if template_sublattice is None:
        template_sublattice = np.ones(N_t, dtype=int)
    else:
        template_sublattice = np.asarray(template_sublattice, dtype=int)

    if N_t > 1:
        t_tree_tmp = cKDTree(np.column_stack([template_x, template_y]))
        nn_d, _ = t_tree_tmp.query(np.column_stack([template_x, template_y]), k=2)
        median_nn = float(np.median(nn_d[:, 1]))
    else:
        median_nn = 1.0

    if max_dist_nm is None:
        max_dist_nm = 0.5 * median_nn

    # 1. Alineación de centroides (estimación inicial de traslación)
    cx_real, cy_real = float(np.mean(x_real)), float(np.mean(y_real))
    cx_t0, cy_t0 = float(np.mean(template_x)), float(np.mean(template_y))
    tx0 = template_x - cx_t0
    ty0 = template_y - cy_t0

    def _residual_for_theta(theta_deg: float) -> float:
        th = np.radians(theta_deg)
        c, s = np.cos(th), np.sin(th)
        rx = tx0 * c - ty0 * s + cx_real
        ry = tx0 * s + ty0 * c + cy_real
        t_tree = cKDTree(np.column_stack([rx, ry]))
        d, _ = t_tree.query(np.column_stack([x_real, y_real]), k=1)
        # Recorte de outliers (aglomerados / partículas espurias) para que no dominen el objetivo
        d_clipped = np.minimum(d, median_nn)
        return float(np.mean(d_clipped ** 2))

    best_theta = float(initial_rotation_deg)
    rotation_search_curve = None
    if auto_rotate:
        coarse_thetas = np.arange(
            initial_rotation_deg - rotation_search_range_deg,
            initial_rotation_deg + rotation_search_range_deg + 1e-9,
            rotation_search_coarse_step_deg
        )
        coarse_residuals = np.array([_residual_for_theta(t) for t in coarse_thetas])
        best_coarse_theta = float(coarse_thetas[int(np.argmin(coarse_residuals))])

        fine_half_width = rotation_search_coarse_step_deg * 1.5
        fine_thetas = np.arange(
            best_coarse_theta - fine_half_width,
            best_coarse_theta + fine_half_width + 1e-9,
            rotation_search_fine_step_deg
        )
        fine_residuals = np.array([_residual_for_theta(t) for t in fine_thetas])
        best_theta = float(fine_thetas[int(np.argmin(fine_residuals))])

        rotation_search_curve = {'theta_deg': coarse_thetas, 'residual': coarse_residuals}

    # 2. Aplicar rotación + traslación óptimas a la plantilla completa
    th = np.radians(best_theta)
    c, s = np.cos(th), np.sin(th)
    reg_x = tx0 * c - ty0 * s + cx_real
    reg_y = tx0 * s + ty0 * c + cy_real

    # 3. Emparejamiento KDTree acotado: real -> plantilla más cercana
    t_tree = cKDTree(np.column_stack([reg_x, reg_y]))
    d_real_to_t, idx_real_to_t = t_tree.query(np.column_stack([x_real, y_real]), k=1)
    valid_mask = d_real_to_t < max_dist_nm

    x_ideal = np.where(valid_mask, reg_x[idx_real_to_t], np.nan)
    y_ideal = np.where(valid_mask, reg_y[idx_real_to_t], np.nan)
    sublattice_id_per_real = np.where(valid_mask, template_sublattice[idx_real_to_t], -1)

    delta_x = np.full(M, np.nan)
    delta_y = np.full(M, np.nan)
    delta_x[valid_mask] = x_real[valid_mask] - x_ideal[valid_mask]
    delta_y[valid_mask] = y_real[valid_mask] - y_ideal[valid_mask]

    valid_dx = delta_x[valid_mask]
    valid_dy = delta_y[valid_mask]
    sigma_x = float(np.std(valid_dx, ddof=1)) if len(valid_dx) > 1 else 0.0
    sigma_y = float(np.std(valid_dy, ddof=1)) if len(valid_dy) > 1 else 0.0
    sigma_pos = float(np.sqrt((sigma_x ** 2 + sigma_y ** 2) / 2.0))

    # Covarianza posicional 2x2 y elipticidad rotacionalmente invariante (autovalores),
    # usada como reemplazo simétrico-agnóstico de sigma_x/sigma_y para redes hex/honeycomb
    # (donde sigma_x/sigma_y individuales, medidos en el marco cartesiano de registro
    # rígido, carecen de significado físico al no existir periodicidad cartesiana).
    if len(valid_dx) > 1:
        cov_xy = float(np.cov(valid_dx, valid_dy, ddof=1)[0, 1])
        cov_matrix = np.array([[sigma_x ** 2, cov_xy], [cov_xy, sigma_y ** 2]])
        eigvals = np.linalg.eigvalsh(cov_matrix)
        lambda_min = float(max(eigvals[0], 0.0))
        lambda_max = float(max(eigvals[1], 1e-12))
        ellipticity = float(1.0 - lambda_min / lambda_max)
    else:
        cov_xy = 0.0
        lambda_min = 0.0
        lambda_max = 0.0
        ellipticity = 0.0

    # 4. Vacancias: nodos de plantilla sin partícula real emparejada (matching inverso)
    r_tree = cKDTree(np.column_stack([x_real, y_real]))
    d_t_to_real, _ = r_tree.query(np.column_stack([reg_x, reg_y]), k=1)
    template_matched_mask = d_t_to_real < max_dist_nm
    vacant_mask = ~template_matched_mask
    vacant_x = reg_x[vacant_mask]
    vacant_y = reg_y[vacant_mask]
    vacant_sublattice = template_sublattice[vacant_mask]

    n_vac_by_sublattice: Dict[int, int] = {}
    n_sites_by_sublattice: Dict[int, int] = {}
    for sub_id in np.unique(template_sublattice):
        n_sites_by_sublattice[int(sub_id)] = int(np.sum(template_sublattice == sub_id))
        n_vac_by_sublattice[int(sub_id)] = int(np.sum(vacant_sublattice == sub_id))

    return {
        'theta_fit_deg': best_theta,
        'centroid_shift_x_nm': cx_real - cx_t0,
        'centroid_shift_y_nm': cy_real - cy_t0,
        'x_ideal': x_ideal, 'y_ideal': y_ideal,
        'valid_mask': valid_mask,
        'sublattice_id': sublattice_id_per_real,
        'delta_x': delta_x, 'delta_y': delta_y,
        'sigma_x': sigma_x, 'sigma_y': sigma_y, 'sigma_pos': sigma_pos,
        'cov_xy': cov_xy, 'lambda_min': lambda_min, 'lambda_max': lambda_max, 'ellipticity': ellipticity,
        'matched_count': int(np.sum(valid_mask)),
        'particles_detected': M,
        'vacant_points': np.column_stack([vacant_x, vacant_y]) if len(vacant_x) > 0 else np.empty((0, 2)),
        'vacant_sublattice_id': vacant_sublattice,
        'n_vacancies_by_sublattice': n_vac_by_sublattice,
        'n_sites_by_sublattice': n_sites_by_sublattice,
        'n_vacancies_total': int(np.sum(vacant_mask)),
        'n_template_sites': N_t,
        'registered_template_x': reg_x, 'registered_template_y': reg_y,
        'rotation_search_curve': rotation_search_curve,
        'max_dist_nm': float(max_dist_nm),
        'median_nn_dist_nm': median_nn
    }


def compute_basis_structure_factor(
    Gx: np.ndarray,
    Gy: np.ndarray,
    sublattice_offsets_nm: List[Tuple[float, float]]
) -> np.ndarray:
    """
    Factor de estructura geométrico |F(G)|^2 = |sum_kappa exp(-i G . d_kappa)|^2 de
    una base de N_atomos por celda unidad, evaluado en vectores recíprocos (Gx, Gy)
    [rad/nm]. Predice qué órdenes de Bragg son geométricamente suprimidos por
    interferencia destructiva entre subredes, independientemente del desorden
    posicional (efecto puramente geométrico de la base, no del desorden térmico).

    Para honeycomb (2 átomos, offset relativo tau = d_B - d_A):
        F(G) = 1 + exp(-i G . tau)
    con d_A = (0,0) como origen de referencia.
    """
    Gx = np.asarray(Gx, dtype=np.float64)
    Gy = np.asarray(Gy, dtype=np.float64)
    F = np.zeros(Gx.shape, dtype=complex)
    for dx, dy in sublattice_offsets_nm:
        F = F + np.exp(-1j * (Gx * dx + Gy * dy))
    return np.abs(F) ** 2


def extract_angular_profile(
    S: np.ndarray,
    fx: np.ndarray,
    fy: np.ndarray,
    angle_deg: float,
    band_width_bins: int = 2
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Extrae el perfil 1D de S(fx, fy) a lo largo de una dirección angular arbitraria
    (0° = eje fx positivo, sentido antihorario), promediando una banda transversal
    de ancho `band_width_bins`. Generaliza extract_diagonal_profile (caso fijo 45°)
    a ángulos arbitrarios, necesario para los cortes de simetría hexagonal a
    0°, 60° y 120°.
    """
    n_bins_y, n_bins_x = S.shape
    iy_zero = int(np.argmin(np.abs(fy)))
    ix_zero = int(np.argmin(np.abs(fx)))
    theta = math.radians(angle_deg)
    cos_t, sin_t = math.cos(theta), math.sin(theta)

    df_x = float(fx[1] - fx[0]) if len(fx) > 1 else 1.0
    df_y = float(fy[1] - fy[0]) if len(fy) > 1 else 1.0

    f_max = float(min(np.max(np.abs(fx)), np.max(np.abs(fy))))
    n_r = max(2, min(n_bins_x, n_bins_y) // 2)
    r_vals = np.linspace(0.0, f_max, n_r)
    profile = np.zeros(n_r, dtype=np.float64)

    for idx, r in enumerate(r_vals):
        f_along_x = r * cos_t
        f_along_y = r * sin_t
        vals = []
        for k in range(-band_width_bins, band_width_bins + 1):
            fx_query = f_along_x - sin_t * k * df_x
            fy_query = f_along_y + cos_t * k * df_y
            ix = ix_zero + int(round(fx_query / df_x))
            iy = iy_zero + int(round(fy_query / df_y))
            if 0 <= ix < n_bins_x and 0 <= iy < n_bins_y:
                vals.append(S[iy, ix])
        profile[idx] = float(np.mean(vals)) if vals else 0.0

    return r_vals, profile


def extract_honeycomb_peak_profile_metrics(
    r_vals: np.ndarray,
    profile: np.ndarray,
    f_nominal: float,
    peak_search_rel_width: float = 0.15
) -> Dict[str, Any]:
    """
    Ajusta/caracteriza el pico localizado alrededor de f_nominal en un corte
    1D radial (r_vals, profile) -- salida de extract_angular_profile -- para
    poblar los "Unit Metrology Boxes" de la Pestaña 3 (misión Honeycomb, CAT-315
    §8.2): posición observada f_obs, altura neta H (sobre fondo local B), FWHM
    (búsqueda de cruces de medio-máximo dentro de la ventana de pico), longitud
    de coherencia xi=2*pi/FWHM, y SNR=H/sigma_ruido (ruido estimado FUERA de la
    ventana de pico).

    Ventana de búsqueda: [f_nominal*(1-peak_search_rel_width), f_nominal*(1+peak_search_rel_width)].
    Si la ventana no contiene puntos válidos, retorna métricas nulas (H=0,
    SNR=0) en vez de lanzar una excepción -- la GUI debe degradar sin fallar
    cuando el barrido de frecuencias no alcanza f_nominal (p.ej. f_max_factor
    insuficiente al calcular S(fx,fy)).
    """
    r_vals = np.asarray(r_vals, dtype=np.float64)
    profile = np.asarray(profile, dtype=np.float64)
    f_lo = f_nominal * (1.0 - peak_search_rel_width)
    f_hi = f_nominal * (1.0 + peak_search_rel_width)
    window_mask = (r_vals >= f_lo) & (r_vals <= f_hi)

    if not np.any(window_mask) or len(r_vals) < 3:
        return {
            'f_obs': float(f_nominal), 'f_nominal': float(f_nominal), 'strain_pct': 0.0,
            'H': 0.0, 'B': 0.0, 'SNR': 0.0, 'FWHM': 0.0, 'xi_um': 0.0
        }

    outside_mask = ~window_mask
    B = float(np.median(profile[outside_mask])) if np.any(outside_mask) else float(np.min(profile))
    noise_sigma = float(np.std(profile[outside_mask])) if np.sum(outside_mask) > 1 else max(1e-9, 0.1 * B)

    idx_window = np.where(window_mask)[0]
    peak_local_idx = int(idx_window[np.argmax(profile[idx_window])])
    f_obs = float(r_vals[peak_local_idx])
    peak_val = float(profile[peak_local_idx])
    H = max(0.0, peak_val - B)
    strain_pct = float(100.0 * (f_obs - f_nominal) / f_nominal) if f_nominal > 1e-12 else 0.0
    SNR = float(H / noise_sigma) if noise_sigma > 1e-12 else 0.0

    # FWHM: cruces de medio-máximo (sobre fondo B) buscando hacia afuera desde el pico.
    half_max = B + 0.5 * H
    df = float(r_vals[1] - r_vals[0]) if len(r_vals) > 1 else 0.0
    left_idx = peak_local_idx
    while left_idx > 0 and profile[left_idx] > half_max:
        left_idx -= 1
    right_idx = peak_local_idx
    while right_idx < len(profile) - 1 and profile[right_idx] > half_max:
        right_idx += 1
    FWHM = float((right_idx - left_idx) * df) if H > 1e-12 else 0.0
    xi_um = float((2.0 * np.pi / FWHM) / 1000.0) if FWHM > 1e-9 else 0.0  # r_vals en nm^-1 -> xi en um

    return {
        'f_obs': f_obs, 'f_nominal': float(f_nominal), 'strain_pct': strain_pct,
        'H': H, 'B': B, 'SNR': SNR, 'FWHM': FWHM, 'xi_um': xi_um
    }


def compute_radial_azimuthal_profile(
    S: np.ndarray,
    fx: np.ndarray,
    fy: np.ndarray,
    n_r_bins: int = 128
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Integra azimutalmente S(fx, fy): S(q) = (1/2*pi) * integral_0^(2*pi) S(q,theta) dtheta,
    vectorizado vía np.bincount (sin bucle Python sobre el ángulo). Útil para redes
    con mosaico angular significativo o muestras policristalinas donde los picos de
    Bragg discretos de una red hexagonal/honeycomb se combinan en anillos continuos.
    """
    FX, FY = np.meshgrid(fx, fy)
    R = np.sqrt(FX ** 2 + FY ** 2).ravel()
    S_flat = np.asarray(S, dtype=np.float64).ravel()

    f_max = float(min(np.max(np.abs(fx)), np.max(np.abs(fy))))
    r_edges = np.linspace(0.0, f_max, n_r_bins + 1)
    r_centers = (r_edges[:-1] + r_edges[1:]) / 2.0

    bin_idx = np.digitize(R, r_edges) - 1
    valid = (bin_idx >= 0) & (bin_idx < n_r_bins)
    sums = np.bincount(bin_idx[valid], weights=S_flat[valid], minlength=n_r_bins)
    counts = np.bincount(bin_idx[valid], minlength=n_r_bins)
    q_profile = np.divide(sums, counts, out=np.zeros(n_r_bins, dtype=np.float64), where=counts > 0)

    return r_centers, q_profile


def find_hexagonal_reciprocal_rotation(
    S: np.ndarray,
    fx: np.ndarray,
    fy: np.ndarray,
    a: float,
    angle_step_deg: float = 0.5,
    annulus_rel_width: float = 0.15
) -> Dict[str, Any]:
    """
    Solver azimutal automático de orientación para redes hexagonales/honeycomb:
    localiza el ángulo theta_peak (en [-30°, 30°)) donde cae el pico de Bragg
    de 1er orden en el espacio recíproco S(fx, fy), plegando la intensidad
    angular con simetría 6-fold: I_fold(theta) = sum_k I(theta + k*60°) para
    k=0..5, theta_peak = argmax I_fold(theta).

    Este ángulo es la orientación real del retículo RECÍPROCO (no del real
    espacio) — para usarlo como semilla desde el ángulo de registro rígido de
    Espacio Real (theta_fit_deg, Pestaña 2), debe restarse 30° primero (ver
    docstring de run_hexagonal_monte_carlo_calibration / DEC-012): el
    retículo recíproco de una red triangular con vectores primitivos reales
    a1=(a,0), a2=(a·cos60°, a·sin60°) está rotado -30° respecto al real.

    Nota honeycomb vs hexagonal (base biatómica): las 6 posiciones angulares
    de los picos de 1er orden son 6-fold simétricas para AMBAS familias (la
    posición depende sólo de la red de Bravais subyacente, no de la base) —
    el plegado de 60° usado aquí para *localizar* theta_peak es válido en
    ambos casos. Sin embargo, para honeycomb el factor de estructura de base
    F(G) = 1 + exp(-i·G·tau) rompe la equivalencia de INTENSIDAD entre G y -G
    (reduce la simetría de intensidad a 3-fold) salvo tau de alta simetría —
    por lo tanto I_fold (a diferencia de su argmax) no debe usarse como
    métrica de calidad/SNR comparable entre hexagonal y honeycomb.

    Retorna dict con 'theta_peak_deg', 'theta_base_deg' (grilla [-30,30)),
    'i_fold' (intensidad plegada, mismo eje que theta_base_deg), 'f0'.
    """
    f0 = 2.0 / (np.sqrt(3.0) * float(a))
    FX, FY = np.meshgrid(fx, fy)
    R = np.sqrt(FX ** 2 + FY ** 2)
    THETA = np.degrees(np.arctan2(FY, FX))  # rango (-180, 180]

    annulus_mask = (R >= f0 * (1.0 - annulus_rel_width)) & (R <= f0 * (1.0 + annulus_rel_width))

    n_bins_full = max(6, int(round(360.0 / angle_step_deg)))
    theta_edges = np.linspace(-180.0, 180.0, n_bins_full + 1)
    theta_centers = 0.5 * (theta_edges[:-1] + theta_edges[1:])

    bin_idx = np.digitize(THETA.ravel(), theta_edges) - 1
    bin_idx = np.clip(bin_idx, 0, n_bins_full - 1)
    valid = annulus_mask.ravel()
    S_flat = np.asarray(S, dtype=np.float64).ravel()
    sums = np.bincount(bin_idx[valid], weights=S_flat[valid], minlength=n_bins_full)
    counts = np.bincount(bin_idx[valid], minlength=n_bins_full)
    i_theta = np.divide(sums, counts, out=np.zeros(n_bins_full, dtype=np.float64), where=counts > 0)

    bins_per_60 = max(1, int(round(60.0 / angle_step_deg)))
    base_mask = (theta_centers >= -30.0) & (theta_centers < 30.0)
    base_idx = np.where(base_mask)[0]
    if len(base_idx) == 0:
        return {'theta_peak_deg': 0.0, 'theta_base_deg': np.array([]), 'i_fold': np.array([]), 'f0': f0}

    i_fold = np.zeros(len(base_idx), dtype=np.float64)
    for k in range(6):
        shifted_idx = (base_idx + k * bins_per_60) % n_bins_full
        i_fold += i_theta[shifted_idx]

    theta_base_deg = theta_centers[base_idx]
    theta_peak_deg = float(theta_base_deg[int(np.argmax(i_fold))])

    return {
        'theta_peak_deg': theta_peak_deg,
        'theta_base_deg': theta_base_deg,
        'i_fold': i_fold,
        'f0': f0
    }


def _honeycomb_basis_factor_sq(h: float, v: float, k: float, w: float) -> float:
    """|F_basis(G_hk)|^2 = 4*cos^2(pi*(h*u2 + k*v2)) para la base diatómica
    honeycomb (ver CAT-315 §4.2-4.3, §6.1). Para redes hexagonales/triangulares
    monoatómicas este factor es idénticamente 1 para todo (h,k) y no se usa."""
    return 4.0 * (math.cos(math.pi * (h * v + k * w)) ** 2)


def compute_hexagonal_bragg_indexing(
    S: np.ndarray,
    fx: np.ndarray,
    fy: np.ndarray,
    a: float,
    rotation_deg: float = 0.0,
    peak_search_rel_width: float = 0.15,
    lattice_type: str = 'hexagonal',
    u2: float = 1.0 / 3.0,
    v2: float = 1.0 / 3.0
) -> Dict[str, Any]:
    """
    Indexación de picos de Bragg hexagonales/honeycomb en S(fx, fy): busca la
    intensidad local máxima (misma técnica que compute_analytical_bragg_relations
    -- ventana circular de radio peak_search_rel_width*f0 alrededor de cada
    punto recíproco nominal) en las 3 direcciones principales del 1er shell
    (destructivo parcial en honeycomb, |F|^2=1) y las 3 direcciones ortogonales
    del 2do shell (constructivo total en honeycomb, |F|^2=4) — ver CAT-315:

        H_axis1   @   0°+rotation_deg,  radio f1 = 2/(sqrt(3)*a)   Miller (1,0)
        H_axis2   @  60°+rotation_deg,  radio f1                   Miller (1,1)
        H_axis3   @ 120°+rotation_deg,  radio f1                   Miller (0,1)
        H_2_axis1 @   0°+rotation_deg,  radio 2*f1  (2do armónico RADIAL, NO
                      el 2do "shell" -- son puntos recíprocos distintos)
        H_2_axis2 @  60°+rotation_deg,  radio 2*f1
        H_ortho1  @  90°+rotation_deg,  radio q_ortho=sqrt(3)*f1=2/a  Miller (1,2)
        H_ortho2  @  30°+rotation_deg,  radio q_ortho                Miller (2,1)
        H_ortho3  @ 150°+rotation_deg,  radio q_ortho                Miller (-1,1)
        (H_ortho es un alias de H_ortho1, retrocompatible con el Paquete D.3)

    Índices de Miller relativos a rotation_deg verificados analítica y
    numéricamente (b1 a azimut -30°, b2 a azimut +90° para rotación real 0°,
    ver find_hexagonal_reciprocal_rotation / CAT-308 §9.1).

    lattice_type : 'hexagonal'/'triangular' (monoatómica, |F|^2≡1 en todo G) o
        'honeycomb'/'graphene' (base diatómica, |F|^2=4cos^2(pi*(h*u2+k*v2))).
    u2, v2 : posición fraccional de la subred B (sólo con efecto en honeycomb;
        canónico 1/3, 1/3 -- ver CAT-315 §4.2, §6.1 para desplazamientos).

    `rotation_deg` debe ser el ángulo de rotación del retículo RECÍPROCO
    (spin_fourier_rotation en la GUI): rotation_deg+0° es, por construcción,
    la azimut de un pico de Bragg real (ver find_hexagonal_reciprocal_rotation).
    """
    ltype_key = lattice_type.lower().strip()
    is_honeycomb = ltype_key in ('honeycomb', 'graphene')

    f1 = 2.0 / (np.sqrt(3.0) * float(a))
    q_ortho = np.sqrt(3.0) * f1
    FX, FY = np.meshgrid(fx, fy)

    def _get_peak(target_fx: float, target_fy: float, radius: float) -> float:
        dist = np.sqrt((FX - target_fx) ** 2 + (FY - target_fy) ** 2)
        m = dist < radius
        return float(np.max(S[m])) if np.any(m) else 1e-6

    def _target_xy(angle_deg: float, radius: float) -> Tuple[float, float]:
        th = np.radians(angle_deg)
        return radius * np.cos(th), radius * np.sin(th)

    search_r1 = peak_search_rel_width * f1
    search_r2 = peak_search_rel_width * f1  # misma tolerancia angular relativa, radio absoluto distinto por punto

    ax1_x, ax1_y = _target_xy(0.0 + rotation_deg, f1)
    ax2_x, ax2_y = _target_xy(60.0 + rotation_deg, f1)
    ax3_x, ax3_y = _target_xy(120.0 + rotation_deg, f1)
    ax1_2_x, ax1_2_y = _target_xy(0.0 + rotation_deg, 2.0 * f1)
    ax2_2_x, ax2_2_y = _target_xy(60.0 + rotation_deg, 2.0 * f1)
    ortho1_x, ortho1_y = _target_xy(90.0 + rotation_deg, q_ortho)
    ortho2_x, ortho2_y = _target_xy(30.0 + rotation_deg, q_ortho)
    ortho3_x, ortho3_y = _target_xy(150.0 + rotation_deg, q_ortho)

    H_axis1 = _get_peak(ax1_x, ax1_y, search_r1)
    H_axis2 = _get_peak(ax2_x, ax2_y, search_r1)
    H_axis3 = _get_peak(ax3_x, ax3_y, search_r1)
    H_2_axis1 = _get_peak(ax1_2_x, ax1_2_y, search_r2)
    H_2_axis2 = _get_peak(ax2_2_x, ax2_2_y, search_r2)
    H_ortho1 = _get_peak(ortho1_x, ortho1_y, search_r2)
    H_ortho2 = _get_peak(ortho2_x, ortho2_y, search_r2)
    H_ortho3 = _get_peak(ortho3_x, ortho3_y, search_r2)
    H_ortho = H_ortho1  # alias retrocompatible (Paquete D.3)

    ratio_21_axis1 = float(H_2_axis1 / H_axis1) if H_axis1 > 1e-9 else 0.0
    ratio_21_axis2 = float(H_2_axis2 / H_axis2) if H_axis2 > 1e-9 else 0.0
    denom = np.sqrt(max(H_axis1, 1e-9) * max(H_axis2, 1e-9))
    ratio_ortho = float(H_ortho / denom) if denom > 1e-9 else 0.0
    ratio_60_0 = float(H_axis2 / H_axis1) if H_axis1 > 1e-9 else 0.0
    ratio_120_0 = float(H_axis3 / H_axis1) if H_axis1 > 1e-9 else 0.0

    # Factores de base geométricos teóricos (Miller relativos a rotation_deg,
    # ver docstring). Para hexagonal monoatómica |F|^2 ≡ 1 en todo G.
    if is_honeycomb:
        F2_axis1 = _honeycomb_basis_factor_sq(1, u2, 0, v2)
        F2_axis2 = _honeycomb_basis_factor_sq(1, u2, 1, v2)
        F2_axis3 = _honeycomb_basis_factor_sq(0, u2, 1, v2)
        F2_ortho1 = _honeycomb_basis_factor_sq(1, u2, 2, v2)
        F2_ortho2 = _honeycomb_basis_factor_sq(2, u2, 1, v2)
        F2_ortho3 = _honeycomb_basis_factor_sq(-1, u2, 1, v2)
    else:
        F2_axis1 = F2_axis2 = F2_axis3 = 1.0
        F2_ortho1 = F2_ortho2 = F2_ortho3 = 1.0

    # Inversión analítica cerrada de sigma_pos (cociente 1er shell axis1 / 2do
    # shell ortho, cancela vacancias globales (1-p)^2 y N -- ver CAT-315 §7.1
    # honeycomb, CAT-308 §9 generalización hexagonal).
    #
    # CORRECCIÓN NUMÉRICA (verificada durante esta implementación, ver
    # tests/test_honeycomb_reciprocal_metrology.py::TestClosedFormSigmaInversion):
    # la fórmula tal como está impresa en CAT-315 §7.1 (sigma = (sqrt(3)a/4pi) *
    # sqrt(ln(4H1/H_ortho)), SIN dividir por 2 dentro de la raíz) sobreestima
    # sigma_pos en un factor sqrt(2) consistente y sistemático frente a redes
    # honeycomb/hexagonales sintéticas con desorden gaussiano CONOCIDO. La
    # convención Debye-Waller REALMENTE usada y ya validada en todo el resto
    # de este código base (ver core/lattice_disorder.py::compute_analytical_bragg_relations,
    # factor_h2h1_x = a_x/(2*pi*sqrt(3)), CAT-308 §3.1, probado en sesiones
    # previas) es H(G) ∝ exp(-G² * sigma_pos²) -- SIN el 1/2 que implicaría la
    # forma cuadrática q^T*Sigma_pos*q de CAT-315 §6.3 tomada literalmente.
    # Bajo esa convención (verificada empíricamente: exp(-q1²σ²) reproduce el
    # decaimiento medido de H_axis1(σ)/H_axis1(0) dentro de <1% en un barrido de
    # sigma de 0-60 nm, mientras que exp(-q1²σ²/2) sobreestima H hasta ~40% a
    # sigma=60 nm), el cociente de conchas correcto es
    # H_ortho/H_axis1 = 4*exp(-2*q1²*sigma_pos²) (no 4*exp(-q1²*sigma_pos²)),
    # y por lo tanto la inversión correcta divide el logaritmo por 2 adicional:
    # sigma_pos = (1/q1) * sqrt(ln(4H1/H_ortho) / 2), q1 = 2*pi*f1 = 4*pi/(sqrt(3)a).
    # Verificado numéricamente: recupera sigma_in conocido (12-40 nm) dentro de
    # <3% sobre 5 semillas independientes (vs. ~40-75% de sesgo sistemático con
    # la fórmula literal de CAT-315). Se recomienda corregir CAT-315 §7.1.
    honeycomb_inversion_valid = bool(4.0 * H_axis1 >= H_ortho)
    if is_honeycomb:
        radicand = (math.log(max(1e-12, 4.0 * H_axis1)) - math.log(max(1e-12, H_ortho))) / 2.0
        sigma_pos_analytic = (np.sqrt(3.0) * float(a)) / (4.0 * np.pi) * math.sqrt(max(0.0, radicand))
    else:
        radicand = (math.log(max(1e-12, H_axis1)) - math.log(max(1e-12, H_ortho))) / 2.0
        sigma_pos_analytic = (np.sqrt(3.0) * float(a)) / (4.0 * np.pi) * math.sqrt(max(0.0, radicand))

    return {
        'lattice_type': ltype_key, 'u2': float(u2), 'v2': float(v2),
        'H_axis1': H_axis1, 'H_axis2': H_axis2, 'H_axis3': H_axis3,
        'H_2_axis1': H_2_axis1, 'H_2_axis2': H_2_axis2,
        'H_ortho': H_ortho, 'H_ortho1': H_ortho1, 'H_ortho2': H_ortho2, 'H_ortho3': H_ortho3,
        'F2_axis1': F2_axis1, 'F2_axis2': F2_axis2, 'F2_axis3': F2_axis3,
        'F2_ortho1': F2_ortho1, 'F2_ortho2': F2_ortho2, 'F2_ortho3': F2_ortho3,
        'f1': f1, 'q_ortho': q_ortho,
        'ratio_21_axis1': ratio_21_axis1, 'ratio_21_axis2': ratio_21_axis2,
        'ratio_ortho': ratio_ortho, 'ratio_60_0': ratio_60_0, 'ratio_120_0': ratio_120_0,
        'sigma_pos_analytic': float(sigma_pos_analytic),
        'honeycomb_inversion_valid': honeycomb_inversion_valid,
        'rotation_deg': float(rotation_deg)
    }


def compute_radial_distribution_function(
    x: np.ndarray,
    y: np.ndarray,
    a_nominal: float = 450.0,
    b_nominal: Optional[float] = None,
    r_max_factor: float = 3.0,
    n_bins: int = 120,
    r_diffraction_limit: float = 250.0,
    enforce_diffraction_limit: bool = True,
    r_roi_min: Optional[float] = None,
    r_roi_max: Optional[float] = None,
    fixed_bg: Optional[float] = None
) -> Dict[str, Any]:
    """
    Calcula la Función de Distribución Radial g(r) y determina el ancho
    del primer pico de coordinación sigma_peak -> sigma_rdf = sigma_peak / sqrt(2).

    Enfoque Metrológico de Evaluación:
    - No presupone a priori que las partículas están perfectamente impresas.
    - Límite de Difracción Instrumental (r < r_diffraction_limit, ~250 nm): El microscopio
      óptico confocal de campo lejano colapsa dos emisores en una única mancha de difracción (PSF).
      Cualquier par detectado a r < r_diffraction_limit representa sobre-detección espuria de ruido
      o multímeros no resueltos, por lo que se impone g(r) = 0 como límite físico de resolución.
    - Ventana Sub-Red (r_diffraction_limit <= r < a_nominal): NO se asume g(r) = 0. Si hay partículas
      mal impresas, satélites o agregados, g(r) reporta su presencia para evaluar la calidad de fabricación.
    - Reglas visuales ROI: r_roi_min y r_roi_max permiten acotar interactivamente la ventana del primer pico.
    - fixed_bg: Permite fijar o liberar la línea base constante de fondo.
    """
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    N = len(x)
    if N < 4:
        return {
            'r': np.array([]),
            'gr': np.array([]),
            'sigma_rdf': 0.0,
            'first_peak_r': 0.0,
            'r_diffraction_limit': float(r_diffraction_limit),
            'sub_diffraction_artifacts': 0,
            'sublattice_defect_ratio': 0.0
        }

    r_max = float(r_max_factor * a_nominal)
    tree = cKDTree(np.column_stack([x, y]))
    # Pares de distancias menores a r_max
    pairs = tree.query_pairs(r_max, output_type='ndarray')
    if len(pairs) == 0:
        return {
            'r': np.array([]),
            'gr': np.array([]),
            'sigma_rdf': 0.0,
            'first_peak_r': 0.0,
            'r_diffraction_limit': float(r_diffraction_limit),
            'sub_diffraction_artifacts': 0,
            'sublattice_defect_ratio': 0.0
        }

    dists = np.hypot(x[pairs[:, 0]] - x[pairs[:, 1]], y[pairs[:, 0]] - y[pairs[:, 1]])

    r_edges = np.linspace(0, r_max, n_bins + 1)
    r_centers = (r_edges[:-1] + r_edges[1:]) / 2.0

    counts, _ = np.histogram(dists, bins=r_edges)

    # Densidad media de partículas en el área encerrada (rectangular: pad X con a, Y con b)
    b_val = float(b_nominal) if b_nominal is not None else a_nominal
    area = (np.ptp(x) + a_nominal) * (np.ptp(y) + b_val)
    rho = N / area if area > 0 else 1.0

    # Normalización por el área anular: 2 * pi * r * dr * (N * (N - 1) / 2)
    shell_areas = np.pi * (r_edges[1:] ** 2 - r_edges[:-1] ** 2)
    expected_pairs = 0.5 * N * rho * shell_areas
    gr = np.divide(counts, expected_pairs, out=np.zeros_like(counts, dtype=np.float64), where=expected_pairs > 0)

    # Auditoría metrológica de sub-difracción y defectos sub-red
    mask_subdiff = r_centers < r_diffraction_limit
    sub_diff_artifacts = int(np.sum(counts[mask_subdiff]))

    # En un software de evaluación metrológica, el límite de difracción impone g(r) = 0
    # para distancias no resolubles ópticamente por campo lejano
    if enforce_diffraction_limit and r_diffraction_limit > 0:
        gr[mask_subdiff] = 0.0

    # Detección de defectos en ventana sub-red [r_diffraction_limit, 0.75 * a_nominal]
    mask_defects = (r_centers >= r_diffraction_limit) & (r_centers < 0.75 * a_nominal)
    sublattice_defects_count = int(np.sum(counts[mask_defects]))
    sublattice_defect_ratio = float(sublattice_defects_count / len(pairs)) if len(pairs) > 0 else 0.0

    # Modelo de doble gaussiana: red rectangular con periodos de vecino resueltos (a != b)
    is_double_mode = bool(b_nominal is not None and abs(a_nominal - b_val) > 15.0)

    # Búsqueda del primer pico de red
    if r_roi_min is not None and r_roi_max is not None:
        lower_bound = min(float(r_roi_min), float(r_roi_max))
        upper_bound = max(float(r_roi_min), float(r_roi_max))
    elif is_double_mode:
        # El límite inferior respeta el límite de difracción instrumental sin presuponer rigidez
        lower_bound = max(r_diffraction_limit, min(a_nominal, b_val) * 0.65)
        upper_bound = max(a_nominal, b_val) * 1.35
    else:
        lower_bound = max(r_diffraction_limit, a_nominal * 0.65)
        upper_bound = a_nominal * 1.35

    mask_peak = (r_centers >= lower_bound) & (r_centers <= upper_bound)
    r_peak_region = r_centers[mask_peak]
    gr_peak_region = gr[mask_peak]

    sigma_rdf = 0.0
    sigma_peak = 0.0
    fwhm_rdf = 0.0
    first_peak_r = a_nominal
    fit_r = np.array([])
    fit_gr = np.array([])
    height_rdf = 0.0
    bg_rdf = 0.0
    is_double_peak = False
    secondary_peak = None
    peak_resolution_warning = False

    if fixed_bg is not None:
        bg_low = float(fixed_bg) - 1e-6
        bg_high = float(fixed_bg) + 1e-6
    else:
        bg_low = 0.0
        bg_high = np.inf

    if len(r_peak_region) >= 5 and np.max(gr_peak_region) > 0.1:
        bg_init = float(fixed_bg) if fixed_bg is not None else float(np.min(gr_peak_region))

        if is_double_mode and len(r_peak_region) >= 8:
            # Doble gaussiana: resuelve los dos primeros picos de vecinos a distancias a y b
            r1_init = float(r_peak_region[np.argmin(np.abs(r_peak_region - a_nominal))])
            r2_init = float(r_peak_region[np.argmin(np.abs(r_peak_region - b_val))])
            H1_init = max(float(gr_peak_region[np.argmin(np.abs(r_peak_region - r1_init))]) - bg_init, 1e-3)
            H2_init = max(float(gr_peak_region[np.argmin(np.abs(r_peak_region - r2_init))]) - bg_init, 1e-3)
            s1_init = a_nominal * 0.08
            s2_init = b_val * 0.08

            p0 = [H1_init, r1_init, s1_init, H2_init, r2_init, s2_init, bg_init]
            bounds = (
                [0.0, lower_bound, 1e-3, 0.0, lower_bound, 1e-3, bg_low],
                [np.inf, upper_bound, max(a_nominal, b_val), np.inf, upper_bound, max(a_nominal, b_val), bg_high]
            )
            try:
                def _double_gr(r, A1, r1, s1, A2, r2, s2, bg):
                    return (A1 * np.exp(-((r - r1) ** 2) / (2 * s1 ** 2)) +
                            A2 * np.exp(-((r - r2) ** 2) / (2 * s2 ** 2)) + bg)

                popt, _ = curve_fit(_double_gr, r_peak_region, gr_peak_region, p0=p0, bounds=bounds, maxfev=2000)
                A1_f, r1_f, s1_f, A2_f, r2_f, s2_f, bg_f = popt

                # Criterio de resolubilidad: dos gaussianas cuya separación de centros es menor a
                # ~1.5x la suma de sus anchos no son estadísticamente distinguibles (ajuste no-identificable,
                # el optimizador intercambia amplitud/ancho libremente entre ambas). Degradar a simple gaussiana
                # en ese caso en vez de reportar un "is_double_peak=True" con parámetros espurios.
                peaks_resolved = abs(r1_f - r2_f) > 1.5 * (abs(s1_f) + abs(s2_f))

                if not peaks_resolved:
                    is_double_mode = False
                    peak_resolution_warning = True
                else:
                    # El pico "primario" es el más cercano a a_nominal (eje X de referencia)
                    if abs(r1_f - a_nominal) <= abs(r2_f - a_nominal):
                        primary = (A1_f, r1_f, s1_f)
                        secondary = (A2_f, r2_f, s2_f)
                    else:
                        primary = (A2_f, r2_f, s2_f)
                        secondary = (A1_f, r1_f, s1_f)

                    height_rdf, first_peak_r, sigma_peak = float(primary[0]), float(primary[1]), abs(float(primary[2]))
                    sigma_rdf = sigma_peak / np.sqrt(2.0)
                    fwhm_rdf = 2.35482 * sigma_peak
                    bg_rdf = float(bg_f)
                    is_double_peak = True

                    H_sec, r0_sec, s_sec = secondary
                    sigma_sec = abs(float(s_sec))
                    secondary_peak = {
                        'first_peak_r': float(r0_sec),
                        'height_rdf': float(H_sec),
                        'sigma_peak': sigma_sec,
                        'sigma_rdf': sigma_sec / np.sqrt(2.0),
                        'fwhm_rdf': 2.35482 * sigma_sec
                    }

                    fit_r = np.linspace(float(r_peak_region[0]), float(r_peak_region[-1]), 200)
                    fit_gr = _double_gr(fit_r, A1_f, r1_f, s1_f, A2_f, r2_f, s2_f, bg_f)
            except Exception:
                is_double_mode = False  # Degradar a ajuste simple si el doble gaussiano no converge

        if not is_double_peak:
            idx_pk = np.argmax(gr_peak_region)
            first_peak_r = float(r_peak_region[idx_pk])
            H_init = max(float(np.max(gr_peak_region)) - bg_init, 1e-3)
            p0 = [H_init, first_peak_r, a_nominal * 0.08, bg_init]

            bounds = ([0.0, lower_bound, 1e-3, bg_low], [np.inf, upper_bound, max(a_nominal, b_val), bg_high])
            try:
                popt, _ = curve_fit(
                    lambda r, A, r0, s, bg: A * np.exp(-((r - r0) ** 2) / (2 * s ** 2)) + bg,
                    r_peak_region,
                    gr_peak_region,
                    p0=p0,
                    bounds=bounds,
                    maxfev=1000
                )
                A_fit, r0_fit, s_fit, bg_fit = popt
                first_peak_r = float(r0_fit)
                sigma_peak = abs(float(s_fit))
                # Para dos partículas fluctuando independientemente: Var(Delta r) = 2 * sigma^2
                sigma_rdf = sigma_peak / np.sqrt(2.0)
                fwhm_rdf = 2.35482 * sigma_peak
                height_rdf = float(A_fit)
                bg_rdf = float(bg_fit)

                fit_r = np.linspace(float(r_peak_region[0]), float(r_peak_region[-1]), 150)
                fit_gr = A_fit * np.exp(-((fit_r - r0_fit) ** 2) / (2.0 * (s_fit ** 2))) + bg_fit
            except Exception:
                sigma_rdf = 0.0

    return {
        'r': r_centers,
        'gr': gr,
        'first_peak_r': first_peak_r,
        'r0': first_peak_r,
        'sigma_rdf': float(sigma_rdf),
        'sigma_peak': float(sigma_peak),
        'fwhm_rdf': float(fwhm_rdf),
        'height_rdf': height_rdf,
        'bg_rdf': bg_rdf,
        'fit_r': fit_r,
        'fit_gr': fit_gr,
        'r_roi_min': lower_bound,
        'r_roi_max': upper_bound,
        'r_diffraction_limit': float(r_diffraction_limit),
        'sub_diffraction_artifacts': sub_diff_artifacts,
        'sublattice_defect_ratio': sublattice_defect_ratio,
        'a_nominal': a_nominal,
        'b_nominal': b_val,
        'is_double_peak': is_double_peak,
        'secondary_peak': secondary_peak,
        'peak_resolution_warning': peak_resolution_warning
    }


# ==============================================================================
# 3. SIMULACIÓN MONTE CARLO & CALIBRACIÓN DEBYE-WALLER
# ==============================================================================

def run_monte_carlo_calibration(
    n_side: int,
    a: float,
    f_vac: float = 0.0,
    sigma_min: float = 0.0,
    sigma_max: float = 60.0,
    n_sigma_steps: int = 25,
    iterations_per_step: int = 40,
    progress_callback: Optional[Callable[[int, int, float], None]] = None,
    a_y: Optional[float] = None,
    n_bragg_pts: int = 81,
    band_width_nm: float = 0.0,
    n_transversal_pts: int = 5,
    seed: Optional[int] = None,
    n_side_x: Optional[int] = None,
    n_side_y: Optional[int] = None
) -> Dict[str, Any]:
    """
    Ejecuta la calibración estocástica Monte Carlo de la atenuación de Debye-Waller
    desacoplando rigurosamente el factor de vacancias (1 - f_vac)^2 y soportando:
    - Alta densidad espectral continua en la campana de Bragg (Mejora 1).
    - Integración de banda espectral transversal para isomorfismo con Pestaña 2 (Mejora 2).
    - Anisotropía cristalográfica de red con evaluación dual X e Y (Mejora 3).

    Parámetros:
    -----------
    n_side : int
        Número de sitios por lado (N x N).
    a : float
        Período de red nominal o en eje X [nm].
    f_vac : float
        Fracción de vacancias medida experimentalmente en el Paso 1.
    sigma_min, sigma_max : float
        Rango de desórdenes posicionales a simular [nm].
    n_sigma_steps : int
        Número de niveles de sigma.
    iterations_per_step : int
        Réplicas estadísticas por cada nivel de sigma.
    progress_callback : callable, opcional
        Función(paso_actual, total_pasos, porcentaje) para actualizar la barra de carga.
    a_y : float, opcional
        Período de red en eje Y [nm]. Si es None, se asume red cuadrada a_x = a_y = a.
    n_bragg_pts : int, por defecto 81
        Cantidad de puntos continuos para muestrear la campana de Bragg (Mejora 1).
    band_width_nm : float, por defecto 0.0
        Ancho físico de la banda transversal en el espacio recíproco [nm^-1].
        Si > 0, integra n_transversal_pts simétricos alrededor de 0 (Mejora 2).
    n_transversal_pts : int, por defecto 5
        Número de puntos de cuadratura en la banda transversal (Mejora 2).
    seed : int, opcional
        Semilla para el generador aleatorio de NumPy para reproducibilidad.
    n_side_x, n_side_y : int, opcional
        Número de sitios independientes por eje (red rectangular N_x x N_y).
        Si son None, se usa `n_side` para ambos ejes (retrocompatibilidad, red cuadrada).
    """
    n_side = max(2, int(n_side))
    n_side_x = max(2, int(n_side_x)) if n_side_x is not None else n_side
    n_side_y = max(2, int(n_side_y)) if n_side_y is not None else n_side
    N_sites = n_side_x * n_side_y
    f_vac = np.clip(float(f_vac), 0.0, 0.95)
    rng = np.random.default_rng(seed)

    ax_val = float(a)
    ay_val = float(a_y) if a_y is not None else ax_val
    is_anisotropic = abs(ax_val - ay_val) > 1e-3

    sigma_values = np.linspace(sigma_min, sigma_max, n_sigma_steps)
    total_runs = n_sigma_steps * iterations_per_step

    # Grilla base ideal 2D centrada (soportando rectangulares/anisótropas, N_x != N_y)
    half_span_x = ((n_side_x - 1) * ax_val) / 2.0
    half_span_y = ((n_side_y - 1) * ay_val) / 2.0
    gx = np.linspace(-half_span_x, half_span_x, n_side_x)
    gy = np.linspace(-half_span_y, half_span_y, n_side_y)
    X0, Y0 = np.meshgrid(gx, gy)
    x0_flat = X0.ravel()
    y0_flat = Y0.ravel()

    # Frecuencias continuas de alta densidad alrededor del pico de Bragg (Mejora 1)
    f0_x = 1.0 / ax_val
    f0_y = 1.0 / ay_val
    n_pts = max(31, int(n_bragg_pts))
    fx_eval = np.linspace(f0_x * 0.75, f0_x * 1.25, n_pts)
    fy_eval = np.linspace(f0_y * 0.75, f0_y * 1.25, n_pts)

    # Multi-orden: frecuencias continuas para pico diagonal (1, 1) y 2do orden armónico (2, 0)
    f_diag_0 = float(np.sqrt(f0_x ** 2 + f0_y ** 2))
    f_diag_eval = np.linspace(f_diag_0 * 0.75, f_diag_0 * 1.25, n_pts)
    f2x_eval = np.linspace(2.0 * f0_x * 0.85, 2.0 * f0_x * 1.15, n_pts)
    f2y_eval = np.linspace(2.0 * f0_y * 0.85, 2.0 * f0_y * 1.15, n_pts) if is_anisotropic else f2x_eval

    # Cuadratura de banda transversal (Mejora 2)
    if band_width_nm > 0.0:
        delta_f = float(band_width_nm)
        n_trans = max(1, int(n_transversal_pts))
        f_trans_y = np.linspace(-delta_f, delta_f, n_trans)
        f_trans_x = np.linspace(-delta_f, delta_f, n_trans)
    else:
        f_trans_y = np.zeros(1, dtype=np.float64)
        f_trans_x = np.zeros(1, dtype=np.float64)

    H_mean_x = np.zeros(n_sigma_steps, dtype=np.float64)
    H_std_x = np.zeros(n_sigma_steps, dtype=np.float64)
    H_mean_y = np.zeros(n_sigma_steps, dtype=np.float64)
    H_std_y = np.zeros(n_sigma_steps, dtype=np.float64)

    H_mean_diag = np.zeros(n_sigma_steps, dtype=np.float64)
    H_std_diag = np.zeros(n_sigma_steps, dtype=np.float64)
    H_mean_2x = np.zeros(n_sigma_steps, dtype=np.float64)
    H_std_2x = np.zeros(n_sigma_steps, dtype=np.float64)
    H_mean_2y = np.zeros(n_sigma_steps, dtype=np.float64)
    H_std_2y = np.zeros(n_sigma_steps, dtype=np.float64)

    run_counter = 0

    for i, s in enumerate(sigma_values):
        heights_step_x = []
        heights_step_y = []
        heights_step_diag = []
        heights_step_2x = []
        heights_step_2y = []

        for _ in range(iterations_per_step):
            # Inyección de vacancias
            if f_vac > 0:
                keep_mask = rng.uniform(0, 1, N_sites) >= f_vac
                if np.sum(keep_mask) < 4:
                    keep_mask[:4] = True
                x_occ = x0_flat[keep_mask]
                y_occ = y0_flat[keep_mask]
            else:
                x_occ = x0_flat
                y_occ = y0_flat

            N_occ = len(x_occ)

            # Inyección de desorden estocástico
            if s > 0:
                x_noisy = x_occ + rng.normal(0, s, N_occ)
                y_noisy = y_occ + rng.normal(0, s, N_occ)
            else:
                x_noisy = x_occ
                y_noisy = y_occ

            # --- 1. Evaluación del Pico Bragg en X (fx cerca de f0_x, fy transversal) ---
            Ex_main = np.exp(-2j * np.pi * np.outer(fx_eval, x_noisy))
            Ey_trans = np.exp(-2j * np.pi * np.outer(f_trans_y, y_noisy))
            M_x = np.matmul(Ey_trans, Ex_main.T)  # (n_trans, n_pts)
            S_x = (np.abs(M_x) ** 2) / float(N_occ)
            profile_x = np.mean(S_x, axis=0) if len(f_trans_y) > 1 else S_x[0]
            heights_step_x.append(float(np.max(profile_x)))

            # --- 2. Evaluación del Pico Bragg en Y (fy cerca de f0_y, fx transversal) ---
            if is_anisotropic:
                Ey_main = np.exp(-2j * np.pi * np.outer(fy_eval, y_noisy))
                Ex_trans = np.exp(-2j * np.pi * np.outer(f_trans_x, x_noisy))
                M_y = np.matmul(Ex_trans, Ey_main.T)  # (n_trans, n_pts)
                S_y = (np.abs(M_y) ** 2) / float(N_occ)
                profile_y = np.mean(S_y, axis=0) if len(f_trans_x) > 1 else S_y[0]
                heights_step_y.append(float(np.max(profile_y)))

            # --- 3. Evaluación del Pico Diagonal (1, 1) ---
            r_diag_norm = (x_noisy + y_noisy) / np.sqrt(2.0)
            r_trans_diag_norm = (-x_noisy + y_noisy) / np.sqrt(2.0)
            Ed_main = np.exp(-2j * np.pi * np.outer(f_diag_eval, r_diag_norm))
            Ed_trans = np.exp(-2j * np.pi * np.outer(f_trans_y, r_trans_diag_norm))
            M_d = np.matmul(Ed_trans, Ed_main.T)
            S_d = (np.abs(M_d) ** 2) / float(N_occ)
            profile_d = np.mean(S_d, axis=0) if len(f_trans_y) > 1 else S_d[0]
            heights_step_diag.append(float(np.max(profile_d)))

            # --- 4. Evaluación del 2do Orden Armónico (2, 0) ---
            E2x_main = np.exp(-2j * np.pi * np.outer(f2x_eval, x_noisy))
            M_2x = np.matmul(Ey_trans, E2x_main.T)
            S_2x = (np.abs(M_2x) ** 2) / float(N_occ)
            profile_2x = np.mean(S_2x, axis=0) if len(f_trans_y) > 1 else S_2x[0]
            heights_step_2x.append(float(np.max(profile_2x)))

            # --- 5. Evaluación del 2do Orden Armónico en Y (0, 2) si anisótropo ---
            if is_anisotropic:
                E2y_main = np.exp(-2j * np.pi * np.outer(f2y_eval, y_noisy))
                M_2y = np.matmul(Ex_trans, E2y_main.T)
                S_2y = (np.abs(M_2y) ** 2) / float(N_occ)
                profile_2y = np.mean(S_2y, axis=0) if len(f_trans_x) > 1 else S_2y[0]
                heights_step_2y.append(float(np.max(profile_2y)))

            run_counter += 1
            if progress_callback is not None and run_counter % 10 == 0:
                pct = (run_counter / total_runs) * 100.0
                progress_callback(run_counter, total_runs, pct)

        H_mean_x[i] = float(np.mean(heights_step_x))
        H_std_x[i] = float(np.std(heights_step_x, ddof=1))

        H_mean_diag[i] = float(np.mean(heights_step_diag))
        H_std_diag[i] = float(np.std(heights_step_diag, ddof=1))

        H_mean_2x[i] = float(np.mean(heights_step_2x))
        H_std_2x[i] = float(np.std(heights_step_2x, ddof=1))

        if is_anisotropic:
            H_mean_y[i] = float(np.mean(heights_step_y))
            H_std_y[i] = float(np.std(heights_step_y, ddof=1))
            H_mean_2y[i] = float(np.mean(heights_step_2y))
            H_std_2y[i] = float(np.std(heights_step_2y, ddof=1))
        else:
            H_mean_y[i] = H_mean_x[i]
            H_std_y[i] = H_std_x[i]
            H_mean_2y[i] = H_mean_2x[i]
            H_std_2y[i] = H_std_2x[i]

    if progress_callback is not None:
        progress_callback(total_runs, total_runs, 100.0)

    # Ajuste analítico de Debye-Waller para X e Y
    fit_res_x = fit_debye_waller_curve(sigma_values, H_mean_x, f_vac=f_vac)
    fit_res_y = fit_debye_waller_curve(sigma_values, H_mean_y, f_vac=f_vac) if is_anisotropic else fit_res_x

    # Ajuste analítico de Debye-Waller para Diagonal y 2do Orden
    fit_res_diag = fit_debye_waller_curve(sigma_values, H_mean_diag, f_vac=f_vac)
    fit_res_2x = fit_debye_waller_curve(sigma_values, H_mean_2x, f_vac=f_vac)
    fit_res_2y = fit_debye_waller_curve(sigma_values, H_mean_2y, f_vac=f_vac) if is_anisotropic else fit_res_2x

    return {
        'n_side': n_side_x,
        'n_side_x': n_side_x,
        'n_side_y': n_side_y,
        'N_sites': N_sites,
        'a': ax_val,
        'a_x': ax_val,
        'a_y': ay_val,
        'is_anisotropic': is_anisotropic,
        'n_bragg_pts': n_pts,
        'band_width_nm': band_width_nm,
        'n_transversal_pts': n_transversal_pts,
        'f_vac': f_vac,
        'sigma_values': sigma_values,
        'H_mean': H_mean_x,
        'H_std': H_std_x,
        'H_mean_x': H_mean_x,
        'H_std_x': H_std_x,
        'H_mean_y': H_mean_y,
        'H_std_y': H_std_y,
        'fit': fit_res_x,
        'fit_x': fit_res_x,
        'fit_y': fit_res_y,

        # Multi-orden
        'H_mean_diag': H_mean_diag,
        'H_std_diag': H_std_diag,
        'fit_diag': fit_res_diag,
        'H_mean_2': H_mean_2x,
        'H_std_2': H_std_2x,
        'H_mean_2x': H_mean_2x,
        'H_std_2x': H_std_2x,
        'fit_2': fit_res_2x,
        'fit_2x': fit_res_2x,
        'H_mean_2y': H_mean_2y,
        'H_std_2y': H_std_2y,
        'fit_2y': fit_res_2y
    }


def run_hexagonal_monte_carlo_calibration(
    lattice_type: str,
    a: float,
    boundary_type: str = 'hexagon',
    boundary_size_nm: float = 4000.0,
    boundary_width_nm: Optional[float] = None,
    boundary_height_nm: Optional[float] = None,
    f_vac: float = 0.0,
    sigma_min: float = 0.0,
    sigma_max: float = 60.0,
    n_sigma_steps: int = 25,
    iterations_per_step: int = 40,
    progress_callback: Optional[Callable[[int, int, float], None]] = None,
    n_bragg_pts: int = 81,
    seed: Optional[int] = None,
    u2: float = 1.0 / 3.0,
    v2: float = 1.0 / 3.0,
    rotation_deg: float = 0.0
) -> Dict[str, Any]:
    """
    Calibración estocástica Monte Carlo de la atenuación de Debye-Waller para redes
    hexagonales/triangulares (Z=6) y honeycomb/grafeno (Z=3, base biatómica), acotadas
    dentro de una geometría poligonal (hexágono, círculo o rectángulo).

    rotation_deg : float, opcional (Paquete D.4)
        Rotación del retículo RECÍPROCO en la misma convención que
        compute_hexagonal_bragg_indexing (spin_fourier_rotation de la Pestaña 3):
        rotation_deg+0° es, por construcción/semilla, la azimut de un pico de
        Bragg real (ver find_hexagonal_reciprocal_rotation), y los 6 picos de
        1er orden caen en rotation_deg + {0°,60°,...,300°} (NO en la base
        histórica -30°/30°/90°/... salvo cuando rotation_deg=0). Además de la
        curva isotrópica H_mean/H_std (promedio de las 6 direcciones,
        comportamiento idéntico al previo con rotation_deg=0.0), evalúa por
        separado las curvas direccionales H_mean_axis1/H_std_axis1 (3 réplicas
        equivalentes por simetría 6-fold: rotation_deg+{0°,120°,240°}) y
        H_mean_axis2/H_std_axis2 (rotation_deg+{60°,180°,300°}), consistentes
        con H_axis1 (rotation_deg+0°) y H_axis2 (rotation_deg+60°) de
        compute_hexagonal_bragg_indexing; y la curva ortogonal de 2do shell
        H_mean_ortho/H_std_ortho (radio q_ortho=sqrt(3)*f0, 3 réplicas en
        rotation_deg+{90°,210°,330°}), consistente con H_ortho (rotation_deg+90°).

    u2, v2 : float, opcional
        Base de la subred B para honeycomb/grafeno (ver generate_ideal_lattice_template).
        Debe coincidir con la misma base usada para el ajuste de grilla/template
        matching de la Pestaña 2 (_on_propagate_to_mc la transfiere automáticamente)
        — el factor de estructura F(G) de la base depende de tau=(u2,v2), así que
        una base inconsistente entre el template matching real y esta calibración
        produciría una curva de atenuación Debye-Waller calculada para un tau
        distinto del que realmente tienen los datos experimentales.

    Reutiliza `generate_ideal_lattice_template` (puente a core/lattice_generator.py)
    para la grilla ideal base, e inyecta vacancias + desorden gaussiano con el mismo
    esquema estadístico que `run_monte_carlo_calibration`, evaluando S(f) promediada
    sobre las 6 direcciones de Bragg de 1er orden equivalentes por simetría hexagonal
    (0°, 60°, ..., 300°) en f0 = 2/(sqrt(3)*a), mediante una única evaluación vectorizada
    BLAS (np.outer + suma compleja) sin bucle Python por dirección/frecuencia. Para
    honeycomb, el factor de estructura de base F(G) = 1 + exp(-i*G.tau) emerge
    naturalmente de la doble subred real (A+B) al evaluar S sobre TODAS las partículas
    (no requiere un término multiplicativo aparte), igual que en el motor NUFFT principal
    (compute_structure_factor_2d) — ver compute_basis_structure_factor para la predicción
    analítica independiente de este mismo efecto.
    """
    ltype_key = lattice_type.lower().strip()
    # Paquete D.4: el retículo ideal se genera YA rotado en espacio real, para que
    # sus picos de Bragg reales caigan exactamente en las direcciones evaluadas más
    # abajo (angles_deg = [0,60,...,300] + rotation_deg). Rotar sólo las direcciones
    # de evaluación sin rotar también la red sintética desalinearía la sonda del
    # pico real (rotación real-espacio <-> recíproco es una isometría covariante:
    # S(R_theta q; R_theta red) = S(q; red) para cualquier theta), produciendo la
    # misma atenuación Debye-Waller CRECIENTE espuria que motivó fijar originalmente
    # la convención -30°/30°/90°/... (ver nota más abajo). El offset +30° adicional
    # convierte rotation_deg (convención "rotation_deg+0° = azimut de un pico real",
    # idéntica a compute_hexagonal_bragg_indexing) a la rotación real-espacio
    # equivalente que hace que la base histórica -30°/30°/90°/... (verificada
    # numéricamente contra generate_ideal_lattice_template con rotación real 0°)
    # coincida con [0,60,...,300]+rotation_deg: base + (rotation_deg+30) =
    # (base+30) + rotation_deg = [0,60,...,300] + rotation_deg.
    template = generate_ideal_lattice_template(
        lattice_type=ltype_key, a=a, boundary_type=boundary_type, boundary_size_nm=boundary_size_nm,
        boundary_width_nm=boundary_width_nm, boundary_height_nm=boundary_height_nm,
        rotation_deg=float(rotation_deg) + 30.0, u2=u2, v2=v2
    )
    x0_flat = template['x']
    y0_flat = template['y']
    N_sites = len(x0_flat)
    if N_sites < 4:
        raise ValueError("La geometría envolvente no generó suficientes sitios de red ideal para calibrar.")

    f_vac = float(np.clip(f_vac, 0.0, 0.95))
    rng = np.random.default_rng(seed)
    sigma_values = np.linspace(sigma_min, sigma_max, n_sigma_steps)
    total_runs = n_sigma_steps * iterations_per_step

    f0 = 2.0 / (np.sqrt(3.0) * float(a))
    q_ortho = np.sqrt(3.0) * f0
    n_pts = max(31, int(n_bragg_pts))
    f_eval = np.linspace(f0 * 0.75, f0 * 1.25, n_pts)
    f_eval_ortho = np.linspace(q_ortho * 0.75, q_ortho * 1.25, n_pts)
    # Las 6 direcciones equivalentes de Bragg de 1er orden están en rotation_deg +
    # {0°,60°,...,300°} (misma convención que compute_hexagonal_bragg_indexing,
    # donde H_axis1/H_axis2 se miden en rotation_deg+0°/+60°) -- consecuencia directa
    # de rotar la red sintética por rotation_deg+30° arriba. La base histórica
    # -30°/30°/90°/... (válida cuando rotation_deg=0, verificada numéricamente por
    # fuerza bruta contra generate_ideal_lattice_template antes de fijar esta
    # constante) queda recuperada exactamente cuando rotation_deg=0.
    angles_deg = np.array([0.0, 60.0, 120.0, 180.0, 240.0, 300.0]) + float(rotation_deg)
    angles_rad = np.radians(angles_deg)
    fx_dirs = np.outer(np.cos(angles_rad), f_eval).ravel()  # (6*n_pts,)
    fy_dirs = np.outer(np.sin(angles_rad), f_eval).ravel()
    # Paquete D.4: índices 0,2,4 (rotation_deg+0°,120°,240°) = familia Eje 1;
    # índices 1,3,5 (rotation_deg+60°,180°,300°) = familia Eje 2 (3 réplicas
    # equivalentes por simetría 6-fold cada una, incluyendo siempre el ángulo
    # exacto donde compute_hexagonal_bragg_indexing mide H_axis1/H_axis2).
    axis1_idx = np.array([0, 2, 4])
    axis2_idx = np.array([1, 3, 5])
    # 2do shell (constructivo en honeycomb, |F|^2=4): rotation_deg + {90°,210°,330°},
    # radio q_ortho=sqrt(3)*f0 -- consistente con H_ortho (rotation_deg+90°).
    angles_ortho_deg = np.array([90.0, 210.0, 330.0]) + float(rotation_deg)
    angles_ortho_rad = np.radians(angles_ortho_deg)
    fx_dirs_ortho = np.outer(np.cos(angles_ortho_rad), f_eval_ortho).ravel()  # (3*n_pts,)
    fy_dirs_ortho = np.outer(np.sin(angles_ortho_rad), f_eval_ortho).ravel()

    H_mean = np.zeros(n_sigma_steps, dtype=np.float64)
    H_std = np.zeros(n_sigma_steps, dtype=np.float64)
    H_mean_axis1 = np.zeros(n_sigma_steps, dtype=np.float64)
    H_std_axis1 = np.zeros(n_sigma_steps, dtype=np.float64)
    H_mean_axis2 = np.zeros(n_sigma_steps, dtype=np.float64)
    H_std_axis2 = np.zeros(n_sigma_steps, dtype=np.float64)
    H_mean_ortho = np.zeros(n_sigma_steps, dtype=np.float64)
    H_std_ortho = np.zeros(n_sigma_steps, dtype=np.float64)
    run_counter = 0

    for i, s in enumerate(sigma_values):
        heights_step = []
        heights_step_axis1 = []
        heights_step_axis2 = []
        heights_step_ortho = []
        for _ in range(iterations_per_step):
            if f_vac > 0:
                keep_mask = rng.uniform(0, 1, N_sites) >= f_vac
                if np.sum(keep_mask) < 4:
                    keep_mask[:4] = True
                x_occ = x0_flat[keep_mask]
                y_occ = y0_flat[keep_mask]
            else:
                x_occ = x0_flat
                y_occ = y0_flat
            N_occ = len(x_occ)

            if s > 0:
                x_noisy = x_occ + rng.normal(0, s, N_occ)
                y_noisy = y_occ + rng.normal(0, s, N_occ)
            else:
                x_noisy = x_occ
                y_noisy = y_occ

            phase = np.outer(fx_dirs, x_noisy) + np.outer(fy_dirs, y_noisy)  # (6*n_pts, N_occ)
            amp_sum = np.sum(np.exp(-2j * np.pi * phase), axis=1)
            S_by_dir = ((np.abs(amp_sum) ** 2) / float(N_occ)).reshape(len(angles_deg), n_pts)
            profile = np.mean(S_by_dir, axis=0)
            heights_step.append(float(np.max(profile)))
            heights_step_axis1.append(float(np.max(np.mean(S_by_dir[axis1_idx], axis=0))))
            heights_step_axis2.append(float(np.max(np.mean(S_by_dir[axis2_idx], axis=0))))

            phase_ortho = np.outer(fx_dirs_ortho, x_noisy) + np.outer(fy_dirs_ortho, y_noisy)  # (3*n_pts, N_occ)
            amp_sum_ortho = np.sum(np.exp(-2j * np.pi * phase_ortho), axis=1)
            S_by_dir_ortho = ((np.abs(amp_sum_ortho) ** 2) / float(N_occ)).reshape(len(angles_ortho_deg), n_pts)
            heights_step_ortho.append(float(np.max(np.mean(S_by_dir_ortho, axis=0))))

            run_counter += 1
            if progress_callback is not None and run_counter % 10 == 0:
                progress_callback(run_counter, total_runs, (run_counter / total_runs) * 100.0)

        H_mean[i] = float(np.mean(heights_step))
        H_std[i] = float(np.std(heights_step, ddof=1)) if len(heights_step) > 1 else 0.0
        H_mean_axis1[i] = float(np.mean(heights_step_axis1))
        H_std_axis1[i] = float(np.std(heights_step_axis1, ddof=1)) if len(heights_step_axis1) > 1 else 0.0
        H_mean_axis2[i] = float(np.mean(heights_step_axis2))
        H_std_axis2[i] = float(np.std(heights_step_axis2, ddof=1)) if len(heights_step_axis2) > 1 else 0.0
        H_mean_ortho[i] = float(np.mean(heights_step_ortho))
        H_std_ortho[i] = float(np.std(heights_step_ortho, ddof=1)) if len(heights_step_ortho) > 1 else 0.0

    if progress_callback is not None:
        progress_callback(total_runs, total_runs, 100.0)

    fit_res = fit_debye_waller_curve(sigma_values, H_mean, f_vac=f_vac)
    fit_res_axis1 = fit_debye_waller_curve(sigma_values, H_mean_axis1, f_vac=f_vac)
    fit_res_axis2 = fit_debye_waller_curve(sigma_values, H_mean_axis2, f_vac=f_vac)
    fit_res_ortho = fit_debye_waller_curve(sigma_values, H_mean_ortho, f_vac=f_vac)

    return {
        'lattice_type': ltype_key,
        'a': float(a),
        'f0': f0,
        'q_ortho': q_ortho,
        'boundary_type': template['boundary_type'],
        'boundary_size_nm': float(boundary_size_nm),
        'N_sites': N_sites,
        'n_side': int(round(math.sqrt(N_sites))),  # aproximación retrocompatible para UI ("N x N" nominal)
        'f_vac': f_vac,
        'sigma_values': sigma_values,
        'rotation_deg': float(rotation_deg),
        'H_mean': H_mean,
        'H_std': H_std,
        'fit': fit_res,
        # Paquete D.4: curvas de calibración direccionales (Eje 1 / Eje 2), aditivas
        # respecto a la curva isotrópica H_mean/H_std (retrocompatible).
        'H_mean_axis1': H_mean_axis1, 'H_std_axis1': H_std_axis1, 'fit_axis1': fit_res_axis1,
        'H_mean_axis2': H_mean_axis2, 'H_std_axis2': H_std_axis2, 'fit_axis2': fit_res_axis2,
        # Paquete C (misión honeycomb): curva de calibración del 2do shell ortogonal
        # (constructivo en honeycomb, |F|^2=4), radio q_ortho=sqrt(3)*f0.
        'H_mean_ortho': H_mean_ortho, 'H_std_ortho': H_std_ortho, 'fit_ortho': fit_res_ortho,
        'ideal_voronoi_coordination': template['ideal_voronoi_coordination']
    }


def debye_waller_model(sigma, H0, sigma_char, H_diffuse, f_vac=0.0):
    """
    Modelo de atenuación Debye-Waller simétrico (x0 = 0) con corrección
    de atenuación por vacancias (1 - p)^2:
        H(sigma, p) = H0 * (1 - p)^2 * exp(-sigma^2 / (2 * sigma_char^2)) + H_diffuse
    """
    vacancy_scale = (1.0 - f_vac) ** 2
    return H0 * vacancy_scale * np.exp(-(sigma ** 2) / (2.0 * sigma_char ** 2)) + H_diffuse


def fit_debye_waller_curve(
    sigma_values: np.ndarray,
    H_mean: np.ndarray,
    f_vac: float = 0.0
) -> Dict[str, Any]:
    """
    Ajusta la curva de calibración simulada mediante el modelo par Debye-Waller.
    """
    H0_init = float(np.max(H_mean)) / max(1e-4, (1.0 - f_vac) ** 2)
    H_diff_init = float(np.min(H_mean))
    sigma_char_init = 25.0

    def model_fixed_vac(s, H0, s_char, H_diff):
        return debye_waller_model(s, H0, s_char, H_diff, f_vac=f_vac)

    p0 = [H0_init, sigma_char_init, H_diff_init]
    bounds = ([0.0, 1.0, 0.0], [np.inf, 200.0, np.inf])

    try:
        popt, _ = curve_fit(model_fixed_vac, sigma_values, H_mean, p0=p0, bounds=bounds, maxfev=3000)
        H0_fit, sigma_char_fit, H_diff_fit = popt
        success = True
    except Exception:
        H0_fit = H0_init
        sigma_char_fit = sigma_char_init
        H_diff_fit = H_diff_init
        success = False

    s_dense = np.linspace(sigma_values[0], sigma_values[-1], 200)
    H_fit_dense = model_fixed_vac(s_dense, H0_fit, sigma_char_fit, H_diff_fit)

    # Coeficiente de determinación R^2
    H_fit_points = model_fixed_vac(sigma_values, H0_fit, sigma_char_fit, H_diff_fit)
    ss_res = np.sum((H_mean - H_fit_points) ** 2)
    ss_tot = np.sum((H_mean - np.mean(H_mean)) ** 2)
    r_squared = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

    return {
        'success': success,
        'H0': float(H0_fit),
        'sigma_char': float(sigma_char_fit),
        'H_diffuse': float(H_diff_fit),
        'r_squared': float(r_squared),
        's_dense': s_dense,
        'H_fit_dense': H_fit_dense
    }


def interpolate_disorder(
    H_meas: float,
    sigma_values: np.ndarray,
    H_mean: np.ndarray,
    H_std: Optional[np.ndarray] = None
) -> Tuple[float, float]:
    """
    Interpola el desorden experimental sigma_real a partir de la altura medida H_meas
    sobre la curva de calibración monótona descendente.

    Retorna:
    --------
    sigma_real, delta_sigma (valor medio e incertidumbre derivada del ancho estadístico).
    """
    H_meas = float(H_meas)

    # Verificar si está fuera de rango
    if H_meas >= H_mean[0]:
        return float(sigma_values[0]), 0.5
    if H_meas <= H_mean[-1]:
        return float(sigma_values[-1]), 2.0

    # Interpolación monótona invertida
    # H_mean desciende cuando sigma aumenta, por ende invertimos los arrays
    H_sorted = H_mean[::-1]
    s_sorted = sigma_values[::-1]

    sigma_real = float(np.interp(H_meas, H_sorted, s_sorted))

    # Estimación de incertidumbre basada en la banda +/- 1 sigma de la curva
    if H_std is not None:
        H_upper = (H_mean + H_std)[::-1]
        H_lower = (H_mean - H_std)[::-1]
        s_lower = float(np.interp(H_meas, H_upper, s_sorted))
        s_upper = float(np.interp(H_meas, H_lower, s_sorted))
        delta_sigma = abs(s_upper - s_lower) / 2.0
    else:
        delta_sigma = 1.0

    return sigma_real, float(delta_sigma)


def save_calibration_curve(file_path: str, data: Dict[str, Any]) -> None:
    """
    Guarda la curva de calibración simulada en un archivo comprimido .npz.
    """
    fit_dict = data.get('fit', {})
    fit_x = data.get('fit_x', fit_dict)
    fit_y = data.get('fit_y', fit_dict)
    fit_diag = data.get('fit_diag', {})
    fit_2 = data.get('fit_2', {})
    ax = float(data.get('a_x', data.get('a', 500.0)))
    ay = float(data.get('a_y', data.get('a', 500.0)))
    is_aniso = bool(data.get('is_anisotropic', abs(ax - ay) > 1e-3))

    np.savez_compressed(
        file_path,
        n_side=data['n_side'],
        a=data['a'],
        a_x=ax,
        a_y=ay,
        is_anisotropic=is_aniso,
        f_vac=data['f_vac'],
        sigma_values=data['sigma_values'],
        H_mean=data['H_mean'],
        H_std=data['H_std'],
        H_mean_x=data.get('H_mean_x', data['H_mean']),
        H_std_x=data.get('H_std_x', data['H_std']),
        H_mean_y=data.get('H_mean_y', data['H_mean']),
        H_std_y=data.get('H_std_y', data['H_std']),
        H_mean_diag=data.get('H_mean_diag', np.array([])),
        H_std_diag=data.get('H_std_diag', np.array([])),
        H_mean_2=data.get('H_mean_2', np.array([])),
        H_std_2=data.get('H_std_2', np.array([])),
        H0=fit_dict.get('H0', 0.0),
        sigma_char=fit_dict.get('sigma_char', 0.0),
        H_diffuse=fit_dict.get('H_diffuse', 0.0),
        r_squared=fit_dict.get('r_squared', 0.0),
        H0_x=fit_x.get('H0', 0.0),
        sigma_char_x=fit_x.get('sigma_char', 0.0),
        H_diffuse_x=fit_x.get('H_diffuse', 0.0),
        r_squared_x=fit_x.get('r_squared', 0.0),
        H0_y=fit_y.get('H0', 0.0),
        sigma_char_y=fit_y.get('sigma_char', 0.0),
        H_diffuse_y=fit_y.get('H_diffuse', 0.0),
        r_squared_y=fit_y.get('r_squared', 0.0),
        H0_diag=fit_diag.get('H0', 0.0),
        sigma_char_diag=fit_diag.get('sigma_char', 0.0),
        r_squared_diag=fit_diag.get('r_squared', 0.0),
        H0_2=fit_2.get('H0', 0.0),
        sigma_char_2=fit_2.get('sigma_char', 0.0),
        r_squared_2=fit_2.get('r_squared', 0.0)
    )


def load_calibration_curve(file_path: str) -> Dict[str, Any]:
    """
    Carga una curva de calibración previa desde un archivo .npz.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Archivo de calibración no encontrado: {file_path}")

    loaded = np.load(file_path, allow_pickle=True)
    n_side = int(loaded['n_side'])
    a = float(loaded['a'])
    ax = float(loaded['a_x']) if 'a_x' in loaded else a
    ay = float(loaded['a_y']) if 'a_y' in loaded else a
    is_aniso = bool(loaded['is_anisotropic']) if 'is_anisotropic' in loaded else abs(ax - ay) > 1e-3
    f_vac = float(loaded['f_vac'])
    sigma_values = loaded['sigma_values']
    H_mean = loaded['H_mean']
    H_std = loaded['H_std']

    H_mean_x = loaded['H_mean_x'] if 'H_mean_x' in loaded else H_mean
    H_std_x = loaded['H_std_x'] if 'H_std_x' in loaded else H_std
    H_mean_y = loaded['H_mean_y'] if 'H_mean_y' in loaded else H_mean
    H_std_y = loaded['H_std_y'] if 'H_std_y' in loaded else H_std

    fit_res_x = fit_debye_waller_curve(sigma_values, H_mean_x, f_vac=f_vac)
    fit_res_y = fit_debye_waller_curve(sigma_values, H_mean_y, f_vac=f_vac) if is_aniso else fit_res_x

    # Cargar multi-orden si está disponible
    if 'H_mean_diag' in loaded and len(loaded['H_mean_diag']) > 0:
        H_mean_diag = loaded['H_mean_diag']
        H_std_diag = loaded['H_std_diag'] if 'H_std_diag' in loaded else np.zeros_like(H_mean_diag)
        fit_res_diag = fit_debye_waller_curve(sigma_values, H_mean_diag, f_vac=f_vac)
    else:
        H_mean_diag = None
        H_std_diag = None
        fit_res_diag = None

    if 'H_mean_2' in loaded and len(loaded['H_mean_2']) > 0:
        H_mean_2 = loaded['H_mean_2']
        H_std_2 = loaded['H_std_2'] if 'H_std_2' in loaded else np.zeros_like(H_mean_2)
        fit_res_2 = fit_debye_waller_curve(sigma_values, H_mean_2, f_vac=f_vac)
    else:
        H_mean_2 = None
        H_std_2 = None
        fit_res_2 = None

    return {
        'n_side': n_side,
        'a': a,
        'a_x': ax,
        'a_y': ay,
        'is_anisotropic': is_aniso,
        'f_vac': f_vac,
        'sigma_values': sigma_values,
        'H_mean': H_mean_x,
        'H_std': H_std_x,
        'H_mean_x': H_mean_x,
        'H_std_x': H_std_x,
        'H_mean_y': H_mean_y,
        'H_std_y': H_std_y,
        'fit': fit_res_x,
        'fit_x': fit_res_x,
        'fit_y': fit_res_y,
        'H_mean_diag': H_mean_diag,
        'H_std_diag': H_std_diag,
        'fit_diag': fit_res_diag,
        'H_mean_2': H_mean_2,
        'H_std_2': H_std_2,
        'fit_2': fit_res_2
    }
