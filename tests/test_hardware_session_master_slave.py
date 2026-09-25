# -*- coding: utf-8 -*-
"""
test_hardware_session_master_slave.py — Arquitectura Master-Slave (Fase 5, DEC-019)
PySpectrum 3.0 — UNSAM Nanofotónica

Verifica la subyugación Master-Slave entre PySpectrum 3.0 (master) y las ventanas satélite
Contrapropagante/PyPrinting (slave): transición a Modo Solo Monitoreo, restauración a modo
autónomo, arbitraje exclusivo + E-STOP, y el módulo puente de soporte óptico
(pyspectrum/modules/optical_support.py) sin colisiones de hilos en SAFE_MODE.
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

import config  # noqa: F401 — registra core/modules/analysis en sys.path antes de los imports flat de abajo
from pyspectrum.modules.spectroscopy_context import spectroscopy_context
from pyspectrum.modules.hardware_session import hardware_session
from pyspectrum.modules import optical_support
from core.nidaq import get_open_shutter_names, open_shutter
from config import SHUTTERS
# Import a nivel de módulo (no perezoso dentro de setUp/tests): mismo patrón ya usado y
# validado en tests/test_confocal.py — importar contrapropagante.py/app.py de forma perezosa
# dentro de un método de test colgaba bajo pytest (aunque el mismo import funcionaba
# instantáneo en un script plano), un efecto de orden de import específico de pytest/EDSDK
# no reproducido fuera de él; no reproducido tampoco a nivel de módulo.
import contrapropagante
import app as pyprinting_app


class TestMasterSlaveTransition(unittest.TestCase):
    """1. Transición Master-Slave: set_subjugated_mode(True) deshabilita los widgets de
    actuación manual y muestra el banner ámbar; los visores de telemetría siguen activos.

    setUpClass/tearDownClass (no setUp/tearDown por método): construir el satélite completo
    (Backend + múltiples QThread reales, incl. un CanonWorker/sesión EDSDK propia) por cada
    uno de los ~8 test methods de esta clase demostró causar agotamiento acumulativo de
    recursos compartidos (Qt/EDSDK) a lo largo de la suite bajo pytest — un único ciclo de
    vida compartido por clase, con set_subjugated_mode(False) reseteado al inicio de cada
    test, preserva la misma cobertura sin ese riesgo."""

    @classmethod
    def setUpClass(cls):
        hardware_session.clear_emergency()
        cls._orig_question = QtWidgets.QMessageBox.question
        QtWidgets.QMessageBox.question = lambda *a, **k: QtWidgets.QMessageBox.StandardButton.Yes
        cls.win, cls.backend, cls.threads = contrapropagante.create_contrapropagante_satellite()
        cls.win.show()  # necesario para que isVisible() refleje el estado real, no sólo el flag

    @classmethod
    def tearDownClass(cls):
        for t in cls.threads:
            t.quit()
        for t in cls.threads:
            t.wait(3000)
        cls.win.close()
        QtWidgets.QMessageBox.question = cls._orig_question

    def setUp(self):
        self.win.set_subjugated_mode(False)

    def test_banner_hidden_by_default(self):
        self.assertFalse(self.win.subjugated_banner.isVisible())

    def test_subjugation_shows_amber_banner_with_master_name(self):
        self.win.set_subjugated_mode(True, master_name="Step & Glue")
        self.assertTrue(self.win.subjugated_banner.isVisible())
        self.assertIn("Step & Glue", self.win.subjugated_banner.text())
        self.assertIn("Modo Solo Monitoreo", self.win.subjugated_banner.text())

    def test_subjugation_disables_nano_actuators(self):
        self.win.set_subjugated_mode(True)
        for w in (self.win.nanoWidget.xUpButton, self.win.nanoWidget.xDownButton,
                  self.win.nanoWidget.yUpButton, self.win.nanoWidget.yDownButton,
                  self.win.nanoWidget.zUpButton, self.win.nanoWidget.zDownButton,
                  self.win.nanoWidget.StepEdit, self.win.nanoWidget.zStepEdit,
                  self.win.nanoWidget.gotoButton):
            self.assertFalse(w.isEnabled())

    def test_subjugation_keeps_position_telemetry_active(self):
        """xLabel/yLabel/zLabel (posición real de la platina) NUNCA se deshabilitan."""
        self.win.set_subjugated_mode(True)
        self.assertTrue(self.win.nanoWidget.xLabel.isEnabled())
        self.assertTrue(self.win.nanoWidget.yLabel.isEnabled())
        self.assertTrue(self.win.nanoWidget.zLabel.isEnabled())
        # Y deben seguir refrescándose con datos nuevos mientras subyugado
        self.win.nanoWidget.read_pos_list([12.345, 6.789, 1.234])
        self.assertEqual(self.win.nanoWidget.xLabel.text(), "12.345")

    def test_subjugation_disables_shutters_but_keeps_close_all_active(self):
        self.win.set_subjugated_mode(True)
        self.assertFalse(self.win.shuttersWidget.shutter0button.isEnabled())
        self.assertFalse(self.win.shuttersWidget.powerbutton.isEnabled())
        self.assertFalse(self.win.shuttersWidget.notch532button.isEnabled())
        # btn_close_all es una vía de escape de seguridad: siempre debe quedar habilitado
        self.assertTrue(self.win.shuttersWidget.btn_close_all.isEnabled())

    def test_subjugation_disables_focus_manual_buttons(self):
        self.win.set_subjugated_mode(True)
        self.assertFalse(self.win.focusWidget.focus_gotomax_button.isEnabled())
        self.assertFalse(self.win.focusWidget.focus_lock_button.isEnabled())
        self.assertFalse(self.win.focusWidget.focus_autocorrx2_button.isEnabled())

    def test_subjugation_disables_confocal_dual_controls(self):
        self.win.set_subjugated_mode(True)
        self.assertFalse(self.win.dual_frontend.controls_container.isEnabled())

    def test_subjugation_keeps_trace_widget_fully_active(self):
        """TraceFrontend (streaming del fotodiodo) nunca se toca — no tiene
        set_actuators_enabled(); debe permanecer 100% habilitado siempre."""
        self.win.set_subjugated_mode(True)
        self.assertTrue(self.win.traceWidget.isEnabled())


class TestAutonomousModeRestoration(unittest.TestCase):
    """2. Restauración de Modo Autónomo: set_subjugated_mode(False) rehabilita al 100%.

    setUpClass/tearDownClass por el mismo motivo documentado en
    TestMasterSlaveTransition."""

    @classmethod
    def setUpClass(cls):
        hardware_session.clear_emergency()
        cls._orig_question = QtWidgets.QMessageBox.question
        QtWidgets.QMessageBox.question = lambda *a, **k: QtWidgets.QMessageBox.StandardButton.Yes
        cls.win, cls.backend, cls.threads = contrapropagante.create_contrapropagante_satellite()
        cls.win.show()

    @classmethod
    def tearDownClass(cls):
        for t in cls.threads:
            t.quit()
        for t in cls.threads:
            t.wait(3000)
        cls.win.close()
        QtWidgets.QMessageBox.question = cls._orig_question

    def setUp(self):
        self.win.set_subjugated_mode(True)

    def test_restoration_hides_banner(self):
        self.win.set_subjugated_mode(False)
        self.assertFalse(self.win.subjugated_banner.isVisible())

    def test_restoration_reenables_all_actuators(self):
        self.win.set_subjugated_mode(False)
        self.assertTrue(self.win.nanoWidget.xUpButton.isEnabled())
        self.assertTrue(self.win.nanoWidget.StepEdit.isEnabled())
        self.assertTrue(self.win.shuttersWidget.shutter0button.isEnabled())
        self.assertTrue(self.win.focusWidget.focus_gotomax_button.isEnabled())
        self.assertTrue(self.win.dual_frontend.controls_container.isEnabled())


class TestAppPySatelliteParity(unittest.TestCase):
    """Paridad: app.py::Frontend implementa la misma subyugación que contrapropagante.py.

    Construye sólo Frontend() (sin Backend/QThreads/CameraWorker): set_subjugated_mode()/
    set_actuators_enabled() operan puramente sobre el árbol de widgets, así que no
    necesitan el Backend cableado. Evita además construir un segundo CameraWorker (Canon
    EDSDK) en el mismo proceso de pytest junto al ya creado por TestMasterSlaveTransition/
    TestAutonomousModeRestoration (contrapropagante.py); create_app_satellite() completo
    (con Backend/QThreads reales) ya fue verificado manualmente end-to-end de forma
    aislada durante el desarrollo de esta fase."""

    def setUp(self):
        hardware_session.clear_emergency()
        self._orig_question = QtWidgets.QMessageBox.question
        QtWidgets.QMessageBox.question = lambda *a, **k: QtWidgets.QMessageBox.StandardButton.Yes
        self.gui = pyprinting_app.Frontend()
        self.gui.show()

    def tearDown(self):
        self.gui.close()
        QtWidgets.QMessageBox.question = self._orig_question

    def test_subjugation_and_restoration_toggle_confocal_actuators(self):
        self.gui.set_subjugated_mode(True, master_name="Cinética")
        self.assertFalse(self.gui.confocalWidget.scanButton.isEnabled())
        self.assertFalse(self.gui.confocalWidget.CMcheck.isEnabled())
        self.assertTrue(self.gui.subjugated_banner.isVisible())
        self.assertIn("Cinética", self.gui.subjugated_banner.text())

        self.gui.set_subjugated_mode(False)
        self.assertTrue(self.gui.confocalWidget.scanButton.isEnabled())
        self.assertFalse(self.gui.subjugated_banner.isVisible())


class TestGlobalBusWiring(unittest.TestCase):
    """Verifica que PySpectrumWindow conecte automáticamente hardware_session.acquire_session()/
    release_session() a spectroscopy_context.set_subjugated(), y que la ventana satélite
    reaccione en vivo a ambas señales del bus global."""

    def setUp(self):
        hardware_session.clear_emergency()
        self._orig_question = QtWidgets.QMessageBox.question
        self._orig_critical = QtWidgets.QMessageBox.critical
        QtWidgets.QMessageBox.question = lambda *a, **k: QtWidgets.QMessageBox.StandardButton.Yes
        # _on_emergency_stop_clicked() muestra un QMessageBox.critical() real de aviso —
        # bloquea bajo QT_QPA_PLATFORM=offscreen igual que .question(), mockeado aparte
        # porque es un método distinto de QMessageBox.
        QtWidgets.QMessageBox.critical = lambda *a, **k: None
        from pyspectrum.window import PySpectrumWindow
        self.win = PySpectrumWindow()

    def tearDown(self):
        self.win.close()
        QtWidgets.QMessageBox.question = self._orig_question
        QtWidgets.QMessageBox.critical = self._orig_critical
        hardware_session.clear_emergency()

    def test_acquiring_session_subjugates_and_releasing_restores(self):
        self.assertFalse(spectroscopy_context.is_subjugated)
        ok = hardware_session.acquire_session("Test Routine")
        self.assertTrue(ok)
        self.assertTrue(spectroscopy_context.is_subjugated)
        hardware_session.release_session("Test Routine")
        self.assertFalse(spectroscopy_context.is_subjugated)

    def test_stage_status_indicator_reflects_subjugation(self):
        hardware_session.acquire_session("Test Routine 2")
        self.assertIn("Subyugada", self.win.lbl_stage_status.text())
        hardware_session.release_session("Test Routine 2")
        self.assertIn("Libre", self.win.lbl_stage_status.text())

    def test_satellite_window_reacts_live_to_master_session(self):
        self.win._open_contrapropagante()
        satellite = self.win.contrapropagante_satellite
        satellite.show()

        hardware_session.acquire_session("Step & Glue")
        self.assertFalse(satellite.nanoWidget.StepEdit.isEnabled())
        self.assertTrue(satellite.subjugated_banner.isVisible())
        self.assertIn("Step & Glue", satellite.subjugated_banner.text())

        hardware_session.release_session("Step & Glue")
        self.assertTrue(satellite.nanoWidget.StepEdit.isEnabled())
        self.assertFalse(satellite.subjugated_banner.isVisible())

        # 3. Arbitraje Exclusivo y E-STOP, reutilizando esta misma ventana/satélite ya
        # abiertos: emergency_stop() cierra shutters, libera la sesión, y ambas ventanas
        # (PySpectrum y Contrapropagante) pasan a estado seguro inmediato — verificado sobre
        # la MISMA instancia en vivo en vez de construir un segundo PySpectrumWindow +
        # satélite completo (Backend + múltiples QThread reales cada uno, incl. su propia
        # sesión Canon EDSDK): repetir esa construcción pesada por separado demostró ser
        # propenso a interbloqueos de recursos compartidos bajo pytest.
        open_shutter(SHUTTERS[0])
        hardware_session.acquire_session("Cinética")
        self.assertFalse(satellite.nanoWidget.StepEdit.isEnabled())

        self.win._on_emergency_stop_clicked()
        self.assertEqual(get_open_shutter_names(), [])
        self.assertFalse(hardware_session.is_busy)
        self.assertTrue(satellite.nanoWidget.StepEdit.isEnabled())
        self.assertFalse(satellite.subjugated_banner.isVisible())

        for t in self.win._contrapropagante_threads:
            t.quit()
        for t in self.win._contrapropagante_threads:
            t.wait(3000)


class TestEmergencyStopSafeState(unittest.TestCase):
    """3a. Arbitraje Exclusivo y E-STOP (núcleo, sin ventanas): emergency_stop() cierra
    shutters y libera sesiones inmediatamente."""

    def setUp(self):
        hardware_session.clear_emergency()

    def tearDown(self):
        hardware_session.clear_emergency()

    def test_emergency_stop_closes_shutters(self):
        open_shutter(SHUTTERS[0])
        self.assertIn(SHUTTERS[0], get_open_shutter_names())
        hardware_session.emergency_stop()
        self.assertEqual(get_open_shutter_names(), [])

    def test_emergency_stop_releases_active_session(self):
        hardware_session.acquire_session("Step & Glue")
        self.assertTrue(hardware_session.is_busy)
        hardware_session.emergency_stop()
        self.assertFalse(hardware_session.is_busy)


class TestOpticalSupportBridge(unittest.TestCase):
    """4. Mock Óptico: run_z_autofocus y run_confocal_centering en SAFE_MODE=True, sin
    errores de concurrencia ni colisiones de hilos."""

    def test_get_stage_coordinates_returns_real_pi_position(self):
        coords = optical_support.get_stage_coordinates()
        self.assertEqual(len(coords), 3)
        for c in coords:
            self.assertIsInstance(c, float)

    def test_run_z_autofocus_converges_in_safe_mode(self):
        ok = optical_support.run_z_autofocus(timeout_s=10.0)
        self.assertTrue(ok)

    def test_run_z_autofocus_with_unknown_laser_color_does_not_raise(self):
        try:
            optical_support.run_z_autofocus(laser_color="not-a-real-laser", timeout_s=10.0)
        except Exception as e:
            self.fail(f"run_z_autofocus lanzó una excepción con láser desconocido: {e}")

    def test_run_confocal_centering_center_of_mass_returns_coordinates_near_start(self):
        x0, y0, _ = optical_support.get_stage_coordinates()
        x_opt, y_opt = optical_support.run_confocal_centering(range_um=1.0, pixels=6, method="center_of_mass")
        self.assertAlmostEqual(x_opt, x0, delta=1.0)
        self.assertAlmostEqual(y_opt, y0, delta=1.0)

    def test_run_confocal_centering_center_of_gauss_fail_soft(self):
        """Incluso si el ajuste gaussiano no converge sobre datos de fotodiodo simulados
        (ruido plano), no debe lanzar — conserva el centro de masa como respaldo."""
        try:
            x_opt, y_opt = optical_support.run_confocal_centering(range_um=1.0, pixels=8, method="center_of_gauss")
        except Exception as e:
            self.fail(f"run_confocal_centering (gauss) lanzó una excepción: {e}")
        self.assertIsInstance(x_opt, float)
        self.assertIsInstance(y_opt, float)

    def test_run_confocal_centering_moves_stage_to_returned_coordinates(self):
        x_opt, y_opt = optical_support.run_confocal_centering(range_um=1.0, pixels=5, method="center_of_mass")
        x_final, y_final, _ = optical_support.get_stage_coordinates()
        self.assertAlmostEqual(x_final, x_opt, places=2)
        self.assertAlmostEqual(y_final, y_opt, places=2)

    def test_run_confocal_centering_respects_stage_range_clamp(self):
        from config import PI_STAGE_RANGE_UM
        x_opt, y_opt = optical_support.run_confocal_centering(range_um=1.0, pixels=5, method="center_of_mass")
        self.assertGreaterEqual(x_opt, 0.0)
        self.assertLessEqual(x_opt, PI_STAGE_RANGE_UM)
        self.assertGreaterEqual(y_opt, 0.0)
        self.assertLessEqual(y_opt, PI_STAGE_RANGE_UM)

    def test_optical_support_functions_run_sequentially_without_thread_collisions(self):
        """Ejecuta autofoco + centrado en secuencia en el mismo hilo (llamante): no debe
        colgarse ni lanzar (verifica ausencia de colisiones de afinidad de hilo Qt)."""
        try:
            optical_support.run_z_autofocus(timeout_s=10.0)
            optical_support.run_confocal_centering(range_um=1.0, pixels=5)
            optical_support.get_stage_coordinates()
        except Exception as e:
            self.fail(f"Secuencia de soporte óptico lanzó una excepción: {e}")


if __name__ == "__main__":
    unittest.main()
