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
    from pyspectrum.modules.step_glue_engine import heartbeat_tick

    tick = heartbeat_tick()
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
    heartbeat_timer.timeout.connect(tick)
    heartbeat_timer.start(5000)

    timeout_timer = QTimer()
    timeout_timer.setSingleShot(True)
    timeout_timer.timeout.connect(loop.quit)
    timeout_timer.start(max(1, int(timeout_s * 1000)))

    try:
        tick()
        QMetaObject.invokeMethod(fb, "focus_autocorr_lin_x2", Qt.ConnectionType.QueuedConnection, Q_ARG(str, "pyspectrum"))
        loop.exec()
    finally:
        heartbeat_timer.stop()
        timeout_timer.stop()
        fb.autodoneSignal.disconnect(_on_auto_done)
        fb.autofinishSignal.disconnect(_on_finish)

    return result["ok"]


def read_photodiode_level(n_samples: int = 5, channel_index: int = 0) -> float:
    """Lee n_samples muestras del canal de fotodiodo channel_index y devuelve su promedio.
    Usa una Task de un solo disparo (continuous=False), correcta para este muestreo puntual
    punto-a-punto (no un streaming continuo como modules/trace.py). Pública (Fase 6, DEC-020):
    reutilizada por growth_kinetics.py/dimers.py para los criterios de parada basados en
    fotodiodo y la detección de eventos de impresión por salto de traza."""
    from core.nidaq import channels_photodiodos

    task = channels_photodiodos(rate=1000.0, samps_per_chan=n_samples, continuous=False)
    try:
        task.start()
        data = task.read(n_samples)
        task.wait_until_done()
    finally:
        task.close()
    return float(np.mean(data[channel_index]))


# Alias retro-compatible (nombre privado original, Fase 5)
_read_photodiode_sample = read_photodiode_level


class StageNotOnTarget(RuntimeError):
    """La platina no confirmó la llegada (C-54, DEC-036). Los obturadores ya se cerraron."""


def move_stage_to(x_um: float, y_um: float, z_um: Optional[float] = None, timeout_s: float = 5.0) -> Tuple[float, float, float]:
    """Desplaza la platina PI a (x_um, y_um[, z_um]), clampeada al recorrido de cada eje, y espera la
    confirmación on-target con `config.wait_on_target` (tope `timeout_s`, latiendo). Si z_um es None, Z no
    se toca. Devuelve la posición leída.

    C-54 (AND-1): si la platina no confirma la llegada, cierra los obturadores y levanta
    `StageNotOnTarget`. Antes seguía en silencio y devolvía la posición actual como si hubiera llegado."""
    import config
    from config import clamp_axis_um, wait_on_target
    from pyspectrum.modules.step_glue_engine import heartbeat_tick

    axes = [1, 2]
    targets = [clamp_axis_um(1, x_um), clamp_axis_um(2, y_um)]
    if z_um is not None:
        axes.append(3)
        targets.append(clamp_axis_um(3, z_um))

    stage = config.pi
    ok = stage.MOV(axes, targets) is not False and wait_on_target(axes, timeout_s=timeout_s,
                                                                   on_tick=heartbeat_tick(), stage=stage)
    if not ok:
        from core import nidaq
        nidaq.close_all_shutters()
        raise StageNotOnTarget(f"La platina no confirmó la llegada a {tuple(round(t, 3) for t in targets)} µm "
                               f"en {timeout_s:g} s. Obturadores cerrados.")
    pos = stage.qPOS()
    return (float(pos["1"]), float(pos["2"]), float(pos["3"]))


def run_confocal_centering(range_um: float = 1.0, pixels: int = 20, method: str = "center_of_gauss") -> Tuple[float, float]:
    """Ejecuta un micro-escaneo confocal rápido (raster pixels×pixels sobre range_um,
    centrado en la posición actual de la platina PI) leyendo el fotodiodo punto a punto,
    aplica center_of_mass (siempre) y opcionalmente refina con center_of_gauss2D
    (analysis/psf.py, fail-soft: si el ajuste gaussiano no converge conserva el centro de
    masa), y desplaza la platina piezoeléctrica al centroide sub-píxel ajustado (x0, y0) en
    µm. Devuelve las coordenadas físicas optimizadas."""
    from config import pi, PI_STAGE_RANGE_UM
    from psf import center_of_mass, center_of_gauss2D
    from pyspectrum.modules.step_glue_engine import heartbeat_tick
    tick = heartbeat_tick()

    pos0 = pi.qPOS()
    x0, y0 = float(pos0["1"]), float(pos0["2"])

    xs = np.linspace(x0 - range_um / 2.0, x0 + range_um / 2.0, pixels)
    ys = np.linspace(y0 - range_um / 2.0, y0 + range_um / 2.0, pixels)
    image = np.zeros((pixels, pixels), dtype=np.float64)

    for iy, y in enumerate(ys):
        for ix, x in enumerate(xs):
            pi.MOV(1, float(np.clip(x, 0.0, PI_STAGE_RANGE_UM)))
            pi.MOV(2, float(np.clip(y, 0.0, PI_STAGE_RANGE_UM)))
            tick()
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

    # la posición final sí importa: se confirma (C-54)
    move_stage_to(x_target, y_target, None)
    return (x_target, y_target)


def get_stage_coordinates() -> Tuple[float, float, float]:
    """Consulta las coordenadas físicas reales (X, Y, Z) en µm de la platina PI en bucle
    cerrado mediante pi.qPOS()."""
    from config import pi

    pos = pi.qPOS()
    return (float(pos["1"]), float(pos["2"]), float(pos["3"]))
