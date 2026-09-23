# -*- coding: utf-8 -*-
"""
test_lattice_disorder_hex_1d_cuts.py — Pruebas de la Misión "Critical
Enhancements & Physical Modeling Corrections", Paquete D.2
(analysis/lattice_disorder_gui.py): arquitectura de dos sub-pestañas para
los cortes 1D del Espacio Recíproco (tabs_1d_cuts).

Cubre:
1. La sub-pestaña "Cortes Cristalográficos Hexagonales" está oculta por
   defecto (redes cuadrada/rectangular) y se vuelve visible al recalcular
   Espacio Recíproco con una red hexagonal/honeycomb activa.
2. Los 3 plots dedicados (θ_rot+60°/120°/150°) se pueblan con datos tras el
   recálculo en modo hexagonal.
3. Los botones/spinbox de orientación recíproca (spin_fourier_rotation,
   btn_auto_rotate_fourier) están ocultos para redes no-hexagonales y
   visibles tras un recálculo hexagonal.
4. Para redes cuadradas/rectangulares, el recálculo no toca la sub-pestaña
   hexagonal (permanece oculta, sin error).

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

from core.lattice_disorder import generate_ideal_lattice_template
from analysis.lattice_disorder_gui import LatticeDisorderWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication(sys.argv)


def _load_hex_locs(win, a=500.0, rotation_deg=5.0, n_noise=2.0, seed=0):
    template = generate_ideal_lattice_template(
        'hexagonal', a=a, boundary_type='hexagon', boundary_size_nm=2500.0, rotation_deg=rotation_deg
    )
    rng = np.random.default_rng(seed)
    n = len(template['x'])
    x_nm = template['x'] + rng.normal(0, n_noise, n)
    y_nm = template['y'] + rng.normal(0, n_noise, n)
    df = pd.DataFrame({'x_nm': x_nm, 'y_nm': y_nm, 'x': x_nm / 50.0, 'y': y_nm / 50.0, 'photons': np.full(n, 1000.0)})
    win.locs_df = win._assign_particle_ids_to_raw(df)
    win.locs_df_raw = win.locs_df.copy()
    win.spin_a_nominal.setValue(a)
    win.spin_boundary_size.setValue(2500.0)


class TestHexCutsTabVisibility:

    def test_hex_tab_hidden_by_default(self, app):
        win = LatticeDisorderWindow()
        assert win.tabs_1d_cuts.isTabVisible(1) is False
        win.close()

    def test_fourier_rotation_controls_hidden_by_default(self, app):
        win = LatticeDisorderWindow()
        assert win.spin_fourier_rotation.isVisible() is False
        assert win.btn_auto_rotate_fourier.isVisible() is False
        win.close()

    def test_hex_tab_becomes_visible_after_hexagonal_recalculation(self, app):
        win = LatticeDisorderWindow()
        win.show()
        win.tabs.setCurrentIndex(2)  # Pestaña 3 (Espacio Recíproco)
        win.combo_lattice_type.setCurrentIndex(1)  # Hexagonal/Triangular
        _load_hex_locs(win)

        win._on_recalculate_reciprocal()

        assert win.tabs_1d_cuts.isTabVisible(1) is True
        assert win.spin_fourier_rotation.isVisible() is True
        assert win.btn_auto_rotate_fourier.isVisible() is True
        win.close()

    def test_square_lattice_recalculation_keeps_hex_tab_hidden(self, app):
        win = LatticeDisorderWindow()
        win.tabs.setCurrentIndex(2)
        win.combo_lattice_type.setCurrentIndex(0)  # Cuadrada/Rectangular
        n = 100
        rng = np.random.default_rng(1)
        x_nm = np.tile(np.arange(10), 10) * 500.0 + rng.normal(0, 2.0, n)
        y_nm = np.repeat(np.arange(10), 10) * 500.0 + rng.normal(0, 2.0, n)
        df = pd.DataFrame({'x_nm': x_nm, 'y_nm': y_nm, 'x': x_nm / 50.0, 'y': y_nm / 50.0, 'photons': np.full(n, 1000.0)})
        win.locs_df = win._assign_particle_ids_to_raw(df)
        win.locs_df_raw = win.locs_df.copy()
        win.spin_a_nominal.setValue(500.0)

        win._on_recalculate_reciprocal()

        assert win.tabs_1d_cuts.isTabVisible(1) is False
        assert win.spin_fourier_rotation.isVisible() is False
        win.close()


class TestHexCutsPlotsPopulated:

    def test_hex60_120_150_plots_receive_data_after_recalculation(self, app):
        win = LatticeDisorderWindow()
        win.tabs.setCurrentIndex(2)
        win.combo_lattice_type.setCurrentIndex(1)
        _load_hex_locs(win)

        win._on_recalculate_reciprocal()

        for plot in (win.plot_cut_hex60, win.plot_cut_hex120, win.plot_cut_hex150):
            data_items = [it for it in plot.listDataItems()]
            assert len(data_items) >= 1
        win.close()

    def test_plot_cut_x_and_y_repurposed_for_hex_axes(self, app):
        win = LatticeDisorderWindow()
        win.tabs.setCurrentIndex(2)
        win.combo_lattice_type.setCurrentIndex(1)
        _load_hex_locs(win)

        win._on_recalculate_reciprocal()

        assert "Eje 1" in win.plot_cut_x.getPlotItem().titleLabel.text
        assert "Ortogonal" in win.plot_cut_y.getPlotItem().titleLabel.text
        win.close()

    def test_hex_bragg_stored_in_reciprocal_results(self, app):
        win = LatticeDisorderWindow()
        win.tabs.setCurrentIndex(2)
        win.combo_lattice_type.setCurrentIndex(1)
        _load_hex_locs(win)

        win._on_recalculate_reciprocal()

        assert 'hex_bragg' in win.reciprocal_results
        hb = win.reciprocal_results['hex_bragg']
        assert hb['H_axis1'] > 0.0
        win.close()
