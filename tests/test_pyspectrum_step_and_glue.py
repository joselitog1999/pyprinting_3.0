# -*- coding: utf-8 -*-
"""
test_pyspectrum_step_and_glue.py — Step & Glue Espectral Avanzado (Fase 4)
PySpectrum 3.0 — UNSAM Nanofotónica

Verifica el algoritmo de cosido raised-cosine (continuidad, w1+w2=1), el cálculo de centros
espectrales según la dispersión real de la red activa (20% por defecto y solapamiento
personalizado), la ejecución secuencial con mocks de Shamrock/Andor, la cancelación anticipada
resiliente (entrega de cosido parcial), la normalización por lámpara halógena y la exportación
TXT/HDF5.
"""
from __future__ import annotations
import os
import sys
import tempfile
import shutil
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

os.environ["PYPRINTING_SAFE"] = "1"
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import numpy as np
from PyQt6 import QtWidgets
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

from pyspectrum.drivers.andor_ccd_driver import get_andor_ccd, READ_MODE_FVB, READ_MODE_IMAGE
from pyspectrum.drivers.shamrock_driver import get_shamrock, DEVICE, GRATING_150_LINES, GRATING_1200_LINES
from pyspectrum.calibration.halogen_lamp import (
    raised_cosine_weights, glue_pair_sigmoidal, sigmoidal_step_and_glue, sigmoidal_step_and_glue_2d,
    compute_step_centers, export_step_and_glue_to_hdf5, H5PY_AVAILABLE, HalogenLampCalibration,
)
from pyspectrum.modules.step_and_glue import Frontend, Backend
from pyspectrum.modules.hardware_session import hardware_session

if H5PY_AVAILABLE:
    import h5py


class TestRaisedCosineWeights(unittest.TestCase):
    """1. Test matemático del blending sigmoidal: continuidad estricta y w1+w2=1.0."""

    def test_weights_sum_to_one_everywhere(self):
        wl = np.linspace(400.0, 700.0, 2001)
        w1, w2 = raised_cosine_weights(wl, 500.0, 600.0)
        np.testing.assert_allclose(w1 + w2, 1.0, atol=1e-12)

    def test_weights_are_endpoints_exact(self):
        wl = np.array([500.0, 600.0])
        w1, w2 = raised_cosine_weights(wl, 500.0, 600.0)
        self.assertAlmostEqual(w1[0], 1.0, places=10)
        self.assertAlmostEqual(w2[0], 0.0, places=10)
        self.assertAlmostEqual(w1[1], 0.0, places=10)
        self.assertAlmostEqual(w2[1], 1.0, places=10)

    def test_weights_monotonic_across_overlap(self):
        wl = np.linspace(500.0, 600.0, 200)
        w1, w2 = raised_cosine_weights(wl, 500.0, 600.0)
        self.assertTrue(np.all(np.diff(w1) <= 1e-12))  # w1 no creciente
        self.assertTrue(np.all(np.diff(w2) >= -1e-12))  # w2 no decreciente

    def test_glued_spectrum_is_continuous_no_steps(self):
        """Une dos espectros constantes distintos y verifica que la transición sea suave
        (sin escalón abrupto) dentro de la región de solapamiento."""
        wave1 = np.linspace(400.0, 600.0, 1000)
        wave2 = np.linspace(550.0, 750.0, 1000)
        spec1 = np.full(1000, 100.0)
        spec2 = np.full(1000, 200.0)  # salto grande entre pasos

        gw, gs = glue_pair_sigmoidal(wave1, spec1, wave2, spec2)
        self.assertTrue(np.all(np.diff(gw) > 0))

        # Dentro del solapamiento [550, 600], el máximo salto punto a punto debe ser mucho
        # menor que el salto abrupto (100 cts) que produciría una unión sin blending.
        mask_overlap = (gw >= 551.0) & (gw <= 599.0)
        deltas = np.abs(np.diff(gs[mask_overlap]))
        self.assertLess(np.max(deltas), 5.0)

    def test_glue_pair_no_overlap_concatenates_cleanly(self):
        wave1 = np.linspace(400.0, 500.0, 100)
        wave2 = np.linspace(600.0, 700.0, 100)
        spec1 = np.full(100, 10.0)
        spec2 = np.full(100, 20.0)
        # edge_crop_pixels=0: aísla la lógica de concatenación sin la confusión del recorte de
        # borde (verificado por separado en TestEdgeCropAndOpticalCoreAndSubstrate).
        gw, gs = glue_pair_sigmoidal(wave1, spec1, wave2, spec2, edge_crop_pixels=0)
        self.assertEqual(len(gw), 200)
        self.assertTrue(np.all(np.diff(gw) > 0))

    def test_sequential_n_step_glue_matches_pairwise_chaining(self):
        w1 = np.linspace(400, 500, 300); s1 = np.full(300, 10.0)
        w2 = np.linspace(470, 570, 300); s2 = np.full(300, 20.0)
        w3 = np.linspace(540, 640, 300); s3 = np.full(300, 15.0)

        gw_all, gs_all = sigmoidal_step_and_glue([w1, w2, w3], [s1, s2, s3])
        gw_12, gs_12 = glue_pair_sigmoidal(w1, s1, w2, s2)
        gw_expected, gs_expected = glue_pair_sigmoidal(gw_12, gs_12, w3, s3)

        np.testing.assert_allclose(gw_all, gw_expected)
        np.testing.assert_allclose(gs_all, gs_expected)


