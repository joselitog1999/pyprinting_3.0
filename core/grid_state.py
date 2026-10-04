# -*- coding: utf-8 -*-
"""Estados de la grilla y política por causa de corte (C-01 Ronda 4, R4-17; `ronda2_architecture.md` §4.5-4.6, §5.4).

Sin Qt. La usa `modules/measurements.py` para decidir qué hace la grilla cuando un nodo en exposición termina sin
decisión del criterio ("interrupted"): por quién cortó, no por cómo se enteró el worker.

Fase 3 (DEC-046): `CAUSE_POLICY` y `NodeMeta`. La máquina de estados completa (`run_state`, Rearmar) y
`compute_resume_index` son de la fase 4.
"""
from __future__ import annotations

from enum import Enum
from typing import Mapping, NamedTuple


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
