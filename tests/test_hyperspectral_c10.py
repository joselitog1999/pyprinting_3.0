# -*- coding: utf-8 -*-
"""Mapa hiperespectral sobre las primitivas de grilla (AND-1, parte 2; C-10; R4-K).

- No arranca sin que el operador confirme dónde está el espejo de detección; después la rutina lo baja
  sola y al terminar lo devuelve a donde estaba.
- Cada píxel: la platina confirma la llegada (`wait_on_target`) y se toma una exposición real. Una
  exposición fallida deja el píxel en NaN, marcado, y el mapa sigue. Una platina que no llega detiene
  el mapa con los obturadores cerrados.
- El obturador del espectrómetro se abre al empezar y se cierra al terminar.
- El cubo se guarda en HDF5 en la carpeta de datos (también si se detiene), y `scanFinishedSignal`
  se emite una sola vez.
"""
import os
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYPRINTING_SAFE", "1")

import h5py
import numpy as np
import pytest
from PyQt6 import QtWidgets

import config
from config import SHUTTERS
from core import nidaq
from pyspectrum.drivers.andor_ccd_driver import get_andor_ccd
from pyspectrum.drivers.shamrock_driver import get_shamrock
from pyspectrum.modules import acquisition
from pyspectrum.modules import hyperspectral_confocal as hc
from pyspectrum.modules.hardware_session import hardware_session


def _run(be, timeout_s=30.0):
    t_end = time.monotonic() + timeout_s
    while be._scanning and time.monotonic() < t_end:
        be._scan_step()
    QtWidgets.QApplication.processEvents()


@pytest.fixture
def be(tmp_path, monkeypatch):
    hardware_session.clear_emergency()
    b = hc.Backend(get_andor_ccd(force_mock=True), get_shamrock(force_mock=True))
    b.data_dir = tmp_path
    b.scan_timer.stop()
    monkeypatch.setattr(b.scan_timer, "start", lambda *a: None)     # los pasos los da el test
    yield b
    b.stop_scan()
    hardware_session.release_session("Mapeo Confocal")
    hardware_session.clear_emergency()
    nidaq.close_all_shutters()


def test_it_does_not_start_without_the_operator_confirming_the_mirror(be):
    be.start_scan(45.0, 46.0, 45.0, 46.0, 1.0, 0.01, SHUTTERS[0])
    assert not be._scanning and not hardware_session.is_busy
    assert SHUTTERS[0] not in nidaq.get_open_shutter_names()


def test_every_pixel_waits_for_the_stage_and_takes_a_real_exposure(be, tmp_path, monkeypatch):
    waits, exposures = [], []
    real_wait, real_exp = config.wait_on_target, acquisition.single_exposure
    monkeypatch.setattr(config, "wait_on_target", lambda *a, **k: waits.append(a) or real_wait(*a, **k))
    monkeypatch.setattr(acquisition, "single_exposure", lambda *a, **k: exposures.append(a[1].shape) or real_exp(*a, **k))
    finished = []
    be.scanFinishedSignal.connect(lambda: finished.append(1))
    be.confirm_mirror("up")
    be.start_scan(45.0, 46.0, 45.0, 47.0, 1.0, 0.01, SHUTTERS[0])
    assert be._scanning
    _run(be)
    assert len(waits) == 6 and exposures == [(1004,)] * 6
    assert finished == [1]
    files = list(Path(tmp_path).glob("*.h5"))
    assert len(files) == 1
    with h5py.File(files[0], "r") as f:
        assert f["cube"].shape == (2, 3, 1004)
        assert f["x_um"][:].tolist() == [45.0, 46.0] and f["y_um"][:].tolist() == [45.0, 46.0, 47.0]
        assert f["wavelength_nm"].shape == (1004,)
        assert f.attrs["complete"] and not f["failed"][:].any()
        assert f.attrs["read_mode"] == "FVB" and f.attrs["exposure_s"] == 0.01


