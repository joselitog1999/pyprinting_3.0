# -*- coding: utf-8 -*-
"""Banco de pruebas de la cadena de la grilla de impresión (C-01 Ronda 4, fase 0; `ronda2_architecture.md` §8).

Arma los workers reales de `app.Backend` con la misma topología de hilos que `app.create_app_satellite`: los de
medición, foco, traza y confocal en un `QThread` real ("confocalThread"), el `Backend` (y sus despachadores) en el
hilo principal, que hace de hilo GUI. Sin Frontend y en `SAFE_MODE`.

Dobles:
- **Escrituras DO:** se registran en `core.nidaq._write_shutter_lines` (lo que se escribe en la placa), con el hilo y
  la función que la pidió (el primer marco fuera de `core/nidaq.py`).
- **Platina:** se registra cada `MOV` (los objetivos, redondeados).
- **Fotodiodo de la traza:** una lectura por tick con guion por número de lectura desde que se abrió el obturador del
  nodo, no por reloj: así la decisión y el tick no dependen del jitter de los hilos. Cada nodo tiene una "lectura de
  captura" (el escalón ×2) o una "lectura de caída" (×0.3, termina por la rama de caída).
- **Esperas:** `time.sleep` de `modules.measurements` y `modules.focus` escalado (× `SLEEP_SCALE`).

`run_grid(script)` corre una grilla completa y devuelve un `ChainRecord`. Lo usan el test dorado de `legacy_timer`
(`tests/test_legacy_timer_golden.py`) y, desde la fase 3, la matriz de cortes por etapa.
"""
from __future__ import annotations

import inspect
import os
import threading
import time
import types
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

SLEEP_SCALE = 0.01
BASE_V = 1.0


@dataclass(frozen=True)
class NodeScript:
    capture_read: Optional[int] = None    # número de lectura (desde la apertura) en que aparece el escalón ×2
    drop_read: Optional[int] = None       # o en que la señal cae a ×0.3 (rama de caída: "timeout")


@dataclass
class ChainRecord:
    decisions: Dict[int, str] = field(default_factory=dict)
    decision_ticks: Dict[int, int] = field(default_factory=dict)
    do_writes: List[Tuple[Tuple[bool, ...], str]] = field(default_factory=list)
    do_threads: List[str] = field(default_factory=list)
    moves: List[Tuple[float, ...]] = field(default_factory=list)
    finished: bool = False

    def transitions(self) -> List[Tuple[int, bool, str]]:
        """Cambios de nivel por línea, en orden: (línea, nivel nuevo, quién)."""
        out, prev = [], None
        for lines, caller in self.do_writes:
            if prev is not None:
                for i, (a, b) in enumerate(zip(prev, lines)):
                    if a != b:
                        out.append((i, b, caller))
            prev = lines
        return out

    def as_golden(self) -> dict:
        return {"decisions": {str(k): v for k, v in sorted(self.decisions.items())},
                "decision_ticks": {str(k): v for k, v in sorted(self.decision_ticks.items())},
                "do_writes": [[list(l), c] for l, c in self.do_writes],
                "transitions": [list(t) for t in self.transitions()],
                "moves": [list(m) for m in self.moves]}


# Las 11 escenas del guion por defecto: capturas tempranas y tardías, y dos caídas
DEFAULT_SCRIPT: Tuple[NodeScript, ...] = (
    NodeScript(capture_read=12), NodeScript(capture_read=20), NodeScript(drop_read=14), NodeScript(capture_read=15),
    NodeScript(capture_read=30), NodeScript(capture_read=12), NodeScript(drop_read=20), NodeScript(capture_read=18),
    NodeScript(capture_read=25), NodeScript(capture_read=13), NodeScript(capture_read=16),
)


def _caller_outside(module_file: str) -> str:
    for fr in inspect.stack()[2:]:
        if os.path.normcase(fr.filename) != os.path.normcase(module_file):
            return fr.function
    return "?"


class _ScriptedTask:
    def __init__(self, rig, n):
        self.rig, self.n = rig, n

    def read(self, n=None):
        return self.rig.next_read(self.n)

    def wait_until_done(self, *a, **k):
        pass

    def close(self):
        pass


