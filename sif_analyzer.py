"""
sif_analyzer.py
===============
Analizador y Procesador Avanzado de Espectros .SIF (Andor Solis).
Aplicación gráfica profesional en PyQt6 + PyQtGraph (Tema Catppuccin Mocha).

Arquitectura por Ventanas de Proceso Separadas (7 pestañas, Fase 4):
- Ventana 1 (⬛ 1. Ruido / Dark): Visualización 1D/2D de ruido (Lazy Rendering + contraste robusto), Wiener/PSD y estadísticas.
- Ventana 2 (💡 2. Referencia): Sub-vistas 1D y 2D, ROI vertical, resta de ruido, comparador de referencias y métricas.
- Ventana 3 (🔴 3. Live / Señal): Sub-vistas 1D y 2D, selector de muestra del lote, resta de ruido, filtros y ROI.
- Ventana 4 (📊 4. Transmisión): Comparación T_calc vs T_meas, cálculo 2D Ruta A vs Ruta B, Noise Gate y post-suavizado.
- Ventana 5 (🔬 5. Extinción y Ajuste): Deconvolución multi-pico (1-5, Gauss/Lorentz/Pseudo-Voigt/Fano) con línea base
  AsLS Whittaker, tabla de parámetros por pico y cálculo de incertidumbre combinada u_c(lambda).
- Ventana 6 (📈 6. Multi-Espectro & Polarización): Comparador Overlay/Cascada del lote marcado, y análisis de
  dicroísmo/polarización plasmónica con ajuste de Ley de Malus y factor de anisotropía g.
- Ventana 7 (📋 7. Ficha Metrológica): Trazabilidad completa del instrumento y del procesamiento, y exportación FAIR
  a HDF5/NeXus, Markdown o portapapeles.
- Archivo Maestro (👑 Maestro): Detección e importación en lote donde el archivo con 4 canales comparte ruido y ref.
- Panel Izquierdo: Entrada y Hardware (Archivos cargados, metadatos 1D-FVB vs 2D, escala óptica y objetivo confocal).
- Panel Central: 7 Ventanas de Proceso Separadas (lienzo 100% gráficos y mapas 2D).
- Panel Derecho: Opciones contextuales por pestaña activa (QStackedWidget con 7 páginas), colapsable con Ctrl+D / botón Opciones.
- Menú contextual universal: exportación FigureExportStudio (SVG/PNG 600 DPI) por clic derecho en todo gráfico;
  acceso directo a la Wiki Científica (ScientificWikiBrowserDialog) desde la barra superior.
"""

import os
import sys
from datetime import datetime
import numpy as np
from typing import Dict, List, Optional, Tuple, Any

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QGroupBox, QLabel, QPushButton, QComboBox, QCheckBox,
    QSpinBox, QDoubleSpinBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QFileDialog, QMessageBox, QTabWidget, QScrollArea, QFrame,
    QRadioButton, QButtonGroup, QStatusBar, QLineEdit, QDialog, QStackedWidget,
    QMenu, QTextBrowser
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QColor, QFont, QIcon, QAction

import pyqtgraph as pg
import pyqtgraph.exporters as pg_export

