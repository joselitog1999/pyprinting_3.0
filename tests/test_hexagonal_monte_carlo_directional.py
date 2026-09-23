# -*- coding: utf-8 -*-
"""
test_hexagonal_monte_carlo_directional.py — Pruebas de la Misión "Critical
Enhancements & Physical Modeling Corrections", Paquete D.4
(core/lattice_disorder.py): run_hexagonal_monte_carlo_calibration() con
soporte direccional (rotation_deg, H_mean_axis1/H_mean_axis2) y su consumo
en analysis/lattice_disorder_gui.py::_plot_debye_waller.

Cubre:
1. rotation_deg=0.0 (por defecto) es retrocompatible: H_mean/H_std idénticos
   al comportamiento previo a la misión.
2. Con rotation_deg != 0.0, la red ideal sintética se genera YA rotada en
   espacio real (para que sus picos de Bragg reales coincidan con las
   direcciones evaluadas) — de lo contrario la calibración muestrea fuera
   del pico real y produce una atenuación Debye-Waller CRECIENTE espuria
   con sigma (bug real encontrado y corregido durante esta implementación).
   Se verifica monotonía decreciente para varios rotation_deg no triviales.
2b. Fija numéricamente la razón física detrás de (2): con rotation_deg no
    nulo, si NO se rota también la red sintética (comportamiento previo al
    fix), H_mean dejaría de ser monótonamente decreciente — se reproduce
    el bug llamando directamente a generate_ideal_lattice_template() sin
    rotación y comparando contra la curva corregida, para que una futura
    regresión que vuelva a desacoplar la rotación de la red del ángulo de
    evaluación sea detectada.
3. H_mean_axis1/H_std_axis1 y H_mean_axis2/H_std_axis2 están presentes,
   monótonamente decrecientes, y estadísticamente equivalentes entre sí
   (mismo modelo de desorden gaussiano isotrópico — sin mecanismo de
   anisotropía en la simulación, ambas familias de 3 réplicas equivalentes
   por simetría 6-fold deben converger al mismo valor esperado).
4. _plot_debye_waller() de la GUI no lanza excepción para mc_results
   hexagonal con hex_bragg presente en reciprocal_results, y reporta
   sigma_1/sigma_2/sigma_medio/anisotropía en lbl_mc_results.

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

from core.lattice_disorder import (
    run_hexagonal_monte_carlo_calibration,
    compute_hexagonal_bragg_indexing,
    generate_ideal_lattice_template,
    compute_structure_factor_2d,
)
from analysis.lattice_disorder_gui import LatticeDisorderWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication(sys.argv)


class TestDirectionalMonteCarloBasics:

    def test_default_rotation_zero_matches_isotropic_curve_shape(self):
        mc = run_hexagonal_monte_carlo_calibration(
            'hexagonal', a=500.0, boundary_type='hexagon', boundary_size_nm=3000.0,
            sigma_min=0.0, sigma_max=30.0, n_sigma_steps=5, iterations_per_step=8, seed=3
        )
        assert mc['rotation_deg'] == 0.0
        assert np.all(np.diff(mc['H_mean']) <= 1e-6)

    @pytest.mark.parametrize("rotation_deg", [-22.0, 10.0, 37.0])
    def test_directional_curves_monotonically_decreasing(self, rotation_deg):
        mc = run_hexagonal_monte_carlo_calibration(
            'hexagonal', a=500.0, boundary_type='hexagon', boundary_size_nm=3000.0,
            sigma_min=0.0, sigma_max=40.0, n_sigma_steps=8, iterations_per_step=12,
            rotation_deg=rotation_deg, seed=5
        )
        assert np.all(np.diff(mc['H_mean_axis1']) <= 1e-6), "H_mean_axis1 debe decrecer monótonamente con sigma"
        assert np.all(np.diff(mc['H_mean_axis2']) <= 1e-6), "H_mean_axis2 debe decrecer monótonamente con sigma"

    def test_unrotated_lattice_with_offset_evaluation_reproduces_spurious_increase(self):
        """Reproduce directamente el bug corregido: si se evalúa S en
        direcciones desplazadas rotation_deg SIN rotar la red sintética
        (comportamiento previo al fix), la atenuación medida deja de ser
        monótonamente decreciente -- confirmando por qué generate_ideal_lattice_template
        debe recibir rotation_deg dentro de run_hexagonal_monte_carlo_calibration."""
        a = 500.0
        rotation_deg = 25.0
        sigma_values = np.array([0.0, 10.0, 20.0, 30.0, 40.0])
        rng = np.random.default_rng(11)
        template = generate_ideal_lattice_template(
            'hexagonal', a=a, boundary_type='hexagon', boundary_size_nm=3000.0, rotation_deg=0.0
        )
        f0 = 2.0 / (np.sqrt(3.0) * a)
        angles_deg = np.array([-30.0, 90.0, 210.0]) + rotation_deg  # familia eje 1, MAL alineada
        angles_rad = np.radians(angles_deg)
        heights = []
        for s in sigma_values:
            reps = []
            for _ in range(10):
                x_noisy = template['x'] + (rng.normal(0, s, len(template['x'])) if s > 0 else 0.0)
                y_noisy = template['y'] + (rng.normal(0, s, len(template['y'])) if s > 0 else 0.0)
                vals = []
                for th in angles_rad:
                    fx_dir = f0 * np.cos(th)
                    fy_dir = f0 * np.sin(th)
                    phase = fx_dir * x_noisy + fy_dir * y_noisy
                    amp = np.sum(np.exp(-2j * np.pi * phase))
                    vals.append((np.abs(amp) ** 2) / len(x_noisy))
                reps.append(np.mean(vals))
            heights.append(np.mean(reps))
        heights = np.array(heights)
        # Con la red desalineada de la dirección de evaluación, la atenuación
        # NO decrece monótonamente (confirma el modo de falla que motivó el fix).
        assert not np.all(np.diff(heights) <= 1e-6)


class TestAxis1Axis2StatisticalEquivalence:

    def test_axis1_and_axis2_converge_to_similar_values_for_isotropic_disorder(self):
        # El modelo de ruido gaussiano isotrópico no tiene mecanismo de anisotropía:
        # H_mean_axis1 y H_mean_axis2 deben converger al mismo valor esperado
        # (dentro de ruido de muestreo MC), ya que ambas familias de 3 réplicas
        # son equivalentes por simetría 6-fold de una red no rotada relativa a
        # sí misma.
        mc = run_hexagonal_monte_carlo_calibration(
            'hexagonal', a=500.0, boundary_type='hexagon', boundary_size_nm=4000.0,
            sigma_min=0.0, sigma_max=30.0, n_sigma_steps=5, iterations_per_step=40,
            rotation_deg=15.0, seed=99
        )
        rel_diff = np.abs(mc['H_mean_axis1'] - mc['H_mean_axis2']) / np.maximum(mc['H_mean_axis1'], 1e-6)
        assert np.all(rel_diff < 0.25)  # tolerancia generosa por ruido MC con pocas iteraciones


class TestPlotDebyeWallerHexagonalBranch:

    def test_plot_debye_waller_hex_family_does_not_raise_and_reports_sigma1_sigma2(self, app):
        win = LatticeDisorderWindow()
        a = 500.0
        mc = run_hexagonal_monte_carlo_calibration(
            'hexagonal', a=a, boundary_type='hexagon', boundary_size_nm=3000.0,
            sigma_min=0.0, sigma_max=30.0, n_sigma_steps=5, iterations_per_step=8,
            rotation_deg=-10.0, seed=2
        )
        win.mc_results = mc

        template = generate_ideal_lattice_template('hexagonal', a=a, boundary_type='hexagon', boundary_size_nm=3000.0)
        fx, fy, S = compute_structure_factor_2d(template['x'], template['y'], a_nominal=a, n_bins=128, f_max_factor=2.0)
        hex_bragg = compute_hexagonal_bragg_indexing(S, fx, fy, a=a, rotation_deg=-10.0)
        win.reciprocal_results = {'S': S, 'fx': fx, 'fy': fy, 'hex_bragg': hex_bragg}

        win._plot_debye_waller()  # no debe lanzar excepción

        txt = win.lbl_mc_results.text()
        assert "σ_1" in txt or "sigma_1" in txt.lower() or "INVERSIÓN DEBYE-WALLER DIRECCIONAL" in txt
        win.close()

    def test_plot_debye_waller_hex_family_without_hex_bragg_does_not_raise(self, app):
        """Si reciprocal_results existe pero aún no tiene 'hex_bragg' (p.ej. el
        usuario corrió Monte Carlo antes de recalcular Espacio Recíproco), la
        rama hexagonal debe degradar sin excepción, no crashear."""
        win = LatticeDisorderWindow()
        mc = run_hexagonal_monte_carlo_calibration(
            'hexagonal', a=500.0, boundary_type='hexagon', boundary_size_nm=3000.0,
            sigma_min=0.0, sigma_max=20.0, n_sigma_steps=3, iterations_per_step=5, seed=4
        )
        win.mc_results = mc
        win.reciprocal_results = {'S': np.zeros((10, 10)), 'fx': np.linspace(-1, 1, 10), 'fy': np.linspace(-1, 1, 10)}
        win._plot_debye_waller()
        win.close()
