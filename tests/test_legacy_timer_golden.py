# -*- coding: utf-8 -*-
"""Línea de base dorada de la cadena de la grilla con `legacy_timer` (C-01 Ronda 4, fase 0; `ronda2_architecture.md` §9.3).

Se grabó sobre `927e818` (con el arreglo de la Pausa de DEC-041 y antes de cualquier cambio de R4-17), con el guion de
11 nodos de `tests/harness/grid_chain_rig.py` y sin cortes, paradas ni pausas. Cada fase de R4-17 tiene que dejar:
- las decisiones y el tick de decisión de cada nodo, idénticos;
- el log de `MOV`, idéntico;
- las transiciones de las líneas de los obturadores (cambios de nivel con su orden), idénticas;
- el log DO crudo, idéntico salvo el delta enumerado de la fase 3 (la apertura redundante de `trace._start`).

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
    # Niveles de las líneas, en orden: idénticos. Quién escribe se compara como conjunto con repeticiones: hoy,
    # al decidir, el criterio (hilo GUI) y la traza (`_stop_and_save`, confocalThread) cierran el mismo obturador
    # en carrera, y el orden entre los dos varía de una corrida a otra (fase 2 de R4-17: la cadena a un hilo).
    assert [t[:2] for t in data["transitions"]] == [t[:2] for t in golden["transitions"]]
    assert [w[0] for w in data["do_writes"]] == [w[0] for w in golden["do_writes"]]
    assert Counter(w[1] for w in data["do_writes"]) == Counter(w[1] for w in golden["do_writes"])
