# -*- coding: utf-8 -*-
"""
pyspectrum.py — Punto de Entrada de PySpectrum 3.0
PyPrinting 3.0 — UNSAM Nanofotónica
"""
import sys
from PyQt6.QtWidgets import QApplication
import pyqtgraph as pg

pg.setConfigOption('background', '#11111B')
pg.setConfigOption('foreground', '#CDD6F4')

from pyspectrum.window import PySpectrumWindow

if __name__ == "__main__":
    app = QApplication(sys.argv)
    # DEC-036: sin esto, una excepción en un slot aborta el proceso sin cerrar los obturadores.
    from core.safety_excepthook import install_safety_excepthook
    install_safety_excepthook()
    win = PySpectrumWindow()
    win.show()
    sys.exit(app.exec())
