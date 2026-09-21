# -*- coding: utf-8 -*-
"""
test_lattice_disorder_log_layer.py — Pruebas para la Fase 4 (Paquete 10) de la
misión "Refactorización y Enriquecimiento Metrológico del Analizador de
Desorden 2D": generación de la capa de Manchones LoG al detectar cúmulos.

Corrige un hallazgo de la auditoría de la Ronda 2 (software-architect): la
capa LoG ya existía como función independiente (_on_generate_laplacian_layer,
botón manual), pero NO se disparaba al presionar "Detectar Aglomerados y
Cadenas" como pide la directiva — quedaban dos rutas de cómputo separadas sin
conectar. Se extrajo la lógica común a _compute_and_render_laplacian_layer()
y se la reutiliza desde ambos lugares en vez de duplicar código.

Cubre:
1. _on_detect_clusters() calcula self.image_laplacian automáticamente cuando
   hay imagen cargada.
2. Si chk_layer_laplacian NO estaba marcada, la capa se calcula pero
   permanece invisible (no fuerza la casilla, a diferencia del botón manual).
3. Si chk_layer_laplacian SÍ estaba marcada de antes, la capa recién
   calculada se muestra inmediatamente.
4. Marcar/desmarcar la casilla ANTES de detectar no dispara ningún cálculo ni
   lanza excepción (permanece sin efecto, comportamiento ya presente en
   _on_layer_visibility_changed, verificado aquí explícitamente).

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

import numpy as np
import pandas as pd
import pytest
from PyQt6.QtWidgets import QApplication

from analysis.lattice_disorder_gui import LatticeDisorderWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication(sys.argv)


def _make_synthetic_image(H=60, W=60, sigma_px=2.0):
    yy, xx = np.mgrid[0:H, 0:W]
    img = np.zeros((H, W), dtype=float)
    for cx, cy in [(15, 15), (45, 45)]:
        img += np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2.0 * sigma_px ** 2))
    return img


def _make_locs_df():
    return pd.DataFrame({
        'x_nm': np.array([15.0, 45.0]) * 50.0, 'y_nm': np.array([15.0, 45.0]) * 50.0,
        'x': np.array([15.0, 45.0]), 'y': np.array([15.0, 45.0]),
        'photons': np.array([1000.0, 1000.0]),
    })


def test_toggle_before_detection_is_noop(app):
    win = LatticeDisorderWindow()
    assert win.image_laplacian is None
    win.chk_layer_laplacian.setChecked(True)  # no debe lanzar ni calcular nada
    assert win.image_laplacian is None
    win.chk_layer_laplacian.setChecked(False)
    assert win.image_laplacian is None
    win.close()


def test_detect_clusters_computes_laplacian_layer_silently_when_unchecked(app):
    win = LatticeDisorderWindow()
    win.image_2d = _make_synthetic_image()
    win.locs_df = win._assign_particle_ids_to_raw(_make_locs_df())
    assert win.chk_layer_laplacian.isChecked() is False

    win._on_detect_clusters()

    assert win.image_laplacian is not None
    assert win.img_item_laplacian is not None
    assert win.img_item_laplacian.isVisible() is False  # no se forzó la casilla
    assert win.chk_layer_laplacian.isChecked() is False  # tampoco se marcó sola
    win.close()


def test_detect_clusters_shows_layer_when_already_checked(app):
    win = LatticeDisorderWindow()
    win.image_2d = _make_synthetic_image()
    win.locs_df = win._assign_particle_ids_to_raw(_make_locs_df())
    win.chk_layer_laplacian.setChecked(True)

    win._on_detect_clusters()

    assert win.image_laplacian is not None
    assert win.img_item_laplacian.isVisible() is True
    win.close()


def test_manual_button_still_forces_checkbox_and_visibility(app, monkeypatch):
    """_on_generate_laplacian_layer (botón manual) conserva su comportamiento
    previo: siempre fuerza la casilla y la visibilidad, a diferencia de la
    detección automática de cúmulos."""
    win = LatticeDisorderWindow()
    win.image_2d = _make_synthetic_image()
    assert win.chk_layer_laplacian.isChecked() is False

    win._on_generate_laplacian_layer()

    assert win.image_laplacian is not None
    assert win.chk_layer_laplacian.isChecked() is True
    assert win.img_item_laplacian.isVisible() is True
    win.close()
