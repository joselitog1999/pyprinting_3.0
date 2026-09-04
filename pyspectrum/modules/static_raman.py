# -*- coding: utf-8 -*-
"""
static_raman.py — Módulo de Adquisición y Procesamiento Raman Estático & Termometría
PySpectrum 3.0 — UNSAM Nanofotónica

Funcionalidades:
  - Adquisición estática ultra-rápida (Single-Shot y Live Raman) sin escaneo mecánico de red.
  - Preconfiguración automática de ventanas:
      * Huella Dactilar Raman (Stokes): Centrado para cubrir ~500 a 2000 cm⁻¹.
      * Stokes + Anti-Stokes Simétrico: Centrado en la línea láser para termometría in-situ.
      * Manual: Definición libre del centro espectral.
  - Selección de láseres compartidos con PyPrinting (config.SHUTTERS): 532 nm, 637 nm, 592 nm, 808 nm.
  - Red por defecto: 150 l/mm (exploratoria de amplio ancho de banda), conmutación ágil a 1200 l/mm.
  - Procesamiento numérico en vivo con core/raman_engine.py:
      * Conversión directa nm <-> Raman Shift (cm⁻¹).
      * Despiking de rayos cósmicos.
      * Sustracción de línea base (AsLS, AirPLS, ModPoly).
      * Suavizado Savitzky-Golay.
  - Cursores interactivos duales (A y B) con cálculo en vivo de:
      * Cociente de intensidades I_Stokes / I_Anti-Stokes.
      * Termometría fototérmica instantánea (K y °C).
  - Exportación 1-clic a TXT con metadatos completos y portapapeles TSV.
"""
from __future__ import annotations
import math
import time
from pathlib import Path
from typing import Optional, Dict, Tuple, Any

import numpy as np
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import pyqtSignal, pyqtSlot, QTimer
import pyqtgraph as pg

from config import SHUTTERS, SAFE_MODE
from pyspectrum.drivers.shamrock_driver import (
    DEVICE, GRATING_150_LINES, GRATING_1200_LINES, NAME_GRATINGS, get_shamrock
)
from pyspectrum.drivers.andor_ccd_driver import get_andor_ccd
from core.raman_engine import (
    wavelength_to_raman_shift,
    raman_shift_to_wavelength,
    remove_cosmic_rays,
    baseline_asls,
    baseline_airpls,
    baseline_modpoly,
    smooth_savgol,
    calculate_photothermal_temperature,
    compute_dual_cursor_metrics,
    RAMAN_REFERENCE_STANDARDS,
    BOLTZMANN_CONST,
    PLANCK_CONSTANT,
    SPEED_OF_LIGHT
)


# Mapeo de nombres en config.SHUTTERS a longitudes de onda nominales (nm)
LASER_WAVELENGTH_MAP = {
    "532 nm (green)": 532.0,
    "637 nm (red)": 637.0,
    "592 nm (yellow)": 592.0,
    "808 nm (IR)": 808.0
}


