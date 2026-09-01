# -*- coding: utf-8 -*-
import sys
import os
import time
import numpy as np
from pathlib import Path

# Fix Windows stdout encoding
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from PyQt6.QtWidgets import QApplication
app = QApplication(sys.argv)

from modules.measurements import Frontend as MeasFrontend, Backend as MeasBackend
from modules.focus import Frontend as FocusFrontend, Backend as FocusBackend
from modules.confocal import Frontend as ConfocalFrontend, Backend as ConfocalBackend

print("=" * 70)
print("TEST DEL PROTOCOLO DE DOBLE AUTOFOCO Z CON DRIFT CORRECTION")
print("=" * 70)

meas_fe = MeasFrontend(mode="printing")
meas_be = MeasBackend(mode="printing")
meas_fe.make_connection(meas_be)
meas_be.make_connection(meas_fe)

focus_be = FocusBackend()
confocal_be = ConfocalBackend()

# Conectar el ciclo completo como en app.py
meas_be.grid_move_finishSignal.connect(meas_be.grid_autofoco)
meas_be.grid_autofocusSignal.connect(focus_be.focus_autocorr_lin_x2)
focus_be.autofinishSignal.connect(lambda mode: meas_be.grid_finish_autofoco())
meas_be.grid_scanSignal.connect(confocal_be.start_scan_routines)
confocal_be.scanfinishedSignal.connect(meas_be.on_scan_finished)

# 1. Verificar widgets de UI Drift XY y Drift Z
print("\n[PASO 1] Verificando casillas de interfaz:")
assert hasattr(meas_fe, "drift_xy_edit")
assert hasattr(meas_fe, "drift_z_edit")
print(f"  -> drift_xy_edit: '{meas_fe.drift_xy_edit.text()}'")
print(f"  -> drift_z_edit:  '{meas_fe.drift_z_edit.text()}'")

# 2. Configurar grilla con Drift y Autofocus
print("\n[PASO 2] Configurando Grilla 2x2 con Drift Correction (P0 ancla + 4 partículas):")
grid_params = [2, 2, 5.0, 5.0, 2.0, 2.0, True]
meas_be.grid_create(grid_params)
meas_be.grid_parameters(
    0, 0,
    [1.2, 0.0, 5.0, 2, 0.0, 0.0, 0.0, 0.0, 10, 10, 2.5, 5, 0.0, 2.0, 10.0, 50.0, 2.0, 2.0, True],
    False, False
)
meas_be.xref = 50.0
meas_be.yref = 50.0
meas_be.zref = 10.0

# 3. Registrar eventos
trace_started = []
meas_be.grid_traceSignal.connect(lambda l, m: trace_started.append(True))

# 4. Iniciar impresión
print("\n[PASO 3] Iniciando corrida (_grid_start)...")
meas_be._grid_start()

# Esperar a que el ciclo de timers (confocal + autofoco 2) complete
t0 = time.time()
while not trace_started and (time.time() - t0 < 5.0):
    app.processEvents()
    time.sleep(0.02)

print(f"  -> Estado autofocus_stage al finalizar el ciclo: '{meas_be.autofocus_stage}'")
assert meas_be.autofocus_stage == "idle"
print(f"  -> Texto en GUI Drift XY: '{meas_fe.drift_xy_edit.text()}'")
assert "nm" in meas_fe.drift_xy_edit.text()
print(f"  -> Texto en GUI Drift Z: '{meas_fe.drift_z_edit.text()}'")
assert "nm" in meas_fe.drift_z_edit.text()
print(f"  -> ¿Se inició la traza de impresión final?: {len(trace_started) > 0}")
assert len(trace_started) > 0

print("\n" + "=" * 70)
print("✅ VALIDACIÓN DEL PROTOCOLO COMPLETO DE DOBLE AUTOFOCO SUPERADA AL 100%!")
print("=" * 70)
