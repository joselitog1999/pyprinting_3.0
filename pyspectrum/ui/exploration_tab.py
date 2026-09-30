# -*- coding: utf-8 -*-
"""
exploration_tab.py — Pestaña 1 (Exploración): Live View 2D y ROI Vertical Automático
PySpectrum 3.0 — UNSAM Nanofotónica

Fase 2 del Rework Arquitectónico: reemplaza definitivamente el frontend legado
camera_andor.py::Frontend en la Pestaña 1. No duplica ningún control de hardware (temperatura,
exposición, EM Gain, pre-amp, etc.) — esos ya viven de forma permanente en LeftHardwarePanel
(Fase 1). Sólo contiene el visor 2D de alto rendimiento, sus herramientas de imagen y el
selector interactivo de ROI vertical, que propaga automáticamente a spectroscopy_context.

Excepción arquitectónica (tercera en este proyecto, junto a Escaneo Lineal Espectral — DEC-006 —
y Mapeo Confocal — ANOM-HYPERSPEC-01): ExplorationWorker corre en un QThread real en vez del
patrón QTimer-en-hilo-GUI usado por la mayoría de las rutinas de pyspectrum, para sostener
Live View a 20-30 fps sin arriesgar que el heartbeat de obturadores o el botón E-STOP queden
sin respuesta durante la adquisición de cada cuadro.
"""
from __future__ import annotations
import math
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional
import numpy as np
from PyQt6 import QtCore, QtWidgets
from PyQt6.QtCore import pyqtSignal, pyqtSlot, QTimer
import pyqtgraph as pg

from pyspectrum.modules.spectroscopy_context import spectroscopy_context
from pyspectrum.drivers.shamrock_driver import DEVICE, get_shamrock
from core.sif_processor import compute_robust_contrast_levels

# El pitch del detector se importa de su driver (fuente canónica única, DEC-031) en vez
# de transcribirlo acá: era una de las cinco copias que no concordaban.
from pyspectrum.drivers.andor_ccd_driver import (  # noqa: E402
    DETECTOR_PIXEL_PITCH_UM, DRV_ACQUIRING, DRV_SUCCESS, DeviceUnavailable)
from pyspectrum.drivers.live_stream import LiveFrame, LiveStopped, live_api  # noqa: E402
from pyspectrum.modules import exploration_analysis as ea  # noqa: E402

# (nombre visible, nombre interno de pyqtgraph, fuente ["" = built-in, "matplotlib" = vía mpl])
COLORMAP_OPTIONS = [
    ("Viridis", "viridis", ""),
    ("Inferno", "inferno", ""),
    ("Greys", "gray", "matplotlib"),
    ("Jet", "jet", "matplotlib"),
]


def _build_fallback_colormap(display_name: str) -> pg.ColorMap:
    """Colormap construido a mano para cuando el backend matplotlib no está disponible en el
    entorno (Greys/Jet dependen de él en pyqtgraph 0.14); nunca deja el selector sin efecto."""
    if display_name == "Greys":
        return pg.ColorMap(pos=[0.0, 1.0], color=[(0, 0, 0, 255), (255, 255, 255, 255)])
    if display_name == "Jet":
        return pg.ColorMap(
            pos=[0.0, 0.35, 0.66, 0.89, 1.0],
            color=[(0, 0, 143, 255), (0, 255, 255, 255), (255, 255, 0, 255), (255, 0, 0, 255), (128, 0, 0, 255)],
        )
    return pg.colormap.get("viridis")


def get_colormap(display_name: str) -> pg.ColorMap:
    """Resuelve un colormap por su nombre visible, con reintento de respaldo si la fuente
    (ej. matplotlib) no está disponible en el entorno."""
    for name, pg_name, source in COLORMAP_OPTIONS:
        if name == display_name:
            try:
                cmap = pg.colormap.get(pg_name, source=source) if source else pg.colormap.get(pg_name)
                if cmap is not None:
                    return cmap
            except Exception:
                pass
            return _build_fallback_colormap(display_name)
    return pg.colormap.get("viridis")


# Lazo del Live (paquete 1 de R4-M, DEC-040)
POLL_PERIOD_MS = 20            # sondeo del contador de cuadros: barato (GetAcquisitionProgress)
DISPLAY_PERIOD_S = 0.050       # la interfaz pinta como máximo cada 50 ms
STATS_PERIOD_S = 1.0


@dataclass(frozen=True)
class LiveStats:
    """Estado del Live para la línea de estado (A7). `fps` cuenta los cuadros leídos del búfer (el
    mostrado y los salteados) con el reloj de la PC, no el temporizador: no depende del índice, que vuelve
    a 0 cuando un cambio en vivo reinicia la adquisición. `shown_fps`, los cuadros que la interfaz pintó."""
    fps: float
    shown_fps: float
    index: int
    not_shown: int
    lost: int
    buffer_fill: float


def format_live_stats(st: LiveStats) -> str:
    """Texto enriquecido de la línea de estado. "Perdidos" en ámbar si hay alguno; "búfer" desde el 50 %."""
    amber = "#F9E2AF"
    lost = f"perdidos {st.lost}"
    if st.lost > 0:
        lost = f"<span style='color:{amber}; font-weight:bold;'>{lost}</span>"
    buf = f"búfer {st.buffer_fill * 100:.0f} %"
    if st.buffer_fill > 0.5:
        buf = f"<span style='color:{amber}; font-weight:bold;'>{buf}</span>"
    return (f"{st.fps:.1f} fps · mostrados {st.shown_fps:.1f}/s · cuadro #{st.index} · "
            f"sin mostrar {st.not_shown} · {lost} · {buf}")


LIVE_STATS_TOOLTIP = (
    "fps: cuadros por segundo leídos del búfer de la cámara, mostrados o no (reloj de la PC).\n"
    "mostrados: cuadros por segundo que se pintaron; se pinta como máximo cada 50 ms y sólo el último.\n"
    "cuadro #: índice del último cuadro desde que arrancó el Live.\n"
    "sin mostrar: cuadros que llegaron entre dos pinturas y no se mostraron. Es normal con exposiciones cortas.\n"
    "perdidos: cuadros que el búfer de la cámara pisó sin que se leyeran. Debería ser 0 (ámbar si no).\n"
    "búfer: fracción del búfer circular de la cámara sin leer (ámbar desde el 50 %).")


def _frame_shape(camera) -> tuple:
    """Forma del cuadro con el modo de lectura vigente, para el cuadro único."""
    fn = getattr(camera, "frame_shape", None)
    if callable(fn):
        try:
            shape = fn()
            if shape:
                return tuple(int(v) for v in shape)
        except Exception:
            pass
    from pyspectrum.ui.acquisition_setup_dialog import compute_buffer_shape
    try:
        mode = int(camera.get_read_mode())
    except Exception:
        mode = 4
    return compute_buffer_shape(mode, width=int(getattr(camera, "width", 1004)),
                                height=int(getattr(camera, "height", 1002)))


