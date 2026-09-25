# -*- coding: utf-8 -*-
"""
test_andor_read_modes_transition.py — Transición Segura de Modos de Lectura y Reasignación de Buffers
PySpectrum 3.0 — UNSAM Nanofotónica

Verifica que compute_buffer_shape()/transition_read_mode() (pyspectrum/ui/acquisition_setup_dialog.py)
calculen la forma exacta del buffer para cada uno de los 5 modos de lectura del Andor SDK 2
(FVB, Single-Track, Multi-Track, Random-Track, Imagen 2D), que el protocolo de transición
aborte/reconfigure el driver sin errores, y que el Pre-Amp Gain / HSSpeed / obturador interno
recién agregados al driver (mock y contrato real) se comporten correctamente.
"""
from __future__ import annotations
import os
import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

os.environ["PYPRINTING_SAFE"] = "1"
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6 import QtWidgets
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

from pyspectrum.drivers.andor_ccd_driver import (
    get_andor_ccd, DRV_SUCCESS, DRV_IDLE,
    READ_MODE_FVB, READ_MODE_SINGLE_TRACK, READ_MODE_MULTI_TRACK, READ_MODE_RANDOM_TRACK, READ_MODE_IMAGE,
    PREAMP_GAINS_MOCK, HSSPEEDS_MHZ_MOCK,
)
from pyspectrum.ui.acquisition_setup_dialog import (
    compute_buffer_shape, transition_read_mode, AcquisitionSetupDialog,
)


class TestComputeBufferShape(unittest.TestCase):

    def test_fvb_and_single_track_are_1d_width(self):
        self.assertEqual(compute_buffer_shape(READ_MODE_FVB, width=1004), (1004,))
        self.assertEqual(compute_buffer_shape(READ_MODE_SINGLE_TRACK, width=1004), (1004,))

    def test_image_is_2d_height_by_width(self):
        self.assertEqual(compute_buffer_shape(READ_MODE_IMAGE, width=1004, height=1002), (1002, 1004))

    def test_multi_track_is_ntracks_by_width(self):
        self.assertEqual(compute_buffer_shape(READ_MODE_MULTI_TRACK, width=1004, n_tracks=4), (4, 1004))

    def test_random_track_is_ntracks_by_width(self):
        self.assertEqual(compute_buffer_shape(READ_MODE_RANDOM_TRACK, width=1004, n_tracks=3), (3, 1004))


class TestTransitionReadMode(unittest.TestCase):

    def setUp(self):
        self.camera = get_andor_ccd(force_mock=True)

    def test_transition_to_each_mode_reports_correct_buffer_shape_and_no_exceptions(self):
        cases = [
            (READ_MODE_FVB, {}, (1004,)),
            (READ_MODE_SINGLE_TRACK, {"single_track_center": 500, "single_track_height": 40}, (1004,)),
            (READ_MODE_MULTI_TRACK, {"n_tracks": 3, "multi_track_height": 5}, (3, 1004)),
            (READ_MODE_RANDOM_TRACK, {"random_track_areas": [(0, 5), (100, 110)]}, (2, 1004)),
            (READ_MODE_IMAGE, {}, (1002, 1004)),
        ]
        for mode, kwargs, expected_shape in cases:
            result = transition_read_mode(self.camera, mode, width=1004, height=1002, **kwargs)
            self.assertEqual(result["applied_mode"], mode)
            self.assertEqual(result["buffer_shape"], expected_shape)
            self.assertEqual(self.camera.get_read_mode(), mode)

    def test_transition_aborts_acquisition_first(self):
        self.camera.start_acquisition()
        self.assertTrue(self.camera._acquiring)
        transition_read_mode(self.camera, READ_MODE_IMAGE)
        self.assertFalse(self.camera._acquiring)

    def test_multi_track_data_shape_matches_declared_buffer(self):
        result = transition_read_mode(self.camera, READ_MODE_MULTI_TRACK, n_tracks=4, multi_track_height=5)
        data = self.camera.get_acquired_data()
        self.assertEqual(data.shape, result["buffer_shape"])

    def test_random_track_data_shape_matches_declared_buffer(self):
        areas = [(0, 5), (50, 60), (900, 910)]
        result = transition_read_mode(self.camera, READ_MODE_RANDOM_TRACK, random_track_areas=areas)
        data = self.camera.get_acquired_data()
        self.assertEqual(data.shape, result["buffer_shape"])
        self.assertEqual(data.shape[0], len(areas))

    def test_repeated_transitions_do_not_leak_or_crash(self):
        modes = [READ_MODE_IMAGE, READ_MODE_FVB, READ_MODE_SINGLE_TRACK, READ_MODE_MULTI_TRACK,
                 READ_MODE_RANDOM_TRACK, READ_MODE_IMAGE]
        for mode in modes:
            transition_read_mode(self.camera, mode, n_tracks=2, random_track_areas=[(0, 5), (10, 15)])
            data = self.camera.get_acquired_data()
            self.assertIsNotNone(data)


class TestAcquisitionSetupDialogRun(unittest.TestCase):

    def test_run_shows_and_closes_dialog_around_transition(self):
        camera = get_andor_ccd(force_mock=True)
        dlg = AcquisitionSetupDialog(message="Configurando adquisición...")
        result = dlg.run(transition_read_mode, camera, READ_MODE_IMAGE)
        self.assertEqual(result["applied_mode"], READ_MODE_IMAGE)
        self.assertFalse(dlg.isVisible())

    def test_run_closes_dialog_even_if_fn_raises(self):
        dlg = AcquisitionSetupDialog()

        def _boom():
            raise RuntimeError("simulated failure")

        with self.assertRaises(RuntimeError):
            dlg.run(_boom)
        self.assertFalse(dlg.isVisible())


class TestAndorDriverPreAmpAndHSSpeedMock(unittest.TestCase):

    def setUp(self):
        self.camera = get_andor_ccd(force_mock=True)

    def test_number_and_values_of_preamp_gains(self):
        n = self.camera.get_number_preamp_gains()
        self.assertEqual(n, len(PREAMP_GAINS_MOCK))
        for i in range(n):
            ret, gain = self.camera.get_preamp_gain(i)
            self.assertEqual(ret, DRV_SUCCESS)
            self.assertEqual(gain, PREAMP_GAINS_MOCK[i])

    def test_set_preamp_gain_out_of_range_clamps(self):
        ret = self.camera.set_preamp_gain(999)
        self.assertEqual(ret, DRV_SUCCESS)
        self.assertEqual(self.camera.get_preamp_gain_index(), len(PREAMP_GAINS_MOCK) - 1)

    def test_number_and_values_of_hs_speeds(self):
        n = self.camera.get_number_hs_speeds()
        self.assertEqual(n, len(HSSPEEDS_MHZ_MOCK))
        for i in range(n):
            ret, speed = self.camera.get_hs_speed(i)
            self.assertEqual(ret, DRV_SUCCESS)
            self.assertEqual(speed, HSSPEEDS_MHZ_MOCK[i])

    def test_shutter_mode_roundtrip(self):
        self.assertEqual(self.camera.set_shutter_mode(1), DRV_SUCCESS)
        self.assertEqual(self.camera.get_shutter_mode(), 1)

    def test_get_status_reflects_acquiring_state(self):
        self.camera.abort_acquisition()
        self.assertEqual(self.camera.get_status(), DRV_IDLE)
        self.camera.start_acquisition()
        self.assertNotEqual(self.camera.get_status(), DRV_IDLE)


if __name__ == "__main__":
    unittest.main()
