# -*- coding: utf-8 -*-
"""
test_pyspectrum_luminescence_and_calibration.py — Fase 7 (DEC-021)
Verifica: (1) el control del Flipper Notch 532 nm y el ciclo de vida del obturador en la
grilla de Luminiscencia, (2) la verificación de calibración con agua y el perfil de ruido
oscuro en Calibraciones, (3) los atajos de teclado globales del shell principal, y (4) la
resiliencia ante E-STOP con liberación limpia de sesiones de hardware.
"""
from __future__ import annotations
import os
import tempfile
import unittest

import numpy as np
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore import QEventLoop, QTimer

import config  # noqa: F401  (orden de import: config antes de PyQt6, ver conftest.py)

from pyspectrum.drivers.andor_ccd_driver import get_andor_ccd
from pyspectrum.drivers.shamrock_driver import get_shamrock
from pyspectrum.modules.hardware_session import hardware_session
from pyspectrum.modules.routines import luminescence
from pyspectrum.modules.routines.luminescence import LuminescenceBackend, LuminescenceWidget
from pyspectrum.modules.calibration_dock import CalibrationBackend, CalibrationFrontend
from pyspectrum.window import PySpectrumWindow, TAB_EXPLORATION, TAB_STATIC_RAMAN, TAB_LUMINESCENCE

_app = QApplication.instance() or QApplication([])


def _wait_for_signal(signal, timeout_s: float = 10.0):
    loop = QEventLoop()
    signal.connect(loop.quit)
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    timer.start(int(timeout_s * 1000))
    loop.exec()
    timer.stop()
    signal.disconnect(loop.quit)


