# -*- coding: utf-8 -*-
"""
test_zero_order_safety.py — Interlock de Seguridad del Movimiento a Orden Cero (0 nm)
PySpectrum 3.0 — UNSAM Nanofotónica

Verifica las 4 ramas de acción + cancelar de ZeroOrderSafetyDialog, disparadas directamente
sobre sus handlers (sin .exec() modal, siguiendo el patrón ya establecido en este proyecto
para evitar diálogos bloqueantes bajo QT_QPA_PLATFORM=offscreen).
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

from config import SHUTTERS
from core.nidaq import open_shutter, close_all_shutters, get_open_shutter_names
from pyspectrum.drivers.andor_ccd_driver import get_andor_ccd
from pyspectrum.drivers.shamrock_driver import get_shamrock
from pyspectrum.ui.zero_order_dialog import ZeroOrderSafetyDialog


class TestZeroOrderSafetyDialog(unittest.TestCase):

    def setUp(self):
        self.camera = get_andor_ccd(force_mock=True)
        self.spectrometer = get_shamrock(force_mock=True)
        close_all_shutters()
        self.camera.set_emccd_gain(0)
        self.laser_name = SHUTTERS[0]

    def tearDown(self):
        close_all_shutters()
        self.camera.set_emccd_gain(0)

    def test_risk_state_reflects_open_shutter_and_gain(self):
        self.camera.set_emccd_gain(80)
        open_shutter(self.laser_name)
        dlg = ZeroOrderSafetyDialog(self.camera, self.spectrometer)
        self.assertEqual(dlg.em_gain, 80)
        self.assertIn(self.laser_name, dlg.open_shutters)

    def test_safe_default_closes_laser_and_zeroes_gain(self):
        self.camera.set_emccd_gain(80)
        open_shutter(self.laser_name)
        dlg = ZeroOrderSafetyDialog(self.camera, self.spectrometer)
        dlg._on_safe_default()
        self.assertEqual(self.camera.get_emccd_gain(), 0)
        self.assertEqual(get_open_shutter_names(), [])
        self.assertEqual(dlg.chosen_action, ZeroOrderSafetyDialog.ACTION_SAFE_DEFAULT)
        self.assertTrue(dlg.result() == QtWidgets.QDialog.DialogCode.Accepted)

    def test_laser_only_closes_laser_but_keeps_gain(self):
        self.camera.set_emccd_gain(50)
        open_shutter(self.laser_name)
        dlg = ZeroOrderSafetyDialog(self.camera, self.spectrometer)
        dlg._on_laser_only()
        self.assertEqual(get_open_shutter_names(), [])
        self.assertEqual(self.camera.get_emccd_gain(), 50)
        self.assertEqual(dlg.chosen_action, ZeroOrderSafetyDialog.ACTION_LASER_ONLY)

    def test_gain_only_zeroes_gain_but_keeps_laser_open(self):
        self.camera.set_emccd_gain(50)
        open_shutter(self.laser_name)
        dlg = ZeroOrderSafetyDialog(self.camera, self.spectrometer)
        dlg._on_gain_only()
        self.assertEqual(self.camera.get_emccd_gain(), 0)
        self.assertIn(self.laser_name, get_open_shutter_names())
        self.assertEqual(dlg.chosen_action, ZeroOrderSafetyDialog.ACTION_GAIN_ONLY)

    def test_override_ignore_changes_nothing(self):
        self.camera.set_emccd_gain(50)
        open_shutter(self.laser_name)
        dlg = ZeroOrderSafetyDialog(self.camera, self.spectrometer)
        dlg._on_override()
        self.assertEqual(self.camera.get_emccd_gain(), 50)
        self.assertIn(self.laser_name, get_open_shutter_names())
        self.assertEqual(dlg.chosen_action, ZeroOrderSafetyDialog.ACTION_OVERRIDE)

    def test_cancel_leaves_state_untouched_and_no_action_chosen(self):
        self.camera.set_emccd_gain(50)
        open_shutter(self.laser_name)
        dlg = ZeroOrderSafetyDialog(self.camera, self.spectrometer)
        dlg.reject()
        self.assertIsNone(dlg.chosen_action)
        self.assertEqual(self.camera.get_emccd_gain(), 50)
        self.assertIn(self.laser_name, get_open_shutter_names())

    def test_execute_and_move_moves_spectrograph_only_when_accepted(self):
        calls = {"n": 0}
        orig = self.spectrometer.goto_zero_order

        def spy(*args, **kwargs):
            calls["n"] += 1
            return orig(*args, **kwargs)

        self.spectrometer.goto_zero_order = spy
        try:
            dlg = ZeroOrderSafetyDialog(self.camera, self.spectrometer)
            dlg.exec = lambda: (dlg._on_safe_default(), QtWidgets.QDialog.DialogCode.Accepted)[-1]
            action = dlg.execute_and_move()
            self.assertEqual(action, ZeroOrderSafetyDialog.ACTION_SAFE_DEFAULT)
            self.assertEqual(calls["n"], 1)
            _, wl = self.spectrometer.ShamrockGetWavelength(0)
            self.assertEqual(wl, 0.0)
        finally:
            self.spectrometer.goto_zero_order = orig

    def test_execute_and_move_does_not_move_spectrograph_when_cancelled(self):
        calls = {"n": 0}
        orig = self.spectrometer.goto_zero_order
        self.spectrometer.goto_zero_order = lambda *a, **k: calls.__setitem__("n", calls["n"] + 1)
        try:
            dlg = ZeroOrderSafetyDialog(self.camera, self.spectrometer)
            dlg.exec = lambda: QtWidgets.QDialog.DialogCode.Rejected
            action = dlg.execute_and_move()
            self.assertIsNone(action)
            self.assertEqual(calls["n"], 0)
        finally:
            self.spectrometer.goto_zero_order = orig


if __name__ == "__main__":
    unittest.main()
