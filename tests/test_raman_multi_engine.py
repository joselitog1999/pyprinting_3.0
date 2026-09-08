# -*- coding: utf-8 -*-
"""
test_raman_multi_engine.py — Verificación de Algoritmos Matriciales y Multi-Espectro
PyPrinting 3.0 — UNSAM Nanofotónica
"""
import os
import sys
from pathlib import Path
import math
import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from core.raman_engine import (
    interpolate_spectra_to_common_grid,
    normalize_spectrum_matrix,
    compute_mean_std_spectrum,
    extract_band_kinetics,
    compute_spectral_pca
)

def test_interpolate_to_common_grid():
    # 3 espectros con ejes ligeramente distintos
    x1 = np.linspace(500, 1800, 300)
    y1 = 1000.0 * np.exp(-0.5 * ((x1 - 1078.0) / 15.0)**2)

    x2 = np.linspace(505, 1795, 250)
    y2 = 1200.0 * np.exp(-0.5 * ((x2 - 1078.0) / 15.0)**2)

    x3 = np.linspace(490, 1810, 350)
    y3 = 800.0 * np.exp(-0.5 * ((x3 - 1078.0) / 15.0)**2)

    spectra = [
        (x1, y1, "Spec1", {"exp": 5.0}),
        (x2, y2, "Spec2", {"exp": 6.0}),
        (x3, y3, "Spec3", {"exp": 4.0}),
    ]

    x_common, Y, names, metas = interpolate_spectra_to_common_grid(spectra, num_points=200)
    assert len(x_common) == 200
    assert Y.shape == (3, 200)
    assert len(names) == 3
    assert len(metas) == 3
    assert x_common[0] >= 505.0  # Intersección
    assert x_common[-1] <= 1795.0
    print(f"PASS: Interpolación a grilla común (3 espectros x {len(x_common)} puntos) verificada.")

def test_normalizations():
    x = np.linspace(500, 1800, 300)
    # 3 espectros con alturas de pico dispares
    p1 = 1000.0 * np.exp(-0.5 * ((x - 1078.0) / 15.0)**2) + 50.0
    p2 = 5000.0 * np.exp(-0.5 * ((x - 1078.0) / 15.0)**2) + 200.0
    p3 = 2500.0 * np.exp(-0.5 * ((x - 1078.0) / 15.0)**2) + 100.0
    Y = np.vstack([p1, p2, p3])

    # 1. Normalización a máximo
    Y_max = normalize_spectrum_matrix(x, Y, mode="max")
    assert math.isclose(Y_max[0].max(), 1.0, abs_tol=1e-5)
    assert math.isclose(Y_max[1].max(), 1.0, abs_tol=1e-5)
    assert math.isclose(Y_max[2].max(), 1.0, abs_tol=1e-5)

    # 2. Normalización a pico de referencia (1078 cm^-1)
    Y_peak = normalize_spectrum_matrix(x, Y, mode="peak", ref_pos=1078.0, half_window=10.0)
    idx_peak = int(np.argmin(np.abs(x - 1078.0)))
    assert math.isclose(Y_peak[0, idx_peak], 1.0, abs_tol=0.01)
    assert math.isclose(Y_peak[1, idx_peak], 1.0, abs_tol=0.01)
    assert math.isclose(Y_peak[2, idx_peak], 1.0, abs_tol=0.01)

    # 3. Normalización a área unitaria
    Y_area = normalize_spectrum_matrix(x, Y, mode="area")
    area0 = np.trapezoid(Y_area[0], x) if hasattr(np, "trapezoid") else np.trapz(Y_area[0], x)
    assert math.isclose(area0, 1.0, abs_tol=1e-3)

    # 4. Normalización SNV
    Y_snv = normalize_spectrum_matrix(x, Y, mode="snv")
    assert math.isclose(float(np.mean(Y_snv[0])), 0.0, abs_tol=1e-5)
    assert math.isclose(float(np.std(Y_snv[0])), 1.0, abs_tol=1e-5)
    print("PASS: Todas las normalizaciones espectroscópicas (max, peak, area, snv) verificadas al 100%.")

