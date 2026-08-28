# -*- coding: utf-8 -*-
"""
growth_kinetics.py — Monitoreo de Cinética de Crecimiento y Síntesis de Nanopartículas
PySpectrum 3.0 — UNSAM Nanofotónica
"""
from __future__ import annotations
import time
import numpy as np
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import pyqtSignal, pyqtSlot, QTimer
import pyqtgraph as pg

from config import SHUTTERS
from core.nidaq import open_shutter, close_shutter
from pyspectrum.drivers.shamrock_driver import DEVICE, get_shamrock
from pyspectrum.drivers.andor_ccd_driver import get_andor_ccd
from pyspectrum.calibration.fit_polynomial import fit_signal_polynomial


class GrowthKineticsWidget(QtWidgets.QDialog):
    """Ventana para el seguimiento in-situ del crecimiento plasmónico de nanopartículas."""

    startGrowthSignal = pyqtSignal(str, float, int, float)
    stopGrowthSignal = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cinética de Crecimiento de Nanopartículas — PySpectrum 3.0")
        self.resize(880, 530)
        self.setStyleSheet("""
            QDialog { background-color: #11111B; }
            QLabel { color: #CDD6F4; font-weight: bold; }
            QPushButton { background-color: #313244; color: #CDD6F4; border: 1px solid #45475A; border-radius: 4px; padding: 6px 12px; font-weight: bold; }
            QPushButton:hover { background-color: #45475A; color: #FAB387; }
            QComboBox, QLineEdit { background-color: #1E1E2E; color: #CDD6F4; border: 1px solid #45475A; border-radius: 4px; padding: 4px; }
        """)
        self._setup_ui()

    def _setup_ui(self):
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # ── Controles ─────────────────────────────────────────────────────────
        ctrl_vlo = QtWidgets.QVBoxLayout()
        ctrl_vlo.setSpacing(8)

        lbl_title = QtWidgets.QLabel("🌱 <b>Monitoreo de Crecimiento</b>")
        lbl_title.setStyleSheet("font-size: 10.5pt; color: #FAB387;")
        ctrl_vlo.addWidget(lbl_title)

        grid = QtWidgets.QGridLayout()
        grid.addWidget(QtWidgets.QLabel("Láser de Irradiación:"), 0, 0)
        self.cmb_laser = QtWidgets.QComboBox()
        self.cmb_laser.addItems(SHUTTERS)
        grid.addWidget(self.cmb_laser, 0, 1)

        grid.addWidget(QtWidgets.QLabel("Tiempo Exp (s):"), 1, 0)
        self.edit_exp = QtWidgets.QLineEdit("0.10")
        grid.addWidget(self.edit_exp, 1, 1)

        grid.addWidget(QtWidgets.QLabel("Cuadros de Cinética:"), 2, 0)
        self.edit_nframes = QtWidgets.QLineEdit("200")
        grid.addWidget(self.edit_nframes, 2, 1)

        grid.addWidget(QtWidgets.QLabel("Intervalo Δt (s):"), 3, 0)
        self.edit_interval = QtWidgets.QLineEdit("0.25")
        grid.addWidget(self.edit_interval, 3, 1)

        ctrl_vlo.addLayout(grid)

        self.btn_run = QtWidgets.QPushButton("▶️ Iniciar Monitoreo de Crecimiento")
        self.btn_run.setStyleSheet("background-color: #FAB387; color: #11111B; font-weight: bold;")
        self.btn_run.setCheckable(True)
        self.btn_run.clicked.connect(self._on_toggle_run)
        ctrl_vlo.addWidget(self.btn_run)

        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setStyleSheet("QProgressBar { border: 1px solid #45475A; border-radius: 4px; text-align: center; color: #CDD6F4; } QProgressBar::chunk { background-color: #FAB387; }")
        self.progress_bar.setValue(0)
        ctrl_vlo.addWidget(self.progress_bar)

        self.lbl_peak = QtWidgets.QLabel("λ_max actual: <b>-- nm</b>")
        self.lbl_peak.setStyleSheet("color: #FAB387; font-size: 9.5pt;")
        ctrl_vlo.addWidget(self.lbl_peak)

        ctrl_vlo.addStretch()
        layout.addLayout(ctrl_vlo, stretch=1)

        # ── Gráficos: Espectro SPR + Desplazamiento λ_max(t) ──────────────────
        plot_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)

        self.plot_spec = pg.PlotWidget(title="<b>Espectro de Extinción / Dispersión SPR</b>")
        self.plot_spec.setLabels(bottom="Longitud de Onda (nm)", left="Intensidad")
        self.curve_spec = self.plot_spec.plot(pen=pg.mkPen("#89B4FA", width=2.0))
        self.curve_fit = self.plot_spec.plot(pen=pg.mkPen("#F38BA8", width=2.2, style=QtCore.Qt.PenStyle.DashLine))
        plot_splitter.addWidget(self.plot_spec)

        self.plot_spr_time = pg.PlotWidget(title="<b>Evolución del Pico Plasmónico λ_max vs Tiempo</b>")
        self.plot_spr_time.setLabels(bottom="Tiempo (s)", left="λ_max SPR (nm)")
        self.curve_spr = self.plot_spr_time.plot(pen=pg.mkPen("#FAB387", width=2.0), symbol='o', symbolSize=4, symbolBrush="#FAB387")
        plot_splitter.addWidget(self.plot_spr_time)

        layout.addWidget(plot_splitter, stretch=3)

    def _on_toggle_run(self, checked: bool):
        if checked:
            try:
                laser = self.cmb_laser.currentText()
                exp = float(self.edit_exp.text())
                n_frames = int(self.edit_nframes.text())
                interval = float(self.edit_interval.text())

                self.btn_run.setText("⏹️ Detener Crecimiento")
                self.btn_run.setStyleSheet("background-color: #F38BA8; color: #11111B;")
                self.startGrowthSignal.emit(laser, exp, n_frames, interval)
            except ValueError:
                self.btn_run.setChecked(False)
        else:
            self.btn_run.setText("▶️ Iniciar Monitoreo de Crecimiento")
            self.btn_run.setStyleSheet("background-color: #FAB387; color: #11111B;")
            self.stopGrowthSignal.emit()

    @pyqtSlot(np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, float, int)
    def update_growth_data(self, wave: np.ndarray, spec: np.ndarray, wave_fit: np.ndarray, spec_fit: np.ndarray,
                           t_axis: np.ndarray, lmax_axis: np.ndarray, current_lmax: float, progress: int):
        self.curve_spec.setData(wave, spec)
        if len(wave_fit) > 0:
            self.curve_fit.setData(wave_fit, spec_fit)
        self.curve_spr.setData(t_axis, lmax_axis)
        self.progress_bar.setValue(progress)
        self.lbl_peak.setText(f"λ_max actual: <b>{current_lmax:.2f} nm</b>")

        if progress >= 100:
            self.btn_run.setChecked(False)
            self.btn_run.setText("▶️ Iniciar Monitoreo de Crecimiento")
            self.btn_run.setStyleSheet("background-color: #FAB387; color: #11111B;")


