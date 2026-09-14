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
import numpy as np
import pandas as pd
try:
    import cv2
except ImportError:
    cv2 = None
from scipy.spatial import cKDTree
from scipy.optimize import curve_fit
from scipy.signal import find_peaks, correlate2d
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
    n_total_particles: Optional[int] = None
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

    # 2. Inversión analítica H_diag / H1 (Coherencia 2D a partir del spot 2D)
    ratio_diag_2d = float(s_11 / max(1e-9, s_1_mean))
    factor_diag = a_mean / (2.0 * np.pi)
    sigma_diag = float(factor_diag * np.sqrt(max(0.0, np.log(max(1e-12, 1.0 / max(1e-12, ratio_diag_2d)))))) if ratio_diag_2d < 1.0 else 0.0

    # 3. Inversión frente al Pico Central DC H1 / H0 (Inestable)
    ratio_10 = float(H1_mean / max(1e-9, H0))
    factor_10 = a_mean / (2.0 * np.pi)
    sigma_h1h0 = float(factor_10 * np.sqrt(max(0.0, np.log(max(1e-12, 1.0 / max(1e-12, ratio_10)))))) if ratio_10 < 1.0 else 0.0

    # 4. Gráfico de Wilson (Wilson Plot)
    wilson_points = [
        {"name": "(1, 0) X", "G_sq": float(G1_x ** 2), "H": max(1e-6, s_10)},
        {"name": "(0, 1) Y", "G_sq": float(G1_y ** 2), "H": max(1e-6, s_01)},
        {"name": "(1, 1) Diag", "G_sq": float(G_diag ** 2), "H": max(1e-6, s_11)},
        {"name": "(2, 0) 2X", "G_sq": float(G2_x ** 2), "H": max(1e-6, s_20)},
        {"name": "(0, 2) 2Y", "G_sq": float(G2_y ** 2), "H": max(1e-6, s_02)},
    ]

    g_sq_arr = np.array([p["G_sq"] for p in wilson_points], dtype=np.float64)
    ln_h_arr = np.array([np.log(p["H"]) for p in wilson_points], dtype=np.float64)

    if len(g_sq_arr) >= 3 and np.ptp(g_sq_arr) > 1e-12:
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

    # 5. Diagnóstico Paracristalino
    fwhm1_x = float(res_dict.get('fwhm_x', 0.0))
    fwhm1_y = float(res_dict.get('fwhm_y', 0.0))
    fwhm1_mean = (fwhm1_x + fwhm1_y) / 2.0

    fwhm2_x = float(res_dict.get('fit_x_2nd', {}).get('fwhm', 0.0))
    fwhm2_y = float(res_dict.get('fit_y_2nd', {}).get('fwhm', 0.0))
    fwhm2_mean = (fwhm2_x + fwhm2_y) / 2.0

    paracrystal_ratio = float(fwhm2_mean / max(1e-9, fwhm1_mean))

    if paracrystal_ratio < 1.40:
        disorder_type = "Tipo I (Debye-Waller Puro)"
        disorder_desc = "Memoria traslacional de red absoluta. Ancho radial limitado por Scherrer (Δq₂ ≈ Δq₁)."
        is_type_1 = True
    else:
        disorder_type = "Tipo II (Paracristal de Hosemann)"
        disorder_desc = "Desorden de espaciado acumulativo. El ancho crece con el orden armónico (Δq₂ > Δq₁)."
        is_type_1 = False

    # 6. Curva de Decaimiento Debye-Waller
    q_norm_curve = np.linspace(0.5, 2.5, 120)
    dw_decay_theory = np.exp(- (q_norm_curve ** 2 - 1.0) * (G1_mean ** 2) * (sigma_h2h1 ** 2))

    points_q_ratio = np.array([1.0, float(np.sqrt(2.0)), 2.0])
    points_H_norm = np.array([
        1.0,
        float(H_diag / max(1e-9, H1_mean)),
        float(H2_mean / max(1e-9, H1_mean))
    ])

    return {
        'sigma_h2h1': sigma_h2h1,
        'sigma_h2h1_x': sigma_h2h1_x,
        'sigma_h2h1_y': sigma_h2h1_y,
        'ratio_21_mean': ratio_21_mean,
        'ratio_21_x': ratio_21_x,
        'ratio_21_y': ratio_21_y,

        'sigma_diag': sigma_diag,
        'ratio_diag': ratio_diag_2d,

        'sigma_h1h0': sigma_h1h0,
        'ratio_10': ratio_10,
        'H0': H0,
        'is_h1h0_unstable': True,

        'sigma_wilson': sigma_wilson,
        'r_squared_wilson': r_squared_w,
        'slope_wilson': slope_w,
        'intercept_wilson': intercept_w,
        'p_wilson_est': p_wilson_est,

        'wilson_data': {
            'g_sq': g_sq_arr,
            'ln_h': ln_h_arr,
            'names': [p["name"] for p in wilson_points],
            'fit_g_sq': g_sq_dense,
            'fit_ln_h': ln_h_dense,
            'points_raw': wilson_points
        },

        'paracrystal_diagnosis': {
            'ratio_fwhm': paracrystal_ratio,
            'disorder_type': disorder_type,
            'is_type_1': is_type_1,
            'fwhm_order1': fwhm1_mean,
            'fwhm_order2': fwhm2_mean,
            'description': disorder_desc
        },

        'debye_waller_curve': {
            'q_norm': q_norm_curve,
            'H_theory': dw_decay_theory,
            'points_q': points_q_ratio,
            'points_H': points_H_norm,
            'labels': ['Orden 1', 'Diagonal (1,1)', 'Orden 2']
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
    n_side: int
) -> Tuple[int, int, int, int]:
    """
    Encuentra la posición óptima de la huella de red (n_side x n_side) en el espacio
    de índices cristalinos enteros (ix, iy) mediante maximización convolutiva 2D de ocupación.

    Garantiza que la grilla abarque la mayor cantidad posible de partículas reales impresas,
    eliminando el desplazamiento espurio de una fila o columna hacia el fondo vacío
    provocado por ruidos asimétricos en los bordes de la imagen confocal.

    Retorna:
    --------
    min_ix, max_ix, min_iy, max_iy : int
    """
    if len(v_ix) == 0:
        return 0, n_side - 1, 0, n_side - 1

    min_x_idx, max_x_idx = int(np.min(v_ix)), int(np.max(v_ix))
    min_y_idx, max_y_idx = int(np.min(v_iy)), int(np.max(v_iy))
    span_x = max_x_idx - min_x_idx + 1
    span_y = max_y_idx - min_y_idx + 1

    if span_x < n_side or span_y < n_side:
        # Si el rango es menor que el tamaño nominal, centrar simétricamente
        pad_x = max(0, n_side - span_x)
        pad_y = max(0, n_side - span_y)
        min_ix = min_x_idx - pad_x // 2
        max_ix = min_ix + n_side - 1
        min_iy = min_y_idx - pad_y // 2
        max_iy = min_iy + n_side - 1
        return min_ix, max_ix, min_iy, max_iy

    # Construir matriz de presencia binaria de ocupación
    occ = np.zeros((span_x, span_y), dtype=int)
    for xi, yi in zip(v_ix, v_iy):
        occ[xi - min_x_idx, yi - min_y_idx] = 1

    kernel = np.ones((n_side, n_side), dtype=int)
    conv = correlate2d(occ, kernel, mode='valid')

    # Encontrar la ventana que maximiza la suma de partículas capturadas
    max_val = np.max(conv)
    best_positions = np.argwhere(conv == max_val)
    if len(best_positions) == 1:
        best_pos = best_positions[0]
    else:
        # En caso de empate, desempatar eligiendo la ventana cuyo centro esté más cerca
        # de la mediana de los índices de las partículas
        target_center_x = (float(np.median(v_ix)) - min_x_idx) - (n_side - 1) / 2.0
        target_center_y = (float(np.median(v_iy)) - min_y_idx) - (n_side - 1) / 2.0
        dists = [
            (pos[0] - target_center_x) ** 2 + (pos[1] - target_center_y) ** 2
            for pos in best_positions
        ]
        best_pos = best_positions[int(np.argmin(dists))]

    best_min_ix = min_x_idx + int(best_pos[0])
    best_min_iy = min_y_idx + int(best_pos[1])
    best_max_ix = best_min_ix + n_side - 1
    best_max_iy = best_min_iy + n_side - 1

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
    tolerance_pct: float = 20.0
) -> Dict[str, Any]:
    """
    Detecta aglomeraciones de partículas, dímeros, trímeros, cadenas ("gusanitos" en L o S)
    y spots individuales superpuestos por fotometría anómala.

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

    Retorna:
    --------
    dict con la lista de clusters, clasificación geométrica, fotometría de contornos y estadísticas.
    """
    if a_nominal is not None:
        a = float(a_nominal)
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
            tolerance_pct=tolerance_pct
        )

    return res


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
    initial_seeds: Optional[List[Tuple[float, float]]] = None
) -> List[Dict[str, Any]]:
    """
    Ajusta una mezcla de n-Gaussianas 2D sobre una región de interés (parche local)
    con el ancho óptico fijado al valor calibrado sigma = sigma_psf_px.

    Parámetros:
    -----------
    patch : np.ndarray
        Matriz 2D de intensidades del parche recortado.
    n_particles : int
        Número de partículas / emisores a desacoplar (n >= 1).
    sigma_psf_px : float
        Ancho óptico calibrado de la PSF en píxeles (constante fija).
    scale_nm : float
        Escala de conversión nm/píxel.
    origin_px : (x_min, y_min)
        Coordenada de origen del parche en la imagen global en píxeles.
    initial_seeds : list of (x_local, y_local), opcional
        Semillas iniciales de las posiciones locales en el parche.
    """
    patch = np.asarray(patch, dtype=float)
    H, W = patch.shape[:2]
    yy, xx = np.indices((H, W))
    coords = np.column_stack([xx.ravel(), yy.ravel()])
    data_1d = patch.ravel()

    border_px = np.concatenate([patch[0, :], patch[-1, :], patch[:, 0], patch[:, -1]])
    bg_init = float(np.percentile(border_px, 50))
    signal = np.clip(patch - bg_init, 0, None)
    tot_signal = float(np.sum(signal))
    i_max = float(np.max(patch))

    # Modelo n-Gaussiano vectorizado con sigma fija
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

    p0 = [bg_init]
    lb = [0.0]
    ub = [i_max * 1.5]

    I_est = (tot_signal / max(n_particles, 1)) / (2.0 * np.pi * (sigma_psf_px ** 2))
    I_est = max(I_est, i_max * 0.3)

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
        # Identificar eje principal de alargamiento del spot
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
        p0.extend([float(np.clip(sx, 0.5, W - 0.5)), float(np.clip(sy, 0.5, H - 0.5)), I_est])
        lb.extend([0.0, 0.0, 0.0])
        ub.extend([float(W), float(H), float(i_max * 3.0)])

    try:
        popt, _ = curve_fit(
            multi_gaussian,
            coords,
            data_1d,
            p0=p0,
            bounds=(lb, ub),
            method='trf',
            max_nfev=300
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
    tolerance_pct: float = 20.0
) -> Dict[str, Any]:
    """
    Segmenta las regiones conexas de emisión alrededor de cada cúmulo,
    mide el volumen luminoso integrado V_omega y área A_omega,
    y evalúa la estequiometría estimada n_est vs detecciones n_det con tolerancia +/- tolerance_pct%.
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
            n_est = max(1, int(round(ratio_p))) if 'Sobrepuesta' in c.get('type', '') else n_det
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

        thresh_val = bg + 0.25 * float(np.max(sig)) if np.max(sig) > 0 else bg
        mask_binary = (patch > thresh_val).astype(np.uint8)
        a_omega = float(np.sum(mask_binary))

        contour_poly_nm = []
        if cv2 is not None:
            try:
                contours, _ = cv2.findContours(mask_binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                if contours:
                    largest_cnt = max(contours, key=cv2.contourArea)
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
        n_est_raw = max(1, int(round(ratio_v)))

        # Regla de tolerancia estequiométrica (+/- tolerance_pct%):
        lower_bound = n_det * (1.0 - tol_factor) * V0
        upper_bound = n_det * (1.0 + tol_factor) * V0

        if lower_bound <= v_omega <= upper_bound:
            n_est = n_det
            status = 'OK'
        elif v_omega > upper_bound:
            n_est = max(n_det + 1, n_est_raw)
            status = 'UNDER_RESOLVED'
        else:
            n_est = max(1, min(n_det - 1, n_est_raw))
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
        c['sigma_psf_px'] = sigma_psf_px

    n_under = sum(1 for c in clusters if c.get('status') == 'UNDER_RESOLVED')
    n_ok = sum(1 for c in clusters if c.get('status') == 'OK')
    n_over = sum(1 for c in clusters if c.get('status') == 'OVER_DETECTED')

    clusters_info['n_under_resolved'] = n_under
    clusters_info['n_ok_resolved'] = n_ok
    clusters_info['n_over_detected'] = n_over
    clusters_info['signature'] = signature_dict

    return clusters_info


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
    A0 = float(np.pi * (2.0 * def_sigma_px) ** 2)
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

    # Estimación del fondo perimetral
    border_px = np.concatenate([patch[0, :], patch[-1, :], patch[:, 0], patch[:, -1]])
    bg = float(np.median(border_px))
    peak = float(np.max(patch))
    contrast = max(peak - bg, 1e-6)
    threshold_val = bg + (float(threshold_pct) / 100.0) * contrast

    mask_binary = (patch > threshold_val).astype(np.uint8)

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
        'sigma_psf_px': sigma_psf_px
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
    tolerance_pct: float = 20.0,
    n_gaussians: Optional[int] = None
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
    target_clusters = [c for c in clusters if c.get('id') == target_cluster_id] if target_cluster_id is not None else clusters

    for c in target_clusters:
        members = c['indices']

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
            # Estimar número de partículas a desacoplar
            if n_gaussians is not None and (target_cluster_id is None or c.get('id') == target_cluster_id):
                n_target = int(n_gaussians)
            else:
                n_target = int(c.get('n_est', len(members)))
                if n_target <= 1 and 'Sobrepuesta' in c.get('type', ''):
                    n_target = 2  # Desacoplar al menos en 2 emisores si es sobrepuesta
            n_target = min(max(n_target, 1), 8)
            if n_target <= 1:
                continue

            # Obtener parche y ancho sigma_psf
            patch = c.get('patch', None)
            origin_px = c.get('patch_origin_px', (0, 0))
            sigma_psf_px = c.get('sigma_psf_px', None)

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

            if patch is not None and patch.size > 0:
                fitted = fit_multi_gaussian_roi(
                    patch=patch,
                    n_particles=n_target,
                    sigma_psf_px=sigma_psf_px,
                    scale_nm=scale_nm,
                    origin_px=origin_px
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
    tolerance_pct: float = 20.0,
    n_gaussians: Optional[int] = None
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
        n_gaussians=n_gaussians
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
    n_particles: int,
    image_2d: Optional[np.ndarray],
    signature_dict: Optional[Dict[str, Any]] = None,
    scale_nm: float = 50.0,
    a_nominal: float = 500.0
) -> Tuple[Any, Dict[str, Any]]:
    """
    Desacopla un punto sospechoso específico (spot_index en df) ajustando n_particles Gaussianas
    con ancho óptico restringido a sigma_psf calibrado.
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

    n_fit = min(max(int(n_particles), 1), 6)

    if patch is not None and patch.size > 0:
        fitted = fit_multi_gaussian_roi(
            patch=patch,
            n_particles=n_fit,
            sigma_psf_px=sigma_psf_px,
            scale_nm=scale_nm,
            origin_px=origin_px
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
    n_side: Optional[int] = None,
    margin_percent: float = 10.0
) -> Dict[str, Any]:
    """
    Realiza el mapeo en espacio real mediante KDTree con cota superior estricta
    (distance_upper_bound = a / 2).

    Evita el error histórico de emparejamiento con vecinos a 450 nm ante vacancias
    y descompone los residuos en componentes cartesianas Delta x y Delta y, eliminando
    la subestimación del 34.5% provocada por std() sobre distancias euclidianas Rayleigh.
    """
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    M = len(x)
    if M == 0:
        raise ValueError("No hay coordenadas para analizar en espacio real.")

    # Estimar dimensiones de la red si no fueron provistas
    if n_side is None or n_side <= 0:
        span_x = float(np.ptp(x))
        span_y = float(np.ptp(y))
        span_mean = max(span_x, span_y)
        n_side = max(2, int(np.round(span_mean / a)) + 1)

    # 1. Estimación de Fase de Red Óptima (Media Circular de Fourier)
    # Encuentra la traslación exacta (x0, y0) del cristal independientemente
    # de si n_side es par o impar, o de si la red está descentrada.
    x0 = (a / (2.0 * np.pi)) * float(np.angle(np.sum(np.exp(2j * np.pi * x / a))))
    y0 = (a / (2.0 * np.pi)) * float(np.angle(np.sum(np.exp(2j * np.pi * y / a))))

    # 2. Asignación de índices enteros de nodo (ix, iy) para cada partícula
    ix = np.round((x - x0) / a).astype(int)
    iy = np.round((y - y0) / a).astype(int)

    # Posición ideal del nodo más cercano para cada partícula
    x_ideal = x0 + ix * a
    y_ideal = y0 + iy * a

    # Residuos cartesianos y distancia
    d_x = x - x_ideal
    d_y = y - y_ideal
    dist = np.hypot(d_x, d_y)

    # Cota estricta: sólo considerar partículas a menos de a/2 del nodo ideal
    valid_mask = dist < (a / 2.0)
    valid_dx = d_x[valid_mask]
    valid_dy = d_y[valid_mask]

    # Desorden posicional cartesiano no-sesgado
    sigma_x = float(np.std(valid_dx, ddof=1)) if len(valid_dx) > 1 else 0.0
    sigma_y = float(np.std(valid_dy, ddof=1)) if len(valid_dy) > 1 else 0.0
    sigma_pos = float(np.sqrt((sigma_x ** 2 + sigma_y ** 2) / 2.0))

    # 3. Detección de Vacancias mediante Maximización Convolutiva 2D de Ocupación
    valid_ix = ix[valid_mask]
    valid_iy = iy[valid_mask]

    if len(valid_ix) > 0:
        min_ix, max_ix, min_iy, max_iy = find_optimal_grid_bounding_box(valid_ix, valid_iy, n_side)

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

        grid_points = np.array([[x0 + i * a, y0 + j * a] for i, j in all_grid_coords], dtype=np.float64)
        vacant_points = np.array([[x0 + i * a, y0 + j * a] for i, j in vacant_indices], dtype=np.float64) if vacant_indices else np.empty((0, 2))
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
        min_ix, max_ix, min_iy, max_iy = 0, n_side - 1, 0, n_side - 1
        grid_points = np.empty((0, 2))
        vacant_points = np.empty((0, 2))
        matched_grid_points = np.empty((0, 2))
        valid_data = np.empty((0, 2))
        N_total_sites = (n_side * n_side) if (n_side and n_side > 0) else 0
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
        'n_side': n_side,
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
        'matched_data_points': valid_data
    }


