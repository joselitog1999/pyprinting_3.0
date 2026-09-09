# -*- coding: utf-8 -*-
"""
test_pyspectrum_stability_safety.py — Batería Integral de Pruebas de Estabilidad, Confiabilidad y Seguridad
PySpectrum 3.0 — UNSAM Nanofotónica
"""
from __future__ import annotations
import os
import sys
import time
import tempfile
import unittest
from pathlib import Path
import numpy as np

# Asegurar root en sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Configurar entorno de simulación seguro y headless para pruebas Qt
os.environ["PYPRINTING_SAFE"] = "1"
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6 import QtWidgets, QtCore
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

import config
from config import SHUTTERS, SHUTTER_POLARITY
from core import nidaq
from core.nidaq import (
    open_shutter, close_shutter, close_all_shutters,
    heartbeat_shutter, is_watchdog_armed, get_watchdog_remaining_time
)
from pyspectrum.drivers.shamrock_driver import (
    DEVICE, _MockShamrock, get_shamrock,
    GRATING_SETTLING_TIME_S, SLIT_SETTLING_TIME_S, WAVELENGTH_SETTLING_TIME_S
)
from pyspectrum.drivers.andor_ccd_driver import (
    _MockAndorCCD, get_andor_ccd, DRV_SUCCESS
)
from pyspectrum.modules.hardware_session import hardware_session
from pyspectrum.modules import spectrum_control
from pyspectrum.modules import step_and_glue
from pyspectrum.modules import camera_andor
from pyspectrum.modules import hyperspectral_confocal
from pyspectrum.modules.routines.luminescence import LuminescenceWidget, LuminescenceBackend
from pyspectrum.modules.routines.growth_kinetics import GrowthKineticsWidget, GrowthKineticsBackend
from pyspectrum.modules.routines.dimers import DimersWidget, DimersBackend
from pyspectrum.calibration.halogen_lamp import HalogenLampCalibration, glue_steps
from pyspectrum.calibration.fit_polynomial import fit_signal_polynomial
from pyspectrum.window import PySpectrumWindow


