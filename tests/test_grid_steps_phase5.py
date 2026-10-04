# -*- coding: utf-8 -*-
"""Pasos entre nodos con restitución y topes de plausibilidad (C-01 Ronda 4, R4-17 fase 5; `ronda2_architecture.md`
§4.7, §5.5; `c01_ronda4/experimentalist.md` §5; DEC-050).

Contrato:
1. "Cerrar todos" durante la segunda rampa del autofoco → Z vuelve a la de antes del paso, `last_af_*` quedan como
   estaban, y el registro de MOV no muestra el Z del ruido (E-6); el paso se repite cuando vence la retención;
2. un escaneo de deriva oscuro → el ancla y la velocidad de deriva no cambian;
3. una corrección que rompe T5 → se rechaza, se repite una vez, y la segunda vez pausa;
4. T6 → pausa al primer rechazo;
5. una parada durante el autofoco → la restitución se difiere y se aplica en el Play, antes de cualquier otra cosa.
Y los topes, uno por uno (numpy puro).
"""
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYPRINTING_SAFE", "1")

import numpy as np
import pytest
from PyQt6.QtWidgets import QApplication

from core import step_plausibility as sp

_app = QApplication.instance() or QApplication(["pytest"])
_KEEP_ALIVE = []
HOLD_S = 1.0
EXPECTED = ["success", "success", "timeout", "success", "success", "success", "timeout", "success", "success",
            "success", "success"]


# ── Los topes ───────────────────────────────────────────────────────────────────────────────

def _spot(n=40, cx=20.0, cy=20.0, sigma=3.0, amp=1.0, noise=0.01, seed=0):
    rng = np.random.default_rng(seed)
    yy, xx = np.indices((n, n))
    return 0.5 + amp * np.exp(-0.5 * (((xx - cx) ** 2 + (yy - cy) ** 2) / sigma ** 2)) + noise * rng.standard_normal((n, n))


BOX = (38.0, 42.0, 38.0, 42.0)          # 4 µm de lado, 40 píxeles: 0.1 µm por píxel
PIX = (0.1, 0.1)


def test_a_good_drift_correction_passes_every_cap():
    img = _spot()
    amp, width = sp.spot_amplitude_width(img, PIX)
    v = sp.check_drift_correction(img, (40.0, 40.0), BOX, PIX, sp.DriftReference(amp, width), (40.02, 39.99),
                                  (40.0, 40.0), 30.0)
    assert v.ok, v


@pytest.mark.parametrize("case,expect", [
    ("oscuro", "T2"), ("amplitud", "T2"), ("ancho", "T3"), ("borde", "T4"), ("paso", "T5"), ("acumulado", "T6")])
def test_each_drift_cap_rejects_its_case(case, expect):
    ref_img = _spot()
    ref = sp.DriftReference(*sp.spot_amplitude_width(ref_img, PIX))
    img, center, prev, origin = _spot(), (40.0, 40.0), (40.0, 40.0), (40.0, 40.0)
    if case == "oscuro":
        img = 0.5 + 0.01 * np.random.default_rng(1).standard_normal((40, 40))
    elif case == "amplitud":
        img = _spot(amp=3.0)
    elif case == "ancho":
        img = _spot(sigma=6.0)
    elif case == "borde":
        center = (38.1, 40.0)
    elif case == "paso":
        prev = (40.6, 40.0)                       # 600 nm de paso: más que el techo de 500 nm
    elif case == "acumulado":
        origin = (36.5, 40.0)                     # 3.5 µm desde la referencia
    v = sp.check_drift_correction(img, center, BOX, PIX, ref, prev, origin, 10.0)
    assert not v.ok and expect in v.failed, v
    assert v.always_pause is (expect == "T6")
    assert v.reason


def test_the_step_cap_grows_with_time_up_to_its_ceiling():
    ref = sp.DriftReference(*sp.spot_amplitude_width(_spot(), PIX))
    ok_late = sp.check_drift_correction(_spot(), (40.0, 40.0), BOX, PIX, ref, (40.16, 40.0), (40.0, 40.0), 60.0)
    assert ok_late.ok                                    # 160 nm en 60 s: permitido 170 nm
    early = sp.check_drift_correction(_spot(), (40.0, 40.0), BOX, PIX, ref, (40.16, 40.0), (40.0, 40.0), 5.0)
    assert "T5" in early.failed                          # en 5 s: permitido 60 nm


def _profile(center=900, n=1800, sigma=30.0, noise=0.02, seed=0):
    rng = np.random.default_rng(seed)
    x = np.arange(n)
    return 0.5 + np.exp(-0.5 * ((x - center) / sigma) ** 2) + noise * rng.standard_normal(n)


