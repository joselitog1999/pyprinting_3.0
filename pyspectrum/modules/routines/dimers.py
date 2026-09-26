# -*- coding: utf-8 -*-
"""
dimers.py — Caracterización Espectral de Dímeros Plasmónicos y Acoplamiento
PySpectrum 3.0 — UNSAM Nanofotónica

Fase 6 (DEC-020): además de la espectroscopía de polarización histórica (par de espectros
paralelo/perpendicular ya adquiridos manualmente), incorpora la reconstrucción moderna de la
Pestaña 5 legada (Dimers_ps.py/CIBION): la secuencia automatizada de fabricación de dímeros por
impresión fototérmica secuencial de dos nanopartículas con detección de evento por salto de
traza de fotodiodo, centrado sub-píxel confocal entre impresiones, y espectroscopía final del
par acoplado.
"""
from __future__ import annotations
import os
import time
from typing import List, Optional, Tuple

import numpy as np
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import pyqtSignal, pyqtSlot, QTimer, QEventLoop
import pyqtgraph as pg

from config import SHUTTERS, PI_STAGE_RANGE_UM
from core.nidaq import open_shutter, close_shutter, heartbeat_shutter
from pyspectrum.drivers.shamrock_driver import DEVICE, get_shamrock
from pyspectrum.drivers.andor_ccd_driver import get_andor_ccd
from pyspectrum.modules.hardware_session import hardware_session
from pyspectrum.modules.optical_support import (
    run_z_autofocus, run_confocal_centering, move_stage_to, get_stage_coordinates, read_photodiode_level,
)

NODE_PENDING = 0
NODE_CURRENT = 1
NODE_DONE = 2
_NODE_STATE_COLORS = {NODE_PENDING: "#45475A", NODE_CURRENT: "#F9E2AF", NODE_DONE: "#A6E3A1"}

_DIMERS_STYLE = """
    QLabel { color: #CDD6F4; font-weight: bold; }
    QPushButton { background-color: #313244; color: #CDD6F4; border: 1px solid #45475A; border-radius: 4px; padding: 6px 12px; font-weight: bold; }
    QPushButton:hover { background-color: #45475A; color: #A6E3A1; }
    QLineEdit, QSpinBox, QDoubleSpinBox { background-color: #1E1E2E; color: #CDD6F4; border: 1px solid #45475A; border-radius: 4px; padding: 4px; }
    QTabWidget::pane { border: 1px solid #313244; }
    QTabBar::tab { background: #181825; color: #A6ADC8; padding: 6px 12px; }
    QTabBar::tab:selected { background: #313244; color: #A6E3A1; font-weight: bold; }
"""


