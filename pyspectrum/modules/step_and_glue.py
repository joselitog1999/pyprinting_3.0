# -*- coding: utf-8 -*-
"""
step_and_glue.py — Medición Espectral, Cosido Continuo (Step & Glue) y Cinéticas
PySpectrum 3.0 — UNSAM Nanofotónica

Fase 4 del Rework Arquitectónico (docs/decisions/DECISION_LOG.md#DEC-018): algoritmo de cosido
raised-cosine (cos²/sin²) con solapamiento configurable 10-50% (default 20%), cálculo de
centros espectrales según la dispersión real de la red activa, soporte multimodal 1D (FVB/
Single-Track) y 2D (Imagen), verificación de referencia Raman de agua (banda O-H ~3400 cm⁻¹) y
exportación HDF5 estructurada. Las funciones puras del algoritmo viven en
pyspectrum/calibration/halogen_lamp.py (testeables sin GUI); glue_steps() (blending logístico
preexistente) permanece sin cambios y sigue siendo usado por linescan_spectroscopy.py.
"""
from __future__ import annotations
import os
import threading
import time
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List, Dict
import numpy as np
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import pyqtSignal, pyqtSlot, QTimer
import pyqtgraph as pg

from pyspectrum.drivers.shamrock_driver import DEVICE, get_shamrock, NAME_GRATINGS, SHAMROCK_SUCCESS
from pyspectrum.drivers.andor_ccd_driver import (
    get_andor_ccd, READ_MODE_FVB, READ_MODE_SINGLE_TRACK, READ_MODE_IMAGE, DETECTOR_WIDTH_PX,
)
from pyspectrum.calibration.halogen_lamp import (
    HalogenLampCalibration, glue_steps,
    compute_step_centers, resolve_step_window_nm, coverage_gaps_nm,
    sigmoidal_step_and_glue, sigmoidal_step_and_glue_2d,
    export_step_and_glue_to_hdf5,
)
from pyspectrum.calibration.fit_polynomial import fit_signal_polynomial
from pyspectrum.calibration.fit_raman_water import fit_signal_raman
from pyspectrum.modules.acquisition import ExposureRequest, Frame, single_exposure
# El motor del paso 11 (DEC-040): plan, preflight y una exposición por ventana. `measured_window_nm` se
# re-exporta desde acá porque el escaneo lineal la importa de este módulo.
from pyspectrum.modules.step_glue_engine import (  # noqa: F401
    PreflightReport, StepGlueRequest, frame_shape_for, heartbeat_tick, measured_window_nm, plan, preflight,
    run_windows,
)

GRATING_SETTLE_TIMEOUT_S = 6.0


