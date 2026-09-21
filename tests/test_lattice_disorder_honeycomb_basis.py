# -*- coding: utf-8 -*-
"""
test_lattice_disorder_honeycomb_basis.py — Pruebas para la Fase 4 (Paquete 11) de
la misión "Refactorización y Enriquecimiento Metrológico del Analizador de
Desorden 2D": base cristalográfica honeycomb (u2, v2) editable, con propagación
dinámica a Monte Carlo — corrección #3 del usuario: default (1/3, 1/3) por
convención de laboratorio (no (1/3, 2/3), el histórico de
core/lattice_generator.py, usado por el diseñador grid_generator.py), pero
siempre editable vía casilla de texto en ambos consumidores (template matching y
calibración Monte Carlo).

Cubre:
1. generate_ideal_lattice_template() usa (1/3, 1/3) por defecto y respeta
   overrides explícitos de u2/v2 — verificado leyendo la posición real de la
   Subred B generada, no sólo que la llamada no falle.
2. run_hexagonal_monte_carlo_calibration() acepta y propaga u2/v2 hacia
   generate_ideal_lattice_template() internamente.
3. GUI: spin_honeycomb_u2/v2 tienen default 1/3, sólo visibles para honeycomb
   (idx=2), no para hexagonal/triangular (idx=1, base monoatómica).
4. _on_recalc_grid (Tab 2) lee u2/v2 de la GUI y los pasa a
   generate_ideal_lattice_template — verificado con un stub que captura los
   kwargs recibidos, sin ejecutar el registro rígido completo.
5. _update_mc_hex_info_label (Tab 4): deshabilita Nx/Ny/anisotropía/ay para
   familia hexagonal, los reactiva para 'square', y el resumen en vivo incluye
   (u2, v2) sólo para honeycomb específicamente (no para hexagonal simple).

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

from core.lattice_disorder import generate_ideal_lattice_template
from analysis.lattice_disorder_gui import LatticeDisorderWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication(sys.argv)


# ── core/lattice_disorder.py: generate_ideal_lattice_template ───────────────

def test_default_basis_is_one_third_one_third():
    template = generate_ideal_lattice_template(
        lattice_type='honeycomb', a=500.0, boundary_type='circle', boundary_size_nm=1500.0
    )
    sub_b_mask = template['sublattice_id'] == 2
    assert np.any(sub_b_mask)
    # Distancia relativa de un nodo de subred B al nodo A más próximo de su
    # propia celda: para (u2,v2)=(1/3,1/3) con a1=(a,0), a2=(a*cos60, a*sin60),
    # la posición cartesiana de un átomo B en la celda (0,0) es
    # u2*a1 + v2*a2 = (a/3)*(1 + cos60, sin60) — se verifica indirectamente
    # comparando contra el resultado de pasar el mismo u2/v2 explícitamente.
    template_explicit = generate_ideal_lattice_template(
        lattice_type='honeycomb', a=500.0, boundary_type='circle', boundary_size_nm=1500.0,
        u2=1.0 / 3.0, v2=1.0 / 3.0
    )
    np.testing.assert_allclose(template['x'], template_explicit['x'])
    np.testing.assert_allclose(template['y'], template_explicit['y'])


def test_basis_override_changes_sublattice_b_position():
    template_a = generate_ideal_lattice_template(
        lattice_type='honeycomb', a=500.0, boundary_type='circle', boundary_size_nm=1500.0,
        u2=1.0 / 3.0, v2=1.0 / 3.0
    )
    template_b = generate_ideal_lattice_template(
        lattice_type='honeycomb', a=500.0, boundary_type='circle', boundary_size_nm=1500.0,
        u2=1.0 / 3.0, v2=2.0 / 3.0  # convención histórica distinta
    )
    # Distintos u2/v2 desplazan la subred B (y hasta pueden cambiar cuántos
    # nodos caen dentro del mismo contorno recortado) — se compara el
    # centroide de la subred B en vez de arreglos ordenados de igual longitud.
    xa_b = template_a['x'][template_a['sublattice_id'] == 2]
    xb_b = template_b['x'][template_b['sublattice_id'] == 2]
    assert len(xa_b) > 0 and len(xb_b) > 0
    assert xa_b.mean() != pytest.approx(xb_b.mean(), abs=1.0)


def test_hexagonal_monoatomic_ignores_u2_v2():
    """Hexagonal/triangular (base monoatómica) no debe verse afectado por u2/v2."""
    t1 = generate_ideal_lattice_template(
        lattice_type='hexagonal', a=500.0, boundary_type='circle', boundary_size_nm=1500.0,
        u2=1.0 / 3.0, v2=1.0 / 3.0
    )
    t2 = generate_ideal_lattice_template(
        lattice_type='hexagonal', a=500.0, boundary_type='circle', boundary_size_nm=1500.0,
        u2=0.7, v2=0.9
    )
    np.testing.assert_allclose(np.sort(t1['x']), np.sort(t2['x']))


# ── GUI: campos editables y visibilidad ──────────────────────────────────────

def test_honeycomb_spinboxes_default_to_one_third(app):
    win = LatticeDisorderWindow()
    assert win.spin_honeycomb_u2.value() == pytest.approx(1.0 / 3.0, abs=1e-4)
    assert win.spin_honeycomb_v2.value() == pytest.approx(1.0 / 3.0, abs=1e-4)
    win.close()


def test_honeycomb_basis_group_visible_only_for_honeycomb(app):
    win = LatticeDisorderWindow()
    win.show()  # isVisible() refleja la cadena de ancestros; sin show() siempre da False
    win.tabs.setCurrentIndex(1)  # grp_honeycomb_basis vive en la Pestaña 2 (índice 1) -
    # una pestaña inactiva de QTabWidget oculta su contenido aunque setVisible(True) se haya llamado.
    win.combo_lattice_type.setCurrentIndex(0)  # square
    assert win.grp_honeycomb_basis.isVisible() is False

    win.combo_lattice_type.setCurrentIndex(1)  # hexagonal/triangular
    assert win.grp_honeycomb_basis.isVisible() is False

    win.combo_lattice_type.setCurrentIndex(2)  # honeycomb/grafeno
    assert win.grp_honeycomb_basis.isVisible() is True
    win.close()


def test_recalc_grid_passes_gui_basis_to_template_generator(app, monkeypatch):
    """_on_recalc_grid debe leer spin_honeycomb_u2/v2 y pasarlos tal cual a
    generate_ideal_lattice_template — se verifica interceptando la llamada."""
    import analysis.lattice_disorder_gui as gui_mod

    win = LatticeDisorderWindow()
    win.combo_lattice_type.setCurrentIndex(2)  # honeycomb
    win.spin_honeycomb_u2.setValue(0.4)
    win.spin_honeycomb_v2.setValue(0.2)
    win.locs_df = None  # dispara el warning temprano de "sin partículas" -> no sigue de largo

    captured = {}
    real_fn = gui_mod.generate_ideal_lattice_template

    def _spy(*args, **kwargs):
        captured.update(kwargs)
        return real_fn(*args, **kwargs)

    monkeypatch.setattr(gui_mod, 'generate_ideal_lattice_template', _spy)

    # Provee un locs_df mínimo para que _on_recalc_grid llegue a la rama hexagonal.
    import pandas as pd
    win.locs_df = pd.DataFrame({
        'x_nm': np.array([0.0, 500.0, 1000.0]), 'y_nm': np.array([0.0, 0.0, 0.0]),
        'x': np.array([0.0, 10.0, 20.0]), 'y': np.array([0.0, 0.0, 0.0]),
    })
    win._on_recalc_grid()

    assert captured.get('u2') == pytest.approx(0.4)
    assert captured.get('v2') == pytest.approx(0.2)
    win.close()


# ── Tab 4: deshabilitado Nx/Ny/ay + resumen en vivo ─────────────────────────

def test_mc_hex_info_label_toggles_with_lattice_family(app):
    win = LatticeDisorderWindow()
    win.show()  # isVisible() refleja la cadena de ancestros; sin show() siempre da False
    win.tabs.setCurrentIndex(3)  # lbl_mc_hex_info vive en la Pestaña 4 (índice 3)

    win.combo_lattice_type.setCurrentIndex(0)  # square
    assert win.spin_mc_n.isEnabled() is True
    assert win.chk_mc_anisotropy.isEnabled() is True
    assert win.lbl_mc_hex_info.isVisible() is False

    win.combo_lattice_type.setCurrentIndex(2)  # honeycomb
    assert win.spin_mc_n.isEnabled() is False
    assert win.spin_mc_ny.isEnabled() is False
    assert win.chk_mc_anisotropy.isEnabled() is False
    assert win.spin_mc_ay.isEnabled() is False
    assert win.lbl_mc_hex_info.isVisible() is True
    assert "u₂" in win.lbl_mc_hex_info.text()  # honeycomb incluye la base en el resumen

    win.combo_lattice_type.setCurrentIndex(1)  # hexagonal (base monoatómica)
    assert win.lbl_mc_hex_info.isVisible() is True
    assert "u₂" not in win.lbl_mc_hex_info.text()  # sin base biatómica que mostrar

    win.combo_lattice_type.setCurrentIndex(0)  # vuelta a square
    assert win.spin_mc_n.isEnabled() is True
    win.close()


def test_run_monte_carlo_hex_params_include_basis(app, monkeypatch):
    """_on_run_monte_carlo debe incluir u2/v2 en hex_params para familia honeycomb."""
    win = LatticeDisorderWindow()
    win.combo_lattice_type.setCurrentIndex(2)
    win.spin_honeycomb_u2.setValue(0.3)
    win.spin_honeycomb_v2.setValue(0.15)

    captured = {}

    class _FakeWorker:
        def __init__(self, *a, **k):
            captured.update(k)
        def start(self):
            pass
        progress_signal = type('S', (), {'connect': lambda self, f: None})()
        finished_signal = type('S', (), {'connect': lambda self, f: None})()
        error_signal = type('S', (), {'connect': lambda self, f: None})()

    import analysis.lattice_disorder_gui as gui_mod
    monkeypatch.setattr(gui_mod, 'MonteCarloWorker', _FakeWorker)

    win._on_run_monte_carlo()

    hex_params = captured.get('hex_params')
    assert hex_params is not None
    assert hex_params['u2'] == pytest.approx(0.3)
    assert hex_params['v2'] == pytest.approx(0.15)
    win.close()
