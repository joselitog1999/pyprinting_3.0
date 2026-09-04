# -*- coding: utf-8 -*-
"""
shamrock_driver.py — Controlador Ctypes y Mock Resiliente para Espectrógrafo Andor Shamrock
PySpectrum 3.0 — UNSAM Nanofotónica
"""
from __future__ import annotations
import os
import sys
import time
from ctypes import c_int, c_float, byref, create_string_buffer, cdll, windll
from pathlib import Path
from typing import Tuple, List, Optional
import numpy as np

from config import SAFE_MODE

# Constantes del espectrógrafo
DEVICE = 0
GRATING_150_LINES = 1
GRATING_1200_LINES = 2
GRATING_MIRROR = 3

SHAMROCK_INPUT_FLIPPER = 1
SHAMROCK_OUTPUT_FLIPPER = 2
SHAMROCK_DIRECT_PORT = 0
SHAMROCK_SIDE_PORT = 1
INPUT_SLIT_PORT = 1
SHAMROCK_SHUTTER = 1

NUMBER_OF_PIXELS = 1002
PIXEL_WIDTH_UM = 8.0

NAME_PORTS_IN = ['Port 0: Fibra Óptica', 'Port 1: Ranura (Slit)']
NAME_PORTS_OUT = ['Port 0: Cámara Andor', 'Port 1: No Usado']
NAME_GRATINGS = ['150 líneas/mm (Blaze 800 nm)', '1200 líneas/mm (Blaze 500 nm)', 'Espejo (Mirror)']

# Códigos de retorno Andor Shamrock
SHAMROCK_COMMUNICATION_ERROR = 20201
SHAMROCK_SUCCESS = 20202
SHAMROCK_P1INVALID = 20266
SHAMROCK_P2INVALID = 20267
SHAMROCK_P3INVALID = 20268
SHAMROCK_NOT_INITIALIZED = 20275
SHAMROCK_NOT_AVAILABLE = 20292


