# -*- coding: utf-8 -*-
"""
hyperspectral_confocal.py — Mapeo Confocal Hiperespectral 2D/3D (PI Piezo + Andor CCD)
PySpectrum 3.0 — UNSAM Nanofotónica
"""
from __future__ import annotations
import time
import numpy as np
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import pyqtSignal, pyqtSlot, QTimer
import pyqtgraph as pg

from config import pi
from pyspectrum.drivers.shamrock_driver import DEVICE, get_shamrock
from pyspectrum.drivers.andor_ccd_driver import get_andor_ccd
from pyspectrum.ui.viewbox_tools import LinePlotWidget


class Frontend(QtWidgets.QFrame):
    """Interfaz para escaneo confocal hiperespectral y visualización de cubos (X, Y, λ)."""

    startScanSignal = pyqtSignal(float, float, float, float, float, float)  # (xmin, xmax, ymin, ymax, step, exp)
    stopScanSignal = pyqtSignal()
    pointSelectedSignal = pyqtSignal(int, int)

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
                padding: 6px 12px;
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
                padding: 4px;
            }
        """)
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QtWidgets.QHBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(12)

        # ── Controles de Escaneo ──────────────────────────────────────────────
        ctrl_vlo = QtWidgets.QVBoxLayout()
        ctrl_vlo.setSpacing(8)

        lbl_title = QtWidgets.QLabel("🧬 <b>Mapeo Confocal Hiperespectral (X, Y, λ)</b>")
        lbl_title.setStyleSheet("font-size: 10pt; color: #89B4FA;")
        ctrl_vlo.addWidget(lbl_title)

        grid = QtWidgets.QGridLayout()
        grid.setSpacing(6)

        grid.addWidget(QtWidgets.QLabel("X Min / Max (µm):"), 0, 0)
        self.edit_xmin = QtWidgets.QLineEdit("45.0")
        self.edit_xmax = QtWidgets.QLineEdit("55.0")
        hlo_x = QtWidgets.QHBoxLayout()
        hlo_x.addWidget(self.edit_xmin); hlo_x.addWidget(self.edit_xmax)
        grid.addLayout(hlo_x, 0, 1)

        grid.addWidget(QtWidgets.QLabel("Y Min / Max (µm):"), 1, 0)
        self.edit_ymin = QtWidgets.QLineEdit("45.0")
        self.edit_ymax = QtWidgets.QLineEdit("55.0")
        hlo_y = QtWidgets.QHBoxLayout()
        hlo_y.addWidget(self.edit_ymin); hlo_y.addWidget(self.edit_ymax)
        grid.addLayout(hlo_y, 1, 1)

        grid.addWidget(QtWidgets.QLabel("Paso Δ (µm):"), 2, 0)
        self.edit_step = QtWidgets.QLineEdit("1.0")
        grid.addWidget(self.edit_step, 2, 1)

        grid.addWidget(QtWidgets.QLabel("Tiempo Exp (s):"), 3, 0)
        self.edit_exp = QtWidgets.QLineEdit("0.05")
        grid.addWidget(self.edit_exp, 3, 1)

        ctrl_vlo.addLayout(grid)

        # Botón Iniciar Escaneo
        self.btn_scan = QtWidgets.QPushButton("🚀 Iniciar Escaneo Hiperespectral")
        self.btn_scan.setCheckable(True)
        self.btn_scan.setStyleSheet("background-color: #89B4FA; color: #11111B;")
        self.btn_scan.clicked.connect(self._on_toggle_scan)
        ctrl_vlo.addWidget(self.btn_scan)

        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setStyleSheet("QProgressBar { border: 1px solid #45475A; border-radius: 4px; text-align: center; color: #CDD6F4; } QProgressBar::chunk { background-color: #A6E3A1; }")
        self.progress_bar.setValue(0)
        ctrl_vlo.addWidget(self.progress_bar)

        self.lbl_info = QtWidgets.QLabel("Matriz: 11x11 pts (121 espectros)")
        self.lbl_info.setStyleSheet("color: #A6ADC8; font-size: 8.5pt;")
        ctrl_vlo.addWidget(self.lbl_info)

        ctrl_vlo.addStretch()
        main_layout.addLayout(ctrl_vlo, stretch=1)

        # ── Visores: Mapa 2D de Intensidad Integrada + Espectro Local ─────────
        right_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)

        # Mapa 2D
        self.imv_map = pg.ImageView()
        self.imv_map.ui.roiBtn.hide()
        self.imv_map.ui.menuBtn.hide()
        right_splitter.addWidget(self.imv_map)

        # Espectro del punto seleccionado
        self.plot_point = LinePlotWidget(title="Espectro del Punto Seleccionado", x_label="Longitud de Onda (nm)", y_label="Intensidad")
        self.plot_point.setFixedHeight(160)
        right_splitter.addWidget(self.plot_point)

        main_layout.addWidget(right_splitter, stretch=3)

    def _on_toggle_scan(self, checked: bool):
        if checked:
            try:
                xmin = float(self.edit_xmin.text())
                xmax = float(self.edit_xmax.text())
                ymin = float(self.edit_ymin.text())
                ymax = float(self.edit_ymax.text())
                step = float(self.edit_step.text())
                exp = float(self.edit_exp.text())

                self.btn_scan.setText("⏹️ Detener Escaneo")
                self.btn_scan.setStyleSheet("background-color: #F38BA8; color: #11111B;")
                self.startScanSignal.emit(xmin, xmax, ymin, ymax, step, exp)
            except ValueError:
                self.btn_scan.setChecked(False)
        else:
            self.btn_scan.setText("🚀 Iniciar Escaneo Hiperespectral")
            self.btn_scan.setStyleSheet("background-color: #89B4FA; color: #11111B;")
            self.stopScanSignal.emit()

    @pyqtSlot(np.ndarray)
    def update_map(self, map_2d: np.ndarray):
        self.imv_map.setImage(map_2d.T, autoRange=False, autoLevels=True)

    @pyqtSlot(int)
    def update_progress(self, val: int):
        self.progress_bar.setValue(val)
        if val >= 100:
            self.btn_scan.setChecked(False)
            self.btn_scan.setText("🚀 Iniciar Escaneo Hiperespectral")
            self.btn_scan.setStyleSheet("background-color: #89B4FA; color: #11111B;")

    @pyqtSlot(np.ndarray, np.ndarray)
    def update_point_spectrum(self, wave_axis: np.ndarray, spec: np.ndarray):
        self.plot_point.set_data(wave_axis, spec, pen_color="#F9E2AF")


class Backend(QtCore.QObject):
    """Lógica de escaneo confocal hiperespectral (PI Piezo + CCD)."""

    mapUpdatedSignal = pyqtSignal(np.ndarray)
    progressSignal = pyqtSignal(int)
    pointSpectrumSignal = pyqtSignal(np.ndarray, np.ndarray)
    scanFinishedSignal = pyqtSignal()

    def __init__(self, camera=None, spectrometer=None, parent=None):
        super().__init__(parent)
        self.camera = camera or get_andor_ccd()
        self.spectrometer = spectrometer or get_shamrock()
        self._scanning = False
        self._datacube = None  # Shape: (Nx, Ny, N_lambda)
        self.wave_axis = np.linspace(450, 750, 1002)

        self.scan_timer = QTimer(self)
        self.scan_timer.setInterval(20)
        self.scan_timer.timeout.connect(self._scan_step)

    def make_connection(self, frontend: Frontend):
        frontend.startScanSignal.connect(self.start_scan)
        frontend.stopScanSignal.connect(self.stop_scan)
        self.mapUpdatedSignal.connect(frontend.update_map)
        self.progressSignal.connect(frontend.update_progress)
        self.pointSpectrumSignal.connect(frontend.update_point_spectrum)

    @pyqtSlot(float, float, float, float, float, float)
    def start_scan(self, xmin: float, xmax: float, ymin: float, ymax: float, step: float, exp_time: float):
        self.xs = np.arange(xmin, xmax + step * 0.5, step)
        self.ys = np.arange(ymin, ymax + step * 0.5, step)
        self.nx = len(self.xs)
        self.ny = len(self.ys)

        ret, self.wave_axis = self.spectrometer.ShamrockGetCalibration(DEVICE, 1002)
        self._datacube = np.zeros((self.nx, self.ny, len(self.wave_axis)), dtype=np.float32)
        self.map_2d = np.zeros((self.nx, self.ny), dtype=np.float32)

        self.curr_ix = 0
        self.curr_iy = 0
        self.total_points = self.nx * self.ny
        self.points_done = 0

        self.camera.set_exposure_time(exp_time)
        self._scanning = True
        self.scan_timer.start()

    @pyqtSlot()
    def stop_scan(self):
        self._scanning = False
        self.scan_timer.stop()
        self.progressSignal.emit(100)

    def _scan_step(self):
        if not self._scanning:
            return

        x = self.xs[self.curr_ix]
        y = self.ys[self.curr_iy]

        # 1. Mover platina PI
        pi.MOV([1, 2], [x, y])

        # 2. Adquirir espectro CCD
        frame = self.camera.get_most_recent_image()
        spec = np.mean(frame, axis=0)

        # 3. Almacenar en hipercubo
        self._datacube[self.curr_ix, self.curr_iy, :] = spec
        self.map_2d[self.curr_ix, self.curr_iy] = float(np.sum(spec))

        self.points_done += 1
        pct = int(100.0 * self.points_done / self.total_points)
        self.progressSignal.emit(pct)

        # Actualizar visualización cada línea o punto
        self.mapUpdatedSignal.emit(self.map_2d)
        self.pointSpectrumSignal.emit(self.wave_axis, spec)

        # Avanzar coordenadas
        self.curr_ix += 1
        if self.curr_ix >= self.nx:
            self.curr_ix = 0
            self.curr_iy += 1
            if self.curr_iy >= self.ny:
                # Escaneo completado
                self.stop_scan()
                self.scanFinishedSignal.emit()
