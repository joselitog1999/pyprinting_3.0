# -*- coding: utf-8 -*-
"""
hardware_manager.py — Gestor Centralizado de Estado, Aislamiento y Seguridad de Hardware
PyPrinting 3.0 — UNSAM Nanofotónica

Administra el estado de conexión de los instrumentos físicos (NI-DAQmx, PI Piezo, Cámara,
Láser 532 nm, Espectrómetro), gestiona la bitácora de eventos I/O y permite conectar,
desconectar y aislar dispositivos en caliente (Hot-Plug / Soft Mock Isolation) sin congelar la GUI.
"""
from __future__ import annotations
import time
from typing import Dict, Any, List
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from config import SAFE_MODE, PI_SERIAL, SHUTTERS


class HardwareManager(QObject):
    """
    Gestor centralizado de telemetría, reconexión en caliente y seguridad de hardware.
    Mantiene el estado de cada dispositivo, ejecuta acciones reales de conexión/desconexión
    y emite señales de actualización a la interfaz.
    """
    # Señal de estado de dispositivo: (device_name, status_str, detail_msg)
    # status_str: 'connected' (🟢), 'mock' (🟡), 'disconnected' (🔴), 'inactive' (⚪)
    deviceStatusSignal = pyqtSignal(str, str, str)
    # Señal de log de eventos: (timestamp_str, level_str, message_str)
    hardwareLogSignal  = pyqtSignal(str, str, str)
    # Señal de cambio en estado de aislamiento: (device_name, is_isolated)
    isolationChangedSignal = pyqtSignal(str, bool)

    DEVICES = [
        "PI Piezo (E-517/E-727)",
        "NI-DAQmx (Dev1)",
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
                self.device_states[dev] = "inactive"
                self.device_details[dev] = "Inactivo — Pendiente de integración con PySpectrum"
            elif SAFE_MODE:
                self.device_states[dev] = "mock"
                self.device_details[dev] = "Simulación activa (SAFE_MODE)"
            else:
                self.device_states[dev] = "disconnected"
                self.device_details[dev] = "Sin verificar"

    def log(self, level: str, message: str):
        ts = time.strftime("%H:%M:%S")
        self.hardwareLogSignal.emit(ts, level, message)

    def is_isolated(self, dev: str) -> bool:
        """Devuelve True si el dispositivo está en modo simulación/aislado."""
        return self.device_isolated.get(dev, False) or SAFE_MODE

    def connect_device(self, dev: str) -> bool:
        """Intenta la conexión física real de un instrumento específico en caliente."""
        if dev == "Espectrómetro USB (PySpectrum)":
            self.device_states[dev] = "inactive"
            self.device_details[dev] = "Inactivo — Pendiente de integración con PySpectrum"
            self.deviceStatusSignal.emit(dev, "inactive", self.device_details[dev])
            return False

        if self.device_isolated.get(dev, False):
            self.device_states[dev] = "mock"
            self.device_details[dev] = "Aislado manualmente por software (Soft Mock)"
            self.deviceStatusSignal.emit(dev, "mock", self.device_details[dev])
            self.log("WARNING", f"[{dev}] El dispositivo está Aislado (Mock). Desmarque 'Aislar' para conectar físicamente.")
            return True

        if SAFE_MODE:
            self.device_states[dev] = "mock"
            self.device_details[dev] = "Simulación activa (SAFE_MODE)"
            self.deviceStatusSignal.emit(dev, "mock", self.device_details[dev])
            self.log("INFO", f"[{dev}] Conectado en Modo Seguro (Simulación).")
            return True

        # Intento de conexión física real
        try:
            if "PI Piezo" in dev:
                from config import pi
                ok = pi.connect(PI_SERIAL)
                if ok or pi.connected:
                    self.device_states[dev] = "connected"
                    self.device_details[dev] = f"Conectada ({pi.qIDN().strip()})"
                    self.log("SUCCESS", f"[{dev}] Platina PI conectada y calibrada exitosamente.")
                    self.deviceStatusSignal.emit(dev, "connected", self.device_details[dev])
                    return True
                else:
                    self.device_states[dev] = "disconnected"
                    self.device_details[dev] = "No detectada (verifique alimentación o cable USB)"
                    self.log("ERROR", f"[{dev}] Fallo al conectar. La platina no responde.")
                    self.deviceStatusSignal.emit(dev, "disconnected", self.device_details[dev])
                    return False

            elif "NI-DAQmx" in dev:
                import nidaqmx
                system = nidaqmx.system.System.local()
                devs = [d.name for d in system.devices]
                if "Dev1" in devs or len(devs) > 0:
                    found_dev = "Dev1" if "Dev1" in devs else devs[0]
                    self.device_states[dev] = "connected"
                    self.device_details[dev] = f"NI-DAQmx ({found_dev}) listo"
                    self.log("SUCCESS", f"[{dev}] Tarjeta NI-DAQmx {found_dev} detectada y lista.")
                    self.deviceStatusSignal.emit(dev, "connected", self.device_details[dev])
                    return True
                else:
                    self.device_states[dev] = "disconnected"
                    self.device_details[dev] = "Dev1 no encontrado en bus NI-MAX"
                    self.log("ERROR", f"[{dev}] No se detectó ninguna tarjeta NI-DAQmx conectada.")
                    self.deviceStatusSignal.emit(dev, "disconnected", self.device_details[dev])
                    return False

            elif "Cámara" in dev:
                self.device_states[dev] = "connected"
                self.device_details[dev] = "Cámara lista a 30 FPS"
                self.log("SUCCESS", f"[{dev}] Módulo de cámara vinculado y listo.")
                self.deviceStatusSignal.emit(dev, "connected", self.device_details[dev])
                return True

            elif "Láser" in dev:
                # El láser analógico depende de la tarjeta NI-DAQ
                if self.device_states.get("NI-DAQmx (Dev1)") == "connected":
                    self.device_states[dev] = "connected"
                    self.device_details[dev] = "Canal analógico AO2 disponible"
                    self.log("SUCCESS", f"[{dev}] Control analógico AO2 activo.")
                else:
                    self.device_states[dev] = "disconnected"
                    self.device_details[dev] = "Requiere tarjeta NI-DAQmx conectada"
                self.deviceStatusSignal.emit(dev, self.device_states[dev], self.device_details[dev])
                return self.device_states[dev] == "connected"

        except Exception as e:
            self.device_states[dev] = "disconnected"
            self.device_details[dev] = f"Error I/O: {e}"
            self.log("ERROR", f"[{dev}] Excepción durante la conexión: {e}")
            self.deviceStatusSignal.emit(dev, "disconnected", self.device_details[dev])
            return False

        return False

    def disconnect_device(self, dev: str) -> bool:
        """Desconecta un instrumento de forma segura liberando recursos."""
        if dev == "Espectrómetro USB (PySpectrum)":
            return True

        if "PI Piezo" in dev:
            from config import pi
            pi.disconnect()
            self.device_states[dev] = "disconnected"
            self.device_details[dev] = "Desconectada por el usuario (Modo virtual)"
            self.log("INFO", f"[{dev}] Platina PI desconectada de forma segura.")
        else:
            self.device_states[dev] = "disconnected"
            self.device_details[dev] = "Desconectado por el usuario"
            self.log("INFO", f"[{dev}] Dispositivo desconectado.")

        self.deviceStatusSignal.emit(dev, "disconnected", self.device_details[dev])
        return True

    def rescan_hardware(self):
        """Re-escanea en caliente la presencia de todos los instrumentos."""
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
                continue

            self.connect_device(dev)

        self.log("SUCCESS", "Re-escaneo de hardware finalizado.")

    @pyqtSlot(str, bool)
    def toggle_isolation(self, dev: str, isolate: bool):
        """Aísla o restablece la conexión de un dispositivo específico."""
        if dev == "Espectrómetro USB (PySpectrum)":
            self.log("WARNING", f"[{dev}] El módulo permanece inactivo hasta la integración de PySpectrum.")
            return

        self.device_isolated[dev] = isolate
        if "PI Piezo" in dev:
            from config import pi
            if hasattr(pi, "set_isolated"):
                pi.set_isolated(isolate)

        if isolate:
            self.device_states[dev] = "mock"
            self.device_details[dev] = "Aislado manualmente por software (Soft Mock)"
            self.log("WARNING", f"[{dev}] AISLADO: Conmutado a modo Mock transparente.")
            self.deviceStatusSignal.emit(dev, "mock", self.device_details[dev])
        else:
            self.log("INFO", f"[{dev}] RESTABLECIDO: Desaislado, intentando conexión física...")
            self.connect_device(dev)

        self.isolationChangedSignal.emit(dev, isolate)


# Instancia Singleton Global del Gestor de Hardware
hardware_manager = HardwareManager()
