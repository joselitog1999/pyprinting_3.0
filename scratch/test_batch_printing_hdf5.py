import os
import sys
import tempfile
import time
import numpy as np
from PyQt6.QtCore import QCoreApplication

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from modules.measurements import Backend
from core.hdf5_container import BatchHDF5Container
import h5py

def test_measurements_hdf5_integration():
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    temp_dir = tempfile.mkdtemp()
    
    print(f"[TEST] Inicializando Backend de Measurements en temp: {temp_dir}")
    backend = Backend()
    backend.grid_direction(temp_dir)
    
    # Configurar grilla de 4 nodos
    backend.grid_create([2, 2, 5.0, 5.0, 0.0, 0.0, False])
    backend.grid_create_folder(custom_name="TestHDF5Batch")
    
    assert backend.h5_container is not None, "El h5_container debe estar inicializado"
    assert os.path.exists(backend.h5_path), "El archivo .h5 debe existir en disco"
    print(f"[PASS] Contenedor HDF5 creado en: {backend.h5_path}")
    
    # Simular guardado de traza y scan para nodos 0, 1, 2, 3
    for i in range(4):
        backend.i_global = i
        backend.timer_real = 3.5
        backend.ptr = 100
        backend.data1 = np.ones(100) * (1.5 + 0.1 * i)
        backend.data_BS = np.ones(100) * 0.5
        backend.node_results[i] = "success"
        backend._save_trace()
        
        scan_mock = np.random.rand(16, 16) * 10.0
        backend._save_scan(scan_mock, scan_mock, scan_mock)
        
    # Finalizar lote
    backend._finalize_grid_measurement()
    assert backend.h5_container is None, "El h5_container debe quedar cerrado tras finalizar"
    
    # Verificar estructura del .h5 creado
    with h5py.File(backend.h5_path, "r") as f:
        assert "metadata" in f, "Debe tener grupo metadata"
        assert "recipe" in f, "Debe tener grupo recipe"
        assert "nodes" in f, "Debe tener grupo nodes"
        assert "node_000" in f["nodes"], "Debe existir node_000"
        assert "photothermal_trace" in f["nodes"]["node_000"], "Debe existir la traza en node_000"
        assert "confocal_scan" in f["nodes"]["node_000"], "Debe existir el confocal en node_000"
        print(f"[PASS] Verificación interna HDF5 exitosa. Nodos guardados: {list(f['nodes'].keys())}")
        
    print("[PASS] INTEGRACIÓN DE MEASUREMENTS CON HDF5 100% EXITOSA!")

if __name__ == "__main__":
    test_measurements_hdf5_integration()
