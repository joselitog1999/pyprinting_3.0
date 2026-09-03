import os
import sys
import tempfile
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from core.hdf5_container import BatchHDF5Container

def test_hdf5_container():
    temp_dir = tempfile.mkdtemp()
    h5_path = os.path.join(temp_dir, "test_batch.h5")
    
    print(f"[TEST] Creando contenedor HDF5 en: {h5_path}")
    metadata = {
        "operator": "Jose Luis Gonzalez",
        "laser_wavelength": "532 nm",
        "substrate": "Glass #1.5 APTES",
        "colloid": "AuNP 60nm",
        "threshold_rel": 1.25,
        "threshold_abs_v": 2.50
    }
    
    recipe = {
        "grid_name": "Graphene_5x5_Test",
        "n_particles": 25,
        "coordinates": np.random.rand(2, 25) * 10.0,
        "anchor_p0": [0.0, 0.0]
    }
    
    container = BatchHDF5Container(h5_path, metadata=metadata, recipe=recipe)
    
    # Agregar 5 nodos
    for i in range(5):
        t = np.linspace(0.01, 2.5, 250)
        v = 1.0 + np.random.rand(250) * 0.1
        bs = 0.5 + np.random.rand(250) * 0.05
        trace = np.column_stack([t, v, bs])
        scan = np.random.rand(32, 32) * 5.0
        container.add_node_data(i, trace=trace, scan=scan, status="SUCCESS" if i > 0 else "ANCHOR", t_print=2.5)
        
    # Telemetría
    drift_xy = [
        {"node": 0, "time": 0.0, "dx_nm": 0.0, "dy_nm": 0.0, "mag_nm": 0.0, "v_xy": 0.0},
        {"node": 1, "time": 15.0, "dx_nm": 1.2, "dy_nm": -0.8, "mag_nm": 1.44, "v_xy": 0.096}
    ]
    drift_z = [
        {"node": 0, "time": 0.0, "dz_nm": 0.0, "v_z": 0.0},
        {"node": 1, "time": 15.0, "dz_nm": 2.1, "v_z": 0.14}
    ]
    container.set_telemetry(drift_xy=drift_xy, drift_z=drift_z)
    container.close()
    
    assert os.path.exists(h5_path), "El archivo .h5 debe existir"
    h5_size = os.path.getsize(h5_path)
    print(f"[PASS] Archivo HDF5 creado exitosamente ({h5_size} bytes).")
    
    # Probar desempaquetado unpack_to_legacy
    unpacked_folder = os.path.join(temp_dir, "Unpacked")
    BatchHDF5Container.unpack_to_legacy(h5_path, unpacked_folder)
    
    assert os.path.exists(os.path.join(unpacked_folder, "grid_info.txt")), "Debe existir grid_info.txt"
    assert os.path.exists(os.path.join(unpacked_folder, "NP_000.txt")), "Debe existir NP_000.txt"
    assert os.path.exists(os.path.join(unpacked_folder, "NPscan_000.tiff")), "Debe existir NPscan_000.tiff"
    assert os.path.exists(os.path.join(unpacked_folder, "drift_tracking_xy.txt")), "Debe existir drift_tracking_xy.txt"
    print(f"[PASS] Desempaquetado 1-Click verificado correctamente en: {unpacked_folder}")
    
    print("[PASS] TODOS LOS TESTS DE BATCH HDF5 CONTAINER PASARON AL 100%!")

if __name__ == "__main__":
    test_hdf5_container()
