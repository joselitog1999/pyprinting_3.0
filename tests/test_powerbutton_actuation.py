# -*- coding: utf-8 -*-
"""
test_powerbutton_actuation.py — Pruebas unitarias de reactividad y sincronización
para el checkbox Low power / High power y flippers en PyPrinting.

Valida:
1. Señal externa PyQt conectada a fe._power_check(bool)
2. Señal externa PyQt conectada a fe.powerbutton.setChecked(bool)
3. Señal externa PyQt conectada al slot público fe.set_power(bool) / fe.set_flipper(bool)
4. Sincronización Backend -> Frontend (be.power_change -> fe.update_power_ui)
5. Notificación directa de hardware (nq.down_flipper / nq.up_flipper -> fe.update_power_ui)
6. Clics manuales en UI (fe.powerbutton.click())
7. Cierre forzado del Watchdog y restauración a Low power en la UI
"""
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ["PYPRINTING_SAFE"] = "1"

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication
import core.nidaq as nq
from core.shutters import Frontend as ShuttersFrontend, Backend as ShuttersBackend


class ExternalSignalSource(QObject):
    bool_signal = pyqtSignal(bool)


def test_power_actuation_via_signals():
    app = QApplication.instance() or QApplication(sys.argv)
    fe = ShuttersFrontend()
    be = ShuttersBackend()
    be.make_connection(fe)

    src = ExternalSignalSource()

    # Estado Inicial: Low power
    assert not fe.powerbutton.isChecked(), "powerbutton debe iniciar desmarcado"
    assert "Low" in fe.powerbutton.text(), "Texto debe indicar Low power"
    assert not nq.is_flipper_high_power(), "Flipper hardware debe iniciar en baja potencia"

    # ── Test 1: Conexión a fe._power_check(bool) ─────────────────────────────
    src.bool_signal.connect(fe._power_check)
    src.bool_signal.emit(True)
    app.processEvents()
    assert fe.powerbutton.isChecked() is True, "powerbutton debe estar checked tras señal True a _power_check"
    assert "High" in fe.powerbutton.text(), "Texto debe cambiar a High power"
    assert nq.is_flipper_high_power() is True, "Hardware debe estar en High power"

    src.bool_signal.emit(False)
    app.processEvents()
    assert fe.powerbutton.isChecked() is False, "powerbutton debe estar unchecked tras señal False a _power_check"
    assert "Low" in fe.powerbutton.text(), "Texto debe volver a Low power"
    assert nq.is_flipper_high_power() is False, "Hardware debe volver a Low power"
    src.bool_signal.disconnect()

    # ── Test 2: Conexión a fe.powerbutton.setChecked(bool) ───────────────────
    src.bool_signal.connect(fe.powerbutton.setChecked)
    src.bool_signal.emit(True)
    app.processEvents()
    assert fe.powerbutton.isChecked() is True, "powerbutton debe marcarse con setChecked(True)"
    assert "High" in fe.powerbutton.text(), "Texto debe actualizarse a High power con setChecked(True)"
    assert nq.is_flipper_high_power() is True, "Hardware debe conmutar a High power con setChecked(True)"

    src.bool_signal.emit(False)
    app.processEvents()
    assert fe.powerbutton.isChecked() is False, "powerbutton debe desmarcarse con setChecked(False)"
    assert "Low" in fe.powerbutton.text(), "Texto debe actualizarse a Low power con setChecked(False)"
    assert nq.is_flipper_high_power() is False, "Hardware debe conmutar a Low power con setChecked(False)"
    src.bool_signal.disconnect()

    # ── Test 3: Conexión a fe.set_power(bool) y alias fe.set_flipper(bool) ───
    src.bool_signal.connect(fe.set_power)
    src.bool_signal.emit(True)
    app.processEvents()
    assert fe.powerbutton.isChecked() is True
    assert "High" in fe.powerbutton.text()
    assert nq.is_flipper_high_power() is True
    src.bool_signal.disconnect()

    src.bool_signal.connect(fe.set_flipper)
    src.bool_signal.emit(False)
    app.processEvents()
    assert fe.powerbutton.isChecked() is False
    assert "Low" in fe.powerbutton.text()
    assert nq.is_flipper_high_power() is False
    src.bool_signal.disconnect()

    # ── Test 4: Conmutación en Backend (be.power_change) ──────────────────────
    be.power_change(True)
    app.processEvents()
    assert fe.powerbutton.isChecked() is True, "UI debe sincronizarse cuando el backend cambia a High"
    assert "High" in fe.powerbutton.text()
    assert nq.is_flipper_high_power() is True

    be.power_change(False)
    app.processEvents()
    assert fe.powerbutton.isChecked() is False, "UI debe sincronizarse cuando el backend cambia a Low"
    assert "Low" in fe.powerbutton.text()
    assert nq.is_flipper_high_power() is False

    # ── Test 5: Llamadas directas en hardware (nq.down_flipper / up_flipper) ──
    nq.down_flipper()
    app.processEvents()
    assert fe.powerbutton.isChecked() is True, "UI debe actualizarse ante down_flipper() en hardware"
    assert "High" in fe.powerbutton.text()

    nq.up_flipper()
    app.processEvents()
    assert fe.powerbutton.isChecked() is False, "UI debe actualizarse ante up_flipper() en hardware"
    assert "Low" in fe.powerbutton.text()

    # ── Test 6: Clic de usuario en UI (fe.powerbutton.click()) ────────────────
    fe.powerbutton.click()
    app.processEvents()
    assert fe.powerbutton.isChecked() is True
    assert "High" in fe.powerbutton.text()
    assert nq.is_flipper_high_power() is True

    fe.powerbutton.click()
    app.processEvents()
    assert fe.powerbutton.isChecked() is False
    assert "Low" in fe.powerbutton.text()
    assert nq.is_flipper_high_power() is False

    # ── Test 7: Watchdog triggered resetea UI a Low power ────────────────────
    fe.set_power(True)
    app.processEvents()
    assert fe.powerbutton.isChecked() is True
    fe._on_watchdog_triggered()
    app.processEvents()
    assert fe.powerbutton.isChecked() is False, "Watchdog debe forzar la UI de potencia a Low power"
    assert "Low" in fe.powerbutton.text()

    fe.close()
    print("ALL POWERBUTTON ACTUATION TESTS PASSED (100%)!")


if __name__ == "__main__":
    test_power_actuation_via_signals()
