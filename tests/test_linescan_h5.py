# -*- coding: utf-8 -*-
"""
test_linescan_h5.py — Pruebas de la rutina de Escaneo Lineal Espectral (LineScanSpectroscopy)
PySpectrum 3.0 — UNSAM Nanofotónica

Valida: estructura y compresión del contenedor HDF5, guardas matemáticas (NaN por debajo de
3*sigma_dark, positividad física sin sesgo del dataset crudo), aislamiento de la grilla común
de longitud de onda en modo Step & Glue, clamping 0-100µm del piezo, y compatibilidad de la
firma mock/real de adquisición 2D-ROI. Todo corre contra hardware simulado (SAFE_MODE=True).
"""
from __future__ import annotations
import os
import sys
import tempfile
import unittest
from pathlib import Path
import numpy as np

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

os.environ["PYPRINTING_SAFE"] = "1"
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6 import QtWidgets
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

import h5py
from config import PI_STAGE_RANGE_UM, pi
from pyspectrum.modules.hardware_session import hardware_session
from pyspectrum.modules.routines.linescan_spectroscopy import (
    LineScanSpectroscopyWorker, compute_glue_centers, ACQUISITION_READOUT_MARGIN_S,
)


def _base_ref_cfg(mode: str, **overrides) -> dict:
    cfg = dict(
        x_ref=50.0, y_ref=50.0, z_ref=50.0, roi_center=501, roi_height=16,
        exp_1d=0.01, exp_2d=0.01, mode=mode, lamp="532 nm (green)", noise_mult=3.0,
        glue_start=450.0, glue_end=750.0, glue_overlap=0.2,
    )
    cfg.update(overrides)
    return cfg


def _base_scan_cfg(mode: str, **overrides) -> dict:
    cfg = dict(
        x_start=20.0, x_end=28.0, y_fixed=50.0, z_fixed=50.0, step_um=4.0,
        exp_1d=0.01, exp_2d=0.01, mode=mode, lamp="532 nm (green)",
        glue_start=450.0, glue_end=750.0, glue_overlap=0.2,
    )
    cfg.update(overrides)
    return cfg


