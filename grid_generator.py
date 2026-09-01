"""
grid_generator.py - Diseñador Universal de Redes Cristalinas 2D para PyPrinting 3.0
===================================================================================
Aplicación interactiva y módulo independiente para la generación, rotación,
superposición y recorte de cualquier red cristalina 2D (5 Redes de Bravais,
Grafeno, Kagome, Lieb, Moiré) con soporte para hasta 3 materiales coloidales,
delimitación por figuras geométricas (hexágonos, círculos, rectángulos) y
cuadratura de precisión mediante Partícula Ancla (P0) para nanofabricación secuencial.

Autor: Equipo PyPrinting 3.0 / INS-UNSAM
Fecha: Agosto 2026
"""

import sys
import os
import math
import json
import numpy as np

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QSize
from PyQt6.QtGui import QFont, QIcon, QColor, QPen, QBrush
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QLineEdit, QPushButton, QComboBox,
    QSpinBox, QDoubleSpinBox, QCheckBox, QTabWidget, QGroupBox,
    QFileDialog, QMessageBox, QSplitter, QFrame, QScrollArea, QSlider
)
import pyqtgraph as pg

# Configuración global de pyqtgraph
pg.setConfigOption('background', '#11111b')
pg.setConfigOption('foreground', '#cdd6f4')
pg.setConfigOption('antialias', True)

from core.lattice_generator import (
    BasisAtom, LatticeLayer, BoundingGeometry, PathOptimizer,
    AnchorConfig, CrystalGridComposer, CrystalGridExporter
)


# ══════════════════════════════════════════════════════════════════════════════
#  PALETA DE COLORES Y ESTILOS CATPPUCCIN MOCHA
# ══════════════════════════════════════════════════════════════════════════════

STYLE_SHEET = """
QMainWindow, QWidget {
    background-color: #181825;
    color: #cdd6f4;
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 9pt;
}

QGroupBox {
    border: 1px solid #313244;
    border-radius: 6px;
    margin-top: 10px;
    font-weight: bold;
    color: #cba6f7;
    padding-top: 10px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 4px;
}

QTabWidget::pane {
    border: 1px solid #313244;
    border-radius: 6px;
    background-color: #1e1e2e;
}
QTabBar::tab {
    background-color: #181825;
    color: #a6adc8;
    padding: 6px 12px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background-color: #313244;
    color: #89b4fa;
    font-weight: bold;
}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #11111b;
    border: 1px solid #45475a;
    border-radius: 4px;
    color: #cdd6f4;
    padding: 3px 6px;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border: 1px solid #89b4fa;
}

QPushButton {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 4px;
    color: #cdd6f4;
    font-weight: bold;
    padding: 5px 10px;
}
QPushButton:hover {
    background-color: #45475a;
    color: #ffffff;
}
QPushButton:pressed {
    background-color: #585b70;
}

QPushButton#btn_primary {
    background-color: #2e7d32;
    border: 1px solid #4caf50;
    color: white;
}
QPushButton#btn_primary:hover {
    background-color: #388e3c;
}

QPushButton#btn_accent {
    background-color: #89b4fa;
    border: 1px solid #b4befe;
    color: #11111b;
}
QPushButton#btn_accent:hover {
    background-color: #b4befe;
}

QCheckBox {
    spacing: 6px;
}
QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #45475a;
    border-radius: 3px;
    background-color: #11111b;
}
QCheckBox::indicator:checked {
    background-color: #89b4fa;
    border-color: #89b4fa;
}
"""

MATERIAL_COLORS = {
    1: {"name": "Material 1 (Au 60nm)", "hex": "#89b4fa", "symbol": "o", "brush": "#89b4fa"},
    2: {"name": "Material 2 (Ag 40nm)", "hex": "#a6e3a1", "symbol": "t", "brush": "#a6e3a1"},
    3: {"name": "Material 3 (Au 100nm)", "hex": "#f38ba8", "symbol": "s", "brush": "#f38ba8"},
}


# ══════════════════════════════════════════════════════════════════════════════
#  VENTANA PRINCIPAL: GRID GENERATOR
# ══════════════════════════════════════════════════════════════════════════════

