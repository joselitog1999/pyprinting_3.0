# -*- coding: utf-8 -*-
"""
test_pi_stage_resilience.py — Estabilidad de conexión de la platina PI E-517 y
pre-flight range checks de grillas de impresión
PyPrinting 3.0 — UNSAM Nanofotónica

Verifica:
  1. config.py::_MockPI.MOV()/_PIController.MOV() recortan siempre cada eje a su recorrido
     físico (X e Y 100 µm, Z 20 µm) antes de enviar el comando.
  2. _PIController distingue un rechazo del firmware (GCSError con código positivo: la conexión
     sigue viva) de una falla de comunicación (cualquier otra excepción, o GCSError con código
     negativo o no numérico).
  3. DEC-036: ante una falla de comunicación la platina se declara desconectada, se cierran los
     obturadores y se activa el interlock "Platina PI". No hay reconexión automática: una
     reconexión manda la platina a home a mitad de la rutina.
  4. qONT() nunca inventa un on-target: ante cualquier falla informa False.
  5. connect() cierra los obturadores antes del home y es la acción que libera el interlock.
  6. config.wait_on_target() confirma la llegada con tope de tiempo y nunca sigue como si la
     platina hubiera llegado.
  7. modules/measurements.py::Backend: pre-flight de rango, pausa ante pérdida de comunicación
     (sin perder i_global) y pausa cuando la platina no confirma la llegada a un nodo.
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
import config as config_mod
from config import (pi, PI_STAGE_RANGE_UM, PI_Z_RANGE_UM, GCSError, _PIController,
                    STAGE_INTERLOCK, _is_stage_comm_error, wait_on_target)
from core import nidaq
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
        self.on_target = True
        self.idn_calls = 0
        self.log = None  # lista compartida para verificar el orden de las llamadas

    def MOV(self, axes, targets):
        if self.log is not None:
            self.log.append("MOV")
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
        return {1: self.on_target, 2: self.on_target, 3: self.on_target}

    def qIDN(self):
        self.idn_calls += 1
        return "PI E-517 [FAKE]"

    # Lo que usa connect()
    def EnumerateUSB(self):
        return ["PI E-517 SN FAKE"]

    def ConnectUSB(self, target):
        if self.log is not None:
            self.log.append("ConnectUSB")

    def SVO(self, *a, **k): pass
    def VCO(self, *a, **k): pass

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


class _StageInterlockGuard(unittest.TestCase):
    """Un interlock "Platina PI" que se filtrara bloquearía los obturadores de los tests que
    siguen: se libera siempre, pase lo que pase en el test."""

    def setUp(self):
        nidaq.clear_shutter_interlock(STAGE_INTERLOCK)

    def tearDown(self):
        nidaq.clear_shutter_interlock(STAGE_INTERLOCK)

    def assertInterlock(self, active: bool):
        self.assertEqual(STAGE_INTERLOCK in nidaq.get_shutter_interlocks(), active)


class TestStageErrorClassification(unittest.TestCase):
    """Qué excepción es una falla de comunicación y cuál un rechazo del firmware."""

    def test_positive_gcs_code_is_firmware(self):
        self.assertFalse(_is_stage_comm_error(GCSError(7)))    # position out of limits

    def test_negative_gcs_code_is_communication(self):
        self.assertTrue(_is_stage_comm_error(GCSError(-7)))    # COM_TIMEOUT
        self.assertTrue(_is_stage_comm_error(GCSError(-1004)))  # PI_UNEXPECTED_RESPONSE

    def test_unparseable_gcs_code_is_communication(self):
        # pipython acepta GCSError("x"); sin código no se puede clasificar -> lado seguro.
        self.assertTrue(_is_stage_comm_error(GCSError("sin código")))

    def test_non_gcs_exception_is_communication(self):
        self.assertTrue(_is_stage_comm_error(OSError("USB desconectado")))


class TestPIControllerResilience(_StageInterlockGuard):
    """Ejercita _PIController con un GCSDevice falso inyectado: nada toca el bus real."""

    def test_mov_clamps_before_reaching_device(self):
        ctrl, fake_dev = _make_connected_controller()
        self.assertTrue(ctrl.MOV(1, 150.0))
        _, targets = fake_dev.mov_calls[0]
        self.assertEqual(targets[0], PI_STAGE_RANGE_UM, "El dispositivo nunca debe recibir un valor fuera de rango.")
        self.assertTrue(ctrl.connected)

    def test_mov_clamps_z_to_its_own_travel(self):
        ctrl, fake_dev = _make_connected_controller()
        ctrl.MOV([1, 3], [50.0, 50.0])
        _, targets = fake_dev.mov_calls[0]
        self.assertEqual(targets, [50.0, PI_Z_RANGE_UM], "Z tiene 20 µm de recorrido, no 100 µm")

    def test_mov_firmware_rejection_keeps_connection(self):
        ctrl, fake_dev = _make_connected_controller()
        fake_dev.mov_exception = GCSError(7)
        fake_dev.mov_exception_count = 99
        self.assertFalse(ctrl.MOV(1, 50.0), "Un comando rechazado no se ejecutó")
        self.assertTrue(ctrl.connected, "Un rechazo del firmware NUNCA debe desconectar la platina.")
        self.assertInterlock(False)

    def test_mov_communication_failure_trips_interlock_without_reconnecting(self):
        ctrl, fake_dev = _make_connected_controller()
        ctrl._pos[1] = 12.0
        fake_dev.mov_exception = OSError("USB desconectado")
        fake_dev.mov_exception_count = 99
        reconnects = []
        ctrl.connect = lambda *a, **k: reconnects.append(1) or True
        self.assertFalse(ctrl.MOV(1, 50.0))
        self.assertFalse(ctrl.connected)
        self.assertInterlock(True)
        self.assertEqual(reconnects, [], "DEC-036: sin reconexión automática")
        self.assertEqual(len(fake_dev.mov_calls), 1, "Ningún MOV extra (home) tras la falla")
        self.assertEqual(ctrl._pos[1], 12.0, "La posición en caché sólo cambia tras un MOV exitoso")

    def test_negative_gcs_code_in_mov_is_a_communication_failure(self):
        ctrl, fake_dev = _make_connected_controller()
        fake_dev.mov_exception = GCSError(-7)
        fake_dev.mov_exception_count = 99
        self.assertFalse(ctrl.MOV(1, 50.0))
        self.assertFalse(ctrl.connected)
        self.assertInterlock(True)

    def test_interlock_blocks_shutters_until_reconnect(self):
        ctrl, fake_dev = _make_connected_controller()
        fake_dev.mov_exception = OSError("USB desconectado")
        fake_dev.mov_exception_count = 1
        ctrl.MOV(1, 50.0)
        self.assertFalse(nidaq.open_shutter(nidaq.SHUTTERS[1], timeout_s=None),
                         "Con la platina en falla no se puede abrir ningún obturador")
        self.assertTrue(ctrl.connect())
        self.assertInterlock(False)
        nidaq.close_all_shutters()

    def test_qpos_firmware_rejection_keeps_connection(self):
        ctrl, fake_dev = _make_connected_controller()
        fake_dev.qpos_exception = GCSError(7)
        fake_dev.qpos_exception_count = 99
        result = ctrl.qPOS()
        self.assertTrue(ctrl.connected)
        self.assertIn("1", result)
        self.assertInterlock(False)

    def test_qpos_retries_on_transient_failure_then_succeeds(self):
        ctrl, fake_dev = _make_connected_controller()
        fake_dev.qpos_exception = OSError("bus busy")
        fake_dev.qpos_exception_count = 2  # falla 2 veces, la 3ra (2do reintento) funciona
        result = ctrl.qPOS()
        self.assertEqual(fake_dev.qpos_call_count, 3)
        self.assertTrue(ctrl.connected)
        self.assertEqual(result["1"], 50.0)
        self.assertInterlock(False)

    def test_qpos_persistent_failure_is_a_stage_fault(self):
        ctrl, fake_dev = _make_connected_controller()
        ctrl._pos[1] = 42.0
        fake_dev.qpos_exception = OSError("bus caído")
        fake_dev.qpos_exception_count = 99
        result = ctrl.qPOS()
        self.assertEqual(fake_dev.qpos_call_count, 3, "Reintenta 2 veces (3 intentos) antes de declarar la falla")
        self.assertFalse(ctrl.connected)
        self.assertInterlock(True)
        self.assertEqual(result["1"], 42.0, "Devuelve la última posición conocida")

    def test_qont_reports_real_state(self):
        ctrl, fake_dev = _make_connected_controller()
        fake_dev.on_target = False
        self.assertFalse(any(ctrl.qONT([1, 2]).values()))
        fake_dev.on_target = True
        self.assertTrue(all(ctrl.qONT([1, 2]).values()))

    def test_qont_firmware_rejection_never_reports_on_target(self):
        ctrl, fake_dev = _make_connected_controller()
        fake_dev.qont_exception = GCSError(7)
        fake_dev.qont_exception_count = 99
        result = ctrl.qONT([1, 2])
        self.assertTrue(ctrl.connected)
        self.assertEqual(result, {1: False, 2: False}, "Nunca se asume que la platina llegó")
        self.assertInterlock(False)

    def test_qont_persistent_failure_is_a_stage_fault(self):
        ctrl, fake_dev = _make_connected_controller()
        fake_dev.qont_exception = OSError("bus caído")
        fake_dev.qont_exception_count = 99
        result = ctrl.qONT([1, 2])
        self.assertEqual(result, {1: False, 2: False})
        self.assertFalse(ctrl.connected)
        self.assertInterlock(True)

    def test_disconnected_stage_rejects_moves_without_tripping(self):
        """Una sesión sin platina (nunca conectada) no es una falla: MOV se rechaza, no hay modo
        virtual silencioso y tampoco interlock."""
        ctrl = _PIController()
        ctrl._dev = _FakeGCSDevice()
        self.assertFalse(ctrl.MOV(1, 30.0))
        self.assertEqual(ctrl._dev.mov_calls, [])
        self.assertFalse(any(ctrl.qONT([1]).values()))
        self.assertInterlock(False)

    def test_isolated_stage_moves_virtually(self):
        ctrl, fake_dev = _make_connected_controller()
        ctrl.set_isolated(True)
        self.assertTrue(ctrl.MOV(1, 30.0))
        self.assertEqual(fake_dev.mov_calls, [], "Aislada no debe tocar el bus")
        self.assertEqual(ctrl._pos[1], 30.0)
        self.assertTrue(all(ctrl.qONT([1]).values()))

    def test_qidn_does_not_query_the_bus(self):
        ctrl, fake_dev = _make_connected_controller()
        ctrl._idn = "PI E-517 CACHE"
        self.assertEqual(ctrl.qIDN(), "PI E-517 CACHE")
        self.assertEqual(fake_dev.idn_calls, 0)

    def test_is_physically_connected_does_not_query_idn(self):
        """DEC-011: is_physically_connected() no debe enviar *IDN? por el bus (saturación
        durante movimiento activo) -- debe usar IsConnected() del lado del host."""
        ctrl, fake_dev = _make_connected_controller()
        self.assertTrue(ctrl.is_physically_connected())
        self.assertEqual(fake_dev.idn_calls, 0)

    def test_is_physically_connected_failure_is_a_stage_fault(self):
        ctrl, fake_dev = _make_connected_controller()

        def _boom():
            raise OSError("driver USB caído")
        fake_dev.IsConnected = _boom
        self.assertFalse(ctrl.is_physically_connected())
        self.assertFalse(ctrl.connected)
        self.assertInterlock(True)

    def test_connect_closes_shutters_before_homing(self):
        log = []
        fake_dev = _FakeGCSDevice()
        fake_dev.log = log
        ctrl = _PIController()
        ctrl._dev = fake_dev
        real_close = config_mod._close_shutters_for_stage
        config_mod._close_shutters_for_stage = lambda reason, trip: log.append("cerrar")
        nidaq.set_shutter_interlock(STAGE_INTERLOCK, "falla anterior")
        try:
            self.assertTrue(ctrl.connect())
        finally:
            config_mod._close_shutters_for_stage = real_close
        self.assertIn("MOV", log)
        self.assertLess(log.index("cerrar"), log.index("MOV"), "Obturadores cerrados ANTES del home")
        self.assertEqual(ctrl._idn, "PI E-517 [FAKE]")
        self.assertInterlock(False)


class _StubStage:
    is_mock = False

    def __init__(self, states=None, connected=True, isolated=False, raises=None):
        self.states = list(states or [])
        self.connected = connected
        self._isolated = isolated
        self.raises = raises
        self.calls = 0

    def qONT(self, axes):
        self.calls += 1
        if self.raises is not None:
            raise self.raises
        value = self.states.pop(0) if self.states else False
        return {a: value for a in (axes if isinstance(axes, list) else [axes])}


class TestWaitOnTarget(unittest.TestCase):

    def test_returns_true_only_on_confirmation(self):
        st = _StubStage(states=[False, False, True])
        ticks = []
        self.assertTrue(wait_on_target([1, 2], timeout_s=2.0, poll_s=0.0,
                                       on_tick=lambda: ticks.append(1), stage=st))
        self.assertEqual(st.calls, 3)
        self.assertEqual(len(ticks), 2, "on_tick (heartbeat) en cada vuelta de espera")

    def test_timeout_returns_false(self):
        st = _StubStage(states=[])
        self.assertFalse(wait_on_target([1], timeout_s=0.05, poll_s=0.005, stage=st))
        self.assertGreater(st.calls, 1)

    def test_disconnected_stage_returns_false_without_polling(self):
        st = _StubStage(states=[True], connected=False)
        self.assertFalse(wait_on_target([1], timeout_s=1.0, stage=st))
        self.assertEqual(st.calls, 0)

    def test_isolated_stage_is_polled(self):
        st = _StubStage(states=[True], connected=False, isolated=True)
        self.assertTrue(wait_on_target([1], timeout_s=1.0, stage=st))

    def test_read_failure_returns_false(self):
        st = _StubStage(raises=OSError("bus"))
        self.assertFalse(wait_on_target([1], timeout_s=1.0, stage=st))

    def test_mock_stage_is_accepted_in_safe_mode(self):
        self.assertTrue(wait_on_target([1, 2], timeout_s=1.0))


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


class TestGridMoveRequiresArrival(unittest.TestCase):
    """DEC-036: en producción _grid_move espera la confirmación on-target; sin ella pausa con
    los obturadores cerrados en vez de seguir al siguiente paso de la rutina."""

    def setUp(self):
        pi.connect()
        self.backend = measurements.Backend(mode="printing")
        self.msgs, self.finished = [], []
        self.backend.stageDisconnectedSignal.connect(self.msgs.append)
        self.backend.grid_move_finishSignal.connect(lambda: self.finished.append(1))
        self.backend.grid_x = np.array([0.0, 5.0])
        self.backend.grid_y = np.array([0.0, 0.0])
        self.backend.startX = 50.0
        self.backend.startY = 50.0
        self.backend.i_global = 1
        self.backend.mode_printing = "printing"
        self._saved = (measurements.SAFE_MODE, measurements.wait_on_target)
        measurements.SAFE_MODE = False

    def tearDown(self):
        measurements.SAFE_MODE, measurements.wait_on_target = self._saved

    def test_no_confirmation_pauses_and_does_not_advance(self):
        measurements.wait_on_target = lambda *a, **k: False
        self.backend._grid_move()
        self.assertTrue(self.backend.is_paused)
        self.assertEqual(self.backend.mode_printing, "none")
        self.assertEqual(self.backend.i_global, 1)
        self.assertEqual(self.finished, [], "Sin llegada confirmada no se avanza de etapa")
        self.assertEqual(len(self.msgs), 1)
        self.assertIn("no confirmó", self.msgs[0])

    def test_confirmation_advances(self):
        measurements.wait_on_target = lambda *a, **k: True
        self.backend._grid_move()
        self.assertFalse(getattr(self.backend, "is_paused", False))
        self.assertEqual(self.finished, [1])
        self.assertEqual(self.msgs, [])

if __name__ == "__main__":
    unittest.main()
