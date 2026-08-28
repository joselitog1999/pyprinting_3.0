# -*- coding: utf-8 -*-
"""
nidaq.py — Capa de abstracción NI-DAQ
PyPrinting — UNSAM Nanofotónica

En SAFE_MODE todas las funciones son no-op o devuelven datos sintéticos.
La lógica real solo se instancia si SAFE_MODE = False.
"""
from __future__ import annotations
import time
import numpy as np

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

_shutter_signal: list[bool]       = [not SHUTTER_POLARITY[s] for s in SHUTTERS]
_flipper_notch532_up: bool        = True
_shutter_task                     = None
_flipper_task0                    = None
_flipper_task1                    = None
_flipper532_task                  = None
_laser532_task                    = None


def _get_shutter_task():
    global _shutter_task
    if SAFE_MODE:
        return _MockNITask(len(SHUTTERS), 1)
    try:
        from core.hardware_manager import hardware_manager
        if hardware_manager.is_isolated("NI-DAQmx (Dev1)"):
            return _MockNITask(len(SHUTTERS), 1)
    except Exception:
        pass
    if _shutter_task is None:
        try:
            _shutter_task = nidaqmx.Task()
            for ch in SHUTTER_CHANNELS:
                _shutter_task.do_channels.add_do_chan(
                    lines=f"{NIDAQ_DEVICE}/port0/line{ch}",
                    line_grouping=LineGrouping.CHAN_PER_LINE)
        except Exception as e:
            print(f"[NI-DAQ Warning] No se pudo inicializar tarea de shutters: {e}. Usando mock.")
            return _MockNITask(len(SHUTTERS), 1)
    return _shutter_task


def _get_flipper_tasks():
    global _flipper_task0, _flipper_task1
    if SAFE_MODE:
        return _MockNITask(1, 1), _MockNITask(1, 1)
    try:
        from core.hardware_manager import hardware_manager
        if hardware_manager.is_isolated("NI-DAQmx (Dev1)"):
            return _MockNITask(1, 1), _MockNITask(1, 1)
    except Exception:
        pass
    try:
        if _flipper_task0 is None:
            _flipper_task0 = nidaqmx.Task()
            _flipper_task0.ao_channels.add_ao_voltage_chan(FLIPPER_AO_DOWN)
        if _flipper_task1 is None:
            _flipper_task1 = nidaqmx.Task()
            _flipper_task1.ao_channels.add_ao_voltage_chan(FLIPPER_AO_UP)
        return _flipper_task0, _flipper_task1
    except Exception as e:
        print(f"[NI-DAQ Warning] No se pudo inicializar tarea de flippers: {e}. Usando mock.")
        return _MockNITask(1, 1), _MockNITask(1, 1)


def _get_flipper532_task():
    global _flipper532_task
    if SAFE_MODE:
        return _MockNITask(1, 1)
    try:
        from core.hardware_manager import hardware_manager
        if hardware_manager.is_isolated("NI-DAQmx (Dev1)"):
            return _MockNITask(1, 1)
    except Exception:
        pass
    try:
        if _flipper532_task is None:
            _flipper532_task = nidaqmx.Task()
            _flipper532_task.do_channels.add_do_chan(
                lines=f"{NIDAQ_DEVICE}/port0/line{FLIPPER_532_CHAN}",
                line_grouping=LineGrouping.CHAN_PER_LINE)
        return _flipper532_task
    except Exception as e:
        print(f"[NI-DAQ Warning] No se pudo inicializar tarea de flipper 532: {e}. Usando mock.")
        return _MockNITask(1, 1)


# ══════════════════════════════════════════════════════════════════════════════
#  API PÚBLICA  — misma en ambos modos
# ══════════════════════════════════════════════════════════════════════════════

def open_shutter(name: str) -> None:
    if name not in SHUTTERS:
        raise ValueError(f"Shutter desconocido: {name}")
    if SAFE_MODE:
        print(f"[NI MOCK] open_shutter({name})")
        return
    try:
        from core.hardware_manager import hardware_manager
        if hardware_manager.is_isolated("NI-DAQmx (Dev1)"):
            print(f"[NI MOCK (Aislado)] open_shutter({name})")
            return
    except Exception:
        pass
    try:
        idx = SHUTTERS.index(name)
        _shutter_signal[idx] = SHUTTER_POLARITY[name]
        t = _get_shutter_task()
        if isinstance(t, _MockNITask):
            print(f"[NI MOCK] open_shutter({name})")
        else:
            t.write(_shutter_signal, auto_start=True)
    except Exception as e:
        print(f"[NI-DAQ Error] open_shutter({name}): {e}")


