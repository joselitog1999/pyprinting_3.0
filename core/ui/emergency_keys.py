# -*- coding: utf-8 -*-
"""Teclas de la parada de emergencia y puente Qt (C-01 Ronda 4, R4-17 fase 4c; `ronda2_architecture.md` §4.3;
`ronda4_conciliacion_fase4c.md`; DEC-049).

- **`EmergencyKeyFilter`**: uno por proceso, instalado en la `QApplication`. Actúa sobre **toda** ventana del
  proceso, sin registro por ventana: una ventana nueva, un diálogo modal o el satélite de PyPrinting no quedan afuera
  ([DA] F-2). `F12` y `Ctrl+E` → `coordinator.trigger("tecla")`, una vez por pulsación: consume el
  `ShortcutOverride` y el `KeyPress` que lo sigue, e ignora la autorrepetición. `F2` → los manejadores de pausa
  (`add_pause_handler`); si ninguno la atiende, el evento sigue (el `QShortcut` de la traza la detiene, como hoy).
- **`EmergencyBridge`**: uno por proceso, en el hilo GUI. Convierte los avisos del cerrador (que llegan desde su
  hilo) y del coordinador en señales Qt; vigila el plazo de confirmación del banner y consulta el rearme cada
  100 ms durante `ESTOP_QUIESCENCE_TIMEOUT_S`. **Nunca abre un modal.**
"""
from __future__ import annotations

import time
from typing import Callable, Optional

from PyQt6.QtCore import QEvent, QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import QApplication

from core import nidaq
from core.emergency_stop import ESTOP_QUIESCENCE_TIMEOUT_S, get_emergency_coordinator

ESTOP_KEYS = ((Qt.Key.Key_F12, Qt.KeyboardModifier.NoModifier),
              (Qt.Key.Key_E, Qt.KeyboardModifier.ControlModifier))
PAUSE_KEY = Qt.Key.Key_F2
CLOSE_CONFIRM_DEADLINE_S = 0.5      # 2 × ESTOP_LOCK_TIMEOUT_S (instrumentación §1.4): el banner no espera al cerrador
REARM_POLL_MS = 100
ESTOP_SOURCE_KEY = "tecla"

_TYPES = (QEvent.Type.ShortcutOverride, QEvent.Type.KeyPress)


def _mods(event):
    return event.modifiers() & ~Qt.KeyboardModifier.KeypadModifier


def is_estop_key(event) -> bool:
    return any(event.key() == k and _mods(event) == m for k, m in ESTOP_KEYS)


class EmergencyKeyFilter(QObject):
    def __init__(self, app: QApplication, coordinator):
        super().__init__(app)
        self._coordinator = coordinator
        self._pause_handlers: list[Callable[[], bool]] = []
        self._estop_armed = False
        self._pause_armed = False

    def add_pause_handler(self, fn: Callable[[], bool]) -> None:
        """`fn()` devuelve True si atendió `F2` (grilla corriendo → pausa); si no, el evento sigue su camino."""
        if fn not in self._pause_handlers:
            self._pause_handlers.append(fn)

    def remove_pause_handler(self, fn) -> None:
        if fn in self._pause_handlers:
            self._pause_handlers.remove(fn)

    def _pause(self) -> bool:
        for fn in list(self._pause_handlers):
            try:
                if fn():
                    return True
            except Exception as e:
                print(f"[Teclas] El manejador de F2 falló: {e}")
        return False

    def eventFilter(self, obj, event):
        t = event.type()
        if t not in _TYPES:
            return False
        if is_estop_key(event):
            if event.isAutoRepeat():
                return True                                  # mantener apretada no dispara de nuevo
            if t == QEvent.Type.ShortcutOverride:
                self._estop_armed = True
                event.accept()
                self._coordinator.trigger(ESTOP_SOURCE_KEY)
                return True
            if self._estop_armed:                            # el KeyPress de la misma pulsación
                self._estop_armed = False
                return True
            self._coordinator.trigger(ESTOP_SOURCE_KEY)
            return True
        if event.key() == PAUSE_KEY and _mods(event) == Qt.KeyboardModifier.NoModifier and not event.isAutoRepeat():
            if t == QEvent.Type.ShortcutOverride:
                if self._pause():
                    self._pause_armed = True
                    event.accept()
                    return True
                return False
            if self._pause_armed:
                self._pause_armed = False
                return True
            return self._pause()
        return False


def install_emergency_key_filter(app: Optional[QApplication] = None, coordinator=None,
                                 pause_handler: Optional[Callable[[], bool]] = None) -> EmergencyKeyFilter:
    """Idempotente: el primero que llega (PySpectrum o PyPrinting) lo instala; los demás sólo suman su manejador de
    `F2`. El filtro queda colgado de la aplicación, así hay uno solo aunque el módulo se importe con otro nombre."""
    app = app or QApplication.instance()
    flt = getattr(app, "_emergency_key_filter", None)
    if flt is None:
        flt = EmergencyKeyFilter(app, coordinator or get_emergency_coordinator())
        app.installEventFilter(flt)
        app._emergency_key_filter = flt
    if pause_handler is not None:
        flt.add_pause_handler(pause_handler)
    return flt


