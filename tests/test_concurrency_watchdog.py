# -*- coding: utf-8 -*-
"""
test_concurrency_watchdog.py — Verificación de Thread-Safety y Watchdog Fail-Safe
PyPrinting 3.0 — UNSAM Nanofotónica
"""
import os
import sys
import time
import threading
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ["PYPRINTING_SAFE"] = "1"

import config
from config import pi
from core.nidaq import open_shutter, close_shutter, close_all_shutters, up_flipper, down_flipper, heartbeat_shutter, _shutter_signal, SHUTTERS, SHUTTER_POLARITY

def test_multithread_pi_and_nidaq():
    print("Iniciando test de concurrencia multihilo (10 hilos x 100 iteraciones)...")
    errors = []
    
    def worker_job(worker_id: int):
        try:
            for i in range(100):
                target_x = (worker_id * 5.0 + i * 0.1) % 100.0
                target_y = (worker_id * 3.0 + i * 0.2) % 100.0
                pi.MOV([1, 2], [target_x, target_y])
                pos = pi.qPOS()
                assert "1" in pos and "2" in pos
                
                # Operaciones de shutter concurrentes
                sh_name = SHUTTERS[worker_id % len(SHUTTERS)]
                open_shutter(sh_name, timeout_s=5.0)
                time.sleep(0.001)
                close_shutter(sh_name)
        except Exception as e:
            errors.append((worker_id, str(e)))

    threads = [threading.Thread(target=worker_job, args=(wid,)) for wid in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    if errors:
        print(f"FAILED: Ocurrieron {len(errors)} errores de concurrencia: {errors}")
        return False
    print("PASS: 1.000 operaciones concurrentes completadas con CERO colisiones o excepciones.")
    return True

def test_watchdog_auto_closure():
    print("Iniciando test del Watchdog Heartbeat Fail-Safe...")
    laser_name = "532 nm (green)"
    # Abrir con timeout de 0.5 segundos
    open_shutter(laser_name, timeout_s=0.5)
    
    # Comprobar que está abierto
    idx = SHUTTERS.index(laser_name)
    assert _shutter_signal[idx] == SHUTTER_POLARITY[laser_name], "El shutter debería estar abierto inicialmente."
    print("Shutter abierto correctamente. Esperando que expire el watchdog (dormir 0.8s)...")
    
    time.sleep(0.8)
    
    # Comprobar que el watchdog forzó el cierre
    assert _shutter_signal[idx] != SHUTTER_POLARITY[laser_name], "El Watchdog debería haber forzado el cierre del shutter."
    print("PASS: El Watchdog forzó el cierre seguro del obturador tras la expiración del heartbeat.")
    return True

if __name__ == "__main__":
    ok_concurrency = test_multithread_pi_and_nidaq()
    ok_watchdog = test_watchdog_auto_closure()
    
    if ok_concurrency and ok_watchdog:
        print("\n=======================================================")
        print("TODAS LAS PRUEBAS DE CONCURRENCIA Y WATCHDOG SUPERADAS!")
        print("=======================================================")
        sys.exit(0)
    else:
        sys.exit(1)
