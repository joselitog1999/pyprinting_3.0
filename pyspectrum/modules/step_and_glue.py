# -*- coding: utf-8 -*-
"""
step_and_glue.py — Medición Espectral, Cosido Continuo (Step & Glue) y Cinéticas
PySpectrum 3.0 — UNSAM Nanofotónica
"""
from __future__ import annotations
import time
from pathlib import Path
from typing import Optional, List, Dict
import numpy as np
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import pyqtSignal, pyqtSlot, QTimer
import pyqtgraph as pg

from pyspectrum.drivers.shamrock_driver import DEVICE, get_shamrock
from pyspectrum.drivers.andor_ccd_driver import get_andor_ccd
from pyspectrum.calibration.halogen_lamp import HalogenLampCalibration, glue_steps
from pyspectrum.calibration.fit_polynomial import fit_signal_polynomial
from pyspectrum.calibration.fit_raman_water import fit_signal_raman


class Frontend(QtWidgets.QFrame):
    """Interfaz para adquisición de espectros simples, cosido Step & Glue y cinéticas."""

    measureSingleSignal = pyqtSignal(float, float)  # (lambda_center, exp_time)
    measureStepGlueSignal = pyqtSignal(float, float, float, float, bool)  # (start, end, overlap, exp_time, normalize)
    measureKineticsSignal = pyqtSignal(int, float, float, bool)  # (n_steps, interval, exp_time, normalize)
    stopMeasurementSignal = pyqtSignal()
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
            QCheckBox {
                color: #CDD6F4;
            }
        """)
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QtWidgets.QHBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(12)

        # ── Panel de Controles Izquierdo ──────────────────────────────────────
        controls_vlo = QtWidgets.QVBoxLayout()
        controls_vlo.setSpacing(10)

        lbl_title = QtWidgets.QLabel("🧩 <b>Adquisición & Step and Glue</b>")
        lbl_title.setStyleSheet("font-size: 10.5pt; color: #89B4FA;")
        controls_vlo.addWidget(lbl_title)

        # 1. Parámetros Básicos
        param_grid = QtWidgets.QGridLayout()
        param_grid.setSpacing(6)

        param_grid.addWidget(QtWidgets.QLabel("Tiempo Exp (s):"), 0, 0)
        self.edit_exp = QtWidgets.QLineEdit("1.0")
        param_grid.addWidget(self.edit_exp, 0, 1)

        param_grid.addWidget(QtWidgets.QLabel("Paso Único λ (nm):"), 1, 0)
        self.edit_center_wl = QtWidgets.QLineEdit("532.0")
        param_grid.addWidget(self.edit_center_wl, 1, 1)

        controls_vlo.addLayout(param_grid)

        # Botón Medición Simple
        self.btn_single = QtWidgets.QPushButton("🔬 Medir Espectro Simple")
        self.btn_single.setStyleSheet("background-color: #89B4FA; color: #11111B;")
        self.btn_single.clicked.connect(self._on_single_measure)
        controls_vlo.addWidget(self.btn_single)

        # 2. Rango Step & Glue
        box_sandg = QtWidgets.QGroupBox("Parámetros Step & Glue (Cosido Amplio)")
        box_sandg.setStyleSheet("color: #CDD6F4; font-weight: bold; border: 1px solid #45475A; padding: 6px;")
        sandg_grid = QtWidgets.QGridLayout(box_sandg)
        sandg_grid.setSpacing(6)

        sandg_grid.addWidget(QtWidgets.QLabel("λ Inicial (nm):"), 0, 0)
        self.edit_start_wl = QtWidgets.QLineEdit("450.0")
        sandg_grid.addWidget(self.edit_start_wl, 0, 1)

        sandg_grid.addWidget(QtWidgets.QLabel("λ Final (nm):"), 1, 0)
        self.edit_end_wl = QtWidgets.QLineEdit("950.0")
        sandg_grid.addWidget(self.edit_end_wl, 1, 1)

        sandg_grid.addWidget(QtWidgets.QLabel("Solapamiento:"), 2, 0)
        self.edit_overlap = QtWidgets.QLineEdit("0.20")
        sandg_grid.addWidget(self.edit_overlap, 2, 1)

        controls_vlo.addWidget(box_sandg)

        # Opciones de procesamiento
        self.chk_norm_lamp = QtWidgets.QCheckBox("Normalizar con Lámpara Halógena")
        self.chk_norm_lamp.setChecked(True)
        controls_vlo.addWidget(self.chk_norm_lamp)

        self.chk_fit_poly = QtWidgets.QCheckBox("Ajuste Polinomial SPR (λ_max)")
        self.chk_fit_poly.setChecked(True)
        controls_vlo.addWidget(self.chk_fit_poly)

        self.chk_fit_raman = QtWidgets.QCheckBox("Ajuste Raman Agua (3300 cm⁻¹)")
        controls_vlo.addWidget(self.chk_fit_raman)

        # Botón Ejecutar Step & Glue
        self.btn_sandg = QtWidgets.QPushButton("🧩 Ejecutar Step and Glue")
        self.btn_sandg.setStyleSheet("background-color: #A6E3A1; color: #11111B;")
        self.btn_sandg.clicked.connect(self._on_sandg_measure)
        controls_vlo.addWidget(self.btn_sandg)

        # Barra de Estado / Info
        self.lbl_status = QtWidgets.QLabel("Listo para medir.")
        self.lbl_status.setStyleSheet("color: #A6ADC8; font-size: 8.5pt;")
        controls_vlo.addWidget(self.lbl_status)

        controls_vlo.addStretch()
        main_layout.addLayout(controls_vlo, stretch=1)

        # ── Gráfico Espectral Derecho ─────────────────────────────────────────
        self.plot_widget = pg.PlotWidget(title="<b>Espectro Adquirido / Step & Glue</b>")
        self.plot_widget.setLabels(bottom="Longitud de Onda (nm)", left="Intensidad (Cuentas / Normalizado)")
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.addLegend(offset=(10, 10))

        self.curve_raw = self.plot_widget.plot(name="Espectro Crudo", pen=pg.mkPen("#89B4FA", width=2.0))
        self.curve_norm = self.plot_widget.plot(name="Normalizado Lámpara", pen=pg.mkPen("#A6E3A1", width=2.0))
        self.curve_fit = self.plot_widget.plot(name="Ajuste Analítico", pen=pg.mkPen("#F38BA8", width=2.5, style=QtCore.Qt.PenStyle.DashLine))

        main_layout.addWidget(self.plot_widget, stretch=3)

    def _on_single_measure(self):
        try:
            wl = float(self.edit_center_wl.text())
            exp = float(self.edit_exp.text())
            self.lbl_status.setText(f"Midiendo espectro simple en {wl:.1f} nm...")
            self.measureSingleSignal.emit(wl, exp)
        except ValueError:
            pass

    def _on_sandg_measure(self):
        try:
            start_wl = float(self.edit_start_wl.text())
            end_wl = float(self.edit_end_wl.text())
            overlap = float(self.edit_overlap.text())
            exp = float(self.edit_exp.text())
            norm = self.chk_norm_lamp.isChecked()
            self.lbl_status.setText(f"Ejecutando Step & Glue [{start_wl:.0f} - {end_wl:.0f} nm]...")
            self.measureStepGlueSignal.emit(start_wl, end_wl, overlap, exp, norm)
        except ValueError:
            pass

    @pyqtSlot(np.ndarray, np.ndarray, np.ndarray, np.ndarray, float)
    def update_spectrum_plot(self, wave_raw: np.ndarray, spec_raw: np.ndarray,
                             wave_norm: np.ndarray, spec_norm: np.ndarray, lambda_max: float):
        self.curve_raw.setData(wave_raw, spec_raw)
        if len(wave_norm) > 0:
            self.curve_norm.setData(wave_norm, spec_norm)
        else:
            self.curve_norm.clear()

        if lambda_max > 0:
            self.lbl_status.setText(f"Medición finalizada. Pico SPR: <b>λ_max = {lambda_max:.2f} nm</b>")
        else:
            self.lbl_status.setText("Medición finalizada con éxito.")

    @pyqtSlot(np.ndarray, np.ndarray)
    def update_fit_plot(self, wave_fit: np.ndarray, spec_fit: np.ndarray):
        self.curve_fit.setData(wave_fit, spec_fit)


class Backend(QtCore.QObject):
    """Motor de adquisición y cosido espectral continuo."""

    spectrumFinishedSignal = pyqtSignal(np.ndarray, np.ndarray, np.ndarray, np.ndarray, float)
    fitFinishedSignal = pyqtSignal(np.ndarray, np.ndarray)

    def __init__(self, camera=None, spectrometer=None, parent=None):
        super().__init__(parent)
        self.camera = camera or get_andor_ccd()
        self.spectrometer = spectrometer or get_shamrock()
        self.lamp_calib = HalogenLampCalibration()

    def make_connection(self, frontend: Frontend):
        frontend.measureSingleSignal.connect(self.measure_single_spectrum)
        frontend.measureStepGlueSignal.connect(self.measure_step_and_glue)
        self.spectrumFinishedSignal.connect(frontend.update_spectrum_plot)
        self.fitFinishedSignal.connect(frontend.update_fit_plot)

    @pyqtSlot(float, float)
    def measure_single_spectrum(self, lambda_center: float, exp_time: float):
        # 1. Configurar espectrógrafo y cámara
        self.spectrometer.ShamrockSetWavelength(DEVICE, lambda_center)
        self.camera.set_exposure_time(exp_time)
        time.sleep(0.05)

        # 2. Adquirir y leer
        frame = self.camera.get_most_recent_image()
        spec_1d = np.mean(frame, axis=0)
        ret, wave_1d = self.spectrometer.ShamrockGetCalibration(DEVICE, len(spec_1d))

        # 3. Ajuste opcional
        wave_fit, spec_fit, lambda_max = fit_signal_polynomial(wave_1d, spec_1d, ends_notch=lambda_center - 10, final_wave=wave_1d[-1])
        if len(wave_fit) > 0:
            self.fitFinishedSignal.emit(wave_fit, spec_fit)

        self.spectrumFinishedSignal.emit(wave_1d, spec_1d, np.array([]), np.array([]), lambda_max)

    @pyqtSlot(float, float, float, float, bool)
    def measure_step_and_glue(self, start_wl: float, end_wl: float, overlap: float, exp_time: float, normalize: bool):
        # Cálculo de los centros espectrales según el ancho de dispersión (~300 nm para red 1)
        step_span = 240.0 * (1.0 - overlap)
        centers = []
        c = start_wl + 120.0
        while c <= end_wl + 50.0:
            centers.append(c)
            c += step_span

        if not centers:
            centers = [0.5 * (start_wl + end_wl)]

        raw_waves = []
        raw_specs = []

        self.camera.set_exposure_time(exp_time)

        for wl_c in centers:
            self.spectrometer.ShamrockSetWavelength(DEVICE, wl_c)
            time.sleep(0.05)
            ret, w_cal = self.spectrometer.ShamrockGetCalibration(DEVICE, 1002)
            frame = self.camera.get_most_recent_image()
            s_1d = np.mean(frame, axis=0)

            raw_waves.append(w_cal)
            raw_specs.append(s_1d)

        # Cosido continuo con algoritmo Step & Glue
        concat_w = np.concatenate(raw_waves)
        concat_s = np.concatenate(raw_specs)

        glued_w, glued_s = glue_steps(concat_w, concat_s, number_pixel=1002, grade=2.0)

        # Normalización con lámpara halógena
        norm_w, norm_s = np.array([]), np.array([])
        lambda_max = 0.0

        if normalize:
            norm_w = glued_w
            norm_s = self.lamp_calib.normalize_spectrum(glued_w, glued_s)
            target_w, target_s = norm_w, norm_s
        else:
            target_w, target_s = glued_w, glued_s

        # Ajuste de SPR
        wave_fit, spec_fit, lambda_max = fit_signal_polynomial(target_w, target_s, ends_notch=start_wl + 10, final_wave=end_wl - 10)
        if len(wave_fit) > 0:
            self.fitFinishedSignal.emit(wave_fit, spec_fit)

        self.spectrumFinishedSignal.emit(glued_w, glued_s, norm_w, norm_s, lambda_max)
