# -*- coding: utf-8 -*-
"""
andor_ccd_driver.py — Controlador Ctypes y Mock Resiliente para Cámara Andor CCD / EMCCD
PySpectrum 3.0 — UNSAM Nanofotónica
"""
from __future__ import annotations
import os
import sys
import time
from ctypes import POINTER, c_char_p, c_int, c_long, c_uint, c_ulong, c_float, byref, create_string_buffer, windll
from pathlib import Path
import threading
from typing import Tuple, Optional
import numpy as np

from config import SAFE_MODE
from pyspectrum.drivers.specular_interlock import get_interlock

# Códigos de retorno Andor SDK 2
DRV_SUCCESS = 20002
DRV_NOT_INITIALIZED = 20075
DRV_ACQUIRING = 20072
DRV_IDLE = 20073
DRV_TEMP_STABILIZED = 20036
DRV_TEMP_NOT_REACHED = 20037
DRV_TEMP_DRIFT = 20040
DRV_TEMP_NOT_STABILIZED = 20035
# Códigos del paso 6 (DEC-040). Se toman de la tabla del legado (`scratch/pyspectrum-legacy/ccd_ps.py`),
# que funcionó en el banco y coincide con las constantes de arriba. La tabla de la sección 12 del SDK
# v2.104 extraída del PDF está desalineada una fila (pone DRV_ACQUIRING = 20073 y DRV_IDLE = 20075).
DRV_NO_NEW_DATA = 20024      # sin datos nuevos todavía ("No acquisition has taken place")
DRV_P1INVALID = 20066
DRV_P2INVALID = 20067        # en GetAcquiredData: tamaño de arreglo incorrecto
ACQ_MODE_SINGLE_SCAN = 1     # SetAcquisitionMode (SDK p. 305)

# Modos de adquisición
ACQ_MODE_SINGLE = 1
ACQ_MODE_ACCUMULATE = 2
ACQ_MODE_KINETICS = 3
ACQ_MODE_FAST_KINETICS = 4
ACQ_MODE_RUN_TILL_ABORT = 5

# Modos de lectura
# Códigos de SetReadMode según el SDK2 de Andor v2.104 (docs/bibliografia/Software Development
# Kit.pdf, p. 305). Antes Single-Track valía 1, que en el SDK es Multi-Track (C-05, DEC-040).
READ_MODE_FVB = 0           # Full Vertical Binning (espectro 1D)
READ_MODE_MULTI_TRACK = 1
READ_MODE_RANDOM_TRACK = 2
READ_MODE_SINGLE_TRACK = 3
READ_MODE_IMAGE = 4         # Imagen 2D

# Modos de obturador interno de cámara (SetShutter typ=1, mode=...)
SHUTTER_MODE_AUTO = 0
SHUTTER_MODE_OPEN = 1
SHUTTER_MODE_CLOSED = 2

# ── Geometría física del detector ────────────────────────────────────────────
# Fuente canónica ÚNICA de la geometría del sensor. Antes estos números estaban
# transcriptos en cinco lugares que no concordaban entre sí (ver DEC-031); ahora todo
# consumidor los importa de acá, de modo que corregirlos sea una edición en un solo punto.
DETECTOR_WIDTH_PX = 1004
ADC_MAX_COUNTS = 16383          # iXon3 885: ADC de 14 bit ([DS-iXon] p. 2; C-25)
DETECTOR_HEIGHT_PX = 1002

# Pitch físico del píxel, en µm/px. Convierte anchos de ranura (µm) a píxeles del eje
# espectral (`exploration_tab._update_slit_overlay`) y se le informa al SDK del Shamrock para
# que calcule λ(píxel) (`shamrock_driver.configure_detector_geometry`).
#
# Verificado (DEC-033): el cabezal es un iXon3 885 — `DU8285_VP` según el encabezado de los
# .sif que Solis escribe leyendo la cámara — con sensor TI TC285SPD. Ambas hojas de datos dan
# 8 x 8 µm, y el legado calibró λ con `PixelWidth = 8` desde 2020. El 13.0 que hubo acá no
# tenía fuente y planificaba el Step & Glue con ventanas un 70 % más anchas que las reales.
DETECTOR_PIXEL_PITCH_UM = 8.0

# Ganancias de pre-amplificador y velocidades de lectura horizontal simuladas en Modo Seguro
PREAMP_GAINS_MOCK = [1.0, 2.0, 4.3]
# Velocidades del iXon3 885 por el amplificador EMCCD: 35, 27 y 13 MHz ([DS-iXon] p. 2). El orden
# real de la tabla del SDK lo confirma BANCO-38; el arranque elige la velocidad por valor, no por índice.
HSSPEEDS_MHZ_MOCK = [35.0, 27.0, 13.0]
# Desplazamiento vertical de 0.5 a 1.9 µs ([DS-iXon] p. 2). El legado usaba el índice 2 = 1.9 µs
# (Camera_ps.py:607); la tabla intermedia es ilustrativa hasta BANCO-38.
VSSPEEDS_US_MOCK = [0.5, 1.0, 1.9]
FAN_MODE_FULL, FAN_MODE_LOW, FAN_MODE_OFF = 0, 1, 2   # SetFanMode (SDK p. 273)


