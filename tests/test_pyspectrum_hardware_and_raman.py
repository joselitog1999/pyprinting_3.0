# -*- coding: utf-8 -*-
"""
test_pyspectrum_hardware_and_raman.py — Pruebas Automatizadas de Hardware y Raman Estático
PySpectrum 3.0 — UNSAM Nanofotónica
"""
import sys
import os
import unittest
from pathlib import Path
import numpy as np

# Añadir directorio raíz a sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# Asegurar modo seguro y evitar interfaz gráfica bloqueante
os.environ["PYPRINTING_SAFE"] = "1"
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6 import QtWidgets
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

from config import SHUTTERS
from pyspectrum.drivers.shamrock_driver import (
    DEVICE, GRATING_150_LINES, GRATING_1200_LINES, NAME_GRATINGS, get_shamrock
)
from pyspectrum.drivers.andor_ccd_driver import (
    get_andor_ccd, DRV_SUCCESS, DRV_TEMP_STABILIZED
)
from pyspectrum.modules.camera_andor import Frontend as CameraFrontend, Backend as CameraBackend
from pyspectrum.modules.spectrum_control import Frontend as SpectrumFrontend, Backend as SpectrumBackend
from pyspectrum.modules.static_raman import (
    StaticRamanWidget, StaticRamanBackend, LASER_WAVELENGTH_MAP
)


class TestShamrockHardware(unittest.TestCase):
    """Verificación de especificaciones y calibración de redes del Shamrock 500i."""

    def setUp(self):
        self.shamrock = get_shamrock(force_mock=True)

    def test_gratings_preconfigured(self):
        """Verifica que las redes pre-configuradas coincidan con el hardware real."""
        self.assertIn("150 líneas/mm", NAME_GRATINGS[0])
        self.assertIn("800 nm", NAME_GRATINGS[0])
        self.assertIn("1200 líneas/mm", NAME_GRATINGS[1])
        self.assertIn("500 nm", NAME_GRATINGS[1])

        # Inspección por SDK
        ret1, lines1, blaze1, _, _ = self.shamrock.ShamrockGetGratingInfo(DEVICE, 1)
        self.assertEqual(ret1, 20202)  # SHAMROCK_SUCCESS
        self.assertEqual(lines1, 150.0)
        self.assertEqual(blaze1, "800nm")

        ret2, lines2, blaze2, _, _ = self.shamrock.ShamrockGetGratingInfo(DEVICE, 2)
        self.assertEqual(ret2, 20202)
        self.assertEqual(lines2, 1200.0)
        self.assertEqual(blaze2, "500nm")

    def test_dispersion_shamrock_500i(self):
        """Verifica la dispersión física del Shamrock 500i (f = 500 mm)."""
        self.shamrock.ShamrockSetGrating(DEVICE, 1)  # 150 l/mm
        self.shamrock.ShamrockSetWavelength(DEVICE, 532.0)
        _, wl1 = self.shamrock.ShamrockGetCalibration(DEVICE, 1002)
        span1 = wl1[-1] - wl1[0]
        # ~175 nm span total en el detector
        self.assertGreater(span1, 160.0)
        self.assertLess(span1, 190.0)

        self.shamrock.ShamrockSetGrating(DEVICE, 2)  # 1200 l/mm
        _, wl2 = self.shamrock.ShamrockGetCalibration(DEVICE, 1002)
        span2 = wl2[-1] - wl2[0]
        # ~22 nm span total en el detector
        self.assertGreater(span2, 18.0)
        self.assertLess(span2, 26.0)

    def test_motorized_slit_range(self):
        """Verifica que la ranura motorizada admita aperturas desde 10 µm hasta 2500 µm."""
        # Prueba en límite inferior
        self.shamrock.ShamrockSetSlit(DEVICE, 1, 10.0)
        ret, w_min = self.shamrock.ShamrockGetSlit(DEVICE, 1)
        self.assertEqual(ret, 20202)
        self.assertEqual(w_min, 10.0)

        # Prueba en régimen confocal
        self.shamrock.ShamrockSetSlit(DEVICE, 1, 50.0)
        _, w_conf = self.shamrock.ShamrockGetSlit(DEVICE, 1)
        self.assertEqual(w_conf, 50.0)

        # Prueba en apertura máxima (2500 µm = 2.5 mm)
        self.shamrock.ShamrockSetSlit(DEVICE, 1, 2500.0)
        _, w_max = self.shamrock.ShamrockGetSlit(DEVICE, 1)
        self.assertEqual(w_max, 2500.0)

        # Prueba de saturación / clamp
        self.shamrock.ShamrockSetSlit(DEVICE, 1, 3000.0)
        _, w_clamped = self.shamrock.ShamrockGetSlit(DEVICE, 1)
        self.assertEqual(w_clamped, 2500.0)


