import sys
import os
import math
import tempfile
import numpy as np

# Agregar raíz al PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from core.lattice_generator import (
    BasisAtom, LatticeLayer, BoundingGeometry, PathOptimizer,
    AnchorConfig, CrystalGridComposer, CrystalGridExporter
)

def test_lattice_generator():
    print("=" * 70)
    print("🚀 INICIANDO TEST: Motor Cristalográfico y Generador de Redes 2D")
    print("=" * 70)

    # 1. Test Red Cuadrada por número de celdas (5x5)
    composer = CrystalGridComposer()
    composer.layers = [LatticeLayer(name="Cuadrada", lattice_type="square", a=2.0)]
    composer.bounding_shape = "cells"
    composer.bounding_params = {"nx": 5, "ny": 5}
    composer.anchor_config.enabled = True
    composer.anchor_config.mode = "offset"
    composer.anchor_config.offset_x_um = -2.0
    composer.anchor_config.offset_y_um = -2.0

    res = composer.generate()
    assert res["stats"]["grid_nodes"] == 25, f"Esperado 25 nodos de grilla, obtenido {res['stats']['grid_nodes']}"
    assert res["stats"]["total"] == 26, f"Esperado 26 con ancla, obtenido {res['stats']['total']}"
    assert res["anchor"] is not None, "El ancla debe existir"
    assert res["anchor"]["x"] == -2.0, f"Ancla X esperada -2.0, obtenido {res['anchor']['x']}"
    print("  ✅ 1. Red Cuadrada 5x5 con Partícula Ancla P0 verificada.")

    # 2. Test Red Hexagonal contenida en Hexágono de apotema ap = 5.0 µm
    composer_hex = CrystalGridComposer()
    composer_hex.layers = [LatticeLayer(name="Hex", lattice_type="hexagonal", a=2.0)]
    composer_hex.bounding_shape = "hexagon"
    composer_hex.bounding_params = {"ap": 5.0}
    composer_hex.anchor_config.enabled = True

    res_hex = composer_hex.generate()
    assert res_hex["stats"]["grid_nodes"] > 10, "Debe generar nodos dentro del hexágono"
    # Verificar que todos los nodos satisfacen la condición de apotema ap=5.0
    for n in res_hex["nodes"]:
        assert BoundingGeometry.is_inside(n["x"], n["y"], "hexagon", {"ap": 5.0}), f"Nodo fuera del hexágono: {n}"
    print(f"  ✅ 2. Red Hexagonal en Hexágono (ap=5 µm) verificada ({res_hex['stats']['grid_nodes']} nodos).")

    # 3. Test Grafeno / Honeycomb (2 átomos de diferente material por celda) en Disco
    composer_graphene = CrystalGridComposer()
    composer_graphene.layers = [LatticeLayer(name="Graphene", lattice_type="graphene", a=2.5)]
    composer_graphene.bounding_shape = "circle"
    composer_graphene.bounding_params = {"radius": 4.0}

    res_graphene = composer_graphene.generate()
    assert res_graphene["stats"]["mat1"] > 0 and res_graphene["stats"]["mat2"] > 0, "Debe contener átomos de Material 1 y Material 2"
    for n in res_graphene["nodes"]:
        assert math.hypot(n["x"], n["y"]) <= 4.0 + 1e-5, f"Nodo fuera del disco: {n}"
    print(f"  ✅ 3. Red de Grafeno/Honeycomb en Disco (R=4 µm) verificada (Mat1={res_graphene['stats']['mat1']}, Mat2={res_graphene['stats']['mat2']}).")

    # 4. Test Superred Moiré Rotada (2 capas hexagonales con rotación θ = 3.0°)
    composer_moire = CrystalGridComposer()
    layer1 = LatticeLayer(name="Layer 1 (0°)", lattice_type="hexagonal", a=3.0, rotation_deg=0.0, color="#89b4fa")
    layer1.atoms = [BasisAtom(u=0.0, v=0.0, material_id=1)]
    layer2 = LatticeLayer(name="Layer 2 (3°)", lattice_type="hexagonal", a=3.0, rotation_deg=3.0, color="#a6e3a1")
    layer2.atoms = [BasisAtom(u=0.0, v=0.0, material_id=2)]
    composer_moire.layers = [layer1, layer2]
    composer_moire.bounding_shape = "square"
    composer_moire.bounding_params = {"size": 10.0}

    res_moire = composer_moire.generate()
    assert res_moire["stats"]["mat1"] > 0 and res_moire["stats"]["mat2"] > 0, "Superred debe contener nodos de ambas capas"
    print(f"  ✅ 4. Superred Moiré Rotada (θ=3°) verificada (Total={res_moire['stats']['total']} nodos).")

    # 5. Test Optimización de Ruta (Snake / Serpiente)
    nodes_test = [
        {"x": 0.0, "y": 0.0}, {"x": 2.0, "y": 0.0},
        {"x": 0.0, "y": 2.0}, {"x": 2.0, "y": 2.0}
    ]
    sorted_snake = PathOptimizer.sort_nodes(nodes_test, mode="snake")
    assert sorted_snake[0]["x"] == 0.0 and sorted_snake[0]["y"] == 0.0
    assert sorted_snake[1]["x"] == 2.0 and sorted_snake[1]["y"] == 0.0
    assert sorted_snake[2]["x"] == 2.0 and sorted_snake[2]["y"] == 2.0 # Segunda fila invertida!
    assert sorted_snake[3]["x"] == 0.0 and sorted_snake[3]["y"] == 2.0
    print("  ✅ 5. Optimizador de Ruta (Snake Zig-Zag) verificado.")

    # 6. Test Exportación Metrológica Multi-Paso
    with tempfile.TemporaryDirectory() as tmpdir:
        files = CrystalGridExporter.export_multipass_package(tmpdir, "TestMoire", res_moire)
        assert "unified" in files and os.path.exists(files["unified"])
        assert "material_1" in files and os.path.exists(files["material_1"])
        assert "material_2" in files and os.path.exists(files["material_2"])
        assert "metadata" in files and os.path.exists(files["metadata"])

        # Verificar que la primera línea de Layer 1 y Layer 2 contiene el ancla P0
        line1_mat1 = open(files["material_1"]).readline().strip()
        line1_mat2 = open(files["material_2"]).readline().strip()
        assert line1_mat1 == line1_mat2, f"La Partícula Ancla P0 debe ser idéntica en todas las capas ({line1_mat1} vs {line1_mat2})"
        print(f"  ✅ 6. Paquete de Recetas Multi-Paso con cuadratura P0 verificado: {files.keys()}")

    print("=" * 70)
    print("🎉 TODAS LAS PRUEBAS DEL MOTOR CRISTALOGRÁFICO PASARON AL 100% (6/6)")
    print("=" * 70)

if __name__ == "__main__":
    test_lattice_generator()
