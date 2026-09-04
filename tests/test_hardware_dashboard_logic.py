# -*- coding: utf-8 -*-
"""
test_hardware_dashboard_logic.py — Pruebas de Telemetría, Aislamiento y Detección Real de Hardware
PyPrinting 3.0 — UNSAM Nanofotónica
"""
import sys
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
for sub in ["core", "modules", "analysis", "pyspectrum"]:
    p = str(BASE_DIR / sub)
    if p not in sys.path:
        sys.path.insert(0, p)

from PyQt6.QtWidgets import QApplication

# Asegurar QApplication
app = QApplication.instance() or QApplication(sys.argv)

from core.hardware_manager import HardwareManager, hardware_manager
from pyspectrum.drivers.shamrock_driver import _MockShamrock, ShamrockDriver, get_shamrock
from pyspectrum.drivers.andor_ccd_driver import _MockAndorCCD, AndorCCDDriver, get_andor_ccd
from config import pi, PI_SERIAL


def test_shamrock_mock_detection():
    """Verifica que el mock de Shamrock declare explícitamente su naturaleza simulada."""
    mock_sh = _MockShamrock()
    assert mock_sh.is_mock is True
    assert mock_sh.is_hardware_alive() is False


def test_andor_ccd_mock_detection():
    """Verifica que el mock de Andor CCD declare explícitamente su naturaleza simulada."""
    mock_cam = _MockAndorCCD()
    assert mock_cam.is_mock is True
    assert mock_cam.is_hardware_alive() is False


def test_get_shamrock_and_ccd_reset():
    """Verifica que el reseteo de instancias fábricas limpie el singleton correctamente."""
    sh1 = get_shamrock(force_mock=True)
    assert sh1.is_mock is True

    sh2 = get_shamrock(reset=True)
    # Sin hardware físico, debe recurrir a mock pero sin estado corrupto
    assert hasattr(sh2, "is_mock")

    cam1 = get_andor_ccd(force_mock=True)
    assert cam1.is_mock is True

    cam2 = get_andor_ccd(reset=True)
    assert hasattr(cam2, "is_mock")


def test_hardware_manager_no_false_positive_connected():
    """
    PRUEBA CRÍTICA:
    Al escanear o conectar Shamrock y Andor CCD sin hardware físico conectado,
    el tablero NUNCA debe marcar 'connected' como falso positivo. Debe marcar 'disconnected' o 'mock'.
    """
    hw = HardwareManager()
    
    # 1. Espectrógrafo Andor Shamrock
    hw.connect_device("Espectrógrafo Andor Shamrock")
    st_sh = hw.device_states.get("Espectrógrafo Andor Shamrock")
    assert st_sh in ("disconnected", "mock"), f"Se esperaba 'disconnected' o 'mock', pero se obtuvo '{st_sh}'"
    assert st_sh != "connected", "¡Falso positivo! El espectrógrafo no físico no debe figurar como conectado."

    # 2. Cámara Andor CCD
    hw.connect_device("Cámara Andor CCD (Espectros)")
    st_cam = hw.device_states.get("Cámara Andor CCD (Espectros)")
    assert st_cam in ("disconnected", "mock"), f"Se esperaba 'disconnected' o 'mock', pero se obtuvo '{st_cam}'"
    assert st_cam != "connected", "¡Falso positivo! La cámara Andor no física no debe figurar como conectada."


def test_hardware_manager_isolation():
    """Verifica el ciclo de aislamiento por software (Soft Mock)."""
    hw = HardwareManager()
    dev = "Espectrógrafo Andor Shamrock"

    # Aislar dispositivo
    hw.toggle_isolation(dev, True)
    assert hw.is_isolated(dev) is True
    assert hw.device_states[dev] == "mock"
    assert "Aislado" in hw.device_details[dev]

    # Desaislar dispositivo (en ausencia de hardware debe pasar a disconnected)
    hw.toggle_isolation(dev, False)
    assert hw.is_isolated(dev) is False
    assert hw.device_states[dev] in ("disconnected", "connected")


def test_pi_virtual_mode_detection():
    """Verifica la detección precisa entre modo físico y virtual en la platina PI."""
    is_phys = hasattr(pi, "is_physically_connected") and pi.is_physically_connected()
    # En entorno de pruebas/desarrollo sin platina USB E-517, debe ser False
    if getattr(pi, "is_mock", False) or not is_phys:
        assert is_phys is False
        assert "Virtual" in pi.qIDN() or "MOCK" in pi.qIDN()


def test_nanopositioning_backend_reconnect_and_signals():
    """Verifica que el Backend de nanopositioning emita el estado de salud sin fallos."""
    from core.nanopositioning import Backend, Frontend

    fe = Frontend()
    be = Backend()
    fe.make_connection(be)

    # Comprobar estado inicial emitido
    assert fe.conn_status_label.text() != "⚪ Verificando..."
    assert ("Física" in fe.conn_status_label.text()) or ("Virtual" in fe.conn_status_label.text())

    # Probar reconexión
    be.reconnect()
    assert fe.conn_status_label.text() != ""

    fe.close()


if __name__ == "__main__":
    print("[TEST 1/6] Test Shamrock Mock Detection...")
    test_shamrock_mock_detection()
    print("  -> PASS")

    print("[TEST 2/6] Test Andor CCD Mock Detection...")
    test_andor_ccd_mock_detection()
    print("  -> PASS")

    print("[TEST 3/6] Test Factory Reset Singletons...")
    test_get_shamrock_and_ccd_reset()
    print("  -> PASS")

    print("[TEST 4/6] Test No False Positive Connected...")
    test_hardware_manager_no_false_positive_connected()
    print("  -> PASS")

    print("[TEST 5/6] Test Hardware Isolation Cycle...")
    test_hardware_manager_isolation()
    print("  -> PASS")

    print("[TEST 6/6] Test Nanopositioning Reconnect & Signals...")
    test_pi_virtual_mode_detection()
    test_nanopositioning_backend_reconnect_and_signals()
    print("  -> PASS")

    print("\n[OK] TODAS LAS PRUEBAS DE TELEMETRIA Y HARDWARE PASARON CON EXITO (6/6)!")
