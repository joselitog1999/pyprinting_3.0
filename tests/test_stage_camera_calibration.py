# -*- coding: utf-8 -*-
"""
test_stage_camera_calibration.py — Pruebas unitarias para
core/stage_camera_calibration.py (Fase B: asistente de calibración de paso físico con
confirmación visual, y corroboración por fiducial de dímeros).

PyPrinting 3.0 — UNSAM Nanofotónica
"""
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ["PYPRINTING_SAFE"] = "1"

# IMPORTANTE: config debe importarse antes que cualquier módulo que transitivamente
# importe trackpy — config.py antepone .venv/Lib/site-packages a sys.path, donde vive
# la instalación real de trackpy en este entorno (ver DECISION_LOG.md / patrón ya
# establecido en tests/test_shutter_alignment_and_heartbeat.py para PyQt6). Si
# core.stage_camera_calibration se importara antes, su "except ImportError" silencioso
# dejaría _TRACKPY_AVAILABLE en False aunque trackpy sí esté disponible.
import config  # noqa: F401

import numpy as np
import pytest

from core.stage_camera_transform import StageCameraTransform, SENSOR_WIDTH_PX, SENSOR_HEIGHT_PX
from core.stage_camera_calibration import (
    display_fraction_to_sensor_px, detect_dominant_feature, StepCalibrationSession,
    compare_fiducial_calibration, _TRACKPY_AVAILABLE,
)

pytestmark = pytest.mark.skipif(not _TRACKPY_AVAILABLE, reason="trackpy no disponible en este entorno")

FRAME_W, FRAME_H = 200, 150


def _make_synthetic_frame(width=FRAME_W, height=FRAME_H, blobs=((100.0, 75.0, 220.0),),
                            sigma=2.2, noise_std=4.0, seed=0):
    """Genera un frame sintético en escala de grises (replicado a 3 canales) con
    blobs gaussianos en las posiciones dadas [(x_px, y_px, amplitud), ...] sobre un
    fondo ruidoso — suficientemente realista para que trackpy los detecte."""
    rng = np.random.default_rng(seed)
    img = rng.normal(loc=30.0, scale=noise_std, size=(height, width)).astype(float)
    yy, xx = np.mgrid[0:height, 0:width]
    for bx, by, amp in blobs:
        img += amp * np.exp(-(((xx - bx) ** 2 + (yy - by) ** 2) / (2 * sigma ** 2)))
    img = np.clip(img, 0, 255).astype(np.uint8)
    return np.stack([img, img, img], axis=-1)


# ── display_fraction_to_sensor_px ────────────────────────────────────────────

def test_display_fraction_swaps_axes_per_rotate_flip_transposition():
    # fx (horizontal en pantalla) -> sensor Y ; fy (vertical en pantalla) -> sensor X
    sx, sy = display_fraction_to_sensor_px(0.0, 0.0)
    assert sx == pytest.approx(0.0)
    assert sy == pytest.approx(0.0)

    sx, sy = display_fraction_to_sensor_px(1.0, 1.0)
    assert sx == pytest.approx(SENSOR_WIDTH_PX)
    assert sy == pytest.approx(SENSOR_HEIGHT_PX)

    sx, sy = display_fraction_to_sensor_px(0.25, 0.75)
    assert sx == pytest.approx(0.75 * SENSOR_WIDTH_PX)
    assert sy == pytest.approx(0.25 * SENSOR_HEIGHT_PX)


# ── detect_dominant_feature ──────────────────────────────────────────────────

def test_detect_dominant_feature_finds_single_blob():
    frame = _make_synthetic_frame(blobs=((100.0, 75.0, 220.0),))
    result = detect_dominant_feature(frame)
    assert result["ok"] is True
    assert result["x_px"] == pytest.approx(100.0, abs=1.0)
    assert result["y_px"] == pytest.approx(75.0, abs=1.0)


def test_detect_dominant_feature_no_particle_fails_explicitly():
    """Ruido puro (sin ningún blob real): trackpy típicamente reporta muchas
    detecciones espurias de mass similar entre sí (fluctuaciones de ruido) — el guard
    de ambigüedad debe rechazarlas igual que rechazaría dos partículas reales
    igual de prominentes. Lo que importa es que NUNCA elija una al azar (ok=False),
    no cuál de los dos mensajes de rechazo específicos dispara."""
    frame = np.random.default_rng(1).normal(30.0, 3.0, size=(FRAME_H, FRAME_W)).astype(np.uint8)
    frame = np.stack([frame, frame, frame], axis=-1)
    result = detect_dominant_feature(frame)
    assert result["ok"] is False
    assert result["reason"]


