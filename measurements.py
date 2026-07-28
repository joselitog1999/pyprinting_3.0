# -*- coding: utf-8 -*-
"""
measurements.py — Grillas de impresión y dímeros (Printing + Dimers unificados)
PyPrinting — UNSAM Nanofotónica  —  PyQt6

Reemplaza Printing_pp.py + Dimers_pp.py.
Ambos módulos comparten ~80% del código; la diferencia está en:
  - mode='printing': ciclo mover→autofoco→traza→(scan_optional)→detect
  - mode='dimers':   ciclo mover→autofoco→center_scan→(pree_scan)→traza→(post_scan)→detect
    con los booleanos preescanbool y postscanbool que habilitan los scans extra.

La señal scanfinishedSignal de Confocal.Backend (unificada) emite:
    (image, center_mass, image_gone, image_back, mode, number_scan)
y este módulo la recibe en _on_scan_finished() para dispatchar correctamente.

Correcciones respecto a los originales:
  - isChecked() con paréntesis
  - pi importado desde config (singleton)
  - open_shutter/close_shutter/up_flipper/down_flipper desde nidaq
  - parametersSignal de Printing y Dimers tenían firmas distintas (int,list,bool)
    vs (int,list,bool,bool) → ahora ambos usan (int, list, bool, bool)
    donde el cuarto bool es postscanbool (ignorado en modo printing)
"""
from __future__ import annotations
import os
import time
import numpy as np
from PIL import Image
from tkinter import filedialog
import tkinter as tk

import pyqtgraph as pg
from PyQt6.QtCore    import Qt, QObject, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (QApplication, QWidget, QFrame, QGridLayout,
                              QHBoxLayout, QLabel, QLineEdit, QComboBox,
                              QPushButton, QCheckBox)
from PyQt6.QtGui     import QIntValidator
from pyqtgraph.dockarea import DockArea, Dock

from config import pi, SHUTTERS, DEFAULT_DATA_PATH
from nidaq  import (open_shutter, close_shutter,
                    up_flipper, down_flipper)


# ══════════════════════════════════════════════════════════════════════════════
#  FRONTEND  (compartido por Printing y Dimers — se instancia con mode=)
# ══════════════════════════════════════════════════════════════════════════════

