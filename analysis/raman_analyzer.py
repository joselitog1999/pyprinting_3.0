# -*- coding: utf-8 -*-
"""
raman_analyzer.py — Analizador Espectroscópico Raman & SERS
PyPrinting 3.0 — UNSAM Nanofotónica

Entorno cuantitativo y visual para el estudio de espectros Raman y SERS
exportados por Andor Solis (.asc, .txt, .csv, .dat).

Características:
  - Carga tolerante de archivos ASCII de Andor Solis (cabeceras ~50 líneas, comas y puntos decimales).
  - Conversión interactiva bidireccional entre Wavelength (nm), Raman Shift (cm^-1) y Energía (eV).
  - Reglas verticales interactivas móviles (Cursores A y B) con arrastre libre y lectura en tiempo real.
  - Medición cuantitativa entre cursores: separación Delta nu, cociente de intensidades (ej. bandas D/G) e integración de área.
  - Corrección de línea base y fluorescencia en tiempo real: AsLS, AirPLS, ModPoly, derivadas, morfológico y splines.
  - Filtros de suavizado: Savitzky-Golay, Fourier FFT (pasa-bajos, pasa-altos, notch 50 Hz), Whittaker y Gaussiano.
  - Eliminador de rayos cósmicos (spikes de 1-2 píxeles) en detectores CCD con 1 solo clic.
  - Detección de picos Raman y ajuste espectral no lineal (Pseudo-Voigt, Lorentziano y Gaussiano).
  - Termometría fototérmica in-situ por cociente de intensidades Anti-Stokes / Stokes (distribución de Boltzmann).
  - Marcadores de referencia estándar SERS (Silicio 520.7, 4-MBA, Rodamina 6G, Grafeno D/G, BPE).
  - Exportación de datos limpios a CSV y figuras en alta resolución (PNG 600 DPI / vectorial).
"""
from __future__ import annotations
import sys
import os
import math
from pathlib import Path
from typing import Optional, Dict, List, Tuple

# ── Registrar directorio raíz y .venv para resolver dependencias ───────────────
_curr = Path(__file__).resolve().parent
while _curr != _curr.parent:
    if (_curr / "config.py").exists():
        _venv_site = _curr / ".venv" / "Lib" / "site-packages"
        if _venv_site.exists() and sys.version_info[:2] == (3, 13) and str(_venv_site) not in sys.path:
            sys.path.insert(0, str(_venv_site))
        for _p in [str(_curr), str(_curr / "core"), str(_curr / "modules"), str(_curr / "analysis")]:
            if _p not in sys.path:
                sys.path.insert(0, _p)
        break
    _curr = _curr.parent

import numpy as np
import pyqtgraph as pg
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QSpinBox, QDoubleSpinBox, QSlider,
    QCheckBox, QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QFileDialog, QMessageBox, QSplitter, QGroupBox, QFormLayout, QScrollArea,
    QFrame
)
from PyQt6.QtGui import QFont, QColor, QPen, QIcon

from core.raman_engine import (
    parse_andor_solis_file,
    wavelength_to_raman_shift,
    raman_shift_to_wavelength,
    raman_shift_to_ev,
    crop_spectrum,
    remove_cosmic_rays,
    baseline_asls,
    baseline_airpls,
    baseline_modpoly,
    baseline_derivative,
    baseline_rolling_ball,
    baseline_spline_anchors,
    smooth_savgol,
    smooth_fourier,
    smooth_whittaker,
    smooth_gaussian,
    detect_peaks_spectrum,
    fit_peak_profile,
    fit_multi_peak_profile,
    model_gaussian,
    model_lorentzian,
    model_pseudo_voigt,
    calculate_photothermal_temperature,
    compute_dual_cursor_metrics,
    RAMAN_REFERENCE_STANDARDS,
    interpolate_spectra_to_common_grid,
    normalize_spectrum_matrix,
    compute_mean_std_spectrum,
    extract_band_kinetics,
    compute_spectral_pca
)
from analysis.multi_spectrum_widget import MultiSpectrumWidget

# Configuración visual de PyQtGraph
pg.setConfigOption("background", "#11111b")  # Catppuccin Mocha Crust
pg.setConfigOption("foreground", "#cdd6f4")  # Text
pg.setConfigOptions(antialias=True)


