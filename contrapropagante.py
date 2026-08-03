# -*- coding: utf-8 -*-
"""
contrapropagante.py — Suite del Microscopio Contrapropagante (Excitación Dual)
PyPrinting 3.0 — UNSAM Nanofotónica — PyQt6

Permite la iluminación simultánea por arriba (Derecho) y por abajo (Invertido),
adquiriendo dos confocales en paralelo (Confocal TOP y Confocal BOT) con el mismo
movimiento de la platina piezoeléctrica PI.

Layout Horizontal:
  [ DISPLAY CONFOCAL TOP (Izquierda) ] | [ CONTROLES COMPARTIDOS (Centro) ] | [ DISPLAY CONFOCAL BOT (Derecha) ]
"""
from __future__ import annotations

import os
import sys
import time
import math
import numpy as np
from PIL import Image
from scipy import optimize

import pyqtgraph as pg
from PyQt6.QtCore import Qt, QObject, QThread, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QFrame, QGridLayout,
                             QHBoxLayout, QVBoxLayout, QLabel, QLineEdit, QComboBox,
                             QPushButton, QCheckBox, QMessageBox, QSlider, QGroupBox)
from PyQt6.QtGui import QAction, QKeySequence, QFont, QColor
from pyqtgraph.dockarea import DockArea, Dock

from config import (pi, SHUTTERS, DEFAULT_DATA_PATH, LAST_POS_FILE, SAFE_MODE,
                    DEFAULT_CONFOCAL_RANGE_X, DEFAULT_CONFOCAL_RANGE_Y,
                    DEFAULT_CONFOCAL_PIXELS_X, DEFAULT_CONFOCAL_PIXELS_Y,
                    DEFAULT_CONFOCAL_FILTER_PERCENT, PI_SERVO_TIME)
from nidaq import (open_shutter, close_shutter, channels_photodiodos,
                   channels_triggers, PD_CHANS_LIST, RATE_MULTICHANNEL)
from psf import (center_of_mass, center_of_gauss2D, center_of_donut2D)
from nanopositioning import Frontend as NanoFrontend, Backend as NanoBackend
from shutters import Frontend as ShuttersFrontend, Backend as ShuttersBackend
from focus import Frontend as FocusFrontend, Backend as FocusBackend
from trace import Frontend as TraceFrontend, Backend as TraceBackend
from measurements import Frontend as MeasFrontend, Backend as MeasBackend
from camera import (CameraWindow, Backend as CameraBackend,
                    Laser532Window, Laser532Backend)
from image_analyzer import ImageAnalyzerWindow
from psf_analyzer import PSFAnalyzerWindow

SCAN_MODES = ["Ramp", "Step by step"]
PSF_MODES = ["x/y", "x/z", "y/x", "y/z"]
SCAN_IMAGE = ["NPs maximum", "NPs minimum"]
METHOD_CENTER = ["center of mass", "center of gauss", "donut (Laguerre-Gauss)"]


# ══════════════════════════════════════════════════════════════════════════════
#  FRONTEND: INTERFAZ DEL MICROSCOPIO CONTRAPROPAGANTE
# ══════════════════════════════════════════════════════════════════════════════

