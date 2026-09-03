# -*- coding: utf-8 -*-
"""
raman_engine.py — Motor de Procesamiento y Algoritmos para Espectroscopía Raman & SERS
PyPrinting 3.0 — UNSAM Nanofotónica

Proporciona funciones numéricas puras y de alto rendimiento para:
  1. Lectura robusta de espectros ASCII de Andor Solis (.asc, .txt, .csv, .dat) con soporte dual de separador decimal (, y .)
  2. Conversión bidireccional Longitud de Onda (nm) <-> Corrimiento Raman (cm^-1) y Energía (eV)
  3. Eliminación de rayos cósmicos (spikes de 1-2 píxeles) en detectores CCD
  4. Corrección de línea base (AsLS, AirPLS, ModPoly, derivadas, morfológico rolling-ball y splines manuales)
  5. Suavizado de señales (Savitzky-Golay, Fourier pasa-bajos/altos/notch, Whittaker-Eilers y Gaussiano)
  6. Detección y ajuste espectral no lineal de picos (Gaussiano, Lorentziano, Pseudo-Voigt)
  7. Termometría fototérmica in-situ por cociente Anti-Stokes / Stokes
  8. Base de datos de marcadores de referencia para nanoplasmónica y SERS
"""
from __future__ import annotations
import math
import re
from pathlib import Path
from typing import Dict, Tuple, List, Optional, Union

import numpy as np
from scipy import sparse
from scipy.sparse.linalg import spsolve
from scipy.signal import find_peaks, savgol_filter, medfilt
from scipy.ndimage import gaussian_filter1d, grey_opening
from scipy.optimize import curve_fit
from scipy.fft import rfft, irfft, rfftfreq

# ══════════════════════════════════════════════════════════════════════════════
#  CONSTANTES FÍSICAS
# ══════════════════════════════════════════════════════════════════════════════
PLANCK_CONSTANT = 6.62607015e-34       # J * s
SPEED_OF_LIGHT  = 2.99792458e10        # cm / s
BOLTZMANN_CONST = 1.380649e-23         # J / K
EV_PER_CM1      = 1.23984193e-4        # eV por cm^-1

# Biblioteca de Modos Vibracionales de Referencia para SERS y Calibración
RAMAN_REFERENCE_STANDARDS: Dict[str, Dict[str, Union[float, List[float], str]]] = {
    "Silicio (Calibración Shamrock)": {
        "peaks": [520.7],
        "desc": "Banda fonónica de Si(100), estándar internacional de calibración de espectrómetros.",
        "color": "#f38ba8"  # Red / Pink
    },
    "4-MBA (4-mercaptobenzoic acid)": {
        "peaks": [1078.0, 1182.0, 1588.0],
        "desc": "Molécula sonda monocapa clásica para SERS y acoplamiento plasmónico en Au/Ag.",
        "color": "#cba6f7"  # Mauve / Purple
    },
    "Rodamina 6G (R6G)": {
        "peaks": [612.0, 773.0, 1184.0, 1312.0, 1362.0, 1509.0, 1650.0],
        "desc": "Fluoróforo resonante modelo para factores de amplificación SERS ultra-altos.",
        "color": "#fab387"  # Peach / Orange
    },
    "BPE (trans-1,2-bis(4-pyridyl)ethylene)": {
        "peaks": [1000.0, 1200.0, 1610.0, 1640.0],
        "desc": "Sonda no fluorescente con gran sección eficaz Raman para nanopartículas.",
        "color": "#a6e3a1"  # Green
    },
    "Grafeno / Nanotubos de Carbono": {
        "peaks": [1350.0, 1582.0, 2680.0],
        "desc": "Bandas características D (defecto), G (orden grafítico sp2) y 2D (segundo orden).",
        "color": "#89dceb"  # Sky
    }
}


# ══════════════════════════════════════════════════════════════════════════════
#  1. LECTURA ROBUSTA DE ARCHIVOS ANDOR SOLIS
# ══════════════════════════════════════════════════════════════════════════════

def parse_andor_solis_file(filepath: Union[str, Path]) -> Tuple[Dict[str, str], np.ndarray, np.ndarray]:
    """
    Lee un archivo de espectroscopía exportado por Andor Solis (.asc, .txt, .dat, .csv).
    
    Características clave:
      - Extrae automáticamente las ~50 líneas iniciales de metadatos experimentales.
      - Tolera variabilidad en el número de líneas de cabecera.
      - Soporta configuración regional dual: procesa comas decimales (español/Europa)
        o puntos decimales (inglés) de manera completamente transparente.
    
    Retorna:
      metadata (dict): Diccionario con las propiedades de la adquisición.
      wavelengths (np.ndarray): Vector 1D con las longitudes de onda en nm.
      counts (np.ndarray): Vector 1D con las cuentas / intensidad registrada.
    """
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"No se encontró el archivo de espectro: {filepath}")

    metadata: Dict[str, str] = {}
    wavelengths: List[float] = []
    counts: List[float] = []

    # Leemos con soporte tolerante a codificación (UTF-8, Latin-1, cp1252)
    lines: List[str] = []
    for enc in ("utf-8", "latin-1", "cp1252"):
        try:
            with open(filepath, "r", encoding=enc) as f:
                lines = f.readlines()
            break
        except UnicodeDecodeError:
            continue

    if not lines:
        raise ValueError(f"El archivo {filepath.name} está vacío o no se pudo decodificar.")

    data_start_idx = -1

    # Fase 1: Extracción de metadatos y detección del inicio de la tabla numérica
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue

        # Verificar si la línea contiene tokens numéricos (separados por tab o espacio)
        # Reemplazamos coma por punto para prueba de parseo
        test_line = stripped.replace(",", ".")
        tokens = test_line.split()

        if len(tokens) >= 2:
            try:
                # Si ambos tokens son flotantes válidos, hemos alcanzado la matriz de datos
                float(tokens[0])
                float(tokens[1])
                data_start_idx = idx
                break
            except ValueError:
                pass

        # Si aún no es dato numérico, registrar como metadato si contiene separador clave: valor
        if ":" in line:
            parts = line.split(":", 1)
            k = parts[0].strip()
            v = parts[1].strip()
            if k:
                metadata[k] = v

    if data_start_idx == -1:
        raise ValueError(f"No se encontraron columnas numéricas de datos en {filepath.name}.")

    # Fase 2: Carga vectorizada o por filas de la matriz de espectro
    for line in lines[data_start_idx:]:
        stripped = line.strip()
        if not stripped:
            continue
        cleaned = stripped.replace(",", ".")
        tokens = cleaned.split()
        if len(tokens) >= 2:
            try:
                wl = float(tokens[0])
                cnt = float(tokens[1])
                wavelengths.append(wl)
                counts.append(cnt)
            except ValueError:
                continue

    w_arr = np.asarray(wavelengths, dtype=np.float64)
    c_arr = np.asarray(counts, dtype=np.float64)

    # Ordenar por longitud de onda ascendente si viene invertido
    if len(w_arr) > 1 and w_arr[0] > w_arr[-1]:
        w_arr = w_arr[::-1]
        c_arr = c_arr[::-1]

    return metadata, w_arr, c_arr