class TestLuminescenceNotchFlipperAndGrid(unittest.TestCase):
    def setUp(self):
        self.camera = get_andor_ccd(force_mock=True, reset=True)
        self.spectrometer = get_shamrock(force_mock=True, reset=True)
        hardware_session.clear_emergency()
        if hardware_session.is_busy:
            hardware_session.release_session(hardware_session.current_owner)

        self.widget = LuminescenceWidget()
        self.backend = LuminescenceBackend(self.camera, self.spectrometer)
        self.backend.make_connection(self.widget)

        self._orig_autofocus = luminescence.run_z_autofocus
        luminescence.run_z_autofocus = lambda **kw: True

    def tearDown(self):
        luminescence.run_z_autofocus = self._orig_autofocus
        hardware_session.clear_emergency()
        if hardware_session.is_busy:
            hardware_session.release_session(hardware_session.current_owner)
        self.widget.close()

    def test_notch_flipper_defaults_to_inserted_and_toggles(self):
        self.assertTrue(self.backend._notch_down, "El estado seguro por defecto debe ser 'dentro del haz'")

        states = []
        self.backend.notchStateChangedSignal.connect(states.append)

        self.widget.notchFlipperSignal.emit(False)  # retirar
        self.assertFalse(self.backend._notch_down)
        self.assertIn("arriba", self.widget.lbl_notch_status.text())  # es el espejo de detección

        self.widget.notchFlipperSignal.emit(True)  # insertar
        self.assertTrue(self.backend._notch_down)
        self.assertIn("abajo", self.widget.lbl_notch_status.text())

        self.assertEqual(states, [False, True])

    def test_grid_generation_and_full_node_run_with_shutter_lifecycle(self):
        self.backend.generate_grid(1, 2, 3.0, 0.0, 5.0, 5.0, 5.0)
        self.assertEqual(len(self.backend._pending_nodes), 2)

        shutter_events = []
        orig_open, orig_close = luminescence.open_shutter, luminescence.close_shutter
        luminescence.open_shutter = lambda name, *a, **kw: (shutter_events.append(("open", name)), orig_open(name))[-1]
        luminescence.close_shutter = lambda name: (shutter_events.append(("close", name)), orig_close(name))[-1]

        try:
            config_dict = {"laser": "532 nm (green)", "exp_time": 0.02, "autofocus_every": 1, "save_dir": tempfile.mkdtemp(),
                           "mirror": "down"}  # AND-1: el operador confirma el espejo
            self.backend.start_grid(config_dict)
            _wait_for_signal(self.backend.gridFinishedSignal, timeout_s=10.0)
        finally:
            luminescence.open_shutter = orig_open
            luminescence.close_shutter = orig_close

        self.assertEqual(self.backend.idx, 2)
        self.assertEqual(shutter_events.count(("open", "532 nm (green)")), 2)
        self.assertEqual(shutter_events.count(("close", "532 nm (green)")), 2)
        self.assertFalse(hardware_session.is_busy)

    def test_grid_acquisition_is_read_mode_aware(self):
        """AND-1: el espectro es una exposición real 1D; desde Imagen se pasa a FVB, Single-Track se respeta."""
        from pyspectrum.drivers.andor_ccd_driver import READ_MODE_IMAGE, READ_MODE_FVB
        from pyspectrum.modules.routines.grid_runner import GridRunner
        runner = GridRunner(self.camera, tick=lambda: None)
        self.camera.set_read_mode(READ_MODE_IMAGE)
        spec, mode = runner.spectrum_1d(0.01)
        self.assertEqual(spec.shape, (1004,))
        self.assertEqual(self.camera.get_read_mode(), READ_MODE_FVB)
        self.assertIn("FVB", mode)

    def test_emergency_stop_during_grid_closes_shutter_and_ends_without_hang(self):
        self.backend.generate_grid(1, 1, 3.0, 0.0, 5.0, 5.0, 5.0)

        shutter_events = []
        orig_open, orig_close = luminescence.open_shutter, luminescence.close_shutter
        luminescence.open_shutter = lambda name, *a, **kw: (shutter_events.append(("open", name)), orig_open(name))[-1]
        luminescence.close_shutter = lambda name: (shutter_events.append(("close", name)), orig_close(name))[-1]

        # Fuerza el E-STOP apenas se solicite el nodo (antes de que la adquisición corta termine).
        QTimer.singleShot(5, hardware_session.emergency_stop)

        try:
            config_dict = {"laser": "808 nm (IR)", "exp_time": 0.02, "autofocus_every": 1, "save_dir": tempfile.mkdtemp(),
                           "mirror": "down"}
            self.backend.start_grid(config_dict)
            _wait_for_signal(self.backend.gridFinishedSignal, timeout_s=10.0)
        finally:
            luminescence.open_shutter = orig_open
            luminescence.close_shutter = orig_close

        self.assertFalse(self.backend._grid_running)
        self.assertFalse(hardware_session.is_busy)
        self.assertTrue(hardware_session.is_emergency_stopped)


class TestCalibrationWaterAndDarkNoiseRetired(unittest.TestCase):
    """Retiradas por el investigador (2026-09-30, DEC-040). La verificación con agua abría el 532, leía un
    cuadro sin adquirir y, sin banda, informaba corrimiento 0; el ruido oscuro no verificaba el cierre de
    los obturadores y caracterizaba con un cuadro viejo. El fondo se toma en cada procedimiento, con la
    misma configuración y todo apagado o el obturador cerrado."""

    def setUp(self):
        self.frontend = CalibrationFrontend()
        self.backend = CalibrationBackend(get_andor_ccd(force_mock=True), get_shamrock(force_mock=True))
        self.backend.make_connection(self.frontend)

    def test_the_actions_no_longer_exist(self):
        for name in ("btn_verify_water", "btn_measure_dark", "btn_save_dark_profile",
                     "verifyWaterCalibrationSignal", "measureDarkNoiseSignal", "saveDarkNoiseProfileSignal"):
            self.assertFalse(hasattr(self.frontend, name), name)
        for name in ("verify_water_calibration", "measure_dark_noise", "save_dark_noise_profile",
                     "waterVerificationResultSignal", "darkNoiseResultSignal"):
            self.assertFalse(hasattr(self.backend, name), name)
        import pyspectrum.modules.calibration_dock as calib_mod
        self.assertFalse(hasattr(calib_mod, "DARK_NOISE_PROFILE_FILE"))

    def test_the_dock_says_what_replaces_them(self):
        text = self.frontend.lbl_retired.text()
        self.assertIn("Calibración de λ (automática)", text)
        self.assertIn("fondo", text.lower())


