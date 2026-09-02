# -*- coding: utf-8 -*-
"""
contrapropagante.py — Suite del Microscopio Contrapropagante (Excitación Dual)
PyPrinting 3.0 — UNSAM Nanofotónica — PyQt6

Permite la iluminación simultánea por arriba (Derecho) y por abajo (Invertido),
adquiriendo dos confocales en paralelo (Confocal TOP y Confocal BOT) con el mismo
movimiento de la platina piezoeléctrica PI.

Disposición Visual de la Ventana Principal (DockArea simétrico a app.py):
  ┌─────────────────────────────────────────────────────────────────────────────┐
  │                    Confocal Contrapropagante Dual                          │
  │ [TOP (PD1/ai0)]   |   [CONTROLES & CM DUAL]   |   [BOT (PD2/ai1)]          │
  ├──────────┬────────────────────────────────────┬─────────────────────────────┤
  │ Nano     │ Focus z                            │ Shutters / Flipper / 532    │
  └──────────┴────────────────────────────────────┴─────────────────────────────┘
  │ Trace (Ancho completo)                                                      │
  └─────────────────────────────────────────────────────────────────────────────┘

Modelos de Ajuste Diferenciados:
  - TOP (Arriba / Derecho): ["center of mass", "center of gauss"]
  - BOT (Abajo / Invertido): ["center of mass", "center of gauss", "donut (Laguerre-Gauss)"]
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
from camera import (CameraWindow, CanonWorker as CameraBackend,
                    Laser532Window, Laser532Backend)
from image_analyzer import ImageAnalyzerWindow
from psf_analyzer import PSFAnalyzerWindow

SCAN_MODES = ["Ramp", "Step by step"]
PSF_MODES = ["x/y", "x/z", "y/x", "y/z"]
SCAN_IMAGE = ["NPs maximum", "NPs minimum"]
METHOD_CENTER_TOP = ["center of mass", "center of gauss"]
METHOD_CENTER_BOT = ["center of mass", "center of gauss", "donut (Laguerre-Gauss)"]


# ══════════════════════════════════════════════════════════════════════════════
#  FRONTEND: INTERFAZ DEL MICROSCOPIO CONTRAPROPAGANTE DUAL
# ══════════════════════════════════════════════════════════════════════════════

class ConfocalDualFrontend(QWidget):

    startSignal = pyqtSignal(int, int)   # (laser_top_idx, laser_bot_idx)
    stopSignal = pyqtSignal()
    parametersrampSignal = pyqtSignal(list)
    parametersstepSignal = pyqtSignal(list)
    scan_modeSignal = pyqtSignal(str)
    psf_modeSignal = pyqtSignal(str)
    image_scanSignal = pyqtSignal(str)
    method_center_topSignal = pyqtSignal(str)
    method_center_botSignal = pyqtSignal(str)
    CMSignal = pyqtSignal()
    CMautoSignal = pyqtSignal(bool)
    filterTopSignal = pyqtSignal(float)
    filterBotSignal = pyqtSignal(float)
    originCornerSignal = pyqtSignal(bool)
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

    def _set_method_center_top(self):
        self.method_center_topSignal.emit(self.method_center_top.currentText())

    def _set_method_center_bot(self):
        self.method_center_botSignal.emit(self.method_center_bot.currentText())

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
        main_hlo.setContentsMargins(4, 4, 4, 4)
        main_hlo.setSpacing(6)

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

        # Fotodiodo 1 (ai0) acoplado al láser TOP seleccionado
        self.vb_top = top_widget.addPlot(title="Confocal TOP (Derecho — Fotodiodo 1 / ai0)", axisItems={"bottom": self.ylabel_top, "left": self.xlabel_top})
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
        controls_vlo.setSpacing(6)

        # Panel 2.1: Láseres Duales & Mapeo Directo a Fotodiodos
        laser_box = QGroupBox("Iluminación Dual (Filtros Dicroicos / Notch)")
        laser_glo = QGridLayout(laser_box)
        self.scan_laser_top = QComboBox()
        self.scan_laser_top.addItems(SHUTTERS)
        self.scan_laser_bot = QComboBox()
        self.scan_laser_bot.addItems(SHUTTERS)

        laser_glo.addWidget(QLabel("Láser TOP (Derecho → PD1):"), 0, 0)
        laser_glo.addWidget(self.scan_laser_top, 0, 1)
        laser_glo.addWidget(QLabel("Láser BOT (Invertido → PD2):"), 1, 0)
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

        self.origin_corner_check = QCheckBox("📍 Inicio en Posición Actual")
        self.origin_corner_check.setToolTip("Define la posición actual de la platina como la esquina inicial (origen) del área de escaneo, en lugar del centro geométrico.")
        self.origin_corner_check.setStyleSheet("color: #A6E3A1; font-weight: bold;")
        self.origin_corner_check.toggled.connect(lambda b: self.originCornerSignal.emit(b))

        param_glo.addWidget(QLabel("Modo:"), 0, 0); param_glo.addWidget(self.scan_mode, 0, 1)
        param_glo.addWidget(QLabel("Dirección:"), 0, 2); param_glo.addWidget(self.PSF_mode, 0, 3)
        param_glo.addWidget(QLabel("Range X (µm):"), 1, 0); param_glo.addWidget(self.scanrangeEdit, 1, 1)
        param_glo.addWidget(QLabel("Range Y (µm):"), 1, 2); param_glo.addWidget(self.scanrangeEdit_y, 1, 3)
        param_glo.addWidget(QLabel("Pixels X:"), 2, 0); param_glo.addWidget(self.NxEdit, 2, 1)
        param_glo.addWidget(QLabel("Pixels Y:"), 2, 2); param_glo.addWidget(self.NyEdit, 2, 3)
        param_glo.addWidget(self.origin_corner_check, 3, 0, 1, 4)
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
        self.btn_psf_analyzer.setStyleSheet("QPushButton { background-color: #89B4FA; color: #11111B; font-weight: bold; padding: 7px; font-size: 9pt; }")
        self.btn_psf_analyzer.clicked.connect(lambda: self.analyzePSFSignal.emit())
        controls_vlo.addWidget(self.btn_psf_analyzer)

        # Panel 2.4: CM Dual (Modelos Diferenciados TOP / BOT) & Selector de Referencia
        cm_box = QGroupBox("Centrado Sub-nanométrico & Referencia Dual")
        cm_glo = QGridLayout(cm_box)

        self.scan_image = QComboBox(); self.scan_image.addItems(SCAN_IMAGE)
        self.method_center_top = QComboBox(); self.method_center_top.addItems(METHOD_CENTER_TOP)
        self.method_center_bot = QComboBox(); self.method_center_bot.addItems(METHOD_CENTER_BOT)
        self.scan_image.currentIndexChanged.connect(self._set_image_scan)
        self.method_center_top.currentIndexChanged.connect(self._set_method_center_top)
        self.method_center_bot.currentIndexChanged.connect(self._set_method_center_bot)

        self.filter_top_edit = QLineEdit(str(int(DEFAULT_CONFOCAL_FILTER_PERCENT)))
        self.filter_top_edit.setFixedWidth(40); self.filter_top_edit.textChanged.connect(self._set_filters)

        self.filter_bot_edit = QLineEdit(str(int(DEFAULT_CONFOCAL_FILTER_PERCENT)))
        self.filter_bot_edit.setFixedWidth(40); self.filter_bot_edit.textChanged.connect(self._set_filters)

        cm_glo.addWidget(QLabel("Detección:"), 0, 0); cm_glo.addWidget(self.scan_image, 0, 1)
        cm_glo.addWidget(QLabel("Modelo TOP:"), 1, 0); cm_glo.addWidget(self.method_center_top, 1, 1)
        cm_glo.addWidget(QLabel("Modelo BOT:"), 1, 2); cm_glo.addWidget(self.method_center_bot, 1, 3)
        cm_glo.addWidget(QLabel("Filtro TOP (%):"), 2, 0); cm_glo.addWidget(self.filter_top_edit, 2, 1)
        cm_glo.addWidget(QLabel("Filtro BOT (%):"), 2, 2); cm_glo.addWidget(self.filter_bot_edit, 2, 3)

        # Deslizador de Referencia (2 posiciones)
        ref_box = QWidget()
        ref_hlo = QHBoxLayout(ref_box)
        ref_hlo.setContentsMargins(0, 0, 0, 0)
        ref_hlo.addWidget(QLabel("Ref TOP"))
        self.slider_ref = QSlider(Qt.Orientation.Horizontal)
        self.slider_ref.setRange(0, 1)
        self.slider_ref.setSingleStep(1)
        self.slider_ref.setFixedWidth(50)
        self.slider_ref.valueChanged.connect(self._on_ref_change)
        ref_hlo.addWidget(self.slider_ref)
        ref_hlo.addWidget(QLabel("Ref BOT"))
        cm_glo.addWidget(ref_box, 3, 0, 1, 2)

        self.lbl_ref_status = QLabel("Referencia Activa: TOP (Derecho)")
        self.lbl_ref_status.setStyleSheet("color: #A6E3A1; font-weight: bold;")
        cm_glo.addWidget(self.lbl_ref_status, 3, 2, 1, 2)

        self.CMcheck = QPushButton("📍 Go to NP (Referencia)")
        self.CMcheck.setStyleSheet("QPushButton { background-color: #CBA6F7; color: #11111B; font-weight: bold; padding: 4px; }")
        self.CMcheck_auto = QCheckBox("Auto CM")
        self.CMcheck.clicked.connect(self._get_CM)
        self.CMcheck_auto.clicked.connect(self._get_CM_auto)

        cm_glo.addWidget(self.CMcheck, 4, 0, 1, 2)
        cm_glo.addWidget(self.CMcheck_auto, 4, 2, 1, 2)

        # Despliegue de Resultados Sub-nanométricos
        self.lbl_center_top = QLabel("Centro TOP: NaN, NaN µm")
        self.lbl_center_bot = QLabel("Centro BOT: NaN, NaN µm")
        self.lbl_diff_vector = QLabel("Vector r_TOP - r_BOT: Δx=0 nm, Δy=0 nm, |Δr|=0.0 nm")
        self.lbl_diff_vector.setStyleSheet("color: #89B4FA; font-weight: bold;")

        cm_glo.addWidget(self.lbl_center_top, 5, 0, 1, 4)
        cm_glo.addWidget(self.lbl_center_bot, 6, 0, 1, 4)
        cm_glo.addWidget(self.lbl_diff_vector, 7, 0, 1, 4)

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

        # Fotodiodo 2 (ai1) acoplado al láser BOT
        self.vb_bot = bot_widget.addPlot(title="Confocal BOT (Invertido — Fotodiodo 2 / ai1)", axisItems={"bottom": self.ylabel_bot, "left": self.xlabel_bot})
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
        self.img_top.setImage(img_top, autoLevels=True)
        self.img_bot.setImage(img_bot, autoLevels=True)

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
    gridScanFinishedSignal = pyqtSignal(np.ndarray, list, np.ndarray, np.ndarray, str, str)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.range_x = DEFAULT_CONFOCAL_RANGE_X
        self.range_y = DEFAULT_CONFOCAL_RANGE_Y
        self.Nx = int(DEFAULT_CONFOCAL_PIXELS_X)
        self.Ny = int(DEFAULT_CONFOCAL_PIXELS_Y)
        self.extra = self.range_x / 6
        self.range_total = self.range_x + 2 * self.extra
        self.frequency = RATE_MULTICHANNEL / 100
        self.frequency_ramp = (1 / 1200) * RATE_MULTICHANNEL / 100
        self.Nramp = 2400

        self.top_laser_idx = 0
        self.bot_laser_idx = 0
        self.scan_mode_opt = SCAN_MODES[0]
        self.psf_mode_opt = PSF_MODES[0]
        self.image_scan_opt = SCAN_IMAGE[0]
        self.method_center_top_opt = METHOD_CENTER_TOP[0]
        self.method_center_bot_opt = METHOD_CENTER_BOT[0]
        self.filter_top = DEFAULT_CONFOCAL_FILTER_PERCENT / 100.0
        self.filter_bot = DEFAULT_CONFOCAL_FILTER_PERCENT / 100.0
        self.ref_pref = 0  # 0: TOP, 1: BOT
        self.cm_auto = False

        self.image_top = np.zeros((self.Ny, self.Nx))
        self.image_bot = np.zeros((self.Ny, self.Nx))
        self.cm_top = [0.0, 0.0]
        self.cm_bot = [0.0, 0.0]
        self.signal_scan_stop = False
        self.PDtimer_rampxy = None
        self.is_grid_routine = False

    def _ensure_timer(self):
        if self.PDtimer_rampxy is None:
            self.PDtimer_rampxy = QTimer(self)
            self.PDtimer_rampxy.timeout.connect(self._scan_ramp_xy)

    def make_connection(self, frontend: ConfocalDualFrontend):
        frontend.startSignal.connect(self.start_scan)
        frontend.stopSignal.connect(self.stop_scan)
        frontend.parametersrampSignal.connect(self.scan_ramp_parameters)
        frontend.parametersstepSignal.connect(self.scan_step_parameters)
        frontend.scan_modeSignal.connect(self.scan_mode)
        frontend.psf_modeSignal.connect(self.psf_mode)
        frontend.image_scanSignal.connect(self.image_scan)
        frontend.method_center_topSignal.connect(self.method_center_top)
        frontend.method_center_botSignal.connect(self.method_center_bot)
        frontend.filterTopSignal.connect(self.set_filter_top)
        frontend.filterBotSignal.connect(self.set_filter_bot)
        frontend.refPreferenceSignal.connect(self.set_ref_preference)
        frontend.CMSignal.connect(self.measure_CM)
        frontend.CMautoSignal.connect(self.set_cm_auto)
        frontend.originCornerSignal.connect(self.set_origin_corner)

        self.scaleSignal.connect(frontend.get_view_scale)
        self.dataDualSignal.connect(frontend.get_dual_img)
        self.cmDualSignal.connect(frontend.update_cm_results)

    @pyqtSlot(bool)
    def set_origin_corner(self, enabled: bool):
        self.origin_corner_enabled = enabled
        print(f"[ConfocalDual] Origen en posicion actual: {'ACTIVADO' if enabled else 'DESACTIVADO'}")

    def _get_scan_geometry(self, x_stage: float, y_stage: float, range_x: float, range_y: float):
        if getattr(self, "origin_corner_enabled", False):
            x_min = x_stage
            x_max = x_stage + range_x
            y_min = y_stage
            y_max = y_stage + range_y
            x_center = x_stage + range_x / 2.0
            y_center = y_stage + range_y / 2.0
        else:
            x_center = x_stage
            y_center = y_stage
            x_min = x_center - range_x / 2.0
            x_max = x_center + range_x / 2.0
            y_min = y_center - range_y / 2.0
            y_max = y_center + range_y / 2.0
        return x_center, y_center, x_min, x_max, y_min, y_max

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
    def method_center_top(self, v: str): self.method_center_top_opt = v
    @pyqtSlot(str)
    def method_center_bot(self, v: str): self.method_center_bot_opt = v

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

    @pyqtSlot(str, str, str)
    def start_scan_routines(self, laser: str, mode_printing: str, number_scan: str):
        self.mode_printing = mode_printing
        self.number_scan   = number_scan
        self.is_grid_routine = True
        top_idx = SHUTTERS.index(laser) if laser in SHUTTERS else 0
        bot_idx = 0
        self.start_scan(top_idx, bot_idx)

    @pyqtSlot(int, int)
    def start_scan(self, top_laser_idx: int, bot_laser_idx: int):
        self._ensure_timer()
        self.signal_scan_stop = False
        self.top_laser_idx = max(0, min(len(SHUTTERS) - 1, top_laser_idx))
        self.bot_laser_idx = max(0, min(len(SHUTTERS) - 1, bot_laser_idx))
        self.scan_ramp_parameters([self.range_x, self.range_y, self.Nx, self.Ny])

        self.image_top = np.zeros((self.Ny, self.Nx))
        self.image_bot = np.zeros((self.Ny, self.Nx))
        self.i = 0
        x_stage, y_stage, z_stage = self._read_pos()
        self.x_start, self.y_start, self.z_start = x_stage, y_stage, z_stage
        x_c, y_c, x_min, x_max, y_min, y_max = self._get_scan_geometry(x_stage, y_stage, self.range_x, self.range_y)
        self.x_pos, self.y_pos, self.z_pos = x_c, y_c, z_stage
        self.x_min, self.x_max = x_min, x_max
        self.y_min, self.y_max = y_min, y_max

        self._configure_ramp_x(self.x_pos)

        open_shutter(SHUTTERS[self.top_laser_idx])
        open_shutter(SHUTTERS[self.bot_laser_idx])
        self.PDtimer_rampxy.start(0)

    @pyqtSlot()
    def stop_scan(self):
        self.signal_scan_stop = True
        if self.PDtimer_rampxy and self.PDtimer_rampxy.isActive():
            self.PDtimer_rampxy.stop()
        close_all_shutters()
        xp = getattr(self, "x_start", getattr(self, "x_pos", 50.0))
        yp = getattr(self, "y_start", getattr(self, "y_pos", 50.0))
        zp = getattr(self, "z_start", getattr(self, "z_pos", 50.0))
        pi.MOV([1, 2, 3], [xp, yp, zp])

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
            close_all_shutters()
            self.measure_CM()
            xp = getattr(self, "x_start", getattr(self, "x_pos", 50.0))
            yp = getattr(self, "y_start", getattr(self, "y_pos", 50.0))
            zp = getattr(self, "z_start", getattr(self, "z_pos", 50.0))
            pi.MOV([1, 2, 3], [xp, yp, zp])
            if getattr(self, 'is_grid_routine', False):
                self.is_grid_routine = False
                self.gridScanFinishedSignal.emit(self.image_top, self.cm_top, None, None,
                                                 getattr(self, 'mode_printing', 'none'),
                                                 getattr(self, 'number_scan', 'none'))
            else:
                self.scanfinishedSignal.emit(self.image_top, self.image_bot, self.cm_top, self.cm_bot)
            return

        dy = self.range_y / self.Ny
        target_y = getattr(self, "y_min", self.y_pos - self.range_y / 2) + dy / 2 + self.i * dy
        pi.MOV(2, target_y)

        # Adquisición multicanal mapeando canal láser -> canal fotodiodo
        task = channels_photodiodos(self.frequency, self.Nramp)
        channels_triggers(task, "X")
        pi.WGO(1, 1)

        try:
            if SAFE_MODE:
                # Simular imágenes gaussianas sintéticas con ligera diferencia espacial
                grid_x, grid_y = np.meshgrid(np.linspace(-1, 1, self.Nx), np.linspace(-1, 1, self.Ny))
                g_top = np.exp(-((grid_x - 0.05)**2 + (grid_y - 0.02)**2) / 0.15) * 8.5
                g_bot = np.exp(-((grid_x + 0.03)**2 + (grid_y + 0.04)**2) / 0.18) * 7.2
                self.image_top[self.i, :] = g_top[self.i, :]
                self.image_bot[self.i, :] = g_bot[self.i, :]
            else:
                from config import PD_CHANNELS, TRIGGER_CHANNELS
                data = task.read(number_of_samples_per_channel=self.Nramp)
                data = np.array(data)

                top_laser_name = SHUTTERS[self.top_laser_idx]
                bot_laser_name = SHUTTERS[self.bot_laser_idx]
                top_pd_chan = PD_CHANNELS.get(top_laser_name, 0)
                bot_pd_chan = PD_CHANNELS.get(bot_laser_name, 0)

                ph_top = data[top_pd_chan]
                ph_bot = data[bot_pd_chan]
                trig_chan = TRIGGER_CHANNELS.get("X", 4)
                trig = data[trig_chan] if len(data) > trig_chan else data[-1]

                d = np.diff(trig); L = len(trig)
                asc = np.where(d >= 1.5)[0]; dsc = np.where(d <= -1.5)[0]
                if len(asc) and len(dsc):
                    fa = asc[0]; fd_i = np.where(dsc > fa + L/6)[0]; fd = dsc[fd_i[0]] if len(fd_i) else fa
                    g_top = ph_top[fa:fd] if fd > fa else ph_top[:L//2]
                    g_bot = ph_bot[fa:fd] if fd > fa else ph_bot[:L//2]
                else:
                    g_top = ph_top[:L//2]
                    g_bot = ph_bot[:L//2]

                # Promedio / Interpolación por píxel
                n_g = len(g_top)
                if n_g >= self.Nx:
                    pts_px = n_g // self.Nx
                    self.image_top[self.i, :] = [g_top[k*pts_px:(k+1)*pts_px].mean() for k in range(self.Nx)]
                    self.image_bot[self.i, :] = [g_bot[k*pts_px:(k+1)*pts_px].mean() for k in range(self.Nx)]
                else:
                    self.image_top[self.i, :] = np.interp(np.linspace(0, max(0, n_g-1), self.Nx), np.arange(n_g), g_top)
                    self.image_bot[self.i, :] = np.interp(np.linspace(0, max(0, n_g-1), self.Nx), np.arange(n_g), g_bot)
        finally:
            try:
                task.close()
            except Exception:
                pass

        self.dataDualSignal.emit(self.image_top, self.image_bot)
        self.i += 1

    @pyqtSlot()
    def measure_CM(self):
        # Calcular centro TOP (center of mass o center of gauss)
        self.cm_top = self._compute_center(self.image_top, self.filter_top, self.method_center_top_opt)
        # Calcular centro BOT (center of mass, center of gauss o donut)
        self.cm_bot = self._compute_center(self.image_bot, self.filter_bot, self.method_center_bot_opt)

        self.cmDualSignal.emit(self.cm_top, self.cm_bot)

        if self.cm_auto:
            self._goto_ref()

    def _compute_center(self, img: np.ndarray, thr: float, method: str) -> list[float]:
        if img is None or img.max() == 0:
            return [self.x_pos, self.y_pos]
        Zn = (img - img.min()) / (img.max() - img.min() + 1e-12)
        Zf = np.where(Zn >= thr, Zn, 0.0)

        if method == "center of mass":
            xo_px, yo_px = center_of_mass(Zf)
        elif method == "center of gauss":
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
        from config import PI_STAGE_RANGE_UM
        ref_cm = self.cm_top if self.ref_pref == 0 else self.cm_bot
        xr, yr = ref_cm[0], ref_cm[1]
        if not math.isnan(xr) and not math.isnan(yr):
            xr = max(0.0, min(PI_STAGE_RANGE_UM, xr))
            yr = max(0.0, min(PI_STAGE_RANGE_UM, yr))
            pi.MOV([1, 2], [xr, yr])
            self.x_pos, self.y_pos = xr, yr


# ══════════════════════════════════════════════════════════════════════════════
#  VENTANA PRINCIPAL DEL MICROSCOPIO CONTRAPROPAGANTE CON DOCKAREA COMPLETA
# ══════════════════════════════════════════════════════════════════════════════

class ContrapropaganteMainWindow(QMainWindow):

    selectDirSignal = pyqtSignal()
    createDirSignal = pyqtSignal()
    openDirSignal = pyqtSignal()
    loadPositionSignal = pyqtSignal()
    loadGridSignal = pyqtSignal()
    closeSignal = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        title = "PyPrinting — Microscopio Contrapropagante (Excitación Dual)"
        if SAFE_MODE:
            title += "  [MODO SEGURO — sin hardware]"
        self.setWindowTitle(title)
        self._cwidget = QWidget()
        self.setCentralWidget(self._cwidget)
        self.setMinimumSize(1000, 600)
        self.resize(1440, 900)

        self._setup_menu()
        self._setup_docks()

    def _add_action(self, menu, label, slot, shortcut=None):
        a = QAction(label, self)
        a.triggered.connect(slot)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        menu.addAction(a)

    def _setup_menu(self):
        mb = self.menuBar()
        fm = mb.addMenu("&Files")
        self._add_action(fm, "Seleccionar directorio", lambda: self.selectDirSignal.emit(), "Ctrl+A")
        self._add_action(fm, "Crear directorio diario", lambda: self.createDirSignal.emit(), "Ctrl+S")
        self._add_action(fm, "Abrir directorio", lambda: self.openDirSignal.emit(), "Ctrl+D")
        self._add_action(fm, "Cargar última posición", lambda: self.loadPositionSignal.emit())

        tm = mb.addMenu("&Tools")
        self._add_action(tm, "Tablero de Conexiones", self.tools_hardware_dashboard, "Ctrl+H")
        self._add_action(tm, "Cámara", lambda: (self.cameraWindow.show(), self.cameraWindow.raise_()))
        self._add_action(tm, "Analizador de Imágenes", lambda: (self.imageAnalyzerWindow.show(), self.imageAnalyzerWindow.raise_()))
        self._add_action(tm, "PSF Analyzer", lambda: (self.psfAnalyzerWindow.show(), self.psfAnalyzerWindow.raise_()))
        self._add_action(tm, "Láser 532", lambda: self.laser532Window.show())
        self._add_action(tm, "Load Grid", lambda: self.loadGridSignal.emit())

        mm = mb.addMenu("&Measurements")
        self._add_action(mm, "Printing", lambda: self.printingWidget.show())
        self._add_action(mm, "Dimers", lambda: self.dimersWidget.show())

        dm = mb.addMenu("&Docks")
        self._add_action(dm, "Guardar configuración", self.save_docks)
        self._add_action(dm, "Restaurar configuración", self.load_docks)

        # Barra de Estado Global
        self.statusBar().showMessage("🟢 PyPrinting Contrapropagante listo | Todos los sistemas en estado nominal")

    def _setup_docks(self):
        grid = QGridLayout(self._cwidget)
        grid.setContentsMargins(0, 0, 0, 0)
        self.dockArea = DockArea()
        grid.addWidget(self.dockArea)

        # 1. Confocal Contrapropagante (TOP | CONTROLES | BOT) — Arriba ocupando ancho principal
        confocalDock = Dock("Confocal Contrapropagante Dual (TOP / BOT)", size=(1200, 480))
        self.dual_frontend = ConfocalDualFrontend()
        confocalDock.addWidget(self.dual_frontend)
        self.dockArea.addDock(confocalDock)

        # 2. Focus z — bajo el confocal
        focusDock = Dock("Focus z", size=(260, 180))
        self.focusWidget = FocusFrontend()
        focusDock.addWidget(self.focusWidget)
        self.dockArea.addDock(focusDock, "bottom", confocalDock)

        # 3. Shutters / Flipper / Láser 532 — a la derecha de focus
        shuttersDock = Dock("Shutters / Flipper / Láser 532", size=(360, 180))
        self.shuttersWidget = ShuttersFrontend()
        shuttersDock.addWidget(self.shuttersWidget)
        self.dockArea.addDock(shuttersDock, "right", focusDock)

        # 4. Nanopositioning — a la izquierda de focus
        nanoDock = Dock("Nanopositioning", size=(200, 180))
        self.nanoWidget = NanoFrontend()
        nanoDock.addWidget(self.nanoWidget)
        self.dockArea.addDock(nanoDock, "left", focusDock)

        # 5. Trace — abajo de todo ocupando todo el ancho
        traceDock = Dock("Trace", size=(1400, 240))
        self.traceWidget = TraceFrontend()
        traceDock.addWidget(self.traceWidget)
        self.dockArea.addDock(traceDock, "bottom")

        # Flotantes
        from modules.hardware_dashboard import HardwareDashboardWindow
        self.hardwareWindow = HardwareDashboardWindow()
        self.hardwareWidget = self.hardwareWindow.widget
        self.cameraWindow = CameraWindow()
        self.imageAnalyzerWindow = ImageAnalyzerWindow()
        self.psfAnalyzerWindow = PSFAnalyzerWindow()
        self.laser532Window = Laser532Window()
        self.printingWidget = MeasFrontend(mode="printing")
        self.dimersWidget = MeasFrontend(mode="dimers")

        self.dual_frontend.analyzePSFSignal.connect(self._on_analyze_psf)

    def tools_hardware_dashboard(self):
        self.hardwareWindow.show()
        self.hardwareWindow.raise_()
        self.hardwareWindow.activateWindow()


    def _on_analyze_psf(self):
        img_t = self.dual_frontend.image_top
        img_b = self.dual_frontend.image_bot
        if img_t is None or img_b is None:
            QMessageBox.information(self, "PSF Analyzer", "Realice primero un escaneo dual para analizar las confocales TOP y BOT.")
            return
        px_size = round(float(self.dual_frontend.scanrangeEdit.text()) / int(self.dual_frontend.NxEdit.text()), 4)
        self.psfAnalyzerWindow.load_dual_images(img_t, img_b, px_size)
        self.psfAnalyzerWindow.show()
        self.psfAnalyzerWindow.raise_()
        self.psfAnalyzerWindow.activateWindow()

    def save_docks(self):
        self._dock_state = self.dockArea.saveState()

    def load_docks(self):
        if hasattr(self, "_dock_state"):
            self.dockArea.restoreState(self._dock_state)

    def closeEvent(self, event):
        reply = QMessageBox.question(
            self, "Salir", "¿Cerrar Microscopio Contrapropagante?",
            QMessageBox.StandardButton.No | QMessageBox.StandardButton.Yes)
        if reply == QMessageBox.StandardButton.Yes:
            self.closeSignal.emit()
            event.accept()
        else:
            event.ignore()

    def make_connection(self, backend: Backend):
        backend.nanoWorker.make_connection(self.nanoWidget)
        backend.shuttersWorker.make_connection(self.shuttersWidget)
        backend.focusWorker.make_connection(self.focusWidget)
        backend.traceWorker.make_connection(self.traceWidget)
        backend.confocalDualWorker.make_connection(self.dual_frontend)
        backend.cameraWorker.make_connection(self.cameraWindow)
        backend.laser532Backend.make_connection(self.laser532Window)
        backend.printingWorker.make_connection(self.printingWidget)
        backend.dimersWorker.make_connection(self.dimersWidget)

        # Conectar barra de estado global en tiempo real
        backend.printingWorker.indexSignal.connect(
            lambda i: self.statusBar().showMessage(f"📍 Posicionando e imprimiendo partícula {i}..."))
        backend.printingWorker.grid_autofocusSignal.connect(
            lambda m: self.statusBar().showMessage("🔍 Ejecutando autofoco Z por correlación axial..."))
        backend.printingWorker.grid_traceSignal.connect(
            lambda l, m: self.statusBar().showMessage(f"⚡ Adquiriendo traza fototérmica ({l}) a ALTA potencia..."))
        backend.printingWorker.grid_scanSignal.connect(
            lambda l, m, n: self.statusBar().showMessage(f"🔬 Escaneo confocal dual 2D en curso ({n})..."))
        backend.printingWorker.patternFinishedSignal.connect(
            lambda path: self.statusBar().showMessage(f"🎉 Patrón completado en: {path}"))

        def _on_set_reference(fx: float, fy: float):
            try:
                pos = pi.qPOS()
                x_um = round(pos["1"], 3)
                y_um = round(pos["2"], 3)
                self.cameraWindow.set_ref_pos_um([x_um, y_um, 0])
            except Exception as e:
                print(f"[Contrapropagante] Error leyendo posición PI para referencia: {e}")

        self.cameraWindow.setReferenceSignal.connect(_on_set_reference)

        def _on_file_signal(path: str):
            self.cameraWindow.directorySignal.emit(path)
        backend.fileSignal.connect(_on_file_signal)


# ══════════════════════════════════════════════════════════════════════════════
#  BACKEND PRINCIPAL Y THREADS (Síncrono con app.py)
# ══════════════════════════════════════════════════════════════════════════════

class Backend(QObject):

    fileSignal = pyqtSignal(str)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        pi.connect()

        self.nanoWorker = NanoBackend()
        self.shuttersWorker = ShuttersBackend()
        self.focusWorker = FocusBackend()
        self.traceWorker = TraceBackend()
        self.confocalDualWorker = ConfocalDualBackend()
        self.printingWorker = MeasBackend(mode="printing")
        self.dimersWorker = MeasBackend(mode="dimers")
        self.cameraWorker = CameraBackend()
        self.laser532Backend = Laser532Backend()

        self._connect_backends()

    def _connect_backends(self):
        for sig in (self.focusWorker.gotomaxdoneSignal,
                    self.focusWorker.lockdoneSignal,
                    self.focusWorker.autodoneSignal,
                    self.confocalDualWorker.scanfinishedSignal,
                    self.confocalDualWorker.gridScanFinishedSignal,
                    self.printingWorker.grid_move_finishSignal,
                    self.printingWorker.goSignal,
                    self.dimersWorker.grid_move_finishSignal,
                    self.dimersWorker.goSignal):
            sig.connect(self.nanoWorker.read_pos)

        def _on_autofinish(mode: str):
            if mode == "printing": self.printingWorker.grid_finish_autofoco()
            elif mode == "dimers": self.dimersWorker.grid_finish_autofoco()
        self.focusWorker.autofinishSignal.connect(_on_autofinish)

        self.confocalDualWorker.gridScanFinishedSignal.connect(
            self.printingWorker.on_scan_finished)
        self.confocalDualWorker.gridScanFinishedSignal.connect(
            self.dimersWorker.on_scan_finished)

        def _dispatch_trace(data: list):
            if not data:
                return
            mode    = data[-1] if isinstance(data[-1], str) else "none"
            payload = data[:-1]
            if mode == "printing":
                self.printingWorker.grid_trace_detect(payload)
            elif mode == "dimers":
                self.dimersWorker.grid_trace_detect(payload)

        self.traceWorker.data_printingSignal.connect(_dispatch_trace)

        # Printing cycle
        self.printingWorker.grid_move_finishSignal.connect(
            self.printingWorker.grid_autofoco)
        self.printingWorker.grid_autofocusSignal.connect(
            self.focusWorker.focus_autocorr_lin_x2)
        self.printingWorker.grid_traceSignal.connect(
            self.traceWorker.trace_configuration)
        self.printingWorker.stepsParametersSignal.connect(
            self.traceWorker.parameters)
        self.printingWorker.grid_trace_stopSignal.connect(self.traceWorker.stop)
        self.printingWorker.grid_detectSignal.connect(self.printingWorker.grid_scan)
        self.printingWorker.grid_scanSignal.connect(
            self.confocalDualWorker.start_scan_routines)
        self.printingWorker.grid_scan_stopSignal.connect(
            self.confocalDualWorker.stop_scan)

        # Dimers cycle
        self.dimersWorker.grid_move_finishSignal.connect(
            self.dimersWorker.grid_autofoco)
        self.dimersWorker.grid_autofocusSignal.connect(
            self.focusWorker.focus_autocorr_lin_x2)
        self.dimersWorker.grid_traceSignal.connect(
            self.traceWorker.trace_configuration)
        self.dimersWorker.stepsParametersSignal.connect(
            self.traceWorker.parameters)
        self.dimersWorker.grid_trace_stopSignal.connect(self.traceWorker.stop)
        self.dimersWorker.grid_detectSignal.connect(self.dimersWorker.grid_finish)
        self.dimersWorker.grid_scanSignal.connect(
            self.confocalDualWorker.start_scan_routines)
        self.dimersWorker.grid_scan_stopSignal.connect(
            self.confocalDualWorker.stop_scan)


def main():
    app = QApplication(sys.argv)

    # Inicializar Hilos e Instrumentos
    instrumentThread = QThread()
    confocalThread = QThread()
    cameraThread = QThread()

    backend = Backend()
    win = ContrapropaganteMainWindow()
    win.make_connection(backend)

    backend.nanoWorker.moveToThread(instrumentThread)
    backend.shuttersWorker.moveToThread(instrumentThread)
    backend.laser532Backend.moveToThread(instrumentThread)

    backend.confocalDualWorker.moveToThread(confocalThread)
    backend.focusWorker.moveToThread(confocalThread)
    backend.traceWorker.moveToThread(confocalThread)
    backend.printingWorker.moveToThread(confocalThread)
    backend.dimersWorker.moveToThread(confocalThread)

    backend.cameraWorker.moveToThread(cameraThread)

    instrumentThread.start()
    confocalThread.start()
    cameraThread.start()

    win.show()
    ret = app.exec()

    instrumentThread.quit(); instrumentThread.wait()
    confocalThread.quit();   confocalThread.wait()
    cameraThread.quit();     cameraThread.wait()

    sys.exit(ret)


if __name__ == "__main__":
    main()
