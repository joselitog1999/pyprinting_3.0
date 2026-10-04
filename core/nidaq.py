# -*- coding: utf-8 -*-
"""
nidaq.py — Capa de abstracción NI-DAQ
PyPrinting — UNSAM Nanofotónica

En SAFE_MODE todas las funciones son no-op o devuelven datos sintéticos.
La lógica real solo se instancia si SAFE_MODE = False.

Confirmación de obturadores (DEC-036): el estado de un obturador es una afirmación que el
software sólo puede hacer después de que la escritura en la placa haya tenido éxito
(DEC-014). Un cierre que no se pudo confirmar se trata como un obturador ABIERTO: queda en
`get_unconfirmed_shutters()`, el watchdog sigue reintentando y se avisa por
`register_shutter_fault_callback()`. Fuera de SAFE_MODE no hay simulador de respaldo: una
tarea DAQmx que no se puede crear deja la placa "no disponible" y activa un interlock que
bloquea toda apertura de obturadores.
"""
from __future__ import annotations
import time
import sys
import atexit
import threading
from enum import Enum
from typing import Callable, Optional, NamedTuple
import numpy as np

# Unificar 'nidaq' y 'core.nidaq' en sys.modules para evitar instancias duplicadas
if __name__ == "core.nidaq":
    sys.modules["nidaq"] = sys.modules[__name__]
elif __name__ == "nidaq":
    sys.modules["core.nidaq"] = sys.modules[__name__]

from core import estop_state

from config import (
    SAFE_MODE, NIDAQ_DEVICE, SHUTTERS, SHUTTER_CHANNELS, SHUTTER_POLARITY,
    FLIPPER_532_CHAN, FLIPPER_AO_UP, FLIPPER_AO_DOWN,
    PD_CHANS_LIST, PD_CHANNELS, TRIGGER_CHANNELS,
    RATE_MULTICHANNEL, LASER_532_V_MIN, LASER_532_V_MAX,
)

# ══════════════════════════════════════════════════════════════════════════════
#  MOCK NI-DAQ TASK  — misma interfaz que nidaqmx.Task
# ══════════════════════════════════════════════════════════════════════════════

class _MockNITask:
    """
    Simula una nidaqmx.Task de lectura analógica.
    read() devuelve ruido gaussiano suave por canal + un canal de trigger
    con pulsos sintéticos para que los algoritmos de perfil z funcionen.
    """
    def __init__(self, n_channels: int, samps: int):
        self._n_ch  = n_channels
        self._samps = samps

    def read(self, samps: int = None):
        n = samps or self._samps
        # Canales de fotodiodo: nivel base 0.5 V + ruido pequeño
        base = 0.5 + 0.02 * np.random.randn(self._n_ch - 1, n)
        # Una tarea configurada como rampa (autofoco en Z, escaneo confocal en X/Y; `channels_triggers`) ve un pico
        # gaussiano en el centro de la ida y de la vuelta, como una NP en foco (R4-17 fase 5): así el autofoco y la
        # corrección de deriva simulados pasan los topes de plausibilidad. La traza no configura rampa: no cambia.
        if getattr(self, "_ramp_axis", None):
            base = base + _synthetic_ramp_peaks(n)
        channels = [list(row) for row in base]
        # Último canal = trigger sintético con dos pulsos (ida y vuelta)
        trigger = _synthetic_trigger(n)
        channels.append(list(trigger))
        return channels

    def wait_until_done(self): pass
    def close(self): pass
    def start(self): pass
    def stop(self): pass
    def write(self, *a, **k): pass


class _UnavailableNITask(_MockNITask):
    """Tarea de lectura que representa una placa NO disponible en producción (DEC-036).

    Existe sólo para que un llamador que no verifica errores no rompa la aplicación (una
    excepción no manejada dentro de un slot de PyQt6 aborta el proceso sin ejecutar atexit,
    es decir, sin el cierre de emergencia de obturadores). No simula nada: read() devuelve
    NaN en todos los canales, de modo que ningún algoritmo pueda tomar el ruido por datos.
    Crearla implica que la placa está en falla y que el interlock de obturadores está activo.
    """
    def read(self, samps: int = None):
        n = samps or self._samps
        return [[float("nan")] * n for _ in range(self._n_ch)]


def _synthetic_ramp_peaks(n: int) -> np.ndarray:
    """Un pico gaussiano (1 V) en el centro de cada ventana del trigger sintético (ida y vuelta)."""
    out = np.zeros(n, dtype=float)
    if n < 4:
        return out
    for a, b in ((int(n * 0.15), int(n * 0.45)), (int(n * 0.55), int(n * 0.85))):
        c, sigma = 0.5 * (a + b), max(1.0, (b - a) / 25.0)
        idx = np.arange(a, b)
        out[a:b] = np.exp(-0.5 * ((idx - c) / sigma) ** 2)
    return out


def _synthetic_trigger(n: int) -> np.ndarray:
    """Genera una señal de trigger sintético con dos pulsos cuadrados limpios (ida y vuelta)
    para que los algoritmos de extracción por flancos en confocal funcionen correctamente."""
    t = np.zeros(n, dtype=float)
    if n < 4:
        return t
    q1, q2 = int(n * 0.15), int(n * 0.45)
    q3, q4 = int(n * 0.55), int(n * 0.85)
    t[q1:q2] = 5.0
    t[q3:q4] = 5.0
    return t


# ══════════════════════════════════════════════════════════════════════════════
#  INICIALIZACIÓN CONDICIONAL DE TASKS REALES
# ══════════════════════════════════════════════════════════════════════════════

if not SAFE_MODE:
    import nidaqmx
    from nidaqmx.constants import LineGrouping, AcquisitionType

# Valor COMANDADO de cada línea de obturador (lo que se escribe en la placa, las cuatro
# líneas a la vez). No es por sí solo el estado confirmado: ver _unconfirmed_shutters.
_shutter_signal: list[bool]       = [not SHUTTER_POLARITY[s] for s in SHUTTERS]
_flipper_notch532_up: bool        = True
# Creencia sobre el espejo de detección (D-10, C-08). El espejo es un MFF101 conmutador sin realimentación
# (BANCO-21): el software sólo sabe lo que ordenó. "none" = sin información (posición "unknown").
_mirror_belief_source: str       = "none"
_mirror_belief_since = None
# Último estado conocido de una sesión anterior (R4-N 3; core/detection_mirror_state.py): se muestra como
# "último conocido, sin confirmar" y guía el próximo pulso, pero la posición que leen las rutinas sigue
# siendo "unknown" hasta que el operador confirme o el software lo mueva (D-01).
_mirror_last_known = None             # SavedMirrorState o None
_flipper_high_power: bool         = False
_shutter_task                     = None
_flipper_task0                    = None
_flipper_task1                    = None
_flipper532_task                  = None
_laser532_task                    = None

_nidaq_lock                       = threading.RLock()
_watchdog_active: bool            = True
_watchdog_deadline: float | None  = None
_watchdog_lock                    = threading.Lock()
_watchdog_callbacks: list[Callable[[], None]] = []
_flipper_callbacks: list[Callable[[bool], None]] = []

# ── Confirmación de obturadores e interlocks (DEC-036) ───────────────────────
SHUTTER_CLOSE_RETRIES = 3          # escrituras por cierre antes de declararlo sin confirmar
SHUTTER_RETRY_DELAY_S = 0.05       # espera entre esos intentos
WATCHDOG_RETRY_INTERVAL_S = 1.0    # reintento del watchdog mientras quede un cierre sin confirmar

