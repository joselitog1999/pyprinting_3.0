# -*- coding: utf-8 -*-
"""Sonda P-1 (C-01 Ronda 4, fase 0; `ronda2_architecture.md` §3, hallazgo nuevo).

Con el criterio en el hilo GUI (`app.py::_dispatch_trace`) y la traza en `confocalThread`, un tick de la traza que ya
estaba encolado cuando el criterio decidió llega igual a `grid_trace_detect`. Si ese tick vuelve a cumplir el
criterio, el nodo se decide dos veces: dos `grid_detectSignal`, `i_global` avanza dos veces y la platina se mueve con
el nodo siguiente salteado.

La sonda lo reproduce sin hilos: dos llamadas seguidas a `grid_trace_detect` con un escalón, como llegarían dos ticks
encolados. Es `xfail(strict=True)` mientras el código lo reproduzca; la fase 2 (la cadena en un solo hilo) o la 3 (la
época) lo tienen que cerrar, y entonces el test pasa y hay que sacar la marca.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYPRINTING_SAFE", "1")

import time
import types

import numpy as np
import pytest
from PyQt6.QtWidgets import QApplication

import config
import modules.measurements as meas

_app = QApplication.instance() or QApplication(["pytest"])
_KEEP_ALIVE = []


@pytest.fixture
def worker(monkeypatch):
    monkeypatch.setattr(meas, "time", types.SimpleNamespace(sleep=lambda s: None, time=time.time))
    monkeypatch.setattr(meas, "open_shutter", lambda *a, **k: True)
    monkeypatch.setattr(meas, "close_shutter", lambda *a, **k: True)
    monkeypatch.setattr(meas, "down_flipper", lambda *a, **k: True)
    monkeypatch.setattr(meas, "up_flipper", lambda *a, **k: True)
    pw = meas.Backend(mode="printing")
    _KEEP_ALIVE.append(pw)
    monkeypatch.setattr(pw, "_save_trace", lambda *a, **k: None)
    pw.laser, pw.mode_arg, pw.mode_printing = config.SHUTTERS[0], "printing", "printing"
    pw.stopping_mode, pw.umbral, pw.umbral_down, pw.timemax, pw.slope_min = 0, 1.5, 0.0, 40.0, 0.0
    pw.i_global, pw.particulas = 0, 3
    pw.timer_inicio = time.time()
    pw.t_raw_history = []
    return pw


@pytest.mark.xfail(strict=True, reason="P-1: hoy un tick encolado después de la decisión vuelve a decidir el nodo "
                                       "(fase 2 o 3 de R4-17)")
def test_a_late_tick_does_not_decide_the_same_node_twice(worker):
    emitted = []
    worker.grid_detectSignal.connect(lambda: emitted.append(worker.i_global))
    step = [1, [0.0, 0.01], [1.0, 2.0], 0, 1.0, 2.0, 1.0, 1.0]
    worker.grid_trace_detect(step)            # decide: success
    worker.grid_trace_detect(step)            # el tick que ya estaba encolado
    assert emitted == [0], emitted
