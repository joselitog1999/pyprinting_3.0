# -*- coding: utf-8 -*-
"""
growth_kinetics.py — Monitoreo de Cinética de Crecimiento y Síntesis de Nanopartículas
PySpectrum 3.0 — UNSAM Nanofotónica

Fase 6 (DEC-020): además del monitoreo puntual histórico (un único punto, SPR vs tiempo),
incorpora la reconstrucción moderna de la Pestaña 4 legada (Growth_ps.py/CIBION): una máquina
de estados por nodo sobre una grilla de coordenadas (generada o cargada desde .txt), con
autofoco/centrado confocal periódicos vía pyspectrum.modules.optical_support, y criterios
duales de parada por nodo (desplazamiento plasmónico λ_max, caída de fotodiodo, tiempo máximo).
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
from pyspectrum.calibration.fit_polynomial import fit_signal_polynomial
from pyspectrum.modules.routines.grid_runner import GridSafetyPause, NodeFailed
from pyspectrum.modules.routines.routine_thread import RoutineThread, mirror_choice, mirror_combo
from pyspectrum.modules.optical_support import (
    run_z_autofocus, run_confocal_centering, move_stage_to, get_stage_coordinates, read_photodiode_level,
    StageNotOnTarget,
)


_GROWTH_KINETICS_CONTROLS_STYLE = """
    QLabel { color: #CDD6F4; font-weight: bold; }
    QPushButton { background-color: #313244; color: #CDD6F4; border: 1px solid #45475A; border-radius: 4px; padding: 6px 12px; font-weight: bold; }
    QPushButton:hover { background-color: #45475A; color: #FAB387; }
    QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox { background-color: #1E1E2E; color: #CDD6F4; border: 1px solid #45475A; border-radius: 4px; padding: 4px; }
    QTabWidget::pane { border: 1px solid #313244; }
    QTabBar::tab { background: #181825; color: #A6ADC8; padding: 6px 12px; }
    QTabBar::tab:selected { background: #313244; color: #FAB387; font-weight: bold; }
"""

# Estados de nodo para el visualizador de grilla
NODE_PENDING = 0
NODE_CURRENT = 1
NODE_DONE = 2
NODE_FAILED = 3          # la exposición del nodo falló (AND-1, R4-K P6): se registra y la grilla sigue
_NODE_STATE_COLORS = {NODE_PENDING: "#45475A", NODE_CURRENT: "#F9E2AF", NODE_DONE: "#A6E3A1", NODE_FAILED: "#F38BA8"}


class GrowthKineticsPanel(QtWidgets.QWidget):
    """Panel de Cinética de Crecimiento embebible (Pestaña 4 del shell principal de
    PySpectrum 3.0). Contiene toda la UI y lógica de presentación; GrowthKineticsWidget lo
    envuelve en un QDialog standalone para uso independiente/retrocompatibilidad.

    Expone dos sub-pestañas: "Monitoreo Puntual" (histórico, un único punto fijo) y
    "Grilla Automatizada" (Fase 6, máquina de estados multi-nodo sobre una grilla)."""

    # ── Señales del modo puntual histórico (sin cambios, Fase 1-5) ──────────────
    startGrowthSignal = pyqtSignal(str, float, int, float)
    mirrorConfirmedSignal = pyqtSignal(str)  # el operador confirma dónde está el espejo antes de iniciar (R4-K)
    stopGrowthSignal = pyqtSignal()

    # ── Señales del modo grilla automatizada (Fase 6) ────────────────────────────
    generateGridSignal = pyqtSignal(int, int, float, float, float, float, float)  # rows, cols, dx, dy, x0, y0, z0
    loadGridFileSignal = pyqtSignal(str)
    useCurrentPosSignal = pyqtSignal()
    startGridSignal = pyqtSignal(dict)
    pauseGridSignal = pyqtSignal()
    resumeGridSignal = pyqtSignal()
    nextNodeGridSignal = pyqtSignal()
    abortGridSignal = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("GrowthKineticsPanel")
        self.setStyleSheet("QWidget#GrowthKineticsPanel { background-color: #11111B; } " + _GROWTH_KINETICS_CONTROLS_STYLE)
        self._setup_ui()

    def _setup_ui(self):
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.tabs = QtWidgets.QTabWidget()
        outer.addWidget(self.tabs)
        self.tabs.addTab(self._build_single_point_tab(), "📈 Monitoreo Puntual")
        self.tabs.addTab(self._build_grid_tab(), "🗺️ Grilla Automatizada")

    # ── Pestaña 1: Monitoreo Puntual (histórico, Fase 1-5, sin cambios) ─────────
    def _build_single_point_tab(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

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

        from pyspectrum.ui.background_row import BackgroundRow
        self.bg_row_point = BackgroundRow(default_frames=1)          # fondo de la serie (R4-N)
        ctrl_vlo.addWidget(self.bg_row_point)

        self.btn_run = QtWidgets.QPushButton("▶️ Iniciar Monitoreo de Crecimiento")
        self.btn_run.setStyleSheet("background-color: #FAB387; color: #11111B; font-weight: bold;")
        self.btn_run.setCheckable(True)
        self.btn_run.clicked.connect(self._on_toggle_run)
        ctrl_vlo.addWidget(self.btn_run)

        self.cmb_mirror = mirror_combo()
        ctrl_vlo.addWidget(QtWidgets.QLabel("Espejo de detección ahora:"))
        ctrl_vlo.addWidget(self.cmb_mirror)

        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setStyleSheet("QProgressBar { border: 1px solid #45475A; border-radius: 4px; text-align: center; color: #CDD6F4; } QProgressBar::chunk { background-color: #FAB387; }")
        self.progress_bar.setValue(0)
        ctrl_vlo.addWidget(self.progress_bar)

        self.lbl_peak = QtWidgets.QLabel("λ_max actual: <b>-- nm</b>")
        self.lbl_peak.setStyleSheet("color: #FAB387; font-size: 9.5pt;")
        ctrl_vlo.addWidget(self.lbl_peak)

        ctrl_vlo.addStretch()
        layout.addLayout(ctrl_vlo, stretch=1)

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
        return page

    def _on_toggle_run(self, checked: bool):
        if checked:
            try:
                laser = self.cmb_laser.currentText()
                exp = float(self.edit_exp.text())
                n_frames = int(self.edit_nframes.text())
                interval = float(self.edit_interval.text())
                mirror = mirror_choice(self.cmb_mirror)
                if mirror is None:
                    self.btn_run.setChecked(False)
                    self.lbl_peak.setText("Confirmá dónde está el espejo de detección antes de iniciar.")
                    return
                self.mirrorConfirmedSignal.emit(mirror)
                self.cmb_mirror.setCurrentIndex(0)

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
        self.curve_spec.setData(wave, self.bg_row_point.for_display(spec))
        if len(wave_fit) > 0:
            self.curve_fit.setData(wave_fit, spec_fit)
        self.curve_spr.setData(t_axis, lmax_axis)
        self.progress_bar.setValue(progress)
        self.lbl_peak.setText(f"λ_max actual: <b>{current_lmax:.2f} nm</b>")

        if progress >= 100:
            self.btn_run.setChecked(False)
            self.btn_run.setText("▶️ Iniciar Monitoreo de Crecimiento")
            self.btn_run.setStyleSheet("background-color: #FAB387; color: #11111B;")

    # ── Pestaña 2: Grilla Automatizada (Fase 6) ─────────────────────────────────
    def _build_grid_tab(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        ctrl_vlo = QtWidgets.QVBoxLayout()
        ctrl_vlo.setSpacing(6)

        lbl_title = QtWidgets.QLabel("🗺️ <b>Grilla de Crecimiento Automatizado</b>")
        lbl_title.setStyleSheet("font-size: 10.5pt; color: #FAB387;")
        ctrl_vlo.addWidget(lbl_title)

        # Generación / carga de grilla
        grid_gen = QtWidgets.QGridLayout()
        self.spin_rows = QtWidgets.QSpinBox(); self.spin_rows.setRange(1, 500); self.spin_rows.setValue(4)
        self.spin_cols = QtWidgets.QSpinBox(); self.spin_cols.setRange(1, 500); self.spin_cols.setValue(4)
        self.spin_dx = QtWidgets.QDoubleSpinBox(); self.spin_dx.setRange(0.01, 1000.0); self.spin_dx.setValue(3.0); self.spin_dx.setSuffix(" µm")
        self.spin_dy = QtWidgets.QDoubleSpinBox(); self.spin_dy.setRange(0.01, 1000.0); self.spin_dy.setValue(3.0); self.spin_dy.setSuffix(" µm")
        self.spin_x0 = QtWidgets.QDoubleSpinBox(); self.spin_x0.setRange(0.0, PI_STAGE_RANGE_UM); self.spin_x0.setSuffix(" µm")
        self.spin_y0 = QtWidgets.QDoubleSpinBox(); self.spin_y0.setRange(0.0, PI_STAGE_RANGE_UM); self.spin_y0.setSuffix(" µm")
        self.spin_z0 = QtWidgets.QDoubleSpinBox(); self.spin_z0.setRange(0.0, PI_Z_RANGE_UM); self.spin_z0.setSuffix(" µm")

        grid_gen.addWidget(QtWidgets.QLabel("Filas (N):"), 0, 0); grid_gen.addWidget(self.spin_rows, 0, 1)
        grid_gen.addWidget(QtWidgets.QLabel("Columnas (M):"), 1, 0); grid_gen.addWidget(self.spin_cols, 1, 1)
        grid_gen.addWidget(QtWidgets.QLabel("Δx:"), 2, 0); grid_gen.addWidget(self.spin_dx, 2, 1)
        grid_gen.addWidget(QtWidgets.QLabel("Δy:"), 3, 0); grid_gen.addWidget(self.spin_dy, 3, 1)
        grid_gen.addWidget(QtWidgets.QLabel("Origen X0/Y0/Z0:"), 4, 0)
        origin_row = QtWidgets.QHBoxLayout()
        origin_row.addWidget(self.spin_x0); origin_row.addWidget(self.spin_y0); origin_row.addWidget(self.spin_z0)
        origin_widget = QtWidgets.QWidget(); origin_widget.setLayout(origin_row)
        grid_gen.addWidget(origin_widget, 4, 1)
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

        # Parámetros de irradiación y foco
        grid_params = QtWidgets.QGridLayout()
        grid_params.addWidget(QtWidgets.QLabel("Láser de Crecimiento:"), 0, 0)
        self.cmb_grid_laser = QtWidgets.QComboBox(); self.cmb_grid_laser.addItems(SHUTTERS)
        grid_params.addWidget(self.cmb_grid_laser, 0, 1)

        grid_params.addWidget(QtWidgets.QLabel("Tiempo Exp (s):"), 1, 0)
        self.spin_grid_exp = QtWidgets.QDoubleSpinBox(); self.spin_grid_exp.setRange(0.001, 60.0); self.spin_grid_exp.setValue(0.05); self.spin_grid_exp.setDecimals(3)
        grid_params.addWidget(self.spin_grid_exp, 1, 1)

        grid_params.addWidget(QtWidgets.QLabel("Autofoco cada N nodos:"), 2, 0)
        self.spin_autofocus_every = QtWidgets.QSpinBox(); self.spin_autofocus_every.setRange(1, 1000); self.spin_autofocus_every.setValue(1)
        grid_params.addWidget(self.spin_autofocus_every, 2, 1)

        self.chk_center_seed = QtWidgets.QCheckBox("Centrar Semilla (confocal)")
        grid_params.addWidget(self.chk_center_seed, 3, 0, 1, 2)
        ctrl_vlo.addLayout(grid_params)

        from pyspectrum.ui.background_row import BackgroundRow
        self.bg_row_grid = BackgroundRow(default_frames=1)           # un fondo por grilla (R4-N)
        ctrl_vlo.addWidget(self.bg_row_grid)

        # Criterios duales de parada
        lbl_stop = QtWidgets.QLabel("Criterios de Parada por Nodo:")
        lbl_stop.setStyleSheet("color: #A6ADC8; font-size: 8.5pt;")
        ctrl_vlo.addWidget(lbl_stop)

        stop_grid = QtWidgets.QGridLayout()
        self.chk_stop_lambda = QtWidgets.QCheckBox("A) λ_max ≥")
        self.spin_lambda_target = QtWidgets.QDoubleSpinBox(); self.spin_lambda_target.setRange(400.0, 900.0); self.spin_lambda_target.setValue(600.0); self.spin_lambda_target.setSuffix(" nm")
        stop_grid.addWidget(self.chk_stop_lambda, 0, 0); stop_grid.addWidget(self.spin_lambda_target, 0, 1)

        self.chk_stop_photodiode = QtWidgets.QCheckBox("B) Caída fotodiodo ≥")
        self.spin_photodiode_drop = QtWidgets.QDoubleSpinBox(); self.spin_photodiode_drop.setRange(1.0, 99.0); self.spin_photodiode_drop.setValue(20.0); self.spin_photodiode_drop.setSuffix(" %")
        stop_grid.addWidget(self.chk_stop_photodiode, 1, 0); stop_grid.addWidget(self.spin_photodiode_drop, 1, 1)

        stop_grid.addWidget(QtWidgets.QLabel("C) Tiempo máx (siempre activo):"), 2, 0)
        self.spin_tmax = QtWidgets.QDoubleSpinBox(); self.spin_tmax.setRange(1.0, 3600.0); self.spin_tmax.setValue(60.0); self.spin_tmax.setSuffix(" s")
        stop_grid.addWidget(self.spin_tmax, 2, 1)
        ctrl_vlo.addLayout(stop_grid)

        # Directorio de guardado
        save_row = QtWidgets.QHBoxLayout()
        self.edit_save_dir = QtWidgets.QLineEdit("")
        self.edit_save_dir.setPlaceholderText("carpeta de trabajo/growth")
        self.btn_pick_save_dir = QtWidgets.QPushButton("📁")
        self.btn_pick_save_dir.clicked.connect(self._on_pick_save_dir)
        save_row.addWidget(self.edit_save_dir)
        save_row.addWidget(self.btn_pick_save_dir)
        ctrl_vlo.addLayout(save_row)

        self.cmb_grid_mirror = mirror_combo()
        ctrl_vlo.addWidget(QtWidgets.QLabel("Espejo de detección ahora:"))
        ctrl_vlo.addWidget(self.cmb_grid_mirror)

        # Controles de ejecución
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

        self.lbl_grid_peak = QtWidgets.QLabel("λ_max nodo actual: <b>-- nm</b> | t: <b>-- s</b>")
        self.lbl_grid_peak.setStyleSheet("color: #FAB387; font-size: 9.5pt;")
        ctrl_vlo.addWidget(self.lbl_grid_peak)

        ctrl_vlo.addStretch()
        layout.addLayout(ctrl_vlo, stretch=1)

        # Visualizador 2D de grilla + espectro en vivo del nodo actual
        plot_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)

        self.plot_grid_map = pg.PlotWidget(title="<b>Mapa de Grilla (pendiente=gris, actual=amarillo, completado=verde)</b>")
        self.plot_grid_map.setLabels(bottom="X (µm)", left="Y (µm)")
        self.scatter_grid = pg.ScatterPlotItem(size=14, pen=pg.mkPen(None))
        self.plot_grid_map.addItem(self.scatter_grid)
        plot_splitter.addWidget(self.plot_grid_map)

        self.plot_grid_spec = pg.PlotWidget(title="<b>Espectro del Nodo Actual</b>")
        self.plot_grid_spec.setLabels(bottom="Longitud de Onda (nm)", left="Intensidad")
        self.curve_grid_spec = self.plot_grid_spec.plot(pen=pg.mkPen("#FAB387", width=2.0))
        plot_splitter.addWidget(self.plot_grid_spec)

        layout.addWidget(plot_splitter, stretch=3)
        self._grid_xs: np.ndarray = np.array([])
        self._grid_ys: np.ndarray = np.array([])
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
            "center_seed": self.chk_center_seed.isChecked(),
            "use_lambda_stop": self.chk_stop_lambda.isChecked(),
            "lambda_target_nm": self.spin_lambda_target.value(),
            "use_photodiode_stop": self.chk_stop_photodiode.isChecked(),
            "photodiode_drop_pct": self.spin_photodiode_drop.value(),
            "t_max_s": self.spin_tmax.value(),
            "interval_s": 0.2,
            "save_dir": self.edit_save_dir.text().strip(),
            "mirror": mirror_choice(self.cmb_grid_mirror),
        }
        if config["mirror"] is None:
            self.lbl_grid_progress.setText("Confirmá dónde está el espejo de detección antes de iniciar la grilla.")
            return
        self.cmb_grid_mirror.setCurrentIndex(0)
        self.startGridSignal.emit(config)

    @pyqtSlot(np.ndarray, np.ndarray)
    def preview_grid(self, xs: np.ndarray, ys: np.ndarray):
        self._grid_xs, self._grid_ys = xs, ys
        n = len(xs)
        self.scatter_grid.setData(xs, ys, brush=[pg.mkBrush(_NODE_STATE_COLORS[NODE_PENDING])] * n)
        self.lbl_grid_progress.setText(f"Nodo: -- / {n} | Estado: Grilla lista para iniciar.")

    @pyqtSlot(np.ndarray, np.ndarray, np.ndarray, int)
    def update_grid_state(self, xs: np.ndarray, ys: np.ndarray, states: np.ndarray, current_idx: int):
        self._grid_xs, self._grid_ys = xs, ys
        brushes = [pg.mkBrush(_NODE_STATE_COLORS.get(int(s), "#45475A")) for s in states]
        self.scatter_grid.setData(xs, ys, brush=brushes)

    @pyqtSlot(int, int, str)
    def update_grid_progress(self, idx: int, total: int, phase_label: str):
        self.lbl_grid_progress.setText(f"Nodo: {idx + 1} / {total} | Estado: {phase_label}")

    @pyqtSlot(np.ndarray, np.ndarray, float, float)
    def point_exposure(self):
        try:
            return float(self.edit_exp.text())
        except ValueError:
            return None

    def update_grid_spectrum(self, wave: np.ndarray, spec: np.ndarray, lmax: float, elapsed_s: float):
        self.curve_grid_spec.setData(wave, self.bg_row_grid.for_display(spec))
        self.lbl_grid_peak.setText(f"λ_max nodo actual: <b>{lmax:.2f} nm</b> | t: <b>{elapsed_s:.1f} s</b>")

    @pyqtSlot()
    def on_grid_finished(self):
        self.lbl_grid_progress.setText(self.lbl_grid_progress.text() + " — Finalizado.")


class GrowthKineticsWidget(QtWidgets.QDialog):
    """Ventana standalone para el seguimiento in-situ del crecimiento plasmónico de
    nanopartículas (compatibilidad hacia atrás: uso independiente fuera del shell principal).
    Envuelve un GrowthKineticsPanel embebido y expone sus controles/señales como atributos
    directos, de modo que GrowthKineticsBackend.make_connection() funcione igual sin importar
    si se le pasa esta ventana standalone o el panel embebido en la Pestaña 4 del shell."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cinética de Crecimiento de Nanopartículas — PySpectrum 3.0")
        self.resize(980, 600)
        self.setStyleSheet("QDialog { background-color: #11111B; } " + _GROWTH_KINETICS_CONTROLS_STYLE)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.panel = GrowthKineticsPanel(self)
        lay.addWidget(self.panel)

        for attr_name in ("cmb_laser", "edit_exp", "edit_nframes", "edit_interval", "cmb_mirror", "cmb_grid_mirror",
                          "btn_run", "progress_bar", "lbl_peak", "plot_spec", "curve_spec",
                          "curve_fit", "plot_spr_time", "curve_spr",
                          "btn_generate_grid", "btn_load_grid", "btn_use_current_pos",
                          "btn_grid_start", "btn_grid_pause", "btn_grid_resume", "btn_grid_next", "btn_grid_abort",
                          "lbl_grid_progress", "lbl_grid_peak", "plot_grid_map", "scatter_grid",
                          "plot_grid_spec", "curve_grid_spec"):
            setattr(self, attr_name, getattr(self.panel, attr_name))

        for sig_name in ("startGrowthSignal", "stopGrowthSignal", "mirrorConfirmedSignal", "generateGridSignal", "loadGridFileSignal",
                         "useCurrentPosSignal", "startGridSignal", "pauseGridSignal", "resumeGridSignal",
                         "nextNodeGridSignal", "abortGridSignal"):
            setattr(self, sig_name, getattr(self.panel, sig_name))

        self.update_growth_data = self.panel.update_growth_data
        self.preview_grid = self.panel.preview_grid
        self.update_grid_state = self.panel.update_grid_state
        self.update_grid_progress = self.panel.update_grid_progress
        self.update_grid_spectrum = self.panel.update_grid_spectrum
        self.on_grid_finished = self.panel.on_grid_finished
        self.set_origin_fields = self.panel.set_origin_fields


class GrowthKineticsBackend(QtCore.QObject):
    """Cinética de crecimiento puntual y en grilla sobre las primitivas del bloque A (AND-1, parte 4; R4-K).

    En su propio hilo. Por nodo, como el legado (`Growth_ps.py`) con las correcciones de R4-K:
    1. platina con llegada confirmada;
    2. autofoco con potencia baja y el espejo arriba (fotodiodo confocal);
    3. centrado de la semilla con potencia baja, el espejo arriba y el láser ABIERTO (antes se centraba con
       el láser cerrado);
    4. crecimiento con potencia alta, el espejo abajo y el láser abierto: una serie de exposiciones reales
       (P4) con los criterios de parada A (λ_max), B (fotodiodo) y C (tiempo máximo).
    La pausa cierra el láser y seguir lo reabre (P7). Un nodo con una exposición fallida queda FALLIDO y la
    grilla sigue (P6); una platina que no llega pausa con los obturadores cerrados (DEC-036)."""

    growthUpdatedSignal = pyqtSignal(np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, float, int)
    statusSignal = pyqtSignal(str)
    gridPreviewSignal = pyqtSignal(np.ndarray, np.ndarray)
    gridStateChangedSignal = pyqtSignal(np.ndarray, np.ndarray, np.ndarray, int)
    gridNodeProgressSignal = pyqtSignal(int, int, str)
    gridSpectralUpdateSignal = pyqtSignal(np.ndarray, np.ndarray, float, float)
    gridFinishedSignal = pyqtSignal()
    originUpdatedSignal = pyqtSignal(float, float, float)

    SESSION_NAME_POINT = "Cinética de Crecimiento"
    SESSION_NAME_GRID = "Cinética de Crecimiento en Grilla"

    def __init__(self, camera=None, spectrometer=None, parent=None):
        super().__init__(parent)
        self.camera = camera or get_andor_ccd()
        self.spectrometer = spectrometer or get_shamrock()
        self.t_points: List[float] = []
        self.lmax_points: List[float] = []
        self.curr_frame = 0
        self.total_frames = 200
        self.laser_in_use = ""
        self.timer = QTimer(self)                  # compatibilidad: ya no maneja la adquisición
        self._mirror_confirmed: Optional[str] = None

        self._pending_nodes: List[Tuple[float, float, Optional[float]]] = []
        self.nodes: List[Tuple[float, float, Optional[float]]] = []
        self.states: List[int] = []
        self.idx = 0
        self.grid_config: dict = {}
        self._grid_running = False
        self._grid_paused = False
        self._grid_abort_requested = False
        self._node_t_points: List[float] = []
        self._node_lmax_points: List[float] = []
        self._node_last_spec: np.ndarray = np.array([])
        self._node_last_wave: np.ndarray = np.array([])
        base = os.getenv("PYSPECTRUM_ROUTINE_DATA_DIR") or os.path.join(os.path.expanduser("~"), "Documents", "Data_PySpectrum")
        self.data_dir = os.path.join(base, "growth")

        self.point_thread = RoutineThread(self.SESSION_NAME_POINT, self)
        self.grid_thread = RoutineThread(self.SESSION_NAME_GRID, self)
        # Fondo de los procedimientos (R4-N): uno para la serie puntual y otro para la grilla
        from pyspectrum.modules.routines.routine_dark import RoutineDark
        self.point_dark = RoutineDark(self.camera, self.spectrometer, self.SESSION_NAME_POINT, "GrowthPoint", self)
        self.grid_dark = RoutineDark(self.camera, self.spectrometer, self.SESSION_NAME_GRID, "GrowthGrid", self)
        self.run_dark = None
        self.point_thread.finished.connect(self._on_point_finished)
        self.grid_thread.finished.connect(self._on_grid_finished)
        hardware_session.emergencyStopSignal.connect(self.stop_growth)
        hardware_session.emergencyStopSignal.connect(self.abort_grid)

    def make_connection(self, widget):
        widget.startGrowthSignal.connect(self.start_growth)
        widget.stopGrowthSignal.connect(self.stop_growth)
        widget.mirrorConfirmedSignal.connect(self.confirm_mirror)
        self.growthUpdatedSignal.connect(widget.update_growth_data)
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
        self.gridSpectralUpdateSignal.connect(widget.update_grid_spectrum)
        self.gridFinishedSignal.connect(widget.on_grid_finished)
        self.originUpdatedSignal.connect(widget.set_origin_fields)
        if hasattr(widget, "lbl_grid_progress"):
            self.statusSignal.connect(widget.lbl_grid_progress.setText)
        if hasattr(widget, "bg_row_point"):
            from pyspectrum.modules.routines.routine_dark import wire_row
            wire_row(widget.bg_row_point, self.point_dark, widget.point_exposure, getattr(widget, "lbl_peak", None))
            wire_row(widget.bg_row_grid, self.grid_dark, widget.spin_grid_exp.value,
                     getattr(widget, "lbl_grid_progress", None))

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
                               down_flipper=nidaq.down_flipper, flipper_notch532=nidaq.flipper_notch532)

    def _wave_axis(self):
        ret, axis = self.spectrometer.ShamrockGetCalibration(DEVICE, 1004)
        axis = np.asarray(axis, dtype=np.float64)
        if ret != 20202 or axis.size != 1004 or not np.all(np.isfinite(axis)):
            print(f"[{type(self).__name__}] Eje λ no confiable: código {ret}, {axis.size} puntos")
            return None
        return axis

    @staticmethod
    def _fit(wave, spec):
        return fit_signal_polynomial(wave, spec, ends_notch=wave[0] + 10, final_wave=wave[-1] - 10)

    # ── modo puntual ──
    @pyqtSlot(str, float, int, float)
    def start_growth(self, laser: str, exp_time: float, n_frames: int, interval: float):
        wave = self._wave_axis()
        if wave is None:
            self.statusSignal.emit("⛔ No se pudo leer el eje λ del Shamrock: la medición no arranca.")
            return
        refusal = self.point_dark.check_start(float(exp_time))
        if refusal:
            self.statusSignal.emit(f"⛔ {refusal}")
            return
        self.wave_axis = wave
        self.laser_in_use = laser
        self.total_frames = int(n_frames)
        self.curr_frame = 0
        self.t_points, self.lmax_points = [], []

        def body(runner, ctl):
            from pyspectrum.modules.routines.routine_dark import corrected
            dark = self.point_dark.ensure(runner, float(exp_time))   # fondo de la serie (R4-N)
            self.run_dark = dark
            runner.set_mirror("down")
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
                wave_fit, spec_fit, lmax = self._fit(wave, corrected(spec, dark))   # λmax sin el fondo (B3)
                self.t_points.append(time.monotonic() - t0)
                self.lmax_points.append(float(lmax))
                self.curr_frame = k + 1
                pct = int(100.0 * self.curr_frame / max(1, self.total_frames))
                self.growthUpdatedSignal.emit(wave, spec, wave_fit, spec_fit, np.array(self.t_points),
                                              np.array(self.lmax_points), float(lmax), pct)
                runner.wait(max(0.0, float(interval) - (time.monotonic() - t_frame)))
            return "done"

        err = self.point_thread.start(body, camera=self.camera, spectrometer=self.spectrometer,
                                      mirror=self._mirror_confirmed, runner_kwargs={"hw": self._hw()})
        self._mirror_confirmed = None
        if err:
            self.statusSignal.emit(f"⛔ {err}")

    @pyqtSlot()
    def stop_growth(self):
        self.point_thread.stop()

    @pyqtSlot(str)
    def _on_point_finished(self, outcome: str):
        self.laser_in_use = ""
        if outcome.startswith(("safety", "error")):
            self.statusSignal.emit("⛔ " + outcome.split(": ", 1)[-1])

    # ── grilla ──
    @pyqtSlot()
    def use_current_position_as_origin(self):
        x, y, z = get_stage_coordinates()
        self.originUpdatedSignal.emit(x, y, z)

    @pyqtSlot(int, int, float, float, float, float, float)
    def generate_grid(self, rows: int, cols: int, dx_um: float, dy_um: float, x0: float, y0: float, z0: float):
        """Grilla rectangular N×M de nodos absolutos (µm), como `Growth_ps.py::grid_create`."""
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
        refusal = self.grid_dark.check_start(float(config["exp_time"]))
        if refusal:
            self.statusSignal.emit(f"⛔ {refusal}")
            hardware_session.statusWarningSignal.emit(refusal)
            return
        self.grid_config = dict(config)
        self.nodes = list(self._pending_nodes)
        self.states = [NODE_PENDING] * len(self.nodes)
        self.idx = 0
        save_dir = self.grid_config.get("save_dir") or self.data_dir

        def body(runner, ctl):
            cfg = self.grid_config
            laser = cfg["laser"]
            every = max(1, int(cfg.get("autofocus_every", 1)))
            total = len(self.nodes)
            self.run_dark = self.grid_dark.ensure(runner, float(cfg["exp_time"]))   # un fondo por grilla (R4-N)
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
                        runner.set_power("low")
                        runner.set_mirror("up")
                        run_z_autofocus(laser_color=laser)
                    if cfg.get("center_seed", False):
                        self.gridNodeProgressSignal.emit(self.idx, total, "Centrado confocal de semilla...")
                        runner.set_power("low")
                        runner.set_mirror("up")
                        runner.laser(laser, True)              # el centrado ve la semilla con el láser
                        try:
                            run_confocal_centering(range_um=1.0)
                        except StageNotOnTarget as e:
                            raise GridSafetyPause(str(e))
                        finally:
                            runner.laser(laser, False)
                    self.gridNodeProgressSignal.emit(self.idx, total, "Irradiando y trackeando SPR...")
                    runner.set_power("high")
                    runner.set_mirror("down")                  # el espectro se mide con el espejo abajo (R4-K)
                    runner.laser(laser, True)
                    try:
                        self._track_node_spectrum(runner, ctl, wave, cfg)
                    finally:
                        runner.laser(laser, False)
                    self._save_node_result(self.idx, wave, self._node_last_spec, self._node_t_points,
                                           self._node_lmax_points, save_dir)
                    self.states[self.idx] = NODE_DONE
                except NodeFailed as e:
                    self.states[self.idx] = NODE_FAILED
                    self._save_node_failure(self.idx, save_dir, str(e))
                    self.gridNodeProgressSignal.emit(self.idx, total, f"Nodo fallido: {e}")
                except GridSafetyPause as e:
                    self.states[self.idx] = NODE_PENDING
                    self._emit_grid_state()
                    self.statusSignal.emit(f"⛔ {e} Reanudá cuando esté resuelto.")
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

    def _track_node_spectrum(self, runner, ctl, wave_axis: np.ndarray, cfg: dict):
        """Serie de exposiciones reales (P4) con ajuste de λ_max y los criterios de parada A (λ_max objetivo),
        B (caída del fotodiodo) y C (tiempo máximo, siempre activo). La pausa cierra el láser y seguir lo
        reabre (P7); "siguiente nodo" termina el seguimiento."""
        use_lambda_stop = bool(cfg.get("use_lambda_stop", False))
        lambda_target = cfg.get("lambda_target_nm")
        use_photodiode_stop = bool(cfg.get("use_photodiode_stop", False))
        photodiode_drop_pct = cfg.get("photodiode_drop_pct")
        t_max_s = float(cfg.get("t_max_s", 60.0))
        interval_s = float(cfg.get("interval_s", 0.2))
        exp_time = float(cfg["exp_time"])
        laser = cfg["laser"]
        self._node_t_points, self._node_lmax_points = [], []
        self._node_last_spec = np.array([])
        self._node_last_wave = wave_axis
        i0 = None
        t0 = time.monotonic()
        while True:
            runner.check()
            if ctl.pause.is_set():
                runner.laser(laser, False)
                ctl.wait_while_paused(runner)
                runner.laser(laser, True)
            if ctl.take_skip():
                return
            t_frame = time.monotonic()
            spec, _mode = runner.spectrum_1d(exp_time)
            from pyspectrum.modules.routines.routine_dark import corrected
            _wf, _sf, lmax = self._fit(wave_axis, corrected(spec, self.run_dark))   # λmax sin el fondo (B3)
            elapsed = time.monotonic() - t0
            self._node_t_points.append(elapsed)
            self._node_lmax_points.append(float(lmax))
            self._node_last_spec = spec
            self.gridSpectralUpdateSignal.emit(wave_axis, spec, float(lmax), float(elapsed))
            stop = elapsed >= t_max_s
            if use_lambda_stop and lambda_target is not None and lmax >= float(lambda_target):
                stop = True
            if use_photodiode_stop and photodiode_drop_pct is not None:
                level = read_photodiode_level()
                if i0 is None:
                    i0 = level if level > 0 else 1e-9
                elif level <= i0 * (1.0 - float(photodiode_drop_pct) / 100.0):
                    stop = True
            if stop:
                return
            runner.wait(max(0.0, interval_s - (time.monotonic() - t_frame)))

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

    def _save_node_result(self, idx: int, wave_axis: np.ndarray, spec: np.ndarray,
                          t_points: List[float], lmax_points: List[float], save_dir: str):
        if len(spec) == 0:
            return
        try:
            os.makedirs(save_dir, exist_ok=True)
            base = os.path.join(save_dir, f"GrowthNode_{idx:03d}")
            from pyspectrum.calibration.repository import correction_header_text
            corr = (correction_header_text(self.spectrometer)       # R3-gui §4.6; λmax también depende del eje
                    + "\n" + self.grid_dark.header_text(self.run_dark, save_dir))   # fondo aparte (R4-N)
            np.savetxt(base + "_kinetics.txt", np.column_stack([t_points, lmax_points]),
                       header="t_s\tlambda_max_nm  (serie de exposiciones reales)\n" + corr, fmt="%.4f", encoding="utf-8")
            np.savetxt(base + "_final_spectrum.txt", np.column_stack([wave_axis, spec]),
                       header="wavelength_nm\tintensity\n" + corr, fmt="%.4f", encoding="utf-8")
        except OSError as e:
            print(f"[GrowthGrid] No se pudo guardar el nodo {idx}: {e}")

    def _save_node_failure(self, idx: int, save_dir: str, reason: str):
        try:
            os.makedirs(save_dir, exist_ok=True)
            with open(os.path.join(save_dir, f"GrowthNode_{idx:03d}_FAILED.txt"), "w", encoding="utf-8") as f:
                f.write(reason + "\n")
        except OSError as e:
            print(f"[GrowthGrid] No se pudo registrar la falla del nodo {idx}: {e}")

    def shutdown(self, timeout_ms: int = 3000):
        return [self.point_thread.shutdown(timeout_ms), self.grid_thread.shutdown(timeout_ms)]
