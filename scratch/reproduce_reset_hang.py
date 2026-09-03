import os
import sys
import time

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QThread
from modules.measurements import Frontend as MeasFrontend, Backend as MeasBackend
import numpy as np

def test_reset_all_hang():
    app = QApplication.instance() or QApplication(sys.argv)
    
    print("[TEST] Inicializando Frontend y Backend...")
    fe = MeasFrontend(mode="printing")
    be = MeasBackend(mode="printing")
    
    fe.make_connection(be)
    be.make_connection(fe)
    
    # Mover Backend a un QThread separado como en app.py
    thread = QThread()
    be.moveToThread(thread)
    thread.start()
    
    print("[TEST] Creando grilla de prueba de 25 nodos...")
    fe.number_files.setText("5")
    fe.number_columns.setText("5")
    fe.distance_files.setText("2.0")
    fe.distance_columns.setText("2.0")
    fe._get_grid_create()
    
    # Procesar eventos Qt
    app.processEvents()
    time.sleep(0.1)
    app.processEvents()
    
    print("[TEST] Simulando estados en nodos...")
    for i in range(10):
        be.nodeStatusSignal.emit(i, "success")
    app.processEvents()
    time.sleep(0.1)
    app.processEvents()
    
    print("[TEST] Haciendo click en Reset all 🔄...")
    t0 = time.time()
    fe.btn_reset_all.click()
    
    # Procesar eventos con timeout
    start_wait = time.time()
    while time.time() - start_wait < 3.0:
        app.processEvents()
        time.sleep(0.05)
        
    dt = time.time() - t0
    print(f"[TEST] Reset all completado en {dt:.3f} s.")
    
    # Verificar si hubo cuelgue o cómo quedó el estado
    print(f"  xref: {fe.xrefLabel.text()}")
    print(f"  indice: {fe.indice_impresionEdit.text()}")
    print(f"  NPevents: {fe.NPevents.text()}")
    
    thread.quit()
    thread.wait(1000)
    print("[TEST] Fin de la prueba.")

if __name__ == "__main__":
    test_reset_all_hang()