class EmergencyBridge(QObject):
    """Las señales de la parada para la interfaz, siempre entregadas en el hilo GUI."""
    stopTriggered = pyqtSignal(int, str, float)     # generación, fuente, hora de pared del disparo
    closeResult = pyqtSignal(object)                # nidaq.CloseResult
    deadlineExpired = pyqtSignal(int)               # la generación sin cierre confirmado a los 0.5 s
    rearmProgress = pyqtSignal(object)              # emergency_stop.RearmCheck
    rearmed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._coordinator = get_emergency_coordinator()
        self._confirmed_gens: set[int] = set()
        self._deadline = QTimer(self)
        self._deadline.setSingleShot(True)
        self._deadline.timeout.connect(self._on_deadline)
        self._deadline_gen = 0
        self._rearm_timer = QTimer(self)
        self._rearm_timer.setInterval(REARM_POLL_MS)
        self._rearm_timer.timeout.connect(self._poll_rearm)
        self._rearm_gen = 0
        self._rearm_t0 = 0.0
        # Los avisos pueden llegar desde el hilo cerrador o desde el que disparó: estas señales los traen al hilo
        # GUI (la conexión se resuelve al emitir: encolada si el que emite es otro hilo)
        self.stopTriggered.connect(self._arm_deadline)
        self.closeResult.connect(self._note_result)
        self.ensure_listening()

    def ensure_listening(self) -> None:
        """Registra los oyentes (idempotente): la suite los borra entre tests."""
        nidaq.register_close_listener(self._on_close_result)
        self._coordinator.add_listener(self._on_coordinator_event)

    # ── desde otros hilos ──
    def _on_close_result(self, result) -> None:
        self.closeResult.emit(result)

    def _on_coordinator_event(self, event: str, generation: int) -> None:
        if event == "stop":
            st = nidaq.get_emergency_state()
            self.stopTriggered.emit(int(generation), str(st.source), float(st.t_trigger_wall or time.time()))
        elif event == "rearmed":
            self.rearmed.emit(int(generation))

    # ── en el hilo GUI ──
    def _arm_deadline(self, generation: int, source: str, t_wall: float) -> None:
        self._deadline_gen = int(generation)
        self._deadline.start(int(CLOSE_CONFIRM_DEADLINE_S * 1000))

    def _note_result(self, result) -> None:
        if result.ok and result.estop_generation is not None:
            self._confirmed_gens.add(int(result.estop_generation))

    def _on_deadline(self) -> None:
        if self._deadline_gen not in self._confirmed_gens:
            self.deadlineExpired.emit(self._deadline_gen)

    def request_rearm(self, generation: int) -> None:
        """Rearmar en cuanto se pueda (cierre confirmado, nada abierto, todo quieto), consultando cada 100 ms durante
        el plazo de quietud. Cada consulta sale por `rearmProgress`."""
        self._rearm_gen = int(generation)
        self._rearm_t0 = time.monotonic()
        self._rearm_timer.start()
        self._poll_rearm()                                   # la primera consulta, ya (el timer se detiene solo)

    def _poll_rearm(self) -> None:
        gen = self._rearm_gen
        if not gen:
            self._rearm_timer.stop()
            return
        check = self._coordinator.rearm_check(gen)
        if check.ok:
            self._rearm_timer.stop()
            self._rearm_gen = 0
            ok, why = self._coordinator.rearm(gen)
            if not ok:
                self.rearmProgress.emit(check._replace(ok=False, reason=why))
            return
        if time.monotonic() - self._rearm_t0 > ESTOP_QUIESCENCE_TIMEOUT_S or not check.generation_current:
            self._rearm_timer.stop()
            self._rearm_gen = 0
            if check.waiting_on:
                check = check._replace(reason=f"La rutina no respondió en {ESTOP_QUIESCENCE_TIMEOUT_S:.0f} s: "
                                              f"{', '.join(check.waiting_on)}. Reiniciá PyPrinting.")
        self.rearmProgress.emit(check)

    def is_rearming(self) -> bool:
        return self._rearm_timer.isActive()


def get_emergency_bridge() -> EmergencyBridge:
    """El puente del proceso (en el hilo GUI, colgado de la aplicación)."""
    app = QApplication.instance()
    bridge = getattr(app, "_emergency_bridge", None)
    if bridge is None:
        bridge = EmergencyBridge(app)
        app._emergency_bridge = bridge
    else:
        bridge.ensure_listening()
    return bridge
