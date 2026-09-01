import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["QT_QPA_PLATFORM"] = "offscreen"

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from PyQt6.QtWidgets import QApplication
from grid_generator import GridGeneratorWindow

def test_gui():
    print("=" * 70)
    print("🚀 INICIANDO TEST: Interfaz Gráfica de Diseñador de Redes (grid_generator.py)")
    print("=" * 70)

    app = QApplication.instance() or QApplication(sys.argv)
    win = GridGeneratorWindow()
    win.show()
    app.processEvents()

    # 1. Verificar existencia de widgets
    assert hasattr(win, "plot_widget"), "Debe tener plot_widget"
    assert hasattr(win, "preset_combo"), "Debe tener preset_combo"
    assert hasattr(win, "tabs"), "Debe tener tabs"
    print("  ✅ 1. Ventana y widgets principales instanciados correctamente.")

    # 2. Probar todos los presets
    for i in range(1, win.preset_combo.count()):
        win.preset_combo.setCurrentIndex(i)
        app.processEvents()
        assert win._current_result is not None, f"Preset {i} falló al generar"
        assert win._current_result["stats"]["total"] > 0, f"Preset {i} generó 0 nodos"
        print(f"  ✅ 2.{i} Preset '{win.preset_combo.currentText()}' verificado ({win._current_result['stats']['total']} nodos).")

    # 3. Probar asignación de materiales y coordenadas (u, v) por átomo en Grafeno (2 átomos)
    win.preset_combo.setCurrentIndex(3) # Grafeno
    app.processEvents()
    assert len(win.composer.layers[0].atoms) == 2, "Grafeno debe tener 2 átomos"
    assert win.atom_rows[0][0].isVisible() and win.atom_rows[1][0].isVisible(), "Las 2 filas de átomos deben ser visibles"
    assert not win.atom_rows[2][0].isVisible(), "La 3ra fila de átomo debe estar oculta"
    
    # Caso A: Modificar a, b y gamma independientemente en Grafeno
    win.spin_a.setValue(2.0)
    win.spin_b.setValue(3.5)
    win.spin_gamma.setValue(75.0)
    app.processEvents()
    assert win.composer.layers[0].a == 2.0 and win.composer.layers[0].b == 3.5 and win.composer.layers[0].gamma_deg == 75.0
    print("  ✅ 3.1 Modificación paramétrica libre de a1 (a=2.0), a2 (b=3.5) y γ=75.0° en Grafeno verificada.")

    # Caso B: Modificar coordenadas fraccionales (u, v) de A2
    win.atom_rows[1][1].setValue(0.40) # u2
    win.atom_rows[1][2].setValue(0.60) # v2
    app.processEvents()
    assert abs(win.composer.layers[0].atoms[1].u - 0.40) < 1e-4
    assert abs(win.composer.layers[0].atoms[1].v - 0.60) < 1e-4
    print("  ✅ 3.2 Desplazamiento fraccional interactivo de átomo A2 a (u=0.40, v=0.60) verificado.")

    # Caso C: Asignar Material 1 + Material 2 vs Material 1 + Material 1
    win.atom_rows[0][3].setCurrentIndex(0) # Mat 1
    win.atom_rows[1][3].setCurrentIndex(1) # Mat 2
    app.processEvents()
    assert len(win._current_result["passes_nodes"]) == 2
    print("  ✅ 3.3 Grafeno con 2 materiales distintos (2 pases separados) verificado.")

    win.atom_rows[1][3].setCurrentIndex(0) # Mat 1
    app.processEvents()
    assert len(win._current_result["passes_nodes"]) == 1
    print("  ✅ 3.4 Grafeno con el mismo material (1 pase unificado) verificado.")

    # 4. Probar adición y remoción dinámica de átomos
    win.btn_add_atom.click()
    app.processEvents()
    assert len(win.composer.layers[0].atoms) == 3, "Debe tener 3 átomos tras añadir uno"
    print("  ✅ 4.1 Botón '➕ Añadir Átomo' verificado (3 átomos en celda).")

    win.btn_remove_atom.click()
    app.processEvents()
    assert len(win.composer.layers[0].atoms) == 2, "Debe tener 2 átomos tras quitar uno"
    print("  ✅ 4.2 Botón '➖ Quitar Átomo' verificado (2 átomos en celda).")

    # 5. Probar nuevos tipos de red del catálogo
    # 5.1 Red de Dice / T3 (3 átomos)
    win.lattice_type_combo.setCurrentIndex(6) # Dice / T3
    app.processEvents()
    assert len(win.composer.layers[0].atoms) == 3
    print("  ✅ 5.1 Red de Dice / T3 (3 átomos) instanciada correctamente.")

    # 5.2 Monocapa TMD / MoS2 (3 átomos)
    win.lattice_type_combo.setCurrentIndex(7) # MoS2 TMD
    app.processEvents()
    assert len(win.composer.layers[0].atoms) == 3
    print("  ✅ 5.2 Monocapa TMD / MoS2 (3 átomos) instanciada correctamente.")

    # 5.3 Rectangular Centrada (2 átomos)
    win.lattice_type_combo.setCurrentIndex(9) # Rectangular Centrada
    app.processEvents()
    assert len(win.composer.layers[0].atoms) == 2
    assert win.spin_gamma.value() == 90.0
    print("  ✅ 5.3 Red Rectangular Centrada (2 átomos, γ=90°) instanciada correctamente.")

    # 6. Probar slider de ángulo gamma y sincronización bidireccional
    win.slider_gamma.setValue(1200) # 120.0°
    app.processEvents()
    assert abs(win.spin_gamma.value() - 120.0) < 1e-2, "El spinbox de gamma debe sincronizarse con el slider"
    assert abs(win.composer.layers[0].gamma_deg - 120.0) < 1e-2
    print("  ✅ 6.1 Deslizador interactivo de ángulo γ (slider -> spinbox 120.0°) verificado.")

    win.spin_gamma.setValue(45.0)
    app.processEvents()
    assert win.slider_gamma.value() == 450, "El slider debe sincronizarse con el spinbox"
    assert abs(win.composer.layers[0].gamma_deg - 45.0) < 1e-2
    print("  ✅ 6.2 Sincronización inversa de ángulo γ (spinbox -> slider 45.0°) verificada.")

    # 7. Probar restricción física de distancia mínima (d_min) entre partículas
    win.preset_combo.setCurrentIndex(1) # Hexagonal a=2.0 en hexágono ap=5
    app.processEvents()
    total_before = win._current_result["stats"]["total"]
    
    # Activar d_min = 2.5 um (mayor que el espaciamiento a=2.0 um)
    win.spin_min_dist.setValue(2.5)
    app.processEvents()
    total_after = win._current_result["stats"]["total"]
    suppressed = win._current_result["stats"]["suppressed_by_min_dist"]
    assert suppressed > 0, "Debe haber nodos suprimidos al aplicar d_min > a"
    assert total_after < total_before, "El total de nodos debe disminuir al aplicar restricción d_min"
    print(f"  ✅ 7. Restricción de distancia mínima d_min=2.5 µm verificada ({suppressed} partículas excluidas por límite físico).")

    # 8. Probar renderizado de la Celda Unidad en el panel izquierdo
    assert hasattr(win, "unit_cell_plot"), "Debe tener unit_cell_plot"
    assert hasattr(win, "lbl_unit_cell_info"), "Debe tener lbl_unit_cell_info"
    win._render_unit_cell()
    print("  ✅ 8. Renderizado interactivo de la Celda Unidad en el panel izquierdo verificado.")

    print("=" * 70)
    print("🎉 TODAS LAS PRUEBAS DE SLIDER Y DISTANCIA MÍNIMA PASARON AL 100%")
    print("=" * 70)

if __name__ == "__main__":
    test_gui()