class ConfocalDualFrontend(QWidget):

    startSignal = pyqtSignal(int, int)   # (laser_top_idx, laser_bot_idx)
    stopSignal = pyqtSignal()
    parametersrampSignal = pyqtSignal(list)
    parametersstepSignal = pyqtSignal(list)
    scan_modeSignal = pyqtSignal(str)
    psf_modeSignal = pyqtSignal(str)
    image_scanSignal = pyqtSignal(str)
    method_centerSignal = pyqtSignal(str)
    CMSignal = pyqtSignal()
    CMautoSignal = pyqtSignal(bool)
    filterTopSignal = pyqtSignal(float)
    filterBotSignal = pyqtSignal(float)
    refPreferenceSignal = pyqtSignal(int)  # 0: TOP, 1: BOT
    saveSignal = pyqtSignal()
    analyzePSFSignal = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.image_top: np.ndarray | None = None
        self.image_bot: np.ndarray | None = None
        self._setup_gui()
        self._set_filters()

    def _set_filters(self):
        try:
            v_top = float(self.filter_top_edit.text()) / 100.0
            self.filterTopSignal.emit(v_top)
        except ValueError:
            pass
        try:
            v_bot = float(self.filter_bot_edit.text()) / 100.0
            self.filterBotSignal.emit(v_bot)
        except ValueError:
            pass

    def _set_parameters(self):
        try:
            params = [float(self.scanrangeEdit.text()),
                      float(self.scanrangeEdit_y.text()),
                      int(self.NxEdit.text()),
                      int(self.NyEdit.text())]
            if self.scan_mode.currentText() == SCAN_MODES[0]:
                self.parametersrampSignal.emit(params)
            else:
                self.parametersstepSignal.emit(params)
        except ValueError:
            pass

    def _get_scan(self):
        self.point_graph_CM_top.hide()
        self.point_graph_CM_bot.hide()
        self.startSignal.emit(self.scan_laser_top.currentIndex(), self.scan_laser_bot.currentIndex())

    def _get_scan_stop(self):
        self.stopSignal.emit()

    def _get_CM(self):
        self.CMSignal.emit()

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

    def _on_ref_change(self, val: int):
        self.refPreferenceSignal.emit(val)
        if val == 0:
            self.lbl_ref_status.setText("Referencia Activa: TOP (Derecho)")
            self.lbl_ref_status.setStyleSheet("color: #A6E3A1; font-weight: bold;")
        else:
            self.lbl_ref_status.setText("Referencia Activa: BOT (Invertido)")
            self.lbl_ref_status.setStyleSheet("color: #F38BA8; font-weight: bold;")

    def _setup_gui(self):
        main_hlo = QHBoxLayout(self)
        main_hlo.setContentsMargins(6, 6, 6, 6)
        main_hlo.setSpacing(8)

        # ── 1. DISPLAY CONFOCAL TOP (Izquierda) ──────────────────────────────
        top_widget = pg.GraphicsLayoutWidget()
        top_widget.setAspectLocked(True)
        self.img_top = pg.ImageItem()
        self.xlabel_top = pg.AxisItem(orientation="left")
        self.ylabel_top = pg.AxisItem(orientation="bottom")
        labelStyle = {"color": "#FFF", "font-size": "8pt"}
        self.xlabel_top.setLabel("X", units="um", **labelStyle)
        self.ylabel_top.setLabel("Y", units="um", **labelStyle)
        px0 = round(2 / 34, 3)
        self.xlabel_top.setScale(scale=px0)
        self.ylabel_top.setScale(scale=px0)

        self.vb_top = top_widget.addPlot(title="Confocal TOP (Derecho)", axisItems={"bottom": self.ylabel_top, "left": self.xlabel_top})
        self.vb_top.addItem(self.img_top)
        self.vb_top.invertY()
        self.vb_top.setAspectLocked(True)

        self.hist_top = pg.HistogramLUTItem(image=self.img_top)
        self.hist_top.gradient.loadPreset("thermal")
        for tick in self.hist_top.gradient.ticks:
            tick.hide()
        top_widget.addItem(self.hist_top, row=0, col=1)

        self.point_graph_CM_top = pg.ScatterPlotItem(size=10, symbol="+", pen="g")
        self.vb_top.addItem(self.point_graph_CM_top)
        self.point_graph_CM_top.hide()

        # ── 2. CONTROLES COMPARTIDOS & CM DUAL (Centro) ──────────────────────
        controls_container = QWidget()
        controls_vlo = QVBoxLayout(controls_container)
        controls_vlo.setContentsMargins(4, 0, 4, 0)
        controls_vlo.setSpacing(8)

        # Panel 2.1: Láseres Duales
        laser_box = QGroupBox("Iluminación Dual")
        laser_glo = QGridLayout(laser_box)
        self.scan_laser_top = QComboBox()
        self.scan_laser_top.addItems(["532 nm (green)", "637 nm (red)", "592 nm (yellow)"])
        self.scan_laser_bot = QComboBox()
        self.scan_laser_bot.addItems(["532 nm (green)"])

        laser_glo.addWidget(QLabel("Láser TOP (Derecho):"), 0, 0)
        laser_glo.addWidget(self.scan_laser_top, 0, 1)
        laser_glo.addWidget(QLabel("Láser BOT (Invertido):"), 1, 0)
        laser_glo.addWidget(self.scan_laser_bot, 1, 1)
        controls_vlo.addWidget(laser_box)

        # Panel 2.2: Parámetros Confocales Compartidos
        param_box = QGroupBox("Parámetros Confocales Compartidos")
        param_glo = QGridLayout(param_box)
        self.scan_mode = QComboBox(); self.scan_mode.addItems(SCAN_MODES)
        self.PSF_mode = QComboBox(); self.PSF_mode.addItems(PSF_MODES)
        self.scanrangeEdit = QLineEdit(str(DEFAULT_CONFOCAL_RANGE_X))
        self.scanrangeEdit_y = QLineEdit(str(DEFAULT_CONFOCAL_RANGE_Y))
        self.NxEdit = QLineEdit(str(DEFAULT_CONFOCAL_PIXELS_X))
        self.NyEdit = QLineEdit(str(DEFAULT_CONFOCAL_PIXELS_Y))

        self.scan_mode.currentIndexChanged.connect(self._set_scan_mode)
        self.PSF_mode.currentIndexChanged.connect(self._set_psf_mode)
        self.scanrangeEdit.textChanged.connect(self._set_parameters)
        self.scanrangeEdit_y.textChanged.connect(self._set_parameters)
        self.NxEdit.textChanged.connect(self._set_parameters)
        self.NyEdit.textChanged.connect(self._set_parameters)

        param_glo.addWidget(QLabel("Modo:"), 0, 0); param_glo.addWidget(self.scan_mode, 0, 1)
        param_glo.addWidget(QLabel("Dirección:"), 0, 2); param_glo.addWidget(self.PSF_mode, 0, 3)
        param_glo.addWidget(QLabel("Range X (µm):"), 1, 0); param_glo.addWidget(self.scanrangeEdit, 1, 1)
        param_glo.addWidget(QLabel("Range Y (µm):"), 1, 2); param_glo.addWidget(self.scanrangeEdit_y, 1, 3)
        param_glo.addWidget(QLabel("Pixels X:"), 2, 0); param_glo.addWidget(self.NxEdit, 2, 1)
        param_glo.addWidget(QLabel("Pixels Y:"), 2, 2); param_glo.addWidget(self.NyEdit, 2, 3)
        controls_vlo.addWidget(param_box)

        # Panel 2.3: Acciones Principales
        btn_box = QWidget()
        btn_hlo = QHBoxLayout(btn_box)
        btn_hlo.setContentsMargins(0, 0, 0, 0)
        self.scanButton = QPushButton("▶ Start Dual Scan")
        self.scanButton.setStyleSheet("QPushButton { background-color: #A6E3A1; color: #11111B; font-weight: bold; padding: 6px; }")
        self.scanButtonstop = QPushButton("⏹ Stop")
        self.saveimageButton = QPushButton("💾 Save Frame")
        self.saveimageButton.setStyleSheet("QPushButton { background-color: #F9E2AF; color: #11111B; font-weight: bold; }")

        self.scanButton.clicked.connect(self._get_scan)
        self.scanButtonstop.clicked.connect(self._get_scan_stop)
        self.saveimageButton.clicked.connect(lambda: self.saveSignal.emit())

        btn_hlo.addWidget(self.scanButton)
        btn_hlo.addWidget(self.scanButtonstop)
        btn_hlo.addWidget(self.saveimageButton)
        controls_vlo.addWidget(btn_box)

        # Botón PSF Analyzer
        self.btn_psf_analyzer = QPushButton("📊 Analyze with PSF Analyzer")
        self.btn_psf_analyzer.setStyleSheet("QPushButton { background-color: #89B4FA; color: #11111B; font-weight: bold; padding: 8px; font-size: 9.5pt; }")
        self.btn_psf_analyzer.clicked.connect(lambda: self.analyzePSFSignal.emit())
        controls_vlo.addWidget(self.btn_psf_analyzer)

        # Panel 2.4: CM Dual & Selector de Referencia
        cm_box = QGroupBox("Centrado Sub-nanométrico & Referencia Dual")
        cm_glo = QGridLayout(cm_box)

        self.scan_image = QComboBox(); self.scan_image.addItems(SCAN_IMAGE)
        self.method_center = QComboBox(); self.method_center.addItems(METHOD_CENTER)
        self.scan_image.currentIndexChanged.connect(self._set_image_scan)
        self.method_center.currentIndexChanged.connect(self._set_method_center)

        self.filter_top_edit = QLineEdit(str(int(DEFAULT_CONFOCAL_FILTER_PERCENT)))
        self.filter_top_edit.setFixedWidth(40)
        self.filter_top_edit.textChanged.connect(self._set_filters)

        self.filter_bot_edit = QLineEdit(str(int(DEFAULT_CONFOCAL_FILTER_PERCENT)))
        self.filter_bot_edit.setFixedWidth(40)
        self.filter_bot_edit.textChanged.connect(self._set_filters)

        cm_glo.addWidget(QLabel("Detección:"), 0, 0); cm_glo.addWidget(self.scan_image, 0, 1)
        cm_glo.addWidget(QLabel("Modelo:"), 0, 2); cm_glo.addWidget(self.method_center, 0, 3)
        cm_glo.addWidget(QLabel("Filtro TOP (%):"), 1, 0); cm_glo.addWidget(self.filter_top_edit, 1, 1)
        cm_glo.addWidget(QLabel("Filtro BOT (%):"), 1, 2); cm_glo.addWidget(self.filter_bot_edit, 1, 3)

        # Deslizador de Referencia (2 posiciones)
        ref_box = QWidget()
        ref_hlo = QHBoxLayout(ref_box)
        ref_hlo.setContentsMargins(0, 0, 0, 0)
        ref_hlo.addWidget(QLabel("Ref TOP"))
        self.slider_ref = QSlider(Qt.Orientation.Horizontal)
        self.slider_ref.setRange(0, 1)
        self.slider_ref.setSingleStep(1)
        self.slider_ref.setFixedWidth(60)
        self.slider_ref.valueChanged.connect(self._on_ref_change)
        ref_hlo.addWidget(self.slider_ref)
        ref_hlo.addWidget(QLabel("Ref BOT"))
        cm_glo.addWidget(ref_box, 2, 0, 1, 2)

        self.lbl_ref_status = QLabel("Referencia Activa: TOP (Derecho)")
        self.lbl_ref_status.setStyleSheet("color: #A6E3A1; font-weight: bold;")
        cm_glo.addWidget(self.lbl_ref_status, 2, 2, 1, 2)

        self.CMcheck = QPushButton("📍 Go to NP (Referencia)")
        self.CMcheck.setStyleSheet("QPushButton { background-color: #CBA6F7; color: #11111B; font-weight: bold; padding: 5px; }")
        self.CMcheck_auto = QCheckBox("Auto CM")
        self.CMcheck.clicked.connect(self._get_CM)
        self.CMcheck_auto.clicked.connect(self._get_CM_auto)

        cm_glo.addWidget(self.CMcheck, 3, 0, 1, 2)
        cm_glo.addWidget(self.CMcheck_auto, 3, 2, 1, 2)

        # Despliegue de Resultados Sub-nanométricos
        self.lbl_center_top = QLabel("Centro TOP: NaN, NaN µm")
        self.lbl_center_bot = QLabel("Centro BOT: NaN, NaN µm")
        self.lbl_diff_vector = QLabel("Diferencia r_TOP - r_BOT: Δx=0 nm, Δy=0 nm, |Δr|=0.0 nm")
        self.lbl_diff_vector.setStyleSheet("color: #89B4FA; font-weight: bold;")

        cm_glo.addWidget(self.lbl_center_top, 4, 0, 1, 4)
        cm_glo.addWidget(self.lbl_center_bot, 5, 0, 1, 4)
        cm_glo.addWidget(self.lbl_diff_vector, 6, 0, 1, 4)

        controls_vlo.addWidget(cm_box)
        controls_vlo.addStretch()

        # ── 3. DISPLAY CONFOCAL BOT (Derecha) ─────────────────────────────────
        bot_widget = pg.GraphicsLayoutWidget()
        bot_widget.setAspectLocked(True)
        self.img_bot = pg.ImageItem()
        self.xlabel_bot = pg.AxisItem(orientation="left")
        self.ylabel_bot = pg.AxisItem(orientation="bottom")
        self.xlabel_bot.setLabel("X", units="um", **labelStyle)
        self.ylabel_bot.setLabel("Y", units="um", **labelStyle)
        self.xlabel_bot.setScale(scale=px0)
        self.ylabel_bot.setScale(scale=px0)

        self.vb_bot = bot_widget.addPlot(title="Confocal BOT (Invertido)", axisItems={"bottom": self.ylabel_bot, "left": self.xlabel_bot})
        self.vb_bot.addItem(self.img_bot)
        self.vb_bot.invertY()
        self.vb_bot.setAspectLocked(True)

        self.hist_bot = pg.HistogramLUTItem(image=self.img_bot)
        self.hist_bot.gradient.loadPreset("inferno")
        for tick in self.hist_bot.gradient.ticks:
            tick.hide()
        bot_widget.addItem(self.hist_bot, row=0, col=1)

        self.point_graph_CM_bot = pg.ScatterPlotItem(size=10, symbol="+", pen="r")
        self.vb_bot.addItem(self.point_graph_CM_bot)
        self.point_graph_CM_bot.hide()

        # Añadir al layout horizontal principal
        main_hlo.addWidget(top_widget, stretch=4)
        main_hlo.addWidget(controls_container, stretch=3)
        main_hlo.addWidget(bot_widget, stretch=4)

    # ── Slots de Actualización desde Backend ──────────────────────────────────

    @pyqtSlot(float, float)
    def get_view_scale(self, px: float, py: float):
        self.xlabel_top.setScale(scale=px)
        self.ylabel_top.setScale(scale=py)
        self.xlabel_bot.setScale(scale=px)
        self.ylabel_bot.setScale(scale=py)

    @pyqtSlot(np.ndarray, np.ndarray)
    def get_dual_img(self, img_top: np.ndarray, img_bot: np.ndarray):
        self.image_top = img_top
        self.image_bot = img_bot
        self.img_top.setImage(img_top)
        self.img_bot.setImage(img_bot)

    @pyqtSlot(list, list)
    def update_cm_results(self, cm_top: list, cm_bot: list):
        xt, yt = cm_top[0], cm_top[1]
        xb, yb = cm_bot[0], cm_bot[1]

        self.lbl_center_top.setText(f"Centro TOP (Derecho): {xt:.3f}, {yt:.3f} µm")
        self.lbl_center_bot.setText(f"Centro BOT (Invertido): {xb:.3f}, {yb:.3f} µm")

        dx_nm = (xt - xb) * 1000.0
        dy_nm = (yt - yb) * 1000.0
        dr_nm = math.hypot(dx_nm, dy_nm)
        self.lbl_diff_vector.setText(f"Vector r_TOP - r_BOT: Δx={dx_nm:+.1f} nm, Δy={dy_nm:+.1f} nm, |Δr|={dr_nm:.1f} nm")

        # Dibujar marcadores
        if not math.isnan(xt) and not math.isnan(yt):
            self.point_graph_CM_top.setData([xt], [yt])
            self.point_graph_CM_top.show()
        if not math.isnan(xb) and not math.isnan(yb):
            self.point_graph_CM_bot.setData([xb], [yb])
            self.point_graph_CM_bot.show()


