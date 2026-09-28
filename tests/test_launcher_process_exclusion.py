# -*- coding: utf-8 -*-
"""Exclusión de procesos en el lanzador (`main.py`) en modo laboratorio.

PySpectrum 3.0, el Microscopio Derecho (`app.py`) y el Contrapropagante se lanzan como procesos
separados, y cada uno abre su propia sesión sobre la placa NI-DAQmx (con su propio watchdog de
obturadores) y sobre la platina PI. El bus de subyugación de DEC-019 es un objeto de Qt en
memoria: sólo coordina las ventanas satélite que PySpectrum abre **dentro de su proceso**
(menú Herramientas). Decisión del investigador (`RESPUESTAS_INVESTIGADOR.md`, R4-2b,
2026-09-28): con PySpectrum abierto, PyPrinting se abre sólo desde Herramientas y el lanzador
lo bloquea.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYPRINTING_SAFE", "1")

import pytest
from PyQt6.QtWidgets import QApplication

import main as launcher_module

_app = QApplication.instance() or QApplication([])


class _FakeProcess:
    _next_pid = 1000

    def __init__(self, args, **kwargs):
        self.args = args
        self.returncode = None
        _FakeProcess._next_pid += 1
        self.pid = _FakeProcess._next_pid

    def poll(self):
        return self.returncode


@pytest.fixture
def launcher(monkeypatch):
    launched = []
    warnings = []

    def fake_popen(args, **kwargs):
        proc = _FakeProcess(args, **kwargs)
        launched.append(proc)
        return proc

    monkeypatch.setattr(launcher_module.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(launcher_module.QMessageBox, "warning",
                        lambda parent, title, text, *a, **k: warnings.append((title, text)))
    monkeypatch.setattr(launcher_module.QMessageBox, "critical",
                        lambda parent, title, text, *a, **k: pytest.fail(f"error inesperado: {title}: {text}"))
    win = launcher_module.MainWindowLauncher()
    win.chk_safe_mode.setChecked(False)  # modo laboratorio
    yield win, launched, warnings
    win.close()
    win.deleteLater()


def _launch(win, script):
    titles = {"app.py": "Microscopio Derecho", "pyspectrum.py": "PySpectrum 3.0",
              "contrapropagante.py": "Microscopio Contrapropagante"}
    win._launch_script(script, titles[script])


@pytest.mark.parametrize("satellite", ["app.py", "contrapropagante.py"])
def test_satellite_blocked_while_pyspectrum_runs_and_points_to_tools_menu(launcher, satellite):
    win, launched, warnings = launcher
    _launch(win, "pyspectrum.py")
    _launch(win, satellite)
    assert len(launched) == 1, "el lanzador abrió un segundo proceso sobre el mismo hardware"
    assert len(warnings) == 1
    assert "Herramientas" in warnings[0][1]


def test_pyspectrum_blocked_while_pyprinting_runs_standalone(launcher):
    win, launched, warnings = launcher
    _launch(win, "app.py")
    _launch(win, "pyspectrum.py")
    assert len(launched) == 1
    assert len(warnings) == 1


@pytest.mark.parametrize("script", ["app.py", "pyspectrum.py", "contrapropagante.py"])
def test_second_instance_of_the_same_hardware_program_is_blocked(launcher, script):
    win, launched, warnings = launcher
    _launch(win, script)
    _launch(win, script)
    assert len(launched) == 1
    assert len(warnings) == 1


def test_existing_pyprinting_contrapropagante_exclusion_is_kept(launcher):
    win, launched, warnings = launcher
    _launch(win, "app.py")
    _launch(win, "contrapropagante.py")
    assert len(launched) == 1
    assert len(warnings) == 1


def test_launch_allowed_again_after_the_other_process_exits(launcher):
    win, launched, warnings = launcher
    _launch(win, "pyspectrum.py")
    launched[0].returncode = 0  # PySpectrum se cerró
    _launch(win, "app.py")
    assert len(launched) == 2
    assert warnings == []


def test_safe_mode_does_not_block(launcher):
    win, launched, warnings = launcher
    win.chk_safe_mode.setChecked(True)
    _launch(win, "pyspectrum.py")
    _launch(win, "app.py")
    assert len(launched) == 2
    assert warnings == []
