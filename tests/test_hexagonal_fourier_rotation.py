# -*- coding: utf-8 -*-
"""
test_hexagonal_fourier_rotation.py — Pruebas de la Misión "Critical
Enhancements & Physical Modeling Corrections", Paquete D.1
(core/lattice_disorder.py): solver azimutal automático de orientación
find_hexagonal_reciprocal_rotation(), y D.3 compute_hexagonal_bragg_indexing().

Cubre:
1. Para una red hexagonal ideal SIN rotación real-espacio, el solver
   recupera theta_peak ≈ -30° (convención ya usada en el código existente
   para los marcadores hexagonales, confirmada por la revisión de
   computational-physicist: el retículo recíproco de a1=(a,0),
   a2=(a·cos60°,a·sin60°) está rotado -30° respecto al real).
2. Para una red rotada rotation_deg=θ_real, theta_peak sigue θ_real-30°
   (plegado módulo 60°, dentro del rango [-30°,30°)) dentro del paso
   angular de muestreo (0.5°).
3. compute_hexagonal_bragg_indexing(), con rotation_deg correctamente
   alineado al pico real, reporta H_axis1/H_axis2 sustancialmente mayores
   que un ángulo de sondeo desalineado (a mitad de camino entre picos).
4. Honeycomb: el solver también recupera correctamente el ángulo (posición
   de picos de 1er orden 6-fold simétrica, independiente de la base).

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

from core.lattice_disorder import (
    compute_structure_factor_2d,
    compute_hexagonal_bragg_indexing,
    find_hexagonal_reciprocal_rotation,
    generate_ideal_lattice_template,
)


def _fold_to_base_range(angle_deg: float) -> float:
    return ((angle_deg + 30.0) % 60.0) - 30.0


class TestFindHexagonalReciprocalRotation:

    @pytest.mark.parametrize("theta_real", [0.0, 10.0, -15.0, 25.0])
    def test_recovers_minus_30_offset_for_hexagonal(self, theta_real):
        a = 500.0
        template = generate_ideal_lattice_template(
            'hexagonal', a=a, boundary_type='hexagon', boundary_size_nm=4000.0,
            rotation_deg=theta_real
        )
        fx, fy, S = compute_structure_factor_2d(template['x'], template['y'], a_nominal=a, n_bins=256, f_max_factor=2.0)
        result = find_hexagonal_reciprocal_rotation(S, fx, fy, a=a, angle_step_deg=0.5)

        expected = _fold_to_base_range(theta_real - 30.0)
        assert abs(result['theta_peak_deg'] - expected) <= 1.0  # tolerancia: paso angular + discretización FFT

    def test_recovers_offset_for_honeycomb(self):
        a = 500.0
        theta_real = 12.0
        template = generate_ideal_lattice_template(
            'honeycomb', a=a, boundary_type='hexagon', boundary_size_nm=4000.0,
            rotation_deg=theta_real
        )
        fx, fy, S = compute_structure_factor_2d(template['x'], template['y'], a_nominal=a, n_bins=256, f_max_factor=2.0)
        result = find_hexagonal_reciprocal_rotation(S, fx, fy, a=a, angle_step_deg=0.5)

        expected = _fold_to_base_range(theta_real - 30.0)
        assert abs(result['theta_peak_deg'] - expected) <= 1.5

    def test_returns_theta_base_and_i_fold_arrays(self):
        a = 500.0
        template = generate_ideal_lattice_template('hexagonal', a=a, boundary_type='hexagon', boundary_size_nm=4000.0)
        fx, fy, S = compute_structure_factor_2d(template['x'], template['y'], a_nominal=a, n_bins=200, f_max_factor=2.0)
        result = find_hexagonal_reciprocal_rotation(S, fx, fy, a=a, angle_step_deg=1.0)
        assert len(result['theta_base_deg']) == len(result['i_fold'])
        assert np.all(result['theta_base_deg'] >= -30.0) and np.all(result['theta_base_deg'] < 30.0)


class TestComputeHexagonalBraggIndexing:

    def test_aligned_rotation_gives_higher_axis_heights_than_misaligned(self):
        a = 500.0
        theta_real = 0.0
        template = generate_ideal_lattice_template(
            'hexagonal', a=a, boundary_type='hexagon', boundary_size_nm=4000.0, rotation_deg=theta_real
        )
        fx, fy, S = compute_structure_factor_2d(template['x'], template['y'], a_nominal=a, n_bins=256, f_max_factor=2.0)

        solved = find_hexagonal_reciprocal_rotation(S, fx, fy, a=a)
        aligned = compute_hexagonal_bragg_indexing(S, fx, fy, a=a, rotation_deg=solved['theta_peak_deg'])
        misaligned = compute_hexagonal_bragg_indexing(S, fx, fy, a=a, rotation_deg=solved['theta_peak_deg'] + 30.0)

        assert aligned['H_axis1'] > misaligned['H_axis1']
        assert aligned['H_axis2'] > misaligned['H_axis2']

    def test_ortho_radius_equals_sqrt3_times_f1(self):
        a = 500.0
        result = compute_hexagonal_bragg_indexing(
            np.zeros((10, 10)), np.linspace(-1, 1, 10), np.linspace(-1, 1, 10), a=a
        )
        assert abs(result['q_ortho'] - np.sqrt(3.0) * result['f1']) < 1e-12

    def test_returns_all_expected_keys(self):
        a = 500.0
        result = compute_hexagonal_bragg_indexing(
            np.zeros((10, 10)), np.linspace(-1, 1, 10), np.linspace(-1, 1, 10), a=a
        )
        for key in ('H_axis1', 'H_axis2', 'H_2_axis1', 'H_2_axis2', 'H_ortho',
                    'f1', 'q_ortho', 'ratio_21_axis1', 'ratio_21_axis2', 'ratio_ortho'):
            assert key in result
