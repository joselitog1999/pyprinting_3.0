# -*- coding: utf-8 -*-
"""Dímeros sobre las primitivas de grilla (AND-1, parte 5; R4-K).

- Impresión con potencia alta y el láser abierto; centrado y post-escaneo con potencia baja y el láser
  ABIERTO (antes se centraba con el láser cerrado). La potencia espera 2 s, como el legado.
- Sin espectro final (P5): la secuencia no expone la cámara ni abre el obturador del espectrómetro.
- El espejo se confirma al arrancar y no se mueve.
- Un centrado cuya platina no llega pausa la secuencia con los obturadores cerrados.
"""
import os
import time

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
from pyspectrum.modules.optical_support import StageNotOnTarget
from pyspectrum.modules.routines import dimers as dm

LASER = config.SHUTTERS[1]


def _cfg(**kw):
    c = {"laser": LASER, "dx_nm": 100.0, "dy_nm": 0.0, "trace_threshold_ratio": 1.2, "trace_max_s": 0.3,
         "refocus_every": 100, "save_dir": "", "mirror": "up"}
    c.update(kw)
    return c


@pytest.fixture
def be(tmp_path, monkeypatch):
    hardware_session.clear_emergency()
    b = dm.DimersBackend(get_andor_ccd(force_mock=True), get_shamrock(force_mock=True))
    b.POWER_SETTLE_S = 0.05
    b.data_dir = str(tmp_path / "dimers")
    b.generate_grid(1, 1, 3.0, 0.0, 40.0, 40.0, 5.0)
    monkeypatch.setattr(dm, "run_z_autofocus", lambda **kw: True)
    monkeypatch.setattr(dm, "read_photodiode_level", lambda *a, **k: 100.0)
    yield b
    b.abort_sequence()
    b.seq_thread.wait_finished(10)
    hardware_session.clear_emergency()
    nidaq.close_all_shutters()


def test_the_legacy_power_settle_is_two_seconds():
    assert dm.DimersBackend.POWER_SETTLE_S == 2.0


def test_printing_is_high_power_and_centering_is_low_power_with_the_laser_open(be, monkeypatch):
    log, seen = [], []
    monkeypatch.setattr(nidaq, "up_flipper", lambda: log.append("low") or True)
    monkeypatch.setattr(nidaq, "down_flipper", lambda: log.append("high") or True)
    ro, rc = dm.open_shutter, dm.close_shutter
    monkeypatch.setattr(dm, "open_shutter", lambda n, *a, **k: log.append("open") or ro(n))
    monkeypatch.setattr(dm, "close_shutter", lambda n: log.append("close") or rc(n))
    mirror = []
    monkeypatch.setattr(nidaq, "flipper_notch532", lambda p: mirror.append(p) or True)
    coords = iter([(41.0, 41.0), (41.1, 41.0)])
    monkeypatch.setattr(dm, "run_confocal_centering",
                        lambda **kw: seen.append(LASER in nidaq.get_open_shutter_names()) or next(coords))
    exposures = []
    monkeypatch.setattr(acquisition, "single_exposure", lambda *a, **k: exposures.append(1))
    spec_shutter = []
    monkeypatch.setattr("pyspectrum.services.spectrometer_shutter.open_spectrometer_shutter",
                        lambda c, s: spec_shutter.append(1))
    be.start_sequence(_cfg())
    assert be.seq_thread.wait_finished(30)
    assert seen == [True, True]                                  # centrado y post-escaneo con el láser abierto
    assert log == ["high", "open", "close", "low", "open", "close",
                   "high", "open", "close", "low", "open", "close"], log
    assert exposures == [] and spec_shutter == []                # sin espectro final (P5)
    assert mirror == []                                          # los dímeros no mueven el espejo
    assert be.states == [dm.NODE_DONE]
    assert (os.path.exists(os.path.join(be.data_dir, "DimerPair_000_coords.txt")))


def test_it_does_not_start_without_the_mirror_confirmation(be):
    be.start_sequence(_cfg(mirror=None))
    assert not be._seq_running and not hardware_session.is_busy


def test_a_centering_whose_stage_does_not_arrive_pauses(be, monkeypatch):
    def stuck(**kw):
        raise StageNotOnTarget("La platina no confirmó la llegada.")
    monkeypatch.setattr(dm, "run_confocal_centering", stuck)
    be.start_sequence(_cfg())
    t_end = time.monotonic() + 15
    while not be.seq_thread.ctl.pause.is_set() and time.monotonic() < t_end:
        QtWidgets.QApplication.processEvents()
        time.sleep(0.01)
    assert be.seq_thread.ctl.pause.is_set() and LASER not in nidaq.get_open_shutter_names()
    be.abort_sequence()
    assert be.seq_thread.wait_finished(10)