# Obturadores cuyo cierre no se pudo confirmar: se tratan como ABIERTOS hasta que una escritura
# posterior (que siempre lleva "cerrar" en su línea) tenga éxito.
_unconfirmed_shutters: set[str]   = set()
_retry_due: float | None          = None
_shutter_fault_callbacks: list[Callable[[str, str, bool], None]] = []
# Fuentes que bloquean toda apertura de obturadores (p.ej. "NI-DAQmx", "Platina PI").
_shutter_interlocks: dict[str, str] = {}
_DAQ_INTERLOCK = "NI-DAQmx"

# Política global de auto-cierre (SYS-201): fuente única de verdad para el timeout que
# open_shutter()/heartbeat_shutter() usan cuando se llaman SIN un timeout_s explícito.
# Antes, ambas funciones hardcodeaban 30.0 como default de parámetro, así que cualquier
# rutina experimental que abriera un shutter sin pasar timeout_s reseteaba silenciosamente
# la política "Sin límite (Modo Alineación)" elegida por el usuario en el dock de Shutters
# (core/shutters.py::Backend.set_autoclose_timeout) en cuanto arrancaba. Ver DECISION_LOG.
_default_timeout_s: float | None  = 30.0
_SENTINEL = object()


# ── Época de cierre y retención de apertura (C-01 Ronda 4, R4-17 fase 3; DEC-046) ─────────────
class CloseCause(str, Enum):
    """Quién pidió un cierre. La política de la grilla por causa está en `core/grid_state.py::CAUSE_POLICY`."""
    OPERATOR = "operator"        # "Cerrar todos" o un botón del dock
    ESTOP = "estop"              # parada de emergencia (fase 4)
    WATCHDOG = "watchdog"
    INTERLOCK = "interlock"
    ROUTINE = "routine"          # una rutina o un camino sin causa propia
    EXCEPTHOOK = "excepthook"
    EXIT = "exit"
    STAGE = "stage"


class CloseEpoch(NamedTuple):
    epoch: int
    cause: CloseCause
    detail: str
    t_mono: float


OPERATOR_HOLD_S = 3.0              # [INV-R4] 5: "Cerrar todos" con una rutina corriendo retiene las aperturas 3 s

# La época crece con cada pedido de cierre, ANTES de tomar _nidaq_lock: quien anotó la época al abrir sabe que
# hubo un cierre aunque el que cierra todavía espere la placa. Monótona: no hay bandera que limpiar ni dueño.
# Se reemplaza entera (lectura sin candado); los escritores se serializan con _epoch_lock, que nunca se anida
# con _nidaq_lock.
_close_epoch: CloseEpoch          = CloseEpoch(0, CloseCause.ROUTINE, "", 0.0)
_epoch_lock                       = threading.Lock()
_open_hold_until: float           = 0.0      # time.monotonic(); open_shutter rechaza antes de este instante
# Época más alta que una escritura exitosa de las cuatro líneas cerradas ya cubrió (se lee antes de escribir:
# una escritura confirma sólo los pedidos anteriores a ella).
_last_written_epoch: int          = 0
# Rutinas que corren (la grilla): con alguna, "Cerrar todos" retiene las aperturas. Provisorio de la fase 3:
# en la fase 4 lo sabe el coordinador de la parada.
_routines_running: set[str]       = set()


# ── Parada de emergencia del proceso (R4-17 fase 4, DEC-047; ronda2_architecture.md §4.1.2-§4.1.6) ──────────
ESTOP_INTERLOCK = "E-STOP"
ESTOP_LOCK_TIMEOUT_S = 0.25        # provisorio: lo fija BANCO-68 (2 × la retención máxima medida, piso 0.25 s)
ESTOP_RETRY_INTERVAL_S = 0.25
LOW_POWER_SETTLE_S = 0.10          # [INV-R4] 3: el filtro en baja potencia ≥ 100 ms antes de abrir (BANCO-65 A)


class CloseResult(NamedTuple):
    """Lo que selló el hilo cerrador después de intentar cerrar los cuatro."""
    epoch: int                       # la época que cubre (leída antes de escribir)
    estop_generation: Optional[int]  # la generación de la parada vigente, o None
    ok: bool
    t_written_mono: Optional[float]
    t_written_wall: Optional[float]
    error: Optional[str]
    lock_wait_s: float
    attempts: int


class EStopState(NamedTuple):
    active: bool
    generation: int
    source: str
    t_trigger_wall: Optional[float]
    t_trigger_mono: Optional[float]
    last_result: Optional[CloseResult]
    confirmed: bool                  # un CloseResult ok del cerrador para esta generación
    low_power_confirmed: bool        # el filtro confirmó baja potencia después del cierre
    lock_busy: bool                  # el cerrador no consigue la placa ("cortá con la llave del láser")


# El cerrador: un hilo por proceso. El pedido es "una escritura exitosa de las cuatro cerradas con época ≥ el
# objetivo"; los pedidos que llegan mientras trabaja se juntan. _closer_cv es una hoja.
_closer_cv = threading.Condition(threading.Lock())
_closer_target_epoch: int = 0
_closer_done_epoch: int = 0
_closer_busy_reported: int = -1          # objetivo para el que ya se avisó "placa tomada" (una vez por episodio)
_last_close_result: Optional[CloseResult] = None
_estop_low_power_ok: bool = False
_close_listeners: list[Callable[[CloseResult], None]] = []
# Compuerta de baja potencia: hora monotónica del último up_flipper que la placa confirmó (None: sin confirmar)
_low_power_confirmed_at: Optional[float] = None


def _bump_close_epoch(cause: CloseCause, detail: str = "") -> int:
    global _close_epoch
    with _epoch_lock:
        _close_epoch = CloseEpoch(_close_epoch.epoch + 1, CloseCause(cause), str(detail), time.monotonic())
        return _close_epoch.epoch


def get_close_epoch() -> CloseEpoch:
    """La época de cierre vigente (sin candado)."""
    return _close_epoch


def _set_open_hold(hold_s: float) -> None:
    """Retiene las aperturas `hold_s` segundos. Una retención vigente NO se extiende: los 3 s cuentan desde el
    primer cierre (respuesta 2 del investigador, 2026-10-02)."""
    global _open_hold_until
    if hold_s is None or hold_s <= 0:
        return
    with _epoch_lock:
        now = time.monotonic()
        if _open_hold_until > now:
            return
        _open_hold_until = now + float(hold_s)


def get_open_hold_remaining_s() -> float:
    """Segundos que faltan para que se vuelvan a aceptar aperturas (0 sin retención)."""
    return max(0.0, _open_hold_until - time.monotonic())


def is_close_confirmed(epoch: int) -> bool:
    """True si una escritura exitosa de las cuatro líneas cerradas cubrió el pedido de cierre `epoch`."""
    return _last_written_epoch >= int(epoch)


def set_routine_running(name: str, running: bool) -> None:
    """Una rutina (la grilla) avisa que empieza o que terminó."""
    with _epoch_lock:
        (_routines_running.add if running else _routines_running.discard)(str(name))


def any_routine_running() -> bool:
    return bool(_routines_running)


def request_close_all(cause: CloseCause, detail: str = "", hold_s: float = 0.0) -> int:
    """Pide el cierre de los cuatro: época + 1, la retención si `hold_s > 0`, y el cierre. Devuelve la época del
    pedido; `is_close_confirmed(época)` dice si la placa lo confirmó. En la fase 3 el cierre es sincrónico (el
    hilo cerrador sin bloqueo es de la fase 4)."""
    epoch = _bump_close_epoch(cause, detail)
    _set_open_hold(hold_s)
    _close_all_locked_write()
    return epoch


