# -*- coding: utf-8 -*-
"""
test_startup_hardware_profiles.py — Pruebas de Perfiles de Hardware por Defecto
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
app = QApplication.instance() or QApplication(sys.argv)

from core.hardware_manager import HardwareManager, hardware_manager


def test_pyprinting_profile_isolation():
    """Verifica que el perfil 'pyprinting' solo conecte PI y NI-DAQmx por defecto."""
    hw = HardwareManager()
    hw.set_profile("pyprinting", rescan=True)

    # 1. PI y NI-DAQ deben haberse escaneado
    assert "PI Piezo (E-517/E-727)" in hw.device_states
    assert "NI-DAQmx (Dev1)" in hw.device_states

    # 2. Espectrómetro, Andor CCD y Cámara deben estar desconectados por defecto
    st_sh = hw.device_states.get("Espectrógrafo Andor Shamrock")
    st_cam = hw.device_states.get("Cámara Andor CCD (Espectros)")
    st_usb = hw.device_states.get("Cámara USB/Thorlabs")

    assert st_sh == "disconnected"
    assert st_cam == "disconnected"
    assert st_usb == "disconnected"
    assert "Disponible bajo demanda" in hw.device_details.get("Espectrógrafo Andor Shamrock", "")


def test_pyspectrum_profile_isolation():
    """Verifica que el perfil 'pyspectrum' incluya PI, NI-DAQ, Shamrock y Andor CCD."""
    hw = HardwareManager()
    hw.set_profile("pyspectrum", rescan=True)

    target_names = [
        "PI Piezo (E-517/E-727)",
        "NI-DAQmx (Dev1)",
        "Espectrógrafo Andor Shamrock",
        "Cámara Andor CCD (Espectros)"
    ]
    for name in target_names:
        assert name in hw.device_states
        # No deben estar marcados con 'Desconectado por perfil por defecto'
        assert "Desconectado por perfil" not in hw.device_details.get(name, "")

    # La cámara USB/Canon debe quedar desconectada
    st_usb = hw.device_states.get("Cámara USB/Thorlabs")
    assert st_usb == "disconnected"
    assert "Disponible bajo demanda" in hw.device_details.get("Cámara USB/Thorlabs", "")


def test_camera_profile_isolation():
    """Verifica que el perfil 'camera' solo active la cámara por defecto."""
    hw = HardwareManager()
    hw.set_profile("camera", rescan=True)

    # Solo cámara es objetivo
    assert "Desconectado por perfil" not in hw.device_details.get("Cámara USB/Thorlabs", "")

    # PI y espectrómetro deben estar desconectados
    assert hw.device_states.get("PI Piezo (E-517/E-727)") == "disconnected"
    assert hw.device_states.get("Espectrógrafo Andor Shamrock") == "disconnected"


def test_on_demand_connection_from_profile():
    """Verifica que un instrumento desconectado por perfil pueda conectarse bajo demanda."""
    hw = HardwareManager()
    hw.set_profile("pyprinting", rescan=True)
    assert hw.device_states.get("Espectrógrafo Andor Shamrock") == "disconnected"

    # Conectar bajo demanda
    hw.connect_device("Espectrógrafo Andor Shamrock")
    # En entorno de test sin hardware físico debe terminar en disconnected o mock, pero NO 'Desconectado por perfil'
    assert "Desconectado por perfil" not in hw.device_details.get("Espectrógrafo Andor Shamrock", "")


def test_all_profile_isolation():
    """Verifica que el perfil 'all' escanee todos los dispositivos."""
    hw = HardwareManager()
    hw.set_profile("all", rescan=True)
    for dev in hw.DEVICES:
        if dev != "Espectrómetro USB (PySpectrum)":
            assert "Desconectado por perfil" not in hw.device_details.get(dev, "")


def test_profile_switching_on_the_fly():
    """Verifica que cambiar de perfil en caliente actualice la matriz de estados."""
    hw = HardwareManager()
    
    # 1. Pasar a pyprinting -> Shamrock debe quedar desconectado por perfil
    hw.set_profile("pyprinting", rescan=True)
    assert hw.active_profile == "pyprinting"
    assert "Disponible bajo demanda" in hw.device_details["Espectrógrafo Andor Shamrock"]

    # 2. Conmutar a pyspectrum -> Shamrock ahora forma parte del perfil activo
    hw.set_profile("pyspectrum", rescan=True)
    assert hw.active_profile == "pyspectrum"
    assert "Desconectado por perfil" not in hw.device_details["Espectrógrafo Andor Shamrock"]

    # 3. Conmutar a camera -> PI debe quedar desconectado por perfil
    hw.set_profile("camera", rescan=True)
    assert hw.active_profile == "camera"
    assert "Disponible bajo demanda" in hw.device_details["PI Piezo (E-517/E-727)"]


if __name__ == "__main__":
    print("[TEST 1/6] Test PyPrinting Profile Defaults...")
    test_pyprinting_profile_isolation()
    print("  -> PASS")

    print("[TEST 2/6] Test PySpectrum Profile Defaults...")
    test_pyspectrum_profile_isolation()
    print("  -> PASS")

    print("[TEST 3/6] Test Camera Profile Defaults...")
    test_camera_profile_isolation()
    print("  -> PASS")

    print("[TEST 4/6] Test 'All' Profile (Full Scan)...")
    test_all_profile_isolation()
    print("  -> PASS")

    print("[TEST 5/6] Test On-Demand Connection from Profile...")
    test_on_demand_connection_from_profile()
    print("  -> PASS")

    print("[TEST 6/6] Test Profile Switching On-The-Fly...")
    test_profile_switching_on_the_fly()
    print("  -> PASS")

    print("\n[OK] TODOS LOS PERFILES DE HARDWARE FUERON VERIFICADOS CON EXITO (6/6)!")
