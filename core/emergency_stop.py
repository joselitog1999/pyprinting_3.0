# -*- coding: utf-8 -*-
"""Coordinador de la parada de emergencia del proceso (C-01 Ronda 4, R4-17 fase 4; `ronda2_architecture.md` §4.2;
DEC-047).

Sin Qt y uno por proceso (`get_emergency_coordinator()`): es el mismo objeto con PyPrinting suelto, con PySpectrum
solo y en modo satélite, así hay **una** parada y **un** Rearmar por construcción.

- `trigger(fuente)`: la parada de `nidaq` (el evento, la época y el cerrador, sin candado), después las banderas de
  cada participante y después los oyentes (el puente Qt de la fase 4c). Idempotente.
- `rearm_check(gen)`: instantáneo. Lo consulta la GUI cada 100 ms durante `ESTOP_QUIESCENCE_TIMEOUT_S`.
- `rearm(gen)`: nunca llama a `pi.connect()` ni a `disconnect()`.

Contrato de un participante (`on_emergency_stop`): < 1 ms, sólo banderas; sin E/S, sin print, sin candados de
hardware. Lo que haga después lo hace su propio hilo, cuando consulte la bandera.
"""
from __future__ import annotations

import sys
import threading
from typing import Callable, NamedTuple, Protocol, runtime_checkable

# Un solo módulo con los dos nombres, como `core/nidaq.py`: un segundo coordinador sería una segunda parada.
if __name__ == "core.emergency_stop":
    sys.modules.setdefault("emergency_stop", sys.modules[__name__])
elif __name__ == "emergency_stop":
    sys.modules.setdefault("core.emergency_stop", sys.modules[__name__])

try:
    from core import nidaq
except ImportError:                                   # pragma: no cover — import por el nombre corto
    import nidaq                                      # type: ignore

ESTOP_QUIESCENCE_TIMEOUT_S = 12.0   # [INS] §1.7: el _move_z de 10 s del autofoco más un margen


@runtime_checkable
class EmergencyParticipant(Protocol):
    name: str

    def on_emergency_stop(self, generation: int) -> None: ...

    def is_quiescent(self) -> bool: ...

    def on_rearmed(self, generation: int) -> None: ...

    def is_running(self) -> bool: ...


class RearmCheck(NamedTuple):
    ok: bool
    closer_confirmed: bool       # un cierre del cerrador confirmado para esta generación
    nothing_open: bool           # ningún obturador abierto ni sin confirmar
    routines_quiescent: bool
    waiting_on: tuple            # los participantes que todavía no están quietos
    generation_current: bool
    reason: str


class EmergencyCoordinator:
    def __init__(self):
        self._lock = threading.Lock()          # hoja: sólo protege las listas
        self._participants: list = []
        self._listeners: list[Callable[[str, int], None]] = []

    # ── registro ──
    def register(self, participant) -> None:
        with self._lock:
            if participant not in self._participants:
                self._participants.append(participant)

    def unregister(self, participant) -> None:
        with self._lock:
            if participant in self._participants:
                self._participants.remove(participant)

    def participants(self) -> list:
        with self._lock:
            return list(self._participants)

    def add_listener(self, fn: Callable[[str, int], None]) -> None:
        """`fn(evento, generación)` con evento "stop" o "rearmed", en el hilo que disparó o rearmó."""
        with self._lock:
            if fn not in self._listeners:
                self._listeners.append(fn)

    def remove_listener(self, fn) -> None:
        with self._lock:
            if fn in self._listeners:
                self._listeners.remove(fn)

    # ── la parada ──
    def trigger(self, source: str) -> int:
        gen = nidaq.request_emergency_stop(source)
        for p in self.participants():
            try:
                p.on_emergency_stop(gen)
            except Exception:
                pass                                  # un participante roto no frena a los demás
        self._notify("stop", gen)
        return gen

    def operator_close_all(self, source: str = "Cerrar todos") -> int:
        hold = nidaq.OPERATOR_HOLD_S if self.any_routine_running() else 0.0
        return nidaq.request_close_all(nidaq.CloseCause.OPERATOR, source, hold_s=hold)

    def any_routine_running(self) -> bool:
        if nidaq.any_routine_running():
            return True
        for p in self.participants():
            try:
                if p.is_running():
                    return True
            except Exception:
                pass
        return False

    def state(self):
        return nidaq.get_emergency_state()

    # ── el rearme ──
    def rearm_check(self, generation: int) -> RearmCheck:
        st = nidaq.get_emergency_state()
        gen_ok = st.active and int(generation) == st.generation
        confirmed = bool(gen_ok and st.confirmed)
        nothing_open = not nidaq.get_open_shutter_names() and not nidaq.get_unconfirmed_shutters()
        waiting = []
        for p in self.participants():
            try:
                quiet = bool(p.is_quiescent())
            except Exception:
                quiet = False
            if not quiet:
                waiting.append(getattr(p, "name", type(p).__name__))
        quiescent = not waiting
        if not st.active:
            reason = "no hay una parada activa"
        elif not gen_ok:
            reason = "hubo otra parada después: rearmá la última"
        elif not confirmed:
            reason = ("la placa no confirmó el cierre: cortá la emisión con la llave del láser"
                      if st.lock_busy or st.last_result is not None else "esperando el cierre confirmado")
        elif not nothing_open:
            reason = "hay obturadores abiertos o sin confirmar"
        elif not quiescent:
            reason = "esperando que terminen: " + ", ".join(waiting)
        else:
            reason = ""
        ok = gen_ok and confirmed and nothing_open and quiescent
        return RearmCheck(ok, confirmed, nothing_open, quiescent, tuple(waiting), gen_ok, reason)

    def rearm(self, generation: int) -> tuple[bool, str]:
        check = self.rearm_check(generation)
        if not check.ok:
            return False, check.reason
        ok, why = nidaq.clear_emergency_stop(generation)
        if not ok:
            return False, why
        for p in self.participants():
            try:
                p.on_rearmed(generation)
            except Exception:
                pass
        self._notify("rearmed", generation)
        return True, ""

    def _notify(self, event: str, generation: int) -> None:
        with self._lock:
            listeners = list(self._listeners)
        for fn in listeners:
            try:
                fn(event, generation)
            except Exception:
                pass


_COORDINATOR: EmergencyCoordinator | None = None
_COORDINATOR_LOCK = threading.Lock()


def get_emergency_coordinator() -> EmergencyCoordinator:
    global _COORDINATOR
    with _COORDINATOR_LOCK:
        if _COORDINATOR is None:
            _COORDINATOR = EmergencyCoordinator()
        return _COORDINATOR
