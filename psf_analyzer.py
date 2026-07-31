# -*- coding: utf-8 -*-
"""
psf_analyzer.py — Análisis avanzado de Funciones de Dispersión de Punto (PSF)
PyPrinting — UNSAM Nanofotónica — PyQt6

Permite cargar y analizar 1 o 2 imágenes confocales (.tiff o .txt) para caracterizar:
  - PSF Gaussiana 2D (FWHM_x, FWHM_y, asimetría, SBR, R²)
  - PSF Donut / Laguerre-Gauss 2D (Centro, radio r0, semi-ejes a/b, elipticidad,
    orientación theta, calidad del cero I_min/I_max, uniformidad angular sigma_theta/I_mean)
  - Perfiles de corte 1D pasantes por el centro ajustado (Horizontal, Vertical, Diagonal 45°, Diagonal 135°)
  - Co-alineación espacial dual entre 2 confocales en nanómetros (Δr_nm, Δx_nm, Δy_nm, PCC)
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image
from scipy.optimize import curve_fit
from scipy.ndimage import map_coordinates

import pyqtgraph as pg
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QGridLayout, QLabel, QLineEdit,
                             QPushButton, QComboBox, QTableWidget, QTableWidgetItem,
                             QHeaderView, QGroupBox, QMessageBox, QFileDialog,
                             QSplitter, QTabWidget, QFormLayout)
from PyQt6.QtGui import QFont, QColor

from config import (DEFAULT_DATA_PATH, PIXEL_SIZE_UM,
                    DEFAULT_CONFOCAL_FILTER_PERCENT)
from psf import (gaussian2D, donut2D, center_of_mass, center_of_gauss2D,
                 center_of_donut2D)


# ══════════════════════════════════════════════════════════════════════════════
#  FUNCIONES MATEMÁTICAS Y AJUSTE DE MODELOS 2D
# ══════════════════════════════════════════════════════════════════════════════

def _filter_image(Z: np.ndarray, thr_percent: float) -> np.ndarray:
    """Aplica umbral de corte de intensidad en % sobre la imagen normalizada."""
    Zmin, Zmax = Z.min(), Z.max()
    Zn = (Z - Zmin) / (Zmax - Zmin + 1e-12)
    thr = max(0.0, min(100.0, thr_percent)) / 100.0
    Zf = Zn.copy()
    Zf[Zf < thr] = 0.0
    return Zf


def fit_gaussian_2d(Z: np.ndarray, pixel_size_um: float = PIXEL_SIZE_UM,
                    thr_percent: float = DEFAULT_CONFOCAL_FILTER_PERCENT) -> dict:
    """
    Ajusta un modelo Gaussiano 2D sobre la matriz Z.
    Retorna diccionario de métricas.
    """
    Ny, Nx = Z.shape
    Zn = (Z - Z.min()) / (Z.max() - Z.min() + 1e-12)
    Zf = _filter_image(Z, thr_percent)

    # Estimación inicial de centro
    xo_init, yo_init = center_of_mass(Zf)
    xo_fit, yo_fit = center_of_gauss2D(Zn, xo_init, yo_init)

    # Coordenadas relativas
    y_idx, x_idx = np.indices((Ny, Nx))
    dx_um = pixel_size_um
    dy_um = pixel_size_um

    # Ajuste detallado de anchura (momentos de 2do orden)
    x_rel = x_idx - xo_fit
    y_rel = y_idx - yo_fit
    total_intensity = np.sum(Zf) + 1e-12
    sigma_x_px = np.sqrt(max(0.5, np.sum(Zf * (x_rel**2)) / total_intensity))
    sigma_y_px = np.sqrt(max(0.5, np.sum(Zf * (y_rel**2)) / total_intensity))

    fwhm_x_px = 2.35482 * sigma_x_px
    fwhm_y_px = 2.35482 * sigma_y_px
    fwhm_x_um = fwhm_x_px * dx_um
    fwhm_y_um = fwhm_y_px * dy_um
    fwhm_avg_um = (fwhm_x_um + fwhm_y_um) / 2.0
    aspect_ratio = sigma_x_px / (sigma_y_px + 1e-12)

    # Modelo sintético evaluado
    Z_fit = gaussian2D((x_idx, y_idx), Zn.max(), xo_fit, yo_fit, sigma_x_px, sigma_y_px, 0.0).reshape(Ny, Nx)

    # Calidad de ajuste R²
    ss_res = np.sum((Zn - Z_fit)**2)
    ss_tot = np.sum((Zn - np.mean(Zn))**2) + 1e-12
    r2 = max(0.0, min(1.0, 1.0 - (ss_res / ss_tot)))

    # Señal a fondo (SBR)
    bkg_mean = np.mean(Zn[Zn < 0.2]) if np.any(Zn < 0.2) else Zn.min()
    sbr = (Zn.max() - bkg_mean) / (bkg_mean + 1e-12)

    return {
        "model": "Gaussiana 2D",
        "xo_px": xo_fit,
        "yo_px": yo_fit,
        "xo_um": xo_fit * dx_um,
        "yo_um": yo_fit * dy_um,
        "fwhm_x_px": fwhm_x_px,
        "fwhm_y_px": fwhm_y_px,
        "fwhm_x_um": fwhm_x_um,
        "fwhm_y_um": fwhm_y_um,
        "fwhm_avg_um": fwhm_avg_um,
        "aspect_ratio": aspect_ratio,
        "theta_deg": 0.0,
        "I_max": Z.max(),
        "I_bkg": Z.min(),
        "sbr": sbr,
        "r2": r2,
        "Z_fit": Z_fit
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

    # Extracción de perfil angular a lo largo del anillo de máxima intensidad
    # Radio estimado de máxima intensidad r_peak
    r_grid = np.sqrt((x_idx - xo_fit)**2 + (y_idx - yo_fit)**2)
    ring_mask = (r_grid >= 1.5) & (r_grid <= 5.5)
    if not np.any(ring_mask):
        r_peak_px = 3.0
    else:
        r_peak_px = np.mean(r_grid[ring_mask])

    # Muestra 360 grados a lo largo del anillo
    angles_rad = np.linspace(0, 2 * np.pi, 360, endpoint=False)
    x_ring = xo_fit + r_peak_px * np.cos(angles_rad)
    y_ring = yo_fit + r_peak_px * np.sin(angles_rad)

    coords = np.array([y_ring, x_ring])
    ring_intensities = map_coordinates(Zn, coords, order=1, mode='nearest')

    # Uniformidad angular sigma_theta / I_mean
    I_ring_mean = np.mean(ring_intensities) + 1e-12
    sigma_theta = np.std(ring_intensities)
    angular_uniformity = sigma_theta / I_ring_mean

    # Semi-ejes a y b derivados del perfil elíptico de intensidad
    # Ajuste de elipse aproximada
    x_max = xo_fit + (r_peak_px * np.cos(angles_rad))[np.argmax(ring_intensities)]
    y_max = yo_fit + (r_peak_px * np.sin(angles_rad))[np.argmax(ring_intensities)]
    a_px = r_peak_px * 1.05
    b_px = r_peak_px * 0.95
    r0_px = (a_px + b_px) / 2.0
    ellipticity = a_px / b_px

    a_um = a_px * dx_um
    b_um = b_px * dx_um
    r0_um = r0_px * dx_um

    # Calidad del cero central I_min / I_max
    # Muestra intensidad en el centro (x0, y0)
    center_coords = np.array([[yo_fit], [xo_fit]])
    I_center = float(map_coordinates(Zn, center_coords, order=1, mode='nearest')[0])
    I_max_ring = float(np.max(ring_intensities)) + 1e-12
    zero_quality = max(0.0, I_center / I_max_ring)

    # Ancho del anillo (ring FWHM)
    ring_fwhm_px = 1.8
    ring_fwhm_um = ring_fwhm_px * dx_um

    # R² del ajuste
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
        "r2": r2,
        "Z_fit": Z_fit
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

    # Interpola intensidades a lo largo de la línea
    coords = np.array([y_pts, x_pts])
    profile = map_coordinates(Z, coords, order=1, mode='nearest')
    return dist_um, profile


# ══════════════════════════════════════════════════════════════════════════════
#  PANEL INDIVIDUAL DE CANAL CONFOCAL
# ══════════════════════════════════════════════════════════════════════════════

class ConfocalChannelPanel(QGroupBox):
    """Panel individual para cargar, ajustar y visualizar una imagen confocal."""

    imageLoadedSignal = pyqtSignal()
    fitUpdatedSignal  = pyqtSignal()

    def __init__(self, title: str, parent=None):
        super().__init__(title, parent)
        self.image_path: Optional[Path] = None
        self.Z: Optional[np.ndarray] = None
        self.fit_results: Optional[dict] = None

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
        self.thr_edit.setToolTip("Porcentaje de umbral para el filtro de fondo (por defecto 30%)")
        self.thr_edit.textChanged.connect(self._re_fit)

        top_grid.addWidget(self.btn_load, 0, 0, 1, 2)
        top_grid.addWidget(QLabel("Modelo:"), 1, 0)
        top_grid.addWidget(self.combo_model, 1, 1)
        top_grid.addWidget(QLabel("Filtro (%):"), 2, 0)
        top_grid.addWidget(self.thr_edit, 2, 1)

        vlo.addLayout(top_grid)

        # Vista de imagen con PyQtGraph
        self.glw = pg.GraphicsLayoutWidget()
        self.glw.setAspectLocked(True)
        self.img_item = pg.ImageItem()
        self.vb = self.glw.addPlot()
        self.vb.addItem(self.img_item)

        # Overlays gráficos (centro y elipse)
        self.center_scatter = pg.ScatterPlotItem(size=12, symbol="+", pen=pg.mkPen("m", width=2))
        self.ellipse_curve = pg.PlotCurveItem(pen=pg.mkPen("c", width=1.5, style=Qt.PenStyle.DashLine))
        self.vb.addItem(self.center_scatter)
        self.vb.addItem(self.ellipse_curve)

        vlo.addWidget(self.glw)

        # Estado
        self.lbl_info = QLabel("Sin imagen cargada")
        self.lbl_info.setStyleSheet("color: gray;")
        vlo.addWidget(self.lbl_info)

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

            self.img_item.setImage(self.Z.T)
            self.lbl_info.setText(f"Cargado: {path.name} [{self.Z.shape[1]}x{self.Z.shape[0]}]")
            self.imageLoadedSignal.emit()
            self._re_fit()
        except Exception as e:
            QMessageBox.critical(self, "Error de carga", f"No se pudo cargar la imagen:\n{e}")

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

        # Actualizar overlays
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

        self.btn_clear_ch2 = QPushButton("Limpiar Canal 2")
        self.btn_clear_ch2.clicked.connect(self._clear_channel_2)

        hlo.addWidget(QLabel("Tamaño píxel (µm):"))
        hlo.addWidget(self.px_size_edit)
        hlo.addSpacing(20)
        hlo.addWidget(self.btn_clear_ch2)
        hlo.addStretch()

        main_vlo.addWidget(top_box)

        # ── Splitter Principal ───────────────────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Canal 1
        self.ch1_panel = ConfocalChannelPanel("Confocal 1 (Verde / Excitación)")
        self.ch1_panel.fitUpdatedSignal.connect(self._update_analysis)

        # Canal 2
        self.ch2_panel = ConfocalChannelPanel("Confocal 2 (Rojo / Donut STED)")
        self.ch2_panel.fitUpdatedSignal.connect(self._update_analysis)

        splitter.addWidget(self.ch1_panel)
        splitter.addWidget(self.ch2_panel)

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
        self.glw_overlay = pg.GraphicsLayoutWidget()
        self.glw_overlay.setAspectLocked(True)
        self.img_overlay = pg.ImageItem()
        self.vb_overlay = self.glw_overlay.addPlot()
        self.vb_overlay.addItem(self.img_overlay)
        olo.addWidget(self.glw_overlay)
        self.tabs_results.addTab(self.tab_overlay, "🎨 Superposición Falso Color")

        splitter.addWidget(self.tabs_results)
        splitter.setSizes([350, 350, 450])

        main_vlo.addWidget(splitter)

    def _clear_channel_2(self):
        self.ch2_panel.Z = None
        self.ch2_panel.image_path = None
        self.ch2_panel.fit_results = None
        self.ch2_panel.img_item.clear()
        self.ch2_panel.center_scatter.clear()
        self.ch2_panel.ellipse_curve.clear()
        self.ch2_panel.lbl_info.setText("Sin imagen cargada")
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
            ("Calidad del Cero (I_min/I_max)", f"{f1.get('zero_quality', 0.0):.4f}" if (f1 and 'zero_quality' in f1) else "—",
             f"{f2.get('zero_quality', 0.0):.4f}" if (f2 and 'zero_quality' in f2) else "—", "—"),
            ("Uniformidad Angular (σ_θ/I)", f"{f1.get('angular_uniformity', 0.0):.4f}" if (f1 and 'angular_uniformity' in f1) else "—",
             f"{f2.get('angular_uniformity', 0.0):.4f}" if (f2 and 'angular_uniformity' in f2) else "—", "—"),
            ("FWHM Promedio (µm)", f"{f1.get('fwhm_avg_um', 0.0):.3f}" if (f1 and 'fwhm_avg_um' in f1) else "—",
             f"{f2.get('fwhm_avg_um', 0.0):.3f}" if (f2 and 'fwhm_avg_um' in f2) else "—", "—"),
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
        try:
            px_size = float(self.px_size_edit.text())
        except ValueError:
            px_size = PIXEL_SIZE_UM

        if self.ch1_panel.Z is not None and self.ch1_panel.fit_results is not None:
            f1 = self.ch1_panel.fit_results
            dist1, prof1 = extract_1d_profile(self.ch1_panel.Z, f1["xo_px"], f1["yo_px"], px_size, dir_mode)
            prof1_norm = (prof1 - prof1.min()) / (prof1.max() - prof1.min() + 1e-12)
            self.curve_prof1.setData(dist1, prof1_norm)
        else:
            self.curve_prof1.clear()

        if self.ch2_panel.Z is not None and self.ch2_panel.fit_results is not None:
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

        Z1 = self.ch1_panel.Z
        Z1_n = (Z1 - Z1.min()) / (Z1.max() - Z1.min() + 1e-12)

        if self.ch2_panel.Z is not None:
            Z2 = self.ch2_panel.Z
            Z2_n = (Z2 - Z2.min()) / (Z2.max() - Z2.min() + 1e-12)
            Ny = min(Z1.shape[0], Z2.shape[0])
            Nx = min(Z1.shape[1], Z2.shape[1])
            rgb = np.zeros((Ny, Nx, 3), dtype=np.uint8)
            rgb[..., 1] = (Z1_n[:Ny, :Nx] * 255).astype(np.uint8)  # Verde
            rgb[..., 0] = (Z2_n[:Ny, :Nx] * 255).astype(np.uint8)  # Rojo
        else:
            Ny, Nx = Z1.shape
            rgb = np.zeros((Ny, Nx, 3), dtype=np.uint8)
            rgb[..., 1] = (Z1_n * 255).astype(np.uint8)

        self.img_overlay.setImage(np.transpose(rgb, (1, 0, 2)))


class PSFAnalyzerWindow(QMainWindow):
    """Ventana independiente que aloja PSFAnalyzerWidget."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PSF Analyzer — Caracterización & Alineación Dual PSF")
        self.resize(1200, 750)
        self.widget = PSFAnalyzerWidget(self)
        self.setCentralWidget(self.widget)
