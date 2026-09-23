# -*- coding: utf-8 -*-
"""
test_honeycomb_reciprocal_metrology.py — Pruebas de la Misión "Honeycomb
Lattice Reciprocal Space & Directional Metrology Upgrade" (Tab 3 & Tab 4):
factor de base diatómico, indexación de 7 picos de Bragg (1er/2do shell +
armónico radial), inversión analítica cerrada de sigma_pos, y la extensión
direccional del 2do shell (H_mean_ortho) en run_hexagonal_monte_carlo_calibration.

Cubre (Paquete D de la misión):
1. |F_basis(G)|^2 = 1.0 en las 3 direcciones del 1er shell (axis1/axis2/axis3)
   y = 4.0 en las 3 direcciones del 2do shell (ortho1/ortho2/ortho3) para la
   base canónica (u2,v2)=(1/3,1/3).
2. Desplazar (u2,v2) rompe la degeneración de intensidad entre los 3 ejes
   principales (axis1/axis2/axis3 dejan de ser iguales entre sí).
3. Inversión cerrada sigma_pos_analytic recupera el desorden simulado dentro
   de 15% sobre una red honeycomb sintética con ruido gaussiano conocido.
4. compute_hexagonal_bragg_indexing indexa correctamente los 7 picos
   (axis1, axis2, axis3, ortho1/ortho2/ortho3, 2do armónico radial) --
   claves presentes y alturas en picos reales muy por encima del fondo.
5. run_hexagonal_monte_carlo_calibration reproduce el ratio teórico
   H_ortho/H_axis1 -> 4 (honeycomb, sigma->0) y -> 1 (hexagonal, sigma->0).

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

from core.lattice_disorder import (
    _honeycomb_basis_factor_sq,
    compute_hexagonal_bragg_indexing,
    find_hexagonal_reciprocal_rotation,
    generate_ideal_lattice_template,
    compute_structure_factor_2d,
    run_hexagonal_monte_carlo_calibration,
)
from analysis.lattice_disorder_gui import LatticeDisorderWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication(sys.argv)


class TestBasisFactorCanonical:

    def test_first_shell_is_one_at_canonical_basis(self):
        u2 = v2 = 1.0 / 3.0
        first_shell_miller = [(1, 0), (1, 1), (0, 1), (-1, 0), (-1, -1), (0, -1)]
        for h, k in first_shell_miller:
            assert _honeycomb_basis_factor_sq(h, u2, k, v2) == pytest.approx(1.0, abs=1e-9)

    def test_second_shell_is_four_at_canonical_basis(self):
        u2 = v2 = 1.0 / 3.0
        second_shell_miller = [(1, 2), (2, 1), (-1, 1), (1, -1), (-2, -1), (-1, -2)]
        for h, k in second_shell_miller:
            assert _honeycomb_basis_factor_sq(h, u2, k, v2) == pytest.approx(4.0, abs=1e-9)


class TestBasisFactorSymmetryBreaking:

    def test_shifted_u2_splits_the_three_primary_axes(self):
        v2 = 1.0 / 3.0
        u2 = 1.0 / 3.0 + 0.05
        f_axis1 = _honeycomb_basis_factor_sq(1, u2, 0, v2)
        f_axis2 = _honeycomb_basis_factor_sq(1, u2, 1, v2)
        f_axis3 = _honeycomb_basis_factor_sq(0, u2, 1, v2)
        # Al menos dos de los tres valores deben diferir claramente (ruptura de
        # la degeneración canónica |F|^2=1 uniforme).
        vals = [f_axis1, f_axis2, f_axis3]
        assert max(vals) - min(vals) > 0.1

    def test_axis3_unaffected_by_pure_u2_shift(self):
        # axis3 = Miller (0,1) depende únicamente de v2 -- verificado analíticamente.
        v2 = 1.0 / 3.0
        u2_shifted = 1.0 / 3.0 + 0.05
        f_axis3_canonical = _honeycomb_basis_factor_sq(0, 1.0 / 3.0, 1, v2)
        f_axis3_shifted = _honeycomb_basis_factor_sq(0, u2_shifted, 1, v2)
        assert f_axis3_canonical == pytest.approx(f_axis3_shifted, abs=1e-9)


class TestComputeHexagonalBraggIndexingSevenPeaks:

    def _make_honeycomb_S(self, a=500.0, theta_real=8.0, boundary_nm=4000.0, sigma_nm=0.0, seed=0):
        template = generate_ideal_lattice_template(
            'honeycomb', a=a, boundary_type='hexagon', boundary_size_nm=boundary_nm, rotation_deg=theta_real
        )
        x, y = template['x'], template['y']
        if sigma_nm > 0:
            rng = np.random.default_rng(seed)
            x = x + rng.normal(0, sigma_nm, len(x))
            y = y + rng.normal(0, sigma_nm, len(y))
        fx, fy, S = compute_structure_factor_2d(x, y, a_nominal=a, n_bins=400, f_max_factor=2.6)
        return a, fx, fy, S

    def test_all_seven_peak_keys_present(self):
        a, fx, fy, S = self._make_honeycomb_S()
        solved = find_hexagonal_reciprocal_rotation(S, fx, fy, a=a)
        hb = compute_hexagonal_bragg_indexing(S, fx, fy, a=a, rotation_deg=solved['theta_peak_deg'], lattice_type='honeycomb')
        for key in ('H_axis1', 'H_axis2', 'H_axis3', 'H_ortho1', 'H_ortho2', 'H_ortho3',
                    'H_2_axis1', 'H_2_axis2', 'H_ortho'):
            assert key in hb

    def test_first_shell_peaks_well_above_background_honeycomb(self):
        a, fx, fy, S = self._make_honeycomb_S()
        solved = find_hexagonal_reciprocal_rotation(S, fx, fy, a=a)
        hb = compute_hexagonal_bragg_indexing(S, fx, fy, a=a, rotation_deg=solved['theta_peak_deg'], lattice_type='honeycomb')
        background = float(np.percentile(S, 50))
        for key in ('H_axis1', 'H_axis2', 'H_axis3'):
            assert hb[key] > 10.0 * max(background, 1e-6)

    def test_second_shell_brighter_than_first_shell_for_honeycomb(self):
        # |F|^2=4 (2do shell) vs |F|^2=1 (1er shell): a igual sigma, el 2do
        # shell debe ser sustancialmente más intenso (constructivo total).
        a, fx, fy, S = self._make_honeycomb_S()
        solved = find_hexagonal_reciprocal_rotation(S, fx, fy, a=a)
        hb = compute_hexagonal_bragg_indexing(S, fx, fy, a=a, rotation_deg=solved['theta_peak_deg'], lattice_type='honeycomb')
        assert hb['H_ortho1'] > 2.0 * hb['H_axis1']

    def test_hexagonal_all_shells_comparable_intensity(self):
        # Red hexagonal monoatómica: |F|^2 ≡ 1 en TODO G -- 1er y 2do shell
        # deben tener intensidad comparable (a diferencia de honeycomb).
        template = generate_ideal_lattice_template('hexagonal', a=500.0, boundary_type='hexagon', boundary_size_nm=4000.0)
        fx, fy, S = compute_structure_factor_2d(template['x'], template['y'], a_nominal=500.0, n_bins=400, f_max_factor=2.6)
        solved = find_hexagonal_reciprocal_rotation(S, fx, fy, a=500.0)
        hb = compute_hexagonal_bragg_indexing(S, fx, fy, a=500.0, rotation_deg=solved['theta_peak_deg'], lattice_type='hexagonal')
        ratio = hb['H_ortho1'] / hb['H_axis1']
        assert 0.5 < ratio < 2.0


class TestClosedFormSigmaInversion:

    def test_recovers_known_noise_within_15_percent(self):
        # Promedia sobre 5 semillas independientes: la inversión H_ortho/H_axis1
        # de una única realización tiene ruido de muestreo estadístico (peak-search
        # sobre un único draw de posiciones), pero el sesgo SISTEMÁTICO debe ser
        # pequeño -- ver el hallazgo documentado en compute_hexagonal_bragg_indexing
        # sobre la corrección de la fórmula de CAT-315 §7.1 (factor sqrt(2)).
        a = 500.0
        sigma_in_nm = 12.0
        template = generate_ideal_lattice_template('honeycomb', a=a, boundary_type='hexagon', boundary_size_nm=8000.0)
        n = len(template['x'])
        sigma_outs = []
        for seed in range(5):
            rng = np.random.default_rng(seed)
            x = template['x'] + rng.normal(0, sigma_in_nm, n)
            y = template['y'] + rng.normal(0, sigma_in_nm, n)
            fx, fy, S = compute_structure_factor_2d(x, y, a_nominal=a, n_bins=512, f_max_factor=2.6)
            solved = find_hexagonal_reciprocal_rotation(S, fx, fy, a=a)
            hb = compute_hexagonal_bragg_indexing(S, fx, fy, a=a, rotation_deg=solved['theta_peak_deg'], lattice_type='honeycomb')
            sigma_outs.append(hb['sigma_pos_analytic'])

        sigma_out_mean = float(np.mean(sigma_outs))
        rel_err = abs(sigma_out_mean - sigma_in_nm) / sigma_in_nm
        assert rel_err < 0.15, f"sigma_out_mean={sigma_out_mean:.2f} nm vs sigma_in={sigma_in_nm} nm (err={rel_err*100:.1f}%)"

    def test_honeycomb_inversion_valid_flag_true_for_realistic_data(self):
        a = 500.0
        template = generate_ideal_lattice_template('honeycomb', a=a, boundary_type='hexagon', boundary_size_nm=4000.0)
        rng = np.random.default_rng(3)
        n = len(template['x'])
        x = template['x'] + rng.normal(0, 8.0, n)
        y = template['y'] + rng.normal(0, 8.0, n)
        fx, fy, S = compute_structure_factor_2d(x, y, a_nominal=a, n_bins=400, f_max_factor=2.6)
        solved = find_hexagonal_reciprocal_rotation(S, fx, fy, a=a)
        hb = compute_hexagonal_bragg_indexing(S, fx, fy, a=a, rotation_deg=solved['theta_peak_deg'], lattice_type='honeycomb')
        assert hb['honeycomb_inversion_valid'] is True

    def test_zero_disorder_ratio_near_four_for_honeycomb(self):
        a = 500.0
        template = generate_ideal_lattice_template('honeycomb', a=a, boundary_type='hexagon', boundary_size_nm=4000.0)
        fx, fy, S = compute_structure_factor_2d(template['x'], template['y'], a_nominal=a, n_bins=400, f_max_factor=2.6)
        solved = find_hexagonal_reciprocal_rotation(S, fx, fy, a=a)
        hb = compute_hexagonal_bragg_indexing(S, fx, fy, a=a, rotation_deg=solved['theta_peak_deg'], lattice_type='honeycomb')
        ratio = hb['H_ortho'] / hb['H_axis1']
        assert 3.5 < ratio < 4.3


class TestDirectionalMonteCarloOrthoCurve:

    def test_honeycomb_ratio_approaches_four_at_zero_disorder(self):
        mc = run_hexagonal_monte_carlo_calibration(
            'honeycomb', a=500.0, boundary_type='hexagon', boundary_size_nm=3000.0,
            sigma_min=0.0, sigma_max=20.0, n_sigma_steps=3, iterations_per_step=15,
            rotation_deg=5.0, seed=1
        )
        ratio0 = mc['H_mean_ortho'][0] / mc['H_mean_axis1'][0]
        assert 3.5 < ratio0 < 4.3

    def test_hexagonal_ratio_approaches_one_at_zero_disorder(self):
        mc = run_hexagonal_monte_carlo_calibration(
            'hexagonal', a=500.0, boundary_type='hexagon', boundary_size_nm=3000.0,
            sigma_min=0.0, sigma_max=20.0, n_sigma_steps=3, iterations_per_step=15,
            rotation_deg=-8.0, seed=1
        )
        ratio0 = mc['H_mean_ortho'][0] / mc['H_mean_axis1'][0]
        assert 0.7 < ratio0 < 1.3

    def test_ortho_curve_monotonically_decreasing(self):
        mc = run_hexagonal_monte_carlo_calibration(
            'honeycomb', a=500.0, boundary_type='hexagon', boundary_size_nm=3000.0,
            sigma_min=0.0, sigma_max=40.0, n_sigma_steps=8, iterations_per_step=10,
            rotation_deg=20.0, seed=2
        )
        assert np.all(np.diff(mc['H_mean_ortho']) <= 1e-6)


def _load_lattice_locs(win, lattice_type, a=500.0, rotation_deg=6.0, n_noise=3.0, seed=0, boundary_nm=3000.0):
    template = generate_ideal_lattice_template(
        lattice_type, a=a, boundary_type='hexagon', boundary_size_nm=boundary_nm, rotation_deg=rotation_deg
    )
    rng = np.random.default_rng(seed)
    n = len(template['x'])
    x_nm = template['x'] + rng.normal(0, n_noise, n)
    y_nm = template['y'] + rng.normal(0, n_noise, n)
    df = pd.DataFrame({'x_nm': x_nm, 'y_nm': y_nm, 'x': x_nm / 50.0, 'y': y_nm / 50.0, 'photons': np.full(n, 1000.0)})
    win.locs_df = win._assign_particle_ids_to_raw(df)
    win.locs_df_raw = win.locs_df.copy()
    win.spin_a_nominal.setValue(a)
    win.spin_boundary_size.setValue(boundary_nm)


class TestGuiHeadlessSmokeHoneycomb:
    """Test 5 de la misión: seleccionar Honeycomb puebla ambas sub-pestañas de
    cortes 1D e instancia todos los Boxes de Metrología Unitaria sin
    excepciones ni fugas de señal (signal leaks)."""

    def test_honeycomb_selection_populates_both_cut_subtabs_and_metrology_boxes(self, app):
        win = LatticeDisorderWindow()
        win.tabs.setCurrentIndex(2)
        win.combo_lattice_type.setCurrentIndex(2)  # Honeycomb
        _load_lattice_locs(win, 'honeycomb')

        win._on_recalc_grid()
        win._on_recalculate_reciprocal()  # no debe lanzar excepción

        assert win.tabs_1d_cuts.isTabVisible(1) is True
        assert win.tabs_1d_cuts.isTabVisible(2) is True
        assert len(win.hex_cut_panels) == 6
        for angle_off, (plot, box) in win.hex_cut_panels.items():
            assert len(plot.listDataItems()) >= 1
            assert len(box.text()) > 20
        for card in (win.lbl_card_h2h1, win.lbl_card_diag, win.lbl_card_h1h0, win.lbl_card_wilson):
            assert len(card.text()) > 20
        win.close()

    def test_switching_between_lattice_types_does_not_leak_stale_curves(self, app):
        # Recalcular dos veces (honeycomb -> hexagonal) no debe acumular curvas
        # huérfanas en los paneles (cada plot.clear() al inicio de cada corte).
        win = LatticeDisorderWindow()
        win.tabs.setCurrentIndex(2)
        win.combo_lattice_type.setCurrentIndex(2)
        _load_lattice_locs(win, 'honeycomb', seed=1)
        win._on_recalc_grid()
        win._on_recalculate_reciprocal()

        win.combo_lattice_type.setCurrentIndex(1)
        _load_lattice_locs(win, 'hexagonal', seed=2)
        win._on_recalc_grid()
        win._on_recalculate_reciprocal()

        for _angle_off, (plot, _box) in win.hex_cut_panels.items():
            assert len(plot.listDataItems()) == 1  # no acumulación de curvas viejas
        win.close()


class TestPackageCMonteCarloPropagation:
    """Paquete C: la propagación Pestaña 3 -> Pestaña 4 usa el período real
    (spin_a_nominal), no el ajuste Cartesiano físicamente inválido para
    familia hexagonal."""

    def test_propagate_uses_real_hex_period_not_cartesian_fit(self, app, monkeypatch):
        monkeypatch.setattr("analysis.lattice_disorder_gui.QMessageBox.information", lambda *a, **k: None)
        win = LatticeDisorderWindow()
        win.combo_lattice_type.setCurrentIndex(2)
        a_real = 437.0  # deliberadamente distinto de cualquier valor "redondo" por defecto
        _load_lattice_locs(win, 'honeycomb', a=a_real, boundary_nm=3000.0)
        win._on_recalc_grid()
        win._on_recalculate_reciprocal()

        win._on_propagate_to_mc()

        assert abs(win.spin_mc_ax.value() - a_real) < 1e-6
        assert win.chk_mc_anisotropy.isChecked() is False
        win.close()