def operator_close_all(detail: str = "Cerrar todos") -> int:
    """"Cerrar todos" del operador: con una rutina corriendo retiene las aperturas `OPERATOR_HOLD_S`; sin rutina,
    sólo cierra (`ronda2_architecture.md` §4.1.3)."""
    hold = OPERATOR_HOLD_S if any_routine_running() else 0.0
    return request_close_all(CloseCause.OPERATOR, detail, hold_s=hold)


def request_emergency_stop(source: str) -> int:
    """La parada, en el hilo que la pide, sin candado de hardware, sin print y en < 1 ms. En este orden: el `Event`
    (es el interlock funcional: desde acá toda apertura y todo movimiento se rechazan), la época, y despertar al
    cerrador. Idempotente: con la parada activa no cambia nada y devuelve la generación vigente."""
    global _closer_target_epoch
    gen, new = estop_state.trip(source)
    if new:
        epoch = _bump_close_epoch(CloseCause.ESTOP, f"parada: {source}")
        with _closer_cv:
            _closer_target_epoch = max(_closer_target_epoch, epoch)
            _closer_cv.notify_all()
    return gen


def is_emergency_stopped() -> bool:
    return estop_state.is_active()


def _estop_confirmed(gen: int) -> bool:
    r = _last_close_result
    return bool(r is not None and r.ok and r.estop_generation == gen)


def get_emergency_state() -> EStopState:
    snap = estop_state.snapshot()
    r = _last_close_result
    for_this = r is not None and r.estop_generation == snap.generation
    return EStopState(snap.active, snap.generation, snap.source, snap.t_trigger_wall, snap.t_trigger_mono,
                      r if for_this else None, _estop_confirmed(snap.generation),
                      bool(for_this and _estop_low_power_ok),
                      bool(for_this and not r.ok and r.error == _BOARD_BUSY))


def clear_emergency_stop(generation: int) -> tuple[bool, str]:
    """Levanta la parada (Rearmar). Exige la generación vigente y un cierre del cerrador confirmado para ella, y que
    no quede ningún obturador abierto ni sin confirmar. Toma la placa con plazo: nunca bloquea al que rearma."""
    snap = estop_state.snapshot()
    if not snap.active:
        return False, "no hay una parada activa"
    if int(generation) != snap.generation:
        return False, "la generación cambió (hubo otra parada)"
    if not _estop_confirmed(snap.generation):
        return False, "el cierre de la parada no está confirmado"
    if not _nidaq_lock.acquire(timeout=ESTOP_LOCK_TIMEOUT_S):
        return False, "placa tomada por otro hilo"
    try:
        if _unconfirmed_shutters or any(sig == SHUTTER_POLARITY[n] for n, sig in zip(SHUTTERS, _shutter_signal)):
            return False, "hay obturadores abiertos o sin confirmar"
        if not estop_state.clear(generation):
            return False, "la generación cambió (hubo otra parada)"
        _shutter_interlocks.pop(ESTOP_INTERLOCK, None)
    finally:
        _nidaq_lock.release()
    return True, ""


def register_close_listener(fn: Callable[[CloseResult], None]) -> None:
    """`fn(CloseResult)` se llama desde el hilo cerrador, FUERA del candado de la placa."""
    if fn not in _close_listeners:
        _close_listeners.append(fn)


def unregister_close_listener(fn: Callable[[CloseResult], None]) -> None:
    if fn in _close_listeners:
        _close_listeners.remove(fn)


_BOARD_BUSY = "placa tomada por otro hilo"


def _publish_close_result(result: CloseResult) -> None:
    global _last_close_result
    _last_close_result = result
    for fn in list(_close_listeners):
        try:
            fn(result)
        except Exception as e:
            try: print(f"[NI-DAQ] Oyente del cierre falló: {e}")
            except Exception: pass


def _closer_has_work() -> bool:
    return _closer_target_epoch > _closer_done_epoch


def _closer_attempt() -> None:
    """Un intento del cerrador: toma la placa con plazo, cierra los cuatro (y pone el interlock "E-STOP", que es
    cosmético: la autoridad es el Event), suelta, sella el resultado y avisa fuera del candado. Nunca escribe sin
    candado. Con la parada y el cierre confirmados, sube el filtro a baja potencia."""
    global _closer_done_epoch, _closer_busy_reported, _estop_low_power_ok
    target = _closer_target_epoch
    snap = estop_state.snapshot()
    gen = snap.generation if snap.active else None
    t_req = time.monotonic()
    if not _nidaq_lock.acquire(timeout=ESTOP_LOCK_TIMEOUT_S):
        if _closer_busy_reported != target:
            _closer_busy_reported = target
            _publish_close_result(CloseResult(target, gen, False, None, None, _BOARD_BUSY,
                                              time.monotonic() - t_req, 0))
        return
    try:
        wait = time.monotonic() - t_req
        if snap.active:
            _shutter_interlocks[ESTOP_INTERLOCK] = f"parada de emergencia ({snap.source}, generación {snap.generation})"
        epoch_before = _close_epoch.epoch
        ok, notes, err, attempts, msgs = _close_all_under_lock()
    finally:
        _nidaq_lock.release()
    for m in msgs:
        try: print(m)
        except Exception: pass
    _dispatch_shutter_notes(notes)
    now_m, now_w = time.monotonic(), time.time()
    if ok:
        _closer_done_epoch = max(_closer_done_epoch, epoch_before)
    _publish_close_result(CloseResult(epoch_before, gen, ok, now_m if ok else None, now_w if ok else None,
                                      None if ok else err, wait, attempts))
    if ok and snap.active:
        # [INV-R4] 3: después del cierre confirmado, el filtro a baja potencia. Una falla se informa, no cambia el
        # resultado de la parada; la reanudación vuelve a intentarlo (la compuerta de baja potencia).
        _estop_low_power_ok = bool(up_flipper(lock_timeout_s=ESTOP_LOCK_TIMEOUT_S))


def _closer_loop() -> None:
    while True:
        try:
            with _closer_cv:
                while not _closer_has_work():
                    _closer_cv.wait(timeout=1.0)
            _closer_attempt()
            if _closer_has_work():
                time.sleep(ESTOP_RETRY_INTERVAL_S)       # la placa tomada o una escritura fallida: se reintenta
        except Exception as e:                            # el cerrador no termina nunca
            try: print(f"[NI-DAQ] Error en el cerrador: {e}")
            except Exception: pass
            time.sleep(ESTOP_RETRY_INTERVAL_S)


def low_power_settle_remaining_s(min_settle_s: float = LOW_POWER_SETTLE_S) -> Optional[float]:
    """None si no hay baja potencia confirmada (hay que pulsar up_flipper); si no, lo que falta para el piso de
    `min_settle_s` desde la confirmación (0 si ya pasó)."""
    t = _low_power_confirmed_at
    if t is None:
        return None
    return max(0.0, float(min_settle_s) - (time.monotonic() - t))


def operator_close_shutter(name: str, detail: str = "") -> bool:
    """El operador cierra un obturador desde su botón: cuenta como un corte suyo, igual que "Cerrar todos" (el
    nodo en exposición queda interrumpido y, con una rutina corriendo, se retienen las aperturas)."""
    _bump_close_epoch(CloseCause.OPERATOR, detail or f"botón {name}")
    if any_routine_running():
        _set_open_hold(OPERATOR_HOLD_S)
    return close_shutter(name)


