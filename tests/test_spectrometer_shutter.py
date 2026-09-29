# -*- coding: utf-8 -*-
"""Obturador del espectrómetro y conexión de la cámara (decisiones del investigador, 2026-09-29).

- **Cuándo se abre** el obturador del Shamrock: a pedido del operador, en una rutina o en el Live. Nunca al
  arrancar.
- **Cómo:** como el legado, que lo acciona por la salida TTL de la cámara (`setup_shutter('open', 1)` para
  abrir y `setup_shutter('closed', 0)` para cerrar, `Camera_ps.py:645-663`, `StepandGlue_ps.py`). El
  legado además abría al arrancar el obturador por USB (`ShamrockSetShutter(DEVICE, 1)`,
  `PySpectrum_UNSAM.py:793`). Como no se sabe cuál de los dos manda en el banco (BANCO-09), abrir acciona
  los dos y cerrar también.
- **Conexión de la cámara:** con `temperature=-60`. pylablib 1.4.3 no toca el enfriador cuando recibe un
  número (sólo actúa con None u "off"), como el legado con `temperature=10`. El estado base fija −60 °C y
  lo relee. Con None, pylablib elegía un setpoint automático y encendía el enfriador al conectar.
"""
import pytest

from pyspectrum.drivers import andor_pylablib as pl_mod
from pyspectrum.drivers.andor_ccd_driver import DRV_SUCCESS, get_andor_ccd
from pyspectrum.drivers.shamrock_driver import DEVICE, SHAMROCK_SUCCESS, get_shamrock
from pyspectrum.modules.camera_baseline import CameraBaseline
from pyspectrum.services.spectrometer_shutter import close_spectrometer_shutter, open_spectrometer_shutter


def test_camera_connects_with_the_baseline_setpoint_so_pylablib_does_not_touch_the_cooler():
    assert pl_mod.CONNECT_KWARGS["temperature"] == CameraBaseline().temperature_c == -60
    assert pl_mod.CONNECT_KWARGS["fan_mode"] == "low"


class _ShutterCam:
    def __init__(self):
        self.calls = []

    def setup_shutter(self, mode, ttl_mode=0, open_time=None, close_time=None):
        self.calls.append((mode, ttl_mode))


def test_pylablib_shutter_uses_the_legacy_ttl_modes():
    cam = _ShutterCam()
    drv = pl_mod.PylablibAndorCCD(camera_factory=lambda: cam, lib_factory=lambda: None)
    assert drv.initialize()
    assert drv.set_shutter_mode(1) == DRV_SUCCESS
    assert drv.set_shutter_mode(2) == DRV_SUCCESS
    assert cam.calls == [("open", 1), ("closed", 0)]


class _Spy:
    def __init__(self, inner, log):
        self._inner, self._log = inner, log

    def __getattr__(self, name):
        attr = getattr(self._inner, name)
        if name in ("ShamrockSetShutter", "set_shutter_mode"):
            def rec(*a):
                self._log.append((name, a[-1]))
                return attr(*a)
            return rec
        return attr


def test_open_and_close_act_on_both_paths():
    log = []
    cam = _Spy(get_andor_ccd(force_mock=True), log)
    spec = _Spy(get_shamrock(force_mock=True), log)
    res = open_spectrometer_shutter(cam, spec)
    assert res.ok and log == [("ShamrockSetShutter", 1), ("set_shutter_mode", 1)]
    log.clear()
    res = close_spectrometer_shutter(cam, spec)
    assert res.ok and log == [("set_shutter_mode", 2), ("ShamrockSetShutter", 0)]


def test_a_failed_path_is_reported():
    class _Bad:
        def ShamrockSetShutter(self, device, mode):
            return 20201
    res = open_spectrometer_shutter(get_andor_ccd(force_mock=True), _Bad())
    assert not res.ok and "20201" in res.detail


def test_live_opens_and_closes_the_spectrometer_shutter():
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication(["pytest"])
    from pyspectrum.ui.exploration_tab import ExplorationWorker
    log = []
    cam = _Spy(get_andor_ccd(force_mock=True), log)
    spec = _Spy(get_shamrock(force_mock=True), log)
    w = ExplorationWorker(cam, spec)
    w.start_live()
    assert ("ShamrockSetShutter", 1) in log and ("set_shutter_mode", 1) in log
    log.clear()
    w.stop_live()
    assert ("ShamrockSetShutter", 0) in log and ("set_shutter_mode", 2) in log
