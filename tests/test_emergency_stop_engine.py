# -*- coding: utf-8 -*-
"""El motor de la parada de emergencia (C-01 Ronda 4, R4-17 fase 4a; `ronda2_architecture.md` §4.1-§4.2; DEC-047).

Contrato:
1. `trigger()` vuelve en el acto aunque otro hilo retenga la placa (`_nidaq_lock`), y en ≤ 0.3 s el cerrador avisa
   "placa tomada"; mientras tanto ninguna apertura escribe, y cuando la placa se libera el cerrador cierra;
2. con un hilo que abre en bucle, ninguna apertura pedida después de la parada tiene éxito (E-1);
3. tres pulsaciones son un episodio, con la generación y la hora de la primera (F-8);
4. Rearmar falla sin un cierre confirmado del cerrador (placa ausente, F-5), con una generación vieja o con una rutina
   que no está quieta, y anda cuando se cumplen las tres;
5. durante la parada el latido no arma el watchdog, y la platina no se mueve (tampoco a mano) hasta Rearmar;
6. la compuerta de baja potencia: un `up_flipper` confirmado la abre con su hora (100 ms de piso) y un `down` la
   cierra; después de una parada confirmada el filtro queda en baja.
"""
import os
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYPRINTING_SAFE", "1")

import pytest

from core import emergency_stop, estop_state, nidaq
from test_shutter_confirmation_and_interlocks import LASER, daq  # noqa: F401  (fixture)


def _wait(pred, timeout=2.0, step=0.005):
    t_end = time.monotonic() + timeout
    while time.monotonic() < t_end:
        if pred():
            return True
        time.sleep(step)
    return bool(pred())


@pytest.fixture
def coordinator():
    return emergency_stop.get_emergency_coordinator()


@pytest.fixture
def results():
    got = []
    fn = lambda r: got.append((time.monotonic(), r))
    nidaq.register_close_listener(fn)
    yield got
    nidaq.unregister_close_listener(fn)


def _rearm(coordinator):
    gen = estop_state.generation()
    assert _wait(lambda: coordinator.rearm_check(gen).ok), coordinator.rearm_check(gen)
    ok, why = coordinator.rearm(gen)
    assert ok, why


class _Participant:
    def __init__(self, name="rutina"):
        self.name = name
        self.stops, self.rearms = [], []
        self.quiet = True

    def on_emergency_stop(self, gen):
        self.stops.append(gen)

    def is_quiescent(self):
        return self.quiet

    def on_rearmed(self, gen):
        self.rearms.append(gen)

    def is_running(self):
        return False


# ── 1. La placa tomada por un hilo colgado ──────────────────────────────────────────────────

def test_trigger_returns_at_once_with_the_board_held_and_the_closer_reports_it(coordinator, results):
    held, release = threading.Event(), threading.Event()

    def hang():
        with nidaq._nidaq_lock:
            held.set()
            release.wait(5.0)
    t = threading.Thread(target=hang, daemon=True)
    t.start()
    assert held.wait(1.0)
    try:
        t0 = time.perf_counter()
        gen = coordinator.trigger("test")
        assert time.perf_counter() - t0 < 0.02          # el hilo que dispara no espera la placa
        t_trip = time.monotonic()
        t1 = time.perf_counter()
        assert nidaq.open_shutter(LASER) is False         # rechaza sin pedir el candado
        assert time.perf_counter() - t1 < 0.02
        assert _wait(lambda: any(not r.ok for _, r in results), timeout=1.0)
        t_busy, busy = next((t, r) for t, r in results if not r.ok)
        assert busy.error == nidaq._BOARD_BUSY and busy.estop_generation == gen
        assert t_busy - t_trip <= 0.35
        st = nidaq.get_emergency_state()
        assert st.active and st.lock_busy and not st.confirmed
        time.sleep(0.8)                                       # el cerrador reintentó al menos una vez
        assert sum(1 for _, r in results if not r.ok) == 1   # un aviso por episodio, aunque reintente
    finally:
        release.set()
        t.join(2.0)
    assert _wait(lambda: nidaq.get_emergency_state().confirmed, timeout=2.0)
    assert nidaq.get_open_shutter_names() == []
    _rearm(coordinator)
    assert nidaq.open_shutter(LASER) is True
    nidaq.close_shutter(LASER)


# ── 2. Ninguna apertura después de la parada (E-1) ──────────────────────────────────────────

def test_no_opening_requested_after_the_stop_succeeds(coordinator):
    calls, stop = [], threading.Event()

    def opener():
        while not stop.is_set():
            t_call = time.monotonic()
            ok = nidaq.open_shutter(LASER, timeout_s=None)
            calls.append((t_call, ok))
            if ok:
                nidaq.close_shutter(LASER)
    th = threading.Thread(target=opener, daemon=True)
    th.start()
    assert _wait(lambda: any(ok for _, ok in calls), timeout=2.0)
    for _ in range(1000):
        coordinator.trigger("estrés")
    t_after = time.monotonic()
    time.sleep(0.2)
    stop.set()
    th.join(2.0)
    late = [(t, ok) for t, ok in calls if t > t_after and ok]
    assert not late, f"{len(late)} aperturas exitosas después de la parada"
    assert _wait(lambda: nidaq.get_emergency_state().confirmed)
    assert nidaq.get_open_shutter_names() == []
    _rearm(coordinator)