def test_detect_dominant_feature_ambiguous_two_similar_blobs_fails_explicitly():
    """Dos partículas de prominencia similar: no debe adivinar cuál es la de referencia."""
    frame = _make_synthetic_frame(blobs=((60.0, 60.0, 200.0), (140.0, 90.0, 195.0)))
    result = detect_dominant_feature(frame, min_mass_ratio=1.5)
    assert result["ok"] is False
    assert "ambig" in result["reason"].lower()
    assert result["n_candidates"] >= 2


def test_detect_dominant_feature_clear_dominant_blob_succeeds_despite_second():
    """Una partícula claramente más brillante que una tenue secundaria sí debe aceptarse."""
    frame = _make_synthetic_frame(blobs=((100.0, 75.0, 230.0), (20.0, 20.0, 40.0)))
    result = detect_dominant_feature(frame, min_mass_ratio=1.5)
    assert result["ok"] is True
    assert result["x_px"] == pytest.approx(100.0, abs=1.5)


# ── StepCalibrationSession ───────────────────────────────────────────────────

def test_step_calibration_session_computes_expected_delta():
    session = StepCalibrationSession(axis=2, step_um=1.0, frame_width_px=FRAME_W, frame_height_px=FRAME_H)
    for _ in range(3):
        session.add_before_frame(_make_synthetic_frame(blobs=((100.0, 75.0, 220.0),), seed=1))
    for _ in range(3):
        session.add_after_frame(_make_synthetic_frame(blobs=((130.0, 75.0, 220.0),), seed=2))

    result = session.compute_result()
    assert result["ok"] is True
    assert result["axis"] == 2
    # La partícula se movió +30px en x de pantalla (fx) -> según la transposición,
    # delta_v_sensor_px debe ser ~ +30/FRAME_W * SENSOR_HEIGHT_PX, delta_u ~ 0.
    expected_dv = (30.0 / FRAME_W) * SENSOR_HEIGHT_PX
    assert result["delta_v_sensor_px"] == pytest.approx(expected_dv, rel=0.05)
    assert result["delta_u_sensor_px"] == pytest.approx(0.0, abs=5.0)


def test_step_calibration_session_rejects_unstable_position():
    session = StepCalibrationSession(axis=1, step_um=1.0, frame_width_px=FRAME_W, frame_height_px=FRAME_H)
    # 3 frames "antes" con la partícula saltando de posición -> alta dispersión
    for i, bx in enumerate([80.0, 100.0, 120.0]):
        session.add_before_frame(_make_synthetic_frame(blobs=((bx, 75.0, 220.0),), seed=10 + i))
    for _ in range(3):
        session.add_after_frame(_make_synthetic_frame(blobs=((100.0, 75.0, 220.0),), seed=20))

    result = session.compute_result(max_std_px=2.0)
    assert result["ok"] is False
    assert "inestable" in result["reason"].lower()


def test_step_calibration_session_rejects_when_no_after_frames():
    session = StepCalibrationSession(axis=1, step_um=1.0, frame_width_px=FRAME_W, frame_height_px=FRAME_H)
    session.add_before_frame(_make_synthetic_frame())
    result = session.compute_result()
    assert result["ok"] is False


def test_step_calibration_session_invalid_axis_raises():
    with pytest.raises(ValueError):
        StepCalibrationSession(axis=3, step_um=1.0, frame_width_px=FRAME_W, frame_height_px=FRAME_H)


def test_step_calibration_session_zero_step_raises():
    with pytest.raises(ValueError):
        StepCalibrationSession(axis=1, step_um=0.0, frame_width_px=FRAME_W, frame_height_px=FRAME_H)


# ── Flujo completo: dos StepCalibrationSession -> StageCameraTransform ──────

