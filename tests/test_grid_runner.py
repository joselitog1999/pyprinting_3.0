# -*- coding: utf-8 -*-
"""Primitivas de las rutinas de grilla (AND-1, parte 1; R4-K; C-54; DEC-036).

- `move_to` confirma la llegada con `wait_on_target` y un tope; si no llega, cierra los obturadores y pausa.
  Nunca "llegó" por timeout (C-54).
- `set_power` y `set_mirror` conmutan como el legado y esperan su asentamiento latiendo; el espejo nunca
  se mueve con un láser de la rutina abierto.
- `laser` confirma la apertura y el cierre; un cierre no confirmado cuenta como abierto y pausa.
- `expose` es una exposición real: una falla es un nodo fallido, nunca un cuadro de ceros.
- Toda espera late sin argumento y se corta con Stop o E-STOP.
"""
import ast
import os
from pathlib import Path

os.environ.setdefault("PYPRINTING_SAFE", "1")

import numpy as np
import pytest

import config
from pyspectrum.modules.routines import grid_runner as gr
from pyspectrum.modules.routines.grid_runner import GridAbort, GridRunner, GridSafetyPause, NodeFailed


class FakeHW:
    def __init__(self, *, open_ok=True, close_ok=True, flipper_ok=True, mirror_ok=True):
        self.log = []
        self.open_ok, self.close_ok, self.flipper_ok, self.mirror_ok = open_ok, close_ok, flipper_ok, mirror_ok

    def open_shutter(self, name):
        self.log.append(("open", name))
        return self.open_ok

    def close_shutter(self, name):
        self.log.append(("close", name))
        return self.close_ok

    def close_all_shutters(self):
        self.log.append("close_all")
        return True

    def up_flipper(self):
        self.log.append("power low")
        return self.flipper_ok

    def down_flipper(self):
        self.log.append("power high")
        return self.flipper_ok

    def flipper_notch532(self, pos):
        self.log.append(("mirror", pos))
        return self.mirror_ok


class StuckStage:
    is_mock = True
    connected = True

    def __init__(self):
        self.moves = []

    def MOV(self, axes, targets):
        self.moves.append((list(axes), list(targets)))
        return True

    def qONT(self, axes=None):
        return {a: False for a in (axes or [1, 2, 3])}

    def qPOS(self, axes=None):
        return {"1": 0.0, "2": 0.0, "3": 0.0}


def _runner(hw=None, stage=None, abort=None, sleeps=None, **kw):
    sleeps = sleeps if sleeps is not None else []
    return GridRunner(camera=kw.pop("camera", None), hw=hw or FakeHW(), stage=stage or config.pi,
                      should_abort=abort or (lambda: False), tick=kw.pop("tick", lambda: None),
                      sleep=lambda s: sleeps.append(s), move_timeout_s=kw.pop("move_timeout_s", 0.05), **kw)


def test_move_to_confirms_the_arrival_and_clamps():
    config.pi.connect()
    r = _runner()
    r.move_to(150.0, 20.0, 30.0)
    pos = config.pi.qPOS()
    assert (pos["1"], pos["2"]) == (config.PI_AXIS_RANGE_UM[1], 20.0)
    assert pos["3"] == config.PI_AXIS_RANGE_UM[3]
    r.move_to(40.0, 40.0)                           # sin Z: el eje Z no se toca
    assert config.pi.qPOS()["3"] == config.PI_AXIS_RANGE_UM[3]
    config.pi.MOV([1, 2, 3], list(config.PI_HOME_POS))


def test_a_stage_that_does_not_arrive_pauses_with_the_shutters_closed():
    hw = FakeHW()
    r = _runner(hw=hw, stage=StuckStage())
    with pytest.raises(GridSafetyPause) as e:
        r.move_to(10.0, 10.0)
    assert "platina" in str(e.value) and "close_all" in hw.log


