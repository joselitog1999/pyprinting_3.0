# -*- coding: utf-8 -*-
"""
camera_andor.py — Panel de Control y Live View de Cámara Andor CCD / EMCCD
PySpectrum 3.0 — UNSAM Nanofotónica
"""
from __future__ import annotations
import numpy as np
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import pyqtSignal, pyqtSlot, QTimer
import pyqtgraph as pg

from pyspectrum.drivers.andor_ccd_driver import get_andor_ccd
from pyspectrum.ui.viewbox_tools import GridOverlay, LinePlotWidget


class Frontend(QtWidgets.QFrame):
    """Interfaz gráfica para el visor 2D y controles de la cámara Andor CCD."""

    liveSignal = pyqtSignal(bool)
    setExposureSignal = pyqtSignal(float)
    setTemperatureSignal = pyqtSignal(float)
    toggleCoolerSignal = pyqtSignal(bool)
    setEMGainSignal = pyqtSignal(int)
    saveSpectrumSignal = pyqtSignal(str)

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
            QPushButton {
                background-color: #313244;
                color: #CDD6F4;
                border: 1px solid #45475A;
                border-radius: 4px;
                padding: 5px 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45475A;
                color: #89B4FA;
            }
            QLineEdit {
                background-color: #11111B;
                color: #CDD6F4;
                border: 1px solid #45475A;
                border-radius: 4px;
                padding: 3px 6px;
            }
        """)
        self._setup_ui()

    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # ── Controles Superiores ──────────────────────────────────────────────
        top_hlo = QtWidgets.QHBoxLayout()

        self.btn_live = QtWidgets.QPushButton("▶️ Iniciar Live View")
        self.btn_live.setCheckable(True)
        self.btn_live.clicked.connect(self._on_toggle_live)

        self.lbl_temp = QtWidgets.QLabel("❄️ Temp: <b>-- °C</b>")
        self.lbl_temp.setStyleSheet("background-color: #11111B; padding: 4px 8px; border-radius: 4px; border: 1px solid #45475A;")

        top_hlo.addWidget(self.btn_live)
        top_hlo.addWidget(self.lbl_temp)
        top_hlo.addStretch()

        # Parámetros rápidos: Exp (s), Temp Setpoint, EM Gain
        top_hlo.addWidget(QtWidgets.QLabel("Exp (s):"))
        self.edit_exp = QtWidgets.QLineEdit("0.05")
        self.edit_exp.setFixedWidth(55)
        self.edit_exp.returnPressed.connect(self._on_exp_changed)
        top_hlo.addWidget(self.edit_exp)

        top_hlo.addWidget(QtWidgets.QLabel("Set T (°C):"))
        self.edit_temp = QtWidgets.QLineEdit("-10")
        self.edit_temp.setFixedWidth(45)
        self.edit_temp.returnPressed.connect(self._on_temp_changed)
        top_hlo.addWidget(self.edit_temp)

        top_hlo.addWidget(QtWidgets.QLabel("EM Gain:"))
        self.edit_gain = QtWidgets.QLineEdit("0")
        self.edit_gain.setFixedWidth(45)
        self.edit_gain.returnPressed.connect(self._on_gain_changed)
        top_hlo.addWidget(self.edit_gain)

        layout.addLayout(top_hlo)

        # ── Visualizadores: Imagen 2D + Espectro 1D ───────────────────────────
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)

        # 1. Visor 2D
        self.imv = pg.ImageView()
        self.imv.ui.histogram.setFixedWidth(110)
        self.imv.ui.roiBtn.hide()
        self.imv.ui.menuBtn.hide()
        self.grid_overlay = GridOverlay(self.imv.getView(), (1002, 1002))

        # Línea ROI horizontal para integración espectral
        self.roi_line = pg.LinearRegionItem(values=[480, 520], orientation=pg.LinearRegionItem.Horizontal,
                                            brush=pg.mkBrush(137, 180, 250, 40))
        self.imv.getView().addItem(self.roi_line)
        splitter.addWidget(self.imv)

        # 2. Perfil 1D (Espectro colapsado)
        self.plot_1d = LinePlotWidget(title="Espectro 1D (Perfil CCD)", x_label="Pixel / Longitud de Onda (nm)", y_label="Cuentas (ADC)")
        self.plot_1d.setFixedHeight(180)
        splitter.addWidget(self.plot_1d)

        layout.addWidget(splitter)

    def _on_toggle_live(self, checked: bool):
        if checked:
            self.btn_live.setText("⏹️ Detener Live View")
            self.btn_live.setStyleSheet("background-color: #F38BA8; color: #11111B; font-weight: bold;")
            self.liveSignal.emit(True)
        else:
            self.btn_live.setText("▶️ Iniciar Live View")
            self.btn_live.setStyleSheet("background-color: #313244; color: #CDD6F4; font-weight: bold;")
            self.liveSignal.emit(False)

    def _on_exp_changed(self):
        try:
            val = float(self.edit_exp.text())
            self.setExposureSignal.emit(val)
        except ValueError:
            pass

    def _on_temp_changed(self):
        try:
            val = float(self.edit_temp.text())
            self.setTemperatureSignal.emit(val)
        except ValueError:
            pass

    def _on_gain_changed(self):
        try:
            val = int(self.edit_gain.text())
            self.setEMGainSignal.emit(val)
        except ValueError:
            pass

    @pyqtSlot(np.ndarray)
    def update_image(self, img: np.ndarray):
        self.imv.setImage(img.T, autoRange=False, autoLevels=False)

    @pyqtSlot(np.ndarray, np.ndarray)
    def update_1d_spectrum(self, x_axis: np.ndarray, spec: np.ndarray):
        self.plot_1d.set_data(x_axis, spec, pen_color="#A6E3A1")

    @pyqtSlot(float, int)
    def update_temperature(self, temp: float, status: int):
        status_str = "🟢 Estabilizado" if abs(temp - float(self.edit_temp.text())) < 1.0 else "🟡 Enfriando..."
        self.lbl_temp.setText(f"❄️ Temp: <b>{temp:.1f} °C</b> ({status_str})")


class Backend(QtCore.QObject):
    """Controlador y bucle de adquisición continua para la cámara Andor CCD."""

    imageUpdatedSignal = pyqtSignal(np.ndarray)
    spectrum1DUpdatedSignal = pyqtSignal(np.ndarray, np.ndarray)
    temperatureUpdatedSignal = pyqtSignal(float, int)

    def __init__(self, camera=None, parent=None):
        super().__init__(parent)
        self.camera = camera or get_andor_ccd()
        self.wavelength_axis = np.linspace(400, 700, 1002)

        self.view_timer = QTimer(self)
        self.view_timer.setInterval(35)  # ~30 FPS
        self.view_timer.timeout.connect(self._acquire_frame)

        self.temp_timer = QTimer(self)
        self.temp_timer.setInterval(1000)  # 1 Hz
        self.temp_timer.timeout.connect(self._read_temperature)
        self.temp_timer.start()

    def make_connection(self, frontend: Frontend):
        frontend.liveSignal.connect(self.toggle_live)
        frontend.setExposureSignal.connect(self.set_exposure)
        frontend.setTemperatureSignal.connect(self.set_temperature)
        frontend.setEMGainSignal.connect(self.set_em_gain)

        self.imageUpdatedSignal.connect(frontend.update_image)
        self.spectrum1DUpdatedSignal.connect(frontend.update_1d_spectrum)
        self.temperatureUpdatedSignal.connect(frontend.update_temperature)

    @pyqtSlot(bool)
    def toggle_live(self, active: bool):
        if active:
            self.camera.start_acquisition()
            self.view_timer.start()
        else:
            self.view_timer.stop()
            self.camera.abort_acquisition()

    @pyqtSlot(float)
    def set_exposure(self, t_sec: float):
        self.camera.set_exposure_time(t_sec)

    @pyqtSlot(float)
    def set_temperature(self, temp: float):
        self.camera.set_temperature(temp)

    @pyqtSlot(int)
    def set_em_gain(self, gain: int):
        self.camera.set_emccd_gain(gain)

    @pyqtSlot(np.ndarray)
    def set_wavelength_axis(self, wl_axis: np.ndarray):
        self.wavelength_axis = wl_axis

    def _acquire_frame(self):
        frame = self.camera.get_most_recent_image()
        self.imageUpdatedSignal.emit(frame)

        # Binning vertical para perfil 1D
        spec1d = np.mean(frame[480:520, :], axis=0) if frame.shape[0] >= 520 else np.mean(frame, axis=0)
        x_axis = self.wavelength_axis if len(self.wavelength_axis) == len(spec1d) else np.arange(len(spec1d))
        self.spectrum1DUpdatedSignal.emit(x_axis, spec1d)

    def _read_temperature(self):
        status, temp = self.camera.get_temperature()
        self.temperatureUpdatedSignal.emit(temp, status)
