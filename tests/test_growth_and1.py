# -*- coding: utf-8 -*-
"""Cinética de crecimiento sobre las primitivas de grilla (AND-1, parte 4; R4-K).

Por nodo, como el legado con las correcciones de R4-K:
- centrado de la semilla con potencia baja, el espejo arriba y el láser ABIERTO;
- crecimiento con potencia alta, el espejo abajo y el láser abierto, con exposiciones reales;
- al terminar, el espejo vuelve a donde lo confirmó el operador.
Un centrado cuya platina no llega pausa la grilla (DEC-036); una exposición fallida deja el nodo FALLIDO
y la grilla sigue (P6). Sin la confirmación del espejo no arranca. Corre en su propio hilo.
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
from pyspectrum.modules.routines import growth_kinetics as gk

LASER = config.SHUTTERS[0]


def _cfg(**kw):
    c = {"laser": LASER, "exp_time": 0.01, "autofocus_every": 10, "center_seed": True, "use_lambda_stop": False,
         "lambda_target_nm": None, "use_photodiode_stop": False, "photodiode_drop_pct": None, "t_max_s": 0.1,
         "interval_s": 0.02, "save_dir": "", "mirror": "up"}
    c.update(kw)
    return c


@pytest.fixture
def be(tmp_path, monkeypatch):
    hardware_session.clear_emergency()
    b = gk.GrowthKineticsBackend(get_andor_ccd(force_mock=True), get_shamrock(force_mock=True))
    b.data_dir = str(tmp_path / "growth")
    b.generate_grid(1, 2, 3.0, 0.0, 40.0, 40.0, 5.0)
    monkeypatch.setattr(gk, "run_z_autofocus", lambda **kw: True)
    yield b
    b.abort_grid()
    b.stop_growth()
    b.grid_thread.wait_finished(10)
    b.point_thread.wait_finished(10)
    hardware_session.clear_emergency()
    nidaq.close_all_shutters()


@pytest.fixture
def log(monkeypatch):
    events = []
    ro, rc = gk.open_shutter, gk.close_shutter
    monkeypatch.setattr(gk, "open_shutter", lambda n, *a, **k: events.append("open") or ro(n))
    monkeypatch.setattr(gk, "close_shutter", lambda n: events.append("close") or rc(n))
    monkeypatch.setattr(nidaq, "up_flipper", lambda: events.append("low") or True)
    monkeypatch.setattr(nidaq, "down_flipper", lambda: events.append("high") or True)
    rm = nidaq.flipper_notch532
    monkeypatch.setattr(nidaq, "flipper_notch532", lambda p: events.append(f"mirror {p}") or rm(p))
    return events


def test_the_node_phases_follow_the_legacy_with_the_centering_laser_open(be, log, monkeypatch):
    seen = {}
    monkeypatch.setattr(gk, "run_confocal_centering",
                        lambda **kw: seen.setdefault("laser_open", LASER in nidaq.get_open_shutter_names()) or (1.0, 2.0))
    t0 = time.monotonic()
    be.start_grid(_cfg())
    assert time.monotonic() - t0 < 0.3 and be.grid_thread.running
    assert be.grid_thread.wait_finished(30)
    assert seen["laser_open"] is True                                   # antes se centraba con el láser cerrado
    node = log[:log.index("close", log.index("high"))]                  # primer nodo, hasta el fin del crecimiento
    i_open = node.index("open")
    assert node[i_open - 2:i_open] == ["low", "mirror up"]              # centrado (después del autofoco del nodo 0)
    i_high = node.index("high")
    assert node[i_high:i_high + 3] == ["high", "mirror down", "open"]    # crecimiento
    assert log[-1] == "mirror up"                                        # vuelve a donde lo confirmó el operador
    assert be.states == [gk.NODE_DONE, gk.NODE_DONE] and not hardware_session.is_busy


def test_growth_frames_are_real_exposures(be, monkeypatch):
    shapes = []
    real = acquisition.single_exposure
    monkeypatch.setattr(acquisition, "single_exposure", lambda *a, **k: shapes.append(a[1].shape) or real(*a, **k))
    monkeypatch.setattr(gk, "run_confocal_centering", lambda **kw: (1.0, 2.0))
    be.start_grid(_cfg(center_seed=False))
    assert be.grid_thread.wait_finished(30)
    assert shapes and all(s == (1004,) for s in shapes)
    assert len(be._node_t_points) == sum(1 for _ in be._node_t_points)


def test_a_centering_whose_stage_does_not_arrive_pauses_the_grid(be, monkeypatch):
    def stuck(**kw):
        raise StageNotOnTarget("La platina no confirmó la llegada.")
    monkeypatch.setattr(gk, "run_confocal_centering", stuck)
    be.start_grid(_cfg())
    t_end = time.monotonic() + 10
    while not be.grid_thread.ctl.pause.is_set() and time.monotonic() < t_end:
        QtWidgets.QApplication.processEvents()
        time.sleep(0.01)
    assert be.grid_thread.ctl.pause.is_set() and LASER not in nidaq.get_open_shutter_names()
    be.abort_grid()
    assert be.grid_thread.wait_finished(10)


def test_a_failed_exposure_fails_the_node_and_the_grid_goes_on(be, tmp_path, monkeypatch):
    monkeypatch.setattr(gk, "run_confocal_centering", lambda **kw: (1.0, 2.0))
    real = acquisition.single_exposure
    count = {"n": 0}

    def flaky(*a, **k):
        count["n"] += 1
        if count["n"] == 1:
            return acquisition.AcquisitionFailure(acquisition.AcquisitionFailureKind.TIMEOUT, None, None, "simulada")
        return real(*a, **k)
    monkeypatch.setattr(acquisition, "single_exposure", flaky)
    be.start_grid(_cfg(center_seed=False))
    assert be.grid_thread.wait_finished(30)
    assert be.states == [gk.NODE_FAILED, gk.NODE_DONE]
    assert (tmp_path / "growth" / "GrowthNode_000_FAILED.txt").exists()
    assert (tmp_path / "growth" / "GrowthNode_001_kinetics.txt").exists()


def test_without_the_mirror_confirmation_nothing_starts(be):
    be.start_grid(_cfg(mirror=None))
    assert not be._grid_running and not hardware_session.is_busy
    be.start_growth(LASER, 0.01, 3, 0.02)
    assert not be.point_thread.running and not hardware_session.is_busy


def test_the_point_mode_takes_real_exposures(be, monkeypatch):
    shapes = []
    real = acquisition.single_exposure
    monkeypatch.setattr(acquisition, "single_exposure", lambda *a, **k: shapes.append(a[1].shape) or real(*a, **k))
    be.confirm_mirror("down")
    be.start_growth(LASER, 0.01, 3, 0.02)
    assert be.point_thread.wait_finished(20)
    assert shapes == [(1004,)] * 3 and len(be.lmax_points) == 3
    assert LASER not in nidaq.get_open_shutter_names()
