# -*- coding: utf-8 -*-
"""
test_pyspectrum_shell_and_panel.py — Shell de Pestañas, Panel Izquierdo Permanente y Contexto
PySpectrum 3.0 — UNSAM Nanofotónica

Fase 1 del Rework Arquitectónico: verifica el nuevo shell de pestañas de flujo de trabajo, el
panel izquierdo permanente y dinámico (LeftHardwarePanel), la adaptabilidad contextual por
pestaña y el bus de estado global (SpectroscopyContext).
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

from pyspectrum.drivers.andor_ccd_driver import get_andor_ccd
from pyspectrum.drivers.shamrock_driver import get_shamrock
from pyspectrum.ui.left_hardware_panel import LeftHardwarePanel
from pyspectrum.modules.spectroscopy_context import SpectroscopyContext, spectroscopy_context
from pyspectrum.modules.routines.growth_kinetics import (
    GrowthKineticsPanel, GrowthKineticsWidget, GrowthKineticsBackend,
)
from pyspectrum.window import (
    PySpectrumWindow, TAB_EXPLORATION, TAB_STATIC_RAMAN, TAB_STEP_AND_GLUE,
    TAB_GROWTH_KINETICS, TAB_CALIBRATION, TAB_CONFOCAL,
)


class TestLeftHardwarePanel(unittest.TestCase):
    """Verifica la construcción, población dinámica y adaptabilidad contextual del panel."""

    def setUp(self):
        self.camera = get_andor_ccd(force_mock=True)
        self.spectrometer = get_shamrock(force_mock=True)
        self.panel = LeftHardwarePanel(self.camera, self.spectrometer, step_glue_tab_index=2)

    def test_preamp_and_hsspeed_combos_populated_from_hardware(self):
        self.assertEqual(self.panel.cmb_preamp.count(), self.camera.get_number_preamp_gains())
        self.assertGreater(self.panel.cmb_preamp.count(), 0)
        self.assertEqual(self.panel.cmb_hsspeed.count(), self.camera.get_number_hs_speeds())
        self.assertGreater(self.panel.cmb_hsspeed.count(), 0)

    def test_preamp_selection_applies_to_camera(self):
        self.panel.cmb_preamp.setCurrentIndex(1)
        self.assertEqual(self.camera.get_preamp_gain_index(), 1)

    def test_hsspeed_selection_applies_to_camera(self):
        self.panel.cmb_hsspeed.setCurrentIndex(2)
        self.assertEqual(self.camera.get_hs_speed_index(), 2)

    def test_shutter_mode_applies_to_camera(self):
        self.panel.cmb_shutter_mode.setCurrentIndex(2)  # Siempre Cerrado
        self.assertEqual(self.camera.get_shutter_mode(), 2)

    def test_set_context_disables_manual_wavelength_on_step_and_glue_tab(self):
        self.panel.set_context(0)
        self.assertTrue(self.panel.edit_wavelength.isEnabled())
        self.assertTrue(self.panel.btn_goto_wavelength.isEnabled())

        self.panel.set_context(2)  # step_glue_tab_index
        self.assertFalse(self.panel.edit_wavelength.isEnabled())
        self.assertFalse(self.panel.btn_goto_wavelength.isEnabled())

        self.panel.set_context(3)
        self.assertTrue(self.panel.edit_wavelength.isEnabled())

    def test_em_gain_change_applies_to_camera(self):
        self.panel.spin_gain.setValue(150)
        self.panel._on_gain_changed()
        self.assertEqual(self.camera.get_emccd_gain(), 150)

    def test_grating_change_updates_spectrograph(self):
        self.panel.cmb_grating.setCurrentIndex(1)
        ret, grating = self.spectrometer.ShamrockGetGrating(0)
        self.assertEqual(grating, 2)


class TestSpectroscopyContext(unittest.TestCase):
    """Verifica el patrón singleton y la propagación de señales del bus de estado global."""

    def test_singleton_returns_same_instance(self):
        a = SpectroscopyContext.get_instance()
        b = SpectroscopyContext.get_instance()
        self.assertIs(a, b)
        self.assertIs(a, spectroscopy_context)

    def test_vertical_roi_changed_signal_emits_and_updates_property(self):
        received = []
        spectroscopy_context.verticalRoiChanged.connect(lambda *args: received.append(args))
        spectroscopy_context.set_vertical_roi(480, 520)
        self.assertEqual(received[-1], (480, 520, 500, 40))
        self.assertEqual(spectroscopy_context.vertical_roi, (480, 520, 500, 40))

    def test_subjugated_mode_changed_signal(self):
        received = []
        spectroscopy_context.subjugatedModeChanged.connect(lambda active: received.append(active))
        spectroscopy_context.set_subjugated(True)
        self.assertTrue(received[-1])
        self.assertTrue(spectroscopy_context.is_subjugated)
        spectroscopy_context.set_subjugated(False)
        self.assertFalse(spectroscopy_context.is_subjugated)


class TestGrowthKineticsPanelCompatibility(unittest.TestCase):
    """Verifica que la extracción de GrowthKineticsPanel no rompa el uso standalone previo."""

    def test_panel_embeddable_and_backend_wireable(self):
        panel = GrowthKineticsPanel()
        camera = get_andor_ccd(force_mock=True)
        spectrometer = get_shamrock(force_mock=True)
        backend = GrowthKineticsBackend(camera, spectrometer)
        backend.make_connection(panel)  # No debe lanzar

    def test_standalone_dialog_exposes_same_controls_as_panel(self):
        widget = GrowthKineticsWidget()
        for attr_name in ("cmb_laser", "edit_exp", "edit_nframes", "edit_interval",
                          "btn_run", "progress_bar", "lbl_peak"):
            self.assertTrue(hasattr(widget, attr_name))
        camera = get_andor_ccd(force_mock=True)
        spectrometer = get_shamrock(force_mock=True)
        backend = GrowthKineticsBackend(camera, spectrometer)
        backend.make_connection(widget)  # No debe lanzar (retrocompatibilidad)


class TestPySpectrumWindowShell(unittest.TestCase):
    """Verifica el shell principal de 6 pestañas y su adaptabilidad contextual."""

    def setUp(self):
        self._orig_question = QtWidgets.QMessageBox.question
        QtWidgets.QMessageBox.question = lambda *a, **k: QtWidgets.QMessageBox.StandardButton.Yes
        self.win = PySpectrumWindow()

    def tearDown(self):
        self.win.close()
        QtWidgets.QMessageBox.question = self._orig_question

    def test_six_tabs_present_with_expected_titles(self):
        self.assertEqual(self.win.tabs_workflow.count(), 6)
        titles = [self.win.tabs_workflow.tabText(i) for i in range(6)]
        self.assertIn("Exploración", titles[TAB_EXPLORATION])
        self.assertIn("Static Raman", titles[TAB_STATIC_RAMAN])
        self.assertIn("Step & Glue", titles[TAB_STEP_AND_GLUE])
        self.assertIn("Cinética", titles[TAB_GROWTH_KINETICS])
        self.assertIn("Calibraciones", titles[TAB_CALIBRATION])
        self.assertIn("Mapeo Confocal", titles[TAB_CONFOCAL])

    def test_left_panel_permanent_across_tab_switches(self):
        for idx in range(self.win.tabs_workflow.count()):
            self.win.tabs_workflow.setCurrentIndex(idx)
            self.assertTrue(self.win.left_panel.isVisible() or not self.win.isVisible())

    def test_tab_switch_adapts_left_panel_context_no_state_loss(self):
        self.win.left_panel.spin_gain.setValue(77)
        self.win.tabs_workflow.setCurrentIndex(TAB_STEP_AND_GLUE)
        self.assertFalse(self.win.left_panel.edit_wavelength.isEnabled())
        # El valor de EM Gain no debe perderse por el cambio de pestaña (resiliencia de estado)
        self.assertEqual(self.win.left_panel.spin_gain.value(), 77)

        self.win.tabs_workflow.setCurrentIndex(TAB_EXPLORATION)
        self.assertTrue(self.win.left_panel.edit_wavelength.isEnabled())
        self.assertEqual(self.win.left_panel.spin_gain.value(), 77)


if __name__ == "__main__":
    unittest.main()