# ══════════════════════════════════════════════════════════════════════════════
#  2. CONVERSIONES DE COORDENADAS ESPECTRALES
# ══════════════════════════════════════════════════════════════════════════════

def wavelength_to_raman_shift(wavelength_nm: np.ndarray | float, laser_nm: float) -> np.ndarray | float:
    """
    Convierte longitud de onda absoluta (nm) a Corrimiento Raman (cm^-1) respecto al láser.
      Δν (cm^-1) = (1/λ_laser - 1/λ) * 1e7
    """
    if laser_nm <= 0:
        raise ValueError("La longitud de onda del láser debe ser positiva.")
    return (1.0 / laser_nm - 1.0 / np.asarray(wavelength_nm, dtype=np.float64)) * 1e7


def raman_shift_to_wavelength(raman_shift_cm1: np.ndarray | float, laser_nm: float) -> np.ndarray | float:
    """
    Convierte Corrimiento Raman (cm^-1) a longitud de onda absoluta (nm).
      λ (nm) = 1 / (1/λ_laser - Δν * 1e-7)
    """
    if laser_nm <= 0:
        raise ValueError("La longitud de onda del láser debe ser positiva.")
    shift = np.asarray(raman_shift_cm1, dtype=np.float64)
    denom = (1.0 / laser_nm) - (shift * 1e-7)
    # Evitar singularidades
    denom = np.where(np.abs(denom) < 1e-12, 1e-12, denom)
    return 1.0 / denom


def raman_shift_to_ev(raman_shift_cm1: np.ndarray | float) -> np.ndarray | float:
    """Convierte Corrimiento Raman (cm^-1) a energía relativa (eV)."""
    return np.asarray(raman_shift_cm1, dtype=np.float64) * EV_PER_CM1


# ══════════════════════════════════════════════════════════════════════════════
#  3. ELIMINADOR DE RAYOS CÓSMICOS (SPIKE REMOVAL)
# ══════════════════════════════════════════════════════════════════════════════

def remove_cosmic_rays(y: np.ndarray, threshold: float = 6.0, window_size: int = 5) -> Tuple[np.ndarray, np.ndarray]:
    """
    Filtro de detección y remoción de rayos cósmicos (spikes ultra-estrechos)
    típicos en detectores CCD Andor con exposiciones largas.
    
    Utiliza el método de Z-Score modificado sobre los residuales del filtro de mediana.
    Los píxeles identificados como rayos cósmicos se reemplazan por la mediana local.
    
    Retorna:
      y_clean (np.ndarray): Espectro limpio.
      spike_mask (np.ndarray): Máscara booleana (True donde había un spike).
    """
    y = np.asarray(y, dtype=np.float64)
    if len(y) < window_size:
        return y.copy(), np.zeros(len(y), dtype=bool)

    # Mediana local
    y_med = medfilt(y, kernel_size=window_size if window_size % 2 == 1 else window_size + 1)
    diff = y - y_med

    # Z-Score modificado basado en la MAD (Median Absolute Deviation)
    median_diff = np.median(diff)
    mad = np.median(np.abs(diff - median_diff))
    if mad < 1e-9:
        mad = np.std(diff) + 1e-9

    mod_z_score = 0.6745 * (diff - median_diff) / mad

    # Los rayos cósmicos son siempre picos de absorción/emisión positivos artificiales
    spike_mask = (mod_z_score > threshold) & (diff > 0)

    y_clean = y.copy()
    y_clean[spike_mask] = y_med[spike_mask]

    return y_clean, spike_mask


# ══════════════════════════════════════════════════════════════════════════════
#  3.1 PRE-PROCESADO: RECORTE DE BORDES Y SELECCIÓN DE ROI
# ══════════════════════════════════════════════════════════════════════════════

