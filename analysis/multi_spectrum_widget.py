# -*- coding: utf-8 -*-
"""
multi_spectrum_widget.py — Suite de Análisis Multi-Espectro, Series Temporales y Lotes SERS
PyPrinting 3.0 — UNSAM Nanofotónica

Permite:
  - Carga masiva de espectros Andor Solis (.asc, .txt, .csv) y remuestreo a grilla común
  - Línea base compartida (AsLS, AirPLS, ModPoly, Rolling Ball) o sustracción de blanco/sustrato
  - Filtros en lote (Savitzky-Golay) y limpieza de rayos cósmicos
  - Normalizaciones: a máximo, a pico de referencia seleccionado, por área unitaria o SNV
  - Modos de visualización: Superposición (Overlay), Cascada (Waterfall interactivo) y Mapa de calor 2D
  - Análisis estadístico: Espectro promedio ± desviación estándar con reporte de reproducibilidad RSD%
  - Cinética y seguimiento temporal de bandas espectrales
  - Descomposición en Componentes Principales (PCA con SVD)
"""
import os
import math
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Union

import numpy as np
import pyqtgraph as pg
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QSpinBox, QDoubleSpinBox, QSlider, QCheckBox, QTabWidget, QTableWidget,
    QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox, QSplitter,
    QGroupBox, QFormLayout, QScrollArea, QFrame, QColorDialog, QApplication
)
from PyQt6.QtGui import QFont, QColor, QPen

from core.raman_engine import (
    parse_andor_solis_file,
    wavelength_to_raman_shift,
    crop_spectrum,
    baseline_asls,
    baseline_airpls,
    baseline_modpoly,
    baseline_rolling_ball,
    smooth_savgol,
    remove_cosmic_rays,
    interpolate_spectra_to_common_grid,
    normalize_spectrum_matrix,
    compute_mean_std_spectrum,
    extract_band_kinetics,
    compute_spectral_pca
)


def generate_spectrum_palette(n: int, cmap_name: str = "viridis") -> List[QColor]:
    """Genera una lista de N colores armoniosos según el colormap solicitado."""
    if n <= 0:
        return []
    try:
        import matplotlib as mpl
        import matplotlib.cm as cm
        cmap = mpl.colormaps[cmap_name] if hasattr(mpl, "colormaps") else cm.get_cmap(cmap_name)
        colors = []
        for i in range(n):
            val = i / max(1, n - 1) if n > 1 else 0.5
            rgba = cmap(val)
            colors.append(QColor(int(rgba[0] * 255), int(rgba[1] * 255), int(rgba[2] * 255)))
        return colors
    except Exception:
        # Paleta de degradé cian a magenta (Catppuccin Mocha)
        colors = []
        for i in range(n):
            t = i / max(1, n - 1) if n > 1 else 0.5
            r = int(137 + t * (243 - 137))
            g = int(180 - t * 40)
            b = int(250 - t * 80)
            colors.append(QColor(r, g, b))
        return colors


