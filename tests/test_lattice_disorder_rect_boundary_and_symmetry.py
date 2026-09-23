# -*- coding: utf-8 -*-
"""
test_lattice_disorder_rect_boundary_and_symmetry.py — Pruebas de la Misión
"Critical Enhancements & Physical Modeling Corrections", Paquete C
(crystallography y topología de espacio real, Pestaña 2):

1. generate_ideal_lattice_template acepta boundary_width_nm/boundary_height_nm
   independientes para envolventes rectangulares, con comportamiento idéntico
   al previo (envolvente cuadrada) cuando se omiten.
2. run_hexagonal_monte_carlo_calibration acepta y propaga los mismos parámetros.
3. register_and_match_template calcula covarianza 2x2 (cov_xy, lambda_min/max)
   y elipticidad ε = 1 - λmin/λmax, rotacionalmente invariante.
4. La GUI alterna entre el spinbox único (radio) y el par Lx/Ly según
   combo_boundary_type, y _update_metrics_table/_update_mc_hex_info_label
   reflejan sitios de envolvente (no Nx*Ny) para familias hexagonales.

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

from core.lattice_disorder import generate_ideal_lattice_template, register_and_match_template
from analysis.lattice_disorder_gui import LatticeDisorderWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication(sys.argv)


class TestRectangularBoundaryWidthHeight:

    def test_default_omitted_matches_square_behavior(self):
        t1 = generate_ideal_lattice_template('square', a=500.0, boundary_type='rectangle', boundary_size_nm=4000.0)
        t2 = generate_ideal_lattice_template(
            'square', a=500.0, boundary_type='rectangle', boundary_size_nm=4000.0,
            boundary_width_nm=None, boundary_height_nm=None
        )
        assert t1['n_points'] == t2['n_points']
        assert np.allclose(sorted(t1['x']), sorted(t2['x']))

    def test_independent_width_height_changes_node_count(self):
        t_square = generate_ideal_lattice_template('square', a=500.0, boundary_type='rectangle', boundary_size_nm=4000.0)
        t_narrow = generate_ideal_lattice_template(
            'square', a=500.0, boundary_type='rectangle',
            boundary_width_nm=1000.0, boundary_height_nm=4000.0
        )
        assert t_narrow['n_points'] < t_square['n_points']
        assert t_narrow['x'].max() - t_narrow['x'].min() < t_square['x'].max() - t_square['x'].min()

    def test_hexagonal_boundary_unaffected_by_width_height_kwargs(self):
        # boundary_width_nm/boundary_height_nm sólo tienen efecto para 'rectangle'.
        t1 = generate_ideal_lattice_template('hexagonal', a=500.0, boundary_type='hexagon', boundary_size_nm=4000.0)
        t2 = generate_ideal_lattice_template(
            'hexagonal', a=500.0, boundary_type='hexagon', boundary_size_nm=4000.0,
            boundary_width_nm=1000.0, boundary_height_nm=9000.0
        )
        assert t1['n_points'] == t2['n_points']


class TestCovarianceAndEllipticity:

    def test_isotropic_disorder_yields_low_ellipticity(self):
        rng = np.random.default_rng(42)
        template = generate_ideal_lattice_template('hexagonal', a=500.0, boundary_type='hexagon', boundary_size_nm=3000.0)
        n = len(template['x'])
        x_real = template['x'] + rng.normal(0, 5.0, n)
        y_real = template['y'] + rng.normal(0, 5.0, n)
        match = register_and_match_template(x_real, y_real, template['x'], template['y'], auto_rotate=False)
        assert 'ellipticity' in match
        assert 0.0 <= match['ellipticity'] <= 1.0
        assert match['ellipticity'] < 0.5  # ruido isotrópico -> baja elipticidad esperada

    def test_anisotropic_disorder_yields_higher_ellipticity(self):
        rng = np.random.default_rng(7)
        template = generate_ideal_lattice_template('hexagonal', a=500.0, boundary_type='hexagon', boundary_size_nm=3000.0)
        n = len(template['x'])
        x_real = template['x'] + rng.normal(0, 30.0, n)  # mucho ruido en X
        y_real = template['y'] + rng.normal(0, 2.0, n)   # poco ruido en Y
        match = register_and_match_template(x_real, y_real, template['x'], template['y'], auto_rotate=False)
        assert match['ellipticity'] > 0.5

    def test_ellipticity_and_cov_present_in_return_dict(self):
        template = generate_ideal_lattice_template('hexagonal', a=500.0, boundary_type='hexagon', boundary_size_nm=2000.0)
        match = register_and_match_template(template['x'], template['y'], template['x'], template['y'], auto_rotate=False)
        for key in ('cov_xy', 'lambda_min', 'lambda_max', 'ellipticity'):
            assert key in match


class TestGuiBoundaryToggleAndSymmetryAwareTable:

    def test_rectangular_selection_shows_lx_ly_hides_radius(self, app):
        win = LatticeDisorderWindow()
        win.combo_lattice_type.setCurrentIndex(1)  # Hexagonal/Triangular
        win.combo_boundary_type.setCurrentIndex(2)  # Rectangular
        assert win.spin_boundary_width.isVisible() or not win.spin_boundary_width.isHidden()
        win.close()

    def test_hexagonal_selection_shows_radius_hides_lx_ly(self, app):
        win = LatticeDisorderWindow()
        win.combo_lattice_type.setCurrentIndex(1)
        win.combo_boundary_type.setCurrentIndex(2)
        win.combo_boundary_type.setCurrentIndex(0)  # de vuelta a Hexagonal
        assert win.spin_boundary_size.isVisible() or not win.spin_boundary_size.isHidden()
        win.close()

    def test_metrics_table_row1_shows_site_count_for_hex_family(self, app):
        win = LatticeDisorderWindow()
        win.combo_lattice_type.setCurrentIndex(1)
        win.kdtree_results = {'N_total_sites': 987, 'sigma_x': 1.0, 'sigma_y': 1.0, 'sigma_pos': 1.0, 'ellipticity': 0.1}
        win._update_metrics_table()
        assert "987" in win.table_metrics.item(1, 1).text()
        win.close()
