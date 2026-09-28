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

from config import SAFE_MODE, PI_SERIAL, SHUTTERS, NIDAQ_DEVICE

NIDAQ_DEVICE_KEY = "NI-DAQmx (Dev1)"


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
        "Espectrógrafo Andor Shamrock",
        "Cámara Andor CCD (Espectros)"
    ]

    PROFILES = {
        "all": [
            "PI Piezo (E-517/E-727)",
            "NI-DAQmx (Dev1)",
            "Láser 532 nm (AO2)",
            "Cámara USB/Thorlabs",
            "Espectrógrafo Andor Shamrock",
            "Cámara Andor CCD (Espectros)"
        ],
        "pyprinting": [
            "PI Piezo (E-517/E-727)",
            "NI-DAQmx (Dev1)",
            "Láser 532 nm (AO2)"
        ],
        "pyspectrum": [
            "PI Piezo (E-517/E-727)",
            "NI-DAQmx (Dev1)",
            "Espectrógrafo Andor Shamrock",
            "Cámara Andor CCD (Espectros)"
        ],
        "camera": [
            "Cámara USB/Thorlabs"
        ]
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.active_profile = "all"
        self.device_states: Dict[str, str] = {}
        self.device_details: Dict[str, str] = {}
        self.device_isolated: Dict[str, bool] = {}

        self._init_defaults()

    def set_profile(self, profile_name: str, rescan: bool = True):
        """Configura el perfil de hardware activo ('pyprinting', 'pyspectrum', 'camera', 'all')."""
        if profile_name in self.PROFILES:
            self.active_profile = profile_name
            self.log("INFO", f"Perfil de hardware configurado: '{profile_name}'.")
            if rescan:
                self.rescan_hardware()

    def _init_defaults(self):
        target_devs = set(self.PROFILES.get(self.active_profile, self.DEVICES))
        for dev in self.DEVICES:
            self.device_isolated[dev] = False
            if SAFE_MODE:
                self.device_states[dev] = "mock"
                self.device_details[dev] = "Simulación activa (SAFE_MODE)"
            elif dev not in target_devs:
                self.device_states[dev] = "disconnected"
                self.device_details[dev] = "Desconectado por perfil por defecto (Disponible bajo demanda)"
            else:
                self.device_states[dev] = "disconnected"
                self.device_details[dev] = "Sin verificar"

    def log(self, level: str, message: str):
        ts = time.strftime("%H:%M:%S")
        self.hardwareLogSignal.emit(ts, level, message)

    def is_isolated(self, dev: str) -> bool:
        """Devuelve True si el dispositivo fue aislado explícitamente por software (Soft Mock,
        ver toggle_isolation()). No consulta SAFE_MODE: los 9 puntos de consumo reales de este
        método (core/nidaq.py) ya verifican `if SAFE_MODE: ...` por su cuenta ANTES de llegar a
        preguntar is_isolated(), así que replicar esa condición aquí sólo enmascaraba el estado
        real del aislamiento manual (p.ej. is_isolated() quedaba en True para siempre bajo
        SAFE_MODE, incluso tras des-aislar explícitamente un dispositivo con toggle_isolation(...,
        False)) sin aportar ninguna protección adicional. Ver DEC-009 y DEC-022."""
        return self.device_isolated.get(dev, False)

    def connect_device(self, dev: str) -> bool:
        """Intenta la conexión física real de un instrumento específico en caliente."""
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
                is_mock_pi = getattr(pi, 'is_mock', False)
                if (ok or pi.connected) and not is_mock_pi:
                    if hasattr(pi, "is_physically_connected") and pi.is_physically_connected():
                        self.device_states[dev] = "connected"
                        self.device_details[dev] = f"Conectada ({pi.qIDN().strip()})"
                        self.log("SUCCESS", f"[{dev}] Platina PI física conectada y calibrada exitosamente.")
                        self.deviceStatusSignal.emit(dev, "connected", self.device_details[dev])
                        return True

                if is_mock_pi:
                    self.device_states[dev] = "mock"
                    self.device_details[dev] = "Simulación activa (SAFE_MODE)"
                    self.deviceStatusSignal.emit(dev, "mock", self.device_details[dev])
                    return True
                else:
                    self.device_states[dev] = "disconnected"
                    err_msg = getattr(pi, "last_error", "")
                    if any(w in err_msg.lower() for w in ("already", "busy", "open", "in use", "access")):
                        self.device_details[dev] = "Puerto USB ocupado por otra ventana activa de PyPrinting"
                        self.log("WARNING", f"[{dev}] Platina física detectada pero el puerto USB está ocupado por otra sesión de PyPrinting ({err_msg}).")
                    else:
                        self.device_details[dev] = "No detectada o apagada (USB) — Modo virtual activo"
                        self.log("ERROR", f"[{dev}] Fallo al conectar. La platina física no responde (Modo virtual activo).")
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

            elif "Cámara USB" in dev:
                from config import CAMERA_INDEX
                import cv2
                cap = cv2.VideoCapture(CAMERA_INDEX)
                if cap.isOpened():
                    ret, _ = cap.read()
                    cap.release()
                    if ret:
                        self.device_states[dev] = "connected"
                        self.device_details[dev] = f"Cámara USB lista (Índice {CAMERA_INDEX})"
                        self.log("SUCCESS", f"[{dev}] Cámara USB conectada (Índice {CAMERA_INDEX}).")
                        self.deviceStatusSignal.emit(dev, "connected", self.device_details[dev])
                        return True
                try:
                    from canon_edsdk import CanonCamera
                    cc = CanonCamera()
                    cams = cc.get_camera_list()
                    if cams:
                        self.device_states[dev] = "connected"
                        self.device_details[dev] = f"Canon EDSDK detectada ({len(cams)} cuerpo/s)"
                        self.log("SUCCESS", f"[{dev}] Cámara réflex Canon EOS lista.")
                        self.deviceStatusSignal.emit(dev, "connected", self.device_details[dev])
                        return True
                except Exception:
                    pass

                self.device_states[dev] = "disconnected"
                self.device_details[dev] = f"No detectada en índice {CAMERA_INDEX} ni Canon EDSDK"
                self.log("WARNING", f"[{dev}] Cámara no detectada.")
                self.deviceStatusSignal.emit(dev, "disconnected", self.device_details[dev])
                return False

            elif "Láser" in dev:
                if self.device_states.get("NI-DAQmx (Dev1)") == "connected":
                    self.device_states[dev] = "connected"
                    self.device_details[dev] = "Canal analógico AO2 disponible"
                    self.log("SUCCESS", f"[{dev}] Control analógico AO2 activo.")
                else:
                    self.device_states[dev] = "disconnected"
                    self.device_details[dev] = "Requiere tarjeta NI-DAQmx conectada"
                self.deviceStatusSignal.emit(dev, self.device_states[dev], self.device_details[dev])
                return self.device_states[dev] == "connected"

            elif "Shamrock" in dev:
                from pyspectrum.drivers.shamrock_driver import reconnect_shamrock, DEVICE, SHAMROCK_SUCCESS
                if self._refuse_reconnect(dev):
                    return False
                # En el lugar (paso 4, DEC-040): get_shamrock(reset=True) creaba otra instancia y
                # dejaba a los backends con una cerrada.
                sh = reconnect_shamrock()
                if getattr(sh, "is_mock", False):
                    self.device_states[dev] = "disconnected"
                    self.device_details[dev] = "No detectado en USB (DLL o hardware ausente)"
                    self.log("WARNING", f"[{dev}] Espectrógrafo físico ausente en bus USB.")
                    self.deviceStatusSignal.emit(dev, "disconnected", self.device_details[dev])
                    return False

                if hasattr(sh, "is_hardware_alive") and sh.is_hardware_alive(DEVICE):
                    ret, sn = sh.ShamrockGetSerialNumber(DEVICE)
                    self.device_states[dev] = "connected"
                    self.device_details[dev] = f"Espectrógrafo Andor listo (SN: {sn})"
                    self.log("SUCCESS", f"[{dev}] Andor Shamrock conectado: {sn}")
                    self.deviceStatusSignal.emit(dev, "connected", self.device_details[dev])
                    return True
                else:
                    self.device_states[dev] = "disconnected"
                    # Motivo real del driver sin conectar (DEC-040: ya no hay simulador de respaldo).
                    self.device_details[dev] = (getattr(sh, "unavailable_reason", "")
                                                or "Fallo de comunicación con hardware Shamrock")
                    self.log("ERROR", f"[{dev}] Shamrock no responde a comandos de telemetría.")
                    self.deviceStatusSignal.emit(dev, "disconnected", self.device_details[dev])
                    return False

            elif "Andor CCD" in dev:
                from pyspectrum.drivers.andor_ccd_driver import reconnect_andor_ccd
                if self._refuse_reconnect(dev):
                    return False
                # En el lugar (paso 4, DEC-040). ShutDown apaga el enfriador: el tablero avisa antes.
                cam = reconnect_andor_ccd()
                if getattr(cam, "is_mock", False):
                    self.device_states[dev] = "disconnected"
                    self.device_details[dev] = "No detectada en USB (SDK o cámara ausente)"
                    self.log("WARNING", f"[{dev}] Cámara Andor CCD física ausente en bus USB.")
                    self.deviceStatusSignal.emit(dev, "disconnected", self.device_details[dev])
                    return False

                if hasattr(cam, "is_hardware_alive") and cam.is_hardware_alive():
                    status, temp = cam.get_temperature()
                    self.device_states[dev] = "connected"
                    self.device_details[dev] = f"Sensor CCD listo ({temp:.1f} °C)"
                    self.log("SUCCESS", f"[{dev}] Cámara Andor CCD conectada y respondiendo.")
                    self.deviceStatusSignal.emit(dev, "connected", self.device_details[dev])
                    return True
                else:
                    self.device_states[dev] = "disconnected"
                    self.device_details[dev] = (getattr(cam, "unavailable_reason", "")
                                                or "Cámara Andor no responde a consultas de temperatura")
                    self.log("ERROR", f"[{dev}] Cámara Andor CCD no responde a comandos SDK.")
                    self.deviceStatusSignal.emit(dev, "disconnected", self.device_details[dev])
                    return False

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
        elif "Shamrock" in dev:
            if self._refuse_reconnect(dev):
                return False
            try:
                # Se cierra en el lugar; antes get_shamrock(reset=True) lo volvía a inicializar.
                from pyspectrum.drivers import shamrock_driver
                sh = shamrock_driver._shamrock_instance
                if sh is not None and hasattr(sh, "close"):
                    sh.close()
            except Exception as e:
                self.log("WARNING", f"[{dev}] Aviso al cerrar Shamrock: {e}")
            self.device_states[dev] = "disconnected"
            self.device_details[dev] = "Desconectado por el usuario"
            self.log("INFO", f"[{dev}] Espectrógrafo Shamrock cerrado y liberado.")
        elif "Andor CCD" in dev:
            if self._refuse_reconnect(dev):
                return False
            try:
                # Se cierra en el lugar; antes get_andor_ccd(reset=True) la volvía a inicializar.
                from pyspectrum.drivers import andor_ccd_driver
                cam = andor_ccd_driver._andor_instance
                if cam is not None and hasattr(cam, "close"):
                    cam.close()
            except Exception as e:
                self.log("WARNING", f"[{dev}] Aviso al cerrar Andor CCD: {e}")
            self.device_states[dev] = "disconnected"
            self.device_details[dev] = "Desconectado por el usuario"
            self.log("INFO", f"[{dev}] Cámara Andor CCD cerrada y liberada.")
        else:
            self.device_states[dev] = "disconnected"
            self.device_details[dev] = "Desconectado por el usuario"
            self.log("INFO", f"[{dev}] Dispositivo desconectado.")

        self.deviceStatusSignal.emit(dev, "disconnected", self.device_details[dev])
        return True

    def _refuse_reconnect(self, dev: str) -> bool:
        """Reconectar o desconectar la cámara o el Shamrock es una acción explícita que se rechaza
        con una rutina en curso o con la E-STOP (paso 4, DEC-040). Devuelve True si se rechazó."""
        try:
            from pyspectrum.modules.hardware_session import hardware_session
        except Exception:
            return False
        reason = None
        if hardware_session.is_emergency_stopped:
            reason = "E-STOP activa: rearme el sistema antes de reconectar."
        elif hardware_session.is_busy:
            reason = f"'{hardware_session.current_owner}' está usando el equipo: detenga la rutina antes de reconectar."
        if reason is None:
            return False
        self.device_details[dev] = f"Reconexión rechazada. {reason}"
        self.log("WARNING", f"[{dev}] {self.device_details[dev]}")
        self.deviceStatusSignal.emit(dev, self.device_states.get(dev, "disconnected"), self.device_details[dev])
        return True

    def refresh_status(self):
        """Informa el estado de cada equipo SIN conectar, reiniciar ni mover nada (paso 4, DEC-040).

        Es lo que hace el tablero al abrirse. Antes abría con `rescan_hardware()`, que reiniciaba la
        cámara y el Shamrock (el enfriador se apagaba) y reconectaba la platina, que va a home si su
        conexión se había perdido (contra DEC-036). Reescanear queda como botón explícito."""
        for dev in self.DEVICES:
            if SAFE_MODE or self.device_isolated.get(dev, False):
                self.deviceStatusSignal.emit(dev, self.device_states.get(dev, "mock"), self.device_details.get(dev, ""))
                continue
            state, detail = self.device_states.get(dev, "disconnected"), self.device_details.get(dev, "Sin verificar")
            try:
                if "Andor CCD" in dev or "Shamrock" in dev:
                    if "Andor CCD" in dev:
                        from pyspectrum.drivers import andor_ccd_driver as mod
                        drv = mod._andor_instance
                    else:
                        from pyspectrum.drivers import shamrock_driver as mod
                        drv = mod._shamrock_instance
                    if drv is None:
                        state, detail = "disconnected", "No inicializado en este proceso"
                    elif getattr(drv, "is_mock", False):
                        state, detail = "mock", "Simulador"
                    elif getattr(drv, "available", False):
                        state, detail = "connected", "Conectado (estado del driver; sin consultas nuevas)"
                    else:
                        state, detail = "disconnected", getattr(drv, "unavailable_reason", "") or "No conectado"
                elif "PI Piezo" in dev:
                    from config import pi
                    state = "connected" if getattr(pi, "connected", False) else "disconnected"
                    detail = "Conectada" if state == "connected" else "No conectada (use Conectar)"
            except Exception as e:
                state, detail = "disconnected", f"Estado no disponible: {e}"
            self.device_states[dev], self.device_details[dev] = state, detail
            self.deviceStatusSignal.emit(dev, state, detail)

    def rescan_hardware(self, profile: Optional[str] = None):
        """
        Re-escanea en caliente según el perfil especificado o activo.
        Los dispositivos excluidos del perfil quedan desconectados pero disponibles bajo demanda.
        """
        prof_name = profile if profile is not None else self.active_profile
        target_devs = set(self.PROFILES.get(prof_name, self.DEVICES))
        self.log("INFO", f"Iniciando escaneo de hardware (Perfil: '{prof_name}')...")

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

            if dev in target_devs:
                self.connect_device(dev)
            else:
                self.device_states[dev] = "disconnected"
                self.device_details[dev] = "Desconectado por perfil por defecto (Disponible bajo demanda)"
                self.deviceStatusSignal.emit(dev, "disconnected", self.device_details[dev])

        self.log("SUCCESS", f"Escaneo de hardware finalizado (Perfil: '{prof_name}').")

    def physical_daq_present(self) -> bool:
        """True si el sistema ve la placa NI física (`NIDAQ_DEVICE`). En SAFE_MODE es False:
        ahí nada toca hardware y el aislamiento es inocuo."""
        if SAFE_MODE:
            return False
        try:
            import nidaqmx.system
            return NIDAQ_DEVICE in [d.name for d in nidaqmx.system.System.local().devices]
        except Exception:
            return False

    @pyqtSlot(str, bool)
    def toggle_isolation(self, dev: str, isolate: bool):
        """Aísla o restablece la conexión de un dispositivo específico."""
        if dev == "Espectrómetro USB (PySpectrum)":
            self.log("WARNING", f"[{dev}] El módulo permanece inactivo hasta la integración de PySpectrum.")
            return

        # DEC-036: con la placa aislada, open/close_shutter, close_all_shutters(), el watchdog y el
        # botón de pánico dejan de escribir en ella. Si la placa física está presente, aislarla
        # significa que un obturador abierto ya no se puede cerrar: se rechaza.
        if isolate and dev == NIDAQ_DEVICE_KEY and self.physical_daq_present():
            self.log("ERROR", f"[{dev}] Aislamiento RECHAZADO: hay una placa NI conectada. Aislarla anularía "
                              f"el cierre de obturadores, el watchdog y el botón de pánico (DEC-036).")
            self.isolationChangedSignal.emit(dev, False)
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