class TestStepCenterCalculation(unittest.TestCase):
    """2. Test de cálculo de pasos con 20% default y con solapamiento personalizado."""

    def test_default_20_percent_overlap_grating_150(self):
        centers = compute_step_centers(450.0, 950.0, 0.20, grating=1)
        self.assertGreater(len(centers), 1)
        self.assertLessEqual(centers[0] - 90.0, 450.0)  # cubre el inicio del rango pedido

    def test_custom_30_percent_overlap_packs_steps_denser(self):
        # Más solapamiento acorta el paso; el NÚMERO de ventanas es una discretización y puede
        # coincidir (con la ventana real de 103 nm, 20 % y 30 % dan 7 en 450-950 nm). La
        # versión anterior exigía "más ventanas", que sólo valía con la ventana errónea de
        # 176 nm (DEC-033).
        centers_20 = compute_step_centers(450.0, 950.0, 0.20, grating=1)
        centers_30 = compute_step_centers(450.0, 950.0, 0.30, grating=1)
        self.assertLess(np.diff(centers_30)[0], np.diff(centers_20)[0])
        self.assertGreaterEqual(len(centers_30), len(centers_20))

    def test_grating_1200_needs_many_more_steps_than_grating_150(self):
        centers_150 = compute_step_centers(450.0, 950.0, 0.20, grating=1)
        centers_1200 = compute_step_centers(450.0, 950.0, 0.20, grating=2)
        self.assertGreater(len(centers_1200), len(centers_150) * 3)

    def test_centers_cover_full_requested_range(self):
        centers = compute_step_centers(500.0, 700.0, 0.20, grating=1)
        self.assertLessEqual(min(centers), 700.0)
        self.assertGreaterEqual(max(centers), 500.0)

    def test_overlap_out_of_bounds_clamped_not_raising(self):
        centers = compute_step_centers(450.0, 950.0, 5.0, grating=1)  # 500% -> clampeado
        self.assertGreater(len(centers), 0)


