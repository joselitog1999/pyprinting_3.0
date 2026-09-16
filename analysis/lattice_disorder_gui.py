"""
analysis/lattice_disorder_gui.py
================================
Interfaz Gráfica Profesional en PyQt6 (Tema Catppuccin Mocha) para el
Análisis de Desorden Posicional y Parámetros de Red en PyPrinting 3.0.

Estructura en 4 Pestañas Secuenciales (Modelo SIF Analyzer):
- Pestaña 1: 📍 1. Espacio Real & SMLM (Carga, Localización Picasso/Trackpy, KDTree y g(r))
- Pestaña 2: 📊 2. Espacio Recíproco & Fourier (NUFFT 2D, Ajuste de Bragg 2D/1D, a_mean)
- Pestaña 3: 🔄 3. Monte Carlo & Debye-Waller (Simulación Asíncrona, Curvas, sigma_real)
- Pestaña 4: 📤 4. Ficha Metrológica & Exportación (Tablas, CSVs, Galería SVG/PNG 600 DPI)
"""

import os
import sys
from pathlib import Path

# ── Registrar directorio raíz y módulos para ejecución directa ───────────────
_curr = Path(__file__).resolve().parent
while _curr != _curr.parent:
    if (_curr / "config.py").exists():
        for _p in [str(_curr), str(_curr / "core"), str(_curr / "modules"), str(_curr / "analysis")]:
            if _p not in sys.path:
                sys.path.insert(0, _p)
        break
    _curr = _curr.parent

import time
import json
import numpy as np
import pandas as pd
from typing import Optional, Dict, Any, Tuple, Set, List

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QSplitter, QGroupBox, QLabel, QPushButton, QComboBox, QCheckBox,
    QSpinBox, QDoubleSpinBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QFileDialog, QMessageBox, QTabWidget, QScrollArea, QFrame,
    QProgressBar, QStackedWidget, QLineEdit, QButtonGroup, QMenu,
    QDialog, QDialogButtonBox, QSlider
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread
from PyQt6.QtGui import QColor, QFont

import pyqtgraph as pg

# Configuración global de PyQtGraph
pg.setConfigOption('background', '#181825')
pg.setConfigOption('foreground', '#cdd6f4')
pg.setConfigOption('antialias', True)

# Importar motor científico
from core.localization_pipeline import (
    load_image,
    load_coordinates,
    apply_richardson_lucy,
    localize_picasso,
    localize_trackpy,
    convert_pixels_to_nm
)
from core.lattice_disorder import (
    compute_structure_factor_2d,
    extract_1d_profiles,
    fit_bragg_peak_1d,
    fit_bragg_peak_double_gaussian,
    analyze_reciprocal_space_2d,
    analyze_real_space_kdtree,
    compute_radial_distribution_function,
    run_monte_carlo_calibration,
    fit_debye_waller_curve,
    interpolate_disorder,
    save_calibration_curve,
    load_calibration_curve,
    detect_clusters_and_chains,
    create_manual_cluster,
    resolve_clusters,
    resolve_clusters_dataframe,
    inspect_single_spot_photometry,
    resolve_single_spot_multi_gaussian,
    find_optimal_grid_bounding_box,
    compute_analytical_bragg_relations,
    calibrate_from_psf_image
)
from analysis.figure_export_studio import FigureExportStudioDialog


def get_pyqtgraph_colormap(name: str):
    """Obtiene un colormap de PyQtGraph o Matplotlib de forma segura."""
    try:
        return pg.colormap.get(name)
    except Exception:
        try:
            return pg.colormap.getFromMatplotlib(name)
        except Exception:
            return pg.colormap.get('viridis')


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
# CATÁLOGO DE PRESETS DE OPERACIÓN
# ==============================================================================
PRESETS_DICT: Dict[str, Dict[str, Any]] = {
    "✨ Confocal Estándar 30x30 (500 nm) [Calibrado 30x30_500]": {
        "motor": 0,  # Picasso
        "scale_nm": 50.0,
        "n_side": 30,
        "a_nominal": 500.0,
        "invert": False,
        "roi_enabled": True,
        "roi_xmin": 15.0,
        "roi_xmax": 315.0,
        "roi_ymin": 15.0,
        "roi_ymax": 318.0,
        # Picasso
        "picasso_grad": 300.0,
        "picasso_box": 7,
        "picasso_method": "gausslq",
        "picasso_box_offset": True,
        "picasso_autoscale": True,
        "picasso_baseline": 100,
        "picasso_gain": 1.0,
        "picasso_sensitivity": 1.0,
        # Trackpy
        "tp_diameter": 5,
        "tp_minmass": 0.05,
        "tp_separation": 7.0,
        "tp_percentile": 64,
        "tp_noise_size": 1.0,
        "tp_rl": False,
        "tp_rl_iter": 15,
        "tp_rl_sigma": 1.5,
    },
    "🔬 Confocal Alta Densidad (400-450 nm)": {
        "motor": 0,  # Picasso
        "scale_nm": 50.0,
        "n_side": 30,
        "a_nominal": 450.0,
        "invert": False,
        "roi_enabled": False,
        "roi_xmin": 0.0,
        "roi_xmax": 330.0,
        "roi_ymin": 0.0,
        "roi_ymax": 330.0,
        "picasso_grad": 200.0,
        "picasso_box": 5,
        "picasso_method": "gausslq",
        "picasso_box_offset": True,
        "picasso_autoscale": True,
        "picasso_baseline": 100,
        "picasso_gain": 1.0,
        "picasso_sensitivity": 1.0,
        "tp_diameter": 5,
        "tp_minmass": 0.02,
        "tp_separation": 5.0,
        "tp_percentile": 64,
        "tp_noise_size": 1.0,
        "tp_rl": False,
        "tp_rl_iter": 15,
        "tp_rl_sigma": 1.5,
    },
    "☀️ Fondo Claro / Transmisión (Invertida)": {
        "motor": 1,  # Trackpy
        "scale_nm": 50.0,
        "n_side": 30,
        "a_nominal": 500.0,
        "invert": True,
        "roi_enabled": False,
        "roi_xmin": 0.0,
        "roi_xmax": 330.0,
        "roi_ymin": 0.0,
        "roi_ymax": 330.0,
        "picasso_grad": 300.0,
        "picasso_box": 7,
        "picasso_method": "gausslq",
        "picasso_box_offset": True,
        "picasso_autoscale": True,
        "picasso_baseline": 100,
        "picasso_gain": 1.0,
        "picasso_sensitivity": 1.0,
        "tp_diameter": 7,
        "tp_minmass": 0.10,
        "tp_separation": 7.0,
        "tp_percentile": 64,
        "tp_noise_size": 1.0,
        "tp_rl": False,
        "tp_rl_iter": 15,
        "tp_rl_sigma": 1.5,
    },
    "📷 Fluorescencia Campo Amplio": {
        "motor": 0,  # Picasso
        "scale_nm": 100.0,
        "n_side": 20,
        "a_nominal": 600.0,
        "invert": False,
        "roi_enabled": False,
        "roi_xmin": 0.0,
        "roi_xmax": 512.0,
        "roi_ymin": 0.0,
        "roi_ymax": 512.0,
        "picasso_grad": 150.0,
        "picasso_box": 9,
        "picasso_method": "gaussmle",
        "picasso_box_offset": True,
        "picasso_autoscale": True,
        "picasso_baseline": 100,
        "picasso_gain": 1.0,
        "picasso_sensitivity": 1.0,
        "tp_diameter": 9,
        "tp_minmass": 0.10,
        "tp_separation": 9.0,
        "tp_percentile": 70,
        "tp_noise_size": 1.5,
        "tp_rl": False,
        "tp_rl_iter": 15,
        "tp_rl_sigma": 1.5,
    }
}


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
    padding: 6px 14px;
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
QPushButton#dangerBtn {
    background-color: #f38ba8;
    color: #11111b;
    font-weight: bold;
    border: none;
}
QPushButton#dangerBtn:hover {
    background-color: #eba0ac;
}
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {
    background-color: #181825;
    border: 1px solid #313244;
    border-radius: 5px;
    padding: 4px 8px;
    color: #cdd6f4;
}
QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus {
    border: 1px solid #89b4fa;
}
QTabWidget::pane {
    border: 1px solid #313244;
    background-color: #181825;
    border-radius: 8px;
}
QTabBar::tab {
    background-color: #181825;
    color: #a6adc8;
    padding: 9px 20px;
    font-weight: bold;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 4px;
    border: 1px solid #313244;
    border-bottom: none;
}
QTabBar::tab:selected {
    background-color: #1e1e2e;
    color: #89b4fa;
    border-top: 2px solid #89b4fa;
}
QTabBar::tab:hover:!selected {
    background-color: #313244;
    color: #cdd6f4;
}
QTableWidget {
    background-color: #181825;
    gridline-color: #313244;
    border: 1px solid #313244;
    border-radius: 6px;
    color: #cdd6f4;
}
QTableWidget QHeaderView::section {
    background-color: #11111b;
    color: #cba6f7;
    padding: 5px;
    font-weight: bold;
    border: 1px solid #313244;
}
QProgressBar {
    border: 1px solid #313244;
    border-radius: 6px;
    text-align: center;
    background-color: #181825;
    color: #cdd6f4;
    font-weight: bold;
}
QProgressBar::chunk {
    background-color: #89b4fa;
    border-radius: 5px;
}
QScrollBar:vertical {
    border: none;
    background: #181825;
    width: 8px;
    margin: 0px;
}
QScrollBar::handle:vertical {
    background: #45475a;
    min-height: 20px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover {
    background: #585b70;
}
"""


# ==============================================================================
# WORKER EN SEGUNDO PLANO PARA MONTE CARLO
# ==============================================================================

class MonteCarloWorker(QThread):
    progress_signal = pyqtSignal(int, int, float)
    finished_signal = pyqtSignal(dict)
    error_signal = pyqtSignal(str)

    def __init__(
        self,
        n_side: int,
        a: float,
        f_vac: float,
        sigma_min: float,
        sigma_max: float,
        n_sigma_steps: int,
        iterations_per_step: int,
        a_y: Optional[float] = None,
        n_bragg_pts: int = 81,
        band_width_nm: float = 0.0,
        n_transversal_pts: int = 5
    ):
        super().__init__()
        self.n_side = n_side
        self.a = a
        self.a_y = a_y
        self.f_vac = f_vac
        self.sigma_min = sigma_min
        self.sigma_max = sigma_max
        self.n_sigma_steps = n_sigma_steps
        self.iterations_per_step = iterations_per_step
        self.n_bragg_pts = n_bragg_pts
        self.band_width_nm = band_width_nm
        self.n_transversal_pts = n_transversal_pts
        self._is_cancelled = False

    def run(self):
        try:
            def callback(step, total, pct):
                if self._is_cancelled:
                    raise InterruptedError("Simulación cancelada por el usuario.")
                self.progress_signal.emit(step, total, pct)

            results = run_monte_carlo_calibration(
                n_side=self.n_side,
                a=self.a,
                a_y=self.a_y,
                f_vac=self.f_vac,
                sigma_min=self.sigma_min,
                sigma_max=self.sigma_max,
                n_sigma_steps=self.n_sigma_steps,
                iterations_per_step=self.iterations_per_step,
                progress_callback=callback,
                n_bragg_pts=self.n_bragg_pts,
                band_width_nm=self.band_width_nm,
                n_transversal_pts=self.n_transversal_pts
            )
            if not self._is_cancelled:
                self.finished_signal.emit(results)
        except InterruptedError:
            pass
        except Exception as e:
            self.error_signal.emit(str(e))

    def cancel(self):
        self._is_cancelled = True


# ==============================================================================
# VENTANA PRINCIPAL (4 PESTAÑAS)
# ==============================================================================

class LatticeDisorderWindow(QMainWindow):
    """
    Ventana principal para el análisis metrológico integral de redes periódicas 2D.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PyPrinting 3.0 — Analizador de Desorden y Estructura de Redes Cristalinas 2D")
        self.resize(1340, 880)
        self.setStyleSheet(DARK_THEME_QSS)

        # Estado interno de la aplicación
        self.current_image_path: Optional[str] = None
        self.raw_image_2d: Optional[np.ndarray] = None
        self.image_2d: Optional[np.ndarray] = None
        self.locs_df_raw: Optional[pd.DataFrame] = None
        self.locs_df: Optional[pd.DataFrame] = None
        self.reciprocal_results: Optional[Dict[str, Any]] = None
        self.kdtree_results: Optional[Dict[str, Any]] = None
        self.rdf_results: Optional[Dict[str, Any]] = None
        self.mc_results: Optional[Dict[str, Any]] = None

        # Control de sincronización interna de ROI
        self._updating_roi_internally: bool = False

        # Curación manual y control de aglomerados
        self.cluster_results: Optional[Dict[str, Any]] = None
        self.selected_particle_indices: Set[int] = set()
        self.selected_cluster_id: Optional[int] = None
        self.monomer_signature: Optional[Dict[str, Any]] = None
        self.selection_mode: str = 'nav'  # 'nav', 'click', 'box'
        self.curation_history: List[pd.DataFrame] = []
        self.raw_detected_df: Optional[pd.DataFrame] = None
        self.cluster_lines_items: List[pg.PlotDataItem] = []
        self.cluster_contour_items: List[pg.PlotDataItem] = []
        self.highlight_contour_item: Optional[pg.PlotDataItem] = None
        self.suspicious_contour_item: Optional[pg.PlotDataItem] = None
        self.current_inspected_spot_idx: Optional[int] = None
        self.current_spot_info: Optional[Dict[str, Any]] = None
        self.selection_box_roi: Optional[pg.RectROI] = None

        # Referencias a elementos gráficos de capas en Espacio Real
        self.img_item: Optional[pg.ImageItem] = None
        self.image_rl: Optional[np.ndarray] = None
        self.img_item_rl: Optional[pg.ImageItem] = None
        self.image_filtered: Optional[np.ndarray] = None
        self.img_item_filtered: Optional[pg.ImageItem] = None
        self.scatter_det: Optional[pg.ScatterPlotItem] = None
        self.scatter_clusters: Optional[pg.ScatterPlotItem] = None
        self.scatter_vac: Optional[pg.ScatterPlotItem] = None
        self.scatter_grid: Optional[pg.ScatterPlotItem] = None
        self.scatter_selected: Optional[pg.ScatterPlotItem] = None
        self.manual_visual_seeds_nm: List[Tuple[float, float]] = []
        self.scatter_visual_seeds: Optional[pg.ScatterPlotItem] = None
        self.text_visual_seeds_items: List[pg.TextItem] = []

        # Worker asíncrono
        self.mc_worker: Optional[MonteCarloWorker] = None

        # Reglas visuales e interactividad de g(r)
        self.line_rdf_rmin: Optional[pg.InfiniteLine] = None
        self.line_rdf_rmax: Optional[pg.InfiniteLine] = None
        self.line_rdf_bg: Optional[pg.InfiniteLine] = None
        self._updating_rdf_rules_internally: bool = False

        # Reglas visuales y ajuste de picos individuales en Espacio Recíproco
        self.peak_tuning_dict: Dict[str, Dict[str, Any]] = {}
        self.line_peak_fmin: Optional[pg.InfiniteLine] = None
        self.line_peak_fmax: Optional[pg.InfiniteLine] = None
        self.line_peak_bg: Optional[pg.InfiniteLine] = None
        self._current_tuned_plot: Optional[pg.PlotWidget] = None
        self._updating_peak_rules_internally: bool = False

        self._init_ui()

    def _init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(12, 10, 12, 10)
        main_layout.setSpacing(8)

        # Barra de navegación por pestañas (Workflow Wizard)
        self.tabs = QTabWidget()
        self.tab1 = QWidget()
        self.tab2 = QWidget()
        self.tab3 = QWidget()
        self.tab4 = QWidget()

        self.tabs.addTab(self.tab1, "📍 1. Espacio Real & SMLM")
        self.tabs.addTab(self.tab2, "📊 2. Espacio Recíproco & Fourier")
        self.tabs.addTab(self.tab3, "🔄 3. Monte Carlo & Debye-Waller")
        self.tabs.addTab(self.tab4, "📤 4. Ficha Metrológica & Exportación")

        main_layout.addWidget(self.tabs)

        # Construir cada pestaña
        self._build_tab1()
        self._build_tab2()
        self._build_tab3()
        self._build_tab4()

    # ==========================================================================
    # GESTIÓN Y EXPORTACIÓN UNIVERSAL DE GRÁFICOS (PNG 600 DPI / SVG)
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
            import pyqtgraph.exporters as pg_exp
            exporter = pg_exp.SVGExporter(plot_widget.plotItem)
            exporter.export(file_path)

    def _export_single_plot(self, plot_widget: pg.PlotWidget, default_name: str):
        """Exporta un gráfico individual en alta resolución PNG (2400 px, 600 DPI) o SVG vectorial."""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            f"Exportar Gráfico: {default_name}",
            f"{default_name}.png",
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
                import pyqtgraph.exporters as pg_exp
                exporter = pg_exp.ImageExporter(plot_widget.plotItem)
                exporter.parameters()['width'] = 2400  # 600 DPI equivalente
                exporter.export(file_path)
            QMessageBox.information(
                self, "Exportación Exitosa",
                f"Gráfico guardado exitosamente en:\n{file_path}"
            )
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
        """Habilita menú contextual de clic derecho para exportar y auto-rango en el gráfico."""
        plot_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        def _show_context_menu(pos):
            menu = QMenu(self)
            menu.setStyleSheet(
                "QMenu { background-color: #1e1e2e; color: #cdd6f4; border: 1px solid #45475a; font-size: 11px; } "
                "QMenu::item { padding: 5px 18px; } "
                "QMenu::item:selected { background-color: #313244; color: #89b4fa; }"
            )
            act_studio = menu.addAction("🎨 Abrir en Estudio de Exportación Científica (SVG / PNG / DAT)...")
            act_studio.triggered.connect(lambda: self._open_figure_export_studio(plot_widget, default_name, display_title))
            menu.addSeparator()
            act_exp = menu.addAction(f"💾 Exportar Rápido '{display_title}' (PNG 600 DPI / SVG)...")
            act_exp.triggered.connect(lambda: self._export_single_plot(plot_widget, default_name))
            act_reset = menu.addAction("🔍 Restablecer Vista (Auto-Rango)")
            act_reset.triggered.connect(plot_widget.enableAutoRange)
            menu.exec(plot_widget.mapToGlobal(pos))
        plot_widget.customContextMenuRequested.connect(_show_context_menu)

    def _on_export_active_cut(self):
        """Exporta el perfil 1D actualmente visible o seleccionado."""
        idx = self.combo_profile_view.currentIndex()
        if idx == 1:
            self._export_single_plot(self.plot_cut_x, "corte_espectral_fx")
        elif idx == 2:
            self._export_single_plot(self.plot_cut_y, "corte_espectral_fy")
        elif idx == 3:
            self._export_single_plot(self.plot_cut_diag, "corte_espectral_diagonal_45deg")
        else:
            folder = QFileDialog.getExistingDirectory(self, "Seleccionar Carpeta para Guardar los 3 Cortes 1D")
            if not folder:
                return
            try:
                import pyqtgraph.exporters as pg_exp
                for plot_w, fname in [
                    (self.plot_cut_x, "corte_espectral_fx.png"),
                    (self.plot_cut_y, "corte_espectral_fy.png"),
                    (self.plot_cut_diag, "corte_espectral_diagonal_45deg.png")
                ]:
                    exp = pg_exp.ImageExporter(plot_w.plotItem)
                    exp.parameters()['width'] = 1800
                    exp.export(os.path.join(folder, fname))
                QMessageBox.information(self, "Exportación Exitosa", f"Los 3 cortes 1D se guardaron en:\n{folder}")
            except Exception as e:
                QMessageBox.critical(self, "Error al Exportar Cortes", str(e))

    # ==========================================================================
    # PESTAÑA 1: ESPACIO REAL & SMLM
    # ==========================================================================
    def _build_tab1(self):
        layout = QHBoxLayout(self.tab1)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)

        # --- Panel Izquierdo con ScrollArea para máxima ergonomía ---
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(6, 6, 8, 6)
        left_layout.setSpacing(10)
        scroll_area.setWidget(left_widget)

        # Grupo 0: Presets de Operación (1-Clic)
        grp_preset = QGroupBox("0. Presets de Operación (1-Clic)")
        grp_preset.setToolTip(make_tooltip(
            "Catálogo de Presets de Operación",
            "Cargue o guarde configuraciones completas de parámetros validados con 1 solo clic.",
            "Serialización de hiperparámetros (escala, período, umbrales y dimensiones) optimizados y validados para cada muestra."
        ))
        lay_pre = QVBoxLayout(grp_preset)

        h_pre = QHBoxLayout()
        h_pre.addWidget(QLabel("Preset:"))
        self.combo_presets = QComboBox()
        self.combo_presets.setToolTip(make_tooltip(
            "Selector de Presets Validados",
            "Elija el tipo de muestra que está analizando para configurar automáticamente todos los controles de detección y red.",
            "Carga diccionarios predefinidos de adquisición y algoritmos validados en experimentos reales de nanofabricación."
        ))
        for p_name in PRESETS_DICT.keys():
            self.combo_presets.addItem(p_name)
        self.combo_presets.addItem("⚙️ Personalizado (Custom)")
        self.combo_presets.currentIndexChanged.connect(self._on_preset_changed)
        h_pre.addWidget(self.combo_presets)
        lay_pre.addLayout(h_pre)

        h_pre_btns = QHBoxLayout()
        self.btn_load_preset = QPushButton("📂 Cargar...")
        self.btn_load_preset.setToolTip(make_tooltip(
            "Cargar Preset Externo (.json)",
            "Importe un archivo JSON con una configuración previamente guardada.",
            "Restaura el estado completo de parámetros de calibración desde un archivo externo."
        ))
        self.btn_load_preset.clicked.connect(self._on_load_custom_preset_json)
        h_pre_btns.addWidget(self.btn_load_preset)

        self.btn_save_preset = QPushButton("💾 Guardar...")
        self.btn_save_preset.setToolTip(make_tooltip(
            "Guardar Preset Actual (.json)",
            "Guarde los parámetros configurados actualmente en un archivo JSON para reutilizarlos en futuras sesiones.",
            "Serializa los campos activos de escala, período, cajas de ajuste y márgenes en formato JSON estructurado."
        ))
        self.btn_save_preset.clicked.connect(self._on_save_custom_preset_json)
        h_pre_btns.addWidget(self.btn_save_preset)
        lay_pre.addLayout(h_pre_btns)

        self.btn_load_psf = QPushButton("🔬 Calibrar con PSF Confocal (psf.tiff)...")
        self.btn_load_psf.setStyleSheet("color: #89dceb; font-weight: bold;")
        self.btn_load_psf.setToolTip(make_tooltip(
            "Calibración Óptica con PSF Confocal Única",
            "Cargue una micrografía confocal de nanopartícula única (ej. 100 nm Au NP) para calibrar las condiciones iniciales de Picasso, Trackpy y RL.",
            "Ajusta una Gaussiana 2D para estimar sigma_psf, FWHM, fotones integrados V₀ y gradiente de Sobel, auto-llenando los parámetros editables."
        ))
        self.btn_load_psf.clicked.connect(self._on_calibrate_psf)
        lay_pre.addWidget(self.btn_load_psf)

        self.lbl_psf_calib_info = QLabel("PSF Confocal: No calibrada")
        self.lbl_psf_calib_info.setStyleSheet("color: #a6adc8; font-size: 10px; font-family: monospace;")
        self.lbl_psf_calib_info.setWordWrap(True)
        lay_pre.addWidget(self.lbl_psf_calib_info)

        left_layout.addWidget(grp_preset)

        # Grupo 1: Carga de Datos y Preprocesamiento
        grp_load = QGroupBox("1. Datos de Entrada")
        grp_load.setToolTip(make_tooltip(
            "Carga de Datos Experimentales",
            "Importe la micrografía confocal (TIFF/PNG/H5) o una tabla previa de coordenadas (CSV/TXT).",
            "Ingesta de imágenes 2D de fluorescencia/confocal o matrices de centroides ya localizados."
        ))
        lay_load = QVBoxLayout(grp_load)

        btn_load_img = QPushButton("📂 Cargar Imagen Confocal (.tiff, .png, .h5)")
        btn_load_img.setObjectName("primaryBtn")
        btn_load_img.setToolTip(make_tooltip(
            "Cargar Imagen Confocal / Fluorescencia",
            "Abre un archivo de imagen científica para detectar automáticamente las nanopartículas.",
            "Carga matrices bidimensionales I(x, y) de 8, 16 o 32 bits, preservando rango dinámico y calibración óptica."
        ))
        btn_load_img.clicked.connect(self._on_load_image)
        lay_load.addWidget(btn_load_img)

        btn_load_coords = QPushButton("📄 Cargar Coordenadas Directas (.csv, .txt)")
        btn_load_coords.setToolTip(make_tooltip(
            "Cargar Coordenadas Directas",
            "Si ya dispone de los centroides localizados por otro software, cárguelos aquí en CSV o TXT.",
            "Ingesta de DataFrames con columnas obligatorias 'x' e 'y' (en píxeles o nanómetros), omitiendo la fase de ajuste de PSF."
        ))
        btn_load_coords.clicked.connect(self._on_load_coordinates)
        lay_load.addWidget(btn_load_coords)

        self.chk_invert_img = QCheckBox("☀️ Invertir Imagen (Negativo / Fondo Claro)")
        self.chk_invert_img.setChecked(False)
        self.chk_invert_img.setToolTip(make_tooltip(
            "Invertir Contraste de Imagen",
            "Márquelo si sus partículas se observan oscuras sobre un fondo claro (microscopía de transmisión o campo claro).",
            "Aplica la transformación I'(x, y) = max(I) - I(x, y) para que los algoritmos de detección localicen máximos de intensidad."
        ))
        self.chk_invert_img.toggled.connect(self._on_invert_toggled)
        lay_load.addWidget(self.chk_invert_img)

        self.lbl_file_info = QLabel("Ningún archivo cargado.")
        self.lbl_file_info.setStyleSheet("color: #a6adc8; font-size: 11px;")
        self.lbl_file_info.setWordWrap(True)
        lay_load.addWidget(self.lbl_file_info)

        left_layout.addWidget(grp_load)

        # Grupo 2: Selector de ROI & Recorte (4 Reglas Móviles)
        grp_roi = QGroupBox("2. Selector de ROI & Recorte (4 Reglas)")
        grp_roi.setToolTip(make_tooltip(
            "Región de Interés (ROI) y Recorte de Bordes",
            "Delimite el área útil de la muestra para excluir bordes defectuosos o partículas fuera de la red.",
            "Define una máscara rectangular acotada [xmin, xmax] x [ymin, ymax] en píxeles para aislar la red nominal."
        ))
        lay_roi = QVBoxLayout(grp_roi)

        self.chk_roi_enable = QCheckBox("✂️ Habilitar Reglas de ROI en Gráfico")
        self.chk_roi_enable.setChecked(True)
        self.chk_roi_enable.setToolTip(make_tooltip(
            "Habilitar Líneas Guía de Recorte",
            "Muestra u oculta las 4 líneas discontinuas en el visor que delimitan la zona de análisis.",
            "Superpone en el grafo de escena cuatro objetos InfiniteLine interactivos arrastrables con el ratón."
        ))
        self.chk_roi_enable.toggled.connect(self._on_roi_enable_toggled)
        lay_roi.addWidget(self.chk_roi_enable)

        grid_roi = QGridLayout()
        grid_roi.addWidget(QLabel("X min (px):"), 0, 0)
        self.spin_roi_xmin = QDoubleSpinBox()
        self.spin_roi_xmin.setRange(0.0, 10000.0)
        self.spin_roi_xmin.setValue(15.0)
        self.spin_roi_xmin.setToolTip(make_tooltip(
            "Límite Izquierdo de Recorte X min (px)",
            "Posición horizontal en píxeles donde comienza el área de análisis.",
            "Cota inferior x >= x_min para el filtrado espacial de centroides en el plano focal."
        ))
        self.spin_roi_xmin.valueChanged.connect(self._on_roi_spin_changed)
        grid_roi.addWidget(self.spin_roi_xmin, 0, 1)

        grid_roi.addWidget(QLabel("X max (px):"), 0, 2)
        self.spin_roi_xmax = QDoubleSpinBox()
        self.spin_roi_xmax.setRange(0.0, 10000.0)
        self.spin_roi_xmax.setValue(315.0)
        self.spin_roi_xmax.setToolTip(make_tooltip(
            "Límite Derecho de Recorte X max (px)",
            "Posición horizontal en píxeles donde termina el área de análisis.",
            "Cota superior x <= x_max para el filtrado espacial de centroides."
        ))
        self.spin_roi_xmax.valueChanged.connect(self._on_roi_spin_changed)
        grid_roi.addWidget(self.spin_roi_xmax, 0, 3)

        grid_roi.addWidget(QLabel("Y min (px):"), 1, 0)
        self.spin_roi_ymin = QDoubleSpinBox()
        self.spin_roi_ymin.setRange(0.0, 10000.0)
        self.spin_roi_ymin.setValue(15.0)
        self.spin_roi_ymin.setToolTip(make_tooltip(
            "Límite Inferior de Recorte Y min (px)",
            "Posición vertical en píxeles donde comienza el área de análisis.",
            "Cota inferior y >= y_min para el filtrado espacial de centroides."
        ))
        self.spin_roi_ymin.valueChanged.connect(self._on_roi_spin_changed)
        grid_roi.addWidget(self.spin_roi_ymin, 1, 1)

        grid_roi.addWidget(QLabel("Y max (px):"), 1, 2)
        self.spin_roi_ymax = QDoubleSpinBox()
        self.spin_roi_ymax.setRange(0.0, 10000.0)
        self.spin_roi_ymax.setValue(318.0)
        self.spin_roi_ymax.setToolTip(make_tooltip(
            "Límite Superior de Recorte Y max (px)",
            "Posición vertical en píxeles donde termina el área de análisis.",
            "Cota superior y <= y_max para el filtrado espacial de centroides."
        ))
        self.spin_roi_ymax.valueChanged.connect(self._on_roi_spin_changed)
        grid_roi.addWidget(self.spin_roi_ymax, 1, 3)
        lay_roi.addLayout(grid_roi)

        h_roi_btns = QHBoxLayout()
        btn_reset_roi = QPushButton("↺ Toda la Imagen")
        btn_reset_roi.setToolTip(make_tooltip(
            "Restablecer Recorte a Toda la Imagen",
            "Expande los límites de corte para incluir la micrografía completa de punta a punta.",
            "Fija xmin=0, xmax=ancho, ymin=0, ymax=alto basándose en el tamaño de la matriz cargada."
        ))
        btn_reset_roi.clicked.connect(self._on_reset_roi_to_image)
        h_roi_btns.addWidget(btn_reset_roi)

        btn_apply_roi = QPushButton("✂️ Aplicar Recorte")
        btn_apply_roi.setObjectName("accentBtn")
        btn_apply_roi.setToolTip(make_tooltip(
            "Aplicar Filtro de Recorte",
            "Descarta de inmediato todas las partículas que queden fuera del rectángulo seleccionado.",
            "Ejecuta el filtrado booleano sobre locs_df y actualiza los cálculos de espacio real y recíproco."
        ))
        btn_apply_roi.clicked.connect(self._apply_roi_filter)
        h_roi_btns.addWidget(btn_apply_roi)
        lay_roi.addLayout(h_roi_btns)

        left_layout.addWidget(grp_roi)

        # Grupo 3: Parámetros Espaciales de Red
        grp_grid = QGroupBox("3. Parámetros Espaciales de Red")
        grp_grid.setToolTip(make_tooltip(
            "Parámetros Espaciales de Red",
            "Configura la escala de aumento del microscopio, el período de separación y el tamaño de la red.",
            "Parámetros fundamentales de diseño físico requeridos para la metrología dimensional en nanómetros."
        ))
        lay_grid = QVBoxLayout(grp_grid)

        h1 = QHBoxLayout()
        h1.addWidget(QLabel("Escala Espacial (nm/px):"))
        self.spin_scale = QDoubleSpinBox()
        self.spin_scale.setRange(1.0, 1000.0)
        self.spin_scale.setValue(50.0)
        self.spin_scale.setSingleStep(1.0)
        self.spin_scale.setToolTip(make_tooltip(
            "Escala Espacial (nm / px)",
            "Calibración del microscopio: indica cuántos nanómetros reales mide el ancho de un píxel de la cámara.",
            "Factor de conversión dimensional s [nm/px] tal que r_nm = s * r_px. Su incertidumbre propaga linealmente a todas las métricas de red."
        ))
        self.spin_scale.valueChanged.connect(self._on_scale_changed)
        h1.addWidget(self.spin_scale)
        lay_grid.addLayout(h1)

        h2 = QHBoxLayout()
        h2.addWidget(QLabel("Dimensiones Nominales (N x N):"))
        self.spin_n_side = QSpinBox()
        self.spin_n_side.setRange(2, 200)
        self.spin_n_side.setValue(30)
        self.spin_n_side.setToolTip(make_tooltip(
            "Dimensiones Nominales de Red (N x N)",
            "Cantidad de nanopartículas que componen la red por fila y por columna (ej. 30 para 30x30 = 900 partículas).",
            "Dimensión cristalográfica entera N del cristal 2D. Define el total de sitios teóricos N^2 para la tasa de vacancias."
        ))
        h2.addWidget(self.spin_n_side)
        lay_grid.addLayout(h2)

        h3 = QHBoxLayout()
        h3.addWidget(QLabel("Período Nominal a (nm):"))
        self.spin_a_nominal = QDoubleSpinBox()
        self.spin_a_nominal.setRange(50.0, 5000.0)
        self.spin_a_nominal.setValue(500.0)
        self.spin_a_nominal.setSingleStep(5.0)
        self.spin_a_nominal.setToolTip(make_tooltip(
            "Período Nominal de Red a (nm)",
            "Distancia teórica o programada entre los centros de dos nanopartículas vecinas en nanómetros.",
            "Parámetro de red de referencia a [nm]. Fija el vector recíproco de Bragg |G1| = 2pi/a y la frecuencia espacial f0 = 1/a."
        ))
        h3.addWidget(self.spin_a_nominal)
        lay_grid.addLayout(h3)

        # Sub-panel de Parámetros Especiales de Red (Ajuste Óptico)
        grp_special = QGroupBox("⚙️ Parámetros Especiales de Red (Ajuste Óptico)")
        grp_special.setStyleSheet(
            "QGroupBox { font-size: 11px; font-weight: bold; color: #a6e3a1; "
            "border: 1px solid #45475a; border-radius: 5px; margin-top: 6px; padding: 6px; }"
        )
        lay_spec = QVBoxLayout(grp_special)
        lay_spec.setSpacing(6)

        self.chk_use_contour_mask_fit = QCheckBox("Ajuste multi-gauss acotado a máscara de contorno")
        self.chk_use_contour_mask_fit.setChecked(True)
        self.chk_use_contour_mask_fit.setStyleSheet("color: #a6e3a1; font-weight: bold;")
        self.chk_use_contour_mask_fit.setToolTip(make_tooltip(
            "Ajuste Acotado a Máscara de Contorno",
            "Limita el ajuste de Gaussianas exclusivamente a los píxeles dentro del contorno gráfico marcado, enviando el resto a 0.",
            "Elimina la influencia de colas difraccionales de partículas vecinas anulando los residuos fuera de la máscara."
        ))
        lay_spec.addWidget(self.chk_use_contour_mask_fit)

        self.chk_constrain_centers_to_mask = QCheckBox("Restringir centros (x_k, y_k) al interior del contorno")
        self.chk_constrain_centers_to_mask.setChecked(True)
        self.chk_constrain_centers_to_mask.setStyleSheet("color: #89b4fa;")
        self.chk_constrain_centers_to_mask.setToolTip(make_tooltip(
            "Restricción Geométrica de Centros",
            "Fuerza que las posiciones (x, y) de los emisores desacoplados permanezcan dentro de la envolvente de la zona marcada.",
            "Cota rígida lb y ub sobre las coordenadas espaciales en la optimización por Levenberg-Marquardt."
        ))
        lay_spec.addWidget(self.chk_constrain_centers_to_mask)

        # Filtro de fondo interactivo con CheckBox, SpinBox y Deslizador
        h_bg_filt = QHBoxLayout()
        self.chk_filter_preview = QCheckBox("Superponer Filtrado")
        self.chk_filter_preview.setChecked(False)
        self.chk_filter_preview.setStyleSheet("color: #f9e2af; font-weight: bold;")
        self.chk_filter_preview.setToolTip(make_tooltip(
            "Superponer Imagen Filtrada por Fondo",
            "Muestra sobre el TIFF la imagen con el fondo sustraído según el porcentaje fijado en el deslizador.",
            "Capa intermedia z=1 superpuesta entre la imagen original y la deconvolución RL."
        ))
        self.chk_filter_preview.toggled.connect(self._on_bg_filter_preview_toggled)
        h_bg_filt.addWidget(self.chk_filter_preview)

        self.spin_bg_filter_pct = QDoubleSpinBox()
        self.spin_bg_filter_pct.setRange(1.0, 50.0)
        self.spin_bg_filter_pct.setValue(20.0)
        self.spin_bg_filter_pct.setSingleStep(1.0)
        self.spin_bg_filter_pct.setSuffix("%")
        self.spin_bg_filter_pct.setToolTip(make_tooltip(
            "Filtro de Fondo (% del Máximo)",
            "Nivel de corte de fondo relativo respecto al brillo pico local para filtrar ruido.",
            "Umbral de corte sustractivo: I_cut = (pct/100) * I_max."
        ))
        self.spin_bg_filter_pct.valueChanged.connect(self._on_bg_filter_spin_changed)
        h_bg_filt.addWidget(self.spin_bg_filter_pct)
        lay_spec.addLayout(h_bg_filt)

        self.slider_bg_filter = QSlider(Qt.Orientation.Horizontal)
        self.slider_bg_filter.setRange(1, 50)
        self.slider_bg_filter.setValue(20)
        self.slider_bg_filter.setToolTip(make_tooltip(
            "Deslizador de Filtro de Fondo",
            "Deslice para ajustar en tiempo real el corte de fondo y ver la imagen filtrada superponerse al instante.",
            "Actualización en vivo de la capa de fondo filtrado (z=1)."
        ))
        self.slider_bg_filter.valueChanged.connect(self._on_bg_filter_slider_changed)
        lay_spec.addWidget(self.slider_bg_filter)

        lay_grid.addWidget(grp_special)

        left_layout.addWidget(grp_grid)

        # Grupo 4: Fase 1: Detección Inicial de Partículas
        grp_loc = QGroupBox("4. Fase 1: Detección Inicial de Partículas")
        grp_loc.setToolTip(make_tooltip(
            "Fase 1: Detección y Localización de Partículas",
            "Algoritmos para encontrar con precisión nanométrica el centro de cada nanopartícula en la imagen.",
            "Pipeline de súper-resolución óptica (SMLM) para el ajuste sub-píxel de emisores fluorescentes o dispersores plasmónicos."
        ))
        lay_loc = QVBoxLayout(grp_loc)

        h4 = QHBoxLayout()
        h4.addWidget(QLabel("Motor:"))
        self.combo_motor = QComboBox()
        self.combo_motor.addItems(["Picasso (GaussLQ / MLE)", "Trackpy (Crocker-Grier)"])
        self.combo_motor.setToolTip(make_tooltip(
            "Motor de Localización Sub-Píxel",
            "Picasso: Ajuste gaussiano de alta precisión (súper-resolución SMLM). Trackpy: Detección rápida de centroides por pasa-bandas.",
            "Picasso ajusta la PSF con modelos analíticos continuos mediante Levenberg-Marquardt o MLE. Trackpy aplica convolución pasa-bandas de Crocker-Grier."
        ))
        self.combo_motor.currentIndexChanged.connect(self._on_motor_changed)
        h4.addWidget(self.combo_motor)
        lay_loc.addLayout(h4)

        # Controles dinámicos según motor
        self.stack_motor = QStackedWidget()

        # Página Picasso
        page_picasso = QWidget()
        lay_pic = QVBoxLayout(page_picasso)
        lay_pic.setContentsMargins(0, 5, 0, 5)

        hp1 = QHBoxLayout()
        hp1.addWidget(QLabel("Min. Net Gradient:"))
        self.spin_net_grad = QDoubleSpinBox()
        self.spin_net_grad.setRange(0.1, 50000.0)
        self.spin_net_grad.setValue(300.0)
        self.spin_net_grad.setSingleStep(50.0)
        self.spin_net_grad.setToolTip(make_tooltip(
            "Gradiente Neto Mínimo (Picasso)",
            "Sensibilidad del detector: valores bajos detectan partículas tenues; valores altos ignoran ruido de fondo.",
            "Umbral de corte sobre el operador gradiente de Sobel para identificar candidatos a centros de dispersión."
        ))
        hp1.addWidget(self.spin_net_grad)
        lay_pic.addLayout(hp1)

        hp2 = QHBoxLayout()
        hp2.addWidget(QLabel("Box Size (px impar):"))
        self.spin_box_size = QSpinBox()
        self.spin_box_size.setRange(3, 31)
        self.spin_box_size.setSingleStep(2)
        self.spin_box_size.setValue(7)
        self.spin_box_size.setToolTip(make_tooltip(
            "Tamaño de Caja de Ajuste (px impar)",
            "Ancho del recuadro en píxeles alrededor de cada mancha para ajustar su forma gaussiana (ej. 7x7 px).",
            "Dimensión de la ventana local de corte (2k+1) x (2k+1) píxeles donde se optimizan los parámetros de la PSF."
        ))
        hp2.addWidget(self.spin_box_size)
        lay_pic.addLayout(hp2)

        hp3 = QHBoxLayout()
        hp3.addWidget(QLabel("Método Ajuste:"))
        self.combo_picasso_method = QComboBox()
        self.combo_picasso_method.addItems(["GaussLQ (Mínimos Cuadrados)", "GaussMLE (Máxima Verosimilitud)"])
        self.combo_picasso_method.setToolTip(make_tooltip(
            "Método de Ajuste Gaussiano (Picasso)",
            "GaussLQ: Mínimos cuadrados estándar (rápido y robusto). GaussMLE: Máxima verosimilitud (óptimo con pocos fotones).",
            "GaussLQ minimiza la suma ponderada de residuos cuadráticos chi^2; GaussMLE maximiza el logaritmo de verosimilitud poissoniana."
        ))
        hp3.addWidget(self.combo_picasso_method)
        lay_pic.addLayout(hp3)

        self.chk_box_offset = QCheckBox("Compensar offset de caja Picasso (+box/2)")
        self.chk_box_offset.setChecked(True)
        self.chk_box_offset.setToolTip(make_tooltip(
            "Compensar Offset de Caja (+box/2)",
            "Mantiene las partículas perfectamente centradas en su posición global dentro de la imagen.",
            "Aplica la corrección baricéntrica local-a-global +(box_size/2) requerida por el estándar de Picasso."
        ))
        lay_pic.addWidget(self.chk_box_offset)

        self.chk_picasso_autoscale = QCheckBox("Auto-escalado dinámico 16-bit")
        self.chk_picasso_autoscale.setChecked(True)
        self.chk_picasso_autoscale.setToolTip(make_tooltip(
            "Auto-escalado Dinámico de Rango",
            "Ajusta automáticamente las intensidades para cámaras científicas de 16 bits sin saturar.",
            "Normaliza el rango dinámico de la imagen para prevenir sub-flujo numérico en el gradiente de Sobel."
        ))
        lay_pic.addWidget(self.chk_picasso_autoscale)

        # Sub-parámetros cámara Picasso
        grid_cam = QGridLayout()
        grid_cam.addWidget(QLabel("Baseline:"), 0, 0)
        self.spin_picasso_baseline = QSpinBox()
        self.spin_picasso_baseline.setRange(0, 10000)
        self.spin_picasso_baseline.setValue(100)
        self.spin_picasso_baseline.setToolTip(make_tooltip(
            "Línea de Base / Offset del Sensor (ADU)",
            "Nivel de corriente oscura o negro de la cámara cuando no hay luz.",
            "Valor de compensación electrónica (bias) sustraído a cada píxel antes del cómputo fotométrico."
        ))
        grid_cam.addWidget(self.spin_picasso_baseline, 0, 1)

        grid_cam.addWidget(QLabel("Gain:"), 0, 2)
        self.spin_picasso_gain = QDoubleSpinBox()
        self.spin_picasso_gain.setRange(0.1, 100.0)
        self.spin_picasso_gain.setValue(1.0)
        self.spin_picasso_gain.setToolTip(make_tooltip(
            "Ganancia del Sensor (e- / ADU)",
            "Factor de conversión electrónica de la cámara.",
            "Ganancia del convertidor analógico-digital (ADC) para transformar unidades de display a fotoelectrones."
        ))
        grid_cam.addWidget(self.spin_picasso_gain, 0, 3)

        grid_cam.addWidget(QLabel("Sensitivity:"), 1, 0)
        self.spin_picasso_sens = QDoubleSpinBox()
        self.spin_picasso_sens.setRange(0.1, 100.0)
        self.spin_picasso_sens.setValue(1.0)
        self.spin_picasso_sens.setToolTip(make_tooltip(
            "Sensibilidad Cuántica / Factor de Conversión",
            "Eficiencia del sensor en transformar fotones incidentes en electrones.",
            "Factor de sensibilidad fotónica para la determinación cuantitativa del número absoluto de fotones emitidos."
        ))
        grid_cam.addWidget(self.spin_picasso_sens, 1, 1)
        lay_pic.addLayout(grid_cam)

        self.stack_motor.addWidget(page_picasso)

        # Página Trackpy
        page_trackpy = QWidget()
        lay_tp = QVBoxLayout(page_trackpy)
        lay_tp.setContentsMargins(0, 5, 0, 5)

        ht1 = QHBoxLayout()
        ht1.addWidget(QLabel("Diámetro (px impar):"))
        self.spin_diameter = QSpinBox()
        self.spin_diameter.setRange(3, 31)
        self.spin_diameter.setSingleStep(2)
        self.spin_diameter.setValue(5)
        self.spin_diameter.setToolTip(make_tooltip(
            "Diámetro Estimado de Partícula (px)",
            "Ancho aproximado en píxeles de una nanopartícula en la micrografía.",
            "Tamaño característico impar del filtro pasa-bandas circular de Crocker-Grier."
        ))
        ht1.addWidget(self.spin_diameter)
        lay_tp.addLayout(ht1)

        ht2 = QHBoxLayout()
        ht2.addWidget(QLabel("Masa Mínima (0=auto):"))
        self.spin_minmass = QDoubleSpinBox()
        self.spin_minmass.setRange(0.0, 50000.0)
        self.spin_minmass.setValue(0.05)
        self.spin_minmass.setSingleStep(0.05)
        self.spin_minmass.setToolTip(make_tooltip(
            "Masa / Brillo Mínimo (Trackpy)",
            "Brillo integrado mínimo que debe sumar una mancha para ser aceptada como partícula real.",
            "Integral mínima de intensidad fotónica sobre el fondo local; previene la detección de fluctuaciones térmicas."
        ))
        ht2.addWidget(self.spin_minmass)
        lay_tp.addLayout(ht2)

        ht3 = QHBoxLayout()
        ht3.addWidget(QLabel("Separación (px, 0=auto):"))
        self.spin_separation = QDoubleSpinBox()
        self.spin_separation.setRange(0.0, 100.0)
        self.spin_separation.setValue(7.0)
        self.spin_separation.setToolTip(make_tooltip(
            "Separación Mínima entre Picos (px)",
            "Distancia mínima en píxeles para que dos partículas contiguas no se fusionen en una sola.",
            "Radio de exclusión espacial entre máximos locales durante la supresión de no-máximos."
        ))
        ht3.addWidget(self.spin_separation)
        lay_tp.addLayout(ht3)

        ht4 = QHBoxLayout()
        ht4.addWidget(QLabel("Percentil Umbral (%):"))
        self.spin_percentile = QSpinBox()
        self.spin_percentile.setRange(0, 100)
        self.spin_percentile.setValue(64)
        self.spin_percentile.setToolTip(make_tooltip(
            "Percentil de Umbralización (%)",
            "Porcentaje de píxeles oscuros a descartar antes de buscar los picos de luz.",
            "Corte acumulativo en el histograma de intensidad de la imagen tras el filtrado pasa-bandas."
        ))
        ht4.addWidget(self.spin_percentile)
        lay_tp.addLayout(ht4)

        ht5 = QHBoxLayout()
        ht5.addWidget(QLabel("Tamaño Ruido (px):"))
        self.spin_noise_size = QDoubleSpinBox()
        self.spin_noise_size.setRange(0.1, 10.0)
        self.spin_noise_size.setValue(1.0)
        self.spin_noise_size.setToolTip(make_tooltip(
            "Tamaño de Grano de Ruido (px)",
            "Escala de suavizado para eliminar píxeles ruidosos aislados (usualmente 1 px).",
            "Desviación estándar sigma_ruido del núcleo Gaussiano de convolución para atenuar ruido de alta frecuencia."
        ))
        ht5.addWidget(self.spin_noise_size)
        lay_tp.addLayout(ht5)

        self.chk_rl = QCheckBox("Pre-filtrado Deconvolución Richardson-Lucy")
        self.chk_rl.setChecked(False)
        self.chk_rl.setToolTip(make_tooltip(
            "Pre-filtrado Deconvolución Richardson-Lucy",
            "Aplica un filtro óptico que re-enfoca matemáticamente la imagen antes de buscar las partículas.",
            "Inversión iterativa no lineal de la degradación por difracción con la función de punto extendido (PSF)."
        ))
        lay_tp.addWidget(self.chk_rl)

        h_rl = QHBoxLayout()
        h_rl.addWidget(QLabel("Iter RL:"))
        self.spin_rl_iter = QSpinBox()
        self.spin_rl_iter.setRange(1, 100)
        self.spin_rl_iter.setValue(15)
        self.spin_rl_iter.setToolTip(make_tooltip(
            "Número de Iteraciones de Deconvolución",
            "Cuántas veces se refina el enfoque (15-20 iteraciones suele ser el balance ideal).",
            "Iteraciones del algoritmo Richardson-Lucy; valores excesivos (>40) pueden amplificar ruido en alta frecuencia."
        ))
        h_rl.addWidget(self.spin_rl_iter)

        h_rl.addWidget(QLabel("PSF σ:"))
        self.spin_rl_sigma = QDoubleSpinBox()
        self.spin_rl_sigma.setRange(0.1, 10.0)
        self.spin_rl_sigma.setValue(1.5)
        self.spin_rl_sigma.setToolTip(make_tooltip(
            "Ancho de PSF Teórica (px)",
            "Radio óptico difraccional de la mancha que produce el microscopio.",
            "Desviación estándar espacial sigma_psf del núcleo Gaussiano modelado para la deconvolución."
        ))
        h_rl.addWidget(self.spin_rl_sigma)
        lay_tp.addLayout(h_rl)

        self.btn_run_rl_direct = QPushButton("⚡ Ejecutar Deconvolución RL")
        self.btn_run_rl_direct.setStyleSheet("color: #f9e2af; font-weight: bold;")
        self.btn_run_rl_direct.setToolTip(make_tooltip(
            "Ejecutar Deconvolución Richardson-Lucy Directa",
            "Aplica la deconvolución sobre la imagen TIFF cargada y la superpone como capa conmutable.",
            "Inversión iterativa no lineal de la convolución por difracción generando la capa img_item_rl."
        ))
        self.btn_run_rl_direct.clicked.connect(self._on_run_rl_deconvolution)
        lay_tp.addWidget(self.btn_run_rl_direct)

        self.stack_motor.addWidget(page_trackpy)
        lay_loc.addWidget(self.stack_motor)

        self.chk_extended = QCheckBox("Incluir parámetros extendidos en salida")
        self.chk_extended.setChecked(True)
        self.chk_extended.setToolTip(make_tooltip(
            "Incluir Parámetros Fotométricos Extendidos",
            "Calcula además el brillo, el fondo local y la elipticidad de cada partícula detectada.",
            "Almacena fotones integrados, excentricidad, ancho local de PSF e incertidumbre de Cramer-Rao en locs_df."
        ))
        lay_loc.addWidget(self.chk_extended)

        self.btn_detect = QPushButton("🔍 Detectar Partículas (Localizar)")
        self.btn_detect.setObjectName("primaryBtn")
        self.btn_detect.setToolTip(make_tooltip(
            "Detectar y Localizar Partículas",
            "Ejecuta la búsqueda automática de nanopartículas con los parámetros seleccionados.",
            "Lanza el motor de localización sub-píxel, actualiza locs_df y renderiza la nube de partículas en el espacio real."
        ))
        self.btn_detect.clicked.connect(self._on_detect_particles)
        lay_loc.addWidget(self.btn_detect)

        left_layout.addWidget(grp_loc)

        # Grupo 5: Fases 2 y 3: Curación Manual y Desacople de Cúmulos
        grp_curation = QGroupBox("5. Fases 2 y 3: Curación y Desacople Fotométrico")
        grp_curation.setToolTip(make_tooltip(
            "Fases 2 y 3: Curación y Desacople Fotométrico",
            "Herramientas para identificar y resolver aglomerados de nanopartículas (dímeros, trímeros) mediante análisis del brillo y área.",
            "Desacopla la emisión de fuentes sub-difraccionales mediante modelos estequiométricos V/V₀ y ajuste de n-Gaussianas con PSF calibrada."
        ))
        lay_cur = QVBoxLayout(grp_curation)

        self.lbl_cluster_summary = QLabel("Aglomerados: - | Sobrepuestas: -")
        self.lbl_cluster_summary.setStyleSheet("color: #fab387; font-weight: bold; font-size: 11px;")
        self.lbl_cluster_summary.setToolTip(make_tooltip(
            "Resumen de Detección de Aglomerados",
            "Muestra la cantidad de partículas sospechosas de estar agrupadas o sobrepuestas.",
            "Conteo de componentes conexas en el grafo de proximidad euclidiana con d < 0.6 a_nominal y firmas fotométricas V > 1.25 V₀."
        ))
        lay_cur.addWidget(self.lbl_cluster_summary)

        self.lbl_monomer_signature = QLabel("Firma Monómero: V₀=- | A₀=- | σ_psf=-")
        self.lbl_monomer_signature.setStyleSheet("color: #89dceb; font-size: 10px; font-family: monospace;")
        self.lbl_monomer_signature.setToolTip(make_tooltip(
            "Firma Fotométrica del Monómero Aislado",
            "Volumen integrado V₀, área proyectada A₀ y radio óptico σ_psf representativos de una partícula solitaria.",
            "Mediana estadística robusta de la integral fotónica y el tensor de inercia espacial evaluados sobre partículas aisladas en la red."
        ))
        lay_cur.addWidget(self.lbl_monomer_signature)

        h_tol = QHBoxLayout()
        h_tol.addWidget(QLabel("Tolerancia (±%):"))
        self.spin_cluster_tolerance = QDoubleSpinBox()
        self.spin_cluster_tolerance.setRange(5.0, 50.0)
        self.spin_cluster_tolerance.setValue(20.0)
        self.spin_cluster_tolerance.setSingleStep(5.0)
        self.spin_cluster_tolerance.setSuffix("%")
        self.spin_cluster_tolerance.setToolTip(make_tooltip(
            "Tolerancia de Clasificación de Aglomerados (±%)",
            "Margen de variación admitido en el brillo y área de una partícula antes de catalogarla como dímero o cúmulo.",
            "Intervalo de confianza porcentual [1 - tol, 1 + tol] aplicado a los múltiplos enteros del volumen fotométrico V₀."
        ))
        h_tol.addWidget(self.spin_cluster_tolerance)
        lay_cur.addLayout(h_tol)

        self.btn_detect_clusters = QPushButton("🔍 Detectar Aglomerados y Cadenas")
        self.btn_detect_clusters.setObjectName("primaryBtn")
        self.btn_detect_clusters.setToolTip(make_tooltip(
            "Detectar Aglomerados, Cadenas y Sobrepuestas",
            "Identifica componentes conexas con distancia d < 0.6 a_nom y analiza firmas fotométricas V/V₀ y área A/A₀.",
            "Segmenta contornos de iso-intensidad con Green-Gauss y puebla la tabla de cúmulos para curación."
        ))
        self.btn_detect_clusters.clicked.connect(self._on_detect_clusters)
        lay_cur.addWidget(self.btn_detect_clusters)

        # Tabla rápida de aglomerados enriquecida con fotometría
        self.table_clusters = QTableWidget(0, 7)
        self.table_clusters.setHorizontalHeaderLabels(["ID", "Tipo", "Det", "Est", "Vol/V₀", "Área/A₀", "Estado"])
        self.table_clusters.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table_clusters.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table_clusters.setFixedHeight(130)
        self.table_clusters.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_clusters.setToolTip(make_tooltip(
            "Registro Detallado de Aglomerados Detectados",
            "Haga clic en una fila para centrar e inspeccionar el cúmulo en el visor del espacio real.",
            "Matriz de topología y fotometría: identificador, multiplicidad sugerida k = round(V/V₀), relación de áreas y estado de curación."
        ))
        self.table_clusters.cellClicked.connect(self._on_cluster_table_clicked)
        lay_cur.addWidget(self.table_clusters)

        # Herramienta Crear Cúmulo Manual
        h_clust_man = QHBoxLayout()
        self.btn_create_manual_cluster = QPushButton("➕ Crear Cúmulo Manual (Sel)")
        self.btn_create_manual_cluster.setObjectName("accentBtn")
        self.btn_create_manual_cluster.setToolTip(make_tooltip(
            "Crear Cúmulo Manual con Partículas Seleccionadas",
            "Seleccione 2 o más partículas en el visor o tabla y presione aquí para asociarlas en un nuevo cúmulo con su contorno y estequiometría.",
            "Permite aplicar sobre este grupo personalizado el desacople multi-gaussiano o las reglas de nodo/COM."
        ))
        self.btn_create_manual_cluster.clicked.connect(self._on_create_manual_cluster)
        h_clust_man.addWidget(self.btn_create_manual_cluster)
        lay_cur.addLayout(h_clust_man)

        # Acciones sobre el Cúmulo Seleccionado (Uno a Uno)
        lbl_single = QLabel("Acción Cúmulo Seleccionado:")
        lbl_single.setStyleSheet("color: #f9e2af; font-weight: bold; font-size: 11px;")
        lay_cur.addWidget(lbl_single)

        # Control interactivo de contorno y número de gaussianas para el cúmulo seleccionado
        h_c_cfg = QHBoxLayout()
        h_c_cfg.addWidget(QLabel("Umbral (%):"))
        self.spin_cluster_contour_thresh = QDoubleSpinBox()
        self.spin_cluster_contour_thresh.setRange(5.0, 80.0)
        self.spin_cluster_contour_thresh.setValue(20.0)
        self.spin_cluster_contour_thresh.setSingleStep(5.0)
        self.spin_cluster_contour_thresh.setToolTip(make_tooltip(
            "Umbral de Contorno Fotométrico (%)",
            "Nivel de corte de intensidad sobre el fondo local para delimitar la silueta del cúmulo seleccionado.",
            "Umbral relativo Ith = Ibg + (thr/100)*(Imax - Ibg) para calcular el contorno de Green sobre el parche."
        ))
        self.spin_cluster_contour_thresh.valueChanged.connect(self._on_cluster_contour_thresh_changed)
        h_c_cfg.addWidget(self.spin_cluster_contour_thresh)

        h_c_cfg.addWidget(QLabel("Fitear (n):"))
        self.spin_cluster_n_gaussians = QSpinBox()
        self.spin_cluster_n_gaussians.setRange(1, 8)
        self.spin_cluster_n_gaussians.setValue(2)
        self.spin_cluster_n_gaussians.setToolTip(make_tooltip(
            "Número de Gaussianas a Fitear (n)",
            "Cantidad de componentes gaussianas independientes para descomponer este cúmulo.",
            "Orden del modelo multi-emisor n_particles para optimización no lineal por Levenberg-Marquardt."
        ))
        h_c_cfg.addWidget(self.spin_cluster_n_gaussians)
        lay_cur.addLayout(h_c_cfg)

        self.btn_cluster_add_particles = QPushButton("➕ Añadir Partículas al Contorno (Modo Clic)")
        self.btn_cluster_add_particles.setCheckable(True)
        self.btn_cluster_add_particles.setStyleSheet("QPushButton:checked { background-color: #f9e2af; color: #11111b; font-weight: bold; }")
        self.btn_cluster_add_particles.setToolTip(make_tooltip(
            "Añadir Partículas al Contorno",
            "Active este botón y haga clic sobre partículas en el visor para incorporarlas manualmente al cúmulo seleccionado.",
            "Permite asociar partículas contiguas o satélites no reconocidas automáticamente dentro del contorno activo."
        ))
        self.btn_cluster_add_particles.toggled.connect(self._on_toggle_add_particles_to_cluster)
        lay_cur.addWidget(self.btn_cluster_add_particles)

        # Herramienta de Centros Visuales Manuales (Condiciones Iniciales)
        h_seeds = QHBoxLayout()
        self.btn_pick_visual_seeds = QPushButton("📍 Centros Visuales")
        self.btn_pick_visual_seeds.setCheckable(True)
        self.btn_pick_visual_seeds.setStyleSheet("QPushButton:checked { background-color: #a6e3a1; color: #11111b; font-weight: bold; }")
        self.btn_pick_visual_seeds.setToolTip(make_tooltip(
            "Marcar Centros Visuales (Modo Clic)",
            "Active este botón y haga clic en el visor en las posiciones donde visualmente estima que hay partículas.",
            "Estos puntos sirven como condiciones iniciales (initial_seeds) para el ajuste multi-gaussiano."
        ))
        self.btn_pick_visual_seeds.toggled.connect(self._on_toggle_pick_visual_seeds)
        h_seeds.addWidget(self.btn_pick_visual_seeds)

        self.btn_use_detected_as_seeds = QPushButton("📌 Usar Detectadas")
        self.btn_use_detected_as_seeds.setToolTip(make_tooltip(
            "Usar Partículas Detectadas como Semillas",
            "Copia las posiciones de las partículas seleccionadas o del cúmulo como centros iniciales de ajuste.",
            "Inicializa el optimizador no lineal directamente sobre las partículas detectadas existentes."
        ))
        self.btn_use_detected_as_seeds.clicked.connect(self._on_use_detected_as_seeds)
        h_seeds.addWidget(self.btn_use_detected_as_seeds)

        self.btn_clear_visual_seeds = QPushButton("🗑️ Limpiar")
        self.btn_clear_visual_seeds.setToolTip("Borra los centros visuales marcados manualmente en el gráfico.")
        self.btn_clear_visual_seeds.clicked.connect(self._on_clear_visual_seeds)
        h_seeds.addWidget(self.btn_clear_visual_seeds)

        self.lbl_visual_seeds_status = QLabel("Semillas: 0")
        self.lbl_visual_seeds_status.setStyleSheet("color: #a6e3a1; font-weight: bold; font-size: 10px;")
        h_seeds.addWidget(self.lbl_visual_seeds_status)
        lay_cur.addLayout(h_seeds)

        self.btn_resolve_selected_gaussian = QPushButton("🎯 Desacoplar Sel. (Fit Multi-Gauss)")
        self.btn_resolve_selected_gaussian.setObjectName("primaryBtn")
        self.btn_resolve_selected_gaussian.setToolTip(make_tooltip(
            "Ajuste Multi-Gaussiano sobre Cúmulo Seleccionado",
            "Descompone el aglomerado seleccionado en n partículas individuales mediante ajuste óptico avanzado.",
            "Optimización no lineal por Levenberg-Marquardt ajustando n centros (x_i, y_i) con ancho de PSF fijo σ = σ_psf."
        ))
        self.btn_resolve_selected_gaussian.clicked.connect(self._on_resolve_selected_cluster_gaussian)
        lay_cur.addWidget(self.btn_resolve_selected_gaussian)

        h_sel_aux = QHBoxLayout()
        self.btn_resolve_selected_nearest = QPushButton("⚡ Conservar Nodo (Sel)")
        self.btn_resolve_selected_nearest.setToolTip(make_tooltip(
            "Conservar Nodo de Red (Cúmulo Seleccionado)",
            "Mantiene solo la partícula del grupo que esté mejor alineada con la cuadrícula periódica y descarta las demás.",
            "Minimiza la distancia euclidiana al nodo ideal más próximo de la red ortogonal R_{u,v} y purga satélites espurios."
        ))
        self.btn_resolve_selected_nearest.clicked.connect(self._on_resolve_selected_cluster_nearest)
        h_sel_aux.addWidget(self.btn_resolve_selected_nearest)

        self.btn_resolve_selected_com = QPushButton("⚡ Fusionar COM (Sel)")
        self.btn_resolve_selected_com.setToolTip(make_tooltip(
            "Fusión Baricéntrica (Cúmulo Seleccionado)",
            "Une todas las partículas del grupo en un único punto promedio ponderado por su brillo.",
            "Calcula el centro de masa fotométrico r_cm = sum(w_i * r_i) / sum(w_i) asignando peso w_i proporcional a la intensidad."
        ))
        self.btn_resolve_selected_com.clicked.connect(self._on_resolve_selected_cluster_com)
        h_sel_aux.addWidget(self.btn_resolve_selected_com)
        lay_cur.addLayout(h_sel_aux)

        # Sub-panel de Inspección y Desacople de Punto Sospechoso (Manual)
        grp_suspicious = QGroupBox("🔍 Inspección de Punto Sospechoso (Manual)")
        grp_suspicious.setStyleSheet(
            "QGroupBox { font-size: 11px; font-weight: bold; color: #f9e2af; "
            "border: 1px solid #45475a; border-radius: 5px; margin-top: 6px; padding: 6px; }"
        )
        grp_suspicious.setToolTip(make_tooltip(
            "Inspección Fotométrica de Punto Sospechoso",
            "Permite analizar en detalle cualquier mancha individual para determinar si oculta múltiples emisores superpuestos.",
            "Extracción de parche local y contorno de iso-intensidad para computar volumen normalizado V/V₀ y área A/A₀."
        ))
        lay_susp = QVBoxLayout(grp_suspicious)
        lay_susp.setSpacing(6)

        h_susp_thr = QHBoxLayout()
        h_susp_thr.addWidget(QLabel("Umbral Contorno (%):"))
        self.spin_suspicious_thresh = QDoubleSpinBox()
        self.spin_suspicious_thresh.setRange(5.0, 80.0)
        self.spin_suspicious_thresh.setValue(20.0)
        self.spin_suspicious_thresh.setSingleStep(5.0)
        self.spin_suspicious_thresh.setToolTip(make_tooltip(
            "Umbral de Contorno Iso-intensidad (%)",
            "Nivel de brillo relativo sobre el fondo local (10% a 40%) para delimitar la silueta fotométrica de la mancha.",
            "Nivel de corte biseccional en el fondo local I_th = I_bg + (thr/100)*(I_max - I_bg) para el polígono de Green."
        ))
        self.spin_suspicious_thresh.valueChanged.connect(self._update_suspicious_spot_inspection)
        h_susp_thr.addWidget(self.spin_suspicious_thresh)
        lay_susp.addLayout(h_susp_thr)

        self.lbl_suspicious_info = QLabel("Seleccione 1 partícula (clic en visor o tabla) para evaluar contorno y volumen.")
        self.lbl_suspicious_info.setStyleSheet("font-family: monospace; font-size: 10px; color: #a6adc8;")
        self.lbl_suspicious_info.setWordWrap(True)
        self.lbl_suspicious_info.setToolTip(make_tooltip(
            "Diagnóstico del Punto Inspeccionado",
            "Presenta la posición, área en píxeles y razón de volumen frente al monómero unitario.",
            "Relaciones estequiométricas locales que fundamentan la necesidad de un desacople n-Gaussiano."
        ))
        lay_susp.addWidget(self.lbl_suspicious_info)

        h_susp_n = QHBoxLayout()
        h_susp_n.addWidget(QLabel("Desacoplar en (n):"))
        self.spin_suspicious_n = QSpinBox()
        self.spin_suspicious_n.setRange(2, 8)
        self.spin_suspicious_n.setValue(2)
        self.spin_suspicious_n.setToolTip(make_tooltip(
            "Multiplicidad de Desacople (n)",
            "Cantidad de partículas en las que desea desacoplar este spot sospechoso (ej. 2 para dímero, 3 para trímero).",
            "Número de componentes gaussianas independientes sumadas en la optimización por mínimos cuadrados no lineales."
        ))
        h_susp_n.addWidget(self.spin_suspicious_n)

        self.btn_resolve_suspicious = QPushButton("🎯 Desacoplar Spot (Fit)")
        self.btn_resolve_suspicious.setObjectName("primaryBtn")
        self.btn_resolve_suspicious.setEnabled(False)
        self.btn_resolve_suspicious.setToolTip(make_tooltip(
            "Desacoplar Punto Seleccionado",
            "Ajusta n Gaussianas sobre la mancha seleccionada y la reemplaza por las nuevas posiciones resueltas.",
            "Minimización chi-cuadrado con restricciones de positividad y preservación de fotones totales."
        ))
        self.btn_resolve_suspicious.clicked.connect(self._on_resolve_suspicious_spot)
        h_susp_n.addWidget(self.btn_resolve_suspicious)
        lay_susp.addLayout(h_susp_n)

        lay_cur.addWidget(grp_suspicious)

        # Acciones Masivas (Todos los Cúmulos en Lote)
        lbl_batch = QLabel("Acciones en Lote (Todos):")
        lbl_batch.setStyleSheet("color: #a6adc8; font-size: 10px;")
        lay_cur.addWidget(lbl_batch)

        h_res_btns = QHBoxLayout()
        self.btn_resolve_all_gaussian = QPushButton("🎯 Desacoplar Todos")
        self.btn_resolve_all_gaussian.setToolTip(make_tooltip(
            "Desacoplar Todos los Cúmulos en Lote",
            "Aplica automáticamente el ajuste multi-gaussiano a todos los cúmulos detectados en la red.",
            "Descomposición estequiométrica secuencial sobre todos los grupos según su factor fotométrico V/V₀."
        ))
        self.btn_resolve_all_gaussian.clicked.connect(self._on_resolve_all_clusters_gaussian)
        h_res_btns.addWidget(self.btn_resolve_all_gaussian)

        self.btn_resolve_nearest = QPushButton("⚡ Conservar Nodo")
        self.btn_resolve_nearest.setToolTip(make_tooltip(
            "Conservar Nodos de Red en Lote",
            "En cada aglomerado, conserva la partícula más cercana a un nodo ideal de la red y descarta satélites.",
            "Filtrado masivo por distancia euclidiana mínima a nodos teóricos sin reajuste fotométrico continuo."
        ))
        self.btn_resolve_nearest.clicked.connect(self._on_resolve_clusters_nearest)
        h_res_btns.addWidget(self.btn_resolve_nearest)

        self.btn_resolve_com = QPushButton("⚡ Fusionar COM")
        self.btn_resolve_com.setToolTip(make_tooltip(
            "Fusión Baricéntrica en Lote",
            "Fusiona todas las partículas de cada cúmulo en su centro de masa ponderado por intensidad.",
            "Condensación puntual masiva al baricentro fotométrico sum(I_i * r_i)/sum(I_i)."
        ))
        self.btn_resolve_com.clicked.connect(self._on_resolve_clusters_com)
        h_res_btns.addWidget(self.btn_resolve_com)
        lay_cur.addLayout(h_res_btns)

        # Botones de historial/deshacer curación
        h_cur_aux = QHBoxLayout()
        self.btn_undo_curation = QPushButton("↺ Deshacer")
        self.btn_undo_curation.setToolTip(make_tooltip(
            "Deshacer Última Curación",
            "Revierte la última acción de eliminación o desacople para corregir modificaciones accidentales.",
            "Restaura el estado previo en la pila histórica LIFO de dataframes de coordenadas."
        ))
        self.btn_undo_curation.clicked.connect(self._on_undo_curation)
        h_cur_aux.addWidget(self.btn_undo_curation)

        self.btn_revert_curation = QPushButton("↺ Restaurar Todo")
        self.btn_revert_curation.setToolTip(make_tooltip(
            "Restaurar Coordenadas Originales",
            "Restaura todas las partículas detectadas originalmente antes de cualquier curación o filtrado.",
            "Sobrescribe locs_df con una copia profunda de raw_detected_df re-inicializando contornos."
        ))
        self.btn_revert_curation.clicked.connect(self._on_revert_curation)
        h_cur_aux.addWidget(self.btn_revert_curation)
        lay_cur.addLayout(h_cur_aux)

        left_layout.addWidget(grp_curation)

        # Grupo 6: Fase 4: Grilla Final, Vacancias & Consistencia
        grp_metrics = QGroupBox("6. Fase 4: Grilla Final, Vacancias & Consistencia")
        grp_metrics.setToolTip(make_tooltip(
            "Fase 4: Grilla Final, Vacancias y Consistencia",
            "Cálculo metrológico de la cuadrícula óptima, localización de vacancias y verificación de congruencia física.",
            "Optimización global de la caja delimitadora de la red, asignación biyectiva húngara y regla M + n_vac <= N²."
        ))
        lay_met = QVBoxLayout(grp_metrics)

        h_marg = QHBoxLayout()
        h_marg.addWidget(QLabel("Margen Consistencia (%):"))
        self.spin_consistency_margin = QDoubleSpinBox()
        self.spin_consistency_margin.setRange(0.0, 50.0)
        self.spin_consistency_margin.setValue(10.0)
        self.spin_consistency_margin.setSingleStep(1.0)
        self.spin_consistency_margin.setToolTip(make_tooltip(
            "Margen Físico de Consistencia Reticular (%)",
            "Tolerancia admitida (típicamente 5-15%) para validar que el conteo total de sitios coincida con la red teórica.",
            "Criterio de coherencia metrológica: |M + n_vac - N²| / N² <= margen/100."
        ))
        h_marg.addWidget(self.spin_consistency_margin)
        lay_met.addLayout(h_marg)

        self.btn_recalc_grid = QPushButton("📐 Ajustar Grilla y Calcular Vacancias")
        self.btn_recalc_grid.setObjectName("accentBtn")
        self.btn_recalc_grid.setToolTip(make_tooltip(
            "Ajustar Grilla Óptima y Localizar Vacancias",
            "Encuentra la posición global óptima de la red y ubica con precisión nanométrica los sitios desocupados.",
            "Ajusta la grilla ortogonal periódica 2D minimizando residuos euclidianos y asigna nodos desocupados mediante KDTree."
        ))
        self.btn_recalc_grid.clicked.connect(self._on_recalc_grid)
        lay_met.addWidget(self.btn_recalc_grid)

        self.lbl_real_metrics = QLabel(
            "Partículas: -\n"
            "Vacancias Prácticas: -% (- vac)\n"
            "Vacancias Teóricas: -% (- vac)\n"
            "Desorden σ_x: - nm\n"
            "Desorden σ_y: - nm\n"
            "Desorden Medio σ_pos: - nm\n"
            "Ancho g(r) σ_rdf: - nm"
        )
        self.lbl_real_metrics.setStyleSheet("font-family: monospace; font-size: 11px; color: #a6e3a1;")
        self.lbl_real_metrics.setToolTip(make_tooltip(
            "Métricas de Red en Espacio Real",
            "Desorden posicional medio σ_pos (nm), fracción de vacancias y ancho del primer pico de g(r).",
            "Varianza cartesianamente desacoplada sigma_pos = sqrt((sigma_x² + sigma_y²)/2) y ancho de pico en la RDF."
        ))
        lay_met.addWidget(self.lbl_real_metrics)

        self.lbl_consistency = QLabel("Consistencia: -")
        self.lbl_consistency.setStyleSheet("font-family: monospace; font-size: 11px; color: #89b4fa; font-weight: bold;")
        self.lbl_consistency.setToolTip(make_tooltip(
            "Dictamen de Consistencia Reticular",
            "Verifica si la suma de partículas detectadas y vacancias concuerda con el número total de sitios N x N.",
            "Regla de conservación de sitios reticulares: M + n_vac <= N² * (1 + margen/100)."
        ))
        lay_met.addWidget(self.lbl_consistency)

        btn_go_tab2 = QPushButton("Ir a Espacio Recíproco ➔")
        btn_go_tab2.setObjectName("primaryBtn")
        btn_go_tab2.setToolTip(make_tooltip(
            "Navegar al Espacio Recíproco (Fourier)",
            "Avanza a la pestaña 2 para calcular la difracción 2D y evaluar los picos armónicos de Bragg.",
            "Conmuta la interfaz y alimenta el motor espectral continuo NUFFT 2D con las coordenadas curadas."
        ))
        btn_go_tab2.clicked.connect(self._on_go_to_reciprocal)
        lay_met.addWidget(btn_go_tab2)

        left_layout.addWidget(grp_metrics)
        left_layout.addStretch()

        # --- Panel Derecho: Gráficos ---
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(8, 8, 8, 8)
        right_layout.setSpacing(8)

        # Plot 1: Visualizador Espacio Real con Barra de Capas y Colormap
        h_p1_hdr = QHBoxLayout()
        lbl_p1 = QLabel("Visualizador Espacio Real (Imagen Confocal & Red Cristalográfica):")
        lbl_p1.setStyleSheet("font-weight: bold; color: #cba6f7;")
        h_p1_hdr.addWidget(lbl_p1)
        h_p1_hdr.addStretch()

        btn_exp_real = QPushButton("💾 Exportar...")
        btn_exp_real.setToolTip(make_tooltip(
            "Exportar Imagen de Espacio Real",
            "Guarde este gráfico en alta resolución PNG (600 DPI) o vector SVG para publicaciones.",
            "Exportación directa del ViewBox a 2400 px con todas las capas y marcadores visibles."
        ))
        btn_exp_real.clicked.connect(lambda: self._export_single_plot(self.plot_real_space, "fig01_espacio_real_smlm"))
        h_p1_hdr.addWidget(btn_exp_real)
        right_layout.addLayout(h_p1_hdr)

        # Barra superior de control de capas y mapa de color (2 Filas compactas para libre redimensionamiento)
        bar_real_layers = QFrame()
        bar_real_layers.setStyleSheet(
            "background-color: #181825; border: 1px solid #313244; "
            "border-radius: 6px; padding: 2px;"
        )
        lay_layers = QVBoxLayout(bar_real_layers)
        lay_layers.setContentsMargins(6, 3, 6, 3)
        lay_layers.setSpacing(4)

        # Fila 1: Mapa de Color + Capas Base
        lay_row1 = QHBoxLayout()
        lay_row1.setContentsMargins(0, 0, 0, 0)
        lay_row1.setSpacing(8)

        lay_row1.addWidget(QLabel("🎨 Mapa:"))
        self.combo_colormap = QComboBox()
        self.combo_colormap.addItems([
            "cividis", "viridis", "plasma", "magma", "inferno", "turbo", "hot", "gray"
        ])
        self.combo_colormap.setCurrentText("cividis")
        self.combo_colormap.setToolTip(make_tooltip(
            "Mapa de Color Perceptual",
            "Cambia la paleta de colores para optimizar el contraste de las nanopartículas sobre el fondo.",
            "Tablas de color perceptualmente uniformes que preservan la linealidad de la luminancia en display."
        ))
        self.combo_colormap.currentTextChanged.connect(self._on_colormap_changed)
        lay_row1.addWidget(self.combo_colormap)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.VLine)
        sep1.setStyleSheet("color: #45475a;")
        lay_row1.addWidget(sep1)

        self.chk_layer_img = QCheckBox("🖼️ TIFF")
        self.chk_layer_img.setChecked(True)
        self.chk_layer_img.setToolTip(make_tooltip(
            "Capa: Imagen TIFF de Microscopía",
            "Muestra u oculta la imagen original de fondo adquirida en el microscopio.",
            "Controla la visibilidad de ImageItem posicionado en el espacio físico nanométrico (z=0)."
        ))
        self.chk_layer_img.toggled.connect(self._on_layer_visibility_changed)
        lay_row1.addWidget(self.chk_layer_img)

        self.chk_layer_filtered = QCheckBox("🧹 Filtro Fondo")
        self.chk_layer_filtered.setChecked(False)
        self.chk_layer_filtered.setStyleSheet("color: #a6e3a1; font-weight: bold;")
        self.chk_layer_filtered.setToolTip(make_tooltip(
            "Capa: Imagen Filtrada por Fondo/Ruido",
            "Superpone la micrografía tras sustraer el fondo relativo al máximo según el deslizador.",
            "Visualiza la capa intermedia filtrada (z=1) entre el TIFF original y la deconvolución RL."
        ))
        self.chk_layer_filtered.toggled.connect(self._on_layer_visibility_changed)
        lay_row1.addWidget(self.chk_layer_filtered)

        self.chk_layer_rl = QCheckBox("✨ RL Deconv")
        self.chk_layer_rl.setChecked(False)
        self.chk_layer_rl.setStyleSheet("color: #f9e2af; font-weight: bold;")
        self.chk_layer_rl.setToolTip(make_tooltip(
            "Capa: Deconvolución Richardson-Lucy",
            "Superpone u oculta la imagen procesada por deconvolución iterativa sobre el TIFF original.",
            "Visualiza la capa óptica de súper-resolución (z=2) con picos difraccionales re-enfocados."
        ))
        self.chk_layer_rl.toggled.connect(self._on_layer_visibility_changed)
        lay_row1.addWidget(self.chk_layer_rl)
        self.chk_overlay_rl = self.chk_layer_rl

        self.chk_layer_det = QCheckBox("🔵 Partículas (o)")
        self.chk_layer_det.setChecked(True)
        self.chk_layer_det.setStyleSheet("color: #89dceb; font-weight: bold;")
        self.chk_layer_det.setToolTip(make_tooltip(
            "Capa: Partículas Localizadas (o)",
            "Muestra u oculta los círculos azules sobre los centros de las partículas detectadas.",
            "Visualiza la nube de coordenadas sub-píxel (x_nm, y_nm) obtenidas por ajuste de PSF."
        ))
        self.chk_layer_det.toggled.connect(self._on_layer_visibility_changed)
        lay_row1.addWidget(self.chk_layer_det)

        self.chk_layer_clusters = QCheckBox("🟠 Aglomerados")
        self.chk_layer_clusters.setChecked(True)
        self.chk_layer_clusters.setStyleSheet("color: #fab387; font-weight: bold;")
        self.chk_layer_clusters.setToolTip(make_tooltip(
            "Capa: Aglomerados y Cúmulos (🟠)",
            "Resalta en color naranja las partículas sospechosas de estar agrupadas o sobrepuestas.",
            "Muestra emisores con distancia inter-partícula anómalamente corta o fotometría anómala."
        ))
        self.chk_layer_clusters.toggled.connect(self._on_layer_visibility_changed)
        lay_row1.addWidget(self.chk_layer_clusters)

        self.chk_layer_contours = QCheckBox("🔲 Contornos")
        self.chk_layer_contours.setChecked(True)
        self.chk_layer_contours.setStyleSheet("color: #f9e2af; font-weight: bold;")
        self.chk_layer_contours.setToolTip(make_tooltip(
            "Capa: Contornos Fotométricos (🔲)",
            "Dibuja los polígonos cerrados de contorno alrededor de las manchas de intensidad de los cúmulos.",
            "Curvas de nivel de iso-intensidad proyectadas a la escala nanométrica de la micrografía."
        ))
        self.chk_layer_contours.toggled.connect(self._on_layer_visibility_changed)
        lay_row1.addWidget(self.chk_layer_contours)

        lay_row1.addStretch()
        lay_layers.addLayout(lay_row1)

        # Fila 2: Capas de Análisis y Selección
        lay_row2 = QHBoxLayout()
        lay_row2.setContentsMargins(0, 0, 0, 0)
        lay_row2.setSpacing(8)

        lbl_capas2 = QLabel("Capas:")
        lbl_capas2.setStyleSheet("font-weight: bold; color: #cba6f7;")
        lay_row2.addWidget(lbl_capas2)

        self.chk_layer_selected = QCheckBox("🟣 Seleccionadas")
        self.chk_layer_selected.setChecked(True)
        self.chk_layer_selected.setStyleSheet("color: #cba6f7; font-weight: bold;")
        self.chk_layer_selected.setToolTip(make_tooltip(
            "Capa: Partículas Seleccionadas (🟣)",
            "Resalta con aros violetas las partículas marcadas para inspección o eliminación manual.",
            "Capa de dispersión de alta visibilidad para los índices activos en selected_particle_indices."
        ))
        self.chk_layer_selected.toggled.connect(self._on_layer_visibility_changed)
        lay_row2.addWidget(self.chk_layer_selected)

        self.chk_layer_vac = QCheckBox("❌ Vacancias (x)")
        self.chk_layer_vac.setChecked(True)
        self.chk_layer_vac.setStyleSheet("color: #f38ba8; font-weight: bold;")
        self.chk_layer_vac.setToolTip(make_tooltip(
            "Capa: Vacancias Reticulares (❌)",
            "Marca con cruces rojas las posiciones teóricas de la red donde falta una partícula impresa.",
            "Nodos de la red sin correspondencia unívoca dentro del radio de tolerancia d < a/2."
        ))
        self.chk_layer_vac.toggled.connect(self._on_layer_visibility_changed)
        lay_row2.addWidget(self.chk_layer_vac)

        self.chk_layer_grid = QCheckBox("📐 Malla (+)")
        self.chk_layer_grid.setChecked(False)
        self.chk_layer_grid.setStyleSheet("color: #a6adc8;")
        self.chk_layer_grid.setToolTip(make_tooltip(
            "Capa: Malla Reticular Teórica (+)",
            "Superpone la cuadrícula regular periódica óptima de período (a_x, a_y) para comparar la alineación.",
            "Red cristalina periódica ideal 2D optimizada globalmente sobre la muestra."
        ))
        self.chk_layer_grid.toggled.connect(self._on_layer_visibility_changed)
        lay_row2.addWidget(self.chk_layer_grid)

        self.chk_layer_roi = QCheckBox("✂️ Reglas ROI")
        self.chk_layer_roi.setChecked(True)
        self.chk_layer_roi.setStyleSheet("color: #fab387;")
        self.chk_layer_roi.setToolTip(make_tooltip(
            "Capa: Reglas Delimitadoras de ROI",
            "Muestra u oculta las líneas guía discontinuas de los límites de la región de interés.",
            "Guías móviles InfiniteLine que permiten ajustar dinámicamente los bordes del área de análisis."
        ))
        self.chk_layer_roi.toggled.connect(self._on_layer_roi_toggled)
        lay_row2.addWidget(self.chk_layer_roi)

        lay_row2.addStretch()
        lay_layers.addLayout(lay_row2)
        right_layout.addWidget(bar_real_layers)

        # Barra de Selección y Curación Manual de Partículas
        bar_curation = QFrame()
        bar_curation.setStyleSheet(
            "background-color: #181825; border: 1px solid #313244; "
            "border-radius: 6px; padding: 2px;"
        )
        lay_cbar = QHBoxLayout(bar_curation)
        lay_cbar.setContentsMargins(8, 3, 8, 3)
        lay_cbar.setSpacing(8)

        lay_cbar.addWidget(QLabel("Herramientas de Selección:"))
        self.btn_mode_nav = QPushButton("👆 Navegar (Zoom/Pan)")
        self.btn_mode_nav.setCheckable(True)
        self.btn_mode_nav.setChecked(True)
        self.btn_mode_nav.setToolTip(make_tooltip(
            "Modo Navegación (Zoom / Desplazamiento)",
            "Permite explorar la imagen con la rueda del ratón y arrastrando con el botón izquierdo.",
            "Modo estándar de manipulación del ViewBox sin selección de partículas."
        ))
        self.btn_mode_nav.clicked.connect(self._on_mode_nav)
        lay_cbar.addWidget(self.btn_mode_nav)

        self.btn_mode_click = QPushButton("🎯 Clic (Puntual)")
        self.btn_mode_click.setCheckable(True)
        self.btn_mode_click.setToolTip(make_tooltip(
            "Modo Clic (Selección Puntual)",
            "Haga clic sobre una partícula para seleccionarla o desmarcarla individualmente.",
            "Búsqueda por vecindad euclidiana con KDTree en el punto de clic del cursor."
        ))
        self.btn_mode_click.clicked.connect(self._on_mode_click)
        lay_cbar.addWidget(self.btn_mode_click)

        self.btn_mode_box = QPushButton("🔲 Caja ROI")
        self.btn_mode_box.setCheckable(True)
        self.btn_mode_box.setToolTip(make_tooltip(
            "Modo Caja (Selección de Área)",
            "Arrastre y redimensione el recuadro violeta para seleccionar un conjunto de partículas a la vez.",
            "Selección múltiple espacial acotada por coordenadas en un pg.RectROI interactivo."
        ))
        self.btn_mode_box.clicked.connect(self._on_mode_box)
        lay_cbar.addWidget(self.btn_mode_box)

        self.btn_mode_group = QButtonGroup(self)
        self.btn_mode_group.addButton(self.btn_mode_nav)
        self.btn_mode_group.addButton(self.btn_mode_click)
        self.btn_mode_group.addButton(self.btn_mode_box)

        sep_c = QFrame()
        sep_c.setFrameShape(QFrame.Shape.VLine)
        sep_c.setStyleSheet("color: #45475a;")
        lay_cbar.addWidget(sep_c)

        self.lbl_selected_status = QLabel("0 seleccionadas")
        self.lbl_selected_status.setStyleSheet("color: #cba6f7; font-weight: bold; font-size: 11px;")
        lay_cbar.addWidget(self.lbl_selected_status)

        self.btn_delete_selected = QPushButton("🗑️ Eliminar Seleccionadas (Del)")
        self.btn_delete_selected.setStyleSheet("color: #f38ba8; font-weight: bold;")
        self.btn_delete_selected.setToolTip(make_tooltip(
            "Eliminar Partículas Seleccionadas",
            "Elimina de forma permanente las partículas seleccionadas de la muestra.",
            "Purga los índices activos en locs_df y actualiza inmediatamente la grilla y el KDTree."
        ))
        self.btn_delete_selected.clicked.connect(self._on_delete_selected_particles)
        lay_cbar.addWidget(self.btn_delete_selected)

        self.btn_clear_selection = QPushButton("✕ Desmarcar")
        self.btn_clear_selection.setToolTip(make_tooltip(
            "Desmarcar Todo",
            "Limpia la selección actual y desmarca todas las partículas.",
            "Vacía el conjunto selected_particle_indices y oculta cajas de selección activas."
        ))
        self.btn_clear_selection.clicked.connect(self._on_clear_selection)
        lay_cbar.addWidget(self.btn_clear_selection)

        lay_cbar.addStretch()
        right_layout.addWidget(bar_curation)

        self.plot_real_space = pg.PlotWidget()
        self.plot_real_space.setAspectLocked(True)
        self.plot_real_space.showGrid(x=True, y=True, alpha=0.3)
        self.plot_real_space.setLabel('bottom', 'Posición X', units='nm')
        self.plot_real_space.setLabel('left', 'Posición Y', units='nm')
        self.plot_real_space.setToolTip(make_tooltip(
            "Visor de Espacio Real 2D (SMLM)",
            "Muestra la micrografía y la red nanométrica. Clic derecho para exportar en alta resolución (PNG 600 DPI / SVG) o restablecer vista.",
            "Lienzo métrico 2D con relación de aspecto ortonormal y coordenadas calibradas en nanómetros [nm]."
        ))
        self._setup_plot_export_menu(self.plot_real_space, "fig01_espacio_real_smlm", "Espacio Real & SMLM")
        self.plot_real_space.scene().sigMouseClicked.connect(self._on_real_space_clicked)
        right_layout.addWidget(self.plot_real_space, stretch=3)

        # Caja ROI de selección de área de partículas
        self.selection_box_roi = pg.RectROI([5000, 5000], [2000, 2000], pen=pg.mkPen('#cba6f7', width=2, style=Qt.PenStyle.DashLine))
        self.selection_box_roi.sigRegionChanged.connect(self._on_box_roi_changed)
        self.plot_real_space.addItem(self.selection_box_roi)
        self.selection_box_roi.setVisible(False)

        # Inicializar 4 Reglas Móviles de ROI
        self.line_roi_xmin = pg.InfiniteLine(pos=15.0 * 50.0, angle=90, movable=True, pen=pg.mkPen('#fab387', width=2, style=Qt.PenStyle.DashLine))
        self.line_roi_xmax = pg.InfiniteLine(pos=315.0 * 50.0, angle=90, movable=True, pen=pg.mkPen('#fab387', width=2, style=Qt.PenStyle.DashLine))
        self.line_roi_ymin = pg.InfiniteLine(pos=15.0 * 50.0, angle=0, movable=True, pen=pg.mkPen('#f38ba8', width=2, style=Qt.PenStyle.DashLine))
        self.line_roi_ymax = pg.InfiniteLine(pos=318.0 * 50.0, angle=0, movable=True, pen=pg.mkPen('#f38ba8', width=2, style=Qt.PenStyle.DashLine))

        for line in [self.line_roi_xmin, self.line_roi_xmax, self.line_roi_ymin, self.line_roi_ymax]:
            line.setHoverPen(pg.mkPen('#cba6f7', width=3))
            line.sigPositionChanged.connect(self._on_roi_line_dragged)
            self.plot_real_space.addItem(line)
            line.setVisible(True)

        # Plot 2: Función de Distribución Radial g(r)
        h_p2_hdr = QHBoxLayout()
        lbl_p2 = QLabel("Función de Distribución Radial g(r):")
        lbl_p2.setStyleSheet("font-weight: bold; color: #cba6f7;")
        h_p2_hdr.addWidget(lbl_p2)

        self.chk_rdf_manual_roi = QCheckBox("📏 Reglas Visuales ROI")
        self.chk_rdf_manual_roi.setStyleSheet("color: #fab387; font-weight: bold; font-size: 11px;")
        self.chk_rdf_manual_roi.setToolTip(make_tooltip(
            "Activar Reglas Visuales para g(r)",
            "Habilita 2 líneas verticales (r_min, r_max) y 1 línea horizontal (línea base) arrastrables en el visor g(r).",
            "Permite acotar visualmente la ventana del primer pico de coordinación y fijar o liberar el fondo."
        ))
        self.chk_rdf_manual_roi.toggled.connect(self._on_toggle_rdf_manual_roi)
        h_p2_hdr.addWidget(self.chk_rdf_manual_roi)

        self.chk_rdf_fix_bg = QCheckBox("Fijar Fondo")
        self.chk_rdf_fix_bg.setStyleSheet("color: #f38ba8; font-size: 10px;")
        self.chk_rdf_fix_bg.setToolTip(make_tooltip(
            "Fijar Línea Base de g(r)",
            "Fija la altura constante del fondo al nivel de la regla horizontal en lugar de optimizarla libremente.",
            "Condición de frontera en mínimos cuadrados: bg = const impuesta por la posición de la regla horizontal."
        ))
        self.chk_rdf_fix_bg.toggled.connect(self._on_rdf_rules_changed)
        h_p2_hdr.addWidget(self.chk_rdf_fix_bg)

        self.btn_reset_rdf_rules = QPushButton("↺")
        self.btn_reset_rdf_rules.setFixedWidth(28)
        self.btn_reset_rdf_rules.setToolTip(make_tooltip(
            "Restablecer Reglas Visuales de g(r)",
            "Restaura los límites de búsqueda nominales [0.65 a_nom, 1.35 a_nom] para el primer pico.",
            "Devuelve las líneas verticales r_min y r_max a la ventana por defecto."
        ))
        self.btn_reset_rdf_rules.clicked.connect(self._on_reset_rdf_rules)
        h_p2_hdr.addWidget(self.btn_reset_rdf_rules)

        h_p2_hdr.addStretch()

        btn_exp_rdf = QPushButton("💾 Exportar...")
        btn_exp_rdf.setToolTip(make_tooltip(
            "Exportar Gráfico g(r)",
            "Guarde este gráfico de correlación de pares en alta resolución PNG (600 DPI) o vector SVG.",
            "Exporta el perfil g(r) y el ajuste gaussiano del primer pico de coordinación."
        ))
        btn_exp_rdf.clicked.connect(lambda: self._export_single_plot(self.plot_rdf, "fig02_distribucion_radial_gr"))
        h_p2_hdr.addWidget(btn_exp_rdf)
        right_layout.addLayout(h_p2_hdr)

        self.plot_rdf = pg.PlotWidget()
        self.plot_rdf.showGrid(x=True, y=True, alpha=0.3)
        self.plot_rdf.setLabel('bottom', 'Distancia r', units='nm')
        self.plot_rdf.setLabel('left', 'g(r)')
        self.plot_rdf.setToolTip(make_tooltip(
            "Función de Distribución Radial g(r)",
            "Probabilidad de encontrar partículas a una distancia r respecto a cualquier otra. Clic derecho para exportar o auto-rango.",
            "Función de correlación par g(r) = (dN/dr)/(2π r ρ dr) con exclusión estérica y ajuste gaussiano del primer pico en r ~ a."
        ))
        self._setup_plot_export_menu(self.plot_rdf, "fig02_distribucion_radial_gr", "Distribución Radial g(r)")

        # Inicializar las 3 líneas móviles de g(r)
        self.line_rdf_rmin = pg.InfiniteLine(
            pos=300.0, angle=90, movable=True,
            pen=pg.mkPen('#fab387', width=1.8, style=Qt.PenStyle.DashLine),
            label="rmin: {value:.1f}", labelOpts={'position': 0.85, 'color': '#fab387'}
        )
        self.line_rdf_rmax = pg.InfiniteLine(
            pos=600.0, angle=90, movable=True,
            pen=pg.mkPen('#fab387', width=1.8, style=Qt.PenStyle.DashLine),
            label="rmax: {value:.1f}", labelOpts={'position': 0.85, 'color': '#fab387'}
        )
        self.line_rdf_bg = pg.InfiniteLine(
            pos=0.0, angle=0, movable=True,
            pen=pg.mkPen('#f38ba8', width=1.8, style=Qt.PenStyle.DotLine),
            label="Base: {value:.2f}", labelOpts={'position': 0.15, 'color': '#f38ba8'}
        )
        for line in [self.line_rdf_rmin, self.line_rdf_rmax, self.line_rdf_bg]:
            line.sigPositionChangeFinished.connect(self._on_rdf_rules_changed)

        right_layout.addWidget(self.plot_rdf, stretch=2)

        splitter.addWidget(scroll_area)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

    def _on_motor_changed(self, idx: int):
        self.stack_motor.setCurrentIndex(idx)

    # ==========================================================================
    # PESTAÑA 2: ESPACIO RECÍPROCO & FOURIER
    # ==========================================================================
    def _build_tab2(self):
        layout = QHBoxLayout(self.tab2)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)

        # --- Panel Izquierdo: Controles Espectrales ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.setSpacing(10)

        grp_recip = QGroupBox("Parámetros Espectrales 2D (NUFFT)")
        grp_recip.setToolTip(make_tooltip(
            "Parámetros Espectrales 2D (NUFFT)",
            "Configuración de la transformada de Fourier continua bidimensional para revelar la periodicidad de la red.",
            "Control de discretización espectral para evaluar la suma exponencial de estructura continua S(fx, fy) = |sum exp(i 2π f · r)|²."
        ))
        lay_rec = QVBoxLayout(grp_recip)

        h1 = QHBoxLayout()
        h1.addWidget(QLabel("Grilla Fourier 2D:"))
        self.combo_bins = QComboBox()
        self.combo_bins.addItems(["256 x 256 (Rápida)", "512 x 512 (Alta Res.)", "1024 x 1024 (Ultra Res.)"])
        self.combo_bins.setToolTip(make_tooltip(
            "Resolución de Malla de Fourier (Bins)",
            "Densidad de puntos de la cuadrícula espectral (256x256 para velocidad, 512x512 para alta fidelidad).",
            "Número de nodos de frecuencia K_x x K_y donde se muestrea el espacio recíproco continuo dentro del rango de Nyquist."
        ))
        self.combo_bins.currentIndexChanged.connect(self._on_recalculate_reciprocal)
        h1.addWidget(self.combo_bins)
        lay_rec.addLayout(h1)

        h2 = QHBoxLayout()
        h2.addWidget(QLabel("Banda Transversal (px):"))
        self.spin_band = QSpinBox()
        self.spin_band.setRange(1, 30)
        self.spin_band.setValue(3)
        self.spin_band.setToolTip(make_tooltip(
            "Ancho de Banda Transversal (px)",
            "Grosor de la franja alrededor de los ejes que se promedia para extraer los perfiles 1D de difracción.",
            "Anchura de integración delta_f_perp para proyectar el tensor 2D en cortes monodimensionales fx, fy y diagonal."
        ))
        self.spin_band.valueChanged.connect(self._on_recalculate_reciprocal)
        h2.addWidget(self.spin_band)
        lay_rec.addLayout(h2)

        h3 = QHBoxLayout()
        h3.addWidget(QLabel("Corte DC (f_cut / f0):"))
        self.spin_dc_cut = QDoubleSpinBox()
        self.spin_dc_cut.setRange(0.1, 0.8)
        self.spin_dc_cut.setValue(0.35)
        self.spin_dc_cut.setSingleStep(0.05)
        self.spin_dc_cut.setToolTip(make_tooltip(
            "Corte Central DC (f_cut / f0)",
            "Radio alrededor del centro (frecuencia cero) que se ignora para no confundir el brillo general con un pico de Bragg.",
            "Máscara circular de rechazo f < f_cut = ratio * f0 para suprimir la componente continua (haz directo q=0)."
        ))
        self.spin_dc_cut.valueChanged.connect(self._on_recalculate_reciprocal)
        h3.addWidget(self.spin_dc_cut)
        lay_rec.addLayout(h3)

        # Controles de Ajuste 1D & Sintonización Fina de Picos Individuales
        grp_peak_tuning = QGroupBox("Sintonización y Ajuste de Picos 1D")
        grp_peak_tuning.setToolTip(make_tooltip(
            "Sintonización y Ajuste Individual de Picos 1D",
            "Permite seleccionar cualquier pico de la jerarquía cristalográfica, elegir modelo simple o doble gaussiana, "
            "delimitar interactivamente la ventana de búsqueda (ROI) con reglas visuales y fijar o liberar la línea base.",
            "Ajusta modelos I(f) = H*exp(...) + bg o Doble Gaussiana con restricciones visuales directas en los gráficos de corte."
        ))
        lay_pt = QVBoxLayout(grp_peak_tuning)

        h_pk_sel = QHBoxLayout()
        h_pk_sel.addWidget(QLabel("Pico:"))
        self.combo_tune_peak = QComboBox()
        self.combo_tune_peak.addItems([
            "(1, 0) Fundamental X",
            "(0, 1) Fundamental Y",
            "(1, 1) Diagonal 45°",
            "(2, 0) 2do Orden X",
            "(0, 2) 2do Orden Y"
        ])
        self.combo_tune_peak.setToolTip(make_tooltip(
            "Pico Cristalográfico a Sintonizar",
            "Selecciona el pico sobre el cual actuarán las reglas visuales interactivas y los parámetros de ajuste.",
            "Conmuta las reglas de ROI hacia el gráfico de corte 1D correspondiente (Corte X, Corte Y o Corte Diagonal)."
        ))
        self.combo_tune_peak.currentIndexChanged.connect(self._on_tune_peak_changed)
        h_pk_sel.addWidget(self.combo_tune_peak)
        lay_pt.addLayout(h_pk_sel)

        h_pk_mod = QHBoxLayout()
        h_pk_mod.addWidget(QLabel("Modelo:"))
        self.combo_peak_model = QComboBox()
        self.combo_peak_model.addItems(["Doble Gaussiana (Doublet)", "Gaussiana Simple"])
        self.combo_peak_model.setToolTip(make_tooltip(
            "Modelo Espectral para el Pico",
            "Gaussiana Simple para reflexiones coherentes estándar, o Doble Gaussiana para picos desdoblados o con hombros.",
            "Descompone el pico en dos centros independientes con selección de componente principal según criterio."
        ))
        h_pk_mod.addWidget(self.combo_peak_model)
        lay_pt.addLayout(h_pk_mod)

        h_crit = QHBoxLayout()
        h_crit.addWidget(QLabel("Criterio:"))
        self.combo_peak_criterion = QComboBox()
        self.combo_peak_criterion.addItems(["Pico Más Alto (Amplitud)", "Más Cercano a Frecuencia Nominal"])
        self.combo_peak_criterion.setToolTip(make_tooltip(
            "Criterio de Selección de Pico Principal",
            "Determina cuál de las dos gaussianas define el vector recíproco y parámetro de red principal.",
            "Filtro de selección: amplitud máxima (H_max) o proximidad mínima a la frecuencia nominal esperada."
        ))
        h_crit.addWidget(self.combo_peak_criterion)
        lay_pt.addLayout(h_crit)

        # Reglas visuales ROI y Fondo para el pico
        h_pk_chks = QHBoxLayout()
        self.chk_peak_manual_roi = QCheckBox("📏 Reglas Visuales ROI")
        self.chk_peak_manual_roi.setStyleSheet("color: #fab387; font-weight: bold; font-size: 11px;")
        self.chk_peak_manual_roi.setToolTip(make_tooltip(
            "Activar Reglas Visuales para el Pico",
            "Muestra 2 líneas verticales (f_min, f_max) y 1 línea horizontal (fondo) en el corte 1D correspondiente.",
            "Arrastre las líneas en el corte 1D para acotar la ventana de ajuste y aislar el pico de difracción."
        ))
        self.chk_peak_manual_roi.toggled.connect(self._on_toggle_peak_rules)
        h_pk_chks.addWidget(self.chk_peak_manual_roi)

        self.chk_peak_fix_bg = QCheckBox("Fijar Base")
        self.chk_peak_fix_bg.setStyleSheet("color: #f38ba8; font-size: 10px;")
        self.chk_peak_fix_bg.setToolTip(make_tooltip(
            "Fijar Línea Base de Fondo",
            "Fija la altura constante del fondo al nivel de la regla horizontal en lugar de optimizarla libremente.",
            "Impone bg = const en la minimización de mínimos cuadrados no lineales."
        ))
        self.chk_peak_fix_bg.toggled.connect(self._on_peak_spin_changed)
        h_pk_chks.addWidget(self.chk_peak_fix_bg)
        lay_pt.addLayout(h_pk_chks)

        # Spinboxes para visualización / ajuste numérico de las reglas
        h_sp_f = QHBoxLayout()
        h_sp_f.addWidget(QLabel("f_min:"))
        self.spin_peak_fmin = QDoubleSpinBox()
        self.spin_peak_fmin.setRange(0.0, 0.05)
        self.spin_peak_fmin.setDecimals(5)
        self.spin_peak_fmin.setSingleStep(0.0002)
        self.spin_peak_fmin.valueChanged.connect(self._on_peak_spin_changed)
        h_sp_f.addWidget(self.spin_peak_fmin)

        h_sp_f.addWidget(QLabel("f_max:"))
        self.spin_peak_fmax = QDoubleSpinBox()
        self.spin_peak_fmax.setRange(0.0, 0.05)
        self.spin_peak_fmax.setDecimals(5)
        self.spin_peak_fmax.setSingleStep(0.0002)
        self.spin_peak_fmax.valueChanged.connect(self._on_peak_spin_changed)
        h_sp_f.addWidget(self.spin_peak_fmax)
        lay_pt.addLayout(h_sp_f)

        h_sp_bg = QHBoxLayout()
        h_sp_bg.addWidget(QLabel("Base (bg):"))
        self.spin_peak_bg = QDoubleSpinBox()
        self.spin_peak_bg.setRange(0.0, 1e7)
        self.spin_peak_bg.setDecimals(2)
        self.spin_peak_bg.setSingleStep(10.0)
        self.spin_peak_bg.valueChanged.connect(self._on_peak_spin_changed)
        h_sp_bg.addWidget(self.spin_peak_bg)

        self.btn_reset_peak_rules = QPushButton("↺")
        self.btn_reset_peak_rules.setFixedWidth(28)
        self.btn_reset_peak_rules.setToolTip(make_tooltip(
            "Restablecer Reglas del Pico",
            "Restaura la ventana y línea base automáticas basadas en la frecuencia nominal del pico.",
            "Reubica las reglas visuales en el centro del pico seleccionado."
        ))
        self.btn_reset_peak_rules.clicked.connect(self._on_reset_peak_rules)
        h_sp_bg.addWidget(self.btn_reset_peak_rules)
        lay_pt.addLayout(h_sp_bg)

        self.btn_apply_peak_fit = QPushButton("🎯 Re-Ajustar Pico Seleccionado")
        self.btn_apply_peak_fit.setObjectName("accentBtn")
        self.btn_apply_peak_fit.setToolTip(make_tooltip(
            "Re-Ajustar Pico Seleccionado",
            "Aplica el modelo y límites especificados exclusivamente sobre este pico y actualiza el gráfico y métricas.",
            "Ejecuta curve_fit con los límites impuestos por las reglas visuales y actualiza el análisis analítico directo."
        ))
        self.btn_apply_peak_fit.clicked.connect(self._on_apply_selected_peak_fit)
        lay_pt.addWidget(self.btn_apply_peak_fit)

        self.chk_double_peak = QCheckBox("Doble Gaussiana Global")
        self.chk_double_peak.setChecked(False)
        self.chk_double_peak.setStyleSheet("color: #a6adc8; font-size: 10px;")
        self.chk_double_peak.setToolTip(make_tooltip(
            "Activar Doble Gaussiana Globalmente",
            "Aplica ajuste de doble gaussiana en todos los cortes de difracción por defecto.",
            "Descompone simultáneamente todos los picos de difracción en dos componentes independientes."
        ))
        self.chk_double_peak.toggled.connect(self._on_recalculate_reciprocal)
        lay_pt.addWidget(self.chk_double_peak)

        lay_rec.addWidget(grp_peak_tuning)

        # Inicializar las 3 líneas móviles de sintonización de picos
        self.line_peak_fmin = pg.InfiniteLine(
            pos=0.001, angle=90, movable=True,
            pen=pg.mkPen('#fab387', width=1.5, style=Qt.PenStyle.DashLine),
            label="fmin: {value:.5f}", labelOpts={'position': 0.85, 'color': '#fab387'}
        )
        self.line_peak_fmax = pg.InfiniteLine(
            pos=0.003, angle=90, movable=True,
            pen=pg.mkPen('#fab387', width=1.5, style=Qt.PenStyle.DashLine),
            label="fmax: {value:.5f}", labelOpts={'position': 0.85, 'color': '#fab387'}
        )
        self.line_peak_bg = pg.InfiniteLine(
            pos=0.0, angle=0, movable=True,
            pen=pg.mkPen('#f38ba8', width=1.5, style=Qt.PenStyle.DotLine),
            label="Base: {value:.2f}", labelOpts={'position': 0.15, 'color': '#f38ba8'}
        )
        for line in [self.line_peak_fmin, self.line_peak_fmax, self.line_peak_bg]:
            line.sigPositionChangeFinished.connect(self._on_peak_line_dragged)

        btn_recalc_fourier = QPushButton("⚡ Recalcular Espectro 2D")
        btn_recalc_fourier.setObjectName("primaryBtn")
        btn_recalc_fourier.setToolTip(make_tooltip(
            "Recalcular Espectro 2D y Picos de Bragg",
            "Ejecuta de nuevo el cómputo espectral y el ajuste gaussiano de todos los picos de difracción.",
            "Re-evalúa la NUFFT 2D, extrae cortes radiales y optimiza parámetros gaussianos de Bragg (amplitud, centro, FWHM)."
        ))
        btn_recalc_fourier.clicked.connect(self._on_recalculate_reciprocal)
        lay_rec.addWidget(btn_recalc_fourier)

        left_layout.addWidget(grp_recip)

        # Tarjeta de Parámetros de Red
        grp_lattice = QGroupBox("Parámetros de Red Extraídos")
        grp_lattice.setToolTip(make_tooltip(
            "Parámetros Cristalográficos de Red Extraídos",
            "Resultados cristalográficos directos: distancia entre partículas (a_x, a_y), anisotropía y orden de red.",
            "Períodos a = 1/f_peak deducidos de los centros de Bragg, longitud de correlación de fase ξ = 2π/FWHM y relación de aspecto."
        ))
        lay_lat = QVBoxLayout(grp_lattice)

        self.lbl_recip_metrics = QLabel(
            "Período a_x: - nm\n"
            "Período a_y: - nm\n"
            "Período Medio a_mean: - nm\n"
            "Anisotropía (ax - ay): - nm\n"
            "Altura Pico H_x: -\n"
            "Altura Pico H_y: -\n"
            "FWHM_x: - nm^-1 (ξ_x: - nm)\n"
            "FWHM_y: - nm^-1 (ξ_y: - nm)"
        )
        self.lbl_recip_metrics.setStyleSheet("font-family: monospace; font-size: 11px; color: #89b4fa;")
        self.lbl_recip_metrics.setToolTip(make_tooltip(
            "Métricas Cristalográficas y Espectrales",
            "Muestra los períodos de red a_x y a_y en nanómetros, la anisotropía y las longitudes de coherencia espacial.",
            "Inversión espectral a_x = 1/f_x0, a_y = 1/f_y0, anisotropía a_x - a_y, y longitud de coherencia reticular xi = 2π / FWHM."
        ))
        lay_lat.addWidget(self.lbl_recip_metrics)

        self.btn_sync_curated = QPushButton("🔄 Actualizar con Puntos Curados")
        self.btn_sync_curated.setToolTip(make_tooltip(
            "Actualizar con Puntos Curados",
            "Recalcula el espacio recíproco y actualiza Monte Carlo con las coordenadas y vacancias prácticas curadas.",
            "Re-ejecuta el análisis recíproco con las partículas activas de locs_df e inyecta a_x, a_y y f_vac_prac en la simulación."
        ))
        self.btn_sync_curated.clicked.connect(self._on_sync_curated_to_reciprocal)
        lay_lat.addWidget(self.btn_sync_curated)

        btn_propagate = QPushButton("Propagar a Monte Carlo ➔")
        btn_propagate.setObjectName("accentBtn")
        btn_propagate.setToolTip(make_tooltip(
            "Propagar Parámetros a Monte Carlo",
            "Copia los períodos medidos y vacancias a la pestaña 3 para configurar automáticamente la simulación.",
            "Transfiere a_x, a_y, N y la fracción de vacancias al motor de simulación estocástica Debye-Waller."
        ))
        btn_propagate.clicked.connect(self._on_propagate_to_mc)
        lay_lat.addWidget(btn_propagate)

        left_layout.addWidget(grp_lattice)
        left_layout.addStretch()

        # --- Panel Derecho: Visualizador Espectral 2D, Cortes 1D y Métricas Analíticas ---
        self.scroll_reciprocal_right = QScrollArea()
        self.scroll_reciprocal_right.setWidgetResizable(True)
        self.scroll_reciprocal_right.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_reciprocal_right.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_reciprocal_right.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(8, 8, 8, 8)
        right_layout.setSpacing(10)
        self.scroll_reciprocal_right.setWidget(right_widget)

        # 1. Mapa 2D de Fourier
        h_m2d_hdr = QHBoxLayout()
        lbl_m2d = QLabel("Mapa Espectral 2D de Bragg log10(1 + S(fx, fy)):")
        lbl_m2d.setStyleSheet("font-weight: bold; color: #cba6f7;")
        h_m2d_hdr.addWidget(lbl_m2d)
        h_m2d_hdr.addStretch()

        btn_exp_fourier = QPushButton("💾 Exportar...")
        btn_exp_fourier.setToolTip(make_tooltip(
            "Exportar Espectro 2D de Fourier",
            "Guarde el patrón de difracción en alta resolución PNG (600 DPI) o vector SVG para publicaciones.",
            "Exporta el mapa log10(1 + S(fx, fy)) a 2400 px con ejes calibrados en nm⁻¹."
        ))
        btn_exp_fourier.clicked.connect(lambda: self._export_single_plot(self.plot_fourier_2d, "fig03_espectro_reciproco_2d"))
        h_m2d_hdr.addWidget(btn_exp_fourier)
        right_layout.addLayout(h_m2d_hdr)

        self.plot_fourier_2d = pg.PlotWidget()
        self.plot_fourier_2d.setAspectLocked(True)
        self.plot_fourier_2d.showGrid(x=True, y=True, alpha=0.3)
        self.plot_fourier_2d.setLabel('bottom', 'Frecuencia fx', units='nm^-1')
        self.plot_fourier_2d.setLabel('left', 'Frecuencia fy', units='nm^-1')
        self.plot_fourier_2d.setMinimumHeight(340)
        self.plot_fourier_2d.setToolTip(make_tooltip(
            "Mapa Espectral 2D de Bragg log10(1 + S(fx, fy))",
            "Patrón de difracción bidimensional. Puntos brillantes representan reflexiones de Bragg. Clic derecho para exportar o auto-rango.",
            "Densidad espectral continua NUFFT normalizada log10(1 + S(q)) mostrando simetría tetragonal, armónicos superiores y halo difuso."
        ))
        self._setup_plot_export_menu(self.plot_fourier_2d, "fig03_espectro_reciproco_2d", "Espectro Recíproco 2D NUFFT")
        right_layout.addWidget(self.plot_fourier_2d)

        # 2. Perfiles 1D con ajuste
        h_cuts_hdr = QHBoxLayout()
        lbl_cuts = QLabel("Cortes Transversales 1D y Ajuste Gaussiano de Picos de Bragg:")
        lbl_cuts.setStyleSheet("font-weight: bold; color: #cba6f7;")
        h_cuts_hdr.addWidget(lbl_cuts)
        h_cuts_hdr.addStretch()

        h_cuts_hdr.addWidget(QLabel("Vista:"))
        self.combo_profile_view = QComboBox()
        self.combo_profile_view.addItems(["Mostrar los 3 Cortes", "Solo Eje X (Horizontal)", "Solo Eje Y (Vertical)", "Solo Diagonal 45°"])
        self.combo_profile_view.setToolTip(make_tooltip(
            "Selector de Vista de Cortes 1D",
            "Permite alternar entre visualizar simultáneamente los 3 cortes o expandir uno en particular.",
            "Gestiona la visibilidad en el layout horizontal lay_cuts para inspección en detalle de perfiles monodimensionales."
        ))
        self.combo_profile_view.currentIndexChanged.connect(self._on_profile_view_changed)
        h_cuts_hdr.addWidget(self.combo_profile_view)

        btn_exp_cuts = QPushButton("💾 Exportar Cortes...")
        btn_exp_cuts.setToolTip(make_tooltip(
            "Exportar Cortes Espectrales 1D",
            "Guarda el perfil 1D activo (o los tres simultáneamente) en imágenes de alta resolución (PNG/SVG).",
            "Exportación directa de los perfiles con curvas de ajuste gaussiano superpuestas."
        ))
        btn_exp_cuts.clicked.connect(self._on_export_active_cut)
        h_cuts_hdr.addWidget(btn_exp_cuts)
        right_layout.addLayout(h_cuts_hdr)

        self.lay_cuts = QHBoxLayout()
        self.plot_cut_x = pg.PlotWidget(title="Perfil fx (Horizontal: Orden 1 + 2)")
        self.plot_cut_x.showGrid(x=True, y=True, alpha=0.3)
        self.plot_cut_x.setLabel('bottom', 'fx', units='nm^-1')
        self.plot_cut_x.setLabel('left', 'Intensidad')
        self.plot_cut_x.setMinimumHeight(220)
        self.plot_cut_x.setToolTip(make_tooltip(
            "Perfil fx (Horizontal: Orden 1 + 2)",
            "Corte de difracción a lo largo de fx con ajuste gaussiano de los picos fundamental (1,0) y segundo armónico (2,0). Clic derecho para exportar.",
            "Proyección de intensidad espectral con ajuste multivariable I(fx) = B + H1*exp(-(fx-f0)²/(2w1²)) + H2*exp(-(fx-2f0)²/(2w2²))."
        ))
        self._setup_plot_export_menu(self.plot_cut_x, "fig04_corte_espectral_fx", "Perfil fx (Horizontal)")

        self.plot_cut_y = pg.PlotWidget(title="Perfil fy (Vertical: Orden 1 + 2)")
        self.plot_cut_y.showGrid(x=True, y=True, alpha=0.3)
        self.plot_cut_y.setLabel('bottom', 'fy', units='nm^-1')
        self.plot_cut_y.setLabel('left', 'Intensidad')
        self.plot_cut_y.setMinimumHeight(220)
        self.plot_cut_y.setToolTip(make_tooltip(
            "Perfil fy (Vertical: Orden 1 + 2)",
            "Corte de difracción a lo largo de fy con ajuste gaussiano de los picos fundamental (0,1) y segundo armónico (0,2). Clic derecho para exportar.",
            "Proyección de intensidad espectral a lo largo del eje Y con ajuste gaussiano para deducir a_y, H_y y FWHM_y."
        ))
        self._setup_plot_export_menu(self.plot_cut_y, "fig05_corte_espectral_fy", "Perfil fy (Vertical)")

        self.plot_cut_diag = pg.PlotWidget(title="Perfil Diagonal 45° (Orden Cruzado (1,1))")
        self.plot_cut_diag.showGrid(x=True, y=True, alpha=0.3)
        self.plot_cut_diag.setLabel('bottom', 'f_diag', units='nm^-1')
        self.plot_cut_diag.setLabel('left', 'Intensidad')
        self.plot_cut_diag.setMinimumHeight(220)
        self.plot_cut_diag.setToolTip(make_tooltip(
            "Perfil Diagonal 45° (Orden Cruzado (1,1))",
            "Corte a 45° en el plano espectral correspondiente a la reflexión cruzada q_diag = sqrt(2) q0. Clic derecho para exportar.",
            "Intensidad de la reflexión tetragonal (1,1); fundamental para evaluar correlación 2D y simetría de la red."
        ))
        self._setup_plot_export_menu(self.plot_cut_diag, "fig06_corte_espectral_diagonal_45deg", "Perfil Diagonal 45°")

        self.lay_cuts.addWidget(self.plot_cut_x)
        self.lay_cuts.addWidget(self.plot_cut_y)
        self.lay_cuts.addWidget(self.plot_cut_diag)
        right_layout.addLayout(self.lay_cuts)

        # ──────────────────────────────────────────────────────────────────────
        # SECTOR ANALÍTICO Y RELACIONES ENTRE PICOS (RESULTADOS PRELIMINARES)
        # ──────────────────────────────────────────────────────────────────────
        sep_frame = QFrame()
        sep_frame.setFrameShape(QFrame.Shape.HLine)
        sep_frame.setFrameShadow(QFrame.Shadow.Sunken)
        sep_frame.setStyleSheet("color: #45475a; margin-top: 10px; margin-bottom: 6px;")
        right_layout.addWidget(sep_frame)

        # Encabezado con título e indicación metrológica
        h_ana_hdr = QHBoxLayout()
        lbl_ana_title = QLabel("🔬 Metrología Analítica Directa de Fourier (Resultados Preliminares)")
        lbl_ana_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #89dceb;")
        lbl_ana_title.setToolTip(make_tooltip(
            "Metrología Analítica Directa de Fourier",
            "Fórmulas exactas de inversión directa que deducen el desorden instantáneamente a partir de los picos armónicos sin simulaciones previas.",
            "Relaciones matemáticas derivadas del factor de estructura Debye-Waller acoplado S(q) para reflexiones fundamentales, cruzadas y armónicas."
        ))
        h_ana_hdr.addWidget(lbl_ana_title)
        h_ana_hdr.addStretch()

        self.chk_anchor_wilson_h0 = QCheckBox("Anclar Wilson a ln(H₀)")
        self.chk_anchor_wilson_h0.setChecked(False)
        self.chk_anchor_wilson_h0.setStyleSheet("font-size: 11px; color: #fab387; font-weight: bold; margin-right: 12px;")
        self.chk_anchor_wilson_h0.setToolTip(make_tooltip(
            "Anclar Intercepto de Wilson a ln(H₀)",
            "Fija c_x = c_y = ln(H₀) en la regresión lineal del Gráfico de Wilson (ajuste forzado a través del origen q=0).",
            "Fórmula de 1 parámetro: m = Σ G_i² (ln(H_i) - ln(H₀)) / Σ G_i⁴. Útil para redes ideales o fondo difuso sustraído. Si H₀ contiene autofluorescencia o fondo DC, introducirá sesgo en σ."
        ))
        self.chk_anchor_wilson_h0.toggled.connect(self._on_anchor_wilson_toggled)
        h_ana_hdr.addWidget(self.chk_anchor_wilson_h0)

        btn_go_mc = QPushButton("Comparar con Monte Carlo ➔")
        btn_go_mc.setObjectName("accentBtn")
        btn_go_mc.setToolTip(make_tooltip(
            "Comparar con Simulación Monte Carlo",
            "Transfiere estos parámetros a la Pestaña 3 para ejecutar la simulación estocástica definitiva con bandas de error.",
            "Navega a la Pestaña 3 cargando los hiperparámetros de red calculados para la validación numérica rigurosa."
        ))
        btn_go_mc.clicked.connect(self._on_propagate_to_mc)
        h_ana_hdr.addWidget(btn_go_mc)
        right_layout.addLayout(h_ana_hdr)

        # Banner de advertencia sobre jerarquía metrológica
        lbl_badge_note = QLabel(
            "ℹ️ <b>Estimaciones Analíticas Instantáneas:</b> Calculadas al vuelo a partir de las alturas de los picos armónicos de Fourier. "
            "La <b>Simulación Monte Carlo (Pestaña 3)</b> sigue siendo la referencia definitiva y de mayor rigor experimental para publicaciones."
        )
        lbl_badge_note.setStyleSheet(
            "background-color: #1e1e2e; border: 1px solid #45475a; border-left: 4px solid #89b4fa; "
            "border-radius: 4px; padding: 6px 10px; font-size: 11px; color: #bac2de;"
        )
        lbl_badge_note.setWordWrap(True)
        lbl_badge_note.setToolTip(make_tooltip(
            "Jerarquía Metrológica de Métodos",
            "Las relaciones analíticas proporcionan estimaciones inmediatas, mientras que Monte Carlo modela fluctuaciones estocásticas exactas de tamaño finito.",
            "Las soluciones cerradas asumen red infinita o fondo difuso plano; Monte Carlo calibra el acoplamiento real N, vacancias y atenuación experimental."
        ))
        right_layout.addWidget(lbl_badge_note)

        # Tarjetas de Resultados Numéricos Preliminares
        grp_ana_cards = QGroupBox("Relaciones Analíticas Directas entre Picos de Bragg")
        grp_ana_cards.setStyleSheet("QGroupBox { font-weight: bold; color: #a6e3a1; }")
        grp_ana_cards.setToolTip(make_tooltip(
            "Relaciones Analíticas Directas entre Picos de Bragg",
            "Estimaciones cuantitativas del desorden obtenidas al evaluar razones de altura entre diferentes reflexiones espectrales.",
            "Inversiones analíticas que cancelan variables de confusión (N, vacancias p y fondo continuo) mediante cocientes de armónicos."
        ))
        lay_cards_grid = QGridLayout(grp_ana_cards)
        lay_cards_grid.setSpacing(10)

        # Card 1: H2 / H1 (Estándar de Oro)
        self.lbl_card_h2h1 = QLabel(
            "<b>σ (H₂ / H₁): - nm</b><br>"
            "<span style='color: #a6adc8; font-size: 10px;'>"
            "Estándar de Oro (Cancela p y N)<br>"
            "H₁x, H₁y, H₂x/H₁x, H₂y/H₁y desglosados<br>"
            "Fórmula: σ = (a / 2π√3) √(ln(H₁/H₂))</span>"
        )
        self.lbl_card_h2h1.setStyleSheet(
            "background-color: #181825; border: 1px solid #a6e3a1; border-radius: 6px; padding: 8px; font-family: monospace;"
        )
        self.lbl_card_h2h1.setToolTip(make_tooltip(
            "Razón H₂ / H₁ (Estándar de Oro de Inversión Analítica)",
            "La forma más pura y robusta de estimar el desorden sin calibración: el cociente entre el segundo armónico y el fundamental cancela totalmente las vacancias y el tamaño de muestra.",
            "Fórmula cerrada: σ = (a / 2π√3) √(ln(H₁/H₂)) evaluada independientemente para los ejes X e Y."
        ))
        lay_cards_grid.addWidget(self.lbl_card_h2h1, 0, 0)

        # Card 2: H_diag / H1 (Coherencia 2D)
        self.lbl_card_diag = QLabel(
            "<b>σ (H_diag / H₁): - nm</b><br>"
            "<span style='color: #a6adc8; font-size: 10px;'>"
            "Coherencia 2D (Orden cruzado (1,1))<br>"
            "H_diag/H₁x y H_diag/H₁y desglosados<br>"
            "Fórmula: σ = (a / 2π) √(ln(H₁/H_diag))</span>"
        )
        self.lbl_card_diag.setStyleSheet(
            "background-color: #181825; border: 1px solid #cba6f7; border-radius: 6px; padding: 8px; font-family: monospace;"
        )
        self.lbl_card_diag.setToolTip(make_tooltip(
            "Razón Diagonal H_diag / H₁ (Coherencia 2D en X e Y)",
            "Estima el desorden a partir del orden cruzado (1,1) a 45° respecto a H₁x y H₁y para validar simetría y correlación bidimensional.",
            "Fórmulas cerradas: σ_diag,x = (a_x / 2π) √(ln(H₁x/H_diag)) y σ_diag,y = (a_y / 2π) √(ln(H₁y/H_diag))."
        ))
        lay_cards_grid.addWidget(self.lbl_card_diag, 0, 1)

        # Card 3: H0 / H1 (Inestable)
        self.lbl_card_h1h0 = QLabel(
            "<b>σ (H₀ / H₁): - nm</b> <span style='color: #f38ba8; font-size: 10px;'>[⚠️ INESTABLE]</span><br>"
            "<span style='color: #a6adc8; font-size: 10px;'>"
            "Razón H₀/H₁x y H₀/H₁y frente a DC Central<br>"
            "Sensible a autofluorescencia, haz directo y N</span>"
        )
        self.lbl_card_h1h0.setStyleSheet(
            "background-color: #181825; border: 1px solid #f38ba8; border-radius: 6px; padding: 8px; font-family: monospace;"
        )
        self.lbl_card_h1h0.setToolTip(make_tooltip(
            "Razón H₀ / H₁ (Inestable frente al Centro DC)",
            "ADVERTENCIA METROLÓGICA: Muy inestable. Comparar el pico fundamental con el centro q=0 es vulnerable al haz directo y a la autofluorescencia.",
            "Fórmulas: σ_x = (a_x / 2π) √(ln(H₀/H₁x)) y σ_y = (a_y / 2π) √(ln(H₀/H₁y)). Sufre por la acumulación de fondo difuso en q=0."
        ))
        lay_cards_grid.addWidget(self.lbl_card_h1h0, 0, 2)

        # Card 4: Gráfico de Wilson
        self.lbl_card_wilson = QLabel(
            "<b>Wilson Plot (X / Y): - nm</b><br>"
            "<span style='color: #a6adc8; font-size: 10px;'>"
            "Regresiones independientes en X e Y<br>"
            "Pendientes m_x, m_y e Interceptos c_x, c_y</span>"
        )
        self.lbl_card_wilson.setStyleSheet(
            "background-color: #181825; border: 1px solid #89b4fa; border-radius: 6px; padding: 8px; font-family: monospace;"
        )
        self.lbl_card_wilson.setToolTip(make_tooltip(
            "Gráfico de Wilson Anisótropo (Ejes X e Y)",
            "Ajuste lineal independiente por eje cristalográfico: ln(H) vs |G|². Cada dimensión posee su propia pendiente m y su ordenada c.",
            "Pendientes: m = -σ² arroja el desorden direccional σ_x y σ_y. Interceptos: c = ln(I₀,eff) permite contrastar la atenuación de coherencia en el origen frente a H₀."
        ))
        lay_cards_grid.addWidget(self.lbl_card_wilson, 1, 0, 1, 2)

        # Card 5: Diagnóstico Paracristalino
        self.lbl_card_paracrystal = QLabel(
            "<b>Diagnóstico: -</b><br>"
            "<span style='color: #a6adc8; font-size: 10px;'>"
            "Ratio FWHM₂ / FWHM₁ (X e Y) = -<br>"
            "-</span>"
        )
        self.lbl_card_paracrystal.setStyleSheet(
            "background-color: #181825; border: 1px solid #f9e2af; border-radius: 6px; padding: 8px; font-family: monospace;"
        )
        self.lbl_card_paracrystal.setToolTip(make_tooltip(
            "Diagnóstico de Tipo de Desorden (Hosemann en X e Y)",
            "Compara el ancho radial del segundo armónico contra el fundamental en ambos ejes para diferenciar desorden vibracional Tipo I de paracristal Tipo II.",
            "Teoría de Hosemann: Si FWHM₂/FWHM₁ ≈ 1.0, el desorden es Tipo I (Debye-Waller puro). Si crece con el orden m², existe paracristal Tipo II."
        ))
        lay_cards_grid.addWidget(self.lbl_card_paracrystal, 1, 2)

        right_layout.addWidget(grp_ana_cards)

        # Batería de 4 Gráficos de Diagnóstico Analítico (Grid 2x2)
        h_ana_plots_hdr = QHBoxLayout()
        grp_ana_plots = QGroupBox("Batería de Gráficos de Diagnóstico Analítico")
        grp_ana_plots.setStyleSheet("QGroupBox { font-weight: bold; color: #89b4fa; }")
        grp_ana_plots.setToolTip(make_tooltip(
            "Batería de 4 Gráficos Analíticos de Fourier",
            "Inspección gráfica integral de los modelos analíticos: Wilson anisótropo, decaimiento Debye-Waller por eje, estabilidad de razones y ancho radial Hosemann.",
            "Panel 2x2 para evaluar bondad de ajuste lineal, atenuación armónica multiorden y criterios de coherencia reticular."
        ))
        lay_plots_grid = QGridLayout(grp_ana_plots)
        lay_plots_grid.setSpacing(8)

        # Plot 1: Gráfico de Wilson
        self.plot_wilson = pg.PlotWidget(title="1. Gráfico de Wilson Anisótropo (ln(H) vs |G|²)")
        self.plot_wilson.showGrid(x=True, y=True, alpha=0.3)
        self.plot_wilson.setLabel('bottom', '|G|²', units='rad²/nm²')
        self.plot_wilson.setLabel('left', 'ln(H)')
        self.plot_wilson.setMinimumHeight(240)
        self.plot_wilson.setToolTip(make_tooltip(
            "1. Gráfico de Wilson Anisótropo (ln(H) vs |G|²)",
            "Regresiones lineales separadas para los ejes X e Y, contrastando pendientes m e interceptos c. Clic derecho para exportar.",
            "Permite diagnosticar anisotropía posicional a partir de m_x y m_y, y evaluar coherencia frente al haz directo a partir de los interceptos."
        ))
        self._setup_plot_export_menu(self.plot_wilson, "fig07_grafico_wilson_linear_fit", "Gráfico de Wilson")
        lay_plots_grid.addWidget(self.plot_wilson, 0, 0)

        # Plot 2: Decaimiento Multiórden Debye-Waller
        self.plot_dw_decay = pg.PlotWidget(title="2. Decaimiento Debye-Waller: H(q)/H₁ (Ejes X e Y)")
        self.plot_dw_decay.showGrid(x=True, y=True, alpha=0.3)
        self.plot_dw_decay.setLabel('bottom', 'q / q₀', units='orden')
        self.plot_dw_decay.setLabel('left', 'H / H₁ (Normalizado)')
        self.plot_dw_decay.setMinimumHeight(240)
        self.plot_dw_decay.setToolTip(make_tooltip(
            "2. Decaimiento Debye-Waller: H(q)/H₁ (Ejes X e Y)",
            "Atenuación armónica teórica y experimental desglosada por dirección cristalina. Clic derecho para exportar.",
            "Contrasta curvas de atenuación para el eje X, eje Y y diagonal (1,1) con leyendas descriptivas."
        ))
        self._setup_plot_export_menu(self.plot_dw_decay, "fig08_decaimiento_debye_waller_multi_orden", "Decaimiento Debye-Waller Multi-Orden")
        lay_plots_grid.addWidget(self.plot_dw_decay, 0, 1)

        # Plot 3: Comparativa de Estabilidad de Ratios
        self.plot_ratio_stability = pg.PlotWidget(title="3. Comparativa de Estabilidad: Métodos Analíticos de σ")
        self.plot_ratio_stability.showGrid(x=True, y=True, alpha=0.3)
        self.plot_ratio_stability.setLabel('bottom', 'Método Analítico')
        self.plot_ratio_stability.setLabel('left', 'σ estimado', units='nm')
        self.plot_ratio_stability.setMinimumHeight(240)
        self.plot_ratio_stability.setToolTip(make_tooltip(
            "3. Comparativa de Estabilidad de Métodos Analíticos de σ",
            "Gráfico comparativo que contrasta los valores de desorden inferidos por H₂/H₁, Diag, Wilson y H₀/H₁ para ambos ejes X e Y.",
            "Visualiza la concordancia o divergencia metrológica entre estimaciones de desorden para identificar efectos de fondo espurio o anisotropía."
        ))
        self._setup_plot_export_menu(self.plot_ratio_stability, "fig09_comparativa_estabilidad_ratios", "Comparativa de Estabilidad de Ratios")
        lay_plots_grid.addWidget(self.plot_ratio_stability, 1, 0)

        # Plot 4: Diagnóstico de Ancho Radial (Tipo I vs Tipo II)
        self.plot_fwhm_paracrystal = pg.PlotWidget(title="4. Diagnóstico Paracristalino: FWHM vs Orden (Ejes X e Y)")
        self.plot_fwhm_paracrystal.showGrid(x=True, y=True, alpha=0.3)
        self.plot_fwhm_paracrystal.setLabel('bottom', 'Orden Cristalográfico m')
        self.plot_fwhm_paracrystal.setLabel('left', 'FWHM Radial', units='nm^-1')
        self.plot_fwhm_paracrystal.setMinimumHeight(240)
        self.plot_fwhm_paracrystal.setToolTip(make_tooltip(
            "4. Diagnóstico Paracristalino: FWHM vs Orden (Ejes X e Y)",
            "Evolución del ancho a media altura (FWHM) para los ejes X e Y frente a modelos Tipo I (constante) y Tipo II (cuadrático Hosemann).",
            "Permite verificar si el ensanchamiento radial es isotrópico o si alguna dirección acumula desorden de espaciado."
        ))
        self._setup_plot_export_menu(self.plot_fwhm_paracrystal, "fig10_diagnostico_paracristal_fwhm_hosemann", "Diagnóstico Paracristal Hosemann")
        lay_plots_grid.addWidget(self.plot_fwhm_paracrystal, 1, 1)

        right_layout.addWidget(grp_ana_plots)

        splitter.addWidget(left_widget)
        splitter.addWidget(self.scroll_reciprocal_right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)

    def _on_profile_view_changed(self, idx: int):
        self.plot_cut_x.setVisible(idx in (0, 1))
        self.plot_cut_y.setVisible(idx in (0, 2))
        self.plot_cut_diag.setVisible(idx in (0, 3))

    # ==========================================================================
    # PESTAÑA 3: MONTE CARLO & DEBYE-WALLER
    # ==========================================================================
    def _build_tab3(self):
        layout = QHBoxLayout(self.tab3)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)

        # --- Panel Izquierdo: Controles Monte Carlo ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.setSpacing(10)

        grp_sim = QGroupBox("Configuración de Simulación")
        grp_sim.setToolTip(make_tooltip(
            "Configuración de Simulación Monte Carlo",
            "Define los parámetros para calibrar numéricamente la atenuación de Debye-Waller en función del desorden.",
            "Genera ensambles estadísticos de redes N x N con desorden gaussiano perturbado e inversión del factor de estructura."
        ))
        lay_sim = QVBoxLayout(grp_sim)

        h1 = QHBoxLayout()
        h1.addWidget(QLabel("Sitios Nominales N:"))
        self.spin_mc_n = QSpinBox()
        self.spin_mc_n.setRange(2, 200)
        self.spin_mc_n.setValue(30)
        self.spin_mc_n.setToolTip(make_tooltip(
            "Tamaño Reticular Lateral (N)",
            "Cantidad de partículas nominales por lado de la red cuadrada (ej. 30 para una red de 30x30 = 900 sitios).",
            "Número de sitios en cada dimensión R_u,v in {0, ..., N-1}². Afecta directamente la finitud del cristal y la relación señal/fondo difuso."
        ))
        h1.addWidget(self.spin_mc_n)
        lay_sim.addLayout(h1)

        self.chk_mc_anisotropy = QCheckBox("Anisotropía Cristalográfica (ax != ay)")
        self.chk_mc_anisotropy.setStyleSheet("color: #fab387; font-weight: bold; font-size: 11px;")
        self.chk_mc_anisotropy.setToolTip(make_tooltip(
            "Anisotropía Cristalográfica (ax != ay)",
            "Active esta casilla si la distancia entre partículas es distinta en el eje horizontal X respecto al eje vertical Y.",
            "Permite modelar una red tetragonal u ortorrómbica con períodos reticulares desacoplados a_x != a_y."
        ))
        lay_sim.addWidget(self.chk_mc_anisotropy)

        h2 = QHBoxLayout()
        h2.addWidget(QLabel("ax (nm):"))
        self.spin_mc_ax = QDoubleSpinBox()
        self.spin_mc_ax.setRange(50.0, 5000.0)
        self.spin_mc_ax.setValue(500.0)
        self.spin_mc_ax.setToolTip(make_tooltip(
            "Período Reticular a_x (nm)",
            "Distancia nominal o experimental entre partículas contiguas a lo largo del eje horizontal X.",
            "Espaciado reticular base en X para la modulación de fase del vector recíproco G = (2π/a_x, 0)."
        ))
        h2.addWidget(self.spin_mc_ax)

        h2.addWidget(QLabel("ay (nm):"))
        self.spin_mc_ay = QDoubleSpinBox()
        self.spin_mc_ay.setRange(50.0, 5000.0)
        self.spin_mc_ay.setValue(500.0)
        self.spin_mc_ay.setEnabled(False)
        self.spin_mc_ay.setToolTip(make_tooltip(
            "Período Reticular a_y (nm)",
            "Distancia entre partículas a lo largo del eje vertical Y (habilitado al activar anisotropía).",
            "Espaciado reticular base en Y para la modulación del vector recíproco G = (0, 2π/a_y)."
        ))
        h2.addWidget(self.spin_mc_ay)
        lay_sim.addLayout(h2)

        # Alias para mantener retrocompatibilidad total
        self.spin_mc_a = self.spin_mc_ax

        def _on_aniso_toggled(checked):
            self.spin_mc_ay.setEnabled(checked)
            if not checked:
                self.spin_mc_ay.setValue(self.spin_mc_ax.value())

        self.chk_mc_anisotropy.toggled.connect(_on_aniso_toggled)

        def _on_ax_changed(val):
            if not self.chk_mc_anisotropy.isChecked():
                self.spin_mc_ay.setValue(val)

        self.spin_mc_ax.valueChanged.connect(_on_ax_changed)

        h3 = QHBoxLayout()
        h3.addWidget(QLabel("Vacancias f_vac (%):"))
        self.spin_mc_vac = QDoubleSpinBox()
        self.spin_mc_vac.setRange(0.0, 95.0)
        self.spin_mc_vac.setValue(0.0)
        self.spin_mc_vac.setToolTip(make_tooltip(
            "Fracción de Vacancias f_vac (%)",
            "Porcentaje de sitios de la red que están desocupados o donde no se imprimió ninguna partícula.",
            "Probabilidad binomial de remoción de emisores p in [0, 1). Modula la intensidad coherente mediante el factor (1 - p)²."
        ))
        h3.addWidget(self.spin_mc_vac)
        lay_sim.addLayout(h3)

        h_band = QHBoxLayout()
        h_band.addWidget(QLabel("Banda Transv. (nm⁻¹):"))
        self.spin_mc_band = QDoubleSpinBox()
        self.spin_mc_band.setRange(0.0, 0.010)
        self.spin_mc_band.setDecimals(5)
        self.spin_mc_band.setSingleStep(0.0001)
        self.spin_mc_band.setValue(0.0002)
        self.spin_mc_band.setToolTip(make_tooltip(
            "Banda Transversal Espectral (nm⁻¹)",
            "Ventana de tolerancia en frecuencia alrededor del vector recíproco para integrar la intensidad del pico de Bragg.",
            "Ancho de banda delta_q para la integración transversal del pico de Bragg respecto al halo difuso."
        ))
        h_band.addWidget(self.spin_mc_band)

        h_band.addWidget(QLabel("Bragg:"))
        self.combo_mc_bragg = QComboBox()
        self.combo_mc_bragg.addItems(["81 pts (Alta Res.)", "121 pts (Ultra Fino)", "31 pts (Rápido)"])
        self.combo_mc_bragg.setToolTip(make_tooltip(
            "Muestreo Espectral de Bragg (Puntos)",
            "Número de puntos calculados alrededor del pico para asegurar una curva de calibración suave y precisa.",
            "Densidad de integración discreta en la vecindad del vector G_0 (81 puntos proporciona equilibrio óptimo velocidad/precisión)."
        ))
        h_band.addWidget(self.combo_mc_bragg)
        lay_sim.addLayout(h_band)

        h4 = QHBoxLayout()
        h4.addWidget(QLabel("Rango σ (nm):"))
        self.spin_mc_smax = QDoubleSpinBox()
        self.spin_mc_smax.setRange(10.0, 300.0)
        self.spin_mc_smax.setValue(60.0)
        self.spin_mc_smax.setToolTip(make_tooltip(
            "Rango Máximo de Desorden σ_max (nm)",
            "Valor más alto de desorden a explorar en la curva de calibración (ej. 60 nm).",
            "Límite superior del espacio de parámetros de simulación [sigma_min, sigma_max] evaluado estocásticamente."
        ))
        h4.addWidget(self.spin_mc_smax)
        lay_sim.addLayout(h4)

        h5 = QHBoxLayout()
        h5.addWidget(QLabel("Puntos σ / Réplicas:"))
        self.spin_mc_steps = QSpinBox()
        self.spin_mc_steps.setRange(5, 50)
        self.spin_mc_steps.setValue(20)
        self.spin_mc_steps.setToolTip(make_tooltip(
            "Puntos de Muestreo de Desorden (N_steps)",
            "Cantidad de escalones de desorden calculados entre 0 y σ_max.",
            "Resolución de interpolación de la curva de calibración Debye-Waller."
        ))
        self.spin_mc_iter = QSpinBox()
        self.spin_mc_iter.setRange(5, 200)
        self.spin_mc_iter.setValue(30)
        self.spin_mc_iter.setToolTip(make_tooltip(
            "Réplicas Estocásticas por Punto",
            "Número de veces que se simula cada valor de desorden para promediar el ruido y obtener barras de error fiables.",
            "Tamaño del ensamble de Monte Carlo por cada nivel de sigma; determina el desvío estándar del error estándar H_std / sqrt(M)."
        ))
        h5.addWidget(self.spin_mc_steps)
        h5.addWidget(self.spin_mc_iter)
        lay_sim.addLayout(h5)

        self.chk_show_multi_order = QCheckBox("Mostrar Jerarquía Multi-Orden (Diagonal y 2do Armónico)")
        self.chk_show_multi_order.setChecked(True)
        self.chk_show_multi_order.setStyleSheet("color: #cba6f7; font-weight: bold; font-size: 11px;")
        self.chk_show_multi_order.setToolTip(make_tooltip(
            "Mostrar Jerarquía Multi-Orden en Gráfico",
            "Dibuja también en el gráfico las curvas para la diagonal (1,1) y el segundo armónico (2,0).",
            "Renderiza las curvas de calibración para reflexiones de orden superior permitiendo la triple inversión Debye-Waller."
        ))
        self.chk_show_multi_order.toggled.connect(self._plot_debye_waller)
        lay_sim.addWidget(self.chk_show_multi_order)

        h_mc_orders = QHBoxLayout()
        self.chk_mc_order1 = QCheckBox("1er Orden (1,0)/(0,1)")
        self.chk_mc_order1.setChecked(True)
        self.chk_mc_order1.setStyleSheet("color: #89b4fa; font-weight: bold; font-size: 10px;")
        self.chk_mc_order1.setToolTip(make_tooltip(
            "Habilitar 1er Orden en Debye-Waller",
            "Muestra la curva y proyecta los picos de primer orden (1,0) y (0,1) sobre la curva Debye-Waller.",
            "Inversión canónica H1 -> sigma_1."
        ))
        self.chk_mc_order1.toggled.connect(self._plot_debye_waller)
        h_mc_orders.addWidget(self.chk_mc_order1)

        self.chk_mc_diag = QCheckBox("Diagonal (1,1)")
        self.chk_mc_diag.setChecked(True)
        self.chk_mc_diag.setStyleSheet("color: #cba6f7; font-weight: bold; font-size: 10px;")
        self.chk_mc_diag.setToolTip(make_tooltip(
            "Habilitar Diagonal (1,1) en Debye-Waller",
            "Muestra la curva y proyecta el pico diagonal de orden cruzado (1,1) sobre la curva Debye-Waller.",
            "Inversión cruzada H_diag -> sigma_diag para coherencia 2D."
        ))
        self.chk_mc_diag.toggled.connect(self._plot_debye_waller)
        h_mc_orders.addWidget(self.chk_mc_diag)

        self.chk_mc_order2 = QCheckBox("2do Orden (2,0)")
        self.chk_mc_order2.setChecked(True)
        self.chk_mc_order2.setStyleSheet("color: #f9e2af; font-weight: bold; font-size: 10px;")
        self.chk_mc_order2.setToolTip(make_tooltip(
            "Habilitar 2do Orden en Debye-Waller",
            "Muestra la curva y proyecta el pico armónico de segundo orden (2,0) sobre la curva Debye-Waller.",
            "Inversión de segundo orden H2 -> sigma_2 para evaluación paracristalina."
        ))
        self.chk_mc_order2.toggled.connect(self._plot_debye_waller)
        h_mc_orders.addWidget(self.chk_mc_order2)
        lay_sim.addLayout(h_mc_orders)

        h_mc_exec = QHBoxLayout()
        self.btn_sync_curated_mc = QPushButton("🔄 Actualizar con Puntos Curados")
        self.btn_sync_curated_mc.setToolTip(make_tooltip(
            "Actualizar con Puntos Curados",
            "Sincroniza los parámetros de red y vacancias prácticas de las partículas curadas con Monte Carlo.",
            "Actualiza spin_mc_n, spin_mc_ax, spin_mc_ay y spin_mc_vac con las métricas curadas más recientes."
        ))
        self.btn_sync_curated_mc.clicked.connect(self._on_sync_curated_to_reciprocal)
        h_mc_exec.addWidget(self.btn_sync_curated_mc)

        self.btn_run_mc = QPushButton("🚀 Iniciar Simulación Monte Carlo")
        self.btn_run_mc.setObjectName("masterBtn")
        self.btn_run_mc.setToolTip(make_tooltip(
            "Iniciar Simulación Monte Carlo Asíncrona",
            "Lanza el cálculo en segundo plano sin congelar la ventana. Muestra el progreso en la barra.",
            "Ejecuta MonteCarloWorker en un QThread independiente, invocando funciones C/BLAS vectorizadas de alta velocidad."
        ))
        self.btn_run_mc.clicked.connect(self._on_run_monte_carlo)
        h_mc_exec.addWidget(self.btn_run_mc)
        lay_sim.addLayout(h_mc_exec)

        self.btn_cancel_mc = QPushButton("⏹ Cancelar Simulación")
        self.btn_cancel_mc.setObjectName("dangerBtn")
        self.btn_cancel_mc.setEnabled(False)
        self.btn_cancel_mc.setToolTip(make_tooltip(
            "Cancelar Simulación en Curso",
            "Detiene inmediatamente la simulación si desea cambiar parámetros.",
            "Activa la bandera _is_cancelled del hilo de trabajo liberando recursos de cómputo."
        ))
        self.btn_cancel_mc.clicked.connect(self._on_cancel_monte_carlo)
        lay_sim.addWidget(self.btn_cancel_mc)

        self.progress_mc = QProgressBar()
        self.progress_mc.setValue(0)
        self.progress_mc.setToolTip(make_tooltip(
            "Barra de Progreso de Simulación",
            "Muestra el porcentaje completado de la simulación Monte Carlo.",
            "Indicador porcentual alimentado por la señal progress_signal del QThread."
        ))
        lay_sim.addWidget(self.progress_mc)

        self.lbl_mc_status = QLabel("Listo para simular.")
        self.lbl_mc_status.setStyleSheet("color: #a6adc8; font-size: 11px;")
        self.lbl_mc_status.setToolTip(make_tooltip(
            "Estado de la Simulación",
            "Informa sobre el paso actual de cálculo o si el proceso ha finalizado.",
            "Monitor de telemetría de simulación con estimación de tiempo restante."
        ))
        lay_sim.addWidget(self.lbl_mc_status)

        left_layout.addWidget(grp_sim)

        # Gestión de Curvas Guardadas
        grp_io = QGroupBox("Gestión de Curvas de Calibración")
        grp_io.setToolTip(make_tooltip(
            "Gestión de Curvas de Calibración (.npz)",
            "Guarde o recupere curvas de calibración generadas previamente para ahorrar tiempo de cómputo en muestras del mismo lote.",
            "Persistencia serializada en formato binario comprimido NumPy (.npz) conteniendo matrices de H(sigma) y metadatos de red."
        ))
        lay_io = QVBoxLayout(grp_io)

        btn_save_curve = QPushButton("💾 Guardar Curva de Calibración (.npz)")
        btn_save_curve.setToolTip(make_tooltip(
            "Guardar Curva de Calibración (.npz)",
            "Guarda la curva calculada en el disco para usarla en análisis futuros.",
            "Serializa diccionarios completos de calibración incluyendo vectores sigma, H_mean, H_std y parámetros de red."
        ))
        btn_save_curve.clicked.connect(self._on_save_calibration_curve)
        lay_io.addWidget(btn_save_curve)

        btn_load_curve = QPushButton("📂 Cargar Curva Previa (.npz)")
        btn_load_curve.setToolTip(make_tooltip(
            "Cargar Curva de Calibración (.npz)",
            "Carga una curva guardada con anterioridad para interpolar inmediatamente el desorden.",
            "Carga arreglos .npz y actualiza los gráficos y la tabla metrológica sin necesidad de re-simular."
        ))
        btn_load_curve.clicked.connect(self._on_load_calibration_curve)
        lay_io.addWidget(btn_load_curve)

        left_layout.addWidget(grp_io)

        # Resultados de Desorden
        grp_res = QGroupBox("Desorden Interpolar Debye-Waller")
        grp_res.setToolTip(make_tooltip(
            "Resultados de Desorden Debye-Waller",
            "Valores finales del desorden real en nanómetros y diagnóstico del cristal.",
            "Inversión experimental obtenida por interpolación cúbica monótona sobre la curva H_exp(q) con bandas de incertidumbre."
        ))
        lay_res = QVBoxLayout(grp_res)

        self.lbl_mc_results = QLabel(
            "Desorden σ_real,x: - nm\n"
            "Desorden σ_real,y: - nm\n"
            "Desorden Promedio σ_dw: - nm\n"
            "Bondad R^2 Ajuste: -"
        )
        self.lbl_mc_results.setStyleSheet("font-family: monospace; font-size: 11px; color: #fab387;")
        self.lbl_mc_results.setToolTip(make_tooltip(
            "Valores de Triple Inversión Debye-Waller",
            "Desorden inferido en X, Y, Diagonal y 2do Orden, más el diagnóstico físico del cristal.",
            "Inversión simultánea en 3 familias de planos cristalinos y prueba de consistencia de Debye-Waller vs Paracristal."
        ))
        lay_res.addWidget(self.lbl_mc_results)

        btn_go_tab4 = QPushButton("Ver Ficha Metrológica y Exportar ➔")
        btn_go_tab4.setObjectName("accentBtn")
        btn_go_tab4.setToolTip(make_tooltip(
            "Avanzar a Ficha Metrológica y Exportación",
            "Pasa a la pestaña final para revisar la tabla metrológica consolidada y exportar informes.",
            "Conmuta a la pestaña 4 actualizando todas las filas de la tabla de parámetros y habilitando la galería completa."
        ))
        btn_go_tab4.clicked.connect(lambda: self.tabs.setCurrentIndex(3))
        lay_res.addWidget(btn_go_tab4)

        left_layout.addWidget(grp_res)
        left_layout.addStretch()

        # --- Panel Derecho: Gráfico Debye-Waller ---
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(8, 8, 8, 8)
        right_layout.setSpacing(8)

        h_dw_hdr = QHBoxLayout()
        lbl_dw = QLabel("Curva de Atenuación Debye-Waller: H(σ, p) = H0(1-p)^2 exp(-σ^2 / 2σ_char^2) + H_diffuse")
        lbl_dw.setStyleSheet("font-weight: bold; color: #cba6f7;")
        h_dw_hdr.addWidget(lbl_dw)
        h_dw_hdr.addStretch()

        btn_exp_dw = QPushButton("💾 Exportar...")
        btn_exp_dw.setToolTip(make_tooltip(
            "Exportar Curva Debye-Waller",
            "Guarde este gráfico de calibración en alta resolución PNG (600 DPI) o vector SVG para publicaciones.",
            "Exporta la curva de atenuación, bandas de error de réplicas e interpolación experimental."
        ))
        btn_exp_dw.clicked.connect(lambda: self._export_single_plot(self.plot_dw, "fig11_curva_calibracion_debye_waller_mc"))
        h_dw_hdr.addWidget(btn_exp_dw)
        right_layout.addLayout(h_dw_hdr)

        self.plot_dw = pg.PlotWidget()
        self.plot_dw.showGrid(x=True, y=True, alpha=0.3)
        self.plot_dw.setLabel('bottom', 'Desorden Posicional σ', units='nm')
        self.plot_dw.setLabel('left', 'Intensidad Coherente del Pico H')
        self.plot_dw_legend = self.plot_dw.addLegend(offset=(15, 15))
        self.plot_dw_legend.setBrush(pg.mkBrush(24, 24, 37, 200))
        self.plot_dw_legend.setPen(pg.mkPen('#45475a'))
        self.plot_dw.setToolTip(make_tooltip(
            "Curva de Atenuación de Debye-Waller: H(σ, p)",
            "Relación entre el desorden posicional σ y la altura del pico de Bragg. La línea punteada indica el desorden de su muestra. Clic derecho para exportar (PNG 600 DPI / SVG).",
            "Función de calibración H(σ) = H₀(1-p)² exp(-σ² / 2σ_char²) + H_diffuse ajustada a las réplicas estocásticas, con puntos experimentales interpolados."
        ))
        self._setup_plot_export_menu(self.plot_dw, "fig11_curva_calibracion_debye_waller_mc", "Calibración Debye-Waller MC")
        right_layout.addWidget(self.plot_dw)

        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

    # ==========================================================================
    # PESTAÑA 4: FICHA METROLÓGICA & EXPORTACIÓN
    # ==========================================================================
    def _build_tab4(self):
        layout = QVBoxLayout(self.tab4)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        lbl_title = QLabel("Ficha Metrológica Consolidada de la Muestra:")
        lbl_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #cba6f7;")
        lbl_title.setToolTip(make_tooltip(
            "Ficha Metrológica Consolidada",
            "Resumen exhaustivo de todas las mediciones de la muestra tanto en espacio real como recíproco y analítico.",
            "Hoja técnica con trazabilidad metrológica: dimensiones, períodos de red, vacancias, desorden KDTree vs Fourier vs Debye-Waller y diagnóstico cristalográfico."
        ))
        layout.addWidget(lbl_title)

        # Tabla de Métricas con Contraste Optimizado y Tooltips
        self.table_metrics = QTableWidget(18, 2)
        self.table_metrics.setHorizontalHeaderLabels(["Parámetro Metrológico", "Valor Experimental"])
        self.table_metrics.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table_metrics.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table_metrics.setAlternatingRowColors(True)
        self.table_metrics.setStyleSheet(
            "QTableWidget { background-color: #181825; color: #cdd6f4; gridline-color: #313244; font-size: 11px; } "
            "QTableWidget::item { padding: 4px 8px; } "
            "QTableWidget::item:alternate { background-color: #1e1e2e; color: #cdd6f4; } "
            "QTableWidget::item:selected { background-color: #313244; color: #89b4fa; font-weight: bold; } "
            "QHeaderView::section { background-color: #11111b; color: #cba6f7; font-weight: bold; padding: 6px; border: 1px solid #313244; }"
        )
        self.table_metrics.setToolTip(make_tooltip(
            "Tabla Metrológica de Parámetros de Red",
            "Contiene todos los parámetros cuantitativos calculados organizados en 18 filas. Pase el cursor sobre cada fila para ver su fundamento físico y matemático.",
            "Matriz estandarizada de resultados experimentales con propagación de errores e índices de consistencia cruzada."
        ))

        rows_info = [
            ("Archivo de Muestra", "-",
             "Identificador del archivo analizado.",
             "Nombre de la micrografía confocal o tabla de coordenadas fuente."),
            ("Dimensiones Nominales de Red (N x N)", "-",
             "Tamaño lateral del cristal 2D.",
             "Número de partículas por fila y columna. Fija el total de sitios teóricos N²."),
            ("Período Experimental a_x / a_y / a_mean", "-",
             "Espaciado físico entre partículas en nanómetros.",
             "Inversión espectral continua a_i = 1/f_peak,i derivada de la NUFFT 2D."),
            ("Anisotropía de Red (a_x - a_y)", "-",
             "Diferencia de período reticular entre ejes cartesianos.",
             "Δa = a_x - a_y [nm]. Detecta distorsión uniaxial ortorrómbica."),
            ("Fracción de Vacancias f_vac (Prácticas / Teóricas)", "-",
             "Tasa de sitios desocupados en la red.",
             "V_prac = N² - M_grid (canónica) vs V_teor = celdas desocupadas bajo cota r < a/2."),
            ("Desorden Espacio Real (KDTree) σ_x / σ_y", "-",
             "Desviación estándar de los centros respecto a nodos ideales.",
             "Dispersión cartesiana cuadrática media σ_x y σ_y calculada por árbol KDTree."),
            ("Desorden Espacio Real Medio σ_pos", "-",
             "Desorden posicional global en nanómetros.",
             "Varianza euclidiana promedio σ_pos = sqrt((σ_x² + σ_y²)/2)."),
            ("Desorden Radial (g(r)) σ_rdf", "-",
             "Ancho gaussiano de la primera esfera de coordinación.",
             "Desvío estándar del primer pico de la RDF: σ_rdf = FWHM / 2.355 [nm]."),
            ("Desorden Recíproco (Debye-Waller) σ_real,x / σ_real,y", "-",
             "Desorden obtenido por inversión estocástica en Fourier.",
             "Inversión de reflectividad experimental H_exp sobre curva de Monte Carlo."),
            ("Desorden Recíproco Medio σ_dw", "-",
             "Promedio del desorden Debye-Waller en ambos ejes.",
             "σ_dw = (σ_real,x + σ_real,y)/2 para comparación cruzada directa con σ_pos."),
            ("Longitud de Correlación Espectral ξ_x / ξ_y", "-",
             "Distancia de coherencia reticular de fase.",
             "ξ = 2π / FWHM_peak [nm]. Acotada en redes finitas o con defectos."),
            ("Diagnóstico de Deriva (FWHM_x / FWHM_y)", "-",
             "Relación de anchos de Bragg entre ejes ortogonales.",
             "Cociente de FWHM. Si difiere significativamente de 1.0 indica deriva piezoeléctrica o astigmatismo."),
            ("Consistencia Cruzada (Real vs Recíproco)", "-",
             "Discrepancia absoluta Δσ = |σ_pos - σ_dw|.",
             "Criterio de coherencia: Δσ < 5.0 nm confirma acuerdo excelente entre ambos métodos."),
            ("Aglomerados / Filamentos Detectados", "-",
             "Conteo de dímeros, trímeros y cúmulos sobrepuestos.",
             "Partículas con firmas fotométricas V > 1.25 V₀ o distancias d < 0.6 a."),
            ("Jerarquía de Bragg (H_diag/H1, H2/H1, SBR)", "-",
             "Ratios de intensidad de reflexiones de orden superior.",
             "H_diag/H1 (orden cruzado), H2/H1 (armónico 2do) y relación señal/fondo difuso."),
            ("Mosaico Angular Δθ / Cizallamiento γ", "-",
             "Dispersión azimutal de Bragg y deformación angular.",
             "Δθ evalúa rotación de dominios y γ = θ_xy - 90° mide deformación de cizalla."),
            ("Triple Inversión Debye-Waller (σ1 / σ_diag / σ2)", "-",
             "Desorden deducido en tres familias cristalográficas independientes.",
             "Clasifica la red en Tipo I (Debye-Waller puro) o Tipo II (Paracristal acumulativo)."),
            ("Inversión Analítica Directa σ(H₂/H₁) / σ(Wilson)", "-",
             "Desorden estimado instantáneamente por relaciones analíticas directas.",
             "Inversión analítica σ(H₂/H₁) y pendiente lineal en el Wilson plot.")
        ]
        for r, (param, val, tt_basic, tt_exp) in enumerate(rows_info):
            it0 = QTableWidgetItem(param)
            it0.setFlags(Qt.ItemFlag.ItemIsEnabled)
            it0.setToolTip(make_tooltip(param, tt_basic, tt_exp))
            it1 = QTableWidgetItem(val)
            it1.setFlags(Qt.ItemFlag.ItemIsEnabled)
            it1.setToolTip(make_tooltip(f"Valor: {param}", f"Valor medido para {param}.", tt_exp))
            self.table_metrics.setItem(r, 0, it0)
            self.table_metrics.setItem(r, 1, it1)

        layout.addWidget(self.table_metrics, stretch=3)

        # Botones de Exportación
        grp_exp = QGroupBox("Exportación Científica y Reportes de 1-Click")
        grp_exp.setToolTip(make_tooltip(
            "Exportación Científica y Reportes de 1-Click",
            "Exporte datos en tablas CSV, resúmenes en texto plano y la galería completa de gráficos listos para tesis o artículos.",
            "Módulo de exportación con soporte de coordenadas brutas, curvas numéricas y gráficos vectoriales/rasterizados en 600 DPI."
        ))
        lay_exp = QHBoxLayout(grp_exp)

        btn_exp_csv = QPushButton("💾 Exportar Coordenadas (.csv)")
        btn_exp_csv.setToolTip(make_tooltip(
            "Exportar Coordenadas Detectadas (.csv)",
            "Guarda la lista completa de posiciones nanométricas (x, y) de las partículas detectadas en un archivo de texto CSV.",
            "Exporta DataFrame completo con columnas x_nm, y_nm, fotones integrados, bg, elipticidad e incertidumbres."
        ))
        btn_exp_csv.clicked.connect(self._on_export_coordinates_csv)
        lay_exp.addWidget(btn_exp_csv)

        btn_exp_txt = QPushButton("📄 Exportar Resumen Metrológico (.txt)")
        btn_exp_txt.setToolTip(make_tooltip(
            "Exportar Resumen Metrológico (.txt)",
            "Crea un informe en texto con fecha, nombre de archivo y todos los valores medidos para archivar.",
            "Documento de texto plano estructurado con metadatos de instrumentación, notas teóricas y tabla metrológica completa."
        ))
        btn_exp_txt.clicked.connect(self._on_export_report_txt)
        lay_exp.addWidget(btn_exp_txt)

        btn_exp_curve = QPushButton("📊 Exportar Curva Debye-Waller (.csv)")
        btn_exp_curve.setToolTip(make_tooltip(
            "Exportar Curva Debye-Waller (.csv)",
            "Guarda los datos de la curva de simulación (desorden vs altura de pico y barras de error) en formato CSV.",
            "Exporta sigma_nm, H_mean y H_std calculados en Monte Carlo para graficar en software externo (Origin, Python, MATLAB)."
        ))
        btn_exp_curve.clicked.connect(self._on_export_dw_curve_csv)
        lay_exp.addWidget(btn_exp_curve)

        btn_exp_gallery = QPushButton("🖼 Exportar Galería de Figuras (SVG / PNG)")
        btn_exp_gallery.setObjectName("primaryBtn")
        btn_exp_gallery.setToolTip(make_tooltip(
            "Exportar Galería Completa de Figuras (SVG / PNG 600 DPI)",
            "Exporta de 1 solo clic los 11 gráficos del software en alta resolución (2400 px, 600 DPI) y vectores SVG a una carpeta.",
            "Generación en lote de las 11 figuras científicas del análisis en formatos listos para publicación editorial (PNG de 600 DPI y SVG escalable)."
        ))
        btn_exp_gallery.clicked.connect(self._on_export_gallery)
        lay_exp.addWidget(btn_exp_gallery)

        layout.addWidget(grp_exp)

    # ==========================================================================
    # SLOTS Y LÓGICA DE NEGOCIO
    # ==========================================================================

    def _on_preset_changed(self, idx: int):
        preset_name = self.combo_presets.currentText()
        if preset_name not in PRESETS_DICT:
            return
        p = PRESETS_DICT[preset_name]

        self._updating_roi_internally = True
        try:
            self.spin_scale.setValue(float(p.get("scale_nm", 50.0)))
            self.spin_n_side.setValue(int(p.get("n_side", 30)))
            self.spin_a_nominal.setValue(float(p.get("a_nominal", 500.0)))

            self.chk_invert_img.setChecked(bool(p.get("invert", False)))
            self.chk_roi_enable.setChecked(bool(p.get("roi_enabled", True)))

            self.spin_roi_xmin.setValue(float(p.get("roi_xmin", 15.0)))
            self.spin_roi_xmax.setValue(float(p.get("roi_xmax", 315.0)))
            self.spin_roi_ymin.setValue(float(p.get("roi_ymin", 15.0)))
            self.spin_roi_ymax.setValue(float(p.get("roi_ymax", 318.0)))

            self.combo_motor.setCurrentIndex(int(p.get("motor", 0)))

            # Parámetros Picasso
            self.spin_net_grad.setValue(float(p.get("picasso_grad", 300.0)))
            self.spin_box_size.setValue(int(p.get("picasso_box", 7)))
            method_str = p.get("picasso_method", "gausslq")
            self.combo_picasso_method.setCurrentIndex(0 if method_str == "gausslq" else 1)
            self.chk_box_offset.setChecked(bool(p.get("picasso_box_offset", True)))
            self.chk_picasso_autoscale.setChecked(bool(p.get("picasso_autoscale", True)))
            self.spin_picasso_baseline.setValue(int(p.get("picasso_baseline", 100)))
            self.spin_picasso_gain.setValue(float(p.get("picasso_gain", 1.0)))
            self.spin_picasso_sens.setValue(float(p.get("picasso_sensitivity", 1.0)))

            # Parámetros Trackpy
            self.spin_diameter.setValue(int(p.get("tp_diameter", 5)))
            self.spin_minmass.setValue(float(p.get("tp_minmass", 0.05)))
            self.spin_separation.setValue(float(p.get("tp_separation", 7.0)))
            self.spin_percentile.setValue(int(p.get("tp_percentile", 64)))
            self.spin_noise_size.setValue(float(p.get("tp_noise_size", 1.0)))
            self.chk_rl.setChecked(bool(p.get("tp_rl", False)))
            self.spin_rl_iter.setValue(int(p.get("tp_rl_iter", 15)))
            self.spin_rl_sigma.setValue(float(p.get("tp_rl_sigma", 1.5)))

            # Sincronizar reglas en nm
            scale_nm = self.spin_scale.value()
            self.line_roi_xmin.setValue(self.spin_roi_xmin.value() * scale_nm)
            self.line_roi_xmax.setValue(self.spin_roi_xmax.value() * scale_nm)
            self.line_roi_ymin.setValue(self.spin_roi_ymin.value() * scale_nm)
            self.line_roi_ymax.setValue(self.spin_roi_ymax.value() * scale_nm)
        finally:
            self._updating_roi_internally = False

    def _on_save_custom_preset_json(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Guardar Preset de Operación",
            "preset_red_confocal.json",
            "Archivos JSON (*.json);;Todos (*.*)"
        )
        if not file_path:
            return

        data = {
            "preset_name": "Custom",
            "scale_nm": self.spin_scale.value(),
            "n_side": self.spin_n_side.value(),
            "a_nominal": self.spin_a_nominal.value(),
            "invert": self.chk_invert_img.isChecked(),
            "roi_enabled": self.chk_roi_enable.isChecked(),
            "roi_xmin": self.spin_roi_xmin.value(),
            "roi_xmax": self.spin_roi_xmax.value(),
            "roi_ymin": self.spin_roi_ymin.value(),
            "roi_ymax": self.spin_roi_ymax.value(),
            "motor": self.combo_motor.currentIndex(),
            "picasso_grad": self.spin_net_grad.value(),
            "picasso_box": self.spin_box_size.value(),
            "picasso_method": "gausslq" if self.combo_picasso_method.currentIndex() == 0 else "gaussmle",
            "picasso_box_offset": self.chk_box_offset.isChecked(),
            "picasso_autoscale": self.chk_picasso_autoscale.isChecked(),
            "picasso_baseline": self.spin_picasso_baseline.value(),
            "picasso_gain": self.spin_picasso_gain.value(),
            "picasso_sensitivity": self.spin_picasso_sens.value(),
            "tp_diameter": self.spin_diameter.value(),
            "tp_minmass": self.spin_minmass.value(),
            "tp_separation": self.spin_separation.value(),
            "tp_percentile": self.spin_percentile.value(),
            "tp_noise_size": self.spin_noise_size.value(),
            "tp_rl": self.chk_rl.isChecked(),
            "tp_rl_iter": self.spin_rl_iter.value(),
            "tp_rl_sigma": self.spin_rl_sigma.value()
        }
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
            QMessageBox.information(self, "Preset Guardado", f"Preset guardado con éxito en:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error al Guardar Preset", str(e))

    def _on_load_custom_preset_json(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Cargar Preset de Operación",
            "",
            "Archivos JSON (*.json);;Todos (*.*)"
        )
        if not file_path:
            return

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self._updating_roi_internally = True
            try:
                if "scale_nm" in data: self.spin_scale.setValue(float(data["scale_nm"]))
                if "n_side" in data: self.spin_n_side.setValue(int(data["n_side"]))
                if "a_nominal" in data: self.spin_a_nominal.setValue(float(data["a_nominal"]))
                if "invert" in data: self.chk_invert_img.setChecked(bool(data["invert"]))
                if "roi_enabled" in data: self.chk_roi_enable.setChecked(bool(data["roi_enabled"]))
                if "roi_xmin" in data: self.spin_roi_xmin.setValue(float(data["roi_xmin"]))
                if "roi_xmax" in data: self.spin_roi_xmax.setValue(float(data["roi_xmax"]))
                if "roi_ymin" in data: self.spin_roi_ymin.setValue(float(data["roi_ymin"]))
                if "roi_ymax" in data: self.spin_roi_ymax.setValue(float(data["roi_ymax"]))
                if "motor" in data: self.combo_motor.setCurrentIndex(int(data["motor"]))

                if "picasso_grad" in data: self.spin_net_grad.setValue(float(data["picasso_grad"]))
                if "picasso_box" in data: self.spin_box_size.setValue(int(data["picasso_box"]))
                if "picasso_method" in data:
                    self.combo_picasso_method.setCurrentIndex(0 if data["picasso_method"] == "gausslq" else 1)
                if "picasso_box_offset" in data: self.chk_box_offset.setChecked(bool(data["picasso_box_offset"]))
                if "picasso_autoscale" in data: self.chk_picasso_autoscale.setChecked(bool(data["picasso_autoscale"]))
                if "picasso_baseline" in data: self.spin_picasso_baseline.setValue(int(data["picasso_baseline"]))
                if "picasso_gain" in data: self.spin_picasso_gain.setValue(float(data["picasso_gain"]))
                if "picasso_sensitivity" in data: self.spin_picasso_sens.setValue(float(data["picasso_sensitivity"]))

                if "tp_diameter" in data: self.spin_diameter.setValue(int(data["tp_diameter"]))
                if "tp_minmass" in data: self.spin_minmass.setValue(float(data["tp_minmass"]))
                if "tp_separation" in data: self.spin_separation.setValue(float(data["tp_separation"]))
                if "tp_percentile" in data: self.spin_percentile.setValue(int(data["tp_percentile"]))
                if "tp_noise_size" in data: self.spin_noise_size.setValue(float(data["tp_noise_size"]))
                if "tp_rl" in data: self.chk_rl.setChecked(bool(data["tp_rl"]))
                if "tp_rl_iter" in data: self.spin_rl_iter.setValue(int(data["tp_rl_iter"]))
                if "tp_rl_sigma" in data: self.spin_rl_sigma.setValue(float(data["tp_rl_sigma"]))

                scale_nm = self.spin_scale.value()
                self.line_roi_xmin.setValue(self.spin_roi_xmin.value() * scale_nm)
                self.line_roi_xmax.setValue(self.spin_roi_xmax.value() * scale_nm)
                self.line_roi_ymin.setValue(self.spin_roi_ymin.value() * scale_nm)
                self.line_roi_ymax.setValue(self.spin_roi_ymax.value() * scale_nm)
            finally:
                self._updating_roi_internally = False

            QMessageBox.information(self, "Preset Cargado", f"Preset '{os.path.basename(file_path)}' cargado con éxito.")
        except Exception as e:
            QMessageBox.critical(self, "Error al Cargar Preset", str(e))

    def _on_scale_changed(self, val: float):
        self._on_roi_spin_changed()

    def _on_invert_toggled(self, checked: bool):
        if self.raw_image_2d is None:
            return
        if checked:
            i_min = float(np.min(self.raw_image_2d))
            i_max = float(np.max(self.raw_image_2d))
            self.image_2d = (i_max + i_min) - self.raw_image_2d
        else:
            self.image_2d = self.raw_image_2d.copy()
        self._update_real_space_analysis()

    def _on_roi_enable_toggled(self, checked: bool):
        if hasattr(self, 'chk_layer_roi'):
            self.chk_layer_roi.blockSignals(True)
            self.chk_layer_roi.setChecked(checked)
            self.chk_layer_roi.blockSignals(False)
        for line in [self.line_roi_xmin, self.line_roi_xmax, self.line_roi_ymin, self.line_roi_ymax]:
            line.setVisible(checked)

    def _on_layer_roi_toggled(self, checked: bool):
        self.chk_roi_enable.blockSignals(True)
        self.chk_roi_enable.setChecked(checked)
        self.chk_roi_enable.blockSignals(False)
        for line in [self.line_roi_xmin, self.line_roi_xmax, self.line_roi_ymin, self.line_roi_ymax]:
            line.setVisible(checked)

    def _on_colormap_changed(self, cmap_name: str):
        cm = get_pyqtgraph_colormap(cmap_name)
        if self.img_item is not None:
            try:
                self.img_item.setColorMap(cm)
            except Exception as e:
                print(f"Error actualizando colormap TIFF: {e}")
        if self.img_item_filtered is not None:
            try:
                self.img_item_filtered.setColorMap(cm)
            except Exception as e:
                print(f"Error actualizando colormap Filtro Fondo: {e}")
        if self.img_item_rl is not None:
            try:
                self.img_item_rl.setColorMap(cm)
            except Exception as e:
                print(f"Error actualizando colormap RL: {e}")

    def _on_layer_visibility_changed(self):
        if self.img_item is not None:
            self.img_item.setVisible(self.chk_layer_img.isChecked())
        if self.img_item_filtered is not None:
            self.img_item_filtered.setVisible(self.chk_layer_filtered.isChecked())
        if self.img_item_rl is not None:
            self.img_item_rl.setVisible(self.chk_layer_rl.isChecked())
        if self.scatter_det is not None:
            self.scatter_det.setVisible(self.chk_layer_det.isChecked())
        if self.scatter_clusters is not None:
            self.scatter_clusters.setVisible(self.chk_layer_clusters.isChecked())
        for line_item in self.cluster_lines_items:
            line_item.setVisible(self.chk_layer_clusters.isChecked())
        if self.scatter_selected is not None:
            self.scatter_selected.setVisible(self.chk_layer_selected.isChecked())
        if self.scatter_vac is not None:
            self.scatter_vac.setVisible(self.chk_layer_vac.isChecked())
        if self.scatter_grid is not None:
            self.scatter_grid.setVisible(self.chk_layer_grid.isChecked())
        for c_item in self.cluster_contour_items:
            c_item.setVisible(self.chk_layer_contours.isChecked())
        if self.highlight_contour_item is not None:
            self.highlight_contour_item.setVisible(self.chk_layer_contours.isChecked())
        if self.suspicious_contour_item is not None:
            self.suspicious_contour_item.setVisible(self.chk_layer_contours.isChecked())

    # --- Métodos de Selección y Curación Manual ---

    def _on_mode_nav(self):
        self.selection_box_roi.setVisible(False)
        self.plot_real_space.getViewBox().setMouseMode(pg.ViewBox.PanMode)

    def _on_mode_click(self):
        self.selection_box_roi.setVisible(False)
        self.plot_real_space.getViewBox().setMouseMode(pg.ViewBox.PanMode)

    def _on_mode_box(self):
        self.selection_box_roi.setVisible(True)
        self._on_box_roi_changed()

    def _on_box_roi_changed(self):
        if not self.btn_mode_box.isChecked() or not self.selection_box_roi.isVisible():
            return
        if self.locs_df is None or self.locs_df.empty:
            return

        rect = self.selection_box_roi.parentBounds()
        rx0, ry0 = rect.left(), rect.top()
        rx1, ry1 = rect.right(), rect.bottom()
        min_x, max_x = min(rx0, rx1), max(rx0, rx1)
        min_y, max_y = min(ry0, ry1), max(ry0, ry1)

        x_nm = self.locs_df['x_nm'].values
        y_nm = self.locs_df['y_nm'].values
        in_box = np.where((x_nm >= min_x) & (x_nm <= max_x) & (y_nm >= min_y) & (y_nm <= max_y))[0]
        self.selected_particle_indices = set(int(i) for i in in_box)
        self._update_selected_status()
        self._redraw_selection_overlay()

    def _on_real_space_clicked(self, event):
        pos = event.scenePos()
        mouse_point = self.plot_real_space.plotItem.vb.mapSceneToView(pos)
        cx, cy = float(mouse_point.x()), float(mouse_point.y())

        # Modo Semillas Visuales Manuales: colocar centro en clic
        if hasattr(self, 'btn_pick_visual_seeds') and self.btn_pick_visual_seeds.isChecked():
            self.manual_visual_seeds_nm.append((cx, cy))
            self._redraw_visual_seeds()
            return

        if not self.btn_mode_click.isChecked():
            return
        if self.locs_df is None or self.locs_df.empty:
            return

        x_nm = self.locs_df['x_nm'].values
        y_nm = self.locs_df['y_nm'].values
        dists = np.hypot(x_nm - cx, y_nm - cy)
        nearest_idx = int(np.argmin(dists))
        search_radius = self.spin_a_nominal.value() * 0.4
        if dists[nearest_idx] <= search_radius:
            if hasattr(self, 'btn_cluster_add_particles') and self.btn_cluster_add_particles.isChecked() and self.selected_cluster_id is not None:
                if self.cluster_results:
                    for c in self.cluster_results.get('clusters', []):
                        if c.get('id') == self.selected_cluster_id:
                            if nearest_idx not in c['indices']:
                                c['indices'].append(nearest_idx)
                            c['n_det'] = len(c['indices'])
                            self.selected_particle_indices.add(nearest_idx)
                            if hasattr(self, 'spin_cluster_n_gaussians'):
                                self.spin_cluster_n_gaussians.setValue(max(2, len(c['indices'])))
                            self._on_cluster_contour_thresh_changed()
                            self._update_selected_status()
                            self._redraw_selection_overlay()
                            return
            if nearest_idx in self.selected_particle_indices:
                self.selected_particle_indices.remove(nearest_idx)
            else:
                self.selected_particle_indices.add(nearest_idx)
            self._update_selected_status()
            self._redraw_selection_overlay()

    def _update_selected_status(self):
        n_sel = len(self.selected_particle_indices)
        self.lbl_selected_status.setText(f"{n_sel} seleccionadas")
        if n_sel > 0:
            self.lbl_selected_status.setStyleSheet("color: #cba6f7; font-weight: bold; font-size: 11px;")
        else:
            self.lbl_selected_status.setStyleSheet("color: #6c7086; font-weight: normal; font-size: 11px;")
        if hasattr(self, '_update_suspicious_spot_inspection'):
            self._update_suspicious_spot_inspection()

    def _redraw_selection_overlay(self):
        if self.scatter_selected is not None:
            self.plot_real_space.removeItem(self.scatter_selected)
            self.scatter_selected = None

        if self.locs_df is None or self.locs_df.empty or not self.selected_particle_indices:
            return

        x_nm = self.locs_df['x_nm'].values
        y_nm = self.locs_df['y_nm'].values
        valid_indices = [i for i in self.selected_particle_indices if i < len(x_nm)]
        if not valid_indices:
            return

        sel_x = x_nm[valid_indices]
        sel_y = y_nm[valid_indices]
        self.scatter_selected = pg.ScatterPlotItem(
            x=sel_x, y=sel_y,
            size=14,
            pen=pg.mkPen('#cba6f7', width=2.5),
            brush=pg.mkBrush(203, 166, 247, 140),
            symbol='star'
        )
        self.scatter_selected.setVisible(self.chk_layer_selected.isChecked())
        self.plot_real_space.addItem(self.scatter_selected)

    def _on_clear_selection(self):
        self.selected_particle_indices.clear()
        if hasattr(self, '_clear_suspicious_contour'):
            self._clear_suspicious_contour()
        self._update_selected_status()
        self._redraw_selection_overlay()

    def _on_delete_selected_particles(self):
        if not self.selected_particle_indices or self.locs_df is None or self.locs_df.empty:
            QMessageBox.warning(self, "Atención", "No hay partículas seleccionadas para eliminar.")
            return

        n_deleted = len(self.selected_particle_indices)
        reply = QMessageBox.question(
            self,
            "Confirmar Eliminación de Partículas",
            f"¿Desea eliminar las {n_deleted} partícula(s) seleccionada(s)?\n\n"
            "Se actualizará el espacio real, la cuadrícula reticular y los cúmulos.\n"
            "(Puede revertir la acción posteriormente con '↺ Deshacer').",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # Guardar historial para Deshacer
        self.curation_history.append(self.locs_df.copy())

        # Descartar partículas seleccionadas
        keep_mask = np.ones(len(self.locs_df), dtype=bool)
        for idx in self.selected_particle_indices:
            if idx < len(keep_mask):
                keep_mask[idx] = False

        self.locs_df = self.locs_df[keep_mask].reset_index(drop=True)
        self.selected_particle_indices.clear()
        self._update_selected_status()
        self._update_real_space_analysis()
        self._on_recalculate_reciprocal()

        QMessageBox.information(
            self,
            "Partículas Eliminadas",
            f"Se eliminaron {n_deleted} partículas espurias.\n"
            f"Quedan {len(self.locs_df)} partículas activas."
        )

    def _on_undo_curation(self):
        if not self.curation_history:
            QMessageBox.information(self, "Historial Vacío", "No hay acciones de curación previas para deshacer.")
            return

        self.locs_df = self.curation_history.pop()
        self.selected_particle_indices.clear()
        self._update_selected_status()
        self._update_real_space_analysis()
        self._on_recalculate_reciprocal()
        QMessageBox.information(self, "Deshacer", f"Se restauró el estado anterior con {len(self.locs_df)} partículas.")

    def _on_revert_curation(self):
        if self.locs_df_raw is None or self.locs_df_raw.empty:
            return

        # Filtrar por ROI si está activo
        if self.chk_roi_enable.isChecked():
            px_xmin = self.spin_roi_xmin.value()
            px_xmax = self.spin_roi_xmax.value()
            px_ymin = self.spin_roi_ymin.value()
            px_ymax = self.spin_roi_ymax.value()
            if px_xmin > px_xmax: px_xmin, px_xmax = px_xmax, px_xmin
            if px_ymin > px_ymax: px_ymin, px_ymax = px_ymax, px_ymin

            self.locs_df = self.locs_df_raw[
                (self.locs_df_raw['x'] >= px_xmin) &
                (self.locs_df_raw['x'] <= px_xmax) &
                (self.locs_df_raw['y'] >= px_ymin) &
                (self.locs_df_raw['y'] <= px_ymax)
            ].reset_index(drop=True)
        else:
            self.locs_df = self.locs_df_raw.copy()

        self.curation_history.clear()
        self.selected_particle_indices.clear()
        self._update_selected_status()
        self._update_real_space_analysis()
        self._on_recalculate_reciprocal()
        QMessageBox.information(self, "Restauración Completa", f"Se restauraron todas las {len(self.locs_df)} partículas originales.")

    def _on_resolve_selected_cluster_gaussian(self):
        if self.locs_df is None or self.locs_df.empty:
            QMessageBox.warning(self, "Atención", "No hay detecciones disponibles.")
            return

        if self.selected_cluster_id is None:
            QMessageBox.information(
                self, "Seleccionar Cúmulo",
                "Por favor, selecciona primero un cúmulo en la tabla o haciendo clic en el visor."
            )
            return

        a_nom = self.spin_a_nominal.value()
        scale_nm = self.spin_scale.value()
        x0 = self.kdtree_results['x0'] if (self.kdtree_results and 'x0' in self.kdtree_results) else 0.0
        y0 = self.kdtree_results['y0'] if (self.kdtree_results and 'y0' in self.kdtree_results) else 0.0
        tol = self.spin_cluster_tolerance.value() if hasattr(self, 'spin_cluster_tolerance') else 20.0

        self.curation_history.append(self.locs_df.copy())

        n_gauss = self.spin_cluster_n_gaussians.value() if hasattr(self, 'spin_cluster_n_gaussians') else None
        init_seeds = self.manual_visual_seeds_nm if len(self.manual_visual_seeds_nm) >= 2 else None

        df_resolved, stats = resolve_clusters_dataframe(
            self.locs_df,
            self.cluster_results,
            action='multi_gaussian',
            a=a_nom,
            x0=x0,
            y0=y0,
            scale_nm=scale_nm,
            target_cluster_id=self.selected_cluster_id,
            image_2d=self.image_2d,
            signature_dict=self.monomer_signature,
            tolerance_pct=tol,
            n_gaussians=n_gauss,
            initial_seeds=init_seeds
        )

        n_rem = stats.get('particles_removed', 0)
        n_add = stats.get('particles_added', 0)
        target_id_done = self.selected_cluster_id
        self.selected_cluster_id = None
        self.locs_df = df_resolved
        self.selected_particle_indices.clear()
        self._on_clear_visual_seeds()
        self._update_selected_status()
        self._update_real_space_analysis()
        self._on_recalculate_reciprocal()

        QMessageBox.information(
            self,
            "Cúmulo Desacoplado (Ajuste Multi-Gaussiano)",
            f"Cúmulo #{target_id_done} resuelto exitosamente:\n"
            f"- Partículas originales descartadas: {n_rem}\n"
            f"- Emisores desacoplados añadidos: {n_add}\n"
            f"Total partículas en muestra: {len(self.locs_df)}."
        )

    def _on_resolve_selected_cluster_nearest(self):
        if self.locs_df is None or self.locs_df.empty:
            QMessageBox.warning(self, "Atención", "No hay detecciones disponibles.")
            return

        if self.selected_cluster_id is None:
            QMessageBox.information(
                self, "Seleccionar Cúmulo",
                "Por favor, selecciona primero un cúmulo en la tabla o haciendo clic en el visor."
            )
            return

        a_nom = self.spin_a_nominal.value()
        scale_nm = self.spin_scale.value()
        x0 = self.kdtree_results['x0'] if (self.kdtree_results and 'x0' in self.kdtree_results) else 0.0
        y0 = self.kdtree_results['y0'] if (self.kdtree_results and 'y0' in self.kdtree_results) else 0.0

        self.curation_history.append(self.locs_df.copy())

        df_resolved, stats = resolve_clusters_dataframe(
            self.locs_df,
            self.cluster_results,
            action='keep_nearest',
            a=a_nom,
            x0=x0,
            y0=y0,
            scale_nm=scale_nm,
            target_cluster_id=self.selected_cluster_id
        )

        n_rem = stats.get('particles_removed', 0)
        target_id_done = self.selected_cluster_id
        self.selected_cluster_id = None
        self.locs_df = df_resolved
        self.selected_particle_indices.clear()
        self._update_selected_status()
        self._update_real_space_analysis()
        self._on_recalculate_reciprocal()

        QMessageBox.information(
            self,
            "Cúmulo Resuelto (Cercano a Red)",
            f"Cúmulo #{target_id_done} resuelto:\n"
            f"- Satélites descartados: {n_rem}\n"
            f"Total partículas conservadas: {len(self.locs_df)}."
        )

    def _on_resolve_selected_cluster_com(self):
        if self.locs_df is None or self.locs_df.empty:
            QMessageBox.warning(self, "Atención", "No hay detecciones disponibles.")
            return

        if self.selected_cluster_id is None:
            QMessageBox.information(
                self, "Seleccionar Cúmulo",
                "Por favor, selecciona primero un cúmulo en la tabla o haciendo clic en el visor."
            )
            return

        a_nom = self.spin_a_nominal.value()
        scale_nm = self.spin_scale.value()
        x0 = self.kdtree_results['x0'] if (self.kdtree_results and 'x0' in self.kdtree_results) else 0.0
        y0 = self.kdtree_results['y0'] if (self.kdtree_results and 'y0' in self.kdtree_results) else 0.0

        self.curation_history.append(self.locs_df.copy())

        df_resolved, stats = resolve_clusters_dataframe(
            self.locs_df,
            self.cluster_results,
            action='merge_com',
            a=a_nom,
            x0=x0,
            y0=y0,
            scale_nm=scale_nm,
            target_cluster_id=self.selected_cluster_id
        )

        target_id_done = self.selected_cluster_id
        self.selected_cluster_id = None
        self.locs_df = df_resolved
        self.selected_particle_indices.clear()
        self._update_selected_status()
        self._update_real_space_analysis()
        self._on_recalculate_reciprocal()

        QMessageBox.information(
            self,
            "Cúmulo Fusionado (Centro de Masa)",
            f"Cúmulo #{target_id_done} fusionado en su Centro de Masa.\n"
            f"Total partículas: {len(self.locs_df)}."
        )

    def _on_resolve_all_clusters_gaussian(self):
        if self.locs_df is None or self.locs_df.empty:
            QMessageBox.warning(self, "Atención", "No hay detecciones disponibles.")
            return

        if not self.cluster_results or self.cluster_results.get('n_clusters', 0) == 0:
            QMessageBox.information(self, "Sin Cúmulos", "No hay aglomerados pendientes para desacoplar.")
            return

        a_nom = self.spin_a_nominal.value()
        scale_nm = self.spin_scale.value()
        x0 = self.kdtree_results['x0'] if (self.kdtree_results and 'x0' in self.kdtree_results) else 0.0
        y0 = self.kdtree_results['y0'] if (self.kdtree_results and 'y0' in self.kdtree_results) else 0.0
        tol = self.spin_cluster_tolerance.value() if hasattr(self, 'spin_cluster_tolerance') else 20.0

        self.curation_history.append(self.locs_df.copy())

        df_resolved, stats = resolve_clusters_dataframe(
            self.locs_df,
            self.cluster_results,
            action='multi_gaussian',
            a=a_nom,
            x0=x0,
            y0=y0,
            scale_nm=scale_nm,
            target_cluster_id=None,
            image_2d=self.image_2d,
            signature_dict=self.monomer_signature,
            tolerance_pct=tol
        )

        self.selected_cluster_id = None
        self.locs_df = df_resolved
        self.selected_particle_indices.clear()
        self._update_selected_status()
        self._update_real_space_analysis()
        self._on_recalculate_reciprocal()

        QMessageBox.information(
            self,
            "Desacople Multi-Gaussiano Masivo",
            f"Se procesaron {stats.get('clusters_resolved', 0)} cúmulos en lote.\n"
            f"- Partículas originales descartadas: {stats.get('particles_removed', 0)}\n"
            f"- Emisores desacoplados añadidos: {stats.get('particles_added', 0)}\n"
            f"Total partículas resultantes: {len(self.locs_df)}."
        )

    def _on_resolve_clusters_nearest(self):
        if self.locs_df is None or self.locs_df.empty:
            QMessageBox.warning(self, "Atención", "No hay detecciones disponibles.")
            return

        if not self.cluster_results or self.cluster_results.get('n_clusters', 0) == 0:
            QMessageBox.information(self, "Sin Aglomerados", "No hay aglomerados detectados para resolver.")
            return

        a_nom = self.spin_a_nominal.value()
        scale_nm = self.spin_scale.value()
        x0 = self.kdtree_results['x0'] if (self.kdtree_results and 'x0' in self.kdtree_results) else 0.0
        y0 = self.kdtree_results['y0'] if (self.kdtree_results and 'y0' in self.kdtree_results) else 0.0

        self.curation_history.append(self.locs_df.copy())

        df_resolved, stats = resolve_clusters_dataframe(
            self.locs_df,
            self.cluster_results,
            action='keep_nearest',
            a=a_nom,
            x0=x0,
            y0=y0,
            scale_nm=scale_nm,
            target_cluster_id=None
        )

        n_removed = stats.get('particles_removed', 0)
        self.selected_cluster_id = None
        self.locs_df = df_resolved
        self.selected_particle_indices.clear()
        self._update_selected_status()
        self._update_real_space_analysis()
        self._on_recalculate_reciprocal()

        QMessageBox.information(
            self,
            "Aglomerados Resueltos (Cercano a Nodo)",
            f"Se procesaron {stats.get('clusters_resolved', 0)} aglomerados.\n"
            f"Se descartaron {n_removed} partículas satélites/espurias.\n"
            f"Partículas conservadas: {len(self.locs_df)}."
        )

    def _on_resolve_clusters_com(self):
        if self.locs_df is None or self.locs_df.empty:
            QMessageBox.warning(self, "Atención", "No hay detecciones disponibles.")
            return

        if not self.cluster_results or self.cluster_results.get('n_clusters', 0) == 0:
            QMessageBox.information(self, "Sin Aglomerados", "No hay aglomerados detectados para fusionar.")
            return

        a_nom = self.spin_a_nominal.value()
        scale_nm = self.spin_scale.value()
        x0 = self.kdtree_results['x0'] if (self.kdtree_results and 'x0' in self.kdtree_results) else 0.0
        y0 = self.kdtree_results['y0'] if (self.kdtree_results and 'y0' in self.kdtree_results) else 0.0

        self.curation_history.append(self.locs_df.copy())

        df_resolved, stats = resolve_clusters_dataframe(
            self.locs_df,
            self.cluster_results,
            action='merge_com',
            a=a_nom,
            x0=x0,
            y0=y0,
            scale_nm=scale_nm,
            target_cluster_id=None
        )

        self.selected_cluster_id = None
        self.locs_df = df_resolved
        self.selected_particle_indices.clear()
        self._update_selected_status()
        self._update_real_space_analysis()
        self._on_recalculate_reciprocal()

        QMessageBox.information(
            self,
            "Aglomerados Fusionados (Centro de Masa)",
            f"Se fusionaron {stats.get('clusters_resolved', 0)} aglomerados en sus centros de masa.\n"
            f"Partículas resultantes: {len(self.locs_df)}."
        )

    def _clear_suspicious_contour(self):
        if self.suspicious_contour_item is not None:
            try:
                self.plot_real_space.removeItem(self.suspicious_contour_item)
            except Exception:
                pass
            self.suspicious_contour_item = None

    def _draw_suspicious_contour(self, poly):
        self._clear_suspicious_contour()
        if poly and len(poly) > 2:
            poly_arr = np.array(poly)
            px = np.append(poly_arr[:, 0], poly_arr[0, 0])
            py = np.append(poly_arr[:, 1], poly_arr[0, 1])
            pen = pg.mkPen(color='#fab387', width=3, style=Qt.PenStyle.SolidLine)
            self.suspicious_contour_item = pg.PlotDataItem(px, py, pen=pen)
            if hasattr(self, 'chk_layer_contours'):
                self.suspicious_contour_item.setVisible(self.chk_layer_contours.isChecked())
            self.plot_real_space.addItem(self.suspicious_contour_item)

    def _update_suspicious_spot_inspection(self):
        if not hasattr(self, 'lbl_suspicious_info') or not hasattr(self, 'btn_resolve_suspicious'):
            return

        if self.locs_df is None or self.locs_df.empty:
            self.lbl_suspicious_info.setText("Sin partículas cargadas.")
            self.btn_resolve_suspicious.setEnabled(False)
            self._clear_suspicious_contour()
            return

        if len(self.selected_particle_indices) != 1:
            if len(self.selected_particle_indices) == 0:
                self.lbl_suspicious_info.setText("Seleccione 1 partícula (clic o tabla) para evaluar contorno y volumen.")
            else:
                self.lbl_suspicious_info.setText(f"{len(self.selected_particle_indices)} seleccionadas. Elija solo 1 para inspección puntual.")
            self.lbl_suspicious_info.setStyleSheet("font-family: monospace; font-size: 10px; color: #a6adc8;")
            self.btn_resolve_suspicious.setEnabled(False)
            self._clear_suspicious_contour()
            self.current_inspected_spot_idx = None
            self.current_spot_info = None
            return

        idx = next(iter(self.selected_particle_indices))
        self.current_inspected_spot_idx = idx

        if idx not in self.locs_df.index:
            self.btn_resolve_suspicious.setEnabled(False)
            self._clear_suspicious_contour()
            return

        row = self.locs_df.loc[idx]
        x_nm = float(row['x_nm'])
        y_nm = float(row['y_nm'])
        scale_nm = self.spin_scale.value()
        a_nom = self.spin_a_nominal.value()
        thr_pct = self.spin_suspicious_thresh.value()

        spot_info = inspect_single_spot_photometry(
            image_2d=self.image_2d,
            x_nm=x_nm,
            y_nm=y_nm,
            signature_dict=self.monomer_signature,
            threshold_pct=thr_pct,
            scale_nm=scale_nm,
            a_nominal=a_nom
        )
        self.current_spot_info = spot_info

        area_px = spot_info['area_px']
        r_v = spot_info['ratio_v']
        r_a = spot_info['ratio_a']
        n_sug = spot_info['n_suggested']

        self.lbl_suspicious_info.setText(
            f"Spot #{idx} en ({x_nm/1000:.2f}, {y_nm/1000:.2f} µm):\n"
            f"Vol/V₀: {r_v:.2f}x | Área/A₀: {r_a:.1f}x ({area_px:.0f} px)\n"
            f"Sugerencia estequiométrica: n = {n_sug} partículas"
        )
        self.lbl_suspicious_info.setStyleSheet("font-family: monospace; font-size: 10px; color: #a6e3a1;")

        if n_sug >= 2:
            self.spin_suspicious_n.setValue(min(max(n_sug, 2), 8))
        self.btn_resolve_suspicious.setEnabled(True)

        self._draw_suspicious_contour(spot_info.get('contour_polygon_nm', []))

    def _on_resolve_suspicious_spot(self):
        if self.current_inspected_spot_idx is None or self.locs_df is None or self.locs_df.empty:
            QMessageBox.warning(self, "Atención", "No hay un punto sospechoso seleccionado.")
            return

        spot_idx = self.current_inspected_spot_idx
        n_fit = self.spin_suspicious_n.value()

        # Guardar en historial para Deshacer
        self.curation_history.append(self.locs_df.copy())
        if len(self.curation_history) > 20:
            self.curation_history.pop(0)

        scale_nm = self.spin_scale.value()
        a_nom = self.spin_a_nominal.value()
        init_seeds = self.manual_visual_seeds_nm if len(self.manual_visual_seeds_nm) >= 2 else None

        df_resolved, stats = resolve_single_spot_multi_gaussian(
            df=self.locs_df,
            spot_index=spot_idx,
            n_particles=n_fit,
            image_2d=self.image_2d,
            signature_dict=self.monomer_signature,
            scale_nm=scale_nm,
            a_nominal=a_nom,
            initial_seeds=init_seeds
        )

        if stats.get('status') == 'ok':
            self.locs_df = df_resolved
            self.selected_particle_indices.clear()
            self._on_clear_visual_seeds()
            self._clear_suspicious_contour()
            self.current_inspected_spot_idx = None
            self.current_spot_info = None

            self._update_selected_status()
            self._update_real_space_analysis()
            self._on_recalculate_reciprocal()

            fitted = stats.get('fitted_emitters', [])
            if fitted:
                avg_x = float(np.mean([f['x_nm'] for f in fitted]))
                avg_y = float(np.mean([f['y_nm'] for f in fitted]))
                span = max(a_nom * 2.5, 1200.0)
                self.plot_real_space.setXRange(avg_x - span, avg_x + span, padding=0.05)
                self.plot_real_space.setYRange(avg_y - span, avg_y + span, padding=0.05)

            QMessageBox.information(
                self,
                "Spot Desacoplado",
                f"El spot #{spot_idx} fue desacoplado exitosamente en {stats['n_fitted']} partículas.\n"
                f"La grilla cristalográfica, cúmulos y vacancias se han actualizado."
            )
        else:
            QMessageBox.warning(self, "Error al Desacoplar", stats.get('msg', 'Error desconocido'))

    def _update_cluster_table(self):
        if self.cluster_results is None:
            self.table_clusters.setRowCount(0)
            self.lbl_cluster_summary.setText("Aglomerados: 0 | Sobrepuestas: 0")
            if hasattr(self, 'lbl_monomer_signature'):
                self.lbl_monomer_signature.setText("Firma Monómero: V₀=- | A₀=- | σ_psf=-")
            return

        res = self.cluster_results
        sig = res.get('signature', self.monomer_signature)
        if sig and hasattr(self, 'lbl_monomer_signature'):
            self.lbl_monomer_signature.setText(
                f"Firma Monómero: V₀={sig.get('V0', 0.0):.1f} | A₀={sig.get('A0', 0.0):.1f} px² | "
                f"σ_psf={sig.get('sigma_psf_px', 0.0):.2f} px ({sig.get('sigma_psf_nm', 0.0):.1f} nm)"
            )

        n_under = res.get('n_under_resolved', 0)
        n_ok = res.get('n_ok_resolved', 0)
        self.lbl_cluster_summary.setText(
            f"Aglomerados: {res.get('n_clusters', 0)} (Dímeros: {res.get('n_dimers', 0)}, "
            f"Trímeros: {res.get('n_trimers', 0)}, Cadenas: {res.get('n_chains', 0)}) | "
            f"Sobrepuestas: {res.get('n_superimposed', 0)} | "
            f"Sub-resueltos: {n_under} | Resueltos: {n_ok}"
        )

        clusters = res.get('clusters', [])
        self.table_clusters.setRowCount(len(clusters))
        for i, cl in enumerate(clusters):
            item_id = QTableWidgetItem(f"#{cl.get('id', i + 1)}")
            item_id.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_type = QTableWidgetItem(str(cl.get('type', 'Aglomerado')))
            item_type.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            n_det = cl.get('n_det', len(cl.get('indices', [])))
            n_est = cl.get('n_est', n_det)
            item_det = QTableWidgetItem(str(n_det))
            item_det.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_est = QTableWidgetItem(str(n_est))
            item_est.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            ratio_v = cl.get('ratio_v', float(cl.get('ratio_photons', 1.0)))
            item_rv = QTableWidgetItem(f"{ratio_v:.2f}x")
            item_rv.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            ratio_a = cl.get('ratio_a', 1.0)
            item_ra = QTableWidgetItem(f"{ratio_a:.1f}x")
            item_ra.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            status = cl.get('status', 'OK')
            if status == 'UNDER_RESOLVED':
                status_str = "⚠️ Desacoplar"
                color_str = "#fab387"
            elif status == 'OVER_DETECTED':
                status_str = "🔍 Satélites"
                color_str = "#89dceb"
            else:
                status_str = "✓ OK"
                color_str = "#a6e3a1"

            item_status = QTableWidgetItem(status_str)
            item_status.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_status.setForeground(pg.mkColor(color_str))

            self.table_clusters.setItem(i, 0, item_id)
            self.table_clusters.setItem(i, 1, item_type)
            self.table_clusters.setItem(i, 2, item_det)
            self.table_clusters.setItem(i, 3, item_est)
            self.table_clusters.setItem(i, 4, item_rv)
            self.table_clusters.setItem(i, 5, item_ra)
            self.table_clusters.setItem(i, 6, item_status)

    def _populate_cluster_table(self, results=None):
        """Alias para _update_cluster_table para compatibilidad robusta."""
        self._update_cluster_table()

    def _on_cluster_table_clicked(self, row: int, col: int):
        if self.cluster_results is None or 'clusters' not in self.cluster_results:
            return
        clusters = self.cluster_results['clusters']
        if row < 0 or row >= len(clusters):
            return

        target_cluster = clusters[row]
        self.selected_cluster_id = target_cluster.get('id')
        indices = target_cluster['indices']
        self.selected_particle_indices = set(int(i) for i in indices)
        self._update_selected_status()
        self._redraw_selection_overlay()

        # Actualizar selector n de componentes gaussianas
        if hasattr(self, 'spin_cluster_n_gaussians'):
            n_comp = int(target_cluster.get('n_est', max(2, len(indices))))
            self.spin_cluster_n_gaussians.blockSignals(True)
            self.spin_cluster_n_gaussians.setValue(n_comp)
            self.spin_cluster_n_gaussians.blockSignals(False)

        # Resaltar contorno fotométrico seleccionado
        if self.highlight_contour_item is not None:
            self.plot_real_space.removeItem(self.highlight_contour_item)
            self.highlight_contour_item = None

        poly = target_cluster.get('contour_polygon_nm', [])
        if len(poly) > 2:
            poly_arr = np.array(poly)
            poly_closed = np.vstack([poly_arr, poly_arr[0]])
            self.highlight_contour_item = pg.PlotDataItem(
                poly_closed[:, 0], poly_closed[:, 1],
                pen=pg.mkPen('#f9e2af', width=3.0)
            )
            self.highlight_contour_item.setVisible(self.chk_layer_contours.isChecked())
            self.plot_real_space.addItem(self.highlight_contour_item)

        # Centrar la vista en el aglomerado
        com_x = target_cluster.get('com_x', target_cluster.get('center_x', 0.0))
        com_y = target_cluster.get('com_y', target_cluster.get('center_y', 0.0))
        span = self.spin_a_nominal.value() * 3.0
        self.plot_real_space.setXRange(com_x - span, com_x + span, padding=0.1)
        self.plot_real_space.setYRange(com_y - span, com_y + span, padding=0.1)

    def _on_create_manual_cluster(self):
        if self.locs_df is None or self.locs_df.empty:
            QMessageBox.warning(self, "Atención", "No hay partículas detectadas disponibles.")
            return

        if len(self.selected_particle_indices) < 2:
            QMessageBox.warning(
                self, "Selección Insuficiente",
                "Por favor, seleccione al menos 2 partículas en el visor o tabla para agruparlas en un cúmulo manual."
            )
            return

        scale_nm = self.spin_scale.value() if hasattr(self, 'spin_scale') else 50.0
        a_nom = self.spin_a_nominal.value() if hasattr(self, 'spin_a_nominal') else 500.0
        tol = self.spin_cluster_tolerance.value() if hasattr(self, 'spin_cluster_tolerance') else 20.0

        if self.cluster_results is None:
            self.cluster_results = {
                'clusters': [],
                'n_clusters': 0,
                'pair_lines': [],
                'cluster_particle_indices': set()
            }

        clusters = self.cluster_results.setdefault('clusters', [])
        next_id = max([c.get('id', c.get('cluster_id', 0)) for c in clusters], default=0) + 1

        new_c = create_manual_cluster(
            locs_df=self.locs_df,
            particle_indices=list(self.selected_particle_indices),
            image_2d=self.image_2d,
            scale_nm=scale_nm,
            a_nominal=a_nom,
            signature_dict=self.monomer_signature,
            tolerance_pct=tol,
            cluster_id=next_id
        )

        clusters.append(new_c)
        self.cluster_results['n_clusters'] = len(clusters)

        cl_indices_set = self.cluster_results.setdefault('cluster_particle_indices', set())
        for idx in self.selected_particle_indices:
            cl_indices_set.add(idx)

        # Añadir líneas de pares si procede
        pts = new_c.get('points', None)
        if pts is not None and len(pts) > 1:
            for i in range(len(pts) - 1):
                self.cluster_results.setdefault('pair_lines', []).append((pts[i, 0], pts[i, 1], pts[i+1, 0], pts[i+1, 1]))

        # Renderizar contorno del cúmulo manual
        poly = new_c.get('contour_polygon_nm', [])
        if len(poly) > 2:
            poly_arr = np.array(poly)
            poly_closed = np.vstack([poly_arr, poly_arr[0]])
            c_item = pg.PlotDataItem(
                poly_closed[:, 0], poly_closed[:, 1],
                pen=pg.mkPen('#a6e3a1', width=1.5, style=Qt.PenStyle.DashLine)
            )
            c_item.setZValue(15)
            c_item.setVisible(self.chk_layer_contours.isChecked())
            self.plot_real_space.addItem(c_item)
            self.cluster_contour_items.append(c_item)

        self._update_cluster_table()
        self.selected_cluster_id = next_id

        # Seleccionar la fila en table_clusters
        for r in range(self.table_clusters.rowCount()):
            item = self.table_clusters.item(r, 0)
            if item and item.text() == str(next_id):
                self.table_clusters.selectRow(r)
                self._on_cluster_table_clicked(r, 0)
                break

        self.statusBar().showMessage(f"Cúmulo manual #{next_id} creado ({len(self.selected_particle_indices)} partículas).", 4000)

    def _on_toggle_pick_visual_seeds(self, checked: bool):
        if checked:
            if hasattr(self, 'btn_cluster_add_particles') and self.btn_cluster_add_particles.isChecked():
                self.btn_cluster_add_particles.setChecked(False)
            self.statusBar().showMessage("Modo Semillas Visuales: Haga clic en el gráfico para colocar centros iniciales de partículas.", 5000)
        else:
            self.statusBar().showMessage("Modo Semillas Visuales desactivado.", 3000)

    def _on_clear_visual_seeds(self):
        self.manual_visual_seeds_nm.clear()
        self._redraw_visual_seeds()

    def _on_use_detected_as_seeds(self):
        if self.locs_df is None or self.locs_df.empty:
            return
        points = []
        if self.selected_particle_indices:
            sub = self.locs_df.loc[list(self.selected_particle_indices)]
            for _, row in sub.iterrows():
                points.append((float(row['x_nm']), float(row['y_nm'])))
        elif self.selected_cluster_id is not None and self.cluster_results:
            for c in self.cluster_results.get('clusters', []):
                if c.get('id') == self.selected_cluster_id or c.get('cluster_id') == self.selected_cluster_id:
                    pts = c.get('points', None)
                    if pts is not None:
                        for pt in pts:
                            points.append((float(pt[0]), float(pt[1])))
                    break
        if points:
            self.manual_visual_seeds_nm = points
            self._redraw_visual_seeds()
            self.statusBar().showMessage(f"{len(points)} posiciones detectadas copiadas como semillas iniciales.", 4000)
        else:
            QMessageBox.information(self, "Sin Selección", "Seleccione partículas o un cúmulo para usar sus centros como semillas.")

    def _redraw_visual_seeds(self):
        if self.scatter_visual_seeds is not None and self.scatter_visual_seeds in self.plot_real_space.items():
            self.plot_real_space.removeItem(self.scatter_visual_seeds)
            self.scatter_visual_seeds = None
        for txt in self.text_visual_seeds_items:
            if txt in self.plot_real_space.items():
                self.plot_real_space.removeItem(txt)
        self.text_visual_seeds_items.clear()

        n_seeds = len(self.manual_visual_seeds_nm)
        if hasattr(self, 'lbl_visual_seeds_status'):
            self.lbl_visual_seeds_status.setText(f"Semillas: {n_seeds}")

        if n_seeds > 0:
            xs = [p[0] for p in self.manual_visual_seeds_nm]
            ys = [p[1] for p in self.manual_visual_seeds_nm]
            self.scatter_visual_seeds = pg.ScatterPlotItem(
                x=xs, y=ys,
                size=14,
                symbol='+',
                pen=pg.mkPen('#a6e3a1', width=2.5),
                brush=pg.mkBrush(166, 227, 161, 200)
            )
            self.scatter_visual_seeds.setZValue(45)
            self.plot_real_space.addItem(self.scatter_visual_seeds)

            for i, (sx, sy) in enumerate(self.manual_visual_seeds_nm):
                txt = pg.TextItem(text=f"S{i+1}", color='#a6e3a1', anchor=(0.5, 1.3))
                txt.setPos(sx, sy)
                txt.setZValue(46)
                self.plot_real_space.addItem(txt)
                self.text_visual_seeds_items.append(txt)

            if hasattr(self, 'spin_cluster_n_gaussians'):
                self.spin_cluster_n_gaussians.blockSignals(True)
                self.spin_cluster_n_gaussians.setValue(min(max(n_seeds, 2), 8))
                self.spin_cluster_n_gaussians.blockSignals(False)

            if hasattr(self, 'spin_suspicious_n'):
                self.spin_suspicious_n.blockSignals(True)
                self.spin_suspicious_n.setValue(min(max(n_seeds, 2), 8))
                self.spin_suspicious_n.blockSignals(False)

    def _on_scatter_det_clicked(self, item, points):
        if len(points) == 0:
            return
        pt = points[0]
        pos = pt.pos()
        if self.locs_df is None or len(self.locs_df) == 0:
            return

        if hasattr(self, 'btn_pick_visual_seeds') and self.btn_pick_visual_seeds.isChecked():
            self.manual_visual_seeds_nm.append((float(pos.x()), float(pos.y())))
            self._redraw_visual_seeds()
            return
        x = self.locs_df['x_nm'].values
        y = self.locs_df['y_nm'].values
        dists = np.hypot(x - pos.x(), y - pos.y())
        idx_min = int(np.argmin(dists))
        search_r = self.spin_a_nominal.value() * 0.4
        if dists[idx_min] < search_r:
            # Modo Clic: Añadir / Quitar Partículas al Contorno Activo
            if hasattr(self, 'btn_cluster_add_particles') and self.btn_cluster_add_particles.isChecked() and self.selected_cluster_id is not None:
                if self.cluster_results is not None and 'clusters' in self.cluster_results:
                    for cl in self.cluster_results['clusters']:
                        if cl.get('id') == self.selected_cluster_id:
                            cur_indices = list(cl.get('indices', []))
                            if idx_min in cur_indices:
                                cur_indices.remove(idx_min)
                            else:
                                cur_indices.append(idx_min)
                            cl['indices'] = cur_indices
                            cl['n_det'] = len(cur_indices)
                            if len(cur_indices) > 0:
                                cl['com_x'] = float(np.mean(x[cur_indices]))
                                cl['com_y'] = float(np.mean(y[cur_indices]))
                            self.selected_particle_indices = set(int(i) for i in cur_indices)
                            self._update_selected_status()
                            self._redraw_selection_overlay()
                            self._on_cluster_contour_thresh_changed()
                            self._update_cluster_table()
                            return

            if idx_min in self.selected_particle_indices:
                self.selected_particle_indices.remove(idx_min)
            else:
                self.selected_particle_indices.add(idx_min)
            self._update_selected_status()
            self._redraw_selection_overlay()

    def _on_go_to_reciprocal(self):
        if self.locs_df is not None and len(self.locs_df) > 0:
            self._on_recalculate_reciprocal()
        self.tabs.setCurrentIndex(1)

    def _on_bg_filter_spin_changed(self, val: float):
        if hasattr(self, 'slider_bg_filter'):
            self.slider_bg_filter.blockSignals(True)
            self.slider_bg_filter.setValue(int(round(val)))
            self.slider_bg_filter.blockSignals(False)
        self._update_filtered_image()

    def _on_bg_filter_slider_changed(self, val: int):
        if hasattr(self, 'spin_bg_filter_pct'):
            self.spin_bg_filter_pct.blockSignals(True)
            self.spin_bg_filter_pct.setValue(float(val))
            self.spin_bg_filter_pct.blockSignals(False)
        self._update_filtered_image()

    def _on_bg_filter_preview_toggled(self, checked: bool):
        if hasattr(self, 'chk_layer_filtered'):
            self.chk_layer_filtered.blockSignals(True)
            self.chk_layer_filtered.setChecked(checked)
            self.chk_layer_filtered.blockSignals(False)
        self._update_filtered_image()

    def _update_filtered_image(self):
        if self.image_2d is None:
            return
        scale_nm = self.spin_scale.value() if hasattr(self, 'spin_scale') else 50.0
        filt_pct = self.spin_bg_filter_pct.value() if hasattr(self, 'spin_bg_filter_pct') else 20.0
        i_max = float(np.max(self.image_2d))
        thresh_val = (filt_pct / 100.0) * i_max
        self.image_filtered = np.clip(self.image_2d - thresh_val, 0, None)

        if self.img_item_filtered is None:
            self.img_item_filtered = pg.ImageItem(self.image_filtered.T)
            self.img_item_filtered.setRect(pg.QtCore.QRectF(
                0, 0, self.image_2d.shape[1] * scale_nm, self.image_2d.shape[0] * scale_nm
            ))
            self.img_item_filtered.setZValue(1)
            cmap_name = self.combo_colormap.currentText()
            self.img_item_filtered.setColorMap(get_pyqtgraph_colormap(cmap_name))
            self.plot_real_space.addItem(self.img_item_filtered)
        else:
            self.img_item_filtered.setImage(self.image_filtered.T)

        is_visible = self.chk_layer_filtered.isChecked() if hasattr(self, 'chk_layer_filtered') else (
            self.chk_filter_preview.isChecked() if hasattr(self, 'chk_filter_preview') else False
        )
        self.img_item_filtered.setVisible(is_visible)

    def _on_run_rl_deconvolution(self):
        if self.image_2d is None:
            QMessageBox.warning(self, "Atención", "Primero debe cargar una imagen TIFF.")
            return
        iter_count = self.spin_rl_iter.value() if hasattr(self, 'spin_rl_iter') else 15
        sigma_val = self.spin_rl_sigma.value() if hasattr(self, 'spin_rl_sigma') else 1.5
        self.statusBar().showMessage(f"Ejecutando Deconvolución Richardson-Lucy ({iter_count} iters, σ={sigma_val} px)...")
        QApplication.processEvents()
        try:
            self.image_rl = apply_richardson_lucy(
                self.image_2d,
                psf_sigma=sigma_val,
                num_iter=iter_count
            )
            scale_nm = self.spin_scale.value() if hasattr(self, 'spin_scale') else 50.0
            if self.img_item_rl is None:
                self.img_item_rl = pg.ImageItem(self.image_rl.T)
                self.img_item_rl.setRect(pg.QtCore.QRectF(
                    0, 0, self.image_2d.shape[1] * scale_nm, self.image_2d.shape[0] * scale_nm
                ))
                self.img_item_rl.setZValue(2)
                cmap_name = self.combo_colormap.currentText()
                self.img_item_rl.setColorMap(get_pyqtgraph_colormap(cmap_name))
                self.plot_real_space.addItem(self.img_item_rl)
            else:
                self.img_item_rl.setImage(self.image_rl.T)

            if hasattr(self, 'chk_layer_rl'):
                self.chk_layer_rl.blockSignals(True)
                self.chk_layer_rl.setChecked(True)
                self.chk_layer_rl.blockSignals(False)
            self.img_item_rl.setVisible(True)
            self.statusBar().showMessage("✅ Deconvolución Richardson-Lucy completada y superpuesta.", 5000)
        except Exception as e:
            QMessageBox.critical(self, "Error en Deconvolución RL", str(e))

    def _render_detected_particles_only(self):
        scale_nm = self.spin_scale.value()

        # Visualizar en plot_real_space
        self.plot_real_space.clear()

        if self.image_2d is not None:
            self.img_item = pg.ImageItem(self.image_2d.T)
            self.img_item.setRect(pg.QtCore.QRectF(
                0, 0, self.image_2d.shape[1] * scale_nm, self.image_2d.shape[0] * scale_nm
            ))
            self.img_item.setZValue(0)
            cmap_name = self.combo_colormap.currentText()
            self.img_item.setColorMap(get_pyqtgraph_colormap(cmap_name))
            self.img_item.setVisible(self.chk_layer_img.isChecked())
            self.plot_real_space.addItem(self.img_item)
        else:
            self.img_item = None

        if self.image_filtered is not None and self.image_2d is not None:
            self.img_item_filtered = pg.ImageItem(self.image_filtered.T)
            self.img_item_filtered.setRect(pg.QtCore.QRectF(
                0, 0, self.image_2d.shape[1] * scale_nm, self.image_2d.shape[0] * scale_nm
            ))
            self.img_item_filtered.setZValue(1)
            cmap_name = self.combo_colormap.currentText()
            self.img_item_filtered.setColorMap(get_pyqtgraph_colormap(cmap_name))
            self.img_item_filtered.setVisible(self.chk_layer_filtered.isChecked() if hasattr(self, 'chk_layer_filtered') else False)
            self.plot_real_space.addItem(self.img_item_filtered)
        else:
            self.img_item_filtered = None

        if self.image_rl is not None and self.image_2d is not None:
            self.img_item_rl = pg.ImageItem(self.image_rl.T)
            self.img_item_rl.setRect(pg.QtCore.QRectF(
                0, 0, self.image_2d.shape[1] * scale_nm, self.image_2d.shape[0] * scale_nm
            ))
            self.img_item_rl.setZValue(2)
            cmap_name = self.combo_colormap.currentText()
            self.img_item_rl.setColorMap(get_pyqtgraph_colormap(cmap_name))
            self.img_item_rl.setVisible(self.chk_layer_rl.isChecked() if hasattr(self, 'chk_layer_rl') else False)
            self.plot_real_space.addItem(self.img_item_rl)
        else:
            self.img_item_rl = None

        if self.locs_df is not None and len(self.locs_df) > 0:
            x_nm = self.locs_df['x_nm'].values
            y_nm = self.locs_df['y_nm'].values

            # Superponer partículas detectadas (Cian)
            self.scatter_det = pg.ScatterPlotItem(
                x=x_nm,
                y=y_nm,
                size=8,
                pen=pg.mkPen('#89dceb', width=1.5),
                brush=pg.mkBrush(137, 220, 235, 120),
                symbol='o'
            )
            self.scatter_det.setZValue(25)
            self.scatter_det.sigClicked.connect(self._on_scatter_det_clicked)
            self.scatter_det.setVisible(self.chk_layer_det.isChecked())
            self.plot_real_space.addItem(self.scatter_det)

            self.lbl_real_metrics.setText(
                f"Partículas Detectadas: {len(self.locs_df)}\n"
                f"Aglomerados / Cadenas: Pendiente (Presione '🔍 Detectar Aglomerados')\n"
                f"Grilla / Vacancias: Pendiente (Presione '📐 Ajustar Grilla')\n"
                f"g(r): Pendiente de cálculo"
            )
            self.lbl_real_metrics.setStyleSheet(
                "font-family: monospace; font-size: 11px; color: #89b4fa; "
                "background: #181825; border: 1px solid #313244; border-radius: 4px; padding: 6px;"
            )
            self.lbl_consistency.setText("Paso 1 Completado: Partículas localizadas.")
            self.lbl_consistency.setStyleSheet("font-family: monospace; font-size: 11px; color: #89b4fa;")

        # Limpiar referencias de superposiciones previas
        self.scatter_clusters = None
        self.scatter_vac = None
        self.scatter_grid = None
        self.cluster_lines_items = []
        self.cluster_contour_items = []
        self.table_clusters.setRowCount(0)
        self.lbl_cluster_summary.setText("Aglomerados: - | Sobrepuestas: -")
        self.plot_rdf.clear()

        # Re-agregar las 4 reglas móviles de ROI
        for line in [self.line_roi_xmin, self.line_roi_xmax, self.line_roi_ymin, self.line_roi_ymax]:
            if line not in self.plot_real_space.items():
                self.plot_real_space.addItem(line)
            line.setVisible(self.chk_layer_roi.isChecked())

    def _on_detect_clusters(self):
        if self.locs_df is None or len(self.locs_df) == 0:
            QMessageBox.warning(self, "Atención", "Primero debe detectar o cargar partículas.")
            return

        scale_nm = self.spin_scale.value()
        a_nom = self.spin_a_nominal.value()
        x_nm = self.locs_df['x_nm'].values
        y_nm = self.locs_df['y_nm'].values

        photons_arr = self.locs_df['photons'].values if 'photons' in self.locs_df.columns else (
            self.locs_df['mass'].values if 'mass' in self.locs_df.columns else None
        )
        tol_val = self.spin_cluster_tolerance.value() if hasattr(self, 'spin_cluster_tolerance') else 20.0

        self.cluster_results = detect_clusters_and_chains(
            x_nm, y_nm,
            a_nominal=a_nom,
            r_cluster_factor=0.60,
            photons=photons_arr,
            image_2d=self.image_2d,
            locs_df=self.locs_df,
            scale_nm=scale_nm,
            signature_dict=self.monomer_signature,
            tolerance_pct=tol_val
        )
        if self.monomer_signature is None and self.cluster_results and 'signature' in self.cluster_results and self.cluster_results['signature']:
            self.monomer_signature = self.cluster_results['signature']

        # Limpiar elementos anteriores de cúmulos en el visor
        for item in self.cluster_lines_items:
            if item in self.plot_real_space.items():
                self.plot_real_space.removeItem(item)
        self.cluster_lines_items = []

        for item in self.cluster_contour_items:
            if item in self.plot_real_space.items():
                self.plot_real_space.removeItem(item)
        self.cluster_contour_items = []

        if self.scatter_clusters and self.scatter_clusters in self.plot_real_space.items():
            self.plot_real_space.removeItem(self.scatter_clusters)
            self.scatter_clusters = None

        # Dibujar líneas de conexión entre pares en cúmulo
        if self.cluster_results and len(self.cluster_results.get('pair_lines', [])) > 0:
            for (lx1, ly1, lx2, ly2) in self.cluster_results['pair_lines']:
                line_item = pg.PlotDataItem(
                    [lx1, lx2], [ly1, ly2],
                    pen=pg.mkPen('#fab387', width=2, style=Qt.PenStyle.DashLine)
                )
                line_item.setZValue(15)
                line_item.setVisible(self.chk_layer_clusters.isChecked())
                self.plot_real_space.addItem(line_item)
                self.cluster_lines_items.append(line_item)

        # Dibujar contornos fotométricos segmentados
        if self.cluster_results and len(self.cluster_results.get('clusters', [])) > 0:
            for c in self.cluster_results['clusters']:
                poly = c.get('contour_polygon_nm', [])
                if len(poly) > 2:
                    poly_arr = np.array(poly)
                    poly_closed = np.vstack([poly_arr, poly_arr[0]])
                    c_item = pg.PlotDataItem(
                        poly_closed[:, 0], poly_closed[:, 1],
                        pen=pg.mkPen('#f9e2af', width=1.5, style=Qt.PenStyle.DashLine)
                    )
                    c_item.setZValue(15)
                    c_item.setVisible(self.chk_layer_contours.isChecked())
                    self.plot_real_space.addItem(c_item)
                    self.cluster_contour_items.append(c_item)

        # Superponer partículas pertenecientes a aglomerados
        if self.cluster_results and self.cluster_results.get('n_clusters', 0) > 0:
            cl_indices = list(self.cluster_results.get('cluster_particle_indices', []))
            if len(cl_indices) > 0:
                cl_x = x_nm[cl_indices]
                cl_y = y_nm[cl_indices]
                self.scatter_clusters = pg.ScatterPlotItem(
                    x=cl_x,
                    y=cl_y,
                    size=12,
                    pen=pg.mkPen('#fab387', width=2),
                    brush=pg.mkBrush(250, 179, 135, 140),
                    symbol='t'
                )
                self.scatter_clusters.setZValue(30)
                self.scatter_clusters.setVisible(self.chk_layer_clusters.isChecked())
                self.plot_real_space.addItem(self.scatter_clusters)

        self._update_cluster_table()
        n_cl = self.cluster_results.get('n_clusters', 0) if self.cluster_results else 0
        n_ov = self.cluster_results.get('n_overlapping_spots', 0) if self.cluster_results else 0
        self.statusBar().showMessage(f"Detección de cúmulos completada: {n_cl} aglomerados, {n_ov} sobrepuestas.", 5000)

    def _on_recalc_grid(self):
        if self.locs_df is None or len(self.locs_df) == 0:
            QMessageBox.warning(self, "Atención", "Primero debe detectar o cargar partículas.")
            return

        a_nom = self.spin_a_nominal.value()
        n_side = self.spin_n_side.value()
        x_nm = self.locs_df['x_nm'].values
        y_nm = self.locs_df['y_nm'].values
        margin_pct = self.spin_consistency_margin.value() if hasattr(self, 'spin_consistency_margin') else 10.0

        # 1. KDTree Bounded con chequeo de margen físico
        self.kdtree_results = analyze_real_space_kdtree(
            x_nm, y_nm, a=a_nom, n_side=n_side, margin_percent=margin_pct
        )

        # 2. Función de Distribución Radial g(r)
        rmin = self.line_rdf_rmin.value() if (hasattr(self, 'line_rdf_rmin') and self.line_rdf_rmin and hasattr(self, 'chk_rdf_manual_roi') and self.chk_rdf_manual_roi.isChecked()) else None
        rmax = self.line_rdf_rmax.value() if (hasattr(self, 'line_rdf_rmax') and self.line_rdf_rmax and hasattr(self, 'chk_rdf_manual_roi') and self.chk_rdf_manual_roi.isChecked()) else None
        bg_val = self.line_rdf_bg.value() if (hasattr(self, 'line_rdf_bg') and self.line_rdf_bg and hasattr(self, 'chk_rdf_fix_bg') and self.chk_rdf_fix_bg.isChecked()) else None

        self.rdf_results = compute_radial_distribution_function(
            x_nm, y_nm, a_nominal=a_nom, r_roi_min=rmin, r_roi_max=rmax, fixed_bg=bg_val
        )

        # Actualizar tarjeta de métricas y consistencia
        kd = self.kdtree_results
        rdf = self.rdf_results

        v_prac = kd.get('n_vac_prac', kd.get('vacant_count', 0))
        f_prac_pct = kd.get('f_vac_prac_percent', kd.get('f_vac_percent', 0.0))
        v_teor = kd.get('n_vac_teor', kd.get('vacant_count', 0))
        f_teor_pct = kd.get('f_vac_teor_percent', kd.get('f_vac_percent', 0.0))
        m_assigned = kd.get('assigned_particles', kd.get('matched_count', 0))

        det_info = (
            f"Sitios Totales N²: {kd['N_total_sites']} | Partículas Asignadas M: {m_assigned}\n"
            f"• Vacancias Prácticas (N² - M): {v_prac} ({f_prac_pct:.1f}%)\n"
            f"• Vacancias Teóricas (Nodos Libres): {v_teor} ({f_teor_pct:.1f}%)\n"
            f"Partículas en ROI: {kd['particles_detected']} (En Grilla: {kd.get('particles_in_grid', kd['particles_detected'])}, Fuera: {kd.get('particles_outside_grid', 0)})\n"
            f"Nodos Multi-ocupados: {kd.get('multi_occupied_count', 0)}"
        )

        alert_block = ""
        if kd.get('excess_particles', False):
            alert_block = (
                f"\n\n⚠️ ALERTA:\n"
                f"Detectadas ({kd['particles_detected']}) > Sitios Nominales ({kd['N_total_sites']})\n"
                f"Ratio = {kd['detection_ratio']:.2f} > 1.0\n"
                f"Active las reglas de ROI para recortar o resuelva aglomerados."
            )
            self.lbl_real_metrics.setStyleSheet(
                "font-family: monospace; font-size: 11px; color: #f38ba8; "
                "background: #312028; border: 1px solid #f38ba8; border-radius: 4px; padding: 6px;"
            )
        else:
            self.lbl_real_metrics.setStyleSheet(
                "font-family: monospace; font-size: 11px; color: #a6e3a1; "
                "background: #181825; border: 1px solid #313244; border-radius: 4px; padding: 6px;"
            )

        self.lbl_real_metrics.setText(
            f"{det_info}\n"
            f"Desorden σ_x: {kd['sigma_x']:.2f} nm | σ_y: {kd['sigma_y']:.2f} nm\n"
            f"Desorden Medio σ_pos: {kd['sigma_pos']:.2f} nm\n"
            f"Ancho g(r) σ_rdf: {rdf['sigma_rdf']:.2f} nm"
            f"{alert_block}"
        )

        c_ok = kd.get('consistency_ok', True)
        c_msg = kd.get('consistency_msg', 'Consistencia: OK')
        if c_ok:
            self.lbl_consistency.setStyleSheet("font-family: monospace; font-size: 11px; color: #a6e3a1; font-weight: bold;")
        else:
            self.lbl_consistency.setStyleSheet("font-family: monospace; font-size: 11px; color: #f38ba8; font-weight: bold;")
        self.lbl_consistency.setText(c_msg)

        # Actualizar scatter de vacancias y grilla
        if self.scatter_vac and self.scatter_vac in self.plot_real_space.items():
            self.plot_real_space.removeItem(self.scatter_vac)
            self.scatter_vac = None

        if len(kd['vacant_points']) > 0:
            vac_x = kd['vacant_points'][:, 0]
            vac_y = kd['vacant_points'][:, 1]
            self.scatter_vac = pg.ScatterPlotItem(
                x=vac_x,
                y=vac_y,
                size=11,
                pen=pg.mkPen('#f38ba8', width=2),
                brush=pg.mkBrush(243, 139, 168, 80),
                symbol='x'
            )
            self.scatter_vac.setZValue(20)
            self.scatter_vac.setVisible(self.chk_layer_vac.isChecked())
            self.plot_real_space.addItem(self.scatter_vac)

        if self.scatter_grid and self.scatter_grid in self.plot_real_space.items():
            self.plot_real_space.removeItem(self.scatter_grid)
            self.scatter_grid = None

        if len(kd['grid_points']) > 0:
            grid_x = kd['grid_points'][:, 0]
            grid_y = kd['grid_points'][:, 1]
            self.scatter_grid = pg.ScatterPlotItem(
                x=grid_x,
                y=grid_y,
                size=5,
                pen=pg.mkPen('#a6adc8', width=1),
                brush=pg.mkBrush(166, 173, 200, 60),
                symbol='+'
            )
            self.scatter_grid.setZValue(10)
            self.scatter_grid.setVisible(self.chk_layer_grid.isChecked())
            self.plot_real_space.addItem(self.scatter_grid)

        # Dibujar / actualizar g(r)
        self._plot_rdf_results()
        self._update_metrics_table()
        self.statusBar().showMessage("Grilla óptima, vacancias y g(r) calculados exitosamente.", 5000)

    def _plot_rdf_results(self):
        if self.rdf_results is None:
            return
        rdf = self.rdf_results
        a_nom = self.spin_a_nominal.value()

        self.plot_rdf.clear()
        if len(rdf['r']) > 0:
            self.plot_rdf.plot(
                rdf['r'], rdf['gr'],
                pen=pg.mkPen('#a6e3a1', width=2),
                name='g(r) Experimental'
            )
            line_a = pg.InfiniteLine(pos=a_nom, angle=90, pen=pg.mkPen('#f9e2af', style=Qt.PenStyle.DashLine))
            self.plot_rdf.addItem(line_a)
            r_diff = rdf.get('r_diffraction_limit', 250.0)
            if r_diff > 0:
                line_diff = pg.InfiniteLine(
                    pos=r_diff, angle=90,
                    pen=pg.mkPen('#f38ba8', width=1, style=Qt.PenStyle.DotLine)
                )
                self.plot_rdf.addItem(line_diff)

            # Ajuste Gaussiano explicativo del 1er pico de coordinación
            fit_r = rdf.get('fit_r')
            fit_gr = rdf.get('fit_gr')
            fit_r0 = rdf.get('first_peak_r', a_nom)
            fit_fwhm = rdf.get('fwhm_rdf', 0.0)
            sigma_rdf = rdf.get('sigma_rdf', 0.0)
            fit_h = rdf.get('height_rdf', 1.0)
            bg_fit = rdf.get('bg_rdf', 0.0)

            if fit_r is not None and len(fit_r) > 0 and fit_gr is not None and len(fit_gr) > 0:
                self.plot_rdf.plot(
                    fit_r, fit_gr,
                    pen=pg.mkPen('#89dceb', width=2.2, style=Qt.PenStyle.DashLine),
                    name='Ajuste Gaussiano 1er Pico'
                )
                line_r0 = pg.InfiniteLine(
                    pos=fit_r0, angle=90,
                    pen=pg.mkPen('#89dceb', width=1.5, style=Qt.PenStyle.DotLine)
                )
                self.plot_rdf.addItem(line_r0)

                # Línea horizontal de FWHM a media altura sobre el fondo
                half_h = bg_fit + fit_h / 2.0
                fwhm_half = fit_fwhm / 2.0
                if fit_fwhm > 0 and fit_h > 0:
                    self.plot_rdf.plot(
                        [fit_r0 - fwhm_half, fit_r0 + fwhm_half],
                        [half_h, half_h],
                        pen=pg.mkPen('#fab387', width=2),
                        name='FWHM 1er Pico'
                    )

                # Tarjeta de texto explicativa sobre el gráfico
                badge_text = (
                    f"<div style='background-color: rgba(24, 24, 37, 190); padding: 6px 10px; "
                    f"border: 1px solid #89dceb; border-radius: 5px; color: #cdd6f4; font-size: 10px;'>"
                    f"<b>1er Pico de Coordinación:</b><br>"
                    f"• Centro r₀: <b>{fit_r0:.1f} nm</b> (Nominal: {a_nom:.0f} nm)<br>"
                    f"• Ancho FWHM: <b>{fit_fwhm:.1f} nm</b><br>"
                    f"• Desorden local σ_rdf: <b>{sigma_rdf:.1f} nm</b><br>"
                    f"• Fondo Base: <b>{bg_fit:.2f}</b>"
                    f"</div>"
                )
                txt_item = pg.TextItem(html=badge_text, anchor=(1, 0))
                max_r = float(np.max(rdf['r'])) if len(rdf['r']) > 0 else a_nom * 2
                max_gr = float(np.max(rdf['gr'])) if len(rdf['gr']) > 0 else 2.0
                txt_item.setPos(max_r * 0.95, max_gr * 0.95)
                self.plot_rdf.addItem(txt_item)

        # Reglas visuales si están activas
        if hasattr(self, 'chk_rdf_manual_roi') and self.chk_rdf_manual_roi.isChecked():
            if self.line_rdf_rmin not in self.plot_rdf.items():
                self.plot_rdf.addItem(self.line_rdf_rmin)
            if self.line_rdf_rmax not in self.plot_rdf.items():
                self.plot_rdf.addItem(self.line_rdf_rmax)
            if self.line_rdf_bg not in self.plot_rdf.items():
                self.plot_rdf.addItem(self.line_rdf_bg)

    def _on_toggle_rdf_manual_roi(self, checked: bool):
        if not checked:
            if self.line_rdf_rmin in self.plot_rdf.items():
                self.plot_rdf.removeItem(self.line_rdf_rmin)
            if self.line_rdf_rmax in self.plot_rdf.items():
                self.plot_rdf.removeItem(self.line_rdf_rmax)
            if self.line_rdf_bg in self.plot_rdf.items():
                self.plot_rdf.removeItem(self.line_rdf_bg)
            if self.locs_df is not None and len(self.locs_df) > 0 and self.kdtree_results is not None:
                self._on_recalc_grid()
        else:
            a_nom = self.spin_a_nominal.value()
            self._updating_rdf_rules_internally = True
            try:
                self.line_rdf_rmin.setValue(a_nom * 0.65)
                self.line_rdf_rmax.setValue(a_nom * 1.35)
                self.line_rdf_bg.setValue(0.0)
            finally:
                self._updating_rdf_rules_internally = False
            self._plot_rdf_results()

    def _on_reset_rdf_rules(self):
        a_nom = self.spin_a_nominal.value()
        self._updating_rdf_rules_internally = True
        try:
            self.line_rdf_rmin.setValue(a_nom * 0.65)
            self.line_rdf_rmax.setValue(a_nom * 1.35)
            self.line_rdf_bg.setValue(0.0)
        finally:
            self._updating_rdf_rules_internally = False
        self._on_rdf_rules_changed()

    def _on_rdf_rules_changed(self):
        if self._updating_rdf_rules_internally or self.locs_df is None or len(self.locs_df) == 0:
            return
        a_nom = self.spin_a_nominal.value()
        x_nm = self.locs_df['x_nm'].values
        y_nm = self.locs_df['y_nm'].values

        rmin = self.line_rdf_rmin.value() if (hasattr(self, 'chk_rdf_manual_roi') and self.chk_rdf_manual_roi.isChecked()) else None
        rmax = self.line_rdf_rmax.value() if (hasattr(self, 'chk_rdf_manual_roi') and self.chk_rdf_manual_roi.isChecked()) else None
        bg_val = self.line_rdf_bg.value() if (hasattr(self, 'chk_rdf_fix_bg') and self.chk_rdf_fix_bg.isChecked()) else None

        self.rdf_results = compute_radial_distribution_function(
            x_nm, y_nm, a_nominal=a_nom, r_roi_min=rmin, r_roi_max=rmax, fixed_bg=bg_val
        )
        self._plot_rdf_results()

        # Actualizar métrica en tarjeta si existe kdtree
        if self.kdtree_results is not None:
            kd = self.kdtree_results
            rdf = self.rdf_results
            v_prac = kd.get('n_vac_prac', kd.get('vacant_count', 0))
            f_prac_pct = kd.get('f_vac_prac_percent', kd.get('f_vac_percent', 0.0))
            v_teor = kd.get('n_vac_teor', kd.get('vacant_count', 0))
            f_teor_pct = kd.get('f_vac_teor_percent', kd.get('f_vac_percent', 0.0))
            m_assigned = kd.get('assigned_particles', kd.get('matched_count', 0))
            det_info = (
                f"Sitios Totales N²: {kd['N_total_sites']} | Partículas Asignadas M: {m_assigned}\n"
                f"• Vacancias Prácticas (N² - M): {v_prac} ({f_prac_pct:.1f}%)\n"
                f"• Vacancias Teóricas (Nodos Libres): {v_teor} ({f_teor_pct:.1f}%)\n"
                f"Partículas en ROI: {kd['particles_detected']} (En Grilla: {kd.get('particles_in_grid', kd['particles_detected'])}, Fuera: {kd.get('particles_outside_grid', 0)})\n"
                f"Nodos Multi-ocupados: {kd.get('multi_occupied_count', 0)}"
            )
            self.lbl_real_metrics.setText(
                f"{det_info}\n"
                f"Desorden σ_x: {kd['sigma_x']:.2f} nm | σ_y: {kd['sigma_y']:.2f} nm\n"
                f"Desorden Medio σ_pos: {kd['sigma_pos']:.2f} nm\n"
                f"Ancho g(r) σ_rdf: {rdf['sigma_rdf']:.2f} nm"
            )

    def _get_peak_info(self, idx: int):
        peak_keys = ['x_1st', 'y_1st', 'diag', 'x_2nd', 'y_2nd']
        pk_key = peak_keys[idx]
        a_nom = self.spin_a_nominal.value() if hasattr(self, 'spin_a_nominal') else 450.0
        f0_nom = 1.0 / a_nom if a_nom > 0 else 1.0 / 450.0

        if pk_key == 'x_1st':
            plot_widget = self.plot_cut_x
            target_f = (self.reciprocal_results['fit_x']['f0'] if self.reciprocal_results and self.reciprocal_results.get('fit_x') and self.reciprocal_results['fit_x']['f0'] > 1e-9 else f0_nom)
        elif pk_key == 'y_1st':
            plot_widget = self.plot_cut_y
            target_f = (self.reciprocal_results['fit_y']['f0'] if self.reciprocal_results and self.reciprocal_results.get('fit_y') and self.reciprocal_results['fit_y']['f0'] > 1e-9 else f0_nom)
        elif pk_key == 'diag':
            plot_widget = getattr(self, 'plot_cut_diag', self.plot_cut_x)
            target_f = (self.reciprocal_results['fit_diag']['f0'] if self.reciprocal_results and self.reciprocal_results.get('fit_diag') and self.reciprocal_results['fit_diag']['f0'] > 1e-9 else f0_nom * np.sqrt(2.0))
        elif pk_key == 'x_2nd':
            plot_widget = self.plot_cut_x
            target_f = (self.reciprocal_results['fit_x_2nd']['f0'] if self.reciprocal_results and self.reciprocal_results.get('fit_x_2nd') and self.reciprocal_results['fit_x_2nd']['f0'] > 1e-9 else 2.0 * f0_nom)
        else:  # 'y_2nd'
            plot_widget = self.plot_cut_y
            target_f = (self.reciprocal_results['fit_y_2nd']['f0'] if self.reciprocal_results and self.reciprocal_results.get('fit_y_2nd') and self.reciprocal_results['fit_y_2nd']['f0'] > 1e-9 else 2.0 * f0_nom)

        return pk_key, plot_widget, target_f

    def _on_tune_peak_changed(self, idx: int):
        pk_key, target_plot, target_f = self._get_peak_info(idx)

        # Retirar líneas del gráfico anterior
        if self._current_tuned_plot is not None:
            for line in [self.line_peak_fmin, self.line_peak_fmax, self.line_peak_bg]:
                if line in self._current_tuned_plot.items():
                    self._current_tuned_plot.removeItem(line)

        self._current_tuned_plot = target_plot

        # Cargar configuración previa si existe en self.peak_tuning_dict
        cfg = self.peak_tuning_dict.get(pk_key, {})
        fmin = cfg.get('f_min', target_f * 0.75)
        fmax = cfg.get('f_max', target_f * 1.25)
        bg = cfg.get('fixed_bg', 0.0)
        fix_bg = cfg.get('fixed_bg') is not None
        model = cfg.get('model', 'double' if self.chk_double_peak.isChecked() else 'single')
        crit = cfg.get('peak_selection_mode', 'highest')

        self._updating_peak_rules_internally = True
        try:
            self.combo_peak_model.setCurrentIndex(0 if model == 'double' else 1)
            self.combo_peak_criterion.setCurrentIndex(0 if crit == 'highest' else 1)
            self.chk_peak_fix_bg.setChecked(fix_bg)
            self.spin_peak_fmin.setValue(fmin)
            self.spin_peak_fmax.setValue(fmax)
            self.spin_peak_bg.setValue(bg if bg is not None else 0.0)

            self.line_peak_fmin.setValue(fmin)
            self.line_peak_fmax.setValue(fmax)
            self.line_peak_bg.setValue(bg if bg is not None else 0.0)
        finally:
            self._updating_peak_rules_internally = False

        # Si las reglas visuales están activas, colocarlas en el nuevo gráfico objetivo
        if self.chk_peak_manual_roi.isChecked() and target_plot is not None:
            for line in [self.line_peak_fmin, self.line_peak_fmax, self.line_peak_bg]:
                if line not in target_plot.items():
                    target_plot.addItem(line)

    def _on_toggle_peak_rules(self, checked: bool):
        idx = self.combo_tune_peak.currentIndex()
        pk_key, target_plot, target_f = self._get_peak_info(idx)

        if not checked:
            if self._current_tuned_plot is not None:
                for line in [self.line_peak_fmin, self.line_peak_fmax, self.line_peak_bg]:
                    if line in self._current_tuned_plot.items():
                        self._current_tuned_plot.removeItem(line)
        else:
            self._current_tuned_plot = target_plot
            if target_plot is not None:
                for line in [self.line_peak_fmin, self.line_peak_fmax, self.line_peak_bg]:
                    if line not in target_plot.items():
                        target_plot.addItem(line)

    def _on_reset_peak_rules(self):
        idx = self.combo_tune_peak.currentIndex()
        _, _, target_f = self._get_peak_info(idx)
        self._updating_peak_rules_internally = True
        try:
            fmin = target_f * 0.75
            fmax = target_f * 1.25
            self.spin_peak_fmin.setValue(fmin)
            self.spin_peak_fmax.setValue(fmax)
            self.spin_peak_bg.setValue(0.0)
            self.line_peak_fmin.setValue(fmin)
            self.line_peak_fmax.setValue(fmax)
            self.line_peak_bg.setValue(0.0)
        finally:
            self._updating_peak_rules_internally = False

    def _on_peak_spin_changed(self):
        if self._updating_peak_rules_internally:
            return
        self._updating_peak_rules_internally = True
        try:
            self.line_peak_fmin.setValue(self.spin_peak_fmin.value())
            self.line_peak_fmax.setValue(self.spin_peak_fmax.value())
            self.line_peak_bg.setValue(self.spin_peak_bg.value())
        finally:
            self._updating_peak_rules_internally = False

    def _on_peak_line_dragged(self):
        if self._updating_peak_rules_internally:
            return
        self._updating_peak_rules_internally = True
        try:
            fmin = self.line_peak_fmin.value()
            fmax = self.line_peak_fmax.value()
            bg = self.line_peak_bg.value()
            self.spin_peak_fmin.setValue(round(fmin, 6))
            self.spin_peak_fmax.setValue(round(fmax, 6))
            self.spin_peak_bg.setValue(round(bg, 2))
        finally:
            self._updating_peak_rules_internally = False

    def _on_apply_selected_peak_fit(self):
        if self.locs_df is None or len(self.locs_df) == 0:
            QMessageBox.warning(self, "Atención", "No hay datos cargados para ajustar.")
            return

        idx = self.combo_tune_peak.currentIndex()
        pk_key, _, _ = self._get_peak_info(idx)

        model_type = 'double' if self.combo_peak_model.currentIndex() == 0 else 'single'
        crit_type = 'highest' if self.combo_peak_criterion.currentIndex() == 0 else 'closest_nominal'

        fmin = self.spin_peak_fmin.value() if self.chk_peak_manual_roi.isChecked() else None
        fmax = self.spin_peak_fmax.value() if self.chk_peak_manual_roi.isChecked() else None
        fixed_bg = self.spin_peak_bg.value() if self.chk_peak_fix_bg.isChecked() else None

        self.peak_tuning_dict[pk_key] = {
            'model': model_type,
            'peak_selection_mode': crit_type,
            'f_min': fmin,
            'f_max': fmax,
            'fixed_bg': fixed_bg
        }

        self._on_recalculate_reciprocal()
        self.statusBar().showMessage(f"Pico {self.combo_tune_peak.currentText()} re-ajustado exitosamente ({model_type}).", 4000)

    def _on_roi_line_dragged(self):
        if self._updating_roi_internally:
            return
        self._updating_roi_internally = True
        try:
            scale_nm = self.spin_scale.value()
            if scale_nm <= 0:
                scale_nm = 50.0

            px_xmin = self.line_roi_xmin.value() / scale_nm
            px_xmax = self.line_roi_xmax.value() / scale_nm
            px_ymin = self.line_roi_ymin.value() / scale_nm
            px_ymax = self.line_roi_ymax.value() / scale_nm

            self.spin_roi_xmin.setValue(round(px_xmin, 1))
            self.spin_roi_xmax.setValue(round(px_xmax, 1))
            self.spin_roi_ymin.setValue(round(px_ymin, 1))
            self.spin_roi_ymax.setValue(round(px_ymax, 1))
        finally:
            self._updating_roi_internally = False

    def _on_roi_spin_changed(self):
        if self._updating_roi_internally:
            return
        self._updating_roi_internally = True
        try:
            scale_nm = self.spin_scale.value()
            px_xmin = self.spin_roi_xmin.value()
            px_xmax = self.spin_roi_xmax.value()
            px_ymin = self.spin_roi_ymin.value()
            px_ymax = self.spin_roi_ymax.value()

            self.line_roi_xmin.setValue(px_xmin * scale_nm)
            self.line_roi_xmax.setValue(px_xmax * scale_nm)
            self.line_roi_ymin.setValue(px_ymin * scale_nm)
            self.line_roi_ymax.setValue(px_ymax * scale_nm)
        finally:
            self._updating_roi_internally = False

    def _on_reset_roi_to_image(self):
        if self.image_2d is not None:
            h_px, w_px = self.image_2d.shape[:2]
            self.spin_roi_xmin.setValue(0.0)
            self.spin_roi_xmax.setValue(float(w_px))
            self.spin_roi_ymin.setValue(0.0)
            self.spin_roi_ymax.setValue(float(h_px))
        else:
            self.spin_roi_xmin.setValue(0.0)
            self.spin_roi_xmax.setValue(330.0)
            self.spin_roi_ymin.setValue(0.0)
            self.spin_roi_ymax.setValue(330.0)

    def _apply_roi_filter(self):
        if self.locs_df_raw is None or self.locs_df_raw.empty:
            if self.locs_df is not None and not self.locs_df.empty:
                self.locs_df_raw = self.locs_df.copy()
            else:
                QMessageBox.warning(self, "Atención", "No hay detecciones previas para recortar.")
                return

        px_xmin = self.spin_roi_xmin.value()
        px_xmax = self.spin_roi_xmax.value()
        px_ymin = self.spin_roi_ymin.value()
        px_ymax = self.spin_roi_ymax.value()

        if px_xmin > px_xmax:
            px_xmin, px_xmax = px_xmax, px_xmin
            self.spin_roi_xmin.setValue(px_xmin)
            self.spin_roi_xmax.setValue(px_xmax)
        if px_ymin > px_ymax:
            px_ymin, px_ymax = px_ymax, px_ymin
            self.spin_roi_ymin.setValue(px_ymin)
            self.spin_roi_ymax.setValue(px_ymax)

        df_filtered = self.locs_df_raw[
            (self.locs_df_raw['x'] >= px_xmin) &
            (self.locs_df_raw['x'] <= px_xmax) &
            (self.locs_df_raw['y'] >= px_ymin) &
            (self.locs_df_raw['y'] <= px_ymax)
        ].copy()

        if df_filtered.empty:
            QMessageBox.warning(self, "Recorte Vacío", "No quedaron partículas dentro del ROI seleccionado.")
            return

        self.locs_df = df_filtered.reset_index(drop=True)
        self._update_real_space_analysis()
        self._on_recalculate_reciprocal()

        QMessageBox.information(
            self,
            "Recorte Aplicado",
            f"Se mantuvieron {len(self.locs_df)} de {len(self.locs_df_raw)} partículas.\n"
            f"Métricas actualizadas automáticamente en Espacio Real y Recíproco."
        )

    def _on_load_image(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Cargar Imagen Confocal",
            "",
            "Imágenes (*.tiff *.tif *.png *.jpg *.h5 *.hdf5);;Todos (*.*)"
        )
        if not file_path:
            return

        try:
            self.raw_image_2d = load_image(file_path)
            self.current_image_path = file_path

            if self.chk_invert_img.isChecked():
                i_min = float(np.min(self.raw_image_2d))
                i_max = float(np.max(self.raw_image_2d))
                self.image_2d = (i_max + i_min) - self.raw_image_2d
            else:
                self.image_2d = self.raw_image_2d.copy()

            self.image_filtered = None
            self.image_rl = None
            if self.img_item_filtered is not None and self.img_item_filtered in self.plot_real_space.items():
                self.plot_real_space.removeItem(self.img_item_filtered)
                self.img_item_filtered = None
            if self.img_item_rl is not None and self.img_item_rl in self.plot_real_space.items():
                self.plot_real_space.removeItem(self.img_item_rl)
                self.img_item_rl = None

            self.lbl_file_info.setText(
                f"Imagen: {os.path.basename(file_path)}\n"
                f"Dimensiones: {self.image_2d.shape[1]} x {self.image_2d.shape[0]} px\n"
                f"Rango: [{self.image_2d.min():.2f}, {self.image_2d.max():.2f}]"
            )

            # Ajustar reglas de ROI si están en 0
            h_px, w_px = self.image_2d.shape[:2]
            if self.spin_roi_xmax.value() == 0 or self.spin_roi_xmax.value() > w_px * 2:
                self.spin_roi_xmin.setValue(0.0)
                self.spin_roi_xmax.setValue(float(w_px))
                self.spin_roi_ymin.setValue(0.0)
                self.spin_roi_ymax.setValue(float(h_px))

            self._update_real_space_analysis()

            QMessageBox.information(
                self,
                "Imagen Cargada",
                f"Imagen cargada exitosamente: {os.path.basename(file_path)}\n"
                f"Tamaño: {self.image_2d.shape[1]} x {self.image_2d.shape[0]} píxeles."
            )
        except Exception as e:
            QMessageBox.critical(self, "Error al Cargar Imagen", f"Detalle: {str(e)}")

    def _on_load_coordinates(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Cargar Coordenadas Directas",
            "",
            "Tablas de Coordenadas (*.csv *.txt *.tsv *.npy);;Todos (*.*)"
        )
        if not file_path:
            return

        try:
            df = load_coordinates(file_path)
            scale_nm = self.spin_scale.value()

            # Verificar si ya están en nm o en px
            if 'x_nm' not in df.columns:
                df = convert_pixels_to_nm(df, pixel_size_nm=scale_nm)

            self.locs_df_raw = df.copy()
            self.locs_df = df.copy()
            self.current_image_path = file_path
            self.lbl_file_info.setText(
                f"Coordenadas: {os.path.basename(file_path)}\n"
                f"Partículas: {len(df)}"
            )

            # Procesar paso 1 (sólo detección y renderizado)
            self.kdtree_results = None
            self.cluster_results = None
            self.rdf_results = None
            self.reciprocal_results = None
            self._render_detected_particles_only()

            QMessageBox.information(
                self,
                "Coordenadas Cargadas (Paso 1)",
                f"Se cargaron {len(df)} coordenadas directas.\n\n"
                "• Siguiente paso recomendado: '🔍 Detectar Aglomerados y Cadenas' en el Grupo 5.\n"
                "• Para ajustar grilla y vacancias: '📐 Ajustar Grilla y Calcular Vacancias' en el Grupo 6."
            )
        except Exception as e:
            QMessageBox.critical(self, "Error al Cargar Coordenadas", f"Detalle: {str(e)}")

    def _on_detect_particles(self):
        if self.image_2d is None:
            QMessageBox.warning(self, "Atención", "Primero debe cargar una imagen confocal.")
            return

        scale_nm = self.spin_scale.value()
        motor_idx = self.combo_motor.currentIndex()
        include_ext = self.chk_extended.isChecked()
        invert_flag = self.chk_invert_img.isChecked()

        img_to_process = self.image_2d.copy()

        try:
            if motor_idx == 0:
                # Picasso
                min_ng = self.spin_net_grad.value()
                box_sz = self.spin_box_size.value()
                method_str = "gausslq" if self.combo_picasso_method.currentIndex() == 0 else "gaussmle"
                comp_box = self.chk_box_offset.isChecked()
                autoscale = self.chk_picasso_autoscale.isChecked()
                cam_base = self.spin_picasso_baseline.value()
                cam_gain = self.spin_picasso_gain.value()
                cam_sens = self.spin_picasso_sens.value()

                locs = localize_picasso(
                    img_to_process,
                    min_net_gradient=min_ng,
                    box_size=box_sz,
                    method=method_str,
                    compensate_box_offset=comp_box,
                    auto_scale_uint16=autoscale,
                    invert=False,  # La imagen ya fue invertida al cargarse si la casilla estaba activa
                    baseline=cam_base,
                    sensitivity=cam_sens,
                    gain=cam_gain,
                    extended_parameters=include_ext
                )
            else:
                # Trackpy
                diam = self.spin_diameter.value()
                mm = self.spin_minmass.value()
                sep = self.spin_separation.value()
                perc = self.spin_percentile.value()
                noise_sz = self.spin_noise_size.value()

                if self.chk_rl.isChecked():
                    self.image_rl = apply_richardson_lucy(
                        img_to_process,
                        psf_sigma=self.spin_rl_sigma.value(),
                        num_iter=self.spin_rl_iter.value()
                    )
                    img_to_process = self.image_rl
                    if hasattr(self, 'chk_layer_rl'):
                        self.chk_layer_rl.blockSignals(True)
                        self.chk_layer_rl.setChecked(True)
                        self.chk_layer_rl.blockSignals(False)

                locs = localize_trackpy(
                    img_to_process,
                    diameter=diam,
                    minmass=mm,
                    separation=sep if sep > 0 else None,
                    noise_size=noise_sz,
                    percentile=perc,
                    invert=False,  # Ya invertida en display
                    extended_parameters=include_ext
                )

            if locs is None or len(locs) == 0:
                QMessageBox.warning(
                    self,
                    "Sin Detecciones",
                    "No se detectaron partículas con los parámetros actuales.\n"
                    "Pruebe disminuyendo el umbral de detección (Min. Net Gradient o Min Mass)."
                )
                return

            self.locs_df_raw = convert_pixels_to_nm(locs, pixel_size_nm=scale_nm)

            # Filtrar por ROI si está habilitado
            if self.chk_roi_enable.isChecked():
                px_xmin = self.spin_roi_xmin.value()
                px_xmax = self.spin_roi_xmax.value()
                px_ymin = self.spin_roi_ymin.value()
                px_ymax = self.spin_roi_ymax.value()
                if px_xmin > px_xmax: px_xmin, px_xmax = px_xmax, px_xmin
                if px_ymin > px_ymax: px_ymin, px_ymax = px_ymax, px_ymin

                self.locs_df = self.locs_df_raw[
                    (self.locs_df_raw['x'] >= px_xmin) &
                    (self.locs_df_raw['x'] <= px_xmax) &
                    (self.locs_df_raw['y'] >= px_ymin) &
                    (self.locs_df_raw['y'] <= px_ymax)
                ].reset_index(drop=True)
            else:
                self.locs_df = self.locs_df_raw.copy()

            self.kdtree_results = None
            self.cluster_results = None
            self.rdf_results = None
            self.reciprocal_results = None
            self._render_detected_particles_only()

            QMessageBox.information(
                self,
                "Detección Exitosa (Paso 1)",
                f"Se detectaron {len(self.locs_df)} partículas (Total en imagen: {len(self.locs_df_raw)}).\n\n"
                "• Siguiente paso recomendado: '🔍 Detectar Aglomerados y Cadenas' en el Grupo 5.\n"
                "• Para ajustar grilla y vacancias: '📐 Ajustar Grilla y Calcular Vacancias' en el Grupo 6."
            )
        except Exception as e:
            QMessageBox.critical(self, "Error en Detección", f"Detalle: {str(e)}")

    def _update_real_space_analysis(self):
        self._render_detected_particles_only()
        if self.locs_df is not None and len(self.locs_df) > 0:
            self._on_detect_clusters()
            self._on_recalc_grid()

    def _on_recalculate_reciprocal(self):
        if self.locs_df is None or len(self.locs_df) == 0:
            return

        x_nm = self.locs_df['x_nm'].values
        y_nm = self.locs_df['y_nm'].values
        a_nom = self.spin_a_nominal.value()
        idx_bins = self.combo_bins.currentIndex()
        n_bins = 256 if idx_bins == 0 else (512 if idx_bins == 1 else 1024)
        band_bins = self.spin_band.value()
        dc_cut = self.spin_dc_cut.value() if hasattr(self, 'spin_dc_cut') else 0.35
        use_double = self.chk_double_peak.isChecked() if hasattr(self, 'chk_double_peak') else False
        peak_mode = ('amplitude' if self.combo_peak_criterion.currentIndex() == 0 else 'closest_nominal') if hasattr(self, 'combo_peak_criterion') else 'amplitude'

        # Análisis espectral completo con soporte de doble pico y ajuste manual individualizado
        self.reciprocal_results = analyze_reciprocal_space_2d(
            x_nm, y_nm,
            a_nominal=a_nom,
            n_bins=n_bins,
            band_width_bins=band_bins,
            dc_cut_factor=dc_cut,
            use_double_peak=use_double,
            peak_selection_mode=peak_mode,
            peak_tuning=getattr(self, 'peak_tuning_dict', None)
        )

        if hasattr(self, 'chk_anchor_wilson_h0') and self.chk_anchor_wilson_h0.isChecked():
            self.reciprocal_results['analytical_relations'] = compute_analytical_bragg_relations(
                self.reciprocal_results,
                a_nominal=a_nom,
                n_total_particles=len(x_nm),
                anchor_wilson_to_h0=True
            )

        res = self.reciprocal_results

        # Actualizar tarjeta de métricas de red con Jerarquía de Bragg Multi-Orden
        self.lbl_recip_metrics.setText(
            f"═══ ORDEN 1 FUNDAMENTAL ═══\n"
            f"Período: ax={res['a_x']:.2f} nm | ay={res['a_y']:.2f} nm (Δa: {res['anisotropy']:+.2f} nm)\n"
            f"Alturas: Hx={res['Hx']:.2f} | Hy={res['Hy']:.2f}\n"
            f"Coherencia ξ: X={res['xi_x']:.1f} nm | Y={res['xi_y']:.1f} nm\n"
            f"Mosaico Angular Δθ: X={res.get('delta_theta_x_deg', 0.0):.2f}° | Y={res.get('delta_theta_y_deg', 0.0):.2f}°\n\n"
            f"═══ ORDEN CRUZADO (1, 1) DIAGONAL 45° ═══\n"
            f"Período: a_diag={res.get('a_diag', 0.0):.2f} nm | H_diag={res.get('H_diag', 0.0):.2f}\n"
            f"Ratio H_diag / H1: {res.get('ratio_diag', 0.0):.4f}\n"
            f"Cizallamiento (Shear): {res.get('shear_strain_deg', 0.0):.2f}°\n\n"
            f"═══ ORDEN 2 ARMÓNICO (2, 0) / (0, 2) ═══\n"
            f"Período: ax2={res.get('a_x_2nd', 0.0):.2f} nm | ay2={res.get('a_y_2nd', 0.0):.2f} nm\n"
            f"Alturas: H2x={res.get('H_x_2nd', 0.0):.2f} | H2y={res.get('H_y_2nd', 0.0):.2f}\n"
            f"Ratio H2 / H1: {res.get('ratio_order2_x', 0.0):.4f}\n"
            f"Paracristal (FWHM2 / FWHM1): {res.get('paracrystal_ratio_x', 0.0):.2f}\n\n"
            f"═══ FONDO DIFUSO Y SBR ═══\n"
            f"Fondo Incoherente: {res.get('I_diffuse', 0.0):.3f}\n"
            f"Señal / Fondo (SBR): {res.get('sbr_mean', 0.0):.1f}"
        )

        # Visualizar mapa 2D log10(1 + S)
        self.plot_fourier_2d.clear()
        log_S = np.log10(1.0 + res['S'])

        fx = res['fx']
        fy = res['fy']
        img_f = pg.ImageItem(log_S.T)
        img_f.setRect(pg.QtCore.QRectF(fx[0], fy[0], fx[-1] - fx[0], fy[-1] - fy[0]))
        img_f.setColorMap(pg.colormap.get('magma'))
        self.plot_fourier_2d.addItem(img_f)

        f0_x = res['fit_x']['f0']
        f0_y = res['fit_y']['f0']

        # 1. Picos Fundamentales de 1er Orden (cruz verde/cyan)
        peaks_1_x = [f0_x, -f0_x, 0.0, 0.0]
        peaks_1_y = [0.0, 0.0, f0_y, -f0_y]
        scatter_1 = pg.ScatterPlotItem(
            x=peaks_1_x, y=peaks_1_y, size=11,
            pen=pg.mkPen('#a6e3a1', width=2),
            brush=pg.mkBrush(166, 227, 161, 160),
            symbol='+'
        )
        self.plot_fourier_2d.addItem(scatter_1)

        # 2. Picos Diagonales de Orden Cruzado (1, 1) (círculos violetas)
        peaks_d_x = [f0_x, -f0_x, f0_x, -f0_x]
        peaks_d_y = [f0_y, f0_y, -f0_y, -f0_y]
        scatter_d = pg.ScatterPlotItem(
            x=peaks_d_x, y=peaks_d_y, size=9,
            pen=pg.mkPen('#cba6f7', width=1.5),
            brush=pg.mkBrush(203, 166, 247, 140),
            symbol='o'
        )
        self.plot_fourier_2d.addItem(scatter_d)

        # 3. Picos Armónicos de 2do Orden (2, 0) y (0, 2) (cuadrados amarillos)
        peaks_2_x = [2.0 * f0_x, -2.0 * f0_x, 0.0, 0.0]
        peaks_2_y = [0.0, 0.0, 2.0 * f0_y, -2.0 * f0_y]
        scatter_2 = pg.ScatterPlotItem(
            x=peaks_2_x, y=peaks_2_y, size=8,
            pen=pg.mkPen('#f9e2af', width=1.5),
            brush=pg.mkBrush(249, 226, 175, 140),
            symbol='s'
        )
        self.plot_fourier_2d.addItem(scatter_2)

        # Graficar cortes 1D: Eje X
        self.plot_cut_x.clear()
        self.plot_cut_x.plot(fx, res['profile_x'], pen=pg.mkPen('#89dceb', width=2), name='Exp')
        fit_x = res['fit_x']
        if fit_x['success']:
            fit_name = 'Fit Doble Pico X' if fit_x.get('is_double_peak') else 'Fit 1er Orden X'
            self.plot_cut_x.plot(
                fit_x['fit_f'], fit_x['fit_curve'],
                pen=pg.mkPen('#a6e3a1', width=2, style=Qt.PenStyle.DashLine),
                name=fit_name
            )
            # Si es doble pico, graficar componentes individuales y línea base
            if fit_x.get('is_double_peak'):
                if 'comp1_curve' in fit_x and fit_x['comp1_curve'] is not None:
                    self.plot_cut_x.plot(fit_x['fit_f'], fit_x['comp1_curve'], pen=pg.mkPen('#89b4fa', width=1.3, style=Qt.PenStyle.DotLine), name='Pico 1')
                if 'comp2_curve' in fit_x and fit_x['comp2_curve'] is not None:
                    self.plot_cut_x.plot(fit_x['fit_f'], fit_x['comp2_curve'], pen=pg.mkPen('#fab387', width=1.3, style=Qt.PenStyle.DotLine), name='Pico 2')
                if 'baseline_curve' in fit_x and fit_x['baseline_curve'] is not None:
                    self.plot_cut_x.plot(fit_x['fit_f'], fit_x['baseline_curve'], pen=pg.mkPen('#6c7086', width=1.0, style=Qt.PenStyle.DotLine), name='Línea Base')

        if res.get('fit_x_2nd') and res['fit_x_2nd']['success']:
            fit_x_2nd = res['fit_x_2nd']
            fit_name_2x = 'Fit Doble 2do Orden X' if fit_x_2nd.get('is_double_peak') else 'Fit 2do Orden X'
            self.plot_cut_x.plot(
                fit_x_2nd['fit_f'], fit_x_2nd['fit_curve'],
                pen=pg.mkPen('#f9e2af', width=1.8, style=Qt.PenStyle.DashLine),
                name=fit_name_2x
            )
            if fit_x_2nd.get('is_double_peak'):
                if 'comp1_curve' in fit_x_2nd and fit_x_2nd['comp1_curve'] is not None:
                    self.plot_cut_x.plot(fit_x_2nd['fit_f'], fit_x_2nd['comp1_curve'], pen=pg.mkPen('#89b4fa', width=1.3, style=Qt.PenStyle.DotLine), name='Pico 1 (2X)')
                if 'comp2_curve' in fit_x_2nd and fit_x_2nd['comp2_curve'] is not None:
                    self.plot_cut_x.plot(fit_x_2nd['fit_f'], fit_x_2nd['comp2_curve'], pen=pg.mkPen('#fab387', width=1.3, style=Qt.PenStyle.DotLine), name='Pico 2 (2X)')
                if 'baseline_curve' in fit_x_2nd and fit_x_2nd['baseline_curve'] is not None:
                    self.plot_cut_x.plot(fit_x_2nd['fit_f'], fit_x_2nd['baseline_curve'], pen=pg.mkPen('#6c7086', width=1.0, style=Qt.PenStyle.DotLine), name='Línea Base (2X)')

        # Graficar cortes 1D: Eje Y
        self.plot_cut_y.clear()
        self.plot_cut_y.plot(fy, res['profile_y'], pen=pg.mkPen('#cba6f7', width=2), name='Exp')
        fit_y = res['fit_y']
        if fit_y['success']:
            fit_name_y = 'Fit Doble Pico Y' if fit_y.get('is_double_peak') else 'Fit 1er Orden Y'
            self.plot_cut_y.plot(
                fit_y['fit_f'], fit_y['fit_curve'],
                pen=pg.mkPen('#a6e3a1', width=2, style=Qt.PenStyle.DashLine),
                name=fit_name_y
            )
            if fit_y.get('is_double_peak'):
                if 'comp1_curve' in fit_y and fit_y['comp1_curve'] is not None:
                    self.plot_cut_y.plot(fit_y['fit_f'], fit_y['comp1_curve'], pen=pg.mkPen('#89b4fa', width=1.3, style=Qt.PenStyle.DotLine), name='Pico 1')
                if 'comp2_curve' in fit_y and fit_y['comp2_curve'] is not None:
                    self.plot_cut_y.plot(fit_y['fit_f'], fit_y['comp2_curve'], pen=pg.mkPen('#fab387', width=1.3, style=Qt.PenStyle.DotLine), name='Pico 2')
                if 'baseline_curve' in fit_y and fit_y['baseline_curve'] is not None:
                    self.plot_cut_y.plot(fit_y['fit_f'], fit_y['baseline_curve'], pen=pg.mkPen('#6c7086', width=1.0, style=Qt.PenStyle.DotLine), name='Línea Base')

        if res.get('fit_y_2nd') and res['fit_y_2nd']['success']:
            fit_y_2nd = res['fit_y_2nd']
            fit_name_2y = 'Fit Doble 2do Orden Y' if fit_y_2nd.get('is_double_peak') else 'Fit 2do Orden Y'
            self.plot_cut_y.plot(
                fit_y_2nd['fit_f'], fit_y_2nd['fit_curve'],
                pen=pg.mkPen('#f9e2af', width=1.8, style=Qt.PenStyle.DashLine),
                name=fit_name_2y
            )
            if fit_y_2nd.get('is_double_peak'):
                if 'comp1_curve' in fit_y_2nd and fit_y_2nd['comp1_curve'] is not None:
                    self.plot_cut_y.plot(fit_y_2nd['fit_f'], fit_y_2nd['comp1_curve'], pen=pg.mkPen('#89b4fa', width=1.3, style=Qt.PenStyle.DotLine), name='Pico 1 (2Y)')
                if 'comp2_curve' in fit_y_2nd and fit_y_2nd['comp2_curve'] is not None:
                    self.plot_cut_y.plot(fit_y_2nd['fit_f'], fit_y_2nd['comp2_curve'], pen=pg.mkPen('#fab387', width=1.3, style=Qt.PenStyle.DotLine), name='Pico 2 (2Y)')
                if 'baseline_curve' in fit_y_2nd and fit_y_2nd['baseline_curve'] is not None:
                    self.plot_cut_y.plot(fit_y_2nd['fit_f'], fit_y_2nd['baseline_curve'], pen=pg.mkPen('#6c7086', width=1.0, style=Qt.PenStyle.DotLine), name='Línea Base (2Y)')

        # Graficar cortes 1D: Diagonal 45°
        if hasattr(self, 'plot_cut_diag'):
            self.plot_cut_diag.clear()
            self.plot_cut_diag.plot(res['f_diag'], res['profile_diag'], pen=pg.mkPen('#f38ba8', width=2), name='Exp Diag')
            if res.get('fit_diag') and res['fit_diag']['success']:
                fit_diag = res['fit_diag']
                fit_name_d = 'Fit Doble (1,1)' if fit_diag.get('is_double_peak') else 'Fit (1,1)'
                self.plot_cut_diag.plot(
                    fit_diag['fit_f'], fit_diag['fit_curve'],
                    pen=pg.mkPen('#cba6f7', width=1.8, style=Qt.PenStyle.DashLine),
                    name=fit_name_d
                )
                if fit_diag.get('is_double_peak'):
                    if 'comp1_curve' in fit_diag and fit_diag['comp1_curve'] is not None:
                        self.plot_cut_diag.plot(fit_diag['fit_f'], fit_diag['comp1_curve'], pen=pg.mkPen('#89b4fa', width=1.3, style=Qt.PenStyle.DotLine), name='Pico 1 (Diag)')
                    if 'comp2_curve' in fit_diag and fit_diag['comp2_curve'] is not None:
                        self.plot_cut_diag.plot(fit_diag['fit_f'], fit_diag['comp2_curve'], pen=pg.mkPen('#fab387', width=1.3, style=Qt.PenStyle.DotLine), name='Pico 2 (Diag)')
                    if 'baseline_curve' in fit_diag and fit_diag['baseline_curve'] is not None:
                        self.plot_cut_diag.plot(fit_diag['fit_f'], fit_diag['baseline_curve'], pen=pg.mkPen('#6c7086', width=1.0, style=Qt.PenStyle.DotLine), name='Línea Base (Diag)')

        # Restaurar reglas visuales del pico seleccionado si están activas
        if hasattr(self, 'chk_peak_manual_roi') and self.chk_peak_manual_roi.isChecked():
            if self._current_tuned_plot is not None:
                for line in [self.line_peak_fmin, self.line_peak_fmax, self.line_peak_bg]:
                    if line not in self._current_tuned_plot.items():
                        self._current_tuned_plot.addItem(line)

        self._update_analytical_panels_and_plots(res)
        self._update_metrics_table()

    def _on_anchor_wilson_toggled(self, checked: bool):
        """Alterna el anclaje del intercepto de Wilson a ln(H0) y actualiza al vuelo los paneles."""
        if self.reciprocal_results is not None:
            a_nom = self.spin_a_nominal.value() if hasattr(self, 'spin_a_nominal') else 450.0
            x_nm = getattr(self, 'current_x_nm', None)
            n_tot = len(x_nm) if x_nm is not None else None
            self.reciprocal_results['analytical_relations'] = compute_analytical_bragg_relations(
                self.reciprocal_results,
                a_nominal=a_nom,
                n_total_particles=n_tot,
                anchor_wilson_to_h0=checked
            )
            self._update_analytical_panels_and_plots(self.reciprocal_results)
            self._update_metrics_table()

    def _update_analytical_panels_and_plots(self, res: Dict[str, Any]):
        """
        Actualiza las tarjetas de resultados analíticos preliminares y la batería
        de 4 gráficos de diagnóstico (Wilson Plot, Decaimiento Debye-Waller,
        Comparativa de Estabilidad y Diagnóstico Paracristalino).
        """
        ana = res.get('analytical_relations')
        if not ana:
            return

        # ── 1. Actualización de Tarjetas Numéricas ───────────────────────────
        # Card 1: H2 / H1 (Estándar de Oro)
        s_h2h1 = ana.get('sigma_h2h1', 0.0)
        s_h2h1_x = ana.get('sigma_h2h1_x', 0.0)
        s_h2h1_y = ana.get('sigma_h2h1_y', 0.0)
        r_21 = ana.get('ratio_21_mean', 0.0)
        r_21_x = ana.get('ratio_21_x', 0.0)
        r_21_y = ana.get('ratio_21_y', 0.0)
        h1_x = ana.get('H1_x', 0.0)
        h1_y = ana.get('H1_y', 0.0)
        h2_x = ana.get('H2_x', 0.0)
        h2_y = ana.get('H2_y', 0.0)
        self.lbl_card_h2h1.setText(
            f"<b>σ (H₂ / H₁): {s_h2h1:.2f} nm</b><br>"
            f"<span style='color: #a6adc8; font-size: 10px;'>"
            f"Estándar de Oro (Cancela p y N)<br>"
            f"<b>X:</b> H₂x/H₁x = {r_21_x:.3f} (H₁x={h1_x:.2e}, H₂x={h2_x:.2e}) ⇒ <b>σ_x = {s_h2h1_x:.2f} nm</b><br>"
            f"<b>Y:</b> H₂y/H₁y = {r_21_y:.3f} (H₁y={h1_y:.2e}, H₂y={h2_y:.2e}) ⇒ <b>σ_y = {s_h2h1_y:.2f} nm</b><br>"
            f"Fórmula: σ = (a / 2π√3) √(ln(H₁/H₂))</span>"
        )

        # Card 2: H_diag / H1 (Coherencia 2D)
        s_diag = ana.get('sigma_diag', 0.0)
        s_diag_x = ana.get('sigma_diag_x', 0.0)
        s_diag_y = ana.get('sigma_diag_y', 0.0)
        r_diag = ana.get('ratio_diag', 0.0)
        r_diag_x = ana.get('ratio_diag_x', 0.0)
        r_diag_y = ana.get('ratio_diag_y', 0.0)
        h_diag = ana.get('H_diag', 0.0)
        self.lbl_card_diag.setText(
            f"<b>σ (H_diag / H₁): {s_diag:.2f} nm</b><br>"
            f"<span style='color: #a6adc8; font-size: 10px;'>"
            f"Coherencia 2D (H_diag = {h_diag:.2e})<br>"
            f"<b>X:</b> H_diag/H₁x = {r_diag_x:.3f} ⇒ <b>σ_diag,x = {s_diag_x:.2f} nm</b><br>"
            f"<b>Y:</b> H_diag/H₁y = {r_diag_y:.3f} ⇒ <b>σ_diag,y = {s_diag_y:.2f} nm</b><br>"
            f"Fórmula: σ = (a / 2π) √(ln(H₁/H_diag))</span>"
        )

        # Card 3: H0 / H1 y H1 / H0 (Inestable)
        s_10 = ana.get('sigma_h1h0', 0.0)
        s_10_x = ana.get('sigma_h1h0_x', 0.0)
        s_10_y = ana.get('sigma_h1h0_y', 0.0)
        r_0_1x = ana.get('ratio_0_1x', 0.0)
        r_0_1y = ana.get('ratio_0_1y', 0.0)
        r_10_x = ana.get('ratio_10_x', 0.0)
        r_10_y = ana.get('ratio_10_y', 0.0)
        h0 = ana.get('H0', 0.0)
        self.lbl_card_h1h0.setText(
            f"<b>σ (H₀ / H₁): {s_10:.2f} nm</b> <span style='color: #f38ba8; font-weight: bold; font-size: 10px;'>[⚠️ INESTABLE]</span><br>"
            f"<span style='color: #a6adc8; font-size: 10px;'>"
            f"Razón frente a DC Central (H₀ = {h0:.2e})<br>"
            f"<b>X:</b> H₀/H₁x = {r_0_1x:.2f} (H₁x/H₀ = {r_10_x:.4f}) ⇒ <b>σ_x = {s_10_x:.2f} nm</b><br>"
            f"<b>Y:</b> H₀/H₁y = {r_0_1y:.2f} (H₁y/H₀ = {r_10_y:.4f}) ⇒ <b>σ_y = {s_10_y:.2f} nm</b><br>"
            f"Sensible a autofluorescencia, haz directo y N</span>"
        )

        # Card 4: Gráfico de Wilson
        is_anchored = ana.get('anchor_wilson_to_h0', False)
        mode_tag = " [c=ln(H₀)]" if is_anchored else ""
        s_w = ana.get('sigma_wilson', 0.0)
        s_wx = ana.get('sigma_wilson_x', s_w)
        s_wy = ana.get('sigma_wilson_y', s_w)
        r2_w = ana.get('r_squared_wilson', 0.0)
        slope_w = ana.get('slope_wilson', 0.0)
        m_x = ana.get('slope_wilson_x', slope_w)
        m_y = ana.get('slope_wilson_y', slope_w)
        c_x = ana.get('intercept_wilson_x', ana.get('intercept_wilson', 0.0))
        c_y = ana.get('intercept_wilson_y', ana.get('intercept_wilson', 0.0))
        w_concl = ana.get('wilson_data', {}).get('conclusions', {})
        aniso_str = w_concl.get('anisotropy_text', '')
        self.lbl_card_wilson.setText(
            f"<b>Wilson Plot{mode_tag}: σ_x = {s_wx:.2f} nm | σ_y = {s_wy:.2f} nm</b> (Global R²: {r2_w:.3f})<br>"
            f"<span style='color: #a6adc8; font-size: 10px;'>"
            f"<b>Eje X:</b> m_x = {m_x:.2e} | c_x = {c_x:.2f} (I₀,x = {np.exp(c_x):.2e})<br>"
            f"<b>Eje Y:</b> m_y = {m_y:.2e} | c_y = {c_y:.2f} (I₀,y = {np.exp(c_y):.2e})<br>"
            f"<b>Conclusiones:</b> {aniso_str}</span>"
        )

        # Card 5: Diagnóstico Paracristalino
        para = ana.get('paracrystal_diagnosis', {})
        r_fwhm = para.get('ratio_fwhm', 1.0)
        r_fx = para.get('ratio_fwhm_x', r_fwhm)
        r_fy = para.get('ratio_fwhm_y', r_fwhm)
        type_x = para.get('disorder_type_x', 'Tipo I')
        type_y = para.get('disorder_type_y', 'Tipo I')
        d_type = para.get('disorder_type', 'Pendiente')
        d_desc = para.get('description', '')
        is_type_1 = para.get('is_type_1', True)
        color_type = '#a6e3a1' if is_type_1 else '#f9e2af'
        self.lbl_card_paracrystal.setText(
            f"<b>Diagnóstico: <span style='color: {color_type};'>{d_type}</span></b><br>"
            f"<span style='color: #a6adc8; font-size: 10px;'>"
            f"FWHM₂x/FWHM₁x = {r_fx:.2f} ({type_x}) | FWHM₂y/FWHM₁y = {r_fy:.2f} ({type_y})<br>"
            f"{d_desc}</span>"
        )

        # ── 2. Gráfico 1: Gráfico de Wilson (ln(H) vs |G|² Anisótropo X / Y) ──
        if hasattr(self, 'plot_wilson'):
            self.plot_wilson.clear()
            if self.plot_wilson.plotItem.legend is None:
                self.plot_wilson.addLegend(offset=(10, 10))
            else:
                self.plot_wilson.plotItem.legend.clear()

            w_data = ana.get('wilson_data', {})
            w_x = w_data.get('x', {})
            w_y = w_data.get('y', {})
            w_diag = w_data.get('diag', {})

            # 1. Dimensión X: Recta de ajuste y picos
            fit_gx = w_x.get('fit_g_sq')
            fit_hx = w_x.get('fit_ln_h')
            gx = w_x.get('g_sq')
            hx = w_x.get('ln_h')
            if fit_gx is not None and fit_hx is not None and len(fit_gx) > 0:
                self.plot_wilson.plot(
                    fit_gx, fit_hx,
                    pen=pg.mkPen('#89b4fa', width=2, style=Qt.PenStyle.DashLine),
                    name=f'Ajuste X{mode_tag}: m={m_x:.2e}, c={c_x:.2f} (σ_x={s_wx:.2f} nm)'
                )
            if gx is not None and hx is not None and len(gx) > 0:
                scatter_wx = pg.ScatterPlotItem(
                    x=gx, y=hx, size=11,
                    pen=pg.mkPen('#1e1e2e', width=1.5),
                    brush=pg.mkBrush('#89b4fa'),
                    symbol='o',
                    name='Picos X: (1,0) y (2,0)'
                )
                self.plot_wilson.addItem(scatter_wx)
                names_x = w_x.get('names', ['(1,0) X', '(2,0) X'])
                for g, h, nm in zip(gx, hx, names_x):
                    ti = pg.TextItem(text=f" {nm}", color='#89b4fa', anchor=(0, 0.5))
                    ti.setPos(g, h)
                    self.plot_wilson.addItem(ti)

            # 2. Dimensión Y: Recta de ajuste y picos
            fit_gy = w_y.get('fit_g_sq')
            fit_hy = w_y.get('fit_ln_h')
            gy = w_y.get('g_sq')
            hy = w_y.get('ln_h')
            if fit_gy is not None and fit_hy is not None and len(fit_gy) > 0:
                self.plot_wilson.plot(
                    fit_gy, fit_hy,
                    pen=pg.mkPen('#fab387', width=2, style=Qt.PenStyle.DashLine),
                    name=f'Ajuste Y{mode_tag}: m={m_y:.2e}, c={c_y:.2f} (σ_y={s_wy:.2f} nm)'
                )
            if gy is not None and hy is not None and len(gy) > 0:
                scatter_wy = pg.ScatterPlotItem(
                    x=gy, y=hy, size=11,
                    pen=pg.mkPen('#1e1e2e', width=1.5),
                    brush=pg.mkBrush('#fab387'),
                    symbol='s',
                    name='Picos Y: (0,1) y (0,2)'
                )
                self.plot_wilson.addItem(scatter_wy)
                names_y = w_y.get('names', ['(0,1) Y', '(0,2) Y'])
                for g, h, nm in zip(gy, hy, names_y):
                    ti = pg.TextItem(text=f" {nm}", color='#fab387', anchor=(0, 0.5))
                    ti.setPos(g, h)
                    self.plot_wilson.addItem(ti)

            # 3. Punto Diagonal (1, 1) como testigo de coherencia 2D
            g_diag = w_diag.get('g_sq')
            h_diag = w_diag.get('ln_h')
            if g_diag is not None and h_diag is not None:
                scatter_wdiag = pg.ScatterPlotItem(
                    x=[g_diag], y=[h_diag], size=12,
                    pen=pg.mkPen('#1e1e2e', width=1.5),
                    brush=pg.mkBrush('#a6e3a1'),
                    symbol='d',
                    name='Pico Diag (1,1)'
                )
                self.plot_wilson.addItem(scatter_wdiag)
                ti_d = pg.TextItem(text=" (1,1) Diag", color='#a6e3a1', anchor=(0, 0.5))
                ti_d.setPos(g_diag, h_diag)
                self.plot_wilson.addItem(ti_d)

            # 4. Conclusiones Físicas deducidas del Wilson Plot
            concl_dict = w_data.get('conclusions', {})
            concl_lines = []
            if 'anisotropy_text' in concl_dict:
                concl_lines.append(f"• {concl_dict['anisotropy_text']}")
            if 'intercept_text' in concl_dict:
                concl_lines.append(f"• {concl_dict['intercept_text']}")
            if 'background_text' in concl_dict:
                concl_lines.append(f"• {concl_dict['background_text']}")
            if 'vacancies_text' in concl_dict:
                concl_lines.append(f"• {concl_dict['vacancies_text']}")
            if concl_lines and gx is not None and len(gx) > 0:
                concl_box_text = "\n".join(concl_lines)
                ti_concl = pg.TextItem(
                    text=f"Conclusiones de Regresión e Interceptos:\n{concl_box_text}",
                    color='#cdd6f4',
                    border=pg.mkPen('#45475a', width=1),
                    fill=pg.mkBrush('#181825ee'),
                    anchor=(0, 0)
                )
                min_g = 0.0
                max_h = max(float(np.max(hx)), float(np.max(hy))) if hy is not None and len(hy) > 0 else float(np.max(hx))
                ti_concl.setPos(min_g, max_h)
                self.plot_wilson.addItem(ti_concl)

            self.plot_wilson.enableAutoRange()

        # ── 3. Gráfico 2: Decaimiento Multiórden Debye-Waller (Ejes X e Y) ────
        if hasattr(self, 'plot_dw_decay'):
            self.plot_dw_decay.clear()
            if self.plot_dw_decay.plotItem.legend is None:
                self.plot_dw_decay.addLegend(offset=(10, 10))
            else:
                self.plot_dw_decay.plotItem.legend.clear()

            dw_data = ana.get('debye_waller_curve', {})
            dw_x = dw_data.get('x', {})
            dw_y = dw_data.get('y', {})
            dw_diag = dw_data.get('diag', {})

            # Eje X: Curva teórica y puntos experimentales
            qx = dw_x.get('q_norm')
            hx_th = dw_x.get('H_theory')
            pts_qx = dw_x.get('points_q')
            pts_hx = dw_x.get('points_H')
            if qx is not None and hx_th is not None:
                self.plot_dw_decay.plot(
                    qx, hx_th,
                    pen=pg.mkPen('#89b4fa', width=2),
                    name=f'Teoría DW X (σ_x={s_h2h1_x:.2f} nm)'
                )
            if pts_qx is not None and pts_hx is not None:
                scatter_dw_x = pg.ScatterPlotItem(
                    x=pts_qx, y=pts_hx, size=11,
                    pen=pg.mkPen('#1e1e2e', width=1.5),
                    brush=pg.mkBrush('#89b4fa'),
                    symbol='o',
                    name='Exp. X: (1,0) y (2,0)'
                )
                self.plot_dw_decay.addItem(scatter_dw_x)
                for q, h, lbl in zip(pts_qx, pts_hx, dw_x.get('labels', ['(1,0) X', '(2,0) X'])):
                    ti = pg.TextItem(text=f" {lbl} ({h:.2f})", color='#89b4fa', anchor=(0, 0.5))
                    ti.setPos(q, h)
                    self.plot_dw_decay.addItem(ti)

            # Eje Y: Curva teórica y puntos experimentales
            qy = dw_y.get('q_norm')
            hy_th = dw_y.get('H_theory')
            pts_qy = dw_y.get('points_q')
            pts_hy = dw_y.get('points_H')
            if qy is not None and hy_th is not None:
                self.plot_dw_decay.plot(
                    qy, hy_th,
                    pen=pg.mkPen('#fab387', width=2, style=Qt.PenStyle.DashLine),
                    name=f'Teoría DW Y (σ_y={s_h2h1_y:.2f} nm)'
                )
            if pts_qy is not None and pts_hy is not None:
                scatter_dw_y = pg.ScatterPlotItem(
                    x=pts_qy, y=pts_hy, size=11,
                    pen=pg.mkPen('#1e1e2e', width=1.5),
                    brush=pg.mkBrush('#fab387'),
                    symbol='s',
                    name='Exp. Y: (0,1) y (0,2)'
                )
                self.plot_dw_decay.addItem(scatter_dw_y)
                for q, h, lbl in zip(pts_qy, pts_hy, dw_y.get('labels', ['(0,1) Y', '(0,2) Y'])):
                    ti = pg.TextItem(text=f" {lbl} ({h:.2f})", color='#fab387', anchor=(0, 0.5))
                    ti.setPos(q, h)
                    self.plot_dw_decay.addItem(ti)

            # Punto Diagonal (1, 1) normalizado
            pts_qdiag = dw_diag.get('points_q')
            pts_hdiag = dw_diag.get('points_H')
            if pts_qdiag is not None and pts_hdiag is not None:
                scatter_dw_diag = pg.ScatterPlotItem(
                    x=pts_qdiag, y=pts_hdiag, size=12,
                    pen=pg.mkPen('#1e1e2e', width=1.5),
                    brush=pg.mkBrush('#a6e3a1'),
                    symbol='d',
                    name='Diagonal (1,1) / H₁x,y'
                )
                self.plot_dw_decay.addItem(scatter_dw_diag)
                for q, h, lbl in zip(pts_qdiag, pts_hdiag, dw_diag.get('labels', ['Diag / H₁x', 'Diag / H₁y'])):
                    ti = pg.TextItem(text=f" {lbl} ({h:.2f})", color='#a6e3a1', anchor=(0, 0.5))
                    ti.setPos(q, h)
                    self.plot_dw_decay.addItem(ti)

            self.plot_dw_decay.enableAutoRange()

        # ── 4. Gráfico 3: Comparativa de Estabilidad de Ratios (X e Y) ────────
        if hasattr(self, 'plot_ratio_stability'):
            self.plot_ratio_stability.clear()
            methods = [
                'H₂/H₁ X', 'H₂/H₁ Y',
                'Diag/H₁ X', 'Diag/H₁ Y',
                'Wilson X', 'Wilson Y',
                'H₀/H₁ X', 'H₀/H₁ Y'
            ]
            raw_sigmas = [
                s_h2h1_x, s_h2h1_y,
                s_diag_x, s_diag_y,
                s_wx, s_wy,
                s_10_x, s_10_y
            ]
            sigmas = [0.0 if np.isnan(s) else max(0.0, float(s)) for s in raw_sigmas]
            colors = [
                '#89b4fa', '#fab387',
                '#74c7ec', '#f9e2af',
                '#b4befe', '#eba0ac',
                '#f38ba8', '#f38ba8'
            ]

            x_coords = np.arange(len(methods), dtype=float)
            brushes = [pg.mkBrush(c) for c in colors]
            bg = pg.BarGraphItem(x=x_coords, height=sigmas, width=0.55, brushes=brushes)
            self.plot_ratio_stability.addItem(bg)

            # Eje con nombres de los métodos
            ax = self.plot_ratio_stability.getAxis('bottom')
            ax.setTicks([[(i, methods[i]) for i in range(len(methods))]])

            # Valores numéricos sobre las barras
            for i, s in enumerate(sigmas):
                ti = pg.TextItem(text=f"{s:.1f} nm", color='#cdd6f4', anchor=(0.5, 1.2))
                ti.setPos(i, s)
                self.plot_ratio_stability.addItem(ti)

            # Línea de referencia Monte Carlo (si está disponible)
            if self.mc_results is not None and 's_prom' in self.mc_results:
                s_mc = self.mc_results['s_prom']
                line_mc = pg.InfiniteLine(
                    pos=s_mc, angle=0,
                    pen=pg.mkPen('#fab387', width=1.8, style=Qt.PenStyle.DashLine),
                    label=f'Ref MC: {s_mc:.1f} nm',
                    labelOpts={'color': '#fab387', 'position': 0.85}
                )
                self.plot_ratio_stability.addItem(line_mc)
            elif self.kdtree_results is not None and 'sigma_pos' in self.kdtree_results:
                s_kd = self.kdtree_results['sigma_pos']
                line_kd = pg.InfiniteLine(
                    pos=s_kd, angle=0,
                    pen=pg.mkPen('#cba6f7', width=1.5, style=Qt.PenStyle.DotLine),
                    label=f'Ref KDTree: {s_kd:.1f} nm',
                    labelOpts={'color': '#cba6f7', 'position': 0.85}
                )
                self.plot_ratio_stability.addItem(line_kd)
            self.plot_ratio_stability.enableAutoRange()

        # ── 5. Gráfico 4: Diagnóstico de Ancho Radial (Hosemann en X e Y) ─────
        if hasattr(self, 'plot_fwhm_paracrystal'):
            self.plot_fwhm_paracrystal.clear()
            if self.plot_fwhm_paracrystal.plotItem.legend is None:
                self.plot_fwhm_paracrystal.addLegend(offset=(10, 10))
            else:
                self.plot_fwhm_paracrystal.plotItem.legend.clear()

            f1x = para.get('fwhm1_x', 0.0)
            f2x = para.get('fwhm2_x', 0.0)
            f1y = para.get('fwhm1_y', 0.0)
            f2y = para.get('fwhm2_y', 0.0)

            m_dense = np.linspace(0.8, 2.2, 50)
            ax4 = self.plot_fwhm_paracrystal.getAxis('bottom')
            ax4.setTicks([[(1, 'm = 1 (10 / 01)'), (2, 'm = 2 (20 / 02)')]])

            # 1. Dimensión X
            if f1x > 0:
                m_x_pts = np.array([1.0, 2.0])
                fwhm_x_pts = np.array([f1x, f2x if f2x > 0 else f1x])
                sc_fx = pg.ScatterPlotItem(
                    x=m_x_pts, y=fwhm_x_pts, size=11,
                    pen=pg.mkPen('#1e1e2e', width=1.5),
                    brush=pg.mkBrush('#89b4fa'),
                    symbol='o',
                    name=f'FWHM Exp. X (r={r_fx:.2f})'
                )
                self.plot_fwhm_paracrystal.addItem(sc_fx)

                # Modelo Tipo I X: Debye-Waller Puro (Scherrer FWHM constante)
                self.plot_fwhm_paracrystal.plot(
                    m_dense, np.full_like(m_dense, f1x),
                    pen=pg.mkPen('#89b4fa', width=1.8, style=Qt.PenStyle.DashLine),
                    name='Tipo I X (DW cte)'
                )
                # Modelo Tipo II X: Paracristal de Hosemann (FWHM ~ m²)
                self.plot_fwhm_paracrystal.plot(
                    m_dense, f1x * (m_dense ** 2),
                    pen=pg.mkPen('#89b4fa', width=1.5, style=Qt.PenStyle.DotLine),
                    name='Tipo II X (Hosemann m²)'
                )

                ti_1x = pg.TextItem(text=f" FWHM₁x={f1x:.4f} nm⁻¹", color='#89b4fa', anchor=(0, 0.5))
                ti_1x.setPos(1.0, f1x)
                self.plot_fwhm_paracrystal.addItem(ti_1x)

                if f2x > 0:
                    ti_2x = pg.TextItem(text=f" FWHM₂x={f2x:.4f} nm⁻¹", color='#89b4fa', anchor=(0, 0.5))
                    ti_2x.setPos(2.0, f2x)
                    self.plot_fwhm_paracrystal.addItem(ti_2x)

            # 2. Dimensión Y
            if f1y > 0:
                m_y_pts = np.array([1.0, 2.0])
                fwhm_y_pts = np.array([f1y, f2y if f2y > 0 else f1y])
                sc_fy = pg.ScatterPlotItem(
                    x=m_y_pts, y=fwhm_y_pts, size=11,
                    pen=pg.mkPen('#1e1e2e', width=1.5),
                    brush=pg.mkBrush('#fab387'),
                    symbol='s',
                    name=f'FWHM Exp. Y (r={r_fy:.2f})'
                )
                self.plot_fwhm_paracrystal.addItem(sc_fy)

                # Modelo Tipo I Y: Debye-Waller Puro (Scherrer FWHM constante)
                self.plot_fwhm_paracrystal.plot(
                    m_dense, np.full_like(m_dense, f1y),
                    pen=pg.mkPen('#fab387', width=1.8, style=Qt.PenStyle.DashLine),
                    name='Tipo I Y (DW cte)'
                )
                # Modelo Tipo II Y: Paracristal de Hosemann (FWHM ~ m²)
                self.plot_fwhm_paracrystal.plot(
                    m_dense, f1y * (m_dense ** 2),
                    pen=pg.mkPen('#fab387', width=1.5, style=Qt.PenStyle.DotLine),
                    name='Tipo II Y (Hosemann m²)'
                )

                ti_1y = pg.TextItem(text=f" FWHM₁y={f1y:.4f} nm⁻¹", color='#fab387', anchor=(0, 0.5))
                ti_1y.setPos(1.0, f1y)
                self.plot_fwhm_paracrystal.addItem(ti_1y)

                if f2y > 0:
                    ti_2y = pg.TextItem(text=f" FWHM₂y={f2y:.4f} nm⁻¹", color='#fab387', anchor=(0, 0.5))
                    ti_2y.setPos(2.0, f2y)
                    self.plot_fwhm_paracrystal.addItem(ti_2y)

            self.plot_fwhm_paracrystal.enableAutoRange()

    def _on_propagate_to_mc(self):
        if self.reciprocal_results is None:
            QMessageBox.warning(self, "Atención", "Primero debe calcular el espacio recíproco.")
            return

        res = self.reciprocal_results
        a_mean = res['a_mean']
        a_x = res.get('a_x', a_mean)
        a_y = res.get('a_y', a_mean)
        aniso = abs(a_x - a_y)

        self.spin_mc_ax.setValue(a_x)
        self.spin_mc_ay.setValue(a_y)
        is_aniso = aniso > 1.0
        self.chk_mc_anisotropy.setChecked(is_aniso)
        self.spin_mc_ay.setEnabled(is_aniso)

        self.spin_mc_n.setValue(self.spin_n_side.value())

        if self.kdtree_results is not None:
            self.spin_mc_vac.setValue(self.kdtree_results['f_vac_percent'])

        # Calcular y propagar el ancho físico de la banda transversal en nm^-1
        band_bins = self.spin_band.value()
        idx_bins = self.combo_bins.currentIndex()
        n_bins = 256 if idx_bins == 0 else (512 if idx_bins == 1 else 1024)
        fmax = 2.5 / a_mean
        delta_f = (2.0 * fmax) / n_bins
        band_nm = band_bins * delta_f
        self.spin_mc_band.setValue(band_nm)

        self.tabs.setCurrentIndex(2)
        aniso_str = f"- Anisotropía detectada: ax={a_x:.2f} nm, ay={a_y:.2f} nm (Δ={aniso:.2f} nm)\n" if is_aniso else f"- Período a_mean = {a_mean:.2f} nm (Isotrópico)\n"
        QMessageBox.information(
            self,
            "Parámetros Propagados",
            f"Parámetros transferidos a Monte Carlo:\n"
            f"{aniso_str}"
            f"- Sitios N x N = {self.spin_n_side.value()}\n"
            f"- Vacancias = {self.spin_mc_vac.value():.1f}%\n"
            f"- Banda Transversal = ±{band_nm*1000.0:.3f} ×10⁻³ nm⁻¹"
        )

    def _on_run_monte_carlo(self):
        n_side = self.spin_mc_n.value()
        ax = self.spin_mc_ax.value()
        ay = self.spin_mc_ay.value() if self.chk_mc_anisotropy.isChecked() else ax
        f_vac = self.spin_mc_vac.value() / 100.0
        s_max = self.spin_mc_smax.value()
        n_steps = self.spin_mc_steps.value()
        n_iter = self.spin_mc_iter.value()
        band_w = self.spin_mc_band.value()

        # Densidad de puntos en pico de Bragg
        bragg_idx = self.combo_mc_bragg.currentIndex()
        n_bragg = 81 if bragg_idx == 0 else (121 if bragg_idx == 1 else 31)

        self.btn_run_mc.setEnabled(False)
        self.btn_cancel_mc.setEnabled(True)
        self.progress_mc.setValue(0)
        self.lbl_mc_status.setText("Simulando réplicas Monte Carlo en segundo plano...")

        self.mc_worker = MonteCarloWorker(
            n_side=n_side,
            a=ax,
            f_vac=f_vac,
            sigma_min=0.0,
            sigma_max=s_max,
            n_sigma_steps=n_steps,
            iterations_per_step=n_iter,
            a_y=ay if self.chk_mc_anisotropy.isChecked() else None,
            n_bragg_pts=n_bragg,
            band_width_nm=band_w,
            n_transversal_pts=5
        )
        self.mc_worker.progress_signal.connect(self._on_mc_progress)
        self.mc_worker.finished_signal.connect(self._on_mc_finished)
        self.mc_worker.error_signal.connect(self._on_mc_error)
        self.mc_worker.start()

    def _on_mc_progress(self, step: int, total: int, pct: float):
        self.progress_mc.setValue(int(pct))
        self.lbl_mc_status.setText(f"Avance: {step}/{total} ejecuciones ({pct:.1f}%)")

    def _on_mc_finished(self, results: Dict[str, Any]):
        self.mc_results = results
        self.btn_run_mc.setEnabled(True)
        self.btn_cancel_mc.setEnabled(False)
        self.progress_mc.setValue(100)
        self.lbl_mc_status.setText("Simulación Monte Carlo completada exitosamente.")

        self._plot_debye_waller()
        if self.reciprocal_results is not None:
            self._update_analytical_panels_and_plots(self.reciprocal_results)
        self._update_metrics_table()

    def _on_mc_error(self, err_msg: str):
        self.btn_run_mc.setEnabled(True)
        self.btn_cancel_mc.setEnabled(False)
        self.lbl_mc_status.setText("Error en la simulación.")
        QMessageBox.critical(self, "Error Monte Carlo", f"Ocurrió un error: {err_msg}")

    def _on_cancel_monte_carlo(self):
        if self.mc_worker and self.mc_worker.isRunning():
            self.mc_worker.cancel()
            self.mc_worker.wait()
            self.btn_run_mc.setEnabled(True)
            self.btn_cancel_mc.setEnabled(False)
            self.lbl_mc_status.setText("Simulación cancelada.")

    def _plot_debye_waller(self):
        if self.mc_results is None:
            return

        mc = self.mc_results
        s_vals = mc['sigma_values']
        is_aniso = mc.get('is_anisotropic', False)
        show_multi = getattr(self, 'chk_show_multi_order', None) is None or self.chk_show_multi_order.isChecked()
        show_order1 = self.chk_mc_order1.isChecked() if hasattr(self, 'chk_mc_order1') else True
        show_diag = (self.chk_mc_diag.isChecked() if hasattr(self, 'chk_mc_diag') else True) and show_multi
        show_order2 = (self.chk_mc_order2.isChecked() if hasattr(self, 'chk_mc_order2') else True) and show_multi

        self.plot_dw.clear()
        if hasattr(self, 'plot_dw_legend') and self.plot_dw_legend is not None:
            self.plot_dw_legend.clear()

        # 1. Graficar Curvas de Calibración MC y Ajustes
        if show_order1:
            if is_aniso:
                # Eje X
                H_mean_x = mc['H_mean_x']
                H_std_x = mc['H_std_x']
                fit_x = mc['fit_x']
                curve_up_x = H_mean_x + H_std_x
                curve_down_x = np.clip(H_mean_x - H_std_x, 0, None)
                c_up_x = self.plot_dw.plot(s_vals, curve_up_x, pen=pg.mkPen(None))
                c_down_x = self.plot_dw.plot(s_vals, curve_down_x, pen=pg.mkPen(None))
                fill_x = pg.FillBetweenItem(c_down_x, c_up_x, brush=pg.mkBrush(137, 180, 250, 35))
                self.plot_dw.addItem(fill_x)

                self.plot_dw.plot(
                    s_vals, H_mean_x, pen=None,
                    symbol='o', symbolSize=7,
                    symbolBrush=pg.mkBrush('#89b4fa'), symbolPen=pg.mkPen('#cdd6f4'),
                    name=f"MC X (ax={mc['a_x']:.1f}nm)"
                )
                if fit_x['success']:
                    self.plot_dw.plot(
                        fit_x['s_dense'], fit_x['H_fit_dense'],
                        pen=pg.mkPen('#89b4fa', width=2),
                        name='Fit DW X'
                    )

                # Eje Y
                H_mean_y = mc['H_mean_y']
                H_std_y = mc['H_std_y']
                fit_y = mc['fit_y']
                curve_up_y = H_mean_y + H_std_y
                curve_down_y = np.clip(H_mean_y - H_std_y, 0, None)
                c_up_y = self.plot_dw.plot(s_vals, curve_up_y, pen=pg.mkPen(None))
                c_down_y = self.plot_dw.plot(s_vals, curve_down_y, pen=pg.mkPen(None))
                fill_y = pg.FillBetweenItem(c_down_y, c_up_y, brush=pg.mkBrush(243, 139, 168, 35))
                self.plot_dw.addItem(fill_y)

                self.plot_dw.plot(
                    s_vals, H_mean_y, pen=None,
                    symbol='s', symbolSize=7,
                    symbolBrush=pg.mkBrush('#f38ba8'), symbolPen=pg.mkPen('#cdd6f4'),
                    name=f"MC Y (ay={mc['a_y']:.1f}nm)"
                )
                if fit_y['success']:
                    self.plot_dw.plot(
                        fit_y['s_dense'], fit_y['H_fit_dense'],
                        pen=pg.mkPen('#f38ba8', width=2, style=Qt.PenStyle.DashLine),
                        name='Fit DW Y'
                    )
            else:
                # Modo Isotrópico
                H_mean = mc['H_mean']
                H_std = mc['H_std']
                fit = mc['fit']

                curve_up = H_mean + H_std
                curve_down = np.clip(H_mean - H_std, 0, None)
                c_up = self.plot_dw.plot(s_vals, curve_up, pen=pg.mkPen(None))
                c_down = self.plot_dw.plot(s_vals, curve_down, pen=pg.mkPen(None))
                fill_item = pg.FillBetweenItem(c_down, c_up, brush=pg.mkBrush(137, 180, 250, 40))
                self.plot_dw.addItem(fill_item)

                self.plot_dw.plot(
                    s_vals, H_mean, pen=None,
                    symbol='o', symbolSize=7,
                    symbolBrush=pg.mkBrush('#89b4fa'), symbolPen=pg.mkPen('#cdd6f4'),
                    name='Simulación MC (1er Orden)'
                )
                if fit['success']:
                    self.plot_dw.plot(
                        fit['s_dense'], fit['H_fit_dense'],
                        pen=pg.mkPen('#a6e3a1', width=2),
                        name='Ajuste Debye-Waller (1er Orden)'
                    )

        # Curvas secundarias Multi-Orden (Diagonal y 2do Armónico)
        if show_diag and 'H_mean_diag' in mc and mc['H_mean_diag'] is not None:
            H_diag = mc['H_mean_diag']
            fit_diag = mc.get('fit_diag', {})
            self.plot_dw.plot(
                s_vals, H_diag, pen=None,
                symbol='d', symbolSize=7,
                symbolBrush=pg.mkBrush('#cba6f7'), symbolPen=pg.mkPen('#cdd6f4'),
                name='MC Diagonal (1,1)'
            )
            if fit_diag and fit_diag.get('success'):
                self.plot_dw.plot(
                    fit_diag['s_dense'], fit_diag['H_fit_dense'],
                    pen=pg.mkPen('#cba6f7', width=1.8, style=Qt.PenStyle.DashLine),
                    name='Fit DW Diag (1,1)'
                )

        if show_order2 and 'H_mean_2' in mc and mc['H_mean_2'] is not None:
            H_2 = mc['H_mean_2']
            fit_2 = mc.get('fit_2', {})
            self.plot_dw.plot(
                s_vals, H_2, pen=None,
                symbol='t', symbolSize=7,
                symbolBrush=pg.mkBrush('#f9e2af'), symbolPen=pg.mkPen('#cdd6f4'),
                name='MC Armónico 2do (2,0)'
            )
            if fit_2 and fit_2.get('success'):
                self.plot_dw.plot(
                    fit_2['s_dense'], fit_2['H_fit_dense'],
                    pen=pg.mkPen('#f9e2af', width=1.8, style=Qt.PenStyle.DashLine),
                    name='Fit DW 2do (2,0)'
                )

        # 2. Proyección Experimental y Triple Inversión
        if self.reciprocal_results is not None:
            r = self.reciprocal_results
            Hx = r['Hx']
            Hy = r['Hy']

            if is_aniso:
                sx, ds_x = interpolate_disorder(Hx, s_vals, mc['H_mean_x'], mc['H_std_x'])
                sy, ds_y = interpolate_disorder(Hy, s_vals, mc['H_mean_y'], mc['H_std_y'])
                if show_order1:
                    self.plot_dw.plot([0, sx, sx], [Hx, Hx, 0], pen=pg.mkPen('#89b4fa', width=1.5, style=Qt.PenStyle.DashLine))
                    self.plot_dw.plot([0, sy, sy], [Hy, Hy, 0], pen=pg.mkPen('#f38ba8', width=1.5, style=Qt.PenStyle.DashLine))
            else:
                sx, ds_x = interpolate_disorder(Hx, s_vals, mc['H_mean'], mc['H_std'])
                sy, ds_y = interpolate_disorder(Hy, s_vals, mc['H_mean'], mc['H_std'])
                if show_order1:
                    self.plot_dw.plot([0, sx, sx], [Hx, Hx, 0], pen=pg.mkPen('#f9e2af', width=1.5, style=Qt.PenStyle.DashLine))
                    self.plot_dw.plot([0, sy, sy], [Hy, Hy, 0], pen=pg.mkPen('#f38ba8', width=1.5, style=Qt.PenStyle.DashLine))

            s_prom = (sx + sy) / 2.0
            mc['sx_interp'] = sx
            mc['sy_interp'] = sy
            mc['s_prom'] = s_prom

            # Inversión Diagonal
            s_diag = None
            ds_diag = 0.0
            if 'H_diag' in r and 'H_mean_diag' in mc and mc['H_mean_diag'] is not None:
                H_meas_diag = r['H_diag']
                s_diag, ds_diag = interpolate_disorder(H_meas_diag, s_vals, mc['H_mean_diag'], mc.get('H_std_diag'))
                mc['s_diag_interp'] = s_diag
                if show_diag:
                    self.plot_dw.plot([0, s_diag, s_diag], [H_meas_diag, H_meas_diag, 0], pen=pg.mkPen('#cba6f7', width=1.5, style=Qt.PenStyle.DashLine))

            # Inversión 2do Orden
            s_2 = None
            ds_2 = 0.0
            if 'H_x_2nd' in r and 'H_mean_2' in mc and mc['H_mean_2'] is not None:
                H_meas_2 = r['H_x_2nd']
                s_2, ds_2 = interpolate_disorder(H_meas_2, s_vals, mc['H_mean_2'], mc.get('H_std_2'))
                mc['s_2_interp'] = s_2
                if show_order2:
                    self.plot_dw.plot([0, s_2, s_2], [H_meas_2, H_meas_2, 0], pen=pg.mkPen('#f9e2af', width=1.5, style=Qt.PenStyle.DashLine))

            # 3. Marcadores Interactivos de Coincidencia (Match Points)
            match_pts = []
            if show_order1:
                if is_aniso:
                    match_pts.append({'name': 'Pico Bragg X (1,0)', 's': sx, 'ds': ds_x, 'H': Hx, 'color': '#89b4fa', 'sym': 'o'})
                    match_pts.append({'name': 'Pico Bragg Y (0,1)', 's': sy, 'ds': ds_y, 'H': Hy, 'color': '#f38ba8', 'sym': 's'})
                else:
                    match_pts.append({'name': 'Pico Fundamental X/Y (1,0)', 's': sx, 'ds': ds_x, 'H': Hx, 'color': '#89b4fa', 'sym': 'o'})
                    match_pts.append({'name': 'Pico Fundamental Y (0,1)', 's': sy, 'ds': ds_y, 'H': Hy, 'color': '#f38ba8', 'sym': 's'})

            if s_diag is not None and show_diag:
                match_pts.append({'name': 'Pico Diagonal Cruzado (1,1)', 's': s_diag, 'ds': ds_diag, 'H': H_meas_diag, 'color': '#cba6f7', 'sym': 'd'})
            if s_2 is not None and show_order2:
                match_pts.append({'name': 'Pico Armónico 2do Orden (2,0)', 's': s_2, 'ds': ds_2, 'H': H_meas_2, 'color': '#f9e2af', 'sym': 't'})

            spots_list = []
            for mp in match_pts:
                spots_list.append({
                    'pos': (mp['s'], mp['H']),
                    'size': 14,
                    'pen': pg.mkPen('#ffffff', width=2),
                    'brush': pg.mkBrush(mp['color']),
                    'symbol': mp['sym'],
                    'data': mp
                })

            self.scatter_match_dw = pg.ScatterPlotItem(spots=spots_list)
            self.scatter_match_dw.sigClicked.connect(self._on_dw_match_point_clicked)
            self.plot_dw.addItem(self.scatter_match_dw)

            # Diagnóstico Físico de Consistencia del Cristal
            if s_diag is not None and s_2 is not None:
                dev_diag = s_diag - s_prom
                dev_2 = s_2 - s_prom
                max_dev = max(abs(dev_diag), abs(dev_2))
                if max_dev <= 5.0:
                    diag_txt = "✅ Red Gaussiana Ideal (Tipo I - Debye-Waller puro)"
                elif dev_diag > 5.0 and dev_diag >= dev_2:
                    diag_txt = f"⚠️ Mosaico / Fluctuación Angular (σ_diag > σ_1 por {dev_diag:.1f} nm)"
                elif dev_2 > 5.0:
                    diag_txt = f"⚠️ Desorden Paracristalino Acumulativo (Tipo II, σ_2 > σ_1 por {dev_2:.1f} nm)"
                else:
                    diag_txt = f"ℹ️ Desorden Mixto / Fluctuaciones Cruzadas (Δσ={max_dev:.1f} nm)"
            else:
                diag_txt = "Pendiente de evaluación multi-orden"

            mc['diagnosis_str'] = diag_txt

            # Formatear texto en tarjeta de resultados
            r2_txt = f"R²_x={mc.get('fit_x', mc['fit'])['r_squared']:.4f}"
            if is_aniso and 'fit_y' in mc:
                r2_txt += f" | R²_y={mc['fit_y']['r_squared']:.4f}"

            res_lines = [
                f"═══ TRIPLE INVERSIÓN DEBYE-WALLER ═══",
                f"• Orden 1 Fundamental: σ_dw,1 = {s_prom:.2f} nm (X={sx:.2f}±{ds_x:.2f} | Y={sy:.2f}±{ds_y:.2f})"
            ]
            if s_diag is not None:
                res_lines.append(f"• Orden Cruzado (1,1): σ_dw,diag = {s_diag:.2f} ± {ds_diag:.2f} nm")
            if s_2 is not None:
                res_lines.append(f"• Orden Armónico (2,0): σ_dw,2 = {s_2:.2f} ± {ds_2:.2f} nm")
            res_lines.append(f"\n═══ DIAGNÓSTICO FÍSICO DE RED ═══\n{diag_txt}")
            res_lines.append(f"Bondad de Calibración: {r2_txt}")

            self.lbl_mc_results.setText("\n".join(res_lines))

    def _on_save_calibration_curve(self):
        if self.mc_results is None:
            QMessageBox.warning(self, "Atención", "No hay resultados de simulación para guardar.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Guardar Curva de Calibración",
            "curva_calibracion_debye.npz",
            "Archivos NumPy (*.npz)"
        )
        if not file_path:
            return

        try:
            save_calibration_curve(file_path, self.mc_results)
            QMessageBox.information(self, "Guardado Exitoso", f"Curva de calibración guardada en:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error al Guardar", str(e))

    def _on_load_calibration_curve(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Cargar Curva de Calibración",
            "",
            "Archivos NumPy (*.npz);;Todos (*.*)"
        )
        if not file_path:
            return

        try:
            self.mc_results = load_calibration_curve(file_path)
            self.spin_mc_n.setValue(self.mc_results['n_side'])
            self.spin_mc_a.setValue(self.mc_results['a'])
            self.spin_mc_vac.setValue(self.mc_results['f_vac'] * 100.0)

            self._plot_debye_waller()
            if self.reciprocal_results is not None:
                self._update_analytical_panels_and_plots(self.reciprocal_results)
            self._update_metrics_table()
            QMessageBox.information(self, "Carga Exitosa", f"Curva de calibración cargada desde:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error al Cargar", str(e))

    def _update_metrics_table(self):
        filename = os.path.basename(self.current_image_path) if self.current_image_path else "Muestra Sintética"
        self.table_metrics.item(0, 1).setText(filename)
        self.table_metrics.item(1, 1).setText(f"{self.spin_n_side.value()} x {self.spin_n_side.value()}")

        if self.reciprocal_results is not None:
            r = self.reciprocal_results
            self.table_metrics.item(2, 1).setText(f"{r['a_x']:.2f} nm / {r['a_y']:.2f} nm / {r['a_mean']:.2f} nm")
            self.table_metrics.item(3, 1).setText(f"{r['anisotropy']:+.2f} nm")
            self.table_metrics.item(10, 1).setText(f"{r['xi_x']:.1f} nm / {r['xi_y']:.1f} nm")
            ratio = (r['fwhm_x'] / r['fwhm_y']) if r['fwhm_y'] > 0 else 1.0
            self.table_metrics.item(11, 1).setText(f"Relación FWHM_x/FWHM_y = {ratio:.2f}")

            # Fila 14: Jerarquía de Bragg
            h_diag_r = r.get('ratio_diag', 0.0)
            h_2_r = r.get('ratio_order2_x', 0.0)
            sbr = r.get('sbr_mean', 0.0)
            self.table_metrics.item(14, 1).setText(f"H_diag/H1={h_diag_r:.3f} | H2/H1={h_2_r:.3f} (SBR: {sbr:.1f})")

            # Fila 15: Mosaico Angular / Cizallamiento
            dth = r.get('delta_theta_x_deg', 0.0)
            shear = r.get('shear_strain_deg', 0.0)
            self.table_metrics.item(15, 1).setText(f"Δθ={dth:.2f}° | Cizalle γ-90°={shear:+.2f}°")

            # Fila 17: Inversión Analítica Directa
            if 'analytical_relations' in r:
                ana = r['analytical_relations']
                s_h2h1 = ana.get('sigma_h2h1', 0.0)
                s_h2h1_x = ana.get('sigma_h2h1_x', s_h2h1)
                s_h2h1_y = ana.get('sigma_h2h1_y', s_h2h1)
                s_w = ana.get('sigma_wilson', 0.0)
                s_wx = ana.get('sigma_wilson_x', s_w)
                s_wy = ana.get('sigma_wilson_y', s_w)
                r2_w = ana.get('r_squared_wilson', 0.0)
                self.table_metrics.item(17, 1).setText(
                    f"σ(H2/H1): X={s_h2h1_x:.1f}, Y={s_h2h1_y:.1f} nm | Wilson: X={s_wx:.1f}, Y={s_wy:.1f} nm (R²={r2_w:.3f})"
                )
            else:
                self.table_metrics.item(17, 1).setText("Pendiente (requiere Espacio Recíproco)")

        if self.kdtree_results is not None:
            kd = self.kdtree_results
            v_prac = kd.get('n_vac_prac', kd.get('vacant_count', 0))
            f_prac_pct = kd.get('f_vac_prac_percent', kd.get('f_vac_percent', 0.0))
            v_teor = kd.get('n_vac_teor', kd.get('vacant_count', 0))
            f_teor_pct = kd.get('f_vac_teor_percent', kd.get('f_vac_percent', 0.0))
            self.table_metrics.item(4, 1).setText(
                f"Prácticas: {f_prac_pct:.1f}% ({v_prac} vac) | Teóricas: {f_teor_pct:.1f}% ({v_teor} vac)"
            )
            self.table_metrics.item(5, 1).setText(f"σ_x={kd['sigma_x']:.2f} nm / σ_y={kd['sigma_y']:.2f} nm")
            self.table_metrics.item(6, 1).setText(f"{kd['sigma_pos']:.2f} nm")

        if self.rdf_results is not None:
            self.table_metrics.item(7, 1).setText(f"{self.rdf_results['sigma_rdf']:.2f} nm")

        if self.mc_results is not None and 'sx_interp' in self.mc_results:
            mc = self.mc_results
            self.table_metrics.item(8, 1).setText(f"σ_dw,x={mc['sx_interp']:.2f} nm / σ_dw,y={mc['sy_interp']:.2f} nm")
            self.table_metrics.item(9, 1).setText(f"{mc['s_prom']:.2f} nm")

            # Fila 16: Triple Inversión Debye-Waller
            if 's_diag_interp' in mc and 's_2_interp' in mc:
                self.table_metrics.item(16, 1).setText(
                    f"σ1={mc['s_prom']:.1f}nm | σ_diag={mc['s_diag_interp']:.1f}nm | σ2={mc['s_2_interp']:.1f}nm ({mc.get('diagnosis_str', '')})"
                )
            else:
                self.table_metrics.item(16, 1).setText(f"σ1={mc['s_prom']:.2f} nm")

        if self.kdtree_results is not None and self.mc_results is not None and 's_prom' in self.mc_results:
            diff = abs(self.kdtree_results['sigma_pos'] - self.mc_results['s_prom'])
            status = "Excelente concordancia" if diff < 5.0 else ("Concordancia aceptable" if diff < 10.0 else "Divergencia (revisar aglomerados/vacancias)")
            self.table_metrics.item(12, 1).setText(f"Δσ = {diff:.2f} nm ({status})")
        else:
            self.table_metrics.item(12, 1).setText("Pendiente (requiere KDTree y Debye-Waller)")

        if self.cluster_results is not None:
            cl = self.cluster_results
            n_cl = cl.get('n_clusters', 0)
            n_pts = len(cl.get('cluster_particle_indices', []))
            self.table_metrics.item(13, 1).setText(f"{n_cl} cúmulos ({n_pts} partículas involucradas)")
        else:
            self.table_metrics.item(13, 1).setText("No evaluado")

    # ==========================================================================
    # EXPORTACIÓN CIENTÍFICA
    # ==========================================================================

    def _on_export_coordinates_csv(self):
        if self.locs_df is None or len(self.locs_df) == 0:
            QMessageBox.warning(self, "Atención", "No hay coordenadas para exportar.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Exportar Coordenadas Detectadas",
            "coordenadas_localizadas.csv",
            "Archivos CSV (*.csv)"
        )
        if not file_path:
            return

        try:
            self.locs_df.to_csv(file_path, index=False)
            QMessageBox.information(self, "Exportación Exitosa", f"Archivo guardado:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error al Exportar", str(e))

    def _on_export_report_txt(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Exportar Resumen Metrológico",
            "reporte_metrologico_redes.txt",
            "Archivos de Texto (*.txt)"
        )
        if not file_path:
            return

        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write("================================================================================\n")
                f.write("PYPRINTING 3.0 — REPORTE METROLÓGICO DE DESORDEN Y ESTRUCTURA DE REDES 2D\n")
                f.write("================================================================================\n")
                f.write(f"Fecha de Análisis: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")

                for row in range(self.table_metrics.rowCount()):
                    param = self.table_metrics.item(row, 0).text()
                    val = self.table_metrics.item(row, 1).text()
                    f.write(f"{param:<50}: {val}\n")

                f.write("\n================================================================================\n")
                f.write("NOTAS TEÓRICAS Y METODOLÓGICAS:\n")
                f.write("- Transformada de Fourier Continua 2D (NUFFT) calculada sobre coordenadas nanométricas\n")
                f.write("  directas sin discretización en histogramas, garantizando piso de ruido nulo (< 0.5 nm).\n")
                f.write("- Atenuación de Debye-Waller desacoplando estrictamente el factor de vacancias (1 - p)^2.\n")
                f.write("- KDTree acotado con cota superior a/2 y varianza cartesianamente desacoplada.\n")
                f.write("================================================================================\n")

            QMessageBox.information(self, "Exportación Exitosa", f"Reporte guardado:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error al Exportar", str(e))

    def _on_export_dw_curve_csv(self):
        if self.mc_results is None:
            QMessageBox.warning(self, "Atención", "No hay datos de curva Debye-Waller para exportar.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Exportar Curva Debye-Waller",
            "curva_debye_waller.csv",
            "Archivos CSV (*.csv)"
        )
        if not file_path:
            return

        try:
            mc = self.mc_results
            df_dw = pd.DataFrame({
                'sigma_nm': mc['sigma_values'],
                'H_mean': mc['H_mean'],
                'H_std': mc['H_std']
            })
            df_dw.to_csv(file_path, index=False)
            QMessageBox.information(self, "Exportación Exitosa", f"Curva guardada:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error al Exportar", str(e))

    def _on_export_gallery(self):
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar Carpeta para Guardar Galería Completa de Figuras")
        if not folder:
            return

        try:
            import pyqtgraph.exporters as pg_exp

            gallery_items = [
                (self.plot_real_space, "fig01_espacio_real_smlm", 2400),
                (self.plot_rdf, "fig02_distribucion_radial_gr", 2000),
                (self.plot_fourier_2d, "fig03_espectro_reciproco_2d", 2400),
                (self.plot_cut_x, "fig04_corte_espectral_fx", 1800),
                (self.plot_cut_y, "fig05_corte_espectral_fy", 1800),
                (self.plot_cut_diag, "fig06_corte_espectral_diagonal_45deg", 1800),
                (self.plot_wilson, "fig07_grafico_wilson_linear_fit", 2000),
                (self.plot_dw_decay, "fig08_decaimiento_debye_waller_multi_orden", 2000),
                (self.plot_ratio_stability, "fig09_comparativa_estabilidad_ratios", 2000),
                (self.plot_fwhm_paracrystal, "fig10_diagnostico_paracristal_fwhm_hosemann", 2000),
                (self.plot_dw, "fig11_curva_calibracion_debye_waller_mc", 2400),
            ]

            saved_png = 0
            saved_svg = 0
            for plot_w, name, w_px in gallery_items:
                # 1. Exportar PNG Alta Resolución (600 DPI)
                png_path = os.path.join(folder, f"{name}.png")
                exp_img = pg_exp.ImageExporter(plot_w.plotItem)
                exp_img.parameters()['width'] = w_px
                exp_img.export(png_path)
                saved_png += 1

                # 2. Exportar SVG Vectorial
                try:
                    svg_path = os.path.join(folder, f"{name}.svg")
                    self._export_plot_to_svg(plot_w, svg_path)
                    saved_svg += 1
                except Exception:
                    pass

            QMessageBox.information(
                self,
                "Galería Completa Exportada",
                f"Se exportaron con éxito {saved_png} figuras científicas en alta resolución (PNG 600 DPI)\n"
                f"y {saved_svg} gráficos vectoriales (SVG) en la carpeta:\n{folder}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Error al Exportar Galería", f"Error durante la exportación:\n{str(e)}")

    # --------------------------------------------------------------------------
    # MÉTODOS DE CALIBRACIÓN ÓPTICA, CURACIÓN DE CÚMULOS Y SINCRONIZACIÓN
    # --------------------------------------------------------------------------

    def _on_calibrate_psf(self):
        """Calibra condiciones iniciales (Picasso, Trackpy, RL, Fotometría) a partir de una PSF confocal experimental."""
        default_dir = os.path.join(os.path.dirname(__file__), "..", "reserva")
        if not os.path.isdir(default_dir):
            default_dir = os.getcwd()

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar Micrografía de PSF Confocal (ej. 100 nm Au NP)",
            default_dir,
            "Imágenes Científicas (*.tiff *.tif *.png *.h5);;Todos los Archivos (*)"
        )
        if not file_path:
            return

        # Diálogo para confirmar escala espacial y factor de potencia láser
        dlg = QDialog(self)
        dlg.setWindowTitle("Parámetros de Calibración PSF Confocal")
        dlg_lay = QVBoxLayout(dlg)

        lbl_desc = QLabel(
            "Configure los parámetros ópticos para el ajuste de la PSF confocal.\n"
            "El ajuste estimará el ancho óptico σ_psf, FWHM, fotones V₀ y gradiente de Sobel."
        )
        lbl_desc.setStyleSheet("color: #cdd6f4; font-size: 11px;")
        dlg_lay.addWidget(lbl_desc)

        form_lay = QGridLayout()
        form_lay.addWidget(QLabel("Escala Espacial (nm/px):"), 0, 0)
        spin_scale_psf = QDoubleSpinBox()
        spin_scale_psf.setRange(1.0, 1000.0)
        spin_scale_psf.setValue(self.spin_scale.value() if hasattr(self, 'spin_scale') else 50.0)
        form_lay.addWidget(spin_scale_psf, 0, 1)

        form_lay.addWidget(QLabel("Factor Potencia Láser (P_red / P_psf):"), 1, 0)
        spin_pwr = QDoubleSpinBox()
        spin_pwr.setRange(0.01, 100.0)
        spin_pwr.setValue(1.0)
        spin_pwr.setSingleStep(0.1)
        form_lay.addWidget(spin_pwr, 1, 1)
        dlg_lay.addLayout(form_lay)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(dlg.accept)
        btn_box.rejected.connect(dlg.reject)
        dlg_lay.addWidget(btn_box)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        scale_nm = spin_scale_psf.value()
        pwr_factor = spin_pwr.value()

        try:
            # Cargar imagen PSF
            psf_img = None
            try:
                import tifffile
                psf_img = tifffile.imread(file_path)
            except Exception:
                pass

            if psf_img is None:
                from PIL import Image
                pil_img = Image.open(file_path)
                psf_img = np.array(pil_img)

            if psf_img is None:
                raise ValueError("No se pudo decodificar el archivo de imagen PSF.")

            if psf_img.ndim > 2:
                psf_img = psf_img[0] if psf_img.shape[0] < psf_img.shape[-1] else psf_img[:, :, 0]

            psf_img = psf_img.astype(np.float64)

            # Normalización respecto a imagen de red activa si está disponible
            target_max = float(np.nanmax(self.image_2d)) if self.image_2d is not None else None

            # Ajuste de PSF y extracción de condiciones iniciales
            calib = calibrate_from_psf_image(
                psf_img,
                scale_nm=scale_nm,
                laser_power_factor=pwr_factor,
                target_img_max=target_max
            )

            # Actualizar firma del monómero
            self.monomer_signature = calib['monomer_signature']

            # Auto-llenar campos GUI manteniendo edición abierta
            self.spin_scale.setValue(scale_nm)

            # Trackpy
            tp = calib['trackpy']
            self.spin_diameter.setValue(int(tp['diameter']))
            self.spin_minmass.setValue(float(tp['minmass']))
            self.spin_separation.setValue(float(tp['separation']))

            # Picasso
            pic = calib['picasso']
            self.spin_box_size.setValue(int(pic['box_size']))
            self.spin_net_grad.setValue(float(pic['min_net_gradient']))

            # Richardson-Lucy
            rl = calib['richardson_lucy']
            self.spin_rl_sigma.setValue(float(rl['psf_sigma']))

            # Actualizar etiquetas informativas
            info_txt = (
                f"PSF Calibrada: σ={calib['sigma_psf_nm']:.1f} nm (FWHM={calib['fwhm_nm']:.1f} nm) | "
                f"V₀={calib['V0']:.1f} fotones | Sobel={calib['max_gradient']:.2f}"
            )
            self.lbl_psf_calib_info.setText(info_txt)
            self.lbl_psf_calib_info.setStyleSheet("color: #a6e3a1; font-size: 10px; font-family: monospace;")

            mono_txt = f"Firma Monómero: V₀={calib['V0']:.1f} | A₀={calib['A0']:.1f} px² | σ_psf={calib['sigma_psf_nm']:.1f} nm"
            self.lbl_monomer_signature.setText(mono_txt)

            QMessageBox.information(
                self,
                "Calibración Óptica con PSF Exitosa",
                f"Se calibraron con éxito los parámetros a partir de:\n{os.path.basename(file_path)}\n\n"
                f"• Ancho difraccional σ_psf: {calib['sigma_psf_nm']:.2f} nm ({calib['sigma_psf_px']:.2f} px)\n"
                f"• FWHM difraccional: {calib['fwhm_nm']:.2f} nm\n"
                f"• Fotones del monómero V₀: {calib['V0']:.1f}\n"
                f"• Gradiente máximo de Sobel: {calib['max_gradient']:.2f}\n\n"
                "Se han actualizado las condiciones iniciales para Trackpy, Picasso, Richardson-Lucy "
                "y el Desacoplamiento Fotométrico. Todos los parámetros permanecen editables."
            )
        except Exception as e:
            QMessageBox.critical(self, "Error en Calibración de PSF", f"Ocurrió un error al calibrar la PSF:\n{str(e)}")

    def _on_cluster_contour_thresh_changed(self):
        """Recalcula y actualiza dinámicamente el contorno fotométrico del cúmulo seleccionado con el umbral especificado."""
        if self.selected_cluster_id is None or self.cluster_results is None:
            return
        clusters = self.cluster_results.get('clusters', [])
        target_cluster = None
        for cl in clusters:
            if cl.get('id') == self.selected_cluster_id:
                target_cluster = cl
                break
        if target_cluster is None or self.image_2d is None:
            return

        scale_nm = self.spin_scale.value() if hasattr(self, 'spin_scale') else 50.0
        thresh_pct = self.spin_cluster_contour_thresh.value() / 100.0 if hasattr(self, 'spin_cluster_contour_thresh') else 0.20
        sigma_psf_px = 1.5
        if self.monomer_signature and 'sigma_psf_px' in self.monomer_signature:
            sigma_psf_px = max(0.5, float(self.monomer_signature['sigma_psf_px']))
        elif self.monomer_signature and 'sigma_nm' in self.monomer_signature:
            sigma_psf_px = max(0.5, float(self.monomer_signature['sigma_nm']) / scale_nm)

        com_x = float(target_cluster.get('com_x', 0.0))
        com_y = float(target_cluster.get('com_y', 0.0))
        cx_px = com_x / scale_nm
        cy_px = com_y / scale_nm

        indices = target_cluster.get('indices', [])
        if len(indices) > 0 and self.locs_df is not None:
            x_pts = self.locs_df['x_nm'].values[indices]
            y_pts = self.locs_df['y_nm'].values[indices]
            d_max_nm = float(np.max(np.hypot(x_pts - com_x, y_pts - com_y)))
            half = int(np.ceil(d_max_nm / scale_nm + 2.5 * sigma_psf_px))
        else:
            half = int(np.ceil(3.5 * sigma_psf_px))
        half = max(half, 6)

        H_img, W_img = self.image_2d.shape[:2]
        x_min = max(0, int(round(cx_px)) - half)
        x_max = min(W_img, int(round(cx_px)) + half + 1)
        y_min = max(0, int(round(cy_px)) - half)
        y_max = min(H_img, int(round(cy_px)) + half + 1)

        patch = self.image_2d[y_min:y_max, x_min:x_max]
        if patch.size == 0:
            return

        border_px = np.concatenate([patch[0, :], patch[-1, :], patch[:, 0], patch[:, -1]])
        bg = float(np.percentile(border_px, 50))
        sig = np.clip(patch - bg, 0, None)
        max_sig = float(np.max(sig))
        thresh_val = bg + thresh_pct * max_sig if max_sig > 0 else bg
        mask_binary = (patch > thresh_val).astype(np.uint8)

        contour_poly_nm = []
        try:
            import cv2
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

        target_cluster['contour_polygon_nm'] = contour_poly_nm

        if self.highlight_contour_item is not None:
            self.plot_real_space.removeItem(self.highlight_contour_item)
            self.highlight_contour_item = None

        if len(contour_poly_nm) > 2:
            poly_arr = np.array(contour_poly_nm)
            poly_closed = np.vstack([poly_arr, poly_arr[0]])
            self.highlight_contour_item = pg.PlotDataItem(
                poly_closed[:, 0], poly_closed[:, 1],
                pen=pg.mkPen('#f9e2af', width=3.0)
            )
            self.highlight_contour_item.setVisible(self.chk_layer_contours.isChecked())
            self.plot_real_space.addItem(self.highlight_contour_item)

    def _on_toggle_add_particles_to_cluster(self, checked: bool):
        """Activa o desactiva el modo interactivo de clic para agregar o remover partículas del cúmulo seleccionado."""
        if checked:
            if self.selected_cluster_id is None:
                QMessageBox.information(
                    self,
                    "Modo Añadir Partículas al Contorno",
                    "Seleccione primero un cúmulo en la tabla de aglomerados para definir a cuál asociar partículas."
                )
                self.btn_cluster_add_particles.setChecked(False)
                return
            self.statusBar().showMessage(
                f"Modo Clic Activo: Haga clic en partículas del visor para añadirlas o removerlas del Cúmulo #{self.selected_cluster_id}."
            )
        else:
            self.statusBar().showMessage("Modo Añadir Partículas desactivado.")

    def _on_sync_curated_to_reciprocal(self):
        """Sincroniza las coordenadas curadas con el Espacio Recíproco (Tab 2) y actualiza la sección de metrología analítica sin cambiar de pestaña."""
        if self.locs_df is None or self.locs_df.empty:
            QMessageBox.warning(self, "Atención", "No hay coordenadas disponibles para sincronizar.")
            return

        # 1. Recalcular espacio recíproco y metrología analítica directa con las coordenadas actuales curadas
        self._on_recalculate_reciprocal()

        # 2. Propagar parámetros a Monte Carlo de forma silenciosa (sin cambiar de pestaña ni abrir popups)
        if self.reciprocal_results is not None:
            res = self.reciprocal_results
            a_mean = res['a_mean']
            a_x = res.get('a_x', a_mean)
            a_y = res.get('a_y', a_mean)
            aniso = abs(a_x - a_y)
            is_aniso = aniso > 1.0

            self.spin_mc_ax.setValue(a_x)
            self.spin_mc_ay.setValue(a_y)
            self.chk_mc_anisotropy.setChecked(is_aniso)
            self.spin_mc_ay.setEnabled(is_aniso)
            self.spin_mc_n.setValue(self.spin_n_side.value())

            if self.kdtree_results is not None:
                self.spin_mc_vac.setValue(self.kdtree_results.get('f_vac_percent', 0.0))

            band_bins = self.spin_band.value()
            idx_bins = self.combo_bins.currentIndex()
            n_bins = 256 if idx_bins == 0 else (512 if idx_bins == 1 else 1024)
            fmax = 2.5 / a_mean if a_mean > 0 else 1.0
            delta_f = (2.0 * fmax) / n_bins
            band_nm = band_bins * delta_f
            self.spin_mc_band.setValue(band_nm)

            self.statusBar().showMessage(
                "✅ Puntos curados sincronizados con Espacio Recíproco (sección analítica y parámetros MC actualizados).",
                5000
            )

    def _on_dw_match_point_clicked(self, item, points):
        """Muestra un callout metrológico detallado al hacer clic en un punto de coincidencia de Debye-Waller."""
        if len(points) == 0:
            return
        pt = points[0]
        data = pt.data()
        if not data:
            return
        name = data.get('name', 'Punto de Intersección')
        s = data.get('s', 0.0)
        ds = data.get('ds', 0.0)
        H = data.get('H', 0.0)
        rel_unc = (ds / max(s, 1e-6) * 100.0)

        QMessageBox.information(
            self,
            f"Metrología Debye-Waller: {name}",
            f"<h3>{name}</h3>"
            f"<p><b>Dispersión estocástica interpolada (σ):</b> {s:.2f} ± {ds:.2f} nm</p>"
            f"<p><b>Altura de pico normalizada experimental (H):</b> {H:.4f}</p>"
            f"<p><b>Incertidumbre relativa (Δσ / σ):</b> {rel_unc:.1f}%</p>"
            f"<hr>"
            f"<p style='color: #a6adc8; font-size: 11px;'><i>Este punto representa la proyección de la altura Bragg medida "
            f"sobre la curva de calibración estocástica Monte Carlo, desacoplando estrictamente el factor canónico "
            f"de vacancias (V_prac = N² - M).</i></p>"
        )


# ==============================================================================
# PUNTO DE ENTRADA PRINCIPAL
# ==============================================================================

def main():
    app = QApplication(sys.argv)
    window = LatticeDisorderWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