def close_shutter(name: str) -> None:
    if name not in SHUTTERS:
        raise ValueError(f"Shutter desconocido: {name}")
    if SAFE_MODE:
        print(f"[NI MOCK] close_shutter({name})")
        return
    try:
        from core.hardware_manager import hardware_manager
        if hardware_manager.is_isolated("NI-DAQmx (Dev1)"):
            print(f"[NI MOCK (Aislado)] close_shutter({name})")
            return
    except Exception:
        pass
    try:
        idx = SHUTTERS.index(name)
        _shutter_signal[idx] = not SHUTTER_POLARITY[name]
        t = _get_shutter_task()
        if isinstance(t, _MockNITask):
            print(f"[NI MOCK] close_shutter({name})")
        else:
            t.write(_shutter_signal, auto_start=True)
    except Exception as e:
        print(f"[NI-DAQ Error] close_shutter({name}): {e}")


def close_all_shutters() -> None:
    for name in SHUTTERS:
        close_shutter(name)


def up_flipper() -> None:
    if SAFE_MODE:
        print("[NI MOCK] up_flipper()"); return
    try:
        t0, t1 = _get_flipper_tasks()
        if isinstance(t1, _MockNITask):
            print("[NI MOCK] up_flipper()"); return
        t1.write(5); time.sleep(0.003); t1.write(0)
    except Exception as e:
        print(f"[NI-DAQ Error] up_flipper: {e}")


def down_flipper() -> None:
    if SAFE_MODE:
        print("[NI MOCK] down_flipper()"); return
    try:
        t0, t1 = _get_flipper_tasks()
        if isinstance(t0, _MockNITask):
            print("[NI MOCK] down_flipper()"); return
        t0.write(5); time.sleep(0.003); t0.write(0)
    except Exception as e:
        print(f"[NI-DAQ Error] down_flipper: {e}")


def flipper_notch532(desired: str) -> None:
    global _flipper_notch532_up
    if desired not in ("up", "down"):
        raise ValueError(f"Estado desconocido: '{desired}'")
    if SAFE_MODE:
        _flipper_notch532_up = (desired == "up")
        print(f"[NI MOCK] flipper_notch532({desired})"); return
    try:
        task = _get_flipper532_task()
        if isinstance(task, _MockNITask):
            _flipper_notch532_up = (desired == "up")
            print(f"[NI MOCK] flipper_notch532({desired})"); return
        need_up  = desired == "up"
        if need_up and not _flipper_notch532_up:
            task.write(True); time.sleep(0.003); task.write(False)
            _flipper_notch532_up = True
        elif not need_up and _flipper_notch532_up:
            task.write(True); time.sleep(0.003); task.write(False)
            _flipper_notch532_up = False
    except Exception as e:
        print(f"[NI-DAQ Error] flipper_notch532: {e}")


def channels_photodiodos(rate: float, samps_per_chan: int):
    """Devuelve una Task real o un _MockNITask según SAFE_MODE o disponibilidad."""
    if SAFE_MODE:
        return _MockNITask(len(PD_CHANS_LIST) + 1, samps_per_chan)
    try:
        from core.hardware_manager import hardware_manager
        if hardware_manager.is_isolated("NI-DAQmx (Dev1)"):
            return _MockNITask(len(PD_CHANS_LIST) + 1, samps_per_chan)
    except Exception:
        pass
    try:
        task = nidaqmx.Task()
        for ch in PD_CHANS_LIST:
            task.ai_channels.add_ai_voltage_chan(
                physical_channel=f"{NIDAQ_DEVICE}/ai{ch}",
                name_to_assign_to_channel=f"chan_PD{ch}")
        task.timing.cfg_samp_clk_timing(
            rate=rate,
            sample_mode=AcquisitionType.FINITE,
            samps_per_chan=samps_per_chan)
        return task
    except Exception as e:
        print(f"[NI-DAQ Warning] Error al crear task de fotodiodos ({e}). Usando mock.")
        return _MockNITask(len(PD_CHANS_LIST) + 1, samps_per_chan)


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
        print(f"[NI MOCK] láser 532 → {v:.3f} V"); return
    try:
        from core.hardware_manager import hardware_manager
        if hardware_manager.is_isolated("NI-DAQmx (Dev1)"):
            print(f"[NI MOCK (Aislado)] láser 532 → {v:.3f} V"); return
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
    if SAFE_MODE:
        return
    for var in ("_shutter_task", "_flipper_task0", "_flipper_task1",
                "_flipper532_task", "_laser532_task"):
        task = globals().get(var)
        if task is not None:
            try:
                task.stop(); task.close()
            except Exception:
                pass
