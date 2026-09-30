# -*- coding: utf-8 -*-
"""
test_growth_kinetics_routine.py — Fase 6 (DEC-020)
Verifica la máquina de estados de grilla automatizada de pyspectrum/modules/routines/growth_kinetics.py:
generación/carga de grilla, movimiento de platina + mocks de autofoco/centrado, criterios duales
de parada (λ_max objetivo y caída de fotodiode), y resiliencia ante E-STOP.
"""
from __future__ import annotations
import os
import tempfile
import unittest

import numpy as np
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QEventLoop, QTimer

import config  # noqa: F401  (orden de import: config antes de PyQt6, ver conftest.py)

from pyspectrum.drivers.andor_ccd_driver import get_andor_ccd
from pyspectrum.drivers.shamrock_driver import get_shamrock
from pyspectrum.modules.hardware_session import hardware_session
from pyspectrum.modules.routines import growth_kinetics
from pyspectrum.modules.routines.growth_kinetics import (
    GrowthKineticsBackend, GrowthKineticsWidget, NODE_PENDING, NODE_CURRENT, NODE_DONE,
)

_app = QApplication.instance() or QApplication([])


def _wait_for_signal(signal, timeout_s: float = 10.0):
    """Bombea el bucle de eventos de Qt hasta que `signal` se emita o venza timeout_s
    (colchón de seguridad para que un hang real falle rápido en vez de bloquear pytest)."""
    loop = QEventLoop()
    signal.connect(loop.quit)
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    timer.start(int(timeout_s * 1000))
    loop.exec()
    timer.stop()
    signal.disconnect(loop.quit)


