# -*- coding: utf-8 -*-
"""
test_measurements.py — Pruebas unitarias para la corrección de seguridad de
modules/measurements.py (auditoría multi-agente 2026-09-18, hallazgo ANOM-MEASURE-02):

El loop de impresión/traza (_grid_trace() abre el obturador; grid_trace_detect() es el
callback por muestra que llega mientras el obturador está abierto) nunca renovaba el
heartbeat del watchdog. Con DEFAULT_PRINTING_TMAX=20s y Healing Pass sumando +10s, el
tiempo total de exposición de un nodo puede caer exactamente en el deadline default del
watchdog (30s) — el watchdog podía forzar el cierre del obturador a mitad de pulso sin
que esta máquina de estados se enterara, quedando "esperando" un salto que ya no puede
detectar (queda como "timeout" en vez de reflejar que fue el propio watchdog el que
cortó la luz).

También cubre la guarda de grid_change_index() (Lote 6, P2): editar el campo "Target
Index" a mano mientras hay una impresión activa reasignaba self.i_global de inmediato,
sin ningún chequeo — el resultado de una traza en curso terminaría atribuyéndose al
nodo nuevo en vez del que físicamente se estaba imprimiendo.

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
import modules.measurements as meas_mod


def _no_jump_data():
    """Payload de grid_trace_detect sin salto fototérmico (I_new/I_old dentro del
    umbral) — no debe disparar la rama de cierre/detección, solo ejercitar el heartbeat."""
    return [1, np.linspace(0, 1, 10), np.ones(10), np.array([]), 1.0, 1.0, np.ones(10), 1.0]


def test_grid_trace_detect_calls_heartbeat_on_every_sample(app, monkeypatch):
    calls = {"n": 0}
    monkeypatch.setattr(meas_mod, "heartbeat_shutter",
                         lambda *a, **k: calls.__setitem__("n", calls["n"] + 1))

    backend = meas_mod.Backend(mode="printing")
    backend.timer_inicio = time.time()

    data = _no_jump_data()
    for _ in range(5):
        backend.grid_trace_detect(data)

    assert calls["n"] == 5, \
        "heartbeat_shutter() debe renovarse en cada muestra recibida durante la traza de impresión"


def test_grid_trace_detect_calls_heartbeat_without_hardcoded_timeout(app, monkeypatch):
    """La renovación debe respetar la política global (bare heartbeat_shutter()), no
    hardcodear un valor propio — el mismo anti-patrón que ANOM-CONFOCAL-02 identificó
    en confocal.py/contrapropagante.py no debe reintroducirse aquí."""
    received_args = []
    monkeypatch.setattr(meas_mod, "heartbeat_shutter",
                         lambda *a, **k: received_args.append((a, k)))

    backend = meas_mod.Backend(mode="printing")
    backend.timer_inicio = time.time()
    backend.grid_trace_detect(_no_jump_data())

    assert received_args == [((), {})], \
        "grid_trace_detect debe llamar heartbeat_shutter() sin argumentos (política global)"


def test_grid_trace_detect_renewal_keeps_shutter_open_past_short_global_timeout(app):
    """Integración con el watchdog real: con la política global acotada a 0.3s, una
    traza simulada que renueva en cada muestra (vía grid_trace_detect) debe sobrevivir
    más allá de ese timeout — antes de este fix, nada en el loop de impresión llamaba
    heartbeat_shutter(), así que el watchdog habría forzado el cierre."""
    prev_default = nq.get_default_shutter_timeout()
    laser = nq.SHUTTERS[0]
    idx = nq.SHUTTERS.index(laser)
    try:
        nq.set_default_shutter_timeout(0.3)
        nq.open_shutter(laser)  # arma el watchdog con la política global (0.3s)
        assert nq.is_watchdog_armed()

        backend = meas_mod.Backend(mode="printing")
        backend.laser = laser
        backend.timer_inicio = time.time()
        data = _no_jump_data()

        for _ in range(6):
            time.sleep(0.1)
            backend.grid_trace_detect(data)
            assert nq._shutter_signal[idx] == nq.SHUTTER_POLARITY[laser], (
                "El obturador no debe cerrarse mientras grid_trace_detect siga "
                "renovando el heartbeat en cada muestra (ANOM-MEASURE-02)"
            )

        nq.close_shutter(laser)
    finally:
        nq.set_default_shutter_timeout(prev_default)


# ── grid_change_index — guarda contra reasignación mid-print (Lote 6, P2) ───

def test_grid_change_index_blocked_during_active_printing(app):
    backend = meas_mod.Backend(mode="printing")
    backend.i_global = 5
    backend.mode_printing = "printing"  # traza activa

    backend.grid_change_index(12)

    assert backend.i_global == 5, "No debe reasignar i_global mientras hay una impresión activa"


def test_grid_change_index_applies_when_idle(app):
    backend = meas_mod.Backend(mode="printing")
    backend.i_global = 5
    backend.mode_printing = "none"  # idle / pausado

    backend.grid_change_index(12)

    assert backend.i_global == 12, "Debe aplicar el cambio cuando no hay impresión activa"
