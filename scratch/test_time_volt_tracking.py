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

    # Verificar que el diálogo de histogramas genera time_volt_distributions.png
    from modules.measurements import TimeVoltTrackingDialog
    # Parse rows from content or pass dict
    test_rows = [
        {"node": 1, "t_raw": 2.0, "t_step": 1.5, "latency": 0.5, "v_low": 1.0, "v_high": 3.2, "delta_v": 2.2, "ratio": 3.2, "status": "SUCCESS"},
        {"node": 2, "t_raw": 1.2, "t_step": 0.8, "latency": 0.4, "v_low": 1.05, "v_high": 3.4, "delta_v": 2.35, "ratio": 3.24, "status": "SUCCESS"},
        {"node": 3, "t_raw": 2.6, "t_step": 2.2, "latency": 0.4, "v_low": 0.98, "v_high": 3.0, "delta_v": 2.02, "ratio": 3.06, "status": "SUCCESS"},
        {"node": 4, "t_raw": 10.0, "t_step": 10.0, "latency": 0.0, "v_low": 1.0, "v_high": 1.0, "delta_v": 0.0, "ratio": 1.0, "status": "TIMEOUT / NO STEP"},
    ]
    dlg = TimeVoltTrackingDialog({"rows": test_rows, "folder": test_dir}, parent=None)
    expected_png = os.path.join(test_dir, "time_volt_distributions.png")
    assert os.path.exists(expected_png), f"No se encontró la imagen esperada en {expected_png}"
    print(f"✅ Imagen de histogramas generada exitosamente: {os.path.basename(expected_png)}")

    print("✅ Generación y contenido de reporte_parametros_*.txt e imagen .png verificado al 100%.")

    # Limpieza
    shutil.rmtree(test_dir, ignore_errors=True)

def test_frontend_gui_elements():
    fe = Frontend(mode="printing")
    assert hasattr(fe, "custom_name_edit"), "Falta custom_name_edit en Frontend"
    assert hasattr(fe, "track_time_volt_check"), "Falta track_time_volt_check en Frontend"
    assert fe.track_time_volt_check.isChecked() == True, "Track Time-Volt debería estar marcado por defecto"
    assert hasattr(fe, "NPevents"), "Falta NPevents en Frontend"
    assert hasattr(fe, "NPsuccess"), "Falta NPsuccess en Frontend"
    assert fe.NPevents.text() == "—", "NPevents debería inicializar en —"
    assert fe.NPsuccess.text() == "—", "NPsuccess debería inicializar en —"

    # Simular grilla de 4 partículas y actualización en tiempo real de nodos
    fe.particulasEdit.setText("4")
    fe.node_status_update(0, "success")
    assert fe.NPevents.text() == "1/4 (25.0%)", f"Esperado 1/4 (25.0%), obtenido {fe.NPevents.text()}"
    assert fe.NPsuccess.text() == "1/4 (25.0%)"

    fe.node_status_update(1, "success")
    fe.node_status_update(2, "success")
    fe.node_status_update(3, "timeout")
    assert fe.NPevents.text() == "3/4 (75.0%)", f"Esperado 3/4 (75.0%), obtenido {fe.NPevents.text()}"
    assert fe.NPsuccess.text() == "3/4 (75.0%)"

    # Simular entrega de datos Time-Volt
    test_data = {
        "rows": [
            {"node": 1, "status": "SUCCESS"},
            {"node": 2, "status": "SUCCESS"},
            {"node": 3, "status": "SUCCESS"},
            {"node": 4, "status": "TIMEOUT"}
        ],
        "folder": ""
    }
    fe._show_time_volt_tracking_dialog(test_data)
    assert fe.NPevents.text() == "3/4 (75.0%)"
    assert fe.NPsuccess.text() == "3/4 (75.0%)"

    fe.custom_name_edit.setText("Muestra_Test")
    fe._emit_parameters()

    # Probar reset
    fe.on_reset_frontend()
    assert fe.custom_name_edit.text() == "", "custom_name_edit no se reseteó a vacío"
    assert fe.NPevents.text() == "—", "NPevents no se reseteó a —"
    assert fe.NPsuccess.text() == "—", "NPsuccess no se reseteó a —"
    print("✅ Widgets de Frontend y cálculo de NP events / NP success verificados correctamente.")

if __name__ == "__main__":
    test_custom_name_folder()
    test_time_volt_report_generation()
    test_frontend_gui_elements()
    print("\n🎉 TODOS LOS TESTS DE TIME-VOLT, CUSTOM NAME Y NP EVENTS/SUCCESS PASARON EXITOSAMENTE.")
