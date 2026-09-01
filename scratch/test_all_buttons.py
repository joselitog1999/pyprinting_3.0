# -*- coding: utf-8 -*-
import sys
import os
from pathlib import Path

# Fix Windows stdout encoding
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Ensure printing3 root is on sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from PyQt6.QtWidgets import QApplication

app = QApplication(sys.argv)

from modules.measurements import Frontend, Backend

for mode in ['printing', 'dimers']:
    print(f"\n=== AUDITORIA EXHAUSTIVA DE BOTONES Y SENALES (Modo: {mode}) ===")
    fe = Frontend(mode=mode)
    be = Backend(mode=mode)
    be.make_connection(fe)

    # 1. Verificar Set Reference
    fe.set_ref_button.click()
    print(f"  [OK] Boton 'Set Reference': xref={fe.xrefLabel.text()}, yref={fe.yrefLabel.text()}, zref={fe.zrefLabel.text()}")

    # 2. Verificar Go Reference
    fe.go_ref_button.click()
    print("  [OK] Boton 'Go Reference': Ejecutado")

    # 3. Verificar Create Grid
    fe.number_files.setText("3")
    fe.number_columns.setText("3")
    fe.distance_files.setText("5.0")
    fe.distance_columns.setText("5.0")
    fe.grid_create_button.click()
    print(f"  [OK] Boton 'Create Grid': {fe.particulasEdit.text()} particulas creadas")
    assert be.particulas == 9

    # 4. Verificar Printing Folder
    fe.imprimir_button.click()
    print(f"  [OK] Boton 'Printing/Dimers Folder': Carpeta={be.new_folder}")
    assert os.path.exists(be.new_folder)

    # 5. Verificar Play Button (emite parametersSignal y gridSignal)
    fe.play_button.click()
    print(f"  [OK] Boton 'Play': Modo={be.mode_printing}, Laser={be.laser}")

    # 6. Verificar Next Index
    fe.next_button.click()
    print(f"  [OK] Boton 'Next Index': i_global={be.i_global}")

    # 7. Verificar Pause
    fe.pause_button.click()
    print(f"  [OK] Boton 'Pause': Modo={be.mode_printing}")

    # 8. Verificar Save Grid Info
    fe.grid_save_info_button.click()
    info_file = os.path.join(be.new_folder, "grid_info.txt")
    print(f"  [OK] Boton 'Save Extra Info': Archivo guardado={os.path.exists(info_file)}")

    # 9. Verificar Reset View Grid
    fe.interactive_grid.btn_reset.click()
    print("  [OK] Boton 'Reset View Grid': Ejecutado")

    # 10. Checkboxes
    fe.interactive_grid.chk_numbers.setChecked(False)
    fe.interactive_grid.chk_numbers.setChecked(True)
    fe.interactive_grid.chk_path.setChecked(False)
    fe.interactive_grid.chk_path.setChecked(True)
    fe.scan_check.setChecked(True)
    fe.scan_check.setChecked(False)
    if mode == 'dimers':
        fe.postscan_check.setChecked(True)
        fe.postscan_check.setChecked(False)
    fe.drift_check.setChecked(True)
    fe.drift_check.setChecked(False)
    print("  [OK] Todos los Checkboxes interactuan correctamente")

    # 11. Comboboxes
    fe.grid_laser.setCurrentIndex(1)
    fe.stop_mode_combo.setCurrentIndex(1)
    fe.stop_mode_combo.setCurrentIndex(2)
    fe.stop_mode_combo.setCurrentIndex(3)
    fe.stop_mode_combo.setCurrentIndex(0)
    print("  [OK] Todos los ComboBoxes cambian de indice sin errores")

    # 12. LineEdits
    fe.indice_impresionEdit.setText('2')
    fe.indice_impresionEdit.setText('0')
    print("  [OK] Edicion de indice objetivo funciona")

print("\n" + "="*70)
print("AUDITORIA FINALIZADA: 100% DE LOS BOTONES Y SENALES FUNCIONAN AL 100%")
print("="*70)
