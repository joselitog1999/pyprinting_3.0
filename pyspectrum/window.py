# -*- coding: utf-8 -*-
"""
window.py — Ventana Principal de PySpectrum 3.0
PyPrinting 3.0 — UNSAM Nanofotónica
"""
from __future__ import annotations
import os
import sys
import time
from pathlib import Path
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import pyqtSignal, pyqtSlot, QThread
from pyqtgraph.dockarea import DockArea, Dock

from config import SAFE_MODE, PI_SERIAL
from core.nanopositioning import Frontend as NanoFrontend, Backend as NanoBackend
from core.shutters import Frontend as ShuttersFrontend, Backend as ShuttersBackend
from pyspectrum.drivers.shamrock_driver import get_shamrock
from pyspectrum.drivers.andor_ccd_driver import get_andor_ccd

from pyspectrum.modules.spectrum_control import Frontend as SpectrumFrontend, Backend as SpectrumBackend
from pyspectrum.modules.camera_andor import Frontend as CameraFrontend, Backend as CameraBackend
from pyspectrum.modules.step_and_glue import Frontend as StepGlueFrontend, Backend as StepGlueBackend
from pyspectrum.modules.hyperspectral_confocal import Frontend as ConfocalFrontend, Backend as ConfocalBackend
from pyspectrum.modules.static_raman import StaticRamanWidget, StaticRamanBackend

from pyspectrum.modules.routines.luminescence import LuminescenceWidget, LuminescenceBackend
from pyspectrum.modules.routines.growth_kinetics import GrowthKineticsWidget, GrowthKineticsBackend
from pyspectrum.modules.routines.dimers import DimersWidget, DimersBackend
from modules.hardware_dashboard import HardwareDashboardWindow


