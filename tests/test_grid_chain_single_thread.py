# -*- coding: utf-8 -*-
"""La cadena de la grilla en un solo hilo (C-01 Ronda 4, R4-17 fase 2; `ronda2_architecture.md` §3; DEC-045).

Antes, el fin del autofoco (`app.py::_on_autofinish`) y el criterio de la traza (`app.py::_dispatch_trace`) eran
funciones del `Backend`, que vive en el hilo GUI: `grid_finish_autofoco`, el `_grid_trace` del primer nodo y
`grid_trace_detect` corrían en el hilo GUI, y el resto de la cadena en `confocalThread`. Con eso:
- al decidir, el criterio (hilo GUI) y el `_stop_and_save` de la traza (confocalThread) cerraban en carrera;
- **P-1:** los ticks de la traza cruzaban al hilo GUI por su cola. Con el hilo GUI ocupado (dibujando), varios ticks
  se acumulaban; el primero decidía el nodo y el siguiente, ya encolado, lo volvía a decidir: dos
  `grid_detectSignal`, `i_global` avanzaba dos veces y el nodo siguiente quedaba salteado.

Contrato:
1. cada etapa de la cadena corre en `confocalThread`, el hilo de los workers;
2. con el hilo GUI ocupado, cada nodo se decide una sola vez y ninguno se saltea.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYPRINTING_SAFE", "1")

from collections import Counter

import pytest
from PyQt6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication(["pytest"])
_KEEP_ALIVE = []

EXPECTED = ["success", "success", "timeout", "success", "success", "success", "timeout", "success", "success",
            "success", "success"]
# Las etapas que el guion recorre (sin escaneos: `on_scan_finished` no se llama con `scanbool=False`)
STAGES_RUN = {"grid_finish_autofoco", "_grid_trace", "grid_trace_detect", "grid_scan", "_grid_detect"}


def _run(monkeypatch, tmp_path, **run_kw):
    from harness.grid_chain_rig import GridChainRig
    rig = GridChainRig(monkeypatch, tmp_path)
    with rig:
        _KEEP_ALIVE.append(rig.backend)
        rig.configure()
        rec = rig.run_grid(**run_kw)
        do_threads = list(rec.do_threads)            # antes del cierre de limpieza del banco (hilo principal)
    return rec, do_threads


def test_every_chain_stage_runs_in_the_confocal_thread(monkeypatch, tmp_path):
    rec, do_threads = _run(monkeypatch, tmp_path)
    assert rec.finished, rec.decisions
    assert STAGES_RUN <= set(rec.stage_threads), sorted(rec.stage_threads)
    elsewhere = {stage: sorted(set(threads) - {"confocalThread"})
                 for stage, threads in rec.stage_threads.items() if set(threads) - {"confocalThread"}}
    assert not elsewhere, f"etapas fuera de confocalThread: {elsewhere}"
    # Las escrituras de los obturadores de la cadena también salen de confocalThread
    assert set(do_threads) <= {"confocalThread"}, Counter(do_threads)


def test_a_busy_gui_thread_does_not_decide_a_node_twice(monkeypatch, tmp_path):
    rec, _ = _run(monkeypatch, tmp_path, gui_period_s=0.25)
    assert rec.finished, rec.decision_events
    per_node = Counter(i for i, _ in rec.decision_events)
    assert sorted(per_node) == list(range(len(EXPECTED))), f"nodos salteados: {rec.decision_events}"
    assert all(n == 1 for n in per_node.values()), f"nodos decididos más de una vez: {rec.decision_events}"
    assert [s for _, s in rec.decision_events] == EXPECTED