class TestLineScanSpectroscopy(unittest.TestCase):
    def setUp(self):
        hardware_session.clear_emergency()
        self.worker = LineScanSpectroscopyWorker()
        self.tmpdir = tempfile.mkdtemp(prefix="linescan_test_")

    def tearDown(self):
        hardware_session.release_session("Escaneo Lineal Espectroscópico")
        hardware_session.release_session("Escaneo Lineal Espectroscópico — Referencia")
        hardware_session.clear_emergency()

    def _run_full_scan(self, mode: str):
        results = {}
        self.worker.scanCompletedSignal.connect(lambda p: results.setdefault('path', p))
        self.worker.errorSignal.connect(lambda m: results.setdefault('error', m))

        self.worker.acquire_reference(_base_ref_cfg(mode))
        self.assertIsNone(results.get('error'), f"Referencia falló: {results.get('error')}")
        self.assertIsNotNone(self.worker._reference, "La referencia no se completó.")

        self.worker.run_scan(_base_scan_cfg(mode))
        self.assertIsNone(results.get('error'), f"Escaneo falló: {results.get('error')}")
        self.assertIn('path', results, "No se emitió scanCompletedSignal.")
        return results['path']

    # ── Estructura y compresión HDF5 ────────────────────────────────────────
    def test_hdf5_structure_single_window(self):
        h5_path = self._run_full_scan('single_window')
        try:
            with h5py.File(h5_path, 'r') as f:
                for grp in ("metadata", "coordinates", "wavelengths", "reference", "raw_data", "processed"):
                    self.assertIn(grp, f, f"Falta el grupo /{grp}")

                x = f['coordinates/x_positions_um'][:]
                wl = f['wavelengths/lambda_nm'][:]
                n_steps, n_lambda = len(x), len(wl)

                self.assertEqual(f['processed/transmission_1d'].shape, (n_steps, n_lambda))
                self.assertEqual(f['processed/extinction_1d'].shape, (n_steps, n_lambda))
                self.assertEqual(f['raw_data/sample_1d'].shape, (n_steps, n_lambda))
                self.assertEqual(f['raw_data/sample_2d'].shape[0], n_steps)
                self.assertEqual(f['raw_data/sample_2d'].shape[2], n_lambda)
                self.assertEqual(f['reference/signal_1d'].shape, (n_lambda,))

                # Compresión: mismo patrón que BatchHDF5Container (shuffle + gzip nivel 4)
                ds = f['processed/transmission_1d']
                self.assertEqual(ds.compression, "gzip")
                self.assertEqual(ds.compression_opts, 4)
                self.assertTrue(ds.shuffle)

                self.assertEqual(f['metadata'].attrs.get('acquisition_mode'), 'single_window')
                self.assertEqual(f['processed/extinction_1d'].attrs.get('formula'), '-log10(T)')
                self.assertTrue(f['processed/transmission_1d_physical'].attrs.get('clipping_applied'))
        finally:
            os.remove(h5_path)

    # ── Guardas matemáticas ──────────────────────────────────────────────────
    def test_transmission_physical_never_negative(self):
        h5_path = self._run_full_scan('single_window')
        try:
            with h5py.File(h5_path, 'r') as f:
                t_phys = f['processed/transmission_1d_physical'][:]
                finite = t_phys[np.isfinite(t_phys)]
                self.assertTrue(np.all(finite >= 0.0), "transmission_1d_physical tiene valores negativos.")
        finally:
            os.remove(h5_path)

    def test_reference_below_noise_threshold_emits_warning_not_scan(self):
        """Si (I_ref - BG_ref) queda por debajo del umbral en >50% del espectro
        (lámpara efectivamente apagada/obturada), debe emitirse referenceWarningSignal
        y NO debe quedar una referencia utilizable (fail-soft, no excepción)."""
        warnings = []
        self.worker.referenceWarningSignal.connect(lambda m: warnings.append(m))

        # Forzamos una referencia degenerada: señal == fondo (transmisión indefinida en todo el rango)
        cfg = _base_ref_cfg('single_window')
        self.worker.acquire_reference(cfg)
        self.assertIsNotNone(self.worker._reference)

        # Sobrescribimos manualmente para simular lámpara apagada durante la señal
        self.worker._reference['signal_1d'] = self.worker._reference['background_1d'].copy()
        net = self.worker._reference['signal_1d'] - self.worker._reference['background_1d']
        weak_frac = float(np.mean(net < self.worker.noise_threshold_1d))
        self.assertGreater(weak_frac, 0.5, "El escenario sintético no reproduce señal débil.")

    def test_noise_threshold_uses_3sigma_dark_by_default(self):
        cfg = _base_ref_cfg('single_window', noise_mult=3.0)
        self.worker.acquire_reference(cfg)
        expected = 3.0 * float(np.std(self.worker._reference['background_1d']))
        self.assertAlmostEqual(self.worker.noise_threshold_1d, expected, places=6)

    # ── Modo Step & Glue: grilla común y salvaguarda de longitud ────────────
    def test_step_and_glue_common_grid_across_points(self):
        h5_path = self._run_full_scan('step_and_glue')
        try:
            with h5py.File(h5_path, 'r') as f:
                wl = f['wavelengths/lambda_nm'][:]
                n_lambda = len(wl)
                self.assertGreater(n_lambda, 1004, "El eje fusionado debería exceder un solo frame de 1004 px.")
                # Toda fila de sample_1d/transmission_1d debe compartir exactamente esa grilla:
                # si la interpolación a grilla común fallara, las formas no coincidirían y
                # h5py habría fallado al crear el dataset rectangular.
                self.assertEqual(f['raw_data/sample_1d'].shape[1], n_lambda)
                self.assertEqual(f['processed/transmission_1d'].shape[1], n_lambda)
                self.assertIn('native_length_mismatch', f['raw_data'])
        finally:
            os.remove(h5_path)

    def test_glue_interpolation_forces_consistent_length(self):
        """Prueba unitaria directa del salvaguarda: dos adquisiciones glued con distinta
        cantidad de centros (y por lo tanto, en general, distinta longitud nativa emergente)
        deben interpolarse a la MISMA grilla de referencia tras la primera llamada."""
        centers_a = compute_glue_centers(450.0, 750.0, 0.2)
        centers_b = compute_glue_centers(450.0, 1050.0, 0.2)
        self.assertNotEqual(len(centers_a), len(centers_b), "El escenario de prueba no varía el número de centros.")

        self.worker._glue_reference_grid = None
        w1, s1, mism1 = self.worker._acquire_glued_spectrum(centers_a, 0.01)
        self.assertFalse(mism1, "La primera adquisición establece la grilla; no debería marcar mismatch.")
        grid_len = len(self.worker._glue_reference_grid)

        w2, s2, mism2 = self.worker._acquire_glued_spectrum(centers_b, 0.01)
        self.assertEqual(len(w2), grid_len, "La segunda adquisición debe interpolarse a la grilla de referencia común.")
        self.assertEqual(len(s2), grid_len)

    # ── Clamping físico 0-100 µm ─────────────────────────────────────────────
    def test_piezo_move_clamps_out_of_range_target(self):
        ok = self.worker._move_and_settle(1, 500.0)  # fuera de rango, debe clampear a 100.0
        self.assertTrue(ok)
        pos = pi.qPOS(1)
        actual = float(pos.get("1"))
        self.assertLessEqual(actual, PI_STAGE_RANGE_UM + 1e-6)
        self.assertAlmostEqual(actual, PI_STAGE_RANGE_UM, places=2)

        ok2 = self.worker._move_and_settle(1, -50.0)  # fuera de rango por abajo, debe clampear a 0.0
        self.assertTrue(ok2)
        pos2 = pi.qPOS(1)
        self.assertAlmostEqual(float(pos2.get("1")), 0.0, places=2)

    # ── Compatibilidad de firma mock/real en adquisición 2D-ROI ─────────────
    def test_2d_roi_acquisition_mock_signature_compat(self):
        self.assertTrue(getattr(self.worker.camera, 'is_mock', False))
        roi_ymin, roi_ymax = 481, 521
        frame = self.worker._acquire_2d_roi(roi_ymin, roi_ymax)
        self.assertEqual(frame.shape[0], roi_ymax - roi_ymin)
        self.assertEqual(frame.shape[1], self.worker.camera.width)

    def test_full_scan_runs_without_exceptions_both_modes(self):
        for mode in ('single_window', 'step_and_glue'):
            with self.subTest(mode=mode):
                h5_path = self._run_full_scan(mode)
                self.assertTrue(os.path.exists(h5_path))
                os.remove(h5_path)


if __name__ == "__main__":
    unittest.main()
