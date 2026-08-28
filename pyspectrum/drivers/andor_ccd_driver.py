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
    """Simulador transparente de Cámara Andor Newton / iDus EMCCD."""

    def __init__(self, temperature: float = -10.0, fan_mode: str = "low"):
        self.width = 1002
        self.height = 1002
        self._target_temp = float(temperature)
        self._current_temp = 18.5
        self._cooler_on = True
        self._fan_mode = fan_mode
        self._exposure_time = 0.05  # 50 ms
        self._emccd_gain = 0
        self._read_mode = READ_MODE_IMAGE
        self._acquiring = False
        self._frame_count = 0
        print("[Andor CCD SIM] Cámara Andor virtual inicializada (1002x1002).")

    def initialize(self) -> int:
        return DRV_SUCCESS

    def close(self) -> int:
        self._acquiring = False
        return DRV_SUCCESS

    def set_temperature(self, temp: float) -> int:
        self._target_temp = float(temp)
        return DRV_SUCCESS

    def get_temperature(self) -> Tuple[int, float]:
        # Simula enfriamiento suave hacia el setpoint
        if self._cooler_on:
            diff = self._target_temp - self._current_temp
            self._current_temp += diff * 0.15
        else:
            self._current_temp += (20.0 - self._current_temp) * 0.05

        status = DRV_TEMP_STABILIZED if abs(self._current_temp - self._target_temp) < 0.5 else DRV_TEMP_NOT_REACHED
        return (status, round(self._current_temp, 1))

    def cooler_on(self) -> int:
        self._cooler_on = True
        return DRV_SUCCESS

    def cooler_off(self) -> int:
        self._cooler_on = False
        return DRV_SUCCESS

    def set_exposure_time(self, t_sec: float) -> int:
        self._exposure_time = max(0.001, min(60.0, float(t_sec)))
        return DRV_SUCCESS

    def get_exposure_time(self) -> float:
        return self._exposure_time

    def set_emccd_gain(self, gain: int) -> int:
        self._emccd_gain = max(0, min(1000, int(gain)))
        return DRV_SUCCESS

    def set_read_mode(self, mode: int) -> int:
        self._read_mode = int(mode)
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

        # Fondo base y ruido de lectura
        dark_counts = 500.0 + np.random.normal(0, 4.0, (self.height, self.width))

        # Línea de emisión central (ranura del espectrógrafo)
        slit_profile = np.exp(-0.5 * (yy / 0.8)**2)
        # Resonancia espectral a lo largo de X (pico plasmónico centrado)
        spr_peak = 1200.0 * np.exp(-0.5 * ((xx - 0.5) / 1.2)**2)
        # Línea de bombeo láser estrecha (532 nm)
        laser_peak = 4500.0 * np.exp(-0.5 * ((xx + 1.8) / 0.08)**2)

        signal = slit_profile * (spr_peak + laser_peak + 150.0)

        frame = (dark_counts + signal).astype(np.float32)
        if self._emccd_gain > 0:
            frame *= (1.0 + self._emccd_gain * 0.02)

        return frame

    def get_1d_spectrum(self) -> np.ndarray:
        """Devuelve el espectro 1D binnizado verticalmente."""
        frame = self.get_most_recent_image()
        return np.mean(frame, axis=0)


class AndorCCDDriver:
    """Controlador Ctypes para la cámara física Andor CCD mediante atmcd64d.dll."""

    def __init__(self):
        self._dll = None
        self._connected = False
        self._init_dll()

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
        try:
            ret = self._dll.Initialize(dir_path.encode("ascii") if dir_path else b"")
            if ret == DRV_SUCCESS:
                self._connected = True
                return True
            print(f"[Andor CCD] Initialize retorno código: {ret}")
            return False
        except Exception as e:
            print(f"[Andor CCD] Excepción al inicializar cámara: {e}")
            return False

    def close(self):
        if self._dll is not None and self._connected:
            try:
                self._dll.ShutDown()
            except Exception:
                pass
        self._connected = False

    def set_temperature(self, temp: float) -> int:
        if not self._connected or self._dll is None:
            return DRV_NOT_INITIALIZED
        return self._dll.SetTemperature(c_int(int(temp)))

    def get_temperature(self) -> Tuple[int, float]:
        if not self._connected or self._dll is None:
            return (DRV_NOT_INITIALIZED, 20.0)
        c_temp = c_int()
        ret = self._dll.GetTemperature(byref(c_temp))
        return (ret, float(c_temp.value))

    def cooler_on(self) -> int:
        if not self._connected or self._dll is None:
            return DRV_NOT_INITIALIZED
        return self._dll.CoolerON()

    def cooler_off(self) -> int:
        if not self._connected or self._dll is None:
            return DRV_NOT_INITIALIZED
        return self._dll.CoolerOFF()

    def set_exposure_time(self, t_sec: float) -> int:
        if not self._connected or self._dll is None:
            return DRV_NOT_INITIALIZED
        return self._dll.SetExposureTime(c_float(float(t_sec)))

    def start_acquisition(self) -> int:
        if not self._connected or self._dll is None:
            return DRV_NOT_INITIALIZED
        return self._dll.StartAcquisition()

    def abort_acquisition(self) -> int:
        if not self._connected or self._dll is None:
            return DRV_NOT_INITIALIZED
        return self._dll.AbortAcquisition()

    def get_most_recent_image(self, width: int = 1002, height: int = 1002) -> np.ndarray:
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


# ── Instancia Singleton y Fábrica ─────────────────────────────────────────────
_andor_instance = None

def get_andor_ccd(force_mock: bool = False) -> _MockAndorCCD | AndorCCDDriver:
    global _andor_instance
    if force_mock or SAFE_MODE:
        return _MockAndorCCD()
    if _andor_instance is None:
        drv = AndorCCDDriver()
        if drv.initialize():
            _andor_instance = drv
        else:
            print("[Andor CCD] Hardware no detectado. Recurriendo a _MockAndorCCD.")
            _andor_instance = _MockAndorCCD()
    return _andor_instance
