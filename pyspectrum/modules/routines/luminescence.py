# -*- coding: utf-8 -*-
"""
luminescence.py — Rutina de Medición de Fotoluminiscencia y Emisión Anti-Stokes
PySpectrum 3.0 — UNSAM Nanofotónica

Monitoreo puntual (un punto fijo, I(t) integrada) y luminiscencia en grilla. La grilla repite la secuencia de
`Luminescence_ps.py` del legado (DEC-054): autofoco con el lock del satélite, centrado con el confocal por fotodiodo
del satélite, mini-mapa hiperespectral en Single-Track sobre la fibra y centro de masa del mapa. El motor está en
`luminescence_grid.py`; este módulo tiene la pestaña y el backend (hilo, verificación previa, fondo). El "notch" del
legado es el espejo de detección (línea 7).
"""
from __future__ import annotations
import os
import time
from typing import List, Optional, Tuple

import numpy as np
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import pyqtSignal, pyqtSlot, QTimer, QEventLoop
import pyqtgraph as pg

from config import SHUTTERS, PI_STAGE_RANGE_UM, PI_Z_RANGE_UM
from core.nidaq import open_shutter, close_shutter, heartbeat_shutter, flipper_notch532
from pyspectrum.drivers.shamrock_driver import DEVICE, get_shamrock
from pyspectrum.drivers.andor_ccd_driver import get_andor_ccd, READ_MODE_IMAGE
from pyspectrum.modules.hardware_session import hardware_session
from pyspectrum.modules.optical_support import run_z_autofocus, move_stage_to, get_stage_coordinates
from typing import Callable
from pyspectrum.modules.routines.grid_runner import FiberROI, GridAbort, GridSafetyPause, NodeFailed
from pyspectrum.modules.routines import luminescence_grid as lg
from pyspectrum.services.satellite_optics import (CenterScanSpec, OpticsUnavailable, SatelliteOptics,
                                                  FOCUS_LOCK_MISSING, SATELLITE_MISSING)
from pyspectrum.services.spectral_axis import spectral_axis

NODE_PENDING = 0
NODE_CURRENT = 1
NODE_DONE = 2
NODE_FAILED = 3          # la exposición del nodo falló (AND-1, R4-K P6): se registra y la grilla sigue
_NODE_STATE_COLORS = {NODE_PENDING: "#45475A", NODE_CURRENT: "#F9E2AF", NODE_DONE: "#A6E3A1", NODE_FAILED: "#F38BA8"}

_LUMINESCENCE_STYLE = """
    QLabel { color: #CDD6F4; font-weight: bold; }
    QPushButton { background-color: #313244; color: #CDD6F4; border: 1px solid #45475A; border-radius: 4px; padding: 6px 12px; font-weight: bold; }
    QPushButton:hover { background-color: #45475A; color: #89B4FA; }
    QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox { background-color: #1E1E2E; color: #CDD6F4; border: 1px solid #45475A; border-radius: 4px; padding: 4px; }
    QTabWidget::pane { border: 1px solid #313244; }
    QTabBar::tab { background: #181825; color: #A6ADC8; padding: 6px 12px; }
    QTabBar::tab:selected { background: #313244; color: #CBA6F7; font-weight: bold; }
"""


def _mirror_combo() -> QtWidgets.QComboBox:
    c = QtWidgets.QComboBox()
    c.addItems(["— confirmá dónde está —", "abajo (espectrómetro)", "arriba (confocal / cámara)"])
    c.setToolTip("El espejo de detección no tiene sensor: confirmá dónde está ahora. La rutina lo baja sola para "
                 "medir y al terminar lo devuelve a esta posición (R4-K).")
    return c


def _mirror_choice(combo: QtWidgets.QComboBox):
    return {1: "down", 2: "up"}.get(combo.currentIndex())


