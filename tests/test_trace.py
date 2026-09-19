# -*- coding: utf-8 -*-
"""
test_trace.py — Pruebas unitarias para las correcciones de seguridad de modules/trace.py
y core/nidaq.py (auditoría multi-agente 2026-09-18, hallazgos ANOM-TRACE-01/02):

1. ANOM-TRACE-01: la Task DAQmx de fotodiodos se crea UNA sola vez por sesión de traza
   (_start()/set_bs_only_active(True)) y se reutiliza en cada tick vía .read(), en vez
   de crearse/destruirse 30x/segundo — la cadencia entre muestras deja de depender del
   overhead de alocar el driver en cada tick. channels_photodiodos() en core/nidaq.py
   gana un parámetro continuous=False por defecto, que preserva el comportamiento FINITE
   existente para focus.py (rampa Z disparada por trigger, no debe volverse continua).
2. ANOM-TRACE-02: el payload emitido por tick se acota a SEND_WINDOW muestras — el
   historial completo permanece intacto en self.timeaxis/self.intensity_* para
   save_trace(). Esto obligó a corregir Frontend.get_data(), que antes recortaba usando
   `n` (el contador global de muestras, sin límite) en vez de la longitud real del array
   recibido — con el backend ya acotado, ambos dejan de coincidir tras SEND_WINDOW ticks.

PyPrinting 3.0 — UNSAM Nanofotónica
"""
import os
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ["PYPRINTING_SAFE"] = "1"

# Ver conftest.py: config debe importarse antes que PyQt6 en este entorno.
import config  # noqa: F401
import numpy as np
import core.nidaq as nq
import modules.trace as trace_mod


class _FakeContinuousTask:
    """Sustituto mínimo de una nidaqmx.Task en modo CONTINUOUS, para verificar que
    trace.py reutiliza la misma instancia en vez de crear una nueva por tick."""
    def __init__(self, n_channels: int, samps: int):
        self.n_channels  = n_channels
        self.samps       = samps
        self.start_calls = 0
        self.read_calls  = 0
        self.stop_calls  = 0
        self.close_calls = 0

    def start(self):
        self.start_calls += 1

    def read(self, samps=None):
        self.read_calls += 1
        n = samps or self.samps
        return [list(np.full(n, 0.5)) for _ in range(self.n_channels)]

    def wait_until_done(self):
        pass

    def stop(self):
        self.stop_calls += 1

    def close(self):
        self.close_calls += 1


# ── ANOM-TRACE-01 — core/nidaq.py: parámetro continuous no rompe el default ─

def test_channels_photodiodos_default_stays_finite_mock():
    task = nq.channels_photodiodos(1000.0, 10)
    assert isinstance(task, nq._MockNITask)


def test_channels_photodiodos_continuous_flag_accepted():
    task = nq.channels_photodiodos(1000.0, 10, continuous=True)
    assert isinstance(task, nq._MockNITask)


# ── ANOM-TRACE-01 — modules/trace.py: Task persistente reutilizada ──────────

def test_trace_backend_creates_task_once_and_reuses_it_across_ticks(app, monkeypatch):
    backend = trace_mod.Backend()
    fake_task = _FakeContinuousTask(len(trace_mod.PD_CHANS_LIST) + 1, backend.N)
    factory_calls = {"n": 0}

    def fake_channels_photodiodos(rate, samps, continuous=False):
        factory_calls["n"] += 1
        assert continuous is True, "trace.py debe pedir explícitamente continuous=True"
        return fake_task

    monkeypatch.setattr(trace_mod, "SAFE_MODE", False)
    monkeypatch.setattr(trace_mod, "channels_photodiodos", fake_channels_photodiodos)
    monkeypatch.setattr(trace_mod, "open_shutter", lambda name: None)
    monkeypatch.setattr(trace_mod, "close_shutter", lambda name: None)
    monkeypatch.setattr(trace_mod, "heartbeat_shutter", lambda *a, **k: None)

    backend.laser1 = trace_mod.SHUTTERS[0]
    backend.laser2 = "None"
    backend._start()

    assert factory_calls["n"] == 1, "La Task debe crearse una sola vez en _start(), no por tick"
    assert fake_task.start_calls == 1

    for _ in range(5):
        backend._trace_update()

    assert factory_calls["n"] == 1, "No debe crearse una Task nueva en cada tick"
    assert fake_task.read_calls == 5, "Debe reutilizar .read() sobre la misma Task en cada tick"

    backend._stop_and_save()
    assert fake_task.stop_calls == 1
    assert fake_task.close_calls == 1
    assert backend._task is None


