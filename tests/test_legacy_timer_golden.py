# -*- coding: utf-8 -*-
"""Línea de base dorada de la cadena de la grilla con `legacy_timer` (C-01 Ronda 4, fase 0; `ronda2_architecture.md` §9.3).

Se grabó sobre `927e818` (con el arreglo de la Pausa de DEC-041 y antes de cualquier cambio de R4-17), con el guion de
11 nodos de `tests/harness/grid_chain_rig.py` y sin cortes, paradas ni pausas. Se regrabó sobre `ec2e198` (fase 1, la
topología todavía repartida) cuando el banco pasó a arrancar cada grilla desde la misma posición de la platina simulada:
antes, el Z del primer autofoco dependía de las grillas que habían corrido antes en el mismo proceso (DEC-045). Sólo
cambiaron los `MOV` en Z; decisiones, ticks y log DO quedaron iguales. Cada fase de R4-17 tiene que dejar:
- las decisiones y el tick de decisión de cada nodo, idénticos;
- el log de `MOV`, idéntico;
- las transiciones de las líneas de los obturadores (cambios de nivel con su orden), idénticas;
- el log DO crudo, idéntico salvo el delta enumerado de la fase 3 (la apertura redundante de `trace._start`).

Fase 3b (DEC-046): la traza ya no reabre el obturador en modo de impresión. En la línea de base esa escritura figura
con el nombre de la envoltura del banco que la registraba (`open_and_reset`), una por nodo, y escribe el mismo
arreglo que la apertura de `_grid_trace` que la precede: no cambia ningún nivel. El test la quita de la línea de base
(`REMOVED_IN_PHASE_3B`) y exige que el resto del log crudo y las transiciones sean idénticos.

Para volver a grabar (sólo si una fase cambia la línea de base a propósito, con su entrada en DECISION_LOG):
`PYPRINTING_GOLDEN_RECORD=1 pytest tests/test_legacy_timer_golden.py`.
"""
import json
import os
from collections import Counter

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYPRINTING_SAFE", "1")

from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication(["pytest"])
GOLDEN = Path(__file__).resolve().parent / "golden" / "legacy_timer_chain.json"
REMOVED_IN_PHASE_3B = "open_and_reset"      # la reapertura de `trace._start`, una por nodo (fase 3b, DEC-046)
_KEEP_ALIVE = []


@pytest.fixture
def record(monkeypatch, tmp_path):
    from harness.grid_chain_rig import GridChainRig
    rig = GridChainRig(monkeypatch, tmp_path)
    with rig:
        _KEEP_ALIVE.append(rig.backend)
        rig.configure()
        rec = rig.run_grid()
    return rec


def test_the_scripted_grid_finishes_with_the_expected_decisions(record):
    assert record.finished, record.decisions
    assert [record.decisions[i] for i in range(11)] == [
        "success", "success", "timeout", "success", "success", "success", "timeout", "success", "success",
        "success", "success"]


def test_legacy_timer_matches_the_golden_baseline(record):
    data = record.as_golden()
    if os.environ.get("PYPRINTING_GOLDEN_RECORD") == "1":
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        pytest.skip(f"línea de base grabada en {GOLDEN}")
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert data["decisions"] == golden["decisions"]
    assert data["decision_ticks"] == golden["decision_ticks"]
    assert data["moves"] == golden["moves"]
    # Niveles de las líneas, en orden: idénticos. Quién escribe se compara como conjunto con repeticiones: al
    # decidir, el criterio y la traza (`_stop_and_save`) cierran el mismo obturador. Hasta la fase 2 lo hacían en
    # carrera desde dos hilos y la línea de base guarda uno de esos órdenes; desde la fase 2 (DEC-045) el orden es
    # fijo (primero la traza, que se detiene en forma sincrónica, y después el criterio).
    assert [t[:2] for t in data["transitions"]] == [t[:2] for t in golden["transitions"]]
    # El delta enumerado de la fase 3b: sólo desaparece la reapertura redundante de la traza, una por nodo, y cada
    # una repetía el arreglo de la escritura anterior (ningún nivel cambia)
    removed = [k for k, w in enumerate(golden["do_writes"]) if w[1] == REMOVED_IN_PHASE_3B]
    assert len(removed) == len(golden["decisions"])
    assert all(golden["do_writes"][k][0] == golden["do_writes"][k - 1][0] for k in removed)
    expected = [w for w in golden["do_writes"] if w[1] != REMOVED_IN_PHASE_3B]
    assert REMOVED_IN_PHASE_3B not in {w[1] for w in data["do_writes"]}
    assert [w[0] for w in data["do_writes"]] == [w[0] for w in expected]
    assert Counter(w[1] for w in data["do_writes"]) == Counter(w[1] for w in expected)
