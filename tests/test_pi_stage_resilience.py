# -*- coding: utf-8 -*-
"""
test_pi_stage_resilience.py — Estabilidad de conexión de la platina PI E-517 y
pre-flight range checks de grillas de impresión
PyPrinting 3.0 — UNSAM Nanofotónica

Verifica:
  1. config.py::_MockPI.MOV()/_PIController.MOV() clampean siempre al rango físico
     [0, PI_STAGE_RANGE_UM] antes de enviar el comando, sin excepción ni desconexión.
  2. _PIController aísla GCSError (rechazo de firmware) de una desconexión física real:
     MOV()/qPOS()/qONT() nunca apagan self._connected ante un GCSError.
  3. qPOS()/qONT() reintentan ante fallos transitorios y degradan sin desconectar.
  4. Solo un fallo de comunicación de bajo nivel genuino en MOV() (no-GCSError), tras un
     intento fallido de reconexión automática, desconecta realmente.
  5. modules/measurements.py::Backend pre-flight range check aborta una grilla fuera de
     rango antes de mover la platina o abrir obturadores.
  6. modules/measurements.py::Backend pausa el experimento (sin perder i_global) ante una
     pérdida real de comunicación física, y resume_after_reconnect() lo retoma.
"""
from __future__ import annotations
import os
import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ["PYPRINTING_SAFE"] = "1"
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import config  # noqa: F401 — antes que PyQt6, ver DEC-010/DEC-011
from PyQt6 import QtWidgets
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

import numpy as np
from config import pi, PI_STAGE_RANGE_UM, GCSError, _PIController
import modules.measurements as measurements


class _FakeGCSDevice:
    """Doble de prueba de pipython.GCSDevice: cada método puede configurarse para
    devolver un valor fijo o lanzar una excepción una cantidad controlada de veces,
    registrando cada llamada para verificar clampeo/reintentos."""

    def __init__(self):
        self.mov_calls: list = []
        self.mov_exception = None
        self.mov_exception_count = 0
        self.qpos_exception = None
        self.qpos_exception_count = 0
        self.qont_exception = None
        self.qont_exception_count = 0
        self.qpos_call_count = 0
        self.qont_call_count = 0
        self._pos = {"1": 50.0, "2": 50.0, "3": 10.0}

    def MOV(self, axes, targets):
        self.mov_calls.append((list(axes) if not isinstance(axes, int) else [axes],
                                list(targets) if not isinstance(targets, (int, float)) else [targets]))
        if self.mov_exception is not None and self.mov_exception_count > 0:
            self.mov_exception_count -= 1
            raise self.mov_exception

    def qPOS(self, axes=None):
        self.qpos_call_count += 1
        if self.qpos_exception is not None and self.qpos_exception_count > 0:
            self.qpos_exception_count -= 1
            raise self.qpos_exception
        return dict(self._pos)

    def qONT(self, axes=None):
        self.qont_call_count += 1
        if self.qont_exception is not None and self.qont_exception_count > 0:
            self.qont_exception_count -= 1
            raise self.qont_exception
        return {1: True, 2: True, 3: True}

    def qIDN(self):
        return "PI E-517 [FAKE]"

    def IsConnected(self):
        return True

    def CloseConnection(self):
        pass


def _make_connected_controller() -> tuple[_PIController, _FakeGCSDevice]:
    """Instancia un _PIController real (pipython no está instalado en este entorno, así
    que __init__ deja self._dev=None) y le inyecta un GCSDevice falso ya 'conectado', sin
    pasar por connect() (que requiere EnumerateUSB/ConnectUSB reales)."""
    ctrl = _PIController()
    fake_dev = _FakeGCSDevice()
    ctrl._dev = fake_dev
    ctrl._connected = True
    return ctrl, fake_dev


class TestMockPIClamping(unittest.TestCase):
    """El singleton `pi` real usado en toda la suite (SAFE_MODE=True) es _MockPI."""

    def setUp(self):
        pi.connect()

    def test_mov_clamps_below_range(self):
        pi.MOV(1, -10.0)
        self.assertEqual(pi.qPOS()["1"], 0.0)
        self.assertTrue(pi.connected, "El clampeo no debe afectar la conexión.")

    def test_mov_clamps_above_range(self):
        pi.MOV(1, 150.0)
        self.assertEqual(pi.qPOS()["1"], PI_STAGE_RANGE_UM)
        self.assertTrue(pi.connected)

    def test_mov_in_range_unaffected(self):
        pi.MOV([1, 2, 3], [25.0, 75.0, 10.0])
        pos = pi.qPOS()
        self.assertAlmostEqual(pos["1"], 25.0)
        self.assertAlmostEqual(pos["2"], 75.0)
        self.assertAlmostEqual(pos["3"], 10.0)


