# -*- coding: utf-8 -*-
"""
camera.py — Launcher / Punto de entrada para la Suite de Cámara Réflex Canon & Microfotónica PyPrinting 3.0
UNSAM — Nanofotónica
"""
import sys
import os

# Registrar subdirectorios en sys.path
_this_dir = os.path.dirname(os.path.abspath(__file__))
for _p in [_this_dir, os.path.join(_this_dir, "core"), os.path.join(_this_dir, "modules"), os.path.join(_this_dir, "analysis")]:
    if os.path.exists(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

from modules.camera import main

if __name__ == "__main__":
    main()
