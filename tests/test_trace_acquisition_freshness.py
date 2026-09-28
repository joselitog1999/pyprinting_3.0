# -*- coding: utf-8 -*-
"""
test_trace_acquisition_freshness.py — La traza de impresión lee datos actuales (C-01, paso 0).

PyPrinting 3.0 — UNSAM Nanofotónica

Desde `6abbbfc` (2026-09-19) la traza y Power BS leían 10 muestras por tick de una tarea DAQmx
**continua** a 10 kS/s. DAQmx entrega por defecto la muestra más vieja sin leer, así que los datos
se atrasaban y, al llenarse el buffer, cada lectura fallaba y se registraba 0.0 V. El criterio de fin
de impresión decidía entonces sobre datos viejos o ceros. La versión en producción (`7f5d10a`) lee
con una tarea finita nueva en cada tick y funciona; el investigador aprobó volver a ella (Ronda 1 de
C-01) hasta que la Ronda 2 diseñe la adquisición definitiva.

El test anterior (`_FakeContinuousTask`) no modelaba el buffer y por eso no vio el defecto. Estos
dobles sí lo modelan: la tarea continua acumula `rate · dt` muestras por tick al nivel de señal de
ese momento, entrega las más viejas y se desborda. Nada toca hardware.
"""
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("PYPRINTING_SAFE", "1")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import config  # noqa: F401 — antes que PyQt6 (DEC-010/DEC-011)
import pytest
from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)

import modules.trace as trace_mod
from config import SHUTTERS, PD_CHANS_LIST

TICK_S = 0.035          # intervalo nominal del QTimer de la traza
BUFFER_SAMPLES = 10_000  # buffer por canal de DAQmx a 10 kS/s (regla de NI; ver c01_ronda1/)


class _Bench:
    """Nivel de señal del fotodiodo y reloj simulado, compartidos por los dobles."""

    def __init__(self):
        self.level = 0.2
        self.continuous_tasks = []
        self.calls = []

    def advance(self, dt):
        for task in self.continuous_tasks:
            task.acquire(dt)


class _FiniteTask:
    """Tarea finita: adquiere N muestras *ahora* y las entrega."""

    def __init__(self, bench):
        self._bench = bench

    def read(self, n):
        return [[self._bench.level] * n for _ in PD_CHANS_LIST]

    def wait_until_done(self):
        pass

    def close(self):
        pass


class _ContinuousTask:
    """Tarea continua con la semántica de DAQmx por defecto: la placa escribe `rate · dt`
    muestras por tick en un buffer finito; `read(n)` entrega las n más viejas sin leer; si el
    buffer se llenó, cada lectura falla (−200279) y la tarea no se recupera sola."""

    def __init__(self, bench, rate):
        self._bench = bench
        self._rate = rate
        self._queue = []
        self._overflow = False
        self._running = False

    def start(self):
        self._running = True

    def acquire(self, dt):
        if not self._running or self._overflow:
            return
        self._queue.extend([self._bench.level] * int(round(self._rate * dt)))
        if len(self._queue) > BUFFER_SAMPLES:
            self._overflow = True

    def read(self, n):
        if self._overflow:
            raise RuntimeError("DAQmx Error -200279: attempted to read samples no longer available")
        chunk, self._queue = self._queue[:n], self._queue[n:]
        return [list(chunk) for _ in PD_CHANS_LIST]

    def stop(self):
        self._running = False

    def close(self):
        self._running = False


@pytest.fixture
def bench(monkeypatch):
    b = _Bench()

    def fake_channels_photodiodos(rate, samps_per_chan, continuous=False):
        b.calls.append(continuous)
        if continuous:
            task = _ContinuousTask(b, rate)
            b.continuous_tasks.append(task)
            return task
        return _FiniteTask(b)

    monkeypatch.setattr(trace_mod, "SAFE_MODE", False)
    monkeypatch.setattr(trace_mod, "channels_photodiodos", fake_channels_photodiodos)
    monkeypatch.setattr(trace_mod, "open_shutter", lambda *a, **k: True)
    monkeypatch.setattr(trace_mod, "close_shutter", lambda *a, **k: True)
    monkeypatch.setattr(trace_mod, "heartbeat_shutter", lambda *a, **k: None)
    return b


def _stop_timers(backend):
    for t in (backend.pointtimer, backend.bs_timer):
        if t is not None and t.isActive():
            t.stop()


def _run_trace(bench, backend, n_ticks, step_at, step_level):
    """Corre n ticks de la traza principal; en el tick `step_at` la señal sube (una captura)."""
    backend.laser1, backend.laser2 = SHUTTERS[0], "None"
    backend._start()
    backend.pointtimer.stop()      # los ticks los da el test, no el event loop
    seen = []
    for k in range(n_ticks):
        if k == step_at:
            bench.level = step_level
        bench.advance(TICK_S)
        backend._trace_update()
        seen.append(float(backend.intensity_l1[-1]))
    return seen


