# -*- coding: utf-8 -*-
"""
conftest.py — Fixtures compartidas de pytest para la suite PyPrinting 3.0 / PySpectrum 3.0

Se carga antes que cualquier módulo de test, así que también es el lugar correcto para
fijar las variables de entorno de modo seguro/headless que la mayoría de los archivos de
test repiten individualmente, y para resolver el conflicto de instalación de PyQt6 (ver
abajo) antes de que ningún archivo de test tenga oportunidad de importarlo primero.
"""
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("PYPRINTING_SAFE", "1")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Causa raíz real de "ImportError: DLL load failed while importing QtWidgets" (visto de
# forma intermitente en toda la sesión, antes atribuido incorrectamente a un problema de
# entorno no accionable): este entorno tiene DOS instalaciones de PyQt6 para Python 3.13 —
# la del entorno conda base (rota: falla al cargar sus DLLs nativas de Qt6) y la de
# `.venv/Lib/site-packages` (funcional). `config.py` antepone `.venv/Lib/site-packages` a
# sys.path (línea ~31), pero solo si `config` ya se importó. Si algún archivo de test
# importa `PyQt6.QtWidgets` ANTES de que `config` se haya importado nunca en el proceso,
# Python resuelve `PyQt6` desde el paquete roto del conda base y la importación falla —
# de forma determinística, no intermitente (confirmado). Importar `config` aquí, antes de
# que pytest coleccione ningún archivo de test, garantiza que sys.path ya esté corregido
# para TODOS los imports de PyQt6 posteriores, sin depender del orden de imports interno
# de cada archivo de test individual.
import config  # noqa: F401

import pytest


@pytest.fixture(scope="session")
def app():
    """QApplication compartida para toda la sesión de pytest. Requerida por
    test_shutter_alignment_and_heartbeat.py::test_watchdog_callback_and_ui_sync /
    test_ui_alignment_mode_selection, que la reciben como parámetro de test — sin este
    fixture, pytest los rechazaba con 'fixture app not found' (2 errores reproducibles
    en toda corrida de la suite completa, ver DECISION_LOG.md). Reutiliza la instancia de
    QApplication ya existente si otro módulo de test la creó primero a nivel de módulo
    (patrón dominante en el resto de la suite), en vez de crear una segunda."""
    from PyQt6.QtWidgets import QApplication
    instance = QApplication.instance() or QApplication(sys.argv)
    yield instance
