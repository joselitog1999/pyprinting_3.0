# -*- coding: utf-8 -*-
"""Pestaña 5 → "Calibración de λ (automática)" (paso 14d del bloque A, DEC-040; R3-gui §1.6, §2.3, §3.1,
§4.2, §4.4).

- **Preparación:** redes, fuente de la referencia, λ_ref en aire con su origen y su u (vacía = sin dato),
  las dos confirmaciones del operador (notch y espejo; se destildan al terminar), modo SÓLO MEDIR fijo.
- **Corrida:** en su propio hilo, con la sesión "Calibración λ" tomada (pausa el Live). Cancelar y la E-STOP
  la detienen en el tramo siguiente; lo medido se guarda como CANCELADA.
- **Resultado:** una fila por red con K1-K7 y el veredicto (§4.4). [Aplicar corrección fina] sólo con
  ACEPTADA o CON RESERVA; [Proponer offset…] abre la transacción del paso 10 sólo si hay px/paso.
- **Semilla (D-05):** si no se vio la línea, un clic sobre el perfil fija dónde buscar y [Reintentar con la
  semilla] corre esa red otra vez; el registro lleva SEEDED_BY_OPERATOR.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import numpy as np
import pyqtgraph as pg
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import pyqtSignal, pyqtSlot

from pyspectrum.calibration.offset_calibration import (AutoCalibrationPlan, CalibrationRun, GratingCalibration,
                                                       OffsetCalibrationConfig, run_auto_calibration)
from pyspectrum.calibration.repository import CalibrationVerdict, apply_fine_correction

SESSION_NAME = "Calibración λ"
VERDICT_STYLE = {
    CalibrationVerdict.ACEPTADA: ("#a6e3a1", "ACEPTADA (criterios PROVISORIOS)"),
    CalibrationVerdict.ACEPTADA_CON_RESERVA: ("#f9e2af", "CON RESERVA: U no declarada (faltan #5, #6, #7)"),
    CalibrationVerdict.EN_SECO: ("#89b4fa", "SÓLO MEDIDA"),
    CalibrationVerdict.RECHAZADA: ("#f38ba8", "RECHAZADA"),
    CalibrationVerdict.CANCELADA: ("#a6adc8", "cancelada"),
}
K_NAMES = ("K1", "K3", "K4", "K5", "K6", "K7")


class AutoCalibrationWorker(QtCore.QObject):
    progress = pyqtSignal(object)
    finished = pyqtSignal(object)

    def __init__(self, port, plan, repo, data_dir, abort: threading.Event, seed=None):
        super().__init__()
        self.port, self.plan, self.repo, self.data_dir, self._abort, self.seed = port, plan, repo, data_dir, abort, seed

    @pyqtSlot()
    def run(self):
        from pyspectrum.modules.hardware_session import hardware_session
        try:
            run = run_auto_calibration(self.port, self.plan, self.repo, data_dir=self.data_dir,
                                       should_abort=lambda: self._abort.is_set() or hardware_session.is_emergency_stopped,
                                       on_progress=self.progress.emit, seed=self.seed)
        except Exception as e:                       # nunca un hilo que muere en silencio
            run = CalibrationRun(blockers=[f"Error inesperado en la calibración: {e}"])
        self.finished.emit(run)


class AutoCalibrationController(QtCore.QObject):
    """Toma la sesión, arma el puerto y corre el worker en su hilo (R2-arq §2.7)."""
    progress = pyqtSignal(object)
    runFinished = pyqtSignal(object)
    statusSignal = pyqtSignal(str)

    def __init__(self, camera=None, spectrometer=None, *, port_factory: Optional[Callable[[], Any]] = None,
                 repository=None, data_dir: Optional[Path] = None, parent=None):
        super().__init__(parent)
        self.camera, self.spectrometer = camera, spectrometer
        self._port_factory = port_factory
        self._repo = repository
        base = os.getenv("PYSPECTRUM_ROUTINE_DATA_DIR") or str(Path.home() / "Documents" / "Data_PySpectrum")
        self.data_dir = Path(data_dir) if data_dir else Path(base) / "calibration"
        self._abort = threading.Event()
        self._thread: Optional[QtCore.QThread] = None
        self._worker: Optional[AutoCalibrationWorker] = None
        self.last_run: Optional[CalibrationRun] = None
        self._last_plan: Optional[AutoCalibrationPlan] = None

    @property
    def running(self) -> bool:
        return self._thread is not None

    @property
    def repository(self):
        if self._repo is None:
            from pyspectrum.calibration.repository import get_repository
            return get_repository()
        return self._repo

    def _port(self):
        if self._port_factory is not None:
            return self._port_factory()
        from pyspectrum.calibration.offset_calibration import PySpectrumCalibrationPort
        return PySpectrumCalibrationPort(self.camera, self.spectrometer)

    def start(self, plan: AutoCalibrationPlan, seed=None) -> bool:
        from pyspectrum.modules.hardware_session import hardware_session
        if self._thread is not None:
            self.statusSignal.emit("Ya hay una calibración en curso.")
            return False
        if not hardware_session.acquire_session(SESSION_NAME, auto_pause_live=True):
            self.statusSignal.emit("La calibración no arrancó: el hardware está ocupado o la E-STOP está activa.")
            return False
        self.last_run = None
        self._last_plan = plan
        self._abort.clear()
        self._thread = QtCore.QThread()
        self._worker = AutoCalibrationWorker(self._port(), plan, self.repository, self.data_dir, self._abort, seed)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self.progress.emit)
        self._worker.finished.connect(self._on_finished)
        self._thread.start()
        return True

    def cancel(self):
        self._abort.set()

    @pyqtSlot(object)
    def _on_finished(self, run: CalibrationRun):
        from pyspectrum.modules.hardware_session import hardware_session
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(3000)
        self._thread, self._worker = None, None
        hardware_session.release_session(SESSION_NAME, restore_live=False)
        self.last_run = run
        self.runFinished.emit(run)

    def shutdown(self, timeout_ms: int = 3000):
        """Cierre de PySpectrum (paso 13): cancela, espera con tope y guarda lo medido."""
        from pyspectrum.services.shutdown import ShutdownStep
        self._abort.set()
        if self._thread is None:
            return ShutdownStep("calibración λ", True, "sin calibración en curso")
        self._thread.quit()
        ok = self._thread.wait(timeout_ms)
        return ShutdownStep("calibración λ", bool(ok), "cancelada; lo medido quedó en el archivo" if ok
                            else f"el hilo de la calibración no terminó en {timeout_ms / 1000:g} s")


class AutoCalibrationPanel(QtWidgets.QWidget):
    def __init__(self, controller: AutoCalibrationController, parent=None):
        super().__init__(parent)
        self.controller = controller
        self._results: Dict[int, GratingCalibration] = {}
        self._seed: Optional[Dict[int, Any]] = None
        self._needs_seed_grating: Optional[int] = None
        self._build()
        controller.progress.connect(self._on_progress)
        controller.runFinished.connect(self._on_finished)
        controller.statusSignal.connect(self.lbl_status.setText)
        self._sync_mirror_from_belief()
        self._update_start_enabled()

    # ── construcción ──
    def _build(self):
        root = QtWidgets.QHBoxLayout(self)
        left = QtWidgets.QVBoxLayout()
        prep = QtWidgets.QGroupBox("Preparación")
        form = QtWidgets.QFormLayout(prep)
        self.chk_g1 = QtWidgets.QCheckBox("1 · 150 l/mm")
        self.chk_g2 = QtWidgets.QCheckBox("2 · 1200 l/mm")
        for c in (self.chk_g1, self.chk_g2):
            c.setChecked(True)
            c.toggled.connect(self._update_start_enabled)
        grat = QtWidgets.QHBoxLayout()
        grat.addWidget(self.chk_g1)
        grat.addWidget(self.chk_g2)
        form.addRow("Redes", grat)
        self.radio_leak = QtWidgets.QRadioButton("fuga del 532 por el notch")
        self.radio_attenuated = QtWidgets.QRadioButton("532 atenuado, sin notch")
        self.radio_leak.setChecked(True)
        self.radio_leak.toggled.connect(self._on_source_changed)
        src = QtWidgets.QVBoxLayout()
        src.addWidget(self.radio_leak)
        src.addWidget(self.radio_attenuated)
        form.addRow("Fuente", src)
        self.spin_lref = QtWidgets.QDoubleSpinBox()
        self.spin_lref.setRange(500.0, 560.0)
        self.spin_lref.setDecimals(3)
        self.spin_lref.setSingleStep(0.001)
        self.spin_lref.setValue(532.0)
        self.spin_lref.setSuffix(" nm (en aire)")
        self.spin_lref.setToolTip("λ del láser de referencia en aire. Sin un valor medido, la exactitud absoluta "
                                  "del eje es la de este número, que no tiene incertidumbre conocida (R2-met §3.4).")
        form.addRow("λ ref.", self.spin_lref)
        self.combo_source = QtWidgets.QComboBox()
        self.combo_source.setEditable(True)
        self.combo_source.addItems(["nominal, sin medir", "etiqueta del láser", "medida con…"])
        form.addRow("origen", self.combo_source)
        self.spin_ulref = QtWidgets.QDoubleSpinBox()
        self.spin_ulref.setRange(0.0, 1.0)
        self.spin_ulref.setDecimals(3)
        self.spin_ulref.setSingleStep(0.001)
        self.spin_ulref.setSpecialValueText("— (sin dato)")
        self.spin_ulref.setSuffix(" nm")
        form.addRow("u(λ ref.)", self.spin_ulref)
        self.chk_notch = QtWidgets.QCheckBox("notch puesto")
        self.chk_mirror = QtWidgets.QCheckBox("espejo de detección abajo")
        for c in (self.chk_notch, self.chk_mirror):
            c.toggled.connect(self._update_start_enabled)
        conf = QtWidgets.QVBoxLayout()
        conf.addWidget(self.chk_notch)
        conf.addWidget(self.chk_mirror)
        form.addRow("Confirmo", conf)
        self.lbl_auto = QtWidgets.QLabel("Automático (preflight): ganancia EM 0 releída, filtro de densidad en "
                                         "baja, geometría 1004 × 8 µm.")
        self.lbl_auto.setWordWrap(True)
        form.addRow(self.lbl_auto)
        self.lbl_mode = QtWidgets.QLabel("Modo: SÓLO MEDIR (la escritura se habilita tras BANCO-40)")
        self.lbl_mode.setStyleSheet("color: #89b4fa; font-weight: bold;")
        form.addRow(self.lbl_mode)
        left.addWidget(prep)

        adv = QtWidgets.QGroupBox("Avanzado")
        adv.setCheckable(True)
        adv.setChecked(False)
        af = QtWidgets.QFormLayout(adv)
        self.chk_walk = QtWidgets.QCheckBox("recorrer la línea a ±0.35 W (K4, K5)")
        self.chk_walk.setChecked(True)
        af.addRow(self.chk_walk)
        self.spin_frames = self._spin(3, 10, 5)
        self.spin_darks = self._spin(3, 10, 5)
        self.spin_per_iter = self._spin(2, 9, 4)
        self.spin_final_min = self._spin(3, 50, 9)
        self.spin_final_max = self._spin(3, 50, 25)
        self.spin_final_min.valueChanged.connect(lambda v: self.spin_final_max.setMinimum(v))
        af.addRow("cuadros por llegada", self.spin_frames)
        af.addRow("cuadros de oscuro", self.spin_darks)
        af.addRow("llegadas del recorrido", self.spin_per_iter)
        af.addRow("llegadas finales, mínimo", self.spin_final_min)
        af.addRow("llegadas finales, máximo", self.spin_final_max)
        left.addWidget(adv)

        btns = QtWidgets.QHBoxLayout()
        self.btn_start = QtWidgets.QPushButton("Iniciar calibración")
        self.btn_cancel = QtWidgets.QPushButton("Cancelar")
        self.btn_cancel.setEnabled(False)
        self.btn_start.clicked.connect(self._on_start)
        self.btn_cancel.clicked.connect(self._on_cancel)
        btns.addWidget(self.btn_start)
        btns.addWidget(self.btn_cancel)
        left.addLayout(btns)
        self.lbl_progress = QtWidgets.QLabel("")
        self.lbl_status = QtWidgets.QLabel("")
        self.lbl_status.setWordWrap(True)
        left.addWidget(self.lbl_progress)
        left.addWidget(self.lbl_status)
        left.addStretch(1)
        lw = QtWidgets.QWidget()
        lw.setLayout(left)
        lw.setMaximumWidth(360)
        root.addWidget(lw)

        right = QtWidgets.QVBoxLayout()
        self.plot_profile = pg.PlotWidget(title="Perfil de la línea")
        self.plot_profile.setLabel("bottom", "píxel")
        self.plot_profile.setLabel("left", "cuentas (oscuro restado)")
        self.curve_profile = self.plot_profile.plot(pen=pg.mkPen("#74c7ec", width=1.5), stepMode="center")
        self.line_xhat = pg.InfiniteLine(angle=90, pen=pg.mkPen("#cba6f7", width=2))
        self.line_pref = pg.InfiniteLine(angle=90, pen=pg.mkPen("#a6e3a1", width=2, style=QtCore.Qt.PenStyle.DashLine))
        self.region_window = pg.LinearRegionItem(movable=False, brush=pg.mkBrush(203, 166, 247, 25))
        self.text_r = pg.TextItem(color="#f9e2af")
        for item in (self.region_window, self.line_xhat, self.line_pref, self.text_r):
            self.plot_profile.addItem(item)
        self.plot_profile.scene().sigMouseClicked.connect(self._on_profile_clicked)
        right.addWidget(self.plot_profile, 3)
        self.plot_arrivals = pg.PlotWidget(title="Llegadas: residuo por llegada (px)")
        self.scatter_arrivals = pg.ScatterPlotItem(size=7, brush=pg.mkBrush("#89b4fa"))
        self.plot_arrivals.addItem(self.scatter_arrivals)
        right.addWidget(self.plot_arrivals, 2)
        self.table = QtWidgets.QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Red", "Offset", "residuo r (px)", "corrección fina (px)",
                                              "K1…K7", "Veredicto"])
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._update_result_buttons)
        right.addWidget(self.table, 2)
        rb = QtWidgets.QHBoxLayout()
        self.btn_fine = QtWidgets.QPushButton("Aplicar corrección fina")
        self.btn_fine.setToolTip("Guarda la corrección fina (sólo PySpectrum) en el archivo. No escribe al equipo.")
        self.btn_propose = QtWidgets.QPushButton("Proponer offset…")
        self.btn_verify = QtWidgets.QPushButton("Verificar")
        self.btn_seed = QtWidgets.QPushButton("Reintentar con la semilla")
        self.btn_fine.clicked.connect(self._on_fine)
        self.btn_propose.clicked.connect(self._on_propose)
        self.btn_verify.clicked.connect(self._on_start)
        self.btn_seed.clicked.connect(self._on_retry_seed)
        for b in (self.btn_fine, self.btn_propose, self.btn_verify, self.btn_seed):
            b.setEnabled(False)
            rb.addWidget(b)
        right.addLayout(rb)
        self.lbl_propose = QtWidgets.QLabel("")
        self.lbl_propose.setWordWrap(True)
        right.addWidget(self.lbl_propose)
        root.addLayout(right, 1)

    @staticmethod
    def _spin(lo, hi, val):
        s = QtWidgets.QSpinBox()
        s.setRange(lo, hi)
        s.setValue(val)
        return s

    # ── estado de los controles ──
    def _sync_mirror_from_belief(self):
        try:
            from core.nidaq import get_detection_mirror_belief
            b = get_detection_mirror_belief()
            down = b.position == "down"
        except Exception:
            down = False
        self.chk_mirror.setChecked(down)
        self.chk_mirror.setText("espejo de detección abajo" + (" (según el software)" if down else ""))

    def _on_source_changed(self):
        leak = self.radio_leak.isChecked()
        self.chk_notch.setText("notch puesto" if leak else "notch retirado, 532 atenuado")
        self.chk_notch.setChecked(False)

    def _update_start_enabled(self, *_):
        ok = (self.chk_notch.isChecked() and self.chk_mirror.isChecked()
              and (self.chk_g1.isChecked() or self.chk_g2.isChecked()) and not self.controller.running)
        self.btn_start.setEnabled(ok)
        self.btn_verify.setEnabled(ok and bool(self._results))

    def build_plan(self) -> AutoCalibrationPlan:
        gratings = [g for g, c in ((1, self.chk_g1), (2, self.chk_g2)) if c.isChecked()]
        u = self.spin_ulref.value()
        cfgs = tuple(OffsetCalibrationConfig(
            grating=g, lambda_ref_nm=round(self.spin_lref.value(), 3),
            lambda_ref_source=self.combo_source.currentText().strip() or "nominal, sin medir",
            u_lambda_ref_nm=None if u <= self.spin_ulref.minimum() else u,
            frames_per_arrival=self.spin_frames.value(), dark_frames=self.spin_darks.value(),
            arrivals_per_iteration=self.spin_per_iter.value(), arrivals_final_min=self.spin_final_min.value(),
            arrivals_final_max=self.spin_final_max.value(), walk=self.chk_walk.isChecked()) for g in gratings)
        mode = "notch_leak" if self.radio_leak.isChecked() else "attenuated_no_notch"
        confirmed = set()
        if self.chk_notch.isChecked():
            confirmed.add("notch_at_input" if mode == "notch_leak" else "notch_removed_attenuated")
        if self.chk_mirror.isChecked():
            confirmed.add("detection_mirror_down")
        return AutoCalibrationPlan(configs=cfgs, reference_mode=mode, operator_confirmed=frozenset(confirmed))

    # ── acciones ──
    def _on_start(self, seed=None):
        if self.controller.start(self.build_plan(), seed=seed if isinstance(seed, dict) else None):
            self._results.clear()
            self.table.setRowCount(0)
            self.scatter_arrivals.clear()
            self.btn_start.setEnabled(False)
            self.btn_cancel.setEnabled(True)
            self.lbl_status.setText("Calibrando… Cancelar detiene y guarda lo medido.")

    def _on_cancel(self):
        self.controller.cancel()
        self.lbl_status.setText("Cancelando: se cierra el 532 y se guarda lo medido.")

    @pyqtSlot(object)
    def _on_progress(self, info: Dict[str, Any]):
        a = info.get("arrival")
        prof = info.get("profile")
        if prof is not None:
            x = np.arange(prof.size + 1) - 0.5
            self.curve_profile.setData(x, np.asarray(prof))
        if a is not None:
            self.line_xhat.setValue(a.x_hat_px)
            self.line_pref.setValue(a.p_ref_px)
            self.text_r.setText(f"r = {a.r_px:+.2f} px = {a.r_px * a.d_nm_per_px:+.4f} nm")
            self.text_r.setPos(a.x_hat_px, float(np.max(prof)) if prof is not None else 0.0)
            self.scatter_arrivals.addPoints([len(self.scatter_arrivals.data)], [a.r_px])
        w = info.get("window_px")
        if w:
            self.region_window.setRegion(w)
        self.lbl_progress.setText(f"Red {info.get('grating')} · λc {info.get('lambda_c_nm', 0):.2f} nm · "
                                  f"llegada {info.get('n', 0)} de ≤ {info.get('n_max', 0)}"
                                  + (f" · {info['stage']}" if info.get("stage") else ""))

    @pyqtSlot(object)
    def _on_finished(self, run: CalibrationRun):
        self.btn_cancel.setEnabled(False)
        self.chk_notch.setChecked(False)          # las confirmaciones no se recuerdan (§1.6)
        self.chk_mirror.setChecked(False)
        self._update_start_enabled()
        if run.blockers:
            self.lbl_status.setText("⛔ No arrancó: " + " ".join(run.blockers))
            return
        self._needs_seed_grating = None
        for g in run.gratings:
            self._results[g.grating] = g
            self._add_row(g)
            if g.needs_seed:
                self._needs_seed_grating = g.grating
        text = ("⚠️ " + run.abort_reason) if run.aborted else "Calibración terminada. Nada se escribió al equipo."
        if run.warnings:
            text += "  " + " ".join(run.warnings)
        if self._needs_seed_grating is not None:
            text += "  No se detectó la línea: hacé clic sobre ella en el perfil y usá [Reintentar con la semilla]."
        self.lbl_status.setText(text)
        if self.table.rowCount():
            self.table.selectRow(0)
        self._update_result_buttons()

    def _add_row(self, g: GratingCalibration):
        row = self.table.rowCount()
        self.table.insertRow(row)
        color, label = VERDICT_STYLE[g.verdict]
        marks = "".join("✓" if (g.checks.get(k, (None,))[0] is True) else ("✗" if g.checks.get(k, (None,))[0] is False
                                                                          else "·") for k in K_NAMES)
        r = f"{g.r_hw_px:+.2f} ± {g.u_r_hw_px:.2f}" if np.isfinite(g.r_hw_px) else "—"
        c = f"{g.c_sw_px:+.2f}" if np.isfinite(g.c_sw_px) else "—"
        verdict = label if g.verdict is not CalibrationVerdict.CANCELADA else f"cancelada tras {len(g.arrivals)} llegadas"
        items = [str(g.grating), "—" if g.offset_read is None else str(g.offset_read), r, c, marks, verdict]
        tip = "\n".join(f"{k}: {v[1]} (umbral {v[2]}; PROVISORIO)" for k, v in g.checks.items()) or "\n".join(g.reasons)
        for col, text in enumerate(items):
            it = QtWidgets.QTableWidgetItem(text)
            it.setToolTip(tip + ("\n" + "\n".join(g.reasons) if g.reasons else ""))
            if col == 5:
                it.setForeground(QtGui.QColor(color))
            self.table.setItem(row, col, it)

    def _selected(self) -> Optional[GratingCalibration]:
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not rows:
            return None
        return self._results.get(int(self.table.item(rows[0].row(), 0).text()))

    def _update_result_buttons(self):
        g = self._selected()
        fine_ok = g is not None and g.verdict in (CalibrationVerdict.ACEPTADA, CalibrationVerdict.ACEPTADA_CON_RESERVA)
        self.btn_fine.setEnabled(bool(fine_ok) and not self.controller.running)
        can_propose = fine_ok and g.proposed_offset is not None
        self.btn_propose.setEnabled(bool(can_propose))
        if g is None:
            self.lbl_propose.setText("")
        elif g.proposed_offset is None:
            self.lbl_propose.setText("Proponer offset: deshabilitado, falta px/paso (BANCO-40).")
        else:
            self.lbl_propose.setText(f"Propuesta: {g.offset_read} → {g.proposed_offset} pasos ({g.proposal_reason}).")
        self.btn_seed.setEnabled(self._needs_seed_grating is not None and self._seed is not None)

    def _on_fine(self):
        g = self._selected()
        if g is None:
            return
        entry = next((e for e in self.controller.repository.history() if e.record_id == g.record_id), None)
        if entry is None:
            self.lbl_status.setText("No se encontró el registro de esa calibración en el archivo.")
            return
        try:
            sc = apply_fine_correction(self.controller.repository, entry)
        except ValueError as e:
            self.lbl_status.setText(f"⛔ {e}")
            return
        self.lbl_status.setText(f"Corrección fina de la red {g.grating} guardada ({g.c_sw_px:+.2f} px, "
                                f"registro {sc.record_id[:8]}). No se escribió nada al equipo.")

    def _on_propose(self):
        g = self._selected()
        if g is None or g.proposed_offset is None:
            return
        from pyspectrum.calibration.offset_transaction import OffsetWriteTransaction
        from pyspectrum.ui.offset_write_dialog import OffsetWriteDialog
        ctrl = self.controller
        factory = lambda: OffsetWriteTransaction(ctrl.spectrometer, ctrl.camera, ctrl.repository, grating=g.grating,
                                                 requested_offset=int(g.proposed_offset),
                                                 source_record_id=g.record_id)
        from pyspectrum.modules.hardware_session import hardware_session
        OffsetWriteDialog(factory, estop_callback=hardware_session.emergency_stop, parent=self).exec()

    def _on_profile_clicked(self, ev):
        if self._needs_seed_grating is None:
            return
        pos = self.plot_profile.plotItem.vb.mapSceneToView(ev.scenePos())
        x = float(pos.x())
        self._seed = {self._needs_seed_grating: (x, (int(x - 15), int(x + 15)))}
        self.line_xhat.setValue(x)
        self.lbl_status.setText(f"Semilla en el píxel {x:.1f}. [Reintentar con la semilla] corre esa red otra vez.")
        self._update_result_buttons()

    def _on_retry_seed(self):
        if self._seed is None:
            return
        g = self._needs_seed_grating
        self.chk_g1.setChecked(g == 1)
        self.chk_g2.setChecked(g == 2)
        self._on_start(seed=self._seed)
        self._seed = None
