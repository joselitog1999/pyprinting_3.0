# -*- coding: utf-8 -*-
"""
test_stage_camera_transform.py — Pruebas unitarias para core/stage_camera_transform.py
(Fase A de la misión "Suite de Cámara Réflex Canon, Cinemática de Ejes y Sincronización
Espacial Bidireccional").

Verifica: calibración columna-por-columna desde pasos físicos conocidos, coherencia con
el patrón de signos ya verificado (derivado a mano de REGIME_LEGACY + la convención
física confirmada por el operador), ida-y-vuelta forward/inverse, persistencia separada
por rig, y que ningún método de conversión devuelva un valor por defecto silencioso
antes de calibrar.

PyPrinting 3.0 — UNSAM Nanofotónica
"""
import os
import sys
import tempfile
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ["PYPRINTING_SAFE"] = "1"

import config  # noqa: F401
import numpy as np
import pytest

from core.stage_camera_transform import StageCameraTransform, KNOWN_SIGN_PATTERN


@pytest.fixture
def tmp_calib_dir():
    d = tempfile.mkdtemp(prefix="sct_test_")
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


def _calibrate_with_verified_convention(t: StageCameraTransform):
    """Aplica los dos pasos de calibración exactamente como predice la convención física
    verificada por el operador: eje1(+1µm) -> +100px en v (abajo en cámara);
    eje2(+1µm) -> +100px en u (derecha en cámara)."""
    t.calibrate_axis_from_step(axis=1, physical_step_um=1.0, measured_delta_u_px=0.0, measured_delta_v_px=100.0)
    t.calibrate_axis_from_step(axis=2, physical_step_um=1.0, measured_delta_u_px=100.0, measured_delta_v_px=0.0)


def test_uncalibrated_raises_on_every_conversion(tmp_calib_dir):
    t = StageCameraTransform("test_rig", base_dir=tmp_calib_dir)
    assert not t.is_calibrated()
    with pytest.raises(RuntimeError):
        t.sensor_px_delta_to_stage_um(10, 10)
    with pytest.raises(RuntimeError):
        t.stage_um_delta_to_sensor_px(1, 1)
    with pytest.raises(RuntimeError):
        t.determinant()


def test_calibration_incomplete_until_both_axes_done(tmp_calib_dir):
    t = StageCameraTransform("test_rig", base_dir=tmp_calib_dir)
    t.calibrate_axis_from_step(axis=1, physical_step_um=1.0, measured_delta_u_px=0.0, measured_delta_v_px=100.0)
    assert not t.is_calibrated(), "Con un solo eje calibrado, la matriz todavía no debe estar completa"
    t.calibrate_axis_from_step(axis=2, physical_step_um=1.0, measured_delta_u_px=100.0, measured_delta_v_px=0.0)
    assert t.is_calibrated()


def test_calibration_matches_known_verified_sign_pattern(tmp_calib_dir):
    t = StageCameraTransform("test_rig", base_dir=tmp_calib_dir)
    _calibrate_with_verified_convention(t)
    assert t.matches_known_sign_pattern() is True


def test_calibration_with_wrong_sign_is_flagged(tmp_calib_dir):
    """Si el operador midiera (por error de montaje, óptica invertida, etc.) el signo
    opuesto al ya verificado, matches_known_sign_pattern() debe detectarlo, no aceptarlo
    en silencio (recomendación explícita del panel de metrología / devil-advocate)."""
    t = StageCameraTransform("test_rig", base_dir=tmp_calib_dir)
    t.calibrate_axis_from_step(axis=1, physical_step_um=1.0, measured_delta_u_px=0.0, measured_delta_v_px=-100.0)
    t.calibrate_axis_from_step(axis=2, physical_step_um=1.0, measured_delta_u_px=100.0, measured_delta_v_px=0.0)
    assert t.matches_known_sign_pattern() is False


def test_determinant_is_negative_reflection_not_rotation(tmp_calib_dir):
    """Confirma el hallazgo de la Ronda 1: la transformación real es una reflexión
    (det<0), no una rotación pura (det>0) como sugería la redacción original del brief."""
    t = StageCameraTransform("test_rig", base_dir=tmp_calib_dir)
    _calibrate_with_verified_convention(t)
    assert t.determinant() < 0
    assert np.linalg.det(KNOWN_SIGN_PATTERN) < 0


def test_forward_inverse_roundtrip(tmp_calib_dir):
    t = StageCameraTransform("test_rig", base_dir=tmp_calib_dir)
    _calibrate_with_verified_convention(t)

    for du, dv in [(37.0, -14.0), (0.0, 0.0), (-200.0, 500.0)]:
        axis1, axis2 = t.sensor_px_delta_to_stage_um(du, dv)
        du2, dv2 = t.stage_um_delta_to_sensor_px(axis1, axis2)
        assert du2 == pytest.approx(du, abs=1e-6)
        assert dv2 == pytest.approx(dv, abs=1e-6)


