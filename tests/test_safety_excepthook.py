# -*- coding: utf-8 -*-
"""
test_safety_excepthook.py — Red de seguridad ante excepciones no manejadas (DEC-036).

PyPrinting 3.0 — UNSAM Nanofotónica

Con el `sys.excepthook` de fábrica, PyQt6 aborta el proceso ante una excepción no manejada en
un slot: no corre `atexit`, el watchdog muere con el proceso y un láser abierto queda abierto.
Estos tests verifican que el hook de `core.safety_excepthook` cierra los obturadores, deja el
error registrado y avisa sin lanzar, y —en un subproceso, con su control negativo— que con el
hook instalado el programa sobrevive a la excepción en vez de abortar.
"""
import os
import subprocess
import sys
import textwrap
import threading
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("PYPRINTING_SAFE", "1")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from core import nidaq
from core import safety_excepthook as seh


@pytest.fixture
def hook_env(monkeypatch, tmp_path):
    """Obturadores simulados que registran el cierre, log en un directorio temporal y hooks
    del proceso restaurados al terminar."""
    closes = []
    monkeypatch.setattr(nidaq, "close_all_shutters", lambda: closes.append(1) or True)
    monkeypatch.setattr(seh, "LOG_PATH", tmp_path / "logs" / "excepciones_no_manejadas.log")
    saved_cbs = list(seh._callbacks)
    saved_hooks = (sys.excepthook, threading.excepthook, seh._installed)
    try:
        yield closes
    finally:
        seh._callbacks[:] = saved_cbs
        sys.excepthook, threading.excepthook, seh._installed = saved_hooks


def _raise_and_handle(exc, origin="hilo principal"):
    try:
        raise exc
    except BaseException:
        seh.handle_unhandled_exception(*sys.exc_info(), origin=origin)


def test_closes_shutters_logs_and_notifies(hook_env):
    seen = []
    seh.register_unhandled_exception_callback(lambda summary, trace: seen.append((summary, trace)))
    _raise_and_handle(ValueError("slot roto"))
    assert hook_env == [1], "Los obturadores se cierran ante cualquier excepción no manejada"
    text = seh.LOG_PATH.read_text(encoding="utf-8")
    assert "ValueError: slot roto" in text and "Traceback" in text
    assert len(seen) == 1
    assert "CERRADOS" in seen[0][0] and "sigue en ejecución" in seen[0][0]


def test_reports_unconfirmed_close(hook_env, monkeypatch):
    monkeypatch.setattr(nidaq, "close_all_shutters", lambda: False)
    seen = []
    seh.register_unhandled_exception_callback(lambda summary, trace: seen.append(summary))
    _raise_and_handle(RuntimeError("x"))
    assert "SIN CONFIRMAR" in seen[0], "Un cierre sin confirmar no se informa como cerrado"


def test_never_raises_even_if_everything_fails(hook_env, monkeypatch, tmp_path):
    def boom():
        raise RuntimeError("DAQ caída")
    monkeypatch.setattr(nidaq, "close_all_shutters", boom)
    blocker = tmp_path / "es_un_archivo"
    blocker.write_text("x")
    monkeypatch.setattr(seh, "LOG_PATH", blocker / "logs" / "x.log")  # el directorio no se puede crear
    seh.register_unhandled_exception_callback(lambda s, t: (_ for _ in ()).throw(RuntimeError("cb")))
    _raise_and_handle(KeyError("k"))  # no debe lanzar


def test_keyboard_interrupt_still_closes_shutters(hook_env, monkeypatch):
    delegated = []
    monkeypatch.setattr(sys, "__excepthook__", lambda *a: delegated.append(a[0]))
    _raise_and_handle(KeyboardInterrupt())
    assert hook_env == [1]
    assert delegated == [KeyboardInterrupt], "Ctrl+C conserva su comportamiento habitual"


def test_install_covers_threads(hook_env):
    seen = []
    seh.register_unhandled_exception_callback(lambda summary, trace: seen.append(summary))
    seh.install_safety_excepthook()
    assert seh.is_installed()
    t = threading.Thread(target=lambda: 1 / 0, name="adquisicion")
    t.start()
    t.join()
    assert hook_env == [1]
    assert len(seen) == 1 and "hilo 'adquisicion'" in seen[0]


def test_callbacks_can_be_unregistered(hook_env):
    seen = []
    cb = lambda s, t: seen.append(s)
    seh.register_unhandled_exception_callback(cb)
    seh.register_unhandled_exception_callback(cb)
    seh.unregister_unhandled_exception_callback(cb)
    _raise_and_handle(ValueError("y"))
    assert seen == []


# ── El programa sobrevive a una excepción en un slot (subproceso) ─────────────

_SLOT_SCRIPT = textwrap.dedent("""
    import os, sys
    sys.path.insert(0, {root!r})
    os.environ["PYPRINTING_SAFE"] = "1"
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    if {install}:
        from core.safety_excepthook import install_safety_excepthook
        install_safety_excepthook()
    def broken_slot():
        raise ValueError("excepción en un slot")
    QTimer.singleShot(0, broken_slot)
    QTimer.singleShot(200, app.quit)
    app.exec()
    print("SOBREVIVIO")
""")


def _run_slot_script(install: bool, tmp_path) -> subprocess.CompletedProcess:
    script = tmp_path / f"slot_{int(install)}.py"
    script.write_text(_SLOT_SCRIPT.format(root=str(BASE_DIR), install=install), encoding="utf-8")
    env = dict(os.environ, PYPRINTING_SAFE="1", QT_QPA_PLATFORM="offscreen")
    return subprocess.run([sys.executable, str(script)], capture_output=True, text=True,
                          timeout=120, env=env, cwd=str(tmp_path))


def test_program_survives_a_slot_exception_with_the_hook(tmp_path):
    r = _run_slot_script(True, tmp_path)
    assert r.returncode == 0 and "SOBREVIVIO" in r.stdout, r.stderr[-2000:]
    assert "excepción en un slot" in r.stderr


def test_negative_control_default_hook_aborts(tmp_path):
    """Sin el hook, PyQt6 aborta: si esto dejara de pasar, el test anterior ya no probaría nada."""
    r = _run_slot_script(False, tmp_path)
    assert r.returncode != 0 and "SOBREVIVIO" not in r.stdout
