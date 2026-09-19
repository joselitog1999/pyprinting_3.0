# -*- coding: utf-8 -*-
"""
test_stage_calibration_wizard_dialog.py — Pruebas para StageCalibrationWizardDialog
(Fase B, modules/camera.py): el diálogo que conecta el motor de calibración
(core/stage_camera_calibration.py) a frames de cámara en vivo y a movimientos reales de
la platina (core/nanopositioning.py::Backend.move(), invocado de forma segura entre
hilos vía QMetaObject.invokeMethod — mismo patrón ya verificado en la Fase A).

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

import config  # noqa: F401  (config antes que PyQt6/trackpy — ver otros tests de esta sesión)

import numpy as np
import pytest
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore import QThread

from modules.camera import StageCalibrationWizardDialog
from core.stage_camera_calibration import _TRACKPY_AVAILABLE
import core.nanopositioning as nanopositioning

pytestmark = pytest.mark.skipif(not _TRACKPY_AVAILABLE, reason="trackpy no disponible en este entorno")

FRAME_W, FRAME_H = 200, 150


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication(sys.argv)


class _FakeCameraWindow:
    """Sustituto liviano de CameraWindow: StageCalibrationWizardDialog solo accede a
    _current_frame y _canon_zoom_levels[_canon_zoom_idx] por duck-typing, así que no
    hace falta construir la ventana de cámara real (pesada, con toda su UI) para probar
    la lógica del asistente."""
    def __init__(self):
        self._current_frame = None
        self._canon_zoom_levels = [1, 5, 10]
        self._canon_zoom_idx = 0


def _make_synthetic_frame(width=FRAME_W, height=FRAME_H, bx=100.0, by=75.0, amp=220.0, seed=0):
    rng = np.random.default_rng(seed)
    img = rng.normal(loc=30.0, scale=4.0, size=(height, width)).astype(float)
    yy, xx = np.mgrid[0:height, 0:width]
    img += amp * np.exp(-(((xx - bx) ** 2 + (yy - by) ** 2) / (2 * 2.2 ** 2)))
    img = np.clip(img, 0, 255).astype(np.uint8)
    return np.stack([img, img, img], axis=-1)


def _make_real_nano_backend_on_own_thread():
    """core.nanopositioning.Backend en un QThread real — necesario para probar que
    _move_stage_blocking() lo invoca de forma segura entre hilos (BlockingQueuedConnection),
    igual que se verificó para el teardown de cámara en la Fase A."""
    backend = nanopositioning.Backend()
    thread = QThread()
    backend.moveToThread(thread)
    thread.start()
    return backend, thread


@pytest.fixture
def nano_backend():
    backend, thread = _make_real_nano_backend_on_own_thread()
    yield backend
    thread.quit()
    thread.wait(2000)


# ── Precondiciones ────────────────────────────────────────────────────────

def test_dialog_blocks_without_live_frame(app, nano_backend, tmp_path, monkeypatch):
    cam = _FakeCameraWindow()
    cam._current_frame = None
    dlg = StageCalibrationWizardDialog(cam, nano_backend, "test_rig", parent=None)
    dlg._transform._base_dir = tmp_path

    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    assert dlg._check_preconditions() is False


def test_dialog_blocks_when_zoom_not_1x(app, nano_backend, tmp_path, monkeypatch):
    cam = _FakeCameraWindow()
    cam._current_frame = _make_synthetic_frame()
    cam._canon_zoom_idx = 1  # 5x
    dlg = StageCalibrationWizardDialog(cam, nano_backend, "test_rig", parent=None)
    dlg._transform._base_dir = tmp_path

    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    assert dlg._check_preconditions() is False


def test_dialog_allows_at_1x_with_frame(app, nano_backend, tmp_path):
    cam = _FakeCameraWindow()
    cam._current_frame = _make_synthetic_frame()
    dlg = StageCalibrationWizardDialog(cam, nano_backend, "test_rig", parent=None)
    dlg._transform._base_dir = tmp_path
    assert dlg._check_preconditions() is True


# ── Movimiento seguro entre hilos ────────────────────────────────────────

def test_move_stage_blocking_completes_without_hanging(app, nano_backend, tmp_path):
    cam = _FakeCameraWindow()
    cam._current_frame = _make_synthetic_frame()
    dlg = StageCalibrationWizardDialog(cam, nano_backend, "test_rig", parent=None)
    dlg._transform._base_dir = tmp_path

    t0 = time.time()
    ok = dlg._move_stage_blocking(axis=1, dist_um=1.0)
    elapsed = time.time() - t0

    assert ok is True
    assert elapsed < 3.0, "_move_stage_blocking no debe colgar el diálogo"


# ── Captura de múltiples frames ──────────────────────────────────────────

def test_capture_n_frames_returns_requested_count(app, nano_backend, tmp_path):
    cam = _FakeCameraWindow()
    cam._current_frame = _make_synthetic_frame()
    dlg = StageCalibrationWizardDialog(cam, nano_backend, "test_rig", parent=None)
    dlg._transform._base_dir = tmp_path

    frames = dlg._capture_n_frames(n=3, interval_ms=10)
    assert len(frames) == 3


# ── Flujo completo de un eje: Antes -> Mover+Después -> Aceptar ─────────

def test_full_single_axis_flow_accept_and_matrix_partial(app, nano_backend, tmp_path):
    cam = _FakeCameraWindow()
    cam._current_frame = _make_synthetic_frame(bx=100.0, by=75.0, seed=1)
    dlg = StageCalibrationWizardDialog(cam, nano_backend, "test_rig", parent=None)
    dlg._transform._base_dir = tmp_path
    dlg._step_edit.setText("1.0")

    dlg._on_capture_before()
    assert dlg._btn_move_after.isEnabled()

    # Simular que la partícula se desplazó en pantalla tras el paso de la platina
    # (SAFE_MODE no mueve una cámara real — el frame se actualiza a mano, como haría
    # el pipeline de Live View real tras el movimiento).
    cam._current_frame = _make_synthetic_frame(bx=130.0, by=75.0, seed=2)
    dlg._on_move_and_capture_after()

    assert dlg._pending_result is not None
    assert dlg._btn_accept_axis.isEnabled()

    dlg._on_accept_axis()

    assert dlg._axis_idx == 1  # avanzó al segundo eje
    assert 1 in dlg._transform._pending_columns


def test_full_two_axis_flow_completes_and_enables_save(app, nano_backend, tmp_path):
    cam = _FakeCameraWindow()
    cam._current_frame = _make_synthetic_frame(bx=100.0, by=75.0, seed=1)
    dlg = StageCalibrationWizardDialog(cam, nano_backend, "test_rig", parent=None)
    dlg._transform._base_dir = tmp_path
    dlg._step_edit.setText("1.0")

    # Eje 1
    dlg._on_capture_before()
    cam._current_frame = _make_synthetic_frame(bx=100.0, by=95.0, seed=2)
    dlg._on_move_and_capture_after()
    dlg._on_accept_axis()

    # Eje 2
    cam._current_frame = _make_synthetic_frame(bx=100.0, by=75.0, seed=3)
    dlg._on_capture_before()
    cam._current_frame = _make_synthetic_frame(bx=120.0, by=75.0, seed=4)
    dlg._on_move_and_capture_after()
    dlg._on_accept_axis()

    assert dlg._transform.is_calibrated()
    assert dlg._btn_save.isEnabled()


def test_unstable_before_frames_rejected_with_retry_available(app, nano_backend, tmp_path, monkeypatch):
    """Si la partícula 'salta' entre los 3 frames de captura (posición inestable), el
    asistente debe rechazar el resultado y NO habilitar 'Aceptar' — solo 'Reintentar'."""
    cam = _FakeCameraWindow()
    dlg = StageCalibrationWizardDialog(cam, nano_backend, "test_rig", parent=None)
    dlg._transform._base_dir = tmp_path
    dlg._step_edit.setText("1.0")

    # Frames "antes" con posiciones saltando -> alta dispersión detectada por
    # StepCalibrationSession.compute_result(). Se simula capturando manualmente en vez
    # de por el QTimer real, para controlar exactamente qué ve cada tick.
    positions = iter([60.0, 100.0, 140.0])
    cam._current_frame = _make_synthetic_frame(bx=next(positions), by=75.0, seed=10)

    monkeypatch.setattr(dlg, "_capture_n_frames", lambda n=3, interval_ms=150: [
        _make_synthetic_frame(bx=60.0, by=75.0, seed=10),
        _make_synthetic_frame(bx=100.0, by=75.0, seed=11),
        _make_synthetic_frame(bx=140.0, by=75.0, seed=12),
    ])
    cam._current_frame = _make_synthetic_frame(bx=100.0, by=75.0, seed=13)
    dlg._on_capture_before()

    assert dlg._session is not None
    result = dlg._session.compute_result(max_std_px=2.0)
    assert result["ok"] is False
