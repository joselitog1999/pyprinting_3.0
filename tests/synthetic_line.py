# -*- coding: utf-8 -*-
"""Generador de líneas sintéticas para los tests de la calibración (R2-met §2.4, §5.2).

Una gaussiana **integrada en cada píxel** (erf) con centro conocido, más fondo lineal, ruido de Poisson y
de lectura, con semilla fija. Es el mismo modelo con el que metrología simuló el estimador.
"""
import numpy as np
from scipy.special import erf

N_PX = 1004
READ_NOISE_E = 22.0          # e⁻ rms por píxel a 27 MHz sin EM ([DS-iXon] p. 2)
N_ROWS = 9                   # filas sumadas (la traza ± 4)


def expected_profile(x0, sigma, snr, *, n_px=N_PX, b0=200.0, slope=0.0, rows=N_ROWS, read_noise=READ_NOISE_E):
    """Perfil esperado (sin ruido) de la suma de `rows` filas, y la amplitud usada.

    SNR = altura del pico / σ de una columna de fondo (R2-met §2.4)."""
    sigma_bg = np.sqrt(b0 + rows * read_noise ** 2)
    height = snr * sigma_bg
    area = height * sigma * np.sqrt(2 * np.pi)
    edges = np.arange(n_px + 1) - 0.5
    cdf = 0.5 * (1 + erf((edges - x0) / (np.sqrt(2) * sigma)))
    line = area * np.diff(cdf)
    x = np.arange(n_px)
    return line + b0 + slope * (x - x0), height


def noisy_profile(rng, x0, sigma, snr, *, rows=N_ROWS, read_noise=READ_NOISE_E, **kw):
    mu, _ = expected_profile(x0, sigma, snr, rows=rows, read_noise=read_noise, **kw)
    counts = rng.poisson(np.clip(mu, 0, None)).astype(float)
    counts += rng.normal(0.0, read_noise * np.sqrt(rows), size=mu.shape)
    return counts


def frames_for_profile(rng, x0, sigma, snr, k, **kw):
    """K perfiles independientes con el mismo esperado (una llegada de K cuadros)."""
    return np.stack([noisy_profile(rng, x0, sigma, snr, **kw) for _ in range(k)])


def linear_axis(n_px=N_PX, lambda_center=532.0, dispersion=0.1026, center_px=501.5, descending=False):
    x = np.arange(n_px) - center_px
    d = -dispersion if descending else dispersion
    return lambda_center + d * x
