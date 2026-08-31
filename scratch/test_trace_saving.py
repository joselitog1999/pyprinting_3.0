# -*- coding: utf-8 -*-
"""
test_trace_saving.py — Verificación de guardado de trazas fototérmicas por evento de impresión
"""
import os
import sys
import shutil
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from modules.measurements import Backend

def test_trace_save():
    be = Backend(mode="printing")
    test_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "tmp_trace_test"))
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)
    os.makedirs(test_dir, exist_ok=True)
    be.new_folder = test_dir

    # Simular datos de traza en nodo 1
    be.i_global = 1
    be.ptr = 100
    be.timer_real = 2.50
    be.data1 = list(np.random.normal(1.0, 0.1, 100))
    be.data_BS = list(np.random.normal(0.5, 0.05, 100))

    # Guardar
    be._save_trace()

    expected_file = os.path.join(test_dir, "NP_001.txt")
    assert os.path.exists(expected_file), f"No se encontró {expected_file}"
    data = np.loadtxt(expected_file)
    assert data.shape == (100, 3), f"Dimensiones incorrectas: {data.shape}"
    print(f"✅ Traza guardada correctamente en: {expected_file}")
    print(f"   Formato: {data.shape[0]} muestras x {data.shape[1]} columnas (Tiempo, Señal PD1, Señal BS)")

    # Limpieza
    shutil.rmtree(test_dir, ignore_errors=True)

if __name__ == "__main__":
    test_trace_save()
