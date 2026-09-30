# -*- coding: utf-8 -*-
"""Herramientas de Exploración sin Qt (paquete 2 de R4-M, DEC-040).

Contrato de las Rondas 2 y 3 (aprobadas 2026-09-30):
- perfiles de la regla con banda impar, en px del sensor;
- eje del perfil horizontal: λ del Shamrock sólo en primer orden, sin la corrección fina (R4-C-6);
  en especular o estado desconocido, px;
- ajuste gaussiano con `estimate_line_center` (el de la calibración), en los dos perfiles;
- saturación sobre el cuadro CRUDO respecto de 16383, siempre (pregunta 6);
- el fondo vale sólo con las mismas condiciones: exposición, ganancia EM, amplificador, preamplificador,
  HS, VS, modo de lectura, red, λc y forma del cuadro (pregunta 2);
- traza en el tiempo de una fila propia o de la media del ROI vertical (pregunta 3);
- guardado automático en HDF5 con el crudo y el fondo por separado (pregunta 5).
"""
import json

import numpy as np
import pytest

from pyspectrum.drivers import specular_interlock as si
from pyspectrum.modules import exploration_analysis as ea

H, W = 60, 200


def _frame(x0=100.0, y0=30.0, sx=3.0, sy=5.0, amp=3000.0, bias=500.0, seed=0):
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:H, 0:W]
    img = bias + amp * np.exp(-((xx - x0) ** 2) / (2 * sx ** 2) - ((yy - y0) ** 2) / (2 * sy ** 2))
    return img + rng.normal(0.0, 3.0, img.shape)


# ── Perfiles ────────────────────────────────────────────────────────────────────────────────

def test_row_and_column_profiles_average_an_odd_band():
    f = np.arange(H * W, dtype=float).reshape(H, W)
    np.testing.assert_allclose(ea.row_profile(f, 10, 1), f[10])
    np.testing.assert_allclose(ea.row_profile(f, 10, 3), f[9:12].mean(axis=0))
    np.testing.assert_allclose(ea.row_profile(f, 10, 4), f[8:13].mean(axis=0))   # par → siguiente impar
    np.testing.assert_allclose(ea.column_profile(f, 50, 5), f[:, 48:53].mean(axis=1))


def test_profiles_clip_at_the_edges_and_accept_1d_frames():
    f = np.arange(H * W, dtype=float).reshape(H, W)
    np.testing.assert_allclose(ea.row_profile(f, 0, 5), f[0:3].mean(axis=0))
    np.testing.assert_allclose(ea.row_profile(f, 10 ** 6, 3), f[H - 2:H].mean(axis=0))
    np.testing.assert_allclose(ea.column_profile(f, -7, 1), f[:, 0])
    one = np.arange(W, dtype=float)
    np.testing.assert_allclose(ea.row_profile(one, 0, 1), one)


def test_band_is_limited_to_the_maximum():
    assert ea.odd_band(0) == 1 and ea.odd_band(2) == 3 and ea.odd_band(10 ** 3) == ea.BAND_MAX_PX


# ── Eje del perfil horizontal ───────────────────────────────────────────────────────────────

def test_lambda_axis_only_in_first_order():
    axis = np.linspace(500.0, 600.0, W)
    a = ea.profile_axis(si.FIRST_ORDER, axis, W)
    assert a.kind == "lambda" and a.values is axis
    for mode in (si.SPECULAR, si.UNKNOWN):
        a = ea.profile_axis(mode, axis, W)
        assert a.kind == "pixel" and a.reason
        np.testing.assert_array_equal(a.values, np.arange(W))


@pytest.mark.parametrize("axis", [None, np.linspace(500, 600, W + 1), np.full(W, np.nan),
                                  np.r_[np.linspace(500, 600, W - 1), 550.0]])
def test_invalid_axis_falls_back_to_pixels_with_a_reason(axis):
    a = ea.profile_axis(si.FIRST_ORDER, axis, W)
    assert a.kind == "pixel" and a.reason


def test_descending_axis_is_valid():
    a = ea.profile_axis(si.FIRST_ORDER, np.linspace(600.0, 500.0, W), W)
    assert a.kind == "lambda"


# ── Ajuste gaussiano ────────────────────────────────────────────────────────────────────────

def test_fit_in_first_order_reports_nm_with_local_dispersion():
    f = _frame(x0=100.0, sx=3.0)
    prof = ea.row_profile(f, 30, 3)
    axis = ea.profile_axis(si.FIRST_ORDER, np.linspace(500.0, 500.0 + 0.1 * (W - 1), W), W)
    fit = ea.fit_profile(prof, seed_px=98, axis=axis)
    assert fit.result.success and fit.unit == "nm"
    assert fit.center_px == pytest.approx(100.0, abs=0.1)
    assert fit.center == pytest.approx(510.0, abs=0.01)
    assert fit.fwhm == pytest.approx(0.1 * 2.3548 * 3.0, rel=0.05)
    assert "SEEDED_BY_OPERATOR" in fit.result.flags