class TestGridGenerationAndLoading(unittest.TestCase):
    def setUp(self):
        self.camera = get_andor_ccd(force_mock=True)
        self.spectrometer = get_shamrock(force_mock=True)
        self.backend = GrowthKineticsBackend(self.camera, self.spectrometer)

    def test_generate_parametric_grid_rectangular(self):
        previews = []
        self.backend.gridPreviewSignal.connect(lambda xs, ys: previews.append((xs, ys)))

        self.backend.generate_grid(2, 3, 3.0, 5.0, 10.0, 20.0, 7.0)

        self.assertEqual(len(self.backend._pending_nodes), 6)
        xs, ys = previews[-1]
        self.assertEqual(len(xs), 6)
        # Nodo (0,0) coincide exactamente con el origen; nodo (1,2) con el máximo esperado.
        self.assertAlmostEqual(self.backend._pending_nodes[0][0], 10.0)
        self.assertAlmostEqual(self.backend._pending_nodes[0][1], 20.0)
        self.assertAlmostEqual(self.backend._pending_nodes[0][2], 7.0)
        self.assertAlmostEqual(self.backend._pending_nodes[-1][0], 10.0 + 2 * 3.0)
        self.assertAlmostEqual(self.backend._pending_nodes[-1][1], 20.0 + 1 * 5.0)

    def test_load_grid_file_two_columns_xy(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "grid.txt")
            np.savetxt(path, np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]]))
            self.backend.load_grid_file(path)

        self.assertEqual(len(self.backend._pending_nodes), 3)
        self.assertEqual(self.backend._pending_nodes[1], (3.0, 4.0, None))

    def test_load_grid_file_legacy_3xN_matrix_orientation(self):
        """Formato legado (Growth_ps.py::grid()): matriz 3×N en memoria (filas=X,Y,Z)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "grid_3xN.txt")
            datos = np.array([[0.0, 3.0, 6.0, 9.0], [0.0, 0.0, 0.0, 0.0], [1.0, 1.0, 1.0, 1.0]])
            np.savetxt(path, datos)
            self.backend.load_grid_file(path)

        self.assertEqual(len(self.backend._pending_nodes), 4)
        self.assertAlmostEqual(self.backend._pending_nodes[2][0], 6.0)
        self.assertAlmostEqual(self.backend._pending_nodes[2][2], 1.0)

    def test_use_current_position_as_origin_emits_stage_coordinates(self):
        received = []
        self.backend.originUpdatedSignal.connect(lambda x, y, z: received.append((x, y, z)))
        self.backend.use_current_position_as_origin()
        self.assertEqual(len(received), 1)
        x, y, z = received[0]
        self.assertGreaterEqual(x, 0.0)
        self.assertGreaterEqual(y, 0.0)


class TestGrowthGridStateMachine(unittest.TestCase):
    """Simulación de corrida completa en SAFE_MODE=True (config.SAFE_MODE ya es True por
    defecto en el entorno de tests): movimiento de platina, mocks de autofoco/centrado,
    apertura de obturador, y ambos criterios de parada automática."""

    def setUp(self):
        self.camera = get_andor_ccd(force_mock=True, reset=True)
        self.spectrometer = get_shamrock(force_mock=True, reset=True)
        hardware_session.clear_emergency()
        if hardware_session.is_busy:
            hardware_session.release_session(hardware_session.current_owner)

        self.backend = GrowthKineticsBackend(self.camera, self.spectrometer)

        self._orig_autofocus = growth_kinetics.run_z_autofocus
        self._orig_centering = growth_kinetics.run_confocal_centering
        self._orig_read_photodiode = growth_kinetics.read_photodiode_level
        self.autofocus_calls = []
        self.centering_calls = []
        growth_kinetics.run_z_autofocus = lambda **kw: (self.autofocus_calls.append(kw) or True)
        growth_kinetics.run_confocal_centering = lambda **kw: (self.centering_calls.append(kw) or (1.0, 2.0))

    def tearDown(self):
        growth_kinetics.run_z_autofocus = self._orig_autofocus
        growth_kinetics.run_confocal_centering = self._orig_centering
        growth_kinetics.read_photodiode_level = self._orig_read_photodiode
        hardware_session.clear_emergency()
        if hardware_session.is_busy:
            hardware_session.release_session(hardware_session.current_owner)

    def test_full_grid_run_stops_on_lambda_criterion(self):
        self.backend.generate_grid(1, 2, 3.0, 0.0, 5.0, 5.0, 5.0)
        shutter_events = []
        orig_open, orig_close = growth_kinetics.open_shutter, growth_kinetics.close_shutter
        growth_kinetics.open_shutter = lambda name, *a, **kw: (shutter_events.append(("open", name)), orig_open(name))[-1]
        growth_kinetics.close_shutter = lambda name: (shutter_events.append(("close", name)), orig_close(name))[-1]
        try:
            config_dict = {
                "laser": "532 nm (green)", "exp_time": 0.01, "autofocus_every": 1, "center_seed": True,
                "use_lambda_stop": True, "lambda_target_nm": 1.0,  # cualquier lmax ajustado dispara de inmediato
                "use_photodiode_stop": False, "photodiode_drop_pct": None,
                "t_max_s": 30.0, "interval_s": 0.01, "save_dir": tempfile.mkdtemp(),
                "mirror": "down",  # AND-1: lo confirma el operador
            }
            self.backend.start_grid(config_dict)
            _wait_for_signal(self.backend.gridFinishedSignal, timeout_s=10.0)
        finally:
            growth_kinetics.open_shutter = orig_open
            growth_kinetics.close_shutter = orig_close

        self.assertEqual(self.backend.idx, 2, "Debe completar ambos nodos de la grilla")
        self.assertEqual(len(self.autofocus_calls), 2, "Autofoco cada 1 nodo -> se llama en ambos nodos")
        self.assertEqual(len(self.centering_calls), 2, "Centrado de semilla activado -> se llama en ambos nodos")
        self.assertIn(("open", "532 nm (green)"), shutter_events)
        self.assertIn(("close", "532 nm (green)"), shutter_events)
        self.assertFalse(hardware_session.is_busy)

    def test_full_grid_run_stops_on_photodiode_drop_criterion(self):
        self.backend.generate_grid(1, 1, 3.0, 0.0, 5.0, 5.0, 5.0)

        readings = iter([100.0, 100.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0])
        growth_kinetics.read_photodiode_level = lambda *a, **kw: next(readings, 40.0)

        config_dict = {
            "laser": "637 nm (red)", "exp_time": 0.01, "autofocus_every": 5, "center_seed": False,
            "use_lambda_stop": False, "lambda_target_nm": None,
            "use_photodiode_stop": True, "photodiode_drop_pct": 20.0,
            "t_max_s": 30.0, "interval_s": 0.01, "save_dir": tempfile.mkdtemp(),
            "mirror": "down",  # AND-1: lo confirma el operador
        }
        self.backend.start_grid(config_dict)
        _wait_for_signal(self.backend.gridFinishedSignal, timeout_s=10.0)

        self.assertEqual(self.backend.idx, 1)
        self.assertEqual(len(self.backend._node_lmax_points), 3, "Debe detenerse en la 3ra lectura (40 <= 100*0.8)")
        self.assertFalse(hardware_session.is_busy)

    def test_full_grid_run_stops_on_tmax_safety_criterion(self):
        self.backend.generate_grid(1, 1, 3.0, 0.0, 5.0, 5.0, 5.0)
        config_dict = {
            "laser": "592 nm (yellow)", "exp_time": 0.01, "autofocus_every": 1, "center_seed": False,
            "use_lambda_stop": False, "lambda_target_nm": None,
            "use_photodiode_stop": False, "photodiode_drop_pct": None,
            "t_max_s": 0.03, "interval_s": 0.01, "save_dir": tempfile.mkdtemp(),
            "mirror": "down",  # AND-1: lo confirma el operador
        }
        self.backend.start_grid(config_dict)
        _wait_for_signal(self.backend.gridFinishedSignal, timeout_s=10.0)

        self.assertEqual(self.backend.idx, 1)
        self.assertFalse(hardware_session.is_busy)

    def test_pause_closes_the_laser_next_node_and_resume(self):
        """R4-K P7: la pausa durante el seguimiento cierra el láser y seguir lo reabre. "Siguiente nodo"
        termina el seguimiento del nodo en curso; al reanudar, la grilla completa los nodos que faltan."""
        from core import nidaq
        from PyQt6 import QtWidgets
        self.backend.generate_grid(1, 3, 3.0, 0.0, 5.0, 5.0, 5.0)
        config_dict = {
            "laser": "532 nm (green)", "exp_time": 0.01, "autofocus_every": 10, "center_seed": False,
            "use_lambda_stop": False, "lambda_target_nm": None,
            "use_photodiode_stop": False, "photodiode_drop_pct": None,
            "t_max_s": 30.0, "interval_s": 0.02, "save_dir": tempfile.mkdtemp(),
            "mirror": "down",
        }
        self.backend.start_grid(config_dict)
        import time as _t

        def pump(cond, timeout=10.0):
            t_end = _t.monotonic() + timeout
            while not cond() and _t.monotonic() < t_end:
                QtWidgets.QApplication.processEvents()
                _t.sleep(0.01)
            return cond()

        self.assertTrue(pump(lambda: len(self.backend._node_t_points) >= 2))    # ya está siguiendo el nodo 0
        self.backend.pause_grid()
        self.assertTrue(pump(lambda: "532 nm (green)" not in nidaq.get_open_shutter_names()))
        _t.sleep(0.2)
        self.assertEqual(self.backend.idx, 0)
        self.assertNotIn("532 nm (green)", nidaq.get_open_shutter_names())    # en pausa, láser cerrado

        self.backend.next_node_grid()
        self.backend.resume_grid()
        self.assertTrue(pump(lambda: self.backend.idx >= 1))
        self.assertEqual(self.backend.states[0], NODE_DONE)
        self.backend.next_node_grid()
        self.assertTrue(pump(lambda: self.backend.idx >= 2))
        self.backend.next_node_grid()
        _wait_for_signal(self.backend.gridFinishedSignal, timeout_s=15.0)
        self.assertEqual(self.backend.idx, 3)
        self.assertFalse(hardware_session.is_busy)


class TestGrowthGridEmergencyStopResilience(unittest.TestCase):
    def setUp(self):
        self.camera = get_andor_ccd(force_mock=True, reset=True)
        self.spectrometer = get_shamrock(force_mock=True, reset=True)
        hardware_session.clear_emergency()
        if hardware_session.is_busy:
            hardware_session.release_session(hardware_session.current_owner)

        self.backend = GrowthKineticsBackend(self.camera, self.spectrometer)
        self._orig_autofocus = growth_kinetics.run_z_autofocus
        self._orig_centering = growth_kinetics.run_confocal_centering
        growth_kinetics.run_z_autofocus = lambda **kw: True
        growth_kinetics.run_confocal_centering = lambda **kw: (1.0, 2.0)

    def tearDown(self):
        growth_kinetics.run_z_autofocus = self._orig_autofocus
        growth_kinetics.run_confocal_centering = self._orig_centering
        hardware_session.clear_emergency()
        if hardware_session.is_busy:
            hardware_session.release_session(hardware_session.current_owner)

    def test_emergency_stop_during_spectral_tracking_closes_shutter_and_ends_without_hang(self):
        self.backend.generate_grid(1, 1, 3.0, 0.0, 5.0, 5.0, 5.0)

        shutter_events = []
        orig_open, orig_close = growth_kinetics.open_shutter, growth_kinetics.close_shutter
        growth_kinetics.open_shutter = lambda name, *a, **kw: (shutter_events.append(("open", name)), orig_open(name))[-1]
        growth_kinetics.close_shutter = lambda name: (shutter_events.append(("close", name)), orig_close(name))[-1]

        config_dict = {
            "laser": "808 nm (IR)", "exp_time": 0.01, "autofocus_every": 1, "center_seed": False,
            "use_lambda_stop": False, "lambda_target_nm": None,
            "use_photodiode_stop": False, "photodiode_drop_pct": None,
            "t_max_s": 30.0, "interval_s": 0.01, "save_dir": tempfile.mkdtemp(),
            "mirror": "down",  # AND-1: lo confirma el operador
        }
        # Dispara el E-STOP a mitad de camino de la fase de tracking espectral (varios ticks de 10ms después).
        # Con potencia, espejo y láser (≈ 1.8 s de asentamientos, R4-K) el seguimiento empieza después.
        QTimer.singleShot(2500, hardware_session.emergency_stop)

        try:
            self.backend.start_grid(config_dict)
            _wait_for_signal(self.backend.gridFinishedSignal, timeout_s=10.0)
        finally:
            growth_kinetics.open_shutter = orig_open
            growth_kinetics.close_shutter = orig_close

        self.assertFalse(self.backend._grid_running)
        self.assertIn(("close", "808 nm (IR)"), shutter_events)
        self.assertFalse(hardware_session.is_busy)
        self.assertTrue(hardware_session.is_emergency_stopped)


if __name__ == "__main__":
    unittest.main()
