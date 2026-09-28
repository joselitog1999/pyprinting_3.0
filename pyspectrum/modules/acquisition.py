# -*- coding: utf-8 -*-
"""
acquisition.py — Una exposición = un cuadro nuevo, o una falla explícita (bloque A, paso 6, DEC-040)

Contrato de la Ronda 2 (`docs/evidence/auditoria_2026-09-27/pyspectrum_A_ronda2/`,
`software_architect.md` §6.3 e `instrumentation.md` §5.2), que reemplaza al patrón "StartAcquisition
y enseguida GetMostRecentImage" de las rutinas de 3.0: ese patrón leía un cuadro anterior a la
exposición, o un arreglo de ceros si la lectura fallaba (AND-1, C-10). Es el esquema del legado:
iniciar, esperar el cuadro, leer ese cuadro (R4-5).

1. `GetStatus` con el código crudo: una falla es `READ_FAILED`, nunca "terminó".
2. Modo single scan y exposición, con el retorno verificado.
3. Contador de cuadros antes, `StartAcquisition` verificado.
4. Espera en tramos (`WaitForAcquisitionTimeOut`): en cada tramo `on_tick()` (latido, progreso),
   `should_abort()` y la E-STOP. Tope total: exposición real + margen de lectura.
5. `GetAcquiredData` con el tamaño exacto: sólo éxito da datos; el contador tiene que avanzar 1.
6. En todo camino de salida la cámara queda sin adquirir.

No abre obturadores ni mueve nada: la rutina que la llama decide la luz (R4-C-3).
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Optional, Tuple, Union

import numpy as np

from pyspectrum.drivers.andor_ccd_driver import (
    ACQ_MODE_SINGLE_SCAN, DRV_ACQUIRING, DRV_IDLE, DRV_NO_NEW_DATA, DRV_SUCCESS,
)

# Tope de exposición por cuadro: 60 s (R4-B-9). La calibración usa 0.10 s (R4-D-4).
MAX_EXPOSURE_S = 60.0
MIN_EXPOSURE_S = 1e-4
# Tramo de espera: fija la latencia máxima de Stop / E-STOP (Ronda 2, instrumentation §5.2).
WAIT_TRANCHE_MS = 250
# Margen sobre la exposición real antes de declarar TIMEOUT. La lectura de un cuadro completo tarda
# ≈ 0.08 s (Ronda 1, instrumentation §4.2); el margen es provisorio hasta medirlo (BANCO-44).
READOUT_MARGIN_S = 2.0


class AcquisitionFailureKind(Enum):
    DEVICE_NOT_CONNECTED = "device_not_connected"
    INVALID_REQUEST = "invalid_request"
    NOT_IDLE = "not_idle"
    SETTER_REJECTED = "setter_rejected"
    START_FAILED = "start_failed"
    TIMEOUT = "timeout"
    USER_STOP = "user_stop"
    ESTOP = "estop"
    READ_FAILED = "read_failed"
    STALE_FRAME = "stale_frame"
    SIZE_MISMATCH = "size_mismatch"


@dataclass(frozen=True)
class ExposureRequest:
    exposure_s: float
    shape: Tuple[int, ...]       # (1004,) en FVB / Single-Track; (n, 1004) en tracks; (filas, 1004) en Image


@dataclass(frozen=True)
class Frame:
    data: np.ndarray
    exposure_s_actual: float      # GetAcquisitionTimings (NaN si no se pudo leer)
    frame_index: Optional[int]    # contador del SDK después de la adquisición (None si no hay contador)
    t_start: float                # reloj monotónico
    t_end: float


@dataclass(frozen=True)
class AcquisitionFailure:
    kind: AcquisitionFailureKind
    code: Optional[int]
    call: Optional[str]
    detail: str


def _default_estop() -> bool:
    try:
        from pyspectrum.modules.hardware_session import hardware_session
        return bool(hardware_session.is_emergency_stopped)
    except Exception:
        return False


def single_exposure(cam: Any, req: ExposureRequest, *,
                    should_abort: Callable[[], bool] = lambda: False,
                    on_tick: Callable[[], None] = lambda: None,
                    is_estopped: Callable[[], bool] = _default_estop,
                    clock: Callable[[], float] = time.monotonic,
                    tranche_ms: int = WAIT_TRANCHE_MS,
                    readout_margin_s: float = READOUT_MARGIN_S) -> Union[Frame, AcquisitionFailure]:
    """Toma exactamente un cuadro nuevo con `req.exposure_s`, o devuelve por qué no pudo."""
    def fail(kind, code=None, call=None, detail=""):
        return AcquisitionFailure(kind, code, call, detail)

    if not getattr(cam, "available", True):
        return fail(AcquisitionFailureKind.DEVICE_NOT_CONNECTED,
                    detail=getattr(cam, "unavailable_reason", "") or "La cámara no está conectada.")
    t_exp = float(req.exposure_s)
    if not (MIN_EXPOSURE_S <= t_exp <= MAX_EXPOSURE_S) or not req.shape or min(req.shape) <= 0:
        return fail(AcquisitionFailureKind.INVALID_REQUEST,
                    detail=f"exposición {t_exp} s fuera de [{MIN_EXPOSURE_S}, {MAX_EXPOSURE_S}] o forma {req.shape} inválida")

    ret, status = cam.get_status_checked()
    if ret != DRV_SUCCESS:
        return fail(AcquisitionFailureKind.READ_FAILED, ret, "GetStatus", "no se pudo consultar el estado de la cámara")
    if status == DRV_ACQUIRING:
        return fail(AcquisitionFailureKind.NOT_IDLE, status, "GetStatus",
                    "la cámara ya está adquiriendo (¿Live activo?)")

    for call, fn, arg in (("SetAcquisitionMode", cam.set_acquisition_mode, ACQ_MODE_SINGLE_SCAN),
                          ("SetExposureTime", cam.set_exposure_time, t_exp)):
        ret = fn(arg)
        if ret != DRV_SUCCESS:
            return fail(AcquisitionFailureKind.SETTER_REJECTED, ret, call, f"{call}({arg}) rechazado")

    ret, exp_actual, _acc, kin = cam.get_acquisition_timings()
    if ret != DRV_SUCCESS or not np.isfinite(exp_actual):
        exp_actual, kin = float("nan"), t_exp
    cycle_s = max(t_exp, kin if np.isfinite(kin) else t_exp,
                  exp_actual if np.isfinite(exp_actual) else t_exp)

    ret_n0, n0 = cam.get_total_number_images_acquired()
    n0 = n0 if ret_n0 == DRV_SUCCESS else None

    t_start = clock()
    ret = cam.start_acquisition()
    if ret != DRV_SUCCESS:
        return fail(AcquisitionFailureKind.START_FAILED, ret, "StartAcquisition", "la cámara no arrancó la exposición")

    deadline = t_start + cycle_s + float(readout_margin_s)
    finished = False
    try:
        while True:
            r = cam.wait_for_acquisition_timeout(int(tranche_ms))
            on_tick()
            if r == DRV_SUCCESS:
                finished = True
                break
            if should_abort():
                return fail(AcquisitionFailureKind.USER_STOP, None, None, "detenido por el operador")
            if is_estopped():
                return fail(AcquisitionFailureKind.ESTOP, None, None, "parada de emergencia")
            ret, status = cam.get_status_checked()
            if ret != DRV_SUCCESS:
                return fail(AcquisitionFailureKind.READ_FAILED, ret, "GetStatus", "falló la consulta de estado durante la espera")
            if status == DRV_IDLE:
                finished = True  # terminó sin que la espera capturara el evento
                break
            if status != DRV_ACQUIRING:
                return fail(AcquisitionFailureKind.READ_FAILED, status, "GetStatus", "estado inesperado durante la espera")
            if clock() > deadline:
                return fail(AcquisitionFailureKind.TIMEOUT, r, "WaitForAcquisitionTimeOut",
                            f"el cuadro no llegó en {cycle_s + readout_margin_s:.2f} s")

        n_pixels = int(np.prod(req.shape))
        ret, data = cam.get_acquired_data_checked(n_pixels)
        if ret == DRV_NO_NEW_DATA:
            return fail(AcquisitionFailureKind.STALE_FRAME, ret, "GetAcquiredData", "no hay un cuadro nuevo")
        if ret != DRV_SUCCESS or data is None:
            return fail(AcquisitionFailureKind.READ_FAILED, ret, "GetAcquiredData", "la lectura del cuadro falló")
        if data.size != n_pixels:
            return fail(AcquisitionFailureKind.SIZE_MISMATCH, None, "GetAcquiredData",
                        f"se esperaban {n_pixels} valores y llegaron {data.size}")
        ret_n1, n1 = cam.get_total_number_images_acquired()
        n1 = n1 if ret_n1 == DRV_SUCCESS else None
        if n0 is not None and n1 is not None and n1 != n0 + 1:
            return fail(AcquisitionFailureKind.STALE_FRAME, None, "GetTotalNumberImagesAcquired",
                        f"el contador pasó de {n0} a {n1}, no avanzó exactamente un cuadro")
        return Frame(np.asarray(data, dtype=np.float64).reshape(req.shape), exp_actual, n1, t_start, clock())
    finally:
        if not finished:
            try:
                ret, status = cam.get_status_checked()
                if ret != DRV_SUCCESS or status == DRV_ACQUIRING:
                    cam.abort_acquisition()
            except Exception:
                cam.abort_acquisition()
