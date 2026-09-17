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

# `config` debe importarse ANTES que PyQt6: este entorno tiene dos instalaciones de PyQt6
# para Python 3.13 (la de conda base, con DLLs nativas rotas, y la de .venv/, funcional).
# config.py antepone .venv/Lib/site-packages a sys.path al importarse — si PyQt6 se importa
# primero, Python lo resuelve desde la instalación rota y falla con "DLL load failed while
# importing QtWidgets" de forma determinística (no es un problema de entorno intermitente).
import config  # noqa: F401
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


def test_experimental_routine_respects_global_alignment_policy(app):
    """PASO 1 (unificacion de politica de timeout): si el usuario selecciona 'Sin limite
    (Modo Alineacion)' en el dock de Shutters, una rutina experimental que llama a
    open_shutter(laser) SIN pasar timeout_s -- el patron real usado en confocal.py,
    measurements.py, focus.py, growth_kinetics.py, etc. -- debe heredar esa politica
    global, no rearmar el watchdog a 30s como ocurria antes de unificar
    core/nidaq.py::set_default_shutter_timeout() con core/shutters.py::set_autoclose_timeout()."""
    print("\n--- Test 5: Rutina experimental respeta la politica global 'Sin limite' ---")
    frontend = ShuttersFrontend()
    backend = ShuttersBackend()
    backend.make_connection(frontend)

    # El usuario elige "Sin limite" en el dock ANTES de arrancar cualquier rutina
    idx_align = frontend.combo_timeout.findData(None)
    assert idx_align >= 0
    frontend.combo_timeout.setCurrentIndex(idx_align)
    app.processEvents()
    assert nq.get_default_shutter_timeout() is None, "La politica global debe quedar en None tras elegir Sin limite"

    # Simula una rutina experimental (Confocal, Measurements, Focus...) abriendo el
    # shutter SIN timeout_s explicito -- exactamente la firma que usan esos modulos.
    laser = nq.SHUTTERS[2]
    nq.open_shutter(laser)
    assert nq._shutter_signal[nq.SHUTTERS.index(laser)] == nq.SHUTTER_POLARITY[laser]
    assert not nq.is_watchdog_armed(), (
        "open_shutter(laser) sin timeout_s explicito NO debe rearmar el watchdog a 30s "
        "cuando la politica global es Sin Limite (bug corregido en DEC-010)"
    )

    nq.close_shutter(laser)
    frontend.close()
    print("PASS: open_shutter() sin argumento hereda la politica global 'Sin limite'.")


def test_experimental_routine_respects_global_30s_policy(app):
    """Camino inverso del test anterior: con la politica global en 30 s (el default de
    fabrica), open_shutter(laser) sin argumento debe armar el watchdog a ~30 s -- para
    confirmar que el fix no rompio el comportamiento por defecto de las rutinas."""
    print("\n--- Test 6: Rutina experimental respeta la politica global de 30 s ---")
    frontend = ShuttersFrontend()
    backend = ShuttersBackend()
    backend.make_connection(frontend)

    idx_30 = frontend.combo_timeout.findData(30.0)
    assert idx_30 >= 0
    frontend.chk_autoclose.setChecked(True)
    frontend.combo_timeout.setCurrentIndex(idx_30)
    # Llamada directa (no solo dependiente de la señal currentIndexChanged): un Frontend
    # recién creado ya arranca en el índice de 30s por defecto, así que si un test previo
    # dejó la política global en otro valor, setCurrentIndex(idx_30) sería un no-op desde
    # la perspectiva de Qt (el índice no "cambia") y jamás dispararía la señal.
    frontend._on_security_mode_changed()
    app.processEvents()
    assert nq.get_default_shutter_timeout() == 30.0

    laser = nq.SHUTTERS[1]
    nq.open_shutter(laser)
    assert nq.is_watchdog_armed(), "open_shutter() sin argumento debe armar el watchdog cuando la politica global es 30s"
    remaining = nq.get_watchdog_remaining_time()
    assert remaining is not None and 20.0 < remaining <= 30.0

    nq.close_shutter(laser)
    frontend.close()
    print("PASS: open_shutter() sin argumento respeta la politica global de 30 s.")


if __name__ == "__main__":
    app = QApplication.instance() or QApplication([])
    test_indefinite_alignment_mode()
    test_heartbeat_renewal_active_trace()
    test_watchdog_callback_and_ui_sync(app)
    test_ui_alignment_mode_selection(app)
    test_experimental_routine_respects_global_alignment_policy(app)
    test_experimental_routine_respects_global_30s_policy(app)

    print("\n==================================================================")
    print("TODAS LAS PRUEBAS DE SHUTTERS, WATCHDOG Y ALINEACION FUERON EXITOSAS!")
    print("==================================================================")
    sys.exit(0)
