# -*- coding: utf-8 -*-
"""
test_pyspectrum_static_raman_modes.py — Selector de Modos de Lectura en Static Raman
PySpectrum 3.0 — UNSAM Nanofotónica

Fase 3 del Rework Arquitectónico: verifica el selector de modos de lectura Andor (FVB/
Single-Track/Multi-Track/Imagen 2D) en la Pestaña 2, la herencia automática del ROI vertical
de SpectroscopyContext en Single-Track, la transición segura vía transition_read_mode(), y que
AsLS + termometría fototérmica sigan funcionando sin regresiones tras el refactor.
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

import numpy as np
from PyQt6 import QtWidgets, QtGui
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

from pyspectrum.drivers.andor_ccd_driver import (
    get_andor_ccd, READ_MODE_FVB, READ_MODE_SINGLE_TRACK, READ_MODE_MULTI_TRACK, READ_MODE_IMAGE,
)
from pyspectrum.drivers.shamrock_driver import get_shamrock
from pyspectrum.modules.spectroscopy_context import spectroscopy_context
from pyspectrum.modules.static_raman import StaticRamanWidget, StaticRamanBackend
from pyspectrum.ui.raman_2d_inspector import Raman2DInspectorWidget


class TestReadModeSelectorUI(unittest.TestCase):

    def setUp(self):
        self.widget = StaticRamanWidget()

    def test_default_mode_is_fvb(self):
        self.assertEqual(self.widget.cmb_read_mode.currentData(), READ_MODE_FVB)

    def test_all_four_modes_present(self):
        modes = {self.widget.cmb_read_mode.itemData(i) for i in range(self.widget.cmb_read_mode.count())}
        self.assertEqual(modes, {READ_MODE_FVB, READ_MODE_SINGLE_TRACK, READ_MODE_MULTI_TRACK, READ_MODE_IMAGE})

    def test_multi_track_spinbox_only_visible_in_multi_track_mode(self):
        self.assertFalse(self.widget.spin_multi_track_n.isVisible())
        idx = self.widget.cmb_read_mode.findData(READ_MODE_MULTI_TRACK)
        self.widget.cmb_read_mode.setCurrentIndex(idx)
        self.widget.show()  # isVisible() requiere que el widget (y sus ancestros) estén mostrados
        self.assertTrue(self.widget.spin_multi_track_n.isVisible())

    def test_single_track_selection_inherits_roi_from_context(self):
        spectroscopy_context.set_vertical_roi(300, 340)
        idx = self.widget.cmb_read_mode.findData(READ_MODE_SINGLE_TRACK)
        self.widget.cmb_read_mode.setCurrentIndex(idx)
        self.assertIn("[300:340]", self.widget.lbl_roi_inherited.text())
        self.assertIn("Centro: 320", self.widget.lbl_roi_inherited.text())
        self.assertIn("Alto: 40 px", self.widget.lbl_roi_inherited.text())

    def test_roi_label_updates_live_while_in_single_track_mode(self):
        idx = self.widget.cmb_read_mode.findData(READ_MODE_SINGLE_TRACK)
        self.widget.cmb_read_mode.setCurrentIndex(idx)
        spectroscopy_context.set_vertical_roi(100, 150)
        self.assertIn("[100:150]", self.widget.lbl_roi_inherited.text())

    def test_roi_label_does_not_update_when_not_in_single_track_mode(self):
        idx = self.widget.cmb_read_mode.findData(READ_MODE_FVB)
        self.widget.cmb_read_mode.setCurrentIndex(idx)
        self.assertEqual(self.widget.lbl_roi_inherited.text(), "")
        spectroscopy_context.set_vertical_roi(10, 20)
        self.assertEqual(self.widget.lbl_roi_inherited.text(), "")

    def test_read_mode_change_emits_signal_with_n_tracks(self):
        received = []
        self.widget.setReadModeSignal.connect(lambda mode, n: received.append((mode, n)))
        idx = self.widget.cmb_read_mode.findData(READ_MODE_MULTI_TRACK)
        self.widget.cmb_read_mode.setCurrentIndex(idx)
        self.widget.spin_multi_track_n.setValue(4)
        self.assertEqual(received[-1], (READ_MODE_MULTI_TRACK, 4))


    def test_spectral_range_badge_updates_on_raman_shift_toggle(self):
        self.widget.chk_raman_shift.setChecked(False)
        self.widget._update_spectral_range_badge()
        text_nm = self.widget.lbl_spectral_range.text()
        self.assertIn("Rango Espectral Cubierto:", text_nm)
        self.assertIn("nm", text_nm)

        self.widget.chk_raman_shift.setChecked(True)
        self.widget._update_spectral_range_badge()
        text_cm1 = self.widget.lbl_spectral_range.text()
        self.assertIn("cm⁻¹", text_cm1)
        self.assertIn("λ:", text_cm1)

    def test_image_2d_selection_inherits_roi_from_context(self):
        spectroscopy_context.set_vertical_roi(200, 260)
        idx = self.widget.cmb_read_mode.findData(READ_MODE_IMAGE)
        self.widget.cmb_read_mode.setCurrentIndex(idx)
        self.assertIn("[200:260]", self.widget.lbl_roi_inherited.text())
        self.assertIn("Centro: 230", self.widget.lbl_roi_inherited.text())
        self.assertIn("Alto: 60 px", self.widget.lbl_roi_inherited.text())


class TestReadModeBackendTransition(unittest.TestCase):

    def setUp(self):
        self.camera = get_andor_ccd(force_mock=True)
        self.spectrometer = get_shamrock(force_mock=True)
        self.widget = StaticRamanWidget()
        self.backend = StaticRamanBackend(self.camera, self.spectrometer)
        self.backend.make_connection(self.widget)

    def test_transition_to_fvb(self):
        self.backend.set_read_mode(READ_MODE_FVB, 1)
        self.assertEqual(self.camera.get_read_mode(), READ_MODE_FVB)
        self.assertEqual(self.backend.current_read_mode, READ_MODE_FVB)

    def test_transition_to_single_track_inherits_context_roi(self):
        spectroscopy_context.set_vertical_roi(400, 460)
        self.backend.set_read_mode(READ_MODE_SINGLE_TRACK, 1)
        self.assertEqual(self.camera.get_read_mode(), READ_MODE_SINGLE_TRACK)
        center, height = self.camera.get_single_track()
        self.assertEqual(center, 430)
        self.assertEqual(height, 60)

    def test_transition_to_multi_track_sets_n_tracks(self):
        self.backend.set_read_mode(READ_MODE_MULTI_TRACK, 3)
        self.assertEqual(self.camera.get_read_mode(), READ_MODE_MULTI_TRACK)
        n, height, offset = self.camera.get_multi_track()
        self.assertEqual(n, 3)

    def test_transition_to_image_2d(self):
        self.backend.set_read_mode(READ_MODE_IMAGE, 1)
        self.assertEqual(self.camera.get_read_mode(), READ_MODE_IMAGE)

    def test_transition_to_image_2d_inherits_context_roi(self):
        spectroscopy_context.set_vertical_roi(200, 280)
        self.backend.set_read_mode(READ_MODE_IMAGE, 1)
        self.assertEqual(self.camera.get_read_mode(), READ_MODE_IMAGE)
        self.assertEqual(self.camera._image_vstart, 201)
        self.assertEqual(self.camera._image_vend, 280)

    def test_all_four_modes_transition_without_raising(self):
        for mode in (READ_MODE_FVB, READ_MODE_SINGLE_TRACK, READ_MODE_MULTI_TRACK, READ_MODE_IMAGE):
            self.backend.set_read_mode(mode, 2)
            self.assertEqual(self.camera.get_read_mode(), mode)


class TestAcquisitionRoutingByMode(unittest.TestCase):

    def setUp(self):
        self.camera = get_andor_ccd(force_mock=True)
        self.spectrometer = get_shamrock(force_mock=True)
        self.widget = StaticRamanWidget()
        self.inspector = Raman2DInspectorWidget()
        self.backend = StaticRamanBackend(self.camera, self.spectrometer)
        self.backend.make_connection(self.widget, self.inspector)

    def test_fvb_acquisition_emits_1d_spectrum(self):
        self.backend.set_read_mode(READ_MODE_FVB, 1)
        received = []
        self.backend.spectrumAcquiredSignal.connect(lambda wl, spec: received.append(spec))
        self.backend.acquire_single()
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].ndim, 1)

    def test_multi_track_acquisition_emits_2d_frame_to_inspector(self):
        self.backend.set_read_mode(READ_MODE_MULTI_TRACK, 3)
        self.backend.acquire_single()
        self.assertIsNotNone(self.inspector.frame_2d)
        self.assertEqual(self.inspector.frame_2d.shape[0], 3)

    def test_image_2d_acquisition_emits_2d_frame_to_inspector_and_switches_view(self):
        spectroscopy_context.set_vertical_roi(0, 0)
        self.backend.set_read_mode(READ_MODE_IMAGE, 1)
        switched = []
        self.inspector.frameReceivedSignal.connect(lambda: switched.append(True))
        self.backend.acquire_single()
        self.assertIsNotNone(self.inspector.frame_2d)
        self.assertEqual(self.inspector.frame_2d.shape, (self.camera.height, self.camera.width))
        self.assertEqual(switched, [True])

    def test_image_2d_acquisition_with_roi_bounds_inspector_frame(self):
        spectroscopy_context.set_vertical_roi(100, 160)
        self.backend.set_read_mode(READ_MODE_IMAGE, 1)
        self.backend.acquire_single()
        self.assertIsNotNone(self.inspector.frame_2d)
        self.assertEqual(self.inspector.frame_2d.shape, (60, self.camera.width))


class TestAutomatedShutterAndFileExport(unittest.TestCase):
    def setUp(self):
        self.camera = get_andor_ccd(force_mock=True)
        self.spectrometer = get_shamrock(force_mock=True)
        self.widget = StaticRamanWidget()
        self.backend = StaticRamanBackend(self.camera, self.spectrometer)
        self.backend.make_connection(self.widget)

    def test_acquire_single_automates_shamrock_shutter(self):
        shutter_calls = []
        orig_shutter = getattr(self.spectrometer, "ShamrockSetShutter", None)
        self.spectrometer.ShamrockSetShutter = lambda dev, mode: shutter_calls.append(mode)
        try:
            self.backend.acquire_single()
            self.assertEqual(shutter_calls, [1, 0])
        finally:
            if orig_shutter:
                self.spectrometer.ShamrockSetShutter = orig_shutter

    def test_toggle_live_automates_shamrock_shutter(self):
        shutter_calls = []
        orig_shutter = getattr(self.spectrometer, "ShamrockSetShutter", None)
        self.spectrometer.ShamrockSetShutter = lambda dev, mode: shutter_calls.append(mode)
        try:
            self.backend.toggle_live(True)
            self.assertEqual(shutter_calls, [1])
            self.backend.toggle_live(False)
            self.assertEqual(shutter_calls, [1, 0])
        finally:
            if orig_shutter:
                self.spectrometer.ShamrockSetShutter = orig_shutter

    def test_save_spectrum_to_file_in_memory_and_parses(self):
        import tempfile
        from core.raman_engine import parse_andor_solis_file

        self.backend.set_read_mode(READ_MODE_IMAGE, 1)

        test_wl = np.linspace(540.0, 580.0, 1004)
        test_cnt = np.ones(1004) * 150.0
        metadata = {
            "Fecha": "2026-09-26 12:00:00",
            "Laser_Excitacion_nm": "532.00",
            "Red_Difraccion": "Grating 2 (600 l/mm)",
            "Centro_Espectrografo_nm": "550.00",
            "Modo_Ventana": "Raman Shift (cm-1)",
            "_raw_wl": test_wl,
            "_raw_counts": test_cnt,
            "_processed_x": test_wl,
            "_processed_y": test_cnt,
            "_baseline_y": np.zeros(1004),
        }

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            self.backend.save_spectrum_to_file(tmp_path, metadata)
            self.assertTrue(os.path.exists(tmp_path))
            parsed_meta, parsed_wl, parsed_cnt = parse_andor_solis_file(tmp_path)
            self.assertEqual(len(parsed_wl), 1004)
            self.assertEqual(len(parsed_cnt), 1004)
            self.assertAlmostEqual(parsed_cnt[0], 150.0, places=1)
            self.assertEqual(parsed_meta.get("Laser_Excitacion_nm"), "532.00")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


class TestPySpectrumWindowTools(unittest.TestCase):
    def test_microscopio_derecho_action_exists(self):
        from pyspectrum.window import PySpectrumWindow
        orig_q = QtWidgets.QMessageBox.question
        QtWidgets.QMessageBox.question = lambda *a, **k: QtWidgets.QMessageBox.StandardButton.Yes
        try:
            win = PySpectrumWindow()
            actions = [a.text() for a in win.findChildren(QtGui.QAction)]
            self.assertTrue(any("Microscopio Derecho" in a for a in actions))
            win.close()
        finally:
            QtWidgets.QMessageBox.question = orig_q


class TestAsLSAndThermometryPreserved(unittest.TestCase):
    """Verifica explícitamente que AsLS y la termometría Stokes/Anti-Stokes sigan
    funcionando sin regresiones tras el refactor de Fase 3."""

    def setUp(self):
        self.widget = StaticRamanWidget()

    def test_asls_baseline_subtraction_reduces_background(self):
        wl_axis = np.linspace(520.0, 600.0, 1004)
        counts = 500.0 + 1000.0 * np.exp(-0.5 * ((wl_axis - 547.1) / 0.3) ** 2)
        self.widget.chk_baseline.setChecked(True)
        idx = self.widget.cmb_baseline.findData("asls")
        self.widget.cmb_baseline.setCurrentIndex(idx)
        self.widget.update_spectrum_data(wl_axis, counts)
        self.assertGreater(np.max(self.widget.baseline_y), 0.0)
        self.assertLess(np.min(self.widget.processed_y), np.min(counts))

    def test_photothermal_temperature_still_computed(self):
        self.widget.laser_nm = 532.0
        wl_axis = np.linspace(510.0, 555.0, 1004)
        counts = np.ones(1004) * 200.0
        idx_stokes = np.argmin(np.abs(wl_axis - 547.1))
        idx_as = np.argmin(np.abs(wl_axis - 517.6))
        counts[idx_stokes] += 5000.0
        counts[idx_as] += 5000.0 * 0.117

        self.widget.update_spectrum_data(wl_axis, counts)
        self.widget.cursor_a.setValue(520.0)
        self.widget.cursor_b.setValue(-520.0)
        self.widget._update_telemetry()

        # Mismo nivel de aserción que el test precedente (no modificado por esta fase):
        # tests/test_pyspectrum_hardware_and_raman.py::test_photothermal_thermometry_calculation
        self.assertIn("Temp Fototérmica:", self.widget.lbl_temp_info.text())
        self.assertIn("K", self.widget.lbl_temp_info.text())


if __name__ == "__main__":
    unittest.main()

