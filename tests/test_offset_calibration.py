# -*- coding: utf-8 -*-
"""Calibración automática de λ en modo SÓLO MEDIR (paso 14b; R2-met §2.2-2.3, §4; R2-inst §4; R4-C-5; R4-D-4).

Contra un puerto simulado con física conocida (residuo verdadero por red, repetibilidad de la torreta,
dispersión y línea de 532 por el notch):
- mide el residuo con M secuencial y deja la corrección fina c_sw = −r;
- **nunca escribe un offset** (el puerto no tiene cómo, y el módulo no llama a ningún Set*Offset);
- el 532 se abre sólo durante los cuadros con luz; el oscuro se toma cerrado y al final queda cerrado;
- exposición fija de 0.10 s y tope de 10 min: al llegar, CANCELADA con lo medido (R4-D-4);
- 150 → 1200 siempre, nunca la red espejo;
- veredictos: CON RESERVA con K1-K7 bien (U no declarada), RECHAZADA con el criterio que falla,
  CANCELADA con Stop o tope; una red no empezada no deja registro;
- sin px/paso (BANCO-40) no hay propuesta en pasos; con una S previa, O* = O₀ + round(−r/S).
"""
import ast
import itertools
import os
from pathlib import Path

os.environ.setdefault("PYPRINTING_SAFE", "1")

import numpy as np
import pytest

import config
from pyspectrum.calibration import offset_calibration as oc
from pyspectrum.calibration.offset_calibration import (AutoCalibrationPlan, CalibrationStopped,
                                                       OffsetCalibrationConfig, run_auto_calibration)
from pyspectrum.calibration.repository import CalibrationRepository, CalibrationVerdict
import synthetic_line as syn

DISP = {1: 0.1026, 2: 0.01152}
TRACE = 500


class SimPort:
    """Espectrógrafo + cámara + 532 simulados. El eje del SDK pone λc en el píxel 501.5; la línea cae en
    501.5 + (λ_L − λc)/D + r_true + jitter, con un jitter nuevo en cada llegada (repetibilidad)."""

    def __init__(self, *, r_true=None, sigma_rep=0.3, snr=60.0, light=True, saturate=False, sign=+1,
                 lam_true=532.0, seed=0, clock=None, frame_time_s=0.0, saturate_from_light_acquire=0):
        self.r_true = r_true or {1: 2.4, 2: -1.1}
        self.sigma_rep, self.snr, self.light, self.saturate, self.sign = sigma_rep, snr, light, saturate, sign
        self.lam_true = lam_true
        self.rng = np.random.default_rng(seed)
        self.g, self.lc, self.jitter = 1, 532.0, 0.0
        self.laser_open = False
        self.log = []
        self.clock, self.frame_time_s = clock, frame_time_s
        self.offsets = {1: 85, 2: 0}
        self.saturate_from = saturate_from_light_acquire
        self.light_acquires = 0

    # identidad y lecturas
    def identity(self):
        return {"serial": "SR-SIM", "camera_serial": "SIM", "n_px": 1004, "pixel_um": 8.0,
                "entrance_port": 1, "exit_port": 0}

    def grating_lines(self, g):
        return {1: 150.0, 2: 1200.0}[g]

    def read_grating_offset(self, g):
        return self.offsets[g]

    def read_detector_offset(self):
        return 0

    def read_slit_um(self):
        return 50.0

    def detector_state(self):
        return {"em_gain": 0, "ccd_temp_c": -60, "temp_status": "stabilized"}

    def window_nm(self, g):
        return DISP[g] * 1004

    def preflight(self):
        self.log.append("preflight")
        return [], []

    def begin(self):
        self.log.append("begin")
        return None

    def end(self):
        self.laser_open = False
        self.log.append("end")

    def tick(self):
        pass

    # movimiento y adquisición
    def move(self, g, lam):
        self.log.append(("move", g, round(lam, 3)))
        self.g, self.lc = g, lam
        self.jitter = self.rng.normal(0.0, self.sigma_rep)
        return None

    def read_axis(self):
        return self.lc + DISP[self.g] * (np.arange(1004) - 501.5)

    def set_laser(self, open_):
        self.laser_open = bool(open_)
        self.log.append("open" if open_ else "close")
        return True

    def acquire(self, n, exposure_s, rows, should_abort):
        if should_abort():
            raise CalibrationStopped("stop")
        self.log.append(("acquire", n, exposure_s, rows, self.laser_open))
        if self.clock is not None:
            self.clock.advance(self.frame_time_s * n)
        r0, r1 = rows if rows is not None else (0, 1002)
        nrows = r1 - r0
        out = self.rng.normal(500.0, 22.0, size=(n, nrows, 1004))
        if self.laser_open and self.light:
            x = 501.5 + self.sign * (self.lam_true - self.lc) / DISP[self.g] + self.r_true[self.g] + self.jitter
            mu, _ = syn.expected_profile(x, 2.0, self.snr, b0=0.0)
            weights = np.exp(-0.5 * ((np.arange(r0, r1) - TRACE) / 1.5) ** 2)
            weights = weights / np.exp(-0.5 * ((np.arange(TRACE - 4, TRACE + 5) - TRACE) / 1.5) ** 2).sum()
            line = weights[:, None] * mu[None, :]
            out += self.rng.poisson(np.clip(line, 0, None)[None].repeat(n, axis=0))
            self.light_acquires += 1
            if self.saturate and self.light_acquires > self.saturate_from:
                out[:, max(0, TRACE - r0), int(x)] = 16383.0
        return out


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


