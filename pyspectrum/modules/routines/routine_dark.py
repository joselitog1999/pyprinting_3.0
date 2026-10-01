# -*- coding: utf-8 -*-
"""
routine_dark.py — El fondo de una rutina de grilla (R4-N; DEC-040)

`RoutineDark` lo compone cada backend (luminiscencia, crecimiento, dímeros, mapa hiperespectral):
- guarda el método y los cuadros elegidos en la fila "Fondo";
- da el estado para la fila con las condiciones que la corrida va a usar (`expected_1d_conditions`);
- verifica al iniciar: con "todo apagado" y sin un fondo válido, la rutina no arranca;
- toma el fondo ahora con su propio hilo y su sesión de hardware ([Tomar fondo ahora]);
- dentro de la corrida, `ensure` reutiliza el fondo o lo toma (obturador cerrado) con el modo de la medición;
- guarda el fondo aparte, una vez por carpeta, y da las líneas de encabezado para los txt.
`wire_row` conecta una `BackgroundRow` con su `RoutineDark`.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
from PyQt6 import QtCore
from PyQt6.QtCore import pyqtSignal, pyqtSlot

from pyspectrum.services import procedure_background as pb


class RoutineDark(QtCore.QObject):
    changed = pyqtSignal(object)        # el fondo vigente de la corrida (pb.Dark) o None
    message = pyqtSignal(str)

    def __init__(self, camera, spectrometer, session_name: str, prefix: str, parent=None, store=None,
                 read_mode: Optional[int] = None,
                 conditions_fn: Optional[Callable[[float], pb.DarkConditions]] = None):
        super().__init__(parent)
        self.read_mode = read_mode          # la rutina mide siempre en este modo (p. ej. el mapa: FVB)
        self.conditions_fn = conditions_fn  # condiciones propias (p. ej. Step & Glue: el modo y la forma vigentes)
        from pyspectrum.modules.routines.routine_thread import RoutineThread
        self.camera, self.spectrometer, self.prefix = camera, spectrometer, prefix
        self.method, self.n_frames = pb.METHOD_SHUTTER, 1
        self._store = store
        self._saved: Dict[Tuple[str, str], Path] = {}
        self._taken: Optional[pb.Dark] = None
        self.thread = RoutineThread(f"{session_name} — Fondo", self)
        self.thread.finished.connect(self._on_take_finished)

    @property
    def store(self) -> pb.DarkStore:
        return self._store if self._store is not None else pb.get_dark_store()

    def set_settings(self, method: str, n_frames: int) -> None:
        self.method, self.n_frames = method, max(1, int(n_frames))

    def conditions(self, exposure_s: float) -> pb.DarkConditions:
        from pyspectrum.modules.routines.grid_runner import expected_1d_conditions
        if self.conditions_fn is not None:
            return self.conditions_fn(exposure_s)
        if self.read_mode is not None:
            return pb.read_conditions(self.camera, (1004,), exposure_s=exposure_s, read_mode=self.read_mode)
        return expected_1d_conditions(self.camera, exposure_s)

    def status(self, exposure_s: Optional[float]) -> Tuple[str, Optional[pb.Dark], str]:
        if exposure_s is None:
            return "invalid", None, "la exposición no es un número válido"
        return self.store.status(self.conditions(exposure_s))

    def check_start(self, exposure_s: float) -> Optional[str]:
        """Con "todo apagado" la rutina no arranca sin un fondo válido. Devuelve el motivo, o None."""
        if self.method != pb.METHOD_ALL_OFF:
            return None
        state, _d, reason = self.status(exposure_s)
        if state == "valid":
            return None
        why = f" (el anterior no vale: {reason})" if state == "invalid" and reason else ""
        return (f"Falta el fondo con \"todo apagado\"{why}: apagá la lámpara y los láseres y apretá "
                f"[Tomar fondo ahora] antes de iniciar.")

    def ensure(self, runner, exposure_s: float) -> pb.Dark:
        """Dentro del cuerpo de la corrida, antes del primer espectro."""
        dark = runner.ensure_dark_1d(exposure_s, spectrometer=self.spectrometer, method=self.method,
                                     n_frames=self.n_frames, store=self.store)
        self.changed.emit(dark)
        return dark

    def ensure_with(self, expose, exposure_s: float) -> pb.Dark:
        """Como `ensure`, con la exposición del que llama (p. ej. el motor de Step & Glue). Lanza DarkError."""
        dark = pb.ensure_dark(self.camera, self.spectrometer, self.conditions(exposure_s), method=self.method,
                              n_frames=self.n_frames, expose=expose, store=self.store)
        self.changed.emit(dark)
        return dark

    def take_now(self, exposure_s: Optional[float]) -> None:
        if exposure_s is None:
            self.message.emit("No se tomó el fondo: la exposición no es un número válido.")
            return
        self._taken = None

        def body(runner, ctl):
            if self.conditions_fn is not None:
                from pyspectrum.modules.routines.grid_runner import GridAbort
                try:
                    self._taken = pb.take_dark(self.camera, self.spectrometer, self.conditions(float(exposure_s)),
                                               method=self.method, n_frames=self.n_frames, expose=runner.expose,
                                               store=self.store)
                except pb.DarkError as e:
                    raise GridAbort(f"No se pudo tomar el fondo: {e}")
            else:
                self._taken = runner.take_dark_1d(float(exposure_s), spectrometer=self.spectrometer,
                                                  method=self.method, n_frames=self.n_frames, store=self.store)
            return "done"
        err = self.thread.start(body, camera=self.camera, spectrometer=self.spectrometer, mirror=None,
                                needs_spectrometer=True, require_mirror=False, restore_mirror=False)
        if err:
            self.message.emit(f"No se tomó el fondo: {err}")

    @pyqtSlot(str)
    def _on_take_finished(self, outcome: str):
        if self._taken is not None:
            d = self._taken
            self.message.emit(f"Fondo tomado: {d.n_frames} {'cuadro' if d.n_frames == 1 else 'cuadros'} a "
                              f"{d.conditions.exposure_s:g} s, {pb.METHOD_LABELS.get(d.method, d.method)}.")
            self.changed.emit(d)
        else:
            self.message.emit("No se tomó el fondo: " + outcome.split(": ", 1)[-1])

    def discard(self, exposure_s: Optional[float]) -> None:
        if exposure_s is not None:
            self.store.discard(self.conditions(exposure_s))
        self.changed.emit(None)

    # ── guardado: el fondo aparte, una vez por carpeta ──
    def save(self, dark: Optional[pb.Dark], directory) -> Optional[Path]:
        if dark is None:
            return None
        key = (dark.id, str(Path(directory).resolve()))
        if key not in self._saved:
            self._saved[key] = pb.save_dark_npz(dark, directory, self.prefix)
        return self._saved[key]

    def header_text(self, dark: Optional[pb.Dark], directory) -> str:
        return "\n".join(pb.dark_header_lines(dark, self.save(dark, directory)))


def corrected(spec, dark: Optional[pb.Dark]):
    """crudo − fondo para el procesamiento (B3: se resta al procesar y al mostrar, nunca en lo guardado)."""
    arr = np.asarray(spec, dtype=np.float64)
    if dark is None or dark.mean.shape != arr.shape:
        return arr
    return arr - dark.mean


def wire_row(row, dark_ctl: RoutineDark, exposure: Callable[[], Optional[float]], status_label=None) -> QtCore.QTimer:
    """Conecta la fila con su rutina: botones, ajustes y el estado cada 1 s mientras la fila se ve."""
    def refresh(*_):
        state, dark, reason = dark_ctl.status(exposure())
        row.show_status(state, dark, reason)

    row.settingsChanged.connect(lambda m, n: (dark_ctl.set_settings(m, n), refresh()))
    row.takeNowRequested.connect(lambda m, n: (dark_ctl.set_settings(m, n), dark_ctl.take_now(exposure())))
    row.discardRequested.connect(lambda: (dark_ctl.discard(exposure()), refresh()))
    dark_ctl.changed.connect(refresh)
    if status_label is not None:
        dark_ctl.message.connect(status_label.setText)
    dark_ctl.set_settings(row.method(), row.n_frames())
    timer = QtCore.QTimer(row)
    timer.setInterval(1000)
    timer.timeout.connect(lambda: refresh() if row.isVisible() else None)
    timer.start()
    row._refresh = refresh
    refresh()
    return timer
