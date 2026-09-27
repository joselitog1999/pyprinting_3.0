# -*- coding: utf-8 -*-
"""
test_shutter_confirmation_and_interlocks.py — Obturadores confirmados, sin simulador en producción.

PyPrinting 3.0 — UNSAM Nanofotónica (DEC-036)

Antes de DEC-036, `close_shutter()` marcaba el obturador como cerrado ANTES de escribir; si la
escritura fallaba sólo imprimía el error y además desarmaba el watchdog, así que nadie volvía a
intentar cerrarlo. Y si la tarea DAQmx no se podía crear, los obturadores pasaban en silencio a
un simulador aun con SAFE_MODE apagado.

Estos caminos son inalcanzables en SAFE_MODE, por eso los tests fuerzan la rama de producción
(`nidaq.SAFE_MODE = False`) con un `nidaqmx` falso que falla a demanda. Nada toca hardware. Un
fixture guarda y restaura todo el estado global del módulo: un interlock o un obturador "sin
confirmar" que se filtrara bloquearía los tests de otros archivos.
"""
import os
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("PYPRINTING_SAFE", "1")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import math
import pytest
from PyQt6.QtWidgets import QApplication

# QApplication a nivel de módulo y viva todo el archivo: si la crea un test como variable
# local, al destruirse PyQt borra también el singleton HardwareManager.
app = QApplication.instance() or QApplication(sys.argv)

from core import nidaq


# ── nidaqmx falso ────────────────────────────────────────────────────────────

class _Chans:
    def add_do_chan(self, *a, **k): pass
    def add_ao_voltage_chan(self, *a, **k): pass
    def add_ai_voltage_chan(self, *a, **k): pass


class _Timing:
    def cfg_samp_clk_timing(self, *a, **k): pass


class _FakeTask:
    def __init__(self, daq):
        self._daq = daq
        self.do_channels = _Chans()
        self.ao_channels = _Chans()
        self.ai_channels = _Chans()
        self.timing = _Timing()

    def write(self, data, auto_start=True):
        if self._daq.write_failures > 0:
            self._daq.write_failures -= 1
            raise RuntimeError("DAQmx Error -200088 (simulado)")
        self._daq.writes.append(list(data) if isinstance(data, (list, tuple)) else data)

    def is_task_done(self): return True
    def close(self): pass
    def start(self): pass
    def stop(self): pass


class _FakeNidaqmx:
    def __init__(self):
        self.create_error = None
        self.write_failures = 0
        self.writes = []

    def Task(self, *a, **k):
        if self.create_error is not None:
            raise self.create_error
        return _FakeTask(self)


class _Consts:
    CHAN_PER_LINE = "chan_per_line"
    CONTINUOUS = "continuous"
    FINITE = "finite"


_STATE = ("SAFE_MODE", "_shutter_task", "_flipper_task0", "_flipper_task1", "_flipper532_task",
          "_retry_due", "_watchdog_deadline", "_flipper_high_power", "WATCHDOG_RETRY_INTERVAL_S",
          "SHUTTER_RETRY_DELAY_S")


