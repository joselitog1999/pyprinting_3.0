# -*- coding: utf-8 -*-
"""
test_camera_overlays_projection.py — Pruebas para la Fase D: overlays Confocal ->
Cámara e Impresión -> Cámara (caja de escaneo confocal proyectada + grilla de
impresión proyectada), cacheados y generalizados a cualquier nivel de zoom de
hardware Canon (a diferencia de ROI -> Confocal / calibración, restringidos a 1x).

Cubre:
1. core/stage_camera_calibration.py::sensor_px_to_display_fraction() — inversa de
   display_fraction_to_sensor_px() a 1x, geometría de recorte a 5x/10x verificada
   contra la fórmula ya validada de core/canon_edsdk.py::_apply_zoom_position_from_center(),
   y el caso "punto fuera del recorte actual -> None".
2. modules/camera.py::OverlayWidget — nuevos setters/toggles (set_confocal_box,
   set_printing_grid_points, toggle_confocal_box_visible, toggle_printing_grid_visible).
3. modules/camera.py::CameraWindow — _stage_um_to_display_frac, los 4 slots públicos
   (update_confocal_center/update_confocal_range/update_printing_reference/
   set_printing_grid) y su lógica de recómputo (todo-o-nada para la caja confocal,
   descarte silencioso de puntos fuera de vista para la grilla de impresión),
   además de que "Limpiar Todo" invalida ambas cachés.

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

from core.stage_camera_calibration import (display_fraction_to_sensor_px,
                                            sensor_px_to_display_fraction,
                                            SENSOR_WIDTH_PX, SENSOR_HEIGHT_PX)
from core.stage_camera_transform import StageCameraTransform
from modules.camera import CameraWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture
def calibrated_transform(tmp_path):
    t = StageCameraTransform("test_rig_overlays", base_dir=tmp_path)
    t.calibrate_axis_from_step(1, 1.0, 0.0, 100.0)   # eje 1 -> +100 sensor_v por µm
    t.calibrate_axis_from_step(2, 1.0, 100.0, 0.0)   # eje 2 -> +100 sensor_u por µm
    return t


# ── sensor_px_to_display_fraction ────────────────────────────────────────────

def test_sensor_px_to_display_fraction_1x_is_inverse_of_display_to_sensor():
    for fx, fy in [(0.5, 0.5), (0.1, 0.9), (0.0, 0.0), (1.0, 1.0), (0.37, 0.62)]:
        u, v = display_fraction_to_sensor_px(fx, fy)
        out = sensor_px_to_display_fraction(u, v, zoom_level=1, zoom_center_frac=(0.5, 0.5))
        assert out is not None
        assert out[0] == pytest.approx(fx, abs=1e-9)
        assert out[1] == pytest.approx(fy, abs=1e-9)


def test_sensor_px_to_display_fraction_5x_matches_canon_edsdk_crop_geometry():
    """Replica a mano la fórmula ya validada de
    core/canon_edsdk.py::_apply_zoom_position_from_center() (mismo z_factor=5.0,
    mismo mapeo Display Y -> Sensor X / Display X -> Sensor Y, mismo clamping) y
    verifica que el punto físico exactamente en el centro del recorte cae en el
    centro de la pantalla (0.5, 0.5)."""
    cx, cy = 0.4, 0.7  # centro de zoom en fracción de pantalla
    z_factor = 5.0
    win_w = SENSOR_WIDTH_PX / z_factor
    win_h = SENSOR_HEIGHT_PX / z_factor
    center_sensor_x = cy * SENSOR_WIDTH_PX
    center_sensor_y = cx * SENSOR_HEIGHT_PX
    ul_x = max(0.0, min(SENSOR_WIDTH_PX - win_w, center_sensor_x - win_w / 2.0))
    ul_y = max(0.0, min(SENSOR_HEIGHT_PX - win_h, center_sensor_y - win_h / 2.0))

    # El propio centro del recorte debe proyectar a (0.5, 0.5) en pantalla.
    u_center = ul_x + win_w / 2.0
    v_center = ul_y + win_h / 2.0
    out = sensor_px_to_display_fraction(u_center, v_center, zoom_level=5, zoom_center_frac=(cx, cy))
    assert out is not None
    assert out[0] == pytest.approx(0.5, abs=1e-6)
    assert out[1] == pytest.approx(0.5, abs=1e-6)

    # Una esquina exacta de la ventana de recorte debe caer en un extremo (0 o 1).
    out_corner = sensor_px_to_display_fraction(ul_x, ul_y, zoom_level=5, zoom_center_frac=(cx, cy))
    assert out_corner is not None
    assert out_corner[0] == pytest.approx(0.0, abs=1e-6)
    assert out_corner[1] == pytest.approx(0.0, abs=1e-6)


def test_sensor_px_to_display_fraction_out_of_crop_returns_none():
    # A 10x, centrado en (0.5, 0.5), un punto muy lejano del sensor queda fuera del recorte.
    out = sensor_px_to_display_fraction(0.0, 0.0, zoom_level=10, zoom_center_frac=(0.5, 0.5))
    assert out is None


def test_sensor_px_to_display_fraction_1x_ignores_zoom_center():
    # A 1x el recorte es el sensor completo, cy/cx (zoom_center_frac) no debe influir.
    out_a = sensor_px_to_display_fraction(2000.0, 1500.0, zoom_level=1, zoom_center_frac=(0.1, 0.1))
    out_b = sensor_px_to_display_fraction(2000.0, 1500.0, zoom_level=1, zoom_center_frac=(0.9, 0.9))
    assert out_a == pytest.approx(out_b)


# ── OverlayWidget: setters / toggles ─────────────────────────────────────────

def test_overlay_confocal_box_setter_and_toggle(app):
    win = CameraWindow()
    ov = win._overlay
    assert ov._confocal_box_pts is None
    assert ov._show_confocal_box is True

    ov.set_confocal_box([(0.1, 0.1), (0.9, 0.1), (0.9, 0.9), (0.1, 0.9)])
    assert ov._confocal_box_pts is not None and len(ov._confocal_box_pts) == 4

    visible = ov.toggle_confocal_box_visible()
    assert visible is False
    assert ov._show_confocal_box is False
    ov.toggle_confocal_box_visible()
    assert ov._show_confocal_box is True
    win.close()


def test_overlay_printing_grid_setter_and_toggle(app):
    win = CameraWindow()
    ov = win._overlay
    assert ov._printing_grid_pts is None

    ov.set_printing_grid_points([(0.2, 0.3), (0.5, 0.5)])
    assert ov._printing_grid_pts == [(0.2, 0.3), (0.5, 0.5)]

    visible = ov.toggle_printing_grid_visible()
    assert visible is False
    win.close()


# ── CameraWindow._stage_um_to_display_frac ───────────────────────────────────

def test_stage_um_to_display_frac_none_without_reference(app, calibrated_transform):
    win = CameraWindow()
    win._ref_set = False
    win.set_stage_camera_transform(calibrated_transform)
    assert win._stage_um_to_display_frac(50.0, 50.0) is None
    win.close()


def test_stage_um_to_display_frac_none_without_calibration(app):
    win = CameraWindow()
    win._ref_set = True
    win._ref_frac = (0.5, 0.5)
    win._ref_pos_um = (50.0, 50.0)
    win._stage_transform = None
    assert win._stage_um_to_display_frac(50.0, 50.0) is None
    win.close()


def test_stage_um_to_display_frac_at_reference_returns_reference_frac(app, calibrated_transform):
    win = CameraWindow()
    win._ref_set = True
    win._ref_frac = (0.5, 0.5)
    win._ref_pos_um = (50.0, 50.0)
    win.set_stage_camera_transform(calibrated_transform)
    frac = win._stage_um_to_display_frac(50.0, 50.0)
    assert frac == pytest.approx((0.5, 0.5), abs=1e-6)
    win.close()


# ── CameraWindow: caja confocal (todo o nada) ────────────────────────────────

def test_recompute_confocal_box_draws_when_fully_in_view(app, calibrated_transform):
    win = CameraWindow()
    win._ref_set = True
    win._ref_frac = (0.5, 0.5)
    win._ref_pos_um = (50.0, 50.0)
    win.set_stage_camera_transform(calibrated_transform)

    win.update_confocal_center([50.0, 50.0, 0.0])
    win.update_confocal_range([1.0, 1.0, 20, 20])  # 1 µm de rango, muy chico, bien adentro del FOV

    assert win._overlay._confocal_box_pts is not None
    assert len(win._overlay._confocal_box_pts) == 4
    win.close()


def test_recompute_confocal_box_all_or_nothing_when_partially_out_of_view(app, calibrated_transform):
    """Si CUALQUIER esquina cae fuera del frame actual, no debe dibujarse nada (decisión
    de diseño de la Ronda 1: un cuadrilátero parcial confundiría al operador)."""
    win = CameraWindow()
    win._ref_set = True
    win._ref_frac = (0.5, 0.5)
    win._ref_pos_um = (50.0, 50.0)
    win.set_stage_camera_transform(calibrated_transform)

    win.update_confocal_center([50.0, 50.0, 0.0])
    # Rango enorme: la calibración usada (100 sensor-px/µm) hace que un rango de
    # varios µm ya exceda ampliamente medio sensor completo (4752/2=2376 px @ 1x).
    win.update_confocal_range([80.0, 80.0, 20, 20])

    assert win._overlay._confocal_box_pts is None
    win.close()


def test_recompute_confocal_box_none_until_both_center_and_range_known(app, calibrated_transform):
    win = CameraWindow()
    win._ref_set = True
    win._ref_frac = (0.5, 0.5)
    win._ref_pos_um = (50.0, 50.0)
    win.set_stage_camera_transform(calibrated_transform)

    win.update_confocal_range([1.0, 1.0, 20, 20])
    assert win._overlay._confocal_box_pts is None  # falta el centro
    win.close()


# ── CameraWindow: grilla de impresión (descarte parcial) ─────────────────────

def test_recompute_printing_grid_drops_out_of_view_points_keeps_visible(app, calibrated_transform):
    win = CameraWindow()
    win._ref_set = True
    win._ref_frac = (0.5, 0.5)
    win._ref_pos_um = (50.0, 50.0)
    win.set_stage_camera_transform(calibrated_transform)

    win.update_printing_reference([50.0, 50.0, 0.0])
    # offsets relativos: (0,0) queda en la referencia (visible), otro muy lejos del FOV.
    datos = np.array([[0.0, 500.0], [0.0, 500.0]])
    win.set_printing_grid(datos)

    pts = win._overlay._printing_grid_pts
    assert pts is not None
    assert len(pts) == 1
    assert pts[0] == pytest.approx((0.5, 0.5), abs=1e-6)
    win.close()


def test_recompute_printing_grid_none_until_both_reference_and_grid_known(app, calibrated_transform):
    win = CameraWindow()
    win._ref_set = True
    win._ref_frac = (0.5, 0.5)
    win._ref_pos_um = (50.0, 50.0)
    win.set_stage_camera_transform(calibrated_transform)

    datos = np.array([[0.0], [0.0]])
    win.set_printing_grid(datos)
    assert win._overlay._printing_grid_pts is None  # falta la referencia de impresión
    win.close()


def test_update_printing_reference_handles_nan_clear(app, calibrated_transform):
    win = CameraWindow()
    win._ref_set = True
    win._ref_frac = (0.5, 0.5)
    win._ref_pos_um = (50.0, 50.0)
    win.set_stage_camera_transform(calibrated_transform)

    win.update_printing_reference([50.0, 50.0, 0.0])
    datos = np.array([[0.0], [0.0]])
    win.set_printing_grid(datos)
    assert win._overlay._printing_grid_pts is not None

    win.update_printing_reference(["NaN", "NaN", "NaN"])
    assert win._printing_ref_xy is None
    assert win._overlay._printing_grid_pts is None
    win.close()


# ── "Limpiar Todo" invalida ambas cachés ─────────────────────────────────────

def test_global_clear_resets_confocal_and_printing_overlays(app, monkeypatch, calibrated_transform):
    win = CameraWindow()
    win._ref_set = True
    win._ref_frac = (0.5, 0.5)
    win._ref_pos_um = (50.0, 50.0)
    win.set_stage_camera_transform(calibrated_transform)

    win.update_confocal_center([50.0, 50.0, 0.0])
    win.update_confocal_range([1.0, 1.0, 20, 20])
    win.update_printing_reference([50.0, 50.0, 0.0])
    win.set_printing_grid(np.array([[0.0], [0.0]]))
    assert win._overlay._confocal_box_pts is not None
    assert win._overlay._printing_grid_pts is not None

    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    win._global_clear_with_confirm()

    assert win._overlay._confocal_box_pts is None
    assert win._overlay._printing_grid_pts is None
    assert win._last_stage_xy is None
    assert win._last_confocal_range is None
    assert win._printing_ref_xy is None
    assert win._printing_grid_datos is None
    win.close()


# ── Cambios de zoom/pan disparan recómputo ───────────────────────────────────

def test_pan_canon_triggers_overlay_recompute(app, calibrated_transform):
    win = CameraWindow()
    win._ref_set = True
    win._ref_frac = (0.5, 0.5)
    win._ref_pos_um = (50.0, 50.0)
    win.set_stage_camera_transform(calibrated_transform)
    win.update_confocal_center([50.0, 50.0, 0.0])
    win.update_confocal_range([1.0, 1.0, 20, 20])
    assert win._overlay._confocal_box_pts is not None

    calls = {"n": 0}
    orig = win._recompute_confocal_box
    def spy():
        calls["n"] += 1
        return orig()
    win._recompute_confocal_box = spy

    win._pan_canon(1, 0)
    assert calls["n"] == 1
    win.close()
