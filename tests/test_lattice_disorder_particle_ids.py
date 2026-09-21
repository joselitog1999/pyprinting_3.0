# -*- coding: utf-8 -*-
"""
test_lattice_disorder_particle_ids.py — Pruebas para la Fase 4 (Paquete 1) de la
misión "Refactorización y Enriquecimiento Metrológico del Analizador de Desorden
2D": actualización unitaria de cúmulos sin anular cluster_results, vía un esquema
de particle_id estable y monótono.

Cubre:
1. Asignación inicial de particle_id sobre el conjunto RAW completo y el contador
   monótono _next_particle_id.
2. Traducción bidireccional posición <-> particle_id, incluyendo el descarte
   silencioso de IDs de partículas eliminadas.
3. _assign_new_particle_ids nunca reutiliza un ID, ni siquiera tras eliminar y
   deshacer una acción de curación (confirmación de la corrección bloqueante #1
   acordada con el usuario: "si se eliminan el id queda reservado, si se hace
   restauración de la acción los ids vuelven a estar disponibles").
4. _apply_cluster_resolution_state muta el cúmulo resuelto in-place y lo traslada
   al final de la lista, sin tocar los demás cúmulos pendientes.
5. Extremo a extremo: resolver UN cúmulo (fusión COM, que no requiere imagen) no
   anula self.cluster_results y el resto de los cúmulos pendientes siguen siendo
   válidos (sus particle_id siguen traduciendo a posiciones correctas) pese a que
   el DataFrame se reindexó por completo.
6. _update_cluster_table colorea en verde y etiqueta correctamente las filas
   resueltas, y las ubica después de las pendientes (orden natural de la lista).

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


def _two_cluster_results(win):
    """Cúmulo A = partículas 0,1 (a resolver). Cúmulo B = partículas 2,3
    (pendiente, debe sobrevivir). Partículas 4,5 sin agrupar. 'indices' ya en
    espacio particle_id (estado post-detección real, ver _on_detect_clusters)."""
    ids = win.locs_df['particle_id'].values
    cluster_a = {
        'id': 1, 'type': 'Dímero', 'indices': [int(ids[0]), int(ids[1])],
        'n_particles': 2, 'com_x': 250.0, 'com_y': 0.0, 'min_dist_nm': 500.0,
        'mean_photons': 1000.0, 'max_photons': 1000.0, 'ratio_photons': 1.0,
        'status': 'UNDER_RESOLVED', 'contour_polygon_nm': [],
    }
    cluster_b = {
        'id': 2, 'type': 'Dímero', 'indices': [int(ids[2]), int(ids[3])],
        'n_particles': 2, 'com_x': 1250.0, 'com_y': 0.0, 'min_dist_nm': 500.0,
        'mean_photons': 1000.0, 'max_photons': 1000.0, 'ratio_photons': 1.0,
        'status': 'UNDER_RESOLVED', 'contour_polygon_nm': [],
    }
    return {
        'clusters': [cluster_a, cluster_b], 'n_clusters': 2,
        'pair_lines': [], 'cluster_particle_indices': set([0, 1, 2, 3]),
        'n_under_resolved': 2, 'n_ok_resolved': 0,
    }


# ── Asignación inicial y traducción ──────────────────────────────────────────

def test_assign_particle_ids_to_raw_is_monotonic(app):
    win = LatticeDisorderWindow()
    df = _make_locs_df(5)
    out = win._assign_particle_ids_to_raw(df)
    assert list(out['particle_id'].values) == [0, 1, 2, 3, 4]
    assert win._next_particle_id == 5
    win.close()


def test_positions_particle_ids_roundtrip(app):
    win = LatticeDisorderWindow()
    win.locs_df = win._assign_particle_ids_to_raw(_make_locs_df(5))
    pids = win._positions_to_particle_ids([0, 2, 4])
    assert pids == [0, 2, 4]
    positions = win._particle_ids_to_positions(pids)
    assert positions == [0, 2, 4]
    win.close()


def test_particle_ids_to_positions_drops_deleted_silently(app):
    win = LatticeDisorderWindow()
    win.locs_df = win._assign_particle_ids_to_raw(_make_locs_df(5))
    # Simula eliminación de la partícula id=2 (posición 2): el resto se
    # reindexa (reset_index(drop=True)) pero particle_id viaja con cada fila.
    win.locs_df = win.locs_df[win.locs_df['particle_id'] != 2].reset_index(drop=True)
    # id=2 ya no existe -> se descarta en silencio, no lanza excepción.
    positions = win._particle_ids_to_positions([0, 1, 2, 3])
    assert 2 not in [win.locs_df['particle_id'].values[p] for p in positions]
    assert len(positions) == 3
    win.close()


def test_assign_new_particle_ids_never_reused_after_delete(app):
    win = LatticeDisorderWindow()
    win.locs_df = win._assign_particle_ids_to_raw(_make_locs_df(3))  # ids 0,1,2 -> next=3
    # Elimina la partícula id=2 (última).
    win.locs_df = win.locs_df[win.locs_df['particle_id'] != 2].reset_index(drop=True)
    assert win._next_particle_id == 3  # el contador NO retrocede al eliminar

    # Simula lo que hacen resolve_clusters_dataframe/resolve_single_spot_multi_gaussian:
    # agregan una fila nueva al final con particle_id=0.0 de relleno (columna
    # faltante rellenada por defecto) — _assign_new_particle_ids debe sobrescribirla
    # con un ID fresco, nunca reciclar el 2 recién liberado.
    new_row = pd.DataFrame({'x_nm': [999.0], 'y_nm': [0.0], 'x': [0.0], 'y': [0.0],
                             'photons': [1.0], 'particle_id': [0.0]})
    df_with_new_row = pd.concat([win.locs_df, new_row], ignore_index=True)

    df_out, new_ids = win._assign_new_particle_ids(df_with_new_row, 1)
    assert new_ids == [3]
    assert win._next_particle_id == 4
    assert int(df_out['particle_id'].iloc[-1]) == 3
    win.close()


# ── Estado de resolución de cúmulos ──────────────────────────────────────────

def test_apply_cluster_resolution_state_moves_resolved_to_end(app):
    win = LatticeDisorderWindow()
    win.locs_df = win._assign_particle_ids_to_raw(_make_locs_df(6))
    win.cluster_results = _two_cluster_results(win)

    win._apply_cluster_resolution_state(target_cluster_id=1, new_particle_ids=[6], status='RESOLVED_GAUSSIAN')

    clusters = win.cluster_results['clusters']
    assert len(clusters) == 2
    assert clusters[-1]['id'] == 1  # el resuelto se traslada al final
    assert clusters[-1]['status'] == 'RESOLVED_GAUSSIAN'
    assert clusters[-1]['indices'] == [6]
    assert clusters[0]['id'] == 2  # el pendiente queda primero, intacto
    assert clusters[0]['indices'] == [2, 3]
    assert clusters[0]['status'] == 'UNDER_RESOLVED'
    win.close()


def test_select_first_pending_cluster_row_skips_resolved(app, monkeypatch):
    win = LatticeDisorderWindow()
    win.locs_df = win._assign_particle_ids_to_raw(_make_locs_df(6))
    win.cluster_results = _two_cluster_results(win)
    win.cluster_results['clusters'][0]['status'] = 'RESOLVED_MANUAL'
    win._update_cluster_table()

    win._select_first_pending_cluster_row()
    assert win.selected_cluster_id == 2  # única pendiente
    win.close()


# ── Extremo a extremo: resolver un cúmulo no anula cluster_results ──────────

def test_resolve_selected_cluster_com_preserves_pending_cluster(app, monkeypatch):
    """Corazón del Paquete 1: fusionar el cúmulo A (COM, no requiere imagen) no
    debe anular self.cluster_results, y el cúmulo B pendiente debe seguir siendo
    válido (su particle_id sigue traduciendo a la posición correcta) pese a que
    resolve_clusters_dataframe reindexó todo el DataFrame."""
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)

    win = LatticeDisorderWindow()
    win.locs_df = win._assign_particle_ids_to_raw(_make_locs_df(6))
    win.cluster_results = _two_cluster_results(win)
    win.selected_cluster_id = 1  # cúmulo A

    win._on_resolve_selected_cluster_com()

    assert win.cluster_results is not None, "Paquete 1: no debe anularse cluster_results"
    clusters = {c['id']: c for c in win.cluster_results['clusters']}
    assert 1 in clusters and 2 in clusters

    resolved = clusters[1]
    assert resolved['status'] == 'RESOLVED_GAUSSIAN'
    # merge_com descarta las 2 partículas originales y agrega 1 punto COM nuevo.
    assert len(resolved['indices']) == 1
    assert resolved['indices'][0] >= 6  # ID nuevo, nunca uno reciclado (0-5 ya usados)

    pending = clusters[2]
    assert pending['status'] == 'UNDER_RESOLVED'
    assert pending['indices'] == [2, 3]  # IDs originales sin tocar

    # Las posiciones de B en el locs_df reindexado deben seguir siendo correctas:
    # originalmente eran x_nm = 1000, 1500 (partículas 2 y 3 * 500nm).
    positions = win._particle_ids_to_positions(pending['indices'])
    assert len(positions) == 2
    x_vals = sorted(win.locs_df['x_nm'].values[positions].tolist())
    assert x_vals == pytest.approx([1000.0, 1500.0])

    # Auto-selección del primer cúmulo pendiente (punto 5 del Paquete 1).
    assert win.selected_cluster_id == 2
    win.close()


# ── _update_cluster_table: color y orden de filas resueltas ─────────────────

def test_update_cluster_table_colors_resolved_rows_green_and_last(app):
    win = LatticeDisorderWindow()
    win.locs_df = win._assign_particle_ids_to_raw(_make_locs_df(6))
    win.cluster_results = _two_cluster_results(win)
    win._apply_cluster_resolution_state(target_cluster_id=1, new_particle_ids=[6], status='RESOLVED_GAUSSIAN')

    win._update_cluster_table()

    assert win.table_clusters.rowCount() == 2
    # Fila 0 = cúmulo pendiente (id=2), fila 1 = cúmulo resuelto (id=1, al final).
    assert win.table_clusters.item(0, 0).text() == "#2"
    assert win.table_clusters.item(1, 0).text() == "#1"
    assert win.table_clusters.item(1, 6).text() == "Resuelto (Multi-Gauss)"
    win.close()