def test_a_good_autofocus_passes_and_each_af_cap_rejects_its_case():
    lock = _profile(seed=1)
    good = _profile(seed=2)
    corr = np.correlate(good, lock, "same")
    assert sp.check_autofocus(good, lock, corr, 900, 0.002, 0.05, 30.0).ok
    dark = 0.5 + 0.02 * np.random.default_rng(3).standard_normal(1800)
    assert "F2" in sp.check_autofocus(dark, lock, corr, 900, None, None, None).failed
    assert "F3" in sp.check_autofocus(good, lock, corr, 900, 0.06, None, None).failed     # 60 nm > 50 nm
    assert "F4" in sp.check_autofocus(good, lock, corr, 900, 0.0, 0.4, 600.0).failed      # 400 nm > techo 300 nm
    assert "F5" in sp.check_autofocus(good, lock, corr, 60, None, None, None).failed       # al 3 % de la rampa


# ── La grilla ───────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def rig(monkeypatch, tmp_path):
    from core import nidaq
    from harness.grid_chain_rig import GridChainRig
    monkeypatch.setattr(nidaq, "OPERATOR_HOLD_S", HOLD_S)
    r = GridChainRig(monkeypatch, tmp_path)
    with r:
        _KEEP_ALIVE.append(r.backend)
        yield r


def _ramp_hook(rig, monkeypatch, at_call, action):
    """Corre `action()` al comienzo de la rampa número `at_call` del foco (1: el auto-lock; 2 y 3: las dos rampas del
    primer autofoco)."""
    fw = rig.backend.focusWorker
    real, calls = fw._ramp_lin, []

    def hooked():
        calls.append(1)
        if len(calls) == at_call:
            action()
        return real()
    monkeypatch.setattr(fw, "_ramp_lin", hooked)
    return calls


def _z_moves(rec, after=float("-inf"), before=float("inf")):
    return [(t, m[0]) for t, m, ok in rec.move_results if len(m) == 1 and after < t < before]


def test_a_close_during_the_second_autofocus_ramp_restores_and_repeats_the_step(rig, monkeypatch):
    rig.configure()
    pw = rig.backend.printingWorker
    seen = {}
    real_emit = pw._emit_autofocus

    def emit():
        seen.setdefault("before_af", (pw.last_af_time, pw.last_af_index))
        return real_emit()
    monkeypatch.setattr(pw, "_emit_autofocus", emit)
    real_invalid = pw._step_invalid

    def invalid(step, reason):
        seen["at_cut"] = (pw.last_af_time, pw.last_af_index)
        return real_invalid(step, reason)
    monkeypatch.setattr(pw, "_step_invalid", invalid)
    _ramp_hook(rig, monkeypatch, 3, rig.close_all)
    rec = rig.run_grid(timeout_s=60)
    assert rec.finished, rec.decision_events
    t_cut = rec.cut_times[0]
    during = [z for _, z in _z_moves(rec, after=t_cut, before=t_cut + HOLD_S)]
    assert 10.0034 not in during and 10.0017 not in during, during   # ningún Z del ruido de la rampa cortada
    assert during and during[-1] == 10.0, during                      # Z vuelve a la de antes del paso
    assert seen["at_cut"] == seen["before_af"]        # el autofoco cortado no tocó last_af_* (se asignan al aceptar)
    after = [z for _, z in _z_moves(rec, after=t_cut + HOLD_S)]
    assert 10.0017 in after                                           # el autofoco se repitió después de la retención
    assert [ {i: s for i, s in rec.decision_events}[i] for i in range(11)] == EXPECTED


def _drift_grid(rig):
    """Una grilla con corrección de deriva: el nodo 0 es el ancla P0, y el primer autofoco pasa por el ancla."""
    rig.configure(driftbool=True, particulas=4, grid_x=np.array([0.0, 2.0, 4.0, 6.0]), grid_y=np.zeros(4))


def _dark_scans(monkeypatch):
    """Los escaneos confocales (rampas en X o Y) sin el pico: oscuros. El autofoco (rampa en Z) sigue viendo luz."""
    from core import nidaq
    real = nidaq._MockNITask.read

    def read(self, samps=None):
        axis = getattr(self, "_ramp_axis", None)
        if axis in ("X", "Y"):
            self._ramp_axis = None
            try:
                return real(self, samps)
            finally:
                self._ramp_axis = axis
        return real(self, samps)
    monkeypatch.setattr(nidaq._MockNITask, "read", read)


def _offset_center(rig, monkeypatch, dx_um):
    cw = rig.backend.confocalWorker
    monkeypatch.setattr(cw, "_CMmeasure", lambda: (round(cw.x_pos + dx_um, 3), round(cw.y_pos, 3)))


