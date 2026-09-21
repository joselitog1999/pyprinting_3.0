# -*- coding: utf-8 -*-
"""
test_lattice_disorder_cluster_ux.py — Pruebas para la Fase 4 (Paquetes 2, 4, 5, 6)
de la misión "Refactorización y Enriquecimiento Metrológico del Analizador de
Desorden 2D": navegación por teclado en la tabla de cúmulos, ergonomía de altura,
selección por clic dentro del contorno, y menú contextual.

Cubre:
1. Paquete 2: currentCellChanged (no cellClicked) dispara la selección de cúmulo
   — verificado disparando setCurrentCell() directamente (equivalente a
   navegación por flechas), sin simular un clic de mouse real.
2. Paquete 4: table_clusters.height() == 280.
3. Paquete 5: _find_cluster_row_at_point() encuentra el cúmulo correcto cuando el
   punto cae dentro de su contour_polygon_nm, y devuelve None si no cae en
   ninguno — extraído a un método propio precisamente para poder probarlo sin
   depender del mapeo de coordenadas de escena de pyqtgraph.
4. Paquete 6: _on_mark_cluster_resolved_manual() preserva las partículas del
   cúmulo sin modificarlas (a diferencia de la fusión COM) y lo traslada al
   final; _on_discard_cluster() lo remueve de la tabla sin tocar locs_df.

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


def _make_locs_df(n=6):
    return pd.DataFrame({
        'x_nm': np.arange(n, dtype=float) * 500.0,
        'y_nm': np.zeros(n, dtype=float),
        'x': np.arange(n, dtype=float) * 10.0,
        'y': np.zeros(n, dtype=float),
        'photons': np.full(n, 1000.0),
    })


def _two_cluster_results(win, with_contours=False):
    ids = win.locs_df['particle_id'].values
    cluster_a = {
        'id': 1, 'type': 'Dímero', 'indices': [int(ids[0]), int(ids[1])],
        'n_particles': 2, 'com_x': 250.0, 'com_y': 0.0, 'min_dist_nm': 500.0,
        'mean_photons': 1000.0, 'max_photons': 1000.0, 'ratio_photons': 1.0,
        'status': 'UNDER_RESOLVED',
        'contour_polygon_nm': [(-100.0, -100.0), (600.0, -100.0), (600.0, 100.0), (-100.0, 100.0)] if with_contours else [],
    }
    cluster_b = {
        'id': 2, 'type': 'Dímero', 'indices': [int(ids[2]), int(ids[3])],
        'n_particles': 2, 'com_x': 1250.0, 'com_y': 0.0, 'min_dist_nm': 500.0,
        'mean_photons': 1000.0, 'max_photons': 1000.0, 'ratio_photons': 1.0,
        'status': 'UNDER_RESOLVED',
        'contour_polygon_nm': [(900.0, -100.0), (1600.0, -100.0), (1600.0, 100.0), (900.0, 100.0)] if with_contours else [],
    }
    return {
        'clusters': [cluster_a, cluster_b], 'n_clusters': 2,
        'pair_lines': [], 'cluster_particle_indices': set([0, 1, 2, 3]),
        'n_under_resolved': 2, 'n_ok_resolved': 0,
    }


# ── Paquete 4: altura de la tabla ────────────────────────────────────────────

def test_table_clusters_height_is_280(app):
    win = LatticeDisorderWindow()
    assert win.table_clusters.height() == 280
    win.close()


# ── Paquete 2: currentCellChanged dispara selección (no sólo cellClicked) ───

def test_keyboard_navigation_via_current_cell_changed(app):
    win = LatticeDisorderWindow()
    win.locs_df = win._assign_particle_ids_to_raw(_make_locs_df(6))
    win.cluster_results = _two_cluster_results(win)
    win._update_cluster_table()

    assert win.selected_cluster_id is None
    # setCurrentCell() dispara currentCellChanged, el mismo camino que usa la
    # navegación por teclado (flechas Up/Down) — no requiere un evento de mouse.
    win.table_clusters.setCurrentCell(1, 0)
    assert win.selected_cluster_id == 2  # fila 1 = cúmulo id=2
    win.close()


# ── Paquete 5: selección por clic dentro del contorno ────────────────────────

def test_find_cluster_row_at_point_inside_contour(app):
    win = LatticeDisorderWindow()
    win.locs_df = win._assign_particle_ids_to_raw(_make_locs_df(6))
    win.cluster_results = _two_cluster_results(win, with_contours=True)

    # Punto dentro del contorno del cúmulo A (com_x=250, contorno [-100,600]x[-100,100]).
    row = win._find_cluster_row_at_point(250.0, 0.0)
    assert row == 0

    # Punto dentro del contorno del cúmulo B.
    row = win._find_cluster_row_at_point(1250.0, 0.0)
    assert row == 1
    win.close()


def test_find_cluster_row_at_point_outside_any_contour_returns_none(app):
    win = LatticeDisorderWindow()
    win.locs_df = win._assign_particle_ids_to_raw(_make_locs_df(6))
    win.cluster_results = _two_cluster_results(win, with_contours=True)

    row = win._find_cluster_row_at_point(5000.0, 5000.0)
    assert row is None
    win.close()


def test_find_cluster_row_at_point_none_when_no_contour_present(app):
    """Cúmulos sin contour_polygon_nm (p.ej. detectados pero nunca inspeccionados)
    deben ignorarse silenciosamente, no lanzar excepción."""
    win = LatticeDisorderWindow()
    win.locs_df = win._assign_particle_ids_to_raw(_make_locs_df(6))
    win.cluster_results = _two_cluster_results(win, with_contours=False)

    row = win._find_cluster_row_at_point(250.0, 0.0)
    assert row is None
    win.close()


# ── Paquete 6: menú contextual — acciones nuevas ─────────────────────────────

def test_mark_cluster_resolved_manual_preserves_particles_unchanged(app):
    win = LatticeDisorderWindow()
    win.locs_df = win._assign_particle_ids_to_raw(_make_locs_df(6))
    win.cluster_results = _two_cluster_results(win)
    original_indices = list(win.cluster_results['clusters'][0]['indices'])

    win._on_mark_cluster_resolved_manual(cluster_id=1)

    clusters = {c['id']: c for c in win.cluster_results['clusters']}
    resolved = clusters[1]
    assert resolved['status'] == 'RESOLVED_MANUAL'
    assert resolved['indices'] == original_indices  # sin fit, sin fusión — intactas
    assert win.cluster_results['clusters'][-1]['id'] == 1  # trasladado al final
    # locs_df no debe haberse mutado (a diferencia de COM/Multi-Gauss).
    assert len(win.locs_df) == 6
    win.close()


def test_discard_cluster_removes_from_table_without_touching_locs_df(app):
    win = LatticeDisorderWindow()
    win.locs_df = win._assign_particle_ids_to_raw(_make_locs_df(6))
    win.cluster_results = _two_cluster_results(win)
    win.selected_cluster_id = 1

    win._on_discard_cluster(cluster_id=1)

    ids_left = [c['id'] for c in win.cluster_results['clusters']]
    assert ids_left == [2]
    assert win.cluster_results['n_clusters'] == 1
    assert win.selected_cluster_id is None
    assert len(win.locs_df) == 6  # ninguna partícula fue eliminada
    win.close()


def test_discard_cluster_unrelated_id_is_noop_for_selection(app):
    win = LatticeDisorderWindow()
    win.locs_df = win._assign_particle_ids_to_raw(_make_locs_df(6))
    win.cluster_results = _two_cluster_results(win)
    win.selected_cluster_id = 2

    win._on_discard_cluster(cluster_id=1)

    assert win.selected_cluster_id == 2  # no se toca una selección distinta
    ids_left = [c['id'] for c in win.cluster_results['clusters']]
    assert ids_left == [2]
    win.close()
