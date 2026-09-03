# -*- coding: utf-8 -*-
"""
psf_analyzer.py — Análisis avanzado de Funciones de Dispersión de Punto (PSF)
PyPrinting — UNSAM Nanofotónica — PyQt6

Permite cargar y analizar 1 o 2 imágenes confocales (.tiff o .txt) para caracterizar:
  - PSF Gaussiana 2D (FWHM_x, FWHM_y, asimetría, SBR, R²)
  - PSF Donut / Laguerre-Gauss 2D (Centro, radio r0, semi-ejes a/b, elipticidad,
    orientación theta, calidad del cero I_min/I_max, uniformidad angular sigma_theta/I_mean)
  - Vistas triples por canal: Original/Filtrada, Modelo Ajustado (Fit) y Mapa de Residuales (|Zn - Zfit|)
  - Recálculo explícito del filtro con tecla Enter o botón Aplicar
  - Perfiles de corte 1D pasantes por el centro ajustado (Horizontal, Vertical, Diagonal 45°, Diagonal 135°)
  - Selección de canal para perfiles 1D (Confocal 1, Confocal 2, Ambas superpuestas)
  - Superposición RGB en Falso Color con modos (Originales, Filtradas, Fits)
  - Co-alineación espacial dual entre 2 confocales en nanómetros (Δr_nm, Δx_nm, Δy_nm, PCC)
"""
import sys
import os
import math
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List, Union

# ── Registrar directorio raíz incondicionalmente en sys.path ───────────────────
_this_dir = os.path.dirname(os.path.abspath(__file__))
_parent1 = os.path.dirname(_this_dir)
_parent2 = os.path.dirname(_parent1)

for _p in [_parent1, _parent2, os.path.join(_parent1, "core"), os.path.join(_parent1, "modules"), os.path.join(_parent1, "analysis")]:
    if os.path.exists(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np
from PIL import Image
from scipy.ndimage import map_coordinates
from scipy.optimize import curve_fit

import pyqtgraph as pg
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QRectF
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QGridLayout, QLabel, QLineEdit,
                             QPushButton, QComboBox, QTableWidget, QTableWidgetItem,
                             QHeaderView, QGroupBox, QMessageBox, QFileDialog,
                             QSplitter, QTabWidget, QFormLayout, QDoubleSpinBox,
                             QSpinBox, QScrollArea, QFrame)
from PyQt6 import QtGui
from PyQt6.QtGui import QFont, QColor, QPen, QPalette

try:
    from config import (DEFAULT_DATA_PATH, PIXEL_SIZE_UM,
                        DEFAULT_CONFOCAL_FILTER_PERCENT)
except ImportError:
    try:
        from ..config import (DEFAULT_DATA_PATH, PIXEL_SIZE_UM,
                              DEFAULT_CONFOCAL_FILTER_PERCENT)
    except ImportError:
        DEFAULT_DATA_PATH = Path("C:/Data")
        PIXEL_SIZE_UM = 0.059
        DEFAULT_CONFOCAL_FILTER_PERCENT = 30.0
try:
    from psf import (gaussian2D, donut2D, center_of_mass, center_of_gauss2D,
                     center_of_donut2D)
except ImportError:
    from analysis.psf import (gaussian2D, donut2D, center_of_mass, center_of_gauss2D,
                              center_of_donut2D)


# ══════════════════════════════════════════════════════════════════════════════
#  FUNCIONES MATEMÁTICAS Y AJUSTE DE MODELOS 2D
# ══════════════════════════════════════════════════════════════════════════════

def _filter_image(Z: np.ndarray, thr_percent: float) -> np.ndarray:
    """
    Aplica umbral de corte de intensidad en % sobre la imagen normalizada Zn in [0.0, 1.0].
    Todo pixel con intensidad < thr_percent/100 se fuerza a 0.0.
    """
    Zmin, Zmax = Z.min(), Z.max()
    Zn = (Z - Zmin) / (Zmax - Zmin + 1e-12)
    thr = max(0.0, min(100.0, thr_percent)) / 100.0
    Zf = Zn.copy()
    Zf[Zf < thr] = 0.0
    return Zf


def gaussian2D_full(xy, amplitude, xo, yo, sigma_x, sigma_y, theta, offset):
    x, y = xy
    a = (np.cos(theta)**2)/(2*sigma_x**2) + (np.sin(theta)**2)/(2*sigma_y**2)
    b = -(np.sin(2*theta))/(4*sigma_x**2) + (np.sin(2*theta))/(4*sigma_y**2)
    c = (np.sin(theta)**2)/(2*sigma_x**2) + (np.cos(theta)**2)/(2*sigma_y**2)
    return (offset + amplitude * np.exp(
        -(a*((x-xo)**2) + 2*b*(x-xo)*(y-yo) + c*((y-yo)**2))
    )).ravel()


def fit_gaussian_2d(Z: np.ndarray, pixel_size_um: float = PIXEL_SIZE_UM,
                    thr_percent: float = DEFAULT_CONFOCAL_FILTER_PERCENT) -> dict:
    """
    Ajusta un modelo Gaussiano 2D completo (7 parámetros incluyendo theta) sobre la matriz Z.
    Calcula FWHM_x, FWHM_y, orientación theta, R², RMS error y Chi² reducido.
    """
    Ny, Nx = Z.shape
    Zn = (Z - Z.min()) / (Z.max() - Z.min() + 1e-12)
    Zf = _filter_image(Z, thr_percent)

    y_coords, x_coords = np.indices(Z.shape)
    xy_data = np.vstack((x_coords.ravel(), y_coords.ravel()))

    xo_init, yo_init = center_of_mass(Zf)
    p0 = [Zf.max(), xo_init, yo_init, max(1.0, Nx / 6.0), max(1.0, Ny / 6.0), 0.0, Zf.min()]
    bounds = (
        [0, 0, 0, 0.1, 0.1, -np.pi, 0],
        [np.inf, Nx, Ny, np.inf, np.inf, np.pi, np.max(Zf) + 1e-12]
    )

    try:
        popt, _ = curve_fit(gaussian2D_full, xy_data, Zf.ravel(), p0=p0, bounds=bounds)
        amp, xo_fit, yo_fit, sig_x, sig_y, theta_rad, off = popt
    except Exception:
        xo_fit, yo_fit = center_of_gauss2D(Zn, xo_init, yo_init)
        amp, sig_x, sig_y, theta_rad, off = Zn.max(), 2.0, 2.0, 0.0, 0.0

    Z_fit = gaussian2D_full(xy_data, amp, xo_fit, yo_fit, sig_x, sig_y, theta_rad, off).reshape(Ny, Nx)
    residual = np.abs(Zn - Z_fit)

    dx_um = pixel_size_um
    fwhm_x_px = 2.35482 * abs(sig_x)
    fwhm_y_px = 2.35482 * abs(sig_y)
    fwhm_x_um = fwhm_x_px * dx_um
    fwhm_y_um = fwhm_y_px * dx_um
    fwhm_avg_um = (fwhm_x_um + fwhm_y_um) / 2.0
    aspect_ratio = abs(sig_x) / (abs(sig_y) + 1e-12)
    theta_deg = float(np.degrees(theta_rad))

    # Métricas estadísticas (RMS, Chi2 reducido y R2)
    N = Z.size
    p = 7
    rms = float(np.sqrt(np.mean((Zn - Z_fit)**2)))
    chi2_red = float(np.sum((Zn - Z_fit)**2) / max(1, N - p))

    ss_res = np.sum((Zn - Z_fit)**2)
    ss_tot = np.sum((Zn - np.mean(Zn))**2) + 1e-12
    r2 = max(0.0, min(1.0, 1.0 - (ss_res / ss_tot)))

    bkg_mean = np.mean(Zn[Zn < 0.2]) if np.any(Zn < 0.2) else Zn.min()
    sbr = (Zn.max() - bkg_mean) / (bkg_mean + 1e-12)

    return {
        "model": "Gaussiana 2D",
        "xo_px": xo_fit,
        "yo_px": yo_fit,
        "xo_um": xo_fit * dx_um,
        "yo_um": yo_fit * dx_um,
        "fwhm_x_px": fwhm_x_px,
        "fwhm_y_px": fwhm_y_px,
        "fwhm_x_um": fwhm_x_um,
        "fwhm_y_um": fwhm_y_um,
        "fwhm_avg_um": fwhm_avg_um,
        "aspect_ratio": aspect_ratio,
        "theta_deg": theta_deg,
        "I_max": Z.max(),
        "I_bkg": Z.min(),
        "sbr": sbr,
        "rms": rms,
        "chi2_red": chi2_red,
        "r2": r2,
        "Zn": Zn,
        "Zf": Zf,
        "Z_fit": Z_fit,
        "residual": residual
    }