# Prototipos del SDK2 v2.104 (docs/bibliografia/Software Development Kit.pdf) para cada función que
# el driver llama. Con `argtypes` declarados, un argumento de otro tipo o una cantidad distinta da un
# error de Python en vez de que la DLL lea o escriba memoria arbitraria (R4-E, DEC-040). `at_32*` es
# un entero de 32 bits: `c_long` en Windows. tests/test_andor_argtypes.py verifica la tabla.
_ANDOR_ARGTYPES = {
    "AbortAcquisition": (),
    "CoolerOFF": (),
    "CoolerON": (),
    "GetAcquiredData": (POINTER(c_long), c_ulong),
    "GetAcquisitionTimings": (POINTER(c_float), POINTER(c_float), POINTER(c_float)),
    "GetEMCCDGain": (POINTER(c_int),),
    "GetCurrentPreAmpGain": (POINTER(c_int), c_char_p, c_int),
    "GetDetector": (POINTER(c_int), POINTER(c_int)),
    "GetEMGainRange": (POINTER(c_int), POINTER(c_int)),
    "GetNumberVSSpeeds": (POINTER(c_int),),
    "GetTemperatureRange": (POINTER(c_int), POINTER(c_int)),
    "GetVSSpeed": (c_int, POINTER(c_float)),
    "IsCoolerOn": (POINTER(c_int),),
    "SetEMGainMode": (c_int,),
    "SetFanMode": (c_int,),
    "SetVSSpeed": (c_int,),
    "GetHSSpeed": (c_int, c_int, c_int, POINTER(c_float)),
    "GetMostRecentImage": (POINTER(c_long), c_ulong),
    "GetNumberHSSpeeds": (c_int, c_int, POINTER(c_int)),
    "GetNumberPreAmpGains": (POINTER(c_int),),
    "GetPreAmpGain": (c_int, POINTER(c_float)),
    "GetStatus": (POINTER(c_int),),
    "GetTemperature": (POINTER(c_int),),
    "GetTotalNumberImagesAcquired": (POINTER(c_long),),
    "Initialize": (c_char_p,),
    "SetAcquisitionMode": (c_int,),
    "SetCoolerMode": (c_int,),
    "SetEMCCDGain": (c_int,),
    "SetExposureTime": (c_float,),
    "SetHSSpeed": (c_int, c_int),
    "SetImage": (c_int, c_int, c_int, c_int, c_int, c_int),
    "SetMultiTrack": (c_int, c_int, c_int, POINTER(c_int), POINTER(c_int)),
    "SetOutputAmplifier": (c_int,),
    "SetPreAmpGain": (c_int,),
    "SetRandomTracks": (c_int, POINTER(c_int)),
    "SetReadMode": (c_int,),
    "SetShutter": (c_int, c_int, c_int, c_int),
    "SetSingleTrack": (c_int, c_int),
    "SetTemperature": (c_int,),
    "ShutDown": (),
    "StartAcquisition": (),
    "WaitForAcquisitionTimeOut": (c_int,),
}


def _declare_argtypes(dll) -> None:
    for name, argtypes in _ANDOR_ARGTYPES.items():
        try:
            fn = getattr(dll, name)
            fn.argtypes = list(argtypes)
            fn.restype = c_uint
        except AttributeError:
            print(f"[Andor CCD] La DLL no exporta {name}.")


def _specular_gain_allowed(gain: int) -> bool:
    """Red mínima del paso 7 (R2-inst §2.5-1): ganancia EM > 0 sólo en primer orden confirmado."""
    lock = get_interlock()
    if lock.gain_allowed(gain):
        return True
    print(f"[Andor CCD Safety] Ganancia EM {gain} rechazada: condición especular o estado del Shamrock "
          f"desconocido ({lock.mode}: {lock.detail}). La ganancia queda en 0.")
    return False


class DeviceUnavailable(RuntimeError):
    """La cámara no está conectada: ninguna lectura puede devolver datos (DEC-040, DEC-036).

    Antes, un driver sin inicializar devolvía un cuadro de ceros y la fábrica caía al simulador
    en silencio; los dos casos producen datos con aspecto válido que no vienen del equipo."""


