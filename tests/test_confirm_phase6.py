# -*- coding: utf-8 -*-
"""Confirmación a baja potencia de los nodos interrumpidos (C-01 Ronda 4, R4-3 / R4-17 fase 6;
`ronda2_architecture.md` §4.8, §5.6; `c01_ronda4/experimentalist.md` §3; DEC-051).

**Entra apagada.** Estos tests la habilitan sólo dentro del test.

Contrato:
- `classify` en cada borde: "la ve" con R ≥ u_c; "no la ve" con R ≤ 1 + δ; "no sé" entre los dos, con dispersión
  alta, con R bajo el piso o sin base;
- la base es la meseta de alta potencia dividida por la atenuación de la sesión; sin atenuación, "no sé";
- apagada (por defecto): los nodos interrumpidos quedan en revisión y el Healing Pass no los toma;
- encendida, en el Healing Pass: "la ve" → impresa, no se reexpone; "no la ve" → se reimprime; "no sé" dos veces →
  revisión; un corte durante la lectura → no clasifica nada, revisión.
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYPRINTING_SAFE", "1")

from dataclasses import replace

import numpy as np
import pytest
from PyQt6.QtWidgets import QApplication

from core.confirm_read import (ConfirmConfig, ConfirmOutcome, base_from_high_plateau, classify)

_app = QApplication.instance() or QApplication(["pytest"])
_KEEP_ALIVE = []
CUT_NODE, CUT_READ = 3, 6


# ── El clasificador ─────────────────────────────────────────────────────────────────────────

DARK, BASE = 0.10, 0.20                                   # B_base = 0.10 V


def _blocks(r, jitter=0.0):
    return DARK + (BASE - DARK) * (np.full(5, r) + jitter * np.array([-1, -0.5, 0, 0.5, 1]))


@pytest.mark.parametrize("r,expect", [
    (1.30, ConfirmOutcome.SEEN), (1.20, ConfirmOutcome.SEEN),           # u_c = 1.20 incluido
    (1.00, ConfirmOutcome.NOT_SEEN), (1.05, ConfirmOutcome.NOT_SEEN),   # 1 + δ = 1.05 incluido
    (1.10, ConfirmOutcome.UNKNOWN), (1.19, ConfirmOutcome.UNKNOWN),     # entre los dos
    (0.84, ConfirmOutcome.UNKNOWN), (0.90, ConfirmOutcome.NOT_SEEN),    # el piso de 0.85
])
def test_classify_at_each_edge(r, expect):
    assert classify(_blocks(r), DARK, BASE).outcome == expect


def test_a_noisy_reading_or_no_base_is_unknown():
    assert classify(_blocks(1.3, jitter=0.2), DARK, BASE).outcome == ConfirmOutcome.UNKNOWN   # s_R alta
    assert classify(_blocks(1.3), DARK, None).outcome == ConfirmOutcome.UNKNOWN
    wide = ConfirmConfig(sigma_r=0.03)                                                        # δ = 0.09
    assert classify(_blocks(1.08), DARK, BASE, wide).outcome == ConfirmOutcome.NOT_SEEN


def test_the_base_is_the_high_plateau_over_the_session_attenuation():
    assert base_from_high_plateau(1.10, 0.10, 10.0) == pytest.approx(0.20)
    assert base_from_high_plateau(1.10, 0.10, None) is None                                   # sin BANCO-65 A
    assert ConfirmConfig().enabled is False                                                    # entra apagada


# ── La secuencia en la grilla ───────────────────────────────────────────────────────────────

@pytest.fixture
def rig(monkeypatch, tmp_path):
    from core import nidaq
    from harness.grid_chain_rig import GridChainRig
    monkeypatch.setattr(nidaq, "OPERATOR_HOLD_S", 0.5)
    r = GridChainRig(monkeypatch, tmp_path)
    with r:
        _KEEP_ALIVE.append(r.backend)
        r.configure(auto_complete_enabled=True)
        r.at_read(CUT_NODE, CUT_READ, r.close_all)       # el nodo 3 queda interrumpido (meseta: 1.0 V)
        yield r


class _ScriptedPD:
    """El fotodiodo de la lectura: el oscuro con el obturador cerrado, `v_open` con el obturador abierto."""

    def __init__(self, rig, v_open, dark=0.10, on_open_read=None):
        self.rig, self.v_open, self.dark, self.on_open_read = rig, v_open, dark, on_open_read
        self.open_reads = 0

    def __call__(self, rate, n, *a, **k):
        from core import nidaq
        outer = self

        class _Task:
            def read(self, m=None):
                is_open = outer.rig.backend.printingWorker.laser in nidaq.get_open_shutter_names()
                if is_open:
                    outer.open_reads += 1
                    if outer.on_open_read:
                        outer.on_open_read()
                v = outer.v_open if is_open else outer.dark
                return [list(np.full(int(n), v)) for _ in range(len(nidaq.PD_CHANS_LIST))]

            def wait_until_done(self):
                pass

            def close(self):
                pass
        return _Task()


def _enable(rig, monkeypatch, v_open, **pd_kw):
    pw = rig.backend.printingWorker
    pw.confirm_cfg = replace(pw.confirm_cfg, enabled=True, attenuation=10.0)    # base = 0.1 + 0.9/10 = 0.19 V
    pd = _ScriptedPD(rig, v_open, **pd_kw)
    monkeypatch.setattr(sys.modules[type(pw).__module__], "channels_photodiodos", pd)
    return pw, pd


def _retried(rec):
    return {i for i, s, _ in rec.status_log if s == "retrying"}


def test_disabled_the_interrupted_node_stays_in_review(rig):
    pw = rig.backend.printingWorker
    assert pw.confirm_cfg.enabled is False
    rec = rig.run_grid(timeout_s=90)
    assert rec.finished and pw.node_results[CUT_NODE] == "interrupted"
    assert CUT_NODE not in _retried(rec) and (CUT_NODE, 1) not in pw.exposed


def test_seen_marks_the_node_printed_and_never_reexposes_it(rig, monkeypatch):
    pw, pd = _enable(rig, monkeypatch, v_open=0.22)                          # R = 1.33
    rec = rig.run_grid(timeout_s=90)
    assert rec.finished, rec.decision_events
    assert pw.node_results[CUT_NODE] == "printed" and pw.node_confirm[CUT_NODE].outcome == ConfirmOutcome.SEEN
    assert (CUT_NODE, 1) not in pw.exposed and pd.open_reads == 1
    assert _retried(rec) == {2, 3, 6}


def test_not_seen_reprints_the_node(rig, monkeypatch):
    pw, pd = _enable(rig, monkeypatch, v_open=0.19)                          # R = 1.0
    rec = rig.run_grid(timeout_s=90)
    assert rec.finished
    assert pw.node_confirm[CUT_NODE].outcome == ConfirmOutcome.NOT_SEEN
    assert (CUT_NODE, 1) in pw.exposed                                        # se reimprimió en el Healing Pass
    assert pw.node_results[CUT_NODE] in ("success", "timeout")


def test_unknown_twice_leaves_the_node_in_review(rig, monkeypatch):
    pw, pd = _enable(rig, monkeypatch, v_open=0.20)                          # R = 1.11: "no sé"
    rec = rig.run_grid(timeout_s=90)
    assert rec.finished
    assert pd.open_reads == 2 and pw._confirm_reads[CUT_NODE] == 2
    assert pw.node_results[CUT_NODE] == "interrupted" and (CUT_NODE, 1) not in pw.exposed


def test_a_cut_during_the_read_classifies_nothing(rig, monkeypatch):
    pw = rig.backend.printingWorker
    from core import nidaq

    def cut():
        if pw.is_healing_pass:
            nidaq.operator_close_all("banco de pruebas")
    pw, pd = _enable(rig, monkeypatch, v_open=0.22, on_open_read=cut)
    rec = rig.run_grid(timeout_s=90)
    assert rec.finished
    assert CUT_NODE not in pw.node_confirm                                    # no clasificó nada
    assert pw.node_results[CUT_NODE] == "interrupted" and (CUT_NODE, 1) not in pw.exposed
