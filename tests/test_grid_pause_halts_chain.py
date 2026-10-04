# -*- coding: utf-8 -*-
"""La Pausa detiene la cadena de la grilla en cualquier etapa (C-01 Ronda 4, pregunta 1; 2026-10-01).

Defecto (instrumentación, `c01_ronda4/instrumentation.md`; también en `7f5d10a`): el fin del autofoco se despacha
al hilo GUI (`app.py::_on_autofinish`) y la Pausa llega encolada al hilo de los workers. Si la Pausa cae
durante el autofoco, corre primero (cierra y pone `mode_printing = "none"`) y después el hilo GUI sigue con
`grid_finish_autofoco` → `_grid_trace`: baja el filtro y **abre el 532 a alta potencia**. La traza arranca en
modo "none", no le manda datos al criterio, nada cierra, y el latido de la traza renueva el watchdog.

Contrato:
- el clic en Pausa marca un evento entre hilos en el acto (sin esperar a que corra `grid_pause`);
- cada entrada de la cadena (después de mover, fin del autofoco, traza, escaneo, detección, Healing Pass)
  no sigue si la grilla está en pausa: no mueve la platina, no cambia el filtro, no abre;
- `_grid_trace` es la última barrera: no abre en pausa ni con `mode_printing == "none"`;
- Play (reanudar) limpia la pausa y la grilla sigue como antes; sin pausa, nada cambia;
- una Pausa durante la exposición deja el nodo "interrupted" y Play sigue con el próximo (R4-17 fase 3, DEC-046).
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYPRINTING_SAFE", "1")

import types

import numpy as np
import pytest
from PyQt6 import QtCore
from PyQt6.QtWidgets import QApplication

import config
import modules.measurements as meas

_app = QApplication.instance() or QApplication([])
_KEEP_ALIVE = []


@pytest.fixture
def grid(monkeypatch):
    """Un worker de impresión con una grilla de dos nodos, sin esperas, que registra lo que hace."""
    log = []
    monkeypatch.setattr(meas, "time", types.SimpleNamespace(sleep=lambda s: None, time=__import__("time").time))
    monkeypatch.setattr(meas, "open_shutter", lambda name, *a, **k: log.append(("open", name)) or True)
    monkeypatch.setattr(meas, "close_shutter", lambda name, *a, **k: log.append(("close", name)) or True)
    monkeypatch.setattr(meas, "down_flipper", lambda *a, **k: log.append(("filter", "high")) or True)
    monkeypatch.setattr(meas, "up_flipper", lambda *a, **k: log.append(("filter", "low")) or True)
    real_mov = meas.pi.MOV
    # La platina simulada figura desconectada y la cadena se cortaría antes por otra vía (DEC-036): acá tiene
    # que estar conectada para que el test vea lo que hace la pausa.
    monkeypatch.setattr(type(meas.pi), "connected", property(lambda self: True))
    monkeypatch.setattr(meas.pi, "MOV", lambda axes, tg: log.append(("MOV", tuple(np.atleast_1d(tg)))) or real_mov(axes, tg))
    pw = meas.Backend(mode="printing")
    _KEEP_ALIVE.append(pw)
    for sig in (pw.grid_traceSignal, pw.grid_autofocusSignal, pw.grid_scanSignal, pw.grid_move_finishSignal,
                pw.grid_detectSignal):
        sig.connect(lambda *a, s=sig: log.append(("emit", s.signal if hasattr(s, "signal") else str(s))))
    pw.laser = config.SHUTTERS[0]
    pw.mode_arg = "printing"
    pw.mode_printing = "printing"
    pw.grid_x = np.array([0.0, 1.0])
    pw.grid_y = np.array([0.0, 0.0])
    pw.startX = pw.startY = 50.0
    pw.xref = pw.yref = 50.0
    pw.i_global = 0
    pw.particulas = 2
    pw.autofocus_stage = "standard_autofocus"
    pw.zref = 10.0
    pw.is_paused = False
    return pw, log


def _opens(log):
    return [e for e in log if e[0] == "open"]


def _after(log, marker):
    return log[log.index(marker) + 1:] if marker in log else list(log)


# ── El defecto ──────────────────────────────────────────────────────────────────────────────

def test_a_pause_during_autofocus_does_not_open_the_532(grid):
    pw, log = grid
    pw.grid_pause()                       # corre en el hilo de los workers apenas termina el autofoco
    log.append("PAUSE")
    pw.grid_finish_autofoco()             # el hilo GUI sigue con el fin del autofoco
    after = _after(log, "PAUSE")
    assert _opens(after) == [], after
    assert ("filter", "high") not in after and not [e for e in after if e[0] == "MOV"], after


def test_the_pause_click_marks_the_grid_before_grid_pause_runs(grid):
    """El clic marca la pausa en el acto: `grid_pause` llega encolada y puede correr tarde."""
    pw, log = grid
    fe = meas.Frontend("printing") if _frontend_takes_mode() else meas.Frontend()
    _KEEP_ALIVE.append(fe)
    worker_thread = QtCore.QThread()                 # nunca arranca: lo encolado no corre
    _KEEP_ALIVE.append(worker_thread)
    pw.moveToThread(worker_thread)
    pw.make_connection(fe)
    from core.grid_state import GridRunState
    pw.run_state = GridRunState.RUNNING              # Pausa se habilita sólo con la grilla corriendo (R4-17 fase 4c)
    assert fe.pause_button.isEnabled()
    fe.pause_button.click()
    assert pw.grid_halted()                           # sin procesar eventos
    log.append("PAUSE")
    pw.grid_finish_autofoco()
    assert _opens(_after(log, "PAUSE")) == []


def _frontend_takes_mode():
    import inspect
    try:
        return "mode" in inspect.signature(meas.Frontend.__init__).parameters
    except (TypeError, ValueError):
        return False


# ── Cada entrada de la cadena ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("entry", ["grid_autofoco", "grid_finish_autofoco", "_grid_trace", "grid_scan",
                                   "_grid_detect", "_grid_center_scan"])
def test_no_entry_of_the_chain_moves_or_opens_while_paused(grid, entry):
    pw, log = grid
    pw.scanbool = True                                # con el escaneo posterior activo, grid_scan emitiría
    pw.grid_pause()
    log.append("PAUSE")
    getattr(pw, entry)()
    after = _after(log, "PAUSE")
    assert _opens(after) == [] and not [e for e in after if e[0] in ("MOV", "emit")], (entry, after)
    assert not [e for e in after if e[0] == "filter"], (entry, after)   # tampoco toca el filtro


def test_a_scan_that_finishes_after_the_pause_does_not_continue(grid):
    pw, log = grid
    pw.grid_pause()
    log.append("PAUSE")
    img = np.zeros((4, 4))
    pw.on_scan_finished(img, [50.1, 50.1], img, img, "printing", "drift_scan")
    after = _after(log, "PAUSE")
    assert _opens(after) == [] and not [e for e in after if e[0] in ("MOV", "emit")], after
    assert pw.startX == 50.0                          # una corrección que llegó en pausa no se aplica


def test_the_healing_pass_does_not_advance_while_paused(grid):
    pw, log = grid
    pw.is_healing_pass = True
    pw.healing_failed_queue = [1]
    pw.healing_index_in_queue = 0
    pw.grid_pause()
    log.append("PAUSE")
    pw._advance_healing_pass()
    after = _after(log, "PAUSE")
    assert not [e for e in after if e[0] in ("MOV", "emit", "open")], after


def test_the_trace_never_opens_without_a_printing_mode(grid):
    pw, log = grid
    pw.mode_printing = "none"
    pw._grid_trace()
    assert _opens(log) == [] and ("filter", "high") not in log      # ni siquiera baja el filtro


# ── Sin pausa, igual que antes; Play reanuda ────────────────────────────────────────────────

def test_without_a_pause_the_autofocus_finish_opens_as_before(grid):
    pw, log = grid
    pw.grid_finish_autofoco()
    assert _opens(log) == [("open", config.SHUTTERS[0])]
    assert log.index(("filter", "high")) < log.index(("open", config.SHUTTERS[0]))


def test_play_clears_the_pause_and_the_grid_goes_on(grid):
    pw, log = grid
    pw.grid_pause()
    assert pw.grid_halted()
    log.append("PLAY")
    pw.grid_measurment()                              # Play con la grilla en pausa: reanuda
    assert not pw.grid_halted()
    assert [e for e in _after(log, "PLAY") if e[0] == "MOV"]
    pw.grid_finish_autofoco()
    assert _opens(_after(log, "PLAY"))


# ── Reanudar después de una pausa: un nodo con decisión no se reexpone ──────────────────────

def _decide_success(pw, monkeypatch):
    """El criterio decide "success" en el nodo actual (sin escribir archivos)."""
    monkeypatch.setattr(pw, "_save_trace", lambda *a, **k: None)
    pw.stopping_mode, pw.umbral, pw.umbral_down, pw.timemax, pw.slope_min = 0, 1.5, 0.0, 40.0, 0.0
    pw.timer_inicio = __import__("time").time()
    pw.t_raw_history = []
    pw.grid_trace_detect([1, [0.0, 0.01], [1.0, 2.0], 0, 1.0, 2.0, 1.0, 1.0])


def test_the_decision_marks_the_node_and_resume_goes_to_the_next(grid, monkeypatch):
    pw, log = grid
    pw._grid_trace()                                  # nodo 0 expuesto
    _decide_success(pw, monkeypatch)
    assert pw.node_results[0] == "success" and (0, 0) in pw.exposed
    pw.grid_pause()                                   # la pausa cae en el escaneo posterior o en la espera
    pw.grid_scan()                                    # la cadena no sigue
    assert pw.i_global == 0
    log.append("PLAY")
    pw.grid_measurment()                              # Play
    after = _after(log, "PLAY")
    assert pw.i_global == 1 and ("MOV", (51.0, 50.0)) in after
    assert ("MOV", (50.0, 50.0)) not in after          # el nodo 0, que ya imprimió, no se reexpone


def test_a_pause_during_the_exposure_leaves_the_node_interrupted_and_resume_goes_to_the_next(grid, monkeypatch):
    """Una Pausa que corta la exposición deja el nodo "interrupted" (en revisión) y Play sigue con el próximo: el
    nodo cortado no se reexpone (respuesta 1 del investigador, 2026-10-02; R4-17 fase 3, DEC-046). Antes (DEC-041)
    volvía al mismo nodo."""
    pw, log = grid
    monkeypatch.setattr(pw, "_save_trace", lambda *a, **k: None)
    pw._grid_trace()                                  # nodo 0 expuesto
    pw.grid_pause()
    assert pw.node_results[0] == "interrupted" and pw.node_meta[0].cause == "pause"
    assert (0, 0) in pw.exposed                       # se expuso: la reanudación lo saltea
    log.append("PLAY")
    pw.grid_measurment()
    after = _after(log, "PLAY")
    assert pw.i_global == 1 and ("MOV", (51.0, 50.0)) in after
    assert ("MOV", (50.0, 50.0)) not in after          # el nodo 0, cortado, no se reexpone


def test_a_new_grid_clears_the_exposed_nodes_of_the_previous_one(grid, monkeypatch):
    """La reanudación sigue en el primer nodo nunca expuesto (R4-17 fase 4b, DEC-048): una grilla nueva no hereda
    las exposiciones de la anterior."""
    pw, log = grid
    pw.exposed = {(0, 0), (1, 0)}
    pw.mode_printing = "none"
    monkeypatch.setattr(pw, "_preflight_grid_range_check", lambda: True, raising=False)
    try:
        pw._grid_start()
    except Exception:
        pass                                          # el arranque completo necesita más estado; importa el borrado
    assert pw.exposed == set()


def test_a_pause_during_the_filter_wait_does_not_open(grid, monkeypatch):
    """La pausa llega en los 0.5 s que espera el filtro antes de abrir: no abre y el filtro vuelve a baja."""
    pw, log = grid

    def sleep(s):
        if s == 0.5:
            pw.request_pause()                        # el clic en Pausa, en el hilo GUI, durante la espera
    monkeypatch.setattr(meas, "time", types.SimpleNamespace(sleep=sleep, time=__import__("time").time))
    pw._grid_trace()
    assert _opens(log) == [] and log[-1] == ("filter", "low"), log
