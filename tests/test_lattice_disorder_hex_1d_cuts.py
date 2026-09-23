# -*- coding: utf-8 -*-
"""
test_lattice_disorder_hex_1d_cuts.py — Pruebas de la arquitectura de tres
sub-pestañas para los cortes 1D del Espacio Recíproco (tabs_1d_cuts) en
analysis/lattice_disorder_gui.py:
- Tab 0 "Cortes Cartesianos / Principales (Fx, Fy)" (redes cuadrada/rectangular)
- Tab 1 "Ejes Cristalográficos Principales (θ_rot, +60°, +120°)" (1er shell,
  destructivo parcial en honeycomb)
- Tab 2 "Ejes Ortogonales / Constructivos (θ_rot+30°, +90°, +150°)" (2do shell,
  constructivo total en honeycomb)

Reestructurado por la misión "Honeycomb Lattice Reciprocal Space & Directional
Metrology Upgrade" (Paquete B) a partir de la arquitectura de un solo tab hex
de la misión anterior.

Cubre:
1. Las sub-pestañas hexagonales (1, 2) están ocultas por defecto y la
   Cartesiana (0) visible; se invierte tras recalcular con una red
   hexagonal/honeycomb activa.
2. Los 6 paneles de self.hex_cut_panels (0°,60°,120°,30°,90°,150°) se pueblan
   con datos (curva 1D + Box de Metrología Unitaria) tras el recálculo.
3. Los botones/spinbox de orientación recíproca (spin_fourier_rotation,
   btn_auto_rotate_fourier) están ocultos para redes no-hexagonales y
   visibles tras un recálculo hexagonal.
4. Para redes cuadradas/rectangulares, el recálculo mantiene las sub-pestañas
   hexagonales ocultas y limpia self.hex_cut_panels sin lanzar excepción.

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


def _load_hex_locs(win, lattice_type='hexagonal', a=500.0, rotation_deg=5.0, n_noise=2.0, seed=0):
    template = generate_ideal_lattice_template(
        lattice_type, a=a, boundary_type='hexagon', boundary_size_nm=2500.0, rotation_deg=rotation_deg
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

    def test_cartesian_tab_visible_hex_tabs_hidden_by_default(self, app):
        win = LatticeDisorderWindow()
        assert win.tabs_1d_cuts.isTabVisible(0) is True
        assert win.tabs_1d_cuts.isTabVisible(1) is False
        assert win.tabs_1d_cuts.isTabVisible(2) is False
        win.close()

    def test_fourier_rotation_controls_hidden_by_default(self, app):
        win = LatticeDisorderWindow()
        assert win.spin_fourier_rotation.isVisible() is False
        assert win.btn_auto_rotate_fourier.isVisible() is False
        win.close()

    def test_hex_tabs_become_visible_cartesian_hidden_after_hexagonal_recalculation(self, app):
        win = LatticeDisorderWindow()
        win.show()
        win.tabs.setCurrentIndex(2)  # Pestaña 3 (Espacio Recíproco)
        win.combo_lattice_type.setCurrentIndex(1)  # Hexagonal/Triangular
        _load_hex_locs(win)

        win._on_recalculate_reciprocal()

        assert win.tabs_1d_cuts.isTabVisible(0) is False
        assert win.tabs_1d_cuts.isTabVisible(1) is True
        assert win.tabs_1d_cuts.isTabVisible(2) is True
        assert win.spin_fourier_rotation.isVisible() is True
        assert win.btn_auto_rotate_fourier.isVisible() is True
        win.close()

    def test_square_lattice_recalculation_keeps_hex_tabs_hidden(self, app):
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

        assert win.tabs_1d_cuts.isTabVisible(0) is True
        assert win.tabs_1d_cuts.isTabVisible(1) is False
        assert win.tabs_1d_cuts.isTabVisible(2) is False
        assert win.spin_fourier_rotation.isVisible() is False
        # Los 6 paneles hexagonales deben quedar limpios (sin datos huérfanos), no fallar.
        for plot, _box in win.hex_cut_panels.values():
            assert len(plot.listDataItems()) == 0
        win.close()


class TestHexCutsPlotsPopulated:

    @pytest.mark.parametrize("lattice_type", ["hexagonal", "honeycomb"])
    def test_all_six_panels_receive_data_after_recalculation(self, app, lattice_type):
        win = LatticeDisorderWindow()
        win.tabs.setCurrentIndex(2)
        win.combo_lattice_type.setCurrentIndex(1 if lattice_type == "hexagonal" else 2)
        _load_hex_locs(win, lattice_type=lattice_type)

        win._on_recalculate_reciprocal()

        assert len(win.hex_cut_panels) == 6
        for angle_off, (plot, box) in win.hex_cut_panels.items():
            assert len(plot.listDataItems()) >= 1, f"panel {angle_off}° sin datos"
            assert len(box.text()) > 20, f"panel {angle_off}° sin box de metrología"
        win.close()

    def test_metrology_box_shows_nature_badge_and_metrics(self, app):
        win = LatticeDisorderWindow()
        win.tabs.setCurrentIndex(2)
        win.combo_lattice_type.setCurrentIndex(2)  # Honeycomb
        _load_hex_locs(win, lattice_type='honeycomb')

        win._on_recalculate_reciprocal()

        _, box_axis1 = win.hex_cut_panels[0.0]
        txt = box_axis1.text()
        assert "Destructivo" in txt or "|F|²=1" in txt
        assert "FWHM" in txt
        assert "SNR" in txt

        _, box_ortho1 = win.hex_cut_panels[90.0]
        txt_ortho = box_ortho1.text()
        assert "Constructivo" in txt_ortho or "|F|²=4" in txt_ortho

    def test_cartesian_tab_widgets_unaffected_by_hex_recalculation(self, app):
        # plot_cut_x/y/diag (Sub-pestaña Cartesiana) NO deben ser repurpuestos
        # por el recálculo hexagonal -- deben mantener su título original.
        win = LatticeDisorderWindow()
        win.tabs.setCurrentIndex(2)
        win.combo_lattice_type.setCurrentIndex(1)
        _load_hex_locs(win)

        win._on_recalculate_reciprocal()

        assert "fx" in win.plot_cut_x.getPlotItem().titleLabel.text.lower() or "orden" in win.plot_cut_x.getPlotItem().titleLabel.text.lower()
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


class TestHexAnalyticalCards:

    def test_honeycomb_cards_show_hex_specific_content(self, app):
        win = LatticeDisorderWindow()
        win.tabs.setCurrentIndex(2)
        win.combo_lattice_type.setCurrentIndex(2)  # Honeycomb
        _load_hex_locs(win, lattice_type='honeycomb', n_noise=8.0)

        win._on_recalculate_reciprocal()

        assert "Honeycomb" in win.lbl_card_h2h1.text() or "sigma_pos" in win.lbl_card_h2h1.text().lower() or "σ_pos" in win.lbl_card_h2h1.text()
        assert "A" in win.lbl_card_diag.text()  # A60/0, A120/0
        assert "R_cross" in win.lbl_card_h1h0.text() or "Cruzada" in win.lbl_card_h1h0.text()
        assert "u" in win.lbl_card_wilson.text().lower()  # (u2,v2) mencionado
        win.close()

    def test_square_lattice_cards_unaffected(self, app):
        # Sin hex_bragg en reciprocal_results, _update_analytical_panels_and_plots
        # debe seguir su rama Cartesiana original sin lanzar excepción.
        win = LatticeDisorderWindow()
        win.tabs.setCurrentIndex(2)
        win.combo_lattice_type.setCurrentIndex(0)
        n = 100
        rng = np.random.default_rng(2)
        x_nm = np.tile(np.arange(10), 10) * 500.0 + rng.normal(0, 2.0, n)
        y_nm = np.repeat(np.arange(10), 10) * 500.0 + rng.normal(0, 2.0, n)
        df = pd.DataFrame({'x_nm': x_nm, 'y_nm': y_nm, 'x': x_nm / 50.0, 'y': y_nm / 50.0, 'photons': np.full(n, 1000.0)})
        win.locs_df = win._assign_particle_ids_to_raw(df)
        win.locs_df_raw = win.locs_df.copy()
        win.spin_a_nominal.setValue(500.0)
        win.chk_anchor_wilson_h0.setChecked(True)

        win._on_recalculate_reciprocal()  # no debe lanzar excepción
        win.close()
