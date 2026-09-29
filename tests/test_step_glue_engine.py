# -*- coding: utf-8 -*-
"""Motor de Step & Glue (paso 11 del bloque A; R2-arq §2.9 y §6.6, R2-inst §5; reconciliación D-09 a D-11,
D-16 y D-17).

- `plan` (puro): centros ascendentes, ventana medida o nominal y duración estimada (D-16).
- `preflight`: bloqueantes y advertencias; el motor no abre diálogos.
  - Bloquean: una ventana en condición especular, un centro fuera de los límites de la red
    (`GetWavelengthLimits`), la exposición fuera de 1e-4 a 10 s (R4-4), la cámara o el Shamrock no
    conectados, normalizar sin archivo de lámpara, o una red distinta de la del snapshot (D-09a).
  - Advierten: el espejo de detección no "abajo" según el software (R4-A-4); un láser abierto cuya línea
    cae en el barrido con ganancia EM > 0 (H-06, D-11: se avisa).
- `run_windows`:
  - una `single_exposure` por ventana, nunca el último cuadro del Live (R4-5);
  - cada movimiento se relee (λ dentro de la tolerancia), y el eje se verifica: nunca un eje falso;
  - cada ventana se escribe a disco al terminar;
  - Stop y E-STOP se revisan en cada tramo, y lo adquirido se entrega con `complete=False`, sin coser;
  - la primera ventana sin luz pausa y pregunta, sin descartarla (G8, D-17);
  - se registran por ventana los láseres abiertos, con la bandera LIGHT_CHANGED si cambiaron (H-03).
- **Latido:** se renueva sólo mientras haya un láser abierto, y **nunca con argumento** (C-29, D-09b).
"""
import json

import numpy as np
import pytest

from pyspectrum.drivers.andor_ccd_driver import READ_MODE_FVB, get_andor_ccd
from pyspectrum.drivers.shamrock_driver import DEVICE, GRATING_150_LINES, SHAMROCK_SUCCESS, get_shamrock
from pyspectrum.modules import step_glue_engine as eng
from pyspectrum.modules.step_glue_engine import (
    PreflightReport, StepGlueRequest, StopReason, heartbeat_tick, plan, preflight, run_windows,
)


class _Clock:
    def __init__(self): self.t = 0.0
    def __call__(self): return self.t
    def sleep(self, s): self.t += s


def _req(**kw):
    base = dict(start_nm=500.0, end_nm=900.0, overlap_frac=0.20, exposure_s=0.01, read_mode=READ_MODE_FVB,
                grating=GRATING_150_LINES, em_gain=0, normalize_with_lamp=False, lamp_file=None)
    base.update(kw)
    return StepGlueRequest(**base)


@pytest.fixture
def rig(tmp_path):
    cam = get_andor_ccd(force_mock=True)
    cam.abort_acquisition()
    cam.set_read_mode(READ_MODE_FVB)
    spec = get_shamrock(force_mock=True)
    return cam, spec, tmp_path


# ── plan ──────────────────────────────────────────────────────────────────────

def test_plan_is_ascending_and_estimates_the_duration(rig):
    cam, spec, _ = rig
    p = plan(_req(exposure_s=1.0), spec)
    assert p.centers == sorted(p.centers) and len(p.centers) >= 4
    np.testing.assert_allclose(np.diff(p.centers), p.window_nm * (1 - 0.20))    # paso = W · (1 − solape)
    assert p.window_source in ("measured", "nominal", "optical_core")
    per_window = eng.SETTLE_EXTRA_S + 1.0 + eng.READOUT_ESTIMATE_S
    assert p.estimated_duration_s == pytest.approx(len(p.centers) * per_window)


# ── preflight ─────────────────────────────────────────────────────────────────

def _pf(cam, spec, req, **kw):
    kw.setdefault("mirror_position", "down")
    kw.setdefault("open_shutters", [])
    return preflight(req, plan(req, spec), cam, spec, **kw)


def test_clean_request_has_no_blockers(rig):
    cam, spec, _ = rig
    rep = _pf(cam, spec, _req())
    assert rep.blockers == [] and rep.warnings == []