class TestGlobalKeyboardShortcuts(unittest.TestCase):
    def setUp(self):
        self._orig_question = QMessageBox.question
        self._orig_critical = QMessageBox.critical
        # Ambos métodos de QMessageBox bloquean modalmente bajo QT_QPA_PLATFORM=offscreen si no
        # se mockean por separado (hallazgo recurrente de la Fase 5, DEC-019): .question() lo
        # dispara closeEvent(), .critical() lo dispara _on_emergency_stop_clicked().
        QMessageBox.question = lambda *a, **k: QMessageBox.StandardButton.Yes
        QMessageBox.critical = lambda *a, **k: None
        hardware_session.clear_emergency()
        if hardware_session.is_busy:
            hardware_session.release_session(hardware_session.current_owner)
        self.win = PySpectrumWindow()

    def tearDown(self):
        self.win.close()
        QMessageBox.question = self._orig_question
        QMessageBox.critical = self._orig_critical
        hardware_session.clear_emergency()
        if hardware_session.is_busy:
            hardware_session.release_session(hardware_session.current_owner)

    def test_seven_tab_shortcuts_registered_and_switch_tabs(self):
        self.assertEqual(len(self.win.shortcuts_tabs), 7)
        self.win.shortcuts_tabs[TAB_LUMINESCENCE].activated.emit()
        self.assertEqual(self.win.tabs_workflow.currentIndex(), TAB_LUMINESCENCE)
        self.win.shortcuts_tabs[TAB_EXPLORATION].activated.emit()
        self.assertEqual(self.win.tabs_workflow.currentIndex(), TAB_EXPLORATION)

    def test_ctrl_space_toggles_live_view_on_exploration_tab(self):
        self.win.tabs_workflow.setCurrentIndex(TAB_EXPLORATION)
        was_checked = self.win.exploration_widget.btn_live.isChecked()
        self.win.shortcut_live_view.activated.emit()
        self.assertNotEqual(self.win.exploration_widget.btn_live.isChecked(), was_checked)
        # Revertir para dejar el estado limpio para otros tests / tearDown.
        self.win.shortcut_live_view.activated.emit()

    def test_ctrl_space_is_noop_on_tabs_without_live_view(self):
        self.win.tabs_workflow.setCurrentIndex(TAB_LUMINESCENCE)
        try:
            self.win.shortcut_live_view.activated.emit()
        except Exception as e:
            self.fail(f"El atajo Ctrl+Space no debe lanzar excepción en pestañas sin Live View: {e}")

    def test_ctrl_r_dispatches_to_the_correct_primary_button_per_tab(self):
        """Verifica el ruteo de Ctrl+R sin disparar adquisiciones reales: reemplaza el método
        .click() de cada botón candidato por un espía y confirma que sólo el de la pestaña
        activa se invoca."""
        targets = {
            TAB_STATIC_RAMAN: self.win.raman_container.spectrum_widget.btn_single,
            self.win.tabs_workflow.indexOf(self.win.sandg_widget): self.win.sandg_widget.btn_single,
            self.win.tabs_workflow.indexOf(self.win.growth_widget): self.win.growth_widget.btn_run,
            self.win.tabs_workflow.indexOf(self.win.confocal_widget): self.win.confocal_widget.btn_scan,
            TAB_LUMINESCENCE: self.win.lumin_widget.btn_run,
        }
        spies = {}
        originals = {}
        for btn in targets.values():
            originals[id(btn)] = btn.click
            calls = []
            spies[id(btn)] = calls
            btn.click = lambda calls=calls: calls.append(True)

        try:
            for idx, btn in targets.items():
                for other_btn in targets.values():
                    spies[id(other_btn)].clear()
                self.win.tabs_workflow.setCurrentIndex(idx)
                self.win.shortcut_measure.activated.emit()
                self.assertEqual(len(spies[id(btn)]), 1, f"El botón esperado para la pestaña {idx} no fue invocado")
                for other_idx, other_btn in targets.items():
                    if other_idx != idx:
                        self.assertEqual(len(spies[id(other_btn)]), 0, f"Se invocó por error el botón de la pestaña {other_idx}")

            # Pestañas sin acción primaria de medición (Exploración, Calibraciones): no debe lanzar.
            for idx in (TAB_EXPLORATION, self.win.tabs_workflow.indexOf(self.win.calib_widget)):
                self.win.tabs_workflow.setCurrentIndex(idx)
                try:
                    self.win.shortcut_measure.activated.emit()
                except Exception as e:
                    self.fail(f"Ctrl+R no debe lanzar excepción en la pestaña {idx}: {e}")
        finally:
            for btn in targets.values():
                btn.click = originals[id(btn)]

    def test_estop_shortcut_triggers_emergency_stop(self):
        hardware_session.emergency_stop()
        hardware_session.clear_emergency()
        self.assertFalse(hardware_session.is_emergency_stopped)

        self.win.shortcut_estop_ctrl.activated.emit()
        self.assertTrue(hardware_session.is_emergency_stopped)
        hardware_session.clear_emergency()

    def test_estop_keys_fire_while_a_modal_dialog_has_focus(self):
        """H-01 / C-30: con un diálogo modal abierto sobre la ventana, Qt bloquea sus atajos en
        cualquier contexto (también ApplicationShortcut: verificado), así que la E-STOP por
        teclado quedaba muerta justo cuando el operador está confirmando algo sobre el equipo.
        La ventana instala un filtro de aplicación que la dispara igual, una vez por pulsación."""
        from unittest import mock
        from PyQt6.QtCore import Qt
        from PyQt6.QtTest import QTest
        from PyQt6.QtWidgets import QDialog

        for key, modifier in ((Qt.Key.Key_F12, Qt.KeyboardModifier.NoModifier),
                              (Qt.Key.Key_E, Qt.KeyboardModifier.ControlModifier)):
            dialog = QDialog(self.win)
            dialog.setModal(True)
            dialog.show()
            dialog.activateWindow()
            QApplication.processEvents()
            try:
                with mock.patch.object(hardware_session, "emergency_stop") as estop:
                    QTest.keyClick(dialog, key, modifier)
                    QApplication.processEvents()
                self.assertEqual(estop.call_count, 1,
                                 f"la E-STOP por teclado debe dispararse una vez con un diálogo modal abierto ({key})")
            finally:
                dialog.close()
                dialog.deleteLater()
                QApplication.processEvents()

    def test_estop_key_fires_once_without_dialog(self):
        from unittest import mock
        from PyQt6.QtCore import Qt
        from PyQt6.QtTest import QTest

        self.win.show()
        self.win.activateWindow()
        QApplication.processEvents()
        with mock.patch.object(hardware_session, "emergency_stop") as estop:
            QTest.keyClick(self.win, Qt.Key.Key_F12)
            QApplication.processEvents()
        self.assertEqual(estop.call_count, 1)

    def test_estop_key_ignored_in_unrelated_windows(self):
        """Una ventana ajena a PySpectrum en el mismo proceso no dispara su E-STOP."""
        from unittest import mock
        from PyQt6.QtCore import Qt
        from PyQt6.QtTest import QTest
        from PyQt6.QtWidgets import QMainWindow

        other = QMainWindow()
        other.show()
        other.activateWindow()
        QApplication.processEvents()
        try:
            with mock.patch.object(hardware_session, "emergency_stop") as estop:
                QTest.keyClick(other, Qt.Key.Key_F12)
                QApplication.processEvents()
            self.assertEqual(estop.call_count, 0)
        finally:
            other.close()
            other.deleteLater()

if __name__ == "__main__":
    unittest.main()