def set_default_shutter_timeout(timeout_s: float | None) -> None:
    """Establece la política global de auto-cierre. Toda llamada posterior a open_shutter()/
    heartbeat_shutter() sin timeout_s explícito usará este valor. None o <= 0 activa el Modo
    Alineación continua (sin límite) de inmediato, incluso si un shutter ya está abierto."""
    global _default_timeout_s, _watchdog_deadline
    with _watchdog_lock:
        if timeout_s is None or timeout_s <= 0:
            _default_timeout_s = None
            _watchdog_deadline = None
        else:
            _default_timeout_s = float(timeout_s)


def get_default_shutter_timeout() -> float | None:
    """Devuelve la política global de auto-cierre actual (None = sin límite)."""
    with _watchdog_lock:
        return _default_timeout_s


def _watchdog_loop():
    global _watchdog_deadline
    while _watchdog_active:
        time.sleep(0.1)
        now = time.time()
        with _watchdog_lock:
            dl = _watchdog_deadline
            rd = _retry_due
        if dl is not None and now > dl:
            with _watchdog_lock:
                _watchdog_deadline = None
            try:
                # Si no confirma, close_all_shutters() deja _retry_due armado: el reintento
                # sigue en este mismo hilo aunque el plazo ya se haya consumido.
                close_all_shutters(CloseCause.WATCHDOG, "heartbeat expirado")
            except Exception as err:
                try: print(f"[WATCHDOG Error] Error en cierre forzado: {err}")
                except Exception: pass
            try:
                print("[WATCHDOG WARNING] Heartbeat expirado: forzando CIERRE INMEDIATO de obturadores por seguridad!")
            except Exception:
                pass
            for cb in list(_watchdog_callbacks):
                try:
                    cb()
                except Exception as cb_err:
                    try: print(f"[WATCHDOG Callback Error] {cb_err}")
                    except Exception: pass
        elif rd is not None and now > rd:
            try:
                _reconfirm_unconfirmed_shutters()
            except Exception as err:
                try: print(f"[WATCHDOG Error] Reintento de cierre: {err}")
                except Exception: pass

_watchdog_thread = threading.Thread(target=_watchdog_loop, daemon=True, name="ShutterWatchdog")
_watchdog_thread.start()


def _start_closer_thread() -> None:
    t = threading.Thread(target=lambda: _closer_loop(), daemon=True, name="ShutterCloser")
    t.start()


def heartbeat_shutter(timeout_s: float | None = _SENTINEL) -> None:
    """Renueva el temporizador de vida del obturador para proteger la muestra.
    Si no se pasa timeout_s explícitamente, usa la política global vigente
    (get_default_shutter_timeout(), fijada por el usuario en el dock de Shutters). Un
    timeout_s explícito (numérico o None) siempre tiene prioridad sobre la política global.
    None o <= 0 desactiva la fecha límite (Modo Alineación continua)."""
    global _watchdog_deadline
    if estop_state.is_active():
        # Durante la parada el latido no arma el plazo (R4-17 fase 4): después del cierre confirmado el watchdog
        # queda desarmado, y un vencimiento posterior avisaría de un corte que ya ocurrió. El reintento de un
        # cierre sin confirmar va por _retry_due y no depende de esto.
        return
    with _watchdog_lock:
        effective = _default_timeout_s if timeout_s is _SENTINEL else timeout_s
        if effective is None or effective <= 0:
            _watchdog_deadline = None
        else:
            _watchdog_deadline = time.time() + max(0.1, float(effective))


def get_watchdog_remaining_time() -> float | None:
    """Retorna los segundos restantes antes del auto-cierre, o None si no está armado."""
    with _watchdog_lock:
        if _watchdog_deadline is None:
            return None
        rem = _watchdog_deadline - time.time()
        return max(0.0, rem)


def is_watchdog_armed() -> bool:
    """Indica si el temporizador de auto-cierre tiene una fecha límite activa."""
    with _watchdog_lock:
        return _watchdog_deadline is not None


def register_watchdog_callback(fn: Callable[[], None]) -> None:
    """Registra una función a invocar cuando el watchdog fuerce el cierre de obturadores."""
    if fn not in _watchdog_callbacks:
        _watchdog_callbacks.append(fn)


def unregister_watchdog_callback(fn: Callable[[], None]) -> None:
    """Desregistra una función del watchdog."""
    if fn in _watchdog_callbacks:
        _watchdog_callbacks.remove(fn)


def register_shutter_fault_callback(fn: Callable[[str, str, bool], None]) -> None:
    """Registra fn(nombre, detalle, confirmado). Se invoca con confirmado=False la primera vez
    que una operación sobre ese obturador no se puede confirmar (o se bloquea por interlock),
    y con confirmado=True cuando un cierre pendiente finalmente se confirma."""
    if fn not in _shutter_fault_callbacks:
        _shutter_fault_callbacks.append(fn)


def unregister_shutter_fault_callback(fn: Callable[[str, str, bool], None]) -> None:
    if fn in _shutter_fault_callbacks:
        _shutter_fault_callbacks.remove(fn)


def _dispatch_shutter_notes(notes: list[tuple[str, str, bool]]) -> None:
    """Se llama FUERA de _nidaq_lock: un callback de UI no debe poder bloquear el hardware."""
    for name, detail, confirmed in notes:
        for cb in list(_shutter_fault_callbacks):
            try:
                cb(name, detail, confirmed)
            except Exception as cb_err:
                try: print(f"[NI-DAQ Fault Callback Error] {cb_err}")
                except Exception: pass


def get_unconfirmed_shutters() -> list[str]:
    """Obturadores cuyo cierre no se pudo confirmar (se tratan como abiertos)."""
    with _nidaq_lock:
        return [name for name in SHUTTERS if name in _unconfirmed_shutters]


def set_shutter_interlock(source: str, reason: str) -> None:
    """Bloquea toda apertura de obturadores mientras `source` no se libere."""
    with _nidaq_lock:
        _shutter_interlocks[source] = reason
    try: print(f"[NI-DAQ INTERLOCK] Activado por {source}: {reason}")
    except Exception: pass


def clear_shutter_interlock(source: str) -> None:
    with _nidaq_lock:
        removed = _shutter_interlocks.pop(source, None)
    if removed is not None:
        try: print(f"[NI-DAQ INTERLOCK] Liberado: {source}")
        except Exception: pass


def get_shutter_interlocks() -> dict[str, str]:
    with _nidaq_lock:
        return dict(_shutter_interlocks)


def trip_shutter_interlock(source: str, reason: str) -> bool:
    """Activa el interlock y cierra todos los obturadores. Devuelve si el cierre se confirmó."""
    set_shutter_interlock(source, reason)
    return close_all_shutters(CloseCause.INTERLOCK, f"{source}: {reason}")


def register_flipper_callback(fn: Callable[[bool], None]) -> None:
    """Registra una función a invocar cuando cambie el estado del flipper de potencia (True=High, False=Low)."""
    if fn not in _flipper_callbacks:
        _flipper_callbacks.append(fn)


def unregister_flipper_callback(fn: Callable[[bool], None]) -> None:
    """Desregistra una función de cambio de estado del flipper."""
    if fn in _flipper_callbacks:
        _flipper_callbacks.remove(fn)


def is_flipper_high_power() -> bool:
    """Retorna True si el flipper está en alta potencia (down), False si está en baja (up)."""
    return _flipper_high_power


def _emergency_shutdown():
    try:
        close_all_shutters(CloseCause.EXIT, "fin del proceso")
        up_flipper()
    except Exception:
        pass

