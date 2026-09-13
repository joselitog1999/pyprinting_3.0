# -*- coding: utf-8 -*-
"""
lattice_disorder_gui.py — Acceso directo raíz al Analizador de Desorden y Redes 2D
PyPrinting 3.0 — UNSAM Nanofotónica
"""
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
for sub in [BASE_DIR / "core", BASE_DIR / "modules", BASE_DIR / "analysis"]:
    if str(sub) not in sys.path:
        sys.path.insert(0, str(sub))

from analysis.lattice_disorder_gui import main

if __name__ == "__main__":
    main()