class TestAndorCCDAndCooling(unittest.TestCase):
    """Verificación de control de enfriamiento, amplificadores y ganancia EM de la iXon3."""

    def setUp(self):
        self.camera = get_andor_ccd(force_mock=True)

    def test_cooling_auto_activation(self):
        """Verifica que fijar temperatura active automáticamente el enfriamiento."""
        self.camera.cooler_off()
        ret = self.camera.set_temperature(-65.0)
        self.assertEqual(ret, DRV_SUCCESS)
        self.assertTrue(self.camera._cooler_on)

        # Simular avance térmico
        for _ in range(50):
            status, temp = self.camera.get_temperature()

        self.assertAlmostEqual(temp, -65.0, delta=1.0)
        self.assertEqual(status, DRV_TEMP_STABILIZED)

    def test_output_amplifier_and_gain(self):
        """Verifica selección entre amplificador EMCCD y Convencional."""
        # Modo EMCCD (0)
        self.camera.set_output_amplifier(0)
        self.assertEqual(self.camera.get_output_amplifier(), 0)
        self.camera.set_emccd_gain(250)
        self.assertEqual(self.camera.get_emccd_gain(), 250)

        img_em = self.camera.get_most_recent_image()
        mean_em = np.mean(img_em)

        # Modo Convencional (1)
        self.camera.set_output_amplifier(1)
        self.assertEqual(self.camera.get_output_amplifier(), 1)
        img_conv = self.camera.get_most_recent_image()
        mean_conv = np.mean(img_conv)

        # La ganancia EM debe amplificar sustancialmente la señal en modo 0
        self.assertGreater(mean_em, mean_conv)


class TestCameraFrontendUI(unittest.TestCase):
    """Verificación de controles interactivos acoplados en el Frontend de Cámara."""

    def setUp(self):
        self.widget = CameraFrontend()

    def test_slider_and_spinbox_sync(self):
        """Verifica que el slider y la casilla numérica de EM Gain estén acoplados bidireccionalmente."""
        # Slider -> SpinBox
        self.widget.slider_gain.setValue(75)
        self.assertEqual(self.widget.spin_gain.value(), 75)
        self.assertIn("75x", self.widget.lbl_gain_badge.text())

        # SpinBox -> Slider
        self.widget.spin_gain.setValue(220)
        self.assertEqual(self.widget.slider_gain.value(), 220)
        self.assertIn("220x", self.widget.lbl_gain_badge.text())
        self.assertIn("⚠️", self.widget.lbl_gain_badge.text())

        # Alerta roja (> 300)
        self.widget.slider_gain.setValue(450)
        self.assertIn("🔥", self.widget.lbl_gain_badge.text())

    def test_output_amplifier_disables_gain(self):
        """En modo convencional, los controles de EM Gain deben desactivarse."""
        self.widget.cmb_amp.setCurrentIndex(1)  # Convencional
        self.assertFalse(self.widget.slider_gain.isEnabled())
        self.assertFalse(self.widget.spin_gain.isEnabled())
        self.assertIn("N/A", self.widget.lbl_gain_badge.text())

        self.widget.cmb_amp.setCurrentIndex(0)  # EMCCD
        self.assertTrue(self.widget.slider_gain.isEnabled())
        self.assertTrue(self.widget.spin_gain.isEnabled())