@pytest.mark.parametrize("kw, text", [
    (dict(start_nm=0.0, end_nm=60.0), "especular"),        # 1.ª ventana centrada en ≈ 41 nm < 56.7 nm
    (dict(start_nm=500.0, end_nm=1700.0), "límites"),
    (dict(exposure_s=12.0), "10 s"),
    (dict(normalize_with_lamp=True, lamp_file=None), "lámpara"),
    (dict(grating=2), "red"),
])
def test_blockers(rig, kw, text):
    cam, spec, _ = rig
    rep = _pf(cam, spec, _req(**kw))
    assert any(text in b for b in rep.blockers), rep.blockers


def test_camera_not_connected_blocks(rig):
    cam, spec, _ = rig

    class _Gone:
        available = False
        unavailable_reason = "pylablib no pudo abrir la cámara"
    rep = _pf(_Gone(), spec, _req())
    assert any("cámara" in b for b in rep.blockers)


@pytest.mark.parametrize("pos", ["up", "unknown"])
def test_mirror_not_down_is_a_warning(rig, pos):
    cam, spec, _ = rig
    rep = _pf(cam, spec, _req(), mirror_position=pos)
    assert rep.blockers == [] and rep.mirror_warning


def test_open_laser_inside_the_range_with_gain_warns(rig):
    cam, spec, _ = rig
    rep = _pf(cam, spec, _req(em_gain=150), open_shutters=["532 nm (green)"])
    assert any("532" in w and "150" in w for w in rep.warnings)
    rep = _pf(cam, spec, _req(em_gain=0), open_shutters=["532 nm (green)"])
    assert not any("ganancia" in w for w in rep.warnings)


# ── latido ────────────────────────────────────────────────────────────────────

def test_heartbeat_only_with_a_laser_open_and_without_argument():
    calls = []
    open_now = []
    tick = heartbeat_tick(get_open=lambda: list(open_now), heartbeat=lambda *a, **k: calls.append((a, k)))
    tick()
    assert calls == []
    open_now.append("532 nm (green)")
    tick()
    assert calls == [((), {})]


# ── run_windows ───────────────────────────────────────────────────────────────

def _run(cam, spec, run_dir, req=None, **kw):
    req = req or _req()
    clock = _Clock()
    kw.setdefault("should_abort", lambda: False)
    kw.setdefault("on_tick", lambda: None)
    kw.setdefault("is_estopped", lambda: False)
    kw.setdefault("get_open", lambda: [])
    kw.setdefault("on_no_signal", lambda w: True)
    return run_windows(plan(req, spec), req, cam, spec, run_dir=run_dir, clock=clock, sleep=clock.sleep, **kw)


def test_one_exposure_per_window_saved_to_disk(rig, monkeypatch):
    cam, spec, tmp = rig
    calls = []
    real = eng.single_exposure
    monkeypatch.setattr(eng, "single_exposure", lambda *a, **k: calls.append(1) or real(*a, **k))
    got = []
    res = _run(cam, spec, tmp, on_window=got.append)
    n = len(res.plan.centers)
    assert res.complete and res.stop_reason == StopReason.COMPLETED
    assert len(calls) == n and len(got) == n and len(res.windows) == n
    for w in res.windows:
        assert abs(w.center_nm_read - w.center_nm_requested) <= eng.WAVELENGTH_READBACK_TOL_NM
        assert w.data.shape == (1004,) and np.all(np.isfinite(w.wavelength_axis))
        assert w.path.exists()
        meta = json.loads(np.load(w.path, allow_pickle=False)["metadata"].item())
        assert meta["center_nm_requested"] == pytest.approx(w.center_nm_requested)
        assert meta["open_lasers"] == []


def test_stop_returns_partial_windows_without_gluing(rig):
    cam, spec, tmp = rig
    count = {"n": 0}

    def on_window(w):
        count["n"] += 1
    res = _run(cam, spec, tmp, on_window=on_window, should_abort=lambda: count["n"] >= 2)
    assert not res.complete and res.stop_reason == StopReason.USER_STOP
    assert len(res.windows) == 2 and res.glued is None


def test_estop_stops_the_sweep(rig):
    cam, spec, tmp = rig
    res = _run(cam, spec, tmp, is_estopped=lambda: True)
    assert res.stop_reason == StopReason.ESTOP and res.windows == ()