class DimersWidget(QtWidgets.QDialog):
    """Ventana para análisis espectral de acoplamiento plasmónico en dímeros. Expone dos
    sub-pestañas: "Polarización" (histórico, espectroscopía manual ∥/⟂) y "Secuencia de
    Impresión" (Fase 6, fabricación automatizada de pares NP1→NP2 con espectroscopía final)."""

    acquirePolarizationSignal = pyqtSignal(str, float)  # (mode: 'parallel'/'perpendicular', exp_time)

    # ── Señales de la secuencia automatizada (Fase 6) ────────────────────────────
    generateGridSignal = pyqtSignal(int, int, float, float, float, float, float)
    loadGridFileSignal = pyqtSignal(str)
    useCurrentPosSignal = pyqtSignal()
    startSequenceSignal = pyqtSignal(dict)
    pauseSequenceSignal = pyqtSignal()
    resumeSequenceSignal = pyqtSignal()
    nextPairSequenceSignal = pyqtSignal()
    abortSequenceSignal = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Caracterización de Dímeros Plasmónicos — PySpectrum 3.0")
        self.resize(980, 600)
        self.setStyleSheet("QDialog { background-color: #11111B; } " + _DIMERS_STYLE)
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.tabs = QtWidgets.QTabWidget()
        outer.addWidget(self.tabs)
        self.tabs.addTab(self._build_polarization_tab(), "⚡ Polarización")
        self.tabs.addTab(self._build_sequence_tab(), "🔗 Secuencia de Impresión")
        self._seq_xs: np.ndarray = np.array([])
        self._seq_ys: np.ndarray = np.array([])

    # ── Pestaña 1: Polarización (histórico, Fase 1-5, sin cambios) ──────────────
    def _build_polarization_tab(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(page)
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
        return page

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

    # ── Pestaña 2: Secuencia de Impresión de Dímeros (Fase 6) ───────────────────
    def _build_sequence_tab(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        ctrl_vlo = QtWidgets.QVBoxLayout()
        ctrl_vlo.setSpacing(6)

        lbl_title = QtWidgets.QLabel("🔗 <b>Fabricación Automatizada de Dímeros</b>")
        lbl_title.setStyleSheet("font-size: 10.5pt; color: #A6E3A1;")
        ctrl_vlo.addWidget(lbl_title)

        grid_gen = QtWidgets.QGridLayout()
        self.spin_rows = QtWidgets.QSpinBox(); self.spin_rows.setRange(1, 500); self.spin_rows.setValue(3)
        self.spin_cols = QtWidgets.QSpinBox(); self.spin_cols.setRange(1, 500); self.spin_cols.setValue(3)
        self.spin_dx_grid = QtWidgets.QDoubleSpinBox(); self.spin_dx_grid.setRange(0.01, 1000.0); self.spin_dx_grid.setValue(3.0); self.spin_dx_grid.setSuffix(" µm")
        self.spin_dy_grid = QtWidgets.QDoubleSpinBox(); self.spin_dy_grid.setRange(0.01, 1000.0); self.spin_dy_grid.setValue(3.0); self.spin_dy_grid.setSuffix(" µm")
        self.spin_x0 = QtWidgets.QDoubleSpinBox(); self.spin_x0.setRange(0.0, PI_STAGE_RANGE_UM); self.spin_x0.setSuffix(" µm")
        self.spin_y0 = QtWidgets.QDoubleSpinBox(); self.spin_y0.setRange(0.0, PI_STAGE_RANGE_UM); self.spin_y0.setSuffix(" µm")
        self.spin_z0 = QtWidgets.QDoubleSpinBox(); self.spin_z0.setRange(0.0, PI_STAGE_RANGE_UM); self.spin_z0.setSuffix(" µm")

        grid_gen.addWidget(QtWidgets.QLabel("Filas (N):"), 0, 0); grid_gen.addWidget(self.spin_rows, 0, 1)
        grid_gen.addWidget(QtWidgets.QLabel("Columnas (M):"), 1, 0); grid_gen.addWidget(self.spin_cols, 1, 1)
        grid_gen.addWidget(QtWidgets.QLabel("Δx / Δy:"), 2, 0)
        dxdy_row = QtWidgets.QHBoxLayout(); dxdy_row.addWidget(self.spin_dx_grid); dxdy_row.addWidget(self.spin_dy_grid)
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
        params.addWidget(QtWidgets.QLabel("Láser de Impresión:"), 0, 0)
        self.cmb_seq_laser = QtWidgets.QComboBox(); self.cmb_seq_laser.addItems(SHUTTERS)
        params.addWidget(self.cmb_seq_laser, 0, 1)

        params.addWidget(QtWidgets.QLabel("Tiempo Exp Espectro (s):"), 1, 0)
        self.spin_seq_exp = QtWidgets.QDoubleSpinBox(); self.spin_seq_exp.setRange(0.001, 60.0); self.spin_seq_exp.setValue(0.5); self.spin_seq_exp.setDecimals(3)
        params.addWidget(self.spin_seq_exp, 1, 1)

        params.addWidget(QtWidgets.QLabel("Offset NP2 Δx (nm):"), 2, 0)
        self.spin_offset_dx_nm = QtWidgets.QDoubleSpinBox(); self.spin_offset_dx_nm.setRange(-2000.0, 2000.0); self.spin_offset_dx_nm.setValue(100.0)
        params.addWidget(self.spin_offset_dx_nm, 2, 1)

        params.addWidget(QtWidgets.QLabel("Offset NP2 Δy (nm):"), 3, 0)
        self.spin_offset_dy_nm = QtWidgets.QDoubleSpinBox(); self.spin_offset_dy_nm.setRange(-2000.0, 2000.0); self.spin_offset_dy_nm.setValue(0.0)
        params.addWidget(self.spin_offset_dy_nm, 3, 1)

        params.addWidget(QtWidgets.QLabel("Umbral de Impresión (I_new > I_old ×):"), 4, 0)
        self.spin_trace_threshold = QtWidgets.QDoubleSpinBox(); self.spin_trace_threshold.setRange(1.01, 20.0); self.spin_trace_threshold.setValue(1.2)
        params.addWidget(self.spin_trace_threshold, 4, 1)

        params.addWidget(QtWidgets.QLabel("Tiempo máx. impresión (s):"), 5, 0)
        self.spin_trace_max_s = QtWidgets.QDoubleSpinBox(); self.spin_trace_max_s.setRange(1.0, 300.0); self.spin_trace_max_s.setValue(20.0)
        params.addWidget(self.spin_trace_max_s, 5, 1)

        params.addWidget(QtWidgets.QLabel("Re-enfoque cada K pares:"), 6, 0)
        self.spin_refocus_every = QtWidgets.QSpinBox(); self.spin_refocus_every.setRange(1, 1000); self.spin_refocus_every.setValue(1)
        params.addWidget(self.spin_refocus_every, 6, 1)
        ctrl_vlo.addLayout(params)

        save_row = QtWidgets.QHBoxLayout()
        self.edit_save_dir = QtWidgets.QLineEdit(os.path.join(os.getcwd(), "dimers_sequence_data"))
        self.btn_pick_save_dir = QtWidgets.QPushButton("📁")
        self.btn_pick_save_dir.clicked.connect(self._on_pick_save_dir)
        save_row.addWidget(self.edit_save_dir)
        save_row.addWidget(self.btn_pick_save_dir)
        ctrl_vlo.addLayout(save_row)

        exec_row = QtWidgets.QHBoxLayout()
        self.btn_seq_start = QtWidgets.QPushButton("▶️ Iniciar Secuencia")
        self.btn_seq_start.setStyleSheet("background-color: #A6E3A1; color: #11111B;")
        self.btn_seq_start.clicked.connect(self._on_start_sequence)
        self.btn_seq_pause = QtWidgets.QPushButton("⏸️ Pausa")
        self.btn_seq_pause.clicked.connect(self.pauseSequenceSignal.emit)
        self.btn_seq_resume = QtWidgets.QPushButton("⏯️ Reanudar")
        self.btn_seq_resume.clicked.connect(self.resumeSequenceSignal.emit)
        self.btn_seq_next = QtWidgets.QPushButton("⏭️ Siguiente Par")
        self.btn_seq_next.clicked.connect(self.nextPairSequenceSignal.emit)
        self.btn_seq_abort = QtWidgets.QPushButton("⏹️ Abortar")
        self.btn_seq_abort.setStyleSheet("background-color: #F38BA8; color: #11111B;")
        self.btn_seq_abort.clicked.connect(self.abortSequenceSignal.emit)
        for b in (self.btn_seq_start, self.btn_seq_pause, self.btn_seq_resume, self.btn_seq_next, self.btn_seq_abort):
            exec_row.addWidget(b)
        ctrl_vlo.addLayout(exec_row)

        self.lbl_seq_progress = QtWidgets.QLabel("Par: -- / -- | Estado: Esperando grilla.")
        self.lbl_seq_progress.setStyleSheet("color: #A6ADC8; font-size: 8.5pt;")
        ctrl_vlo.addWidget(self.lbl_seq_progress)

        ctrl_vlo.addStretch()
        layout.addLayout(ctrl_vlo, stretch=1)

        plot_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        self.plot_seq_map = pg.PlotWidget(title="<b>Mapa de Pares (pendiente=gris, actual=amarillo, completado=verde)</b>")
        self.plot_seq_map.setLabels(bottom="X (µm)", left="Y (µm)")
        self.scatter_seq = pg.ScatterPlotItem(size=14, pen=pg.mkPen(None))
        self.plot_seq_map.addItem(self.scatter_seq)
        plot_splitter.addWidget(self.plot_seq_map)

        self.plot_seq_spec = pg.PlotWidget(title="<b>Espectro del Último Dímero Acoplado</b>")
        self.plot_seq_spec.setLabels(bottom="Longitud de Onda (nm)", left="Intensidad")
        self.curve_seq_spec = self.plot_seq_spec.plot(pen=pg.mkPen("#A6E3A1", width=2.0))
        plot_splitter.addWidget(self.plot_seq_spec)

        layout.addWidget(plot_splitter, stretch=3)
        return page

    def _on_generate_grid(self):
        self.generateGridSignal.emit(
            self.spin_rows.value(), self.spin_cols.value(), self.spin_dx_grid.value(), self.spin_dy_grid.value(),
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

    def _on_start_sequence(self):
        config = {
            "laser": self.cmb_seq_laser.currentText(),
            "exp_time": self.spin_seq_exp.value(),
            "dx_nm": self.spin_offset_dx_nm.value(),
            "dy_nm": self.spin_offset_dy_nm.value(),
            "trace_threshold_ratio": self.spin_trace_threshold.value(),
            "trace_max_s": self.spin_trace_max_s.value(),
            "refocus_every": self.spin_refocus_every.value(),
            "save_dir": self.edit_save_dir.text().strip() or ".",
        }
        self.startSequenceSignal.emit(config)

    @pyqtSlot(np.ndarray, np.ndarray)
    def preview_grid(self, xs: np.ndarray, ys: np.ndarray):
        self._seq_xs, self._seq_ys = xs, ys
        n = len(xs)
        self.scatter_seq.setData(xs, ys, brush=[pg.mkBrush(_NODE_STATE_COLORS[NODE_PENDING])] * n)
        self.lbl_seq_progress.setText(f"Par: -- / {n} | Estado: Grilla lista para iniciar.")

    @pyqtSlot(np.ndarray, np.ndarray, np.ndarray, int)
    def update_grid_state(self, xs: np.ndarray, ys: np.ndarray, states: np.ndarray, current_idx: int):
        self._seq_xs, self._seq_ys = xs, ys
        brushes = [pg.mkBrush(_NODE_STATE_COLORS.get(int(s), "#45475A")) for s in states]
        self.scatter_seq.setData(xs, ys, brush=brushes)

    @pyqtSlot(int, int, str)
    def update_sequence_progress(self, idx: int, total: int, phase_label: str):
        self.lbl_seq_progress.setText(f"Par: {idx + 1} / {total} | Estado: {phase_label}")

    @pyqtSlot(np.ndarray, np.ndarray, float, float, float, float)
    def update_pair_finished(self, wave: np.ndarray, spec: np.ndarray, x1: float, y1: float, x2: float, y2: float):
        self.curve_seq_spec.setData(wave, spec)

    @pyqtSlot()
    def on_sequence_finished(self):
        self.lbl_seq_progress.setText(self.lbl_seq_progress.text() + " — Finalizado.")


class DimersBackend(QtCore.QObject):
    """Lógica de adquisición para dímeros plasmónicos: espectroscopía de polarización manual
    (Fase 1-5, intacta) más la secuencia automatizada de fabricación NP1→NP2 (Fase 6, DEC-020)."""

    dimerDataSignal = pyqtSignal(str, np.ndarray, np.ndarray, np.ndarray)

    # ── Señales de la secuencia automatizada (Fase 6) ────────────────────────────
    gridPreviewSignal = pyqtSignal(np.ndarray, np.ndarray)
    gridStateChangedSignal = pyqtSignal(np.ndarray, np.ndarray, np.ndarray, int)
    sequenceProgressSignal = pyqtSignal(int, int, str)
    pairFinishedSignal = pyqtSignal(np.ndarray, np.ndarray, float, float, float, float)
    sequenceFinishedSignal = pyqtSignal()
    originUpdatedSignal = pyqtSignal(float, float, float)

    SESSION_NAME_POLARIZATION = "Dímeros Plasmónicos"
    SESSION_NAME_SEQUENCE = "Fabricación de Dímeros"

    def __init__(self, camera=None, spectrometer=None, parent=None):
        super().__init__(parent)
        self.camera = camera or get_andor_ccd()
        self.spectrometer = spectrometer or get_shamrock()

        self.spec_par = None
        self.spec_perp = None
        self.wave_axis = np.linspace(450, 750, 1004)

        # Estado de la secuencia automatizada (Fase 6)
        self._pending_nodes: List[Tuple[float, float, Optional[float]]] = []
        self.nodes: List[Tuple[float, float, Optional[float]]] = []
        self.states: List[int] = []
        self.idx = 0
        self.seq_config: dict = {}
        self._pairs_done = 0
        self._seq_running = False
        self._seq_paused = False
        self._seq_abort_requested = False

        hardware_session.emergencyStopSignal.connect(self.abort_sequence)

    def make_connection(self, widget: DimersWidget):
        widget.acquirePolarizationSignal.connect(self.acquire_polarization)
        self.dimerDataSignal.connect(widget.update_dimer_data)

        widget.generateGridSignal.connect(self.generate_grid)
        widget.loadGridFileSignal.connect(self.load_grid_file)
        widget.useCurrentPosSignal.connect(self.use_current_position_as_origin)
        widget.startSequenceSignal.connect(self.start_sequence)
        widget.pauseSequenceSignal.connect(self.pause_sequence)
        widget.resumeSequenceSignal.connect(self.resume_sequence)
        widget.nextPairSequenceSignal.connect(self.next_pair_sequence)
        widget.abortSequenceSignal.connect(self.abort_sequence)

        self.gridPreviewSignal.connect(widget.preview_grid)
        self.gridStateChangedSignal.connect(widget.update_grid_state)
        self.sequenceProgressSignal.connect(widget.update_sequence_progress)
        self.pairFinishedSignal.connect(widget.update_pair_finished)
        self.sequenceFinishedSignal.connect(widget.on_sequence_finished)
        self.originUpdatedSignal.connect(widget.set_origin_fields)

    # ══════════════════════════════════════════════════════════════════════════
    # Espectroscopía de Polarización (Fase 1-5, intacta)
    # ══════════════════════════════════════════════════════════════════════════
    @pyqtSlot(str, float)
    def acquire_polarization(self, mode: str, exp_time: float):
        if not hardware_session.acquire_session(self.SESSION_NAME_POLARIZATION):
            return
        try:
            self.camera.set_exposure_time(exp_time)
            ret, self.wave_axis = self.spectrometer.ShamrockGetCalibration(DEVICE, 1004)

            self.camera.start_acquisition()
            frame = self.camera.get_most_recent_image()
            if hasattr(frame, "ndim") and frame.ndim == 2:
                spec = np.mean(frame, axis=0)
            else:
                spec = np.asarray(frame, dtype=float)

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
        finally:
            hardware_session.release_session(self.SESSION_NAME_POLARIZATION)

    # ══════════════════════════════════════════════════════════════════════════
    # Secuencia Automatizada de Fabricación NP1→NP2 (Fase 6, DEC-020)
    # ══════════════════════════════════════════════════════════════════════════
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

    def _set_pending_nodes(self, nodes: List[Tuple[float, float, Optional[float]]]):
        self._pending_nodes = nodes
        xs = np.array([n[0] for n in nodes])
        ys = np.array([n[1] for n in nodes])
        self.gridPreviewSignal.emit(xs, ys)

    @pyqtSlot(dict)
    def start_sequence(self, config: dict):
        if not self._pending_nodes:
            hardware_session.statusWarningSignal.emit("No hay grilla de posiciones NP1 generada/cargada.")
            return
        if not hardware_session.acquire_session(self.SESSION_NAME_SEQUENCE):
            return

        self.seq_config = config
        self.nodes = list(self._pending_nodes)
        self.states = [NODE_PENDING] * len(self.nodes)
        self.idx = 0
        self._pairs_done = 0
        self._seq_running = True
        self._seq_paused = False
        self._seq_abort_requested = False
        self._emit_seq_state()
        QTimer.singleShot(0, self._process_next_pair)

    @pyqtSlot()
    def pause_sequence(self):
        self._seq_paused = True

    @pyqtSlot()
    def resume_sequence(self):
        if self._seq_paused and self._seq_running:
            self._seq_paused = False
            QTimer.singleShot(0, self._process_next_pair)

    @pyqtSlot()
    def next_pair_sequence(self):
        if not self._seq_running or self.idx >= len(self.nodes):
            return
        self.states[self.idx] = NODE_DONE
        self.idx += 1
        self._emit_seq_state()
        if not self._seq_paused:
            QTimer.singleShot(0, self._process_next_pair)

    @pyqtSlot()
    def abort_sequence(self):
        if not self._seq_running:
            return
        self._seq_abort_requested = True
        self._seq_running = False
        laser = self.seq_config.get("laser", "")
        if laser:
            try:
                close_shutter(laser)
            except Exception as e:
                print(f"[DimersSequence] Error cerrando obturador en abort: {e}")
        hardware_session.release_session(self.SESSION_NAME_SEQUENCE)
        self.sequenceFinishedSignal.emit()

    def _emit_seq_state(self):
        xs = np.array([n[0] for n in self.nodes])
        ys = np.array([n[1] for n in self.nodes])
        states = np.array(self.states)
        self.gridStateChangedSignal.emit(xs, ys, states, self.idx)

    def _check_seq_abort(self) -> bool:
        if self._seq_abort_requested or hardware_session.is_emergency_stopped or not self._seq_running:
            self.abort_sequence()
            return True
        return False

    def _monitor_print_trace(self, threshold_ratio: float, max_s: float) -> bool:
        """Monitorea la traza de fotodiodo y detecta el salto característico de un evento de
        impresión fototérmica (I_new > I_old × threshold_ratio), replicando
        Dimers_ps.py::grid_trace_detect. Devuelve True si detectó el evento, False si se agotó
        el tiempo máximo sin detección."""
        t0 = time.time()
        state = {"i_old": None, "detected": False}
        loop = QEventLoop()
        timer = QTimer()
        timer.setInterval(50)

        def _tick():
            if self._seq_abort_requested or hardware_session.is_emergency_stopped:
                loop.quit()
                return
            heartbeat_shutter(30.0)
            level = read_photodiode_level()
            if state["i_old"] is None:
                state["i_old"] = level if level > 0 else 1e-9
            elif level > state["i_old"] * threshold_ratio:
                state["detected"] = True
                loop.quit()
                return
            if time.time() - t0 >= max_s:
                loop.quit()

        timer.timeout.connect(_tick)
        timer.start()
        loop.exec()
        timer.stop()
        return state["detected"]

    def _process_next_pair(self):
        if self._check_seq_abort():
            return
        if self._seq_paused:
            return
        if self.idx >= len(self.nodes):
            self._finish_sequence()
            return

        self.states[self.idx] = NODE_CURRENT
        self._emit_seq_state()
        x, y, z = self.nodes[self.idx]
        cfg = self.seq_config
        laser = cfg["laser"]
        exp_time = float(cfg["exp_time"])
        threshold_ratio = float(cfg.get("trace_threshold_ratio", 1.2))
        trace_max_s = float(cfg.get("trace_max_s", 20.0))

        self.sequenceProgressSignal.emit(self.idx, len(self.nodes), "Moviendo a NP1...")
        move_stage_to(x, y, z)
        if self._check_seq_abort():
            return

        self.sequenceProgressSignal.emit(self.idx, len(self.nodes), "Imprimiendo NP1 (esperando salto de traza)...")
        open_shutter(laser)
        try:
            self._monitor_print_trace(threshold_ratio, trace_max_s)
        finally:
            close_shutter(laser)
        if self._check_seq_abort():
            return

        self.sequenceProgressSignal.emit(self.idx, len(self.nodes), "Centrando NP1 (confocal sub-píxel)...")
        x1, y1 = run_confocal_centering(range_um=1.0)
        if self._check_seq_abort():
            return

        dx_um = float(cfg.get("dx_nm", 100.0)) / 1000.0
        dy_um = float(cfg.get("dy_nm", 0.0)) / 1000.0
        self.sequenceProgressSignal.emit(self.idx, len(self.nodes), "Desplazando offset nanométrico a NP2...")
        move_stage_to(x1 + dx_um, y1 + dy_um, None)
        if self._check_seq_abort():
            return

        self.sequenceProgressSignal.emit(self.idx, len(self.nodes), "Imprimiendo NP2 (esperando salto de traza)...")
        open_shutter(laser)
        try:
            self._monitor_print_trace(threshold_ratio, trace_max_s)
        finally:
            close_shutter(laser)
        if self._check_seq_abort():
            return

        self.sequenceProgressSignal.emit(self.idx, len(self.nodes), "Post-escaneo de validación morfológica...")
        x2, y2 = run_confocal_centering(range_um=1.0)
        if self._check_seq_abort():
            return

        self.sequenceProgressSignal.emit(self.idx, len(self.nodes), "Espectroscopía del dímero acoplado...")
        self.camera.set_exposure_time(exp_time)
        ret, wave_axis = self.spectrometer.ShamrockGetCalibration(DEVICE, 1004)
        self.camera.start_acquisition()
        frame = self.camera.get_most_recent_image()
        spec = np.mean(frame, axis=0) if hasattr(frame, "ndim") and frame.ndim == 2 else np.asarray(frame, dtype=float)

        self._save_pair_result(self.idx, wave_axis, spec, x1, y1, x2, y2, cfg.get("save_dir", "."))
        self.pairFinishedSignal.emit(wave_axis, spec, float(x1), float(y1), float(x2), float(y2))

        self.states[self.idx] = NODE_DONE
        self.idx += 1
        self._pairs_done += 1
        self._emit_seq_state()

        refocus_every = max(1, int(cfg.get("refocus_every", 1)))
        if self._pairs_done % refocus_every == 0:
            self.sequenceProgressSignal.emit(self.idx, len(self.nodes), "Re-enfoque axial periódico...")
            run_z_autofocus(laser_color=laser)
        if self._check_seq_abort():
            return

        QTimer.singleShot(0, self._process_next_pair)

    def _save_pair_result(self, idx: int, wave_axis: np.ndarray, spec: np.ndarray,
                          x1: float, y1: float, x2: float, y2: float, save_dir: str):
        try:
            os.makedirs(save_dir, exist_ok=True)
            base = os.path.join(save_dir, f"DimerPair_{idx:03d}")
            np.savetxt(base + "_spectrum.txt", np.column_stack([wave_axis, spec]),
                      header="wavelength_nm\tintensity", fmt="%.4f")
            with open(base + "_coords.txt", "w", encoding="utf-8") as f:
                f.write(f"NP1_x_um\t{x1:.4f}\nNP1_y_um\t{y1:.4f}\nNP2_x_um\t{x2:.4f}\nNP2_y_um\t{y2:.4f}\n")
        except OSError as e:
            print(f"[DimersSequence] No se pudo guardar el par {idx}: {e}")

    def _finish_sequence(self):
        self._seq_running = False
        hardware_session.release_session(self.SESSION_NAME_SEQUENCE)
        self.sequenceFinishedSignal.emit()