class GridGeneratorWindow(QMainWindow):
    """Ventana interactiva de diseño y síntesis de redes cristalinas 2D."""

    gridGeneratedSignal = pyqtSignal(dict)  # Emite el diccionario generado para integración

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📐 Diseñador Universal de Redes Cristalinas 2D — PyPrinting 3.0")
        self.resize(1180, 780)
        self.setStyleSheet(STYLE_SHEET)

        self.composer = CrystalGridComposer()
        self._current_result: Optional[Dict] = None

        self._setup_ui()
        self._on_params_changed()

    def _setup_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(6)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)

        # ── Panel Izquierdo: Configuración y Controles ────────────────────────
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QFrame.Shape.NoFrame)
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(6, 6, 6, 6)
        left_layout.setSpacing(8)

        # 1. Encabezado & Presets Rápidos
        header_gb = QGroupBox("✨ Presets Rápidos de Estructuras 2D")
        hlo = QHBoxLayout(header_gb)
        self.preset_combo = QComboBox()
        self.preset_combo.addItems([
            "Personalizado / Libre",
            "🔷 Red Hexagonal en Hexágono (ap=5.0 µm, a=2.0 µm)",
            "🟦 Red Cuadrada 5x5 (a=3.0 µm)",
            "🐝 Grafeno / Honeycomb en Disco (R=5.0 µm, a=2.5 µm)",
            "✡️ Red Kagome en Hexágono (ap=6.0 µm, a=3.0 µm)",
            "🌀 Superred Moiré Rotada (Hexagonal θ=2.5°)",
            "🔲 Red Cuadrada Centrada (Corner + Center, a=3.0 µm)",
            "🪐 Corona Circular / Anillo Hexagonal (R_in=2, R_out=6 µm)",
            "🔺 Triángulo Equilátero Kagome (L=12 µm)"
        ])
        self.preset_combo.currentIndexChanged.connect(self._apply_preset)
        hlo.addWidget(self.preset_combo)
        left_layout.addWidget(header_gb)

        # 2. Pestañas de Parámetros
        self.tabs = QTabWidget()

        # Pestaña A: Capas Cristalográficas (Lattice Layers)
        self._setup_layer_tab()

        # Pestaña B: Geometría Contenedora (Bounding Mask)
        self._setup_geometry_tab()

        # Pestaña C: Partícula Ancla (P0) & Multi-Paso
        self._setup_anchor_tab()

        # Pestaña D: Ruta de Platina PI
        self._setup_path_tab()

        left_layout.addWidget(self.tabs)

        # 3. Vista Previa de la Celda Unidad (Unit Cell Preview)
        unit_cell_gb = QGroupBox("🔬 Celda Unidad de la Capa Activa")
        uclo = QVBoxLayout(unit_cell_gb)
        uclo.setContentsMargins(6, 6, 6, 6)
        uclo.setSpacing(4)

        self.unit_cell_plot = pg.PlotWidget()
        self.unit_cell_plot.setMinimumHeight(160)
        self.unit_cell_plot.setMaximumHeight(190)
        self.unit_cell_plot.setAspectLocked(True)
        self.unit_cell_plot.showGrid(x=True, y=True, alpha=0.25)
        self.unit_cell_plot.setLabel('bottom', 'a₁', units='µm')
        self.unit_cell_plot.setLabel('left', 'a₂', units='µm')
        self.unit_cell_plot.setTitle("Base Atómica & Vectores Primitivos", color='#cba6f7', size='9pt')
        uclo.addWidget(self.unit_cell_plot)

        self.lbl_unit_cell_info = QLabel("a = 3.00 µm, b = 3.00 µm, γ = 60.0° | 1 átomo")
        self.lbl_unit_cell_info.setStyleSheet("font-family: monospace; font-size: 8pt; color: #a6adc8;")
        self.lbl_unit_cell_info.setWordWrap(True)
        uclo.addWidget(self.lbl_unit_cell_info)

        left_layout.addWidget(unit_cell_gb)

        # 4. Panel de Exportación y Acciones
        export_gb = QGroupBox("💾 Exportación y Recetas Multi-Paso")
        elo = QGridLayout(export_gb)

        elo.addWidget(QLabel("Nombre Lote:"), 0, 0)
        self.batch_name_edit = QLineEdit("Lattice_2D_Structure")
        elo.addWidget(self.batch_name_edit, 0, 1, 1, 2)

        self.btn_export_single = QPushButton("💾 Exportar .txt Unificado")
        self.btn_export_single.setObjectName("btn_primary")
        self.btn_export_single.setToolTip("Exporta archivo .txt estándar de 2 columnas listo para 'Load grid' en Measurements.")
        self.btn_export_single.clicked.connect(self._export_single)

        self.btn_export_multipass = QPushButton("📦 Paquete Receta Multi-Paso (P0)")
        self.btn_export_multipass.setObjectName("btn_accent")
        self.btn_export_multipass.setToolTip("Genera archivos individuales por material con cuadratura estricta de la Partícula Ancla P0.")
        self.btn_export_multipass.clicked.connect(self._export_multipass)

        self.btn_export_png = QPushButton("🖼️ Exportar PNG")
        self.btn_export_png.clicked.connect(self._export_png)

        elo.addWidget(self.btn_export_single, 1, 0, 1, 3)
        elo.addWidget(self.btn_export_multipass, 2, 0, 1, 2)
        elo.addWidget(self.btn_export_png, 2, 2)

        left_layout.addWidget(export_gb)
        left_layout.addStretch()

        left_scroll.setWidget(left_widget)
        splitter.addWidget(left_scroll)

        # ── Panel Derecho: Visualizador 2D Interactivo (pyqtgraph) ────────────
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(6, 6, 6, 6)
        right_layout.setSpacing(4)

        # Barra Superior de Control Visual de Trayectorias
        view_bar = QFrame()
        view_bar.setStyleSheet("background-color: #1e1e2e; border: 1px solid #313244; border-radius: 6px; padding: 2px 6px;")
        vblo = QHBoxLayout(view_bar)
        vblo.setContentsMargins(4, 2, 4, 2)
        vblo.setSpacing(8)

        vblo.addWidget(QLabel("👁️ <b>Visualizar Ruta:</b>"))
        self.path_view_combo = QComboBox()
        self.path_view_combo.addItems([
            "🌐 Todas las Capas (Trayectoria Global)",
            "✨ Rutas Multi-Paso Separadas (1 trazo por material)",
            "🔷 Solo Paso 1 (Material 1 — Au 60nm)",
            "🟢 Solo Paso 2 (Material 2 — Ag 40nm)",
            "🌸 Solo Paso 3 (Material 3 — Au 100nm)"
        ])
        self.path_view_combo.currentIndexChanged.connect(self._render_plot)
        vblo.addWidget(self.path_view_combo)

        self.chk_show_numbers = QCheckBox("🔢 Números de Orden")
        self.chk_show_numbers.setToolTip("Muestra el índice secuencial exacto (1, 2, 3...) de recorrido de la platina PI.")
        self.chk_show_numbers.stateChanged.connect(self._render_plot)
        vblo.addWidget(self.chk_show_numbers)

        self.chk_show_path = QCheckBox("🛤️ Líneas de Trayectoria")
        self.chk_show_path.setChecked(True)
        self.chk_show_path.stateChanged.connect(self._render_plot)
        vblo.addWidget(self.chk_show_path)

        vblo.addStretch()
        right_layout.addWidget(view_bar)

        # Gráfico 2D
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setAspectLocked(True)
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.setLabel('bottom', 'Coordenada X', units='µm')
        self.plot_widget.setLabel('left', 'Coordenada Y', units='µm')
        self.plot_widget.setTitle("🗺️ Visualización 2D de la Red Cristalina", color='#cba6f7', size='11pt')
        right_layout.addWidget(self.plot_widget)

        # Barra de Telemetría Inferior
        telemetry_gb = QGroupBox("📊 Métricas de Estructura y Trayectoria")
        tlo = QHBoxLayout(telemetry_gb)
        self.lbl_stats_total = QLabel("N Total: 0")
        self.lbl_stats_total.setStyleSheet("font-weight: bold; color: #cdd6f4;")
        self.lbl_stats_mat = QLabel("Mat 1: 0 | Mat 2: 0 | Mat 3: 0")
        self.lbl_stats_mat.setStyleSheet("color: #89b4fa; font-family: monospace;")
        self.lbl_stats_dims = QLabel("Dim: 0.0 x 0.0 µm")
        self.lbl_stats_dims.setStyleSheet("color: #a6e3a1; font-family: monospace;")
        self.lbl_stats_path = QLabel("Trayectoria: 0.00 mm")
        self.lbl_stats_path.setStyleSheet("color: #f9e2af; font-family: monospace;")

        tlo.addWidget(self.lbl_stats_total)
        tlo.addWidget(self.lbl_stats_mat)
        tlo.addWidget(self.lbl_stats_dims)
        tlo.addWidget(self.lbl_stats_path)
        right_layout.addWidget(telemetry_gb)

        splitter.addWidget(right_widget)
        splitter.setSizes([460, 720])

    # ── Pestaña 1: Capas Cristalográficas ─────────────────────────────────────
    def _setup_layer_tab(self):
        tab = QWidget(); lo = QVBoxLayout(tab)

        # Selector de Capa Activa
        top_hlo = QHBoxLayout()
        top_hlo.addWidget(QLabel("Capa Activa:"))
        self.layer_combo = QComboBox()
        self.layer_combo.addItems(["Capa 1 (Primaria)", "Capa 2 (Sobrepuesta)", "Capa 3 (Multicapa)"])
        self.layer_combo.currentIndexChanged.connect(self._on_layer_selected)
        top_hlo.addWidget(self.layer_combo)

        self.layer_enable_check = QCheckBox("Habilitada")
        self.layer_enable_check.setChecked(True)
        self.layer_enable_check.stateChanged.connect(self._on_layer_enable_changed)
        top_hlo.addWidget(self.layer_enable_check)
        lo.addLayout(top_hlo)

        # Parámetros de Red
        grid_gb = QGroupBox("Parámetros de Red de Bravais 2D")
        glo = QGridLayout(grid_gb)

        glo.addWidget(QLabel("Tipo de Red:"), 0, 0)
        self.lattice_type_combo = QComboBox()
        self.lattice_type_combo.addItems([
            "Hexagonal / Triangular (60°)",
            "Cuadrada (Square 90°)",
            "Grafeno / Honeycomb (2 átomos: C1, C2)",
            "Nitruro de Boro / h-BN (2 átomos: B, N)",
            "Red Kagome (3 átomos: K1, K2, K3)",
            "Red de Lieb (3 átomos: L1, L2, L3)",
            "Red de Dice / T3 (3 átomos: Hub, Rim1, Rim2)",
            "Monocapa TMD / MoS2 (3 átomos: Mo, S1, S2)",
            "Cuadrada Centrada / Checkerboard (2 átomos)",
            "Rectangular Centrada (2 átomos)",
            "Triangular Decorada (2 átomos)",
            "Rectangular Simple",
            "Rómbica / Inclinada",
            "Oblicua General",
            "Personalizada / Libre (Custom Basis)"
        ])
        self.lattice_type_combo.currentIndexChanged.connect(self._on_lattice_type_changed)
        glo.addWidget(self.lattice_type_combo, 0, 1, 1, 3)

        glo.addWidget(QLabel("Vector a₁ (a µm):"), 1, 0)
        self.spin_a = QDoubleSpinBox()
        self.spin_a.setRange(0.1, 50.0); self.spin_a.setValue(3.0); self.spin_a.setSingleStep(0.2)
        self.spin_a.setDecimals(3)
        self.spin_a.setToolTip("Longitud física del vector de red primitivo a1 (|a1| en µm).")
        self.spin_a.valueChanged.connect(self._on_params_changed)
        glo.addWidget(self.spin_a, 1, 1)

        glo.addWidget(QLabel("Vector a₂ (b µm):"), 1, 2)
        self.spin_b = QDoubleSpinBox()
        self.spin_b.setRange(0.1, 50.0); self.spin_b.setValue(3.0); self.spin_b.setSingleStep(0.2)
        self.spin_b.setDecimals(3)
        self.spin_b.setToolTip("Longitud física del vector de red primitivo a2 (|a2| en µm).")
        self.spin_b.valueChanged.connect(self._on_params_changed)
        glo.addWidget(self.spin_b, 1, 3)

        glo.addWidget(QLabel("Ángulo γ (°):"), 2, 0)
        gamma_hlo = QHBoxLayout()
        self.spin_gamma = QDoubleSpinBox()
        self.spin_gamma.setRange(5.0, 175.0); self.spin_gamma.setValue(60.0); self.spin_gamma.setSingleStep(0.5)
        self.spin_gamma.setDecimals(1)
        self.spin_gamma.setFixedWidth(75)
        self.spin_gamma.setToolTip("Ángulo entre los vectores primitivos a1 y a2 (grados).")
        self.spin_gamma.valueChanged.connect(self._on_spin_gamma_changed)

        self.slider_gamma = QSlider(Qt.Orientation.Horizontal)
        self.slider_gamma.setRange(50, 1750)  # 5.0° a 175.0° (x10 para 0.1° de precisión)
        self.slider_gamma.setValue(600)
        self.slider_gamma.setToolTip("Deslizador para ajuste interactivo y continuo del ángulo γ.")
        self.slider_gamma.valueChanged.connect(self._on_slider_gamma_changed)

        gamma_hlo.addWidget(self.spin_gamma)
        gamma_hlo.addWidget(self.slider_gamma)
        glo.addLayout(gamma_hlo, 2, 1, 1, 3)

        glo.addWidget(QLabel("Distancia Mínima d_min (µm):"), 3, 0)
        self.spin_min_dist = QDoubleSpinBox()
        self.spin_min_dist.setRange(0.0, 25.0); self.spin_min_dist.setValue(0.0); self.spin_min_dist.setSingleStep(0.1); self.spin_min_dist.setDecimals(3)
        self.spin_min_dist.setSpecialValueText("Desactivada (0.0 µm)")
        self.spin_min_dist.setToolTip("Restricción de exclusión física: descarta cualquier partícula que quede a una distancia menor a d_min de otra ya existente (límite de resolución óptica/espaciado de impresión).")
        self.spin_min_dist.valueChanged.connect(self._on_params_changed)
        glo.addWidget(self.spin_min_dist, 3, 1, 1, 3)

        lo.addWidget(grid_gb)

        # Base Atómica & Coordenadas Fraccionales (u, v) por Átomo
        self.basis_gb = QGroupBox("⚛️ Base Atómica: Posiciones (u, v) y Materiales")
        self.basis_layout = QGridLayout(self.basis_gb)

        self.atom_rows = []
        for i in range(6):  # Soporta hasta 6 átomos en la base
            lbl_name = QLabel(f"A{i+1}:")
            lbl_name.setStyleSheet("font-weight: bold; color: #89b4fa; font-family: monospace;")
            
            spin_u = QDoubleSpinBox()
            spin_u.setRange(-2.0, 2.0); spin_u.setValue(0.0); spin_u.setSingleStep(0.05); spin_u.setDecimals(4)
            spin_u.setToolTip(f"Coordenada fraccional u_{i+1} a lo largo de a1 (r = u·a1 + v·a2).")
            spin_u.valueChanged.connect(lambda val, a_idx=i: self._on_atom_coord_changed(a_idx))

            spin_v = QDoubleSpinBox()
            spin_v.setRange(-2.0, 2.0); spin_v.setValue(0.0); spin_v.setSingleStep(0.05); spin_v.setDecimals(4)
            spin_v.setToolTip(f"Coordenada fraccional v_{i+1} a lo largo de a2 (r = u·a1 + v·a2).")
            spin_v.valueChanged.connect(lambda val, a_idx=i: self._on_atom_coord_changed(a_idx))

            combo_mat = QComboBox()
            combo_mat.addItems([
                "Material 1 (Au 60nm — Cian)",
                "Material 2 (Ag 40nm — Verde)",
                "Material 3 (Au 100nm — Rosa)"
            ])
            combo_mat.currentIndexChanged.connect(lambda idx, a_idx=i: self._on_atom_material_changed(a_idx, idx))

            self.basis_layout.addWidget(lbl_name, i, 0)
            self.basis_layout.addWidget(QLabel("u:"), i, 1)
            self.basis_layout.addWidget(spin_u, i, 2)
            self.basis_layout.addWidget(QLabel("v:"), i, 3)
            self.basis_layout.addWidget(spin_v, i, 4)
            self.basis_layout.addWidget(combo_mat, i, 5)

            self.atom_rows.append((lbl_name, spin_u, spin_v, combo_mat))

        # Botones de añadir / quitar átomo y resetear base
        atom_btns_hlo = QHBoxLayout()
        self.btn_add_atom = QPushButton("➕ Añadir Átomo")
        self.btn_add_atom.setToolTip("Añade un nuevo átomo a la base de la celda unidad.")
        self.btn_add_atom.clicked.connect(self._add_atom)

        self.btn_remove_atom = QPushButton("➖ Quitar Átomo")
        self.btn_remove_atom.setToolTip("Elimina el último átomo de la base de la celda unidad.")
        self.btn_remove_atom.clicked.connect(self._remove_atom)

        self.btn_reset_basis = QPushButton("🔄 Resetear Base")
        self.btn_reset_basis.setToolTip("Restaura la base atómica canónica correspondiente al tipo de red seleccionado.")
        self.btn_reset_basis.clicked.connect(self._reset_basis_canonical)

        atom_btns_hlo.addWidget(self.btn_add_atom)
        atom_btns_hlo.addWidget(self.btn_remove_atom)
        atom_btns_hlo.addWidget(self.btn_reset_basis)
        self.basis_layout.addLayout(atom_btns_hlo, 6, 0, 1, 6)

        lo.addWidget(self.basis_gb)

        # Transformaciones Afines (Rotación & Moiré)
        affine_gb = QGroupBox("Transformación Afín (Rotación Moiré & Desplazamiento)")
        alo = QGridLayout(affine_gb)

        alo.addWidget(QLabel("Rotación θ (°):"), 0, 0)
        self.spin_rot = QDoubleSpinBox()
        self.spin_rot.setRange(-360.0, 360.0); self.spin_rot.setValue(0.0); self.spin_rot.setSingleStep(0.5)
        self.spin_rot.valueChanged.connect(self._on_params_changed)
        alo.addWidget(self.spin_rot, 0, 1)

        alo.addWidget(QLabel("Offset X (µm):"), 1, 0)
        self.spin_off_x = QDoubleSpinBox()
        self.spin_off_x.setRange(-100.0, 100.0); self.spin_off_x.setValue(0.0); self.spin_off_x.setSingleStep(0.5)
        self.spin_off_x.valueChanged.connect(self._on_params_changed)
        alo.addWidget(self.spin_off_x, 1, 1)

        alo.addWidget(QLabel("Offset Y (µm):"), 1, 2)
        self.spin_off_y = QDoubleSpinBox()
        self.spin_off_y.setRange(-100.0, 100.0); self.spin_off_y.setValue(0.0); self.spin_off_y.setSingleStep(0.5)
        self.spin_off_y.valueChanged.connect(self._on_params_changed)
        alo.addWidget(self.spin_off_y, 1, 3)

        lo.addWidget(affine_gb)
        lo.addStretch()
        self.tabs.addTab(tab, "🔹 Capas Cristalográficas")

    # ── Pestaña 2: Geometría Contenedora ──────────────────────────────────────
    def _setup_geometry_tab(self):
        tab = QWidget(); lo = QVBoxLayout(tab)

        shape_gb = QGroupBox("Figura Contenedora / Máscara Espacial")
        slo = QGridLayout(shape_gb)

        slo.addWidget(QLabel("Geometría:"), 0, 0)
        self.geom_combo = QComboBox()
        self.geom_combo.addItems([
            "Hexágono Regular (por Apotema)",
            "Hexágono Regular (por Radio Exterior)",
            "Círculo / Disco (Radio R)",
            "Cuadrado / Rectángulo (Lx × Ly)",
            "Corona Circular / Anillo (R_in < r < R_out)",
            "Triángulo Equilátero (Lado L)",
            "Por Conteo de Celdas (Nx × Ny)"
        ])
        self.geom_combo.currentIndexChanged.connect(self._on_geom_type_changed)
        slo.addWidget(self.geom_combo, 0, 1, 1, 2)

        # Dimensiones
        self.lbl_dim1 = QLabel("Apotema ap (µm):")
        self.spin_dim1 = QDoubleSpinBox()
        self.spin_dim1.setRange(0.5, 100.0); self.spin_dim1.setValue(5.0); self.spin_dim1.setSingleStep(0.5)
        self.spin_dim1.valueChanged.connect(self._on_params_changed)
        slo.addWidget(self.lbl_dim1, 1, 0); slo.addWidget(self.spin_dim1, 1, 1)

        self.lbl_dim2 = QLabel("Dimensión 2 (µm):")
        self.spin_dim2 = QDoubleSpinBox()
        self.spin_dim2.setRange(0.5, 100.0); self.spin_dim2.setValue(5.0); self.spin_dim2.setSingleStep(0.5)
        self.spin_dim2.valueChanged.connect(self._on_params_changed)
        slo.addWidget(self.lbl_dim2, 1, 2); slo.addWidget(self.spin_dim2, 1, 3)

        lo.addWidget(shape_gb)

        desc_lbl = QLabel(
            "ℹ️ <b>Regla de Recorte:</b> El motor expande la red cristalina en el espacio infinito y "
            "recorta automáticamente los átomos que caen estrictamente dentro del polígono delimitador."
        )
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet("color: #a6adc8; font-size: 8pt; padding: 4px;")
        lo.addWidget(desc_lbl)

        lo.addStretch()
        self.tabs.addTab(tab, "📐 Geometría Contenedora")

    # ── Pestaña 3: Partícula Ancla (P0) ───────────────────────────────────────
    def _setup_anchor_tab(self):
        tab = QWidget(); lo = QVBoxLayout(tab)

        p0_gb = QGroupBox("Partícula Ancla (P0) — Eje de Cuadratura Multi-Paso")
        plo = QGridLayout(p0_gb)

        self.p0_enable_check = QCheckBox("Habilitar Partícula Ancla (P0) ⭐")
        self.p0_enable_check.setChecked(True)
        self.p0_enable_check.setStyleSheet("font-weight: bold; color: #f9e2af;")
        self.p0_enable_check.stateChanged.connect(self._on_params_changed)
        plo.addWidget(self.p0_enable_check, 0, 0, 1, 2)

        plo.addWidget(QLabel("Ubicación P0:"), 1, 0)
        self.p0_mode_combo = QComboBox()
        self.p0_mode_combo.addItems([
            "Offset Exterior de Seguridad",
            "Centro Geométrico (0, 0)",
            "Primer Nodo de la Red",
            "Coordenadas Personalizadas"
        ])
        self.p0_mode_combo.currentIndexChanged.connect(self._on_params_changed)
        plo.addWidget(self.p0_mode_combo, 1, 1)

        plo.addWidget(QLabel("Offset X (µm):"), 2, 0)
        self.spin_p0_off_x = QDoubleSpinBox()
        self.spin_p0_off_x.setRange(-50.0, 50.0); self.spin_p0_off_x.setValue(-2.0); self.spin_p0_off_x.setSingleStep(0.5)
        self.spin_p0_off_x.valueChanged.connect(self._on_params_changed)
        plo.addWidget(self.spin_p0_off_x, 2, 1)

        plo.addWidget(QLabel("Offset Y (µm):"), 3, 0)
        self.spin_p0_off_y = QDoubleSpinBox()
        self.spin_p0_off_y.setRange(-50.0, 50.0); self.spin_p0_off_y.setValue(-2.0); self.spin_p0_off_y.setSingleStep(0.5)
        self.spin_p0_off_y.valueChanged.connect(self._on_params_changed)
        plo.addWidget(self.spin_p0_off_y, 3, 1)

        lo.addWidget(p0_gb)

        info_p0 = QLabel(
            "⭐ <b>Protocolo de Nanofabricación Multi-Paso:</b><br>"
            "• <b>Paso 1 (Material 1)</b>: Se imprime primero la Partícula Ancla P0 en el nodo 0 y luego la Capa 1.<br>"
            "• <b>Paso 2 (Material 2)</b>: Tras lavar y cambiar el coloide, el microscopio ejecuta escaneo confocal "
            "2D sobre P0 (Drift check P0), recentra el origen (0,0) y cuadra la Capa 2 con precisión sub-nanométrica."
        )
        info_p0.setWordWrap(True)
        info_p0.setStyleSheet("color: #f9e2af; font-size: 8pt; background-color: #1e1e2e; border: 1px solid #45475a; border-radius: 4px; padding: 6px;")
        lo.addWidget(info_p0)

        lo.addStretch()
        self.tabs.addTab(tab, "⭐ Partícula Ancla (P0)")

    # ── Pestaña 4: Ruta de Platina PI ─────────────────────────────────────────
    def _setup_path_tab(self):
        tab = QWidget(); lo = QVBoxLayout(tab)

        path_gb = QGroupBox("Estrategia de Recorrido de la Platina PI")
        plo = QVBoxLayout(path_gb)

        self.path_mode_combo = QComboBox()
        self.path_mode_combo.addItems([
            "Serpiente / Zig-Zag (Filas Alternadas — Recomendado)",
            "Espiral (Del Centro hacia el Borde)",
            "TSP Euclidiano (Camino de Distancia Mínima)",
            "Sin Ordenar (Directo)"
        ])
        self.path_mode_combo.currentIndexChanged.connect(self._on_params_changed)
        plo.addWidget(self.path_mode_combo)

        info_path = QLabel(
            "🛤️ <b>Optimización de Deriva:</b> El recorrido en Serpiente minimiza retrocesos bruscos de la platina PI, "
            "reduciendo la fatiga mecánica de los actuadores y la acumulación de deriva durante la impresión."
        )
        info_path.setWordWrap(True)
        info_path.setStyleSheet("color: #a6adc8; font-size: 8pt; padding: 4px;")
        plo.addWidget(info_path)

        lo.addWidget(path_gb)
        lo.addStretch()
        self.tabs.addTab(tab, "🛤️ Ruta de Impresión")

    # ── Handlers y Actualización en Tiempo Real ───────────────────────────────
    def _on_layer_selected(self, idx: int):
        # Asegurar que existan capas suficientes
        while len(self.composer.layers) <= idx:
            new_l = LatticeLayer(
                name=f"Layer {len(self.composer.layers)+1}",
                lattice_type="hexagonal",
                a=3.0,
                color=MATERIAL_COLORS.get(len(self.composer.layers)+1, {}).get("hex", "#89b4fa")
            )
            new_l.enabled = False
            self.composer.layers.append(new_l)

        layer = self.composer.layers[idx]
        self.layer_enable_check.blockSignals(True)
        self.layer_enable_check.setChecked(layer.enabled)
        self.layer_enable_check.blockSignals(False)

        # Actualizar combos y spinners sin disparar bucle
        self.spin_a.blockSignals(True); self.spin_a.setValue(layer.a); self.spin_a.blockSignals(False)
        self.spin_b.blockSignals(True); self.spin_b.setValue(layer.b); self.spin_b.blockSignals(False)
        self.spin_gamma.blockSignals(True); self.spin_gamma.setValue(layer.gamma_deg); self.spin_gamma.blockSignals(False)
        self.slider_gamma.blockSignals(True); self.slider_gamma.setValue(int(round(layer.gamma_deg * 10))); self.slider_gamma.blockSignals(False)
        self.spin_rot.blockSignals(True); self.spin_rot.setValue(layer.rotation_deg); self.spin_rot.blockSignals(False)
        self.spin_off_x.blockSignals(True); self.spin_off_x.setValue(layer.offset_x); self.spin_off_x.blockSignals(False)
        self.spin_off_y.blockSignals(True); self.spin_off_y.setValue(layer.offset_y); self.spin_off_y.blockSignals(False)

        # Actualizar UI de base atómica
        self._update_basis_ui(layer)
        self._on_params_changed()

    def _on_spin_gamma_changed(self, val: float):
        self.slider_gamma.blockSignals(True)
        self.slider_gamma.setValue(int(round(val * 10)))
        self.slider_gamma.blockSignals(False)
        self._on_params_changed()

    def _on_slider_gamma_changed(self, val_int: int):
        val_deg = val_int / 10.0
        self.spin_gamma.blockSignals(True)
        self.spin_gamma.setValue(val_deg)
        self.spin_gamma.blockSignals(False)
        self._on_params_changed()

    def _update_basis_ui(self, layer: LatticeLayer):
        num_atoms = len(layer.atoms)
        if num_atoms == 1:
            self.basis_gb.setTitle("⚛️ Base Atómica: 1 Átomo")
        else:
            self.basis_gb.setTitle(f"⚛️ Base Atómica: {num_atoms} Átomos en Celda Unidad")

        for i, (lbl_name, spin_u, spin_v, combo_mat) in enumerate(self.atom_rows):
            if i < num_atoms:
                atom = layer.atoms[i]
                lbl_name.setText(f"A{i+1} [{atom.label}]:")
                spin_u.blockSignals(True); spin_u.setValue(atom.u); spin_u.blockSignals(False)
                spin_v.blockSignals(True); spin_v.setValue(atom.v); spin_v.blockSignals(False)
                combo_mat.blockSignals(True); combo_mat.setCurrentIndex(min(atom.material_id - 1, 2)); combo_mat.blockSignals(False)

                lbl_name.setVisible(True); spin_u.setVisible(True); spin_v.setVisible(True); combo_mat.setVisible(True)
            else:
                lbl_name.setVisible(False); spin_u.setVisible(False); spin_v.setVisible(False); combo_mat.setVisible(False)

        self.btn_remove_atom.setEnabled(num_atoms > 1)
        self.btn_add_atom.setEnabled(num_atoms < len(self.atom_rows))

    def _on_atom_coord_changed(self, atom_idx: int):
        layer_idx = self.layer_combo.currentIndex()
        if layer_idx < len(self.composer.layers):
            layer = self.composer.layers[layer_idx]
            if atom_idx < len(layer.atoms):
                _, spin_u, spin_v, _ = self.atom_rows[atom_idx]
                layer.atoms[atom_idx].u = float(spin_u.value())
                layer.atoms[atom_idx].v = float(spin_v.value())
        self._on_params_changed()

    def _on_atom_material_changed(self, atom_idx: int, mat_combo_idx: int):
        layer_idx = self.layer_combo.currentIndex()
        if layer_idx < len(self.composer.layers):
            layer = self.composer.layers[layer_idx]
            if atom_idx < len(layer.atoms):
                mat_id = mat_combo_idx + 1
                layer.atoms[atom_idx].material_id = mat_id
                if atom_idx == 0:
                    layer.color = MATERIAL_COLORS.get(mat_id, {}).get("hex", "#89b4fa")
        self._on_params_changed()

    def _add_atom(self):
        layer_idx = self.layer_combo.currentIndex()
        if layer_idx < len(self.composer.layers):
            layer = self.composer.layers[layer_idx]
            if len(layer.atoms) < len(self.atom_rows):
                new_idx = len(layer.atoms) + 1
                layer.atoms.append(BasisAtom(u=0.5, v=0.5, material_id=min(new_idx, 3), label=f"A{new_idx}"))
                self._update_basis_ui(layer)
                self._on_params_changed()

    def _remove_atom(self):
        layer_idx = self.layer_combo.currentIndex()
        if layer_idx < len(self.composer.layers):
            layer = self.composer.layers[layer_idx]
            if len(layer.atoms) > 1:
                layer.atoms.pop()
                self._update_basis_ui(layer)
                self._on_params_changed()

    def _reset_basis_canonical(self):
        layer_idx = self.layer_combo.currentIndex()
        if layer_idx < len(self.composer.layers):
            layer = self.composer.layers[layer_idx]
            layer.atoms = LatticeLayer._default_basis_for_type(layer.lattice_type)
            self._update_basis_ui(layer)
            self._on_params_changed()

    def _on_layer_enable_changed(self, state: int):
        idx = self.layer_combo.currentIndex()
        if idx < len(self.composer.layers):
            self.composer.layers[idx].enabled = (state == 2 or state == Qt.CheckState.Checked)
        self._on_params_changed()

    def _on_lattice_type_changed(self, idx: int):
        ltype_map = [
            "hexagonal", "square", "graphene", "boron_nitride", "kagome", "lieb",
            "dice_t3", "mos2", "centered_square", "centered_rectangular",
            "decorated_triangular", "rectangular", "rhombic", "oblique", "custom"
        ]
        selected_ltype = ltype_map[idx]
        layer_idx = self.layer_combo.currentIndex()
        if layer_idx < len(self.composer.layers):
            layer = self.composer.layers[layer_idx]
            layer.lattice_type = selected_ltype
            layer.atoms = LatticeLayer._default_basis_for_type(selected_ltype)

            # Cargar valores canónicos iniciales recomendados
            is_hex = selected_ltype in ("hexagonal", "graphene", "boron_nitride", "kagome", "dice_t3", "mos2", "decorated_triangular")
            is_sq = selected_ltype in ("square", "lieb", "centered_square")
            is_rec = selected_ltype in ("rectangular", "centered_rectangular")

            if is_hex:
                self.spin_gamma.setValue(60.0)
                if self.spin_b.value() != self.spin_a.value():
                    self.spin_b.setValue(self.spin_a.value())
            elif is_sq or is_rec:
                self.spin_gamma.setValue(90.0)
                if is_sq:
                    self.spin_b.setValue(self.spin_a.value())

            self._update_basis_ui(layer)

        self._on_params_changed()

    def _on_geom_type_changed(self, idx: int):
        if idx == 0:  # Hexágono por apotema
            self.lbl_dim1.setText("Apotema ap (µm):")
            self.lbl_dim2.setVisible(False); self.spin_dim2.setVisible(False)
        elif idx == 1:  # Hexágono por radio
            self.lbl_dim1.setText("Radio Exterior R (µm):")
            self.lbl_dim2.setVisible(False); self.spin_dim2.setVisible(False)
        elif idx == 2:  # Círculo
            self.lbl_dim1.setText("Radio R (µm):")
            self.lbl_dim2.setVisible(False); self.spin_dim2.setVisible(False)
        elif idx == 3:  # Rectángulo
            self.lbl_dim1.setText("Ancho Lx (µm):")
            self.lbl_dim2.setText("Alto Ly (µm):")
            self.lbl_dim2.setVisible(True); self.spin_dim2.setVisible(True)
        elif idx == 4:  # Anillo
            self.lbl_dim1.setText("Radio Int R_in (µm):")
            self.lbl_dim2.setText("Radio Ext R_out (µm):")
            self.lbl_dim2.setVisible(True); self.spin_dim2.setVisible(True)
        elif idx == 5:  # Triángulo
            self.lbl_dim1.setText("Lado L (µm):")
            self.lbl_dim2.setVisible(False); self.spin_dim2.setVisible(False)
        elif idx == 6:  # Celdas Nx x Ny
            self.lbl_dim1.setText("Celdas Nx:")
            self.lbl_dim2.setText("Celdas Ny:")
            self.lbl_dim2.setVisible(True); self.spin_dim2.setVisible(True)

        self._on_params_changed()

    def _apply_preset(self, idx: int):
        if idx == 0:
            return

        self.composer.layers = []
        if idx == 1:  # Hexagonal en hexágono ap=5, a=2
            l1 = LatticeLayer(name="Hexagonal Layer", lattice_type="hexagonal", a=2.0, color="#89b4fa")
            self.composer.layers = [l1]
            self.composer.bounding_shape = "hexagon"
            self.composer.bounding_params = {"ap": 5.0}
            self.batch_name_edit.setText("Hexagonal_ap5um_a2um")

        elif idx == 2:  # Cuadrada 5x5
            l1 = LatticeLayer(name="Square Layer", lattice_type="square", a=3.0, color="#89b4fa")
            self.composer.layers = [l1]
            self.composer.bounding_shape = "cells"
            self.composer.bounding_params = {"nx": 5, "ny": 5}
            self.batch_name_edit.setText("Square_5x5_a3um")

        elif idx == 3:  # Grafeno en Disco R=5
            l1 = LatticeLayer(name="Graphene Layer", lattice_type="graphene", a=2.5, color="#89b4fa")
            self.composer.layers = [l1]
            self.composer.bounding_shape = "circle"
            self.composer.bounding_params = {"radius": 5.0}
            self.batch_name_edit.setText("Graphene_Disk_R5um")

        elif idx == 4:  # Kagome en Hexágono ap=6
            l1 = LatticeLayer(name="Kagome Layer", lattice_type="kagome", a=3.0, color="#a6e3a1")
            self.composer.layers = [l1]
            self.composer.bounding_shape = "hexagon"
            self.composer.bounding_params = {"ap": 6.0}
            self.batch_name_edit.setText("Kagome_Hex_ap6um")

        elif idx == 5:  # Superred Moiré Rotada (θ=2.5°)
            l1 = LatticeLayer(name="Layer 1 (0°)", lattice_type="hexagonal", a=3.0, rotation_deg=0.0, color="#89b4fa")
            l1.atoms = [BasisAtom(u=0.0, v=0.0, material_id=1, label="Layer 1")]
            l2 = LatticeLayer(name="Layer 2 (2.5°)", lattice_type="hexagonal", a=3.0, rotation_deg=2.5, color="#a6e3a1")
            l2.atoms = [BasisAtom(u=0.0, v=0.0, material_id=2, label="Layer 2")]
            self.composer.layers = [l1, l2]
            self.composer.bounding_shape = "hexagon"
            self.composer.bounding_params = {"ap": 7.0}
            self.batch_name_edit.setText("Moire_Superlattice_2.5deg")

        elif idx == 6:  # Cuadrada Centrada
            l1 = LatticeLayer(name="Centered Square", lattice_type="centered_square", a=3.0, color="#89b4fa")
            self.composer.layers = [l1]
            self.composer.bounding_shape = "rectangle"
            self.composer.bounding_params = {"lx": 12.0, "ly": 12.0}
            self.batch_name_edit.setText("Centered_Square_12um")

        elif idx == 7:  # Anillo Hexagonal
            l1 = LatticeLayer(name="Hexagonal Ring", lattice_type="hexagonal", a=2.0, color="#89b4fa")
            self.composer.layers = [l1]
            self.composer.bounding_shape = "annulus"
            self.composer.bounding_params = {"r_in": 2.0, "r_out": 6.0}
            self.batch_name_edit.setText("Hexagonal_Ring_R2_R6um")

        elif idx == 8:  # Triángulo Kagome
            l1 = LatticeLayer(name="Kagome Triangle", lattice_type="kagome", a=2.5, color="#f38ba8")
            self.composer.layers = [l1]
            self.composer.bounding_shape = "triangle"
            self.composer.bounding_params = {"side": 12.0}
            self.batch_name_edit.setText("Kagome_Triangle_L12um")

        # Sincronizar UI
        self._on_layer_selected(0)

    def _on_params_changed(self):
        # 1. Actualizar capa activa en el compositor
        cur_idx = self.layer_combo.currentIndex()
        if cur_idx < len(self.composer.layers):
            cur_l = self.composer.layers[cur_idx]
            cur_l.a = float(self.spin_a.value())
            cur_l.b = float(self.spin_b.value())
            cur_l.gamma_deg = float(self.spin_gamma.value())
            cur_l.rotation_deg = float(self.spin_rot.value())
            cur_l.offset_x = float(self.spin_off_x.value())
            cur_l.offset_y = float(self.spin_off_y.value())

        # 2. Actualizar geometría contenedora
        g_idx = self.geom_combo.currentIndex()
        geom_map = ["hexagon", "hexagon", "circle", "rectangle", "annulus", "triangle", "cells"]
        self.composer.bounding_shape = geom_map[g_idx]

        p = {}
        if g_idx == 0:  # Hexágono apotema
            p["ap"] = float(self.spin_dim1.value())
        elif g_idx == 1:  # Hexágono radio
            p["radius"] = float(self.spin_dim1.value())
        elif g_idx == 2:  # Círculo
            p["radius"] = float(self.spin_dim1.value())
        elif g_idx == 3:  # Rectángulo
            p["lx"] = float(self.spin_dim1.value())
            p["ly"] = float(self.spin_dim2.value())
        elif g_idx == 4:  # Anillo
            p["r_in"] = float(self.spin_dim1.value())
            p["r_out"] = float(self.spin_dim2.value())
        elif g_idx == 5:  # Triángulo
            p["side"] = float(self.spin_dim1.value())
        elif g_idx == 6:  # Celdas Nx x Ny
            p["nx"] = int(self.spin_dim1.value())
            p["ny"] = int(self.spin_dim2.value())
        self.composer.bounding_params = p

        # 3. Actualizar configuración de Partícula Ancla (P0)
        self.composer.anchor_config.enabled = self.p0_enable_check.isChecked()
        p0_mode_map = ["offset", "center", "first_node", "custom"]
        self.composer.anchor_config.mode = p0_mode_map[self.p0_mode_combo.currentIndex()]
        self.composer.anchor_config.offset_x_um = float(self.spin_p0_off_x.value())
        self.composer.anchor_config.offset_y_um = float(self.spin_p0_off_y.value())

        # 4. Actualizar optimizador de ruta y restricción de distancia mínima
        path_map = ["snake", "spiral", "tsp", "none"]
        self.composer.path_mode = path_map[self.path_mode_combo.currentIndex()]
        self.composer.min_distance_um = float(self.spin_min_dist.value())

        # 5. Generar y Renderizar
        self._current_result = self.composer.generate()
        self._render_plot()
        self._render_unit_cell()

    def _render_unit_cell(self):
        self.unit_cell_plot.clear()
        cur_idx = self.layer_combo.currentIndex()
        if cur_idx >= len(self.composer.layers):
            return
        layer = self.composer.layers[cur_idx]
        a1, a2 = layer.get_basis_vectors()

        # 1. Contorno de paralelogramo de la celda: (0,0) -> a1 -> a1+a2 -> a2 -> (0,0)
        poly_x = [0.0, a1[0], a1[0] + a2[0], a2[0], 0.0]
        poly_y = [0.0, a1[1], a1[1] + a2[1], a2[1], 0.0]
        poly_curve = pg.PlotCurveItem(
            poly_x, poly_y,
            pen=pg.mkPen(color='#f9e2af', width=1.5, style=Qt.PenStyle.DashLine)
        )
        self.unit_cell_plot.addItem(poly_curve)

        # 2. Vectores primitivos a1 y a2
        curve_a1 = pg.PlotCurveItem([0.0, a1[0]], [0.0, a1[1]], pen=pg.mkPen(color='#89b4fa', width=2.5))
        curve_a2 = pg.PlotCurveItem([0.0, a2[0]], [0.0, a2[1]], pen=pg.mkPen(color='#a6e3a1', width=2.5))
        self.unit_cell_plot.addItem(curve_a1)
        self.unit_cell_plot.addItem(curve_a2)

        # Textos a1 y a2
        t_a1 = pg.TextItem("a₁", color='#89b4fa', anchor=(0.5, 1.3))
        t_a1.setFont(QFont("Arial", 8, QFont.Weight.Bold))
        t_a1.setPos(a1[0]/2.0, a1[1]/2.0)
        self.unit_cell_plot.addItem(t_a1)

        t_a2 = pg.TextItem("a₂", color='#a6e3a1', anchor=(1.3, 0.5))
        t_a2.setFont(QFont("Arial", 8, QFont.Weight.Bold))
        t_a2.setPos(a2[0]/2.0, a2[1]/2.0)
        self.unit_cell_plot.addItem(t_a2)

        # 3. Átomos de la base
        for j, atom in enumerate(layer.atoms):
            r_atom = atom.u * a1 + atom.v * a2
            mat_info = MATERIAL_COLORS.get(atom.material_id, MATERIAL_COLORS[1])
            scatter = pg.ScatterPlotItem(
                x=[r_atom[0]], y=[r_atom[1]],
                size=14, symbol=mat_info["symbol"],
                brush=pg.mkBrush(mat_info["brush"]),
                pen=pg.mkPen(color='#11111b', width=1.5)
            )
            self.unit_cell_plot.addItem(scatter)

            t_at = pg.TextItem(f"A{j+1}", color='#ffffff', anchor=(0.5, 1.4))
            t_at.setFont(QFont("Arial", 7, QFont.Weight.Bold))
            t_at.setPos(r_atom[0], r_atom[1])
            self.unit_cell_plot.addItem(t_at)

        # 4. Actualizar descripción en etiqueta
        atom_desc = " | ".join([f"A{j+1}: Mat {atom.material_id} ({atom.u:.2f}, {atom.v:.2f})" for j, atom in enumerate(layer.atoms)])
        self.lbl_unit_cell_info.setText(
            f"<b>a</b>={layer.a:.2f} µm, <b>b</b>={layer.b:.2f} µm, <b>γ</b>={layer.gamma_deg:.1f}° ({len(layer.atoms)} átomos)<br>"
            f"<span style='color: #89b4fa;'>{atom_desc}</span>"
        )

    def _render_plot(self):
        self.plot_widget.clear()
        if not self._current_result:
            return

        nodes = self._current_result.get("nodes", [])
        passes_nodes = self._current_result.get("passes_nodes", {})
        anchor = self._current_result.get("anchor")
        stats = self._current_result.get("stats", {})

        view_mode = self.path_view_combo.currentIndex()
        # 0: Global, 1: Separated multi-pass, 2: Pass 1, 3: Pass 2, 4: Pass 3
        show_path = self.chk_show_path.isChecked()
        show_nums = self.chk_show_numbers.isChecked()

        # 1. Dibujar contorno de la geometría contenedora
        self._draw_bounding_outline()

        # 2. Dibujar trayectorias de platina PI según el modo visual seleccionado
        if show_path:
            if view_mode == 0:  # Global unificado
                pts = ([anchor] if anchor else []) + nodes
                if len(pts) > 1:
                    px = [p["x"] for p in pts]
                    py = [p["y"] for p in pts]
                    path_curve = pg.PlotCurveItem(
                        px, py, pen=pg.mkPen(color='#585b70', width=1.5, style=Qt.PenStyle.DashLine)
                    )
                    self.plot_widget.addItem(path_curve)

            elif view_mode == 1:  # Rutas Multi-Paso Separadas (1 trazo por material)
                for mat_id, m_nodes in passes_nodes.items():
                    m_color = MATERIAL_COLORS.get(mat_id, {}).get("hex", "#cdd6f4")
                    pts = ([anchor] if anchor else []) + m_nodes
                    if len(pts) > 1:
                        px = [p["x"] for p in pts]
                        py = [p["y"] for p in pts]
                        path_curve = pg.PlotCurveItem(
                            px, py, pen=pg.mkPen(color=m_color, width=1.8, style=Qt.PenStyle.DashLine)
                        )
                        self.plot_widget.addItem(path_curve)

            else:  # Solo Paso 1 (mat_id=1), Paso 2 (mat_id=2), o Paso 3 (mat_id=3)
                target_mat = view_mode - 1  # 2->1, 3->2, 4->3
                m_nodes = passes_nodes.get(target_mat, [])
                m_color = MATERIAL_COLORS.get(target_mat, {}).get("hex", "#89b4fa")
                pts = ([anchor] if anchor else []) + m_nodes
                if len(pts) > 1:
                    px = [p["x"] for p in pts]
                    py = [p["y"] for p in pts]
                    path_curve = pg.PlotCurveItem(
                        px, py, pen=pg.mkPen(color=m_color, width=2.0, style=Qt.PenStyle.SolidLine)
                    )
                    self.plot_widget.addItem(path_curve)

        # 3. Dibujar nodos por material (con resalte / atenuación según vista)
        for mat_id, mat_info in MATERIAL_COLORS.items():
            mat_nodes = passes_nodes.get(mat_id, [n for n in nodes if n["material_id"] == mat_id])
            if not mat_nodes:
                continue

            is_active_mat = (view_mode in (0, 1)) or (view_mode - 1 == mat_id)
            if is_active_mat:
                scatter = pg.ScatterPlotItem(
                    x=[n["x"] for n in mat_nodes],
                    y=[n["y"] for n in mat_nodes],
                    size=11,
                    symbol=mat_info["symbol"],
                    brush=pg.mkBrush(mat_info["brush"]),
                    pen=pg.mkPen(color='#11111b', width=1),
                    name=mat_info["name"]
                )
                self.plot_widget.addItem(scatter)

                # Mostrar números de secuencia sobre cada nodo
                if show_nums:
                    for s_idx, n in enumerate(mat_nodes):
                        txt_num = pg.TextItem(str(s_idx + 1), color='#ffffff', anchor=(0.5, 1.4))
                        txt_num.setFont(QFont("Arial", 7, QFont.Weight.Bold))
                        txt_num.setPos(n["x"], n["y"])
                        self.plot_widget.addItem(txt_num)
            else:
                # Nodo atenuado / dim
                dim_scatter = pg.ScatterPlotItem(
                    x=[n["x"] for n in mat_nodes],
                    y=[n["y"] for n in mat_nodes],
                    size=7,
                    symbol=mat_info["symbol"],
                    brush=pg.mkBrush('#313244'),
                    pen=pg.mkPen(color='#45475a', width=1),
                    name=f"{mat_info['name']} (Inactivo)"
                )
                self.plot_widget.addItem(dim_scatter)

        # 4. Dibujar Partícula Ancla P0 (Estrella dorada ⭐)
        if anchor:
            anchor_scatter = pg.ScatterPlotItem(
                x=[anchor["x"]],
                y=[anchor["y"]],
                size=18,
                symbol='star',
                brush=pg.mkBrush('#f9e2af'),
                pen=pg.mkPen(color='#fab387', width=1.5),
                name="Anchor P0 ⭐"
            )
            self.plot_widget.addItem(anchor_scatter)

            txt = pg.TextItem("P0 (Ancla)", color='#f9e2af', anchor=(0.5, 1.5))
            txt.setFont(QFont("Arial", 8, QFont.Weight.Bold))
            txt.setPos(anchor["x"], anchor["y"])
            self.plot_widget.addItem(txt)

        # 5. Actualizar Barra de Telemetría
        total = stats.get("total", 0)
        has_anc = stats.get("has_anchor", False)
        anc_txt = " (incluye Ancla P0 ⭐)" if has_anc else ""
        suppressed = stats.get("suppressed_by_min_dist", 0)
        supp_txt = f" | ⚠️ Excluidos por d_min: {suppressed}" if suppressed > 0 else ""
        self.lbl_stats_total.setText(f"N Total: {total}{anc_txt}{supp_txt}")
        self.lbl_stats_mat.setText(f"Mat 1: {stats.get('mat1', 0)} | Mat 2: {stats.get('mat2', 0)} | Mat 3: {stats.get('mat3', 0)}")
        self.lbl_stats_dims.setText(f"Dim: {stats.get('width_um', 0.0):.2f} × {stats.get('height_um', 0.0):.2f} µm")

        if view_mode in (2, 3, 4):
            t_mat = view_mode - 1
            p_stat = stats.get("pass_stats", {}).get(t_mat, {})
            p_len = p_stat.get("path_length_mm", 0.0)
            p_cnt = p_stat.get("count", 0)
            self.lbl_stats_path.setText(f"Trayectoria Paso {t_mat}: {p_len:.3f} mm ({p_cnt} nodos)")
        else:
            self.lbl_stats_path.setText(f"Trayectoria Global: {stats.get('path_length_mm', 0.0):.3f} mm")

    def _draw_bounding_outline(self):
        shape = self.composer.bounding_shape
        p = self.composer.bounding_params
        pen = pg.mkPen(color='#f9e2af', width=1.5, style=Qt.PenStyle.DotLine)

        if shape == "circle":
            r = float(p.get("radius", 5.0))
            theta = np.linspace(0, 2*np.pi, 100)
            self.plot_widget.plot(r * np.cos(theta), r * np.sin(theta), pen=pen)

        elif shape == "annulus":
            r_in = float(p.get("r_in", 2.0))
            r_out = float(p.get("r_out", 6.0))
            theta = np.linspace(0, 2*np.pi, 100)
            self.plot_widget.plot(r_in * np.cos(theta), r_in * np.sin(theta), pen=pen)
            self.plot_widget.plot(r_out * np.cos(theta), r_out * np.sin(theta), pen=pen)

        elif shape in ("rectangle", "square"):
            lx = float(p.get("lx", p.get("size", 10.0))) / 2.0
            ly = float(p.get("ly", p.get("size", 10.0))) / 2.0
            bx = [-lx, lx, lx, -lx, -lx]
            by = [-ly, -ly, ly, ly, -ly]
            self.plot_widget.plot(bx, by, pen=pen)

        elif shape == "hexagon":
            ap = float(p.get("ap", 5.0)) if "ap" in p else float(p.get("radius", 5.0)) * math.cos(math.radians(30))
            r_vert = ap / math.cos(math.radians(30.0))
            angles = [math.radians(30 + 60*i) for i in range(7)]
            hx = [r_vert * math.cos(a) for a in angles]
            hy = [r_vert * math.sin(a) for a in angles]
            self.plot_widget.plot(hx, hy, pen=pen)

        elif shape == "triangle":
            side = float(p.get("side", 10.0))
            h = side * math.sqrt(3.0) / 2.0
            r_in = h / 3.0
            r_out = 2.0 * h / 3.0
            tx = [0.0, side/2.0, -side/2.0, 0.0]
            ty = [r_out, -r_in, -r_in, r_out]
            self.plot_widget.plot(tx, ty, pen=pen)

    # ── Exportadores ──────────────────────────────────────────────────────────
    def _export_single(self):
        if not self._current_result or not self._current_result.get("nodes"):
            QMessageBox.warning(self, "Aviso", "No hay nodos generados para exportar.")
            return

        default_name = f"{self.batch_name_edit.text().strip() or 'Lattice_Grid'}.txt"
        file_path, _ = QFileDialog.getSaveFileName(self, "Exportar Grilla para PyPrinting", default_name, "Archivos de Grilla (*.txt)")
        if file_path:
            CrystalGridExporter.export_single_txt(file_path, self._current_result, include_anchor=True)
            QMessageBox.information(
                self, "Exportación Exitosa",
                f"✅ <b>Grilla exportada exitosamente:</b><br><code>{file_path}</code><br><br>"
                f"Contiene <b>{self._current_result['stats']['total']}</b> partículas "
                f"(incluyendo Partícula Ancla P0 si fue habilitada)."
            )

    def _export_multipass(self):
        if not self._current_result or not self._current_result.get("nodes"):
            QMessageBox.warning(self, "Aviso", "No hay nodos generados para exportar.")
            return

        folder = QFileDialog.getExistingDirectory(self, "Seleccionar Carpeta para Paquete Multi-Paso")
        if folder:
            prefix = self.batch_name_edit.text().strip() or "Lattice_Recipe"
            files = CrystalGridExporter.export_multipass_package(folder, prefix, self._current_result)
            files_txt = "<br>".join([f"• <code>{os.path.basename(p)}</code>" for p in files.values()])
            QMessageBox.information(
                self, "Paquete Multi-Paso Generado",
                f"📦 <b>Paquete de recetas para nanofabricación secuencial generado en:</b><br><code>{folder}</code><br><br>"
                f"<b>Archivos creados:</b><br>{files_txt}<br><br>"
                f"<i>Cada capa incluye la Partícula Ancla P0 en el nodo 0 para permitir cuadratura sub-nanométrica.</i>"
            )

    def _export_png(self):
        default_name = f"{self.batch_name_edit.text().strip() or 'Lattice_Plot'}.png"
        file_path, _ = QFileDialog.getSaveFileName(self, "Exportar Gráfico 2D", default_name, "Imágenes PNG (*.png)")
        if file_path:
            import pyqtgraph.exporters
            exporter = pg.exporters.ImageExporter(self.plot_widget.plotItem)
            exporter.parameters()['width'] = 1920
            exporter.export(file_path)
            QMessageBox.information(self, "Gráfico Exportado", f"🖼️ Imagen PNG guardada en:\n{file_path}")


# ══════════════════════════════════════════════════════════════════════════════
#  PUNTO DE ENTRADA PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

def main():
    app = QApplication(sys.argv)
    window = GridGeneratorWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
