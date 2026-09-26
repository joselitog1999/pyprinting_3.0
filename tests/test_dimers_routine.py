# -*- coding: utf-8 -*-
"""
test_dimers_routine.py — Fase 6 (DEC-020)
Verifica la secuencia automatizada de fabricación de dímeros de
pyspectrum/modules/routines/dimers.py: ciclo NP1→NP2 con detección de impresión por salto de
traza de fotodiodo, desplazamiento relativo (Δx,Δy), centrado confocal sub-píxel, espectroscopía
final del par acoplado, re-enfoque periódico, y resiliencia ante E-STOP.
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
from pyspectrum.modules.routines import dimers
from pyspectrum.modules.routines.dimers import DimersBackend, NODE_DONE

_app = QApplication.instance() or QApplication([])


def _wait_for_signal(signal, timeout_s: float = 10.0):
    loop = QEventLoop()
    signal.connect(loop.quit)
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    timer.start(int(timeout_s * 1000))
    loop.exec()
    timer.stop()
    signal.disconnect(loop.quit)


def _rising_photodiode_reader(baseline: float = 100.0, jump_after: int = 2, jump_to: float = 300.0):
    """Devuelve un callable que simula I_old estable y luego un salto característico de un
    evento de impresión (I_new > I_old*umbral) tras `jump_after` lecturas."""
    counter = {"n": 0}

    def _reader(*_a, **_kw):
        counter["n"] += 1
        return jump_to if counter["n"] > jump_after else baseline

    return _reader


class TestDimersGridGeneration(unittest.TestCase):
    def setUp(self):
        self.camera = get_andor_ccd(force_mock=True)
        self.spectrometer = get_shamrock(force_mock=True)
        self.backend = DimersBackend(self.camera, self.spectrometer)

    def test_generate_parametric_grid(self):
        previews = []
        self.backend.gridPreviewSignal.connect(lambda xs, ys: previews.append((xs, ys)))
        self.backend.generate_grid(2, 2, 4.0, 4.0, 1.0, 1.0, 2.0)
        self.assertEqual(len(self.backend._pending_nodes), 4)
        xs, ys = previews[-1]
        self.assertEqual(len(xs), 4)

    def test_load_grid_file_two_columns(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "dimer_grid.txt")
            np.savetxt(path, np.array([[2.0, 2.0], [8.0, 2.0]]))
            self.backend.load_grid_file(path)
        self.assertEqual(len(self.backend._pending_nodes), 2)
        self.assertEqual(self.backend._pending_nodes[1], (8.0, 2.0, None))


class TestDimersSequenceStateMachine(unittest.TestCase):
    """Verifica el ciclo completo de dos partículas (NP1 -> offset (Δx,Δy) -> NP2 -> validación
    -> espectroscopía) en SAFE_MODE=True, con mocks de centrado confocal y autofoco."""

    def setUp(self):
        self.camera = get_andor_ccd(force_mock=True, reset=True)
        self.spectrometer = get_shamrock(force_mock=True, reset=True)
        hardware_session.clear_emergency()
        if hardware_session.is_busy:
            hardware_session.release_session(hardware_session.current_owner)

        self.backend = DimersBackend(self.camera, self.spectrometer)

        self._orig_autofocus = dimers.run_z_autofocus
        self._orig_centering = dimers.run_confocal_centering
        self._orig_read_photodiode = dimers.read_photodiode_level
        self._orig_move = dimers.move_stage_to

        self.autofocus_calls = []
        self.centering_calls = []
        self.move_calls = []

        self._centering_coords = iter([(11.0, 21.0), (12.0, 22.0)])
        dimers.run_z_autofocus = lambda **kw: (self.autofocus_calls.append(kw) or True)
        dimers.run_confocal_centering = lambda **kw: (self.centering_calls.append(kw) or next(self._centering_coords))
        dimers.read_photodiode_level = _rising_photodiode_reader()

        def _spy_move(x, y, z=None, **kw):
            self.move_calls.append((x, y, z))
            return self._orig_move(x, y, z, **kw)
        dimers.move_stage_to = _spy_move

    def tearDown(self):
        dimers.run_z_autofocus = self._orig_autofocus
        dimers.run_confocal_centering = self._orig_centering
        dimers.read_photodiode_level = self._orig_read_photodiode
        dimers.move_stage_to = self._orig_move
        hardware_session.clear_emergency()
        if hardware_session.is_busy:
            hardware_session.release_session(hardware_session.current_owner)

    def test_two_particle_cycle_applies_offset_and_acquires_final_spectrum(self):
        self.backend.generate_grid(1, 1, 3.0, 0.0, 5.0, 5.0, 5.0)

        pairs_finished = []
        self.backend.pairFinishedSignal.connect(
            lambda wave, spec, x1, y1, x2, y2: pairs_finished.append((wave, spec, x1, y1, x2, y2))
        )

        config_dict = {
            "laser": "637 nm (red)", "exp_time": 0.02, "dx_nm": 120.0, "dy_nm": -40.0,
            "trace_threshold_ratio": 1.2, "trace_max_s": 5.0, "refocus_every": 1,
            "save_dir": tempfile.mkdtemp(),
        }
        self.backend.start_sequence(config_dict)
        _wait_for_signal(self.backend.sequenceFinishedSignal, timeout_s=10.0)

        self.assertEqual(self.backend.idx, 1)
        self.assertEqual(len(pairs_finished), 1)
        wave, spec, x1, y1, x2, y2 = pairs_finished[0]
        self.assertEqual(len(wave), 1004)
        self.assertEqual(len(spec), 1004)
        self.assertAlmostEqual(x1, 11.0)
        self.assertAlmostEqual(y1, 21.0)
        self.assertAlmostEqual(x2, 12.0)
        self.assertAlmostEqual(y2, 22.0)

        # Verificar que el movimiento a NP2 aplicó exactamente el offset (Δx,Δy) sobre el
        # centroide sub-píxel de NP1 (convertido de nm a µm: 120nm=0.12µm, -40nm=-0.04µm).
        move_to_np2 = self.move_calls[1]
        self.assertAlmostEqual(move_to_np2[0], 11.0 + 0.12, places=5)
        self.assertAlmostEqual(move_to_np2[1], 21.0 - 0.04, places=5)

        self.assertEqual(len(self.centering_calls), 2, "Centrado confocal: una vez tras NP1, una vez de post-validación")
        self.assertEqual(len(self.autofocus_calls), 1, "Re-enfoque cada 1 par -> se llama tras completar el par")
        self.assertFalse(hardware_session.is_busy)

    def test_refocus_every_k_pairs(self):
        self.backend.generate_grid(1, 2, 3.0, 0.0, 5.0, 5.0, 5.0)
        self._centering_coords = iter([(11.0, 21.0), (12.0, 22.0), (13.0, 23.0), (14.0, 24.0)])
        dimers.run_confocal_centering = lambda **kw: (self.centering_calls.append(kw) or next(self._centering_coords))
        dimers.read_photodiode_level = _rising_photodiode_reader(jump_after=1)

        config_dict = {
            "laser": "592 nm (yellow)", "exp_time": 0.02, "dx_nm": 100.0, "dy_nm": 0.0,
            "trace_threshold_ratio": 1.2, "trace_max_s": 5.0, "refocus_every": 2,
            "save_dir": tempfile.mkdtemp(),
        }
        self.backend.start_sequence(config_dict)
        _wait_for_signal(self.backend.sequenceFinishedSignal, timeout_s=10.0)

        self.assertEqual(self.backend.idx, 2)
        self.assertEqual(len(self.autofocus_calls), 1, "Con K=2 y 2 pares, el re-enfoque sólo debe disparar una vez")


class TestDimersEmergencyStopResilience(unittest.TestCase):
    def setUp(self):
        self.camera = get_andor_ccd(force_mock=True, reset=True)
        self.spectrometer = get_shamrock(force_mock=True, reset=True)
        hardware_session.clear_emergency()
        if hardware_session.is_busy:
            hardware_session.release_session(hardware_session.current_owner)

        self.backend = DimersBackend(self.camera, self.spectrometer)
        self._orig_autofocus = dimers.run_z_autofocus
        self._orig_centering = dimers.run_confocal_centering
        self._orig_read_photodiode = dimers.read_photodiode_level
        dimers.run_z_autofocus = lambda **kw: True
        dimers.run_confocal_centering = lambda **kw: (1.0, 2.0)

    def tearDown(self):
        dimers.run_z_autofocus = self._orig_autofocus
        dimers.run_confocal_centering = self._orig_centering
        dimers.read_photodiode_level = self._orig_read_photodiode
        hardware_session.clear_emergency()
        if hardware_session.is_busy:
            hardware_session.release_session(hardware_session.current_owner)

    def test_emergency_stop_during_print_trace_wait_closes_shutter_and_ends_without_hang(self):
        self.backend.generate_grid(1, 1, 3.0, 0.0, 5.0, 5.0, 5.0)

        # La traza nunca supera el umbral por sí sola: sólo el E-STOP puede terminarla.
        dimers.read_photodiode_level = lambda *a, **kw: 100.0

        shutter_events = []
        orig_open, orig_close = dimers.open_shutter, dimers.close_shutter
        dimers.open_shutter = lambda name, *a, **kw: (shutter_events.append(("open", name)), orig_open(name))[-1]
        dimers.close_shutter = lambda name: (shutter_events.append(("close", name)), orig_close(name))[-1]

        config_dict = {
            "laser": "808 nm (IR)", "exp_time": 0.02, "dx_nm": 100.0, "dy_nm": 0.0,
            "trace_threshold_ratio": 1.2, "trace_max_s": 30.0, "refocus_every": 1,
            "save_dir": tempfile.mkdtemp(),
        }
        QTimer.singleShot(80, hardware_session.emergency_stop)

        try:
            self.backend.start_sequence(config_dict)
            _wait_for_signal(self.backend.sequenceFinishedSignal, timeout_s=10.0)
        finally:
            dimers.open_shutter = orig_open
            dimers.close_shutter = orig_close

        self.assertFalse(self.backend._seq_running)
        self.assertIn(("close", "808 nm (IR)"), shutter_events)
        self.assertFalse(hardware_session.is_busy)
        self.assertTrue(hardware_session.is_emergency_stopped)


if __name__ == "__main__":
    unittest.main()