atexit.register(_emergency_shutdown)


def _is_daq_isolated() -> bool:
    try:
        from core.hardware_manager import hardware_manager
        return bool(hardware_manager.is_isolated("NI-DAQmx (Dev1)"))
    except Exception:
        return False


def _daq_fault(component: str, err: Exception) -> None:
    """Una tarea DAQmx no se pudo crear fuera de SAFE_MODE. No hay simulador de respaldo en
    producción (DEC-036): la placa se declara no disponible y se bloquea toda apertura."""
    set_shutter_interlock(_DAQ_INTERLOCK, f"no se pudo crear la tarea de {component} ({err}); reiniciar el programa")


def _get_shutter_task():
    """Tarea real de obturadores, un _MockNITask en SAFE_MODE o aislado, o None si la placa no
    está disponible en producción."""
    global _shutter_task
    if SAFE_MODE or _is_daq_isolated():
        return _MockNITask(len(SHUTTERS), 1)
    if _shutter_task is None:
        try:
            _shutter_task = nidaqmx.Task()
            for ch in SHUTTER_CHANNELS:
                _shutter_task.do_channels.add_do_chan(
                    lines=f"{NIDAQ_DEVICE}/port0/line{ch}",
                    line_grouping=LineGrouping.CHAN_PER_LINE)
        except Exception as e:
            print(f"[NI-DAQ Error] No se pudo inicializar la tarea de obturadores: {e}. "
                  f"Placa NO disponible: las aperturas quedan bloqueadas.")
            try:
                if _shutter_task is not None:
                    _shutter_task.close()
            except Exception:
                pass
            _shutter_task = None
            _daq_fault("obturadores", e)
            return None
    return _shutter_task


def _write_shutter_lines(desired: list[bool]) -> tuple[Optional[str], bool]:
    """Escribe las cuatro líneas. Devuelve (error, simulado): error es None si la escritura
    tuvo éxito; simulado indica SAFE_MODE o placa aislada."""
    t = _get_shutter_task()
    if t is None:
        return "tarea DAQmx de obturadores no disponible", False
    if isinstance(t, _MockNITask):
        return None, True
    try:
        t.write(list(desired), auto_start=True)
        return None, False
    except Exception as e:
        return str(e), False


def _apply_shutter_lines(desired: list[bool]) -> tuple[Optional[str], bool, list[str], list[str]]:
    """Escribe `desired` y, sólo si tuvo éxito, lo adopta como valor comandado. Toda escritura
    exitosa aplica el arreglo completo, así que confirma las cuatro líneas: un cierre pendiente de
    una línea comandada "cerrar", y el estado de una comandada "abrir" que quedó sin confirmar por una
    escritura fallida (R4-17 fase 1). Devuelve (error, simulado, cierres recién confirmados,
    aperturas recién confirmadas)."""
    global _last_written_epoch
    epoch_before = _close_epoch.epoch          # se lee antes: la escritura cubre sólo los pedidos anteriores
    err, simulated = _write_shutter_lines(desired)
    recovered: list[str] = []
    recovered_open: list[str] = []
    if err is None:
        _shutter_signal[:] = list(desired)
        if all(sig == (not SHUTTER_POLARITY[n]) for n, sig in zip(SHUTTERS, desired)):
            _last_written_epoch = max(_last_written_epoch, epoch_before)
        for name, sig in zip(SHUTTERS, desired):
            if name in _unconfirmed_shutters:
                _unconfirmed_shutters.discard(name)
                (recovered if sig == (not SHUTTER_POLARITY[name]) else recovered_open).append(name)
    return err, simulated, recovered, recovered_open


def _confirmed_notes(recovered: list[str], recovered_open: list[str], how: str = "cierre confirmado"):
    return ([(n, how, True) for n in recovered]
            + [(n, "estado confirmado (abierto)", True) for n in recovered_open])


def _mark_all_unconfirmed(err: str, why: str) -> list[tuple[str, str, bool]]:
    """Después de una escritura fallida no se sabe el estado real de la placa: las cuatro líneas quedan sin
    confirmar y se tratan como abiertas (respuesta 3 (b) del investigador, 2026-10-02; R4-17 fase 1). Antes,
    sólo las que el software creía abiertas, así que un cierre fallido con nada creído abierto no marcaba
    nada y `_all_closed_confirmed()` daba verdadero. Devuelve un aviso por cada línea recién marcada."""
    notes: list[tuple[str, str, bool]] = []
    for name, sig in zip(SHUTTERS, _shutter_signal):
        if name in _unconfirmed_shutters:
            continue
        _unconfirmed_shutters.add(name)
        if sig == (not SHUTTER_POLARITY[name]):
            notes.append((name, f"cierre NO confirmado ({why}): {err}", False))
        else:
            notes.append((name, f"estado sin confirmar ({why}): {err}", False))
    _arm_retry()
    return notes


def _all_closed_confirmed() -> bool:
    return (not _unconfirmed_shutters
            and all(s == (not SHUTTER_POLARITY[sh]) for s, sh in zip(_shutter_signal, SHUTTERS)))


def _arm_retry() -> None:
    global _retry_due
    with _watchdog_lock:
        _retry_due = time.time() + WATCHDOG_RETRY_INTERVAL_S


def _settle_after_success() -> None:
    """Tras una escritura exitosa: si ya no queda nada abierto ni pendiente, desarmar todo."""
    global _watchdog_deadline, _retry_due
    if _all_closed_confirmed():
        with _watchdog_lock:
            _watchdog_deadline = None
            _retry_due = None
    elif not _unconfirmed_shutters:
        with _watchdog_lock:
            _retry_due = None


def _reconfirm_unconfirmed_shutters() -> None:
    """Reintento del watchdog: reescribe el arreglo comandado (que lleva "cerrar" en toda línea
    pendiente) hasta que se confirme."""
    global _retry_due
    notes: list[tuple[str, str, bool]] = []
    with _nidaq_lock:
        if not _unconfirmed_shutters:
            with _watchdog_lock:
                _retry_due = None
            return
        err, _sim, recovered, recovered_open = _apply_shutter_lines(list(_shutter_signal))
        if err is None:
            notes += _confirmed_notes(recovered, recovered_open, "cierre confirmado en un reintento")
            _settle_after_success()
        else:
            _arm_retry()
    _dispatch_shutter_notes(notes)


# ══════════════════════════════════════════════════════════════════════════════
#  API PÚBLICA  — misma en ambos modos
# ══════════════════════════════════════════════════════════════════════════════

