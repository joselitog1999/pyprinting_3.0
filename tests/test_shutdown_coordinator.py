# -*- coding: utf-8 -*-
"""Orden de cierre de PySpectrum (paso 13 del bloque A; R2-arq §3.3; R3-gui §1.13; R4-B 6).

- Un solo orden, y ninguna espera infinita:
  1. E-STOP;
  2. rutinas de PySpectrum;
  3. satélites huéspedes (liberar con sus hilos vivos, después terminar sus hilos y cerrar la ventana);
  4. obturadores con el cierre confirmado;
  5. obturador del espectrómetro, Shamrock y cámara, en ese orden;
  6. platina a `config.PI_HOME_POS`.
- La platina se mueve **sólo** si los obturadores confirmaron el cierre (DEC-036: no confirmado =
  abierto).
- Nada se invoca de forma bloqueante en un hilo que no corre.
- Una falla se registra y el cierre sigue.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYPRINTING_SAFE", "1")

import pytest

import config
from pyspectrum.services import shutdown as sd
from pyspectrum.services.shutdown import GuestHandle, ShutdownCoordinator, ShutdownStep


class FakeThread:
    def __init__(self, log, name, running=True, finishes=True):
        self.log, self.name, self.running, self.finishes = log, name, running, finishes

    def isRunning(self):
        return self.running

    def quit(self):
        self.log.append(f"quit {self.name}")

    def wait(self, ms):
        self.log.append(f"wait {self.name} {ms}")
        if self.finishes:
            self.running = False
        return self.finishes


class FakeStage:
    def __init__(self, log, connected=True, on_target=True, lands=True):
        self.log, self.connected, self.on_target, self.lands = log, connected, on_target, lands
        self.pos = {"1": 20.0, "2": 30.0, "3": 5.0}

    def MOV(self, axes, targets):
        self.log.append(("MOV", list(axes), [float(t) for t in targets]))
        if self.lands:
            self.pos = {str(a): float(t) for a, t in zip(axes, targets)}
        return True

    def qONT(self, axes=None):
        return {a: self.on_target for a in (axes or [1, 2, 3])}

    def qPOS(self, axes=None):
        return dict(self.pos)


def _coordinator(log, *, shutters_ok=True, stage=None, guests=(), routines=None, devices=None):
    def estop():
        log.append("estop")

    def close_shutters():
        log.append("shutters")
        return shutters_ok

    routines = routines if routines is not None else [("rutina", lambda: log.append("rutina"))]
    devices = devices if devices is not None else [
        ("obturador del espectrómetro", lambda: log.append("spec shutter")),
        ("Shamrock", lambda: log.append("shamrock")),
        ("cámara", lambda: log.append("camera")),
    ]
    stage = stage if stage is not None else FakeStage(log)
    park = lambda: sd.park_stage(stage, config.PI_HOME_POS, timeout_s=0.2, poll_s=0.01)
    mirror = lambda: log.append("mirror down")
    return ShutdownCoordinator(estop=estop, routines=routines, guests=list(guests), close_shutters=close_shutters,
                               devices=devices, park=park, mirror=mirror)


def test_the_order_is_estop_routines_guests_shutters_devices_stage():
    log = []
    t = FakeThread(log, "satélite")
    guest = GuestHandle("PyPrinting", release=lambda: log.append("release"), threads=[t],
                        close_from_host=lambda: log.append("close_from_host"))
    report = _coordinator(log, guests=[guest]).run()
    names = [e if isinstance(e, str) else e[0] for e in log]
    assert names == ["estop", "rutina", "release", "quit satélite", "wait satélite 3000", "close_from_host",
                     "shutters", "spec shutter", "shamrock", "camera", "mirror down", "MOV"], names
    assert not report.problems, report.summary()


def test_the_guest_is_released_while_its_threads_still_run():
    """La inversión del orden viejo (hilos del satélite antes que su cierre) era el deadlock V3."""
    log = []
    t = FakeThread(log, "cámara del satélite")
    seen = {}
    guest = GuestHandle("PyPrinting", release=lambda: seen.setdefault("alive", t.isRunning()), threads=[t],
                        close_from_host=lambda: None)
    _coordinator(log, guests=[guest]).run()
    assert seen["alive"] is True


def test_the_stage_goes_to_config_home_after_the_shutters_confirm():
    log = []
    stage = FakeStage(log)
    report = _coordinator(log, stage=stage).run()
    moves = [e for e in log if isinstance(e, tuple)]
    assert moves == [("MOV", [1, 2, 3], [float(v) for v in config.PI_HOME_POS])]
    assert log.index("shutters") < log.index(moves[0])
    assert not report.problems


def test_the_stage_and_the_mirror_do_not_move_when_the_shutters_do_not_confirm():
    """El espejo abajo manda la luz al espectrómetro: con un obturador que puede estar abierto, no se pulsa."""
    log = []
    report = _coordinator(log, shutters_ok=False).run()
    assert not [e for e in log if isinstance(e, tuple)], log
    assert "mirror down" not in log
    text = report.summary()
    assert "obturadores" in text and "platina" in text and "espejo" in text
    assert {s.name for s in report.problems} >= {"obturadores", "platina", "espejo de detección"}


def test_a_stage_that_does_not_reach_home_is_reported_without_hanging():
    log = []
    report = _coordinator(log, stage=FakeStage(log, on_target=False)).run()
    assert any(s.name == "platina" and "on-target" in s.detail for s in report.problems), report.summary()


def test_a_stage_that_is_not_connected_is_left_alone():
    log = []
    report = _coordinator(log, stage=FakeStage(log, connected=False)).run()
    assert not [e for e in log if isinstance(e, tuple)]
    step = [s for s in report.steps if s.name == "platina"][0]
    assert step.ok and "no conectada" in step.detail


def test_a_failing_step_is_recorded_and_the_shutdown_goes_on():
    log = []

    def broken():
        raise RuntimeError("se colgó")
    report = _coordinator(log, routines=[("rutina rota", broken), ("rutina", lambda: log.append("rutina"))],
                          devices=[("Shamrock", broken), ("cámara", lambda: log.append("camera"))]).run()
    assert "rutina" in log and "camera" in log and any(isinstance(e, tuple) for e in log)
    assert {s.name for s in report.problems} == {"rutina rota", "Shamrock"}
    assert "se colgó" in report.summary()


def test_a_thread_that_does_not_finish_is_reported_not_waited_forever():
    log = []
    t = FakeThread(log, "colgado", finishes=False)
    guest = GuestHandle("PyPrinting", release=lambda: None, threads=[t], close_from_host=lambda: log.append("cfh"))
    report = _coordinator(log, guests=[guest]).run()
    assert "cfh" in log
    assert any("colgado" in s.detail for s in report.problems), report.summary()


def test_a_step_can_report_its_own_failure():
    log = []
    report = _coordinator(log, routines=[("Step & Glue", lambda: ShutdownStep("Step & Glue", False, "el hilo no terminó"))]).run()
    assert [s.detail for s in report.problems] == ["el hilo no terminó"]


def test_stop_in_thread_never_invokes_into_a_thread_that_is_not_running(monkeypatch):
    calls = []
    from PyQt6 import QtCore
    monkeypatch.setattr(QtCore.QMetaObject, "invokeMethod", lambda *a, **k: calls.append(a))
    step = sd.stop_in_thread(object(), "stop_live", FakeThread([], "muerto", running=False), "Live")
    assert step.ok and not calls and "no corre" in step.detail


def test_the_question_names_the_home_position_and_the_open_guests():
    text = sd.closing_question_text(config.PI_HOME_POS, [])
    x, y, z = (f"{v:g}" for v in config.PI_HOME_POS)
    assert f"({x}, {y}, {z}) µm" in text
    assert "enfriador" in text and "obturadores" in text
    assert "PyPrinting" not in text
    text2 = sd.closing_question_text(config.PI_HOME_POS, ["PyPrinting (Microscopio Derecho)"])
    assert "PyPrinting (Microscopio Derecho)" in text2 and "sin mover la platina" in text2
