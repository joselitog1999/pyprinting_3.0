"""
sif_analyzer.py
===============
Analizador y Procesador Avanzado de Espectros .SIF (Andor Solis).
Aplicación gráfica profesional en PyQt6 + PyQtGraph (Tema Catppuccin Mocha).

Arquitectura por Ventanas de Proceso Separadas:
- Ventana 1 (⬛ 1. Ruido / Dark): Visualización 1D/2D de ruido, filtros normales, Wiener/PSD y estadísticas.
- Ventana 2 (💡 2. Referencia): Sub-vistas 1D y 2D, ROI vertical, resta de ruido, comparador de referencias y métricas.
- Ventana 3 (🔴 3. Live / Señal): Sub-vistas 1D y 2D, selector de muestra del lote, resta de ruido, filtros y ROI.
- Ventana 4 (📊 4. Transmisión): Comparación T_calc vs T_meas, cálculo 2D Ruta A vs Ruta B, Noise Gate y post-suavizado.
- Ventana 5 (🔬 5. Extinción y Ajuste): Extinción (A = -log10(T) o 1-T), ajuste de picos (Gauss, Lorentz, Fano) con
  reglas arrastrables en el espectro y cálculo de incertidumbre combinada u_c(lambda) considerando ranura y píxeles.
- Archivo Maestro (👑 Maestro): Detección e importación en lote donde el archivo con 4 canales comparte ruido y ref.
- Panel Derecho: Opciones generales, instrumental (torreta de objetivos, dispersión externa) y exportación científica.
"""

import os
import sys
import numpy as np
from typing import Dict, List, Optional, Tuple, Any

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QGroupBox, QLabel, QPushButton, QComboBox, QCheckBox,
    QSpinBox, QDoubleSpinBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QFileDialog, QMessageBox, QTabWidget, QScrollArea, QFrame,
    QRadioButton, QButtonGroup, QStatusBar, QLineEdit, QDialog
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QColor, QFont, QIcon, QAction

import pyqtgraph as pg
import pyqtgraph.exporters as pg_export

# Configuración global de PyQtGraph para apariencia oscura premium
pg.setConfigOption('background', '#181825')
pg.setConfigOption('foreground', '#cdd6f4')
pg.setConfigOption('antialias', True)

# Importar motor científico
try:
    from core.sif_processor import (
        read_sif_file,
        parse_all_sif_channels,
        spatial_roi_reduce,
        set_average,
        roi_and_set_average,
        apply_spectral_filter,
        filter_wiener_adaptive,
        filter_despike_adaptive,
        filter_despike_median,
        estimate_photonic_noise,
        compute_transmittance,
        compute_transmittance_with_errors,
        compute_transmittance_dual_route,
        fit_peak_advanced,
        compute_extinction,
        compute_residuals,
        export_spectrum_txt,
        compute_wavelength_uncertainty,
        load_external_calibration_file,
        characterize_background_noise,
        _extract_wavelength_axis,
        NoiseProfile,
        SifSpectrum,
        SifMetadata,
        MICROSCOPE_OBJECTIVES,
        CCD_PIXEL_PITCH_UM
    )
except ImportError:
    from sif_processor import (
        read_sif_file,
        parse_all_sif_channels,
        spatial_roi_reduce,
        set_average,
        roi_and_set_average,
        apply_spectral_filter,
        filter_wiener_adaptive,
        filter_despike_adaptive,
        filter_despike_median,
        estimate_photonic_noise,
        compute_transmittance,
        compute_transmittance_with_errors,
        compute_transmittance_dual_route,
        fit_peak_advanced,
        compute_extinction,
        compute_residuals,
        export_spectrum_txt,
        compute_wavelength_uncertainty,
        load_external_calibration_file,
        characterize_background_noise,
        _extract_wavelength_axis,
        NoiseProfile,
        SifSpectrum,
        SifMetadata,
        MICROSCOPE_OBJECTIVES,
        CCD_PIXEL_PITCH_UM
    )


# ==============================================================================
# HOJA DE ESTILOS CSS - CATPPUCCIN MOCHA PREMIUM
# ==============================================================================
DARK_THEME_QSS = """
QMainWindow, QWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-family: 'Segoe UI', 'Inter', -apple-system, sans-serif;
    font-size: 12px;
}
QGroupBox {
    border: 1px solid #313244;
    border-radius: 8px;
    margin-top: 10px;
    padding-top: 10px;
    font-weight: bold;
    color: #cba6f7;
    background-color: #181825;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 5px;
}
QPushButton {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 5px 12px;
    font-weight: 500;
}
QPushButton:hover {
    background-color: #45475a;
    border-color: #585b70;
}
QPushButton:pressed {
    background-color: #585b70;
}
QPushButton#primaryBtn {
    background-color: #89b4fa;
    color: #11111b;
    font-weight: bold;
    border: none;
}
QPushButton#primaryBtn:hover {
    background-color: #b4befe;
}
QPushButton#accentBtn {
    background-color: #a6e3a1;
    color: #11111b;
    font-weight: bold;
    border: none;
}
QPushButton#accentBtn:hover {
    background-color: #94e2d5;
}
QPushButton#masterBtn {
    background-color: #f9e2af;
    color: #11111b;
    font-weight: bold;
    border: none;
}
QPushButton#masterBtn:hover {
    background-color: #fab387;
}
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {
    background-color: #181825;
    border: 1px solid #313244;
    border-radius: 5px;
    padding: 3px 8px;
    color: #cdd6f4;
}
QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus {
    border: 1px solid #89b4fa;
}
QComboBox::drop-down {
    border: none;
    width: 20px;
}
QTableWidget {
    background-color: #181825;
    border: 1px solid #313244;
    border-radius: 6px;
    gridline-color: #313244;
    selection-background-color: #45475a;
    selection-color: #cdd6f4;
}
QHeaderView::section {
    background-color: #11111b;
    color: #bac2de;
    padding: 4px 6px;
    border: none;
    border-bottom: 1px solid #313244;
    font-weight: bold;
}
QTabWidget::pane {
    border: 1px solid #313244;
    border-radius: 8px;
    background-color: #181825;
    top: -1px;
}
QTabBar::tab {
    background-color: #11111b;
    color: #a6adc8;
    padding: 8px 16px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    border: 1px solid #313244;
    border-bottom: none;
    margin-right: 3px;
    font-weight: bold;
}
QTabBar::tab:selected {
    background-color: #181825;
    color: #89b4fa;
    border-bottom: 2px solid #89b4fa;
}
QTabBar::tab:hover:!selected {
    background-color: #1e1e2e;
    color: #cdd6f4;
}
QCheckBox {
    spacing: 6px;
}
QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border-radius: 3px;
    border: 1px solid #45475a;
    background-color: #181825;
}
QCheckBox::indicator:checked {
    background-color: #89b4fa;
    border-color: #89b4fa;
}
QRadioButton::indicator {
    width: 14px;
    height: 14px;
    border-radius: 7px;
    border: 1px solid #45475a;
    background-color: #181825;
}
QRadioButton::indicator:checked {
    background-color: #a6e3a1;
    border-color: #a6e3a1;
}
QScrollBar:vertical {
    border: none;
    background: #181825;
    width: 10px;
    margin: 0px;
}
QScrollBar::handle:vertical {
    background: #313244;
    min-height: 20px;
    border-radius: 5px;
}
QScrollBar::handle:vertical:hover {
    background: #45475a;
}
"""


# ==============================================================================
# DIÁLOGO DE CARACTERIZACIÓN Y PSD DE RUIDO
# ==============================================================================
class NoisePsdDialog(QDialog):
    """Diálogo modal interactivo para inspección de la Densidad Espectral de Potencia (PSD) del Ruido."""
    def __init__(self, noise_profile: NoiseProfile, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Espectro y Caracterización de Ruido de Fondo (PSD) — Andor CCD")
        self.resize(800, 560)
        self.setStyleSheet(DARK_THEME_QSS)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        lbl_info = QLabel(
            f"<b>Offset Térmico/Bias Medio:</b> {noise_profile.mean_counts:.2f} cuentas | "
            f"<b>Desvío Estándar Total σ_BG:</b> {noise_profile.std_counts:.3f} cuentas | "
            f"<b>Líneas/Muestras:</b> {noise_profile.num_samples}"
        )
        lbl_info.setStyleSheet("color: #89b4fa; font-size: 12px; margin-bottom: 4px;")
        layout.addWidget(lbl_info)

        splitter = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(splitter, stretch=1)

        plot_psd = pg.PlotWidget(title="Densidad Espectral de Potencia del Ruido (PSD)")
        plot_psd.showGrid(x=True, y=True, alpha=0.3)
        plot_psd.setLabel('bottom', "Frecuencia Espacial Normalizada", units='ciclos/px')
        plot_psd.setLabel('left', "Potencia Espectral (PSD)", units='cuentas²/px')
        plot_psd.setLogMode(x=False, y=True)
        pen_psd = pg.mkPen('#89dceb', width=1.8)
        plot_psd.plot(noise_profile.psd_freqs, np.maximum(1e-12, noise_profile.noise_psd), pen=pen_psd)
        splitter.addWidget(plot_psd)

        plot_sigma = pg.PlotWidget(title="Desvío Estándar de Ruido a lo largo del Sensor σ_BG(píxel)")
        plot_sigma.showGrid(x=True, y=True, alpha=0.3)
        plot_sigma.setLabel('bottom', "Índice de Píxel Horizontal")
        plot_sigma.setLabel('left', "Incertidumbre Local σ_BG", units='cuentas')
        pen_sig = pg.mkPen('#f9e2af', width=1.5)
        plot_sigma.plot(noise_profile.noise_std_spectral, pen=pen_sig)
        splitter.addWidget(plot_sigma)

        btn_close = QPushButton("Cerrar")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignRight)


