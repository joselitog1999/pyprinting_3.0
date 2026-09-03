# -*- coding: utf-8 -*-
"""
test_raman_engine.py — Pruebas Unitarias del Motor Raman & SERS
PyPrinting 3.0 — UNSAM Nanofotónica
"""
import os
import sys
import math
import numpy as np
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from core.raman_engine import (
    parse_andor_solis_file,
    wavelength_to_raman_shift,
    raman_shift_to_wavelength,
    remove_cosmic_rays,
    baseline_asls,
    baseline_airpls,
    baseline_modpoly,
    baseline_derivative,
    baseline_rolling_ball,
    smooth_savgol,
    smooth_fourier,
    smooth_whittaker,
    smooth_gaussian,
    detect_peaks_spectrum,
    fit_peak_profile,
    calculate_photothermal_temperature,
    compute_dual_cursor_metrics,
    RAMAN_REFERENCE_STANDARDS
)

def test_parse_real_andor_file():
    asc_path = BASE_DIR / "reserva" / "90%_in_red_10s_3_em.asc"
    assert asc_path.exists(), f"No se encontró el archivo de prueba: {asc_path}"
    
    metadata, wls, counts = parse_andor_solis_file(asc_path)
    assert len(wls) == 1004, f"Se esperaban 1004 puntos, se obtuvieron {len(wls)}"
    assert len(counts) == 1004
    assert "Exposure Time (secs)" in metadata or "Date and Time" in metadata
    assert np.all(wls > 0), "Las longitudes de onda deben ser positivas"
    assert np.all(counts > 0), "Las cuentas deben ser positivas"
    print(f"PASS: Archivo real Andor Solis parseado correctamente ({len(wls)} puntos, {len(metadata)} metadatos).")

def test_raman_shift_conversions():
    laser_nm = 532.0
    wl = 547.072  # Aproximadamente la banda fonónica del silicio
    shift = wavelength_to_raman_shift(wl, laser_nm)
    expected_shift = (1.0 / 532.0 - 1.0 / 547.072) * 1e7
    assert math.isclose(shift, expected_shift, rel_tol=1e-5)
    
    # Conversión inversa
    wl_recovered = raman_shift_to_wavelength(shift, laser_nm)
    assert math.isclose(wl_recovered, wl, rel_tol=1e-5)
    print(f"PASS: Conversión Raman Shift (532 nm -> 547.07 nm = {shift:.2f} cm^-1) y reconversión exacta.")

def test_cosmic_ray_removal():
    x = np.linspace(500, 700, 300)
    y = 1000.0 + 50.0 * np.sin(x / 10.0) + np.random.normal(0, 5, len(x))
    # Inyectar spike cósmico de 50.000 cuentas en el índice 150
    spike_idx = 150
    y[spike_idx] += 50000.0
    
    y_clean, mask = remove_cosmic_rays(y, threshold=6.0)
    assert mask[spike_idx], "El spike cósmico debería haber sido detectado"
    assert y_clean[spike_idx] < 2000.0, f"El spike debería haberse reducido drásticamente: {y_clean[spike_idx]}"
    print("PASS: Eliminación de rayos cósmicos validada con éxito.")

def test_baseline_corrections():
    x = np.linspace(100, 3000, 500)
    # Fondo de fluorescencia cuadrático + picos Raman
    fluorescence = 10000.0 + 5.0 * (x - 1000.0)**2 / 1000.0
    peaks = 5000.0 * np.exp(-0.5 * ((x - 1078.0) / 15.0)**2) + 8000.0 * np.exp(-0.5 * ((x - 1588.0) / 20.0)**2)
    y = fluorescence + peaks
    
    b_asls = baseline_asls(y, lam=1e5, p=0.001)
    assert len(b_asls) == len(y)
    idx_p2 = np.argmin(np.abs(x - 1588.0))
    assert y[idx_p2] - b_asls[idx_p2] > 5000.0, "La línea base debe sustraer el pico correctamente"
    assert np.mean(np.abs(b_asls - fluorescence)) < 800.0, "La línea base debe aproximar el fondo de fluorescencia"
    
    b_air = baseline_airpls(y, lam=1e6)
    assert len(b_air) == len(y)
    
    b_poly = baseline_modpoly(y, x, poly_order=3)
    assert len(b_poly) == len(y)
    
    b_roll = baseline_rolling_ball(y, radius=40)
    assert len(b_roll) == len(y)
    print("PASS: Algoritmos de línea base (AsLS, AirPLS, ModPoly, Rolling-Ball) verificados.")

def test_smoothers():
    y = np.sin(np.linspace(0, 10, 200)) + np.random.normal(0, 0.2, 200)
    y_sg = smooth_savgol(y, window_length=15, polyorder=3)
    assert len(y_sg) == len(y)
    
    y_fft = smooth_fourier(y, cutoff_fraction=0.2, filter_type="lowpass")
    assert len(y_fft) == len(y)
    
    y_whit = smooth_whittaker(y, lam=1e2)
    assert len(y_whit) == len(y)
    
    y_gauss = smooth_gaussian(y, sigma=2.0)
    assert len(y_gauss) == len(y)
    print("PASS: Suavizados (Savitzky-Golay, Fourier FFT, Whittaker, Gaussiano) verificados.")

