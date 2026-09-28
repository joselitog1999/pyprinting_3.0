# -*- coding: utf-8 -*-
"""Servicio de orden cero, el "espejo rápido" (paso 7 del bloque A, DEC-040).

Contrato (R2-inst §2.2-2.4, reconciliado en la Ronda 4 con D-06, D-07a, D-08 y D-18):
- `enter_specular(target, restart_live)` recorre Z1-Z9, cada paso con su retorno verificado. Si un paso
  falla, **no se mueve la red** y el resultado dice qué paso, con qué código y en qué estado quedó cada
  recurso (H-12).
- Z5 no acota la exposición: fija la exposición recordada del modo especular. La primera de la sesión es
  `SPECULAR_DEFAULT_EXPOSURE_S` (D-18, R4-D-2).
- Z6 cierra todos los obturadores y exige la confirmación (R4-B-3, DEC-036).
- Al volver, la exposición de primer orden se restituye sola; la ganancia EM **no** (R4-B-4, H-13).
- El Live se reanuda sólo si la ganancia 0 quedó confirmada (H-12).
Todo contra los simuladores, con el obturador y la sesión inyectados.
"""
import pytest

import config
from pyspectrum.drivers import specular_interlock as si
from pyspectrum.drivers.andor_ccd_driver import DRV_ACQUIRING, DRV_SUCCESS, get_andor_ccd
from pyspectrum.drivers.shamrock_driver import (
    DEVICE, GRATING_150_LINES, GRATING_1200_LINES, GRATING_MIRROR, SHAMROCK_SUCCESS, get_shamrock,
)
from pyspectrum.modules.hardware_session import HardwareSessionManager
from pyspectrum.modules.zero_order_service import ZeroOrderService


class _Shutters:
    def __init__(self, open_names=(), close_ok=True, high_power=False):
        self.open = list(open_names)
        self.close_ok = close_ok
        self.high_power = high_power
        self.close_calls = 0

    def close_all(self):
        self.close_calls += 1
        if self.close_ok:
            self.open = []
        return self.close_ok

    def names(self):
        return list(self.open)


class _Live:
    def __init__(self, session):
        self.paused = self.resumed = 0
        session.register_live_controller("Exploración", self._pause, self._resume)

    def _pause(self): self.paused += 1
    def _resume(self): self.resumed += 1


@pytest.fixture
def rig():
    cam = get_andor_ccd(force_mock=True)
    spec = get_shamrock(force_mock=True)
    cam.abort_acquisition()
    cam.set_exposure_time(0.05)
    cam.set_emccd_gain(150)
    session = HardwareSessionManager()
    live = _Live(session)
    shutters = _Shutters(open_names=["532"])
    svc = ZeroOrderService(cam, spec, session=session, close_all_shutters=shutters.close_all,
                           get_open_shutter_names=shutters.names,
                           is_flipper_high_power=lambda: shutters.high_power, sleep=lambda s: None)
    return svc, cam, spec, session, live, shutters


def _gain(cam):
    g = cam.get_emccd_gain()
    return g[1] if isinstance(g, tuple) else g


# ── Entrada ───────────────────────────────────────────────────────────────────

def test_enter_zero_order_runs_the_full_sequence(rig):
    svc, cam, spec, session, live, shutters = rig
    cam.start_acquisition()                                  # el Live estaba adquiriendo
    res = svc.enter_specular("zero_order")
    assert res.ok, res.detail
    assert [s.key for s in res.steps] == ["session", "camera_idle", "gain_zero", "gain_confirm",
                                          "exposure", "shutters", "move", "readback"]
    assert spec.ShamrockGetWavelength(DEVICE)[1] == pytest.approx(0.0)
    assert si.get_interlock().mode == si.SPECULAR
    assert _gain(cam) == 0 and res.gain_confirmed == 0
    assert cam.get_exposure_time() == pytest.approx(config.SPECULAR_DEFAULT_EXPOSURE_S)
    assert res.exposure_real_s == pytest.approx(config.SPECULAR_DEFAULT_EXPOSURE_S)
    assert res.shutters_closed and shutters.open == []
    assert live.paused == 1 and live.resumed == 1
    assert not session.is_busy
    assert svc.return_target == (GRATING_150_LINES, pytest.approx(532.0))
    assert svc.gain_before_specular == 150
    assert svc.exposure_by_mode["first_order"] == pytest.approx(0.05)


def test_enter_without_restart_live_leaves_live_paused(rig):
    svc, cam, spec, session, live, shutters = rig
    assert svc.enter_specular("zero_order", restart_live=False).ok
    assert live.paused == 1 and live.resumed == 0


def test_mirror_target_selects_turret_position_3(rig):
    svc, cam, spec, *_ = rig
    res = svc.enter_specular("mirror")
    assert res.ok, res.detail
    assert spec.ShamrockGetGrating(DEVICE)[1] == GRATING_MIRROR
    assert si.get_interlock().mode == si.SPECULAR


