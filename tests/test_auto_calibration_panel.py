# -*- coding: utf-8 -*-
"""Pestaña "Calibración de λ (automática)" (paso 14d; R3-gui §1.6, §2.3, §4.2, §4.4; H-02).

- El plan sale de los widgets con los valores por defecto del diseño; λ_ref en aire; u(λ_ref) vacía = null.
- "Iniciar" exige las dos confirmaciones del operador (notch y espejo), que se destildan al terminar.
- Corre en su propio hilo, con la sesión "Calibración λ" tomada, y la suelta al terminar.
- Una fila por red, con el veredicto como en §4.4. [Aplicar corrección fina] sólo con ACEPTADA o CON RESERVA;
  [Proponer offset…] deshabilitado sin px/paso, con el motivo escrito.
- Cancelar deja la red CANCELADA con lo medido y el 532 cerrado.
- No hay ningún control para salir de SÓLO MEDIR. Ctrl+R no inicia la calibración (H-02).
"""
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYPRINTING_SAFE", "1")

import pytest
from PyQt6 import QtCore, QtWidgets

from pyspectrum.calibration.repository import CalibrationRepository
from pyspectrum.modules.hardware_session import hardware_session
from pyspectrum.ui import auto_calibration_panel as acp
from test_offset_calibration import SimPort

_KEEP_ALIVE = []


def _wait(cond, timeout_s=90.0):
    t_end = time.monotonic() + timeout_s
    while time.monotonic() < t_end:
        QtWidgets.QApplication.processEvents()
        if cond():
            return True
        time.sleep(0.01)
    return False


@pytest.fixture
def panel(tmp_path):
    hardware_session.clear_emergency()
    repo = CalibrationRepository(tmp_path / "cal.jsonl")
    ports = []

    def factory():
        p = SimPort()
        ports.append(p)
        return p
    ctrl = acp.AutoCalibrationController(port_factory=factory, repository=repo, data_dir=tmp_path / "raw")
    w = acp.AutoCalibrationPanel(ctrl)
    _KEEP_ALIVE.append((w, ctrl))
    w.ports, w.repo = ports, repo
    yield w
    ctrl.shutdown()
    hardware_session.release_session(acp.SESSION_NAME)
    hardware_session.clear_emergency()


def _confirm(w):
    w.chk_notch.setChecked(True)
    w.chk_mirror.setChecked(True)


def _small(w):
    w.spin_final_min.setValue(3)
    w.spin_final_max.setValue(3)
    w.spin_per_iter.setValue(2)


def test_the_plan_comes_from_the_widgets_with_the_design_defaults(panel):
    _confirm(panel)
    plan = panel.build_plan()
    assert [c.grating for c in plan.configs] == [1, 2]
    assert plan.reference_mode == "notch_leak"
    c = plan.configs[0]
    assert c.lambda_ref_nm == 532.0 and c.lambda_ref_source == "nominal, sin medir" and c.u_lambda_ref_nm is None
    assert (c.frames_per_arrival, c.dark_frames, c.arrivals_per_iteration) == (5, 5, 4)
    assert (c.arrivals_final_min, c.arrivals_final_max, c.walk) == (9, 25, True)
    assert c.dry_run is True
    assert plan.operator_confirmed == {"notch_at_input", "detection_mirror_down"}


def test_start_needs_both_confirmations(panel):
    panel.chk_mirror.setChecked(False)
    panel.chk_notch.setChecked(False)
    assert not panel.btn_start.isEnabled()
    panel.chk_notch.setChecked(True)
    assert not panel.btn_start.isEnabled()
    panel.chk_mirror.setChecked(True)
    assert panel.btn_start.isEnabled()


def test_the_attenuated_source_changes_the_confirmation(panel):
    panel.radio_attenuated.setChecked(True)
    assert "retirado" in panel.chk_notch.text()
    _confirm(panel)
    assert panel.build_plan().operator_confirmed == {"notch_removed_attenuated", "detection_mirror_down"}


def test_there_is_no_way_out_of_only_measure(panel):
    assert "SÓLO MEDIR" in panel.lbl_mode.text()
    for chk in panel.findChildren(QtWidgets.QCheckBox):
        assert "escrib" not in chk.text().lower() and "seco" not in chk.text().lower(), chk.text()


def test_a_run_fills_the_table_releases_the_session_and_clears_the_confirmations(panel):
    _confirm(panel)
    _small(panel)
    busy = []
    hardware_session.sessionChangedSignal.connect(lambda owner, b: busy.append((owner, b)))
    panel.btn_start.click()
    assert _wait(lambda: panel.controller.last_run is not None)
    assert (acp.SESSION_NAME, True) in busy and not hardware_session.is_busy
    assert panel.table.rowCount() == 2
    assert "CON RESERVA" in panel.table.item(0, 5).text()
    assert not panel.chk_notch.isChecked() and not panel.chk_mirror.isChecked()
    assert panel.ports[-1].laser_open is False


def test_fine_correction_and_the_disabled_proposal(panel):
    _confirm(panel)
    _small(panel)
    panel.btn_start.click()
    assert _wait(lambda: panel.controller.last_run is not None)
    panel.table.selectRow(0)
    assert panel.btn_fine.isEnabled()
    assert not panel.btn_propose.isEnabled() and "BANCO-40" in panel.lbl_propose.text()
    panel.btn_fine.click()
    kinds = [e.kind for e in panel.repo.history()]
    assert kinds.count("SOFTWARE_CORRECTION") == 1


def test_cancel_leaves_the_grating_cancelled_with_the_laser_closed(panel):
    _confirm(panel)
    panel.btn_start.click()
    assert _wait(lambda: panel.controller.running and panel.ports and len(panel.ports[-1].log) > 20)
    panel.btn_cancel.click()
    assert _wait(lambda: panel.controller.last_run is not None)
    assert "cancelada" in panel.table.item(0, 5).text().lower()
    assert panel.ports[-1].laser_open is False and not hardware_session.is_busy


def test_ctrl_r_does_not_start_the_calibration(monkeypatch):
    from pyspectrum.window import PySpectrumWindow, TAB_CALIBRATION
    monkeypatch.setattr(QtWidgets.QMessageBox, "question", lambda *a, **k: QtWidgets.QMessageBox.StandardButton.Yes)
    win = PySpectrumWindow()
    _KEEP_ALIVE.append(win)
    win.tabs_workflow.setCurrentIndex(TAB_CALIBRATION)
    started = []
    monkeypatch.setattr(win.auto_cal_controller, "start", lambda *a, **k: started.append(1))
    win._shortcut_trigger_measurement()
    assert started == []
    assert win.auto_cal_panel is not None
    win.close()
    hardware_session.clear_emergency()


def test_the_closing_question_mentions_a_running_calibration():
    import config
    from pyspectrum.services.shutdown import closing_question_text
    text = closing_question_text(config.PI_HOME_POS, [], ["Hay una calibración en curso: se cancela y se guarda lo medido."])
    assert "calibración en curso" in text
