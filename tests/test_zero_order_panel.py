# -*- coding: utf-8 -*-
"""Espejo rápido en el panel izquierdo (paso 7, Ronda 3 §1.3-1.4, reconciliada en la Ronda 4).

- Un único control: el botón entra al orden cero desde primer orden y vuelve desde especular. `Ctrl+0`
  lo invoca y no se repite con la tecla sostenida (H-11a, H-11e).
- Sin diálogo: los pasos y, si falla, el estado de cada recurso quedan a la vista en el panel (H-12).
- En especular la ganancia EM queda bloqueada en 0 (el spinbox se deshabilita) y la insignia dice
  "ORDEN CERO · EM 0 bloqueada" (H-33, H-34).
- "Ir a λ" con un destino bajo el umbral pasa a "Ir (espejo rápido)" y entra por el mismo servicio (§3.3).
- Al volver, la ganancia no se restituye sola: aparece la pastilla "Restituir"; con un láser abierto pide
  confirmar el notch (R4-B-4, H-05).
- En estado desconocido no se mueve nada y se ofrece [Releer estado] (H-11c).
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYPRINTING_SAFE", "1")

import pytest
from PyQt6.QtWidgets import QApplication

from pyspectrum.drivers import specular_interlock as si
from pyspectrum.drivers.andor_ccd_driver import get_andor_ccd
from pyspectrum.drivers.shamrock_driver import (
    DEVICE, GRATING_150_LINES, GRATING_MIRROR, get_shamrock,
)
from pyspectrum.modules.hardware_session import hardware_session
from pyspectrum.ui.left_hardware_panel import LeftHardwarePanel

_app = QApplication.instance() or QApplication(["pytest"])


def _gain(cam):
    g = cam.get_emccd_gain()
    return g[1] if isinstance(g, tuple) else g


@pytest.fixture
def panel():
    hardware_session.clear_emergency()
    cam = get_andor_ccd(force_mock=True)
    spec = get_shamrock(force_mock=True)
    cam.abort_acquisition()
    cam.set_exposure_time(0.05)
    p = LeftHardwarePanel(cam, spec)
    p.spin_gain.setValue(150)
    p._on_gain_changed()
    assert _gain(cam) == 150
    yield p, cam, spec
    p._refresh_timer.stop()
    p.deleteLater()


def test_zero_order_button_enters_and_locks_the_gain(panel):
    p, cam, spec = panel
    p.btn_zero_order.click()
    assert si.get_interlock().mode == si.SPECULAR
    assert spec.ShamrockGetWavelength(DEVICE)[1] == pytest.approx(0.0)
    assert _gain(cam) == 0
    assert not p.spin_gain.isEnabled() and p.spin_gain.value() == 0
    assert "ORDEN CERO" in p.lbl_specular_state.text() and "EM 0 bloqueada" in p.lbl_specular_state.text()
    assert "Volver" in p.btn_zero_order.text()
    assert "✓" in p.lbl_zo_steps.text()


def test_second_click_returns_and_offers_the_gain_restore_pill(panel):
    p, cam, spec = panel
    p.btn_zero_order.click()
    p.btn_zero_order.click()
    assert si.get_interlock().mode == si.FIRST_ORDER
    assert spec.ShamrockGetWavelength(DEVICE)[1] == pytest.approx(532.0)
    assert _gain(cam) == 0                                   # no vuelve sola
    assert p.spin_gain.isEnabled()
    assert not p.btn_restore_gain.isHidden() and "150" in p.btn_restore_gain.text()
    p.btn_restore_gain.click()
    assert _gain(cam) == 150 and p.spin_gain.value() == 150
    assert p.btn_restore_gain.isHidden()


def test_restore_with_a_laser_open_needs_the_notch_confirmation(panel):
    p, cam, spec = panel
    p.btn_zero_order.click()
    p.zero_order._open_names = lambda: ["532"]
    p.btn_zero_order.click()
    assert not p.chk_notch.isHidden()
    p.btn_restore_gain.click()
    assert _gain(cam) == 0                                   # sin confirmar el notch, no restituye
    p.chk_notch.setChecked(True)
    p.btn_restore_gain.click()
    assert _gain(cam) == 150


def test_goto_below_threshold_goes_through_the_quick_mirror(panel):
    p, cam, spec = panel
    p.edit_wavelength.setValue(40.0)
    assert "ESPECULAR" in p.lbl_destination.text()
    assert "espejo rápido" in p.btn_goto_wavelength.text()
    p.btn_goto_wavelength.click()
    assert spec.ShamrockGetWavelength(DEVICE)[1] == pytest.approx(40.0)
    assert si.get_interlock().mode == si.SPECULAR and _gain(cam) == 0
    p.edit_wavelength.setValue(650.0)
    assert "primer orden" in p.lbl_destination.text() and "56.7" in p.lbl_destination.text()
    assert p.btn_goto_wavelength.text() == "➡️ Ir a λ"


def test_mirror_grating_from_the_combo_enters_through_the_service(panel):
    p, cam, spec = panel
    p.cmb_grating.setCurrentIndex(GRATING_MIRROR - 1)       # elegirla no mueve (paso 8, G-04)
    assert spec.ShamrockGetGrating(DEVICE)[1] != GRATING_MIRROR
    p.btn_goto_wavelength.click()
    assert spec.ShamrockGetGrating(DEVICE)[1] == GRATING_MIRROR
    assert si.get_interlock().mode == si.SPECULAR and _gain(cam) == 0


def test_gain_spin_cannot_raise_the_gain_in_specular(panel):
    p, cam, spec = panel
    p.btn_zero_order.click()
    p.spin_gain.setValue(80)
    p._on_gain_changed()
    assert _gain(cam) == 0 and p.spin_gain.value() == 0


def test_a_failed_step_is_shown_with_the_resource_state(panel, monkeypatch):
    p, cam, spec = panel
    monkeypatch.setattr(cam, "get_emccd_gain", lambda: 12)
    p.btn_zero_order.click()
    text = p.lbl_zo_steps.text()
    assert "✗" in text and "12" in text and "red: no se movió" in text
    assert spec.ShamrockGetWavelength(DEVICE)[1] == pytest.approx(532.0)


def test_unknown_state_offers_reread_and_does_not_move(panel, monkeypatch):
    p, cam, spec = panel
    monkeypatch.setattr(spec, "ShamrockGetWavelength", lambda device=DEVICE: (20201, 0.0))
    p._refresh_status()
    assert si.get_interlock().mode == si.UNKNOWN
    assert "desconocido" in p.lbl_specular_state.text()
    assert not p.btn_reread.isHidden()
    assert not p.spin_gain.isEnabled()
    p.btn_zero_order.click()
    assert spec.ShamrockGetGrating(DEVICE)[1] == GRATING_150_LINES
    monkeypatch.undo()
    p.btn_reread.click()
    assert si.get_interlock().mode == si.FIRST_ORDER and p.btn_reread.isHidden()


def test_open_laser_in_specular_is_named_and_high_power_warns(panel, monkeypatch):
    p, cam, spec = panel
    p.btn_zero_order.click()
    p.zero_order._open_names = lambda: ["532"]
    p.zero_order._high_power = lambda: True
    p._refresh_status()
    assert "532" in p.lbl_light.text() and "potencia alta" in p.lbl_light.text()


def test_window_badge_and_ctrl0_toggle(monkeypatch):
    from PyQt6 import QtWidgets
    from pyspectrum.window import PySpectrumWindow
    hardware_session.clear_emergency()
    monkeypatch.setattr(QtWidgets.QMessageBox, "question", lambda *a, **k: QtWidgets.QMessageBox.StandardButton.No)
    monkeypatch.setattr(QtWidgets.QMessageBox, "critical", lambda *a, **k: None)
    win = PySpectrumWindow()
    try:
        assert not win.shortcut_zero_order.autoRepeat()
        assert not win._specular_badge_action.isVisible()
        win._shortcut_goto_zero_order()
        assert si.get_interlock().mode == si.SPECULAR
        assert win._specular_badge_action.isVisible()
        assert "ORDEN CERO" in win.lbl_specular_badge.text()
        win._shortcut_goto_zero_order()
        assert si.get_interlock().mode == si.FIRST_ORDER
        assert not win._specular_badge_action.isVisible()
    finally:
        win.left_panel._refresh_timer.stop()
        win.close()


def test_live_viewer_shows_peak_fraction_only_in_specular():
    import numpy as np
    from pyspectrum.ui.exploration_tab import ExplorationTabWidget
    w = ExplorationTabWidget()
    frame = np.full((20, 20), 500.0)
    frame[10, 10] = 500.0 + 0.62 * 16383
    si.get_interlock().publish(si.FIRST_ORDER, "prueba")
    w.update_image(frame)
    assert w.lbl_saturation.isHidden()
    si.get_interlock().publish(si.SPECULAR, "prueba")
    w.update_image(frame)
    assert not w.lbl_saturation.isHidden()
    assert "62 %" in w.lbl_saturation.text() and "#F9E2AF" in w.lbl_saturation.styleSheet()   # amarillo
    frame[10, 10] = 500.0 + 0.9 * 16383
    w.update_image(frame)
    assert "saturación en orden cero" in w.lbl_saturation.text() and "#F38BA8" in w.lbl_saturation.styleSheet()
    w.deleteLater()
