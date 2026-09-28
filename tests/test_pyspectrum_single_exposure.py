# -*- coding: utf-8 -*-
"""Bloque A de PySpectrum 3.0, paso 6: una exposición = un cuadro nuevo o una falla explícita (DEC-040).

El doble `_FakeAndorDll` modela la máquina de estados del SDK2 (IDLE → ACQUIRING → IDLE, con un
evento de adquisición al terminar un single scan) y se usa debajo del driver REAL
(`AndorCCDDriver`), así que el código de producción del driver también corre.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYPRINTING_SAFE", "1")

import threading
import time

import numpy as np
import pytest

from pyspectrum.drivers import andor_ccd_driver as andor_mod
from pyspectrum.modules.acquisition import (
    AcquisitionFailure, AcquisitionFailureKind, ExposureRequest, Frame, single_exposure,
)

OK = andor_mod.DRV_SUCCESS


class _FakeAndorDll:
    def __init__(self, *, never_finishes=False, read_code=OK, counter_step=1, status_fail=False,
                 status_fail_while_acquiring=False, start_status=andor_mod.DRV_IDLE):
        self.calls = []
        self.exposure = 0.1
        self.acquiring = start_status == andor_mod.DRV_ACQUIRING
        self.t0 = time.monotonic()
        self.count = 7
        self.event = False
        self.never_finishes = never_finishes
        self.read_code = read_code
        self.counter_step = counter_step
        self.status_fail = status_fail
        self.status_fail_while_acquiring = status_fail_while_acquiring

    def _log(self, name):
        self.calls.append(name)

    def _advance(self):
        if self.acquiring and not self.never_finishes and time.monotonic() - self.t0 >= self.exposure:
            self.acquiring = False
            self.count += self.counter_step
            self.event = True

    def Initialize(self, _d):
        return OK

    def SetCoolerMode(self, _m):
        return OK

    def SetAcquisitionMode(self, _m):
        self._log("SetAcquisitionMode")
        return andor_mod.DRV_ACQUIRING if self.acquiring else OK

    def SetExposureTime(self, t):
        self._log("SetExposureTime")
        self.exposure = t.value
        return OK

    def GetEMCCDGain(self, p):
        p._obj.value = 0
        return OK

    def GetAcquisitionTimings(self, e, a, k):
        e._obj.value = a._obj.value = k._obj.value = self.exposure
        return OK

    def GetTotalNumberImagesAcquired(self, p):
        self._advance()
        p._obj.value = self.count
        return OK

    def GetStatus(self, p):
        self._advance()
        if self.status_fail or (self.status_fail_while_acquiring and self.acquiring):
            return 20013  # DRV_ERROR_ACK
        p._obj.value = andor_mod.DRV_ACQUIRING if self.acquiring else andor_mod.DRV_IDLE
        return OK

    def StartAcquisition(self):
        self._log("StartAcquisition")
        self.acquiring, self.t0, self.event = True, time.monotonic(), False
        return OK

    def AbortAcquisition(self):
        self._log("AbortAcquisition")
        self.acquiring = False
        return OK

    def WaitForAcquisitionTimeOut(self, ms):
        self._advance()
        if self.event:
            self.event = False
            return OK
        remaining = self.t0 + self.exposure - time.monotonic()
        time.sleep(max(0.0, min(ms.value / 1000.0, remaining if not self.never_finishes else ms.value / 1000.0)))
        self._advance()
        if self.event:
            self.event = False
            return OK
        return andor_mod.DRV_NO_NEW_DATA

    def GetAcquiredData(self, arr, size):
        self._log("GetAcquiredData")
        if self.read_code != OK:
            return self.read_code
        for i in range(size.value):
            arr[i] = i + 1
        return OK

    def GetTemperature(self, p):
        p._obj.value = -60
        return andor_mod.DRV_TEMP_STABILIZED


def _camera(monkeypatch, **fake_kwargs):
    monkeypatch.setattr(andor_mod.AndorCCDDriver, "_init_dll", lambda self: None)
    cam = andor_mod.AndorCCDDriver()
    cam._dll = _FakeAndorDll(**fake_kwargs)
    cam._connected = True
    return cam


REQ = ExposureRequest(exposure_s=0.3, shape=(1004,))


def test_waits_for_the_exposure_and_returns_a_new_frame(monkeypatch):
    cam = _camera(monkeypatch)
    t0 = time.monotonic()
    out = single_exposure(cam, REQ, is_estopped=lambda: False)
    assert isinstance(out, Frame), out
    assert time.monotonic() - t0 >= 0.29, "devolvió un cuadro antes de terminar la exposición"
    assert out.data.shape == (1004,) and out.data[0] == 1 and out.data[-1] == 1004
    assert out.frame_index == 8
    assert cam._dll.calls.index("StartAcquisition") < cam._dll.calls.index("GetAcquiredData")


def test_read_failure_is_a_failure_never_zeros(monkeypatch):
    cam = _camera(monkeypatch, read_code=andor_mod.DRV_P2INVALID)
    out = single_exposure(cam, REQ, is_estopped=lambda: False)
    assert isinstance(out, AcquisitionFailure)
    assert out.kind is AcquisitionFailureKind.READ_FAILED and out.code == andor_mod.DRV_P2INVALID


def test_no_new_data_is_a_stale_frame(monkeypatch):
    cam = _camera(monkeypatch, read_code=andor_mod.DRV_NO_NEW_DATA)
    out = single_exposure(cam, REQ, is_estopped=lambda: False)
    assert isinstance(out, AcquisitionFailure) and out.kind is AcquisitionFailureKind.STALE_FRAME


def test_counter_that_does_not_advance_one_frame_is_stale(monkeypatch):
    cam = _camera(monkeypatch, counter_step=2)
    out = single_exposure(cam, REQ, is_estopped=lambda: False)
    assert isinstance(out, AcquisitionFailure) and out.kind is AcquisitionFailureKind.STALE_FRAME


def test_timeout_is_bounded_beats_every_tranche_and_aborts(monkeypatch):
    cam = _camera(monkeypatch, never_finishes=True)
    ticks = []
    t0 = time.monotonic()
    out = single_exposure(cam, ExposureRequest(0.2, (1004,)), on_tick=lambda: ticks.append(1),
                          is_estopped=lambda: False, tranche_ms=100, readout_margin_s=0.3)
    elapsed = time.monotonic() - t0
    assert isinstance(out, AcquisitionFailure) and out.kind is AcquisitionFailureKind.TIMEOUT
    assert elapsed < 0.2 + 0.3 + 0.35, f"el tope no se respetó ({elapsed:.2f} s)"
    assert len(ticks) >= 4, "el latido (on_tick) tiene que llamarse en cada tramo"
    assert cam._dll.calls[-1] == "AbortAcquisition" and not cam._dll.acquiring


def test_user_stop_responds_within_one_tranche(monkeypatch):
    cam = _camera(monkeypatch)
    stop_at = time.monotonic() + 0.2
    t0 = time.monotonic()
    out = single_exposure(cam, ExposureRequest(5.0, (1004,)), should_abort=lambda: time.monotonic() >= stop_at,
                          is_estopped=lambda: False, tranche_ms=250)
    assert isinstance(out, AcquisitionFailure) and out.kind is AcquisitionFailureKind.USER_STOP
    assert time.monotonic() - t0 < 0.6
    assert "AbortAcquisition" in cam._dll.calls and not cam._dll.acquiring


def test_estop_aborts_the_exposure(monkeypatch):
    cam = _camera(monkeypatch)
    out = single_exposure(cam, ExposureRequest(5.0, (1004,)), is_estopped=lambda: True, tranche_ms=50)
    assert isinstance(out, AcquisitionFailure) and out.kind is AcquisitionFailureKind.ESTOP
    assert "AbortAcquisition" in cam._dll.calls and not cam._dll.acquiring


def test_refuses_to_start_if_the_camera_is_already_acquiring(monkeypatch):
    cam = _camera(monkeypatch, start_status=andor_mod.DRV_ACQUIRING, never_finishes=True)
    out = single_exposure(cam, REQ, is_estopped=lambda: False)
    assert isinstance(out, AcquisitionFailure) and out.kind is AcquisitionFailureKind.NOT_IDLE
    assert "StartAcquisition" not in cam._dll.calls


def test_status_failure_is_never_read_as_finished(monkeypatch):
    cam = _camera(monkeypatch, status_fail=True)
    out = single_exposure(cam, REQ, is_estopped=lambda: False)
    assert isinstance(out, AcquisitionFailure) and out.kind is AcquisitionFailureKind.READ_FAILED
    assert "GetAcquiredData" not in cam._dll.calls


def test_status_failure_during_the_wait_is_never_read_as_finished(monkeypatch):
    """La consulta de estado entre tramos falla: no es "terminó", y no se lee ningún cuadro."""
    cam = _camera(monkeypatch, status_fail_while_acquiring=True)
    out = single_exposure(cam, ExposureRequest(1.0, (1004,)), is_estopped=lambda: False, tranche_ms=50)
    assert isinstance(out, AcquisitionFailure) and out.kind is AcquisitionFailureKind.READ_FAILED
    assert out.call == "GetStatus"
    assert "GetAcquiredData" not in cam._dll.calls
    assert "AbortAcquisition" in cam._dll.calls, "tras una falla de estado se aborta por las dudas"


def test_unconnected_camera_is_reported_not_simulated(monkeypatch):
    monkeypatch.setattr(andor_mod.AndorCCDDriver, "_init_dll", lambda self: None)
    cam = andor_mod.AndorCCDDriver()
    cam.initialize()
    out = single_exposure(cam, REQ, is_estopped=lambda: False)
    assert isinstance(out, AcquisitionFailure) and out.kind is AcquisitionFailureKind.DEVICE_NOT_CONNECTED


@pytest.mark.parametrize("exposure", [0.0, -1.0, 61.0])
def test_exposure_outside_the_allowed_range_is_rejected(monkeypatch, exposure):
    cam = _camera(monkeypatch)
    out = single_exposure(cam, ExposureRequest(exposure, (1004,)), is_estopped=lambda: False)
    assert isinstance(out, AcquisitionFailure) and out.kind is AcquisitionFailureKind.INVALID_REQUEST
    assert "StartAcquisition" not in cam._dll.calls


def test_waiting_does_not_hold_the_driver_lock(monkeypatch):
    """Mientras un tramo espera, otro hilo (el sondeo de temperatura, el Stop) usa el driver."""
    cam = _camera(monkeypatch)
    result = {}

    def _probe():
        time.sleep(0.1)
        t0 = time.monotonic()
        cam.get_temperature()
        result["latency"] = time.monotonic() - t0

    th = threading.Thread(target=_probe)
    th.start()
    single_exposure(cam, ExposureRequest(0.6, (1004,)), is_estopped=lambda: False, tranche_ms=500)
    th.join()
    assert result["latency"] < 0.15, f"get_temperature esperó {result['latency']:.2f} s: la espera retiene el lock"


@pytest.mark.parametrize("mode, shape", [(andor_mod.READ_MODE_FVB, (1004,)),
                                         (andor_mod.READ_MODE_SINGLE_TRACK, (1004,)),
                                         (andor_mod.READ_MODE_IMAGE, (1002, 1004))])
def test_safe_mode_simulator_follows_the_same_contract(mode, shape):
    cam = andor_mod._MockAndorCCD()
    cam.set_read_mode(mode)
    out = single_exposure(cam, ExposureRequest(0.05, shape), is_estopped=lambda: False)
    assert isinstance(out, Frame), out
    assert out.data.shape == shape and np.all(np.isfinite(out.data))
    again = cam.get_acquired_data_checked(int(np.prod(shape)))
    assert again[0] == andor_mod.DRV_NO_NEW_DATA, "el mismo cuadro no se puede leer dos veces como nuevo"
