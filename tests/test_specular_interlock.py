# -*- coding: utf-8 -*-
"""Interlock especular en los drivers (paso 7 del bloque A, DEC-040).

La red mínima de R2-inst §2.5, que ningún widget, rutina ni script puede esquivar:
- la cámara rechaza ganancia EM > 0 mientras el espectrógrafo esté en condición especular o en
  estado desconocido (falla cerrada, R2-inst §2.1-4);
- el Shamrock rechaza un destino especular si la ganancia 0 no está confirmada por relectura;
- tras un movimiento aceptado, el Shamrock publica la condición del destino.

Umbral especular (D-07a): (1 + SPECULAR_MARGIN_FRAC) · W/2, con W la ventana nominal de la red
(dispersión de la hoja de datos × 1004 px × 8 µm): 56.7 nm con 150 l/mm y 6.4 nm con 1200 l/mm.
La red 3 de la torreta es un espejo (leído del equipo el 2026-09-28, BANCO-25): siempre especular.
"""
import math

import pytest

import config
from pyspectrum.drivers import andor_ccd_driver as andor_mod
from pyspectrum.drivers import andor_pylablib as pl_mod
from pyspectrum.drivers import shamrock_driver as sh_mod
from pyspectrum.drivers import specular_interlock as si
from pyspectrum.drivers.andor_ccd_driver import DRV_P1INVALID, DRV_SUCCESS
from pyspectrum.drivers.shamrock_driver import (
    DEVICE, GRATING_1200_LINES, GRATING_150_LINES, GRATING_MIRROR, SHAMROCK_P2INVALID, SHAMROCK_SUCCESS,
)


# ── Umbral y clasificación (funciones puras) ──────────────────────────────────

def test_margin_is_a_single_config_symbol():
    assert config.SPECULAR_MARGIN_FRAC == pytest.approx(0.10)


def test_threshold_follows_the_reconciled_formula():
    w150 = sh_mod.nominal_window_nm(GRATING_150_LINES)
    w1200 = sh_mod.nominal_window_nm(GRATING_1200_LINES)
    assert si.specular_threshold_nm(GRATING_150_LINES) == pytest.approx(1.1 * w150 / 2)
    assert si.specular_threshold_nm(GRATING_150_LINES) == pytest.approx(56.7, abs=0.05)
    assert si.specular_threshold_nm(GRATING_1200_LINES) == pytest.approx(6.4, abs=0.05)
    assert math.isinf(si.specular_threshold_nm(GRATING_MIRROR))


@pytest.mark.parametrize("grating, wl, expected", [
    (GRATING_150_LINES, 532.0, si.FIRST_ORDER),
    (GRATING_150_LINES, 56.8, si.FIRST_ORDER),
    (GRATING_150_LINES, 56.6, si.SPECULAR),
    (GRATING_150_LINES, 40.0, si.SPECULAR),
    (GRATING_150_LINES, 0.0, si.SPECULAR),
    (GRATING_150_LINES, -40.0, si.SPECULAR),
    (GRATING_1200_LINES, 7.0, si.FIRST_ORDER),
    (GRATING_1200_LINES, 6.0, si.SPECULAR),
    (GRATING_MIRROR, 532.0, si.SPECULAR),
    (None, 532.0, si.UNKNOWN),
    (GRATING_150_LINES, None, si.UNKNOWN),
    (GRATING_150_LINES, float("nan"), si.UNKNOWN),
    (7, 532.0, si.UNKNOWN),
])
def test_classify(grating, wl, expected):
    assert si.classify(grating, wl) == expected


def test_classify_reading_treats_failed_reads_as_unknown():
    assert si.classify_reading((SHAMROCK_SUCCESS, 1), (SHAMROCK_SUCCESS, 532.0)) == si.FIRST_ORDER
    assert si.classify_reading((20201, 1), (SHAMROCK_SUCCESS, 532.0)) == si.UNKNOWN
    assert si.classify_reading((SHAMROCK_SUCCESS, 1), (20201, 532.0)) == si.UNKNOWN
    assert si.classify_reading((SHAMROCK_SUCCESS, 1), (SHAMROCK_SUCCESS, 532.0), at_zero_order=(SHAMROCK_SUCCESS, 1)) == si.SPECULAR


