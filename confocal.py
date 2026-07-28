# -*- coding: utf-8 -*-
"""
confocal.py — Scan confocal láser (ramp/step), CM, drift
PyPrinting — UNSAM Nanofotónica  —  PyQt6

Funcionalidades (idénticas al original Confocal_pp.py):
  - Scan ramp: x/y, x/z, y/x, y/z
  - Scan step by step: x/y con espiral
  - Center of mass / gauss2D / two NP gauss
  - Go to NP1, go to NP2, CM auto
  - Drift measurement (timer periódico + guardado)
  - Save frame (scan + gone + back .tiff)
  - Señal scanfinishedSignal unificada (reemplaza las 4 señales paralelas)

Correcciones respecto al original:
  - isChecked() con paréntesis en todos los botones
  - pi importado desde config (singleton)
  - open_shutter/close_shutter desde nidaq (lógica de polaridad correcta)
  - scanfinishSignal unificada: emite (image, center_mass, image_gone,
    image_back, mode, number_scan) — los receptores discriminan por mode
  - Bug en scan_ramp_y_lin_configuration: pi_device.MOV('2', xo) → pi.MOV(2, xo)
"""
from __future__ import annotations
import os
import time
import numpy as np
from PIL import Image
from scipy import optimize

import pyqtgraph as pg
from PyQt6.QtCore    import Qt, QObject, QThread, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (QApplication, QFrame, QWidget, QGridLayout,
                              QHBoxLayout, QLabel, QLineEdit, QComboBox,
                              QPushButton, QCheckBox, QMessageBox)
from pyqtgraph.dockarea import DockArea, Dock

from config  import pi, SHUTTERS, DEFAULT_DATA_PATH
from nidaq   import (open_shutter, close_shutter, channels_photodiodos,
                     channels_triggers, PD_CHANNELS, PD_CHANS_LIST,
                     RATE_MULTICHANNEL)
from psf    import (center_of_mass, center_of_gauss2D,
                    find_two_centers, two_centers_of_gauss2D)
from spiral import to_spiral

SCAN_MODES    = ["Ramp", "Step by step"]
PSF_MODES     = ["x/y", "x/z", "y/x", "y/z"]
SCAN_IMAGE    = ["NPs maximum", "NPs minimum", "choose", "two NP: maximum-minimum"]
METHOD_CENTER = ["center of mass", "center of gauss", "two NP: center of gauss"]


