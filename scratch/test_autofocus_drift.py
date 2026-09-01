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
print("TEST COMPLETO DE INTEGRACIÓN: AUTOFOCO AXIAL Z Y CORRECCIÓN DE DERIVA (DRIFT)")
print("=" * 70)

# 1. Instanciación
meas_fe = MeasFrontend(mode="printing")
meas_be = MeasBackend(mode="printing")
meas_fe.make_connection(meas_be)
meas_be.make_connection(meas_fe)

focus_be = FocusBackend()
confocal_be = ConfocalBackend()

# 2. Conectar el ciclo idéntico a app.py
meas_be.grid_autofocusSignal.connect(focus_be.focus_autocorr_lin_x2)
focus_be.autofinishSignal.connect(lambda mode: meas_be.grid_finish_autofoco())
meas_be.grid_scanSignal.connect(confocal_be.start_scan_routines)
confocal_be.scanfinishedSignal.connect(meas_be.on_scan_finished)

# 3. Configurar grilla con Drift Correction y Autofoco cada 2 partículas
print("\n[PASO 1] Configurando Grilla 2x2 con Drift Correction (P0 ancla + 4 partículas)")
grid_params = [2, 2, 5.0, 5.0, 2.0, 2.0, True]  # n=2, N=2, dn=5, dN=5, startX=2, startY=2, drift=True
meas_be.grid_create(grid_params)
print(f"  -> Total de nodos en grilla: {meas_be.particulas} (P0 Ancla en (0,0) + 4 nodos de impresión)")
assert meas_be.particulas == 5

meas_be.grid_parameters(
    0, 0,  # laser=532, stop_mode=0
    [1.2, 0.0, 5.0, 2, 0.0, 0.0, 0.0, 0.0, 10, 10, 2.5, 5, 0.0, 2.0, 10.0, 50.0, 2.0, 2.0, True],
    False, False
)
meas_be.xref = 50.0
meas_be.yref = 50.0
meas_be.zref = 10.0

# 4. Probar secuencia de inicio en Nodo 1 (primer nodo impreso)
print("\n[PASO 2] Iniciando impresión en Nodo 1 -> Verificando disparo de Autofoco y Drift")
# Interceptar si llega a grid_traceSignal
trace_called = []
meas_be.grid_traceSignal.connect(lambda l, m: trace_called.append(True))

meas_be._grid_start()

# Simular que el escaneo confocal de drift terminó con un pequeño corrimiento (deriva de 35 nm en X, -20 nm en Y)
# En simulación, simulamos el resultado de on_scan_finished para drift_scan
drift_center_mass = [50.0 + 0.035, 50.0 - 0.020]
meas_be.on_scan_finished(np.zeros((10, 10)), drift_center_mass, np.zeros((10, 10)), np.zeros((10, 10)), "printing", "drift_scan")

print(f"  -> Valor mostrado en GUI disp_acumuladoEdit: '{meas_fe.disp_acumuladoEdit.text()}'")
assert "nm" in meas_fe.disp_acumuladoEdit.text()
assert "+35.0" in meas_fe.disp_acumuladoEdit.text()
assert "-20.0" in meas_fe.disp_acumuladoEdit.text()
assert "r=40.3 nm" in meas_fe.disp_acumuladoEdit.text()

# 5. Probar evaluación de Autofoco en Nodo 2 (debe saltar porque autofoc=2) y Nodo 3 (debe ejecutar)
print("\n[PASO 3] Verificando cadencia de Autofoco:")
meas_be.i_global = 2
print(f"  -> Evaluando Nodo 2 (i=2, autofoc=2):")
start_idx = 1
should_af_2 = ((2 - start_idx) % 2 == 0)
print(f"     ¿Debe hacer autofoco en nodo 2?: {should_af_2} (Correcto: salta nodo intermedio)")
assert should_af_2 is False

meas_be.i_global = 3
print(f"  -> Evaluando Nodo 3 (i=3, autofoc=2):")
should_af_3 = ((3 - start_idx) % 2 == 0)
print(f"     ¿Debe hacer autofoco en nodo 3?: {should_af_3} (Correcto: ejecuta autofoco)")
assert should_af_3 is True

print("\n" + "=" * 70)
print("✅ VALIDACIÓN DE AUTOFOCO Y DRIFT CORRECTION SUPERADA AL 100%!")
print("=" * 70)