class StaticRamanWidget(QtWidgets.QWidget):
    """Interfaz gráfica para el módulo de Raman Estático y Termometría."""

    requestAcquireSingleSignal = pyqtSignal()
    toggleLiveRamanSignal = pyqtSignal(bool)
    applySpectrometerConfigSignal = pyqtSignal(int, float)  # grating_idx (1-based), wl_center_nm
    saveSpectrumSignal = pyqtSignal(str, dict)  # path, metadata
    copyClipboardSignal = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.laser_nm: float = 532.0
        self.use_raman_shift: bool = True
        self.raw_wl: np.ndarray = np.array([])
        self.raw_counts: np.ndarray = np.array([])
        self.processed_x: np.ndarray = np.array([])
        self.processed_y: np.ndarray = np.array([])
        self.baseline_y: np.ndarray = np.array([])

        self._setup_styles()
        self._setup_ui()
        self._connect_internal_signals()

    def _setup_styles(self):
        self.setStyleSheet("""
            QWidget {
                background-color: #181825;
                color: #CDD6F4;
            }
            QGroupBox {
                border: 1px solid #313244;
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 10px;
                font-weight: bold;
                color: #89B4FA;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 4px;
            }
            QLabel {
                color: #CDD6F4;
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
            QPushButton:disabled {
                background-color: #1E1E2E;
                color: #585B70;
            }
            QComboBox, QLineEdit, QDoubleSpinBox, QSpinBox {
                background-color: #11111B;
                color: #CDD6F4;
                border: 1px solid #45475A;
                border-radius: 4px;
                padding: 3px 6px;
            }
            QCheckBox {
                color: #CDD6F4;
                spacing: 6px;
            }
        """)

    def _setup_ui(self):
        main_vlo = QtWidgets.QVBoxLayout(self)
        main_vlo.setContentsMargins(8, 8, 8, 8)
        main_vlo.setSpacing(6)

        # ── 1. Barra Superior: Parámetros del Espectrómetro & Láser ───────────
        grp_hw = QtWidgets.QGroupBox("⚙️ Configuración Óptica & Ventana Espectral")
        hw_vlo = QtWidgets.QVBoxLayout(grp_hw)
        hw_vlo.setSpacing(6)

        # Fila 1: Láser y Red de difracción
        row1 = QtWidgets.QHBoxLayout()
        row1.addWidget(QtWidgets.QLabel("Láser Excitación:"))
        self.cmb_laser = QtWidgets.QComboBox()
        for s in SHUTTERS:
            self.cmb_laser.addItem(f"🔦 {s}", LASER_WAVELENGTH_MAP.get(s, 532.0))
        self.cmb_laser.addItem("✏️ Personalizado...", -1.0)
        row1.addWidget(self.cmb_laser)

        self.spin_laser_custom = QtWidgets.QDoubleSpinBox()
        self.spin_laser_custom.setRange(200.0, 1500.0)
        self.spin_laser_custom.setValue(532.0)
        self.spin_laser_custom.setDecimals(2)
        self.spin_laser_custom.setSuffix(" nm")
        self.spin_laser_custom.setFixedWidth(90)
        self.spin_laser_custom.setEnabled(False)
        row1.addWidget(self.spin_laser_custom)

        row1.addWidget(QtWidgets.QLabel("Red Shamrock:"))
        self.cmb_grating = QtWidgets.QComboBox()
        # Red 1 (150 l/mm) por defecto (exploratorio)
        self.cmb_grating.addItem("150 l/mm (Blaze 800 nm)", 1)
        self.cmb_grating.addItem("1200 l/mm (Blaze 500 nm)", 2)
        row1.addWidget(self.cmb_grating)

        row1.addStretch()
        hw_vlo.addLayout(row1)

        # Fila 2: Modos de Ventana Preconfigurados
        row2 = QtWidgets.QHBoxLayout()
        row2.addWidget(QtWidgets.QLabel("Modo Ventana:"))
        self.cmb_mode = QtWidgets.QComboBox()
        self.cmb_mode.addItem("🔍 Huella Dactilar Raman (Stokes)", "stokes")
        self.cmb_mode.addItem("⚖️ Stokes + Anti-Stokes Simétrico (Termometría)", "symmetric")
        self.cmb_mode.addItem("🖐️ Manual", "manual")
        row2.addWidget(self.cmb_mode)

        row2.addWidget(QtWidgets.QLabel("Centro Espectrógrafo:"))
        self.spin_center_wl = QtWidgets.QDoubleSpinBox()
        self.spin_center_wl.setRange(300.0, 1200.0)
        self.spin_center_wl.setValue(565.0)
        self.spin_center_wl.setDecimals(2)
        self.spin_center_wl.setSuffix(" nm")
        self.spin_center_wl.setFixedWidth(95)
        row2.addWidget(self.spin_center_wl)

        self.lbl_shift_center = QtWidgets.QLabel("≈ +1098 cm⁻¹")
        self.lbl_shift_center.setStyleSheet("color: #89B4FA; font-weight: bold;")
        row2.addWidget(self.lbl_shift_center)

        self.btn_apply_spectrometer = QtWidgets.QPushButton("🚀 Sintonizar Espectrógrafo")
        self.btn_apply_spectrometer.setStyleSheet("background-color: #89B4FA; color: #11111B;")
        row2.addWidget(self.btn_apply_spectrometer)

        row2.addStretch()
        hw_vlo.addLayout(row2)

        main_vlo.addWidget(grp_hw)

        # ── 2. Barra de Procesamiento Numérico en Vivo ────────────────────────
        grp_proc = QtWidgets.QGroupBox("🧮 Algoritmos de Procesamiento en Tiempo Real")
        proc_hlo = QtWidgets.QHBoxLayout(grp_proc)
        proc_hlo.setSpacing(12)

        # Eje X: cm^-1 vs nm
        self.chk_raman_shift = QtWidgets.QCheckBox("Mostrar Raman Shift (cm⁻¹)")
        self.chk_raman_shift.setChecked(True)
        proc_hlo.addWidget(self.chk_raman_shift)

        # Despiking
        self.chk_despike = QtWidgets.QCheckBox("Despiking Rayos Cósmicos")
        self.chk_despike.setChecked(True)
        proc_hlo.addWidget(self.chk_despike)

        # Línea Base
        self.chk_baseline = QtWidgets.QCheckBox("Sustraer Línea Base:")
        self.chk_baseline.setChecked(False)
        proc_hlo.addWidget(self.chk_baseline)

        self.cmb_baseline = QtWidgets.QComboBox()
        self.cmb_baseline.addItem("AsLS (Asymmetric Least Squares)", "asls")
        self.cmb_baseline.addItem("AirPLS (Adaptive Iterative Reweighted)", "airpls")
        self.cmb_baseline.addItem("ModPoly (Polinomial Modificado)", "modpoly")
        proc_hlo.addWidget(self.cmb_baseline)

        # Suavizado Savitzky-Golay
        self.chk_savgol = QtWidgets.QCheckBox("Suavizado Savitzky-Golay")
        self.chk_savgol.setChecked(False)
        proc_hlo.addWidget(self.chk_savgol)

        self.spin_savgol_win = QtWidgets.QSpinBox()
        self.spin_savgol_win.setRange(5, 51)
        self.spin_savgol_win.setSingleStep(2)
        self.spin_savgol_win.setValue(11)
        self.spin_savgol_win.setSuffix(" pts")
        self.spin_savgol_win.setFixedWidth(70)
        proc_hlo.addWidget(self.spin_savgol_win)

        proc_hlo.addStretch()
        main_vlo.addWidget(grp_proc)

        # ── 3. Visualizador Gráfico PyQtGraph ─────────────────────────────────
        self.plot_widget = pg.PlotWidget(title="Espectro Raman Estático")
        self.plot_widget.setBackground("#11111B")
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.setLabel('bottom', "Corrimiento Raman (cm⁻¹)", color='#CDD6F4', size='10pt')
        self.plot_widget.setLabel('left', "Intensidad / Cuentas (ADC)", color='#CDD6F4', size='10pt')

        # Curvas
        self.curve_raw = self.plot_widget.plot(name="Espectro Crudo", pen=pg.mkPen(color="#585B70", width=1, style=QtCore.Qt.PenStyle.DotLine))
        self.curve_baseline = self.plot_widget.plot(name="Línea Base", pen=pg.mkPen(color="#FAB387", width=1.5, style=QtCore.Qt.PenStyle.DashLine))
        self.curve_proc = self.plot_widget.plot(name="Espectro Procesado", pen=pg.mkPen(color="#A6E3A1", width=2))

        # Cursores duales A y B
        self.cursor_a = pg.InfiniteLine(pos=520.0, angle=90, movable=True, pen=pg.mkPen(color="#89B4FA", width=2))
        self.cursor_b = pg.InfiniteLine(pos=-520.0, angle=90, movable=True, pen=pg.mkPen(color="#F38BA8", width=2))
        self.plot_widget.addItem(self.cursor_a)
        self.plot_widget.addItem(self.cursor_b)

        # Etiquetas flotantes sobre los cursores
        self.lbl_cursor_a_tag = pg.TextItem(text="A", color="#89B4FA", anchor=(0.5, 1.2))
        self.lbl_cursor_b_tag = pg.TextItem(text="B", color="#F38BA8", anchor=(0.5, 1.2))
        self.plot_widget.addItem(self.lbl_cursor_a_tag)
        self.plot_widget.addItem(self.lbl_cursor_b_tag)

        main_vlo.addWidget(self.plot_widget, stretch=1)

        # ── 4. Panel Inferior: Telemetría de Cursores & Termometría ───────────
        telemetry_box = QtWidgets.QFrame()
        telemetry_box.setStyleSheet("background-color: #11111B; border-radius: 4px; padding: 4px; border: 1px solid #313244;")
        tel_hlo = QtWidgets.QHBoxLayout(telemetry_box)
        tel_hlo.setSpacing(15)

        self.lbl_cursor_a_info = QtWidgets.QLabel("🔵 <b>Cursor A:</b> -- cm⁻¹ | -- cts")
        self.lbl_cursor_b_info = QtWidgets.QLabel("🔴 <b>Cursor B:</b> -- cm⁻¹ | -- cts")
        self.lbl_diff_info = QtWidgets.QLabel("📏 <b>Δν:</b> -- cm⁻¹ | <b>IA/IB:</b> --")
        self.lbl_temp_info = QtWidgets.QLabel("🌡️ <b>Temp Fototérmica:</b> -- K (-- °C)")
        self.lbl_temp_info.setStyleSheet("color: #F9E2AF; font-weight: bold;")

        tel_hlo.addWidget(self.lbl_cursor_a_info)
        tel_hlo.addWidget(self.lbl_cursor_b_info)
        tel_hlo.addWidget(self.lbl_diff_info)
        tel_hlo.addWidget(self.lbl_temp_info)
        tel_hlo.addStretch()

        main_vlo.addWidget(telemetry_box)

        # ── 5. Botones de Acción & Exportación ─────────────────────────────────
        actions_hlo = QtWidgets.QHBoxLayout()

        self.btn_single = QtWidgets.QPushButton("📸 Capturar Espectro Único")
        self.btn_single.clicked.connect(self._on_acquire_single)
        actions_hlo.addWidget(self.btn_single)

        self.btn_live = QtWidgets.QPushButton("▶️ Live Raman (Continuo)")
        self.btn_live.setCheckable(True)
        self.btn_live.clicked.connect(self._on_toggle_live)
        actions_hlo.addWidget(self.btn_live)

        actions_hlo.addStretch()

        self.btn_copy_tsv = QtWidgets.QPushButton("📋 Copiar Datos (TSV)")
        self.btn_copy_tsv.clicked.connect(self._on_copy_tsv)
        actions_hlo.addWidget(self.btn_copy_tsv)

        self.btn_save = QtWidgets.QPushButton("💾 Guardar Espectro (.txt)")
        self.btn_save.clicked.connect(self._on_save_spectrum)
        actions_hlo.addWidget(self.btn_save)

        main_vlo.addLayout(actions_hlo)

    def _connect_internal_signals(self):
        self.cmb_laser.currentIndexChanged.connect(self._on_laser_combo_changed)
        self.spin_laser_custom.valueChanged.connect(self._on_laser_value_changed)
        self.cmb_mode.currentIndexChanged.connect(self._on_mode_changed)
        self.cmb_grating.currentIndexChanged.connect(self._on_mode_changed)
        self.spin_center_wl.valueChanged.connect(self._on_center_wl_changed)
        self.btn_apply_spectrometer.clicked.connect(self._on_apply_spectrometer)

        self.chk_raman_shift.toggled.connect(self._reprocess_current_spectrum)
        self.chk_despike.toggled.connect(self._reprocess_current_spectrum)
        self.chk_baseline.toggled.connect(self._reprocess_current_spectrum)
        self.cmb_baseline.currentIndexChanged.connect(self._reprocess_current_spectrum)
        self.chk_savgol.toggled.connect(self._reprocess_current_spectrum)
        self.spin_savgol_win.valueChanged.connect(self._reprocess_current_spectrum)

        self.cursor_a.sigPositionChanged.connect(self._update_telemetry)
        self.cursor_b.sigPositionChanged.connect(self._update_telemetry)

        # Configuración inicial de modo y centro
        self._on_mode_changed()

    # ── Manejadores de Interfaz ───────────────────────────────────────────────
    def _on_laser_combo_changed(self, idx: int):
        val = self.cmb_laser.currentData()
        if val < 0:
            self.spin_laser_custom.setEnabled(True)
            self.laser_nm = float(self.spin_laser_custom.value())
        else:
            self.spin_laser_custom.setEnabled(False)
            self.laser_nm = float(val)
            self.spin_laser_custom.setValue(self.laser_nm)
        self._on_mode_changed()
        self._reprocess_current_spectrum()

    def _on_laser_value_changed(self, val: float):
        if self.cmb_laser.currentData() < 0:
            self.laser_nm = float(val)
            self._on_mode_changed()
            self._reprocess_current_spectrum()

    def _on_mode_changed(self):
        mode = self.cmb_mode.currentData()
        grating = self.cmb_grating.currentData()

        if mode == "symmetric":
            # Modo simétrico centrado exactamente en la longitud de onda láser
            center = self.laser_nm
            self.spin_center_wl.setValue(center)
            self.spin_center_wl.setEnabled(False)
        elif mode == "stokes":
            # Modo Huella Dactilar: centrado a ~1100 cm^-1 hacia el Stokes
            # Con 150 l/mm a 532 nm, centro ~565 nm cubre de ~478 a 652 nm (-2100 a +3400 cm^-1)
            # Con 1200 l/mm a 532 nm, centro ~562 nm cubre ~1000 cm^-1
            target_shift = 1100.0 if grating == 1 else 1000.0
            center = float(raman_shift_to_wavelength(target_shift, self.laser_nm))
            self.spin_center_wl.setValue(center)
            self.spin_center_wl.setEnabled(False)
        else:
            # Modo manual
            self.spin_center_wl.setEnabled(True)

        self._on_center_wl_changed(self.spin_center_wl.value())

    def _on_center_wl_changed(self, wl: float):
        if wl > 0 and self.laser_nm > 0:
            shift = float(wavelength_to_raman_shift(wl, self.laser_nm))
            sign = "+" if shift >= 0 else ""
            self.lbl_shift_center.setText(f"≈ {sign}{shift:.1f} cm⁻¹")

    def _on_apply_spectrometer(self):
        grating_idx = int(self.cmb_grating.currentData())
        wl_center = float(self.spin_center_wl.value())
        self.applySpectrometerConfigSignal.emit(grating_idx, wl_center)

    def _on_acquire_single(self):
        self.requestAcquireSingleSignal.emit()

    def _on_toggle_live(self, checked: bool):
        if checked:
            self.btn_live.setText("⏹️ Detener Live Raman")
            self.btn_live.setStyleSheet("background-color: #F38BA8; color: #11111B;")
            self.toggleLiveRamanSignal.emit(True)
        else:
            self.btn_live.setText("▶️ Live Raman (Continuo)")
            self.btn_live.setStyleSheet("background-color: #313244; color: #CDD6F4;")
            self.toggleLiveRamanSignal.emit(False)

    # ── Pipeline de Procesamiento en Tiempo Real ──────────────────────────────
    @pyqtSlot(np.ndarray, np.ndarray)
    def update_spectrum_data(self, wl_axis: np.ndarray, counts: np.ndarray):
        """Recibe un nuevo espectro adquirido (longitudes de onda y cuentas)."""
        self.raw_wl = wl_axis
        self.raw_counts = counts
        self._reprocess_current_spectrum()

    def _reprocess_current_spectrum(self):
        if len(self.raw_wl) == 0 or len(self.raw_counts) == 0:
            return

        y_proc = self.raw_counts.copy().astype(np.float64)

        # 1. Despiking de Rayos Cósmicos
        if self.chk_despike.isChecked() and len(y_proc) > 7:
            y_proc, _ = remove_cosmic_rays(y_proc, threshold=6.0, window_size=5)

        # 2. Corrección de Línea Base
        base = np.zeros_like(y_proc)
        if self.chk_baseline.isChecked() and len(y_proc) > 10:
            algo = self.cmb_baseline.currentData()
            try:
                if algo == "asls":
                    base = baseline_asls(y_proc, lam=1e5, p=0.001)
                elif algo == "airpls":
                    base = baseline_airpls(y_proc, lam=1e5)
                elif algo == "modpoly":
                    base = baseline_modpoly(y_proc, poly_order=4)
                y_proc = np.maximum(0.0, y_proc - base)
            except Exception:
                base = np.zeros_like(y_proc)

        # 3. Suavizado Savitzky-Golay
        if self.chk_savgol.isChecked() and len(y_proc) > 15:
            win = self.spin_savgol_win.value()
            if win % 2 == 0:
                win += 1
            if win > len(y_proc):
                win = len(y_proc) - 1 if (len(y_proc) - 1) % 2 != 0 else len(y_proc) - 2
            if win >= 5:
                y_proc = smooth_savgol(y_proc, window_length=win, polyorder=3)

        # 4. Eje X: Longitud de Onda o Raman Shift
        self.use_raman_shift = self.chk_raman_shift.isChecked()
        if self.use_raman_shift:
            x_axis = wavelength_to_raman_shift(self.raw_wl, self.laser_nm)
            self.plot_widget.setLabel('bottom', "Corrimiento Raman (cm⁻¹)", color='#CDD6F4', size='10pt')
        else:
            x_axis = self.raw_wl
            self.plot_widget.setLabel('bottom', "Longitud de Onda (nm)", color='#CDD6F4', size='10pt')

        self.processed_x = x_axis
        self.processed_y = y_proc
        self.baseline_y = base

        # 5. Renderizado en Plot
        self.curve_raw.setData(x_axis, self.raw_counts)
        if self.chk_baseline.isChecked():
            self.curve_baseline.setData(x_axis, base)
            self.curve_baseline.show()
        else:
            self.curve_baseline.hide()
        self.curve_proc.setData(x_axis, y_proc)

        self._update_telemetry()

    def _update_telemetry(self):
        if len(self.processed_x) == 0 or len(self.processed_y) == 0:
            return

        pos_a = self.cursor_a.value()
        pos_b = self.cursor_b.value()

        # Posicionar etiquetas A y B
        view_box = self.plot_widget.getViewBox()
        view_range_y = view_box.viewRange()[1]
        y_top = view_range_y[1] if view_range_y else 0
        self.lbl_cursor_a_tag.setPos(pos_a, y_top * 0.95)
        self.lbl_cursor_b_tag.setPos(pos_b, y_top * 0.95)

        # Interpolar intensidad en posición del cursor
        idx_a = int(np.clip(np.argmin(np.abs(self.processed_x - pos_a)), 0, len(self.processed_y) - 1))
        idx_b = int(np.clip(np.argmin(np.abs(self.processed_x - pos_b)), 0, len(self.processed_y) - 1))

        val_a_x = self.processed_x[idx_a]
        val_a_y = self.processed_y[idx_a]
        val_b_x = self.processed_x[idx_b]
        val_b_y = self.processed_y[idx_b]

        unit = "cm⁻¹" if self.use_raman_shift else "nm"
        self.lbl_cursor_a_info.setText(f"🔵 <b>Cursor A:</b> {val_a_x:.1f} {unit} | <b>{val_a_y:.0f}</b> cts")
        self.lbl_cursor_b_info.setText(f"🔴 <b>Cursor B:</b> {val_b_x:.1f} {unit} | <b>{val_b_y:.0f}</b> cts")

        delta_x = abs(val_b_x - val_a_x)
        ratio = (val_a_y / val_b_y) if val_b_y > 1e-6 else 0.0
        self.lbl_diff_info.setText(f"📏 <b>|Δ|:</b> {delta_x:.1f} {unit} | <b>IA/IB:</b> {ratio:.2f}")

        # Cálculo de Termometría Fototérmica Anti-Stokes / Stokes
        if self.use_raman_shift:
            # Determinar cuál cursor está en Anti-Stokes (<0) y cuál en Stokes (>0)
            if (val_a_x < -20.0 and val_b_x > 20.0) or (val_b_x < -20.0 and val_a_x > 20.0):
                if val_a_x < 0:
                    i_as, i_stokes = val_a_y, val_b_y
                    shift = abs(val_b_x)
                else:
                    i_as, i_stokes = val_b_y, val_a_y
                    shift = abs(val_a_x)

                if i_as > 10.0 and i_stokes > 10.0:
                    try:
                        t_k = calculate_photothermal_temperature(
                            i_anti_stokes=i_as,
                            i_stokes=i_stokes,
                            delta_nu_cm1=shift,
                            laser_wavelength_nm=self.laser_nm
                        )
                        t_c = t_k - 273.15
                        if 100.0 <= t_k <= 2000.0:
                            self.lbl_temp_info.setText(f"🌡️ <b>Temp Fototérmica:</b> {t_k:.1f} K (<b>{t_c:.1f} °C</b>)")
                            return
                    except Exception:
                        pass
        self.lbl_temp_info.setText("🌡️ <b>Temp Fototérmica:</b> -- K (-- °C)")

    # ── Exportación y Portapapeles ────────────────────────────────────────────
    def _on_copy_tsv(self):
        if len(self.processed_x) == 0:
            return
        unit = "Raman_Shift_cm-1" if self.use_raman_shift else "Wavelength_nm"
        lines = [f"{unit}\tRaw_Counts\tProcessed_Counts\tBaseline"]
        for x, y_raw, y_proc, b in zip(self.processed_x, self.raw_counts, self.processed_y, self.baseline_y):
            lines.append(f"{x:.3f}\t{y_raw:.1f}\t{y_proc:.1f}\t{b:.1f}")
        tsv_data = "\n".join(lines)

        clipboard = QtWidgets.QApplication.clipboard()
        clipboard.setText(tsv_data)
        self.copyClipboardSignal.emit()
        QtWidgets.QToolTip.showText(QtGui.QCursor.pos(), "✅ Datos copiados al portapapeles (TSV)")

    def _on_save_spectrum(self):
        if len(self.processed_x) == 0:
            return
        default_name = f"Raman_Static_{int(self.laser_nm)}nm_{time.strftime('%Y%m%d_%H%M%S')}.txt"
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Guardar Espectro Raman Estático", default_name, "Archivos de Texto (*.txt);;CSV (*.csv)"
        )
        if not path:
            return

        metadata = {
            "Fecha": time.strftime("%Y-%m-%d %H:%M:%S"),
            "Laser_Excitacion_nm": f"{self.laser_nm:.2f}",
            "Red_Difraccion": self.cmb_grating.currentText(),
            "Centro_Espectrografo_nm": f"{self.spin_center_wl.value():.2f}",
            "Modo_Ventana": self.cmb_mode.currentText(),
            "Despiking": str(self.chk_despike.isChecked()),
            "Linea_Base": f"{self.cmb_baseline.currentText()}" if self.chk_baseline.isChecked() else "Ninguna",
            "Savitzky_Golay": f"Ventana {self.spin_savgol_win.value()}" if self.chk_savgol.isChecked() else "No",
        }
        self.saveSpectrumSignal.emit(path, metadata)


