# -*- coding: utf-8 -*-
"""
calibration_dock.py — Pestaña Modular de Calibraciones del Sistema
PySpectrum 3.0 — UNSAM Nanofotónica

Provee paneles modulares ("ventanitas") para:
1. Ranura de Entrada & Pixel X Central del Slit (Alineación Orden Cero y ajuste gaussiano).
2. Offset de Rejillas & Detector según SDK Andor Shamrock (ShamrockCIF.dll).
3. Coeficientes Cúbicos de Calibración de Longitud de Onda (EEPROM).
4. Calibración de Respuesta Espectral con Lámpara Halógena.
"""
from __future__ import annotations
import os
import json
import time
from pathlib import Path
from typing import Tuple, Optional

import numpy as np
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import pyqtSignal, pyqtSlot
import pyqtgraph as pg

from config import (
    SAFE_MODE,
    ANDOR_FLIP_Y_IMAGE,
    ANDOR_FLIP_X_IMAGE
)
from pyspectrum.drivers.shamrock_driver import (
    DEVICE,
    INPUT_SLIT_PORT,
    GRATING_150_LINES,
    GRATING_1200_LINES,
    GRATING_MIRROR,
    SHAMROCK_SUCCESS,
    get_shamrock
)
from pyspectrum.drivers.andor_ccd_driver import get_andor_ccd
from pyspectrum.calibration.halogen_lamp import HalogenLampCalibration

# Archivo de persistencia de calibración local
CALIBRATION_FILE = Path(__file__).resolve().parent.parent / "calibration" / "pyspectrum_calibration.json"