def test_bs_only_backend_creates_task_once_and_reuses_it(app, monkeypatch):
    backend = trace_mod.Backend()
    fake_task = _FakeContinuousTask(len(trace_mod.PD_CHANS_LIST) + 1, backend.N)
    factory_calls = {"n": 0}

    def fake_channels_photodiodos(rate, samps, continuous=False):
        factory_calls["n"] += 1
        assert continuous is True
        return fake_task

    monkeypatch.setattr(trace_mod, "SAFE_MODE", False)
    monkeypatch.setattr(trace_mod, "channels_photodiodos", fake_channels_photodiodos)

    backend.set_bs_only_active(True)
    assert factory_calls["n"] == 1
    assert fake_task.start_calls == 1

    for _ in range(4):
        backend._bs_only_update()

    assert factory_calls["n"] == 1
    assert fake_task.read_calls == 4

    backend.set_bs_only_active(False)
    assert fake_task.stop_calls == 1
    assert fake_task.close_calls == 1
    assert backend._bs_task is None


# ── ANOM-TRACE-02 — payload acotado, historial completo preservado ──────────

def test_trace_update_windows_emitted_payload_but_keeps_full_history(app):
    backend = trace_mod.Backend()
    backend.laser1 = trace_mod.SHUTTERS[0]
    backend.laser2 = "None"
    backend.mode_printing = "none"

    long_n = trace_mod.SEND_WINDOW + 500
    backend._n            = long_n
    backend.timer_inicio  = time.time() - 100.0
    backend.timeaxis      = np.arange(long_n, dtype=float)
    backend.intensity_l1  = np.zeros(long_n)
    backend.intensity_l2  = np.zeros(long_n)
    backend.intensity_BS  = np.zeros(long_n)

    received = {}
    backend.dataSignal.connect(lambda data: received.update(payload=data))

    backend._trace_update()

    assert "payload" in received
    assert len(received["payload"][1]) <= trace_mod.SEND_WINDOW, \
        "El payload emitido no debe exceder SEND_WINDOW muestras (ANOM-TRACE-02)"
    assert len(backend.timeaxis) == long_n + 1, \
        "El historial completo en self.timeaxis debe seguir intacto para save_trace()"


def test_frontend_get_data_uses_received_array_length_not_global_counter(app):
    """Regresión directa del bug introducido por el propio fix de ANOM-TRACE-02:
    Frontend.get_data() recortaba usando `n` (data[0], contador global sin límite) en
    vez de la longitud real de los arrays ya acotados por el Backend — una vez que
    n > SEND_WINDOW, ambos dejan de coincidir y el slice antiguo devolvía un tramo
    vacío/incorrecto."""
    frontend = trace_mod.Frontend()
    n_total = 50_000  # contador global, mucho mayor que la ventana recibida
    m = 1500          # longitud real de los arrays ya acotados por el backend
    data = [
        n_total,
        np.arange(m, dtype=float),
        np.ones(m),
        np.array([]),   # laser2 = "None" por defecto: no se usa
        0.5, 0.5,
        np.zeros(m),
        0.5,
    ]
    frontend.get_data(data)  # no debe lanzar

    x_data, y_data = frontend.curve_L1.getData()
    assert x_data is not None and len(x_data) == 1000, \
        "Debe recortar a las últimas SHOW=1000 muestras usando la longitud real recibida"
