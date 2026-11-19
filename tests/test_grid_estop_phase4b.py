# -*- coding: utf-8 -*-
"""La grilla ante la parada de emergencia: detenida, Rearmar, Play y reanudación (C-01 Ronda 4, R4-17 fase 4b;
`ronda2_architecture.md` §4.4-§4.6; DEC-048).

Contrato:
4. una parada en cualquier etapa → cero MOV y cero aperturas hasta Rearmar **y** Play; el nodo en exposición queda
   "interrupted" con la causa "estop";
5. Play detenida no hace nada (defensa en el motor); Rearmar sólo cuando la grilla está quieta;
6. después de rearmar la grilla queda en PAUSA, y la primera apertura es posterior al Play;
7. la reanudación es en el primer nodo que nunca se expuso (E-3);
8. con una parada de más de 60 s, antes del primer nodo se vuelve a enfocar;
9. antes de la primera acción al reanudar, el filtro en baja potencia confirmado hace ≥ 100 ms; si la placa no
   confirma el filtro, la grilla pausa (respuesta 5).
"""
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYPRINTING_SAFE", "1")

from collections import Counter

import pytest
from PyQt6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication(["pytest"])
_KEEP_ALIVE = []

EXPECTED = ["success", "success", "timeout", "success", "success", "success", "timeout", "success", "success",
            "success", "success"]
CUT_NODE, CUT_READ = 3, 6


@pytest.fixture
def rig(monkeypatch, tmp_path):
    from core import nidaq
    from harness.grid_chain_rig import GridChainRig
    monkeypatch.setattr(nidaq, "OPERATOR_HOLD_S", 1.0)
    r = GridChainRig(monkeypatch, tmp_path)
    with r:
        _KEEP_ALIVE.append(r.backend)
        r.configure()
        yield r


def _laser_line(rig):
    import config
    return config.SHUTTERS.index(rig.backend.printingWorker.laser)


def _meas(rig):
    return sys.modules[type(rig.backend.printingWorker).__module__]


def _primary(rec):
    """Las decisiones del pase principal, una por nodo."""
    out = {}
    for i, s in rec.decision_events:
        out.setdefault(i, s)
    return out


def _stop_at(rig, monkeypatch, where):
    """Programa la parada en una etapa de la cadena."""
    pw = rig.backend.printingWorker
    if where == "exposición":
        rig.at_read(CUT_NODE, CUT_READ, rig.estop)
    elif where == "espera del filtro":                         # nodo 5, después de bajar el filtro, antes de abrir
        meas = _meas(rig)
        real_down, fired = meas.down_flipper, []

        def down_then_stop(*a, **k):
            out = real_down(*a, **k)
            if pw.i_global == 5 and not fired:
                fired.append(1)
                rig.estop()
            return out
        monkeypatch.setattr(meas, "down_flipper", down_then_stop)
    elif where == "autofoco":                                  # justo antes de la apertura del primer autofoco
        focus_mod = sys.modules[type(rig.backend.focusWorker).__module__]
        real_open, fired = focus_mod.open_shutter, []

        def stop_then_open(name, *a, **k):
            if not fired:
                fired.append(1)
                rig.estop()
            return real_open(name, *a, **k)
        monkeypatch.setattr(focus_mod, "open_shutter", stop_then_open)
    elif where == "espera de Cerrar todos":
        def close_then_stop():
            rig.close_all()
            rig.after(0.3, rig.estop)
        rig.at_read(CUT_NODE, CUT_READ, close_then_stop)
    else:
        raise ValueError(where)


def _stopped(rig):
    from core.grid_state import GridRunState
    return lambda: rig.backend.printingWorker.run_state == GridRunState.STOPPED


# ── 4, 5 y 6: cero MOV y cero aperturas hasta Rearmar y Play ─────────────────────────────────