class StaticRamanBackend(QtCore.QObject):
    """Controlador y orquestador físico para Raman Estático y Cámara CCD."""

    spectrumAcquiredSignal = pyqtSignal(np.ndarray, np.ndarray)  # wl_axis, counts
    statusMessageSignal = pyqtSignal(str)

    def __init__(self, camera=None, spectrometer=None, parent=None):
        super().__init__(parent)
        self.camera = camera or get_andor_ccd()
        self.spectrometer = spectrometer or get_shamrock()

        self.live_timer = QTimer(self)
        self.live_timer.setInterval(40)  # ~25 FPS
        self.live_timer.timeout.connect(self._acquire_live_frame)

    def make_connection(self, widget: StaticRamanWidget):
        widget.requestAcquireSingleSignal.connect(self.acquire_single)
        widget.toggleLiveRamanSignal.connect(self.toggle_live)
        widget.applySpectrometerConfigSignal.connect(self.apply_spectrometer_config)
        widget.saveSpectrumSignal.connect(self.save_spectrum_to_file)

        self.spectrumAcquiredSignal.connect(widget.update_spectrum_data)

    @pyqtSlot(int, float)
    def apply_spectrometer_config(self, grating_idx: int, wl_center: float):
        """Aplica la red y longitud de onda central al espectrógrafo Shamrock."""
        try:
            self.spectrometer.ShamrockSetGrating(DEVICE, grating_idx)
            self.spectrometer.ShamrockSetWavelength(DEVICE, wl_center)
            # Leer el vector de calibración actualizado del detector
            _, wl_arr = self.spectrometer.ShamrockGetCalibration(DEVICE, 1002)
            self.statusMessageSignal.emit(f"Espectrógrafo configurado: Red {grating_idx}, Centro {wl_center:.2f} nm")
        except Exception as e:
            self.statusMessageSignal.emit(f"Error al configurar espectrógrafo: {e}")

    @pyqtSlot()
    def acquire_single(self):
        """Adquiere un único cuadro de la cámara y extrae el espectro 1D."""
        try:
            # Obtener eje de calibración actual
            _, wl_arr = self.spectrometer.ShamrockGetCalibration(DEVICE, 1002)
            frame = self.camera.get_most_recent_image()

            # Binning vertical en la zona central de la ranura
            if frame.shape[0] >= 520:
                spec1d = np.mean(frame[480:520, :], axis=0)
            else:
                spec1d = np.mean(frame, axis=0)

            self.spectrumAcquiredSignal.emit(wl_arr, spec1d)
            self.statusMessageSignal.emit("Espectro único adquirido exitosamente.")
        except Exception as e:
            self.statusMessageSignal.emit(f"Error en adquisición única: {e}")

    @pyqtSlot(bool)
    def toggle_live(self, active: bool):
        """Inicia o detiene la adquisición Raman continua."""
        if active:
            self.camera.start_acquisition()
            self.live_timer.start()
            self.statusMessageSignal.emit("Adquisición Live Raman iniciada.")
        else:
            self.live_timer.stop()
            self.camera.abort_acquisition()
            self.statusMessageSignal.emit("Adquisición Live Raman detenida.")

    def _acquire_live_frame(self):
        try:
            _, wl_arr = self.spectrometer.ShamrockGetCalibration(DEVICE, 1002)
            frame = self.camera.get_most_recent_image()
            if frame.shape[0] >= 520:
                spec1d = np.mean(frame[480:520, :], axis=0)
            else:
                spec1d = np.mean(frame, axis=0)
            self.spectrumAcquiredSignal.emit(wl_arr, spec1d)
        except Exception:
            pass

    @pyqtSlot(str, dict)
    def save_spectrum_to_file(self, filepath: str, metadata: dict):
        """Exporta el espectro con cabecera detallada de metadatos experimentales."""
        try:
            _, wl_arr = self.spectrometer.ShamrockGetCalibration(DEVICE, 1002)
            frame = self.camera.get_most_recent_image()
            spec1d = np.mean(frame[480:520, :], axis=0) if frame.shape[0] >= 520 else np.mean(frame, axis=0)

            laser_nm = float(metadata.get("Laser_Excitacion_nm", 532.0))
            raman_shift = wavelength_to_raman_shift(wl_arr, laser_nm)

            p = Path(filepath)
            with open(p, "w", encoding="utf-8") as f:
                f.write("# PySpectrum 3.0 — Adquisición Raman Estática\n")
                f.write("# UNSAM Nanofotónica\n")
                for k, v in metadata.items():
                    f.write(f"# {k}: {v}\n")
                f.write("# ------------------------------------------------------------\n")
                f.write("Wavelength_nm\tRaman_Shift_cm-1\tCounts_ADC\n")
                for w, rs, c in zip(wl_arr, raman_shift, spec1d):
                    f.write(f"{w:.4f}\t{rs:.3f}\t{c:.2f}\n")

            self.statusMessageSignal.emit(f"Espectro guardado en: {p.name}")
        except Exception as e:
            self.statusMessageSignal.emit(f"Error al guardar espectro: {e}")
