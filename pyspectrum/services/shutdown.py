# -*- coding: utf-8 -*-
"""Orden de cierre de PySpectrum (paso 13 del bloque A, DEC-040; R2-arq §3.3; R3-gui §1.13; R4-B 6).

Una sola confirmación del operador y una secuencia en la que **ninguna espera es infinita**:

1. E-STOP: obturadores, cámara abortada, ganancia EM 0 releída.
2. Rutinas y workers de PySpectrum, cada uno detenido en su hilo mientras el hilo vive.
3. Satélites huéspedes: se liberan con sus hilos vivos, después se terminan sus hilos y por último se
   cierra la ventana sin preguntar. Es la inversión del orden viejo, que causaba el deadlock V3.
4. Obturadores otra vez, con el cierre confirmado. No confirmado = abierto (DEC-036).
5. Obturador del espectrómetro, Shamrock y cámara, en ese orden (R2-arq §3.3-6; lo confirma BANCO-23).
6. Espejo de detección abajo, como el legado (`Shutters_ps.py:201`; decisión del investigador del
   2026-09-29), **sólo** si el paso 4 confirmó: abajo manda la luz al espectrómetro.
7. Platina a `config.PI_HOME_POS` (R4-B 6), **sólo** si el paso 4 confirmó. Así, al volver a conectarse,
   no se mueve.

Una falla se registra y el cierre sigue: el informe dice qué no se confirmó.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence, Tuple

THREAD_WAIT_MS = 3000
STAGE_PARK_TIMEOUT_S = 5.0
STAGE_PARK_TOLERANCE_UM = 0.1


@dataclass(frozen=True)
class ShutdownStep:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class ShutdownReport:
    steps: List[ShutdownStep] = field(default_factory=list)

    def add(self, step: ShutdownStep) -> None:
        self.steps.append(step)

    @property
    def problems(self) -> List[ShutdownStep]:
        return [s for s in self.steps if not s.ok]

    def summary(self) -> str:
        if not self.problems:
            return "Cierre completo: todo confirmado."
        return "\n".join(f"• {s.name}: {s.detail}" for s in self.problems)


@dataclass
class GuestHandle:
    """Un satélite abierto desde PySpectrum. `release` corre con sus hilos vivos (R2-arq §3.1)."""
    name: str
    release: Callable[[], object]
    threads: Sequence
    close_from_host: Callable[[], None]


def closing_question_text(home_pos: Sequence[float], guests: Sequence[str], extra: Sequence[str] = ()) -> str:
    """Texto de la única pregunta de cierre (R3-gui §1.13). La posición sale de config, no de un literal."""
    x, y, z = (f"{float(v):g}" for v in home_pos)
    text = (f"Se cierran todos los obturadores, la platina va a ({x}, {y}, {z}) µm y la cámara se cierra: "
            f"el enfriador deja de enfriar.")
    for name in guests:
        text += f"\n\n{name} (abierto desde aquí) también se cierra, sin mover la platina."
    for line in extra:
        text += f"\n\n{line}"
    return text


def _alive(thread) -> bool:
    try:
        return thread is not None and bool(thread.isRunning())
    except RuntimeError:          # el QThread de C++ ya se destruyó
        return False


def stop_in_thread(obj, method: str, thread, name: str) -> ShutdownStep:
    """Invoca `obj.method()` en su hilo, bloqueando, sólo si ese hilo corre. Nunca hacia un hilo muerto:
    una llamada bloqueante a un hilo sin bucle de eventos no vuelve (V3)."""
    from PyQt6 import QtCore
    if not _alive(thread):
        return ShutdownStep(name, True, "el hilo no corre: no se invoca")
    if thread is QtCore.QThread.currentThread():
        getattr(obj, method)()
    else:
        QtCore.QMetaObject.invokeMethod(obj, method, QtCore.Qt.ConnectionType.BlockingQueuedConnection)
    return ShutdownStep(name, True, "detenido en su hilo")


def thread_label(thread, index: int = 0) -> str:
    """Nombre legible de un hilo para el informe: su objectName, o su posición."""
    try:
        label = thread.objectName() if callable(getattr(thread, "objectName", None)) else ""
    except RuntimeError:
        label = ""
    return label or str(getattr(thread, "name", "") or f"n.º {index + 1}")


def quit_thread(thread, name: str, timeout_ms: int = THREAD_WAIT_MS) -> ShutdownStep:
    if not _alive(thread):
        return ShutdownStep(name, True, "el hilo ya había terminado")
    thread.quit()
    if thread.wait(timeout_ms):
        return ShutdownStep(name, True, "hilo terminado")
    return ShutdownStep(name, False, f"el hilo {name} no terminó en {timeout_ms / 1000:g} s")


def park_stage(stage, home_pos: Sequence[float], *, timeout_s: float = STAGE_PARK_TIMEOUT_S,
               tolerance_um: float = STAGE_PARK_TOLERANCE_UM, poll_s: float = 0.02,
               clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep) -> ShutdownStep:
    """Lleva la platina a `home_pos` y espera on-target con tope. No conecta ni desconecta (DEC-036)."""
    name = "platina"
    if not bool(getattr(stage, "connected", False)):
        return ShutdownStep(name, True, "no conectada: no se movió")
    target = [float(v) for v in home_pos]
    try:
        if stage.MOV([1, 2, 3], target) is False:
            return ShutdownStep(name, False, f"la platina rechazó el movimiento a {tuple(target)} µm")
        t_end = clock() + timeout_s
        while not all(stage.qONT([1, 2, 3]).values()):
            if clock() >= t_end:
                return ShutdownStep(name, False, f"no confirmó on-target en {timeout_s:g} s")
            sleep(poll_s)
        pos = stage.qPOS()
        read = [float(pos.get(str(a), pos.get(a))) for a in (1, 2, 3)]
    except Exception as e:
        return ShutdownStep(name, False, f"error al llevarla a {tuple(target)} µm: {e}")
    off = max(abs(r - t) for r, t in zip(read, target))
    if off > tolerance_um:
        return ShutdownStep(name, False, f"quedó en {tuple(round(r, 3) for r in read)} µm, a {off:.3f} µm de {tuple(target)}")
    return ShutdownStep(name, True, f"en {tuple(target)} µm")


def _as_steps(name: str, result) -> List[ShutdownStep]:
    if isinstance(result, ShutdownStep):
        return [result]
    if isinstance(result, (list, tuple)) and all(isinstance(r, ShutdownStep) for r in result) and result:
        return list(result)
    problems = getattr(result, "problems", None)
    if problems:
        return [ShutdownStep(name, False, "; ".join(str(p) for p in problems))]
    return [ShutdownStep(name, True, "")]


class ShutdownCoordinator:
    def __init__(self, *, estop: Callable[[], object],
                 routines: Sequence[Tuple[str, Callable[[], object]]],
                 guests: Sequence[GuestHandle],
                 close_shutters: Callable[[], bool],
                 devices: Sequence[Tuple[str, Callable[[], object]]],
                 park: Optional[Callable[[], ShutdownStep]],
                 mirror: Optional[Callable[[], object]] = None,
                 thread_timeout_ms: int = THREAD_WAIT_MS):
        self._estop = estop
        self._routines = list(routines)
        self._guests = list(guests)
        self._close_shutters = close_shutters
        self._devices = list(devices)
        self._park = park
        self._mirror = mirror
        self._thread_timeout_ms = thread_timeout_ms

    def _run(self, report: ShutdownReport, name: str, fn: Callable[[], object]) -> None:
        try:
            for step in _as_steps(name, fn()):
                report.add(step)
        except Exception as e:
            report.add(ShutdownStep(name, False, f"error: {e}"))

    def run(self) -> ShutdownReport:
        report = ShutdownReport()
        self._run(report, "E-STOP", self._estop)
        for name, fn in self._routines:
            self._run(report, name, fn)
        for g in self._guests:
            self._run(report, g.name, g.release)
            for i, t in enumerate(g.threads):
                label = f"{thread_label(t, i)} de {g.name}"
                self._run(report, f"hilo {label}", lambda t=t, label=label: quit_thread(t, label, self._thread_timeout_ms))
            self._run(report, f"ventana de {g.name}", g.close_from_host)
        try:
            shutters_ok = bool(self._close_shutters())
            report.add(ShutdownStep("obturadores", shutters_ok,
                                    "cerrados, confirmado" if shutters_ok else "CIERRE NO CONFIRMADO: cuenta como abierto"))
        except Exception as e:
            shutters_ok = False
            report.add(ShutdownStep("obturadores", False, f"error al cerrarlos: {e}"))
        for name, fn in self._devices:
            self._run(report, name, fn)
        if self._mirror is not None:
            if shutters_ok:
                self._run(report, "espejo de detección", self._mirror)
            else:
                report.add(ShutdownStep("espejo de detección", False,
                                        "no se bajó: los obturadores no confirmaron el cierre (DEC-036)"))
        if self._park is not None:
            if shutters_ok:
                self._run(report, "platina", self._park)
            else:
                report.add(ShutdownStep("platina", False,
                                        "no se movió: los obturadores no confirmaron el cierre (DEC-036)"))
        for s in report.problems:
            print(f"[Cierre] {s.name}: {s.detail}")
        return report
