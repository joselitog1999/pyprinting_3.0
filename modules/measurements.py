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
import time
import numpy as np
from PIL import Image
import tkinter as tk
from tkinter import filedialog

import pyqtgraph as pg
from PyQt6.QtCore    import Qt, QObject, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (QApplication, QWidget, QFrame, QGridLayout,
                               QHBoxLayout, QVBoxLayout, QLabel, QLineEdit, QComboBox,
                               QPushButton, QCheckBox, QGroupBox, QProgressBar)
from PyQt6.QtGui     import QIntValidator
from pyqtgraph.dockarea import DockArea, Dock

from config import (pi, SHUTTERS, DEFAULT_DATA_PATH,
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
#  FRONTEND  (compartido por Printing y Dimers — se instancia con mode=)
# ══════════════════════════════════════════════════════════════════════════════

class Frontend(QFrame):
    setreferenceSignal  = pyqtSignal()
    goreferenceSignal   = pyqtSignal()
    readgridSignal      = pyqtSignal()
    gridcreateSignal    = pyqtSignal(list)
    foldergridSignal    = pyqtSignal()
    gridSignal          = pyqtSignal()
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

        # ── Selector de 5 Modos de Criterio de Parada ─────────────────────────
        self.stop_mode_combo = QComboBox()
        self.stop_mode_combo.addItems([
            "Modo 0: Legacy (Salto Relativo Estándar)",
            "Modo 1: Salto Relativo + Umbral Absoluto & Anti-Paso",
            "Modo 2: Derivada Temporal Adaptativa & Aplanamiento (dI/dt)",
            "Modo 3: Calibración Confocal Raw & Umbral Absoluto Reescalado",
            "Modo 4: Criterio Híbrido Tri-Factor (All-In-One)"
        ])
        self.stop_mode_combo.setToolTip("Algoritmo de criterio de parada en tiempo real (Modos 0 a 4).")
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

        # Parámetros dinámicos para Modos 1-4
        self.umbral_absEdit   = QLineEdit("2.500"); self.umbral_absEdit.setFixedWidth(55)
        self.umbral_absEdit.setToolTip("Voltaje absoluto mínimo en Volts (Modos 1, 2 y 4) necesario para considerar el evento.")
        self.n_holdEdit       = QLineEdit("5");     self.n_holdEdit.setFixedWidth(44)
        self.n_holdEdit.setToolTip("Número de pasos continuos de confirmación (anti-paso) para descartar partículas flotantes de paso.")
        self.slope_minEdit    = QLineEdit("15.0");  self.slope_minEdit.setFixedWidth(55)
        self.slope_minEdit.setToolTip("Derivada mínima dI/dt (V/s) en el pico para el criterio de aplanamiento (Modos 2 y 4).")
        self.slope_flatEdit   = QLineEdit("2.0");   self.slope_flatEdit.setFixedWidth(55)
        self.slope_flatEdit.setToolTip("Pendiente máxima dI/dt (V/s) en la meseta para confirmar la parada del obturador (Modos 2 y 4).")
        self.ratio_kEdit      = QLineEdit("10.0");  self.ratio_kEdit.setFixedWidth(55)
        self.ratio_kEdit.setToolTip("Constante de amplificación K (P_print / P_scan) para reescalado confocal en Modo 3.")
        self.percent_threshEdit = QLineEdit("50.0"); self.percent_threshEdit.setFixedWidth(55)
        self.percent_threshEdit.setToolTip("Porcentaje de umbral confocal reescalado (%) para disparar la parada en Modo 3.")

        self.autofocEdit     = QLineEdit(str(DEFAULT_PRINTING_AUTOFOCUS_EVERY));  self.autofocEdit.setFixedWidth(44)
        self.autofocEdit.setToolTip("Frecuencia de partículas (cada N partículas) entre las cuales se ejecuta el autofoco axial dinámico en Z.")
        self.shiftxEdit      = QLineEdit(str(int(DEFAULT_PRINTING_SHIFT_X) if DEFAULT_PRINTING_SHIFT_X.is_integer() else DEFAULT_PRINTING_SHIFT_X));  self.shiftxEdit.setFixedWidth(44)
        self.shiftxEdit.setToolTip("Desplazamiento X en µm para realizar el autofoco Z en una zona limpia contigua sin perturbar el nodo actual.")
        self.shiftyEdit      = QLineEdit(str(int(DEFAULT_PRINTING_SHIFT_Y) if DEFAULT_PRINTING_SHIFT_Y.is_integer() else DEFAULT_PRINTING_SHIFT_Y));  self.shiftyEdit.setFixedWidth(44)
        self.shiftyEdit.setToolTip("Desplazamiento Y en µm para realizar el autofoco Z en una zona limpia contigua sin perturbar el nodo actual.")

        # ── Scan check ────────────────────────────────────────────────────────
        self.scan_check = QCheckBox("Scan pre-print?")
        self.scan_check.setToolTip("Ejecuta un escaneo confocal de verificación previo a la impresión del nodo.")
        self.scan_check.clicked.connect(self._scan_change)
        self.scan_check.setStyleSheet("color: green;")
        self._scan_change()

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
        self.disp_acumuladoEdit = QLineEdit("(+0.000, +0.000) µm | r=0.000 µm")
        self.disp_acumuladoEdit.setReadOnly(True)
        self.disp_acumuladoEdit.setStyleSheet("font-family: monospace; font-weight: bold; color: #4a9eff;")
        self.disp_acumuladoEdit.setToolTip("Desplazamiento vectorial acumulado (Δx, Δy) µm corregido por Drift Correction.")
        self.extra_info  = QLineEdit("—"); self.extra_info.setToolTip("Comentarios experimentales adicionales.")
        self.grid_save_info_button = QPushButton("Save info")
        self.grid_save_info_button.setToolTip("Guarda el archivo grid_info.txt en la carpeta del lote experimental.")
        self.grid_save_info_button.clicked.connect(self._get_grid_info)

        # ── Layout principal ──────────────────────────────────────────────────
        hbox      = QHBoxLayout(self)
        dock_area = DockArea()

        # Reference dock
        refW = QWidget(); rlo = QGridLayout(refW)
        rlo.addWidget(QLabel("X ref:"),    0, 0); rlo.addWidget(self.xrefLabel, 0, 1)
        rlo.addWidget(QLabel("Y ref:"),    1, 0); rlo.addWidget(self.yrefLabel, 1, 1)
        rlo.addWidget(QLabel("Z ref:"),    2, 0); rlo.addWidget(self.zrefLabel, 2, 1)
        rlo.addWidget(self.set_ref_button, 3, 0, 1, 2)
        rlo.addWidget(self.go_ref_button,  4, 0)
        refDock = Dock("Reference pos"); refDock.addWidget(refW)
        dock_area.addDock(refDock)

        # Grid create dock
        gcW = QWidget(); glo = QGridLayout(gcW)
        glo.addWidget(QLabel("NPs/col"),        0, 0); glo.addWidget(self.number_files,    0, 1)
        glo.addWidget(QLabel("Columns"),         1, 0); glo.addWidget(self.number_columns,  1, 1)
        glo.addWidget(QLabel("Dist NP (µm)"),   2, 0); glo.addWidget(self.distance_files,  2, 1)
        glo.addWidget(QLabel("Dist col (µm)"),  3, 0); glo.addWidget(self.distance_columns,3, 1)
        glo.addWidget(self.grid_create_button,  4, 0, 1, 2)
        glo.addWidget(self.cargar_archivo_button,5,0,1,2)
        gcDock = Dock("Grid"); gcDock.addWidget(gcW)
        dock_area.addDock(gcDock, "right", refDock)

        # Print control dock (Multi-column layout expandido)
        pcW = QWidget(); plo = QGridLayout(pcW)
        plo.setContentsMargins(6, 6, 6, 6)
        plo.setHorizontalSpacing(10)
        plo.setVerticalSpacing(4)

        # Fila 0: Botón de directorio + Nombre de ruta
        plo.addWidget(self.imprimir_button,    0, 0, 1, 2)
        plo.addWidget(self.NameDirValue,       0, 2, 1, 2)

        # Fila 1: Selector de Criterio de Parada
        plo.addWidget(QLabel("Criterio Parada:"), 1, 0)
        plo.addWidget(self.stop_mode_combo,       1, 1, 1, 3)

        # Fila 2: Láser | Umbral Relativo
        plo.addWidget(QLabel("Láser:"),        2, 0); plo.addWidget(self.grid_laser,       2, 1)
        self.lbl_umbral_rel = QLabel("Umbral rel:"); plo.addWidget(self.lbl_umbral_rel, 2, 2); plo.addWidget(self.umbralEdit, 2, 3)

        # Fila 3: Umbral Absoluto (V) | N hold steps
        self.lbl_umbral_abs = QLabel("Umbral Abs (V):"); plo.addWidget(self.lbl_umbral_abs, 3, 0); plo.addWidget(self.umbral_absEdit, 3, 1)
        self.lbl_n_hold     = QLabel("N hold steps:");  plo.addWidget(self.lbl_n_hold,     3, 2); plo.addWidget(self.n_holdEdit,     3, 3)

        # Fila 4: Slope Min (V/s) | Slope Flat (V/s)
        self.lbl_slope_min  = QLabel("Slope Min:");     plo.addWidget(self.lbl_slope_min,  4, 0); plo.addWidget(self.slope_minEdit,  4, 1)
        self.lbl_slope_flat = QLabel("Slope Flat:");    plo.addWidget(self.lbl_slope_flat, 4, 2); plo.addWidget(self.slope_flatEdit, 4, 3)

        # Fila 5: Ratio K (P_print/P_scan) | Porcentaje Umbral (%)
        self.lbl_ratio_k    = QLabel("Ratio K (P/S):"); plo.addWidget(self.lbl_ratio_k,    5, 0); plo.addWidget(self.ratio_kEdit,    5, 1)
        self.lbl_pct_thresh = QLabel("Umbral (%):");    plo.addWidget(self.lbl_pct_thresh, 5, 2); plo.addWidget(self.percent_threshEdit, 5, 3)

        # Fila 6: Umbral down | T max (s)
        plo.addWidget(QLabel("Umbral down:"),  6, 0); plo.addWidget(self.umbral_downEdit,   6, 1)
        plo.addWidget(QLabel("T max (s):"),    6, 2); plo.addWidget(self.tmaxEdit,          6, 3)

        # Fila 7: Steps before | Steps after
        self.lbl_steps_before = QLabel("Steps before:"); plo.addWidget(self.lbl_steps_before, 7, 0); plo.addWidget(self.steps_beforeEdit, 7, 1)
        self.lbl_steps_after  = QLabel("Steps after:");  plo.addWidget(self.lbl_steps_after,  7, 2); plo.addWidget(self.steps_afterEdit,  7, 3)

        # Fila 8: Scan pre-print | Post scan
        plo.addWidget(self.scan_check,         8, 0, 1, 2)
        if self.mode == "dimers":
            plo.addWidget(self.postscan_check, 8, 2, 1, 2)

        # Fila 9: Controles de reproducción Play / Pause / Next Index
        plo.addWidget(self.play_button,        9, 0); plo.addWidget(self.pause_button,      9, 1)
        plo.addWidget(self.next_button,        9, 2, 1, 2)

        # Fila 10: Total targets | Target Index
        plo.addWidget(QLabel("Total targets:"), 10, 0); plo.addWidget(self.particulasEdit,     10, 1)
        plo.addWidget(QLabel("Target Index:"),  10, 2); plo.addWidget(self.indice_impresionEdit,10, 3)

        pcDock = Dock(f"{label} control", size=(640, 420))
        pcDock.addWidget(pcW)
        dock_area.addDock(pcDock, "right", gcDock)

        # Focus shift & Drift correction dock
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

        fsDock = Dock("Focus shift & Drift"); fsDock.addWidget(fsW)
        dock_area.addDock(fsDock, "right", pcDock)

        # Extra info dock
        eiW = QWidget(); elo = QGridLayout(eiW)
        ei_rows = [("Power BFP (mW)", self.powerlaser),
                   ("NP type",        self.typeNP),
                   ("Substrate",      self.substrate),
                   ("NP events",      self.NPevents),
                   ("NP success",     self.NPsuccess),
                   ("Desplazamiento acumulado", self.disp_acumuladoEdit),
                   ("Comments",       self.extra_info)]
        for r, (lbl, w) in enumerate(ei_rows):
            elo.addWidget(QLabel(lbl), r, 0); elo.addWidget(w, r, 1)
        elo.addWidget(self.grid_save_info_button, len(ei_rows), 0, 1, 2)
        eiDock = Dock("Extra info"); eiDock.addWidget(eiW)
        dock_area.addDock(eiDock, "right", fsDock)

        # Interactive Grid Viewer Dock
        self.interactive_grid = InteractiveGridWidget()
        self.interactive_grid.nodeClickedSignal.connect(self._on_grid_node_clicked)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(18)
        self.progress_bar.setStyleSheet(
            "QProgressBar { text-align: center; border: 1px solid #45475a; border-radius: 4px; background-color: #1e1e2e; color: #cdd6f4; font-size: 8pt; }"
            "QProgressBar::chunk { background-color: #a6e3a1; }"
        )
        plo.addWidget(QLabel("Progreso Lote:"), 11, 0)
        plo.addWidget(self.progress_bar,        11, 1, 1, 3)

        gridViewerDock = Dock(f"{label} Pattern & Path Viewer 🗺️", size=(450, 420))
        gridViewerDock.addWidget(self.interactive_grid)
        dock_area.addDock(gridViewerDock, "right", eiDock)

        hbox.addWidget(dock_area)

        # Inicializar visibilidad dinámica de casilleros según Modo 0 por defecto
        self._on_stopping_mode_changed(0)

    def _on_grid_node_clicked(self, idx: int):
        self.indice_impresionEdit.setText(str(idx))
        self.new_index_Signal.emit(idx)

    def _on_stopping_mode_changed(self, idx: int):
        """Muestra u oculta los casilleros de la interfaz según el Modo de Parada seleccionado."""
        # Modo 0: Legacy (Salto Relativo Estándar)
        # Modo 1: Salto Relativo + Absoluto & Anti-Paso
        # Modo 2: Derivada dI/dt
        # Modo 3: Calibración Confocal Raw
        # Modo 4: Criterio Híbrido Tri-Factor
        show_rel     = idx in (0, 1, 4)
        show_abs     = idx in (1, 2, 4)
        show_hold    = idx in (1, 2, 3, 4)
        show_slope   = idx in (2, 4)
        show_confocal= idx in (3,)
        show_steps   = idx in (0, 1, 4)

        self.lbl_umbral_rel.setVisible(show_rel);      self.umbralEdit.setVisible(show_rel)
        self.lbl_umbral_abs.setVisible(show_abs);      self.umbral_absEdit.setVisible(show_abs)
        self.lbl_n_hold.setVisible(show_hold);         self.n_holdEdit.setVisible(show_hold)
        self.lbl_slope_min.setVisible(show_slope);     self.slope_minEdit.setVisible(show_slope)
        self.lbl_slope_flat.setVisible(show_slope);    self.slope_flatEdit.setVisible(show_slope)
        self.lbl_ratio_k.setVisible(show_confocal);    self.ratio_kEdit.setVisible(show_confocal)
        self.lbl_pct_thresh.setVisible(show_confocal); self.percent_threshEdit.setVisible(show_confocal)
        self.lbl_steps_before.setVisible(show_steps);  self.steps_beforeEdit.setVisible(show_steps)
        self.lbl_steps_after.setVisible(show_steps);   self.steps_afterEdit.setVisible(show_steps)

    def _color_menu(self, combo: QComboBox):
        colors = ["#2e7d32", "#c62828", "#f57f17"] # verde, rojo, amarillo
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
            float(self.slope_minEdit.text() or 15.0),
            float(self.slope_flatEdit.text() or 2.0),
            float(self.ratio_kEdit.text() or 10.0),
            float(self.percent_threshEdit.text() or 50.0),
            float(self.startxEdit.text() or 2.0),
            float(self.startyEdit.text() or 2.0),
            self.drift_check.isChecked()
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

    def make_connection(self, backend: Backend):
        backend.referenceSignal.connect(self.reference_label)
        backend.particulasSignal.connect(self.particulas_edit)
        backend.gridplotSignal.connect(self.grid_plot)
        backend.namefolderSignal.connect(self.name_folder)
        backend.indexSignal.connect(self.index_target)
        if hasattr(backend, "nodeStatusSignal"):
            backend.nodeStatusSignal.connect(self.node_status_update)


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

        self.grid_name     = "unnamed"
        self.grid_x        = np.array([0.0])
        self.grid_y        = np.array([0.0])
        self.particulas    = 1
        self.i_global      = 0
        self.xref = self.yref = self.zref = 0.0
        self.startX = self.startY = 0.0

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
        if hasattr(self, 'new_folder') and os.path.exists(self.new_folder):
            path = os.path.join(self.new_folder, "grid_info.txt")
            with open(path, "w", encoding="utf-8") as f:
                for line in info:
                    f.write(f"{line[0]}\t{line[1]}\n")

    def _read_pos(self):
        pos = pi.qPOS()
        return pos["1"], pos["2"], pos["3"]

    @pyqtSlot()
    def set_reference(self):
        self.xref, self.yref, self.zref = self._read_pos()
        self.referenceSignal.emit([self.xref, self.yref, self.zref])

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
        self.scanbool       = scanbool
        self.postscanbool   = postscanbool
        self.hold_counter   = 0

    @pyqtSlot()
    def grid_measurment(self):
        if self.mode_printing == "none":
            self._grid_start()
        else:
            self.indexSignal.emit(self.i_global)
            self._grid_move()

    def _grid_start(self):
        self.mode_printing = self.mode_arg
        self.startX        = self.xref
        self.startY        = self.yref
        self.printing_error_x = []; self.printing_error_y = []

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

        self._grid_move()

    def _grid_move(self):
        axes    = [1, 2]
        targets = [self.grid_x[self.i_global] + self.startX,
                   self.grid_y[self.i_global] + self.startY]
        pi.MOV(axes, targets); time.sleep(0.1)
        self.grid_move_finishSignal.emit()

    @pyqtSlot()
    def grid_autofoco(self):
        multifoco = np.arange(0, self.particulas, self.autofoc)
        if self.i_global in multifoco:
            if self.shiftx != 0 or self.shifty != 0:
                pi.MOV([1, 2], [self.shiftx + self.grid_x[self.i_global] + self.startX,
                                self.shifty + self.grid_y[self.i_global] + self.startY])
                time.sleep(0.1)
            up_flipper(); time.sleep(1)
            self.grid_autofocusSignal.emit(self.mode_printing)
        else:
            if self.mode_arg == "dimers": self._grid_center_scan()
            else:                         self._grid_trace()

    @pyqtSlot()
    def grid_finish_autofoco(self):
        time.sleep(0.1)
        if self.shiftx != 0 or self.shifty != 0:
            pi.MOV([1, 2], [self.grid_x[self.i_global] + self.startX,
                            self.grid_y[self.i_global] + self.startY])
            time.sleep(0.1)
        if getattr(self, "driftbool", False):
            # Mover a la Partícula 0 (Origen de referencia + deriva acumulada)
            pi.MOV([1, 2], [self.startX, self.startY])
            time.sleep(0.1)
            # Mantener flipper arriba (baja potencia) para el escaneo confocal de drift
            self.number_scan = "drift_scan"
            self.grid_scanSignal.emit(self.laser, self.mode_printing, "drift_scan")
        else:
            down_flipper(); time.sleep(1)
            if self.mode_arg == "dimers": self._grid_center_scan()
            else:                         self._grid_trace()

    def _grid_trace(self):
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

        # Lectura instantánea (I_new) e inicial de fondo (I_old) como flotantes escalares
        I_new = float(self.data1[-1]) if len(self.data1) > 0 else 0.0
        I_old = float(self.data1[0]) if len(self.data1) > 0 else 1.0
        elapsed       = time.time() - self.timer_inicio

        # 1. Derivada Discreta dI/dt (V/s) en ventana corta
        if len(self.data1) >= 5:
            dt = self.timeaxis[-1] - self.timeaxis[-5] if len(self.timeaxis) >= 5 else 0.005
            dI_dt = (self.data1[-1] - self.data1[-5]) / dt if dt > 0 else 0.0
        else:
            dI_dt = 0.0

        # 2. Evaluación de Condición de Detección según Modo Seleccionado
        condition = False

        if self.stopping_mode == 0:
            # Modo 0: Legacy (Salto Relativo Estándar I_new / I_old > Umbral)
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
            # Modo 3: Calibración Confocal Raw & Umbral Absoluto Reescalado (K_scale, P%)
            v_thresh = self.v_glass + (self.percent_thresh / 100.0) * (self.v_peak_scaled - self.v_glass)
            condition = I_new > v_thresh

        elif self.stopping_mode == 4:
            # Modo 4: Criterio Híbrido Tri-Factor (All-In-One)
            c_rel  = (I_old > 0) and (I_new > I_old * self.umbral)
            c_flat = (abs(dI_dt) < self.slope_flat) and (I_new > I_old + 0.1)
            c_abs  = I_new > self.umbral_abs_v
            condition = c_rel or c_flat or c_abs

        # 3. Verificación Anti-Partículas de Paso (N_hold steps)
        if self.stopping_mode == 0:
            should_stop = condition
        else:
            if condition:
                self.hold_counter += 1
            else:
                self.hold_counter = 0
            should_stop = (self.hold_counter >= self.n_hold_steps)

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
                dx_drift = center_mass[0] - self.xref
                dy_drift = center_mass[1] - self.yref
                self.startX += dx_drift
                self.startY += dy_drift

                # Calcular y actualizar casilla de Desplazamiento Acumulado
                disp_x = self.startX - self.xref - getattr(self, 'start_x_offset', 0.0)
                disp_y = self.startY - self.yref - getattr(self, 'start_y_offset', 0.0)
                mag = float(np.sqrt(disp_x**2 + disp_y**2))
                disp_str = f"({disp_x:+.3f}, {disp_y:+.3f}) µm | r={mag:.3f} µm"
                if hasattr(self, 'disp_acumuladoEdit'):
                    self.disp_acumuladoEdit.setText(disp_str)

            down_flipper(); time.sleep(0.5)  # Conmutar a alta potencia para continuar la impresión
            pi.MOV([1, 2], [self.grid_x[self.i_global] + self.startX,
                            self.grid_y[self.i_global] + self.startY])
            time.sleep(0.1)
            if self.mode_arg == "dimers": self._grid_center_scan()
            else:                         self._grid_trace()
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

    def _grid_detect(self):
        Nmax = self.particulas - 1
        if self.i_global >= Nmax:
            self.file_path = self.old_folder
            self.namefolderSignal.emit(self.old_folder)
            self.indexSignal.emit(self.i_global + 1)
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
            Image.fromarray(np.transpose(arr)).save(os.path.join(folder, f"{suffix}.tiff"))

    def _save_rescaled_scan(self, image_scaled: np.ndarray):
        ts   = f"NPscan_rescaled_{int(self.i_global):03d}"
        path_txt = os.path.join(self.new_folder, f"{ts}.txt")
        path_tif = os.path.join(self.new_folder, f"{ts}.tiff")
        np.savetxt(path_txt, image_scaled, fmt="%.4e")
        Image.fromarray(np.transpose(image_scaled)).save(path_tif)

    def _save_pree_scan(self, image, gone, back):
        self._save_scan(image, gone, back, folder=self.pree_folder)

    def _save_post_scan(self, image, gone, back):
        self._save_scan(image, gone, back, folder=self.post_folder)

    def _grid_printing_error(self, center_mass: list):
        target_x = self.grid_x[self.i_global] + self.startX
        target_y = self.grid_y[self.i_global] + self.startY
        self.printing_error_x.append((target_x - center_mass[0]) * 1e3)
        self.printing_error_y.append((target_y - center_mass[1]) * 1e3)
        ts   = time.strftime("%Y%m%d-%H%M%S")
        name = os.path.join(self.new_folder, f"printing_error_{ts}.txt")
        np.savetxt(name, np.transpose([self.printing_error_x, self.printing_error_y]))