class TestSequentialExecutionWithMocks(unittest.TestCase):
    """3. Test de ejecución secuencial con Mock del Shamrock y Cámara Andor."""

    def setUp(self):
        # hardware_session es un singleton de proceso: un test anterior que cierre una
        # PySpectrumWindow real (closeEvent -> emergency_stop()) deja el E-STOP activo para el
        # resto de la suite si no se limpia aquí (mismo patrón defensivo ya establecido en
        # test_pyspectrum_stability_safety.py::TestPySpectrumStability.tearDown).
        hardware_session.clear_emergency()
        self.camera = get_andor_ccd(force_mock=True)
        self.spectrometer = get_shamrock(force_mock=True)
        self.camera.set_read_mode(READ_MODE_FVB)
        self.fe = Frontend()
        self.be = Backend(self.camera, self.spectrometer)
        self.be.make_connection(self.fe)

    def test_full_step_and_glue_run_emits_progress_and_final_spectrum(self):
        progress_calls = []
        self.be.stepProgressSignal.connect(lambda i, n, wl: progress_calls.append((i, n, wl)))
        finished = []
        self.be.spectrumFinishedSignal.connect(lambda *args: finished.append(args))

        self.be.measure_step_and_glue(450.0, 700.0, 0.20, 0.05, normalize=False, check_water=False)

        self.assertGreater(len(progress_calls), 0)
        self.assertEqual(len(finished), 1)
        glued_w, glued_s, norm_w, norm_s, lambda_max = finished[0]
        self.assertGreater(len(glued_w), 0)
        self.assertTrue(np.all(np.diff(glued_w) > 0))

    def test_progress_reports_correct_step_count(self):
        progress_calls = []
        self.be.stepProgressSignal.connect(lambda i, n, wl: progress_calls.append((i, n, wl)))
        self.be.measure_step_and_glue(450.0, 700.0, 0.20, 0.05, normalize=False, check_water=False)
        expected_n = progress_calls[0][1]
        self.assertEqual([c[0] for c in progress_calls], list(range(1, expected_n + 1)))

    def test_2d_image_mode_glues_full_frame(self):
        self.camera.set_read_mode(READ_MODE_IMAGE)
        self.be.measure_step_and_glue(450.0, 650.0, 0.20, 0.05, normalize=False, check_water=False)
        self.assertIsNotNone(self.be._last_frame_2d)
        self.assertEqual(self.be._last_frame_2d.shape[0], self.camera.height)
        self.assertEqual(self.be._last_frame_2d.shape[1], len(self.be._last_wave))


class TestResilientCancellation(unittest.TestCase):
    """4. Test de cancelación anticipada (verificar entrega de cosido parcial sin errores)."""

    def setUp(self):
        hardware_session.clear_emergency()
        self.camera = get_andor_ccd(force_mock=True)
        self.spectrometer = get_shamrock(force_mock=True)
        self.camera.set_read_mode(READ_MODE_FVB)
        self.fe = Frontend()
        self.be = Backend(self.camera, self.spectrometer)
        self.be.make_connection(self.fe)

    def test_abort_after_first_step_keeps_the_window_and_glues_only_on_request(self):
        # Paso 11 (Ronda 3 §4.3): un barrido incompleto no se cose solo; las ventanas quedan en disco y
        # [Coser lo adquirido] las cose a pedido, rotuladas como incompletas.
        planned_n = {"n": None}

        def _maybe_abort(i, n, wl):
            planned_n["n"] = n
            if i >= 1:
                self.be._abort_requested = True

        self.be.stepProgressSignal.connect(_maybe_abort)
        finished = []
        self.be.spectrumFinishedSignal.connect(lambda *args: finished.append(args))

        try:
            self.be.measure_step_and_glue(450.0, 950.0, 0.20, 0.05, normalize=False, check_water=False)
        except Exception as e:
            self.fail(f"measure_step_and_glue lanzó una excepción tras cancelación: {e}")

        self.assertEqual(finished, [])
        self.assertGreater(planned_n["n"], 1)
        self.assertEqual(len(self.be._raw_wave_steps), 1)
        self.assertFalse(self.be.last_result.complete)
        self.assertTrue(self.be.last_result.windows[0].path.exists())

        self.be.glue_acquired()
        self.assertEqual(len(finished), 1)
        self.assertGreater(len(finished[0][0]), 0)

    def test_stop_measurement_sets_abort_flag(self):
        self.be._abort_requested = False
        self.fe.stopMeasurementSignal.emit()
        self.assertTrue(self.be._abort_requested)