@pytest.fixture
def daq(monkeypatch):
    saved = {k: getattr(nidaq, k) for k in _STATE}
    saved_signal = list(nidaq._shutter_signal)
    saved_unconf = set(nidaq._unconfirmed_shutters)
    saved_locks = dict(nidaq._shutter_interlocks)
    saved_fault_cbs = list(nidaq._shutter_fault_callbacks)
    saved_flip_cbs = list(nidaq._flipper_callbacks)

    fake = _FakeNidaqmx()
    monkeypatch.setattr(nidaq, "nidaqmx", fake, raising=False)
    monkeypatch.setattr(nidaq, "LineGrouping", _Consts, raising=False)
    monkeypatch.setattr(nidaq, "AcquisitionType", _Consts, raising=False)
    monkeypatch.setattr(nidaq, "_is_daq_isolated", lambda: False)
    nidaq.SAFE_MODE = False
    nidaq.SHUTTER_RETRY_DELAY_S = 0.0
    nidaq.WATCHDOG_RETRY_INTERVAL_S = 0.2
    for k in ("_shutter_task", "_flipper_task0", "_flipper_task1", "_flipper532_task"):
        setattr(nidaq, k, None)
    nidaq._shutter_signal[:] = [not nidaq.SHUTTER_POLARITY[s] for s in nidaq.SHUTTERS]
    nidaq._unconfirmed_shutters.clear()
    nidaq._shutter_interlocks.clear()
    nidaq._retry_due = None
    nidaq._watchdog_deadline = None

    events = []
    cb = lambda name, detail, confirmed: events.append((name, detail, confirmed))
    nidaq.register_shutter_fault_callback(cb)
    fake.events = events
    try:
        yield fake
    finally:
        for k, v in saved.items():
            setattr(nidaq, k, v)
        nidaq._shutter_signal[:] = saved_signal
        nidaq._unconfirmed_shutters.clear(); nidaq._unconfirmed_shutters.update(saved_unconf)
        nidaq._shutter_interlocks.clear(); nidaq._shutter_interlocks.update(saved_locks)
        nidaq._shutter_fault_callbacks[:] = saved_fault_cbs
        nidaq._flipper_callbacks[:] = saved_flip_cbs


LASER = nidaq.SHUTTERS[1]
OTHER = nidaq.SHUTTERS[2]


def _closed(name):
    return not nidaq.SHUTTER_POLARITY[name]