class TestPySpectrumStability(unittest.TestCase):
    """Pruebas de estabilidad, resiliencia bajo carga y ciclo de vida de componentes."""

    def setUp(self):
        self.camera = get_andor_ccd(force_mock=True)
        self.spectrometer = get_shamrock(force_mock=True)

    def test_continuous_frame_acquisition_stress(self):
        """Stress testing: adquisición continua de 100 cuadros simulados verificando consistencia y memoria."""
        frame_shape = (1002, 1004)
        means = []
        for i in range(100):
            frame = self.camera.get_most_recent_image()
            self.assertEqual(frame.shape, frame_shape, f"Cuadro {i} con dimensión inesperada: {frame.shape}")
            self.assertIn(frame.dtype, (np.float32, np.float64))
            m = np.mean(frame)
            self.assertFalse(np.isnan(m) or np.isinf(m), f"Cuadro {i} contiene valores inválidos")
            means.append(m)

        self.assertEqual(len(means), 100)
        # Verificar que no hubo degeneración a ceros o infinitos
        self.assertGreater(np.mean(means), 0.0)

    def test_rapid_start_stop_toggling(self):
        """Prueba de resiliencia: encendido y detención instantánea repetida (10 ciclos) sin timers huérfanos."""
        # 1. LuminescenceBackend
        laser_green = SHUTTERS[0]
        laser_red = SHUTTERS[1]
        l_be = LuminescenceBackend(self.camera, self.spectrometer)
        for _ in range(10):
            l_be.start_luminescence(laser_green, 0.05, 50, 0.1)
            self.assertTrue(l_be.timer.isActive())
            l_be.stop_luminescence()
            self.assertFalse(l_be.timer.isActive())

        # 2. GrowthKineticsBackend
        g_be = GrowthKineticsBackend(self.camera, self.spectrometer)
        for _ in range(10):
            g_be.start_growth(laser_red, 0.05, 50, 0.1)
            self.assertTrue(g_be.timer.isActive())
            g_be.stop_growth()
            self.assertFalse(g_be.timer.isActive())

        # 3. ConfocalBackend
        c_be = hyperspectral_confocal.Backend(self.camera, self.spectrometer)
        for _ in range(10):
            c_be.start_scan(45.0, 50.0, 45.0, 50.0, 1.0, 0.05)
            self.assertTrue(c_be.scan_timer.isActive())
            c_be.stop_scan()
            self.assertFalse(c_be.scan_timer.isActive())

    def test_step_and_glue_immediate_abort_resilience(self):
        """Verifica que abortar Step & Glue de inmediato o entre pasos no cause excepciones."""
        be = step_and_glue.Backend(self.camera, self.spectrometer)
        fe = step_and_glue.Frontend()
        be.make_connection(fe)

        # Aborto previo inmediato
        be._abort_requested = True
        # Debe retornar limpiamente sin levantar ValueError en np.concatenate
        try:
            be.measure_step_and_glue(450.0, 750.0, 0.2, 0.05, normalize=False)
        except Exception as e:
            self.fail(f"measure_step_and_glue falló tras aborto previo: {e}")

        # Aborto tras señal
        be._abort_requested = False
        fe.stopMeasurementSignal.emit()
        self.assertTrue(be._abort_requested)

    def test_window_lifecycle_and_clean_exit(self):
        """Verifica apertura, inspección de docks y cierre ordenado de PySpectrumWindow."""
        orig_question = QtWidgets.QMessageBox.question
        QtWidgets.QMessageBox.question = lambda *a, **k: QtWidgets.QMessageBox.StandardButton.Yes
        try:
            win = PySpectrumWindow()
            # Docks obligatorios
            self.assertIsNotNone(win.dock_camera)
            self.assertIsNotNone(win.dock_spectrometer)
            self.assertIsNotNone(win.dock_sandg)
            self.assertIsNotNone(win.dock_raman)
            self.assertIsNotNone(win.dock_calibration)
            self.assertIsNotNone(win.dock_confocal)

            # Widgets de rutinas
            self.assertIsNotNone(win.lumin_widget)
            self.assertIsNotNone(win.growth_widget)
            self.assertIsNotNone(win.dimers_widget)

            # Cierre seguro
            win.close()
            self.assertFalse(win.isVisible())
        finally:
            QtWidgets.QMessageBox.question = orig_question

    def test_hyperspectral_cube_allocation_memory(self):
        """Verifica que el hipercubo hiperespectral (X, Y, λ) se reserve e indexe sin errores de límites."""
        c_be = hyperspectral_confocal.Backend(self.camera, self.spectrometer)
        c_be.start_scan(xmin=48.0, xmax=52.0, ymin=48.0, ymax=52.0, step=2.0, exp_time=0.01)

        self.assertEqual(c_be.nx, 3)
        self.assertEqual(c_be.ny, 3)
        self.assertEqual(c_be.total_points, 9)
        self.assertEqual(c_be._datacube.shape, (3, 3, 1004))
        self.assertEqual(c_be.map_2d.shape, (3, 3))

        # Simular 3 pasos
        for _ in range(3):
            c_be._scan_step()

        self.assertEqual(c_be.points_done, 3)
        self.assertGreater(c_be.map_2d[0, 0], 0.0)
        c_be.stop_scan()
        self.assertFalse(c_be._scanning)