# ── Estado compartido ─────────────────────────────────────────────────────────

class _Clock:
    def __init__(self): self.t = 100.0
    def __call__(self): return self.t


def test_fresh_interlock_is_unknown_and_refuses_gain():
    lock = si.SpecularInterlock()
    assert lock.mode == si.UNKNOWN and lock.is_specular_or_unknown()
    assert not lock.gain_allowed(1)
    assert lock.gain_allowed(0)


def test_first_order_allows_gain_and_specular_refuses_it():
    lock = si.SpecularInterlock()
    lock.publish(si.FIRST_ORDER, "prueba")
    assert lock.gain_allowed(150)
    lock.publish(si.SPECULAR, "prueba")
    assert not lock.gain_allowed(150) and lock.gain_allowed(0)


def test_gain_zero_confirmation_needs_a_successful_readback_of_zero():
    clock = _Clock()
    lock = si.SpecularInterlock(clock=clock)
    assert not lock.gain_confirmed_zero()
    lock.note_gain_reading(DRV_SUCCESS, 12)
    assert not lock.gain_confirmed_zero()
    lock.note_gain_reading(20013, 0)          # lectura fallida: ganancia desconocida
    assert not lock.gain_confirmed_zero()
    lock.note_gain_reading(DRV_SUCCESS, 0)
    assert lock.gain_confirmed_zero()


def test_gain_zero_confirmation_expires_and_is_voided_by_a_gain_increase():
    clock = _Clock()
    lock = si.SpecularInterlock(clock=clock)
    lock.note_gain_reading(DRV_SUCCESS, 0)
    clock.t += si.GAIN_ZERO_CONFIRMATION_MAX_AGE_S + 0.1
    assert not lock.gain_confirmed_zero()
    lock.note_gain_reading(DRV_SUCCESS, 0)
    lock.note_gain_set(DRV_SUCCESS, 50)
    assert not lock.gain_confirmed_zero()


def test_specular_move_allowed_only_with_confirmed_zero_or_lock_armed():
    lock = si.SpecularInterlock()
    lock.publish(si.FIRST_ORDER, "prueba")
    assert lock.move_allowed(si.FIRST_ORDER)
    assert not lock.move_allowed(si.SPECULAR)
    assert not lock.move_allowed(si.UNKNOWN)
    lock.note_gain_reading(DRV_SUCCESS, 0)
    assert lock.move_allowed(si.SPECULAR)
    other = si.SpecularInterlock()
    other.publish(si.SPECULAR, "ya armado")   # la ganancia ya está bloqueada en 0
    assert other.move_allowed(si.SPECULAR)


# ── La cámara: los tres backends ──────────────────────────────────────────────

def test_mock_camera_refuses_gain_in_specular():
    cam = andor_mod.get_andor_ccd(force_mock=True)
    si.get_interlock().publish(si.SPECULAR, "prueba")
    assert cam.set_emccd_gain(50) == DRV_P1INVALID
    assert cam.set_emccd_gain(0) == DRV_SUCCESS
    si.get_interlock().publish(si.FIRST_ORDER, "prueba")
    assert cam.set_emccd_gain(50) == DRV_SUCCESS


def test_mock_camera_readback_feeds_the_interlock():
    cam = andor_mod.get_andor_ccd(force_mock=True)
    si.get_interlock().publish(si.FIRST_ORDER, "prueba")
    cam.set_emccd_gain(0)
    cam.get_emccd_gain()
    assert si.get_interlock().gain_confirmed_zero()
    cam.set_emccd_gain(30)
    assert not si.get_interlock().gain_confirmed_zero()


class _PlCam:
    def __init__(self): self.calls, self.gain = [], 0
    def set_EMCCD_gain(self, g, advanced=None): self.calls.append(g); self.gain = g
    def get_EMCCD_gain(self): return (self.gain, False)


