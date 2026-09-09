# -*- coding: utf-8 -*-
"""
andor_ccd_driver.py — Controlador Ctypes y Mock Resiliente para Cámara Andor CCD / EMCCD
PySpectrum 3.0 — UNSAM Nanofotónica
"""
from __future__ import annotations
import os
import sys
import time
from ctypes import c_int, c_long, c_float, byref, create_string_buffer, windll
from pathlib import Path
import threading
from typing import Tuple, Optional
import numpy as np

from config import SAFE_MODE

# Códigos de retorno Andor SDK 2
DRV_SUCCESS = 20002
DRV_NOT_INITIALIZED = 20075
DRV_ACQUIRING = 20072
DRV_IDLE = 20073
DRV_TEMP_STABILIZED = 20036
DRV_TEMP_NOT_REACHED = 20037
DRV_TEMP_DRIFT = 20040
DRV_TEMP_NOT_STABILIZED = 20035

# Modos de adquisición
ACQ_MODE_SINGLE = 1
ACQ_MODE_ACCUMULATE = 2
ACQ_MODE_KINETICS = 3
ACQ_MODE_FAST_KINETICS = 4
ACQ_MODE_RUN_TILL_ABORT = 5

# Modos de lectura
READ_MODE_FVB = 0         # Full Vertical Binning (Espectro 1D)
READ_MODE_SINGLE_TRACK = 1
READ_MODE_MULTI_TRACK = 2
READ_MODE_RANDOM_TRACK = 3
READ_MODE_IMAGE = 4       # Imagen 2D