def test_wavelength_target_below_threshold_is_entered_through_the_service(rig):
    svc, cam, spec, *_ = rig
    res = svc.enter_specular("wavelength", grating=GRATING_150_LINES, wavelength_nm=40.0)
    assert res.ok, res.detail
    assert spec.ShamrockGetWavelength(DEVICE)[1] == pytest.approx(40.0)
    assert si.get_interlock().mode == si.SPECULAR


def test_wavelength_target_with_grating_change(rig):
    svc, cam, spec, *_ = rig
    res = svc.enter_specular("wavelength", grating=GRATING_1200_LINES, wavelength_nm=5.0)
    assert res.ok, res.detail
    assert spec.ShamrockGetGrating(DEVICE)[1] == GRATING_1200_LINES
    assert spec.ShamrockGetWavelength(DEVICE)[1] == pytest.approx(5.0)
    assert si.get_interlock().mode == si.SPECULAR


# ── Fallas: la red no se mueve ────────────────────────────────────────────────

def _not_moved(spec):
    return (spec.ShamrockGetGrating(DEVICE)[1] == GRATING_150_LINES
            and spec.ShamrockGetWavelength(DEVICE)[1] == pytest.approx(532.0))


def test_gain_readback_not_zero_aborts_before_moving(rig, monkeypatch):
    svc, cam, spec, session, live, shutters = rig
    monkeypatch.setattr(cam, "get_emccd_gain", lambda: 12)
    res = svc.enter_specular("zero_order")
    assert not res.ok and res.step_failed == "gain_confirm"
    assert "12" in res.detail
    assert _not_moved(spec)
    assert shutters.close_calls == 0                          # Z6 va después
    assert live.resumed == 0                                  # ganancia sin confirmar: el Live no vuelve
    assert not session.is_busy
    assert res.final_state["red"] == "no se movió"
    assert res.final_state["ganancia"] == "desconocida"
    assert "532" in res.final_state["obturadores"]


def test_camera_that_does_not_stop_aborts(rig, monkeypatch):
    svc, cam, spec, session, live, shutters = rig
    cam.set_acquisition_mode(5)      # continua (run till abort): un single scan terminaría solo
    cam.start_acquisition()
    monkeypatch.setattr(cam, "abort_acquisition", lambda: DRV_SUCCESS)   # no la detiene
    res = svc.enter_specular("zero_order")
    assert not res.ok and res.step_failed == "camera_idle"
    assert _not_moved(spec) and _gain(cam) == 150


def test_unconfirmed_shutter_close_aborts(rig):
    svc, cam, spec, session, live, shutters = rig
    shutters.close_ok = False
    res = svc.enter_specular("zero_order")
    assert not res.ok and res.step_failed == "shutters"
    assert _not_moved(spec)
    assert live.resumed == 1                                  # ganancia 0 confirmada: el Live puede volver


def test_busy_session_touches_nothing(rig):
    svc, cam, spec, session, live, shutters = rig
    assert session.acquire_session("Step & Glue", auto_pause_live=False)
    res = svc.enter_specular("zero_order")
    assert not res.ok and res.step_failed == "session"
    assert _not_moved(spec) and _gain(cam) == 150 and live.paused == 0
    assert session.current_owner == "Step & Glue"


def test_emergency_stop_active_refuses(rig):
    svc, cam, spec, session, live, shutters = rig
    session._emergency_active = True
    res = svc.enter_specular("zero_order")
    assert not res.ok and res.step_failed == "session"
    assert _not_moved(spec)


def test_failed_move_reports_the_code(rig, monkeypatch):
    svc, cam, spec, *_ = rig
    monkeypatch.setattr(spec, "goto_zero_order", lambda device=DEVICE: 20201)
    res = svc.enter_specular("zero_order")
    assert not res.ok and res.step_failed == "move" and res.code == 20201
    assert _gain(cam) == 0                                    # la ganancia no se restituye


def test_readback_failure_leaves_state_unknown(rig, monkeypatch):
    svc, cam, spec, *_ = rig
    monkeypatch.setattr(spec, "ShamrockGetWavelength", lambda device=DEVICE: (20201, 0.0))
    res = svc.enter_specular("zero_order")
    assert not res.ok and res.step_failed == "readback"
    assert si.get_interlock().mode == si.UNKNOWN              # sigue bloqueando la ganancia


# ── Salida ────────────────────────────────────────────────────────────────────

def test_leave_returns_to_remembered_first_order_and_restores_only_the_exposure(rig):
    svc, cam, spec, session, live, shutters = rig
    assert svc.enter_specular("zero_order").ok
    cam.set_exposure_time(0.3)                                # el operador ajusta en orden cero
    res = svc.leave_specular()
    assert res.ok, res.detail
    assert spec.ShamrockGetGrating(DEVICE)[1] == GRATING_150_LINES
    assert spec.ShamrockGetWavelength(DEVICE)[1] == pytest.approx(532.0)
    assert si.get_interlock().mode == si.FIRST_ORDER
    assert cam.get_exposure_time() == pytest.approx(0.05)     # la de primer orden vuelve sola
    assert _gain(cam) == 0                                    # la ganancia no
    assert svc.exposure_by_mode["specular"] == pytest.approx(0.3)
    assert svc.enter_specular("zero_order").ok                # S-08: la segunda entrada usa 0.3 s
    assert cam.get_exposure_time() == pytest.approx(0.3)


