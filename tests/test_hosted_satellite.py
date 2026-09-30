# -*- coding: utf-8 -*-
"""PyPrinting como satélite huésped de PySpectrum (paso 13 del bloque A; R2-arq §3.1; V1, V2, V3, V11).

El satélite abierto desde PySpectrum usa los recursos del anfitrión y nunca los crea, reconfigura ni
destruye:
- al abrirse, no conecta la platina (su `connect()` hace home y libera el interlock) ni cambia el perfil;
- al cerrarse, no desconecta la platina (lleva a (0, 0, 0)), no cierra las tareas DAQ ni pulsa el espejo;
- cierra los obturadores (con el resultado), guarda la posición y detiene su cámara en su hilo sólo si
  ese hilo corre.

PyPrinting suelto (`python app.py`) no cambia.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYPRINTING_SAFE", "1")

import config  # noqa: F401 — registra core/modules en sys.path antes de los imports planos
# Import a nivel de módulo, como en test_hardware_session_master_slave: importar app.py dentro de
# un test colgaba bajo pytest (efecto de orden de import con EDSDK).
import app as pyprinting_app
import contrapropagante

import pytest
from PyQt6 import QtCore, QtWidgets

from pyspectrum.modules.hardware_session import hardware_session


class DummyCamera(QtCore.QObject):
    """Reemplaza al CanonWorker: un segundo worker de EDSDK en el mismo proceso de pytest es frágil."""
    closed = 0

    @QtCore.pyqtSlot()
    def close(self):
        DummyCamera.closed += 1

    @QtCore.pyqtSlot(str)
    def set_directory(self, path):
        pass


@pytest.fixture
def calls(monkeypatch, tmp_path):
    log = []
    from core.hardware_manager import hardware_manager
    monkeypatch.setattr(pyprinting_app.pi, "connect", lambda *a, **k: log.append("pi.connect") or True)
    monkeypatch.setattr(pyprinting_app.pi, "disconnect", lambda *a, **k: log.append("pi.disconnect"))
    monkeypatch.setattr(pyprinting_app, "close_all_tasks", lambda *a, **k: log.append("close_all_tasks"))
    monkeypatch.setattr(pyprinting_app, "flipper_notch532", lambda *a, **k: log.append("flipper_notch532"))
    monkeypatch.setattr(pyprinting_app, "close_all_shutters",
                        lambda *a, **k: log.append("close_all_shutters") or True)
    monkeypatch.setattr(hardware_manager, "set_profile", lambda *a, **k: log.append("set_profile"))
    monkeypatch.setattr(pyprinting_app, "CameraBackend", DummyCamera)
    monkeypatch.setattr(pyprinting_app, "LAST_POS_FILE", tmp_path / "Last_position.txt")
    DummyCamera.closed = 0
    hardware_session.clear_emergency()
    yield log
    hardware_session.clear_emergency()


HOST = pyprinting_app.HostContext("PySpectrum 3.0")


# Las ventanas con gráficos de pyqtgraph quedan vivas hasta el final de la sesión: si el recolector
# destruye una, su ViewBox con nombre queda registrado en pyqtgraph y rompe la próxima ImageView.
_KEEP_ALIVE = []


def test_the_hosted_backend_does_not_connect_the_stage_nor_change_the_profile(calls):
    pyprinting_app.Backend(host=HOST)
    assert "pi.connect" not in calls and "set_profile" not in calls, calls


def test_the_standalone_backend_keeps_connecting_as_before(calls):
    pyprinting_app.Backend()
    assert calls[:2] == ["set_profile", "pi.connect"], calls
    assert calls.count("pi.connect") == 4, calls      # app, platina, foco y confocal: como antes


def test_closing_the_hosted_satellite_leaves_stage_daq_and_mirror_to_the_host(calls, tmp_path):
    backend = pyprinting_app.Backend(host=HOST)
    backend.on_frontend_closed()
    assert "close_all_shutters" in calls
    for forbidden in ("pi.disconnect", "close_all_tasks", "flipper_notch532"):
        assert forbidden not in calls, calls
    assert (tmp_path / "Last_position.txt").exists()


def test_release_as_guest_reports_and_runs_once(calls):
    backend = pyprinting_app.Backend(host=HOST)
    report = backend.release_as_guest()
    assert report.shutters_confirmed and not report.problems, report
    again = backend.release_as_guest()
    assert calls.count("close_all_shutters") == 1
    assert again is report


def test_release_never_invokes_into_a_camera_thread_that_is_not_running(calls):
    backend = pyprinting_app.Backend(host=HOST)
    idle = QtCore.QThread()
    backend.cameraWorker.moveToThread(idle)          # hilo nunca arrancado: una llamada bloqueante colgaría
    report = backend.release_as_guest()
    assert DummyCamera.closed == 0
    assert "no corre" in report.camera


def test_release_stops_the_camera_in_its_running_thread(calls):
    backend = pyprinting_app.Backend(host=HOST)
    t = QtCore.QThread()
    backend.cameraWorker.moveToThread(t)
    t.start()
    try:
        backend.release_as_guest()
        assert DummyCamera.closed == 1
    finally:
        t.quit()
        assert t.wait(3000)


def test_a_shutter_close_that_does_not_confirm_is_a_problem(calls, monkeypatch):
    monkeypatch.setattr(pyprinting_app, "close_all_shutters", lambda *a, **k: False)
    report = pyprinting_app.Backend(host=HOST).release_as_guest()
    assert not report.shutters_confirmed
    assert any("obturadores" in p for p in report.problems)


def test_the_standalone_close_is_unchanged(calls):
    backend = pyprinting_app.Backend()
    t = QtCore.QThread()
    backend.cameraWorker.moveToThread(t)      # como en create_app_satellite: close_all invoca en ese hilo
    t.start()
    try:
        backend.close_all()
    finally:
        t.quit()
        assert t.wait(3000)
    for expected in ("close_all_tasks", "flipper_notch532", "pi.disconnect"):
        assert expected in calls, calls


def test_close_from_host_neither_asks_nor_emits(monkeypatch):
    def no_dialog(*a, **k):
        raise AssertionError("el cierre desde el anfitrión no abre un segundo diálogo (V3)")
    monkeypatch.setattr(QtWidgets.QMessageBox, "question", no_dialog)
    gui = pyprinting_app.Frontend()
    _KEEP_ALIVE.append(gui)
    emitted = []
    gui.closeSignal.connect(lambda: emitted.append(1))
    gui.show()
    gui.close_from_host()
    assert not gui.isVisible()
    assert emitted == []


@pytest.fixture
def cp_calls(monkeypatch):
    log = []
    monkeypatch.setattr(contrapropagante.pi, "connect", lambda *a, **k: log.append("pi.connect") or True)
    monkeypatch.setattr(contrapropagante, "CameraBackend", DummyCamera)
    return log


def test_the_hosted_contrapropagante_does_not_connect_the_stage(cp_calls):
    """Decisión del investigador (2026-09-29): el contrapropagante abierto desde PySpectrum también es huésped."""
    backend = contrapropagante.Backend(host=HOST)
    assert cp_calls == [], cp_calls
    assert backend.host is HOST


def test_the_standalone_contrapropagante_keeps_connecting_as_before(cp_calls):
    contrapropagante.Backend()
    assert cp_calls.count("pi.connect") == 3, cp_calls        # el backend, la platina y el foco


def test_the_contrapropagante_window_also_closes_from_host_without_asking(monkeypatch):
    def no_dialog(*a, **k):
        raise AssertionError("el cierre desde el anfitrión no abre un segundo diálogo")
    monkeypatch.setattr(QtWidgets.QMessageBox, "question", no_dialog)
    win = contrapropagante.ContrapropaganteMainWindow()
    _KEEP_ALIVE.append(win)
    emitted = []
    win.closeSignal.connect(lambda: emitted.append(1))
    win.show()
    win.close_from_host()
    assert not win.isVisible() and emitted == []