def _plan(gratings=(1, 2), confirmed=("notch_at_input", "detection_mirror_down"), **kw):
    return AutoCalibrationPlan(configs=tuple(OffsetCalibrationConfig(grating=g, lambda_ref_nm=532.0,
                                                                      lambda_ref_source="nominal, sin medir", **kw)
                                             for g in gratings),
                               reference_mode="notch_leak", operator_confirmed=frozenset(confirmed))


@pytest.fixture
def repo(tmp_path):
    return CalibrationRepository(tmp_path / "cal.jsonl")


def test_it_measures_the_residual_and_leaves_the_fine_correction(repo, tmp_path):
    port = SimPort()
    run = run_auto_calibration(port, _plan(), repo, data_dir=tmp_path)
    assert [g.grating for g in run.gratings] == [1, 2]
    for g in run.gratings:
        truth = port.r_true[g.grating]
        assert g.r_hw_px == pytest.approx(truth, abs=4 * g.u_r_hw_px + 0.05), (g.grating, g.r_hw_px, truth)
        assert g.c_sw_px == pytest.approx(-g.r_hw_px)
        assert g.verdict is CalibrationVerdict.ACEPTADA_CON_RESERVA, g.reasons
        assert 9 <= g.m_final <= 25
        assert g.proposed_offset is None and "BANCO-40" in g.proposal_reason
        assert Path(g.raw_path).exists() and str(tmp_path) in g.raw_path


def test_the_record_carries_the_schema_fields(repo, tmp_path):
    run = run_auto_calibration(SimPort(), _plan(gratings=(1,)), repo, data_dir=tmp_path)
    entries = [e for e in repo.history() if e.kind == "PROPOSED"]
    assert len(entries) == 1
    v = entries[0].values
    assert entries[0].method == "auto_offset_laser_leak_v1" and entries[0].software
    for field in ("dry_run", "verdict", "reasons", "lambda_ref_nm", "lambda_ref_medium",
                  "lambda_ref_source", "u_lambda_ref_nm", "declared_geometry", "grating_offset_before",
                  "detector_offset_read", "exposure_s", "em_gain", "slit_width_um", "roi_rows", "offsets_tried",
                  "r_hw_px", "u_r_hw_px", "M_final", "s_rep_px", "c_sw_px", "u_c_sw_px", "c_sw_convention",
                  "D_nm_per_px", "drift_check_px", "walk", "dispersion_sign_ok", "budget", "U_px",
                  "proposed_offset", "raw_data_path", "raw_data_sha256", "filters", "operator_confirmed",
                  "detection_mirror_state", "checks"):
        assert field in v, field
    assert v["dry_run"] is True
    assert v["lambda_ref_medium"] == "air" and v["u_lambda_ref_nm"] is None
    assert v["declared_geometry"] == {"n_px": 1004, "pixel_width_um": 8.0}
    assert v["U_px"] is None                               # hay términos sin valor: no se declara U
    assert v["c_sw_convention"] == "lambda(p) = lambda_SDK(p + c_sw)"
    assert v["exposure_s"] == config.CAL_EXPOSURE_S == 0.10
    assert entries[0].record_id == run.gratings[0].record_id


