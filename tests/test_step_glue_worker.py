# -*- coding: utf-8 -*-
"""Step & Glue en su propio hilo (paso 11; R2-arq §7.2, R2-inst §5.1 G1/G2/G6; Ronda 3 §1.9.2).

- El barrido corre en un QThread: la GUI sigue respondiendo (V7).
- Stop responde en el tramo siguiente, y la E-STOP corta a mitad de exposición.
- La rutina toma la sesión con la pausa del Live, abre el obturador del espectrómetro al empezar y lo
  cierra al terminar (R4-H-2, G6).
- Con bloqueantes en el preflight no se toma la sesión ni se abre nada.
"""
import os
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYPRINTING_SAFE", "1")

import pytest
from PyQt6 import QtWidgets

from pyspectrum.drivers.andor_ccd_driver import READ_MODE_FVB, get_andor_ccd
from pyspectrum.drivers.shamrock_driver import get_shamrock
from pyspectrum.modules import step_glue_engine as eng
from pyspectrum.modules.hardware_session import hardware_session
from pyspectrum.modules.step_and_glue import Backend
from pyspectrum.modules.step_glue_engine import StopReason

_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["pytest"])


def _wait(pred, timeout=30.0):
    t0 = time.monotonic()
    while not pred():
        _app.processEvents()
        if time.monotonic() - t0 > timeout:
            return False
        time.sleep(0.01)
    return True


@pytest.fixture
def be(tmp_path, monkeypatch):
    hardware_session.clear_emergency()
    cam = get_andor_ccd(force_mock=True)
    cam.abort_acquisition()
    cam.set_read_mode(READ_MODE_FVB)
    spec = get_shamrock(force_mock=True)
    b = Backend(cam, spec)
    b.data_dir = tmp_path
    shutter = []
    monkeypatch.setattr("pyspectrum.services.spectrometer_shutter.open_spectrometer_shutter",
                        lambda c, s: shutter.append("open") or type("R", (), {"ok": True, "detail": ""})())
    monkeypatch.setattr("pyspectrum.services.spectrometer_shutter.close_spectrometer_shutter",
                        lambda c, s: shutter.append("close") or type("R", (), {"ok": True, "detail": ""})())
    b._shutter_log = shutter
    yield b
    hardware_session.clear_emergency()


def _done(b):
    got = []
    b.sweepFinishedSignal.connect(got.append)
    return got


def test_sweep_runs_off_the_gui_thread_and_manages_session_and_shutter(be, monkeypatch):
    threads = []
    real = eng.single_exposure
    monkeypatch.setattr(eng, "single_exposure", lambda *a, **k: threads.append(threading.get_ident()) or real(*a, **k))
    got = _done(be)
    be.start_sweep(500.0, 700.0, 0.2, 0.01, False)
    assert hardware_session.current_owner == "Step & Glue"
    assert _wait(lambda: got)
    res = got[0]
    assert res.complete and res.stop_reason == StopReason.COMPLETED
    assert threads and all(t != threading.get_ident() for t in threads)
    # La rutina abre una vez y cierra al final. Antes puede haber un "close": el de un Live registrado
    # que la sesión pausa (comportamiento correcto del Live).
    assert be._shutter_log.count("open") == 1 and be._shutter_log[-2:] == ["open", "close"]
    assert not hardware_session.is_busy


def test_stop_responds_within_a_tranche(be):
    got = _done(be)
    be.start_sweep(500.0, 900.0, 0.2, 5.0, False)
    time.sleep(0.3)
    t0 = time.monotonic()
    be.stop_measurement()
    assert _wait(lambda: got, timeout=5.0)
    assert time.monotonic() - t0 < 1.5
    assert got[0].stop_reason == StopReason.USER_STOP and not got[0].complete


def test_estop_mid_exposure(be):
    got = _done(be)
    be.start_sweep(500.0, 900.0, 0.2, 5.0, False)
    time.sleep(0.3)
    hardware_session._emergency_active = True
    assert _wait(lambda: got, timeout=5.0)
    assert got[0].stop_reason == StopReason.ESTOP


def test_blockers_take_nothing(be):
    got = _done(be)
    reports = []
    be.preflightSignal.connect(reports.append)
    be.start_sweep(0.0, 60.0, 0.2, 0.01, False)          # ventana especular
    assert reports and reports[-1].blockers
    assert not hardware_session.is_busy and "open" not in be._shutter_log and got == []
