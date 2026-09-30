# -*- coding: utf-8 -*-
"""
camera_control.py — Control de la cámara en operación (paso 8 del bloque A, D-13, DEC-040)

Setpoint de temperatura, enfriador, ventilador y velocidad horizontal después del arranque. Contrato de
R2-inst §6.2-6.3 y de la Ronda 3 §2.2 (con H-08 y H-27):

- **Verificación:**
  - el enfriador se relee con IsCoolerOn;
  - el setpoint, el ventilador y el índice de HS no tienen getter en el SDK. Quedan registrados como
    **enviados** ([E]) en el `SentRegistry` con el DRV_SUCCESS de la escritura.
- **Entre adquisiciones:** con la cámara adquiriendo, el SDK rechaza estos cambios con DRV_ACQUIRING.
  El pedido queda pendiente y `apply_pending()` lo aplica cuando la cámara está IDLE. Nunca se aborta el
  Live ni una rutina por esto.
- **Durante el Live (paquete 1 de R4-M, pregunta 2):** la velocidad HS se aplica en el momento: el driver
  pausa el Live (`pausing_acquisition`), la cambia y lo vuelve a arrancar. Con una rutina adquiriendo sigue
  quedando pendiente.
- **Ventilador:** "low" = FanMode 1 (arranque, R4-A-6) y "high" = FanMode 0 ("full"). "Off" no se ofrece:
  con el sensor frío el manual lo permite sólo por períodos cortos (SDK p. 273).
- **Setpoint:** se valida contra GetTemperatureRange.
- **HS:** se elige **por valor** en la tabla de la cámara; un valor que no está se rechaza sin adivinar.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple

from pyspectrum.services.spectrometer_state import SentRegistry, get_sent_registry

_DRV_SUCCESS = 20002
_DRV_ACQUIRING = 20072
FAN_MODES = {"low": 1, "high": 0}          # SetFanMode: 0 = full, 1 = low, 2 = off (SDK p. 273)
HS_TOLERANCE_MHZ = 0.5


class ControlState(Enum):
    APPLIED = "APPLIED"
    PENDING = "PENDING"
    FAILED = "FAILED"
    MISMATCH = "MISMATCH"
    REFUSED = "REFUSED"


@dataclass(frozen=True)
class ControlResult:
    name: str
    state: ControlState
    detail: str = ""
    code: Optional[int] = None


class CameraControlService:
    def __init__(self, camera, sent: Optional[SentRegistry] = None):
        self.camera = camera
        self.sent = sent if sent is not None else get_sent_registry()
        self._lock = threading.Lock()
        self._pending: Dict[str, Callable[[], ControlResult]] = {}

    # ── Estado de la cámara ──
    def _acquiring(self) -> bool:
        cam = self.camera
        try:
            if hasattr(cam, "get_status_checked"):
                ret, st = cam.get_status_checked()
                return ret == _DRV_SUCCESS and st == _DRV_ACQUIRING
            return cam.get_status() == _DRV_ACQUIRING
        except Exception:
            return False

    def _live_only(self) -> bool:
        """La cámara adquiere porque corre el Live (no una rutina)."""
        return bool(getattr(self.camera, "live_active", False))

    def _run_or_defer(self, name: str, action: Callable[[], ControlResult], what: str,
                      live_pausable: bool = False) -> ControlResult:
        if self._acquiring() and not (live_pausable and self._live_only()):
            with self._lock:
                self._pending[name] = action
            return ControlResult(name, ControlState.PENDING,
                                 f"{what}: pendiente; se aplica cuando la cámara termine de adquirir "
                                 f"(detené el Live o esperá a que termine la rutina).")
        with self._lock:
            self._pending.pop(name, None)
        return action()

    def pending_names(self) -> List[str]:
        with self._lock:
            return sorted(self._pending)

    def apply_pending(self) -> List[ControlResult]:
        """Aplica los pedidos pendientes si la cámara está IDLE. Lo llama el sondeo del estado."""
        if self._acquiring():
            return []
        with self._lock:
            items = list(self._pending.items())
            self._pending.clear()
        return [action() for _name, action in items]

    # ── Pedidos ──
    def request_temperature(self, setpoint_c: int) -> ControlResult:
        setpoint_c = int(setpoint_c)
        rng = self.camera.get_temperature_range() if hasattr(self.camera, "get_temperature_range") else None
        if rng and rng[0] == _DRV_SUCCESS:
            lo, hi = int(rng[1]), int(rng[2])
            if not lo <= setpoint_c <= hi:
                return ControlResult("temperature_setpoint_c", ControlState.REFUSED,
                                     f"{setpoint_c} °C está fuera del rango de la cámara ({lo} a {hi} °C).")

        def action() -> ControlResult:
            code = self.camera.set_temperature(setpoint_c)
            self.sent.record("temperature_setpoint_c", setpoint_c, code)
            if code != _DRV_SUCCESS:
                return ControlResult("temperature_setpoint_c", ControlState.FAILED,
                                     f"SetTemperature({setpoint_c}) devolvió {code}.", code)
            return ControlResult("temperature_setpoint_c", ControlState.APPLIED,
                                 f"Setpoint enviado: {setpoint_c} °C.", code)
        return self._run_or_defer("temperature_setpoint_c", action, f"setpoint {setpoint_c} °C")

    def request_cooler(self, on: bool) -> ControlResult:
        def action() -> ControlResult:
            code = self.camera.cooler_on() if on else self.camera.cooler_off()
            if code != _DRV_SUCCESS:
                return ControlResult("cooler_on", ControlState.FAILED,
                                     f"{'CoolerON' if on else 'CoolerOFF'} devolvió {code}.", code)
            ret, state = self.camera.is_cooler_on()
            if ret != _DRV_SUCCESS:
                return ControlResult("cooler_on", ControlState.FAILED,
                                     f"No se pudo releer el enfriador (IsCoolerOn {ret}).", ret)
            if bool(state) != bool(on):
                return ControlResult("cooler_on", ControlState.MISMATCH,
                                     f"Se pidió {'encender' if on else 'apagar'}; IsCoolerOn dice "
                                     f"{'encendido' if state else 'apagado'}.", ret)
            return ControlResult("cooler_on", ControlState.APPLIED,
                                 f"Enfriador {'encendido' if on else 'apagado'} (releído).", ret)
        return self._run_or_defer("cooler_on", action, "enfriador")

    def request_fan(self, mode: str) -> ControlResult:
        if mode not in FAN_MODES:
            raise ValueError("ventilador: sólo 'low' o 'high' ('off' no se ofrece)")
        code_mode = FAN_MODES[mode]

        def action() -> ControlResult:
            code = self.camera.set_fan_mode(code_mode)
            self.sent.record("fan_mode", code_mode, code)
            if code != _DRV_SUCCESS:
                return ControlResult("fan_mode", ControlState.FAILED, f"SetFanMode({code_mode}) devolvió {code}.", code)
            return ControlResult("fan_mode", ControlState.APPLIED, f"Ventilador en {mode} (enviado).", code)
        return self._run_or_defer("fan_mode", action, f"ventilador en {mode}")

    def hs_table(self) -> List[float]:
        cam = self.camera
        out = []
        for i in range(int(cam.get_number_hs_speeds())):
            ret, mhz = cam.get_hs_speed(i)
            if ret == _DRV_SUCCESS:
                out.append(float(mhz))
        return out

    def request_hs_speed_mhz(self, mhz: float) -> ControlResult:
        table = self.hs_table()
        idx = next((i for i, v in enumerate(table) if abs(v - float(mhz)) <= HS_TOLERANCE_MHZ), None)
        if idx is None:
            return ControlResult("hs_speed_mhz", ControlState.REFUSED,
                                 f"{mhz:g} MHz no está en la tabla de la cámara ({', '.join(f'{v:g}' for v in table)} MHz).")
        value = table[idx]

        def action() -> ControlResult:
            code = self.camera.set_hs_speed(idx)
            self.sent.record("hs_speed_mhz", value, code)
            if code != _DRV_SUCCESS:
                return ControlResult("hs_speed_mhz", ControlState.FAILED, f"SetHSSpeed({idx}) devolvió {code}.", code)
            return ControlResult("hs_speed_mhz", ControlState.APPLIED, f"HS {value:g} MHz (enviada).", code)
        return self._run_or_defer("hs_speed_mhz", action, f"HS {value:g} MHz", live_pausable=True)
