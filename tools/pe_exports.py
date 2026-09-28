# -*- coding: utf-8 -*-
"""Lectura estática de una DLL de Windows (formato PE): arquitectura y funciones exportadas.

No carga la DLL: cargarla ejecutaría su código de inicialización. Sirve para comprobar, sin
hardware ni SDK instalado, que cada función que un driver llama por ctypes exista en la DLL que se
va a usar (DEC-040: el driver llamaba a `ShamrockGetFlipper` y `SetRandomTrack`, que no existen).

Uso: python tools/pe_exports.py <ruta.dll> [<nombre> ...]
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path
from typing import Set, Tuple

_MACHINES = {0x14C: "x86", 0x8664: "x64", 0xAA64: "arm64"}


def read_pe(path) -> Tuple[str, Set[str]]:
    """Devuelve (arquitectura, conjunto de nombres exportados)."""
    b = Path(path).read_bytes()
    pe = struct.unpack_from("<I", b, 0x3C)[0]
    if b[pe:pe + 4] != b"PE\0\0":
        raise ValueError(f"{path}: no es un archivo PE")
    machine, n_sections = struct.unpack_from("<HH", b, pe + 4)
    opt_size = struct.unpack_from("<H", b, pe + 20)[0]
    opt = pe + 24
    magic = struct.unpack_from("<H", b, opt)[0]
    data_dirs = opt + (96 if magic == 0x10B else 112)
    export_rva = struct.unpack_from("<I", b, data_dirs)[0]

    sections = []
    first = opt + opt_size
    for i in range(n_sections):
        vsize, va, raw_size, raw_ptr = struct.unpack_from("<IIII", b, first + 40 * i + 8)
        sections.append((va, max(vsize, raw_size), raw_ptr))

    def offset(rva: int) -> int:
        for va, size, raw in sections:
            if va <= rva < va + size:
                return rva - va + raw
        raise ValueError(f"RVA {rva:#x} fuera de las secciones")

    names: Set[str] = set()
    if export_rva:
        e = offset(export_rva)
        n_names = struct.unpack_from("<I", b, e + 24)[0]
        names_table = offset(struct.unpack_from("<I", b, e + 32)[0])
        for i in range(n_names):
            o = offset(struct.unpack_from("<I", b, names_table + 4 * i)[0])
            names.add(b[o:b.index(b"\0", o)].decode("ascii", "replace"))
    return _MACHINES.get(machine, hex(machine)), names


if __name__ == "__main__":
    arch, exports = read_pe(sys.argv[1])
    print(f"{sys.argv[1]}: {arch}, {len(exports)} funciones exportadas")
    for name in sys.argv[2:]:
        print(f"  {name}: {'exporta' if name in exports else 'NO EXISTE'}")
