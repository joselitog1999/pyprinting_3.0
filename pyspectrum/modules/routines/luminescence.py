# -*- coding: utf-8 -*-
"""
luminescence.py — Rutina de Medición de Fotoluminiscencia y Emisión Anti-Stokes
PySpectrum 3.0 — UNSAM Nanofotónica

Fase 7 (DEC-021): además del monitoreo puntual histórico (un único punto fijo, I(t) integrada),
incorpora la reconstrucción moderna de la Pestaña 6 legada (Luminescence_ps.py/CIBION): control
explícito del filtro Notch 532 nm motorizado (Flipper, `core.nidaq.flipper_notch532()`) para
suprimir la dispersión Rayleigh elástica del láser de excitación, y adquisición en grilla de
coordenadas reutilizando `pyspectrum.modules.optical_support.move_stage_to()`, con lectura
consciente del modo activo de la cámara Andor (FVB/1D vs Imagen 2D).
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
from pyspectrum.modules.routines.grid_runner import GridSafetyPause, NodeFailed

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
    def update_data(self, wave: np.ndarray, spec: np.ndarray, t_axis: np.ndarray, i_axis: np.ndarray, progress: int):
        self.curve_spec.setData(wave, spec)
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

        params = QtWidgets.QGridLayout()
        params.addWidget(QtWidgets.QLabel("Láser de Excitación:"), 0, 0)
        self.cmb_grid_laser = QtWidgets.QComboBox(); self.cmb_grid_laser.addItems(SHUTTERS)
        params.addWidget(self.cmb_grid_laser, 0, 1)

        params.addWidget(QtWidgets.QLabel("Tiempo Exp (s):"), 1, 0)
        self.spin_grid_exp = QtWidgets.QDoubleSpinBox(); self.spin_grid_exp.setRange(0.001, 60.0); self.spin_grid_exp.setValue(0.2); self.spin_grid_exp.setDecimals(3)
        params.addWidget(self.spin_grid_exp, 1, 1)

        params.addWidget(QtWidgets.QLabel("Autofoco cada N nodos:"), 2, 0)
        self.spin_autofocus_every = QtWidgets.QSpinBox(); self.spin_autofocus_every.setRange(1, 1000); self.spin_autofocus_every.setValue(2)
        params.addWidget(self.spin_autofocus_every, 2, 1)
        ctrl_vlo.addLayout(params)

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
        layout.addLayout(ctrl_vlo, stretch=1)

        plot_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        self.plot_grid_map = pg.PlotWidget(title="<b>Mapa de Grilla (pendiente=gris, actual=amarillo, completado=verde)</b>")
        self.plot_grid_map.setLabels(bottom="X (µm)", left="Y (µm)")
        self.scatter_grid = pg.ScatterPlotItem(size=14, pen=pg.mkPen(None))
        self.plot_grid_map.addItem(self.scatter_grid)
        plot_splitter.addWidget(self.plot_grid_map)

        self.plot_grid_spec = pg.PlotWidget(title="<b>Espectro del Nodo Actual</b>")
        self.plot_grid_spec.setLabels(bottom="Longitud de Onda (nm)", left="Intensidad")
        self.curve_grid_spec = self.plot_grid_spec.plot(pen=pg.mkPen("#CBA6F7", width=2.0))
        plot_splitter.addWidget(self.plot_grid_spec)

        layout.addWidget(plot_splitter, stretch=3)
        return page

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
        self.curve_grid_spec.setData(wave, spec)

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
                          "lbl_grid_progress", "plot_grid_map", "scatter_grid", "plot_grid_spec", "curve_grid_spec"):
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
        widget.update_notch_status(self._notch_down)

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
        ret, axis = self.spectrometer.ShamrockGetCalibration(DEVICE, 1004)
        axis = np.asarray(axis, dtype=np.float64)
        if ret != 20202 or axis.size != 1004 or not np.all(np.isfinite(axis)):
            print(f"[{type(self).__name__}] Eje λ no confiable: código {ret}, {axis.size} puntos")
            return None
        return axis

    # ── modo puntual ──
    @pyqtSlot(str, float, int, float)
    def start_luminescence(self, laser: str, exp_time: float, n_frames: int, interval: float):
        wave = self._wave_axis()
        if wave is None:
            self.statusSignal.emit("⛔ No se pudo leer el eje λ del Shamrock: la medición no arranca.")
            self._emit_point_end()
            return
        self.wave_axis = wave
        self.laser_in_use = laser
        self.total_frames = int(n_frames)
        self.curr_frame = 0
        self.t_points, self.i_points = [], []

        def body(runner, ctl):
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
                self.i_points.append(float(np.sum(spec)))
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
        self._set_pending_nodes(list(zip(xs.tolist(), ys.tolist(), [float(z) if z is not None else None for z in zs])))

    def _set_pending_nodes(self, nodes):
        self._pending_nodes = nodes
        self.gridPreviewSignal.emit(np.array([n[0] for n in nodes]), np.array([n[1] for n in nodes]))

    @pyqtSlot(dict)
    def start_grid(self, config: dict):
        if not self._pending_nodes:
            hardware_session.statusWarningSignal.emit("No hay grilla generada/cargada para iniciar.")
            return
        wave = self._wave_axis()
        if wave is None:
            self.statusSignal.emit("⛔ No se pudo leer el eje λ del Shamrock: la grilla no arranca.")
            return
        self.grid_config = dict(config)
        self.nodes = list(self._pending_nodes)
        self.states = [NODE_PENDING] * len(self.nodes)
        self.idx = 0
        save_dir = self.grid_config.get("save_dir") or self.data_dir

        def body(runner, ctl):
            laser = self.grid_config["laser"]
            exp_time = float(self.grid_config["exp_time"])
            every = max(1, int(self.grid_config.get("autofocus_every", 1)))
            total = len(self.nodes)
            while self.idx < total:
                ctl.wait_while_paused(runner, lambda: self.gridNodeProgressSignal.emit(self.idx, total, "En pausa."))
                if ctl.take_skip():
                    self.states[self.idx] = NODE_DONE
                    self.idx += 1
                    self._emit_grid_state()
                    continue
                self.states[self.idx] = NODE_CURRENT
                self._emit_grid_state()
                x, y, z = self.nodes[self.idx]
                try:
                    self.gridNodeProgressSignal.emit(self.idx, total, "Moviendo platina...")
                    runner.move_to(x, y, z)
                    if self.idx % every == 0:
                        self.gridNodeProgressSignal.emit(self.idx, total, "Autofoco Z...")
                        runner.set_mirror("up")                  # el autofoco usa el fotodiodo confocal
                        run_z_autofocus(laser_color=laser)
                    self.gridNodeProgressSignal.emit(self.idx, total, "Adquiriendo luminiscencia...")
                    runner.set_mirror("down")
                    runner.laser(laser, True)
                    try:
                        spec, mode = runner.spectrum_1d(exp_time)
                    finally:
                        runner.laser(laser, False)
                    self.gridSpectrumUpdateSignal.emit(wave, spec)
                    self._save_node_result(self.idx, wave, spec, save_dir, mode)
                    self.states[self.idx] = NODE_DONE
                except NodeFailed as e:
                    self.states[self.idx] = NODE_FAILED
                    self._save_node_failure(self.idx, save_dir, str(e))
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

    def _save_node_result(self, idx: int, wave_axis: np.ndarray, spec: np.ndarray, save_dir: str, mode: str = ""):
        try:
            os.makedirs(save_dir, exist_ok=True)
            base = os.path.join(save_dir, f"LuminescenceNode_{idx:03d}")
            from pyspectrum.calibration.repository import correction_header_text
            np.savetxt(base + "_spectrum.txt", np.column_stack([wave_axis, spec]),
                       header=f"wavelength_nm\tintensity  (una exposición real; lectura {mode})\n"
                       + correction_header_text(self.spectrometer), fmt="%.4f", encoding="utf-8")   # R3-gui §4.6
        except OSError as e:
            print(f"[LuminescenceGrid] No se pudo guardar el nodo {idx}: {e}")

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
