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
from pyspectrum.modules.hardware_session import hardware_session

from pyspectrum.modules.spectrum_control import Frontend as SpectrumFrontend, Backend as SpectrumBackend
from pyspectrum.modules.camera_andor import Frontend as CameraFrontend, Backend as CameraBackend
from pyspectrum.modules.step_and_glue import Frontend as StepGlueFrontend, Backend as StepGlueBackend
from pyspectrum.modules.hyperspectral_confocal import Frontend as ConfocalFrontend, Backend as ConfocalBackend
from pyspectrum.modules.static_raman import StaticRamanWidget, StaticRamanBackend
from pyspectrum.modules.calibration_dock import CalibrationFrontend, CalibrationBackend

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
        self._setup_toolbar()
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

        act_calib = QtGui.QAction("🎯 Calibraciones del Sistema (Slit, Grating, Offset)", self)
        act_calib.triggered.connect(lambda: self.dock_calibration.raise_())
        tools_menu.addAction(act_calib)

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

    def _setup_toolbar(self):
        """Barra de seguridad de hardware e instrumentación con botón E-STOP y estado de sesión."""
        toolbar = QtWidgets.QToolBar("Barra de Seguridad e Instrumentación", self)
        toolbar.setMovable(False)
        toolbar.setStyleSheet("""
            QToolBar {
                background-color: #181825;
                border-bottom: 1px solid #313244;
                padding: 4px;
                spacing: 10px;
            }
        """)
        self.addToolBar(QtCore.Qt.ToolBarArea.TopToolBarArea, toolbar)

        # 🚨 Botón E-STOP Global
        self.btn_estop = QtWidgets.QPushButton("🚨 PARADA DE EMERGENCIA (E-STOP)")
        self.btn_estop.setStyleSheet("""
            QPushButton {
                background-color: #F38BA8;
                color: #11111B;
                font-weight: bold;
                font-size: 10pt;
                padding: 6px 14px;
                border-radius: 4px;
                border: 1px solid #eba0ac;
            }
            QPushButton:hover {
                background-color: #eba0ac;
            }
        """)
        self.btn_estop.setToolTip("Cierra inmediatamente todos los láseres y aborta la adquisición del detector")
        self.btn_estop.clicked.connect(self._on_emergency_stop_clicked)
        toolbar.addWidget(self.btn_estop)

        # 🔄 Botón Rearmar
        self.btn_reset_estop = QtWidgets.QPushButton("🔄 Rearmar Sistema")
        self.btn_reset_estop.setStyleSheet("""
            QPushButton {
                background-color: #313244;
                color: #CDD6F4;
                font-weight: bold;
                padding: 6px 10px;
                border-radius: 4px;
                border: 1px solid #45475A;
            }
            QPushButton:hover {
                background-color: #45475A;
                color: #A6E3A1;
            }
            QPushButton:disabled {
                background-color: #181825;
                color: #585B70;
                border: 1px solid #313244;
            }
        """)
        self.btn_reset_estop.setEnabled(False)
        self.btn_reset_estop.setToolTip("Restaura el enclavamiento tras una parada de emergencia y rehabilita el hardware óptico.")
        self.btn_reset_estop.clicked.connect(self._on_reset_estop_clicked)
        toolbar.addWidget(self.btn_reset_estop)

        toolbar.addSeparator()

        # Badge de Estado de Sesión de Hardware
        self.lbl_hw_status = QtWidgets.QLabel("🟢 Sesión: Hardware Disponible")
        self.lbl_hw_status.setStyleSheet("""
            QLabel {
                color: #A6E3A1;
                font-weight: bold;
                font-size: 9.5pt;
                padding: 4px 10px;
                background-color: #1E1E2E;
                border: 1px solid #313244;
                border-radius: 4px;
            }
        """)
        self.lbl_hw_status.setToolTip("Monitorea la exclusividad mutua: indica qué rutina tiene tomado el control de los instrumentos.")
        toolbar.addWidget(self.lbl_hw_status)

        # Espaciador elástico
        spacer = QtWidgets.QWidget()
        spacer.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        # Acceso rápido a obturadores
        btn_quick_shutters = QtWidgets.QPushButton("⚡ Obturadores")
        btn_quick_shutters.setStyleSheet("""
            QPushButton {
                background-color: #313244;
                color: #CDD6F4;
                border: 1px solid #45475A;
                border-radius: 4px;
                padding: 5px 10px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45475A;
                color: #89B4FA;
            }
        """)
        btn_quick_shutters.setToolTip("Acceso directo a la ventana de control de obturadores láser y espejos abatibles (flippers).")
        btn_quick_shutters.clicked.connect(self._open_shutters_dialog)
        toolbar.addWidget(btn_quick_shutters)

        # Acceso rápido a tablero de hardware
        btn_quick_hw = QtWidgets.QPushButton("🔧 Tablero Hardware")
        btn_quick_hw.setStyleSheet("""
            QPushButton {
                background-color: #313244;
                color: #CDD6F4;
                border: 1px solid #45475A;
                border-radius: 4px;
                padding: 5px 10px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45475A;
                color: #FAB387;
            }
        """)
        btn_quick_hw.setToolTip("Abre el panel general de instrumentación y diagnóstico de conexiones físicas.")
        btn_quick_hw.clicked.connect(self._open_hardware_dashboard)
        toolbar.addWidget(btn_quick_hw)

    def _on_emergency_stop_clicked(self):
        hardware_session.emergency_stop()
        self.lbl_hw_status.setText("🚨 E-STOP ACTIVO (Láseres cerrados)")
        self.lbl_hw_status.setStyleSheet("""
            QLabel {
                color: #F38BA8;
                font-weight: bold;
                font-size: 9.5pt;
                padding: 4px 10px;
                background-color: #311B24;
                border: 1px solid #F38BA8;
                border-radius: 4px;
            }
        """)
        self.btn_reset_estop.setEnabled(True)
        QtWidgets.QMessageBox.critical(
            self,
            "🚨 PARADA DE EMERGENCIA",
            "Se ha ejecutado la PARADA DE EMERGENCIA GLOBAL:\n\n"
            "• Todos los obturadores láser han sido cerrados de inmediato.\n"
            "• Las adquisiciones de la cámara Andor CCD han sido abortadas.\n"
            "• Todas las rutinas activas han sido canceladas.\n\n"
            "Para continuar, verifique la seguridad física y presione 'Rearmar Sistema'."
        )

    def _on_reset_estop_clicked(self):
        hardware_session.clear_emergency()
        self.lbl_hw_status.setText("🟢 Sesión: Hardware Disponible")
        self.lbl_hw_status.setStyleSheet("""
            QLabel {
                color: #A6E3A1;
                font-weight: bold;
                font-size: 9.5pt;
                padding: 4px 10px;
                background-color: #1E1E2E;
                border: 1px solid #313244;
                border-radius: 4px;
            }
        """)
        self.btn_reset_estop.setEnabled(False)
        self.statusBar().showMessage("Sistema rearmado y listo para operar.", 4000)

    def _on_session_changed(self, owner: str, is_busy: bool):
        if hardware_session.is_emergency_stopped:
            return
        if is_busy and owner:
            self.lbl_hw_status.setText(f"🟠 En Ejecución: {owner}")
            self.lbl_hw_status.setStyleSheet("""
                QLabel {
                    color: #FAB387;
                    font-weight: bold;
                    font-size: 9.5pt;
                    padding: 4px 10px;
                    background-color: #2E251E;
                    border: 1px solid #FAB387;
                    border-radius: 4px;
                }
            """)
        else:
            self.lbl_hw_status.setText("🟢 Sesión: Hardware Disponible")
            self.lbl_hw_status.setStyleSheet("""
                QLabel {
                    color: #A6E3A1;
                    font-weight: bold;
                    font-size: 9.5pt;
                    padding: 4px 10px;
                    background-color: #1E1E2E;
                    border: 1px solid #313244;
                    border-radius: 4px;
                }
            """)

    def _setup_ui(self):
        self.dock_area = DockArea()
        self.setCentralWidget(self.dock_area)

        # ── Docks Modulares ───────────────────────────────────────────────────
        self.dock_camera = Dock("📷 Cámara Andor CCD (Detector)", size=(500, 500))
        self.cam_widget = CameraFrontend()
        self.cam_widget.setToolTip("Panel del detector Andor CCD: adquisición en vivo 2D/1D, control térmico Peltier y ganancia EM.")
        self.dock_camera.addWidget(self.cam_widget)
        self.dock_area.addDock(self.dock_camera, 'left')

        self.dock_spectrometer = Dock("🌈 Espectrógrafo Andor Shamrock", size=(500, 260))
        self.spec_widget = SpectrumFrontend()
        self.spec_widget.setToolTip("Control motorizado del espectrógrafo Shamrock 500i: redes de difracción, longitud de onda central y ranura.")
        self.dock_spectrometer.addWidget(self.spec_widget)
        self.dock_area.addDock(self.dock_spectrometer, 'bottom', self.dock_camera)

        self.dock_sandg = Dock("🧩 Espectroscopía & Step and Glue", size=(650, 400))
        self.sandg_widget = StepGlueFrontend()
        self.sandg_widget.setToolTip("Módulo de adquisición espectral y cosido continuo (Step & Glue) para barridos de banda ancha.")
        self.dock_sandg.addWidget(self.sandg_widget)
        self.dock_area.addDock(self.dock_sandg, 'right')

        self.dock_raman = Dock("🔬 Espectroscopía Raman Estática & Termometría", size=(650, 400))
        self.raman_widget = StaticRamanWidget()
        self.raman_widget.setToolTip("Módulo de Raman estático ultra-rápido, sustracción de línea base y termometría in-situ con cursores duales.")
        self.dock_raman.addWidget(self.raman_widget)
        self.dock_area.addDock(self.dock_raman, 'above', self.dock_sandg)

        self.dock_calibration = Dock("🎯 Calibraciones del Sistema", size=(650, 400))
        self.calib_widget = CalibrationFrontend()
        self.calib_widget.setToolTip("Subsistema metrológico de calibraciones: alineación de slit, offsets de rejilla, EEPROM y persistencia TXT.")
        self.dock_calibration.addWidget(self.calib_widget)
        self.dock_area.addDock(self.dock_calibration, 'above', self.dock_sandg)

        self.dock_confocal = Dock("🧬 Mapeo Confocal Hiperespectral (X, Y, λ)", size=(650, 360))
        self.confocal_widget = ConfocalFrontend()
        self.confocal_widget.setToolTip("Mapeo hiperespectral confocal: escaneo piezoeléctrico bidimensional sincronizado con espectrometría.")
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

        self.calib_backend = CalibrationBackend(self.camera, self.spectrometer)
        self.calib_backend.make_connection(self.calib_widget)
        self.calib_backend.statusSignal.connect(lambda msg: self.statusBar().showMessage(msg, 4000))

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

        # Registrar controladores Live en el HardwareSessionManager
        def pause_camera_live():
            if self.cam_widget.btn_live.isChecked():
                self.cam_widget.btn_live.setChecked(False)
                self.cam_widget.btn_live.setText("▶️ Iniciar Live View")
                self.cam_widget.btn_live.setStyleSheet("background-color: #313244; color: #CDD6F4; font-weight: bold;")
            self.cam_backend.toggle_live(False)

        def pause_raman_live():
            if self.raman_widget.btn_live.isChecked():
                self.raman_widget.btn_live.setChecked(False)
                self.raman_widget.btn_live.setText("▶️ Iniciar Live Raman")
                self.raman_widget.btn_live.setStyleSheet("background-color: #313244; color: #CDD6F4; font-weight: bold;")
            self.raman_backend.toggle_live(False)

        hardware_session.register_live_controller("Live CCD", pause_camera_live)
        hardware_session.register_live_controller("Live Raman", pause_raman_live)
        hardware_session.sessionChangedSignal.connect(self._on_session_changed)
        hardware_session.statusWarningSignal.connect(lambda msg: self.statusBar().showMessage(msg, 6000))

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
            hardware_session.emergency_stop()
            self.cam_backend.toggle_live(False)
            self.raman_backend.toggle_live(False)
            self.confocal_backend.stop_scan()
            self.lumin_backend.stop_luminescence()
            self.growth_backend.stop_growth()
            from core.nidaq import close_all_shutters
            close_all_shutters()
            event.accept()
        else:
            event.ignore()