def test_fit_in_zero_order_reports_px_and_um():
    f = _frame(x0=100.0, sx=3.0)
    prof = ea.row_profile(f, 30, 1)
    fit = ea.fit_profile(prof, seed_px=100, axis=ea.profile_axis(si.SPECULAR, None, W))
    assert fit.unit == "µm"
    assert fit.fwhm_px == pytest.approx(2.3548 * 3.0, rel=0.05)
    assert fit.fwhm == pytest.approx(fit.fwhm_px * 8.0)


def test_vertical_fit_is_spatial():
    f = _frame(y0=30.0, sy=5.0)
    prof = ea.column_profile(f, 100, 3)
    fit = ea.fit_profile(prof, seed_px=30, axis=None)
    assert fit.result.success and fit.unit == "µm"
    assert fit.center_px == pytest.approx(30.0, abs=0.15)


def test_fit_flags_saturation_and_does_not_invent_a_result():
    prof = ea.row_profile(_frame(), 30, 1)
    fit = ea.fit_profile(prof, seed_px=100, axis=None, saturated=True)
    assert not fit.result.success and "SATURATED" in fit.result.flags
    assert np.isnan(fit.center) and np.isnan(fit.fwhm)


def test_fit_model_reconstructs_the_line():
    prof = ea.row_profile(_frame(x0=100.0, sx=3.0), 30, 1)
    fit = ea.fit_profile(prof, seed_px=100, axis=None)
    x, y = ea.fit_model_curve(fit)
    assert x.size > 5 and np.max(y) == pytest.approx(np.max(prof), rel=0.05)


# ── Saturación sobre el crudo ───────────────────────────────────────────────────────────────

def test_raw_saturation_uses_absolute_counts_and_counts_clipped_pixels():
    raw = np.full((10, 10), 500.0)
    raw[2, 2] = 0.62 * 16383
    s = ea.raw_saturation(raw)
    assert s.peak_counts == pytest.approx(0.62 * 16383) and s.level == "warn" and s.n_clipped == 0
    raw[3, 3] = raw[4, 4] = 16383
    s = ea.raw_saturation(raw)
    assert s.level == "alarm" and s.n_clipped == 2 and s.frac == pytest.approx(1.0)
    assert ea.raw_saturation(np.full((4, 4), 500.0)).level == "ok"


# ── Fondo: mismas condiciones ───────────────────────────────────────────────────────────────

def _settings(**kw):
    base = dict(exposure_s=0.1, em_gain=0, output_amplifier=0, preamp_index=1, hs_index=0, vs_index=1,
                read_mode=4, grating=1, center_nm=633.0, shape=(H, W))
    base.update(kw)
    return ea.CameraSettings(**base)


def test_background_valid_only_under_the_same_conditions():
    bg = ea.Background(np.zeros((H, W), np.float32), 10, _settings(), 0, 9, 1.0, "obturador cerrado (USB)")
    assert ea.background_status(bg, _settings()) == (True, "")
    for kw, word in [(dict(exposure_s=0.2), "exposición"), (dict(em_gain=10), "ganancia EM"),
                     (dict(output_amplifier=1), "amplificador"), (dict(preamp_index=2), "preamplificador"),
                     (dict(hs_index=1), "HS"), (dict(vs_index=0), "VS"), (dict(read_mode=0), "modo de lectura"),
                     (dict(grating=2), "red"), (dict(center_nm=700.0), "λc"), (dict(shape=(1, W)), "forma")]:
        ok, reason = ea.background_status(bg, _settings(**kw))
        assert not ok and word in reason, kw


def test_background_is_invalid_if_a_setting_cannot_be_read():
    bg = ea.Background(np.zeros((H, W), np.float32), 10, _settings(), 0, 9, 1.0, "")
    ok, reason = ea.background_status(bg, _settings(em_gain=None))
    assert not ok and "no se pudo leer" in reason
    assert ea.background_status(None, _settings()) == (False, "sin fondo")


def test_exposure_tolerance_is_relative():
    bg = ea.Background(np.zeros((H, W), np.float32), 10, _settings(exposure_s=0.1), 0, 9, 1.0, "")
    assert ea.background_status(bg, _settings(exposure_s=0.1 * (1 + 1e-9)))[0]


def test_snapshot_reads_camera_and_spectrometer_and_tolerates_failures():
    class Cam:
        def get_exposure_time_checked(self): return (20002, 0.1)
        def get_emccd_gain(self): return (20002, 5)
        def get_output_amplifier(self): return 0
        def get_preamp_gain_index(self): return 1
        def get_hs_speed_index(self): return 0
        def get_vs_speed_index(self): raise RuntimeError("sin lectura")
        def get_read_mode(self): return 4

    class Spec:
        def ShamrockGetGrating(self, dev): return (20202, 2)
        def ShamrockGetWavelength(self, dev): return (20202, 650.0)

    s = ea.snapshot_settings(Cam(), Spec(), (H, W))
    assert (s.exposure_s, s.em_gain, s.output_amplifier, s.preamp_index, s.hs_index) == (0.1, 5, 0, 1, 0)
    assert s.vs_index is None and s.read_mode == 4 and s.grating == 2 and s.center_nm == 650.0 and s.shape == (H, W)


