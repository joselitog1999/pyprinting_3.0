# -*- coding: utf-8 -*-
"""
test_trace.py — Pruebas unitarias para las correcciones de seguridad de modules/trace.py
y core/nidaq.py (auditoría multi-agente 2026-09-18, hallazgos ANOM-TRACE-01/02):

1. ANOM-TRACE-01 (REVERTIDO por DEC-037, 2026-09-27): la Task continua reutilizada se
   leía de a 10 muestras por tick y DAQmx entrega la más vieja sin leer: los datos se
   atrasaban y el buffer se desbordaba (C-01). La traza volvió a la lectura finita por
   tick de producción (7f5d10a); lo verifica tests/test_trace_acquisition_freshness.py,
   con un doble que sí modela el buffer. El parámetro continuous=False de
   channels_photodiodos() se conserva (sin usuarios por ahora).
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


# ── ANOM-TRACE-01 — core/nidaq.py: parámetro continuous no rompe el default ─

def test_channels_photodiodos_default_stays_finite_mock():
    task = nq.channels_photodiodos(1000.0, 10)
    assert isinstance(task, nq._MockNITask)


def test_channels_photodiodos_continuous_flag_accepted():
    task = nq.channels_photodiodos(1000.0, 10, continuous=True)
    assert isinstance(task, nq._MockNITask)


# ── ANOM-TRACE-01 — la Task persistente se revirtió (DEC-037) ──────────────
# Los dos tests que exigían una Task continua reutilizada codificaban el defecto C-01
# (su doble no modelaba el buffer de DAQmx, por eso pasaban). Los reemplaza
# tests/test_trace_acquisition_freshness.py.


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