class _MockShamrock:
    """Simulador transparente de Espectrógrafo Andor Shamrock para Modo Seguro."""
    is_mock = True

    def __init__(self):
        self._connected = True
        self._grating = GRATING_150_LINES
        self._wavelength = 532.0
        self._slit_width = 50.0  # µm
        self._shutter_mode = 1    # 1: Open, 0: Closed
        self._flipper_in = SHAMROCK_DIRECT_PORT
        self._flipper_out = SHAMROCK_DIRECT_PORT
        self._serial = "SR-303i-SIM-UNSAM"
        print("[Shamrock SIM] Inicializado controlador virtual de espectrógrafo.")

    def is_hardware_alive(self, device: int = DEVICE) -> bool:
        return False

    def ShamrockInitialize(self, inipath: str = "") -> int:
        return SHAMROCK_SUCCESS

    def ShamrockClose(self) -> int:
        return SHAMROCK_SUCCESS

    def ShamrockGetSerialNumber(self, device: int = DEVICE) -> Tuple[int, str]:
        return (SHAMROCK_SUCCESS, self._serial)

    def ShamrockGetGrating(self, device: int = DEVICE) -> Tuple[int, int]:
        return (SHAMROCK_SUCCESS, self._grating)

    def ShamrockSetGrating(self, device: int = DEVICE, grating: int = 1) -> int:
        self._grating = max(1, min(3, int(grating)))
        time.sleep(0.05)  # Simula movimiento del revólver motorizado
        return SHAMROCK_SUCCESS

    def ShamrockGetNumberGratings(self, device: int = DEVICE) -> Tuple[int, int]:
        return (SHAMROCK_SUCCESS, 3)

    def ShamrockGetGratingInfo(self, device: int = DEVICE, grating: int = 1) -> Tuple[int, float, str, int, int]:
        lines_map = {1: 150.0, 2: 1200.0, 3: 0.0}
        blaze_map = {1: "800nm", 2: "500nm", 3: "N/A"}
        return (SHAMROCK_SUCCESS, lines_map.get(grating, 150.0), blaze_map.get(grating, "500nm"), 0, 0)

    def ShamrockGetWavelength(self, device: int = DEVICE) -> Tuple[int, float]:
        return (SHAMROCK_SUCCESS, float(self._wavelength))

    def ShamrockSetWavelength(self, device: int = DEVICE, wavelength: float = 532.0) -> int:
        self._wavelength = round(float(wavelength), 2)
        time.sleep(0.02)  # Simula movimiento del motor de paso
        return SHAMROCK_SUCCESS

    def ShamrockGetSlit(self, device: int = DEVICE, index: int = INPUT_SLIT_PORT) -> Tuple[int, float]:
        return (SHAMROCK_SUCCESS, float(self._slit_width))

    def ShamrockSetSlit(self, device: int = DEVICE, index: int = INPUT_SLIT_PORT, width: float = 50.0) -> int:
        self._slit_width = max(10.0, min(2500.0, float(width)))
        return SHAMROCK_SUCCESS

    def ShamrockGetShutter(self, device: int = DEVICE) -> Tuple[int, int]:
        return (SHAMROCK_SUCCESS, self._shutter_mode)

    def ShamrockSetShutter(self, device: int = DEVICE, mode: int = 1) -> int:
        self._shutter_mode = int(mode)
        return SHAMROCK_SUCCESS

    def ShamrockGetFlipper(self, device: int = DEVICE, flipper: int = 1) -> Tuple[int, int]:
        port = self._flipper_in if flipper == SHAMROCK_INPUT_FLIPPER else self._flipper_out
        return (SHAMROCK_SUCCESS, port)

    def ShamrockSetFlipper(self, device: int = DEVICE, flipper: int = 1, port: int = 0) -> int:
        if flipper == SHAMROCK_INPUT_FLIPPER:
            self._flipper_in = int(port)
        else:
            self._flipper_out = int(port)
        return SHAMROCK_SUCCESS

    def ShamrockGetCalibration(self, device: int = DEVICE, num_pixels: int = NUMBER_OF_PIXELS) -> Tuple[int, np.ndarray]:
        # Dispersión física para Shamrock SR-500i (f = 500 mm)
        # 150 l/mm -> ~13.33 nm/mm (~0.175 nm/px con pixel de 13µm)
        # 1200 l/mm -> ~1.67 nm/mm (~0.022 nm/px con pixel de 13µm)
        dispersion = 0.175 if self._grating == 1 else (0.022 if self._grating == 2 else 0.0)
        half_span = (num_pixels / 2.0) * dispersion
        wl_axis = np.linspace(self._wavelength - half_span, self._wavelength + half_span, num_pixels)
        return (SHAMROCK_SUCCESS, wl_axis)


