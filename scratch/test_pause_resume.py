# -*- coding: utf-8 -*-
import sys
import os
import time
from pathlib import Path

# Fix Windows stdout encoding
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from PyQt6.QtWidgets import QApplication
app = QApplication(sys.argv)

from modules.measurements import Frontend, Backend

print("=" * 70)
print("TEST DE PAUSA Y REANUDACIÓN EN TIEMPO REAL (PLAY / PAUSE / PLAY)")
print("=" * 70)

fe = Frontend(mode="printing")
be = Backend(mode="printing")
be.make_connection(fe)
fe.make_connection(be)

# 1. Crear grilla 3x3
fe.number_files.setText("3")
fe.number_columns.setText("3")
fe.distance_files.setText("5.0")
fe.distance_columns.setText("5.0")
fe.grid_create_button.click()
fe.imprimir_button.click()
print(f"[PASO 1] Grilla creada con {be.particulas} partículas. Carpeta: {be.new_folder}")

# 2. Iniciar impresión
print("\n[PASO 2] Presionando Play inicial...")
fe.play_button.click()
print(f"  -> Estado: mode_printing='{be.mode_printing}', i_global={be.i_global}")
assert be.mode_printing == "printing"

# 3. Avanzar al nodo 2 y pausar
be.i_global = 2
fe.indice_impresionEdit.setText("2")
print("\n[PASO 3] Presionando Pause en nodo 2...")
fe.pause_button.click()
print(f"  -> Estado post-pause: mode_printing='{be.mode_printing}', is_paused={getattr(be, 'is_paused', False)}, i_global={be.i_global}")
assert getattr(be, "is_paused", False) is True
assert be.i_global == 2

# 4. Reanudar con Play
print("\n[PASO 4] Presionando Play para reanudar...")
fe.play_button.click()
print(f"  -> Estado post-resume: mode_printing='{be.mode_printing}', is_paused={getattr(be, 'is_paused', False)}, i_global={be.i_global}")
assert be.mode_printing == "printing"
assert getattr(be, "is_paused", False) is False
assert be.i_global == 2  # Debe haber conservado el nodo 2, NO reiniciado a 0

# 5. Pausar, cambiar manualmente al nodo 5, y reanudar con Play
print("\n[PASO 5] Pausando y saltando manualmente al nodo 5...")
fe.pause_button.click()
fe.indice_impresionEdit.setText("5")
print(f"  -> Índice cambiado a: {be.i_global}")
fe.play_button.click()
print(f"  -> Reanudado en nodo: {be.i_global}")
assert be.i_global == 5
assert be.mode_printing == "printing"

print("\n" + "=" * 70)
print("✅ VALIDACIÓN DE PAUSE Y REANUDACIÓN EXITOSA AL 100%!")
print("=" * 70)