class GrowthKineticsBackend(QtCore.QObject):
    """Motor de adquisición y ajuste continuo para cinética de crecimiento."""

    growthUpdatedSignal = pyqtSignal(np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, float, int)

    def __init__(self, camera=None, spectrometer=None, parent=None):
        super().__init__(parent)
        self.camera = camera or get_andor_ccd()
        self.spectrometer = spectrometer or get_shamrock()

        self.t_points = []
        self.lmax_points = []
        self.curr_frame = 0
        self.total_frames = 200
        self.laser_in_use = ""

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._step)

    def make_connection(self, widget: GrowthKineticsWidget):
        widget.startGrowthSignal.connect(self.start_growth)
        widget.stopGrowthSignal.connect(self.stop_growth)
        self.growthUpdatedSignal.connect(widget.update_growth_data)

    @pyqtSlot(str, float, int, float)
    def start_growth(self, laser: str, exp_time: float, n_frames: int, interval: float):
        self.laser_in_use = laser
        self.total_frames = n_frames
        self.curr_frame = 0
        self.t_points = []
        self.lmax_points = []
        self.t0 = time.time()

        self.camera.set_exposure_time(exp_time)
        ret, self.wave_axis = self.spectrometer.ShamrockGetCalibration(DEVICE, 1002)

        open_shutter(self.laser_in_use)
        self.timer.setInterval(int(max(50, interval * 1000)))
        self.timer.start()

    @pyqtSlot()
    def stop_growth(self):
        self.timer.stop()
        if self.laser_in_use:
            close_shutter(self.laser_in_use)

    def _step(self):
        if self.curr_frame >= self.total_frames:
            self.stop_growth()
            return

        frame = self.camera.get_most_recent_image()
        spec = np.mean(frame, axis=0)

        # Ajuste de SPR
        wave_fit, spec_fit, lmax = fit_signal_polynomial(self.wave_axis, spec, ends_notch=self.wave_axis[0] + 10, final_wave=self.wave_axis[-1] - 10)

        t_now = time.time() - self.t0
        self.t_points.append(t_now)
        self.lmax_points.append(lmax)
        self.curr_frame += 1

        pct = int(100.0 * self.curr_frame / self.total_frames)
        self.growthUpdatedSignal.emit(self.wave_axis, spec, wave_fit, spec_fit,
                                      np.array(self.t_points), np.array(self.lmax_points), lmax, pct)