class TestPySpectrumLegacyRoutines(unittest.TestCase):
    """Pruebas de preservación de funciones y algoritmos de legado histórico."""

    def setUp(self):
        self.camera = get_andor_ccd(force_mock=True)
        self.spectrometer = get_shamrock(force_mock=True)

    def test_step_and_glue_sigmoidal_monotonicity(self):
        """Verifica que el cosido espectral histórico (glue_steps) genere un eje monótonamente creciente."""
        w1 = np.linspace(450.0, 650.0, 1004)
        w2 = np.linspace(600.0, 800.0, 1004)
        s1 = 200.0 + 1000.0 * np.exp(-0.5 * ((w1 - 550.0) / 20.0)**2)
        s2 = 200.0 + 500.0 * np.exp(-0.5 * ((w2 - 700.0) / 30.0)**2)

        concat_w = np.concatenate([w1, w2])
        concat_s = np.concatenate([s1, s2])

        glued_w, glued_s = glue_steps(concat_w, concat_s, number_pixel=1004, grade=2.0)

        # 1. Monotonicidad estricta (sin longitudes de onda repetidas o decrecientes)
        self.assertTrue(np.all(np.diff(glued_w) > 0), "El eje resultante de Step & Glue no es monótono creciente")
        # 2. Rango espectral expandido
        self.assertLess(glued_w[0], 460.0)
        self.assertGreater(glued_w[-1], 790.0)
        # 3. Continuidad de intensidades
        self.assertEqual(len(glued_w), len(glued_s))
        self.assertTrue(np.all(glued_s > 0))

    def test_halogen_lamp_calibration_legacy(self):
        """Verifica la carga del espectro de referencia de la lámpara halógena y su normalización."""
        lamp = HalogenLampCalibration()
        self.assertTrue(lamp.is_loaded, "No se pudo cargar el perfil de lámpara halógena")

        # Probar normalización con espectro sintético
        test_w = np.linspace(500.0, 850.0, 1004)
        test_s = np.ones(1004) * 5000.0
        norm_s = lamp.normalize_spectrum(test_w, test_s)

        self.assertEqual(len(norm_s), len(test_w))
        self.assertFalse(np.any(np.isnan(norm_s)))
        self.assertFalse(np.any(np.isinf(norm_s)))
        self.assertTrue(np.all(norm_s >= 0))

    def test_luminescence_routine_signals_and_integration(self):
        """Verifica que la rutina de fotoluminiscencia calcule I(t) y emita telemetría espectral."""
        widget = LuminescenceWidget()
        backend = LuminescenceBackend(self.camera, self.spectrometer)
        backend.make_connection(widget)

        received_packets = []
        backend.dataUpdatedSignal.connect(lambda w, s, t, i, p: received_packets.append((w, s, t, i, p)))

        backend.start_luminescence(SHUTTERS[0], 0.02, 5, 0.05)
        # Simular 5 pasos de adquisición
        for _ in range(5):
            backend._step()

        self.assertGreaterEqual(len(received_packets), 5)
        last_wave, last_spec, last_t, last_i, progress = received_packets[-1]
        self.assertEqual(len(last_wave), 1004)
        self.assertEqual(len(last_spec), 1004)
        self.assertEqual(len(last_t), 5)
        self.assertEqual(len(last_i), 5)
        self.assertEqual(progress, 100)

        # I(t) debe ser positiva
        self.assertTrue(np.all(last_i > 0))
        backend.stop_luminescence()

    def test_growth_kinetics_routine_spr_tracking(self):
        """Verifica que la rutina de cinética de crecimiento ajuste la resonancia SPR en cada frame."""
        widget = GrowthKineticsWidget()
        backend = GrowthKineticsBackend(self.camera, self.spectrometer)
        backend.make_connection(widget)

        results = []
        backend.growthUpdatedSignal.connect(
            lambda w, s, wf, sf, t, lm_axis, lmax, p: results.append((lmax, p))
        )

        backend.start_growth(SHUTTERS[1], 0.02, 3, 0.05)
        for _ in range(3):
            backend._step()

        self.assertEqual(len(results), 3)
        for lmax, p in results:
            self.assertGreaterEqual(lmax, 400.0)
            self.assertLessEqual(lmax, 900.0)
        backend.stop_growth()

    def test_dimers_routine_polarization_subtraction(self):
        """Verifica la medición de polarización paralela/perpendicular y el cálculo de diferencia (∥ - ⟂)."""
        widget = DimersWidget()
        backend = DimersBackend(self.camera, self.spectrometer)
        backend.make_connection(widget)

        emitted_diffs = []
        backend.dimerDataSignal.connect(lambda mode, w, s, diff: emitted_diffs.append((mode, diff)))

        # 1. Polarización paralela
        backend.acquire_polarization("parallel", 0.05)
        self.assertEqual(emitted_diffs[-1][0], "parallel")
        self.assertEqual(len(emitted_diffs[-1][1]), 0)  # Aún no hay perpendicular para restar

        # 2. Polarización perpendicular
        backend.acquire_polarization("perpendicular", 0.05)
        self.assertEqual(emitted_diffs[-1][0], "perpendicular")
        diff_spectrum = emitted_diffs[-1][1]
        self.assertEqual(len(diff_spectrum), 1004)
        self.assertFalse(np.any(np.isnan(diff_spectrum)))

    def test_solis_ascii_and_npz_export_compatibility(self):
        """Verifica que la exportación de espectros respete los formatos estándar de Andor Solis."""
        be = step_and_glue.Backend(self.camera, self.spectrometer)
        be._last_wave = np.linspace(500.0, 600.0, 100)
        be._last_spec = np.random.rand(100) * 500.0 + 100.0
        be._last_norm = be._last_spec / 500.0

        with tempfile.TemporaryDirectory() as tmpdir:
            # 1. Formato ASCII (.txt con tabulaciones)
            txt_path = Path(tmpdir) / "solis_test.txt"
            be.save_spectrum(str(txt_path))
            self.assertTrue(txt_path.exists())

            # Validar encabezado y lectura
            with open(txt_path, "r", encoding="utf-8") as f:
                header = f.readline()
                self.assertIn("Wavelength_nm", header)
                self.assertIn("Intensity_Counts", header)
                self.assertIn("Normalized_Intensity", header)

            loaded_ascii = np.loadtxt(txt_path)
            self.assertEqual(loaded_ascii.shape, (100, 3))
            np.testing.assert_allclose(loaded_ascii[:, 0], be._last_wave)

            # 2. Formato NumPy comprimido (.npz)
            npz_path = Path(tmpdir) / "solis_test.npz"
            be.save_spectrum(str(npz_path))
            self.assertTrue(npz_path.exists())
            with np.load(npz_path) as data:
                self.assertIn("wavelength", data)
                self.assertIn("intensity", data)
                self.assertIn("normalized", data)
                self.assertEqual(len(data["wavelength"]), 100)


