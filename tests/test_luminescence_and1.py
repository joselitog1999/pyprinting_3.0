# -*- coding: utf-8 -*-
"""Luminiscencia sobre las primitivas de grilla (AND-1, parte 3; R4-K).

- Sin la confirmación del espejo no arranca (ni toma la sesión).
- Corre en su propio hilo: `start_grid` vuelve enseguida y la GUI sigue respondiendo.
- Cada nodo: una exposición real; el espejo baja antes de abrir el láser; el láser se abre sólo para la
  exposición. Al terminar, el espejo vuelve a donde lo confirmó el operador.
- Un nodo con la exposición fallida queda FALLIDO (con su archivo) y la grilla sigue (P6).
- Una platina que no llega pausa la grilla con los obturadores cerrados (DEC-036).
- Sin carpeta elegida, los datos van a la carpeta de datos de las rutinas, nunca al directorio actual.
- El modo puntual toma una exposición real por cuadro.
"""
import os
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYPRINTING_SAFE", "1")

import pytest
from PyQt6 import QtWidgets

import config
from core import nidaq
from pyspectrum.drivers.andor_ccd_driver import get_andor_ccd
from pyspectrum.drivers.shamrock_driver import get_shamrock
from pyspectrum.modules import acquisition
from pyspectrum.modules.hardware_session import hardware_session
from pyspectrum.modules.routines import luminescence as lm

LASER = config.SHUTTERS[0]


@pytest.fixture
def be(tmp_path, monkeypatch):
    hardware_session.clear_emergency()
    monkeypatch.setattr(lm, "run_z_autofocus", lambda **kw: True)
    b = lm.LuminescenceBackend(get_andor_ccd(force_mock=True), get_shamrock(force_mock=True))
    b.data_dir = str(tmp_path / "lum")
    b.generate_grid(1, 2, 3.0, 0.0, 40.0, 40.0, 5.0)
    yield b
    b.abort_grid()
    b.stop_luminescence()
    b.grid_thread.wait_finished(10)
    b.point_thread.wait_finished(10)
    hardware_session.clear_emergency()
    nidaq.close_all_shutters()


def _cfg(**kw):
    c = {"laser": LASER, "exp_time": 0.02, "autofocus_every": 5, "save_dir": "", "mirror": "up"}
    c.update(kw)
    return c


def test_it_does_not_start_without_the_mirror_confirmation(be):
    be.start_grid(_cfg(mirror=None))
    assert not be._grid_running and not hardware_session.is_busy


def test_it_runs_in_its_own_thread_and_each_node_is_a_real_exposure(be, tmp_path, monkeypatch):
    shapes, log = [], []
    real_exp = acquisition.single_exposure
    monkeypatch.setattr(acquisition, "single_exposure", lambda *a, **k: shapes.append(a[1].shape) or real_exp(*a, **k))
    real_open, real_close, real_mirror = lm.open_shutter, lm.close_shutter, lm.flipper_notch532
    monkeypatch.setattr(lm, "open_shutter", lambda n, *a, **k: log.append(("open", n)) or real_open(n))
    monkeypatch.setattr(lm, "close_shutter", lambda n: log.append(("close", n)) or real_close(n))
    monkeypatch.setattr(lm, "flipper_notch532", lambda p: log.append(("mirror", p)) or real_mirror(p))
    t0 = time.monotonic()
    be.start_grid(_cfg(exp_time=0.3))
    assert time.monotonic() - t0 < 0.3 and be.grid_thread.running       # no bloquea la GUI
    assert be.grid_thread.wait_finished(20)
    assert shapes == [(1004,), (1004,), (1004,)]                  # el fondo de la grilla (R4-N) y los 2 nodos
    assert be.states == [lm.NODE_DONE, lm.NODE_DONE]
    first_open = log.index(("open", LASER))
    assert ("mirror", "down") in log[:first_open]
    for i, e in enumerate(log):
        if e == ("open", LASER):
            assert log[i + 1] == ("close", LASER)                # abierto sólo para la exposición
    assert log[-1] == ("mirror", "up")                           # vuelve a donde lo confirmó el operador
    files = sorted(p.name for p in (tmp_path / "lum").iterdir())
    # el fondo de la grilla, aparte y una sola vez (R4-N, B3), y cada nodo crudo, con su referencia
    assert files[0].startswith("LuminescenceGrid_background_") and files[0].endswith(".npz")
    assert files[1:] == ["LuminescenceNode_000_spectrum.txt", "LuminescenceNode_001_spectrum.txt"]
    dark_id = files[0][len("LuminescenceGrid_background_"):-len(".npz")]
    assert f"background_id: {dark_id}" in (tmp_path / "lum" / files[1]).read_text(encoding="utf-8")
    assert not hardware_session.is_busy


