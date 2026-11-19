# -*- coding: utf-8 -*-
"""
hardware_session.py — Gestor Central de Sesión y Arbitraje de Hardware
PySpectrum 3.0 — UNSAM Nanofotónica
"""
from __future__ import annotations
import threading
import time
from typing import Callable, Optional, Dict, Any
from PyQt6 import QtCore
from PyQt6.QtCore import pyqtSignal, pyqtSlot, QObject, QMetaObject, Qt, QThread

from core.nidaq import close_all_shutters
from core import estop_state as _estop_state

# La grilla de PyPrinting, en modo satélite, toma la sesión con un nombre que empieza así (R4-17 fase 4c)
PYPRINTING_OWNER_PREFIX = "PyPrinting"
from pyspectrum.drivers.andor_ccd_driver import get_andor_ccd
from pyspectrum.drivers.shamrock_driver import get_shamrock


class HardwareSessionManager(QObject):
    """
    Árbitro central de hardware exclusivo (Patrón Exclusive Lease).
    Evita colisiones entre modos Live (cámara y Raman) y rutinas de medición
    (Step & Glue, Mapeo Confocal, Fotoluminiscencia, Cinética, Dímeros, Calibraciones).
    """

    sessionChangedSignal = pyqtSignal(str, bool)  # (owner_name, is_busy)
    emergencyStopSignal = pyqtSignal()
    statusWarningSignal = pyqtSignal(str)

    _instance: Optional[HardwareSessionManager] = None
    _lock = threading.RLock()

    @classmethod
    def get_instance(cls) -> HardwareSessionManager:
        with cls._lock:
            if cls._instance is None:
                cls._instance = HardwareSessionManager()
            return cls._instance

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_owner: str = ""
        self._is_busy: bool = False
        self._emergency_active: bool = False
        self._live_pause_callbacks: Dict[str, Callable[[], None]] = {}
        self._live_resume_callbacks: Dict[str, Callable[[], None]] = {}
        self._auto_paused_sources: list[str] = []
        self.last_estop_report: Dict[str, str] = {}
        # Participante de la parada de emergencia del proceso (R4-17 fase 4c, DEC-049)
        self.name = "PySpectrum (sesión de hardware)"
        self._estop_work_done = threading.Event()
        self._estop_work_done.set()
        self._estop_handled_gen = 0
        self._gui_work_gen = 0
        self._legacy_estop = False

    @property
    def current_owner(self) -> str:
        with self._lock:
            return self._current_owner

    @property
    def is_busy(self) -> bool:
        with self._lock:
            return self._is_busy

    # Lecturas sin el lock, para el hilo del Live: el E-STOP y `acquire_session` llaman a las pausas con el
    # lock tomado, y el Live espera su propio lock mientras lee la sesión. Tomar este lock ahí sería un
    # bloqueo mutuo. Leer un bool es atómico; el orden de `acquire_session` (ocupada antes de pausar)
    # asegura que un Live que vio "libre" queda detenido por la pausa.
    @property
    def busy_nowait(self) -> bool:
        return self._is_busy

    @property
    def estopped_nowait(self) -> bool:
        return _estop_state.is_active() or self._emergency_active

    @property
    def is_emergency_stopped(self) -> bool:
        """La parada del proceso (R4-17 fase 4c): también la de PyPrinting en modo satélite. Sin candado."""
        return _estop_state.is_active() or self._emergency_active

    def clear_emergency(self, timeout_s: float = 3.0) -> bool:
        """API heredada del rearme (la interfaz nueva usa el Rearmar del coordinador, con su consulta de 12 s).
        Limpia la bandera propia y, si hay una parada del proceso, la rearma en cuanto se pueda, esperando a lo sumo
        `timeout_s`. Devuelve si quedó sin parada."""
        with self._lock:
            self._emergency_active = False
        if _estop_state.is_active():
            from core.emergency_stop import get_emergency_coordinator
            coordinator = get_emergency_coordinator()
            gen = _estop_state.generation()
            t_end = time.monotonic() + float(timeout_s)
            check = coordinator.rearm_check(gen)
            while not check.ok and time.monotonic() < t_end:
                time.sleep(0.01)
                check = coordinator.rearm_check(gen)
            ok, why = coordinator.rearm(gen) if check.ok else (False, check.reason)
            if not ok:
                print(f"[HardwareSessionManager] No se pudo rearmar: {why}")
                return False
        print("[HardwareSessionManager] Parada de emergencia rearmada. Sistema listo.")
        self.statusWarningSignal.emit("Sistema rearmado. Estado normal restaurado.")
        return True

    def register_live_controller(self, name: str, pause_cb: Callable[[], None], resume_cb: Optional[Callable[[], None]] = None):
        """Registra controladores de modo Live que deben ser pausados al iniciar una rutina batch."""
        with self._lock:
            self._live_pause_callbacks[name] = pause_cb
            if resume_cb:
                self._live_resume_callbacks[name] = resume_cb

    def acquire_session(self, requester_name: str, auto_pause_live: bool = True) -> bool:
        """
        Intenta obtener el control exclusivo del hardware.
        Si hay un modo Live corriendo y auto_pause_live=True, lo pausa automáticamente.
        Si otra rutina batch está activa o hay E-STOP activo, rechaza la solicitud.
        """
        with self._lock:
            if self.is_emergency_stopped:
                msg = f"E-STOP ACTIVO: Imposible iniciar '{requester_name}'. Debe rearmar el sistema."
                print(f"[HardwareSessionManager] {msg}")
                self.statusWarningSignal.emit(msg)
                return False

            if self._is_busy and self._current_owner != requester_name:
                msg = f"Hardware ocupado por '{self._current_owner}'. Imposible iniciar '{requester_name}'."
                print(f"[HardwareSessionManager] {msg}")
                self.statusWarningSignal.emit(msg)
                return False

            # Ocupada ANTES de pausar los Live (paquete 1 de R4-M): un Live que arranca en otro hilo lee
            # `busy_nowait`; si todavía vio "libre", la pausa de abajo lo detiene de forma sincrónica.
            self._current_owner = requester_name
            self._is_busy = True

            # Si se inicia una rutina de medición, pausar automáticamente cualquier vista previa Live
            if auto_pause_live:
                self._auto_paused_sources = []
                for name, pause_cb in self._live_pause_callbacks.items():
                    if name != requester_name:
                        try:
                            pause_cb()
                            self._auto_paused_sources.append(name)
                            print(f"[HardwareSessionManager] Modo Live '{name}' pausado automáticamente.")
                        except Exception as e:
                            print(f"[HardwareSessionManager] Error al pausar Live '{name}': {e}")

            print(f"[HardwareSessionManager] Sesión concedida exclusivamente a: '{requester_name}'")
            self.sessionChangedSignal.emit(self._current_owner, True)
            return True

    def release_session(self, requester_name: str, restore_live: bool = False):
        """Libera el control del hardware concedido previamente."""
        with self._lock:
            if self._current_owner == requester_name or not self._current_owner:
                prev_owner = self._current_owner
                self._current_owner = ""
                self._is_busy = False
                print(f"[HardwareSessionManager] Sesión liberada por: '{prev_owner}'")
                self.sessionChangedSignal.emit("", False)

                if restore_live:
                    for name in self._auto_paused_sources:
                        if name in self._live_resume_callbacks:
                            try:
                                self._live_resume_callbacks[name]()
                                print(f"[HardwareSessionManager] Modo Live '{name}' reanudado.")
                            except Exception as e:
                                print(f"[HardwareSessionManager] Error al reanudar Live '{name}': {e}")
                    self._auto_paused_sources = []

    # ── Participante de la parada de emergencia del proceso (R4-17 fase 4c, DEC-049) ──
    def on_emergency_stop(self, generation: int) -> None:
        """Sólo banderas en el hilo que disparó (< 1 ms, sin E/S ni candados): la cámara va a un hilo propio,
        DESPUÉS del pedido de cierre, y las pausas de los Live al hilo GUI fuera del filtro de teclas."""
        self._emergency_active = True
        if self._legacy_estop or generation == self._estop_handled_gen:
            return
        self._estop_handled_gen = int(generation)
        self._pending_gui_gen = int(generation)
        self._estop_work_done.clear()
        threading.Thread(target=self._estop_camera_work, daemon=True, name="EStopCamera").start()
        QMetaObject.invokeMethod(self, "_estop_gui_work", Qt.ConnectionType.QueuedConnection)

    def is_quiescent(self) -> bool:
        owner = self._current_owner
        routine_busy = self._is_busy and not owner.startswith(PYPRINTING_OWNER_PREFIX)
        return self._estop_work_done.is_set() and not routine_busy

    def on_rearmed(self, generation: int) -> None:
        self._emergency_active = False
        self.statusWarningSignal.emit("Sistema rearmado. Estado normal restaurado.")

    def is_running(self) -> bool:
        return self._is_busy and not self._current_owner.startswith(PYPRINTING_OWNER_PREFIX)

    def _reset_estop_for_tests(self) -> None:
        self._emergency_active = False
        self._estop_work_done.set()
        self._legacy_estop = False

    def _estop_camera_work(self) -> Dict[str, str]:
        """Aborto de la cámara y ganancia EM a 0 releída (R2-inst §2.5-5, paso 7). Sin el candado de la sesión
        durante la E/S de la cámara."""
        report: Dict[str, str] = {}
        try:
            try:
                cam = get_andor_ccd()
                cam.abort_acquisition()
            except Exception as e:
                cam = None
                print(f"[E-STOP Error] cam.abort_acquisition: {e}")
            try:
                if cam is None:
                    raise RuntimeError("cámara no disponible")
                ret = cam.set_emccd_gain(0)
                read = cam.get_emccd_gain()
                ret_r, gain = (read[0], read[1]) if isinstance(read, (tuple, list)) else (20002, read)
                if ret == 20002 and ret_r == 20002 and int(gain) == 0:
                    report["gain"] = "0 releído"
                else:
                    report["gain"] = f"NO CONFIRMADA (set {ret}, lectura {ret_r}: {gain})"
            except Exception as e:
                report["gain"] = f"error: {e}"
                print(f"[E-STOP Error] ganancia EM: {e}")
            self.last_estop_report = {**self.last_estop_report, **report}
        finally:
            self._estop_work_done.set()
        return report

    @pyqtSlot()
    def _estop_gui_work(self) -> None:
        """En el hilo GUI: pausa los Live, libera la sesión de una rutina de PySpectrum (no la de la grilla de
        PyPrinting, que la conserva detenida: respuesta 3 del 2026-10-03) y avisa a la interfaz."""
        # Encolado: corre sólo si la parada que lo pidió sigue activa. Si ya se rearmó (o hubo otra), pausar los Live y
        # soltar la sesión ahora caería sobre una rutina nueva, que no tiene nada que ver con esa parada.
        gen = int(getattr(self, "_pending_gui_gen", 0))
        if not (_estop_state.is_active() and _estop_state.generation() == gen) and not self._emergency_active:
            return
        if gen and gen == self._gui_work_gen:
            return
        self._gui_work_gen = gen
        with self._lock:
            for name, pause_cb in self._live_pause_callbacks.items():
                try:
                    pause_cb()
                except Exception:
                    pass
            if not self._current_owner.startswith(PYPRINTING_OWNER_PREFIX):
                self._current_owner = ""
                self._is_busy = False
                self.sessionChangedSignal.emit("", False)
        self.emergencyStopSignal.emit()
        self.statusWarningSignal.emit("🚨 PARADA DE EMERGENCIA EJECUTADA: Láseres cerrados y adquisición abortada.")

    def emergency_stop(self):
        """
        PARADA DE EMERGENCIA (API heredada; el botón y las teclas usan el coordinador del proceso).
        Desde R4-17 fase 4c es la parada del PROCESO: bloquea toda apertura y todo movimiento, también de PyPrinting
        en modo satélite, hasta Rearmar. Sigue siendo sincrónica, como antes, para el cierre ordenado y las rutinas:
        1. dispara la parada del proceso (el evento, la época, el cerrador);
        2. cierra los cuatro obturadores también desde acá y espera el resultado;
        3. aborta la cámara y pone la ganancia EM en 0, releída;
        4. pausa los Live, libera la sesión de una rutina de PySpectrum y avisa a la interfaz.
        """
        print("\n" + "=" * 60)
        print("[E-STOP] PARADA DE EMERGENCIA DISPARADA EN PYSPECTRUM 3.0!")
        print("=" * 60)
        from core.emergency_stop import get_emergency_coordinator
        self._legacy_estop = True
        try:
            gen = get_emergency_coordinator().trigger("PySpectrum")
        finally:
            self._legacy_estop = False
        self._estop_handled_gen = int(gen)
        self._pending_gui_gen = int(gen)
        with self._lock:
            self._emergency_active = True
            report: Dict[str, str] = {}
            # 1. Apagado inmediato de láseres. Un cierre no confirmado cuenta como abierto (DEC-036):
            #    el watchdog sigue reintentando y acá queda registrado.
            try:
                report["shutters"] = "cerrados" if close_all_shutters() else "CIERRE NO CONFIRMADO"
            except Exception as e:
                report["shutters"] = f"error: {e}"
                print(f"[E-STOP Error] close_all_shutters: {e}")

            self.last_estop_report = report
        # 2-3. La cámara, en este mismo hilo (sincrónica, como antes)
        self._estop_work_done.clear()
        report.update(self._estop_camera_work())
        self.last_estop_report = report
        print(f"[E-STOP] obturadores: {report.get('shutters')} · ganancia EM: {report.get('gain')}")
        # 4. La interfaz: en el hilo GUI ya; desde otro hilo, encolada
        if QThread.currentThread() == self.thread():
            self._estop_gui_work()
        else:
            QMetaObject.invokeMethod(self, "_estop_gui_work", Qt.ConnectionType.QueuedConnection)


# Instancia singleton para importación directa
hardware_session = HardwareSessionManager.get_instance()

# Participante permanente de la parada del proceso (R4-17 fase 4c): PySpectrum solo, PyPrinting suelto (que importa
# este módulo para el bus de subyugación) y el satélite comparten la misma parada y el mismo Rearmar
from core.emergency_stop import get_emergency_coordinator as _get_coordinator
_get_coordinator().register(hardware_session, permanent=True)
