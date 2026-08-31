import sys
import os
import tempfile
import numpy as np

# Añadir raíz al PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configurar modo headless
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import QApplication
from modules.measurements import Frontend, Backend

def test_time_remaining_eta():
    print("=" * 70)
    print("🚀 INICIANDO TEST: Estimación de Tiempo Restante (ETA)")
    print("=" * 70)

    app = QApplication.instance() or QApplication(sys.argv)

    frontend = Frontend(mode="printing")
    backend  = Backend(mode="printing")
    frontend.make_connection(backend)
    backend.make_connection(frontend)

    # 1. Verificar widget en Frontend
    assert hasattr(frontend, "time_remaining_label"), "Frontend debe tener time_remaining_label"
    assert frontend.time_remaining_label.text() == "—", f"Valor inicial debe ser '—', obtenido: {frontend.time_remaining_label.text()}"
    print("  ✅ 1. Widget time_remaining_label inicializado correctamente.")

    # 2. Configurar grilla de 25 partículas -> ETA inicial = 25 * 15s = 375s = 06m 15s
    backend.particulas = 25
    backend.particulasSignal.emit(25)
    app.processEvents()

    assert "06m 15s" in frontend.time_remaining_label.text(), f"ETA inicial esperado '~06m 15s', obtenido: {frontend.time_remaining_label.text()}"
    print(f"  ✅ 2. ETA inicial para N=25 verificado: {frontend.time_remaining_label.text()}")

    # 3. Simular impresión de nodo 0 con t_raw = 10.0 s
    backend.i_global = 0
    backend.timer_real = 10.0
    backend.t_raw_history.append(10.0)
    mean_t = float(np.mean(backend.t_raw_history))
    rem_nodes = max(0, backend.particulas - (backend.i_global + 1)) # 25 - 1 = 24
    eta_val = rem_nodes * mean_t # 24 * 10 = 240s = 04m 00s
    backend.timeRemainingSignal.emit(backend._format_eta(eta_val))
    app.processEvents()

    assert frontend.time_remaining_label.text() == "04m 00s", f"ETA esperado '04m 00s', obtenido: {frontend.time_remaining_label.text()}"
    print(f"  ✅ 3. ETA tras partícula 1 (t=10s): {frontend.time_remaining_label.text()}")

    # 4. Simular impresión de nodo 1 con t_raw = 20.0 s
    backend.i_global = 1
    backend.timer_real = 20.0
    backend.t_raw_history.append(20.0)
    mean_t = float(np.mean(backend.t_raw_history)) # (10+20)/2 = 15.0s
    rem_nodes = max(0, backend.particulas - (backend.i_global + 1)) # 25 - 2 = 23
    eta_val = rem_nodes * mean_t # 23 * 15 = 345s = 05m 45s
    backend.timeRemainingSignal.emit(backend._format_eta(eta_val))
    app.processEvents()

    assert frontend.time_remaining_label.text() == "05m 45s", f"ETA esperado '05m 45s', obtenido: {frontend.time_remaining_label.text()}"
    print(f"  ✅ 4. ETA tras partícula 2 (t=20s): {frontend.time_remaining_label.text()}")

    # 5. Simular finalización del lote
    backend.timeRemainingSignal.emit("Completado 🎉")
    app.processEvents()
    assert frontend.time_remaining_label.text() == "Completado 🎉"
    print(f"  ✅ 5. Estado de finalización verificado: {frontend.time_remaining_label.text()}")

    # 6. Verificar exportación en grid_info.txt
    with tempfile.TemporaryDirectory() as tmpdir:
        backend.old_folder = tmpdir
        backend.new_folder = tmpdir
        frontend._get_grid_info()
        app.processEvents()
        
        info_file = os.path.join(tmpdir, "grid_info.txt")
        assert os.path.exists(info_file), "grid_info.txt debe existir"
        content = open(info_file, "r", encoding="utf-8").read()
        assert "Time Remaining (ETA)" in content, "grid_info.txt debe contener Time Remaining (ETA)"
        print("  ✅ 6. Exportación en grid_info.txt verificada.")

    # 7. Verificar reset_all
    backend.reset_all()
    app.processEvents()
    assert frontend.time_remaining_label.text() == "—"
    assert backend.t_raw_history == []
    print("  ✅ 7. Reset all verificado correctamente.")

    print("=" * 70)
    print("🎉 TODAS LAS PRUEBAS DE TIME REMAINING (ETA) PASARON AL 100% (7/7)")
    print("=" * 70)

if __name__ == "__main__":
    test_time_remaining_eta()