# ══════════════════════════════════════════════════════════════════════════════
class Frontend(QFrame):

    startSignal          = pyqtSignal(int)         # color_laser index
    stopSignal           = pyqtSignal()
    parametersrampSignal = pyqtSignal(list)
    parametersstepSignal = pyqtSignal(list)
    scan_modeSignal      = pyqtSignal(str)
    psf_modeSignal       = pyqtSignal(str)
    image_scanSignal     = pyqtSignal(str)
    method_centerSignal  = pyqtSignal(str)
    CMSignal             = pyqtSignal()
    CMautoSignal         = pyqtSignal(bool)
    CMSignal_NP2         = pyqtSignal()
    driftSignal          = pyqtSignal(bool, int, float, float)
    saveSignal           = pyqtSignal()
    closeSignal          = pyqtSignal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._setup_gui()

    # ── Acciones ──────────────────────────────────────────────────────────────

    def _set_parameters(self):
        params = [float(self.scanrangeEdit.text()),
                  float(self.scanrangeEdit_y.text()),
                  int(self.NxEdit.text()),
                  int(self.NyEdit.text())]
        if self.scan_mode.currentText() == SCAN_MODES[0]:
            self.parametersrampSignal.emit(params)
        else:
            self.parametersstepSignal.emit(params)

    def _get_scan(self):
        self.point_graph_CM.hide()
        self.point_graph_CM_2.hide()
        self.startSignal.emit(self.scan_laser.currentIndex())

    def _get_scan_stop(self):
        self.stopSignal.emit()

    def _get_CM(self):       self.CMSignal.emit()
    def _get_CM_NP2(self):   self.CMSignal_NP2.emit()

    def _get_CM_auto(self):
        self.CMautoSignal.emit(self.CMcheck_auto.isChecked())

    def _set_scan_mode(self):
        self._set_parameters()
        self.scan_modeSignal.emit(self.scan_mode.currentText())

    def _set_psf_mode(self):
        self.psf_modeSignal.emit(self.PSF_mode.currentText())

    def _set_image_scan(self):
        self.image_scanSignal.emit(self.scan_image.currentText())

    def _set_method_center(self):
        self.method_centerSignal.emit(self.method_center.currentText())

    def _get_save(self):
        self.saveSignal.emit()

    def _get_drift(self):
        total   = float(self.drift_totaltime.text()) * 60
        refresh = float(self.drift_refreshtime.text())
        self.driftSignal.emit(
            self.driftButton.isChecked(),
            self.scan_laser.currentIndex(),
            total, refresh,
        )

    def _color_menu(self, combo: QComboBox):
        colors = ["color: green;", "color: red;", "color: #d4ac0d; font-weight: bold;", "color: blue;", "color: darkred;"]
        idx = combo.currentIndex()
        if 0 <= idx < len(colors):
            combo.setStyleSheet(f"QComboBox {{ {colors[idx]} }}")

    # ── GUI ───────────────────────────────────────────────────────────────────

    def _setup_gui(self):

        # ── Scan parameters ───────────────────────────────────────────────────
        self.scan_laser = QComboBox()
        self.scan_laser.addItems(SHUTTERS)
        self.scan_laser.setFixedWidth(100)
        self.scan_laser.currentIndexChanged.connect(
            lambda: self._color_menu(self.scan_laser))
        self._color_menu(self.scan_laser)

        self.scan_mode = QComboBox()
        self.scan_mode.addItems(SCAN_MODES)
        self.scan_mode.setFixedWidth(100)
        self.scan_mode.currentIndexChanged.connect(self._set_scan_mode)

        self.PSF_mode = QComboBox()
        self.PSF_mode.addItems(PSF_MODES)
        self.PSF_mode.setFixedWidth(100)
        self.PSF_mode.currentIndexChanged.connect(self._set_psf_mode)

        self.scanrangeEdit   = QLineEdit("2");  self.scanrangeEdit.textChanged.connect(self._set_parameters)
        self.scanrangeEdit_y = QLineEdit("2");  self.scanrangeEdit_y.textChanged.connect(self._set_parameters)
        self.NxEdit          = QLineEdit("34"); self.NxEdit.textChanged.connect(self._set_parameters)
        self.NyEdit          = QLineEdit("34"); self.NyEdit.textChanged.connect(self._set_parameters)
        self.NxEdit.setToolTip("Múltiplos de 16 por µm")

        self.scanButton     = QPushButton("Start Scan")
        self.scanButtonstop = QPushButton("Stop")
        self.saveimageButton = QPushButton("Save Frame")
        self.saveimageButton.setStyleSheet("QPushButton { background-color: rgb(200,200,10); }")
        self.saveimageButton.setFixedWidth(110)

        self.scanButton.clicked.connect(self._get_scan)
        self.scanButtonstop.clicked.connect(self._get_scan_stop)
        self.saveimageButton.clicked.connect(self._get_save)

        paramWidget = QWidget()
        sg = QGridLayout(paramWidget)
        sg.addWidget(self.scan_laser,      1, 1)
        sg.addWidget(self.scan_mode,       1, 2)
        sg.addWidget(self.PSF_mode,        2, 2)
        sg.addWidget(QLabel("Range x (µm)"),  3, 1); sg.addWidget(self.scanrangeEdit,   3, 2)
        sg.addWidget(QLabel("Range y (µm)"),  4, 1); sg.addWidget(self.scanrangeEdit_y, 4, 2)
        sg.addWidget(QLabel("Pixels x"),      5, 1); sg.addWidget(self.NxEdit,          5, 2)
        sg.addWidget(QLabel("Pixels y"),      6, 1); sg.addWidget(self.NyEdit,          6, 2)
        sg.addWidget(self.scanButton,      7, 1)
        sg.addWidget(self.scanButtonstop,  7, 2)
        sg.addWidget(self.saveimageButton, 8, 2)

        # ── CM widget ─────────────────────────────────────────────────────────
        self.CMcheck     = QPushButton("Go to NP1")
        self.CMcheck_NP2 = QPushButton("Go to NP2")
        self.CMcheck_auto = QCheckBox("Auto CM")
        self.scan_image   = QComboBox(); self.scan_image.addItems(SCAN_IMAGE);   self.scan_image.setFixedWidth(150)
        self.method_center= QComboBox(); self.method_center.addItems(METHOD_CENTER); self.method_center.setFixedWidth(150)
        self.CxValue_1 = QLabel("NaN"); self.CyValue_1 = QLabel("NaN")
        self.CxValue_2 = QLabel("NaN"); self.CyValue_2 = QLabel("NaN")

        self.CMcheck.clicked.connect(self._get_CM)
        self.CMcheck_NP2.clicked.connect(self._get_CM_NP2)
        self.CMcheck_auto.clicked.connect(self._get_CM_auto)
        self.scan_image.currentIndexChanged.connect(self._set_image_scan)
        self.method_center.currentIndexChanged.connect(self._set_method_center)

        self.point_graph_CM   = pg.ScatterPlotItem(size=10, symbol="+", pen="m")
        self.point_graph_CM_2 = pg.ScatterPlotItem(size=5,  symbol="+", pen="b")

        goCMWidget = QWidget()
        lo3 = QGridLayout(goCMWidget)
        lo3.addWidget(self.CMcheck,       1, 1); lo3.addWidget(self.CMcheck_auto, 1, 2)
        lo3.addWidget(self.CMcheck_NP2,   1, 3)
        lo3.addWidget(self.scan_image,    2, 1); lo3.addWidget(self.method_center, 2, 2)
        lo3.addWidget(QLabel("NP 1:"),    3, 2); lo3.addWidget(QLabel("NP 2:"),    3, 3)
        lo3.addWidget(QLabel("Cx:"),      4, 1); lo3.addWidget(self.CxValue_1,    4, 2); lo3.addWidget(self.CxValue_2, 4, 3)
        lo3.addWidget(QLabel("Cy:"),      5, 1); lo3.addWidget(self.CyValue_1,    5, 2); lo3.addWidget(self.CyValue_2, 5, 3)

        # ── Drift widget ──────────────────────────────────────────────────────
        self.driftButton       = QPushButton("DRIFT measurement / stop")
        self.driftButton.setCheckable(True)
        self.driftButton.clicked.connect(self._get_drift)
        self.driftButton.setToolTip("Modo ramp, PSF x/y")
        self.drift_totaltime   = QLineEdit("20")
        self.drift_refreshtime = QLineEdit("40")
        self.drift_widget      = pg.GraphicsLayoutWidget()

        driftWidget = QWidget()
        lo4 = QGridLayout(driftWidget)
        lo4.addWidget(self.driftButton,        1, 1)
        lo4.addWidget(QLabel("Total (min):"),  2, 1); lo4.addWidget(self.drift_totaltime,   2, 2)
        lo4.addWidget(QLabel("Refresh (s):"),  3, 1); lo4.addWidget(self.drift_refreshtime, 3, 2)

        # ── Image viewbox ─────────────────────────────────────────────────────
        imageWidget = pg.GraphicsLayoutWidget()
        imageWidget.setAspectLocked(True)
        self.img  = pg.ImageItem()
        self.xlabel = pg.AxisItem(orientation="left")
        self.ylabel = pg.AxisItem(orientation="bottom")
        labelStyle  = {"color": "#FFF", "font-size": "8pt"}
        self.xlabel.setLabel("X", units="um", **labelStyle)
        self.ylabel.setLabel("Y", units="um", **labelStyle)
        px0 = round(2/34, 3)
        self.xlabel.setScale(scale=px0); self.ylabel.setScale(scale=px0)
        self.vb = imageWidget.addPlot(axisItems={"bottom": self.ylabel, "left": self.xlabel})
        self.vb.addItem(self.img)
        self.vb.invertY(); self.vb.setAspectLocked(True)
        self.hist = pg.HistogramLUTItem(image=self.img)
        self.hist.gradient.loadPreset("thermal")
        for tick in self.hist.gradient.ticks:
            tick.hide()
        imageWidget.addItem(self.hist, row=0, col=1)

        # ── Docks ─────────────────────────────────────────────────────────────
        hbox      = QHBoxLayout(self)
        dock_area = DockArea()

        viewDock = Dock("Viewbox", size=(100, 100))
        viewDock.addWidget(imageWidget); viewDock.hideTitleBar()
        dock_area.addDock(viewDock)

        scanDock = Dock("Confocal parameters")
        scanDock.addWidget(paramWidget)
        dock_area.addDock(scanDock, "right", viewDock)

        goCMDock = Dock("CM")
        goCMDock.addWidget(goCMWidget)
        dock_area.addDock(goCMDock, "right", scanDock)

        driftDock = Dock("Drift measurement")
        driftDock.addWidget(driftWidget)
        dock_area.addDock(driftDock, "bottom", goCMDock)

        hbox.addWidget(dock_area)
        self.setLayout(hbox)

    # ── Slots desde Backend ───────────────────────────────────────────────────

    @pyqtSlot(float, float)
    def get_view_scale(self, px: float, py: float):
        self.xlabel.setScale(scale=px)
        self.ylabel.setScale(scale=py)

    @pyqtSlot(np.ndarray)
    def get_img(self, data_img: np.ndarray):
        self.img.setImage(data_img)

    @pyqtSlot(list)
    def get_CMValues(self, data: list):
        self.CxValue_1.setText(str(data[0]))
        self.CyValue_1.setText(str(data[1]))
        self.point_graph_CM.setData([data[3]], [data[2]])
        self.point_graph_CM.show()
        self.vb.addItem(self.point_graph_CM)

    @pyqtSlot(list)
    def get_CMValues_NP2(self, data: list):
        self.CxValue_2.setText(str(data[0]))
        self.CyValue_2.setText(str(data[1]))
        self.point_graph_CM_2.setData([data[3]], [data[2]])
        self.point_graph_CM_2.show()
        self.vb.addItem(self.point_graph_CM_2)

    @pyqtSlot(list)
    def plot_drift(self, drift: list):
        self.drift_widget.clear()
        p = self.drift_widget.addPlot(title="Drift x, y")
        p.showGrid(x=True, y=True)
        p.setLabel("left", "Position CM"); p.setLabel("bottom", "Time (s)")
        p.plot(drift[0], drift[1], pen=pg.mkPen("r", width=1), symbol="o")
        p.plot(drift[0], drift[2], pen=pg.mkPen("b", width=1), symbol="o")
        self.drift_widget.show()

    def closeEvent(self, event):
        reply = QMessageBox.question(
            self, "Salir", "¿Cerrar Confocal?",
            QMessageBox.StandardButton.No | QMessageBox.StandardButton.Yes)
        if reply == QMessageBox.StandardButton.Yes:
            self.closeSignal.emit(); event.accept()
        else:
            event.ignore()

    def make_connection(self, backend: Backend):
        backend.scaleSignal.connect(self.get_view_scale)
        backend.dataSignal.connect(self.get_img)
        backend.CMValuesSignal.connect(self.get_CMValues)
        backend.CMValuesSignal_NP2.connect(self.get_CMValues_NP2)
        backend.plotdriftSignal.connect(self.plot_drift)