@pytest.mark.parametrize("where", ["exposición", "espera del filtro", "autofoco", "espera de Cerrar todos"])
def test_a_stop_in_any_stage_moves_and_opens_nothing_until_rearm_and_play(rig, monkeypatch, where):
    from core.grid_state import GridRunState
    pw = rig.backend.printingWorker
    meas = _meas(rig)
    real_up, worker_ups = meas.up_flipper, []

    def logged_up(*a, **k):
        worker_ups.append(time.monotonic())
        return real_up(*a, **k)
    monkeypatch.setattr(meas, "up_flipper", logged_up)
    _stop_at(rig, monkeypatch, where)
    rig.run_grid(timeout_s=60, until=_stopped(rig))
    rec = rig.record
    assert pw.run_state == GridRunState.STOPPED, pw.run_state
    t_stop = rec.cut_times[-1]
    line = _laser_line(rig)
    rig.wait_until(lambda: False, timeout_s=0.6)
    rig.play()                                                 # Play detenida: el motor lo rechaza
    rig.wait_until(lambda: False, timeout_s=0.3)
    assert rec.executed_moves(after_t=t_stop) == [] and rec.line_opens(line, after_t=t_stop) == []
    if where == "exposición":
        # detenida, el worker no toca el filtro: lo sube el cerrador después del cierre confirmado
        assert [t for t in worker_ups if t > t_stop] == []
    assert rig.rearm(), "no se pudo rearmar"
    assert pw.run_state == GridRunState.PAUSED and pw.is_paused
    rig.wait_until(lambda: False, timeout_s=0.3)
    assert rec.executed_moves(after_t=t_stop) == [] and rec.line_opens(line, after_t=t_stop) == []
    t_play = time.monotonic()
    rig.play()
    assert rig.wait_until(lambda: rec.finished, timeout_s=90), rec.decision_events
    opens = rec.line_opens(line, after_t=t_stop)
    assert opens and min(opens) > t_play                       # la primera apertura, después del Play
    assert all(n == 1 for n in Counter(i for i, _ in rec.decision_events).values()), rec.decision_events
    assert all(n == 1 for n in Counter(pw.exposed).values())
    if where in ("exposición", "espera de Cerrar todos"):
        assert pw.node_results[CUT_NODE] == "interrupted"
        assert pw.node_meta[CUT_NODE].cause == ("estop" if where == "exposición" else "operator")


# ── 7: la reanudación en el primer nodo nunca expuesto (E-3) ─────────────────────────────────

def test_resume_goes_to_the_first_never_exposed_node(rig, monkeypatch):
    pw = rig.backend.printingWorker
    _stop_at(rig, monkeypatch, "espera del filtro")            # el nodo 5 no llegó a abrir
    rig.run_grid(timeout_s=60, until=_stopped(rig))
    rec = rig.record
    assert (5, 0) not in pw.exposed and 5 not in pw.node_results
    assert rig.rearm()
    rig.play()
    assert rig.wait_until(lambda: rec.finished, timeout_s=90)
    d = _primary(rec)
    assert [d[i] for i in range(11)] == EXPECTED               # el 5 se imprimió al reanudar, sin saltear ninguno


def test_resume_after_a_stop_in_the_exposure_goes_to_the_next_node(rig, monkeypatch):
    pw = rig.backend.printingWorker
    _stop_at(rig, monkeypatch, "exposición")
    rig.run_grid(timeout_s=60, until=_stopped(rig))
    rec = rig.record
    assert rig.rearm()
    rig.play()
    assert rig.wait_until(lambda: rec.finished, timeout_s=90)
    target = (round(40.0 + 2.0 * CUT_NODE, 4), 40.0)
    assert [m for m in rec.executed_moves() if m == target] == [target]   # el interrumpido no se reexpone
    d = _primary(rec)
    assert [d[i] for i in range(11) if i != CUT_NODE] == [s for i, s in enumerate(EXPECTED) if i != CUT_NODE]


