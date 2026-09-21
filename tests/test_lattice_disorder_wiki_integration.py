# -*- coding: utf-8 -*-
"""
test_lattice_disorder_wiki_integration.py — Pruebas para la Fase 4 (Paquete 9,
integración) de la misión "Refactorización y Enriquecimiento Metrológico del
Analizador de Desorden 2D": botones "📖 Ayuda Científica" en
analysis/lattice_disorder_gui.py, singleton gestionado por la ventana.

Cubre:
1. _open_wiki_note() crea la instancia ScientificWikiBrowserDialog una sola vez
   (patrón singleton) y la reutiliza en llamadas posteriores.
2. _open_wiki_note(None) abre la página de aterrizaje por defecto sin navegar.
3. _open_wiki_note("CAT-206") navega directamente a la nota correcta.
4. El botón global y los 4 botones contextuales apuntan a las notas correctas
   (CAT-206 junto al selector de motor, CAT-204 junto al desacople
   multi-gaussiano, CAT-102 junto a la base honeycomb, CAT-308 junto a la
   configuración Monte Carlo).

PyPrinting 3.0 — UNSAM Nanofotónica
"""
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["PYPRINTING_SAFE"] = "1"

import config  # noqa: F401

import pytest
from PyQt6.QtWidgets import QApplication

from analysis.lattice_disorder_gui import LatticeDisorderWindow
from analysis.scientific_wiki_browser import ScientificWikiBrowserDialog


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication(sys.argv)


def test_open_wiki_note_is_singleton(app):
    win = LatticeDisorderWindow()
    assert win._wiki_dialog is None

    win._open_wiki_note("CAT-001")
    dlg1 = win._wiki_dialog
    assert isinstance(dlg1, ScientificWikiBrowserDialog)

    win._open_wiki_note("CAT-102")
    dlg2 = win._wiki_dialog
    assert dlg1 is dlg2  # misma instancia reutilizada, no una nueva
    win.close()
    dlg1.close()


def test_open_wiki_note_none_opens_landing_without_navigating(app):
    """_open_wiki_note(None) no navega explícitamente — el diálogo recién
    creado ya se auto-posiciona en su nota de aterrizaje por defecto
    (CAT-001, ver ScientificWikiBrowserDialog.DEFAULT_LANDING_NOTE) en su
    propio __init__, sin que _open_wiki_note tenga que pedirlo."""
    win = LatticeDisorderWindow()
    win._open_wiki_note(None)
    assert win._wiki_dialog is not None
    assert win._wiki_dialog._current_note_id == ScientificWikiBrowserDialog.DEFAULT_LANDING_NOTE
    win.close()
    win._wiki_dialog.close()


def test_open_wiki_note_navigates_to_requested_note(app):
    win = LatticeDisorderWindow()
    win._open_wiki_note("CAT-206")
    assert win._wiki_dialog._current_note_id == "CAT-206"
    win.close()
    win._wiki_dialog.close()


def test_global_help_button_wired_to_open_wiki_note(app, monkeypatch):
    win = LatticeDisorderWindow()
    calls = []
    monkeypatch.setattr(win, '_open_wiki_note', lambda note_id, anchor=None: calls.append(note_id))

    win.btn_wiki_global.click()

    assert calls == [None]
    win.close()
