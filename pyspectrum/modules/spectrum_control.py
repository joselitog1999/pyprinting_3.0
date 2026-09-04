# -*- coding: utf-8 -*-
"""
spectrum_control.py — Panel de Control del Espectrógrafo Andor Shamrock
PySpectrum 3.0 — UNSAM Nanofotónica
"""
from __future__ import annotations
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import pyqtSignal, pyqtSlot
import numpy as np

from pyspectrum.drivers.shamrock_driver import (
    DEVICE, GRATING_150_LINES, GRATING_1200_LINES, GRATING_MIRROR,
    NAME_GRATINGS, NAME_PORTS_IN, NAME_PORTS_OUT, get_shamrock
)


class Frontend(QtWidgets.QFrame):
    """Interfaz gráfica de control para el espectrógrafo Shamrock."""

    setGratingSignal = pyqtSignal(int)
    setWavelengthSignal = pyqtSignal(float)
    setSlitSignal = pyqtSignal(int, float)
    setShutterSignal = pyqtSignal(int)
    setFlipperSignal = pyqtSignal(int, int)
    requestCalibrationSignal = pyqtSignal()

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
                font-weight: bold;
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
            QComboBox, QLineEdit {
                background-color: #11111B;
                color: #CDD6F4;
                border: 1px solid #45475A;
                border-radius: 4px;
                padding: 4px;
            }
        """)
        self._setup_ui()

    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # ── Título ────────────────────────────────────────────────────────────
        lbl_title = QtWidgets.QLabel("🌈 <b>Control de Espectrógrafo (Andor Shamrock)</b>")
        lbl_title.setStyleSheet("font-size: 10pt; color: #89B4FA;")
        layout.addWidget(lbl_title)

        grid = QtWidgets.QGridLayout()
        grid.setSpacing(8)

        # 1. Red de Difracción
        grid.addWidget(QtWidgets.QLabel("Red de Difracción:"), 0, 0)
        self.cmb_grating = QtWidgets.QComboBox()
        self.cmb_grating.addItems(NAME_GRATINGS)
        self.cmb_grating.currentIndexChanged.connect(self._on_grating_changed)
        grid.addWidget(self.cmb_grating, 0, 1)

        # 2. Longitud de Onda Central (nm)
        grid.addWidget(QtWidgets.QLabel("Longitud de Onda Central (nm):"), 1, 0)
        self.edit_wavelength = QtWidgets.QLineEdit("532.00")
        self.edit_wavelength.returnPressed.connect(self._on_wavelength_changed)
        grid.addWidget(self.edit_wavelength, 1, 1)

        # 3. Ancho de Ranura (Slit en µm: 10 a 2500 µm)
        grid.addWidget(QtWidgets.QLabel("Ancho Ranura (10–2500 µm):"), 2, 0)
        self.edit_slit = QtWidgets.QLineEdit("50.0")
        self.edit_slit.setToolTip(
            "Ancho motorizado de la ranura de entrada (10 µm a 2500 µm).\n"
            "• 40–50 µm: Raman confocal óptimo (1 Airy Disk).\n"
            "• 100–500 µm: Alto flujo / cinética de crecimiento.\n"
            "• 2500 µm: Apertura máxima (90 µm en muestra / imagen directa)."
        )
        self.edit_slit.returnPressed.connect(self._on_slit_changed)
        grid.addWidget(self.edit_slit, 2, 1)

        # 4. Flipper Entrada (Fibra vs Ranura)
        grid.addWidget(QtWidgets.QLabel("Puerto Entrada (Flipper IN):"), 3, 0)
        self.cmb_flipper_in = QtWidgets.QComboBox()
        self.cmb_flipper_in.addItems(NAME_PORTS_IN)
        self.cmb_flipper_in.currentIndexChanged.connect(lambda idx: self.setFlipperSignal.emit(1, idx))
        grid.addWidget(self.cmb_flipper_in, 3, 1)

        # 5. Obturador del Espectrógrafo
        self.btn_shutter = QtWidgets.QPushButton("🟢 Obturador Espectrógrafo: ABIERTO")
        self.btn_shutter.setCheckable(True)
        self.btn_shutter.setChecked(True)
        self.btn_shutter.clicked.connect(self._on_toggle_shutter)
        grid.addWidget(self.btn_shutter, 4, 0, 1, 2)

        layout.addLayout(grid)

        # Barra de información de dispersión
        self.lbl_info = QtWidgets.QLabel("Rango espectral en detector: ~350 nm a 710 nm")
        self.lbl_info.setStyleSheet("color: #A6ADC8; font-size: 8.5pt; font-style: italic;")
        layout.addWidget(self.lbl_info)

        layout.addStretch()

    def _on_grating_changed(self, idx: int):
        self.setGratingSignal.emit(idx + 1)

    def _on_wavelength_changed(self):
        try:
            wl = float(self.edit_wavelength.text())
            self.setWavelengthSignal.emit(wl)
        except ValueError:
            pass

    def _on_slit_changed(self):
        try:
            w = float(self.edit_slit.text())
            self.setSlitSignal.emit(1, w)
        except ValueError:
            pass

    def _on_toggle_shutter(self, checked: bool):
        if checked:
            self.btn_shutter.setText("🟢 Obturador Espectrógrafo: ABIERTO")
            self.btn_shutter.setStyleSheet("background-color: #A6E3A1; color: #11111B;")
            self.setShutterSignal.emit(1)
        else:
            self.btn_shutter.setText("🔴 Obturador Espectrógrafo: CERRADO")
            self.btn_shutter.setStyleSheet("background-color: #F38BA8; color: #11111B;")
            self.setShutterSignal.emit(0)

    @pyqtSlot(float, float, float)
    def update_calibration_display(self, wl_center: float, wl_min: float, wl_max: float):
        span = wl_max - wl_min
        disp_nm_px = span / 1002.0 if span > 0 else 0.0
        # Dispersión en número de onda cm^-1 por pixel a la longitud de onda central
        if wl_center > 0 and disp_nm_px > 0:
            disp_cm1_px = (1e7 / wl_center**2) * disp_nm_px
        else:
            disp_cm1_px = 0.0
        self.lbl_info.setText(
            f"Centro: <b>{wl_center:.2f} nm</b> | Ventana CCD: <b>{wl_min:.1f} — {wl_max:.1f} nm</b> (Δλ: {span:.1f} nm)<br>"
            f"Dispersión lineal: <b>{disp_nm_px:.3f} nm/px</b> (≈ <b>{disp_cm1_px:.2f} cm⁻¹/px</b> a {wl_center:.0f} nm)"
        )


class Backend(QtCore.QObject):
    """Lógica y despacho de comandos hacia el espectrógrafo Andor Shamrock."""

    calibrationUpdatedSignal = pyqtSignal(float, float, float)
    wavelengthAxisSignal = pyqtSignal(np.ndarray)

    def __init__(self, spectrometer=None, parent=None):
        super().__init__(parent)
        self.spectrometer = spectrometer or get_shamrock()
        self.wavelength_axis = np.linspace(400, 700, 1002)

    def make_connection(self, frontend: Frontend):
        frontend.setGratingSignal.connect(self.set_grating)
        frontend.setWavelengthSignal.connect(self.set_wavelength)
        frontend.setSlitSignal.connect(self.set_slit)
        frontend.setShutterSignal.connect(self.set_shutter)
        frontend.setFlipperSignal.connect(self.set_flipper)
        frontend.requestCalibrationSignal.connect(self.update_calibration)

        self.calibrationUpdatedSignal.connect(frontend.update_calibration_display)
        self.update_calibration()

    @pyqtSlot(int)
    def set_grating(self, grating: int):
        self.spectrometer.ShamrockSetGrating(DEVICE, grating)
        self.update_calibration()

    @pyqtSlot(float)
    def set_wavelength(self, wl: float):
        self.spectrometer.ShamrockSetWavelength(DEVICE, wl)
        self.update_calibration()

    @pyqtSlot(int, float)
    def set_slit(self, index: int, width: float):
        self.spectrometer.ShamrockSetSlit(DEVICE, index, width)

    @pyqtSlot(int)
    def set_shutter(self, mode: int):
        self.spectrometer.ShamrockSetShutter(DEVICE, mode)

    @pyqtSlot(int, int)
    def set_flipper(self, flipper: int, port: int):
        self.spectrometer.ShamrockSetFlipper(DEVICE, flipper, port)

    @pyqtSlot()
    def update_calibration(self):
        ret, wl_center = self.spectrometer.ShamrockGetWavelength(DEVICE)
        ret, wl_arr = self.spectrometer.ShamrockGetCalibration(DEVICE, 1002)
        self.wavelength_axis = wl_arr
        self.calibrationUpdatedSignal.emit(wl_center, float(wl_arr[0]), float(wl_arr[-1]))
        self.wavelengthAxisSignal.emit(wl_arr)
