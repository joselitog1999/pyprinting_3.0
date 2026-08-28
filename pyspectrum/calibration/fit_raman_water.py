# -*- coding: utf-8 -*-
"""
fit_raman_water.py — Ajuste Lorentziano / Gaussiano para la Banda Raman de Agua
PySpectrum 3.0 — UNSAM Nanofotónica
"""
from __future__ import annotations
import numpy as np
from scipy.optimize import curve_fit
import scipy.signal as sig
from typing import Tuple


def smooth_signal(signal: np.ndarray, window: int = 15, deg: int = 2, repetitions: int = 1) -> np.ndarray:
    for _ in range(repetitions):
        signal = sig.savgol_filter(signal, window, deg, mode='mirror')
    return signal


def lorentz(x, I, gamma, x0, C):
    return (1.0 / np.pi) * I * (gamma / 2.0)**2 / ((x - x0)**2 + (gamma / 2.0)**2) + C


def three_lorentz(x, I, gamma, x0, I_2, I_3, C):
    a = (1.0 / np.pi) * I_2 * (15.5 / 2.0)**2 / ((x - 649.0)**2 + (15.2 / 2.0)**2)
    b = (1.0 / np.pi) * I_3 * (183.0 / 2.0)**2 / ((x - 702.0)**2 + (183.0 / 2.0)**2)
    return (1.0 / np.pi) * I * (gamma / 2.0)**2 / ((x - x0)**2 + (gamma / 2.0)**2) + a + b + C


def calc_r2(observed: np.ndarray, fitted: np.ndarray) -> float:
    avg_y = np.mean(observed)
    ssres = np.sum((observed - fitted)**2)
    sstot = np.sum((observed - avg_y)**2)
    return 1.0 - (ssres / sstot) if sstot != 0 else 0.0


def fit_signal_raman(wavelength_np: np.ndarray, signal_np: np.ndarray,
                     ends_notch: float = 540.0, final_wave: float = 800.0) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Ajusta la señal Raman de agua y nanopartícula en el rango Stokes.
    """
    sort_idx = np.argsort(wavelength_np)
    wave_sorted = wavelength_np[sort_idx]
    spec_sorted = signal_np[sort_idx]

    mask = (wave_sorted > ends_notch + 2.0) & (wave_sorted <= final_wave - 2.0)
    wave_stokes = wave_sorted[mask]
    spec_stokes = spec_sorted[mask]

    if len(wave_stokes) < 10:
        return wave_sorted, spec_sorted, np.array([0, 0, 0, 0, 0, 0])

    init_params = np.array([2500.0, 50.0, 550.0, 100.0, 100.0, 450.0], dtype=np.float64)
    bounds = ([0, 0, 500, 0, 0, 0], [20000, 300, 1000, 20000, 20000, 1000])

    try:
        best_params, _ = curve_fit(three_lorentz, wave_stokes, spec_stokes, p0=init_params, bounds=bounds, maxfev=2000)
        wave_fitted = np.linspace(wave_stokes[0] - 10, wave_stokes[-1] + 10, 500)
        lorentz_fitted = three_lorentz(wave_fitted, *best_params)
        return wave_fitted, lorentz_fitted, best_params
    except Exception as e:
        print(f"[Raman Fit] Advertencia: ajuste no convergió ({e})")
        return wave_stokes, spec_stokes, init_params
