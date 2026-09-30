# -*- coding: utf-8 -*-
"""
acquisition_setup_dialog.py — Máquina de Transición de Modos de Lectura y Diálogo Modal
PySpectrum 3.0 — UNSAM Nanofotónica

Implementa el protocolo de transición segura entre modos de lectura del Andor SDK
(FVB, Single-Track, Multi-Track, Random-Track, Imagen 2D): abortar adquisición en curso,
esperar IDLE, reconfigurar el driver y calcular la forma exacta del nuevo buffer de captura
para que la GUI reasigne sus arrays (ctypes + NumPy) sin desbordamientos ni fugas de memoria.

compute_buffer_shape()/transition_read_mode() son funciones puras (sin dependencia de Qt),
testeables de forma aislada. AcquisitionSetupDialog es el indicador visual no bloqueante que
las envuelve y deshabilita los disparadores de la UI durante la transición.
"""
from __future__ import annotations
import time
from typing import Any, Dict, List, Optional, Tuple
from PyQt6 import QtCore, QtWidgets

from pyspectrum.drivers.andor_ccd_driver import (
    DRV_IDLE,
    READ_MODE_FVB,
    READ_MODE_SINGLE_TRACK,
    READ_MODE_MULTI_TRACK,
    READ_MODE_RANDOM_TRACK,
    READ_MODE_IMAGE,
)


def compute_buffer_shape(read_mode: int, width: int = 1004, height: int = 1002, n_tracks: int = 1,
                         v_height: Optional[int] = None) -> Tuple[int, ...]:
    """Calcula la forma exacta (NumPy shape) del buffer de captura para cada modo de lectura."""
    if read_mode in (READ_MODE_FVB, READ_MODE_SINGLE_TRACK):
        return (int(width),)
    if read_mode in (READ_MODE_MULTI_TRACK, READ_MODE_RANDOM_TRACK):
        return (max(1, int(n_tracks)), int(width))
    eff_h = int(v_height) if v_height is not None else int(height)
    return (eff_h, int(width))  # READ_MODE_IMAGE (o sub-área 2D acotada a ROI)


def transition_read_mode(camera, new_mode: int, *, width: int = 1004, height: int = 1002,
                          single_track_center: Optional[int] = None, single_track_height: int = 40,
                          multi_track_height: int = 5, multi_track_offset: int = 0, n_tracks: int = 1,
                          random_track_areas: Optional[List[Tuple[int, int]]] = None,
                          image_vstart: Optional[int] = None, image_vend: Optional[int] = None,
                          idle_timeout_s: float = 2.0) -> Dict[str, Any]:
    """Ejecuta el protocolo de transición segura de modo de lectura:
    1) Aborta cualquier adquisición en curso y espera a que el driver reporte DRV_IDLE.
    2) Aplica SetReadMode + la configuración específica del nuevo modo (SingleTrack/MultiTrack/
       RandomTrack/Image).
    3) Calcula la forma exacta del nuevo buffer de captura.
    Devuelve {'applied_mode', 'buffer_shape', 'n_tracks'} para que la GUI reasigne sus arrays.

    Con el Live activo no hace nada y devuelve `refused` (paquete 1 de R4-M, pregunta 2): el modo de
    lectura cambia la forma del cuadro, y abortar acá dejaría al Live leyendo una cámara detenida.
    """
    from pyspectrum.drivers.live_stream import live_api
    if live_api(camera).live_active:
        return {"applied_mode": None, "buffer_shape": None, "n_tracks": 0,
                "refused": "Detené el Live para cambiar el modo de lectura: cambia la forma del cuadro."}
    camera.abort_acquisition()

    if hasattr(camera, "get_status"):
        t0 = time.time()
        while time.time() - t0 < idle_timeout_s:
            try:
                if camera.get_status() == DRV_IDLE:
                    break
            except Exception:
                break
            time.sleep(0.02)

    camera.set_read_mode(new_mode)

    effective_n_tracks = 1
    eff_height = height
    if new_mode == READ_MODE_SINGLE_TRACK:
        center = int(single_track_center) if single_track_center is not None else height // 2
        camera.set_single_track(center, int(single_track_height))
    elif new_mode == READ_MODE_MULTI_TRACK:
        camera.set_multi_track(int(n_tracks), int(multi_track_height), int(multi_track_offset))
        effective_n_tracks = max(1, int(n_tracks))
    elif new_mode == READ_MODE_RANDOM_TRACK:
        areas = random_track_areas or [(0, 5)]
        camera.set_random_track(areas)
        effective_n_tracks = max(1, len(areas))
    elif new_mode == READ_MODE_IMAGE:
        if image_vstart is not None and image_vend is not None:
            vstart = max(1, min(height, int(image_vstart)))
            vend = max(vstart, min(height, int(image_vend)))
            eff_height = vend - vstart + 1
        else:
            vstart, vend = 1, height
            eff_height = height
        camera.set_image(1, 1, 1, width, vstart, vend)

    buffer_shape = compute_buffer_shape(new_mode, width=width, height=height, n_tracks=effective_n_tracks,
                                        v_height=eff_height if new_mode == READ_MODE_IMAGE else None)
    return {"applied_mode": new_mode, "buffer_shape": buffer_shape, "n_tracks": effective_n_tracks}


class AcquisitionSetupDialog(QtWidgets.QDialog):
    """Indicador modal no bloqueante ('Configurando adquisición...') mostrado durante una
    transición de modo de lectura, para evitar condiciones de carrera en la UI mientras el
    driver aborta, reconfigura y reasigna buffers."""

    def __init__(self, parent=None, message: str = "Configurando adquisición..."):
        super().__init__(parent)
        self.setWindowTitle("PySpectrum 3.0")
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        self.setStyleSheet("""
            QDialog { background-color: #1E1E2E; border: 1px solid #45475A; }
            QLabel { color: #CDD6F4; font-weight: bold; padding: 6px; }
            QProgressBar { border: 1px solid #45475A; border-radius: 4px; background-color: #11111B; }
            QProgressBar::chunk { background-color: #89B4FA; }
        """)
        layout = QtWidgets.QVBoxLayout(self)
        self.lbl_message = QtWidgets.QLabel(message)
        layout.addWidget(self.lbl_message)
        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 0)  # Indeterminado
        layout.addWidget(self.progress)
        self.setFixedSize(320, 90)

    def run(self, fn, *args, **kwargs) -> Any:
        """Muestra el diálogo, ejecuta fn(*args, **kwargs) manteniendo la UI responsiva
        mediante processEvents(), y cierra el diálogo al finalizar (incluso si fn lanza)."""
        self.show()
        QtWidgets.QApplication.processEvents()
        try:
            return fn(*args, **kwargs)
        finally:
            self.close()
