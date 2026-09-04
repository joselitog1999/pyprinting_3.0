# -*- coding: utf-8 -*-
"""
luminescence.py — Rutina de Medición de Fotoluminiscencia y Emisión Anti-Stokes
PySpectrum 3.0 — UNSAM Nanofotónica
"""
from __future__ import annotations
import time
import numpy as np
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import pyqtSignal, pyqtSlot, QTimer
import pyqtgraph as pg

from config import SHUTTERS
from core.nidaq import open_shutter, close_shutter, heartbeat_shutter
from pyspectrum.drivers.shamrock_driver import DEVICE, get_shamrock
from pyspectrum.drivers.andor_ccd_driver import get_andor_ccd


class LuminescenceWidget(QtWidgets.QDialog):
    """Ventana independiente para mediciones de luminiscencia bajo excitación láser."""

    startLuminescenceSignal = pyqtSignal(str, float, int, float)  # (laser, exp, n_frames, interval)
    stopLuminescenceSignal = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Fotoluminiscencia & Cinética Espectral — PySpectrum 3.0")
        self.resize(850, 520)
        self.setStyleSheet("""
            QDialog {
                background-color: #11111B;
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
                padding: 6px 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45475A;
                color: #89B4FA;
            }
            QComboBox, QLineEdit {
                background-color: #1E1E2E;
                color: #CDD6F4;
                border: 1px solid #45475A;
                border-radius: 4px;
                padding: 4px;
            }
        """)
        self._setup_ui()

    def _setup_ui(self):
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # ── Controles ─────────────────────────────────────────────────────────
        ctrl_vlo = QtWidgets.QVBoxLayout()
        ctrl_vlo.setSpacing(8)

        lbl_title = QtWidgets.QLabel("✨ <b>Parámetros de Luminiscencia</b>")
        lbl_title.setStyleSheet("font-size: 10.5pt; color: #CBA6F7;")
        ctrl_vlo.addWidget(lbl_title)

        grid = QtWidgets.QGridLayout()
        grid.addWidget(QtWidgets.QLabel("Láser de Excitación:"), 0, 0)
        self.cmb_laser = QtWidgets.QComboBox()
        self.cmb_laser.addItems(SHUTTERS)
        grid.addWidget(self.cmb_laser, 0, 1)

        grid.addWidget(QtWidgets.QLabel("Tiempo Exp (s):"), 1, 0)
        self.edit_exp = QtWidgets.QLineEdit("0.20")
        grid.addWidget(self.edit_exp, 1, 1)

        grid.addWidget(QtWidgets.QLabel("Número de Cuadros:"), 2, 0)
        self.edit_nframes = QtWidgets.QLineEdit("100")
        grid.addWidget(self.edit_nframes, 2, 1)

        grid.addWidget(QtWidgets.QLabel("Intervalo Δt (s):"), 3, 0)
        self.edit_interval = QtWidgets.QLineEdit("0.50")
        grid.addWidget(self.edit_interval, 3, 1)

        ctrl_vlo.addLayout(grid)

        self.btn_run = QtWidgets.QPushButton("▶️ Iniciar Medición de Luminiscencia")
        self.btn_run.setStyleSheet("background-color: #CBA6F7; color: #11111B; font-weight: bold;")
        self.btn_run.setCheckable(True)
        self.btn_run.clicked.connect(self._on_toggle_run)
        ctrl_vlo.addWidget(self.btn_run)

        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setStyleSheet("QProgressBar { border: 1px solid #45475A; border-radius: 4px; text-align: center; color: #CDD6F4; } QProgressBar::chunk { background-color: #CBA6F7; }")
        self.progress_bar.setValue(0)
        ctrl_vlo.addWidget(self.progress_bar)

        self.lbl_status = QtWidgets.QLabel("Estado: Esperando inicio.")
        self.lbl_status.setStyleSheet("color: #A6ADC8; font-size: 8.5pt;")
        ctrl_vlo.addWidget(self.lbl_status)

        ctrl_vlo.addStretch()
        layout.addLayout(ctrl_vlo, stretch=1)

        # ── Gráficos: Espectro Instantáneo + Evolución Temporal ───────────────
        plot_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)

        self.plot_spec = pg.PlotWidget(title="<b>Espectro de Fotoluminiscencia I(λ)</b>")
        self.plot_spec.setLabels(bottom="Longitud de Onda (nm)", left="Intensidad (Cuentas)")
        self.curve_spec = self.plot_spec.plot(pen=pg.mkPen("#CBA6F7", width=2.0))
        plot_splitter.addWidget(self.plot_spec)

        self.plot_time = pg.PlotWidget(title="<b>Intensidad Integrada vs Tiempo I(t)</b>")
        self.plot_time.setLabels(bottom="Tiempo (s)", left="Intensidad Total (Cuentas)")
        self.curve_time = self.plot_time.plot(pen=pg.mkPen("#A6E3A1", width=2.0))
        plot_splitter.addWidget(self.plot_time)

        layout.addWidget(plot_splitter, stretch=3)

    def _on_toggle_run(self, checked: bool):
        if checked:
            try:
                laser = self.cmb_laser.currentText()
                exp = float(self.edit_exp.text())
                n_frames = int(self.edit_nframes.text())
                interval = float(self.edit_interval.text())

                self.btn_run.setText("⏹️ Detener Luminiscencia")
                self.btn_run.setStyleSheet("background-color: #F38BA8; color: #11111B;")
                self.lbl_status.setText(f"Midiendo con {laser}...")
                self.startLuminescenceSignal.emit(laser, exp, n_frames, interval)
            except ValueError:
                self.btn_run.setChecked(False)
        else:
            self.btn_run.setText("▶️ Iniciar Medición de Luminiscencia")
            self.btn_run.setStyleSheet("background-color: #CBA6F7; color: #11111B;")
            self.stopLuminescenceSignal.emit()

    @pyqtSlot(np.ndarray, np.ndarray, np.ndarray, np.ndarray, int)
    def update_data(self, wave: np.ndarray, spec: np.ndarray, t_axis: np.ndarray, i_axis: np.ndarray, progress: int):
        self.curve_spec.setData(wave, spec)
        self.curve_time.setData(t_axis, i_axis)
        self.progress_bar.setValue(progress)
        if progress >= 100:
            self.btn_run.setChecked(False)
            self.btn_run.setText("▶️ Iniciar Medición de Luminiscencia")
            self.btn_run.setStyleSheet("background-color: #CBA6F7; color: #11111B;")
            self.lbl_status.setText("Medición completada exitosamente.")


