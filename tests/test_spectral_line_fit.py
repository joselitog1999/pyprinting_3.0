# -*- coding: utf-8 -*-
"""Estimador del centro de una línea y presupuesto de la calibración (paso 14a; R2-met §2.1, §3.2, §5.2).

Con datos sintéticos de centro conocido (gaussiana integrada en el píxel, Poisson y lectura):
- T1 sesgo, con el control negativo del fondo constante sobre un fondo inclinado;
- T2 eficiencia frente a la cota de Cramér-Rao;
- T3 cobertura de la u informada;
- T5 rayos cósmicos, con rechazo temporal, y el control sin rechazo;
- T6 línea angosta sin despike espacial;
- T7 saturación; T8 sin línea;
- T9 residuo y signo con ejes ascendente y descendente;
- T13 presupuesto: sin U mientras falte un término, k = t(ν_eff).
"""
import numpy as np
import pytest
from scipy import stats

from core import spectral_line_fit as slf
import synthetic_line as syn


def _bias_and_std(sigma, snr, reps, *, background="linear", slope=0.0, seed=1):
    rng = np.random.default_rng(seed)
    errs = []
    for j in range(reps):
        x0 = 501.0 + (j % 20) / 20.0
        prof = syn.noisy_profile(rng, x0, sigma, snr, slope=slope)
        res = slf.estimate_line_center(prof, background=background)
        assert res.success, res.flags
        errs.append(res.center_px - x0)
    errs = np.asarray(errs)
    return errs.mean(), errs.std(ddof=1), errs


@pytest.mark.parametrize("sigma,snr", [(1.3, 20), (1.3, 50), (2.5, 20), (2.5, 50)])
def test_T1_the_estimator_is_unbiased_across_subpixel_phases(sigma, snr):
    bias, std, errs = _bias_and_std(sigma, snr, 300)
    se = std / np.sqrt(errs.size)
    assert abs(bias) <= max(0.02, 3 * se), (bias, se)


def test_T1_negative_control_a_constant_background_is_biased_on_a_slope():
    """El test tiene que poder ver un sesgo: gauss + constante sobre 2 e⁻/px se corre (SIMULADO +0.05 px)."""
    lin, _, _ = _bias_and_std(2.5, 20, 400, slope=2.0, seed=3)
    const, std, errs = _bias_and_std(2.5, 20, 400, background="constant", slope=2.0, seed=3)
    assert abs(lin) <= 0.02
    assert abs(const) > 0.02 and abs(const) > 3 * std / np.sqrt(errs.size), const


def test_T4_the_default_estimator_is_unbiased_on_a_sloped_background():
    rng = np.random.default_rng(4)
    errs = []
    for j in range(300):
        x0 = 501.0 + (j % 20) / 20.0
        errs.append(slf.estimate_line_center(syn.noisy_profile(rng, x0, 2.5, 20, slope=2.0)).center_px - x0)
    errs = np.asarray(errs)
    assert abs(errs.mean()) <= max(0.02, 3 * errs.std(ddof=1) / np.sqrt(errs.size)), errs.mean()


def _crlb_x0(sigma, snr):
    """Cota de Cramér-Rao numérica del centro para el modelo del generador (área, x0, σ, B0, B1)."""
    x0 = 501.3
    mu, height = syn.expected_profile(x0, sigma, snr)
    var = mu + syn.N_ROWS * syn.READ_NOISE_E ** 2
    area = height * sigma * np.sqrt(2 * np.pi)
    p = np.array([area, x0, sigma, 200.0, 0.0])

    def model(q):
        m, _ = syn.expected_profile(q[1], q[2], 1.0)
        m_unit_height = m - 200.0
        a_unit = 1.0 * np.sqrt(syn.N_ROWS * syn.READ_NOISE_E ** 2 + 200.0) * q[2] * np.sqrt(2 * np.pi)
        x = np.arange(syn.N_PX)
        return m_unit_height * (q[0] / a_unit) + q[3] + q[4] * (x - x0)

    jac = np.empty((syn.N_PX, p.size))
    for i in range(p.size):
        h = 1e-4 * max(1.0, abs(p[i]))
        dp = np.zeros_like(p)
        dp[i] = h
        jac[:, i] = (model(p + dp) - model(p - dp)) / (2 * h)
    sl = slice(int(x0 - 12 * sigma), int(x0 + 12 * sigma))
    fisher = (jac[sl] / var[sl, None]).T @ jac[sl]
    return np.sqrt(np.linalg.inv(fisher)[1, 1])


@pytest.mark.parametrize("sigma,snr", [(1.3, 20), (2.5, 50)])
def test_T2_the_estimator_is_efficient(sigma, snr):
    _, std, _ = _bias_and_std(sigma, snr, 300, seed=5)
    assert std <= 1.15 * _crlb_x0(sigma, snr), (std, _crlb_x0(sigma, snr))


def test_T3_the_reported_uncertainty_covers():
    rng = np.random.default_rng(7)
    inside, n = 0, 500
    for j in range(n):
        x0 = 501.0 + (j % 20) / 20.0
        res = slf.estimate_line_center(syn.noisy_profile(rng, x0, 1.8, 30))
        inside += abs(res.center_px - x0) <= 2 * res.u_center_px
    assert 0.92 <= inside / n <= 0.98, inside / n


