# -*- coding: utf-8 -*-
"""
test_lattice_disorder_histograms.py — Pruebas para la Fase 4 (Paquete 8) de la
misión "Refactorización y Enriquecimiento Metrológico del Analizador de
Desorden 2D": histogramas de diagnóstico metrológicos con leyenda/sigma para
residuos Δx/Δy, coordinación Voronoi P(Z) con resaltado de la barra nominal
según familia de red, y conmutación dinámica |ψ4|/|ψ6|/|ψ3| en vez de un
título estático (bug latente encontrado durante la auditoría de la Ronda 1).

Cubre:
1. Residuos Δx/Δy: la leyenda existe y su curva incluye sigma_x/sigma_y en el
   nombre (formato "Δx (σx=... nm)").
2. Voronoi P(Z): el título incluye el Z nominal correcto por familia de red
   (4/6/3) y la fracción de celdas regulares, y la barra correspondiente a
   Z_nominal recibe el color de resaltado (#a6e3a1) distinto de las demás.
3. Orden orientacional: el título conmuta entre |ψ4| (square, sin n_fold en
   bond_order), |ψ6| (hexagonal) y |ψ3| (honeycomb), leyendo psi_n_local en
   vez de quedar fijo en psi4_local.

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
import pytest
from PyQt6.QtWidgets import QApplication

from analysis.lattice_disorder_gui import LatticeDisorderWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication(sys.argv)


def _make_kdtree_results(n=50, seed=0):
    rng = np.random.default_rng(seed)
    return {
        'delta_x': rng.normal(0.0, 3.0, n),
        'delta_y': rng.normal(0.0, 5.0, n),
    }


def _make_crystallography_results(z_values, n_fold=None, psi_n_vals=None):
    z_arr = np.array(z_values, dtype=int)
    voronoi = {
        'coordination': z_arr,
        'is_internal': np.ones(len(z_arr), dtype=bool),
        'n_internal': len(z_arr),
    }
    bond_order = {
        'psi4_local': np.random.default_rng(1).uniform(0, 1, 20),
    }
    if n_fold is not None:
        bond_order['n_fold'] = n_fold
        bond_order['psi_n_local'] = psi_n_vals if psi_n_vals is not None else np.random.default_rng(2).uniform(0, 1, 20)
    return {'voronoi': voronoi, 'bond_order': bond_order}


def _get_plot_title(win, col):
    item = win.plot_topology_hist.getItem(0, col)
    return item.titleLabel.text


# ── Residuos Δx/Δy: leyenda + sigma ──────────────────────────────────────────

def test_residuals_histogram_has_legend_with_sigma(app):
    win = LatticeDisorderWindow()
    win.combo_lattice_type.setCurrentIndex(0)  # square
    win.kdtree_results = _make_kdtree_results()
    win.crystallography_results = _make_crystallography_results(z_values=[4] * 20)

    win._update_topology_histograms()

    p1 = win.plot_topology_hist.getItem(0, 0)
    assert p1.legend is not None
    legend_names = [sample[1].text for sample in p1.legend.items]
    assert any("σx=" in n for n in legend_names)
    assert any("σy=" in n for n in legend_names)
    win.close()


# ── Voronoi P(Z): título con Z nominal + fracción, barra resaltada ──────────

@pytest.mark.parametrize("idx,z_nominal", [(0, 4), (1, 6), (2, 3)])
def test_voronoi_title_shows_correct_nominal_z_per_family(app, idx, z_nominal):
    win = LatticeDisorderWindow()
    win.combo_lattice_type.setCurrentIndex(idx)
    win.kdtree_results = _make_kdtree_results()
    # 8 celdas con Z nominal, 2 con un defecto (Z_nominal - 1), fracción regular = 0.8
    z_values = [z_nominal] * 8 + [max(1, z_nominal - 1)] * 2
    win.crystallography_results = _make_crystallography_results(z_values=z_values)

    win._update_topology_histograms()

    title = _get_plot_title(win, 1)
    assert f"Z_nom={z_nominal}" in title
    assert "80.0%" in title
    win.close()


def test_voronoi_nominal_bar_is_highlighted(app):
    win = LatticeDisorderWindow()
    win.combo_lattice_type.setCurrentIndex(0)  # square, Z_nom=4
    win.kdtree_results = _make_kdtree_results()
    win.crystallography_results = _make_crystallography_results(z_values=[3, 4, 4, 5])

    win._update_topology_histograms()

    p2 = win.plot_topology_hist.getItem(0, 1)
    bar_items = [it for it in p2.items if hasattr(it, 'opts') and 'brushes' in it.opts]
    assert len(bar_items) == 1
    brushes = bar_items[0].opts['brushes']
    x_vals = list(bar_items[0].opts['x'])
    # El índice correspondiente a Z=4 (el nominal) debe llevar el color de resaltado.
    idx_nominal = x_vals.index(4.0)
    assert brushes[idx_nominal] == '#a6e3a1'
    for i, xv in enumerate(x_vals):
        if xv != 4.0:
            assert brushes[i] != '#a6e3a1'
    win.close()


# ── Orden orientacional: conmutación dinámica |ψ4|/|ψ6|/|ψ3| ────────────────

def test_psi_title_defaults_to_psi4_for_square(app):
    win = LatticeDisorderWindow()
    win.combo_lattice_type.setCurrentIndex(0)
    win.kdtree_results = _make_kdtree_results()
    win.crystallography_results = _make_crystallography_results(z_values=[4] * 10, n_fold=None)

    win._update_topology_histograms()

    assert _get_plot_title(win, 2) == "Distribución |ψ4|"
    win.close()


def test_psi_title_switches_to_psi6_for_hexagonal(app):
    win = LatticeDisorderWindow()
    win.combo_lattice_type.setCurrentIndex(1)
    win.kdtree_results = _make_kdtree_results()
    win.crystallography_results = _make_crystallography_results(z_values=[6] * 10, n_fold=6)

    win._update_topology_histograms()

    assert _get_plot_title(win, 2) == "Distribución |ψ6|"
    win.close()


def test_psi_title_switches_to_psi3_for_honeycomb(app):
    win = LatticeDisorderWindow()
    win.combo_lattice_type.setCurrentIndex(2)
    win.kdtree_results = _make_kdtree_results()
    win.crystallography_results = _make_crystallography_results(z_values=[3] * 10, n_fold=3)

    win._update_topology_histograms()

    assert _get_plot_title(win, 2) == "Distribución |ψ3|"
    win.close()
