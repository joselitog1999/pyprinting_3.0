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
import threading
from typing import Tuple, List, Optional
import numpy as np

from config import SAFE_MODE
from pyspectrum.drivers.andor_ccd_driver import DETECTOR_WIDTH_PX, DETECTOR_PIXEL_PITCH_UM

# Constantes del espectrógrafo
DEVICE = 0
GRATING_150_LINES = 1
GRATING_1200_LINES = 2
GRATING_MIRROR = 3

# Tiempos de asentamiento mecánico prudenciales (en segundos)
GRATING_SETTLING_TIME_S = 4.0     # Rotación del revólver motorizado de 3 redes
SLIT_SETTLING_TIME_S = 0.8        # Traslación de mordazas micrométricas de ranura
WAVELENGTH_SETTLING_TIME_S = 0.3  # Giro del tornillo micrométrico de longitud de onda

SHAMROCK_INPUT_FLIPPER = 1
SHAMROCK_OUTPUT_FLIPPER = 2
SHAMROCK_DIRECT_PORT = 0
SHAMROCK_SIDE_PORT = 1
INPUT_SLIT_PORT = 1
SHAMROCK_SHUTTER = 1

# Geometría del detector: alias de la fuente única en `andor_ccd_driver` (DEC-031/DEC-033).
NUMBER_OF_PIXELS = DETECTOR_WIDTH_PX

# Dispersión recíproca lineal nominal del Shamrock 500i para las dos redes instaladas, en nm/mm,
# de la hoja de datos de Andor ("Nominal dispersion"): 150 l/mm blaze 800 nm y 1200 l/mm blaze
# 500 nm. Multiplicada por el ancho del detector (1004 x 8 µm = 8.032 mm) da ventanas de
# 103.05 / 11.57 nm — las mismas 103 / 12 nm que el legado midió en el banco. El eje de
# medición NO sale de acá sino de `ShamrockGetCalibration`; estos valores alimentan el mock, la
# planificación de respaldo del Step & Glue y los indicadores previos a la primera adquisición.
NOMINAL_DISPERSION_150_NM_PER_MM = 12.83
NOMINAL_DISPERSION_1200_NM_PER_MM = 1.44

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

# Código propio (no del SDK): la geometría se configuró sin error pero la relectura no coincide.
GEOMETRY_READBACK_MISMATCH = -1
PIXEL_WIDTH_READBACK_TOL_UM = 1e-3

NOMINAL_DISPERSION_NM_PER_MM = {
    GRATING_150_LINES: NOMINAL_DISPERSION_150_NM_PER_MM,
    GRATING_1200_LINES: NOMINAL_DISPERSION_1200_NM_PER_MM,
    GRATING_MIRROR: 0.0,  # el espejo forma imagen: no dispersa
}


def nominal_dispersion_nm_per_px(grating: int, pixel_width_um: float = DETECTOR_PIXEL_PITCH_UM) -> float:
    """Dispersión nominal en nm/px: la de la red (hoja de datos) por el ancho de píxel."""
    per_mm = NOMINAL_DISPERSION_NM_PER_MM.get(int(grating), NOMINAL_DISPERSION_150_NM_PER_MM)
    return per_mm * float(pixel_width_um) / 1000.0


def nominal_window_nm(grating: int, num_pixels: int = DETECTOR_WIDTH_PX,
                      pixel_width_um: float = DETECTOR_PIXEL_PITCH_UM) -> float:
    """Ancho espectral nominal que cubre el detector completo con la red dada."""
    return nominal_dispersion_nm_per_px(grating, pixel_width_um) * int(num_pixels)


def _configure_and_verify_geometry(spec, device: int, num_pixels: int, pixel_width_um: float) -> int:
    """Le informa al espectrógrafo la geometría del detector y la relee antes de darla por buena.

    El SDK del Shamrock calcula λ(píxel) con el número de píxeles y su ancho: sin ellos,
    `ShamrockGetCalibration` no tiene con qué construir el eje. Siguiendo `DEC-014`, el
    resultado sólo es SUCCESS si lo configurado vuelve idéntico al releerlo; `geometry_verified`
    registra ese veredicto para que los consumidores puedan desconfiar del eje. Compartido por
    el driver real y el mock para que ambos recorran exactamente el mismo protocolo.
    """
    spec.geometry_verified = False
    for ret in (spec.set_number_pixels(device, num_pixels), spec.set_pixel_width(device, pixel_width_um)):
        if ret != SHAMROCK_SUCCESS:
            return ret
    ret_n, n_read = spec.get_number_pixels(device)
    if ret_n != SHAMROCK_SUCCESS:
        return ret_n
    ret_w, w_read = spec.get_pixel_width(device)
    if ret_w != SHAMROCK_SUCCESS:
        return ret_w
    if int(n_read) != int(num_pixels) or abs(float(w_read) - float(pixel_width_um)) > PIXEL_WIDTH_READBACK_TOL_UM:
        return GEOMETRY_READBACK_MISMATCH
    spec.geometry_verified = True
    return SHAMROCK_SUCCESS