class TestHalogenNormalization(unittest.TestCase):
    """5. Test de normalización por lámpara halógena."""

    def setUp(self):
        hardware_session.clear_emergency()
        self.camera = get_andor_ccd(force_mock=True)
        self.spectrometer = get_shamrock(force_mock=True)
        self.camera.set_read_mode(READ_MODE_FVB)
        self.fe = Frontend()
        self.be = Backend(self.camera, self.spectrometer)
        self.be.make_connection(self.fe)

    def test_normalize_flag_produces_normalized_output(self):
        finished = []
        self.be.spectrumFinishedSignal.connect(lambda *args: finished.append(args))
        self.be.measure_step_and_glue(450.0, 700.0, 0.20, 0.05, normalize=True, check_water=False)
        glued_w, glued_s, norm_w, norm_s, lambda_max = finished[0]
        self.assertGreater(len(norm_w), 0)
        self.assertEqual(len(norm_w), len(norm_s))
        # La normalización divide por un perfil de lámpara no trivial: el resultado no debe
        # ser idéntico al espectro crudo.
        self.assertFalse(np.allclose(norm_s, glued_s))

    def test_lamp_calibration_normalize_matches_direct_division(self):
        lamp = HalogenLampCalibration()
        wave = np.linspace(500.0, 600.0, 50)
        spec = np.full(50, 1000.0)
        normalized = lamp.normalize_spectrum(wave, spec)
        lamp_interp = np.interp(wave, lamp.wave_lamp, lamp.spec_lamp)
        lamp_interp = np.where(lamp_interp <= 0, 1.0, lamp_interp)
        np.testing.assert_allclose(normalized, spec / lamp_interp)

    def test_2d_mode_normalization_broadcasts_row_wise(self):
        self.camera.set_read_mode(READ_MODE_IMAGE)
        finished = []
        self.be.spectrumFinishedSignal.connect(lambda *args: finished.append(args))
        self.be.measure_step_and_glue(450.0, 650.0, 0.20, 0.05, normalize=True, check_water=False)
        self.assertIsNotNone(self.be._last_frame_2d)  # matriz cruda cacheada, no la normalizada
        glued_w, glued_s, norm_w, norm_s, lambda_max = finished[0]
        self.assertEqual(len(norm_s), len(glued_w))


class TestExport(unittest.TestCase):
    """6. Test de exportación a HDF5 y TXT."""

    def setUp(self):
        hardware_session.clear_emergency()
        self.camera = get_andor_ccd(force_mock=True)
        self.spectrometer = get_shamrock(force_mock=True)
        self.camera.set_read_mode(READ_MODE_FVB)
        self.fe = Frontend()
        self.be = Backend(self.camera, self.spectrometer)
        self.be.make_connection(self.fe)
        self.be.measure_step_and_glue(450.0, 700.0, 0.20, 0.05, normalize=True, check_water=False)
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_save_spectrum_txt(self):
        path = os.path.join(self.tmp_dir, "glued.txt")
        self.be.save_spectrum(path)
        self.assertTrue(os.path.isfile(path))
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("Wavelength_nm", content)
        self.assertIn("Normalized_Intensity", content)

    def test_save_spectrum_npz(self):
        path = os.path.join(self.tmp_dir, "glued.npz")
        self.be.save_spectrum(path)
        self.assertTrue(os.path.isfile(path))
        data = np.load(path)
        self.assertIn("wavelength", data)
        self.assertIn("intensity", data)

    @unittest.skipUnless(H5PY_AVAILABLE, "h5py no disponible en este entorno")
    def test_export_hdf5_structure(self):
        path = os.path.join(self.tmp_dir, "glued.h5")
        self.be.export_hdf5(path)
        self.assertTrue(os.path.isfile(path))
        with h5py.File(path, "r") as f:
            self.assertIn("glued_spectrum", f)
            self.assertIn("wavelengths", f)
            self.assertIn("raw_steps", f)
            self.assertGreater(len(f["raw_steps"].keys()), 0)
            self.assertIn("grating", f.attrs)
            self.assertIn("slit_width_um", f.attrs)
            self.assertIn("timestamp", f.attrs)

    def test_export_hdf5_function_direct_with_raw_steps(self):
        path = os.path.join(self.tmp_dir, "direct.h5")
        wave_steps = [np.linspace(400, 500, 100), np.linspace(480, 580, 100)]
        spec_steps = [np.full(100, 1.0), np.full(100, 2.0)]
        gw, gs = sigmoidal_step_and_glue(wave_steps, spec_steps)
        result_path = export_step_and_glue_to_hdf5(path, gw, gs, wave_steps, spec_steps, {"grating": 1})
        self.assertEqual(result_path, path)
        if H5PY_AVAILABLE:
            with h5py.File(path, "r") as f:
                self.assertEqual(len(f["raw_steps"].keys()), 2)
                self.assertEqual(f.attrs["n_steps"], 2)