def test_pylablib_camera_refuses_gain_in_specular_without_calling_pylablib():
    fake = _PlCam()
    drv = pl_mod.PylablibAndorCCD(camera_factory=lambda: fake, lib_factory=lambda: None)
    assert drv.initialize()
    si.get_interlock().publish(si.UNKNOWN, "prueba")
    assert drv.set_emccd_gain(50) == DRV_P1INVALID
    assert fake.calls == []
    assert drv.set_emccd_gain(0) == DRV_SUCCESS and fake.calls == [0]
    assert drv.get_emccd_gain() == (DRV_SUCCESS, 0)
    assert si.get_interlock().gain_confirmed_zero()


class _Dll:
    def __init__(self): self.calls = []
    def SetEMCCDGain(self, g): self.calls.append(g.value); return DRV_SUCCESS


def test_ctypes_camera_refuses_gain_in_specular_without_calling_the_dll():
    import threading
    drv = andor_mod.AndorCCDDriver.__new__(andor_mod.AndorCCDDriver)   # sin DLL real
    drv._lock, drv._connected, drv._dll, drv._current_exposure_time = threading.RLock(), True, _Dll(), 0.05
    si.get_interlock().publish(si.SPECULAR, "prueba")
    assert drv.set_emccd_gain(50) == DRV_P1INVALID
    assert drv._dll.calls == []
    si.get_interlock().publish(si.FIRST_ORDER, "prueba")
    assert drv.set_emccd_gain(50) == DRV_SUCCESS and drv._dll.calls == [50]


# ── El Shamrock (simulador) ───────────────────────────────────────────────────

@pytest.fixture
def spec():
    s = sh_mod.get_shamrock(force_mock=True)
    s.ShamrockSetGrating(DEVICE, GRATING_150_LINES)
    s.ShamrockSetWavelength(DEVICE, 532.0)
    si.get_interlock().publish(si.FIRST_ORDER, "prueba")
    return s


def test_zero_order_refused_without_confirmed_zero_gain(spec):
    assert spec.goto_zero_order(DEVICE) == SHAMROCK_P2INVALID
    assert spec.ShamrockGetWavelength(DEVICE)[1] == pytest.approx(532.0)
    assert si.get_interlock().mode == si.FIRST_ORDER


def test_zero_order_accepted_with_confirmed_zero_gain_publishes_specular(spec):
    si.get_interlock().note_gain_reading(DRV_SUCCESS, 0)
    assert spec.goto_zero_order(DEVICE) == SHAMROCK_SUCCESS
    assert si.get_interlock().mode == si.SPECULAR


def test_low_wavelength_and_mirror_grating_are_specular_destinations(spec):
    assert spec.ShamrockSetWavelength(DEVICE, 40.0) == SHAMROCK_P2INVALID
    assert spec.ShamrockSetGrating(DEVICE, GRATING_MIRROR) == SHAMROCK_P2INVALID
    assert spec.ShamrockGetGrating(DEVICE)[1] == GRATING_150_LINES
    assert spec.ShamrockSetWavelength(DEVICE, 650.0) == SHAMROCK_SUCCESS


def test_leaving_specular_to_first_order_is_allowed_and_publishes_it(spec):
    si.get_interlock().note_gain_reading(DRV_SUCCESS, 0)
    assert spec.goto_zero_order(DEVICE) == SHAMROCK_SUCCESS
    assert spec.ShamrockSetWavelength(DEVICE, 532.0) == SHAMROCK_SUCCESS
    assert si.get_interlock().mode == si.FIRST_ORDER


def test_grating_change_is_classified_with_the_current_wavelength(spec):
    si.get_interlock().note_gain_reading(DRV_SUCCESS, 0)
    assert spec.ShamrockSetWavelength(DEVICE, 40.0) == SHAMROCK_SUCCESS   # especular con 150
    si.get_interlock().publish(si.SPECULAR, "prueba")
    assert spec.ShamrockSetWavelength(DEVICE, 60.0) == SHAMROCK_SUCCESS   # primer orden con 150
    assert si.get_interlock().mode == si.FIRST_ORDER
    assert spec.ShamrockSetGrating(DEVICE, GRATING_1200_LINES) == SHAMROCK_SUCCESS  # 60 nm ≥ 6.4
    assert si.get_interlock().mode == si.FIRST_ORDER
