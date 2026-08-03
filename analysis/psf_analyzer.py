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
from typing import Optional

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

import pyqtgraph as pg
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QGridLayout, QLabel, QLineEdit,
                             QPushButton, QComboBox, QTableWidget, QTableWidgetItem,
                             QHeaderView, QGroupBox, QMessageBox, QFileDialog,
                             QSplitter, QTabWidget, QFormLayout)
from PyQt6.QtGui import QFont, QColor

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


class PSFAnalyzerWindow(QMainWindow):
    """Ventana independiente que aloja PSFAnalyzerWidget."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PSF Analyzer — Caracterización & Alineación Dual PSF")
        self.resize(1300, 850)
        self.widget = PSFAnalyzerWidget()
        self.setCentralWidget(self.widget)

    def load_dual_images(self, Z1: np.ndarray, Z2: np.ndarray, px_size_um: float):
        self.widget.load_dual_images(Z1, Z2, px_size_um)
        self.show()
        self.raise_()