def test_T3_type_a_uncertainty_from_the_frames_of_an_arrival():
    rng = np.random.default_rng(8)
    frames = syn.frames_for_profile(rng, 501.4, 2.0, 15, 5)
    res = slf.estimate_line_center(frames.mean(axis=0), per_frame_profiles=frames)
    assert res.u_center_typeA_px is not None and res.u_center_typeA_px > 0
    assert res.u_center_px == pytest.approx(max(res.u_center_cov_px, res.u_center_typeA_px))
    assert 0.3 < res.chi2_red < 3.0


def test_T5_temporal_rejection_removes_a_cosmic_ray():
    rng = np.random.default_rng(11)
    clean_errs, raw_errs, rej_errs = [], [], []
    for j in range(60):
        x0 = 501.0 + (j % 20) / 20.0
        frames = syn.frames_for_profile(rng, x0, 2.0, 20, 5)
        clean_errs.append(slf.estimate_line_center(frames.mean(axis=0)).center_px - x0)
        hit = frames.copy()
        hit[j % 5, int(round(x0)) + 3] += 1e4
        raw_errs.append(slf.estimate_line_center(hit.mean(axis=0)).center_px - x0)
        cleaned, mask = slf.reject_cosmic_rays_temporal(hit)
        assert mask[j % 5, int(round(x0)) + 3]
        rej_errs.append(slf.estimate_line_center(cleaned).center_px - x0)
    limit = 3 * np.std(clean_errs)
    assert np.sqrt(np.mean(np.square(rej_errs))) <= limit
    assert np.sqrt(np.mean(np.square(raw_errs))) > limit          # sin rechazo, el rayo corre el centro


def test_T6_a_narrow_bright_line_is_not_damaged():
    rng = np.random.default_rng(13)
    errs = [slf.estimate_line_center(syn.noisy_profile(rng, 501.0 + j / 20, 1.0, 2000)).center_px - (501.0 + j / 20)
            for j in range(20)]
    assert np.std(errs) <= 0.01, np.std(errs)


def test_T7_saturation_is_detected_and_no_center_is_returned():
    rng = np.random.default_rng(17)
    raw = rng.normal(500, 5, size=(5, 9, syn.N_PX))
    raw[:, 4, 500:503] = 16383
    assert slf.check_saturation(raw, adc_max_counts=16383)
    assert not slf.check_saturation(raw[:, :, :400], adc_max_counts=16383)
    res = slf.estimate_line_center(raw.sum(axis=1).mean(axis=0), saturated=True)
    assert not res.success and "SATURATED" in res.flags and np.isnan(res.center_px)


@pytest.mark.parametrize("profile", [np.ones(syn.N_PX) * 100.0,
                                     np.random.default_rng(19).normal(300, 20, syn.N_PX)])
def test_T8_no_line_means_no_center(profile):
    res = slf.estimate_line_center(profile)
    assert not res.success and "NO_LINE" in res.flags and np.isnan(res.center_px)


@pytest.mark.parametrize("descending", [False, True])
def test_T9_residual_sign_and_the_software_correction(descending):
    axis = syn.linear_axis(descending=descending)
    lambda_ref = 532.0
    x_true = 507.25                      # la línea cae 5.75 px a la derecha de donde el SDK pone 532
    r, d = slf.calibration_residual_px(x_true, axis, lambda_ref)
    assert r == pytest.approx(x_true - 501.5, abs=1e-6)
    assert d == pytest.approx(0.1026, rel=1e-6)
    c_sw = -r
    corrected = np.interp(x_true + c_sw, np.arange(axis.size), axis)
    assert corrected == pytest.approx(lambda_ref, abs=1e-6)       # λ(p) = λ_SDK(p + c_sw) en la línea
    with pytest.raises(ValueError):
        slf.calibration_residual_px(x_true, axis, 900.0)            # λ_ref fuera del eje


def test_combine_arrivals():
    mean, u_a, nu, s = slf.combine_arrivals([1.0, 2.0, 3.0, 4.0])
    assert (mean, nu) == (2.5, 3)
    assert s == pytest.approx(np.std([1, 2, 3, 4], ddof=1))
    assert u_a == pytest.approx(s / 2)


def test_propose_offset_needs_a_sensitivity():
    assert slf.propose_offset(r_px=6.0, s_px_per_step=None, current_offset=85) is None
    assert slf.propose_offset(r_px=6.0, s_px_per_step=1.8, current_offset=85) == 85 + round(-6.0 / 1.8)
    assert slf.propose_offset(r_px=0.4, s_px_per_step=1.8, current_offset=85) == 85


def test_T13_no_expanded_uncertainty_while_a_term_has_no_value():
    rows = slf.build_budget(u_noise_px=0.09, s_rep_px=0.87, n_arrivals=9)
    names = [r.name for r in rows]
    assert any("notch" in n for n in names) and any(r.contribution_px is None for r in rows)
    assert slf.expanded_uncertainty(rows) is None
    known = [r for r in rows if r.contribution_px is not None]
    u_c, nu_eff, k = slf.expanded_uncertainty(known)
    # a mano: 0.03, 0.29 (ν = 8) y 0.012 (tipo B, ν infinito)
    c = [0.09 / 3, 0.87 / 3, 0.02 / np.sqrt(3)]
    assert u_c == pytest.approx(np.sqrt(sum(v ** 2 for v in c)), rel=1e-6)
    expected_nu = u_c ** 4 / (c[0] ** 4 / 8 + c[1] ** 4 / 8)
    assert nu_eff == pytest.approx(expected_nu, rel=1e-6)
    assert k == pytest.approx(stats.t.ppf(0.975, nu_eff), rel=1e-9)