from analysis.figure_export_studio import FigureExportStudioDialog
from analysis.scientific_wiki_browser import ScientificWikiBrowserDialog

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
        apply_spectral_filters_2d,
        filter_wiener_adaptive,
        filter_despike_adaptive,
        filter_despike_median,
        estimate_photonic_noise,
        compute_transmittance,
        compute_transmittance_with_errors,
        compute_transmittance_dual_route,
        fit_peak_advanced,
        fit_extinction_multi_peak,
        extract_polarization_angle_from_name,
        fit_malus_law,
        export_sif_session_to_hdf5,
        compute_extinction,
        compute_residuals,
        compute_robust_contrast_levels,
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
        apply_spectral_filters_2d,
        filter_wiener_adaptive,
        filter_despike_adaptive,
        filter_despike_median,
        estimate_photonic_noise,
        compute_transmittance,
        compute_transmittance_with_errors,
        compute_transmittance_dual_route,
        fit_peak_advanced,
        fit_extinction_multi_peak,
        extract_polarization_angle_from_name,
        fit_malus_law,
        export_sif_session_to_hdf5,
        compute_extinction,
        compute_residuals,
        compute_robust_contrast_levels,
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
QScrollBar:horizontal {
    border: none;
    background: #181825;
    height: 10px;
    margin: 0px;
}
QScrollBar::handle:horizontal {
    background: #313244;
    min-width: 20px;
    border-radius: 5px;
}
QScrollBar::handle:horizontal:hover {
    background: #45475a;
}
"""


# ==============================================================================
# PRESETS DE CONTRASTE ROBUSTO PARA MAPAS DE CALOR 2D
# ==============================================================================
CONTRAST_PRESETS: Dict[str, Tuple[float, float]] = {
    "✨ Auto-Robusto (1% - 99%)": (1.0, 99.0),
    "🔍 Alto Contraste (2% - 98%)": (2.0, 98.0),
    "🌟 Resaltar Señal Débil (5% - 95%)": (5.0, 95.0),
    "🎯 Rango Completo (0% - 100% Raw)": (0.0, 100.0),
}
CONTRAST_MANUAL_LABEL = "⚙️ Manual / LUT"

# ==============================================================================
# PALETA DE COMPONENTES INDIVIDUALES PARA DECONVOLUCIÓN MULTI-PICO (1-5 PICOS)
# ==============================================================================
PEAK_COMPONENT_COLORS: List[str] = ['#f38ba8', '#fab387', '#a6e3a1', '#89dceb', '#cba6f7']


def _build_contrast_combo() -> QComboBox:
    """Construye un QComboBox con los presets de contraste robusto 2D + modo Manual/LUT."""
    combo = QComboBox()
    combo.addItems(list(CONTRAST_PRESETS.keys()) + [CONTRAST_MANUAL_LABEL])
    combo.setToolTip(make_tooltip(
        "Contraste del Mapa de Calor 2D (Clipping de Percentiles)",
        "Un único píxel saturado (rayo cósmico, píxel caliente) puede 'quemar' la escala de colores y "
        "esconder el resto del espectro útil. Los presets recortan un pequeño porcentaje de los extremos "
        "de intensidad para que el color se reparta sobre la señal real y no sobre el outlier.",
        "Los niveles [v_min, v_max] se fijan por percentiles robustos p_low/p_high de la distribución de "
        "intensidades finitas (excluyendo NaN/Inf) vía <code>compute_robust_contrast_levels()</code>. "
        "'Rango Completo' usa p=[0,100] (equivalente al mínimo/máximo crudo); 'Manual/LUT' cede el control "
        "de niveles al <code>HistogramLUTWidget</code> interactivo."
    ))
    return combo


def make_tooltip(title: str, basic: str, expert: str) -> str:
    """
    Genera un cartel explicativo en HTML estructurado para usuarios de nivel bajo y experto.
    - Modo Intuitivo (Básico): Pedagogía práctica, significado cualitativo y comportamiento.
    - Metrología (Experto): Rigor físico-matemático, fórmulas, unidades e impacto de incertidumbres.
    """
    return (
        f"<div style='font-family: Segoe UI, sans-serif; font-size: 11px; max-width: 380px; line-height: 1.35;'>"
        f"<div style='background-color: #313244; color: #89b4fa; font-weight: bold; font-size: 12px; padding: 4px 8px; border-radius: 4px; border-left: 3px solid #89b4fa;'>"
        f"ℹ️ {title}</div><br>"
        f"<b style='color: #a6e3a1;'>🌱 Modo Intuitivo (Básico):</b><br>"
        f"<span style='color: #cdd6f4;'>{basic}</span><br><br>"
        f"<b style='color: #cba6f7;'>🔬 Metrología (Nivel Experto):</b><br>"
        f"<span style='color: #bac2de;'>{expert}</span>"
        f"</div>"
    )


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

        # Fase 2: Lazy Rendering — matrices 2D procesadas en caché y banderas de "sucio" por pestaña
        self._current_dark_2d_processed: Optional[np.ndarray] = None
        self._current_ref_2d_processed: Optional[np.ndarray] = None
        self._current_live_2d_processed: Optional[np.ndarray] = None
        self._dark_2d_plot_cache: Optional[np.ndarray] = None
        self._ref_2d_plot_cache: Optional[np.ndarray] = None
        self._live_2d_plot_cache: Optional[np.ndarray] = None
        self._tab_2d_dirty: Dict[int, bool] = {0: True, 1: True, 2: True}

        # Fase 4: Wiki singleton, resultados de polarización y ficha metrológica
        self._wiki_dialog: Optional[ScientificWikiBrowserDialog] = None
        self.last_malus_fit_results: Optional[Dict[str, Any]] = None

        # Timer para recálculos reactivos suaves (25 fps max)
        self.recalc_timer = QTimer(self)
        self.recalc_timer.setSingleShot(True)
        self.recalc_timer.setInterval(40)
        self.recalc_timer.timeout.connect(self._recalculate_all)

        # 2. Construcción de Interfaz
        self._setup_menus()
        self._setup_ui()
        self._setup_crosshairs()
        self._setup_all_plot_export_menus()

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

        menu_view = menubar.addMenu("Ver")
        self.act_toggle_right = QAction("👁️ Opciones del Panel Activo", self)
        self.act_toggle_right.setShortcut("Ctrl+D")
        self.act_toggle_right.setCheckable(True)
        self.act_toggle_right.setChecked(True)
        self.act_toggle_right.triggered.connect(self._on_toggle_right_panel)
        menu_view.addAction(self.act_toggle_right)

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
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(6)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.main_splitter)

        # 1. Panel Izquierdo: Entrada y Hardware (Archivos, Metadatos, Óptica)
        self.left_panel = self._create_left_panel()
        self.left_panel.setMinimumWidth(280)
        self.main_splitter.addWidget(self.left_panel)

        # 2. Panel Central: 7 Ventanas de Proceso Separadas (lienzo 100% gráficos)
        self.center_panel = self._create_center_process_tabs()
        self.center_panel.setMinimumWidth(500)
        self.main_splitter.addWidget(self.center_panel)

        # 3. Panel Derecho: Parámetros y Modelos Contextuales (Opciones del Panel Activo)
        self.right_panel = self._create_right_panel()
        self.right_panel.setMinimumWidth(300)
        self.main_splitter.addWidget(self.right_panel)

        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.setSizes([320, 960, 340])

    # --------------------------------------------------------------------------
    # PANEL IZQUIERDO: ARCHIVO MAESTRO, ARCHIVOS Y METADATOS
    # --------------------------------------------------------------------------
    def _create_left_panel(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)
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

        # Grupo: Gestor de Archivos (grp_files)
        grp_files = QGroupBox("Gestor de Archivos SIF")
        vbox_files = QVBoxLayout(grp_files)

        btn_row = QHBoxLayout()
        self.btn_add_file = QPushButton("📂 Añadir .SIF")
        self.btn_add_file.setObjectName("primaryBtn")
        self.btn_add_file.setToolTip("Añade uno o varios archivos .sif al lote.")
        self.btn_add_file.clicked.connect(self._on_open_single_file)
        self.btn_add_folder = QPushButton("📁 Cargar Carpeta")
        self.btn_add_folder.setToolTip("Carga todos los archivos .sif contenidos en un directorio.")
        self.btn_add_folder.clicked.connect(self._on_open_folder)
        btn_row.addWidget(self.btn_add_file)
        btn_row.addWidget(self.btn_add_folder)
        vbox_files.addLayout(btn_row)

        self.table_files = QTableWidget()
        self.table_files.setColumnCount(4)
        self.table_files.setHorizontalHeaderLabels(["Sel", "Archivo", "Canales", "Rol / Estado"])
        self.table_files.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.table_files.setHorizontalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        self.table_files.setVerticalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        self.table_files.horizontalHeader().setStretchLastSection(False)
        self.table_files.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table_files.setColumnWidth(0, 40)
        self.table_files.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table_files.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table_files.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table_files.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_files.setToolTip(make_tooltip(
            "Navegación de la Tabla de Archivos",
            "Hacé clic en cualquier fila para activarla, o usá las flechas ↑/↓ y RePág/AvPág del teclado "
            "una vez que la tabla tenga el foco: el espectro activo cambia al instante junto con metadatos y gráficos.",
            "La selección dispara <code>currentCellChanged</code>, que invoca <code>_select_file_index(row)</code> "
            "sólo cuando la fila objetivo difiere de <code>active_index</code>, evitando recálculos redundantes "
            "en cada evento de foco."
        ))
        self.table_files.cellClicked.connect(self._on_file_row_clicked)
        self.table_files.currentCellChanged.connect(
            lambda cur_r, cur_c, prev_r, prev_c: self._select_file_index(cur_r) if cur_r >= 0 and cur_r != self.active_index else None
        )
        vbox_files.addWidget(self.table_files)

        row_aux = QHBoxLayout()
        self.btn_remove_file = QPushButton("Eliminar")
        self.btn_remove_file.setToolTip("Elimina el archivo actualmente seleccionado del lote.")
        self.btn_remove_file.clicked.connect(self._on_remove_selected_file)
        self.btn_auto_roles = QPushButton("Auto-Roles")
        self.btn_auto_roles.setToolTip("Auto-asigna el archivo Maestro que contenga los 4 canales completos.")
        self.btn_auto_roles.clicked.connect(self._on_auto_assign_roles)
        row_aux.addWidget(self.btn_remove_file)
        row_aux.addWidget(self.btn_auto_roles)
        vbox_files.addLayout(row_aux)

        layout.addWidget(grp_files)

        # Grupo: Metadatos del Espectro Activo (grp_meta) — enriquecido con insignia FVB vs 2D
        grp_meta = QGroupBox("Metadatos del Espectro Activo")
        vbox_meta = QVBoxLayout(grp_meta)

        self.lbl_meta_badge = QLabel("Sin espectro activo")
        self.lbl_meta_badge.setStyleSheet("font-weight: bold; font-size: 12px;")
        vbox_meta.addWidget(self.lbl_meta_badge)

        self.lbl_meta_dims = QLabel("Dimensiones: --")
        self.lbl_meta_dims.setStyleSheet("color: #bac2de; font-size: 11px;")
        vbox_meta.addWidget(self.lbl_meta_dims)

        self.lbl_meta_scale_range = QLabel("--")
        self.lbl_meta_scale_range.setWordWrap(True)
        self.lbl_meta_scale_range.setStyleSheet("color: #bac2de; font-size: 11px;")
        vbox_meta.addWidget(self.lbl_meta_scale_range)

        line_meta = QFrame()
        line_meta.setFrameShape(QFrame.Shape.HLine)
        line_meta.setStyleSheet("color: #313244;")
        vbox_meta.addWidget(line_meta)

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
        layout.addWidget(grp_meta)

        # Grupo: Instrumentación Óptica y Escala (grp_optics) — trasladado del antiguo panel derecho
        grp_optics = QGroupBox("Instrumentación: Escala y Óptica")
        vbox_optics = QVBoxLayout(grp_optics)

        lbl_obj = QLabel("Objetivo Microscopio:")
        lbl_obj.setToolTip("Objetivo óptico utilizado para recolectar la señal espectral.")
        vbox_optics.addWidget(lbl_obj)
        self.combo_objective = QComboBox()
        for obj_name in MICROSCOPE_OBJECTIVES.keys():
            self.combo_objective.addItem(obj_name)
        self.combo_objective.setCurrentIndex(0)
        self.combo_objective.setToolTip("Selecciona el objetivo para calcular la escala espacial exacta (µm/px) y apertura numérica NA.")
        self.combo_objective.currentIndexChanged.connect(self._on_objective_changed)
        vbox_optics.addWidget(self.combo_objective)

        first_obj = list(MICROSCOPE_OBJECTIVES.values())[0]
        self.lbl_pixel_scale = QLabel(f"Escala: {first_obj['pixel_scale_um']:.4f} µm/px | NA {first_obj['na']:.2f}")
        self.lbl_pixel_scale.setStyleSheet("color: #a6e3a1; font-weight: bold;")
        vbox_optics.addWidget(self.lbl_pixel_scale)

        lbl_disp = QLabel("Calibración de Dispersión:")
        lbl_disp.setToolTip("Calibración del eje de longitudes de onda (nm) por píxel del espectrógrafo.")
        vbox_optics.addWidget(lbl_disp)
        self.lbl_calib_status = QLabel("Origen: SIF Nativo")
        self.lbl_calib_status.setStyleSheet("color: #89b4fa; font-size: 11px;")
        vbox_optics.addWidget(self.lbl_calib_status)

        h_calib = QHBoxLayout()
        self.btn_load_calib = QPushButton("📥 Calib (.txt)")
        self.btn_load_calib.setToolTip("Carga una calibración de longitudes de onda externa en archivo de texto.")
        self.btn_load_calib.clicked.connect(self._on_load_external_calib)
        self.btn_reset_calib = QPushButton("↺ Nativo")
        self.btn_reset_calib.setToolTip("Restablece el eje espectral a los polinomios de calibración del archivo SIF.")
        self.btn_reset_calib.clicked.connect(self._on_reset_calib)
        h_calib.addWidget(self.btn_load_calib)
        h_calib.addWidget(self.btn_reset_calib)
        vbox_optics.addLayout(h_calib)

        self.chk_calculate_errors = QCheckBox("Propagar Incertidumbres (±σ_T)")
        self.chk_calculate_errors.setChecked(True)
        self.chk_calculate_errors.setStyleSheet("color: #f9e2af; font-weight: bold;")
        self.chk_calculate_errors.setToolTip(make_tooltip(
            "Propagación de Incertidumbres ±σ_T",
            "Dibuja una banda sombreada alrededor de la curva de transmitancia calculada que representa "
            "cuánto podría variar la medición debido al ruido real del detector. Una banda angosta indica "
            "una medición confiable; una banda ancha indica que conviene aumentar la exposición o promediar más.",
            "Propaga en cuadratura la incertidumbre fotónica de Poisson (√N) y la varianza de lectura/oscuro "
            "del EMCCD (σ_dark²) a través de T(λ) = Live/Ref según el criterio ISO/GUM (k=1), sumando "
            "términos de covarianza cuando Live y Ref comparten el mismo canal de fondo."
        ))
        self.chk_calculate_errors.toggled.connect(self._schedule_recalculation)
        vbox_optics.addWidget(self.chk_calculate_errors)

        layout.addWidget(grp_optics)
        layout.addStretch(1)

        scroll.setWidget(container)
        return scroll

    # --------------------------------------------------------------------------
    # PANEL DERECHO: OPCIONES CONTEXTUALES DE LA VENTANA ACTIVA
    # --------------------------------------------------------------------------
    def _create_right_panel(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        # Grupo: Opciones Contextuales de la Ventana Activa (QStackedWidget)
        grp_context_options = QGroupBox("⚙️ Opciones del Panel Activo")
        vbox_context = QVBoxLayout(grp_context_options)
        vbox_context.setContentsMargins(4, 4, 4, 4)
        self.stack_options = QStackedWidget()
        self.stack_options.addWidget(self._create_dark_options_page())
        self.stack_options.addWidget(self._create_ref_options_page())
        self.stack_options.addWidget(self._create_live_options_page())
        self.stack_options.addWidget(self._create_trans_options_page())
        self.stack_options.addWidget(self._create_ext_options_page())
        self.stack_options.addWidget(self._create_multi_options_page())
        self.stack_options.addWidget(self._create_metrology_options_page())
        vbox_context.addWidget(self.stack_options)
        layout.addWidget(grp_context_options, stretch=1)

        scroll.setWidget(container)
        return scroll

    # --------------------------------------------------------------------------
    # PANEL CENTRAL: 5 VENTANAS DE PROCESO SEPARADAS
    # --------------------------------------------------------------------------
    def _create_center_process_tabs(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Fase 4: barra superior con acceso global a la Wiki Científica
        # (instancia singleton gestionada por esta ventana — ver _open_wiki_note()).
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(2, 0, 2, 0)
        top_bar.addStretch()
        self.btn_wiki_global = QPushButton("📖 Wiki Científica")
        self.btn_wiki_global.setToolTip(make_tooltip(
            "Wiki Científica de PyPrinting 3.0",
            "Abre el navegador de documentación con los compendios científicos (CAT), reportes de sistema (SYS) y manuales de módulo (MOD) del proyecto.",
            "Ventana flotante no modal (ScientificWikiBrowserDialog) — permanece abierta junto a esta ventana. Navega por defecto a CAT-108 (fundamentos ópticos del canal confocal)."
        ))
        self.btn_wiki_global.clicked.connect(lambda: self._open_wiki_note("CAT-108"))
        top_bar.addWidget(self.btn_wiki_global)

        self.btn_toggle_right = QPushButton("👁️ Opciones")
        self.btn_toggle_right.setCheckable(True)
        self.btn_toggle_right.setChecked(True)
        self.btn_toggle_right.setToolTip(make_tooltip(
            "Alternar Panel de Opciones (Ctrl+D)",
            "Muestra u oculta el panel lateral derecho con las opciones y parámetros de la pestaña activa.",
            "Permite colapsar el panel de parámetros para maximizar el área de visualización gráfica de espectros y mapas 2D."
        ))
        self.btn_toggle_right.clicked.connect(self._on_toggle_right_panel)
        top_bar.addWidget(self.btn_toggle_right)

        layout.addLayout(top_bar)

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

        # Ventana 6: Multi-Espectro & Polarización
        tab_multi = self._create_multi_tab()
        self.tabs_process.addTab(tab_multi, "📈 6. Multi-Espectro & Polarización")

        # Ventana 7: Ficha Metrológica & FAIR
        tab_metrology = self._create_metrology_tab()
        self.tabs_process.addTab(tab_metrology, "📋 7. Ficha Metrológica")

        self.tabs_process.currentChanged.connect(self._on_main_tab_changed)

        return widget

    # ==========================================================================
    # PÁGINA 0 DE self.stack_options: OPCIONES DE RUIDO / DARK
    # ==========================================================================
    def _create_dark_options_page(self) -> QWidget:
        page = QWidget()
        vbox_dark_ctrls = QVBoxLayout(page)
        vbox_dark_ctrls.setContentsMargins(0, 0, 0, 0)
        vbox_dark_ctrls.setSpacing(4)

        row1_dark = QHBoxLayout()
        self.lbl_dark_source = QLabel("Origen Ruido: --")
        self.lbl_dark_source.setStyleSheet("color: #f9e2af; font-weight: bold; font-size: 11px;")
        self.lbl_dark_source.setToolTip("Indica de qué archivo y canal físico proviene el ruido de fondo (Dark).")
        row1_dark.addWidget(self.lbl_dark_source)

        self.chk_dark_despike = QCheckBox("Despike")
        self.chk_dark_despike.setChecked(True)
        self.chk_dark_despike.setToolTip(make_tooltip(
            "Despike (Eliminación de Rayos Cósmicos)",
            "Limpia picos aislados y anómalos que no son parte del espectro real, como destellos de rayos "
            "cósmicos que impactan el sensor CCD durante la exposición. No suaviza la forma general de la señal.",
            "Detección de outliers por umbral de desviación local (mediana móvil ± k·σ) seguida de "
            "interpolación puntual. Preserva la forma espectral física evitando el sesgo de un filtro "
            "pasabajos convencional."
        ))
        self.chk_dark_despike.toggled.connect(self._schedule_recalculation)
        row1_dark.addWidget(self.chk_dark_despike)

        self.btn_dark_psd = QPushButton("🔍 Ver PSD")
        self.btn_dark_psd.setToolTip("Abre la ventana de diagnóstico de Densidad Espectral de Potencia (PSD) y desvío espacial del sensor.")
        self.btn_dark_psd.clicked.connect(self._on_view_dark_psd)
        row1_dark.addWidget(self.btn_dark_psd)
        row1_dark.addStretch()
        vbox_dark_ctrls.addLayout(row1_dark)

        row1b_dark = QHBoxLayout()
        self.btn_reset_dark = QPushButton("↺ Raw")
        self.btn_reset_dark.setToolTip("Desactiva los filtros en el canal de ruido para ver la señal cruda.")
        self.btn_reset_dark.clicked.connect(self._on_reset_dark_filters)
        row1b_dark.addWidget(self.btn_reset_dark)

        btn_auto_dark = QPushButton("Auto-Escala")
        btn_auto_dark.setToolTip("Ajusta automáticamente los rangos de los ejes para encuadrar la señal.")
        btn_auto_dark.clicked.connect(lambda: self.plot_dark_1d.autoRange())
        row1b_dark.addWidget(btn_auto_dark)
        row1b_dark.addStretch()
        vbox_dark_ctrls.addLayout(row1b_dark)

        row2_dark = QHBoxLayout()
        lbl_d_filt = QLabel("Filtro Suavizado:")
        lbl_d_filt.setToolTip("Algoritmo matemático de filtrado espectral para el ruido de fondo.")
        row2_dark.addWidget(lbl_d_filt)
        self.combo_dark_filter = QComboBox()
        self.combo_dark_filter.addItems(["Ninguno", "Savitzky-Golay", "Fourier Lowpass", "Media Móvil"])
        self.combo_dark_filter.setToolTip(make_tooltip(
            "Filtro de Suavizado Savitzky-Golay",
            "Suaviza el espectro dibujando una curva local que sigue la tendencia general sin aplanar los "
            "picos reales, a diferencia de un promedio simple que los recorta.",
            "Ajuste polinomial local de mínimos cuadrados por ventana deslizante: preserva momentos "
            "estadísticos de orden ≤ p (posición, ancho, altura de picos) a diferencia de un filtro FIR "
            "pasabajos de fase no lineal."
        ))
        self.combo_dark_filter.currentIndexChanged.connect(self._schedule_recalculation)
        row2_dark.addWidget(self.combo_dark_filter)

        lbl_d_win = QLabel("Ventana:")
        lbl_d_win.setToolTip("Longitud de la ventana en píxeles espectrales (debe ser impar).")
        row2_dark.addWidget(lbl_d_win)
        self.spin_dark_param = QSpinBox()
        self.spin_dark_param.setRange(3, 101)
        self.spin_dark_param.setSingleStep(2)
        self.spin_dark_param.setValue(15)
        self.spin_dark_param.setToolTip("Número de píxeles para la ventana móvil del filtro.")
        self.spin_dark_param.valueChanged.connect(self._schedule_recalculation)
        row2_dark.addWidget(self.spin_dark_param)
        vbox_dark_ctrls.addLayout(row2_dark)

        row3_dark = QHBoxLayout()
        lbl_dark_contrast = QLabel("Contraste 2D:")
        row3_dark.addWidget(lbl_dark_contrast)
        self.combo_dark_contrast = _build_contrast_combo()
        self.combo_dark_contrast.currentIndexChanged.connect(self._on_dark_contrast_changed)
        row3_dark.addWidget(self.combo_dark_contrast)
        vbox_dark_ctrls.addLayout(row3_dark)

        self.chk_dark_hist = QCheckBox("📊 Histograma/LUT")
        self.chk_dark_hist.setToolTip("Muestra el editor interactivo de niveles y curva de transferencia (gamma) del mapa 2D de Ruido.")
        self.chk_dark_hist.toggled.connect(self._on_dark_hist_toggled)
        vbox_dark_ctrls.addWidget(self.chk_dark_hist)

        vbox_dark_ctrls.addStretch()
        return page

    # ==========================================================================
    # VENTANA 1: RUIDO / DARK
    # ==========================================================================
    def _create_dark_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Splitter 2D y 1D para Ruido
        self.splitter_dark = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(self.splitter_dark, stretch=1)

        # Sub-panel 2D Ruido
        self.widget_dark_2d = QWidget()
        vbox_d2d = QVBoxLayout(self.widget_dark_2d)
        vbox_d2d.setContentsMargins(0, 0, 0, 0)
        row_d2d = QHBoxLayout()
        self.plot_dark_2d = pg.PlotWidget(title="Mapa Espacial 2D de Ruido de Fondo")
        self.plot_dark_2d.setLabel('bottom', "Longitud de onda", units='nm')
        self.plot_dark_2d.setLabel('left', "Píxel vertical (Y)", units='px')
        self.img_dark_2d = pg.ImageItem()
        self.img_dark_2d.setColorMap(pg.colormap.get('viridis'))
        self.plot_dark_2d.addItem(self.img_dark_2d)
        self.vLine_dark2d = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen('#f9e2af', width=1, style=Qt.PenStyle.DashLine))
        self.hLine_dark2d = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen('#f9e2af', width=1, style=Qt.PenStyle.DashLine))
        self.plot_dark_2d.addItem(self.vLine_dark2d, ignoreBounds=True)
        self.plot_dark_2d.addItem(self.hLine_dark2d, ignoreBounds=True)
        self.plot_dark_2d.scene().sigMouseMoved.connect(self._on_mouse_moved_dark_2d)
        row_d2d.addWidget(self.plot_dark_2d, stretch=1)
        self.hist_dark_2d = pg.HistogramLUTWidget()
        self.hist_dark_2d.setImageItem(self.img_dark_2d)
        self.hist_dark_2d.setVisible(False)
        row_d2d.addWidget(self.hist_dark_2d)
        vbox_d2d.addLayout(row_d2d)
        self.lbl_dark_2d_hud = QLabel("λ = -- | Y = -- | Intensidad = --")
        self.lbl_dark_2d_hud.setStyleSheet("color: #f9e2af; font-family: Consolas, monospace; font-size: 10px;")
        vbox_d2d.addWidget(self.lbl_dark_2d_hud)
        self.splitter_dark.addWidget(self.widget_dark_2d)

        # Sub-panel 1D Ruido
        self.plot_dark_1d = pg.PlotWidget(title="Espectro 1D de Ruido (Cuentas vs Longitud de Onda)")
        self.plot_dark_1d.showGrid(x=True, y=True, alpha=0.3)
        self.plot_dark_1d.setLabel('bottom', "Longitud de onda", units='nm')
        self.plot_dark_1d.setLabel('left', "Cuentas de Ruido (Counts)")
        self.plot_dark_1d.addLegend(offset=(20, 20))
        self.splitter_dark.addWidget(self.plot_dark_1d)
        self.splitter_dark.setSizes([260, 440])

        # Tarjeta de métricas del ruido (Metrología Unitaria)
        self.lbl_dark_metrics = QLabel("Métricas Ruido: Bias Medio: -- | Desvío σ_dark: -- | Mín: -- | Máx: --")
        self.lbl_dark_metrics.setWordWrap(True)
        self.lbl_dark_metrics.setStyleSheet("color: #89b4fa; font-weight: bold; background-color: #11111b; padding: 6px; border-radius: 5px;")
        layout.addWidget(self._wrap_in_metrology_box(self.lbl_dark_metrics))

        return widget

    # ==========================================================================
    # VENTANA 2: REFERENCIA
    # ==========================================================================
    def _create_ref_options_page(self) -> QWidget:
        page = QWidget()
        vbox_ref_ctrls = QVBoxLayout(page)
        vbox_ref_ctrls.setContentsMargins(0, 0, 0, 0)
        vbox_ref_ctrls.setSpacing(4)

        # Fila 1: Selección de Origen y Región Espacial (ROI) - Entrada
        row1_ref = QHBoxLayout()
        self.lbl_ref_source = QLabel("Origen Referencia: --")
        self.lbl_ref_source.setStyleSheet("color: #fab387; font-weight: bold; font-size: 11px;")
        self.lbl_ref_source.setToolTip("Reporta si la referencia proviene del archivo activo o si es heredada del Maestro.")
        row1_ref.addWidget(self.lbl_ref_source)
        vbox_ref_ctrls.addLayout(row1_ref)

        row1b_ref = QHBoxLayout()
        lbl_ref_src = QLabel("Fuente:")
        lbl_ref_src.setToolTip("Prioridad de asignación del canal de referencia espectral.")
        row1b_ref.addWidget(lbl_ref_src)
        self.combo_ref_source = QComboBox()
        self.combo_ref_source.addItems(["Auto (Propia o Maestro)", "Forzar Propia del Archivo", "Forzar 👑 Maestro"])
        self.combo_ref_source.setToolTip("Auto: usa la propia si el archivo tiene canal 'reference', de lo contrario hereda la del Maestro.\nForzar Propia: exige referencia local del archivo.\nForzar Maestro: siempre utiliza la referencia del archivo Maestro.")
        self.combo_ref_source.currentIndexChanged.connect(self._schedule_recalculation)
        row1b_ref.addWidget(self.combo_ref_source)
        vbox_ref_ctrls.addLayout(row1b_ref)

        row1c_ref = QHBoxLayout()
        lbl_r_ymin = QLabel("ROI Y Min:")
        lbl_r_ymin.setToolTip("Límite inferior del píxel vertical (ranura CCD) a promediar.")
        row1c_ref.addWidget(lbl_r_ymin)
        self.spin_ref_ymin = QSpinBox()
        self.spin_ref_ymin.setRange(0, 2000)
        self.spin_ref_ymin.setValue(10)
        self.spin_ref_ymin.setToolTip(make_tooltip(
            "ROI Espacial Vertical (Y Min/Max)",
            "Define la franja vertical del sensor (en la dirección de la ranura de entrada) que se promedia "
            "para obtener el espectro 1D. También se puede ajustar arrastrando la banda horizontal directamente "
            "sobre el mapa 2D.",
            "Selecciona las filas [Y_min, Y_max) del detector 2D a integrar antes del cociente T=Live/Ref. "
            "Un ROI angosto reduce la señal disponible (más ruido de disparo); uno ancho puede promediar "
            "regiones con distinta iluminación (aberración de campo, viñeteado)."
        ))
        self.spin_ref_ymin.valueChanged.connect(self._on_ref_roi_spinners_changed)
        row1c_ref.addWidget(self.spin_ref_ymin)

        lbl_r_ymax = QLabel("Max:")
        lbl_r_ymax.setToolTip("Límite superior del píxel vertical a promediar.")
        row1c_ref.addWidget(lbl_r_ymax)
        self.spin_ref_ymax = QSpinBox()
        self.spin_ref_ymax.setRange(0, 2000)
        self.spin_ref_ymax.setValue(50)
        self.spin_ref_ymax.setToolTip("Píxel vertical superior de la Región de Interés (ROI).")
        self.spin_ref_ymax.valueChanged.connect(self._on_ref_roi_spinners_changed)
        row1c_ref.addWidget(self.spin_ref_ymax)
        vbox_ref_ctrls.addLayout(row1c_ref)

        row1d_ref = QHBoxLayout()
        lbl_r_mode = QLabel("Modo:")
        lbl_r_mode.setToolTip("Método de integración vertical: Promedio o Suma.")
        row1d_ref.addWidget(lbl_r_mode)
        self.combo_ref_roimode = QComboBox()
        self.combo_ref_roimode.addItems(["Promedio", "Suma"])
        self.combo_ref_roimode.setToolTip("Promedio: normaliza por el número de filas del ROI.\nSuma: acumula el conteo total de fotones de todas las filas.")
        self.combo_ref_roimode.currentIndexChanged.connect(self._schedule_recalculation)
        row1d_ref.addWidget(self.combo_ref_roimode)
        row1d_ref.addStretch()
        btn_auto_ref = QPushButton("Auto-Escala")
        btn_auto_ref.setToolTip("Auto-escala los ejes del gráfico de referencia.")
        btn_auto_ref.clicked.connect(lambda: self.plot_ref_1d.autoRange())
        row1d_ref.addWidget(btn_auto_ref)
        vbox_ref_ctrls.addLayout(row1d_ref)

        # Fila 2: Acondicionamiento Físico y Filtros Espectrales (2D y 1D) - Proceso
        row2_ref = QHBoxLayout()
        self.chk_ref_sub_dark = QCheckBox("Restar Ruido Dark")
        self.chk_ref_sub_dark.setChecked(True)
        self.chk_ref_sub_dark.setToolTip("Resta el ruido de fondo CCD (Dark) tanto a la matriz 2D como al espectro 1D de referencia (omitido automáticamente si Solis ya lo corrigió).")
        self.chk_ref_sub_dark.toggled.connect(self._schedule_recalculation)
        row2_ref.addWidget(self.chk_ref_sub_dark)

        self.chk_ref_despike = QCheckBox("Despike")
        self.chk_ref_despike.setChecked(True)
        self.chk_ref_despike.setToolTip("Elimina rayos cósmicos y píxeles anómalos fila a fila en el mapa 2D y en el espectro 1D.")
        self.chk_ref_despike.toggled.connect(self._schedule_recalculation)
        row2_ref.addWidget(self.chk_ref_despike)
        vbox_ref_ctrls.addLayout(row2_ref)

        row2b_ref = QHBoxLayout()
        self.chk_ref_adaptive = QCheckBox("Wiener Adaptativo")
        self.chk_ref_adaptive.setToolTip(make_tooltip(
            "Filtro Wiener Adaptativo (Físico)",
            "Limpia el ruido de fondo del detector usando el 'sonido' característico del ruido de la cámara "
            "(medido en la pestaña de Ruido/Dark) para saber qué frecuencias suprimir sin borrar la señal real.",
            "Filtro óptimo de Wiener en el dominio de Fourier: W(f) = |S(f)|² / (|S(f)|² + α·N(f)), donde N(f) "
            "es la PSD de ruido caracterizada experimentalmente y α controla la agresividad de la "
            "sobre-sustracción espectral."
        ))
        self.chk_ref_adaptive.toggled.connect(self._schedule_recalculation)
        row2b_ref.addWidget(self.chk_ref_adaptive)

        self.spin_ref_wiener_alpha = QDoubleSpinBox()
        self.spin_ref_wiener_alpha.setRange(0.1, 10.0)
        self.spin_ref_wiener_alpha.setSingleStep(0.1)
        self.spin_ref_wiener_alpha.setValue(1.0)
        self.spin_ref_wiener_alpha.setPrefix("α: ")
        self.spin_ref_wiener_alpha.setToolTip("Factor de sobre-sustracción espectral α para el filtro Wiener en referencia (0.5 suave, 1.0 estándar, 2.0 agresivo).")
        self.spin_ref_wiener_alpha.valueChanged.connect(self._schedule_recalculation)
        row2b_ref.addWidget(self.spin_ref_wiener_alpha)
        vbox_ref_ctrls.addLayout(row2b_ref)

        row2c_ref = QHBoxLayout()
        lbl_r_filt = QLabel("Filtro:")
        lbl_r_filt.setToolTip("Filtro espectral de suavizado para la lámpara/referencia.")
        row2c_ref.addWidget(lbl_r_filt)
        self.combo_ref_filter = QComboBox()
        self.combo_ref_filter.addItems(["Ninguno", "Savitzky-Golay", "Fourier Lowpass", "Media Móvil", "Wiener Adaptativo (BG)"])
        self.combo_ref_filter.setToolTip("Seleccione el filtro espectral para la referencia: Savitzky-Golay, Fourier Lowpass, Media Móvil o Wiener.")
        self.combo_ref_filter.currentIndexChanged.connect(self._schedule_recalculation)
        row2c_ref.addWidget(self.combo_ref_filter)

        lbl_r_win = QLabel("Vent.:")
        lbl_r_win.setToolTip("Longitud de ventana del filtro (píxeles).")
        row2c_ref.addWidget(lbl_r_win)
        self.spin_ref_param = QSpinBox()
        self.spin_ref_param.setRange(3, 101)
        self.spin_ref_param.setSingleStep(2)
        self.spin_ref_param.setValue(11)
        self.spin_ref_param.setToolTip("Tamaño de la ventana de suavizado espectral (debe ser impar).")
        self.spin_ref_param.valueChanged.connect(self._schedule_recalculation)
        row2c_ref.addWidget(self.spin_ref_param)
        vbox_ref_ctrls.addLayout(row2c_ref)

        self.btn_reset_ref = QPushButton("↺ Raw")
        self.btn_reset_ref.setToolTip("Desactiva temporalmente los filtros de referencia para inspeccionar la señal cruda.")
        self.btn_reset_ref.clicked.connect(self._on_reset_ref_filters)
        vbox_ref_ctrls.addWidget(self.btn_reset_ref)

        row3_ref = QHBoxLayout()
        lbl_ref_contrast = QLabel("Contraste 2D:")
        row3_ref.addWidget(lbl_ref_contrast)
        self.combo_ref_contrast = _build_contrast_combo()
        self.combo_ref_contrast.currentIndexChanged.connect(self._on_ref_contrast_changed)
        row3_ref.addWidget(self.combo_ref_contrast)
        vbox_ref_ctrls.addLayout(row3_ref)

        self.chk_ref_hist = QCheckBox("📊 Histograma/LUT")
        self.chk_ref_hist.setToolTip("Muestra el editor interactivo de niveles y curva de transferencia (gamma) del mapa 2D de Referencia.")
        self.chk_ref_hist.toggled.connect(self._on_ref_hist_toggled)
        vbox_ref_ctrls.addWidget(self.chk_ref_hist)

        vbox_ref_ctrls.addStretch()
        return page

    # ==========================================================================
    # VENTANA 2: REFERENCIA
    # ==========================================================================
    def _create_ref_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

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
        row_r2d = QHBoxLayout()
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
        self.vLine_ref2d = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen('#89b4fa', width=1, style=Qt.PenStyle.DashLine))
        self.hLine_ref2d = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen('#89b4fa', width=1, style=Qt.PenStyle.DashLine))
        self.plot_ref_2d.addItem(self.vLine_ref2d, ignoreBounds=True)
        self.plot_ref_2d.addItem(self.hLine_ref2d, ignoreBounds=True)
        self.plot_ref_2d.scene().sigMouseMoved.connect(self._on_mouse_moved_ref_2d)
        row_r2d.addWidget(self.plot_ref_2d, stretch=1)
        self.hist_ref_2d = pg.HistogramLUTWidget()
        self.hist_ref_2d.setImageItem(self.img_ref_2d)
        self.hist_ref_2d.setVisible(False)
        row_r2d.addWidget(self.hist_ref_2d)
        vbox_r2d.addLayout(row_r2d)
        self.lbl_ref_2d_hud = QLabel("λ = -- | Y = -- | Intensidad = --")
        self.lbl_ref_2d_hud.setStyleSheet("color: #fab387; font-family: Consolas, monospace; font-size: 10px;")
        vbox_r2d.addWidget(self.lbl_ref_2d_hud)
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

        # Tarjeta de métricas de Referencia (Metrología Unitaria)
        self.lbl_ref_metrics = QLabel("Métricas Referencia: Cuentas Medias ROI: -- | Pico Lámpara: -- | Desvío Espacial: --")
        self.lbl_ref_metrics.setWordWrap(True)
        self.lbl_ref_metrics.setStyleSheet("color: #fab387; font-weight: bold; background-color: #11111b; padding: 6px; border-radius: 5px;")
        layout.addWidget(self._wrap_in_metrology_box(self.lbl_ref_metrics))

        return widget

    # ==========================================================================
    # VENTANA 3: LIVE / SEÑAL
    # ==========================================================================
    def _create_live_options_page(self) -> QWidget:
        page = QWidget()
        vbox_live_ctrls = QVBoxLayout(page)
        vbox_live_ctrls.setContentsMargins(0, 0, 0, 0)
        vbox_live_ctrls.setSpacing(4)

        # Fila 1: Selección de Muestra y Región Espacial (ROI) - Entrada
        row1_live = QHBoxLayout()
        lbl_l_samp = QLabel("Muestra Activa:")
        lbl_l_samp.setToolTip("Selecciona el espectro de muestra del lote cargado.")
        row1_live.addWidget(lbl_l_samp)
        self.combo_live_sample = QComboBox()
        self.combo_live_sample.setToolTip("Lista de espectros cargados para alternar rápidamente entre muestras.")
        self.combo_live_sample.currentIndexChanged.connect(self._on_live_sample_selected)
        row1_live.addWidget(self.combo_live_sample)
        vbox_live_ctrls.addLayout(row1_live)

        row1b_live = QHBoxLayout()
        lbl_l_ymin = QLabel("ROI Y Min:")
        lbl_l_ymin.setToolTip("Píxel vertical inferior de la ranura CCD a integrar.")
        row1b_live.addWidget(lbl_l_ymin)
        self.spin_live_ymin = QSpinBox()
        self.spin_live_ymin.setRange(0, 2000)
        self.spin_live_ymin.setValue(10)
        self.spin_live_ymin.setToolTip("Límite inferior del ROI vertical para extraer el espectro 1D.")
        self.spin_live_ymin.valueChanged.connect(self._on_live_roi_spinners_changed)
        row1b_live.addWidget(self.spin_live_ymin)

        lbl_l_ymax = QLabel("Max:")
        lbl_l_ymax.setToolTip("Píxel vertical superior de la ranura CCD a integrar.")
        row1b_live.addWidget(lbl_l_ymax)
        self.spin_live_ymax = QSpinBox()
        self.spin_live_ymax.setRange(0, 2000)
        self.spin_live_ymax.setValue(50)
        self.spin_live_ymax.setToolTip("Límite superior del ROI vertical para extraer el espectro 1D.")
        self.spin_live_ymax.valueChanged.connect(self._on_live_roi_spinners_changed)
        row1b_live.addWidget(self.spin_live_ymax)
        vbox_live_ctrls.addLayout(row1b_live)

        row1c_live = QHBoxLayout()
        lbl_l_mode = QLabel("Modo:")
        lbl_l_mode.setToolTip("Método de integración vertical: Promedio o Suma.")
        row1c_live.addWidget(lbl_l_mode)
        self.combo_live_roimode = QComboBox()
        self.combo_live_roimode.addItems(["Promedio", "Suma"])
        self.combo_live_roimode.setToolTip("Promedio: normaliza por el número de filas del ROI.\nSuma: acumula el conteo total de fotones de todas las filas.")
        self.combo_live_roimode.currentIndexChanged.connect(self._schedule_recalculation)
        row1c_live.addWidget(self.combo_live_roimode)
        vbox_live_ctrls.addLayout(row1c_live)

        row1d_live = QHBoxLayout()
        self.btn_sync_roi = QPushButton("📋 Copiar ROI de Referencia")
        self.btn_sync_roi.setToolTip("Sincroniza los límites espaciales (ROI Y Min/Max) con los definidos en la Ventana de Referencia.")
        self.btn_sync_roi.clicked.connect(self._on_sync_roi_to_live)
        self.btn_copy_ref_roi = self.btn_sync_roi  # Alias de compatibilidad (nombre de contrato de la Fase 2)
        row1d_live.addWidget(self.btn_sync_roi)
        btn_auto_live = QPushButton("Auto-Escala")
        btn_auto_live.setToolTip("Auto-escala los ejes del gráfico de señal.")
        btn_auto_live.clicked.connect(lambda: self.plot_live_1d.autoRange())
        row1d_live.addWidget(btn_auto_live)
        vbox_live_ctrls.addLayout(row1d_live)

        # Fila 2: Acondicionamiento Físico y Filtros Espectrales (2D y 1D) - Proceso
        row2_live = QHBoxLayout()
        self.chk_live_sub_dark = QCheckBox("Restar Ruido Dark")
        self.chk_live_sub_dark.setChecked(True)
        self.chk_live_sub_dark.setToolTip("Resta el ruido de fondo (Dark) a la matriz 2D y al espectro 1D de la muestra.")
        self.chk_live_sub_dark.toggled.connect(self._schedule_recalculation)
        row2_live.addWidget(self.chk_live_sub_dark)

        self.chk_live_despike = QCheckBox("Despike")
        self.chk_live_despike.setChecked(True)
        self.chk_live_despike.setToolTip("Elimina rayos cósmicos y eventos espurios en la imagen 2D y en el espectro 1D.")
        self.chk_live_despike.toggled.connect(self._schedule_recalculation)
        row2_live.addWidget(self.chk_live_despike)
        vbox_live_ctrls.addLayout(row2_live)

        row2b_live = QHBoxLayout()
        self.chk_live_adaptive = QCheckBox("Wiener Adaptativo")
        self.chk_live_adaptive.setToolTip("Filtro Wiener adaptativo que limpia el ruido en la matriz 2D y 1D según la caracterización del fondo CCD.")
        self.chk_live_adaptive.toggled.connect(self._schedule_recalculation)
        row2b_live.addWidget(self.chk_live_adaptive)

        self.spin_live_wiener_alpha = QDoubleSpinBox()
        self.spin_live_wiener_alpha.setRange(0.1, 10.0)
        self.spin_live_wiener_alpha.setSingleStep(0.1)
        self.spin_live_wiener_alpha.setValue(1.0)
        self.spin_live_wiener_alpha.setPrefix("α: ")
        self.spin_live_wiener_alpha.setToolTip("Factor α del filtro Wiener para la señal de muestra (0.5 suave, 1.0 estándar, 2.0 agresivo).")
        self.spin_live_wiener_alpha.valueChanged.connect(self._schedule_recalculation)
        row2b_live.addWidget(self.spin_live_wiener_alpha)
        vbox_live_ctrls.addLayout(row2b_live)

        row2c_live = QHBoxLayout()
        lbl_l_filt = QLabel("Filtro:")
        lbl_l_filt.setToolTip("Filtro espectral de suavizado para la señal de muestra.")
        row2c_live.addWidget(lbl_l_filt)
        self.combo_live_filter = QComboBox()
        self.combo_live_filter.addItems(["Ninguno", "Savitzky-Golay", "Fourier Lowpass", "Media Móvil", "Wiener Adaptativo (BG)"])
        self.combo_live_filter.setToolTip("Seleccione el filtro espectral: Savitzky-Golay, Fourier Lowpass, Media Móvil o Wiener.")
        self.combo_live_filter.currentIndexChanged.connect(self._schedule_recalculation)
        row2c_live.addWidget(self.combo_live_filter)

        lbl_l_win = QLabel("Vent.:")
        lbl_l_win.setToolTip("Longitud de la ventana móvil de filtrado (píxeles).")
        row2c_live.addWidget(lbl_l_win)
        self.spin_live_param = QSpinBox()
        self.spin_live_param.setRange(3, 101)
        self.spin_live_param.setSingleStep(2)
        self.spin_live_param.setValue(11)
        self.spin_live_param.setToolTip("Tamaño de la ventana de suavizado (debe ser impar).")
        self.spin_live_param.valueChanged.connect(self._schedule_recalculation)
        row2c_live.addWidget(self.spin_live_param)
        vbox_live_ctrls.addLayout(row2c_live)

        self.btn_reset_live = QPushButton("↺ Raw")
        self.btn_reset_live.setToolTip("Desactiva temporalmente los filtros de señal para ver las cuentas crudas.")
        self.btn_reset_live.clicked.connect(self._on_reset_live_filters)
        vbox_live_ctrls.addWidget(self.btn_reset_live)

        row3_live = QHBoxLayout()
        lbl_live_contrast = QLabel("Contraste 2D:")
        row3_live.addWidget(lbl_live_contrast)
        self.combo_live_contrast = _build_contrast_combo()
        self.combo_live_contrast.currentIndexChanged.connect(self._on_live_contrast_changed)
        row3_live.addWidget(self.combo_live_contrast)
        vbox_live_ctrls.addLayout(row3_live)

        self.chk_live_hist = QCheckBox("📊 Histograma/LUT")
        self.chk_live_hist.setToolTip("Muestra el editor interactivo de niveles y curva de transferencia (gamma) del mapa 2D de Live/Señal.")
        self.chk_live_hist.toggled.connect(self._on_live_hist_toggled)
        vbox_live_ctrls.addWidget(self.chk_live_hist)

        vbox_live_ctrls.addStretch()
        return page

    # ==========================================================================
    # VENTANA 3: LIVE / SEÑAL
    # ==========================================================================
    def _create_live_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Splitter 2D y 1D para Live/Señal
        self.splitter_live = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(self.splitter_live, stretch=1)

        # Sub-panel 2D
        self.widget_live_2d = QWidget()
        vbox_l2d = QVBoxLayout(self.widget_live_2d)
        vbox_l2d.setContentsMargins(0, 0, 0, 0)
        row_l2d = QHBoxLayout()
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
        self.vLine_live2d = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen('#f38ba8', width=1, style=Qt.PenStyle.DashLine))
        self.hLine_live2d = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen('#f38ba8', width=1, style=Qt.PenStyle.DashLine))
        self.plot_live_2d.addItem(self.vLine_live2d, ignoreBounds=True)
        self.plot_live_2d.addItem(self.hLine_live2d, ignoreBounds=True)
        self.plot_live_2d.scene().sigMouseMoved.connect(self._on_mouse_moved_live_2d)
        row_l2d.addWidget(self.plot_live_2d, stretch=1)
        self.hist_live_2d = pg.HistogramLUTWidget()
        self.hist_live_2d.setImageItem(self.img_live_2d)
        self.hist_live_2d.setVisible(False)
        row_l2d.addWidget(self.hist_live_2d)
        vbox_l2d.addLayout(row_l2d)
        self.lbl_live_2d_hud = QLabel("λ = -- | Y = -- | Intensidad = --")
        self.lbl_live_2d_hud.setStyleSheet("color: #f38ba8; font-family: Consolas, monospace; font-size: 10px;")
        vbox_l2d.addWidget(self.lbl_live_2d_hud)
        self.splitter_live.addWidget(self.widget_live_2d)

        # Sub-panel 1D
        self.plot_live_1d = pg.PlotWidget(title="Espectro 1D de Señal / Muestra (Cuentas Promediadas en ROI)")
        self.plot_live_1d.showGrid(x=True, y=True, alpha=0.3)
        self.plot_live_1d.setLabel('bottom', "Longitud de onda", units='nm')
        self.plot_live_1d.setLabel('left', "Cuentas de Señal (Counts)")
        self.plot_live_1d.addLegend(offset=(20, 20))
        self.splitter_live.addWidget(self.plot_live_1d)
        self.splitter_live.setSizes([260, 440])

        # Tarjeta de métricas de Señal (Metrología Unitaria)
        self.lbl_live_metrics = QLabel("Métricas Señal: Cuentas Medias ROI: -- | Cuentas Pico: -- | Relación Señal/Fondo (SBR): --")
        self.lbl_live_metrics.setWordWrap(True)
        self.lbl_live_metrics.setStyleSheet("color: #f38ba8; font-weight: bold; background-color: #11111b; padding: 6px; border-radius: 5px;")
        layout.addWidget(self._wrap_in_metrology_box(self.lbl_live_metrics))

        return widget

    # ==========================================================================
    # VENTANA 4: TRANSMISIÓN
    # ==========================================================================
    def _create_trans_options_page(self) -> QWidget:
        page = QWidget()
        vbox_trans_ctrls = QVBoxLayout(page)
        vbox_trans_ctrls.setContentsMargins(0, 0, 0, 0)
        vbox_trans_ctrls.setSpacing(6)

        # Panel de Opciones de Cálculo 2D (Mutuamente excluyentes y umbrales)
        grp_calc_options = QGroupBox("⚙️ Opciones de Cálculo 2D")
        grp_calc_options.setToolTip("Panel de configuración del algoritmo de transmitancia 2D y descarte de ruido.")
        lay_calc_options = QVBoxLayout(grp_calc_options)
        lay_calc_options.setContentsMargins(8, 2, 8, 4)
        lay_calc_options.setSpacing(4)

        self.radio_route_a = QRadioButton("Ruta A (Pixel 2D)")
        self.radio_route_a.setChecked(True)
        self.radio_route_a.setToolTip("Ruta A: Cálculo pixel a pixel en el detector 2D T(y, λ) = Live/Ref y posterior promedio en el ROI vertical. Recomendada para muestras homogéneas.")
        self.radio_route_a.toggled.connect(self._schedule_recalculation)

        self.radio_route_b = QRadioButton("Ruta B (Promedios ROI)")
        self.radio_route_b.setToolTip("Ruta B: Promedia verticalmente las cuentas del ROI de Live y Ref por separado y luego calcula el cociente T(λ) = <Live>/<Ref>. Más robusta ante baja relación señal/ruido.")
        self.radio_route_b.toggled.connect(self._schedule_recalculation)

        self.route_btn_group = QButtonGroup(self)
        self.route_btn_group.addButton(self.radio_route_a)
        self.route_btn_group.addButton(self.radio_route_b)

        lay_calc_options.addWidget(self.radio_route_a)
        lay_calc_options.addWidget(self.radio_route_b)

        self.chk_compare_routes = QCheckBox("Comparar A y B")
        self.chk_compare_routes.setToolTip("Superpone simultáneamente la curva de Ruta B sobre Ruta A para evaluar gradientes y discrepancias espaciales.")
        self.chk_compare_routes.toggled.connect(self._refresh_transmittance_plots)
        lay_calc_options.addWidget(self.chk_compare_routes)

        row_gate = QHBoxLayout()
        lbl_t_gate = QLabel("Noise Gate:")
        row_gate.addWidget(lbl_t_gate)
        self.spin_trans_gate = QDoubleSpinBox()
        self.spin_trans_gate.setRange(0.0, 1000.0)
        self.spin_trans_gate.setValue(5.0)
        self.spin_trans_gate.setToolTip(make_tooltip(
            "Noise Gate (Umbral Anti-División-por-Cero)",
            "Ignora los píxeles donde la lámpara de referencia casi no llega (cuentas muy bajas), porque "
            "dividir por un número cercano a cero produce valores de transmitancia disparatados o infinitos.",
            "Máscara T(λ)=NaN donde Ref(λ) < noise_gate (en cuentas). Debe fijarse por encima de 3σ_dark "
            "para evitar que el propio ruido de fondo, y no la señal de lámpara, determine el corte."
        ))
        self.spin_trans_gate.valueChanged.connect(self._schedule_recalculation)
        row_gate.addWidget(self.spin_trans_gate)
        lay_calc_options.addLayout(row_gate)

        vbox_trans_ctrls.addWidget(grp_calc_options)

        # Panel de Post-Filtros en Cascada (Enfoque A: Despike -> Wiener -> Suavizado Contextual)
        grp_post_filters = QGroupBox("🧹 Pipeline de Filtrado en T(λ)")
        grp_post_filters.setToolTip("Cadena en cascada de 3 fases físicas para T(λ): 1) Despiking -> 2) Wiener Físico -> 3) Suavizado Espectral.")
        lay_post_filters = QVBoxLayout(grp_post_filters)
        lay_post_filters.setContentsMargins(8, 2, 8, 4)
        lay_post_filters.setSpacing(4)

        # Fase 1: Despiking en T(λ)
        row_desp = QHBoxLayout()
        self.chk_trans_despike = QCheckBox("Despike")
        self.chk_trans_despike.setToolTip("Fase 1: Elimina rayos cósmicos o picos espurios locales en el espectro de transmitancia.")
        self.chk_trans_despike.toggled.connect(self._schedule_recalculation)
        row_desp.addWidget(self.chk_trans_despike)

        self.spin_trans_despike_k = QDoubleSpinBox()
        self.spin_trans_despike_k.setRange(2.0, 15.0)
        self.spin_trans_despike_k.setSingleStep(0.5)
        self.spin_trans_despike_k.setValue(4.0)
        self.spin_trans_despike_k.setPrefix("k: ")
        self.spin_trans_despike_k.setToolTip("Umbral de detección de picos espurios (k * sigma).")
        self.spin_trans_despike_k.valueChanged.connect(self._schedule_recalculation)
        row_desp.addWidget(self.spin_trans_despike_k)
        lay_post_filters.addLayout(row_desp)

        # Fase 2: Wiener Adaptativo Físico (PSD Dark)
        row_wien = QHBoxLayout()
        self.chk_trans_wiener = QCheckBox("Wiener")
        self.chk_trans_adaptive = self.chk_trans_wiener  # Alias de compatibilidad
        self.chk_trans_wiener.setToolTip("Fase 2: Filtro óptimo de Wiener basado en la PSD experimental de ruido del fondo.")
        self.chk_trans_wiener.toggled.connect(self._schedule_recalculation)
        row_wien.addWidget(self.chk_trans_wiener)

        self.spin_trans_wiener_alpha = QDoubleSpinBox()
        self.spin_trans_wiener_alpha.setRange(0.1, 10.0)
        self.spin_trans_wiener_alpha.setSingleStep(0.1)
        self.spin_trans_wiener_alpha.setValue(1.0)
        self.spin_trans_wiener_alpha.setPrefix("α: ")
        self.spin_trans_wiener_alpha.setToolTip("Factor de agresividad α para el filtro Wiener sobre la transmitancia.")
        self.spin_trans_wiener_alpha.valueChanged.connect(self._schedule_recalculation)
        row_wien.addWidget(self.spin_trans_wiener_alpha)
        lay_post_filters.addLayout(row_wien)

        # Fase 3: Suavizado Espectral Matemático con Panel Sensible al Contexto
        row_filt = QHBoxLayout()
        lbl_t_filt = QLabel("Suavizado:")
        lbl_t_filt.setToolTip("Fase 3: Suavizado espectral matemático (Savitzky-Golay, Fourier Lowpass o Media Móvil).")
        row_filt.addWidget(lbl_t_filt)
        self.combo_trans_filter = QComboBox()
        self.combo_trans_filter.addItems(["Ninguno", "Savitzky-Golay", "Fourier Lowpass", "Media Móvil"])
        self.combo_trans_filter.setToolTip("Seleccione el algoritmo de suavizado matemático.")
        self.combo_trans_filter.currentIndexChanged.connect(self._on_trans_filter_type_changed)
        row_filt.addWidget(self.combo_trans_filter)
        lay_post_filters.addLayout(row_filt)

        # Controles Contextuales Dinámicos (Parámetro 1: Ventana o Frecuencia de corte)
        row_p1 = QHBoxLayout()
        self.lbl_trans_param1 = QLabel("Ventana:")
        self.lbl_trans_param1.setToolTip("Parámetro primario del filtro de suavizado.")
        row_p1.addWidget(self.lbl_trans_param1)

        self.spin_trans_param1 = QSpinBox()
        self.spin_trans_param = self.spin_trans_param1  # Alias de compatibilidad
        self.spin_trans_param1.setRange(3, 101)
        self.spin_trans_param1.setSingleStep(2)
        self.spin_trans_param1.setValue(15)
        self.spin_trans_param1.setToolTip("Ancho de la ventana de filtrado en puntos espectrales.")
        self.spin_trans_param1.valueChanged.connect(self._on_trans_param1_changed)
        row_p1.addWidget(self.spin_trans_param1)

        self.spin_trans_fc = QDoubleSpinBox()
        self.spin_trans_fc.setRange(0.01, 0.50)
        self.spin_trans_fc.setSingleStep(0.01)
        self.spin_trans_fc.setValue(0.05)
        self.spin_trans_fc.setDecimals(2)
        self.spin_trans_fc.setPrefix("fc: ")
        self.spin_trans_fc.setToolTip("Frecuencia de corte normalizada respecto a Nyquist (0.01 a 0.50).")
        self.spin_trans_fc.valueChanged.connect(self._schedule_recalculation)
        self.spin_trans_fc.setVisible(False)
        row_p1.addWidget(self.spin_trans_fc)
        lay_post_filters.addLayout(row_p1)

        # Controles Contextuales Dinámicos (Parámetro 2: Orden Polinomial para Savitzky-Golay)
        row_p2 = QHBoxLayout()
        self.lbl_trans_param2 = QLabel("Orden p:")
        self.lbl_trans_param2.setToolTip("Orden del polinomio de ajuste local en Savitzky-Golay (debe ser menor que la ventana).")
        row_p2.addWidget(self.lbl_trans_param2)

        self.spin_trans_param2 = QSpinBox()
        self.spin_trans_param2.setRange(1, 5)
        self.spin_trans_param2.setValue(3)
        self.spin_trans_param2.setToolTip("Grado del polinomio para Savitzky-Golay (1 a 5).")
        self.spin_trans_param2.valueChanged.connect(self._schedule_recalculation)
        row_p2.addWidget(self.spin_trans_param2)
        lay_post_filters.addLayout(row_p2)

        # Configurar estado inicial del panel sensible al contexto
        self._on_trans_filter_type_changed()

        vbox_trans_ctrls.addWidget(grp_post_filters)

        # Panel de Curvas Visibles
        grp_curves = QGroupBox("👁️ Curvas Visibles")
        grp_curves.setToolTip("Active o desactive las curvas y bandas a mostrar en el gráfico principal.")
        lay_curves = QVBoxLayout(grp_curves)
        lay_curves.setContentsMargins(8, 2, 8, 4)
        lay_curves.setSpacing(4)

        self.chk_show_tcalc = QCheckBox("T_calc (%)")
        self.chk_show_tcalc.setChecked(True)
        self.chk_show_tcalc.setStyleSheet("color: #a6e3a1; font-weight: bold;")
        self.chk_show_tcalc.setToolTip("Muestra u oculta la curva de Transmitancia Calculada físicamente: T_calc(λ) = Live / Ref con los filtros aplicados.")
        self.chk_show_tcalc.toggled.connect(self._refresh_transmittance_plots)
        lay_curves.addWidget(self.chk_show_tcalc)

        self.chk_show_tmeas = QCheckBox("T_meas SIF (%)")
        self.chk_show_tmeas.setChecked(True)
        self.chk_show_tmeas.setStyleSheet("color: #89b4fa; font-weight: bold;")
        self.chk_show_tmeas.setToolTip("Muestra u oculta la curva de Transmitancia medida originalmente por Andor Solis en el archivo SIF (Canal 0).")
        self.chk_show_tmeas.toggled.connect(self._refresh_transmittance_plots)
        lay_curves.addWidget(self.chk_show_tmeas)

        self.chk_show_ribbon = QCheckBox("Banda Incertidumbre (±σ_T)")
        self.chk_show_ribbon.setChecked(True)
        self.chk_show_ribbon.setStyleSheet("color: #f9e2af;")
        self.chk_show_ribbon.setToolTip("Muestra la banda sombreada de incertidumbre combinada (±1σ_T) calculada analíticamente para T_calc según ISO/GUM (ruido Poisson, readout EMCCD y varianza Dark).")
        self.chk_show_ribbon.toggled.connect(self._refresh_transmittance_plots)
        lay_curves.addWidget(self.chk_show_ribbon)

        vbox_trans_ctrls.addWidget(grp_curves)

        row_actions = QHBoxLayout()
        btn_auto_trans = QPushButton("Auto-Escala")
        btn_auto_trans.setToolTip("Auto-escala los ejes de transmitancia y residuos.")
        btn_auto_trans.clicked.connect(lambda: self.plot_trans_main.autoRange())
        row_actions.addWidget(btn_auto_trans)

        btn_recalc = QPushButton("⚡ Recalcular")
        btn_recalc.setObjectName("primaryBtn")
        btn_recalc.setToolTip("Fuerza un recálculo inmediato de todas las curvas y métricas en las 5 ventanas.")
        btn_recalc.clicked.connect(self._recalculate_all)
        row_actions.addWidget(btn_recalc)
        vbox_trans_ctrls.addLayout(row_actions)

        vbox_trans_ctrls.addStretch()
        return page

    # ==========================================================================
    # VENTANA 4: TRANSMISIÓN
    # ==========================================================================
    def _create_transmittance_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

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

        # Tarjeta de métricas de Transmisión (Metrología Unitaria)
        self.lbl_trans_metrics = QLabel("Métricas Transmisión: T_media: -- | Mín: -- | Máx: -- | Discrepancia RMS: -- | Incertidumbre Media: --")
        self.lbl_trans_metrics.setWordWrap(True)
        self.lbl_trans_metrics.setStyleSheet("color: #a6e3a1; font-weight: bold; background-color: #11111b; padding: 6px; border-radius: 5px;")
        layout.addWidget(self._wrap_in_metrology_box(self.lbl_trans_metrics))

        return widget

    # ==========================================================================
    # VENTANA 5: EXTINCIÓN Y AJUSTE DE PICOS (LSPR / FANO)
    # ==========================================================================
    def _create_ext_options_page(self) -> QWidget:
        page = QWidget()
        vbox_ext_ctrls = QVBoxLayout(page)
        vbox_ext_ctrls.setContentsMargins(0, 0, 0, 0)
        vbox_ext_ctrls.setSpacing(4)

        row0_ext = QHBoxLayout()
        lbl_e_form = QLabel("Fórmula:")
        lbl_e_form.setToolTip("Fórmula física para calcular la extinción o absorbancia óptica a partir de T(λ).")
        row0_ext.addWidget(lbl_e_form)
        self.combo_ext_formula = QComboBox()
        self.combo_ext_formula.addItems(["Absorbancia A = -log10(T/100)", "Extinción E = 1 - T/100"])
        self.combo_ext_formula.setToolTip("Absorbancia de Beer-Lambert A = -log10(T) o Extinción directa E = 1 - T.")
        self.combo_ext_formula.currentIndexChanged.connect(self._schedule_recalculation)
        row0_ext.addWidget(self.combo_ext_formula)
        vbox_ext_ctrls.addLayout(row0_ext)

        row1_ext = QHBoxLayout()
        self.chk_ext_adaptive = QCheckBox("Pre-filtrado Wiener")
        self.chk_ext_adaptive.setToolTip("Limpia el espectro de extinción antes de ejecutar el ajuste para mejorar la convergencia de picos.")
        self.chk_ext_adaptive.toggled.connect(self._schedule_recalculation)
        row1_ext.addWidget(self.chk_ext_adaptive)

        self.spin_ext_wiener_alpha = QDoubleSpinBox()
        self.spin_ext_wiener_alpha.setRange(0.1, 10.0)
        self.spin_ext_wiener_alpha.setSingleStep(0.1)
        self.spin_ext_wiener_alpha.setValue(1.0)
        self.spin_ext_wiener_alpha.setPrefix("α: ")
        self.spin_ext_wiener_alpha.setToolTip("Factor α del filtro Wiener sobre la extinción.")
        self.spin_ext_wiener_alpha.valueChanged.connect(self._schedule_recalculation)
        row1_ext.addWidget(self.spin_ext_wiener_alpha)
        vbox_ext_ctrls.addLayout(row1_ext)

        btn_auto_ext = QPushButton("Auto-Escala")
        btn_auto_ext.setToolTip("Auto-escala los ejes del gráfico de extinción.")
        btn_auto_ext.clicked.connect(lambda: self.plot_ext_main.autoRange())
        vbox_ext_ctrls.addWidget(btn_auto_ext)

        # Modelo de Ajuste, Número de Picos, Línea Base, ROI espectral y Ejecución
        row1b_ext = QHBoxLayout()
        lbl_e_npeaks = QLabel("N° de Picos:")
        lbl_e_npeaks.setToolTip("Número de resonancias a deconvolucionar simultáneamente en el ROI (1 a 5).")
        row1b_ext.addWidget(lbl_e_npeaks)
        self.spin_fit_n_peaks = QSpinBox()
        self.spin_fit_n_peaks.setRange(1, 5)
        self.spin_fit_n_peaks.setValue(1)
        self.spin_fit_n_peaks.setToolTip(make_tooltip(
            "Deconvolución Multi-Pico (1 a 5)",
            "Cuando dos o más resonancias plasmónicas se superponen en el espectro (por ejemplo, un dímero "
            "con modos longitudinal y transversal), un único perfil no alcanza a describir la forma real. "
            "Aumentar este número ajusta simultáneamente varios picos independientes y los separa.",
            "El semillado automático detecta hasta N máximos locales prominentes (scipy.signal.find_peaks) "
            "sobre la señal ya corregida de línea base; si se detectan menos, las semillas restantes se "
            "distribuyen equiespaciadas en el ROI antes del ajuste conjunto por mínimos cuadrados no lineales."
        ))
        row1b_ext.addWidget(self.spin_fit_n_peaks)
        vbox_ext_ctrls.addLayout(row1b_ext)

        row2_ext = QHBoxLayout()
        lbl_e_mod = QLabel("Modelo Ajuste:")
        lbl_e_mod.setToolTip("Función analítica de ajuste: Gaussiana, Lorentziana (LSPR clásica), Pseudo-Voigt (mezcla) o Fano (resonancia asimétrica).")
        row2_ext.addWidget(lbl_e_mod)
        self.combo_fit_model = QComboBox()
        self.combo_fit_model.addItems(["Gaussiano", "Lorentziano", "Pseudo-Voigt", "Resonancia de Fano"])
        self.combo_fit_model.setCurrentText("Pseudo-Voigt")
        self.combo_fit_model.setToolTip(make_tooltip(
            "Modelo de Ajuste: Fano vs Lorentziano vs Pseudo-Voigt",
            "Un pico simétrico y acampanado se describe bien con Lorentziano (o Gaussiano si el ensanchamiento "
            "es por dispersión de tamaños). Pseudo-Voigt mezcla ambos linealmente (fracción η) cuando ninguno "
            "solo alcanza. Si el pico luce asimétrico, con un 'hombro' o una caída abrupta a un lado, la "
            "Resonancia de Fano lo captura correctamente.",
            "Pseudo-Voigt: PV(x) = η·Lorentz(x) + (1-η)·Gauss(x), η ∈ [0,1]. Fano: interferencia entre un canal "
            "resonante discreto y un continuo de fondo, q = parámetro de asimetría; q→∞ recupera el límite "
            "Lorentziano. Elegir Fano cuando el R² de un ajuste simétrico sea sistemáticamente pobre."
        ))
        row2_ext.addWidget(self.combo_fit_model)
        vbox_ext_ctrls.addLayout(row2_ext)

        row2b_ext = QHBoxLayout()
        lbl_e_base = QLabel("Línea Base:")
        lbl_e_base.setToolTip("Fondo a sustraer antes de ajustar los picos: fluorescencia ancha, dispersión no resonante del sustrato, etc.")
        row2b_ext.addWidget(lbl_e_base)
        self.combo_fit_baseline = QComboBox()
        self.combo_fit_baseline.addItems(["Ninguno", "Constante", "Lineal", "AsLS Whittaker"])
        self.combo_fit_baseline.setCurrentText("AsLS Whittaker")
        self.combo_fit_baseline.setToolTip(make_tooltip(
            "Sustracción de Línea Base AsLS (Asymmetric Least Squares)",
            "Remueve un fondo suave (fluorescencia, dispersión difusa del sustrato) que de otro modo se "
            "confundiría con la señal de los picos, dejando sólo las resonancias reales para el ajuste.",
            "Whittaker pentadiagonal (Eilers & Boelens 2005): minimiza Σw(y-z)² + λΣ(Δ²z)² con pesos "
            "asimétricos w = p si (y-z)>0 sino (1-p), iterado hasta convergencia. λ controla la rigidez de "
            "la línea base; p controla cuánto se penalizan los residuos por encima de ella (picos)."
        ))
        self.combo_fit_baseline.currentIndexChanged.connect(self._on_fit_baseline_type_changed)
        row2b_ext.addWidget(self.combo_fit_baseline)
        vbox_ext_ctrls.addLayout(row2b_ext)

        row2c_ext = QHBoxLayout()
        self.lbl_fit_asls_lam = QLabel("λ (rigidez):")
        row2c_ext.addWidget(self.lbl_fit_asls_lam)
        self.spin_fit_asls_lam = QDoubleSpinBox()
        self.spin_fit_asls_lam.setDecimals(0)
        self.spin_fit_asls_lam.setRange(1.0e2, 1.0e7)
        self.spin_fit_asls_lam.setValue(1.0e5)
        self.spin_fit_asls_lam.setSingleStep(1.0e4)
        self.spin_fit_asls_lam.setToolTip("Parámetro de suavidad λ del AsLS (10² a 10⁷): mayor valor → línea base más rígida/plana.")
        row2c_ext.addWidget(self.spin_fit_asls_lam)

        self.lbl_fit_asls_p = QLabel("p (asimetría):")
        row2c_ext.addWidget(self.lbl_fit_asls_p)
        self.spin_fit_asls_p = QDoubleSpinBox()
        self.spin_fit_asls_p.setDecimals(4)
        self.spin_fit_asls_p.setRange(0.001, 0.05)
        self.spin_fit_asls_p.setSingleStep(0.001)
        self.spin_fit_asls_p.setValue(0.001)
        self.spin_fit_asls_p.setToolTip("Factor de asimetría p del AsLS (0.001 a 0.05): penaliza los residuos positivos (picos) sobre la línea base.")
        row2c_ext.addWidget(self.spin_fit_asls_p)
        vbox_ext_ctrls.addLayout(row2c_ext)

        row3_ext = QHBoxLayout()
        lbl_e_lmin = QLabel("ROI λ Min:")
        lbl_e_lmin.setToolTip("Longitud de onda mínima del intervalo de ajuste (nm).")
        row3_ext.addWidget(lbl_e_lmin)
        self.spin_fit_lmin = QDoubleSpinBox()
        self.spin_fit_lmin.setRange(200.0, 2500.0)
        self.spin_fit_lmin.setValue(600.0)
        self.spin_fit_lmin.setSingleStep(5.0)
        self.spin_fit_lmin.setToolTip("Límite espectral inferior (también arrastrable en el gráfico).")
        self.spin_fit_lmin.valueChanged.connect(self._on_fit_spinners_changed)
        row3_ext.addWidget(self.spin_fit_lmin)

        lbl_e_lmax = QLabel("Max:")
        lbl_e_lmax.setToolTip("Longitud de onda máxima del intervalo de ajuste (nm).")
        row3_ext.addWidget(lbl_e_lmax)
        self.spin_fit_lmax = QDoubleSpinBox()
        self.spin_fit_lmax.setRange(200.0, 2500.0)
        self.spin_fit_lmax.setValue(750.0)
        self.spin_fit_lmax.setSingleStep(5.0)
        self.spin_fit_lmax.setToolTip("Límite espectral superior (también arrastrable en el gráfico).")
        self.spin_fit_lmax.valueChanged.connect(self._on_fit_spinners_changed)
        row3_ext.addWidget(self.spin_fit_lmax)
        vbox_ext_ctrls.addLayout(row3_ext)

        row4_ext = QHBoxLayout()
        lbl_e_slit = QLabel("Ranura (µm):")
        lbl_e_slit.setToolTip("Ancho de la ranura de entrada del espectrógrafo (para propagar resolución instrumental).")
        row4_ext.addWidget(lbl_e_slit)
        self.spin_fit_slit = QDoubleSpinBox()
        self.spin_fit_slit.setRange(10.0, 2500.0)
        self.spin_fit_slit.setValue(100.0)
        self.spin_fit_slit.setToolTip("Ancho de rendija (Slit) leído del archivo SIF o definido manualmente.")
        row4_ext.addWidget(self.spin_fit_slit)
        vbox_ext_ctrls.addLayout(row4_ext)

        row_fit_btns = QHBoxLayout()
        self.btn_run_fit = QPushButton("⚡ Ajustar Modelo en ROI")
        self.btn_run_fit.setObjectName("accentBtn")
        self.btn_run_fit.setToolTip("Ejecuta la deconvolución multi-pico por mínimos cuadrados no lineales y reporta λ_pico, FWHM, áreas e incertidumbres por cada pico.")
        self.btn_run_fit.clicked.connect(self._on_run_peak_fit)
        row_fit_btns.addWidget(self.btn_run_fit)

        self.btn_clear_fit = QPushButton("🧹 Limpiar Ajuste")
        self.btn_clear_fit.setToolTip("Descarta el ajuste actual y limpia la tabla de parámetros y las curvas superpuestas.")
        self.btn_clear_fit.clicked.connect(self._on_clear_peak_fit)
        row_fit_btns.addWidget(self.btn_clear_fit)
        vbox_ext_ctrls.addLayout(row_fit_btns)

        self.btn_export_fit = QPushButton("💾 Exportar Ajuste")
        self.btn_export_fit.setToolTip("Exporta los parámetros de ajuste y las curvas ajustadas a un archivo .txt.")
        self.btn_export_fit.clicked.connect(self._on_export_peak_fit)
        vbox_ext_ctrls.addWidget(self.btn_export_fit)

        self._on_fit_baseline_type_changed()

        vbox_ext_ctrls.addStretch()
        return page

    # ==========================================================================
    # VENTANA 5: EXTINCIÓN Y AJUSTE DE PICOS (LSPR / FANO)
    # ==========================================================================
    def _create_extinction_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

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

        # Tabla de Parámetros de Ajuste Multi-Pico (1 fila por pico deconvolucionado)
        self.table_fit_peaks = QTableWidget()
        self.table_fit_peaks.setColumnCount(8)
        self.table_fit_peaks.setHorizontalHeaderLabels(
            ["Pico #", "λ_pico (nm)", "FWHM (nm)", "Amplitud H", "Área", "Hᵢ/H₀", "Parámetro (q o η)", "R²"]
        )
        self.table_fit_peaks.horizontalHeader().setStretchLastSection(True)
        self.table_fit_peaks.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_fit_peaks.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_fit_peaks.setMaximumHeight(160)
        self.table_fit_peaks.setToolTip(make_tooltip(
            "Tabla de Parámetros de Ajuste Multi-Pico",
            "Cada fila resume un pico detectado: dónde está (λ_pico), qué tan ancho es (FWHM), qué tan alto "
            "(Amplitud) y qué fracción representa del pico principal (Hᵢ/H₀). Útil para comparar la intensidad "
            "relativa entre modos plasmónicos acoplados.",
            "λ_pico y FWHM se reportan con su incertidumbre combinada u_c (ajuste ⊕ ranura ⊕ cuantización de "
            "píxel). El 'Parámetro' es η (fracción Lorentziana, Pseudo-Voigt) o q (asimetría de Fano), según "
            "el modelo activo; queda vacío para Gaussiano/Lorentziano puros."
        ))
        layout.addWidget(self.table_fit_peaks)

        # Tarjeta de Metrología Unitaria: resumen global del ajuste (OD_max, λ_res, Q, R², chi2_red)
        grp_ext_metrics = QGroupBox("📐 Metrología Unitaria")
        vbox_ext_metrics = QVBoxLayout(grp_ext_metrics)
        self.lbl_fit_results = QLabel(
            "Resultados del Ajuste: Seleccione el ROI espectral con las reglas arrastrables y presione '⚡ Ajustar Modelo en ROI'."
        )
        self.lbl_fit_results.setWordWrap(True)
        self.lbl_fit_results.setStyleSheet(
            "color: #cba6f7; font-weight: bold; background-color: #11111b; padding: 8px; border-radius: 5px; font-size: 11px;"
        )
        vbox_ext_metrics.addWidget(self.lbl_fit_results)
        layout.addWidget(grp_ext_metrics)

        return widget

    # ==========================================================================
    # PÁGINA 5 DE self.stack_options: OPCIONES MULTI-ESPECTRO & POLARIZACIÓN
    # ==========================================================================
    def _create_multi_options_page(self) -> QWidget:
        page = QWidget()
        vbox = QVBoxLayout(page)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(4)

        row_mode = QHBoxLayout()
        row_mode.addWidget(QLabel("Modo:"))
        self.combo_multi_mode = QComboBox()
        self.combo_multi_mode.addItems(["Superposición (Overlay)", "Cascada (Waterfall 2.5D)"])
        self.combo_multi_mode.setToolTip(make_tooltip(
            "Modo de Visualización Multi-Espectro",
            "Superposición dibuja todas las curvas seleccionadas sobre los mismos ejes, útil para comparar "
            "formas y posiciones de pico directamente. Cascada las desplaza progresivamente en X/Y, útil "
            "para inspeccionar visualmente muchos espectros sin que se tapen entre sí.",
            "En modo Cascada, la curva k-ésima (k=0,1,2,...) se desplaza (k·ΔX, k·ΔY) en las unidades "
            "nativas de la curva seleccionada (nm en X; cuentas, % o unidades de extinción en Y)."
        ))
        row_mode.addWidget(self.combo_multi_mode)
        vbox.addLayout(row_mode)

        row_curve = QHBoxLayout()
        row_curve.addWidget(QLabel("Curva:"))
        self.combo_multi_curve = QComboBox()
        self.combo_multi_curve.addItems(["Transmitancia T_calc", "Extinción / Absorbancia", "Señal Live (Counts)", "Transmitancia T_meas"])
        row_curve.addWidget(self.combo_multi_curve)
        vbox.addLayout(row_curve)

        row_norm = QHBoxLayout()
        row_norm.addWidget(QLabel("Normalización:"))
        self.combo_multi_norm = QComboBox()
        self.combo_multi_norm.addItems(["Ninguna", "Normalizar [0, 1]", "Dividir por Máximo"])
        row_norm.addWidget(self.combo_multi_norm)
        vbox.addLayout(row_norm)

        row_offsets = QHBoxLayout()
        row_offsets.addWidget(QLabel("ΔY Cascada:"))
        self.spin_multi_dy = QDoubleSpinBox()
        self.spin_multi_dy.setRange(0.0, 1.0e6)
        self.spin_multi_dy.setValue(1.0)
        self.spin_multi_dy.setDecimals(3)
        self.spin_multi_dy.setSingleStep(0.1)
        row_offsets.addWidget(self.spin_multi_dy)
        row_offsets.addWidget(QLabel("ΔX Cascada:"))
        self.spin_multi_dx = QDoubleSpinBox()
        self.spin_multi_dx.setRange(-500.0, 500.0)
        self.spin_multi_dx.setValue(0.0)
        self.spin_multi_dx.setDecimals(2)
        self.spin_multi_dx.setSingleStep(1.0)
        row_offsets.addWidget(self.spin_multi_dx)
        vbox.addLayout(row_offsets)

        self.btn_multi_refresh = QPushButton("🔄 Actualizar Multi-Espectro")
        self.btn_multi_refresh.setObjectName("primaryBtn")
        self.btn_multi_refresh.setToolTip("Redibuja el comparador con los archivos actualmente marcados (casilla 'Sel') en la tabla de la izquierda.")
        self.btn_multi_refresh.clicked.connect(self._refresh_multi_spectrum_plot)
        vbox.addWidget(self.btn_multi_refresh)

        grp_pol = QGroupBox("🧭 Dicroísmo y Polarización Plasmónica")
        vbox_pol = QVBoxLayout(grp_pol)
        row_pol_lambda = QHBoxLayout()
        row_pol_lambda.addWidget(QLabel("λ_res (nm):"))
        self.spin_multi_pol_lambda = QDoubleSpinBox()
        self.spin_multi_pol_lambda.setRange(200.0, 2500.0)
        self.spin_multi_pol_lambda.setValue(650.0)
        self.spin_multi_pol_lambda.setSingleStep(5.0)
        self.spin_multi_pol_lambda.setToolTip(make_tooltip(
            "Longitud de Onda de Resonancia para el Análisis de Polarización",
            "Fija en qué color del espectro se mide la intensidad de cada archivo antes de ajustar la Ley "
            "de Malus — habitualmente el pico de la resonancia plasmónica de interés.",
            "Se interpola linealmente la curva seleccionada (T_calc/Extinción/Live/T_meas) en λ_res para "
            "cada archivo con ángulo de polarización detectable en su nombre, formando la serie I(θ_pol)."
        ))
        row_pol_lambda.addWidget(self.spin_multi_pol_lambda)
        vbox_pol.addLayout(row_pol_lambda)

        self.btn_run_malus = QPushButton("⚡ Ajustar Ley de Malus")
        self.btn_run_malus.setObjectName("accentBtn")
        self.btn_run_malus.setToolTip(make_tooltip(
            "Ley de Malus Generalizada y Factor de Anisotropía g",
            "Detecta automáticamente el ángulo del polarizador en el nombre de cada archivo cargado (ej. "
            "'_45deg', 'pol90') y ajusta cómo varía la señal con ese ángulo, revelando si la nanoestructura "
            "responde de forma distinta según la orientación de la luz incidente (dicroísmo).",
            "I(θ) = I_min + (I_max - I_min)·cos²(θ - θ₀). g = 2(I_par - I_perp)/(I_par + 2·I_perp), con "
            "I_par = I_max e I_perp = I_min. Requiere ≥3 archivos con ángulo de polarización reconocible."
        ))
        self.btn_run_malus.clicked.connect(self._on_run_malus_fit)
        vbox_pol.addWidget(self.btn_run_malus)
        vbox.addWidget(grp_pol)

        vbox.addStretch()
        return page

    # ==========================================================================
    # VENTANA 6: MULTI-ESPECTRO & POLARIZACIÓN
    # ==========================================================================
    def _create_multi_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self.tabs_multi_internal = QTabWidget()
        layout.addWidget(self.tabs_multi_internal, stretch=1)

        # Sub-tab A: Visualizador Multi-Curva (Overlay / Cascada)
        sub_curves = QWidget()
        vbox_c = QVBoxLayout(sub_curves)
        vbox_c.setContentsMargins(0, 0, 0, 0)
        self.plot_multi_curves = pg.PlotWidget(title="Comparador Multi-Espectro (Overlay / Cascada)")
        self.plot_multi_curves.showGrid(x=True, y=True, alpha=0.3)
        self.plot_multi_curves.setLabel('bottom', "Longitud de onda", units='nm')
        self.plot_multi_curves.setLabel('left', "Intensidad (según curva y normalización)")
        self.plot_multi_curves.addLegend(offset=(20, 20))
        vbox_c.addWidget(self.plot_multi_curves)
        self.tabs_multi_internal.addTab(sub_curves, "📊 Visualizador Multi-Curva")

        # Sub-tab B: Gráfico Polar de Dicroísmo
        sub_polar = QWidget()
        vbox_p = QVBoxLayout(sub_polar)
        vbox_p.setContentsMargins(0, 0, 0, 0)
        self.plot_multi_polar = pg.PlotWidget(title="Dicroísmo y Polarización: A(θ_pol) — Proyección Polar")
        self.plot_multi_polar.showGrid(x=True, y=True, alpha=0.2)
        self.plot_multi_polar.setLabel('bottom', "I · cos(θ)")
        self.plot_multi_polar.setLabel('left', "I · sin(θ)")
        self.plot_multi_polar.setAspectLocked(True)
        self.plot_multi_polar.addLegend(offset=(20, 20))
        vbox_p.addWidget(self.plot_multi_polar)

        grp_polar_metrics = QGroupBox("📐 Metrología Unitaria")
        vbox_polar_metrics = QVBoxLayout(grp_polar_metrics)
        self.lbl_polar_metrics = QLabel(
            "Resultados de Polarización: cargue ≥3 archivos con ángulo detectable en el nombre y presione '⚡ Ajustar Ley de Malus'."
        )
        self.lbl_polar_metrics.setWordWrap(True)
        self.lbl_polar_metrics.setStyleSheet(
            "color: #94e2d5; font-weight: bold; background-color: #11111b; padding: 8px; border-radius: 5px; font-size: 11px;"
        )
        vbox_polar_metrics.addWidget(self.lbl_polar_metrics)
        vbox_p.addWidget(grp_polar_metrics)
        self.tabs_multi_internal.addTab(sub_polar, "🧭 Dicroísmo y Polarización")

        return widget

    # ==========================================================================
    # PÁGINA 6 DE self.stack_options: OPCIONES FICHA METROLÓGICA & FAIR
    # ==========================================================================
    def _create_metrology_options_page(self) -> QWidget:
        page = QWidget()
        vbox = QVBoxLayout(page)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(4)

        lbl_info = QLabel("Ficha de Trazabilidad Metrológica y Exportación FAIR del espectro activo.")
        lbl_info.setWordWrap(True)
        lbl_info.setStyleSheet("color: #a6adc8; font-size: 11px;")
        vbox.addWidget(lbl_info)

        self.btn_export_hdf5 = QPushButton("💾 Exportar Sesión HDF5 / NeXus")
        self.btn_export_hdf5.setObjectName("accentBtn")
        self.btn_export_hdf5.setToolTip(make_tooltip(
            "Exportación FAIR a HDF5 / NeXus",
            "Guarda toda la sesión activa (metadatos del instrumento, curvas procesadas y resultados del "
            "ajuste) en un único archivo binario abierto y comprimido, legible por cualquier lenguaje "
            "científico (Python, MATLAB, Julia) sin depender del software propietario de Andor.",
            "Sigue la ontología NeXus (NXroot/NXentry/NXinstrument/NXdata/NXprocess, CAT-402) con "
            "compresión gzip nivel 4 + shuffle, consistente con core.hdf5_container. Requiere h5py (opcional)."
        ))
        self.btn_export_hdf5.clicked.connect(self._on_export_session_hdf5)
        vbox.addWidget(self.btn_export_hdf5)

        self.btn_copy_ficha = QPushButton("📋 Copiar Ficha al Portapapeles")
        self.btn_copy_ficha.setToolTip("Copia la ficha metrológica en texto Markdown al portapapeles del sistema.")
        self.btn_copy_ficha.clicked.connect(self._on_copy_ficha_clipboard)
        vbox.addWidget(self.btn_copy_ficha)

        self.btn_export_ficha_md = QPushButton("📥 Exportar Ficha (.md)")
        self.btn_export_ficha_md.setToolTip("Guarda la ficha metrológica completa como Markdown listo para un cuaderno de laboratorio o repositorio.")
        self.btn_export_ficha_md.clicked.connect(self._on_export_ficha_markdown)
        vbox.addWidget(self.btn_export_ficha_md)

        vbox.addStretch()
        return page

    # ==========================================================================
    # VENTANA 7: FICHA METROLÓGICA & FAIR
    # ==========================================================================
    def _create_metrology_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self.text_metrology_ficha = QTextBrowser()
        self.text_metrology_ficha.setOpenExternalLinks(False)
        self.text_metrology_ficha.setStyleSheet(
            "QTextBrowser { background-color: #11111b; color: #cdd6f4; border: 1px solid #313244; "
            "border-radius: 6px; padding: 10px; font-size: 12px; }"
        )
        self.text_metrology_ficha.setHtml(self._render_report_html({}))
        layout.addWidget(self.text_metrology_ficha, stretch=1)

        return widget

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

    def _setup_all_plot_export_menus(self):
        """Fase 4: habilita el menú contextual de clic derecho (FigureExportStudio) en todos los gráficos principales de la suite."""
        plot_specs = [
            (self.plot_dark_1d, "ruido_1d", "Espectro 1D de Ruido"),
            (self.plot_dark_2d, "ruido_2d", "Mapa 2D de Ruido"),
            (self.plot_ref_1d, "referencia_1d", "Espectro 1D de Referencia"),
            (self.plot_ref_2d, "referencia_2d", "Mapa 2D de Referencia"),
            (self.plot_ref_compare, "comparador_referencias", "Comparador de Referencias"),
            (self.plot_live_1d, "senal_1d", "Espectro 1D de Señal"),
            (self.plot_live_2d, "senal_2d", "Mapa 2D de Señal"),
            (self.plot_trans_main, "transmitancia", "Transmitancia"),
            (self.plot_trans_residuals, "transmitancia_residuos", "Residuos de Transmitancia"),
            (self.plot_ext_main, "extincion", "Extinción y Ajuste Multi-Pico"),
            (self.plot_ext_residuals, "extincion_residuos", "Residuos del Ajuste"),
            (self.plot_multi_curves, "multi_espectro", "Multi-Espectro"),
            (self.plot_multi_polar, "polarizacion_malus", "Polarización — Ley de Malus"),
        ]
        for plot_widget, default_name, display_title in plot_specs:
            self._setup_plot_export_menu(plot_widget, default_name, display_title)

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
            chk.setToolTip("Activar o desactivar este espectro en comparativas y cálculos.")
            chk.stateChanged.connect(lambda state, r=row: self._schedule_recalculation())
            chk_widget = QWidget()
            chk_lay = QHBoxLayout(chk_widget)
            chk_lay.addWidget(chk)
            chk_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chk_lay.setContentsMargins(0, 0, 0, 0)
            self.table_files.setCellWidget(row, 0, chk_widget)

            # Nombre / Alias completo
            name_text = ("👑 " if spec is self.master_spectrum else "") + spec.custom_name
            item_name = QTableWidgetItem(name_text)
            fpath = getattr(spec.metadata, 'filepath', spec.custom_name) if hasattr(spec, 'metadata') and spec.metadata else spec.custom_name
            item_name.setToolTip(f"Ruta completa: {fpath}\nNombre: {spec.custom_name}")
            if spec is self.master_spectrum:
                item_name.setForeground(QColor("#a6e3a1"))
                font = item_name.font()
                font.setBold(True)
                item_name.setFont(font)
            self.table_files.setItem(row, 1, item_name)

            # Canales
            ch_count = spec.channels_count
            ch_desc = f"{ch_count} ch ({'2D' if spec.is_2d else '1D'})"
            item_ch = QTableWidgetItem(ch_desc)
            ch_names = ', '.join(spec.channels.keys()) if hasattr(spec, 'channels') else ch_desc
            item_ch.setToolTip(f"Canales presentes en este archivo: {ch_names}")
            item_ch.setFlags(item_ch.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table_files.setItem(row, 2, item_ch)

            # Rol / Estado
            role_desc = "👑 Maestro" if spec is self.master_spectrum else ("Muestra Completa" if ch_count == 4 else "Hereda Maestro")
            item_role = QTableWidgetItem(role_desc)
            item_role.setToolTip(f"Estado en el lote: {role_desc}")
            item_role.setFlags(item_role.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if spec is self.master_spectrum:
                item_role.setForeground(QColor("#a6e3a1"))
            self.table_files.setItem(row, 3, item_role)

        self.table_files.resizeColumnsToContents()
        self.table_files.setColumnWidth(0, 42)
        if self.table_files.columnWidth(1) < 180:
            self.table_files.setColumnWidth(1, 180)
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

            self._update_meta_badge(spec)

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

    # ==========================================================================
    # FASE 4: EXPORTACIÓN CIENTÍFICA UNIVERSAL (FigureExportStudio) POR CLIC DERECHO
    # ==========================================================================
    def _export_plot_to_svg(self, plot_widget: pg.PlotWidget, file_path: str):
        """Exporta de forma robusta y nativa un PlotWidget a formato SVG vectorial usando QSvgGenerator de Qt6."""
        try:
            from PyQt6.QtSvg import QSvgGenerator
            from PyQt6.QtGui import QPainter
            generator = QSvgGenerator()
            generator.setFileName(file_path)
            rect = plot_widget.plotItem.sceneBoundingRect()
            if rect.width() <= 0 or rect.height() <= 0:
                rect = plot_widget.rect()
            generator.setSize(rect.size().toSize())
            generator.setViewBox(rect)
            painter = QPainter()
            painter.begin(generator)
            plot_widget.plotItem.scene().render(painter, rect, rect)
            painter.end()
        except Exception:
            exporter = pg_export.SVGExporter(plot_widget.plotItem)
            exporter.export(file_path)

    def _export_single_plot(self, plot_widget: pg.PlotWidget, default_name: str):
        """Exporta un gráfico individual en alta resolución PNG (2400 px, 600 DPI) o SVG vectorial."""
        file_path, _ = QFileDialog.getSaveFileName(
            self, f"Exportar Gráfico: {default_name}", f"{default_name}.png",
            "Imagen PNG de Alta Resolución (*.png);;Gráfico Vectorial SVG (*.svg);;Todos los Archivos (*.*)"
        )
        if not file_path:
            return
        try:
            if file_path.lower().endswith(".svg"):
                self._export_plot_to_svg(plot_widget, file_path)
            else:
                if not file_path.lower().endswith(".png"):
                    file_path += ".png"
                exporter = pg_export.ImageExporter(plot_widget.plotItem)
                exporter.parameters()['width'] = 2400  # 600 DPI equivalente
                exporter.export(file_path)
            QMessageBox.information(self, "Exportación Exitosa", f"Gráfico guardado exitosamente en:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error al Exportar Gráfico", f"No se pudo exportar el gráfico:\n{str(e)}")

    def _open_figure_export_studio(self, plot_widget: pg.PlotWidget, default_name: str, display_title: str = ""):
        """Abre el diálogo interactivo de exportación científica multicapa (FigureExportStudioDialog)."""
        try:
            dlg = FigureExportStudioDialog(plot_widget, parent=self, title=display_title, default_filename=default_name)
            dlg.exec()
        except Exception as e:
            QMessageBox.critical(self, "Error en Estudio de Exportación", f"No se pudo abrir el estudio de exportación:\n{str(e)}")

    def _setup_plot_export_menu(self, plot_widget: pg.PlotWidget, default_name: str, display_title: str):
        """Habilita menú contextual de clic derecho para exportar (FigureExportStudio / rápido) y auto-rango en el gráfico."""
        plot_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        def _show_context_menu(pos):
            menu = QMenu(self)
            menu.setStyleSheet(
                "QMenu { background-color: #1e1e2e; color: #cdd6f4; border: 1px solid #45475a; font-size: 11px; } "
                "QMenu::item { padding: 5px 18px; } "
                "QMenu::item:selected { background-color: #313244; color: #89b4fa; }"
            )
            act_studio = menu.addAction("🎨 Abrir en Estudio de Exportación Científica (SVG / PNG 600 DPI)...")
            act_studio.triggered.connect(lambda: self._open_figure_export_studio(plot_widget, default_name, display_title))
            menu.addSeparator()
            act_exp = menu.addAction(f"💾 Exportar Rápido '{display_title}' (PNG 600 DPI / SVG)...")
            act_exp.triggered.connect(lambda: self._export_single_plot(plot_widget, default_name))
            act_reset = menu.addAction("🔍 Restablecer Vista (Auto-Rango)")
            act_reset.triggered.connect(plot_widget.enableAutoRange)
            menu.exec(plot_widget.mapToGlobal(pos))

        plot_widget.customContextMenuRequested.connect(_show_context_menu)

    def _open_wiki_note(self, note_id: Optional[str], anchor: Optional[str] = None) -> None:
        """Abre (o reutiliza, patrón singleton) la Wiki Científica navegando directamente a note_id."""
        if self._wiki_dialog is None:
            self._wiki_dialog = ScientificWikiBrowserDialog(parent=self)
        if note_id:
            self._wiki_dialog.navigate_to(note_id, anchor)
        self._wiki_dialog.show()
        self._wiki_dialog.raise_()
        self._wiki_dialog.activateWindow()

    def _wrap_in_metrology_box(self, label_widget: QLabel) -> QGroupBox:
        """Envuelve una etiqueta de métricas en el marco estandarizado 'Metrología Unitaria' (Fase 3)."""
        grp = QGroupBox("📐 Metrología Unitaria")
        lay = QVBoxLayout(grp)
        lay.setContentsMargins(6, 4, 6, 6)
        lay.addWidget(label_widget)
        return grp

    def _current_scale_um(self) -> float:
        obj_name = self.combo_objective.currentText()
        obj_info = MICROSCOPE_OBJECTIVES.get(obj_name)
        if obj_info is None:
            obj_info = list(MICROSCOPE_OBJECTIVES.values())[0]
        return float(obj_info["pixel_scale_um"])

    def _update_meta_badge(self, spec: SifSpectrum):
        """Actualiza la insignia de la tarjeta de metadatos distinguiendo Imagen Espacial 2D de Espectro 1D (FVB)."""
        if spec.is_2d or spec.height > 1:
            self.lbl_meta_badge.setText("🗺️ Imagen Espacial 2D")
            self.lbl_meta_badge.setStyleSheet("color: #cba6f7; font-weight: bold; font-size: 12px;")
            self.lbl_meta_dims.setText(f"Dimensiones: {spec.height} (Y) × {spec.width} (X) px")
            scale_um = self._current_scale_um()
            fov_y = spec.height * scale_um
            self.lbl_meta_scale_range.setText(
                f"Escala: {scale_um:.4f} µm/px | FOV_Y: {fov_y:.2f} µm"
            )
        else:
            self.lbl_meta_badge.setText("📊 Espectro 1D (FVB / Full Vertical Binning)")
            self.lbl_meta_badge.setStyleSheet("color: #89dceb; font-weight: bold; font-size: 12px;")
            self.lbl_meta_dims.setText(f"Canales: {spec.width} px")
            wl = spec.wavelengths
            if wl is not None and len(wl) > 1:
                span = float(wl[-1] - wl[0])
                dispersion = span / max(1, len(wl) - 1)
                self.lbl_meta_scale_range.setText(
                    f"Rango espectral: {wl[0]:.1f} nm - {wl[-1]:.1f} nm (Δλ = {span:.1f} nm) | "
                    f"Dispersión: {dispersion:.3f} nm/px"
                )
            else:
                self.lbl_meta_scale_range.setText("Rango espectral: --")

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

    def _on_trans_filter_type_changed(self):
        """Reconfigura dinámicamente el panel de parámetros según el algoritmo de suavizado seleccionado."""
        filt_name = self.combo_trans_filter.currentText()
        if "Savitzky" in filt_name:
            self.lbl_trans_param1.setText("Ventana:")
            self.lbl_trans_param1.setVisible(True)
            self.spin_trans_param1.setVisible(True)
            self.spin_trans_fc.setVisible(False)
            self.spin_trans_param1.setRange(3, 101)
            self.spin_trans_param1.setSingleStep(2)
            if self.spin_trans_param1.value() % 2 == 0:
                self.spin_trans_param1.setValue(self.spin_trans_param1.value() + 1)
            self.lbl_trans_param2.setText("Orden p:")
            self.lbl_trans_param2.setVisible(True)
            self.spin_trans_param2.setVisible(True)
            self.spin_trans_param2.setMaximum(max(1, self.spin_trans_param1.value() - 1))
        elif "Fourier" in filt_name:
            self.lbl_trans_param1.setText("Corte fc:")
            self.lbl_trans_param1.setVisible(True)
            self.spin_trans_param1.setVisible(False)
            self.spin_trans_fc.setVisible(True)
            self.lbl_trans_param2.setVisible(False)
            self.spin_trans_param2.setVisible(False)
        elif "Media" in filt_name:
            self.lbl_trans_param1.setText("Ventana:")
            self.lbl_trans_param1.setVisible(True)
            self.spin_trans_param1.setVisible(True)
            self.spin_trans_fc.setVisible(False)
            self.spin_trans_param1.setRange(2, 51)
            self.spin_trans_param1.setSingleStep(1)
            self.lbl_trans_param2.setVisible(False)
            self.spin_trans_param2.setVisible(False)
        else:  # Ninguno
            self.lbl_trans_param1.setVisible(False)
            self.spin_trans_param1.setVisible(False)
            self.spin_trans_fc.setVisible(False)
            self.lbl_trans_param2.setVisible(False)
            self.spin_trans_param2.setVisible(False)
        self._schedule_recalculation()

    def _on_trans_param1_changed(self):
        """Valida paridad impar y acota el orden polinomial si el filtro activo es Savitzky-Golay."""
        filt_name = self.combo_trans_filter.currentText()
        if "Savitzky" in filt_name:
            val = self.spin_trans_param1.value()
            if val % 2 == 0:
                self.spin_trans_param1.setValue(val + 1)
                return
            self.spin_trans_param2.setMaximum(max(1, val - 1))
        self._schedule_recalculation()

    def _on_fit_baseline_type_changed(self):
        """Muestra los parámetros λ/p del AsLS Whittaker únicamente cuando esa línea base está activa."""
        is_asls = "AsLS" in self.combo_fit_baseline.currentText()
        self.lbl_fit_asls_lam.setVisible(is_asls)
        self.spin_fit_asls_lam.setVisible(is_asls)
        self.lbl_fit_asls_p.setVisible(is_asls)
        self.spin_fit_asls_p.setVisible(is_asls)

    def _on_toggle_right_panel(self, checked: Optional[bool] = None):
        """Alterna la visibilidad del panel derecho de opciones contextuales."""
        if not hasattr(self, "right_panel") or self.right_panel is None:
            return
        if checked is not None and isinstance(checked, bool):
            new_visible = checked
        else:
            new_visible = self.right_panel.isHidden()
        self.right_panel.setVisible(new_visible)
        if hasattr(self, "btn_toggle_right") and self.btn_toggle_right.isChecked() != new_visible:
            self.btn_toggle_right.setChecked(new_visible)
        if hasattr(self, "act_toggle_right") and self.act_toggle_right.isChecked() != new_visible:
            self.act_toggle_right.setChecked(new_visible)

    def _on_main_tab_changed(self, idx: int):
        if hasattr(self, 'stack_options'):
            self.stack_options.setCurrentIndex(min(idx, self.stack_options.count() - 1))
        # Fase 2: Lazy Rendering — sólo se renderiza bajo demanda el mapa 2D de la pestaña
        # recién activada si quedó marcada "sucia" por un _recalculate_all() previo mientras
        # el usuario miraba otra pestaña. El pipeline numérico ya está calculado de antemano.
        if idx in (0, 1, 2) and self._tab_2d_dirty.get(idx, False):
            self._render_tab_2d(idx)
            self._tab_2d_dirty[idx] = False

        # Fase 4: Pestaña 6 (Multi-Espectro) y 7 (Ficha Metrológica) se refrescan
        # sólo al ser visitadas (no en cada _recalculate_all, ya que iteran sobre
        # todo el lote de archivos marcados y no únicamente el espectro activo).
        if idx == 5:
            self._refresh_multi_spectrum_plot()
        elif idx == 6:
            self._refresh_metrology_ficha()

    def _schedule_recalculation(self):
        if hasattr(self, 'recalc_timer'):
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
        dark_mat_proc = None
        dark_1d = None
        if dark_mat is not None:
            despike_d = self.chk_dark_despike.isChecked()
            filt_d = self._map_filter_name(self.combo_dark_filter.currentText())
            p_d = self.spin_dark_param.value()
            dark_mat_proc = apply_spectral_filters_2d(
                matrix_2d=dark_mat,
                dark_matrix=None,
                sub_dark=False,
                ref_is_bg_subtracted=False,
                despike=despike_d,
                despike_sigma=4.0,
                noise_profile=self.current_noise_profile,
                wiener_adaptive=False,
                filter_type=filt_d,
                filter_params={'window_length': p_d, 'cutoff_ratio': 1.0 / p_d}
            )
            d_h = dark_mat_proc.shape[0] if dark_mat_proc.ndim == 2 else 1
            dark_1d = self._reduce_matrix(dark_mat_proc, 0, d_h, method="mean")
        self.current_dark_1d = dark_1d

        # 3. Reducción y filtrado de Referencia (Ventana 2) - Procesamiento integral 2D y 1D
        ref_mat_proc = None
        ref_1d = None
        ref_ymin = self.spin_ref_ymin.value()
        ref_ymax = self.spin_ref_ymax.value()
        ref_mode = "sum" if self.combo_ref_roimode.currentText() == "Suma" else "mean"
        ref_is_bg_sub = getattr(spec, 'ref_is_bg_corrected', False)
        if ref_inherited and self.master_spectrum is not None:
            ref_is_bg_sub = getattr(self.master_spectrum, 'ref_is_bg_corrected', False)

        if ref_mat is not None:
            filt_r = self._map_filter_name(self.combo_ref_filter.currentText())
            p_r = self.spin_ref_param.value()
            sub_dark_r = self.chk_ref_sub_dark.isChecked()
            despike_r = self.chk_ref_despike.isChecked()
            wiener_r = self.chk_ref_adaptive.isChecked() or (filt_r == "wiener")
            alpha_r = self.spin_ref_wiener_alpha.value()

            ref_mat_proc = apply_spectral_filters_2d(
                matrix_2d=ref_mat,
                dark_matrix=dark_mat_proc if dark_mat_proc is not None else dark_mat,
                sub_dark=sub_dark_r,
                ref_is_bg_subtracted=ref_is_bg_sub,
                despike=despike_r,
                despike_sigma=4.0,
                noise_profile=self.current_noise_profile,
                wiener_adaptive=wiener_r,
                wiener_alpha=alpha_r,
                filter_type=filt_r if filt_r != "wiener" else "none",
                filter_params={'window_length': p_r, 'cutoff_ratio': 1.0 / p_r}
            )
            ref_1d = self._reduce_matrix(ref_mat_proc, ref_ymin, ref_ymax, ref_mode)
        self.current_ref_1d = ref_1d

        # 4. Reducción y filtrado de Live / Señal (Ventana 3) - Procesamiento integral 2D y 1D
        live_mat_proc = None
        live_1d = None
        live_ymin = self.spin_live_ymin.value()
        live_ymax = self.spin_live_ymax.value()
        live_mode = "sum" if self.combo_live_roimode.currentText() == "Suma" else "mean"

        if live_mat is not None:
            filt_l = self._map_filter_name(self.combo_live_filter.currentText())
            p_l = self.spin_live_param.value()
            sub_dark_l = self.chk_live_sub_dark.isChecked()
            despike_l = self.chk_live_despike.isChecked()
            wiener_l = self.chk_live_adaptive.isChecked() or (filt_l == "wiener")
            alpha_l = self.spin_live_wiener_alpha.value()

            live_mat_proc = apply_spectral_filters_2d(
                matrix_2d=live_mat,
                dark_matrix=dark_mat_proc if dark_mat_proc is not None else dark_mat,
                sub_dark=sub_dark_l,
                ref_is_bg_subtracted=False,
                despike=despike_l,
                despike_sigma=4.0,
                noise_profile=self.current_noise_profile,
                wiener_adaptive=wiener_l,
                wiener_alpha=alpha_l,
                filter_type=filt_l if filt_l != "wiener" else "none",
                filter_params={'window_length': p_l, 'cutoff_ratio': 1.0 / p_l}
            )
            live_1d = self._reduce_matrix(live_mat_proc, live_ymin, live_ymax, live_mode)
        self.current_live_1d = live_1d

        # 5. Cálculo de Transmisión (Ventana 4) sobre Matrices y Señales Filtradas
        noise_gate = self.spin_trans_gate.value()
        t_route_a, t_route_b = None, None
        t_calc = None

        if live_mat_proc is not None and ref_mat_proc is not None:
            # Dado que live_mat_proc y ref_mat_proc ya han sido procesados, filtrados y
            # restados de fondo si correspondió, se pasan con dark=None y ref_is_bg_subtracted=True
            # para evitar cualquier doble resta destructiva.
            t_a, t_b, val_mask = compute_transmittance_dual_route(
                live=live_mat_proc,
                ref=ref_mat_proc,
                dark=None,
                roi_ymin=live_ymin,
                roi_ymax=live_ymax,
                noise_gate=noise_gate,
                in_percentage=True,
                ref_is_bg_subtracted=True
            )
            t_route_a = t_a
            t_route_b = t_b
            t_calc = t_route_a if self.radio_route_a.isChecked() else t_route_b
        elif trans_meas_mat is not None:
            t_meas_red = self._reduce_matrix(trans_meas_mat, live_ymin, live_ymax)
            t_calc = t_meas_red.copy()

        # Pipeline Cascada Multietapa de Filtrado sobre T_calc (Enfoque A)
        if t_calc is not None:
            fin_idx = np.isfinite(t_calc)
            if np.sum(fin_idx) > 8:
                t_calc_f = t_calc.copy()

                # Fase 1: Supresión de Rayos Cósmicos / Spikes en T(λ)
                if hasattr(self, 'chk_trans_despike') and self.chk_trans_despike.isChecked():
                    k_th = self.spin_trans_despike_k.value()
                    if self.current_noise_profile is not None:
                        t_calc_f[fin_idx] = filter_despike_adaptive(t_calc_f[fin_idx], self.current_noise_profile, threshold_k=k_th, kernel_size=5)
                    else:
                        t_calc_f[fin_idx] = filter_despike_median(t_calc_f[fin_idx], threshold_sigma=k_th, kernel_size=5)

                # Fase 2: Denoising Adaptativo de Wiener Físico (PSD Dark)
                chk_w = getattr(self, 'chk_trans_wiener', getattr(self, 'chk_trans_adaptive', None))
                if chk_w is not None and chk_w.isChecked() and self.current_noise_profile is not None:
                    alpha_t = self.spin_trans_wiener_alpha.value()
                    t_calc_f[fin_idx] = filter_wiener_adaptive(t_calc_f[fin_idx], self.current_noise_profile, alpha=alpha_t)

                # Fase 3: Suavizado Espectral Matemático con Parámetros Contextuales
                filt_post = self._map_filter_name(self.combo_trans_filter.currentText())
                if filt_post not in ("none", "wiener"):
                    filter_params = {}
                    if filt_post == "savgol":
                        w = self.spin_trans_param1.value()
                        if w % 2 == 0:
                            w += 1
                        p = min(self.spin_trans_param2.value(), max(1, w - 1))
                        filter_params = {'window_length': w, 'polyorder': p}
                    elif filt_post == "fourier":
                        fc = self.spin_trans_fc.value()
                        filter_params = {'cutoff_ratio': fc}
                    elif filt_post == "moving_average":
                        w = self.spin_trans_param1.value()
                        filter_params = {'window_size': w}

                    t_calc_f[fin_idx] = apply_spectral_filter(t_calc_f[fin_idx], filt_post, filter_params, despike_first=False)

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
                    ref_is_bg_subtracted=True
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

        # 6. Extinción (Ventana 5) - Realizada rigurosamente con los datos post-procesados de la Ventana 4
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

        # 7. Refrescar gráficos correspondientes con las matrices procesadas
        self._refresh_dark_plots(dark_mat_proc if dark_mat_proc is not None else dark_mat, dark_1d, dark_inherited)
        self._refresh_ref_plots(ref_mat_proc if ref_mat_proc is not None else ref_mat, ref_1d, ref_inherited)
        self._refresh_live_plots(live_mat_proc if live_mat_proc is not None else live_mat, live_1d, live_inherited)
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

    # ==========================================================================
    # FASE 2: LAZY RENDERING 2D, CONTRASTE ROBUSTO Y CROSSHAIR HUD
    # ==========================================================================
    def _maybe_render_2d_tab(self, tab_idx: int, render_func):
        """
        Renderiza el mapa de calor 2D de inmediato sólo si `tab_idx` es la pestaña central
        actualmente visible; en caso contrario la marca "sucia" (`_tab_2d_dirty`) para que
        `_on_main_tab_changed` la renderice bajo demanda quien recién se active.
        """
        if self.tabs_process.currentIndex() == tab_idx:
            render_func()
            self._tab_2d_dirty[tab_idx] = False
        else:
            self._tab_2d_dirty[tab_idx] = True

    def _render_tab_2d(self, idx: int):
        if idx == 0:
            self._render_dark_2d()
        elif idx == 1:
            self._render_ref_2d()
        elif idx == 2:
            self._render_live_2d()

    def _render_2d_pane(self, mat: Optional[np.ndarray], img_item: pg.ImageItem, plot_widget: pg.PlotWidget,
                         splitter: QSplitter, combo_contrast: QComboBox, cache_attr: str):
        """Ejecuta el renderizado costoso (setImage + niveles de contraste + rangos) de un mapa 2D."""
        if mat is None or self.active_index < 0 or self.active_index >= len(self.loaded_spectra):
            return
        spec = self.loaded_spectra[self.active_index]
        wl = spec.wavelengths

        d2 = mat[0] if mat.ndim == 3 else mat
        if d2.ndim == 1:
            d2 = d2.reshape(1, -1)
        h = d2.shape[0]
        d2_plot = np.tile(d2, (10, 1)) if h == 1 else d2
        h_plot = 10 if h == 1 else h
        setattr(self, cache_attr, d2_plot)

        img_item.setImage(d2_plot.T, autoLevels=False)
        self._apply_contrast_levels(img_item, d2_plot, combo_contrast)
        img_item.setRect(pg.QtCore.QRectF(wl[0], 0, wl[-1] - wl[0], h_plot))
        plot_widget.setXRange(wl[0], wl[-1], padding=0.02)
        plot_widget.setYRange(0, h_plot, padding=0.02)
        if len(splitter.sizes()) > 0 and splitter.sizes()[0] < 50:
            splitter.setSizes([260, 440])

    def _render_dark_2d(self):
        self._render_2d_pane(self._current_dark_2d_processed, self.img_dark_2d, self.plot_dark_2d,
                              self.splitter_dark, self.combo_dark_contrast, '_dark_2d_plot_cache')

    def _render_ref_2d(self):
        self._render_2d_pane(self._current_ref_2d_processed, self.img_ref_2d, self.plot_ref_2d,
                              self.splitter_ref, self.combo_ref_contrast, '_ref_2d_plot_cache')

    def _render_live_2d(self):
        self._render_2d_pane(self._current_live_2d_processed, self.img_live_2d, self.plot_live_2d,
                              self.splitter_live, self.combo_live_contrast, '_live_2d_plot_cache')

    def _apply_contrast_levels(self, img_item: pg.ImageItem, data_2d: np.ndarray, combo: QComboBox):
        """Recalcula únicamente los niveles [vmin, vmax] del ImageItem según el preset activo, sin tocar el pipeline numérico."""
        preset = combo.currentText()
        if preset == CONTRAST_MANUAL_LABEL:
            return
        p_low, p_high = CONTRAST_PRESETS.get(preset, (1.0, 99.0))
        vmin, vmax = compute_robust_contrast_levels(data_2d, p_low=p_low, p_high=p_high)
        img_item.setLevels([vmin, vmax])

    def _on_dark_contrast_changed(self):
        if self._dark_2d_plot_cache is not None:
            self._apply_contrast_levels(self.img_dark_2d, self._dark_2d_plot_cache, self.combo_dark_contrast)

    def _on_ref_contrast_changed(self):
        if self._ref_2d_plot_cache is not None:
            self._apply_contrast_levels(self.img_ref_2d, self._ref_2d_plot_cache, self.combo_ref_contrast)

    def _on_live_contrast_changed(self):
        if self._live_2d_plot_cache is not None:
            self._apply_contrast_levels(self.img_live_2d, self._live_2d_plot_cache, self.combo_live_contrast)

    def _on_dark_hist_toggled(self, checked: bool):
        self.hist_dark_2d.setVisible(checked)

    def _on_ref_hist_toggled(self, checked: bool):
        self.hist_ref_2d.setVisible(checked)

    def _on_live_hist_toggled(self, checked: bool):
        self.hist_live_2d.setVisible(checked)

    def _on_mouse_moved_2d_generic(self, pos, plot_widget: pg.PlotWidget, vline: pg.InfiniteLine,
                                    hline: pg.InfiniteLine, hud_label: QLabel, cache_attr: str):
        if not plot_widget.sceneBoundingRect().contains(pos):
            return
        mouse_point = plot_widget.plotItem.vb.mapSceneToView(pos)
        x_val = mouse_point.x()
        y_val = mouse_point.y()
        vline.setPos(x_val)
        hline.setPos(y_val)

        intensity_str = "--"
        mat = getattr(self, cache_attr)
        if mat is not None and 0 <= self.active_index < len(self.loaded_spectra):
            wl = self.loaded_spectra[self.active_index].wavelengths
            row = int(round(y_val))
            h = mat.shape[0]
            if 0 <= row < h and len(wl) > 0:
                col = int(np.clip(np.searchsorted(wl, x_val), 0, mat.shape[1] - 1))
                intensity_str = f"{mat[row, col]:.1f}"

        scale_um = self._current_scale_um()
        y_um = y_val * scale_um
        hud_label.setText(f"λ = {x_val:.2f} nm | Y = {y_val:.1f} px ({y_um:.2f} µm) | Intensidad = {intensity_str} cuentas")

    def _on_mouse_moved_dark_2d(self, pos):
        self._on_mouse_moved_2d_generic(pos, self.plot_dark_2d, self.vLine_dark2d, self.hLine_dark2d, self.lbl_dark_2d_hud, '_dark_2d_plot_cache')

    def _on_mouse_moved_ref_2d(self, pos):
        self._on_mouse_moved_2d_generic(pos, self.plot_ref_2d, self.vLine_ref2d, self.hLine_ref2d, self.lbl_ref_2d_hud, '_ref_2d_plot_cache')

    def _on_mouse_moved_live_2d(self, pos):
        self._on_mouse_moved_2d_generic(pos, self.plot_live_2d, self.vLine_live2d, self.hLine_live2d, self.lbl_live_2d_hud, '_live_2d_plot_cache')

    # --------------------------------------------------------------------------
    # REFRESH GRÁFICOS VENTANA 1: RUIDO
    # --------------------------------------------------------------------------
    def _refresh_dark_plots(self, dark_mat: Optional[np.ndarray], dark_1d: Optional[np.ndarray], inherited: bool):
        spec = self.loaded_spectra[self.active_index]
        wl = spec.wavelengths

        origin_str = f"Heredado de 👑 {self.master_spectrum.custom_name}" if (inherited and self.master_spectrum) else "Archivo Activo"
        self.lbl_dark_source.setText(f"Origen Ruido: {origin_str}")

        # Fase 2: cachear la matriz 2D procesada (barata) y diferir el renderizado costoso (setImage)
        self._current_dark_2d_processed = dark_mat
        self.widget_dark_2d.setVisible(dark_mat is not None)
        self._maybe_render_2d_tab(0, self._render_dark_2d)

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
            fin_d = np.isfinite(dark_1d)
            read_noise_rms = float(np.nanstd(np.diff(dark_1d[fin_d])) / np.sqrt(2.0)) if np.sum(fin_d) > 2 else 0.0
            n_hot = int(np.sum(dark_1d > (mean_c + 5.0 * std_c)))
            hot_str = f"Sí ({n_hot} px)" if n_hot > 0 else "No detectados"
            self.lbl_dark_metrics.setText(
                f"Métricas Ruido: Bias Medio: {mean_c:.2f} | Desvío σ_dark: {std_c:.2f} | Mín: {min_c:.1f} | Máx: {max_c:.1f} ({origin_str})<br>"
                f"Ruido de Lectura RMS: {read_noise_rms:.3f} cuentas | Píxeles Calientes (&gt;μ+5σ): {hot_str}"
            )
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

        # Fase 2: cachear la matriz 2D procesada (barata) y diferir el renderizado costoso (setImage)
        self._current_ref_2d_processed = ref_mat
        self.widget_ref_2d.setVisible(ref_mat is not None)
        self._maybe_render_2d_tab(1, self._render_ref_2d)

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
            dynamic_fill_pct = 100.0 * max_r / 65535.0

            lamp_maxima = []
            for s in self.loaded_spectra:
                if "reference" in s.channels:
                    r_1d_s = self._reduce_matrix(s.channels["reference"], self.spin_ref_ymin.value(), self.spin_ref_ymax.value())
                    if np.any(np.isfinite(r_1d_s)):
                        lamp_maxima.append(float(np.nanmax(r_1d_s)))
            if len(lamp_maxima) > 1:
                cv_pct = 100.0 * float(np.std(lamp_maxima)) / max(1e-9, float(np.mean(lamp_maxima)))
                stability_str = f"CV = {cv_pct:.2f}% (n={len(lamp_maxima)} archivos)"
            else:
                stability_str = "N/D (requiere ≥2 archivos con referencia propia)"

            self.lbl_ref_metrics.setText(
                f"Métricas Referencia: Cuentas Medias ROI: {mean_r:.1f} | Pico Lámpara: {max_r:.1f} (@ {peak_wl:.1f} nm) | Desvío: {std_r:.1f}<br>"
                f"Llenado Dinámico CCD (rango ADC 16-bit): {dynamic_fill_pct:.1f}% | Estabilidad Espectral: {stability_str}"
            )
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

        # Fase 2: cachear la matriz 2D procesada (barata) y diferir el renderizado costoso (setImage)
        self._current_live_2d_processed = live_mat
        self.widget_live_2d.setVisible(live_mat is not None)
        self._maybe_render_2d_tab(2, self._render_live_2d)

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
            dark_mean = float(np.nanmean(self.current_dark_1d)) if self.current_dark_1d is not None else 0.0
            dark_std = float(np.nanstd(self.current_dark_1d)) if self.current_dark_1d is not None else 1.0
            sbr = (mean_l / max(1.0, dark_mean)) if self.current_dark_1d is not None else 1.0
            net_max_l = max_l - dark_mean
            snr_peak = net_max_l / max(1e-9, dark_std)
            snr_integrated = float(np.nansum(live_1d - dark_mean)) / max(1e-9, np.sqrt(len(live_1d)) * dark_std)
            self.lbl_live_metrics.setText(
                f"Métricas Señal: Cuentas Medias ROI: {mean_l:.1f} | Pico Muestra: {max_l:.1f} (@ {peak_wl:.1f} nm) | SBR (Señal/Ruido): {sbr:.1f}x<br>"
                f"Señal Neta Máx: {net_max_l:.1f} | SNR Pico (H/σ_dark): {snr_peak:.1f} | SNR Integrado: {snr_integrated:.1f}"
            )
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
            u_t_mean = float(np.nanmean(sigma_t)) if sigma_t is not None and np.any(np.isfinite(sigma_t)) else 0.0
            self.lbl_trans_metrics.setText(
                f"Métricas Transmisión: T_media: {mean_t:.2f}% | Mín: {min_t:.1f}% | Máx: {max_t:.1f}% | RMS Residuo: {rms:.3f}% (ΔT medio: {mean_r:.3f}%)<br>"
                f"Contraste ΔT: {max_t - min_t:.2f}% | Incertidumbre Combinada Media ū_T: ±{u_t_mean:.3f}% | Discrepancia RMS (T_meas-T_calc): {rms:.3f}%"
            )
        elif t_calc is not None:
            fin_t = t_calc[np.isfinite(t_calc)]
            mean_t = float(np.mean(fin_t)) if len(fin_t) > 0 else 0.0
            min_t = float(np.min(fin_t)) if len(fin_t) > 0 else 0.0
            max_t = float(np.max(fin_t)) if len(fin_t) > 0 else 0.0
            u_t_mean = float(np.nanmean(sigma_t)) if sigma_t is not None and np.any(np.isfinite(sigma_t)) else 0.0
            self.lbl_trans_metrics.setText(
                f"Métricas Transmisión: T_media: {mean_t:.2f}% | Mín: {min_t:.1f}% | Máx: {max_t:.1f}%<br>"
                f"Contraste ΔT: {max_t - min_t:.2f}% | Incertidumbre Combinada Media ū_T: ±{u_t_mean:.3f}%"
            )

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
            self.plot_ext_main.plot(wl[fin], ext[fin], pen=pg.mkPen('#89dceb', width=2.0), name=f"Experimental ({formula_name})")

            # Si ya se realizó un ajuste, graficar el modelo global, la línea base y los componentes individuales
            if self.last_peak_fit_results is not None:
                res = self.last_peak_fit_results
                x_roi = res['roi_wavelengths']
                self.plot_ext_main.plot(x_roi, res['model_curve'], pen=pg.mkPen('#f38ba8', width=2.5), name=f"Ajuste Global ({res['n_peaks']} pico(s))")

                if res['baseline_mode'] != 'none':
                    self.plot_ext_main.plot(x_roi, res['baseline_curve'], pen=pg.mkPen('#6c7086', width=1.5, style=Qt.PenStyle.DashLine), name="Línea Base")

                for i, peak_curve in enumerate(res['individual_peaks']):
                    color = PEAK_COMPONENT_COLORS[i % len(PEAK_COMPONENT_COLORS)]
                    component_curve = res['baseline_curve'] + peak_curve
                    self.plot_ext_main.plot(x_roi, component_curve, pen=pg.mkPen(color, width=1.5, style=Qt.PenStyle.DotLine), name=f"Pico {i + 1}")

                self.plot_ext_residuals.clear()
                zero_l = pg.InfiniteLine(pos=0.0, angle=0, pen=pg.mkPen('#6c7086', style=Qt.PenStyle.DashLine))
                self.plot_ext_residuals.addItem(zero_l)
                self.plot_ext_residuals.plot(x_roi, res['residuals'], pen=pg.mkPen('#fab387', width=1.8), name="Residuo")

            if self.last_peak_fit_results is None:
                od_max = float(np.nanmax(ext[fin]))
                self.lbl_fit_results.setText(
                    f"<b>OD_max:</b> {od_max:.4f} | Seleccione el ROI espectral con las reglas arrastrables y presione '⚡ Ajustar Modelo en ROI'."
                )

        self._populate_fit_peaks_table()

    def _populate_fit_peaks_table(self):
        self.table_fit_peaks.setRowCount(0)
        res = self.last_peak_fit_results
        if res is None:
            return
        peaks = res.get('peaks_params', [])
        r2 = res.get('r_squared', 0.0)
        self.table_fit_peaks.setRowCount(len(peaks))
        for row, p in enumerate(peaks):
            extra_name = p.get('param_extra_name')
            extra_val = p.get('param_extra')
            extra_str = f"{extra_name} = {extra_val:.3f}" if extra_name and extra_val is not None else "--"
            values = [
                str(p['index']),
                f"{p['lambda_0']:.3f} ± {p['u_lambda_0']:.3f}",
                f"{p['fwhm']:.3f} ± {p['u_fwhm']:.3f}",
                f"{p['amplitude']:.4f}",
                f"{p['area']:.4f}",
                f"{p['ratio_h0']:.3f}",
                extra_str,
                f"{r2:.5f}"
            ]
            for col, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table_fit_peaks.setItem(row, col, item)
        self.table_fit_peaks.resizeColumnsToContents()

    def _on_run_peak_fit(self):
        if self.current_extinction is None:
            QMessageBox.warning(self, "Ajuste de Picos", "No hay curva de extinción calculada para ajustar.")
            return

        spec = self.loaded_spectra[self.active_index]
        wl = spec.wavelengths
        ext = self.current_extinction

        lmin = min(self.spin_fit_lmin.value(), self.spin_fit_lmax.value())
        lmax = max(self.spin_fit_lmin.value(), self.spin_fit_lmax.value())
        n_peaks = self.spin_fit_n_peaks.value()
        model_key = self._map_fit_model_name(self.combo_fit_model.currentText())
        baseline_key = self._map_baseline_name(self.combo_fit_baseline.currentText())
        slit_um = self.spin_fit_slit.value()

        try:
            results = fit_extinction_multi_peak(
                wavelengths=wl,
                signal_data=ext,
                roi_range=(lmin, lmax),
                n_peaks=n_peaks,
                model_type=model_key,
                baseline_mode=baseline_key,
                asls_lam=self.spin_fit_asls_lam.value(),
                asls_p=self.spin_fit_asls_p.value(),
                slit_width_um=slit_um,
                pixel_pitch_um=CCD_PIXEL_PITCH_UM
            )
            self.last_peak_fit_results = results

            model_disp = results['model'].replace('_', ' ').capitalize()
            r2 = results['r_squared']
            chi2r = results['chi2_reduced']
            peaks = results['peaks_params']
            od_max = float(np.nanmax(ext[np.isfinite(ext)])) if np.any(np.isfinite(ext)) else 0.0

            lines = [
                f"<b>OD_max:</b> {od_max:.4f} | "
                f"<b>Modelo:</b> {model_disp} ({results['n_peaks']} pico(s)) | "
                f"<b>Línea Base:</b> {results['baseline_mode']} | "
                f"<b>R²:</b> {r2:.5f} | <b>χ²_red:</b> {chi2r:.4g}"
            ]
            if peaks:
                principal = max(peaks, key=lambda p: p['amplitude'])
                q_factor = principal['lambda_0'] / max(1e-9, principal['fwhm'])
                lines.append(
                    f"<b>λ_res (principal):</b> {principal['lambda_0']:.3f} ± {principal['u_lambda_0']:.3f} nm | "
                    f"<b>FWHM:</b> {principal['fwhm']:.3f} ± {principal['u_fwhm']:.3f} nm | "
                    f"<b>Q = λ_res/FWHM:</b> {q_factor:.2f}"
                )
                if n_peaks >= 2 and peaks[0].get('ratio_h2_h1') is not None:
                    lines.append(f"<b>H₂/H₁:</b> {peaks[0]['ratio_h2_h1']:.3f}")

            self.lbl_fit_results.setText("<br>".join(lines))
            self._refresh_extinction_plots()
            self.statusBar().showMessage(f"Ajuste {model_disp} completado: {n_peaks} pico(s), R² = {r2:.4f}")

        except Exception as e:
            QMessageBox.critical(self, "Error en Ajuste", f"Ocurrió un error al ajustar el modelo:\n{str(e)}")

    def _on_clear_peak_fit(self):
        self.last_peak_fit_results = None
        self.table_fit_peaks.setRowCount(0)
        self.lbl_fit_results.setText(
            "Resultados del Ajuste: Seleccione el ROI espectral con las reglas arrastrables y presione '⚡ Ajustar Modelo en ROI'."
        )
        self._refresh_extinction_plots()
        self.statusBar().showMessage("Ajuste de picos descartado.", 2000)

    def _on_export_peak_fit(self):
        if self.last_peak_fit_results is None:
            QMessageBox.warning(self, "Exportar Ajuste", "Primero debe realizar un ajuste de pico(s) exitoso.")
            return

        res = self.last_peak_fit_results
        spec = self.loaded_spectra[self.active_index]
        default_fn = f"{spec.custom_name}_ajuste_{res['model']}_{res['n_peaks']}pico.txt"

        path, _ = QFileDialog.getSaveFileName(self, "Guardar resultados de ajuste", default_fn, "Texto (*.txt);;CSV (*.csv)")
        if not path:
            return

        cols = {
            "Experimental": res['roi_signal'],
            "Ajuste_Global": res['model_curve'],
            "Linea_Base": res['baseline_curve'],
            "Residuo": res['residuals']
        }
        for i, peak_curve in enumerate(res['individual_peaks']):
            cols[f"Pico_{i + 1}_Componente"] = peak_curve

        meta_hdr = {
            "Muestra": spec.metadata.filename,
            "Modelo": res['model'],
            "N_Picos": str(res['n_peaks']),
            "Linea_Base": res['baseline_mode'],
            "R_Squared": f"{res['r_squared']:.6f}",
            "Chi2_Reducido": f"{res['chi2_reduced']:.6g}",
        }
        for p in res['peaks_params']:
            idx = p['index']
            meta_hdr[f"Pico{idx}_lambda0_nm"] = f"{p['lambda_0']:.4f} +- {p['u_lambda_0']:.4f}"
            meta_hdr[f"Pico{idx}_FWHM_nm"] = f"{p['fwhm']:.4f} +- {p['u_fwhm']:.4f}"
            meta_hdr[f"Pico{idx}_Amplitud"] = f"{p['amplitude']:.6e}"
            meta_hdr[f"Pico{idx}_Area"] = f"{p['area']:.6e}"
            meta_hdr[f"Pico{idx}_Hi_H0"] = f"{p['ratio_h0']:.4f}"
            if p.get('param_extra') is not None:
                meta_hdr[f"Pico{idx}_{p['param_extra_name']}"] = f"{p['param_extra']:.4f}"

        delim = "," if path.lower().endswith(".csv") else "\t"
        try:
            export_spectrum_txt(path, res['roi_wavelengths'], cols, metadata_header=meta_hdr, delimiter=delim)
            QMessageBox.information(self, "Ajuste Exportado", f"Archivo de ajuste guardado exitosamente:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Error de Exportación", f"Error al guardar:\n{str(e)}")

    # ==========================================================================
    # VENTANA 6: MULTI-ESPECTRO & POLARIZACIÓN — LÓGICA
    # ==========================================================================
    def _get_checked_spectrum_indices(self) -> List[int]:
        """Retorna los índices de fila de la tabla de archivos cuya casilla 'Sel' está activa."""
        indices = []
        for row in range(self.table_files.rowCount()):
            cell_widget = self.table_files.cellWidget(row, 0)
            if cell_widget is not None:
                chk = cell_widget.findChild(QCheckBox)
                if chk is not None and chk.isChecked():
                    indices.append(row)
        return indices

    def _map_multi_curve_name(self, text: str) -> str:
        if "Extinción" in text or "Absorbancia" in text:
            return "extinction"
        if "Live" in text:
            return "live"
        if "T_meas" in text:
            return "t_meas"
        return "t_calc"

    def _compute_multi_curve_for_spectrum(self, spec: SifSpectrum, curve_key: str) -> Optional[np.ndarray]:
        """
        Calcula una curva 1D ligera (sin cascada de filtros) para el comparador multi-espectro y el
        análisis de polarización, reduciendo directamente los canales crudos/heredados del archivo con
        el ROI vertical compartido de la Pestaña 3 — el mismo criterio ya usado por
        `_refresh_ref_comparator` para comparaciones rápidas de todo el lote.
        """
        ymin = self.spin_live_ymin.value()
        ymax = self.spin_live_ymax.value()
        mode = "sum" if self.combo_live_roimode.currentText() == "Suma" else "mean"

        if curve_key == "live":
            live_mat, _ = self._get_effective_channel(spec, "live")
            if live_mat is None:
                return None
            return self._reduce_matrix(live_mat, ymin, ymax, mode)

        if curve_key == "t_meas":
            trans_mat, _ = self._get_effective_channel(spec, "transmittance")
            if trans_mat is None:
                return None
            return self._reduce_matrix(trans_mat, ymin, ymax, mode)

        live_mat, _ = self._get_effective_channel(spec, "live")
        ref_mat, _ = self._get_effective_channel(spec, "reference")
        dark_mat, _ = self._get_effective_channel(spec, "dark")
        if live_mat is None or ref_mat is None:
            return None
        live_1d = self._reduce_matrix(live_mat, ymin, ymax, mode)
        ref_1d = self._reduce_matrix(ref_mat, ymin, ymax, mode)
        dark_1d = self._reduce_matrix(dark_mat, ymin, ymax, mode) if dark_mat is not None else np.zeros_like(live_1d)
        ref_is_bg_sub = getattr(spec, 'ref_is_bg_corrected', False)

        t_calc, _, _ = compute_transmittance_with_errors(
            signal_spec=live_1d, ref_spec=ref_1d, bg_spec=dark_1d,
            noise_threshold=self.spin_trans_gate.value(), in_percentage=True,
            ref_is_bg_subtracted=ref_is_bg_sub
        )
        if curve_key == "t_calc":
            return t_calc

        if "log10" in self.combo_ext_formula.currentText():
            ext, _ = compute_extinction(t_calc)
        else:
            ext = 1.0 - (t_calc / 100.0)
        return ext

    def _refresh_multi_spectrum_plot(self):
        if not hasattr(self, 'plot_multi_curves'):
            return
        self.plot_multi_curves.clear()
        self.plot_multi_curves.addLegend(offset=(20, 20))
        indices = self._get_checked_spectrum_indices()
        if not indices:
            return

        is_waterfall = "Cascada" in self.combo_multi_mode.currentText()
        curve_key = self._map_multi_curve_name(self.combo_multi_curve.currentText())
        norm_mode = self.combo_multi_norm.currentText()
        dy = self.spin_multi_dy.value()
        dx = self.spin_multi_dx.value()

        for k, idx in enumerate(indices):
            if idx >= len(self.loaded_spectra):
                continue
            spec = self.loaded_spectra[idx]
            y = self._compute_multi_curve_for_spectrum(spec, curve_key)
            if y is None:
                continue
            x = spec.wavelengths
            fin = np.isfinite(y) & np.isfinite(x)
            if not np.any(fin):
                continue

            y_plot = np.asarray(y, dtype=np.float64).copy()
            if "Normalizar" in norm_mode:
                y_fin = y_plot[fin]
                rng = max(1e-9, float(np.max(y_fin) - np.min(y_fin)))
                y_plot = (y_plot - float(np.min(y_fin))) / rng
            elif "Máximo" in norm_mode:
                y_plot = y_plot / max(1e-9, float(np.max(np.abs(y_plot[fin]))))

            x_plot = np.asarray(x, dtype=np.float64).copy()
            if is_waterfall:
                y_plot = y_plot + k * dy
                x_plot = x_plot + k * dx

            color = PEAK_COMPONENT_COLORS[k % len(PEAK_COMPONENT_COLORS)]
            self.plot_multi_curves.plot(x_plot[fin], y_plot[fin], pen=pg.mkPen(color, width=1.6), name=spec.custom_name)

    def _on_run_malus_fit(self):
        lambda_res = self.spin_multi_pol_lambda.value()
        curve_key = self._map_multi_curve_name(self.combo_multi_curve.currentText())
        angles: List[float] = []
        intensities: List[float] = []

        for spec in self.loaded_spectra:
            theta = extract_polarization_angle_from_name(spec.metadata.filename or spec.custom_name)
            if theta is None:
                continue
            y = self._compute_multi_curve_for_spectrum(spec, curve_key)
            if y is None:
                continue
            wl = spec.wavelengths
            if not np.any(np.isfinite(y)):
                continue
            angles.append(theta)
            intensities.append(float(np.interp(lambda_res, wl, y)))

        if len(angles) < 3:
            QMessageBox.warning(
                self, "Ajuste de Ley de Malus",
                f"Se requieren al menos 3 archivos con ángulo de polarización reconocible en el nombre "
                f"(ej. '_45deg', 'pol90'); se encontraron {len(angles)}."
            )
            return

        try:
            res = fit_malus_law(np.array(angles), np.array(intensities))
            self.last_malus_fit_results = res
            self._refresh_polar_plot()
            self.statusBar().showMessage(
                f"Ajuste de Malus completado: θ₀ = {res['theta0_deg']:.1f}°, g = {res['g_factor']:.3f}, R² = {res['r_squared']:.4f}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Error en Ajuste de Malus", f"No se pudo ajustar la Ley de Malus:\n{str(e)}")

    def _refresh_polar_plot(self):
        if not hasattr(self, 'plot_multi_polar'):
            return
        self.plot_multi_polar.clear()
        self.plot_multi_polar.addLegend(offset=(20, 20))
        res = self.last_malus_fit_results
        if res is None:
            self.lbl_polar_metrics.setText(
                "Resultados de Polarización: cargue ≥3 archivos con ángulo detectable en el nombre y presione '⚡ Ajustar Ley de Malus'."
            )
            return

        # Grillas de referencia (círculos concéntricos a fracciones de I_max)
        theta_grid = np.linspace(0, 2 * np.pi, 200)
        for frac in (0.25, 0.5, 0.75, 1.0):
            r = frac * max(1e-9, res['i_max'])
            self.plot_multi_polar.plot(
                r * np.cos(theta_grid), r * np.sin(theta_grid),
                pen=pg.mkPen('#313244', width=1, style=Qt.PenStyle.DotLine)
            )

        theta_exp_rad = np.radians(res['angles_deg'])
        x_exp = res['intensities'] * np.cos(theta_exp_rad)
        y_exp = res['intensities'] * np.sin(theta_exp_rad)
        self.plot_multi_polar.plot(x_exp, y_exp, pen=None, symbol='o', symbolBrush='#89dceb', symbolSize=9, name="Experimental")

        theta_dense_rad = np.radians(res['theta_dense_deg'])
        x_fit = res['intensity_dense'] * np.cos(theta_dense_rad)
        y_fit = res['intensity_dense'] * np.sin(theta_dense_rad)
        self.plot_multi_polar.plot(x_fit, y_fit, pen=pg.mkPen('#f38ba8', width=2.2), name="Ajuste Ley de Malus")

        self.lbl_polar_metrics.setText(
            f"<b>I_max:</b> {res['i_max']:.4f} ± {res['u_i_max']:.4f} | "
            f"<b>I_min:</b> {res['i_min']:.4f} ± {res['u_i_min']:.4f} | "
            f"<b>θ₀:</b> {res['theta0_deg']:.2f}° ± {res['u_theta0_deg']:.2f}°<br>"
            f"<b>Factor de Anisotropía g:</b> {res['g_factor']:.4f} | "
            f"<b>Contraste C:</b> {res['contrast']:.4f} | <b>R²:</b> {res['r_squared']:.5f}"
        )

    # ==========================================================================
    # VENTANA 7: FICHA METROLÓGICA & FAIR — LÓGICA
    # ==========================================================================
    def _build_metrology_report_data(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        if not (0 <= self.active_index < len(self.loaded_spectra)):
            return data

        spec = self.loaded_spectra[self.active_index]
        meta = spec.metadata
        obj_name = self.combo_objective.currentText()
        obj_info = MICROSCOPE_OBJECTIVES.get(obj_name, list(MICROSCOPE_OBJECTIVES.values())[0])
        wl = spec.wavelengths
        dispersion = float(np.mean(np.abs(np.diff(wl)))) if len(wl) > 1 else 0.0

        data['filename'] = meta.filename or spec.custom_name
        data['detector'] = {
            'model': meta.detector_type, 'temp_c': meta.detector_temp_c, 'em_gain': meta.em_gain,
            'xbin': meta.xbin, 'ybin': meta.ybin, 'exposure_s': meta.exposure_time,
        }
        data['optics'] = {
            'objective': obj_name, 'na': obj_info.get('na'), 'scale_um_px': obj_info.get('pixel_scale_um'),
            'fov_y_um': (spec.height * obj_info.get('pixel_scale_um', 0.0)) if spec.is_2d else None,
        }
        data['spectrometer'] = {
            'slit_um': meta.slit_width_um,
            'calibration_origin': self.lbl_calib_status.text().replace('Origen: ', ''),
            'dispersion_nm_px': dispersion,
        }
        data['processing'] = {
            'dark_despike': self.chk_dark_despike.isChecked(),
            'dark_filter': self.combo_dark_filter.currentText(),
            'ref_despike': self.chk_ref_despike.isChecked(),
            'ref_wiener': self.chk_ref_adaptive.isChecked(),
            'live_despike': self.chk_live_despike.isChecked(),
            'live_wiener': self.chk_live_adaptive.isChecked(),
            'noise_gate_counts': self.spin_trans_gate.value(),
            'trans_despike': self.chk_trans_despike.isChecked(),
            'trans_wiener': self.chk_trans_wiener.isChecked(),
            'baseline_mode': self.combo_fit_baseline.currentText(),
            'fit_model': self.combo_fit_model.currentText(),
        }
        data['peaks_params'] = self.last_peak_fit_results.get('peaks_params') if self.last_peak_fit_results else None
        return data

    def _render_report_html(self, data: Dict[str, Any]) -> str:
        if not data:
            return "<p style='color:#6c7086;'>Cargue y active un espectro para generar la ficha metrológica.</p>"

        det, opt, spx, proc = data.get('detector', {}), data.get('optics', {}), data.get('spectrometer', {}), data.get('processing', {})
        peaks = data.get('peaks_params')

        html = [f"<h2 style='color:#cba6f7;'>📋 Ficha Metrológica — {data.get('filename', '--')}</h2>"]

        html.append("<h3 style='color:#89b4fa;'>🔧 Hardware: Detector Andor EMCCD</h3><ul>")
        html.append(f"<li>Modelo: {det.get('model', '--')}</li>")
        html.append(f"<li>Temperatura: {det.get('temp_c', 0.0):.1f} °C</li>")
        html.append(f"<li>Ganancia EM: {det.get('em_gain', 0.0):.1f}</li>")
        html.append(f"<li>Binning: X={det.get('xbin', '--')}, Y={det.get('ybin', '--')}</li>")
        html.append(f"<li>Exposición: {det.get('exposure_s', 0.0):.3f} s</li></ul>")

        html.append("<h3 style='color:#89b4fa;'>🔭 Óptica</h3><ul>")
        html.append(f"<li>Objetivo: {opt.get('objective', '--')}</li>")
        na = opt.get('na')
        html.append(f"<li>Apertura Numérica (NA): {na:.2f}</li>" if na is not None else "<li>Apertura Numérica (NA): --</li>")
        scale = opt.get('scale_um_px')
        html.append(f"<li>Escala Espacial: {scale:.4f} µm/px</li>" if scale is not None else "<li>Escala Espacial: --</li>")
        fov = opt.get('fov_y_um')
        if fov is not None:
            html.append(f"<li>Campo de Visión Vertical (FOV_Y): {fov:.2f} µm</li>")
        html.append("</ul>")

        html.append("<h3 style='color:#89b4fa;'>🌈 Calibración Espectral</h3><ul>")
        html.append(f"<li>Ranura (Slit): {spx.get('slit_um', 0.0):.0f} µm</li>")
        html.append(f"<li>Origen de Calibración: {spx.get('calibration_origin', '--')}</li>")
        html.append(f"<li>Dispersión Media: {spx.get('dispersion_nm_px', 0.0):.4f} nm/px</li></ul>")

        html.append("<h3 style='color:#89b4fa;'>⚙️ Protocolo de Procesamiento</h3><ul>")
        for k, v in proc.items():
            html.append(f"<li>{k}: {v}</li>")
        html.append("</ul>")

        if peaks:
            html.append("<h3 style='color:#89b4fa;'>🔬 Resultados del Ajuste Multi-Pico</h3>")
            html.append("<table border='1' cellpadding='4' style='border-collapse:collapse; color:#cdd6f4;'>")
            html.append("<tr><th>Pico</th><th>λ₀ ± u_c (nm)</th><th>FWHM ± u_c (nm)</th><th>Área</th><th>Hᵢ/H₀</th></tr>")
            for p in peaks:
                html.append(
                    f"<tr><td>{p['index']}</td><td>{p['lambda_0']:.3f} ± {p['u_lambda_0']:.3f}</td>"
                    f"<td>{p['fwhm']:.3f} ± {p['u_fwhm']:.3f}</td><td>{p['area']:.4f}</td><td>{p['ratio_h0']:.3f}</td></tr>"
                )
            html.append("</table>")
        else:
            html.append("<p style='color:#6c7086;'>Sin ajuste multi-pico realizado en la Pestaña 5.</p>")

        return "".join(html)

    def _render_report_markdown(self, data: Dict[str, Any]) -> str:
        if not data:
            return "# Ficha Metrológica\n\nCargue y active un espectro para generar la ficha.\n"

        det, opt, spx, proc = data.get('detector', {}), data.get('optics', {}), data.get('spectrometer', {}), data.get('processing', {})
        peaks = data.get('peaks_params')

        lines = [f"# Ficha Metrológica — {data.get('filename', '--')}", "", f"_Generado: {datetime.now().isoformat(timespec='seconds')}_", ""]

        lines += ["## Hardware: Detector Andor EMCCD", ""]
        lines.append(f"- Modelo: {det.get('model', '--')}")
        lines.append(f"- Temperatura: {det.get('temp_c', 0.0):.1f} °C")
        lines.append(f"- Ganancia EM: {det.get('em_gain', 0.0):.1f}")
        lines.append(f"- Binning: X={det.get('xbin', '--')}, Y={det.get('ybin', '--')}")
        lines.append(f"- Exposición: {det.get('exposure_s', 0.0):.3f} s")
        lines.append("")

        lines += ["## Óptica", ""]
        lines.append(f"- Objetivo: {opt.get('objective', '--')}")
        na = opt.get('na')
        lines.append(f"- NA: {na:.2f}" if na is not None else "- NA: --")
        scale = opt.get('scale_um_px')
        lines.append(f"- Escala: {scale:.4f} µm/px" if scale is not None else "- Escala: --")
        lines.append("")

        lines += ["## Calibración Espectral", ""]
        lines.append(f"- Ranura: {spx.get('slit_um', 0.0):.0f} µm")
        lines.append(f"- Origen: {spx.get('calibration_origin', '--')}")
        lines.append(f"- Dispersión: {spx.get('dispersion_nm_px', 0.0):.4f} nm/px")
        lines.append("")

        lines += ["## Protocolo de Procesamiento", ""]
        for k, v in proc.items():
            lines.append(f"- {k}: {v}")
        lines.append("")

        if peaks:
            lines += ["## Resultados del Ajuste Multi-Pico", "", "| Pico | λ₀ ± u_c (nm) | FWHM ± u_c (nm) | Área | Hᵢ/H₀ |", "|---|---|---|---|---|"]
            for p in peaks:
                lines.append(f"| {p['index']} | {p['lambda_0']:.3f} ± {p['u_lambda_0']:.3f} | {p['fwhm']:.3f} ± {p['u_fwhm']:.3f} | {p['area']:.4f} | {p['ratio_h0']:.3f} |")
        else:
            lines.append("_Sin ajuste multi-pico realizado._")

        return "\n".join(lines)

    def _refresh_metrology_ficha(self):
        if not hasattr(self, 'text_metrology_ficha'):
            return
        self.text_metrology_ficha.setHtml(self._render_report_html(self._build_metrology_report_data()))

    def _build_hdf5_session_data(self, spec: SifSpectrum) -> Dict[str, Any]:
        report_data = self._build_metrology_report_data()

        data_1d: Dict[str, np.ndarray] = {}
        if self.current_dark_1d is not None:
            data_1d['dark'] = self.current_dark_1d
        if self.current_ref_1d is not None:
            data_1d['reference'] = self.current_ref_1d
        if self.current_live_1d is not None:
            data_1d['live'] = self.current_live_1d
        if self.current_t_calc is not None:
            data_1d['transmittance_calc'] = self.current_t_calc
        if self.current_t_meas is not None:
            data_1d['transmittance_meas'] = self.current_t_meas
        if self.current_extinction is not None:
            data_1d['extinction'] = self.current_extinction

        data_2d: Dict[str, np.ndarray] = {}
        if spec.is_2d:
            dark_mat, _ = self._get_effective_channel(spec, "dark")
            ref_mat, _ = self._get_effective_channel(spec, "reference")
            live_mat, _ = self._get_effective_channel(spec, "live")
            if dark_mat is not None:
                data_2d['dark'] = dark_mat
            if ref_mat is not None:
                data_2d['reference'] = ref_mat
            if live_mat is not None:
                data_2d['live'] = live_mat

        return {
            'title': f"Sesion SIF -- {spec.custom_name}",
            'filename': spec.metadata.filename or spec.custom_name,
            'detector': report_data.get('detector', {}),
            'optics': report_data.get('optics', {}),
            'spectrometer': report_data.get('spectrometer', {}),
            'processing': report_data.get('processing', {}),
            'wavelengths_nm': spec.wavelengths,
            'data_1d': data_1d,
            'data_2d': data_2d,
            'peaks_params': report_data.get('peaks_params'),
        }

    def _on_export_session_hdf5(self):
        if not (0 <= self.active_index < len(self.loaded_spectra)):
            QMessageBox.warning(self, "Exportar Sesión", "No hay ningún espectro activo para exportar.")
            return

        spec = self.loaded_spectra[self.active_index]
        default_fn = f"{spec.custom_name}_sesion_FAIR.h5"
        path, _ = QFileDialog.getSaveFileName(self, "Exportar Sesión FAIR (HDF5 / NeXus)", default_fn, "HDF5 (*.h5)")
        if not path:
            return

        session_data = self._build_hdf5_session_data(spec)
        try:
            out_path = export_sif_session_to_hdf5(path, session_data)
            QMessageBox.information(self, "Sesión Exportada", f"Sesión FAIR (HDF5/NeXus) guardada en:\n{out_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error al Exportar Sesión", f"No se pudo generar el archivo HDF5:\n{str(e)}")

    def _on_copy_ficha_clipboard(self):
        data = self._build_metrology_report_data()
        if not data:
            QMessageBox.warning(self, "Copiar Ficha", "No hay ningún espectro activo.")
            return
        QApplication.clipboard().setText(self._render_report_markdown(data))
        self.statusBar().showMessage("Ficha metrológica copiada al portapapeles (Markdown).", 3000)

    def _on_export_ficha_markdown(self):
        data = self._build_metrology_report_data()
        if not data:
            QMessageBox.warning(self, "Exportar Ficha", "No hay ningún espectro activo.")
            return
        default_fn = f"{data.get('filename', 'ficha')}_metrologica.md"
        path, _ = QFileDialog.getSaveFileName(self, "Exportar Ficha Metrológica", default_fn, "Markdown (*.md);;Texto (*.txt)")
        if not path:
            return
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(self._render_report_markdown(data))
            QMessageBox.information(self, "Ficha Exportada", f"Ficha metrológica guardada en:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Error al Exportar Ficha", f"No se pudo guardar la ficha:\n{str(e)}")

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

    def _map_fit_model_name(self, name: str) -> str:
        if "Lorentz" in name:
            return "lorentzian"
        elif "Voigt" in name:
            return "pseudo_voigt"
        elif "Fano" in name:
            return "fano"
        return "gaussian"

    def _map_baseline_name(self, name: str) -> str:
        if "Constante" in name:
            return "constant"
        elif "Lineal" in name:
            return "linear"
        elif "AsLS" in name:
            return "asls"
        return "none"

    def _on_reset_dark_filters(self):
        """Restaura los filtros de ruido (Dark) al estado crudo sin procesar."""
        self.chk_dark_despike.setChecked(False)
        self.combo_dark_filter.setCurrentIndex(0)
        self._recalculate_all()
        self.statusBar().showMessage("Filtros de ruido reiniciados a crudo (Raw).", 2000)

    def _on_reset_ref_filters(self):
        """Restaura los filtros de referencia al estado crudo sin procesar."""
        self.chk_ref_sub_dark.setChecked(False)
        self.chk_ref_despike.setChecked(False)
        self.chk_ref_adaptive.setChecked(False)
        self.combo_ref_filter.setCurrentIndex(0)
        self._recalculate_all()
        self.statusBar().showMessage("Filtros de referencia reiniciados a crudo (Raw).", 2000)

    def _on_reset_live_filters(self):
        """Restaura los filtros de señal (Live) al estado crudo sin procesar."""
        self.chk_live_sub_dark.setChecked(False)
        self.chk_live_despike.setChecked(False)
        self.chk_live_adaptive.setChecked(False)
        self.combo_live_filter.setCurrentIndex(0)
        self._recalculate_all()
        self.statusBar().showMessage("Filtros de señal reiniciados a crudo (Raw).", 2000)

    def _on_sync_roi_to_live(self):
        """Copia y sincroniza los límites espaciales (ROI Y Min/Max) de Referencia hacia Live."""
        ymin = self.spin_ref_ymin.value()
        ymax = self.spin_ref_ymax.value()
        mode = self.combo_ref_roimode.currentIndex()
        self.spin_live_ymin.setValue(ymin)
        self.spin_live_ymax.setValue(ymax)
        self.combo_live_roimode.setCurrentIndex(mode)
        self.roi_live_region.setRegion([ymin, ymax])
        self._schedule_recalculation()
        self.statusBar().showMessage(f"ROI sincronizado con Referencia: [{ymin}, {ymax}] px", 2500)

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
        if 0 <= self.active_index < len(self.loaded_spectra):
            self._update_meta_badge(self.loaded_spectra[self.active_index])
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