class LuminescenceBackend(QtCore.QObject):
    """Motor de adquisición para mediciones de luminiscencia."""

    dataUpdatedSignal = pyqtSignal(np.ndarray, np.ndarray, np.ndarray, np.ndarray, int)

    def __init__(self, camera=None, spectrometer=None, parent=None):
        super().__init__(parent)
        self.camera = camera or get_andor_ccd()
        self.spectrometer = spectrometer or get_shamrock()

        self.t_points = []
        self.i_points = []
        self.curr_frame = 0
        self.total_frames = 100
        self.laser_in_use = ""

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._step)

    def make_connection(self, widget: LuminescenceWidget):
        widget.startLuminescenceSignal.connect(self.start_luminescence)
        widget.stopLuminescenceSignal.connect(self.stop_luminescence)
        self.dataUpdatedSignal.connect(widget.update_data)

    @pyqtSlot(str, float, int, float)
    def start_luminescence(self, laser: str, exp_time: float, n_frames: int, interval: float):
        self.laser_in_use = laser
        self.total_frames = n_frames
        self.curr_frame = 0
        self.t_points = []
        self.i_points = []
        self.t0 = time.time()

        self.camera.set_exposure_time(exp_time)
        ret, self.wave_axis = self.spectrometer.ShamrockGetCalibration(DEVICE, 1002)

        # Abrir obturador de excitación
        open_shutter(self.laser_in_use)

        self.timer.setInterval(int(max(50, interval * 1000)))
        self.timer.start()

    @pyqtSlot()
    def stop_luminescence(self):
        self.timer.stop()
        if self.laser_in_use:
            close_shutter(self.laser_in_use)
        self.dataUpdatedSignal.emit(np.array([]), np.array([]), np.array(self.t_points), np.array(self.i_points), 100)

    def _step(self):
        if self.curr_frame >= self.total_frames:
            self.stop_luminescence()
            return

        heartbeat_shutter(30.0)

        frame = self.camera.get_most_recent_image()
        spec = np.mean(frame, axis=0)

        t_now = time.time() - self.t0
        i_total = float(np.sum(spec))

        self.t_points.append(t_now)
        self.i_points.append(i_total)
        self.curr_frame += 1

        pct = int(100.0 * self.curr_frame / self.total_frames)
        self.dataUpdatedSignal.emit(self.wave_axis, spec, np.array(self.t_points), np.array(self.i_points), pct)
