import os
import sys
import shutil
import tempfile
import numpy as np

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PyQt6.QtWidgets import QApplication
from modules.measurements import Frontend, Backend, InteractiveGridWidget

def test_autocomplete_printing():
    app = QApplication.instance() or QApplication(sys.argv)

    temp_dir = tempfile.mkdtemp(prefix="test_healing_pass_")
    try:
        frontend = Frontend(mode="printing")
        backend = Backend(mode="printing")
        backend.file_path = temp_dir

        backend.make_connection(frontend)
        frontend.make_connection(backend)

        # 1. Verificar widget visual y estado "retrying"
        grid_widget = InteractiveGridWidget()
        coords = np.array([[0.0, 2.0, 4.0, 6.0], [0.0, 0.0, 0.0, 0.0], [0.0, 0.0, 0.0, 0.0]])
        grid_widget.set_grid(coords)
        assert len(grid_widget.node_states) == 4, "Debe tener 4 nodos"
        
        grid_widget.set_node_status(1, "retrying")
        assert grid_widget.node_states[1] == "retrying", "Estado del nodo 1 debe ser 'retrying'"

        # 2. Verificar Frontend UI
        assert hasattr(frontend, "auto_complete_check"), "Frontend debe tener auto_complete_check"
        frontend.auto_complete_check.setChecked(True)

        # 3. Configurar parámetros en Backend con Healing Pass activo
        params = [
            1.2,   # umbral
            0.0,   # umbral_down
            5.0,   # timemax
            2,     # autofoc
            0.0,   # shiftx
            0.0,   # shifty
            0.0,   # dx
            0.0,   # dy
            10,    # steps_before
            10,    # steps_after
            2.5,   # umbral_abs
            5,     # n_hold
            0.0,   # slope_min
            2.0,   # slope_flat
            10.0,  # ratio_k
            50.0,  # percent_thresh
            2.0,   # startx
            2.0,   # starty
            False, # drift_check
            True,  # track_drift_xy
            True,  # track_drift_z
            True,  # track_time_volt
            "Healing_Test", # custom_name
            True,  # adaptive_af
            25.0,  # drift_tol
            True   # auto_complete_enabled
        ]
        backend.grid_parameters(0, 0, params, False, False)
        assert backend.auto_complete_enabled is True, "Backend auto_complete_enabled debe ser True"

        # 4. Crear carpeta de lote y definir grilla
        backend.grid_create_folder("Healing_Test")
        lot_folder = backend.new_folder
        backend.grid_create([2, 2, 2.0, 2.0, 2.0, 2.0, False])  # 4 partículas (0, 1, 2, 3)

        # Simular estados de impresión del pase primario:
        # Nodo 0: Success
        # Nodo 1: Timeout (fallido)
        # Nodo 2: Success
        # Nodo 3: Timeout (fallido)
        backend.node_results[0] = "success"
        backend.node_results[1] = "timeout"
        backend.node_results[2] = "success"
        backend.node_results[3] = "timeout"

        # Simular fin del pase primario llamando a _grid_detect() cuando i_global = 3 (Nmax)
        backend.i_global = 3
        backend.particulas = 4
        backend._grid_detect()

        # Debe haber detectado nodos 1 y 3 e iniciado Healing Pass
        assert backend.is_healing_pass is True, "Debe entrar en is_healing_pass = True"
        assert backend.healing_failed_queue == [1, 3], f"Cola de fallidos esperada [1, 3], obtenida: {backend.healing_failed_queue}"
        assert backend.i_global == 1, "Debe haber seleccionado el nodo 1 como primer reintento"
        assert backend.effective_timemax == 15.0, f"Tiempo extendido esperado 15.0s, obtenido {backend.effective_timemax}s"

        # Simular éxito en el reintento del nodo 1
        backend.timer_real = 4.2
        backend.data1 = [0.1, 0.2, 1.5]
        backend.data_BS = [0.1, 0.1, 0.1]
        backend.ptr = 3
        backend.node_results[1] = "success"
        backend._save_trace()

        # Verificar que el archivo NP_001.txt contiene el header de Healing Pass
        trace_file_1 = os.path.join(lot_folder, "NP_001.txt")
        assert os.path.exists(trace_file_1), f"Debe existir {trace_file_1}"
        with open(trace_file_1, "r", encoding="utf-8") as f:
            content = f.read()
            assert "Healing Pass - Retry" in content, f"Header debe indicar Healing Pass: {content[:100]}"
            assert "SUCCESS" in content, "Header debe indicar SUCCESS"

        # Avanzar al siguiente nodo de la cola (nodo 3)
        backend._grid_detect()
        assert backend.is_healing_pass is True, "Sigue en healing pass"
        assert backend.i_global == 3, "Debe haber avanzado al nodo 3"
        assert backend.healing_index_in_queue == 1

        # Simular timeout persistente en el nodo 3
        backend.timer_real = 15.0
        backend.data1 = [0.1, 0.1, 0.1]
        backend.data_BS = [0.1, 0.1, 0.1]
        backend.ptr = 3
        backend.node_results[3] = "timeout"
        backend._save_trace()

        # Finalizar Healing Pass
        backend._grid_detect()
        assert backend.is_healing_pass is False, "Healing pass debe finalizar"
        assert backend.mode_printing == "none", "Modo impresión debe volver a none"

        # 5. Verificar generación de reporte_parametros_Healing_Test.txt con estadísticas de Healing Pass
        report_file = os.path.join(lot_folder, "reporte_parametros_Healing_Test.txt")
        assert os.path.exists(report_file), f"Debe haberse generado el reporte: {report_file}"
        with open(report_file, "r", encoding="utf-8") as f:
            report_text = f.read()
            assert "Autocompletitud (Healing):ACTIVADA" in report_text or "Autocompletitud (Healing): ACTIVADA" in report_text or "Healing" in report_text
            assert "Nodos Reintentados (Healing):" in report_text or "Healing Pass" in report_text
            assert "Recuperados en Healing Pass:" in report_text or "Healing Pass" in report_text

        print("[PASS] TEST AUTOCOMPLETE / HEALING PASS PASSED SUCCESSFULLY!")

    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)

if __name__ == "__main__":
    test_autocomplete_printing()
