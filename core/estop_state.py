# -*- coding: utf-8 -*-
"""Estado de la parada de emergencia del proceso (C-01 Ronda 4, R4-17 fase 4; DEC-047).

Módulo hoja: no importa `config` ni `nidaq`, así lo pueden leer los dos sin ciclo (`config.py` lo consulta para
retener los movimientos de la platina; `core/nidaq.py` para rechazar las aperturas). Es uno por proceso: con
PyPrinting en modo satélite, PySpectrum y PyPrinting ven la misma parada.

- La **autoridad es el `Event`**: `is_active()` lo lee sin candado. Nadie espera un candado de hardware para saber
  que hay una parada.
- `_state_lock` es una hoja: se toma sólo para asignar los campos, nunca con E/S ni con otro candado adentro.
- `trip()` es idempotente: con la parada activa no cambia la generación, la hora ni la fuente (tres pulsaciones son
  un solo episodio, con la hora de la primera).
"""
from __future__ import annotations

import sys
import threading
import time
from typing import NamedTuple, Optional

# Un solo módulo con los dos nombres (como `core/nidaq.py`): `core/` también está en `sys.path`, y un
# `import estop_state` corto crearía una segunda parada, que nadie más vería.
if __name__ == "core.estop_state":
    sys.modules.setdefault("estop_state", sys.modules[__name__])
elif __name__ == "estop_state":
    sys.modules.setdefault("core.estop_state", sys.modules[__name__])


class EStopSnapshot(NamedTuple):
    active: bool
    generation: int
    source: str
    t_trigger_mono: Optional[float]
    t_trigger_wall: Optional[float]


_active = threading.Event()
_state_lock = threading.Lock()
_generation = 0
_source = ""
_t0_mono: Optional[float] = None
_t0_wall: Optional[float] = None


def trip(source: str) -> tuple[int, bool]:
    """Activa la parada. Devuelve (generación, nueva): `nueva` es False si ya estaba activa. El `Event` se pone
    PRIMERO: desde ese instante toda apertura y todo movimiento se rechazan."""
    global _generation, _source, _t0_mono, _t0_wall
    with _state_lock:
        if _active.is_set():
            return _generation, False
        _active.set()
        _generation += 1
        _source = str(source)
        _t0_mono = time.monotonic()
        _t0_wall = time.time()
        return _generation, True


def is_active() -> bool:
    return _active.is_set()


def generation() -> int:
    return _generation


def snapshot() -> EStopSnapshot:
    with _state_lock:
        return EStopSnapshot(_active.is_set(), _generation, _source, _t0_mono, _t0_wall)


def clear(gen: int) -> bool:
    """Levanta la parada sólo si `gen` es la generación vigente (un rearme de un episodio viejo no levanta uno
    nuevo)."""
    with _state_lock:
        if not _active.is_set() or int(gen) != _generation:
            return False
        _active.clear()
        return True


def _reset_for_tests() -> None:
    """Sólo para la suite: deja el proceso sin parada (la generación sigue creciendo)."""
    global _source, _t0_mono, _t0_wall
    with _state_lock:
        _active.clear()
        _source = ""
        _t0_mono = _t0_wall = None
