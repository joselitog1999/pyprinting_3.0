# -*- coding: utf-8 -*-
"""Bloque A de PySpectrum 3.0, paso 8: estado operativo base de la cámara al arrancar (DEC-040).

Contrato de la Ronda 2 (instrumentation §1.2) con las decisiones R4-A-6 y R4-B-8: se fijan sólo
parámetros electrónicos de la cámara, cada uno con relectura cuando el SDK la permite; velocidades
elegidas por valor; ganancia EM 0 confirmada o no se adquiere. El doble del SDK corre debajo del
driver REAL.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYPRINTING_SAFE", "1")

import pytest
from PyQt6.QtWidgets import QApplication

from pyspectrum.drivers import andor_ccd_driver as andor_mod
from pyspectrum.modules.camera_baseline import (
    OK, READBACK_MISMATCH, SENT, SET_FAILED, SKIPPED, NOT_READABLE, CameraBaseline, apply_camera_baseline,
)

S = andor_mod.DRV_SUCCESS
# Se guarda: una QApplication sin referencia la recolecta Python y Qt destruye objetos con ella.
_app = QApplication.instance() or QApplication(["pytest"])

# Lo único que el arranque puede escribir en la cámara (instrumentation §1.2 y §1.4).
WHITELIST_SET = {"SetCoolerMode", "SetAcquisitionMode", "SetReadMode", "SetImage", "SetOutputAmplifier",
                 "SetHSSpeed", "SetPreAmpGain", "SetVSSpeed", "SetEMGainMode", "SetEMCCDGain", "SetFanMode",
                 "SetTemperature", "CoolerON", "AbortAcquisition"}


class _FakeSdk:
    def __init__(self, *, detector=(1004, 1002), hs=(35.0, 27.0, 13.0), vs=(0.5, 1.0, 1.9),
                 gain_readback=None, gain_read_code=S, temp_range=(-100, 25)):
        self.calls = []
        self.detector, self.hs, self.vs = detector, list(hs), list(vs)
        self.gain, self.gain_readback, self.gain_read_code = 0, gain_readback, gain_read_code
        self.temp_range, self.preamp, self.cooler = temp_range, None, 0

    def __getattr__(self, name):
        if name.startswith("Set") or name in ("CoolerON", "AbortAcquisition"):
            def _set(*args):
                self.calls.append((name, tuple(getattr(a, "value", a) for a in args)))
                if name == "SetEMCCDGain":
                    self.gain = args[0].value
                if name == "SetPreAmpGain":
                    self.preamp = args[0].value
                if name == "CoolerON":
                    self.cooler = 1
                return S
            return _set
        raise AttributeError(name)

    def GetDetector(self, x, y):
        x._obj.value, y._obj.value = self.detector
        return S

    def GetStatus(self, p):
        p._obj.value = andor_mod.DRV_IDLE
        return S

    def GetNumberHSSpeeds(self, ch, typ, p):
        p._obj.value = len(self.hs)
        return S

    def GetHSSpeed(self, ch, typ, idx, p):
        p._obj.value = self.hs[idx.value]
        return S

    def GetCurrentPreAmpGain(self, p, name, n):
        p._obj.value = self.preamp if self.preamp is not None else -1
        return S

    def GetNumberVSSpeeds(self, p):
        p._obj.value = len(self.vs)
        return S

    def GetVSSpeed(self, idx, p):
        p._obj.value = self.vs[idx.value]
        return S

    def GetEMGainRange(self, lo, hi):
        lo._obj.value, hi._obj.value = 0, 255
        return S

    def GetEMCCDGain(self, p):
        p._obj.value = self.gain if self.gain_readback is None else self.gain_readback
        return self.gain_read_code

    def GetTemperatureRange(self, lo, hi):
        lo._obj.value, hi._obj.value = self.temp_range
        return S

    def IsCoolerOn(self, p):
        p._obj.value = self.cooler
        return S


def _cam(monkeypatch, **kw):
    monkeypatch.setattr(andor_mod.AndorCCDDriver, "_init_dll", lambda self: None)
    cam = andor_mod.AndorCCDDriver()
    cam._dll = _FakeSdk(**kw)
    cam._connected = True
    return cam


def _called(cam, name):
    return [args for n, args in cam._dll.calls if n == name]


def test_baseline_writes_only_whitelisted_camera_settings(monkeypatch):
    cam = _cam(monkeypatch)
    rep = apply_camera_baseline(cam)
    written = {n for n, _ in cam._dll.calls}
    assert written <= WHITELIST_SET, f"el arranque escribió fuera de la lista blanca: {written - WHITELIST_SET}"
    assert not rep.blocks_acquisition, rep.summary()
    assert _called(cam, "SetEMCCDGain") == [(0,)]
    assert _called(cam, "SetFanMode") == [(andor_mod.FAN_MODE_LOW,)]
    assert _called(cam, "SetTemperature") == [(-60,)]
    assert _called(cam, "SetOutputAmplifier") == [(0,)]
    assert rep.item("cooler_on").outcome == OK


def test_vertical_speed_is_chosen_by_value_and_matches_the_legacy_index():
    """Con la tabla (0.5, 1.0, 1.9) µs el índice de 1.9 µs es el 2, como el legado (Camera_ps.py:607)."""
    rep = apply_camera_baseline(andor_mod._MockAndorCCD())
    item = rep.item("vs_speed_us")
    assert item.outcome == SENT and item.readback == pytest.approx(1.9) and "índice 2" in item.detail


def test_vertical_speed_found_at_another_index_is_used_and_flagged(monkeypatch):
    cam = _cam(monkeypatch, vs=(0.3, 0.5, 0.9, 1.7, 1.9))
    rep = apply_camera_baseline(cam)
    assert _called(cam, "SetVSSpeed") == [(4,)]
    assert "difiere" in rep.item("vs_speed_us").detail


def test_vertical_speed_is_not_set_blindly_without_a_1_9_us_entry(monkeypatch):
    cam = _cam(monkeypatch, vs=(0.5, 1.0, 1.5))
    rep = apply_camera_baseline(cam)
    assert rep.item("vs_speed_us").outcome == SET_FAILED
    assert _called(cam, "SetVSSpeed") == []


def test_horizontal_speed_13_mhz_is_chosen_by_value(monkeypatch):
    cam = _cam(monkeypatch, hs=(13.0, 27.0, 35.0))
    apply_camera_baseline(cam)
    assert _called(cam, "SetHSSpeed") == [(0, 0)]  # typ 0 (EMCCD), índice 0 = 13 MHz


def test_horizontal_speed_without_13_mhz_is_not_set(monkeypatch):
    cam = _cam(monkeypatch, hs=(35.0, 27.0))
    rep = apply_camera_baseline(cam)
    assert rep.item("hs_speed_mhz").outcome == SET_FAILED and _called(cam, "SetHSSpeed") == []


def test_em_gain_readback_different_from_zero_blocks_acquisition(monkeypatch):
    cam = _cam(monkeypatch, gain_readback=12)
    rep = apply_camera_baseline(cam)
    assert rep.item("em_gain").outcome == READBACK_MISMATCH
    assert rep.blocks_acquisition


def test_em_gain_readback_failure_blocks_acquisition(monkeypatch):
    cam = _cam(monkeypatch, gain_read_code=20013)
    rep = apply_camera_baseline(cam)
    assert rep.item("em_gain").outcome == NOT_READABLE and rep.blocks_acquisition


def test_unexpected_detector_geometry_blocks_acquisition(monkeypatch):
    cam = _cam(monkeypatch, detector=(1002, 1002))
    rep = apply_camera_baseline(cam)
    assert rep.item("detector").outcome == READBACK_MISMATCH and rep.blocks_acquisition


def test_setpoint_outside_the_camera_range_is_not_sent(monkeypatch):
    cam = _cam(monkeypatch, temp_range=(-40, 25))
    rep = apply_camera_baseline(cam)
    assert rep.item("temperature_c").outcome == SKIPPED and _called(cam, "SetTemperature") == []


def test_unavailable_camera_is_skipped_without_calls(monkeypatch):
    monkeypatch.setattr(andor_mod.AndorCCDDriver, "_init_dll", lambda self: None)
    cam = andor_mod.AndorCCDDriver()
    cam.initialize()
    rep = apply_camera_baseline(cam)
    assert [i.outcome for i in rep.items] == [SKIPPED]


def test_fan_high_is_an_operator_option(monkeypatch):
    cam = _cam(monkeypatch)
    apply_camera_baseline(cam, CameraBaseline(fan_mode=andor_mod.FAN_MODE_FULL))
    assert _called(cam, "SetFanMode") == [(andor_mod.FAN_MODE_FULL,)]


def test_safe_mode_simulator_ends_in_the_requested_state():
    cam = andor_mod._MockAndorCCD()
    rep = apply_camera_baseline(cam)
    assert not rep.blocks_acquisition, rep.summary()
    assert cam.get_hs_speed(cam.get_hs_speed_index())[1] == 13.0
    assert cam._fan_mode == "low" and cam._cooler_on and cam.get_emccd_gain() == 0


def test_set_cooler_mode_does_not_report_success_when_the_call_fails(monkeypatch):
    """`set_cooler_mode` devolvía DRV_SUCCESS si la llamada a la DLL tiraba una excepción."""
    cam = _cam(monkeypatch)

    def _boom(*a):
        raise OSError("access violation")
    cam._dll.__dict__["SetCoolerMode"] = _boom
    assert cam.set_cooler_mode(0) != andor_mod.DRV_SUCCESS


def test_pyspectrum_startup_applies_the_baseline_and_the_panel_shows_it(monkeypatch):
    """Al abrir PySpectrum se aplica el estado base, y el panel muestra el setpoint y el enfriador
    enviados, no los valores por defecto del widget (antes: −65 °C y "ON" sin haber enviado nada)."""
    from PyQt6.QtWidgets import QMessageBox
    from pyspectrum.modules.hardware_session import hardware_session
    # Bajo offscreen, question() (closeEvent) y critical() (E-STOP) bloquean si no se reemplazan.
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: None)
    hardware_session.clear_emergency()
    from pyspectrum.window import PySpectrumWindow
    win = PySpectrumWindow()
    try:
        rep = win.camera_baseline_report
        assert rep is not None and not rep.blocks_acquisition, rep.summary()
        assert win.left_panel.spin_temp.value() == -60
        assert win.left_panel.btn_cooler.isChecked() is True
        assert "Enfriador: ON" in win.left_panel.btn_cooler.text()
    finally:
        win.close()
        hardware_session.clear_emergency()
        if hardware_session.is_busy:
            hardware_session.release_session(hardware_session.current_owner)
