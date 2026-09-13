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
    QProgressBar, QStackedWidget, QLineEdit, QButtonGroup, QMenu
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
    analyze_reciprocal_space_2d,
    analyze_real_space_kdtree,
    compute_radial_distribution_function,
    run_monte_carlo_calibration,
    fit_debye_waller_curve,
    interpolate_disorder,
    save_calibration_curve,
    load_calibration_curve,
    detect_clusters_and_chains,
    resolve_clusters,
    resolve_clusters_dataframe,
    inspect_single_spot_photometry,
    resolve_single_spot_multi_gaussian,
    find_optimal_grid_bounding_box,
    compute_analytical_bragg_relations
)


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
        self.scatter_det: Optional[pg.ScatterPlotItem] = None
        self.scatter_clusters: Optional[pg.ScatterPlotItem] = None
        self.scatter_vac: Optional[pg.ScatterPlotItem] = None
        self.scatter_grid: Optional[pg.ScatterPlotItem] = None
        self.scatter_selected: Optional[pg.ScatterPlotItem] = None

        # Worker asíncrono
        self.mc_worker: Optional[MonteCarloWorker] = None

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
            act_exp = menu.addAction(f"💾 Exportar '{display_title}' (PNG 600 DPI / SVG)...")
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
        self.spin_cluster_tolerance.valueChanged.connect(self._on_recalc_grid)
        h_tol.addWidget(self.spin_cluster_tolerance)
        lay_cur.addLayout(h_tol)

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

        # Acciones sobre el Cúmulo Seleccionado (Uno a Uno)
        lbl_single = QLabel("Acción Cúmulo Seleccionado:")
        lbl_single.setStyleSheet("color: #f9e2af; font-weight: bold; font-size: 11px;")
        lay_cur.addWidget(lbl_single)

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
        self.spin_consistency_margin.valueChanged.connect(self._on_recalc_grid)
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
            "Vacancias: -%\n"
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
        btn_go_tab2.clicked.connect(lambda: self.tabs.setCurrentIndex(1))
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
            "Controla la visibilidad de ImageItem posicionado en el espacio físico nanométrico."
        ))
        self.chk_layer_img.toggled.connect(self._on_layer_visibility_changed)
        lay_row1.addWidget(self.chk_layer_img)

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
        lbl_p2 = QLabel("Función de Distribución Radial g(r) y Primer Pico de Coordinación:")
        lbl_p2.setStyleSheet("font-weight: bold; color: #cba6f7;")
        h_p2_hdr.addWidget(lbl_p2)
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
            "Fórmula: σ = (a / 2π√3) √(ln(H₁/H₂))</span>"
        )
        self.lbl_card_h2h1.setStyleSheet(
            "background-color: #181825; border: 1px solid #a6e3a1; border-radius: 6px; padding: 8px; font-family: monospace;"
        )
        self.lbl_card_h2h1.setToolTip(make_tooltip(
            "Razón H₂ / H₁ (Estándar de Oro de Inversión Analítica)",
            "La forma más pura y robusta de estimar el desorden sin calibración: el cociente entre el segundo armónico y el fundamental cancela totalmente las vacancias y el tamaño de muestra.",
            "Fórmula cerrada: σ = (a / 2π√3) √(ln(H₁/H₂)). Dado que H(q) = N²(1-p)² exp(-q²σ²), al tomar el cociente H₂/H₁ el prefactor N²(1-p)² desaparece rigurosamente."
        ))
        lay_cards_grid.addWidget(self.lbl_card_h2h1, 0, 0)

        # Card 2: H_diag / H1 (Coherencia 2D)
        self.lbl_card_diag = QLabel(
            "<b>σ (H_diag / H₁): - nm</b><br>"
            "<span style='color: #a6adc8; font-size: 10px;'>"
            "Coherencia 2D (Orden cruzado (1,1))<br>"
            "Fórmula: σ = (a / 2π) √(ln(H₁/H_diag))</span>"
        )
        self.lbl_card_diag.setStyleSheet(
            "background-color: #181825; border: 1px solid #cba6f7; border-radius: 6px; padding: 8px; font-family: monospace;"
        )
        self.lbl_card_diag.setToolTip(make_tooltip(
            "Razón Diagonal H_diag / H₁ (Coherencia 2D)",
            "Estima el desorden a partir del orden cruzado (1,1) a 45°, sensible a la simetría y correlación bidimensional.",
            "Fórmula cerrada: σ = (a / 2π) √(ln(H₁/H_diag)) ya que |G_diag|² = 2 |G₁|². Cancela N y vacancias p asumiendo desorden isotrópico."
        ))
        lay_cards_grid.addWidget(self.lbl_card_diag, 0, 1)

        # Card 3: H1 / H0 (Inestable)
        self.lbl_card_h1h0 = QLabel(
            "<b>σ (H₁ / H₀): - nm</b> <span style='color: #f38ba8; font-size: 10px;'>[⚠️ INESTABLE]</span><br>"
            "<span style='color: #a6adc8; font-size: 10px;'>"
            "Razón frente a DC Central (q=0)<br>"
            "Sensible a autofluorescencia, haz directo y N</span>"
        )
        self.lbl_card_h1h0.setStyleSheet(
            "background-color: #181825; border: 1px solid #f38ba8; border-radius: 6px; padding: 8px; font-family: monospace;"
        )
        self.lbl_card_h1h0.setToolTip(make_tooltip(
            "Razón H₁ / H₀ (Inestable frente al Centro DC)",
            "ADVERTENCIA METROLÓGICA: Muy inestable. Comparar el pico fundamental con el centro q=0 es vulnerable al haz directo y a la autofluorescencia.",
            "Fórmula: σ = (a / 2π) √( -2 ln( (H₁/H₀) / (1-p) ) ). Requiere conocer p a priori y sufre por la acumulación de fondo difuso e iluminación de campo amplio en q=0."
        ))
        lay_cards_grid.addWidget(self.lbl_card_h1h0, 0, 2)

        # Card 4: Gráfico de Wilson
        self.lbl_card_wilson = QLabel(
            "<b>σ (Wilson Plot): - nm</b> (R²: -)<br>"
            "<span style='color: #a6adc8; font-size: 10px;'>"
            "Ajuste lineal multi-orden ln(H) vs |G|²<br>"
            "Vacancias estimadas: p_est = -%</span>"
        )
        self.lbl_card_wilson.setStyleSheet(
            "background-color: #181825; border: 1px solid #89b4fa; border-radius: 6px; padding: 8px; font-family: monospace;"
        )
        self.lbl_card_wilson.setToolTip(make_tooltip(
            "Gráfico de Wilson Multiórden (ln H vs |G|²)",
            "Ajuste lineal simultáneo sobre todos los picos de difracción. La pendiente da el desorden y la ordenada al origen estima las vacancias.",
            "Ecuación: ln(H_G) = ln(N²(1-p)²) - (σ²/2) |G|². La pendiente m = -σ²/2 arroja σ = √( -2m ), y la ordenada b permite estimar p = 1 - √(exp(b))/N."
        ))
        lay_cards_grid.addWidget(self.lbl_card_wilson, 1, 0, 1, 2)

        # Card 5: Diagnóstico Paracristalino
        self.lbl_card_paracrystal = QLabel(
            "<b>Diagnóstico: -</b><br>"
            "<span style='color: #a6adc8; font-size: 10px;'>"
            "Ratio FWHM₂ / FWHM₁ = -<br>"
            "-</span>"
        )
        self.lbl_card_paracrystal.setStyleSheet(
            "background-color: #181825; border: 1px solid #f9e2af; border-radius: 6px; padding: 8px; font-family: monospace;"
        )
        self.lbl_card_paracrystal.setToolTip(make_tooltip(
            "Diagnóstico de Tipo de Desorden (Hosemann)",
            "Compara el ancho del segundo armónico contra el fundamental para diferenciar desorden vibracional (Tipo I) de desorden acumulativo (Tipo II).",
            "Teoría de Hosemann: Si FWHM₂/FWHM₁ ≈ 1.0, el desorden es Tipo I (Debye-Waller puro). Si crece proporcional al orden m o m², existe desorden acumulativo de paracristal."
        ))
        lay_cards_grid.addWidget(self.lbl_card_paracrystal, 1, 2)

        right_layout.addWidget(grp_ana_cards)

        # Batería de 4 Gráficos de Diagnóstico Analítico (Grid 2x2)
        h_ana_plots_hdr = QHBoxLayout()
        grp_ana_plots = QGroupBox("Batería de Gráficos de Diagnóstico Analítico")
        grp_ana_plots.setStyleSheet("QGroupBox { font-weight: bold; color: #89b4fa; }")
        grp_ana_plots.setToolTip(make_tooltip(
            "Batería de 4 Gráficos Analíticos de Fourier",
            "Inspección gráfica integral de los modelos analíticos: Wilson, decaimiento Debye-Waller, estabilidad de razones y ancho radial.",
            "Panel 2x2 para evaluar bondad de ajuste lineal, atenuación armónica multiorden y criterios de coherencia reticular."
        ))
        lay_plots_grid = QGridLayout(grp_ana_plots)
        lay_plots_grid.setSpacing(8)

        # Plot 1: Gráfico de Wilson
        self.plot_wilson = pg.PlotWidget(title="1. Gráfico de Wilson (ln(H) vs |G|²)")
        self.plot_wilson.showGrid(x=True, y=True, alpha=0.3)
        self.plot_wilson.setLabel('bottom', '|G|²', units='rad²/nm²')
        self.plot_wilson.setLabel('left', 'ln(H)')
        self.plot_wilson.setMinimumHeight(240)
        self.plot_wilson.setToolTip(make_tooltip(
            "1. Gráfico de Wilson (ln(H) vs |G|²)",
            "Ajuste lineal de la atenuación de intensidad en función del cuadrado del vector recíproco |G|². Clic derecho para exportar.",
            "Recta de regresión ln(H_G) vs |G|² donde la pendiente m determina el desorden σ = √(-2m) y el coeficiente R² valida el modelo gaussiano."
        ))
        self._setup_plot_export_menu(self.plot_wilson, "fig07_grafico_wilson_linear_fit", "Gráfico de Wilson")
        lay_plots_grid.addWidget(self.plot_wilson, 0, 0)

        # Plot 2: Decaimiento Multiórden Debye-Waller
        self.plot_dw_decay = pg.PlotWidget(title="2. Decaimiento Debye-Waller: H(q)/H₁ vs Orden")
        self.plot_dw_decay.showGrid(x=True, y=True, alpha=0.3)
        self.plot_dw_decay.setLabel('bottom', 'q / q₀', units='orden')
        self.plot_dw_decay.setLabel('left', 'H / H₁ (Normalizado)')
        self.plot_dw_decay.setMinimumHeight(240)
        self.plot_dw_decay.setToolTip(make_tooltip(
            "2. Decaimiento Debye-Waller: H(q)/H₁ vs Orden",
            "Atenuación relativa de los picos de difracción respecto al fundamental frente a la curva analítica teórica. Clic derecho para exportar.",
            "Perfil normalizado H(q)/H₁ = exp(- (q² - q₀²) σ² / 2) contrastando mediciones experimentales de los órdenes (1,0), (1,1) y (2,0)."
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
            "Gráfico comparativo que contrasta los valores de desorden inferidos por H₂/H₁, H_diag/H₁, Wilson Plot y H₁/H₀. Clic derecho para exportar.",
            "Visualiza la concordancia o divergencia metrológica entre estimaciones de desorden para identificar efectos de fondo espurio o anisotropía."
        ))
        self._setup_plot_export_menu(self.plot_ratio_stability, "fig09_comparativa_estabilidad_ratios", "Comparativa de Estabilidad de Ratios")
        lay_plots_grid.addWidget(self.plot_ratio_stability, 1, 0)

        # Plot 4: Diagnóstico de Ancho Radial (Tipo I vs Tipo II)
        self.plot_fwhm_paracrystal = pg.PlotWidget(title="4. Diagnóstico de Desorden: FWHM vs Orden (Hosemann)")
        self.plot_fwhm_paracrystal.showGrid(x=True, y=True, alpha=0.3)
        self.plot_fwhm_paracrystal.setLabel('bottom', 'Orden Cristalográfico m')
        self.plot_fwhm_paracrystal.setLabel('left', 'FWHM Radial', units='nm^-1')
        self.plot_fwhm_paracrystal.setMinimumHeight(240)
        self.plot_fwhm_paracrystal.setToolTip(make_tooltip(
            "4. Diagnóstico de Desorden: FWHM vs Orden (Hosemann)",
            "Evolución del ancho a media altura (FWHM) de los picos en función del orden cristalográfico m. Clic derecho para exportar.",
            "Ensanchamiento radial de Bragg: FWHM constante confirma desorden Tipo I (acotado); ensanchamiento cuadrático revela paracristal Tipo II."
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

        self.btn_run_mc = QPushButton("🚀 Iniciar Simulación Monte Carlo")
        self.btn_run_mc.setObjectName("masterBtn")
        self.btn_run_mc.setToolTip(make_tooltip(
            "Iniciar Simulación Monte Carlo Asíncrona",
            "Lanza el cálculo en segundo plano sin congelar la ventana. Muestra el progreso en la barra.",
            "Ejecuta MonteCarloWorker en un QThread independiente, invocando funciones C/BLAS vectorizadas de alta velocidad."
        ))
        self.btn_run_mc.clicked.connect(self._on_run_monte_carlo)
        lay_sim.addWidget(self.btn_run_mc)

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

        # Tabla de Métricas
        self.table_metrics = QTableWidget(18, 2)
        self.table_metrics.setHorizontalHeaderLabels(["Parámetro Metrológico", "Valor Experimental"])
        self.table_metrics.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table_metrics.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table_metrics.setAlternatingRowColors(True)
        self.table_metrics.setToolTip(make_tooltip(
            "Tabla Metrológica de Parámetros de Red",
            "Contiene todos los parámetros cuantitativos calculados organizados en 18 filas. Haga doble clic para copiar.",
            "Matriz estandarizada de resultados experimentales con propagación de errores e índices de consistencia cruzada."
        ))

        rows = [
            ("Archivo de Muestra", "-"),
            ("Dimensiones Nominales de Red (N x N)", "-"),
            ("Período Experimental a_x / a_y / a_mean", "-"),
            ("Anisotropía de Red (a_x - a_y)", "-"),
            ("Fracción de Vacancias f_vac", "-"),
            ("Desorden Espacio Real (KDTree) σ_x / σ_y", "-"),
            ("Desorden Espacio Real Medio σ_pos", "-"),
            ("Desorden Radial (g(r)) σ_rdf", "-"),
            ("Desorden Recíproco (Debye-Waller) σ_real,x / σ_real,y", "-"),
            ("Desorden Recíproco Medio σ_dw", "-"),
            ("Longitud de Correlación Espectral ξ_x / ξ_y", "-"),
            ("Diagnóstico de Deriva (FWHM_x / FWHM_y)", "-"),
            ("Consistencia Cruzada (Real vs Recíproco)", "-"),
            ("Aglomerados / Filamentos Detectados", "-"),
            ("Jerarquía de Bragg (H_diag/H1, H2/H1, SBR)", "-"),
            ("Mosaico Angular Δθ / Cizallamiento γ", "-"),
            ("Triple Inversión Debye-Waller (σ1 / σ_diag / σ2)", "-"),
            ("Inversión Analítica Directa σ(H₂/H₁) / σ(Wilson)", "-")
        ]
        for r, (param, val) in enumerate(rows):
            it0 = QTableWidgetItem(param)
            it0.setFlags(Qt.ItemFlag.ItemIsEnabled)
            it1 = QTableWidgetItem(val)
            it1.setFlags(Qt.ItemFlag.ItemIsEnabled)
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
        if self.img_item is not None:
            try:
                cm = get_pyqtgraph_colormap(cmap_name)
                self.img_item.setColorMap(cm)
            except Exception as e:
                print(f"Error actualizando colormap: {e}")

    def _on_layer_visibility_changed(self):
        if self.img_item is not None:
            self.img_item.setVisible(self.chk_layer_img.isChecked())
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
        if not self.btn_mode_click.isChecked():
            return
        if self.locs_df is None or self.locs_df.empty:
            return

        pos = event.scenePos()
        mouse_point = self.plot_real_space.plotItem.vb.mapSceneToView(pos)
        cx, cy = mouse_point.x(), mouse_point.y()

        x_nm = self.locs_df['x_nm'].values
        y_nm = self.locs_df['y_nm'].values
        dists = np.hypot(x_nm - cx, y_nm - cy)
        nearest_idx = int(np.argmin(dists))
        search_radius = self.spin_a_nominal.value() * 0.4
        if dists[nearest_idx] <= search_radius:
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
            tolerance_pct=tol
        )

        n_rem = stats.get('particles_removed', 0)
        n_add = stats.get('particles_added', 0)
        target_id_done = self.selected_cluster_id
        self.selected_cluster_id = None
        self.locs_df = df_resolved
        self.selected_particle_indices.clear()
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

        df_resolved, stats = resolve_single_spot_multi_gaussian(
            df=self.locs_df,
            spot_index=spot_idx,
            n_particles=n_fit,
            image_2d=self.image_2d,
            signature_dict=self.monomer_signature,
            scale_nm=scale_nm,
            a_nominal=a_nom
        )

        if stats.get('status') == 'ok':
            self.locs_df = df_resolved
            self.selected_particle_indices.clear()
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

    def _on_scatter_det_clicked(self, item, points):
        if len(points) == 0:
            return
        pt = points[0]
        pos = pt.pos()
        if self.locs_df is None or len(self.locs_df) == 0:
            return
        x = self.locs_df['x_nm'].values
        y = self.locs_df['y_nm'].values
        dists = np.hypot(x - pos.x(), y - pos.y())
        idx_min = int(np.argmin(dists))
        search_r = self.spin_a_nominal.value() * 0.4
        if dists[idx_min] < search_r:
            if idx_min in self.selected_particle_indices:
                self.selected_particle_indices.remove(idx_min)
            else:
                self.selected_particle_indices.add(idx_min)
            self._update_selected_status()
            self._redraw_selection_overlay()

    def _on_recalc_grid(self):
        if self.locs_df is None or self.locs_df.empty:
            return
        self._update_real_space_analysis()
        self._on_recalculate_reciprocal()

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

            # Procesar directamente
            self._update_real_space_analysis()
            self._on_recalculate_reciprocal()

            QMessageBox.information(
                self,
                "Coordenadas Cargadas",
                f"Se cargaron {len(df)} coordenadas directas.\n"
                "Se omitió la etapa de detección y se calcularon métricas de espacio real y Fourier."
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
                    img_to_process = apply_richardson_lucy(
                        img_to_process,
                        psf_sigma=self.spin_rl_sigma.value(),
                        num_iter=self.spin_rl_iter.value()
                    )

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

            self._update_real_space_analysis()
            self._on_recalculate_reciprocal()

            if self.kdtree_results and self.kdtree_results.get('excess_particles', False):
                QMessageBox.warning(
                    self,
                    "⚠️ Alerta: Partículas Excedentes",
                    f"{self.kdtree_results['excess_alert']}\n\n"
                    "Sugerencia: Use las 4 reglas móviles de la Pestaña 1 y presione '✂️ Aplicar Recorte' "
                    "para aislar la red y excluir partículas de fondo o impurezas."
                )
            else:
                QMessageBox.information(
                    self,
                    "Detección Exitosa",
                    f"Se detectaron {len(self.locs_df)} partículas (Total en imagen: {len(self.locs_df_raw)}).\n"
                    "Métricas actualizadas en Espacio Real y Espacio Recíproco."
                )
        except Exception as e:
            QMessageBox.critical(self, "Error en Detección", f"Detalle: {str(e)}")

    def _update_real_space_analysis(self):
        scale_nm = self.spin_scale.value()
        a_nom = self.spin_a_nominal.value()
        n_side = self.spin_n_side.value()

        # Visualizar en plot_real_space
        self.plot_real_space.clear()

        if self.image_2d is not None:
            self.img_item = pg.ImageItem(self.image_2d.T)
            self.img_item.setRect(pg.QtCore.QRectF(
                0, 0, self.image_2d.shape[1] * scale_nm, self.image_2d.shape[0] * scale_nm
            ))
            cmap_name = self.combo_colormap.currentText()
            self.img_item.setColorMap(get_pyqtgraph_colormap(cmap_name))
            self.img_item.setVisible(self.chk_layer_img.isChecked())
            self.plot_real_space.addItem(self.img_item)
        else:
            self.img_item = None

        # Superponer partículas si existen
        if self.locs_df is not None and len(self.locs_df) > 0:
            x_nm = self.locs_df['x_nm'].values
            y_nm = self.locs_df['y_nm'].values

            margin_pct = self.spin_consistency_margin.value() if hasattr(self, 'spin_consistency_margin') else 10.0
            # 1. KDTree Bounded con chequeo de margen físico
            self.kdtree_results = analyze_real_space_kdtree(
                x_nm, y_nm, a=a_nom, n_side=n_side, margin_percent=margin_pct
            )

            # 2. Función de Distribución Radial g(r)
            self.rdf_results = compute_radial_distribution_function(x_nm, y_nm, a_nominal=a_nom)

            # Actualizar tarjeta de métricas
            kd = self.kdtree_results
            rdf = self.rdf_results

            det_info = (
                f"Sitios Totales N²: {kd['N_total_sites']} | Ocupados: {kd.get('matched_count', 0)}\n"
                f"Vacancias (N² - N_occ): {kd['vacant_count']} ({kd['f_vac_percent']:.1f}%)\n"
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

            # Superponer partículas detectadas (Cian)
            self.scatter_det = pg.ScatterPlotItem(
                x=x_nm,
                y=y_nm,
                size=8,
                pen=pg.mkPen('#89dceb', width=1.5),
                brush=pg.mkBrush(137, 220, 235, 120),
                symbol='o'
            )
            self.scatter_det.sigClicked.connect(self._on_scatter_det_clicked)
            self.scatter_det.setVisible(self.chk_layer_det.isChecked())
            self.plot_real_space.addItem(self.scatter_det)

            # Detección de Aglomerados y Cadenas (Gusanitos/Dímeros/Sobrepuestas) con Fotometría
            photons_arr = self.locs_df['photons'].values if 'photons' in self.locs_df.columns else (self.locs_df['mass'].values if 'mass' in self.locs_df.columns else None)
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
            if self.cluster_results and 'signature' in self.cluster_results and self.cluster_results['signature']:
                self.monomer_signature = self.cluster_results['signature']
            self._update_cluster_table()

            # Dibujar líneas de conexión entre pares en cúmulo
            self.cluster_lines_items = []
            if self.cluster_results and len(self.cluster_results.get('pair_lines', [])) > 0:
                for (lx1, ly1, lx2, ly2) in self.cluster_results['pair_lines']:
                    line_item = pg.PlotDataItem(
                        [lx1, lx2], [ly1, ly2],
                        pen=pg.mkPen('#fab387', width=2, style=Qt.PenStyle.DashLine)
                    )
                    line_item.setVisible(self.chk_layer_clusters.isChecked())
                    self.plot_real_space.addItem(line_item)
                    self.cluster_lines_items.append(line_item)

            # Dibujar contornos fotométricos segmentados (Amarillo suave)
            self.cluster_contour_items = []
            self.highlight_contour_item = None
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
                        c_item.setVisible(self.chk_layer_contours.isChecked())
                        self.plot_real_space.addItem(c_item)
                        self.cluster_contour_items.append(c_item)

            # Superponer partículas pertenecientes a aglomerados (Naranja suave / Triángulo)
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
                    self.scatter_clusters.setVisible(self.chk_layer_clusters.isChecked())
                    self.plot_real_space.addItem(self.scatter_clusters)
                else:
                    self.scatter_clusters = None
            else:
                self.scatter_clusters = None

            # Superponer vacancias (Rojo)
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
                self.scatter_vac.setVisible(self.chk_layer_vac.isChecked())
                self.plot_real_space.addItem(self.scatter_vac)
            else:
                self.scatter_vac = None

            # Superponer malla ideal (Gris suave / Cruz)
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
                self.scatter_grid.setVisible(self.chk_layer_grid.isChecked())
                self.plot_real_space.addItem(self.scatter_grid)
            else:
                self.scatter_grid = None

            # Redibujar superposición de selección activa
            self._redraw_selection_overlay()

            # Graficar g(r)
            self.plot_rdf.clear()
            if len(rdf['r']) > 0:
                self.plot_rdf.plot(
                    rdf['r'], rdf['gr'],
                    pen=pg.mkPen('#a6e3a1', width=2),
                    name='g(r)'
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

            if self.reciprocal_results is not None:
                self._update_analytical_panels_and_plots(self.reciprocal_results)
            self._update_metrics_table()

        # Re-agregar las 4 reglas móviles de ROI
        for line in [self.line_roi_xmin, self.line_roi_xmax, self.line_roi_ymin, self.line_roi_ymax]:
            if line not in self.plot_real_space.items():
                self.plot_real_space.addItem(line)
            line.setVisible(self.chk_layer_roi.isChecked())

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

        # Análisis espectral completo
        self.reciprocal_results = analyze_reciprocal_space_2d(
            x_nm, y_nm,
            a_nominal=a_nom,
            n_bins=n_bins,
            band_width_bins=band_bins,
            dc_cut_factor=dc_cut
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
        if res['fit_x']['success']:
            self.plot_cut_x.plot(
                res['fit_x']['fit_f'], res['fit_x']['fit_curve'],
                pen=pg.mkPen('#a6e3a1', width=2, style=Qt.PenStyle.DashLine),
                name='Fit 1er Orden'
            )
        if res.get('fit_x_2nd') and res['fit_x_2nd']['success']:
            self.plot_cut_x.plot(
                res['fit_x_2nd']['fit_f'], res['fit_x_2nd']['fit_curve'],
                pen=pg.mkPen('#f9e2af', width=1.8, style=Qt.PenStyle.DashLine),
                name='Fit 2do Orden'
            )

        # Graficar cortes 1D: Eje Y
        self.plot_cut_y.clear()
        self.plot_cut_y.plot(fy, res['profile_y'], pen=pg.mkPen('#cba6f7', width=2), name='Exp')
        if res['fit_y']['success']:
            self.plot_cut_y.plot(
                res['fit_y']['fit_f'], res['fit_y']['fit_curve'],
                pen=pg.mkPen('#a6e3a1', width=2, style=Qt.PenStyle.DashLine),
                name='Fit 1er Orden'
            )
        if res.get('fit_y_2nd') and res['fit_y_2nd']['success']:
            self.plot_cut_y.plot(
                res['fit_y_2nd']['fit_f'], res['fit_y_2nd']['fit_curve'],
                pen=pg.mkPen('#f9e2af', width=1.8, style=Qt.PenStyle.DashLine),
                name='Fit 2do Orden'
            )

        # Graficar cortes 1D: Diagonal 45°
        if hasattr(self, 'plot_cut_diag'):
            self.plot_cut_diag.clear()
            self.plot_cut_diag.plot(res['f_diag'], res['profile_diag'], pen=pg.mkPen('#f38ba8', width=2), name='Exp Diag')
            if res.get('fit_diag') and res['fit_diag']['success']:
                self.plot_cut_diag.plot(
                    res['fit_diag']['fit_f'], res['fit_diag']['fit_curve'],
                    pen=pg.mkPen('#cba6f7', width=1.8, style=Qt.PenStyle.DashLine),
                    name='Fit (1,1)'
                )

        self._update_analytical_panels_and_plots(res)
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
        self.lbl_card_h2h1.setText(
            f"<b>σ (H₂ / H₁): {s_h2h1:.2f} nm</b><br>"
            f"<span style='color: #a6adc8; font-size: 10px;'>"
            f"Estándar de Oro (Cancela p y N)<br>"
            f"H₂/H₁ = {r_21:.3f} | σ_x = {s_h2h1_x:.1f} nm, σ_y = {s_h2h1_y:.1f} nm<br>"
            f"Fórmula: σ = (a / 2π√3) √(ln(H₁/H₂))</span>"
        )

        # Card 2: H_diag / H1 (Coherencia 2D)
        s_diag = ana.get('sigma_diag', 0.0)
        r_diag = ana.get('ratio_diag', 0.0)
        self.lbl_card_diag.setText(
            f"<b>σ (H_diag / H₁): {s_diag:.2f} nm</b><br>"
            f"<span style='color: #a6adc8; font-size: 10px;'>"
            f"Coherencia 2D (Orden cruzado (1,1))<br>"
            f"H_diag/H₁ = {r_diag:.3f}<br>"
            f"Fórmula: σ = (a / 2π) √(ln(H₁/H_diag))</span>"
        )

        # Card 3: H1 / H0 (Inestable)
        s_10 = ana.get('sigma_h1h0', 0.0)
        r_10 = ana.get('ratio_10', 0.0)
        h0 = ana.get('H0', 0.0)
        self.lbl_card_h1h0.setText(
            f"<b>σ (H₁ / H₀): {s_10:.2f} nm</b> <span style='color: #f38ba8; font-weight: bold; font-size: 10px;'>[⚠️ INESTABLE]</span><br>"
            f"<span style='color: #a6adc8; font-size: 10px;'>"
            f"Razón frente a DC Central (H₀ = {h0:.2e})<br>"
            f"H₁/H₀ = {r_10:.4f}<br>"
            f"Sensible a autofluorescencia, haz directo y N</span>"
        )

        # Card 4: Gráfico de Wilson
        s_w = ana.get('sigma_wilson', 0.0)
        r2_w = ana.get('r_squared_wilson', 0.0)
        p_est = ana.get('p_wilson_est', 0.0) * 100.0
        slope_w = ana.get('slope_wilson', 0.0)
        self.lbl_card_wilson.setText(
            f"<b>σ (Wilson Plot): {s_w:.2f} nm</b> (R²: {r2_w:.3f})<br>"
            f"<span style='color: #a6adc8; font-size: 10px;'>"
            f"Ajuste lineal multi-orden ln(H) vs |G|² (m = {slope_w:.2e})<br>"
            f"Vacancias estimadas: p_est = {p_est:.1f}%</span>"
        )

        # Card 5: Diagnóstico Paracristalino
        para = ana.get('paracrystal_diagnosis', {})
        r_fwhm = para.get('ratio_fwhm', 1.0)
        d_type = para.get('disorder_type', 'Pendiente')
        d_desc = para.get('description', '')
        is_type_1 = para.get('is_type_1', True)
        color_type = '#a6e3a1' if is_type_1 else '#f9e2af'
        self.lbl_card_paracrystal.setText(
            f"<b>Diagnóstico: <span style='color: {color_type};'>{d_type}</span></b><br>"
            f"<span style='color: #a6adc8; font-size: 10px;'>"
            f"Ratio FWHM₂ / FWHM₁ = {r_fwhm:.2f}<br>"
            f"{d_desc}</span>"
        )

        # ── 2. Gráfico 1: Gráfico de Wilson (ln(H) vs |G|²) ──────────────────
        if hasattr(self, 'plot_wilson'):
            self.plot_wilson.clear()
            w_data = ana.get('wilson_data', {})
            g_sq = w_data.get('g_sq')
            ln_h = w_data.get('ln_h')
            fit_g_sq = w_data.get('fit_g_sq')
            fit_ln_h = w_data.get('fit_ln_h')
            names = w_data.get('names', [])

            if fit_g_sq is not None and fit_ln_h is not None and len(fit_g_sq) > 0:
                self.plot_wilson.plot(
                    fit_g_sq, fit_ln_h,
                    pen=pg.mkPen('#89b4fa', width=2, style=Qt.PenStyle.DashLine),
                    name=f'Ajuste (R²={r2_w:.3f})'
                )

            if g_sq is not None and ln_h is not None and len(g_sq) > 0:
                scatter_w = pg.ScatterPlotItem(
                    x=g_sq, y=ln_h, size=11,
                    pen=pg.mkPen('#1e1e2e', width=1.5),
                    brush=pg.mkBrush('#a6e3a1'),
                    symbol='o'
                )
                self.plot_wilson.addItem(scatter_w)

                for g, h, nm in zip(g_sq, ln_h, names):
                    ti = pg.TextItem(text=f" {nm}", color='#bac2de', anchor=(0, 0.5))
                    ti.setPos(g, h)
                    self.plot_wilson.addItem(ti)
            self.plot_wilson.enableAutoRange()

        # ── 3. Gráfico 2: Decaimiento Multiórden Debye-Waller ────────────────
        if hasattr(self, 'plot_dw_decay'):
            self.plot_dw_decay.clear()
            dw_data = ana.get('debye_waller_curve', {})
            q_norm = dw_data.get('q_norm')
            h_theory = dw_data.get('H_theory')
            pts_q = dw_data.get('points_q')
            pts_h = dw_data.get('points_H')
            labels = dw_data.get('labels', [])

            if q_norm is not None and h_theory is not None:
                self.plot_dw_decay.plot(
                    q_norm, h_theory,
                    pen=pg.mkPen('#a6e3a1', width=2),
                    name='Teoría DW e^{-ΔG²σ²}'
                )

            if pts_q is not None and pts_h is not None:
                scatter_dw = pg.ScatterPlotItem(
                    x=pts_q, y=pts_h, size=12,
                    pen=pg.mkPen('#1e1e2e', width=1.5),
                    brush=pg.mkBrush('#fab387'),
                    symbol='d'
                )
                self.plot_dw_decay.addItem(scatter_dw)

                for q, h, lbl in zip(pts_q, pts_h, labels):
                    ti = pg.TextItem(text=f" {lbl} ({h:.2f})", color='#cdd6f4', anchor=(0, 0.5))
                    ti.setPos(q, h)
                    self.plot_dw_decay.addItem(ti)
            self.plot_dw_decay.enableAutoRange()

        # ── 4. Gráfico 3: Comparativa de Estabilidad de Ratios ────────────────
        if hasattr(self, 'plot_ratio_stability'):
            self.plot_ratio_stability.clear()
            stab = ana.get('stability_comparison', {})
            methods = stab.get('methods', ['H2/H1 (Oro)', 'Diag (1,1)', 'Wilson', 'H1/H0 (Inest.)'])
            raw_sigmas = stab.get('sigmas', [s_h2h1, s_diag, s_w, s_10])
            sigmas = [0.0 if np.isnan(s) else max(0.0, float(s)) for s in raw_sigmas]
            colors = stab.get('colors', ['#a6e3a1', '#cba6f7', '#89b4fa', '#f38ba8'])

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

        # ── 5. Gráfico 4: Diagnóstico de Ancho Radial (Hosemann) ──────────────
        if hasattr(self, 'plot_fwhm_paracrystal'):
            self.plot_fwhm_paracrystal.clear()
            f1 = para.get('fwhm_order1', 0.0)
            f2 = para.get('fwhm_order2', 0.0)

            if f1 > 0:
                m_orders = np.array([1.0, 2.0])
                fwhm_vals = np.array([f1, f2 if f2 > 0 else f1])
                scatter_fwhm = pg.ScatterPlotItem(
                    x=m_orders, y=fwhm_vals, size=12,
                    pen=pg.mkPen('#1e1e2e', width=1.5),
                    brush=pg.mkBrush('#f9e2af'),
                    symbol='t'
                )
                self.plot_fwhm_paracrystal.addItem(scatter_fwhm)

                # Modelos teóricos de comparación
                m_dense = np.linspace(0.8, 2.2, 50)
                # Modelo Tipo I: Debye-Waller Puro (Scherrer FWHM constante)
                self.plot_fwhm_paracrystal.plot(
                    m_dense, np.full_like(m_dense, f1),
                    pen=pg.mkPen('#a6e3a1', width=1.8, style=Qt.PenStyle.DashLine),
                    name='Tipo I: DW (FWHM cte)'
                )
                # Modelo Tipo II: Paracristal de Hosemann (FWHM ~ m²)
                f_hosemann = f1 * (m_dense ** 2)
                self.plot_fwhm_paracrystal.plot(
                    m_dense, f_hosemann,
                    pen=pg.mkPen('#f38ba8', width=1.5, style=Qt.PenStyle.DotLine),
                    name='Tipo II: Hosemann (m²)'
                )

                ax4 = self.plot_fwhm_paracrystal.getAxis('bottom')
                ax4.setTicks([[(1, 'm = 1 (10)'), (2, 'm = 2 (20)')]])

                ti1 = pg.TextItem(text=f" FWHM₁={f1:.4f} nm⁻¹", color='#bac2de', anchor=(0, 0.5))
                ti1.setPos(1.0, f1)
                self.plot_fwhm_paracrystal.addItem(ti1)

                if f2 > 0:
                    ti2 = pg.TextItem(text=f" FWHM₂={f2:.4f} nm⁻¹", color='#bac2de', anchor=(0, 0.5))
                    ti2.setPos(2.0, f2)
                    self.plot_fwhm_paracrystal.addItem(ti2)
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

        self.plot_dw.clear()

        # 1. Graficar Curvas de Calibración MC y Ajustes
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
        if show_multi and 'H_mean_diag' in mc and mc['H_mean_diag'] is not None:
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

        if show_multi and 'H_mean_2' in mc and mc['H_mean_2'] is not None:
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
                self.plot_dw.plot([0, sx, sx], [Hx, Hx, 0], pen=pg.mkPen('#89b4fa', width=1.5, style=Qt.PenStyle.DashLine))
                self.plot_dw.plot([0, sy, sy], [Hy, Hy, 0], pen=pg.mkPen('#f38ba8', width=1.5, style=Qt.PenStyle.DashLine))
            else:
                sx, ds_x = interpolate_disorder(Hx, s_vals, mc['H_mean'], mc['H_std'])
                sy, ds_y = interpolate_disorder(Hy, s_vals, mc['H_mean'], mc['H_std'])
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
                if show_multi:
                    self.plot_dw.plot([0, s_diag, s_diag], [H_meas_diag, H_meas_diag, 0], pen=pg.mkPen('#cba6f7', width=1.5, style=Qt.PenStyle.DashLine))

            # Inversión 2do Orden
            s_2 = None
            ds_2 = 0.0
            if 'H_x_2nd' in r and 'H_mean_2' in mc and mc['H_mean_2'] is not None:
                H_meas_2 = r['H_x_2nd']
                s_2, ds_2 = interpolate_disorder(H_meas_2, s_vals, mc['H_mean_2'], mc.get('H_std_2'))
                mc['s_2_interp'] = s_2
                if show_multi:
                    self.plot_dw.plot([0, s_2, s_2], [H_meas_2, H_meas_2, 0], pen=pg.mkPen('#f9e2af', width=1.5, style=Qt.PenStyle.DashLine))

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
                s_w = ana.get('sigma_wilson', 0.0)
                r2_w = ana.get('r_squared_wilson', 0.0)
                self.table_metrics.item(17, 1).setText(
                    f"σ(H2/H1)={s_h2h1:.2f} nm | σ(Wilson)={s_w:.2f} nm (R²={r2_w:.3f})"
                )
            else:
                self.table_metrics.item(17, 1).setText("Pendiente (requiere Espacio Recíproco)")

        if self.kdtree_results is not None:
            kd = self.kdtree_results
            c_ratio = kd.get('consistency_sum', kd['particles_detected'] + kd['vacant_count'])
            tot = kd.get('N_total_sites', self.spin_n_side.value() ** 2)
            c_tag = f" [Suma M+Vac={c_ratio}/{tot}]"
            self.table_metrics.item(4, 1).setText(f"{kd['f_vac_percent']:.1f}% ({kd['vacant_count']} vacancias){c_tag}")
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