def test_a_node_whose_healing_retry_was_cut_is_not_exposed_again(rig):
    """En el Healing Pass el nodo ya tiene el "timeout" del pase principal: lo que dice que el reintento llegó a
    abrir es el registro de exposiciones (nodo, intento 1)."""
    pw = rig.backend.printingWorker
    pw.auto_complete_enabled = True

    def stop_in_the_retry():
        if pw.is_healing_pass:
            rig.estop()
        else:
            rig.at_read(2, CUT_READ, stop_in_the_retry)        # el pase principal: esperar al reintento
    rig.at_read(2, CUT_READ, stop_in_the_retry)
    rig.run_grid(timeout_s=90, until=lambda: pw.is_healing_pass and pw.node_results.get(2) == "interrupted")
    rec = rig.record
    assert _stopped(rig)() and (2, 1) in pw.exposed
    assert rig.rearm()
    rig.play()
    assert rig.wait_until(lambda: rec.finished, timeout_s=90), rec.decision_events
    retried = Counter(i for i, s, _ in rec.status_log if s == "retrying")
    assert retried[2] == 1, rec.status_log                     # no se volvió a reintentar el nodo cortado
    assert retried[6] == 1


# ── 8: el reenfoque después de una parada larga ──────────────────────────────────────────────

@pytest.mark.parametrize("long_stop", [False, True], ids=["parada corta", "parada de más de 60 s"])
def test_a_long_stop_refocuses_before_the_first_node(rig, monkeypatch, long_stop):
    from core.grid_state import RESUME_REFOCUS_AFTER_S
    pw = rig.backend.printingWorker
    _stop_at(rig, monkeypatch, "exposición")
    rig.run_grid(timeout_s=60, until=_stopped(rig))
    rec = rig.record
    assert rig.rearm()
    if long_stop:
        pw.t_halt -= RESUME_REFOCUS_AFTER_S + 1.0            # como si la parada hubiera durado más de un minuto
    t_play = time.monotonic()
    rig.play()
    assert rig.wait_until(lambda: rec.finished, timeout_s=90)
    z_after = [m for m in rec.executed_moves(after_t=t_play) if len(m) == 1]
    assert bool(z_after) is long_stop, z_after                 # las rampas del autofoco, sólo después de > 60 s


# ── 9: la compuerta de baja potencia al reanudar ─────────────────────────────────────────────

def test_resume_waits_100_ms_after_a_confirmed_low_power(rig, monkeypatch):
    from core import nidaq
    pw = rig.backend.printingWorker
    _stop_at(rig, monkeypatch, "exposición")
    rig.run_grid(timeout_s=60, until=_stopped(rig))
    rec = rig.record
    assert rig.rearm()
    monkeypatch.setattr(nidaq, "_low_power_confirmed_at", None)   # el filtro sin confirmar (p. ej. falló en la parada)
    meas = _meas(rig)
    real_up, ups = meas.up_flipper, []

    def logged_up(*a, **k):
        ok = real_up(*a, **k)
        ups.append((time.monotonic(), ok))
        return ok
    monkeypatch.setattr(meas, "up_flipper", logged_up)
    t_play = time.monotonic()
    rig.play()
    assert rig.wait_until(lambda: rec.finished, timeout_s=90)
    t_up = next(t for t, ok in ups if ok and t > t_play)
    first_move = next(t for t, m, ok in rec.move_results if ok and t > t_play)
    assert first_move - t_up >= nidaq.LOW_POWER_SETTLE_S, first_move - t_up


def test_an_unconfirmed_filter_pauses_the_resume(rig, monkeypatch):
    from core import nidaq
    from core.grid_state import GridRunState
    pw = rig.backend.printingWorker
    _stop_at(rig, monkeypatch, "exposición")
    rig.run_grid(timeout_s=60, until=_stopped(rig))
    rec = rig.record
    assert rig.rearm()
    monkeypatch.setattr(nidaq, "_low_power_confirmed_at", None)
    monkeypatch.setattr(_meas(rig), "up_flipper", lambda *a, **k: False)   # la placa no confirma el filtro
    t_play = time.monotonic()
    rig.play()
    assert rig.wait_until(lambda: pw.run_state == GridRunState.PAUSED and pw.is_paused, timeout_s=5)
    rig.wait_until(lambda: False, timeout_s=0.3)
    assert rec.executed_moves(after_t=t_play) == [] and rec.line_opens(_laser_line(rig), after_t=t_play) == []


