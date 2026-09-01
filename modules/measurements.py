# -*- coding: utf-8 -*-
"""
measurements.py — Grillas de impresión y dímeros (Printing + Dimers unificados)
PyPrinting — UNSAM Nanofotónica  —  PyQt6

Reemplaza Printing_pp.py + Dimers_pp.py.
Ambos módulos comparten ~80% del código; la diferencia está en:
  - mode='printing': ciclo mover→autofoco→traza→(scan_optional)→detect
  - mode='dimers':   ciclo mover→autofoco→center_scan→(pree_scan)→traza→(post_scan)→detect
    con los booleanos preescanbool y postscanbool que habilitan los scans extra.

Incorpora 5 Modos de Criterio de Parada Seleccionables en Tiempo Real:
  - Modo 0: Legacy (Salto Relativo Estándar I_new / I_old > Umbral)
  - Modo 1: Salto Relativo + Umbral Absoluto (V) & Anti-Paso (N_hold steps)
  - Modo 2: Derivada Temporal Adaptativa & Aplanamiento (dI/dt -> 0 post-pico)
  - Modo 3: Calibración Confocal Raw & Umbral Absoluto Reescalado (K_scale, P%)
  - Modo 4: Criterio Híbrido Tri-Factor (All-In-One)
"""
from __future__ import annotations
import os
import sys
import time
import numpy as np

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from PIL import Image
import tkinter as tk
from tkinter import filedialog

import pyqtgraph as pg
from PyQt6.QtCore    import Qt, QObject, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (QApplication, QWidget, QFrame, QGridLayout,
                               QHBoxLayout, QVBoxLayout, QLabel, QLineEdit, QComboBox,
                               QPushButton, QCheckBox, QGroupBox, QProgressBar,
                               QFileDialog, QInputDialog, QMessageBox, QDialog)
from PyQt6.QtGui     import QIntValidator
from pyqtgraph.dockarea import DockArea, Dock

from config import (pi, SAFE_MODE, SHUTTERS, DEFAULT_DATA_PATH, LAST_POS_FILE,
                    DEFAULT_GRID_NPS_COL, DEFAULT_GRID_COLS,
                    DEFAULT_GRID_DIST_NP, DEFAULT_GRID_DIST_COL,
                    DEFAULT_PRINTING_UMBRAL, DEFAULT_PRINTING_UMBRAL_DOWN,
                    DEFAULT_PRINTING_TMAX, DEFAULT_PRINTING_STEPS_BEFORE,
                    DEFAULT_PRINTING_STEPS_AFTER, DEFAULT_PRINTING_AUTOFOCUS_EVERY,
                    DEFAULT_PRINTING_SHIFT_X, DEFAULT_PRINTING_SHIFT_Y,
                    DEFAULT_DIMERS_DX, DEFAULT_DIMERS_DY)
from nidaq  import (open_shutter, close_shutter,
                    up_flipper, down_flipper)


# ══════════════════════════════════════════════════════════════════════════════
#  INTERACTIVE GRID VIEWER (Display 2D del patrón, camino y estado de partículas)
# ══════════════════════════════════════════════════════════════════════════════

class InteractiveGridWidget(QFrame):
    """
    Visualizador 2D interactivo y desplegable del patrón de la grilla de impresión.
    Muestra la trayectoria continua del microscopio (camino) y el cambio de color
    de cada partícula según su estado (pendiente, activa, impresa, timeout).
    """
    nodeClickedSignal = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Raised)

        self.grid_coords: np.ndarray | None = None  # Array (2, N) [xs, ys]
        self.node_states: list[str] = []            # "pending", "active", "success", "timeout"
        self.text_items: list[pg.TextItem] = []

        self._show_numbers = True
        self._show_path    = True

        self._setup_ui()

    def _setup_ui(self):
        vlo = QVBoxLayout(self)
        vlo.setContentsMargins(4, 4, 4, 4)
        vlo.setSpacing(4)

        # ── Barra de herramientas superior ──────────────────────────────────
        tb = QWidget()
        tlo = QHBoxLayout(tb)
        tlo.setContentsMargins(0, 0, 0, 0)
        tlo.setSpacing(6)

        self.chk_numbers = QCheckBox("🏷️ Números")
        self.chk_numbers.setChecked(True)
        self.chk_numbers.setToolTip("Mostrar u ocultar la numeración de los nodos (0, 1, 2...)")
        self.chk_numbers.toggled.connect(self._toggle_numbers)

        self.chk_path = QCheckBox("🛤️ Camino")
        self.chk_path.setChecked(True)
        self.chk_path.setToolTip("Mostrar u ocultar la línea de trayectoria que seguirá el microscopio")
        self.chk_path.toggled.connect(self._toggle_path)

        self.btn_reset = QPushButton("🎯 Reset View")
        self.btn_reset.setToolTip("Auto-centrar y ajustar la vista a la grilla completa")
        self.btn_reset.clicked.connect(self.reset_view)
        self.btn_reset.setFixedHeight(24)

        tlo.addWidget(self.chk_numbers)
        tlo.addWidget(self.chk_path)
        tlo.addStretch()
        tlo.addWidget(self.btn_reset)

        vlo.addWidget(tb)

        # ── Visualizador PyQtGraph (Sistema Cartesiano Estándar) ────────────
        # Sistema cartesiano:
        #   Eje Horizontal = X (Positivo +X a la derecha)
        #   Eje Vertical   = Y (Positivo +Y hacia arriba)
        self.graphics = pg.GraphicsLayoutWidget()
        self.plot = self.graphics.addPlot()
        self.plot.setAspectLocked(True)
        self.plot.showGrid(x=True, y=True)
        self.plot.invertY(False)  # +Y hacia arriba (estándar cartesiano)
        self.plot.invertX(False)  # +X hacia la derecha (estándar cartesiano)

        label_style = {"color": "#cdd6f4", "font-size": "9pt"}
        self.plot.setLabel("left", "Y (µm)", **label_style)    # Eje vertical = Y
        self.plot.setLabel("bottom", "X (µm)", **label_style)  # Eje horizontal = X

        # Elementos del gráfico:
        # 1. Camino (Línea punteada de trayectoria)
        self.path_item = pg.PlotDataItem(
            pen=pg.mkPen(color="#89b4fa", width=2, style=Qt.PenStyle.DashLine)
        )
        self.plot.addItem(self.path_item)

        # 2. Scatter plot de nodos
        self.scatter_item = pg.ScatterPlotItem(size=14, hoverable=True)
        self.scatter_item.sigClicked.connect(self._on_scatter_clicked)
        self.plot.addItem(self.scatter_item)

        # 3. Anillo de destaque de partícula activa
        self.active_ring = pg.ScatterPlotItem(
            size=26, symbol="o",
            pen=pg.mkPen("#f9e2af", width=3),
            brush=pg.mkBrush(0, 0, 0, 0)
        )
        self.plot.addItem(self.active_ring)

        vlo.addWidget(self.graphics, stretch=1)

        # ── Leyenda de estados inferior ─────────────────────────────────────
        leg = QWidget()
        llo = QHBoxLayout(leg)
        llo.setContentsMargins(2, 2, 2, 2)
        llo.setSpacing(8)

        def badge(text: str, color_hex: str):
            lbl = QLabel(f"● {text}")
            lbl.setStyleSheet(f"QLabel {{ color: {color_hex}; font-size: 8pt; font-weight: bold; }}")
            return lbl

        llo.addWidget(badge("Pendiente", "#9399b2"))
        llo.addWidget(badge("En Proceso", "#f9e2af"))
        llo.addWidget(badge("Impresa", "#a6e3a1"))
        llo.addWidget(badge("Timeout", "#f38ba8"))
        llo.addStretch()

        vlo.addWidget(leg)

    def set_grid(self, datos: np.ndarray):
        """Carga las coordenadas de la grilla datos[2, N] y reconstruye la visualización en coordenadas cartesianas (X horizontal, Y vertical)."""
        if datos is None or datos.shape[0] < 2 or datos.shape[1] == 0:
            return

        self.grid_coords = datos
        xs_stage = datos[0, :]  # Coordenada X platina (horizontal)
        ys_stage = datos[1, :]  # Coordenada Y platina (vertical)
        N = len(xs_stage)

        # Mapeo a pantalla: X_display = X_stage (horiz), Y_display = Y_stage (vert)
        x_disp = xs_stage
        y_disp = ys_stage

        self.node_states = ["pending"] * N

        # Limpiar elementos de texto anteriores
        for ti in self.text_items:
            self.plot.removeItem(ti)
        self.text_items.clear()

        # Crear TextItems con número de nodo
        for idx in range(N):
            ti = pg.TextItem(text=str(idx), color="#cdd6f4", anchor=(0.5, 1.3))
            ti.setPos(x_disp[idx], y_disp[idx])
            ti.setVisible(self._show_numbers)
            self.plot.addItem(ti)
            self.text_items.append(ti)

        # Actualizar línea de camino
        if self._show_path and N > 1:
            self.path_item.setData(x_disp, y_disp)
            self.path_item.show()
        else:
            self.path_item.hide()

        self._update_scatter()
        self.active_ring.clear()
        self.plot.autoRange()

    def set_node_status(self, idx: int, status: str):
        """Actualiza el estado del nodo idx ('active', 'retrying', 'success', 'timeout', 'pending')."""
        if self.grid_coords is None or idx < 0 or idx >= len(self.node_states):
            return

        # Si el anterior estaba en 'active', revertir a 'success' si no era timeout
        for i, st in enumerate(self.node_states):
            if st in ("active", "retrying") and i != idx:
                if st == "active" and self.node_states[i] not in ("timeout", "pending"):
                    self.node_states[i] = "success"

        self.node_states[idx] = status

        x_disp = self.grid_coords[0, :]  # X_stage (pantalla horiz)
        y_disp = self.grid_coords[1, :]  # Y_stage (pantalla vert)

        if status in ("active", "retrying"):
            self.active_ring.setData([x_disp[idx]], [y_disp[idx]])
            pen_color = "#fab387" if status == "retrying" else "#f9e2af"
            self.active_ring.setPen(pg.mkPen(pen_color, width=2))
        elif all(s not in ("active", "retrying") for s in self.node_states):
            self.active_ring.clear()

        self._update_scatter()

    def _update_scatter(self):
        if self.grid_coords is None:
            return

        x_disp = self.grid_coords[0, :]  # X_stage (pantalla horiz)
        y_disp = self.grid_coords[1, :]  # Y_stage (pantalla vert)
        N = len(x_disp)

        color_map = {
            "pending":  "#45475a",
            "active":   "#f9e2af",
            "retrying": "#fab387",  # Naranja cálido para nodos en Healing Pass
            "success":  "#a6e3a1",
            "timeout":  "#f38ba8",
        }

        spots = []
        for i in range(N):
            st = self.node_states[i]
            col = color_map.get(st, "#45475a")
            spots.append({
                'pos': (x_disp[i], y_disp[i]),
                'data': i,
                'brush': pg.mkBrush(col),
                'pen': pg.mkPen('#11111b', width=1),
                'symbol': 'o',
                'size': 16 if st in ('active', 'retrying') else 14
            })

        self.scatter_item.setData(spots)

    def _on_scatter_clicked(self, plot, points):
        if len(points) > 0:
            idx = points[0].data()
            if idx is not None:
                self.nodeClickedSignal.emit(int(idx))

    def _toggle_numbers(self, checked: bool):
        self._show_numbers = checked
        for ti in self.text_items:
            ti.setVisible(checked)

    def _toggle_path(self, checked: bool):
        self._show_path = checked
        if self.grid_coords is not None and self.grid_coords.shape[1] > 1 and checked:
            self.path_item.show()
        else:
            self.path_item.hide()

    def reset_view(self):
        self.plot.autoRange()


# ══════════════════════════════════════════════════════════════════════════════
#  DRIFT TRACKING DIALOG (Mapa 2D de Trayectoria XY y Evolución Z)
# ══════════════════════════════════════════════════════════════════════════════

