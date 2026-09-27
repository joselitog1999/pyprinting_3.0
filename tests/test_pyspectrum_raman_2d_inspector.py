# -*- coding: utf-8 -*-
"""
test_pyspectrum_raman_2d_inspector.py — Sub-pestaña "Resultado Medición / Inspector 2D"
PySpectrum 3.0 — UNSAM Nanofotónica

Fase 3 del Rework Arquitectónico: verifica el Inspector 2D (visor + slider de fila +
conmutador de promedio espacial ± σ del ROI) y su exportación estructurada (TXT/CSV y HDF5).
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

from pyspectrum.modules.spectroscopy_context import spectroscopy_context
from pyspectrum.ui.raman_2d_inspector import (
    Raman2DInspectorWidget, compute_roi_mean_std, export_raman_2d_to_hdf5, H5PY_AVAILABLE,
)

if H5PY_AVAILABLE:
    import h5py


def _make_synthetic_frame(height=1002, width=1004, seed=42):
    rng = np.random.default_rng(seed)
    wl_axis = np.linspace(500.0, 700.0, width)
    base = 100.0 * np.exp(-0.5 * ((wl_axis - 600.0) / 15.0) ** 2)
    frame = np.tile(base, (height, 1)) + rng.normal(0, 2.0, (height, width))
    return frame.astype(np.float32), wl_axis


class TestInspectorFrameInjection(unittest.TestCase):

    def setUp(self):
        self.w = Raman2DInspectorWidget()

    def test_injecting_full_size_synthetic_matrix_updates_viewer_and_slider(self):
        frame, wl_axis = _make_synthetic_frame(1002, 1004)
        spectroscopy_context.set_vertical_roi(400, 500)
        self.w.set_frame_2d(wl_axis, frame, "Imagen 2D")
        self.assertEqual(self.w.frame_2d.shape, (1002, 1004))
        self.assertEqual(self.w.slider_row.maximum(), 1001)
        self.assertEqual(self.w.roi_rows, (400, 500))

    def test_frame_received_signal_fires_on_new_frame(self):
        received = []
        self.w.frameReceivedSignal.connect(lambda: received.append(True))
        frame, wl_axis = _make_synthetic_frame(50, 100)
        self.w.set_frame_2d(wl_axis, frame, "Multi-Track")
        self.assertEqual(received, [True])


class TestRowSlider(unittest.TestCase):

    def setUp(self):
        self.w = Raman2DInspectorWidget()
        self.frame, self.wl_axis = _make_synthetic_frame(200, 300)
        spectroscopy_context.set_vertical_roi(50, 150)
        self.w.set_frame_2d(self.wl_axis, self.frame, "Imagen 2D")

    def test_moving_slider_updates_1d_curve_to_exact_row(self):
        self.w.slider_row.setValue(77)
        x, y = self.w.curve_1d.getData()
        np.testing.assert_array_equal(y, self.frame[77, :])
        self.assertIn("Fila Y: [77]", self.w.lbl_row_status.text())

    def test_row_label_reports_correct_peak_counts(self):
        self.w.slider_row.setValue(10)
        expected_peak = float(np.max(self.frame[10, :]))
        self.assertIn(f"{expected_peak:.0f}", self.w.lbl_row_status.text())

    def test_dragging_guide_line_updates_slider_and_curve(self):
        self.w.row_line.setValue(42)
        self.assertEqual(self.w.slider_row.value(), 42)
        x, y = self.w.curve_1d.getData()
        np.testing.assert_array_equal(y, self.frame[42, :])

    def test_slider_disabled_when_spatial_mean_active(self):
        self.assertTrue(self.w.slider_row.isEnabled())
        self.w.chk_spatial_mean.setChecked(True)
        self.assertFalse(self.w.slider_row.isEnabled())


class TestSpatialMeanToggle(unittest.TestCase):

    def setUp(self):
        self.w = Raman2DInspectorWidget()
        self.frame, self.wl_axis = _make_synthetic_frame(200, 300)
        spectroscopy_context.set_vertical_roi(60, 100)
        self.w.set_frame_2d(self.wl_axis, self.frame, "Imagen 2D")

    def test_mean_and_std_match_numpy_over_roi_rows(self):
        self.w.chk_spatial_mean.setChecked(True)
        expected_mean = np.mean(self.frame[60:100, :], axis=0)
        expected_std = np.std(self.frame[60:100, :], axis=0)
        x, mu = self.w.curve_1d.getData()
        np.testing.assert_allclose(mu, expected_mean)
        _, upper = self.w.curve_upper.getData()
        np.testing.assert_allclose(upper, expected_mean + expected_std)
        _, lower = self.w.curve_lower.getData()
        np.testing.assert_allclose(lower, expected_mean - expected_std)

    def test_compute_roi_mean_std_helper_matches_numpy_directly(self):
        mu, sigma = compute_roi_mean_std(self.frame, (60, 100))
        np.testing.assert_allclose(mu, np.mean(self.frame[60:100, :], axis=0))
        np.testing.assert_allclose(sigma, np.std(self.frame[60:100, :], axis=0))

    def test_fill_shown_only_in_mean_mode(self):
        self.assertFalse(self.w.fill.isVisible())
        self.w.chk_spatial_mean.setChecked(True)
        self.assertTrue(self.w.fill.isVisible())
        self.w.chk_spatial_mean.setChecked(False)
        self.assertFalse(self.w.fill.isVisible())


class TestExport(unittest.TestCase):

    def setUp(self):
        self.w = Raman2DInspectorWidget()
        self.frame, self.wl_axis = _make_synthetic_frame(100, 150)
        spectroscopy_context.set_vertical_roi(20, 60)
        self.w.set_frame_2d(self.wl_axis, self.frame, "Multi-Track")
        self.w.set_extra_metadata(laser_nm=532.0, grating_name="150 l/mm")
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_export_txt_single_row(self):
        path = os.path.join(self.tmp_dir, "row.txt")
        self.w.slider_row.setValue(5)
        self.w.export_txt_to_path(path)
        self.assertTrue(os.path.isfile(path))
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("Fila Y: 5", content)
        self.assertIn("Wavelength_nm\tCounts", content)

    def test_export_txt_spatial_mean(self):
        path = os.path.join(self.tmp_dir, "mean.txt")
        self.w.chk_spatial_mean.setChecked(True)
        self.w.export_txt_to_path(path)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("Wavelength_nm\tMean_Counts\tStd_Counts", content)

    @unittest.skipUnless(H5PY_AVAILABLE, "h5py no disponible en este entorno")
    def test_export_hdf5_structure_and_datasets(self):
        path = os.path.join(self.tmp_dir, "raman2d.h5")
        self.w.export_hdf5_to_path(path)
        self.assertTrue(os.path.isfile(path))
        with h5py.File(path, "r") as f:
            self.assertEqual(f["raw_2d"].shape, self.frame.shape)
            self.assertEqual(f["wavelengths"].shape, self.wl_axis.shape)
            expected_mean, expected_std = compute_roi_mean_std(self.frame, (20, 60))
            np.testing.assert_allclose(f["spectrum_mean"][:], expected_mean, rtol=1e-5)
            np.testing.assert_allclose(f["std"][:], expected_std, rtol=1e-5)
            self.assertAlmostEqual(f.attrs["laser_nm"], 532.0)
            self.assertEqual(f.attrs["grating"], "150 l/mm")
            self.assertEqual(f.attrs["roi_y_min"], 20)
            self.assertEqual(f.attrs["roi_y_max"], 60)

    def test_export_hdf5_gracefully_returns_path_without_h5py(self):
        # Simula ausencia de h5py monkeypatchando el flag del módulo
        import pyspectrum.ui.raman_2d_inspector as mod
        original = mod.H5PY_AVAILABLE
        mod.H5PY_AVAILABLE = False
        try:
            path = os.path.join(self.tmp_dir, "no_h5py.h5")
            result = mod.export_raman_2d_to_hdf5(path, self.frame, self.wl_axis, (0, 10))
            self.assertEqual(result, path)
            self.assertFalse(os.path.isfile(path))
        finally:
            mod.H5PY_AVAILABLE = original

    def test_export_without_frame_does_not_raise(self):
        w2 = Raman2DInspectorWidget()
        w2.export_txt_to_path(os.path.join(self.tmp_dir, "empty.txt"))
        w2.export_hdf5_to_path(os.path.join(self.tmp_dir, "empty.h5"))
        self.assertFalse(os.path.isfile(os.path.join(self.tmp_dir, "empty.txt")))


class TestInspectorAcquisitionAndLiveControls(unittest.TestCase):

    def setUp(self):
        self.w = Raman2DInspectorWidget()

    def test_btn_single_emits_request_acquire_single(self):
        called = []
        self.w.requestAcquireSingleSignal.connect(lambda: called.append(True))
        self.w.btn_single.click()
        self.assertEqual(called, [True])

    def test_btn_live_emits_toggle_live_raman(self):
        emitted = []
        self.w.toggleLiveRamanSignal.connect(lambda val: emitted.append(val))
        self.w.btn_live.click()
        self.assertEqual(emitted, [True])
        self.assertIn("Detener", self.w.btn_live.text())
        self.assertFalse(self.w.btn_single.isEnabled())

        self.w.btn_live.click()
        self.assertEqual(emitted, [True, False])
        self.assertIn("Live Raman", self.w.btn_live.text())
        self.assertTrue(self.w.btn_single.isEnabled())

    def test_set_live_state_updates_appearance_and_buttons(self):
        self.w.set_live_state(True)
        self.assertTrue(self.w.btn_live.isChecked())
        self.assertIn("Detener", self.w.btn_live.text())
        self.assertFalse(self.w.btn_single.isEnabled())

        self.w.set_live_state(False)
        self.assertFalse(self.w.btn_live.isChecked())
        self.assertIn("Live Raman", self.w.btn_live.text())
        self.assertTrue(self.w.btn_single.isEnabled())

    def test_autolevels_button(self):
        from core.sif_processor import compute_robust_contrast_levels

        frame, wl = _make_synthetic_frame(50, 100)
        self.w.set_frame_2d(wl, frame)

        # Se parte de niveles deliberadamente distintos de los robustos, para que la
        # aserción distinga "aplicó el contraste" de "no hizo nada": sin esto el test
        # pasaría igual con un _on_autolevels() vacío.
        self.w.image_item.setLevels((0.0, 1.0))
        before = tuple(float(v) for v in self.w.image_item.getLevels())

        self.w.btn_autolevels.click()

        after = tuple(float(v) for v in self.w.image_item.getLevels())
        self.assertNotEqual(before, after, "btn_autolevels no modificó los niveles del ImageItem")
        expected = tuple(float(v) for v in compute_robust_contrast_levels(frame))
        self.assertAlmostEqual(after[0], expected[0], places=6)
        self.assertAlmostEqual(after[1], expected[1], places=6)

    def test_colormap_reaction_from_spectroscopy_context(self):
        import numpy as np
        from pyspectrum.ui.exploration_tab import get_colormap

        emitted = []
        handler = lambda name: emitted.append(name)  # noqa: E731
        spectroscopy_context.colormapChanged.connect(handler)
        try:
            spectroscopy_context.set_colormap("Inferno")
            # El setter del contexto emite SÓLO si el valor cambió, así que esta aserción es
            # lo que impide que el test degenere en un no-op cuando otro test dejó el
            # colormap fijado en "Inferno" (ver el fixture _isolate_spectroscopy_context en
            # tests/conftest.py).
            self.assertEqual(emitted, ["Inferno"])

            # Y el LUT debe haber llegado efectivamente al ImageItem, que es lo que el
            # comentario original prometía y no verificaba.
            expected_lut = get_colormap("Inferno").getLookupTable(0.0, 1.0, 256)
            self.assertTrue(
                np.array_equal(np.asarray(self.w.image_item.lut), np.asarray(expected_lut)),
                "El colormap del contexto no se aplicó como LookupTable del ImageItem",
            )
        finally:
            spectroscopy_context.colormapChanged.disconnect(handler)

    def test_container_wires_and_syncs_buttons(self):
        from pyspectrum.ui.static_raman_container import StaticRamanTabContainer
        container = StaticRamanTabContainer()
        single_called = []
        container.spectrum_widget.btn_single.clicked.connect(lambda: single_called.append(True))
        container.inspector_widget.btn_single.click()
        self.assertEqual(single_called, [True])

        # Test live sync from inspector to spectrum widget
        container.inspector_widget.btn_live.click()
        self.assertTrue(container.spectrum_widget.btn_live.isChecked())
        self.assertFalse(container.inspector_widget.btn_single.isEnabled())


if __name__ == "__main__":
    unittest.main()