# ══════════════════════════════════════════════════════════════════════════════
#  BACKEND: HILO ASÍNCRONO DE ADQUISICIÓN DUAL
# ══════════════════════════════════════════════════════════════════════════════

class ConfocalDualBackend(QObject):

    scaleSignal = pyqtSignal(float, float)
    dataDualSignal = pyqtSignal(np.ndarray, np.ndarray)
    cmDualSignal = pyqtSignal(list, list)
    scanfinishedSignal = pyqtSignal(np.ndarray, np.ndarray, list, list)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.range_x = DEFAULT_CONFOCAL_RANGE_X
        self.range_y = DEFAULT_CONFOCAL_RANGE_Y
        self.Nx = int(DEFAULT_CONFOCAL_PIXELS_X)
        self.Ny = int(DEFAULT_CONFOCAL_PIXELS_Y)
        self.scan_mode_opt = SCAN_MODES[0]
        self.psf_mode_opt = PSF_MODES[0]
        self.image_scan_opt = SCAN_IMAGE[0]
        self.method_center_opt = METHOD_CENTER[0]
        self.filter_top = DEFAULT_CONFOCAL_FILTER_PERCENT / 100.0
        self.filter_bot = DEFAULT_CONFOCAL_FILTER_PERCENT / 100.0
        self.ref_pref = 0  # 0: TOP, 1: BOT
        self.cm_auto = False

        self.image_top = np.zeros((self.Ny, self.Nx))
        self.image_bot = np.zeros((self.Ny, self.Nx))
        self.cm_top = [0.0, 0.0]
        self.cm_bot = [0.0, 0.0]
        self.signal_scan_stop = False

        self.PDtimer_rampxy = QTimer()
        self.PDtimer_rampxy.timeout.connect(self._scan_ramp_xy)

    def make_connection(self, frontend: ConfocalDualFrontend):
        frontend.startSignal.connect(self.start_scan)
        frontend.stopSignal.connect(self.stop_scan)
        frontend.parametersrampSignal.connect(self.scan_ramp_parameters)
        frontend.parametersstepSignal.connect(self.scan_step_parameters)
        frontend.scan_modeSignal.connect(self.scan_mode)
        frontend.psf_modeSignal.connect(self.psf_mode)
        frontend.image_scanSignal.connect(self.image_scan)
        frontend.method_centerSignal.connect(self.method_center)
        frontend.filterTopSignal.connect(self.set_filter_top)
        frontend.filterBotSignal.connect(self.set_filter_bot)
        frontend.refPreferenceSignal.connect(self.set_ref_preference)
        frontend.CMSignal.connect(self.measure_CM)
        frontend.CMautoSignal.connect(self.set_cm_auto)

        self.scaleSignal.connect(frontend.get_view_scale)
        self.dataDualSignal.connect(frontend.get_dual_img)
        self.cmDualSignal.connect(frontend.update_cm_results)

    @pyqtSlot(float)
    def set_filter_top(self, v: float): self.filter_top = v
    @pyqtSlot(float)
    def set_filter_bot(self, v: float): self.filter_bot = v
    @pyqtSlot(int)
    def set_ref_preference(self, ref: int): self.ref_pref = ref
    @pyqtSlot(bool)
    def set_cm_auto(self, b: bool): self.cm_auto = b
    @pyqtSlot(str)
    def scan_mode(self, v: str): self.scan_mode_opt = v
    @pyqtSlot(str)
    def psf_mode(self, v: str): self.psf_mode_opt = v
    @pyqtSlot(str)
    def image_scan(self, v: str): self.image_scan_opt = v
    @pyqtSlot(str)
    def method_center(self, v: str): self.method_center_opt = v

    @pyqtSlot(list)
    def scan_ramp_parameters(self, p: list):
        self.range_x, self.range_y, self.Nx, self.Ny = p[0], p[1], int(p[2]), int(p[3])
        self.extra = self.range_x / 6
        self.range_total = self.range_x + 2 * self.extra
        self.frequency = RATE_MULTICHANNEL / 100

        if self.Nx <= 50 and self.range_x <= 5.0:
            self.frequency_ramp = (1 / 1200) * RATE_MULTICHANNEL / 100
            self.Nramp = 2 * int(self.frequency / self.frequency_ramp)
        else:
            pixels_total_line = int(self.Nx * (self.range_total / self.range_x))
            self.Nramp = 2 * pixels_total_line * 4
            self.frequency_ramp = self.frequency / (self.Nramp / 2)

        self.scaleSignal.emit(round(self.range_x / self.Nx, 3), round(self.range_y / self.Ny, 3))

    @pyqtSlot(list)
    def scan_step_parameters(self, p: list):
        self.range_x, self.range_y, self.Nx, self.Ny = p[0], p[1], int(p[2]), int(p[3])
        self.scaleSignal.emit(round(self.range_x / self.Nx, 3), round(self.range_y / self.Ny, 3))

    @pyqtSlot(int, int)
    def start_scan(self, top_laser_idx: int, bot_laser_idx: int):
        self.signal_scan_stop = False
        self.image_top = np.zeros((self.Ny, self.Nx))
        self.image_bot = np.zeros((self.Ny, self.Nx))
        self.i = 0
        self.x_pos, self.y_pos, self.z_pos = self._read_pos()
        self._configure_ramp_x(self.x_pos)
        open_shutter(SHUTTERS[top_laser_idx])
        open_shutter(SHUTTERS[0])  # Verde 532 nm por abajo
        self.PDtimer_rampxy.start(0)

    @pyqtSlot()
    def stop_scan(self):
        self.signal_scan_stop = True

    def _read_pos(self) -> tuple[float, float, float]:
        if SAFE_MODE:
            return (50.0, 50.0, 50.0)
        pos = pi.qPOS()
        return (float(pos.get("1", 50.0)), float(pos.get("2", 50.0)), float(pos.get("3", 50.0)))

    def _configure_ramp_x(self, x_pos: float):
        sp = self.range_x / self.Nx
        Npoints = int(self.range_total / sp) * 20
        Npoints = max(100, min(4000, Npoints))
        Nspeed = int(Npoints / 4)
        WTRtime = int(1 / (self.frequency_ramp * PI_SERVO_TIME * Npoints))
        WTRtime = max(1, WTRtime)
        pi.WTR(0, WTRtime, 0)
        pi.WAV_LIN(1, 0, Npoints, "X", Nspeed, self.range_total, 0, Npoints)
        pi.WAV_LIN(1, 0, Npoints, "&", Nspeed, -self.range_total, self.range_total, Npoints)
        pi.WSL(1, 1); pi.WGC(1, 1)
        xo = x_pos - self.range_total / 2
        xo = max(0.0, min(100.0 - self.range_total, xo))
        pi.MOV(1, xo); pi.WOS(1, xo)
        pi.TWC(); pi.CTO(1, 3, 3)
        pi.CTO(1, 5, xo + self.extra)
        pi.CTO(1, 6, xo + self.range_total - self.extra)

    def _scan_ramp_xy(self):
        if self.signal_scan_stop or self.i >= self.Ny:
            self.PDtimer_rampxy.stop()
            close_shutter("532 nm (green)")
            close_shutter("637 nm (red)")
            close_shutter("592 nm (yellow)")
            self.measure_CM()
            self.scanfinishedSignal.emit(self.image_top, self.image_bot, self.cm_top, self.cm_bot)
            return

        dy = self.range_y / self.Ny
        pi.MOV(2, self.y_pos - self.range_y / 2 + dy / 2 + self.i * dy)

        # Adquisición multicanal real / mock
        task = channels_photodiodos(self.frequency, self.Nramp)
        channels_triggers(task, "X")
        pi.WGO(1, 1)

        if SAFE_MODE:
            # Simular imágenes gaussianas sintéticas con ligera diferencia espacial
            grid_x, grid_y = np.meshgrid(np.linspace(-1, 1, self.Nx), np.linspace(-1, 1, self.Ny))
            g_top = np.exp(-((grid_x - 0.05)**2 + (grid_y - 0.02)**2) / 0.15) * 8.5
            g_bot = np.exp(-((grid_x + 0.03)**2 + (grid_y + 0.04)**2) / 0.18) * 7.2
            self.image_top[self.i, :] = g_top[self.i, :]
            self.image_bot[self.i, :] = g_bot[self.i, :]
        else:
            data = task.read(number_of_samples_per_channel=self.Nramp)
            data = np.array(data)
            # data[0] -> Top PD, data[1] -> Bot PD, data[2] -> Trigger
            ph_top, ph_bot, trig = data[0], data[1], data[2]
            d = np.diff(trig); L = len(trig)
            asc = np.where(d >= 1.5)[0]; dsc = np.where(d <= -1.5)[0]
            if len(asc) and len(dsc):
                fa = asc[0]; fd_i = np.where(dsc > fa + L/6)[0]; fd = dsc[fd_i[0]] if len(fd_i) else fa
                g_top = ph_top[fa:fd]; g_bot = ph_bot[fa:fd]
                # Promedio por píxel
                n_g = len(g_top)
                if n_g >= self.Nx:
                    pts_px = n_g // self.Nx
                    self.image_top[self.i, :] = [g_top[k*pts_px:(k+1)*pts_px].mean() for k in range(self.Nx)]
                    self.image_bot[self.i, :] = [g_bot[k*pts_px:(k+1)*pts_px].mean() for k in range(self.Nx)]

        self.dataDualSignal.emit(self.image_top, self.image_bot)
        self.i += 1

    @pyqtSlot()
    def measure_CM(self):
        # Calcular centro TOP
        self.cm_top = self._compute_center(self.image_top, self.filter_top)
        # Calcular centro BOT
        self.cm_bot = self._compute_center(self.image_bot, self.filter_bot)

        self.cmDualSignal.emit(self.cm_top, self.cm_bot)

        if self.cm_auto:
            self._goto_ref()

    def _compute_center(self, img: np.ndarray, thr: float) -> list[float]:
        if img is None or img.max() == 0:
            return [self.x_pos, self.y_pos]
        Zn = (img - img.min()) / (img.max() - img.min() + 1e-12)
        Zf = np.where(Zn >= thr, Zn, 0.0)

        if self.method_center_opt == "center of mass":
            xo_px, yo_px = center_of_mass(Zf)
        elif self.method_center_opt == "center of gauss":
            fit = center_of_gauss2D(Zf)
            xo_px, yo_px = fit[0], fit[1]
        else:
            fit = center_of_donut2D(Zf)
            xo_px, yo_px = fit[0], fit[1]

        # Convertir a micrómetros
        dx = self.range_x / self.Nx
        dy = self.range_y / self.Ny
        xo_um = self.x_pos - self.range_x / 2 + dx / 2 + xo_px * dx
        yo_um = self.y_pos - self.range_y / 2 + dy / 2 + yo_px * dy
        return [round(xo_um, 3), round(yo_um, 3)]

    def _goto_ref(self):
        ref_cm = self.cm_top if self.ref_pref == 0 else self.cm_bot
        xr, yr = ref_cm[0], ref_cm[1]
        if not math.isnan(xr) and not math.isnan(yr):
            pi.MOV([1, 2], [xr, yr])
            self.x_pos, self.y_pos = xr, yr