class RamanAnalyzerWindow(QMainWindow):
    """Ventana Principal del Analizador de Espectros Raman & SERS."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("RamanAnalyzer 3.0 — Espectroscopía Cuantitativa & SERS (UNSAM Nanofotónica)")
        self.resize(1420, 880)
        self.setMinimumSize(1100, 700)

        # Estado del espectro original
        self.filepath: Optional[Path] = None
        self.metadata: Dict[str, str] = {}
        self.raw_wls: np.ndarray = np.array([])       # Longitudes de onda originales (nm)
        self.raw_counts: np.ndarray = np.array([])    # Cuentas originales

        # Estado del espectro recortado (ROI) y procesado
        self.cropped_wls: np.ndarray = np.array([])   # Longitudes de onda activas recortadas
        self.cropped_raw_counts: np.ndarray = np.array([]) # Cuentas activas recortadas
        self.crop_mask: np.ndarray = np.array([])     # Máscara de selección
        self.active_counts: np.ndarray = np.array([]) # Cuentas tras filtrado/spikes
        self.baseline: np.ndarray = np.array([])      # Línea base estimada
        self.corrected: np.ndarray = np.array([])     # Cuentas - Línea base
        self.spike_mask: np.ndarray = np.array([])    # Posiciones de rayos cósmicos

        self.fitted_curve_x: Optional[np.ndarray] = None
        self.fitted_curve_y: Optional[np.ndarray] = None
        self.multi_fit_curves: List[pg.PlotDataItem] = []
        self.multi_fit_subpeaks: List[Dict[str, float]] = []
        self.detected_peaks: List[Dict[str, float]] = []
        self.peak_labels: List[pg.TextItem] = []
        self.manual_anchor_indices: List[int] = []

        # Configuración de excitación
        self.laser_nm: float = 532.0
        self.unit_mode: str = "raman_shift"  # 'raman_shift' (cm^-1) o 'wavelength' (nm) o 'energy' (eV)

        self._setup_styles()
        self._setup_ui()
        self._setup_plots()
        self._setup_cursors()

        # Cargar archivo de demostración si existe
        demo_file = Path(__file__).resolve().parent.parent / "reserva" / "90%_in_red_10s_3_em.asc"
        if demo_file.exists():
            self.load_spectrum_file(demo_file)

    def _setup_styles(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #11111B;
            }
            QGroupBox {
                border: 1px solid #313244;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 12px;
                font-weight: bold;
                color: #89B4FA;
                background-color: #181825;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 6px;
                background-color: #181825;
            }
            QLabel {
                color: #CDD6F4;
                font-size: 9pt;
            }
            QPushButton {
                background-color: #313244;
                color: #CDD6F4;
                border: 1px solid #45475A;
                border-radius: 6px;
                padding: 6px 12px;
                font-weight: bold;
                font-size: 9pt;
            }
            QPushButton:hover {
                background-color: #45475A;
                color: #FFFFFF;
                border: 1px solid #89B4FA;
            }
            QPushButton:pressed {
                background-color: #585B70;
            }
            QComboBox, QSpinBox, QDoubleSpinBox {
                background-color: #181825;
                color: #CDD6F4;
                border: 1px solid #45475A;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 9pt;
            }
            QComboBox QAbstractItemView {
                background-color: #181825;
                color: #CDD6F4;
                selection-background-color: #89B4FA;
                selection-color: #11111B;
            }
            QTabWidget::pane {
                border: 1px solid #313244;
                background-color: #181825;
                border-radius: 6px;
            }
            QTabBar::tab {
                background-color: #181825;
                color: #A6ADC8;
                border: 1px solid #313244;
                padding: 6px 12px;
                margin-right: 2px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                font-weight: bold;
                font-size: 8.5pt;
            }
            QTabBar::tab:selected {
                background-color: #313244;
                color: #89B4FA;
                border-bottom: 2px solid #89B4FA;
            }
            QTableWidget {
                background-color: #11111B;
                color: #CDD6F4;
                border: 1px solid #313244;
                border-radius: 4px;
                gridline-color: #313244;
                font-size: 8.5pt;
            }
            QHeaderView::section {
                background-color: #181825;
                color: #89B4FA;
                font-weight: bold;
                border: 1px solid #313244;
                padding: 4px;
            }
            QScrollBar:vertical {
                background: #181825;
                width: 10px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #45475A;
                min-height: 20px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical:hover {
                background: #89B4FA;
            }
            QCheckBox {
                color: #CDD6F4;
                font-size: 9pt;
                spacing: 6px;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
                border-radius: 3px;
                border: 1px solid #45475A;
                background-color: #181825;
            }
            QCheckBox::indicator:checked {
                background-color: #89B4FA;
                border-color: #89B4FA;
            }
        """)

    def _setup_ui(self):
        self.main_nav_tabs = QTabWidget()
        self.setCentralWidget(self.main_nav_tabs)

        # ── Pestaña 1: Espectro Individual ────────────────────────────────────
        self.tab_single = QWidget()
        single_layout = QHBoxLayout(self.tab_single)
        single_layout.setContentsMargins(6, 6, 6, 6)
        single_layout.setSpacing(6)

        # Splitter principal (Controles a la izquierda, Gráficos a la derecha)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── Panel de Controles (Scrollable) ───────────────────────────────────
        controls_scroll = QScrollArea()
        controls_scroll.setWidgetResizable(True)
        controls_scroll.setMinimumWidth(440)
        controls_scroll.setMaximumWidth(520)
        controls_scroll.setFrameShape(QFrame.Shape.NoFrame)

        controls_content = QWidget()
        controls_vlo = QVBoxLayout(controls_content)
        controls_vlo.setContentsMargins(4, 4, 4, 4)
        controls_vlo.setSpacing(8)

        # 1. Cabecera y Archivo
        file_box = QGroupBox("📂 Archivo de Espectro")
        file_flo = QVBoxLayout(file_box)

        btn_row = QHBoxLayout()
        self.btn_open_file = QPushButton("Examinar Espectro...")
        self.btn_open_file.setToolTip("Abrir archivo de Andor Solis (.asc, .txt, .csv, .dat)")
        self.btn_open_file.clicked.connect(self._on_browse_file)
        self.btn_open_file.setStyleSheet("background-color: #89B4FA; color: #11111B; font-weight: bold;")

        self.btn_load_demo = QPushButton("Cargar Demo Real")
        self.btn_load_demo.setToolTip("Carga el archivo real de Andor Solis 90%_in_red_10s_3_em.asc")
        self.btn_load_demo.clicked.connect(self._on_load_demo)
        btn_row.addWidget(self.btn_open_file)
        btn_row.addWidget(self.btn_load_demo)
        file_flo.addLayout(btn_row)

        self.lbl_file_info = QLabel("Ningún archivo cargado")
        self.lbl_file_info.setStyleSheet("color: #A6ADC8; font-size: 8pt; font-style: italic;")
        self.lbl_file_info.setWordWrap(True)
        file_flo.addWidget(self.lbl_file_info)

        controls_vlo.addWidget(file_box)

        # 2. Pestañas de Procesamiento y Parámetros
        self.tabs = QTabWidget()

        # Tab: Excitación y Ejes
        tab_axis = QWidget()
        ax_flo = QFormLayout(tab_axis)
        ax_flo.setContentsMargins(8, 8, 8, 8)
        ax_flo.setSpacing(6)

        self.combo_laser = QComboBox()
        self.combo_laser.addItems(["532.0 nm (Verde)", "632.8 nm (He-Ne)", "637.0 nm (Rojo)", "785.0 nm (NIR)", "Personalizado..."])
        self.combo_laser.currentIndexChanged.connect(self._on_laser_combo_changed)
        ax_flo.addRow("Láser Excitación:", self.combo_laser)

        self.spin_laser_custom = QDoubleSpinBox()
        self.spin_laser_custom.setRange(200.0, 2000.0)
        self.spin_laser_custom.setValue(532.0)
        self.spin_laser_custom.setSuffix(" nm")
        self.spin_laser_custom.valueChanged.connect(self._on_laser_value_changed)
        self.spin_laser_custom.setEnabled(False)
        ax_flo.addRow("λ Láser personalizada:", self.spin_laser_custom)

        self.combo_units = QComboBox()
        self.combo_units.addItems(["Corrimiento Raman (cm⁻¹)", "Longitud de Onda (nm)", "Energía Relativa (eV)"])
        self.combo_units.currentIndexChanged.connect(self._on_units_changed)
        ax_flo.addRow("Unidades Eje X:", self.combo_units)

        self.check_flip_x = QCheckBox("Invertir Eje X (Decreciente)")
        self.check_flip_x.toggled.connect(self._update_plots)
        ax_flo.addRow("", self.check_flip_x)

        self.tabs.addTab(tab_axis, "🔬 Excitación")

        # Tab: Recorte y Pre-procesado (ROI)
        tab_crop = QWidget()
        cr_vlo = QVBoxLayout(tab_crop)
        cr_vlo.setContentsMargins(8, 8, 8, 8)
        cr_vlo.setSpacing(8)

        # Acciones Rápidas
        grp_quick = QGroupBox("Atajos de Recorte Rápido")
        quick_vlo = QVBoxLayout(grp_quick)
        self.btn_crop_cursors = QPushButton("✂️ Recortar a Cursores A y B")
        self.btn_crop_cursors.setStyleSheet("background-color: #A6E3A1; color: #11111B; font-weight: bold;")
        self.btn_crop_cursors.setToolTip("Recorta el espectro al intervalo definido visualmente entre el Cursor A y el Cursor B")
        self.btn_crop_cursors.clicked.connect(self._on_crop_to_cursors)
        quick_vlo.addWidget(self.btn_crop_cursors)

        self.btn_crop_rayleigh = QPushButton("⚡ Recortar Láser/Filtro (< 150 cm⁻¹)")
        self.btn_crop_rayleigh.setToolTip("Recorta el flanco del filtro Rayleigh por debajo de 150 cm⁻¹ para evitar distorsión de línea base")
        self.btn_crop_rayleigh.clicked.connect(self._on_crop_rayleigh)
        quick_vlo.addWidget(self.btn_crop_rayleigh)

        self.btn_reset_crop = QPushButton("↺ Restaurar Rango Completo")
        self.btn_reset_crop.setStyleSheet("background-color: #F38BA8; color: #11111B; font-weight: bold;")
        self.btn_reset_crop.setToolTip("Deshace cualquier recorte y recupera los datos crudos originales al 100%")
        self.btn_reset_crop.clicked.connect(self._on_reset_crop)
        quick_vlo.addWidget(self.btn_reset_crop)
        cr_vlo.addWidget(grp_quick)

        # Recorte por Rango Físico X
        grp_range = QGroupBox("Límites Espectrales [X Mín, X Máx]")
        range_flo = QFormLayout(grp_range)
        self.check_enable_crop_x = QCheckBox("Habilitar Límite por Rango X")
        self.check_enable_crop_x.setChecked(False)
        self.check_enable_crop_x.toggled.connect(self._recalculate_all)
        range_flo.addRow(self.check_enable_crop_x)

        self.spin_crop_xmin = QDoubleSpinBox()
        self.spin_crop_xmin.setRange(-10000.0, 50000.0)
        self.spin_crop_xmin.setDecimals(1)
        self.spin_crop_xmin.setValue(0.0)
        self.spin_crop_xmin.valueChanged.connect(self._on_crop_params_changed)
        range_flo.addRow("X Mínimo:", self.spin_crop_xmin)

        self.spin_crop_xmax = QDoubleSpinBox()
        self.spin_crop_xmax.setRange(-10000.0, 50000.0)
        self.spin_crop_xmax.setDecimals(1)
        self.spin_crop_xmax.setValue(4000.0)
        self.spin_crop_xmax.valueChanged.connect(self._on_crop_params_changed)
        range_flo.addRow("X Máximo:", self.spin_crop_xmax)
        cr_vlo.addWidget(grp_range)

        # Recorte por Puntos de Borde (CCD Sensor Edge Trimming)
        grp_trim = QGroupBox("Poda de Bordes del Sensor CCD")
        trim_flo = QFormLayout(grp_trim)
        self.spin_trim_left = QSpinBox()
        self.spin_trim_left.setRange(0, 500)
        self.spin_trim_left.setValue(0)
        self.spin_trim_left.setSuffix(" pts")
        self.spin_trim_left.valueChanged.connect(self._recalculate_all)
        trim_flo.addRow("Podar Inicio (izq):", self.spin_trim_left)

        self.spin_trim_right = QSpinBox()
        self.spin_trim_right.setRange(0, 500)
        self.spin_trim_right.setValue(0)
        self.spin_trim_right.setSuffix(" pts")
        self.spin_trim_right.valueChanged.connect(self._recalculate_all)
        trim_flo.addRow("Podar Fin (der):", self.spin_trim_right)
        cr_vlo.addWidget(grp_trim)

        # Estado del recorte
        self.lbl_crop_status = QLabel("Puntos activos: 0 / 0 (100.0%)")
        self.lbl_crop_status.setStyleSheet("color: #89B4FA; font-weight: bold; font-family: monospace; font-size: 8.5pt;")
        cr_vlo.addWidget(self.lbl_crop_status)
        cr_vlo.addStretch()

        self.tabs.addTab(tab_crop, "✂️ Recorte (ROI)")

        # Tab: Línea Base
        tab_baseline = QWidget()
        bl_vlo = QVBoxLayout(tab_baseline)
        bl_vlo.setContentsMargins(8, 8, 8, 8)
        bl_vlo.setSpacing(6)

        self.check_enable_baseline = QCheckBox("Habilitar Corrección de Línea Base")
        self.check_enable_baseline.setChecked(True)
        self.check_enable_baseline.toggled.connect(self._recalculate_all)
        bl_vlo.addWidget(self.check_enable_baseline)

        bl_form = QFormLayout()
        self.combo_baseline_mode = QComboBox()
        self.combo_baseline_mode.addItems([
            "AsLS (Asymmetric Least Squares)",
            "AirPLS (Adaptativo Automático)",
            "Polinómico Modificado (ModPoly)",
            "Tercera Derivada (Zero-Crossing)",
            "Morfológico (Rolling Ball / Top-Hat)",
            "Spline Manual (Puntos Ancla)"
        ])
        self.combo_baseline_mode.currentIndexChanged.connect(self._recalculate_all)
        bl_form.addRow("Método:", self.combo_baseline_mode)

        # Parámetros AsLS / AirPLS
        self.spin_bl_lambda = QDoubleSpinBox()
        self.spin_bl_lambda.setRange(1.0, 1e9)
        self.spin_bl_lambda.setValue(1e5)
        self.spin_bl_lambda.setSingleStep(1e4)
        self.spin_bl_lambda.valueChanged.connect(self._recalculate_all)
        bl_form.addRow("Suavidad λ (AsLS/AirPLS):", self.spin_bl_lambda)

        self.spin_bl_p = QDoubleSpinBox()
        self.spin_bl_p.setRange(1e-5, 0.5)
        self.spin_bl_p.setDecimals(5)
        self.spin_bl_p.setValue(0.001)
        self.spin_bl_p.setSingleStep(0.0005)
        self.spin_bl_p.valueChanged.connect(self._recalculate_all)
        bl_form.addRow("Asimetría p (AsLS):", self.spin_bl_p)

        self.spin_bl_poly_order = QSpinBox()
        self.spin_bl_poly_order.setRange(1, 8)
        self.spin_bl_poly_order.setValue(4)
        self.spin_bl_poly_order.valueChanged.connect(self._recalculate_all)
        bl_form.addRow("Grado Polinómico:", self.spin_bl_poly_order)

        self.spin_bl_rolling_radius = QSpinBox()
        self.spin_bl_rolling_radius.setRange(5, 500)
        self.spin_bl_rolling_radius.setValue(50)
        self.spin_bl_rolling_radius.valueChanged.connect(self._recalculate_all)
        bl_form.addRow("Radio Morfológico (px):", self.spin_bl_rolling_radius)

        bl_vlo.addLayout(bl_form)

        self.btn_clear_anchors = QPushButton("Limpiar Puntos Ancla Manuales")
        self.btn_clear_anchors.clicked.connect(self._on_clear_anchors)
        bl_vlo.addWidget(self.btn_clear_anchors)

        self.tabs.addTab(tab_baseline, "📉 Línea Base")

        # Tab: Suavizado & Rayos Cósmicos
        tab_filters = QWidget()
        flt_vlo = QVBoxLayout(tab_filters)
        flt_vlo.setContentsMargins(8, 8, 8, 8)
        flt_vlo.setSpacing(6)

        # Botón Rayos Cósmicos
        self.btn_cosmic_rays = QPushButton("⚡ Limpiar Rayos Cósmicos (Spikes)")
        self.btn_cosmic_rays.setStyleSheet("background-color: #F38BA8; color: #11111B; font-weight: bold;")
        self.btn_cosmic_rays.setToolTip("Elimina spikes de 1 o 2 píxeles típicos en exposiciones CCD")
        self.btn_cosmic_rays.clicked.connect(self._on_remove_cosmic_rays)
        flt_vlo.addWidget(self.btn_cosmic_rays)

        self.lbl_cosmic_status = QLabel("Rayos cósmicos: sin procesar")
        self.lbl_cosmic_status.setStyleSheet("color: #A6ADC8; font-size: 8pt;")
        flt_vlo.addWidget(self.lbl_cosmic_status)

        flt_vlo.addSpacing(6)

        self.check_enable_smooth = QCheckBox("Habilitar Suavizado")
        self.check_enable_smooth.toggled.connect(self._recalculate_all)
        flt_vlo.addWidget(self.check_enable_smooth)

        flt_form = QFormLayout()
        self.combo_smooth_mode = QComboBox()
        self.combo_smooth_mode.addItems([
            "Savitzky-Golay (Conserva Picos)",
            "Fourier FFT (Pasa-Bajos)",
            "Fourier FFT (Pasa-Altos)",
            "Fourier FFT (Filtro Notch 50 Hz)",
            "Whittaker-Eilers",
            "Gaussiano"
        ])
        self.combo_smooth_mode.currentIndexChanged.connect(self._recalculate_all)
        flt_form.addRow("Método:", self.combo_smooth_mode)

        self.spin_sg_window = QSpinBox()
        self.spin_sg_window.setRange(3, 101)
        self.spin_sg_window.setValue(11)
        self.spin_sg_window.setSingleStep(2)
        self.spin_sg_window.valueChanged.connect(self._recalculate_all)
        flt_form.addRow("Ventana SG (pts impares):", self.spin_sg_window)

        self.spin_sg_order = QSpinBox()
        self.spin_sg_order.setRange(1, 5)
        self.spin_sg_order.setValue(3)
        self.spin_sg_order.valueChanged.connect(self._recalculate_all)
        flt_form.addRow("Orden Polinómico SG:", self.spin_sg_order)

        self.spin_fft_cutoff = QDoubleSpinBox()
        self.spin_fft_cutoff.setRange(0.005, 0.5)
        self.spin_fft_cutoff.setValue(0.15)
        self.spin_fft_cutoff.setSingleStep(0.02)
        self.spin_fft_cutoff.valueChanged.connect(self._recalculate_all)
        flt_form.addRow("Corte Fourier (fracción):", self.spin_fft_cutoff)

        self.spin_gauss_sigma = QDoubleSpinBox()
        self.spin_gauss_sigma.setRange(0.2, 50.0)
        self.spin_gauss_sigma.setValue(2.0)
        self.spin_gauss_sigma.setSingleStep(0.5)
        self.spin_gauss_sigma.valueChanged.connect(self._recalculate_all)
        flt_form.addRow("Sigma Gaussiano (px):", self.spin_gauss_sigma)

        flt_vlo.addLayout(flt_form)
        self.tabs.addTab(tab_filters, "✨ Filtros")

        # Tab: Picos & Ajuste
        tab_peaks = QWidget()
        pk_vlo = QVBoxLayout(tab_peaks)
        pk_vlo.setContentsMargins(8, 8, 8, 8)
        pk_vlo.setSpacing(6)

        # Parámetros de detección
        grp_det = QGroupBox("Criterios de Búsqueda de Picos")
        pk_form = QFormLayout(grp_det)

        self.check_auto_prominence = QCheckBox("Prominencia Automática (adaptativa)")
        self.check_auto_prominence.setChecked(True)
        self.check_auto_prominence.toggled.connect(self._on_auto_prominence_toggled)
        pk_form.addRow(self.check_auto_prominence)

        self.spin_peak_prominence = QDoubleSpinBox()
        self.spin_peak_prominence.setRange(0.1, 1e7)
        self.spin_peak_prominence.setValue(100.0)
        self.spin_peak_prominence.setEnabled(False)
        self.spin_peak_prominence.valueChanged.connect(self._on_find_peaks)
        pk_form.addRow("Prominencia Manual:", self.spin_peak_prominence)

        self.spin_peak_min_height = QDoubleSpinBox()
        self.spin_peak_min_height.setRange(0.0, 1e7)
        self.spin_peak_min_height.setValue(0.0)
        self.spin_peak_min_height.setToolTip("Cuentas mínimas sobre la línea base para considerar un pico")
        self.spin_peak_min_height.valueChanged.connect(self._on_find_peaks)
        pk_form.addRow("Altura Mínima (cuentas):", self.spin_peak_min_height)

        self.spin_peak_min_width = QDoubleSpinBox()
        self.spin_peak_min_width.setRange(0.0, 500.0)
        self.spin_peak_min_width.setValue(3.0)
        self.spin_peak_min_width.setSuffix(" cm⁻¹")
        self.spin_peak_min_width.setToolTip("Filtra ruido ultra-estrecho de 1-2 píxeles")
        self.spin_peak_min_width.valueChanged.connect(self._on_find_peaks)
        pk_form.addRow("Ancho Mínimo FWHM:", self.spin_peak_min_width)

        self.spin_peak_max_width = QDoubleSpinBox()
        self.spin_peak_max_width.setRange(0.0, 2000.0)
        self.spin_peak_max_width.setValue(150.0)
        self.spin_peak_max_width.setSuffix(" cm⁻¹")
        self.spin_peak_max_width.setToolTip("Filtra fondos de fluorescencia anchos residuales")
        self.spin_peak_max_width.valueChanged.connect(self._on_find_peaks)
        pk_form.addRow("Ancho Máximo FWHM:", self.spin_peak_max_width)

        self.spin_peak_distance = QSpinBox()
        self.spin_peak_distance.setRange(1, 200)
        self.spin_peak_distance.setValue(4)
        self.spin_peak_distance.valueChanged.connect(self._on_find_peaks)
        pk_form.addRow("Distancia Mín (pts):", self.spin_peak_distance)

        self.combo_sort_peaks = QComboBox()
        self.combo_sort_peaks.addItems([
            "Posición Creciente (cm⁻¹)",
            "Intensidad Decreciente",
            "Prominencia Decreciente"
        ])
        self.combo_sort_peaks.currentIndexChanged.connect(self._on_find_peaks)
        pk_form.addRow("Ordenar Por:", self.combo_sort_peaks)

        self.check_show_peak_labels = QCheckBox("Mostrar etiquetas numéricas en gráfico")
        self.check_show_peak_labels.setChecked(True)
        self.check_show_peak_labels.toggled.connect(self._update_plots)
        pk_form.addRow(self.check_show_peak_labels)

        pk_vlo.addWidget(grp_det)

        # Fila de acciones de picos
        pk_btn_row = QHBoxLayout()
        btn_find_pk = QPushButton("🔍 Encontrar Picos")
        btn_find_pk.setStyleSheet("background-color: #89B4FA; color: #11111B; font-weight: bold;")
        btn_find_pk.clicked.connect(self._on_find_peaks)
        pk_btn_row.addWidget(btn_find_pk)

        self.btn_add_peak = QPushButton("➕ En Cursor A")
        self.btn_add_peak.setToolTip("Agrega un pico manualmente en la posición exacta del Cursor A")
        self.btn_add_peak.clicked.connect(self._on_add_peak_at_cursor_a)
        pk_btn_row.addWidget(self.btn_add_peak)

        self.btn_del_peak = QPushButton("❌ Eliminar")
        self.btn_del_peak.setToolTip("Elimina el pico seleccionado en la tabla")
        self.btn_del_peak.clicked.connect(self._on_delete_selected_peak)
        pk_btn_row.addWidget(self.btn_del_peak)

        self.btn_copy_peaks = QPushButton("📋 Copiar")
        self.btn_copy_peaks.setToolTip("Copia la tabla de picos al portapapeles en formato TSV (para Origin / Excel)")
        self.btn_copy_peaks.clicked.connect(self._on_copy_peak_table)
        pk_btn_row.addWidget(self.btn_copy_peaks)

        pk_vlo.addLayout(pk_btn_row)

        # Tabla de Picos (5 columnas)
        self.table_peaks = QTableWidget(0, 5)
        self.table_peaks.setHorizontalHeaderLabels(["#", "Posición", "Cuentas", "FWHM est.", "Prominencia"])
        self.table_peaks.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_peaks.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_peaks.itemClicked.connect(self._on_peak_table_clicked)
        pk_vlo.addWidget(self.table_peaks)

        # Sección de Ajuste Espectral
        fit_box = QGroupBox("Ajuste y Deconvolución Espectral")
        fit_flo = QFormLayout(fit_box)

        self.combo_fit_model = QComboBox()
        self.combo_fit_model.addItems(["Pseudo-Voigt (Recomendado)", "Lorentziano Puro", "Gaussiano Puro"])
        fit_flo.addRow("Modelo:", self.combo_fit_model)

        fit_btn_row = QHBoxLayout()
        self.btn_fit_peak = QPushButton("Ajustar Pico en Cursor A")
        self.btn_fit_peak.setStyleSheet("background-color: #CBA6F7; color: #11111B; font-weight: bold;")
        self.btn_fit_peak.clicked.connect(self._on_fit_selected_peak)
        fit_btn_row.addWidget(self.btn_fit_peak)

        self.btn_fit_multi = QPushButton("Ajustar Región A-B (Multi-Pico)")
        self.btn_fit_multi.setStyleSheet("background-color: #FAB387; color: #11111B; font-weight: bold;")
        self.btn_fit_multi.setToolTip("Ajusta simultáneamente todos los picos detectados entre los cursores A y B para deconvolucionar bandas solapadas")
        self.btn_fit_multi.clicked.connect(self._on_fit_multi_region)
        fit_btn_row.addWidget(self.btn_fit_multi)
        fit_flo.addRow(fit_btn_row)

        self.lbl_fit_results = QLabel("Sin ajuste activo")
        self.lbl_fit_results.setStyleSheet("font-family: monospace; font-size: 8pt; color: #A6E3A1;")
        self.lbl_fit_results.setWordWrap(True)
        fit_flo.addRow(self.lbl_fit_results)

        pk_vlo.addWidget(fit_box)
        self.tabs.addTab(tab_peaks, "📍 Picos & Ajuste")

        # Tab: Metrología Dual & Termometría
        tab_metrics = QWidget()
        met_vlo = QVBoxLayout(tab_metrics)
        met_vlo.setContentsMargins(8, 8, 8, 8)
        met_vlo.setSpacing(6)

        self.check_cursor_b = QCheckBox("Mostrar Regla B (Metrología Dual)")
        self.check_cursor_b.setChecked(True)
        self.check_cursor_b.toggled.connect(self._on_toggle_cursor_b)
        met_vlo.addWidget(self.check_cursor_b)

        # Tabla de métricas duales
        self.lbl_metrics_dual = QLabel("Métricas entre Regla A y Regla B")
        self.lbl_metrics_dual.setStyleSheet("""
            background-color: #11111B;
            border: 1px solid #313244;
            border-radius: 6px;
            padding: 8px;
            font-family: monospace;
            font-size: 8.5pt;
            color: #CDD6F4;
        """)
        self.lbl_metrics_dual.setWordWrap(True)
        met_vlo.addWidget(self.lbl_metrics_dual)

        # Termometría Anti-Stokes / Stokes
        thermo_box = QGroupBox("🌡️ Termometría Fototérmica In-situ")
        th_flo = QFormLayout(thermo_box)

        self.spin_vib_shift = QDoubleSpinBox()
        self.spin_vib_shift.setRange(10.0, 4000.0)
        self.spin_vib_shift.setValue(520.7)
        self.spin_vib_shift.setSuffix(" cm⁻¹")
        th_flo.addRow("Modo vibracional ν:", self.spin_vib_shift)

        btn_calc_temp = QPushButton("Calcular T Fototérmica (A=Stokes, B=AntiStokes)")
        btn_calc_temp.clicked.connect(self._on_calculate_temperature)
        th_flo.addRow(btn_calc_temp)

        self.lbl_temp_result = QLabel("T = — K (— °C)")
        self.lbl_temp_result.setStyleSheet("font-weight: bold; color: #FAB387; font-size: 9.5pt;")
        th_flo.addRow("Temperatura Local:", self.lbl_temp_result)

        met_vlo.addWidget(thermo_box)
        met_vlo.addStretch()

        self.tabs.addTab(tab_metrics, "📏 Metrología")

        # Tab: Marcadores SERS & Exportación
        tab_export = QWidget()
        exp_vlo = QVBoxLayout(tab_export)
        exp_vlo.setContentsMargins(8, 8, 8, 8)
        exp_vlo.setSpacing(8)

        ref_box = QGroupBox("Estándares y Marcadores SERS")
        ref_vlo = QVBoxLayout(ref_box)
        self.ref_checkboxes: Dict[str, QCheckBox] = {}
        for name, data in RAMAN_REFERENCE_STANDARDS.items():
            cb = QCheckBox(name)
            cb.setToolTip(str(data["desc"]))
            cb.toggled.connect(self._update_plots)
            ref_vlo.addWidget(cb)
            self.ref_checkboxes[name] = cb
        exp_vlo.addWidget(ref_box)

        exp_box = QGroupBox("Exportación de Datos y Gráficos")
        exp_flo = QVBoxLayout(exp_box)

        self.btn_export_csv = QPushButton("💾 Exportar Espectro Limpio (.CSV)")
        self.btn_export_csv.setStyleSheet("background-color: #A6E3A1; color: #11111B; font-weight: bold;")
        self.btn_export_csv.clicked.connect(self._on_export_csv)
        exp_flo.addWidget(self.btn_export_csv)

        self.btn_export_png = QPushButton("📊 Exportar Figura de Alta Resolución (600 DPI)")
        self.btn_export_png.clicked.connect(self._on_export_png)
        exp_flo.addWidget(self.btn_export_png)

        exp_vlo.addWidget(exp_box)
        exp_vlo.addStretch()

        self.tabs.addTab(tab_export, "🏷️ SERS & Export")

        # Tab: Metadatos Andor Solis
        tab_meta = QWidget()
        meta_vlo = QVBoxLayout(tab_meta)
        self.table_metadata = QTableWidget(0, 2)
        self.table_metadata.setHorizontalHeaderLabels(["Propiedad Solis", "Valor"])
        self.table_metadata.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        meta_vlo.addWidget(self.table_metadata)
        self.tabs.addTab(tab_meta, "ℹ️ Metadatos")

        controls_vlo.addWidget(self.tabs)

        controls_scroll.setWidget(controls_content)
        splitter.addWidget(controls_scroll)

        # ── Área Gráfica (Derecha) ────────────────────────────────────────────
        plots_container = QWidget()
        plots_vlo = QVBoxLayout(plots_container)
        plots_vlo.setContentsMargins(0, 0, 0, 0)
        plots_vlo.setSpacing(4)

        # Layout gráfico con dos gráficos sincronizados
        self.plot_layout = pg.GraphicsLayoutWidget()
        plots_vlo.addWidget(self.plot_layout)

        splitter.addWidget(plots_container)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        single_layout.addWidget(splitter)
        self.main_nav_tabs.addTab(self.tab_single, "🔬 Espectro Individual")

        # ── Pestaña 2: Multi-Espectro & Series ────────────────────────────────
        self.tab_multi = MultiSpectrumWidget(parent_analyzer=self)
        self.main_nav_tabs.addTab(self.tab_multi, "📚 Multi-Espectro & Series")

    def _setup_plots(self):
        # Gráfico Superior: Crudo + Línea Base
        self.plot_top = self.plot_layout.addPlot(row=0, col=0)
        self.plot_top.setTitle("<b style='color:#89B4FA; font-size:11pt;'>Espectro Original & Estimación de Línea Base</b>")
        self.plot_top.showGrid(x=True, y=True, alpha=0.25)
        self.plot_top.setLabel("left", "Intensidad (Cuentas)")
        self.plot_top.addLegend(offset=(-10, 10))

        self.curve_raw = self.plot_top.plot(pen=pg.mkPen("#89B4FA", width=1.5), name="Espectro (Crudo)")
        self.curve_baseline = self.plot_top.plot(pen=pg.mkPen("#FAB387", width=2.0, style=Qt.PenStyle.DashLine), name="Línea Base")
        self.scatter_spikes = pg.ScatterPlotItem(size=10, pen=pg.mkPen("#F38BA8", width=1.5), symbol="x")
        self.plot_top.addItem(self.scatter_spikes)

        # Gráfico Inferior: Corregido + Picos + Ajuste
        self.plot_layout.nextRow()
        self.plot_bottom = self.plot_layout.addPlot(row=1, col=0)
        self.plot_bottom.setTitle("<b style='color:#A6E3A1; font-size:11pt;'>Espectro Raman Corregido & Identificación de Bandas</b>")
        self.plot_bottom.showGrid(x=True, y=True, alpha=0.25)
        self.plot_bottom.setLabel("left", "Intensidad Neta (Cuentas)")
        self.plot_bottom.setLabel("bottom", "Corrimiento Raman (cm⁻¹)")
        self.plot_bottom.addLegend(offset=(-10, 10))

        self.curve_corrected = self.plot_bottom.plot(pen=pg.mkPen("#A6E3A1", width=1.8), name="Raman Neto")
        self.curve_fit = self.plot_bottom.plot(pen=pg.mkPen("#F38BA8", width=2.2), name="Ajuste Voigt/Lorentz")
        self.scatter_peaks = pg.ScatterPlotItem(size=11, brush=pg.mkBrush("#F5C2E7"), pen=pg.mkPen("#11111B", width=1.0), symbol="d")
        self.plot_bottom.addItem(self.scatter_peaks)

        # Enlazar ejes X para zoom y paneo sincronizados
        self.plot_top.setXLink(self.plot_bottom)

    def _setup_cursors(self):
        # Regla Vertical A (Cursor Principal)
        self.cursor_a = pg.InfiniteLine(pos=520.0, angle=90, movable=True, pen=pg.mkPen("#F38BA8", width=2.0, style=Qt.PenStyle.SolidLine))
        self.cursor_a.sigPositionChanged.connect(self._on_cursors_moved)
        self.plot_bottom.addItem(self.cursor_a)

        # Regla Vertical B (Cursor Secundario)
        self.cursor_b = pg.InfiniteLine(pos=1078.0, angle=90, movable=True, pen=pg.mkPen("#F9E2AF", width=2.0, style=Qt.PenStyle.DashLine))
        self.cursor_b.sigPositionChanged.connect(self._on_cursors_moved)
        self.plot_bottom.addItem(self.cursor_b)

        # Región lineal sombreada entre A y B para visualización de integración
        self.linear_region = pg.LinearRegionItem(values=[520.0, 1078.0], brush=pg.mkBrush(137, 180, 250, 40), movable=False)
        self.plot_bottom.addItem(self.linear_region)

        # Líneas de referencia para estándares SERS
        self.reference_lines: List[pg.InfiniteLine] = []

    # ── Gestión de Archivos ───────────────────────────────────────────────────

    def _on_browse_file(self):
        start_dir = str(Path.home() / "Documents")
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Abrir Espectro de Andor Solis", start_dir,
            "Archivos Espectroscópicos (*.asc *.txt *.csv *.dat);;Todos (*.*)"
        )
        if file_path:
            self.load_spectrum_file(file_path)

    def _on_load_demo(self):
        demo_file = Path(__file__).resolve().parent.parent / "reserva" / "90%_in_red_10s_3_em.asc"
        if demo_file.exists():
            self.load_spectrum_file(demo_file)
        else:
            QMessageBox.warning(self, "Archivo no encontrado", f"No se encontró el archivo demo en:\n{demo_file}")

    def load_spectrum_file(self, filepath: Union[str, Path]):
        try:
            filepath = Path(filepath)
            metadata, wls, counts = parse_andor_solis_file(filepath)

            self.filepath = filepath
            self.metadata = metadata
            self.raw_wls = wls
            self.raw_counts = counts
            self.cropped_wls = wls.copy()
            self.cropped_raw_counts = counts.copy()
            self.crop_mask = np.ones(len(wls), dtype=bool)
            self.active_counts = counts.copy()
            self.corrected = counts.copy()
            self.baseline = np.zeros_like(counts)
            self.spike_mask = np.zeros(len(counts), dtype=bool)
            self.manual_anchor_indices = []
            self.fitted_curve_x = None
            self.fitted_curve_y = None
            self.multi_fit_subpeaks = []

            # Auto-detección de longitud de onda del láser si está en la cabecera
            for k in ("Laser Wavelength", "Laser Wavelength (nm)", "Excitation (nm)", "Laser", "Excitation Wavelength"):
                if k in metadata:
                    try:
                        val = float(metadata[k].replace(",", "."))
                        if 300.0 <= val <= 1500.0:
                            self.spin_laser_custom.setValue(val)
                            if math.isclose(val, 532.0, abs_tol=1.0):
                                self.combo_laser.setCurrentIndex(0)
                            elif math.isclose(val, 637.0, abs_tol=1.0):
                                self.combo_laser.setCurrentIndex(2)
                            break
                    except ValueError:
                        pass

            # Actualizar tabla de metadatos
            self.table_metadata.setRowCount(len(metadata))
            for r, (k, v) in enumerate(metadata.items()):
                item_k = QTableWidgetItem(k)
                item_v = QTableWidgetItem(v)
                self.table_metadata.setItem(r, 0, item_k)
                self.table_metadata.setItem(r, 1, item_v)

            exp_time = metadata.get("Exposure Time (secs)", "N/A")
            accum = metadata.get("Number of Accumulations", "1")
            temp = metadata.get("Temperature (C)", "N/A")
            self.lbl_file_info.setText(
                f"📄 <b>{filepath.name}</b><br>"
                f"Puntos: {len(wls)} | Rango: {wls.min():.1f} – {wls.max():.1f} nm<br>"
                f"Exposición: {exp_time} s | Acum: {accum} | Temp CCD: {temp} °C"
            )

            self.lbl_cosmic_status.setText("Rayos cósmicos: sin procesar")

            # Resetear estado de recorte para el nuevo archivo
            self.check_enable_crop_x.blockSignals(True)
            self.check_enable_crop_x.setChecked(False)
            self.check_enable_crop_x.blockSignals(False)
            self.spin_trim_left.blockSignals(True)
            self.spin_trim_left.setValue(0)
            self.spin_trim_left.blockSignals(False)
            self.spin_trim_right.blockSignals(True)
            self.spin_trim_right.setValue(0)
            self.spin_trim_right.blockSignals(False)

            # Inicializar spinboxes de recorte con el rango completo
            x_full = self._get_full_x()
            if len(x_full) > 0:
                self.spin_crop_xmin.blockSignals(True)
                self.spin_crop_xmax.blockSignals(True)
                self.spin_crop_xmin.setValue(float(np.min(x_full)))
                self.spin_crop_xmax.setValue(float(np.max(x_full)))
                self.spin_crop_xmin.blockSignals(False)
                self.spin_crop_xmax.blockSignals(False)

            # Posicionar cursores en rango útil bloqueando señales transitorias
            x_vals = self._get_current_x()
            if len(x_vals) > 1:
                mid = float(x_vals[len(x_vals) // 2])
                q1 = float(x_vals[len(x_vals) // 4])
                self.cursor_a.blockSignals(True)
                self.cursor_b.blockSignals(True)
                self.cursor_a.setValue(q1)
                self.cursor_b.setValue(mid)
                self.cursor_a.blockSignals(False)
                self.cursor_b.blockSignals(False)

            self._recalculate_all()

        except Exception as e:
            QMessageBox.critical(self, "Error al cargar archivo", f"No se pudo parsear el espectro:\n{e}")

    # ── Conversión de Coordenadas y Cálculos ───────────────────────────────────

    def _get_current_x(self) -> np.ndarray:
        """Devuelve el vector X activo sobre los datos RECORTADOS según la unidad elegida."""
        if len(self.cropped_wls) == 0:
            return np.array([])

        if self.unit_mode == "raman_shift":
            return wavelength_to_raman_shift(self.cropped_wls, self.laser_nm)
        elif self.unit_mode == "energy":
            shifts = wavelength_to_raman_shift(self.cropped_wls, self.laser_nm)
            return raman_shift_to_ev(shifts)
        else:  # 'wavelength'
            return self.cropped_wls.copy()

    def _get_full_x(self) -> np.ndarray:
        """Devuelve el vector X original COMPLETO sin recortar según la unidad elegida."""
        if len(self.raw_wls) == 0:
            return np.array([])

        if self.unit_mode == "raman_shift":
            return wavelength_to_raman_shift(self.raw_wls, self.laser_nm)
        elif self.unit_mode == "energy":
            shifts = wavelength_to_raman_shift(self.raw_wls, self.laser_nm)
            return raman_shift_to_ev(shifts)
        else:
            return self.raw_wls.copy()

    def _on_laser_combo_changed(self, idx: int):
        lasers = [532.0, 632.8, 637.0, 785.0]
        if idx < len(lasers):
            self.laser_nm = lasers[idx]
            self.spin_laser_custom.setEnabled(False)
            self.spin_laser_custom.setValue(self.laser_nm)
        else:
            self.spin_laser_custom.setEnabled(True)
            self.laser_nm = self.spin_laser_custom.value()
        self._recalculate_all()

    def _on_laser_value_changed(self, val: float):
        if self.combo_laser.currentIndex() == 4:  # Personalizado
            self.laser_nm = val
            self._recalculate_all()

    def _on_units_changed(self, idx: int):
        modes = ["raman_shift", "wavelength", "energy"]
        labels = ["Corrimiento Raman (cm⁻¹)", "Longitud de Onda (nm)", "Energía Relativa (eV)"]
        self.unit_mode = modes[idx]
        self.plot_bottom.setLabel("bottom", labels[idx])

        # Actualizar sufijos en spinboxes
        suf = " cm⁻¹" if self.unit_mode == "raman_shift" else (" nm" if self.unit_mode == "wavelength" else " eV")
        self.spin_peak_min_width.setSuffix(suf)
        self.spin_peak_max_width.setSuffix(suf)

        self._recalculate_all()

    # ── Pipeline de Procesamiento (Recorte + Spikes + Línea Base + Filtros) ────

    def _recalculate_all(self):
        if len(self.raw_counts) == 0:
            return

        # Paso 0: Pre-procesado de Recorte de Bordes (ROI)
        x_full = self._get_full_x()
        crop_xmin = self.spin_crop_xmin.value() if self.check_enable_crop_x.isChecked() else None
        crop_xmax = self.spin_crop_xmax.value() if self.check_enable_crop_x.isChecked() else None
        trim_l = self.spin_trim_left.value()
        trim_r = self.spin_trim_right.value()

        _, self.cropped_raw_counts, self.crop_mask = crop_spectrum(
            x_full,
            self.raw_counts,
            x_min=crop_xmin,
            x_max=crop_xmax,
            trim_left_pts=trim_l,
            trim_right_pts=trim_r
        )
        self.cropped_wls = self.raw_wls[self.crop_mask]

        n_act = len(self.cropped_raw_counts)
        n_tot = len(self.raw_counts)
        pct = (n_act / n_tot * 100.0) if n_tot > 0 else 0.0
        self.lbl_crop_status.setText(f"Puntos activos: <b>{n_act}</b> / {n_tot} ({pct:.1f}%)")

        # Paso 1: Rayos cósmicos (despiking) proyectados sobre el array recortado
        y_working = self.cropped_raw_counts.copy()
        if len(self.spike_mask) == len(self.raw_counts) and np.any(self.spike_mask):
            active_spikes = self.spike_mask[self.crop_mask]
            if np.any(active_spikes):
                from scipy.signal import medfilt
                y_med = medfilt(y_working, kernel_size=5)
                y_working[active_spikes] = y_med[active_spikes]
        self.active_counts = y_working.copy()

        # Paso 2: Suavizado si está activo
        if self.check_enable_smooth.isChecked():
            mode = self.combo_smooth_mode.currentIndex()
            try:
                if mode == 0:  # Savitzky-Golay
                    y_working = smooth_savgol(y_working, self.spin_sg_window.value(), self.spin_sg_order.value())
                elif mode == 1:  # Fourier Lowpass
                    y_working = smooth_fourier(y_working, self.spin_fft_cutoff.value(), "lowpass")
                elif mode == 2:  # Fourier Highpass
                    y_working = smooth_fourier(y_working, self.spin_fft_cutoff.value(), "highpass")
                elif mode == 3:  # Fourier Notch 50 Hz
                    y_working = smooth_fourier(y_working, filter_type="notch50")
                elif mode == 4:  # Whittaker
                    y_working = smooth_whittaker(y_working, lam=1e3)
                elif mode == 5:  # Gaussiano
                    y_working = smooth_gaussian(y_working, self.spin_gauss_sigma.value())
            except Exception as e:
                print(f"[RamanAnalyzer Warning] Error en suavizado: {e}")

        # Paso 3: Corrección de Línea Base sobre el espectro recortado
        if self.check_enable_baseline.isChecked():
            b_mode = self.combo_baseline_mode.currentIndex()
            try:
                if b_mode == 0:  # AsLS
                    self.baseline = baseline_asls(
                        y_working,
                        lam=self.spin_bl_lambda.value(),
                        p=self.spin_bl_p.value()
                    )
                elif b_mode == 1:  # AirPLS
                    self.baseline = baseline_airpls(
                        y_working,
                        lam=self.spin_bl_lambda.value()
                    )
                elif b_mode == 2:  # ModPoly
                    self.baseline = baseline_modpoly(
                        y_working,
                        poly_order=self.spin_bl_poly_order.value()
                    )
                elif b_mode == 3:  # Tercera Derivada
                    self.baseline = baseline_derivative(y_working)
                elif b_mode == 4:  # Morfológico Rolling Ball
                    self.baseline = baseline_rolling_ball(
                        y_working,
                        radius=self.spin_bl_rolling_radius.value()
                    )
                elif b_mode == 5:  # Splines manuales
                    self.baseline = baseline_spline_anchors(y_working, self.manual_anchor_indices)
            except Exception as e:
                print(f"[RamanAnalyzer Warning] Error en cálculo de línea base: {e}")
                self.baseline = np.zeros_like(y_working)
        else:
            self.baseline = np.zeros_like(y_working)

        # Espectro corregido neto
        self.corrected = y_working - self.baseline

        # Paso 4: Búsqueda y actualización de picos
        self._on_find_peaks()
        self._update_plots()

    # ── Atajos y Gestión de Recorte (ROI) ─────────────────────────────────────

    def _on_crop_to_cursors(self):
        if len(self.raw_counts) == 0:
            return
        pos_a = float(self.cursor_a.value())
        pos_b = float(self.cursor_b.value())
        x_min = min(pos_a, pos_b)
        x_max = max(pos_a, pos_b)

        self.spin_crop_xmin.blockSignals(True)
        self.spin_crop_xmax.blockSignals(True)
        self.spin_crop_xmin.setValue(x_min)
        self.spin_crop_xmax.setValue(x_max)
        self.spin_crop_xmin.blockSignals(False)
        self.spin_crop_xmax.blockSignals(False)

        self.check_enable_crop_x.setChecked(True)
        self._recalculate_all()

    def _on_crop_rayleigh(self):
        if len(self.raw_counts) == 0:
            return
        if self.unit_mode == "raman_shift":
            self.spin_crop_xmin.setValue(150.0)
            self.check_enable_crop_x.setChecked(True)
            self._recalculate_all()
        else:
            QMessageBox.information(
                self,
                "Recorte Rayleigh",
                "El atajo de 150 cm⁻¹ está disponible cuando el eje está en Corrimiento Raman (cm⁻¹)."
            )

    def _on_reset_crop(self):
        self.check_enable_crop_x.setChecked(False)
        self.spin_trim_left.setValue(0)
        self.spin_trim_right.setValue(0)
        x_full = self._get_full_x()
        if len(x_full) > 0:
            self.spin_crop_xmin.blockSignals(True)
            self.spin_crop_xmax.blockSignals(True)
            self.spin_crop_xmin.setValue(float(np.min(x_full)))
            self.spin_crop_xmax.setValue(float(np.max(x_full)))
            self.spin_crop_xmin.blockSignals(False)
            self.spin_crop_xmax.blockSignals(False)
        self._recalculate_all()

    def _on_crop_params_changed(self):
        if self.check_enable_crop_x.isChecked():
            self._recalculate_all()

    def _on_remove_cosmic_rays(self):
        if len(self.raw_counts) == 0:
            return
        y_clean, mask = remove_cosmic_rays(self.raw_counts, threshold=5.5)
        count_spikes = int(np.sum(mask))
        self.spike_mask = mask
        self.lbl_cosmic_status.setText(f"Rayos cósmicos: {count_spikes} spikes detectados ✨")
        self._recalculate_all()

    def _on_clear_anchors(self):
        self.manual_anchor_indices = []
        self._recalculate_all()

    # ── Picos, Detección Adaptativa y Ajuste ───────────────────────────────────

    def _on_auto_prominence_toggled(self, checked: bool):
        self.spin_peak_prominence.setEnabled(not checked)
        self._on_find_peaks()

    def _on_find_peaks(self):
        if len(self.corrected) == 0:
            return
        x_vals = self._get_current_x()
        if len(x_vals) == 0 or len(x_vals) != len(self.corrected):
            return

        # Determinar prominencia: automática adaptativa o manual
        if self.check_auto_prominence.isChecked():
            diffs = np.diff(self.corrected)
            noise_sigma = 1.4826 * float(np.median(np.abs(diffs - np.median(diffs))))
            prom_val = max(4.0 * noise_sigma, 0.03 * float(np.ptp(self.corrected)))
            self.spin_peak_prominence.blockSignals(True)
            self.spin_peak_prominence.setValue(float(prom_val))
            self.spin_peak_prominence.blockSignals(False)
        else:
            prom_val = float(self.spin_peak_prominence.value())

        h_min = float(self.spin_peak_min_height.value()) if self.spin_peak_min_height.value() > 0 else None
        w_min = float(self.spin_peak_min_width.value()) if self.spin_peak_min_width.value() > 0 else None
        w_max = float(self.spin_peak_max_width.value()) if self.spin_peak_max_width.value() > 0 else None

        sort_mode = "position"
        if self.combo_sort_peaks.currentIndex() == 1:
            sort_mode = "intensity"
        elif self.combo_sort_peaks.currentIndex() == 2:
            sort_mode = "prominence"

        self.detected_peaks = detect_peaks_spectrum(
            x_vals,
            self.corrected,
            prominence=prom_val,
            distance=self.spin_peak_distance.value(),
            height=h_min,
            width_min_units=w_min,
            width_max_units=w_max,
            sort_by=sort_mode
        )

        self._refresh_peaks_table()
        self._update_plots()

    def _refresh_peaks_table(self):
        self.table_peaks.setRowCount(len(self.detected_peaks))
        for r, pk in enumerate(self.detected_peaks):
            self.table_peaks.setItem(r, 0, QTableWidgetItem(str(r + 1)))
            self.table_peaks.setItem(r, 1, QTableWidgetItem(f"{pk['position']:.2f}"))
            self.table_peaks.setItem(r, 2, QTableWidgetItem(f"{pk['intensity']:.1f}"))
            self.table_peaks.setItem(r, 3, QTableWidgetItem(f"{pk['fwhm_est']:.2f}"))
            self.table_peaks.setItem(r, 4, QTableWidgetItem(f"{pk['prominence']:.1f}"))

    def _on_peak_table_clicked(self, item: QTableWidgetItem):
        row = item.row()
        if row < len(self.detected_peaks):
            pk_pos = self.detected_peaks[row]["position"]
            self.cursor_a.setValue(pk_pos)
            self._on_cursors_moved()

    def _on_add_peak_at_cursor_a(self):
        if len(self.corrected) == 0:
            return
        x_vals = self._get_current_x()
        if len(x_vals) == 0 or len(x_vals) != len(self.corrected):
            return

        pos_a = float(self.cursor_a.value())
        idx = int(np.argmin(np.abs(x_vals - pos_a)))
        actual_pos = float(x_vals[idx])
        actual_int = float(self.corrected[idx])

        dx = abs(np.mean(np.diff(x_vals))) if len(x_vals) > 1 else 1.0
        new_peak = {
            "index": idx,
            "position": actual_pos,
            "intensity": actual_int,
            "prominence": actual_int * 0.5,
            "fwhm_est": 10.0 * dx
        }

        if not any(math.isclose(p["position"], actual_pos, abs_tol=dx * 1.5) for p in self.detected_peaks):
            self.detected_peaks.append(new_peak)

        if self.combo_sort_peaks.currentIndex() == 0:
            self.detected_peaks.sort(key=lambda item: item["position"])
        elif self.combo_sort_peaks.currentIndex() == 1:
            self.detected_peaks.sort(key=lambda item: item["intensity"], reverse=True)
        else:
            self.detected_peaks.sort(key=lambda item: item["prominence"], reverse=True)

        self._refresh_peaks_table()
        self._update_plots()

    def _on_delete_selected_peak(self):
        row = self.table_peaks.currentRow()
        if 0 <= row < len(self.detected_peaks):
            del self.detected_peaks[row]
            self._refresh_peaks_table()
            self._update_plots()

    def _on_copy_peak_table(self):
        if not self.detected_peaks:
            return
        lines = ["#\tPosicion\tCuentas\tFWHM_est\tProminencia"]
        for i, p in enumerate(self.detected_peaks):
            lines.append(f"{i+1}\t{p['position']:.2f}\t{p['intensity']:.1f}\t{p['fwhm_est']:.2f}\t{p['prominence']:.1f}")
        tsv_text = "\n".join(lines)
        QApplication.clipboard().setText(tsv_text)
        self.statusBar().showMessage("Tabla de picos copiada al portapapeles (formato TSV).", 4000)

    def _on_fit_selected_peak(self):
        if len(self.corrected) == 0:
            return
        x_vals = self._get_current_x()
        if len(x_vals) == 0 or len(x_vals) != len(self.corrected):
            return
        center_guess = float(self.cursor_a.value())

        models = ["pseudo_voigt", "lorentzian", "gaussian"]
        m_type = models[self.combo_fit_model.currentIndex()]

        fit_res = fit_peak_profile(x_vals, self.corrected, center_guess=center_guess, model_type=m_type)
        if fit_res:
            self.fitted_curve_x = fit_res["fit_x"]
            self.fitted_curve_y = fit_res["fit_y"]
            self.multi_fit_subpeaks = []
            eta_str = f" | η (Lorentz) = {fit_res['eta']:.2f}" if m_type == "pseudo_voigt" else ""
            self.lbl_fit_results.setText(
                f"Ajuste {m_type.upper()}:<br>"
                f"Centro: <b>{fit_res['center']:.2f}</b> | Amp: {fit_res['amplitude']:.1f}<br>"
                f"FWHM: <b>{fit_res['fwhm']:.2f}</b> | Área: {fit_res['area']:.1f}{eta_str}<br>"
                f"Calidad R²: <b>{fit_res['r_squared']:.4f}</b>"
            )
        else:
            self.fitted_curve_x = None
            self.fitted_curve_y = None
            self.multi_fit_subpeaks = []
            self.lbl_fit_results.setText("No convergió el ajuste en la ROI")

        self._update_plots()

    def _on_fit_multi_region(self):
        if len(self.corrected) == 0:
            return
        x_vals = self._get_current_x()
        if len(x_vals) < 10 or len(x_vals) != len(self.corrected):
            return

        pos_a = float(self.cursor_a.value())
        pos_b = float(self.cursor_b.value())
        x_left = min(pos_a, pos_b)
        x_right = max(pos_a, pos_b)

        # Buscar picos detectados dentro de la región A-B
        peaks_in_roi = [p["position"] for p in self.detected_peaks if x_left <= p["position"] <= x_right]
        if len(peaks_in_roi) == 0:
            peaks_in_roi = [(x_left + x_right) / 2.0]

        mask = (x_vals >= x_left) & (x_vals <= x_right)
        x_roi = x_vals[mask]
        y_roi = self.corrected[mask]

        if len(x_roi) < len(peaks_in_roi) * 3:
            self.lbl_fit_results.setText("La región entre reglas A y B contiene muy pocos puntos.")
            return

        models = ["pseudo_voigt", "lorentzian", "gaussian"]
        m_type = models[self.combo_fit_model.currentIndex()]

        fit_res = fit_multi_peak_profile(x_roi, y_roi, peak_centers=peaks_in_roi, model_type=m_type)
        if fit_res:
            self.fitted_curve_x = fit_res["fit_x"]
            self.fitted_curve_y = fit_res["fit_y"]
            self.multi_fit_subpeaks = fit_res["peaks"]

            txt_lines = [
                f"<b>Ajuste Multi-Pico ({len(fit_res['peaks'])} bandas) [{m_type.upper()}]:</b>",
                f"Calidad R²: <b>{fit_res['r_squared']:.4f}</b>"
            ]
            for idx_pk, spk in enumerate(fit_res["peaks"]):
                txt_lines.append(
                    f"Banda #{idx_pk+1}: Centro=<b>{spk['center']:.1f}</b> | "
                    f"FWHM=<b>{spk['fwhm']:.1f}</b> | Área=<b>{spk['area']:.0f}</b>"
                )
            self.lbl_fit_results.setText("<br>".join(txt_lines))
        else:
            self.fitted_curve_x = None
            self.fitted_curve_y = None
            self.multi_fit_subpeaks = []
            self.lbl_fit_results.setText("No convergió la deconvolución multi-pico.")

        self._update_plots()

    # ── Metrología y Termometría ──────────────────────────────────────────────

    def _on_toggle_cursor_b(self, visible: bool):
        self.cursor_b.setVisible(visible)
        self.linear_region.setVisible(visible)
        self._on_cursors_moved()

    def _on_cursors_moved(self):
        if len(self.corrected) == 0:
            return
        x_vals = self._get_current_x()
        if len(x_vals) == 0 or len(x_vals) != len(self.corrected):
            return

        pos_a = float(self.cursor_a.value())
        pos_b = float(self.cursor_b.value())

        # Actualizar región lineal sombreada
        self.linear_region.setRegion([min(pos_a, pos_b), max(pos_a, pos_b)])

        metrics = compute_dual_cursor_metrics(x_vals, self.corrected, pos_a, pos_b)

        unit_str = "cm⁻¹" if self.unit_mode == "raman_shift" else ("nm" if self.unit_mode == "wavelength" else "eV")

        self.lbl_metrics_dual.setText(
            f"<b>Regla A:</b> {metrics['pos_a']:.2f} {unit_str} | Y = {metrics['val_a']:.1f} cts<br>"
            f"<b>Regla B:</b> {metrics['pos_b']:.2f} {unit_str} | Y = {metrics['val_b']:.1f} cts<br>"
            f"<b>ΔX:</b> {metrics['delta_x']:.2f} {unit_str}<br>"
            f"<b>ΔY:</b> {metrics['delta_y']:+.1f} cts<br>"
            f"<b>Cociente I_B / I_A:</b> {metrics['ratio_ba']:.3f}<br>"
            f"<b>Área Integrada (A-B):</b> {metrics['integrated_area']:.2e}"
        )

    def _on_calculate_temperature(self):
        if len(self.corrected) == 0:
            return
        x_vals = self._get_current_x()
        if len(x_vals) == 0 or len(x_vals) != len(self.corrected):
            return
        pos_a = float(self.cursor_a.value())
        pos_b = float(self.cursor_b.value())

        if len(x_vals) > 1 and x_vals[0] > x_vals[-1]:
            x_interp = x_vals[::-1]
            y_interp = self.corrected[::-1]
        else:
            x_interp = x_vals
            y_interp = self.corrected

        y_a = float(np.interp(pos_a, x_interp, y_interp))
        y_b = float(np.interp(pos_b, x_interp, y_interp))

        vib_shift = self.spin_vib_shift.value()

        t_k, t_c = calculate_photothermal_temperature(
            shift_cm1=vib_shift,
            intensity_stokes=y_a,
            intensity_anti_stokes=y_b,
            laser_nm=self.laser_nm
        )

        if not math.isnan(t_k):
            self.lbl_temp_result.setText(f"T = <b>{t_k:.1f} K</b> ({t_c:.1f} °C)")
        else:
            self.lbl_temp_result.setText("T = Indeterminado (verificar I_AS < I_S)")

    # ── Actualización de Gráficos ─────────────────────────────────────────────

    def _update_plots(self):
        if len(self.raw_counts) == 0:
            return

        x_vals = self._get_current_x()
        if len(x_vals) == 0:
            return

        # Actualizar curvas superiores (Crudo y Línea base)
        self.curve_raw.setData(x_vals, self.active_counts)
        if len(self.baseline) == len(x_vals):
            self.curve_baseline.setData(x_vals, self.baseline)

        # Spikes sobre los datos recortados
        if len(self.spike_mask) == len(self.raw_counts) and np.any(self.spike_mask):
            act_spikes = self.spike_mask[self.crop_mask]
            if np.any(act_spikes):
                self.scatter_spikes.setData(x=x_vals[act_spikes], y=self.cropped_raw_counts[act_spikes])
            else:
                self.scatter_spikes.clear()
        else:
            self.scatter_spikes.clear()

        # Actualizar curva inferior (Raman neto)
        if len(self.corrected) == len(x_vals):
            self.curve_corrected.setData(x_vals, self.corrected)

        # Limpiar etiquetas numéricas anteriores
        for lbl in self.peak_labels:
            self.plot_bottom.removeItem(lbl)
        self.peak_labels.clear()

        # Limpiar curvas de sub-picos de ajustes multi-pico previos
        for c in self.multi_fit_curves:
            self.plot_bottom.removeItem(c)
        self.multi_fit_curves.clear()

        # Picos y etiquetas de texto
        if self.detected_peaks:
            pk_x = [p["position"] for p in self.detected_peaks]
            pk_y = [p["intensity"] for p in self.detected_peaks]
            self.scatter_peaks.setData(x=pk_x, y=pk_y)

            if self.check_show_peak_labels.isChecked():
                for p in self.detected_peaks:
                    txt = pg.TextItem(
                        text=f"{p['position']:.1f}",
                        color="#F5C2E7",
                        anchor=(0.5, 1.2)
                    )
                    txt.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
                    txt.setPos(p["position"], p["intensity"])
                    self.plot_bottom.addItem(txt)
                    self.peak_labels.append(txt)
        else:
            self.scatter_peaks.clear()

        # Ajuste Total Voigt/Lorentz/Gaussiano
        if self.fitted_curve_x is not None and len(self.fitted_curve_x) > 0:
            self.curve_fit.setData(self.fitted_curve_x, self.fitted_curve_y)
            self.curve_fit.setVisible(True)

            # Si es un ajuste multi-pico, graficar cada banda individual punteada
            if self.multi_fit_subpeaks:
                m_type = ["pseudo_voigt", "lorentzian", "gaussian"][self.combo_fit_model.currentIndex()]
                x_eval = self.fitted_curve_x
                sub_colors = ["#F38BA8", "#FAB387", "#F9E2AF", "#A6E3A1", "#89DCEB", "#CBA6F7"]
                for i_spk, spk in enumerate(self.multi_fit_subpeaks):
                    c_col = sub_colors[i_spk % len(sub_colors)]
                    if m_type == "gaussian":
                        y_sub = model_gaussian(x_eval, spk["amplitude"], spk["center"], spk["fwhm"])
                    elif m_type == "lorentzian":
                        y_sub = model_lorentzian(x_eval, spk["amplitude"], spk["center"], spk["fwhm"])
                    else:
                        y_sub = model_pseudo_voigt(x_eval, spk["amplitude"], spk["center"], spk["fwhm"], spk.get("eta", 0.5))

                    c_item = self.plot_bottom.plot(
                        x_eval, y_sub,
                        pen=pg.mkPen(c_col, width=1.5, style=Qt.PenStyle.DashLine)
                    )
                    self.multi_fit_curves.append(c_item)
        else:
            self.curve_fit.clear()
            self.curve_fit.setVisible(False)

        # Inversión de eje X si corresponde
        invert = self.check_flip_x.isChecked()
        self.plot_top.getViewBox().invertX(invert)
        self.plot_bottom.getViewBox().invertX(invert)

        # Superposición de marcadores SERS
        self._update_reference_lines()

        self._on_cursors_moved()

    def _update_reference_lines(self):
        for line in self.reference_lines:
            self.plot_bottom.removeItem(line)
        self.reference_lines.clear()

        if self.unit_mode != "raman_shift":
            return

        for name, cb in self.ref_checkboxes.items():
            if cb.isChecked():
                ref_info = RAMAN_REFERENCE_STANDARDS[name]
                color = str(ref_info["color"])
                for p_pos in ref_info["peaks"]:
                    line = pg.InfiniteLine(
                        pos=p_pos,
                        angle=90,
                        movable=False,
                        pen=pg.mkPen(color, width=1.2, style=Qt.PenStyle.DashLine),
                        label=f"{name[:8]}: {p_pos:.0f}",
                        labelOpts={"position": 0.95, "color": color}
                    )
                    self.plot_bottom.addItem(line)
                    self.reference_lines.append(line)

    # ── Exportación ───────────────────────────────────────────────────────────

    def _on_export_csv(self):
        if len(self.cropped_wls) == 0:
            QMessageBox.warning(self, "Sin datos", "No hay datos espectroscópicos para exportar.")
            return

        default_name = f"Processed_{self.filepath.stem if self.filepath else 'spectrum'}.csv"
        out_path, _ = QFileDialog.getSaveFileName(
            self, "Exportar Datos Procesados", default_name, "Archivos CSV (*.csv);;Archivos de Texto (*.txt)"
        )
        if not out_path:
            return

        try:
            x_shifts = wavelength_to_raman_shift(self.cropped_wls, self.laser_nm)
            base_col = self.baseline if len(self.baseline) == len(self.cropped_wls) else np.zeros_like(self.cropped_wls)
            corr_col = self.corrected if len(self.corrected) == len(self.cropped_wls) else self.cropped_raw_counts

            data_matrix = np.column_stack((
                self.cropped_wls,
                x_shifts,
                self.cropped_raw_counts,
                self.active_counts,
                base_col,
                corr_col
            ))

            header = (
                f"# RamanAnalyzer 3.0 — Exportación Cuantitativa\n"
                f"# Archivo Origen: {self.filepath.name if self.filepath else 'Manual'}\n"
                f"# Láser de Excitación: {self.laser_nm} nm\n"
                f"Wavelength_nm,Raman_Shift_cm-1,Raw_Counts,Denoised_Counts,Baseline,Corrected_Counts"
            )

            np.savetxt(out_path, data_matrix, delimiter=",", header=header, comments="", fmt="%.5f,%.4f,%.2f,%.2f,%.2f,%.2f")
            QMessageBox.information(self, "Exportación Exitosa", f"Datos exportados correctamente en:\n{out_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error de Exportación", f"No se pudo guardar el archivo:\n{e}")

    def _on_export_png(self):
        if len(self.raw_wls) == 0:
            QMessageBox.warning(self, "Sin datos", "No hay gráficos para exportar.")
            return

        default_name = f"Figure_{self.filepath.stem if self.filepath else 'spectrum'}.png"
        out_path, _ = QFileDialog.getSaveFileName(
            self, "Exportar Figura de Alta Resolución", default_name, "Imagen PNG (*.png);;Gráficos Vectoriales (*.svg)"
        )
        if not out_path:
            return

        try:
            import pyqtgraph.exporters
            exporter = pg.exporters.ImageExporter(self.plot_layout.scene())
            # 600 DPI escalando el ancho a ~2400 px
            exporter.parameters()["width"] = 2400
            exporter.export(out_path)
            QMessageBox.information(self, "Figura Exportada", f"Figura científica guardada con éxito en:\n{out_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error de Exportación", f"No se pudo exportar la imagen:\n{e}")


# ══════════════════════════════════════════════════════════════════════════════
#  PUNTO DE ENTRADA PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

def main():
    app = QApplication(sys.argv)
    win = RamanAnalyzerWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