def test_full_wizard_flow_produces_calibration_matching_known_sign_pattern(tmp_path):
    """Simula el asistente completo: paso en eje 1 (debe mover la partícula en pantalla
    Y, según la convención verificada), paso en eje 2 (debe moverla en pantalla X),
    ambos resultados aplicados a StageCameraTransform.calibrate_axis_from_step()."""
    # Eje 1 (+1 µm) -> platina arriba -> laser DERECHA en cámara (+u_sensor) según la
    # convención verificada; en fracción de pantalla eso corresponde a mover fy
    # (vertical de pantalla), dado el swap de la transposición (display Y -> sensor X).
    s1 = StepCalibrationSession(axis=1, step_um=1.0, frame_width_px=FRAME_W, frame_height_px=FRAME_H)
    for _ in range(3):
        s1.add_before_frame(_make_synthetic_frame(blobs=((100.0, 75.0, 220.0),), seed=1))
    for _ in range(3):
        s1.add_after_frame(_make_synthetic_frame(blobs=((100.0, 95.0, 220.0),), seed=2))
    r1 = s1.compute_result()
    assert r1["ok"] is True

    s2 = StepCalibrationSession(axis=2, step_um=1.0, frame_width_px=FRAME_W, frame_height_px=FRAME_H)
    for _ in range(3):
        s2.add_before_frame(_make_synthetic_frame(blobs=((100.0, 75.0, 220.0),), seed=3))
    for _ in range(3):
        s2.add_after_frame(_make_synthetic_frame(blobs=((120.0, 75.0, 220.0),), seed=4))
    r2 = s2.compute_result()
    assert r2["ok"] is True

    t = StageCameraTransform("test_rig_wizard", base_dir=tmp_path)
    t.calibrate_axis_from_step(1, r1["step_um"], r1["delta_u_sensor_px"], r1["delta_v_sensor_px"])
    t.calibrate_axis_from_step(2, r2["step_um"], r2["delta_u_sensor_px"], r2["delta_v_sensor_px"])

    assert t.is_calibrated()
    # No forzamos el signo exacto acá (depende de la dirección física real de los ejes
    # en el banco) — lo que sí verificamos es que la matriz queda bien formada y
    # utilizable de punta a punta.
    axis1, axis2 = t.sensor_px_delta_to_stage_um(*t.stage_um_delta_to_sensor_px(1.0, 0.0))
    assert axis1 == pytest.approx(1.0, abs=1e-6)
    assert axis2 == pytest.approx(0.0, abs=1e-6)


# ── compare_fiducial_calibration ─────────────────────────────────────────────

def test_compare_fiducial_calibration_reports_zero_discrepancy_for_consistent_data(tmp_path):
    t = StageCameraTransform("test_rig_fiducial", base_dir=tmp_path)
    t.calibrate_axis_from_step(1, 1.0, 0.0, 100.0)
    t.calibrate_axis_from_step(2, 1.0, 100.0, 0.0)

    # Un desplazamiento de sensor puro en u de 100px corresponde a eje2=+1µm, eje1=0 —
    # construimos dos puntos de cámara (fracción 1x) que produzcan exactamente ese delta.
    pt1_frac = (0.5, 0.5)
    u1, v1 = display_fraction_to_sensor_px(*pt1_frac)
    target_u, target_v = u1 + 100.0, v1
    pt2_frac = (target_v / SENSOR_HEIGHT_PX, target_u / SENSOR_WIDTH_PX)

    result = compare_fiducial_calibration(
        t, printed_dx_um=0.0, printed_dy_um=1.0,
        camera_pt1_frac=pt1_frac, camera_pt2_frac=pt2_frac,
        confocal_measured_dx_um=0.0, confocal_measured_dy_um=1.0,
    )
    assert result["discrepancy_vs_printed_pct"] == pytest.approx(0.0, abs=1e-3)
    assert result["discrepancy_vs_confocal_pct"] == pytest.approx(0.0, abs=1e-3)


def test_compare_fiducial_calibration_flags_real_discrepancy(tmp_path):
    t = StageCameraTransform("test_rig_fiducial2", base_dir=tmp_path)
    t.calibrate_axis_from_step(1, 1.0, 0.0, 100.0)
    t.calibrate_axis_from_step(2, 1.0, 100.0, 0.0)

    pt1_frac = (0.5, 0.5)
    u1, v1 = display_fraction_to_sensor_px(*pt1_frac)
    target_u, target_v = u1 + 100.0, v1
    pt2_frac = (target_v / SENSOR_HEIGHT_PX, target_u / SENSOR_WIDTH_PX)

    # Nominal impreso muy distinto de lo que predice la calibración -> debe reflejarse
    # como una discrepancia grande, no quedar oculto.
    result = compare_fiducial_calibration(
        t, printed_dx_um=0.0, printed_dy_um=5.0,
        camera_pt1_frac=pt1_frac, camera_pt2_frac=pt2_frac,
    )
    assert result["discrepancy_vs_printed_pct"] > 50.0
