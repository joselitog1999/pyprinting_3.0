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

from config import SHUTTERS, PI_STAGE_RANGE_UM, PI_Z_RANGE_UM
from core.nidaq import open_shutter, close_shutter, heartbeat_shutter
from pyspectrum.drivers.shamrock_driver import DEVICE, get_shamrock
from pyspectrum.drivers.andor_ccd_driver import get_andor_ccd
from pyspectrum.modules.hardware_session import hardware_session
from pyspectrum.modules.routines.grid_runner import GridSafetyPause, NodeFailed
from pyspectrum.modules.routines.routine_thread import RoutineThread, mirror_choice, mirror_combo
from pyspectrum.modules.optical_support import (
    run_z_autofocus, run_confocal_centering, move_stage_to, get_stage_coordinates, read_photodiode_level,
    StageNotOnTarget,
)

NODE_PENDING = 0
NODE_CURRENT = 1
NODE_DONE = 2
NODE_FAILED = 3          # el par no se pudo completar (AND-1, R4-K P6): se registra y la secuencia sigue
_NODE_STATE_COLORS = {NODE_PENDING: "#45475A", NODE_CURRENT: "#F9E2AF", NODE_DONE: "#A6E3A1", NODE_FAILED: "#F38BA8"}

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

        from pyspectrum.ui.background_row import BackgroundRow
        self.bg_row_pol = BackgroundRow(default_frames=1)            # fondo de las polarizaciones (R4-N)
        ctrl_vlo.addWidget(self.bg_row_pol)

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
    def pol_exposure(self):
        try:
            return float(self.edit_exp.text())
        except ValueError:
            return None

    def update_dimer_data(self, mode: str, wave: np.ndarray, spec: np.ndarray, diff: np.ndarray):
        # ∥ − ⟂ no cambia con el fondo (se cancela); los dos espectros se muestran sin él (R4-N)
        if mode == "parallel":
            self.curve_par.setData(wave, self.bg_row_pol.for_display(spec))
        else:
            self.curve_perp.setData(wave, self.bg_row_pol.for_display(spec))

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
        self.spin_z0 = QtWidgets.QDoubleSpinBox(); self.spin_z0.setRange(0.0, PI_Z_RANGE_UM); self.spin_z0.setSuffix(" µm")

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

        # Sin espectro final del dímero (R4-K, P5): el legado no lo tomaba.
        params.addWidget(QtWidgets.QLabel("Espejo de detección ahora:"), 1, 0)
        self.cmb_seq_mirror = mirror_combo()
        params.addWidget(self.cmb_seq_mirror, 1, 1)

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
        self.edit_save_dir = QtWidgets.QLineEdit("")
        self.edit_save_dir.setPlaceholderText("carpeta de trabajo/dimers")
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

        self.lbl_last_pair = QtWidgets.QLabel("Último par: —")
        self.lbl_last_pair.setStyleSheet("color: #A6E3A1; font-size: 9pt;")
        plot_splitter.addWidget(self.lbl_last_pair)

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
            "dx_nm": self.spin_offset_dx_nm.value(),
            "dy_nm": self.spin_offset_dy_nm.value(),
            "trace_threshold_ratio": self.spin_trace_threshold.value(),
            "trace_max_s": self.spin_trace_max_s.value(),
            "refocus_every": self.spin_refocus_every.value(),
            "save_dir": self.edit_save_dir.text().strip(),
            "mirror": mirror_choice(self.cmb_seq_mirror),
        }
        if config["mirror"] is None:
            self.lbl_seq_progress.setText("Confirmá dónde está el espejo de detección antes de iniciar.")
            return
        self.cmb_seq_mirror.setCurrentIndex(0)
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

    @pyqtSlot(float, float, float, float)
    def update_pair_finished(self, x1: float, y1: float, x2: float, y2: float):
        self.lbl_last_pair.setText(f"Último par: NP1 ({x1:.3f}, {y1:.3f}) µm · NP2 ({x2:.3f}, {y2:.3f}) µm")

    @pyqtSlot()
    def on_sequence_finished(self):
        self.lbl_seq_progress.setText(self.lbl_seq_progress.text() + " — Finalizado.")