def test_an_opening_waiting_for_the_board_when_the_stop_arrives_does_not_write():
    """La apertura pasó la revisión previa y espera el candado; la parada llega mientras espera: adentro del candado
    vuelve a mirar y no escribe."""
    held, release, done = threading.Event(), threading.Event(), []

    def hang():
        with nidaq._nidaq_lock:
            held.set()
            release.wait(5.0)
    th = threading.Thread(target=hang, daemon=True)
    th.start()
    assert held.wait(1.0)
    opener = threading.Thread(target=lambda: done.append(nidaq.open_shutter(LASER, timeout_s=None)), daemon=True)
    opener.start()
    time.sleep(0.05)                                      # el opener ya pasó la revisión previa y espera
    assert not done
    gen = nidaq.request_emergency_stop("test")
    release.set()
    opener.join(2.0)
    th.join(2.0)
    assert done == [False]
    assert nidaq.get_open_shutter_names() == []
    assert _wait(lambda: nidaq.get_emergency_state().confirmed)
    assert nidaq.clear_emergency_stop(gen) == (True, "")


def test_clear_refuses_without_a_close_of_the_closer(monkeypatch):
    """Aunque los cuatro figuren cerrados, sin un cierre del cerrador para esta generación no se rearma (F-5)."""
    monkeypatch.setattr(nidaq, "_closer_attempt", lambda: None)   # el cerrador no llega a escribir
    gen = nidaq.request_emergency_stop("test")
    assert nidaq.get_open_shutter_names() == []
    ok, why = nidaq.clear_emergency_stop(gen)
    assert ok is False and "no está confirmado" in why and estop_state.is_active()


# ── 3. Tres pulsaciones, un episodio (F-8) ──────────────────────────────────────────────────

def test_three_presses_are_one_episode_with_the_first_time(coordinator):
    g1 = coordinator.trigger("tecla")
    st1 = nidaq.get_emergency_state()
    time.sleep(0.02)
    assert coordinator.trigger("tecla") == g1 and coordinator.trigger("botón") == g1
    st = nidaq.get_emergency_state()
    assert st.generation == g1 and st.t_trigger_mono == st1.t_trigger_mono and st.source == "tecla"
    _rearm(coordinator)


# ── 4. Rearmar ──────────────────────────────────────────────────────────────────────────────

def test_rearm_fails_without_a_confirmed_close_of_the_closer(daq, coordinator):
    daq.write_failures = 10 ** 6                          # la placa no acepta ninguna escritura
    gen = coordinator.trigger("test")
    time.sleep(0.4)
    check = coordinator.rearm_check(gen)
    assert not check.ok and not check.closer_confirmed and "llave" in check.reason
    assert coordinator.rearm(gen)[0] is False and estop_state.is_active()
    daq.write_failures = 0                                # la placa vuelve: el cerrador, que siguió, confirma
    assert _wait(lambda: coordinator.rearm_check(gen).ok, timeout=3.0), coordinator.rearm_check(gen)
    assert coordinator.rearm(gen) == (True, "")


def test_rearm_fails_with_an_old_generation_and_with_a_busy_routine(coordinator):
    p = _Participant("grilla")
    coordinator.register(p)
    gen = coordinator.trigger("test")
    assert p.stops == [gen]
    assert _wait(lambda: nidaq.get_emergency_state().confirmed)
    old = coordinator.rearm_check(gen - 1)
    assert not old.ok and not old.generation_current
    assert nidaq.clear_emergency_stop(gen - 1)[0] is False and estop_state.is_active()   # también en nidaq
    assert estop_state.clear(gen - 1) is False and estop_state.is_active()               # y en el estado
    p.quiet = False
    busy = coordinator.rearm_check(gen)
    assert not busy.ok and busy.waiting_on == ("grilla",) and "grilla" in busy.reason
    assert coordinator.rearm(gen)[0] is False
    p.quiet = True
    assert coordinator.rearm(gen) == (True, "")
    assert p.rearms == [gen] and not estop_state.is_active()
    assert nidaq.ESTOP_INTERLOCK not in nidaq.get_shutter_interlocks()


# ── 5. El latido y la platina ───────────────────────────────────────────────────────────────

def test_the_heartbeat_does_not_arm_the_watchdog_during_the_stop(coordinator):
    coordinator.trigger("test")
    assert _wait(lambda: nidaq.get_emergency_state().confirmed)
    nidaq.heartbeat_shutter(30.0)
    assert not nidaq.is_watchdog_armed()
    _rearm(coordinator)
    nidaq.heartbeat_shutter(30.0)
    assert nidaq.is_watchdog_armed()
    nidaq.heartbeat_shutter(None)


def test_no_stage_move_until_rearm_also_by_hand(coordinator):
    import config
    before = dict(config.pi.qPOS())
    coordinator.trigger("test")
    assert config.pi.MOV([1, 2], [12.0, 13.0]) is False   # la grilla o las flechas del panel: lo mismo
    assert config.pi.MOV(3, 7.0) is False
    assert config.pi.qPOS() == before
    _rearm(coordinator)
    assert config.pi.MOV([1, 2], [12.0, 13.0]) is True
    config.pi.MOV([1, 2, 3], [float(before["1"]), float(before["2"]), float(before["3"])])


# ── 6. La compuerta de baja potencia ────────────────────────────────────────────────────────

def test_the_low_power_gate(coordinator):
    assert nidaq.down_flipper() is True
    assert nidaq.low_power_settle_remaining_s() is None
    assert nidaq.up_flipper() is True
    rem = nidaq.low_power_settle_remaining_s()
    assert rem is not None and 0.05 < rem <= nidaq.LOW_POWER_SETTLE_S
    time.sleep(nidaq.LOW_POWER_SETTLE_S + 0.02)
    assert nidaq.low_power_settle_remaining_s() == 0.0
    assert nidaq.down_flipper() is True
    assert nidaq.low_power_settle_remaining_s() is None
    coordinator.trigger("test")                           # el cerrador sube el filtro después del cierre
    assert _wait(lambda: nidaq.get_emergency_state().low_power_confirmed)
    assert nidaq.low_power_settle_remaining_s() is not None
    _rearm(coordinator)
