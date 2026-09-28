# -*- coding: utf-8 -*-
"""Bloque A de PySpectrum 3.0, paso 4: un solo dueño de los drivers y ningún reinicio implícito (DEC-040).

Antes (Ronda 2, V5):
- abrir el tablero de hardware reescaneaba, y reescanear llamaba a `get_andor_ccd(reset=True)` /
  `get_shamrock(reset=True)`. Eso cerraba el driver vivo (ShutDown apaga el enfriador de la cámara)
  y creaba OTRA instancia, así que todos los backends quedaban apuntando a una instancia cerrada;
- "Desconectar" cerraba y enseguida pedía una instancia nueva, que se volvía a inicializar;
- el reescaneo también llamaba a `pi.connect()`, que reconecta la platina y la manda a home si su
  conexión se había perdido (contra DEC-036: sin reconexión automática).

Ahora: reconectar reinicializa LA MISMA instancia y sólo por una acción explícita, rechazada con una
rutina en curso o con la E-STOP; abrir el tablero sólo refresca el estado, sin tocar ningún equipo.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYPRINTING_SAFE", "1")

import pytest
from PyQt6.QtWidgets import QApplication

from core import hardware_manager as hm_mod
from pyspectrum.drivers import andor_ccd_driver as andor_mod
from pyspectrum.drivers import shamrock_driver as shamrock_mod
from pyspectrum.modules.hardware_session import hardware_session

_app = QApplication.instance() or QApplication(["pytest"])

CAMERA = "Cámara Andor CCD (Espectros)"
SPECTROGRAPH = "Espectrógrafo Andor Shamrock"


class _LoggingDll:
    """Acepta cualquier función del SDK y registra el nombre; todo devuelve éxito."""

    def __init__(self, success):
        self.calls = []
        self._success = success

    def __getattr__(self, name):
        def _call(*args):
            self.calls.append(name)
            return self._success
        return _call


@pytest.fixture
def lab_mode(monkeypatch):
    """Modo laboratorio con drivers REALES sobre DLL falsas, ya conectados como al arrancar."""
    import config
    monkeypatch.setattr(config, "ANDOR_BACKEND", "ctypes")  # el driver ctypes propio (R4-F)
    monkeypatch.setattr(hm_mod, "SAFE_MODE", False)
    monkeypatch.setattr(andor_mod, "SAFE_MODE", False)
    monkeypatch.setattr(shamrock_mod, "SAFE_MODE", False)
    monkeypatch.setattr(andor_mod.AndorCCDDriver, "_init_dll",
                        lambda self: setattr(self, "_dll", _LoggingDll(andor_mod.DRV_SUCCESS)))
    monkeypatch.setattr(shamrock_mod.ShamrockDriver, "_init_dll",
                        lambda self: setattr(self, "_dll", _LoggingDll(shamrock_mod.SHAMROCK_SUCCESS)))
    monkeypatch.setattr(andor_mod, "_andor_instance", None)
    monkeypatch.setattr(shamrock_mod, "_shamrock_instance", None)
    cam = andor_mod.get_andor_ccd()
    spec = shamrock_mod.get_shamrock()
    assert cam.available and spec.available
    cam._dll.calls.clear()
    spec._dll.calls.clear()
    hardware_session.clear_emergency()
    yield hm_mod.HardwareManager(), cam, spec
    hardware_session.clear_emergency()


def test_reconnecting_the_camera_reinitializes_the_same_instance(lab_mode):
    hw, cam, _ = lab_mode
    hw.connect_device(CAMERA)
    assert andor_mod.get_andor_ccd() is cam, "reconectar creó otra instancia: los backends quedarían con una cerrada"
    assert cam._dll.calls.index("ShutDown") < cam._dll.calls.index("Initialize")
    assert cam.available


def test_reconnecting_the_spectrograph_reinitializes_the_same_instance(lab_mode):
    hw, _, spec = lab_mode
    hw.connect_device(SPECTROGRAPH)
    assert shamrock_mod.get_shamrock() is spec
    assert spec._dll.calls.index("ShamrockClose") < spec._dll.calls.index("ShamrockInitialize")
    assert spec.available


@pytest.mark.parametrize("dev, which", [(CAMERA, "cam"), (SPECTROGRAPH, "spec")])
def test_disconnecting_closes_in_place_without_reinitializing(lab_mode, dev, which):
    hw, cam, spec = lab_mode
    drv = cam if which == "cam" else spec
    hw.disconnect_device(dev)
    same = andor_mod.get_andor_ccd() if which == "cam" else shamrock_mod.get_shamrock()
    assert same is drv
    assert drv.available is False and drv.unavailable_reason
    assert not any("Initialize" in c for c in drv._dll.calls), "desconectar volvió a inicializar el equipo"


@pytest.mark.parametrize("dev", [CAMERA, SPECTROGRAPH])
def test_reconnect_is_refused_while_a_routine_holds_the_session(lab_mode, dev):
    hw, cam, spec = lab_mode
    assert hardware_session.acquire_session("Rutina de prueba")
    try:
        assert hw.connect_device(dev) is False
    finally:
        hardware_session.release_session("Rutina de prueba")
    assert cam._dll.calls == [] and spec._dll.calls == []
    assert "Rutina de prueba" in hw.device_details[dev]


def test_reconnect_is_refused_during_an_emergency_stop(lab_mode):
    hw, cam, _ = lab_mode
    hardware_session.emergency_stop()
    assert hw.connect_device(CAMERA) is False
    assert "ShutDown" not in cam._dll.calls and "Initialize" not in cam._dll.calls


def test_refresh_status_touches_no_instrument(lab_mode, monkeypatch):
    hw, cam, spec = lab_mode
    import config
    monkeypatch.setattr(config.pi, "connect", lambda *a, **k: pytest.fail("refrescar el estado no conecta la platina"))
    hw.refresh_status()
    forbidden = {"Initialize", "ShutDown", "ShamrockInitialize", "ShamrockClose", "SetCoolerMode"}
    assert not forbidden & set(cam._dll.calls + spec._dll.calls)
    assert hw.device_states[CAMERA] in ("connected", "disconnected")


def test_opening_the_dashboard_does_not_rescan_or_connect(monkeypatch):
    from modules import hardware_dashboard
    calls = []
    monkeypatch.setattr(hardware_dashboard.hardware_manager, "rescan_hardware", lambda *a, **k: calls.append("rescan"))
    monkeypatch.setattr(hardware_dashboard.hardware_manager, "connect_device", lambda *a, **k: calls.append("connect"))
    refreshed = []
    monkeypatch.setattr(hardware_dashboard.hardware_manager, "refresh_status", lambda: refreshed.append(1))
    win = hardware_dashboard.HardwareDashboardWindow()
    try:
        assert calls == [], f"abrir el tablero no puede reescanear ni conectar: {calls}"
        assert refreshed, "al abrir, el tablero refresca el estado (sin efectos)"
    finally:
        win.close()
        win.deleteLater()


@pytest.mark.parametrize("answer_yes", [False, True])
def test_rescan_and_camera_button_ask_before_restarting(monkeypatch, answer_yes):
    """R4-B-7: reconectar la cámara (o reescanear) apaga el enfriador; se pide confirmación."""
    from PyQt6.QtWidgets import QMessageBox
    from modules import hardware_dashboard
    hm = hardware_dashboard.hardware_manager
    monkeypatch.setattr(hm, "refresh_status", lambda: None)
    calls = []
    monkeypatch.setattr(hm, "rescan_hardware", lambda *a, **k: calls.append("rescan"))
    monkeypatch.setattr(hm, "connect_device", lambda dev: calls.append(("connect", dev)))
    monkeypatch.setattr(hm, "disconnect_device", lambda dev: calls.append(("disconnect", dev)))
    asked = []
    reply = QMessageBox.StandardButton.Yes if answer_yes else QMessageBox.StandardButton.No
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: (asked.append(a[1]), reply)[1])
    win = hardware_dashboard.HardwareDashboardWindow()
    try:
        win.widget._confirm_rescan()
        win.widget._handle_action_button(CAMERA)
        assert len(asked) == 2, "reescanear y el botón de la cámara tienen que avisar"
        expected = ["rescan", ("connect", CAMERA)] if answer_yes else []
        assert calls == expected
    finally:
        win.close()
        win.deleteLater()
