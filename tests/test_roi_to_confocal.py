# -*- coding: utf-8 -*-
"""
test_roi_to_confocal.py — Pruebas para la Fase C: Cámara -> Confocal usando
StageCameraTransform en vez de la fórmula ad-hoc anterior.

Cubre:
1. modules/confocal.py::Frontend.set_ramp_parameters_from_external() — refleja los
   valores en los campos visibles, fuerza modo Ramp, emite parametersrampSignal una
   sola vez (no una vez por campo).
2. modules/camera.py::CameraWindow._send_roi_to_confocal() — precondiciones (sin
   referencia, sin ROI, zoom != 1x, sin calibración), el cómputo geométrico completo
   contra una calibración conocida (bounding box de las 4 esquinas del ROI, no solo
   una diagonal), el chequeo de límites físicos, y que roiToConfocalSignal ahora lleve
   el centro objetivo (el bug que encontró el panel de la Ronda 1 — antes la señal
   nunca lo llevaba y quedaba completamente sin conectar en todo el repo).

PyPrinting 3.0 — UNSAM Nanofotónica
"""
import os
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["PYPRINTING_SAFE"] = "1"

import config  # noqa: F401

import pytest
from PyQt6.QtWidgets import QApplication, QMessageBox, QInputDialog
from PyQt6.QtCore import QThread

import modules.confocal as confocal_mod
from modules.camera import CameraWindow
from core.stage_camera_transform import StageCameraTransform
import core.nanopositioning as nanopositioning
from app import move_stage_to_absolute_xy


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture
def calibrated_transform(tmp_path):
    t = StageCameraTransform("test_rig_roi2confocal", base_dir=tmp_path)
    t.calibrate_axis_from_step(1, 1.0, 0.0, 100.0)
    t.calibrate_axis_from_step(2, 1.0, 100.0, 0.0)
    return t


# ── Frontend.set_ramp_parameters_from_external ──────────────────────────────

def test_set_ramp_parameters_from_external_updates_fields_and_forces_ramp(app):
    fe = confocal_mod.Frontend()
    fe.scan_mode.setCurrentText(confocal_mod.SCAN_MODES[1])  # Step, a propósito

    emits = []
    fe.parametersrampSignal.connect(lambda p: emits.append(p))

    fe.set_ramp_parameters_from_external(6.336, 9.504, 127, 190)

    assert fe.scan_mode.currentText() == confocal_mod.SCAN_MODES[0]
    assert fe.scanrangeEdit.text() == "6.336"
    assert fe.scanrangeEdit_y.text() == "9.504"
    assert fe.NxEdit.text() == "127"
    assert fe.NyEdit.text() == "190"
    assert len(emits) == 1, "Debe emitir parametersrampSignal una sola vez, no una vez por campo"
    assert emits[0] == [6.336, 9.504, 127, 190]


# ── CameraWindow._send_roi_to_confocal — precondiciones ─────────────────────

def test_send_roi_blocks_without_reference(app, monkeypatch):
    win = CameraWindow()
    win._ref_set = False
    warned = {"n": 0}
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warned.__setitem__("n", warned["n"] + 1))
    win._send_roi_to_confocal()
    assert warned["n"] == 1
    win.close()


def test_send_roi_blocks_without_roi(app, monkeypatch):
    win = CameraWindow()
    win._ref_set = True
    win._overlay.clear_roi()
    warned = {"n": 0}
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warned.__setitem__("n", warned["n"] + 1))
    win._send_roi_to_confocal()
    assert warned["n"] == 1
    win.close()


def test_send_roi_blocks_when_not_1x(app, monkeypatch, calibrated_transform):
    win = CameraWindow()
    win._ref_set = True
    win._overlay.set_roi((0.4, 0.4, 0.6, 0.6))
    win._canon_zoom_idx = 1  # 5x
    win.set_stage_camera_transform(calibrated_transform)
    warned = {"n": 0}
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warned.__setitem__("n", warned["n"] + 1))
    win._send_roi_to_confocal()
    assert warned["n"] == 1
    win.close()


def test_send_roi_blocks_without_calibration(app, monkeypatch):
    win = CameraWindow()
    win._ref_set = True
    win._overlay.set_roi((0.4, 0.4, 0.6, 0.6))
    win._stage_transform = None
    warned = {"n": 0}
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warned.__setitem__("n", warned["n"] + 1))
    win._send_roi_to_confocal()
    assert warned["n"] == 1
    win.close()


# ── CameraWindow._send_roi_to_confocal — cómputo geométrico completo ────────

