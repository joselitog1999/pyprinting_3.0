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

if __name__ == "__main__":
    test_interpolate_to_common_grid()
    test_normalizations()
    test_mean_std_and_kinetics()
    test_pca_decomposition()
    print("\n=======================================================")
    print("TODAS LAS PRUEBAS DE MOTOR MULTI-ESPECTRO SUPERADAS!")
    print("=======================================================")