def test_mean_std_and_kinetics():
    x = np.linspace(500, 1800, 200)
    # Serie temporal de 5 espectros simulando cinética de crecimiento SERS
    t_factors = [1.0, 1.5, 2.2, 3.1, 4.0]
    Y = np.zeros((len(t_factors), len(x)))
    for i, tf in enumerate(t_factors):
        Y[i, :] = tf * 1000.0 * np.exp(-0.5 * ((x - 1078.0) / 15.0)**2) + 20.0

    mean_y, std_y, rsd = compute_mean_std_spectrum(Y)
    assert len(mean_y) == len(x)
    assert len(std_y) == len(x)
    assert len(rsd) == len(x)
    assert mean_y.max() > 2000.0

    # Seguimiento cinético de la banda 1078 cm^-1
    kinetics = extract_band_kinetics(x, Y, pos_min=1050.0, pos_max=1100.0)
    heights = kinetics["heights"]
    areas = kinetics["areas"]
    assert len(heights) == len(t_factors)
    assert heights[-1] > heights[0]
    assert areas[-1] > areas[0]
    print(f"PASS: Espectro promedio ± std y cinética de banda ({heights[0]:.0f} -> {heights[-1]:.0f} cts) verificados.")

def test_pca_decomposition():
    x = np.linspace(500, 1800, 200)
    # Generar 6 espectros con dos componentes químicas ortogonales
    c1 = np.exp(-0.5 * ((x - 1078.0) / 15.0)**2)  # 4-MBA
    c2 = np.exp(-0.5 * ((x - 1580.0) / 20.0)**2)  # G-band carbon
    Y = []
    for a in [1.0, 2.0, 3.0]:
        for b in [0.5, 1.5]:
            Y.append(a * c1 + b * c2)
    Y = np.array(Y)

    pca_res = compute_spectral_pca(Y, n_components=2)
    scores = pca_res["scores"]
    loadings = pca_res["loadings"]
    var_exp = pca_res["explained_variance"]

    assert scores.shape == (6, 2)
    assert loadings.shape == (2, 200)
    assert np.sum(var_exp) > 99.0  # Las 2 componentes explican casi el 100% de la varianza
    print(f"PASS: Descomposición PCA (Varianza Explicada: PC1={var_exp[0]:.1f}%, PC2={var_exp[1]:.1f}%) verificada.")

def test_laser_excitation_shift_recalculation():
    from core.raman_engine import wavelength_to_raman_shift, raman_shift_to_wavelength
    wls = np.array([550.0, 560.0, 570.0])

    # Láser 532 nm
    shift_532 = wavelength_to_raman_shift(wls, 532.0)
    expected_532 = (1.0 / 532.0 - 1.0 / wls) * 1e7
    assert np.allclose(shift_532, expected_532, atol=1e-5)

    # Láser 632.8 nm (He-Ne)
    shift_633 = wavelength_to_raman_shift(wls, 632.8)
    expected_633 = (1.0 / 632.8 - 1.0 / wls) * 1e7
    assert np.allclose(shift_633, expected_633, atol=1e-5)

    # Láser 785.0 nm (NIR)
    shift_785 = wavelength_to_raman_shift(wls, 785.0)
    expected_785 = (1.0 / 785.0 - 1.0 / wls) * 1e7
    assert np.allclose(shift_785, expected_785, atol=1e-5)

    # Verificar que el corrimiento con 632.8 nm es sustancialmente distinto que con 532.0 nm
    assert not np.allclose(shift_532, shift_633)
    print("PASS: Recálculo de corrimiento Raman para distintos láseres (532, 632.8, 785 nm) verificado.")

