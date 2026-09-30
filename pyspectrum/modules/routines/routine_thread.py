# -*- coding: utf-8 -*-
"""Una rutina de grilla en su propio hilo (AND-1; R4-K, P1).

`RoutineThread` hace lo común a crecimiento, luminiscencia y dímeros:
- toma la sesión y registra la posición del espejo que confirmó el operador (R4-K, P2);
- abre el obturador del espectrómetro si la rutina mide espectros (R4-H-2);
- corre el cuerpo de la rutina en un `QThread` con un `GridRunner`, así la GUI y el E-STOP siguen
  respondiendo durante una exposición (R4-K, P1);
- expone Stop, pausa, seguir y "siguiente" como eventos seguros entre hilos;
- al terminar, pase lo que pase: cierra los láseres de la rutina y el obturador del espectrómetro,
  devuelve el espejo a donde lo confirmó el operador (salvo con E-STOP), suelta la sesión y avisa.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, Optional

from PyQt6 import QtCore
from PyQt6.QtCore import pyqtSignal, pyqtSlot

from pyspectrum.modules.routines.grid_runner import GridAbort, GridRunner, GridSafetyPause


class RoutineControl:
    """Eventos que la GUI toca y el hilo de la rutina lee."""

    def __init__(self):
        self.stop = threading.Event()
        self.pause = threading.Event()
        self.skip = threading.Event()

    def should_abort(self) -> bool:
        return self.stop.is_set()

    def wait_while_paused(self, runner: GridRunner, on_paused: Optional[Callable[[], None]] = None) -> None:
        """En pausa no hay láseres de la rutina abiertos (R4-K, P7); Stop y E-STOP la cortan."""
        notified = False
        while self.pause.is_set():
            if not notified and on_paused is not None:
                on_paused()
                notified = True
            runner.check()
            time.sleep(0.05)

    def take_skip(self) -> bool:
        if self.skip.is_set():
            self.skip.clear()
            return True
        return False


class _Worker(QtCore.QObject):
    finished = pyqtSignal(str)

    def __init__(self, body, runner, ctl, cleanup):
        super().__init__()
        self.body, self.runner, self.ctl, self.cleanup = body, runner, ctl, cleanup

    @pyqtSlot()
    def run(self):
        outcome = "done"
        try:
            outcome = self.body(self.runner, self.ctl) or "done"
        except GridAbort:
            outcome = "aborted"
        except GridSafetyPause as e:
            outcome = f"safety: {e}"
        except Exception as e:                        # nunca un hilo que muere con un láser abierto
            outcome = f"error: {e}"
            try:
                self.runner.hw.close_all_shutters()
            except Exception:
                pass
        finally:
            try:
                self.cleanup(self.runner)
            finally:
                self.finished.emit(outcome)


class RoutineThread(QtCore.QObject):
    finished = pyqtSignal(str)

    def __init__(self, session_name: str, parent=None):
        super().__init__(parent)
        self.session_name = session_name
        self.ctl = RoutineControl()
        self._thread: Optional[QtCore.QThread] = None
        self._worker: Optional[_Worker] = None
        self._mirror: Optional[str] = None
        self._spec_shutter = False
        self._camera = self._spectrometer = None
        self.last_outcome: Optional[str] = None

    @property
    def running(self) -> bool:
        return self._thread is not None

    def start(self, body: Callable[[GridRunner, RoutineControl], Optional[str]], *, camera, spectrometer,
              mirror: Optional[str], needs_spectrometer: bool = True, require_mirror: bool = True,
              restore_mirror: bool = True, runner_kwargs: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Arranca la rutina. Devuelve None si arrancó, o el motivo por el que no."""
        from core.nidaq import confirm_detection_mirror_belief
        from pyspectrum.modules.hardware_session import hardware_session
        from pyspectrum.services.spectrometer_shutter import open_spectrometer_shutter
        if self._thread is not None:
            return "La rutina ya está corriendo."
        if require_mirror and mirror not in ("up", "down"):
            return "Confirmá dónde está el espejo de detección antes de iniciar (R4-K)."
        if not hardware_session.acquire_session(self.session_name):
            return "El hardware está ocupado o la E-STOP está activa."
        if mirror in ("up", "down"):
            confirm_detection_mirror_belief(mirror)
        else:
            mirror = None                     # una rutina que no mueve el espejo no lo devuelve
        self._mirror, self._camera, self._spectrometer = mirror, camera, spectrometer
        self._restore_mirror = bool(restore_mirror)
        self._spec_shutter = False
        if needs_spectrometer:
            res = open_spectrometer_shutter(camera, spectrometer)
            if not res.ok:
                hardware_session.release_session(self.session_name)
                return f"El obturador del espectrómetro no abrió: {res.detail}"
            self._spec_shutter = True
        self.ctl = RoutineControl()
        runner = GridRunner(camera, should_abort=self.ctl.should_abort, **(runner_kwargs or {}))
        self._thread = QtCore.QThread()
        self._worker = _Worker(body, runner, self.ctl, self._cleanup)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_finished)
        self._thread.start()
        return None

    def _cleanup(self, runner: GridRunner) -> None:
        """En el hilo de la rutina, pase lo que pase."""
        from pyspectrum.modules.hardware_session import hardware_session
        from pyspectrum.services.spectrometer_shutter import close_spectrometer_shutter
        try:
            if not runner.close_lasers():
                runner.hw.close_all_shutters()
        except Exception:
            pass
        if self._spec_shutter:
            try:
                close_spectrometer_shutter(self._camera, self._spectrometer)
            except Exception:
                pass
        if self._mirror and self._restore_mirror and not hardware_session.is_emergency_stopped:
            try:
                runner.hw.flipper_notch532(self._mirror)
            except Exception:
                pass

    @pyqtSlot(str)
    def _on_finished(self, outcome: str):
        from pyspectrum.modules.hardware_session import hardware_session
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(3000)
        self._thread, self._worker = None, None
        hardware_session.release_session(self.session_name)
        self.last_outcome = outcome
        if outcome != "done":
            print(f"[{self.session_name}] terminó: {outcome}")
        self.finished.emit(outcome)

    # ── controles (desde la GUI) ──
    def stop(self):
        self.ctl.stop.set()
        self.ctl.pause.clear()

    def pause(self):
        self.ctl.pause.set()

    def resume(self):
        self.ctl.pause.clear()

    def skip(self):
        self.ctl.skip.set()

    def shutdown(self, timeout_ms: int = 3000):
        from pyspectrum.services.shutdown import ShutdownStep
        self.stop()
        if self._thread is None:
            return ShutdownStep(self.session_name, True, "sin rutina en curso")
        ok = self._thread.wait(timeout_ms)
        return ShutdownStep(self.session_name, bool(ok), "detenida" if ok else
                            f"el hilo de {self.session_name} no terminó en {timeout_ms / 1000:g} s")

    def wait_finished(self, timeout_s: float = 10.0) -> bool:
        """Para tests y el cierre: procesa eventos hasta que la rutina termine."""
        from PyQt6.QtWidgets import QApplication
        t_end = time.monotonic() + timeout_s
        while self._thread is not None and time.monotonic() < t_end:
            QApplication.processEvents()
            time.sleep(0.005)
        QApplication.processEvents()
        return self._thread is None


# ── confirmación del espejo en la GUI (R4-K, P2) ──
def mirror_combo():
    from PyQt6 import QtWidgets
    c = QtWidgets.QComboBox()
    c.addItems(["— confirmá dónde está —", "abajo (espectrómetro)", "arriba (confocal / cámara)"])
    c.setToolTip("El espejo de detección no tiene sensor: confirmá dónde está ahora. La rutina lo mueve sola "
                 "según la fase y al terminar lo devuelve a esta posición (R4-K).")
    return c


def mirror_choice(combo):
    return {1: "down", 2: "up"}.get(combo.currentIndex())
