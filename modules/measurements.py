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

        # ── Visualizador PyQtGraph (Orientación Física 90° a la derecha) ────
        # Sistema cartesiano físico del microscopio:
        #   Eje Vertical   = X (Positivo +X para abajo -> invertY)
        #   Eje Horizontal = Y (Negativo -Y a la derecha -> invertX)
        self.graphics = pg.GraphicsLayoutWidget()
        self.plot = self.graphics.addPlot()
        self.plot.setAspectLocked(True)
        self.plot.showGrid(x=True, y=True)
        self.plot.invertY(True)   # +X hacia abajo
        self.plot.invertX(False)  # +Y hacia la derecha (dirección estándar)

        label_style = {"color": "#cdd6f4", "font-size": "9pt"}
        self.plot.setLabel("left", "X (µm)", **label_style)    # Eje vertical = X
        self.plot.setLabel("bottom", "Y (µm)", **label_style)  # Eje horizontal = Y

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
        """Carga las coordenadas de la grilla datos[2, N] y reconstruye la visualización (mapeando Y a horizontal, X a vertical)."""
        if datos is None or datos.shape[0] < 2 or datos.shape[1] == 0:
            return

        self.grid_coords = datos
        xs_stage = datos[0, :]  # Coordenada X platina
        ys_stage = datos[1, :]  # Coordenada Y platina
        N = len(xs_stage)

        # Mapeo a pantalla: X_display = Y_stage (horiz), Y_display = X_stage (vert)
        x_disp = ys_stage
        y_disp = xs_stage

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
        """Actualiza el estado del nodo idx ('active', 'success', 'timeout', 'pending')."""
        if self.grid_coords is None or idx < 0 or idx >= len(self.node_states):
            return

        # Si el anterior estaba en 'active', revertir a 'success' si no era timeout
        for i, st in enumerate(self.node_states):
            if st == "active" and i != idx:
                self.node_states[i] = "success"

        self.node_states[idx] = status

        x_disp = self.grid_coords[1, :]  # Y_stage (pantalla horiz)
        y_disp = self.grid_coords[0, :]  # X_stage (pantalla vert)

        if status == "active":
            self.active_ring.setData([x_disp[idx]], [y_disp[idx]])

        self._update_scatter()

    def _update_scatter(self):
        if self.grid_coords is None:
            return

        x_disp = self.grid_coords[1, :]  # Y_stage (pantalla horiz)
        y_disp = self.grid_coords[0, :]  # X_stage (pantalla vert)
        N = len(x_disp)

        color_map = {
            "pending": "#45475a",
            "active":  "#f9e2af",
            "success": "#a6e3a1",
            "timeout": "#f38ba8",
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
                'size': 16 if st == 'active' else 14
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

        lbl_info = QLabel(f"<b>🗺️ Mapa y Registro de Deriva Termomecánica</b> | Lote: <code>{self.folder}</code>")
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
#  FRONTEND  (compartido por Printing y Dimers — se instancia con mode=)
# ══════════════════════════════════════════════════════════════════════════════

class Frontend(QFrame):
    setreferenceSignal  = pyqtSignal()
    goreferenceSignal   = pyqtSignal()
    resetAllSignal      = pyqtSignal()
    readgridSignal      = pyqtSignal()
    gridcreateSignal    = pyqtSignal(list)
    gridSignal          = pyqtSignal()
    foldergridSignal    = pyqtSignal()
    # (color_laser, stopping_mode, params, scanbool, postscanbool)
    parametersSignal    = pyqtSignal(int, int, list, bool, bool)
    pauseSignal         = pyqtSignal()
    next_index_Signal   = pyqtSignal()
    new_index_Signal    = pyqtSignal(int)
    gridinfoSignal      = pyqtSignal(list)

    def __init__(self, mode: str = "printing", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mode = mode
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

        # ── Post-scan (solo dimers) ────────────────────────────────────────────
        self.postscan_check = QCheckBox("Post scan?")
        self.postscan_check.setToolTip("Ejecuta un escaneo confocal posterior para confirmar la formación del dímero.")
        self.postscan_check.setVisible(self.mode == "dimers")

        # ── dx/dy (solo dimers) ───────────────────────────────────────────────
        self.dxEdit = QLineEdit(str(int(DEFAULT_DIMERS_DX) if DEFAULT_DIMERS_DX.is_integer() else DEFAULT_DIMERS_DX)); self.dxEdit.setFixedWidth(44)
        self.dxEdit.setToolTip("Desplazamiento X (µm) para la colocación de la segunda nanopartícula en el dímero.")
        self.dyEdit = QLineEdit(str(int(DEFAULT_DIMERS_DY) if DEFAULT_DIMERS_DY.is_integer() else DEFAULT_DIMERS_DY)); self.dyEdit.setFixedWidth(44)
        self.dyEdit.setToolTip("Desplazamiento Y (µm) para la colocación de la segunda nanopartícula en el dímero.")

        # ── Botones de control ────────────────────────────────────────────────
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

        # ── Info extra ────────────────────────────────────────────────────────
        self.powerlaser  = QLineEdit("—"); self.powerlaser.setToolTip("Potencia medida en la pupila trasera del objetivo (BFP en mW).")
        self.typeNP      = QLineEdit("—"); self.typeNP.setToolTip("Tipo y tamaño de la solución coloidal de nanopartículas (ej. AuNP 60 nm).")
        self.substrate   = QLineEdit("—"); self.substrate.setToolTip("Sustrato y funcionalización (ej. vidrio + PDDA + PSS).")
        self.NPevents    = QLineEdit("—"); self.NPevents.setToolTip("Porcentaje de eventos de impresión detectados (%).")
        self.NPsuccess   = QLineEdit("—"); self.NPsuccess.setToolTip("Porcentaje de éxito en la formación de la grilla (%).")
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
        glo.addWidget(self.cargar_archivo_button,5,0,1,2)

        # Print control widget (Multi-column layout expandido)
        pcW = QWidget(); plo = QGridLayout(pcW)
        plo.setContentsMargins(6, 6, 6, 6)
        plo.setHorizontalSpacing(10)
        plo.setVerticalSpacing(4)

        # Fila 0: Botón de directorio + Nombre de ruta
        plo.addWidget(self.imprimir_button,    0, 0, 1, 2)
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

        # Fila 8: Scan pre-print | Track Drift XY | Track Drift Z | Post scan
        plo.addWidget(self.scan_check,           8, 0)
        plo.addWidget(self.track_drift_xy_check, 8, 1)
        plo.addWidget(self.track_drift_z_check,  8, 2)
        if self.mode == "dimers":
            plo.addWidget(self.postscan_check,   8, 3)

        # Fila 9: Controles de reproducción Play / Pause / Next Index
        plo.addWidget(self.play_button,        9, 0); plo.addWidget(self.pause_button,      9, 1)
        plo.addWidget(self.next_button,        9, 2, 1, 2)

        # Fila 10: Total targets | Target Index
        plo.addWidget(QLabel("Total targets:"), 10, 0); plo.addWidget(self.particulasEdit,      10, 1)
        plo.addWidget(QLabel("Target Index:"),  10, 2); plo.addWidget(self.indice_impresionEdit, 10, 3)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(18)
        self.progress_bar.setStyleSheet(
            "QProgressBar { text-align: center; border: 1px solid #45475a; border-radius: 4px; background-color: #1e1e2e; color: #cdd6f4; font-size: 8pt; }"
            "QProgressBar::chunk { background-color: #a6e3a1; }"
        )
        plo.addWidget(QLabel("Progreso Lote:"), 10, 0)
        plo.addWidget(self.progress_bar,        10, 1, 1, 3)

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

        r_offset = 5 if self.mode == "dimers" else 3
        flo.addWidget(self.drift_check,        r_offset,   0, 1, 2)
        flo.addWidget(QLabel("Start X (µm)"),  r_offset+1, 0); flo.addWidget(self.startxEdit, r_offset+1, 1)
        flo.addWidget(QLabel("Start Y (µm)"),  r_offset+2, 0); flo.addWidget(self.startyEdit, r_offset+2, 1)

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
        self.foldergridSignal.emit()

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
            self.track_drift_z_check.isChecked()
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
                ["Drift XY:", self.drift_xy_edit.text()],
                ["Drift Z:", self.drift_z_edit.text()],
                ["Track Drift XY:", "ON" if self.track_drift_xy_check.isChecked() else "OFF"],
                ["Track Drift Z:", "ON" if self.track_drift_z_check.isChecked() else "OFF"],
                ["Comments:", self.extra_info.text()]]
        self.gridinfoSignal.emit(info)

    @pyqtSlot(list)
    def reference_label(self, ref: list):
        self.xrefLabel.setText(str(ref[0]))
        self.yrefLabel.setText(str(ref[1]))
        self.zrefLabel.setText(str(ref[2]))
        self.set_ref_button.setStyleSheet("QPushButton { background-color: #2e7d32; color: white; font-weight: bold; }")

    @pyqtSlot(int)
    def particulas_edit(self, n: int): self.particulasEdit.setText(str(n))
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
        self.xrefLabel.setText("NaN")
        self.yrefLabel.setText("NaN")
        self.zrefLabel.setText("NaN")
        self.set_ref_button.setStyleSheet("QPushButton { background-color: orange; } QPushButton:pressed { background-color: blue; }")
        self.indice_impresionEdit.setText("0")
        self.drift_xy_edit.setText("(+0.0, +0.0) nm | r=0.0 nm")
        self.drift_z_edit.setText("+0.0 nm")
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
        msg_box.setWindowTitle("Patrón finalizado")
        msg_box.setIcon(QMessageBox.Icon.Information)
        msg_box.setText("🎉 <b>¡Patrón de impresión finalizado con éxito!</b>")
        msg_box.setInformativeText(f"Se ha completado la secuencia en todas las partículas.\nCarpeta del lote: {folder_path}")

        btn_accept = msg_box.addButton("Aceptar", QMessageBox.ButtonRole.AcceptRole)
        btn_save   = msg_box.addButton("Save extra info", QMessageBox.ButtonRole.ActionRole)
        msg_box.setDefaultButton(btn_accept)

        msg_box.exec()

        if msg_box.clickedButton() == btn_save:
            self._get_grid_info()
            QMessageBox.information(self, "Info Guardada", "📄 Archivo grid_info.txt guardado correctamente en la carpeta del lote.")

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
        if hasattr(backend, "driftTrackingFinishedSignal"):
            backend.driftTrackingFinishedSignal.connect(self._show_drift_tracking_dialog)
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
    driftTrackingFinishedSignal = pyqtSignal(dict)
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
        self.drift_history_xy: list = []
        self.drift_history_z: list  = []
        self.grid_start_time: float = 0.0

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
        self.i_global = 0
        self.mode_printing = "none"
        self.is_paused = False
        self.autofocus_stage = "idle"
        self.drift_history_xy = []
        self.drift_history_z  = []
        self.referenceSignal.emit(["NaN", "NaN", "NaN"])
        self.driftDisplacementSignal.emit("(+0.0, +0.0) nm | r=0.0 nm")
        self.driftZDisplacementSignal.emit("+0.0 nm")
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

    @pyqtSlot()
    def grid_create_folder(self):
        ts         = time.strftime("%Y%m%d-%H%M%S")
        label      = "Printing" if self.mode_arg == "printing" else "Dimers"
        self.old_folder = self.file_path
        self.new_folder = os.path.join(self.old_folder, f"{ts}_{label}_{self.grid_name}")
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
        self.scanbool       = scanbool
        self.postscanbool   = postscanbool
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
        self.mode_printing   = self.mode_arg
        self.is_paused       = False
        self.autofocus_stage = "idle"
        self.grid_start_time = time.time()
        self.startX          = self.xref
        self.startY          = self.yref
        self.printing_error_x = []; self.printing_error_y = []
        self.drift_history_xy = []
        self.drift_history_z  = []

        if getattr(self, "zref", 0.0) == 0.0:
            try:
                self.zref = float(pi.qPOS().get("3", 10.0))
            except Exception:
                pass

        # Registrar punto de partida (nodo 0, t=0s, desplazamiento=0nm)
        if getattr(self, "track_drift_xy", True):
            self.drift_history_xy.append({
                "node": 0, "time": 0.0, "dx_nm": 0.0, "dy_nm": 0.0,
                "mag_nm": 0.0, "stage_x": float(self.startX), "stage_y": float(self.startY)
            })
        if getattr(self, "track_drift_z", True):
            self.drift_history_z.append({
                "node": 0, "time": 0.0, "dz_nm": 0.0, "stage_z": float(self.zref)
            })

        if getattr(self, "driftbool", False) and self.particulas > 1:
            self.i_global = 1
        else:
            self.i_global = 0

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

    @pyqtSlot()
    def grid_autofoco(self):
        if self.autofoc > 0:
            start_idx = 1 if (getattr(self, "driftbool", False) and self.particulas > 1) else 0
            should_autofocus = ((self.i_global - start_idx) % self.autofoc == 0) and (self.i_global >= start_idx)
        else:
            should_autofocus = False

        if should_autofocus:
            if getattr(self, "driftbool", False):
                # ── ETAPA 1/4: Desplazarse a zona limpia del ancla (-1 µm en X, -1 µm en Y) y disparar Autofoco 1 ──
                self.autofocus_stage = "anchor_autofocus"
                clean_anchor_x = self.startX - 1.0
                clean_anchor_y = self.startY - 1.0
                pi.MOV([1, 2], [clean_anchor_x, clean_anchor_y])
                time.sleep(0.1)
                up_flipper(); time.sleep(1.0)
                print(f"[Measurements] 🔍 [Etapa 1/4] Autofoco Z en zona limpia del ancla ({clean_anchor_x:.3f}, {clean_anchor_y:.3f}) µm...")
                self.grid_autofocusSignal.emit(self.mode_printing)
            else:
                # ── MODO ESTÁNDAR: Autofoco in-situ con shift si aplica ──
                self.autofocus_stage = "standard_autofocus"
                if self.shiftx != 0 or self.shifty != 0:
                    pi.MOV([1, 2], [self.shiftx + self.grid_x[self.i_global] + self.startX,
                                    self.shifty + self.grid_y[self.i_global] + self.startY])
                    time.sleep(0.1)
                up_flipper(); time.sleep(1.0)
                print(f"[Measurements] 🔍 Autofoco Z in-situ en nodo {self.i_global} (frecuencia cada {self.autofoc} partículas)...")
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
        if should_stop or (I_new < I_old * self.umbral_down) or (elapsed > self.timemax):
            self.grid_trace_stopSignal.emit()
            close_shutter(self.laser)
            self.timer_real = round(elapsed, 2)
            self._save_trace()
            if should_stop:
                self.nodeStatusSignal.emit(self.i_global, "success")
            else:
                self.nodeStatusSignal.emit(self.i_global, "timeout")
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
                    f.write("# Node\tTime_s\tDelta_X_nm\tDelta_Y_nm\tMag_nm\tStage_X_um\tStage_Y_um\n")
                    for pt in self.drift_history_xy:
                        f.write(f"{pt['node']}\t{pt['time']:.2f}\t{pt['dx_nm']:+.2f}\t{pt['dy_nm']:+.2f}\t{pt['mag_nm']:.2f}\t{pt['stage_x']:.3f}\t{pt['stage_y']:.3f}\n")
                print(f"[Drift Tracking] 📄 Archivo drift_tracking_xy.txt guardado en: {xy_path}")
            except Exception as e:
                print(f"[Drift Tracking Error] Al guardar drift_tracking_xy.txt: {e}")

        # Guardar tracking Z
        if getattr(self, "track_drift_z", True) and getattr(self, "drift_history_z", None):
            z_path = os.path.join(folder_path, "drift_tracking_z.txt")
            try:
                with open(z_path, "w", encoding="utf-8") as f:
                    f.write("# PyPrinting 3.0 - Drift Tracking Z\n")
                    f.write("# Node\tTime_s\tDelta_Z_nm\tStage_Z_um\n")
                    for pt in self.drift_history_z:
                        f.write(f"{pt['node']}\t{pt['time']:.2f}\t{pt['dz_nm']:+.2f}\t{pt['stage_z']:.3f}\n")
                print(f"[Drift Tracking] 📄 Archivo drift_tracking_z.txt guardado en: {z_path}")
            except Exception as e:
                print(f"[Drift Tracking Error] Al guardar drift_tracking_z.txt: {e}")

    def _grid_detect(self):
        Nmax = self.particulas - 1
        if self.i_global >= Nmax:
            finished_folder = getattr(self, 'new_folder', self.old_folder)
            self.file_path = self.old_folder
            self.mode_printing = "none"
            self.is_paused = False

            # Guardar archivos .txt de tracking de deriva si corresponde
            self._save_drift_tracking_files(finished_folder)

            self.namefolderSignal.emit(self.old_folder)
            self.indexSignal.emit(self.i_global + 1)
            self.patternFinishedSignal.emit(finished_folder)

            if getattr(self, "track_drift_xy", True) or getattr(self, "track_drift_z", True):
                self.driftTrackingFinishedSignal.emit({
                    "xy": self.drift_history_xy,
                    "z": self.drift_history_z,
                    "folder": finished_folder
                })
        else:
            self.i_global += 1
            self.indexSignal.emit(self.i_global)
            self._grid_move()

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
        np.savetxt(name, np.transpose([t, self.data1, self.data_BS]), fmt="%.3e")

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
