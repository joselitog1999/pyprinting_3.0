# -*- coding: utf-8 -*-
"""
camera_baseline.py — Estado operativo base de la cámara al arrancar (bloque A, paso 8, DEC-040)

Secuencia C2-C21 de la Ronda 2 (`docs/evidence/auditoria_2026-09-27/pyspectrum_A_ronda2/
instrumentation.md` §1.2), con las decisiones del investigador (R4-A-6, R4-B-8):
- se fijan parámetros ELECTRÓNICOS de la cámara, cada uno con escritura → relectura → comparación
  cuando el SDK tiene con qué releer, y rotulado "enviado" (SENT) cuando no (D-15);
- nada del espectrógrafo, nada de calibración: el arranque no mueve la red ni escribe offsets;
- enfriador encendido a −60 °C, ventilador en bajo (con opción alto), velocidad vertical 1.9 µs como
  el legado y velocidad horizontal 13 MHz, ambas elegidas POR VALOR en la tabla del SDK.

pylablib, la referencia probada en el banco (R4-E), hace lo mismo al conectar: fija ventilador,
enfriador, ganancia EM 0 y velocidad vertical; el legado agregaba pre-amp 0 y `set_vsspeed(2)`.

Una falla de un ítem no aborta el arranque: queda en el informe. Sólo `blocks_acquisition` (ganancia
EM 0 no confirmada, modos, pre-amp, geometría) debe bloquear las adquisiciones.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple

from pyspectrum.drivers.andor_ccd_driver import (
    ACQ_MODE_SINGLE_SCAN, DETECTOR_HEIGHT_PX, DETECTOR_WIDTH_PX, DRV_ACQUIRING, DRV_SUCCESS,
    FAN_MODE_LOW, READ_MODE_IMAGE,
)

OK, SENT, SET_FAILED, READBACK_MISMATCH, NOT_READABLE, SKIPPED = (
    "OK", "SENT", "SET_FAILED", "READBACK_MISMATCH", "NOT_READABLE", "SKIPPED")


@dataclass(frozen=True)
class CameraBaseline:
    acquisition_mode: int = ACQ_MODE_SINGLE_SCAN
    read_mode: int = READ_MODE_IMAGE
    image: Tuple[int, int, int, int, int, int] = (1, 1, 1, DETECTOR_WIDTH_PX, 1, DETECTOR_HEIGHT_PX)
    output_amplifier: int = 0            # registro EMCCD; el 885 no tiene amplificador convencional listado
    hs_speed_mhz: float = 13.0           # R4-B-8: 13 MHz por defecto, modificable
    hs_speed_tol_mhz: float = 0.5
    preamp_index: int = 0                # el SDK exige fijarlo antes de adquirir (nota de versión, p. 16)
    vs_speed_us: float = 1.9             # como el legado (Camera_ps.py:607)
    vs_speed_tol_us: float = 0.05
    em_gain_mode: int = 0                # DAC 0-255
    em_gain: int = 0
    fan_mode: int = FAN_MODE_LOW         # R4-A-6: bajo; FAN_MODE_FULL = alto, opción del operador
    temperature_c: int = -60             # R4-A-6
    cooler_on: bool = True


@dataclass(frozen=True)
class BaselineItem:
    name: str
    requested: Any
    set_code: Optional[int]
    readback: Any
    outcome: str
    detail: str = ""


@dataclass
class BaselineReport:
    items: List[BaselineItem] = field(default_factory=list)

    # Ítems sin los cuales no se debe adquirir (instrumentation §1.2, columna "Si falla").
    BLOCKING = ("detector", "acquisition_mode", "read_mode", "image", "output_amplifier",
                "preamp", "em_gain_mode", "em_gain")

    @property
    def blocks_acquisition(self) -> bool:
        return any(i.name in self.BLOCKING and i.outcome not in (OK, SENT) for i in self.items)

    def item(self, name: str) -> Optional[BaselineItem]:
        return next((i for i in self.items if i.name == name), None)

    def summary(self) -> str:
        return "; ".join(f"{i.name}={i.outcome}" for i in self.items)


def _pick_by_value(values: List[float], target: float, tol: float) -> Optional[int]:
    best = None
    for i, v in enumerate(values):
        if v == v and abs(v - target) <= tol and (best is None or abs(v - target) < abs(values[best] - target)):
            best = i
    return best


def apply_camera_baseline(cam: Any, profile: CameraBaseline = CameraBaseline()) -> BaselineReport:
    """Fija y relee el estado operativo base. No llama nunca a funciones del espectrógrafo."""
    rep = BaselineReport()
    add = rep.items.append

    if not getattr(cam, "available", True):
        add(BaselineItem("camera", None, None, None, SKIPPED,
                         getattr(cam, "unavailable_reason", "") or "cámara no conectada"))
        return rep

    # C2: geometría. Si no es la de la hoja de datos, la cámara instalada no es la esperada (DEC-033).
    ret, w, h = cam.get_detector()
    if ret != DRV_SUCCESS:
        add(BaselineItem("detector", (DETECTOR_WIDTH_PX, DETECTOR_HEIGHT_PX), None, None, NOT_READABLE, f"GetDetector {ret}"))
    else:
        ok = (w, h) == (DETECTOR_WIDTH_PX, DETECTOR_HEIGHT_PX)
        add(BaselineItem("detector", (DETECTOR_WIDTH_PX, DETECTOR_HEIGHT_PX), None, (w, h),
                         OK if ok else READBACK_MISMATCH, "" if ok else "geometría distinta de la hoja de datos"))

    # C3: la cámara tiene que estar inactiva; si no, se aborta una vez.
    ret, status = cam.get_status_checked()
    if ret == DRV_SUCCESS and status == DRV_ACQUIRING:
        cam.abort_acquisition()

    # C4: al cerrar, el enfriador vuelve a ambiente (seguro).
    add(BaselineItem("cooler_mode_on_shutdown", 0, cam.set_cooler_mode(0), None, SENT))

    # C5-C8: modos, imagen y amplificador. El SDK no tiene getters: "enviado" si el Set respondió éxito.
    for name, fn, arg in (("acquisition_mode", cam.set_acquisition_mode, profile.acquisition_mode),
                          ("read_mode", cam.set_read_mode, profile.read_mode),
                          ("output_amplifier", cam.set_output_amplifier, profile.output_amplifier)):
        code = fn(arg)
        add(BaselineItem(name, arg, code, None, SENT if code == DRV_SUCCESS else SET_FAILED))
    code = cam.set_image(*profile.image)
    add(BaselineItem("image", profile.image, code, None, SENT if code == DRV_SUCCESS else SET_FAILED))

    # C9: velocidad horizontal POR VALOR (R4-B-8).
    n_hs = cam.get_number_hs_speeds(0, 0)
    hs_values = [cam.get_hs_speed(i, 0, 0)[1] for i in range(int(n_hs))]
    idx = _pick_by_value(hs_values, profile.hs_speed_mhz, profile.hs_speed_tol_mhz)
    if idx is None:
        add(BaselineItem("hs_speed_mhz", profile.hs_speed_mhz, None, hs_values, SET_FAILED,
                         "ninguna velocidad de la tabla coincide"))
    else:
        code = cam.set_hs_speed(idx, 0)
        add(BaselineItem("hs_speed_mhz", profile.hs_speed_mhz, code, hs_values[idx],
                         SENT if code == DRV_SUCCESS else SET_FAILED, f"índice {idx} de {hs_values}"))

    # C10: pre-amp, con relectura.
    code = cam.set_preamp_gain(profile.preamp_index)
    ret, cur = cam.get_current_preamp_gain()
    outcome = SET_FAILED if code != DRV_SUCCESS else (OK if ret == DRV_SUCCESS and cur == profile.preamp_index
                                                        else READBACK_MISMATCH if ret == DRV_SUCCESS else SENT)
    add(BaselineItem("preamp", profile.preamp_index, code, cur if ret == DRV_SUCCESS else None, outcome))

    # C11: velocidad vertical POR VALOR (1.9 µs; el legado usaba el índice 2).
    ret, n_vs = cam.get_number_vs_speeds()
    vs_values = [cam.get_vs_speed(i)[1] for i in range(int(n_vs))] if ret == DRV_SUCCESS else []
    idx = _pick_by_value(vs_values, profile.vs_speed_us, profile.vs_speed_tol_us)
    if idx is None:
        add(BaselineItem("vs_speed_us", profile.vs_speed_us, None, vs_values, SET_FAILED,
                         "ninguna velocidad de la tabla da 1.9 µs: no se fija a ciegas (BANCO-38)"))
    else:
        code = cam.set_vs_speed(idx)
        add(BaselineItem("vs_speed_us", profile.vs_speed_us, code, vs_values[idx],
                         SENT if code == DRV_SUCCESS else SET_FAILED,
                         f"índice {idx}" + ("" if idx == 2 else " (el legado usaba el 2: la tabla difiere)")))

    # C13-C14: modo de ganancia y ganancia 0, confirmada por relectura. Sin esto no se adquiere.
    code = cam.set_em_gain_mode(profile.em_gain_mode)
    ret, lo, hi = cam.get_em_gain_range()
    add(BaselineItem("em_gain_mode", profile.em_gain_mode, code, (lo, hi) if ret == DRV_SUCCESS else None,
                     SENT if code == DRV_SUCCESS else SET_FAILED, "rango de ganancia del modo vigente"))
    code = cam.set_emccd_gain(profile.em_gain)
    got = cam.get_emccd_gain()   # el driver real devuelve (código, ganancia); el simulador, la ganancia
    ret, g = got if isinstance(got, tuple) else (DRV_SUCCESS, got)
    if code != DRV_SUCCESS:
        outcome = SET_FAILED
    elif ret != DRV_SUCCESS:
        outcome = NOT_READABLE
    else:
        outcome = OK if int(g) == profile.em_gain else READBACK_MISMATCH
    add(BaselineItem("em_gain", profile.em_gain, code, g if ret == DRV_SUCCESS else None, outcome))

    # C17: ventilador (sin getter).
    code = cam.set_fan_mode(profile.fan_mode)
    add(BaselineItem("fan_mode", profile.fan_mode, code, None, SENT if code == DRV_SUCCESS else SET_FAILED))

    # C18-C20: enfriador a −60 °C, dentro del rango de la cámara, con relectura de IsCoolerOn.
    ret, t_min, t_max = cam.get_temperature_range()
    if ret == DRV_SUCCESS and not (t_min <= profile.temperature_c <= t_max):
        add(BaselineItem("temperature_c", profile.temperature_c, None, (t_min, t_max), SKIPPED,
                         "fuera del rango de la cámara: no se fija"))
    else:
        code = cam.set_temperature(profile.temperature_c)
        add(BaselineItem("temperature_c", profile.temperature_c, code, (t_min, t_max) if ret == DRV_SUCCESS else None,
                         SENT if code == DRV_SUCCESS else SET_FAILED))
    if profile.cooler_on:
        code = cam.cooler_on()
        ret, on = cam.is_cooler_on()
        outcome = SET_FAILED if code != DRV_SUCCESS else (OK if ret == DRV_SUCCESS and on else
                                                          READBACK_MISMATCH if ret == DRV_SUCCESS else SENT)
        add(BaselineItem("cooler_on", True, code, on if ret == DRV_SUCCESS else None, outcome))
    return rep
