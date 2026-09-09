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
from PyQt6.QtCore import pyqtSignal, pyqtSlot, QObject

from core.nidaq import close_all_shutters
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

    @property
    def current_owner(self) -> str:
        with self._lock:
            return self._current_owner

    @property
    def is_busy(self) -> bool:
        with self._lock:
            return self._is_busy

    @property
    def is_emergency_stopped(self) -> bool:
        with self._lock:
            return self._emergency_active

    def clear_emergency(self):
        """Rearma el sistema tras una parada de emergencia."""
        with self._lock:
            self._emergency_active = False
            print("[HardwareSessionManager] Parada de emergencia rearmada. Sistema listo.")
            self.statusWarningSignal.emit("Sistema rearmado. Estado normal restaurado.")

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
            if self._emergency_active:
                msg = f"E-STOP ACTIVO: Imposible iniciar '{requester_name}'. Debe rearmar el sistema."
                print(f"[HardwareSessionManager] {msg}")
                self.statusWarningSignal.emit(msg)
                return False

            if self._is_busy and self._current_owner != requester_name:
                msg = f"Hardware ocupado por '{self._current_owner}'. Imposible iniciar '{requester_name}'."
                print(f"[HardwareSessionManager] {msg}")
                self.statusWarningSignal.emit(msg)
                return False

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

            self._current_owner = requester_name
            self._is_busy = True
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

    def emergency_stop(self):
        """
        PARADA DE EMERGENCIA GLOBAL (E-STOP):
        1. Cierra todos los obturadores láser de forma instantánea.
        2. Aborta cualquier adquisición de cámara en curso.
        3. Libera inmediatamente la sesión de hardware y bloquea nuevas adquisiciones.
        4. Notifica a toda la interfaz mediante emergencyStopSignal.
        """
        print("\n" + "=" * 60)
        print("[E-STOP] PARADA DE EMERGENCIA DISPARADA EN PYSPECTRUM 3.0!")
        print("=" * 60)
        with self._lock:
            self._emergency_active = True
            # 1. Apagado inmediato de láseres
            try:
                close_all_shutters()
            except Exception as e:
                print(f"[E-STOP Error] close_all_shutters: {e}")

            # 2. Aborto de cámara
            try:
                cam = get_andor_ccd()
                cam.abort_acquisition()
            except Exception as e:
                print(f"[E-STOP Error] cam.abort_acquisition: {e}")

            # 3. Pausa de todos los modos live
            for name, pause_cb in self._live_pause_callbacks.items():
                try:
                    pause_cb()
                except Exception:
                    pass

            self._current_owner = ""
            self._is_busy = False
            self.sessionChangedSignal.emit("", False)
            self.emergencyStopSignal.emit()
            self.statusWarningSignal.emit("🚨 PARADA DE EMERGENCIA EJECUTADA: Láseres cerrados y adquisición abortada.")


# Instancia singleton para importación directa
hardware_session = HardwareSessionManager.get_instance()