class TestFrontendUI(unittest.TestCase):
    """Verifica el SpinBox de solapamiento 10-50% y la señal extendida con check_water."""

    def setUp(self):
        self.fe = Frontend()

    def test_overlap_spinbox_range_and_default(self):
        self.assertEqual(self.fe.spin_overlap_pct.minimum(), 10)
        self.assertEqual(self.fe.spin_overlap_pct.maximum(), 50)
        self.assertEqual(self.fe.spin_overlap_pct.value(), 20)

    def test_sandg_measure_emits_overlap_fraction_and_water_flag(self):
        received = []
        self.fe.measureStepGlueSignal.connect(lambda *args: received.append(args))
        self.fe.spin_overlap_pct.setValue(30)
        self.fe.chk_fit_raman.setChecked(True)
        from core.nidaq import confirm_detection_mirror_belief
        confirm_detection_mirror_belief("down")      # si no, el diálogo del espejo (paso 11) pregunta
        self.fe.edit_start_wl.setValue(450.0)
        self.fe.edit_end_wl.setValue(950.0)
        self.fe.edit_exp.setValue(0.1)
        self.fe._on_sandg_measure()
        start, end, overlap_pct, exp, norm, check_water, use_optical_core, subtract_substrate = received[-1]
        self.assertAlmostEqual(overlap_pct, 0.30)
        self.assertTrue(check_water)
        self.assertFalse(use_optical_core)
        self.assertFalse(subtract_substrate)

    def test_progress_bar_updates_from_signal(self):
        self.fe.update_progress(2, 5, 532.5)
        self.assertEqual(self.fe.progress_bar.value(), 2)
        self.assertEqual(self.fe.progress_bar.maximum(), 5)
        self.assertIn("532.5", self.fe.progress_bar.format())