def test_background_accumulator_averages_distinct_frames():
    acc = ea.BackgroundAccumulator(3, _settings(), "obturador cerrado (USB)")
    assert acc.add(np.full((H, W), 1.0), 5) is None
    assert acc.add(np.full((H, W), 1.0), 5) is None           # mismo índice: no se cuenta dos veces
    assert acc.add(np.full((H, W), 2.0), 6) is None
    bg = acc.add(np.full((H, W), 6.0), 7)
    assert bg.n_frames == 3 and bg.first_index == 5 and bg.last_index == 7
    np.testing.assert_allclose(bg.data, 3.0)
    assert bg.data.dtype == np.float32


def test_background_accumulator_rejects_a_shape_change():
    acc = ea.BackgroundAccumulator(3, _settings(), "")
    acc.add(np.zeros((H, W)), 0)
    with pytest.raises(ValueError):
        acc.add(np.zeros((1, W)), 1)


# ── Traza en el tiempo ──────────────────────────────────────────────────────────────────────

def test_trace_value_row_or_roi():
    f = np.arange(H * W, dtype=float).reshape(H, W)
    assert ea.trace_value(f, ea.TraceSource("row", 7)) == pytest.approx(f[7].mean())
    assert ea.trace_value(f, ea.TraceSource("roi", 10, 20)) == pytest.approx(f[10:20].mean())
    assert ea.trace_value(f, ea.TraceSource("roi", 20, 20)) == pytest.approx(f[20].mean())   # al menos una fila


def test_trace_buffer_trims_by_time_and_windows():
    tr = ea.RoiTrace(max_s=10.0)
    for i in range(30):
        tr.append(float(i), i, float(i) * 2)
    t, v = tr.points(window_s=5.0)
    np.testing.assert_allclose(t, [24, 25, 26, 27, 28, 29])
    assert len(tr) == 11                                          # recorta a 10 s
    tr.clear()
    t, v = tr.points(60.0)
    assert t.size == 0


# ── Niveles ─────────────────────────────────────────────────────────────────────────────────

def test_display_levels_modes():
    f = _frame()
    assert ea.display_levels(f, "manual") is None
    lo, hi = ea.display_levels(f, "auto")
    assert lo < hi
    assert ea.display_levels(f, "adc") == (0.0, 16383.0)
    with pytest.raises(ValueError):
        ea.display_levels(f, "otro")


# ── Guardado ────────────────────────────────────────────────────────────────────────────────

def test_save_keeps_raw_and_background_apart_and_records_provenance(tmp_path):
    h5py = pytest.importorskip("h5py")
    raw = _frame().astype(np.float32)
    bg = ea.Background(np.full((H, W), 500.0, np.float32), 10, _settings(), 3, 12, 5.0, "obturador cerrado (USB)")
    axis = ea.profile_axis(si.FIRST_ORDER, np.linspace(500.0, 520.0, W), W)
    path = ea.save_exploration_h5(tmp_path / "x.h5", raw=raw, background=bg, subtract=True, axis=axis,
                                  cuts={"horizontal": raw[30], "vertical": raw[:, 100]},
                                  metadata={"frame_index": 42, "display_flip_x": True, "ruler": (100, 30)},
                                  full_info={"temperature_monitor": -60.0, "amp_mode": (0, 14, "EM")})
    with h5py.File(path, "r") as f:
        np.testing.assert_array_equal(f["frame/raw"][()], raw)
        np.testing.assert_array_equal(f["frame/background"][()], bg.data)
        assert f["frame/background"].attrs["n_frames"] == 10
        assert "exposición" in f["frame/background"].attrs["settings_json"]
        np.testing.assert_allclose(f["axis/wavelength_nm"][()], axis.values)
        assert f["cuts/horizontal"].shape == (W,)
        a = f.attrs
        assert a["provenance"] == "EXPERIMENTAL" and a["subtract_background"] and a["display_flip_x"]
        assert a["frame_index"] == 42
        info = json.loads(a["camera_full_info_json"])
        assert info["temperature_monitor"] == -60.0
        assert "software_version" in a


def test_save_without_background_or_lambda(tmp_path):
    h5py = pytest.importorskip("h5py")
    raw = _frame().astype(np.float32)
    path = ea.save_exploration_h5(tmp_path / "y.h5", raw=raw, background=None, subtract=False,
                                  axis=ea.profile_axis(si.SPECULAR, None, W), cuts={}, metadata={}, full_info={})
    with h5py.File(path, "r") as f:
        assert "frame/background" not in f and "axis/wavelength_nm" not in f
        assert f.attrs["axis_kind"] == "pixel"


def test_default_save_path_is_timestamped_in_the_exploration_folder(tmp_path):
    import datetime as dt
    p = ea.default_save_path(tmp_path / "exploration", now=dt.datetime(2026, 9, 30, 14, 5, 9))
    assert p == tmp_path / "exploration" / "exploration_20260930_140509.h5"
