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
from typing import Callable, Optional
import numpy as np

# Unificar 'nidaq' y 'core.nidaq' en sys.modules para evitar instancias duplicadas
if __name__ == "core.nidaq":
    sys.modules["nidaq"] = sys.modules[__name__]
elif __name__ == "nidaq":
    sys.modules["core.nidaq"] = sys.modules[__name__]

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
        channels = [list(0.5 + 0.02 * np.random.randn(n))
                    for _ in range(self._n_ch - 1)]
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
                close_all_shutters()
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


def heartbeat_shutter(timeout_s: float | None = _SENTINEL) -> None:
    """Renueva el temporizador de vida del obturador para proteger la muestra.
    Si no se pasa timeout_s explícitamente, usa la política global vigente
    (get_default_shutter_timeout(), fijada por el usuario en el dock de Shutters). Un
    timeout_s explícito (numérico o None) siempre tiene prioridad sobre la política global.
    None o <= 0 desactiva la fecha límite (Modo Alineación continua)."""
    global _watchdog_deadline
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
    return close_all_shutters()


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
        close_all_shutters()
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


def _apply_shutter_lines(desired: list[bool]) -> tuple[Optional[str], bool, list[str]]:
    """Escribe `desired` y, sólo si tuvo éxito, lo adopta como valor comandado. Toda escritura
    exitosa aplica el arreglo completo, así que confirma cualquier cierre pendiente de una línea
    comandada "cerrar". Devuelve (error, simulado, obturadores recién confirmados)."""
    err, simulated = _write_shutter_lines(desired)
    recovered: list[str] = []
    if err is None:
        _shutter_signal[:] = list(desired)
        for name, sig in zip(SHUTTERS, desired):
            if sig == (not SHUTTER_POLARITY[name]) and name in _unconfirmed_shutters:
                _unconfirmed_shutters.discard(name)
                recovered.append(name)
    return err, simulated, recovered


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
        err, _sim, recovered = _apply_shutter_lines(list(_shutter_signal))
        if err is None:
            notes += [(n, "cierre confirmado en un reintento", True) for n in recovered]
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

    Un interlock activo (placa no disponible, falla de la platina) bloquea la apertura."""
    if name not in SHUTTERS:
        raise ValueError(f"Shutter desconocido: {name}")
    notes: list[tuple[str, str, bool]] = []
    with _nidaq_lock:
        if _shutter_interlocks:
            reason = "; ".join(f"{k}: {v}" for k, v in _shutter_interlocks.items())
            print(f"[NI-DAQ] open_shutter({name}) BLOQUEADO por interlock — {reason}")
            notes.append((name, f"apertura bloqueada por interlock ({reason})", False))
            ok = False
        else:
            idx = SHUTTERS.index(name)
            desired = list(_shutter_signal)
            desired[idx] = SHUTTER_POLARITY[name]
            err, simulated, recovered = _apply_shutter_lines(desired)
            # El watchdog se arma aunque la escritura falle: si el obturador llegó a abrirse,
            # el plazo lo cierra igual.
            heartbeat_shutter(timeout_s)
            notes += [(n, "cierre confirmado", True) for n in recovered]
            if err is None:
                if simulated:
                    print(f"[NI MOCK] open_shutter({name})")
                ok = True
            else:
                print(f"[NI-DAQ Error] open_shutter({name}) NO confirmado: {err}")
                notes.append((name, f"apertura no confirmada: {err}", False))
                ok = False
    _dispatch_shutter_notes(notes)
    return ok


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
            err, simulated, recovered = _apply_shutter_lines(desired)
            if err is None:
                break
            if attempt < SHUTTER_CLOSE_RETRIES - 1:
                time.sleep(SHUTTER_RETRY_DELAY_S)
        if err is None:
            if simulated:
                print(f"[NI MOCK] close_shutter({name})")
            notes += [(n, "cierre confirmado", True) for n in recovered]
            _settle_after_success()
            ok = True
        else:
            # El valor comandado sigue siendo "cerrar": toda escritura posterior lo reintenta.
            _shutter_signal[idx] = not SHUTTER_POLARITY[name]
            first = name not in _unconfirmed_shutters
            _unconfirmed_shutters.add(name)
            _arm_retry()
            print(f"[NI-DAQ Error] close_shutter({name}) NO confirmado tras "
                  f"{SHUTTER_CLOSE_RETRIES} intentos: {err}. Se trata como ABIERTO.")
            if first:
                notes.append((name, f"cierre NO confirmado tras {SHUTTER_CLOSE_RETRIES} intentos: {err}", False))
            ok = False
    _dispatch_shutter_notes(notes)
    return ok


def close_all_shutters() -> bool:
    """Cierra los cuatro obturadores con una sola escritura. Devuelve True sólo si se confirmó."""
    global _watchdog_deadline, _retry_due
    notes: list[tuple[str, str, bool]] = []
    with _nidaq_lock:
        desired = [not SHUTTER_POLARITY[s] for s in SHUTTERS]
        previously_open = [n for n, s in zip(SHUTTERS, _shutter_signal) if s == SHUTTER_POLARITY[n]]
        err = None
        for attempt in range(SHUTTER_CLOSE_RETRIES):
            err, _simulated, recovered = _apply_shutter_lines(desired)
            if err is None:
                break
            if attempt < SHUTTER_CLOSE_RETRIES - 1:
                time.sleep(SHUTTER_RETRY_DELAY_S)
        if err is None:
            notes += [(n, "cierre confirmado", True) for n in recovered]
            with _watchdog_lock:
                _watchdog_deadline = None
                _retry_due = None
            ok = True
        else:
            _shutter_signal[:] = desired
            for n in previously_open:
                if n not in _unconfirmed_shutters:
                    _unconfirmed_shutters.add(n)
                    notes.append((n, f"cierre NO confirmado tras {SHUTTER_CLOSE_RETRIES} intentos: {err}", False))
            if _unconfirmed_shutters:
                _arm_retry()
            print(f"[NI-DAQ Error] close_all_shutters() NO confirmado: {err}")
            ok = False
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


def _pulse_flipper(high_power: bool) -> bool:
    """Pulso de 5 ms en la salida analógica del flipper. El estado y los callbacks se
    actualizan DESPUÉS de una escritura exitosa (DEC-014/DEC-036), nunca antes."""
    global _flipper_task0, _flipper_task1
    label = "down_flipper" if high_power else "up_flipper"
    with _nidaq_lock:
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


def up_flipper() -> bool:
    """Flipper de potencia arriba (baja potencia). Devuelve True sólo si se confirmó."""
    return _pulse_flipper(False)


def down_flipper() -> bool:
    """Flipper de potencia abajo (alta potencia). Devuelve True sólo si se confirmó."""
    return _pulse_flipper(True)


def flipper_notch532(desired: str) -> bool:
    """Mueve el flipper notch 532. Devuelve True sólo si se confirmó (o no hacía falta moverlo)."""
    global _flipper_notch532_up
    if desired not in ("up", "down"):
        raise ValueError(f"Estado desconocido: '{desired}'")
    with _nidaq_lock:
        if SAFE_MODE:
            _flipper_notch532_up = (desired == "up")
            print(f"[NI MOCK] flipper_notch532({desired})"); return True
        try:
            task = _get_flipper532_task()
            if task is None:
                print(f"[NI-DAQ Error] flipper_notch532({desired}) rechazado: placa NO disponible.")
                return False
            if isinstance(task, _MockNITask):
                _flipper_notch532_up = (desired == "up")
                print(f"[NI MOCK] flipper_notch532({desired})"); return True
            need_up  = desired == "up"
            if need_up and not _flipper_notch532_up:
                task.write(True); time.sleep(0.003); task.write(False)
                _flipper_notch532_up = True
            elif not need_up and _flipper_notch532_up:
                task.write(True); time.sleep(0.003); task.write(False)
                _flipper_notch532_up = False
            return True
        except Exception as e:
            print(f"[NI-DAQ Error] flipper_notch532: {e}")
            return False


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
        close_all_shutters()
        return _UnavailableNITask(len(PD_CHANS_LIST) + 1, samps_per_chan)


def channels_triggers(task, axis: str) -> None:
    """Agrega el canal de trigger. En SAFE_MODE el _MockNITask ya lo incluye."""
    if SAFE_MODE or isinstance(task, _MockNITask):
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
