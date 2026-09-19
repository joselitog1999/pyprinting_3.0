# -*- coding: utf-8 -*-
"""
test_fiducial_validation_dialog.py — Pruebas para FiducialValidationDialog y
CameraWindow._open_fiducial_validation (Fase B, Método B: corroboración por fiducial de
dímeros impresos).

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
from PyQt6.QtWidgets import QApplication, QMessageBox

from modules.camera import CameraWindow, FiducialValidationDialog
from core.stage_camera_transform import StageCameraTransform
from core.stage_camera_calibration import display_fraction_to_sensor_px, SENSOR_WIDTH_PX, SENSOR_HEIGHT_PX


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture
def calibrated_transform(tmp_path):
    t = StageCameraTransform("test_rig_fiducial_dialog", base_dir=tmp_path)
    t.calibrate_axis_from_step(1, 1.0, 0.0, 100.0)
    t.calibrate_axis_from_step(2, 1.0, 100.0, 0.0)
    return t


def _make_frame(w=200, h=150):
    return (np.random.default_rng(0).normal(30, 4, size=(h, w, 3))).clip(0, 255).astype(np.uint8)


# ── FiducialValidationDialog ─────────────────────────────────────────────

def test_compute_requires_two_points(app, calibrated_transform):
    dlg = FiducialValidationDialog(_make_frame(), calibrated_transform, parent=None)
    dlg._pts = [(50.0, 50.0)]  # solo 1 punto
    warned = {"n": 0}
    import PyQt6.QtWidgets as qtw
    orig = qtw.QMessageBox.warning
    qtw.QMessageBox.warning = staticmethod(lambda *a, **k: warned.__setitem__("n", warned["n"] + 1))
    try:
        dlg._on_compute()
    finally:
        qtw.QMessageBox.warning = orig
    assert warned["n"] == 1
    assert dlg._btn_record.isEnabled() is False


def test_compute_consistent_data_shows_low_discrepancy_and_enables_record(app, calibrated_transform):
    frame = _make_frame(w=200, h=150)
    dlg = FiducialValidationDialog(frame, calibrated_transform, parent=None)

    H, W = frame.shape[:2]
    pt1_frac = (0.5, 0.5)
    u1, v1 = display_fraction_to_sensor_px(*pt1_frac)
    target_u, target_v = u1 + 100.0, v1
    pt2_frac = (target_v / SENSOR_HEIGHT_PX, target_u / SENSOR_WIDTH_PX)

    dlg._pts = [(pt1_frac[0] * W, pt1_frac[1] * H), (pt2_frac[0] * W, pt2_frac[1] * H)]
    dlg._dx_printed_edit.setText("0.0")
    dlg._dy_printed_edit.setText("1.0")

    dlg._on_compute()

    assert dlg._last_result is not None
    assert dlg._last_result["discrepancy_vs_printed_pct"] == pytest.approx(0.0, abs=1.0)
    assert dlg._btn_record.isEnabled() is True
    assert "✅" in dlg._result_lbl.text()


def test_compute_large_discrepancy_flags_warning_icon(app, calibrated_transform):
    frame = _make_frame()
    dlg = FiducialValidationDialog(frame, calibrated_transform, parent=None)
    H, W = frame.shape[:2]
    pt1_frac = (0.5, 0.5)
    u1, v1 = display_fraction_to_sensor_px(*pt1_frac)
    pt2_frac = ((v1) / SENSOR_HEIGHT_PX, (u1 + 100.0) / SENSOR_WIDTH_PX)
    dlg._pts = [(pt1_frac[0] * W, pt1_frac[1] * H), (pt2_frac[0] * W, pt2_frac[1] * H)]
    dlg._dx_printed_edit.setText("0.0")
    dlg._dy_printed_edit.setText("5.0")  # muy distinto de lo que predice la calibración

    dlg._on_compute()

    assert dlg._last_result["discrepancy_vs_printed_pct"] > 50.0
    assert "⚠️" in dlg._result_lbl.text()


def test_record_persists_validation_on_transform(app, calibrated_transform, tmp_path, monkeypatch):
    # QMessageBox.information() es modal — bajo QT_QPA_PLATFORM=offscreen se queda
    # esperando un click que nunca llega y cuelga el test si no se mockea.
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)

    frame = _make_frame()
    dlg = FiducialValidationDialog(frame, calibrated_transform, parent=None)
    H, W = frame.shape[:2]
    pt1_frac = (0.5, 0.5)
    u1, v1 = display_fraction_to_sensor_px(*pt1_frac)
    pt2_frac = (v1 / SENSOR_HEIGHT_PX, (u1 + 100.0) / SENSOR_WIDTH_PX)
    dlg._pts = [(pt1_frac[0] * W, pt1_frac[1] * H), (pt2_frac[0] * W, pt2_frac[1] * H)]
    dlg._dx_printed_edit.setText("0.0")
    dlg._dy_printed_edit.setText("1.0")
    dlg._on_compute()

    dlg._on_record()

    assert calibrated_transform.last_fiducial_validation is not None
    reloaded = StageCameraTransform("test_rig_fiducial_dialog", base_dir=tmp_path)
    assert reloaded.last_fiducial_validation is not None


def test_record_does_not_modify_matrix(app, calibrated_transform, monkeypatch):
    """La corroboración es de solo lectura respecto de la matriz — ver nota de diseño
    #3 de core/stage_camera_calibration.py."""
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)

    frame = _make_frame()
    dlg = FiducialValidationDialog(frame, calibrated_transform, parent=None)
    M_before = calibrated_transform.M_forward.copy()
    H, W = frame.shape[:2]
    dlg._pts = [(50.0, 50.0), (150.0, 50.0)]
    dlg._dx_printed_edit.setText("1.0")
    dlg._dy_printed_edit.setText("1.0")
    dlg._on_compute()
    dlg._on_record()
    np.testing.assert_array_equal(calibrated_transform.M_forward, M_before)


# ── CameraWindow._open_fiducial_validation ───────────────────────────────

def test_open_fiducial_validation_blocks_without_frame(app, monkeypatch):
    win = CameraWindow()
    win._current_frame = None
    warned = {"n": 0}
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warned.__setitem__("n", warned["n"] + 1))
    win._open_fiducial_validation()
    assert warned["n"] == 1
    win.close()


def test_open_fiducial_validation_blocks_when_not_1x(app, monkeypatch):
    win = CameraWindow()
    win._current_frame = _make_frame()
    win._canon_zoom_idx = 1  # 5x
    warned = {"n": 0}
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warned.__setitem__("n", warned["n"] + 1))
    win._open_fiducial_validation()
    assert warned["n"] == 1
    win.close()


def test_open_fiducial_validation_emits_full_frame_ignoring_roi(app):
    """Regresión directa del bug detectado durante la implementación: a diferencia de
    _open_set_scale, este método NO debe recortar por ROI — el frame emitido debe
    conservar las dimensiones completas del Live View para que las fracciones de clic
    sigan siendo válidas en display_fraction_to_sensor_px()."""
    win = CameraWindow()
    full_frame = _make_frame(w=200, h=150)
    win._current_frame = full_frame
    win._overlay.set_roi((0.2, 0.2, 0.6, 0.6))  # ROI activo, no debe afectar el emit

    received = {}
    win.openFiducialValidationSignal.connect(lambda f: received.update(frame=f))
    win._open_fiducial_validation()

    assert "frame" in received
    assert received["frame"].shape == full_frame.shape
    win.close()