class _MockAndorCCD:
    """Simulador transparente de Cámara Andor iXon3 EMCCD (1002x1002 px, 13 µm)."""
    is_mock = True

    def __init__(self, temperature: float = -65.0, fan_mode: str = "low"):
        self._lock = threading.RLock()
        self.width = 1004
        self.height = 1002
        self._target_temp = float(temperature)
        self._current_temp = 18.5
        self._cooler_on = True
        self._cooler_mode = 0  # 0: temp returns to ambient on shutdown, 1: maintain
        self._fan_mode = fan_mode
        self._exposure_time = 0.05  # 50 ms
        self._emccd_gain = 0
        self._output_amplifier = 0  # 0: EMCCD, 1: Convencional
        self._read_mode = READ_MODE_IMAGE
        self._track_center = 501
        self._track_height = 40
        self._acquiring = False
        self._frame_count = 0
        print("[Andor CCD SIM] Cámara Andor virtual inicializada (1004x1002, iXon3 EMCCD DU8285).")

    def is_hardware_alive(self) -> bool:
        return False

    def initialize(self) -> int:
        with self._lock:
            self._cooler_on = True
            return DRV_SUCCESS

    def close(self) -> int:
        with self._lock:
            self._acquiring = False
            if self._cooler_mode == 0:
                self._cooler_on = False
            return DRV_SUCCESS

    def set_temperature(self, temp: float) -> int:
        with self._lock:
            self._target_temp = max(-100.0, min(25.0, float(temp)))
            self.cooler_on()
            return DRV_SUCCESS

    def get_temperature(self) -> Tuple[int, float]:
        with self._lock:
            # Simula enfriamiento suave hacia el setpoint (-65 °C típico de iXon3)
            if self._cooler_on:
                diff = self._target_temp - self._current_temp
                self._current_temp += diff * 0.15
            else:
                self._current_temp += (20.0 - self._current_temp) * 0.05

            status = DRV_TEMP_STABILIZED if abs(self._current_temp - self._target_temp) < 0.5 else DRV_TEMP_NOT_REACHED
            return (status, round(self._current_temp, 1))

    def cooler_on(self) -> int:
        with self._lock:
            self._cooler_on = True
            return DRV_SUCCESS

    def cooler_off(self) -> int:
        with self._lock:
            self._cooler_on = False
            return DRV_SUCCESS

    def set_cooler_mode(self, mode: int) -> int:
        with self._lock:
            self._cooler_mode = int(mode)
            return DRV_SUCCESS

    def set_output_amplifier(self, typ: int) -> int:
        with self._lock:
            # 0: EMCCD (High Gain), 1: Conventional CCD (Ultra-low noise)
            self._output_amplifier = 0 if int(typ) == 0 else 1
            return DRV_SUCCESS

    def get_output_amplifier(self) -> int:
        with self._lock:
            return self._output_amplifier

    def set_exposure_time(self, t_sec: float) -> int:
        with self._lock:
            self._exposure_time = max(0.001, min(60.0, float(t_sec)))
            # Salvaguarda EMCCD: si exposición > 1.0 s, clampear ganancia EM a máximo 5x para proteger el registro
            if self._exposure_time > 1.0 and self._emccd_gain > 5:
                print(f"[Andor CCD Safety] Ganancia EM reducida automáticamente de {self._emccd_gain}x a 5x por exposición > 1.0s.")
                self._emccd_gain = 5
            return DRV_SUCCESS

    def get_exposure_time(self) -> float:
        with self._lock:
            return self._exposure_time

    def set_emccd_gain(self, gain: int) -> int:
        with self._lock:
            g = max(0, min(1000, int(gain)))
            # Salvaguarda EMCCD: si tiempo de exposición > 1.0 s, impedir superar 5x
            if self._exposure_time > 1.0 and g > 5:
                print(f"[Andor CCD Safety] Ganancia EM clampeada a 5x: exposición actual ({self._exposure_time:.2f}s) > 1.0s.")
                g = 5
            self._emccd_gain = g
            return DRV_SUCCESS

    def get_emccd_gain(self) -> int:
        with self._lock:
            return self._emccd_gain

    def set_read_mode(self, mode: int) -> int:
        with self._lock:
            self._read_mode = int(mode)
            return DRV_SUCCESS

    def get_read_mode(self) -> int:
        return self._read_mode

    def set_single_track(self, center: int, height: int) -> int:
        self._track_center = max(1, min(self.height, int(center)))
        self._track_height = max(1, min(self.height, int(height)))
        return DRV_SUCCESS

    def get_single_track(self) -> Tuple[int, int]:
        return (self._track_center, self._track_height)

    def set_image(self, hbin: int = 1, vbin: int = 1, hstart: int = 1, hend: int = 1004, vstart: int = 1, vend: int = 1002) -> int:
        return DRV_SUCCESS

    def start_acquisition(self) -> int:
        self._acquiring = True
        return DRV_SUCCESS

    def abort_acquisition(self) -> int:
        self._acquiring = False
        return DRV_SUCCESS

    def get_most_recent_image(self) -> np.ndarray:
        """Genera un cuadro sintético realista (ruido + ranura + resonancia plasmónica)."""
        self._frame_count += 1
        x = np.linspace(-5, 5, self.width)
        y = np.linspace(-5, 5, self.height)
        xx, yy = np.meshgrid(x, y)

        # Fondo base y ruido de lectura por píxel 2D
        dark_counts = 500.0 + np.random.normal(0, 4.0, (self.height, self.width))

        # Línea de emisión central (ranura del espectrógrafo)
        slit_profile = np.exp(-0.5 * (yy / 0.8)**2)
        # Resonancia espectral a lo largo de X (pico plasmónico centrado)
        spr_peak = 1200.0 * np.exp(-0.5 * ((xx - 0.5) / 1.2)**2)
        # Línea de bombeo láser estrecha (532 nm)
        laser_peak = 4500.0 * np.exp(-0.5 * ((xx + 1.8) / 0.08)**2)

        signal = slit_profile * (spr_peak + laser_peak + 150.0)

        frame = (dark_counts + signal).astype(np.float32)
        # En modo EMCCD (0), aplicar ganancia de multiplicación de electrones
        if self._output_amplifier == 0 and self._emccd_gain > 0:
            frame *= (1.0 + self._emccd_gain * 0.02)

        return frame

    def get_1d_spectrum(self) -> np.ndarray:
        """Devuelve el espectro 1D binnizado en hardware (FVB o Single Track) con ruido de lectura cobrado una sola vez."""
        x = np.linspace(-5, 5, self.width)
        spr_peak = 1200.0 * np.exp(-0.5 * ((x - 0.5) / 1.2)**2)
        laser_peak = 4500.0 * np.exp(-0.5 * ((x + 1.8) / 0.08)**2)
        signal_base = (spr_peak + laser_peak + 150.0)

        # Ruido de lectura analógico cobrado UNA SOLA VEZ por columna (no multiplicado por filas)
        read_noise = np.random.normal(0, 4.0, self.width)

        if self._read_mode == READ_MODE_SINGLE_TRACK:
            # Integra verticalmente solo dentro del track configurado
            dark_integrated = 500.0 + (self._track_height * 0.12)
            y_span = (self._track_height / float(self.height)) * 10.0
            integral_factor = min(1.0, max(0.2, y_span / 1.6))
            spec = (dark_integrated + signal_base * integral_factor + read_noise).astype(np.float32)
        elif self._read_mode == READ_MODE_FVB:
            # FVB suma las 1002 filas completas
            dark_integrated = 500.0 + (self.height * 0.12)
            spec = (dark_integrated + signal_base + read_noise).astype(np.float32)
        else:
            # En Modo Imagen, si se llama get_1d_spectrum, colapsa el frame 2D
            frame = self.get_most_recent_image()
            spec = np.mean(frame, axis=0)

        if self._output_amplifier == 0 and self._emccd_gain > 0:
            spec *= (1.0 + self._emccd_gain * 0.02)

        return spec

    def get_acquired_data(self) -> np.ndarray:
        if self._read_mode in (READ_MODE_FVB, READ_MODE_SINGLE_TRACK):
            return self.get_1d_spectrum()
        return self.get_most_recent_image()


