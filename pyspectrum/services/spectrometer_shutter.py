# -*- coding: utf-8 -*-
"""
spectrometer_shutter.py — Obturador del espectrómetro (decisión del investigador, 2026-09-29)

**Cuándo:** se abre a pedido del operador, en una rutina o en el Live; nunca al arrancar.

**Cómo, como el legado.** El único obturador está en el Shamrock (BANCO-22) y tiene dos caminos:
- la salida TTL de la cámara: `setup_shutter('open', 1)` para abrir y `setup_shutter('closed', 0)` para
  cerrar (`Camera_ps.py:645-663`, `StepandGlue_ps.py`);
- el comando USB `ShamrockSetShutter(device, 1 = abierto / 0 = cerrado)`. El legado lo llamaba una vez al
  arrancar (`PySpectrum_UNSAM.py:793`).

Como no se sabe cuál de los dos manda en el banco (BANCO-09), abrir acciona los dos (USB y después TTL) y
cerrar también (TTL y después USB). Cada código se verifica: un obturador que no confirma es una
afirmación metrológica falsa (DEC-014).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

_DRV_SUCCESS = 20002
_SHAMROCK_SUCCESS = 20202
_DEVICE = 0
CAMERA_SHUTTER_OPEN, CAMERA_SHUTTER_CLOSED = 1, 2      # set_shutter_mode: 0 auto, 1 open, 2 closed


@dataclass(frozen=True)
class ShutterResult:
    ok: bool
    detail: str
    codes: Tuple[Tuple[str, object], ...]


def _act(camera, spectrometer, open_: bool) -> ShutterResult:
    steps: List[Tuple[str, object]] = []
    problems: List[str] = []

    def shamrock():
        if spectrometer is None or not hasattr(spectrometer, "ShamrockSetShutter"):
            return
        try:
            ret = spectrometer.ShamrockSetShutter(_DEVICE, 1 if open_ else 0)
        except Exception as e:
            ret = f"excepción: {e}"
        steps.append(("ShamrockSetShutter", ret))
        if ret != _SHAMROCK_SUCCESS:
            problems.append(f"Shamrock (USB) devolvió {ret}")

    def camera_ttl():
        if camera is None or not hasattr(camera, "set_shutter_mode") or not getattr(camera, "available", True):
            return
        try:
            ret = camera.set_shutter_mode(CAMERA_SHUTTER_OPEN if open_ else CAMERA_SHUTTER_CLOSED)
        except Exception as e:
            ret = f"excepción: {e}"
        steps.append(("set_shutter_mode", ret))
        if ret != _DRV_SUCCESS:
            problems.append(f"cámara (TTL) devolvió {ret}")

    if open_:
        shamrock()
        camera_ttl()
    else:
        camera_ttl()
        shamrock()
    action = "apertura" if open_ else "cierre"
    if problems:
        return ShutterResult(False, f"El obturador del espectrómetro no confirmó la {action}: "
                                    + "; ".join(problems) + ".", tuple(steps))
    return ShutterResult(True, f"Obturador del espectrómetro: {action} confirmada.", tuple(steps))


def open_spectrometer_shutter(camera, spectrometer) -> ShutterResult:
    return _act(camera, spectrometer, True)


def close_spectrometer_shutter(camera, spectrometer) -> ShutterResult:
    return _act(camera, spectrometer, False)
