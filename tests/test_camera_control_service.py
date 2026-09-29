# -*- coding: utf-8 -*-
"""Control de la cámara en operación (paso 8, D-13; R2-inst §6.2-6.3; Ronda 3 §2.2, H-27).

- Setpoint de temperatura, enfriador, ventilador (low/high, sin "off") y velocidad horizontal, cada uno
  con su verificación:
  - el enfriador con IsCoolerOn;
  - el setpoint, el ventilador y la HS no tienen getter: quedan como enviados [E].
- **Entre adquisiciones:** con la cámara adquiriendo, el SDK devuelve DRV_ACQUIRING. El pedido queda
  pendiente y se aplica cuando la cámara está IDLE; nunca aborta el Live ni una rutina.
- El setpoint se valida contra GetTemperatureRange.
- La HS se elige por valor en la tabla. Si el valor pedido no está, se rechaza sin adivinar (H-08).
"""
import pytest

from pyspectrum.drivers.andor_ccd_driver import DRV_SUCCESS, FAN_MODE_FULL, FAN_MODE_LOW, get_andor_ccd
from pyspectrum.services.camera_control import CameraControlService, ControlState
from pyspectrum.services.spectrometer_state import ReadStatus, SentRegistry


@pytest.fixture
def cam():
    c = get_andor_ccd(force_mock=True)
    c.abort_acquisition()
    return c


@pytest.fixture
def svc(cam):
    return CameraControlService(cam, SentRegistry())


def test_temperature_setpoint_is_sent_and_recorded(svc, cam):
    res = svc.request_temperature(-60)
    assert res.state == ControlState.APPLIED
    assert svc.sent.get("temperature_setpoint_c").status == ReadStatus.SENT_OK
    assert svc.sent.get("temperature_setpoint_c").value == -60


def test_temperature_outside_the_camera_range_is_refused(svc, cam):
    lo, hi = cam.get_temperature_range()[1:]
    res = svc.request_temperature(lo - 5)
    assert res.state == ControlState.REFUSED and str(lo) in res.detail
    assert svc.sent.get("temperature_setpoint_c").status == ReadStatus.NOT_READ


def test_cooler_is_verified_with_is_cooler_on(svc, cam, monkeypatch):
    assert svc.request_cooler(False).state == ControlState.APPLIED
    assert cam.is_cooler_on() == (DRV_SUCCESS, False)
    monkeypatch.setattr(cam, "is_cooler_on", lambda: (DRV_SUCCESS, False))   # no enciende
    res = svc.request_cooler(True)
    assert res.state == ControlState.MISMATCH and "apagado" in res.detail


def test_fan_low_and_high_map_to_the_sdk_codes_and_off_is_not_offered(svc, cam):
    calls = []
    real = cam.set_fan_mode
    cam.set_fan_mode = lambda m: calls.append(m) or real(m)
    assert svc.request_fan("high").state == ControlState.APPLIED
    assert svc.request_fan("low").state == ControlState.APPLIED
    assert calls == [FAN_MODE_FULL, FAN_MODE_LOW]
    assert svc.sent.get("fan_mode").value == FAN_MODE_LOW
    with pytest.raises(ValueError):
        svc.request_fan("off")
    del cam.set_fan_mode


def test_while_acquiring_requests_wait_and_apply_when_idle(svc, cam):
    cam.set_acquisition_mode(5)
    cam.start_acquisition()
    res = svc.request_fan("high")
    assert res.state == ControlState.PENDING and "Live" in res.detail
    assert svc.sent.get("fan_mode").status == ReadStatus.NOT_READ
    assert svc.apply_pending() == []                     # sigue adquiriendo: nada
    cam.abort_acquisition()
    applied = svc.apply_pending()
    assert [r.name for r in applied] == ["fan_mode"] and applied[0].state == ControlState.APPLIED
    assert svc.sent.get("fan_mode").value == FAN_MODE_FULL
    assert svc.pending_names() == []


def test_hs_speed_is_chosen_by_value(svc, cam):
    res = svc.request_hs_speed_mhz(27.0)
    assert res.state == ControlState.APPLIED
    assert svc.sent.get("hs_speed_mhz").value == pytest.approx(27.0)
    res = svc.request_hs_speed_mhz(20.0)
    assert res.state == ControlState.REFUSED and "35" in res.detail and "13" in res.detail


def test_failed_send_is_marked_failed(svc, cam, monkeypatch):
    monkeypatch.setattr(cam, "set_fan_mode", lambda m: 20013)
    res = svc.request_fan("low")
    assert res.state == ControlState.FAILED and res.code == 20013
    assert svc.sent.get("fan_mode").status == ReadStatus.READ_FAILED