class TestPIControllerResilience(unittest.TestCase):
    """Ejercita _PIController directamente con un GCSDevice falso inyectado, ya que
    pipython no está instalado en este entorno de pruebas (self._dev sería None)."""

    def test_mov_clamps_before_reaching_device(self):
        ctrl, fake_dev = _make_connected_controller()
        ctrl.MOV(1, 150.0)
        self.assertEqual(len(fake_dev.mov_calls), 1)
        _, targets = fake_dev.mov_calls[0]
        self.assertEqual(targets[0], PI_STAGE_RANGE_UM, "El dispositivo real nunca debe recibir un valor fuera de rango.")
        self.assertTrue(ctrl.connected)

    def test_mov_gcserror_does_not_disconnect(self):
        ctrl, fake_dev = _make_connected_controller()
        fake_dev.mov_exception = GCSError("simulated -1004 Position out of limits")
        fake_dev.mov_exception_count = 99
        ctrl.MOV(1, 50.0)
        self.assertTrue(ctrl.connected, "Un GCSError (rechazo de firmware) NUNCA debe desconectar la platina.")

    def test_qpos_gcserror_does_not_disconnect(self):
        ctrl, fake_dev = _make_connected_controller()
        fake_dev.qpos_exception = GCSError("simulated firmware rejection")
        fake_dev.qpos_exception_count = 99
        result = ctrl.qPOS()
        self.assertTrue(ctrl.connected)
        self.assertIn("1", result)

    def test_qont_gcserror_does_not_disconnect(self):
        ctrl, fake_dev = _make_connected_controller()
        fake_dev.qont_exception = GCSError("simulated firmware rejection")
        fake_dev.qont_exception_count = 99
        result = ctrl.qONT()
        self.assertTrue(ctrl.connected)
        self.assertTrue(all(result.values()))

    def test_qpos_retries_on_transient_failure_then_succeeds(self):
        ctrl, fake_dev = _make_connected_controller()
        fake_dev.qpos_exception = OSError("bus busy")
        fake_dev.qpos_exception_count = 2  # falla 2 veces, la 3ra (2do reintento) funciona
        result = ctrl.qPOS()
        self.assertEqual(fake_dev.qpos_call_count, 3)
        self.assertTrue(ctrl.connected)
        self.assertEqual(result["1"], 50.0)

    def test_qpos_falls_back_to_cached_position_without_disconnecting(self):
        ctrl, fake_dev = _make_connected_controller()
        ctrl._pos[1] = 42.0
        fake_dev.qpos_exception = OSError("bus busy, persistente")
        fake_dev.qpos_exception_count = 99
        result = ctrl.qPOS()
        self.assertEqual(fake_dev.qpos_call_count, 3, "Debe reintentar 2 veces (3 intentos totales) antes de degradar.")
        self.assertTrue(ctrl.connected, "qPOS jamás debe desconectar, incluso tras agotar reintentos.")
        self.assertEqual(result["1"], 42.0, "Debe devolver la última posición conocida en memoria.")

    def test_qont_falls_back_without_disconnecting(self):
        ctrl, fake_dev = _make_connected_controller()
        fake_dev.qont_exception = OSError("bus busy, persistente")
        fake_dev.qont_exception_count = 99
        result = ctrl.qONT([1, 2])
        self.assertTrue(ctrl.connected)
        self.assertTrue(all(result.values()))

    def test_mov_generic_communication_error_disconnects_after_failed_reconnect(self):
        ctrl, fake_dev = _make_connected_controller()
        fake_dev.mov_exception = OSError("USB desconectado")
        fake_dev.mov_exception_count = 99
        ctrl.try_auto_reconnect = lambda: False  # simula reconexión fallida
        ctrl.MOV(1, 50.0)
        self.assertFalse(ctrl.connected, "Un fallo de comunicación real (no-GCSError) tras reconexión fallida SÍ debe desconectar.")

    def test_mov_generic_error_recovers_via_auto_reconnect(self):
        ctrl, fake_dev = _make_connected_controller()
        fake_dev.mov_exception = OSError("glitch transitorio de bus")
        fake_dev.mov_exception_count = 1  # solo falla la primera vez
        ctrl.try_auto_reconnect = lambda: True  # simula reconexión exitosa
        ctrl.MOV(1, 50.0)
        self.assertTrue(ctrl.connected, "Tras una reconexión automática exitosa, la platina debe seguir conectada.")

    def test_is_physically_connected_does_not_query_idn(self):
        """DEC-011: is_physically_connected() no debe enviar *IDN? por el bus (saturación
        durante movimiento activo) -- debe usar IsConnected() del lado del host."""
        ctrl, fake_dev = _make_connected_controller()
        idn_calls = []
        fake_dev.qIDN = lambda: (idn_calls.append(1) or "PI E-517 [FAKE]")
        self.assertTrue(ctrl.is_physically_connected())
        self.assertEqual(len(idn_calls), 0, "is_physically_connected() no debe llamar qIDN() cuando IsConnected() está disponible.")