def _no_axis(num_pixels: int) -> np.ndarray:
    """Eje λ de una lectura fallida: todo NaN, para que ningún gráfico ni cálculo lo tome por real."""
    return np.full(int(num_pixels), np.nan, dtype=np.float64)


class _MockShamrock:
    """Simulador transparente de Espectrógrafo Andor Shamrock para Modo Seguro."""
    available = True
    unavailable_reason = ""
    is_mock = True

    def __init__(self):
        self._lock = threading.RLock()
        self._connected = True
        self._grating = GRATING_150_LINES
        self._wavelength = 532.0
        self._slit_width = 50.0  # µm
        self._shutter_mode = 1    # 1: Open, 0: Closed
        self._flipper_in = SHAMROCK_DIRECT_PORT
        self._flipper_out = SHAMROCK_DIRECT_PORT
        self._serial = "SR-303i-SIM-UNSAM"
        self._grating_offsets = {1: 0, 2: 0, 3: 0}
        self._detector_offset = 0
        self._slit_zero_pos = 0
        self._settling_until = 0.0
        self._last_motion_type = ""
        # Geometría del detector tal como la conoce el espectrógrafo. La calibración simulada se
        # deriva de acá (paridad con el SDK real, que calcula λ(píxel) con estos dos valores),
        # así que un pitch equivocado se ve en simulación en vez de esconderse.
        self._number_pixels = DETECTOR_WIDTH_PX
        self._pixel_width_um = DETECTOR_PIXEL_PITCH_UM
        self.geometry_verified = False
        print("[Shamrock SIM] Inicializado controlador virtual de espectrógrafo.")

    def is_moving(self) -> bool:
        """Indica si el actuador mecánico (red, rendija o tornillo) está en movimiento o asentamiento."""
        with self._lock:
            return time.time() < self._settling_until

    def wait_until_ready(self, timeout_s: float = 6.0) -> bool:
        """Bloquea hasta que cesen las vibraciones y el actuador termine de asentarse."""
        t0 = time.time()
        while time.time() < self._settling_until:
            if time.time() - t0 > timeout_s:
                return False
            time.sleep(0.01)
        return True

    def is_hardware_alive(self, device: int = DEVICE) -> bool:
        return False

    def ShamrockInitialize(self, inipath: str = "") -> int:
        return SHAMROCK_SUCCESS

    def ShamrockClose(self) -> int:
        return SHAMROCK_SUCCESS

    def ShamrockGetSerialNumber(self, device: int = DEVICE) -> Tuple[int, str]:
        with self._lock:
            return (SHAMROCK_SUCCESS, self._serial)

    def ShamrockGetGrating(self, device: int = DEVICE) -> Tuple[int, int]:
        with self._lock:
            return (SHAMROCK_SUCCESS, self._grating)

    def ShamrockSetGrating(self, device: int = DEVICE, grating: int = 1) -> int:
        with self._lock:
            self._grating = max(1, min(3, int(grating)))
            self._settling_until = time.time() + (0.05 if SAFE_MODE else GRATING_SETTLING_TIME_S)
            self._last_motion_type = "grating"
            time.sleep(0.05)  # Simula movimiento del revólver motorizado
            return SHAMROCK_SUCCESS

    def ShamrockGetNumberGratings(self, device: int = DEVICE) -> Tuple[int, int]:
        return (SHAMROCK_SUCCESS, 3)

    def ShamrockGetGratingInfo(self, device: int = DEVICE, grating: int = 1) -> Tuple[int, float, str, int, int]:
        lines_map = {1: 150.0, 2: 1200.0, 3: 0.0}
        blaze_map = {1: "800nm", 2: "500nm", 3: "N/A"}
        return (SHAMROCK_SUCCESS, lines_map.get(grating, 150.0), blaze_map.get(grating, "500nm"), 0, 0)

    def ShamrockGetWavelength(self, device: int = DEVICE) -> Tuple[int, float]:
        with self._lock:
            return (SHAMROCK_SUCCESS, float(self._wavelength))

    def ShamrockSetWavelength(self, device: int = DEVICE, wavelength: float = 532.0) -> int:
        with self._lock:
            self._wavelength = round(float(wavelength), 2)
            self._settling_until = time.time() + (0.02 if SAFE_MODE else WAVELENGTH_SETTLING_TIME_S)
            self._last_motion_type = "wavelength"
            time.sleep(0.02)  # Simula movimiento del motor de paso
            return SHAMROCK_SUCCESS

    def ShamrockGetSlit(self, device: int = DEVICE, index: int = INPUT_SLIT_PORT) -> Tuple[int, float]:
        with self._lock:
            return (SHAMROCK_SUCCESS, float(self._slit_width))

    def ShamrockSetSlit(self, device: int = DEVICE, index: int = INPUT_SLIT_PORT, width: float = 50.0) -> int:
        with self._lock:
            self._slit_width = max(10.0, min(2500.0, float(width)))
            self._settling_until = time.time() + (0.02 if SAFE_MODE else SLIT_SETTLING_TIME_S)
            self._last_motion_type = "slit"
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

    def set_number_pixels(self, device: int = DEVICE, num_pixels: int = NUMBER_OF_PIXELS) -> int:
        if int(num_pixels) <= 0:
            return SHAMROCK_P2INVALID
        with self._lock:
            self._number_pixels = int(num_pixels)
        return SHAMROCK_SUCCESS

    def get_number_pixels(self, device: int = DEVICE) -> Tuple[int, int]:
        return (SHAMROCK_SUCCESS, int(self._number_pixels))

    def set_pixel_width(self, device: int = DEVICE, width_um: float = DETECTOR_PIXEL_PITCH_UM) -> int:
        if not float(width_um) > 0.0:
            return SHAMROCK_P2INVALID
        with self._lock:
            self._pixel_width_um = float(width_um)
        return SHAMROCK_SUCCESS

    def get_pixel_width(self, device: int = DEVICE) -> Tuple[int, float]:
        return (SHAMROCK_SUCCESS, float(self._pixel_width_um))

    def ShamrockSetNumberPixels(self, device: int = DEVICE, num_pixels: int = NUMBER_OF_PIXELS) -> int:
        return self.set_number_pixels(device, num_pixels)

    def ShamrockGetNumberPixels(self, device: int = DEVICE) -> Tuple[int, int]:
        return self.get_number_pixels(device)

    def ShamrockSetPixelWidth(self, device: int = DEVICE, width_um: float = DETECTOR_PIXEL_PITCH_UM) -> int:
        return self.set_pixel_width(device, width_um)

    def ShamrockGetPixelWidth(self, device: int = DEVICE) -> Tuple[int, float]:
        return self.get_pixel_width(device)

    def configure_detector_geometry(self, device: int = DEVICE, num_pixels: int = DETECTOR_WIDTH_PX,
                                    pixel_width_um: float = DETECTOR_PIXEL_PITCH_UM) -> int:
        return _configure_and_verify_geometry(self, device, num_pixels, pixel_width_um)

    def ShamrockGetCalibration(self, device: int = DEVICE, num_pixels: int = NUMBER_OF_PIXELS) -> Tuple[int, np.ndarray]:
        # Dispersión nominal del SR-500i (hoja de datos) por el ancho de píxel configurado:
        # 150 l/mm -> 12.83 nm/mm (0.1026 nm/px con 8 µm); 1200 l/mm -> 1.44 nm/mm (0.0115 nm/px).
        dispersion = nominal_dispersion_nm_per_px(self._grating, self._pixel_width_um)
        half_span = (num_pixels / 2.0) * dispersion
        wl_axis = np.linspace(self._wavelength - half_span, self._wavelength + half_span, num_pixels)
        return (SHAMROCK_SUCCESS, wl_axis)

    def ShamrockGetPixelCalibrationCoefficients(self, device: int = DEVICE) -> Tuple[int, float, float, float, float]:
        """Simula los coeficientes cúbicos de la EEPROM de Shamrock para λ(p) = a + b*p + c*p^2 + d*p^3."""
        dispersion = nominal_dispersion_nm_per_px(self._grating, self._pixel_width_um)
        a = float(self._wavelength - (self._number_pixels / 2.0) * dispersion)
        b = float(dispersion)
        c = 1e-6 if dispersion > 0 else 0.0
        d = -1e-10 if dispersion > 0 else 0.0
        return (SHAMROCK_SUCCESS, a, b, c, d)

    def get_pixel_calibration_coefficients(self, device: int = DEVICE) -> Tuple[int, Tuple[float, float, float, float]]:
        ret, a, b, c, d = self.ShamrockGetPixelCalibrationCoefficients(device)
        return (ret, (a, b, c, d))

    def ShamrockGotoZeroOrder(self, device: int = DEVICE) -> int:
        self._wavelength = 0.0
        return SHAMROCK_SUCCESS

    def goto_zero_order(self, device: int = DEVICE) -> int:
        return self.ShamrockGotoZeroOrder(device)

    def ShamrockGetGratingOffset(self, device: int = DEVICE, grating: int = 1) -> Tuple[int, int]:
        return (SHAMROCK_SUCCESS, int(self._grating_offsets.get(grating, 0)))

    def ShamrockSetGratingOffset(self, device: int = DEVICE, grating: int = 1, offset: int = 0) -> int:
        self._grating_offsets[grating] = int(offset)
        return SHAMROCK_SUCCESS

    def get_grating_offset(self, device: int = DEVICE, grating: int = 1) -> Tuple[int, int]:
        return self.ShamrockGetGratingOffset(device, grating)

    def set_grating_offset(self, device: int = DEVICE, grating: int = 1, offset: int = 0) -> int:
        return self.ShamrockSetGratingOffset(device, grating, offset)

    def ShamrockGetDetectorOffset(self, device: int = DEVICE) -> Tuple[int, int]:
        return (SHAMROCK_SUCCESS, int(self._detector_offset))

    def ShamrockSetDetectorOffset(self, device: int = DEVICE, offset: int = 0) -> int:
        self._detector_offset = int(offset)
        return SHAMROCK_SUCCESS

    def get_detector_offset(self, device: int = DEVICE) -> Tuple[int, int]:
        return self.ShamrockGetDetectorOffset(device)

    def set_detector_offset(self, device: int = DEVICE, offset: int = 0) -> int:
        return self.ShamrockSetDetectorOffset(device, offset)

    def ShamrockGetSlitZeroPosition(self, device: int = DEVICE, index: int = INPUT_SLIT_PORT) -> Tuple[int, int]:
        return (SHAMROCK_SUCCESS, int(self._slit_zero_pos))

    def ShamrockSetSlitZeroPosition(self, device: int = DEVICE, index: int = INPUT_SLIT_PORT, offset: int = 0) -> int:
        self._slit_zero_pos = int(offset)
        return SHAMROCK_SUCCESS

    def get_slit_zero_position(self, device: int = DEVICE, index: int = INPUT_SLIT_PORT) -> Tuple[int, int]:
        return self.ShamrockGetSlitZeroPosition(device, index)

    def set_slit_zero_position(self, device: int = DEVICE, index: int = INPUT_SLIT_PORT, offset: int = 0) -> int:
        return self.ShamrockSetSlitZeroPosition(device, index, offset)

    def get_wavelength_axis_cubic(self, device: int = DEVICE, num_pixels: int = NUMBER_OF_PIXELS) -> Tuple[int, np.ndarray]:
        ret, (a, b, c, d) = self.get_pixel_calibration_coefficients(device)
        p = np.arange(num_pixels, dtype=np.float64)
        wl_axis = a + b * p + c * (p ** 2) + d * (p ** 3)
        return (ret, wl_axis)