def test_the_mirror_goes_down_before_the_laser_and_comes_back_at_the_end(be, monkeypatch):
    log = []
    real_mirror, real_open = nidaq.flipper_notch532, nidaq.open_shutter
    monkeypatch.setattr(nidaq, "flipper_notch532", lambda p: log.append(("mirror", p)) or real_mirror(p))
    monkeypatch.setattr(nidaq, "open_shutter", lambda n, *a, **k: log.append(("open", n)) or real_open(n, *a, **k))
    be.confirm_mirror("up")
    be.start_scan(45.0, 45.0, 45.0, 45.0, 1.0, 0.01, SHUTTERS[0])
    _run(be)
    assert log.index(("mirror", "down")) < log.index(("open", SHUTTERS[0]))
    assert log[-1] == ("mirror", "up")
    assert SHUTTERS[0] not in nidaq.get_open_shutter_names()


def test_a_failed_exposure_marks_the_pixel_and_the_map_goes_on(be, tmp_path, monkeypatch):
    real_exp = acquisition.single_exposure
    count = {"n": 0}

    def flaky(*a, **k):
        count["n"] += 1
        if count["n"] == 2:
            return acquisition.AcquisitionFailure(acquisition.AcquisitionFailureKind.TIMEOUT, None, None, "simulada")
        return real_exp(*a, **k)
    monkeypatch.setattr(acquisition, "single_exposure", flaky)
    be.confirm_mirror("down")
    be.start_scan(45.0, 46.0, 45.0, 45.0, 1.0, 0.01, SHUTTERS[0])
    _run(be)
    with h5py.File(next(Path(tmp_path).glob("*.h5")), "r") as f:
        failed = f["failed"][:]
        assert failed.tolist() == [[False], [True]]
        assert np.all(np.isnan(f["cube"][1, 0])) and np.all(np.isfinite(f["cube"][0, 0]))
        assert f.attrs["complete"]


def test_a_stage_that_does_not_arrive_stops_the_map_with_the_shutters_closed(be, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "wait_on_target", lambda *a, **k: False)
    msgs = []
    be.statusSignal.connect(msgs.append)
    be.confirm_mirror("down")
    be.start_scan(45.0, 46.0, 45.0, 45.0, 1.0, 0.01, SHUTTERS[0])
    _run(be)
    assert not be._scanning and not nidaq.get_open_shutter_names()
    assert any("platina" in m for m in msgs)
    with h5py.File(next(Path(tmp_path).glob("*.h5")), "r") as f:
        assert not f.attrs["complete"]


def test_the_spectrometer_shutter_opens_and_closes(be, monkeypatch):
    log = []
    ok = type("R", (), {"ok": True, "detail": ""})()
    monkeypatch.setattr("pyspectrum.services.spectrometer_shutter.open_spectrometer_shutter",
                        lambda c, s: log.append("open") or ok)
    monkeypatch.setattr("pyspectrum.services.spectrometer_shutter.close_spectrometer_shutter",
                        lambda c, s: log.append("close") or ok)
    be.confirm_mirror("down")
    be.start_scan(45.0, 45.0, 45.0, 45.0, 1.0, 0.01, SHUTTERS[0])
    _run(be)
    # abre al empezar y cierra al terminar; un Live pausado por la sesión puede agregar cierres propios
    assert "open" in log and log[-1] == "close" and log.index("open") < len(log) - 1


def test_stop_from_another_thread_cuts_an_exposure(be):
    be.confirm_mirror("down")
    be.start_scan(45.0, 50.0, 45.0, 50.0, 1.0, 2.0, SHUTTERS[0])
    import threading
    threading.Timer(0.3, be.request_stop).start()
    t0 = time.monotonic()
    be._scan_step()
    assert time.monotonic() - t0 < 1.5
    _run(be, 5.0)
    assert not be._scanning