class _MockAndorCCD:
    """Simulador transparente de Cámara Andor iXon3 EMCCD DU8285 (1004x1002 px)."""
    is_mock = True
    available = True
    unavailable_reason = ""

    def __init__(self, temperature: float = -65.0, fan_mode: str = "low"):
        self._lock = threading.RLock()
        self.width = DETECTOR_WIDTH_PX
        self.height = DETECTOR_HEIGHT_PX
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
        self._preamp_gain_idx = 0
        self._hsspeed_idx = 0
        self._shutter_mode = SHUTTER_MODE_AUTO
        self._multi_track_params: Tuple[int, int, int] = (1, 5, 0)  # (number, height, offset)
        self._random_track_areas: list = []
        self._image_vstart: int = 1
        self._image_vend: int = 1002
        # Paso 6 (DEC-040): estado de una adquisición de un solo cuadro. `_acq_mode` arranca en
        # "run till abort" (5) para no cambiar lo que ya usan el Live y las rutinas viejas; sólo en
        # modo 1 (single scan) la adquisición termina sola al cumplirse la exposición, como el SDK.
        self._acq_mode = 5
        self._vsspeed_idx = 0
        self._em_gain_mode = 0
        self._fan_code = FAN_MODE_LOW if fan_mode == "low" else FAN_MODE_FULL
        self._acq_started_at = 0.0
        self._images_acquired = 0
        self._last_read_index = 0
        self._event_pending = False
        print("[Andor CCD SIM] Cámara Andor virtual inicializada (1004x1002, iXon3 EMCCD DU8285).")

    def is_hardware_alive(self) -> bool:
        return False

    def get_status(self) -> int:
        return DRV_ACQUIRING if self._acquiring else DRV_IDLE

    def get_number_preamp_gains(self) -> int:
        return len(PREAMP_GAINS_MOCK)

    def get_preamp_gain(self, index: int) -> Tuple[int, float]:
        idx = max(0, min(len(PREAMP_GAINS_MOCK) - 1, int(index)))
        return (DRV_SUCCESS, PREAMP_GAINS_MOCK[idx])

    def set_preamp_gain(self, index: int) -> int:
        with self._lock:
            self._preamp_gain_idx = max(0, min(len(PREAMP_GAINS_MOCK) - 1, int(index)))
            return DRV_SUCCESS

    def get_preamp_gain_index(self) -> int:
        return self._preamp_gain_idx

    def get_number_hs_speeds(self, channel: int = 0, typ: int = 0) -> int:
        return len(HSSPEEDS_MHZ_MOCK)

    def get_hs_speed(self, index: int, channel: int = 0, typ: int = 0) -> Tuple[int, float]:
        idx = max(0, min(len(HSSPEEDS_MHZ_MOCK) - 1, int(index)))
        return (DRV_SUCCESS, HSSPEEDS_MHZ_MOCK[idx])

    def set_hs_speed(self, index: int, typ: int = 0) -> int:
        with self._lock:
            self._hsspeed_idx = max(0, min(len(HSSPEEDS_MHZ_MOCK) - 1, int(index)))
            return DRV_SUCCESS

    def get_hs_speed_index(self) -> int:
        return self._hsspeed_idx

    # ── Primitivas del estado operativo base (paso 8, DEC-040) ───────────────
    def get_detector(self) -> Tuple[int, int, int]:
        return (DRV_SUCCESS, self.width, self.height)

    def get_number_vs_speeds(self) -> Tuple[int, int]:
        return (DRV_SUCCESS, len(VSSPEEDS_US_MOCK))

    def get_vs_speed(self, index: int) -> Tuple[int, float]:
        if not 0 <= int(index) < len(VSSPEEDS_US_MOCK):
            return (DRV_P1INVALID, float("nan"))
        return (DRV_SUCCESS, VSSPEEDS_US_MOCK[int(index)])

    def set_vs_speed(self, index: int) -> int:
        if not 0 <= int(index) < len(VSSPEEDS_US_MOCK):
            return DRV_P1INVALID
        self._vsspeed_idx = int(index)
        return DRV_SUCCESS

    def set_fan_mode(self, mode: int) -> int:
        self._fan_code = int(mode)
        self._fan_mode = {FAN_MODE_FULL: "full", FAN_MODE_LOW: "low", FAN_MODE_OFF: "off"}.get(int(mode), "?")
        return DRV_SUCCESS

    def get_temperature_range(self) -> Tuple[int, int, int]:
        return (DRV_SUCCESS, -100, 25)

    def is_cooler_on(self) -> Tuple[int, bool]:
        return (DRV_SUCCESS, bool(self._cooler_on))

    def set_em_gain_mode(self, mode: int) -> int:
        self._em_gain_mode = int(mode)
        return DRV_SUCCESS

    def get_em_gain_range(self) -> Tuple[int, int, int]:
        return (DRV_SUCCESS, 0, 255) if self._em_gain_mode == 0 else (DRV_SUCCESS, 2, 1000)

    def get_current_preamp_gain(self) -> Tuple[int, int]:
        return (DRV_SUCCESS, int(self._preamp_gain_idx))

    def set_shutter_mode(self, mode: int, closing_time_ms: int = 0, opening_time_ms: int = 0) -> int:
        """0: Auto (sincronizado con adquisición), 1: Siempre Abierto, 2: Siempre Cerrado."""
        with self._lock:
            self._shutter_mode = int(mode)
            return DRV_SUCCESS

    def get_shutter_mode(self) -> int:
        return self._shutter_mode

    def set_multi_track(self, number: int, height: int, offset: int) -> Tuple[int, int, int]:
        with self._lock:
            number = max(1, int(number))
            height = max(1, int(height))
            self._multi_track_params = (number, height, int(offset))
            return (DRV_SUCCESS, int(offset), 0)

    def get_multi_track(self) -> Tuple[int, int, int]:
        return self._multi_track_params

    def set_random_track(self, areas: list) -> int:
        with self._lock:
            self._random_track_areas = list(areas)
            return DRV_SUCCESS

    def get_random_track_areas(self) -> list:
        return list(self._random_track_areas)

    def get_tracks_2d_spectrum(self) -> np.ndarray:
        """Genera un cuadro (NumTracks, Width) sintético para modos Multi-Track / Random-Track."""
        if self._read_mode == READ_MODE_MULTI_TRACK:
            n_tracks = self._multi_track_params[0]
        else:
            n_tracks = max(1, len(self._random_track_areas))
        rows = [self.get_1d_spectrum() for _ in range(max(1, n_tracks))]
        return np.stack(rows, axis=0).astype(np.float32)

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

    def reconnect(self) -> bool:
        with self._lock:
            self._acquiring = False
            return True

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

    def get_exposure_time_checked(self) -> Tuple[int, Optional[float]]:
        with self._lock:
            return (DRV_SUCCESS, float(self._exposure_time))

    def set_emccd_gain(self, gain: int) -> int:
        with self._lock:
            g = max(0, min(1000, int(gain)))
            if not _specular_gain_allowed(g):
                return DRV_P1INVALID
            # Salvaguarda EMCCD: si tiempo de exposición > 1.0 s, impedir superar 5x
            if self._exposure_time > 1.0 and g > 5:
                print(f"[Andor CCD Safety] Ganancia EM clampeada a 5x: exposición actual ({self._exposure_time:.2f}s) > 1.0s.")
                g = 5
            self._emccd_gain = g
            get_interlock().note_gain_set(DRV_SUCCESS, g)
            return DRV_SUCCESS

    def get_emccd_gain(self) -> int:
        with self._lock:
            get_interlock().note_gain_reading(DRV_SUCCESS, self._emccd_gain)
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
        self._image_vstart = int(vstart)
        self._image_vend = int(vend)
        return DRV_SUCCESS

    def start_acquisition(self) -> int:
        self._acquiring = True
        self._acq_started_at = time.monotonic()
        self._event_pending = False
        return DRV_SUCCESS

    def abort_acquisition(self) -> int:
        self._acquiring = False
        return DRV_SUCCESS

    # ── Primitivas del paso 6 (single scan) ──────────────────────────────────
    def _advance(self) -> None:
        if (self._acquiring and self._acq_mode == ACQ_MODE_SINGLE_SCAN
                and time.monotonic() - self._acq_started_at >= self._exposure_time):
            self._acquiring = False
            self._images_acquired += 1
            self._event_pending = True

    def set_acquisition_mode(self, mode: int) -> int:
        with self._lock:
            if self._acquiring:
                return DRV_ACQUIRING
            self._acq_mode = int(mode)
            return DRV_SUCCESS

    def get_status_checked(self) -> Tuple[int, int]:
        self._advance()
        return (DRV_SUCCESS, DRV_ACQUIRING if self._acquiring else DRV_IDLE)

    def wait_for_acquisition_timeout(self, timeout_ms: int) -> int:
        self._advance()
        if self._event_pending:
            self._event_pending = False
            return DRV_SUCCESS
        if not self._acquiring:
            return DRV_NO_NEW_DATA
        remaining = self._acq_started_at + self._exposure_time - time.monotonic()
        time.sleep(max(0.0, min(timeout_ms / 1000.0, remaining)))
        self._advance()
        if self._event_pending:
            self._event_pending = False
            return DRV_SUCCESS
        return DRV_NO_NEW_DATA

    def get_acquisition_timings(self) -> Tuple[int, float, float, float]:
        e = float(self._exposure_time)
        return (DRV_SUCCESS, e, e, e)

    def get_total_number_images_acquired(self) -> Tuple[int, int]:
        self._advance()
        return (DRV_SUCCESS, int(self._images_acquired))

    def get_acquired_data_checked(self, n_pixels: int) -> Tuple[int, Optional[np.ndarray]]:
        self._advance()
        if self._acquiring:
            return (DRV_ACQUIRING, None)
        if self._images_acquired == self._last_read_index:
            return (DRV_NO_NEW_DATA, None)
        data = np.asarray(self.get_acquired_data(), dtype=np.float64).ravel()
        if data.size != int(n_pixels):
            return (DRV_P2INVALID, None)
        self._last_read_index = self._images_acquired
        return (DRV_SUCCESS, data)

    def _light_factor(self) -> float:
        """0 con el obturador cerrado (modo 2): la cámara acciona el obturador del Shamrock por TTL."""
        return 0.0 if int(getattr(self, "_shutter_mode", 0)) == 2 else 1.0

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

        # Con el obturador cerrado (TTL de la cámara al Shamrock, BANCO-22) sólo llega oscuridad
        signal = slit_profile * (spr_peak + laser_peak + 150.0) * self._light_factor()

        frame = (dark_counts + signal).astype(np.float32)
        # En modo EMCCD (0), aplicar ganancia de multiplicación de electrones
        if self._output_amplifier == 0 and self._emccd_gain > 0:
            frame *= (1.0 + self._emccd_gain * 0.02)

        if self._read_mode == READ_MODE_IMAGE and (self._image_vstart > 1 or self._image_vend < self.height):
            v0 = max(0, self._image_vstart - 1)
            v1 = min(self.height, self._image_vend)
            frame = frame[v0:v1, :]

        return frame

    def get_1d_spectrum(self) -> np.ndarray:
        """Devuelve el espectro 1D binnizado en hardware (FVB o Single Track) con ruido de lectura cobrado una sola vez."""
        x = np.linspace(-5, 5, self.width)
        spr_peak = 1200.0 * np.exp(-0.5 * ((x - 0.5) / 1.2)**2)
        laser_peak = 4500.0 * np.exp(-0.5 * ((x + 1.8) / 0.08)**2)
        signal_base = (spr_peak + laser_peak + 150.0) * self._light_factor()

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
        if self._read_mode in (READ_MODE_MULTI_TRACK, READ_MODE_RANDOM_TRACK):
            return self.get_tracks_2d_spectrum()
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
        self.unavailable_reason = ""
        self._init_dll()

    @property
    def available(self) -> bool:
        """True sólo si `Initialize` respondió éxito y la sesión sigue abierta."""
        return self._connected and self._dll is not None

    def _require_connected(self) -> None:
        if not self.available:
            raise DeviceUnavailable(self.unavailable_reason or "La cámara Andor no está conectada.")

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
            self.unavailable_reason = f"No se encontró atmcd64d.dll en {dll_path}."
            print(f"[Andor CCD] {self.unavailable_reason} La cámara queda NO CONECTADA.")
            return

        try:
            os.environ["PATH"] = str(dll_path.parent) + os.pathsep + os.environ.get("PATH", "")
            self._dll = windll.LoadLibrary(str(dll_path))
            _declare_argtypes(self._dll)
            print(f"[Andor CCD] DLL cargada exitosamente: {dll_path}")
        except Exception as e:
            self.unavailable_reason = f"No se pudo cargar atmcd64d.dll ({e})."
            print(f"[Andor CCD] {self.unavailable_reason}")
            self._dll = None

    def initialize(self, dir_path: str = "") -> bool:
        if self._dll is None:
            if not self.unavailable_reason:
                self.unavailable_reason = "No se encontró atmcd64d.dll (atmcd64d.dll no cargada)."
            return False
        with self._lock:
            try:
                ret = self._dll.Initialize(dir_path.encode("ascii") if dir_path else b"")
                if ret == DRV_SUCCESS:
                    self._connected = True
                    self.unavailable_reason = ""
                    try:
                        self._dll.SetCoolerMode(c_int(0))  # 0: vuelve a ambiente al apagar (seguro)
                    except Exception:
                        pass
                    return True
                self.unavailable_reason = (
                    f"La cámara no respondió a Initialize (código {ret}). ¿Solis o el PySpectrum "
                    f"legado están abiertos? Sólo un programa puede usar la cámara a la vez.")
                print(f"[Andor CCD] {self.unavailable_reason}")
                return False
            except Exception as e:
                self.unavailable_reason = f"Excepción al inicializar la cámara: {e}"
                print(f"[Andor CCD] {self.unavailable_reason}")
                return False

    def close(self):
        with self._lock:
            if self._dll is not None and self._connected:
                try:
                    self._dll.ShutDown()
                except Exception:
                    pass
                self.unavailable_reason = "Cámara cerrada por el programa (ShutDown); el enfriador se apagó."
            self._connected = False

    def reconnect(self) -> bool:
        """Cierra y vuelve a inicializar ESTA instancia (paso 4, DEC-040): todos los que la guardan
        siguen apuntando al driver vivo. ShutDown apaga el enfriador: quien lo pida avisa antes."""
        with self._lock:
            if self.available:
                try:
                    self._dll.AbortAcquisition()
                except Exception:
                    pass
            self.close()
            if self._dll is None:
                self._init_dll()
            return self.initialize()

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
            except Exception as e:
                # Antes devolvía DRV_SUCCESS: una falla de la DLL pasaba por éxito (DEC-040, paso 8).
                print(f"[Andor CCD] Error SetCoolerMode: {e}")
                return DRV_NOT_INITIALIZED

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
            if not _specular_gain_allowed(g):
                return DRV_P1INVALID
            # Salvaguarda EMCCD: si tiempo de exposición > 1.0 s, impedir superar 5x
            if self._current_exposure_time > 1.0 and g > 5:
                print(f"[Andor CCD Safety] Ganancia EM clampeada a 5x: exposición actual ({self._current_exposure_time:.2f}s) > 1.0s.")
                g = 5
            try:
                ret = self._dll.SetEMCCDGain(c_int(g))
            except Exception as e:
                print(f"[Andor CCD] Error SetEMCCDGain: {e}")
                return DRV_NOT_INITIALIZED
            get_interlock().note_gain_set(ret, g)
            return ret

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
        self._require_connected()
        try:
            n_pixels = width * height
            arr = (c_long * n_pixels)()
            ret = self._dll.GetMostRecentImage(arr, c_ulong(n_pixels))
            if ret == DRV_SUCCESS:
                img = np.array(arr[:], dtype=np.float32).reshape((height, width))
                return img
            return np.zeros((height, width), dtype=np.float32)
        except Exception:
            return np.zeros((height, width), dtype=np.float32)

    def set_read_mode(self, mode: int) -> int:
        """Códigos del SDK (p. 305): 0 FVB, 1 Multi-Track, 2 Random-Track, 3 Single-Track, 4 Image."""
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
        self._require_connected()
        try:
            arr = (c_long * width)()
            ret = self._dll.GetMostRecentImage(arr, c_ulong(width))
            if ret == DRV_SUCCESS:
                return np.array(arr[:], dtype=np.float32)
            # Respaldo con GetAcquiredData
            ret2 = self._dll.GetAcquiredData(arr, c_ulong(width))
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

    # ── Primitivas del estado operativo base (paso 8, DEC-040): código crudo del SDK ──
    def get_detector(self) -> Tuple[int, int, int]:
        """GetDetector(int* x, int* y)."""
        if not self.available:
            return (DRV_NOT_INITIALIZED, -1, -1)
        with self._lock:
            x, y = c_int(), c_int()
            ret = self._dll.GetDetector(byref(x), byref(y))
            return (ret, int(x.value), int(y.value))

    def get_number_vs_speeds(self) -> Tuple[int, int]:
        if not self.available:
            return (DRV_NOT_INITIALIZED, 0)
        with self._lock:
            n = c_int()
            ret = self._dll.GetNumberVSSpeeds(byref(n))
            return (ret, int(n.value))

    def get_vs_speed(self, index: int) -> Tuple[int, float]:
        """GetVSSpeed(int index, float* speed): µs por fila del índice pedido (no el vigente)."""
        if not self.available:
            return (DRV_NOT_INITIALIZED, float("nan"))
        with self._lock:
            s = c_float()
            ret = self._dll.GetVSSpeed(c_int(int(index)), byref(s))
            return (ret, float(s.value) if ret == DRV_SUCCESS else float("nan"))

    def set_vs_speed(self, index: int) -> int:
        if not self.available:
            return DRV_NOT_INITIALIZED
        with self._lock:
            return self._dll.SetVSSpeed(c_int(int(index)))

    def set_fan_mode(self, mode: int) -> int:
        """SetFanMode: 0 máximo, 1 bajo, 2 apagado (SDK p. 273). El SDK no tiene getter."""
        if not self.available:
            return DRV_NOT_INITIALIZED
        with self._lock:
            return self._dll.SetFanMode(c_int(int(mode)))

    def get_temperature_range(self) -> Tuple[int, int, int]:
        if not self.available:
            return (DRV_NOT_INITIALIZED, 0, 0)
        with self._lock:
            lo, hi = c_int(), c_int()
            ret = self._dll.GetTemperatureRange(byref(lo), byref(hi))
            return (ret, int(lo.value), int(hi.value))

    def is_cooler_on(self) -> Tuple[int, bool]:
        """IsCoolerOn(int*): 1 = encendido (SDK p. 211)."""
        if not self.available:
            return (DRV_NOT_INITIALIZED, False)
        with self._lock:
            s = c_int()
            ret = self._dll.IsCoolerOn(byref(s))
            return (ret, bool(s.value))

    def set_em_gain_mode(self, mode: int) -> int:
        """SetEMGainMode: 0 = DAC 0-255 (SDK p. 271). El SDK v2.104 no documenta un getter."""
        if not self.available:
            return DRV_NOT_INITIALIZED
        with self._lock:
            return self._dll.SetEMGainMode(c_int(int(mode)))

    def get_em_gain_range(self) -> Tuple[int, int, int]:
        """GetEMGainRange(int* low, int* high): depende del modo de ganancia vigente."""
        if not self.available:
            return (DRV_NOT_INITIALIZED, 0, 0)
        with self._lock:
            lo, hi = c_int(), c_int()
            ret = self._dll.GetEMGainRange(byref(lo), byref(hi))
            return (ret, int(lo.value), int(hi.value))

    def get_current_preamp_gain(self) -> Tuple[int, int]:
        """GetCurrentPreAmpGain(int* index, char* name, int len)."""
        if not self.available:
            return (DRV_NOT_INITIALIZED, -1)
        with self._lock:
            idx = c_int()
            name = create_string_buffer(64)
            ret = self._dll.GetCurrentPreAmpGain(byref(idx), name, c_int(64))
            return (ret, int(idx.value))

    # ── Primitivas del paso 6 (DEC-040): cada una devuelve el código crudo del SDK ──
    def set_acquisition_mode(self, mode: int) -> int:
        """SetAcquisitionMode(int) — 1 = single scan (SDK p. 305)."""
        if not self.available:
            return DRV_NOT_INITIALIZED
        with self._lock:
            return self._dll.SetAcquisitionMode(c_int(int(mode)))

    def get_status_checked(self) -> Tuple[int, int]:
        """GetStatus(int*) con el código crudo. `get_status()` traduce una falla en DRV_IDLE, que
        haría creer que la cámara terminó; la adquisición de un cuadro usa esta versión."""
        if not self.available:
            return (DRV_NOT_INITIALIZED, DRV_NOT_INITIALIZED)
        with self._lock:
            c_status = c_int()
            ret = self._dll.GetStatus(byref(c_status))
            return (ret, c_status.value)

    def wait_for_acquisition_timeout(self, timeout_ms: int) -> int:
        """WaitForAcquisitionTimeOut(int ms). **No toma el lock del driver**: si lo retuviera, el
        sondeo de temperatura y el AbortAcquisition de Stop desde otro hilo quedarían bloqueados
        hasta el fin del tramo (Ronda 2, instrumentation §5.2)."""
        if not self.available:
            return DRV_NOT_INITIALIZED
        return self._dll.WaitForAcquisitionTimeOut(c_int(int(timeout_ms)))

    def get_acquisition_timings(self) -> Tuple[int, float, float, float]:
        """GetAcquisitionTimings(float* exposure, float* accumulate, float* kinetic)."""
        if not self.available:
            return (DRV_NOT_INITIALIZED, float("nan"), float("nan"), float("nan"))
        with self._lock:
            e, a, k = c_float(), c_float(), c_float()
            ret = self._dll.GetAcquisitionTimings(byref(e), byref(a), byref(k))
            return (ret, float(e.value), float(a.value), float(k.value))

    def get_total_number_images_acquired(self) -> Tuple[int, int]:
        """GetTotalNumberImagesAcquired(long*): contador de cuadros del SDK."""
        if not self.available:
            return (DRV_NOT_INITIALIZED, -1)
        with self._lock:
            n = c_long()
            ret = self._dll.GetTotalNumberImagesAcquired(byref(n))
            return (ret, int(n.value))

    def get_acquired_data_checked(self, n_pixels: int) -> Tuple[int, Optional[np.ndarray]]:
        """GetAcquiredData(at_32*, unsigned long) con el tamaño exacto. Sólo DRV_SUCCESS devuelve
        datos: cualquier otro código devuelve None, nunca un arreglo de ceros."""
        if not self.available:
            return (DRV_NOT_INITIALIZED, None)
        with self._lock:
            n = int(n_pixels)
            arr = (c_long * n)()
            ret = self._dll.GetAcquiredData(arr, c_ulong(n))
            if ret != DRV_SUCCESS:
                return (ret, None)
            return (ret, np.array(arr[:], dtype=np.float64))

    def get_status(self) -> int:
        """Consulta el estado de adquisición (DRV_IDLE / DRV_ACQUIRING) del driver."""
        if not self._connected or self._dll is None:
            return DRV_NOT_INITIALIZED
        try:
            c_status = c_int()
            ret = self._dll.GetStatus(byref(c_status))
            return c_status.value if ret == DRV_SUCCESS else DRV_IDLE
        except Exception:
            return DRV_IDLE

    def get_number_preamp_gains(self) -> int:
        if not self._connected or self._dll is None:
            return 0
        try:
            c_n = c_int()
            ret = self._dll.GetNumberPreAmpGains(byref(c_n))
            return c_n.value if ret == DRV_SUCCESS else 0
        except Exception as e:
            print(f"[Andor CCD] Error GetNumberPreAmpGains: {e}")
            return 0

    def get_preamp_gain(self, index: int) -> Tuple[int, float]:
        if not self._connected or self._dll is None:
            return (DRV_NOT_INITIALIZED, 1.0)
        try:
            c_gain = c_float()
            ret = self._dll.GetPreAmpGain(c_int(int(index)), byref(c_gain))
            return (ret, float(c_gain.value))
        except Exception as e:
            print(f"[Andor CCD] Error GetPreAmpGain: {e}")
            return (DRV_NOT_INITIALIZED, 1.0)

    def set_preamp_gain(self, index: int) -> int:
        if not self._connected or self._dll is None:
            return DRV_NOT_INITIALIZED
        try:
            return self._dll.SetPreAmpGain(c_int(int(index)))
        except Exception as e:
            print(f"[Andor CCD] Error SetPreAmpGain: {e}")
            return DRV_NOT_INITIALIZED

    def get_number_hs_speeds(self, channel: int = 0, typ: int = 0) -> int:
        if not self._connected or self._dll is None:
            return 0
        try:
            c_n = c_int()
            ret = self._dll.GetNumberHSSpeeds(c_int(channel), c_int(typ), byref(c_n))
            return c_n.value if ret == DRV_SUCCESS else 0
        except Exception as e:
            print(f"[Andor CCD] Error GetNumberHSSpeeds: {e}")
            return 0

    def get_hs_speed(self, index: int, channel: int = 0, typ: int = 0) -> Tuple[int, float]:
        if not self._connected or self._dll is None:
            return (DRV_NOT_INITIALIZED, 1.0)
        try:
            c_speed = c_float()
            ret = self._dll.GetHSSpeed(c_int(channel), c_int(typ), c_int(int(index)), byref(c_speed))
            return (ret, float(c_speed.value))
        except Exception as e:
            print(f"[Andor CCD] Error GetHSSpeed: {e}")
            return (DRV_NOT_INITIALIZED, 1.0)

    def set_hs_speed(self, index: int, typ: int = 0) -> int:
        if not self._connected or self._dll is None:
            return DRV_NOT_INITIALIZED
        try:
            return self._dll.SetHSSpeed(c_int(typ), c_int(int(index)))
        except Exception as e:
            print(f"[Andor CCD] Error SetHSSpeed: {e}")
            return DRV_NOT_INITIALIZED

    def set_shutter_mode(self, mode: int, closing_time_ms: int = 0, opening_time_ms: int = 0) -> int:
        """0: Auto, 1: Siempre Abierto, 2: Siempre Cerrado. Mapea a SetShutter(typ=1, mode, ...)
        del SDK 2 (typ=1: TTL alto abre el obturador interno de la cámara)."""
        if not self._connected or self._dll is None:
            return DRV_NOT_INITIALIZED
        try:
            return self._dll.SetShutter(c_int(1), c_int(int(mode)), c_int(int(closing_time_ms)), c_int(int(opening_time_ms)))
        except Exception as e:
            print(f"[Andor CCD] Error SetShutter: {e}")
            return DRV_NOT_INITIALIZED

    def set_multi_track(self, number: int, height: int, offset: int) -> Tuple[int, int, int]:
        if not self._connected or self._dll is None:
            return (DRV_NOT_INITIALIZED, 0, 0)
        try:
            c_bottom = c_int()
            c_gap = c_int()
            ret = self._dll.SetMultiTrack(c_int(int(number)), c_int(int(height)), c_int(int(offset)), byref(c_bottom), byref(c_gap))
            return (ret, c_bottom.value, c_gap.value)
        except Exception as e:
            print(f"[Andor CCD] Error SetMultiTrack: {e}")
            return (DRV_NOT_INITIALIZED, 0, 0)

    def set_random_track(self, areas: list) -> int:
        """areas: lista de tuplas (y_start, y_end) por pista, en orden ascendente de fila."""
        if not self._connected or self._dll is None:
            return DRV_NOT_INITIALIZED
        try:
            flat = []
            for (y0, y1) in areas:
                flat.extend([int(y0), int(y1)])
            arr = (c_int * len(flat))(*flat)
            # SetRandomTracks (plural): es el nombre que exporta la DLL (SDK p. 311); SetRandomTrack no existe.
            return self._dll.SetRandomTracks(c_int(len(areas)), arr)
        except Exception as e:
            print(f"[Andor CCD] Error SetRandomTrack: {e}")
            return DRV_NOT_INITIALIZED

    def get_tracks_2d_spectrum(self, n_tracks: int, width: int = 1004) -> np.ndarray:
        """Lee datos adquiridos con forma (NumTracks, Width) para Multi-Track / Random-Track."""
        n_tracks = max(1, int(n_tracks))
        self._require_connected()
        try:
            n_pixels = n_tracks * width
            arr = (c_long * n_pixels)()
            ret = self._dll.GetAcquiredData(arr, c_ulong(n_pixels))
            if ret == DRV_SUCCESS:
                return np.array(arr[:], dtype=np.float32).reshape((n_tracks, width))
            return np.zeros((n_tracks, width), dtype=np.float32)
        except Exception:
            return np.zeros((n_tracks, width), dtype=np.float32)


