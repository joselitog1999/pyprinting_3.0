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
from pyspectrum.modules.calibration_dock import CalibrationBackend, CalibrationFrontend, DARK_NOISE_PROFILE_FILE
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
        self.assertIn("Fuera del haz", self.widget.lbl_notch_status.text())

        self.widget.notchFlipperSignal.emit(True)  # insertar
        self.assertTrue(self.backend._notch_down)
        self.assertIn("Dentro del haz", self.widget.lbl_notch_status.text())

        self.assertEqual(states, [False, True])

    def test_grid_generation_and_full_node_run_with_shutter_lifecycle(self):
        self.backend.generate_grid(1, 2, 3.0, 0.0, 5.0, 5.0, 5.0)
        self.assertEqual(len(self.backend._pending_nodes), 2)

        shutter_events = []
        orig_open, orig_close = luminescence.open_shutter, luminescence.close_shutter
        luminescence.open_shutter = lambda name, *a, **kw: (shutter_events.append(("open", name)), orig_open(name))[-1]
        luminescence.close_shutter = lambda name: (shutter_events.append(("close", name)), orig_close(name))[-1]

        try:
            config_dict = {"laser": "532 nm (green)", "exp_time": 0.02, "autofocus_every": 1, "save_dir": tempfile.mkdtemp()}
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
        from pyspectrum.drivers.andor_ccd_driver import READ_MODE_IMAGE, READ_MODE_FVB

        self.camera._read_mode = READ_MODE_IMAGE
        spec_2d = self.backend._acquire_read_mode_aware()
        self.assertEqual(spec_2d.ndim, 1)
        self.assertEqual(len(spec_2d), self.camera.width)

        self.camera._read_mode = READ_MODE_FVB
        spec_1d = self.backend._acquire_read_mode_aware()
        self.assertEqual(spec_1d.ndim, 1)

    def test_emergency_stop_during_grid_closes_shutter_and_ends_without_hang(self):
        self.backend.generate_grid(1, 1, 3.0, 0.0, 5.0, 5.0, 5.0)

        shutter_events = []
        orig_open, orig_close = luminescence.open_shutter, luminescence.close_shutter
        luminescence.open_shutter = lambda name, *a, **kw: (shutter_events.append(("open", name)), orig_open(name))[-1]
        luminescence.close_shutter = lambda name: (shutter_events.append(("close", name)), orig_close(name))[-1]

        # Fuerza el E-STOP apenas se solicite el nodo (antes de que la adquisición corta termine).
        QTimer.singleShot(5, hardware_session.emergency_stop)

        try:
            config_dict = {"laser": "808 nm (IR)", "exp_time": 0.02, "autofocus_every": 1, "save_dir": tempfile.mkdtemp()}
            self.backend.start_grid(config_dict)
            _wait_for_signal(self.backend.gridFinishedSignal, timeout_s=10.0)
        finally:
            luminescence.open_shutter = orig_open
            luminescence.close_shutter = orig_close

        self.assertFalse(self.backend._grid_running)
        self.assertFalse(hardware_session.is_busy)
        self.assertTrue(hardware_session.is_emergency_stopped)


class TestCalibrationWaterAndDarkNoise(unittest.TestCase):
    def setUp(self):
        self.camera = get_andor_ccd(force_mock=True, reset=True)
        self.spectrometer = get_shamrock(force_mock=True, reset=True)
        hardware_session.clear_emergency()
        if hardware_session.is_busy:
            hardware_session.release_session(hardware_session.current_owner)

        self.frontend = CalibrationFrontend()
        self.backend = CalibrationBackend(self.camera, self.spectrometer)
        self.backend.make_connection(self.frontend)

    def tearDown(self):
        hardware_session.clear_emergency()
        if hardware_session.is_busy:
            hardware_session.release_session(hardware_session.current_owner)
        if DARK_NOISE_PROFILE_FILE.exists():
            try:
                DARK_NOISE_PROFILE_FILE.unlink()
            except OSError:
                pass

    def test_water_verification_reports_shift_from_known_synthetic_peak(self):
        wave_axis = np.linspace(500.0, 800.0, 1004)
        # Pico Raman de agua sintético a 650.5 nm (1.5 nm de corrimiento respecto al teórico 649.0 nm)
        spec = 300.0 + 4000.0 * np.exp(-0.5 * ((wave_axis - 650.5) / 3.0) ** 2)
        self.backend.camera.get_1d_spectrum = lambda: spec
        self.backend.camera.get_read_mode = lambda: 0  # READ_MODE_FVB
        self.backend.spectrometer.ShamrockGetCalibration = lambda dev, n: (0, wave_axis)

        results = []
        self.backend.waterVerificationResultSignal.connect(
            lambda shift, obs, r2, wr, sr, wf, sf: results.append((shift, obs, r2))
        )

        self.backend.verify_water_calibration()

        self.assertEqual(len(results), 1)
        shift_nm, observed_peak_nm, r2 = results[0]
        self.assertAlmostEqual(observed_peak_nm, 650.5, delta=1.0)
        self.assertAlmostEqual(shift_nm, 1.5, delta=1.0)
        self.assertIn("Corrimiento", self.frontend.lbl_water_status.text())
        self.assertFalse(hardware_session.is_busy)

    def test_dark_noise_measurement_closes_all_shutters_and_enables_save(self):
        closed_calls = []
        orig_close_all = luminescence.close_shutter  # sólo para asegurar import limpio, no usado directamente
        import pyspectrum.modules.calibration_dock as calib_mod
        orig_close_all_shutters = calib_mod.close_all_shutters
        calib_mod.close_all_shutters = lambda: closed_calls.append(True)

        try:
            self.assertFalse(self.frontend.btn_save_dark_profile.isEnabled())
            self.backend.measure_dark_noise()
        finally:
            calib_mod.close_all_shutters = orig_close_all_shutters

        self.assertEqual(len(closed_calls), 1, "measure_dark_noise debe cerrar todos los obturadores antes de adquirir")
        self.assertGreaterEqual(self.backend._last_dark_mean, 0.0)
        self.assertGreaterEqual(self.backend._last_dark_std, 0.0)
        self.assertTrue(self.frontend.btn_save_dark_profile.isEnabled())
        self.assertFalse(hardware_session.is_busy)

    def test_save_dark_noise_profile_persists_npz_with_expected_keys(self):
        self.backend.measure_dark_noise()
        self.backend.save_dark_noise_profile()

        self.assertTrue(DARK_NOISE_PROFILE_FILE.exists())
        with np.load(str(DARK_NOISE_PROFILE_FILE), allow_pickle=True) as data:
            self.assertIn("dark_frame", data)
            self.assertIn("mean_counts", data)
            self.assertIn("std_counts", data)
            self.assertAlmostEqual(float(data["mean_counts"]), self.backend._last_dark_mean, places=4)

    def test_save_dark_noise_profile_without_measurement_is_safe_no_op(self):
        # No debe lanzar excepción ni crear el archivo si no se midió nada todavía.
        self.backend.save_dark_noise_profile()
        self.assertFalse(DARK_NOISE_PROFILE_FILE.exists())


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