# ── Las barreras de cada participante, una por una (otra capa las taparía en la grilla) ──────

def test_grid_move_does_not_even_try_to_move_during_the_stop(monkeypatch):
    """Barrera 2: `_grid_move` no llega al driver (la retención del driver, la barrera 4, la taparía)."""
    import config
    import modules.measurements as meas
    from core import emergency_stop
    tried = []
    monkeypatch.setattr(meas.pi, "MOV", lambda axes, tg: tried.append(tg) or True)
    monkeypatch.setattr(type(meas.pi), "connected", property(lambda self: True))   # que no la frene otra guarda
    pw = meas.Backend(mode="printing")
    _KEEP_ALIVE.append(pw)
    pw.grid_x, pw.grid_y, pw.startX, pw.startY, pw.i_global = [0.0, 1.0], [0.0, 0.0], 50.0, 50.0, 0
    emergency_stop.get_emergency_coordinator().trigger("test")
    pw._grid_move()
    pw.grid_next_index()
    assert tried == []


def test_the_manual_trace_stops_at_the_first_tick_after_the_stop(monkeypatch):
    import modules.trace as trace_mod
    from core import emergency_stop
    be = trace_mod.Backend()
    _KEEP_ALIVE.append(be)
    aborted = []
    be.traceAbortedSignal.connect(lambda m, c: aborted.append((m, c)))
    monkeypatch.setattr(trace_mod, "open_shutter", lambda *a, **k: True)
    be.mode_printing = "none"
    be.laser1, be.laser2 = trace_mod.SHUTTERS[0], "None"
    be._start()
    assert be.pointtimer.isActive()
    emergency_stop.get_emergency_coordinator().trigger("test")
    be._trace_update()
    assert not be.pointtimer.isActive() and be.is_quiescent()
    assert aborted == []                                       # sin modo de impresión no hay a quién avisar
    be.mode_printing = "printing"
    be._trace_update()
    assert aborted == [("printing", "estop")]


def test_a_confocal_scan_tick_after_the_stop_stops_without_moving(monkeypatch):
    from PyQt6.QtCore import QTimer
    import modules.confocal as conf
    tried = []
    monkeypatch.setattr(conf.pi, "MOV", lambda axes, tg: tried.append(tg) or True)
    be = conf.Backend()
    _KEEP_ALIVE.append(be)
    finished = []
    be.scanfinishedSignal.connect(lambda *a: finished.append(a))
    be.PDtimer_rampxy = QTimer()
    be.PDtimer_rampxy.start(1000)
    be.on_emergency_stop(1)
    assert not be.is_quiescent()
    be._scan_ramp_xy()
    assert tried == [] and finished == [] and be.is_quiescent()
    be.on_rearmed(1)
    assert be._estop_abort is False


def test_the_autofocus_does_not_ramp_after_the_stop(monkeypatch):
    import modules.focus as focus_mod
    ramps = []
    monkeypatch.setattr(focus_mod, "open_shutter", lambda *a, **k: True)
    monkeypatch.setattr(focus_mod, "close_shutter", lambda *a, **k: True)
    be = focus_mod.Backend(connect_stage=False)
    _KEEP_ALIVE.append(be)
    be.locked_focus = True
    monkeypatch.setattr(be, "_focus_autocorr_lin", lambda: ramps.append(1))
    done = []
    be.autofocusFinished.connect(lambda m, r: done.append(m))
    be.on_emergency_stop(1)
    be.focus_autocorr_lin_x2("printing")
    assert ramps == [] and done == ["printing"] and be.is_quiescent()


def test_the_grid_is_not_quiescent_while_a_stage_runs(monkeypatch):
    import modules.measurements as meas
    pw = meas.Backend(mode="printing")
    _KEEP_ALIVE.append(pw)
    seen = []
    monkeypatch.setattr(pw, "_grid_start", lambda: seen.append(pw.is_quiescent()))
    pw.mode_printing = "none"
    assert pw.is_quiescent()
    pw.grid_measurment()
    assert seen == [False] and pw.is_quiescent()