class DriftTrackingDialog(QDialog):
    """
    Ventana interactiva de visualización de Deriva Termomecánica post-impresión.
    Muestra:
      1. Mapa 2D de trayectoria de desplazamientos (ΔX, ΔY) en nm desde (0, 0).
      2. Evolución temporal de derivas laterales (ΔX, ΔY) y axial (ΔZ) en nm.
    """
    def __init__(self, data: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Drift Tracking Map 🧭 — PyPrinting 3.0")
        self.resize(920, 520)
        self.data = data
        self.folder = data.get("folder", "")
        self._setup_ui()

    def _setup_ui(self):
        vlo = QVBoxLayout(self)
        vlo.setContentsMargins(10, 10, 10, 10)

        v_xy_val = self.data.get("mean_v_xy", 0.0)
        v_z_val  = self.data.get("mean_v_z", 0.0)
        v_info_str = f" | ⚡ &lang;v_xy&rang;: <b>{v_xy_val:.2f} nm/s</b> | &lang;v_z&rang;: <b>{v_z_val:.2f} nm/s</b>" if (v_xy_val > 0 or v_z_val > 0) else ""

        lbl_info = QLabel(f"<b>🗺️ Mapa y Registro de Deriva Termomecánica</b> | Lote: <code>{self.folder}</code>{v_info_str}")
        lbl_info.setStyleSheet("color: #cdd6f4; font-size: 10pt;")
        vlo.addWidget(lbl_info)

        self.plot_widget = pg.GraphicsLayoutWidget()
        vlo.addWidget(self.plot_widget, stretch=1)

        # Plot 1: Trayectoria 2D XY (nm)
        self.p_xy = self.plot_widget.addPlot(row=0, col=0, title="Mapa 2D de Desplazamientos XY (nm)")
        self.p_xy.showGrid(x=True, y=True, alpha=0.5)
        self.p_xy.setLabel("bottom", "ΔX (nm)")
        self.p_xy.setLabel("left", "ΔY (nm)")

        # Plot 2: Serie temporal ΔX, ΔY, ΔZ (nm)
        self.p_t = self.plot_widget.addPlot(row=0, col=1, title="Evolución Temporal de Deriva (nm)")
        self.p_t.showGrid(x=True, y=True, alpha=0.5)
        self.p_t.setLabel("bottom", "Tiempo (s)")
        self.p_t.setLabel("left", "Deriva (nm)")
        self.p_t.addLegend()

        self._plot_data()

        # Botones inferiores
        btn_hlo = QHBoxLayout()
        self.btn_export_png = QPushButton("Exportar PNG 📸")
        self.btn_export_png.setToolTip("Guarda una imagen PNG del mapa de deriva en la carpeta del lote.")
        self.btn_export_png.clicked.connect(self._export_png)
        self.btn_close = QPushButton("Cerrar")
        self.btn_close.clicked.connect(self.accept)
        btn_hlo.addStretch()
        btn_hlo.addWidget(self.btn_export_png)
        btn_hlo.addWidget(self.btn_close)
        vlo.addLayout(btn_hlo)

        # Auto-exportar PNG a la carpeta del lote
        self._auto_save_png()

    def _plot_data(self):
        xy_list = self.data.get("xy", [])
        z_list  = self.data.get("z", [])

        if xy_list:
            dxs = [pt["dx_nm"] for pt in xy_list]
            dys = [pt["dy_nm"] for pt in xy_list]
            times_xy = [pt["time"] for pt in xy_list]

            # Curva de trayectoria XY
            self.p_xy.plot(dxs, dys, pen=pg.mkPen("#89b4fa", width=2, style=Qt.PenStyle.DashLine),
                           symbol='o', symbolSize=8, symbolBrush='#f38ba8', symbolPen='w')
            # Punto inicial (0,0)
            self.p_xy.plot([0.0], [0.0], symbol='star', symbolSize=14, symbolBrush='#a6e3a1', symbolPen='w')

            self.p_t.plot(times_xy, dxs, pen=pg.mkPen("#89b4fa", width=2), name="ΔX (nm)")
            self.p_t.plot(times_xy, dys, pen=pg.mkPen("#f38ba8", width=2), name="ΔY (nm)")

        if z_list:
            dzs = [pt["dz_nm"] for pt in z_list]
            times_z = [pt["time"] for pt in z_list]
            self.p_t.plot(times_z, dzs, pen=pg.mkPen("#a6e3a1", width=2), name="ΔZ (nm)")

    def _auto_save_png(self):
        if self.folder and os.path.exists(self.folder):
            png_path = os.path.join(self.folder, "drift_map.png")
            try:
                pixmap = self.plot_widget.grab()
                pixmap.save(png_path, "PNG")
                print(f"[Drift Tracking] 📸 Mapa de deriva guardado automáticamente en: {png_path}")
            except Exception as e:
                print(f"[Drift Tracking Error] Auto-guardado PNG: {e}")

    def _export_png(self):
        if self.folder and os.path.exists(self.folder):
            default_path = os.path.join(self.folder, "drift_map.png")
        else:
            default_path = "drift_map.png"
        path, _ = QFileDialog.getSaveFileName(self, "Guardar Mapa de Deriva", default_path, "PNG Image (*.png)")
        if path:
            pixmap = self.plot_widget.grab()
            pixmap.save(path, "PNG")
            QMessageBox.information(self, "Exportación Exitosa", f"Mapa de deriva guardado en:\n{path}")


# ══════════════════════════════════════════════════════════════════════════════
#  TIME-VOLT TRACKING DIALOG (Histogramas de Tiempos, Voltajes y Dispersión)
# ══════════════════════════════════════════════════════════════════════════════

class TimeVoltTrackingDialog(QDialog):
    """
    Ventana interactiva de visualización y distribución estadística Time-Volt post-impresión.
    Muestra:
      1. Histogramas de Tiempos: t_raw (tiempo total de exposición) vs t_step (tiempo real de adhesión).
      2. Histogramas de Voltajes: V_low (línea base) vs V_high (post-adhesión) y salto ΔV.
      3. Correlación 2D: Diagrama de dispersión t_step vs ΔV para cada partícula del lote.
    """
    def __init__(self, data: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Time-Volt Analytics & Histograms 📊 — PyPrinting 3.0")
        self.resize(1080, 520)
        self.data = data
        self.folder = data.get("folder", "")
        self.rows = data.get("rows", [])
        self._setup_ui()

    def _setup_ui(self):
        vlo = QVBoxLayout(self)
        vlo.setContentsMargins(10, 10, 10, 10)

        folder_name = os.path.basename(self.folder) if self.folder else "Lote"
        lbl_info = QLabel(f"<b>📊 Distribución Estadística Time-Volt & Histogramas de Impresión</b> | Lote: <code>{folder_name}</code>")
        lbl_info.setStyleSheet("color: #f9e2af; font-size: 10pt;")
        vlo.addWidget(lbl_info)

        self.plot_widget = pg.GraphicsLayoutWidget()
        vlo.addWidget(self.plot_widget, stretch=1)

        # Plot 1: Histogramas de Tiempos (t_raw vs t_step)
        self.p_time = self.plot_widget.addPlot(row=0, col=0, title="Tiempos: t_raw vs t_step (s)")
        self.p_time.showGrid(x=True, y=True, alpha=0.4)
        self.p_time.setLabel("bottom", "Tiempo (s)")
        self.p_time.setLabel("left", "Conteo / Frecuencia")
        self.p_time.addLegend()

        # Plot 2: Histogramas de Voltajes (V_low, V_high, ΔV)
        self.p_volt = self.plot_widget.addPlot(row=0, col=1, title="Voltajes: V_low, V_high y ΔV (V)")
        self.p_volt.showGrid(x=True, y=True, alpha=0.4)
        self.p_volt.setLabel("bottom", "Voltaje (V)")
        self.p_volt.setLabel("left", "Conteo / Frecuencia")
        self.p_volt.addLegend()

        # Plot 3: Scatter Plot t_step vs ΔV
        self.p_scatter = self.plot_widget.addPlot(row=0, col=2, title="Correlación: t_step vs ΔV")
        self.p_scatter.showGrid(x=True, y=True, alpha=0.4)
        self.p_scatter.setLabel("bottom", "t_step (s)")
        self.p_scatter.setLabel("left", "Salto ΔV (V)")
        self.p_scatter.addLegend()

        self._plot_data()

        # Botones inferiores
        btn_hlo = QHBoxLayout()
        self.btn_export_png = QPushButton("Exportar PNG 📸")
        self.btn_export_png.setToolTip("Guarda una imagen PNG de los histogramas y distribuciones en la carpeta del lote.")
        self.btn_export_png.clicked.connect(self._export_png)
        self.btn_close = QPushButton("Cerrar")
        self.btn_close.clicked.connect(self.accept)
        btn_hlo.addStretch()
        btn_hlo.addWidget(self.btn_export_png)
        btn_hlo.addWidget(self.btn_close)
        vlo.addLayout(btn_hlo)

        # Auto-guardado
        self._auto_save_png()

    def _plot_data(self):
        if not self.rows:
            return

        t_raw_vals   = [float(r.get("t_raw", 0.0)) for r in self.rows]
        t_step_vals  = [float(r.get("t_step", 0.0)) for r in self.rows]
        v_low_vals   = [float(r.get("v_low", 0.0)) for r in self.rows]
        v_high_vals  = [float(r.get("v_high", 0.0)) for r in self.rows]
        delta_v_vals = [float(r.get("delta_v", 0.0)) for r in self.rows]

        # ── 1. Histograma de Tiempos ──────────────────────────────────────────
        all_times = t_raw_vals + t_step_vals
        min_t, max_t = min(all_times), max(all_times)
        n_bins = max(4, min(12, len(self.rows)))
        bins_t = np.linspace(min_t, max_t if max_t > min_t else min_t + 1.0, n_bins + 1)
        w_t = (bins_t[1] - bins_t[0]) * 0.42

        counts_raw, _  = np.histogram(t_raw_vals, bins=bins_t)
        counts_step, _ = np.histogram(t_step_vals, bins=bins_t)
        centers_t = 0.5 * (bins_t[:-1] + bins_t[1:])

        bg_raw  = pg.BarGraphItem(x=centers_t - w_t/2, height=counts_raw, width=w_t, brush=pg.mkBrush("#89b4fa"), pen=pg.mkPen("#b4befe", width=1), name="t_raw (s)")
        bg_step = pg.BarGraphItem(x=centers_t + w_t/2, height=counts_step, width=w_t, brush=pg.mkBrush("#a6e3a1"), pen=pg.mkPen("#94e2d5", width=1), name="t_step (s)")
        self.p_time.addItem(bg_raw)
        self.p_time.addItem(bg_step)

        # Líneas de media
        m_t_raw, m_t_step = float(np.mean(t_raw_vals)), float(np.mean(t_step_vals))
        line_t_raw  = pg.InfiniteLine(pos=m_t_raw, angle=90, pen=pg.mkPen("#89b4fa", width=2, style=Qt.PenStyle.DashLine), label=f"<t_raw>={m_t_raw:.2f}s", labelOpts={'position': 0.9, 'color': '#89b4fa'})
        line_t_step = pg.InfiniteLine(pos=m_t_step, angle=90, pen=pg.mkPen("#a6e3a1", width=2, style=Qt.PenStyle.DashLine), label=f"<t_step>={m_t_step:.2f}s", labelOpts={'position': 0.75, 'color': '#a6e3a1'})
        self.p_time.addItem(line_t_raw)
        self.p_time.addItem(line_t_step)

        # ── 2. Histograma de Voltajes ─────────────────────────────────────────
        all_v = v_low_vals + v_high_vals
        min_v, max_v = min(all_v), max(all_v)
        bins_v = np.linspace(min_v, max_v if max_v > min_v else min_v + 1.0, n_bins + 1)
        w_v = (bins_v[1] - bins_v[0]) * 0.42
        counts_low, _  = np.histogram(v_low_vals, bins=bins_v)
        counts_high, _ = np.histogram(v_high_vals, bins=bins_v)
        centers_v = 0.5 * (bins_v[:-1] + bins_v[1:])

        bg_low  = pg.BarGraphItem(x=centers_v - w_v/2, height=counts_low, width=w_v, brush=pg.mkBrush("#f9e2af"), pen=pg.mkPen("#fab387", width=1), name="V_low (V)")
        bg_high = pg.BarGraphItem(x=centers_v + w_v/2, height=counts_high, width=w_v, brush=pg.mkBrush("#f38ba8"), pen=pg.mkPen("#eba0ac", width=1), name="V_high (V)")
        self.p_volt.addItem(bg_low)
        self.p_volt.addItem(bg_high)

        m_v_low, m_v_high = float(np.mean(v_low_vals)), float(np.mean(v_high_vals))
        line_v_low  = pg.InfiniteLine(pos=m_v_low, angle=90, pen=pg.mkPen("#f9e2af", width=2, style=Qt.PenStyle.DashLine), label=f"<V_low>={m_v_low:.2f}V", labelOpts={'position': 0.9, 'color': '#f9e2af'})
        line_v_high = pg.InfiniteLine(pos=m_v_high, angle=90, pen=pg.mkPen("#f38ba8", width=2, style=Qt.PenStyle.DashLine), label=f"<V_high>={m_v_high:.2f}V", labelOpts={'position': 0.75, 'color': '#f38ba8'})
        self.p_volt.addItem(line_v_low)
        self.p_volt.addItem(line_v_high)

        # ── 3. Diagrama de Dispersión t_step vs ΔV ───────────────────────────
        success_t  = [float(r.get("t_step", 0.0)) for r in self.rows if r.get("status") == "SUCCESS"]
        success_dv = [float(r.get("delta_v", 0.0)) for r in self.rows if r.get("status") == "SUCCESS"]
        timeout_t  = [float(r.get("t_step", 0.0)) for r in self.rows if r.get("status") != "SUCCESS"]
        timeout_dv = [float(r.get("delta_v", 0.0)) for r in self.rows if r.get("status") != "SUCCESS"]

        if success_t:
            self.p_scatter.plot(success_t, success_dv, pen=None, symbol='o', symbolSize=10,
                                symbolBrush='#a6e3a1', symbolPen='w', name="Éxito")
        if timeout_t:
            self.p_scatter.plot(timeout_t, timeout_dv, pen=None, symbol='x', symbolSize=12,
                                symbolBrush='#f38ba8', symbolPen='#f38ba8', name="Timeout / Sin Salto")

    def _auto_save_png(self):
        if self.folder and os.path.exists(self.folder):
            png_path = os.path.join(self.folder, "time_volt_distributions.png")
            try:
                pixmap = self.plot_widget.grab()
                pixmap.save(png_path, "PNG")
                print(f"[Time-Volt Tracking] 📊 Histogramas y distribuciones guardados automáticamente en: {png_path}")
            except Exception as e:
                print(f"[Time-Volt Tracking Error] Auto-guardado PNG: {e}")

    def _export_png(self):
        default_path = os.path.join(self.folder, "time_volt_distributions.png") if self.folder and os.path.exists(self.folder) else "time_volt_distributions.png"
        path, _ = QFileDialog.getSaveFileName(self, "Guardar Gráfico de Histogramas Time-Volt", default_path, "PNG Image (*.png)")
        if path:
            pixmap = self.plot_widget.grab()
            pixmap.save(path, "PNG")
            QMessageBox.information(self, "Exportación Exitosa", f"Gráfico Time-Volt guardado en:\n{path}")


# ══════════════════════════════════════════════════════════════════════════════
#  FRONTEND  (compartido por Printing y Dimers — se instancia con mode=)
# ══════════════════════════════════════════════════════════════════════════════

class Frontend(QFrame):
    setreferenceSignal  = pyqtSignal()
    goreferenceSignal   = pyqtSignal()
    resetAllSignal      = pyqtSignal()
    readgridSignal      = pyqtSignal()
    gridcreateSignal    = pyqtSignal(list)
    gridSignal          = pyqtSignal()
    foldergridSignal    = pyqtSignal(str)
    # (color_laser, stopping_mode, params, scanbool, postscanbool)
    parametersSignal    = pyqtSignal(int, int, list, bool, bool)
    pauseSignal         = pyqtSignal()
    next_index_Signal   = pyqtSignal()
    new_index_Signal    = pyqtSignal(int)
    gridinfoSignal      = pyqtSignal(list)

    def __init__(self, mode: str = "printing", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mode = mode
        self._node_results: dict[int, str] = {}
        self._setup_gui()

    def _setup_gui(self):
        label = "Printing" if self.mode == "printing" else "Dimers"
        self.setWindowTitle(label)

        # ── Láser ─────────────────────────────────────────────────────────────
        self.grid_laser = QComboBox()
        self.grid_laser.addItems(SHUTTERS)
        self.grid_laser.setFixedWidth(100)
        self.grid_laser.setToolTip("Línea láser seleccionada para la impresión fototérmica.")
        self.grid_laser.currentIndexChanged.connect(
            lambda: self._color_menu(self.grid_laser))
        self._color_menu(self.grid_laser)

        # ── Presets Experimentales Basados en Archivos .txt ───────────────────
        self.preset_combo = QComboBox()
        self.preset_combo.setToolTip("Carga un perfil pre-configurado almacenado en un archivo de texto plano (.txt).")
        self.preset_combo.currentIndexChanged.connect(self._on_preset_changed)

        self.btn_preset_wizard = QPushButton("🧙 Wizard")
        self.btn_preset_wizard.setToolTip("Abre el Asistente Guiado multipaso para crear y guardar un nuevo preset .txt.")
        self.btn_preset_wizard.clicked.connect(self._on_launch_wizard)

        self.btn_preset_load = QPushButton("📂 Cargar")
        self.btn_preset_load.setToolTip("Abre un archivo de preset .txt externo.")
        self.btn_preset_load.clicked.connect(self._on_load_preset_file)

        self.btn_preset_save = QPushButton("💾 Guardar")
        self.btn_preset_save.setToolTip("Guarda la configuración actual de la interfaz como un nuevo preset .txt.")
        self.btn_preset_save.clicked.connect(self._on_save_preset_file)

        self._refresh_presets_combo()

        # ── Selector de 4 Modos de Criterio de Parada ─────────────────────────
        self.stop_mode_combo = QComboBox()
        self.stop_mode_combo.addItems([
            "Modo 0: Salto Relativo Estándar (I_new / I_old > Umbral)",
            "Modo 1: Salto Relativo + Umbral Absoluto (V) & Anti-Paso",
            "Modo 2: Derivada Temporal Adaptativa (dI/dt -> 0)",
            "Modo 3: Criterio Híbrido Tri-Factor (All-In-One)"
        ])
        self.stop_mode_combo.setToolTip("Algoritmo de criterio de parada en tiempo real (Modos 0 a 3).")
        self.stop_mode_combo.currentIndexChanged.connect(self._on_stopping_mode_changed)

        # ── Parámetros de detección estándar y avanzados ──────────────────────
        self.umbralEdit       = QLineEdit(str(DEFAULT_PRINTING_UMBRAL)); self.umbralEdit.setFixedWidth(55)
        self.umbralEdit.setToolTip("Umbral de salto relativo de la traza para detectar el evento de impresión (ej. 1.20 = 20% de incremento sobre I_old).")
        self.umbral_downEdit  = QLineEdit(str(int(DEFAULT_PRINTING_UMBRAL_DOWN) if DEFAULT_PRINTING_UMBRAL_DOWN.is_integer() else DEFAULT_PRINTING_UMBRAL_DOWN)); self.umbral_downEdit.setFixedWidth(55)
        self.umbral_downEdit.setToolTip("Umbral de caída mínima de la traza para cancelar impresión por blanqueamiento o pérdida de señal.")
        self.tmaxEdit         = QLineEdit(str(int(DEFAULT_PRINTING_TMAX) if DEFAULT_PRINTING_TMAX.is_integer() else DEFAULT_PRINTING_TMAX)); self.tmaxEdit.setFixedWidth(55)
        self.tmaxEdit.setToolTip("Tiempo máximo de espera por nodo en segundos antes de abortar por timeout.")
        self.steps_beforeEdit = QLineEdit(str(DEFAULT_PRINTING_STEPS_BEFORE)); self.steps_beforeEdit.setFixedWidth(44)
        self.steps_beforeEdit.setToolTip("Muestras analógicas adquiridas antes de abrir obturador para calcular la línea base (I_old).")
        self.steps_afterEdit  = QLineEdit(str(DEFAULT_PRINTING_STEPS_AFTER)); self.steps_afterEdit.setFixedWidth(44)
        self.steps_afterEdit.setToolTip("Muestras analógicas adicionales adquiridas tras cerrar el obturador.")

        # Parámetros dinámicos para Modos 1-3
        self.umbral_absEdit   = QLineEdit("2.500"); self.umbral_absEdit.setFixedWidth(55)
        self.umbral_absEdit.setToolTip("Voltaje absoluto en Volts (Modos 1 y 3) necesario para considerar el evento.")
        self.n_holdEdit       = QLineEdit("5");     self.n_holdEdit.setFixedWidth(44)
        self.n_holdEdit.setToolTip("Número de pasos continuos de confirmación (anti-paso) para descartar partículas flotantes de paso.")
        self.slope_minEdit    = QLineEdit("0.000"); self.slope_minEdit.setFixedWidth(55)
        self.slope_minEdit.setToolTip("Umbral Mínimo Absoluto (V). Cualquier lectura I_new por debajo de este valor NO se reconoce en ningún modo.")
        self.slope_flatEdit   = QLineEdit("2.0");   self.slope_flatEdit.setFixedWidth(55)
        self.slope_flatEdit.setToolTip("Pendiente máxima dI/dt (V/s) en la meseta para confirmar la parada del obturador (Modos 2 y 3).")

        self.autofocEdit     = QLineEdit(str(DEFAULT_PRINTING_AUTOFOCUS_EVERY));  self.autofocEdit.setFixedWidth(44)
        self.autofocEdit.setToolTip("Frecuencia de partículas (cada N partículas) entre las cuales se ejecuta el autofoco axial dinámico en Z.")
        self.shiftxEdit      = QLineEdit(str(int(DEFAULT_PRINTING_SHIFT_X) if DEFAULT_PRINTING_SHIFT_X.is_integer() else DEFAULT_PRINTING_SHIFT_X));  self.shiftxEdit.setFixedWidth(44)
        self.shiftxEdit.setToolTip("Desplazamiento X en µm para realizar el autofoco Z en una zona limpia contigua sin perturbar el nodo actual.")
        self.shiftyEdit      = QLineEdit(str(int(DEFAULT_PRINTING_SHIFT_Y) if DEFAULT_PRINTING_SHIFT_Y.is_integer() else DEFAULT_PRINTING_SHIFT_Y));  self.shiftyEdit.setFixedWidth(44)
        self.shiftyEdit.setToolTip("Desplazamiento Y en µm para realizar el autofoco Z en una zona limpia contigua sin perturbar el nodo actual.")

        # ── Scan & Drift Tracking Checks ──────────────────────────────────────
        self.scan_check = QCheckBox("Scan pre-print?")
        self.scan_check.setToolTip("Ejecuta un escaneo confocal de verificación previo a la impresión del nodo.")
        self.scan_check.clicked.connect(self._scan_change)
        self.scan_check.setStyleSheet("color: green;")
        self._scan_change()

        self.track_drift_xy_check = QCheckBox("Track Drift XY?")
        self.track_drift_xy_check.setToolTip("Registra la deriva lateral XY en cada corrección y genera el mapa 2D final.")
        self.track_drift_xy_check.setChecked(True)
        self.track_drift_xy_check.setStyleSheet("color: #89b4fa; font-weight: bold;")

        self.track_drift_z_check = QCheckBox("Track Drift Z?")
        self.track_drift_z_check.setToolTip("Registra la deriva axial Z en cada evento de autofoco y genera la curva temporal final.")
        self.track_drift_z_check.setChecked(True)
        self.track_drift_z_check.setStyleSheet("color: #a6e3a1; font-weight: bold;")

        self.track_time_volt_check = QCheckBox("Track Time-Volt?")
        self.track_time_volt_check.setToolTip("Al finalizar la impresión, ajusta la función salto (V_low, V_high, t_step) en todas las trazas y genera reporte_parametros_*.txt.")
        self.track_time_volt_check.setChecked(True)
        self.track_time_volt_check.setStyleSheet("color: #f9e2af; font-weight: bold;")

        # ── Post-scan (solo dimers) ────────────────────────────────────────────
        self.postscan_check = QCheckBox("Post scan?")
        self.postscan_check.setToolTip("Ejecuta un escaneo confocal posterior para confirmar la formación del dímero.")
        self.postscan_check.setVisible(self.mode == "dimers")

        # ── dx/dy (solo dimers) ───────────────────────────────────────────────
        self.dxEdit = QLineEdit(str(int(DEFAULT_DIMERS_DX) if DEFAULT_DIMERS_DX.is_integer() else DEFAULT_DIMERS_DX)); self.dxEdit.setFixedWidth(44)
        self.dxEdit.setToolTip("Desplazamiento X (µm) para la colocación de la segunda nanopartícula en el dímero.")
        self.dyEdit = QLineEdit(str(int(DEFAULT_DIMERS_DY) if DEFAULT_DIMERS_DY.is_integer() else DEFAULT_DIMERS_DY)); self.dyEdit.setFixedWidth(44)
        self.dyEdit.setToolTip("Desplazamiento Y (µm) para la colocación de la segunda nanopartícula en el dímero.")

        # ── Nombre de Lote Personalizado y Botones de control ──────────────────
        self.custom_name_edit = QLineEdit("")
        self.custom_name_edit.setPlaceholderText("Nombre lote (ej: AuNP_60nm)")
        self.custom_name_edit.setToolTip("Nombre personalizado para la subcarpeta del lote y reportes. Si está vacío, se usará el nombre por defecto de la grilla.")

        self.imprimir_button = QPushButton(f"{label} folder")
        self.imprimir_button.setToolTip("Crea la subcarpeta del lote experimental fechada YYYYMMDD-HHMMSS_Printing_<GridName> en la carpeta diaria.")
        self.imprimir_button.clicked.connect(self._get_create_folder)
        self.imprimir_button.setStyleSheet("QPushButton:pressed { background-color: blue; }")

        self.play_button  = QPushButton("Play ►")
        self.play_button.setToolTip("Inicia la rutina automatizada de impresión nodo a nodo.")
        self.play_button.clicked.connect(self._get_grid_measurement)

        self.pause_button = QPushButton("Pause")
        self.pause_button.setToolTip("Pausa la impresión y cierra los obturadores inmediatamente.")
        self.pause_button.clicked.connect(lambda: self.pauseSignal.emit())

        self.next_button  = QPushButton("Next index ►")
        self.next_button.setToolTip("Salta inmediatamente el nodo actual y avanza a la siguiente partícula.")
        self.next_button.clicked.connect(lambda: self.next_index_Signal.emit())

        self.go_ref_button  = QPushButton("Go reference")
        self.go_ref_button.setToolTip("Desplaza la platina PI inmediatamente al punto de referencia de origen (X0, Y0, Z0).")
        self.go_ref_button.clicked.connect(lambda: self.goreferenceSignal.emit())
        self.go_ref_button.setFixedWidth(90)

        self.set_ref_button = QPushButton("Set reference")
        self.set_ref_button.setToolTip("Congela la posición actual de los sensores capacitivos de la platina PI como origen (X0, Y0, Z0).")
        self.set_ref_button.clicked.connect(lambda: self.setreferenceSignal.emit())
        self.set_ref_button.setStyleSheet(
            "QPushButton { background-color: orange; }"
            "QPushButton:pressed { background-color: blue; }")

        self.btn_reset_all = QPushButton("Reset all 🔄")
        self.btn_reset_all.setToolTip("Restablece todas las variables de Printing, referencias, acumuladores de deriva y estados a cero.")
        self.btn_reset_all.clicked.connect(lambda: self.resetAllSignal.emit())
        self.btn_reset_all.setStyleSheet(
            "QPushButton { background-color: #3b4252; color: #eceff4; font-weight: bold; border: 1px solid #4c566a; border-radius: 4px; }"
            "QPushButton:hover { background-color: #bf616a; color: white; }"
            "QPushButton:pressed { background-color: #882d38; }"
        )

        # ── Contadores ────────────────────────────────────────────────────────
        self.NameDirValue      = QLabel("")
        self.NameDirValue.setStyleSheet("background-color: red;")
        self.particulasEdit    = QLabel("0")
        self.particulasEdit.setStyleSheet("font-family: monospace; font-weight: bold; color: #cdd6f4;")
        self.time_remaining_label = QLabel("—")
        self.time_remaining_label.setStyleSheet("color: #89dceb; font-family: monospace; font-weight: bold;")
        self.time_remaining_label.setToolTip("Tiempo estimado restante para finalizar el lote (calculado con el promedio de t_raw y N restante; 15s inicial).")
        self.indice_impresionEdit = QLineEdit("0")
        self.indice_impresionEdit.setToolTip("Índice del nodo actual en proceso de impresión.")
        self.indice_impresionEdit.textChanged.connect(self._new_index_target)

        # ── Referencia ────────────────────────────────────────────────────────
        self.xrefLabel = QLabel("NaN")
        self.yrefLabel = QLabel("NaN")
        self.zrefLabel = QLabel("NaN")

        # ── Crear grilla ──────────────────────────────────────────────────────
        self.number_files    = QLineEdit(str(DEFAULT_GRID_NPS_COL))
        self.number_files.setToolTip("Número de nanopartículas a imprimir por cada columna.")
        self.number_columns  = QLineEdit(str(DEFAULT_GRID_COLS))
        self.number_columns.setToolTip("Número de columnas de la grilla.")
        self.distance_files  = QLineEdit(str(int(DEFAULT_GRID_DIST_NP) if DEFAULT_GRID_DIST_NP.is_integer() else DEFAULT_GRID_DIST_NP))
        self.distance_files.setToolTip("Espaciamiento espacial entre nanopartículas contiguas en la columna (µm).")
        self.distance_columns= QLineEdit(str(int(DEFAULT_GRID_DIST_COL) if DEFAULT_GRID_DIST_COL.is_integer() else DEFAULT_GRID_DIST_COL))
        self.distance_columns.setToolTip("Espaciamiento espacial entre columnas contiguas (µm).")

        self.grid_create_button = QPushButton("Create grid")
        self.grid_create_button.setToolTip("Genera la grilla regular de posiciones (X, Y) con las dimensiones especificadas.")
        self.grid_create_button.clicked.connect(self._get_grid_create)
        self.grid_create_button.setStyleSheet(
            "QPushButton { background-color: orange; }"
            "QPushButton:pressed { background-color: blue; }")

        self.cargar_archivo_button = QPushButton("Load grid (.txt)")
        self.cargar_archivo_button.setToolTip("Carga una grilla personalizada de posiciones desde un archivo .txt.")
        self.cargar_archivo_button.clicked.connect(lambda: self.readgridSignal.emit())
        self.cargar_archivo_button.setStyleSheet(
            "QPushButton { background-color: orange; }"
            "QPushButton:pressed { background-color: blue; }")

        self.btn_open_grid_generator = QPushButton("📐 Diseñador 2D")
        self.btn_open_grid_generator.setToolTip("Abre el Diseñador Universal de Redes Cristalinas 2D (Bravais, Moiré, figuras y recetas multi-paso con P0).")
        self.btn_open_grid_generator.clicked.connect(self._open_grid_generator)
        self.btn_open_grid_generator.setStyleSheet(
            "QPushButton { background-color: #313244; color: #cba6f7; font-weight: bold; border: 1px solid #45475a; border-radius: 4px; }"
            "QPushButton:hover { background-color: #45475a; color: white; }"
            "QPushButton:pressed { background-color: #585b70; }"
        )

        # ── Info extra ────────────────────────────────────────────────────────
        self.powerlaser  = QLineEdit("—"); self.powerlaser.setToolTip("Potencia medida en la pupila trasera del objetivo (BFP en mW).")
        self.typeNP      = QLineEdit("—"); self.typeNP.setToolTip("Tipo y tamaño de la solución coloidal de nanopartículas (ej. AuNP 60 nm).")
        self.substrate   = QLineEdit("—"); self.substrate.setToolTip("Sustrato y funcionalización (ej. vidrio + PDDA + PSS).")
        self.NPevents    = QLineEdit("—"); self.NPevents.setToolTip("Eventos de impresión detectados / total (%).")
        self.NPevents.setStyleSheet("font-family: monospace; font-weight: bold; color: #89b4fa;")
        self.NPsuccess   = QLineEdit("—"); self.NPsuccess.setToolTip("Porcentaje de éxito confirmado en la formación de la grilla (%).")
        self.NPsuccess.setStyleSheet("font-family: monospace; font-weight: bold; color: #a6e3a1;")
        self.drift_xy_edit = QLineEdit("(+0.0, +0.0) nm | r=0.0 nm")
        self.drift_xy_edit.setReadOnly(True)
        self.drift_xy_edit.setStyleSheet("font-family: monospace; font-weight: bold; color: #4a9eff;")
        self.drift_xy_edit.setToolTip("Desplazamiento lateral acumulado (Δx, Δy) nm corregido por Drift Correction.")
        self.disp_acumuladoEdit = self.drift_xy_edit  # Alias por compatibilidad

        self.drift_z_edit = QLineEdit("+0.0 nm")
        self.drift_z_edit.setReadOnly(True)
        self.drift_z_edit.setStyleSheet("font-family: monospace; font-weight: bold; color: #a6e3a1;")
        self.drift_z_edit.setToolTip("Desplazamiento axial acumulado Δz nm corregido por Autofoco Z respecto al origen (Z0).")

        self.extra_info  = QLineEdit("—"); self.extra_info.setToolTip("Comentarios experimentales adicionales.")
        self.grid_save_info_button = QPushButton("Save info")
        self.grid_save_info_button.setToolTip("Guarda el archivo grid_info.txt en la carpeta del lote experimental.")
        self.grid_save_info_button.clicked.connect(self._get_grid_info)

        # ── Layout principal ──────────────────────────────────────────────────
        hbox      = QHBoxLayout(self)
        dock_area = DockArea()

        # Reference widget
        refW = QWidget(); rlo = QGridLayout(refW)
        rlo.addWidget(QLabel("X ref:"),    0, 0); rlo.addWidget(self.xrefLabel, 0, 1)
        rlo.addWidget(QLabel("Y ref:"),    1, 0); rlo.addWidget(self.yrefLabel, 1, 1)
        rlo.addWidget(QLabel("Z ref:"),    2, 0); rlo.addWidget(self.zrefLabel, 2, 1)
        rlo.addWidget(self.set_ref_button, 3, 0, 1, 2)
        rlo.addWidget(self.go_ref_button,  4, 0)
        rlo.addWidget(self.btn_reset_all,  4, 1)

        # Grid create widget
        gcW = QWidget(); glo = QGridLayout(gcW)
        glo.addWidget(QLabel("NPs/col"),        0, 0); glo.addWidget(self.number_files,    0, 1)
        glo.addWidget(QLabel("Columns"),         1, 0); glo.addWidget(self.number_columns,  1, 1)
        glo.addWidget(QLabel("Dist NP (µm)"),   2, 0); glo.addWidget(self.distance_files,  2, 1)
        glo.addWidget(QLabel("Dist col (µm)"),  3, 0); glo.addWidget(self.distance_columns,3, 1)
        glo.addWidget(self.grid_create_button,  4, 0, 1, 2)
        glo.addWidget(self.cargar_archivo_button,5,0, 1, 2)
        glo.addWidget(self.btn_open_grid_generator, 6, 0, 1, 2)

        # Print control widget (Multi-column layout expandido)
        pcW = QWidget(); plo = QGridLayout(pcW)
        plo.setContentsMargins(6, 6, 6, 6)
        plo.setHorizontalSpacing(10)
        plo.setVerticalSpacing(4)

        # Fila 0: Botón de directorio + Nombre de lote personalizado + Nombre de ruta
        plo.addWidget(self.imprimir_button,    0, 0)
        plo.addWidget(self.custom_name_edit,   0, 1)
        plo.addWidget(self.NameDirValue,       0, 2, 1, 2)

        # Fila 1: Presets (.txt) y Botones de Wizard / Cargar / Guardar
        plo.addWidget(QLabel("Preset (.txt):"), 1, 0)
        plo.addWidget(self.preset_combo,        1, 1)

        preset_btns_hlo = QHBoxLayout()
        preset_btns_hlo.setContentsMargins(0, 0, 0, 0)
        preset_btns_hlo.setSpacing(4)
        preset_btns_hlo.addWidget(self.btn_preset_wizard)
        preset_btns_hlo.addWidget(self.btn_preset_load)
        preset_btns_hlo.addWidget(self.btn_preset_save)
        plo.addLayout(preset_btns_hlo, 1, 2, 1, 2)

        # Fila 2: Selector de Criterio de Parada
        plo.addWidget(QLabel("Criterio Parada:"), 2, 0)
        plo.addWidget(self.stop_mode_combo,       2, 1, 1, 3)

        # Fila 3: Láser | Umbral Relativo
        plo.addWidget(QLabel("Láser:"),        3, 0); plo.addWidget(self.grid_laser,       3, 1)
        self.lbl_umbral_rel = QLabel("Umbral rel:"); plo.addWidget(self.lbl_umbral_rel, 3, 2); plo.addWidget(self.umbralEdit, 3, 3)

        # Fila 4: Umbral Absoluto (V) | N hold steps
        self.lbl_umbral_abs = QLabel("Umbral Abs (V):"); plo.addWidget(self.lbl_umbral_abs, 4, 0); plo.addWidget(self.umbral_absEdit, 4, 1)
        self.lbl_n_hold     = QLabel("N hold steps:");  plo.addWidget(self.lbl_n_hold,     4, 2); plo.addWidget(self.n_holdEdit,     4, 3)

        # Fila 5: Umbral Mín (V) | Slope Flat (V/s)
        self.lbl_umbral_min = QLabel("Umbral Mín (V):"); plo.addWidget(self.lbl_umbral_min, 5, 0); plo.addWidget(self.slope_minEdit,  5, 1)
        self.lbl_slope_flat = QLabel("Slope Flat:");    plo.addWidget(self.lbl_slope_flat, 5, 2); plo.addWidget(self.slope_flatEdit, 5, 3)

        # Fila 6: Umbral down | T max (s)
        plo.addWidget(QLabel("Umbral down:"),  6, 0); plo.addWidget(self.umbral_downEdit,   6, 1)
        plo.addWidget(QLabel("T max (s):"),    6, 2); plo.addWidget(self.tmaxEdit,          6, 3)

        # Fila 7: Steps before | Steps after
        self.lbl_steps_before = QLabel("Steps before:"); plo.addWidget(self.lbl_steps_before, 7, 0); plo.addWidget(self.steps_beforeEdit, 7, 1)
        self.lbl_steps_after  = QLabel("Steps after:");  plo.addWidget(self.lbl_steps_after,  7, 2); plo.addWidget(self.steps_afterEdit,  7, 3)

        # Fila 8: Scan pre-print | Track Drift XY | Track Drift Z | Track Time-Volt
        plo.addWidget(self.scan_check,            8, 0)
        plo.addWidget(self.track_drift_xy_check,  8, 1)
        plo.addWidget(self.track_drift_z_check,   8, 2)
        plo.addWidget(self.track_time_volt_check, 8, 3)
        if self.mode == "dimers":
            plo.addWidget(self.postscan_check,    9, 3)

        # Fila 9: Controles de reproducción Play / Pause / Next Index
        plo.addWidget(self.play_button,        9, 0); plo.addWidget(self.pause_button,      9, 1)
        plo.addWidget(self.next_button,        9, 2, 1, 1 if self.mode == "dimers" else 2)

        # Fila 10: Checkbox de Autocompletitud Inteligente (Healing Pass)
        self.auto_complete_check = QCheckBox("🔄 Autocompletitud de redes (Healing Pass)")
        self.auto_complete_check.setChecked(False)
        self.auto_complete_check.setStyleSheet("color: #fab387; font-weight: bold;")
        self.auto_complete_check.setToolTip("Al finalizar la grilla, reintenta automáticamente los nodos con TIMEOUT ejecutando autofoco in-situ y tiempo extendido (+10s).")
        plo.addWidget(self.auto_complete_check, 10, 0, 1, 4)

        # Fila 11: Total targets | Time Remaining (ETA)
        plo.addWidget(QLabel("Total targets:"), 11, 0); plo.addWidget(self.particulasEdit,        11, 1)
        plo.addWidget(QLabel("Time Rem ⏱️:"),   11, 2); plo.addWidget(self.time_remaining_label, 11, 3)

        # Fila 12: Target Index | Barra de progreso de avance
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(18)
        self.progress_bar.setStyleSheet(
            "QProgressBar { text-align: center; border: 1px solid #45475a; border-radius: 4px; background-color: #1e1e2e; color: #cdd6f4; font-size: 8pt; }"
            "QProgressBar::chunk { background-color: #a6e3a1; }"
        )
        plo.addWidget(QLabel("Target Index:"),  12, 0); plo.addWidget(self.indice_impresionEdit, 12, 1)
        plo.addWidget(QLabel("Progreso Lote:"), 12, 2); plo.addWidget(self.progress_bar,        12, 3)

        # Focus shift & Drift correction widget
        fsW = QWidget(); flo = QGridLayout(fsW)
        flo.addWidget(QLabel("Autofocus every N"), 0, 0); flo.addWidget(self.autofocEdit, 0, 1)
        flo.addWidget(QLabel("Shift x (µm)"),      1, 0); flo.addWidget(self.shiftxEdit,  1, 1)
        flo.addWidget(QLabel("Shift y (µm)"),      2, 0); flo.addWidget(self.shiftyEdit,  2, 1)
        if self.mode == "dimers":
            flo.addWidget(QLabel("dx (µm)"), 3, 0); flo.addWidget(self.dxEdit, 3, 1)
            flo.addWidget(QLabel("dy (µm)"), 4, 0); flo.addWidget(self.dyEdit, 4, 1)

        # Drift correction controls
        self.drift_check = QCheckBox("Drift Correction (P0)?")
        self.drift_check.setToolTip("Realiza un escaneo confocal 2x2 µm en la Partícula 0 post-autofoco Z para corregir derivas X-Y acumuladas.")
        self.startxEdit = QLineEdit("2.0"); self.startxEdit.setFixedWidth(44)
        self.startxEdit.setToolTip("Offset X de inicio del arreglo de impresión respecto a la Partícula 0 (µm).")
        self.startyEdit = QLineEdit("2.0"); self.startyEdit.setFixedWidth(44)
        self.startyEdit.setToolTip("Offset Y de inicio del arreglo de impresión respecto a la Partícula 0 (µm).")

        self.adaptive_af_check = QCheckBox("Adaptive AF? 🧠")
        self.adaptive_af_check.setChecked(True)
        self.adaptive_af_check.setStyleSheet("color: #cba6f7; font-weight: bold;")
        self.adaptive_af_check.setToolTip("Sintoniza dinámicamente el intervalo de autofoco y corrección de deriva según la velocidad de deriva medida (nm/s).")
        self.drift_tol_edit = QLineEdit("25.0"); self.drift_tol_edit.setFixedWidth(44)
        self.drift_tol_edit.setToolTip("Tolerancia espacial máxima de deriva permitida (nm) antes de forzar un ciclo de foco/deriva.")
        self.v_drift_label = QLabel("v: — | N_eff: 5")
        self.v_drift_label.setStyleSheet("color: #89dceb; font-family: monospace; font-size: 8pt;")
        self.v_drift_label.setToolTip("Velocidad instantánea de deriva estimada y número efectivo actual de partículas entre autofocos.")

        r_offset = 5 if self.mode == "dimers" else 3
        flo.addWidget(self.drift_check,        r_offset,   0, 1, 2)
        flo.addWidget(QLabel("Start X (µm)"),  r_offset+1, 0); flo.addWidget(self.startxEdit, r_offset+1, 1)
        flo.addWidget(QLabel("Start Y (µm)"),  r_offset+2, 0); flo.addWidget(self.startyEdit, r_offset+2, 1)
        flo.addWidget(self.adaptive_af_check,  r_offset+3, 0, 1, 2)
        flo.addWidget(QLabel("Drift Tol (nm)"),r_offset+4, 0); flo.addWidget(self.drift_tol_edit, r_offset+4, 1)
        flo.addWidget(self.v_drift_label,      r_offset+5, 0, 1, 2)

        # Extra info widget
        eiW = QWidget(); elo = QGridLayout(eiW)
        ei_rows = [("Power BFP (mW)", self.powerlaser),
                   ("NP type",        self.typeNP),
                   ("Substrate",      self.substrate),
                   ("NP events",      self.NPevents),
                   ("NP success",     self.NPsuccess),
                   ("Drift XY",       self.drift_xy_edit),
                   ("Drift Z",        self.drift_z_edit),
                   ("Comments",       self.extra_info)]
        for r, (lbl, w) in enumerate(ei_rows):
            elo.addWidget(QLabel(lbl), r, 0); elo.addWidget(w, r, 1)
        elo.addWidget(self.grid_save_info_button, len(ei_rows), 0, 1, 2)

        # Interactive Grid Widget
        self.interactive_grid = InteractiveGridWidget()
        self.interactive_grid.nodeClickedSignal.connect(self._on_grid_node_clicked)

        # ── Disposición de Docks Unificada (2 Columna Limpias sin Duplicados) ──────
        # 1. Columna Derecha Global (Ocupa toda la altura de la ventana a la derecha)
        gridViewerDock = Dock(f"{label} Pattern & Path Viewer 🗺️", size=(560, 600))
        gridViewerDock.addWidget(self.interactive_grid)
        dock_area.addDock(gridViewerDock, "right")

        # 2. Columna Izquierda Arriba: Printing Control Panel
        pcDock = Dock(f"{label} Control Panel 🎛️", size=(680, 360))
        pcDock.addWidget(pcW)
        dock_area.addDock(pcDock, "left", gridViewerDock)

        # 3. Columna Izquierda Abajo: Reference, Grid, Focus & Drift, Extra Info
        refDock = Dock("Reference pos", size=(160, 160))
        refDock.addWidget(refW)
        dock_area.addDock(refDock, "bottom", pcDock)

        gcDock = Dock("Grid", size=(160, 160))
        gcDock.addWidget(gcW)
        dock_area.addDock(gcDock, "right", refDock)

        fsDock = Dock("Focus shift & Drift", size=(180, 160))
        fsDock.addWidget(fsW)
        dock_area.addDock(fsDock, "right", gcDock)

        eiDock = Dock("Extra info", size=(180, 160))
        eiDock.addWidget(eiW)
        dock_area.addDock(eiDock, "right", fsDock)

        hbox.addWidget(dock_area)

        # Inicializar visibilidad dinámica de casilleros según Modo 0 por defecto
        self._on_stopping_mode_changed(0)

    def _open_grid_generator(self):
        if not hasattr(self, "_gridGenWindow") or self._gridGenWindow is None:
            from grid_generator import GridGeneratorWindow
            self._gridGenWindow = GridGeneratorWindow(self)
        self._gridGenWindow.show()
        self._gridGenWindow.raise_()
        self._gridGenWindow.activateWindow()

    def _on_grid_node_clicked(self, idx: int):
        self.indice_impresionEdit.setText(str(idx))
        self.new_index_Signal.emit(idx)

    def _refresh_presets_combo(self):
        from core.preset_manager import PresetManager
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        self._preset_list = PresetManager.get_available_presets()

        self.preset_combo.addItem("Preset: Personalizado / Libre", None)
        for p in self._preset_list:
            self.preset_combo.addItem(f"📄 {p.get('name', 'Sin nombre')}", p)
        self.preset_combo.blockSignals(False)

    def _on_preset_changed(self, idx: int):
        data = self.preset_combo.itemData(idx)
        if not data:
            return

        if "stop_mode" in data:
            try: self.stop_mode_combo.setCurrentIndex(int(data["stop_mode"]))
            except ValueError: pass
        if "umbral_rel" in data: self.umbralEdit.setText(data["umbral_rel"])
        if "umbral_abs" in data: self.umbral_absEdit.setText(data["umbral_abs"])
        if "umbral_min" in data: self.slope_minEdit.setText(data["umbral_min"])
        if "umbral_down" in data: self.umbral_downEdit.setText(data["umbral_down"])
        if "slope_flat" in data: self.slope_flatEdit.setText(data["slope_flat"])
        if "tmax" in data: self.tmaxEdit.setText(data["tmax"])
        if "n_hold" in data: self.n_holdEdit.setText(data["n_hold"])
        if "steps_before" in data: self.steps_beforeEdit.setText(data["steps_before"])
        if "steps_after" in data: self.steps_afterEdit.setText(data["steps_after"])
        if "autofocus_every" in data: self.autofocEdit.setText(data["autofocus_every"])
        if "shift_x" in data: self.shiftxEdit.setText(data["shift_x"])
        if "shift_y" in data: self.shiftyEdit.setText(data["shift_y"])
        if "dx" in data: self.dxEdit.setText(data["dx"])
        if "dy" in data: self.dyEdit.setText(data["dy"])
        if "scan_preprint" in data: self.scan_check.setChecked(data["scan_preprint"].lower() == "true")
        if "postscan" in data and hasattr(self, 'postscan_check'):
            self.postscan_check.setChecked(data["postscan"].lower() == "true")
        if "drift_correction" in data: self.drift_check.setChecked(data["drift_correction"].lower() == "true")

    def _on_launch_wizard(self):
        from modules.preset_wizard import PresetWizardDialog
        dlg = PresetWizardDialog(self)
        if dlg.exec():
            self._refresh_presets_combo()
            if dlg.created_preset_path:
                for i in range(self.preset_combo.count()):
                    item_data = self.preset_combo.itemData(i)
                    if item_data and item_data.get("_filepath") == dlg.created_preset_path:
                        self.preset_combo.setCurrentIndex(i)
                        break

    def _on_load_preset_file(self):
        from core.preset_manager import PresetManager, PRESETS_DIR
        path, _ = QFileDialog.getOpenFileName(self, "Cargar Archivo Preset .txt", PRESETS_DIR, "Archivos Preset (*.txt)")
        if path:
            pdata = PresetManager.load_preset_file(path)
            pdata["_filepath"] = path
            self.preset_combo.addItem(f"📂 {pdata.get('name', 'Custom')}", pdata)
            self.preset_combo.setCurrentIndex(self.preset_combo.count() - 1)

    def _on_save_preset_file(self):
        from core.preset_manager import PresetManager, PRESETS_DIR
        name, ok = QInputDialog.getText(self, "Guardar Preset .txt", "Nombre del Preset:")
        if ok and name:
            fname = name.replace(" ", "_").replace("—", "_") + ".txt"
            fpath = os.path.join(PRESETS_DIR, fname)
            data = {
                "name": name,
                "description": "Preset guardado manualmente desde la interfaz de PyPrinting",
                "stop_mode": str(self.stop_mode_combo.currentIndex()),
                "umbral_rel": self.umbralEdit.text(),
                "umbral_abs": self.umbral_absEdit.text(),
                "umbral_min": self.slope_minEdit.text(),
                "umbral_down": self.umbral_downEdit.text(),
                "slope_flat": self.slope_flatEdit.text(),
                "tmax": self.tmaxEdit.text(),
                "n_hold": self.n_holdEdit.text(),
                "steps_before": self.steps_beforeEdit.text(),
                "steps_after": self.steps_afterEdit.text(),
                "autofocus_every": self.autofocEdit.text(),
                "shift_x": self.shiftxEdit.text(),
                "shift_y": self.shiftyEdit.text(),
                "dx": self.dxEdit.text(),
                "dy": self.dyEdit.text(),
                "scan_preprint": str(self.scan_check.isChecked()),
                "postscan": str(self.postscan_check.isChecked() if hasattr(self, 'postscan_check') else False),
                "drift_correction": str(self.drift_check.isChecked())
            }
            saved_path = PresetManager.save_preset_file(fpath, data)
            self._refresh_presets_combo()
            QMessageBox.information(self, "Preset Guardado", f"¡Preset .txt guardado exitosamente en:\n{saved_path}")

    def _on_stopping_mode_changed(self, idx: int):
        """Muestra u oculta los casilleros de la interfaz según el Modo de Parada seleccionado (0 a 3)."""
        # Modo 0: Salto Relativo Estándar
        # Modo 1: Salto Relativo + Umbral Absoluto (V) & Anti-Paso
        # Modo 2: Derivada Temporal Adaptativa (dI/dt -> 0)
        # Modo 3: Criterio Híbrido Tri-Factor (All-In-One)
        show_rel     = idx in (0, 1, 3)
        show_abs     = idx in (1, 3)
        show_hold    = idx in (1, 2, 3)
        show_slope   = idx in (2, 3)

        self.lbl_umbral_rel.setVisible(show_rel);      self.umbralEdit.setVisible(show_rel)
        self.lbl_umbral_abs.setVisible(show_abs);      self.umbral_absEdit.setVisible(show_abs)
        self.lbl_n_hold.setVisible(show_hold);         self.n_holdEdit.setVisible(show_hold)
        self.lbl_umbral_min.setVisible(True);          self.slope_minEdit.setVisible(True)  # SIEMPRE VISIBLE EN TODOS LOS MODOS
        self.lbl_slope_flat.setVisible(show_slope);    self.slope_flatEdit.setVisible(show_slope)

    def _color_menu(self, combo: QComboBox):
        colors = ["#2e7d32", "#c62828", "#f57f17", "#880e4f"] # verde, rojo, amarillo, infrarrojo (808nm)
        idx = combo.currentIndex()
        c = colors[idx] if idx < len(colors) else "#ffffff"
        combo.setStyleSheet(f"background-color: {c}; color: white; font-weight: bold;")

    def _scan_change(self):
        v = self.scan_check.isChecked()
        self.scan_check.setText("Scan pre-print? (ON)" if v else "Scan pre-print? (OFF)")

    def _new_index_target(self, text: str):
        try: self.new_index_Signal.emit(int(text))
        except ValueError: pass

    def _get_create_folder(self):
        self.foldergridSignal.emit(self.custom_name_edit.text().strip())

    def _get_grid_create(self):
        try:
            start_x = float(self.startxEdit.text() or 2.0)
            start_y = float(self.startyEdit.text() or 2.0)
            drift_bool = self.drift_check.isChecked()
            grid = [int(self.number_files.text()),
                    int(self.number_columns.text()),
                    float(self.distance_files.text()),
                    float(self.distance_columns.text()),
                    start_x,
                    start_y,
                    drift_bool]
            self.gridcreateSignal.emit(grid)
        except ValueError: pass

    def _get_grid_measurement(self):
        self._emit_parameters()
        self.gridSignal.emit()

    def _emit_parameters(self):
        color = self.grid_laser.currentIndex()
        stop_mode = self.stop_mode_combo.currentIndex()
        params = [
            float(self.umbralEdit.text() or DEFAULT_PRINTING_UMBRAL),
            float(self.umbral_downEdit.text() or DEFAULT_PRINTING_UMBRAL_DOWN),
            float(self.tmaxEdit.text() or DEFAULT_PRINTING_TMAX),
            float(self.autofocEdit.text() or DEFAULT_PRINTING_AUTOFOCUS_EVERY),
            float(self.shiftxEdit.text() or 0.0),
            float(self.shiftyEdit.text() or 0.0),
            float(self.dxEdit.text() or 0.0),
            float(self.dyEdit.text() or 0.0),
            int(self.steps_beforeEdit.text() or DEFAULT_PRINTING_STEPS_BEFORE),
            int(self.steps_afterEdit.text() or DEFAULT_PRINTING_STEPS_AFTER),
            float(self.umbral_absEdit.text() or 2.5),
            int(self.n_holdEdit.text() or 5),
            float(self.slope_minEdit.text() or 0.0),
            float(self.slope_flatEdit.text() or 2.0),
            float(self.ratio_kEdit.text() if hasattr(self, 'ratio_kEdit') else 10.0),
            float(self.percent_threshEdit.text() if hasattr(self, 'percent_threshEdit') else 50.0),
            float(self.startxEdit.text() or 2.0),
            float(self.startyEdit.text() or 2.0),
            self.drift_check.isChecked(),
            self.track_drift_xy_check.isChecked(),
            self.track_drift_z_check.isChecked(),
            self.track_time_volt_check.isChecked(),
            self.custom_name_edit.text().strip(),
            self.adaptive_af_check.isChecked(),
            float(self.drift_tol_edit.text() or 25.0),
            self.auto_complete_check.isChecked()
        ]
        scanbool     = self.scan_check.isChecked()
        postscanbool = self.postscan_check.isChecked() if self.mode == "dimers" else False
        self.parametersSignal.emit(color, stop_mode, params, scanbool, postscanbool)

    def _get_grid_info(self):
        info = [["Laser:", self.grid_laser.currentText()],
                ["Criterio Parada:", self.stop_mode_combo.currentText()],
                ["Umbral:", self.umbralEdit.text()],
                ["Umbral Absoluto:", self.umbral_absEdit.text()],
                ["Power BFP:", self.powerlaser.text()],
                ["NP type:", self.typeNP.text()],
                ["Substrate:", self.substrate.text()],
                ["NP events:", self.NPevents.text()],
                ["NP success:", self.NPsuccess.text()],
                ["Custom Name:", self.custom_name_edit.text().strip() or "Auto"],
                ["Drift XY:", self.drift_xy_edit.text()],
                ["Drift Z:", self.drift_z_edit.text()],
                ["Drift Velocity (v):", self.v_drift_label.text()],
                ["Adaptive AF:", "ON" if self.adaptive_af_check.isChecked() else "OFF"],
                ["Drift Tolerance (nm):", self.drift_tol_edit.text()],
                ["Track Drift XY:", "ON" if self.track_drift_xy_check.isChecked() else "OFF"],
                ["Track Drift Z:", "ON" if self.track_drift_z_check.isChecked() else "OFF"],
                ["Track Time-Volt:", "ON" if self.track_time_volt_check.isChecked() else "OFF"],
                ["Auto-Complete (Healing):", "ON" if self.auto_complete_check.isChecked() else "OFF"],
                ["Time Remaining (ETA):", self.time_remaining_label.text()],
                ["Comments:", self.extra_info.text()]]
        self.gridinfoSignal.emit(info)

    @pyqtSlot(list)
    def reference_label(self, ref: list):
        self.xrefLabel.setText(str(ref[0]))
        self.yrefLabel.setText(str(ref[1]))
        self.zrefLabel.setText(str(ref[2]))
        self.set_ref_button.setStyleSheet("QPushButton { background-color: #2e7d32; color: white; font-weight: bold; }")

    @pyqtSlot(int)
    def particulas_edit(self, n: int):
        self.particulasEdit.setText(str(n))
        if n > 0:
            init_eta_s = n * 15.0
            mins = int(init_eta_s // 60)
            secs = int(init_eta_s % 60)
            eta_str = f"{mins:02d}m {secs:02d}s" if mins > 0 else f"{secs:02d}s"
            self.time_remaining_label.setText(f"~{eta_str}")
        else:
            self.time_remaining_label.setText("—")

    @pyqtSlot(str)
    def name_folder(self, folder: str): self.NameDirValue.setText(folder); self.NameDirValue.setStyleSheet("background-color: green;")
    @pyqtSlot(int)
    def index_target(self, i: int):
        self.indice_impresionEdit.setText(str(i))
        self.interactive_grid.set_node_status(i, "active")
        if self.interactive_grid.grid_coords is not None:
            total = self.interactive_grid.grid_coords.shape[1]
            if total > 0:
                self.progress_bar.setValue(int(min(100, (i / total) * 100)))

    @pyqtSlot(int, str)
    def node_status_update(self, i: int, status: str):
        self.interactive_grid.set_node_status(i, status)
        self._node_results[i] = status

        total_targets = 0
        if self.interactive_grid.grid_coords is not None:
            total_targets = self.interactive_grid.grid_coords.shape[1]
        elif self.particulasEdit.text().isdigit():
            total_targets = int(self.particulasEdit.text())
        else:
            total_targets = len(self._node_results)

        events_count = sum(1 for s in self._node_results.values() if s in ("success", "printed"))
        if total_targets > 0:
            events_pct = (events_count / total_targets) * 100.0
            self.NPevents.setText(f"{events_count}/{total_targets} ({events_pct:.1f}%)")
            self.NPsuccess.setText(f"{events_count}/{total_targets} ({events_pct:.1f}%)")

    @pyqtSlot(np.ndarray)
    def grid_plot(self, datos: np.ndarray):
        self.interactive_grid.set_grid(datos)

    @pyqtSlot(dict)
    def _show_drift_tracking_dialog(self, data: dict):
        if not data.get("xy") and not data.get("z"):
            return
        self._drift_dialog = DriftTrackingDialog(data, parent=self)
        self._drift_dialog.show()

    @pyqtSlot()
    def on_reset_frontend(self):
        self._node_results.clear()
        self.NPevents.setText("—")
        self.NPsuccess.setText("—")
        self.custom_name_edit.setText("")
        self.xrefLabel.setText("NaN")
        self.yrefLabel.setText("NaN")
        self.zrefLabel.setText("NaN")
        self.set_ref_button.setStyleSheet("QPushButton { background-color: orange; } QPushButton:pressed { background-color: blue; }")
        self.indice_impresionEdit.setText("0")
        self.drift_xy_edit.setText("(+0.0, +0.0) nm | r=0.0 nm")
        self.drift_z_edit.setText("+0.0 nm")
        self.v_drift_label.setText("v: — | N_eff: 5")
        self.drift_tol_edit.setText("25.0")
        self.time_remaining_label.setText("—")
        self.progress_bar.setValue(0)
        self.interactive_grid.reset_view()
        if hasattr(self, 'interactive_grid') and self.interactive_grid.grid_coords is not None:
            total = self.interactive_grid.grid_coords.shape[1]
            for i in range(total):
                self.interactive_grid.set_node_status(i, "pending")
        print("[Measurements] 🔄 Frontend reseteado a valores iniciales.")

    @pyqtSlot(str)
    def _show_pattern_finished_dialog(self, folder_path: str):
        if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            return
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("🎉 Patrón de Impresión Finalizado")
        msg_box.setIcon(QMessageBox.Icon.Information)
        btn_accept = msg_box.addButton("Aceptar", QMessageBox.ButtonRole.AcceptRole)
        btn_save   = msg_box.addButton("Save extra info", QMessageBox.ButtonRole.ActionRole)
        msg_box.setDefaultButton(btn_accept)

        msg_box.exec()

        if msg_box.clickedButton() == btn_save:
            self._get_grid_info()
            QMessageBox.information(self, "Info Guardada", "📄 Archivo grid_info.txt guardado correctamente en la carpeta del lote.")

    @pyqtSlot(dict)
    def _show_time_volt_tracking_dialog(self, data: dict):
        rows = data.get("rows", [])
        if rows:
            total_cnt = len(rows)
            success_cnt = sum(1 for r in rows if r.get("status") == "SUCCESS")
            success_pct = (success_cnt / total_cnt) * 100.0 if total_cnt > 0 else 0.0
            self.NPevents.setText(f"{success_cnt}/{total_cnt} ({success_pct:.1f}%)")
            self.NPsuccess.setText(f"{success_cnt}/{total_cnt} ({success_pct:.1f}%)")

        if not rows:
            return
        if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            # Auto-save headless
            dlg = TimeVoltTrackingDialog(data, parent=None)
            dlg._auto_save_png()
            return
        self._tv_dialog = TimeVoltTrackingDialog(data, parent=self)
        self._tv_dialog.show()

    def make_connection(self, backend: Backend):
        backend.referenceSignal.connect(self.reference_label)
        backend.particulasSignal.connect(self.particulas_edit)
        backend.gridplotSignal.connect(self.grid_plot)
        backend.namefolderSignal.connect(self.name_folder)
        backend.indexSignal.connect(self.index_target)
        if hasattr(backend, "nodeStatusSignal"):
            backend.nodeStatusSignal.connect(self.node_status_update)
        if hasattr(backend, "patternFinishedSignal"):
            backend.patternFinishedSignal.connect(self._show_pattern_finished_dialog)
        if hasattr(backend, "driftDisplacementSignal"):
            backend.driftDisplacementSignal.connect(self.drift_xy_edit.setText)
        if hasattr(backend, "driftZDisplacementSignal"):
            backend.driftZDisplacementSignal.connect(self.drift_z_edit.setText)
        if hasattr(backend, "driftVelocitySignal"):
            backend.driftVelocitySignal.connect(self.v_drift_label.setText)
        if hasattr(backend, "timeRemainingSignal"):
            backend.timeRemainingSignal.connect(self.time_remaining_label.setText)
        if hasattr(backend, "driftTrackingFinishedSignal"):
            backend.driftTrackingFinishedSignal.connect(self._show_drift_tracking_dialog)
        if hasattr(backend, "timeVoltTrackingFinishedSignal"):
            backend.timeVoltTrackingFinishedSignal.connect(self._show_time_volt_tracking_dialog)
        if hasattr(backend, "resetFrontendSignal"):
            backend.resetFrontendSignal.connect(self.on_reset_frontend)


# ══════════════════════════════════════════════════════════════════════════════
#  BACKEND
# ══════════════════════════════════════════════════════════════════════════════

class Backend(QObject):
    referenceSignal       = pyqtSignal(list)
    particulasSignal      = pyqtSignal(int)
    gridplotSignal        = pyqtSignal(np.ndarray)
    namefolderSignal      = pyqtSignal(str)
    indexSignal           = pyqtSignal(int)
    nodeStatusSignal      = pyqtSignal(int, str)
    patternFinishedSignal = pyqtSignal(str)
    driftDisplacementSignal = pyqtSignal(str)
    driftZDisplacementSignal = pyqtSignal(str)
    driftVelocitySignal   = pyqtSignal(str)
    timeRemainingSignal   = pyqtSignal(str)
    driftTrackingFinishedSignal = pyqtSignal(dict)
    timeVoltTrackingFinishedSignal = pyqtSignal(dict)
    resetFrontendSignal   = pyqtSignal()

    grid_move_finishSignal = pyqtSignal()
    grid_autofocusSignal   = pyqtSignal(str)
    grid_traceSignal       = pyqtSignal(str, str)
    grid_trace_stopSignal  = pyqtSignal()
    grid_detectSignal      = pyqtSignal()
    grid_scanSignal        = pyqtSignal(str, str, str)
    grid_scan_stopSignal   = pyqtSignal()
    goSignal               = pyqtSignal()

    def __init__(self, mode: str = "printing", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mode_arg      = mode
        self.mode_printing = "none"
        self.number_scan   = "none"
        self.file_path     = str(DEFAULT_DATA_PATH)
        self.printing_error_x: list = []
        self.printing_error_y: list = []
        self.preescanbool  = False
        self.postscanbool  = False
        self.scanbool      = False
        self.track_drift_xy: bool = True
        self.track_drift_z: bool  = True
        self.track_time_volt: bool = True
        self.custom_name: str     = ""
        self.drift_history_xy: list = []
        self.drift_history_z: list  = []
        self.t_raw_history: list    = []
        self.grid_start_time: float = 0.0

        # Control Adaptativo de Frecuencia de Foco y Deriva
        self.adaptive_af: bool = True
        self.drift_tolerance_nm: float = 25.0
        self.last_af_time: float = 0.0
        self.last_af_index: int = 0
        self.current_n_effective: int = 5
        self.tau_safe_current: float = 300.0
        self.v_xy_current: float = 0.0
        self.v_z_current: float = 0.0
        self.v_eff_current: float = 0.0
        self.v_drift_xy_history: list = []
        self.v_drift_z_history: list = []

        # Autocompletitud inteligente de redes (Healing Pass)
        self.auto_complete_enabled: bool = False
        self.is_healing_pass: bool       = False
        self.healing_failed_queue: list  = []
        self.healing_index_in_queue: int = 0
        self.total_print_attempts: int   = 0
        self.effective_timemax: float    = 20.0
        self.node_results: dict          = {}

        self.grid_name     = "unnamed"
        self.grid_x        = np.array([0.0])
        self.grid_y        = np.array([0.0])
        self.particulas    = 1
        self.i_global      = 0
        self.xref = self.yref = self.zref = 0.0
        self.startX = self.startY = 0.0
        self.autofocus_stage = "idle"

        self.laser          = SHUTTERS[0]
        self.stopping_mode  = 0
        self.umbral         = 1.2
        self.umbral_down    = 0.0
        self.timemax        = 20.0
        self.autofoc        = 2
        self.shiftx         = 0.0
        self.shifty         = 0.0
        self.dx             = 0.0
        self.dy             = 0.0
        self.steps_before   = 10
        self.steps_after    = 10

        # Parámetros avanzados para Modos 1-4
        self.umbral_abs_v   = 2.5
        self.n_hold_steps   = 5
        self.hold_counter   = 0
        self.slope_min      = 15.0
        self.slope_flat     = 2.0
        self.ratio_k        = 10.0
        self.percent_thresh = 50.0

        # Calibración Confocal (Modo 3)
        self.v_glass        = 0.05
        self.v_peak_scaled  = 3.5

        self.ptr            = 0
        self.timeaxis: list  = []
        self.data1: list     = []
        self.data_BS: list   = []
        self.timer_real     = 0.0
        self.timer_inicio   = 0.0

        self.old_folder     = str(DEFAULT_DATA_PATH)
        self.new_folder     = str(DEFAULT_DATA_PATH)
        self.pree_folder    = str(DEFAULT_DATA_PATH)
        self.post_folder    = str(DEFAULT_DATA_PATH)

    def _format_eta(self, eta_s: float) -> str:
        if eta_s <= 0:
            return "00m 00s"
        mins = int(eta_s // 60)
        secs = int(eta_s % 60)
        if mins > 0:
            return f"{mins:02d}m {secs:02d}s"
        else:
            return f"{secs:02d}s"

    def make_connection(self, frontend: QObject):
        if hasattr(frontend, "make_connection"):
            frontend.make_connection(self)
        if hasattr(frontend, "gridSignal"):
            frontend.gridSignal.connect(self.grid_measurment)
        if hasattr(frontend, "parametersSignal"):
            frontend.parametersSignal.connect(self.grid_parameters)
        if hasattr(frontend, "gridinfoSignal"):
            frontend.gridinfoSignal.connect(self.grid_info)
        if hasattr(frontend, "setreferenceSignal"):
            frontend.setreferenceSignal.connect(self.set_reference)
        if hasattr(frontend, "goreferenceSignal"):
            frontend.goreferenceSignal.connect(self.go_reference)
        if hasattr(frontend, "resetAllSignal"):
            frontend.resetAllSignal.connect(self.reset_all)
        if hasattr(frontend, "gridcreateSignal"):
            frontend.gridcreateSignal.connect(self.grid_create)
        if hasattr(frontend, "readgridSignal"):
            frontend.readgridSignal.connect(self.grid_read)
        if hasattr(frontend, "foldergridSignal"):
            frontend.foldergridSignal.connect(self.grid_create_folder)
        if hasattr(frontend, "pauseSignal"):
            frontend.pauseSignal.connect(self.grid_pause)
        if hasattr(frontend, "next_index_Signal"):
            frontend.next_index_Signal.connect(self.grid_next_index)
        if hasattr(frontend, "new_index_Signal"):
            frontend.new_index_Signal.connect(self.grid_change_index)

    @pyqtSlot(list)
    def grid_info(self, info: list):
        target_dir = getattr(self, 'new_folder', None)
        if not target_dir or target_dir == str(DEFAULT_DATA_PATH) or not os.path.exists(target_dir):
            print(f"[Measurements] ⚠️ Carpeta del lote no creada aún. Presione el botón '{self.mode_arg.capitalize()} folder' primero.")
            return
        path = os.path.join(target_dir, "grid_info.txt")
        with open(path, "w", encoding="utf-8") as f:
            for line in info:
                f.write(f"{line[0]}\t{line[1]}\n")
        print(f"[Measurements] 📄 Archivo grid_info.txt guardado exitosamente en: {path}")

    def _read_pos(self):
        pos = pi.qPOS()
        return pos["1"], pos["2"], pos["3"]

    @pyqtSlot()
    def set_reference(self):
        self.xref, self.yref, self.zref = self._read_pos()
        self.startX = self.xref
        self.startY = self.yref
        self.drift_history_xy = []
        self.drift_history_z  = []
        self.referenceSignal.emit([self.xref, self.yref, self.zref])
        self.driftDisplacementSignal.emit("(+0.0, +0.0) nm | r=0.0 nm")
        self.driftZDisplacementSignal.emit("+0.0 nm")
        print(f"[Measurements] 🎯 Origen de referencia fijado en: X={self.xref:.3f} µm, Y={self.yref:.3f} µm, Z={self.zref:.3f} µm")

    @pyqtSlot()
    def reset_all(self):
        try: close_shutter(self.laser)
        except Exception: pass
        self.xref = self.yref = self.zref = 0.0
        self.startX = self.startY = 0.0
        self.custom_name = ""
        self.i_global = 0
        self.mode_printing = "none"
        self.is_paused = False
        self.autofocus_stage = "idle"
        self.drift_history_xy = []
        self.drift_history_z  = []
        self.v_drift_xy_history = []
        self.v_drift_z_history  = []
        self.v_xy_current       = 0.0
        self.v_z_current        = 0.0
        self.v_eff_current      = 0.0
        self.tau_safe_current   = 300.0
        self.current_n_effective = getattr(self, "autofoc", 5)
        self.last_af_time       = 0.0
        self.last_af_index      = 0
        self.t_raw_history      = []
        self.referenceSignal.emit(["NaN", "NaN", "NaN"])
        self.driftDisplacementSignal.emit("(+0.0, +0.0) nm | r=0.0 nm")
        self.driftZDisplacementSignal.emit("+0.0 nm")
        if hasattr(self, 'driftVelocitySignal'):
            self.driftVelocitySignal.emit("v: — | N_eff: 5")
        if hasattr(self, 'timeRemainingSignal'):
            self.timeRemainingSignal.emit("—")
        self.resetFrontendSignal.emit()
        print("[Measurements] 🔄 Todas las variables, referencias y acumuladores de Printing han sido reiniciados.")

    @pyqtSlot()
    def go_reference(self):
        self._moveto(self.xref, self.yref, self.zref)
        self.goSignal.emit()

    def _moveto(self, x, y, z=None):
        axes = [1, 2] if z is None else [1, 2, 3]
        targets = [x, y] if z is None else [x, y, z]
        pi.MOV(axes, targets)
        while not all(pi.qONT(axes).values()):
            time.sleep(0.01)

    @pyqtSlot()
    def grid_read(self):
        root = tk.Tk(); root.withdraw()
        name = filedialog.askopenfilename()
        if not name: return
        datos = np.loadtxt(name, unpack=True)
        self.grid_name = "Load_grid"
        self.grid_x = datos[0, :]; self.grid_y = datos[1, :]
        self.particulas = len(self.grid_x)
        self.particulasSignal.emit(self.particulas)
        self.gridplotSignal.emit(datos)

    @pyqtSlot(list)
    def grid_create(self, grid: list):
        n, N, d_n, d_N = int(grid[0]), int(grid[1]), grid[2], grid[3]
        start_x    = grid[4] if len(grid) > 4 else 2.0
        start_y    = grid[5] if len(grid) > 5 else 2.0
        drift_bool = bool(grid[6]) if len(grid) > 6 else False
        self.driftbool = drift_bool
        self.start_x_offset = start_x
        self.start_y_offset = start_y

        if drift_bool:
            total = 1 + n * N
            datos = np.zeros((3, total))
            # Partícula 0 (Ancla) en (0, 0)
            datos[0, 0] = 0.0
            datos[1, 0] = 0.0

            idx = 1
            for k in range(N):        # Filas Y
                for i in range(n):    # Columnas X (avanza en X positivo primero)
                    datos[0, idx] = start_x + i * d_n
                    datos[1, idx] = start_y + k * d_N
                    idx += 1

            self.grid_name  = f"{n}x{N}_drift_{d_n}umx{d_N}um"
            self.grid_x     = datos[0, :]
            self.grid_y     = datos[1, :]
            self.particulas = total
        else:
            datos = np.zeros((3, n * N))
            for k in range(N):        # Filas Y
                for i in range(n):    # Columnas X (avanza en X positivo primero)
                    datos[0, k*n+i] = i * d_n
                    datos[1, k*n+i] = k * d_N
            self.grid_name  = f"{n}x{N}_{d_n}umx{d_N}um"
            self.grid_x     = datos[0, :]
            self.grid_y     = datos[1, :]
            self.particulas = n * N

        self.particulasSignal.emit(self.particulas)
        self.gridplotSignal.emit(datos)

    @pyqtSlot(str)
    def grid_direction(self, path: str):
        self.file_path = path
        self.namefolderSignal.emit(path)

    @pyqtSlot(str)
    @pyqtSlot()
    def grid_create_folder(self, custom_name: str = ""):
        ts         = time.strftime("%Y%m%d-%H%M%S")
        label      = "Printing" if self.mode_arg == "printing" else "Dimers"
        self.old_folder = self.file_path
        name_tag = custom_name.strip() if custom_name and custom_name.strip() else getattr(self, "custom_name", "").strip()
        if not name_tag:
            name_tag = self.grid_name
        self.custom_name = name_tag
        self.new_folder = os.path.join(self.old_folder, f"{ts}_{label}_{name_tag}")
        os.makedirs(self.new_folder, exist_ok=True)
        self.i_global      = 1
        self.mode_printing = "none"
        self.number_scan   = "none"
        self.namefolderSignal.emit(self.new_folder)
        self.indexSignal.emit(self.i_global)

    @pyqtSlot(int, int, list, bool, bool)
    def grid_parameters(self, color_laser: int, stopping_mode: int, params: list,
                         scanbool: bool, postscanbool: bool):
        self.laser          = SHUTTERS[color_laser]
        self.stopping_mode  = stopping_mode
        self.umbral         = params[0]
        self.umbral_down    = params[1]
        self.timemax        = params[2]
        self.autofoc        = int(params[3])
        self.shiftx         = params[4]
        self.shifty         = params[5]
        self.dx             = params[6]
        self.dy             = params[7]
        self.steps_before   = int(params[8])
        self.steps_after    = int(params[9])
        self.umbral_abs_v   = params[10]
        self.n_hold_steps   = int(params[11])
        self.slope_min      = params[12]
        self.slope_flat     = params[13]
        self.ratio_k        = params[14]
        self.percent_thresh = params[15]
        if len(params) > 16:
            self.start_x_offset = params[16]
            self.start_y_offset = params[17]
            self.driftbool      = bool(params[18])
        if len(params) > 19:
            self.track_drift_xy = bool(params[19])
        else:
            self.track_drift_xy = True
        if len(params) > 20:
            self.track_drift_z  = bool(params[20])
        else:
            self.track_drift_z  = True
        if len(params) > 21:
            self.track_time_volt = bool(params[21])
        else:
            self.track_time_volt = True
        if len(params) > 22 and str(params[22]).strip():
            self.custom_name = str(params[22]).strip()
        if len(params) > 23:
            self.adaptive_af = bool(params[23])
        else:
            self.adaptive_af = True
        if len(params) > 24:
            self.drift_tolerance_nm = float(params[24])
        else:
            self.drift_tolerance_nm = 25.0
        if len(params) > 25:
            self.auto_complete_enabled = bool(params[25])
        else:
            self.auto_complete_enabled = False
        self.scanbool       = scanbool
        postscanbool_val    = postscanbool if self.mode_arg == "dimers" else False
        self.postscanbool   = postscanbool_val
        self.hold_counter   = 0
        if hasattr(self, 'stepsParametersSignal'):
            self.stepsParametersSignal.emit([self.steps_after, self.steps_before])

    @pyqtSlot()
    def grid_measurment(self):
        if getattr(self, "is_paused", False):
            self.is_paused = False
            self.mode_printing = self.mode_arg
            print(f"[Measurements] ▶️ Reanudando impresión en nodo {self.i_global}...")
            self.indexSignal.emit(self.i_global)
            self._grid_move()
        elif self.mode_printing == "none":
            self.is_paused = False
            self._grid_start()
        else:
            self.indexSignal.emit(self.i_global)
            self._grid_move()

    def _grid_start(self):
        self.mode_printing        = self.mode_arg
        self.is_paused            = False
        self.is_healing_pass      = False
        self.healing_failed_queue = []
        self.healing_index_in_queue = 0
        self.total_print_attempts = 0
        self.node_results.clear()
        self.effective_timemax    = getattr(self, "timemax", 20.0)
        self.autofocus_stage      = "idle"
        self.grid_start_time      = time.time()
        self.startX               = self.xref
        self.startY               = self.yref
        self.printing_error_x = []; self.printing_error_y = []
        self.drift_history_xy = []
        self.drift_history_z  = []
        self.v_drift_xy_history = []
        self.v_drift_z_history  = []
        self.v_xy_current       = 0.0
        self.v_z_current        = 0.0
        self.v_eff_current      = 0.0
        self.tau_safe_current   = 300.0
        self.current_n_effective = getattr(self, "autofoc", 5)
        self.last_af_time       = time.time()
        self.last_af_index      = 0

        if getattr(self, "zref", 0.0) == 0.0:
            try:
                self.zref = float(pi.qPOS().get("3", 10.0))
            except Exception:
                pass

        # Registrar punto de partida (nodo 0, t=0s, desplazamiento=0nm)
        if getattr(self, "track_drift_xy", True):
            self.drift_history_xy.append({
                "node": 0, "time": 0.0, "dx_nm": 0.0, "dy_nm": 0.0,
                "mag_nm": 0.0, "v_xy": 0.0, "stage_x": float(self.startX), "stage_y": float(self.startY)
            })
        if getattr(self, "track_drift_z", True):
            self.drift_history_z.append({
                "node": 0, "time": 0.0, "dz_nm": 0.0, "v_z": 0.0, "stage_z": float(self.zref)
            })

        if getattr(self, "driftbool", False) and self.particulas > 1:
            self.i_global = 1
        else:
            self.i_global = 0

        self.t_raw_history = []
        init_eta_s = getattr(self, "particulas", 1) * 15.0
        init_str = f"~{self._format_eta(init_eta_s)}" if getattr(self, "particulas", 0) > 0 else "—"
        if hasattr(self, "timeRemainingSignal"):
            self.timeRemainingSignal.emit(init_str)

        if self.mode_arg == "dimers":
            if self.scanbool:
                self.pree_folder = os.path.join(self.new_folder, "Pree_Scan")
                os.makedirs(self.pree_folder, exist_ok=True)
            if self.postscanbool:
                self.post_folder = os.path.join(self.new_folder, "Dimer_Scan")
                os.makedirs(self.post_folder, exist_ok=True)

        self.indexSignal.emit(self.i_global)
        self._grid_move()

    stepsParametersSignal = pyqtSignal(list)

    def _grid_move(self):
        if hasattr(self, 'grid_x') and len(self.grid_x) > 0:
            self.i_global = max(0, min(self.i_global, len(self.grid_x) - 1))
        axes    = [1, 2]
        targets = [self.grid_x[self.i_global] + self.startX,
                   self.grid_y[self.i_global] + self.startY]
        pi.MOV(axes, targets)
        if not SAFE_MODE:
            try:
                while not all(pi.qONT(axes).values()):
                    time.sleep(0.01)
            except Exception:
                time.sleep(0.1)
        else:
            time.sleep(0.05)
        self.grid_move_finishSignal.emit()

    def _update_drift_velocity(self):
        """
        Calcula las velocidades instantáneas de deriva (v_xy, v_z, v_eff) en nm/s
        y actualiza el intervalo dinámico N_adaptive según la tolerancia espacial configurada.
        """
        v_xy = 0.0
        v_z = 0.0

        # Velocidad XY
        if len(self.drift_history_xy) >= 2:
            p_curr = self.drift_history_xy[-1]
            p_prev = self.drift_history_xy[-2]
            dt = max(0.1, p_curr["time"] - p_prev["time"])
            dr = float(np.sqrt((p_curr["dx_nm"] - p_prev["dx_nm"])**2 + (p_curr["dy_nm"] - p_prev["dy_nm"])**2))
            v_xy = float(dr / dt)
            p_curr["v_xy"] = v_xy
            self.v_drift_xy_history.append(v_xy)
        elif len(self.drift_history_xy) == 1:
            self.drift_history_xy[0]["v_xy"] = 0.0

        # Velocidad Z
        if len(self.drift_history_z) >= 2:
            z_curr = self.drift_history_z[-1]
            z_prev = self.drift_history_z[-2]
            dt = max(0.1, z_curr["time"] - z_prev["time"])
            dz = abs(z_curr["dz_nm"] - z_prev["dz_nm"])
            v_z = float(dz / dt)
            z_curr["v_z"] = v_z
            self.v_drift_z_history.append(v_z)
        elif len(self.drift_history_z) == 1:
            self.drift_history_z[0]["v_z"] = 0.0

        v_eff = max(v_xy, v_z)
        tol_nm = getattr(self, "drift_tolerance_nm", 25.0)

        # Tiempo seguro de fabricación (s)
        if v_eff > 0.001:
            tau_safe = tol_nm / v_eff
        else:
            tau_safe = 300.0  # Muy estable: 5 minutos seguros

        t_per_node = 4.0
        n_calc = int(np.floor(tau_safe / t_per_node))
        n_adaptive = max(1, min(15, n_calc))

        if getattr(self, "adaptive_af", True):
            self.current_n_effective = n_adaptive
        else:
            self.current_n_effective = getattr(self, "autofoc", 5)

        self.tau_safe_current = tau_safe
        self.v_xy_current = v_xy
        self.v_z_current = v_z
        self.v_eff_current = v_eff

        disp_text = f"v_xy:{v_xy:.2f}|v_z:{v_z:.2f} nm/s | N_eff:{self.current_n_effective}"
        if hasattr(self, 'driftVelocitySignal'):
            self.driftVelocitySignal.emit(disp_text)
        print(f"[Adaptive Drift] 🧠 v_xy={v_xy:.2f} nm/s, v_z={v_z:.2f} nm/s (v_eff={v_eff:.2f} nm/s) -> τ_safe={tau_safe:.1f}s, N_eff={self.current_n_effective}")

    @pyqtSlot()
    def grid_autofoco(self):
        start_idx = 1 if (getattr(self, "driftbool", False) and self.particulas > 1) else 0
        n_every = getattr(self, "current_n_effective", getattr(self, "autofoc", 5))

        elapsed_since_last_af = time.time() - getattr(self, "last_af_time", time.time())
        tau_safe = getattr(self, "tau_safe_current", 300.0)

        # Condición 1: Por conteo de nodos
        nodes_since_last = self.i_global - getattr(self, "last_af_index", 0)
        count_trigger = (n_every > 0) and (nodes_since_last >= n_every) and (self.i_global >= start_idx)

        # Condición 2: Por tiempo transcurrido seguro
        time_trigger = getattr(self, "adaptive_af", True) and (elapsed_since_last_af >= tau_safe) and (self.i_global >= start_idx)

        # Forzar en nodo inicial start_idx
        initial_trigger = (self.i_global == start_idx)

        should_autofocus = initial_trigger or count_trigger or time_trigger

        if should_autofocus:
            self.last_af_time = time.time()
            self.last_af_index = self.i_global
            if getattr(self, "driftbool", False):
                # ── ETAPA 1/4: Desplazarse a zona limpia del ancla (-1 µm en X, -1 µm en Y) y disparar Autofoco 1 ──
                self.autofocus_stage = "anchor_autofocus"
                clean_anchor_x = self.startX - 1.0
                clean_anchor_y = self.startY - 1.0
                pi.MOV([1, 2], [clean_anchor_x, clean_anchor_y])
                time.sleep(0.1)
                up_flipper(); time.sleep(1.0)
                reason_str = "tiempo τ_safe" if time_trigger else f"conteo (N_eff={n_every})"
                print(f"[Measurements] 🔍 [Etapa 1/4] Autofoco Z en zona limpia del ancla ({clean_anchor_x:.3f}, {clean_anchor_y:.3f}) µm [Disparo por {reason_str}]...")
                self.grid_autofocusSignal.emit(self.mode_printing)
            else:
                # ── MODO ESTÁNDAR: Autofoco in-situ con shift si aplica ──
                self.autofocus_stage = "standard_autofocus"
                if self.shiftx != 0 or self.shifty != 0:
                    pi.MOV([1, 2], [self.shiftx + self.grid_x[self.i_global] + self.startX,
                                    self.shifty + self.grid_y[self.i_global] + self.startY])
                    time.sleep(0.1)
                up_flipper(); time.sleep(1.0)
                print(f"[Measurements] 🔍 Autofoco Z in-situ en nodo {self.i_global} (frecuencia cada {n_every} partículas)...")
                self.grid_autofocusSignal.emit(self.mode_printing)
        else:
            if self.mode_arg == "dimers": self._grid_center_scan()
            else:                         self._grid_trace()

    @pyqtSlot()
    def grid_finish_autofoco(self):
        time.sleep(0.1)
        # Actualizar Drift Z tras cualquier autofoco
        try:
            current_z = float(pi.qPOS().get("3", getattr(self, 'zref', 10.0)))
            z_ref_val = getattr(self, 'zref', current_z)
            disp_z_nm = (current_z - z_ref_val) * 1000.0
            drift_z_str = f"{disp_z_nm:+.1f} nm"
            self.driftZDisplacementSignal.emit(drift_z_str)
            print(f"[Focus] 📏 Drift Z acumulado: {drift_z_str} (Z={current_z:.3f} µm, Zref={z_ref_val:.3f} µm)")

            if getattr(self, "track_drift_z", True):
                elapsed_t = round(time.time() - getattr(self, "grid_start_time", time.time()), 2)
                self.drift_history_z.append({
                    "node": int(self.i_global),
                    "time": elapsed_t,
                    "dz_nm": float(disp_z_nm),
                    "stage_z": float(current_z)
                })
            self._update_drift_velocity()
        except Exception as e:
            print(f"[Focus Error] Cálculo Drift Z: {e}")

        stage = getattr(self, "autofocus_stage", "idle")

        if stage == "anchor_autofocus":
            # ── ETAPA 2/4: Mover al ancla P0 y disparar confocal drift_scan ──
            pi.MOV([1, 2], [self.startX, self.startY])
            time.sleep(0.1)
            up_flipper(); time.sleep(0.5)  # Mantener flipper en baja potencia
            self.number_scan = "drift_scan"
            print(f"[Measurements] 📸 [Etapa 2/4] Disparando escaneo confocal 2D de Partícula 0 (Ancla) en ({self.startX:.3f}, {self.startY:.3f}) µm...")
            self.grid_scanSignal.emit(self.laser, self.mode_printing, "drift_scan")

        elif stage in ("insitu_autofocus", "standard_autofocus", "idle"):
            # ── ETAPA 4/4: Posicionar en nodo objetivo y conmutar a ALTA potencia para imprimir ──
            target_x = self.grid_x[self.i_global] + self.startX
            target_y = self.grid_y[self.i_global] + self.startY
            pi.MOV([1, 2], [target_x, target_y])
            time.sleep(0.1)
            down_flipper(); time.sleep(0.5)  # Conmutar estrictamente a ALTA potencia para la traza de impresión
            print(f"[Measurements] 🎯 [Etapa 4/4] Posicionado en nodo {self.i_global} ({target_x:.3f}, {target_y:.3f}) µm. Iniciando traza a ALTA potencia...")
            self.autofocus_stage = "idle"
            if self.mode_arg == "dimers": self._grid_center_scan()
            else:                         self._grid_trace()

    def _grid_trace(self):
        down_flipper(); time.sleep(0.5)  # Conmutar estrictamente a ALTA potencia para la traza de impresión
        open_shutter(self.laser); time.sleep(0.01)
        self.timer_inicio = time.time()
        self.hold_counter = 0
        self.grid_traceSignal.emit(self.laser, self.mode_printing)

    @pyqtSlot(list)
    def grid_trace_detect(self, data: list):
        self.ptr      = data[0]
        self.timeaxis = data[1]
        self.data1    = data[2]
        self.data_BS  = data[6] if len(data) > 6 else data[5]

        # Lectura integrada de ventana móvil para I_old (baseline) e I_new (señal evento)
        if len(data) >= 6:
            I_old = float(data[4])
            I_new = float(data[5])
        else:
            I_new = float(self.data1[-1]) if len(self.data1) > 0 else 0.0
            I_old = float(self.data1[0]) if len(self.data1) > 0 else 1.0
        elapsed = time.time() - self.timer_inicio

        # 1. Derivada Discreta dI/dt (V/s) en ventana corta
        if len(self.data1) >= 5:
            dt = self.timeaxis[-1] - self.timeaxis[-5] if len(self.timeaxis) >= 5 else 0.005
            dI_dt = (self.data1[-1] - self.data1[-5]) / dt if dt > 0 else 0.0
        else:
            dI_dt = 0.0

        # 2. Evaluación de Condición de Detección según Modo Seleccionado
        condition = False

        if self.stopping_mode == 0:
            # Modo 0: Salto Relativo Estándar (I_new / I_old > Umbral)
            condition = (I_old > 0) and (I_new > I_old * self.umbral)

        elif self.stopping_mode == 1:
            # Modo 1: Salto Relativo + Umbral Absoluto (V) & Anti-Paso (N_hold)
            c_rel = (I_old > 0) and (I_new > I_old * self.umbral)
            c_abs = I_new > self.umbral_abs_v
            condition = c_rel or c_abs

        elif self.stopping_mode == 2:
            # Modo 2: Derivada Temporal Adaptativa & Aplanamiento (dI/dt -> 0 post-pico)
            c_flat = (abs(dI_dt) < self.slope_flat) and (I_new > I_old + 0.1)
            c_abs  = I_new > self.umbral_abs_v
            condition = c_flat or c_abs

        elif self.stopping_mode == 3:
            # Modo 3: Criterio Híbrido Tri-Factor (All-In-One)
            c_rel  = (I_old > 0) and (I_new > I_old * self.umbral)
            c_flat = (abs(dI_dt) < self.slope_flat) and (I_new > I_old + 0.1)
            c_abs  = I_new > self.umbral_abs_v
            condition = c_rel or c_flat or c_abs

        # Restricción Fuerte de Umbral Mínimo Absoluto en TODOS los modos:
        # Si se especificó un Umbral Mínimo (> 0 V), ningún evento por debajo de él se reconoce o detiene el obturador
        if getattr(self, "slope_min", 0.0) > 0 and I_new < self.slope_min:
            condition = False

        # 3. Verificación Anti-Partículas de Paso (N_hold steps)
        if self.stopping_mode == 0:
            should_stop = condition
        else:
            if condition:
                self.hold_counter += 1
            else:
                self.hold_counter = 0
            should_stop = (self.hold_counter >= self.n_hold_steps)

        # Aplicación final de restricción fuerte por Umbral Mínimo
        if getattr(self, "slope_min", 0.0) > 0 and I_new < self.slope_min:
            should_stop = False

        # 4. Decisión Final de Parada del Obturador
        effective_tmax = getattr(self, "effective_timemax", self.timemax) if getattr(self, "is_healing_pass", False) else self.timemax

        if should_stop or (I_new < I_old * self.umbral_down) or (elapsed > effective_tmax):
            self.grid_trace_stopSignal.emit()
            close_shutter(self.laser)
            self.timer_real = round(elapsed, 2)

            if should_stop:
                self.node_results[self.i_global] = "success"
                self.nodeStatusSignal.emit(self.i_global, "success")
            else:
                self.node_results[self.i_global] = "timeout"
                self.nodeStatusSignal.emit(self.i_global, "timeout")

            self._save_trace()

            # Actualizar promedio de t_raw y calcular ETA restante
            self.t_raw_history.append(float(self.timer_real))
            mean_t = float(np.mean(self.t_raw_history))
            if not getattr(self, "is_healing_pass", False):
                rem_nodes = max(0, getattr(self, "particulas", 1) - (self.i_global + 1))
            else:
                rem_nodes = max(0, len(self.healing_failed_queue) - (self.healing_index_in_queue + 1))

            if rem_nodes > 0:
                eta_val = rem_nodes * mean_t
                eta_text = self._format_eta(eta_val)
            else:
                eta_text = "00m 00s"
            if hasattr(self, "timeRemainingSignal"):
                self.timeRemainingSignal.emit(eta_text)
            print(f"[ETA] ⏱️ <t_raw>={mean_t:.2f}s | N_restantes={rem_nodes} -> ETA: {eta_text}")

            self.grid_detectSignal.emit()

    @pyqtSlot()
    def grid_scan(self):
        if self.scanbool and self.mode_arg == "printing":
            up_flipper(); time.sleep(1)
            self.number_scan = "none"
            self.grid_scanSignal.emit(self.laser, self.mode_printing, self.number_scan)
        else:
            self._grid_detect()

    def _grid_center_scan(self):
        up_flipper(); time.sleep(0.5)  # Conmutar estrictamente a BAJA potencia para el escaneo 2D de centrado
        self.number_scan = "center_scan"
        self.grid_scanSignal.emit(self.laser, self.mode_printing, self.number_scan)

    @pyqtSlot(np.ndarray, list, np.ndarray, np.ndarray, str, str)
    def on_scan_finished(self, image: np.ndarray, center_mass: list,
                          image_gone: np.ndarray, image_back: np.ndarray,
                          mode: str, number_scan: str):
        if mode != self.mode_arg:
            return

        if number_scan == "drift_scan":
            if center_mass and len(center_mass) >= 2:
                # Actualizar posición absoluta real del ancla (Partícula 0)
                self.startX = float(center_mass[0])
                self.startY = float(center_mass[1])

                # Calcular y actualizar casilla de Drift XY (convertido a nanómetros)
                disp_x_nm = (self.startX - self.xref) * 1000.0
                disp_y_nm = (self.startY - self.yref) * 1000.0
                mag_nm = float(np.sqrt(disp_x_nm**2 + disp_y_nm**2))
                disp_str = f"({disp_x_nm:+.1f}, {disp_y_nm:+.1f}) nm | r={mag_nm:.1f} nm"
                self.driftDisplacementSignal.emit(disp_str)
                print(f"[Drift Correction] 📍 [Etapa 3/4] Partícula 0 (Ancla) re-centrada: Δx={disp_x_nm:+.1f} nm, Δy={disp_y_nm:+.1f} nm (|r|={mag_nm:.1f} nm)")

                if getattr(self, "track_drift_xy", True):
                    elapsed_t = round(time.time() - getattr(self, "grid_start_time", time.time()), 2)
                    self.drift_history_xy.append({
                        "node": int(self.i_global),
                        "time": elapsed_t,
                        "dx_nm": float(disp_x_nm),
                        "dy_nm": float(disp_y_nm),
                        "mag_nm": float(mag_nm),
                        "stage_x": float(self.startX),
                        "stage_y": float(self.startY)
                    })
                self._update_drift_velocity()

            # ── ETAPA 3/4: Mover al sitio de impresión de la partícula i y disparar Autofoco 2 in situ ──
            self.autofocus_stage = "insitu_autofocus"
            target_insitu_x = self.grid_x[self.i_global] + self.startX + getattr(self, 'shiftx', 0.0)
            target_insitu_y = self.grid_y[self.i_global] + self.startY + getattr(self, 'shifty', 0.0)
            pi.MOV([1, 2], [target_insitu_x, target_insitu_y])
            time.sleep(0.1)
            up_flipper(); time.sleep(0.5)  # Mantener flipper en baja potencia para el autofoco in-situ
            print(f"[Measurements] 🔍 [Etapa 3/4] Disparando Autofoco Z in-situ en nodo {self.i_global} ({target_insitu_x:.3f}, {target_insitu_y:.3f}) µm...")
            self.grid_autofocusSignal.emit(self.mode_printing)
            return

        # Si estamos en Modo 3, procesar reescalado de confocal raw
        if self.stopping_mode == 3 and image is not None and image.size > 0:
            self.v_glass = float(np.min(image))
            v_peak_raw = float(np.max(image))
            amplitude = max(0.001, v_peak_raw - self.v_glass)
            self.v_peak_scaled = self.v_glass + self.ratio_k * amplitude
            
            # Matriz reescalada
            image_scaled = self.v_glass + self.ratio_k * (image - self.v_glass)
            self._save_rescaled_scan(image_scaled)

        if mode == "printing":
            self._save_scan(image, image_gone, image_back)
            self._grid_printing_error(center_mass)
            down_flipper(); time.sleep(1)
            self._grid_detect()

        elif mode == "dimers":
            if number_scan == "center_scan":
                self._save_scan(image, image_gone, image_back)
                self.center_mass_x = center_mass[0]
                self.center_mass_y = center_mass[1]
                pi.MOV([1, 2], [self.dx + self.center_mass_x,
                                self.dy + self.center_mass_y])
                time.sleep(0.1)
                if self.scanbool:
                    self.number_scan = "pree_scan"
                    self.grid_scanSignal.emit(self.laser, self.mode_printing, "pree_scan")
                else:
                    down_flipper(); time.sleep(1)
                    self._grid_trace()

            elif number_scan == "pree_scan":
                self._save_pree_scan(image, image_gone, image_back)
                pi.MOV([1, 2], [self.dx + self.center_mass_x,
                                self.dy + self.center_mass_y])
                time.sleep(0.1)
                down_flipper(); time.sleep(1)
                self._grid_trace()

            elif number_scan == "post_scan":
                self._save_post_scan(image, image_gone, image_back)
                down_flipper(); time.sleep(1)
                self._grid_detect()

    @pyqtSlot()
    def grid_finish(self):
        if self.postscanbool:
            up_flipper(); time.sleep(1)
            self.number_scan = "post_scan"
            self.grid_scanSignal.emit(self.laser, self.mode_printing, "post_scan")
        else:
            self._grid_detect()

    def _save_drift_tracking_files(self, folder_path: str):
        if not folder_path or not os.path.exists(folder_path):
            return

        # Guardar tracking XY
        if getattr(self, "track_drift_xy", True) and getattr(self, "drift_history_xy", None):
            xy_path = os.path.join(folder_path, "drift_tracking_xy.txt")
            try:
                with open(xy_path, "w", encoding="utf-8") as f:
                    f.write("# PyPrinting 3.0 - Drift Tracking XY\n")
                    f.write("# Node\tTime_s\tDelta_X_nm\tDelta_Y_nm\tMag_nm\tV_xy_nm_s\tStage_X_um\tStage_Y_um\n")
                    for pt in self.drift_history_xy:
                        v_val = pt.get("v_xy", 0.0)
                        f.write(f"{pt['node']}\t{pt['time']:.2f}\t{pt['dx_nm']:+.2f}\t{pt['dy_nm']:+.2f}\t{pt['mag_nm']:.2f}\t{v_val:.3f}\t{pt['stage_x']:.3f}\t{pt['stage_y']:.3f}\n")
                print(f"[Drift Tracking] 📄 Archivo drift_tracking_xy.txt guardado en: {xy_path}")
            except Exception as e:
                print(f"[Drift Tracking Error] Al guardar drift_tracking_xy.txt: {e}")

        # Guardar tracking Z
        if getattr(self, "track_drift_z", True) and getattr(self, "drift_history_z", None):
            z_path = os.path.join(folder_path, "drift_tracking_z.txt")
            try:
                with open(z_path, "w", encoding="utf-8") as f:
                    f.write("# PyPrinting 3.0 - Drift Tracking Z\n")
                    f.write("# Node\tTime_s\tDelta_Z_nm\tV_z_nm_s\tStage_Z_um\n")
                    for pt in self.drift_history_z:
                        v_val = pt.get("v_z", 0.0)
                        f.write(f"{pt['node']}\t{pt['time']:.2f}\t{pt['dz_nm']:+.2f}\t{v_val:.3f}\t{pt['stage_z']:.3f}\n")
                print(f"[Drift Tracking] 📄 Archivo drift_tracking_z.txt guardado en: {z_path}")
            except Exception as e:
                print(f"[Drift Tracking Error] Al guardar drift_tracking_z.txt: {e}")

    def _generate_time_volt_report(self, folder_path: str):
        """
        Analiza todas las trazas NP_*.txt del lote, ajusta la función salto (V_low, V_high, t_step),
        calcula la estadística global de tiempos y voltajes, cinética de deriva termomecánica
        y genera reporte_parametros_<nombre_red>.txt con desglose de pases primario y Healing Pass.
        """
        if not folder_path or not os.path.exists(folder_path):
            return

        import glob
        pattern = os.path.join(folder_path, "NP_*.txt")
        files = glob.glob(pattern)
        if not files:
            print(f"[Time-Volt Tracking] ⚠️ No se encontraron archivos NP_*.txt en {folder_path}")
            return

        def _sort_key(p):
            base = os.path.basename(p)
            num_str = "".join(filter(str.isdigit, base))
            return int(num_str) if num_str else 0

        files = sorted(files, key=_sort_key)
        rows = []
        for file_p in files:
            try:
                base = os.path.basename(file_p)
                node_str = "".join(filter(str.isdigit, base))
                node_idx = int(node_str) if node_str else len(rows) + 1

                # Leer tag de encabezado si fue Healing Pass
                tag = "Primary Pass"
                try:
                    with open(file_p, "r", encoding="utf-8") as hf:
                        first_line = hf.readline()
                        if "Healing Pass" in first_line:
                            tag = "Healing Pass (Retry)"
                except Exception:
                    pass

                data = np.loadtxt(file_p, unpack=True)
                if data.ndim < 2 or data.shape[1] == 0:
                    continue
                t_arr  = data[0]
                v1_arr = data[1]
                t_raw  = float(t_arr[-1])
                n_pts  = len(v1_arr)
                if n_pts == 0:
                    continue

                k_win = min(10, n_pts)
                v_low  = float(np.mean(v1_arr[:k_win]))
                v_high = float(np.mean(v1_arr[-k_win:]))
                delta_v = v_high - v_low
                ratio = v_high / max(1e-6, v_low)

                # Detección del punto medio del salto (t_step)
                v_mid = v_low + 0.5 * delta_v
                step_idx = None
                if delta_v > 0.05:
                    for idx, val in enumerate(v1_arr):
                        if val >= v_mid:
                            step_idx = idx
                            break

                if step_idx is not None:
                    t_step = float(t_arr[step_idx])
                    latency = max(0.0, t_raw - t_step)
                    status = "SUCCESS"
                else:
                    t_step = t_raw
                    latency = 0.0
                    status = "TIMEOUT / NO STEP" if (t_raw >= getattr(self, "timemax", 20.0) - 0.15 or delta_v <= 0.05) else "LOW JUMP"

                rows.append({
                    "node": node_idx,
                    "t_raw": t_raw,
                    "t_step": t_step,
                    "latency": latency,
                    "v_low": v_low,
                    "v_high": v_high,
                    "delta_v": delta_v,
                    "ratio": ratio,
                    "status": status,
                    "tag": tag
                })
            except Exception as e:
                print(f"[Time-Volt Tracking Error] Leyendo {file_p}: {e}")

        if not rows:
            return

        # Estadísticas Globales
        t_raw_vals   = [r["t_raw"] for r in rows]
        t_step_vals  = [r["t_step"] for r in rows]
        v_low_vals   = [r["v_low"] for r in rows]
        v_high_vals  = [r["v_high"] for r in rows]
        delta_v_vals = [r["delta_v"] for r in rows]
        ratio_vals   = [r["ratio"] for r in rows]
        latency_vals = [r["latency"] for r in rows]
        success_cnt  = sum(1 for r in rows if r["status"] == "SUCCESS")
        total_cnt    = len(rows)
        success_rate = (success_cnt / total_cnt) * 100.0 if total_cnt > 0 else 0.0

        name_tag = getattr(self, "custom_name", "").strip() or getattr(self, "grid_name", "grid")
        report_name = f"reporte_parametros_{name_tag}.txt"
        report_path = os.path.join(folder_path, report_name)

        stop_mode_names = [
            "Modo 0: Salto Relativo Estándar",
            "Modo 1: Salto Relativo + Umbral Absoluto (V) & Anti-Paso",
            "Modo 2: Derivada Temporal Adaptativa & Aplanamiento",
            "Modo 3: Calibración Confocal Raw & Umbral Absoluto Reescalado",
            "Modo 4: Criterio Híbrido Tri-Factor (All-In-One)"
        ]
        stop_name = stop_mode_names[self.stopping_mode] if hasattr(self, 'stopping_mode') and self.stopping_mode < len(stop_mode_names) else f"Modo {getattr(self, 'stopping_mode', 0)}"

        try:
            with open(report_path, "w", encoding="utf-8") as f:
                f.write("=" * 110 + "\n")
                f.write("REPORTE DE PARÁMETROS Y ANÁLISIS TIME-VOLT — PyPrinting 3.0\n")
                f.write("=" * 110 + "\n")
                f.write(f"Fecha y Hora:             {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Lote Experimental:        {os.path.basename(folder_path)}\n")
                f.write(f"Nombre de Red / Lote:     {name_tag}\n")
                f.write(f"Láser Utilizado:          {getattr(self, 'laser', 'Laser')}\n")
                f.write(f"Criterio de Parada:       {stop_name}\n")
                f.write(f"Umbral Relativo Config:   {getattr(self, 'umbral', 1.2):.2f}\n")
                f.write(f"Umbral Absoluto Config:   {getattr(self, 'umbral_abs_v', 2.5):.2f} V\n")
                f.write(f"Tiempo Máximo (T max):    {getattr(self, 'timemax', 20.0):.2f} s\n")
                f.write(f"Autocompletitud (Healing):{'ACTIVADA' if getattr(self, 'auto_complete_enabled', False) else 'DESACTIVADA'}\n")
                f.write(f"Steps Before / After:     {getattr(self, 'steps_before', 10)} / {getattr(self, 'steps_after', 10)}\n\n")

                f.write("=" * 110 + "\n")
                f.write("1. TABLA PARTÍCULA A PARTÍCULA (AJUSTE DE FUNCIÓN SALTO EN TRAZAS)\n")
                f.write("=" * 110 + "\n")
                f.write(f"{'Node':<6}{'t_raw (s)':<12}{'t_step (s)':<13}{'Latencia(s)':<13}{'V_low (V)':<12}{'V_high (V)':<12}{'Delta_V(V)':<12}{'Ratio':<10}{'Estado':<15}{'Pase':<20}\n")
                f.write("-" * 110 + "\n")
                for r in rows:
                    f.write(f"{r['node']:03d}   {r['t_raw']:<12.3f}{r['t_step']:<13.3f}{r['latency']:<13.3f}{r['v_low']:<12.3f}{r['v_high']:<12.3f}{r['delta_v']:<+12.3f}{r['ratio']:<10.2f}{r['status']:<15}{r.get('tag', 'Primary Pass'):<20}\n")

                f.write("\n" + "=" * 110 + "\n")
                f.write("2. ESTADÍSTICAS GLOBALES DEL LOTE\n")
                f.write("=" * 110 + "\n")
                healing_rows = [r for r in rows if "Healing Pass" in r.get("tag", "")]
                primary_rows = [r for r in rows if "Healing Pass" not in r.get("tag", "")]
                healing_success = sum(1 for r in healing_rows if r["status"] == "SUCCESS")
                primary_success = sum(1 for r in primary_rows if r["status"] == "SUCCESS")

                f.write(f"- Partículas Totales Analizadas:     {total_cnt}\n")
                f.write(f"- Eventos Exitosos Finales:          {success_cnt} ({success_rate:.1f}%)\n")
                if healing_rows:
                    f.write(f"  * Éxito en Pase Primario:          {primary_success}/{len(primary_rows)} ({primary_success/max(1,len(primary_rows))*100:.1f}%)\n")
                    f.write(f"  * Nodos Reintentados (Healing):    {len(healing_rows)}\n")
                    f.write(f"  * Recuperados en Healing Pass:     {healing_success}/{len(healing_rows)} ({healing_success/max(1,len(healing_rows))*100:.1f}%)\n")
                f.write(f"- Timeouts / Sin Salto Finales:      {total_cnt - success_cnt} ({100.0 - success_rate:.1f}%)\n\n")

                f.write(f"- Tiempo Raw Promedio <t_raw>:   {np.mean(t_raw_vals):.3f} ± {np.std(t_raw_vals):.3f} s  (Min: {np.min(t_raw_vals):.3f} s, Max: {np.max(t_raw_vals):.3f} s)\n")
                f.write(f"- Tiempo Step Promedio <t_step>: {np.mean(t_step_vals):.3f} ± {np.std(t_step_vals):.3f} s  (Min: {np.min(t_step_vals):.3f} s, Max: {np.max(t_step_vals):.3f} s)\n")
                f.write(f"- Latencia Promedio Parada:      {np.mean(latency_vals):.3f} ± {np.std(latency_vals):.3f} s\n\n")

                f.write(f"- Voltaje Low Promedio <V_low>:  {np.mean(v_low_vals):.3f} ± {np.std(v_low_vals):.3f} V\n")
                f.write(f"- Voltaje High Promedio <V_high>:{np.mean(v_high_vals):.3f} ± {np.std(v_high_vals):.3f} V\n")
                f.write(f"- Salto Promedio <Delta_V>:      {np.mean(delta_v_vals):+.3f} ± {np.std(delta_v_vals):.3f} V\n")
                f.write(f"- Ratio de Salto Promedio:       {np.mean(ratio_vals):.2f} ± {np.std(ratio_vals):.2f}\n\n")

                f.write("=" * 110 + "\n")
                f.write("3. DIAGNÓSTICO Y RECOMENDACIONES DE OPTIMIZACIÓN\n")
                f.write("=" * 110 + "\n")
                mean_ratio = float(np.mean(ratio_vals))
                cur_umbral = getattr(self, 'umbral', 1.2)
                if mean_ratio > cur_umbral * 1.3:
                    f.write(f"* Relación Señal/Fondo (SBR): EXCELENTE. El salto promedio (x{mean_ratio:.2f}) supera ampliamente el umbral ({cur_umbral:.2f}).\n")
                    f.write(f"  -> Margen de seguridad alto. Se puede aumentar el umbral a {min(mean_ratio * 0.7, cur_umbral * 1.25):.2f} si se desea mayor selectividad.\n")
                elif mean_ratio >= cur_umbral:
                    f.write(f"* Relación Señal/Fondo (SBR): ADECUADA. El salto promedio (x{mean_ratio:.2f}) está en rango del umbral ({cur_umbral:.2f}).\n")
                else:
                    f.write(f"* Relación Señal/Fondo (SBR): BAJA. El salto promedio (x{mean_ratio:.2f}) está por debajo del umbral ({cur_umbral:.2f}).\n")
                    f.write("  -> Considere reducir el umbral o verificar la alineación óptica del láser y fotodiodos.\n")

                mean_lat = float(np.mean(latency_vals))
                f.write(f"* Latencia de Obturación Promedio: {mean_lat:.3f} s.\n\n")

                f.write("=" * 110 + "\n")
                f.write("4. CINÉTICA DE DERIVA TERMOMECÁNICA Y CONTROL ADAPTATIVO\n")
                f.write("=" * 110 + "\n")
                v_xy_list = getattr(self, "v_drift_xy_history", [])
                v_z_list  = getattr(self, "v_drift_z_history", [])
                mean_v_xy = float(np.mean(v_xy_list)) if v_xy_list else 0.0
                max_v_xy  = float(np.max(v_xy_list)) if v_xy_list else 0.0
                mean_v_z  = float(np.mean(v_z_list)) if v_z_list else 0.0
                max_v_z   = float(np.max(v_z_list)) if v_z_list else 0.0
                v_eff_max = max(max_v_xy, max_v_z)
                tol_nm    = getattr(self, "drift_tolerance_nm", 25.0)
                mean_t_raw = float(np.mean(t_raw_vals)) if t_raw_vals else 4.0

                f.write(f"- Velocidad Deriva Lateral <v_xy>: {mean_v_xy:.3f} nm/s  (Máx: {max_v_xy:.3f} nm/s | {max_v_xy*60:.1f} nm/min)\n")
                f.write(f"- Velocidad Deriva Axial   <v_z>:  {mean_v_z:.3f} nm/s  (Máx: {max_v_z:.3f} nm/s | {max_v_z*60:.1f} nm/min)\n")
                f.write(f"- Tolerancia Espacial Configurada:  {tol_nm:.1f} nm\n")
                f.write(f"- Modo Control Adaptativo:         {'ACTIVADO (Sintonía dinámica)' if getattr(self, 'adaptive_af', True) else 'DESACTIVADO (Registro pasivo)'}\n\n")

                if v_eff_max > 0.001:
                    safe_tau = tol_nm / v_eff_max
                    n_opt = max(1, min(15, int(np.floor(safe_tau / (mean_t_raw + 1.0)))))
                    f.write(f"* Tiempo Seguro Estimado (tau_safe): {safe_tau:.1f} s sin corrección antes de exceder {tol_nm:.1f} nm.\n")
                    f.write(f"* Intervalo de Autofoco Recomendado (N_sugerido): Cada {n_opt} partículas (para operación manual/estática).\n")
                    if mean_v_xy > 1.0 or mean_v_z > 1.0:
                        f.write("  -> ALERTA DE DERIVA ALTA: Se recomienda encarecidamente utilizar 'Adaptive AF' o N <= 2 para evitar defocus.\n")
                    elif mean_v_xy < 0.2 and mean_v_z < 0.2:
                        f.write("  -> ESTABILIDAD TÉRMICA EXCELENTE: El microscopio está estabilizado. Se puede usar N >= 8 para acelerar throughput.\n")
                    else:
                        f.write("  -> DERIVA MODERADA: El régimen nominal (N = 3 a 5) es adecuado.\n")
                else:
                    f.write("* Deriva residual despreciable durante el lote. Intervalo recomendado: N = 8 - 10.\n")
                f.write("=" * 110 + "\n")
            print(f"[Time-Volt Tracking] 📊 Reporte de parámetros guardado en: {report_path}")
        except Exception as e:
            print(f"[Time-Volt Tracking Error] Al guardar {report_path}: {e}")

        # Emitir señal con los datos para mostrar los histogramas y auto-guardar PNG
        self.timeVoltTrackingFinishedSignal.emit({
            "rows": rows,
            "folder": folder_path
        })

    def _grid_detect(self):
        # Si estamos ejecutando el pase de autocompletitud (Healing Pass)
        if getattr(self, "is_healing_pass", False):
            self.healing_index_in_queue += 1
            self._advance_healing_pass()
            return

        Nmax = self.particulas - 1
        if self.i_global >= Nmax:
            # Fin del pase principal: verificar si se activa Healing Pass para nodos no impresos
            if getattr(self, "auto_complete_enabled", False):
                failed_nodes = [idx for idx, status in self.node_results.items() if status == "timeout"]
                if failed_nodes:
                    print(f"[Healing Pass] 🔄 Iniciando reintento de {len(failed_nodes)} nodos no impresos: {failed_nodes}")
                    self.is_healing_pass = True
                    self.healing_failed_queue = list(failed_nodes)
                    self.healing_index_in_queue = 0
                    self._advance_healing_pass()
                    return

            # Fin normal del patrón
            self._finalize_grid_measurement()
        else:
            self.i_global += 1
            self.total_print_attempts += 1
            self.indexSignal.emit(self.i_global)
            self._grid_move()

    def _advance_healing_pass(self):
        """
        Ejecuta el ciclo de reintento inteligente (Healing Pass) para nodos fallidos.
        Posiciona en el nodo, evalúa la necesidad de corrección de deriva XY en P0 (cada N partículas),
        realiza autofoco in-situ en el sitio exacto y activa la traza con tiempo extendido (+10s).
        """
        if not getattr(self, "healing_failed_queue", None) or self.healing_index_in_queue >= len(self.healing_failed_queue):
            print("[Healing Pass] 🎉 Todos los nodos del pase de autocompletitud han sido procesados.")
            self.is_healing_pass = False
            self._finalize_grid_measurement()
            return

        target_node = self.healing_failed_queue[self.healing_index_in_queue]
        self.i_global = target_node
        self.total_print_attempts += 1
        self.effective_timemax = float(getattr(self, "timemax", 20.0)) + 10.0

        self.indexSignal.emit(self.i_global)
        self.nodeStatusSignal.emit(self.i_global, "retrying")
        print(f"[Healing Pass] 🔄 Reintentando nodo {target_node} ({self.healing_index_in_queue + 1}/{len(self.healing_failed_queue)}) | T_max extendido = {self.effective_timemax}s")

        # Verificar si corresponde corrección de deriva periódica cada N partículas
        n_every = getattr(self, "current_n_effective", getattr(self, "autofoc", 5))
        do_periodic_drift = getattr(self, "driftbool", False) and (self.total_print_attempts % max(1, n_every) == 0)

        if do_periodic_drift:
            print(f"[Healing Pass] 📍 Disparando corrección periódica de deriva XY en Partícula 0 (intento global {self.total_print_attempts})...")
            self.autofocus_stage = "anchor_autofocus"
            pi.MOV([1, 2], [self.startX, self.startY])
            time.sleep(0.05)
            up_flipper(); time.sleep(0.5)
            self.grid_autofocusSignal.emit(self.mode_printing)
        else:
            target_x = self.grid_x[self.i_global] + self.startX
            target_y = self.grid_y[self.i_global] + self.startY
            pi.MOV([1, 2], [target_x, target_y])
            time.sleep(0.05)
            self.autofocus_stage = "insitu_autofocus"
            up_flipper(); time.sleep(0.5)
            print(f"[Healing Pass] 🔍 Autofoco in-situ en nodo {self.i_global} ({target_x:.3f}, {target_y:.3f}) µm...")
            self.grid_autofocusSignal.emit(self.mode_printing)

    def _finalize_grid_measurement(self):
        finished_folder = getattr(self, 'new_folder', self.old_folder)
        self.file_path = self.old_folder
        self.mode_printing = "none"
        self.is_paused = False
        self.is_healing_pass = False

        # Guardar archivos .txt de tracking de deriva si corresponde
        self._save_drift_tracking_files(finished_folder)

        # Generar reporte de parámetros Time-Volt si corresponde
        if getattr(self, "track_time_volt", True):
            self._generate_time_volt_report(finished_folder)

        self.namefolderSignal.emit(self.old_folder)
        self.indexSignal.emit(getattr(self, "particulas", 1))
        if hasattr(self, "timeRemainingSignal"):
            self.timeRemainingSignal.emit("Completado 🎉")
        self.patternFinishedSignal.emit(finished_folder)

        if getattr(self, "track_drift_xy", True) or getattr(self, "track_drift_z", True):
            v_xy_list = getattr(self, "v_drift_xy_history", [])
            v_z_list  = getattr(self, "v_drift_z_history", [])
            mean_v_xy = float(np.mean(v_xy_list)) if v_xy_list else 0.0
            mean_v_z  = float(np.mean(v_z_list)) if v_z_list else 0.0
            self.driftTrackingFinishedSignal.emit({
                "xy": self.drift_history_xy,
                "z": self.drift_history_z,
                "folder": finished_folder,
                "mean_v_xy": mean_v_xy,
                "mean_v_z": mean_v_z
            })

    @pyqtSlot()
    def grid_pause(self):
        try: close_shutter(self.laser); self.grid_trace_stopSignal.emit()
        except Exception: pass
        try: self.grid_scan_stopSignal.emit()
        except Exception: pass
        self.is_paused = True
        self.mode_printing = "none"
        print(f"[Measurements] ⏸️ Impresión pausada en nodo {self.i_global}. Presione 'Play ►' para reanudar.")

    @pyqtSlot()
    def grid_next_index(self):
        self.i_global += 1
        self.indexSignal.emit(self.i_global)
        self._grid_move()

    @pyqtSlot(int)
    def grid_change_index(self, new_index: int): self.i_global = new_index

    # ── Guardado ──────────────────────────────────────────────────────────────

    def _save_trace(self):
        ts   = f"NP_{int(self.i_global):03d}"
        name = os.path.join(self.new_folder, f"{ts}.txt")
        t    = list(np.linspace(0.01, self.timer_real, self.ptr))

        status_val = self.node_results.get(self.i_global, "UNKNOWN")
        is_healing = getattr(self, "is_healing_pass", False)

        hdr_status = f"SUCCESS (Healing Pass - Retry, t_print={self.timer_real:.2f}s)" if (is_healing and status_val == "success") else \
                     (f"TIMEOUT (Healing Pass - Retry, t_print={self.timer_real:.2f}s)" if (is_healing and status_val != "success") else \
                     (f"SUCCESS (Primary Pass, t_print={self.timer_real:.2f}s)" if status_val == "success" else f"TIMEOUT (Primary Pass, t_print={self.timer_real:.2f}s)"))

        hdr = f"Status: {hdr_status}\nTime_s\tPhotodiode_V\tPhotodiode_BS_V"
        np.savetxt(name, np.transpose([t, self.data1, self.data_BS]), fmt="%.3e", header=hdr)

    def _save_scan(self, image, gone, back, folder=None):
        folder = folder or self.new_folder
        ts     = f"NPscan_{int(self.i_global):03d}"
        for suffix, arr in [(ts, image), (f"gone_{ts}", gone), (f"back_{ts}", back)]:
            if arr is None or arr.size == 0:
                continue
            arr_tr = np.transpose(arr)

            # Exportación Multimaterial Secundaria (no altera ni reemplaza el TIFF primario)
            try:
                np.save(os.path.join(folder, f"{suffix}.npy"), arr_tr)
                np.savetxt(os.path.join(folder, f"{suffix}.csv"), arr_tr, delimiter=",", fmt="%.5e")
            except Exception:
                pass

            if arr_tr.dtype != np.uint8 and arr_tr.dtype != np.uint16:
                arr_min = float(np.min(arr_tr))
                arr_max = float(np.max(arr_tr))
                rng = max(1e-9, arr_max - arr_min)
                arr_norm = (arr_tr - arr_min) / rng
                arr_uint = (arr_norm * 65535).astype(np.uint16)
            else:
                arr_uint = arr_tr
            Image.fromarray(arr_uint).save(os.path.join(folder, f"{suffix}.tiff"))

    def _save_rescaled_scan(self, image_scaled: np.ndarray):
        ts   = f"NPscan_rescaled_{int(self.i_global):03d}"
        path_txt = os.path.join(self.new_folder, f"{ts}.txt")
        path_tif = os.path.join(self.new_folder, f"{ts}.tiff")
        np.savetxt(path_txt, image_scaled, fmt="%.4e")
        if image_scaled is not None and image_scaled.size > 0:
            arr_tr = np.transpose(image_scaled)
            arr_min = float(np.min(arr_tr))
            arr_max = float(np.max(arr_tr))
            rng = max(1e-9, arr_max - arr_min)
            arr_norm = (arr_tr - arr_min) / rng
            arr_uint = (arr_norm * 65535).astype(np.uint16)
            Image.fromarray(arr_uint).save(path_tif)

    def _save_pree_scan(self, image, gone, back):
        self._save_scan(image, gone, back, folder=self.pree_folder)

    def _save_post_scan(self, image, gone, back):
        self._save_scan(image, gone, back, folder=self.post_folder)

    def _grid_printing_error(self, center_mass: list):
        if not center_mass or len(center_mass) < 2:
            return
        target_x = self.grid_x[self.i_global] + self.startX
        target_y = self.grid_y[self.i_global] + self.startY
        self.printing_error_x.append((target_x - center_mass[0]) * 1e3)
        self.printing_error_y.append((target_y - center_mass[1]) * 1e3)
        ts   = time.strftime("%Y%m%d-%H%M%S")
        name = os.path.join(self.new_folder, f"printing_error_{ts}.txt")
        np.savetxt(name, np.transpose([self.printing_error_x, self.printing_error_y]))