def crop_spectrum(
    x: np.ndarray,
    y: np.ndarray,
    x_min: Optional[float] = None,
    x_max: Optional[float] = None,
    trim_left_pts: int = 0,
    trim_right_pts: int = 0
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Recorta un espectro por rango físico de coordenadas [x_min, x_max]
    y/o podando N puntos de los bordes izquierdo/derecho del sensor CCD.
    
    Retorna:
      (x_cropped, y_cropped, mask)
    """
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    L = len(x)
    if L == 0:
        return x.copy(), y.copy(), np.zeros(0, dtype=bool)

    mask = np.ones(L, dtype=bool)

    # 1. Poda por número de puntos de borde del detector
    if trim_left_pts > 0:
        mask[:min(L, trim_left_pts)] = False
    if trim_right_pts > 0:
        mask[max(0, L - trim_right_pts):] = False

    # 2. Recorte por coordenadas físicas (cm^-1 o nm)
    if x_min is not None:
        mask &= (x >= x_min)
    if x_max is not None:
        mask &= (x <= x_max)

    if not np.any(mask):
        # Si la selección quedó vacía, devolver arrays originales para evitar cuelgues
        return x.copy(), y.copy(), np.ones(L, dtype=bool)

    return x[mask], y[mask], mask


# ══════════════════════════════════════════════════════════════════════════════
#  4. ALGORITMOS DE CORRECCIÓN DE LÍNEA BASE
# ══════════════════════════════════════════════════════════════════════════════

def baseline_asls(y: np.ndarray, lam: float = 1e5, p: float = 0.001, max_iter: int = 20, tol: float = 1e-4) -> np.ndarray:
    """
    Asymmetric Least Squares Smoothing (AsLS) — Eilers & Boelens (2005).
    Estándar en quimiometría para sustraer fondos de fluorescencia ancha en Raman.
    
    Parámetros:
      lam (float): Parámetro de suavidad (1e2 a 1e9). Mayor lambda = línea base más rígida/plana.
      p (float): Parámetro de asimetría (1e-4 a 1e-1). Penaliza desviaciones donde y < z.
    """
    y = np.asarray(y, dtype=np.float64)
    L = len(y)
    D = sparse.diags([1.0, -2.0, 1.0], [0, 1, 2], shape=(L - 2, L), dtype=np.float64, format="csc")
    H = lam * (D.T @ D)
    w = np.ones(L, dtype=np.float64)

    z = y.copy()
    for _ in range(max_iter):
        W = sparse.diags(w, 0, shape=(L, L), dtype=np.float64, format="csc")
        z_new = spsolve(W + H, w * y)
        d = y - z_new
        w_new = np.where(d > 0, p, 1.0 - p)

        if np.linalg.norm(w_new - w) / (np.linalg.norm(w) + 1e-9) < tol:
            z = z_new
            break
        w = w_new
        z = z_new

    return np.asarray(z, dtype=np.float64)


def baseline_airpls(y: np.ndarray, lam: float = 1e5, max_iter: int = 20, tol: float = 1e-4) -> np.ndarray:
    """
    Adaptive Iteratively Reweighted Penalized Least Squares (AirPLS) — Zhang et al. (2010).
    Línea base autorregulada sin necesidad de ajustar manualmente el factor de asimetría p.
    """
    y = np.asarray(y, dtype=np.float64)
    L = len(y)
    D = sparse.diags([1.0, -2.0, 1.0], [0, 1, 2], shape=(L - 2, L), dtype=np.float64, format="csc")
    H = lam * (D.T @ D)
    w = np.ones(L, dtype=np.float64)

    z = y.copy()
    for i in range(1, max_iter + 1):
        W = sparse.diags(w, 0, shape=(L, L), dtype=np.float64, format="csc")
        z = spsolve(W + H, w * y)
        d = y - z

        # Identificar residuales negativos (puntos por debajo de la línea base tentativa)
        d_neg = d[d < 0]
        if len(d_neg) == 0:
            break

        sum_neg = np.abs(np.sum(d_neg))
        if sum_neg < 1e-6:
            break

        # Pesos adaptativos decrecientes exponenciales
        w_new = np.zeros(L)
        mask = d < 0
        w_new[mask] = np.exp(i * np.abs(d[mask]) / sum_neg)
        w_new[d >= 0] = 0.0

        if np.linalg.norm(w_new - w) / (np.linalg.norm(w) + 1e-9) < tol:
            break
        w = w_new

    return np.asarray(z, dtype=np.float64)


def baseline_modpoly(y: np.ndarray, x: Optional[np.ndarray] = None, poly_order: int = 4, max_iter: int = 25, tol: float = 1e-3) -> np.ndarray:
    """
    Modified Polynomial Fitting (ModPoly) — Lieber & Mahadevan-Jansen (2003).
    Ajusta un polinomio de grado N ignorando progresivamente los picos de emisión.
    """
    y = np.asarray(y, dtype=np.float64)
    L = len(y)
    if x is None:
        x_norm = np.linspace(-1.0, 1.0, L)
    else:
        x_norm = 2.0 * (x - np.min(x)) / (np.ptp(x) + 1e-9) - 1.0

    y_work = y.copy()
    coeffs = np.polyfit(x_norm, y_work, poly_order)
    baseline = np.polyval(coeffs, x_norm)

    for _ in range(max_iter):
        # Reemplazar valores donde la señal excede el polinomio (picos)
        y_work = np.minimum(y_work, baseline)
        coeffs_new = np.polyfit(x_norm, y_work, poly_order)
        baseline_new = np.polyval(coeffs_new, x_norm)

        if np.max(np.abs(baseline_new - baseline)) / (np.ptp(y) + 1e-9) < tol:
            baseline = baseline_new
            break
        baseline = baseline_new

    return baseline


def baseline_derivative(y: np.ndarray, window_length: int = 21, polyorder: int = 3, threshold: float = 0.05) -> np.ndarray:
    """
    Corrección de línea base por detección de regiones planas mediante tercera derivada.
    Encuentra zonas donde d³y/dx³ ≈ 0 (ausencia de picos Raman) e interpola lineal/spline.
    """
    y = np.asarray(y, dtype=np.float64)
    L = len(y)
    wl = min(window_length if window_length % 2 == 1 else window_length + 1, L - 1)
    if wl < 5:
        wl = 5
    po = min(polyorder, wl - 1)

    # Tercera derivada vía Savitzky-Golay
    d3 = savgol_filter(y, window_length=wl, polyorder=po, deriv=3)
    d3_norm = np.abs(d3) / (np.max(np.abs(d3)) + 1e-9)

    # Puntos libres de picos
    flat_indices = np.where(d3_norm < threshold)[0]

    # Forzar inclusión de bordes
    flat_indices = np.unique(np.concatenate(([0], flat_indices, [L - 1])))

    # Suavizar puntos de soporte
    baseline_pts = savgol_filter(y[flat_indices], window_length=min(9, len(flat_indices) - (1 - len(flat_indices) % 2)), polyorder=2) if len(flat_indices) > 10 else y[flat_indices]

    # Interpolar sobre toda la grilla
    return np.interp(np.arange(L), flat_indices, baseline_pts)


def baseline_rolling_ball(y: np.ndarray, radius: int = 50) -> np.ndarray:
    """
    Filtro morfológico Top-Hat / Rolling Ball (apertura morfológica 1D).
    Elimina estructuras más anchas que el elemento estructurante (fluorescencia)
    sin podar picos agudos.
    """
    y = np.asarray(y, dtype=np.float64)
    rad = max(3, int(radius))
    # Apertura morfológica: erosión seguida de dilatación
    b_morph = grey_opening(y, size=rad * 2 + 1)
    # Suavizado fino para evitar escalones morfológicos
    return gaussian_filter1d(b_morph, sigma=rad / 4.0)


def baseline_spline_anchors(y: np.ndarray, anchor_indices: List[int]) -> np.ndarray:
    """
    Línea base interactiva manual generada a partir de puntos de anclaje
    seleccionados por el usuario mediante clics en la interfaz gráfica.
    """
    y = np.asarray(y, dtype=np.float64)
    L = len(y)
    if not anchor_indices:
        return np.zeros(L, dtype=np.float64)

    anchors = sorted(set(max(0, min(L - 1, int(idx))) for idx in anchor_indices))
    if anchors[0] != 0:
        anchors.insert(0, 0)
    if anchors[-1] != L - 1:
        anchors.append(L - 1)

    x_anchors = np.array(anchors)
    y_anchors = y[x_anchors]

    return np.interp(np.arange(L), x_anchors, y_anchors)


# ══════════════════════════════════════════════════════════════════════════════
#  5. SUAVIZADO Y FILTRADO ESPECTRAL
# ══════════════════════════════════════════════════════════════════════════════

def smooth_savgol(y: np.ndarray, window_length: int = 11, polyorder: int = 3) -> np.ndarray:
    """Suavizado Savitzky-Golay (preserva altura y área de picos)."""
    y = np.asarray(y, dtype=np.float64)
    wl = window_length if window_length % 2 == 1 else window_length + 1
    wl = max(3, min(wl, len(y) - 1))
    po = min(polyorder, wl - 1)
    return savgol_filter(y, window_length=wl, polyorder=po)


def smooth_fourier(y: np.ndarray, cutoff_fraction: float = 0.15, filter_type: str = "lowpass") -> np.ndarray:
    """
    Filtrado en el dominio de Fourier (FFT):
      - 'lowpass': Remueve ruido de alta frecuencia (shot noise y lectura).
      - 'highpass': Remueve derivas ultralentas.
      - 'notch50': Remueve zumbido de línea de 50 Hz/armónicos.
    """
    y = np.asarray(y, dtype=np.float64)
    n = len(y)
    yf = rfft(y)
    freqs = rfftfreq(n)

    cutoff = max(0.001, min(0.999, cutoff_fraction))
    k = int(cutoff * len(yf))

    if filter_type == "lowpass":
        # Ventana sigmoidea suave en el corte para evitar artefactos de Gibbs
        ramp = 0.5 * (1.0 + np.cos(np.pi * np.clip((np.arange(len(yf)) - k) / max(1, k * 0.2), 0, 1)))
        yf *= ramp
    elif filter_type == "highpass":
        ramp = 0.5 * (1.0 - np.cos(np.pi * np.clip(np.arange(len(yf)) / max(1, k), 0, 1)))
        yf *= ramp
    elif filter_type == "notch50":
        # Suprime componente con ventana notch estrecha
        idx_50 = int(0.25 * len(yf))
        width = max(2, int(0.02 * len(yf)))
        yf[max(0, idx_50 - width):min(len(yf), idx_50 + width)] *= 0.05

    return irfft(yf, n=n)


def smooth_whittaker(y: np.ndarray, lam: float = 1e3) -> np.ndarray:
    """Suavizado Whittaker-Eilers (splines penalizados discretos)."""
    y = np.asarray(y, dtype=np.float64)
    L = len(y)
    D = sparse.diags([1.0, -2.0, 1.0], [0, 1, 2], shape=(L - 2, L), dtype=np.float64, format="csc")
    H = lam * (D.T @ D)
    I_sp = sparse.eye(L, dtype=np.float64, format="csc")
    return np.asarray(spsolve(I_sp + H, y), dtype=np.float64)


def smooth_gaussian(y: np.ndarray, sigma: float = 2.0) -> np.ndarray:
    """Suavizado Gaussiano 1D clásico."""
    return gaussian_filter1d(np.asarray(y, dtype=np.float64), sigma=max(0.1, float(sigma)))


# ══════════════════════════════════════════════════════════════════════════════
#  6. DETECCIÓN Y AJUSTE ESPECTRAL DE PICOS (LORENTZ / VOIGT)
# ══════════════════════════════════════════════════════════════════════════════

def detect_peaks_spectrum(
    x: np.ndarray,
    y: np.ndarray,
    prominence: Optional[float] = None,
    distance: int = 5,
    height: Optional[float] = None,
    width_min_units: Optional[float] = None,
    width_max_units: Optional[float] = None,
    sort_by: str = "position"
) -> List[Dict[str, float]]:
    """
    Encuentra picos espectrales Raman usando scipy.signal.find_peaks con filtros físicos.
    
    Parámetros:
      prominence (float | None): Prominencia mínima. Si es None, toma 5% del ptp.
      distance (int): Separación mínima en puntos entre picos.
      height (float | None): Umbral mínimo de cuentas absolutas sobre la línea base.
      width_min_units (float | None): Ancho FWHM mínimo en unidades de X (cm^-1 o nm).
      width_max_units (float | None): Ancho FWHM máximo en unidades de X (cm^-1 o nm).
      sort_by (str): Criterio de ordenamiento: 'position' (ascendente), 'prominence' o 'intensity'.
    """
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)

    if len(x) < 3:
        return []

    dx = float(np.mean(np.diff(x))) if len(x) > 1 else 1.0
    abs_dx = max(1e-6, abs(dx))

    # Convertir anchos en unidades físicas a puntos del array
    pts_w_min = max(1.0, width_min_units / abs_dx) if width_min_units is not None else None
    pts_w_max = max(1.0, width_max_units / abs_dx) if width_max_units is not None else None
    width_param = None
    if pts_w_min is not None and pts_w_max is not None:
        width_param = (min(pts_w_min, pts_w_max), max(pts_w_min, pts_w_max))
    elif pts_w_min is not None:
        width_param = (pts_w_min, None)
    elif pts_w_max is not None:
        width_param = (None, pts_w_max)

    if prominence is None:
        prominence = 0.05 * float(np.ptp(y))

    indices, props = find_peaks(
        y,
        prominence=prominence,
        distance=max(1, int(distance)),
        height=height,
        width=width_param
    )

    results = []
    for i, idx in enumerate(indices):
        fwhm_pts = float(props["widths"][i]) if "widths" in props else 5.0
        results.append({
            "index": int(idx),
            "position": float(x[idx]),
            "intensity": float(y[idx]),
            "prominence": float(props["prominences"][i]) if "prominences" in props else 0.0,
            "fwhm_est": float(fwhm_pts * abs_dx)
        })

    # Ordenamiento configurable
    if sort_by == "position":
        results.sort(key=lambda item: item["position"])
    elif sort_by == "intensity":
        results.sort(key=lambda item: item["intensity"], reverse=True)
    else:  # 'prominence'
        results.sort(key=lambda item: item["prominence"], reverse=True)

    return results


# ── Funciones de perfil espectral para ajuste no lineal ───────────────────────

def model_gaussian(x: np.ndarray, amp: float, center: float, fwhm: float) -> np.ndarray:
    """Perfil Gaussiano parametrizado por Amplitud, Centro y FWHM."""
    sigma = fwhm / (2.0 * math.sqrt(2.0 * math.log(2.0)) + 1e-9)
    return amp * np.exp(-0.5 * ((x - center) / (sigma + 1e-9)) ** 2)


def model_lorentzian(x: np.ndarray, amp: float, center: float, fwhm: float) -> np.ndarray:
    """Perfil Lorentziano estándar para vidas medias vibracionales moleculares."""
    gamma = fwhm / 2.0
    return amp * (gamma**2) / ((x - center)**2 + gamma**2 + 1e-9)


def model_pseudo_voigt(x: np.ndarray, amp: float, center: float, fwhm: float, eta: float) -> np.ndarray:
    """
    Combinación lineal Pseudo-Voigt:
      V(x) = eta * Lorentzian(x) + (1 - eta) * Gaussian(x), con 0 <= eta <= 1.
    """
    eta = max(0.0, min(1.0, eta))
    return eta * model_lorentzian(x, amp, center, fwhm) + (1.0 - eta) * model_gaussian(x, amp, center, fwhm)


def fit_peak_profile(
    x: np.ndarray,
    y: np.ndarray,
    center_guess: float,
    fwhm_guess: float = 15.0,
    model_type: str = "pseudo_voigt",
    roi_width: Optional[float] = None
) -> Optional[Dict[str, Union[float, np.ndarray, str]]]:
    """
    Ajusta una banda espectral en una región de interés (ROI) alrededor del pico.
    
    Retorna un diccionario con los parámetros óptimos del ajuste:
      - 'center': Posición del centro ajustado
      - 'amplitude': Amplitud pico
      - 'fwhm': Ancho a media altura ajustado
      - 'area': Área integrada analítica de la banda
      - 'eta': Fracción Lorentziana (si modelo es pseudo_voigt)
      - 'model': Tipo de modelo ajustado
      - 'fit_x': Vector X del ajuste
      - 'fit_y': Vector Y evaluado
      - 'r_squared': Coeficiente de determinación R^2
    """
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)

    if roi_width is None:
        roi_width = 3.0 * abs(fwhm_guess)

    mask = (x >= center_guess - roi_width) & (x <= center_guess + roi_width)
    x_sub = x[mask]
    y_sub = y[mask]

    if len(x_sub) < 5:
        return None

    amp_guess = max(float(np.max(y_sub)), 1e-3)
    fwhm_init = max(float(abs(fwhm_guess)), 1.0)

    try:
        if model_type == "gaussian":
            popt, _ = curve_fit(
                model_gaussian, x_sub, y_sub,
                p0=[amp_guess, center_guess, fwhm_init],
                bounds=([0.0, x_sub.min(), 0.1], [amp_guess * 5.0, x_sub.max(), roi_width * 2.0]),
                maxfev=2000
            )
            fit_curve = model_gaussian(x_sub, *popt)
            area = popt[0] * popt[2] * math.sqrt(math.pi / (4.0 * math.log(2.0)))
            eta_val = 0.0

        elif model_type == "lorentzian":
            popt, _ = curve_fit(
                model_lorentzian, x_sub, y_sub,
                p0=[amp_guess, center_guess, fwhm_init],
                bounds=([0.0, x_sub.min(), 0.1], [amp_guess * 5.0, x_sub.max(), roi_width * 2.0]),
                maxfev=2000
            )
            fit_curve = model_lorentzian(x_sub, *popt)
            area = popt[0] * popt[2] * math.pi / 2.0
            eta_val = 1.0

        else:  # pseudo_voigt por defecto
            popt, _ = curve_fit(
                model_pseudo_voigt, x_sub, y_sub,
                p0=[amp_guess, center_guess, fwhm_init, 0.5],
                bounds=([0.0, x_sub.min(), 0.1, 0.0], [amp_guess * 5.0, x_sub.max(), roi_width * 2.0, 1.0]),
                maxfev=2000
            )
            fit_curve = model_pseudo_voigt(x_sub, *popt)
            area_gauss = popt[0] * popt[2] * math.sqrt(math.pi / (4.0 * math.log(2.0)))
            area_lorentz = popt[0] * popt[2] * math.pi / 2.0
            area = popt[3] * area_lorentz + (1.0 - popt[3]) * area_gauss
            eta_val = popt[3]

        # Cálculo de bondad de ajuste R^2
        ss_res = np.sum((y_sub - fit_curve) ** 2)
        ss_tot = np.sum((y_sub - np.mean(y_sub)) ** 2) + 1e-9
        r2 = max(0.0, 1.0 - (ss_res / ss_tot))

        return {
            "center": float(popt[1]),
            "amplitude": float(popt[0]),
            "fwhm": float(popt[2]),
            "area": float(area),
            "eta": float(eta_val),
            "model": model_type,
            "fit_x": x_sub,
            "fit_y": fit_curve,
            "r_squared": float(r2)
        }
    except Exception:
        return None


def fit_multi_peak_profile(
    x: np.ndarray,
    y: np.ndarray,
    peak_centers: List[float],
    fwhm_guess: float = 15.0,
    model_type: str = "pseudo_voigt"
) -> Optional[Dict[str, Union[float, np.ndarray, List[Dict[str, float]], str]]]:
    """
    Ajusta simultáneamente múltiples picos superpuestos (deconvolución multi-pico)
    en una región espectral de interés.
    """
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)

    if len(peak_centers) == 0 or len(x) < len(peak_centers) * 3:
        return None

    n_peaks = len(peak_centers)
    dx = abs(np.mean(np.diff(x))) if len(x) > 1 else 1.0

    # Construir función del modelo compuesto
    if model_type == "gaussian":
        def multi_model(x_eval, *params):
            val = np.zeros_like(x_eval)
            for k in range(n_peaks):
                a = params[3 * k]
                c = params[3 * k + 1]
                w = params[3 * k + 2]
                val += model_gaussian(x_eval, a, c, w)
            return val

        p0, lower, upper = [], [], []
        for c in peak_centers:
            amp_local = float(np.interp(c, x, y))
            p0.extend([max(1.0, amp_local), c, max(2.0, fwhm_guess)])
            lower.extend([0.0, c - 30.0 * dx, 0.5])
            upper.extend([max(10.0, amp_local * 5.0), c + 30.0 * dx, 250.0])

    elif model_type == "lorentzian":
        def multi_model(x_eval, *params):
            val = np.zeros_like(x_eval)
            for k in range(n_peaks):
                a = params[3 * k]
                c = params[3 * k + 1]
                w = params[3 * k + 2]
                val += model_lorentzian(x_eval, a, c, w)
            return val

        p0, lower, upper = [], [], []
        for c in peak_centers:
            amp_local = float(np.interp(c, x, y))
            p0.extend([max(1.0, amp_local), c, max(2.0, fwhm_guess)])
            lower.extend([0.0, c - 30.0 * dx, 0.5])
            upper.extend([max(10.0, amp_local * 5.0), c + 30.0 * dx, 250.0])

    else:  # pseudo_voigt
        def multi_model(x_eval, *params):
            val = np.zeros_like(x_eval)
            for k in range(n_peaks):
                a = params[4 * k]
                c = params[4 * k + 1]
                w = params[4 * k + 2]
                e = params[4 * k + 3]
                val += model_pseudo_voigt(x_eval, a, c, w, e)
            return val

        p0, lower, upper = [], [], []
        for c in peak_centers:
            amp_local = float(np.interp(c, x, y))
            p0.extend([max(1.0, amp_local), c, max(2.0, fwhm_guess), 0.5])
            lower.extend([0.0, c - 30.0 * dx, 0.5, 0.0])
            upper.extend([max(10.0, amp_local * 5.0), c + 30.0 * dx, 250.0, 1.0])

    try:
        popt, _ = curve_fit(multi_model, x, y, p0=p0, bounds=(lower, upper), maxfev=6000)
        fit_y = multi_model(x, *popt)

        sub_peaks = []
        stride = 4 if model_type == "pseudo_voigt" else 3
        for k in range(n_peaks):
            a_k = float(popt[stride * k])
            c_k = float(popt[stride * k + 1])
            w_k = float(popt[stride * k + 2])
            eta_k = float(popt[stride * k + 3]) if model_type == "pseudo_voigt" else (1.0 if model_type == "lorentzian" else 0.0)

            # Área individual
            area_gauss = a_k * w_k * math.sqrt(math.pi / (4.0 * math.log(2.0)))
            area_lorentz = a_k * w_k * math.pi / 2.0
            area_k = eta_k * area_lorentz + (1.0 - eta_k) * area_gauss

            sub_peaks.append({
                "center": c_k,
                "amplitude": a_k,
                "fwhm": w_k,
                "eta": eta_k,
                "area": area_k
            })

        ss_res = np.sum((y - fit_y) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2) + 1e-9
        r2 = max(0.0, 1.0 - (ss_res / ss_tot))

        return {
            "model": model_type,
            "fit_x": x,
            "fit_y": fit_y,
            "peaks": sub_peaks,
            "r_squared": float(r2)
        }
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════════════
#  7. TERMOMETRÍA FOTOTÉRMICA ANTI-STOKES / STOKES
# ══════════════════════════════════════════════════════════════════════════════

def calculate_photothermal_temperature(
    shift_cm1: float,
    intensity_stokes: float,
    intensity_anti_stokes: float,
    laser_nm: float
) -> Tuple[float, float]:
    """
    Calcula la temperatura local absoluta T (Kelvin y Celsius) mediante la
    relación de Boltzmann entre bandas conjugadas Stokes y Anti-Stokes:
    
      I_AS / I_S = [(ν_0 + ν_vib)/(ν_0 - ν_vib)]^4 * exp(-h * c * ν_vib / (k_B * T))
    
    Retorna:
      (T_kelvin, T_celsius)
    """
    shift = abs(float(shift_cm1))
    i_s = max(1e-6, float(intensity_stokes))
    i_as = max(1e-6, float(intensity_anti_stokes))

    # Frecuencias absolutas en cm^-1
    laser_cm1 = 1e7 / float(laser_nm)
    nu_stokes = laser_cm1 - shift
    nu_anti_stokes = laser_cm1 + shift

    # Factor de corrección por dispersión dipolar (omega^4)
    omega_factor = (nu_anti_stokes / max(1.0, nu_stokes)) ** 4

    ratio = i_as / (i_s * omega_factor)
    if ratio <= 0.0 or ratio >= 1.0:
        # Físicamente imposible o ruido excesivo (anti-stokes más intenso que stokes)
        # Si ratio >= 1.0 la temperatura tendería a infinito
        return float("nan"), float("nan")

    # T = (h * c * ν) / (k_B * -ln(ratio))
    delta_energy = PLANCK_CONSTANT * SPEED_OF_LIGHT * shift
    t_kelvin = delta_energy / (BOLTZMANN_CONST * (-math.log(ratio)))
    t_celsius = t_kelvin - 273.15

    return float(t_kelvin), float(t_celsius)


# ══════════════════════════════════════════════════════════════════════════════
#  8. METROLOGÍA DUAL & INTEGRACIÓN NUMÉRICA
# ══════════════════════════════════════════════════════════════════════════════

def compute_dual_cursor_metrics(x: np.ndarray, y: np.ndarray, pos_a: float, pos_b: float) -> Dict[str, float]:
    """
    Calcula magnitudes cuantitativas entre dos cursores interactivos (Regla A y Regla B):
      - delta_x: Separación espectral (cm^-1 o nm)
      - delta_y: Diferencia de intensidad
      - ratio_y: Cociente I_B / I_A (e.g. cociente de intensidades D/G en carbono o SERS)
      - integrated_area: Integral numérica de Simpson / Trapezoidal bajo la curva entre A y B
    """
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)

    if len(x) != len(y) or len(x) < 2:
        return {
            "pos_a": float(pos_a),
            "pos_b": float(pos_b),
            "val_a": 0.0,
            "val_b": 0.0,
            "delta_x": float(abs(pos_b - pos_a)),
            "delta_y": 0.0,
            "ratio_ba": 0.0,
            "integrated_area": 0.0
        }

    x_min = min(pos_a, pos_b)
    x_max = max(pos_a, pos_b)

    # np.interp exige que xp sea monotónicamente creciente
    if x[0] > x[-1]:
        x_interp = x[::-1]
        y_interp = y[::-1]
    else:
        x_interp = x
        y_interp = y

    # Valor interpolado exacto en las posiciones de los cursores
    y_a = float(np.interp(pos_a, x_interp, y_interp))
    y_b = float(np.interp(pos_b, x_interp, y_interp))

    mask = (x >= x_min) & (x <= x_max)
    x_sub = x[mask]
    y_sub = y[mask]

    if len(x_sub) >= 2:
        # Asegurar orden creciente para la integración trapezoidal
        if x_sub[0] > x_sub[-1]:
            x_sub = x_sub[::-1]
            y_sub = y_sub[::-1]
        area = float(np.trapezoid(y_sub, x_sub) if hasattr(np, "trapezoid") else np.trapz(y_sub, x_sub))
    else:
        area = 0.0

    ratio = (y_b / y_a) if abs(y_a) > 1e-9 else float("inf")

    return {
        "pos_a": float(pos_a),
        "pos_b": float(pos_b),
        "val_a": float(y_a),
        "val_b": float(y_b),
        "delta_x": float(abs(pos_b - pos_a)),
        "delta_y": float(y_b - y_a),
        "ratio_ba": float(ratio),
        "integrated_area": float(area)
    }


# ══════════════════════════════════════════════════════════════════════════════
#  9. MOTOR MULTI-ESPECTRO & ANÁLISIS EN LOTE (BATCH SPECTROSCOPY)
# ══════════════════════════════════════════════════════════════════════════════

def interpolate_spectra_to_common_grid(
    spectra: List[Tuple[np.ndarray, np.ndarray, str, Dict]],
    num_points: Optional[int] = None
) -> Tuple[np.ndarray, np.ndarray, List[str], List[Dict]]:
    """
    Toma una lista de tuplas (x_i, y_i, nombre, metadatos) e interpola todos los espectros
    sobre una grilla común x_common.
    Retorna:
      x_common: array 1D de longitud M (monotónicamente creciente)
      Y_matrix: array 2D de forma (N, M) con cada espectro en una fila
      names: lista de nombres válidos
      metas: lista de metadatos correspondientes
    """
    if not spectra:
        return np.array([]), np.empty((0, 0)), [], []

    cleaned = []
    x_mins = []
    x_maxs = []
    for item in spectra:
        x_i, y_i, name, meta = item[0], item[1], item[2], item[3] if len(item) > 3 else {}
        x_arr = np.asarray(x_i, dtype=np.float64)
        y_arr = np.asarray(y_i, dtype=np.float64)
        if len(x_arr) < 2 or len(x_arr) != len(y_arr):
            continue
        if x_arr[0] > x_arr[-1]:
            x_arr = x_arr[::-1]
            y_arr = y_arr[::-1]
        cleaned.append((x_arr, y_arr, str(name), dict(meta)))
        x_mins.append(float(x_arr.min()))
        x_maxs.append(float(x_arr.max()))

    if not cleaned:
        return np.array([]), np.empty((0, 0)), [], []

    # El rango común es la intersección máxima para no inventar datos extrapolados
    global_min = max(x_mins) if max(x_mins) < min(x_maxs) else min(x_mins)
    global_max = min(x_maxs) if max(x_mins) < min(x_maxs) else max(x_maxs)

    if num_points is None:
        num_points = int(np.median([len(c[0]) for c in cleaned]))
        num_points = max(num_points, 100)

    x_common = np.linspace(global_min, global_max, num_points)
    Y_matrix = np.zeros((len(cleaned), num_points), dtype=np.float64)
    names = [c[2] for c in cleaned]
    metas = [c[3] for c in cleaned]

    for i, (x_arr, y_arr, _, _) in enumerate(cleaned):
        Y_matrix[i, :] = np.interp(x_common, x_arr, y_arr)

    return x_common, Y_matrix, names, metas


def normalize_spectrum_matrix(
    x: np.ndarray,
    Y: np.ndarray,
    mode: str = "max",
    ref_pos: Optional[float] = None,
    half_window: float = 20.0
) -> np.ndarray:
    """
    Normaliza una matriz de espectros Y (N_espectros, M_puntos) según el modo:
      - 'none': sin cambios
      - 'max': escala cada espectro a su máximo global: Y_i / max(Y_i)
      - 'min_max': escala cada espectro al rango [0, 1]
      - 'peak': escala según la intensidad del pico más cercano a ref_pos (+/- half_window)
      - 'area': normaliza por la integral trapezoidal (área unitaria = 1.0)
      - 'snv': Standard Normal Variate (y - mean) / std
    """
    if Y.size == 0:
        return Y.copy()

    Y_out = Y.copy().astype(np.float64)
    N, M = Y_out.shape

    if mode == "none":
        return Y_out

    elif mode == "max":
        for i in range(N):
            m = np.max(Y_out[i, :])
            if abs(m) > 1e-12:
                Y_out[i, :] /= m

    elif mode == "min_max":
        for i in range(N):
            y_min = np.min(Y_out[i, :])
            y_max = np.max(Y_out[i, :])
            ptp = y_max - y_min
            if ptp > 1e-12:
                Y_out[i, :] = (Y_out[i, :] - y_min) / ptp

    elif mode == "peak":
        if ref_pos is None and len(x) > 0:
            ref_pos = float(x[len(x) // 2])
        mask = (x >= (ref_pos - half_window)) & (x <= (ref_pos + half_window)) if ref_pos is not None else np.ones(M, dtype=bool)
        if not np.any(mask):
            mask = np.ones(M, dtype=bool)

        for i in range(N):
            peak_val = np.max(Y_out[i, mask])
            if abs(peak_val) > 1e-12:
                Y_out[i, :] /= peak_val

    elif mode == "area":
        for i in range(N):
            if hasattr(np, "trapezoid"):
                area = float(np.trapezoid(np.abs(Y_out[i, :]), x))
            else:
                area = float(np.trapz(np.abs(Y_out[i, :]), x))
            if abs(area) > 1e-12:
                Y_out[i, :] /= area

    elif mode == "snv":
        for i in range(N):
            mu = np.mean(Y_out[i, :])
            std = np.std(Y_out[i, :])
            if std > 1e-12:
                Y_out[i, :] = (Y_out[i, :] - mu) / std

    return Y_out


def compute_mean_std_spectrum(Y: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Calcula el espectro promedio, desviación estándar y RSD% (coeficiente de variación)
    a lo largo del conjunto de espectros Y (N, M).
    Retorna:
      mean_y: array 1D de longitud M
      std_y: array 1D de longitud M
      rsd_percent: array 1D (std / |mean| * 100)
    """
    if Y.size == 0:
        return np.array([]), np.array([]), np.array([])
    mean_y = np.mean(Y, axis=0)
    std_y = np.std(Y, axis=0)
    denom = np.where(np.abs(mean_y) > 1e-9, np.abs(mean_y), 1e-9)
    rsd_percent = (std_y / denom) * 100.0
    return mean_y, std_y, rsd_percent


def extract_band_kinetics(
    x: np.ndarray,
    Y: np.ndarray,
    pos_min: float,
    pos_max: float
) -> Dict[str, np.ndarray]:
    """
    Extrae la evolución de una banda espectral a lo largo de los N espectros de la serie:
      - heights: Altura máxima neta dentro de [pos_min, pos_max]
      - areas: Integral numérica en la banda
      - positions: Posición exacta del máximo local para cada espectro
    """
    if Y.size == 0 or len(x) == 0:
        return {"heights": np.array([]), "areas": np.array([]), "positions": np.array([])}

    x_min = min(pos_min, pos_max)
    x_max = max(pos_min, pos_max)
    mask = (x >= x_min) & (x <= x_max)
    if not np.any(mask):
        mask = np.ones(len(x), dtype=bool)

    x_sub = x[mask]
    N = Y.shape[0]
    heights = np.zeros(N)
    areas = np.zeros(N)
    positions = np.zeros(N)

    for i in range(N):
        y_sub = Y[i, mask]
        max_idx = int(np.argmax(y_sub))
        heights[i] = float(y_sub[max_idx])
        positions[i] = float(x_sub[max_idx])
        if len(x_sub) >= 2:
            areas[i] = float(np.trapezoid(y_sub, x_sub) if hasattr(np, "trapezoid") else np.trapz(y_sub, x_sub))
        else:
            areas[i] = 0.0

    return {
        "heights": heights,
        "areas": areas,
        "positions": positions
    }


def compute_spectral_pca(Y: np.ndarray, n_components: int = 2) -> Dict[str, Any]:
    """
    Realiza Análisis de Componentes Principales (PCA) mediante SVD sobre la matriz de espectros Y (N, M).
    Retorna:
      scores: matriz (N, n_components) con las coordenadas en el espacio de componentes
      loadings: matriz (n_components, M) con los perfiles espectrales de cada componente
      explained_variance: porcentaje de varianza explicada por cada componente
      mean_spectrum: espectro medio restado
    """
    if Y.shape[0] < 2 or Y.shape[1] < 2:
        return {"scores": np.empty((0, 0)), "loadings": np.empty((0, 0)), "explained_variance": np.array([]), "mean_spectrum": np.array([])}

    mean_spectrum = np.mean(Y, axis=0)
    Y_centered = Y - mean_spectrum

    U, S, Vt = np.linalg.svd(Y_centered, full_matrices=False)

    n_comp = min(n_components, len(S), Y.shape[0])
    scores = U[:, :n_comp] * S[:n_comp]
    loadings = Vt[:n_comp, :]

    var_total = np.sum(S**2)
    var_explained = (S[:n_comp]**2) / (var_total + 1e-12) * 100.0

    return {
        "scores": scores,
        "loadings": loadings,
        "explained_variance": var_explained,
        "mean_spectrum": mean_spectrum
    }
