# -*- coding: utf-8 -*-
"""
spectrometer_state.py — Estado leído del espectrómetro (paso 8 del bloque A, DEC-040)

Es la única fuente de lo que muestra la GUI (R2-arq §2.4, reconciliado con D-15): una instantánea en la
que cada campo es un `Reading` con su estado. Marcas de la Ronda 3 §1.1:

| Estado | Marca | Qué significa |
| :--- | :--- | :--- |
| READ_OK | [L] | leído; con la edad si pasa de 3 s |
| SENT_OK | [E] | enviado: no hay getter y sólo consta el DRV_SUCCESS de la escritura |
| READ_FAILED | [! código] | falló la lectura, o falló el envío |
| NOT_READ | [?] | sin leer; por ejemplo, la temperatura mientras la cámara adquiere |
| NOT_CONNECTED | [X] | equipo no conectado |

**Un valor viejo nunca se muestra como leído:** si la lectura falla, `value` es None, y lo último leído
queda sólo en `detail`.

Parámetros sin getter, que se muestran [E]:
- los seis de D-15: modo de lectura, modo de adquisición, ventilador, modo de ganancia, índice de VS e
  índice de HS;
- con pylablib, también el pre-amp: su `get_preamp` devuelve lo último enviado, no `GetCurrentPreAmpGain`.
"""
from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Optional, Tuple

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from pyspectrum.drivers import specular_interlock as si

_DRV_SUCCESS = 20002
_DRV_ACQUIRING = 20072
_SHAMROCK_SUCCESS = 20202
_DEVICE = 0
AGE_SHOWN_AFTER_S = 3.0

TEMPERATURE_WORDS = {
    20034: "enfriador apagado",
    20035: "llegó pero no se estabilizó",
    20036: "estabilizada",
    20037: "enfriando, todavía no llega",
    20040: "deriva",
}


class ReadStatus(Enum):
    READ_OK = "READ_OK"
    SENT_OK = "SENT_OK"
    READ_FAILED = "READ_FAILED"
    NOT_READ = "NOT_READ"
    NOT_CONNECTED = "NOT_CONNECTED"


@dataclass(frozen=True)
class Reading:
    value: Any
    status: ReadStatus
    code: Optional[int] = None
    t_read: Optional[float] = None
    detail: str = ""

    def mark(self, clock: Callable[[], float] = time.monotonic) -> str:
        if self.status == ReadStatus.READ_OK:
            if self.t_read is not None:
                age = clock() - self.t_read
                if age > AGE_SHOWN_AFTER_S:
                    return f"[L hace {age:.0f} s]"
            return "[L]"
        if self.status == ReadStatus.SENT_OK:
            return "[E]"
        if self.status == ReadStatus.READ_FAILED:
            return f"[! {self.code}]" if self.code is not None else "[!]"
        if self.status == ReadStatus.NOT_CONNECTED:
            return "[X]"
        return "[?]"

    @property
    def ok(self) -> bool:
        return self.status in (ReadStatus.READ_OK, ReadStatus.SENT_OK)


def _nc(reason: str = "") -> Reading:
    return Reading(None, ReadStatus.NOT_CONNECTED, None, None, reason)


class SentRegistry:
    """Lo último enviado con éxito para los parámetros sin getter (D-15)."""

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._lock = threading.Lock()
        self._clock = clock
        self._items: Dict[str, Reading] = {}

    def record(self, name: str, value: Any, code: Optional[int]) -> None:
        with self._lock:
            if code == _DRV_SUCCESS:
                self._items[name] = Reading(value, ReadStatus.SENT_OK, code, self._clock())
            else:
                self._items[name] = Reading(None, ReadStatus.READ_FAILED, code, self._clock(),
                                            f"falló el envío de {value!r}")

    def get(self, name: str) -> Reading:
        with self._lock:
            return self._items.get(name, Reading(None, ReadStatus.NOT_READ))

    def record_baseline(self, report) -> None:
        """Registra lo que el estado base de arranque envió (paso 8, `camera_baseline`)."""
        for name in ("fan_mode", "read_mode", "acquisition_mode", "em_gain_mode", "vs_speed_us",
                     "hs_speed_mhz", "preamp"):
            item = report.item(name) if report is not None else None
            if item is None or item.outcome in ("SKIPPED", "SDK_DEFAULT"):   # R4-L: no se envió nada
                continue
            value = item.requested
            if name in ("vs_speed_us", "hs_speed_mhz") and isinstance(item.readback, (int, float)):
                value = float(item.readback)
            code = item.set_code if item.set_code is not None else (_DRV_SUCCESS if item.outcome in ("OK", "SENT") else None)
            if item.outcome in ("OK", "SENT") and code == _DRV_SUCCESS:
                self.record(name, value, _DRV_SUCCESS)
            else:
                self.record(name, value, code if code is not None else -1)


_SENT: Optional[SentRegistry] = None


