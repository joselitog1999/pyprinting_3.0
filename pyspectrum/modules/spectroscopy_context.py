# -*- coding: utf-8 -*-
"""
spectroscopy_context.py — Bus de Estado Global de la Sesión de Espectroscopía
PySpectrum 3.0 — UNSAM Nanofotónica

Singleton que centraliza el estado compartido entre pestañas del nuevo shell (ROI vertical,
modo de lectura activo, posición del espectrógrafo y subyugación de subsistemas auxiliares)
y lo propaga vía señales Qt, siguiendo el mismo patrón de instancia única por módulo ya usado
en pyspectrum/modules/hardware_session.py (HardwareSessionManager.get_instance()).
"""
from __future__ import annotations
import threading
from typing import Optional
from PyQt6.QtCore import pyqtSignal, QObject


class SpectroscopyContext(QObject):
    """Contexto central de sesión de PySpectrum 3.0: ROI vertical, modo de lectura activo,
    posición del espectrógrafo y estado de subyugación de subsistemas auxiliares
    (platina de contrapropagante y fotodiodo), propagados a todas las pestañas del shell."""

    verticalRoiChanged = pyqtSignal(int, int, int, int)   # (y_min, y_max, y_center, y_height)
    readModeChanged = pyqtSignal(int)                     # modo de lectura actual de la cámara
    spectrographMoved = pyqtSignal(float, int)             # (wavelength_nm, grating)
    subjugatedModeChanged = pyqtSignal(bool)                # True: control exclusivo de platina/DAQ

    _instance: Optional["SpectroscopyContext"] = None
    _lock = threading.RLock()

    @classmethod
    def get_instance(cls) -> "SpectroscopyContext":
        with cls._lock:
            if cls._instance is None:
                cls._instance = SpectroscopyContext()
            return cls._instance

    def __init__(self, parent=None):
        super().__init__(parent)
        self._roi = (0, 0, 0, 0)
        self._read_mode = 0
        self._wavelength = 0.0
        self._grating = 1
        self._subjugated = False

    @property
    def vertical_roi(self) -> tuple:
        return self._roi

    @property
    def read_mode(self) -> int:
        return self._read_mode

    @property
    def wavelength_nm(self) -> float:
        return self._wavelength

    @property
    def grating(self) -> int:
        return self._grating

    @property
    def is_subjugated(self) -> bool:
        return self._subjugated

    def set_vertical_roi(self, y_min: int, y_max: int) -> None:
        y_min, y_max = int(min(y_min, y_max)), int(max(y_min, y_max))
        y_center = (y_min + y_max) // 2
        y_height = max(1, y_max - y_min)
        self._roi = (y_min, y_max, y_center, y_height)
        self.verticalRoiChanged.emit(y_min, y_max, y_center, y_height)

    def set_read_mode(self, mode: int) -> None:
        self._read_mode = int(mode)
        self.readModeChanged.emit(self._read_mode)

    def set_spectrograph_position(self, wavelength_nm: float, grating: int) -> None:
        self._wavelength = float(wavelength_nm)
        self._grating = int(grating)
        self.spectrographMoved.emit(self._wavelength, self._grating)

    def set_subjugated(self, active: bool) -> None:
        self._subjugated = bool(active)
        self.subjugatedModeChanged.emit(self._subjugated)


# Instancia singleton para importación directa
spectroscopy_context = SpectroscopyContext.get_instance()