class Frontend(QtWidgets.QFrame):
    """Interfaz para adquisición de espectros simples, cosido Step & Glue y cinéticas."""

    measureSingleSignal = pyqtSignal(float, float)  # (lambda_center, exp_time)
    # (start, end, overlap_pct, exp_time, normalize, check_water, use_optical_core, subtract_substrate)
    measureStepGlueSignal = pyqtSignal(float, float, float, float, bool, bool, bool, bool)
    stopMeasurementSignal = pyqtSignal()
    saveSpectrumSignal = pyqtSignal(str)
    exportHDF5Signal = pyqtSignal(str)
    lockSubstrateSignal = pyqtSignal(float, float, float, float, bool)   # sustrato ventana por ventana (R4-N, B4)
    resumeSignal = pyqtSignal(bool)              # [Seguir] / [Stop] tras "ventana 1 sin señal" (G8)
    glueAcquiredSignal = pyqtSignal()            # [Coser lo adquirido] (Ronda 3 §4.3)
    planRequestSignal = pyqtSignal(float, float, float, float, bool)   # (desde, hasta, solape, exp, zona central)

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
        self.edit_exp = QtWidgets.QDoubleSpinBox()
        self.edit_exp.setDecimals(4)
        self.edit_exp.setRange(0.0001, 10.0)
        self.edit_exp.setValue(1.0)
        self.edit_exp.setSuffix(" s")
        self.edit_exp.setToolTip("Tiempo de integración de cada ventana. Las rutinas aceptan hasta 10 s (R4-4).")
        param_grid.addWidget(self.edit_exp, 0, 1)

        param_grid.addWidget(QtWidgets.QLabel("Paso Único λ (nm):"), 1, 0)
        self.edit_center_wl = QtWidgets.QDoubleSpinBox()
        self.edit_center_wl.setRange(0.0, 2000.0)
        self.edit_center_wl.setDecimals(2)
        self.edit_center_wl.setValue(532.0)
        self.edit_center_wl.setSuffix(" nm")
        self.edit_center_wl.setToolTip("Longitud de onda central (nm) para la adquisición simple de paso único.")
        param_grid.addWidget(self.edit_center_wl, 1, 1)

        controls_vlo.addLayout(param_grid)

        # Botón Medición Simple
        self.btn_single = QtWidgets.QPushButton("🔬 Medir Espectro Simple")
        self.btn_single.setStyleSheet("background-color: #89B4FA; color: #11111B;")
        self.btn_single.setToolTip("Posiciona el espectrógrafo y adquiere un único espectro centrado en la longitud de onda especificada.")
        self.btn_single.clicked.connect(self._on_single_measure)
        controls_vlo.addWidget(self.btn_single)

        # 2. Rango Step & Glue
        box_sandg = QtWidgets.QGroupBox("Parámetros Step & Glue (Cosido Amplio)")
        box_sandg.setStyleSheet("color: #CDD6F4; font-weight: bold; border: 1px solid #45475A; padding: 6px;")
        sandg_grid = QtWidgets.QGridLayout(box_sandg)
        sandg_grid.setSpacing(6)

        sandg_grid.addWidget(QtWidgets.QLabel("λ Inicial (nm):"), 0, 0)
        self.edit_start_wl = QtWidgets.QDoubleSpinBox()
        self.edit_start_wl.setRange(0.0, 2000.0)
        self.edit_start_wl.setDecimals(1)
        self.edit_start_wl.setValue(500.0)
        self.edit_start_wl.setSuffix(" nm")
        self.edit_start_wl.setToolTip("Longitud de onda inicial (nm) para el barrido multi-paso concatenado.")
        sandg_grid.addWidget(self.edit_start_wl, 0, 1)

        sandg_grid.addWidget(QtWidgets.QLabel("λ Final (nm):"), 1, 0)
        self.edit_end_wl = QtWidgets.QDoubleSpinBox()
        self.edit_end_wl.setRange(0.0, 2000.0)
        self.edit_end_wl.setDecimals(1)
        self.edit_end_wl.setValue(900.0)
        self.edit_end_wl.setSuffix(" nm")
        self.edit_end_wl.setToolTip("Longitud de onda final (nm) para el barrido multi-paso concatenado.")
        sandg_grid.addWidget(self.edit_end_wl, 1, 1)

        sandg_grid.addWidget(QtWidgets.QLabel("Solapamiento (%):"), 2, 0)
        self.spin_overlap_pct = QtWidgets.QSpinBox()
        self.spin_overlap_pct.setRange(10, 50)
        self.spin_overlap_pct.setValue(20)
        self.spin_overlap_pct.setSuffix(" %")
        self.spin_overlap_pct.setToolTip(
            "Porcentaje de solapamiento espectral entre ventanas consecutivas de la red activa "
            "(10% a 50%, 20% por defecto). El cosido raised-cosine funde suavemente cada región "
            "de solapamiento real, garantizando continuidad sin escalones de intensidad."
        )
        sandg_grid.addWidget(self.spin_overlap_pct, 2, 1)

        self.chk_optical_core = QtWidgets.QCheckBox("🎯 Usar Zona Óptica Central (103 nm / 12 nm)")
        self.chk_optical_core.setToolTip(
            "Planifica con la ventana fija que usaba el código legado (103 nm para 150 l/mm, "
            "12 nm para 1200 l/mm — StepandGlue_ps.py de Luciana/CIBION). Sin tildar, la ventana "
            "se mide con la calibración real del espectrógrafo, que para este detector de 8 µm "
            "da prácticamente lo mismo (103.05 / 11.57 nm, hoja de datos del SR-500i)."
        )
        sandg_grid.addWidget(self.chk_optical_core, 3, 0, 1, 2)

        controls_vlo.addWidget(box_sandg)

        # Opciones de procesamiento
        self.chk_norm_lamp = QtWidgets.QCheckBox("Normalizar con Lámpara Halógena")
        self.chk_norm_lamp.setChecked(False)
        self.chk_norm_lamp.setToolTip("Corrige la curva de respuesta instrumental espectral dividiendo por el perfil de la lámpara halógena.\n"
                                      "Sin un archivo de lámpara real no se inicia: nunca se normaliza con un perfil sintético.")
        controls_vlo.addWidget(self.chk_norm_lamp)

        self.chk_fit_poly = QtWidgets.QCheckBox("Ajuste Polinomial SPR (λ_max)")
        self.chk_fit_poly.setChecked(True)
        self.chk_fit_poly.setToolTip("Ajusta un modelo polinomial de 4to orden para estimar el pico máximo de resonancia plasmónica (SPR).")
        controls_vlo.addWidget(self.chk_fit_poly)

        self.chk_fit_raman = QtWidgets.QCheckBox("Verificar Referencia Raman Agua (banda O-H, ~3400 cm⁻¹)")
        self.chk_fit_raman.setToolTip("Ajusta la banda O-H del agua (~650 nm a 532 nm de excitación) sobre el espectro cosido, para detectar distorsión espectral introducida por el cosido.")
        controls_vlo.addWidget(self.chk_fit_raman)

        # Fijar fondo de sustrato (código legado: "Lock Signal on Sustrate")
        substrate_box = QtWidgets.QHBoxLayout()
        self.btn_lock_substrate = QtWidgets.QPushButton("🔒 Fijar sustrato (barrido completo)")
        self.btn_lock_substrate.setToolTip(
            "Barre el sustrato con el mismo plan (desde, hasta, solape, exposición) y guarda una ventana por λc.\n"
            "Al restar, cada ventana de la muestra resta el sustrato de SU λc; el oscuro se cancela.\n"
            "Si el plan, la exposición, la red o el modo de lectura no coinciden, el sustrato no se resta (R4-N, B4).")
        self.btn_lock_substrate.clicked.connect(self._on_lock_substrate)
        substrate_box.addWidget(self.btn_lock_substrate)

        self.chk_sub_substrate = QtWidgets.QCheckBox("Restar Fondo de Sustrato")
        self.chk_sub_substrate.setToolTip("Resta a cada ventana el sustrato de su misma λc, antes de la normalización y el cosido.")
        substrate_box.addWidget(self.chk_sub_substrate)
        controls_vlo.addLayout(substrate_box)

        from pyspectrum.ui.background_row import BackgroundRow
        self.bg_row = BackgroundRow(default_frames=1)                # un oscuro por corrida (R4-N)
        controls_vlo.addWidget(self.bg_row)

        # Plan y preflight (Ronda 3 §1.9-1.9.1): se recalculan con cada cambio, sin tocar el hardware
        self.lbl_plan = QtWidgets.QLabel("Plan: —")
        self.lbl_plan.setWordWrap(True)
        self.lbl_plan.setStyleSheet("color: #A6ADC8; font-size: 8.5pt;")
        self.lbl_plan.setToolTip("Paso ≈ W · (1 − solape). Por ventana: movimiento (≤ 0.3 s, provisorio hasta BANCO-39) +\n"
                                 "exposición + lectura (≈ 0.08 s a 13 MHz).")
        controls_vlo.addWidget(self.lbl_plan)
        self.lbl_preflight = QtWidgets.QLabel("")
        self.lbl_preflight.setWordWrap(True)
        controls_vlo.addWidget(self.lbl_preflight)
        for w in (self.edit_start_wl, self.edit_end_wl, self.edit_exp):
            w.valueChanged.connect(lambda _v: self._request_plan())
        self.spin_overlap_pct.valueChanged.connect(lambda _v: self._request_plan())
        self.chk_optical_core.toggled.connect(lambda _v: self._request_plan())

        # Botones de Acción Step & Glue y Detención
        btn_box = QtWidgets.QHBoxLayout()
        self.btn_sandg = QtWidgets.QPushButton("🧩 Ejecutar Step and Glue")
        self.btn_sandg.setStyleSheet("background-color: #A6E3A1; color: #11111B;")
        self.btn_sandg.setToolTip("Inicia la rutina automática: cálculo de centros intermedios, rotación de red, lectura y cosido suave de espectros.")
        self.btn_sandg.clicked.connect(self._on_sandg_measure)
        btn_box.addWidget(self.btn_sandg)

        self.btn_stop = QtWidgets.QPushButton("⏹ Detener")
        self.btn_stop.setStyleSheet("background-color: #F38BA8; color: #11111B;")
        self.btn_stop.setToolTip("Detiene de manera inmediata y segura la rutina de adquisición y movimiento en curso, entregando el cosido parcial obtenido hasta ese momento.")
        self.btn_stop.clicked.connect(self._on_stop_measure)
        btn_box.addWidget(self.btn_stop)
        controls_vlo.addLayout(btn_box)

        # Pausa por "ventana 1 sin señal" (G8): la ventana no se descarta
        pause_box = QtWidgets.QHBoxLayout()
        self.btn_resume = QtWidgets.QPushButton("▶ Seguir")
        self.btn_resume.clicked.connect(lambda: self._answer_no_signal(True))
        self.btn_resume.hide()
        pause_box.addWidget(self.btn_resume)
        self.btn_glue_partial = QtWidgets.QPushButton("🧵 Coser lo adquirido")
        self.btn_glue_partial.setToolTip("Cose las ventanas de un barrido incompleto. El resultado queda rotulado como incompleto.")
        self.btn_glue_partial.clicked.connect(self.glueAcquiredSignal.emit)
        self.btn_glue_partial.hide()
        pause_box.addWidget(self.btn_glue_partial)
        controls_vlo.addLayout(pause_box)

        self.table_windows = QtWidgets.QTableWidget(0, 5)
        self.table_windows.setHorizontalHeaderLabels(["#", "λc pedida", "λc leída", "estado", "archivo"])
        self.table_windows.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_windows.setMinimumHeight(160)
        self.table_windows.horizontalHeader().setStretchLastSection(True)
        controls_vlo.addWidget(self.table_windows)

        # Barra de Progreso No Bloqueante
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Paso %v / %m")
        self.progress_bar.setToolTip("Progreso del barrido secuencial de longitudes de onda centrales.")
        controls_vlo.addWidget(self.progress_bar)

        self.lbl_water_ref = QtWidgets.QLabel("")
        self.lbl_water_ref.setWordWrap(True)
        self.lbl_water_ref.setStyleSheet("color: #F9E2AF; font-size: 8.5pt;")
        controls_vlo.addWidget(self.lbl_water_ref)

        self.btn_save = QtWidgets.QPushButton("💾 Guardar Espectro (.txt)...")
        self.btn_save.setStyleSheet("background-color: #313244; color: #CDD6F4;")
        self.btn_save.setToolTip("Guarda los datos espectrales procesados (longitud de onda e intensidad) en formato de texto (.txt).")
        self.btn_save.clicked.connect(self._on_save_spectrum)
        controls_vlo.addWidget(self.btn_save)

        self.btn_export_hdf5 = QtWidgets.QPushButton("💾 Exportar HDF5 Estructurado...")
        self.btn_export_hdf5.setStyleSheet("background-color: #313244; color: #CDD6F4;")
        self.btn_export_hdf5.setToolTip("Exporta el cosido completo (/glued_spectrum, /wavelengths, /raw_steps por paso) con metadatos de red, ranura, pasos y timestamp a HDF5 estructurado.")
        self.btn_export_hdf5.clicked.connect(self._on_export_hdf5)
        controls_vlo.addWidget(self.btn_export_hdf5)

        # Barra de Estado / Info
        self.lbl_status = QtWidgets.QLabel("Listo para medir.")
        self.lbl_status.setStyleSheet("color: #A6ADC8; font-size: 8.5pt;")
        controls_vlo.addWidget(self.lbl_status)

        controls_vlo.addStretch()
        main_layout.addLayout(controls_vlo, stretch=1)

        # ── Gráfico Espectral Derecho ─────────────────────────────────────────
        self.plot_widget = pg.PlotWidget(title="<b>Espectro Adquirido / Step & Glue</b>")
        self.plot_widget.setBackground("#11111B")
        self.plot_widget.setLabel('bottom', "Longitud de Onda (nm)", color='#CDD6F4')
        self.plot_widget.setLabel('left', "Intensidad (Cuentas / Normalizado)", color='#CDD6F4')
        self.plot_widget.setTitle("<b>Espectro Adquirido / Step & Glue</b>", color='#CDD6F4')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.addLegend(offset=(10, 10))

        self.curve_raw = self.plot_widget.plot(name="Espectro Crudo", pen=pg.mkPen("#89B4FA", width=2.0))
        self.curve_norm = self.plot_widget.plot(name="Normalizado Lámpara", pen=pg.mkPen("#A6E3A1", width=2.0))
        self.curve_fit = self.plot_widget.plot(name="Ajuste Analítico", pen=pg.mkPen("#F38BA8", width=2.5, style=QtCore.Qt.PenStyle.DashLine))

        main_layout.addWidget(self.plot_widget, stretch=3)

    def _on_single_measure(self):
        wl = float(self.edit_center_wl.value())
        exp = float(self.edit_exp.value())
        self.lbl_status.setText(f"Midiendo espectro simple en {wl:.1f} nm...")
        self.measureSingleSignal.emit(wl, exp)

    def _request_plan(self):
        self.planRequestSignal.emit(float(self.edit_start_wl.value()), float(self.edit_end_wl.value()),
                                    float(self.spin_overlap_pct.value()) / 100.0, float(self.edit_exp.value()),
                                    self.chk_optical_core.isChecked())

    def _confirm_mirror(self) -> bool:
        """Advertencia del espejo de detección (R4-A-4, G4): la única con diálogo (Ronda 3 §1.9.1). El espejo no
        tiene sensor: es lo último que ordenó el software (C-08, BANCO-21)."""
        try:
            from core.nidaq import confirm_detection_mirror_belief, flipper_notch532, get_detection_mirror_belief
            belief = get_detection_mirror_belief()
        except Exception:
            return True
        if belief.position == "down":
            return True
        text = ("El software no sabe dónde está el espejo de detección." if belief.position == "unknown"
                else "El software cree que el espejo de detección está ARRIBA.")
        box = QtWidgets.QMessageBox(self)
        box.setWindowTitle("Step & Glue: espejo de detección")
        box.setText(text + "\nEl espejo no tiene sensor: esto es lo último que ordenó el software.\n"
                           "Con el espejo arriba, la luz no llega al espectrómetro.")
        b_down = box.addButton("Bajar el espejo y seguir", QtWidgets.QMessageBox.ButtonRole.AcceptRole)
        b_conf = box.addButton("Ya está abajo: confirmo y sigo", QtWidgets.QMessageBox.ButtonRole.AcceptRole)
        b_cancel = box.addButton("Cancelar", QtWidgets.QMessageBox.ButtonRole.RejectRole)
        b_estop = box.addButton("🚨 E-STOP", QtWidgets.QMessageBox.ButtonRole.DestructiveRole)
        box.setDefaultButton(b_cancel)
        box.exec()
        clicked = box.clickedButton()
        if clicked is b_estop:
            from pyspectrum.modules.hardware_session import hardware_session
            hardware_session.emergency_stop()
            return False
        if clicked is b_down:
            return bool(flipper_notch532("down"))
        if clicked is b_conf:
            confirm_detection_mirror_belief("down")
            return True
        return False

    def _on_sandg_measure(self):
        start_wl = float(self.edit_start_wl.value())
        end_wl = float(self.edit_end_wl.value())
        overlap_pct = float(self.spin_overlap_pct.value()) / 100.0
        exp = float(self.edit_exp.value())
        norm = self.chk_norm_lamp.isChecked()
        check_water = self.chk_fit_raman.isChecked()
        use_optical_core = self.chk_optical_core.isChecked()
        subtract_substrate = self.chk_sub_substrate.isChecked()
        if not self._confirm_mirror():
            self.lbl_status.setText("Step & Glue cancelado (espejo de detección).")
            return
        self.lbl_water_ref.setText("")
        self.btn_glue_partial.hide()
        self.lbl_status.setText(f"Ejecutando Step & Glue [{start_wl:.0f} - {end_wl:.0f} nm], solapamiento {self.spin_overlap_pct.value()}%...")
        self.measureStepGlueSignal.emit(
            start_wl, end_wl, overlap_pct, exp, norm, check_water, use_optical_core, subtract_substrate,
        )

    def _answer_no_signal(self, go_on: bool):
        self.btn_resume.hide()
        self.resumeSignal.emit(go_on)

    @pyqtSlot(str)
    def show_status(self, message: str):
        self.lbl_status.setText(message)

    @pyqtSlot(object)
    def show_plan(self, the_plan):
        n = len(the_plan.centers)
        step = (the_plan.centers[1] - the_plan.centers[0]) if n > 1 else 0.0
        mins = the_plan.estimated_duration_s / 60.0
        self.lbl_plan.setText(f"Plan: {n} ventanas · paso ≈ {step:.1f} nm · ≈ {mins:.1f} min · ventana "
                              f"{the_plan.window_nm:.1f} nm ({the_plan.window_source})")
        if not self.table_windows.rowCount() or getattr(self, "_plan_rows", None) != n:
            self._plan_rows = n
            self.table_windows.setRowCount(0)
            for i, c in enumerate(the_plan.centers):
                self.table_windows.insertRow(i)
                for col, text in enumerate((str(i + 1), f"{c:.2f}", "", "pendiente", "")):
                    self.table_windows.setItem(i, col, QtWidgets.QTableWidgetItem(text))

    @pyqtSlot(object)
    def show_preflight(self, report):
        lines = [f"⛔ {b}" for b in report.blockers] + [f"⚠️ {w}" for w in report.warnings]
        self.lbl_preflight.setText("\n".join(lines))
        self.lbl_preflight.setStyleSheet(f"color: {'#F38BA8' if report.blockers else '#F9E2AF'}; font-size: 8.5pt;")

    @pyqtSlot(object)
    def on_window_acquired(self, w):
        row = w.index
        if row < self.table_windows.rowCount():
            self.table_windows.setItem(row, 2, QtWidgets.QTableWidgetItem(f"{w.center_nm_read:.2f}"))
            state = "✓ en disco" + (" · LIGHT_CHANGED" if w.light_changed else "")
            self.table_windows.setItem(row, 3, QtWidgets.QTableWidgetItem(state))
            self.table_windows.setItem(row, 4, QtWidgets.QTableWidgetItem(w.path.name if w.path else ""))

    @pyqtSlot(int)
    def on_no_signal(self, index: int):
        self.lbl_status.setText(f"Ventana {index + 1}: sin señal por encima del fondo. ¿Espejo arriba o lámpara "
                                f"apagada? [Seguir] o [Detener].")
        self.btn_resume.show()

    @pyqtSlot(object)
    def on_sweep_finished(self, result):
        self.btn_resume.hide()
        done = len(result.windows)
        for row in range(done, self.table_windows.rowCount()):
            state = "interrumpida (sin datos)" if row == done and not result.complete else "no adquirida"
            self.table_windows.setItem(row, 3, QtWidgets.QTableWidgetItem(state))
        self.btn_glue_partial.setVisible(not result.complete and done > 0)

    def _on_stop_measure(self):
        self.lbl_status.setText("⏹ Detención solicitada por el usuario...")
        self.stopMeasurementSignal.emit()

    def _on_lock_substrate(self):
        if not self._confirm_mirror():
            self.lbl_status.setText("Sustrato cancelado (espejo de detección).")
            return
        self.lbl_status.setText("🔒 Barriendo el sustrato con el plan actual...")
        self.lockSubstrateSignal.emit(float(self.edit_start_wl.value()), float(self.edit_end_wl.value()),
                                      float(self.spin_overlap_pct.value()) / 100.0, float(self.edit_exp.value()),
                                      self.chk_optical_core.isChecked())

    def exposure(self):
        return float(self.edit_exp.value())

    def _on_save_spectrum(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Guardar Espectro", "", "Datos ASCII (*.txt *.csv);;NumPy (*.npz);;Todos (*.*)")
        if path:
            self.lbl_status.setText(f"Guardando espectro en {Path(path).name}...")
            self.saveSpectrumSignal.emit(path)

    def _on_export_hdf5(self):
        default_name = f"StepAndGlue_{time.strftime('%Y%m%d_%H%M%S')}.h5"
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Exportar HDF5 Estructurado", default_name, "HDF5 (*.h5 *.hdf5)")
        if path:
            self.lbl_status.setText(f"Exportando HDF5 estructurado a {Path(path).name}...")
            self.exportHDF5Signal.emit(path)

    @pyqtSlot(int, int, float)
    def update_progress(self, step_idx: int, n_steps: int, wl_center: float):
        self.progress_bar.setRange(0, max(1, n_steps))
        self.progress_bar.setValue(step_idx)
        self.progress_bar.setFormat(f"Paso {step_idx} / {n_steps} (λ_c = {wl_center:.1f} nm)")

    @pyqtSlot(str)
    def update_water_reference_status(self, message: str):
        self.lbl_water_ref.setText(message)

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


@dataclass(frozen=True)
class Substrate:
    """El sustrato ventana por ventana (R4-N, B4): una ventana cruda por λc pedida, con la llave del plan."""
    key: tuple
    windows: Dict[float, np.ndarray]
    dark_id: Optional[str]
    run_dir: str


class StepGlueWorker(QtCore.QObject):
    """Corre `run_windows` en su propio `QThread` (G1, paso 11). La GUI sigue respondiendo y Stop / E-STOP
    se ven en el tramo siguiente. La pausa por "sin señal" sigue latiendo (D-17)."""

    windowAcquired = pyqtSignal(object)
    progress = pyqtSignal(int, int, float)
    noSignal = pyqtSignal(int)
    finished = pyqtSignal(object)

    def __init__(self, request, the_plan, camera, spectrometer, run_dir: Path, abort_event: threading.Event,
                 dark=None):
        super().__init__()
        self.dark = dark                     # el oscuro de la corrida (R4-N)
        self.request, self.plan = request, the_plan
        self.camera, self.spectrometer = camera, spectrometer
        self.run_dir = run_dir
        self._abort = abort_event
        self._resume_event = threading.Event()
        self._resume_answer = True

    def resume(self, go_on: bool):
        self._resume_answer = bool(go_on)
        self._resume_event.set()

    def _wait_answer(self, window) -> bool:
        self.noSignal.emit(window.index)
        tick = heartbeat_tick()
        while not self._resume_event.wait(0.1):
            tick()                               # la pausa sigue latiendo (D-17)
            if self._abort.is_set() or _estopped():
                return False
        self._resume_event.clear()
        return self._resume_answer

    @pyqtSlot()
    def run(self):
        res = run_windows(self.plan, self.request, self.camera, self.spectrometer, run_dir=self.run_dir,
                          should_abort=self._abort.is_set, on_tick=heartbeat_tick(), is_estopped=_estopped,
                          on_window=self.windowAcquired.emit, on_no_signal=self._wait_answer,
                          on_progress=lambda i, n, f: self.progress.emit(i, n, f), dark=self.dark)
        self.finished.emit(res)


def _estopped() -> bool:
    from pyspectrum.modules.hardware_session import hardware_session
    return bool(hardware_session.is_emergency_stopped)


def _mirror_position() -> str:
    try:
        from core.nidaq import get_detection_mirror_belief
        return get_detection_mirror_belief().position
    except Exception:
        return "unknown"


def _open_lasers() -> List[str]:
    try:
        from core.nidaq import get_open_shutter_names
        return list(get_open_shutter_names())
    except Exception:
        return []


class Backend(QtCore.QObject):
    """Step & Glue sobre el motor (paso 11, DEC-040). La GUI usa `start_sweep`, que corre en un QThread;
    `measure_step_and_glue` es la misma secuencia, síncrona, para scripts y tests."""

    spectrumFinishedSignal = pyqtSignal(np.ndarray, np.ndarray, np.ndarray, np.ndarray, float)
    fitFinishedSignal = pyqtSignal(np.ndarray, np.ndarray)
    stepProgressSignal = pyqtSignal(int, int, float)  # (step_idx, n_steps, wl_center)
    waterReferenceCheckedSignal = pyqtSignal(str)
    statusSignal = pyqtSignal(str)
    preflightSignal = pyqtSignal(object)      # PreflightReport
    planSignal = pyqtSignal(object)           # StepGluePlan
    windowAcquiredSignal = pyqtSignal(object)  # WindowResult
    noSignalSignal = pyqtSignal(int)
    sweepFinishedSignal = pyqtSignal(object)  # StepGlueResult

    def __init__(self, camera=None, spectrometer=None, parent=None):
        super().__init__(parent)
        self.camera = camera or get_andor_ccd()
        self.spectrometer = spectrometer or get_shamrock()
        self.lamp_calib = HalogenLampCalibration()
        self._abort_event = threading.Event()
        self._last_wave = np.array([])
        self._last_spec = np.array([])
        self._last_norm = np.array([])
        self._raw_wave_steps: List[np.ndarray] = []
        self._raw_spec_steps: List[np.ndarray] = []
        self._last_frame_2d: Optional[np.ndarray] = None  # matriz cosida (H, W_total) en modo Imagen 2D
        self.substrate = None                   # sustrato ventana por ventana (R4-N, B4)
        # Un oscuro por corrida (R4-N), con el modo y la forma de las ventanas
        from pyspectrum.modules.routines.routine_dark import RoutineDark
        self.dark_ctl = RoutineDark(self.camera, self.spectrometer, "Step & Glue", "StepGlue", self,
                                    conditions_fn=self._dark_conditions)
        self.subtract_dark = True
        self._conclude_opts: Dict = {}
        self._last_req = None
        self._single_dark = None
        self._last_window_nm: Optional[float] = None
        self._last_window_source: str = ""
        self._last_coverage_gaps: List[tuple] = []
        self.last_result = None                 # StepGlueResult del último barrido
        # Carpeta de las ventanas: la de trabajo de PySpectrum (la ventana la actualiza). Nunca el directorio
        # actual: los tests y un lanzamiento desde el repo no deben dejar datos dentro del repositorio.
        base = os.getenv("PYSPECTRUM_ROUTINE_DATA_DIR") or str(Path.home() / "Documents" / "Data_PySpectrum")
        self.data_dir = Path(base) / "step_and_glue"
        self._thread: Optional[QtCore.QThread] = None
        self._worker: Optional[StepGlueWorker] = None
        self._sweep_opts: Dict = {}

    @property
    def _abort_requested(self) -> bool:
        return self._abort_event.is_set()

    @_abort_requested.setter
    def _abort_requested(self, value: bool) -> None:
        self._abort_event.set() if value else self._abort_event.clear()

    def make_connection(self, frontend: "Frontend"):
        frontend.measureSingleSignal.connect(self.measure_single_spectrum)
        frontend.measureStepGlueSignal.connect(self.start_sweep)
        frontend.stopMeasurementSignal.connect(self.stop_measurement)
        frontend.saveSpectrumSignal.connect(self.save_spectrum)
        frontend.exportHDF5Signal.connect(self.export_hdf5)
        frontend.lockSubstrateSignal.connect(self.lock_substrate)
        frontend.resumeSignal.connect(self.resume)
        frontend.glueAcquiredSignal.connect(self.glue_acquired)
        frontend.planRequestSignal.connect(self.publish_plan)
        self.spectrumFinishedSignal.connect(frontend.update_spectrum_plot)
        self.fitFinishedSignal.connect(frontend.update_fit_plot)
        self.stepProgressSignal.connect(frontend.update_progress)
        self.waterReferenceCheckedSignal.connect(frontend.update_water_reference_status)
        self.statusSignal.connect(frontend.show_status)
        self.preflightSignal.connect(frontend.show_preflight)
        self.planSignal.connect(frontend.show_plan)
        self.windowAcquiredSignal.connect(frontend.on_window_acquired)
        self.noSignalSignal.connect(frontend.on_no_signal)
        self.sweepFinishedSignal.connect(frontend.on_sweep_finished)
        if hasattr(frontend, "bg_row"):
            from pyspectrum.modules.routines.routine_dark import wire_row
            wire_row(frontend.bg_row, self.dark_ctl, frontend.exposure, getattr(frontend, "lbl_status", None))
            frontend.bg_row.chk_subtract.toggled.connect(self.set_subtract_dark)

    @pyqtSlot()
    def stop_measurement(self):
        self._abort_event.set()
        print("[Step & Glue] Solicitud de detención recibida.")

    @pyqtSlot(bool)
    def resume(self, go_on: bool):
        if self._worker is not None:
            self._worker.resume(go_on)

    def shutdown(self, timeout_ms: int = 3000):
        """Cierre de PySpectrum (paso 13): pide Stop, suelta una pausa de "sin señal" y espera el hilo con
        tope. El resultado parcial no se cose ni se informa: el programa se está cerrando."""
        from pyspectrum.services.shutdown import ShutdownStep
        self._shutting_down = True
        self.stop_measurement()
        if self._worker is not None:
            self._worker.resume(False)
        if self._thread is None:
            return ShutdownStep("Step & Glue", True, "sin barrido en curso")
        self._thread.quit()
        if self._thread.wait(timeout_ms):
            return ShutdownStep("Step & Glue", True, "barrido detenido")
        return ShutdownStep("Step & Glue", False, f"el hilo del barrido no terminó en {timeout_ms / 1000:g} s")

    # ── oscuro de la corrida y sustrato (R4-N) ──
    def _dark_conditions(self, exposure_s: float):
        from pyspectrum.services import procedure_background as pb
        mode = self.camera.get_read_mode() if hasattr(self.camera, "get_read_mode") else READ_MODE_FVB
        return pb.read_conditions(self.camera, frame_shape_for(mode), exposure_s=float(exposure_s), read_mode=mode)

    def _dark_fn(self, req):
        return lambda expose: self.dark_ctl.ensure_with(expose, req.exposure_s)

    def _refuse_without_dark(self, exp_time: float) -> bool:
        refusal = self.dark_ctl.check_start(float(exp_time))
        if refusal:
            self.statusSignal.emit(f"⛔ {refusal}")
        return bool(refusal)

    @staticmethod
    def _plan_key(req, the_plan):
        return (tuple(round(float(c), 4) for c in the_plan.centers), round(float(req.exposure_s), 9),
                int(req.read_mode), int(req.grating), tuple(the_plan.frame_shape))

    @pyqtSlot(bool)
    def set_subtract_dark(self, on: bool):
        """"Restar" de la fila: vuelve a procesar y coser el último barrido con o sin el oscuro."""
        self.subtract_dark = bool(on)
        res = self.last_result
        if res is not None and res.windows and self._conclude_opts:
            o = self._conclude_opts
            self._raw_spec_steps = self._processed_windows(res, o["subtract_substrate"], quiet=True)
            if res.complete:
                self._glue_and_emit(o["start_wl"], o["end_wl"], o["normalize"], False, incomplete=False)

    def _processed_windows(self, result, subtract_substrate: bool, quiet: bool = False):
        """Cada ventana para procesar (B3): menos su sustrato (misma λc; el oscuro se cancela) o menos el
        oscuro de la corrida. Lo guardado sigue crudo."""
        from pyspectrum.modules.routines.routine_dark import corrected
        dark = result.dark if self.subtract_dark else None
        sub_windows = None
        if subtract_substrate:
            if self.substrate is None:
                if not quiet:
                    self.statusSignal.emit("⚠️ No hay sustrato fijado: no se restó (sólo el oscuro).")
            elif self._last_req is None or self.substrate.key != self._plan_key(self._last_req, result.plan):
                if not quiet:
                    self.statusSignal.emit("⚠️ El sustrato es de otro plan (λc, exposición, red o modo de lectura): "
                                           "no se restó; se restó sólo el oscuro.")
            else:
                sub_windows = self.substrate.windows
        out = []
        for w in result.windows:
            s_data = sub_windows.get(round(float(w.center_nm_requested), 4)) if sub_windows is not None else None
            if s_data is not None and np.shape(s_data) == np.shape(w.data):
                out.append(np.asarray(w.data, dtype=np.float64) - s_data)
            else:
                out.append(corrected(w.data, dark))
        return out

    def _store_substrate(self, req, result):
        if not result.complete:
            self.statusSignal.emit(f"⛔ El sustrato no se fijó: el barrido no terminó ({result.detail}).")
            return
        self.substrate = Substrate(
            key=self._plan_key(req, result.plan),
            windows={round(float(w.center_nm_requested), 4): np.asarray(w.data, dtype=np.float64)
                     for w in result.windows},
            dark_id=result.dark.id if result.dark is not None else None,
            run_dir=str(result.windows[0].path.parent) if result.windows and result.windows[0].path else "")
        self.statusSignal.emit(f"🔒 Sustrato fijado: {len(result.windows)} ventanas, una por λc.")

    @pyqtSlot(float, float, float, float, bool)
    def lock_substrate(self, start_wl: float, end_wl: float, overlap_pct: float, exp_time: float,
                       use_optical_core: bool = False):
        """[Fijar sustrato]: un barrido completo sobre el sustrato, en su hilo, con el mismo plan (B4)."""
        self.start_sweep(start_wl, end_wl, overlap_pct, exp_time, False, False, use_optical_core, False,
                         substrate=True)

    def measure_substrate(self, start_wl: float, end_wl: float, overlap_pct: float, exp_time: float,
                          use_optical_core: bool = False):
        """El mismo barrido del sustrato, síncrono (scripts, tests)."""
        return self.measure_step_and_glue(start_wl, end_wl, overlap_pct, exp_time, False, False, use_optical_core,
                                          False, substrate=True)

    # ── pedido, plan y preflight ──
    def _request(self, start_wl, end_wl, overlap, exp_time, normalize, use_optical_core) -> StepGlueRequest:
        ret_g, grating = self.spectrometer.ShamrockGetGrating(DEVICE)
        g = self.camera.get_emccd_gain() if hasattr(self.camera, "get_emccd_gain") else 0
        gain = int(g[1]) if isinstance(g, (tuple, list)) else int(g)
        read_mode = self.camera.get_read_mode() if hasattr(self.camera, "get_read_mode") else READ_MODE_FVB
        lamp_file = getattr(self.lamp_calib, "source_path", None) if normalize else None
        return StepGlueRequest(float(start_wl), float(end_wl), float(overlap), float(exp_time), int(read_mode),
                               int(grating) if ret_g == SHAMROCK_SUCCESS else -1, gain,
                               normalize_with_lamp=bool(normalize), lamp_file=lamp_file,
                               use_optical_core=bool(use_optical_core))

    @pyqtSlot(float, float, float, float, bool)
    def publish_plan(self, start_wl: float, end_wl: float, overlap: float, exp_time: float, use_optical_core: bool):
        """Plan en vivo para la GUI: puro, sin tocar el hardware salvo lecturas (Ronda 3 §1.9)."""
        try:
            req = self._request(start_wl, end_wl, overlap, exp_time, False, use_optical_core)
            self.planSignal.emit(plan(req, self.spectrometer, measured_window=self._measured_window_nm()))
        except Exception as e:
            self.statusSignal.emit(f"No se pudo calcular el plan: {e}")

    def _prepare(self, start_wl, end_wl, overlap, exp_time, normalize, use_optical_core):
        req = self._request(start_wl, end_wl, overlap, exp_time, normalize, use_optical_core)
        the_plan = plan(req, self.spectrometer, measured_window=self._measured_window_nm())
        rep = preflight(req, the_plan, self.camera, self.spectrometer, mirror_position=_mirror_position(),
                        open_shutters=_open_lasers())
        self._last_window_nm, self._last_window_source = the_plan.window_nm, the_plan.window_source
        self.planSignal.emit(the_plan)
        self.preflightSignal.emit(rep)
        return req, the_plan, rep

    def _begin(self) -> bool:
        from pyspectrum.modules.hardware_session import hardware_session
        from pyspectrum.services.spectrometer_shutter import open_spectrometer_shutter
        if not hardware_session.acquire_session("Step & Glue", auto_pause_live=True):
            self.statusSignal.emit("Step & Glue no arrancó: el hardware está ocupado o la E-STOP está activa.")
            return False
        res = open_spectrometer_shutter(self.camera, self.spectrometer)      # G6, R4-H-2
        if not res.ok:
            self.statusSignal.emit(f"⛔ {res.detail} No se inicia el barrido.")
            hardware_session.release_session("Step & Glue")
            return False
        return True

    def _end(self):
        from pyspectrum.modules.hardware_session import hardware_session
        from pyspectrum.services.spectrometer_shutter import close_spectrometer_shutter
        res = close_spectrometer_shutter(self.camera, self.spectrometer)
        if not res.ok:
            self.statusSignal.emit(f"⚠️ {res.detail}")
        hardware_session.release_session("Step & Glue", restore_live=False)

    def _run_dir(self) -> Path:
        return Path(self.data_dir) / time.strftime("sg_%Y%m%d_%H%M%S")

    # ── barrido en su hilo (GUI) ──
    @pyqtSlot(float, float, float, float, bool, bool, bool, bool)
    def start_sweep(self, start_wl: float, end_wl: float, overlap_pct: float, exp_time: float,
                    normalize: bool, check_water: bool = False, use_optical_core: bool = False,
                    subtract_substrate: bool = False, substrate: bool = False):
        if self._thread is not None:
            self.statusSignal.emit("Ya hay un barrido en curso.")
            return
        req, the_plan, rep = self._prepare(start_wl, end_wl, overlap_pct, exp_time, normalize, use_optical_core)
        if rep.blockers:
            self.statusSignal.emit("⛔ No se inicia: " + "; ".join(rep.blockers))
            return
        if self._refuse_without_dark(exp_time):
            return
        if not self._begin():
            return
        self._abort_event.clear()
        self._sweep_opts = dict(start_wl=start_wl, end_wl=end_wl, normalize=normalize, check_water=check_water,
                                subtract_substrate=subtract_substrate, substrate=substrate, req=req)
        self._thread = QtCore.QThread()
        self._worker = StepGlueWorker(req, the_plan, self.camera, self.spectrometer, self._run_dir(), self._abort_event,
                                      dark=self._dark_fn(req))
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.windowAcquired.connect(self.windowAcquiredSignal.emit)
        self._worker.progress.connect(lambda i, n, f: self._on_progress(i, n, the_plan))
        self._worker.noSignal.connect(self.noSignalSignal.emit)
        self._worker.finished.connect(self._on_worker_finished)
        self._thread.start()

    def _on_progress(self, i, n, the_plan):
        center = the_plan.centers[min(max(i - 1, 0), len(the_plan.centers) - 1)] if the_plan.centers else 0.0
        self.stepProgressSignal.emit(i, n, center)

    @pyqtSlot(object)
    def _on_worker_finished(self, result):
        if getattr(self, "_shutting_down", False):
            return                  # el cierre ya detuvo el hilo y cerró los equipos (paso 13)
        self._end()
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(2000)
        self._thread, self._worker = None, None
        opts = dict(self._sweep_opts)
        req = opts.pop("req")
        if opts.pop("substrate", False):
            self._store_substrate(req, result)
            return
        self._last_req = req
        self._conclude(result, **opts)

    # ── barrido síncrono (scripts, tests) ──
    @pyqtSlot(float, float, float, float, bool, bool, bool, bool)
    def measure_step_and_glue(self, start_wl: float, end_wl: float, overlap_pct: float, exp_time: float,
                               normalize: bool, check_water: bool = False, use_optical_core: bool = False,
                               subtract_substrate: bool = False, substrate: bool = False):
        req, the_plan, rep = self._prepare(start_wl, end_wl, overlap_pct, exp_time, normalize, use_optical_core)
        if rep.blockers:
            self.statusSignal.emit("⛔ No se inicia: " + "; ".join(rep.blockers))
            return None
        if self._refuse_without_dark(exp_time):
            return None
        if not self._begin():
            return None
        self._abort_event.clear()
        try:
            def on_window(w):
                self.windowAcquiredSignal.emit(w)
                self.stepProgressSignal.emit(w.index + 1, len(the_plan.centers), w.center_nm_requested)

            def on_no_signal(w):
                self.statusSignal.emit("⚠️ Ventana 1 sin señal por encima del fondo: ¿espejo arriba o lámpara apagada?")
                return True
            result = run_windows(the_plan, req, self.camera, self.spectrometer, run_dir=self._run_dir(),
                                 should_abort=self._abort_event.is_set, on_tick=heartbeat_tick(), is_estopped=_estopped,
                                 on_window=on_window, on_no_signal=on_no_signal, dark=self._dark_fn(req))
        finally:
            self._end()
        if substrate:
            self._store_substrate(req, result)
            return result
        self._last_req = req
        self._conclude(result, start_wl=start_wl, end_wl=end_wl, normalize=normalize, check_water=check_water,
                       subtract_substrate=subtract_substrate)
        return result

    # ── resultado ──
    def _conclude(self, result, *, start_wl, end_wl, normalize, check_water, subtract_substrate):
        self.last_result = result
        self._conclude_opts = dict(start_wl=start_wl, end_wl=end_wl, normalize=normalize,
                                   subtract_substrate=subtract_substrate)
        self._raw_wave_steps = [w.wavelength_axis for w in result.windows]
        self._raw_spec_steps = self._processed_windows(result, subtract_substrate)
        self.sweepFinishedSignal.emit(result)
        if not result.windows:
            self.statusSignal.emit(f"Step & Glue sin datos: {result.detail}")
            return
        if not result.complete:
            # Un resultado incompleto no se cose solo (Ronda 3 §4.3): [Coser lo adquirido] lo hace a pedido.
            self.statusSignal.emit(f"Barrido incompleto ({len(result.windows)} de {len(result.plan.centers)} "
                                   f"ventanas, {result.stop_reason.value}): {result.detail}. Las ventanas están "
                                   f"en disco; [Coser lo adquirido] cose lo que hay.")
            return
        self._last_coverage_gaps = coverage_gaps_nm(self._raw_wave_steps, start_wl, end_wl)
        self._glue_and_emit(start_wl, end_wl, normalize, check_water, incomplete=False)

    @pyqtSlot()
    def glue_acquired(self):
        """[Coser lo adquirido]: cose las ventanas de un barrido incompleto y lo rotula así."""
        res = self.last_result
        if res is None or not res.windows:
            self.statusSignal.emit("No hay ventanas adquiridas para coser.")
            return
        w0 = res.windows[0].center_nm_requested
        w1 = res.windows[-1].center_nm_requested
        self._glue_and_emit(w0 - res.plan.window_nm / 2, w1 + res.plan.window_nm / 2, False, False,
                            incomplete=not res.complete)

    def _glue_and_emit(self, start_wl, end_wl, normalize, check_water, incomplete: bool):
        raw_waves, raw_data = self._raw_wave_steps, self._raw_spec_steps
        is_2d_mode = bool(raw_data) and np.ndim(raw_data[0]) == 2
        if is_2d_mode:
            glued_w, glued_frame = sigmoidal_step_and_glue_2d(raw_waves, raw_data)
            glued_s = np.mean(glued_frame, axis=0)
        else:
            glued_w, glued_s = sigmoidal_step_and_glue(raw_waves, raw_data)
            glued_frame = None
        self._last_frame_2d = glued_frame
        norm_w, norm_s = np.array([]), np.array([])
        if normalize:
            norm_w = glued_w
            if is_2d_mode:
                norm_s = np.mean(self.lamp_calib.normalize_spectrum(glued_w, glued_frame), axis=0)
            else:
                norm_s = self.lamp_calib.normalize_spectrum(glued_w, glued_s)
            target_w, target_s = norm_w, norm_s
        else:
            target_w, target_s = glued_w, glued_s
        wave_fit, spec_fit, lambda_max = fit_signal_polynomial(target_w, target_s, ends_notch=start_wl + 10,
                                                               final_wave=end_wl - 10)
        if len(wave_fit) > 0:
            self.fitFinishedSignal.emit(wave_fit, spec_fit)
        if check_water:
            self.waterReferenceCheckedSignal.emit(self._check_water_reference(target_w, target_s))
        self._last_wave, self._last_spec, self._last_norm = glued_w, glued_s, norm_s
        self.spectrumFinishedSignal.emit(glued_w, glued_s, norm_w, norm_s, lambda_max)
        if incomplete:
            self.statusSignal.emit(f"Cosido INCOMPLETO (ventanas 1-{len(raw_waves)} de "
                                   f"{len(self.last_result.plan.centers) if self.last_result else '?'}).")

    # ── espectro único y sustrato: una exposición real (R4-5) ──
    def _one_exposure(self, exp_time: float):
        read_mode = self.camera.get_read_mode() if hasattr(self.camera, "get_read_mode") else READ_MODE_FVB
        frame = single_exposure(self.camera, ExposureRequest(float(exp_time), frame_shape_for(read_mode)),
                                should_abort=self._abort_event.is_set, on_tick=heartbeat_tick(),
                                is_estopped=_estopped)
        if not isinstance(frame, Frame):
            self.statusSignal.emit(f"⛔ No se pudo adquirir: {frame.detail}")
            return None
        data = np.asarray(frame.data)
        return data

    def _measured_window_nm(self) -> Optional[float]:
        return measured_window_nm(self.spectrometer)

    @pyqtSlot(float, float)
    def measure_single_spectrum(self, lambda_center: float, exp_time: float):
        from pyspectrum.modules.hardware_session import hardware_session
        from pyspectrum.modules.zero_order_service import get_zero_order_service
        from pyspectrum.services.spectrometer_shutter import close_spectrometer_shutter, open_spectrometer_shutter
        if self._refuse_without_dark(exp_time):
            return
        if not hardware_session.acquire_session("Step & Glue — Espectro Único", auto_pause_live=True):
            return
        try:
            ret_g, grating = self.spectrometer.ShamrockGetGrating(DEVICE)
            mv = get_zero_order_service(self.camera, self.spectrometer).move(int(grating), float(lambda_center))
            if not mv.ok:
                self.statusSignal.emit(f"⛔ El espectrógrafo no fue a {lambda_center:.2f} nm: {mv.detail}")
                return
            ret_a, wave_1d = self.spectrometer.get_wavelength_axis_cubic(DEVICE, DETECTOR_WIDTH_PX)
            wave_1d = np.asarray(wave_1d, dtype=np.float64)
            if ret_a != SHAMROCK_SUCCESS or not np.all(np.isfinite(wave_1d)):
                self.statusSignal.emit(f"⛔ No se pudo leer el eje λ del Shamrock (código {ret_a}).")
                return
            open_spectrometer_shutter(self.camera, self.spectrometer)
            try:
                from pyspectrum.services import procedure_background as pb

                def expose(shape, exposure_s):
                    d = self._one_exposure(exposure_s)
                    if d is None:
                        raise pb.DarkError("la exposición del fondo falló")
                    return d
                try:
                    self._single_dark = self.dark_ctl.ensure_with(expose, float(exp_time))   # R4-N
                except pb.DarkError as e:
                    self.statusSignal.emit(f"⛔ Sin fondo: {e}")
                    return
                data = self._one_exposure(exp_time)
            finally:
                close_spectrometer_shutter(self.camera, self.spectrometer)
            if data is None:
                return
            from pyspectrum.modules.routines.routine_dark import corrected
            self._single_raw = np.asarray(data)
            proc = corrected(data, self._single_dark if self.subtract_dark else None)
            spec_1d = proc if proc.ndim == 1 else np.mean(proc, axis=0)
            wave_fit, spec_fit, lambda_max = fit_signal_polynomial(wave_1d, spec_1d, ends_notch=lambda_center - 10,
                                                                   final_wave=wave_1d[-1])
            if len(wave_fit) > 0:
                self.fitFinishedSignal.emit(wave_fit, spec_fit)
            self._last_wave, self._last_spec, self._last_norm = wave_1d, spec_1d, np.array([])
            self.spectrumFinishedSignal.emit(wave_1d, spec_1d, np.array([]), np.array([]), lambda_max)
        finally:
            hardware_session.release_session("Step & Glue — Espectro Único")

    @pyqtSlot(str)
    def save_spectrum(self, filepath: str):
        if len(self._last_wave) == 0:
            print("[Step & Glue] No hay espectro registrado para guardar.")
            return
        try:
            p = Path(filepath)
            from pyspectrum.calibration.repository import correction_header_lines, spectrum_software_correction
            from pyspectrum.services.procedure_background import dark_header_lines
            correction = spectrum_software_correction(self.spectrometer)      # R3-gui §4.6
            run_dark = getattr(self.last_result, "dark", None)
            dark_lines = dark_header_lines(run_dark, None)
            if run_dark is not None:
                dark_lines = [l for l in dark_lines if not l.startswith("background_subtracted")]
                dark_lines.append("background_subtracted: " + ("sí (el espectro cosido es crudo − oscuro)"
                                                               if self.subtract_dark else "no (crudo)"))
                if self.last_result.windows and self.last_result.windows[0].path is not None:
                    dark_lines.append(f"background_folder: {self.last_result.windows[0].path.parent}")
            if p.suffix == ".npz":
                import json
                meta = dict(correction)
                meta["background"] = run_dark.metadata() if run_dark is not None else None
                meta["background_subtracted"] = bool(run_dark is not None and self.subtract_dark)
                np.savez_compressed(p, wavelength=self._last_wave, intensity=self._last_spec, normalized=self._last_norm,
                                    metadata=np.array(json.dumps(meta, ensure_ascii=False)))
            else:
                data = np.column_stack([self._last_wave, self._last_spec])
                header = "Wavelength_nm\tIntensity_Counts"
                if len(self._last_norm) == len(self._last_wave) and len(self._last_norm) > 0:
                    data = np.column_stack([self._last_wave, self._last_spec, self._last_norm])
                    header += "\tNormalized_Intensity"
                # Primero la línea de columnas (formato de Solis: los importadores leen la primera línea)
                header = header + "\n" + "\n".join(correction_header_lines(correction) + dark_lines)
                np.savetxt(p, data, delimiter="\t", header=header, comments="# ", encoding="utf-8")
            print(f"[Step & Glue] Espectro guardado con éxito en: {p}")
        except Exception as e:
            print(f"[Step & Glue] Error al guardar espectro: {e}")

    @pyqtSlot(str)
    def export_hdf5(self, filepath: str):
        """Exporta el último cosido a HDF5 estructurado: /glued_spectrum, /wavelengths y un
        grupo /raw_steps por cada paso crudo, con metadatos de red, ranura y timestamp."""
        if len(self._last_wave) == 0:
            print("[Step & Glue] No hay cosido registrado para exportar a HDF5.")
            return
        try:
            ret_g, grating = self.spectrometer.ShamrockGetGrating(DEVICE)
            ret_s, slit_width = self.spectrometer.ShamrockGetSlit(DEVICE)
            result = self.last_result
            metadata = {
                "grating": int(grating) if ret_g == SHAMROCK_SUCCESS else -1,
                "grating_name": NAME_GRATINGS[grating - 1] if ret_g == SHAMROCK_SUCCESS and 1 <= grating <= len(NAME_GRATINGS) else "desconocida",
                "slit_width_um": float(slit_width) if ret_s == SHAMROCK_SUCCESS else float("nan"),
                "window_nm": self._last_window_nm,
                "window_source": self._last_window_source or None,
                "coverage_gaps_nm": np.asarray(self._last_coverage_gaps, dtype=np.float64).reshape(-1),
                "complete": bool(result.complete) if result is not None else True,
                "stop_reason": result.stop_reason.value if result is not None else "",
                "open_lasers_per_window": [",".join(w.open_lasers) for w in result.windows] if result is not None else [],
            }
            # /glued_spectrum es la matriz 2D completa (H, W_total) cuando el barrido se hizo en
            # modo Imagen; de lo contrario, el vector 1D cosido.
            glued_for_export = self._last_frame_2d if self._last_frame_2d is not None else self._last_spec
            export_step_and_glue_to_hdf5(
                filepath, self._last_wave, glued_for_export,
                self._raw_wave_steps, self._raw_spec_steps, metadata,
            )
            print(f"[Step & Glue] HDF5 estructurado exportado con éxito en: {filepath}")
        except Exception as e:
            print(f"[Step & Glue] Error al exportar HDF5: {e}")

    def _check_water_reference(self, wave: np.ndarray, spec: np.ndarray, laser_nm: float = 532.0) -> str:
        """Ajusta la banda O-H del agua (~3400 cm⁻¹, ~650 nm a 532 nm) sobre el espectro cosido
        para detectar distorsión espectral introducida por el cosido (reutiliza
        pyspectrum/calibration/fit_raman_water.py::fit_signal_raman sin modificarlo)."""
        try:
            _, _, params = fit_signal_raman(wave, spec, ends_notch=wave[0], final_wave=wave[-1], laser_nm=laser_nm)
            amplitude_oh = float(params[3])  # I_2: amplitud de la banda O-H principal (peak1, ~3400 cm⁻¹)
            if amplitude_oh > 50.0:
                return f"✅ Referencia Raman Agua: banda O-H (~3400 cm⁻¹) detectada, amplitud {amplitude_oh:.0f} — cosido sin distorsión aparente."
            return f"⚠️ Referencia Raman Agua: banda O-H (~3400 cm⁻¹) débil o no detectada (amplitud {amplitude_oh:.0f}) — verificar el cosido."
        except Exception as e:
            return f"⚠️ No se pudo verificar la referencia Raman de agua: {e}"