def get_sent_registry() -> SentRegistry:
    global _SENT
    if _SENT is None:
        _SENT = SentRegistry()
    return _SENT


# ── Cámara ────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CameraState:
    connection: Reading
    temperature_c: Reading
    temperature_status: Reading
    cooler_on: Reading
    em_gain: Reading
    em_gain_range: Reading
    exposure_s: Reading
    fan_mode: Reading
    read_mode: Reading
    acquisition_mode: Reading
    em_gain_mode: Reading
    hs_speed_mhz: Reading
    vs_speed_us: Reading
    preamp: Reading
    acquiring: Reading

    @property
    def temperature_word(self) -> str:
        if self.temperature_status.status != ReadStatus.READ_OK:
            return self.temperature_c.detail or "sin lectura"
        return TEMPERATURE_WORDS.get(self.temperature_status.value, f"código {self.temperature_status.value}")


def _pair(value) -> Tuple[int, Any]:
    if isinstance(value, (tuple, list)) and len(value) >= 2:
        return int(value[0]), value[1]
    return _DRV_SUCCESS, value


def read_camera_state(cam, sent: SentRegistry, clock: Callable[[], float] = time.monotonic) -> CameraState:
    """Lee la cámara con sus getters. Nunca inventa un valor."""
    if cam is None or not getattr(cam, "available", True):
        reason = getattr(cam, "unavailable_reason", "") or "cámara no conectada"
        nc = _nc(reason)
        return CameraState(*([nc] * 15))
    now = clock()

    def safe(fn) -> Tuple[Optional[int], Any]:
        if fn is None:
            return (None, None)          # el backend no tiene ese getter: queda "sin leer"
        try:
            return _pair(fn())
        except Exception as e:
            return (None, str(e))

    # Temperatura: el código es el estado (DRV_TEMP_*). Mientras adquiere, el SDK no la lee.
    ret, t = safe(getattr(cam, "get_temperature", None))
    if ret in TEMPERATURE_WORDS or (ret is not None and 20034 <= ret <= 20040):
        temp = Reading(float(t), ReadStatus.READ_OK, ret, now)
        tstat = Reading(ret, ReadStatus.READ_OK, ret, now)
    elif ret == _DRV_ACQUIRING:
        last = f"; último: {float(t):.1f} °C" if isinstance(t, (int, float)) and math.isfinite(float(t)) else ""
        temp = Reading(None, ReadStatus.NOT_READ, ret, now, f"adquiriendo (el SDK no la lee){last}")
        tstat = Reading(None, ReadStatus.NOT_READ, ret, now)
    else:
        temp = Reading(None, ReadStatus.READ_FAILED, ret, now, f"falló la lectura ({ret})")
        tstat = Reading(None, ReadStatus.READ_FAILED, ret, now)

    ret, on = safe(getattr(cam, "is_cooler_on", None))
    cooler = (Reading(bool(on), ReadStatus.READ_OK, ret, now) if ret == _DRV_SUCCESS
              else Reading(None, ReadStatus.READ_FAILED, ret, now))

    ret, g = safe(getattr(cam, "get_emccd_gain", None))
    gain = (Reading(int(g), ReadStatus.READ_OK, ret, now) if ret == _DRV_SUCCESS
            else Reading(None, ReadStatus.READ_FAILED, ret, now))

    if hasattr(cam, "get_em_gain_range"):
        r = cam.get_em_gain_range()
        gr = (Reading((int(r[1]), int(r[2])), ReadStatus.READ_OK, r[0], now) if r and r[0] == _DRV_SUCCESS
              else Reading(None, ReadStatus.READ_FAILED, r[0] if r else None, now))
    else:
        gr = Reading(None, ReadStatus.NOT_READ)

    if hasattr(cam, "get_exposure_time_checked"):
        ret, e = safe(cam.get_exposure_time_checked)
    elif hasattr(cam, "get_exposure_time"):
        ret, e = safe(cam.get_exposure_time)
    else:
        ret, e = (None, None)
    exposure = (Reading(float(e), ReadStatus.READ_OK, ret, now) if ret == _DRV_SUCCESS and e is not None
                else Reading(None, ReadStatus.READ_FAILED, ret, now))

    if hasattr(cam, "get_status_checked"):
        ret, st = safe(cam.get_status_checked)
        acq = (Reading(st == _DRV_ACQUIRING, ReadStatus.READ_OK, ret, now) if ret == _DRV_SUCCESS
               else Reading(None, ReadStatus.READ_FAILED, ret, now))
    else:
        acq = Reading(None, ReadStatus.NOT_READ)

    return CameraState(Reading(True, ReadStatus.READ_OK, _DRV_SUCCESS, now), temp, tstat, cooler, gain, gr,
                       exposure, sent.get("fan_mode"), sent.get("read_mode"), sent.get("acquisition_mode"),
                       sent.get("em_gain_mode"), sent.get("hs_speed_mhz"), sent.get("vs_speed_us"),
                       sent.get("preamp"), acq)