class ShamrockDriver:
    """Controlador real Ctypes para el espectrógrafo Andor Shamrock."""
    is_mock = False

    def __init__(self):
        self._lock = threading.RLock()
        self._dll = None
        self._connected = False
        self._settling_until = 0.0
        self._last_motion_type = ""
        self.geometry_verified = False
        self.unavailable_reason = ""
        self._init_dll()

    @property
    def available(self) -> bool:
        """True sólo si `ShamrockInitialize` respondió éxito y la sesión sigue abierta."""
        return self._connected and self._dll is not None

    def is_moving(self) -> bool:
        """Indica si el actuador mecánico (red, rendija o tornillo) está en movimiento o asentamiento."""
        with self._lock:
            return time.time() < self._settling_until

    def wait_until_ready(self, timeout_s: float = 6.0) -> bool:
        """Bloquea hasta que cesen las vibraciones y el actuador termine de asentarse."""
        t0 = time.time()
        while time.time() < self._settling_until:
            if time.time() - t0 > timeout_s:
                return False
            time.sleep(0.01)
        return True

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
            self.unavailable_reason = f"No se encontró ShamrockCIF.dll en {dll_path}."
            print(f"[Shamrock] {self.unavailable_reason} El espectrógrafo queda NO CONECTADO.")
            return

        try:
            # Agregar directorio de DLLs a PATH para que encuentre atshamrock.dll
            os.environ["PATH"] = str(dll_dir) + os.pathsep + os.environ.get("PATH", "")
            if hasattr(os, "add_dll_directory"):
                os.add_dll_directory(str(dll_dir))

            self._dll = windll.LoadLibrary(str(dll_path))
            print(f"[Shamrock] DLL cargada exitosamente: {dll_path}")
        except Exception as e:
            self.unavailable_reason = f"No se pudo cargar ShamrockCIF.dll ({e})."
            print(f"[Shamrock] {self.unavailable_reason}")
            self._dll = None

    def initialize(self, inipath: str = "") -> bool:
        if self._dll is None:
            if not self.unavailable_reason:
                self.unavailable_reason = "No se encontró ShamrockCIF.dll (ShamrockCIF.dll no cargada)."
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
                self.unavailable_reason = ""
                return True
            self.unavailable_reason = (
                f"El espectrógrafo no respondió a ShamrockInitialize (código {ret}). ¿Solis o el "
                f"PySpectrum legado están abiertos? Sólo un programa puede usarlo a la vez.")
            print(f"[Shamrock] {self.unavailable_reason}")
            return False
        except Exception as e:
            self.unavailable_reason = f"Excepción al inicializar el espectrógrafo: {e}"
            print(f"[Shamrock] {self.unavailable_reason}")
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
        with self._lock:
            ret = self._dll.ShamrockSetGrating(c_int(device), c_int(grating))
            if ret == SHAMROCK_SUCCESS:
                self._settling_until = time.time() + GRATING_SETTLING_TIME_S
                self._last_motion_type = "grating"
            return ret

    def ShamrockSetGrating(self, device: int = DEVICE, grating: int = 1) -> int:
        return self.set_grating(device, grating)

    def get_wavelength(self, device: int = DEVICE) -> Tuple[int, float]:
        if not self._connected or self._dll is None:
            return (SHAMROCK_NOT_INITIALIZED, 532.0)
        with self._lock:
            c_wl = c_float()
            ret = self._dll.ShamrockGetWavelength(c_int(device), byref(c_wl))
            return (ret, float(c_wl.value))

    def ShamrockGetWavelength(self, device: int = DEVICE) -> Tuple[int, float]:
        return self.get_wavelength(device)

    def set_wavelength(self, device: int = DEVICE, wavelength: float = 532.0) -> int:
        if not self._connected or self._dll is None:
            return SHAMROCK_NOT_INITIALIZED
        with self._lock:
            ret = self._dll.ShamrockSetWavelength(c_int(device), c_float(wavelength))
            if ret == SHAMROCK_SUCCESS:
                self._settling_until = time.time() + WAVELENGTH_SETTLING_TIME_S
                self._last_motion_type = "wavelength"
            return ret

    def ShamrockSetWavelength(self, device: int = DEVICE, wavelength: float = 532.0) -> int:
        return self.set_wavelength(device, wavelength)

    def get_slit(self, device: int = DEVICE, index: int = INPUT_SLIT_PORT) -> Tuple[int, float]:
        if not self._connected or self._dll is None:
            return (SHAMROCK_NOT_INITIALIZED, 50.0)
        with self._lock:
            c_w = c_float()
            ret = self._dll.ShamrockGetSlit(c_int(device), c_int(index), byref(c_w))
            return (ret, float(c_w.value))

    def ShamrockGetSlit(self, device: int = DEVICE, index: int = INPUT_SLIT_PORT) -> Tuple[int, float]:
        return self.get_slit(device, index)

    def set_slit(self, device: int = DEVICE, index: int = INPUT_SLIT_PORT, width: float = 50.0) -> int:
        if not self._connected or self._dll is None:
            return SHAMROCK_NOT_INITIALIZED
        with self._lock:
            # Interlock físico obligatorio (CLAUDE.md §4): las mordazas motorizadas de la
            # ranura tienen topes mecánicos duros fuera de este rango — clampear aquí evita
            # que el driver real llegue a mandarles un valor fuera de rango al DLL. Paridad
            # con _MockShamrock.ShamrockSetSlit(), que ya clampeaba (línea 139).
            width = max(10.0, min(2500.0, float(width)))
            ret = self._dll.ShamrockSetSlit(c_int(device), c_int(index), c_float(width))
            if ret == SHAMROCK_SUCCESS:
                self._settling_until = time.time() + SLIT_SETTLING_TIME_S
                self._last_motion_type = "slit"
            return ret

    def ShamrockSetSlit(self, device: int = DEVICE, index: int = INPUT_SLIT_PORT, width: float = 50.0) -> int:
        return self.set_slit(device, index, width)

    def ShamrockGetShutter(self, device: int = DEVICE) -> Tuple[int, int]:
        if not self._connected or self._dll is None:
            return (SHAMROCK_NOT_INITIALIZED, 1)
        c_mode = c_int()
        try:
            ret = self._dll.ShamrockGetShutter(c_int(device), byref(c_mode))
            return (ret, c_mode.value)
        except Exception as e:
            # DEC-034: una excepción de la DLL es un fallo, nunca un éxito. El valor de relleno
            # no se interpreta: el contrato es el código de retorno.
            print(f"[Shamrock] Error ShamrockGetShutter: {e}")
            return (SHAMROCK_COMMUNICATION_ERROR, 1)

    def ShamrockSetShutter(self, device: int = DEVICE, mode: int = 1) -> int:
        if not self._connected or self._dll is None:
            return SHAMROCK_NOT_INITIALIZED
        try:
            return self._dll.ShamrockSetShutter(c_int(device), c_int(mode))
        except Exception as e:
            print(f"[Shamrock] Error ShamrockSetShutter: {e}")
            return SHAMROCK_COMMUNICATION_ERROR

    def ShamrockGetFlipper(self, device: int = DEVICE, flipper: int = 1) -> Tuple[int, int]:
        if not self._connected or self._dll is None:
            return (SHAMROCK_NOT_INITIALIZED, 0)
        c_port = c_int()
        try:
            ret = self._dll.ShamrockGetFlipper(c_int(device), c_int(flipper), byref(c_port))
            return (ret, c_port.value)
        except Exception as e:
            print(f"[Shamrock] Error ShamrockGetFlipper: {e}")
            return (SHAMROCK_COMMUNICATION_ERROR, 0)

    def ShamrockSetFlipper(self, device: int = DEVICE, flipper: int = 1, port: int = 0) -> int:
        if not self._connected or self._dll is None:
            return SHAMROCK_NOT_INITIALIZED
        try:
            return self._dll.ShamrockSetFlipper(c_int(device), c_int(flipper), c_int(port))
        except Exception as e:
            print(f"[Shamrock] Error ShamrockSetFlipper: {e}")
            return SHAMROCK_COMMUNICATION_ERROR

    def set_number_pixels(self, device: int = DEVICE, num_pixels: int = NUMBER_OF_PIXELS) -> int:
        if not self._connected or self._dll is None:
            return SHAMROCK_NOT_INITIALIZED
        try:
            return self._dll.ShamrockSetNumberPixels(c_int(device), c_int(int(num_pixels)))
        except Exception as e:
            print(f"[Shamrock] Error ShamrockSetNumberPixels: {e}")
            return SHAMROCK_COMMUNICATION_ERROR

    def get_number_pixels(self, device: int = DEVICE) -> Tuple[int, int]:
        if not self._connected or self._dll is None:
            return (SHAMROCK_NOT_INITIALIZED, 0)
        c_n = c_int()
        try:
            ret = self._dll.ShamrockGetNumberPixels(c_int(device), byref(c_n))
            return (ret, int(c_n.value))
        except Exception as e:
            print(f"[Shamrock] Error ShamrockGetNumberPixels: {e}")
            return (SHAMROCK_COMMUNICATION_ERROR, 0)

    def set_pixel_width(self, device: int = DEVICE, width_um: float = DETECTOR_PIXEL_PITCH_UM) -> int:
        """Ancho de píxel del detector acoplado, en micrones (unidad del SDK)."""
        if not self._connected or self._dll is None:
            return SHAMROCK_NOT_INITIALIZED
        try:
            return self._dll.ShamrockSetPixelWidth(c_int(device), c_float(float(width_um)))
        except Exception as e:
            print(f"[Shamrock] Error ShamrockSetPixelWidth: {e}")
            return SHAMROCK_COMMUNICATION_ERROR

    def get_pixel_width(self, device: int = DEVICE) -> Tuple[int, float]:
        if not self._connected or self._dll is None:
            return (SHAMROCK_NOT_INITIALIZED, 0.0)
        c_w = c_float()
        try:
            ret = self._dll.ShamrockGetPixelWidth(c_int(device), byref(c_w))
            return (ret, float(c_w.value))
        except Exception as e:
            print(f"[Shamrock] Error ShamrockGetPixelWidth: {e}")
            return (SHAMROCK_COMMUNICATION_ERROR, 0.0)

    def ShamrockSetNumberPixels(self, device: int = DEVICE, num_pixels: int = NUMBER_OF_PIXELS) -> int:
        return self.set_number_pixels(device, num_pixels)

    def ShamrockGetNumberPixels(self, device: int = DEVICE) -> Tuple[int, int]:
        return self.get_number_pixels(device)

    def ShamrockSetPixelWidth(self, device: int = DEVICE, width_um: float = DETECTOR_PIXEL_PITCH_UM) -> int:
        return self.set_pixel_width(device, width_um)

    def ShamrockGetPixelWidth(self, device: int = DEVICE) -> Tuple[int, float]:
        return self.get_pixel_width(device)

    def configure_detector_geometry(self, device: int = DEVICE, num_pixels: int = DETECTOR_WIDTH_PX,
                                    pixel_width_um: float = DETECTOR_PIXEL_PITCH_UM) -> int:
        """Configura y verifica la geometría del detector en el SDK (DEC-033).

        El legado lo hacía al arrancar (`Spectrum_ps.py:157-158`); PySpectrum 3.0 nunca lo había
        hecho, así que `ShamrockGetCalibration` dependía de un estado que nadie fijaba.
        """
        ret = _configure_and_verify_geometry(self, device, num_pixels, pixel_width_um)
        if ret != SHAMROCK_SUCCESS:
            print(f"[Shamrock] ADVERTENCIA: geometría del detector NO verificada (código {ret}). "
                  f"El eje de longitudes de onda de ShamrockGetCalibration no es confiable.")
        return ret

    def get_calibration(self, device: int = DEVICE, num_pixels: int = NUMBER_OF_PIXELS) -> Tuple[int, np.ndarray]:
        # Ante cualquier falla el eje es NaN, nunca un eje inventado: antes era 400-700 nm, que
        # pasaba por real en todo consumidor que no mirara el código de retorno (DEC-040).
        if not self._connected or self._dll is None:
            return (SHAMROCK_NOT_INITIALIZED, _no_axis(num_pixels))
        try:
            arr = (c_float * num_pixels)()
            ret = self._dll.ShamrockGetCalibration(c_int(device), arr, c_int(num_pixels))
            if ret == SHAMROCK_SUCCESS:
                return (ret, np.array(arr[:], dtype=np.float64))
            return (ret, _no_axis(num_pixels))
        except Exception:
            return (SHAMROCK_COMMUNICATION_ERROR, _no_axis(num_pixels))

    def ShamrockGetCalibration(self, device: int = DEVICE, num_pixels: int = NUMBER_OF_PIXELS) -> Tuple[int, np.ndarray]:
        return self.get_calibration(device, num_pixels)

    def ShamrockGetPixelCalibrationCoefficients(self, device: int = DEVICE) -> Tuple[int, float, float, float, float]:
        """Obtiene los coeficientes polinomiales cúbicos (a, b, c, d) de calibración de fábrica de la EEPROM."""
        if not self._connected or self._dll is None:
            return (SHAMROCK_NOT_INITIALIZED, 0.0, 0.0, 0.0, 0.0)
        try:
            a = c_float()
            b = c_float()
            c = c_float()
            d = c_float()
            ret = self._dll.ShamrockGetPixelCalibrationCoefficients(c_int(device), byref(a), byref(b), byref(c), byref(d))
            if ret == SHAMROCK_SUCCESS:
                return (ret, float(a.value), float(b.value), float(c.value), float(d.value))
            return (ret, 0.0, 0.0, 0.0, 0.0)
        except Exception as e:
            print(f"[Shamrock] Error ShamrockGetPixelCalibrationCoefficients: {e}")
            return (SHAMROCK_COMMUNICATION_ERROR, 0.0, 0.0, 0.0, 0.0)

    def get_pixel_calibration_coefficients(self, device: int = DEVICE) -> Tuple[int, Tuple[float, float, float, float]]:
        ret, a, b, c, d = self.ShamrockGetPixelCalibrationCoefficients(device)
        return (ret, (a, b, c, d))

    def ShamrockGotoZeroOrder(self, device: int = DEVICE) -> int:
        """Mueve la red a Orden Cero (0.0 nm) para reflexión especular directa (alineación visual)."""
        if not self._connected or self._dll is None:
            return SHAMROCK_NOT_INITIALIZED
        try:
            if hasattr(self._dll, "ShamrockGotoZeroOrder"):
                return self._dll.ShamrockGotoZeroOrder(c_int(device))
            return self.set_wavelength(device, 0.0)
        except Exception as e:
            print(f"[Shamrock] Error ShamrockGotoZeroOrder: {e}")
            return SHAMROCK_COMMUNICATION_ERROR

    def goto_zero_order(self, device: int = DEVICE) -> int:
        return self.ShamrockGotoZeroOrder(device)

    def get_grating_offset(self, device: int = DEVICE, grating: int = 1) -> Tuple[int, int]:
        if not self._connected or self._dll is None:
            return (SHAMROCK_NOT_INITIALIZED, 0)
        c_off = c_int()
        try:
            ret = self._dll.ShamrockGetGratingOffset(c_int(device), c_int(grating), byref(c_off))
            return (ret, int(c_off.value))
        except Exception as e:
            print(f"[Shamrock] Error ShamrockGetGratingOffset: {e}")
            return (SHAMROCK_COMMUNICATION_ERROR, 0)

    def ShamrockGetGratingOffset(self, device: int = DEVICE, grating: int = 1) -> Tuple[int, int]:
        return self.get_grating_offset(device, grating)

    def set_grating_offset(self, device: int = DEVICE, grating: int = 1, offset: int = 0) -> int:
        if not self._connected or self._dll is None:
            return SHAMROCK_NOT_INITIALIZED
        try:
            return self._dll.ShamrockSetGratingOffset(c_int(device), c_int(grating), c_int(offset))
        except Exception as e:
            print(f"[Shamrock] Error ShamrockSetGratingOffset: {e}")
            return SHAMROCK_COMMUNICATION_ERROR

    def ShamrockSetGratingOffset(self, device: int = DEVICE, grating: int = 1, offset: int = 0) -> int:
        return self.set_grating_offset(device, grating, offset)

    def get_detector_offset(self, device: int = DEVICE) -> Tuple[int, int]:
        if not self._connected or self._dll is None:
            return (SHAMROCK_NOT_INITIALIZED, 0)
        c_off = c_int()
        try:
            ret = self._dll.ShamrockGetDetectorOffset(c_int(device), byref(c_off))
            return (ret, int(c_off.value))
        except Exception as e:
            print(f"[Shamrock] Error ShamrockGetDetectorOffset: {e}")
            return (SHAMROCK_COMMUNICATION_ERROR, 0)

    def ShamrockGetDetectorOffset(self, device: int = DEVICE) -> Tuple[int, int]:
        return self.get_detector_offset(device)

    def set_detector_offset(self, device: int = DEVICE, offset: int = 0) -> int:
        if not self._connected or self._dll is None:
            return SHAMROCK_NOT_INITIALIZED
        try:
            return self._dll.ShamrockSetDetectorOffset(c_int(device), c_int(offset))
        except Exception as e:
            print(f"[Shamrock] Error ShamrockSetDetectorOffset: {e}")
            return SHAMROCK_COMMUNICATION_ERROR

    def ShamrockSetDetectorOffset(self, device: int = DEVICE, offset: int = 0) -> int:
        return self.set_detector_offset(device, offset)

    def get_slit_zero_position(self, device: int = DEVICE, index: int = INPUT_SLIT_PORT) -> Tuple[int, int]:
        if not self._connected or self._dll is None:
            return (SHAMROCK_NOT_INITIALIZED, 0)
        c_pos = c_int()
        try:
            ret = self._dll.ShamrockGetSlitZeroPosition(c_int(device), c_int(index), byref(c_pos))
            return (ret, int(c_pos.value))
        except Exception as e:
            print(f"[Shamrock] Error ShamrockGetSlitZeroPosition: {e}")
            return (SHAMROCK_COMMUNICATION_ERROR, 0)

    def ShamrockGetSlitZeroPosition(self, device: int = DEVICE, index: int = INPUT_SLIT_PORT) -> Tuple[int, int]:
        return self.get_slit_zero_position(device, index)

    def set_slit_zero_position(self, device: int = DEVICE, index: int = INPUT_SLIT_PORT, offset: int = 0) -> int:
        if not self._connected or self._dll is None:
            return SHAMROCK_NOT_INITIALIZED
        try:
            return self._dll.ShamrockSetSlitZeroPosition(c_int(device), c_int(index), c_int(offset))
        except Exception as e:
            print(f"[Shamrock] Error ShamrockSetSlitZeroPosition: {e}")
            return SHAMROCK_COMMUNICATION_ERROR

    def ShamrockSetSlitZeroPosition(self, device: int = DEVICE, index: int = INPUT_SLIT_PORT, offset: int = 0) -> int:
        return self.set_slit_zero_position(device, index, offset)

    def get_wavelength_axis_cubic(self, device: int = DEVICE, num_pixels: int = NUMBER_OF_PIXELS) -> Tuple[int, np.ndarray]:
        """Calcula el eje de longitudes de onda evaluando el polinomio cúbico de fábrica de la EEPROM."""
        ret, (a, b, c, d) = self.get_pixel_calibration_coefficients(device)
        if ret == SHAMROCK_SUCCESS and (a > 0 or b > 0):
            p = np.arange(num_pixels, dtype=np.float64)
            wl_axis = a + b * p + c * (p ** 2) + d * (p ** 3)
            return (ret, wl_axis)
        # Fallback a calibración estándar
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

    if _shamrock_instance is None:
        if force_mock or SAFE_MODE:
            _shamrock_instance = _MockShamrock()
        else:
            # Fuera de SAFE_MODE nunca se cae al simulador (DEC-040, DEC-036): si la inicialización
            # falla, queda el driver real sin conectar, con `available = False` y el motivo en
            # `unavailable_reason`; sus métodos devuelven códigos de error y ningún eje inventado.
            drv = ShamrockDriver()
            if not drv.initialize():
                print(f"[Shamrock] NO CONECTADO: {drv.unavailable_reason}")
            _shamrock_instance = drv
        # Antes de que nadie pida una calibración: todo camino de inicialización (incluida la
        # reconexión de core/hardware_manager.py) pasa por acá. Si falla, el driver real se
        # conserva con geometry_verified=False — esconderlo detrás del mock sería peor.
        _shamrock_instance.configure_detector_geometry()
    return _shamrock_instance