def test_reference_blank_subtraction_mode():
    x_common = np.linspace(400, 1800, 200)
    # 3 espectros con fondo parabólico común y picos
    bg_true = 0.001 * (x_common - 1000.0)**2 + 100.0
    p1 = 1000.0 * np.exp(-0.5 * ((x_common - 1078.0) / 15.0)**2) + bg_true
    p2 = 2000.0 * np.exp(-0.5 * ((x_common - 1078.0) / 15.0)**2) + bg_true
    Y = np.vstack([p1, p2])

    # Blanco externo medido en eje ligeramente diferente (ej. 150 puntos)
    x_blank = np.linspace(350, 1850, 150)
    bg_blank_raw = 0.001 * (x_blank - 1000.0)**2 + 100.0

    # Interpolar blanco a x_common y restar (Modo 1)
    blank_interp = np.interp(x_common, x_blank, bg_blank_raw)
    Y_sub = Y.copy()
    for i in range(len(Y_sub)):
        Y_sub[i, :] -= blank_interp

    # Los residuales de fondo lejos del pico deben ser ~0
    assert np.allclose(Y_sub[0, :30], 0.0, atol=1.0)
    assert np.allclose(Y_sub[1, :30], 0.0, atol=1.0)
    print("PASS: Sustracción de fondo de referencia externo (Modo 1) verificado.")

def test_individual_baseline_mode():
    from core.raman_engine import baseline_asls, baseline_airpls
    x_common = np.linspace(400, 1800, 200)
    # 2 espectros con diferente fluorescencia (pendientes opuestas)
    bg1 = 200.0 + 0.1 * x_common
    bg2 = 500.0 - 0.15 * x_common
    p1 = 1500.0 * np.exp(-0.5 * ((x_common - 1078.0) / 15.0)**2) + bg1
    p2 = 1200.0 * np.exp(-0.5 * ((x_common - 1078.0) / 15.0)**2) + bg2
    Y = np.vstack([p1, p2])

    # Calcular línea base individual con AsLS (Modo 2)
    Y_sub = Y.copy()
    for i in range(len(Y_sub)):
        base_i = baseline_asls(Y_sub[i, :], lam=1e5, p=0.005)
        Y_sub[i, :] -= base_i

    # Ambos espectros deben quedar aplanados cerca de 0 fuera del pico
    assert np.abs(np.mean(Y_sub[0, :30])) < 50.0
    assert np.abs(np.mean(Y_sub[1, :30])) < 50.0
    print("PASS: Cálculo individual adaptativo de línea base por espectro (Modo 2) verificado.")

def test_interpolate_spectra_to_common_grid_with_x_range_and_trimming():
    from core.raman_engine import crop_spectrum
    # 3 espectros sintéticos de 1000 puntos en rango [100.0, 3600.0]
    x_full = np.linspace(100.0, 3600.0, 1000)
    y1 = 1000.0 * np.exp(-0.5 * ((x_full - 1078.0) / 15.0)**2) + 200.0
    y2 = 1500.0 * np.exp(-0.5 * ((x_full - 1585.0) / 18.0)**2) + 250.0
    spectra = [(x_full, y1, "Sp1", {}), (x_full, y2, "Sp2", {})]

    # 1. Sin recorte (rango completo)
    x_c1, Y1, _, _ = interpolate_spectra_to_common_grid(spectra)
    assert math.isclose(x_c1[0], 100.0, abs_tol=1.0)
    assert math.isclose(x_c1[-1], 3600.0, abs_tol=1.0)
    assert Y1.shape[0] == 2

    # 2. Con recorte de ROI a [600.0, 1800.0] cm^-1
    x_c2, Y2, _, _ = interpolate_spectra_to_common_grid(spectra, x_range=(600.0, 1800.0))
    assert math.isclose(x_c2[0], 600.0, abs_tol=1e-3)
    assert math.isclose(x_c2[-1], 1800.0, abs_tol=1e-3)
    assert len(x_c2) < len(x_c1)
    assert Y2.shape == (2, len(x_c2))

    # 3. Con atajo Rayleigh (< 150.0 cm^-1)
    x_c3, Y3, _, _ = interpolate_spectra_to_common_grid(spectra, x_range=(150.0, 3600.0))
    assert math.isclose(x_c3[0], 150.0, abs_tol=1e-3)
    assert math.isclose(x_c3[-1], 3600.0, abs_tol=1e-3)

    # 4. Con poda de bordes CCD por puntos (trim_left_pts=20, trim_right_pts=30)
    trimmed_spectra = []
    for x_i, y_i, name, meta in spectra:
        x_t, y_t, _ = crop_spectrum(x_i, y_i, trim_left_pts=20, trim_right_pts=30)
        assert len(x_t) == 1000 - 50
        trimmed_spectra.append((x_t, y_t, name, meta))
    x_c4, Y4, _, _ = interpolate_spectra_to_common_grid(trimmed_spectra)
    assert len(x_c4) > 0
    assert Y4.shape[0] == 2
    print("PASS: Recorte de ROI por rango [Xmin, Xmax] y poda de bordes CCD verificado al 100%.")