class CalibrationFrontend(QtWidgets.QFrame):
    """Interfaz gráfica modular con ventanitas de calibración del sistema."""

    gotoZeroOrderSignal = pyqtSignal()
    setSlitWidthSignal = pyqtSignal(float)
    getSlitZeroPosSignal = pyqtSignal(int)
    setSlitZeroPosSignal = pyqtSignal(int, int)
    saveSlitPixelSignal = pyqtSignal(float)
    autoCalibrateSlitSignal = pyqtSignal()

    getGratingOffsetSignal = pyqtSignal(int)
    setGratingOffsetSignal = pyqtSignal(int, int)
    getDetectorOffsetSignal = pyqtSignal()
    setDetectorOffsetSignal = pyqtSignal(int)

    readCubicCoeffsSignal = pyqtSignal()
    loadLampCalibSignal = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.setStyleSheet("""
            QFrame {
                background-color: #1E1E2E;
                border-radius: 6px;
            }
            QLabel {
                color: #CDD6F4;
            }
            QGroupBox {
                color: #89B4FA;
                font-weight: bold;
                border: 1px solid #45475A;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 6px;
                background-color: #1E1E2E;
            }
            QPushButton {
                background-color: #313244;
                color: #CDD6F4;
                border: 1px solid #45475A;
                border-radius: 4px;
                padding: 5px 10px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45475A;
                color: #89B4FA;
            }
            QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
                background-color: #11111B;
                color: #CDD6F4;
                border: 1px solid #45475A;
                border-radius: 4px;
                padding: 3px 6px;
            }
        """)
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QtWidgets.QHBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(12)

        # Scroll area para albergar las ventanitas de calibración
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        container = QtWidgets.QWidget()
        vbox = QtWidgets.QVBoxLayout(container)
        vbox.setSpacing(12)

        # ── 1. Ventanita: Slit & Pixel X Central ──────────────────────────────
        box_slit = QtWidgets.QGroupBox("🪟 1. Ranura de Entrada (Slit) & Centroide Óptico X")
        slit_layout = QtWidgets.QGridLayout(box_slit)
        slit_layout.setSpacing(6)

        self.btn_zero_order = QtWidgets.QPushButton("🎯 Mover a Orden Cero (0.0 nm)")
        self.btn_zero_order.setStyleSheet("background-color: #89B4FA; color: #11111B;")
        self.btn_zero_order.clicked.connect(self.gotoZeroOrderSignal.emit)
        slit_layout.addWidget(self.btn_zero_order, 0, 0, 1, 2)

        slit_layout.addWidget(QtWidgets.QLabel("Ancho Ranura (µm):"), 1, 0)
        self.spin_slit_width = QtWidgets.QDoubleSpinBox()
        self.spin_slit_width.setRange(10.0, 2500.0)
        self.spin_slit_width.setValue(50.0)
        self.spin_slit_width.setSuffix(" µm")
        slit_layout.addWidget(self.spin_slit_width, 1, 1)

        btn_apply_slit = QtWidgets.QPushButton("Aplicar Ancho")
        btn_apply_slit.clicked.connect(lambda: self.setSlitWidthSignal.emit(self.spin_slit_width.value()))
        slit_layout.addWidget(btn_apply_slit, 1, 2)

        # Accesos rápidos de ancho
        quick_box = QtWidgets.QHBoxLayout()
        for w in [10, 50, 100, 500]:
            b = QtWidgets.QPushButton(f"{w}µm")
            b.setStyleSheet("padding: 2px 6px; font-size: 8pt;")
            b.clicked.connect(lambda _, val=float(w): self._quick_set_slit(val))
            quick_box.addWidget(b)
        slit_layout.addLayout(quick_box, 2, 0, 1, 3)

        # Pixel X central del Slit
        slit_layout.addWidget(QtWidgets.QLabel("Pixel X Central del Slit:"), 3, 0)
        self.spin_pixel_x = QtWidgets.QDoubleSpinBox()
        self.spin_pixel_x.setRange(0.0, 1024.0)
        self.spin_pixel_x.setDecimals(2)
        self.spin_pixel_x.setValue(501.0)
        self.spin_pixel_x.setSuffix(" px")
        slit_layout.addWidget(self.spin_pixel_x, 3, 1)

        btn_save_px = QtWidgets.QPushButton("💾 Guardar Pixel X")
        btn_save_px.clicked.connect(lambda: self.saveSlitPixelSignal.emit(self.spin_pixel_x.value()))
        slit_layout.addWidget(btn_save_px, 3, 2)

        self.btn_auto_slit = QtWidgets.QPushButton("🔍 Auto-Calibrar Centroide X (Ajuste Gaussiano)")
        self.btn_auto_slit.setStyleSheet("background-color: #A6E3A1; color: #11111B;")
        self.btn_auto_slit.clicked.connect(self.autoCalibrateSlitSignal.emit)
        slit_layout.addWidget(self.btn_auto_slit, 4, 0, 1, 3)

        # Slit Zero Position SDK
        slit_layout.addWidget(QtWidgets.QLabel("Slit Zero Pos (SDK steps):"), 5, 0)
        self.spin_slit_zero = QtWidgets.QSpinBox()
        self.spin_slit_zero.setRange(-10000, 10000)
        slit_layout.addWidget(self.spin_slit_zero, 5, 1)

        btn_set_sz = QtWidgets.QPushButton("Escribir SDK")
        btn_set_sz.clicked.connect(lambda: self.setSlitZeroPosSignal.emit(INPUT_SLIT_PORT, self.spin_slit_zero.value()))
        slit_layout.addWidget(btn_set_sz, 5, 2)

        vbox.addWidget(box_slit)

        # ── 2. Ventanita: Offset de Rejillas & Detector (SDK) ─────────────────
        box_offset = QtWidgets.QGroupBox("⚙️ 2. Offsets de Rejilla & Detector (Shamrock SDK Oficial)")
        off_layout = QtWidgets.QGridLayout(box_offset)
        off_layout.setSpacing(6)

        off_layout.addWidget(QtWidgets.QLabel("Rejilla / Torret:"), 0, 0)
        self.combo_grating = QtWidgets.QComboBox()
        self.combo_grating.addItem("1: 150 l/mm (Blaze 800 nm)", 1)
        self.combo_grating.addItem("2: 1200 l/mm (Blaze 500 nm)", 2)
        self.combo_grating.addItem("3: Espejo (Mirror)", 3)
        self.combo_grating.currentIndexChanged.connect(self._on_grating_combo_changed)
        off_layout.addWidget(self.combo_grating, 0, 1, 1, 2)

        off_layout.addWidget(QtWidgets.QLabel("Grating Offset (pasos):"), 1, 0)
        self.spin_grating_off = QtWidgets.QSpinBox()
        self.spin_grating_off.setRange(-50000, 50000)
        off_layout.addWidget(self.spin_grating_off, 1, 1)

        btn_set_go = QtWidgets.QPushButton("💾 Escribir Rejilla")
        btn_set_go.clicked.connect(self._on_write_grating_offset)
        off_layout.addWidget(btn_set_go, 1, 2)

        off_layout.addWidget(QtWidgets.QLabel("Detector Offset (pasos):"), 2, 0)
        self.spin_detector_off = QtWidgets.QSpinBox()
        self.spin_detector_off.setRange(-50000, 50000)
        off_layout.addWidget(self.spin_detector_off, 2, 1)

        btn_set_do = QtWidgets.QPushButton("💾 Escribir Detector")
        btn_set_do.clicked.connect(lambda: self.setDetectorOffsetSignal.emit(self.spin_detector_off.value()))
        off_layout.addWidget(btn_set_do, 2, 2)

        btn_read_offsets = QtWidgets.QPushButton("📥 Leer Offsets de Hardware (SDK)")
        btn_read_offsets.setStyleSheet("background-color: #F9E2AF; color: #11111B;")
        btn_read_offsets.clicked.connect(self._on_read_all_offsets)
        off_layout.addWidget(btn_read_offsets, 3, 0, 1, 3)

        vbox.addWidget(box_offset)

        # ── 3. Ventanita: Coeficientes Cúbicos EEPROM ─────────────────────────
        box_cubic = QtWidgets.QGroupBox("📐 3. Calibración Cúbica λ(p) de Fábrica (EEPROM)")
        cubic_layout = QtWidgets.QGridLayout(box_cubic)
        cubic_layout.setSpacing(6)

        self.lbl_cubic_formula = QtWidgets.QLabel("λ(p) = a + b·p + c·p² + d·p³")
        self.lbl_cubic_formula.setStyleSheet("color: #F5C2E7; font-weight: bold; font-family: monospace;")
        cubic_layout.addWidget(self.lbl_cubic_formula, 0, 0, 1, 2)

        cubic_layout.addWidget(QtWidgets.QLabel("a (Offset λ):"), 1, 0)
        self.edit_a = QtWidgets.QLineEdit("0.0")
        self.edit_a.setReadOnly(True)
        cubic_layout.addWidget(self.edit_a, 1, 1)

        cubic_layout.addWidget(QtWidgets.QLabel("b (Dispersión nm/px):"), 2, 0)
        self.edit_b = QtWidgets.QLineEdit("0.0")
        self.edit_b.setReadOnly(True)
        cubic_layout.addWidget(self.edit_b, 2, 1)

        cubic_layout.addWidget(QtWidgets.QLabel("c (Término cuadrático):"), 3, 0)
        self.edit_c = QtWidgets.QLineEdit("0.0")
        self.edit_c.setReadOnly(True)
        cubic_layout.addWidget(self.edit_c, 3, 1)

        cubic_layout.addWidget(QtWidgets.QLabel("d (Término cúbico):"), 4, 0)
        self.edit_d = QtWidgets.QLineEdit("0.0")
        self.edit_d.setReadOnly(True)
        cubic_layout.addWidget(self.edit_d, 4, 1)

        btn_read_cubic = QtWidgets.QPushButton("📥 Leer Coeficientes EEPROM")
        btn_read_cubic.clicked.connect(self.readCubicCoeffsSignal.emit)
        cubic_layout.addWidget(btn_read_cubic, 5, 0, 1, 2)

        vbox.addWidget(box_cubic)

        # ── 4. Ventanita: Lámpara Halógena ────────────────────────────────────
        box_lamp = QtWidgets.QGroupBox("💡 4. Calibración de Intensidad (Lámpara Halógena)")
        lamp_layout = QtWidgets.QGridLayout(box_lamp)
        lamp_layout.setSpacing(6)

        self.lbl_lamp_status = QtWidgets.QLabel("Perfil halógeno: Modelo Planck Activo (T=3100 K)")
        self.lbl_lamp_status.setStyleSheet("color: #A6E3A1; font-size: 8.5pt;")
        lamp_layout.addWidget(self.lbl_lamp_status, 0, 0, 1, 2)

        self.btn_load_lamp = QtWidgets.QPushButton("📂 Cargar Espectro de Calibración Halógena...")
        self.btn_load_lamp.clicked.connect(self._on_load_lamp_file)
        lamp_layout.addWidget(self.btn_load_lamp, 1, 0, 1, 2)

        vbox.addWidget(box_lamp)

        # Barra de estado local
        self.lbl_status = QtWidgets.QLabel("Listo para calibrar.")
        self.lbl_status.setStyleSheet("color: #A6ADC8; font-size: 9pt; font-weight: bold;")
        vbox.addWidget(self.lbl_status)

        vbox.addStretch()
        scroll.setWidget(container)
        main_layout.addWidget(scroll, stretch=2)

        # ── Gráfico Lateral de Ajuste y Perfil ────────────────────────────────
        self.plot_widget = pg.PlotWidget(title="<b>Perfil Óptico / Ajuste de Calibración</b>")
        self.plot_widget.setLabels(bottom="Coordenada / Pixel X", left="Intensidad (Cuentas)")
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.addLegend(offset=(10, 10))

        self.curve_profile = self.plot_widget.plot(name="Perfil Medido", pen=pg.mkPen("#89B4FA", width=2.0))
        self.curve_fit = self.plot_widget.plot(name="Ajuste Gaussiano", pen=pg.mkPen("#F38BA8", width=2.5, style=QtCore.Qt.PenStyle.DashLine))
        self.line_center = pg.InfiniteLine(pos=501.0, angle=90, pen=pg.mkPen("#A6E3A1", width=2.0, style=QtCore.Qt.PenStyle.DotLine), label="Centro Slit")
        self.plot_widget.addItem(self.line_center)

        main_layout.addWidget(self.plot_widget, stretch=3)

    def _quick_set_slit(self, val: float):
        self.spin_slit_width.setValue(val)
        self.setSlitWidthSignal.emit(val)

    def _on_grating_combo_changed(self):
        grating = self.combo_grating.currentData()
        if grating is not None:
            self.getGratingOffsetSignal.emit(int(grating))

    def _on_write_grating_offset(self):
        grating = self.combo_grating.currentData()
        offset = self.spin_grating_off.value()
        if grating is not None:
            self.setGratingOffsetSignal.emit(int(grating), offset)

    def _on_read_all_offsets(self):
        grating = self.combo_grating.currentData()
        if grating is not None:
            self.getGratingOffsetSignal.emit(int(grating))
        self.getDetectorOffsetSignal.emit()
        self.getSlitZeroPosSignal.emit(INPUT_SLIT_PORT)

    def _on_load_lamp_file(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Cargar Archivo de Lámpara Halógena", "", "Archivos de Datos (*.txt *.csv *.dat);;Todos (*.*)"
        )
        if path:
            self.loadLampCalibSignal.emit(path)

    @pyqtSlot(float, int)
    def update_slit_info(self, width: float, zero_pos: int):
        self.spin_slit_width.blockSignals(True)
        self.spin_slit_width.setValue(width)
        self.spin_slit_width.blockSignals(False)

        self.spin_slit_zero.blockSignals(True)
        self.spin_slit_zero.setValue(zero_pos)
        self.spin_slit_zero.blockSignals(False)
        self.lbl_status.setText(f"Slit actualizado: {width:.1f} µm (Zero pos: {zero_pos})")

    @pyqtSlot(int, int)
    def update_grating_offset(self, grating: int, offset: int):
        self.spin_grating_off.blockSignals(True)
        self.spin_grating_off.setValue(offset)
        self.spin_grating_off.blockSignals(False)
        self.lbl_status.setText(f"Offset Rejilla {grating}: {offset} pasos.")

    @pyqtSlot(int)
    def update_detector_offset(self, offset: int):
        self.spin_detector_off.blockSignals(True)
        self.spin_detector_off.setValue(offset)
        self.spin_detector_off.blockSignals(False)
        self.lbl_status.setText(f"Offset Detector: {offset} pasos.")

    @pyqtSlot(float, float, float, float)
    def update_cubic_coefficients(self, a: float, b: float, c: float, d: float):
        self.edit_a.setText(f"{a:.6f}")
        self.edit_b.setText(f"{b:.6f}")
        self.edit_c.setText(f"{c:.6e}")
        self.edit_d.setText(f"{d:.6e}")
        self.lbl_status.setText(f"Coeficientes EEPROM leídos. Dispersión: {b:.4f} nm/px.")

    @pyqtSlot(float, float, np.ndarray, np.ndarray, np.ndarray)
    def update_slit_fit_result(self, centroid_x: float, fwhm: float, x_data: np.ndarray, y_data: np.ndarray, fit_data: np.ndarray):
        self.spin_pixel_x.setValue(centroid_x)
        self.line_center.setValue(centroid_x)
        self.curve_profile.setData(x_data, y_data)
        if len(fit_data) == len(x_data):
            self.curve_fit.setData(x_data, fit_data)
        self.lbl_status.setText(f"Ajuste Slit: <b>Centroide X = {centroid_x:.2f} px</b> (FWHM = {fwhm:.2f} px)")

    @pyqtSlot(str)
    def show_status(self, msg: str):
        self.lbl_status.setText(msg)