class DimersBackend(QtCore.QObject):
    """Dímeros plasmónicos: polarización manual y la secuencia automatizada NP1 → NP2, sobre las primitivas
    del bloque A (AND-1, parte 5; R4-K).

    En su propio hilo. Por par, como el legado (`Dimers_ps.py`) con las correcciones de R4-K:
    1. platina a NP1 con llegada confirmada;
    2. impresión de NP1 con potencia alta y el láser abierto, hasta el salto de la traza del fotodiodo;
    3. centrado de NP1 con potencia baja y el láser ABIERTO (antes se centraba con el láser cerrado);
    4. platina a NP1 + (Δx, Δy) e impresión de NP2;
    5. post-escaneo de validación, con potencia baja y el láser abierto;
    6. re-enfoque cada K pares, con potencia baja.
    Sin espectro final (P5). La potencia espera 2 s después de conmutar, como el legado. Los dímeros no
    mueven el espejo: se confirma al arrancar y queda donde está."""

    dimerDataSignal = pyqtSignal(str, np.ndarray, np.ndarray, np.ndarray)
    statusSignal = pyqtSignal(str)
    gridPreviewSignal = pyqtSignal(np.ndarray, np.ndarray)
    gridStateChangedSignal = pyqtSignal(np.ndarray, np.ndarray, np.ndarray, int)
    sequenceProgressSignal = pyqtSignal(int, int, str)
    pairFinishedSignal = pyqtSignal(float, float, float, float)
    sequenceFinishedSignal = pyqtSignal()
    originUpdatedSignal = pyqtSignal(float, float, float)

    SESSION_NAME_POLARIZATION = "Dímeros Plasmónicos"
    SESSION_NAME_SEQUENCE = "Fabricación de Dímeros"
    POWER_SETTLE_S = 2.0          # legado: 2 s después de conmutar el filtro de densidad (Dimers_ps.py)

    def __init__(self, camera=None, spectrometer=None, parent=None):
        super().__init__(parent)
        self.camera = camera or get_andor_ccd()
        self.spectrometer = spectrometer or get_shamrock()
        self.spec_par = None
        self.spec_perp = None
        self.wave_axis = np.linspace(450, 750, 1004)
        self._pending_nodes: List[Tuple[float, float, Optional[float]]] = []
        self.nodes: List[Tuple[float, float, Optional[float]]] = []
        self.states: List[int] = []
        self.idx = 0
        self.seq_config: dict = {}
        self._pairs_done = 0
        self._seq_running = False
        self._seq_paused = False
        self._seq_abort_requested = False
        base = os.getenv("PYSPECTRUM_ROUTINE_DATA_DIR") or os.path.join(os.path.expanduser("~"), "Documents", "Data_PySpectrum")
        self.data_dir = os.path.join(base, "dimers")
        self.pol_thread = RoutineThread(self.SESSION_NAME_POLARIZATION, self)
        self.seq_thread = RoutineThread(self.SESSION_NAME_SEQUENCE, self)
        # Fondo de las polarizaciones (R4-N). La secuencia NP1 → NP2 no toma espectros (AND-1).
        from pyspectrum.modules.routines.routine_dark import RoutineDark
        self.pol_dark = RoutineDark(self.camera, self.spectrometer, self.SESSION_NAME_POLARIZATION, "DimersPolarization",
                                    self)
        self.run_dark = None
        self.seq_thread.finished.connect(self._on_sequence_finished)
        hardware_session.emergencyStopSignal.connect(self.abort_sequence)

    def make_connection(self, widget):
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
        if hasattr(widget, "lbl_seq_progress"):
            self.statusSignal.connect(widget.lbl_seq_progress.setText)
        if hasattr(widget, "bg_row_pol"):
            from pyspectrum.modules.routines.routine_dark import wire_row
            wire_row(widget.bg_row_pol, self.pol_dark, widget.pol_exposure, getattr(widget, "lbl_info", None))

    def _hw(self):
        """Las acciones del hardware por los nombres de este módulo (los tests los interceptan acá)."""
        from types import SimpleNamespace
        from core import nidaq
        mod = __import__(__name__, fromlist=["open_shutter"])
        return SimpleNamespace(open_shutter=lambda n: mod.open_shutter(n), close_shutter=lambda n: mod.close_shutter(n),
                               close_all_shutters=nidaq.close_all_shutters, up_flipper=nidaq.up_flipper,
                               down_flipper=nidaq.down_flipper, flipper_notch532=nidaq.flipper_notch532)

    # ── polarización manual: una exposición real (AND-1) ──
    @pyqtSlot(str, float)
    def acquire_polarization(self, mode: str, exp_time: float):
        ret, axis = self.spectrometer.ShamrockGetCalibration(DEVICE, 1004)
        axis = np.asarray(axis, dtype=np.float64)
        if ret != 20202 or axis.size != 1004 or not np.all(np.isfinite(axis)):
            self.statusSignal.emit("⛔ No se pudo leer el eje λ del Shamrock.")
            return
        self.wave_axis = axis
        refusal = self.pol_dark.check_start(float(exp_time))
        if refusal:
            self.statusSignal.emit(f"⛔ {refusal}")
            return

        def body(runner, ctl):
            self.run_dark = self.pol_dark.ensure(runner, float(exp_time))   # fondo (R4-N)
            try:
                spec, _mode = runner.spectrum_1d(float(exp_time))
            except NodeFailed as e:
                self.statusSignal.emit(f"⛔ {e}")
                return "failed"
            diff = np.array([])
            if mode == "parallel":
                self.spec_par = spec
                if self.spec_perp is not None and len(self.spec_perp) == len(spec):
                    diff = self.spec_par - self.spec_perp
            else:
                self.spec_perp = spec
                if self.spec_par is not None and len(self.spec_par) == len(spec):
                    diff = self.spec_par - self.spec_perp
            self.dimerDataSignal.emit(mode, axis, spec, diff)
            return "done"

        err = self.pol_thread.start(body, camera=self.camera, spectrometer=self.spectrometer, mirror=None,
                                    require_mirror=False, runner_kwargs={"hw": self._hw()})
        if err:
            self.statusSignal.emit(f"⛔ {err}")

    # ── secuencia NP1 → NP2 ──
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

    def _center(self, runner, laser: str) -> Tuple[float, float]:
        """Centrado confocal con potencia baja y el láser abierto; una platina que no llega pausa."""
        runner.set_power("low")
        runner.laser(laser, True)
        try:
            return run_confocal_centering(range_um=1.0)
        except StageNotOnTarget as e:
            raise GridSafetyPause(str(e))
        finally:
            runner.laser(laser, False)

    def _print(self, runner, ctl, laser: str, threshold_ratio: float, max_s: float) -> bool:
        runner.set_power("high")
        runner.laser(laser, True)
        try:
            return self._monitor_print_trace(runner, threshold_ratio, max_s)
        finally:
            runner.laser(laser, False)

    def _monitor_print_trace(self, runner, threshold_ratio: float, max_s: float) -> bool:
        """Salto de la traza del fotodiodo (I_new > I_old × umbral), como `Dimers_ps.py::grid_trace_detect`.
        True si detectó el evento; False si se agotó el tiempo."""
        t0 = time.monotonic()
        i_old = None
        while True:
            runner.check()
            level = read_photodiode_level()
            if i_old is None:
                i_old = level if level > 0 else 1e-9
            elif level > i_old * threshold_ratio:
                return True
            if time.monotonic() - t0 >= max_s:
                return False
            runner.wait(0.05)

    @pyqtSlot(dict)
    def start_sequence(self, config: dict):
        if not self._pending_nodes:
            hardware_session.statusWarningSignal.emit("No hay grilla de posiciones NP1 generada/cargada.")
            return
        self.seq_config = dict(config)
        self.nodes = list(self._pending_nodes)
        self.states = [NODE_PENDING] * len(self.nodes)
        self.idx = 0
        self._pairs_done = 0
        save_dir = self.seq_config.get("save_dir") or self.data_dir
        if self.seq_config.get("mirror") == "down":
            self.statusSignal.emit("Aviso: el espejo está abajo; el centrado y la traza usan el fotodiodo confocal.")

        def body(runner, ctl):
            cfg = self.seq_config
            laser = cfg["laser"]
            ratio = float(cfg.get("trace_threshold_ratio", 1.2))
            trace_max_s = float(cfg.get("trace_max_s", 20.0))
            refocus_every = max(1, int(cfg.get("refocus_every", 1)))
            total = len(self.nodes)
            while self.idx < total:
                ctl.wait_while_paused(runner, lambda: self.sequenceProgressSignal.emit(self.idx, total, "En pausa."))
                if ctl.take_skip():
                    self.states[self.idx] = NODE_DONE
                    self.idx += 1
                    self._emit_seq_state()
                    continue
                self.states[self.idx] = NODE_CURRENT
                self._emit_seq_state()
                x, y, z = self.nodes[self.idx]
                try:
                    self.sequenceProgressSignal.emit(self.idx, total, "Moviendo a NP1...")
                    runner.move_to(x, y, z)
                    self.sequenceProgressSignal.emit(self.idx, total, "Imprimiendo NP1 (esperando salto de traza)...")
                    self._print(runner, ctl, laser, ratio, trace_max_s)
                    self.sequenceProgressSignal.emit(self.idx, total, "Centrando NP1 (confocal sub-píxel)...")
                    x1, y1 = self._center(runner, laser)
                    dx_um = float(cfg.get("dx_nm", 100.0)) / 1000.0
                    dy_um = float(cfg.get("dy_nm", 0.0)) / 1000.0
                    self.sequenceProgressSignal.emit(self.idx, total, "Desplazando offset nanométrico a NP2...")
                    runner.move_to(x1 + dx_um, y1 + dy_um, None)
                    self.sequenceProgressSignal.emit(self.idx, total, "Imprimiendo NP2 (esperando salto de traza)...")
                    self._print(runner, ctl, laser, ratio, trace_max_s)
                    self.sequenceProgressSignal.emit(self.idx, total, "Post-escaneo de validación morfológica...")
                    x2, y2 = self._center(runner, laser)
                    self._save_pair_result(self.idx, x1, y1, x2, y2, save_dir)
                    self.pairFinishedSignal.emit(float(x1), float(y1), float(x2), float(y2))
                    self.states[self.idx] = NODE_DONE
                except NodeFailed as e:
                    self.states[self.idx] = NODE_FAILED
                    self.sequenceProgressSignal.emit(self.idx, total, f"Par fallido: {e}")
                except GridSafetyPause as e:
                    self.states[self.idx] = NODE_PENDING
                    self._emit_seq_state()
                    self.statusSignal.emit(f"⛔ {e} Reanudá cuando esté resuelto.")
                    ctl.pause.set()
                    continue
                self.idx += 1
                self._pairs_done += 1
                self._emit_seq_state()
                if self._pairs_done % refocus_every == 0:
                    self.sequenceProgressSignal.emit(self.idx, total, "Re-enfoque axial periódico...")
                    runner.set_power("low")
                    run_z_autofocus(laser_color=laser)
            return "done"

        err = self.seq_thread.start(body, camera=self.camera, spectrometer=self.spectrometer,
                                    mirror=self.seq_config.get("mirror"), needs_spectrometer=False,
                                    restore_mirror=False,
                                    runner_kwargs={"hw": self._hw(), "power_settle_s": self.POWER_SETTLE_S})
        if err:
            self.statusSignal.emit(f"⛔ {err}")
            hardware_session.statusWarningSignal.emit(err)
            return
        self._seq_running = True
        self._seq_paused = False
        self._seq_abort_requested = False
        self._emit_seq_state()

    @pyqtSlot()
    def pause_sequence(self):
        self._seq_paused = True
        self.seq_thread.pause()

    @pyqtSlot()
    def resume_sequence(self):
        self._seq_paused = False
        self.seq_thread.resume()

    @pyqtSlot()
    def next_pair_sequence(self):
        if self._seq_running:
            self.seq_thread.skip()

    @pyqtSlot()
    def abort_sequence(self):
        if not self._seq_running:
            return
        self._seq_abort_requested = True
        self.seq_thread.stop()

    @pyqtSlot(str)
    def _on_sequence_finished(self, outcome: str):
        self._seq_running = False
        if outcome.startswith(("safety", "error")):
            self.statusSignal.emit("⛔ " + outcome.split(": ", 1)[-1])
        self.sequenceFinishedSignal.emit()

    def _emit_seq_state(self):
        xs = np.array([n[0] for n in self.nodes])
        ys = np.array([n[1] for n in self.nodes])
        self.gridStateChangedSignal.emit(xs, ys, np.array(self.states), self.idx)

    def _save_pair_result(self, idx: int, x1: float, y1: float, x2: float, y2: float, save_dir: str):
        try:
            os.makedirs(save_dir, exist_ok=True)
            base = os.path.join(save_dir, f"DimerPair_{idx:03d}")
            with open(base + "_coords.txt", "w", encoding="utf-8") as f:
                f.write(f"NP1_x_um\t{x1:.4f}\nNP1_y_um\t{y1:.4f}\nNP2_x_um\t{x2:.4f}\nNP2_y_um\t{y2:.4f}\n")
        except OSError as e:
            print(f"[DimersSequence] No se pudo guardar el par {idx}: {e}")

    def shutdown(self, timeout_ms: int = 3000):
        return [self.seq_thread.shutdown(timeout_ms), self.pol_thread.shutdown(timeout_ms)]
