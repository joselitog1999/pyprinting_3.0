# -*- coding: utf-8 -*-
"""
optical_support.py — Módulo Puente de Soporte Óptico (Fase 5, DEC-019)
PySpectrum 3.0 — UNSAM Nanofotónica

Permite a cualquier pestaña de PySpectrum invocar las rutinas ópticas de soporte históricas
del microscopio (autofoco Z por correlación cruzada, centrado confocal de nanopartículas) sin
depender de que la ventana satélite Contrapropagante/PyPrinting esté abierta, y sin bloquear
el hilo GUI ni requerir un QThread propio: cada función es síncrona en el hilo llamante, pero
respeta la afinidad de hilo real de cualquier FocusBackend ya en ejecución (si se provee uno)
mediante QMetaObject.invokeMethod + un QEventLoop local con timeout.

Imports de modules.focus/core.nidaq perezosos (dentro de las funciones) para no acoplar la
carga del módulo a la disponibilidad de hardware NI-DAQ/PI en tiempo de importación.
"""
from __future__ import annotations
import time
from typing import Any, Optional, Tuple

import numpy as np
from PyQt6.QtCore import QEventLoop, QMetaObject, QTimer, Qt, Q_ARG


def run_z_autofocus(laser_color: str = "532 nm (green)", timeout_s: float = 15.0, backend: Optional[Any] = None) -> bool:
    """Ejecuta el autofoco Z por correlación cruzada (focus_autocorr_lin_x2) de
    modules/focus.py::Backend. Si no se provee un backend ya construido (ej. el de la
    ventana satélite Contrapropagante), crea uno propio de vida corta. Monitorea
    autofinishSignal/autodoneSignal y renueva heartbeat_shutter() mientras espera, con
    timeout_s como cota de seguridad. Devuelve True si el foco convergió al máximo de
    autocorrelación (autodoneSignal se emitió antes de finalizar/timeout)."""
    from modules.focus import Backend as FocusBackend
    from config import SHUTTERS
    from core.nidaq import heartbeat_shutter

    fb = backend or FocusBackend()
    if laser_color in SHUTTERS:
        fb.laser = laser_color

    loop = QEventLoop()
    result = {"ok": False}

    def _on_auto_done():
        result["ok"] = True

    def _on_finish(_mode: str):
        loop.quit()

    fb.autodoneSignal.connect(_on_auto_done)
    fb.autofinishSignal.connect(_on_finish)

    heartbeat_timer = QTimer()
    heartbeat_timer.timeout.connect(lambda: heartbeat_shutter(30.0))
    heartbeat_timer.start(5000)

    timeout_timer = QTimer()
    timeout_timer.setSingleShot(True)
    timeout_timer.timeout.connect(loop.quit)
    timeout_timer.start(max(1, int(timeout_s * 1000)))

    try:
        heartbeat_shutter(30.0)
        QMetaObject.invokeMethod(fb, "focus_autocorr_lin_x2", Qt.ConnectionType.QueuedConnection, Q_ARG(str, "pyspectrum"))
        loop.exec()
    finally:
        heartbeat_timer.stop()
        timeout_timer.stop()
        fb.autodoneSignal.disconnect(_on_auto_done)
        fb.autofinishSignal.disconnect(_on_finish)

    return result["ok"]


def _read_photodiode_sample(n_samples: int = 5, channel_index: int = 0) -> float:
    """Lee n_samples muestras del canal de fotodiodo channel_index y devuelve su promedio.
    Usa una Task de un solo disparo (continuous=False), correcta para este muestreo puntual
    punto-a-punto (no un streaming continuo como modules/trace.py)."""
    from core.nidaq import channels_photodiodos

    task = channels_photodiodos(rate=1000.0, samps_per_chan=n_samples, continuous=False)
    try:
        task.start()
        data = task.read(n_samples)
        task.wait_until_done()
    finally:
        task.close()
    return float(np.mean(data[channel_index]))


def run_confocal_centering(range_um: float = 1.0, pixels: int = 20, method: str = "center_of_gauss") -> Tuple[float, float]:
    """Ejecuta un micro-escaneo confocal rápido (raster pixels×pixels sobre range_um,
    centrado en la posición actual de la platina PI) leyendo el fotodiodo punto a punto,
    aplica center_of_mass (siempre) y opcionalmente refina con center_of_gauss2D
    (analysis/psf.py, fail-soft: si el ajuste gaussiano no converge conserva el centro de
    masa), y desplaza la platina piezoeléctrica al centroide sub-píxel ajustado (x0, y0) en
    µm. Devuelve las coordenadas físicas optimizadas."""
    from config import pi, PI_STAGE_RANGE_UM
    from psf import center_of_mass, center_of_gauss2D
    from core.nidaq import heartbeat_shutter

    pos0 = pi.qPOS()
    x0, y0 = float(pos0["1"]), float(pos0["2"])

    xs = np.linspace(x0 - range_um / 2.0, x0 + range_um / 2.0, pixels)
    ys = np.linspace(y0 - range_um / 2.0, y0 + range_um / 2.0, pixels)
    image = np.zeros((pixels, pixels), dtype=np.float64)

    for iy, y in enumerate(ys):
        for ix, x in enumerate(xs):
            pi.MOV(1, float(np.clip(x, 0.0, PI_STAGE_RANGE_UM)))
            pi.MOV(2, float(np.clip(y, 0.0, PI_STAGE_RANGE_UM)))
            heartbeat_shutter(30.0)
            image[iy, ix] = _read_photodiode_sample()

    cx, cy = center_of_mass(image)
    if method == "center_of_gauss":
        try:
            cx, cy = center_of_gauss2D(image, cx, cy)
        except Exception as e:
            print(f"[OpticalSupport] Ajuste gaussiano no convergió ({e}); se conserva el centro de masa.")

    x_span = xs[-1] - xs[0]
    y_span = ys[-1] - ys[0]
    x_target = xs[0] + cx * (x_span / max(1, pixels - 1))
    y_target = ys[0] + cy * (y_span / max(1, pixels - 1))
    x_target = float(np.clip(x_target, 0.0, PI_STAGE_RANGE_UM))
    y_target = float(np.clip(y_target, 0.0, PI_STAGE_RANGE_UM))

    pi.MOV(1, x_target)
    pi.MOV(2, y_target)

    return (x_target, y_target)


def get_stage_coordinates() -> Tuple[float, float, float]:
    """Consulta las coordenadas físicas reales (X, Y, Z) en µm de la platina PI en bucle
    cerrado mediante pi.qPOS()."""
    from config import pi

    pos = pi.qPOS()
    return (float(pos["1"]), float(pos["2"]), float(pos["3"]))
