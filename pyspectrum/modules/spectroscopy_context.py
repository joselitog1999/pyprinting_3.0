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
    slitParametersChanged = pyqtSignal(float, float, int)  # (slit_width_um, slit_center_px, slit_zero_pos)
    colormapChanged = pyqtSignal(str)                     # nombre visible del colormap ("Viridis", etc.)

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
        self._slit_width_um = 50.0
        self._slit_center_px = 501.25
        self._slit_zero_pos = 0
        self._colormap = "Viridis"

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

    @property
    def slit_width_um(self) -> float:
        return self._slit_width_um

    @property
    def slit_center_px(self) -> float:
        return self._slit_center_px

    @property
    def slit_zero_pos(self) -> int:
        return self._slit_zero_pos

    @property
    def colormap(self) -> str:
        return self._colormap

    def set_vertical_roi(self, y_min: int, y_max: int) -> None:
        y_min, y_max = int(min(y_min, y_max)), int(max(y_min, y_max))
        y_center = (y_min + y_max) // 2
        y_height = max(0, y_max - y_min)
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

    def set_slit_parameters(
        self,
        slit_width_um: Optional[float] = None,
        slit_center_px: Optional[float] = None,
        slit_zero_pos: Optional[int] = None,
    ) -> None:
        changed = False
        if slit_width_um is not None and abs(self._slit_width_um - float(slit_width_um)) > 1e-4:
            self._slit_width_um = float(slit_width_um)
            changed = True
        if slit_center_px is not None and abs(self._slit_center_px - float(slit_center_px)) > 1e-4:
            self._slit_center_px = float(slit_center_px)
            changed = True
        if slit_zero_pos is not None and self._slit_zero_pos != int(slit_zero_pos):
            self._slit_zero_pos = int(slit_zero_pos)
            changed = True
        if changed:
            self.slitParametersChanged.emit(self._slit_width_um, self._slit_center_px, self._slit_zero_pos)

    def set_colormap(self, colormap_name: str) -> None:
        if colormap_name and colormap_name != self._colormap:
            self._colormap = str(colormap_name)
            self.colormapChanged.emit(self._colormap)


# Instancia singleton para importación directa
spectroscopy_context = SpectroscopyContext.get_instance()