def test_trace_sees_a_capture_within_one_tick(bench):
    backend = trace_mod.Backend()
    try:
        seen = _run_trace(bench, backend, n_ticks=20, step_at=10, step_level=0.4)
    finally:
        _stop_timers(backend)
    assert seen[:10] == pytest.approx([0.2] * 10)
    assert seen[10] == pytest.approx(0.4), (
        f"La traza no ve el escalón en el tick en que ocurre: {seen[10]:.3f} en vez de 0.4. "
        "Con una tarea continua leída de a 10 muestras por tick, los datos van atrasados.")
    assert seen[-1] == pytest.approx(0.4)


def test_trace_never_records_zero_after_a_long_node(bench):
    """Un nodo largo (40 s, el tiempo máximo del preset en uso) no debe terminar leyendo 0 V."""
    backend = trace_mod.Backend()
    n_ticks = int(40.0 / TICK_S)
    try:
        seen = _run_trace(bench, backend, n_ticks=n_ticks, step_at=n_ticks + 1, step_level=0.2)
    finally:
        _stop_timers(backend)
    assert min(seen) == pytest.approx(0.2), (
        "La traza registró 0.0 V: la tarea continua desbordó su buffer y cada lectura falló.")


def test_trace_and_power_bs_do_not_use_a_continuous_task(bench):
    backend = trace_mod.Backend()
    try:
        _run_trace(bench, backend, n_ticks=3, step_at=99, step_level=0.2)
        _stop_timers(backend)
        backend.set_bs_only_active(True)
        backend.bs_timer.stop()
        bench.advance(TICK_S)
        backend._bs_only_update()
    finally:
        backend.set_bs_only_active(False)
        _stop_timers(backend)
    assert bench.calls and not any(bench.calls), (
        "La traza o Power BS crearon una tarea continua: C-01, paso 0, vuelve a la lectura finita "
        "por tick de producción hasta que la Ronda 2 diseñe la adquisición definitiva.")


class _FailingFiniteTask:
    """Tarea finita cuya lectura falla (p. ej. −200279 o −50103): cuenta los cierres."""
    closes = 0

    def read(self, n):
        raise RuntimeError("DAQmx Error -50103: the specified resource is reserved")

    def wait_until_done(self):
        pass

    def close(self):
        _FailingFiniteTask.closes += 1


def test_a_failed_read_still_releases_the_task(monkeypatch):
    """Si `read()` lanza, la tarea igual se cierra: `nidaqmx.Task.__del__` sólo avisa y no libera
    el motor de entradas analógicas, que quedaría reservado para el confocal, el foco o
    PySpectrum (hallazgo de la Ronda 2 de C-01, instrumentación §1)."""
    _FailingFiniteTask.closes = 0
    monkeypatch.setattr(trace_mod, "SAFE_MODE", False)
    monkeypatch.setattr(trace_mod, "channels_photodiodos", lambda *a, **k: _FailingFiniteTask())
    monkeypatch.setattr(trace_mod, "open_shutter", lambda *a, **k: True)
    monkeypatch.setattr(trace_mod, "close_shutter", lambda *a, **k: True)
    monkeypatch.setattr(trace_mod, "heartbeat_shutter", lambda *a, **k: None)
    backend = trace_mod.Backend()
    try:
        backend.laser1, backend.laser2 = SHUTTERS[0], "None"
        backend._start()
        backend.pointtimer.stop()
        backend._trace_update()
        assert _FailingFiniteTask.closes == 1, "La traza no cerró la tarea tras una lectura fallida"
        backend.set_bs_only_active(False)
        backend.set_bs_only_active(True)
        backend.bs_timer.stop()
        backend._bs_only_update()
        assert _FailingFiniteTask.closes == 2, "Power BS no cerró la tarea tras una lectura fallida"
    finally:
        backend.set_bs_only_active(False)
        _stop_timers(backend)


def test_power_bs_follows_the_current_power(bench):
    backend = trace_mod.Backend()
    try:
        backend.set_bs_only_active(True)
        backend.bs_timer.stop()
        values = []
        for k in range(12):
            if k == 6:
                bench.level = 0.9
            bench.advance(TICK_S)
            backend._bs_only_update()
            values.append(float(backend.bs_intensity[-1]))
    finally:
        backend.set_bs_only_active(False)
        _stop_timers(backend)
    assert values[6] == pytest.approx(0.9), f"Power BS va atrasada: {values[6]:.3f} en vez de 0.9"
