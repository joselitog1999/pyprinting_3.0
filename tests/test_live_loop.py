# -*- coding: utf-8 -*-
"""El lazo del Live sobre pylablib (paquete 1 de la revisión con pyLabLib-cam-control, R4-M; DEC-040).

Contrato aprobado en la Ronda 2 (2026-09-30):
- A1: el Live arranca siempre en adquisición continua ("cont"). El estado base deja "single" y el Live
  se congelaba en el primer cuadro.
- A2/A5: `read_live_frame` lee sólo el cuadro más nuevo, avanza el puntero y trae el índice de pylablib;
  separa los cuadros que no se mostraron de los que pisó el búfer.
- A3: buzón con el último cuadro y un solo aviso pendiente; la interfaz pinta cada 50 ms como máximo y
  sólo si el visor se ve.
- A4: exposición, preamplificador y velocidades HS y VS se aplican durante el Live con
  `pausing_acquisition`. Lo que cambia la forma del cuadro y el amplificador se rechazan con el Live
  activo (R4-M, pregunta 2).
- A7: estadísticas una vez por segundo.
- La pausa por una rutina es sincrónica (`halt_now`): cuando `acquire_session` vuelve, la cámara ya se
  detuvo y el obturador del espectrómetro ya se cerró; un sondeo tardío no hace nada.
- `acquire_single` deja la exposición como la encontró, también cuando falla (pregunta 1).

La cámara falsa imita la API de pylablib 1.4.3 que se usa, verificada en su fuente: el contador de cuadros
(`get_new_images_range`, `read_multiple_images`, `get_frames_status`), `pausing_acquisition` y que el SDK
rechaza `SetExposureTime` y el cambio de amplificador mientras adquiere.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYPRINTING_SAFE", "1")

import threading
from collections import namedtuple
from contextlib import contextmanager

import numpy as np
import pytest
from PyQt6.QtWidgets import QApplication

from pyspectrum.drivers import andor_pylablib as pl_mod
from pyspectrum.drivers.andor_ccd_driver import (
    DRV_ACQUIRING, DRV_SUCCESS, READ_MODE_FVB, READ_MODE_IMAGE, get_andor_ccd,
)
from pyspectrum.drivers.live_stream import LiveFrame, LiveStopped, live_api
from pyspectrum.modules.acquisition import AcquisitionFailure, ExposureRequest, Frame

_app = QApplication.instance() or QApplication(["pytest"])

TFrameInfo = namedtuple("TFrameInfo", ["frame_index"])
TFramesStatus = namedtuple("TFramesStatus", ["acquired", "unread", "skipped", "buffer_size"])
TAmp = namedtuple("TAmp", "channel channel_bitdepth oamp oamp_kind hsspeed hsspeed_MHz preamp preamp_gain")


class _LibError(Exception):
    def __init__(self, code):
        super().__init__(f"error {code}")
        self.code = code


class _StreamCam:
    """Cámara falsa con el contador de cuadros de pylablib (interface/camera.py, FrameCounter)."""

    class TimeoutError(Exception):
        pass

    def __init__(self, *, buffer_size=8, shape=(4, 5)):
        self.calls = []
        self.mode, self.acquiring = "single", False
        self.exposure = 0.05
        self.buffer_size, self.shape = buffer_size, shape
        self._reset()
        self.hsspeed = self.preamp = self.oamp = self.vsspeed = 0
        self.fail_read = None

    def _reset(self):
        self.acquired, self.last_read, self.skipped = 0, -1, 0

    def _log(self, *a):
        self.calls.append(a)

    # conexión y lecturas simples
    def is_opened(self): return True
    def close(self): self._log("close")
    def get_status(self): return "acquiring" if self.acquiring else "idle"
    def acquisition_in_progress(self): return self.acquiring
    def get_exposure(self): return self.exposure

    # parámetros que el SDK rechaza mientras adquiere (DRV_ACQUIRING)
    def _reject_if_acquiring(self):
        if self.acquiring:
            self._log("rejected")                    # el pedido llegó a la cámara y el SDK lo rechazó
            raise _LibError(DRV_ACQUIRING)

    def set_exposure(self, e):
        self._reject_if_acquiring()
        self._log("set_exposure", e)
        self.exposure = float(e)
        return e

    def get_all_amp_modes(self):
        return [TAmp(0, 14, 0, "Electron Multiplying", i, mhz, p, g)
                for i, mhz in enumerate((17.0, 10.0, 5.0)) for p, g in enumerate((1.0, 2.4, 4.9))]
    def get_oamp(self): return self.oamp
    def get_hsspeed(self): return self.hsspeed
    def get_preamp(self): return self.preamp

    def set_amp_mode(self, channel=None, oamp=None, hsspeed=None, preamp=None):
        self._reject_if_acquiring()
        self._log("set_amp_mode", dict(oamp=oamp, hsspeed=hsspeed, preamp=preamp))
        self.oamp = self.oamp if oamp is None else oamp
        self.hsspeed = self.hsspeed if hsspeed is None else hsspeed
        self.preamp = self.preamp if preamp is None else preamp

    def set_vsspeed(self, i):
        self._reject_if_acquiring()
        self._log("set_vsspeed", i)
        self.vsspeed = i

    # pylablib pausa sola estos (@acqstopped): el driver los rechaza antes con el Live activo
    def set_read_mode(self, name): self._log("set_read_mode", name)
    def setup_single_track_mode(self, center=0, width=1): self._log("setup_single_track_mode", center, width)
    def setup_image_mode(self, *a): self._log("setup_image_mode", *a)
    def setup_shutter(self, mode, ttl_mode=0, open_time=None, close_time=None): self._log("setup_shutter", mode)

    # adquisición
    def setup_acquisition(self, mode=None):
        self._log("setup_acquisition", mode)
        self.mode = mode

    def start_acquisition(self):
        self._log("start_acquisition", self.mode)
        self._reset()
        self.acquiring = True

    def stop_acquisition(self):
        self._log("stop_acquisition")
        self.acquiring = False

    @contextmanager
    def pausing_acquisition(self, clear=None, stop=True, setup_after=None, start_after=True):
        was = self.acquiring
        self._log("pause")
        self.stop_acquisition()
        try:
            yield was, {"mode": self.mode}
        finally:
            if was:
                self.start_acquisition()

    def produce(self, n=1):
        """Llegan n cuadros. En "single" la cámara se detiene después del primero, como el SDK."""
        for _ in range(n):
            if not self.acquiring:
                return
            self.acquired += 1
            if self.mode == "single":
                self.acquiring = False

    def _oldest_valid(self):
        return max(0, self.acquired - self.buffer_size)

    def get_new_images_range(self):
        first = max(self.last_read + 1, self._oldest_valid())
        return (first, self.acquired) if self.acquired > first else None

    def read_multiple_images(self, rng=None, peek=False, missing_frame="skip", return_info=False):
        if self.fail_read is not None:
            raise self.fail_read
        lo = max(rng[0], self._oldest_valid())
        frames = [np.full(self.shape, float(i)) for i in range(lo, rng[1])]
        if not peek:
            self.skipped += max(lo - 1 - self.last_read, 0)
            self.last_read = max(self.last_read, rng[1] - 1)
        info = [TFrameInfo(i) for i in range(lo, rng[1])]
        return (frames, info) if return_info else frames

    def get_frames_status(self):
        full_unread = self.acquired - 1 - self.last_read
        unread = min(full_unread, self.buffer_size)
        return TFramesStatus(self.acquired, unread, self.skipped + (full_unread - unread), self.buffer_size)

    # un cuadro (acquire_single)
    def wait_for_frame(self, timeout=20.0):
        self.produce(1)

    def read_oldest_image(self):
        rng = self.get_new_images_range()
        if rng is None:
            return None
        frames = self.read_multiple_images(rng=(rng[0], rng[0] + 1))
        return frames[0] if frames else None


def _driver(**kw):
    cam = _StreamCam(**kw)
    drv = pl_mod.PylablibAndorCCD(camera_factory=lambda: cam)
    assert drv.initialize()
    return drv, cam


def _named(cam, name):
    return [c[1:] for c in cam.calls if c[0] == name]


# ── A1: el Live arranca en continuo aunque el estado base haya dejado "single" ──────────────

def test_live_from_cold_start_uses_cont_and_keeps_delivering_new_frames():
    drv, cam = _driver()
    assert cam.mode == "single"                     # como lo deja el estado base
    assert drv.start_live() == DRV_SUCCESS
    assert cam.mode == "cont" and cam.acquiring and drv.live_active
    seen = []
    for _ in range(3):
        cam.produce(1)
        seen.append(drv.read_live_frame().index)
    assert seen == [0, 1, 2]                         # no se congela en el primer cuadro


def test_start_live_refuses_when_another_live_owns_the_camera():
    drv, cam = _driver()
    assert drv.start_live() == DRV_SUCCESS
    n_starts = len(_named(cam, "start_acquisition"))
    assert drv.start_live() == DRV_ACQUIRING         # pylablib reiniciaría la adquisición en silencio
    assert len(_named(cam, "start_acquisition")) == n_starts


def test_stop_live_stops_only_its_own_acquisition():
    drv, cam = _driver()
    cam.acquiring = True                             # una rutina expone; el Live no está activo
    assert drv.stop_live() == DRV_SUCCESS
    assert cam.acquiring and not _named(cam, "stop_acquisition")
    drv.start_live()
    drv.stop_live()
    assert not cam.acquiring and not drv.live_active


# ── A2/A5: sólo el más nuevo, con índice; sin mostrar vs perdidos ───────────────────────────

def test_read_live_frame_none_without_new_frames_and_stopped_when_not_acquiring():
    drv, cam = _driver()
    with pytest.raises(LiveStopped):
        drv.read_live_frame()                        # el Live no está activo
    drv.start_live()
    assert drv.read_live_frame() is None
    cam.acquiring = False                            # E-STOP o alguien abortó
    with pytest.raises(LiveStopped):
        drv.read_live_frame()
    assert not drv.live_active                       # se libera: los setters vuelven a andar


def test_read_live_frame_never_reads_a_routine_acquisition():
    drv, cam = _driver()
    cam.mode, cam.acquiring = "cont", True           # adquiere una rutina; el Live no está activo
    cam.produce(2)
    with pytest.raises(LiveStopped):
        drv.read_live_frame()
    assert cam.last_read == -1                       # los cuadros siguen siendo de la rutina


def test_read_live_frame_reads_newest_and_counts_not_shown_separately_from_lost():
    drv, cam = _driver(buffer_size=8)
    drv.start_live()
    cam.produce(5)
    lf = drv.read_live_frame()
    assert isinstance(lf, LiveFrame)
    assert lf.index == 4 and float(lf.data[0, 0]) == 4.0
    assert lf.not_shown == 4 and lf.lost_total == 0
    assert lf.data.dtype == np.float32
    cam.produce(1)
    lf = drv.read_live_frame()
    assert lf.index == 5 and lf.not_shown == 0 and lf.lost_total == 0


def test_buffer_overrun_counts_as_lost():
    drv, cam = _driver(buffer_size=4)
    drv.start_live()
    cam.produce(10)                                  # el búfer pisó 6 cuadros sin leer
    lf = drv.read_live_frame()
    assert lf.index == 9
    assert lf.not_shown == 3                         # los 3 que seguían en el búfer
    assert lf.lost_total == 6


def test_buffer_fill_is_unread_over_buffer_size():
    drv, cam = _driver(buffer_size=8)
    drv.start_live()
    cam.produce(1)
    assert drv.read_live_frame().buffer_fill == 0.0


# ── A4: cambios durante el Live ─────────────────────────────────────────────────────────────

def test_exposure_during_live_goes_through_pausing_acquisition():
    drv, cam = _driver()
    drv.start_live()
    assert drv.set_exposure_time(0.2) == DRV_SUCCESS
    assert cam.exposure == 0.2 and cam.acquiring and _named(cam, "pause")
    cam.produce(3)
    lf = drv.read_live_frame()
    assert lf.lost_total == 0                        # el reinicio del contador no se cuenta como pérdida


def test_losses_after_a_live_pause_are_counted_from_the_restart():
    """El reinicio de `pausing_acquisition` pone en cero el contador de pylablib: los "sin mostrar" de
    antes no pueden tapar pérdidas nuevas."""
    drv, cam = _driver(buffer_size=4)
    drv.start_live()
    cam.produce(3)
    assert drv.read_live_frame().not_shown == 2
    drv.set_exposure_time(0.2)
    cam.produce(10)
    lf = drv.read_live_frame()
    assert lf.not_shown == 3 and lf.lost_total == 6


@pytest.mark.parametrize("call,check", [
    (lambda d: d.set_hs_speed(1), lambda c: c.hsspeed == 1),
    (lambda d: d.set_preamp_gain(2), lambda c: c.preamp == 2),
    (lambda d: d.set_vs_speed(1), lambda c: c.vsspeed == 1),
])
def test_speeds_and_preamp_apply_during_live(call, check):
    drv, cam = _driver()
    drv.start_live()
    assert call(drv) == DRV_SUCCESS
    assert check(cam) and cam.acquiring


def test_exposure_during_a_routine_is_still_rejected():
    drv, cam = _driver()
    cam.acquiring = True                             # adquiere una rutina, no el Live
    assert drv.set_exposure_time(0.2) == DRV_ACQUIRING
    assert not _named(cam, "pause")


@pytest.mark.parametrize("call", [
    lambda d: d.set_read_mode(READ_MODE_FVB),
    lambda d: d.set_single_track(500, 20),
    lambda d: d.set_image(1, 1, 1, 1004, 1, 1002),
    lambda d: d.set_output_amplifier(1),
])
def test_shape_changes_and_amplifier_are_refused_while_live(call):
    drv, cam = _driver()
    drv.start_live()
    before = list(cam.calls)
    assert call(drv) == DRV_ACQUIRING
    assert cam.calls == before                       # no llega a pylablib, que pausaría solo
    drv.stop_live()
    assert call(drv) == DRV_SUCCESS


# ── acquire_single: exposición restaurada y nunca con el Live activo ────────────────────────

def _acq(drv, exposure_s=0.3, **kw):
    kw.setdefault("should_abort", lambda: False)
    kw.setdefault("on_tick", lambda: None)
    kw.setdefault("is_estopped", lambda: False)
    return drv.acquire_single(ExposureRequest(exposure_s, (4, 5)), clock=lambda: 0.0, tranche_ms=10,
                              readout_margin_s=1.0, **kw)


def test_acquire_single_restores_the_exposure_it_found():
    drv, cam = _driver()
    drv.set_exposure_time(0.05)
    out = _acq(drv, 0.3)
    assert isinstance(out, Frame)
    assert cam.exposure == 0.05 and drv.get_exposure_time() == 0.05
    assert cam.mode == "cont"


def test_acquire_single_restores_exposure_also_on_failure():
    drv, cam = _driver()
    drv.set_exposure_time(0.05)
    cam.wait_for_frame = lambda timeout=20.0: (_ for _ in ()).throw(cam.TimeoutError())
    out = _acq(drv, 0.3, should_abort=lambda: True)
    assert isinstance(out, AcquisitionFailure)
    assert cam.exposure == 0.05


def test_acquire_single_refuses_while_the_live_flag_is_up_even_if_the_camera_stopped():
    """Si el Live sigue marcado (la cámara se abortó y el worker todavía no lo vio), su próximo sondeo
    leería los cuadros de la rutina: la exposición no arranca."""
    drv, cam = _driver()
    drv.start_live()
    cam.acquiring = False
    out = _acq(drv)
    assert isinstance(out, AcquisitionFailure) and out.kind.value == "not_idle"
    assert not _named(cam, "set_exposure")


def test_acquire_single_refuses_while_live_is_active():
    drv, cam = _driver()
    drv.start_live()
    out = _acq(drv)
    assert isinstance(out, AcquisitionFailure) and out.kind.value == "not_idle"
    assert drv.live_active and cam.acquiring


# ── El adaptador para el simulador y el driver ctypes ───────────────────────────────────────

def test_live_api_adapter_runs_the_mock_in_run_till_abort():
    mock = get_andor_ccd(force_mock=True)
    mock.set_acquisition_mode(1)
    live = live_api(mock)
    assert live is live_api(mock)                    # un solo adaptador por cámara
    assert live.start_live() == DRV_SUCCESS and live.live_active
    lf1, lf2 = live.read_live_frame(), live.read_live_frame()
    assert lf2.index == lf1.index + 1 and lf1.data.ndim == 2
    live.stop_live()
    with pytest.raises(LiveStopped):
        live.read_live_frame()


def test_live_api_returns_the_pylablib_driver_itself():
    drv, _cam = _driver()
    assert live_api(drv) is drv


# ── El worker de Exploración: buzón, visibilidad, estadísticas, pausa sincrónica ────────────

class _Spec:
    def __init__(self):
        self.calls = []

    def ShamrockSetShutter(self, dev, state):
        self.calls.append(state)
        return 20202


class _Session:
    def __init__(self):
        self.busy_nowait = False
        self.estopped_nowait = False


class _Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def _worker(**kw):
    from pyspectrum.ui.exploration_tab import ExplorationWorker
    drv, cam = _driver(**kw)
    spec, sess, clock = _Spec(), _Session(), _Clock()
    w = ExplorationWorker(drv, spectrometer=spec, session=sess, clock=clock)
    return w, drv, cam, spec, sess, clock


def test_worker_mailbox_keeps_latest_and_one_pending_notice():
    w, drv, cam, spec, sess, clock = _worker()
    notices = []
    w.frameReadySignal.connect(lambda: notices.append(1))
    w.start_live()
    assert cam.mode == "cont" and spec.calls == [1]  # obturador abierto
    cam.produce(1); w._poll()
    clock.t += 0.06
    cam.produce(1); w._poll()                       # la interfaz no tomó el anterior: no hay otro aviso
    clock.t += 0.06
    cam.produce(1); w._poll()
    assert len(notices) == 1
    lf = w.take_frame()
    assert lf.index == 2                             # el último, no el primero
    assert w.take_frame() is None
    clock.t += 0.06
    cam.produce(1); w._poll()
    assert len(notices) == 2


def test_worker_notifies_at_most_every_display_period():
    from pyspectrum.ui.exploration_tab import DISPLAY_PERIOD_S
    w, drv, cam, spec, sess, clock = _worker()
    notices = []
    w.frameReadySignal.connect(lambda: notices.append(1))
    w.start_live()
    cam.produce(1); w._poll()
    w.take_frame()
    clock.t += DISPLAY_PERIOD_S / 2
    cam.produce(1); w._poll()
    assert len(notices) == 1                         # demasiado pronto
    clock.t += DISPLAY_PERIOD_S
    w._poll()                                        # sin cuadro nuevo, pero el buzón tiene uno
    assert len(notices) == 2 and w.take_frame().index == 1


def test_worker_does_not_notify_while_hidden_but_keeps_draining():
    w, drv, cam, spec, sess, clock = _worker()
    notices = []
    w.frameReadySignal.connect(lambda: notices.append(1))
    w.set_display_visible(False)
    w.start_live()
    cam.produce(3); w._poll()
    assert notices == [] and cam.last_read == 2      # el puntero avanza igual
    w.set_display_visible(True)
    clock.t += 0.06
    cam.produce(1); w._poll()
    assert len(notices) == 1


def test_worker_stats_once_per_second():
    w, drv, cam, spec, sess, clock = _worker()
    stats = []
    w.statsSignal.connect(stats.append)
    w.start_live()
    for _ in range(8):
        clock.t += 0.125                             # exacto en binario: el octavo sondeo cae en 1 s
        cam.produce(2); w._poll()
        w.take_frame()
    assert len(stats) == 1
    s = stats[0]
    assert s.fps == pytest.approx(16.0)              # 16 cuadros (índices 0 a 15) en 1 s
    assert s.shown_fps == pytest.approx(7.0)         # el octavo se toma después de emitir las estadísticas
    assert s.index == 15 and s.not_shown == 8 and s.lost == 0


def test_worker_fps_survives_a_restart_of_the_frame_counter():
    """Cambiar la exposición durante el Live reinicia la adquisición y el índice vuelve a 0: los fps no
    pueden salir negativos ni saltar."""
    w, drv, cam, spec, sess, clock = _worker()
    stats = []
    w.statsSignal.connect(stats.append)
    w.start_live()
    for k in range(8):
        if k == 4:
            drv.set_exposure_time(0.2)               # pausing_acquisition: el contador vuelve a 0
        clock.t += 0.125
        cam.produce(2); w._poll()
        w.take_frame()
    assert len(stats) == 1 and stats[0].fps == pytest.approx(16.0)


def test_worker_refuses_to_start_during_a_session_or_estop():
    for attr in ("busy_nowait", "estopped_nowait"):
        w, drv, cam, spec, sess, clock = _worker()
        errors = []
        w.liveErrorSignal.connect(errors.append)
        setattr(sess, attr, True)
        w.start_live()
        assert not drv.live_active and not cam.acquiring and spec.calls == [] and errors


def test_halt_now_is_synchronous_and_a_late_poll_does_nothing():
    w, drv, cam, spec, sess, clock = _worker()
    errors = []
    w.liveErrorSignal.connect(errors.append)
    w.start_live()
    assert w.halt_now() is True
    assert not cam.acquiring and not drv.live_active
    assert spec.calls == [1, 0]                      # el obturador ya se cerró al volver
    cam.acquiring, cam.mode = True, "single"         # la rutina empieza a exponer
    cam.produce(0)
    w._poll()                                        # tick tardío
    w.stop_live()                                    # orden del botón que llegó tarde
    assert cam.acquiring and spec.calls == [1, 0] and errors == []
    assert w.halt_now() is False


def test_worker_stops_and_reports_when_camera_stops_acquiring():
    w, drv, cam, spec, sess, clock = _worker()
    errors = []
    w.liveErrorSignal.connect(errors.append)
    w.start_live()
    cam.acquiring = False
    w._poll()
    assert errors and "Live detenido" in errors[0]
    assert spec.calls == [1, 0] and not drv.live_active


def test_worker_stops_on_read_error_instead_of_raising_in_the_timer():
    w, drv, cam, spec, sess, clock = _worker()
    errors = []
    w.liveErrorSignal.connect(errors.append)
    w.start_live()
    cam.produce(1)
    cam.fail_read = _LibError(20013)
    w._poll()
    assert errors and not drv.live_active and not cam.acquiring


def test_halt_now_does_not_deadlock_under_the_session_lock():
    """El E-STOP llama a las pausas con el lock de la sesión tomado; `halt_now` no debe esperar al hilo
    del worker ni a ese lock."""
    from pyspectrum.modules.hardware_session import HardwareSessionManager
    w, drv, cam, spec, sess, clock = _worker()
    w.start_live()
    done = threading.Event()

    def estop_like():
        with HardwareSessionManager._lock:
            w.halt_now()
        done.set()

    t = threading.Thread(target=estop_like, daemon=True)
    t.start()
    assert done.wait(5.0)
    assert not cam.acquiring


# ── La sesión marca "ocupada" antes de pausar los Live ──────────────────────────────────────

def test_acquire_session_is_busy_before_live_pause_callbacks_run():
    from pyspectrum.modules.hardware_session import HardwareSessionManager
    mgr = HardwareSessionManager()
    seen = []
    mgr.register_live_controller("Live CCD", lambda: seen.append(mgr.busy_nowait))
    assert mgr.acquire_session("rutina")
    assert seen == [True]
    assert mgr.busy_nowait and not mgr.estopped_nowait
    mgr.release_session("rutina")
    assert not mgr.busy_nowait


# ── Servicio de control: HS durante el Live se aplica; durante una rutina queda pendiente ───

def test_hs_request_applies_during_live_and_defers_during_routine():
    from pyspectrum.services.camera_control import CameraControlService, ControlState
    from pyspectrum.services.spectrometer_state import SentRegistry
    drv, cam = _driver()
    svc = CameraControlService(drv, sent=SentRegistry())
    drv.start_live()
    res = svc.request_hs_speed_mhz(10.0)
    assert res.state == ControlState.APPLIED and cam.hsspeed == 1
    drv.stop_live()
    cam.acquiring = True                             # una rutina
    res = svc.request_hs_speed_mhz(5.0)
    assert res.state == ControlState.PENDING and cam.hsspeed == 1


# ── Cambio de modo de lectura con el Live activo ────────────────────────────────────────────

def test_transition_read_mode_refuses_while_live_without_aborting():
    from pyspectrum.ui.acquisition_setup_dialog import transition_read_mode
    drv, cam = _driver()
    drv.start_live()
    result = transition_read_mode(drv, READ_MODE_IMAGE)
    assert result.get("refused") and result["applied_mode"] is None
    assert cam.acquiring and drv.live_active         # no abortó el Live
