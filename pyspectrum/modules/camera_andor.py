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
    """Interfaz gráfica para el visor 2D y controles avanzados de la cámara Andor iXon3 EMCCD."""

    liveSignal = pyqtSignal(bool)
    setExposureSignal = pyqtSignal(float)
    setTemperatureSignal = pyqtSignal(float)
    toggleCoolerSignal = pyqtSignal(bool)
    setOutputAmplifierSignal = pyqtSignal(int)
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
            QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
                background-color: #11111B;
                color: #CDD6F4;
                border: 1px solid #45475A;
                border-radius: 4px;
                padding: 3px 6px;
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: #313244;
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: #89B4FA;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #CDD6F4;
                border: 1px solid #89B4FA;
                width: 14px;
                margin-top: -4px;
                margin-bottom: -4px;
                border-radius: 7px;
            }
        """)
        self._setup_ui()

    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # ── Fila 1: Control de Adquisición y Refrigeración ────────────────────
        row1 = QtWidgets.QHBoxLayout()

        self.btn_live = QtWidgets.QPushButton("▶️ Iniciar Live View")
        self.btn_live.setCheckable(True)
        self.btn_live.clicked.connect(self._on_toggle_live)
        row1.addWidget(self.btn_live)

        self.lbl_temp = QtWidgets.QLabel("❄️ Temp: <b>-- °C</b> (⚪ Off)")
        self.lbl_temp.setStyleSheet("background-color: #11111B; padding: 4px 8px; border-radius: 4px; border: 1px solid #45475A;")
        row1.addWidget(self.lbl_temp)

        self.btn_cooler = QtWidgets.QPushButton("❄️ Enfriador: ON")
        self.btn_cooler.setCheckable(True)
        self.btn_cooler.setChecked(True)
        self.btn_cooler.setStyleSheet("background-color: #89B4FA; color: #11111B; font-weight: bold;")
        self.btn_cooler.clicked.connect(self._on_toggle_cooler)
        row1.addWidget(self.btn_cooler)

        row1.addWidget(QtWidgets.QLabel("Set T (°C):"))
        self.spin_temp = QtWidgets.QSpinBox()
        self.spin_temp.setRange(-100, 25)
        self.spin_temp.setValue(-65)
        self.spin_temp.setSuffix(" °C")
        self.spin_temp.setFixedWidth(75)
        self.spin_temp.editingFinished.connect(self._on_temp_changed)
        row1.addWidget(self.spin_temp)

        row1.addWidget(QtWidgets.QLabel("Exp (s):"))
        self.edit_exp = QtWidgets.QLineEdit("0.05")
        self.edit_exp.setFixedWidth(55)
        self.edit_exp.returnPressed.connect(self._on_exp_changed)
        row1.addWidget(self.edit_exp)

        row1.addStretch()
        layout.addLayout(row1)

        # ── Fila 2: Modo de Amplificación y Ganancia EM interactiva ───────────
        row2 = QtWidgets.QHBoxLayout()

        row2.addWidget(QtWidgets.QLabel("Salida:"))
        self.cmb_amp = QtWidgets.QComboBox()
        self.cmb_amp.addItem("Modo EMCCD (Multiplicador)", 0)
        self.cmb_amp.addItem("Modo Convencional (Bajo Ruido)", 1)
        self.cmb_amp.currentIndexChanged.connect(self._on_amp_changed)
        row2.addWidget(self.cmb_amp)

        row2.addWidget(QtWidgets.QLabel("EM Gain:"))
        self.slider_gain = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.slider_gain.setRange(0, 1000)
        self.slider_gain.setValue(0)
        self.slider_gain.setFixedWidth(140)
        self.slider_gain.valueChanged.connect(self._on_slider_gain_changed)
        row2.addWidget(self.slider_gain)

        # Casilla numérica al lado del slider para ingreso directo
        self.spin_gain = QtWidgets.QSpinBox()
        self.spin_gain.setRange(0, 1000)
        self.spin_gain.setValue(0)
        self.spin_gain.setFixedWidth(65)
        self.spin_gain.valueChanged.connect(self._on_spin_gain_changed)
        row2.addWidget(self.spin_gain)

        self.lbl_gain_badge = QtWidgets.QLabel("1x (CCD)")
        self.lbl_gain_badge.setStyleSheet("background-color: #A6E3A1; color: #11111B; font-weight: bold; padding: 2px 6px; border-radius: 3px;")
        row2.addWidget(self.lbl_gain_badge)

        row2.addStretch()
        layout.addLayout(row2)

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

    def _on_toggle_cooler(self, checked: bool):
        if checked:
            self.btn_cooler.setText("❄️ Enfriador: ON")
            self.btn_cooler.setStyleSheet("background-color: #89B4FA; color: #11111B; font-weight: bold;")
            self.toggleCoolerSignal.emit(True)
        else:
            self.btn_cooler.setText("❄️ Enfriador: OFF")
            self.btn_cooler.setStyleSheet("background-color: #45475A; color: #A6ADC8; font-weight: normal;")
            self.toggleCoolerSignal.emit(False)

    def _on_exp_changed(self):
        try:
            val = float(self.edit_exp.text())
            self.setExposureSignal.emit(val)
        except ValueError:
            pass

    def _on_temp_changed(self):
        val = float(self.spin_temp.value())
        self.setTemperatureSignal.emit(val)

    def _on_amp_changed(self, idx: int):
        amp_type = self.cmb_amp.currentData()
        if amp_type == 1:
            # Modo convencional
            self.slider_gain.setEnabled(False)
            self.spin_gain.setEnabled(False)
            self.lbl_gain_badge.setText("N/A (Convencional)")
            self.lbl_gain_badge.setStyleSheet("background-color: #45475A; color: #A6ADC8; padding: 2px 6px; border-radius: 3px;")
        else:
            # Modo EMCCD
            self.slider_gain.setEnabled(True)
            self.spin_gain.setEnabled(True)
            self._update_gain_badge(self.spin_gain.value())
        self.setOutputAmplifierSignal.emit(amp_type)

    def _on_slider_gain_changed(self, val: int):
        if self.spin_gain.value() != val:
            self.spin_gain.blockSignals(True)
            self.spin_gain.setValue(val)
            self.spin_gain.blockSignals(False)
        self._update_gain_badge(val)
        self.setEMGainSignal.emit(val)

    def _on_spin_gain_changed(self, val: int):
        if self.slider_gain.value() != val:
            self.slider_gain.blockSignals(True)
            self.slider_gain.setValue(val)
            self.slider_gain.blockSignals(False)
        self._update_gain_badge(val)
        self.setEMGainSignal.emit(val)

    def _update_gain_badge(self, val: int):
        if val <= 100:
            color = "#A6E3A1"  # Verde seguro
            txt = f"{val}x" if val > 0 else "1x (Off)"
        elif val <= 300:
            color = "#F9E2AF"  # Amarillo precaución
            txt = f"⚠️ {val}x"
        else:
            color = "#F38BA8"  # Rojo peligro saturación
            txt = f"🔥 {val}x (ALERTA)"
        self.lbl_gain_badge.setText(txt)
        self.lbl_gain_badge.setStyleSheet(f"background-color: {color}; color: #11111B; font-weight: bold; padding: 2px 6px; border-radius: 3px;")

    @pyqtSlot(np.ndarray)
    def update_image(self, img: np.ndarray):
        self.imv.setImage(img.T, autoRange=False, autoLevels=False)

    @pyqtSlot(np.ndarray, np.ndarray)
    def update_1d_spectrum(self, x_axis: np.ndarray, spec: np.ndarray):
        self.plot_1d.set_data(x_axis, spec, pen_color="#A6E3A1")

    @pyqtSlot(float, int)
    def update_temperature(self, temp: float, status: int):
        # Interpretación de estados Andor SDK 2
        # DRV_TEMP_STABILIZED = 20036
        # DRV_TEMP_NOT_REACHED = 20037
        # DRV_TEMP_DRIFT = 20040
        # DRV_TEMP_NOT_STABILIZED = 20035
        if status == 20036 or abs(temp - float(self.spin_temp.value())) < 0.8:
            status_str = "🟢 Estabilizado"
        elif status == 20040:
            status_str = "🟠 Deriva Térmica"
        elif status == 20037:
            status_str = "🟡 Enfriando..."
        elif status == 20035:
            status_str = "🔴 No Estabilizado"
        else:
            status_str = "🟡 Activo"

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
        frontend.toggleCoolerSignal.connect(self.toggle_cooler)
        frontend.setOutputAmplifierSignal.connect(self.set_output_amplifier)
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

    @pyqtSlot(bool)
    def toggle_cooler(self, active: bool):
        if active:
            self.camera.cooler_on()
        else:
            self.camera.cooler_off()

    @pyqtSlot(int)
    def set_output_amplifier(self, typ: int):
        self.camera.set_output_amplifier(typ)

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