# ── Espectrógrafo ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SpectrographState:
    connection: Reading
    grating: Reading
    grating_lines_per_mm: Reading
    wavelength_nm: Reading
    at_zero_order: Reading
    specular: str
    slit_width_um: Reading
    ports: Reading


def read_spectrograph_state(spec, clock: Callable[[], float] = time.monotonic) -> SpectrographState:
    if spec is None or not getattr(spec, "available", True):
        reason = getattr(spec, "unavailable_reason", "") or "espectrógrafo no conectado"
        nc = _nc(reason)
        return SpectrographState(nc, nc, nc, nc, nc, si.UNKNOWN, nc, nc)
    now = clock()
    g_raw = spec.ShamrockGetGrating(_DEVICE)
    grating = (Reading(int(g_raw[1]), ReadStatus.READ_OK, g_raw[0], now) if g_raw[0] == _SHAMROCK_SUCCESS
               else Reading(None, ReadStatus.READ_FAILED, g_raw[0], now))
    lines = Reading(None, ReadStatus.NOT_READ)
    if grating.ok and hasattr(spec, "ShamrockGetGratingInfo"):
        info = spec.ShamrockGetGratingInfo(_DEVICE, grating.value)
        lines = (Reading(float(info[1]), ReadStatus.READ_OK, info[0], now) if info and info[0] == _SHAMROCK_SUCCESS
                 else Reading(None, ReadStatus.READ_FAILED, info[0] if info else None, now))
    w_raw = spec.ShamrockGetWavelength(_DEVICE)
    wl = (Reading(float(w_raw[1]), ReadStatus.READ_OK, w_raw[0], now) if w_raw[0] == _SHAMROCK_SUCCESS
          else Reading(None, ReadStatus.READ_FAILED, w_raw[0], now))
    at_zero = Reading(None, ReadStatus.NOT_READ)
    z_raw = None
    if hasattr(spec, "ShamrockAtZeroOrder"):
        z_raw = spec.ShamrockAtZeroOrder(_DEVICE)
        at_zero = (Reading(bool(z_raw[1]), ReadStatus.READ_OK, z_raw[0], now) if z_raw[0] == _SHAMROCK_SUCCESS
                   else Reading(None, ReadStatus.READ_FAILED, z_raw[0], now))
    specular = si.classify_reading(g_raw, w_raw, z_raw)

    s_raw = spec.ShamrockGetSlit(_DEVICE, 1)
    slit_ok = s_raw[0] == _SHAMROCK_SUCCESS and isinstance(s_raw[1], (int, float)) and math.isfinite(float(s_raw[1]))
    slit = (Reading(float(s_raw[1]), ReadStatus.READ_OK, s_raw[0], now) if slit_ok
            else Reading(None, ReadStatus.READ_FAILED, s_raw[0], now))
    p_in, p_out = spec.ShamrockGetFlipper(_DEVICE, 1), spec.ShamrockGetFlipper(_DEVICE, 2)
    ports = (Reading((int(p_in[1]), int(p_out[1])), ReadStatus.READ_OK, _SHAMROCK_SUCCESS, now)
             if p_in[0] == _SHAMROCK_SUCCESS and p_out[0] == _SHAMROCK_SUCCESS
             else Reading(None, ReadStatus.READ_FAILED, p_in[0] if p_in[0] != _SHAMROCK_SUCCESS else p_out[0], now))
    return SpectrographState(Reading(True, ReadStatus.READ_OK, _SHAMROCK_SUCCESS, now), grating, lines, wl,
                             at_zero, specular, slit, ports)


# ── Instantánea y servicio ────────────────────────────────────────────────────

@dataclass(frozen=True)
class SpectrometerSnapshot:
    camera: CameraState
    spectrograph: SpectrographState
    seq: int
    t: float


class SpectrometerStateService(QObject):
    """Sondea cámara y espectrógrafo (1 s por defecto) y publica una instantánea inmutable."""

    snapshotChanged = pyqtSignal(object)

    def __init__(self, camera, spectrometer, sent: Optional[SentRegistry] = None, *, interval_ms: int = 1000,
                 clock: Callable[[], float] = time.monotonic, parent=None):
        super().__init__(parent)
        self.camera = camera
        self.spectrometer = spectrometer
        self.sent = sent if sent is not None else get_sent_registry()
        self._clock = clock
        self._seq = 0
        self.last: Optional[SpectrometerSnapshot] = None
        self._timer = QTimer(self)
        self._timer.setInterval(int(interval_ms))
        self._timer.timeout.connect(self.poll)

    def start(self):
        self._timer.start()

    def stop(self):
        self._timer.stop()

    def poll(self) -> SpectrometerSnapshot:
        self._seq += 1
        snap = SpectrometerSnapshot(read_camera_state(self.camera, self.sent, self._clock),
                                    read_spectrograph_state(self.spectrometer, self._clock),
                                    self._seq, self._clock())
        self.last = snap
        self.snapshotChanged.emit(snap)
        return snap