# ══════════════════════════════════════════════════════════════════════════════
class Backend(QObject):

    scaleSignal         = pyqtSignal(float, float)
    dataSignal          = pyqtSignal(np.ndarray)
    CMValuesSignal      = pyqtSignal(list)
    CMValuesSignal_NP2  = pyqtSignal(list)
    scandoneSignal      = pyqtSignal()
    plotdriftSignal     = pyqtSignal(list)

    # Señal unificada: (image, center_mass, image_gone, image_back, mode, number_scan)
    # center_mass = [] para scans sin CM (pree, post)
    scanfinishedSignal  = pyqtSignal(np.ndarray, list, np.ndarray, np.ndarray, str, str)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        pi.connect()
        self.file_path         = str(DEFAULT_DATA_PATH)
        self.scan_mode_option  = SCAN_MODES[0]
        self.psf_mode_option   = PSF_MODES[0]
        self.image_scan_option = SCAN_IMAGE[0]
        self.method_center_opt = METHOD_CENTER[0]
        self.cm_auto           = False
        self.mode_printing     = "none"
        self.number_scan       = "none"
        self.signal_scan_stop  = False

        self.PDtimer_stepxy = QTimer(self); self.PDtimer_stepxy.timeout.connect(self._scan_step_xy)
        self.PDtimer_rampxy = QTimer(self); self.PDtimer_rampxy.timeout.connect(self._scan_ramp_xy)
        self.PDtimer_rampxz = QTimer(self); self.PDtimer_rampxz.timeout.connect(self._scan_ramp_xz)
        self.PDtimer_rampyx = QTimer(self); self.PDtimer_rampyx.timeout.connect(self._scan_ramp_yx)
        self.PDtimer_rampyz = QTimer(self); self.PDtimer_rampyz.timeout.connect(self._scan_ramp_yz)
        self.drifttimer     = QTimer(self); self.drifttimer.timeout.connect(self._drift_tick)

        self._scan_ramp_parameters([2, 2, 34, 34])
        # Inicializar posición para evitar AttributeError en stop_scan
        # si se llama antes del primer scan
        try:
            self.x_pos, self.y_pos, self.z_pos = self._read_pos()
        except Exception:
            self.x_pos = self.y_pos = 50.0
            self.z_pos = 10.0

    # ── Slots de configuración ────────────────────────────────────────────────

    @pyqtSlot(str)
    def scan_mode(self, v: str):      self.scan_mode_option = v

    @pyqtSlot(str)
    def psf_mode(self, v: str):       self.psf_mode_option = v

    @pyqtSlot(str)
    def image_scan(self, v: str):     self.image_scan_option = v

    @pyqtSlot(str)
    def method_center(self, v: str):  self.method_center_opt = v

    @pyqtSlot(list)
    def scan_ramp_parameters(self, p: list):
        self._scan_ramp_parameters(p)

    @pyqtSlot(list)
    def scan_step_parameters(self, p: list):
        self._scan_step_parameters(p)

    def _scan_ramp_parameters(self, p: list):
        self.range_x, self.range_y, self.Nx, self.Ny = p[0], p[1], int(p[2]), int(p[3])
        self.extra         = self.range_x / 6
        self.range_total   = self.range_x + 2 * self.extra
        self.extra_y       = self.range_y / 6
        self.range_total_y = self.range_y + 2 * self.extra_y
        self.frequency     = RATE_MULTICHANNEL / 100
        factor_ramp        = 1 / 1200
        self.frequency_ramp = factor_ramp * RATE_MULTICHANNEL / 100
        self.tau            = 1 / self.frequency_ramp
        self.Nramp          = 2 * int(self.frequency / self.frequency_ramp)
        self.scaleSignal.emit(round(self.range_x / self.Nx, 3),
                              round(self.range_y / self.Ny, 3))

    def _scan_step_parameters(self, p: list):
        self.range_x, self.range_y, self.Nx, self.Ny = p[0], p[1], int(p[2]), int(p[3])
        self.Nph  = 10
        self.rate = RATE_MULTICHANNEL / 10
        self.scaleSignal.emit(round(self.range_x / self.Nx, 3),
                              round(self.range_y / self.Ny, 3))

    # ── Inicio / parada de scan ───────────────────────────────────────────────

    @pyqtSlot(int)
    def start_scan_button(self, color_laser: int):
        self.mode_printing = "none"
        self.number_scan   = "none"
        self.laser         = SHUTTERS[color_laser]
        self._start_scan()

    @pyqtSlot(str, str, str)
    def start_scan_routines(self, laser: str, mode_printing: str, number_scan: str):
        self.mode_printing = mode_printing
        self.number_scan   = number_scan
        self.laser         = laser
        self._start_scan()

    def _start_scan(self):
        self.signal_scan_stop = False
        self.image      = np.zeros((self.Ny, self.Nx))
        self.image_gone = np.zeros((self.Ny, self.Nx))
        self.image_back = np.zeros((self.Ny, self.Nx))
        if self.scan_mode_option == SCAN_MODES[0]:
            dispatch = {PSF_MODES[0]: self._start_ramp_xy,
                        PSF_MODES[1]: self._start_ramp_xz,
                        PSF_MODES[2]: self._start_ramp_yx,
                        PSF_MODES[3]: self._start_ramp_yz}
            dispatch.get(self.psf_mode_option, lambda: None)()
        else:
            self._start_step()

    @pyqtSlot()
    def stop_scan(self):
        if not self.signal_scan_stop:
            close_shutter(self.laser)
        xp = getattr(self, "x_pos", 50.0)
        yp = getattr(self, "y_pos", 50.0)
        zp = getattr(self, "z_pos", 10.0)
        timers = {
            (SCAN_MODES[0], PSF_MODES[0]): (self.PDtimer_rampxy, [1, 2], [xp, yp]),
            (SCAN_MODES[0], PSF_MODES[1]): (self.PDtimer_rampxz, [1, 3], [xp, zp]),
            (SCAN_MODES[0], PSF_MODES[2]): (self.PDtimer_rampyx, [2, 1], [yp, xp]),
            (SCAN_MODES[0], PSF_MODES[3]): (self.PDtimer_rampyz, [2, 3], [yp, zp]),
            (SCAN_MODES[1], PSF_MODES[0]): (self.PDtimer_stepxy, [1, 2], [xp, yp]),
        }
        key = (self.scan_mode_option, self.psf_mode_option)
        if key in timers:
            timer, axes, targets = timers[key]
            timer.stop()
            if self.mode_printing == "none":
                pi.MOV(axes, targets)

    # ── Scan step ─────────────────────────────────────────────────────────────

    def _start_step(self):
        self.tic = time.time(); self.i = self.j = 0
        self.x_pos, self.y_pos, self.z_pos = self._read_pos()
        dx = self.range_x / self.Nx; dy = self.range_y / self.Ny
        xs = np.arange(self.x_pos - self.range_x/2 + dx/2, self.x_pos + self.range_x/2, dx)
        ys = np.arange(self.y_pos - self.range_y/2 + dy/2, self.y_pos + self.range_y/2, dy)
        self.matrix_scan_step   = [xs, ys]
        self.matrix_scan_spiral = to_spiral([xs, ys], "cw")
        open_shutter(self.laser); time.sleep(0.05)
        self.PDtimer_stepxy.start(0)

    def _scan_step_xy(self):
        if self.j < self.Ny:
            if self.i < self.Nx:
                pi.MOV([1, 2], [self.matrix_scan_step[0][self.i],
                                self.matrix_scan_step[1][self.j]])
                task = channels_photodiodos(self.rate, self.Nph)
                raw  = task.read(self.Nph); task.wait_until_done(); task.close()
                self.image[self.j, self.i] = np.mean(raw[PD_CHANS_LIST.index(PD_CHANNELS[self.laser])])
                self.dataSignal.emit(self.image); self.i += 1
            else:
                self.i = 0; self.j += 1
        else:
            self.PDtimer_stepxy.stop()
            self.signal_scan_stop = True
            close_shutter(self.laser)
            time.sleep(0.1)
            x_o, y_o = self._CMmeasure()
            print(f"[Confocal] Step scan done {round(time.time()-self.tic,2)}s")
            self._post_scan_dispatch(x_o, y_o)

    # ── Scan ramp helpers ─────────────────────────────────────────────────────

    def _read_pos(self):
        pos = pi.qPOS()
        return pos["1"], pos["2"], pos["3"]

    def _start_ramp_xy(self):
        self.tic = time.time(); self.i = 0
        self.x_pos, self.y_pos, self.z_pos = self._read_pos()
        self._configure_ramp_x(self.x_pos)
        open_shutter(self.laser)
        self.PDtimer_rampxy.start(0)

    def _start_ramp_xz(self):
        self.tic = time.time(); self.i = 0
        self.x_pos, self.y_pos, self.z_pos = self._read_pos()
        self._configure_ramp_x(self.x_pos)
        open_shutter(self.laser)
        self.PDtimer_rampxz.start(0)

    def _start_ramp_yx(self):
        self.tic = time.time(); self.i = 0
        self.x_pos, self.y_pos, self.z_pos = self._read_pos()
        self._configure_ramp_y(self.y_pos)
        open_shutter(self.laser)
        self.PDtimer_rampyx.start(0)

    def _start_ramp_yz(self):
        self.tic = time.time(); self.i = 0
        self.x_pos, self.y_pos, self.z_pos = self._read_pos()
        self._configure_ramp_y(self.y_pos)
        open_shutter(self.laser)
        self.PDtimer_rampyz.start(0)

    def _configure_ramp_x(self, x_pos: float):
        sp       = self.range_x / self.Nx
        Npoints  = int(self.range_total / sp) * 20
        Nspeed   = int(Npoints / 4)
        from config import PI_SERVO_TIME
        WTRtime  = int(1 / (self.frequency_ramp * PI_SERVO_TIME * Npoints))
        pi.WTR(0, WTRtime, 0)
        pi.WAV_LIN(1, 0, Npoints, "X",  Nspeed,  self.range_total, 0, Npoints)
        pi.WAV_LIN(1, 0, Npoints, "&",  Nspeed, -self.range_total, self.range_total, Npoints)
        pi.WSL(1, 1); pi.WGC(1, 1)
        xo = x_pos - self.range_total / 2
        pi.MOV(1, xo); pi.WOS(1, xo)
        pi.TWC(); pi.CTO(1, 3, 3)
        pi.CTO(1, 5, xo + self.extra)
        pi.CTO(1, 6, xo + self.range_total - self.extra)

    def _configure_ramp_y(self, y_pos: float):
        sp       = self.range_y / self.Ny
        Npoints  = int(self.range_total_y / sp) * 20
        Nspeed   = int(Npoints / 4)
        from config import PI_SERVO_TIME
        WTRtime  = int(1 / (self.frequency_ramp * PI_SERVO_TIME * Npoints))
        pi.WTR(0, WTRtime, 0)
        pi.WAV_LIN(2, 0, Npoints, "X",  Nspeed,  self.range_total_y, 0,                  Npoints)
        pi.WAV_LIN(2, 0, Npoints, "&",  Nspeed, -self.range_total_y, self.range_total_y,  Npoints)
        pi.WSL(2, 2); pi.WGC(2, 1)
        yo = y_pos - self.range_total_y / 2
        pi.MOV(2, yo); pi.WOS(2, yo)   # bug original: pi_device.MOV('2', xo) → corregido
        pi.TWC(); pi.CTO(2, 3, 3)
        pi.CTO(2, 5, yo + self.extra_y)
        pi.CTO(2, 6, yo + self.range_total_y - self.extra_y)

    def _ramp_x_line(self):
        task = channels_photodiodos(self.frequency, self.Nramp)
        channels_triggers(task, "X")
        pi.WGO(1, 1)
        data = task.read(self.Nramp); task.close()
        ph      = np.array(data[PD_CHANS_LIST.index(PD_CHANNELS[self.laser])])
        trigger = np.array(data[len(PD_CHANS_LIST)])
        return self._profiles(ph, trigger)

    def _ramp_y_line(self):
        task = channels_photodiodos(self.frequency, self.Nramp)
        channels_triggers(task, "Y")
        pi.WGO(2, 1)
        data = task.read(self.Nramp); task.close()
        ph      = np.array(data[PD_CHANS_LIST.index(PD_CHANNELS[self.laser])])
        trigger = np.array(data[len(PD_CHANS_LIST)])
        return self._profiles(ph, trigger)

    def _profiles(self, ph, trig):
        d    = np.diff(trig); L = len(trig)
        asc  = np.where(d >= 1.5)[0]; dsc = np.where(d <= -1.5)[0]
        if not len(asc) or not len(dsc):
            return np.zeros(self.Nx), np.zeros(self.Nx)
        fa = asc[0]
        d2 = np.where(asc > fa + L/3)[0]
        sa = asc[d2[0]] if len(d2) else fa
        fd_i = np.where(dsc > fa + L/6)[0]
        fd   = dsc[fd_i[0]] if len(fd_i) else fa
        d3   = np.where(dsc > fd + L/3)[0]
        sd   = dsc[d3[0]] if len(d3) else fd
        return ph[fa:fd], ph[sa:sd]

    # ── Scan ramp loops ───────────────────────────────────────────────────────

    def _scan_ramp_xy(self):
        dy = self.range_y / self.Ny
        if self.i < self.Ny:
            pi.MOV(2, self.y_pos - self.range_y/2 + dy/2 + self.i*dy)
            gone, back = self._ramp_x_line()
            self.image_gone[self.i, :] = _average(gone, self.Nx)
            self.image_back[self.i, :] = _average(back, self.Nx)
            self.image = self.image_gone + np.fliplr(self.image_back)
            self.dataSignal.emit(self.image); self.i += 1
        else:
            self.PDtimer_rampxy.stop(); self.signal_scan_stop = True
            close_shutter(self.laser)
            self.image_back = np.fliplr(self.image_back)
            self.image = self.image_gone + self.image_back
            time.sleep(0.1)
            x_o, y_o = self._CMmeasure()
            print(f"[Confocal] Ramp x/y done {round(time.time()-self.tic,2)}s")
            self._post_scan_dispatch(x_o, y_o)

    def _scan_ramp_xz(self):
        dz = self.range_y / self.Ny
        if self.i < self.Ny:
            pi.MOV(3, self.z_pos - self.range_y/2 + dz/2 + self.i*dz)
            gone, back = self._ramp_x_line()
            self.image_gone[self.i, :] = _average(gone, self.Nx)
            self.image_back[self.i, :] = _average(back, self.Nx)
            self.image = self.image_gone + np.fliplr(self.image_back)
            self.dataSignal.emit(self.image); self.i += 1
        else:
            self.PDtimer_rampxz.stop(); self.signal_scan_stop = True
            close_shutter(self.laser); time.sleep(0.1)
            self.image_back = np.fliplr(self.image_back)
            self.image = self.image_gone + self.image_back
            pi.MOV([1, 3], [self.x_pos, self.z_pos])
            self._save_frame(); self.scandoneSignal.emit()

    def _scan_ramp_yx(self):
        dx = self.range_x / self.Nx
        if self.i < self.Nx:
            pi.MOV(1, self.x_pos - self.range_x/2 + dx/2 + self.i*dx)
            gone, back = self._ramp_y_line()
            self.image_gone[:, self.i] = _average(gone, self.Ny)
            self.image_back[:, self.i] = _average(back, self.Ny)
            self.image = self.image_gone + np.flipud(self.image_back)
            self.dataSignal.emit(self.image); self.i += 1
        else:
            self.PDtimer_rampyx.stop(); self.signal_scan_stop = True
            close_shutter(self.laser); time.sleep(0.1)
            self.image_back = np.flipud(self.image_back)
            self.image = self.image_gone + self.image_back
            x_o, y_o = self._CMmeasure()
            self._post_scan_dispatch(x_o, y_o)

    def _scan_ramp_yz(self):
        dz = self.range_x / self.Nx
        if self.i < self.Nx:
            pi.MOV(3, self.z_pos - self.range_x/2 + dz/2 + self.i*dz)
            gone, back = self._ramp_y_line()
            self.image_gone[self.i, :] = _average(gone, self.Ny)
            self.image_back[self.i, :] = _average(back, self.Ny)
            self.image = self.image_gone + np.fliplr(self.image_back)
            self.dataSignal.emit(self.image); self.i += 1
        else:
            self.PDtimer_rampyz.stop(); self.signal_scan_stop = True
            close_shutter(self.laser); time.sleep(0.1)
            self.image_back = np.fliplr(self.image_back)
            self.image = self.image_gone + self.image_back
            pi.MOV([2, 3], [self.y_pos, self.z_pos])
            self._save_frame(); self.scandoneSignal.emit()

    # ── Post-scan dispatch ────────────────────────────────────────────────────

    def _post_scan_dispatch(self, x_o: float, y_o: float):
        center_mass = [x_o, y_o]
        if self.mode_printing == "none":
            self._save_frame()
            if self.cm_auto:
                self._moveto(x_o, y_o)
            else:
                pi.MOV([1, 2], [self.x_pos, self.y_pos])
            self.scandoneSignal.emit()
        elif self.mode_printing == "drift":
            self._save_frame_drift()
            self.x_cm_drift.append(x_o); self.y_cm_drift.append(y_o)
            pi.MOV([1, 2], [self.x_pos, self.y_pos])
            self.scandoneSignal.emit()
        else:
            self.scanfinishedSignal.emit(
                self.image, center_mass,
                self.image_gone, self.image_back,
                self.mode_printing, self.number_scan,
            )

    # ── CM ────────────────────────────────────────────────────────────────────

    def _CMmeasure(self) -> tuple[float, float]:
        Z  = self.image
        Zn = self._norm_image(Z)
        Zf = self._filter_image(Z, Zn, 0.3)
        if self.method_center_opt == METHOD_CENTER[0]:
            xo, yo = center_of_mass(Zf)
        elif self.method_center_opt == METHOD_CENTER[1]:
            xo, yo = center_of_mass(Zf)
            xo, yo = center_of_gauss2D(Zn, xo, yo)
        else:
            xo1, yo1, xo2, yo2 = find_two_centers(Zf)
            xo, yo, xo2, yo2   = two_centers_of_gauss2D(Zn, xo1, yo1, xo2, yo2)
            xo2_um, yo2_um = self._coords(xo2, yo2)
            self._xo2_um = xo2_um; self._yo2_um = yo2_um
            self.CMValuesSignal_NP2.emit([xo2_um, yo2_um, xo2, yo2])

        xo_um, yo_um = self._coords(xo, yo)
        self.CMValuesSignal.emit([xo_um, yo_um, xo, yo])
        return xo_um, yo_um

    def _norm_image(self, Z: np.ndarray) -> np.ndarray:
        Zmin, Zmax = Z.min(), Z.max()
        Zn = (Z - Zmin) / (Zmax - Zmin + 1e-12)
        if self.image_scan_option == SCAN_IMAGE[1]:
            Zn = np.abs(Zn - 1)
        elif self.image_scan_option == SCAN_IMAGE[2]:
            if np.mean(Z) > 0.3 * Zmax:
                Zn = np.abs(Zn - 1)
        elif self.image_scan_option == SCAN_IMAGE[3]:
            bkg = np.mean(Z)
            Zn  = np.abs((Z - bkg) / (Zmax - bkg + 1e-12))
        return Zn

    def _filter_image(self, Z, Zn, thr):
        Zf = Zn.copy()
        Zf[Zf < thr] = 0
        return Zf

    def _coords(self, xo: float, yo: float) -> tuple[float, float]:
        dx = self.range_x / self.Nx; dy = self.range_y / self.Ny
        return (round(self.x_pos - self.range_x/2 + dx/2 + xo*dx, 3),
                round(self.y_pos - self.range_y/2 + dy/2 + yo*dy, 3))

    @pyqtSlot()
    def goCM(self):
        xo, yo = self._CMmeasure()
        self._moveto(xo, yo); self.scandoneSignal.emit()

    @pyqtSlot(bool)
    def goCM_auto(self, v: bool):
        self.cm_auto = v

    @pyqtSlot()
    def goCM_NP2(self):
        self._moveto(self._xo2_um, self._yo2_um)
        self.scandoneSignal.emit()

    def _moveto(self, x: float, y: float):
        pi.MOV([1, 2], [x, y])
        while not all(pi.qONT([1, 2]).values()):
            time.sleep(0.01)

    # ── Guardado ──────────────────────────────────────────────────────────────

    @pyqtSlot(str)
    def direction(self, path: str):
        self.file_path = path

    @pyqtSlot()
    def saveFrame(self):
        self._save_frame()

    def _save_frame(self):
        ts = time.strftime("%Y%m%d-%H%M%S")
        for suffix, arr in [("scan", self.image),
                             ("image_gone", self.image_gone),
                             ("image_back", self.image_back)]:
            name = os.path.join(self.file_path, f"{suffix}_{ts}.tiff")
            Image.fromarray(np.transpose(arr)).save(name)
        print("[Confocal] Scan guardado.")

    def _save_frame_drift(self):
        ts = str(round(float(time.strftime("%M")) + float(time.strftime("%S"))/60, 2))
        folder = os.path.join(self.file_path, "Drift")
        for suffix, arr in [("scan_minute", self.image),
                             ("image_gone_minute", self.image_gone),
                             ("image_back_minute", self.image_back)]:
            name = os.path.join(folder, f"{suffix}_{ts}.tiff")
            Image.fromarray(np.transpose(arr)).save(name)

    # ── Drift ─────────────────────────────────────────────────────────────────

    @pyqtSlot(bool, int, float, float)
    def measurment_drift(self, play: bool, color_laser: int,
                         time_total: float, time_refresh: float):
        self.laser = SHUTTERS[color_laser]
        if play:
            self._play_drift(time_total, time_refresh)
        else:
            self._stop_drift()

    def _play_drift(self, time_total: float, time_refresh: float):
        folder = os.path.join(self.file_path, "Drift")
        os.makedirs(folder, exist_ok=True)
        self._time_inicial = time.time()
        self._n_drift      = 0
        self._N_drift      = int(time_total / time_refresh)
        self.x_cm_drift    = []; self.y_cm_drift = []; self.time = []
        self.start_scan_routines(self.laser, "drift", "none")
        self.time.append(round(time.time() - self._time_inicial, 2))
        self.drifttimer.start(int(time_refresh * 1000))

    def _stop_drift(self):
        self.drifttimer.stop()
        self.plotdriftSignal.emit([self.time, self.x_cm_drift, self.y_cm_drift])
        name = os.path.join(self.file_path, "Drift",
                            time.strftime("%Y%m%d-%H%M%S") + "_Drift.txt")
        np.savetxt(name, np.transpose([self.time, self.x_cm_drift, self.y_cm_drift]))
        self.mode_printing = "none"

    def _drift_tick(self):
        if self._n_drift < self._N_drift - 1:
            self._n_drift += 1
            self.start_scan_routines(self.laser, "drift", "none")
            self.time.append(round(time.time() - self._time_inicial, 2))
            self.plotdriftSignal.emit([self.time, self.x_cm_drift, self.y_cm_drift])
        else:
            self._stop_drift()

    @pyqtSlot()
    def close(self):
        """Detiene todos los timers activos al cerrar la ventana."""
        for t in (self.PDtimer_stepxy, self.PDtimer_rampxy,
                  self.PDtimer_rampxz, self.PDtimer_rampyx,
                  self.PDtimer_rampyz, self.drifttimer):
            t.stop()
        try:
            close_shutter(getattr(self, "laser", SHUTTERS[0]))
        except Exception:
            pass

    def make_connection(self, frontend: Frontend):
        frontend.scan_modeSignal.connect(self.scan_mode)
        frontend.psf_modeSignal.connect(self.psf_mode)
        frontend.startSignal.connect(self.start_scan_button)
        frontend.stopSignal.connect(self.stop_scan)
        frontend.parametersrampSignal.connect(self.scan_ramp_parameters)
        frontend.parametersstepSignal.connect(self.scan_step_parameters)
        frontend.image_scanSignal.connect(self.image_scan)
        frontend.method_centerSignal.connect(self.method_center)
        frontend.CMSignal.connect(self.goCM)
        frontend.CMautoSignal.connect(self.goCM_auto)
        frontend.CMSignal_NP2.connect(self.goCM_NP2)
        frontend.driftSignal.connect(self.measurment_drift)
        frontend.saveSignal.connect(self.saveFrame)
        frontend.closeSignal.connect(self.close)


# ── Helper ────────────────────────────────────────────────────────────────────

def _average(arr: np.ndarray, n: int) -> np.ndarray:
    if n <= 0 or len(arr) == 0:
        return np.zeros(n)
    end = (len(arr) // n) * n
    return np.mean(arr[:end].reshape(-1, n), axis=1) if end > 0 else np.zeros(n)


# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    gui    = Frontend()
    worker = Backend()
    worker.make_connection(gui)
    gui.make_connection(worker)
    thread = QThread()
    worker.moveToThread(thread)
    thread.start()
    gui.show()
    sys.exit(app.exec())