# ── Instancia Singleton y Fábrica ─────────────────────────────────────────────
_andor_instance = None

def _new_hardware_driver():
    """El driver de hardware según `config.ANDOR_BACKEND` (R4-F, DEC-040): por ahora pylablib, como
    el legado; "ctypes" es el driver propio, que queda para más adelante."""
    try:
        from config import ANDOR_BACKEND
    except Exception:
        ANDOR_BACKEND = "pylablib"
    if str(ANDOR_BACKEND).lower() == "ctypes":
        return AndorCCDDriver()
    from pyspectrum.drivers.andor_pylablib import PylablibAndorCCD
    return PylablibAndorCCD()


def reconnect_andor_ccd():
    """Reconexión explícita de la cámara, en el lugar (paso 4, DEC-040). Nunca crea otra instancia
    si ya hay una: `get_andor_ccd(reset=True)` la reemplazaba y dejaba a los backends con una cerrada."""
    if _andor_instance is None:
        return get_andor_ccd()
    _andor_instance.reconnect()
    return _andor_instance


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
            # Fuera de SAFE_MODE nunca se cae al simulador (DEC-040, DEC-036): si Initialize falla,
            # queda el driver real sin conectar, con `available = False` y el motivo en
            # `unavailable_reason`; sus setters devuelven DRV_NOT_INITIALIZED y sus lecturas de
            # imagen lanzan DeviceUnavailable.
            drv = _new_hardware_driver()
            if not drv.initialize():
                print(f"[Andor CCD] NO CONECTADA: {drv.unavailable_reason}")
            _andor_instance = drv
    return _andor_instance