# ==============================================================================
# VENTANA PRINCIPAL DEL ANALIZADOR ESPECTRAL
# ==============================================================================
class SifAnalyzerWindow(QMainWindow):
    """
    Ventana principal del analizador y procesador SIF con 5 Ventanas de Proceso Separadas
    y Arquitectura de Archivo Maestro (👑 Maestro).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Analizador Espectral Multi-Canal SIF (Andor Solis) — PyPrinting 3.0")
        self.resize(1560, 960)
        self.setStyleSheet(DARK_THEME_QSS)

        # 1. Estado en memoria
        self.loaded_spectra: List[SifSpectrum] = []
        self.active_index: int = -1
        self.master_spectrum: Optional[SifSpectrum] = None

        # Roles y perfiles
        self.current_noise_profile: Optional[NoiseProfile] = None
        self.custom_calib_wavelengths: Optional[np.ndarray] = None
        self.custom_calib_source: str = ""

        # Datos procesados en caché para el espectro activo
        self.current_dark_1d: Optional[np.ndarray] = None
        self.current_ref_1d: Optional[np.ndarray] = None
        self.current_live_1d: Optional[np.ndarray] = None
        self.current_t_calc: Optional[np.ndarray] = None
        self.current_t_meas: Optional[np.ndarray] = None
        self.current_t_route_a: Optional[np.ndarray] = None
        self.current_t_route_b: Optional[np.ndarray] = None
        self.current_sigma_t: Optional[np.ndarray] = None
        self.current_extinction: Optional[np.ndarray] = None
        self.current_residuals: Optional[np.ndarray] = None
        self.last_peak_fit_results: Optional[Dict[str, Any]] = None

        # 2. Construcción de Interfaz
        self._setup_menus()
        self._setup_ui()
        self._setup_crosshairs()

        # Timer para recálculos reactivos suaves (25 fps max)
        self.recalc_timer = QTimer(self)
        self.recalc_timer.setSingleShot(True)
        self.recalc_timer.setInterval(40)
        self.recalc_timer.timeout.connect(self._recalculate_all)

        self.statusBar().showMessage("Listo. Cargue uno o más archivos .sif para comenzar.")

    # ==========================================================================
    # MENÚS Y ACCIONES
    # ==========================================================================
    def _setup_menus(self):
        menubar = self.menuBar()

        menu_file = menubar.addMenu("Archivo")
        act_open_file = QAction("📂 Abrir Archivo .SIF...", self)
        act_open_file.setShortcut("Ctrl+O")
        act_open_file.triggered.connect(self._on_open_single_file)
        menu_file.addAction(act_open_file)

        act_open_dir = QAction("📁 Cargar Carpeta / Lote de Archivos...", self)
        act_open_dir.setShortcut("Ctrl+Shift+O")
        act_open_dir.triggered.connect(self._on_open_folder)
        menu_file.addAction(act_open_dir)

        menu_file.addSeparator()
        act_export_dat = QAction("💾 Exportar Espectro Activo (.dat)...", self)
        act_export_dat.setShortcut("Ctrl+S")
        act_export_dat.triggered.connect(self._on_export_active_curves)
        menu_file.addAction(act_export_dat)

        act_export_batch = QAction("📦 Exportación Completa en Lote...", self)
        act_export_batch.triggered.connect(self._on_export_batch_set)
        menu_file.addAction(act_export_batch)

        act_export_img = QAction("📷 Exportar Gráfico como Imagen (PNG/SVG)...", self)
        act_export_img.triggered.connect(self._on_export_plot_image)
        menu_file.addAction(act_export_img)

        menu_file.addSeparator()
        act_clear = QAction("🧹 Limpiar Todo", self)
        act_clear.triggered.connect(self._on_clear_all)
        menu_file.addAction(act_clear)

        menu_tools = menubar.addMenu("Herramientas")
        act_auto_roles = QAction("🎯 Auto-asignar Roles Heurísticos", self)
        act_auto_roles.triggered.connect(self._on_auto_assign_roles)
        menu_tools.addAction(act_auto_roles)

    # ==========================================================================
    # CONSTRUCCIÓN DE LA INTERFAZ PRINCIPAL
    # ==========================================================================
    def _setup_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.main_splitter)

        # 1. Panel Izquierdo: Gestor de Archivos y Maestro
        left_widget = self._create_left_panel()
        self.main_splitter.addWidget(left_widget)

        # 2. Panel Central: 5 Ventanas de Proceso Separadas
        center_widget = self._create_center_process_tabs()
        self.main_splitter.addWidget(center_widget)

        # 3. Panel Derecho: Opciones Generales, Instrumento y Exportación
        right_widget = self._create_right_panel()
        self.main_splitter.addWidget(right_widget)

        # Proporciones: Izq 22%, Centro 56%, Der 22%
        self.main_splitter.setSizes([340, 880, 340])

    # --------------------------------------------------------------------------
    # PANEL IZQUIERDO: ARCHIVO MAESTRO, ARCHIVOS Y METADATOS
    # --------------------------------------------------------------------------
    def _create_left_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Tarjeta de Archivo Maestro
        grp_master = QGroupBox("👑 Archivo Maestro del Lote")
        vbox_master = QVBoxLayout(grp_master)
        self.lbl_master_status = QLabel("Maestro: Ninguno asignado")
        self.lbl_master_status.setStyleSheet("color: #f9e2af; font-weight: bold; font-size: 11px;")
        self.lbl_master_channels = QLabel("Canales: --")
        self.lbl_master_channels.setStyleSheet("color: #a6adc8; font-size: 11px;")
        vbox_master.addWidget(self.lbl_master_status)
        vbox_master.addWidget(self.lbl_master_channels)

        self.btn_set_master = QPushButton("👑 Designar como Maestro")
        self.btn_set_master.setObjectName("masterBtn")
        self.btn_set_master.setToolTip("Designa el archivo seleccionado como Maestro para compartir Referencia y Ruido con los demás archivos.")
        self.btn_set_master.clicked.connect(self._on_designate_master_clicked)
        vbox_master.addWidget(self.btn_set_master)
        layout.addWidget(grp_master)

        # Grupo: Gestor de Archivos
        grp_files = QGroupBox("Gestor de Archivos SIF")
        vbox_files = QVBoxLayout(grp_files)

        btn_row = QHBoxLayout()
        self.btn_add_file = QPushButton("📂 Añadir .SIF")
        self.btn_add_file.setObjectName("primaryBtn")
        self.btn_add_file.clicked.connect(self._on_open_single_file)
        self.btn_add_folder = QPushButton("📁 Cargar Carpeta")
        self.btn_add_folder.clicked.connect(self._on_open_folder)
        btn_row.addWidget(self.btn_add_file)
        btn_row.addWidget(self.btn_add_folder)
        vbox_files.addLayout(btn_row)

        self.table_files = QTableWidget()
        self.table_files.setColumnCount(4)
        self.table_files.setHorizontalHeaderLabels(["Sel", "Archivo", "Canales", "Rol / Estado"])
        self.table_files.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table_files.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table_files.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table_files.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table_files.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_files.cellClicked.connect(self._on_file_row_clicked)
        vbox_files.addWidget(self.table_files)

        row_aux = QHBoxLayout()
        self.btn_remove_file = QPushButton("Eliminar")
        self.btn_remove_file.clicked.connect(self._on_remove_selected_file)
        self.btn_auto_roles = QPushButton("Auto-Roles")
        self.btn_auto_roles.clicked.connect(self._on_auto_assign_roles)
        row_aux.addWidget(self.btn_remove_file)
        row_aux.addWidget(self.btn_auto_roles)
        vbox_files.addLayout(row_aux)

        layout.addWidget(grp_files, stretch=3)

        # Grupo: Metadatos del Espectro Activo
        grp_meta = QGroupBox("Metadatos del Espectro Activo")
        vbox_meta = QVBoxLayout(grp_meta)
        self.lbl_meta_exp = QLabel("Exposición: --")
        self.lbl_meta_slit = QLabel("Ranura (Slit): --")
        self.lbl_meta_temp = QLabel("Temp Detector: --")
        self.lbl_meta_bin = QLabel("Binning: --")
        self.lbl_meta_gain = QLabel("Ganancia EM: --")
        self.lbl_meta_type = QLabel("Tipo Datos: --")
        self.lbl_meta_channels = QLabel("Canales detectados: --")
        for lbl in [self.lbl_meta_exp, self.lbl_meta_slit, self.lbl_meta_temp,
                    self.lbl_meta_bin, self.lbl_meta_gain, self.lbl_meta_type,
                    self.lbl_meta_channels]:
            lbl.setStyleSheet("color: #bac2de; font-size: 11px;")
            vbox_meta.addWidget(lbl)
        layout.addWidget(grp_meta, stretch=2)

        return widget

    # --------------------------------------------------------------------------
    # PANEL CENTRAL: 5 VENTANAS DE PROCESO SEPARADAS
    # --------------------------------------------------------------------------
    def _create_center_process_tabs(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.tabs_process = QTabWidget()
        layout.addWidget(self.tabs_process)

        # Ventana 1: Ruido / Dark
        tab_dark = self._create_dark_tab()
        self.tabs_process.addTab(tab_dark, "⬛ 1. Ruido / Dark")

        # Ventana 2: Referencia
        tab_ref = self._create_ref_tab()
        self.tabs_process.addTab(tab_ref, "💡 2. Referencia")

        # Ventana 3: Live / Señal
        tab_live = self._create_live_tab()
        self.tabs_process.addTab(tab_live, "🔴 3. Live / Señal")

        # Ventana 4: Transmisión
        tab_trans = self._create_transmittance_tab()
        self.tabs_process.addTab(tab_trans, "📊 4. Transmisión")

        # Ventana 5: Extinción y Ajuste de Picos (LSPR / Fano)
        tab_ext = self._create_extinction_tab()
        self.tabs_process.addTab(tab_ext, "🔬 5. Extinción y Ajuste")

        self.tabs_process.currentChanged.connect(self._on_tab_changed)

        return widget

    # --------------------------------------------------------------------------
    # VENTANA 1: RUIDO / DARK
    # --------------------------------------------------------------------------
    def _create_dark_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Barra de controles pertinentes a RUIDO
        bar_dark = QHBoxLayout()
        self.lbl_dark_source = QLabel("Origen Ruido: --")
        self.lbl_dark_source.setStyleSheet("color: #f9e2af; font-weight: bold;")
        bar_dark.addWidget(self.lbl_dark_source)

        bar_dark.addStretch()

        self.chk_dark_despike = QCheckBox("Despike")
        self.chk_dark_despike.setChecked(True)
        self.chk_dark_despike.toggled.connect(self._schedule_recalculation)
        bar_dark.addWidget(self.chk_dark_despike)

        bar_dark.addWidget(QLabel("Filtro:"))
        self.combo_dark_filter = QComboBox()
        self.combo_dark_filter.addItems(["Ninguno", "Savitzky-Golay", "Fourier Lowpass", "Media Móvil"])
        self.combo_dark_filter.currentIndexChanged.connect(self._schedule_recalculation)
        bar_dark.addWidget(self.combo_dark_filter)

        bar_dark.addWidget(QLabel("Ventana:"))
        self.spin_dark_param = QSpinBox()
        self.spin_dark_param.setRange(3, 101)
        self.spin_dark_param.setSingleStep(2)
        self.spin_dark_param.setValue(15)
        self.spin_dark_param.valueChanged.connect(self._schedule_recalculation)
        bar_dark.addWidget(self.spin_dark_param)

        self.btn_dark_psd = QPushButton("🔍 Ver PSD")
        self.btn_dark_psd.clicked.connect(self._on_view_dark_psd)
        bar_dark.addWidget(self.btn_dark_psd)

        btn_auto_dark = QPushButton("Auto-Escala")
        btn_auto_dark.clicked.connect(lambda: self.plot_dark_1d.autoRange())
        bar_dark.addWidget(btn_auto_dark)

        layout.addLayout(bar_dark)

        # Splitter 2D y 1D para Ruido
        self.splitter_dark = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(self.splitter_dark, stretch=1)

        # Sub-panel 2D Ruido
        self.widget_dark_2d = QWidget()
        vbox_d2d = QVBoxLayout(self.widget_dark_2d)
        vbox_d2d.setContentsMargins(0, 0, 0, 0)
        self.plot_dark_2d = pg.PlotWidget(title="Mapa Espacial 2D de Ruido de Fondo")
        self.plot_dark_2d.setLabel('bottom', "Longitud de onda", units='nm')
        self.plot_dark_2d.setLabel('left', "Píxel vertical (Y)", units='px')
        self.img_dark_2d = pg.ImageItem()
        self.img_dark_2d.setColorMap(pg.colormap.get('viridis'))
        self.plot_dark_2d.addItem(self.img_dark_2d)
        vbox_d2d.addWidget(self.plot_dark_2d)
        self.splitter_dark.addWidget(self.widget_dark_2d)

        # Sub-panel 1D Ruido
        self.plot_dark_1d = pg.PlotWidget(title="Espectro 1D de Ruido (Cuentas vs Longitud de Onda)")
        self.plot_dark_1d.showGrid(x=True, y=True, alpha=0.3)
        self.plot_dark_1d.setLabel('bottom', "Longitud de onda", units='nm')
        self.plot_dark_1d.setLabel('left', "Cuentas de Ruido (Counts)")
        self.plot_dark_1d.addLegend(offset=(20, 20))
        self.splitter_dark.addWidget(self.plot_dark_1d)
        self.splitter_dark.setSizes([260, 440])

        # Tarjeta de métricas del ruido
        self.lbl_dark_metrics = QLabel("Métricas Ruido: Bias Medio: -- | Desvío σ_dark: -- | Mín: -- | Máx: --")
        self.lbl_dark_metrics.setStyleSheet("color: #89b4fa; font-weight: bold; background-color: #11111b; padding: 6px; border-radius: 5px;")
        layout.addWidget(self.lbl_dark_metrics)

        return widget

    # --------------------------------------------------------------------------
    # VENTANA 2: REFERENCIA
    # --------------------------------------------------------------------------
    def _create_ref_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Barra de controles pertinentes a REFERENCIA
        bar_ref = QHBoxLayout()
        self.lbl_ref_source = QLabel("Origen Referencia: --")
        self.lbl_ref_source.setStyleSheet("color: #fab387; font-weight: bold;")
        bar_ref.addWidget(self.lbl_ref_source)

        bar_ref.addWidget(QLabel("Fuente:"))
        self.combo_ref_source = QComboBox()
        self.combo_ref_source.addItems(["Auto (Propia o Maestro)", "Forzar Propia del Archivo", "Forzar 👑 Maestro"])
        self.combo_ref_source.currentIndexChanged.connect(self._schedule_recalculation)
        bar_ref.addWidget(self.combo_ref_source)

        bar_ref.addStretch()

        self.chk_ref_sub_dark = QCheckBox("Restar Ruido Dark")
        self.chk_ref_sub_dark.setChecked(True)
        self.chk_ref_sub_dark.toggled.connect(self._schedule_recalculation)
        bar_ref.addWidget(self.chk_ref_sub_dark)

        self.chk_ref_despike = QCheckBox("Despike")
        self.chk_ref_despike.setChecked(True)
        self.chk_ref_despike.toggled.connect(self._schedule_recalculation)
        bar_ref.addWidget(self.chk_ref_despike)

        self.chk_ref_adaptive = QCheckBox("Limpieza Adaptativa BG (Wiener)")
        self.chk_ref_adaptive.toggled.connect(self._schedule_recalculation)
        bar_ref.addWidget(self.chk_ref_adaptive)

        self.spin_ref_wiener_alpha = QDoubleSpinBox()
        self.spin_ref_wiener_alpha.setRange(0.1, 10.0)
        self.spin_ref_wiener_alpha.setSingleStep(0.1)
        self.spin_ref_wiener_alpha.setValue(1.0)
        self.spin_ref_wiener_alpha.setPrefix("α: ")
        self.spin_ref_wiener_alpha.setToolTip("Factor de sobre-sustracción espectral α para filtro de Wiener adaptativo")
        self.spin_ref_wiener_alpha.valueChanged.connect(self._schedule_recalculation)
        bar_ref.addWidget(self.spin_ref_wiener_alpha)

        bar_ref.addWidget(QLabel("Filtro:"))
        self.combo_ref_filter = QComboBox()
        self.combo_ref_filter.addItems(["Ninguno", "Savitzky-Golay", "Fourier Lowpass", "Media Móvil", "Wiener Adaptativo (BG)"])
        self.combo_ref_filter.currentIndexChanged.connect(self._schedule_recalculation)
        bar_ref.addWidget(self.combo_ref_filter)

        bar_ref.addWidget(QLabel("Ventana:"))
        self.spin_ref_param = QSpinBox()
        self.spin_ref_param.setRange(3, 101)
        self.spin_ref_param.setSingleStep(2)
        self.spin_ref_param.setValue(11)
        self.spin_ref_param.valueChanged.connect(self._schedule_recalculation)
        bar_ref.addWidget(self.spin_ref_param)

        bar_ref.addWidget(QLabel("ROI Y Min:"))
        self.spin_ref_ymin = QSpinBox()
        self.spin_ref_ymin.setRange(0, 2000)
        self.spin_ref_ymin.setValue(10)
        self.spin_ref_ymin.valueChanged.connect(self._on_ref_roi_spinners_changed)
        bar_ref.addWidget(self.spin_ref_ymin)

        bar_ref.addWidget(QLabel("ROI Y Max:"))
        self.spin_ref_ymax = QSpinBox()
        self.spin_ref_ymax.setRange(0, 2000)
        self.spin_ref_ymax.setValue(50)
        self.spin_ref_ymax.valueChanged.connect(self._on_ref_roi_spinners_changed)
        bar_ref.addWidget(self.spin_ref_ymax)

        bar_ref.addWidget(QLabel("Modo:"))
        self.combo_ref_roimode = QComboBox()
        self.combo_ref_roimode.addItems(["Promedio", "Suma"])
        self.combo_ref_roimode.currentIndexChanged.connect(self._schedule_recalculation)
        bar_ref.addWidget(self.combo_ref_roimode)

        btn_auto_ref = QPushButton("Auto-Escala")
        btn_auto_ref.clicked.connect(lambda: self.plot_ref_1d.autoRange())
        bar_ref.addWidget(btn_auto_ref)

        layout.addLayout(bar_ref)

        # Sub-pestañas: Vista Principal (1D/2D) y Comparador de Referencias
        self.tabs_ref_internal = QTabWidget()
        layout.addWidget(self.tabs_ref_internal, stretch=1)

        # Sub-tab A: 1D + 2D
        sub_ref_view = QWidget()
        vbox_rv = QVBoxLayout(sub_ref_view)
        vbox_rv.setContentsMargins(0, 0, 0, 0)
        self.splitter_ref = QSplitter(Qt.Orientation.Vertical)
        vbox_rv.addWidget(self.splitter_ref)

        # 2D Heatmap con LinearRegionItem
        self.widget_ref_2d = QWidget()
        vbox_r2d = QVBoxLayout(self.widget_ref_2d)
        vbox_r2d.setContentsMargins(0, 0, 0, 0)
        self.plot_ref_2d = pg.PlotWidget(title="Mapa 2D de Lámpara/Referencia (Seleccione ROI en Y)")
        self.plot_ref_2d.setLabel('bottom', "Longitud de onda", units='nm')
        self.plot_ref_2d.setLabel('left', "Píxel vertical (Y)", units='px')
        self.img_ref_2d = pg.ImageItem()
        self.img_ref_2d.setColorMap(pg.colormap.get('viridis'))
        self.plot_ref_2d.addItem(self.img_ref_2d)

        self.roi_ref_region = pg.LinearRegionItem(
            values=[10, 50],
            orientation=pg.LinearRegionItem.Horizontal,
            brush=pg.mkBrush(250, 179, 135, 60),
            pen=pg.mkPen('#fab387', width=1.5)
        )
        self.roi_ref_region.sigRegionChanged.connect(self._on_ref_roi_region_changed)
        self.plot_ref_2d.addItem(self.roi_ref_region)
        vbox_r2d.addWidget(self.plot_ref_2d)
        self.splitter_ref.addWidget(self.widget_ref_2d)

        # 1D Spectrum
        self.plot_ref_1d = pg.PlotWidget(title="Espectro 1D de Referencia (Cuentas Promediadas en ROI)")
        self.plot_ref_1d.showGrid(x=True, y=True, alpha=0.3)
        self.plot_ref_1d.setLabel('bottom', "Longitud de onda", units='nm')
        self.plot_ref_1d.setLabel('left', "Cuentas de Referencia (Counts)")
        self.plot_ref_1d.addLegend(offset=(20, 20))
        self.splitter_ref.addWidget(self.plot_ref_1d)
        self.splitter_ref.setSizes([260, 440])

        self.tabs_ref_internal.addTab(sub_ref_view, "📊 Espectro y Región 2D")

        # Sub-tab B: Comparador de Referencias
        sub_ref_comp = QWidget()
        vbox_rc = QVBoxLayout(sub_ref_comp)
        self.plot_ref_compare = pg.PlotWidget(title="Comparador de Sets de Referencias")
        self.plot_ref_compare.showGrid(x=True, y=True, alpha=0.3)
        self.plot_ref_compare.setLabel('bottom', "Longitud de onda", units='nm')
        self.plot_ref_compare.setLabel('left', "Cuentas Normalizadas")
        self.plot_ref_compare.addLegend(offset=(20, 20))
        vbox_rc.addWidget(self.plot_ref_compare)
        self.tabs_ref_internal.addTab(sub_ref_comp, "📈 Comparador de Referencias")

        # Tarjeta de métricas de Referencia
        self.lbl_ref_metrics = QLabel("Métricas Referencia: Cuentas Medias ROI: -- | Pico Lámpara: -- | Desvío Espacial: --")
        self.lbl_ref_metrics.setStyleSheet("color: #fab387; font-weight: bold; background-color: #11111b; padding: 6px; border-radius: 5px;")
        layout.addWidget(self.lbl_ref_metrics)

        return widget

    # --------------------------------------------------------------------------
    # VENTANA 3: LIVE / SEÑAL
    # --------------------------------------------------------------------------
    def _create_live_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Barra de controles pertinentes a SEÑAL/LIVE
        bar_live = QHBoxLayout()
        bar_live.addWidget(QLabel("Muestra Activa:"))
        self.combo_live_sample = QComboBox()
        self.combo_live_sample.currentIndexChanged.connect(self._on_live_sample_selected)
        bar_live.addWidget(self.combo_live_sample)

        bar_live.addStretch()

        self.chk_live_sub_dark = QCheckBox("Restar Ruido Dark")
        self.chk_live_sub_dark.setChecked(True)
        self.chk_live_sub_dark.toggled.connect(self._schedule_recalculation)
        bar_live.addWidget(self.chk_live_sub_dark)

        self.chk_live_despike = QCheckBox("Despike")
        self.chk_live_despike.setChecked(True)
        self.chk_live_despike.toggled.connect(self._schedule_recalculation)
        bar_live.addWidget(self.chk_live_despike)

        self.chk_live_adaptive = QCheckBox("Limpieza Adaptativa BG (Wiener)")
        self.chk_live_adaptive.toggled.connect(self._schedule_recalculation)
        bar_live.addWidget(self.chk_live_adaptive)

        self.spin_live_wiener_alpha = QDoubleSpinBox()
        self.spin_live_wiener_alpha.setRange(0.1, 10.0)
        self.spin_live_wiener_alpha.setSingleStep(0.1)
        self.spin_live_wiener_alpha.setValue(1.0)
        self.spin_live_wiener_alpha.setPrefix("α: ")
        self.spin_live_wiener_alpha.setToolTip("Factor de sobre-sustracción espectral α para filtro de Wiener adaptativo")
        self.spin_live_wiener_alpha.valueChanged.connect(self._schedule_recalculation)
        bar_live.addWidget(self.spin_live_wiener_alpha)

        bar_live.addWidget(QLabel("Filtro:"))
        self.combo_live_filter = QComboBox()
        self.combo_live_filter.addItems(["Ninguno", "Savitzky-Golay", "Fourier Lowpass", "Media Móvil", "Wiener Adaptativo (BG)"])
        self.combo_live_filter.currentIndexChanged.connect(self._schedule_recalculation)
        bar_live.addWidget(self.combo_live_filter)

        bar_live.addWidget(QLabel("Ventana:"))
        self.spin_live_param = QSpinBox()
        self.spin_live_param.setRange(3, 101)
        self.spin_live_param.setSingleStep(2)
        self.spin_live_param.setValue(11)
        self.spin_live_param.valueChanged.connect(self._schedule_recalculation)
        bar_live.addWidget(self.spin_live_param)

        bar_live.addWidget(QLabel("ROI Y Min:"))
        self.spin_live_ymin = QSpinBox()
        self.spin_live_ymin.setRange(0, 2000)
        self.spin_live_ymin.setValue(10)
        self.spin_live_ymin.valueChanged.connect(self._on_live_roi_spinners_changed)
        bar_live.addWidget(self.spin_live_ymin)

        bar_live.addWidget(QLabel("ROI Y Max:"))
        self.spin_live_ymax = QSpinBox()
        self.spin_live_ymax.setRange(0, 2000)
        self.spin_live_ymax.setValue(50)
        self.spin_live_ymax.valueChanged.connect(self._on_live_roi_spinners_changed)
        bar_live.addWidget(self.spin_live_ymax)

        bar_live.addWidget(QLabel("Modo:"))
        self.combo_live_roimode = QComboBox()
        self.combo_live_roimode.addItems(["Promedio", "Suma"])
        self.combo_live_roimode.currentIndexChanged.connect(self._schedule_recalculation)
        bar_live.addWidget(self.combo_live_roimode)

        btn_auto_live = QPushButton("Auto-Escala")
        btn_auto_live.clicked.connect(lambda: self.plot_live_1d.autoRange())
        bar_live.addWidget(btn_auto_live)

        layout.addLayout(bar_live)

        # Splitter 2D y 1D para Live/Señal
        self.splitter_live = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(self.splitter_live, stretch=1)

        # Sub-panel 2D
        self.widget_live_2d = QWidget()
        vbox_l2d = QVBoxLayout(self.widget_live_2d)
        vbox_l2d.setContentsMargins(0, 0, 0, 0)
        self.plot_live_2d = pg.PlotWidget(title="Mapa Espacial 2D de Live/Señal (Seleccione ROI en Y)")
        self.plot_live_2d.setLabel('bottom', "Longitud de onda", units='nm')
        self.plot_live_2d.setLabel('left', "Píxel vertical (Y)", units='px')
        self.img_live_2d = pg.ImageItem()
        self.img_live_2d.setColorMap(pg.colormap.get('viridis'))
        self.plot_live_2d.addItem(self.img_live_2d)

        self.roi_live_region = pg.LinearRegionItem(
            values=[10, 50],
            orientation=pg.LinearRegionItem.Horizontal,
            brush=pg.mkBrush(243, 139, 168, 60),
            pen=pg.mkPen('#f38ba8', width=1.5)
        )
        self.roi_live_region.sigRegionChanged.connect(self._on_live_roi_region_changed)
        self.plot_live_2d.addItem(self.roi_live_region)
        vbox_l2d.addWidget(self.plot_live_2d)
        self.splitter_live.addWidget(self.widget_live_2d)

        # Sub-panel 1D
        self.plot_live_1d = pg.PlotWidget(title="Espectro 1D de Señal / Muestra (Cuentas Promediadas en ROI)")
        self.plot_live_1d.showGrid(x=True, y=True, alpha=0.3)
        self.plot_live_1d.setLabel('bottom', "Longitud de onda", units='nm')
        self.plot_live_1d.setLabel('left', "Cuentas de Señal (Counts)")
        self.plot_live_1d.addLegend(offset=(20, 20))
        self.splitter_live.addWidget(self.plot_live_1d)
        self.splitter_live.setSizes([260, 440])

        # Tarjeta de métricas de Señal
        self.lbl_live_metrics = QLabel("Métricas Señal: Cuentas Medias ROI: -- | Cuentas Pico: -- | Relación Señal/Fondo (SBR): --")
        self.lbl_live_metrics.setStyleSheet("color: #f38ba8; font-weight: bold; background-color: #11111b; padding: 6px; border-radius: 5px;")
        layout.addWidget(self.lbl_live_metrics)

        return widget

    # --------------------------------------------------------------------------
    # VENTANA 4: TRANSMISIÓN
    # --------------------------------------------------------------------------
    def _create_transmittance_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Barra de controles pertinentes a TRANSMISIÓN
        bar_trans = QHBoxLayout()

        self.chk_show_tcalc = QCheckBox("T_calc (%)")
        self.chk_show_tcalc.setChecked(True)
        self.chk_show_tcalc.setStyleSheet("color: #a6e3a1; font-weight: bold;")
        self.chk_show_tcalc.toggled.connect(self._refresh_transmittance_plots)
        bar_trans.addWidget(self.chk_show_tcalc)

        self.chk_show_tmeas = QCheckBox("T_meas SIF (%)")
        self.chk_show_tmeas.setChecked(True)
        self.chk_show_tmeas.setStyleSheet("color: #89b4fa; font-weight: bold;")
        self.chk_show_tmeas.toggled.connect(self._refresh_transmittance_plots)
        bar_trans.addWidget(self.chk_show_tmeas)

        self.chk_show_ribbon = QCheckBox("Área de Error (±σ_T)")
        self.chk_show_ribbon.setChecked(True)
        self.chk_show_ribbon.setStyleSheet("color: #f9e2af;")
        self.chk_show_ribbon.toggled.connect(self._refresh_transmittance_plots)
        bar_trans.addWidget(self.chk_show_ribbon)

        bar_trans.addStretch()

        # Opciones de ruta de cálculo 2D
        bar_trans.addWidget(QLabel("Ruta 2D:"))
        self.radio_route_a = QRadioButton("Ruta A (Pixel 2D)")
        self.radio_route_a.setChecked(True)
        self.radio_route_a.setToolTip("Ruta A: Cálculo pixel a pixel en 2D y posterior promedio vertical en el ROI.")
        self.radio_route_a.toggled.connect(self._schedule_recalculation)
        self.radio_route_b = QRadioButton("Ruta B (Promedio ROI)")
        self.radio_route_b.setToolTip("Ruta B: Promedio espacial previo en el ROI de Live y Ref, y posterior cociente.")
        self.radio_route_b.toggled.connect(self._schedule_recalculation)
        bar_trans.addWidget(self.radio_route_a)
        bar_trans.addWidget(self.radio_route_b)

        self.chk_compare_routes = QCheckBox("Comparar A y B")
        self.chk_compare_routes.toggled.connect(self._refresh_transmittance_plots)
        bar_trans.addWidget(self.chk_compare_routes)

        bar_trans.addWidget(QLabel("Noise Gate:"))
        self.spin_trans_gate = QDoubleSpinBox()
        self.spin_trans_gate.setRange(0.0, 1000.0)
        self.spin_trans_gate.setValue(5.0)
        self.spin_trans_gate.valueChanged.connect(self._schedule_recalculation)
        bar_trans.addWidget(self.spin_trans_gate)

        self.chk_trans_adaptive = QCheckBox("Limpieza Adaptativa BG (Wiener)")
        self.chk_trans_adaptive.toggled.connect(self._schedule_recalculation)
        bar_trans.addWidget(self.chk_trans_adaptive)

        self.spin_trans_wiener_alpha = QDoubleSpinBox()
        self.spin_trans_wiener_alpha.setRange(0.1, 10.0)
        self.spin_trans_wiener_alpha.setSingleStep(0.1)
        self.spin_trans_wiener_alpha.setValue(1.0)
        self.spin_trans_wiener_alpha.setPrefix("α: ")
        self.spin_trans_wiener_alpha.setToolTip("Factor de sobre-sustracción espectral α para filtro de Wiener adaptativo")
        self.spin_trans_wiener_alpha.valueChanged.connect(self._schedule_recalculation)
        bar_trans.addWidget(self.spin_trans_wiener_alpha)

        bar_trans.addWidget(QLabel("Post-Filtro:"))
        self.combo_trans_filter = QComboBox()
        self.combo_trans_filter.addItems(["Ninguno", "Savitzky-Golay", "Fourier Lowpass", "Media Móvil", "Wiener Adaptativo (BG)"])
        self.combo_trans_filter.currentIndexChanged.connect(self._schedule_recalculation)
        bar_trans.addWidget(self.combo_trans_filter)

        self.spin_trans_param = QSpinBox()
        self.spin_trans_param.setRange(3, 101)
        self.spin_trans_param.setSingleStep(2)
        self.spin_trans_param.setValue(11)
        self.spin_trans_param.valueChanged.connect(self._schedule_recalculation)
        bar_trans.addWidget(self.spin_trans_param)

        btn_recalc = QPushButton("⚡ Recalcular")
        btn_recalc.setObjectName("primaryBtn")
        btn_recalc.clicked.connect(self._recalculate_all)
        bar_trans.addWidget(btn_recalc)

        layout.addLayout(bar_trans)

        # Splitter: Gráfico de Transmitancia (Arriba) y Gráfico de Residuos (Abajo)
        self.splitter_trans = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(self.splitter_trans, stretch=1)

        self.plot_trans_main = pg.PlotWidget(title="Transmitancia Óptica: T_calc vs T_meas")
        self.plot_trans_main.showGrid(x=True, y=True, alpha=0.3)
        self.plot_trans_main.setLabel('bottom', "Longitud de onda", units='nm')
        self.plot_trans_main.setLabel('left', "Transmitancia", units='%')
        self.plot_trans_main.addLegend(offset=(20, 20))
        self.splitter_trans.addWidget(self.plot_trans_main)

        self.plot_trans_residuals = pg.PlotWidget(title="Diferencia Residual (T_meas - T_calc)")
        self.plot_trans_residuals.showGrid(x=True, y=True, alpha=0.3)
        self.plot_trans_residuals.setLabel('bottom', "Longitud de onda", units='nm')
        self.plot_trans_residuals.setLabel('left', "Residuo ΔT", units='%')
        zero_line = pg.InfiniteLine(pos=0.0, angle=0, pen=pg.mkPen('#6c7086', style=Qt.PenStyle.DashLine))
        self.plot_trans_residuals.addItem(zero_line)
        self.splitter_trans.addWidget(self.plot_trans_residuals)
        self.splitter_trans.setSizes([480, 220])

        # Tarjeta de métricas de Transmisión
        self.lbl_trans_metrics = QLabel("Métricas Transmisión: T_media: -- | Mín: -- | Máx: -- | Discrepancia RMS: -- | Incertidumbre Media: --")
        self.lbl_trans_metrics.setStyleSheet("color: #a6e3a1; font-weight: bold; background-color: #11111b; padding: 6px; border-radius: 5px;")
        layout.addWidget(self.lbl_trans_metrics)

        return widget

    # --------------------------------------------------------------------------
    # VENTANA 5: EXTINCIÓN Y AJUSTE DE PICOS (LSPR / FANO)
    # --------------------------------------------------------------------------
    def _create_extinction_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Barra de controles pertinentes a EXTINCIÓN Y AJUSTE
        bar_ext = QHBoxLayout()

        bar_ext.addWidget(QLabel("Fórmula Extinción:"))
        self.combo_ext_formula = QComboBox()
        self.combo_ext_formula.addItems(["Absorbancia A = -log10(T/100)", "Extinción E = 1 - T/100"])
        self.combo_ext_formula.currentIndexChanged.connect(self._schedule_recalculation)
        bar_ext.addWidget(self.combo_ext_formula)

        bar_ext.addWidget(QLabel("Modelo Ajuste:"))
        self.combo_fit_model = QComboBox()
        self.combo_fit_model.addItems(["Gaussiano", "Lorentziano", "Resonancia de Fano"])
        bar_ext.addWidget(self.combo_fit_model)

        bar_ext.addWidget(QLabel("ROI λ Min:"))
        self.spin_fit_lmin = QDoubleSpinBox()
        self.spin_fit_lmin.setRange(200.0, 2500.0)
        self.spin_fit_lmin.setValue(600.0)
        self.spin_fit_lmin.setSingleStep(5.0)
        self.spin_fit_lmin.valueChanged.connect(self._on_fit_spinners_changed)
        bar_ext.addWidget(self.spin_fit_lmin)

        bar_ext.addWidget(QLabel("ROI λ Max:"))
        self.spin_fit_lmax = QDoubleSpinBox()
        self.spin_fit_lmax.setRange(200.0, 2500.0)
        self.spin_fit_lmax.setValue(750.0)
        self.spin_fit_lmax.setSingleStep(5.0)
        self.spin_fit_lmax.valueChanged.connect(self._on_fit_spinners_changed)
        bar_ext.addWidget(self.spin_fit_lmax)

        bar_ext.addWidget(QLabel("Ranura (µm):"))
        self.spin_fit_slit = QDoubleSpinBox()
        self.spin_fit_slit.setRange(10.0, 2500.0)
        self.spin_fit_slit.setValue(100.0)
        bar_ext.addWidget(self.spin_fit_slit)

        self.chk_ext_adaptive = QCheckBox("Limpieza Adaptativa BG (Wiener)")
        self.chk_ext_adaptive.toggled.connect(self._schedule_recalculation)
        bar_ext.addWidget(self.chk_ext_adaptive)

        self.spin_ext_wiener_alpha = QDoubleSpinBox()
        self.spin_ext_wiener_alpha.setRange(0.1, 10.0)
        self.spin_ext_wiener_alpha.setSingleStep(0.1)
        self.spin_ext_wiener_alpha.setValue(1.0)
        self.spin_ext_wiener_alpha.setPrefix("α: ")
        self.spin_ext_wiener_alpha.setToolTip("Factor de sobre-sustracción espectral α para filtro de Wiener adaptativo")
        self.spin_ext_wiener_alpha.valueChanged.connect(self._schedule_recalculation)
        bar_ext.addWidget(self.spin_ext_wiener_alpha)

        self.btn_run_fit = QPushButton("⚡ Ajustar Pico en ROI")
        self.btn_run_fit.setObjectName("accentBtn")
        self.btn_run_fit.clicked.connect(self._on_run_peak_fit)
        bar_ext.addWidget(self.btn_run_fit)

        self.btn_export_fit = QPushButton("💾 Exportar Ajuste")
        self.btn_export_fit.clicked.connect(self._on_export_peak_fit)
        bar_ext.addWidget(self.btn_export_fit)

        btn_auto_ext = QPushButton("Auto-Escala")
        btn_auto_ext.clicked.connect(lambda: self.plot_ext_main.autoRange())
        bar_ext.addWidget(btn_auto_ext)

        layout.addLayout(bar_ext)

        # Splitter: Gráfico de Extinción con Reglas Arrastrables (Arriba) y Residuos del Ajuste (Abajo)
        self.splitter_ext = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(self.splitter_ext, stretch=1)

        # Gráfico principal de extinción
        self.plot_ext_main = pg.PlotWidget(title="Espectro de Extinción Óptica y Ajuste de Resonancia Plasmónica")
        self.plot_ext_main.showGrid(x=True, y=True, alpha=0.3)
        self.plot_ext_main.setLabel('bottom', "Longitud de onda", units='nm')
        self.plot_ext_main.setLabel('left', "Extinción / Absorbancia")
        self.plot_ext_main.addLegend(offset=(20, 20))

        # Región arrastrable espectral para ajuste
        self.roi_spectral_fit = pg.LinearRegionItem(
            values=[600.0, 750.0],
            orientation=pg.LinearRegionItem.Vertical,
            brush=pg.mkBrush(203, 166, 247, 50),
            pen=pg.mkPen('#cba6f7', width=1.8)
        )
        self.roi_spectral_fit.sigRegionChanged.connect(self._on_fit_region_changed)
        self.plot_ext_main.addItem(self.roi_spectral_fit)
        self.splitter_ext.addWidget(self.plot_ext_main)

        # Gráfico de residuos del ajuste
        self.plot_ext_residuals = pg.PlotWidget(title="Residuos del Ajuste: Datos Experimentales - Modelo Ajustado")
        self.plot_ext_residuals.showGrid(x=True, y=True, alpha=0.3)
        self.plot_ext_residuals.setLabel('bottom', "Longitud de onda", units='nm')
        self.plot_ext_residuals.setLabel('left', "Residuo de Ajuste")
        zero_line_ext = pg.InfiniteLine(pos=0.0, angle=0, pen=pg.mkPen('#6c7086', style=Qt.PenStyle.DashLine))
        self.plot_ext_residuals.addItem(zero_line_ext)
        self.splitter_ext.addWidget(self.plot_ext_residuals)
        self.splitter_ext.setSizes([480, 220])

        # Tarjeta de resultados detallados del ajuste
        self.lbl_fit_results = QLabel(
            "Resultados del Ajuste: Seleccione el ROI espectral con las reglas arrastrables y presione '⚡ Ajustar Pico en ROI'."
        )
        self.lbl_fit_results.setWordWrap(True)
        self.lbl_fit_results.setStyleSheet(
            "color: #cba6f7; font-weight: bold; background-color: #11111b; padding: 8px; border-radius: 5px; font-size: 11px;"
        )
        layout.addWidget(self.lbl_fit_results)

        return widget

    # --------------------------------------------------------------------------
    # PANEL DERECHO: INSTRUMENTACIÓN, CALIBRACIÓN Y EXPORTACIÓN
    # --------------------------------------------------------------------------
    def _create_right_panel(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(8)

        # Grupo: Instrumentación Óptica y Escala
        grp_optics = QGroupBox("Instrumentación: Escala y Óptica")
        vbox_optics = QVBoxLayout(grp_optics)

        vbox_optics.addWidget(QLabel("Objetivo Microscopio:"))
        self.combo_objective = QComboBox()
        for obj_name in MICROSCOPE_OBJECTIVES.keys():
            self.combo_objective.addItem(obj_name)
        self.combo_objective.setCurrentIndex(0)
        self.combo_objective.currentIndexChanged.connect(self._on_objective_changed)
        vbox_optics.addWidget(self.combo_objective)

        first_obj = list(MICROSCOPE_OBJECTIVES.values())[0]
        self.lbl_pixel_scale = QLabel(f"Escala: {first_obj['pixel_scale_um']:.4f} µm/px | NA {first_obj['na']:.2f}")
        self.lbl_pixel_scale.setStyleSheet("color: #a6e3a1; font-weight: bold;")
        vbox_optics.addWidget(self.lbl_pixel_scale)

        vbox_optics.addWidget(QLabel("Calibración de Dispersión:"))
        self.lbl_calib_status = QLabel("Origen: SIF Nativo")
        self.lbl_calib_status.setStyleSheet("color: #89b4fa; font-size: 11px;")
        vbox_optics.addWidget(self.lbl_calib_status)

        h_calib = QHBoxLayout()
        self.btn_load_calib = QPushButton("📥 Calib (.txt)")
        self.btn_load_calib.clicked.connect(self._on_load_external_calib)
        self.btn_reset_calib = QPushButton("↺ Nativo")
        self.btn_reset_calib.clicked.connect(self._on_reset_calib)
        h_calib.addWidget(self.btn_load_calib)
        h_calib.addWidget(self.btn_reset_calib)
        vbox_optics.addLayout(h_calib)

        self.chk_calculate_errors = QCheckBox("Propagar Incertidumbres y Error Ribbon")
        self.chk_calculate_errors.setChecked(True)
        self.chk_calculate_errors.setStyleSheet("color: #f9e2af; font-weight: bold;")
        self.chk_calculate_errors.toggled.connect(self._schedule_recalculation)
        vbox_optics.addWidget(self.chk_calculate_errors)

        layout.addWidget(grp_optics)

        # Grupo: Exportación Científica
        grp_export = QGroupBox("Exportación Científica")
        vbox_export = QVBoxLayout(grp_export)

        self.btn_export_txt = QPushButton("💾 Exportar Curvas (.dat)")
        self.btn_export_txt.setObjectName("accentBtn")
        self.btn_export_txt.clicked.connect(self._on_export_active_curves)
        vbox_export.addWidget(self.btn_export_txt)

        self.btn_export_batch = QPushButton("📦 Exportar Todo el Lote")
        self.btn_export_batch.clicked.connect(self._on_export_batch_set)
        vbox_export.addWidget(self.btn_export_batch)

        self.btn_export_img = QPushButton("📷 Guardar Imagen (PNG/SVG)")
        self.btn_export_img.clicked.connect(self._on_export_plot_image)
        vbox_export.addWidget(self.btn_export_img)

        layout.addWidget(grp_export)

        # Grupo: Ayuda y Flujo
        grp_flow = QGroupBox("Flujo Metodológico")
        vbox_flow = QVBoxLayout(grp_flow)
        lbl_help = QLabel(
            "<b>1. Ruido / Dark:</b> Limpieza y filtro basal.<br>"
            "<b>2. Referencia:</b> ROI espacial de lámpara.<br>"
            "<b>3. Live / Señal:</b> ROI y resta de dark.<br>"
            "<b>4. Transmisión:</b> T_calc vs T_meas y Ruta 2D.<br>"
            "<b>5. Extinción:</b> Ajuste Gauss, Lorentz o Fano."
        )
        lbl_help.setStyleSheet("color: #a6adc8; font-size: 11px;")
        vbox_flow.addWidget(lbl_help)
        layout.addWidget(grp_flow)

        layout.addStretch()
        scroll.setWidget(container)
        return scroll

    # ==========================================================================
    # CROSSHAIRS INTERACTIVOS
    # ==========================================================================
    def _setup_crosshairs(self):
        self.vLine_trans = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen('#fab387', width=1, style=Qt.PenStyle.DashLine))
        self.hLine_trans = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen('#fab387', width=1, style=Qt.PenStyle.DashLine))
        self.plot_trans_main.addItem(self.vLine_trans, ignoreBounds=True)
        self.plot_trans_main.addItem(self.hLine_trans, ignoreBounds=True)
        self.plot_trans_main.scene().sigMouseMoved.connect(self._on_mouse_moved_trans)

    def _on_mouse_moved_trans(self, pos):
        if self.plot_trans_main.sceneBoundingRect().contains(pos):
            mousePoint = self.plot_trans_main.plotItem.vb.mapSceneToView(pos)
            x_val = mousePoint.x()
            y_val = mousePoint.y()
            self.vLine_trans.setPos(x_val)
            self.hLine_trans.setPos(y_val)
            self.statusBar().showMessage(f"Cursor Transmisión: λ = {x_val:.2f} nm  |  T = {y_val:.2f} %")

    # ==========================================================================
    # GESTIÓN DE ARCHIVOS Y REGLA DEL ARCHIVO MAESTRO
    # ==========================================================================
    def _on_open_single_file(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Abrir archivos SIF de Andor", "", "Archivos SIF (*.sif);;Todos (*.*)"
        )
        if paths:
            self._load_file_list(paths)

    def _on_open_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta con lote SIF")
        if folder:
            sif_files = [
                os.path.join(folder, f) for f in os.listdir(folder)
                if f.lower().endswith('.sif')
            ]
            if not sif_files:
                QMessageBox.warning(self, "Sin archivos", "No se encontraron archivos .sif en la carpeta.")
                return
            sif_files.sort()
            self._load_file_list(sif_files)

    def _load_file_list(self, paths: List[str]):
        added_count = 0
        newly_loaded = []
        for p in paths:
            try:
                spec = read_sif_file(p)
                self.loaded_spectra.append(spec)
                newly_loaded.append(spec)
                added_count += 1
            except Exception as e:
                QMessageBox.critical(self, "Error al leer SIF", f"Error cargando {os.path.basename(p)}:\n{str(e)}")

        if added_count > 0:
            # Buscar archivo maestro automático si no hay uno activo
            if self.master_spectrum is None:
                for s in self.loaded_spectra:
                    if s.is_master:
                        self.master_spectrum = s
                        break

            self._update_master_status_ui()
            self._rebuild_files_table()
            self._update_live_sample_combo()

            if self.active_index < 0:
                self._select_file_index(0)
            else:
                self._recalculate_all()

            self.statusBar().showMessage(f"Se cargaron {added_count} archivo(s) SIF exitosamente.")

    def _on_designate_master_clicked(self):
        row = self.table_files.currentRow()
        if 0 <= row < len(self.loaded_spectra):
            spec = self.loaded_spectra[row]
            self.master_spectrum = spec
            self._update_master_status_ui()
            self._rebuild_files_table()
            self._recalculate_all()
            self.statusBar().showMessage(f"Archivo maestro asignado: {spec.custom_name}")
        else:
            QMessageBox.information(self, "Designar Maestro", "Seleccione una fila en la tabla de archivos para designarla como Maestro.")

    def _update_master_status_ui(self):
        if self.master_spectrum is not None:
            ms = self.master_spectrum
            ch_list = list(ms.channels.keys())
            self.lbl_master_status.setText(f"👑 Maestro: {ms.custom_name}")
            self.lbl_master_channels.setText(f"Canales ({len(ch_list)}): {', '.join(ch_list)}")
            self.lbl_master_status.setStyleSheet("color: #a6e3a1; font-weight: bold; font-size: 11px;")
        else:
            self.lbl_master_status.setText("Maestro: Ninguno asignado")
            self.lbl_master_channels.setText("Canales: --")
            self.lbl_master_status.setStyleSheet("color: #f9e2af; font-weight: bold; font-size: 11px;")

    def _rebuild_files_table(self):
        self.table_files.blockSignals(True)
        self.table_files.setRowCount(len(self.loaded_spectra))

        for row, spec in enumerate(self.loaded_spectra):
            chk = QCheckBox()
            chk.setChecked(True)
            chk.stateChanged.connect(lambda state, r=row: self._schedule_recalculation())
            chk_widget = QWidget()
            chk_lay = QHBoxLayout(chk_widget)
            chk_lay.addWidget(chk)
            chk_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chk_lay.setContentsMargins(0, 0, 0, 0)
            self.table_files.setCellWidget(row, 0, chk_widget)

            # Nombre / Alias
            name_text = ("👑 " if spec is self.master_spectrum else "") + spec.custom_name
            item_name = QTableWidgetItem(name_text)
            if spec is self.master_spectrum:
                item_name.setForeground(QColor("#a6e3a1"))
                font = item_name.font()
                font.setBold(True)
                item_name.setFont(font)
            self.table_files.setItem(row, 1, item_name)

            # Canales
            ch_count = spec.channels_count
            item_ch = QTableWidgetItem(f"{ch_count} ch ({'2D' if spec.is_2d else '1D'})")
            item_ch.setFlags(item_ch.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table_files.setItem(row, 2, item_ch)

            # Rol / Estado
            role_desc = "👑 Maestro" if spec is self.master_spectrum else ("Muestra Completa" if ch_count == 4 else "Hereda Maestro")
            item_role = QTableWidgetItem(role_desc)
            item_role.setFlags(item_role.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if spec is self.master_spectrum:
                item_role.setForeground(QColor("#a6e3a1"))
            self.table_files.setItem(row, 3, item_role)

        self.table_files.blockSignals(False)

    def _update_live_sample_combo(self):
        self.combo_live_sample.blockSignals(True)
        self.combo_live_sample.clear()
        for i, s in enumerate(self.loaded_spectra):
            self.combo_live_sample.addItem(s.custom_name, i)
        if 0 <= self.active_index < self.combo_live_sample.count():
            self.combo_live_sample.setCurrentIndex(self.active_index)
        self.combo_live_sample.blockSignals(False)

    def _on_file_row_clicked(self, row: int, col: int):
        self._select_file_index(row)

    def _on_live_sample_selected(self, idx: int):
        if 0 <= idx < len(self.loaded_spectra):
            self._select_file_index(idx)

    def _select_file_index(self, index: int):
        if 0 <= index < len(self.loaded_spectra):
            self.active_index = index
            self.table_files.selectRow(index)
            spec = self.loaded_spectra[index]

            meta = spec.metadata
            self.lbl_meta_exp.setText(f"Exposición: {meta.exposure_time:.3f} s")
            self.lbl_meta_slit.setText(f"Ranura (Slit): {meta.slit_width_um:.0f} µm")
            self.lbl_meta_temp.setText(f"Temp Detector: {meta.detector_temp_c:.1f} °C")
            self.lbl_meta_bin.setText(f"Binning: X={meta.xbin}, Y={meta.ybin}")
            self.lbl_meta_gain.setText(f"Ganancia EM: {meta.em_gain:.1f}")
            self.lbl_meta_type.setText(f"Tipo Datos: {meta.data_type}")
            self.lbl_meta_channels.setText(f"Canales: {spec.channels_count} ({', '.join(spec.channels.keys())})")

            # Actualizar slit width en el ajuste de picos
            self.spin_fit_slit.setValue(meta.slit_width_um if meta.slit_width_um > 0 else 100.0)

            # Sincronizar combo de muestra en la ventana Live
            self.combo_live_sample.blockSignals(True)
            self.combo_live_sample.setCurrentIndex(index)
            self.combo_live_sample.blockSignals(False)

            self._recalculate_all()

    def _on_remove_selected_file(self):
        row = self.table_files.currentRow()
        if 0 <= row < len(self.loaded_spectra):
            removed = self.loaded_spectra.pop(row)
            if self.master_spectrum is removed:
                self.master_spectrum = None
                for s in self.loaded_spectra:
                    if s.is_master:
                        self.master_spectrum = s
                        break
                self._update_master_status_ui()

            self.active_index = min(self.active_index, len(self.loaded_spectra) - 1)
            self._rebuild_files_table()
            self._update_live_sample_combo()
            if self.active_index >= 0:
                self._select_file_index(self.active_index)
            else:
                self._clear_all_plots()

    def _on_auto_assign_roles(self):
        for s in self.loaded_spectra:
            if s.is_master and self.master_spectrum is None:
                self.master_spectrum = s
        self._update_master_status_ui()
        self._rebuild_files_table()
        self._recalculate_all()

    def _on_clear_all(self):
        self.loaded_spectra.clear()
        self.active_index = -1
        self.master_spectrum = None
        self._update_master_status_ui()
        self._rebuild_files_table()
        self._update_live_sample_combo()
        self._clear_all_plots()
        self.statusBar().showMessage("Memoria y gráficos reiniciados.")

    def _clear_all_plots(self):
        self.plot_dark_1d.clear()
        self.plot_dark_2d.clear()
        self.plot_ref_1d.clear()
        self.plot_ref_2d.clear()
        self.plot_ref_compare.clear()
        self.plot_live_1d.clear()
        self.plot_live_2d.clear()
        self.plot_trans_main.clear()
        self.plot_trans_residuals.clear()
        self.plot_ext_main.clear()
        self.plot_ext_residuals.clear()

    # ==========================================================================
    # MANEJO Y OBTENCIÓN EFECTIVA DE CANALES (HERENCIA DEL MAESTRO)
    # ==========================================================================
    def _get_effective_channel(self, spec: SifSpectrum, channel_name: str) -> Tuple[Optional[np.ndarray], bool]:
        """
        Retorna la matriz de datos correspondiente al canal para el espectro especificado.
        Si el archivo no posee el canal, lo hereda dinámicamente del archivo Maestro.
        Retorna: (data_array, is_inherited)
        """
        # Selector de Fuente en Referencia:
        if channel_name == "reference" and hasattr(self, 'combo_ref_source'):
            src_mode = self.combo_ref_source.currentText()
            if "Forzar 👑 Maestro" in src_mode:
                if self.master_spectrum is not None and "reference" in self.master_spectrum.channels:
                    return self.master_spectrum.channels["reference"].copy(), True
                return None, False
            elif "Forzar Propia" in src_mode:
                if "reference" in spec.channels and spec.channels["reference"] is not None:
                    return spec.channels["reference"], False
                return None, False

        # Modo Auto / General:
        if channel_name in spec.channels and spec.channels[channel_name] is not None:
            return spec.channels[channel_name], False

        if self.master_spectrum is not None and channel_name in self.master_spectrum.channels:
            master_ch = self.master_spectrum.channels[channel_name]
            if master_ch is not None:
                ch_copy = master_ch.copy()
                # Escalar ruido por tiempo de exposición si difieren
                if channel_name == "dark":
                    t_master = self.master_spectrum.metadata.exposure_time
                    t_spec = spec.metadata.exposure_time
                    if t_master > 0 and abs(t_master - t_spec) > 1e-4:
                        ch_copy = ch_copy * (t_spec / t_master)
                return ch_copy, True

        return None, False

    # ==========================================================================
    # MANEJADORES DE ROI Y SINCRONIZACIÓN
    # ==========================================================================
    def _on_ref_roi_region_changed(self):
        y0, y1 = self.roi_ref_region.getRegion()
        ymin, ymax = int(round(min(y0, y1))), int(round(max(y0, y1)))
        self.spin_ref_ymin.blockSignals(True)
        self.spin_ref_ymax.blockSignals(True)
        self.spin_ref_ymin.setValue(ymin)
        self.spin_ref_ymax.setValue(ymax)
        self.spin_ref_ymin.blockSignals(False)
        self.spin_ref_ymax.blockSignals(False)
        self._schedule_recalculation()

    def _on_ref_roi_spinners_changed(self):
        ymin = self.spin_ref_ymin.value()
        ymax = self.spin_ref_ymax.value()
        if ymin > ymax:
            ymin, ymax = ymax, ymin
        self.roi_ref_region.blockSignals(True)
        self.roi_ref_region.setRegion([ymin, ymax])
        self.roi_ref_region.blockSignals(False)
        self._schedule_recalculation()

    def _on_live_roi_region_changed(self):
        y0, y1 = self.roi_live_region.getRegion()
        ymin, ymax = int(round(min(y0, y1))), int(round(max(y0, y1)))
        self.spin_live_ymin.blockSignals(True)
        self.spin_live_ymax.blockSignals(True)
        self.spin_live_ymin.setValue(ymin)
        self.spin_live_ymax.setValue(ymax)
        self.spin_live_ymin.blockSignals(False)
        self.spin_live_ymax.blockSignals(False)
        self._schedule_recalculation()

    def _on_live_roi_spinners_changed(self):
        ymin = self.spin_live_ymin.value()
        ymax = self.spin_live_ymax.value()
        if ymin > ymax:
            ymin, ymax = ymax, ymin
        self.roi_live_region.blockSignals(True)
        self.roi_live_region.setRegion([ymin, ymax])
        self.roi_live_region.blockSignals(False)
        self._schedule_recalculation()

    def _on_fit_region_changed(self):
        l0, l1 = self.roi_spectral_fit.getRegion()
        lmin, lmax = min(l0, l1), max(l0, l1)
        self.spin_fit_lmin.blockSignals(True)
        self.spin_fit_lmax.blockSignals(True)
        self.spin_fit_lmin.setValue(lmin)
        self.spin_fit_lmax.setValue(lmax)
        self.spin_fit_lmin.blockSignals(False)
        self.spin_fit_lmax.blockSignals(False)

    def _on_fit_spinners_changed(self):
        lmin = self.spin_fit_lmin.value()
        lmax = self.spin_fit_lmax.value()
        if lmin > lmax:
            lmin, lmax = lmax, lmin
        self.roi_spectral_fit.blockSignals(True)
        self.roi_spectral_fit.setRegion([lmin, lmax])
        self.roi_spectral_fit.blockSignals(False)

    def _on_tab_changed(self, idx: int):
        self._recalculate_all()

    def _schedule_recalculation(self):
        self.recalc_timer.start()

    # ==========================================================================
    # PIPELINE DE CÁLCULO INTEGRAL Y ACTUALIZACIÓN DE LAS 5 VENTANAS
    # ==========================================================================
    def _recalculate_all(self):
        if self.active_index < 0 or self.active_index >= len(self.loaded_spectra):
            return

        spec = self.loaded_spectra[self.active_index]
        wl = spec.wavelengths

        # 1. Extraer matrices crudas efectivas
        dark_mat, dark_inherited = self._get_effective_channel(spec, "dark")
        ref_mat, ref_inherited = self._get_effective_channel(spec, "reference")
        live_mat, live_inherited = self._get_effective_channel(spec, "live")
        trans_meas_mat, _ = self._get_effective_channel(spec, "transmittance")

        # Caracterización adaptativa del ruido empírico de fondo (Dark)
        if dark_mat is not None:
            try:
                self.current_noise_profile = characterize_background_noise(dark_mat)
            except Exception:
                self.current_noise_profile = None
        else:
            self.current_noise_profile = None

        # 2. Reducción y filtrado de Ruido (Ventana 1)
        dark_1d = None
        if dark_mat is not None:
            d_red = self._reduce_matrix(dark_mat, 0, dark_mat.shape[1] if dark_mat.ndim > 2 else (dark_mat.shape[0] if dark_mat.ndim == 2 else 1))
            despike_d = self.chk_dark_despike.isChecked()
            filt_d = self._map_filter_name(self.combo_dark_filter.currentText())
            p_d = self.spin_dark_param.value()
            dark_1d = apply_spectral_filter(d_red, filt_d, {'window_length': p_d, 'cutoff_ratio': 1.0 / p_d}, despike_first=despike_d)
        self.current_dark_1d = dark_1d

        # 3. Reducción y filtrado de Referencia (Ventana 2)
        ref_1d = None
        ref_ymin = self.spin_ref_ymin.value()
        ref_ymax = self.spin_ref_ymax.value()
        ref_mode = "sum" if self.combo_ref_roimode.currentText() == "Suma" else "mean"
        ref_is_bg_sub = getattr(spec, 'ref_is_bg_corrected', False)
        if ref_inherited and self.master_spectrum is not None:
            ref_is_bg_sub = getattr(self.master_spectrum, 'ref_is_bg_corrected', False)

        if ref_mat is not None:
            r_red = self._reduce_matrix(ref_mat, ref_ymin, ref_ymax, ref_mode)
            # Solo sustraer ruido si el canal no viene pre-corregido por fondo desde el SIF
            if self.chk_ref_sub_dark.isChecked() and dark_1d is not None and not ref_is_bg_sub:
                r_red = r_red - dark_1d

            # Despiking
            if self.chk_ref_despike.isChecked():
                if self.current_noise_profile is not None:
                    r_red = filter_despike_adaptive(r_red, self.current_noise_profile)
                else:
                    r_red = filter_despike_median(r_red)

            # Limpieza Adaptativa Wiener BG
            filt_r = self._map_filter_name(self.combo_ref_filter.currentText())
            if (self.chk_ref_adaptive.isChecked() or filt_r == "wiener") and self.current_noise_profile is not None:
                alpha_r = self.spin_ref_wiener_alpha.value()
                r_red = filter_wiener_adaptive(r_red, self.current_noise_profile, alpha=alpha_r)

            # Filtro tradicional si está seleccionado (y no es wiener)
            if filt_r not in ("none", "wiener"):
                p_r = self.spin_ref_param.value()
                r_red = apply_spectral_filter(r_red, filt_r, {'window_length': p_r, 'cutoff_ratio': 1.0 / p_r}, despike_first=False)
            ref_1d = r_red
        self.current_ref_1d = ref_1d

        # 4. Reducción y filtrado de Live / Señal (Ventana 3)
        live_1d = None
        live_ymin = self.spin_live_ymin.value()
        live_ymax = self.spin_live_ymax.value()
        live_mode = "sum" if self.combo_live_roimode.currentText() == "Suma" else "mean"
        if live_mat is not None:
            l_red = self._reduce_matrix(live_mat, live_ymin, live_ymax, live_mode)
            if self.chk_live_sub_dark.isChecked() and dark_1d is not None:
                l_red = l_red - dark_1d

            # Despiking
            if self.chk_live_despike.isChecked():
                if self.current_noise_profile is not None:
                    l_red = filter_despike_adaptive(l_red, self.current_noise_profile)
                else:
                    l_red = filter_despike_median(l_red)

            # Limpieza Adaptativa Wiener BG
            filt_l = self._map_filter_name(self.combo_live_filter.currentText())
            if (self.chk_live_adaptive.isChecked() or filt_l == "wiener") and self.current_noise_profile is not None:
                alpha_l = self.spin_live_wiener_alpha.value()
                l_red = filter_wiener_adaptive(l_red, self.current_noise_profile, alpha=alpha_l)

            # Filtro tradicional si está seleccionado
            if filt_l not in ("none", "wiener"):
                p_l = self.spin_live_param.value()
                l_red = apply_spectral_filter(l_red, filt_l, {'window_length': p_l, 'cutoff_ratio': 1.0 / p_l}, despike_first=False)
            live_1d = l_red
        self.current_live_1d = live_1d

        # 5. Cálculo de Transmisión (Ventana 4)
        noise_gate = self.spin_trans_gate.value()
        t_route_a, t_route_b = None, None
        t_calc = None

        if live_mat is not None and ref_mat is not None:
            t_a, t_b, val_mask = compute_transmittance_dual_route(
                live=live_mat, ref=ref_mat, dark=dark_mat,
                roi_ymin=live_ymin, roi_ymax=live_ymax,
                noise_gate=noise_gate, in_percentage=True,
                ref_is_bg_subtracted=ref_is_bg_sub
            )
            t_route_a = t_a
            t_route_b = t_b
            t_calc = t_route_a if self.radio_route_a.isChecked() else t_route_b
        elif trans_meas_mat is not None:
            t_meas_red = self._reduce_matrix(trans_meas_mat, live_ymin, live_ymax)
            t_calc = t_meas_red.copy()

        # Limpieza Adaptativa Wiener sobre T_calc
        filt_post = self._map_filter_name(self.combo_trans_filter.currentText())
        if (self.chk_trans_adaptive.isChecked() or filt_post == "wiener") and self.current_noise_profile is not None and t_calc is not None:
            fin_idx = np.isfinite(t_calc)
            if np.sum(fin_idx) > 8:
                t_calc_f = t_calc.copy()
                alpha_t = self.spin_trans_wiener_alpha.value()
                t_calc_f[fin_idx] = filter_wiener_adaptive(t_calc[fin_idx], self.current_noise_profile, alpha=alpha_t)
                t_calc = t_calc_f

        # Post-suavizado tradicional sobre T_calc
        if filt_post not in ("none", "wiener") and t_calc is not None:
            p_post = self.spin_trans_param.value()
            fin_idx = np.isfinite(t_calc)
            if np.sum(fin_idx) > 5:
                t_calc_f = t_calc.copy()
                t_calc_f[fin_idx] = apply_spectral_filter(t_calc[fin_idx], filt_post, {'window_length': p_post, 'cutoff_ratio': 1.0 / p_post}, despike_first=False)
                t_calc = t_calc_f

        # T_meas de referencia directa del SIF
        t_meas = None
        if trans_meas_mat is not None:
            t_meas = self._reduce_matrix(trans_meas_mat, live_ymin, live_ymax)

        # Residuos
        residuals = None
        if t_meas is not None and t_calc is not None:
            residuals = compute_residuals(t_meas, t_calc)

        # Propagación de error sigma_T analítica considerando sigma_BG empírico
        sigma_t = None
        if t_calc is not None and self.chk_calculate_errors.isChecked():
            if live_1d is not None and ref_1d is not None:
                s_bg = self.current_noise_profile.noise_std_spectral if self.current_noise_profile is not None else None
                _, s_t, _ = compute_transmittance_with_errors(
                    signal_spec=live_1d,
                    ref_spec=ref_1d,
                    bg_spec=dark_1d,
                    sigma_bg=s_bg,
                    noise_threshold=noise_gate,
                    in_percentage=True,
                    ref_is_bg_subtracted=ref_is_bg_sub
                )
                sigma_t = s_t
            else:
                sigma_t = np.abs(t_calc) * 0.015 + 0.1

        self.current_t_calc = t_calc
        self.current_t_meas = t_meas
        self.current_t_route_a = t_route_a
        self.current_t_route_b = t_route_b
        self.current_sigma_t = sigma_t
        self.current_residuals = residuals

        # 6. Extinción (Ventana 5)
        extinction = None
        if t_calc is not None:
            is_beer = ("log10" in self.combo_ext_formula.currentText())
            if is_beer:
                extinction, _ = compute_extinction(t_calc)
            else:
                extinction = 1.0 - (t_calc / 100.0)

            # Limpieza Adaptativa Wiener sobre la Extinción
            if self.chk_ext_adaptive.isChecked() and self.current_noise_profile is not None and extinction is not None:
                fin_e = np.isfinite(extinction)
                if np.sum(fin_e) > 8:
                    ext_f = extinction.copy()
                    alpha_e = self.spin_ext_wiener_alpha.value()
                    ext_f[fin_e] = filter_wiener_adaptive(extinction[fin_e], self.current_noise_profile, alpha=alpha_e)
                    extinction = ext_f

        self.current_extinction = extinction

        # 7. Refrescar gráficos correspondientes
        self._refresh_dark_plots(dark_mat, dark_1d, dark_inherited)
        self._refresh_ref_plots(ref_mat, ref_1d, ref_inherited)
        self._refresh_live_plots(live_mat, live_1d, live_inherited)
        self._refresh_transmittance_plots()
        self._refresh_extinction_plots()

    def _reduce_matrix(self, mat: np.ndarray, ymin: int, ymax: int, method: str = "mean") -> np.ndarray:
        while mat.ndim > 2 and mat.shape[0] == 1:
            mat = mat[0]
        if mat.ndim == 1:
            return mat.astype(np.float64)
        h, w = mat.shape
        y0 = max(0, min(ymin, h - 1))
        y1 = max(0, min(ymax, h - 1))
        if y0 > y1:
            y0, y1 = y1, y0
        sl = mat[y0:y1 + 1, :].astype(np.float64)
        return np.nansum(sl, axis=0) if method == "sum" else np.nanmean(sl, axis=0)

    # --------------------------------------------------------------------------
    # REFRESH GRÁFICOS VENTANA 1: RUIDO
    # --------------------------------------------------------------------------
    def _refresh_dark_plots(self, dark_mat: Optional[np.ndarray], dark_1d: Optional[np.ndarray], inherited: bool):
        spec = self.loaded_spectra[self.active_index]
        wl = spec.wavelengths

        origin_str = f"Heredado de 👑 {self.master_spectrum.custom_name}" if (inherited and self.master_spectrum) else "Archivo Activo"
        self.lbl_dark_source.setText(f"Origen Ruido: {origin_str}")

        # 2D Heatmap
        if dark_mat is not None:
            self.widget_dark_2d.setVisible(True)
            d2 = dark_mat[0] if dark_mat.ndim == 3 else dark_mat
            if d2.ndim == 1:
                d2 = d2.reshape(1, -1)
            h = d2.shape[0]
            d2_plot = np.tile(d2, (10, 1)) if h == 1 else d2
            h_plot = 10 if h == 1 else h
            self.img_dark_2d.setImage(d2_plot.T, autoLevels=True)
            self.img_dark_2d.setRect(pg.QtCore.QRectF(wl[0], 0, wl[-1] - wl[0], h_plot))
            self.plot_dark_2d.setXRange(wl[0], wl[-1], padding=0.02)
            self.plot_dark_2d.setYRange(0, h_plot, padding=0.02)
            if len(self.splitter_dark.sizes()) > 0 and self.splitter_dark.sizes()[0] < 50:
                self.splitter_dark.setSizes([260, 440])
        else:
            self.widget_dark_2d.setVisible(False)

        # 1D
        self.plot_dark_1d.clear()
        self.plot_dark_1d.addLegend(offset=(20, 20))
        if dark_1d is not None and np.any(np.isfinite(dark_1d)):
            pen = pg.mkPen('#89dceb', width=1.8)
            self.plot_dark_1d.plot(wl, dark_1d, pen=pen, name="Ruido / Dark (Counts)")
            mean_c = float(np.nanmean(dark_1d))
            std_c = float(np.nanstd(dark_1d))
            min_c = float(np.nanmin(dark_1d))
            max_c = float(np.nanmax(dark_1d))
            self.lbl_dark_metrics.setText(f"Métricas Ruido: Bias Medio: {mean_c:.2f} | Desvío σ_dark: {std_c:.2f} | Mín: {min_c:.1f} | Máx: {max_c:.1f} ({origin_str})")
        else:
            self.lbl_dark_metrics.setText("Métricas Ruido: Sin canal de ruido disponible en este archivo ni en Maestro.")

    # --------------------------------------------------------------------------
    # REFRESH GRÁFICOS VENTANA 2: REFERENCIA
    # --------------------------------------------------------------------------
    def _refresh_ref_plots(self, ref_mat: Optional[np.ndarray], ref_1d: Optional[np.ndarray], inherited: bool):
        spec = self.loaded_spectra[self.active_index]
        wl = spec.wavelengths

        origin_str = f"Heredado de 👑 {self.master_spectrum.custom_name}" if (inherited and self.master_spectrum) else "Archivo Activo"
        self.lbl_ref_source.setText(f"Origen Referencia: {origin_str}")

        # 2D Heatmap
        if ref_mat is not None:
            self.widget_ref_2d.setVisible(True)
            r2 = ref_mat[0] if ref_mat.ndim == 3 else ref_mat
            if r2.ndim == 1:
                r2 = r2.reshape(1, -1)
            h = r2.shape[0]
            r2_plot = np.tile(r2, (10, 1)) if h == 1 else r2
            h_plot = 10 if h == 1 else h
            self.img_ref_2d.setImage(r2_plot.T, autoLevels=True)
            self.img_ref_2d.setRect(pg.QtCore.QRectF(wl[0], 0, wl[-1] - wl[0], h_plot))
            self.plot_ref_2d.setXRange(wl[0], wl[-1], padding=0.02)
            self.plot_ref_2d.setYRange(0, h_plot, padding=0.02)
            if len(self.splitter_ref.sizes()) > 0 and self.splitter_ref.sizes()[0] < 50:
                self.splitter_ref.setSizes([260, 440])
        else:
            self.widget_ref_2d.setVisible(False)

        # 1D
        self.plot_ref_1d.clear()
        self.plot_ref_1d.addLegend(offset=(20, 20))
        if ref_1d is not None and np.any(np.isfinite(ref_1d)):
            pen = pg.mkPen('#fab387', width=2.0)
            self.plot_ref_1d.plot(wl, ref_1d, pen=pen, name="Referencia (Counts)")
            mean_r = float(np.nanmean(ref_1d))
            max_r = float(np.nanmax(ref_1d))
            max_idx = int(np.nanargmax(ref_1d))
            peak_wl = float(wl[max_idx])
            std_r = float(np.nanstd(ref_1d))
            self.lbl_ref_metrics.setText(f"Métricas Referencia: Cuentas Medias ROI: {mean_r:.1f} | Pico Lámpara: {max_r:.1f} (@ {peak_wl:.1f} nm) | Desvío: {std_r:.1f}")
        else:
            self.lbl_ref_metrics.setText("Métricas Referencia: Sin canal de referencia disponible.")

        self._refresh_ref_comparator()

    def _refresh_ref_comparator(self):
        self.plot_ref_compare.clear()
        self.plot_ref_compare.addLegend(offset=(20, 20))
        colors = ['#fab387', '#a6e3a1', '#89b4fa', '#f9e2af', '#cba6f7', '#f38ba8']

        refs = []
        for i, s in enumerate(self.loaded_spectra):
            if "reference" in s.channels:
                r_arr = s.channels["reference"]
                r_1d = self._reduce_matrix(r_arr, self.spin_ref_ymin.value(), self.spin_ref_ymax.value())
                refs.append((s.custom_name, s.wavelengths, r_1d))

        for idx, (name, wls, data) in enumerate(refs):
            pen = pg.mkPen(colors[idx % len(colors)], width=1.8)
            norm = data / max(1e-6, float(np.nanmax(data)))
            self.plot_ref_compare.plot(wls, norm, pen=pen, name=name)

    # --------------------------------------------------------------------------
    # REFRESH GRÁFICOS VENTANA 3: LIVE / SEÑAL
    # --------------------------------------------------------------------------
    def _refresh_live_plots(self, live_mat: Optional[np.ndarray], live_1d: Optional[np.ndarray], inherited: bool):
        spec = self.loaded_spectra[self.active_index]
        wl = spec.wavelengths

        # 2D Heatmap
        if live_mat is not None:
            self.widget_live_2d.setVisible(True)
            l2 = live_mat[0] if live_mat.ndim == 3 else live_mat
            if l2.ndim == 1:
                l2 = l2.reshape(1, -1)
            h = l2.shape[0]
            l2_plot = np.tile(l2, (10, 1)) if h == 1 else l2
            h_plot = 10 if h == 1 else h
            self.img_live_2d.setImage(l2_plot.T, autoLevels=True)
            self.img_live_2d.setRect(pg.QtCore.QRectF(wl[0], 0, wl[-1] - wl[0], h_plot))
            self.plot_live_2d.setXRange(wl[0], wl[-1], padding=0.02)
            self.plot_live_2d.setYRange(0, h_plot, padding=0.02)
            if len(self.splitter_live.sizes()) > 0 and self.splitter_live.sizes()[0] < 50:
                self.splitter_live.setSizes([260, 440])
        else:
            self.widget_live_2d.setVisible(False)

        # 1D
        self.plot_live_1d.clear()
        self.plot_live_1d.addLegend(offset=(20, 20))
        if live_1d is not None and np.any(np.isfinite(live_1d)):
            pen = pg.mkPen('#f38ba8', width=2.0)
            self.plot_live_1d.plot(wl, live_1d, pen=pen, name=f"Live: {spec.custom_name}")
            mean_l = float(np.nanmean(live_1d))
            max_l = float(np.nanmax(live_1d))
            max_idx = int(np.nanargmax(live_1d))
            peak_wl = float(wl[max_idx])
            sbr = (mean_l / max(1.0, float(np.nanmean(self.current_dark_1d)))) if self.current_dark_1d is not None else 1.0
            self.lbl_live_metrics.setText(f"Métricas Señal: Cuentas Medias ROI: {mean_l:.1f} | Pico Muestra: {max_l:.1f} (@ {peak_wl:.1f} nm) | SBR (Señal/Ruido): {sbr:.1f}x")
        else:
            self.lbl_live_metrics.setText("Métricas Señal: Sin canal de señal disponible.")

        # 1D
        self.plot_live_1d.clear()
        self.plot_live_1d.addLegend(offset=(20, 20))
        if live_1d is not None and np.any(np.isfinite(live_1d)):
            pen = pg.mkPen('#f38ba8', width=2.0)
            self.plot_live_1d.plot(wl, live_1d, pen=pen, name=f"Live: {spec.custom_name}")
            mean_l = float(np.nanmean(live_1d))
            max_l = float(np.nanmax(live_1d))
            max_idx = int(np.nanargmax(live_1d))
            peak_wl = float(wl[max_idx])
            sbr = (mean_l / max(1.0, float(np.nanmean(self.current_dark_1d)))) if self.current_dark_1d is not None else 1.0
            self.lbl_live_metrics.setText(f"Métricas Señal: Cuentas Medias ROI: {mean_l:.1f} | Pico Muestra: {max_l:.1f} (@ {peak_wl:.1f} nm) | SBR (Señal/Ruido): {sbr:.1f}x")
        else:
            self.lbl_live_metrics.setText("Métricas Señal: Sin canal de señal disponible.")

    # --------------------------------------------------------------------------
    # REFRESH GRÁFICOS VENTANA 4: TRANSMISIÓN
    # --------------------------------------------------------------------------
    def _refresh_transmittance_plots(self):
        spec = self.loaded_spectra[self.active_index]
        wl = spec.wavelengths

        self.plot_trans_main.clear()
        self.plot_trans_main.addLegend(offset=(20, 20))
        self.plot_trans_main.addItem(self.vLine_trans, ignoreBounds=True)
        self.plot_trans_main.addItem(self.hLine_trans, ignoreBounds=True)

        t_calc = self.current_t_calc
        t_meas = self.current_t_meas
        sigma_t = self.current_sigma_t
        res = self.current_residuals

        # T_calc
        if self.chk_show_tcalc.isChecked() and t_calc is not None:
            fin = np.isfinite(t_calc)
            if np.any(fin):
                self.plot_trans_main.plot(wl[fin], t_calc[fin], pen=pg.mkPen('#a6e3a1', width=2.2), name="T_calc (%)")
                if self.chk_show_ribbon.isChecked() and sigma_t is not None:
                    up = t_calc + sigma_t
                    low = t_calc - sigma_t
                    c_up = self.plot_trans_main.plot(wl[fin], up[fin], pen=pg.mkPen(color=(166, 227, 161, 0)))
                    c_low = self.plot_trans_main.plot(wl[fin], low[fin], pen=pg.mkPen(color=(166, 227, 161, 0)))
                    fill = pg.FillBetweenItem(c_low, c_up, brush=pg.mkBrush(166, 227, 161, 40))
                    self.plot_trans_main.addItem(fill)

        # Comparar Ruta B
        if self.chk_compare_routes.isChecked() and self.current_t_route_b is not None:
            fin_b = np.isfinite(self.current_t_route_b)
            if np.any(fin_b):
                self.plot_trans_main.plot(wl[fin_b], self.current_t_route_b[fin_b], pen=pg.mkPen('#f9e2af', width=1.8, style=Qt.PenStyle.DashLine), name="Ruta B (Promedio ROI)")

        # T_meas
        if self.chk_show_tmeas.isChecked() and t_meas is not None:
            fin_m = np.isfinite(t_meas)
            if np.any(fin_m):
                self.plot_trans_main.plot(wl[fin_m], t_meas[fin_m], pen=pg.mkPen('#89b4fa', width=2.0, style=Qt.PenStyle.DotLine), name="T_meas SIF (%)")

        # Residuos
        self.plot_trans_residuals.clear()
        zero_line = pg.InfiniteLine(pos=0.0, angle=0, pen=pg.mkPen('#6c7086', style=Qt.PenStyle.DashLine))
        self.plot_trans_residuals.addItem(zero_line)
        if res is not None and np.any(np.isfinite(res)):
            fin_r = np.isfinite(res)
            self.plot_trans_residuals.plot(wl[fin_r], res[fin_r], pen=pg.mkPen('#f38ba8', width=1.8), name="Residuo (T_meas - T_calc)")
            rms = float(np.sqrt(np.nanmean(res ** 2)))
            mean_r = float(np.nanmean(res))
            fin_t = t_calc[np.isfinite(t_calc)] if t_calc is not None else np.array([])
            mean_t = float(np.mean(fin_t)) if len(fin_t) > 0 else 0.0
            min_t = float(np.min(fin_t)) if len(fin_t) > 0 else 0.0
            max_t = float(np.max(fin_t)) if len(fin_t) > 0 else 0.0
            self.lbl_trans_metrics.setText(f"Métricas Transmisión: T_media: {mean_t:.2f}% | Mín: {min_t:.1f}% | Máx: {max_t:.1f}% | RMS Residuo: {rms:.3f}% (ΔT medio: {mean_r:.3f}%)")
        elif t_calc is not None:
            fin_t = t_calc[np.isfinite(t_calc)]
            mean_t = float(np.mean(fin_t)) if len(fin_t) > 0 else 0.0
            min_t = float(np.min(fin_t)) if len(fin_t) > 0 else 0.0
            max_t = float(np.max(fin_t)) if len(fin_t) > 0 else 0.0
            self.lbl_trans_metrics.setText(f"Métricas Transmisión: T_media: {mean_t:.2f}% | Mín: {min_t:.1f}% | Máx: {max_t:.1f}%")

    # --------------------------------------------------------------------------
    # REFRESH GRÁFICOS VENTANA 5: EXTINCIÓN Y AJUSTE DE PICOS
    # --------------------------------------------------------------------------
    def _refresh_extinction_plots(self):
        spec = self.loaded_spectra[self.active_index]
        wl = spec.wavelengths
        ext = self.current_extinction

        self.plot_ext_main.clear()
        self.plot_ext_main.addLegend(offset=(20, 20))
        self.plot_ext_main.addItem(self.roi_spectral_fit)

        if ext is not None and np.any(np.isfinite(ext)):
            fin = np.isfinite(ext)
            formula_name = "Absorbancia A" if "log10" in self.combo_ext_formula.currentText() else "Extinción E"
            self.plot_ext_main.plot(wl[fin], ext[fin], pen=pg.mkPen('#cba6f7', width=2.0), name=f"Experimental ({formula_name})")

            # Si ya se realizó un ajuste, graficar curva ajustada
            if self.last_peak_fit_results is not None:
                res = self.last_peak_fit_results
                self.plot_ext_main.plot(res['x_dense'], res['y_dense'], pen=pg.mkPen('#a6e3a1', width=2.5), name=f"Ajuste {res['model'].capitalize()}")
                self.plot_ext_residuals.clear()
                zero_l = pg.InfiniteLine(pos=0.0, angle=0, pen=pg.mkPen('#6c7086', style=Qt.PenStyle.DashLine))
                self.plot_ext_residuals.addItem(zero_l)
                self.plot_ext_residuals.plot(res['fit_x'], res['residuals'], pen=pg.mkPen('#fab387', width=1.8), name="Residuo")

    def _on_run_peak_fit(self):
        if self.current_extinction is None:
            QMessageBox.warning(self, "Ajuste de Picos", "No hay curva de extinción calculada para ajustar.")
            return

        spec = self.loaded_spectra[self.active_index]
        wl = spec.wavelengths
        ext = self.current_extinction

        lmin = min(self.spin_fit_lmin.value(), self.spin_fit_lmax.value())
        lmax = max(self.spin_fit_lmin.value(), self.spin_fit_lmax.value())
        model_str = self.combo_fit_model.currentText()
        slit_um = self.spin_fit_slit.value()

        try:
            results = fit_peak_advanced(
                wavelengths=wl,
                signal_data=ext,
                roi_range=(lmin, lmax),
                model_type=model_str,
                slit_width_um=slit_um,
                pixel_pitch_um=CCD_PIXEL_PITCH_UM
            )
            self.last_peak_fit_results = results

            # Mostrar resultados formateados
            model_disp = results['model'].capitalize()
            l0 = results['peak_center']
            u_l0 = results['u_peak_center_combined']
            fwhm = results['fwhm']
            u_fwhm = results['u_fwhm_combined']
            amp = results['amplitude']
            r2 = results['r_squared']
            u_slit = results['u_slit']
            u_px = results['u_pixel']
            u_fit = results['u_peak_center_fit']

            q_info = f" | Factor Fano q = {results['q_factor']:.3f} ± {results['u_q_factor']:.3f}" if results.get('q_factor') is not None else ""

            text = (
                f"<b>Modelo:</b> {model_disp}{q_info} | "
                f"<b>λ_peak:</b> {l0:.3f} ± {u_l0:.3f} nm | "
                f"<b>FWHM:</b> {fwhm:.3f} ± {u_fwhm:.3f} nm | "
                f"<b>Amplitud A₀:</b> {amp:.4f} | <b>R²:</b> {r2:.5f}<br>"
                f"<b>Desglose de Incertidumbre Metrológica:</b> u_fit = ±{u_fit:.3f} nm, u_slit = ±{u_slit:.3f} nm, u_pixel = ±{u_px:.3f} nm"
            )
            self.lbl_fit_results.setText(text)
            self._refresh_extinction_plots()
            self.statusBar().showMessage(f"Ajuste {model_disp} completado exitosamente: λ₀ = {l0:.2f} ± {u_l0:.2f} nm, R² = {r2:.4f}")

        except Exception as e:
            QMessageBox.critical(self, "Error en Ajuste", f"Ocurrió un error al ajustar pico:\n{str(e)}")

    def _on_export_peak_fit(self):
        if self.last_peak_fit_results is None:
            QMessageBox.warning(self, "Exportar Ajuste", "Primero debe realizar un ajuste de pico exitoso.")
            return

        res = self.last_peak_fit_results
        spec = self.loaded_spectra[self.active_index]
        default_fn = f"{spec.custom_name}_ajuste_{res['model']}.txt"

        path, _ = QFileDialog.getSaveFileName(self, "Guardar resultados de ajuste", default_fn, "Texto (*.txt);;CSV (*.csv)")
        if not path:
            return

        cols = {
            "Experimental": res['fit_y'],
            "Ajuste": res['y_pred'],
            "Residuo": res['residuals']
        }
        meta_hdr = {
            "Muestra": spec.metadata.filename,
            "Modelo": res['model'],
            "Peak_Center_nm": f"{res['peak_center']:.4f} +- {res['u_peak_center_combined']:.4f}",
            "FWHM_nm": f"{res['fwhm']:.4f} +- {res['u_fwhm_combined']:.4f}",
            "Amplitud": f"{res['amplitude']:.6e}",
            "R_Squared": f"{res['r_squared']:.6f}",
            "u_slit_nm": f"{res['u_slit']:.4f}",
            "u_pixel_nm": f"{res['u_pixel']:.4f}"
        }
        if res.get('q_factor') is not None:
            meta_hdr["Fano_q"] = f"{res['q_factor']:.4f} +- {res['u_q_factor']:.4f}"

        delim = "," if path.lower().endswith(".csv") else "\t"
        try:
            export_spectrum_txt(path, res['fit_x'], cols, metadata_header=meta_hdr, delimiter=delim)
            QMessageBox.information(self, "Ajuste Exportado", f"Archivo de ajuste guardado exitosamente:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Error de Exportación", f"Error al guardar:\n{str(e)}")

    # ==========================================================================
    # DIÁLOGO DE RUIDO PSD Y UTILIDADES
    # ==========================================================================
    def _on_view_dark_psd(self):
        if self.active_index < 0:
            return
        spec = self.loaded_spectra[self.active_index]
        dark_mat, _ = self._get_effective_channel(spec, "dark")
        if dark_mat is None:
            QMessageBox.warning(self, "PSD Ruido", "No hay matriz de ruido disponible.")
            return

        try:
            dummy_spec = SifSpectrum(
                raw_data=dark_mat if dark_mat.ndim == 3 else dark_mat[np.newaxis, ...],
                wavelengths=spec.wavelengths,
                metadata=spec.metadata,
                is_2d=(dark_mat.ndim >= 2 and (dark_mat.shape[1] > 1 if dark_mat.ndim == 3 else dark_mat.shape[0] > 1))
            )
            profile = characterize_background_noise(dummy_spec)
            dlg = NoisePsdDialog(profile, self)
            dlg.exec()
        except Exception as e:
            QMessageBox.critical(self, "Error PSD", f"Error al calcular PSD de ruido:\n{str(e)}")

    def _map_filter_name(self, name: str) -> str:
        if "Savitzky" in name:
            return "savgol"
        elif "Fourier" in name:
            return "fourier"
        elif "Media" in name:
            return "moving_average"
        elif "Wiener" in name:
            return "wiener"
        return "none"

    # ==========================================================================
    # INSTRUMENTACIÓN Y CALIBRACIÓN EXTERNA
    # ==========================================================================
    def _on_objective_changed(self):
        obj_name = self.combo_objective.currentText()
        if obj_name in MICROSCOPE_OBJECTIVES:
            obj_info = MICROSCOPE_OBJECTIVES[obj_name]
            scale_um = obj_info["pixel_scale_um"]
            na = obj_info["na"]
            self.lbl_pixel_scale.setText(f"Escala: {scale_um:.4f} µm/px | NA {na:.2f}")
        self._schedule_recalculation()

    def _on_load_external_calib(self):
        if self.active_index < 0:
            QMessageBox.warning(self, "Calibración", "Cargue un archivo SIF primero.")
            return

        spec = self.loaded_spectra[self.active_index]
        path, _ = QFileDialog.getOpenFileName(
            self, "Cargar calibración de longitud de onda", "", "Archivos (*.txt *.cal *.dat);;Todos (*.*)"
        )
        if not path:
            return

        try:
            new_wl = load_external_calibration_file(path, spec.width)
            self.custom_calib_wavelengths = new_wl
            self.custom_calib_source = os.path.basename(path)
            for s in self.loaded_spectra:
                if s.width == spec.width:
                    s.wavelengths = new_wl.copy()

            self.lbl_calib_status.setText(f"Origen: {self.custom_calib_source}")
            self._recalculate_all()
            self.statusBar().showMessage(f"Calibración externa cargada: {path}")
        except Exception as e:
            QMessageBox.critical(self, "Error de Calibración", f"Error al cargar dispersión:\n{str(e)}")

    def _on_reset_calib(self):
        if not self.loaded_spectra:
            return
        for s in self.loaded_spectra:
            s.wavelengths = _extract_wavelength_axis(s.metadata.extra_info, s.width)
        self.custom_calib_wavelengths = None
        self.custom_calib_source = ""
        self.lbl_calib_status.setText("Origen: SIF Nativo")
        self._recalculate_all()

    # ==========================================================================
    # EXPORTACIÓN CIENTÍFICA
    # ==========================================================================
    def _on_export_active_curves(self):
        if self.active_index < 0:
            QMessageBox.warning(self, "Exportar", "No hay espectro seleccionado.")
            return

        spec = self.loaded_spectra[self.active_index]
        path, _ = QFileDialog.getSaveFileName(
            self, "Exportar espectro procesado", f"{spec.custom_name}_proc.dat", "Archivo de Datos (*.dat);;Texto (*.txt);;CSV (*.csv)"
        )
        if not path:
            return

        cols = {}
        if self.current_live_1d is not None:
            cols["Live_Signal_Counts"] = self.current_live_1d
        if self.current_ref_1d is not None:
            cols["Reference_Counts"] = self.current_ref_1d
        if self.current_dark_1d is not None:
            cols["Dark_Noise_Counts"] = self.current_dark_1d
        if self.current_t_calc is not None:
            cols["Transmittance_calc_pct"] = self.current_t_calc
        if self.current_t_meas is not None:
            cols["Transmittance_meas_pct"] = self.current_t_meas
        if self.current_extinction is not None:
            cols["Extinction"] = self.current_extinction
        if self.current_residuals is not None:
            cols["Residuals_pct"] = self.current_residuals

        meta_hdr = {
            "Archivo": spec.metadata.filename,
            "Exposicion_s": f"{spec.metadata.exposure_time:.4f}",
            "Ranura_um": f"{spec.metadata.slit_width_um:.0f}",
            "Objetivo": self.combo_objective.currentText(),
            "Archivo_Maestro": self.master_spectrum.custom_name if self.master_spectrum else "Ninguno"
        }

        delim = "," if path.lower().endswith(".csv") else "\t"
        try:
            export_spectrum_txt(path, spec.wavelengths, cols, metadata_header=meta_hdr, delimiter=delim)
            QMessageBox.information(self, "Exportación Exitosa", f"Archivo guardado en:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Error al Exportar", f"Error:\n{str(e)}")

    def _on_export_batch_set(self):
        if not self.loaded_spectra:
            QMessageBox.warning(self, "Exportar", "No hay espectros cargados.")
            return

        out_dir = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta destino para lote")
        if not out_dir:
            return

        count = 0
        live_ymin = self.spin_live_ymin.value()
        live_ymax = self.spin_live_ymax.value()
        noise_gate = self.spin_trans_gate.value()

        for spec in self.loaded_spectra:
            dark_mat, _ = self._get_effective_channel(spec, "dark")
            ref_mat, _ = self._get_effective_channel(spec, "reference")
            live_mat, _ = self._get_effective_channel(spec, "live")
            trans_meas, _ = self._get_effective_channel(spec, "transmittance")

            cols = {}
            if live_mat is not None and ref_mat is not None:
                t_a, t_b, _ = compute_transmittance_dual_route(
                    live=live_mat, ref=ref_mat, dark=dark_mat,
                    roi_ymin=live_ymin, roi_ymax=live_ymax,
                    noise_gate=noise_gate, in_percentage=True
                )
                cols["T_RouteA_pct"] = t_a
                cols["T_RouteB_pct"] = t_b
                cols["T_Selected_pct"] = t_a if self.radio_route_a.isChecked() else t_b

            if trans_meas is not None:
                cols["T_meas_SIF_pct"] = self._reduce_matrix(trans_meas, live_ymin, live_ymax)

            if not cols:
                continue

            out_fn = os.path.join(out_dir, f"{spec.custom_name}_proc.dat")
            meta_hdr = {
                "Archivo": spec.metadata.filename,
                "Exposicion_s": str(spec.metadata.exposure_time),
                "Maestro_Usado": self.master_spectrum.custom_name if self.master_spectrum else "N/A"
            }
            try:
                export_spectrum_txt(out_fn, spec.wavelengths, cols, metadata_header=meta_hdr)
                count += 1
            except Exception:
                pass

        QMessageBox.information(self, "Lote Exportado", f"Se procesaron y exportaron {count} espectros en:\n{out_dir}")

    def _on_export_plot_image(self):
        current_tab_idx = self.tabs_process.currentIndex()
        plot_map = {
            0: self.plot_dark_1d,
            1: self.plot_ref_1d,
            2: self.plot_live_1d,
            3: self.plot_trans_main,
            4: self.plot_ext_main
        }
        target_plot = plot_map.get(current_tab_idx, self.plot_trans_main)

        path, _ = QFileDialog.getSaveFileName(
            self, "Guardar gráfico como imagen", "espectro_publicacion.png", "Imagen PNG (*.png);;Vectorial SVG (*.svg)"
        )
        if not path:
            return

        try:
            if path.lower().endswith(".svg"):
                exporter = pg_export.SVGExporter(target_plot.plotItem)
                exporter.export(path)
            else:
                exporter = pg_export.ImageExporter(target_plot.plotItem)
                exporter.parameters()['width'] = 2400
                exporter.export(path)
            QMessageBox.information(self, "Imagen Guardada", f"Gráfico exportado correctamente en:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Error al Guardar Imagen", f"Error:\n{str(e)}")


# ==============================================================================
# ENTRADA PRINCIPAL STANDALONE
# ==============================================================================
def main():
    app = QApplication(sys.argv)
    window = SifAnalyzerWindow()

    if len(sys.argv) > 1:
        sif_args = [arg for arg in sys.argv[1:] if os.path.isfile(arg) and arg.lower().endswith('.sif')]
        if sif_args:
            window._load_file_list(sif_args)

    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