def _run_until_paused(rig, timeout_s=90):
    pw = rig.backend.printingWorker
    rig.run_grid(timeout_s=timeout_s, until=lambda: pw.is_paused or rig.record.finished)
    return pw


def test_a_dark_drift_scan_moves_neither_the_anchor_nor_the_drift_speed(rig, monkeypatch):
    _drift_grid(rig)
    _dark_scans(monkeypatch)
    pw = rig.backend.printingWorker
    rejected = []
    pw.stepRejectedSignal.connect(lambda i, step, why: rejected.append((i, step, why)))
    import inspect
    callers = []
    real_speed = pw._update_drift_velocity
    monkeypatch.setattr(pw, "_update_drift_velocity",
                        lambda: callers.append(inspect.stack()[1].function) or real_speed())
    scans = []
    real_start = pw._start_drift_scan
    monkeypatch.setattr(pw, "_start_drift_scan", lambda: scans.append(1) or real_start())
    pw2 = _run_until_paused(rig)
    assert pw2.is_paused and not rig.record.finished
    assert len(scans) == 2                                              # el escaneo oscuro y su repetición
    assert (pw.startX, pw.startY) == (40.0, 40.0)                       # el ancla no se movió
    assert pw.drift_history_xy == []                                    # ninguna corrección registrada
    assert "on_scan_finished" not in callers, callers                   # la velocidad de deriva tampoco
    assert rejected and rejected[0][1] == "deriva" and "T2" in rejected[0][2]


def test_a_drift_correction_that_breaks_t5_is_repeated_once_and_then_pauses(rig, monkeypatch):
    _drift_grid(rig)
    _offset_center(rig, monkeypatch, 0.8)                               # 800 nm de paso en pocos segundos
    pw = rig.backend.printingWorker
    rejected = []
    pw.stepRejectedSignal.connect(lambda i, step, why: rejected.append((i, step, why)))
    scans = []
    real_start = pw._start_drift_scan
    monkeypatch.setattr(pw, "_start_drift_scan", lambda: scans.append(1) or real_start())
    _run_until_paused(rig)
    assert pw.is_paused and len(scans) == 2                             # el escaneo y su única repetición
    assert len(rejected) == 1 and "T5" in rejected[0][2]
    assert (pw.startX, pw.startY) == (40.0, 40.0)


def test_t6_pauses_at_the_first_rejection(rig, monkeypatch):
    _drift_grid(rig)
    _offset_center(rig, monkeypatch, 3.5)                               # 3.5 µm desde la referencia
    pw = rig.backend.printingWorker
    rejected = []
    pw.stepRejectedSignal.connect(lambda i, step, why: rejected.append((i, step, why)))
    scans = []
    real_start = pw._start_drift_scan
    monkeypatch.setattr(pw, "_start_drift_scan", lambda: scans.append(1) or real_start())
    _run_until_paused(rig)
    assert pw.is_paused and len(scans) == 1                             # sin repetición
    assert rejected and "T6" in rejected[0][2]


def test_a_stop_during_the_autofocus_defers_the_restore_to_play(rig, monkeypatch):
    from core.grid_state import GridRunState
    rig.configure()
    pw = rig.backend.printingWorker
    _ramp_hook(rig, monkeypatch, 3, rig.estop)
    rig.run_grid(timeout_s=60, until=lambda: pw.run_state == GridRunState.STOPPED and pw.is_quiescent())
    rec = rig.record
    t_stop = rec.cut_times[0]
    assert pw._pending_restore is not None
    rig.wait_until(lambda: False, timeout_s=0.4)
    assert rec.executed_moves(after_t=t_stop) == []                     # cero MOV hasta Play
    assert rig.rearm()
    t_play = time.monotonic()
    rig.play()
    assert rig.wait_until(lambda: rec.finished, timeout_s=90), rec.decision_events
    first = next(m for t, m, ok in rec.move_results if ok and t > t_play)
    assert first == (10.0,)                                             # lo primero: Z vuelve a la de antes
    assert pw._pending_restore is None


def test_the_panel_keeps_the_rejected_step_notice_until_play():
    import modules.measurements as meas
    from core.grid_state import GridRunState
    fe = meas.Frontend("printing")
    be = meas.Backend(mode="printing")
    _KEEP_ALIVE.extend([fe, be])
    fe.make_connection(be)
    be.stepRejectedSignal.emit(3, "deriva", "T5 paso: Δ = 800 nm, permitido 60 nm")
    assert "Corrección de deriva no plausible en P0" in fe.lbl_cut_notice.text()
    assert not fe.lbl_cut_notice.isHidden() and not fe._cut_notice_timer.isActive()
    be.run_state = GridRunState.RUNNING
    assert fe.lbl_cut_notice.isHidden()