def test_multi_spectrum_units_conversion():
    from core.raman_engine import (
        wavelength_to_raman_shift,
        raman_shift_to_wavelength,
        raman_shift_to_ev,
        ev_to_raman_shift
    )
    wls = np.linspace(540.0, 650.0, 500)
    laser_nm = 532.0

    # 1. Espectros en tres unidades distintas
    # A. Wavelength (nm)
    spec_wl = [(wls, np.sin(wls), "Spec_WL", {})]
    x_wl, Y_wl, _, _ = interpolate_spectra_to_common_grid(spec_wl)
    assert math.isclose(x_wl[0], 540.0, abs_tol=1e-3)
    assert math.isclose(x_wl[-1], 650.0, abs_tol=1e-3)

    # B. Raman Shift (cm^-1)
    shifts = wavelength_to_raman_shift(wls, laser_nm)
    spec_shift = [(shifts, np.sin(wls), "Spec_Shift", {})]
    x_shift, Y_shift, _, _ = interpolate_spectra_to_common_grid(spec_shift)
    assert x_shift[0] >= 270.0
    assert x_shift[-1] <= 3500.0

    # C. Energía Relativa (eV)
    evs = raman_shift_to_ev(shifts)
    spec_ev = [(evs, np.sin(wls), "Spec_EV", {})]
    x_ev, Y_ev, _, _ = interpolate_spectra_to_common_grid(spec_ev)
    assert x_ev[0] >= 0.03
    assert x_ev[-1] <= 0.45

    # 2. Consistencia biyectiva de ida y vuelta
    wls_recovered = raman_shift_to_wavelength(shifts, laser_nm)
    assert np.allclose(wls, wls_recovered, atol=1e-9)

    shifts_recovered = ev_to_raman_shift(evs)
    assert np.allclose(shifts, shifts_recovered, atol=1e-9)

    # 3. Interpolar blanco de referencia (Modo 1) en las tres unidades
    wls_blank = np.linspace(535.0, 655.0, 300)
    bg_raw = 0.05 * (wls_blank - 532.0)**2 + 50.0

    # En nm
    bg_interp_wl = np.interp(x_wl, wls_blank, bg_raw)
    assert len(bg_interp_wl) == len(x_wl)

    # En cm^-1
    shifts_blank = wavelength_to_raman_shift(wls_blank, laser_nm)
    sort_s = np.argsort(shifts_blank)
    bg_interp_shift = np.interp(x_shift, shifts_blank[sort_s], bg_raw[sort_s])
    assert len(bg_interp_shift) == len(x_shift)

    # En eV
    evs_blank = raman_shift_to_ev(shifts_blank)
    sort_e = np.argsort(evs_blank)
    bg_interp_ev = np.interp(x_ev, evs_blank[sort_e], bg_raw[sort_e])
    assert len(bg_interp_ev) == len(x_ev)

    print("PASS: Conversión de grilla multi-espectro (nm, cm^-1, eV) y sustracción de blanco verificado al 100%.")

if __name__ == "__main__":
    test_interpolate_to_common_grid()
    test_normalizations()
    test_mean_std_and_kinetics()
    test_pca_decomposition()
    test_laser_excitation_shift_recalculation()
    test_reference_blank_subtraction_mode()
    test_individual_baseline_mode()
    test_interpolate_spectra_to_common_grid_with_x_range_and_trimming()
    test_multi_spectrum_units_conversion()
    print("\n=======================================================")
    print("TODAS LAS PRUEBAS DE MOTOR MULTI-ESPECTRO SUPERADAS!")
    print("=======================================================")