def test_send_roi_computes_expected_center_and_range(app, monkeypatch, calibrated_transform):
    win = CameraWindow()
    win._ref_set = True
    win._ref_frac = (0.5, 0.5)
    win._ref_pos_um = (50.0, 50.0)
    win._overlay.set_roi((0.4, 0.4, 0.6, 0.6))  # simétrico alrededor de la referencia
    win.set_stage_camera_transform(calibrated_transform)

    monkeypatch.setattr(QInputDialog, "getDouble", staticmethod(lambda *a, **k: (50.0, True)))

    received = {}
    win.roiToConfocalSignal.connect(
        lambda rx, ry, px, py, tx, ty: received.update(
            range_x=rx, range_y=ry, px_x=px, px_y=py, target_x=tx, target_y=ty))

    win._send_roi_to_confocal()

    assert received, "roiToConfocalSignal debe emitirse"
    assert received["target_x"] == pytest.approx(50.0, abs=1e-2)
    assert received["target_y"] == pytest.approx(50.0, abs=1e-2)
    assert received["range_x"] == pytest.approx(6.336, abs=1e-2)
    assert received["range_y"] == pytest.approx(9.504, abs=1e-2)
    # pixels = round(range_um * 1000 / res_nm), res_nm=50.0
    assert received["px_x"] == pytest.approx(round(6.336 * 1000 / 50.0), abs=1)
    assert received["px_y"] == pytest.approx(round(9.504 * 1000 / 50.0), abs=1)
    win.close()


def test_send_roi_off_center_reference_shifts_target(app, monkeypatch, calibrated_transform):
    """Si el ROI no está centrado en la referencia, el centro objetivo debe desplazarse
    en la dirección física correcta, no quedarse fijo en la posición de referencia.
    display_fraction_to_sensor_px mapea fy (pantalla, vertical) -> sensor_x=u, y esta
    calibración (calibrate_axis_from_step(2, ..., du=100, dv=0)) hace que u responda al
    eje físico 2 — no al eje 1 — así que un ROI desplazado en +fy debe mover target_y
    (eje 2), dejando target_x (eje 1) sin cambios. Confirmado también por el propio
    print de diagnóstico de _send_roi_to_confocal en la primera corrida de este test."""
    win = CameraWindow()
    win._ref_set = True
    win._ref_frac = (0.5, 0.5)
    win._ref_pos_um = (50.0, 50.0)
    win._overlay.set_roi((0.45, 0.55, 0.55, 0.75))  # desplazado hacia +fy respecto de la referencia
    win.set_stage_camera_transform(calibrated_transform)
    monkeypatch.setattr(QInputDialog, "getDouble", staticmethod(lambda *a, **k: (50.0, True)))

    received = {}
    win.roiToConfocalSignal.connect(
        lambda rx, ry, px, py, tx, ty: received.update(target_x=tx, target_y=ty))
    win._send_roi_to_confocal()

    assert received["target_x"] == pytest.approx(50.0, abs=1e-6), \
        "Un ROI desplazado solo en fy no debe mover el eje físico 1 (responde a fx, no a fy)"
    assert received["target_y"] > 50.0, "Un ROI desplazado en +fy debe mover el centro objetivo en +eje2"
    win.close()


def test_send_roi_out_of_bounds_blocked(app, monkeypatch, calibrated_transform):
    win = CameraWindow()
    win._ref_set = True
    win._ref_frac = (0.5, 0.5)
    win._ref_pos_um = (1.0, 1.0)  # cerca del límite inferior [0, 100] µm
    win._overlay.set_roi((0.0, 0.0, 1.0, 1.0))  # ROI enorme -> excede el rango físico
    win.set_stage_camera_transform(calibrated_transform)

    warned = {"n": 0}
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warned.__setitem__("n", warned["n"] + 1))
    emitted = {"n": 0}
    win.roiToConfocalSignal.connect(lambda *a: emitted.__setitem__("n", emitted["n"] + 1))

    win._send_roi_to_confocal()

    assert warned["n"] == 1
    assert emitted["n"] == 0, "No debe emitir la señal si el escaneo excede los límites físicos"
    win.close()


# ── app.py::move_stage_to_absolute_xy ────────────────────────────────────────

def test_move_stage_to_absolute_xy_completes_without_hanging(app):
    backend = nanopositioning.Backend()
    thread = QThread()
    backend.moveToThread(thread)
    thread.start()
    try:
        t0 = time.time()
        ok = move_stage_to_absolute_xy(backend, 60.0, 40.0)
        elapsed = time.time() - t0

        assert ok is True
        assert elapsed < 3.0, "move_stage_to_absolute_xy no debe colgar el hilo llamante"
    finally:
        thread.quit()
        thread.wait(2000)


def test_move_stage_to_absolute_xy_reaches_target_position(app):
    """En SAFE_MODE, _MockPI aplica el movimiento relativo a su posición interna
    inmediatamente — confirma que el delta calculado (target - actual) efectivamente
    deja la platina en el target, no en un desplazamiento fijo arbitrario."""
    backend = nanopositioning.Backend()
    thread = QThread()
    backend.moveToThread(thread)
    thread.start()
    try:
        from config import pi
        pi.MOV([1, 2], [10.0, 10.0])  # posición de partida conocida

        move_stage_to_absolute_xy(backend, 60.0, 40.0)

        pos = pi.qPOS()
        assert float(pos["1"]) == pytest.approx(60.0, abs=1e-2)
        assert float(pos["2"]) == pytest.approx(40.0, abs=1e-2)
    finally:
        thread.quit()
        thread.wait(2000)
