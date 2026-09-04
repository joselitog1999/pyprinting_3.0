# -*- coding: utf-8 -*-
"""
test_shutter_alignment_and_heartbeat.py — Pruebas unitarias para:
1. Modo Alineación continua (timeout_s=None) sin corte de Watchdog
2. Renovación de Heartbeat durante adquisición activa (Trace)
3. Callback del Watchdog y desmarcado automático en la UI
4. Selección de Modo Alineación en el panel de Shutters
PyPrinting 3.0 — UNSAM Nanofotónica
"""
import os
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ["PYPRINTING_SAFE"] = "1"

from PyQt6.QtWidgets import QApplication
import core.nidaq as nq
from core.shutters import Frontend as ShuttersFrontend, Backend as ShuttersBackend


def test_indefinite_alignment_mode():
    print("\n--- Test 1: Modo Alineacion Continua (timeout_s=None) ---")
    laser = "532 nm (green)"
    idx = nq.SHUTTERS.index(laser)

    # Abrir sin timeout (modo alineacion)
    nq.open_shutter(laser, timeout_s=None)
    assert nq._shutter_signal[idx] == nq.SHUTTER_POLARITY[laser], "El shutter debe estar abierto"
    assert not nq.is_watchdog_armed(), "El watchdog NO debe estar armado en modo alineacion"
    assert nq.get_watchdog_remaining_time() is None, "El tiempo restante debe ser None"

    # Esperar 0.5 s (si tuviera timeout corto se cerraria)
    time.sleep(0.5)
    assert nq._shutter_signal[idx] == nq.SHUTTER_POLARITY[laser], "El shutter debe permanecer abierto en modo alineacion"
    print("PASS: Shutter se mantiene abierto sin corte por Watchdog.")

    nq.close_shutter(laser)
    assert nq._shutter_signal[idx] != nq.SHUTTER_POLARITY[laser], "El shutter debe cerrarse tras close_shutter"


def test_heartbeat_renewal_active_trace():
    print("\n--- Test 2: Renovacion de Heartbeat durante bucle activo (Traza) ---")
    laser = "637 nm (red)"
    idx = nq.SHUTTERS.index(laser)

    # Abrir con timeout corto: 0.3 segundos
    nq.open_shutter(laser, timeout_s=0.3)
    assert nq.is_watchdog_armed(), "El watchdog debe estar armado"

    # Simular bucle de traza activo renovando heartbeat cada 0.1s durante 0.5s totales
    for _ in range(5):
        time.sleep(0.1)
        nq.heartbeat_shutter(0.3)
        assert nq._shutter_signal[idx] == nq.SHUTTER_POLARITY[laser], "El shutter no debe cerrarse mientras haya heartbeat"

    print("PASS: El shutter supero los 0.5 s (timeout original 0.3 s) gracias al latido activo.")
    nq.close_shutter(laser)


def test_watchdog_callback_and_ui_sync(app):
    print("\n--- Test 3: Sincronizacion de UI ante cierre por Watchdog ---")
    frontend = ShuttersFrontend()
    backend = ShuttersBackend()
    backend.make_connection(frontend)

    # Verificar timeout por defecto = 30s
    assert frontend.get_selected_timeout() == 30.0

    # Abrir shutter 0 en hardware con timeout corto de 0.2 s
    frontend.shutter0button.setChecked(True)
    nq.open_shutter(nq.SHUTTERS[0], timeout_s=0.2)
    idx0 = nq.SHUTTERS.index(nq.SHUTTERS[0])
    assert nq._shutter_signal[idx0] == nq.SHUTTER_POLARITY[nq.SHUTTERS[0]], "El shutter 0 debe estar abierto"

    # Esperar que expire el watchdog (0.5 s)
    time.sleep(0.5)
    app.processEvents()

    # Comprobar que en hardware se cerro y en la UI se desmarco
    assert nq._shutter_signal[idx0] != nq.SHUTTER_POLARITY[nq.SHUTTERS[0]], "El hardware debe haber cerrado el shutter"
    assert not frontend.shutter0button.isChecked(), "La UI debe desmarcar automaticamente la casilla tras cierre de watchdog"
    print("PASS: La UI se sincronizo y desmarco la casilla tras el cierre forzado del Watchdog.")

    frontend.close()


def test_ui_alignment_mode_selection(app):
    print("\n--- Test 4: Seleccion de Modo Alineacion en Frontend UI ---")
    frontend = ShuttersFrontend()
    backend = ShuttersBackend()
    backend.make_connection(frontend)

    # Cambiar a Sin limite (Alineacion) mediante findData(None)
    idx_align = frontend.combo_timeout.findData(None)
    assert idx_align >= 0, "Debe existir la opcion de alineacion con data None"
    frontend.combo_timeout.setCurrentIndex(idx_align)
    app.processEvents()

    assert backend.current_timeout is None, "El backend debe haber recibido timeout None"
    assert "ALINEACI" in frontend.lbl_security_status.text().upper(), "El label debe indicar Modo Alineacion"

    # Abrir shutter 1 en modo alineacion
    frontend.shutter1button.setChecked(True)
    frontend._shutter1_check()
    app.processEvents()

    idx1 = nq.SHUTTERS.index(nq.SHUTTERS[1])
    assert nq._shutter_signal[idx1] == nq.SHUTTER_POLARITY[nq.SHUTTERS[1]]
    assert not nq.is_watchdog_armed()

    # Cerrar todos desde el boton de Frontend
    frontend.btn_close_all.click()
    app.processEvents()

    assert not frontend.shutter1button.isChecked()
    assert nq._shutter_signal[idx1] != nq.SHUTTER_POLARITY[nq.SHUTTERS[1]]
    print("PASS: Selector de Modo Alineacion y boton 'Cerrar Todos' validados exitosamente.")

    frontend.close()


if __name__ == "__main__":
    app = QApplication.instance() or QApplication([])
    test_indefinite_alignment_mode()
    test_heartbeat_renewal_active_trace()
    test_watchdog_callback_and_ui_sync(app)
    test_ui_alignment_mode_selection(app)

    print("\n==================================================================")
    print("TODAS LAS PRUEBAS DE SHUTTERS, WATCHDOG Y ALINEACION FUERON EXITOSAS!")
    print("==================================================================")
    sys.exit(0)
