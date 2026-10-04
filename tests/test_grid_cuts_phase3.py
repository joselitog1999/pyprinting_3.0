# -*- coding: utf-8 -*-
"""Cortes de la grilla con `legacy_timer`: época de cierre, nodo interrumpido y espera de 3 s (C-01 Ronda 4, R4-17
fase 3; `ronda2_architecture.md` §4.1.1, §4.1.3, §4.6; DEC-046).

Antes, un "Cerrar todos" (o el botón del obturador, o una Pausa) durante la exposición dejaba la traza corriendo con
el obturador cerrado: la señal caía, el criterio lo decidía "timeout", el Healing Pass lo volvía a exponer y el nodo
siguiente abría en el acto. Un nodo que pudo haber impreso se reimprimía.

Contrato:
1. un corte durante la exposición → el nodo queda "interrupted" y nunca "timeout"; el Healing Pass no lo toma; el
   criterio no vuelve a latir en ese nodo; la traza guardada dice INTERRUPTED y el informe Time-Volt lo separa;
2. la primera apertura después de "Cerrar todos" llega ≥ la retención, y la grilla sigue sola;
3. un cierre que cae en la espera del filtro, antes de abrir (E-5), o justo antes de la apertura del autofoco:
   ninguna apertura durante la retención;
4. una Pausa durante la exposición → "interrupted" (no "timeout"); Play sigue con el nodo siguiente;
5. un "Cerrar todos" sin grilla y después Play → la grilla imprime normal, sin espera (E-12);
6. un segundo "Cerrar todos" durante la espera no la reinicia: cuenta desde el primero (respuesta 2, 2026-10-02);
7. un cierre del watchdog durante la exposición → "interrupted" y la grilla en pausa.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYPRINTING_SAFE", "1")

from collections import Counter
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication(["pytest"])
_KEEP_ALIVE = []

HOLD_S = 1.0                     # la retención de "Cerrar todos", acortada para los tests (en el equipo, 3 s)
EXPECTED = ["success", "success", "timeout", "success", "success", "success", "timeout", "success", "success",
            "success", "success"]
CUT_NODE, CUT_READ = 3, 6        # el nodo 3 captura en la lectura 15: el corte cae en plena exposición


@pytest.fixture
def rig(monkeypatch, tmp_path):
    from core import nidaq
    from harness.grid_chain_rig import GridChainRig
    monkeypatch.setattr(nidaq, "OPERATOR_HOLD_S", HOLD_S)
    r = GridChainRig(monkeypatch, tmp_path)
    with r:
        _KEEP_ALIVE.append(r.backend)
        yield r


def _laser_line(rig):
    import config
    return config.SHUTTERS.index(rig.backend.printingWorker.laser)


def _per_node(rec):
    return Counter(i for i, _ in rec.decision_events)


def _decisions(rec):
    return {i: s for i, s in rec.decision_events}


# ── 1 y 2: "Cerrar todos" (y el botón del obturador) durante la exposición ──────────────────

@pytest.mark.parametrize("cut", ["close_all", "close_laser"])
def test_a_close_during_the_exposure_interrupts_the_node_and_the_grid_goes_on(rig, cut):
    rig.configure(auto_complete_enabled=True)
    rig.at_read(CUT_NODE, CUT_READ, getattr(rig, cut))
    rec = rig.run_grid(timeout_s=90)
    pw = rig.backend.printingWorker
    assert rec.finished, rec.decision_events
    assert pw.node_results[CUT_NODE] == "interrupted"
    assert pw.node_meta[CUT_NODE].cause == "operator" and pw.node_meta[CUT_NODE].review
    # el Healing Pass reintenta los "timeout" (2 y 6), nunca el interrumpido
    retried = {i for i, s, _ in rec.status_log if s == "retrying"}
    assert retried == {2, 6}, rec.status_log
    primary = rec.decision_events[:11]                 # el pase principal: cada nodo una vez, en orden
    assert [i for i, _ in primary] == list(range(11)), rec.decision_events
    assert [s for i, s in primary if i != CUT_NODE] == [s for i, s in enumerate(EXPECTED) if i != CUT_NODE]
    assert Counter(i for i, _ in rec.decision_events[11:]) == Counter({2: 1, 6: 1})
    # el criterio no vuelve a latir en el nodo cortado después del corte
    t_cut = rec.cut_times[0]
    assert not [t for i, t in rec.heartbeats if i == CUT_NODE and t > t_cut + 1e-3], "latido después del corte"
    # 2: la primera apertura después del corte respeta la retención
    first_open = rec.line_opens(_laser_line(rig), after_t=t_cut)[0]
    assert first_open - t_cut >= HOLD_S, first_open - t_cut
    # la traza guardada y el informe Time-Volt
    header = (Path(pw.new_folder) / f"NP_{CUT_NODE:03d}.txt").read_text(encoding="utf-8").splitlines()[0]
    assert "INTERRUPTED (operator" in header and "TIMEOUT" not in header, header


def test_the_time_volt_report_keeps_the_interrupted_node_apart(rig):
    rig.configure()
    rig.at_read(CUT_NODE, CUT_READ, rig.close_all)
    rec = rig.run_grid(timeout_s=60)
    assert rec.finished
    pw = rig.backend.printingWorker
    pw.grid_name = "corte"
    pw._generate_time_volt_report(pw.new_folder)
    report = (Path(pw.new_folder) / "reporte_parametros_corte.txt").read_text(encoding="utf-8")
    assert "Nodos Interrumpidos (en revisión): 1" in report
    assert f"{CUT_NODE:03d}: Status: INTERRUPTED (operator" in report
    assert "Partículas Totales Analizadas:     10" in report       # el interrumpido no entra en las estadísticas


# ── 3: un cierre antes de abrir (E-5) ────────────────────────────────────────────────────────

def test_a_close_during_the_filter_wait_holds_the_opening(rig, monkeypatch):
    """El cierre cae después de bajar el filtro y antes de abrir: el nodo no se expone durante la retención, se
    reintenta cuando vence y se imprime normal (nunca expuesto: no queda interrumpido)."""
    import sys
    rig.configure()
    pw = rig.backend.printingWorker
    meas = sys.modules[type(pw).__module__]
    real_down = meas.down_flipper
    fired = []

    def down_then_close(*a, **k):
        out = real_down(*a, **k)
        if pw.i_global == 4 and not fired:
            fired.append(1)
            rig.close_all()                            # en el hilo de la cadena, en la espera del filtro
        return out
    monkeypatch.setattr(meas, "down_flipper", down_then_close)
    rec = rig.run_grid(timeout_s=60)
    assert rec.finished and fired
    t_cut = rec.cut_times[0]
    opens = rec.line_opens(_laser_line(rig), after_t=t_cut)
    assert opens and opens[0] - t_cut >= HOLD_S, [o - t_cut for o in opens]
    assert _decisions(rec)[4] == "success" and all(n == 1 for n in _per_node(rec).values())


@pytest.mark.parametrize("which", [1, 2], ids=["en el auto-lock", "en las rampas del autofoco"])
def test_a_close_right_before_a_focus_opening_holds_it_and_z_is_not_corrected(rig, monkeypatch, which):
    """El primer autofoco de la grilla abre dos veces: el "auto-lock" (fija el perfil de referencia) y las rampas del
    autofoco. Un "Cerrar todos" justo antes de cualquiera de las dos: la apertura queda retenida, no se barre con el
    obturador cerrado y Z vuelve a donde estaba."""
    import sys
    rig.configure()
    focus_mod = sys.modules[type(rig.backend.focusWorker).__module__]
    real_open = focus_mod.open_shutter
    results = []

    def close_then_open(name, *a, **k):
        if len(results) == which - 1:
            rig.close_all()
        ok = real_open(name, *a, **k)
        results.append(ok)
        return ok
    monkeypatch.setattr(focus_mod, "open_shutter", close_then_open)
    rec = rig.run_grid(timeout_s=60)
    assert rec.finished
    assert results[which - 1] is False                 # la apertura del foco fue retenida
    t_cut = rec.cut_times[0]
    opens = rec.line_opens(_laser_line(rig), after_t=t_cut)
    assert opens and opens[0] - t_cut >= HOLD_S
    assert [_decisions(rec)[i] for i in range(11)] == EXPECTED
    # Sólo las dos rampas del lock (bajar al inicio y volver), o su vuelta si no pudo abrir: ninguna rampa del
    # autofoco y ninguna corrección de Z sobre la oscuridad
    assert [m for m in rec.moves if len(m) == 1] == [(6.25,), (10.0,)], rec.moves
    # con el lock retenido, el foco no queda fijado sobre un perfil oscuro; con el lock bueno, sí queda fijado
    assert rig.backend.focusWorker.locked_focus is (which == 2)


# ── 4: la Pausa durante la exposición ────────────────────────────────────────────────────────

def test_a_pause_during_the_exposure_interrupts_the_node_and_play_goes_to_the_next(rig):
    rig.configure()
    rig.at_read(CUT_NODE, CUT_READ, rig.pause)
    pw = rig.backend.printingWorker
    rig.run_grid(timeout_s=60, until=lambda: CUT_NODE in rig.record.decisions and pw.is_paused)
    rec = rig.record
    assert _decisions(rec)[CUT_NODE] == "interrupted" and pw.node_meta[CUT_NODE].cause == "pause"
    n_moves = len(rec.moves)
    rig.wait_until(lambda: False, timeout_s=0.5)       # en pausa no se abre ni se mueve nada
    assert not rec.line_opens(_laser_line(rig), after_t=rec.cut_times[0])
    assert len(rec.moves) == n_moves
    rig.play()
    assert rig.wait_until(lambda: rec.finished, timeout_s=60), rec.decision_events
    target = (round(40.0 + 2.0 * CUT_NODE, 4), 40.0)
    assert [m for m in rec.moves if m == target] == [target]        # el nodo cortado se expuso una sola vez
    assert all(n == 1 for n in _per_node(rec).values()), rec.decision_events


# ── 5: "Cerrar todos" sin grilla (E-12) ──────────────────────────────────────────────────────

def test_a_close_all_without_a_grid_does_not_hold_the_next_grid(rig):
    import time as _t
    from core import nidaq
    rig.configure()
    t0 = _t.monotonic()
    nidaq.operator_close_all("antes de la grilla")
    assert nidaq.get_open_hold_remaining_s() == 0.0    # sin rutina corriendo, no retiene
    rec = rig.run_grid(timeout_s=60)
    assert rec.finished and [_decisions(rec)[i] for i in range(11)] == EXPECTED
    first_open = rec.line_opens(_laser_line(rig))[0]
    assert first_open - t0 < HOLD_S


# ── 6: un segundo "Cerrar todos" durante la espera ───────────────────────────────────────────

def test_a_second_close_all_during_the_wait_does_not_restart_it(rig):
    rig.configure()

    def first():
        rig.close_all()
        rig.after(0.5 * HOLD_S, rig.close_all)
    rig.at_read(CUT_NODE, CUT_READ, first)
    rec = rig.run_grid(timeout_s=60)
    assert rec.finished and len(rec.cut_times) == 2
    t1, t2 = rec.cut_times
    first_open = rec.line_opens(_laser_line(rig), after_t=t2)[0]
    assert first_open - t1 >= HOLD_S                   # respeta la retención del primer cierre
    assert first_open - t2 < HOLD_S                    # y no la reinicia el segundo
    assert _decisions(rec)[CUT_NODE] == "interrupted"
    assert all(n == 1 for n in _per_node(rec).values())


# ── 7: el watchdog ───────────────────────────────────────────────────────────────────────────

def test_a_watchdog_close_during_the_exposure_interrupts_and_pauses(rig):
    from core import nidaq
    rig.configure()
    pw = rig.backend.printingWorker
    rig.at_read(CUT_NODE, CUT_READ,
                lambda: (rig.record.cut_times.append(__import__("time").monotonic()),
                         nidaq.close_all_shutters(nidaq.CloseCause.WATCHDOG, "banco de pruebas")))
    rig.run_grid(timeout_s=60, until=lambda: CUT_NODE in rig.record.decisions and pw.is_paused)
    rec = rig.record
    assert _decisions(rec)[CUT_NODE] == "interrupted" and pw.node_meta[CUT_NODE].cause == "watchdog"
    assert pw.is_paused
    rig.wait_until(lambda: False, timeout_s=0.5)
    assert not rec.line_opens(_laser_line(rig), after_t=rec.cut_times[0])


# ── 8: la Pausa durante la espera de "Cerrar todos" ──────────────────────────────────────────

def test_a_pause_during_the_wait_keeps_the_grid_paused_and_play_goes_to_the_next(rig):
    rig.configure()
    pw = rig.backend.printingWorker

    def close_then_pause():
        rig.close_all()
        rig.after(0.4 * HOLD_S, rig.pause)
    rig.at_read(CUT_NODE, CUT_READ, close_then_pause)
    rig.run_grid(timeout_s=60, until=lambda: len(rig.record.cut_times) == 2 and pw.is_paused)
    rec = rig.record
    rig.wait_until(lambda: False, timeout_s=1.5 * HOLD_S)   # vence la retención: en pausa, la grilla no sigue
    assert not rec.line_opens(_laser_line(rig), after_t=rec.cut_times[0])
    assert max(rec.decisions) == CUT_NODE and rec.decisions[CUT_NODE] == "interrupted"
    rig.play()
    assert rig.wait_until(lambda: rec.finished, timeout_s=60), rec.decision_events
    assert all(n == 1 for n in _per_node(rec).values()) and len(_per_node(rec)) == 11


# ── La Pausa no mueve la platina: stop_scan sin escaneo en curso ─────────────────────────────

def test_stop_scan_without_a_running_scan_does_not_move_the_stage(monkeypatch):
    import modules.confocal as conf
    moves = []
    monkeypatch.setattr(conf.pi, "MOV", lambda axes, targets: moves.append((axes, targets)))
    monkeypatch.setattr(conf, "close_shutter", lambda *a, **k: True)
    be = conf.Backend()
    _KEEP_ALIVE.append(be)
    be.mode_printing = "none"
    be.stop_scan()                                     # la Pausa de la grilla lo llama por grid_scan_stopSignal
    assert moves == []


# ── 3b: la traza no reabre con un modo de impresión ──────────────────────────────────────────

def test_the_trace_does_not_reopen_the_shutter_in_printing_mode(monkeypatch):
    """La apertura del nodo es de la grilla, que anota la época y mira si abrió. Una segunda apertura en
    `trace._start` reabría el láser si un "Cerrar todos" caía entre las dos (R4-17 fase 3b, DEC-046). La traza manual
    (sin modo de impresión) abre como siempre."""
    import config
    import modules.trace as trace_mod
    opens = []
    monkeypatch.setattr(trace_mod, "open_shutter", lambda name, *a, **k: opens.append(name) or True)
    be = trace_mod.Backend()
    _KEEP_ALIVE.append(be)
    be.trace_configuration(config.SHUTTERS[0], "printing")
    be.stop()
    assert opens == []
    be.mode_printing = "none"
    be.laser1, be.laser2 = config.SHUTTERS[0], "None"
    be._start()
    be.stop()
    assert opens == [config.SHUTTERS[0]]
