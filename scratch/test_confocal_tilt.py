import os
import sys
import numpy as np

# Forzar modo offscreen para testing
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PyQt6.QtWidgets import QApplication
from modules.confocal import Frontend, Backend
from modules.focus import Backend as FocusBackend

def test_confocal_tilt():
    app = QApplication.instance() or QApplication(sys.argv)

    frontend = Frontend()
    backend = Backend()
    focus_be = FocusBackend()
    backend.focus_backend = focus_be

    backend.make_connection(frontend)
    frontend.make_connection(backend)

    # 1. Verificar UI widgets
    assert hasattr(frontend, "tilt_correction_check"), "Frontend debe tener tilt_correction_check"
    assert hasattr(frontend, "lbl_confocal_eta"), "Frontend debe tener lbl_confocal_eta"
    assert hasattr(frontend, "lbl_confocal_total"), "Frontend debe tener lbl_confocal_total"
    assert hasattr(frontend, "saveimageButton"), "Frontend debe tener saveimageButton"

    # 2. Verificar activación de tilt correction vía checkbox
    frontend.tilt_correction_check.setChecked(True)
    assert backend.tilt_correction_enabled is True, "Backend debe reflejar tilt_correction_enabled = True"

    # 3. Probar advertencia si Lock Focus no está listo
    focus_be.locked_focus = False
    warning_received = []
    frontend.showTiltWarning = lambda msg: warning_received.append(msg)
    backend.tiltWarningSignal.connect(frontend.showTiltWarning)
    
    ok = backend._measure_4_corners_tilt(50.0, 50.0, 10.0, 10.0)
    assert ok is False, "Debe retornar False si lock_focus no está activo"
    assert len(warning_received) > 0, "Debe haber emitido advertencia de Lock Focus"

    # 4. Probar cálculo de plano 2D con Lock Focus listo
    focus_be.locked_focus = True
    focus_be.z_profile_lock_filter = np.ones(50)
    
    ok = backend._measure_4_corners_tilt(50.0, 50.0, 10.0, 10.0)
    assert ok is True, "Debe calcular el plano con éxito"
    assert backend.tilt_plane is not None, "tilt_plane no debe ser None"
    
    z0, alpha, beta, x_TL, y_TL = backend.tilt_plane
    print(f"Plano calculado: z0={z0:.3f}, alpha={alpha:.5f}, beta={beta:.5f}, x_TL={x_TL:.2f}, y_TL={y_TL:.2f}")

    # 5. Probar evaluación de Z
    z_eval_tl = backend._evaluate_tilt_z(x_TL, y_TL)
    assert abs(z_eval_tl - z0) < 1e-4, f"En TL, Z evaluado ({z_eval_tl}) debe coincidir con z0 ({z0})"

    # 6. Probar telemetría ETA
    eta_received = []
    backend.etaSignal.connect(lambda eta, tot: eta_received.append((eta, tot)))
    backend.etaSignal.emit("ETA: 01m 30s", "Total: ~02m 00s")
    assert frontend.lbl_confocal_eta.text() == "ETA: 01m 30s"
    assert frontend.lbl_confocal_total.text() == "Total: ~02m 00s"

    print("[PASS] TEST CONFOCAL TILT & TELEMETRY PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_confocal_tilt()
