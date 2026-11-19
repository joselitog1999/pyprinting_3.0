# -*- coding: utf-8 -*-
"""Sonda P-1, a nivel del criterio (C-01 Ronda 4; `ronda2_architecture.md` §3, §4.6; DEC-043, DEC-045, DEC-046).

Hasta la fase 2, el criterio corría en el hilo GUI (`app.py::_dispatch_trace`) y la traza en `confocalThread`. Un tick
que ya estaba encolado cuando el criterio decidió llegaba igual a `grid_trace_detect`, y podía volver a decidir el nodo
(dos `grid_detectSignal`, `i_global` avanza dos veces, un nodo salteado) o caer en el nodo siguiente.

- **La fase 2 cerró el camino** (DEC-045): el criterio decide dentro del tick, en el mismo hilo, y la parada de la traza
  es sincrónica. Lo verifica `tests/test_grid_chain_single_thread.py`, con el hilo GUI ocupado.
- **La fase 3 agregó la guarda del criterio mismo** (DEC-046): un nodo decidido (`_node_decided`) no se vuelve a decidir.
  Esta sonda la comprueba sin hilos, con dos llamadas seguidas a `grid_trace_detect`.
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


def test_a_late_tick_does_not_decide_the_same_node_twice(worker):
    emitted = []
    worker.grid_detectSignal.connect(lambda: emitted.append(worker.i_global))
    step = [1, [0.0, 0.01], [1.0, 2.0], 0, 1.0, 2.0, 1.0, 1.0]
    worker.grid_trace_detect(step)            # decide: success
    worker.grid_trace_detect(step)            # el tick que ya estaba encolado
    assert emitted == [0], emitted