def open_shutter(name: str, timeout_s: float | None = _SENTINEL) -> bool:
    """Abre un shutter y arma/renueva el watchdog. Devuelve True sólo si la placa confirmó la
    escritura (o en SAFE_MODE / aislado). Si no se pasa timeout_s explícitamente, usa la
    política global vigente (get_default_shutter_timeout()) en vez de un valor hardcodeado,
    para que la elección del usuario en el dock de Shutters ("Auto-cierre" / "Sin límite") se
    respete también cuando una rutina experimental abre el shutter.

    Un interlock activo (placa no disponible, falla de la platina) bloquea la apertura, y también la retención de
    "Cerrar todos" (`get_open_hold_remaining_s()`, R4-17 fase 3): se revisa antes de pedir el candado y otra vez
    adentro. Una apertura retenida no escribe ni arma el watchdog."""
    if name not in SHUTTERS:
        raise ValueError(f"Shutter desconocido: {name}")
    if estop_state.is_active():
        _print_estop_rejection(name)                     # sin pedir el candado: la rutina no espera la placa
        return False
    if get_open_hold_remaining_s() > 0:
        _print_hold_rejection(name)
        return False
    notes: list[tuple[str, str, bool]] = []
    held = False
    stopped = False
    with _nidaq_lock:
        if estop_state.is_active():                      # una parada que llegó mientras esperaba el candado
            stopped, ok = True, False
        elif get_open_hold_remaining_s() > 0:
            held, ok = True, False
        elif _shutter_interlocks:
            reason = "; ".join(f"{k}: {v}" for k, v in _shutter_interlocks.items())
            print(f"[NI-DAQ] open_shutter({name}) BLOQUEADO por interlock — {reason}")
            notes.append((name, f"apertura bloqueada por interlock ({reason})", False))
            ok = False
        else:
            idx = SHUTTERS.index(name)
            desired = list(_shutter_signal)
            desired[idx] = SHUTTER_POLARITY[name]
            err, simulated, recovered, recovered_open = _apply_shutter_lines(desired)
            # El watchdog se arma aunque la escritura falle: si el obturador llegó a abrirse,
            # el plazo lo cierra igual.
            heartbeat_shutter(timeout_s)
            notes += _confirmed_notes(recovered, recovered_open)
            if err is None:
                if simulated:
                    print(f"[NI MOCK] open_shutter({name})")
                ok = True
            else:
                print(f"[NI-DAQ Error] open_shutter({name}) NO confirmado: {err}")
                notes.append((name, f"apertura no confirmada: {err}", False))
                notes += _mark_all_unconfirmed(err, f"falló la apertura de {name}")
                ok = False
    if stopped:
        _print_estop_rejection(name)
    if held:
        _print_hold_rejection(name)
    _dispatch_shutter_notes(notes)
    return ok


def _print_estop_rejection(name: str) -> None:
    try:
        print(f"[NI-DAQ] open_shutter({name}) RECHAZADO: parada de emergencia activa (Rearmar para volver a abrir).")
    except Exception:
        pass


def _print_hold_rejection(name: str) -> None:
    try:
        print(f"[NI-DAQ] open_shutter({name}) RETENIDO: \"Cerrar todos\" retiene las aperturas "
              f"{get_open_hold_remaining_s():.1f} s más.")
    except Exception:
        pass


def close_shutter(name: str) -> bool:
    """Cierra un shutter. Devuelve True sólo si la placa confirmó la escritura. Si tras
    SHUTTER_CLOSE_RETRIES intentos no se confirma, el obturador se trata como abierto: queda
    en get_unconfirmed_shutters(), el watchdog sigue armado y reintenta cada
    WATCHDOG_RETRY_INTERVAL_S, y se avisa una vez por register_shutter_fault_callback()."""
    if name not in SHUTTERS:
        raise ValueError(f"Shutter desconocido: {name}")
    notes: list[tuple[str, str, bool]] = []
    with _nidaq_lock:
        idx = SHUTTERS.index(name)
        desired = list(_shutter_signal)
        desired[idx] = not SHUTTER_POLARITY[name]
        err = None
        for attempt in range(SHUTTER_CLOSE_RETRIES):
            err, simulated, recovered, recovered_open = _apply_shutter_lines(desired)
            if err is None:
                break
            if attempt < SHUTTER_CLOSE_RETRIES - 1:
                time.sleep(SHUTTER_RETRY_DELAY_S)
        if err is None:
            if simulated:
                print(f"[NI MOCK] close_shutter({name})")
            notes += _confirmed_notes(recovered, recovered_open)
            _settle_after_success()
            ok = True
        else:
            # El valor comandado sigue siendo "cerrar": toda escritura posterior lo reintenta.
            _shutter_signal[idx] = not SHUTTER_POLARITY[name]
            print(f"[NI-DAQ Error] close_shutter({name}) NO confirmado tras "
                  f"{SHUTTER_CLOSE_RETRIES} intentos: {err}. Las cuatro líneas se tratan como ABIERTAS.")
            notes += _mark_all_unconfirmed(err, f"tras {SHUTTER_CLOSE_RETRIES} intentos de cerrar {name}")
            ok = False
    _dispatch_shutter_notes(notes)
    return ok


def close_all_shutters(cause: CloseCause = CloseCause.ROUTINE, detail: str = "") -> bool:
    """Cierra los cuatro obturadores con una sola escritura. Devuelve True sólo si se confirmó. Todo cierre de los
    cuatro es un corte: incrementa la época antes de tomar la placa (R4-17 fase 3)."""
    _bump_close_epoch(cause, detail)
    return _close_all_locked_write()


def _close_all_under_lock():
    """El cierre de los cuatro con `_nidaq_lock` YA tomado por el llamador. No imprime (H9): devuelve
    (ok, avisos, error, intentos, mensajes) para que el llamador imprima y despache fuera del candado."""
    global _watchdog_deadline, _retry_due
    notes: list[tuple[str, str, bool]] = []
    msgs: list[str] = []
    desired = [not SHUTTER_POLARITY[s] for s in SHUTTERS]
    err = None
    attempts = 0
    for attempt in range(SHUTTER_CLOSE_RETRIES):
        attempts += 1
        err, _simulated, recovered, recovered_open = _apply_shutter_lines(desired)
        if err is None:
            break
        if attempt < SHUTTER_CLOSE_RETRIES - 1:
            time.sleep(SHUTTER_RETRY_DELAY_S)
    if err is None:
        notes += _confirmed_notes(recovered, recovered_open)
        with _watchdog_lock:
            _watchdog_deadline = None
            _retry_due = None
        ok = True
    else:
        _shutter_signal[:] = desired
        # Las cuatro, no sólo las que se creían abiertas (R4-17 fase 1, respuesta 3 (b)): con nada creído
        # abierto, antes no se marcaba nada y el cierre fallido pasaba por confirmado.
        notes += _mark_all_unconfirmed(err, f"tras {SHUTTER_CLOSE_RETRIES} intentos de cerrar todos")
        msgs.append(f"[NI-DAQ Error] close_all_shutters() NO confirmado: {err}. Las cuatro líneas se tratan "
                    f"como ABIERTAS.")
        ok = False
    return ok, notes, err, attempts, msgs


def _close_all_locked_write() -> bool:
    with _nidaq_lock:
        ok, notes, _err, _attempts, msgs = _close_all_under_lock()
    for m in msgs:
        try: print(m)
        except Exception: pass
    _dispatch_shutter_notes(notes)
    return ok


def get_open_shutter_names() -> list[str]:
    """Devuelve los nombres de los shutters abiertos o que no se pudieron confirmar cerrados
    (se tratan como abiertos, DEC-036). No usar is_watchdog_armed() como proxy: en Modo
    Alineación (timeout=None, "Sin límite") un shutter puede estar físicamente abierto con el
    watchdog desarmado a propósito, así que is_watchdog_armed()==False no implica que no haya
    láser abierto."""
    with _nidaq_lock:
        return [name for name, sig in zip(SHUTTERS, _shutter_signal)
                if sig == SHUTTER_POLARITY[name] or name in _unconfirmed_shutters]


