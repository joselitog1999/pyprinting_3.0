# -*- coding: utf-8 -*-
"""Panel izquierdo: lo leído y lo pedido (paso 8 del bloque A; Ronda 3 §1.3, §2.1-2.2; H-08, H-09, H-10, H-27).

- **Columnas:** la izquierda muestra lo leído, con su marca [L]/[E]/[!]/[?]/[X]; la derecha, lo que el
  operador pide. Nunca comparten widget.
- **Explícito:** ningún combo ni spinbox de hardware actúa al cambiar; hacen falta [Aplicar], [Fijar] o
  [Ir] (G-04, H-27). La rueda no cambia un control sin foco (H-10, S-06).
- **Nada inventado:** la temperatura y el enfriador salen de la lectura, nunca del valor por defecto del
  widget (test de R2-arq §7.2).
- **Enfriador:** apagarlo pide confirmación con la temperatura actual (H-27).
- **Ventilador:** low/high, sin "off".
- **Marcas:** el setpoint, la HS, la VS y los modos se muestran [E].
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYPRINTING_SAFE", "1")

import pytest
from PyQt6 import QtCore, QtGui, QtWidgets

from pyspectrum.drivers.andor_ccd_driver import DRV_SUCCESS, FAN_MODE_FULL, get_andor_ccd
from pyspectrum.drivers.shamrock_driver import DEVICE, GRATING_1200_LINES, get_shamrock
from pyspectrum.modules.camera_baseline import apply_camera_baseline
from pyspectrum.modules.hardware_session import hardware_session
from pyspectrum.services import spectrometer_state as st_mod
from pyspectrum.ui.left_hardware_panel import LeftHardwarePanel

_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["pytest"])


@pytest.fixture
def env(monkeypatch):
    hardware_session.clear_emergency()
    monkeypatch.setattr(st_mod, "_SENT", st_mod.SentRegistry())
    cam = get_andor_ccd(force_mock=True)
    cam.abort_acquisition()
    cam.set_exposure_time(0.05)
    spec = get_shamrock(force_mock=True)
    report = apply_camera_baseline(cam)
    p = LeftHardwarePanel(cam, spec)
    p.apply_camera_baseline_report(report)
    p._refresh_status()
    yield p, cam, spec
    p._refresh_timer.stop()


def test_temperature_and_cooler_come_from_the_reading(env, monkeypatch):
    p, cam, spec = env
    assert "[L]" in p.lbl_temp_badge.text() and "°C" in p.lbl_temp_badge.text()
    assert "[L]" in p.lbl_cooler_read.text() and "encendido" in p.lbl_cooler_read.text()
    monkeypatch.setattr(cam, "get_temperature", lambda: (20075, -65.0))
    monkeypatch.setattr(cam, "is_cooler_on", lambda: (20075, True))
    p._refresh_status()
    assert "[! 20075]" in p.lbl_temp_badge.text() and "-65" not in p.lbl_temp_badge.text()
    assert "[! 20075]" in p.lbl_cooler_read.text() and "encendido" not in p.lbl_cooler_read.text()


def test_setpoint_needs_apply(env):
    p, cam, spec = env
    p.spin_temp.setValue(-61)
    p.spin_temp.editingFinished.emit()
    assert p.control.sent.get("temperature_setpoint_c").value == -60     # el del arranque
    p.btn_apply_temp.click()
    p._refresh_status()
    assert p.control.sent.get("temperature_setpoint_c").value == -61
    assert "[E] -61 °C" in p.lbl_setpoint.text()


def test_turning_the_cooler_off_asks_for_confirmation(env, monkeypatch):
    p, cam, spec = env
    asked = []
    monkeypatch.setattr(QtWidgets.QMessageBox, "question",
                        lambda *a, **k: asked.append(a[2]) or QtWidgets.QMessageBox.StandardButton.No)
    p.btn_cooler.click()
    assert asked and "°C" in asked[0]
    assert cam.is_cooler_on() == (DRV_SUCCESS, True)
    monkeypatch.setattr(QtWidgets.QMessageBox, "question", lambda *a, **k: QtWidgets.QMessageBox.StandardButton.Yes)
    p.btn_cooler.click()
    assert cam.is_cooler_on() == (DRV_SUCCESS, False)
    assert "apagado" in p.lbl_cooler_read.text() and "Encender" in p.btn_cooler.text()


def test_fan_low_high_radios(env):
    p, cam, spec = env
    assert "[E] low" in p.lbl_fan.text() and p.rb_fan_low.isChecked()
    p.rb_fan_high.click()
    assert p.control.sent.get("fan_mode").value == FAN_MODE_FULL
    assert "[E] high" in p.lbl_fan.text()


def test_hs_speed_needs_apply_and_is_shown_as_sent(env):
    p, cam, spec = env
    assert "[E] HS 13 MHz" in p.lbl_speeds.text() and "[E] VS 1.9 µs" in p.lbl_speeds.text()
    idx = p.cmb_hsspeed.findData(27.0)
    p.cmb_hsspeed.setCurrentIndex(idx)
    assert p.control.sent.get("hs_speed_mhz").value == pytest.approx(13.0)   # nada sin [Aplicar]
    p.btn_apply_hs.click()
    assert "[E] HS 27 MHz" in p.lbl_speeds.text()


def test_modes_are_shown_as_sent(env):
    p, cam, spec = env
    assert "[E] Image" in p.lbl_modes.text() and "[E] Single Scan" in p.lbl_modes.text()


def test_gain_and_exposure_need_apply_and_show_the_reading(env):
    p, cam, spec = env
    assert p.spin_gain.maximum() == 255 and p.spin_gain.suffix().strip() == "DAC"
    p.spin_gain.setValue(40)
    p.spin_gain.editingFinished.emit()
    assert cam.get_emccd_gain() == 0
    p.btn_apply_gain.click()
    assert cam.get_emccd_gain() == 40
    p.spin_exposure.setValue(0.2)
    p.spin_exposure.editingFinished.emit()
    assert cam.get_exposure_time() == pytest.approx(0.05)
    p.btn_apply_exposure.click()
    p._refresh_status()
    assert cam.get_exposure_time() == pytest.approx(0.2)
    assert "[L] 0.2000 s" in p.lbl_exposure_read.text()


def test_grating_combo_does_not_move_until_ir(env):
    p, cam, spec = env
    p.cmb_grating.setCurrentIndex(GRATING_1200_LINES - 1)
    assert spec.ShamrockGetGrating(DEVICE)[1] == 1
    p.edit_wavelength.setValue(550.0)
    p.btn_goto_wavelength.click()
    assert spec.ShamrockGetGrating(DEVICE)[1] == GRATING_1200_LINES
    p._refresh_status()
    assert "[L]" in p.lbl_grating_read.text() and "1200 l/mm" in p.lbl_grating_read.text()


def test_slit_and_ports_are_set_explicitly_and_reread(env):
    p, cam, spec = env
    p.spin_slit.setValue(120.0)
    p.spin_slit.editingFinished.emit()
    assert spec.ShamrockGetSlit(DEVICE, 1)[1] != pytest.approx(120.0)
    p.btn_set_slit.click()
    assert spec.ShamrockGetSlit(DEVICE, 1)[1] == pytest.approx(120.0)
    assert "[L] 120.0 µm" in p.lbl_slit_read.text()
    p.cmb_flipper_in.setCurrentIndex(1)
    assert spec.ShamrockGetFlipper(DEVICE, 1)[1] == 0
    p.btn_set_ports.click()
    assert spec.ShamrockGetFlipper(DEVICE, 1)[1] == 1
    assert "[L]" in p.lbl_ports_read.text()


def test_wheel_does_not_change_an_unfocused_control(env):
    p, cam, spec = env
    before = p.spin_temp.value()
    ev = QtGui.QWheelEvent(QtCore.QPointF(5, 5), QtCore.QPointF(5, 5), QtCore.QPoint(0, 0), QtCore.QPoint(0, 120),
                           QtCore.Qt.MouseButton.NoButton, QtCore.Qt.KeyboardModifier.NoModifier,
                           QtCore.Qt.ScrollPhase.NoScrollPhase, False)
    QtWidgets.QApplication.sendEvent(p.spin_temp, ev)
    assert p.spin_temp.value() == before
    idx = p.cmb_grating.currentIndex()
    QtWidgets.QApplication.sendEvent(p.cmb_grating, ev)
    assert p.cmb_grating.currentIndex() == idx


def test_disconnected_camera_shows_not_connected(monkeypatch):
    class _Gone:
        available = False
        unavailable_reason = "pylablib no pudo abrir la cámara"
        def __getattr__(self, name):
            return lambda *a, **k: 20075
    hardware_session.clear_emergency()
    p = LeftHardwarePanel(_Gone(), get_shamrock(force_mock=True))
    try:
        assert "[X]" in p.lbl_camera_connection.text() and "pylablib" in p.lbl_camera_connection.text()
        assert not p.btn_apply_temp.isEnabled() and not p.btn_cooler.isEnabled()
    finally:
        p._refresh_timer.stop()
