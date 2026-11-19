# -*- coding: utf-8 -*-
"""
test_shutter_alignment_and_heartbeat.py — El watchdog es sólo de las rutinas (DEC-052).

Antes (DEC-002, DEC-010, SYS-201) toda apertura armaba un plazo global de 30 s: un láser abierto a mano desde el dock
de Shutters o la ventana Láser 532 se cerraba solo, y el selector "Auto-cierre / Sin límite" vivía en el dock. Ahora:

1. La operación manual (dock, Láser 532, traza F1) no arma ningún plazo: el láser queda abierto hasta que el operador
   lo cierre.
2. Una rutina registrada (`routine_watchdog`, `RoutineWatchdogLease`, `set_routine_running`) que tiene un láser abierto
   arma el plazo al abrir o al latir; si deja de latir, se cierran TODOS los obturadores (también los manuales).
3. Al terminar la última rutina el plazo se desarma, aunque quede un láser manual abierto.
4. El plazo se elige en el Control Panel de impresión y en el panel izquierdo de PySpectrum
   (`RoutineWatchdogSelector`), un valor por proceso; el dock ya no tiene selector.
5. Ningún módulo de producción fija un plazo propio, y todo módulo que abre un láser es manual o se registra.

PyPrinting 3.0 — UNSAM Nanofotónica
"""
import os
import re
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ["PYPRINTING_SAFE"] = "1"

# `config` debe importarse ANTES que PyQt6: config.py antepone .venv/Lib/site-packages a sys.path (ver la nota
# histórica de este archivo en git: con el orden inverso, PyQt6 se resuelve desde una instalación rota).
import config  # noqa: F401
from PyQt6.QtWidgets import QApplication
import core.nidaq as nq
from core.shutters import Frontend as ShuttersFrontend, Backend as ShuttersBackend


def _is_open(name: str) -> bool:
    return nq._shutter_signal[nq.SHUTTERS.index(name)] == nq.SHUTTER_POLARITY[name]


def _close_everything():
    nq.close_all_shutters()


# ── 1. Operación manual: sin plazo ────────────────────────────────────────────

def test_manual_open_never_arms_the_deadline():
    laser = nq.SHUTTERS[0]
    nq.set_routine_watchdog_timeout(0.2)
    try:
        assert nq.open_shutter(laser)
        assert not nq.is_watchdog_armed(), "una apertura manual no arma el plazo"
        assert nq.get_watchdog_remaining_time() is None
        time.sleep(0.5)
        assert _is_open(laser), "un láser abierto a mano no se cierra solo"
    finally:
        _close_everything()


def test_heartbeat_without_a_routine_does_nothing():
    laser = nq.SHUTTERS[1]
    try:
        assert nq.open_shutter(laser)
        nq.heartbeat_shutter()
        assert not nq.is_watchdog_armed(), "sin rutina, el latido no arma el plazo"
    finally:
        _close_everything()


def test_manual_open_from_the_dock_stays_open(app):
    frontend = ShuttersFrontend()
    backend = ShuttersBackend()
    backend.make_connection(frontend)
    nq.set_routine_watchdog_timeout(0.2)
    try:
        frontend.shutter0button.setChecked(True)
        app.processEvents()
        assert _is_open(nq.SHUTTERS[0])
        assert not nq.is_watchdog_armed()
        time.sleep(0.5)
        app.processEvents()
        assert _is_open(nq.SHUTTERS[0]), "el dock es operación manual: no hay auto-cierre"
        assert frontend.shutter0button.isChecked()
        frontend._update_security_status()
        assert frontend.lbl_security_status.text() == frontend.MANUAL_OPEN_TEXT
    finally:
        _close_everything()
        frontend.close()


def test_the_dock_has_no_autoclose_selector(app):
    frontend = ShuttersFrontend()
    try:
        for attr in ("chk_autoclose", "combo_timeout", "get_selected_timeout", "autoclose_timeout_signal"):
            assert not hasattr(frontend, attr), f"el dock ya no elige el plazo ({attr}); vive en el Control Panel"
        assert not hasattr(ShuttersBackend(), "set_autoclose_timeout")
        assert frontend.lbl_security_status.text() == frontend.MANUAL_STATUS_TEXT
    finally:
        frontend.close()