class LuminescencePanel(QtWidgets.QWidget):
    """Panel de Luminiscencia embebible (Pestaña 7 del shell principal de PySpectrum 3.0).
    Expone dos sub-pestañas: "Monitoreo Puntual" (histórico, un único punto fijo) y "Grilla +
    Filtro Notch" (Fase 7, control del Flipper Notch 532 nm + máquina de estados multi-nodo)."""

    startLuminescenceSignal = pyqtSignal(str, float, int, float)
    stopLuminescenceSignal = pyqtSignal()

    notchFlipperSignal = pyqtSignal(bool)  # espejo de detección: True = abajo (espectrómetro), False = arriba
    mirrorConfirmedSignal = pyqtSignal(str)  # el operador confirma dónde está el espejo antes de iniciar (R4-K)

    generateGridSignal = pyqtSignal(int, int, float, float, float, float, float)
    loadGridFileSignal = pyqtSignal(str)
    useCurrentPosSignal = pyqtSignal()
    startGridSignal = pyqtSignal(dict)
    pauseGridSignal = pyqtSignal()
    resumeGridSignal = pyqtSignal()
    nextNodeGridSignal = pyqtSignal()
    abortGridSignal = pyqtSignal()
    fiberRoiChangedSignal = pyqtSignal(int, int)   # fila central y alto de la fibra (DEC-054)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("LuminescencePanel")
        self.setStyleSheet("QWidget#LuminescencePanel { background-color: #11111B; } " + _LUMINESCENCE_STYLE)
        self._setup_ui()

    def _setup_ui(self):
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.tabs = QtWidgets.QTabWidget()
        outer.addWidget(self.tabs)
        self.tabs.addTab(self._build_single_point_tab(), "📈 Monitoreo Puntual")
        self.tabs.addTab(self._build_grid_tab(), "🔬 Grilla + Filtro Notch")

    # ── Pestaña 1: Monitoreo Puntual (histórico, Fase 1-6, sin cambios) ─────────
    def _build_single_point_tab(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

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

        from pyspectrum.ui.background_row import BackgroundRow
        self.bg_row_point = BackgroundRow(default_frames=1)          # fondo de la serie (R4-N)
        ctrl_vlo.addWidget(self.bg_row_point)

        self.cmb_mirror = _mirror_combo()
        ctrl_vlo.addWidget(QtWidgets.QLabel("Espejo de detección ahora:"))
        ctrl_vlo.addWidget(self.cmb_mirror)

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
        return page

    def _on_toggle_run(self, checked: bool):
        if checked:
            try:
                laser = self.cmb_laser.currentText()
                exp = float(self.edit_exp.text())
                n_frames = int(self.edit_nframes.text())
                interval = float(self.edit_interval.text())
                mirror = _mirror_choice(self.cmb_mirror)
                if mirror is None:
                    self.btn_run.setChecked(False)
                    self.lbl_status.setText("Confirmá dónde está el espejo de detección antes de iniciar.")
                    return
                self.mirrorConfirmedSignal.emit(mirror)

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
    def point_exposure(self):
        try:
            return float(self.edit_exp.text())
        except ValueError:
            return None

    def update_data(self, wave: np.ndarray, spec: np.ndarray, t_axis: np.ndarray, i_axis: np.ndarray, progress: int):
        self.curve_spec.setData(wave, self.bg_row_point.for_display(spec))
        self.curve_time.setData(t_axis, i_axis)
        self.progress_bar.setValue(progress)
        if progress >= 100:
            self.btn_run.setChecked(False)
            self.btn_run.setText("▶️ Iniciar Medición de Luminiscencia")
            self.btn_run.setStyleSheet("background-color: #CBA6F7; color: #11111B;")
            self.lbl_status.setText("Medición completada exitosamente.")

    # ── Pestaña 2: Grilla + Filtro Notch 532 nm (Fase 7) ────────────────────────
    def _build_grid_tab(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        ctrl_vlo = QtWidgets.QVBoxLayout()
        ctrl_vlo.setSpacing(6)

        lbl_title = QtWidgets.QLabel("🔬 <b>Luminiscencia en Grilla</b>")
        lbl_title.setStyleSheet("font-size: 10.5pt; color: #CBA6F7;")
        ctrl_vlo.addWidget(lbl_title)

        # Control del Filtro Notch 532 nm (Flipper)
        # `flipper_notch532` mueve el ESPEJO DE DETECCIÓN (línea 7), no un filtro: "notch" es un error de
        # notación heredado del legado (lab-invariants). Abajo = espectrómetro; arriba = confocal y cámara.
        notch_box = QtWidgets.QGroupBox("🪞 Espejo de detección (flipper de la línea 7)")
        notch_layout = QtWidgets.QHBoxLayout(notch_box)
        self.btn_notch_in = QtWidgets.QPushButton("⬇️ Bajar espejo (espectrómetro)")
        self.btn_notch_in.setStyleSheet("background-color: #CBA6F7; color: #11111B;")
        self.btn_notch_in.clicked.connect(lambda: self.notchFlipperSignal.emit(True))
        self.btn_notch_out = QtWidgets.QPushButton("⬆️ Subir espejo (confocal / cámara)")
        self.btn_notch_out.clicked.connect(lambda: self.notchFlipperSignal.emit(False))
        notch_layout.addWidget(self.btn_notch_in)
        notch_layout.addWidget(self.btn_notch_out)
        ctrl_vlo.addWidget(notch_box)

        self.lbl_notch_status = QtWidgets.QLabel("Espejo de detección: sin confirmar")
        self.lbl_notch_status.setStyleSheet("color: #CBA6F7; font-size: 9pt;")
        ctrl_vlo.addWidget(self.lbl_notch_status)

        # Generación / carga de grilla (mismo patrón que growth_kinetics.py/dimers.py)
        grid_gen = QtWidgets.QGridLayout()
        self.spin_rows = QtWidgets.QSpinBox(); self.spin_rows.setRange(1, 500); self.spin_rows.setValue(3)
        self.spin_cols = QtWidgets.QSpinBox(); self.spin_cols.setRange(1, 500); self.spin_cols.setValue(3)
        self.spin_dx = QtWidgets.QDoubleSpinBox(); self.spin_dx.setRange(0.01, 1000.0); self.spin_dx.setValue(3.0); self.spin_dx.setSuffix(" µm")
        self.spin_dy = QtWidgets.QDoubleSpinBox(); self.spin_dy.setRange(0.01, 1000.0); self.spin_dy.setValue(3.0); self.spin_dy.setSuffix(" µm")
        self.spin_x0 = QtWidgets.QDoubleSpinBox(); self.spin_x0.setRange(0.0, PI_STAGE_RANGE_UM); self.spin_x0.setSuffix(" µm")
        self.spin_y0 = QtWidgets.QDoubleSpinBox(); self.spin_y0.setRange(0.0, PI_STAGE_RANGE_UM); self.spin_y0.setSuffix(" µm")
        self.spin_z0 = QtWidgets.QDoubleSpinBox(); self.spin_z0.setRange(0.0, PI_Z_RANGE_UM); self.spin_z0.setSuffix(" µm")

        grid_gen.addWidget(QtWidgets.QLabel("Filas (N):"), 0, 0); grid_gen.addWidget(self.spin_rows, 0, 1)
        grid_gen.addWidget(QtWidgets.QLabel("Columnas (M):"), 1, 0); grid_gen.addWidget(self.spin_cols, 1, 1)
        grid_gen.addWidget(QtWidgets.QLabel("Δx / Δy:"), 2, 0)
        dxdy_row = QtWidgets.QHBoxLayout(); dxdy_row.addWidget(self.spin_dx); dxdy_row.addWidget(self.spin_dy)
        dxdy_widget = QtWidgets.QWidget(); dxdy_widget.setLayout(dxdy_row)
        grid_gen.addWidget(dxdy_widget, 2, 1)
        grid_gen.addWidget(QtWidgets.QLabel("Origen X0/Y0/Z0:"), 3, 0)
        origin_row = QtWidgets.QHBoxLayout()
        origin_row.addWidget(self.spin_x0); origin_row.addWidget(self.spin_y0); origin_row.addWidget(self.spin_z0)
        origin_widget = QtWidgets.QWidget(); origin_widget.setLayout(origin_row)
        grid_gen.addWidget(origin_widget, 3, 1)
        ctrl_vlo.addLayout(grid_gen)

        self.btn_use_current_pos = QtWidgets.QPushButton("📍 Usar Posición Actual como Origen")
        self.btn_use_current_pos.clicked.connect(self.useCurrentPosSignal.emit)
        ctrl_vlo.addWidget(self.btn_use_current_pos)

        row_gen_load = QtWidgets.QHBoxLayout()
        self.btn_generate_grid = QtWidgets.QPushButton("🧮 Generar Grilla N×M")
        self.btn_generate_grid.clicked.connect(self._on_generate_grid)
        self.btn_load_grid = QtWidgets.QPushButton("📂 Cargar Grilla (.txt)")
        self.btn_load_grid.clicked.connect(self._on_load_grid)
        row_gen_load.addWidget(self.btn_generate_grid)
        row_gen_load.addWidget(self.btn_load_grid)
        ctrl_vlo.addLayout(row_gen_load)

        # ── Parámetros de la secuencia del legado (Ronda 3, DEC-054) ──
        self.lbl_preflight = QtWidgets.QLabel("")
        self.lbl_preflight.setWordWrap(True)
        self.lbl_preflight.setStyleSheet("background-color: #3A1C1C; color: #F38BA8; border: 1px solid #F38BA8; "
                                         "border-radius: 4px; padding: 6px; font-weight: bold;")
        self.lbl_preflight.hide()
        ctrl_vlo.addWidget(self.lbl_preflight)

        params = QtWidgets.QGridLayout()
        params.addWidget(QtWidgets.QLabel("Láser de Excitación:"), 0, 0)
        self.cmb_grid_laser = QtWidgets.QComboBox(); self.cmb_grid_laser.addItems(SHUTTERS)
        self.cmb_grid_laser.setToolTip("Láser del centrado y de la excitación. El fotodiodo es el de este láser "
                                       "(config.PD_CHANNELS).")
        params.addWidget(self.cmb_grid_laser, 0, 1)
        ctrl_vlo.addLayout(params)

        def dspin(lo, hi, val, step, dec, suffix="", tip=""):
            w = QtWidgets.QDoubleSpinBox(); w.setRange(lo, hi); w.setDecimals(dec); w.setSingleStep(step)
            w.setValue(val)
            if suffix:
                w.setSuffix(suffix)
            if tip:
                w.setToolTip(tip)
            return w

        def ispin(lo, hi, val, suffix="", tip=""):
            w = QtWidgets.QSpinBox(); w.setRange(lo, hi); w.setValue(val)
            if suffix:
                w.setSuffix(suffix)
            if tip:
                w.setToolTip(tip)
            return w

        # Autofoco
        box_af = QtWidgets.QGroupBox("🎯 Autofoco (lock del satélite PyPrinting)")
        af = QtWidgets.QGridLayout(box_af)
        self.spin_autofocus_every = ispin(0, 1000, 2, tip="Autofoco cada N nodos; 0 = nunca. Con N > 0 hace falta el "
                                          "lock de foco fijado en el satélite Microscopio Derecho.")
        self.spin_af_shift_x = dspin(-10.0, 10.0, 0.0, 0.1, 2, " µm", "Corrimiento en x durante el autofoco (legado).")
        self.spin_af_shift_y = dspin(-10.0, 10.0, 0.0, 0.1, 2, " µm", "Corrimiento en y durante el autofoco (legado).")
        af.addWidget(QtWidgets.QLabel("Cada N nodos:"), 0, 0); af.addWidget(self.spin_autofocus_every, 0, 1)
        af.addWidget(QtWidgets.QLabel("Corrimiento x / y:"), 1, 0)
        af.addWidget(self.spin_af_shift_x, 1, 1); af.addWidget(self.spin_af_shift_y, 1, 2)
        ctrl_vlo.addWidget(box_af)

        # Centrado por fotodiodo
        self.box_center = QtWidgets.QGroupBox("📍 Centrar en cada NP (confocal por fotodiodo del satélite)")
        self.box_center.setCheckable(True); self.box_center.setChecked(True)
        self.box_center.setToolTip("Rampa x/y centrada en el nodo, con el fotodiodo del láser. Se guardan los TIFF "
                                   "NPscan crudos y la platina va al centro de masa (Confocal_ps del legado).")
        ce = QtWidgets.QGridLayout(self.box_center)
        self.spin_center_range = dspin(0.1, 75.0, 2.0, 0.1, 2, " µm")
        self.spin_center_px = ispin(2, 400, 34, " px")
        self.spin_center_thr = dspin(0.0, 0.99, 0.3, 0.05, 2, "",
                                     "Umbral del centro de masa: se anula lo menor a este valor del escaneo normalizado.")
        ce.addWidget(QtWidgets.QLabel("Rango:"), 0, 0); ce.addWidget(self.spin_center_range, 0, 1)
        ce.addWidget(QtWidgets.QLabel("Píxeles:"), 0, 2); ce.addWidget(self.spin_center_px, 0, 3)
        ce.addWidget(QtWidgets.QLabel("Filtro (umbral CM):"), 1, 0); ce.addWidget(self.spin_center_thr, 1, 1)
        ctrl_vlo.addWidget(self.box_center)

        # Mini-mapa
        self.box_minimap = QtWidgets.QGroupBox("🗺️ Mini-mapa hiperespectral en cada NP")
        self.box_minimap.setCheckable(True); self.box_minimap.setChecked(True)
        self.box_minimap.setToolTip("Una exposición por píxel alrededor del centro. Valor del mapa = Σ I(λ) dentro de "
                                    "la banda, sobre las filas de la fibra (Confocal_Spectrum_ps del legado). Apagado: "
                                    "una sola exposición en el centro.")
        mm = QtWidgets.QGridLayout(self.box_minimap)
        self.spin_map_range = dspin(0.05, 20.0, 1.0, 0.1, 2, " µm")
        self.spin_map_nx = ispin(1, 200, 20, " px")
        self.spin_map_ny = ispin(1, 200, 20, " px")
        self.chk_map_lock = QtWidgets.QCheckBox("🔗"); self.chk_map_lock.setChecked(True)
        self.chk_map_lock.setToolTip("Ny = Nx")
        self.spin_grid_exp = dspin(0.001, 60.0, 2.0, 0.1, 3, " s", "Exposición por píxel del mapa (legado: 2 s).")
        self.spin_band_lo = dspin(150.0, 1500.0, 540.0, 1.0, 1, " nm")
        self.spin_band_hi = dspin(150.0, 1500.0, 580.0, 1.0, 1, " nm")
        self.spin_map_thr = dspin(0.0, 0.99, 0.7, 0.05, 2, "", "Umbral del centro de masa del mapa (legado: 0.7).")
        self.spin_roi_center = ispin(0, 1001, 438, "", "Fila central de la fibra (desde 0, como el legado).")
        self.spin_roi_height = ispin(1, 1002, 25, " filas", "Filas de la fibra que suma la cámara (Single-Track).")
        self.lbl_roi_rows = QtWidgets.QLabel("")
        self.lbl_roi_rows.setStyleSheet("color: #A6ADC8; font-size: 8pt;")
        self.chk_laser_off = QtWidgets.QCheckBox("Láser apagado (scattering)")
        self.chk_laser_off.setToolTip("Modo scattering del legado: no se abre ningún láser durante el mapa.")
        mm.addWidget(QtWidgets.QLabel("Rango:"), 0, 0); mm.addWidget(self.spin_map_range, 0, 1)
        mm.addWidget(QtWidgets.QLabel("Nx / Ny:"), 1, 0); mm.addWidget(self.spin_map_nx, 1, 1)
        mm.addWidget(self.chk_map_lock, 1, 2); mm.addWidget(self.spin_map_ny, 1, 3)
        mm.addWidget(QtWidgets.QLabel("Exposición:"), 2, 0); mm.addWidget(self.spin_grid_exp, 2, 1)
        mm.addWidget(QtWidgets.QLabel("Banda λ:"), 3, 0); mm.addWidget(self.spin_band_lo, 3, 1)
        mm.addWidget(self.spin_band_hi, 3, 3)
        mm.addWidget(QtWidgets.QLabel("Umbral CM:"), 4, 0); mm.addWidget(self.spin_map_thr, 4, 1)
        mm.addWidget(QtWidgets.QLabel("Fibra fila / alto:"), 5, 0); mm.addWidget(self.spin_roi_center, 5, 1)
        mm.addWidget(self.spin_roi_height, 5, 3)
        mm.addWidget(self.lbl_roi_rows, 6, 0, 1, 4)
        mm.addWidget(self.chk_laser_off, 7, 0, 1, 4)
        ctrl_vlo.addWidget(self.box_minimap)

        self.chk_refresh_ref = QtWidgets.QCheckBox("Corregir el origen con el centro del mapa")
        self.chk_refresh_ref.setToolTip("Como \"Refresh reference?\" del legado: el resto de la grilla se corre por "
                                        "(centro de masa del mapa − nodo nominal).")
        ctrl_vlo.addWidget(self.chk_refresh_ref)

        self.lbl_estimate = QtWidgets.QLabel("")
        self.lbl_estimate.setStyleSheet("color: #A6ADC8; font-size: 8pt;")
        self.lbl_estimate.setWordWrap(True)
        ctrl_vlo.addWidget(self.lbl_estimate)

        self.btn_help = QtWidgets.QPushButton("📖 Ayuda")
        self.btn_help.setToolTip("Abre la sección de luminiscencia de MOD-06 en la wiki científica.")
        self.btn_help.clicked.connect(self._open_help)
        ctrl_vlo.addWidget(self.btn_help)

        self.spin_map_nx.valueChanged.connect(self._on_nx_changed)
        self.chk_map_lock.toggled.connect(lambda on: (self.spin_map_ny.setEnabled(not on),
                                                      on and self._on_nx_changed(self.spin_map_nx.value())))
        self.spin_map_ny.setEnabled(False)
        self.spin_roi_center.valueChanged.connect(self._on_roi_changed)
        self.spin_roi_height.valueChanged.connect(self._on_roi_changed)
        self.spin_band_lo.valueChanged.connect(self._on_band_spin_changed)
        self.spin_band_hi.valueChanged.connect(self._on_band_spin_changed)
        for w in (self.spin_map_nx, self.spin_map_ny, self.spin_grid_exp, self.spin_center_px, self.spin_rows,
                  self.spin_cols):
            w.valueChanged.connect(self._update_estimate)
        for b in (self.box_center, self.box_minimap):
            b.toggled.connect(self._update_estimate)

        from pyspectrum.ui.background_row import BackgroundRow
        self.bg_row_grid = BackgroundRow(default_frames=1)           # un fondo por grilla (R4-N)
        ctrl_vlo.addWidget(self.bg_row_grid)

        save_row = QtWidgets.QHBoxLayout()
        self.edit_save_dir = QtWidgets.QLineEdit("")
        self.edit_save_dir.setPlaceholderText("carpeta de trabajo/luminescence")
        self.btn_pick_save_dir = QtWidgets.QPushButton("📁")
        self.btn_pick_save_dir.clicked.connect(self._on_pick_save_dir)
        save_row.addWidget(self.edit_save_dir)
        save_row.addWidget(self.btn_pick_save_dir)
        ctrl_vlo.addLayout(save_row)
        self.cmb_grid_mirror = _mirror_combo()
        ctrl_vlo.addWidget(QtWidgets.QLabel("Espejo de detección ahora:"))
        ctrl_vlo.addWidget(self.cmb_grid_mirror)

        exec_row = QtWidgets.QHBoxLayout()
        self.btn_grid_start = QtWidgets.QPushButton("▶️ Iniciar Grilla")
        self.btn_grid_start.setStyleSheet("background-color: #A6E3A1; color: #11111B;")
        self.btn_grid_start.clicked.connect(self._on_start_grid)
        self.btn_grid_pause = QtWidgets.QPushButton("⏸️ Pausa")
        self.btn_grid_pause.clicked.connect(self.pauseGridSignal.emit)
        self.btn_grid_resume = QtWidgets.QPushButton("⏯️ Reanudar")
        self.btn_grid_resume.clicked.connect(self.resumeGridSignal.emit)
        self.btn_grid_next = QtWidgets.QPushButton("⏭️ Siguiente Nodo")
        self.btn_grid_next.clicked.connect(self.nextNodeGridSignal.emit)
        self.btn_grid_abort = QtWidgets.QPushButton("⏹️ Abortar")
        self.btn_grid_abort.setStyleSheet("background-color: #F38BA8; color: #11111B;")
        self.btn_grid_abort.clicked.connect(self.abortGridSignal.emit)
        for b in (self.btn_grid_start, self.btn_grid_pause, self.btn_grid_resume, self.btn_grid_next, self.btn_grid_abort):
            exec_row.addWidget(b)
        ctrl_vlo.addLayout(exec_row)

        self.lbl_grid_progress = QtWidgets.QLabel("Nodo: -- / -- | Estado: Esperando grilla.")
        self.lbl_grid_progress.setStyleSheet("color: #A6ADC8; font-size: 8.5pt;")
        ctrl_vlo.addWidget(self.lbl_grid_progress)

        ctrl_vlo.addStretch()
        ctrl_w = QtWidgets.QWidget(); ctrl_w.setLayout(ctrl_vlo)
        scroll = QtWidgets.QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(ctrl_w)
        scroll.setMinimumWidth(380)
        layout.addWidget(scroll, stretch=1)

        # Panel derecho 2×2 (Ronda 3, DEC-054): grilla, escaneo del fotodiodo, mini-mapa y espectro
        plots = QtWidgets.QWidget()
        pg_lay = QtWidgets.QGridLayout(plots)
        pg_lay.setContentsMargins(0, 0, 0, 0)
        self.plot_grid_map = pg.PlotWidget(title="<b>Grilla (pendiente=gris, actual=amarillo, completado=verde)</b>")
        self.plot_grid_map.setLabels(bottom="X (µm)", left="Y (µm)")
        self.scatter_grid = pg.ScatterPlotItem(size=14, pen=pg.mkPen(None))
        self.plot_grid_map.addItem(self.scatter_grid)

        self.plot_center = pg.PlotWidget(title="<b>Escaneo del fotodiodo (NP actual)</b>")
        self.plot_center.setAspectLocked(True)
        self.img_center = pg.ImageItem()
        self.plot_center.addItem(self.img_center)
        self.cross_center = pg.ScatterPlotItem(size=16, symbol="+", pen=pg.mkPen("#F38BA8", width=2))
        self.plot_center.addItem(self.cross_center)

        self.plot_minimap = pg.PlotWidget(title="<b>Mini-mapa Σ I(λ) en la banda — clic: espectro del píxel</b>")
        self.plot_minimap.setAspectLocked(True)
        self.plot_minimap.setLabels(bottom="X (µm)", left="Y (µm)")
        self.img_minimap = pg.ImageItem()
        self.plot_minimap.addItem(self.img_minimap)
        self.cross_minimap = pg.ScatterPlotItem(size=16, symbol="+", pen=pg.mkPen("#A6E3A1", width=2))
        self.plot_minimap.addItem(self.cross_minimap)
        self.img_minimap.mouseClickEvent = self._on_minimap_click

        self.plot_grid_spec = pg.PlotWidget(title="<b>Espectro (último píxel o el elegido)</b>")
        self.plot_grid_spec.setLabels(bottom="Longitud de Onda (nm)", left="Intensidad")
        self.curve_grid_spec = self.plot_grid_spec.plot(pen=pg.mkPen("#CBA6F7", width=2.0))
        self.band_region = pg.LinearRegionItem(values=(540.0, 580.0), brush=pg.mkBrush(203, 166, 247, 40))
        self.band_region.setToolTip("Banda λ del mapa: arrastrá los bordes")
        self.band_region.sigRegionChanged.connect(self._on_band_region_changed)
        self.plot_grid_spec.addItem(self.band_region)

        pg_lay.addWidget(self.plot_grid_map, 0, 0)
        pg_lay.addWidget(self.plot_center, 0, 1)
        pg_lay.addWidget(self.plot_minimap, 1, 0)
        pg_lay.addWidget(self.plot_grid_spec, 1, 1)
        layout.addWidget(plots, stretch=3)

        self._map_spectra: list = []          # espectros del mapa en curso, en orden de píxel
        self._map_wave = None
        self._map_geom = None                 # (xs, ys)
        self._on_roi_changed()
        self._update_estimate()
        return page

    # ── Interacciones de la grilla (Ronda 3, DEC-054) ──
    MAP_PIXEL_OVERHEAD_S = 0.05      # mover y asentar por píxel del mapa (la lectura Single-Track es despreciable)
    CENTER_LINE_S = 0.12             # una línea de la rampa del confocal en el caso típico (1/8.3 Hz)

    def _on_nx_changed(self, v: int):
        if self.chk_map_lock.isChecked():
            self.spin_map_ny.blockSignals(True)
            self.spin_map_ny.setValue(int(v))
            self.spin_map_ny.blockSignals(False)
            self._update_estimate()

    def _on_roi_changed(self, *_):
        c, h = self.spin_roi_center.value(), self.spin_roi_height.value()
        a, b = c - h // 2, c + (h - 1) // 2
        ok = a >= 0 and b <= 1001
        self.lbl_roi_rows.setText(f"Filas {a}–{b} (Single-Track: centro SDK {c + 1}, alto {h})" if ok
                                  else f"⚠️ Las filas {a}–{b} salen del detector (0–1001)")
        self.lbl_roi_rows.setStyleSheet("color: #A6ADC8; font-size: 8pt;" if ok else "color: #F38BA8; font-size: 8pt;")
        if ok:
            self.fiberRoiChangedSignal.emit(int(c), int(h))

    def _on_band_spin_changed(self, *_):
        lo, hi = self.spin_band_lo.value(), self.spin_band_hi.value()
        self.band_region.blockSignals(True)
        self.band_region.setRegion((lo, hi))
        self.band_region.blockSignals(False)

    def _on_band_region_changed(self, *_):
        lo, hi = self.band_region.getRegion()
        for w, v in ((self.spin_band_lo, lo), (self.spin_band_hi, hi)):
            w.blockSignals(True)
            w.setValue(float(v))
            w.blockSignals(False)

    def _update_estimate(self, *_):
        n = self.spin_rows.value() * self.spin_cols.value()
        per = 0.0
        if self.box_center.isChecked():
            per += self.CENTER_LINE_S * self.spin_center_px.value()
        if self.box_minimap.isChecked():
            per += self.spin_map_nx.value() * self.spin_map_ny.value() * (self.spin_grid_exp.value()
                                                                         + self.MAP_PIXEL_OVERHEAD_S)
        else:
            per += self.spin_grid_exp.value()
        total = per * n
        fmt = lambda s: f"{s / 3600:.1f} h" if s >= 3600 else (f"{s / 60:.1f} min" if s >= 60 else f"{s:.0f} s")
        self.lbl_estimate.setText(f"Estimado: ≈ {fmt(per)} por NP, ≈ {fmt(total)} para {n} nodos "
                                  f"(sin el autofoco). Eje λ: EEPROM, 1004 puntos.")

    def _open_help(self):
        try:
            from analysis.scientific_wiki_browser import ScientificWikiBrowserDialog
            if getattr(self, "_wiki_dialog", None) is None:
                self._wiki_dialog = ScientificWikiBrowserDialog(parent=self)
            self._wiki_dialog.navigate_to("MOD-06", None)
            self._wiki_dialog.show()
            self._wiki_dialog.raise_()
        except Exception as e:
            self.lbl_grid_progress.setText(f"No se pudo abrir la ayuda: {e}")

    def _on_minimap_click(self, ev):
        if self._map_geom is None or not self._map_spectra or self._map_wave is None:
            return
        xs, ys = self._map_geom
        pos = ev.pos()
        i, j = int(pos.x()), int(pos.y())
        k = j * len(xs) + i
        if 0 <= i < len(xs) and 0 <= j < len(ys) and k < len(self._map_spectra):
            self.curve_grid_spec.setData(self._map_wave, self.bg_row_grid.for_display(self._map_spectra[k]))
            self.plot_grid_spec.setTitle(f"<b>Espectro del píxel i={i}, j={j}</b>")

    @staticmethod
    def _rect(xs, ys):
        xs, ys = np.asarray(xs, float), np.asarray(ys, float)
        dx = (xs[1] - xs[0]) if xs.size > 1 else 1.0
        dy = (ys[1] - ys[0]) if ys.size > 1 else 1.0
        return QtCore.QRectF(float(xs[0]), float(ys[0]), dx * xs.size, dy * ys.size)

    @pyqtSlot(np.ndarray, float, float)
    def update_center_image(self, image: np.ndarray, x_um: float, y_um: float):
        self.img_center.setImage(np.asarray(image, dtype=float).T, autoLevels=True)
        self.cross_center.setData([image.shape[1] / 2.0], [image.shape[0] / 2.0])
        self.plot_center.setTitle(f"<b>Escaneo del fotodiodo — centro ({x_um:.3f}, {y_um:.3f}) µm</b>")
        self._map_spectra = []

    @pyqtSlot(np.ndarray, np.ndarray, np.ndarray)
    def update_minimap(self, image: np.ndarray, xs: np.ndarray, ys: np.ndarray):
        img = np.asarray(image, dtype=float)
        if np.count_nonzero(np.isfinite(img)) <= 1:          # empieza un mapa nuevo
            self._map_spectra = []
            self.cross_minimap.setData([], [])
        self._map_geom = (np.asarray(xs), np.asarray(ys))
        shown = np.where(np.isfinite(img), img, np.nanmin(img) if np.any(np.isfinite(img)) else 0.0)
        self.img_minimap.setImage(shown.T, autoLevels=True)
        self.img_minimap.setRect(self._rect(xs, ys))

    @pyqtSlot(np.ndarray, float, float)
    def update_minimap_done(self, image: np.ndarray, x_um: float, y_um: float):
        self.cross_minimap.setData([x_um], [y_um])
        self.plot_minimap.setTitle(f"<b>Mini-mapa — centro de masa ({x_um:.3f}, {y_um:.3f}) µm</b>")

    @pyqtSlot(str)
    def show_preflight(self, text: str):
        self.lbl_preflight.setText(f"⛔ {text}" if text else "")
        self.lbl_preflight.setVisible(bool(text))

    def _on_generate_grid(self):
        self.generateGridSignal.emit(
            self.spin_rows.value(), self.spin_cols.value(), self.spin_dx.value(), self.spin_dy.value(),
            self.spin_x0.value(), self.spin_y0.value(), self.spin_z0.value(),
        )

    def _on_load_grid(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Cargar Grilla", "", "Texto (*.txt)")
        if path:
            self.loadGridFileSignal.emit(path)

    def _on_pick_save_dir(self):
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "Directorio de Guardado")
        if path:
            self.edit_save_dir.setText(path)

    @pyqtSlot(float, float, float)
    def set_origin_fields(self, x0: float, y0: float, z0: float):
        self.spin_x0.setValue(x0)
        self.spin_y0.setValue(y0)
        self.spin_z0.setValue(z0)

    def _on_start_grid(self):
        config = {
            "laser": self.cmb_grid_laser.currentText(),
            "exp_time": self.spin_grid_exp.value(),
            "autofocus_every": self.spin_autofocus_every.value(),
            "af_shift_x": self.spin_af_shift_x.value(), "af_shift_y": self.spin_af_shift_y.value(),
            "center_enabled": self.box_center.isChecked(), "center_range_um": self.spin_center_range.value(),
            "center_pixels": self.spin_center_px.value(), "center_threshold": self.spin_center_thr.value(),
            "minimap_enabled": self.box_minimap.isChecked(), "map_range_um": self.spin_map_range.value(),
            "map_nx": self.spin_map_nx.value(), "map_ny": self.spin_map_ny.value(),
            "band_lo_nm": self.spin_band_lo.value(), "band_hi_nm": self.spin_band_hi.value(),
            "map_cm_threshold": self.spin_map_thr.value(),
            "roi_center_row": self.spin_roi_center.value(), "roi_height": self.spin_roi_height.value(),
            "laser_off": self.chk_laser_off.isChecked(), "refresh_reference": self.chk_refresh_ref.isChecked(),
            "save_dir": self.edit_save_dir.text().strip(),
            "mirror": _mirror_choice(self.cmb_grid_mirror),
        }
        if config["mirror"] is None:
            self.lbl_grid_progress.setText("Confirmá dónde está el espejo de detección antes de iniciar la grilla.")
            return
        self.cmb_grid_mirror.setCurrentIndex(0)        # la confirmación no se recuerda
        self.startGridSignal.emit(config)

    @pyqtSlot(bool)
    def update_notch_status(self, down: bool):
        self.lbl_notch_status.setText("Espejo de detección: " + ("abajo (espectrómetro)" if down
                                                                 else "arriba (confocal / cámara)")
                                      + " — según el software; no tiene sensor")

    @pyqtSlot(np.ndarray, np.ndarray)
    def preview_grid(self, xs: np.ndarray, ys: np.ndarray):
        n = len(xs)
        self.scatter_grid.setData(xs, ys, brush=[pg.mkBrush(_NODE_STATE_COLORS[NODE_PENDING])] * n)
        self.lbl_grid_progress.setText(f"Nodo: -- / {n} | Estado: Grilla lista para iniciar.")

    @pyqtSlot(np.ndarray, np.ndarray, np.ndarray, int)
    def update_grid_state(self, xs: np.ndarray, ys: np.ndarray, states: np.ndarray, current_idx: int):
        brushes = [pg.mkBrush(_NODE_STATE_COLORS.get(int(s), "#45475A")) for s in states]
        self.scatter_grid.setData(xs, ys, brush=brushes)

    @pyqtSlot(int, int, str)
    def update_grid_progress(self, idx: int, total: int, phase_label: str):
        self.lbl_grid_progress.setText(f"Nodo: {idx + 1} / {total} | Estado: {phase_label}")

    @pyqtSlot(np.ndarray, np.ndarray)
    def update_grid_spectrum(self, wave: np.ndarray, spec: np.ndarray):
        self.curve_grid_spec.setData(wave, self.bg_row_grid.for_display(spec))
        self._map_wave = wave
        if self.box_minimap.isChecked():
            self._map_spectra.append(np.asarray(spec, dtype=float))

    @pyqtSlot()
    def on_grid_finished(self):
        self.lbl_grid_progress.setText(self.lbl_grid_progress.text() + " — Finalizado.")


class LuminescenceWidget(QtWidgets.QDialog):
    """Ventana standalone para mediciones de luminiscencia bajo excitación láser
    (compatibilidad hacia atrás: uso independiente fuera del shell principal). Envuelve un
    LuminescencePanel embebido y expone sus controles/señales como atributos directos."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Fotoluminiscencia & Cinética Espectral — PySpectrum 3.0")
        self.resize(980, 600)
        self.setStyleSheet("QDialog { background-color: #11111B; } " + _LUMINESCENCE_STYLE)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.panel = LuminescencePanel(self)
        lay.addWidget(self.panel)

        for attr_name in ("cmb_laser", "edit_exp", "edit_nframes", "edit_interval",
                          "btn_run", "progress_bar", "lbl_status", "plot_spec", "curve_spec",
                          "plot_time", "curve_time",
                          "btn_notch_in", "btn_notch_out", "lbl_notch_status", "cmb_mirror", "cmb_grid_mirror",
                          "btn_generate_grid", "btn_load_grid", "btn_use_current_pos",
                          "btn_grid_start", "btn_grid_pause", "btn_grid_resume", "btn_grid_next", "btn_grid_abort",
                          "lbl_grid_progress", "plot_grid_map", "scatter_grid", "plot_grid_spec", "curve_grid_spec",
                          "spin_grid_exp", "spin_autofocus_every", "bg_row_grid", "lbl_preflight"):
            setattr(self, attr_name, getattr(self.panel, attr_name))

        for sig_name in ("startLuminescenceSignal", "stopLuminescenceSignal", "notchFlipperSignal", "mirrorConfirmedSignal",
                         "generateGridSignal", "loadGridFileSignal", "useCurrentPosSignal", "startGridSignal",
                         "pauseGridSignal", "resumeGridSignal", "nextNodeGridSignal", "abortGridSignal"):
            setattr(self, sig_name, getattr(self.panel, sig_name))

        self.update_data = self.panel.update_data
        self.update_notch_status = self.panel.update_notch_status
        self.preview_grid = self.panel.preview_grid
        self.update_grid_state = self.panel.update_grid_state
        self.update_grid_progress = self.panel.update_grid_progress
        self.update_grid_spectrum = self.panel.update_grid_spectrum
        self.on_grid_finished = self.panel.on_grid_finished
        self.set_origin_fields = self.panel.set_origin_fields
        for name in ("update_center_image", "update_minimap", "update_minimap_done", "show_preflight",
                     "fiberRoiChangedSignal"):
            setattr(self, name, getattr(self.panel, name))


class LuminescenceBackend(QtCore.QObject):
    """Luminiscencia puntual y en grilla sobre las primitivas del bloque A (AND-1, parte 3; R4-K).

    Corre en su propio hilo (`RoutineThread`): la GUI y el E-STOP responden durante cada exposición. Cada
    espectro es una exposición real (nunca "el último cuadro", R4-5). El espejo lo confirma el operador; la
    rutina lo baja para medir y al terminar lo devuelve. Un nodo cuya exposición falla queda FALLIDO y la
    grilla sigue (P6); una platina que no llega o un obturador sin confirmar pausan la grilla con los
    obturadores cerrados (DEC-036)."""

    dataUpdatedSignal = pyqtSignal(np.ndarray, np.ndarray, np.ndarray, np.ndarray, int)
    notchStateChangedSignal = pyqtSignal(bool)
    statusSignal = pyqtSignal(str)

    gridPreviewSignal = pyqtSignal(np.ndarray, np.ndarray)
    gridStateChangedSignal = pyqtSignal(np.ndarray, np.ndarray, np.ndarray, int)
    gridNodeProgressSignal = pyqtSignal(int, int, str)
    gridSpectrumUpdateSignal = pyqtSignal(np.ndarray, np.ndarray)
    gridFinishedSignal = pyqtSignal()
    originUpdatedSignal = pyqtSignal(float, float, float)
    # Secuencia completa del legado (DEC-054)
    gridCenterImageSignal = pyqtSignal(np.ndarray, float, float)        # escaneo del fotodiodo y su centro (µm)
    gridMapSignal = pyqtSignal(np.ndarray, np.ndarray, np.ndarray)      # mini-mapa parcial, xs, ys
    gridMapDoneSignal = pyqtSignal(np.ndarray, float, float)            # mini-mapa y su centro de masa (µm)
    gridPreflightSignal = pyqtSignal(str)                               # "" = sin aviso; si no, por qué no arranca

    SESSION_NAME_POINT = "Fotoluminiscencia"
    SESSION_NAME_GRID = "Fotoluminiscencia en Grilla"

    def __init__(self, camera=None, spectrometer=None, parent=None):
        super().__init__(parent)
        from pyspectrum.modules.routines.routine_thread import RoutineThread
        self.camera = camera or get_andor_ccd()
        self.spectrometer = spectrometer or get_shamrock()
        self.t_points: List[float] = []
        self.i_points: List[float] = []
        self.curr_frame = 0
        self.total_frames = 100
        self.laser_in_use = ""
        self.timer = QTimer(self)                  # compatibilidad: ya no maneja la adquisición
        self._notch_down = True                    # creencia del espejo de detección (True = abajo)
        self._mirror_confirmed: Optional[str] = None

        self._pending_nodes: List[Tuple[float, float, Optional[float]]] = []
        self.nodes: List[Tuple[float, float, Optional[float]]] = []
        self.states: List[int] = []
        self.idx = 0
        self.grid_config: dict = {}
        self._grid_running = False
        self._grid_paused = False
        self._grid_abort_requested = False
        base = os.getenv("PYSPECTRUM_ROUTINE_DATA_DIR") or os.path.join(os.path.expanduser("~"), "Documents", "Data_PySpectrum")
        self.data_dir = os.path.join(base, "luminescence")

        self.point_thread = RoutineThread(self.SESSION_NAME_POINT, self)
        self.grid_thread = RoutineThread(self.SESSION_NAME_GRID, self)
        # Fondo de los procedimientos (R4-N): uno para la serie puntual y otro para la grilla
        from pyspectrum.modules.routines.routine_dark import RoutineDark
        self.point_dark = RoutineDark(self.camera, self.spectrometer, self.SESSION_NAME_POINT, "LuminescencePoint", self)
        # El fondo de la grilla se toma en Single-Track sobre las filas de la fibra, las de la medición (DEC-054)
        self.fiber_roi = FiberROI()
        self.grid_dark = RoutineDark(self.camera, self.spectrometer, self.SESSION_NAME_GRID, "LuminescenceGrid", self,
                                     conditions_fn=self._grid_dark_conditions)
        self.optics_provider: Optional[Callable[[], Optional[SatelliteOptics]]] = None
        self._grid_label = ("Load_grid", 1000)          # rótulo y nodos por "columna" del legado
        self.run_dark = None
        self.point_thread.finished.connect(self._on_point_finished)
        self.grid_thread.finished.connect(self._on_grid_finished)
        hardware_session.emergencyStopSignal.connect(self.stop_luminescence)
        hardware_session.emergencyStopSignal.connect(self.abort_grid)

    def make_connection(self, widget):
        widget.startLuminescenceSignal.connect(self.start_luminescence)
        widget.stopLuminescenceSignal.connect(self.stop_luminescence)
        widget.mirrorConfirmedSignal.connect(self.confirm_mirror)
        self.dataUpdatedSignal.connect(widget.update_data)
        widget.notchFlipperSignal.connect(self.set_notch_flipper)
        self.notchStateChangedSignal.connect(widget.update_notch_status)
        widget.generateGridSignal.connect(self.generate_grid)
        widget.loadGridFileSignal.connect(self.load_grid_file)
        widget.useCurrentPosSignal.connect(self.use_current_position_as_origin)
        widget.startGridSignal.connect(self.start_grid)
        widget.pauseGridSignal.connect(self.pause_grid)
        widget.resumeGridSignal.connect(self.resume_grid)
        widget.nextNodeGridSignal.connect(self.next_node_grid)
        widget.abortGridSignal.connect(self.abort_grid)
        self.gridPreviewSignal.connect(widget.preview_grid)
        self.gridStateChangedSignal.connect(widget.update_grid_state)
        self.gridNodeProgressSignal.connect(widget.update_grid_progress)
        self.gridSpectrumUpdateSignal.connect(widget.update_grid_spectrum)
        self.gridFinishedSignal.connect(widget.on_grid_finished)
        self.originUpdatedSignal.connect(widget.set_origin_fields)
        if hasattr(widget, "lbl_status"):
            self.statusSignal.connect(widget.lbl_status.setText)
        for sig, slot in ((self.gridCenterImageSignal, "update_center_image"), (self.gridMapSignal, "update_minimap"),
                          (self.gridMapDoneSignal, "update_minimap_done"), (self.gridPreflightSignal, "show_preflight")):
            if hasattr(widget, slot):
                sig.connect(getattr(widget, slot))
        if hasattr(widget, "fiberRoiChangedSignal"):
            widget.fiberRoiChangedSignal.connect(self.set_fiber_roi)
        widget.update_notch_status(self._notch_down)
        if hasattr(widget, "bg_row_point"):
            from pyspectrum.modules.routines.routine_dark import wire_row
            wire_row(widget.bg_row_point, self.point_dark, widget.point_exposure, getattr(widget, "lbl_status", None))
            wire_row(widget.bg_row_grid, self.grid_dark, widget.spin_grid_exp.value,
                     getattr(widget, "lbl_grid_progress", None))

    # ── fila de la fibra y fondo de la grilla (DEC-054) ──
    @pyqtSlot(int, int)
    def set_fiber_roi(self, center_row: int, height: int):
        try:
            self.fiber_roi = FiberROI(center_row, height)
        except ValueError as e:
            self.statusSignal.emit(f"⛔ {e}")

    def _grid_dark_conditions(self, exposure_s: float):
        """Las condiciones del fondo de la grilla: Single-Track sobre la fibra configurada, no el modo en que esté
        la cámara al apretar Iniciar."""
        import dataclasses
        from pyspectrum.drivers.andor_ccd_driver import READ_MODE_SINGLE_TRACK
        from pyspectrum.services import procedure_background as pb
        cond = pb.read_conditions(self.camera, (1004,), exposure_s=exposure_s, read_mode=READ_MODE_SINGLE_TRACK)
        return dataclasses.replace(cond, read_params=tuple(self.fiber_roi.sdk_track))

    # ── espejo de detección ──
    @pyqtSlot(bool)
    def set_notch_flipper(self, down: bool):
        """Movimiento manual del espejo de detección (el "notch" del legado)."""
        flipper_notch532("down" if down else "up")
        self._notch_down = bool(down)
        self.notchStateChangedSignal.emit(self._notch_down)

    @pyqtSlot(str)
    def confirm_mirror(self, position: str):
        if position in ("up", "down"):
            self._mirror_confirmed = position

    def _hw(self):
        """Las acciones del hardware por los nombres de este módulo (los tests los interceptan acá)."""
        from types import SimpleNamespace
        from core import nidaq
        mod = __import__(__name__, fromlist=["open_shutter"])
        return SimpleNamespace(open_shutter=lambda n: mod.open_shutter(n), close_shutter=lambda n: mod.close_shutter(n),
                               close_all_shutters=nidaq.close_all_shutters, up_flipper=nidaq.up_flipper,
                               down_flipper=nidaq.down_flipper, flipper_notch532=lambda p: mod.flipper_notch532(p))

    def _wave_axis(self):
        # Una sola fuente del eje λ en PySpectrum: la EEPROM, con GetCalibration de respaldo (DEC-054)
        ax = spectral_axis(self.spectrometer, 1004)
        if ax is None:
            print(f"[{type(self).__name__}] Eje λ no confiable: ni la EEPROM ni GetCalibration dan un eje válido")
            return None
        self.wave_axis_source = ax.source
        return ax.nm

    # ── modo puntual ──
    @pyqtSlot(str, float, int, float)
    def start_luminescence(self, laser: str, exp_time: float, n_frames: int, interval: float):
        wave = self._wave_axis()
        if wave is None:
            self.statusSignal.emit("⛔ No se pudo leer el eje λ del Shamrock: la medición no arranca.")
            self._emit_point_end()
            return
        refusal = self.point_dark.check_start(float(exp_time))
        if refusal:
            self.statusSignal.emit(f"⛔ {refusal}")
            self._emit_point_end()
            return
        self.wave_axis = wave
        self.laser_in_use = laser
        self.total_frames = int(n_frames)
        self.curr_frame = 0
        self.t_points, self.i_points = [], []

        def body(runner, ctl):
            from pyspectrum.modules.routines.routine_dark import corrected
            dark = self.point_dark.ensure(runner, float(exp_time))   # fondo de la serie (R4-N)
            self.run_dark = dark
            runner.set_mirror("down")                         # el espectro se mide con el espejo abajo
            runner.laser(laser, True)
            t0 = time.monotonic()
            for k in range(self.total_frames):
                runner.check()
                t_frame = time.monotonic()
                try:
                    spec, _mode = runner.spectrum_1d(exp_time)
                except NodeFailed as e:
                    self.statusSignal.emit(f"Cuadro {k + 1} fallido: {e}")
                    continue
                self.t_points.append(time.monotonic() - t0)
                self.i_points.append(float(np.sum(corrected(spec, dark))))   # integral sin el fondo (B3)
                self.curr_frame = k + 1
                pct = int(100.0 * self.curr_frame / max(1, self.total_frames))
                self.dataUpdatedSignal.emit(wave, spec, np.array(self.t_points), np.array(self.i_points), min(pct, 99))
                runner.wait(max(0.0, float(interval) - (time.monotonic() - t_frame)))
            return "done"

        err = self.point_thread.start(body, camera=self.camera, spectrometer=self.spectrometer,
                                      mirror=self._mirror_confirmed, runner_kwargs={"hw": self._hw()})
        self._mirror_confirmed = None
        if err:
            self.statusSignal.emit(f"⛔ {err}")
            self._emit_point_end()

    @pyqtSlot()
    def stop_luminescence(self):
        self.point_thread.stop()

    def _emit_point_end(self):
        self.dataUpdatedSignal.emit(np.array([]), np.array([]), np.array(self.t_points), np.array(self.i_points), 100)

    @pyqtSlot(str)
    def _on_point_finished(self, outcome: str):
        self.laser_in_use = ""
        if outcome.startswith(("safety", "error")):
            self.statusSignal.emit("⛔ " + outcome.split(": ", 1)[-1])
        self._emit_point_end()

    # ── grilla ──
    @pyqtSlot()
    def use_current_position_as_origin(self):
        x, y, z = get_stage_coordinates()
        self.originUpdatedSignal.emit(x, y, z)

    @pyqtSlot(int, int, float, float, float, float, float)
    def generate_grid(self, rows: int, cols: int, dx_um: float, dy_um: float, x0: float, y0: float, z0: float):
        nodes = []
        for i in range(rows):
            for j in range(cols):
                nodes.append((x0 + j * dx_um, y0 + i * dy_um, z0))
        self._grid_label = (lg.grid_name(rows, cols, dx_um, dy_um), int(cols))   # Col_%03d = fila de la grilla
        self._set_pending_nodes(nodes)

    @pyqtSlot(str)
    def load_grid_file(self, path: str):
        data = np.loadtxt(path)
        if data.ndim == 1:
            data = data.reshape(1, -1)
        if data.shape[0] in (2, 3) and data.shape[1] not in (2, 3):
            data = data.T
        xs = data[:, 0]
        ys = data[:, 1]
        zs = data[:, 2] if data.shape[1] > 2 else [None] * len(xs)
        self._grid_label = ("Load_grid", 1000)          # como el legado: grilla cargada, todo en Col_001
        self._set_pending_nodes(list(zip(xs.tolist(), ys.tolist(), [float(z) if z is not None else None for z in zs])))

    def _set_pending_nodes(self, nodes):
        self._pending_nodes = nodes
        self.gridPreviewSignal.emit(np.array([n[0] for n in nodes]), np.array([n[1] for n in nodes]))

    def _params_from_config(self, config: dict) -> lg.LuminescenceGridParams:
        """El contrato de la Ronda 2 a partir de lo que manda la pestaña (DEC-054). Lo que falta toma el valor del
        legado. ValueError si algo no vale."""
        g = config.get
        roi = FiberROI(int(g("roi_center_row", self.fiber_roi.center_row)), int(g("roi_height", self.fiber_roi.height)))
        center = CenterScanSpec(range_um=float(g("center_range_um", 2.0)), pixels=int(g("center_pixels", 34)),
                                threshold=float(g("center_threshold", 0.3)))
        minimap = lg.MiniMapSpec(enabled=bool(g("minimap_enabled", True)), range_um=float(g("map_range_um", 1.0)),
                                 nx=int(g("map_nx", 20)), ny=int(g("map_ny", g("map_nx", 20))),
                                 exposure_s=float(g("exp_time", 2.0)),
                                 band_nm=(float(g("band_lo_nm", 540.0)), float(g("band_hi_nm", 580.0))),
                                 cm_threshold=float(g("map_cm_threshold", 0.7)), laser_off=bool(g("laser_off", False)))
        name, group = self._grid_label
        return lg.LuminescenceGridParams(
            laser=str(config["laser"]), autofocus_every=max(0, int(g("autofocus_every", 2))),
            af_shift_um=(float(g("af_shift_x", 0.0)), float(g("af_shift_y", 0.0))),
            center_enabled=bool(g("center_enabled", True)), center=center, minimap=minimap, roi=roi,
            refresh_reference=bool(g("refresh_reference", False)), grid_name=name, group_size=group)

    def _preflight(self, params: lg.LuminescenceGridParams) -> Tuple[Optional[str], Optional[SatelliteOptics]]:
        """Lo que impide arrancar, antes de abrir ningún láser: (motivo, servicio del satélite)."""
        optics = None
        if params.needs_optics:
            optics = self.optics_provider() if self.optics_provider is not None else None
            if optics is None:
                return SATELLITE_MISSING, None
            if params.autofocus_every > 0 and not optics.has_focus_lock():
                return FOCUS_LOCK_MISSING, None
        if not hasattr(self.camera, "set_single_track"):
            return "La cámara no admite Single-Track: la fila de la fibra no se puede leer.", None
        return None, optics

    @pyqtSlot(dict)
    def start_grid(self, config: dict):
        if not self._pending_nodes:
            hardware_session.statusWarningSignal.emit("No hay grilla generada/cargada para iniciar.")
            return
        try:
            params = self._params_from_config(config)
        except (ValueError, KeyError) as e:
            self.statusSignal.emit(f"⛔ Parámetros inválidos: {e}")
            self.gridPreflightSignal.emit(f"Parámetros inválidos: {e}")
            return
        self.fiber_roi = params.roi
        refusal, optics = self._preflight(params)
        if refusal:
            self.statusSignal.emit(f"⛔ {refusal}")
            self.gridPreflightSignal.emit(refusal)
            hardware_session.statusWarningSignal.emit(refusal)
            return
        wave = self._wave_axis()
        if wave is None:
            self.statusSignal.emit("⛔ No se pudo leer el eje λ del Shamrock: la grilla no arranca.")
            return
        exp_time = params.minimap.exposure_s
        refusal = self.grid_dark.check_start(exp_time)
        if refusal:
            self.statusSignal.emit(f"⛔ {refusal}")
            hardware_session.statusWarningSignal.emit(refusal)
            return
        self.gridPreflightSignal.emit("")
        self.grid_config = dict(config)
        self.grid_params = params
        self.nodes = list(self._pending_nodes)
        self.states = [NODE_PENDING] * len(self.nodes)
        self.idx = 0
        save_dir = self.grid_config.get("save_dir") or self.data_dir
        axis_source = getattr(self, "wave_axis_source", "?")
        events = lg.NodeEvents(
            center=lambda img, x, y: self.gridCenterImageSignal.emit(np.asarray(img, dtype=np.float64), float(x), float(y)),
            map_update=lambda m, xs, ys: self.gridMapSignal.emit(np.array(m, copy=True), np.asarray(xs), np.asarray(ys)),
            spectrum=lambda w, s: self.gridSpectrumUpdateSignal.emit(np.asarray(w), np.asarray(s, dtype=np.float64)),
            map_done=lambda m, x, y: self.gridMapDoneSignal.emit(np.array(m, copy=True), float(x), float(y)))

        def body(runner, ctl):
            from pyspectrum.modules.optical_support import read_bs_level
            total = len(self.nodes)
            runner.use_fiber_roi(params.roi)                      # la medición y el fondo, en la fibra
            self.run_dark = self.grid_dark.ensure_with(runner.expose, exp_time)
            from pyspectrum.calibration.repository import spectrum_software_correction
            writer = lg.LuminescenceRunWriter(save_dir, params, wave, axis_source, dark=self.run_dark,
                                              correction=spectrum_software_correction(self.spectrometer))
            writer.set_dark_header(self.grid_dark.header_text(self.run_dark, writer.run_dir))
            self.run_dir = writer.run_dir
            engine = lg.LuminescenceGridEngine(runner, optics, params, wave, writer, read_bs_level, events)

            def progress(text):
                self.gridNodeProgressSignal.emit(self.idx, total, text)
            engine.ev.progress = progress
            while self.idx < total:
                ctl.wait_while_paused(runner, lambda: self.gridNodeProgressSignal.emit(self.idx, total, "En pausa."))
                if ctl.take_skip():
                    self.states[self.idx] = NODE_DONE
                    self.idx += 1
                    self._emit_grid_state()
                    continue
                self.states[self.idx] = NODE_CURRENT
                self._emit_grid_state()
                try:
                    engine.run_node(self.idx, self.nodes[self.idx])
                    self.states[self.idx] = NODE_DONE
                except (NodeFailed, OpticsUnavailable) as e:
                    self.states[self.idx] = NODE_FAILED
                    self._save_node_failure(self.idx, writer.run_dir, str(e))
                    self.gridNodeProgressSignal.emit(self.idx, total, f"Nodo fallido: {e}")
                except GridSafetyPause as e:
                    self.states[self.idx] = NODE_PENDING
                    self._emit_grid_state()
                    self.statusSignal.emit(f"⛔ {e} Reanudá cuando esté resuelto.")
                    self.gridNodeProgressSignal.emit(self.idx, total, f"Pausa de seguridad: {e}")
                    ctl.pause.set()
                    continue
                self.idx += 1
                self._emit_grid_state()
            writer.write_info([("Nodes_done", sum(1 for s in self.states if s == NODE_DONE)),
                               ("Nodes_failed", sum(1 for s in self.states if s == NODE_FAILED))])
            return "done"

        err = self.grid_thread.start(body, camera=self.camera, spectrometer=self.spectrometer,
                                     mirror=self.grid_config.get("mirror"), runner_kwargs={"hw": self._hw()})
        if err:
            self.statusSignal.emit(f"⛔ {err}")
            hardware_session.statusWarningSignal.emit(err)
            return
        self._grid_running = True
        self._grid_paused = False
        self._grid_abort_requested = False
        self._emit_grid_state()

    @pyqtSlot()
    def pause_grid(self):
        self._grid_paused = True
        self.grid_thread.pause()

    @pyqtSlot()
    def resume_grid(self):
        self._grid_paused = False
        self.grid_thread.resume()

    @pyqtSlot()
    def next_node_grid(self):
        if self._grid_running:
            self.grid_thread.skip()

    @pyqtSlot()
    def abort_grid(self):
        if not self._grid_running:
            return
        self._grid_abort_requested = True
        self.grid_thread.stop()

    @pyqtSlot(str)
    def _on_grid_finished(self, outcome: str):
        self._grid_running = False
        if outcome.startswith(("safety", "error")):
            self.statusSignal.emit("⛔ " + outcome.split(": ", 1)[-1])
        self.gridFinishedSignal.emit()

    def _emit_grid_state(self):
        xs = np.array([n[0] for n in self.nodes])
        ys = np.array([n[1] for n in self.nodes])
        self.gridStateChangedSignal.emit(xs, ys, np.array(self.states), self.idx)

    def _save_node_failure(self, idx: int, save_dir: str, reason: str):
        try:
            os.makedirs(save_dir, exist_ok=True)
            with open(os.path.join(save_dir, f"LuminescenceNode_{idx:03d}_FAILED.txt"), "w", encoding="utf-8") as f:
                f.write(reason + "\n")
        except OSError as e:
            print(f"[LuminescenceGrid] No se pudo registrar la falla del nodo {idx}: {e}")

    def shutdown(self, timeout_ms: int = 3000):
        a = self.point_thread.shutdown(timeout_ms)
        b = self.grid_thread.shutdown(timeout_ms)
        return [a, b]