def compute_radial_distribution_function(
    x: np.ndarray,
    y: np.ndarray,
    a_nominal: float = 450.0,
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

    # Densidad media de partículas en el área encerrada
    area = (np.ptp(x) + a_nominal) * (np.ptp(y) + a_nominal)
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

    # Búsqueda del primer pico de red
    if r_roi_min is not None and r_roi_max is not None:
        lower_bound = min(float(r_roi_min), float(r_roi_max))
        upper_bound = max(float(r_roi_min), float(r_roi_max))
    else:
        # El límite inferior respeta el límite de difracción instrumental sin presuponer rigidez
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

    if len(r_peak_region) >= 5 and np.max(gr_peak_region) > 0.1:
        idx_pk = np.argmax(gr_peak_region)
        first_peak_r = float(r_peak_region[idx_pk])
        bg_init = float(fixed_bg) if fixed_bg is not None else float(np.min(gr_peak_region))
        H_init = max(float(np.max(gr_peak_region)) - bg_init, 1e-3)
        p0 = [H_init, first_peak_r, a_nominal * 0.08, bg_init]

        if fixed_bg is not None:
            bg_low = float(fixed_bg) - 1e-6
            bg_high = float(fixed_bg) + 1e-6
        else:
            bg_low = 0.0
            bg_high = np.inf

        bounds = ([0.0, lower_bound, 1e-3, bg_low], [np.inf, upper_bound, a_nominal, bg_high])
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
        'sublattice_defect_ratio': sublattice_defect_ratio
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
    seed: Optional[int] = None
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
    """
    n_side = max(2, int(n_side))
    N_sites = n_side * n_side
    f_vac = np.clip(float(f_vac), 0.0, 0.95)
    rng = np.random.default_rng(seed)

    ax_val = float(a)
    ay_val = float(a_y) if a_y is not None else ax_val
    is_anisotropic = abs(ax_val - ay_val) > 1e-3

    sigma_values = np.linspace(sigma_min, sigma_max, n_sigma_steps)
    total_runs = n_sigma_steps * iterations_per_step

    # Grilla base ideal 2D centrada (soportando rectangulares/anisótropas)
    half_span_x = ((n_side - 1) * ax_val) / 2.0
    half_span_y = ((n_side - 1) * ay_val) / 2.0
    gx = np.linspace(-half_span_x, half_span_x, n_side)
    gy = np.linspace(-half_span_y, half_span_y, n_side)
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
        'n_side': n_side,
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
