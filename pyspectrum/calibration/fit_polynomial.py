# -*- coding: utf-8 -*-
"""
fit_polynomial.py — Ajuste Polinomial para Detección de Resonancia Plasmónica (SPR)
PySpectrum 3.0 — UNSAM Nanofotónica
"""
from __future__ import annotations
import numpy as np
from typing import Tuple


def calc_r2(observed: np.ndarray, fitted: np.ndarray) -> float:
    avg_y = np.mean(observed)
    ssres = np.sum((observed - fitted)**2)
    sstot = np.sum((observed - avg_y)**2)
    return 1.0 - (ssres / sstot) if sstot != 0 else 0.0


def fit_polynomial(spectrum: np.ndarray, wavelength: np.ndarray,
                   npol: int = 4) -> Tuple[np.ndarray, np.ndarray, float, float]:
    """Ajuste de polinomio de grado npol para determinar la longitud de onda de máxima resonancia."""
    spectrum = np.asarray(spectrum, dtype=np.float64)
    wavelength = np.asarray(wavelength, dtype=np.float64)
    if len(wavelength) < npol + 1:
        return spectrum, wavelength, 0.0, 0.0

    wavelength_fitted = np.linspace(wavelength[0], wavelength[-1], 1000)
    spectrum_interp = np.interp(wavelength_fitted, wavelength, spectrum)

    poly = np.polyfit(wavelength_fitted, spectrum_interp, npol)
    spectrum_fitted = np.polyval(poly, wavelength_fitted)

    r2 = calc_r2(spectrum_interp, spectrum_fitted)
    max_idx = np.argmax(spectrum_fitted)
    max_wavelength = float(wavelength_fitted[max_idx])

    return spectrum_fitted, wavelength_fitted, max_wavelength, r2


def fit_signal_polynomial(wavelength_np: np.ndarray, signal_np: np.ndarray,
                          ends_notch: float = 540.0, final_wave: float = 850.0,
                          npol: int = 4) -> Tuple[np.ndarray, np.ndarray, float]:
    """Filtra rango Stokes y ajusta el polinomio de resonancia SPR."""
    wavelength_np = np.asarray(wavelength_np, dtype=np.float64)
    signal_np = np.asarray(signal_np, dtype=np.float64)
    sort_idx = np.argsort(wavelength_np)
    wave_sorted = wavelength_np[sort_idx]
    spec_sorted = signal_np[sort_idx]

    mask = (wave_sorted > ends_notch) & (wave_sorted <= final_wave)
    wave_stokes = wave_sorted[mask]
    spec_stokes = spec_sorted[mask]

    if len(wave_stokes) < npol + 2:
        return wave_sorted, spec_sorted, 0.0

    spec_fit, wave_fit, lambda_max, r2 = fit_polynomial(spec_stokes, wave_stokes, npol)
    return wave_fit, spec_fit, lambda_max
