# -*- coding: utf-8 -*-
"""
test_cluster_undo_resilience.py — Pruebas de la Misión "Critical Enhancements
& Physical Modeling Corrections", Paquete B (analysis/lattice_disorder_gui.py):
deshacer no-destructivo de curación, ayudante de imagen activa (RL), y
atenuación/resaltado unificado de contornos de cúmulos.

Cubre:
1. _on_undo_curation() restaura tanto locs_df como cluster_results (no sólo
   locs_df como antes) y repuebla table_clusters con el número de filas
   correcto — antes, deshacer una acción posterior a una detección de
   cúmulos vaciaba cluster_results por completo.
2. curation_history almacena tuplas (DataFrame, cluster_results) en cada
   punto de guardado (eliminar partículas, resolver cúmulo individual).
3. _get_active_image() retorna image_rl sólo si chk_rl está activo y
   image_rl no es None; en caso contrario retorna image_2d.
4. _redraw_cluster_contours() dibuja todos los cúmulos de cluster_results
   (atenuados) más uno prominente para el seleccionado, y no deja huérfanos
   tras descartar/marcar-resuelto un cúmulo.

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

import copy

import numpy as np
import pandas as pd
import pytest
from PyQt6.QtWidgets import QApplication, QMessageBox

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


def _two_cluster_results(win, with_contours=True):
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


class TestUndoPreservesClusterResults:

    def test_curation_history_stores_tuple_of_df_and_clusters(self, app, monkeypatch):
        win = LatticeDisorderWindow()
        win.locs_df = win._assign_particle_ids_to_raw(_make_locs_df(6))
        win.locs_df_raw = win.locs_df.copy()
        win.cluster_results = _two_cluster_results(win)
        win.selected_particle_indices = {4, 5}

        monkeypatch.setattr(
            "analysis.lattice_disorder_gui.QMessageBox.question",
            lambda *a, **k: QMessageBox.StandardButton.Yes
        )
        monkeypatch.setattr("analysis.lattice_disorder_gui.QMessageBox.information", lambda *a, **k: None)

        win._on_delete_selected_particles()

        assert len(win.curation_history) == 1
        stored_df, stored_clusters = win.curation_history[0]
        assert len(stored_df) == 6  # snapshot previo al borrado
        assert stored_clusters is not None
        assert stored_clusters['n_clusters'] == 2
        win.close()

    def test_undo_restores_both_locs_df_and_cluster_results(self, app, monkeypatch):
        win = LatticeDisorderWindow()
        win.locs_df = win._assign_particle_ids_to_raw(_make_locs_df(6))
        win.locs_df_raw = win.locs_df.copy()
        win.cluster_results = _two_cluster_results(win)
        win._update_cluster_table()
        assert win.table_clusters.rowCount() == 2

        monkeypatch.setattr("analysis.lattice_disorder_gui.QMessageBox.information", lambda *a, **k: None)

        # Simular una acción de curación posterior a la detección de cúmulos:
        # descartar un cúmulo (muta cluster_results sin pasar por curation_history
        # -- para este test empujamos el historial manualmente, como lo haría
        # cualquiera de los 6 sitios reales de curación).
        win.curation_history.append((win.locs_df.copy(), copy.deepcopy(win.cluster_results)))
        win.cluster_results = None  # simula la pérdida que antes causaba el bug
        win._update_cluster_table()
        assert win.table_clusters.rowCount() == 0

        win._on_undo_curation()

        assert win.cluster_results is not None
        assert win.cluster_results['n_clusters'] == 2
        assert win.table_clusters.rowCount() == 2
        win.close()

    def test_undo_with_empty_history_shows_message_and_does_not_crash(self, app, monkeypatch):
        win = LatticeDisorderWindow()
        win.locs_df = win._assign_particle_ids_to_raw(_make_locs_df(4))
        calls = []
        monkeypatch.setattr(
            "analysis.lattice_disorder_gui.QMessageBox.information",
            lambda *a, **k: calls.append(a)
        )
        win._on_undo_curation()
        assert len(calls) == 1
        win.close()


class TestGetActiveImage:

    def test_returns_image_2d_when_rl_unchecked(self, app):
        win = LatticeDisorderWindow()
        win.image_2d = np.zeros((10, 10), dtype=np.float64)
        win.image_rl = np.ones((10, 10), dtype=np.float64)
        win.chk_rl.setChecked(False)
        result = win._get_active_image()
        assert result is win.image_2d
        win.close()

    def test_returns_image_rl_when_checked_and_available(self, app):
        win = LatticeDisorderWindow()
        win.image_2d = np.zeros((10, 10), dtype=np.float64)
        win.image_rl = np.ones((10, 10), dtype=np.float64)
        win.chk_rl.setChecked(True)
        result = win._get_active_image()
        assert result is win.image_rl
        win.close()

    def test_falls_back_to_image_2d_when_rl_checked_but_none(self, app):
        win = LatticeDisorderWindow()
        win.image_2d = np.zeros((10, 10), dtype=np.float64)
        win.image_rl = None
        win.chk_rl.setChecked(True)
        result = win._get_active_image()
        assert result is win.image_2d
        win.close()


class TestRedrawClusterContours:

    def test_redraw_draws_one_item_per_cluster_plus_no_highlight_when_none_selected(self, app):
        win = LatticeDisorderWindow()
        win.locs_df = win._assign_particle_ids_to_raw(_make_locs_df(6))
        win.cluster_results = _two_cluster_results(win, with_contours=True)
        win.selected_cluster_id = None

        win._redraw_cluster_contours()

        assert len(win.cluster_contour_items) == 2
        assert win.highlight_contour_item is None
        win.close()

    def test_redraw_promotes_selected_cluster_to_highlight(self, app):
        win = LatticeDisorderWindow()
        win.locs_df = win._assign_particle_ids_to_raw(_make_locs_df(6))
        win.cluster_results = _two_cluster_results(win, with_contours=True)
        win.selected_cluster_id = 2

        win._redraw_cluster_contours()

        assert len(win.cluster_contour_items) == 1  # sólo el no-seleccionado
        assert win.highlight_contour_item is not None
        win.close()

    def test_discard_cluster_removes_its_contour_not_just_its_row(self, app):
        win = LatticeDisorderWindow()
        win.locs_df = win._assign_particle_ids_to_raw(_make_locs_df(6))
        win.cluster_results = _two_cluster_results(win, with_contours=True)
        win._update_cluster_table()
        win._redraw_cluster_contours()
        assert len(win.cluster_contour_items) == 2

        win._on_discard_cluster(1)

        assert win.cluster_results['n_clusters'] == 1
        assert len(win.cluster_contour_items) == 1  # el contorno del cúmulo #1 ya no queda huérfano
        win.close()

    def test_empty_cluster_results_clears_contours_without_error(self, app):
        win = LatticeDisorderWindow()
        win.locs_df = win._assign_particle_ids_to_raw(_make_locs_df(6))
        win.cluster_results = _two_cluster_results(win, with_contours=True)
        win._redraw_cluster_contours()
        assert len(win.cluster_contour_items) == 2

        win.cluster_results = None
        win._redraw_cluster_contours()

        assert win.cluster_contour_items == []
        assert win.highlight_contour_item is None
        win.close()