def _get_flipper_tasks():
    """Tareas reales de los flippers de potencia, _MockNITask en SAFE_MODE o aislado, o
    (None, None) si la placa no está disponible en producción (DEC-036)."""
    global _flipper_task0, _flipper_task1
    if SAFE_MODE or _is_daq_isolated():
        return _MockNITask(1, 1), _MockNITask(1, 1)

    # Validar si las tareas existentes siguen abiertas/activas
    if _flipper_task0 is not None:
        try:
            _ = _flipper_task0.is_task_done()
        except Exception:
            try: _flipper_task0.close()
            except Exception: pass
            _flipper_task0 = None

    if _flipper_task1 is not None:
        try:
            _ = _flipper_task1.is_task_done()
        except Exception:
            try: _flipper_task1.close()
            except Exception: pass
            _flipper_task1 = None

    try:
        if _flipper_task0 is None:
            _flipper_task0 = nidaqmx.Task()
            _flipper_task0.ao_channels.add_ao_voltage_chan(FLIPPER_AO_DOWN)
        if _flipper_task1 is None:
            _flipper_task1 = nidaqmx.Task()
            _flipper_task1.ao_channels.add_ao_voltage_chan(FLIPPER_AO_UP)
        return _flipper_task0, _flipper_task1
    except Exception as e:
        print(f"[NI-DAQ Error] No se pudo inicializar la tarea de flippers: {e}. Placa NO disponible.")
        _daq_fault("flippers de potencia", e)
        return None, None


def _get_flipper532_task():
    """Tarea real del flipper notch 532, _MockNITask en SAFE_MODE o aislado, o None si la
    placa no está disponible en producción (DEC-036)."""
    global _flipper532_task
    if SAFE_MODE or _is_daq_isolated():
        return _MockNITask(1, 1)

    if _flipper532_task is not None:
        try:
            _ = _flipper532_task.is_task_done()
        except Exception:
            try: _flipper532_task.close()
            except Exception: pass
            _flipper532_task = None

    try:
        if _flipper532_task is None:
            _flipper532_task = nidaqmx.Task()
            _flipper532_task.do_channels.add_do_chan(
                lines=f"{NIDAQ_DEVICE}/port0/line{FLIPPER_532_CHAN}",
                line_grouping=LineGrouping.CHAN_PER_LINE)
        return _flipper532_task
    except Exception as e:
        print(f"[NI-DAQ Error] No se pudo inicializar la tarea del flipper 532: {e}. Placa NO disponible.")
        _daq_fault("flipper notch 532", e)
        return None


def _set_flipper_state(high_power: bool) -> None:
    global _flipper_high_power
    _flipper_high_power = high_power
    for cb in list(_flipper_callbacks):
        try:
            cb(high_power)
        except Exception:
            pass


def _pulse_flipper(high_power: bool, lock_timeout_s: Optional[float] = None) -> bool:
    """Pulso de 5 ms en la salida analógica del flipper. El estado y los callbacks se
    actualizan DESPUÉS de una escritura exitosa (DEC-014/DEC-036), nunca antes. Con `lock_timeout_s`, no
    espera la placa más que eso (el cerrador de la parada, R4-17 fase 4). Anota la compuerta de baja potencia:
    un up confirmado la abre con su hora; un down, o cualquier falla, la cierra."""
    global _low_power_confirmed_at
    if lock_timeout_s is None:
        _nidaq_lock.acquire()
    elif not _nidaq_lock.acquire(timeout=float(lock_timeout_s)):
        _low_power_confirmed_at = None
        return False
    try:
        ok = _pulse_flipper_locked(high_power)
    finally:
        _nidaq_lock.release()
    _low_power_confirmed_at = time.monotonic() if (ok and not high_power) else None
    return ok


def _pulse_flipper_locked(high_power: bool) -> bool:
    global _flipper_task0, _flipper_task1
    label = "down_flipper" if high_power else "up_flipper"
    t0, t1 = _get_flipper_tasks()
    task = t0 if high_power else t1
    if task is None:
        print(f"[NI-DAQ Error] {label}() rechazado: placa NO disponible.")
        return False
    if isinstance(task, _MockNITask):
        print(f"[NI MOCK] {label}()")
        _set_flipper_state(high_power)
        return True
    try:
        task.write(5.0); time.sleep(0.005); task.write(0.0)
    except Exception as e:
        print(f"[NI-DAQ Warning] Error en {label} ({e}). Reintentando con nueva tarea...")
        try:
            if high_power:
                if _flipper_task0 is not None:
                    try: _flipper_task0.close()
                    except Exception: pass
                _flipper_task0 = None
            else:
                if _flipper_task1 is not None:
                    try: _flipper_task1.close()
                    except Exception: pass
                _flipper_task1 = None
            t0, t1 = _get_flipper_tasks()
            task = t0 if high_power else t1
            if task is None or isinstance(task, _MockNITask):
                print(f"[NI-DAQ Error] {label} falló: placa NO disponible.")
                return False
            task.write(5.0); time.sleep(0.005); task.write(0.0)
        except Exception as e2:
            print(f"[NI-DAQ Error] {label} falló: {e2}")
            return False
    _set_flipper_state(high_power)
    return True


def up_flipper(lock_timeout_s: Optional[float] = None) -> bool:
    """Flipper de potencia arriba (baja potencia). Devuelve True sólo si se confirmó."""
    return _pulse_flipper(False, lock_timeout_s)


def down_flipper(lock_timeout_s: Optional[float] = None) -> bool:
    """Flipper de potencia abajo (alta potencia). Devuelve True sólo si se confirmó."""
    return _pulse_flipper(True, lock_timeout_s)


class MirrorBelief(NamedTuple):
    position: str          # "up" / "down" / "unknown"
    source: str            # "none" / "commanded" / "operator_confirmed"
    since: Optional[float]
    last_known: Optional[str] = None           # el último estado guardado (de esta sesión o de una anterior)
    last_known_since: Optional[float] = None


def _mirror_state_module():
    """`core.detection_mirror_state`; PyPrinting importa este módulo como `nidaq`, con `core/` en el path."""
    try:
        from core import detection_mirror_state as dms
    except ImportError:
        import detection_mirror_state as dms
    return dms


def _remember_mirror_state() -> None:
    """Guarda la creencia actual en disco (R4-N 3). Una falla al escribir no rompe el movimiento."""
    global _mirror_last_known
    dms = _mirror_state_module()
    pos = "up" if _flipper_notch532_up else "down"
    _mirror_last_known = dms.SavedMirrorState(pos, _mirror_belief_source, _mirror_belief_since or time.time())
    dms.save_state(pos, _mirror_belief_source, _mirror_belief_since)


def _note_mirror_commanded() -> None:
    global _mirror_belief_source, _mirror_belief_since
    _mirror_belief_source, _mirror_belief_since = "commanded", time.time()
    _remember_mirror_state()


def load_last_known_mirror_state():
    """Lee el último estado guardado (al importar y en los tests). Sin archivo o dañado: sin información.

    El último conocido guía el próximo pulso (el espejo cambia de lado con cada pulso), pero no reemplaza la
    confirmación del operador: la creencia queda con fuente "none" y posición "unknown"."""
    global _flipper_notch532_up, _mirror_last_known, _mirror_belief_source, _mirror_belief_since
    dms = _mirror_state_module()
    saved = dms.load_state()
    with _nidaq_lock:
        _mirror_last_known = saved
        _mirror_belief_source, _mirror_belief_since = "none", None
        _flipper_notch532_up = True if saved is None else saved.position == "up"
    return saved


def get_detection_mirror_belief() -> MirrorBelief:
    """Qué cree el software sobre el espejo de detección (D-10). Sin información, "unknown"; el último estado
    guardado va aparte, en `last_known`, y no cuenta como confirmación (R4-N 3, D-01)."""
    with _nidaq_lock:
        last = _mirror_last_known
        lk, lk_since = (last.position, last.since) if last is not None else (None, None)
        if _mirror_belief_source == "none":
            return MirrorBelief("unknown", "none", None, lk, lk_since)
        return MirrorBelief("up" if _flipper_notch532_up else "down", _mirror_belief_source, _mirror_belief_since,
                            lk, lk_since)