def test_power_switching_settles_while_beating():
    hw, sleeps, ticks = FakeHW(), [], []
    r = _runner(hw=hw, sleeps=sleeps, tick=lambda: ticks.append(1), power_settle_s=0.5)
    r.set_power("low")
    r.set_power("high")
    assert hw.log == ["power low", "power high"]
    assert sum(sleeps) == pytest.approx(1.0, abs=0.06) and ticks
    with pytest.raises(ValueError):
        r.set_power("media")


def test_a_power_pulse_that_fails_pauses():
    with pytest.raises(GridSafetyPause):
        _runner(hw=FakeHW(flipper_ok=False)).set_power("high")


def test_the_mirror_never_moves_with_a_laser_of_the_routine_open():
    hw, sleeps = FakeHW(), []
    r = _runner(hw=hw, sleeps=sleeps)
    r.laser("532 nm (green)", True)
    r.set_mirror("down")
    assert hw.log.index(("close", "532 nm (green)")) < hw.log.index(("mirror", "down"))
    with pytest.raises(ValueError):
        r.set_mirror("medio")


def test_laser_open_waits_and_an_unconfirmed_close_pauses():
    hw, sleeps = FakeHW(close_ok=False), []
    r = _runner(hw=hw, sleeps=sleeps, laser_settle_s=0.5)
    r.laser("532 nm (green)", True)
    assert sum(sleeps) == pytest.approx(0.5, abs=0.06)
    with pytest.raises(GridSafetyPause):
        r.laser("532 nm (green)", False)
    with pytest.raises(GridSafetyPause):
        _runner(hw=FakeHW(open_ok=False)).laser("532 nm (green)", True)


def test_close_lasers_closes_every_laser_the_routine_opened():
    hw = FakeHW()
    r = _runner(hw=hw)
    r.laser("532 nm (green)", True)
    r.laser("637 nm (red)", True)
    assert r.close_lasers()
    assert ("close", "532 nm (green)") in hw.log and ("close", "637 nm (red)") in hw.log and not r.open_lasers


def test_waits_are_cut_by_stop():
    calls = []
    r = _runner(abort=lambda: len(calls) > 3, tick=lambda: calls.append(1))
    with pytest.raises(GridAbort):
        r.wait(10.0)


def test_expose_is_a_real_exposure_and_a_failure_fails_the_node():
    from pyspectrum.drivers.andor_ccd_driver import get_andor_ccd
    from pyspectrum.drivers.andor_ccd_driver import READ_MODE_FVB
    cam = get_andor_ccd(force_mock=True)
    cam.set_read_mode(READ_MODE_FVB)
    r = _runner(camera=cam)
    a = r.expose((1004,), 0.01)
    b = r.expose((1004,), 0.01)
    assert a.shape == (1004,) and not np.array_equal(a, b)

    class Broken:
        available = False                  # la cámara no está: single_exposure lo informa, nunca ceros
        unavailable_reason = "cámara desconectada"
    with pytest.raises(NodeFailed):
        _runner(camera=Broken()).expose((1004,), 0.01)


def test_the_optical_support_move_no_longer_pretends_to_arrive(monkeypatch):
    """C-54: si la platina no llega, cierra los obturadores y levanta un error; nunca devuelve la
    posición como si hubiera llegado."""
    from pyspectrum.modules import optical_support as osup
    closed = []
    monkeypatch.setattr(config, "pi", StuckStage())
    monkeypatch.setattr("core.nidaq.close_all_shutters", lambda: closed.append(1) or True)
    with pytest.raises(osup.StageNotOnTarget):
        osup.move_stage_to(10.0, 10.0, timeout_s=0.05)
    assert closed


@pytest.mark.parametrize("path", ["pyspectrum/modules/routines/grid_runner.py",
                                  "pyspectrum/modules/optical_support.py"])
def test_heartbeat_is_never_called_with_an_argument(path):
    src = (Path(__file__).resolve().parents[1] / path).read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", "")) == "heartbeat_shutter":
            assert not node.args and not node.keywords, (path, node.lineno)