class TestGridPreflightRangeCheck(unittest.TestCase):
    def setUp(self):
        pi.connect()
        self.backend = measurements.Backend(mode="printing")
        self.errors: list = []
        self.backend.gridRangeErrorSignal.connect(lambda msg: self.errors.append(msg))

    def test_out_of_range_grid_blocked_before_any_movement(self):
        self.backend.xref = 2.0
        self.backend.yref = 50.0
        self.backend.grid_x = np.array([-5.0, 0.0, 5.0])  # startX=2 + min(-5) - margen(3) < 0
        self.backend.grid_y = np.array([0.0, 0.0, 0.0])
        self.backend.particulas = 3
        self.backend.mode_printing = "none"

        self.backend._grid_start()

        self.assertEqual(len(self.errors), 1, "Debe emitirse exactamente una advertencia de rango.")
        self.assertIn("excede el rango", self.errors[0])
        self.assertEqual(self.backend.mode_printing, "none", "La grilla NO debe haber arrancado.")

    def test_in_range_grid_proceeds_normally(self):
        self.backend.xref = 50.0
        self.backend.yref = 50.0
        self.backend.grid_x = np.array([-5.0, 0.0, 5.0])
        self.backend.grid_y = np.array([-5.0, 0.0, 5.0])
        self.backend.particulas = 3
        self.backend.mode_printing = "none"

        self.backend._grid_start()

        self.assertEqual(len(self.errors), 0, "Una grilla dentro de rango no debe generar advertencias.")
        self.assertEqual(self.backend.mode_printing, "printing", "La grilla SÍ debe haber arrancado.")

    def test_range_check_uses_drift_margin(self):
        """Un nodo justo en el borde físico (sin margen) debe bloquearse por el margen de
        deriva térmica de 3 µm, aunque el nodo nominal esté dentro de [0,100]."""
        self.backend.xref = 1.5  # startX=1.5 + min(grid_x)=0 - margen(3) = -1.5 < 0
        self.backend.yref = 50.0
        self.backend.grid_x = np.array([0.0, 10.0])
        self.backend.grid_y = np.array([0.0, 0.0])
        self.backend.particulas = 2
        self.backend.mode_printing = "none"

        self.backend._grid_start()

        self.assertEqual(len(self.errors), 1)
        self.assertEqual(self.backend.mode_printing, "none")


class TestStageDisconnectPauseResume(unittest.TestCase):
    def setUp(self):
        pi.connect()
        self.backend = measurements.Backend(mode="printing")
        self.disconnect_msgs: list = []
        self.backend.stageDisconnectedSignal.connect(lambda msg: self.disconnect_msgs.append(msg))
        self.backend.grid_x = np.array([0.0, 5.0, 10.0])
        self.backend.grid_y = np.array([0.0, 0.0, 0.0])
        self.backend.startX = 50.0
        self.backend.startY = 50.0
        self.backend.i_global = 1
        self.backend.mode_printing = "printing"

    def tearDown(self):
        pi.connect()  # restaura la conexión global para no contaminar otros tests

    def test_disconnected_stage_pauses_experiment_and_preserves_index(self):
        pi.disconnect()
        self.backend._grid_move()

        self.assertTrue(self.backend.is_paused, "El experimento debe pausarse, no abortarse.")
        self.assertEqual(self.backend.mode_printing, "none")
        self.assertEqual(self.backend.i_global, 1, "El índice de partícula pendiente no debe perderse.")
        self.assertEqual(len(self.disconnect_msgs), 1)
        self.assertIn("particula 1", self.disconnect_msgs[0].replace("í", "i"))

    def test_resume_after_reconnect_continues_from_pending_node(self):
        pi.disconnect()
        self.backend._grid_move()
        self.assertTrue(self.backend.is_paused)

        self.backend.resume_after_reconnect()

        self.assertFalse(self.backend.is_paused)
        self.assertEqual(self.backend.mode_printing, "printing")
        self.assertTrue(pi.connected)
        # _grid_move() se re-ejecutó y sí llegó a mover la platina esta vez (ya reconectada)
        self.assertAlmostEqual(float(pi.qPOS()["1"]), 55.0)  # grid_x[1]=5 + startX=50


if __name__ == "__main__":
    unittest.main()