def test_laser532_window_open_stays_open(app):
    from modules.camera import Laser532Window
    win = Laser532Window()
    nq.set_routine_watchdog_timeout(0.2)
    try:
        win._toggle_shutter_532(True)
        assert _is_open(nq.SHUTTERS[0])
        assert not nq.is_watchdog_armed()
        time.sleep(0.5)
        assert _is_open(nq.SHUTTERS[0]), "la ventana Láser 532 es operación manual: no se cierra sola"
        win._toggle_shutter_532(False)
        assert not _is_open(nq.SHUTTERS[0])
    finally:
        _close_everything()
        win.close()


# ── 2. Rutinas: el plazo vigila mientras corren ───────────────────────────────

def test_a_routine_that_stops_beating_closes_every_shutter_and_the_dock_follows(app):
    frontend = ShuttersFrontend()
    backend = ShuttersBackend()
    backend.make_connection(frontend)
    manual, routine_laser = nq.SHUTTERS[1], nq.SHUTTERS[0]
    nq.set_routine_watchdog_timeout(0.2)
    try:
        frontend.shutter1button.setChecked(True)               # un láser abierto a mano
        app.processEvents()
        with nq.routine_watchdog("rutina colgada"):
            assert nq.open_shutter(routine_laser)
            assert nq.is_watchdog_armed()
            time.sleep(0.6)                                    # la rutina no late
            app.processEvents()
            assert not _is_open(routine_laser)
            assert not _is_open(manual), "al vencer el plazo de una rutina se cierran todos, también los manuales"
            assert not frontend.shutter1button.isChecked(), "el dock refleja el cierre"
            assert nq.get_close_epoch().cause == nq.CloseCause.WATCHDOG
            assert "rutina colgada" in nq.get_close_epoch().detail
    finally:
        _close_everything()
        frontend.close()


def test_a_routine_that_keeps_beating_is_never_cut():
    laser = nq.SHUTTERS[1]
    nq.set_routine_watchdog_timeout(0.3)
    try:
        with nq.routine_watchdog("rutina sana"):
            assert nq.open_shutter(laser)
            for _ in range(8):                                 # 0.8 s > 0.3 s, latiendo cada 0.1 s
                time.sleep(0.1)
                nq.heartbeat_shutter()
                assert _is_open(laser), "una rutina que late no se corta"
    finally:
        _close_everything()


def test_the_end_of_a_routine_disarms_and_spares_a_manual_laser():
    manual, routine_laser = nq.SHUTTERS[2], nq.SHUTTERS[0]
    nq.set_routine_watchdog_timeout(0.2)
    try:
        assert nq.open_shutter(manual)
        with nq.routine_watchdog("rutina corta"):
            assert nq.open_shutter(routine_laser)
            nq.heartbeat_shutter()
            assert nq.is_watchdog_armed()
            assert nq.close_shutter(routine_laser)
            assert nq.is_watchdog_armed(), "queda un láser abierto: el plazo sigue mientras la rutina corre"
        assert not nq.is_watchdog_armed(), "al terminar la última rutina el plazo se desarma"
        time.sleep(0.5)
        assert _is_open(manual), "el láser manual sobrevive al final de la rutina"
    finally:
        _close_everything()


def test_a_beat_with_nothing_open_does_not_arm():
    with nq.routine_watchdog("rutina sin láser"):
        nq.heartbeat_shutter()
        assert not nq.is_watchdog_armed()


def test_sin_limite_disarms_routines_too():
    laser = nq.SHUTTERS[0]
    try:
        with nq.routine_watchdog("rutina"):
            assert nq.open_shutter(laser)
            assert nq.is_watchdog_armed()
            nq.set_routine_watchdog_timeout(None)
            assert not nq.is_watchdog_armed()
            nq.heartbeat_shutter()
            assert not nq.is_watchdog_armed(), "con Sin límite el latido no arma"
            nq.set_routine_watchdog_timeout(60.0)
            nq.heartbeat_shutter()
            rem = nq.get_watchdog_remaining_time()
            assert rem is not None and 55.0 < rem <= 60.0
    finally:
        nq.set_routine_watchdog_timeout(30.0)
        _close_everything()


def test_lease_is_idempotent_and_nested_registrations_count():
    lease = nq.RoutineWatchdogLease("escaneo")
    lease.begin(); lease.begin()
    assert nq.get_watchdog_routines() == ["escaneo"]
    lease.end(); lease.end()
    assert not nq.is_routine_watchdog_active()
    with nq.routine_watchdog("a"):
        with nq.routine_watchdog("a"):
            pass
        assert nq.is_routine_watchdog_active(), "el registro externo sigue vigente"
    assert not nq.is_routine_watchdog_active()