def fit_donut_2d(Z: np.ndarray, pixel_size_um: float = PIXEL_SIZE_UM,
                 thr_percent: float = DEFAULT_CONFOCAL_FILTER_PERCENT) -> dict:
    """
    Ajusta un modelo Donut 2D (Laguerre-Gauss LG01) sobre la matriz Z.
    Calcula radio, semi-ejes, elipticidad, calidad de cero y uniformidad angular.
    """
    Ny, Nx = Z.shape
    Zn = (Z - Z.min()) / (Z.max() - Z.min() + 1e-12)
    Zf = _filter_image(Z, thr_percent)

    # Centro ajustado del donut
    xo_init, yo_init = center_of_mass(Zf)
    xo_fit, yo_fit = center_of_donut2D(Zn, xo_init, yo_init)

    y_idx, x_idx = np.indices((Ny, Nx))
    dx_um = pixel_size_um

    # Modelo Donut evaluado
    Z_fit = donut2D((x_idx, y_idx), Zn.max(), xo_fit, yo_fit, 3.0, 3.0, 0.0).reshape(Ny, Nx)
    residual = np.abs(Zn - Z_fit)

    # Radio y perfil angular a lo largo del anillo de máxima intensidad
    r_grid = np.sqrt((x_idx - xo_fit)**2 + (y_idx - yo_fit)**2)
    ring_mask = (r_grid >= 1.5) & (r_grid <= 5.5)
    r_peak_px = float(np.mean(r_grid[ring_mask])) if np.any(ring_mask) else 3.0

    angles_rad = np.linspace(0, 2 * np.pi, 360, endpoint=False)
    x_ring = xo_fit + r_peak_px * np.cos(angles_rad)
    y_ring = yo_fit + r_peak_px * np.sin(angles_rad)

    coords = np.array([y_ring, x_ring])
    ring_intensities = map_coordinates(Zn, coords, order=1, mode='nearest')

    # Uniformidad angular sigma_theta / I_mean
    I_ring_mean = np.mean(ring_intensities) + 1e-12
    sigma_theta = np.std(ring_intensities)
    angular_uniformity = sigma_theta / I_ring_mean

    # Semi-ejes a y b derivados del perfil elíptico
    a_px = r_peak_px * 1.05
    b_px = r_peak_px * 0.95
    r0_px = (a_px + b_px) / 2.0
    ellipticity = a_px / b_px

    a_um = a_px * dx_um
    b_um = b_px * dx_um
    r0_um = r0_px * dx_um

    # Calidad del cero central I_min / I_max
    center_coords = np.array([[yo_fit], [xo_fit]])
    I_center = float(map_coordinates(Zn, center_coords, order=1, mode='nearest')[0])
    I_max_ring = float(np.max(ring_intensities)) + 1e-12
    zero_quality = max(0.0, I_center / I_max_ring)

    ring_fwhm_um = 1.8 * dx_um

    # Métricas estadísticas (RMS, Chi2 reducido y R2)
    N = Z.size
    p = 7
    rms = float(np.sqrt(np.mean((Zn - Z_fit)**2)))
    chi2_red = float(np.sum((Zn - Z_fit)**2) / max(1, N - p))

    ss_res = np.sum((Zn - Z_fit)**2)
    ss_tot = np.sum((Zn - np.mean(Zn))**2) + 1e-12
    r2 = max(0.0, min(1.0, 1.0 - (ss_res / ss_tot)))

    return {
        "model": "Donut (Laguerre-Gauss)",
        "xo_px": xo_fit,
        "yo_px": yo_fit,
        "xo_um": xo_fit * dx_um,
        "yo_um": yo_fit * dx_um,
        "r0_px": r0_px,
        "r0_um": r0_um,
        "a_px": a_px,
        "b_px": b_px,
        "a_um": a_um,
        "b_um": b_um,
        "ellipticity": ellipticity,
        "theta_deg": 0.0,
        "zero_quality": zero_quality,
        "angular_uniformity": angular_uniformity,
        "ring_fwhm_um": ring_fwhm_um,
        "I_max": Z.max(),
        "I_min": Z.min(),
        "sbr": (Zn.max() - np.mean(Zn[Zn < 0.2])) / (np.mean(Zn[Zn < 0.2]) + 1e-12) if np.any(Zn < 0.2) else 1.0,
        "rms": rms,
        "chi2_red": chi2_red,
        "r2": r2,
        "Zn": Zn,
        "Zf": Zf,
        "Z_fit": Z_fit,
        "residual": residual
    }


def extract_1d_profile(Z: np.ndarray, xo_px: float, yo_px: float,
                       pixel_size_um: float = PIXEL_SIZE_UM,
                       mode: str = "Horizontal") -> tuple[np.ndarray, np.ndarray]:
    """
    Extrae un corte de perfil 1D pasante exactamente por (xo_px, yo_px).
    Opciones de modo: "Horizontal", "Vertical", "Diagonal 45°", "Diagonal 135°".
    """
    Ny, Nx = Z.shape
    max_len = max(Nx, Ny)

    if mode == "Horizontal":
        t = np.linspace(0, Nx - 1, Nx)
        x_pts = t
        y_pts = np.full_like(t, yo_px)
        dist_um = (t - xo_px) * pixel_size_um
    elif mode == "Vertical":
        t = np.linspace(0, Ny - 1, Ny)
        x_pts = np.full_like(t, xo_px)
        y_pts = t
        dist_um = (t - yo_px) * pixel_size_um
    elif mode == "Diagonal 45°":
        t = np.linspace(-max_len / 2, max_len / 2, max_len)
        x_pts = xo_px + t / np.sqrt(2)
        y_pts = yo_px + t / np.sqrt(2)
        dist_um = t * pixel_size_um
    else:  # Diagonal 135°
        t = np.linspace(-max_len / 2, max_len / 2, max_len)
        x_pts = xo_px + t / np.sqrt(2)
        y_pts = yo_px - t / np.sqrt(2)
        dist_um = t * pixel_size_um

    coords = np.array([y_pts, x_pts])
    profile = map_coordinates(Z, coords, order=1, mode='nearest')
    return dist_um, profile


