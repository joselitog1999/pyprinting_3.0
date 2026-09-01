# -*- coding: utf-8 -*-
import sys
import os
from pathlib import Path

# Fix Windows stdout encoding
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from PyQt6.QtWidgets import QApplication
app = QApplication(sys.argv)

from app import Frontend, Backend

fe = Frontend()
be = Backend()
fe.make_connection(be)

print("=== Probando conexión de statusBar en Frontend ===")
be.printingWorker.indexSignal.emit(5)
msg1 = fe.statusBar().currentMessage()
print("  Mensaje 1:", msg1)
assert "5" in msg1

be.printingWorker.grid_traceSignal.emit("532 nm (green)", "printing")
msg2 = fe.statusBar().currentMessage()
print("  Mensaje 2:", msg2)
assert "532 nm" in msg2

be.printingWorker.patternFinishedSignal.emit("C:/lote_finalizado")
msg3 = fe.statusBar().currentMessage()
print("  Mensaje 3:", msg3)
assert "Patrón completado" in msg3

print("VALIDACIÓN EXITOSA: La barra de estado de app.py se actualiza sin ningún error!")
os._exit(0)
