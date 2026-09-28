# -*- coding: utf-8 -*-
"""
specular_interlock.py — Condición especular compartida entre la cámara y el Shamrock (paso 7, DEC-040)

En condición especular la red refleja la luz hacia el detector sin dispersarla, así que toda la luz cae
en la imagen de la ranura. Los casos son:
- orden cero;
- la red espejo, posición 3 de la torreta. En el equipo es un espejo real, `Mirr` en BANCO-25;
- una λc tan chica que el orden cero entra al chip.

Esta es la red mínima de R2-inst §2.5, que vive en los drivers para que ningún widget, rutina ni
script la esquive:
- **Cámara:** `set_emccd_gain(g > 0)` se rechaza con DRV_P1INVALID si el estado es especular o
  desconocido. El estado desconocido cuenta como especular (falla cerrada, R2-inst §2.1-4).
- **Shamrock:** un movimiento a un destino especular se rechaza con SHAMROCK_P2INVALID, salvo que:
  - una relectura exitosa haya confirmado ganancia 0 hace menos de `GAIN_ZERO_CONFIRMATION_MAX_AGE_S`, o
  - el bloqueo ya esté armado, es decir, ya estamos en especular con la ganancia bloqueada.
- Tras un movimiento aceptado, el Shamrock publica la condición del destino. El servicio de orden cero
  la corrige con la relectura.

El umbral (D-07a) es (1 + SPECULAR_MARGIN_FRAC) · W/2, con W la ventana nominal de la red. BANCO-42
mide dónde aparece de verdad la imagen especular.

Este módulo no importa ningún driver en el nivel superior (evita el ciclo cámara ↔ Shamrock): la
ventana nominal se importa dentro de la función.
"""
from __future__ import annotations

import math
import threading
import time
from typing import Callable, Optional, Tuple

FIRST_ORDER = "first_order"
SPECULAR = "specular"
UNKNOWN = "unknown"

_DRV_SUCCESS = 20002          # Andor SDK2
_SHAMROCK_SUCCESS = 20202     # Shamrock SDK
_GRATING_MIRROR = 3

# Una relectura de ganancia 0 vale como confirmación durante este tiempo. El servicio de orden cero
# relee justo antes de girar (Z4 → Z7), así que alcanza con pocos segundos.
GAIN_ZERO_CONFIRMATION_MAX_AGE_S = 5.0


def _margin_frac() -> float:
    try:
        from config import SPECULAR_MARGIN_FRAC
        return float(SPECULAR_MARGIN_FRAC)
    except Exception:
        return 0.10


def specular_threshold_nm(grating: int) -> float:
    """|λc| por debajo de este valor es especular con esa red. Infinito para el espejo."""
    if int(grating) == _GRATING_MIRROR:
        return math.inf
    from pyspectrum.drivers.shamrock_driver import NOMINAL_DISPERSION_NM_PER_MM, nominal_window_nm
    if int(grating) not in NOMINAL_DISPERSION_NM_PER_MM:
        # nominal_window_nm cae a la red de 150 para una red desconocida; acá eso no vale
        raise ValueError(f"red {grating} desconocida")
    return (1.0 + _margin_frac()) * nominal_window_nm(int(grating)) / 2.0


def classify(grating: Optional[int], wavelength_nm: Optional[float]) -> str:
    """Condición de una configuración (red, λc). Datos faltantes o red desconocida → UNKNOWN."""
    if grating is None or wavelength_nm is None:
        return UNKNOWN
    try:
        g, wl = int(grating), float(wavelength_nm)
    except (TypeError, ValueError):
        return UNKNOWN
    if not math.isfinite(wl):
        return UNKNOWN
    if g == _GRATING_MIRROR:
        return SPECULAR
    try:
        threshold = specular_threshold_nm(g)
    except Exception:
        return UNKNOWN          # red que el driver no conoce
    return SPECULAR if abs(wl) < threshold else FIRST_ORDER


def classify_reading(grating_reading: Tuple[int, int], wavelength_reading: Tuple[int, float],
                     at_zero_order: Optional[Tuple[int, int]] = None) -> str:
    """Clasifica lecturas `(ret, valor)` del Shamrock. Una lectura fallida → UNKNOWN."""
    ret_g, g = grating_reading
    ret_w, wl = wavelength_reading
    if ret_g != _SHAMROCK_SUCCESS or ret_w != _SHAMROCK_SUCCESS:
        return UNKNOWN
    if at_zero_order is not None and at_zero_order[0] == _SHAMROCK_SUCCESS and at_zero_order[1]:
        return SPECULAR
    return classify(g, wl)


class SpecularInterlock:
    """Estado compartido, protegido por lock. Lo escriben el Shamrock y el servicio; lo lee la cámara."""

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._lock = threading.Lock()
        self._clock = clock
        self._mode = UNKNOWN
        self._detail = "todavía no se leyó el estado del Shamrock"
        self._gain_zero_at: Optional[float] = None

    # ── Condición del espectrógrafo ──
    def publish(self, mode: str, detail: str = "") -> None:
        if mode not in (FIRST_ORDER, SPECULAR, UNKNOWN):
            mode = UNKNOWN
        with self._lock:
            self._mode, self._detail = mode, detail

    @property
    def mode(self) -> str:
        with self._lock:
            return self._mode

    @property
    def detail(self) -> str:
        with self._lock:
            return self._detail

    def is_specular_or_unknown(self) -> bool:
        return self.mode != FIRST_ORDER

    # ── Ganancia EM ──
    def gain_allowed(self, gain: int) -> bool:
        return int(gain) <= 0 or self.mode == FIRST_ORDER

    def note_gain_set(self, ret: int, gain: int) -> None:
        """Una ganancia > 0 aceptada invalida la confirmación de ganancia 0."""
        if ret == _DRV_SUCCESS and int(gain) > 0:
            with self._lock:
                self._gain_zero_at = None

    def note_gain_reading(self, ret: int, gain: int) -> None:
        with self._lock:
            ok_zero = ret == _DRV_SUCCESS and int(gain) == 0
            self._gain_zero_at = self._clock() if ok_zero else None

    def gain_confirmed_zero(self) -> bool:
        with self._lock:
            t = self._gain_zero_at
            return t is not None and (self._clock() - t) <= GAIN_ZERO_CONFIRMATION_MAX_AGE_S

    # ── Movimiento del Shamrock ──
    def move_allowed(self, destination_mode: str) -> bool:
        if destination_mode == FIRST_ORDER:
            return True
        return self.gain_confirmed_zero() or self.mode == SPECULAR


_INTERLOCK = SpecularInterlock()


def get_interlock() -> SpecularInterlock:
    return _INTERLOCK
