"""
analysis/figure_export_studio.py
================================
Estudio de Exportación Científica Universal (PyPrinting 3.0).

Permite inspeccionar, editar capas, estilizar y exportar cualquier gráfico
en calidades de publicación editorial:
- SVG Vectorial Nativo con texto editable (<text>) para Inkscape / Illustrator.
- Rasterizado de Ultra Alta Definición (PNG / JPEG / TIFF a 300, 600, 1200 DPI).
- Vectorial PDF para manuscritos LaTeX.
- Exportación de curvas numéricas a tablas tabuladas (.txt, .dat, .csv).
"""

import os
from typing import Optional, List, Dict, Any
import numpy as np
import matplotlib
matplotlib.use('Agg')
matplotlib.rcParams['svg.fonttype'] = 'none'
matplotlib.rcParams['pdf.fonttype'] = 42
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
import pyqtgraph as pg

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QSplitter,
    QGroupBox, QLabel, QPushButton, QComboBox, QCheckBox,
    QSpinBox, QDoubleSpinBox, QLineEdit, QTableWidget,
    QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox,
    QColorDialog, QFrame, QScrollArea, QWidget
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QIcon


class FigureExportStudioDialog(QDialog):
    """
    Diálogo modal avanzado para la personalización y exportación de gráficos
    científicos para publicaciones y tesis.
    """

    def __init__(
        self,
        source_plot: Optional[pg.PlotWidget] = None,
        parent=None,
        title: str = "",
        default_title: str = "",
        default_filename: str = "figura_cientifica",
        *args,
        **kwargs
    ):
        # Compatibilidad flexible de argumentos posicionales o por nombre
        if isinstance(source_plot, QWidget) and not isinstance(source_plot, pg.PlotWidget):
            real_parent = source_plot
            real_source = kwargs.get('source_plot', parent)
        else:
            real_source = source_plot
            real_parent = parent

        super().__init__(real_parent)
        self.source_plot = real_source
        self.default_title = title or default_title or default_filename or "figura_cientifica"
        self.default_filename = default_filename or self.default_title
        self.setWindowTitle(f"🎨 Estudio de Exportación Científica — {self.default_title}")
        self.resize(1100, 720)
        self.setMinimumSize(900, 600)

        # Extraer capas y metadatos del gráfico original
        self.layers = self._extract_layers(source_plot)
        self.plot_metadata = self._extract_metadata(source_plot)

        # Matplotlib Figure y Canvas para la vista previa en vivo
        self.fig = Figure(figsize=(7, 5), dpi=100)
        self.canvas = FigureCanvasQTAgg(self.fig)

        self._init_ui()
        self._populate_layers()
        self.update_preview()

    def _extract_metadata(self, plot_widget: Optional[pg.PlotWidget]) -> dict:
        meta = {
            'title': self.default_title.replace('_', ' ').title(),
            'xlabel': 'Eje X',
            'xunits': '',
            'ylabel': 'Eje Y',
            'yunits': '',
            'xmin': 0.0,
            'xmax': 10.0,
            'ymin': 0.0,
            'ymax': 10.0,
            'has_range': False,
        }
        if plot_widget is not None:
            try:
                pi = plot_widget.plotItem
                if pi.titleLabel and pi.titleLabel.text:
                    meta['title'] = str(pi.titleLabel.text)
                b_axis = pi.getAxis('bottom')
                if b_axis.labelText:
                    meta['xlabel'] = str(b_axis.labelText)
                if b_axis.unitText:
                    meta['xunits'] = str(b_axis.unitText)
                l_axis = pi.getAxis('left')
                if l_axis.labelText:
                    meta['ylabel'] = str(l_axis.labelText)
                if l_axis.unitText:
                    meta['yunits'] = str(l_axis.unitText)

                vb = pi.getViewBox()
                if vb:
                    vr = vb.viewRange()
                    meta['xmin'] = float(vr[0][0])
                    meta['xmax'] = float(vr[0][1])
                    meta['ymin'] = float(vr[1][0])
                    meta['ymax'] = float(vr[1][1])
                    meta['has_range'] = True
            except Exception:
                pass
        return meta

    def _compute_data_bounds(self) -> tuple[float, float, float, float]:
        """Calcula los límites envolventes reales (xmin, xmax, ymin, ymax) de las capas cargadas."""
        xs, ys = [], []
        for l in self.layers:
            if 'x' in l and 'y' in l:
                x_arr = np.asarray(l['x'], dtype=float)
                y_arr = np.asarray(l['y'], dtype=float)
                x_valid = x_arr[np.isfinite(x_arr)]
                y_valid = y_arr[np.isfinite(y_arr)]
                if len(x_valid) > 0:
                    xs.extend([float(np.min(x_valid)), float(np.max(x_valid))])
                if len(y_valid) > 0:
                    ys.extend([float(np.min(y_valid)), float(np.max(y_valid))])
            elif l.get('type') == 'image' and 'extent' in l:
                ext = l['extent']
                xs.extend([float(ext[0]), float(ext[1])])
                ys.extend([float(ext[2]), float(ext[3])])

        if xs and ys:
            return float(np.min(xs)), float(np.max(xs)), float(np.min(ys)), float(np.max(ys))
        return (
            float(self.plot_metadata.get('xmin', 0.0)),
            float(self.plot_metadata.get('xmax', 10.0)),
            float(self.plot_metadata.get('ymin', 0.0)),
            float(self.plot_metadata.get('ymax', 10.0))
        )

    def _extract_layers(self, plot_widget: Optional[pg.PlotWidget]) -> list:
        layers = []
        if plot_widget is None:
            return layers

        try:
            items = plot_widget.plotItem.items
        except Exception:
            return layers

        idx = 1
        for it in items:
            # 1. PlotDataItem (curvas y dispersión continua)
            if isinstance(it, pg.PlotDataItem):
                x, y = it.getData()
                if x is None or y is None or len(x) == 0:
                    continue
                name = getattr(it, 'opts', {}).get('name') or f"Curva {idx}"
                pen = it.opts.get('pen')
                color_hex = '#89b4fa'
                line_w = 1.5
                line_style = 'solid'

                if isinstance(pen, pg.QtGui.QPen):
                    color_hex = pen.color().name()
                    line_w = max(0.5, float(pen.widthF() or pen.width()))
                    st = pen.style()
                    if st == Qt.PenStyle.DashLine:
                        line_style = 'dashed'
                    elif st == Qt.PenStyle.DotLine:
                        line_style = 'dotted'
                    elif st == Qt.PenStyle.DashDotLine:
                        line_style = 'dashdot'
                elif isinstance(pen, str):
                    color_hex = pen

                symbol = it.opts.get('symbol')
                layers.append({
                    'id': idx,
                    'type': 'curve',
                    'name': str(name),
                    'x': np.asarray(x, dtype=float),
                    'y': np.asarray(y, dtype=float),
                    'color': color_hex,
                    'linewidth': line_w,
                    'linestyle': line_style,
                    'symbol': symbol,
                    'visible': it.isVisible()
                })
                idx += 1

            # 2. ScatterPlotItem (puntos discretos)
            elif isinstance(it, pg.ScatterPlotItem):
                try:
                    data = it.getData()
                    if data and len(data) >= 2 and data[0] is not None:
                        x, y = data[0], data[1]
                    else:
                        pts = it.points()
                        x = np.array([p.pos().x() for p in pts])
                        y = np.array([p.pos().y() for p in pts])
                except Exception:
                    continue

                if len(x) == 0:
                    continue

                name = getattr(it, 'name', lambda: None)() or f"Dispersión {idx}"
                color_hex = '#f9e2af'
                try:
                    brush = it.data['brush'][0] if hasattr(it, 'data') and len(it.data) > 0 else None
                    if isinstance(brush, pg.QtGui.QBrush):
                        color_hex = brush.color().name()
                except Exception:
                    pass

                layers.append({
                    'id': idx,
                    'type': 'scatter',
                    'name': str(name),
                    'x': np.asarray(x, dtype=float),
                    'y': np.asarray(y, dtype=float),
                    'color': color_hex,
                    'size': 6.0,
                    'symbol': 'o',
                    'visible': it.isVisible()
                })
                idx += 1

            # 3. InfiniteLine (guías de referencia)
            elif isinstance(it, pg.InfiniteLine):
                pos = float(it.value())
                angle = float(it.angle)
                pen = it.pen
                color_hex = '#f38ba8'
                if isinstance(pen, pg.QtGui.QPen):
                    color_hex = pen.color().name()
                layers.append({
                    'id': idx,
                    'type': 'infoline',
                    'name': f"Línea Guía ({'Vert' if angle == 90 else 'Horiz'} @ {pos:.1f})",
                    'pos': pos,
                    'angle': angle,
                    'color': color_hex,
                    'linestyle': 'dashed',
                    'linewidth': 1.2,
                    'visible': it.isVisible()
                })
                idx += 1

            # 4. ImageItem (mapa 2D de intensidades)
            elif isinstance(it, pg.ImageItem):
                img = it.image
                if img is not None and getattr(img, 'size', 0) > 0:
                    try:
                        br = it.mapRectToParent(it.boundingRect())
                        left, right = float(br.left()), float(br.right())
                        top, bottom = float(br.top()), float(br.bottom())
                        x_min, x_max = min(left, right), max(left, right)
                        y_min, y_max = min(top, bottom), max(top, bottom)
                        extent = (x_min, x_max, y_min, y_max)
                    except Exception:
                        extent = (0.0, float(img.shape[0]), 0.0, float(img.shape[1]))

                    layers.append({
                        'id': idx,
                        'type': 'image',
                        'name': f"Mapa 2D ({img.shape[0]}x{img.shape[1]})",
                        'image': img.copy(),
                        'extent': extent,
                        'visible': it.isVisible()
                    })
                    idx += 1

            # 5. BarGraphItem (gráficos de barras)
            elif isinstance(it, pg.BarGraphItem):
                try:
                    opts = getattr(it, 'opts', {})
                    x = opts.get('x')
                    height = opts.get('height')
                    width = opts.get('width', 0.55)
                    brushes = opts.get('brushes') or opts.get('brush')

                    bar_colors = []
                    if isinstance(brushes, (list, np.ndarray)):
                        for b in brushes:
                            if isinstance(b, pg.QtGui.QBrush):
                                bar_colors.append(b.color().name())
                            elif isinstance(b, str):
                                bar_colors.append(b)
                            else:
                                bar_colors.append('#89b4fa')
                    elif isinstance(brushes, pg.QtGui.QBrush):
                        bar_colors = [brushes.color().name()]
                    elif isinstance(brushes, str):
                        bar_colors = [brushes]
                    else:
                        bar_colors = ['#89b4fa']

                    ticks = None
                    try:
                        b_axis = plot_widget.plotItem.getAxis('bottom')
                        if hasattr(b_axis, 'ticks') and b_axis.ticks:
                            ticks = b_axis.ticks
                    except Exception:
                        pass

                    x_arr = np.asarray(x, dtype=float) if x is not None else np.array([])
                    h_arr = np.asarray(height, dtype=float) if height is not None else np.array([])
                    if len(x_arr) > 0 and len(h_arr) > 0:
                        layers.append({
                            'id': idx,
                            'type': 'bar',
                            'name': f"Barras {idx}",
                            'x': x_arr,
                            'y': h_arr,
                            'height': h_arr,
                            'width': float(width) if isinstance(width, (int, float)) else 0.55,
                            'colors': bar_colors,
                            'color': bar_colors[0] if bar_colors else '#89b4fa',
                            'ticks': ticks,
                            'visible': it.isVisible()
                        })
                        idx += 1
                except Exception:
                    pass

            # 6. TextItem (anotaciones textuales)
            elif isinstance(it, pg.TextItem):
                try:
                    pos = it.pos()
                    raw_text = it.toPlainText() if hasattr(it, 'toPlainText') else str(getattr(it, 'text', ''))
                    if raw_text:
                        color_hex = '#cdd6f4'
                        if hasattr(it, 'color') and isinstance(it.color, pg.QtGui.QColor):
                            color_hex = it.color.name()
                        layers.append({
                            'id': idx,
                            'type': 'text',
                            'name': f"Texto: {raw_text[:12]}",
                            'x': float(pos.x()),
                            'y': float(pos.y()),
                            'text': raw_text,
                            'color': color_hex,
                            'visible': it.isVisible()
                        })
                        idx += 1
                except Exception:
                    pass

        return layers

    def _init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)

        # ── Panel Izquierdo: Controles de Personalización ─────────────────────
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QFrame.Shape.NoFrame)
        left_scroll.setFixedWidth(460)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(4, 4, 8, 4)
        left_layout.setSpacing(10)
        left_scroll.setWidget(left_widget)

        # Grupo 1: Gestor de Capas y Curvas
        grp_layers = QGroupBox("1. Gestor de Capas y Curvas")
        lay_layers = QVBoxLayout(grp_layers)

        self.table_layers = QTableWidget(0, 5)
        self.table_layers.setHorizontalHeaderLabels(["Ver", "Nombre", "Tipo", "Color", "Grosor"])
        self.table_layers.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table_layers.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table_layers.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table_layers.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table_layers.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table_layers.setFixedHeight(180)
        self.table_layers.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        lay_layers.addWidget(self.table_layers)

        h_lay_btns = QHBoxLayout()
        btn_toggle_all = QPushButton("Alternar Todas")
        btn_toggle_all.clicked.connect(self._toggle_all_layers)
        h_lay_btns.addWidget(btn_toggle_all)
        lay_layers.addLayout(h_lay_btns)

        left_layout.addWidget(grp_layers)

        # Grupo 2: Lienzo, Ejes y Tipografía Editorial
        grp_canvas = QGroupBox("2. Lienzo, Estilo Editorial y Tipografía")
        lay_canvas = QVBoxLayout(grp_canvas)

        grid_c = QGridLayout()
        grid_c.addWidget(QLabel("Tema Lienzo:"), 0, 0)
        self.combo_bg = QComboBox()
        self.combo_bg.addItems(["Blanco Publicación (Paper Editorial)", "Oscuro Catppuccin Mocha", "Transparente"])
        self.combo_bg.currentIndexChanged.connect(self.update_preview)
        grid_c.addWidget(self.combo_bg, 0, 1)

        grid_c.addWidget(QLabel("Fuente Texto:"), 1, 0)
        self.combo_font = QComboBox()
        self.combo_font.addItems(["DejaVu Sans", "Arial", "Helvetica", "Times New Roman", "Segoe UI"])
        self.combo_font.currentIndexChanged.connect(self.update_preview)
        grid_c.addWidget(self.combo_font, 1, 1)

        grid_c.addWidget(QLabel("Motor LaTeX:"), 2, 0)
        self.combo_math_font = QComboBox()
        self.combo_math_font.addItems([
            "Computer Modern (TeX Clásico / CMR)",
            "STIX (Times / Serif Editorial)",
            "DejaVu Sans (Moderno)"
        ])
        self.combo_math_font.currentIndexChanged.connect(self.update_preview)
        grid_c.addWidget(self.combo_math_font, 2, 1)

        grid_c.addWidget(QLabel("Título:"), 3, 0)
        self.edit_title = QLineEdit(self.plot_metadata['title'])
        self.edit_title.setToolTip(r"Soporta expresiones matemáticas en LaTeX entre signos $, ej: $g(r)$, $\lambda_{\mathrm{max}}$")
        self.edit_title.textChanged.connect(self.update_preview)
        grid_c.addWidget(self.edit_title, 3, 1)

        grid_c.addWidget(QLabel("Etiqueta X:"), 4, 0)
        self.edit_xlabel = QLineEdit(f"{self.plot_metadata['xlabel']} [{self.plot_metadata['xunits']}]" if self.plot_metadata['xunits'] else self.plot_metadata['xlabel'])
        self.edit_xlabel.setToolTip(r"Soporta LaTeX, ej: $r$ [nm], $2\theta$ [°], $q$ [nm$^{-1}$]")
        self.edit_xlabel.textChanged.connect(self.update_preview)
        grid_c.addWidget(self.edit_xlabel, 4, 1)

        grid_c.addWidget(QLabel("Etiqueta Y:"), 5, 0)
        self.edit_ylabel = QLineEdit(f"{self.plot_metadata['ylabel']} [{self.plot_metadata['yunits']}]" if self.plot_metadata['yunits'] else self.plot_metadata['ylabel'])
        self.edit_ylabel.setToolTip(r"Soporta LaTeX, ej: $I / I_0$ [a.u.], $\sigma_{\mathrm{DW}}$ [nm]")
        self.edit_ylabel.textChanged.connect(self.update_preview)
        grid_c.addWidget(self.edit_ylabel, 5, 1)

        lay_canvas.addLayout(grid_c)

        h_opts = QHBoxLayout()
        self.chk_latex = QCheckBox("Interpretar LaTeX ($...$)")
        self.chk_latex.setChecked(True)
        self.chk_latex.setToolTip("Interpreta fórmulas matemáticas escritas entre signos de dólar")
        self.chk_latex.toggled.connect(self.update_preview)
        h_opts.addWidget(self.chk_latex)

        self.chk_grid = QCheckBox("Malla (Grid)")
        self.chk_grid.setChecked(True)
        self.chk_grid.toggled.connect(self.update_preview)
        h_opts.addWidget(self.chk_grid)

        self.chk_legend = QCheckBox("Leyenda")
        self.chk_legend.setChecked(True)
        self.chk_legend.toggled.connect(self.update_preview)
        h_opts.addWidget(self.chk_legend)

        self.combo_legend_loc = QComboBox()
        self.combo_legend_loc.addItems(["best", "upper right", "upper left", "lower right", "lower left", "center right"])
        self.combo_legend_loc.currentIndexChanged.connect(self.update_preview)
        h_opts.addWidget(self.combo_legend_loc)
        lay_canvas.addLayout(h_opts)

        left_layout.addWidget(grp_canvas)

        # Grupo 3: Delimitación de Ejes (xlim / ylim)
        grp_limits = QGroupBox("3. Delimitación de Ejes (xlim / ylim)")
        lay_limits = QVBoxLayout(grp_limits)

        grid_lim = QGridLayout()
        self.chk_xlim = QCheckBox("Fijar Rango X:")
        self.chk_xlim.toggled.connect(self.update_preview)
        grid_lim.addWidget(self.chk_xlim, 0, 0)

        h_lim_x = QHBoxLayout()
        self.spin_xmin = QDoubleSpinBox()
        self.spin_xmin.setRange(-1e9, 1e9)
        self.spin_xmin.setDecimals(3)
        self.spin_xmin.setValue(self.plot_metadata.get('xmin', 0.0))
        self.spin_xmin.valueChanged.connect(self.update_preview)
        h_lim_x.addWidget(self.spin_xmin)
        h_lim_x.addWidget(QLabel("a"))
        self.spin_xmax = QDoubleSpinBox()
        self.spin_xmax.setRange(-1e9, 1e9)
        self.spin_xmax.setDecimals(3)
        self.spin_xmax.setValue(self.plot_metadata.get('xmax', 10.0))
        self.spin_xmax.valueChanged.connect(self.update_preview)
        h_lim_x.addWidget(self.spin_xmax)
        grid_lim.addLayout(h_lim_x, 0, 1)

        self.chk_ylim = QCheckBox("Fijar Rango Y:")
        self.chk_ylim.toggled.connect(self.update_preview)
        grid_lim.addWidget(self.chk_ylim, 1, 0)

        h_lim_y = QHBoxLayout()
        self.spin_ymin = QDoubleSpinBox()
        self.spin_ymin.setRange(-1e9, 1e9)
        self.spin_ymin.setDecimals(3)
        self.spin_ymin.setValue(self.plot_metadata.get('ymin', 0.0))
        self.spin_ymin.valueChanged.connect(self.update_preview)
        h_lim_y.addWidget(self.spin_ymin)
        h_lim_y.addWidget(QLabel("a"))
        self.spin_ymax = QDoubleSpinBox()
        self.spin_ymax.setRange(-1e9, 1e9)
        self.spin_ymax.setDecimals(3)
        self.spin_ymax.setValue(self.plot_metadata.get('ymax', 10.0))
        self.spin_ymax.valueChanged.connect(self.update_preview)
        h_lim_y.addWidget(self.spin_ymax)
        grid_lim.addLayout(h_lim_y, 1, 1)

        lay_limits.addLayout(grid_lim)

        btn_auto_lim = QPushButton("🔄 Auto-Ajustar a Límites de Datos")
        btn_auto_lim.setToolTip("Rellena xmin, xmax, ymin, ymax con los límites reales de las curvas")
        btn_auto_lim.clicked.connect(self._auto_fit_limits_to_data)
        lay_limits.addWidget(btn_auto_lim)

        left_layout.addWidget(grp_limits)

        # Grupo 4: Exportación Científica Multiformato & Dimensiones
        grp_export = QGroupBox("4. Exportación Multiformato & Dimensiones")
        lay_exp = QVBoxLayout(grp_export)

        grid_exp = QGridLayout()
        grid_exp.addWidget(QLabel("Formato Imagen:"), 0, 0)
        self.combo_format = QComboBox()
        self.combo_format.addItems([
            "SVG Vectorial Nativo (*.svg) [Texto editable en Inkscape]",
            "PNG Alta Resolución (*.png) [300 - 1200 DPI]",
            "PDF Vectorial para LaTeX (*.pdf)",
            "TIFF Científico (*.tiff)",
            "JPEG Calidad Publicación (*.jpg)"
        ])
        grid_exp.addWidget(self.combo_format, 0, 1)

        grid_exp.addWidget(QLabel("Resolución (DPI):"), 1, 0)
        self.combo_dpi = QComboBox()
        self.combo_dpi.addItems(["600 DPI (Estándar de Revista/Tesis)", "1200 DPI (Ultra Alta Resolución)", "300 DPI (Estándar Web/Pantalla)", "150 DPI (Borrador Rápido)"])
        grid_exp.addWidget(self.combo_dpi, 1, 1)

        grid_exp.addWidget(QLabel("Unidad Tamaño:"), 2, 0)
        self.combo_size_units = QComboBox()
        self.combo_size_units.addItems(["Pulgadas (in)", "Centímetros (cm)"])
        self.combo_size_units.currentIndexChanged.connect(self._on_size_unit_changed)
        grid_exp.addWidget(self.combo_size_units, 2, 1)

        grid_exp.addWidget(QLabel("Ancho x Alto:"), 3, 0)
        h_dim = QHBoxLayout()
        self.spin_width = QDoubleSpinBox()
        self.spin_width.setRange(1.0, 150.0)
        self.spin_width.setValue(7.0)
        self.spin_width.setSingleStep(0.5)
        self.spin_width.setDecimals(2)
        self.spin_width.valueChanged.connect(self.update_preview)
        h_dim.addWidget(self.spin_width)

        h_dim.addWidget(QLabel("x"))
        self.spin_height = QDoubleSpinBox()
        self.spin_height.setRange(1.0, 150.0)
        self.spin_height.setValue(5.0)
        self.spin_height.setSingleStep(0.5)
        self.spin_height.setDecimals(2)
        self.spin_height.valueChanged.connect(self.update_preview)
        h_dim.addWidget(self.spin_height)

        self.lbl_unit_tag = QLabel("in")
        h_dim.addWidget(self.lbl_unit_tag)
        grid_exp.addLayout(h_dim, 3, 1)

        # Alias para compatibilidad con código existente
        self.spin_width_in = self.spin_width
        self.spin_height_in = self.spin_height

        grid_exp.addWidget(QLabel("Ajuste Predefinido:"), 4, 0)
        self.combo_presets = QComboBox()
        self.combo_presets.addItems([
            "Personalizado",
            "1 Columna Revista (3.35 in / 8.5 cm)",
            "1.5 Columnas (4.72 in / 12.0 cm)",
            "2 Columnas / Ancho Completo (7.00 in / 17.8 cm)",
            "Diapositiva 16:9 (10.0 in / 25.4 cm)",
            "Cuadrada 1:1 (5.00 in / 12.7 cm)"
        ])
        self.combo_presets.currentIndexChanged.connect(self._on_preset_changed)
        grid_exp.addWidget(self.combo_presets, 4, 1)

        lay_exp.addLayout(grid_exp)

        self.btn_export_figure = QPushButton("💾 Exportar Figura Científica...")
        self.btn_export_figure.setObjectName("primaryBtn")
        self.btn_export_figure.setStyleSheet("padding: 8px; font-size: 12px; font-weight: bold;")
        self.btn_export_figure.clicked.connect(self._on_export_figure)
        lay_exp.addWidget(self.btn_export_figure)

        self.btn_export_data = QPushButton("📊 Exportar Curvas Numéricas (.txt / .dat / .csv)...")
        self.btn_export_data.setObjectName("accentBtn")
        self.btn_export_data.setStyleSheet("padding: 8px; font-size: 12px; font-weight: bold;")
        self.btn_export_data.clicked.connect(self._on_export_data)
        lay_exp.addWidget(self.btn_export_data)

        left_layout.addWidget(grp_export)
        left_layout.addStretch()

        splitter.addWidget(left_scroll)

        # ── Panel Derecho: Vista Previa en Vivo ───────────────────────────────
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(6, 6, 6, 6)
        right_layout.setSpacing(6)

        lbl_pv = QLabel("Vista Previa en Vivo (Render Editorial WYSIWYG):")
        lbl_pv.setStyleSheet("font-weight: bold; color: #cba6f7;")
        right_layout.addWidget(lbl_pv)

        right_layout.addWidget(self.canvas, stretch=1)

        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

    def _populate_layers(self):
        self.table_layers.setRowCount(len(self.layers))
        for r, layer in enumerate(self.layers):
            # Checkbox de visibilidad
            chk = QCheckBox()
            chk.setChecked(layer.get('visible', True))
            chk.toggled.connect(lambda checked, idx=r: self._on_layer_visibility(idx, checked))
            cell_w = QWidget()
            lay_chk = QHBoxLayout(cell_w)
            lay_chk.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay_chk.setContentsMargins(0, 0, 0, 0)
            lay_chk.addWidget(chk)
            self.table_layers.setCellWidget(r, 0, cell_w)

            # Nombre
            it_name = QTableWidgetItem(layer.get('name', ''))
            self.table_layers.setItem(r, 1, it_name)

            # Tipo
            it_type = QTableWidgetItem(layer.get('type', ''))
            it_type.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table_layers.setItem(r, 2, it_type)

            # Botón de Color
            btn_color = QPushButton()
            c_hex = layer.get('color', '#89b4fa')
            btn_color.setStyleSheet(f"background-color: {c_hex}; border: 1px solid #cdd6f4; border-radius: 4px; min-width: 24px;")
            btn_color.clicked.connect(lambda _, idx=r: self._choose_layer_color(idx))
            self.table_layers.setCellWidget(r, 3, btn_color)

            # Grosor / Tamaño
            spin_w = QDoubleSpinBox()
            spin_w.setRange(0.5, 12.0)
            spin_w.setValue(float(layer.get('linewidth', layer.get('size', 2.0))))
            spin_w.setSingleStep(0.5)
            spin_w.valueChanged.connect(lambda val, idx=r: self._on_layer_width(idx, val))
            self.table_layers.setCellWidget(r, 4, spin_w)

        self.table_layers.itemChanged.connect(self._on_table_item_changed)

    def _on_table_item_changed(self, item):
        row = item.row()
        col = item.column()
        if col == 1 and 0 <= row < len(self.layers):
            self.layers[row]['name'] = item.text()
            self.update_preview()

    def _toggle_all_layers(self):
        any_visible = any(layer.get('visible', True) for layer in self.layers)
        new_state = not any_visible
        for r, layer in enumerate(self.layers):
            layer['visible'] = new_state
            cell = self.table_layers.cellWidget(r, 0)
            if cell:
                chk = cell.findChild(QCheckBox)
                if chk:
                    chk.setChecked(new_state)
        self.update_preview()

    def _on_layer_visibility(self, idx: int, checked: bool):
        if 0 <= idx < len(self.layers):
            self.layers[idx]['visible'] = checked
            self.update_preview()

    def _on_layer_width(self, idx: int, val: float):
        if 0 <= idx < len(self.layers):
            if 'linewidth' in self.layers[idx]:
                self.layers[idx]['linewidth'] = val
            if 'size' in self.layers[idx]:
                self.layers[idx]['size'] = val
            self.update_preview()

    def _choose_layer_color(self, idx: int):
        if 0 <= idx < len(self.layers):
            init_c = QColor(self.layers[idx].get('color', '#89b4fa'))
            color = QColorDialog.getColor(init_c, self, f"Color para {self.layers[idx]['name']}")
            if color.isValid():
                hex_c = color.name()
                self.layers[idx]['color'] = hex_c
                btn = self.table_layers.cellWidget(idx, 3)
                if btn:
                    btn.setStyleSheet(f"background-color: {hex_c}; border: 1px solid #cdd6f4; border-radius: 4px; min-width: 24px;")
                self.update_preview()

    def _on_size_unit_changed(self, idx: int):
        # idx 0: in, idx 1: cm
        self.spin_width.blockSignals(True)
        self.spin_height.blockSignals(True)
        if idx == 1:  # Pasar a cm
            w_cm = self.spin_width.value() * 2.54
            h_cm = self.spin_height.value() * 2.54
            self.spin_width.setRange(2.5, 300.0)
            self.spin_height.setRange(2.5, 300.0)
            self.spin_width.setValue(w_cm)
            self.spin_height.setValue(h_cm)
            self.lbl_unit_tag.setText("cm")
        else:  # Pasar a in
            w_in = self.spin_width.value() / 2.54
            h_in = self.spin_height.value() / 2.54
            self.spin_width.setRange(1.0, 120.0)
            self.spin_height.setRange(1.0, 120.0)
            self.spin_width.setValue(w_in)
            self.spin_height.setValue(h_in)
            self.lbl_unit_tag.setText("in")
        self.spin_width.blockSignals(False)
        self.spin_height.blockSignals(False)
        self.update_preview()

    def _get_size_in_inches(self) -> tuple[float, float]:
        unit = getattr(self, 'combo_size_units', None)
        u_idx = unit.currentIndex() if unit is not None else 0
        w = self.spin_width.value() if hasattr(self, 'spin_width') else 7.0
        h = self.spin_height.value() if hasattr(self, 'spin_height') else 5.0
        if u_idx == 1:  # cm -> in
            return w / 2.54, h / 2.54
        return w, h

    def _on_preset_changed(self, idx: int):
        if idx == 0:
            return  # Personalizado
        is_cm = (self.combo_size_units.currentIndex() == 1)
        presets_in = {
            1: (3.35, 2.60),  # 1 Columna (8.5 cm)
            2: (4.72, 3.50),  # 1.5 Columnas (12.0 cm)
            3: (7.00, 4.80),  # 2 Columnas (17.8 cm)
            4: (10.0, 5.62),  # Diapositiva 16:9
            5: (5.00, 5.00),  # Cuadrada 1:1
        }
        if idx in presets_in:
            win_in, hin_in = presets_in[idx]
            self.spin_width.blockSignals(True)
            self.spin_height.blockSignals(True)
            if is_cm:
                self.spin_width.setValue(win_in * 2.54)
                self.spin_height.setValue(hin_in * 2.54)
            else:
                self.spin_width.setValue(win_in)
                self.spin_height.setValue(hin_in)
            self.spin_width.blockSignals(False)
            self.spin_height.blockSignals(False)
            self.update_preview()

    def _auto_fit_limits_to_data(self):
        xmin, xmax, ymin, ymax = self._compute_data_bounds()
        self.spin_xmin.blockSignals(True)
        self.spin_xmax.blockSignals(True)
        self.spin_ymin.blockSignals(True)
        self.spin_ymax.blockSignals(True)
        self.spin_xmin.setValue(xmin)
        self.spin_xmax.setValue(xmax)
        self.spin_ymin.setValue(ymin)
        self.spin_ymax.setValue(ymax)
        self.spin_xmin.blockSignals(False)
        self.spin_xmax.blockSignals(False)
        self.spin_ymin.blockSignals(False)
        self.spin_ymax.blockSignals(False)
        self.chk_xlim.setChecked(True)
        self.chk_ylim.setChecked(True)
        self.update_preview()

    def update_preview(self):
        """Redibuja la figura en el FigureCanvasQTAgg según la configuración actual."""
        self.fig.clear()

        # Ajustar relación de aspecto de la vista previa según dimensiones configuradas
        w_in, h_in = self._get_size_in_inches()
        ratio = w_in / max(0.1, h_in)
        pv_w = 7.0
        pv_h = max(2.5, min(8.0, pv_w / ratio))
        self.fig.set_size_inches(pv_w, pv_h)

        # Configuración de Fondo
        bg_mode = self.combo_bg.currentIndex()
        if bg_mode == 0:
            # Blanco Publicación
            fig_bg = '#ffffff'
            ax_bg = '#ffffff'
            fg_color = '#11111b'
            grid_color = '#d0d0d0'
        elif bg_mode == 1:
            # Oscuro Catppuccin
            fig_bg = '#181825'
            ax_bg = '#1e1e2e'
            fg_color = '#cdd6f4'
            grid_color = '#313244'
        else:
            # Transparente
            fig_bg = 'none'
            ax_bg = 'none'
            fg_color = '#11111b'
            grid_color = '#d0d0d0'

        self.fig.patch.set_facecolor(fig_bg if fig_bg != 'none' else 'white')
        if fig_bg == 'none':
            self.fig.patch.set_alpha(0.0)

        ax = self.fig.add_subplot(111)
        ax.set_facecolor(ax_bg if ax_bg != 'none' else 'white')
        if ax_bg == 'none':
            ax.patch.set_alpha(0.0)

        # Configuración de Ejes y Tipografía
        font_family = self.combo_font.currentText()
        plt.rcParams['font.family'] = font_family

        # Motor de Matemáticas LaTeX (mathtext)
        if hasattr(self, 'combo_math_font'):
            m_idx = self.combo_math_font.currentIndex()
            if m_idx == 0:
                matplotlib.rcParams['mathtext.fontset'] = 'cm'
            elif m_idx == 1:
                matplotlib.rcParams['mathtext.fontset'] = 'stix'
            else:
                matplotlib.rcParams['mathtext.fontset'] = 'dejavusans'

        ax.spines['bottom'].set_color(fg_color)
        ax.spines['top'].set_color(fg_color)
        ax.spines['left'].set_color(fg_color)
        ax.spines['right'].set_color(fg_color)
        ax.tick_params(colors=fg_color, which='both', labelsize=9)

        if self.chk_grid.isChecked():
            ax.grid(True, linestyle='--', alpha=0.6, color=grid_color)
        else:
            ax.grid(False)

        use_latex = getattr(self, 'chk_latex', None) is None or self.chk_latex.isChecked()

        def _fmt_label(t: str) -> str:
            if not t: return ""
            if not use_latex:
                return t.replace('$', '')
            return t

        title_txt = _fmt_label(self.edit_title.text().strip())
        if title_txt:
            ax.set_title(title_txt, color=fg_color, fontsize=11, fontweight='bold', pad=10)

        xlab = _fmt_label(self.edit_xlabel.text().strip())
        if xlab:
            ax.set_xlabel(xlab, color=fg_color, fontsize=10)

        ylab = _fmt_label(self.edit_ylabel.text().strip())
        if ylab:
            ax.set_ylabel(ylab, color=fg_color, fontsize=10)

        # Delimitación de Ejes xlim / ylim
        if hasattr(self, 'chk_xlim') and self.chk_xlim.isChecked():
            x0 = self.spin_xmin.value()
            x1 = self.spin_xmax.value()
            if x0 != x1:
                ax.set_xlim(min(x0, x1), max(x0, x1))

        if hasattr(self, 'chk_ylim') and self.chk_ylim.isChecked():
            y0 = self.spin_ymin.value()
            y1 = self.spin_ymax.value()
            if y0 != y1:
                ax.set_ylim(min(y0, y1), max(y0, y1))

        # Dibujar cada capa
        has_legend_items = False
        for layer in self.layers:
            if not layer.get('visible', True):
                continue

            ltype = layer.get('type')
            label = _fmt_label(layer.get('name', ''))

            if ltype == 'curve':
                x = layer['x']
                y = layer['y']
                c = layer.get('color', '#89b4fa')
                lw = layer.get('linewidth', 1.5)
                ls = layer.get('linestyle', 'solid')
                sym = layer.get('symbol')

                marker = 'o' if sym == 'o' else (None if not sym else 's')
                ax.plot(x, y, label=label, color=c, linewidth=lw, linestyle=ls, marker=marker, markersize=4)
                has_legend_items = True

            elif ltype == 'scatter':
                x = layer['x']
                y = layer['y']
                c = layer.get('color', '#f9e2af')
                sz = layer.get('size', 6.0)
                ax.scatter(x, y, label=label, color=c, s=(sz ** 2), alpha=0.85, edgecolors='none')
                has_legend_items = True

            elif ltype == 'infoline':
                pos = layer['pos']
                angle = layer.get('angle', 90)
                c = layer.get('color', '#f38ba8')
                lw = layer.get('linewidth', 1.2)
                ls = layer.get('linestyle', '--')
                if angle == 90:
                    ax.axvline(pos, color=c, linewidth=lw, linestyle=ls, label=label)
                else:
                    ax.axhline(pos, color=c, linewidth=lw, linestyle=ls, label=label)
                has_legend_items = True

            elif ltype == 'image':
                img = layer['image']
                ext = layer.get('extent')
                ax.imshow(img.T, extent=ext, origin='lower', cmap='cividis', aspect='equal')

            elif ltype == 'bar':
                x = layer.get('x')
                h = layer.get('height')
                w = layer.get('width', 0.55)
                colors = layer.get('colors', ['#89b4fa'])
                if x is not None and h is not None and len(x) > 0:
                    c_list = colors if len(colors) == len(x) else [layer.get('color', '#89b4fa')] * len(x)
                    ax.bar(x, h, width=w, color=c_list, edgecolor=fg_color, linewidth=0.8, alpha=0.9, label=label)
                    ticks = layer.get('ticks')
                    if ticks and len(ticks) > 0 and len(ticks[0]) > 0:
                        major_ticks = ticks[0]
                        tick_positions = [t[0] for t in major_ticks]
                        tick_labels = [t[1] for t in major_ticks]
                        ax.set_xticks(tick_positions)
                        ax.set_xticklabels(tick_labels, rotation=30, ha='right', fontsize=8, color=fg_color)
                    has_legend_items = True

            elif ltype == 'text':
                tx = layer.get('x', 0.0)
                ty = layer.get('y', 0.0)
                ttxt = _fmt_label(layer.get('text', ''))
                tc = layer.get('color', fg_color)
                ax.text(tx, ty, ttxt, color=tc, fontsize=8, ha='center', va='bottom')

        if self.chk_legend.isChecked() and has_legend_items:
            loc = self.combo_legend_loc.currentText()
            leg = ax.legend(loc=loc, fontsize=8, framealpha=0.85)
            if leg:
                leg.get_frame().set_facecolor(fig_bg if fig_bg != 'none' else '#ffffff')
                leg.get_frame().set_edgecolor(fg_color)
                for text in leg.get_texts():
                    text.set_color(fg_color)

        try:
            self.fig.tight_layout()
            self.canvas.draw()
        except Exception:
            # Fallback seguro en caso de sintaxis incompleta mientras el usuario escribe fórmulas LaTeX
            try:
                if title_txt: ax.set_title(title_txt.replace('$', ''), color=fg_color, fontsize=11, fontweight='bold', pad=10)
                if xlab: ax.set_xlabel(xlab.replace('$', ''), color=fg_color, fontsize=10)
                if ylab: ax.set_ylabel(ylab.replace('$', ''), color=fg_color, fontsize=10)
                self.fig.tight_layout()
                self.canvas.draw()
            except Exception:
                pass

    def _on_export_figure(self):
        """Exporta la figura con la máxima fidelidad y opciones científicas."""
        fmt_idx = self.combo_format.currentIndex()
        if fmt_idx == 0:
            def_ext = "svg"
            filter_str = "SVG Vectorial Nativo (*.svg)"
        elif fmt_idx == 1:
            def_ext = "png"
            filter_str = "Imagen PNG Alta Resolución (*.png)"
        elif fmt_idx == 2:
            def_ext = "pdf"
            filter_str = "Documento PDF Vectorial (*.pdf)"
        elif fmt_idx == 3:
            def_ext = "tiff"
            filter_str = "Imagen TIFF Científica (*.tiff)"
        else:
            def_ext = "jpg"
            filter_str = "Imagen JPEG (*.jpg)"

        default_fname = f"{self.default_title}.{def_ext}"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Guardar Figura Científica",
            default_fname,
            f"{filter_str};;Todos los Archivos (*.*)"
        )
        if not file_path:
            return

        # DPI
        dpi_str = self.combo_dpi.currentText()
        if "1200" in dpi_str:
            dpi = 1200
        elif "600" in dpi_str:
            dpi = 600
        elif "300" in dpi_str:
            dpi = 300
        else:
            dpi = 150

        # Dimensiones en pulgadas reales
        w_in, h_in = self._get_size_in_inches()

        bg_mode = self.combo_bg.currentIndex()
        is_transparent = (bg_mode == 2)

        orig_size = self.fig.get_size_inches()
        try:
            self.fig.set_size_inches(w_in, h_in)

            if def_ext == "svg":
                # CRÍTICO: svg.fonttype = 'none' garantiza texto editable en Inkscape/Illustrator
                matplotlib.rcParams['svg.fonttype'] = 'none'
                self.fig.savefig(
                    file_path,
                    format='svg',
                    dpi=dpi,
                    bbox_inches='tight',
                    transparent=is_transparent
                )
            elif def_ext == "pdf":
                matplotlib.rcParams['pdf.fonttype'] = 42
                self.fig.savefig(
                    file_path,
                    format='pdf',
                    dpi=dpi,
                    bbox_inches='tight',
                    transparent=is_transparent
                )
            else:
                self.fig.savefig(
                    file_path,
                    dpi=dpi,
                    bbox_inches='tight',
                    transparent=is_transparent
                )

            QMessageBox.information(
                self,
                "Exportación Exitosa",
                f"Figura guardada exitosamente en:\n{file_path}\n"
                f"Dimensiones: {w_in:.2f} x {h_in:.2f} in ({w_in*2.54:.1f} x {h_in*2.54:.1f} cm) | {dpi} DPI"
            )
        except Exception as e:
            QMessageBox.critical(self, "Error de Exportación", f"No se pudo guardar la figura:\n{str(e)}")
        finally:
            self.fig.set_size_inches(orig_size)
            self.canvas.draw()

    def _on_export_data(self):
        """Exporta las curvas numéricas visibles en un archivo tabular estructurado."""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Exportar Curvas Numéricas",
            f"datos_curvas_{self.default_title}.txt",
            "Archivo de Texto Científico (*.txt);;Archivo DAT (*.dat);;Valores Separados por Coma (*.csv);;Todos (*.*)"
        )
        if not file_path:
            return

        visible_curves = [
            layer for layer in self.layers
            if layer.get('visible', True) and (
                (layer.get('type') in ('curve', 'scatter') and 'x' in layer and 'y' in layer) or
                (layer.get('type') == 'bar' and 'x' in layer and ('y' in layer or 'height' in layer))
            )
        ]

        if not visible_curves:
            QMessageBox.warning(self, "Sin Curvas", "No hay curvas visibles para exportar.")
            return

        is_csv = file_path.lower().endswith(".csv")
        sep = "," if is_csv else "\t"

        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(f"# PyPrinting 3.0 — Datos Numéricos de Curvas de Gráfico\n")
                f.write(f"# Título: {self.edit_title.text()}\n")
                f.write(f"# Eje X: {self.edit_xlabel.text()}\n")
                f.write(f"# Eje Y: {self.edit_ylabel.text()}\n")
                f.write(f"# Número de Curvas: {len(visible_curves)}\n#\n")

                for i, c in enumerate(visible_curves):
                    x_vals = c['x']
                    y_vals = c['y'] if 'y' in c else c['height']
                    f.write(f"# ── Curva #{i+1}: {c['name']} (Tipo: {c.get('type')}, Total Puntos: {len(x_vals)}) ──\n")
                    f.write(f"# X{sep}Y\n")
                    for x_val, y_val in zip(x_vals, y_vals):
                        f.write(f"{x_val:.6e}{sep}{y_val:.6e}\n")
                    f.write("\n")

            QMessageBox.information(
                self,
                "Datos Exportados",
                f"Datos numéricos guardados exitosamente en:\n{file_path}\n"
                f"Se exportaron {len(visible_curves)} curvas listas para OriginLab, Python o MATLAB."
            )
        except Exception as e:
            QMessageBox.critical(self, "Error al Exportar Datos", f"Detalle: {str(e)}")