class CalibrationBackend(QtCore.QObject):
    """Backend de gestión y sincronización de calibraciones ópticas."""

    slitInfoUpdatedSignal = pyqtSignal(float, int)
    gratingOffsetUpdatedSignal = pyqtSignal(int, int)
    detectorOffsetUpdatedSignal = pyqtSignal(int)
    cubicCoeffsUpdatedSignal = pyqtSignal(float, float, float, float)
    slitFitResultSignal = pyqtSignal(float, float, np.ndarray, np.ndarray, np.ndarray)
    statusSignal = pyqtSignal(str)

    def __init__(self, camera=None, spectrometer=None, parent=None):
        super().__init__(parent)
        self.camera = camera or get_andor_ccd()
        self.spectrometer = spectrometer or get_shamrock()
        self.lamp_calib = HalogenLampCalibration()
        self.slit_center_x = 501.0
        self._load_saved_calibration()

    def make_connection(self, frontend: CalibrationFrontend):
        frontend.gotoZeroOrderSignal.connect(self.goto_zero_order)
        frontend.setSlitWidthSignal.connect(self.set_slit_width)
        frontend.getSlitZeroPosSignal.connect(self.get_slit_zero_position)
        frontend.setSlitZeroPosSignal.connect(self.set_slit_zero_position)
        frontend.saveSlitPixelSignal.connect(self.save_slit_pixel)
        frontend.autoCalibrateSlitSignal.connect(self.auto_calibrate_slit)

        frontend.getGratingOffsetSignal.connect(self.get_grating_offset)
        frontend.setGratingOffsetSignal.connect(self.set_grating_offset)
        frontend.getDetectorOffsetSignal.connect(self.get_detector_offset)
        frontend.setDetectorOffsetSignal.connect(self.set_detector_offset)

        frontend.readCubicCoeffsSignal.connect(self.read_cubic_coefficients)
        frontend.loadLampCalibSignal.connect(self.load_lamp_calibration)

        self.slitInfoUpdatedSignal.connect(frontend.update_slit_info)
        self.gratingOffsetUpdatedSignal.connect(frontend.update_grating_offset)
        self.detectorOffsetUpdatedSignal.connect(frontend.update_detector_offset)
        self.cubicCoeffsUpdatedSignal.connect(frontend.update_cubic_coefficients)
        self.slitFitResultSignal.connect(frontend.update_slit_fit_result)
        self.statusSignal.connect(frontend.show_status)

        # Iniciar valores en UI
        frontend.spin_pixel_x.setValue(self.slit_center_x)
        self.read_initial_values()

    def read_initial_values(self):
        """Lee los valores actuales del hardware e inicializa la vista."""
        try:
            ret, w = self.spectrometer.ShamrockGetSlit(DEVICE, INPUT_SLIT_PORT)
            ret_z, z = self.spectrometer.ShamrockGetSlitZeroPosition(DEVICE, INPUT_SLIT_PORT)
            self.slitInfoUpdatedSignal.emit(float(w), int(z))

            ret_g, g = self.spectrometer.ShamrockGetGrating(DEVICE)
            ret_go, go = self.spectrometer.ShamrockGetGratingOffset(DEVICE, g)
            self.gratingOffsetUpdatedSignal.emit(int(g), int(go))

            ret_do, do = self.spectrometer.ShamrockGetDetectorOffset(DEVICE)
            self.detectorOffsetUpdatedSignal.emit(int(do))

            self.read_cubic_coefficients()
        except Exception as e:
            print(f"[Calib Backend] Excepción al leer hardware inicial: {e}")

    @pyqtSlot()
    def goto_zero_order(self):
        ret = self.spectrometer.ShamrockGotoZeroOrder(DEVICE)
        if ret == SHAMROCK_SUCCESS:
            self.statusSignal.emit("Red movida a Orden Cero (0.0 nm). Reflexión directa lista.")
        else:
            self.statusSignal.emit(f"Error al mover a Orden Cero. Código: {ret}")

    @pyqtSlot(float)
    def set_slit_width(self, width: float):
        ret = self.spectrometer.ShamrockSetSlit(DEVICE, INPUT_SLIT_PORT, float(width))
        if ret == SHAMROCK_SUCCESS:
            self.statusSignal.emit(f"Ancho de ranura ajustado a {width:.1f} µm.")
        else:
            self.statusSignal.emit(f"Error al ajustar ranura ({ret}).")

    @pyqtSlot(int)
    def get_slit_zero_position(self, index: int):
        ret, val = self.spectrometer.ShamrockGetSlitZeroPosition(DEVICE, index)
        self.statusSignal.emit(f"Slit Zero Position leído: {val} pasos.")

    @pyqtSlot(int, int)
    def set_slit_zero_position(self, index: int, offset: int):
        ret = self.spectrometer.ShamrockSetSlitZeroPosition(DEVICE, index, int(offset))
        if ret == SHAMROCK_SUCCESS:
            self.statusSignal.emit(f"Slit Zero Position aplicado: {offset} pasos.")
        else:
            self.statusSignal.emit(f"Error al escribir Slit Zero Position ({ret}).")

    @pyqtSlot(int)
    def get_grating_offset(self, grating: int):
        ret, off = self.spectrometer.ShamrockGetGratingOffset(DEVICE, int(grating))
        self.gratingOffsetUpdatedSignal.emit(int(grating), int(off))

    @pyqtSlot(int, int)
    def set_grating_offset(self, grating: int, offset: int):
        ret = self.spectrometer.ShamrockSetGratingOffset(DEVICE, int(grating), int(offset))
        if ret == SHAMROCK_SUCCESS:
            self.statusSignal.emit(f"Offset de Rejilla {grating} actualizado a {offset} pasos.")
            self.gratingOffsetUpdatedSignal.emit(int(grating), int(offset))
        else:
            self.statusSignal.emit(f"Error al fijar offset de rejilla ({ret}).")

    @pyqtSlot()
    def get_detector_offset(self):
        ret, off = self.spectrometer.ShamrockGetDetectorOffset(DEVICE)
        self.detectorOffsetUpdatedSignal.emit(int(off))

    @pyqtSlot(int)
    def set_detector_offset(self, offset: int):
        ret = self.spectrometer.ShamrockSetDetectorOffset(DEVICE, int(offset))
        if ret == SHAMROCK_SUCCESS:
            self.statusSignal.emit(f"Offset de detector actualizado a {offset} pasos.")
            self.detectorOffsetUpdatedSignal.emit(int(offset))
        else:
            self.statusSignal.emit(f"Error al fijar offset del detector ({ret}).")

    @pyqtSlot()
    def read_cubic_coefficients(self):
        ret, (a, b, c, d) = self.spectrometer.get_pixel_calibration_coefficients(DEVICE)
        self.cubicCoeffsUpdatedSignal.emit(float(a), float(b), float(c), float(d))

    @pyqtSlot(float)
    def save_slit_pixel(self, pixel_x: float):
        self.slit_center_x = float(pixel_x)
        self._save_calibration_file()
        self.statusSignal.emit(f"Pixel X central {pixel_x:.2f} px guardado en configuración.")

    @pyqtSlot()
    def auto_calibrate_slit(self):
        """Adquiere el perfil actual de la ranura en Orden Cero y realiza un ajuste Gaussiano."""
        try:
            # 1. Obtener imagen o perfil 1D
            if hasattr(self.camera, "get_most_recent_image"):
                img = self.camera.get_most_recent_image()
                # Proyección horizontal (sumando filas o perfil central)
                if img.ndim == 2:
                    y_mid = img.shape[0] // 2
                    sub_y = img[max(0, y_mid - 20): min(img.shape[0], y_mid + 20), :]
                    profile = np.mean(sub_y, axis=0)
                else:
                    profile = img
            else:
                profile = np.ones(1002, dtype=np.float64) * 100.0

            x = np.arange(len(profile), dtype=np.float64)
            y = np.array(profile, dtype=np.float64)

            # 2. Ajuste Gaussiano
            centroid, fwhm, fit_curve = self._fit_gaussian_slit(x, y)
            self.slit_center_x = centroid
            self._save_calibration_file()

            self.slitFitResultSignal.emit(float(centroid), float(fwhm), x, y, fit_curve)
        except Exception as e:
            self.statusSignal.emit(f"Error en auto-calibración: {e}")

    def _fit_gaussian_slit(self, x: np.ndarray, y: np.ndarray) -> Tuple[float, float, np.ndarray]:
        """Ajusta un modelo Gaussiano sobre el perfil de intensidad del slit."""
        from scipy.optimize import curve_fit

        # Estimaciones iniciales
        bg = np.percentile(y, 10)
        amp = np.max(y) - bg
        x0_guess = float(x[np.argmax(y)])
        sigma_guess = 5.0

        def gauss(p, a, x0, sig, c):
            return a * np.exp(-((p - x0) ** 2) / (2.0 * sig ** 2)) + c

        try:
            popt, _ = curve_fit(gauss, x, y, p0=[amp, x0_guess, sigma_guess, bg], maxfev=2000)
            a_fit, x0_fit, sig_fit, c_fit = popt
            fwhm = 2.355 * abs(sig_fit)
            fit_curve = gauss(x, *popt)
            return (float(x0_fit), float(fwhm), fit_curve)
        except Exception:
            # Fallback por centro de gravedad
            weights = np.maximum(0, y - bg)
            if np.sum(weights) > 0:
                cg = float(np.sum(x * weights) / np.sum(weights))
            else:
                cg = float(x0_guess)
            return (cg, 10.0, np.array([]))

    @pyqtSlot(str)
    def load_lamp_calibration(self, filepath: str):
        try:
            # Validar carga de archivo
            data = np.loadtxt(filepath)
            self.statusSignal.emit(f"Espectro halógeno cargado con éxito ({len(data)} puntos).")
        except Exception as e:
            self.statusSignal.emit(f"Error al cargar archivo halógeno: {e}")

    def _load_saved_calibration(self):
        if CALIBRATION_FILE.exists():
            try:
                with open(CALIBRATION_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.slit_center_x = float(data.get("slit_center_pixel_x", 501.0))
            except Exception:
                self.slit_center_x = 501.0

    def _save_calibration_file(self):
        try:
            CALIBRATION_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = {"slit_center_pixel_x": self.slit_center_x}
            with open(CALIBRATION_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"[Calib Backend] Error al persistir calibración: {e}")