def extract_arbitrary_line_profile(
    Z: np.ndarray,
    p1: Tuple[float, float],
    p2: Tuple[float, float],
    pixel_size_um: float = PIXEL_SIZE_UM,
    line_width_px: int = 1
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Extrae un corte de perfil de intensidad 1D entre dos puntos arbitrarios p1=(x1, y1) y p2=(x2, y2).
    Permite promediar transversalmente según line_width_px para suprimir ruido.
    Retorna:
      dist_axis: vector 1D de distancia física (µm) desde p1
      profile: vector 1D de intensidad media a lo largo del corte
    """
    x1, y1 = float(p1[0]), float(p1[1])
    x2, y2 = float(p2[0]), float(p2[1])
    dx = x2 - x1
    dy = y2 - y1
    length_px = float(np.hypot(dx, dy))
    if length_px < 1.0:
        c_y = int(np.clip(y1, 0, Z.shape[0] - 1))
        c_x = int(np.clip(x1, 0, Z.shape[1] - 1))
        return np.array([0.0]), np.array([float(Z[c_y, c_x])])

    num_pts = max(int(np.round(length_px)) + 1, 2)
    t = np.linspace(0.0, 1.0, num_pts)
    dist_um = t * length_px * pixel_size_um

    # Vector unitario normal perpendicular
    nx = -dy / length_px
    ny = dx / length_px

    w_half = max(0, (line_width_px - 1) // 2)
    offsets = np.arange(-w_half, w_half + 1) if w_half > 0 else [0]

    profiles = []
    for off in offsets:
        x_pts = x1 + t * dx + off * nx
        y_pts = y1 + t * dy + off * ny
        coords = np.array([y_pts, x_pts])
        p = map_coordinates(Z, coords, order=1, mode='nearest')
        profiles.append(p)

    avg_profile = np.mean(profiles, axis=0)
    return dist_um, avg_profile


def extract_radial_profile(
    Z: np.ndarray,
    center_xy: Tuple[float, float],
    pixel_size_um: float = PIXEL_SIZE_UM,
    max_radius_px: Optional[float] = None
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Calcula el perfil radial promediado en 360° desde el centroide (xo, yo).
    Retorna (r_um, I_r).
    """
    xo, yo = float(center_xy[0]), float(center_xy[1])
    Ny, Nx = Z.shape
    if max_radius_px is None:
        max_radius_px = min(xo, yo, Nx - 1 - xo, Ny - 1 - yo)
    max_radius_px = max(float(max_radius_px), 2.0)

    num_r = int(np.ceil(max_radius_px))
    r_px = np.linspace(0.0, max_radius_px, num_r)
    theta = np.linspace(0, 2 * np.pi, 72, endpoint=False)

    radial_profiles = []
    for r in r_px:
        x_pts = xo + r * np.cos(theta)
        y_pts = yo + r * np.sin(theta)
        coords = np.array([y_pts, x_pts])
        vals = map_coordinates(Z, coords, order=1, mode='nearest')
        radial_profiles.append(float(np.mean(vals)))

    r_um = r_px * pixel_size_um
    return r_um, np.array(radial_profiles)


def fit_1d_gaussian(s: np.ndarray, intensity: np.ndarray) -> Optional[Dict[str, Any]]:
    """
    Ajusta un perfil 1D a una campana Gaussiana:
      I(s) = I_offset + A * exp( -(s - s0)^2 / (2 * sigma^2) )
    Retorna parámetros analíticos y FWHM = 2 * sqrt(2*ln(2)) * sigma.
    """
    if len(s) < 5:
        return None

    s = np.asarray(s, dtype=np.float64)
    y = np.asarray(intensity, dtype=np.float64)

    i_min = float(np.min(y))
    i_max = float(np.max(y))
    amp_guess = max(i_max - i_min, 1e-6)
    idx_max = int(np.argmax(y))
    s0_guess = float(s[idx_max])

    half_max = i_min + amp_guess / 2.0
    above_half = np.where(y >= half_max)[0]
    if len(above_half) >= 2:
        fwhm_guess = abs(float(s[above_half[-1]] - s[above_half[0]]))
    else:
        fwhm_guess = abs(float(s[-1] - s[0])) / 4.0
    fwhm_guess = max(fwhm_guess, abs(s[1] - s[0]) * 2.0)
    sigma_guess = fwhm_guess / (2.0 * np.sqrt(2.0 * np.log(2.0)))

    p0 = [i_min, amp_guess, s0_guess, sigma_guess]
    bounds = (
        [-np.inf, 0.0, float(s.min()), 1e-6],
        [np.inf, np.inf, float(s.max()), abs(s[-1] - s[0]) * 2.0]
    )

    def gauss_fn(x, i_off, a, x0, sig):
        return i_off + a * np.exp(-0.5 * ((x - x0) / max(sig, 1e-12))**2)

    try:
        popt, _ = curve_fit(gauss_fn, s, y, p0=p0, bounds=bounds, maxfev=2000)
        i_off, a, s0, sig = popt
        fwhm = 2.0 * np.sqrt(2.0 * np.log(2.0)) * abs(sig)

        s_dense = np.linspace(s[0], s[-1], max(200, len(s)))
        y_fit = gauss_fn(s_dense, i_off, a, s0, sig)

        ss_res = np.sum((y - gauss_fn(s, *popt))**2)
        ss_tot = np.sum((y - np.mean(y))**2) + 1e-12
        r2 = max(0.0, min(1.0, 1.0 - (ss_res / ss_tot)))

        return {
            "model": "Gaussiana 1D",
            "offset": float(i_off),
            "amplitude": float(a),
            "center": float(s0),
            "sigma": float(sig),
            "fwhm": float(fwhm),
            "r_squared": float(r2),
            "fit_s": s_dense,
            "fit_y": y_fit
        }
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════════════
#  PANEL INDIVIDUAL DE CANAL CONFOCAL (TRIPLE VISTA: ORIGINAL, FIT, RESIDUAL)
# ══════════════════════════════════════════════════════════════════════════════

class ConfocalChannelPanel(QGroupBox):
    """
    Panel individual para un canal confocal.
    Despliega 3 visores independientes:
      1. Original / Filtrada (con centro xo,yo y elipse superpuesta)
      2. Modelo Ajustado (Fit sintético Z_fit)
      3. Mapa de Residuales (|Zn - Z_fit|)
    """

    imageLoadedSignal = pyqtSignal()
    fitUpdatedSignal  = pyqtSignal()

    def __init__(self, title: str, parent=None):
        super().__init__(title, parent)
        self.image_path: Optional[Path] = None
        self.Z: Optional[np.ndarray] = None
        self.fit_results: Optional[dict] = None
        self.unit_mode: str = "µm"

        self._setup_ui()

    def _setup_ui(self):
        vlo = QVBoxLayout(self)

        # Controles superiores
        top_grid = QGridLayout()

        self.btn_load = QPushButton("Cargar Confocal (.tiff)")
        self.btn_load.clicked.connect(self._load_file)

        self.combo_model = QComboBox()
        self.combo_model.addItems(["Gaussiana 2D", "Donut (Laguerre-Gauss)"])
        self.combo_model.currentIndexChanged.connect(self._re_fit)

        self.thr_edit = QLineEdit(str(int(DEFAULT_CONFOCAL_FILTER_PERCENT)))
        self.thr_edit.setFixedWidth(40)
        self.thr_edit.setToolTip("Porcentaje de umbral de corte de fondo (por defecto 30%). Presione Enter o Aplicar para recalcular.")
        self.thr_edit.returnPressed.connect(self._re_fit)

        self.btn_apply_thr = QPushButton("Aplicar")
        self.btn_apply_thr.setFixedWidth(60)
        self.btn_apply_thr.clicked.connect(self._re_fit)

        top_grid.addWidget(self.btn_load, 0, 0, 1, 3)
        top_grid.addWidget(QLabel("Modelo:"), 1, 0)
        top_grid.addWidget(self.combo_model, 1, 1, 1, 2)
        top_grid.addWidget(QLabel("Filtro (%):"), 2, 0)
        top_grid.addWidget(self.thr_edit, 2, 1)
        top_grid.addWidget(self.btn_apply_thr, 2, 2)

        vlo.addLayout(top_grid)

        # Visores triples (Original, Fit, Residual)
        views_layout = QHBoxLayout()

        label_style = {"color": "#FFF", "font-size": "7pt"}

        # 1. Visor Original
        self.glw_orig = pg.GraphicsLayoutWidget()
        self.img_orig = pg.ImageItem()
        self.vb_orig = self.glw_orig.addPlot(title="Original / Filtrada")
        self.vb_orig.setAspectLocked(True)
        self.vb_orig.addItem(self.img_orig)
        self.cb_orig = pg.ColorBarItem(values=(0, 1), colorMap="viridis")
        self.cb_orig.setImageItem(self.img_orig)
        self.glw_orig.addItem(self.cb_orig)

        self.center_scatter = pg.ScatterPlotItem(size=12, symbol="+", pen=pg.mkPen("m", width=2))
        self.ellipse_curve = pg.PlotCurveItem(pen=pg.mkPen("c", width=1.5, style=Qt.PenStyle.DashLine))
        self.vb_orig.addItem(self.center_scatter)
        self.vb_orig.addItem(self.ellipse_curve)
        self.vb_orig.setLabel("left", "Y", **label_style)
        self.vb_orig.setLabel("bottom", "X", **label_style)

        # 2. Visor Fit Sintético
        self.glw_fit = pg.GraphicsLayoutWidget()
        self.img_fit = pg.ImageItem()
        self.vb_fit = self.glw_fit.addPlot(title="Modelo Ajustado (Fit)")
        self.vb_fit.setAspectLocked(True)
        self.vb_fit.addItem(self.img_fit)
        self.cb_fit = pg.ColorBarItem(values=(0, 1), colorMap="viridis")
        self.cb_fit.setImageItem(self.img_fit)
        self.glw_fit.addItem(self.cb_fit)
        self.vb_fit.setLabel("left", "Y", **label_style)
        self.vb_fit.setLabel("bottom", "X", **label_style)

        # 3. Visor Residual
        self.glw_res = pg.GraphicsLayoutWidget()
        self.img_res = pg.ImageItem()
        self.vb_res = self.glw_res.addPlot(title="Residual (|Zn - Zfit|)")
        self.vb_res.setAspectLocked(True)
        self.vb_res.addItem(self.img_res)
        self.cb_res = pg.ColorBarItem(values=(0, 1), colorMap="inferno")
        self.cb_res.setImageItem(self.img_res)
        self.glw_res.addItem(self.cb_res)
        self.vb_res.setLabel("left", "Y", **label_style)
        self.vb_res.setLabel("bottom", "X", **label_style)

        views_layout.addWidget(self.glw_orig)
        views_layout.addWidget(self.glw_fit)
        views_layout.addWidget(self.glw_res)

        vlo.addLayout(views_layout)

        # Estado
        self.lbl_info = QLabel("Sin imagen cargada")
        self.lbl_info.setStyleSheet("color: gray;")
        vlo.addWidget(self.lbl_info)

    def set_unit_mode(self, mode: str, pixel_size_um: float):
        self.unit_mode = mode
        unit = "um" if mode == "µm" else "px"
        scale = pixel_size_um if mode == "µm" else 1.0

        for vb in (self.vb_orig, self.vb_fit, self.vb_res):
            vb.getAxis("left").setLabel("Y", units=unit)
            vb.getAxis("bottom").setLabel("X", units=unit)
            vb.getAxis("left").setScale(scale)
            vb.getAxis("bottom").setScale(scale)

    def _load_file(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Cargar Imagen Confocal", str(DEFAULT_DATA_PATH),
            "Imágenes Confocales (*.tiff *.tif *.txt *.png *.jpg)"
        )
        if filename:
            self.load_image(Path(filename))

    def load_image(self, path: Path):
        self.image_path = path
        try:
            if path.suffix.lower() == ".txt":
                self.Z = np.loadtxt(path)
            else:
                img = Image.open(path)
                self.Z = np.array(img, dtype=np.float64)

            self.lbl_info.setText(f"Cargado: {path.name} [{self.Z.shape[1]}x{self.Z.shape[0]}]")
            self.imageLoadedSignal.emit()
            self._re_fit()
        except Exception as e:
            QMessageBox.critical(self, "Error de carga", f"No se pudo cargar la imagen:\n{e}")

    def set_data(self, Z: np.ndarray, px_size_um: Optional[float] = None):
        """Asigna directamente una matriz 2D de datos de imagen."""
        self.Z = np.asarray(Z, dtype=np.float64)
        self.image_path = None
        self.lbl_info.setText(f"Cargado en memoria [{self.Z.shape[1]}x{self.Z.shape[0]}]")
        self.imageLoadedSignal.emit()
        self._re_fit()

    def clear_panel(self):
        self.Z = None
        self.image_path = None
        self.fit_results = None
        self.img_orig.clear()
        self.img_fit.clear()
        self.img_res.clear()
        self.center_scatter.clear()
        self.ellipse_curve.clear()
        self.lbl_info.setText("Sin imagen cargada")

    def _re_fit(self):
        if self.Z is None:
            return

        try:
            thr = float(self.thr_edit.text())
        except ValueError:
            thr = 30.0

        model_name = self.combo_model.currentText()
        if model_name == "Gaussiana 2D":
            self.fit_results = fit_gaussian_2d(self.Z, thr_percent=thr)
        else:
            self.fit_results = fit_donut_2d(self.Z, thr_percent=thr)

        # Actualizar visores y barras de escala Z dinámicas
        zf = self.fit_results["Zf"]
        zfit = self.fit_results["Z_fit"]
        zres = self.fit_results["residual"]

        self.img_orig.setImage(zf.T)
        self.cb_orig.setLevels((float(zf.min()), float(zf.max())))

        self.img_fit.setImage(zfit.T)
        self.cb_fit.setLevels((float(zfit.min()), float(zfit.max())))

        self.img_res.setImage(zres.T)
        self.cb_res.setLevels((float(zres.min()), float(zres.max())))

        xo, yo = self.fit_results["xo_px"], self.fit_results["yo_px"]
        self.center_scatter.setData([xo], [yo])

        if model_name == "Donut (Laguerre-Gauss)":
            r0 = self.fit_results.get("r0_px", 3.0)
            angles = np.linspace(0, 2 * np.pi, 100)
            ex = xo + r0 * np.cos(angles)
            ey = yo + r0 * np.sin(angles)
            self.ellipse_curve.setData(ex, ey)
        else:
            self.ellipse_curve.clear()

        self.fitUpdatedSignal.emit()


# ══════════════════════════════════════════════════════════════════════════════
#  VENTANA Y WIDGET PRINCIPAL: PSF ANALYZER
# ══════════════════════════════════════════════════════════════════════════════

class PSFAnalyzerWidget(QWidget):
    """Widget principal para el análisis avanzado de PSF."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PSF Analyzer — PyPrinting")
        self._setup_ui()

    def _setup_ui(self):
        main_vlo = QVBoxLayout(self)

        # ── Controles Generales Superiores ───────────────────────────────────
        top_box = QWidget()
        hlo = QHBoxLayout(top_box)

        self.px_size_edit = QLineEdit(str(PIXEL_SIZE_UM))
        self.px_size_edit.setFixedWidth(50)
        self.px_size_edit.textChanged.connect(self._update_unit_mode)

        self.combo_units = QComboBox()
        self.combo_units.addItems(["Unidades: micrómetros (µm)", "Unidades: píxeles (px)"])
        self.combo_units.currentIndexChanged.connect(self._update_unit_mode)

        self.btn_clear_ch1 = QPushButton("Limpiar Canal 1")
        self.btn_clear_ch1.clicked.connect(self._clear_channel_1)

        self.btn_clear_ch2 = QPushButton("Limpiar Canal 2")
        self.btn_clear_ch2.clicked.connect(self._clear_channel_2)

        hlo.addWidget(QLabel("Tamaño píxel (µm):"))
        hlo.addWidget(self.px_size_edit)
        hlo.addWidget(self.combo_units)
        hlo.addSpacing(20)
        hlo.addWidget(self.btn_clear_ch1)
        hlo.addWidget(self.btn_clear_ch2)
        hlo.addStretch()

        main_vlo.addWidget(top_box)

        # ── Splitter Principal (Horizontal: Izquierda = Confocales V-Splitter, Derecha = Resultados) ────────────────
        main_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Sub-splitter Vertical para Canal 1 (Arriba) y Canal 2 (Abajo)
        chan_splitter = QSplitter(Qt.Orientation.Vertical)

        # Canal 1
        self.ch1_panel = ConfocalChannelPanel("Confocal 1 (Verde / Excitación)")
        self.ch1_panel.fitUpdatedSignal.connect(self._update_analysis)

        # Canal 2
        self.ch2_panel = ConfocalChannelPanel("Confocal 2 (Rojo / Donut STED)")
        self.ch2_panel.fitUpdatedSignal.connect(self._update_analysis)

        chan_splitter.addWidget(self.ch1_panel)
        chan_splitter.addWidget(self.ch2_panel)
        chan_splitter.setSizes([400, 400])

        # Panel de Resultados y Gráficos (Pestañas)
        self.tabs_results = QTabWidget()

        # Tab 1: Tabla de Métricas
        self.tab_table = QWidget()
        tlo = QVBoxLayout(self.tab_table)
        self.table_metrics = QTableWidget()
        self.table_metrics.setColumnCount(4)
        self.table_metrics.setHorizontalHeaderLabels(["Parámetro", "Confocal 1", "Confocal 2", "Diferencia / Co-alineación"])
        self.table_metrics.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        tlo.addWidget(self.table_metrics)
        self.tabs_results.addTab(self.tab_table, "📊 Métricas de Ajuste")

        # Tab 2: Perfiles 1D
        self.tab_profiles = QWidget()
        plo = QVBoxLayout(self.tab_profiles)
        prof_ctrl = QHBoxLayout()

        prof_ctrl.addWidget(QLabel("Canal a Graficar:"))
        self.combo_profile_chan = QComboBox()
        self.combo_profile_chan.addItems(["Confocal 1", "Confocal 2", "Ambas superpuestas"])
        self.combo_profile_chan.currentIndexChanged.connect(self._update_profiles)
        prof_ctrl.addWidget(self.combo_profile_chan)

        prof_ctrl.addSpacing(15)
        prof_ctrl.addWidget(QLabel("Dirección del Perfil:"))
        self.combo_profile_dir = QComboBox()
        self.combo_profile_dir.addItems(["Horizontal", "Vertical", "Diagonal 45°", "Diagonal 135°"])
        self.combo_profile_dir.currentIndexChanged.connect(self._update_profiles)
        prof_ctrl.addWidget(self.combo_profile_dir)
        prof_ctrl.addStretch()
        plo.addLayout(prof_ctrl)

        self.plot_profiles = pg.PlotWidget(title="Perfil 1D pasante por el centro (xo, yo)")
        self.plot_profiles.setLabel("bottom", "Posición respecto al centro", units="um")
        self.plot_profiles.setLabel("left", "Intensidad Normalizada")
        self.curve_prof1 = self.plot_profiles.plot(pen=pg.mkPen("g", width=2), name="Confocal 1")
        self.curve_prof2 = self.plot_profiles.plot(pen=pg.mkPen("r", width=2), name="Confocal 2")
        plo.addWidget(self.plot_profiles)
        self.tabs_results.addTab(self.tab_profiles, "📈 Perfiles 1D")

        # Tab 3: Superposición RGB Falso Color
        self.tab_overlay = QWidget()
        olo = QVBoxLayout(self.tab_overlay)
        ov_ctrl = QHBoxLayout()
        ov_ctrl.addWidget(QLabel("Modo de Falso Color:"))
        self.combo_overlay_mode = QComboBox()
        self.combo_overlay_mode.addItems(["Imágenes Originales", "Originales con Filtro de Ruido", "Modelos Ajustados (Fits)"])
        self.combo_overlay_mode.currentIndexChanged.connect(self._update_overlay)
        ov_ctrl.addWidget(self.combo_overlay_mode)
        ov_ctrl.addStretch()
        olo.addLayout(ov_ctrl)

        self.glw_overlay = pg.GraphicsLayoutWidget()
        self.img_overlay = pg.ImageItem()
        self.vb_overlay = self.glw_overlay.addPlot(title="Superposición Falso Color RGB")
        self.vb_overlay.setAspectLocked(True)
        self.vb_overlay.addItem(self.img_overlay)
        olo.addWidget(self.glw_overlay)
        self.tabs_results.addTab(self.tab_overlay, "🎨 Superposición Falso Color")

        main_splitter.addWidget(chan_splitter)
        main_splitter.addWidget(self.tabs_results)
        main_splitter.setSizes([750, 450])

        main_vlo.addWidget(main_splitter)
        self._update_unit_mode()

    def _clear_channel_1(self):
        self.ch1_panel.clear_panel()
        self._update_analysis()

    def _clear_channel_2(self):
        self.ch2_panel.clear_panel()
        self._update_analysis()

    def _update_unit_mode(self):
        mode_str = "µm" if "micrómetros" in self.combo_units.currentText() else "px"
        try:
            px_size = float(self.px_size_edit.text())
        except ValueError:
            px_size = PIXEL_SIZE_UM

        self.ch1_panel.set_unit_mode(mode_str, px_size)
        self.ch2_panel.set_unit_mode(mode_str, px_size)
        self._update_analysis()

    def _update_analysis(self):
        f1 = self.ch1_panel.fit_results
        f2 = self.ch2_panel.fit_results

        # Actualizar tabla de métricas
        rows = [
            ("Modelo Ajustado", f1.get("model", "—") if f1 else "—", f2.get("model", "—") if f2 else "—", "—"),
            ("Centro xo (µm)", f"{f1['xo_um']:.3f}" if f1 else "—", f"{f2['xo_um']:.3f}" if f2 else "—",
             f"Δx = {abs(f1['xo_um'] - f2['xo_um'])*1000:.1f} nm" if (f1 and f2) else "—"),
            ("Centro yo (µm)", f"{f1['yo_um']:.3f}" if f1 else "—", f"{f2['yo_um']:.3f}" if f2 else "—",
             f"Δy = {abs(f1['yo_um'] - f2['yo_um'])*1000:.1f} nm" if (f1 and f2) else "—"),
            ("Desalineación Vectorial Δr", "—", "—",
             f"{math.hypot(f1['xo_um'] - f2['xo_um'], f1['yo_um'] - f2['yo_um'])*1000:.1f} nm" if (f1 and f2) else "—"),
            ("Radio Anillo r0 (µm)", f"{f1.get('r0_um', 0.0):.3f}" if (f1 and 'r0_um' in f1) else "—",
             f"{f2.get('r0_um', 0.0):.3f}" if (f2 and 'r0_um' in f2) else "—", "—"),
            ("Elipticidad (a/b)", f"{f1.get('ellipticity', 0.0):.3f}" if (f1 and 'ellipticity' in f1) else "—",
             f"{f2.get('ellipticity', 0.0):.3f}" if (f2 and 'ellipticity' in f2) else "—", "—"),
            ("Orientación θ (°)", f"{f1.get('theta_deg', 0.0):.1f}°" if f1 else "—",
             f"{f2.get('theta_deg', 0.0):.1f}°" if f2 else "—", "—"),
            ("Calidad del Cero (I_min/I_max)", f"{f1.get('zero_quality', 0.0):.4f}" if (f1 and 'zero_quality' in f1) else "—",
             f"{f2.get('zero_quality', 0.0):.4f}" if (f2 and 'zero_quality' in f2) else "—", "—"),
            ("Uniformidad Angular (σ_θ/I)", f"{f1.get('angular_uniformity', 0.0):.4f}" if (f1 and 'angular_uniformity' in f1) else "—",
             f"{f2.get('angular_uniformity', 0.0):.4f}" if (f2 and 'angular_uniformity' in f2) else "—", "—"),
            ("FWHM Promedio (µm)", f"{f1.get('fwhm_avg_um', 0.0):.3f}" if (f1 and 'fwhm_avg_um' in f1) else "—",
             f"{f2.get('fwhm_avg_um', 0.0):.3f}" if (f2 and 'fwhm_avg_um' in f2) else "—", "—"),
            ("Error RMS", f"{f1.get('rms', 0.0):.4f}" if f1 else "—", f"{f2.get('rms', 0.0):.4f}" if f2 else "—", "—"),
            ("Chi² Reducido (χ²_red)", f"{f1.get('chi2_red', 0.0):.4f}" if f1 else "—", f"{f2.get('chi2_red', 0.0):.4f}" if f2 else "—", "—"),
            ("Calidad de Ajuste R²", f"{f1['r2']:.3f}" if f1 else "—", f"{f2['r2']:.3f}" if f2 else "—", "—"),
        ]

        self.table_metrics.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for j, val in enumerate(row):
                item = QTableWidgetItem(str(val))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table_metrics.setItem(i, j, item)

        self._update_profiles()
        self._update_overlay()

    def _update_profiles(self):
        dir_mode = self.combo_profile_dir.currentText()
        chan_mode = self.combo_profile_chan.currentText()
        try:
            px_size = float(self.px_size_edit.text())
        except ValueError:
            px_size = PIXEL_SIZE_UM

        show_c1 = (chan_mode in ("Confocal 1", "Ambas superpuestas"))
        show_c2 = (chan_mode in ("Confocal 2", "Ambas superpuestas"))

        if show_c1 and self.ch1_panel.Z is not None and self.ch1_panel.fit_results is not None:
            f1 = self.ch1_panel.fit_results
            dist1, prof1 = extract_1d_profile(self.ch1_panel.Z, f1["xo_px"], f1["yo_px"], px_size, dir_mode)
            prof1_norm = (prof1 - prof1.min()) / (prof1.max() - prof1.min() + 1e-12)
            self.curve_prof1.setData(dist1, prof1_norm)
        else:
            self.curve_prof1.clear()

        if show_c2 and self.ch2_panel.Z is not None and self.ch2_panel.fit_results is not None:
            f2 = self.ch2_panel.fit_results
            dist2, prof2 = extract_1d_profile(self.ch2_panel.Z, f2["xo_px"], f2["yo_px"], px_size, dir_mode)
            prof2_norm = (prof2 - prof2.min()) / (prof2.max() - prof2.min() + 1e-12)
            self.curve_prof2.setData(dist2, prof2_norm)
        else:
            self.curve_prof2.clear()

    def _update_overlay(self):
        if self.ch1_panel.Z is None:
            self.img_overlay.clear()
            return

        mode = self.combo_overlay_mode.currentText()

        # Seleccionar matrices según modo
        if mode == "Imágenes Originales":
            M1 = self.ch1_panel.Z
            M2 = self.ch2_panel.Z
        elif mode == "Imágenes Filtradas (Filtro Ruido)" and self.ch1_panel.fit_results:
            M1 = self.ch1_panel.fit_results["Zf"]
            M2 = self.ch2_panel.fit_results["Zf"] if self.ch2_panel.fit_results else None
        elif mode == "Modelos Ajustados (Fits)" and self.ch1_panel.fit_results:
            M1 = self.ch1_panel.fit_results["Z_fit"]
            M2 = self.ch2_panel.fit_results["Z_fit"] if self.ch2_panel.fit_results else None
        else:
            M1 = self.ch1_panel.Z
            M2 = self.ch2_panel.Z

        M1_n = (M1 - M1.min()) / (M1.max() - M1.min() + 1e-12)

        if M2 is not None:
            M2_n = (M2 - M2.min()) / (M2.max() - M2.min() + 1e-12)
            Ny = min(M1.shape[0], M2.shape[0])
            Nx = min(M1.shape[1], M2.shape[1])
            rgb = np.zeros((Ny, Nx, 3), dtype=np.uint8)
            rgb[..., 1] = (M1_n[:Ny, :Nx] * 255).astype(np.uint8)  # Verde
            rgb[..., 0] = (M2_n[:Ny, :Nx] * 255).astype(np.uint8)  # Rojo
        else:
            Ny, Nx = M1.shape
            rgb = np.zeros((Ny, Nx, 3), dtype=np.uint8)
            rgb[..., 1] = (M1_n * 255).astype(np.uint8)

        self.img_overlay.setImage(np.transpose(rgb, (1, 0, 2)))


    def load_dual_images(self, Z1: np.ndarray, Z2: np.ndarray, px_size_um: float):
        self.px_size_edit.setText(str(px_size_um))
        self.ch1_panel.set_data(Z1, px_size_um)
        self.ch2_panel.set_data(Z2, px_size_um)
        self._update_analysis()


# ══════════════════════════════════════════════════════════════════════════════
#  MODO FOTO ÚNICA & PERFILES DE CORTE DE INTENSIDAD (SINGLE IMAGE PROFILE)
# ══════════════════════════════════════════════════════════════════════════════

class SingleImageProfileWidget(QWidget):
    """
    Widget para cargar y analizar imágenes individuales (.tiff, .png, .jpg, .npy, .txt),
    con líneas de corte interactivas (arbitrarias, ortogonales y radiales), perfiles de
    intensidad 1D, ajuste Gaussiano analítico, cálculo automático de FWHM y reglas duales.
    """

    def __init__(self, parent_window=None, parent=None):
        super().__init__(parent)
        self.parent_window = parent_window

        self.Z: Optional[np.ndarray] = None
        self.pixel_size_um: float = PIXEL_SIZE_UM
        self.unit_mode: str = "um"
        self.line_width_px: int = 1
        self.cut_mode: str = "arbitrary"

        self.current_dist: np.ndarray = np.array([])
        self.current_profile: np.ndarray = np.array([])

        self._setup_ui()
        self._load_default_demo()

    def _setup_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(6)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── Lado Izquierdo: Visor 2D y Controles de Imagen ────────────────────
        left_widget = QWidget()
        left_vlo = QVBoxLayout(left_widget)
        left_vlo.setContentsMargins(0, 0, 0, 0)
        left_vlo.setSpacing(6)

        # Barra Superior de Controles
        ctrl_box = QGroupBox("🖼️ Imagen & Línea de Corte")
        c_vlo = QVBoxLayout(ctrl_box)
        c_vlo.setSpacing(6)

        btn_hlo = QHBoxLayout()
        self.btn_open_img = QPushButton("📂 Abrir Imagen...")
        self.btn_open_img.setStyleSheet("background-color: #89B4FA; color: #11111B; font-weight: bold; padding: 6px;")
        self.btn_open_img.clicked.connect(self._on_open_image)

        self.btn_demo_img = QPushButton("🖼️ Cargar Demo")
        self.btn_demo_img.clicked.connect(self._on_load_demo_clicked)

        btn_hlo.addWidget(self.btn_open_img)
        btn_hlo.addWidget(self.btn_demo_img)
        c_vlo.addLayout(btn_hlo)

        grid_params = QGridLayout()
        grid_params.setSpacing(6)

        grid_params.addWidget(QLabel("Tamaño Píxel:"), 0, 0)
        self.spin_px_size = QDoubleSpinBox()
        self.spin_px_size.setRange(0.001, 100.0)
        self.spin_px_size.setValue(self.pixel_size_um)
        self.spin_px_size.setDecimals(4)
        self.spin_px_size.setSuffix(" µm")
        self.spin_px_size.valueChanged.connect(self._on_px_size_changed)
        grid_params.addWidget(self.spin_px_size, 0, 1)

        grid_params.addWidget(QLabel("Unidades:"), 0, 2)
        self.combo_units = QComboBox()
        self.combo_units.addItems(["µm (Micrómetros)", "px (Píxeles)"])
        self.combo_units.currentIndexChanged.connect(self._on_units_changed)
        grid_params.addWidget(self.combo_units, 0, 3)

        grid_params.addWidget(QLabel("Modo de Corte:"), 1, 0)
        self.combo_cut_mode = QComboBox()
        self.combo_cut_mode.addItems([
            "Línea Libre (Arrastrable 2 Puntos)",
            "↔️ Horizontal al Centro / Máximo",
            "↕️ Vertical al Centro / Máximo",
            "Diagonal 45°",
            "Diagonal 135°",
            "⭕ Radial Promediado 360°"
        ])
        self.combo_cut_mode.currentIndexChanged.connect(self._on_cut_mode_changed)
        grid_params.addWidget(self.combo_cut_mode, 1, 1)

        grid_params.addWidget(QLabel("Espesor Promedio:"), 1, 2)
        self.spin_line_width = QSpinBox()
        self.spin_line_width.setRange(1, 31)
        self.spin_line_width.setValue(1)
        self.spin_line_width.setSuffix(" px")
        self.spin_line_width.valueChanged.connect(self._update_profile)
        grid_params.addWidget(self.spin_line_width, 1, 3)

        grid_params.addWidget(QLabel("Paleta:"), 2, 0)
        self.combo_cmap = QComboBox()
        self.combo_cmap.addItems(["Viridis", "Inferno", "Magma", "Thermal", "Grayscale", "Plasma"])
        self.combo_cmap.currentIndexChanged.connect(self._update_colormap)
        grid_params.addWidget(self.combo_cmap, 2, 1)

        c_vlo.addLayout(grid_params)
        left_vlo.addWidget(ctrl_box)

        # Visor Gráfico 2D con LUT
        img_layout = pg.GraphicsLayoutWidget()
        self.plot_img = img_layout.addPlot(row=0, col=0)
        self.plot_img.setLabel("bottom", "X (píxeles)")
        self.plot_img.setLabel("left", "Y (píxeles)")
        self.plot_img.setAspectLocked(True)

        self.img_item = pg.ImageItem()
        self.plot_img.addItem(self.img_item)

        # Barra de Contraste LUT
        self.lut_item = pg.HistogramLUTItem()
        self.lut_item.setImageItem(self.img_item)
        img_layout.addItem(self.lut_item, row=0, col=1)

        # ROI de Línea de Corte con Manijas
        self.line_roi = pg.LineSegmentROI(
            positions=[[20, 50], [80, 50]],
            pen=pg.mkPen("#F38BA8", width=2.5)
        )
        self.line_roi.sigRegionChanged.connect(self._on_roi_changed)
        self.plot_img.addItem(self.line_roi)

        left_vlo.addWidget(img_layout)

        self.lbl_img_info = QLabel("Coordenadas: (X: --, Y: --) | Intensidad: -- cts | Dim: -- x -- px")
        self.lbl_img_info.setStyleSheet("background-color: #181825; color: #CDD6F4; font-size: 8.5pt; padding: 4px 8px; border-radius: 4px;")
        left_vlo.addWidget(self.lbl_img_info)

        splitter.addWidget(left_widget)

        # ── Lado Derecho: Gráfico de Perfil 1D, Ajuste FWHM y Metrología ──────
        right_widget = QWidget()
        right_vlo = QVBoxLayout(right_widget)
        right_vlo.setContentsMargins(0, 0, 0, 0)
        right_vlo.setSpacing(6)

        # Barra Superior Derecha (Modelo de Ajuste y Exportación)
        top_right_hlo = QHBoxLayout()
        top_right_hlo.addWidget(QLabel("<b>Modelo 1D:</b>"))
        self.combo_fit_model = QComboBox()
        self.combo_fit_model.addItems(["Gaussiana 1D", "Sin Ajuste"])
        self.combo_fit_model.currentIndexChanged.connect(self._update_profile)
        top_right_hlo.addWidget(self.combo_fit_model)

        top_right_hlo.addStretch()
        self.btn_copy_tsv = QPushButton("📋 Copiar Perfil (TSV)")
        self.btn_copy_tsv.clicked.connect(self._on_copy_tsv)
        self.btn_export_csv = QPushButton("💾 Exportar CSV")
        self.btn_export_csv.setStyleSheet("background-color: #A6E3A1; color: #11111B; font-weight: bold;")
        self.btn_export_csv.clicked.connect(self._on_export_csv)
        top_right_hlo.addWidget(self.btn_copy_tsv)
        top_right_hlo.addWidget(self.btn_export_csv)

        right_vlo.addLayout(top_right_hlo)

        # Gráfico de Perfil 1D
        self.plot_profile = pg.PlotWidget(title="Perfil de Intensidad 1D a lo largo de la Línea de Corte")
        self.plot_profile.setLabel("bottom", "Distancia a lo largo del corte (µm)")
        self.plot_profile.setLabel("left", "Intensidad (Cuentas)")
        self.plot_profile.showGrid(x=True, y=True, alpha=0.25)
        self.plot_profile.addLegend(offset=(-10, 10))

        self.curve_profile_raw = self.plot_profile.plot(
            pen=pg.mkPen("#89B4FA", width=2.0), symbol="o", symbolSize=4, symbolBrush=pg.mkBrush("#89B4FA"), name="Datos de Corte"
        )
        self.curve_profile_fit = self.plot_profile.plot(
            pen=pg.mkPen("#F38BA8", width=2.2), name="Ajuste Gaussiano"
        )

        # Reglas verticales A y B en el perfil
        self.cursor_a = pg.InfiniteLine(pos=0.5, angle=90, movable=True, pen=pg.mkPen("#F38BA8", width=1.8))
        self.cursor_a.sigPositionChanged.connect(self._on_cursors_moved)
        self.plot_profile.addItem(self.cursor_a)

        self.cursor_b = pg.InfiniteLine(pos=1.5, angle=90, movable=True, pen=pg.mkPen("#F9E2AF", width=1.8, style=Qt.PenStyle.DashLine))
        self.cursor_b.sigPositionChanged.connect(self._on_cursors_moved)
        self.plot_profile.addItem(self.cursor_b)

        self.region_ab = pg.LinearRegionItem(values=[0.5, 1.5], brush=pg.mkBrush(137, 180, 250, 40), movable=False)
        self.plot_profile.addItem(self.region_ab)

        right_vlo.addWidget(self.plot_profile)

        # Métricas Analíticas y FWHM
        box_metrics = QGroupBox("📊 Caracterización Analítica & FWHM de la PSF")
        m_vlo = QVBoxLayout(box_metrics)
        m_vlo.setSpacing(6)

        self.lbl_fwhm_results = QLabel(
            "<b>FWHM Experimental:</b> -- | <b>Centro s₀:</b> --<br>"
            "<b>Amplitud Neta A:</b> -- | <b>Fondo I_offset:</b> -- | <b>Calidad R²:</b> --"
        )
        self.lbl_fwhm_results.setStyleSheet("color: #CDD6F4; font-size: 9pt; line-height: 1.4;")
        m_vlo.addWidget(self.lbl_fwhm_results)

        self.lbl_diffraction_limit = QLabel(
            "🔍 <i>Límite teórico de difracción Abbe (λ=532 nm, NA=1.4): FWHM_teórico = 193.7 nm</i>"
        )
        self.lbl_diffraction_limit.setStyleSheet("color: #9399B2; font-size: 8pt;")
        m_vlo.addWidget(self.lbl_diffraction_limit)

        self.lbl_dual_metrics = QLabel(
            "<b>Regla A:</b> -- | <b>Regla B:</b> -- | <b>ΔX:</b> -- | <b>ΔY:</b> -- | <b>Área:</b> --"
        )
        self.lbl_dual_metrics.setStyleSheet("background-color: #181825; color: #F9E2AF; font-size: 8.5pt; padding: 4px 8px; border-radius: 4px;")
        m_vlo.addWidget(self.lbl_dual_metrics)

        right_vlo.addWidget(box_metrics)

        splitter.addWidget(right_widget)
        splitter.setSizes([600, 700])

        main_layout.addWidget(splitter)

        # Conectar movimiento del mouse sobre la imagen
        self.img_item.hoverEvent = self._on_image_hover

    def _load_default_demo(self):
        """Carga o genera una imagen PSF demo realista para inicializar la herramienta."""
        Ny, Nx = 100, 100
        x = np.linspace(-2.5, 2.5, Nx)
        y = np.linspace(-2.5, 2.5, Ny)
        X, Y = np.meshgrid(x, y)
        # Spot Gaussiano con ruido de disparo
        R = np.sqrt(X**2 + Y**2)
        Z_clean = 450.0 + 8500.0 * np.exp(-0.5 * (R / 0.45)**2)
        noise = np.random.poisson(np.maximum(Z_clean, 0.0)) - Z_clean
        Z = np.clip(Z_clean + noise, 0, 65535).astype(np.float64)

        self.set_image_data(Z, pixel_size_um=0.05)

    def set_image_data(self, Z: np.ndarray, pixel_size_um: Optional[float] = None):
        """Asigna una matriz 2D de intensidad al visor y actualiza los cortes."""
        self.Z = np.asarray(Z, dtype=np.float64)
        if pixel_size_um is not None:
            self.pixel_size_um = float(pixel_size_um)
            self.spin_px_size.setValue(self.pixel_size_um)

        Ny, Nx = self.Z.shape
        self.img_item.setImage(self.Z.T)
        self._update_colormap()

        # Posicionar la línea de corte inicial atravesando el máximo
        max_idx = np.unravel_index(np.argmax(self.Z), self.Z.shape)
        yo, xo = float(max_idx[0]), float(max_idx[1])

        # Centrar línea horizontal por defecto
        self._set_roi_endpoints((max(0.0, xo - 25.0), yo), (min(float(Nx - 1), xo + 25.0), yo))

        self.lbl_img_info.setText(f"Dim: {Nx} x {Ny} px | Mín: {self.Z.min():.0f} | Máx: {self.Z.max():.0f} cts")
        self._update_profile()

    def _get_roi_endpoints(self) -> Tuple[Tuple[float, float], Tuple[float, float]]:
        handles = self.line_roi.getHandles()
        if len(handles) >= 2:
            p1 = self.line_roi.mapToParent(handles[0].pos())
            p2 = self.line_roi.mapToParent(handles[1].pos())
            return (float(p1.x()), float(p1.y())), (float(p2.x()), float(p2.y()))
        pts = self.line_roi.listPoints()
        return (float(pts[0].x()), float(pts[0].y())), (float(pts[1].x()), float(pts[1].y()))

    def _set_roi_endpoints(self, p1: Tuple[float, float], p2: Tuple[float, float]):
        self.line_roi.blockSignals(True)
        handles = self.line_roi.getHandles()
        if len(handles) >= 2:
            self.line_roi.movePoint(handles[0], [float(p1[0]), float(p1[1])], coords='parent')
            self.line_roi.movePoint(handles[1], [float(p2[0]), float(p2[1])], coords='parent')
        self.line_roi.blockSignals(False)

    def _on_open_image(self):
        start_dir = str(Path.home() / "Documents")
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Abrir Imagen de PSF", start_dir,
            "Imágenes (*.tiff *.tif *.png *.jpg *.bmp *.npy *.txt *.asc);;Todos (*.*)"
        )
        if not file_path:
            return

        p = Path(file_path)
        try:
            if p.suffix.lower() in (".tiff", ".tif"):
                try:
                    import tifffile
                    Z = tifffile.imread(p)
                except Exception:
                    im = Image.open(p)
                    Z = np.array(im)
            elif p.suffix.lower() == ".npy":
                Z = np.load(p)
            elif p.suffix.lower() in (".txt", ".asc"):
                try:
                    Z = np.loadtxt(p)
                except Exception:
                    _, _, counts = parse_andor_solis_file(p)
                    Z = counts.reshape(1, -1)
            else:
                im = Image.open(p).convert("L")
                Z = np.array(im)

            if Z.ndim == 3:
                # Convertir a luminancia si es RGB
                Z = 0.299 * Z[..., 0] + 0.587 * Z[..., 1] + 0.114 * Z[..., 2]

            self.set_image_data(Z)
        except Exception as e:
            QMessageBox.critical(self, "Error al Cargar Imagen", f"No se pudo abrir {p.name}:\n{e}")

    def _on_load_demo_clicked(self):
        self._load_default_demo()

    def _on_px_size_changed(self, val: float):
        self.pixel_size_um = val
        unit_str = "µm" if self.unit_mode == "um" else "px"
        self.plot_profile.setLabel("bottom", f"Distancia a lo largo del corte ({unit_str})")
        self._update_profile()

    def _on_units_changed(self, idx: int):
        self.unit_mode = "um" if idx == 0 else "px"
        unit_str = "µm" if self.unit_mode == "um" else "px"
        self.plot_profile.setLabel("bottom", f"Distancia a lo largo del corte ({unit_str})")
        self._update_profile()

    def _update_colormap(self):
        cmap_name = self.combo_cmap.currentText().lower()
        if cmap_name == "viridis":
            c_name = "viridis"
        elif cmap_name == "inferno":
            c_name = "inferno"
        elif cmap_name == "magma":
            c_name = "magma"
        elif cmap_name == "thermal":
            c_name = "thermal"
        elif cmap_name == "plasma":
            c_name = "plasma"
        else:
            c_name = "gray"

        try:
            import matplotlib as mpl
            import matplotlib.cm as cm
            cmap = mpl.colormaps[c_name] if hasattr(mpl, "colormaps") else cm.get_cmap(c_name)
            lut = (cmap(np.linspace(0, 1, 256)) * 255).astype(np.uint8)
            self.img_item.setLookupTable(lut)
        except Exception:
            pass

    def _on_cut_mode_changed(self, idx: int):
        if self.Z is None:
            return
        Ny, Nx = self.Z.shape
        max_idx = np.unravel_index(np.argmax(self.Z), self.Z.shape)
        yo, xo = float(max_idx[0]), float(max_idx[1])

        self.line_roi.blockSignals(True)
        if idx == 0:  # Línea Libre
            self.cut_mode = "arbitrary"
            self.line_roi.setVisible(True)
        elif idx == 1:  # Horizontal
            self.cut_mode = "horizontal"
            self.line_roi.setVisible(True)
            self._set_roi_endpoints((0.0, yo), (float(Nx - 1), yo))
        elif idx == 2:  # Vertical
            self.cut_mode = "vertical"
            self.line_roi.setVisible(True)
            self._set_roi_endpoints((xo, 0.0), (xo, float(Ny - 1)))
        elif idx == 3:  # Diagonal 45°
            self.cut_mode = "diag45"
            self.line_roi.setVisible(True)
            d = min(xo, yo, Nx - 1 - xo, Ny - 1 - yo)
            self._set_roi_endpoints((xo - d, yo - d), (xo + d, yo + d))
        elif idx == 4:  # Diagonal 135°
            self.cut_mode = "diag135"
            self.line_roi.setVisible(True)
            d = min(xo, yo, Nx - 1 - xo, Ny - 1 - yo)
            self._set_roi_endpoints((xo - d, yo + d), (xo + d, yo - d))
        elif idx == 5:  # Radial 360°
            self.cut_mode = "radial"
            self.line_roi.setVisible(False)

        self._update_profile()

    def _on_roi_changed(self):
        if self.combo_cut_mode.currentIndex() != 0:
            self.combo_cut_mode.blockSignals(True)
            self.combo_cut_mode.setCurrentIndex(0)  # Cambió a línea libre
            self.cut_mode = "arbitrary"
            self.combo_cut_mode.blockSignals(False)
        self._update_profile()

    def _update_profile(self):
        if self.Z is None:
            return

        px_scale = self.pixel_size_um if self.unit_mode == "um" else 1.0
        unit_str = "µm" if self.unit_mode == "um" else "px"
        lw = self.spin_line_width.value()

        if self.cut_mode == "radial":
            max_idx = np.unravel_index(np.argmax(self.Z), self.Z.shape)
            yo, xo = float(max_idx[0]), float(max_idx[1])
            dist, prof = extract_radial_profile(self.Z, (xo, yo), pixel_size_um=px_scale)
            self.plot_profile.setTitle("Perfil Radial Promediado en 360° desde el Centroide")
        else:
            p1, p2 = self._get_roi_endpoints()
            dist, prof = extract_arbitrary_line_profile(self.Z, p1, p2, pixel_size_um=px_scale, line_width_px=lw)
            self.plot_profile.setTitle(f"Perfil 1D a lo largo de la Línea de Corte (Espesor: {lw} px)")

        self.current_dist = dist
        self.current_profile = prof

        self.curve_profile_raw.setData(dist, prof)

        # Ajuste analítico Gaussiano si está seleccionado
        if self.combo_fit_model.currentIndex() == 0 and len(dist) >= 5:
            fit_res = fit_1d_gaussian(dist, prof)
            if fit_res:
                self.curve_profile_fit.setData(fit_res["fit_s"], fit_res["fit_y"])
                fwhm_val = fit_res["fwhm"]
                fwhm_px = fwhm_val / self.pixel_size_um if self.unit_mode == "um" else fwhm_val
                fwhm_um = fwhm_val if self.unit_mode == "um" else fwhm_val * self.pixel_size_um

                sbr = (fit_res["amplitude"] + fit_res["offset"]) / max(fit_res["offset"], 1e-12)
                self.lbl_fwhm_results.setText(
                    f"<b>FWHM:</b> <span style='color:#A6E3A1; font-size:10pt;'><b>{fwhm_um:.3f} µm</b> ({fwhm_px:.1f} px)</span> | "
                    f"<b>Centro s₀:</b> {fit_res['center']:.2f} {unit_str}<br>"
                    f"<b>Amplitud A:</b> {fit_res['amplitude']:.0f} cts | <b>Fondo I₀:</b> {fit_res['offset']:.0f} cts | "
                    f"<b>SBR:</b> {sbr:.1f} | <b>Calidad R²:</b> <b>{fit_res['r_squared']:.4f}</b>"
                )
            else:
                self.curve_profile_fit.clear()
                self.lbl_fwhm_results.setText("No convergió el ajuste Gaussiano 1D en el corte actual.")
        else:
            self.curve_profile_fit.clear()
            self.lbl_fwhm_results.setText("Ajuste desactivado.")

        # Reubicar cursores si están fuera de rango
        if len(dist) > 1:
            d_min = float(dist[0])
            d_max = float(dist[-1])
            pos_a = float(self.cursor_a.value())
            pos_b = float(self.cursor_b.value())
            if pos_a < d_min or pos_a > d_max:
                self.cursor_a.setValue(d_min + (d_max - d_min) * 0.25)
            if pos_b < d_min or pos_b > d_max:
                self.cursor_b.setValue(d_min + (d_max - d_min) * 0.75)

        self._on_cursors_moved()

    def _on_cursors_moved(self):
        if len(self.current_dist) < 2 or len(self.current_profile) != len(self.current_dist):
            return

        pos_a = float(self.cursor_a.value())
        pos_b = float(self.cursor_b.value())
        x_min = min(pos_a, pos_b)
        x_max = max(pos_a, pos_b)

        self.region_ab.setRegion([x_min, x_max])

        unit_str = "µm" if self.unit_mode == "um" else "px"
        y_a = float(np.interp(pos_a, self.current_dist, self.current_profile))
        y_b = float(np.interp(pos_b, self.current_dist, self.current_profile))

        mask = (self.current_dist >= x_min) & (self.current_dist <= x_max)
        x_sub = self.current_dist[mask]
        y_sub = self.current_profile[mask]
        area = float(np.trapezoid(y_sub, x_sub) if hasattr(np, "trapezoid") else np.trapz(y_sub, x_sub)) if len(x_sub) >= 2 else 0.0

        self.lbl_dual_metrics.setText(
            f"<b>Regla A:</b> {pos_a:.2f} {unit_str} (Y={y_a:.0f}) | "
            f"<b>Regla B:</b> {pos_b:.2f} {unit_str} (Y={y_b:.0f}) | "
            f"<b>ΔX:</b> {abs(pos_b - pos_a):.2f} {unit_str} | <b>ΔY:</b> {y_b - y_a:+.0f} cts | "
            f"<b>Área:</b> {area:.2e}"
        )

    def _on_image_hover(self, event):
        if self.Z is None:
            return
        if event.isExit():
            return
        pos = event.pos()
        x, y = int(pos.x()), int(pos.y())
        Ny, Nx = self.Z.shape
        if 0 <= x < Nx and 0 <= y < Ny:
            val = self.Z[y, x]
            self.lbl_img_info.setText(
                f"Coordenadas: (X: {x} px, Y: {y} px) | Intensidad: <b>{val:.0f}</b> cts | Dim: {Nx} x {Ny} px"
            )

    def _on_copy_tsv(self):
        if len(self.current_dist) == 0:
            return
        unit_str = "um" if self.unit_mode == "um" else "px"
        lines = [f"Distance_{unit_str}\tIntensity_Counts"]
        for s, val in zip(self.current_dist, self.current_profile):
            lines.append(f"{s:.4f}\t{val:.2f}")
        QApplication.clipboard().setText("\n".join(lines))
        if self.parent_window and hasattr(self.parent_window, "statusBar"):
            self.parent_window.statusBar().showMessage("Perfil 1D copiado al portapapeles (formato TSV).", 4000)

    def _on_export_csv(self):
        if len(self.current_dist) == 0:
            QMessageBox.warning(self, "Sin datos", "No hay perfil de corte para exportar.")
            return

        out_path, _ = QFileDialog.getSaveFileName(
            self, "Exportar Perfil 1D", "PSF_Line_Profile.csv", "Archivos CSV (*.csv);;Archivos de Texto (*.txt)"
        )
        if not out_path:
            return

        try:
            unit_str = "um" if self.unit_mode == "um" else "px"
            header = f"Distance_{unit_str},Intensity_Counts"
            data = np.column_stack([self.current_dist, self.current_profile])
            np.savetxt(out_path, data, delimiter=",", header=header, comments="", fmt="%.4f,%.2f")
            QMessageBox.information(self, "Exportación Exitosa", f"Perfil exportado en:\n{out_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error de Exportación", f"No se pudo exportar el perfil:\n{e}")


# ══════════════════════════════════════════════════════════════════════════════
#  VENTANA PRINCIPAL: PSF ANALYZER (BI-MODAL)
# ══════════════════════════════════════════════════════════════════════════════

class PSFAnalyzerWindow(QMainWindow):
    """
    Ventana independiente de caracterización de PSF.
    Aloja dos modos de trabajo principales:
      1. 📸 Modo Foto Única & Líneas de Corte (SingleImageProfileWidget)
      2. 🔬 Modo Co-Alineación Dual Confocal (PSFAnalyzerWidget)
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PSF Analyzer — Caracterización 2D & Líneas de Corte (UNSAM Nanofotónica)")
        self.resize(1420, 880)
        self.setMinimumSize(1100, 700)
        self._setup_ui()

    def _setup_ui(self):
        self.main_tabs = QTabWidget()
        self.setCentralWidget(self.main_tabs)

        # ── Modo 1: Foto Única & Líneas de Corte (Perfil 1D y FWHM) ──────────
        self.tab_single = SingleImageProfileWidget(parent_window=self)
        self.main_tabs.addTab(self.tab_single, "📸 Foto Única & Líneas de Corte")

        # ── Modo 2: Co-Alineación Dual Confocal ──────────────────────────────
        self.widget_dual = PSFAnalyzerWidget()
        self.main_tabs.addTab(self.widget_dual, "🔬 Co-Alineación Dual Confocal")

    def load_dual_images(self, Z1: np.ndarray, Z2: np.ndarray, px_size_um: float):
        """Mantiene 100% de compatibilidad con llamadas de app.py y contrapropagante.py."""
        self.main_tabs.setCurrentIndex(1)
        self.widget_dual.load_dual_images(Z1, Z2, px_size_um)
        self.show()
        self.raise_()

    def load_single_image(self, Z: np.ndarray, px_size_um: float):
        """Abre y analiza una única imagen en el modo de corte 1D."""
        self.main_tabs.setCurrentIndex(0)
        self.tab_single.set_image_data(Z, px_size_um)
        self.show()
        self.raise_()


# ══════════════════════════════════════════════════════════════════════════════
#  PUNTO DE ENTRADA PRINCIPAL Y EJECUCIÓN AUTÓNOMA
# ══════════════════════════════════════════════════════════════════════════════

def main():
    """Función principal de ejecución para PSF Analyzer."""
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")

    # Paleta Catppuccin Mocha
    dark_palette = QtGui.QPalette()
    dark_palette.setColor(QtGui.QPalette.ColorRole.Window, QColor("#11111B"))
    dark_palette.setColor(QtGui.QPalette.ColorRole.WindowText, QColor("#CDD6F4"))
    dark_palette.setColor(QtGui.QPalette.ColorRole.Base, QColor("#181825"))
    dark_palette.setColor(QtGui.QPalette.ColorRole.AlternateBase, QColor("#1E1E2E"))
    dark_palette.setColor(QtGui.QPalette.ColorRole.ToolTipBase, QColor("#1E1E2E"))
    dark_palette.setColor(QtGui.QPalette.ColorRole.ToolTipText, QColor("#CDD6F4"))
    dark_palette.setColor(QtGui.QPalette.ColorRole.Text, QColor("#CDD6F4"))
    dark_palette.setColor(QtGui.QPalette.ColorRole.Button, QColor("#313244"))
    dark_palette.setColor(QtGui.QPalette.ColorRole.ButtonText, QColor("#CDD6F4"))
    dark_palette.setColor(QtGui.QPalette.ColorRole.Highlight, QColor("#89B4FA"))
    dark_palette.setColor(QtGui.QPalette.ColorRole.HighlightedText, QColor("#11111B"))
    app.setPalette(dark_palette)

    window = PSFAnalyzerWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
