# -*- coding: utf-8 -*-
"""El fondo en Step & Glue (R4-N; DEC-040).

- Un oscuro por corrida, antes de la primera ventana, con la exposición, el modo de lectura y la forma de las
  ventanas. Sin luz no depende de λc: sirve a todas las ventanas. Se reutiliza si las condiciones no cambian.
- Cada ventana se guarda cruda y referencia el oscuro, que se guarda aparte una vez por corrida (B3).
- El cosido se hace con crudo − oscuro (procesar); "Restar" apagado lo vuelve a coser con el crudo.
- "Todo apagado" sin oscuro válido: el barrido no arranca.
- El sustrato se toma ventana por ventana con un barrido completo (B4) y se resta en la ventana de su misma
  λc; con el sustrato, el oscuro se cancela ((w − d) − (s − d) = w − s). Si el plan no coincide, no se resta.
"""
import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYPRINTING_SAFE", "1")

import numpy as np
import pytest
from PyQt6 import QtWidgets

from pyspectrum.drivers.andor_ccd_driver import READ_MODE_FVB, get_andor_ccd
from pyspectrum.drivers.shamrock_driver import GRATING_150_LINES, get_shamrock
from pyspectrum.modules import step_glue_engine as eng
from pyspectrum.modules.acquisition import Frame
from pyspectrum.modules.hardware_session import hardware_session
from pyspectrum.modules.step_glue_engine import StepGlueRequest, StopReason, plan, run_windows
from pyspectrum.services import procedure_background as pb

_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["pytest"])
_KEEP = []


class _Clock:
    def __init__(self): self.t = 0.0
    def __call__(self): return self.t
    def sleep(self, s): self.t += s


def _req(**kw):
    base = dict(start_nm=500.0, end_nm=900.0, overlap_frac=0.20, exposure_s=0.01, read_mode=READ_MODE_FVB,
                grating=GRATING_150_LINES, em_gain=0, normalize_with_lamp=False, lamp_file=None)
    base.update(kw)
    return StepGlueRequest(**base)


def _frames(monkeypatch, values):
    """Cada exposición devuelve un cuadro constante con el valor siguiente."""
    it = iter(values)
    calls = []

    def fake(cam, req, **kw):
        calls.append(req.shape)
        return Frame(np.full(req.shape, float(next(it))), req.exposure_s, None, 0.0, 0.0)
    monkeypatch.setattr(eng, "single_exposure", fake)
    return calls


@pytest.fixture
def rig(tmp_path):
    cam = get_andor_ccd(force_mock=True)
    cam.abort_acquisition()
    cam.set_read_mode(READ_MODE_FVB)
    return cam, get_shamrock(force_mock=True), tmp_path


def _run(cam, spec, run_dir, req=None, **kw):
    req = req or _req()
    clock = _Clock()
    for k, v in (("should_abort", lambda: False), ("on_tick", lambda: None), ("is_estopped", lambda: False),
                 ("get_open", lambda: []), ("on_no_signal", lambda w: True)):
        kw.setdefault(k, v)
    return run_windows(plan(req, spec), req, cam, spec, run_dir=run_dir, clock=clock, sleep=clock.sleep, **kw)


# ── Motor ───────────────────────────────────────────────────────────────────────────────────

def test_engine_takes_the_dark_once_before_the_windows_and_each_window_references_it(rig, monkeypatch):
    cam, spec, tmp = rig
    n = len(plan(_req(), spec).centers)
    calls = _frames(monkeypatch, [100.0] + [150.0] * n)
    seen = []

    def dark(expose):
        seen.append(len(calls))                             # antes de la primera ventana
        cond = pb.read_conditions(cam, (1004,), exposure_s=0.01, read_mode=READ_MODE_FVB)
        return pb.take_dark(cam, spec, cond, method=pb.METHOD_SHUTTER, n_frames=1, expose=expose,
                            store=pb.DarkStore(), open_lasers=lambda: [])
    res = _run(cam, spec, tmp, dark=dark)
    assert res.complete and seen == [0] and len(calls) == n + 1
    assert res.dark is not None and float(res.dark.mean[0]) == 100.0
    dark_files = list(tmp.glob("StepGlue_background_*.npz"))
    assert len(dark_files) == 1
    for w in res.windows:
        meta = json.loads(np.load(w.path, allow_pickle=False)["metadata"].item())
        assert meta["background_id"] == res.dark.id and meta["background_file"] == dark_files[0].name
        assert float(w.data[0]) == 150.0                    # la ventana se guarda cruda


def test_engine_without_a_dark_stops_before_the_first_window(rig, monkeypatch):
    cam, spec, tmp = rig
    calls = _frames(monkeypatch, [150.0] * 50)

    def dark(expose):
        raise pb.DarkMissing("Falta el fondo con \"todo apagado\"")
    res = _run(cam, spec, tmp, dark=dark)
    assert res.stop_reason == StopReason.ACQUISITION_FAILED and not res.windows and calls == []
    assert "fondo" in res.detail


# ── Backend ─────────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def be(tmp_path, monkeypatch):
    from pyspectrum.modules.step_and_glue import Backend
    hardware_session.clear_emergency()
    cam = get_andor_ccd(force_mock=True)
    cam.abort_acquisition()
    cam.set_read_mode(READ_MODE_FVB)
    b = Backend(cam, get_shamrock(force_mock=True))
    b.data_dir = tmp_path
    _KEEP.append(b)
    yield b
    hardware_session.clear_emergency()