class TestPySpectrumSafety(unittest.TestCase):
    """Pruebas de salvaguardas de seguridad física: láseres, watchdog, platina y detector."""

    def setUp(self):
        self.camera = get_andor_ccd(force_mock=True)
        self.spectrometer = get_shamrock(force_mock=True)
        hardware_session.clear_emergency()
        if hardware_session.is_busy:
            hardware_session.release_session(hardware_session.current_owner)
        close_all_shutters()

    def tearDown(self):
        hardware_session.clear_emergency()
        if hardware_session.is_busy:
            hardware_session.release_session(hardware_session.current_owner)
        close_all_shutters()

    def test_shutter_failsafe_on_routine_lifecycle(self):
        """Verifica que las rutinas espectrales abran el obturador al iniciar y lo cierren sin falta al detenerse."""
        l_be = LuminescenceBackend(self.camera, self.spectrometer)
        laser = SHUTTERS[0]

        # Estado inicial cerrado
        idx = SHUTTERS.index(laser)
        self.assertEqual(nidaq._shutter_signal[idx], not SHUTTER_POLARITY[laser])

        # Inicio -> Debe abrirse
        l_be.start_luminescence(laser, 0.05, 10, 0.1)
        self.assertEqual(nidaq._shutter_signal[idx], SHUTTER_POLARITY[laser])

        # Detención normal -> Debe cerrarse
        l_be.stop_luminescence()
        self.assertEqual(nidaq._shutter_signal[idx], not SHUTTER_POLARITY[laser])

    def test_heartbeat_watchdog_renewed_during_acquisition(self):
        """Verifica que se arme el watchdog al abrir obturador y se desarme al cerrar."""
        heartbeat_shutter(30.0)
        self.assertTrue(is_watchdog_armed())
        rem = get_watchdog_remaining_time()
        self.assertIsNotNone(rem)
        self.assertGreater(rem, 25.0)
        self.assertLessEqual(rem, 30.0)

        close_all_shutters()
        self.assertFalse(is_watchdog_armed())
        self.assertIsNone(get_watchdog_remaining_time())

    def test_window_close_failsafe_shutter_sweep(self):
        """Verifica que el cierre de la ventana principal ejecute barrido fail-safe (close_all_shutters)."""
        # Abrir intencionalmente todos los shutters
        for s in SHUTTERS:
            open_shutter(s)

        orig_question = QtWidgets.QMessageBox.question
        QtWidgets.QMessageBox.question = lambda *a, **k: QtWidgets.QMessageBox.StandardButton.Yes
        try:
            win = PySpectrumWindow()
            win.close()
            # Todos los shutters deben haber sido forzados a cerrar
            for s in SHUTTERS:
                idx = SHUTTERS.index(s)
                self.assertEqual(nidaq._shutter_signal[idx], not SHUTTER_POLARITY[s])
            self.assertFalse(is_watchdog_armed())
        finally:
            QtWidgets.QMessageBox.question = orig_question

    def test_piezo_stage_bounds_protection(self):
        """Verifica que las coordenadas del escaneo confocal hiperespectral se clampeen a [0.0, 100.0] µm."""
        c_be = hyperspectral_confocal.Backend(self.camera, self.spectrometer)
        # Intentar valores peligrosamente fuera de rango: -30 µm a 160 µm
        c_be.start_scan(xmin=-30.0, xmax=160.0, ymin=-10.0, ymax=115.0, step=10.0, exp_time=0.01)

        self.assertGreaterEqual(c_be.xs[0], 0.0, "Coordenada X mínima menor a 0.0 µm")
        self.assertLessEqual(c_be.xs[-1], 100.0, "Coordenada X máxima mayor a 100.0 µm")
        self.assertGreaterEqual(c_be.ys[0], 0.0, "Coordenada Y mínima menor a 0.0 µm")
        self.assertLessEqual(c_be.ys[-1], 100.0, "Coordenada Y máxima mayor a 100.0 µm")
        c_be.stop_scan()

    def test_emccd_gain_clamping_and_visual_alerts(self):
        """Verifica alertas visuales de ganancia EM (>200x y >300x) y desacoplamiento en modo convencional."""
        cam_ui = camera_andor.Frontend()

        # 1. Régimen seguro (<200)
        cam_ui.slider_gain.setValue(100)
        self.assertIn("100x", cam_ui.lbl_gain_badge.text())
        self.assertNotIn("⚠️", cam_ui.lbl_gain_badge.text())
        self.assertNotIn("🔥", cam_ui.lbl_gain_badge.text())

        # 2. Alerta moderada (200 a 300)
        cam_ui.slider_gain.setValue(250)
        self.assertIn("250x", cam_ui.lbl_gain_badge.text())
        self.assertIn("⚠️", cam_ui.lbl_gain_badge.text())

        # 3. Alerta crítica (>300)
        cam_ui.slider_gain.setValue(450)
        self.assertIn("450x", cam_ui.lbl_gain_badge.text())
        self.assertIn("🔥", cam_ui.lbl_gain_badge.text())

        # 4. Modo convencional desactiva ganancia EM
        cam_ui.cmb_amp.setCurrentIndex(1)
        self.assertFalse(cam_ui.slider_gain.isEnabled())
        self.assertFalse(cam_ui.spin_gain.isEnabled())
        self.assertIn("N/A", cam_ui.lbl_gain_badge.text())

        # 5. Clampeo del driver mock a [0, 1000]
        self.camera.set_emccd_gain(1500)
        self.assertEqual(self.camera.get_emccd_gain(), 1000)
        self.camera.set_emccd_gain(-50)
        self.assertEqual(self.camera.get_emccd_gain(), 0)

    def test_hardware_session_arbitration_and_mutual_exclusion(self):
        """Verifica que el Árbitro Central de Hardware impida colisiones de rutinas simultáneas."""
        # 1. Rutina A adquiere sesión
        res_a = hardware_session.acquire_session("Rutina Alpha")
        self.assertTrue(res_a)
        self.assertEqual(hardware_session.current_owner, "Rutina Alpha")
        self.assertTrue(hardware_session.is_busy)

        # 2. Rutina B intenta adquirir sesión simultáneamente -> Rechazada
        res_b = hardware_session.acquire_session("Rutina Beta")
        self.assertFalse(res_b)
        self.assertEqual(hardware_session.current_owner, "Rutina Alpha")

        # 3. Rutina A libera sesión
        hardware_session.release_session("Rutina Alpha")
        self.assertFalse(hardware_session.is_busy)
        self.assertEqual(hardware_session.current_owner, "")

        # 4. Ahora Rutina B puede adquirir sesión
        res_b2 = hardware_session.acquire_session("Rutina Beta")
        self.assertTrue(res_b2)
        self.assertEqual(hardware_session.current_owner, "Rutina Beta")
        hardware_session.release_session("Rutina Beta")

    def test_hardware_session_auto_pause_live(self):
        """Verifica que iniciar una rutina batch pause automáticamente los modos Live registrados."""
        live_paused = [False]
        def dummy_pause():
            live_paused[0] = True

        hardware_session.register_live_controller("TestLive", dummy_pause)
        self.assertFalse(live_paused[0])

        # Adquirir sesión de rutina batch
        res = hardware_session.acquire_session("Batch Test", auto_pause_live=True)
        self.assertTrue(res)
        self.assertTrue(live_paused[0], "El modo Live no fue pausado automáticamente")
        hardware_session.release_session("Batch Test")

    def test_photoflux_gain_clamping_safety(self):
        """
        Regla de Fotoflux:
        Impedir que la ganancia EM supere 5x si el tiempo de exposición es superior a 1.0 s.
        """
        # Caso 1: Exposición corta (<= 1.0s) permite ganancia alta
        self.camera.set_exposure_time(0.2)
        self.camera.set_emccd_gain(150)
        self.assertEqual(self.camera.get_emccd_gain(), 150)

        # Caso 2: Exposición > 1.0s clampea ganancia existente a <= 5x
        self.camera.set_exposure_time(2.0)
        self.assertLessEqual(self.camera.get_emccd_gain(), 5)

        # Caso 3: Intentar setear ganancia > 5x con exposición > 1.0s se rechaza/clampea a 5
        self.camera.set_emccd_gain(200)
        self.assertEqual(self.camera.get_emccd_gain(), 5)

        # Caso 4: Regresar a exposición corta permite nuevamente setear ganancia alta
        self.camera.set_exposure_time(0.5)
        self.camera.set_emccd_gain(80)
        self.assertEqual(self.camera.get_emccd_gain(), 80)

    def test_zero_order_interlock_detector_safeguard(self):
        """
        Interlock de Orden Cero:
        Al posicionar 0.0 nm (o modo espejo), fuerza ganancia EM a 0 y cierra todos los obturadores láser.
        """
        fe = spectrum_control.Frontend()
        be = spectrum_control.Backend(self.spectrometer)
        be.make_connection(fe)

        # Configurar detector con ganancia EM alta y un obturador abierto
        self.camera.set_exposure_time(0.1)
        self.camera.set_emccd_gain(250)
        laser = SHUTTERS[0]
        open_shutter(laser)
        self.assertEqual(self.camera.get_emccd_gain(), 250)
        self.assertEqual(nidaq._shutter_signal[SHUTTERS.index(laser)], SHUTTER_POLARITY[laser])

        # Solicitar 0.0 nm
        be.set_wavelength(0.0)

        # Interlock de Orden Cero debe haberse activado
        self.assertEqual(self.camera.get_emccd_gain(), 0, "La ganancia EM no fue forzada a 0 en orden cero")
        for s in SHUTTERS:
            idx = SHUTTERS.index(s)
            self.assertEqual(nidaq._shutter_signal[idx], not SHUTTER_POLARITY[s], f"Obturador {s} no se cerró en orden cero")

    def test_shamrock_mechanical_settling_times_and_locks(self):
        """Verifica que el espectrógrafo Shamrock tenga tiempos de asentamiento y sincronización de hilos."""
        # Constantes de asentamiento físico
        self.assertEqual(GRATING_SETTLING_TIME_S, 4.0)
        self.assertEqual(SLIT_SETTLING_TIME_S, 0.8)
        self.assertEqual(WAVELENGTH_SETTLING_TIME_S, 0.3)

        # Métodos de sincronización
        self.assertTrue(hasattr(self.spectrometer, "is_moving"))
        self.assertTrue(hasattr(self.spectrometer, "wait_until_ready"))

        # Movimiento de red y verificación de estado
        self.spectrometer.ShamrockSetGrating(DEVICE, 2)
        self.assertFalse(self.spectrometer.is_moving())  # En mock avanza en simulación inmediata

    def test_global_estop_execution_and_reset(self):
        """Verifica el funcionamiento de la PARADA DE EMERGENCIA (E-STOP) global y su rearmado."""
        # 1. Abrir láser y verificar estado inicial
        open_shutter(SHUTTERS[0])
        self.assertEqual(nidaq._shutter_signal[0], SHUTTER_POLARITY[SHUTTERS[0]])
        self.assertFalse(hardware_session.is_emergency_stopped)

        # 2. Ejecutar E-STOP
        hardware_session.emergency_stop()
        self.assertTrue(hardware_session.is_emergency_stopped)

        # Todos los shutters deben haberse cerrado de inmediato
        for s in SHUTTERS:
            idx = SHUTTERS.index(s)
            self.assertEqual(nidaq._shutter_signal[idx], not SHUTTER_POLARITY[s])

        # Intentar iniciar una rutina bajo E-STOP activo debe ser rechazado
        self.assertFalse(hardware_session.acquire_session("Test Under E-Stop"))

        # 3. Rearmar el sistema
        hardware_session.clear_emergency()
        self.assertFalse(hardware_session.is_emergency_stopped)

        # Ahora sí se puede adquirir sesión
        self.assertTrue(hardware_session.acquire_session("Test After Reset"))
        hardware_session.release_session("Test After Reset")

    def test_mock_hardware_isolation_safety(self):
        """Verifica que en SAFE_MODE los drivers mock informen is_mock=True y no invoquen DLLs nativas."""
        self.assertTrue(config.SAFE_MODE)
        self.assertTrue(self.camera.is_mock)
        self.assertTrue(self.spectrometer.is_mock)

        # Invocaciones típicas de hardware no deben causar segfaults ni FileNotFound de DLLs
        ret_temp = self.camera.set_temperature(-70.0)
        self.assertEqual(ret_temp, DRV_SUCCESS)
        ret_wl = self.spectrometer.ShamrockSetWavelength(DEVICE, 532.0)
        self.assertEqual(ret_wl, 20202)  # SHAMROCK_SUCCESS

    def test_calibration_txt_persistence_roundtrip(self):
        """Verifica que CalibrationBackend guarde y cargue el archivo TXT con todos los campos y valores."""
        from pyspectrum.modules import calibration_dock
        import tempfile

        be = calibration_dock.CalibrationBackend(self.camera, self.spectrometer)
        fe = calibration_dock.CalibrationFrontend()
        be.make_connection(fe)

        # 1. Verificar carga inicial desde pyspectrum_calibration_last.txt
        self.assertAlmostEqual(be.slit_center_x, 502.00, places=1)
        self.assertEqual(be.slit_width, 50.0)
        self.assertEqual(be.grating_offsets[1], 12)
        self.assertEqual(be.grating_offsets[2], -35)
        self.assertEqual(be.detector_offset, 5)

        # 2. Modificar valores
        be.slit_center_x = 502.40
        be.slit_width = 75.0
        be.grating_offsets[1] = 20
        be.grating_offsets[2] = -40
        be.detector_offset = 8

        # 3. Guardar en archivo TXT temporal
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            save_ok = be.save_calibration_to_txt(tmp_path)
            self.assertTrue(save_ok)
            self.assertTrue(Path(tmp_path).exists())

            # 4. Crear nuevo backend y cargar desde el archivo temporal
            be2 = calibration_dock.CalibrationBackend(self.camera, self.spectrometer)
            load_ok = be2.load_calibration_from_txt(tmp_path)
            self.assertTrue(load_ok)
            self.assertAlmostEqual(be2.slit_center_x, 502.40, places=2)
            self.assertEqual(be2.slit_width, 75.0)
            self.assertEqual(be2.grating_offsets[1], 20)
            self.assertEqual(be2.grating_offsets[2], -40)
            self.assertEqual(be2.detector_offset, 8)
        finally:
            if Path(tmp_path).exists():
                Path(tmp_path).unlink(missing_ok=True)

    def test_ui_tooltips_completeness(self):
        """Verifica que todos los elementos PyQt útiles de PySpectrum tengan tooltips informativos."""
        from pyspectrum.modules import calibration_dock, spectrum_control, camera_andor, step_and_glue, static_raman

        # 1. CalibrationFrontend
        fe_calib = calibration_dock.CalibrationFrontend()
        self.assertTrue(len(fe_calib.btn_zero_order.toolTip()) > 10)
        self.assertTrue(len(fe_calib.spin_slit_width.toolTip()) > 10)
        self.assertTrue(len(fe_calib.btn_auto_slit.toolTip()) > 10)
        self.assertTrue(len(fe_calib.combo_grating.toolTip()) > 10)
        self.assertTrue(len(fe_calib.btn_save_calib_txt.toolTip()) > 10)
        self.assertTrue(len(fe_calib.btn_load_calib_txt.toolTip()) > 10)
        self.assertTrue(len(fe_calib.btn_reload_last.toolTip()) > 10)

        # 2. SpectrumFrontend
        fe_spec = spectrum_control.Frontend()
        self.assertTrue(len(fe_spec.cmb_grating.toolTip()) > 10)
        self.assertTrue(len(fe_spec.edit_wavelength.toolTip()) > 10)
        self.assertTrue(len(fe_spec.edit_slit.toolTip()) > 10)
        self.assertTrue(len(fe_spec.cmb_flipper_in.toolTip()) > 10)
        self.assertTrue(len(fe_spec.btn_shutter.toolTip()) > 10)
        self.assertTrue(len(fe_spec.btn_zero.toolTip()) > 10)

        # 3. CameraFrontend
        fe_cam = camera_andor.Frontend()
        self.assertTrue(len(fe_cam.btn_live.toolTip()) > 10)
        self.assertTrue(len(fe_cam.btn_cooler.toolTip()) > 10)
        self.assertTrue(len(fe_cam.spin_temp.toolTip()) > 10)
        self.assertTrue(len(fe_cam.edit_exp.toolTip()) > 10)
        self.assertTrue(len(fe_cam.cmb_amp.toolTip()) > 10)
        self.assertTrue(len(fe_cam.slider_gain.toolTip()) > 10)
        self.assertTrue(len(fe_cam.cmb_read_mode.toolTip()) > 10)
        self.assertTrue(len(fe_cam.chk_flip_y.toolTip()) > 10)

        # 4. StepGlueFrontend
        fe_sandg = step_and_glue.Frontend()
        self.assertTrue(len(fe_sandg.btn_single.toolTip()) > 10)
        self.assertTrue(len(fe_sandg.btn_sandg.toolTip()) > 10)
        self.assertTrue(len(fe_sandg.btn_stop.toolTip()) > 10)
        self.assertTrue(len(fe_sandg.chk_norm_lamp.toolTip()) > 10)
        self.assertTrue(len(fe_sandg.chk_fit_poly.toolTip()) > 10)

        # 5. StaticRamanWidget
        fe_raman = static_raman.StaticRamanWidget()
        self.assertTrue(len(fe_raman.cmb_laser.toolTip()) > 10)
        self.assertTrue(len(fe_raman.cmb_grating.toolTip()) > 10)
        self.assertTrue(len(fe_raman.cmb_mode.toolTip()) > 10)
        self.assertTrue(len(fe_raman.btn_apply_spectrometer.toolTip()) > 10)
        self.assertTrue(len(fe_raman.btn_single.toolTip()) > 10)
        self.assertTrue(len(fe_raman.btn_live.toolTip()) > 10)
        self.assertTrue(len(fe_raman.btn_save.toolTip()) > 10)

        # 6. HyperspectralConfocal Frontend
        from pyspectrum.modules import hyperspectral_confocal
        fe_confocal = hyperspectral_confocal.Frontend()
        self.assertTrue(len(fe_confocal.btn_scan.toolTip()) > 10)
        self.assertTrue(len(fe_confocal.edit_xmin.toolTip()) > 10)
        self.assertTrue(len(fe_confocal.edit_step.toolTip()) > 10)
        self.assertTrue(len(fe_confocal.edit_exp.toolTip()) > 10)
        self.assertTrue(len(fe_confocal.imv_map.toolTip()) > 10)
        self.assertTrue(len(fe_confocal.plot_point.toolTip()) > 10)


if __name__ == "__main__":
    unittest.main()