class AndorCCDDriver:
    """Controlador Ctypes para la cámara física Andor iXon3 EMCCD mediante atmcd64d.dll."""
    is_mock = False

    def __init__(self):
        self._lock = threading.RLock()
        self._dll = None
        self._connected = False
        self._read_mode = READ_MODE_IMAGE
        self._track_center = 501
        self._track_height = 40
        self._current_exposure_time = 0.05
        self._init_dll()

    def is_hardware_alive(self) -> bool:
        if not self._connected or self._dll is None:
            return False
        try:
            ret, _ = self.get_temperature()
            valid_statuses = (DRV_SUCCESS, DRV_TEMP_STABILIZED, DRV_TEMP_NOT_REACHED, DRV_TEMP_DRIFT, DRV_TEMP_NOT_STABILIZED)
            return ret in valid_statuses
        except Exception:
            return False

    def _init_dll(self):
        curr_dir = Path(__file__).resolve().parent
        dll_path = curr_dir / "libs" / "atmcd64d.dll"

        if not dll_path.exists():
            print(f"[Andor CCD] DLL no encontrada en {dll_path}. Modo simulación activo.")
            return

        try:
            os.environ["PATH"] = str(dll_path.parent) + os.pathsep + os.environ.get("PATH", "")
            self._dll = windll.LoadLibrary(str(dll_path))
            print(f"[Andor CCD] DLL cargada exitosamente: {dll_path}")
        except Exception as e:
            print(f"[Andor CCD] Error al cargar atmcd64d.dll ({e}).")
            self._dll = None

    def initialize(self, dir_path: str = "") -> bool:
        if self._dll is None:
            return False
        with self._lock:
            try:
                ret = self._dll.Initialize(dir_path.encode("ascii") if dir_path else b"")
                if ret == DRV_SUCCESS:
                    self._connected = True
                    try:
                        self._dll.SetCoolerMode(c_int(0))  # 0: vuelve a ambiente al apagar (seguro)
                    except Exception:
                        pass
                    return True
                print(f"[Andor CCD] Initialize retorno código: {ret}")
                return False
            except Exception as e:
                print(f"[Andor CCD] Excepción al inicializar cámara: {e}")
                return False

    def close(self):
        with self._lock:
            if self._dll is not None and self._connected:
                try:
                    self._dll.ShutDown()
                except Exception:
                    pass
            self._connected = False

    def set_temperature(self, temp: float) -> int:
        if not self._connected or self._dll is None:
            return DRV_NOT_INITIALIZED
        with self._lock:
            ret = self._dll.SetTemperature(c_int(int(temp)))
            # Asegurar que el enfriador Peltier esté activado al definir temperatura
            self.cooler_on()
            return ret

    def get_temperature(self) -> Tuple[int, float]:
        if not self._connected or self._dll is None:
            return (DRV_NOT_INITIALIZED, 20.0)
        with self._lock:
            c_temp = c_int()
            ret = self._dll.GetTemperature(byref(c_temp))
            return (ret, float(c_temp.value))

    def cooler_on(self) -> int:
        if not self._connected or self._dll is None:
            return DRV_NOT_INITIALIZED
        with self._lock:
            return self._dll.CoolerON()

    def cooler_off(self) -> int:
        if not self._connected or self._dll is None:
            return DRV_NOT_INITIALIZED
        with self._lock:
            return self._dll.CoolerOFF()

    def set_cooler_mode(self, mode: int) -> int:
        """0: Retorna a temperatura ambiente al cerrar; 1: Mantiene temperatura."""
        if not self._connected or self._dll is None:
            return DRV_NOT_INITIALIZED
        with self._lock:
            try:
                return self._dll.SetCoolerMode(c_int(int(mode)))
            except Exception:
                return DRV_SUCCESS

    def set_output_amplifier(self, typ: int) -> int:
        """0: Multiplicador de electrones EMCCD; 1: Convencional bajo ruido CCD."""
        if not self._connected or self._dll is None:
            return DRV_NOT_INITIALIZED
        with self._lock:
            try:
                return self._dll.SetOutputAmplifier(c_int(int(typ)))
            except Exception as e:
                print(f"[Andor CCD] Error SetOutputAmplifier: {e}")
                return DRV_NOT_INITIALIZED

    def set_emccd_gain(self, gain: int) -> int:
        """Fija la ganancia EM (0 a 1000) con protección estricta contra envejecimiento."""
        if not self._connected or self._dll is None:
            return DRV_NOT_INITIALIZED
        with self._lock:
            g = max(0, min(1000, int(gain)))
            # Salvaguarda EMCCD: si tiempo de exposición > 1.0 s, impedir superar 5x
            if self._current_exposure_time > 1.0 and g > 5:
                print(f"[Andor CCD Safety] Ganancia EM clampeada a 5x: exposición actual ({self._current_exposure_time:.2f}s) > 1.0s.")
                g = 5
            try:
                return self._dll.SetEMCCDGain(c_int(g))
            except Exception as e:
                print(f"[Andor CCD] Error SetEMCCDGain: {e}")
                return DRV_NOT_INITIALIZED

    def get_emccd_gain(self) -> Tuple[int, int]:
        if not self._connected or self._dll is None:
            return (DRV_NOT_INITIALIZED, 0)
        with self._lock:
            try:
                c_gain = c_int()
                ret = self._dll.GetEMCCDGain(byref(c_gain))
                return (ret, c_gain.value)
            except Exception:
                return (DRV_NOT_INITIALIZED, 0)

    def set_exposure_time(self, t_sec: float) -> int:
        if not self._connected or self._dll is None:
            return DRV_NOT_INITIALIZED
        with self._lock:
            self._current_exposure_time = float(t_sec)
            ret = self._dll.SetExposureTime(c_float(float(t_sec)))
            # Salvaguarda EMCCD: si exposición > 1.0 s, clampear ganancia EM si supera 5x
            if self._current_exposure_time > 1.0:
                ret_g, g = self.get_emccd_gain()
                if g > 5:
                    print(f"[Andor CCD Safety] Ganancia EM reducida automáticamente de {g}x a 5x por exposición > 1.0s.")
                    self.set_emccd_gain(5)
            return ret

    def start_acquisition(self) -> int:
        if not self._connected or self._dll is None:
            return DRV_NOT_INITIALIZED
        return self._dll.StartAcquisition()

    def abort_acquisition(self) -> int:
        if not self._connected or self._dll is None:
            return DRV_NOT_INITIALIZED
        return self._dll.AbortAcquisition()

    def get_most_recent_image(self, width: int = 1004, height: int = 1002) -> np.ndarray:
        if not self._connected or self._dll is None:
            return np.zeros((height, width), dtype=np.float32)
        try:
            n_pixels = width * height
            arr = (c_long * n_pixels)()
            ret = self._dll.GetMostRecentImage(arr, c_long(n_pixels))
            if ret == DRV_SUCCESS:
                img = np.array(arr[:], dtype=np.float32).reshape((height, width))
                return img
            return np.zeros((height, width), dtype=np.float32)
        except Exception:
            return np.zeros((height, width), dtype=np.float32)

    def set_read_mode(self, mode: int) -> int:
        """0: FVB (Full Vertical Binning), 1: Single Track, 4: Image 2D."""
        if not self._connected or self._dll is None:
            return DRV_NOT_INITIALIZED
        try:
            ret = self._dll.SetReadMode(c_int(int(mode)))
            if ret == DRV_SUCCESS:
                self._read_mode = int(mode)
            return ret
        except Exception as e:
            print(f"[Andor CCD] Error SetReadMode: {e}")
            return DRV_NOT_INITIALIZED

    def get_read_mode(self) -> int:
        return self._read_mode

    def set_single_track(self, center: int, height: int) -> int:
        """Configura el ROI de integración vertical en hardware (Single Track)."""
        if not self._connected or self._dll is None:
            return DRV_NOT_INITIALIZED
        try:
            ret = self._dll.SetSingleTrack(c_int(int(center)), c_int(int(height)))
            if ret == DRV_SUCCESS:
                self._track_center = int(center)
                self._track_height = int(height)
            return ret
        except Exception as e:
            print(f"[Andor CCD] Error SetSingleTrack: {e}")
            return DRV_NOT_INITIALIZED

    def get_single_track(self) -> Tuple[int, int]:
        return (self._track_center, self._track_height)

    def set_image(self, hbin: int = 1, vbin: int = 1, hstart: int = 1, hend: int = 1004, vstart: int = 1, vend: int = 1002) -> int:
        """Configura la subárea y binning para modo imagen 2D."""
        if not self._connected or self._dll is None:
            return DRV_NOT_INITIALIZED
        try:
            return self._dll.SetImage(c_int(int(hbin)), c_int(int(vbin)),
                                      c_int(int(hstart)), c_int(int(hend)),
                                      c_int(int(vstart)), c_int(int(vend)))
        except Exception as e:
            print(f"[Andor CCD] Error SetImage: {e}")
            return DRV_NOT_INITIALIZED

    def get_1d_spectrum(self, width: int = 1004) -> np.ndarray:
        """Lee el espectro 1D binnizado en hardware (FVB o Single Track) con ruido cobrado una sola vez."""
        if not self._connected or self._dll is None:
            return np.zeros(width, dtype=np.float32)
        try:
            arr = (c_long * width)()
            ret = self._dll.GetMostRecentImage(arr, c_long(width))
            if ret == DRV_SUCCESS:
                return np.array(arr[:], dtype=np.float32)
            # Respaldo con GetAcquiredData
            ret2 = self._dll.GetAcquiredData(arr, c_long(width))
            if ret2 == DRV_SUCCESS:
                return np.array(arr[:], dtype=np.float32)
            return np.zeros(width, dtype=np.float32)
        except Exception:
            return np.zeros(width, dtype=np.float32)

    def get_acquired_data(self, width: int = 1004, height: int = 1002) -> np.ndarray:
        """Retorna datos adquiridos según el modo activo (1D para FVB/Track, 2D para Image)."""
        if self._read_mode in (READ_MODE_FVB, READ_MODE_SINGLE_TRACK):
            return self.get_1d_spectrum(width)
        return self.get_most_recent_image(width, height)


# ── Instancia Singleton y Fábrica ─────────────────────────────────────────────
_andor_instance = None

def get_andor_ccd(force_mock: bool = False, reset: bool = False) -> _MockAndorCCD | AndorCCDDriver:
    global _andor_instance
    if reset:
        if _andor_instance is not None:
            try:
                _andor_instance.close()
            except Exception:
                pass
            _andor_instance = None

    if _andor_instance is None:
        if force_mock or SAFE_MODE:
            _andor_instance = _MockAndorCCD()
        else:
            drv = AndorCCDDriver()
            if drv.initialize():
                _andor_instance = drv
            else:
                print("[Andor CCD] Hardware no detectado. Recurriendo a _MockAndorCCD.")
                _andor_instance = _MockAndorCCD()
    return _andor_instance