class GridChainRig:
    """Usar como contexto: instala los dobles con `monkeypatch` y arma los hilos."""

    def __init__(self, monkeypatch, tmp_path: Path, script=DEFAULT_SCRIPT):
        self.mp, self.tmp, self.script = monkeypatch, Path(tmp_path), tuple(script)
        self.record = ChainRecord()
        self._reads_since_open = 0
        self._lock = threading.Lock()

    # ── dobles ──
    def next_read(self, n_samples: int):
        from core.nidaq import PD_CHANS_LIST
        with self._lock:
            self._reads_since_open += 1
            k = self._reads_since_open
        node = self.backend.printingWorker.i_global if hasattr(self, "backend") else 0
        sc = self.script[node] if 0 <= node < len(self.script) else NodeScript()
        v = BASE_V
        if sc.capture_read is not None and k >= sc.capture_read:
            v = 2.0 * BASE_V
        if sc.drop_read is not None and k >= sc.drop_read:
            v = 0.3 * BASE_V
        return np.full((len(PD_CHANS_LIST), int(n_samples)), v)

    def _install(self):
        # `app.py` importa los módulos por su nombre corto (`measurements`, `trace`, `focus`): son otros objetos
        # que `modules.measurements` etc. Se parchean los módulos de las clases de los workers que se usan.
        import sys
        import config
        from core import nidaq
        meas = sys.modules[type(self.backend.printingWorker).__module__]
        trace_mod = sys.modules[type(self.backend.traceWorker).__module__]
        focus_mod = sys.modules[type(self.backend.focusWorker).__module__]

        real_write = nidaq._write_shutter_lines

        def logged_write(desired):
            self.record.do_writes.append((tuple(bool(v) for v in desired), _caller_outside(nidaq.__file__)))
            self.record.do_threads.append(threading.current_thread().name)
            return real_write(desired)
        self.mp.setattr(nidaq, "_write_shutter_lines", logged_write)

        real_mov = config.pi.MOV

        def logged_mov(axes, targets):
            self.record.moves.append(tuple(round(float(v), 4) for v in np.atleast_1d(targets)))
            return real_mov(axes, targets)
        self.mp.setattr(config.pi, "MOV", logged_mov)
        self.mp.setattr(type(config.pi), "connected", property(lambda s: True))

        # La traza lee el fotodiodo con guion, y el contador se reinicia cuando abre el obturador del nodo
        self.mp.setattr(trace_mod, "SAFE_MODE", False)
        self.mp.setattr(trace_mod, "channels_photodiodos", lambda rate, n, *a, **k: _ScriptedTask(self, n))
        real_open = trace_mod.open_shutter

        def open_and_reset(name, *a, **k):
            with self._lock:
                self._reads_since_open = 0
            return real_open(name, *a, **k)
        self.mp.setattr(trace_mod, "open_shutter", open_and_reset)

        real_meas_time = meas.time
        scaled = types.SimpleNamespace(sleep=lambda s: real_meas_time.sleep(s * SLEEP_SCALE), time=real_meas_time.time,
                                       monotonic=real_meas_time.monotonic, strftime=real_meas_time.strftime)
        self.mp.setattr(meas, "time", scaled)
        real_focus_time = focus_mod.time
        self.mp.setattr(focus_mod, "time", types.SimpleNamespace(
            sleep=lambda s: real_focus_time.sleep(s * SLEEP_SCALE), time=real_focus_time.time,
            monotonic=real_focus_time.monotonic, strftime=real_focus_time.strftime))

    # ── armado ──
    def __enter__(self):
        from PyQt6.QtCore import QThread
        import app as pyprinting_app
        self.backend = pyprinting_app.Backend()
        self._install()
        self.thread = QThread()
        self.thread.setObjectName("confocalThread")
        for w in (self.backend.focusWorker, self.backend.traceWorker, self.backend.confocalWorker,
                  self.backend.printingWorker, self.backend.dimersWorker):
            w.moveToThread(self.thread)
        self.thread.start()
        pw = self.backend.printingWorker
        pw.patternFinishedSignal.connect(lambda *a: setattr(self.record, "finished", True))
        pw.nodeStatusSignal.connect(self._on_status)
        return self

    def __exit__(self, *exc):
        from core.nidaq import close_all_shutters
        try:
            self.backend.printingWorker.is_paused = True
        except Exception:
            pass
        self.thread.quit()
        self.thread.wait(5000)
        close_all_shutters()
        return False

    def _on_status(self, i: int, status: str):
        if status in ("success", "timeout"):
            self.record.decisions[int(i)] = status
            self.record.decision_ticks[int(i)] = int(getattr(self.backend.printingWorker, "ptr", -1))

    # ── la grilla ──
    def configure(self, **overrides):
        """Los parámetros de la práctica del banco (Ronda 3 de C-01), sin autofoco salvo el inicial."""
        import config
        pw = self.backend.printingWorker
        n = len(self.script)
        params = dict(laser=config.SHUTTERS[0], mode_arg="printing", grid_x=np.arange(n, dtype=float) * 2.0,
                      grid_y=np.zeros(n), xref=40.0, yref=40.0, startX=40.0, startY=40.0, particulas=n,
                      timemax=40.0, umbral=1.5, umbral_down=0.5, stopping_mode=1, n_hold_steps=3,
                      umbral_abs_v=99.0, slope_min=0.0, autofoc=10 ** 6, adaptive_af=False, driftbool=False,
                      scanbool=False, postscanbool=False, auto_complete_enabled=False, zref=10.0,
                      new_folder=str(self.tmp), old_folder=str(self.tmp), file_path=str(self.tmp),
                      track_drift_xy=False, track_drift_z=False, track_time_volt=False, shiftx=0.0, shifty=0.0)
        params.update(overrides)
        for k, v in params.items():
            setattr(pw, k, v)
        self.backend.traceWorker.parameters([5, 5])           # steps_after, steps_before (ventanas cortas)

    def run_grid(self, timeout_s: float = 120.0) -> ChainRecord:
        from PyQt6.QtCore import QMetaObject, Qt
        from PyQt6.QtWidgets import QApplication
        pw = self.backend.printingWorker
        pw.mode_printing = "none"
        QMetaObject.invokeMethod(pw, "grid_measurment", Qt.ConnectionType.QueuedConnection)
        t_end = time.monotonic() + timeout_s
        while not self.record.finished and time.monotonic() < t_end:
            QApplication.processEvents()
            time.sleep(0.002)
        QApplication.processEvents()
        return self.record
