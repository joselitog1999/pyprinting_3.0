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
            except Exception:
                pass
        return meta

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
                if img is not None and img.size > 0:
                    rect = it.rect()
                    layers.append({
                        'id': idx,
                        'type': 'image',
                        'name': f"Mapa 2D ({img.shape[0]}x{img.shape[1]})",
                        'image': img.copy(),
                        'extent': (rect.left(), rect.right(), rect.bottom(), rect.top()),
                        'visible': it.isVisible()
                    })
                    idx += 1

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

        grid_c.addWidget(QLabel("Fuente:"), 1, 0)
        self.combo_font = QComboBox()
        self.combo_font.addItems(["DejaVu Sans", "Arial", "Helvetica", "Times New Roman", "Segoe UI"])
        self.combo_font.currentIndexChanged.connect(self.update_preview)
        grid_c.addWidget(self.combo_font, 1, 1)

        grid_c.addWidget(QLabel("Título:"), 2, 0)
        self.edit_title = QLineEdit(self.plot_metadata['title'])
        self.edit_title.textChanged.connect(self.update_preview)
        grid_c.addWidget(self.edit_title, 2, 1)

        grid_c.addWidget(QLabel("Etiqueta X:"), 3, 0)
        self.edit_xlabel = QLineEdit(f"{self.plot_metadata['xlabel']} [{self.plot_metadata['xunits']}]" if self.plot_metadata['xunits'] else self.plot_metadata['xlabel'])
        self.edit_xlabel.textChanged.connect(self.update_preview)
        grid_c.addWidget(self.edit_xlabel, 3, 1)

        grid_c.addWidget(QLabel("Etiqueta Y:"), 4, 0)
        self.edit_ylabel = QLineEdit(f"{self.plot_metadata['ylabel']} [{self.plot_metadata['yunits']}]" if self.plot_metadata['yunits'] else self.plot_metadata['ylabel'])
        self.edit_ylabel.textChanged.connect(self.update_preview)
        grid_c.addWidget(self.edit_ylabel, 4, 1)

        lay_canvas.addLayout(grid_c)

        h_opts = QHBoxLayout()
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

        # Grupo 3: Exportación Científica Multiformato
        grp_export = QGroupBox("3. Exportación Multiformato & Datos")
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

        grid_exp.addWidget(QLabel("Ancho x Alto (pulg):"), 2, 0)
        h_dim = QHBoxLayout()
        self.spin_width_in = QDoubleSpinBox()
        self.spin_width_in.setRange(2.0, 30.0)
        self.spin_width_in.setValue(7.0)
        self.spin_width_in.setSingleStep(0.5)
        h_dim.addWidget(self.spin_width_in)

        h_dim.addWidget(QLabel("x"))
        self.spin_height_in = QDoubleSpinBox()
        self.spin_height_in.setRange(2.0, 30.0)
        self.spin_height_in.setValue(5.0)
        self.spin_height_in.setSingleStep(0.5)
        h_dim.addWidget(self.spin_height_in)
        grid_exp.addLayout(h_dim, 2, 1)

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

    def update_preview(self):
        """Redibuja la figura en el FigureCanvasQTAgg según la configuración actual."""
        self.fig.clear()

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

        ax.spines['bottom'].set_color(fg_color)
        ax.spines['top'].set_color(fg_color)
        ax.spines['left'].set_color(fg_color)
        ax.spines['right'].set_color(fg_color)
        ax.tick_params(colors=fg_color, which='both', labelsize=9)

        if self.chk_grid.isChecked():
            ax.grid(True, linestyle='--', alpha=0.6, color=grid_color)
        else:
            ax.grid(False)

        title_txt = self.edit_title.text().strip()
        if title_txt:
            ax.set_title(title_txt, color=fg_color, fontsize=11, fontweight='bold', pad=10)

        xlab = self.edit_xlabel.text().strip()
        if xlab:
            ax.set_xlabel(xlab, color=fg_color, fontsize=10)

        ylab = self.edit_ylabel.text().strip()
        if ylab:
            ax.set_ylabel(ylab, color=fg_color, fontsize=10)

        # Dibujar cada capa
        has_legend_items = False
        for layer in self.layers:
            if not layer.get('visible', True):
                continue

            ltype = layer.get('type')
            label = layer.get('name')

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

        if self.chk_legend.isChecked() and has_legend_items:
            loc = self.combo_legend_loc.currentText()
            leg = ax.legend(loc=loc, fontsize=8, framealpha=0.85)
            if leg:
                leg.get_frame().set_facecolor(fig_bg if fig_bg != 'none' else '#ffffff')
                leg.get_frame().set_edgecolor(fg_color)
                for text in leg.get_texts():
                    text.set_color(fg_color)

        self.fig.tight_layout()
        self.canvas.draw()

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

        # Dimensiones
        w_in = self.spin_width_in.value()
        h_in = self.spin_height_in.value()

        bg_mode = self.combo_bg.currentIndex()
        is_transparent = (bg_mode == 2)

        try:
            # Configurar tamaño temporal
            orig_size = self.fig.get_size_inches()
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

            self.fig.set_size_inches(orig_size)
            self.canvas.draw()

            QMessageBox.information(
                self,
                "Exportación Exitosa",
                f"Figura guardada exitosamente en:\n{file_path}\n"
                f"Resolución: {dpi} DPI | Dimensiones: {w_in} x {h_in} in"
            )
        except Exception as e:
            QMessageBox.critical(self, "Error al Exportar", f"No se pudo guardar la figura:\n{str(e)}")

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
            if layer.get('visible', True) and layer.get('type') in ('curve', 'scatter') and 'x' in layer and 'y' in layer
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
                    f.write(f"# ── Curva #{i+1}: {c['name']} (Total Puntos: {len(c['x'])}) ──\n")
                    f.write(f"# X{sep}Y\n")
                    for x_val, y_val in zip(c['x'], c['y']):
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
