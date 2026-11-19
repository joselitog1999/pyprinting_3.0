# -*- coding: utf-8 -*-
"""El foco y el confocal por fotodiodo del satélite PyPrinting, para las grillas de PySpectrum (DEC-054).

Decisión del investigador (2026-11-19): las grillas de PySpectrum que enfocan o centran usan el `FocusBackend` y el
`ConfocalBackend` del satélite **Microscopio Derecho**, y sin satélite no arrancan. Así hay un solo lock de foco por
proceso, el que fijó el operador en el satélite. Antes `run_z_autofocus` creaba un `FocusBackend` nuevo en cada
nodo, que se re-bloqueaba en la Z actual y no corregía la deriva; y el centrado leía siempre `ai0`.

Las grillas corren en un `RoutineThread`; los backends del satélite viven en su `confocalThread`. Todo pedido cruza
de hilo con `QMetaObject.invokeMethod` y la rutina espera con latido, cortable por Stop o E-STOP.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np


class OpticsUnavailable(RuntimeError):
    """No hay satélite, o le falta lo que la grilla necesita (p. ej. el lock de foco)."""


SATELLITE_MISSING = ("Abrí el satélite PyPrinting (Microscopio Derecho) para usar su foco y su confocal: las grillas "
                     "de PySpectrum que enfocan o centran no arrancan sin él.")
FOCUS_LOCK_MISSING = "Fijá el lock de foco en el satélite PyPrinting, o poné \"Autofoco cada N\" = 0."


@dataclass
class CenterScanSpec:
    """El escaneo de centrado, como la ventana "Confocal Photodiode" del legado (`Confocal_ps.py:197-208`)."""
    range_um: float = 2.0
    pixels: int = 34
    method: str = "center of mass"        # modules.confocal.METHOD_CENTER[0]
    threshold: float = 0.3                # filtro del centro de masa del confocal

    def __post_init__(self):
        if not (0.1 <= float(self.range_um) <= 75.0):
            raise ValueError(f"Rango de centrado {self.range_um} µm fuera de 0.1–75 µm")
        if int(self.pixels) < 2:
            raise ValueError("El centrado necesita al menos 2×2 píxeles")
        if not (0.0 <= float(self.threshold) < 1.0):
            raise ValueError("El umbral del centro de masa va de 0 a 1")


@dataclass
class CenterResult:
    x_um: float
    y_um: float
    image: np.ndarray
    gone: np.ndarray
    back: np.ndarray
    extra: dict = field(default_factory=dict)


def _invoke(obj, method: str, *args, blocking: bool = True):
    """Llama al slot `method` de `obj` en el hilo de `obj`. Bloqueante salvo que sea el mismo hilo (Qt prohíbe
    BlockingQueued sobre el propio hilo: entonces la llamada es directa)."""
    from PyQt6.QtCore import QMetaObject, Qt, QThread, Q_ARG
    if obj.thread() is QThread.currentThread():
        return getattr(obj, method)(*args)
    q_args = []
    for a in args:
        if isinstance(a, bool):
            q_args.append(Q_ARG(bool, a))
        elif isinstance(a, float):
            q_args.append(Q_ARG(float, a))
        elif isinstance(a, int):
            q_args.append(Q_ARG(int, a))
        elif isinstance(a, str):
            q_args.append(Q_ARG(str, a))
        elif isinstance(a, list):
            q_args.append(Q_ARG(list, a))
        else:
            raise TypeError(f"Argumento no soportado para {method}: {type(a).__name__}")
    kind = Qt.ConnectionType.BlockingQueuedConnection if blocking else Qt.ConnectionType.QueuedConnection
    QMetaObject.invokeMethod(obj, method, kind, *q_args)


class SatelliteOptics:
    """El foco y el confocal del satélite. Ninguna instancia propia: siempre los del satélite."""

    def __init__(self, focus_backend, confocal_backend):
        self.focus = focus_backend
        self.confocal = confocal_backend

    # ── foco ──
    def has_focus_lock(self) -> bool:
        return bool(getattr(self.focus, "locked_focus", False))

    def autofocus(self, laser: str, should_abort: Callable[[], bool], tick: Callable[[], None],
                  timeout_s: float = 30.0) -> bool:
        """Autofoco por correlación con el lock del operador (`focus_autocorr_lin_x2`). Sin lock no corre: el
        backend se re-bloquearía en la Z actual y no corregiría nada. True si convergió."""
        if not self.has_focus_lock():
            raise OpticsUnavailable(FOCUS_LOCK_MISSING)
        done = threading.Event()
        result = {"ok": False}

        def _on_done():
            result["ok"] = True

        def _on_finish(_mode: str = ""):
            done.set()

        self.focus.autodoneSignal.connect(_on_done)
        self.focus.autofinishSignal.connect(_on_finish)
        try:
            if laser:
                self.focus.laser = laser
            _invoke(self.focus, "focus_autocorr_lin_x2", "pyspectrum", blocking=False)
            self._wait(done, should_abort, tick, timeout_s, "el autofoco", stop=None)
        finally:
            self.focus.autodoneSignal.disconnect(_on_done)
            self.focus.autofinishSignal.disconnect(_on_finish)
        return result["ok"]

    # ── centrado por fotodiodo ──
    def center_scan(self, laser: str, spec: CenterScanSpec, should_abort: Callable[[], bool],
                    tick: Callable[[], None], label: str = "luminescence", number: str = "none",
                    timeout_s: float = 120.0) -> CenterResult:
        """Un escaneo en rampa x/y del confocal del satélite, centrado en la posición actual, con el fotodiodo del
        láser (`PD_CHANNELS[laser]`). El confocal abre y cierra el láser. Los parámetros del panel del satélite se
        restauran al terminar: la rutina no cambia lo que el operador dejó configurado."""
        from modules.confocal import SCAN_MODES, PSF_MODES
        cf = self.confocal
        saved = {
            "ramp": [float(cf.range_x), float(cf.range_y), int(cf.Nx), int(cf.Ny)],
            "scan_mode": str(cf.scan_mode_option), "psf_mode": str(cf.psf_mode_option),
            "method": str(cf.method_center_opt),
            "threshold": float(getattr(cf, "threshold_filter_val", 0.3)),
        }
        done = threading.Event()
        out: dict = {}

        def _on_finished(image, center_mass, gone, back, mode, _number):
            if mode != label:
                return
            out.update(image=np.array(image, copy=True), cm=list(center_mass),
                       gone=np.array(gone, copy=True), back=np.array(back, copy=True))
            done.set()

        cf.scanfinishedSignal.connect(_on_finished)
        try:
            _invoke(cf, "scan_mode", SCAN_MODES[0])
            _invoke(cf, "psf_mode", PSF_MODES[0])
            _invoke(cf, "method_center", str(spec.method))
            _invoke(cf, "set_threshold_filter", float(spec.threshold))
            r = float(spec.range_um)
            _invoke(cf, "scan_ramp_parameters", [r, r, int(spec.pixels), int(spec.pixels)])
            _invoke(cf, "start_scan_routines", str(laser), str(label), str(number), blocking=False)
            self._wait(done, should_abort, tick, timeout_s, "el centrado por fotodiodo",
                       stop=lambda: _invoke(cf, "stop_scan", blocking=False))
        finally:
            cf.scanfinishedSignal.disconnect(_on_finished)
            try:
                _invoke(cf, "scan_ramp_parameters", saved["ramp"])
                _invoke(cf, "scan_mode", saved["scan_mode"])
                _invoke(cf, "psf_mode", saved["psf_mode"])
                _invoke(cf, "method_center", saved["method"])
                _invoke(cf, "set_threshold_filter", saved["threshold"])
            except Exception as e:
                print(f"[Satélite] No se pudieron restaurar los parámetros del confocal: {e}")
        cm = out["cm"]
        return CenterResult(float(cm[0]), float(cm[1]), out["image"], out["gone"], out["back"])

    @staticmethod
    def _wait(done: threading.Event, should_abort, tick, timeout_s: float, what: str, stop) -> None:
        from pyspectrum.modules.routines.grid_runner import GridAbort, NodeFailed
        t0 = time.monotonic()
        while not done.wait(0.05):
            tick()
            if should_abort():
                if stop is not None:
                    stop()
                raise GridAbort(f"Detenida durante {what}.")
            if time.monotonic() - t0 > timeout_s:
                if stop is not None:
                    stop()
                raise NodeFailed(f"{what[0].upper() + what[1:]} no terminó en {timeout_s:g} s.")


def satellite_optics_from(app_backend) -> Optional[SatelliteOptics]:
    """El servicio a partir del `Backend` de app.py (el satélite Microscopio Derecho), o None."""
    if app_backend is None:
        return None
    fw, cw = getattr(app_backend, "focusWorker", None), getattr(app_backend, "confocalWorker", None)
    if fw is None or cw is None:
        return None
    return SatelliteOptics(fw, cw)
