# -*- coding: utf-8 -*-
"""
test_time_volt_tracking.py — Verificación de Track Time-Volt, Reporte de Parámetros y Custom Name
"""
import os
import sys
import shutil
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PyQt6.QtWidgets import QApplication
from modules.measurements import Frontend, Backend

app = QApplication.instance() or QApplication(sys.argv)

def test_custom_name_folder():
    be = Backend(mode="printing")
    test_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "tmp_tv_test"))
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)
    os.makedirs(test_dir, exist_ok=True)
    be.file_path = test_dir
    be.grid_name = "5x5_5.0umx5.0um"

    # Caso 1: Sin custom name (vacio)
    be.grid_create_folder("")
    assert "5x5_5.0umx5.0um" in be.new_folder, f"Esperado nombre de grilla por defecto en {be.new_folder}"
    print(f"✅ Carpeta automática correcta: {os.path.basename(be.new_folder)}")

    # Caso 2: Con custom name
    be.grid_create_folder("Muestra_AuNP_60nm_BatchA")
    assert "Muestra_AuNP_60nm_BatchA" in be.new_folder, f"Esperado nombre custom en {be.new_folder}"
    print(f"✅ Carpeta personalizada correcta: {os.path.basename(be.new_folder)}")

    # Limpieza
    shutil.rmtree(test_dir, ignore_errors=True)

def test_time_volt_report_generation():
    be = Backend(mode="printing")
    test_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "tmp_tv_report_test"))
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)
    os.makedirs(test_dir, exist_ok=True)

    be.file_path = test_dir
    be.grid_name = "3x3_5.0umx5.0um"
    be.custom_name = "Batch_Optimizacion_Gold"
    be.stopping_mode = 1
    be.umbral = 1.30
    be.umbral_abs_v = 2.50
    be.timemax = 10.0
    be.laser = "532 nm (green)"
    be.new_folder = test_dir

    # Crear 4 trazas simuladas: 3 con salto claro (exitosas) y 1 con timeout
    # Traza 1: Salto en t=1.5s, V_low=1.0V, V_high=3.2V
    t1 = np.linspace(0.01, 2.0, 200)
    v1 = np.where(t1 < 1.5, 1.0 + np.random.normal(0, 0.02, 200), 3.2 + np.random.normal(0, 0.02, 200))
    bs1 = np.full(200, 0.5)
    np.savetxt(os.path.join(test_dir, "NP_001.txt"), np.transpose([t1, v1, bs1]), fmt="%.3e")

    # Traza 2: Salto en t=0.8s, V_low=1.05V, V_high=3.4V
    t2 = np.linspace(0.01, 1.2, 120)
    v2 = np.where(t2 < 0.8, 1.05 + np.random.normal(0, 0.02, 120), 3.4 + np.random.normal(0, 0.02, 120))
    bs2 = np.full(120, 0.5)
    np.savetxt(os.path.join(test_dir, "NP_002.txt"), np.transpose([t2, v2, bs2]), fmt="%.3e")

    # Traza 3: Salto en t=2.2s, V_low=0.98V, V_high=3.0V
    t3 = np.linspace(0.01, 2.6, 260)
    v3 = np.where(t3 < 2.2, 0.98 + np.random.normal(0, 0.02, 260), 3.0 + np.random.normal(0, 0.02, 260))
    bs3 = np.full(260, 0.5)
    np.savetxt(os.path.join(test_dir, "NP_003.txt"), np.transpose([t3, v3, bs3]), fmt="%.3e")

    # Traza 4: Timeout a 10s (sin salto, fluctuaciones de 1.0V)
    t4 = np.linspace(0.01, 10.0, 1000)
    v4 = 1.0 + np.random.normal(0, 0.02, 1000)
    bs4 = np.full(1000, 0.5)
    np.savetxt(os.path.join(test_dir, "NP_004.txt"), np.transpose([t4, v4, bs4]), fmt="%.3e")

    # Generar reporte
    be._generate_time_volt_report(test_dir)

    expected_report = os.path.join(test_dir, "reporte_parametros_Batch_Optimizacion_Gold.txt")
    assert os.path.exists(expected_report), f"No se encontró el reporte esperado en {expected_report}"

    with open(expected_report, "r", encoding="utf-8") as f:
        content = f.read()

    print("📄 Contenido del reporte generado:")
    print("-" * 60)
    print(content)
    print("-" * 60)

    assert "REPORTE DE PARÁMETROS Y ANÁLISIS TIME-VOLT" in content
    assert "001" in content and "004" in content
    assert "SUCCESS" in content
    assert "TIMEOUT" in content
    assert "Tiempo Raw Promedio" in content
    assert "Voltaje Low Promedio" in content
    assert "Voltaje High Promedio" in content

    print("✅ Generación y contenido de reporte_parametros_*.txt verificado al 100%.")

    # Limpieza
    shutil.rmtree(test_dir, ignore_errors=True)

def test_frontend_gui_elements():
    fe = Frontend(mode="printing")
    assert hasattr(fe, "custom_name_edit"), "Falta custom_name_edit en Frontend"
    assert hasattr(fe, "track_time_volt_check"), "Falta track_time_volt_check en Frontend"
    assert fe.track_time_volt_check.isChecked() == True, "Track Time-Volt debería estar marcado por defecto"

    fe.custom_name_edit.setText("Muestra_Test")
    fe._emit_parameters()

    # Probar reset
    fe.on_reset_frontend()
    assert fe.custom_name_edit.text() == "", "custom_name_edit no se reseteó a vacío"
    print("✅ Widgets de Frontend verificados correctamente.")

if __name__ == "__main__":
    test_custom_name_folder()
    test_time_volt_report_generation()
    test_frontend_gui_elements()
    print("\n🎉 TODOS LOS TESTS DE TIME-VOLT Y CUSTOM NAME PASARON EXITOSAMENTE.")
