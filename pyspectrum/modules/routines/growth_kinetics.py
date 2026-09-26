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

from config import SHUTTERS, PI_STAGE_RANGE_UM
from core.nidaq import open_shutter, close_shutter, heartbeat_shutter
from pyspectrum.drivers.shamrock_driver import DEVICE, get_shamrock
from pyspectrum.drivers.andor_ccd_driver import get_andor_ccd
from pyspectrum.modules.hardware_session import hardware_session
from pyspectrum.calibration.fit_polynomial import fit_signal_polynomial
from pyspectrum.modules.optical_support import (
    run_z_autofocus, run_confocal_centering, move_stage_to, get_stage_coordinates, read_photodiode_level,
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
_NODE_STATE_COLORS = {NODE_PENDING: "#45475A", NODE_CURRENT: "#F9E2AF", NODE_DONE: "#A6E3A1"}


class GrowthKineticsPanel(QtWidgets.QWidget):
    """Panel de Cinética de Crecimiento embebible (Pestaña 4 del shell principal de
    PySpectrum 3.0). Contiene toda la UI y lógica de presentación; GrowthKineticsWidget lo
    envuelve en un QDialog standalone para uso independiente/retrocompatibilidad.

    Expone dos sub-pestañas: "Monitoreo Puntual" (histórico, un único punto fijo) y
    "Grilla Automatizada" (Fase 6, máquina de estados multi-nodo sobre una grilla)."""

    # ── Señales del modo puntual histórico (sin cambios, Fase 1-5) ──────────────
    startGrowthSignal = pyqtSignal(str, float, int, float)
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
        self.spin_z0 = QtWidgets.QDoubleSpinBox(); self.spin_z0.setRange(0.0, PI_STAGE_RANGE_UM); self.spin_z0.setSuffix(" µm")

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
        self.edit_save_dir = QtWidgets.QLineEdit(os.path.join(os.getcwd(), "growth_grid_data"))
        self.btn_pick_save_dir = QtWidgets.QPushButton("📁")
        self.btn_pick_save_dir.clicked.connect(self._on_pick_save_dir)
        save_row.addWidget(self.edit_save_dir)
        save_row.addWidget(self.btn_pick_save_dir)
        ctrl_vlo.addLayout(save_row)

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
            "save_dir": self.edit_save_dir.text().strip() or ".",
        }
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
    def update_grid_spectrum(self, wave: np.ndarray, spec: np.ndarray, lmax: float, elapsed_s: float):
        self.curve_grid_spec.setData(wave, spec)
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

        for attr_name in ("cmb_laser", "edit_exp", "edit_nframes", "edit_interval",
                          "btn_run", "progress_bar", "lbl_peak", "plot_spec", "curve_spec",
                          "curve_fit", "plot_spr_time", "curve_spr",
                          "btn_generate_grid", "btn_load_grid", "btn_use_current_pos",
                          "btn_grid_start", "btn_grid_pause", "btn_grid_resume", "btn_grid_next", "btn_grid_abort",
                          "lbl_grid_progress", "lbl_grid_peak", "plot_grid_map", "scatter_grid",
                          "plot_grid_spec", "curve_grid_spec"):
            setattr(self, attr_name, getattr(self.panel, attr_name))

        for sig_name in ("startGrowthSignal", "stopGrowthSignal", "generateGridSignal", "loadGridFileSignal",
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
    """Motor de adquisición y ajuste continuo para cinética de crecimiento (modo puntual
    histórico, Fase 1-5) más la máquina de estados de grilla automatizada (Fase 6, DEC-020)."""

    growthUpdatedSignal = pyqtSignal(np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, float, int)

    # ── Señales del modo grilla (Fase 6) ─────────────────────────────────────────
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

        # Estado modo puntual (histórico)
        self.t_points = []
        self.lmax_points = []
        self.curr_frame = 0
        self.total_frames = 200
        self.laser_in_use = ""

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._step)

        # Estado modo grilla (Fase 6)
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

        hardware_session.emergencyStopSignal.connect(self.stop_growth)
        hardware_session.emergencyStopSignal.connect(self.abort_grid)

    def make_connection(self, widget: GrowthKineticsWidget):
        widget.startGrowthSignal.connect(self.start_growth)
        widget.stopGrowthSignal.connect(self.stop_growth)
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

    # ══════════════════════════════════════════════════════════════════════════
    # Modo Puntual histórico (Fase 1-5, intacto)
    # ══════════════════════════════════════════════════════════════════════════
    @pyqtSlot(str, float, int, float)
    def start_growth(self, laser: str, exp_time: float, n_frames: int, interval: float):
        if not hardware_session.acquire_session(self.SESSION_NAME_POINT):
            self.stop_growth()
            return

        self.laser_in_use = laser
        self.total_frames = n_frames
        self.curr_frame = 0
        self.t_points = []
        self.lmax_points = []
        self.t0 = time.time()

        self.camera.set_exposure_time(exp_time)
        ret, self.wave_axis = self.spectrometer.ShamrockGetCalibration(DEVICE, 1004)

        open_shutter(self.laser_in_use)
        self.timer.setInterval(int(max(50, interval * 1000)))
        self.timer.start()

    @pyqtSlot()
    def stop_growth(self):
        self.timer.stop()
        if self.laser_in_use:
            close_shutter(self.laser_in_use)
            self.laser_in_use = ""
        hardware_session.release_session(self.SESSION_NAME_POINT)

    def _step(self):
        if hardware_session.is_emergency_stopped:
            self.stop_growth()
            return

        if self.curr_frame >= self.total_frames:
            self.stop_growth()
            return

        heartbeat_shutter(30.0)

        frame = self.camera.get_most_recent_image()
        spec = np.mean(frame, axis=0)

        wave_fit, spec_fit, lmax = fit_signal_polynomial(self.wave_axis, spec, ends_notch=self.wave_axis[0] + 10, final_wave=self.wave_axis[-1] - 10)

        t_now = time.time() - self.t0
        self.t_points.append(t_now)
        self.lmax_points.append(lmax)
        self.curr_frame += 1

        pct = int(100.0 * self.curr_frame / self.total_frames)
        self.growthUpdatedSignal.emit(self.wave_axis, spec, wave_fit, spec_fit,
                                      np.array(self.t_points), np.array(self.lmax_points), lmax, pct)

    # ══════════════════════════════════════════════════════════════════════════
    # Modo Grilla Automatizada (Fase 6, DEC-020)
    # ══════════════════════════════════════════════════════════════════════════
    @pyqtSlot()
    def use_current_position_as_origin(self):
        x, y, z = get_stage_coordinates()
        self.originUpdatedSignal.emit(x, y, z)

    @pyqtSlot(int, int, float, float, float, float, float)
    def generate_grid(self, rows: int, cols: int, dx_um: float, dy_um: float, x0: float, y0: float, z0: float):
        """Genera una grilla rectangular N×M de nodos absolutos (µm), análoga al generador
        paramétrico del legado Growth_ps.py::grid_create, pero produciendo coordenadas
        absolutas directamente (el origen X0/Y0/Z0 hace las veces de la antigua 'referencia')."""
        nodes = []
        for i in range(rows):
            for j in range(cols):
                nodes.append((x0 + j * dx_um, y0 + i * dy_um, z0))
        self._set_pending_nodes(nodes)

    @pyqtSlot(str)
    def load_grid_file(self, path: str):
        """Carga una grilla desde un archivo .txt (formato legado: matriz 2×N/3×N o lista
        N×2/N×3 de coordenadas X,Y[,Z] en µm; se detecta automáticamente la orientación)."""
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
    def start_grid(self, config: dict):
        if not self._pending_nodes:
            hardware_session.statusWarningSignal.emit("No hay grilla generada/cargada para iniciar.")
            return
        if not hardware_session.acquire_session(self.SESSION_NAME_GRID):
            return

        self.grid_config = config
        self.nodes = list(self._pending_nodes)
        self.states = [NODE_PENDING] * len(self.nodes)
        self.idx = 0
        self._grid_running = True
        self._grid_paused = False
        self._grid_abort_requested = False
        self._emit_grid_state()
        QTimer.singleShot(0, self._process_next_node)

    @pyqtSlot()
    def pause_grid(self):
        self._grid_paused = True

    @pyqtSlot()
    def resume_grid(self):
        if self._grid_paused and self._grid_running:
            self._grid_paused = False
            QTimer.singleShot(0, self._process_next_node)

    @pyqtSlot()
    def next_node_grid(self):
        if not self._grid_running or self.idx >= len(self.nodes):
            return
        self.states[self.idx] = NODE_DONE
        self.idx += 1
        self._emit_grid_state()
        if not self._grid_paused:
            QTimer.singleShot(0, self._process_next_node)

    @pyqtSlot()
    def abort_grid(self):
        if not self._grid_running:
            return
        self._grid_abort_requested = True
        self._grid_running = False
        laser = self.grid_config.get("laser", "")
        if laser:
            try:
                close_shutter(laser)
            except Exception as e:
                print(f"[GrowthGrid] Error cerrando obturador en abort: {e}")
        hardware_session.release_session(self.SESSION_NAME_GRID)
        self.gridFinishedSignal.emit()

    def _emit_grid_state(self):
        xs = np.array([n[0] for n in self.nodes])
        ys = np.array([n[1] for n in self.nodes])
        states = np.array(self.states)
        self.gridStateChangedSignal.emit(xs, ys, states, self.idx)

    def _check_grid_abort(self) -> bool:
        if self._grid_abort_requested or hardware_session.is_emergency_stopped or not self._grid_running:
            self.abort_grid()
            return True
        return False

    def _process_next_node(self):
        if self._check_grid_abort():
            return
        if self._grid_paused:
            return
        if self.idx >= len(self.nodes):
            self._finish_grid()
            return

        self.states[self.idx] = NODE_CURRENT
        self._emit_grid_state()
        x, y, z = self.nodes[self.idx]
        cfg = self.grid_config
        laser = cfg["laser"]
        exp_time = float(cfg["exp_time"])
        autofocus_every = max(1, int(cfg.get("autofocus_every", 1)))
        center_seed = bool(cfg.get("center_seed", False))

        self.gridNodeProgressSignal.emit(self.idx, len(self.nodes), "Moviendo platina...")
        heartbeat_shutter(30.0)
        move_stage_to(x, y, z)
        if self._check_grid_abort():
            return

        if self.idx % autofocus_every == 0:
            self.gridNodeProgressSignal.emit(self.idx, len(self.nodes), "Autofoco Z...")
            run_z_autofocus(laser_color=laser)
        if self._check_grid_abort():
            return

        if center_seed:
            self.gridNodeProgressSignal.emit(self.idx, len(self.nodes), "Centrado confocal de semilla...")
            run_confocal_centering(range_um=1.0)
        if self._check_grid_abort():
            return

        self.gridNodeProgressSignal.emit(self.idx, len(self.nodes), "Irradiando y trackeando SPR...")
        self.camera.set_exposure_time(exp_time)
        ret, wave_axis = self.spectrometer.ShamrockGetCalibration(DEVICE, 1004)
        open_shutter(laser)
        try:
            self._track_node_spectrum(wave_axis, cfg)
        finally:
            close_shutter(laser)

        if self._check_grid_abort():
            return

        self._save_node_result(self.idx, wave_axis, self._node_last_spec, self._node_t_points, self._node_lmax_points, cfg.get("save_dir", "."))

        self.states[self.idx] = NODE_DONE
        self.idx += 1
        self._emit_grid_state()
        QTimer.singleShot(0, self._process_next_node)

    def _track_node_spectrum(self, wave_axis: np.ndarray, cfg: dict):
        """Adquisición continua de alta velocidad con ajuste en vivo de λ_max y evaluación de
        los 3 criterios de parada (A: λ_max objetivo, B: caída de fotodiodo, C: tiempo máximo,
        siempre activo como colchón de seguridad)."""
        use_lambda_stop = bool(cfg.get("use_lambda_stop", False))
        lambda_target = cfg.get("lambda_target_nm")
        use_photodiode_stop = bool(cfg.get("use_photodiode_stop", False))
        photodiode_drop_pct = cfg.get("photodiode_drop_pct")
        t_max_s = float(cfg.get("t_max_s", 60.0))
        interval_s = float(cfg.get("interval_s", 0.2))

        self._node_t_points = []
        self._node_lmax_points = []
        self._node_last_spec = np.array([])
        self._node_last_wave = wave_axis

        t0 = time.time()
        state = {"i0_photodiode": None}
        loop = QEventLoop()
        timer = QTimer()
        timer.setInterval(max(50, int(interval_s * 1000)))

        def _tick():
            if self._grid_abort_requested or hardware_session.is_emergency_stopped:
                loop.quit()
                return
            heartbeat_shutter(30.0)
            frame = self.camera.get_most_recent_image()
            spec = np.mean(frame, axis=0) if hasattr(frame, "ndim") and frame.ndim == 2 else np.asarray(frame, dtype=float)
            wave_fit, spec_fit, lmax = fit_signal_polynomial(wave_axis, spec, ends_notch=wave_axis[0] + 10, final_wave=wave_axis[-1] - 10)
            elapsed = time.time() - t0

            self._node_t_points.append(elapsed)
            self._node_lmax_points.append(float(lmax))
            self._node_last_spec = spec
            self.gridSpectralUpdateSignal.emit(wave_axis, spec, float(lmax), float(elapsed))

            stop = False
            if use_lambda_stop and lambda_target is not None and lmax >= float(lambda_target):
                stop = True
            if use_photodiode_stop and photodiode_drop_pct is not None:
                level = read_photodiode_level()
                if state["i0_photodiode"] is None:
                    state["i0_photodiode"] = level if level > 0 else 1e-9
                elif level <= state["i0_photodiode"] * (1.0 - float(photodiode_drop_pct) / 100.0):
                    stop = True
            if elapsed >= t_max_s:
                stop = True
            if stop:
                loop.quit()

        timer.timeout.connect(_tick)
        timer.start()
        loop.exec()
        timer.stop()

    def _save_node_result(self, idx: int, wave_axis: np.ndarray, spec: np.ndarray,
                          t_points: List[float], lmax_points: List[float], save_dir: str):
        if len(spec) == 0:
            return
        try:
            os.makedirs(save_dir, exist_ok=True)
            base = os.path.join(save_dir, f"GrowthNode_{idx:03d}")
            np.savetxt(base + "_kinetics.txt", np.column_stack([t_points, lmax_points]),
                      header="t_s\tlambda_max_nm", fmt="%.4f")
            np.savetxt(base + "_final_spectrum.txt", np.column_stack([wave_axis, spec]),
                      header="wavelength_nm\tintensity", fmt="%.4f")
        except OSError as e:
            print(f"[GrowthGrid] No se pudo guardar el nodo {idx}: {e}")

    def _finish_grid(self):
        self._grid_running = False
        hardware_session.release_session(self.SESSION_NAME_GRID)
        self.gridFinishedSignal.emit()