def test_peak_finding_and_fitting():
    x = np.linspace(500, 1800, 600)
    center_true = 1078.0
    fwhm_true = 16.0
    amp_true = 4500.0
    # Banda 4-MBA simulada (Lorentziana pura o Voigt)
    y = amp_true * ((fwhm_true/2)**2) / ((x - center_true)**2 + (fwhm_true/2)**2) + 100.0
    
    peaks = detect_peaks_spectrum(x, y, prominence=500.0)
    assert len(peaks) >= 1
    p0 = peaks[0]
    assert math.isclose(p0["position"], center_true, abs_tol=5.0)
    
    fit_res = fit_peak_profile(x, y - 100.0, center_guess=center_true, fwhm_guess=fwhm_true, model_type="pseudo_voigt")
    assert fit_res is not None
    assert math.isclose(fit_res["center"], center_true, abs_tol=1.0)
    assert fit_res["r_squared"] > 0.98
    print(f"PASS: Detección y ajuste de pico Pseudo-Voigt (Centro = {fit_res['center']:.2f} cm^-1, R^2 = {fit_res['r_squared']:.4f}).")

def test_cropping():
    from core.raman_engine import crop_spectrum
    x = np.linspace(100, 3000, 500)
    y = np.ones(500) * 50.0

    # Recorte por coordenadas físicas [500, 1800]
    x_c, y_c, mask = crop_spectrum(x, y, x_min=500.0, x_max=1800.0)
    assert x_c.min() >= 500.0
    assert x_c.max() <= 1800.0
    assert len(x_c) < len(x)

    # Recorte por poda de bordes (trim left 20, right 30)
    x_t, y_t, mask_t = crop_spectrum(x, y, trim_left_pts=20, trim_right_pts=30)
    assert len(x_t) == 500 - 50
    assert mask_t[:20].sum() == 0
    assert mask_t[-30:].sum() == 0
    print("PASS: Pre-procesado de recorte espectral (crop_spectrum) validado al 100%.")

def test_multi_peak_deconvolution():
    from core.raman_engine import fit_multi_peak_profile
    x = np.linspace(1000, 1700, 400)
    # Doblete característico D y G de carbón
    p1 = 2000.0 * np.exp(-0.5 * ((x - 1350.0) / 20.0)**2)
    p2 = 3500.0 * np.exp(-0.5 * ((x - 1580.0) / 18.0)**2)
    y = p1 + p2

    peaks = detect_peaks_spectrum(x, y, prominence=500.0, width_min_units=10.0, width_max_units=60.0, sort_by="position")
    assert len(peaks) == 2
    assert math.isclose(peaks[0]["position"], 1350.0, abs_tol=5.0)
    assert math.isclose(peaks[1]["position"], 1580.0, abs_tol=5.0)

    # Deconvolución multi-pico
    fit_res = fit_multi_peak_profile(x, y, peak_centers=[1350.0, 1580.0], model_type="pseudo_voigt")
    assert fit_res is not None
    assert fit_res["r_squared"] > 0.99
    assert len(fit_res["peaks"]) == 2
    assert math.isclose(fit_res["peaks"][0]["center"], 1350.0, abs_tol=2.0)
    assert math.isclose(fit_res["peaks"][1]["center"], 1580.0, abs_tol=2.0)
    print(f"PASS: Deconvolución Multi-Pico (D y G: R^2 = {fit_res['r_squared']:.4f}) validada al 100%.")

def test_dual_cursor_and_temperature():
    x = np.linspace(200, 2000, 1000)
    y = np.exp(-0.5 * ((x - 520.7) / 10.0)**2) * 1000.0
    metrics = compute_dual_cursor_metrics(x, y, pos_a=500.0, pos_b=540.0)
    assert metrics["delta_x"] == 40.0
    assert metrics["integrated_area"] > 0.0
    
    # Temperatura fototérmica a T = 350 K (76.85 °C)
    t_k, t_c = calculate_photothermal_temperature(
        shift_cm1=520.7,
        intensity_stokes=10000.0,
        intensity_anti_stokes=500.0,
        laser_nm=532.0
    )
    assert not math.isnan(t_k)
    assert t_k > 0
    print(f"PASS: Métricas duales e inferencia fototérmica Anti-Stokes / Stokes (T = {t_k:.1f} K = {t_c:.1f} °C).")

if __name__ == "__main__":
    test_parse_real_andor_file()
    test_raman_shift_conversions()
    test_cosmic_ray_removal()
    test_baseline_corrections()
    test_smoothers()
    test_cropping()
    test_peak_finding_and_fitting()
    test_multi_peak_deconvolution()
    test_dual_cursor_and_temperature()
    print("\n=======================================================")
    print("TODAS LAS PRUEBAS DE RAMAN ENGINE SUPERADAS AL 100%!")
    print("=======================================================")
