# -*- coding: utf-8 -*-
"""
test_powerbutton_actuation.py — Pruebas unitarias de reactividad y sincronización
para el checkbox Low power / High power y flippers en PyPrinting.

Valida:
1. Señal externa PyQt conectada a fe._power_check(bool)
2. Señal externa PyQt conectada al slot público fe.set_power(bool) / fe.set_flipper(bool)
3. Clics manuales en UI (fe.powerbutton.click())
4. Sincronización Backend -> Frontend (be.power_change -> fe.update_power_ui)
5. Notificación directa de hardware (nq.down_flipper / nq.up_flipper -> fe.update_power_ui)
6. Desacoplamiento de Watchdog: el auto-cierre cierra shutters pero preserva el estado del flipper
7. Resiliencia de hardware ante close_all_tasks() (inmunidad a tareas zombi)
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

    # ── Test 2: Conexión a fe.set_power(bool) y alias fe.set_flipper(bool) ───
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

    # ── Test 3: Clic de usuario en UI (fe.powerbutton.click()) ────────────────
    fe.powerbutton.click()
    app.processEvents()
    assert fe.powerbutton.isChecked() is True, "Clic debe poner powerbutton en True"
    assert "High" in fe.powerbutton.text()
    assert nq.is_flipper_high_power() is True, "Clic debe accionar flipper a High power"

    fe.powerbutton.click()
    app.processEvents()
    assert fe.powerbutton.isChecked() is False, "Clic debe poner powerbutton en False"
    assert "Low" in fe.powerbutton.text()
    assert nq.is_flipper_high_power() is False, "Clic debe accionar flipper a Low power"

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

    # ── Test 6: Desacoplamiento de Watchdog (el flipper no se ve alterado) ───
    # Abrir un shutter y activar High power en el flipper
    fe.shutter0button.setChecked(True)
    fe.set_power(True)
    app.processEvents()
    assert fe.shutter0button.isChecked() is True
    assert fe.powerbutton.isChecked() is True
    assert nq.is_flipper_high_power() is True

    # Disparar watchdog: debe cerrar el shutter pero respetar la posición del flipper
    fe._on_watchdog_triggered()
    app.processEvents()
    assert fe.shutter0button.isChecked() is False, "Watchdog debe cerrar shutters abiertos"
    assert fe.powerbutton.isChecked() is True, "Watchdog NO debe alterar la posición del flipper"
    assert nq.is_flipper_high_power() is True, "Hardware flipper debe permanecer en High power"

    # ── Test 7: Resiliencia ante close_all_tasks() (inmunidad a tareas zombi) ─
    nq.close_all_tasks()
    # Verificar que las variables globales se resetearon a None
    assert nq._flipper_task0 is None, "_flipper_task0 debe ser None tras close_all_tasks()"
    assert nq._flipper_task1 is None, "_flipper_task1 debe ser None tras close_all_tasks()"

    # Accionar el flipper después del cierre de tareas debe funcionar sin error
    fe.powerbutton.click()
    app.processEvents()
    assert fe.powerbutton.isChecked() is False
    assert "Low" in fe.powerbutton.text()

    fe.powerbutton.click()
    app.processEvents()
    assert fe.powerbutton.isChecked() is True
    assert "High" in fe.powerbutton.text()

    fe.close()
    print("ALL POWERBUTTON ACTUATION TESTS PASSED (100%)!")


if __name__ == "__main__":
    test_power_actuation_via_signals()
