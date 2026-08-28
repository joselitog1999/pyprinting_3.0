# -*- coding: utf-8 -*-
"""
halogen_lamp.py — Calibración de Lámpara Halógena y Algoritmo de Cosido (Step & Glue)
PySpectrum 3.0 — UNSAM Nanofotónica
"""
from __future__ import annotations
import os
from pathlib import Path
from typing import Tuple, List, Optional
import numpy as np


class HalogenLampCalibration:
    """Gestiona el perfil de referencia de la lámpara halógena para normalización espectral."""

    def __init__(self, data_path: Optional[str] = None):
        self.wave_lamp = np.linspace(450, 950, 1002)
        self.spec_lamp = np.ones_like(self.wave_lamp)
        self.is_loaded = False
        self._load_reference_data(data_path)

    def _load_reference_data(self, data_path: Optional[str] = None):
        if not data_path:
            base = Path(__file__).resolve().parent / "data" / "lamparaIR_450-950_overlap0.2"
            data_path = str(base / "lamparaIR_grade_2.txt")

        p = Path(data_path)
        if p.exists():
            try:
                data = np.loadtxt(str(p), comments="#")
                self.wave_lamp = data[:, 0]
                self.spec_lamp = data[:, 1]
                self.is_loaded = True
                print(f"[Lamp Calibration] Perfil halógeno cargado ({len(self.wave_lamp)} puntos) desde {p.name}")
            except Exception as e:
                print(f"[Lamp Calibration] Error al leer {p} ({e}). Generando perfil sintético.")
                self._generate_synthetic_profile()
        else:
            print(f"[Lamp Calibration] Archivo {p} no encontrado. Generando perfil sintético de cuerpo negro.")
            self._generate_synthetic_profile()

    def _generate_synthetic_profile(self):
        """Genera una curva de lámpara halógena de 3000 K (cuerpo negro)."""
        self.wave_lamp = np.linspace(450, 950, 1002)
        # Ley de Planck aproximada en el rango visible/NIR
        wl_m = self.wave_lamp * 1e-9
        T = 3000.0  # Kelvin
        h = 6.626e-34; c = 3.0e8; k = 1.38e-23
        intensity = (2.0 * h * c**2) / (wl_m**5 * (np.exp((h * c) / (wl_m * k * T)) - 1.0))
        self.spec_lamp = intensity / np.max(intensity) * 50000.0
        self.is_loaded = True

    def get_lamp_profile(self) -> Tuple[np.ndarray, np.ndarray]:
        return self.wave_lamp, self.spec_lamp

    def normalize_spectrum(self, wave: np.ndarray, spec: np.ndarray) -> np.ndarray:
        """Interpola la lámpara a la cuadrícula de longitud de onda del espectro y normaliza."""
        lamp_interp = np.interp(wave, self.wave_lamp, self.spec_lamp)
        # Evitar división por cero
        lamp_interp = np.where(lamp_interp <= 0, 1.0, lamp_interp)
        return spec / lamp_interp


# ── Algoritmo Step and Glue ───────────────────────────────────────────────────

def glue_steps(wave_py: np.ndarray, spec_py: np.ndarray, number_pixel: int = 1002, grade: float = 2.0) -> Tuple[np.ndarray, np.ndarray]:
    """
    Une múltiples espectros discretos obtenidos por Step & Glue con solapamiento ponderado suave.
    """
    if len(spec_py) == 0 or len(wave_py) == 0:
        return np.array([]), np.array([])

    L = int(len(spec_py) / number_pixel)
    if L <= 1:
        return wave_py, spec_py

    n_skip_points = 30
    n = int(n_skip_points / 2)
    valid_pixels = number_pixel - n_skip_points

    spec_steps = np.zeros((valid_pixels, L))
    wave_steps = np.zeros((valid_pixels, L))
    spec_steps_glue = np.zeros((valid_pixels, L))
    wave_steps_glue = np.zeros((valid_pixels, L))

    list_of_inf = np.zeros(L)

    for i in range(L):
        spec = spec_py[i * number_pixel:(i + 1) * number_pixel]
        wave = wave_py[i * number_pixel:(i + 1) * number_pixel]
        spec_steps[:, i] = spec[n:-n]
        wave_steps[:, i] = wave[n:-n]
        spec_steps_glue[:, i] = spec[n:-n]
        wave_steps_glue[:, i] = wave[n:-n]
        list_of_inf[i] = wave_steps[0, i]

    for j in range(L - 1):
        inf = list_of_inf[j + 1]
        wave_tail = wave_steps[:, j]
        desired_range_tail = np.where(wave_tail >= inf)[0]
        m = int(len(desired_range_tail))

        if m > 0:
            weight_h = np.linspace(0, 1, m) ** grade
            weight_t = np.flip(weight_h)
            coef = weight_h + weight_t
            coef = np.where(coef == 0, 1.0, coef)
            weight_h /= coef
            weight_t /= coef

            idx_tail = range(valid_pixels - m, valid_pixels)
            idx_head = range(0, m)

            spec_tail = spec_steps[idx_tail, j]
            wave_t_seg = wave_steps[idx_tail, j]

            spec_head = spec_steps[idx_head, j + 1]
            wave_h_seg = wave_steps[idx_head, j + 1]

            spec_weight = weight_h * spec_head + weight_t * spec_tail

            spec_steps_glue[idx_tail, j] = spec_weight
            wave_steps_glue[idx_tail, j] = wave_t_seg

            spec_steps_glue[idx_head, j + 1] = spec_weight
            wave_steps_glue[idx_head, j + 1] = wave_h_seg

    wave_final = wave_steps_glue.flatten()
    spectrum_final = spec_steps_glue.flatten()

    sort_idx = np.argsort(wave_final)
    wave_sorted = wave_final[sort_idx]
    spec_sorted = spectrum_final[sort_idx]

    return wave_sorted, spec_sorted