def _wait(cond, timeout=3.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if cond():
            return True
        time.sleep(0.02)
    return cond()


# ── 1. Cierre no confirmado ──────────────────────────────────────────────────

def test_close_failure_is_treated_as_open_and_keeps_retrying(daq):
    assert nidaq.open_shutter(LASER, timeout_s=None) is True
    daq.write_failures = nidaq.SHUTTER_CLOSE_RETRIES
    assert nidaq.close_shutter(LASER) is False
    assert LASER in nidaq.get_unconfirmed_shutters()
    assert LASER in nidaq.get_open_shutter_names(), "Un cierre sin confirmar debe contar como abierto"
    assert nidaq._retry_due is not None, "El watchdog tiene que seguir reintentando"
    assert nidaq._shutter_signal[nidaq.SHUTTERS.index(LASER)] == _closed(LASER), (
        "El valor comandado debe seguir siendo 'cerrar': si quedara 'abrir', la próxima "
        "escritura de otro obturador abriría éste")
    faults = [e for e in daq.events if e[0] == LASER and not e[2]]
    assert len(faults) == 1


def test_fault_is_reported_once_per_episode(daq):
    nidaq.open_shutter(LASER, timeout_s=None)
    daq.write_failures = 2 * nidaq.SHUTTER_CLOSE_RETRIES
    nidaq.close_shutter(LASER)
    nidaq.close_shutter(LASER)
    assert len([e for e in daq.events if e[0] == LASER and not e[2]]) == 1


def test_watchdog_retry_confirms_the_close_later(daq):
    nidaq.open_shutter(LASER, timeout_s=None)
    daq.write_failures = nidaq.SHUTTER_CLOSE_RETRIES
    nidaq.close_shutter(LASER)
    assert _wait(lambda: not nidaq.get_unconfirmed_shutters()), "El watchdog no confirmó el cierre"
    assert (LASER, "cierre confirmado en un reintento", True) in daq.events
    assert daq.writes[-1][nidaq.SHUTTERS.index(LASER)] == _closed(LASER)
    assert nidaq._watchdog_deadline is None and nidaq._retry_due is None


def test_any_later_successful_write_confirms_a_pending_close(daq):
    nidaq.open_shutter(LASER, timeout_s=None)
    daq.write_failures = nidaq.SHUTTER_CLOSE_RETRIES
    nidaq.close_shutter(LASER)
    nidaq.WATCHDOG_RETRY_INTERVAL_S = 60.0  # que no se adelante el watchdog
    nidaq._arm_retry()
    assert nidaq.open_shutter(OTHER, timeout_s=None) is True
    assert LASER not in nidaq.get_unconfirmed_shutters()
    assert daq.writes[-1][nidaq.SHUTTERS.index(LASER)] == _closed(LASER)
    nidaq.close_shutter(OTHER)


def test_close_all_failure_marks_previously_open_shutters(daq):
    nidaq.open_shutter(LASER, timeout_s=None)
    daq.write_failures = nidaq.SHUTTER_CLOSE_RETRIES
    assert nidaq.close_all_shutters() is False
    assert nidaq.get_unconfirmed_shutters() == [LASER]
    assert all(s == _closed(n) for n, s in zip(nidaq.SHUTTERS, nidaq._shutter_signal))


# ── 2. Apertura ──────────────────────────────────────────────────────────────

def test_failed_open_is_not_reported_as_open(daq):
    daq.write_failures = 1
    assert nidaq.open_shutter(LASER, timeout_s=5.0) is False
    assert nidaq._shutter_signal[nidaq.SHUTTERS.index(LASER)] == _closed(LASER)
    assert nidaq.is_watchdog_armed(), "Si llegó a abrirse, el plazo tiene que cerrarlo"
    assert any(e[0] == LASER and not e[2] for e in daq.events)
    nidaq.close_shutter(LASER)


# ── 3. Interlocks y producción sin simulador ─────────────────────────────────

def test_interlock_blocks_every_opening(daq):
    nidaq.set_shutter_interlock("Platina PI", "comunicación perdida")
    n_writes = len(daq.writes)
    assert nidaq.open_shutter(LASER, timeout_s=None) is False
    assert len(daq.writes) == n_writes, "Con interlock no debe escribirse nada"
    nidaq.clear_shutter_interlock("Platina PI")
    assert nidaq.open_shutter(LASER, timeout_s=None) is True
    nidaq.close_shutter(LASER)


def test_trip_interlock_closes_everything(daq):
    nidaq.open_shutter(LASER, timeout_s=None)
    assert nidaq.trip_shutter_interlock("Platina PI", "prueba") is True
    assert nidaq.get_open_shutter_names() == []
    assert nidaq.open_shutter(LASER, timeout_s=None) is False


def test_no_simulator_when_the_task_cannot_be_created(daq):
    daq.create_error = RuntimeError("Could not find an installation of NI-DAQmx")
    assert nidaq.open_shutter(LASER, timeout_s=None) is False
    assert "NI-DAQmx" in nidaq.get_shutter_interlocks()
    assert daq.writes == []
    assert not isinstance(nidaq._shutter_task, nidaq._MockNITask)


def test_photodiode_failure_reads_nan_and_blocks_lasers(daq):
    daq.create_error = RuntimeError("DAQmx no disponible")
    task = nidaq.channels_photodiodos(10000.0, 10)
    assert isinstance(task, nidaq._UnavailableNITask)
    data = task.read(10)
    assert all(math.isnan(v) for ch in data for v in ch), "Sin placa no hay datos, sólo NaN"
    assert "NI-DAQmx" in nidaq.get_shutter_interlocks()


# ── 4. Flipper de potencia: estado sólo después de confirmar ─────────────────

def test_flipper_state_changes_only_after_a_confirmed_write(daq):
    seen = []
    nidaq.register_flipper_callback(seen.append)
    nidaq._flipper_high_power = False
    daq.write_failures = 2  # falla la escritura y el reintento con tarea nueva
    assert nidaq.down_flipper() is False
    assert nidaq.is_flipper_high_power() is False
    assert seen == []
    assert nidaq.down_flipper() is True
    assert nidaq.is_flipper_high_power() is True
    assert seen == [True]


# ── 5. Panel de obturadores (mini Ronda 3) ───────────────────────────────────

def test_panel_shows_unconfirmed_close_until_confirmed():
    """El panel refleja el estado real: un cierre sin confirmar queda marcado y en rojo con un
    banner persistente, y vuelve a la normalidad cuando el cierre se confirma. No hace falta la
    rama de producción: se inyecta la notificación que emite nidaq."""
    from core.shutters import Frontend
    fe = Frontend()
    try:
        name = nidaq.SHUTTERS[1]
        btn = fe.shutter1button
        nidaq._dispatch_shutter_notes([(name, "cierre NO confirmado tras 3 intentos: DAQmx", False)])
        app.processEvents()
        assert btn.isChecked(), "Un cierre sin confirmar se muestra como abierto"
        assert fe.lbl_fault_banner.isVisibleTo(fe)
        assert name in fe.lbl_fault_banner.text()
        fe._on_watchdog_triggered()
        assert btn.isChecked(), "El aviso del watchdog no debe desmarcar un cierre sin confirmar"
        nidaq._dispatch_shutter_notes([(name, "cierre confirmado en un reintento", True)])
        app.processEvents()
        assert not btn.isChecked()
        assert not fe.lbl_fault_banner.isVisibleTo(fe), "Confirmado el cierre, el banner desaparece"
        nidaq._dispatch_shutter_notes([(name, "apertura bloqueada por interlock (Platina PI: prueba)", False)])
        app.processEvents()
        assert not btn.isChecked(), "Una apertura rechazada no se muestra como abierta"
        assert "interlock" in fe.lbl_fault_banner.text()
    finally:
        fe.close()


# ── 6. Aislamiento de NI-DAQ con placa presente (decisión 2b) ────────────────

def _fake_nidaqmx_system(device_names):
    import types
    dev = lambda n: types.SimpleNamespace(name=n)
    system_mod = types.ModuleType("nidaqmx.system")
    system_mod.System = types.SimpleNamespace(
        local=lambda: types.SimpleNamespace(devices=[dev(n) for n in device_names]))
    pkg = types.ModuleType("nidaqmx")
    pkg.system = system_mod
    return {"nidaqmx": pkg, "nidaqmx.system": system_mod}


def test_isolating_the_daq_is_refused_when_the_board_is_present(monkeypatch):
    from core import hardware_manager as hm_mod
    hm = hm_mod.hardware_manager
    monkeypatch.setattr(hm_mod, "SAFE_MODE", False)
    for k, v in _fake_nidaqmx_system([hm_mod.NIDAQ_DEVICE]).items():
        monkeypatch.setitem(sys.modules, k, v)
    emitted = []
    hm.isolationChangedSignal.connect(lambda d, iso: emitted.append((d, iso)))
    before = hm.device_isolated.get(hm_mod.NIDAQ_DEVICE_KEY, False)
    try:
        assert hm.physical_daq_present() is True
        hm.toggle_isolation(hm_mod.NIDAQ_DEVICE_KEY, True)
        assert hm.is_isolated(hm_mod.NIDAQ_DEVICE_KEY) is False, "Con placa presente no se puede aislar"
        assert (hm_mod.NIDAQ_DEVICE_KEY, False) in emitted, "La casilla del Dashboard debe volver atrás"
    finally:
        hm.device_isolated[hm_mod.NIDAQ_DEVICE_KEY] = before


def test_isolating_the_daq_is_allowed_without_a_board(monkeypatch):
    from core import hardware_manager as hm_mod
    hm = hm_mod.hardware_manager
    monkeypatch.setattr(hm_mod, "SAFE_MODE", False)
    for k, v in _fake_nidaqmx_system(["Dev7"]).items():
        monkeypatch.setitem(sys.modules, k, v)
    before = hm.device_isolated.get(hm_mod.NIDAQ_DEVICE_KEY, False)
    monkeypatch.setattr(hm, "connect_device", lambda dev: None)
    try:
        assert hm.physical_daq_present() is False
        hm.toggle_isolation(hm_mod.NIDAQ_DEVICE_KEY, True)
        assert hm.is_isolated(hm_mod.NIDAQ_DEVICE_KEY) is True
    finally:
        hm.device_isolated[hm_mod.NIDAQ_DEVICE_KEY] = before
