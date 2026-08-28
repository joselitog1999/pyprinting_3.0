# -*- coding: utf-8 -*-
"""
dimers.py — Caracterización Espectral de Dímeros Plasmónicos y Acoplamiento
PySpectrum 3.0 — UNSAM Nanofotónica
"""
from __future__ import annotations
import numpy as np
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import pyqtSignal, pyqtSlot
import pyqtgraph as pg

from pyspectrum.drivers.shamrock_driver import DEVICE, get_shamrock
from pyspectrum.drivers.andor_ccd_driver import get_andor_ccd


class DimersWidget(QtWidgets.QDialog):
    """Ventana para análisis espectral de acoplamiento plasmónico en dímeros."""

    acquirePolarizationSignal = pyqtSignal(str, float)  # (mode: 'parallel'/'perpendicular', exp_time)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Caracterización de Dímeros Plasmónicos — PySpectrum 3.0")
        self.resize(850, 500)
        self.setStyleSheet("""
            QDialog { background-color: #11111B; }
            QLabel { color: #CDD6F4; font-weight: bold; }
            QPushButton { background-color: #313244; color: #CDD6F4; border: 1px solid #45475A; border-radius: 4px; padding: 6px 12px; font-weight: bold; }
            QPushButton:hover { background-color: #45475A; color: #A6E3A1; }
            QLineEdit { background-color: #1E1E2E; color: #CDD6F4; border: 1px solid #45475A; border-radius: 4px; padding: 4px; }
        """)
        self._setup_ui()

    def _setup_ui(self):
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        ctrl_vlo = QtWidgets.QVBoxLayout()
        ctrl_vlo.setSpacing(8)

        lbl_title = QtWidgets.QLabel("🔗 <b>Acoplamiento de Dímeros</b>")
        lbl_title.setStyleSheet("font-size: 10.5pt; color: #A6E3A1;")
        ctrl_vlo.addWidget(lbl_title)

        grid = QtWidgets.QGridLayout()
        grid.addWidget(QtWidgets.QLabel("Tiempo Exp (s):"), 0, 0)
        self.edit_exp = QtWidgets.QLineEdit("0.50")
        grid.addWidget(self.edit_exp, 0, 1)
        ctrl_vlo.addLayout(grid)

        self.btn_par = QtWidgets.QPushButton("⚡ Medir Polarización Paralela (∥)")
        self.btn_par.setStyleSheet("background-color: #89B4FA; color: #11111B;")
        self.btn_par.clicked.connect(lambda: self._on_measure("parallel"))
        ctrl_vlo.addWidget(self.btn_par)

        self.btn_perp = QtWidgets.QPushButton("⚡ Medir Polarización Perpendicular (⟂)")
        self.btn_perp.setStyleSheet("background-color: #FAB387; color: #11111B;")
        self.btn_perp.clicked.connect(lambda: self._on_measure("perpendicular"))
        ctrl_vlo.addWidget(self.btn_perp)

        self.lbl_info = QtWidgets.QLabel("Diferencia plasmónica: --")
        self.lbl_info.setStyleSheet("color: #A6ADC8; font-size: 8.5pt;")
        ctrl_vlo.addWidget(self.lbl_info)

        ctrl_vlo.addStretch()
        layout.addLayout(ctrl_vlo, stretch=1)

        self.plot_widget = pg.PlotWidget(title="<b>Espectros de Polarización y Acoplamiento Plasmónico</b>")
        self.plot_widget.setLabels(bottom="Longitud de Onda (nm)", left="Intensidad")
        self.plot_widget.addLegend(offset=(10, 10))

        self.curve_par = self.plot_widget.plot(name="Polarización Paralela (∥)", pen=pg.mkPen("#89B4FA", width=2.2))
        self.curve_perp = self.plot_widget.plot(name="Polarización Perpendicular (⟂)", pen=pg.mkPen("#FAB387", width=2.2))
        self.curve_diff = self.plot_widget.plot(name="Diferencia (∥ - ⟂)", pen=pg.mkPen("#A6E3A1", width=2.0, style=QtCore.Qt.PenStyle.DashLine))

        layout.addWidget(self.plot_widget, stretch=3)

    def _on_measure(self, mode: str):
        try:
            exp = float(self.edit_exp.text())
            self.acquirePolarizationSignal.emit(mode, exp)
        except ValueError:
            pass

    @pyqtSlot(str, np.ndarray, np.ndarray, np.ndarray)
    def update_dimer_data(self, mode: str, wave: np.ndarray, spec: np.ndarray, diff: np.ndarray):
        if mode == "parallel":
            self.curve_par.setData(wave, spec)
        else:
            self.curve_perp.setData(wave, spec)

        if len(diff) > 0:
            self.curve_diff.setData(wave, diff)
            self.lbl_info.setText("Acoplamiento plasmónico calculado.")


class DimersBackend(QtCore.QObject):
    """Lógica de adquisición para dímeros plasmónicos."""

    dimerDataSignal = pyqtSignal(str, np.ndarray, np.ndarray, np.ndarray)

    def __init__(self, camera=None, spectrometer=None, parent=None):
        super().__init__(parent)
        self.camera = camera or get_andor_ccd()
        self.spectrometer = spectrometer or get_shamrock()

        self.spec_par = None
        self.spec_perp = None
        self.wave_axis = np.linspace(450, 750, 1002)

    def make_connection(self, widget: DimersWidget):
        widget.acquirePolarizationSignal.connect(self.acquire_polarization)
        self.dimerDataSignal.connect(widget.update_dimer_data)

    @pyqtSlot(str, float)
    def acquire_polarization(self, mode: str, exp_time: float):
        self.camera.set_exposure_time(exp_time)
        ret, self.wave_axis = self.spectrometer.ShamrockGetCalibration(DEVICE, 1002)

        frame = self.camera.get_most_recent_image()
        spec = np.mean(frame, axis=0)

        diff = np.array([])
        if mode == "parallel":
            self.spec_par = spec
            if self.spec_perp is not None and len(self.spec_perp) == len(spec):
                diff = self.spec_par - self.spec_perp
        else:
            self.spec_perp = spec
            if self.spec_par is not None and len(self.spec_par) == len(spec):
                diff = self.spec_par - self.spec_perp

        self.dimerDataSignal.emit(mode, self.wave_axis, spec, diff)
