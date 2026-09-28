# -*- coding: utf-8 -*-
"""La cámara Andor sobre pylablib, como en el legado (R4-F, DEC-040).

`PylablibAndorCCD` ofrece la interfaz de `AndorCCDDriver` sobre `AndorSDK2Camera`. La cámara falsa
imita la API de pylablib 1.4.3 (métodos, nombres de modos, coordenadas desde 0 con fin exclusivo y
`TimeoutError` de `wait_for_frame`); así se prueban la traducción de coordenadas y de errores, el
estado base y la adquisición de un cuadro, sin cámara.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYPRINTING_SAFE", "1")

import time
from collections import namedtuple

import numpy as np
import pytest
from PyQt6.QtWidgets import QApplication

from pyspectrum.drivers import andor_ccd_driver as andor_mod
from pyspectrum.drivers import andor_pylablib as pl_mod
from pyspectrum.modules.acquisition import AcquisitionFailure, AcquisitionFailureKind, ExposureRequest, Frame, single_exposure
from pyspectrum.modules.camera_baseline import apply_camera_baseline

_app = QApplication.instance() or QApplication(["pytest"])

TAmp = namedtuple("TAmp", "channel channel_bitdepth oamp oamp_kind hsspeed hsspeed_MHz preamp preamp_gain")


class _LibError(Exception):
    def __init__(self, code):
        super().__init__(f"error {code}")
        self.code = code


class _FakeCam:
    class TimeoutError(Exception):
        pass

    def __init__(self, *, finishes=True, frame=None):
        self.calls = []
        self.exposure, self.mode, self.acquiring = 0.05, "cont", False
        self.t0, self.finishes = 0.0, finishes
        self.frame = frame
        self.unread = None
        self.gain, self.cooler, self.oamp, self.hsspeed, self.preamp = 0, False, 0, 0, 0
        self.fan = "low"

    def _log(self, *a):
        self.calls.append(a)

    def is_opened(self): return True
    def close(self): self._log("close")
    def set_temperature(self, t, enable_cooler=True):
        self._log("set_temperature", t, enable_cooler)
        self.cooler = self.cooler or enable_cooler
    def get_temperature(self): return -60.0
    def get_temperature_status(self): return "stabilized"
    def set_cooler(self, on=True): self._log("set_cooler", on); self.cooler = on
    def is_cooler_on(self): return self.cooler
    def get_temperature_range(self): return (-100, 25)
    def set_fan_mode(self, mode): self._log("set_fan_mode", mode); self.fan = mode
    def get_all_amp_modes(self):
        return [TAmp(0, 14, 0, "Electron Multiplying", i, mhz, p, g)
                for i, mhz in enumerate((35.0, 27.0, 13.0)) for p, g in enumerate((1.0, 2.4, 4.9))]
    def get_oamp(self): return self.oamp
    def set_amp_mode(self, channel=None, oamp=None, hsspeed=None, preamp=None):
        self._log("set_amp_mode", dict(channel=channel, oamp=oamp, hsspeed=hsspeed, preamp=preamp))
        self.oamp = self.oamp if oamp is None else oamp
        self.hsspeed = self.hsspeed if hsspeed is None else hsspeed
        self.preamp = self.preamp if preamp is None else preamp
    def get_hsspeed(self): return self.hsspeed
    def get_preamp(self): return self.preamp
    def get_all_vsspeeds(self): return [0.5, 1.0, 1.9]
    def set_vsspeed(self, i): self._log("set_vsspeed", i)
    def set_EMCCD_gain(self, g, advanced=None): self._log("set_EMCCD_gain", g); self.gain = g
    def get_EMCCD_gain(self): return (self.gain, False)
    def set_exposure(self, e): self._log("set_exposure", e); self.exposure = e; return e
    def get_exposure(self): return self.exposure
    def setup_shutter(self, mode, ttl_mode=0, open_time=None, close_time=None): self._log("setup_shutter", mode)
    def set_read_mode(self, name): self._log("set_read_mode", name)
    def setup_single_track_mode(self, center=0, width=1): self._log("setup_single_track_mode", center, width)
    def setup_image_mode(self, *a): self._log("setup_image_mode", *a)
    def setup_multi_track_mode(self, n, h, o): self._log("setup_multi_track_mode", n, h, o); return (n, h, o, 3, 7)
    def setup_random_track_mode(self, tracks): self._log("setup_random_track_mode", tracks)
    def get_detector_size(self): return (1004, 1002)
    def get_status(self): return "acquiring" if self.acquiring else "idle"
    def setup_acquisition(self, mode=None): self._log("setup_acquisition", mode); self.mode = mode
    def start_acquisition(self):
        self._log("start_acquisition", self.mode)
        self.acquiring, self.t0, self.unread = True, time.monotonic(), None
    def stop_acquisition(self): self._log("stop_acquisition"); self.acquiring = False
    def wait_for_frame(self, timeout=20.0):
        remaining = self.t0 + self.exposure - time.monotonic()
        if not self.finishes or remaining > timeout:
            time.sleep(timeout)
            raise self.TimeoutError()
        time.sleep(max(0.0, remaining))
        self.unread = self.frame if self.frame is not None else np.arange(1004.0).reshape(1, 1004)
    def read_oldest_image(self):
        f, self.unread = self.unread, None
        return f
    def read_newest_image(self, peek=False):
        return self.unread


class _FakeLib:
    def __init__(self): self.calls = []
    def SetCoolerMode(self, m): self.calls.append(("SetCoolerMode", m))
    def SetEMGainMode(self, m): self.calls.append(("SetEMGainMode", m))
    def GetEMGainRange(self): return (0, 255)


def _adapter(**cam_kw):
    cam = _FakeCam(**cam_kw)
    drv = pl_mod.PylablibAndorCCD(camera_factory=lambda: cam, lib_factory=_FakeLib)
    assert drv.initialize()
    return drv, cam


def _named(cam, name):
    return [c[1:] for c in cam.calls if c[0] == name]


# ── Selección del backend y falla de conexión ─────────────────────────────────────────────────

def test_lab_mode_uses_pylablib_by_default_and_never_the_simulator(monkeypatch):
    import config
    monkeypatch.setattr(config, "ANDOR_BACKEND", "pylablib")
    monkeypatch.setattr(andor_mod, "SAFE_MODE", False)
    monkeypatch.setattr(andor_mod, "_andor_instance", None)

    def _no_camera():
        raise RuntimeError("camera index 0 is not available (0 cameras exist)")
    monkeypatch.setattr(pl_mod, "_default_camera_factory", _no_camera)
    monkeypatch.setattr(pl_mod.PylablibAndorCCD.__init__, "__defaults__", (_no_camera, pl_mod._default_lib))
    cam = andor_mod.get_andor_ccd()
    assert isinstance(cam, pl_mod.PylablibAndorCCD)
    assert cam.is_mock is False and cam.available is False
    assert "0 cameras" in cam.unavailable_reason and "atmcd64d_legacy.dll" in cam.unavailable_reason
    with pytest.raises(andor_mod.DeviceUnavailable):
        cam.get_most_recent_image()


def test_ctypes_backend_remains_selectable(monkeypatch):
    import config
    monkeypatch.setattr(config, "ANDOR_BACKEND", "ctypes")
    assert isinstance(andor_mod._new_hardware_driver(), andor_mod.AndorCCDDriver)


# ── Coordenadas: SDK (desde 1, inclusivas) → pylablib (desde 0, fin exclusivo) ────────────────

def test_image_and_track_coordinates_are_converted_once():
    drv, cam = _adapter()
    assert drv.set_image(1, 1, 1, 1004, 1, 1002) == andor_mod.DRV_SUCCESS
    assert _named(cam, "setup_image_mode")[-1] == (0, 1004, 0, 1002, 1, 1)
    drv.set_single_track(501, 40)
    assert _named(cam, "setup_single_track_mode")[-1] == (500, 40)
    drv.set_random_track([(10, 20), (40, 60)])
    assert _named(cam, "setup_random_track_mode")[-1] == ([(9, 20), (39, 60)],)
    assert drv.set_multi_track(2, 5, 0) == (andor_mod.DRV_SUCCESS, 3, 7)


def test_read_mode_codes_map_to_pylablib_names():
    drv, cam = _adapter()
    drv.set_read_mode(andor_mod.READ_MODE_FVB)
    drv.set_read_mode(andor_mod.READ_MODE_IMAGE)
    assert _named(cam, "set_read_mode") == [("fvb",), ("image",)]
    drv.set_read_mode(andor_mod.READ_MODE_SINGLE_TRACK)
    assert _named(cam, "setup_single_track_mode")[-1] == (500, 40)
    assert drv.get_read_mode() == andor_mod.READ_MODE_SINGLE_TRACK


def test_pylablib_errors_become_sdk_codes():
    drv, cam = _adapter()

    def _boom(name):
        raise _LibError(20072)
    cam.set_fan_mode = _boom
    assert drv.set_fan_mode(andor_mod.FAN_MODE_LOW) == 20072


# ── Estado base (paso 8) sobre pylablib ───────────────────────────────────────────────────────

def test_camera_baseline_through_pylablib():
    drv, cam = _adapter()
    rep = apply_camera_baseline(drv)
    assert not rep.blocks_acquisition, rep.summary()
    assert _named(cam, "set_fan_mode") == [("low",)]
    assert _named(cam, "set_temperature") == [(-60, True)]
    assert _named(cam, "set_vsspeed") == [(2,)]            # 1.9 µs, el índice del legado
    assert cam.hsspeed == 2 and cam.preamp == 0            # 13 MHz por valor; pre-amp 0
    assert _named(cam, "set_EMCCD_gain") == [(0,)]
    assert rep.item("em_gain").outcome == "OK" and rep.item("cooler_on").outcome == "OK"


# ── Una exposición = un cuadro nuevo (paso 6) sobre pylablib ──────────────────────────────────

def test_single_exposure_through_pylablib_waits_and_restores_continuous_mode():
    drv, cam = _adapter()
    t0 = time.monotonic()
    out = single_exposure(drv, ExposureRequest(0.3, (1004,)), is_estopped=lambda: False)
    assert isinstance(out, Frame), out
    assert time.monotonic() - t0 >= 0.29
    assert out.data.shape == (1004,) and out.data[-1] == 1003
    modes = [c[1] for c in cam.calls if c[0] == "setup_acquisition"]
    assert modes[0] == "single" and modes[-1] == "cont", "el Live espera la adquisición continua"
    assert cam.acquiring is False


def test_single_exposure_through_pylablib_times_out_and_stops():
    drv, cam = _adapter(finishes=False)
    ticks = []
    out = single_exposure(drv, ExposureRequest(0.2, (1004,)), on_tick=lambda: ticks.append(1),
                          is_estopped=lambda: False, tranche_ms=100, readout_margin_s=0.2)
    assert isinstance(out, AcquisitionFailure) and out.kind is AcquisitionFailureKind.TIMEOUT
    assert len(ticks) >= 3 and cam.acquiring is False


def test_single_exposure_through_pylablib_stop_and_estop():
    drv, cam = _adapter()
    stop_at = time.monotonic() + 0.15
    out = single_exposure(drv, ExposureRequest(5.0, (1004,)), should_abort=lambda: time.monotonic() >= stop_at,
                          is_estopped=lambda: False, tranche_ms=100)
    assert out.kind is AcquisitionFailureKind.USER_STOP and cam.acquiring is False
    out = single_exposure(drv, ExposureRequest(5.0, (1004,)), is_estopped=lambda: True, tranche_ms=50)
    assert out.kind is AcquisitionFailureKind.ESTOP


def test_single_exposure_through_pylablib_rejects_a_wrong_size_frame():
    drv, cam = _adapter(frame=np.zeros((1, 10)))
    out = single_exposure(drv, ExposureRequest(0.05, (1004,)), is_estopped=lambda: False)
    assert isinstance(out, AcquisitionFailure) and out.kind is AcquisitionFailureKind.SIZE_MISMATCH


# ── Live: sin cuadro todavía no es una falla, y nunca se inventan ceros ──────────────────────

def test_live_skips_the_tick_while_no_frame_exists():
    from pyspectrum.drivers.shamrock_driver import _MockShamrock
    from pyspectrum.ui.exploration_tab import ExplorationWorker
    drv, cam = _adapter()
    with pytest.raises(pl_mod.FrameNotReady):
        drv.get_most_recent_image()
    worker = ExplorationWorker(drv, spectrometer=_MockShamrock())
    frames, errors = [], []
    worker.imageUpdatedSignal.connect(frames.append)
    worker.liveErrorSignal.connect(errors.append)
    worker._acquire_frame()
    assert frames == [] and errors == []


def test_installed_pylablib_is_the_bench_version():
    pylablib = pytest.importorskip("pylablib")
    assert pylablib.__version__ == "1.4.3", "el banco usa pylablib 1.4.3 (R4-F)"


# ── Temperatura durante la adquisición (banco, 2026-09-28) ────────────────────
# Con el Live del legado encendido, pylablib informó
# "function 'GetTemperatureF' raised error 20072(DRV_ACQUIRING)": el SDK no lee la temperatura
# mientras la cámara adquiere. La interfaz devuelve la ÚLTIMA lectura marcada con DRV_ACQUIRING,
# para que la GUI la muestre como vieja, nunca como actual ni como "Estabilizado".

def _busy():
    raise _LibError(andor_mod.DRV_ACQUIRING)


def test_temperature_while_acquiring_returns_last_reading_marked_stale():
    drv, cam = _adapter()
    assert drv.get_temperature() == (andor_mod.DRV_TEMP_STABILIZED, -60.0)
    cam.get_temperature = _busy
    assert drv.get_temperature() == (andor_mod.DRV_ACQUIRING, -60.0)


def test_temperature_while_acquiring_without_previous_reading_is_nan():
    drv, cam = _adapter()
    cam.get_temperature = _busy
    ret, t = drv.get_temperature()
    assert ret == andor_mod.DRV_ACQUIRING and np.isnan(t)


class _TempOnlyCam:
    def __init__(self, reading): self.reading = reading
    def get_temperature(self): return self.reading


def test_left_panel_shows_stale_temperature_while_acquiring():
    from pyspectrum.drivers.shamrock_driver import get_shamrock
    from pyspectrum.ui.left_hardware_panel import LeftHardwarePanel
    panel = LeftHardwarePanel(andor_mod.get_andor_ccd(force_mock=True), get_shamrock(force_mock=True))
    panel.camera = _TempOnlyCam((andor_mod.DRV_ACQUIRING, -60.0))
    panel._refresh_status()
    text = panel.lbl_temp_badge.text()
    assert "-60.0" in text and "adquiriendo" in text
    assert "Estabilizado" not in text and "Enfriando" not in text
    panel.camera = _TempOnlyCam((andor_mod.DRV_ACQUIRING, float("nan")))
    panel._refresh_status()
    assert "nan" not in panel.lbl_temp_badge.text()


def test_camera_frontend_never_calls_a_stale_reading_stabilized():
    from pyspectrum.modules.camera_andor import Frontend
    fe = Frontend()
    fe.update_temperature(float(fe.spin_temp.value()), andor_mod.DRV_ACQUIRING)
    assert "Estabilizado" not in fe.lbl_temp.text() and "adquiriendo" in fe.lbl_temp.text()
