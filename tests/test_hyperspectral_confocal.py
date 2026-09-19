# -*- coding: utf-8 -*-
"""
test_hyperspectral_confocal.py — Pruebas unitarias para las correcciones de seguridad de
pyspectrum/modules/hyperspectral_confocal.py y pyspectrum/window.py (auditoría
multi-agente 2026-09-18, hallazgos ANOM-HYPERSPEC-01/02):

1. ANOM-HYPERSPEC-02: el mapeo hiperespectral no tenía ningún selector de láser de
   excitación ni ciclo de vida de obturador — start_scan()/stop_scan() ahora abren y
   cierran el láser seleccionado, y _scan_step() renueva el watchdog en cada punto.
2. ANOM-HYPERSPEC-01: ConfocalBackend se mueve a un QThread real (segunda excepción
   arquitectónica del proyecto junto a linescan_spectroscopy.py / DEC-006) — antes cada
   punto del mapa (pi.MOV + exposición/lectura CCD bloqueante) corría en el hilo GUI,
   congelando toda la ventana (incluido el Stop/E-STOP) por la duración de cada
   exposición. Se verifica también que PySpectrumWindow.closeEvent() invoque stop_scan()
   de forma segura entre hilos (QMetaObject.invokeMethod), no con una llamada directa que
   tocaría el QTimer del otro hilo sin marshalling.

PyPrinting 3.0 / PySpectrum 3.0 — UNSAM Nanofotónica
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

from PyQt6 import QtWidgets, QtCore
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

import config  # noqa: F401
from config import SHUTTERS, SHUTTER_POLARITY
from core import nidaq
from core.nidaq import is_watchdog_armed
from pyspectrum.drivers.shamrock_driver import get_shamrock
from pyspectrum.drivers.andor_ccd_driver import get_andor_ccd
from pyspectrum.modules.hardware_session import hardware_session
from pyspectrum.modules import hyperspectral_confocal
from pyspectrum.window import PySpectrumWindow


class TestHyperspectralShutterLifecycle(unittest.TestCase):
    """ANOM-HYPERSPEC-02: selector de láser + apertura/cierre de obturador."""

    def setUp(self):
        self.camera = get_andor_ccd(force_mock=True)
        self.spectrometer = get_shamrock(force_mock=True)

    def tearDown(self):
        hardware_session.clear_emergency()
        nidaq.close_all_shutters()

    def test_frontend_exposes_laser_combo_populated_with_shutters(self):
        fe = hyperspectral_confocal.Frontend()
        self.assertTrue(hasattr(fe, "combo_laser"))
        items = [fe.combo_laser.itemText(i) for i in range(fe.combo_laser.count())]
        self.assertEqual(items, list(SHUTTERS))

    def test_start_scan_opens_selected_laser_and_stop_closes_it(self):
        laser = SHUTTERS[-1]
        idx = SHUTTERS.index(laser)
        self.assertEqual(nidaq._shutter_signal[idx], not SHUTTER_POLARITY[laser],
                          "Precondición: el shutter debe iniciar cerrado")

        be = hyperspectral_confocal.Backend(self.camera, self.spectrometer)
        be.start_scan(45.0, 50.0, 45.0, 50.0, 1.0, 0.05, laser)
        self.assertEqual(be.laser_in_use, laser)
        self.assertEqual(nidaq._shutter_signal[idx], SHUTTER_POLARITY[laser],
                          "start_scan() debe abrir el láser seleccionado")

        be.stop_scan()
        self.assertEqual(nidaq._shutter_signal[idx], not SHUTTER_POLARITY[laser],
                          "stop_scan() debe cerrar el láser abierto")
        self.assertEqual(be.laser_in_use, "")

    def test_start_scan_defaults_laser_when_omitted(self):
        """Compatibilidad hacia atrás: llamadas directas sin el argumento laser (como las
        de la suite pre-existente test_pyspectrum_stability_safety.py) no deben romperse
        ni dejar el mapeo sin ningún láser seleccionado."""
        be = hyperspectral_confocal.Backend(self.camera, self.spectrometer)
        be.start_scan(45.0, 50.0, 45.0, 50.0, 1.0, 0.05)  # sin 7mo argumento
        self.assertEqual(be.laser_in_use, SHUTTERS[0])
        be.stop_scan()

    def test_scan_step_renews_watchdog_heartbeat(self):
        laser = SHUTTERS[0]
        be = hyperspectral_confocal.Backend(self.camera, self.spectrometer)
        be.start_scan(45.0, 47.0, 45.0, 47.0, 1.0, 0.01, laser)
        self.assertTrue(is_watchdog_armed())

        # Forzar un timeout global corto y confirmar que _scan_step() (llamado
        # manualmente, sin esperar al QTimer real) lo renueva en cada punto.
        nidaq.set_default_shutter_timeout(0.2)
        try:
            import time
            for _ in range(4):
                time.sleep(0.05)
                be._scan_step()
                idx = SHUTTERS.index(laser)
                self.assertEqual(nidaq._shutter_signal[idx], SHUTTER_POLARITY[laser],
                                  "El obturador no debe cerrarse mientras _scan_step siga renovando el heartbeat")
        finally:
            nidaq.set_default_shutter_timeout(30.0)
        be.stop_scan()

    def test_emergency_stop_closes_shutter_during_scan(self):
        laser = SHUTTERS[0]
        idx = SHUTTERS.index(laser)
        be = hyperspectral_confocal.Backend(self.camera, self.spectrometer)
        be.start_scan(45.0, 50.0, 45.0, 50.0, 1.0, 0.05, laser)
        self.assertEqual(nidaq._shutter_signal[idx], SHUTTER_POLARITY[laser])

        hardware_session.emergency_stop()
        # La señal emergencyStopSignal -> stop_scan() está conectada en __init__; en este
        # test el Backend no fue movido a un QThread (conexión directa, mismo hilo), así
        # que se ejecuta sincrónicamente.
        self.assertEqual(nidaq._shutter_signal[idx], not SHUTTER_POLARITY[laser],
                          "El E-STOP debe cerrar el obturador incluso a mitad de mapeo")


class TestHyperspectralQThreadTopology(unittest.TestCase):
    """ANOM-HYPERSPEC-01: ConfocalBackend movido a un QThread real."""

    def tearDown(self):
        hardware_session.clear_emergency()
        nidaq.close_all_shutters()

    def test_confocal_backend_lives_on_its_own_thread(self):
        orig_question = QtWidgets.QMessageBox.question
        QtWidgets.QMessageBox.question = lambda *a, **k: QtWidgets.QMessageBox.StandardButton.Yes
        try:
            win = PySpectrumWindow()
            self.assertIsNotNone(win.confocal_thread)
            self.assertIs(win.confocal_backend.thread(), win.confocal_thread)
            self.assertIsNot(win.confocal_backend.thread(), QtCore.QThread.currentThread())
            # scan_timer se parenta a self dentro de Backend.__init__: debe migrar con moveToThread()
            self.assertIs(win.confocal_backend.scan_timer.thread(), win.confocal_thread)
            win.close()
        finally:
            QtWidgets.QMessageBox.question = orig_question

    def test_window_close_stops_confocal_thread_cleanly(self):
        """closeEvent() debe detener el scan (vía QMetaObject.invokeMethod, sin tocar el
        QTimer del otro hilo directamente) y luego parar/unir confocal_thread sin colgar."""
        orig_question = QtWidgets.QMessageBox.question
        QtWidgets.QMessageBox.question = lambda *a, **k: QtWidgets.QMessageBox.StandardButton.Yes
        try:
            win = PySpectrumWindow()
            win.confocal_backend.start_scan(45.0, 55.0, 45.0, 55.0, 1.0, 0.01, SHUTTERS[0])
            win.close()  # no debe lanzar ni colgar
            self.assertFalse(win.confocal_thread.isRunning())
        finally:
            QtWidgets.QMessageBox.question = orig_question


if __name__ == "__main__":
    unittest.main()
