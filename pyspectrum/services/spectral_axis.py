# -*- coding: utf-8 -*-
"""Una sola fuente del eje λ para todo PySpectrum 3.0 (paridad con el legado, DEC-054).

Hasta acá había dos fuentes según el módulo: el polinomio de fábrica de la EEPROM del Shamrock
(`ShamrockGetPixelCalibrationCoefficients`) en Step & Glue, Raman, linescan y la calibración, y
`ShamrockGetCalibration` en crecimiento, luminiscencia, dímeros, el mapa hiperespectral y la exploración. Un mismo
pico podía caer en λ distintas según la pestaña. El investigador eligió la EEPROM con 1004 píxeles (2026-11-19).

`spectral_axis()` evalúa la EEPROM, λ(p) = a + b·p + c·p² + d·p³ con p = 0..n−1, y sólo si sus coeficientes no
sirven usa `GetCalibration` como respaldo. Devuelve también la fuente, que cada archivo deja escrita. Nunca
inventa un eje: si ninguna fuente sirve, devuelve None.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

SOURCE_EEPROM = "EEPROM"
SOURCE_GETCALIBRATION = "GetCalibration (respaldo)"


@dataclass(frozen=True)
class SpectralAxis:
    nm: np.ndarray
    source: str

    @property
    def n_pixels(self) -> int:
        return int(self.nm.size)


def _valid(axis, n: int) -> bool:
    """n puntos finitos y estrictamente monótonos (en cualquier sentido: el legado ordenaba por λ antes de usar
    el eje, así que no se supone el sentido). Un eje constante, como el del espejo, no es un eje."""
    a = np.asarray(axis, dtype=np.float64)
    if a.size != n or not np.all(np.isfinite(a)):
        return False
    d = np.diff(a)
    return bool(np.all(d > 0) or np.all(d < 0))


def spectral_axis(spectrometer, n_pixels: int = 1004, device: Optional[int] = None) -> Optional[SpectralAxis]:
    """El eje λ de `n_pixels` puntos y su fuente, o None si no hay uno confiable."""
    from pyspectrum.drivers.shamrock_driver import DEVICE, SHAMROCK_SUCCESS
    dev = DEVICE if device is None else int(device)
    n = int(n_pixels)
    coeffs = getattr(spectrometer, "ShamrockGetPixelCalibrationCoefficients", None)
    if coeffs is not None:
        try:
            ret, a, b, c, d = coeffs(dev)
            if ret == SHAMROCK_SUCCESS and b > 0:
                p = np.arange(n, dtype=np.float64)
                axis = a + b * p + c * p ** 2 + d * p ** 3
                if _valid(axis, n):
                    return SpectralAxis(axis, SOURCE_EEPROM)
            print(f"[Eje λ] La EEPROM no da un eje válido (código {ret}, b={b}): se usa GetCalibration.")
        except Exception as e:
            print(f"[Eje λ] No se pudieron leer los coeficientes de la EEPROM ({e}): se usa GetCalibration.")
    try:
        ret, axis = spectrometer.ShamrockGetCalibration(dev, n)
    except Exception as e:
        print(f"[Eje λ] GetCalibration falló: {e}")
        return None
    axis = np.asarray(axis, dtype=np.float64)
    if ret != SHAMROCK_SUCCESS or not _valid(axis, n):
        print(f"[Eje λ] GetCalibration no da un eje válido (código {ret}, {axis.size} puntos).")
        return None
    return SpectralAxis(axis, SOURCE_GETCALIBRATION)
