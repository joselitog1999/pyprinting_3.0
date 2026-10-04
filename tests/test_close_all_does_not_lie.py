# -*- coding: utf-8 -*-
""""Cerrar Todos" que no miente (C-01 Ronda 4, R4-17 fase 1; respuesta 3 (b) del 2026-10-02; DEC-044).

Antes (DEC-036): una escritura fallida marcaba como "sin confirmar" sólo los obturadores que el software creía
abiertos. Con nada creído abierto, `close_all_shutters()` devolvía False pero `_all_closed_confirmed()` daba True, y
el botón "Cerrar Todos" desmarcaba los obturadores antes de escribir e ignoraba el resultado: fallaba en silencio.

Contrato:
- después de una escritura fallida (apertura, cierre o cierre de todos), **las cuatro líneas** quedan sin confirmar:
  el estado real de la placa no se conoce. Se tratan como abiertas y el watchdog reintenta;
- una escritura exitosa aplica el arreglo completo, así que confirma las cuatro;
- "Cerrar Todos" escribe primero y desmarca sólo si la placa confirmó; si no, los obturadores quedan marcados en
  rojo con el banner de DEC-036.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYPRINTING_SAFE", "1")

import pytest

from test_shutter_confirmation_and_interlocks import LASER, OTHER, _closed, daq  # noqa: F401  (fixture)

from core import nidaq


def test_a_failed_close_all_with_nothing_believed_open_confirms_nothing(daq):
    daq.write_failures = nidaq.SHUTTER_CLOSE_RETRIES
    assert nidaq.close_all_shutters() is False
    assert sorted(nidaq.get_unconfirmed_shutters()) == sorted(nidaq.SHUTTERS)
    assert nidaq._all_closed_confirmed() is False
    assert nidaq._retry_due is not None
    assert sorted(nidaq.get_open_shutter_names()) == sorted(nidaq.SHUTTERS)      # se tratan como abiertos
    faults = {e[0] for e in daq.events if not e[2]}
    assert faults == set(nidaq.SHUTTERS)
    assert all("cierre" in e[1] for e in daq.events if not e[2])


def test_the_watchdog_retry_confirms_all_four_later(daq):
    from test_shutter_confirmation_and_interlocks import _wait
    daq.write_failures = nidaq.SHUTTER_CLOSE_RETRIES
    nidaq.close_all_shutters()
    assert _wait(lambda: not nidaq.get_unconfirmed_shutters())
    assert nidaq._all_closed_confirmed() is True


def test_a_failed_open_leaves_all_four_unconfirmed(daq):
    daq.write_failures = 1
    assert nidaq.open_shutter(LASER, timeout_s=5.0) is False
    assert sorted(nidaq.get_unconfirmed_shutters()) == sorted(nidaq.SHUTTERS)
    assert LASER in nidaq.get_open_shutter_names()                     # pudo haber abierto
    nidaq.close_shutter(LASER)
    assert not nidaq.get_unconfirmed_shutters()


def test_a_failed_close_marks_an_intentionally_open_line_too(daq):
    nidaq.WATCHDOG_RETRY_INTERVAL_S = 60.0                              # que no se adelante el watchdog
    assert nidaq.open_shutter(OTHER, timeout_s=None) is True
    assert nidaq.open_shutter(LASER, timeout_s=None) is True
    daq.write_failures = nidaq.SHUTTER_CLOSE_RETRIES
    assert nidaq.close_shutter(LASER) is False
    assert sorted(nidaq.get_unconfirmed_shutters()) == sorted(nidaq.SHUTTERS)
    other_note = [e for e in daq.events if e[0] == OTHER and not e[2]]
    assert other_note and "sin confirmar" in other_note[0][1]
    # el que estaba abierto a propósito sigue comandado abierto
    assert nidaq._shutter_signal[nidaq.SHUTTERS.index(OTHER)] == nidaq.SHUTTER_POLARITY[OTHER]
    # una escritura exitosa confirma las cuatro y no cambia lo comandado
    assert nidaq.close_shutter(LASER) is True
    assert not nidaq.get_unconfirmed_shutters()
    assert nidaq._shutter_signal[nidaq.SHUTTERS.index(OTHER)] == nidaq.SHUTTER_POLARITY[OTHER]
    nidaq.close_shutter(OTHER)


# ── El botón ────────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def dock(daq):
    from PyQt6.QtWidgets import QApplication
    from core.shutters import Frontend
    QApplication.instance() or QApplication(["pytest"])
    fe = Frontend()
    _KEEP_ALIVE.append(fe)
    return fe, daq


_KEEP_ALIVE = []


def _buttons(fe):
    return [fe.shutter0button, fe.shutter1button, fe.shutter2button, fe.shutter3button]


def _process():
    from PyQt6.QtWidgets import QApplication
    for _ in range(5):
        QApplication.processEvents()


def test_close_all_unchecks_only_after_a_confirmed_close(dock):
    fe, daq = dock
    nidaq.WATCHDOG_RETRY_INTERVAL_S = 60.0          # que el reintento no confirme antes de mirar la casilla
    idx = nidaq.SHUTTERS.index(LASER)
    btn = _buttons(fe)[idx]
    assert nidaq.open_shutter(LASER, timeout_s=None)                       # el obturador abierto, y su casilla
    btn.blockSignals(True); btn.setChecked(True); btn.blockSignals(False)
    assert btn.isChecked() and LASER in nidaq.get_open_shutter_names()
    daq.write_failures = nidaq.SHUTTER_CLOSE_RETRIES
    fe._close_all_shutters_clicked()
    _process()
    assert btn.isChecked()                                               # no se desmarca: el cierre falló
    assert "f38ba8" in btn.styleSheet()
    assert fe.lbl_fault_banner.isVisible() or not fe.lbl_fault_banner.isHidden()
    assert "SIN CONFIRMAR" in fe.lbl_fault_banner.text()
    fe._close_all_shutters_clicked()                                     # ahora sí confirma
    _process()
    assert not btn.isChecked() and not nidaq.get_unconfirmed_shutters()


def test_close_all_with_a_working_board_unchecks_everything(dock):
    fe, daq = dock
    btn = _buttons(fe)[nidaq.SHUTTERS.index(LASER)]
    assert nidaq.open_shutter(LASER, timeout_s=None)
    btn.blockSignals(True); btn.setChecked(True); btn.blockSignals(False)
    fe._close_all_shutters_clicked()
    _process()
    assert not any(b.isChecked() for b in _buttons(fe) if b is not None)
    assert nidaq.get_open_shutter_names() == []


def test_an_intentionally_open_line_stays_checked_and_red_until_confirmed(dock):
    fe, daq = dock
    nidaq.WATCHDOG_RETRY_INTERVAL_S = 60.0
    b_other = _buttons(fe)[nidaq.SHUTTERS.index(OTHER)]
    for name in (OTHER, LASER):
        assert nidaq.open_shutter(name, timeout_s=None)
        b = _buttons(fe)[nidaq.SHUTTERS.index(name)]
        b.blockSignals(True); b.setChecked(True); b.blockSignals(False)
    daq.write_failures = nidaq.SHUTTER_CLOSE_RETRIES
    assert nidaq.close_shutter(LASER) is False                         # el cierre del otro falla
    _process()
    assert b_other.isChecked() and "f38ba8" in b_other.styleSheet()    # sigue abierto, sin confirmar
    assert nidaq.close_shutter(LASER) is True                          # una escritura buena confirma todo
    _process()
    assert b_other.isChecked() and "f38ba8" not in b_other.styleSheet()
    nidaq.close_shutter(OTHER)