class ShamrockDriver:
    """Controlador real Ctypes para el espectrógrafo Andor Shamrock."""
    is_mock = False

    def __init__(self):
        self._dll = None
        self._connected = False
        self._init_dll()

    def is_hardware_alive(self, device: int = DEVICE) -> bool:
        if not self._connected or self._dll is None:
            return False
        try:
            ret, sn = self.get_serial_number(device)
            return (ret == SHAMROCK_SUCCESS) and bool(sn) and (sn != "N/A")
        except Exception:
            return False

    def _init_dll(self):
        curr_dir = Path(__file__).resolve().parent
        dll_dir = curr_dir / "libs" / "Windows" / "64"
        dll_path = dll_dir / "ShamrockCIF.dll"

        if not dll_path.exists():
            print(f"[Shamrock] DLL no encontrada en {dll_path}. Modo simulación activado.")
            return

        try:
            # Agregar directorio de DLLs a PATH para que encuentre atshamrock.dll
            os.environ["PATH"] = str(dll_dir) + os.pathsep + os.environ.get("PATH", "")
            if hasattr(os, "add_dll_directory"):
                os.add_dll_directory(str(dll_dir))

            self._dll = windll.LoadLibrary(str(dll_path))
            print(f"[Shamrock] DLL cargada exitosamente: {dll_path}")
        except Exception as e:
            print(f"[Shamrock] Error al cargar ShamrockCIF.dll ({e}). Modo simulación activado.")
            self._dll = None

    def initialize(self, inipath: str = "") -> bool:
        if self._dll is None:
            return False
        try:
            if not inipath:
                # Búsqueda de inipath por defecto en sistema
                candidates = [
                    r"C:\Program Files\Andor SOLIS\SPECTROG.INI",
                    r"C:\Program Files (x86)\Andor SOLIS\SPECTROG.INI",
                    str(Path(__file__).resolve().parent / "SPECTROG.INI")
                ]
                for c in candidates:
                    if Path(c).exists():
                        inipath = c
                        break

            c_ini = inipath.encode("ascii") if inipath else b""
            ret = self._dll.ShamrockInitialize(c_ini)
            if ret == SHAMROCK_SUCCESS:
                self._connected = True
                return True
            else:
                print(f"[Shamrock] ShamrockInitialize retorno código: {ret}")
                return False
        except Exception as e:
            print(f"[Shamrock] Excepción al inicializar: {e}")
            return False

    def close(self):
        if self._dll is not None and self._connected:
            try:
                self._dll.ShamrockClose()
            except Exception:
                pass
        self._connected = False

    def get_serial_number(self, device: int = DEVICE) -> Tuple[int, str]:
        if not self._connected or self._dll is None:
            return (SHAMROCK_NOT_INITIALIZED, "N/A")
        try:
            buf = create_string_buffer(64)
            ret = self._dll.ShamrockGetSerialNumber(c_int(device), buf)
            return (ret, buf.value.decode("ascii", errors="ignore"))
        except Exception as e:
            return (SHAMROCK_COMMUNICATION_ERROR, str(e))

    def ShamrockGetSerialNumber(self, device: int = DEVICE) -> Tuple[int, str]:
        return self.get_serial_number(device)

    def get_grating(self, device: int = DEVICE) -> Tuple[int, int]:
        if not self._connected or self._dll is None:
            return (SHAMROCK_NOT_INITIALIZED, 1)
        c_grating = c_int()
        ret = self._dll.ShamrockGetGrating(c_int(device), byref(c_grating))
        return (ret, c_grating.value)

    def ShamrockGetGrating(self, device: int = DEVICE) -> Tuple[int, int]:
        return self.get_grating(device)

    def set_grating(self, device: int = DEVICE, grating: int = 1) -> int:
        if not self._connected or self._dll is None:
            return SHAMROCK_NOT_INITIALIZED
        return self._dll.ShamrockSetGrating(c_int(device), c_int(grating))

    def ShamrockSetGrating(self, device: int = DEVICE, grating: int = 1) -> int:
        return self.set_grating(device, grating)

    def get_wavelength(self, device: int = DEVICE) -> Tuple[int, float]:
        if not self._connected or self._dll is None:
            return (SHAMROCK_NOT_INITIALIZED, 532.0)
        c_wl = c_float()
        ret = self._dll.ShamrockGetWavelength(c_int(device), byref(c_wl))
        return (ret, float(c_wl.value))

    def ShamrockGetWavelength(self, device: int = DEVICE) -> Tuple[int, float]:
        return self.get_wavelength(device)

    def set_wavelength(self, device: int = DEVICE, wavelength: float = 532.0) -> int:
        if not self._connected or self._dll is None:
            return SHAMROCK_NOT_INITIALIZED
        return self._dll.ShamrockSetWavelength(c_int(device), c_float(wavelength))

    def ShamrockSetWavelength(self, device: int = DEVICE, wavelength: float = 532.0) -> int:
        return self.set_wavelength(device, wavelength)

    def get_slit(self, device: int = DEVICE, index: int = INPUT_SLIT_PORT) -> Tuple[int, float]:
        if not self._connected or self._dll is None:
            return (SHAMROCK_NOT_INITIALIZED, 50.0)
        c_w = c_float()
        ret = self._dll.ShamrockGetSlit(c_int(device), c_int(index), byref(c_w))
        return (ret, float(c_w.value))

    def ShamrockGetSlit(self, device: int = DEVICE, index: int = INPUT_SLIT_PORT) -> Tuple[int, float]:
        return self.get_slit(device, index)

    def set_slit(self, device: int = DEVICE, index: int = INPUT_SLIT_PORT, width: float = 50.0) -> int:
        if not self._connected or self._dll is None:
            return SHAMROCK_NOT_INITIALIZED
        return self._dll.ShamrockSetSlit(c_int(device), c_int(index), c_float(width))

    def ShamrockSetSlit(self, device: int = DEVICE, index: int = INPUT_SLIT_PORT, width: float = 50.0) -> int:
        return self.set_slit(device, index, width)

    def ShamrockGetShutter(self, device: int = DEVICE) -> Tuple[int, int]:
        if not self._connected or self._dll is None:
            return (SHAMROCK_NOT_INITIALIZED, 1)
        c_mode = c_int()
        try:
            ret = self._dll.ShamrockGetShutter(c_int(device), byref(c_mode))
            return (ret, c_mode.value)
        except Exception:
            return (SHAMROCK_SUCCESS, 1)

    def ShamrockSetShutter(self, device: int = DEVICE, mode: int = 1) -> int:
        if not self._connected or self._dll is None:
            return SHAMROCK_NOT_INITIALIZED
        try:
            return self._dll.ShamrockSetShutter(c_int(device), c_int(mode))
        except Exception:
            return SHAMROCK_SUCCESS

    def ShamrockGetFlipper(self, device: int = DEVICE, flipper: int = 1) -> Tuple[int, int]:
        if not self._connected or self._dll is None:
            return (SHAMROCK_NOT_INITIALIZED, 0)
        c_port = c_int()
        try:
            ret = self._dll.ShamrockGetFlipper(c_int(device), c_int(flipper), byref(c_port))
            return (ret, c_port.value)
        except Exception:
            return (SHAMROCK_SUCCESS, 0)

    def ShamrockSetFlipper(self, device: int = DEVICE, flipper: int = 1, port: int = 0) -> int:
        if not self._connected or self._dll is None:
            return SHAMROCK_NOT_INITIALIZED
        try:
            return self._dll.ShamrockSetFlipper(c_int(device), c_int(flipper), c_int(port))
        except Exception:
            return SHAMROCK_SUCCESS

    def get_calibration(self, device: int = DEVICE, num_pixels: int = NUMBER_OF_PIXELS) -> Tuple[int, np.ndarray]:
        if not self._connected or self._dll is None:
            return (SHAMROCK_NOT_INITIALIZED, np.linspace(400, 700, num_pixels))
        try:
            arr = (c_float * num_pixels)()
            ret = self._dll.ShamrockGetCalibration(c_int(device), arr, c_int(num_pixels))
            if ret == SHAMROCK_SUCCESS:
                return (ret, np.array(arr[:], dtype=np.float64))
            return (ret, np.linspace(400, 700, num_pixels))
        except Exception:
            return (SHAMROCK_COMMUNICATION_ERROR, np.linspace(400, 700, num_pixels))

    def ShamrockGetCalibration(self, device: int = DEVICE, num_pixels: int = NUMBER_OF_PIXELS) -> Tuple[int, np.ndarray]:
        return self.get_calibration(device, num_pixels)


# ── Instancia Singleton y Fábrica ─────────────────────────────────────────────
_shamrock_instance = None

def get_shamrock(force_mock: bool = False, reset: bool = False) -> _MockShamrock | ShamrockDriver:
    global _shamrock_instance
    if reset:
        if _shamrock_instance is not None:
            try:
                _shamrock_instance.close()
            except Exception:
                pass
            _shamrock_instance = None

    if force_mock or SAFE_MODE:
        return _MockShamrock()
    if _shamrock_instance is None:
        drv = ShamrockDriver()
        if drv.initialize():
            _shamrock_instance = drv
        else:
            print("[Shamrock] No fue posible inicializar hardware físico. Recurriendo a _MockShamrock.")
            _shamrock_instance = _MockShamrock()
    return _shamrock_instance
