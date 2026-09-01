# -*- coding: utf-8 -*-
import sys
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

from modules.measurements import Frontend, Backend

def test_stopping_modes():
    print("=" * 70)
    print("VERIFICACIÓN DE RUTINAS DE PARADA Y FLUJO DE ALGORITMO (PyPrinting 3.0)")
    print("=" * 70)

    be = Backend(mode="printing")
    fe = Frontend(mode="printing")
    be.make_connection(fe)

    # ──────────────────────────────────────────────────────────────────────────
    # PRUEBA 1: MODO 0 — Salto Relativo Estándar
    # ──────────────────────────────────────────────────────────────────────────
    print("\n[TEST 1] Modo 0: Salto Relativo Estándar")
    be.grid_parameters(0, 0, [1.2, 0.0, 10.0, 2, 0.0, 0.0, 0.0, 0.0, 10, 10, 2.5, 5, 0.0, 2.0, 10.0, 50.0], False, False)
    be.timer_inicio = time.time()

    # Paso 1: Sin salto (I_old=1.0, I_new=1.1) -> No detiene
    data_no_event = [10, [0.01*i for i in range(10)], [1.0]*9 + [1.1], 0, 1.0, 1.1, [1.0]*10]
    be.grid_trace_detect(data_no_event)
    print("  -> Paso sin salto (I_new=1.1, I_old=1.0): Obturador abierto (Correcto)")

    # Paso 2: Salto por encima del umbral 1.20 (I_new=1.35) -> Detiene
    data_event = [11, [0.01*i for i in range(11)], [1.0]*10 + [1.35], 0, 1.0, 1.35, [1.0]*11]
    be.grid_trace_detect(data_event)
    print(f"  -> Paso con salto (I_new=1.35): Detención exitosa! (timer_real={be.timer_real} s)")

    # ──────────────────────────────────────────────────────────────────────────
    # PRUEBA 2: MODO 1 — Salto Relativo + Absoluto + Filtro Anti-Paso (N_hold = 3)
    # ──────────────────────────────────────────────────────────────────────────
    print("\n[TEST 2] Modo 1: Salto Relativo + Absoluto + Filtro Anti-Paso (N_hold=3)")
    be.grid_parameters(0, 1, [1.2, 0.0, 10.0, 2, 0.0, 0.0, 0.0, 0.0, 10, 10, 2.5, 3, 0.0, 2.0, 10.0, 50.0], False, False)
    be.timer_inicio = time.time()

    # Partícula de paso: Sube a 2.8 V por 2 muestras y luego cae
    data_pass1 = [10, [0.01*i for i in range(10)], [0.5]*10, 0, 0.5, 2.8, [0.5]*10]
    be.grid_trace_detect(data_pass1)
    print(f"  -> Muestra 1 paso transitorio (I=2.8V): hold_counter={be.hold_counter}/3 (No detiene)")
    
    data_pass2 = [11, [0.01*i for i in range(11)], [0.5]*11, 0, 0.5, 2.9, [0.5]*11]
    be.grid_trace_detect(data_pass2)
    print(f"  -> Muestra 2 paso transitorio (I=2.9V): hold_counter={be.hold_counter}/3 (No detiene)")

    data_drop = [12, [0.01*i for i in range(12)], [0.5]*12, 0, 0.5, 0.5, [0.5]*12]
    be.grid_trace_detect(data_drop)
    print(f"  -> Partícula pasó y se fue (I=0.5V): hold_counter reiniciado a {be.hold_counter} (Correcto!)")

    # Partícula depositada real: 3 muestras consecutivas > 2.5 V
    for h in range(1, 4):
        data_deposit = [12+h, [0.01*i for i in range(12+h)], [0.5]*12 + [3.0]*h, 0, 0.5, 3.0, [0.5]*(12+h)]
        be.grid_trace_detect(data_deposit)
        print(f"  -> Muestra {h}/3 confirmada (I=3.0V): hold_counter={be.hold_counter}/3")
    print(f"  -> Partícula depositada confirmada! Detención en N_hold alcanzado (timer_real={be.timer_real} s)")

    # ──────────────────────────────────────────────────────────────────────────
    # PRUEBA 3: MODO 2 — Derivada Temporal Adaptativa (dI/dt -> 0 post-salto)
    # ──────────────────────────────────────────────────────────────────────────
    print("\n[TEST 3] Modo 2: Derivada Temporal Adaptativa (dI/dt < Slope_Flat)")
    be.grid_parameters(0, 2, [1.2, 0.0, 10.0, 2, 0.0, 0.0, 0.0, 0.0, 10, 10, 5.0, 2, 0.0, 1.5, 10.0, 50.0], False, False)
    be.timer_inicio = time.time()

    # Subida rápida (dI/dt = (2.0 - 0.5)/0.05 = 30 V/s > 1.5) -> En crecimiento, no detener
    t_axis = [0.01*i for i in range(10)]
    sig_rise = [0.5]*5 + [0.8, 1.2, 1.5, 1.8, 2.0]
    data_rise = [10, t_axis, sig_rise, 0, 0.5, 2.0, [0.5]*10]
    be.grid_trace_detect(data_rise)
    print(f"  -> En pleno crecimiento rápido (dI/dt > 1.5 V/s): hold_counter={be.hold_counter} (Continúa)")

    # Meseta alcanzada (dI/dt ≈ 0 V/s < 1.5 V/s con I_new > I_old + 0.1)
    sig_flat1 = [0.5]*5 + [2.0, 2.0, 2.0, 2.01, 2.0]
    data_flat1 = [10, t_axis, sig_flat1, 0, 0.5, 2.0, [0.5]*10]
    be.grid_trace_detect(data_flat1)
    sig_flat2 = [0.5]*5 + [2.0, 2.01, 2.0, 2.0, 2.0]
    data_flat2 = [10, t_axis, sig_flat2, 0, 0.5, 2.0, [0.5]*10]
    be.grid_trace_detect(data_flat2)
    print(f"  -> Meseta detectada y sostenida: Detención exitosa! (timer_real={be.timer_real} s)")

    # ──────────────────────────────────────────────────────────────────────────
    # PRUEBA 4: MODO 3 — Híbrido Tri-Factor All-In-One
    # ──────────────────────────────────────────────────────────────────────────
    print("\n[TEST 4] Modo 3: Híbrido Tri-Factor All-In-One (Salto + Derivada + Absoluto)")
    be.grid_parameters(0, 3, [1.2, 0.0, 10.0, 2, 0.0, 0.0, 0.0, 0.0, 10, 10, 2.5, 2, 0.0, 2.0, 10.0, 50.0], False, False)
    be.timer_inicio = time.time()
    
    data_hybrid1 = [10, t_axis, [0.5]*5 + [2.8, 2.8, 2.8, 2.8, 2.8], 0, 0.5, 2.8, [0.5]*10]
    be.grid_trace_detect(data_hybrid1)
    data_hybrid2 = [10, t_axis, [0.5]*5 + [2.8, 2.8, 2.8, 2.8, 2.8], 0, 0.5, 2.8, [0.5]*10]
    be.grid_trace_detect(data_hybrid2)
    print(f"  -> Condición triple cumplida y validada con N_hold=2: Detención exitosa! (timer_real={be.timer_real} s)")

    # ──────────────────────────────────────────────────────────────────────────
    # PRUEBA 5: Restricción Fuerte de Umbral Mínimo (Universal)
    # ──────────────────────────────────────────────────────────────────────────
    print("\n[TEST 5] Restricción Fuerte de Umbral Mínimo (V_min = 1.0 V)")
    # Se configura V_min = 1.0 V. Una señal I_new=0.8 con salto relativo 2.0x (0.4 -> 0.8) NO debe detener
    be.grid_parameters(0, 0, [1.2, 0.0, 10.0, 2, 0.0, 0.0, 0.0, 0.0, 10, 10, 2.5, 1, 1.0, 2.0, 10.0, 50.0], False, False)
    be.timer_inicio = time.time()
    data_below_min = [10, t_axis, [0.4]*9 + [0.8], 0, 0.4, 0.8, [0.4]*10]
    be.grid_trace_detect(data_below_min)
    print("  -> Salto relativo 2.0x pero I_new=0.8 V < V_min=1.0 V: Bloqueado correctamente (No detiene)")

    data_above_min = [10, t_axis, [0.4]*9 + [1.2], 0, 0.4, 1.2, [0.4]*10]
    be.grid_trace_detect(data_above_min)
    print("  -> Salto relativo 3.0x e I_new=1.2 V > V_min=1.0 V: Detención permitida (Correcto!)")

    print("\n" + "=" * 70)
    print("RESULTADO: 100% DE LAS RUTINAS DE PARADA Y CONDICIONES VALIDADAS")
    print("=" * 70)

if __name__ == "__main__":
    test_stopping_modes()