# ══════════════════════════════════════════════════════════════════════════════
#  VENTANA PRINCIPAL DEL MICROSCOPIO CONTRAPROPAGANTE
# ══════════════════════════════════════════════════════════════════════════════

class ContrapropaganteMainWindow(QMainWindow):

    def __init__(self, parent=None):
        super().__init__(parent)
        title = "PyPrinting — Microscopio Contrapropagante (Excitación Dual)"
        if SAFE_MODE:
            title += "  [MODO SEGURO — sin hardware]"
        self.setWindowTitle(title)
        self.resize(1550, 920)

        self._cwidget = QWidget()
        self.setCentralWidget(self._cwidget)
        self._setup_menu()

        # Layout Principal
        vlo = QVBoxLayout(self._cwidget)
        vlo.setContentsMargins(4, 4, 4, 4)

        self.dual_frontend = ConfocalDualFrontend()
        vlo.addWidget(self.dual_frontend)

        # Flotantes
        self.cameraWindow = CameraWindow()
        self.imageAnalyzerWindow = ImageAnalyzerWindow()
        self.psfAnalyzerWindow = PSFAnalyzerWindow()
        self.laser532Window = Laser532Window()
        self.printingWidget = MeasFrontend(mode="printing")
        self.dimersWidget = MeasFrontend(mode="dimers")

        # Conectar acción PSF Analyzer integrada
        self.dual_frontend.analyzePSFSignal.connect(self._on_analyze_psf)

        # Threading del Backend Dual
        self.backendThread = QThread()
        self.dualBackend = ConfocalDualBackend()
        self.dualBackend.moveToThread(self.backendThread)
        self.dualBackend.make_connection(self.dual_frontend)
        self.backendThread.start()

    def _setup_menu(self):
        mb = self.menuBar()
        fm = mb.addMenu("&Files")
        fm.addAction("Seleccionar directorio (Ctrl+A)", lambda: None, QKeySequence("Ctrl+A"))
        fm.addAction("Crear directorio diario (Ctrl+S)", lambda: None, QKeySequence("Ctrl+S"))
        fm.addAction("Abrir directorio (Ctrl+D)", lambda: None, QKeySequence("Ctrl+D"))

        tm = mb.addMenu("&Tools")
        tm.addAction("Cámara", lambda: self.cameraWindow.show())
        tm.addAction("Analizador de Imágenes", lambda: self.imageAnalyzerWindow.show())
        tm.addAction("PSF Analyzer", lambda: self.psfAnalyzerWindow.show())
        tm.addAction("Láser 532", lambda: self.laser532Window.show())

        mm = mb.addMenu("&Measurements")
        mm.addAction("Printing", lambda: self.printingWidget.show())
        mm.addAction("Dimers", lambda: self.dimersWidget.show())

    def _on_analyze_psf(self):
        img_t = self.dual_frontend.image_top
        img_b = self.dual_frontend.image_bot
        if img_t is None or img_b is None:
            QMessageBox.information(self, "PSF Analyzer", "Realice primero un escaneo dual para analizar las confocales TOP y BOT.")
            return
        px_size = round(float(self.dual_frontend.scanrangeEdit.text()) / int(self.dual_frontend.NxEdit.text()), 4)
        self.psfAnalyzerWindow.load_dual_images(img_t, img_b, px_size)

    def closeEvent(self, event):
        self.backendThread.quit()
        self.backendThread.wait()
        event.accept()


def main():
    app = QApplication(sys.argv)
    win = ContrapropaganteMainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