def test_leave_to_an_explicit_first_order_target(rig):
    svc, cam, spec, *_ = rig
    assert svc.enter_specular("mirror").ok
    res = svc.leave_specular(GRATING_1200_LINES, 550.0)
    assert res.ok, res.detail
    assert spec.ShamrockGetGrating(DEVICE)[1] == GRATING_1200_LINES
    assert si.get_interlock().mode == si.FIRST_ORDER


def test_leave_to_a_specular_target_is_refused(rig):
    svc, cam, spec, *_ = rig
    assert svc.enter_specular("zero_order").ok
    res = svc.leave_specular(GRATING_150_LINES, 40.0)
    assert not res.ok and res.step_failed == "target"
    assert si.get_interlock().mode == si.SPECULAR


def test_leave_with_mismatched_readback_keeps_the_gain_locked(rig, monkeypatch):
    svc, cam, spec, *_ = rig
    assert svc.enter_specular("zero_order").ok
    monkeypatch.setattr(spec, "ShamrockGetWavelength", lambda device=DEVICE: (SHAMROCK_SUCCESS, 531.5))
    res = svc.leave_specular()
    assert not res.ok and res.step_failed == "readback"
    assert si.get_interlock().mode == si.UNKNOWN
    assert cam.set_emccd_gain(150) != DRV_SUCCESS


def test_leave_without_remembered_target_asks_for_one(rig):
    svc, cam, spec, *_ = rig
    si.get_interlock().publish(si.SPECULAR, "arrancó en orden cero (Solis)")
    res = svc.leave_specular()
    assert not res.ok and res.step_failed == "target"
    assert "red y λ" in res.detail


def test_move_routes_specular_destinations_through_the_entry_sequence(rig):
    svc, cam, spec, *_ = rig
    res = svc.move(GRATING_150_LINES, 650.0)
    assert res.ok and spec.ShamrockGetWavelength(DEVICE)[1] == pytest.approx(650.0)
    assert "gain_confirm" not in [s.key for s in res.steps]
    res = svc.move(GRATING_150_LINES, 30.0)
    assert res.ok and "gain_confirm" in [s.key for s in res.steps]
    assert si.get_interlock().mode == si.SPECULAR
    res = svc.move(GRATING_150_LINES, 650.0)                  # desde especular: salida protegida
    assert res.ok and si.get_interlock().mode == si.FIRST_ORDER


# ── Informes para la GUI ──────────────────────────────────────────────────────

@pytest.mark.parametrize("peak_frac, level", [(0.30, "ok"), (0.60, "warn"), (0.85, "alarm")])
def test_saturation_scale_without_alarm_fatigue(peak_frac, level):
    import numpy as np
    bias = 500.0
    frame = np.full((10, 10), bias)
    frame[5, 5] = bias + peak_frac * 16383
    frac, lvl = ZeroOrderService.saturation_level(frame, bias=bias)
    assert frac == pytest.approx(peak_frac, abs=1e-3) and lvl == level


def test_light_report_names_open_lasers_and_warns_on_high_power(rig):
    svc, cam, spec, session, live, shutters = rig
    assert svc.enter_specular("zero_order").ok
    shutters.open = ["532"]
    names, warning = svc.specular_light_report()
    assert names == ["532"] and warning is None
    shutters.high_power = True
    names, warning = svc.specular_light_report()
    assert "potencia alta" in warning and "532" in warning     # R4-C-2: se avisa, no se bloquea


def test_gain_restore_needs_notch_confirmation_only_with_a_laser_open(rig):
    svc, cam, spec, session, live, shutters = rig
    assert svc.enter_specular("zero_order").ok
    shutters.open = ["532"]
    assert svc.leave_specular().ok
    assert svc.gain_restore_needs_notch_confirmation()       # H-05
    shutters.open = []
    assert not svc.gain_restore_needs_notch_confirmation()


# ── E-STOP (R2-inst §2.5-5) ───────────────────────────────────────────────────

def test_emergency_stop_zeroes_and_rereads_the_gain(monkeypatch):
    from pyspectrum.modules import hardware_session as hs_mod
    cam = get_andor_ccd(force_mock=True)
    cam.set_emccd_gain(150)
    monkeypatch.setattr(hs_mod, "close_all_shutters", lambda: True)
    mgr = HardwareSessionManager()
    mgr.emergency_stop()
    assert _gain(cam) == 0
    assert si.get_interlock().gain_confirmed_zero()
    assert mgr.last_estop_report["gain"] == "0 releído"
    mgr.clear_emergency()
