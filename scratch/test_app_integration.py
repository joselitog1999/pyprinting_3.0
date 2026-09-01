# -*- coding: utf-8 -*-
import sys
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

print("=== 1. Instanciando Frontend y Backend de app.py ===")
fe = Frontend()
be = Backend()
fe.make_connection(be)

print("=== 2. Emitiendo señales de barra de estado desde printingWorker ===")
be.printingWorker.indexSignal.emit(3)
print("  Status message:", fe.statusBar().currentMessage())
assert "3" in fe.statusBar().currentMessage()

be.printingWorker.grid_autofocusSignal.emit("printing")
print("  Status message:", fe.statusBar().currentMessage())
assert "autofoco" in fe.statusBar().currentMessage()

be.printingWorker.grid_traceSignal.emit("532 nm (green)", "printing")
print("  Status message:", fe.statusBar().currentMessage())
assert "532 nm" in fe.statusBar().currentMessage()

be.printingWorker.grid_scanSignal.emit("532 nm (green)", "printing", "pree_scan")
print("  Status message:", fe.statusBar().currentMessage())
assert "confocal" in fe.statusBar().currentMessage()

be.printingWorker.patternFinishedSignal.emit("C:/test_folder")
print("  Status message:", fe.statusBar().currentMessage())
assert "Patrón completado" in fe.statusBar().currentMessage()

print("\n" + "="*70)
print("✅ TODAS LAS SEÑALES Y BARRA DE ESTADO DE APP.PY FUNCIONAN AL 100%!")
print("="*70)
