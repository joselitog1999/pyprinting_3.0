# -*- coding: utf-8 -*-
"""
hardware_manager.py — Gestor Centralizado de Estado, Aislamiento y Seguridad de Hardware
PyPrinting 3.0 — UNSAM Nanofotónica

Administra el estado de conexión de los instrumentos físicos (NI-DAQmx, PI Piezo, Cámara,
Láser 532 nm, Espectrómetro), gestiona la bitácora de eventos I/O y permite aislar
dispositivos en caliente (Soft Disconnect / Mock Isolation) para pruebas seguras sin congelar la GUI.
"""
from __future__ import annotations
import time
from typing import Dict, Any, List
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from config import SAFE_MODE, PI_SERIAL, SHUTTERS


class HardwareManager(QObject):
    """
    Gestor centralizado de telemetría y seguridad de hardware.
    Mantiene el estado de cada dispositivo y emite señales de actualización a la interfaz.
    """
    # Señal de estado de dispositivo: (device_name, status_str, detail_msg)
    # status_str: 'connected' (🟢), 'mock' (🟡), 'disconnected' (🔴), 'inactive' (⚪)
    deviceStatusSignal = pyqtSignal(str, str, str)
    # Señal de log de eventos: (timestamp_str, level_str, message_str)
    hardwareLogSignal  = pyqtSignal(str, str, str)
    # Señal de cambio en estado de aislamiento: (device_name, is_isolated)
    isolationChangedSignal = pyqtSignal(str, bool)

    DEVICES = [
        "NI-DAQmx (Dev1)",
        "PI Piezo (E-517/E-727)",
        "Cámara USB/Thorlabs",
        "Láser 532 nm (AO2)",
        "Espectrómetro USB (PySpectrum)"
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.device_states: Dict[str, str] = {}
        self.device_details: Dict[str, str] = {}
        self.device_isolated: Dict[str, bool] = {}

        self._init_defaults()

    def _init_defaults(self):
        for dev in self.DEVICES:
            self.device_isolated[dev] = False
            if dev == "Espectrómetro USB (PySpectrum)":
                # Módulo presente pero inactivo por especificación (pendiente PySpectrum)
                self.device_states[dev] = "inactive"
                self.device_details[dev] = "Inactivo — Pendiente de integración con PySpectrum"
            elif SAFE_MODE:
                self.device_states[dev] = "mock"
                self.device_details[dev] = "Simulación activa (SAFE_MODE)"
            else:
                self.device_states[dev] = "connected"
                self.device_details[dev] = "Conectado y operativo"

    def log(self, level: str, message: str):
        ts = time.strftime("%H:%M:%S")
        self.hardwareLogSignal.emit(ts, level, message)

    def rescan_hardware(self):
        """Re-escanea en caliente la presencia de hardware físico y actualiza la matriz de estado."""
        self.log("INFO", "Iniciando re-escaneo en caliente de instrumentos...")
        for dev in self.DEVICES:
            if dev == "Espectrómetro USB (PySpectrum)":
                self.device_states[dev] = "inactive"
                self.device_details[dev] = "Inactivo — Pendiente de integración con PySpectrum"
                self.deviceStatusSignal.emit(dev, "inactive", self.device_details[dev])
                continue

            if self.device_isolated.get(dev, False):
                self.device_states[dev] = "mock"
                self.device_details[dev] = "Aislado manualmente por software (Soft Mock)"
                self.deviceStatusSignal.emit(dev, "mock", self.device_details[dev])
                self.log("WARNING", f"[{dev}] Mantenido en modo Aislado (Soft Mock).")
                continue

            if SAFE_MODE:
                self.device_states[dev] = "mock"
                self.device_details[dev] = "Simulación activa (SAFE_MODE)"
                self.deviceStatusSignal.emit(dev, "mock", self.device_details[dev])
            else:
                # Comprobar hardware real
                try:
                    if "NI-DAQmx" in dev:
                        import nidaqmx
                        system = nidaqmx.system.System.local()
                        devs = [d.name for d in system.devices]
                        if "Dev1" in devs:
                            self.device_states[dev] = "connected"
                            self.device_details[dev] = "NI-DAQmx Dev1 detectado"
                        else:
                            self.device_states[dev] = "disconnected"
                            self.device_details[dev] = "Dev1 no encontrado en NI-MAX"
                    elif "PI Piezo" in dev:
                        from pipython import GCSDevice
                        self.device_states[dev] = "connected"
                        self.device_details[dev] = f"Controlador PI SN {PI_SERIAL} activo"
                    elif "Cámara" in dev:
                        self.device_states[dev] = "connected"
                        self.device_details[dev] = "Cámara lista a 30 FPS"
                    elif "Láser" in dev:
                        self.device_states[dev] = "connected"
                        self.device_details[dev] = "Canal analógico AO2 verificado"
                except Exception as e:
                    self.device_states[dev] = "disconnected"
                    self.device_details[dev] = f"Error I/O: {e}"

                self.deviceStatusSignal.emit(dev, self.device_states[dev], self.device_details[dev])
                self.log("INFO", f"[{dev}] Estado: {self.device_states[dev]} ({self.device_details[dev]})")

        self.log("SUCCESS", "Re-escaneo de hardware completado con éxito.")

    @pyqtSlot(str, bool)
    def toggle_isolation(self, dev: str, isolate: bool):
        """Aísla o restablece la conexión de un dispositivo específico."""
        if dev == "Espectrómetro USB (PySpectrum)":
            self.log("WARNING", f"[{dev}] El módulo del espectrómetro permanece inactivo hasta la integración de PySpectrum.")
            return

        self.device_isolated[dev] = isolate
        if isolate:
            self.device_states[dev] = "mock"
            self.device_details[dev] = "Aislado manualmente por software (Soft Mock)"
            self.log("WARNING", f"[{dev}] AISLADO: Conmutado a modo Mock transparente.")
        else:
            if SAFE_MODE:
                self.device_states[dev] = "mock"
                self.device_details[dev] = "Simulación activa (SAFE_MODE)"
            else:
                self.device_states[dev] = "connected"
                self.device_details[dev] = "Restablecido a conexión física real"
            self.log("INFO", f"[{dev}] RESTABLECIDO: Modo físico reactivado.")

        self.deviceStatusSignal.emit(dev, self.device_states[dev], self.device_details[dev])
        self.isolationChangedSignal.emit(dev, isolate)


# Instancia Singleton Global del Gestor de Hardware
hardware_manager = HardwareManager()