def test_the_grid_registration_also_registers_the_watchdog():
    nq.set_routine_running("grilla printing", True)
    try:
        assert "grilla printing" in nq.get_watchdog_routines()
    finally:
        nq.set_routine_running("grilla printing", False)
    assert not nq.is_routine_watchdog_active()


# ── 3. El selector del panel ─────────────────────────────────────────────────

def test_selector_sets_the_process_value_and_two_panels_stay_in_sync(app):
    from core.ui.routine_watchdog_widget import RoutineWatchdogSelector
    a, b = RoutineWatchdogSelector(), RoutineWatchdogSelector()
    try:
        assert a.selected_timeout() == 30.0 and b.selected_timeout() == 30.0
        a.combo.setCurrentIndex(a.combo.findData(300.0))
        assert nq.get_routine_watchdog_timeout() == 300.0
        b.refresh()
        assert b.selected_timeout() == 300.0, "el otro panel del proceso se resincroniza"
        b.combo.setCurrentIndex(b.combo.findData(None))
        assert nq.get_routine_watchdog_timeout() is None
        a.refresh()
        assert a.selected_timeout() is None and "sin corte" in a.lbl_state.text()
    finally:
        nq.set_routine_watchdog_timeout(30.0)
        a.close(); b.close()


def test_selector_shows_the_running_routine_and_its_countdown(app):
    from core.ui.routine_watchdog_widget import RoutineWatchdogSelector
    sel = RoutineWatchdogSelector()
    try:
        sel.refresh()
        assert "sin rutina" in sel.lbl_state.text()
        with nq.routine_watchdog("Step & Glue"):
            assert nq.open_shutter(nq.SHUTTERS[0])
            sel.refresh()
            assert "Step & Glue" in sel.lbl_state.text() and "cierre en" in sel.lbl_state.text()
    finally:
        _close_everything()
        sel.close()


def test_both_programs_show_the_selector(app):
    from modules import measurements as meas_mod
    src = Path(meas_mod.__file__).read_text(encoding="utf-8")
    assert "RoutineWatchdogSelector" in src, "el Control Panel de impresión tiene el selector"
    lhp = (BASE_DIR / "pyspectrum" / "ui" / "left_hardware_panel.py").read_text(encoding="utf-8")
    assert "RoutineWatchdogSelector" in lhp, "el panel izquierdo de PySpectrum tiene el selector"


# ── 4. Contrato del código de producción ──────────────────────────────────────

_PROD_DIRS = ("core", "modules", "pyspectrum", "analysis")
_PROD_ROOT_FILES = ("app.py", "contrapropagante.py", "main.py")
_SKIP = {"core/nidaq.py", "modules/camera_backup_pre_fusion.py"}
# Operación manual (DEC-052): abren sin plazo. La traza abre a mano sólo en F1; en impresión la abre la grilla.
_MANUAL = {"core/shutters.py", "modules/camera.py", "modules/trace.py"}
_REGISTERS = ("routine_watchdog", "RoutineWatchdogLease", "set_routine_running", "begin_routine_watchdog")


def _production_files():
    for d in _PROD_DIRS:
        for p in (BASE_DIR / d).rglob("*.py"):
            yield p
    for f in _PROD_ROOT_FILES:
        p = BASE_DIR / f
        if p.exists():
            yield p


def test_no_production_code_hardcodes_a_deadline():
    offenders = []
    for p in _production_files():
        rel = p.relative_to(BASE_DIR).as_posix()
        if rel in _SKIP:
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        for m in re.finditer(r"heartbeat_shutter\(\s*[^)\s]", text):
            offenders.append(f"{rel}: {text[m.start():m.start() + 40]!r}")
        for m in re.finditer(r"open_shutter\([^)]*timeout_s", text):
            offenders.append(f"{rel}: {text[m.start():m.start() + 60]!r}")
    assert not offenders, "el plazo es el del panel (DEC-052): " + "; ".join(offenders)


def test_every_module_that_opens_a_laser_is_manual_or_registers_a_routine():
    offenders = []
    for p in _production_files():
        rel = p.relative_to(BASE_DIR).as_posix()
        if rel in _SKIP or rel in _MANUAL:
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        if not re.search(r"(?<![\w.])open_shutter\(|\.open_shutter\(|set_laser\(True|\.laser\([^)]*True", text):
            continue
        if any(k in text for k in _REGISTERS) or "RoutineThread" in text or "GridRunner" in text:
            continue
        offenders.append(rel)
    assert not offenders, ("abren un láser sin registrarse en el watchdog de rutinas ni figurar como operación "
                           "manual (DEC-052): " + ", ".join(offenders))


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
