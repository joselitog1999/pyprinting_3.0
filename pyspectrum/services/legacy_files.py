# -*- coding: utf-8 -*-
"""Archivos con los nombres y columnas del PySpectrum legado (paridad, DEC-054).

El investigador pidió que 3.0 deje **los dos formatos** (2026-11-19): los del legado, para que los análisis
existentes sigan funcionando, y los nuevos (`.h5` con todo, encabezados con la corrección y el fondo). Este
módulo escribe sólo los del legado, con su formato exacto, y nada más:

- `NPscan_%03d.tiff`, `gone_NPscan_%03d.tiff`, `back_NPscan_%03d.tiff`: imagen del fotodiodo **cruda**,
  traspuesta como el legado (`Image.fromarray(np.transpose(arr))`, `Luminescence_ps.py:759-777`), en float32;
- `wavelength_<YYYYmmdd_HHMMSS>.txt`: el eje λ, un valor por línea, `%.4f`, sin encabezado
  (`Confocal_Spectrum_ps.py:783-790`);
- `Spectrum_i%04d_j%04d.txt`: el espectro de un píxel del mapa, una columna, `%.3f`, sin encabezado (`:794-801`);
- `Slow_Confocal_Spectrum<YYYYmmdd-HHMMSS>.tiff`: el mapa, traspuesto, crudo (`:847-854`);
- `Trace_BS.txt`: dos columnas (tiempo, BS), `%.3e`, sin encabezado (`Trace_ps.py:370-387`);
- `Info.txt`: filas "etiqueta valor", `fmt="%s"` (`Luminescence_ps.py:799-809`).

Diferencias con el legado, por decisión del investigador: el eje λ tiene 1004 puntos (no 1002) y sale de la
EEPROM; los espectros son la suma de las filas de la fibra leída en Single-Track. `Info.txt` lo deja escrito.
Ningún valor guardado lleva el fondo restado: el fondo va aparte, como en el resto de 3.0 (B3).
"""
from __future__ import annotations

import os
import time
from typing import Iterable, Optional, Sequence, Tuple

import numpy as np


def _tiff(path: str, arr) -> str:
    from PIL import Image
    Image.fromarray(np.ascontiguousarray(np.transpose(np.asarray(arr, dtype=np.float32)))).save(path)
    return path


def write_npscan_tiffs(folder: str, index: int, image, gone=None, back=None) -> list:
    """El trío de TIFF del escaneo del fotodiodo, crudos. Devuelve las rutas escritas."""
    os.makedirs(folder, exist_ok=True)
    out = []
    for prefix, arr in (("", image), ("gone_", gone), ("back_", back)):
        if arr is None:
            continue
        out.append(_tiff(os.path.join(folder, f"{prefix}NPscan_{int(index):03d}.tiff"), arr))
    return out


def write_wavelength(folder: str, wavelength_nm, stamp: Optional[str] = None) -> str:
    os.makedirs(folder, exist_ok=True)
    stamp = stamp or time.strftime("%Y%m%d_%H%M%S")
    path = os.path.join(folder, f"wavelength_{stamp}.txt")
    np.savetxt(path, np.asarray(wavelength_nm, dtype=np.float64), fmt="%.4f")
    return path


def write_pixel_spectrum(folder: str, i: int, j: int, spectrum) -> str:
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"Spectrum_i{int(i):04d}_j{int(j):04d}.txt")
    np.savetxt(path, np.asarray(spectrum, dtype=np.float64), fmt="%.3f")
    return path


def write_map_tiff(folder: str, image, stamp: Optional[str] = None) -> str:
    os.makedirs(folder, exist_ok=True)
    stamp = stamp or time.strftime("%Y%m%d-%H%M%S")
    return _tiff(os.path.join(folder, f"Slow_Confocal_Spectrum{stamp}.tiff"), image)


def write_trace_bs(folder: str, t_s: Sequence[float], bs_v: Sequence[float]) -> str:
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "Trace_BS.txt")
    n = min(len(t_s), len(bs_v))
    data = np.column_stack([np.asarray(t_s, dtype=float)[:n], np.asarray(bs_v, dtype=float)[:n]]) if n \
        else np.empty((0, 2))
    np.savetxt(path, data, fmt="%.3e")
    return path


def write_info(folder: str, rows: Iterable[Tuple[str, object]]) -> str:
    """`Info.txt` del legado: una fila por dato, "etiqueta valor". Los espacios de la etiqueta pasan a '_' para
    que cada fila siga siendo de dos campos."""
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "Info.txt")
    lines = [f"{str(k).strip().replace(' ', '_')} {v}" for k, v in rows]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path


def node_folder_name(kind: str, col: int, np_index: int) -> str:
    """`<kind>_Col_%03d_NP_%03d`, como el legado (p. ej. `Slow_Confocal_Spectrum_Col_001_NP_002`)."""
    return f"{kind}_Col_{int(col):03d}_NP_{int(np_index):03d}"