class ExplorationWorker(QtCore.QObject):
    """Motor del Live de Exploración, destinado a moveToThread().

    - **Arranque (A1):** `live_api(camera).start_live()`, siempre en adquisición continua. No arranca con
      una rutina en curso ni con el E-STOP activo.
    - **Lectura (A2/A5):** cada 20 ms `read_live_frame()`, que trae sólo el cuadro más nuevo.
    - **Buzón (A3):** se guarda sólo el último cuadro y se emite `frameReadySignal` (sin datos) si no hay
      otro aviso pendiente y pasaron 50 ms del anterior; la interfaz lo toma con `take_frame()`. Con el
      visor oculto se sigue leyendo (el puntero avanza) pero no se avisa.
    - **Estadísticas (A7):** `statsSignal(LiveStats)` una vez por segundo.
    - **Pausa por una rutina:** `halt_now()` se puede llamar desde cualquier hilo y es sincrónica: al
      volver, la cámara ya se detuvo y el obturador del espectrómetro ya se cerró. Un sondeo o una orden
      del botón que lleguen tarde no hacen nada.
    - **Herramientas (paquete 2 de R4-M):**
      - traza en el tiempo de una fila o de la media del ROI, con cada cuadro leído (también con la
        pestaña oculta);
      - fondo: promedia los próximos n cuadros distintos del Live y lo descarta si una condición cambió
        durante la captura. El obturador lo cierra el operador; acá sólo se lee y se registra;
      - cuadro único con el Live detenido, abriendo y cerrando el obturador del espectrómetro como el Live.

    El QTimer se crea en start_live(), ya en el hilo del worker, para que quede afín a ese hilo.
    """

    frameReadySignal = pyqtSignal()
    statsSignal = pyqtSignal(object)
    liveErrorSignal = pyqtSignal(str)  # motivo por el que el Live no arrancó o se detuvo
    backgroundReadySignal = pyqtSignal(object)   # ea.Background
    messageSignal = pyqtSignal(str)              # avisos de las herramientas (fondo, cuadro único)

    def __init__(self, camera: Any, spectrometer: Optional[Any] = None, parent=None, *,
                 session: Optional[Any] = None, clock: Callable[[], float] = time.monotonic):
        super().__init__(parent)
        self.camera = camera
        self.spectrometer = spectrometer if spectrometer is not None else get_shamrock()
        if session is None:
            from pyspectrum.modules.hardware_session import hardware_session as session
        self._session = session
        self._clock = clock
        self._timer: Optional[QTimer] = None
        self._state_lock = threading.Lock()
        self._active = False
        self._mail_lock = threading.Lock()
        self._mailbox = None
        self._pending = False
        self._last_notice = float("-inf")
        self._visible = True
        self._reset_stats()
        self._trace_lock = threading.Lock()
        self._trace = ea.RoiTrace()
        self._trace_source: Optional[ea.TraceSource] = None
        self._bg_acc: Optional[ea.BackgroundAccumulator] = None

    # ── Estado ────────────────────────────────────────────────────────────
    @property
    def active(self) -> bool:
        return self._active

    def set_display_visible(self, visible: bool) -> None:
        """La interfaz avisa si el visor se ve (cambio de pestaña). Se puede llamar desde cualquier hilo."""
        self._visible = bool(visible)
        if not visible:
            with self._mail_lock:
                self._mailbox = None

    def _reset_stats(self) -> None:
        now = self._clock()
        self._st_t0, self._st_frames, self._st_shown = now, 0, 0
        self._st_last = None
        self._not_shown_total = 0

    def _close_shutter(self) -> None:
        try:
            from pyspectrum.services.spectrometer_shutter import close_spectrometer_shutter
            res = close_spectrometer_shutter(self.camera, self.spectrometer)
            if not res.ok:
                self.liveErrorSignal.emit(res.detail)
        except Exception as exc:
            self.liveErrorSignal.emit(f"El obturador del espectrómetro no confirmó el cierre: {exc}")

    # ── Arranque y parada ─────────────────────────────────────────────────
    @pyqtSlot()
    def start_live(self):
        # Sin cámara conectada el Live no arranca (DEC-040): antes leía cuadros de ceros, o del
        # simulador, cada 35 ms como si fueran del detector.
        if not getattr(self.camera, "available", True):
            self.liveErrorSignal.emit(
                "Live no disponible: " + (getattr(self.camera, "unavailable_reason", "") or "la cámara no está conectada."))
            return
        live = live_api(self.camera)
        with self._state_lock:
            if self._active:
                return
            if bool(getattr(self._session, "estopped_nowait", False)):
                self.liveErrorSignal.emit("Live no disponible: la parada de emergencia está activa. Rearmá el sistema.")
                return
            if bool(getattr(self._session, "busy_nowait", False)):
                self.liveErrorSignal.emit("Live no disponible: una rutina está usando la cámara.")
                return
            try:
                # El obturador del espectrómetro se abre en el Live (investigador, 2026-09-29), por los dos
                # caminos del legado: USB del Shamrock y TTL de la cámara.
                from pyspectrum.services.spectrometer_shutter import open_spectrometer_shutter
                res = open_spectrometer_shutter(self.camera, self.spectrometer)
                if not res.ok:
                    self.liveErrorSignal.emit(res.detail)
            except Exception:
                pass
            code = live.start_live()
            if code != DRV_SUCCESS:
                self._close_shutter()
                hint = (" Otro Live (¿Raman?) o una rutina usa la cámara." if code == DRV_ACQUIRING else "")
                self.liveErrorSignal.emit(f"Live no arrancó: la cámara devolvió {code}.{hint}")
                return
            self._active = True
            with self._mail_lock:
                self._mailbox, self._pending, self._last_notice = None, False, float("-inf")
            self._reset_stats()
        if self._timer is None:
            self._timer = QTimer(self)
            self._timer.setInterval(POLL_PERIOD_MS)
            self._timer.timeout.connect(self._poll)
        self._timer.start()

    def halt_now(self) -> bool:
        """Detiene el Live de inmediato, desde cualquier hilo. Devuelve si había un Live que detener."""
        with self._state_lock:
            if not self._active:
                return False
            self._active = False
            live_api(self.camera).stop_live()
            self._close_shutter()
            self._cancel_background("el Live se detuvo")
        QtCore.QMetaObject.invokeMethod(self, "_stop_timer", QtCore.Qt.ConnectionType.QueuedConnection)
        return True

    @pyqtSlot()
    def _stop_timer(self):
        if self._timer is not None:
            self._timer.stop()

    @pyqtSlot()
    def stop_live(self):
        self.halt_now()
        self._stop_timer()

    @pyqtSlot(bool)
    def set_live(self, active: bool):
        self.start_live() if active else self.stop_live()

    def _fail(self, message: str) -> None:
        """El Live se cae solo: se detiene, se cierra el obturador y se avisa. Llamar con el lock tomado."""
        self._active = False
        self._cancel_background("el Live se detuvo")
        try:
            live_api(self.camera).stop_live()
        except Exception:
            pass
        self._close_shutter()
        self.liveErrorSignal.emit(message)

    # ── Lazo ──────────────────────────────────────────────────────────────
    @pyqtSlot()
    def _poll(self):
        lf = None
        with self._state_lock:
            if not self._active:
                return
            try:
                lf = live_api(self.camera).read_live_frame()
            except LiveStopped as exc:
                self._fail(f"Live detenido: {exc}.")
            except DeviceUnavailable as exc:
                self._fail(f"Live detenido: {exc}")
            except Exception as exc:
                self._fail(f"Live detenido: error al leer el cuadro ({exc}).")
            if not self._active:
                self._stop_timer()
                return
        now = self._clock()
        if lf is not None:
            self._not_shown_total += int(lf.not_shown)
            self._st_frames += int(lf.not_shown) + 1
            self._st_last = lf
            self._feed_tools(lf)
            if self._visible:
                with self._mail_lock:
                    self._mailbox = lf
        self._maybe_notify(now)
        self._maybe_stats(now)

    def _maybe_notify(self, now: float) -> None:
        with self._mail_lock:
            if self._mailbox is None or self._pending or now - self._last_notice < DISPLAY_PERIOD_S:
                return
            self._pending, self._last_notice = True, now
        self.frameReadySignal.emit()

    def _maybe_stats(self, now: float) -> None:
        dt = now - self._st_t0
        if dt < STATS_PERIOD_S or self._st_last is None:
            return
        last = self._st_last
        self.statsSignal.emit(LiveStats(
            fps=self._st_frames / dt, shown_fps=self._st_shown / dt, index=int(last.index),
            not_shown=self._not_shown_total, lost=int(last.lost_total), buffer_fill=float(last.buffer_fill)))
        self._st_t0, self._st_frames, self._st_shown = now, 0, 0

    # ── Herramientas (paquete 2 de R4-M) ──────────────────────────────────
    def set_trace_source(self, source: Optional[ea.TraceSource]) -> None:
        """Fila o ROI de la traza; None la apaga. Otra fuente es otra magnitud: la traza se limpia."""
        with self._trace_lock:
            if source != self._trace_source:
                self._trace_source = source
                self._trace.clear()

    def clear_trace(self) -> None:
        with self._trace_lock:
            self._trace.clear()

    def trace_points(self, window_s: float):
        with self._trace_lock:
            return self._trace.points(window_s)

    def _shutter_note(self) -> str:
        fn = getattr(self.spectrometer, "ShamrockGetShutter", None)
        if fn is None:
            return "estado del obturador del espectrómetro no disponible"
        try:
            ret, state = fn(0)
        except Exception as exc:
            return f"estado del obturador no leído ({exc})"
        if ret != 20202:
            return f"estado del obturador no leído (código {ret})"
        return ("obturador del espectrómetro ABIERTO (USB): ¿seguro que es fondo?" if int(state) == 1
                else "obturador del espectrómetro cerrado (USB)")

    @pyqtSlot(int)
    def request_background(self, n_frames: int):
        """Empieza a promediar los próximos `n_frames` cuadros del Live como fondo."""
        if not self._active:
            self.messageSignal.emit("El fondo se toma con el Live corriendo: iniciá el Live y cerrá el obturador.")
            return
        settings = ea.snapshot_settings(self.camera, self.spectrometer, None)
        note = self._shutter_note()
        self._bg_acc = ea.BackgroundAccumulator(int(n_frames), settings, note)
        self.messageSignal.emit(f"Tomando fondo: {int(n_frames)} cuadros · {note}")

    def _cancel_background(self, why: str) -> None:
        if self._bg_acc is not None:
            self._bg_acc = None
            self.messageSignal.emit(f"Fondo cancelado: {why}.")

    def _feed_tools(self, lf) -> None:
        with self._trace_lock:
            src = self._trace_source
            if src is not None:
                self._trace.append(lf.t_host, lf.index, ea.trace_value(lf.data, src))
        acc = self._bg_acc
        if acc is None:
            return
        try:
            bg = acc.add(lf.data, lf.index, lf.t_host)
        except ValueError as exc:
            self._bg_acc = None
            self.messageSignal.emit(f"Fondo descartado: {exc}.")
            return
        if bg is None:
            return
        self._bg_acc = None
        from dataclasses import replace
        shape = tuple(int(v) for v in np.shape(lf.data))
        ref = replace(bg.settings, shape=shape)
        diffs = ea.settings_differences(ref, ea.snapshot_settings(self.camera, self.spectrometer, shape))
        if diffs:
            self.messageSignal.emit("Fondo descartado: cambió durante la captura (" + "; ".join(diffs) + ").")
            return
        self.backgroundReadySignal.emit(replace(bg, settings=ref))
        self.messageSignal.emit(f"Fondo listo: {bg.n_frames} cuadros · {bg.shutter_note}")

    @pyqtSlot()
    def snap(self):
        """Un cuadro con la exposición del panel, con el Live detenido (B7)."""
        from pyspectrum.modules.acquisition import ExposureRequest, Frame, single_exposure
        if self._active:
            self.messageSignal.emit("Cuadro único: detené el Live primero.")
            return
        if not getattr(self.camera, "available", True):
            self.messageSignal.emit("Cuadro único no disponible: la cámara no está conectada.")
            return
        if bool(getattr(self._session, "estopped_nowait", False)):
            self.messageSignal.emit("Cuadro único no disponible: la parada de emergencia está activa.")
            return
        if bool(getattr(self._session, "busy_nowait", False)):
            self.messageSignal.emit("Cuadro único no disponible: una rutina está usando la cámara.")
            return
        shape = _frame_shape(self.camera)
        exposure = float(self.camera.get_exposure_time())
        try:
            from pyspectrum.services.spectrometer_shutter import open_spectrometer_shutter
            res = open_spectrometer_shutter(self.camera, self.spectrometer)
            if not res.ok:
                self.messageSignal.emit(res.detail)
            out = single_exposure(self.camera, ExposureRequest(exposure, shape),
                                  is_estopped=lambda: bool(getattr(self._session, "estopped_nowait", False)))
        finally:
            self._close_shutter()
        if not isinstance(out, Frame):
            self.messageSignal.emit(f"Cuadro único falló: {out.kind.value} · {out.detail}")
            return
        data = np.asarray(out.data, dtype=np.float32)
        if data.ndim == 1:
            data = data.reshape(1, -1)
        lf = LiveFrame(data, int(out.frame_index) if out.frame_index is not None else -1, self._clock())
        with self._mail_lock:
            self._mailbox, self._pending, self._last_notice = lf, True, self._clock()
        self.frameReadySignal.emit()
        self.messageSignal.emit(f"Cuadro único: {out.exposure_s_actual:g} s de exposición.")

    def take_frame(self):
        """La interfaz toma el último cuadro del buzón (hilo de la GUI)."""
        with self._mail_lock:
            lf, self._mailbox, self._pending = self._mailbox, None, False
        if lf is not None:
            self._st_shown += 1
        return lf


