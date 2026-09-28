# -*- coding: utf-8 -*-
"""Cada función que los drivers de PySpectrum llaman por ctypes existe en la DLL del repo (DEC-040).

Las DLL de `pyspectrum/drivers/libs/` son idénticas byte a byte a las del legado que corre en el
banco (verificado por SHA-256 el 2026-09-28): atmcd64d.dll 2.104.33065.0 y ShamrockCIF.dll /
atshamrock.dll 2.103.30023.0, todas x64. Se leen sin cargarlas (`tools/pe_exports.py`). Este test
habría detectado `ShamrockGetFlipper` (C-07) y `SetRandomTrack`, que no existen.
"""
import re
from pathlib import Path

import pytest

from tools.pe_exports import read_pe

ROOT = Path(__file__).resolve().parent.parent

CASES = [
    ("pyspectrum/drivers/andor_ccd_driver.py", "pyspectrum/drivers/libs/atmcd64d.dll"),
    ("pyspectrum/drivers/shamrock_driver.py", "pyspectrum/drivers/libs/Windows/64/ShamrockCIF.dll"),
]


def _called_functions(driver: Path):
    return sorted(set(re.findall(r"self\._dll\.([A-Za-z_]\w*)\(", driver.read_text(encoding="utf-8"))))


@pytest.mark.parametrize("driver, dll", CASES)
def test_every_ctypes_call_is_exported_by_the_dll(driver, dll):
    arch, exports = read_pe(ROOT / dll)
    assert arch == "x64", f"{dll} es {arch}; el Python del proyecto es de 64 bits"
    called = _called_functions(ROOT / driver)
    assert called, f"no encontré llamadas a self._dll en {driver}"
    missing = [name for name in called if name not in exports]
    assert missing == [], f"{driver} llama a funciones que {dll} no exporta: {missing}"


def test_the_shamrock_argtypes_table_names_exported_functions():
    from pyspectrum.drivers.shamrock_driver import _SHAMROCK_ARGTYPES
    _, exports = read_pe(ROOT / "pyspectrum/drivers/libs/Windows/64/ShamrockCIF.dll")
    assert [n for n in _SHAMROCK_ARGTYPES if n not in exports] == []


def test_the_reader_detects_a_missing_function():
    """Control negativo: un nombre inventado no aparece entre las exportaciones."""
    _, exports = read_pe(ROOT / "pyspectrum/drivers/libs/atmcd64d.dll")
    assert "SetRandomTracks" in exports and "SetRandomTrack" not in exports
    assert "GetReadMode" not in exports  # el SDK no tiene getter del modo de lectura (D-15)