def test_pure_u_shift_maps_to_axis2_only(tmp_calib_dir):
    """Reproduce numéricamente la convención verificada: un corrimiento puro en u
    (horizontal, cámara) debe atribuirse enteramente al eje físico 2, nada al eje 1."""
    t = StageCameraTransform("test_rig", base_dir=tmp_calib_dir)
    _calibrate_with_verified_convention(t)
    axis1, axis2 = t.sensor_px_delta_to_stage_um(100.0, 0.0)
    assert axis1 == pytest.approx(0.0, abs=1e-9)
    assert axis2 == pytest.approx(1.0, abs=1e-9)


def test_pure_v_shift_maps_to_axis1_only(tmp_calib_dir):
    t = StageCameraTransform("test_rig", base_dir=tmp_calib_dir)
    _calibrate_with_verified_convention(t)
    axis1, axis2 = t.sensor_px_delta_to_stage_um(0.0, 100.0)
    assert axis1 == pytest.approx(1.0, abs=1e-9)
    assert axis2 == pytest.approx(0.0, abs=1e-9)


def test_save_and_load_roundtrip(tmp_calib_dir):
    t1 = StageCameraTransform("microscopio_derecho", base_dir=tmp_calib_dir)
    _calibrate_with_verified_convention(t1)
    t1.save()

    t2 = StageCameraTransform("microscopio_derecho", base_dir=tmp_calib_dir)
    assert t2.is_calibrated(), "load() en __init__ debe recuperar la calibración persistida"
    np.testing.assert_allclose(t2.M_forward, t1.M_forward)
    assert t2.calibration_method == "step_wizard"
    assert t2.calibrated_at is not None


def test_separate_rigs_do_not_share_calibration_file(tmp_calib_dir):
    t_right = StageCameraTransform("microscopio_derecho", base_dir=tmp_calib_dir)
    _calibrate_with_verified_convention(t_right)
    t_right.save()

    t_counter = StageCameraTransform("contrapropagante", base_dir=tmp_calib_dir)
    assert not t_counter.is_calibrated(), "Un rig no calibrado no debe heredar la calibración de otro rig"

    files = list(tmp_calib_dir.glob("stage_camera_calibration_*.json"))
    assert len(files) == 1
    assert "microscopio_derecho" in files[0].name


def test_reset_calibration_clears_state(tmp_calib_dir):
    t = StageCameraTransform("test_rig", base_dir=tmp_calib_dir)
    _calibrate_with_verified_convention(t)
    assert t.is_calibrated()
    t.reset_calibration()
    assert not t.is_calibrated()
    with pytest.raises(RuntimeError):
        t.sensor_px_delta_to_stage_um(1, 1)


def test_set_calibrated_matrix_direct(tmp_calib_dir):
    t = StageCameraTransform("test_rig", base_dir=tmp_calib_dir)
    M = np.array([[0.0, 50.0], [50.0, 0.0]])
    t.set_calibrated_matrix(M, method="fiducial_dimer")
    assert t.is_calibrated()
    assert t.calibration_method == "fiducial_dimer"
    axis1, axis2 = t.sensor_px_delta_to_stage_um(50.0, 0.0)
    assert axis2 == pytest.approx(1.0)


# ── record_fiducial_validation (Fase B, Método B) ────────────────────────────

def test_record_fiducial_validation_requires_calibration(tmp_calib_dir):
    t = StageCameraTransform("test_rig", base_dir=tmp_calib_dir)
    with pytest.raises(RuntimeError):
        t.record_fiducial_validation({"discrepancy_vs_printed_pct": 2.0})


def test_record_fiducial_validation_persists_with_save(tmp_calib_dir):
    t1 = StageCameraTransform("test_rig", base_dir=tmp_calib_dir)
    _calibrate_with_verified_convention(t1)
    t1.record_fiducial_validation({"discrepancy_vs_printed_pct": 3.5, "predicted_magnitude_um": 1.02})
    assert t1.last_fiducial_validation is not None
    assert "recorded_at" in t1.last_fiducial_validation
    t1.save()

    t2 = StageCameraTransform("test_rig", base_dir=tmp_calib_dir)
    assert t2.last_fiducial_validation is not None
    assert t2.last_fiducial_validation["discrepancy_vs_printed_pct"] == pytest.approx(3.5)


def test_reset_calibration_clears_fiducial_validation_too(tmp_calib_dir):
    t = StageCameraTransform("test_rig", base_dir=tmp_calib_dir)
    _calibrate_with_verified_convention(t)
    t.record_fiducial_validation({"discrepancy_vs_printed_pct": 1.0})
    t.reset_calibration()
    assert t.last_fiducial_validation is None