try:
    from config import EXPLORATION_DISPLAY_FLIP_X as DISPLAY_FLIP_X
except Exception:          # sin config (herramientas sueltas): el régimen de BANCO-56
    DISPLAY_FLIP_X = True

FIT_MIN_PERIOD_S = 0.1          # el ajuste se recalcula como máximo 10 veces por segundo
BACKGROUND_CHECK_MS = 1000      # validez del fondo contra las condiciones actuales
_AMBER, _RED, _GREEN, _DIM = "#F9E2AF", "#F38BA8", "#A6E3A1", "#A6ADC8"
_RULER_PEN = pg.mkPen("#F9E2AF", width=1)
_TRACE_PEN = pg.mkPen("#FAB387", width=1, style=QtCore.Qt.PenStyle.DotLine)
_ROI_PEN = pg.mkPen("#89B4FA", width=1, style=QtCore.Qt.PenStyle.DashLine)
_FIT_PEN = pg.mkPen("#F38BA8", width=2, style=QtCore.Qt.PenStyle.DashLine)


class WavelengthAxisItem(pg.AxisItem):
    """Eje inferior del perfil horizontal. Con λ, las marcas caen en valores redondos de nm, ubicadas en su
    píxel con el eje del Shamrock: el perfil queda alineado columna a columna con la imagen (eje X
    vinculado) aunque λ(px) no sea lineal. Sin λ, marcas de px normales."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._lam: Optional[np.ndarray] = None
        self.enableAutoSIPrefix(False)

    def set_wavelengths(self, lam) -> None:
        self._lam = None if lam is None else np.asarray(lam, dtype=float)
        self.picture = None
        self.update()

    def tickValues(self, minVal, maxVal, size):
        if self._lam is None:
            return super().tickValues(minVal, maxVal, size)
        n = self._lam.size
        idx = np.arange(n, dtype=float)
        lo, hi = max(0.0, min(minVal, maxVal)), min(n - 1.0, max(minVal, maxVal))
        if hi <= lo:
            return []
        l0, l1 = np.interp([lo, hi], idx, self._lam)
        lmin, lmax = min(l0, l1), max(l0, l1)
        order = np.argsort(self._lam)
        lam_s, idx_s = self._lam[order], idx[order]
        out = []
        for spacing, vals in super().tickValues(lmin, lmax, size):
            out.append((spacing, [float(np.interp(v, lam_s, idx_s)) for v in vals if lmin <= v <= lmax]))
        return out

    def tickStrings(self, values, scale, spacing):
        if self._lam is None:
            return super().tickStrings(values, scale, spacing)
        lam = np.interp(values, np.arange(self._lam.size, dtype=float), self._lam)
        dec = max(0, int(math.ceil(-math.log10(spacing)))) if spacing and spacing > 0 else 1
        return [f"{v:.{dec}f}" for v in lam]


def _fmt_counts(v: float) -> str:
    return f"{v:,.0f}".replace(",", " ")


class ExplorationTabWidget(QtWidgets.QWidget):
    """Pestaña 1 (Exploración): visor 2D, ROI vertical y las herramientas del paquete 2 de R4-M.

    - Regla en cruz: un clic en la imagen la lleva al punto. Perfil horizontal abajo (eje X vinculado) y
      vertical al costado (eje Y vinculado), promediados en una banda. En el perfil vertical se ven las
      líneas del ROI, fijas (R4-M 1).
    - Eje del perfil horizontal: λ en primer orden, px en orden cero (R4-M 2).
    - Ajuste gaussiano de los dos perfiles (R4-M 3) con el estimador de la calibración.
    - Saturación sobre el crudo, siempre. Niveles: manual, auto 1–99 % o ADC completo. Congelar.
    - Cuadro único con el Live detenido. Fondo en las mismas condiciones, restado sólo si sigue válido.
    - Traza en el tiempo de una fila propia o de la media del ROI vertical (R4-M 3).
    - Guardar cuadro: HDF5 automático en work_dir/exploration, con la ruta en la barra de estado.
    - La vista está invertida en X (config.EXPLORATION_DISPLAY_FLIP_X, BANCO-56); los datos no.
    Sin controles de hardware duplicados con LeftHardwarePanel."""

    liveToggledSignal = pyqtSignal(bool)
    snapRequestedSignal = pyqtSignal()
    backgroundRequestedSignal = pyqtSignal(int)
    statusMessageSignal = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._last_frame: Optional[np.ndarray] = None      # lo que se muestra (crudo o crudo − fondo)
        self._last_raw: Optional[np.ndarray] = None
        self._last_lf = None
        self._frozen_pending = None
        self._live_source: Optional[ExplorationWorker] = None
        self._axis_provider = None
        self._settings_provider = None
        self.profile_axis: Optional[ea.ProfileAxis] = None
        self._axis_width: Optional[int] = None
        self._axis_mode: Optional[str] = None
        self._last_position = None       # (λc, red) del último spectrographMoved atendido
        self.background: Optional[ea.Background] = None
        self._bg_valid = False
        self._last_fit_t = float("-inf")
        self._hfit = self._vfit = None
        self.data_dir: Optional[Path] = None
        self.setStyleSheet("""
            QLabel { color: #CDD6F4; }
            QPushButton, QToolButton {
                background-color: #313244; color: #CDD6F4; border: 1px solid #45475A;
                border-radius: 4px; padding: 5px 10px; font-weight: bold;
            }
            QPushButton:hover, QToolButton:hover { background-color: #45475A; color: #89B4FA; }
            QPushButton:checked, QToolButton:checked { background-color: #89B4FA; color: #11111B; }
            QPushButton:disabled { color: #6C7086; }
            QComboBox, QSpinBox { background-color: #11111B; color: #CDD6F4; border: 1px solid #45475A; border-radius: 4px; padding: 3px 6px; }
        """)
        self._setup_ui()
        self._bg_timer = QTimer(self)
        self._bg_timer.setInterval(BACKGROUND_CHECK_MS)
        self._bg_timer.timeout.connect(self._check_background)
        # Método ligado, no lambda: spectroscopy_context es global y un lambda que captura el widget lo
        # mantendría vivo y conectado después de destruirlo (una pestaña por cada ventana creada).
        spectroscopy_context.spectrographMoved.connect(self._on_spectrograph_moved)

    # ── Construcción ──────────────────────────────────────────────────────
    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # ── Cabecera: Live View, herramientas de imagen ────────
        header = QtWidgets.QHBoxLayout()

        self.btn_live = QtWidgets.QPushButton("▶️ Iniciar Live View")
        self.btn_live.setCheckable(True)
        self.btn_live.setToolTip("Inicia o detiene la adquisición continua (Live View) del detector.")
        self.btn_live.clicked.connect(self._on_toggle_live)
        header.addWidget(self.btn_live)

        self.btn_snap = QtWidgets.QPushButton("📷 Cuadro único")
        self.btn_snap.setToolTip(
            "Toma un cuadro con la exposición del panel, con el Live detenido.\n"
            "Abre el obturador del espectrómetro para el cuadro y lo cierra después, como el Live.\n"
            "No se puede con una rutina en curso ni con la parada de emergencia activa.")
        self.btn_snap.clicked.connect(self.snapRequestedSignal.emit)
        header.addWidget(self.btn_snap)

        self.btn_freeze = QtWidgets.QPushButton("❄ Congelar")
        self.btn_freeze.setCheckable(True)
        self.btn_freeze.setToolTip(
            "Deja de pintar para mirar el cuadro con calma. El Live y la traza siguen;\n"
            "al descongelar se muestra el último cuadro.")
        self.btn_freeze.toggled.connect(self._on_freeze_toggled)
        header.addWidget(self.btn_freeze)

        header.addWidget(QtWidgets.QLabel("Niveles:"))
        self.cmb_levels = QtWidgets.QComboBox()
        for text, mode in (("Manual (histograma)", "manual"), ("Auto 1–99 %", "auto"), ("ADC completo", "adc")):
            self.cmb_levels.addItem(text, mode)
        self.cmb_levels.setToolTip(
            "Manual: mandan los topes del histograma de la derecha.\n"
            "Auto 1–99 %: percentiles robustos de cada cuadro pintado.\n"
            "ADC completo: 0 a 16 383 cuentas, para ver cuánto falta para saturar.")
        self.cmb_levels.currentIndexChanged.connect(lambda _i: self._repaint_levels())
        header.addWidget(self.cmb_levels)

        header.addWidget(QtWidgets.QLabel("Colormap:"))
        self.cmb_colormap = QtWidgets.QComboBox()
        self.cmb_colormap.addItems([name for name, _, _ in COLORMAP_OPTIONS])
        self.cmb_colormap.currentTextChanged.connect(self._on_colormap_changed)
        header.addWidget(self.cmb_colormap)

        self.btn_autorange = QtWidgets.QPushButton("🔍 Auto-Rango")
        self.btn_autorange.setToolTip("Ajusta la vista para encuadrar la imagen completa.")
        self.btn_autorange.clicked.connect(self._on_autorange)
        header.addWidget(self.btn_autorange)

        self.btn_autolevels = QtWidgets.QPushButton("🎚️ Auto-Contraste")
        self.btn_autolevels.setToolTip("Recalcula una vez los niveles con percentiles robustos (1–99%) del cuadro actual.")
        self.btn_autolevels.clicked.connect(self._on_autolevels)
        header.addWidget(self.btn_autolevels)

        self.btn_crosshair = QtWidgets.QPushButton("✛ Retícula Slit")
        self.btn_crosshair.setCheckable(True)
        self.btn_crosshair.setToolTip("Muestra u oculta la retícula central guía y la zona de apertura proyectada de la ranura.")
        self.btn_crosshair.clicked.connect(self._on_toggle_crosshair)
        header.addWidget(self.btn_crosshair)

        header.addWidget(QtWidgets.QLabel("🎯 Slit Objetivo:"))
        self.spin_target_slit = QtWidgets.QDoubleSpinBox()
        self.spin_target_slit.setRange(10.0, 2500.0)
        self.spin_target_slit.setValue(spectroscopy_context.slit_width_um)
        self.spin_target_slit.setSuffix(" µm")
        self.spin_target_slit.setToolTip(
            "Ancho de ranura objetivo para el experimento.\n"
            "Permite visualizar la zona donde se cerrará el slit mientras se opera con apertura amplia (ej. 2500 µm) en Orden Cero."
        )
        self.spin_target_slit.valueChanged.connect(self._on_target_slit_changed)
        header.addWidget(self.spin_target_slit)

        header.addStretch()
        layout.addLayout(header)

        # ── Fila 2: regla, ajuste, fondo, guardar ────────
        tools = QtWidgets.QHBoxLayout()
        self.chk_ruler = QtWidgets.QCheckBox("📏 Regla")
        self.chk_ruler.setChecked(True)
        self.chk_ruler.setToolTip("Regla en cruz: un clic en la imagen la lleva al punto; también se arrastran sus líneas.")
        self.chk_ruler.toggled.connect(self._on_ruler_toggled)
        tools.addWidget(self.chk_ruler)
        tools.addWidget(QtWidgets.QLabel("Banda H:"))
        self.spin_band_h = self._band_spin(
            "Filas promediadas para el perfil horizontal (impar).\n"
            "Perfil: Ī(x) = (1/B) Σ I(x, y) sobre las B filas de la banda.")
        tools.addWidget(self.spin_band_h)
        tools.addWidget(QtWidgets.QLabel("Banda V:"))
        self.spin_band_v = self._band_spin("Columnas promediadas para el perfil vertical (impar).")
        tools.addWidget(self.spin_band_v)
        self.chk_fit = QtWidgets.QCheckBox("Ajuste gaussiano")
        self.chk_fit.setToolTip(
            "Gaussiana con fondo lineal en los dos perfiles, alrededor de la regla (±50 px), con el estimador\n"
            "de la calibración de λ (estimate_line_center).\n"
            "Primer orden: centro ± u y FWHM en nm, con FWHM[nm] = FWHM[px] · |dλ/dx| en el centro.\n"
            "Orden cero y perfil vertical: FWHM en µm = FWHM[px] · 8 µm (imagen 1:1 de la ranura).\n"
            "Si el crudo satura, no se ajusta. Sin ajuste se muestran las banderas del estimador.")
        self.chk_fit.toggled.connect(lambda _c: self._refresh_analysis(force_fit=True))
        tools.addWidget(self.chk_fit)
        tools.addSpacing(12)
        tools.addWidget(QtWidgets.QLabel("Fondo:"))
        self.spin_bg_n = QtWidgets.QSpinBox()
        self.spin_bg_n.setRange(1, 100)
        self.spin_bg_n.setValue(ea.BACKGROUND_FRAMES_DEFAULT)
        self.spin_bg_n.setSuffix(" cuadros")
        self.spin_bg_n.setToolTip("Cuadros distintos del Live que se promedian para el fondo.")
        tools.addWidget(self.spin_bg_n)
        self.btn_bg_take = QtWidgets.QPushButton("Tomar fondo")
        self.btn_bg_take.setToolTip(
            "Promedia los próximos cuadros del Live como fondo. Cerrá antes el obturador del espectrómetro\n"
            "desde el panel izquierdo: acá no se acciona nada, sólo se lee y se registra su estado.\n"
            "El fondo vale mientras no cambien la exposición, la ganancia EM, el amplificador, el\n"
            "preamplificador, las velocidades HS y VS, el modo de lectura, la red ni λc.")
        self.btn_bg_take.clicked.connect(lambda: self.backgroundRequestedSignal.emit(int(self.spin_bg_n.value())))
        tools.addWidget(self.btn_bg_take)
        self.chk_bg_subtract = QtWidgets.QCheckBox("Restar")
        self.chk_bg_subtract.setEnabled(False)
        self.chk_bg_subtract.setToolTip("Muestra crudo − fondo. La saturación sigue mirando el crudo.")
        self.chk_bg_subtract.toggled.connect(lambda _c: self._repaint())
        tools.addWidget(self.chk_bg_subtract)
        self.lbl_bg_status = QtWidgets.QLabel("sin fondo")
        self.lbl_bg_status.setStyleSheet(f"color: {_DIM};")
        tools.addWidget(self.lbl_bg_status)
        tools.addStretch()
        self.btn_save = QtWidgets.QPushButton("💾 Guardar cuadro")
        self.btn_save.setToolTip(
            "Guarda en work_dir/exploration un .h5 con el cuadro crudo, el fondo aparte (si hay), el eje λ\n"
            "en primer orden, los dos cortes de la regla y la información completa de la cámara (pylablib).")
        self.btn_save.clicked.connect(self._on_save)
        tools.addWidget(self.btn_save)
        layout.addLayout(tools)

        self.lbl_roi_status = QtWidgets.QLabel("ROI Slit: [-- : --] (Centro: --, Alto: -- px)")
        self.lbl_roi_status.setStyleSheet("background-color: #11111B; padding: 4px 8px; border-radius: 4px; border: 1px solid #45475A;")
        layout.addWidget(self.lbl_roi_status)

        # ── Visor 2D con los perfiles de la regla ──
        viewer_row = QtWidgets.QHBoxLayout()
        self.graphics_widget = pg.GraphicsLayoutWidget()
        self.graphics_widget.setBackground("#11111B")
        self.plot_item = self.graphics_widget.addPlot(row=0, col=0)
        self.plot_item.setAspectLocked(False)
        self.plot_item.invertY(True)
        self.plot_item.invertX(DISPLAY_FLIP_X)
        self.plot_item.setLabel('bottom', "Pixel X (eje espectral)", color='#CDD6F4')
        self.plot_item.setLabel('left', "Pixel Y (altura de ranura)", color='#CDD6F4')

        self.image_item = pg.ImageItem()
        self.plot_item.addItem(self.image_item)

        # ROI vertical interactivo: propagación automática y silenciosa a spectroscopy_context
        self.roi_region = pg.LinearRegionItem(
            values=[480, 520], orientation=pg.LinearRegionItem.Horizontal,
            brush=pg.mkBrush(137, 180, 250, 40),
        )
        self.plot_item.addItem(self.roi_region)
        self.roi_region.sigRegionChanged.connect(self._on_roi_changed)

        # Visualización de Slit Objetivo (franja sombreada proyectada) y Retícula central guía
        c_x = spectroscopy_context.slit_center_px
        self.slit_region = pg.LinearRegionItem(
            values=[c_x - 2, c_x + 2],
            orientation=pg.LinearRegionItem.Vertical,
            brush=pg.mkBrush(243, 139, 168, 35),
            pen=pg.mkPen('#F38BA8', width=1, style=QtCore.Qt.PenStyle.DotLine),
            movable=False
        )
        self.crosshair_v = pg.InfiniteLine(pos=c_x, angle=90, pen=pg.mkPen('#F38BA8', width=1, style=QtCore.Qt.PenStyle.DashLine))
        self.crosshair_h = pg.InfiniteLine(pos=501, angle=0, pen=pg.mkPen('#F38BA8', width=1, style=QtCore.Qt.PenStyle.DashLine))
        self.slit_region.hide()
        self.crosshair_v.hide()
        self.crosshair_h.hide()
        self.plot_item.addItem(self.slit_region)
        self.plot_item.addItem(self.crosshair_v)
        self.plot_item.addItem(self.crosshair_h)

        # Regla en cruz y bandas promediadas (px del sensor)
        self.ruler_x = pg.InfiniteLine(pos=502, angle=90, movable=True, pen=_RULER_PEN)
        self.ruler_y = pg.InfiniteLine(pos=501, angle=0, movable=True, pen=_RULER_PEN)
        self.ruler_band_x = pg.LinearRegionItem(orientation=pg.LinearRegionItem.Vertical, movable=False,
                                                brush=pg.mkBrush(249, 226, 175, 25), pen=pg.mkPen(None))
        self.ruler_band_y = pg.LinearRegionItem(orientation=pg.LinearRegionItem.Horizontal, movable=False,
                                                brush=pg.mkBrush(249, 226, 175, 25), pen=pg.mkPen(None))
        for item in (self.ruler_band_x, self.ruler_band_y, self.ruler_x, self.ruler_y):
            self.plot_item.addItem(item)
        self.ruler_x.sigPositionChanged.connect(lambda *_: self._on_ruler_moved())
        self.ruler_y.sigPositionChanged.connect(lambda *_: self._on_ruler_moved())
        # Fila propia de la traza en el tiempo (sólo con la traza desplegada y la fuente "Fila")
        self.trace_row_line = pg.InfiniteLine(pos=501, angle=0, movable=True, pen=_TRACE_PEN,
                                              label="traza", labelOpts={"color": "#FAB387", "position": 0.95})
        self.trace_row_line.hide()
        self.plot_item.addItem(self.trace_row_line)
        # Cada movimiento empuja la fila; el worker limpia la traza sólo si la fila cambia de verdad.
        self.trace_row_line.sigPositionChanged.connect(lambda *_: self._push_trace_source())
        self.graphics_widget.scene().sigMouseClicked.connect(self._on_scene_clicked)

        # Perfil vertical, al costado (eje Y vinculado): valor en X, fila en Y
        self.vprofile_plot = self.graphics_widget.addPlot(row=0, col=1)
        self.vprofile_plot.setYLink(self.plot_item)
        self.vprofile_plot.invertY(True)
        self.vprofile_plot.setLabel('bottom', "cuentas", color='#CDD6F4')
        self.vprofile_plot.hideAxis('left')
        self.vprofile_curve = self.vprofile_plot.plot(pen=pg.mkPen("#A6E3A1", width=1))
        self.vfit_curve = self.vprofile_plot.plot(pen=_FIT_PEN)
        self.vprof_roi_lines = (pg.InfiniteLine(pos=480, angle=0, movable=False, pen=_ROI_PEN),
                                pg.InfiniteLine(pos=520, angle=0, movable=False, pen=_ROI_PEN))
        for line in self.vprof_roi_lines:
            self.vprofile_plot.addItem(line)
        self.vprof_cursor = pg.InfiniteLine(pos=501, angle=0, movable=False, pen=_RULER_PEN)
        self.vprofile_plot.addItem(self.vprof_cursor)

        # Perfil horizontal, abajo (eje X vinculado): λ en primer orden, px en orden cero
        self.lambda_axis = WavelengthAxisItem(orientation="bottom")
        self.hprofile_plot = self.graphics_widget.addPlot(row=1, col=0, axisItems={"bottom": self.lambda_axis})
        self.hprofile_plot.setXLink(self.plot_item)
        self.hprofile_plot.invertX(DISPLAY_FLIP_X)
        self.hprofile_plot.setLabel('left', "cuentas", color='#CDD6F4')
        self.hprofile_plot.setLabel('bottom', "px del sensor", color='#CDD6F4')
        self.hprofile_curve = self.hprofile_plot.plot(pen=pg.mkPen("#A6E3A1", width=1))
        self.hfit_curve = self.hprofile_plot.plot(pen=_FIT_PEN)
        self.hprof_cursor = pg.InfiniteLine(pos=502, angle=90, movable=False, pen=_RULER_PEN)
        self.hprofile_plot.addItem(self.hprof_cursor)

        gl = self.graphics_widget.ci.layout
        gl.setColumnStretchFactor(0, 5)
        gl.setColumnStretchFactor(1, 1)
        gl.setRowStretchFactor(0, 4)
        gl.setRowStretchFactor(1, 1)

        viewer_row.addWidget(self.graphics_widget, stretch=1)

        self.histogram = pg.HistogramLUTWidget()
        self.histogram.setBackground("#11111B")
        self.histogram.setImageItem(self.image_item)
        self.histogram.setFixedWidth(110)
        viewer_row.addWidget(self.histogram)

        layout.addLayout(viewer_row, stretch=1)

        # ── Lecturas ──
        self.lbl_readout = QtWidgets.QLabel("Regla: —")
        self.lbl_readout.setTextFormat(QtCore.Qt.TextFormat.RichText)
        self.lbl_readout.setStyleSheet("padding: 2px 8px;")
        layout.addWidget(self.lbl_readout)

        # Saturación sobre el crudo (pregunta 6 de las Rondas 2-3 del paquete 2): pico / 16 383, siempre.
        self.lbl_saturation = QtWidgets.QLabel("")
        self.lbl_saturation.setToolTip(
            "Pico del cuadro CRUDO (antes de restar el fondo) como fracción del ADC de 14 bit (16 383 cuentas),\n"
            "y cuántos píxeles llegaron al tope. Amarillo desde el 50 %, rojo desde el 80 %.\n"
            "El ADC recorta las cuentas crudas, bias incluido. Sólo informa: no detiene el Live.")
        self.lbl_saturation.hide()
        layout.addWidget(self.lbl_saturation)

        # Línea de estado del Live (A7, Ronda 3 del paquete 1)
        self.lbl_live_stats = QtWidgets.QLabel("Live detenido")
        self.lbl_live_stats.setTextFormat(QtCore.Qt.TextFormat.RichText)
        self.lbl_live_stats.setToolTip(LIVE_STATS_TOOLTIP)
        self.lbl_live_stats.setStyleSheet("color: #A6ADC8; padding: 2px 8px;")
        layout.addWidget(self.lbl_live_stats)

        # ── Traza en el tiempo (desplegable) ──
        trace_head = QtWidgets.QHBoxLayout()
        self.btn_trace_toggle = QtWidgets.QToolButton()
        self.btn_trace_toggle.setText("▸ Traza en el tiempo")
        self.btn_trace_toggle.setCheckable(True)
        self.btn_trace_toggle.setToolTip("Media de una fila (con su propia línea en la imagen) o del ROI vertical, cuadro a cuadro.")
        self.btn_trace_toggle.toggled.connect(self._on_trace_toggled)
        trace_head.addWidget(self.btn_trace_toggle)
        trace_head.addStretch()
        layout.addLayout(trace_head)

        self.trace_container = QtWidgets.QWidget()
        tv = QtWidgets.QVBoxLayout(self.trace_container)
        tv.setContentsMargins(0, 0, 0, 0)
        trow = QtWidgets.QHBoxLayout()
        trow.addWidget(QtWidgets.QLabel("Fuente:"))
        self.cmb_trace_source = QtWidgets.QComboBox()
        self.cmb_trace_source.addItem("Fila (línea propia)", "row")
        self.cmb_trace_source.addItem("Media del ROI vertical", "roi")
        self.cmb_trace_source.setToolTip(
            "Fila: la media de una sola fila, la que marca la línea naranja punteada (arrastrala).\n"
            "ROI vertical: la media de las filas del ROI en todas las columnas, en cuentas por píxel.\n"
            "Cambiar de fuente o de fila limpia la traza: es otra magnitud.")
        self.cmb_trace_source.currentIndexChanged.connect(lambda _i: self._push_trace_source())
        trow.addWidget(self.cmb_trace_source)
        trow.addWidget(QtWidgets.QLabel("Ventana:"))
        self.spin_trace_window = QtWidgets.QSpinBox()
        self.spin_trace_window.setRange(10, int(ea.TRACE_MAX_S))
        self.spin_trace_window.setValue(int(ea.TRACE_WINDOW_DEFAULT_S))
        self.spin_trace_window.setSingleStep(10)
        self.spin_trace_window.setSuffix(" s")
        trow.addWidget(self.spin_trace_window)
        self.chk_trace_pause = QtWidgets.QCheckBox("⏸ Pausar gráfico")
        self.chk_trace_pause.setToolTip("Deja quieto el gráfico; la traza se sigue registrando.")
        trow.addWidget(self.chk_trace_pause)
        self.btn_trace_clear = QtWidgets.QPushButton("🗑 Limpiar")
        self.btn_trace_clear.clicked.connect(self._on_trace_clear)
        trow.addWidget(self.btn_trace_clear)
        trow.addStretch()
        tv.addLayout(trow)
        self.trace_plot = pg.PlotWidget()
        self.trace_plot.setBackground("#11111B")
        self.trace_plot.setLabel('bottom', "t − último cuadro (s)", color='#CDD6F4')
        self.trace_plot.setLabel('left', "cuentas / px", color='#CDD6F4')
        self.trace_plot.setMinimumHeight(140)
        self.trace_curve = self.trace_plot.plot(pen=pg.mkPen("#FAB387", width=1))
        tv.addWidget(self.trace_plot)
        self.trace_container.hide()
        layout.addWidget(self.trace_container)

        spectroscopy_context.slitParametersChanged.connect(self._on_context_slit_changed)
        spectroscopy_context.colormapChanged.connect(self._on_context_colormap_changed)

        self._on_roi_changed()
        self._on_colormap_changed(self.cmb_colormap.currentText())
        self._update_slit_overlay()
        self._update_ruler_bands()

    def _band_spin(self, tooltip: str) -> QtWidgets.QSpinBox:
        spin = QtWidgets.QSpinBox()
        spin.setRange(1, ea.BAND_MAX_PX)
        spin.setSingleStep(2)
        spin.setValue(1)
        spin.setSuffix(" px")
        spin.setToolTip(tooltip)
        spin.valueChanged.connect(lambda v, s=spin: self._on_band_changed(s, v))
        return spin

    # ── Fuentes externas (la ventana o los tests) ─────────────────────────
    def set_axis_provider(self, provider) -> None:
        """`provider(width) -> ea.ProfileAxis`."""
        self._axis_provider = provider
        self._invalidate_axis()

    def set_settings_provider(self, provider) -> None:
        """`provider(shape) -> ea.CameraSettings` con las condiciones actuales (validez del fondo)."""
        self._settings_provider = provider

    def _default_axis_provider(self, width: int) -> ea.ProfileAxis:
        from pyspectrum.drivers.specular_interlock import get_interlock
        mode = get_interlock().mode
        lam = None
        spec = getattr(self._live_source, "spectrometer", None)
        if mode == "first_order" and spec is not None:
            try:
                ret, arr = spec.ShamrockGetCalibration(DEVICE, int(width))
                lam = np.asarray(arr, dtype=float) if ret == 20202 else None
            except Exception:
                lam = None
        return ea.profile_axis(mode, lam, int(width))

    def _current_settings(self, shape) -> Optional[ea.CameraSettings]:
        if self._settings_provider is not None:
            return self._settings_provider(shape)
        src = self._live_source
        if src is None:
            return None
        return ea.snapshot_settings(src.camera, src.spectrometer, shape)

    # ── Live View ──────────────────────────────────────────────────────────

    def attach_live_source(self, worker: "ExplorationWorker") -> None:
        """Conecta el buzón, las estadísticas y las herramientas del worker (paquetes 1 y 2 de R4-M)."""
        self._live_source = worker
        worker.frameReadySignal.connect(self._on_frame_ready)
        worker.statsSignal.connect(self.on_live_stats)
        worker.backgroundReadySignal.connect(self.on_background_ready)
        worker.messageSignal.connect(self.on_tool_message)
        self.snapRequestedSignal.connect(worker.snap)
        self.backgroundRequestedSignal.connect(worker.request_background)
        worker.set_display_visible(self.isVisible())
        self._push_trace_source()

    @pyqtSlot()
    def _on_frame_ready(self):
        if self._live_source is None:
            return
        lf = self._live_source.take_frame()
        if lf is not None:
            if self.btn_freeze.isChecked():
                self._frozen_pending = lf
                self.lbl_live_stats.setText(f"❄ Congelado · cuadro #{self._last_lf.index if self._last_lf else '—'}"
                                            f" · el Live sigue (último #{lf.index})")
            else:
                self._show_frame(lf.data, lf)
        self._redraw_trace()

    @pyqtSlot(object)
    def on_live_stats(self, stats: LiveStats):
        if self.btn_live.isChecked() and not self.btn_freeze.isChecked():
            self.lbl_live_stats.setText(format_live_stats(stats))

    @pyqtSlot(str)
    def on_tool_message(self, message: str):
        """Avisos del worker. Los del fondo van a su etiqueta: advertencias en ámbar, progreso en gris;
        "Fondo listo" no pisa el estado "fondo válido" que ya puso `on_background_ready`."""
        low = message.lower()
        if "fondo" in low and not low.startswith("fondo listo"):
            warn = any(k in message for k in ("descartado", "cancelado", "ABIERTO", "no leído", "Live corriendo"))
            self.lbl_bg_status.setText(message)
            self.lbl_bg_status.setStyleSheet(f"color: {_AMBER if warn else _DIM};")
        self.statusMessageSignal.emit(message)

    def showEvent(self, event):
        super().showEvent(event)
        if self._live_source is not None:
            self._live_source.set_display_visible(True)

    def hideEvent(self, event):
        super().hideEvent(event)
        if self._live_source is not None:
            self._live_source.set_display_visible(False)

    def _set_live_button(self, running: bool) -> None:
        if running:
            self.btn_live.setText("⏹️ Detener Live View")
            self.btn_live.setStyleSheet("background-color: #F38BA8; color: #11111B; font-weight: bold;")
        else:
            self.btn_live.setText("▶️ Iniciar Live View")
            self.btn_live.setStyleSheet("background-color: #313244; color: #CDD6F4; font-weight: bold;")
        self.btn_snap.setEnabled(not running)
        self.btn_snap.setToolTip(self.btn_snap.toolTip().split("\n\n")[0]
                                 + ("\n\nDeshabilitado: detené el Live primero." if running else ""))

    def _on_toggle_live(self, checked: bool):
        self._set_live_button(checked)
        self.lbl_live_stats.setText("Arrancando el Live…" if checked else "Live detenido")
        self.liveToggledSignal.emit(checked)

    def show_live_stopped(self, message: str = "Live detenido") -> None:
        """Vuelve el botón a "Iniciar" sin re-emitir la orden (p. ej. una rutina pausó el Live)."""
        self.btn_live.blockSignals(True)
        self.btn_live.setChecked(False)
        self.btn_live.blockSignals(False)
        self._set_live_button(False)
        self.lbl_live_stats.setText(message)

    @pyqtSlot(str)
    def on_live_error(self, message: str):
        """El worker no pudo arrancar o sostener el Live: vuelve el botón a "Iniciar" sin
        re-emitir la orden y deja el motivo a la vista (DEC-040)."""
        self.show_live_stopped("Live detenido")
        self.btn_live.setToolTip(message)
        self.lbl_roi_status.setText(message)

    # ── Pintura ───────────────────────────────────────────────────────────

    @pyqtSlot(np.ndarray)
    def update_image(self, img: np.ndarray):
        """Muestra un cuadro crudo (sin índice): lo usan los tests y cualquier fuente sin Live."""
        self._show_frame(img, None)

    def _show_frame(self, raw, lf) -> None:
        raw_arr = raw if np.ndim(raw) == 2 else np.asarray(raw).reshape(1, -1)
        self._last_raw = raw_arr
        self._last_lf = lf
        disp = raw_arr
        bg = self.background
        if self.chk_bg_subtract.isChecked() and bg is not None and self._bg_valid:
            if tuple(bg.data.shape) == tuple(np.shape(raw_arr)):
                disp = np.asarray(raw_arr, dtype=np.float32) - bg.data
            else:
                self._set_background_invalid(f"forma del cuadro: {tuple(bg.data.shape)} → {tuple(np.shape(raw_arr))}")
        self._last_frame = disp
        self.image_item.setImage(np.asarray(disp).T, autoLevels=False)
        self._repaint_levels()
        self._update_saturation(raw_arr)
        width = int(np.shape(raw_arr)[1])
        if self._axis_width != width or self._axis_mode_changed():
            self._refresh_axis(width)
        self._refresh_analysis()

    def _repaint(self) -> None:
        if self._last_raw is not None:
            self._show_frame(self._last_raw, self._last_lf)

    def _repaint_levels(self) -> None:
        if self._last_frame is None:
            return
        levels = ea.display_levels(self._last_frame, self.cmb_levels.currentData())
        if levels is not None:
            self.image_item.setLevels(levels)
            self.histogram.blockSignals(True)
            self.histogram.setLevels(*levels)
            self.histogram.blockSignals(False)

    def _update_saturation(self, raw: np.ndarray):
        s = ea.raw_saturation(raw)
        color = {"ok": _DIM, "warn": _AMBER, "alarm": _RED}[s.level]
        n = s.n_clipped
        text = (f"pico {_fmt_counts(s.peak_counts)} cuentas ({s.frac * 100:.0f} % del ADC) · "
                f"{n} {'píxel saturado' if n == 1 else 'píxeles saturados'}")
        if s.level == "alarm":
            text += " · saturación: bajá la luz, la exposición o la ganancia"
        self.lbl_saturation.setText(text)
        self.lbl_saturation.setStyleSheet(f"color: {color}; font-weight: bold; padding: 2px 8px;")
        self.lbl_saturation.show()

    def _on_freeze_toggled(self, frozen: bool) -> None:
        if not frozen and self._frozen_pending is not None:
            lf, self._frozen_pending = self._frozen_pending, None
            self._show_frame(lf.data, lf)
        elif frozen:
            self.lbl_live_stats.setText(f"❄ Congelado · cuadro #{self._last_lf.index if self._last_lf else '—'}")
            self._refresh_analysis(force_fit=True)

    # ── Eje del perfil horizontal ─────────────────────────────────────────
    def _axis_mode_changed(self) -> bool:
        if self._axis_provider is not None:
            return False
        from pyspectrum.drivers.specular_interlock import get_interlock
        return get_interlock().mode != self._axis_mode

    @pyqtSlot(float, int)
    def _on_spectrograph_moved(self, wavelength_nm: float, grating: int) -> None:
        # El panel izquierdo publica la posición en cada sondeo (1 s), se haya movido o no: el eje del
        # Shamrock se relee y los ajustes se rehacen sólo si cambian la red o λc.
        position = (round(float(wavelength_nm), 4), int(grating))
        if position == self._last_position:
            return
        self._last_position = position
        self._invalidate_axis()

    def _invalidate_axis(self) -> None:
        self._axis_width = None
        if self._last_raw is not None:
            self._refresh_axis(int(np.shape(self._last_raw)[1]))
            self._refresh_analysis(force_fit=True)

    def _refresh_axis(self, width: int) -> None:
        provider = self._axis_provider or self._default_axis_provider
        try:
            axis = provider(width)
        except Exception as exc:
            axis = ea.ProfileAxis("pixel", np.arange(width, dtype=float), f"no se pudo leer el eje ({exc})")
        self.profile_axis = axis
        self._axis_width = width
        if self._axis_provider is None:
            from pyspectrum.drivers.specular_interlock import get_interlock
            self._axis_mode = get_interlock().mode
        if axis.kind == "lambda":
            self.lambda_axis.set_wavelengths(axis.values)
            self.hprofile_plot.setLabel('bottom', "λ (nm) · eje del Shamrock, sin corrección fina", color='#CDD6F4')
        else:
            self.lambda_axis.set_wavelengths(None)
            self.hprofile_plot.setLabel('bottom', f"px del sensor ({axis.reason})", color='#CDD6F4')

    # ── Regla, perfiles y ajuste ──────────────────────────────────────────
    def set_ruler(self, x: float, y: float) -> None:
        for line, v in ((self.ruler_x, x), (self.ruler_y, y)):
            line.blockSignals(True)
            line.setValue(float(v))
            line.blockSignals(False)
        self._on_ruler_moved()

    def _on_scene_clicked(self, ev) -> None:
        if ev.button() != QtCore.Qt.MouseButton.LeftButton or ev.double() or not self.chk_ruler.isChecked():
            return
        pos = ev.scenePos()
        if not self.plot_item.vb.sceneBoundingRect().contains(pos):
            return
        p = self.plot_item.vb.mapSceneToView(pos)
        self.set_ruler(p.x(), p.y())

    def _on_ruler_toggled(self, on: bool) -> None:
        for item in (self.ruler_x, self.ruler_y, self.ruler_band_x, self.ruler_band_y,
                     self.hprof_cursor, self.vprof_cursor):
            item.setVisible(on)
        if not on:
            for c in (self.hprofile_curve, self.vprofile_curve, self.hfit_curve, self.vfit_curve):
                c.setData([], [])
            self.lbl_readout.setText("Regla: apagada")
        else:
            self._refresh_analysis(force_fit=True)

    def _on_band_changed(self, spin: QtWidgets.QSpinBox, value: int) -> None:
        odd = ea.odd_band(value)
        if odd != value:
            spin.blockSignals(True)
            spin.setValue(odd)
            spin.blockSignals(False)
        self._update_ruler_bands()
        self._refresh_analysis(force_fit=True)

    def _on_ruler_moved(self) -> None:
        self.hprof_cursor.setValue(self.ruler_x.value())
        self.vprof_cursor.setValue(self.ruler_y.value())
        self._update_ruler_bands()
        self._refresh_analysis(force_fit=True)

    def _update_ruler_bands(self) -> None:
        hy = ea.odd_band(self.spin_band_h.value()) / 2.0
        hx = ea.odd_band(self.spin_band_v.value()) / 2.0
        y, x = round(self.ruler_y.value()), round(self.ruler_x.value())
        self.ruler_band_y.setRegion([y - hy + 0.5, y + hy + 0.5])
        self.ruler_band_x.setRegion([x - hx + 0.5, x + hx + 0.5])

    def _ruler_px(self):
        frame = self._last_frame
        h, w = np.shape(frame)
        x = int(round(min(max(self.ruler_x.value(), 0), w - 1)))
        y = int(round(min(max(self.ruler_y.value(), 0), h - 1)))
        return x, y

    def _refresh_analysis(self, force_fit: bool = False) -> None:
        frame = self._last_frame
        if frame is None or not self.chk_ruler.isChecked():
            return
        x, y = self._ruler_px()
        hprof = ea.row_profile(frame, y, self.spin_band_h.value())
        vprof = ea.column_profile(frame, x, self.spin_band_v.value())
        self.hprofile_curve.setData(np.arange(hprof.size, dtype=float), hprof)
        self.vprofile_curve.setData(vprof, np.arange(vprof.size, dtype=float))
        self._hprof, self._vprof = hprof, vprof
        now = time.monotonic()
        if self.chk_fit.isChecked() and (force_fit or now - self._last_fit_t >= FIT_MIN_PERIOD_S):
            self._last_fit_t = now
            saturated = ea.raw_saturation(self._last_raw).level == "alarm"
            self._hfit = ea.fit_profile(hprof, seed_px=x, axis=self.profile_axis, saturated=saturated)
            self._vfit = ea.fit_profile(vprof, seed_px=y, axis=None, saturated=saturated)
            hx, hy = ea.fit_model_curve(self._hfit)
            vx, vy = ea.fit_model_curve(self._vfit)
            self.hfit_curve.setData(hx, hy)
            self.vfit_curve.setData(vy, vx)
        elif not self.chk_fit.isChecked():
            self._hfit = self._vfit = None
            self.hfit_curve.setData([], [])
            self.vfit_curve.setData([], [])
        self._update_readout(x, y)

    def _fit_text(self, name: str, fit) -> str:
        if fit is None:
            return ""
        r = fit.result
        if not r.success:
            flags = ", ".join(f for f in r.flags if f != "SEEDED_BY_OPERATOR") or "sin línea"
            return f"<br><span style='color:{_AMBER};'>{name}: sin ajuste ({flags})</span>"
        if fit.unit == "nm":
            return (f"<br>{name}: centro {fit.center:.3f} ± {fit.u_center:.3f} nm (px {fit.center_px:.2f}) · "
                    f"FWHM {fit.fwhm:.3f} nm ({fit.fwhm_px:.2f} px)")
        return (f"<br>{name}: centro px {fit.center_px:.2f} ± {r.u_center_px:.2f} · "
                f"FWHM {fit.fwhm:.1f} µm ({fit.fwhm_px:.2f} px)")

    def _update_readout(self, x: int, y: int) -> None:
        frame = self._last_frame
        value = float(np.asarray(frame)[y, x])
        where = f"x = {x} px"
        if self.profile_axis is not None and self.profile_axis.kind == "lambda":
            where += f" (λ = {float(self.profile_axis.values[x]):.3f} nm)"
        text = (f"Regla: {where} · y = {y} px · valor {_fmt_counts(value)} · bandas H {ea.odd_band(self.spin_band_h.value())}"
                f" / V {ea.odd_band(self.spin_band_v.value())} px")
        text += self._fit_text("Perfil H", self._hfit) + self._fit_text("Perfil V", self._vfit)
        self.lbl_readout.setText(text)

    # ── Fondo ─────────────────────────────────────────────────────────────
    @pyqtSlot(object)
    def on_background_ready(self, bg: ea.Background) -> None:
        self.background = bg
        self._check_background()
        self._bg_timer.start()

    def _check_background(self) -> None:
        bg = self.background
        if bg is None:
            return
        shape = tuple(np.shape(self._last_raw)) if self._last_raw is not None else bg.settings.shape
        now = self._current_settings(shape)
        ok, reason = ea.background_status(bg, now) if now is not None else (False, "no se pueden leer las condiciones")
        if ok:
            self._bg_valid = True
            self.chk_bg_subtract.setEnabled(True)
            self.lbl_bg_status.setText(f"fondo válido · {bg.n_frames} cuadros · "
                                       f"{bg.settings.exposure_s:g} s · {bg.shutter_note}")
            self.lbl_bg_status.setStyleSheet(f"color: {_GREEN};")
        else:
            self._set_background_invalid(reason)

    def _set_background_invalid(self, reason: str) -> None:
        was_subtracting = self.chk_bg_subtract.isChecked()
        self._bg_valid = False
        self.chk_bg_subtract.blockSignals(True)
        self.chk_bg_subtract.setChecked(False)
        self.chk_bg_subtract.blockSignals(False)
        self.chk_bg_subtract.setEnabled(False)
        self.lbl_bg_status.setText(f"fondo no válido: {reason}. Tomalo de nuevo o volvé a esas condiciones.")
        self.lbl_bg_status.setStyleSheet(f"color: {_AMBER};")
        if was_subtracting and self._last_raw is not None:
            self._show_frame(self._last_raw, self._last_lf)

    # ── Traza ─────────────────────────────────────────────────────────────
    def _on_trace_toggled(self, open_: bool) -> None:
        self.btn_trace_toggle.setText(("▾" if open_ else "▸") + " Traza en el tiempo")
        self.trace_container.setVisible(open_)
        self._push_trace_source()

    def _trace_source(self) -> Optional[ea.TraceSource]:
        if not self.btn_trace_toggle.isChecked():
            return None
        if self.cmb_trace_source.currentData() == "row":
            return ea.TraceSource("row", int(round(self.trace_row_line.value())))
        y1, y2 = self.roi_region.getRegion()
        return ea.TraceSource("roi", int(round(min(y1, y2))), int(round(max(y1, y2))))

    def _push_trace_source(self) -> None:
        src = self._trace_source()
        self.trace_row_line.setVisible(src is not None and src.kind == "row")
        if src is not None and src.kind == "row":
            self.trace_plot.setLabel('left', f"fila {src.a}: cuentas / px", color='#CDD6F4')
        elif src is not None:
            self.trace_plot.setLabel('left', f"ROI [{src.a} : {src.b}]: cuentas / px", color='#CDD6F4')
        if self._live_source is not None:
            self._live_source.set_trace_source(src)

    def _on_trace_clear(self) -> None:
        if self._live_source is not None:
            self._live_source.clear_trace()
        self.trace_curve.setData([], [])

    def _redraw_trace(self) -> None:
        if (self._live_source is None or not self.btn_trace_toggle.isChecked()
                or self.chk_trace_pause.isChecked()):
            return
        t, v = self._live_source.trace_points(float(self.spin_trace_window.value()))
        if t.size:
            self.trace_curve.setData(t - t[-1], v)
        else:
            self.trace_curve.setData([], [])

    # ── Guardar ───────────────────────────────────────────────────────────
    def _on_save(self) -> None:
        if self._last_raw is None:
            self.statusMessageSignal.emit("No hay cuadro para guardar: iniciá el Live o tomá un cuadro único.")
            return
        from pyspectrum.drivers.specular_interlock import get_interlock
        data_dir = Path(self.data_dir) if self.data_dir is not None else Path.home() / "Documents" / "Data_PySpectrum" / "exploration"
        raw = np.asarray(self._last_raw)
        shape = tuple(raw.shape)
        settings = self._current_settings(shape)
        x, y = self._ruler_px() if self._last_frame is not None else (None, None)
        y1, y2 = self.roi_region.getRegion()
        lf = self._last_lf
        meta = {
            "frame_index": int(lf.index) if lf is not None else -1,
            "t_host": float(lf.t_host) if lf is not None else float("nan"),
            "interlock_mode": get_interlock().mode,
            "display_flip_x": bool(DISPLAY_FLIP_X),
            "ruler_px": (x, y),
            "band_h_px": ea.odd_band(self.spin_band_h.value()),
            "band_v_px": ea.odd_band(self.spin_band_v.value()),
            "roi_rows": (int(round(min(y1, y2))), int(round(max(y1, y2)))),
            "levels_mode": self.cmb_levels.currentData(),
            "acquisition_settings": asdict_safe(settings),
        }
        full_info = {}
        cam = getattr(self._live_source, "camera", None)
        if cam is not None and hasattr(cam, "get_full_info"):
            try:
                full_info = cam.get_full_info()
            except Exception as exc:
                full_info = {"error": str(exc)}
        width = shape[1] if len(shape) > 1 else shape[0]
        axis = self.profile_axis or ea.ProfileAxis("pixel", np.arange(width, dtype=float), "sin eje")
        cuts = {}
        if getattr(self, "_hprof", None) is not None:
            cuts = {"horizontal": self._hprof, "vertical": self._vprof}
        subtract = self.chk_bg_subtract.isChecked() and self._bg_valid
        from pyspectrum.calibration.repository import spectrum_software_correction
        correction = spectrum_software_correction(getattr(self._live_source, "spectrometer", None))
        try:
            path = ea.save_exploration_h5(ea.default_save_path(data_dir), raw=raw, background=self.background,
                                          subtract=subtract, axis=axis, cuts=cuts, metadata=meta,
                                          full_info=full_info, correction=correction)
        except Exception as exc:
            self.statusMessageSignal.emit(f"No se pudo guardar el cuadro: {exc}")
            return
        self.statusMessageSignal.emit(f"Cuadro guardado: {path}")

    # ── Herramientas de imagen ────────────────────────────────────────────

    def _on_colormap_changed(self, name: str):
        cmap = get_colormap(name)
        self.histogram.gradient.setColorMap(cmap)
        spectroscopy_context.set_colormap(name)

    def _on_context_colormap_changed(self, name: str):
        if self.cmb_colormap.currentText() != name:
            self.cmb_colormap.blockSignals(True)
            self.cmb_colormap.setCurrentText(name)
            self.cmb_colormap.blockSignals(False)
            cmap = get_colormap(name)
            self.histogram.gradient.setColorMap(cmap)

    def _on_autorange(self):
        self.plot_item.getViewBox().autoRange()

    def _on_autolevels(self):
        if self._last_frame is not None:
            levels = compute_robust_contrast_levels(self._last_frame)
            self.image_item.setLevels(levels)
            self.histogram.setLevels(*levels)

    def _on_toggle_crosshair(self, checked: bool):
        if checked:
            self.crosshair_v.show()
            self.crosshair_h.show()
            self.slit_region.show()
            self.btn_crosshair.setStyleSheet("background-color: #89B4FA; color: #11111B; font-weight: bold;")
        else:
            self.crosshair_v.hide()
            self.crosshair_h.hide()
            self.slit_region.hide()
            self.btn_crosshair.setStyleSheet("background-color: #313244; color: #CDD6F4; font-weight: bold;")

    def _update_slit_overlay(self):
        w_um = float(self.spin_target_slit.value())
        center_x = float(self.crosshair_v.value())
        w_px = max(1.0, w_um / DETECTOR_PIXEL_PITCH_UM)
        half_w = w_px / 2.0
        self.slit_region.setRegion([center_x - half_w, center_x + half_w])

    def _on_target_slit_changed(self, val: float):
        self._update_slit_overlay()

    def _on_context_slit_changed(self, width_um: float, center_px: float, zero_pos: int):
        self.crosshair_v.setValue(center_px)
        self._update_slit_overlay()

    # ── ROI vertical: propagación automática y silenciosa ─────────────────

    def _on_roi_changed(self):
        y1, y2 = self.roi_region.getRegion()
        y_min, y_max = int(round(min(y1, y2))), int(round(max(y1, y2)))
        y_center = (y_min + y_max) // 2
        y_height = max(1, y_max - y_min)
        self.lbl_roi_status.setText(f"ROI Slit: [{y_min} : {y_max}] (Centro: {y_center}, Alto: {y_height} px)")
        spectroscopy_context.set_vertical_roi(y_min, y_max)
        if hasattr(self, "vprof_roi_lines"):
            self.vprof_roi_lines[0].setValue(y_min)
            self.vprof_roi_lines[1].setValue(y_max)
            if self.btn_trace_toggle.isChecked() and self.cmb_trace_source.currentData() == "roi":
                self._push_trace_source()


def asdict_safe(obj):
    if obj is None:
        return None
    from dataclasses import asdict
    return asdict(obj)
