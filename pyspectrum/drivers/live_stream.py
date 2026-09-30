# -*- coding: utf-8 -*-
"""
live_stream.py — El contrato del Live de la cámara (paquete 1 de R4-M, DEC-040)

Un Live es una adquisición continua de la que se muestra el cuadro más nuevo. El contrato lo cumplen:
- `PylablibAndorCCD`, la cámara del banco (R4-F). Lee con el contador de cuadros de pylablib:
  sólo el más nuevo, avanzando el puntero, con su índice y separando los cuadros que no se mostraron de
  los que pisó el búfer.
- `live_api(camera)`, un adaptador para el simulador (SAFE_MODE) y el driver ctypes propio, que no tienen
  contador de cuadros: arranca en "run till abort" y lee `get_most_recent_image`.

Métodos del contrato: `start_live() -> código`, `stop_live() -> código`, `live_active` y
`read_live_frame() -> LiveFrame | None` (`None`: no llegó un cuadro nuevo; `LiveStopped`: la cámara no
está en Live).
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

_DRV_SUCCESS = 20002
_DRV_ACQUIRING = 20072
_ACQ_MODE_RUN_TILL_ABORT = 5


class LiveStopped(RuntimeError):
    """La cámara no está en Live: se detuvo, alguien abortó la adquisición o el Live no arrancó."""


@dataclass(frozen=True)
class LiveFrame:
    """Un cuadro del Live.

    - `index`: índice del cuadro desde el arranque. Con el SDK2, pylablib no trae marca de tiempo del
      equipo: `t_host` es el reloj de la PC al leer.
    - `not_shown`: cuadros nuevos que se saltearon en esta lectura, porque sólo se muestra el último.
    - `lost_total`: cuadros que el búfer pisó sin que se leyeran, desde el último (re)arranque.
    - `buffer_fill`: cuadros sin leer / tamaño del búfer, después de esta lectura.
    """
    data: np.ndarray
    index: int
    t_host: float
    not_shown: int = 0
    lost_total: int = 0
    buffer_fill: float = 0.0


class _SdkLiveAdapter:
    """El contrato del Live sobre `start_acquisition` / `get_most_recent_image` (simulador, ctypes)."""

    def __init__(self, camera):
        self._camera = camera
        self._lock = threading.RLock()
        self._active = False
        self._index = -1

    @property
    def live_active(self) -> bool:
        return self._active

    def start_live(self) -> int:
        cam = self._camera
        with self._lock:
            if self._active:
                return _DRV_ACQUIRING
            cam.abort_acquisition()
            if hasattr(cam, "set_acquisition_mode"):
                code = cam.set_acquisition_mode(_ACQ_MODE_RUN_TILL_ABORT)
                if code != _DRV_SUCCESS:
                    return code
            code = cam.start_acquisition()
            if code == _DRV_SUCCESS:
                self._active, self._index = True, -1
            return code

    def stop_live(self) -> int:
        with self._lock:
            if not self._active:
                return _DRV_SUCCESS
            self._active = False
            return self._camera.abort_acquisition()

    def read_live_frame(self) -> Optional[LiveFrame]:
        with self._lock:
            if not self._active:
                raise LiveStopped("el Live no está activo")
            try:
                frame = self._camera.get_most_recent_image()
            except Exception as exc:
                if type(exc).__name__ == "FrameNotReady":
                    return None
                raise
            self._index += 1
            return LiveFrame(np.asarray(frame, dtype=np.float32), self._index, time.monotonic())


def live_api(camera: Any):
    """La cámara misma si cumple el contrato del Live; si no, su adaptador (uno solo por cámara, para
    que dos Live no se pisen). Se mira la clase, no la instancia: un envoltorio con `__getattr__` (los
    espías de los tests) no cumple el contrato por responder a cualquier nombre."""
    if callable(getattr(type(camera), "read_live_frame", None)):
        return camera
    adapter = getattr(camera, "__dict__", {}).get("_live_adapter")
    if not isinstance(adapter, _SdkLiveAdapter):
        adapter = _SdkLiveAdapter(camera)
        camera._live_adapter = adapter
    return adapter