class TestEdgeCropOpticalCoreAndSubstrate(unittest.TestCase):
    """Corrección de alineación con legacy (StepandGlue_ps.py / Lampara_ps.py, Luciana/CIBION):
    recorte de 15 px de borde por defecto, ventana óptica central 103/12 nm, y resta de fondo
    de sustrato fijado ("Lock Sustrato") antes de la normalización y el cosido."""

    def setUp(self):
        hardware_session.clear_emergency()
        self.camera = get_andor_ccd(force_mock=True)
        self.spectrometer = get_shamrock(force_mock=True)
        self.camera.set_read_mode(READ_MODE_FVB)
        self.fe = Frontend()
        self.be = Backend(self.camera, self.spectrometer)
        self.be.make_connection(self.fe)

    # ── 1. Recorte de 15 píxeles de borde ─────────────────────────────────

    def test_default_edge_crop_is_15_pixels_per_side(self):
        wave1 = np.arange(0.0, 100.0)  # 100 puntos, índice == valor
        wave2 = np.arange(80.0, 180.0)
        spec1 = np.full(100, 10.0)
        spec2 = np.full(100, 20.0)
        gw, gs = glue_pair_sigmoidal(wave1, spec1, wave2, spec2)  # default edge_crop_pixels=15
        # wave1 recortado: [15, 84]; wave2 recortado: [95, 164] -> unión final debe empezar en
        # 15 (no en 0) y terminar en 164 (no en 179).
        self.assertAlmostEqual(gw.min(), 15.0)
        self.assertAlmostEqual(gw.max(), 164.0)

    def test_edge_crop_zero_preserves_full_range(self):
        wave1 = np.arange(0.0, 100.0)
        wave2 = np.arange(80.0, 180.0)
        spec1 = np.full(100, 10.0)
        spec2 = np.full(100, 20.0)
        gw, gs = glue_pair_sigmoidal(wave1, spec1, wave2, spec2, edge_crop_pixels=0)
        self.assertAlmostEqual(gw.min(), 0.0)
        self.assertAlmostEqual(gw.max(), 179.0)

    def test_edge_crop_does_not_empty_short_arrays(self):
        # Array de 20 puntos con recorte de 15 por lado (30 total) sería vacío: debe
        # degradar con seguridad a "sin recorte" en vez de lanzar o perder datos.
        wave1 = np.linspace(0.0, 19.0, 20)
        wave2 = np.linspace(15.0, 34.0, 20)
        spec1 = np.full(20, 5.0)
        spec2 = np.full(20, 7.0)
        gw, gs = glue_pair_sigmoidal(wave1, spec1, wave2, spec2, edge_crop_pixels=15)
        self.assertGreater(len(gw), 0)

    def test_full_pipeline_edge_crop_reduces_range_vs_uncropped(self):
        centers_uncropped_w, centers_uncropped_s = sigmoidal_step_and_glue(
            [np.linspace(400, 500, 1004), np.linspace(470, 570, 1004)],
            [np.full(1004, 1.0), np.full(1004, 2.0)],
            edge_crop_pixels=0,
        )
        cropped_w, cropped_s = sigmoidal_step_and_glue(
            [np.linspace(400, 500, 1004), np.linspace(470, 570, 1004)],
            [np.full(1004, 1.0), np.full(1004, 2.0)],
            edge_crop_pixels=15,
        )
        self.assertGreater(centers_uncropped_w.max(), cropped_w.max())
        self.assertLess(centers_uncropped_w.min(), cropped_w.min())

    # ── 2. Ventana óptica central (103 nm / 12 nm) ────────────────────────

    # Con el pitch real de 8 µm, la ventana "central" del legado (103 / 12 nm) ES la ventana
    # completa (103.05 / 11.57 nm): el modo core ya no significa "más pasos", sólo "ventana fija
    # del legado en vez de la medida". Los tests verifican eso y no la premisa anterior, que
    # dependía de la ventana errónea de 176 / 22 nm (DEC-033).

    def test_optical_core_grating_150_uses_103nm_window(self):
        centers_core = compute_step_centers(450.0, 950.0, 0.20, grating=1, use_optical_core=True)
        np.testing.assert_allclose(np.diff(centers_core), 103.0 * 0.8)

    def test_optical_core_grating_1200_uses_12nm_window(self):
        centers_core = compute_step_centers(500.0, 520.0, 0.20, grating=2, use_optical_core=True)
        np.testing.assert_allclose(np.diff(centers_core), 12.0 * 0.8)

    def test_optical_core_flag_reaches_backend_step_calculation(self):
        self.camera.set_read_mode(READ_MODE_FVB)
        self.spectrometer.ShamrockSetGrating(0, 1)
        progress_calls = []
        self.be.stepProgressSignal.connect(lambda i, n, wl: progress_calls.append((n, wl)))

        self.be.measure_step_and_glue(450.0, 950.0, 0.20, 0.05, normalize=False, check_water=False, use_optical_core=True)
        self.assertEqual(self.be._last_window_source, "optical_core")
        self.assertEqual(self.be._last_window_nm, 103.0)
        expected = compute_step_centers(450.0, 950.0, 0.20, grating=1, use_optical_core=True)
        self.assertEqual(progress_calls[0][0], len(expected))
        np.testing.assert_allclose([wl for _, wl in progress_calls], expected)

        progress_calls.clear()
        self.be.measure_step_and_glue(450.0, 950.0, 0.20, 0.05, normalize=False, check_water=False, use_optical_core=False)
        self.assertEqual(self.be._last_window_source, "measured")

    # ── 3. Fijar y restar fondo de sustrato ───────────────────────────────

    def _processing_events_until_idle(self, timeout_s=30.0):
        import time
        from PyQt6.QtWidgets import QApplication
        t_end = time.monotonic() + timeout_s
        while self.be._thread is not None and time.monotonic() < t_end:
            QApplication.processEvents()
            time.sleep(0.01)

    def test_lock_substrate_stores_one_window_per_center(self):
        # R4-N, B4: el sustrato es un barrido completo con el mismo plan, una ventana por λc.
        self.assertIsNone(self.be.substrate)
        self.be.measure_substrate(450.0, 650.0, 0.20, 0.05)
        req, the_plan, _rep = self.be._prepare(450.0, 650.0, 0.20, 0.05, False, False)
        self.assertIsNotNone(self.be.substrate)
        self.assertEqual(len(self.be.substrate.windows), len(the_plan.centers))
        self.assertTrue(all(np.shape(v) == (1004,) for v in self.be.substrate.windows.values()))

    def test_lock_substrate_signal_from_frontend_reaches_backend(self):
        # El panel manda el plan actual; el barrido del sustrato corre en su hilo.
        self.fe._confirm_mirror = lambda: True
        self.fe.edit_start_wl.setValue(450.0)
        self.fe.edit_end_wl.setValue(650.0)
        self.fe._on_lock_substrate()
        self._processing_events_until_idle()
        self.assertIsNotNone(self.be.substrate)

    def test_subtract_substrate_removes_its_own_window_from_each_step(self):
        original_get_1d = self.camera.get_1d_spectrum
        try:
            self.camera.get_1d_spectrum = lambda: np.full(1004, 300.0)       # oscuro y sustrato: 300
            self.be.measure_substrate(450.0, 650.0, 0.20, 0.05)
            self.camera.get_1d_spectrum = lambda: np.full(1004, 1000.0)      # muestra: 1000
            self.be.measure_step_and_glue(450.0, 650.0, 0.20, 0.05, normalize=False, check_water=False,
                                          subtract_substrate=True)
        finally:
            self.camera.get_1d_spectrum = original_get_1d
        # Cada ventana menos el sustrato de su λc = 700 (el oscuro se cancela), no 1000.
        self.assertGreater(len(self.be._raw_spec_steps), 0)
        for step_spec in self.be._raw_spec_steps:
            np.testing.assert_allclose(step_spec, 700.0)

    def test_subtract_substrate_ignored_without_lock(self):
        # subtract_substrate=True pero nunca se fijó sustrato: no debe lanzar ni alterar datos.
        try:
            self.be.measure_step_and_glue(450.0, 650.0, 0.20, 0.05, normalize=False, check_water=False, subtract_substrate=True)
        except Exception as e:
            self.fail(f"measure_step_and_glue lanzó una excepción sin sustrato fijado: {e}")
        self.assertGreater(len(self.be._raw_spec_steps), 0)

    def test_subtract_substrate_shape_mismatch_does_not_raise(self):
        # Sustrato fijado en 2D pero el barrido corre en 1D: forma incompatible, debe
        # ignorarse con seguridad (no restar, no lanzar).
        from pyspectrum.modules.step_and_glue import Substrate
        req, the_plan, _rep = self.be._prepare(450.0, 650.0, 0.20, 0.05, False, False)
        self.be.substrate = Substrate(self.be._plan_key(req, the_plan),
                                      {round(c, 4): np.zeros((self.camera.height, self.camera.width))
                                       for c in the_plan.centers}, None, "")
        try:
            self.be.measure_step_and_glue(450.0, 650.0, 0.20, 0.05, normalize=False, check_water=False, subtract_substrate=True)
        except Exception as e:
            self.fail(f"measure_step_and_glue lanzó una excepción con forma de sustrato incompatible: {e}")
        self.assertGreater(len(self.be._raw_spec_steps), 0)


if __name__ == "__main__":
    unittest.main()
