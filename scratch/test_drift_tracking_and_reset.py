# -*- coding: utf-8 -*-
"""
test_drift_tracking_and_reset.py — Test automatizado para Tracking de Deriva XY/Z,
generacion de archivos .txt y PNG del mapa de deriva, y boton Reset all.
"""
import os
import sys
import time
import shutil
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import QApplication
from modules.measurements import Frontend, Backend, DriftTrackingDialog
from modules.confocal import Backend as ConfocalBackend
from modules.focus import Backend as FocusBackend

def main():
    print("=" * 70)
    print("TEST: TRACKING DE DERIVA XY/Z, MAPAS 2D Y BOTON RESET ALL")
    print("=" * 70)

    app = QApplication.instance() or QApplication(sys.argv)

    # 1. Instanciar modulos
    meas_fe = Frontend(mode="printing")
    meas_be = Backend(mode="printing")
    conf_be = ConfocalBackend()
    focu_be = FocusBackend()

    meas_fe.make_connection(meas_be)
    meas_be.make_connection(meas_fe)

    # Interconectar senales de hardware
    meas_be.grid_scanSignal.connect(conf_be.start_scan_routines)
    conf_be.scanfinishedSignal.connect(meas_be.on_scan_finished)
    meas_be.grid_autofocusSignal.connect(focu_be.focus_autocorr_lin_x2)
    focu_be.autofinishSignal.connect(meas_be.grid_finish_autofoco)

    test_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "tmp_drift_track_test"))
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)
    os.makedirs(test_dir, exist_ok=True)
    meas_be.new_folder = test_dir
    meas_fe.NameDirValue.setText(test_dir)

    print("\n[PASO 1] Probando 'Set reference' y posterior 'Reset all':")
    # Fijar referencia
    meas_be.set_reference()
    print(f"  -> X ref en GUI: {meas_fe.xrefLabel.text()}, Y ref: {meas_fe.yrefLabel.text()}")
    assert meas_fe.xrefLabel.text() != "NaN"
    assert meas_be.xref != 0.0 or meas_be.xref == 50.0

    # Ejecutar Reset All
    meas_fe.btn_reset_all.click()
    print(f"  -> Tras Reset All: X ref: {meas_fe.xrefLabel.text()}, Drift XY: '{meas_fe.drift_xy_edit.text()}', Drift Z: '{meas_fe.drift_z_edit.text()}'")
    assert meas_fe.xrefLabel.text() == "NaN"
    assert meas_be.xref == 0.0
    assert meas_be.i_global == 0
    assert meas_fe.drift_xy_edit.text() == "(+0.0, +0.0) nm | r=0.0 nm"
    assert meas_fe.drift_z_edit.text() == "+0.0 nm"

    print("\n[PASO 2] Probando 'Set reference' en nueva posicion:")
    meas_be.set_reference()
    assert meas_fe.xrefLabel.text() != "NaN"

    print("\n[PASO 3] Configurando Grilla con Track Drift XY y Track Drift Z activos:")
    assert meas_fe.track_drift_xy_check.isChecked()
    assert meas_fe.track_drift_z_check.isChecked()

    grid_params = [2, 2, 5.0, 5.0, 2.0, 2.0, True]
    meas_be.grid_create(grid_params)
    meas_be.grid_parameters(
        0, 0,
        [1.2, 0.0, 5.0, 2, 0.0, 0.0, 0.0, 0.0, 10, 10, 2.5, 5, 0.0, 2.0, 10.0, 50.0, 2.0, 2.0, True, True, True],
        False, False
    )

    tracking_dialog_opened = []
    meas_be.driftTrackingFinishedSignal.connect(lambda d: tracking_dialog_opened.append(d))

    print("\n[PASO 4] Ejecutando simulacion de ciclo de impresion...")
    meas_be._grid_start()

    # Avanzar el ciclo hasta completion
    t0 = time.time()
    while not tracking_dialog_opened and (time.time() - t0 < 8.0):
        app.processEvents()
        time.sleep(0.02)
        if meas_be.mode_printing != "none":
            meas_be._grid_detect()

    print(f"  -> Total entradas en drift_history_xy: {len(meas_be.drift_history_xy)}")
    print(f"  -> Total entradas en drift_history_z:  {len(meas_be.drift_history_z)}")
    assert len(meas_be.drift_history_xy) > 0
    assert len(meas_be.drift_history_z) > 0

    print("\n[PASO 5] Verificando generacion de archivos en carpeta del lote:")
    xy_file = os.path.join(test_dir, "drift_tracking_xy.txt")
    z_file  = os.path.join(test_dir, "drift_tracking_z.txt")
    png_file = os.path.join(test_dir, "drift_map.png")

    print(f"  -> Existe drift_tracking_xy.txt: {os.path.exists(xy_file)}")
    assert os.path.exists(xy_file)
    with open(xy_file, "r") as f:
        print("     Contenido drift_tracking_xy.txt:\n    ", f.read().strip().replace("\n", "\n     "))

    print(f"  -> Existe drift_tracking_z.txt: {os.path.exists(z_file)}")
    assert os.path.exists(z_file)
    with open(z_file, "r") as f:
        print("     Contenido drift_tracking_z.txt:\n    ", f.read().strip().replace("\n", "\n     "))

    print("\n[PASO 6] Verificando Dialogo DriftTrackingDialog y auto-guardado PNG:")
    diag = DriftTrackingDialog(tracking_dialog_opened[0])
    diag.show()
    app.processEvents()
    diag.close()

    print(f"  -> Existe drift_map.png: {os.path.exists(png_file)}")
    assert os.path.exists(png_file)

    # Limpieza
    shutil.rmtree(test_dir, ignore_errors=True)

    print("\n" + "=" * 70)
    print("TODAS LAS PRUEBAS DE TRACKING DE DERIVA Y RESET PASARON CON EXITO!")
    print("=" * 70)

if __name__ == "__main__":
    main()
