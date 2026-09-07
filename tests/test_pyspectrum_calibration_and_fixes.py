# -*- coding: utf-8 -*-
"""
test_pyspectrum_calibration_and_fixes.py — Tests de Validación de Calibraciones y Parches de PySpectrum 3.0
PySpectrum 3.0 — UNSAM Nanofotónica
"""
import os
import sys
import unittest
import numpy as np
from pathlib import Path
from PyQt6 import QtWidgets, QtCore

# Asegurar root en sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Aplicación Qt compartida para tests
app = QtWidgets.QApplication.instance()
if app is None:
    app = QtWidgets.QApplication(sys.argv)

from pyspectrum.drivers.shamrock_driver import (
    _MockShamrock,
    ShamrockDriver,
    SHAMROCK_SUCCESS,
    DEVICE,
    INPUT_SLIT_PORT,
    get_shamrock
)
from pyspectrum.drivers.andor_ccd_driver import get_andor_ccd
from pyspectrum.modules import step_and_glue
from pyspectrum.modules import camera_andor
from pyspectrum.modules.calibration_dock import CalibrationFrontend, CalibrationBackend
from pyspectrum.window import PySpectrumWindow


class TestShamrockSDKOffsets(unittest.TestCase):
    """Verificación de que los métodos de offset coinciden con la SDK de Shamrock."""

    def setUp(self):
        self.mock = _MockShamrock()

    def test_grating_offset_mock(self):
        # Grating 1
        ret, val = self.mock.get_grating_offset(DEVICE, 1)
        self.assertEqual(ret, SHAMROCK_SUCCESS)
        self.assertEqual(val, 0)

        # Modificar offset de rejilla 1
        ret_set = self.mock.set_grating_offset(DEVICE, 1, 450)
        self.assertEqual(ret_set, SHAMROCK_SUCCESS)
        ret, val = self.mock.get_grating_offset(DEVICE, 1)
        self.assertEqual(val, 450)

        # Grating 2 independiente
        self.mock.set_grating_offset(DEVICE, 2, -120)
        _, val2 = self.mock.get_grating_offset(DEVICE, 2)
        self.assertEqual(val2, -120)
        _, val1 = self.mock.get_grating_offset(DEVICE, 1)
        self.assertEqual(val1, 450)

    def test_detector_offset_mock(self):
        ret, val = self.mock.get_detector_offset(DEVICE)
        self.assertEqual(ret, SHAMROCK_SUCCESS)
        self.assertEqual(val, 0)

        ret_set = self.mock.set_detector_offset(DEVICE, 85)
        self.assertEqual(ret_set, SHAMROCK_SUCCESS)
        ret, val = self.mock.get_detector_offset(DEVICE)
        self.assertEqual(val, 85)

    def test_slit_zero_position_mock(self):
        ret, val = self.mock.get_slit_zero_position(DEVICE, INPUT_SLIT_PORT)
        self.assertEqual(ret, SHAMROCK_SUCCESS)
        self.assertEqual(val, 0)

        ret_set = self.mock.set_slit_zero_position(DEVICE, INPUT_SLIT_PORT, -15)
        self.assertEqual(ret_set, SHAMROCK_SUCCESS)
        ret, val = self.mock.get_slit_zero_position(DEVICE, INPUT_SLIT_PORT)
        self.assertEqual(val, -15)

    def test_driver_real_class_has_sdk_methods(self):
        """Verifica que la clase ShamrockDriver real tiene los métodos con la firma adecuada."""
        driver = ShamrockDriver()
        self.assertTrue(hasattr(driver, "ShamrockGetGratingOffset"))
        self.assertTrue(hasattr(driver, "ShamrockSetGratingOffset"))
        self.assertTrue(hasattr(driver, "ShamrockGetDetectorOffset"))
        self.assertTrue(hasattr(driver, "ShamrockSetDetectorOffset"))
        self.assertTrue(hasattr(driver, "ShamrockGetSlitZeroPosition"))
        self.assertTrue(hasattr(driver, "ShamrockSetSlitZeroPosition"))