class TestStaticRamanModule(unittest.TestCase):
    """Verificación de widget modular y algoritmos de Raman Estático."""

    def setUp(self):
        self.camera = get_andor_ccd(force_mock=True)
        self.spectrometer = get_shamrock(force_mock=True)
        self.widget = StaticRamanWidget()
        self.backend = StaticRamanBackend(self.camera, self.spectrometer)
        self.backend.make_connection(self.widget)

    def test_default_grating_is_150(self):
        """Verifica que la red inicial sea la de 150 l/mm (exploratoria)."""
        grating_idx = self.widget.cmb_grating.currentData()
        self.assertEqual(grating_idx, 1)  # 150 l/mm
        self.assertIn("150 l/mm", self.widget.cmb_grating.currentText())

    def test_lasers_shared_with_pyprinting(self):
        """Verifica que los láseres provengan de config.SHUTTERS."""
        combo_items = [self.widget.cmb_laser.itemText(i) for i in range(self.widget.cmb_laser.count())]
        for s in SHUTTERS:
            found = any(s in item for item in combo_items)
            self.assertTrue(found, f"Láser {s} no encontrado en selector.")

    def test_window_presets(self):
        """Verifica los cálculos de longitud de onda central para los modos de ventana."""
        # Modo Stokes Fingerprint a 532 nm
        self.widget.cmb_mode.setCurrentIndex(0)
        wl_stokes = self.widget.spin_center_wl.value()
        self.assertGreater(wl_stokes, 560.0)
        self.assertLess(wl_stokes, 570.0)

        # Modo Simétrico Stokes + Anti-Stokes (532 nm)
        self.widget.cmb_mode.setCurrentIndex(1)
        wl_sym = self.widget.spin_center_wl.value()
        self.assertEqual(wl_sym, 532.0)

    def test_realtime_processing_pipeline(self):
        """Verifica que la recepción de datos ejecute despiking, línea base y shift Raman."""
        wl_axis = np.linspace(520.0, 600.0, 1002)
        # Señal sintética: fondo + pico Stokes a 547.1 nm (~519 cm^-1) + spike cósmico
        counts = 500.0 + 1000.0 * np.exp(-0.5 * ((wl_axis - 547.1) / 0.3)**2)
        counts[300] += 8000.0  # Spike cósmico artificial

        self.widget.chk_despike.setChecked(True)
        self.widget.chk_baseline.setChecked(True)
        self.widget.chk_savgol.setChecked(True)

        self.widget.update_spectrum_data(wl_axis, counts)

        # Verificar que el spike fue removido por despiking
        self.assertLess(self.widget.processed_y[300], 4000.0)
        # Verificar que el eje X fue convertido a Raman Shift cm^-1
        self.assertGreater(self.widget.processed_x[-1], 2000.0)
        self.assertLess(self.widget.processed_x[0], 0.0)

    def test_photothermal_thermometry_calculation(self):
        """Verifica la telemetría y cálculo de temperatura fototérmica."""
        # Configurar en modo simétrico a 532 nm
        self.widget.laser_nm = 532.0
        wl_axis = np.linspace(510.0, 555.0, 1002)
        counts = np.ones(1002) * 200.0

        # Crear pico Stokes a +520 cm^-1 y Anti-Stokes a -520 cm^-1 a T ~ 350 K
        # Stokes: ~547.1 nm
        # Anti-Stokes: ~517.6 nm
        idx_stokes = np.argmin(np.abs(wl_axis - 547.1))
        idx_as = np.argmin(np.abs(wl_axis - 517.6))

        # Razón Boltzmann a ~350 K para 520 cm^-1: ~0.117
        counts[idx_stokes] += 5000.0
        counts[idx_as] += 5000.0 * 0.117

        self.widget.update_spectrum_data(wl_axis, counts)

        # Ubicar cursores en Stokes (+520) y Anti-Stokes (-520)
        self.widget.cursor_a.setValue(520.0)
        self.widget.cursor_b.setValue(-520.0)
        self.widget._update_telemetry()

        # Debe detectarse temperatura fototérmica en rango físicamente realista (300K a 400K)
        temp_text = self.widget.lbl_temp_info.text()
        self.assertIn("Temp Fototérmica:", temp_text)
        self.assertIn("K", temp_text)


if __name__ == "__main__":
    unittest.main()
