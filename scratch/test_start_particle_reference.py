import os
import sys
import tempfile
import numpy as np

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PyQt6.QtWidgets import QApplication
from core.lattice_generator import CrystalGridComposer, LatticeLayer, CrystalGridExporter
from grid_generator import GridGeneratorWindow

def test_start_particle_reference():
    app = QApplication.instance() or QApplication(sys.argv)

    # 1. Test básico de Composer en modo printing_reference
    composer = CrystalGridComposer()
    composer.layers = [LatticeLayer(name="Square", lattice_type="square", a=3.0)]
    composer.bounding_shape = "cells"
    composer.bounding_params = {"nx": 3, "ny": 3}
    composer.anchor_config.enabled = True
    composer.anchor_config.mode = "printing_reference"
    composer.anchor_config.start_x_um = 2.0
    composer.anchor_config.start_y_um = 2.0

    res = composer.generate()
    anchor = res["anchor"]
    nodes = res["nodes"]

    assert anchor is not None, "Debe tener Partícula Ancla P0"
    assert abs(anchor["x"] - 0.0) < 1e-4 and abs(anchor["y"] - 0.0) < 1e-4, f"P0 debe estar en (0,0), obtenida: ({anchor['x']}, {anchor['y']})"

    first_node = nodes[0]
    assert abs(first_node["x"] - 2.0) < 1e-4 and abs(first_node["y"] - 2.0) < 1e-4, f"Primer nodo de la red debe estar en (2.0, 2.0), obtenido: ({first_node['x']}, {first_node['y']})"
    print(f"[PASS] P0: ({anchor['x']:.2f}, {anchor['y']:.2f}) um | Primer nodo red: ({first_node['x']:.2f}, {first_node['y']:.2f}) um")

    # 2. Test cambiando start_x y start_y personalizados
    composer.anchor_config.start_x_um = 4.5
    composer.anchor_config.start_y_um = 6.0
    res2 = composer.generate()
    assert abs(res2["nodes"][0]["x"] - 4.5) < 1e-4 and abs(res2["nodes"][0]["y"] - 6.0) < 1e-4, f"Primer nodo de la red debe estar en (4.5, 6.0), obtenido: ({res2['nodes'][0]['x']}, {res2['nodes'][0]['y']})"
    print(f"[PASS] Con startX=4.5, startY=6.0 -> Primer nodo red: ({res2['nodes'][0]['x']:.2f}, {res2['nodes'][0]['y']:.2f}) um")

    # 3. Test de exportación TXT
    temp_file = tempfile.mktemp(suffix=".txt")
    try:
        CrystalGridExporter.export_single_txt(temp_file, res, include_anchor=True)
        data = np.loadtxt(temp_file)
        assert data.shape[0] == 10, f"Debe tener 10 filas (1 ancla + 9 celdas), tiene {data.shape[0]}"
        assert data[0, 0] == 0.0 and data[0, 1] == 0.0, f"Fila 0 debe ser P0 (0,0), obtenida: {data[0]}"
        assert data[1, 0] == 2.0 and data[1, 1] == 2.0, f"Fila 1 debe ser primer nodo (2,2), obtenida: {data[1]}"
        print("[PASS] Archivo TXT generado coincide 1:1 con la convención de Measurements (P0 en (0,0), red en (startX, startY))")
    finally:
        if os.path.exists(temp_file):
            os.remove(temp_file)

    # 4. Test de GUI de GridGeneratorWindow
    win = GridGeneratorWindow()
    win.geom_combo.setCurrentIndex(6)  # Celdas Nx x Ny
    win.spin_p0_off_x.setValue(3.0)
    win.spin_p0_off_y.setValue(3.0)
    
    first_x = win._current_result["nodes"][0]["x"]
    first_y = win._current_result["nodes"][0]["y"]
    assert abs(first_x - 3.0) < 1e-4 and abs(first_y - 3.0) < 1e-4, f"GUI debe actualizar la posición del primer nodo a (3.0, 3.0), obtenido: ({first_x}, {first_y})"
    print(f"[PASS] GridGeneratorWindow (Celdas Nx x Ny) actualiza dinámicamente el primer nodo a ({first_x:.2f}, {first_y:.2f}) um")

    print("[PASS] ALL TESTS FOR START PARTICLE REFERENCE PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_start_particle_reference()