def _n_windows(be, start=500.0, end=900.0, overlap=0.2, exp=0.01):
    req, the_plan, _rep = be._prepare(start, end, overlap, exp, False, False)
    return len(the_plan.centers)


def test_backend_stitches_dark_subtracted_windows_and_reuses_the_dark(be, monkeypatch):
    n = _n_windows(be)
    calls = _frames(monkeypatch, [100.0] + [150.0] * n + [150.0] * n)
    got = []
    be.spectrumFinishedSignal.connect(lambda w, s, nw, ns, lm: got.append(np.asarray(s)))
    be.measure_step_and_glue(500.0, 900.0, 0.2, 0.01, False)
    assert len(calls) == n + 1 and got and np.allclose(got[-1], 50.0)
    be.measure_step_and_glue(500.0, 900.0, 0.2, 0.01, False)
    assert len(calls) == 2 * n + 1                            # el segundo barrido reutiliza el oscuro


def test_restar_off_stitches_the_raw_windows(be, monkeypatch):
    n = _n_windows(be)
    _frames(monkeypatch, [100.0] + [150.0] * n)
    got = []
    be.spectrumFinishedSignal.connect(lambda w, s, nw, ns, lm: got.append(np.asarray(s)))
    be.measure_step_and_glue(500.0, 900.0, 0.2, 0.01, False)
    be.set_subtract_dark(False)
    assert np.allclose(got[-1], 150.0)
    be.set_subtract_dark(True)
    assert np.allclose(got[-1], 50.0)


def test_all_off_without_a_dark_does_not_start(be, monkeypatch):
    calls = _frames(monkeypatch, [150.0] * 50)
    msgs = []
    be.statusSignal.connect(msgs.append)
    be.dark_ctl.set_settings(pb.METHOD_ALL_OFF, 1)
    assert be.measure_step_and_glue(500.0, 900.0, 0.2, 0.01, False) is None
    assert calls == [] and not hardware_session.is_busy and "Tomar fondo ahora" in msgs[-1]


def test_glued_txt_references_the_dark(be, monkeypatch, tmp_path):
    n = _n_windows(be)
    _frames(monkeypatch, [100.0] + [150.0] * n)
    be.measure_step_and_glue(500.0, 900.0, 0.2, 0.01, False)
    be.save_spectrum(str(tmp_path / "g.txt"))
    text = (tmp_path / "g.txt").read_text(encoding="utf-8")
    assert text.splitlines()[0].startswith("# Wavelength_nm")       # primera línea: las columnas (Solis)
    assert f"background_id: {be.last_result.dark.id}" in text


# ── Sustrato ventana por ventana (B4) ───────────────────────────────────────────────────────

def test_substrate_is_taken_per_window_and_subtracted_at_its_own_lambda(be, monkeypatch):
    n = _n_windows(be)
    # sustrato: oscuro (100) y una ventana por λc con valores distintos; después la muestra (150)
    substrate = [120.0 + i for i in range(n)]
    _frames(monkeypatch, [100.0] + substrate + [150.0] * n)
    be.measure_substrate(500.0, 900.0, 0.2, 0.01, False)
    assert be.substrate is not None and len(be.substrate.windows) == n
    got = []
    be.spectrumFinishedSignal.connect(lambda w, s, nw, ns, lm: got.append(np.asarray(s)))
    be.measure_step_and_glue(500.0, 900.0, 0.2, 0.01, False, subtract_substrate=True)
    processed = be._raw_spec_steps
    for i, data in enumerate(processed):
        assert np.allclose(data, 150.0 - (120.0 + i))           # cada ventana, su sustrato (el oscuro se cancela)


def test_substrate_of_another_plan_is_not_subtracted(be, monkeypatch):
    n = _n_windows(be)
    n2 = _n_windows(be, exp=0.02)
    _frames(monkeypatch, [100.0] + [120.0] * n + [100.0] + [150.0] * n2)
    be.measure_substrate(500.0, 900.0, 0.2, 0.01, False)
    msgs = []
    be.statusSignal.connect(msgs.append)
    be.measure_step_and_glue(500.0, 900.0, 0.2, 0.02, False, subtract_substrate=True)
    assert all(np.allclose(d, 50.0) for d in be._raw_spec_steps)    # sólo el oscuro
    assert any("sustrato" in m and "no se restó" in m for m in msgs)


@pytest.mark.parametrize("kind,reason", [("USER_STOP", StopReason.USER_STOP), ("ESTOP", StopReason.ESTOP)])
def test_stop_or_estop_during_the_dark_is_not_an_acquisition_failure(rig, monkeypatch, kind, reason):
    from pyspectrum.modules.acquisition import AcquisitionFailure, AcquisitionFailureKind
    cam, spec, tmp = rig
    monkeypatch.setattr(eng, "single_exposure", lambda cam, req, **kw: AcquisitionFailure(
        getattr(AcquisitionFailureKind, kind), None, None, "interrumpida"))
    spy = []
    spec_calls = type("S", (), {"ShamrockSetShutter": lambda self, d, st: spy.append(st) or 20202})()

    def dark(expose):
        cond = pb.read_conditions(cam, (1004,), exposure_s=0.01, read_mode=READ_MODE_FVB)
        return pb.take_dark(cam, spec_calls, cond, method=pb.METHOD_SHUTTER, n_frames=1, expose=expose,
                            store=pb.DarkStore(), open_lasers=lambda: [])
    res = _run(cam, spec, tmp, dark=dark)
    assert res.stop_reason == reason and not res.windows
    assert spy == [0, 1]                                      # el obturador vuelve a abrirse igual