class MultiSpectrumWidget(QWidget):
    """Widget de Análisis de Múltiples Espectros, Series y Lotes SERS."""

    def __init__(self, parent_analyzer=None, parent=None):
        super().__init__(parent)
        self.parent_analyzer = parent_analyzer

        # Colección de espectros cargados
        # Cada item: {"name": str, "filepath": Path, "wls": np.ndarray, "raw_counts": np.ndarray,
        #             "counts": np.ndarray, "color": QColor, "visible": bool, "metadata": dict}
        self.spectra_list: List[Dict[str, Any]] = []

        # Matrices remuestreadas a grilla común
        self.common_x: np.ndarray = np.array([])
        self.Y_raw: np.ndarray = np.empty((0, 0))
        self.Y_corrected: np.ndarray = np.empty((0, 0))
        self.Y_displayed: np.ndarray = np.empty((0, 0))
        self.active_indices: List[int] = []

        # Parámetros espectrales
        self.laser_nm: float = 532.0
        if self.parent_analyzer and hasattr(self.parent_analyzer, "laser_nm"):
            self.laser_nm = float(self.parent_analyzer.laser_nm)
        self.view_mode: str = "overlay"  # 'overlay', 'waterfall', 'heatmap'
        self.norm_mode: str = "none"     # 'none', 'max', 'peak', 'area', 'snv'
        self.ref_peak_pos: float = 1078.0

        # Referencia de línea base externa / fondo (Modo 1)
        self.ref_blank_filepath: Optional[Path] = None
        self.ref_blank_name: str = ""
        self.ref_blank_wls: np.ndarray = np.array([])
        self.ref_blank_counts: np.ndarray = np.array([])

        # Recorte espectral (ROI) y poda de bordes de detector
        self.enable_crop_x: bool = False
        self.crop_xmin: float = 0.0
        self.crop_xmax: float = 4000.0
        self.trim_left_pts: int = 0
        self.trim_right_pts: int = 0

        # Elementos gráficos
        self.curve_items: List[pg.PlotDataItem] = []
        self.mean_curve_item: Optional[pg.PlotDataItem] = None
        self.mean_fill_item: Optional[pg.FillBetweenItem] = None
        self.heatmap_item: Optional[pg.ImageItem] = None

        self._setup_ui()

    def _setup_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(6)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── Panel Izquierdo: Controles de Lote y Procesamiento (Scrollable) ───
        controls_scroll = QScrollArea()
        controls_scroll.setWidgetResizable(True)
        controls_scroll.setMinimumWidth(440)
        controls_scroll.setMaximumWidth(520)
        controls_scroll.setFrameShape(QFrame.Shape.NoFrame)

        controls_content = QWidget()
        ctrl_vlo = QVBoxLayout(controls_content)
        ctrl_vlo.setContentsMargins(4, 4, 4, 4)
        ctrl_vlo.setSpacing(8)

        # 1. Grupo: Gestión de Lotes
        box_batch = QGroupBox("📚 Lote de Espectros")
        b_vlo = QVBoxLayout(box_batch)

        btns_batch_hlo = QHBoxLayout()
        self.btn_load_files = QPushButton("📂 Cargar Espectros...")
        self.btn_load_files.setStyleSheet("background-color: #89B4FA; color: #11111B; font-weight: bold;")
        self.btn_load_files.clicked.connect(self._on_load_files)

        self.btn_load_demo = QPushButton("🖼️ Cargar Serie Demo")
        self.btn_load_demo.clicked.connect(self._on_load_demo_series)

        btns_batch_hlo.addWidget(self.btn_load_files)
        btns_batch_hlo.addWidget(self.btn_load_demo)
        b_vlo.addLayout(btns_batch_hlo)

        btns_action_hlo = QHBoxLayout()
        self.btn_remove_sel = QPushButton("🗑️ Quitar")
        self.btn_remove_sel.clicked.connect(self._on_remove_selected)
        self.btn_clear_all = QPushButton("🧹 Limpiar Todo")
        self.btn_clear_all.clicked.connect(self._on_clear_all)
        btns_action_hlo.addWidget(self.btn_remove_sel)
        btns_action_hlo.addWidget(self.btn_clear_all)
        b_vlo.addLayout(btns_action_hlo)

        self.table_spectra = QTableWidget()
        self.table_spectra.setColumnCount(4)
        self.table_spectra.setHorizontalHeaderLabels(["✓", "Color", "Nombre de Archivo", "Puntos"])
        self.table_spectra.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table_spectra.setColumnWidth(0, 30)
        self.table_spectra.setColumnWidth(1, 45)
        self.table_spectra.setColumnWidth(3, 60)
        self.table_spectra.setMinimumHeight(170)
        self.table_spectra.itemChanged.connect(self._on_table_item_changed)
        self.table_spectra.cellDoubleClicked.connect(self._on_color_cell_double_clicked)
        b_vlo.addWidget(self.table_spectra)

        self.lbl_batch_summary = QLabel("0 espectros cargados")
        self.lbl_batch_summary.setStyleSheet("color: #A6ADC8; font-size: 8pt; font-style: italic;")
        b_vlo.addWidget(self.lbl_batch_summary)

        ctrl_vlo.addWidget(box_batch)

        # 2. Grupo: Láser de Excitación (Multi-Espectro)
        box_laser = QGroupBox("🔬 Láser de Excitación")
        l_flo = QFormLayout(box_laser)
        l_flo.setSpacing(6)

        self.combo_multi_laser = QComboBox()
        self.combo_multi_laser.addItems([
            "532.0 nm (Verde Nd:YAG)",
            "632.8 nm (He-Ne)",
            "637.0 nm (Rojo Diodo)",
            "785.0 nm (NIR Diodo)",
            "592.0 nm (Amarillo)",
            "Personalizado..."
        ])
        self.combo_multi_laser.currentIndexChanged.connect(self._on_laser_combo_changed)
        l_flo.addRow("Láser:", self.combo_multi_laser)

        self.spin_multi_laser_custom = QDoubleSpinBox()
        self.spin_multi_laser_custom.setRange(200.0, 2000.0)
        self.spin_multi_laser_custom.setValue(self.laser_nm)
        self.spin_multi_laser_custom.setSuffix(" nm")
        self.spin_multi_laser_custom.setEnabled(False)
        self.spin_multi_laser_custom.valueChanged.connect(self._on_laser_custom_changed)
        l_flo.addRow("λ Personalizada:", self.spin_multi_laser_custom)

        self.check_sync_laser = QCheckBox("Sincronizar con Espectro Individual")
        self.check_sync_laser.setChecked(True)
        l_flo.addRow(self.check_sync_laser)

        self.lbl_laser_status = QLabel(f"Láser activo: {self.laser_nm:.1f} nm")
        self.lbl_laser_status.setStyleSheet("color: #89DCEB; font-size: 8.5pt; font-weight: bold;")
        l_flo.addRow(self.lbl_laser_status)

        ctrl_vlo.addWidget(box_laser)

        # 3. Grupo: Recorte de Rango Espectral (ROI / Bordes)
        box_crop = QGroupBox("✂️ Recorte de Rango Espectral (ROI)")
        cr_vlo = QVBoxLayout(box_crop)
        cr_vlo.setSpacing(6)

        # Atajos Rápidos
        grp_quick = QGroupBox("Atajos Rápidos de Recorte")
        quick_vlo = QVBoxLayout(grp_quick)
        quick_vlo.setSpacing(4)
        quick_vlo.setContentsMargins(6, 6, 6, 6)

        self.btn_crop_cursors = QPushButton("✂️ Recortar a Cursores A y B")
        self.btn_crop_cursors.setStyleSheet("background-color: #A6E3A1; color: #11111B; font-weight: bold; padding: 4px;")
        self.btn_crop_cursors.setToolTip("Recorta todos los espectros del lote al intervalo definido entre el Cursor A y el Cursor B")
        self.btn_crop_cursors.clicked.connect(self._on_crop_to_cursors)
        quick_vlo.addWidget(self.btn_crop_cursors)

        self.btn_crop_rayleigh = QPushButton("⚡ Recortar Láser/Rayleigh (< 150 cm⁻¹)")
        self.btn_crop_rayleigh.setToolTip("Elimina la dispersión elástica Rayleigh por debajo de 150 cm⁻¹ en todo el lote")
        self.btn_crop_rayleigh.clicked.connect(self._on_crop_rayleigh)
        quick_vlo.addWidget(self.btn_crop_rayleigh)

        self.btn_reset_crop = QPushButton("↺ Restaurar Rango Completo")
        self.btn_reset_crop.setStyleSheet("background-color: #F38BA8; color: #11111B; font-weight: bold; padding: 4px;")
        self.btn_reset_crop.setToolTip("Deshace cualquier recorte y restaura el rango espectral original completo de los datos")
        self.btn_reset_crop.clicked.connect(self._on_reset_crop)
        quick_vlo.addWidget(self.btn_reset_crop)
        cr_vlo.addWidget(grp_quick)

        # Límites por Rango Físico X
        grp_range = QGroupBox("Límites Espectrales [X Mín, X Máx]")
        range_flo = QFormLayout(grp_range)
        range_flo.setSpacing(4)
        range_flo.setContentsMargins(6, 6, 6, 6)

        self.check_enable_crop_x = QCheckBox("Habilitar Límite por Rango X")
        self.check_enable_crop_x.setChecked(False)
        self.check_enable_crop_x.toggled.connect(self._on_crop_enable_toggled)
        range_flo.addRow(self.check_enable_crop_x)

        self.spin_crop_xmin = QDoubleSpinBox()
        self.spin_crop_xmin.setRange(-5000.0, 50000.0)
        self.spin_crop_xmin.setDecimals(1)
        self.spin_crop_xmin.setValue(0.0)
        self.spin_crop_xmin.setSuffix(" cm⁻¹")
        self.spin_crop_xmin.valueChanged.connect(self._on_crop_params_changed)
        range_flo.addRow("X Mínimo:", self.spin_crop_xmin)

        self.spin_crop_xmax = QDoubleSpinBox()
        self.spin_crop_xmax.setRange(-5000.0, 50000.0)
        self.spin_crop_xmax.setDecimals(1)
        self.spin_crop_xmax.setValue(4000.0)
        self.spin_crop_xmax.setSuffix(" cm⁻¹")
        self.spin_crop_xmax.valueChanged.connect(self._on_crop_params_changed)
        range_flo.addRow("X Máximo:", self.spin_crop_xmax)
        cr_vlo.addWidget(grp_range)

        # Poda de Bordes del Sensor CCD (Detector Edge Trimming)
        grp_trim = QGroupBox("Poda de Bordes del Sensor CCD")
        trim_flo = QFormLayout(grp_trim)
        trim_flo.setSpacing(4)
        trim_flo.setContentsMargins(6, 6, 6, 6)

        self.spin_trim_left = QSpinBox()
        self.spin_trim_left.setRange(0, 500)
        self.spin_trim_left.setValue(0)
        self.spin_trim_left.setSuffix(" pts")
        self.spin_trim_left.valueChanged.connect(self._reinterpolate_all)
        trim_flo.addRow("Podar Inicio (izq):", self.spin_trim_left)

        self.spin_trim_right = QSpinBox()
        self.spin_trim_right.setRange(0, 500)
        self.spin_trim_right.setValue(0)
        self.spin_trim_right.setSuffix(" pts")
        self.spin_trim_right.valueChanged.connect(self._reinterpolate_all)
        trim_flo.addRow("Podar Fin (der):", self.spin_trim_right)
        cr_vlo.addWidget(grp_trim)

        # Estado del recorte
        self.lbl_crop_status = QLabel("Rango: Completo (0 pts)")
        self.lbl_crop_status.setStyleSheet("color: #89B4FA; font-weight: bold; font-family: monospace; font-size: 8.5pt;")
        cr_vlo.addWidget(self.lbl_crop_status)

        ctrl_vlo.addWidget(box_crop)

        # 4. Grupo: Línea Base / Fondo (2 Modos)
        box_baseline = QGroupBox("📉 Línea Base / Fondo (2 Modos)")
        base_vlo = QVBoxLayout(box_baseline)
        base_vlo.setSpacing(6)

        mode_flo = QFormLayout()
        mode_flo.setSpacing(4)
        self.combo_baseline_mode = QComboBox()
        self.combo_baseline_mode.addItems([
            "Modo 1: Archivo de Referencia (Blanco / Fondo)",
            "Modo 2: Cálculo Individual por Espectro (Algorítmico)",
            "Sin Corrección de Línea Base"
        ])
        self.combo_baseline_mode.currentIndexChanged.connect(self._on_baseline_strategy_changed)
        mode_flo.addRow("Estrategia:", self.combo_baseline_mode)
        base_vlo.addLayout(mode_flo)

        # Sub-Panel Modo 1: Archivo de Referencia (Fondo / Blanco)
        self.panel_mode_ref = QFrame()
        self.panel_mode_ref.setFrameShape(QFrame.Shape.StyledPanel)
        self.panel_mode_ref.setStyleSheet("background-color: #181825; border: 1px solid #313244; border-radius: 6px; padding: 4px;")
        pm1_vlo = QVBoxLayout(self.panel_mode_ref)
        pm1_vlo.setSpacing(5)

        pm1_btns_hlo = QHBoxLayout()
        self.btn_load_ref_file = QPushButton("📂 Cargar Archivo de Fondo...")
        self.btn_load_ref_file.setStyleSheet("background-color: #89B4FA; color: #11111B; font-weight: bold; padding: 4px 8px;")
        self.btn_load_ref_file.clicked.connect(self._on_load_reference_file)
        self.btn_clear_ref_file = QPushButton("❌ Quitar Fondo")
        self.btn_clear_ref_file.clicked.connect(self._on_clear_reference_file)
        pm1_btns_hlo.addWidget(self.btn_load_ref_file)
        pm1_btns_hlo.addWidget(self.btn_clear_ref_file)
        pm1_vlo.addLayout(pm1_btns_hlo)

        self.lbl_ref_file = QLabel("Sin archivo de fondo cargado.")
        self.lbl_ref_file.setStyleSheet("color: #A6ADC8; font-size: 8pt; font-style: italic;")
        self.lbl_ref_file.setWordWrap(True)
        pm1_vlo.addWidget(self.lbl_ref_file)

        pm1_batch_flo = QFormLayout()
        self.combo_blank_from_batch = QComboBox()
        self.combo_blank_from_batch.addItem("(Ninguno / Usar Archivo Externo)")
        self.combo_blank_from_batch.currentIndexChanged.connect(self._reprocess_and_update)
        pm1_batch_flo.addRow("O blanco del lote:", self.combo_blank_from_batch)
        pm1_vlo.addLayout(pm1_batch_flo)

        base_vlo.addWidget(self.panel_mode_ref)

        # Sub-Panel Modo 2: Cálculo Individual por Espectro
        self.panel_mode_indiv = QFrame()
        self.panel_mode_indiv.setFrameShape(QFrame.Shape.StyledPanel)
        self.panel_mode_indiv.setStyleSheet("background-color: #181825; border: 1px solid #313244; border-radius: 6px; padding: 4px;")
        pm2_flo = QFormLayout(self.panel_mode_indiv)
        pm2_flo.setSpacing(5)

        self.combo_indiv_algo = QComboBox()
        self.combo_indiv_algo.addItems([
            "AsLS (Asimétrico Penalizado)",
            "AirPLS (Iterativo Ponderado)",
            "Polinomio ModPoly",
            "Rolling Ball (Morfológico)"
        ])
        self.combo_indiv_algo.currentIndexChanged.connect(self._on_indiv_algo_changed)
        pm2_flo.addRow("Algoritmo:", self.combo_indiv_algo)

        self.spin_asls_lambda = QDoubleSpinBox()
        self.spin_asls_lambda.setRange(1e2, 1e9)
        self.spin_asls_lambda.setValue(1e5)
        self.spin_asls_lambda.setSingleStep(1e4)
        self.spin_asls_lambda.valueChanged.connect(self._reprocess_and_update)
        pm2_flo.addRow("AsLS Lambda (λ):", self.spin_asls_lambda)

        self.spin_asls_p = QDoubleSpinBox()
        self.spin_asls_p.setRange(0.0001, 0.1)
        self.spin_asls_p.setValue(0.005)
        self.spin_asls_p.setSingleStep(0.001)
        self.spin_asls_p.setDecimals(4)
        self.spin_asls_p.valueChanged.connect(self._reprocess_and_update)
        pm2_flo.addRow("AsLS Asimetría (p):", self.spin_asls_p)

        self.spin_modpoly_order = QSpinBox()
        self.spin_modpoly_order.setRange(1, 8)
        self.spin_modpoly_order.setValue(3)
        self.spin_modpoly_order.setEnabled(False)
        self.spin_modpoly_order.valueChanged.connect(self._reprocess_and_update)
        pm2_flo.addRow("Orden ModPoly:", self.spin_modpoly_order)

        self.spin_rolling_radius = QSpinBox()
        self.spin_rolling_radius.setRange(5, 500)
        self.spin_rolling_radius.setValue(50)
        self.spin_rolling_radius.setEnabled(False)
        self.spin_rolling_radius.valueChanged.connect(self._reprocess_and_update)
        pm2_flo.addRow("Radio Bola (px):", self.spin_rolling_radius)

        base_vlo.addWidget(self.panel_mode_indiv)
        self.panel_mode_indiv.setVisible(False)  # Por defecto Modo 1 está visible

        # Alias para compatibilidad hacia atrás
        self.combo_multi_baseline = self.combo_baseline_mode
        self.combo_blank_spectrum = self.combo_blank_from_batch

        self.btn_apply_baseline = QPushButton("⚡ Actualizar Línea Base")
        self.btn_apply_baseline.setStyleSheet("background-color: #A6E3A1; color: #11111B; font-weight: bold; padding: 5px;")
        self.btn_apply_baseline.clicked.connect(self._reprocess_and_update)
        base_vlo.addWidget(self.btn_apply_baseline)

        ctrl_vlo.addWidget(box_baseline)

        # 3. Grupo: Filtros en Lote & Despiking
        box_filters = QGroupBox("🌊 Filtros en Lote & Despiking")
        f_flo = QFormLayout(box_filters)
        f_flo.setSpacing(6)

        self.check_batch_smooth = QCheckBox("Suavizado Savitzky-Golay Compartido")
        self.check_batch_smooth.toggled.connect(self._reprocess_and_update)
        f_flo.addRow(self.check_batch_smooth)

        self.spin_batch_sg_win = QSpinBox()
        self.spin_batch_sg_win.setRange(3, 51)
        self.spin_batch_sg_win.setSingleStep(2)
        self.spin_batch_sg_win.setValue(9)
        self.spin_batch_sg_win.valueChanged.connect(self._reprocess_and_update)
        f_flo.addRow("Ventana SG (pts):", self.spin_batch_sg_win)

        self.btn_batch_despike = QPushButton("✨ Limpiar Rayos Cósmicos en Lote")
        self.btn_batch_despike.clicked.connect(self._on_batch_despike)
        f_flo.addRow(self.btn_batch_despike)

        ctrl_vlo.addWidget(box_filters)

        # 4. Grupo: Normalizaciones Espectroscópicas
        box_norm = QGroupBox("⚖️ Normalizaciones Espectroscópicas")
        n_flo = QFormLayout(box_norm)
        n_flo.setSpacing(6)

        self.combo_norm_mode = QComboBox()
        self.combo_norm_mode.addItems([
            "Sin Normalizar (Cuentas Netas)",
            "A Máximo Global (0 - 1)",
            "A Pico de Referencia Elegido",
            "Por Área Unitaria (Integral = 1)",
            "SNV (Standard Normal Variate)"
        ])
        self.combo_norm_mode.currentIndexChanged.connect(self._on_norm_mode_changed)
        n_flo.addRow("Modo:", self.combo_norm_mode)

        ref_hlo = QHBoxLayout()
        self.spin_ref_peak = QDoubleSpinBox()
        self.spin_ref_peak.setRange(100.0, 4000.0)
        self.spin_ref_peak.setValue(1078.0)
        self.spin_ref_peak.setSuffix(" cm⁻¹")
        self.spin_ref_peak.setEnabled(False)
        self.spin_ref_peak.valueChanged.connect(self._reprocess_and_update)

        self.btn_use_cursor_a = QPushButton("🎯 Usar Cursor A")
        self.btn_use_cursor_a.setEnabled(False)
        self.btn_use_cursor_a.clicked.connect(self._on_use_cursor_a_as_ref)

        ref_hlo.addWidget(self.spin_ref_peak)
        ref_hlo.addWidget(self.btn_use_cursor_a)
        n_flo.addRow("Pico Ref:", ref_hlo)

        ctrl_vlo.addWidget(box_norm)
        ctrl_vlo.addStretch()

        controls_scroll.setWidget(controls_content)
        splitter.addWidget(controls_scroll)

        # ── Panel Derecho: Visualizador y Herramientas Cuantitativas ──────────
        right_widget = QWidget()
        right_vlo = QVBoxLayout(right_widget)
        right_vlo.setContentsMargins(4, 4, 4, 4)
        right_vlo.setSpacing(6)

        # Barra Superior de Visualización
        top_bar = QWidget()
        tb_hlo = QHBoxLayout(top_bar)
        tb_hlo.setContentsMargins(0, 0, 0, 0)
        tb_hlo.setSpacing(8)

        tb_hlo.addWidget(QLabel("<b>Modo:</b>"))
        self.combo_view_mode = QComboBox()
        self.combo_view_mode.addItems(["Superposición (Overlay)", "Cascada Vertical (Waterfall)", "Mapa de Calor 2D (Heatmap)"])
        self.combo_view_mode.currentIndexChanged.connect(self._on_view_mode_changed)
        tb_hlo.addWidget(self.combo_view_mode)

        self.lbl_waterfall = QLabel("Offset Cascada:")
        self.slider_waterfall = QSlider(Qt.Orientation.Horizontal)
        self.slider_waterfall.setRange(0, 100)
        self.slider_waterfall.setValue(30)
        self.slider_waterfall.setFixedWidth(120)
        self.slider_waterfall.setEnabled(False)
        self.slider_waterfall.valueChanged.connect(self._reprocess_and_update)
        tb_hlo.addWidget(self.lbl_waterfall)
        tb_hlo.addWidget(self.slider_waterfall)

        tb_hlo.addSpacing(10)
        tb_hlo.addWidget(QLabel("Paleta:"))
        self.combo_cmap = QComboBox()
        self.combo_cmap.addItems(["Viridis", "Plasma", "Turbo", "Magma", "Rainbow", "Cian a Magenta"])
        self.combo_cmap.currentIndexChanged.connect(self._on_palette_changed)
        tb_hlo.addWidget(self.combo_cmap)

        tb_hlo.addStretch()

        self.btn_copy_tsv = QPushButton("📋 Copiar TSV")
        self.btn_copy_tsv.clicked.connect(self._on_copy_tsv)
        self.btn_export_csv = QPushButton("💾 Exportar CSV")
        self.btn_export_csv.setStyleSheet("background-color: #A6E3A1; color: #11111B; font-weight: bold;")
        self.btn_export_csv.clicked.connect(self._on_export_csv)
        tb_hlo.addWidget(self.btn_copy_tsv)
        tb_hlo.addWidget(self.btn_export_csv)

        right_vlo.addWidget(top_bar)

        # Pestañas de Visualización y Métricas
        self.tabs_views = QTabWidget()

        # ── Tab 1: Gráfico Principal de Espectros (Overlay / Cascada) ─────────
        tab_plot = QWidget()
        tp_vlo = QVBoxLayout(tab_plot)
        tp_vlo.setContentsMargins(0, 0, 0, 0)
        tp_vlo.setSpacing(4)

        self.plot_multi = pg.PlotWidget(title="Espectros Raman en Lote (Overlay / Cascada)")
        self.plot_multi.setLabel("bottom", "Corrimiento Raman (cm⁻¹)")
        self.plot_multi.setLabel("left", "Intensidad Normalizada (cts / u.a.)")
        self.plot_multi.showGrid(x=True, y=True, alpha=0.25)
        self.plot_multi.addLegend(offset=(-10, 10))

        # Cursores A y B en Multi-Espectro
        self.cursor_a = pg.InfiniteLine(pos=1078.0, angle=90, movable=True, pen=pg.mkPen("#F38BA8", width=1.8))
        self.cursor_a.sigPositionChanged.connect(self._on_cursors_moved)
        self.plot_multi.addItem(self.cursor_a)

        self.cursor_b = pg.InfiniteLine(pos=1580.0, angle=90, movable=True, pen=pg.mkPen("#F9E2AF", width=1.8, style=Qt.PenStyle.DashLine))
        self.cursor_b.sigPositionChanged.connect(self._on_cursors_moved)
        self.plot_multi.addItem(self.cursor_b)

        self.region_ab = pg.LinearRegionItem(values=[1078.0, 1580.0], brush=pg.mkBrush(137, 180, 250, 35), movable=True)
        self.region_ab.sigRegionChanged.connect(self._on_region_ab_dragged)
        self.plot_multi.addItem(self.region_ab)

        tp_vlo.addWidget(self.plot_multi)

        self.lbl_cursor_metrics = QLabel("Regla A: 1078.00 cm⁻¹ | Regla B: 1580.00 cm⁻¹ | ΔX: 502.00 cm⁻¹")
        self.lbl_cursor_metrics.setStyleSheet("background-color: #181825; color: #CDD6F4; font-size: 8.5pt; padding: 4px 8px; border-radius: 4px;")
        tp_vlo.addWidget(self.lbl_cursor_metrics)

        self.tabs_views.addTab(tab_plot, "📈 Espectros (Overlay / Cascada)")

        # ── Tab 2: Espectro Promedio ± Desviación Estándar (μ ± σ) ─────────────
        tab_mean = QWidget()
        tm_vlo = QVBoxLayout(tab_mean)
        tm_vlo.setContentsMargins(0, 0, 0, 0)
        tm_vlo.setSpacing(4)

        self.plot_mean = pg.PlotWidget(title="Espectro Promedio (Línea Central) y Banda de Dispersión ± 1σ (Sombreado)")
        self.plot_mean.setLabel("bottom", "Corrimiento Raman (cm⁻¹)")
        self.plot_mean.setLabel("left", "Intensidad Promedio (cts / u.a.)")
        self.plot_mean.showGrid(x=True, y=True, alpha=0.25)
        tm_vlo.addWidget(self.plot_mean)

        self.lbl_reproducibility = QLabel("RSD% Promedio Global: N/A | RSD% en Cursor A: N/A")
        self.lbl_reproducibility.setStyleSheet("background-color: #181825; color: #A6E3A1; font-weight: bold; font-size: 9pt; padding: 6px; border-radius: 4px;")
        tm_vlo.addWidget(self.lbl_reproducibility)

        self.tabs_views.addTab(tab_mean, "📊 Promedio ± Desvío (μ ± σ)")

        # ── Tab 3: Seguimiento Cinético de Banda (Rango A-B) ──────────────────
        tab_kin = QWidget()
        tk_vlo = QVBoxLayout(tab_kin)
        tk_vlo.setContentsMargins(0, 0, 0, 0)
        tk_vlo.setSpacing(4)

        self.plot_kinetics = pg.PlotWidget(title="Evolución de Intensidad Máxima y Área de Banda en la Región [A, B]")
        self.plot_kinetics.setLabel("bottom", "Número de Espectro / Medición")
        self.plot_kinetics.setLabel("left", "Intensidad Neta (cts)")
        self.plot_kinetics.showGrid(x=True, y=True, alpha=0.25)
        self.plot_kinetics.addLegend(offset=(-10, 10))
        tk_vlo.addWidget(self.plot_kinetics)

        self.tabs_views.addTab(tab_kin, "⏱️ Cinética de Banda (Rango A-B)")

        # ── Tab 4: Mapa de Calor Espectro-Temporal 2D ──────────────────────────
        tab_heat = QWidget()
        th_vlo = QVBoxLayout(tab_heat)
        th_vlo.setContentsMargins(0, 0, 0, 0)
        th_vlo.setSpacing(4)

        self.plot_heatmap = pg.PlotWidget(title="Mapa de Calor Espectro-Temporal 2D (Eje X: Raman Shift, Eje Y: Índice)")
        self.plot_heatmap.setLabel("bottom", "Corrimiento Raman (cm⁻¹)")
        self.plot_heatmap.setLabel("left", "Índice de Espectro / Tiempo")
        self.heatmap_item = pg.ImageItem()
        self.plot_heatmap.addItem(self.heatmap_item)
        th_vlo.addWidget(self.plot_heatmap)

        self.tabs_views.addTab(tab_heat, "🗺️ Mapa de Calor 2D")

        # ── Tab 5: Análisis Quimiométrico (PCA) ────────────────────────────────
        tab_pca = QWidget()
        tpca_vlo = QVBoxLayout(tab_pca)
        tpca_vlo.setContentsMargins(0, 0, 0, 0)
        tpca_vlo.setSpacing(4)

        pca_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.plot_pca_scores = pg.PlotWidget(title="Score Plot (PC1 vs PC2)")
        self.plot_pca_scores.setLabel("bottom", "Componente Principal 1 (PC1)")
        self.plot_pca_scores.setLabel("left", "Componente Principal 2 (PC2)")
        self.plot_pca_scores.showGrid(x=True, y=True, alpha=0.25)

        self.plot_pca_loadings = pg.PlotWidget(title="Cargas Espectrales (Loadings PC1 & PC2)")
        self.plot_pca_loadings.setLabel("bottom", "Corrimiento Raman (cm⁻¹)")
        self.plot_pca_loadings.setLabel("left", "Amplitud de Carga (u.a.)")
        self.plot_pca_loadings.showGrid(x=True, y=True, alpha=0.25)

        pca_splitter.addWidget(self.plot_pca_scores)
        pca_splitter.addWidget(self.plot_pca_loadings)
        tpca_vlo.addWidget(pca_splitter)

        self.lbl_pca_info = QLabel("Varianza Explicada: PC1: N/A | PC2: N/A | Total: N/A")
        self.lbl_pca_info.setStyleSheet("background-color: #181825; color: #F5C2E7; font-size: 8.5pt; padding: 4px 8px; border-radius: 4px;")
        tpca_vlo.addWidget(self.lbl_pca_info)

        self.tabs_views.addTab(tab_pca, "🧬 Análisis PCA (SVD)")

        right_vlo.addWidget(self.tabs_views)

        splitter.addWidget(right_widget)
        splitter.setSizes([460, 960])

        main_layout.addWidget(splitter)

    # ── Gestión de Archivos y Carga ───────────────────────────────────────────

    def _on_load_files(self):
        start_dir = str(Path.home() / "Documents")
        files, _ = QFileDialog.getOpenFileNames(
            self, "Cargar Lote de Espectros", start_dir,
            "Archivos Espectroscópicos (*.asc *.txt *.csv *.dat);;Todos (*.*)"
        )
        if not files:
            return

        loaded_count = 0
        for f in files:
            p = Path(f)
            try:
                meta, wls, counts = parse_andor_solis_file(p)
                if len(wls) > 5 and len(counts) > 5:
                    self._add_spectrum_to_collection(p.name, p, wls, counts, meta)
                    loaded_count += 1
            except Exception as e:
                print(f"[MultiSpectrum Error] Error leyendo {p.name}: {e}")

        if loaded_count > 0:
            # Auto-detección del láser a partir de los metadatos del primer archivo cargado
            if len(self.spectra_list) == loaded_count:
                first_meta = self.spectra_list[0].get("metadata", {})
                for k in ("Laser Wavelength", "Laser Wavelength (nm)", "Excitation (nm)", "Laser", "Excitation Wavelength"):
                    if k in first_meta:
                        try:
                            val = float(str(first_meta[k]).replace(",", "."))
                            if 300.0 <= val <= 1500.0:
                                self.set_laser_wavelength(val, sync_parent=self.check_sync_laser.isChecked())
                                break
                        except ValueError:
                            pass

            self._update_palettes()
            self._reinterpolate_all()
            self._refresh_table()

    def _on_load_demo_series(self):
        demo_file = Path(__file__).resolve().parent.parent / "reserva" / "90%_in_red_10s_3_em.asc"
        if demo_file.exists():
            meta, wls, counts = parse_andor_solis_file(demo_file)
        else:
            # Espectro sintético SERS 4-MBA
            wls = np.linspace(540.0, 600.0, 1000)
            shifts = wavelength_to_raman_shift(wls, 532.0)
            counts = 500.0 + 3000.0 * np.exp(-0.5 * ((shifts - 1078.0) / 14.0)**2) + 1500.0 * np.exp(-0.5 * ((shifts - 1585.0) / 18.0)**2)
            meta = {"Demo": "True", "Laser": "532.0"}

        # Generar una serie cinética de 6 espectros modulando intensidades y agregando ruido realista
        factors = [0.4, 0.7, 1.0, 1.4, 1.9, 2.5]
        for i, f in enumerate(factors):
            noise = np.random.normal(0, 15.0 * np.sqrt(f), len(counts))
            c_series = counts * f + noise
            self._add_spectrum_to_collection(
                f"Serie_SERS_t{(i+1)*10}s.asc",
                None,
                wls,
                c_series,
                {**meta, "Time_s": str((i + 1) * 10)}
            )

        self._update_palettes()
        self._reinterpolate_all()
        self._refresh_table()

    def _add_spectrum_to_collection(self, name: str, filepath: Optional[Path], wls: np.ndarray, counts: np.ndarray, meta: Dict):
        # Asignar color temporal por defecto
        col = QColor("#89B4FA")
        self.spectra_list.append({
            "name": name,
            "filepath": filepath,
            "raw_wls": np.asarray(wls, dtype=np.float64),
            "raw_counts": np.asarray(counts, dtype=np.float64),
            "active_counts": np.asarray(counts, dtype=np.float64).copy(),
            "color": col,
            "visible": True,
            "metadata": dict(meta)
        })

    def _update_palettes(self):
        cmap_name = self.combo_cmap.currentText().lower()
        if "viridis" in cmap_name:
            c_name = "viridis"
        elif "plasma" in cmap_name:
            c_name = "plasma"
        elif "turbo" in cmap_name:
            c_name = "turbo"
        elif "magma" in cmap_name:
            c_name = "magma"
        elif "arcoíris" in cmap_name or "rainbow" in cmap_name:
            c_name = "hsv"
        else:
            c_name = "cool"

        colors = generate_spectrum_palette(len(self.spectra_list), c_name)
        for i, col in enumerate(colors):
            self.spectra_list[i]["color"] = col

    def _refresh_table(self):
        self.table_spectra.blockSignals(True)
        self.table_spectra.setRowCount(len(self.spectra_list))
        self.combo_blank_from_batch.blockSignals(True)
        curr_batch_blank = self.combo_blank_from_batch.currentIndex()
        self.combo_blank_from_batch.clear()
        self.combo_blank_from_batch.addItem("(Ninguno / Usar Archivo Externo)")

        for r, sp in enumerate(self.spectra_list):
            # Checkbox de visibilidad
            chk_item = QTableWidgetItem()
            chk_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            chk_item.setCheckState(Qt.CheckState.Checked if sp["visible"] else Qt.CheckState.Unchecked)
            self.table_spectra.setItem(r, 0, chk_item)

            # Muestra de color
            col_item = QTableWidgetItem(" ■ ")
            col_item.setForeground(sp["color"])
            col_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            col_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.table_spectra.setItem(r, 1, col_item)

            # Nombre de archivo
            name_item = QTableWidgetItem(sp["name"])
            name_item.setToolTip(str(sp["filepath"]) if sp["filepath"] else sp["name"])
            self.table_spectra.setItem(r, 2, name_item)

            # Puntos
            pts_item = QTableWidgetItem(str(len(sp["raw_wls"])))
            pts_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table_spectra.setItem(r, 3, pts_item)

            self.combo_blank_from_batch.addItem(f"#{r+1} {sp['name']}")

        if 0 <= curr_batch_blank < self.combo_blank_from_batch.count():
            self.combo_blank_from_batch.setCurrentIndex(curr_batch_blank)
        self.combo_blank_from_batch.blockSignals(False)

        self.table_spectra.blockSignals(False)
        act = sum(1 for s in self.spectra_list if s["visible"])
        self.lbl_batch_summary.setText(f"{len(self.spectra_list)} espectros ({act} visibles)")

    def _on_table_item_changed(self, item: QTableWidgetItem):
        if item.column() == 0:
            row = item.row()
            if row < len(self.spectra_list):
                self.spectra_list[row]["visible"] = (item.checkState() == Qt.CheckState.Checked)
                self._reinterpolate_all()

    def _on_color_cell_double_clicked(self, row: int, col: int):
        if col == 1 and row < len(self.spectra_list):
            curr_col = self.spectra_list[row]["color"]
            new_col = QColorDialog.getColor(curr_col, self, "Seleccionar Color de Espectro")
            if new_col.isValid():
                self.spectra_list[row]["color"] = new_col
                self._refresh_table()
                self._reprocess_and_update()

    def _on_remove_selected(self):
        row = self.table_spectra.currentRow()
        if 0 <= row < len(self.spectra_list):
            self.spectra_list.pop(row)
            self._update_palettes()
            self._reinterpolate_all()
            self._refresh_table()

    def _on_clear_all(self):
        self.spectra_list.clear()
        self.common_x = np.array([])
        self.Y_raw = np.empty((0, 0))
        self.Y_corrected = np.empty((0, 0))
        self.Y_displayed = np.empty((0, 0))
        self._refresh_table()
        self._reprocess_and_update()

    # ── Remuestreo e Intercalibración con Recorte de ROI y Poda de Bordes ─────

    def _reinterpolate_all(self):
        crop_xmin = self.spin_crop_xmin.value() if self.check_enable_crop_x.isChecked() else None
        crop_xmax = self.spin_crop_xmax.value() if self.check_enable_crop_x.isChecked() else None
        trim_l = self.spin_trim_left.value()
        trim_r = self.spin_trim_right.value()

        x_range = None
        if self.check_enable_crop_x.isChecked() and crop_xmin is not None and crop_xmax is not None:
            x_range = (min(crop_xmin, crop_xmax), max(crop_xmin, crop_xmax))

        visible_spectra = []
        self.active_indices = []
        for idx, sp in enumerate(self.spectra_list):
            if sp["visible"]:
                # Convertir a corrimiento Raman según el láser actual
                x_shift = wavelength_to_raman_shift(sp["raw_wls"], self.laser_nm)

                # Poda de bordes de detector si trim_l > 0 o trim_r > 0
                if trim_l > 0 or trim_r > 0:
                    x_shift, y_cnts, _ = crop_spectrum(
                        x_shift, sp["active_counts"],
                        trim_left_pts=trim_l, trim_right_pts=trim_r
                    )
                else:
                    y_cnts = sp["active_counts"]

                visible_spectra.append((x_shift, y_cnts, sp["name"], sp["metadata"]))
                self.active_indices.append(idx)

        if not visible_spectra:
            self.common_x = np.array([])
            self.Y_raw = np.empty((0, 0))
            self.Y_corrected = np.empty((0, 0))
            self.Y_displayed = np.empty((0, 0))
            self.lbl_crop_status.setText("Sin espectros visibles")
            self._reprocess_and_update()
            return

        self.common_x, self.Y_raw, _, _ = interpolate_spectra_to_common_grid(
            visible_spectra,
            x_range=x_range
        )

        if len(self.common_x) > 0:
            x0 = float(self.common_x[0])
            x1 = float(self.common_x[-1])
            n_pts = len(self.common_x)

            if not self.check_enable_crop_x.isChecked():
                self.spin_crop_xmin.blockSignals(True)
                self.spin_crop_xmax.blockSignals(True)
                self.spin_crop_xmin.setValue(round(x0, 1))
                self.spin_crop_xmax.setValue(round(x1, 1))
                self.spin_crop_xmin.blockSignals(False)
                self.spin_crop_xmax.blockSignals(False)
                self.lbl_crop_status.setText(f"Rango Completo: <b>{x0:.1f}</b> a <b>{x1:.1f} cm⁻¹</b> ({n_pts} pts)")
            else:
                self.lbl_crop_status.setText(f"ROI Activo: <b>{x0:.1f}</b> a <b>{x1:.1f} cm⁻¹</b> ({n_pts} pts)")

            # Clamping suave de cursores si quedaron fuera del rango
            val_a = float(self.cursor_a.value())
            val_b = float(self.cursor_b.value())
            new_a = max(x0, min(x1, val_a))
            new_b = max(x0, min(x1, val_b))
            if math.isclose(new_a, new_b, abs_tol=1e-3):
                span = x1 - x0
                new_a = max(x0, new_a - 0.05 * span)
                new_b = min(x1, new_b + 0.05 * span)

            self.cursor_a.blockSignals(True)
            self.cursor_b.blockSignals(True)
            self.cursor_a.setValue(new_a)
            self.cursor_b.setValue(new_b)
            self.cursor_a.blockSignals(False)
            self.cursor_b.blockSignals(False)

            self.region_ab.blockSignals(True)
            self.region_ab.setRegion([min(new_a, new_b), max(new_a, new_b)])
            self.region_ab.blockSignals(False)

        self._reprocess_and_update()

    # ── Gestión de Recorte de ROI y Poda de Bordes ────────────────────────────

    def _on_crop_to_cursors(self):
        """Recorta todos los espectros del lote al intervalo definido entre Cursor A y Cursor B."""
        if not self.spectra_list or len(self.common_x) == 0:
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
        self._reinterpolate_all()

    def _on_crop_rayleigh(self):
        """Atajo para recortar la subida del filtro Rayleigh (< 150 cm⁻¹) en todo el lote."""
        if not self.spectra_list or len(self.common_x) == 0:
            return
        self.spin_crop_xmin.setValue(150.0)
        self.check_enable_crop_x.setChecked(True)
        self._reinterpolate_all()

    def _on_reset_crop(self):
        """Restaura el rango completo original de los espectros del lote sin pérdidas."""
        self.check_enable_crop_x.setChecked(False)
        self.spin_trim_left.setValue(0)
        self.spin_trim_right.setValue(0)
        full_mins = []
        full_maxs = []
        for sp in self.spectra_list:
            xs = wavelength_to_raman_shift(sp["raw_wls"], self.laser_nm)
            full_mins.append(float(np.min(xs)))
            full_maxs.append(float(np.max(xs)))
        if full_mins and full_maxs:
            self.spin_crop_xmin.blockSignals(True)
            self.spin_crop_xmax.blockSignals(True)
            self.spin_crop_xmin.setValue(round(min(full_mins), 1))
            self.spin_crop_xmax.setValue(round(max(full_maxs), 1))
            self.spin_crop_xmin.blockSignals(False)
            self.spin_crop_xmax.blockSignals(False)
        self._reinterpolate_all()

    def _on_crop_enable_toggled(self, checked: bool):
        self._reinterpolate_all()

    def _on_crop_params_changed(self):
        if self.check_enable_crop_x.isChecked():
            self._reinterpolate_all()

    # ── Gestión de Láser de Excitación ────────────────────────────────────────

    def _on_laser_combo_changed(self, idx: int):
        lasers = [532.0, 632.8, 637.0, 785.0, 592.0]
        if idx < len(lasers):
            self.laser_nm = lasers[idx]
            self.spin_multi_laser_custom.setEnabled(False)
            self.spin_multi_laser_custom.blockSignals(True)
            self.spin_multi_laser_custom.setValue(self.laser_nm)
            self.spin_multi_laser_custom.blockSignals(False)
        else:
            self.spin_multi_laser_custom.setEnabled(True)
            self.laser_nm = float(self.spin_multi_laser_custom.value())

        self.lbl_laser_status.setText(f"Láser activo: {self.laser_nm:.1f} nm")

        if self.check_sync_laser.isChecked() and self.parent_analyzer and hasattr(self.parent_analyzer, "set_laser_wavelength"):
            self.parent_analyzer.set_laser_wavelength(self.laser_nm, sync_multi=False)

        self._reinterpolate_all()

    def _on_laser_custom_changed(self, val: float):
        if self.combo_multi_laser.currentIndex() == 5:  # Personalizado
            self.laser_nm = float(val)
            self.lbl_laser_status.setText(f"Láser activo: {self.laser_nm:.1f} nm")
            if self.check_sync_laser.isChecked() and self.parent_analyzer and hasattr(self.parent_analyzer, "set_laser_wavelength"):
                self.parent_analyzer.set_laser_wavelength(self.laser_nm, sync_multi=False)
            self._reinterpolate_all()

    def set_laser_wavelength(self, laser_nm: float, sync_parent: bool = False):
        """Fija programáticamente la longitud de onda del láser y actualiza la UI."""
        self.laser_nm = float(laser_nm)
        lasers = [532.0, 632.8, 637.0, 785.0, 592.0]
        found_idx = -1
        for i, l in enumerate(lasers):
            if math.isclose(self.laser_nm, l, abs_tol=0.2):
                found_idx = i
                break

        self.combo_multi_laser.blockSignals(True)
        self.spin_multi_laser_custom.blockSignals(True)
        if found_idx >= 0:
            self.combo_multi_laser.setCurrentIndex(found_idx)
            self.spin_multi_laser_custom.setValue(self.laser_nm)
            self.spin_multi_laser_custom.setEnabled(False)
        else:
            self.combo_multi_laser.setCurrentIndex(5)  # Personalizado
            self.spin_multi_laser_custom.setValue(self.laser_nm)
            self.spin_multi_laser_custom.setEnabled(True)
        self.combo_multi_laser.blockSignals(False)
        self.spin_multi_laser_custom.blockSignals(False)

        self.lbl_laser_status.setText(f"Láser activo: {self.laser_nm:.1f} nm")

        if sync_parent and self.check_sync_laser.isChecked() and self.parent_analyzer and hasattr(self.parent_analyzer, "set_laser_wavelength"):
            self.parent_analyzer.set_laser_wavelength(self.laser_nm, sync_multi=False)

        self._reinterpolate_all()

    # ── Gestión de Línea Base en Dos Modos ───────────────────────────────────

    def _on_baseline_strategy_changed(self, idx: int):
        # 0: Modo 1 (Archivo / Blanco), 1: Modo 2 (Cálculo individual), 2: Sin línea base
        self.panel_mode_ref.setVisible(idx == 0)
        self.panel_mode_indiv.setVisible(idx == 1)
        self._reprocess_and_update()

    def _on_indiv_algo_changed(self, idx: int):
        is_asls = (idx == 0)
        is_airpls = (idx == 1)
        is_modpoly = (idx == 2)
        is_rolling = (idx == 3)
        self.spin_asls_lambda.setEnabled(is_asls or is_airpls)
        self.spin_asls_p.setEnabled(is_asls)
        self.spin_modpoly_order.setEnabled(is_modpoly)
        self.spin_rolling_radius.setEnabled(is_rolling)
        self._reprocess_and_update()

    def _on_load_reference_file(self):
        start_dir = str(Path.home() / "Documents")
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar Archivo de Fondo / Blanco de Referencia", start_dir,
            "Archivos Espectroscópicos (*.asc *.txt *.csv *.dat);;Todos (*.*)"
        )
        if not filepath:
            return
        self.load_reference_file(filepath)

    def load_reference_file(self, filepath: Union[str, Path]):
        """Carga un archivo de referencia/blanco externo para sustraer como línea base (Modo 1)."""
        p = Path(filepath)
        try:
            meta, wls, counts = parse_andor_solis_file(p)
            self.ref_blank_filepath = p
            self.ref_blank_name = p.name
            self.ref_blank_wls = np.asarray(wls, dtype=np.float64)
            self.ref_blank_counts = np.asarray(counts, dtype=np.float64)
            self.lbl_ref_file.setText(f"✓ <b>{self.ref_blank_name}</b> ({len(wls)} pts)")
            self.lbl_ref_file.setStyleSheet("color: #A6E3A1; font-size: 8pt;")
            self.combo_baseline_mode.setCurrentIndex(0)
            self._reprocess_and_update()
        except Exception as e:
            QMessageBox.critical(self, "Error al cargar fondo", f"No se pudo parsear el archivo de referencia:\n{e}")

    def _on_clear_reference_file(self):
        self.ref_blank_filepath = None
        self.ref_blank_name = ""
        self.ref_blank_wls = np.array([])
        self.ref_blank_counts = np.array([])
        self.lbl_ref_file.setText("Sin archivo de fondo cargado.")
        self.lbl_ref_file.setStyleSheet("color: #A6ADC8; font-size: 8pt; font-style: italic;")
        self._reprocess_and_update()

    def _on_baseline_mode_changed(self, idx: int):
        """Método de compatibilidad hacia atrás si se invoca desde tests o scripts."""
        if idx == 4:  # Restar blanco
            self.combo_baseline_mode.setCurrentIndex(0)
        elif idx == 5:  # Sin línea base
            self.combo_baseline_mode.setCurrentIndex(2)
        elif idx in (0, 1, 2, 3):  # Modos algorítmicos individuales
            self.combo_baseline_mode.setCurrentIndex(1)
            self.combo_indiv_algo.setCurrentIndex(idx)
        else:
            self._reprocess_and_update()

    # ── Pipeline de Procesamiento Matricial (Línea Base + Filtro + Norm) ──────

    def _on_norm_mode_changed(self, idx: int):
        modes = ["none", "max", "peak", "area", "snv"]
        self.norm_mode = modes[idx]
        is_peak = (self.norm_mode == "peak")
        self.spin_ref_peak.setEnabled(is_peak)
        self.btn_use_cursor_a.setEnabled(is_peak)
        self._reprocess_and_update()

    def _on_view_mode_changed(self, idx: int):
        modes = ["overlay", "waterfall", "heatmap"]
        self.view_mode = modes[idx]
        self.slider_waterfall.setEnabled(self.view_mode == "waterfall")
        if self.view_mode == "heatmap":
            self.tabs_views.setCurrentIndex(3)
        else:
            self.tabs_views.setCurrentIndex(0)
        self._reprocess_and_update()

    def _on_palette_changed(self):
        self._update_palettes()
        self._refresh_table()
        self._reprocess_and_update()

    def _on_use_cursor_a_as_ref(self):
        pos_a = float(self.cursor_a.value())
        self.spin_ref_peak.setValue(pos_a)
        self._reprocess_and_update()

    def _on_batch_despike(self):
        if not self.spectra_list:
            return
        total_spikes = 0
        for sp in self.spectra_list:
            cleaned, mask = remove_cosmic_rays(sp["active_counts"], threshold=5.0)
            sp["active_counts"] = cleaned
            total_spikes += int(np.sum(mask))

        QMessageBox.information(
            self,
            "Limpieza de Rayos Cósmicos",
            f"Se limpiaron {total_spikes} spikes en {len(self.spectra_list)} espectros."
        )
        self._reinterpolate_all()

    def _reprocess_and_update(self):
        if self.Y_raw.size == 0 or len(self.common_x) == 0:
            self.plot_multi.clear()
            self.plot_mean.clear()
            self.plot_kinetics.clear()
            self.heatmap_item.clear()
            self.plot_pca_scores.clear()
            self.plot_pca_loadings.clear()
            return

        N, M = self.Y_raw.shape
        Y_work = self.Y_raw.copy()

        # 1. Corrección de Línea Base en Dos Modos
        b_strategy = self.combo_baseline_mode.currentIndex()

        if b_strategy == 0:  # Modo 1: Archivo de Referencia (Fondo / Blanco)
            if self.ref_blank_wls.size > 0 and self.ref_blank_counts.size > 0:
                # Si las longitudes de onda son ópticas en nm, convertir al mismo Raman Shift
                if np.all(self.ref_blank_wls > 200.0):
                    blank_x = wavelength_to_raman_shift(self.ref_blank_wls, self.laser_nm)
                else:
                    blank_x = self.ref_blank_wls.copy()

                sort_idx = np.argsort(blank_x)
                bx_sorted = blank_x[sort_idx]
                by_sorted = self.ref_blank_counts[sort_idx]

                # Interpolar en la grilla común de corrimiento Raman
                blank_curve = np.interp(self.common_x, bx_sorted, by_sorted)
                for i in range(N):
                    Y_work[i, :] -= blank_curve
            else:
                # Blanco alternativo desde el lote
                b_idx = self.combo_blank_from_batch.currentIndex() - 1  # 0 es "(Ninguno)"
                if 0 <= b_idx < N:
                    blank_curve = Y_work[b_idx, :].copy()
                    for i in range(N):
                        Y_work[i, :] -= blank_curve

        elif b_strategy == 1:  # Modo 2: Cálculo Individual por Espectro (Algorítmico)
            algo_idx = self.combo_indiv_algo.currentIndex()
            if algo_idx == 0:  # AsLS
                lam = float(self.spin_asls_lambda.value())
                p = float(self.spin_asls_p.value())
                for i in range(N):
                    base = baseline_asls(Y_work[i, :], lam=lam, p=p)
                    Y_work[i, :] -= base
            elif algo_idx == 1:  # AirPLS
                lam = float(self.spin_asls_lambda.value())
                for i in range(N):
                    base = baseline_airpls(Y_work[i, :], lam=lam)
                    Y_work[i, :] -= base
            elif algo_idx == 2:  # ModPoly
                deg = int(self.spin_modpoly_order.value())
                for i in range(N):
                    base = baseline_modpoly(Y_work[i, :], poly_order=deg)
                    Y_work[i, :] -= base
            elif algo_idx == 3:  # Rolling Ball
                rad = int(self.spin_rolling_radius.value())
                for i in range(N):
                    base = baseline_rolling_ball(Y_work[i, :], radius=rad)
                    Y_work[i, :] -= base

        elif b_strategy == 2:  # Sin Corrección de Línea Base
            pass

        # 2. Suavizado en Lote si está activo
        if self.check_batch_smooth.isChecked():
            w = self.spin_batch_sg_win.value()
            if w % 2 == 0:
                w += 1
            for i in range(N):
                Y_work[i, :] = smooth_savgol(Y_work[i, :], window_length=w, polyorder=3)

        self.Y_corrected = Y_work.copy()

        # 3. Normalización Espectroscópica
        ref_p = float(self.spin_ref_peak.value())
        Y_norm = normalize_spectrum_matrix(self.common_x, self.Y_corrected, mode=self.norm_mode, ref_pos=ref_p)

        # 4. Cálculo de Desplazamiento Vertical para Cascada (Waterfall)
        if self.view_mode == "waterfall":
            ptp_ref = float(np.ptp(Y_norm)) if Y_norm.size > 0 else 1.0
            offset_step = (ptp_ref * (self.slider_waterfall.value() / 100.0))
            self.Y_displayed = np.zeros_like(Y_norm)
            for i in range(N):
                self.Y_displayed[i, :] = Y_norm[i, :] + i * offset_step
        else:
            self.Y_displayed = Y_norm.copy()

        # 5. Renderizado en Gráfico Principal
        self._render_main_plot()

        # 6. Actualizar Sub-Pestañas Cuantitativas
        self._update_mean_std_tab(Y_norm)
        self._update_kinetics_tab(Y_norm)
        self._update_heatmap_tab(Y_norm)
        self._update_pca_tab(Y_norm)

    # ── Renderizado Gráfico ───────────────────────────────────────────────────

    def _render_main_plot(self):
        self.plot_multi.clear()

        # Re-agregar cursores
        self.plot_multi.addItem(self.cursor_a)
        self.plot_multi.addItem(self.cursor_b)
        self.plot_multi.addItem(self.region_ab)

        N = self.Y_displayed.shape[0]
        for i in range(N):
            orig_idx = self.active_indices[i]
            sp_data = self.spectra_list[orig_idx]
            pen = pg.mkPen(sp_data["color"], width=1.6)
            self.plot_multi.plot(self.common_x, self.Y_displayed[i, :], pen=pen, name=sp_data["name"])

        self._on_cursors_moved()

    def _on_region_ab_dragged(self):
        region = self.region_ab.getRegion()
        if not region or len(region) < 2:
            return
        min_x, max_x = float(min(region)), float(max(region))
        self.cursor_a.blockSignals(True)
        self.cursor_b.blockSignals(True)
        self.cursor_a.setValue(min_x)
        self.cursor_b.setValue(max_x)
        self.cursor_a.blockSignals(False)
        self.cursor_b.blockSignals(False)
        self._on_cursors_moved(from_region=True)

    def _on_cursors_moved(self, from_region: bool = False):
        pos_a = float(self.cursor_a.value())
        pos_b = float(self.cursor_b.value())
        x_min = min(pos_a, pos_b)
        x_max = max(pos_a, pos_b)

        if not from_region:
            self.region_ab.blockSignals(True)
            self.region_ab.setRegion([x_min, x_max])
            self.region_ab.blockSignals(False)

        self.lbl_cursor_metrics.setText(
            f"<b>Regla A:</b> {pos_a:.2f} cm⁻¹ | <b>Regla B:</b> {pos_b:.2f} cm⁻¹ | <b>ΔX:</b> {abs(pos_b - pos_a):.2f} cm⁻¹"
        )

        # Actualizar cinética si la pestaña está activa
        if self.tabs_views.currentIndex() == 2:
            ref_p = float(self.spin_ref_peak.value())
            Y_norm = normalize_spectrum_matrix(self.common_x, self.Y_corrected, mode=self.norm_mode, ref_pos=ref_p)
            self._update_kinetics_tab(Y_norm)

    def _update_mean_std_tab(self, Y_norm: np.ndarray):
        self.plot_mean.clear()
        if Y_norm.size == 0 or len(self.common_x) == 0:
            return

        mean_y, std_y, rsd = compute_mean_std_spectrum(Y_norm)

        # Curva de media y relleno de dispersión
        upper = self.plot_mean.plot(self.common_x, mean_y + std_y, pen=pg.mkPen(None))
        lower = self.plot_mean.plot(self.common_x, mean_y - std_y, pen=pg.mkPen(None))
        fill = pg.FillBetweenItem(lower, upper, brush=pg.mkBrush(137, 180, 250, 65))
        self.plot_mean.addItem(fill)

        self.plot_mean.plot(self.common_x, mean_y, pen=pg.mkPen("#89B4FA", width=2.5), name="Espectro Promedio")

        # Métricas de RSD%
        mean_rsd = float(np.mean(rsd)) if len(rsd) > 0 else 0.0
        pos_a = float(self.cursor_a.value())
        idx_a = int(np.argmin(np.abs(self.common_x - pos_a))) if len(self.common_x) > 0 else 0
        rsd_at_a = float(rsd[idx_a]) if len(rsd) > idx_a else 0.0

        self.lbl_reproducibility.setText(
            f"<b>RSD% Promedio Global:</b> {mean_rsd:.2f}% | <b>RSD% en Cursor A ({pos_a:.1f} cm⁻¹):</b> {rsd_at_a:.2f}%"
        )

    def _update_kinetics_tab(self, Y_norm: np.ndarray):
        self.plot_kinetics.clear()
        if Y_norm.size == 0 or len(self.common_x) == 0:
            return

        pos_a = float(self.cursor_a.value())
        pos_b = float(self.cursor_b.value())
        kin = extract_band_kinetics(self.common_x, Y_norm, pos_a, pos_b)

        indices = np.arange(1, len(kin["heights"]) + 1)
        self.plot_kinetics.plot(
            indices, kin["heights"],
            pen=pg.mkPen("#F38BA8", width=2.0), symbol="o", symbolBrush=pg.mkBrush("#F38BA8"), name="Altura Máxima"
        )
        self.plot_kinetics.plot(
            indices, kin["areas"],
            pen=pg.mkPen("#A6E3A1", width=2.0, style=Qt.PenStyle.DashLine), symbol="s", symbolBrush=pg.mkBrush("#A6E3A1"), name="Área Integrada"
        )

    def _update_heatmap_tab(self, Y_norm: np.ndarray):
        if Y_norm.size == 0 or len(self.common_x) == 0:
            self.heatmap_item.clear()
            return

        # PyQtGraph ImageItem toma matriz (X, Y)
        # Transponer para que el eje horizontal sea Raman Shift y vertical sea el índice
        N, M = Y_norm.shape
        self.heatmap_item.setImage(Y_norm.T)

        # Escalar coordenadas físicas
        x0 = float(self.common_x[0])
        dx = float((self.common_x[-1] - self.common_x[0]) / max(1, M - 1))
        self.heatmap_item.setRect(QtCore.QRectF(x0, 0, float(self.common_x[-1] - self.common_x[0]), N))

    def _update_pca_tab(self, Y_norm: np.ndarray):
        self.plot_pca_scores.clear()
        self.plot_pca_loadings.clear()
        if Y_norm.shape[0] < 2 or Y_norm.shape[1] < 2:
            self.lbl_pca_info.setText("Se requieren al menos 2 espectros activos para PCA.")
            return

        pca = compute_spectral_pca(Y_norm, n_components=2)
        scores = pca["scores"]
        loadings = pca["loadings"]
        exp_var = pca["explained_variance"]

        # Score plot
        scatter = pg.ScatterPlotItem(
            x=scores[:, 0], y=scores[:, 1],
            size=11, pen=pg.mkPen("#11111B", width=1), brush=pg.mkBrush("#F5C2E7")
        )
        self.plot_pca_scores.addItem(scatter)

        # Añadir etiquetas con el nombre de cada espectro
        for i in range(len(scores)):
            orig_idx = self.active_indices[i]
            sp_name = self.spectra_list[orig_idx]["name"]
            txt = pg.TextItem(sp_name, color="#CDD6F4", anchor=(0.5, -0.5))
            txt.setPos(scores[i, 0], scores[i, 1])
            self.plot_pca_scores.addItem(txt)

        # Loadings plot
        if loadings.shape[0] >= 1:
            self.plot_pca_loadings.plot(self.common_x, loadings[0, :], pen=pg.mkPen("#89B4FA", width=2.0), name="PC1 Loading")
        if loadings.shape[0] >= 2:
            self.plot_pca_loadings.plot(self.common_x, loadings[1, :], pen=pg.mkPen("#FAB387", width=2.0), name="PC2 Loading")

        v1 = exp_var[0] if len(exp_var) > 0 else 0.0
        v2 = exp_var[1] if len(exp_var) > 1 else 0.0
        self.lbl_pca_info.setText(
            f"<b>Varianza Explicada:</b> PC1 = {v1:.1f}% | PC2 = {v2:.1f}% | <b>Total Acumulado:</b> {v1 + v2:.1f}%"
        )

    # ── Exportación ───────────────────────────────────────────────────────────

    def _on_export_csv(self):
        if self.Y_displayed.size == 0 or len(self.common_x) == 0:
            QMessageBox.warning(self, "Sin datos", "No hay matriz de espectros para exportar.")
            return

        out_path, _ = QFileDialog.getSaveFileName(
            self, "Exportar Matriz Multi-Espectro", "Raman_MultiSpectra_Matrix.csv",
            "Archivos CSV (*.csv);;Archivos de Texto (*.txt)"
        )
        if not out_path:
            return

        try:
            # Construir matriz de datos: Primera columna = Corrimiento Raman, columnas siguientes = cada espectro
            N = len(self.active_indices)
            header_cols = ["Raman_Shift_cm-1"] + [self.spectra_list[idx]["name"].replace(",", "_") for idx in self.active_indices]
            header = ",".join(header_cols)

            matrix_out = np.column_stack([self.common_x] + [self.Y_displayed[i, :] for i in range(N)])
            np.savetxt(out_path, matrix_out, delimiter=",", header=header, comments="", fmt="%.4f" + ",%.4f" * N)
            QMessageBox.information(self, "Exportación Exitosa", f"Matriz exportada correctamente en:\n{out_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error de Exportación", f"No se pudo exportar la matriz:\n{e}")

    def _on_copy_tsv(self):
        if self.Y_displayed.size == 0 or len(self.common_x) == 0:
            return

        N = len(self.active_indices)
        header_cols = ["Raman_Shift_cm-1"] + [self.spectra_list[idx]["name"] for idx in self.active_indices]
        lines = ["\t".join(header_cols)]

        M = len(self.common_x)
        for j in range(M):
            row_vals = [f"{self.common_x[j]:.2f}"] + [f"{self.Y_displayed[i, j]:.4f}" for i in range(N)]
            lines.append("\t".join(row_vals))

        tsv_text = "\n".join(lines)
        QApplication.clipboard().setText(tsv_text)
        if self.parent_analyzer and hasattr(self.parent_analyzer, "statusBar"):
            self.parent_analyzer.statusBar().showMessage(f"Matriz de {N} espectros x {M} puntos copiada al portapapeles (TSV).", 4000)
        elif os.environ.get("QT_QPA_PLATFORM") != "offscreen":
            QMessageBox.information(self, "Copiado", "Matriz completa copiada al portapapeles en formato TSV (OriginLab / Excel).")
