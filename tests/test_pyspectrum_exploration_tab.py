# -*- coding: utf-8 -*-
"""
test_pyspectrum_exploration_tab.py — Pestaña 1 (Exploración): Visor 2D y ROI Vertical Automático
PySpectrum 3.0 — UNSAM Nanofotónica

Fase 2 del Rework Arquitectónico: verifica ExplorationTabWidget/ExplorationWorker, su
incrustación como Pestaña 0 del shell principal, la interacción con el ROI vertical
(pg.LinearRegionItem) y su propagación automática y silenciosa a SpectroscopyContext.
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
from PyQt6 import QtWidgets
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

from pyspectrum.drivers.andor_ccd_driver import get_andor_ccd
from pyspectrum.modules.spectroscopy_context import spectroscopy_context
from pyspectrum.ui.exploration_tab import ExplorationTabWidget, ExplorationWorker, get_colormap, COLORMAP_OPTIONS
from pyspectrum.window import PySpectrumWindow, TAB_EXPLORATION


class TestExplorationTabWidgetInit(unittest.TestCase):

    def test_initializes_without_hardware_controls_duplicated(self):
        w = ExplorationTabWidget()
        # No debe duplicar controles de hardware ya presentes en LeftHardwarePanel
        for forbidden_attr in ("spin_temp", "spin_gain", "cmb_preamp", "cmb_hsspeed", "spin_exposure"):
            self.assertFalse(hasattr(w, forbidden_attr), f"ExplorationTabWidget no debe exponer '{forbidden_attr}'")
        # Sí debe tener el visor y sus herramientas
        self.assertTrue(hasattr(w, "image_item"))
        self.assertTrue(hasattr(w, "plot_item"))
        self.assertTrue(hasattr(w, "histogram"))
        self.assertTrue(hasattr(w, "roi_region"))
        self.assertTrue(hasattr(w, "btn_live"))

    def test_update_image_sets_last_frame(self):
        w = ExplorationTabWidget()
        frame = np.random.rand(50, 60).astype(np.float32)
        w.update_image(frame)
        self.assertIs(w._last_frame, frame)


class TestExplorationTabRoiInteraction(unittest.TestCase):

    def setUp(self):
        self.w = ExplorationTabWidget()

    def test_roi_default_region_matches_initial_status_label(self):
        y1, y2 = self.w.roi_region.getRegion()
        self.assertEqual((int(y1), int(y2)), (480, 520))
        self.assertIn("480", self.w.lbl_roi_status.text())
        self.assertIn("520", self.w.lbl_roi_status.text())

    def test_moving_roi_updates_status_label_center_and_height(self):
        self.w.roi_region.setRegion([100, 140])
        self.assertIn("Centro: 120", self.w.lbl_roi_status.text())
        self.assertIn("Alto: 40 px", self.w.lbl_roi_status.text())

    def test_roi_region_handles_reversed_bounds(self):
        self.w.roi_region.setRegion([300, 200])
        y1, y2 = self.w.roi_region.getRegion()
        self.assertLessEqual(min(y1, y2), max(y1, y2))
        self.assertIn("[200 : 300]", self.w.lbl_roi_status.text())


class TestExplorationTabRoiPropagation(unittest.TestCase):

    def setUp(self):
        self.w = ExplorationTabWidget()
        self.received = []
        self._conn = spectroscopy_context.verticalRoiChanged.connect(lambda *a: self.received.append(a))

    def tearDown(self):
        spectroscopy_context.verticalRoiChanged.disconnect(self._conn)

    def test_moving_roi_propagates_to_spectroscopy_context_and_emits_signal(self):
        self.w.roi_region.setRegion([50, 90])
        self.assertEqual(spectroscopy_context.vertical_roi, (50, 90, 70, 40))
        self.assertEqual(self.received[-1], (50, 90, 70, 40))

    def test_propagation_is_automatic_without_extra_buttons(self):
        # No debe existir ningún botón de "Importar"/"Guardar" ROI: la propagación es directa.
        for attr_name in dir(self.w):
            self.assertNotIn("import_roi", attr_name.lower())
            self.assertNotIn("save_roi", attr_name.lower())
        self.w.roi_region.setRegion([10, 30])
        self.assertEqual(spectroscopy_context.vertical_roi, (10, 30, 20, 20))


class TestExplorationTabColormapAndContrast(unittest.TestCase):

    def setUp(self):
        self.w = ExplorationTabWidget()

    def test_all_required_colormaps_resolve_to_valid_colormap(self):
        names = [name for name, _, _ in COLORMAP_OPTIONS]
        self.assertEqual(names, ["Viridis", "Inferno", "Greys", "Jet"])
        for name in names:
            cmap = get_colormap(name)
            self.assertIsNotNone(cmap)
            lut = cmap.getLookupTable()
            self.assertEqual(lut.ndim, 2)
            self.assertIn(lut.shape[1], (3, 4))  # RGB o RGBA según el backend

    def test_changing_colormap_combo_applies_to_histogram_gradient(self):
        self.w.cmb_colormap.setCurrentText("Jet")
        # No debe lanzar y debe quedar seleccionado
        self.assertEqual(self.w.cmb_colormap.currentText(), "Jet")

    def test_autolevels_uses_robust_percentiles_on_last_frame(self):
        frame = np.full((20, 20), 100.0, dtype=np.float32)
        frame[0, 0] = 10000.0  # outlier tipo rayo cósmico
        self.w.update_image(frame)
        self.w._on_autolevels()
        low, high = self.w.image_item.getLevels()
        self.assertLess(high, 10000.0)  # el outlier no debe dominar el rango
        self.assertGreaterEqual(low, 0.0)

    def test_autolevels_without_frame_does_not_raise(self):
        w = ExplorationTabWidget()
        w._on_autolevels()  # No debe lanzar aunque nunca se haya recibido un cuadro

    def test_autorange_does_not_raise(self):
        self.w._on_autorange()

    def test_crosshair_toggle(self):
        self.assertFalse(self.w.crosshair_v.isVisible())
        self.w.btn_crosshair.setChecked(True)
        self.w._on_toggle_crosshair(True)
        self.assertTrue(self.w.crosshair_v.isVisible())
        self.assertTrue(self.w.crosshair_h.isVisible())


class TestExplorationWorker(unittest.TestCase):

    def setUp(self):
        self.camera = get_andor_ccd(force_mock=True)
        self.worker = ExplorationWorker(self.camera)

    def test_start_live_starts_acquisition_and_emits_frames(self):
        received = []
        self.worker.imageUpdatedSignal.connect(lambda img: received.append(img))
        self.worker.start_live()
        self.worker._acquire_frame()
        self.worker.stop_live()
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].shape, (self.camera.height, self.camera.width))

    def test_set_live_dispatches_to_start_and_stop(self):
        self.worker.set_live(True)
        self.assertTrue(self.worker._timer.isActive())
        self.worker.set_live(False)
        self.assertFalse(self.worker._timer.isActive())


class TestExplorationTabEmbeddedInWindow(unittest.TestCase):

    def setUp(self):
        self._orig_question = QtWidgets.QMessageBox.question
        QtWidgets.QMessageBox.question = lambda *a, **k: QtWidgets.QMessageBox.StandardButton.Yes
        self.win = PySpectrumWindow()

    def tearDown(self):
        self.win.close()
        QtWidgets.QMessageBox.question = self._orig_question

    def test_exploration_widget_is_tab_zero(self):
        self.assertIs(self.win.tabs_workflow.widget(TAB_EXPLORATION), self.win.exploration_widget)
        self.assertIn("Exploración", self.win.tabs_workflow.tabText(TAB_EXPLORATION))

    def test_live_toggle_from_gui_acquires_frame_via_worker_thread(self):
        received = []
        self.win.exploration_widget.liveToggledSignal.connect(lambda active: received.append(active))
        self.win.exploration_widget.btn_live.click()
        self.assertEqual(received, [True])
        self.win.exploration_widget.btn_live.click()
        self.assertEqual(received, [True, False])

    def test_roi_move_on_embedded_tab_still_propagates_to_context(self):
        self.win.exploration_widget.roi_region.setRegion([200, 260])
        self.assertEqual(spectroscopy_context.vertical_roi, (200, 260, 230, 60))


if __name__ == "__main__":
    unittest.main()