def test_the_laser_is_open_only_for_light_frames_and_closed_at_the_end(repo, tmp_path):
    port = SimPort()
    run_auto_calibration(port, _plan(gratings=(1,)), repo, data_dir=tmp_path)
    acquires = [e for e in port.log if isinstance(e, tuple) and e[0] == "acquire"]
    assert any(not a[4] for a in acquires), "falta el oscuro con el 532 cerrado"
    assert any(a[4] for a in acquires)
    assert all(a[2] == config.CAL_EXPOSURE_S for a in acquires)
    # nunca se mueve el espectrógrafo con el 532 abierto
    open_ = False
    for e in port.log:
        if e in ("open", "close"):
            open_ = e == "open"
        elif isinstance(e, tuple) and e[0] == "move":
            assert not open_, "movimiento con el 532 abierto"
    assert port.laser_open is False and port.log[-1] == "end"
    # y se cierra apenas terminan los cuadros con luz, no en el próximo movimiento
    for i, e in enumerate(port.log):
        if isinstance(e, tuple) and e[0] == "acquire" and e[4]:
            assert port.log[i + 1] == "close", port.log[i:i + 3]


def test_the_laser_is_closed_between_arrivals(repo, tmp_path):
    """Mientras se calcula y se informa una llegada, el 532 ya está cerrado."""
    port = SimPort()
    states = []
    run_auto_calibration(port, _plan(gratings=(1,), walk=False), repo, data_dir=tmp_path,
                         on_progress=lambda info: states.append(port.laser_open))
    assert states and not any(states)


def test_arrivals_approach_from_below(repo, tmp_path):
    port = SimPort()
    run_auto_calibration(port, _plan(gratings=(2,), walk=False), repo, data_dir=tmp_path)
    moves = [e for e in port.log if isinstance(e, tuple) and e[0] == "move"]
    for first, second in zip(moves[0::2], moves[1::2]):
        assert first[2] == pytest.approx(second[2] - 3.0)       # δ = 3 nm con la red de 1200


def test_gratings_go_150_then_1200_and_the_mirror_is_refused(repo, tmp_path):
    port = SimPort()
    run = run_auto_calibration(port, _plan(gratings=(2, 1)), repo, data_dir=tmp_path)
    assert [g.grating for g in run.gratings] == [1, 2]
    with pytest.raises(ValueError):
        OffsetCalibrationConfig(grating=3, lambda_ref_nm=532.0, lambda_ref_source="x")


def test_only_measure_mode_is_the_only_mode():
    with pytest.raises(ValueError):
        OffsetCalibrationConfig(grating=1, lambda_ref_nm=532.0, lambda_ref_source="x", dry_run=False)


def test_the_module_never_writes_an_offset():
    src = Path(oc.__file__).read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Attribute):
            assert not (node.attr.startswith("ShamrockSet") and "Offset" in node.attr), node.attr
            assert node.attr not in ("set_grating_offset", "set_detector_offset"), node.attr
    assert not any("offset" in name.lower() and name.lower().startswith(("set", "write"))
                   for name in dir(oc.PySpectrumCalibrationPort))


def test_missing_operator_confirmations_block_before_any_light(repo, tmp_path):
    port = SimPort()
    run = run_auto_calibration(port, _plan(confirmed=("notch_at_input",)), repo, data_dir=tmp_path)
    assert run.blockers and "espejo" in " ".join(run.blockers)
    assert "open" not in port.log and not run.gratings and not repo.history()


def test_poor_repeatability_is_rejected_by_K3(repo, tmp_path):
    run = run_auto_calibration(SimPort(sigma_rep=1.6, seed=3), _plan(gratings=(1,), walk=False), repo, data_dir=tmp_path)
    g = run.gratings[0]
    assert g.verdict is CalibrationVerdict.RECHAZADA
    assert any(r.startswith("K3") for r in g.reasons), g.reasons
    assert g.m_final == 25                                     # M secuencial hasta el máximo sin llegar a u objetivo


def test_a_dispersion_sign_opposite_to_the_axis_is_rejected_by_K5(repo, tmp_path):
    run = run_auto_calibration(SimPort(sign=-1), _plan(gratings=(1,)), repo, data_dir=tmp_path)
    g = run.gratings[0]
    assert g.verdict is CalibrationVerdict.RECHAZADA and any(r.startswith("K5") for r in g.reasons), g.reasons


def test_without_the_walk_the_result_is_only_measured(repo, tmp_path):
    run = run_auto_calibration(SimPort(), _plan(gratings=(1,), walk=False), repo, data_dir=tmp_path)
    g = run.gratings[0]
    assert g.verdict is CalibrationVerdict.EN_SECO
    assert g.checks["K4"][0] is None and g.checks["K5"][0] is None


def test_no_light_aborts_with_the_laser_closed(repo, tmp_path):
    port = SimPort(light=False)
    run = run_auto_calibration(port, _plan(), repo, data_dir=tmp_path)
    assert run.aborted and "espejo" in run.abort_reason
    assert port.laser_open is False
    assert [g.grating for g in run.gratings] == [1] and run.gratings[0].needs_seed


