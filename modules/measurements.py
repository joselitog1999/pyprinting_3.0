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
                               QPushButton, QCheckBox, QGroupBox)
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
        self.stop_mode_combo.currentIndexChanged.connect(self._on_stopping_mode_changed)

        # ── Parámetros de detección estándar y avanzados ──────────────────────
        self.umbralEdit       = QLineEdit(str(DEFAULT_PRINTING_UMBRAL)); self.umbralEdit.setFixedWidth(55)
        self.umbral_downEdit  = QLineEdit(str(int(DEFAULT_PRINTING_UMBRAL_DOWN) if DEFAULT_PRINTING_UMBRAL_DOWN.is_integer() else DEFAULT_PRINTING_UMBRAL_DOWN)); self.umbral_downEdit.setFixedWidth(55)
        self.tmaxEdit         = QLineEdit(str(int(DEFAULT_PRINTING_TMAX) if DEFAULT_PRINTING_TMAX.is_integer() else DEFAULT_PRINTING_TMAX)); self.tmaxEdit.setFixedWidth(55)
        self.steps_beforeEdit = QLineEdit(str(DEFAULT_PRINTING_STEPS_BEFORE)); self.steps_beforeEdit.setFixedWidth(44)
        self.steps_afterEdit  = QLineEdit(str(DEFAULT_PRINTING_STEPS_AFTER)); self.steps_afterEdit.setFixedWidth(44)
        
        # Parámetros dinámicos para Modos 1-4
        self.umbral_absEdit   = QLineEdit("2.500"); self.umbral_absEdit.setFixedWidth(55)
        self.n_holdEdit       = QLineEdit("5");     self.n_holdEdit.setFixedWidth(44)
        self.slope_minEdit    = QLineEdit("15.0");  self.slope_minEdit.setFixedWidth(55)
        self.slope_flatEdit   = QLineEdit("2.0");   self.slope_flatEdit.setFixedWidth(55)
        self.ratio_kEdit      = QLineEdit("10.0");  self.ratio_kEdit.setFixedWidth(55)
        self.percent_threshEdit = QLineEdit("50.0"); self.percent_threshEdit.setFixedWidth(55)

        self.autofocEdit     = QLineEdit(str(DEFAULT_PRINTING_AUTOFOCUS_EVERY));  self.autofocEdit.setFixedWidth(44)
        self.shiftxEdit      = QLineEdit(str(int(DEFAULT_PRINTING_SHIFT_X) if DEFAULT_PRINTING_SHIFT_X.is_integer() else DEFAULT_PRINTING_SHIFT_X));  self.shiftxEdit.setFixedWidth(44)
        self.shiftyEdit      = QLineEdit(str(int(DEFAULT_PRINTING_SHIFT_Y) if DEFAULT_PRINTING_SHIFT_Y.is_integer() else DEFAULT_PRINTING_SHIFT_Y));  self.shiftyEdit.setFixedWidth(44)

        # ── Scan check ────────────────────────────────────────────────────────
        self.scan_check = QCheckBox("Scan pre-print?")
        self.scan_check.clicked.connect(self._scan_change)
        self.scan_check.setStyleSheet("color: green;")
        self._scan_change()

        # ── Post-scan (solo dimers) ────────────────────────────────────────────
        self.postscan_check = QCheckBox("Post scan?")
        self.postscan_check.setVisible(self.mode == "dimers")

        # ── dx/dy (solo dimers) ───────────────────────────────────────────────
        self.dxEdit = QLineEdit(str(int(DEFAULT_DIMERS_DX) if DEFAULT_DIMERS_DX.is_integer() else DEFAULT_DIMERS_DX)); self.dxEdit.setFixedWidth(44)
        self.dyEdit = QLineEdit(str(int(DEFAULT_DIMERS_DY) if DEFAULT_DIMERS_DY.is_integer() else DEFAULT_DIMERS_DY)); self.dyEdit.setFixedWidth(44)

        # ── Botones de control ────────────────────────────────────────────────
        self.imprimir_button = QPushButton(f"{label} folder")
        self.imprimir_button.clicked.connect(self._get_create_folder)
        self.imprimir_button.setStyleSheet("QPushButton:pressed { background-color: blue; }")

        self.play_button  = QPushButton("Play ►")
        self.play_button.clicked.connect(self._get_grid_measurement)

        self.pause_button = QPushButton("Pause")
        self.pause_button.clicked.connect(lambda: self.pauseSignal.emit())

        self.next_button  = QPushButton("Next index ►")
        self.next_button.clicked.connect(lambda: self.next_index_Signal.emit())

        self.go_ref_button  = QPushButton("Go reference")
        self.go_ref_button.clicked.connect(lambda: self.goreferenceSignal.emit())
        self.go_ref_button.setFixedWidth(90)

        self.set_ref_button = QPushButton("Set reference")
        self.set_ref_button.clicked.connect(lambda: self.setreferenceSignal.emit())
        self.set_ref_button.setStyleSheet(
            "QPushButton { background-color: orange; }"
            "QPushButton:pressed { background-color: blue; }")

        # ── Contadores ────────────────────────────────────────────────────────
        self.NameDirValue      = QLabel("")
        self.NameDirValue.setStyleSheet("background-color: red;")
        self.particulasEdit    = QLabel("0")
        self.indice_impresionEdit = QLineEdit("0")
        self.indice_impresionEdit.textChanged.connect(self._new_index_target)

        # ── Referencia ────────────────────────────────────────────────────────
        self.xrefLabel = QLabel("NaN")
        self.yrefLabel = QLabel("NaN")
        self.zrefLabel = QLabel("NaN")

        # ── Crear grilla ──────────────────────────────────────────────────────
        self.number_files    = QLineEdit(str(DEFAULT_GRID_NPS_COL))
        self.number_columns  = QLineEdit(str(DEFAULT_GRID_COLS))
        self.distance_files  = QLineEdit(str(int(DEFAULT_GRID_DIST_NP) if DEFAULT_GRID_DIST_NP.is_integer() else DEFAULT_GRID_DIST_NP))
        self.distance_columns= QLineEdit(str(int(DEFAULT_GRID_DIST_COL) if DEFAULT_GRID_DIST_COL.is_integer() else DEFAULT_GRID_DIST_COL))

        self.grid_create_button = QPushButton("Create grid")
        self.grid_create_button.clicked.connect(self._get_grid_create)
        self.grid_create_button.setStyleSheet(
            "QPushButton { background-color: orange; }"
            "QPushButton:pressed { background-color: blue; }")

        self.cargar_archivo_button = QPushButton("Load grid (.txt)")
        self.cargar_archivo_button.clicked.connect(lambda: self.readgridSignal.emit())
        self.cargar_archivo_button.setStyleSheet(
            "QPushButton { background-color: orange; }"
            "QPushButton:pressed { background-color: blue; }")

        # ── Info extra ────────────────────────────────────────────────────────
        self.powerlaser  = QLineEdit("—")
        self.typeNP      = QLineEdit("—")
        self.substrate   = QLineEdit("—")
        self.NPevents    = QLineEdit("—")
        self.NPsuccess   = QLineEdit("—")
        self.extra_info  = QLineEdit("—")
        self.grid_save_info_button = QPushButton("Save info")
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

        # Focus shift dock
        fsW = QWidget(); flo = QGridLayout(fsW)
        flo.addWidget(QLabel("Autofocus every N"), 0, 0); flo.addWidget(self.autofocEdit, 0, 1)
        flo.addWidget(QLabel("Shift x (µm)"),      1, 0); flo.addWidget(self.shiftxEdit,  1, 1)
        flo.addWidget(QLabel("Shift y (µm)"),      2, 0); flo.addWidget(self.shiftyEdit,  2, 1)
        if self.mode == "dimers":
            flo.addWidget(QLabel("dx (µm)"), 3, 0); flo.addWidget(self.dxEdit, 3, 1)
            flo.addWidget(QLabel("dy (µm)"), 4, 0); flo.addWidget(self.dyEdit, 4, 1)
        fsDock = Dock("Focus shift"); fsDock.addWidget(fsW)
        dock_area.addDock(fsDock, "right", pcDock)

        # Extra info dock
        eiW = QWidget(); elo = QGridLayout(eiW)
        ei_rows = [("Power BFP (mW)", self.powerlaser),
                   ("NP type",        self.typeNP),
                   ("Substrate",      self.substrate),
                   ("NP events",      self.NPevents),
                   ("NP success",     self.NPsuccess),
                   ("Comments",       self.extra_info)]
        for r, (lbl, w) in enumerate(ei_rows):
            elo.addWidget(QLabel(lbl), r, 0); elo.addWidget(w, r, 1)
        elo.addWidget(self.grid_save_info_button, len(ei_rows), 0, 1, 2)
        eiDock = Dock("Extra info"); eiDock.addWidget(eiW)
        dock_area.addDock(eiDock, "right", fsDock)

        hbox.addWidget(dock_area)

        # Inicializar visibilidad dinámica de casilleros según Modo 0 por defecto
        self._on_stopping_mode_changed(0)

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
        root = tk.Tk(); root.withdraw()
        path = filedialog.askdirectory()
        if path: self.foldergridSignal.emit()

    def _get_grid_create(self):
        try:
            grid = [int(self.number_files.text()),
                    int(self.number_columns.text()),
                    float(self.distance_files.text()),
                    float(self.distance_columns.text())]
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
            float(self.percent_threshEdit.text() or 50.0)
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

    @pyqtSlot(int)
    def particulas_edit(self, n: int): self.particulasEdit.setText(str(n))
    @pyqtSlot(str)
    def name_folder(self, folder: str): self.NameDirValue.setText(folder); self.NameDirValue.setStyleSheet("background-color: green;")
    @pyqtSlot(int)
    def index_target(self, i: int): self.indice_impresionEdit.setText(str(i))

    @pyqtSlot(np.ndarray)
    def grid_plot(self, datos: np.ndarray):
        self._gridplot = pg.GraphicsLayoutWidget()
        p = self._gridplot.addPlot(title="Grilla")
        p.showGrid(x=True, y=True)
        p.setLabel("left", "x (µm)"); p.setLabel("bottom", "y (µm)")
        p.plot(datos[1, :], datos[0, :], pen=None, symbol="o")
        self._gridplot.show()

    def make_connection(self, backend: Backend):
        backend.referenceSignal.connect(self.reference_label)
        backend.particulasSignal.connect(self.particulas_edit)
        backend.gridplotSignal.connect(self.grid_plot)
        backend.namefolderSignal.connect(self.name_folder)
        backend.indexSignal.connect(self.index_target)


# ══════════════════════════════════════════════════════════════════════════════
#  BACKEND
# ══════════════════════════════════════════════════════════════════════════════

class Backend(QObject):
    referenceSignal       = pyqtSignal(list)
    particulasSignal      = pyqtSignal(int)
    gridplotSignal        = pyqtSignal(np.ndarray)
    namefolderSignal      = pyqtSignal(str)
    indexSignal           = pyqtSignal(int)

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
        datos = np.zeros((3, n * N))
        for i in range(n):
            for k in range(N):
                datos[0, k*n+i] = i * d_n
                datos[1, k*n+i] = k * d_N
        self.grid_name  = f"{n}x{N}_{d_n}umx{d_N}um"
        self.grid_x     = datos[0, :]; self.grid_y = datos[1, :]
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
        multifoco = np.arange(0, self.particulas - 1, self.autofoc)
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
        I_old, I_new  = data[3], data[4]
        self.data_BS  = data[5]
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