def test_failed_move_aborts_and_keeps_previous_windows(rig, monkeypatch):
    cam, spec, tmp = rig
    real = spec.ShamrockSetWavelength
    state = {"n": 0}

    def flaky(device=DEVICE, wavelength=0.0):
        state["n"] += 1
        return 20201 if state["n"] == 2 else real(device, wavelength)
    monkeypatch.setattr(spec, "ShamrockSetWavelength", flaky)
    res = _run(cam, spec, tmp)
    assert res.stop_reason == StopReason.MOTION_FAILED and len(res.windows) == 1
    assert "20201" in res.detail


def test_failed_axis_never_uses_a_fake_axis(rig, monkeypatch):
    cam, spec, tmp = rig
    monkeypatch.setattr(spec, "get_wavelength_axis_cubic", lambda device=DEVICE, num_pixels=1004: (20201, np.full(num_pixels, np.nan)))
    res = _run(cam, spec, tmp)
    assert res.stop_reason == StopReason.MOTION_FAILED and res.windows == ()


def test_acquisition_failure_is_reported(rig, monkeypatch):
    cam, spec, tmp = rig
    from pyspectrum.modules.acquisition import AcquisitionFailure, AcquisitionFailureKind
    monkeypatch.setattr(eng, "single_exposure",
                        lambda *a, **k: AcquisitionFailure(AcquisitionFailureKind.TIMEOUT, None, "WaitForAcquisition", "sin cuadro"))
    res = _run(cam, spec, tmp)
    assert res.stop_reason == StopReason.ACQUISITION_FAILED and "sin cuadro" in res.detail


def test_no_signal_in_the_first_window_asks_and_can_stop(rig, monkeypatch):
    cam, spec, tmp = rig
    from pyspectrum.modules.acquisition import Frame
    monkeypatch.setattr(eng, "single_exposure", lambda *a, **k: Frame(np.full(1004, 300.0), 0.01, 1, 0.0, 0.01))
    asked = []
    res = _run(cam, spec, tmp, on_no_signal=lambda w: asked.append(w.index) or False)
    assert asked == [0] and res.stop_reason == StopReason.USER_STOP and len(res.windows) == 1
    asked.clear()
    res = _run(cam, spec, tmp, on_no_signal=lambda w: asked.append(w.index) or True)
    assert asked == [0] and res.complete


def test_open_lasers_are_recorded_and_changes_flagged(rig):
    cam, spec, tmp = rig
    state = {"n": 0}

    def get_open():
        return ["532 nm (green)"] if state["n"] < 2 else []

    def on_window(w):
        state["n"] += 1
    res = _run(cam, spec, tmp, get_open=get_open, on_window=on_window)
    assert res.windows[0].open_lasers == ("532 nm (green)",) and not res.windows[0].light_changed
    assert res.windows[2].open_lasers == () and res.windows[2].light_changed


def test_complete_sweep_is_glued_with_the_existing_formula(rig):
    cam, spec, tmp = rig
    res = _run(cam, spec, tmp)
    from pyspectrum.calibration.halogen_lamp import sigmoidal_step_and_glue
    wl, sp = sigmoidal_step_and_glue([w.wavelength_axis for w in res.windows], [w.spectrum_1d for w in res.windows])
    np.testing.assert_allclose(res.glued[0], wl)
    np.testing.assert_allclose(res.glued[1], sp)


def test_never_passes_an_explicit_heartbeat_timeout(monkeypatch):
    """R2-arq §7.2 (C-29): ni el motor ni la rutina llaman a heartbeat_shutter con argumento."""
    import ast
    from pathlib import Path
    from core import nidaq
    calls = []
    monkeypatch.setattr(nidaq, "heartbeat_shutter", lambda *a, **k: calls.append((a, k)))
    eng._default_heartbeat()
    assert calls == [((), {})]
    root = Path(__file__).resolve().parent.parent
    for rel in ("pyspectrum/modules/step_glue_engine.py", "pyspectrum/modules/step_and_glue.py"):
        tree = ast.parse((root / rel).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = getattr(node.func, "id", getattr(node.func, "attr", ""))
                if name == "heartbeat_shutter":
                    assert not node.args and not node.keywords, f"{rel}:{node.lineno}"