def test_saturation_in_the_light_probe_aborts_before_the_dark(repo, tmp_path):
    port = SimPort(saturate=True)
    run = run_auto_calibration(port, _plan(gratings=(1,)), repo, data_dir=tmp_path)
    assert run.aborted and "densidad" in run.abort_reason and port.laser_open is False
    assert not [e for e in port.log if isinstance(e, tuple) and e[0] == "acquire" and not e[4]]


def test_saturation_that_appears_during_the_arrivals_aborts(repo, tmp_path):
    port = SimPort(saturate=True, saturate_from_light_acquire=3)
    run = run_auto_calibration(port, _plan(gratings=(1,)), repo, data_dir=tmp_path)
    assert run.aborted and "densidad" in run.abort_reason and port.laser_open is False
    assert run.gratings[0].verdict is CalibrationVerdict.RECHAZADA


def test_stop_cancels_keeps_what_was_measured_and_skips_the_next_grating(repo, tmp_path):
    port = SimPort()
    counter = itertools.count()
    stop_at = 12
    run = run_auto_calibration(port, _plan(), repo, data_dir=tmp_path,
                               should_abort=lambda: next(counter) > stop_at)
    assert [g.grating for g in run.gratings] == [1]
    g = run.gratings[0]
    assert g.verdict is CalibrationVerdict.CANCELADA and g.arrivals, g
    assert port.laser_open is False
    assert [e.values["verdict"] for e in repo.history()] == ["CANCELADA"]


def test_the_ten_minute_cap_cancels(repo, tmp_path):
    clock = FakeClock()
    port = SimPort(clock=clock, frame_time_s=10.0)            # 5 cuadros por llegada = 50 s
    run = run_auto_calibration(port, _plan(), repo, data_dir=tmp_path, clock=clock)
    assert config.CAL_MAX_DURATION_S == 600
    assert run.gratings[-1].verdict is CalibrationVerdict.CANCELADA
    assert "600" in " ".join(run.gratings[-1].reasons) and port.laser_open is False


def test_a_prior_sensitivity_gives_an_integer_proposal(repo, tmp_path):
    run = run_auto_calibration(SimPort(r_true={1: 5.4, 2: 0.0}),
                               _plan(gratings=(1,), s_prior_px_per_step=1.8), repo, data_dir=tmp_path)
    g = run.gratings[0]
    assert g.proposed_offset == 85 + round(-g.r_hw_px / 1.8)


def test_a_seed_from_the_operator_is_flagged(repo, tmp_path):
    port = SimPort()
    run = run_auto_calibration(port, _plan(gratings=(1,), walk=False), repo, data_dir=tmp_path,
                               seed={1: (504.0, (490, 520))})
    g = run.gratings[0]
    assert "SEEDED_BY_OPERATOR" in g.flags
    assert repo.history()[-1].values["seeded_by_operator"] is True


def test_the_real_port_runs_on_the_simulator_without_writing(repo, tmp_path, monkeypatch):
    """El adaptador contra los simuladores de SAFE_MODE: la corrida termina, el 532 queda cerrado y nadie
    escribe un offset. El simulador no mueve la línea con λc, así que el veredicto no importa acá."""
    from pyspectrum.drivers.andor_ccd_driver import get_andor_ccd
    from pyspectrum.drivers.shamrock_driver import get_shamrock
    from core import nidaq
    cam, spec = get_andor_ccd(force_mock=True), get_shamrock(force_mock=True)
    writes = []
    for name in ("ShamrockSetGratingOffset", "ShamrockSetDetectorOffset"):
        monkeypatch.setattr(spec, name, lambda *a, _n=name, **k: writes.append(_n) or 20202, raising=False)
    port = oc.PySpectrumCalibrationPort(cam, spec, tick=lambda: None)
    monkeypatch.setattr(oc.PySpectrumCalibrationPort, "move", lambda self, g, lam: None)   # sin esperas
    assert port.simulated
    plan = _plan(gratings=(1,), walk=False, arrivals_final_min=3, arrivals_final_max=3)
    run = run_auto_calibration(port, plan, repo, data_dir=tmp_path)
    assert not run.blockers, run.blockers
    assert any("SIMULADOR" in w for w in run.warnings)
    assert writes == []
    assert nidaq.SHUTTERS[0] not in nidaq.get_open_shutter_names()
    assert repo.history()[-1].values["simulated"] is True
