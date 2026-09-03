import os
import sys
import time

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PyQt6.QtWidgets import QApplication
from modules.measurements import Frontend as MeasFrontend, Backend as MeasBackend
import numpy as np

def benchmark_reset():
    app = QApplication.instance() or QApplication(sys.argv)
    
    fe = MeasFrontend(mode="printing")
    be = MeasBackend(mode="printing")
    
    fe.make_connection(be)
    
    # Grilla de 400 nodos (20x20)
    N = 400
    grid_coords = np.zeros((3, N))
    for idx in range(N):
        grid_coords[0, idx] = (idx % 20) * 2.0
        grid_coords[1, idx] = (idx // 20) * 2.0
    fe.interactive_grid.set_grid(grid_coords)
    
    print(f"[TEST] Grilla cargada con {N} nodos.")
    
    t0 = time.time()
    fe.on_reset_frontend()
    dt = time.time() - t0
    print(f"[TEST] on_reset_frontend() para {N} nodos tomó: {dt*1000:.2f} ms")

if __name__ == "__main__":
    benchmark_reset()