def test_a_failed_exposure_fails_the_node_and_the_grid_goes_on(be, tmp_path, monkeypatch):
    real_exp = acquisition.single_exposure
    count = {"n": 0}

    def flaky(*a, **k):
        count["n"] += 1
        if count["n"] == 2:                                   # la 1.ª es el fondo de la grilla (R4-N)
            return acquisition.AcquisitionFailure(acquisition.AcquisitionFailureKind.TIMEOUT, None, None, "simulada")
        return real_exp(*a, **k)
    monkeypatch.setattr(acquisition, "single_exposure", flaky)
    be.start_grid(_cfg())
    assert be.grid_thread.wait_finished(20)
    assert be.states == [lm.NODE_FAILED, lm.NODE_DONE]
    assert (tmp_path / "lum" / "LuminescenceNode_000_FAILED.txt").exists()
    assert not nidaq.get_open_shutter_names()


def test_a_stage_that_does_not_arrive_pauses_with_the_shutters_closed(be, monkeypatch):
    monkeypatch.setattr(config, "wait_on_target", lambda *a, **k: False)
    msgs = []
    be.statusSignal.connect(msgs.append)
    be.start_grid(_cfg())
    t_end = time.monotonic() + 10
    while not be.grid_thread.ctl.pause.is_set() and time.monotonic() < t_end:
        QtWidgets.QApplication.processEvents()
        time.sleep(0.01)
    assert be.grid_thread.ctl.pause.is_set() and be.grid_thread.running
    QtWidgets.QApplication.processEvents()
    assert any("platina" in m for m in msgs)
    assert not nidaq.get_open_shutter_names()
    be.abort_grid()
    assert be.grid_thread.wait_finished(10) and not hardware_session.is_busy


def test_the_point_mode_takes_one_real_exposure_per_frame(be, monkeypatch):
    shapes = []
    real_exp = acquisition.single_exposure
    monkeypatch.setattr(acquisition, "single_exposure", lambda *a, **k: shapes.append(a[1].shape) or real_exp(*a, **k))
    be.confirm_mirror("down")
    be.start_luminescence(LASER, 0.02, 3, 0.05)
    assert be.point_thread.wait_finished(20)
    assert shapes == [(1004,)] * 4 and len(be.i_points) == 3      # el fondo de la serie (R4-N) y 3 cuadros
    assert LASER not in nidaq.get_open_shutter_names()


def test_the_point_mode_needs_the_mirror_confirmation(be):
    be.start_luminescence(LASER, 0.02, 3, 0.05)
    assert not be.point_thread.running and not hardware_session.is_busy


def test_the_spectrometer_shutter_opens_for_the_routine_and_closes_at_the_end(be, monkeypatch):
    log = []
    ok = type("R", (), {"ok": True, "detail": ""})()
    monkeypatch.setattr("pyspectrum.services.spectrometer_shutter.open_spectrometer_shutter",
                        lambda c, s: log.append("open") or ok)
    monkeypatch.setattr("pyspectrum.services.spectrometer_shutter.close_spectrometer_shutter",
                        lambda c, s: log.append("close") or ok)
    be.start_grid(_cfg())
    assert be.grid_thread.wait_finished(20)
    # un Live pausado por la sesión puede agregar cierres propios
    assert "open" in log and log[-1] == "close" and log.index("open") < len(log) - 1


def test_the_laser_is_already_closed_when_the_node_spectrum_is_reported(be):
    """El láser se abre sólo para la exposición: cuando se informa el espectro del nodo, ya está cerrado."""
    from PyQt6 import QtCore
    states = []
    be.gridSpectrumUpdateSignal.connect(lambda w, s: states.append(LASER in nidaq.get_open_shutter_names()),
                                        QtCore.Qt.ConnectionType.DirectConnection)
    be.start_grid(_cfg())
    assert be.grid_thread.wait_finished(20)
    assert states == [False, False]
