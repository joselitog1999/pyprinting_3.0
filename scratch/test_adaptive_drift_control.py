# -*- coding: utf-8 -*-
"""
Prueba de Validación Automatizada para el Control Adaptativo de Frecuencia de Foco y Deriva
PyPrinting 3.0
"""
import os
import sys
import tempfile
import time
import numpy as np

# Ejecutar sin interfaz gráfica (Headless Qt)
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.abspath("."))

try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QObject
except ImportError:
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import QObject

app = QApplication.instance() or QApplication(sys.argv)

from modules.measurements import Frontend, Backend, DriftTrackingDialog, TimeVoltTrackingDialog


def test_adaptive_drift_control():
    print("=" * 70)
    print("🚀 INICIANDO TEST: Control Adaptativo de Frecuencia de Foco y Deriva")
    print("=" * 70)

    # 1. Instanciación y Verificación de la GUI
    frontend = Frontend(mode="printing")
    backend = Backend(mode="printing")
    frontend.make_connection(backend)

    assert hasattr(frontend, "adaptive_af_check"), "Falta adaptive_af_check en Frontend"
    assert hasattr(frontend, "drift_tol_edit"), "Falta drift_tol_edit en Frontend"
    assert hasattr(frontend, "v_drift_label"), "Falta v_drift_label en Frontend"
    assert frontend.adaptive_af_check.isChecked() == True, "Adaptive AF debe estar tildado por defecto"
    assert frontend.drift_tol_edit.text() == "25.0", "Tolerancia por defecto debe ser 25.0 nm"
    print("  ✅ 1. Widgets de UI (Adaptive AF, Drift Tol, v_drift_label) verificados correctamente.")

    # 2. Configuración de Parámetros Adaptativos en Backend
    with tempfile.TemporaryDirectory() as tmpdir:
        backend.old_folder = tmpdir
        backend.new_folder = tmpdir
        backend.track_drift_xy = True
        backend.track_drift_z = True
        backend.track_time_volt = True
        backend.adaptive_af = True
        backend.drift_tolerance_nm = 25.0
        backend.autofoc = 5

        # Simular historial de deriva XY y Z con velocidad conocida
        # t0 = 0s (0,0), t1 = 50s (dx=50nm, dy=0nm -> v_xy = 1.0 nm/s), t2 = 100s (dx=150nm, dy=0nm -> v_xy = 2.0 nm/s)
        backend.drift_history_xy = [
            {"node": 0, "time": 0.0, "dx_nm": 0.0, "dy_nm": 0.0, "mag_nm": 0.0, "v_xy": 0.0, "stage_x": 0.0, "stage_y": 0.0},
            {"node": 1, "time": 50.0, "dx_nm": 50.0, "dy_nm": 0.0, "mag_nm": 50.0, "stage_x": 0.05, "stage_y": 0.0},
            {"node": 2, "time": 100.0, "dx_nm": 150.0, "dy_nm": 0.0, "mag_nm": 150.0, "stage_x": 0.15, "stage_y": 0.0}
        ]

        # Simular deriva Z: t0=0s (dz=0), t1=50s (dz=25nm -> v_z = 0.5 nm/s), t2=100s (dz=75nm -> v_z = 1.0 nm/s)
        backend.drift_history_z = [
            {"node": 0, "time": 0.0, "dz_nm": 0.0, "v_z": 0.0, "stage_z": 10.0},
            {"node": 1, "time": 50.0, "dz_nm": 25.0, "stage_z": 10.025},
            {"node": 2, "time": 100.0, "dz_nm": 75.0, "stage_z": 10.075}
        ]

        # 3. Calcular cinéticas
        backend._update_drift_velocity()

        assert len(backend.v_drift_xy_history) > 0, "Debe registrar historial de v_xy"
        assert len(backend.v_drift_z_history) > 0, "Debe registrar historial de v_z"
        assert np.isclose(backend.v_xy_current, 2.0, atol=0.01), f"v_xy esperado 2.0 nm/s, obtenido {backend.v_xy_current}"
        assert np.isclose(backend.v_z_current, 1.0, atol=0.01), f"v_z esperado 1.0 nm/s, obtenido {backend.v_z_current}"
        assert np.isclose(backend.v_eff_current, 2.0, atol=0.01), f"v_eff esperado 2.0 nm/s, obtenido {backend.v_eff_current}"

        # tau_safe = 25.0 / 2.0 = 12.5 s -> N_eff = floor(12.5 / 4.0) = 3
        assert backend.current_n_effective == 3, f"N_eff esperado 3, obtenido {backend.current_n_effective}"
        print(f"  ✅ 2. Motor cinético: v_xy={backend.v_xy_current:.2f} nm/s, v_z={backend.v_z_current:.2f} nm/s -> τ_safe={backend.tau_safe_current:.1f}s, N_eff={backend.current_n_effective}")

        # 4. Guardar archivos de tracking de deriva y verificar columnas de velocidad
        backend._save_drift_tracking_files(tmpdir)
        xy_file = os.path.join(tmpdir, "drift_tracking_xy.txt")
        z_file = os.path.join(tmpdir, "drift_tracking_z.txt")

        assert os.path.exists(xy_file), "drift_tracking_xy.txt debe existir"
        assert os.path.exists(z_file), "drift_tracking_z.txt debe existir"

        with open(xy_file, "r", encoding="utf-8") as f:
            xy_content = f.read()
            assert "V_xy_nm_s" in xy_content, "La cabecera debe incluir V_xy_nm_s"
            print("  ✅ 3. Archivo drift_tracking_xy.txt contiene columna V_xy_nm_s.")

        with open(z_file, "r", encoding="utf-8") as f:
            z_content = f.read()
            assert "V_z_nm_s" in z_content, "La cabecera debe incluir V_z_nm_s"
            print("  ✅ 4. Archivo drift_tracking_z.txt contiene columna V_z_nm_s.")

        # 5. Generar trazas simuladas y reporte de parámetros con Sección 4
        for i in range(4):
            trace_path = os.path.join(tmpdir, f"NP_{i:03d}.txt")
            t = np.linspace(0, 3.0, 100)
            v = np.ones_like(t) * 0.5
            if i < 3: # 3 éxitos
                v[40:] = 2.5
            else:    # 1 timeout
                v[:] = 0.5
            np.savetxt(trace_path, np.vstack((t, v)))

        backend._generate_time_volt_report(tmpdir)
        report_file = os.path.join(tmpdir, f"reporte_parametros_{backend.grid_name}.txt")
        assert os.path.exists(report_file), "reporte_parametros_*.txt debe existir"

        with open(report_file, "r", encoding="utf-8") as f:
            rep_content = f.read()
            assert "4. CINÉTICA DE DERIVA TERMOMECÁNICA Y CONTROL ADAPTATIVO" in rep_content, "Debe contener la Sección 4"
            assert "Velocidad Deriva Lateral <v_xy>" in rep_content, "Debe reportar velocidad XY"
            assert "Velocidad Deriva Axial   <v_z>" in rep_content, "Debe reportar velocidad Z"
            assert "Tiempo Seguro Estimado (tau_safe)" in rep_content, "Debe reportar tau_safe"
            assert "Intervalo de Autofoco Recomendado (N_sugerido)" in rep_content, "Debe reportar N_sugerido"
            print("  ✅ 5. Reporte de parámetros incluye Sección 4 con cinética completa y recomendaciones.")

        # 6. Guardar grid_info.txt y verificar campos de velocidad y adaptativo
        info_data = [
            ["Laser:", "Laser Verde"],
            ["Drift Velocity (v):", frontend.v_drift_label.text()],
            ["Adaptive AF:", "ON" if frontend.adaptive_af_check.isChecked() else "OFF"],
            ["Drift Tolerance (nm):", frontend.drift_tol_edit.text()]
        ]
        backend.grid_info(info_data)
        grid_info_file = os.path.join(tmpdir, "grid_info.txt")
        assert os.path.exists(grid_info_file), "grid_info.txt debe existir"
        with open(grid_info_file, "r", encoding="utf-8") as f:
            gi_content = f.read()
            assert "Drift Velocity (v):" in gi_content
            assert "Adaptive AF:" in gi_content
            assert "Drift Tolerance (nm):" in gi_content
            print("  ✅ 6. Archivo grid_info.txt contiene campos de velocidad y configuración adaptativa.")

        # 7. Probar modo pasivo (Adaptive AF = False)
        backend.adaptive_af = False
        backend.autofoc = 7
        backend._update_drift_velocity()
        assert backend.current_n_effective == 7, "En modo pasivo, N_eff debe mantenerse en el valor fijo configurado (7)"
        print("  ✅ 7. Modo pasivo verificado: calcula y reporta cinéticas pero mantiene N fijo para control manual.")

        # 8. Probar reseteo Frontend y Backend
        backend.reset_all()
        assert len(backend.v_drift_xy_history) == 0, "v_drift_xy_history debe resetearse"
        assert len(backend.v_drift_z_history) == 0, "v_drift_z_history debe resetearse"
        assert frontend.NPevents.text() == "—"
        assert frontend.NPsuccess.text() == "—"
        print("  ✅ 8. Reset Frontend y Backend verificado.")

    print("=" * 70)
    print("🎉 TODAS LAS PRUEBAS DE CONTROL ADAPTATIVO PASARON EXITOSAMENTE (8/8)")
    print("=" * 70)

if __name__ == "__main__":
    test_adaptive_drift_control()
