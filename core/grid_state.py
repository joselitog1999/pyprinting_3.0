# -*- coding: utf-8 -*-
"""Estados de la grilla y política por causa de corte (C-01 Ronda 4, R4-17; `ronda2_architecture.md` §4.5-4.6, §5.4).

Sin Qt. La usa `modules/measurements.py` para decidir qué hace la grilla cuando un nodo en exposición termina sin
decisión del criterio ("interrupted"): por quién cortó, no por cómo se enteró el worker.

Fase 3 (DEC-046): `CAUSE_POLICY` y `NodeMeta`. Fase 4b (DEC-048): `compute_resume_index` y
`RESUME_REFOCUS_AFTER_S`; la máquina de estados (`run_state`) la lleva el worker con `GridRunState`.
"""
from __future__ import annotations

from enum import Enum
from typing import AbstractSet, Mapping, NamedTuple, Optional, Sequence


class GridRunState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    FINISHED = "finished"


class GridTransition(NamedTuple):
    run_state: GridRunState      # cómo queda la grilla
    continue_after_hold: bool    # sigue sola con el nodo siguiente cuando vence la retención de aperturas
    restore_now: bool            # un paso entre nodos cortado se restituye ya (fase 5)


# La causa de la Pausa: no es un cierre de `nidaq`, es la bandera de DEC-041
PAUSE_CAUSE = "pause"

# `gui_design_v2.md` §5.3, en el motor. Las claves son los valores de `core.nidaq.CloseCause` y la Pausa.
CAUSE_POLICY: Mapping[str, GridTransition] = {
    "operator": GridTransition(GridRunState.RUNNING, True, True),      # "Cerrar todos": la grilla sigue
    "estop": GridTransition(GridRunState.STOPPED, False, False),
    PAUSE_CAUSE: GridTransition(GridRunState.PAUSED, False, False),
    "watchdog": GridTransition(GridRunState.PAUSED, False, False),
    "interlock": GridTransition(GridRunState.PAUSED, False, False),
    "stage": GridTransition(GridRunState.PAUSED, False, False),
    "routine": GridTransition(GridRunState.PAUSED, False, False),
    "excepthook": GridTransition(GridRunState.PAUSED, False, False),
    "exit": GridTransition(GridRunState.PAUSED, False, False),
}
# Una causa que no está en la tabla queda del lado seguro
_SAFE_SIDE = GridTransition(GridRunState.PAUSED, False, False)


def policy_for(cause) -> GridTransition:
    key = getattr(cause, "value", cause)
    return CAUSE_POLICY.get(str(key), _SAFE_SIDE)


class NodeMeta(NamedTuple):
    """Lo que se sabe de un nodo que no terminó con una decisión del criterio."""
    cause: str            # quién cortó (`CloseCause`, "pause") o por qué no se abrió
    t_exposed_s: float    # tiempo con el obturador abierto (0 si no llegó a abrir)
    epoch: int            # la época de cierre que lo cortó
    attempt: int          # intento (pase principal = 0)
    review: bool          # True: expuesto sin decisión, lo decide el operador (regla P4)


INTERRUPTED = "interrupted"   # valor de `node_results`: expuesto sin decisión; el Healing Pass no lo toma

# [INV-R4] 4: si la grilla estuvo detenida o en pausa más que esto, antes del primer nodo se vuelve a enfocar (y,
# con corrección de deriva, se pasa por el ancla)
RESUME_REFOCUS_AFTER_S = 60.0


def compute_resume_index(order: Sequence[int], results: Mapping[int, str],
                         exposed: AbstractSet[tuple], attempt: Mapping[int, int]) -> Optional[int]:
    """El primer nodo de `order` que nunca se expuso en su intento vigente ([INV-R4] 4; respuestas 1 y 5 del
    investigador). Un nodo que llegó a abrir no se vuelve a exponer, tenga o no decisión: si la tiene, ya está;
    si no, quedó "interrupted" y en revisión. En el pase principal el intento es 0; en el Healing Pass, la cola es
    el orden y el intento es 1, así que su resultado "timeout" del pase principal no lo saltea. Devuelve None si
    no queda ninguno (el pase terminó)."""
    for i in order:
        a = int(attempt.get(i, 0))
        if (int(i), a) in exposed:
            continue
        if a == 0 and i in results:
            continue                  # decidido sin registro de apertura (p. ej. una grilla anterior a la fase 4b)
        return int(i)
    return None
