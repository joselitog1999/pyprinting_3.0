# -*- coding: utf-8 -*-
"""
andor_pylablib.py — La cámara Andor a través de pylablib, como en el legado (R4-F, DEC-040)

El PySpectrum legado maneja la cámara con pylablib (`AndorSDK2Camera`), y es lo que funciona en el
banco. En el banco (2026-09-28) el legado carga `C:\\Program Files\\Andor SOLIS\\atmcd64d_legacy.dll`,
el primer candidato de pylablib 1.4.3; la `atmcd64d.dll` 2.104 del repo ve 0 cámaras. Por decisión del
investigador, por ahora la cámara se maneja con pylablib y el driver ctypes propio queda para más
adelante (`ANDOR_BACKEND = "ctypes"`).

`PylablibAndorCCD` ofrece la MISMA interfaz que `AndorCCDDriver`, para no reescribir los módulos que
usan la cámara ni sus tests: los métodos devuelven los códigos del SDK (DRV_*) que esos módulos ya
esperan, traduciendo las excepciones de pylablib (`AndorSDK2LibError.code`). La adquisición de un
cuadro (`acquire_single`) sigue el camino de pylablib que usa el legado: `start_acquisition` →
`wait_for_frame` → `read_oldest_image` → `stop_acquisition`.

El Live (paquete 1 de R4-M) cumple el contrato de `live_stream`: arranca siempre en "cont", lee sólo el
cuadro más nuevo con el contador de pylablib y, con el Live activo, aplica la exposición, el
preamplificador y las velocidades HS y VS con `pausing_acquisition`. Lo que cambia la forma del cuadro
(modo de lectura, track, imagen) y el amplificador se rechazan con DRV_ACQUIRING mientras el Live corre:
pylablib pausaría solo (`@acqstopped`) y el Live seguiría con otra forma de cuadro.

Coordenadas: la interfaz de PySpectrum usa las del SDK (filas y columnas desde 1, inclusivas);
pylablib, desde 0 con fin exclusivo. La conversión se hace sólo acá.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable, Optional, Tuple

import numpy as np

from pyspectrum.drivers.andor_ccd_driver import (
    ACQ_MODE_SINGLE_SCAN, DETECTOR_HEIGHT_PX, DETECTOR_WIDTH_PX, DRV_ACQUIRING, DRV_IDLE,
    DRV_NO_NEW_DATA, DRV_NOT_INITIALIZED, DRV_P1INVALID, DRV_SUCCESS, DRV_TEMP_DRIFT,
    DRV_TEMP_NOT_REACHED, DRV_TEMP_NOT_STABILIZED, DRV_TEMP_STABILIZED, DeviceUnavailable,
    FAN_MODE_FULL, FAN_MODE_LOW, FAN_MODE_OFF, READ_MODE_FVB, READ_MODE_IMAGE, READ_MODE_MULTI_TRACK,
    READ_MODE_RANDOM_TRACK, READ_MODE_SINGLE_TRACK, _specular_gain_allowed,
)
from pyspectrum.drivers.live_stream import LiveFrame, LiveStopped
from pyspectrum.drivers.specular_interlock import get_interlock

DRV_TEMP_OFF = 20034
_ERROR_GENERIC = 20013          # DRV_ERROR_ACK: se usa cuando pylablib falla sin código del SDK
_READ_MODE_NAMES = {READ_MODE_FVB: "fvb", READ_MODE_SINGLE_TRACK: "single_track",
                    READ_MODE_MULTI_TRACK: "multi_track", READ_MODE_RANDOM_TRACK: "random_track",
                    READ_MODE_IMAGE: "image"}
_FAN_NAMES = {FAN_MODE_FULL: "full", FAN_MODE_LOW: "low", FAN_MODE_OFF: "off"}
_TEMP_CODES = {"off": DRV_TEMP_OFF, "not_reached": DRV_TEMP_NOT_REACHED,
               "not_stabilized": DRV_TEMP_NOT_STABILIZED, "drifted": DRV_TEMP_DRIFT,
               "stabilized": DRV_TEMP_STABILIZED}
# Modo del obturador y tipo de TTL como el legado (Camera_ps.py:645-663): abrir con TTL 1 (alto abre),
# cerrar con TTL 0. La salida TTL de la cámara acciona el obturador del Shamrock (BANCO-22).
_SHUTTER_NAMES = {0: ("auto", 1), 1: ("open", 1), 2: ("closed", 0)}

# Conexión (decisión del investigador, 2026-09-29): con un setpoint numérico pylablib 1.4.3 no toca el
# enfriador al conectar (sólo actúa con None, eligiendo uno automático y encendiéndolo, o con "off"), como
# el legado con temperature=10. El estado base fija −60 °C y lo relee. Ventilador en bajo (R4-A-6); el
# default de pylablib es "off".
CONNECT_KWARGS = {"idx": 0, "ini_path": "", "temperature": -60, "fan_mode": "low"}


class FrameNotReady(RuntimeError):
    """Todavía no hay ningún cuadro para mostrar (por ejemplo, al empezar el Live). No es una falla."""


def _default_camera_factory():
    """Crea la cámara de pylablib con la búsqueda de DLL de pylablib (la del legado) o la carpeta de
    `config.ANDOR_SDK2_DLL_DIR`. `fan_mode="low"` para que la conexión no apague el ventilador (el
    valor por defecto de pylablib es "off"); el enfriador y el resto los fija el estado base."""
    import pylablib as pll
    try:
        from config import ANDOR_SDK2_DLL_DIR
    except Exception:
        ANDOR_SDK2_DLL_DIR = None
    if ANDOR_SDK2_DLL_DIR:
        pll.par["devices/dlls/andor_sdk2"] = str(ANDOR_SDK2_DLL_DIR)
    from pylablib.devices.Andor import AndorSDK2Camera
    return AndorSDK2Camera(**CONNECT_KWARGS)


class PylablibAndorCCD:
    """Cámara Andor iXon3 sobre pylablib, con la interfaz de `AndorCCDDriver`."""
    is_mock = False

    def __init__(self, camera_factory: Callable[[], Any] = _default_camera_factory):
        # R4-L (2026-09-30): sólo la API de cámara de pylablib (`AndorSDK2Camera`), como el legado. Nada de
        # su capa baja: SetCoolerMode, SetEMGainMode y GetEMGainRange quedan en el valor del SDK.
        self._lock = threading.RLock()
        self._factory = camera_factory
        self._cam = None
        self.unavailable_reason = ""
        self._read_mode = READ_MODE_IMAGE
        self._track_center = 501
        self._track_height = 40
        self._current_exposure_time = 0.05
        self._last_temp_c = float("nan")
        self._live_active = False
        self._live_not_shown_total = 0

    # ── Conexión ──────────────────────────────────────────────────────────────
    @property
    def available(self) -> bool:
        return self._cam is not None

    def _require_connected(self) -> None:
        if not self.available:
            raise DeviceUnavailable(self.unavailable_reason or "La cámara Andor no está conectada.")

    def initialize(self, dir_path: str = "") -> bool:
        with self._lock:
            try:
                self._cam = self._factory()
                self.unavailable_reason = ""
                return True
            except Exception as e:
                self._cam = None
                self.unavailable_reason = (
                    f"pylablib no pudo abrir la cámara: {e}. ¿Solis o el PySpectrum legado están abiertos? "
                    f"pylablib busca la DLL en config.ANDOR_SDK2_DLL_DIR y después en "
                    f"C:\\Program Files\\Andor SOLIS (atmcd64d_legacy.dll primero).")
                print(f"[Andor CCD pylablib] {self.unavailable_reason}")
                return False

    def close(self):
        with self._lock:
            if self._cam is not None:
                try:
                    self._cam.close()
                except Exception:
                    pass
                self.unavailable_reason = "Cámara cerrada por el programa; el enfriador vuelve a ambiente."
            self._cam = None

    def reconnect(self) -> bool:
        with self._lock:
            self.close()
            return self.initialize()

    def is_hardware_alive(self) -> bool:
        if not self.available:
            return False
        try:
            return bool(self._cam.is_opened())
        except Exception:
            return False

    # ── Traducción de errores ─────────────────────────────────────────────────
    def _call(self, fn: Callable, *args, **kwargs) -> int:
        """Ejecuta una operación de pylablib y devuelve un código del SDK."""
        if not self.available:
            return DRV_NOT_INITIALIZED
        with self._lock:
            try:
                fn(*args, **kwargs)
                return DRV_SUCCESS
            except Exception as e:
                code = getattr(e, "code", None)
                print(f"[Andor CCD pylablib] {getattr(fn, '__name__', fn)} falló: {e}")
                return int(code) if isinstance(code, int) else _ERROR_GENERIC

    def _get(self, fn: Callable, default, *args, **kwargs) -> Tuple[int, Any]:
        if not self.available:
            return (DRV_NOT_INITIALIZED, default)
        with self._lock:
            try:
                return (DRV_SUCCESS, fn(*args, **kwargs))
            except Exception as e:
                code = getattr(e, "code", None)
                return (int(code) if isinstance(code, int) else _ERROR_GENERIC, default)

    # ── Temperatura, enfriador y ventilador ───────────────────────────────────
    def set_temperature(self, temp: float) -> int:
        return self._call(lambda: self._cam.set_temperature(int(temp), enable_cooler=True))

    def get_temperature(self) -> Tuple[int, float]:
        """Mientras la cámara adquiere, el SDK no lee la temperatura (banco 2026-09-28: 20072
        con el Live encendido). Entonces se devuelve la última lectura con DRV_ACQUIRING, para que la
        GUI la muestre como vieja; NaN si todavía no hubo ninguna."""
        if not self.available:
            return (DRV_NOT_INITIALIZED, float("nan"))
        ret, t = self._get(self._cam.get_temperature, float("nan"))
        if ret == DRV_ACQUIRING:
            return (DRV_ACQUIRING, self._last_temp_c)
        if ret != DRV_SUCCESS:
            return (ret, t)
        self._last_temp_c = float(t)
        ret_s, status = self._get(self._cam.get_temperature_status, None)
        return (_TEMP_CODES.get(status, DRV_TEMP_NOT_REACHED) if ret_s == DRV_SUCCESS else ret_s, float(t))

    def cooler_on(self) -> int:
        return self._call(lambda: self._cam.set_cooler(True))

    def cooler_off(self) -> int:
        return self._call(lambda: self._cam.set_cooler(False))

    def is_cooler_on(self) -> Tuple[int, bool]:
        ret, on = self._get(self._cam.is_cooler_on if self.available else None, False)
        return (ret, bool(on))

    def get_temperature_range(self) -> Tuple[int, int, int]:
        ret, rng = self._get(self._cam.get_temperature_range if self.available else None, (0, 0))
        return (ret, int(rng[0]), int(rng[1]))

    def set_fan_mode(self, mode: int) -> int:
        name = _FAN_NAMES.get(int(mode))
        if name is None:
            return DRV_P1INVALID
        return self._call(lambda: self._cam.set_fan_mode(name))

    # ── Amplificador, velocidades y ganancia ──────────────────────────────────
    def _amp_modes(self):
        ret, modes = self._get(self._cam.get_all_amp_modes if self.available else None, [])
        return modes if ret == DRV_SUCCESS else []

    def _current_oamp(self) -> int:
        ret, oamp = self._get(self._cam.get_oamp if self.available else None, 0)
        return int(oamp) if ret == DRV_SUCCESS else 0

    def _hs_table(self):
        """Velocidades horizontales (MHz) del amplificador vigente, por índice."""
        oamp = self._current_oamp()
        table = {}
        for m in self._amp_modes():
            if m.oamp == oamp:
                table[int(m.hsspeed)] = float(m.hsspeed_MHz)
        return [table[i] for i in sorted(table)]

    def _preamp_table(self):
        table = {}
        for m in self._amp_modes():
            table[int(m.preamp)] = float(m.preamp_gain)
        return [table[i] for i in sorted(table)]

    def get_output_amplifier(self) -> Optional[int]:
        """Amplificador vigente (0 = EM, 1 = convencional), o None si no se pudo leer."""
        ret, oamp = self._get(self._cam.get_oamp if self.available else None, None)
        return int(oamp) if ret == DRV_SUCCESS and oamp is not None else None

    def set_output_amplifier(self, typ: int) -> int:
        if self._live_active:
            return DRV_ACQUIRING
        return self._call(lambda: self._cam.set_amp_mode(oamp=int(typ)))

    def get_number_hs_speeds(self, channel: int = 0, typ: int = 0) -> int:
        return len(self._hs_table())

    def get_hs_speed(self, index: int, channel: int = 0, typ: int = 0) -> Tuple[int, float]:
        table = self._hs_table()
        if not 0 <= int(index) < len(table):
            return (DRV_P1INVALID, float("nan"))
        return (DRV_SUCCESS, table[int(index)])

    def set_hs_speed(self, index: int, typ: int = 0) -> int:
        return self._live_pausing(lambda: self._cam.set_amp_mode(hsspeed=int(index)))

    def get_hs_speed_index(self) -> int:
        ret, idx = self._get(self._cam.get_hsspeed if self.available else None, 0)
        return int(idx)

    def get_number_preamp_gains(self) -> int:
        return len(self._preamp_table())

    def get_preamp_gain(self, index: int) -> Tuple[int, float]:
        table = self._preamp_table()
        if not 0 <= int(index) < len(table):
            return (DRV_P1INVALID, float("nan"))
        return (DRV_SUCCESS, table[int(index)])

    def set_preamp_gain(self, index: int) -> int:
        return self._live_pausing(lambda: self._cam.set_amp_mode(preamp=int(index)))

    def get_preamp_gain_index(self) -> int:
        ret, idx = self._get(self._cam.get_preamp if self.available else None, 0)
        return int(idx)

    def get_current_preamp_gain(self) -> Tuple[int, int]:
        ret, idx = self._get(self._cam.get_preamp if self.available else None, -1)
        return (ret, int(idx))

    def get_number_vs_speeds(self) -> Tuple[int, int]:
        ret, speeds = self._get(self._cam.get_all_vsspeeds if self.available else None, [])
        return (ret, len(speeds))

    def get_vs_speed(self, index: int) -> Tuple[int, float]:
        ret, speeds = self._get(self._cam.get_all_vsspeeds if self.available else None, [])
        if ret != DRV_SUCCESS:
            return (ret, float("nan"))
        if not 0 <= int(index) < len(speeds):
            return (DRV_P1INVALID, float("nan"))
        return (DRV_SUCCESS, float(speeds[int(index)]))

    def get_vs_speed_index(self) -> Optional[int]:
        ret, idx = self._get(self._cam.get_vsspeed if self.available else None, None)
        return int(idx) if ret == DRV_SUCCESS and idx is not None else None

    def set_vs_speed(self, index: int) -> int:
        return self._live_pausing(lambda: self._cam.set_vsspeed(int(index)))

    def set_emccd_gain(self, gain: int) -> int:
        if not _specular_gain_allowed(int(gain)):
            return DRV_P1INVALID
        ret = self._call(lambda: self._cam.set_EMCCD_gain(int(gain)))
        get_interlock().note_gain_set(ret, int(gain))
        return ret

    def get_emccd_gain(self) -> Tuple[int, int]:
        ret, g = self._get(self._cam.get_EMCCD_gain if self.available else None, (0, False))
        value = int(g[0]) if isinstance(g, (tuple, list)) else int(g)
        get_interlock().note_gain_reading(ret, value)
        return (ret, value)

    # ── Exposición y obturador ────────────────────────────────────────────────
    def set_exposure_time(self, t_sec: float) -> int:
        code = self._live_pausing(lambda: self._cam.set_exposure(float(t_sec)))
        if code == DRV_SUCCESS:
            self._current_exposure_time = float(t_sec)
        return code

    def get_exposure_time_checked(self) -> Tuple[int, Optional[float]]:
        """Exposición real (GetAcquisitionTimings vía pylablib) con su código. Sin el eco del pedido."""
        ret, e = self._get(self._cam.get_exposure if self.available else None, None)
        return (ret, float(e) if ret == DRV_SUCCESS and e is not None else None)

    def get_exposure_time(self) -> float:
        ret, e = self._get(self._cam.get_exposure if self.available else None, self._current_exposure_time)
        return float(e)

    def set_shutter_mode(self, mode: int, closing_time_ms: int = 0, opening_time_ms: int = 0) -> int:
        entry = _SHUTTER_NAMES.get(int(mode))
        if entry is None:
            return DRV_P1INVALID
        name, ttl = entry
        return self._call(lambda: self._cam.setup_shutter(name, ttl, open_time=opening_time_ms or None,
                                                          close_time=closing_time_ms or None))

    # ── Modos de lectura (coordenadas del SDK: desde 1, inclusivas) ───────────
    def set_read_mode(self, mode: int) -> int:
        name = _READ_MODE_NAMES.get(int(mode))
        if name is None:
            return DRV_P1INVALID
        if self._live_active:
            return DRV_ACQUIRING
        if int(mode) == READ_MODE_SINGLE_TRACK:
            ret = self._call(lambda: self._cam.setup_single_track_mode(center=self._track_center - 1,
                                                                      width=self._track_height))
        else:
            ret = self._call(lambda: self._cam.set_read_mode(name))
        if ret == DRV_SUCCESS:
            self._read_mode = int(mode)
        return ret

    def get_read_mode(self) -> int:
        return self._read_mode

    def set_single_track(self, center: int, height: int) -> int:
        if self._live_active:
            return DRV_ACQUIRING
        self._track_center = max(1, min(DETECTOR_HEIGHT_PX, int(center)))
        self._track_height = max(1, min(DETECTOR_HEIGHT_PX, int(height)))
        ret = self._call(lambda: self._cam.setup_single_track_mode(center=self._track_center - 1,
                                                                  width=self._track_height))
        if ret == DRV_SUCCESS:
            self._read_mode = READ_MODE_SINGLE_TRACK
        return ret

    def get_single_track(self) -> Tuple[int, int]:
        return (self._track_center, self._track_height)

    def set_image(self, hbin: int = 1, vbin: int = 1, hstart: int = 1, hend: int = DETECTOR_WIDTH_PX,
                  vstart: int = 1, vend: int = DETECTOR_HEIGHT_PX) -> int:
        if self._live_active:
            return DRV_ACQUIRING
        ret = self._call(lambda: self._cam.setup_image_mode(int(hstart) - 1, int(hend), int(vstart) - 1,
                                                           int(vend), int(hbin), int(vbin)))
        if ret == DRV_SUCCESS:
            self._read_mode = READ_MODE_IMAGE
        return ret

    def set_multi_track(self, number: int, height: int, offset: int) -> Tuple[int, int, int]:
        if self._live_active:
            return (DRV_ACQUIRING, 0, 0)
        ret, res = self._get(self._cam.setup_multi_track_mode if self.available else None, None,
                             int(number), int(height), int(offset))
        if ret != DRV_SUCCESS or res is None:
            return (ret, 0, 0)
        self._read_mode = READ_MODE_MULTI_TRACK
        return (ret, int(res[3]), int(res[4]))

    def set_random_track(self, areas: list) -> int:
        if self._live_active:
            return DRV_ACQUIRING
        tracks = [(int(y0) - 1, int(y1)) for (y0, y1) in areas]
        ret = self._call(lambda: self._cam.setup_random_track_mode(tracks))
        if ret == DRV_SUCCESS:
            self._read_mode = READ_MODE_RANDOM_TRACK
        return ret

    def frame_shape(self) -> Optional[Tuple[int, int]]:
        """(filas, columnas) del cuadro con el modo de lectura vigente (`get_data_dimensions` de pylablib)."""
        ret, dims = self._get(self._cam.get_data_dimensions if self.available else None, None)
        return (int(dims[0]), int(dims[1])) if ret == DRV_SUCCESS and dims is not None else None

    def get_full_info(self) -> dict:
        """`get_full_info()` de pylablib para guardar con el cuadro (C1 de R4-M). Sus lecturas ignoran el
        DRV_ACQUIRING del SDK; si igual falla, se devuelve el motivo en vez del diccionario."""
        ret, info = self._get(self._cam.get_full_info if self.available else None, None)
        if ret != DRV_SUCCESS or info is None:
            return {"error": f"get_full_info no disponible (código {ret})"}
        return dict(info)

    def get_detector(self) -> Tuple[int, int, int]:
        ret, size = self._get(self._cam.get_detector_size if self.available else None, (-1, -1))
        return (ret, int(size[0]), int(size[1]))

    # ── Estado y adquisición ──────────────────────────────────────────────────
    def get_status_checked(self) -> Tuple[int, int]:
        ret, status = self._get(self._cam.get_status if self.available else None, None)
        if ret != DRV_SUCCESS:
            return (ret, DRV_NOT_INITIALIZED)
        return (DRV_SUCCESS, DRV_ACQUIRING if status == "acquiring" else DRV_IDLE)

    def get_status(self) -> int:
        ret, status = self.get_status_checked()
        return status

    def set_acquisition_mode(self, mode: int) -> int:
        name = "single" if int(mode) == ACQ_MODE_SINGLE_SCAN else "cont"
        return self._call(lambda: self._cam.setup_acquisition(mode=name))

    def start_acquisition(self) -> int:
        return self._call(self._cam.start_acquisition if self.available else None)

    def abort_acquisition(self) -> int:
        return self._call(self._cam.stop_acquisition if self.available else None)

    # ── Live (contrato de live_stream; paquete 1 de R4-M) ─────────────────────
    @property
    def live_active(self) -> bool:
        return self._live_active

    def _live_pausing(self, fn: Callable) -> int:
        """Con el Live activo, aplica `fn` dentro de `pausing_acquisition` (detiene, cambia y vuelve a
        arrancar). Sin Live, como antes: si adquiere una rutina, el SDK rechaza con DRV_ACQUIRING."""
        if not self.available:
            return DRV_NOT_INITIALIZED
        with self._lock:
            if not (self._live_active and self._cam.acquisition_in_progress()):
                return self._call(fn)

            def paused():
                with self._cam.pausing_acquisition():
                    fn()
            code = self._call(paused)
            self._live_not_shown_total = 0          # el reinicio pone en cero el contador de pylablib
            return code

    def start_live(self) -> int:
        """Adquisición continua para el Live: siempre "cont", aunque el estado base haya dejado
        "single" (A1). Con otro Live activo devuelve DRV_ACQUIRING: pylablib reiniciaría la adquisición
        en silencio."""
        if not self.available:
            return DRV_NOT_INITIALIZED
        with self._lock:
            if self._live_active:
                return DRV_ACQUIRING
            cam = self._cam
            for fn in (cam.stop_acquisition, lambda: cam.setup_acquisition(mode="cont"), cam.start_acquisition):
                code = self._call(fn)
                if code != DRV_SUCCESS:
                    self._call(cam.stop_acquisition)
                    return code
            self._live_active = True
            self._live_not_shown_total = 0
            return DRV_SUCCESS

    def stop_live(self) -> int:
        """Detiene sólo el Live: si el Live no está activo no toca la cámara (puede exponer una rutina)."""
        with self._lock:
            if not self._live_active:
                return DRV_SUCCESS
            self._live_active = False
            if not self.available:
                return DRV_NOT_INITIALIZED
            return self._call(self._cam.stop_acquisition)

    def read_live_frame(self) -> Optional[LiveFrame]:
        """El cuadro más nuevo, marcando leídos los anteriores (A2). `None` si no llegó uno nuevo;
        `LiveStopped` si el Live no está activo o la cámara dejó de adquirir. Nunca lee cuadros de una
        rutina: sin Live activo no toca el contador."""
        self._require_connected()
        with self._lock:
            cam = self._cam
            if not self._live_active:
                raise LiveStopped("el Live no está activo")
            if not cam.acquisition_in_progress():
                self._live_active = False
                raise LiveStopped("la cámara dejó de adquirir")
            rng = cam.get_new_images_range()
            if rng is None:
                return None
            first, last = int(rng[0]), int(rng[1])
            frames, infos = cam.read_multiple_images(rng=(last - 1, last), return_info=True)
            if not frames:
                return None
            not_shown = max(0, last - 1 - first)
            self._live_not_shown_total += not_shown
            status = cam.get_frames_status()
            lost = max(0, int(status.skipped) - self._live_not_shown_total)
            fill = float(status.unread) / float(status.buffer_size) if status.buffer_size else 0.0
            info = infos[0] if infos else None
            index = getattr(info, "frame_index", None)
            index = int(index) if index is not None else last - 1
            data = np.asarray(frames[0], dtype=np.float32)
        return LiveFrame(data, index, time.monotonic(), not_shown, lost, fill)

    def get_most_recent_image(self, width: int = DETECTOR_WIDTH_PX, height: int = DETECTOR_HEIGHT_PX) -> np.ndarray:
        """Último cuadro disponible (para el Live). Nunca ceros: sin cuadro, `FrameNotReady`."""
        self._require_connected()
        with self._lock:
            frame = self._cam.read_newest_image(peek=True)
        if frame is None:
            raise FrameNotReady("todavía no hay un cuadro")
        return np.asarray(frame, dtype=np.float32)

    def get_1d_spectrum(self, width: int = DETECTOR_WIDTH_PX) -> np.ndarray:
        return np.asarray(self.get_most_recent_image(), dtype=np.float32).ravel()

    def get_acquired_data(self, width: int = DETECTOR_WIDTH_PX, height: int = DETECTOR_HEIGHT_PX) -> np.ndarray:
        if self._read_mode in (READ_MODE_FVB, READ_MODE_SINGLE_TRACK):
            return self.get_1d_spectrum(width)
        return self.get_most_recent_image(width, height)

    def get_tracks_2d_spectrum(self, n_tracks: int, width: int = DETECTOR_WIDTH_PX) -> np.ndarray:
        return np.asarray(self.get_most_recent_image(), dtype=np.float32).reshape((int(n_tracks), -1))

    # ── Una exposición = un cuadro nuevo (el contrato de single_exposure) ──────
    def acquire_single(self, req, *, should_abort, on_tick, is_estopped, clock, tranche_ms, readout_margin_s):
        """Mismo contrato que `acquisition.single_exposure`, con el camino de pylablib del legado."""
        from pyspectrum.modules.acquisition import AcquisitionFailure, AcquisitionFailureKind as K, Frame

        def fail(kind, code=None, call=None, detail=""):
            return AcquisitionFailure(kind, code, call, detail)

        cam = self._cam
        if self._live_active:
            return fail(K.NOT_IDLE, DRV_ACQUIRING, "live", "el Live está activo: hay que detenerlo antes")
        ret, status = self.get_status_checked()
        if ret != DRV_SUCCESS:
            return fail(K.READ_FAILED, ret, "get_status", "no se pudo consultar el estado de la cámara")
        if status == DRV_ACQUIRING:
            return fail(K.NOT_IDLE, status, "get_status", "la cámara ya está adquiriendo (¿Live activo?)")
        # Pregunta 1 de la Ronda 2 del Live: la rutina no cambia la exposición del operador.
        ret_e, exposure_before = self._get(cam.get_exposure, None)
        exposure_before = float(exposure_before) if ret_e == DRV_SUCCESS and exposure_before is not None else None
        for call, fn in (("setup_acquisition", lambda: cam.setup_acquisition(mode="single")),
                         ("set_exposure", lambda: cam.set_exposure(float(req.exposure_s)))):
            code = self._call(fn)
            if code != DRV_SUCCESS:
                return fail(K.SETTER_REJECTED, code, call, f"{call} rechazado")
        ret, exp_actual = self._get(cam.get_exposure, float("nan"))
        cycle_s = max(float(req.exposure_s), float(exp_actual) if np.isfinite(exp_actual) else 0.0)
        t_start = clock()
        code = self._call(cam.start_acquisition)
        if code != DRV_SUCCESS:
            return fail(K.START_FAILED, code, "start_acquisition", "la cámara no arrancó la exposición")
        deadline = t_start + cycle_s + float(readout_margin_s)
        finished = False
        try:
            while True:
                try:
                    with self._lock:
                        cam.wait_for_frame(timeout=tranche_ms / 1000.0)
                    finished = True
                except cam.TimeoutError:
                    pass
                on_tick()
                if finished:
                    break
                if should_abort():
                    return fail(K.USER_STOP, None, None, "detenido por el operador")
                if is_estopped():
                    return fail(K.ESTOP, None, None, "parada de emergencia")
                if clock() > deadline:
                    return fail(K.TIMEOUT, None, "wait_for_frame",
                                f"el cuadro no llegó en {cycle_s + readout_margin_s:.2f} s")
            ret, frame = self._get(lambda: cam.read_oldest_image(), None)
            if ret != DRV_SUCCESS:
                return fail(K.READ_FAILED, ret, "read_oldest_image", "la lectura del cuadro falló")
            if frame is None:
                return fail(K.STALE_FRAME, DRV_NO_NEW_DATA, "read_oldest_image", "no hay un cuadro nuevo")
            data = np.asarray(frame, dtype=np.float64)
            n = int(np.prod(req.shape))
            if data.size != n:
                return fail(K.SIZE_MISMATCH, None, "read_oldest_image",
                            f"se esperaban {n} valores y llegaron {data.size}")
            return Frame(data.reshape(req.shape), float(exp_actual), None, t_start, clock())
        finally:
            self._call(cam.stop_acquisition)
            # El Live del legado y de 3.0 trabaja en adquisición continua: se deja como estaba.
            self._call(lambda: cam.setup_acquisition(mode="cont"))
            if exposure_before is not None:
                self._call(lambda: cam.set_exposure(exposure_before))