class PySpectrumWindow(QtWidgets.QMainWindow):
    """Ventana Principal de PySpectrum 3.0."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("PySpectrum 3.0 — Espectroscopía & Mapeo Hiperespectral (UNSAM Nanofotónica)")
        self.resize(1360, 840)
        self.setMinimumSize(1000, 680)

        self.work_dir = Path.home() / "Documents" / "Data_PySpectrum"
        self.work_dir.mkdir(parents=True, exist_ok=True)

        self._setup_styles()
        self._setup_menu()
        self._setup_ui()
        self._setup_threads_and_backends()

    def _setup_styles(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #11111B;
            }
            QMenuBar {
                background-color: #181825;
                color: #CDD6F4;
                font-weight: bold;
                border-bottom: 1px solid #313244;
            }
            QMenuBar::item:selected {
                background-color: #313244;
                color: #89B4FA;
            }
            QMenu {
                background-color: #181825;
                color: #CDD6F4;
                border: 1px solid #45475A;
            }
            QMenu::item:selected {
                background-color: #89B4FA;
                color: #11111B;
            }
            QStatusBar {
                background-color: #181825;
                color: #A6ADC8;
                font-size: 9pt;
            }
        """)

    def _setup_menu(self):
        menubar = self.menuBar()

        # ── Menú Archivo ──────────────────────────────────────────────────────
        file_menu = menubar.addMenu("📁 Archivo")

        act_select_dir = QtGui.QAction("Seleccionar Directorio de Trabajo", self)
        act_select_dir.triggered.connect(self._select_directory)
        file_menu.addAction(act_select_dir)

        act_daily_dir = QtGui.QAction("Crear Carpeta del Día (AAAA-MM-DD)", self)
        act_daily_dir.triggered.connect(self._create_daily_directory)
        file_menu.addAction(act_daily_dir)

        act_open_dir = QtGui.QAction("Abrir Carpeta de Datos en Explorador", self)
        act_open_dir.triggered.connect(self._open_directory)
        file_menu.addAction(act_open_dir)

        file_menu.addSeparator()
        act_exit = QtGui.QAction("Salir", self)
        act_exit.triggered.connect(self.close)
        file_menu.addAction(act_exit)

        # ── Menú Herramientas Ópticas ─────────────────────────────────────────
        tools_menu = menubar.addMenu("🔧 Herramientas")

        act_nano = QtGui.QAction("Platina Nanoposicionamiento (PI Piezo)", self)
        act_nano.triggered.connect(self._open_nano_dialog)
        tools_menu.addAction(act_nano)

        act_shutters = QtGui.QAction("Obturadores & Flippers Láser", self)
        act_shutters.triggered.connect(self._open_shutters_dialog)
        tools_menu.addAction(act_shutters)

        tools_menu.addSeparator()
        act_hw = QtGui.QAction("Tablero de Hardware & Conexiones", self)
        act_hw.triggered.connect(self._open_hardware_dashboard)
        tools_menu.addAction(act_hw)

        # ── Menú Rutinas Especializadas ───────────────────────────────────────
        routines_menu = menubar.addMenu("🧪 Rutinas")

        act_static_raman = QtGui.QAction("🔬 Espectroscopía Raman Estática & Termometría", self)
        act_static_raman.triggered.connect(lambda: self.dock_raman.raise_())
        routines_menu.addAction(act_static_raman)

        routines_menu.addSeparator()

        act_lumin = QtGui.QAction("Luminiscencia & Anti-Stokes", self)
        act_lumin.triggered.connect(self._open_luminescence)
        routines_menu.addAction(act_lumin)

        act_growth = QtGui.QAction("Cinética de Crecimiento de Nanopartículas", self)
        act_growth.triggered.connect(self._open_growth)
        routines_menu.addAction(act_growth)

        act_dimers = QtGui.QAction("Caracterización de Dímeros Plasmónicos", self)
        act_dimers.triggered.connect(self._open_dimers)
        routines_menu.addAction(act_dimers)

    def _setup_ui(self):
        self.dock_area = DockArea()
        self.setCentralWidget(self.dock_area)

        # ── Docks Modulares ───────────────────────────────────────────────────
        self.dock_camera = Dock("📷 Cámara Andor CCD (Detector)", size=(500, 500))
        self.cam_widget = CameraFrontend()
        self.dock_camera.addWidget(self.cam_widget)
        self.dock_area.addDock(self.dock_camera, 'left')

        self.dock_spectrometer = Dock("🌈 Espectrógrafo Andor Shamrock", size=(500, 260))
        self.spec_widget = SpectrumFrontend()
        self.dock_spectrometer.addWidget(self.spec_widget)
        self.dock_area.addDock(self.dock_spectrometer, 'bottom', self.dock_camera)

        self.dock_sandg = Dock("🧩 Espectroscopía & Step and Glue", size=(650, 400))
        self.sandg_widget = StepGlueFrontend()
        self.dock_sandg.addWidget(self.sandg_widget)
        self.dock_area.addDock(self.dock_sandg, 'right')

        self.dock_raman = Dock("🔬 Espectroscopía Raman Estática & Termometría", size=(650, 400))
        self.raman_widget = StaticRamanWidget()
        self.dock_raman.addWidget(self.raman_widget)
        self.dock_area.addDock(self.dock_raman, 'above', self.dock_sandg)

        self.dock_confocal = Dock("🧬 Mapeo Confocal Hiperespectral (X, Y, λ)", size=(650, 360))
        self.confocal_widget = ConfocalFrontend()
        self.dock_confocal.addWidget(self.confocal_widget)
        self.dock_area.addDock(self.dock_confocal, 'bottom', self.dock_sandg)

        self.statusBar().showMessage(f"PySpectrum 3.0 Listo. Carpeta de trabajo: {self.work_dir}")

    def _setup_threads_and_backends(self):
        from core.hardware_manager import hardware_manager
        from config import pi
        hardware_manager.set_profile("pyspectrum", rescan=False)
        pi.connect()

        self.spectrometer = get_shamrock()
        self.camera = get_andor_ccd()

        self.spec_backend = SpectrumBackend(self.spectrometer)
        self.spec_backend.make_connection(self.spec_widget)

        self.cam_backend = CameraBackend(self.camera)
        self.cam_backend.make_connection(self.cam_widget)

        self.sandg_backend = StepGlueBackend(self.camera, self.spectrometer)
        self.sandg_backend.make_connection(self.sandg_widget)

        self.raman_backend = StaticRamanBackend(self.camera, self.spectrometer)
        self.raman_backend.make_connection(self.raman_widget)
        self.raman_backend.statusMessageSignal.connect(lambda msg: self.statusBar().showMessage(msg, 4000))

        self.confocal_backend = ConfocalBackend(self.camera, self.spectrometer)
        self.confocal_backend.make_connection(self.confocal_widget)

        self.lumin_widget = LuminescenceWidget(self)
        self.lumin_backend = LuminescenceBackend(self.camera, self.spectrometer)
        self.lumin_backend.make_connection(self.lumin_widget)

        self.growth_widget = GrowthKineticsWidget(self)
        self.growth_backend = GrowthKineticsBackend(self.camera, self.spectrometer)
        self.growth_backend.make_connection(self.growth_widget)

        self.dimers_widget = DimersWidget(self)
        self.dimers_backend = DimersBackend(self.camera, self.spectrometer)
        self.dimers_backend.make_connection(self.dimers_widget)

        self.nano_dialog = QtWidgets.QDialog(self)
        self.nano_dialog.setWindowTitle("Control de Platina PI Piezoeléctrica")
        nano_vlo = QtWidgets.QVBoxLayout(self.nano_dialog)
        self.nano_fe = NanoFrontend()
        self.nano_be = NanoBackend()
        self.nano_fe.make_connection(self.nano_be)
        nano_vlo.addWidget(self.nano_fe)

        self.shutters_dialog = QtWidgets.QDialog(self)
        self.shutters_dialog.setWindowTitle("Obturadores Láser & Flippers")
        sh_vlo = QtWidgets.QVBoxLayout(self.shutters_dialog)
        self.shutters_fe = ShuttersFrontend()
        self.shutters_be = ShuttersBackend()
        self.shutters_fe.make_connection(self.shutters_be)
        sh_vlo.addWidget(self.shutters_fe)

        self.hw_dashboard = None

    def _select_directory(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Seleccionar Carpeta de Trabajo", str(self.work_dir))
        if d:
            self.work_dir = Path(d)
            self.statusBar().showMessage(f"Carpeta activa: {self.work_dir}")

    def _create_daily_directory(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Seleccionar Directorio Base", str(self.work_dir))
        if d:
            today_str = time.strftime("%Y-%m-%d")
            daily = Path(d) / today_str
            daily.mkdir(parents=True, exist_ok=True)
            self.work_dir = daily
            self.statusBar().showMessage(f"Carpeta del día creada y activa: {self.work_dir}")

    def _open_directory(self):
        if self.work_dir.exists():
            os.startfile(str(self.work_dir))

    def _open_nano_dialog(self):
        self.nano_dialog.show()

    def _open_shutters_dialog(self):
        self.shutters_dialog.show()

    def _open_hardware_dashboard(self):
        if self.hw_dashboard is None:
            self.hw_dashboard = HardwareDashboardWindow()
        self.hw_dashboard.show()
        self.hw_dashboard.raise_()

    def _open_luminescence(self):
        self.lumin_widget.show()

    def _open_growth(self):
        self.growth_widget.show()

    def _open_dimers(self):
        self.dimers_widget.show()

    def closeEvent(self, event):
        reply = QtWidgets.QMessageBox.question(
            self, 'Cerrar PySpectrum 3.0',
            '¿Desea cerrar la sesión de PySpectrum y apagar cámaras y láseres?',
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
        )
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            self.cam_backend.toggle_live(False)
            self.raman_backend.toggle_live(False)
            self.confocal_backend.stop_scan()
            self.lumin_backend.stop_luminescence()
            self.growth_backend.stop_growth()
            event.accept()
        else:
            event.ignore()