class TestStepAndGluePatches(unittest.TestCase):
    """Verificación de parches en step_and_glue."""

    def test_signals_and_orphan_cleanup(self):
        fe = step_and_glue.Frontend()
        # Verificar que la señal residual ya no existe
        self.assertFalse(hasattr(fe, "measureKineticsSignal"))
        # Verificar que existen las señales activas y conectables
        self.assertTrue(hasattr(fe, "stopMeasurementSignal"))
        self.assertTrue(hasattr(fe, "saveSpectrumSignal"))
        self.assertTrue(hasattr(fe, "btn_stop"))
        self.assertTrue(hasattr(fe, "btn_save"))

    def test_abort_execution(self):
        be = step_and_glue.Backend()
        fe = step_and_glue.Frontend()
        be.make_connection(fe)

        self.assertFalse(be._abort_requested)
        fe.stopMeasurementSignal.emit()
        self.assertTrue(be._abort_requested)

    def test_save_spectrum(self):
        be = step_and_glue.Backend()
        fe = step_and_glue.Frontend()
        be.make_connection(fe)

        test_file = ROOT_DIR / "scratch" / "test_saved_spectrum.txt"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        if test_file.exists():
            test_file.unlink()

        be._last_wave = np.linspace(500, 600, 100)
        be._last_spec = np.random.rand(100) * 1000
        be._last_norm = np.random.rand(100)

        fe.saveSpectrumSignal.emit(str(test_file))
        self.assertTrue(test_file.exists())

        # Verificar datos guardados
        data = np.loadtxt(test_file)
        self.assertEqual(data.shape[0], 100)
        self.assertEqual(data.shape[1], 3)
        test_file.unlink()


class TestCameraAndorPatches(unittest.TestCase):
    """Verificación de parches en camera_andor."""

    def test_orphan_signal_removed(self):
        fe = camera_andor.Frontend()
        self.assertFalse(hasattr(fe, "saveSpectrumSignal"))


class TestCalibrationDock(unittest.TestCase):
    """Verificación de la pestaña modular de calibraciones."""

    def setUp(self):
        self.mock_spec = _MockShamrock()
        self.fe = CalibrationFrontend()
        self.be = CalibrationBackend(spectrometer=self.mock_spec)
        self.be.make_connection(self.fe)

    def test_connection_and_initial_values(self):
        self.assertIsNotNone(self.fe.spin_slit_width)
        self.assertIsNotNone(self.fe.spin_pixel_x)
        self.assertIsNotNone(self.fe.spin_grating_off)
        self.assertIsNotNone(self.fe.spin_detector_off)
        self.assertIsNotNone(self.fe.spin_slit_zero)

    def test_slit_gaussian_fit(self):
        """Genera un perfil gaussiano artificial con centro en X = 512.4 px y verifica recuperación."""
        x = np.arange(1002, dtype=np.float64)
        true_center = 512.4
        true_sigma = 4.2
        y = 5000.0 * np.exp(-((x - true_center) ** 2) / (2.0 * true_sigma ** 2)) + 120.0
        # Añadir ruido aleatorio
        np.random.seed(42)
        y += np.random.normal(0, 15, len(y))

        centroid, fwhm, fit_curve = self.be._fit_gaussian_slit(x, y)
        self.assertAlmostEqual(centroid, true_center, delta=0.2)
        self.assertAlmostEqual(fwhm, 2.355 * true_sigma, delta=0.5)

    def test_grating_offset_flow(self):
        self.fe.spin_grating_off.setValue(320)
        self.fe.setGratingOffsetSignal.emit(1, 320)
        _, val = self.be.spectrometer.ShamrockGetGratingOffset(DEVICE, 1)
        self.assertEqual(val, 320)

    def test_detector_offset_flow(self):
        self.fe.spin_detector_off.setValue(-75)
        self.fe.setDetectorOffsetSignal.emit(-75)
        _, val = self.be.spectrometer.ShamrockGetDetectorOffset(DEVICE)
        self.assertEqual(val, -75)

    def test_zero_order_flow(self):
        self.fe.gotoZeroOrderSignal.emit()
        _, wl = self.be.spectrometer.ShamrockGetWavelength(DEVICE)
        self.assertEqual(wl, 0.0)


class TestWindowIntegration(unittest.TestCase):
    """Verificación de que el dock se integra a la ventana principal de PySpectrum."""

    def test_dock_present_in_window(self):
        # Mock QMessageBox.question para evitar diálogo interactivo
        orig_question = QtWidgets.QMessageBox.question
        QtWidgets.QMessageBox.question = lambda *a, **k: QtWidgets.QMessageBox.StandardButton.Yes
        try:
            win = PySpectrumWindow()
            self.assertTrue(hasattr(win, "dock_calibration"))
            self.assertTrue(hasattr(win, "calib_widget"))
            self.assertTrue(hasattr(win, "calib_backend"))
            self.assertIsNotNone(win.dock_calibration)
            win.close()
        finally:
            QtWidgets.QMessageBox.question = orig_question


if __name__ == "__main__":
    unittest.main()