class Frontend(QFrame):
    """
    Pasar mode='printing' o mode='dimers' al instanciar.
    El modo controla qué campos extras se muestran (pre/post scan para dimers).
    """

    setreferenceSignal  = pyqtSignal()
    goreferenceSignal   = pyqtSignal()
    readgridSignal      = pyqtSignal()
    gridcreateSignal    = pyqtSignal(list)
    foldergridSignal    = pyqtSignal()
    gridSignal          = pyqtSignal()
    # (color_laser, [umbral, umbral_down, tmax, autofoc, shiftx, shifty, dx, dy],
    #  scanbool, postscanbool)
    parametersSignal    = pyqtSignal(int, list, bool, bool)
    pauseSignal         = pyqtSignal()
    next_index_Signal   = pyqtSignal()
    new_index_Signal    = pyqtSignal(int)
    gridinfoSignal      = pyqtSignal(list)

    def __init__(self, mode: str = "printing", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mode = mode
        self._setup_gui()

    # ── GUI ───────────────────────────────────────────────────────────────────

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

        # ── Parámetros de detección ───────────────────────────────────────────
        self.umbralEdit      = QLineEdit("1.2")
        self.umbral_downEdit = QLineEdit("0")
        self.tmaxEdit        = QLineEdit("20")
        self.autofocEdit     = QLineEdit("2");  self.autofocEdit.setFixedWidth(44)
        self.shiftxEdit      = QLineEdit("0");  self.shiftxEdit.setFixedWidth(44)
        self.shiftyEdit      = QLineEdit("0");  self.shiftyEdit.setFixedWidth(44)

        # ── Scan check ────────────────────────────────────────────────────────
        self.scan_check = QCheckBox("Scan pre-print?")
        self.scan_check.clicked.connect(self._scan_change)
        self.scan_check.setStyleSheet("color: green;")
        self._scan_change()

        # ── Post-scan (solo dimers) ────────────────────────────────────────────
        self.postscan_check = QCheckBox("Post scan?")
        self.postscan_check.setVisible(self.mode == "dimers")

        # ── dx/dy (solo dimers) ───────────────────────────────────────────────
        self.dxEdit = QLineEdit("0"); self.dxEdit.setFixedWidth(44)
        self.dyEdit = QLineEdit("0"); self.dyEdit.setFixedWidth(44)

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
        self.number_files    = QLineEdit("4")
        self.number_columns  = QLineEdit("4")
        self.distance_files  = QLineEdit("3")
        self.distance_columns= QLineEdit("3")

        self.grid_create_button = QPushButton("Create grid")
        self.grid_create_button.clicked.connect(self._get_grid_create)
        self.grid_create_button.setStyleSheet(
            "QPushButton { background-color: orange; }"
            "QPushButton:pressed { background-color: blue; }")

        self.cargar_archivo_button = QPushButton("Load grid (.txt)")
        self.cargar_archivo_button.clicked.connect(lambda: self.readgridSignal.emit())
        self.cargar_archivo_button.setStyleSheet(
            "QPushButton { background-color: orange; }")

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

        # Print control dock
        pcW = QWidget(); plo = QGridLayout(pcW)
        plo.addWidget(self.imprimir_button,    0, 0, 1, 2)
        plo.addWidget(self.NameDirValue,       0, 2, 1, 2)
        plo.addWidget(QLabel("Láser:"),        1, 0); plo.addWidget(self.grid_laser,       1, 1)
        plo.addWidget(QLabel("Umbral:"),       2, 0); plo.addWidget(self.umbralEdit,        2, 1)
        plo.addWidget(QLabel("Umbral down:"),  3, 0); plo.addWidget(self.umbral_downEdit,   3, 1)
        plo.addWidget(QLabel("T max (s):"),    4, 0); plo.addWidget(self.tmaxEdit,          4, 1)
        plo.addWidget(self.scan_check,         5, 0)
        if self.mode == "dimers":
            plo.addWidget(self.postscan_check, 5, 1)
        plo.addWidget(self.set_ref_button,     6, 0, 1, 2)
        plo.addWidget(self.play_button,        7, 0); plo.addWidget(self.pause_button,      7, 1)
        plo.addWidget(self.next_button,        8, 0)
        plo.addWidget(QLabel("Total targets"), 9, 0); plo.addWidget(self.particulasEdit,    9, 1)
        plo.addWidget(QLabel("Index"),        10, 0); plo.addWidget(self.indice_impresionEdit,10,1)
        pcDock = Dock(f"{label} control"); pcDock.addWidget(pcW)
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
                   ("Total events (%)", self.NPevents),
                   ("Success (%)",    self.NPsuccess),
                   ("Comments",       self.extra_info)]
        for row, (lbl, w) in enumerate(ei_rows):
            elo.addWidget(QLabel(lbl), row, 0); elo.addWidget(w, row, 1)
        elo.addWidget(self.grid_save_info_button, len(ei_rows), 0)
        eiDock = Dock("Extra info"); eiDock.addWidget(eiW)
        dock_area.addDock(eiDock, "right", fsDock)

        hbox.addWidget(dock_area)
        self.setLayout(hbox)

    # ── Helpers GUI ──────────────────────────────────────────────────────────

    def _color_menu(self, combo: QComboBox):
        colors = ["color: green;", "color: red;", "color: #d4ac0d; font-weight: bold;", "color: blue;", "color: darkred;"]
        idx = combo.currentIndex()
        if 0 <= idx < len(colors):
            combo.setStyleSheet(f"QComboBox {{ {colors[idx]} }}")

    def _scan_change(self):
        checked = self.scan_check.isChecked()
        self.scan_check.setText("Scan? YES" if checked else "Scan? NO")
        self.scan_check.setStyleSheet("color: orange;" if checked else "color: blue;")

    def _new_index_target(self):
        try:
            self.new_index_Signal.emit(int(self.indice_impresionEdit.text()))
        except ValueError:
            pass

    def _get_create_folder(self):
        self.foldergridSignal.emit()

    def _get_grid_create(self):
        try:
            grid = [int(self.number_files.text()),
                    int(self.number_columns.text()),
                    float(self.distance_files.text()),
                    float(self.distance_columns.text())]
            self.gridcreateSignal.emit(grid)
        except ValueError:
            pass

    def _get_grid_measurement(self):
        self._emit_parameters()
        self.gridSignal.emit()

    def _emit_parameters(self):
        color = self.grid_laser.currentIndex()
        params = [float(self.umbralEdit.text()),
                  float(self.umbral_downEdit.text()),
                  float(self.tmaxEdit.text()),
                  float(self.autofocEdit.text()),
                  float(self.shiftxEdit.text()),
                  float(self.shiftyEdit.text()),
                  float(self.dxEdit.text()),
                  float(self.dyEdit.text())]
        scanbool     = self.scan_check.isChecked()
        postscanbool = self.postscan_check.isChecked() if self.mode == "dimers" else False
        self.parametersSignal.emit(color, params, scanbool, postscanbool)

    def _get_grid_info(self):
        info = [["Laser:", self.grid_laser.currentText()],
                ["Umbral:", self.umbralEdit.text()],
                ["Power BFP:", self.powerlaser.text()],
                ["NP type:", self.typeNP.text()],
                ["Substrate:", self.substrate.text()],
                ["Comments:", self.extra_info.text()]]
        self.gridinfoSignal.emit(info)

    # ── Slots desde Backend ───────────────────────────────────────────────────

    @pyqtSlot(list)
    def reference_label(self, ref: list):
        self.xrefLabel.setText(str(ref[0]))
        self.yrefLabel.setText(str(ref[1]))
        self.zrefLabel.setText(str(ref[2]))

    @pyqtSlot(int)
    def particulas_edit(self, n: int):
        self.particulasEdit.setText(str(n))

    @pyqtSlot(str)
    def name_folder(self, folder: str):
        self.NameDirValue.setText(folder)
        self.NameDirValue.setStyleSheet("background-color: green;")

    @pyqtSlot(int)
    def index_target(self, i: int):
        self.indice_impresionEdit.setText(str(i))

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
    grid_autofocusSignal   = pyqtSignal(str)      # mode_printing
    grid_traceSignal       = pyqtSignal(str, str)  # laser, mode
    grid_trace_stopSignal  = pyqtSignal()
    grid_detectSignal      = pyqtSignal()
    grid_scanSignal        = pyqtSignal(str, str, str)  # laser, mode, number_scan
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
        # Atributos de grilla — se asignan al cargar/crear la grilla
        self.grid_name     = "unnamed"
        self.grid_x        = np.array([0.0])
        self.grid_y        = np.array([0.0])
        self.particulas    = 1
        self.i_global      = 0
        # Atributos de referencia — se asignan en set_reference
        self.xref = self.yref = self.zref = 0.0
        self.startX = self.startY = 0.0
        # Atributos de trace — se asignan en grid_parameters
        self.laser         = SHUTTERS[0]
        self.umbral        = 1.2
        self.umbral_down   = 0.0
        self.timemax       = 20.0
        self.autofoc       = 2
        self.shiftx        = 0.0
        self.shifty        = 0.0
        self.dx            = 0.0
        self.dy            = 0.0
        # Atributos de trace data — se asignan en grid_trace_detect
        self.ptr           = 0
        self.timeaxis: list = []
        self.data1: list    = []
        self.data_BS: list  = []
        self.timer_real    = 0.0
        self.timer_inicio  = 0.0
        # Carpetas — se asignan en grid_create_folder
        self.old_folder    = str(DEFAULT_DATA_PATH)
        self.new_folder    = str(DEFAULT_DATA_PATH)
        self.pree_folder   = str(DEFAULT_DATA_PATH)
        self.post_folder   = str(DEFAULT_DATA_PATH)

    # ── Reference / position ─────────────────────────────────────────────────

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

    # ── Grid load / create ────────────────────────────────────────────────────

    @pyqtSlot()
    def grid_read(self):
        root = tk.Tk(); root.withdraw()
        name = filedialog.askopenfilename()
        if not name:
            return
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
        self.new_folder = os.path.join(self.old_folder,
                                       f"{ts}_{label}_{self.grid_name}")
        os.makedirs(self.new_folder, exist_ok=True)
        self.i_global      = 1
        self.mode_printing = "none"
        self.number_scan   = "none"
        self.namefolderSignal.emit(self.new_folder)
        self.indexSignal.emit(self.i_global)

    # ── Parameters ───────────────────────────────────────────────────────────

    @pyqtSlot(int, list, bool, bool)
    def grid_parameters(self, color_laser: int, params: list,
                         scanbool: bool, postscanbool: bool):
        self.laser        = SHUTTERS[color_laser]
        self.umbral       = params[0]
        self.umbral_down  = params[1]
        self.timemax      = params[2]
        self.autofoc      = int(params[3])
        self.shiftx       = params[4]
        self.shifty       = params[5]
        self.dx           = params[6]
        self.dy           = params[7]
        self.scanbool     = scanbool
        self.postscanbool = postscanbool

    # ── Grid measurement loop ─────────────────────────────────────────────────

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
            print(f"[Meas] Autofoco en partícula {self.i_global}")
            if self.shiftx != 0 or self.shifty != 0:
                pi.MOV([1, 2], [self.shiftx + self.grid_x[self.i_global] + self.startX,
                                self.shifty + self.grid_y[self.i_global] + self.startY])
                time.sleep(0.1)
            up_flipper(); time.sleep(1)
            self.grid_autofocusSignal.emit(self.mode_printing)
        else:
            if self.mode_arg == "dimers":
                self._grid_center_scan()
            else:
                self._grid_trace()

    @pyqtSlot()
    def grid_finish_autofoco(self):
        time.sleep(0.1)
        if self.shiftx != 0 or self.shifty != 0:
            pi.MOV([1, 2], [self.grid_x[self.i_global] + self.startX,
                            self.grid_y[self.i_global] + self.startY])
            time.sleep(0.1)
        down_flipper(); time.sleep(1)
        if self.mode_arg == "dimers":
            self._grid_center_scan()
        else:
            self._grid_trace()

    # ── Printing trace → detect ───────────────────────────────────────────────

    def _grid_trace(self):
        open_shutter(self.laser); time.sleep(0.01)
        self.timer_inicio = time.time()
        self.grid_traceSignal.emit(self.laser, self.mode_printing)

    @pyqtSlot(list)
    def grid_trace_detect(self, data: list):
        self.ptr      = data[0]
        self.timeaxis = data[1]
        self.data1    = data[2]
        I_old, I_new  = data[3], data[4]
        self.data_BS  = data[5]
        elapsed       = time.time() - self.timer_inicio

        if (I_new > I_old * self.umbral or
                I_new < I_old * self.umbral_down or
                elapsed > self.timemax):
            self.grid_trace_stopSignal.emit()
            close_shutter(self.laser)
            self.timer_real = round(elapsed, 2)
            self._save_trace()
            if self.mode_arg == "printing" and self.scanbool:
                self.grid_detectSignal.emit()
            else:
                self.grid_detectSignal.emit()

    @pyqtSlot()
    def grid_scan(self):
        if self.scanbool and self.mode_arg == "printing":
            up_flipper(); time.sleep(1)
            self.number_scan = "none"
            self.grid_scanSignal.emit(self.laser, self.mode_printing, self.number_scan)
        else:
            self._grid_detect()

    # ── Dimers center / pre / post scan ──────────────────────────────────────

    def _grid_center_scan(self):
        self.number_scan = "center_scan"
        self.grid_scanSignal.emit(self.laser, self.mode_printing, self.number_scan)

    # ── Slot central para scanfinishedSignal de Confocal ─────────────────────

    @pyqtSlot(np.ndarray, list, np.ndarray, np.ndarray, str, str)
    def on_scan_finished(self, image: np.ndarray, center_mass: list,
                          image_gone: np.ndarray, image_back: np.ndarray,
                          mode: str, number_scan: str):
        """
        Recibe la señal unificada de Confocal.Backend.scanfinishedSignal.
        Dispatcher según mode y number_scan.
        """
        if mode != self.mode_arg:
            return   # no nos corresponde

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

    # ── Detect (avanzar al siguiente punto) ──────────────────────────────────

    def _grid_detect(self):
        Nmax = self.particulas - 1
        print(f"[Meas] i_global = {self.i_global}")
        if self.i_global >= Nmax:
            self.file_path = self.old_folder
            self.namefolderSignal.emit(self.old_folder)
            self.indexSignal.emit(self.i_global + 1)
            print("[Meas] Fin de grilla.")
        else:
            self.i_global += 1
            self.indexSignal.emit(self.i_global)
            self._grid_move()

    @pyqtSlot()
    def grid_pause(self):
        try:
            close_shutter(self.laser)
            self.grid_trace_stopSignal.emit()
        except Exception:
            pass
        try:
            self.grid_scan_stopSignal.emit()
        except Exception:
            pass

    @pyqtSlot()
    def grid_next_index(self):
        self.i_global += 1
        self.indexSignal.emit(self.i_global)
        self._grid_move()

    @pyqtSlot(int)
    def grid_change_index(self, new_index: int):
        self.i_global = new_index

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
        name = os.path.join(self.new_folder, f"printing_error-{ts}.txt")
        np.savetxt(name, np.transpose([self.printing_error_x,
                                        self.printing_error_y]))

    @pyqtSlot(list)
    def grid_extra_info(self, info: list):
        name = os.path.join(self.new_folder, "Info.txt")
        np.savetxt(name, info, fmt="%s")

    def make_connection(self, frontend: Frontend):
        frontend.setreferenceSignal.connect(self.set_reference)
        frontend.goreferenceSignal.connect(self.go_reference)
        frontend.readgridSignal.connect(self.grid_read)
        frontend.gridcreateSignal.connect(self.grid_create)
        frontend.foldergridSignal.connect(self.grid_create_folder)
        frontend.parametersSignal.connect(self.grid_parameters)
        frontend.gridSignal.connect(self.grid_measurment)
        frontend.pauseSignal.connect(self.grid_pause)
        frontend.next_index_Signal.connect(self.grid_next_index)
        frontend.new_index_Signal.connect(self.grid_change_index)
        frontend.gridinfoSignal.connect(self.grid_extra_info)


# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    gui    = Frontend(mode="printing")
    worker = Backend(mode="printing")
    worker.make_connection(gui)
    gui.make_connection(worker)
    thread = QThread()
    worker.moveToThread(thread)
    thread.start()
    gui.show()
    sys.exit(app.exec())
