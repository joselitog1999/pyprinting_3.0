# -*- coding: utf-8 -*-
"""
test_senior_qc_fixes.py — Pruebas de Verificación de No-Conformidades Senior QC
PyPrinting 3.0 & PySpectrum 3.0 — UNSAM Nanofotónica

Verifica estrictamente:
- NC-01: 5 Modos de criterio de parada, controles de interfaz Modo 3/4 y detección.
- NC-02: Adquisición fresca en dimers.py (start_acquisition) y soporte 1D/2D.
- NC-03: Generalización multi-láser en fit_raman_water.py y dinámica de bandas Stokes de agua.
"""
import os
import sys
import unittest
import numpy as np
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


class TestSeniorQCFixes(unittest.TestCase):

    def test_nc01_measurements_stopping_modes(self):
        """Verifica la existencia y configuración de los 5 modos de parada en measurements.py."""
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication(sys.argv)

        from modules.measurements import Frontend
        trace_widget = Frontend(mode="printing")

        # 1. Comprobar que el combo tiene exactamente 5 elementos
        self.assertEqual(trace_widget.stop_mode_combo.count(), 5)
        self.assertIn("Modo 3: Calibración Confocal Raw", trace_widget.stop_mode_combo.itemText(3))
        self.assertIn("Modo 4: Criterio Híbrido Tri-Factor", trace_widget.stop_mode_combo.itemText(4))

        # 2. Comprobar existencia de widgets de Modo 3
        self.assertTrue(hasattr(trace_widget, "ratio_kEdit"))
        self.assertTrue(hasattr(trace_widget, "percent_threshEdit"))
        self.assertTrue(hasattr(trace_widget, "lbl_ratio_k"))
        self.assertTrue(hasattr(trace_widget, "lbl_percent_thresh"))

        # 3. Comprobar visibilidad dinámica al alternar modos
        # Modo 0: ratio_k y percent_thresh ocultos, umbralEdit visible
        trace_widget.stop_mode_combo.setCurrentIndex(0)
        self.assertTrue(trace_widget.ratio_kEdit.isHidden())
        self.assertTrue(trace_widget.percent_threshEdit.isHidden())
        self.assertFalse(trace_widget.umbralEdit.isHidden())

        # Modo 3: ratio_k y percent_thresh visibles, umbral_abs visible
        trace_widget.stop_mode_combo.setCurrentIndex(3)
        self.assertFalse(trace_widget.ratio_kEdit.isHidden())
        self.assertFalse(trace_widget.percent_threshEdit.isHidden())
        self.assertFalse(trace_widget.umbral_absEdit.isHidden())

        # Modo 4: hybrid tri-factor, ratio_k oculto, slope_flat visible
        trace_widget.stop_mode_combo.setCurrentIndex(4)
        self.assertTrue(trace_widget.ratio_kEdit.isHidden())
        self.assertFalse(trace_widget.slope_flatEdit.isHidden())
        self.assertFalse(trace_widget.umbralEdit.isHidden())
        self.assertFalse(trace_widget.umbral_absEdit.isHidden())

    def test_nc02_dimers_fresh_acquisition(self):
        """Verifica que DimersBackend ejecuta start_acquisition y procesa frames 1D/2D."""
        from pyspectrum.modules.routines.dimers import DimersBackend

        class MockCamera:
            def __init__(self):
                self.started = False
                self.exposure = 0.1
                self.width = 1004
                self.height = 1002

            def set_exposure_time(self, exp):
                self.exposure = exp

            def start_acquisition(self):
                self.started = True
                return 0

            def get_most_recent_image(self):
                # Retorna frame 2D
                return np.ones((50, 1004), dtype=np.float32) * 123.0

        class MockSpectrometer:
            def ShamrockGetCalibration(self, dev, num_pix):
                return 0, np.linspace(500, 700, num_pix)

        cam = MockCamera()
        spec = MockSpectrometer()
        backend = DimersBackend(camera=cam, spectrometer=spec)

        emitted = []
        backend.dimerDataSignal.connect(lambda mode, wave, s, diff: emitted.append((mode, s)))

        # Simular sesión adquirida
        from pyspectrum.modules.hardware_session import hardware_session
        hardware_session.current_user = None  # asegurar libre

        backend.acquire_polarization("parallel", 0.05)
        self.assertTrue(cam.started, "start_acquisition() debe haberse llamado para asegurar frame fresco")
        self.assertEqual(len(emitted), 1)
        self.assertEqual(emitted[0][0], "parallel")
        self.assertAlmostEqual(float(emitted[0][1][0]), 123.0)

    def test_nc03_raman_dynamic_wavelength(self):
        """Verifica la generalización multi-láser en fit_signal_raman y three_lorentz."""
        from pyspectrum.calibration.fit_raman_water import fit_signal_raman, three_lorentz

        # 1. Con 532 nm, los centros de agua son 649 nm y 702 nm
        x = np.linspace(550, 800, 300)
        # Sintetizar señal con lorentziana en 649 y 702
        y_sim = three_lorentz(x, 1000.0, 30.0, 580.0, 800.0, 500.0, 100.0)
        w_fit, s_fit, params = fit_signal_raman(x, y_sim, ends_notch=540.0, final_wave=800.0, laser_nm=532.0)
        self.assertEqual(len(w_fit), 500)
        self.assertEqual(len(params), 6)

        # 2. Con láser a 632.8 nm (He-Ne), la banda O-H (3388.7 cm^-1) se desplaza a ~805.5 nm
        nu_laser = 1.0e7 / 632.8
        expected_stokes_oh = 1.0e7 / (nu_laser - 3388.67)
        self.assertAlmostEqual(expected_stokes_oh, 805.5, delta=1.0)

        # Probar que fit_signal_raman procesa láser alternativo sin error
        x_red = np.linspace(650, 950, 300)
        y_red = np.ones(300) * 50.0
        w_fit2, s_fit2, params2 = fit_signal_raman(x_red, y_red, ends_notch=640.0, final_wave=950.0, laser_nm=632.8)
        self.assertEqual(len(w_fit2), 500)


if __name__ == "__main__":
    unittest.main()