def confirm_detection_mirror_belief(position: str) -> MirrorBelief:
    """El operador confirma la posición (p. ej. "Ya está abajo: confirmo"). No mueve nada (D-10)."""
    global _flipper_notch532_up, _mirror_belief_source, _mirror_belief_since
    if position not in ("up", "down"):
        raise ValueError(f"Posición desconocida: '{position}'")
    with _nidaq_lock:
        _flipper_notch532_up = position == "up"
        _mirror_belief_source, _mirror_belief_since = "operator_confirmed", time.time()
        _remember_mirror_state()
    return get_detection_mirror_belief()


def flipper_notch532(desired: str) -> bool:
    """Nombre viejo de `set_detection_mirror` (P6): lo sigue usando PyPrinting (`app.py`); se renombra después.
    "Notch" era un error de notación heredado del legado: la línea mueve el espejo de detección."""
    return set_detection_mirror(desired)


def set_detection_mirror(desired: str) -> bool:
    """Mueve el espejo de detección ("up" = confocal / cámara, "down" = espectrómetro). Un pulso lo cambia de
    lado, así que sólo pulsa si la creencia es la otra. Devuelve True sólo si se confirmó (o no hacía falta)."""
    global _flipper_notch532_up
    if desired not in ("up", "down"):
        raise ValueError(f"Estado desconocido: '{desired}'")
    with _nidaq_lock:
        if SAFE_MODE:
            _flipper_notch532_up = (desired == "up")
            _note_mirror_commanded()
            print(f"[NI MOCK] flipper_notch532({desired})"); return True
        try:
            task = _get_flipper532_task()
            if task is None:
                print(f"[NI-DAQ Error] flipper_notch532({desired}) rechazado: placa NO disponible.")
                return False
            if isinstance(task, _MockNITask):
                _flipper_notch532_up = (desired == "up")
                _note_mirror_commanded()
                print(f"[NI MOCK] flipper_notch532({desired})"); return True
            need_up  = desired == "up"
            if need_up and not _flipper_notch532_up:
                task.write(True); time.sleep(0.003); task.write(False)
                _flipper_notch532_up = True
            elif not need_up and _flipper_notch532_up:
                task.write(True); time.sleep(0.003); task.write(False)
                _flipper_notch532_up = False
            _note_mirror_commanded()
            return True
        except Exception as e:
            print(f"[NI-DAQ Error] flipper_notch532: {e}")
            return False


try:
    load_last_known_mirror_state()
except Exception as _e:                    # nunca impide importar el módulo de seguridad
    print(f"[Espejo de detección] No se pudo leer el último estado: {_e}")


def channels_photodiodos(rate: float, samps_per_chan: int, continuous: bool = False):
    """Devuelve una Task real o un _MockNITask según SAFE_MODE o disponibilidad.

    continuous=True configura AcquisitionType.CONTINUOUS con un buffer de hardware más
    grande que samps_per_chan, pensado para que el llamador cree la Task UNA sola vez,
    la inicie con .start() y luego reutilice múltiples .read(samps_per_chan) sobre la
    misma instancia (ANOM-TRACE-01) en vez de crear/destruir una Task nueva en cada tick.

    Los llamadores existentes que necesitan una adquisición de un solo disparo
    sincronizada a un trigger externo (p.ej. la rampa Z de focus.py, disparada por el
    wave-table del piezo) deben seguir usando el default continuous=False (FINITE) —
    cambiar el modo global de esta función rompería esa sincronización.

    Fuera de SAFE_MODE, si la tarea no se puede crear (DEC-036) no hay simulador: se activa el
    interlock, se cierran los obturadores y se devuelve una _UnavailableNITask que lee NaN.
    Sin fotodiodo no hay detección de captura, así que ningún láser debe quedar abierto.
    """
    if SAFE_MODE or _is_daq_isolated():
        return _MockNITask(len(PD_CHANS_LIST) + 1, samps_per_chan)
    task = None
    try:
        task = nidaqmx.Task()
        for ch in PD_CHANS_LIST:
            task.ai_channels.add_ai_voltage_chan(
                physical_channel=f"{NIDAQ_DEVICE}/ai{ch}",
                name_to_assign_to_channel=f"chan_PD{ch}")
        if continuous:
            task.timing.cfg_samp_clk_timing(
                rate=rate,
                sample_mode=AcquisitionType.CONTINUOUS,
                samps_per_chan=max(samps_per_chan * 10, 1000))
        else:
            task.timing.cfg_samp_clk_timing(
                rate=rate,
                sample_mode=AcquisitionType.FINITE,
                samps_per_chan=samps_per_chan)
        return task
    except Exception as e:
        print(f"[NI-DAQ Error] No se pudo crear la tarea de fotodiodos ({e}). Placa NO disponible: "
              f"obturadores cerrados y aperturas bloqueadas.")
        try:
            if task is not None:
                task.close()
        except Exception:
            pass
        _daq_fault("fotodiodos", e)
        close_all_shutters(CloseCause.INTERLOCK, "tarea de fotodiodos no disponible")
        return _UnavailableNITask(len(PD_CHANS_LIST) + 1, samps_per_chan)


def channels_triggers(task, axis: str) -> None:
    """Agrega el canal de trigger. En SAFE_MODE el _MockNITask ya lo incluye (y marca la tarea como rampa)."""
    if isinstance(task, _MockNITask):
        task._ramp_axis = axis
        return
    if SAFE_MODE:
        return
    try:
        ch = TRIGGER_CHANNELS[axis]
        task.ai_channels.add_ai_voltage_chan(
            physical_channel=f"{NIDAQ_DEVICE}/ai{ch}",
            name_to_assign_to_channel=f"trigger_pi_{ch}")
    except Exception as e:
        print(f"[NI-DAQ Warning] Error al agregar trigger {axis}: {e}")


def set_laser532_voltage(v: float) -> None:
    global _laser532_task
    v = max(LASER_532_V_MIN, min(LASER_532_V_MAX, v))
    if SAFE_MODE:
        print(f"[NI MOCK] láser 532 -> {v:.3f} V"); return
    try:
        from core.hardware_manager import hardware_manager
        if hardware_manager.is_isolated("NI-DAQmx (Dev1)"):
            print(f"[NI MOCK (Aislado)] láser 532 -> {v:.3f} V"); return
    except Exception:
        pass
    try:
        if _laser532_task is None:
            _laser532_task = nidaqmx.Task("laser532")
            _laser532_task.ao_channels.add_ao_voltage_chan(
                "Dev1/ao2", min_val=0.0, max_val=5.0)
            _laser532_task.start()
        _laser532_task.write(v)
    except Exception as e:
        print(f"[NI-DAQ Error] set_laser532_voltage({v}): {e}")


def close_all_tasks() -> None:
    global _shutter_task, _flipper_task0, _flipper_task1, _flipper532_task, _laser532_task
    if SAFE_MODE:
        return
    for var in ("_shutter_task", "_flipper_task0", "_flipper_task1",
                "_flipper532_task", "_laser532_task"):
        task = globals().get(var)
        if task is not None:
            try:
                task.stop()
                task.close()
            except Exception:
                pass
            globals()[var] = None


# El cerrador de la parada (R4-17 fase 4): un hilo por proceso, de larga vida, como el watchdog
_start_closer_thread()
