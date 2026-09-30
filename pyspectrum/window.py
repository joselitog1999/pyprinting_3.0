# -*- coding: utf-8 -*-
"""
window.py — Ventana Principal de PySpectrum 3.0
PyPrinting 3.0 — UNSAM Nanofotónica

Fase 1 del Rework Arquitectónico (DIRECTIVA DE INGENIERÍA — REWORK PYSPECTRUM 3.0): shell
unificado de pestañas de flujo de trabajo con un Panel Izquierdo Permanente y Dinámico
(LeftHardwarePanel) que centraliza el control de la cámara Andor EMCCD y el espectrógrafo
Shamrock 500i, reemplazando el DockArea flotante anterior.

Decisiones de alcance (Fase 1, ver docs/decisions/DECISION_LOG.md#DEC-015):
- Las 6 pestañas del shell son: Exploración, Static Raman, Step & Glue, Cinética de
  Crecimiento, Calibraciones y Mapeo Confocal. Las 4 primeras son las nombradas
  explícitamente en la directiva; Calibraciones y Mapeo Confocal se agregan como pestañas
  5/6 adicionales para no perder funcionalidad ya probada (antes vivían en el DockArea).
- Cinética de Crecimiento se embebe mediante GrowthKineticsPanel (extraído de
  GrowthKineticsWidget, que sigue existiendo standalone por retrocompatibilidad).
- El Frontend legado del espectrógrafo (spectrum_control.py) queda 100% superado en
  funcionalidad por el sub-panel Shamrock del LeftHardwarePanel (mismos controles, sin vista
  propia) — se mantiene instanciado y wireado, mas no visible por defecto, accesible como
  diálogo de compatibilidad desde el menú Herramientas.

Fase 2 (ver docs/decisions/DECISION_LOG.md#DEC-016): Pestaña 1 (Exploración) reemplaza
definitivamente camera_andor.py::Frontend por ExplorationTabWidget (visor 2D + ROI vertical
interactivo propagado a SpectroscopyContext, sin controles de hardware duplicados con
LeftHardwarePanel). camera_andor.py::Frontend/Backend permanecen intactos como módulo — sólo
se retiran las instancias `cam_widget`/`cam_backend` que este archivo creaba.

Fase 3 (ver docs/decisions/DECISION_LOG.md#DEC-017): Pestaña 2 (Static Raman) pasa de alojar
directamente static_raman.py::StaticRamanWidget a alojar
pyspectrum/ui/static_raman_container.py::StaticRamanTabContainer, que la divide en dos
sub-pestañas internas (Espectro 1D & Análisis / Resultado Medición — Inspector 2D). `self.
raman_widget` se conserva como alias de compatibilidad hacia el widget de la sub-pestaña A.

Fase 4 (ver docs/decisions/DECISION_LOG.md#DEC-018): Pestaña 3 (Step & Glue) — sin cambios de
wiring en este archivo, ya embebía step_and_glue.py::Frontend directamente (self.sandg_widget).
El cosido raised-cosine, el soporte 2D y la exportación HDF5 viven en
pyspectrum/calibration/halogen_lamp.py y pyspectrum/modules/step_and_glue.py.
"""
from __future__ import annotations
import os
import sys
import time
from pathlib import Path
import weakref
from typing import Optional

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6 import sip
from PyQt6.QtCore import pyqtSignal, pyqtSlot, QThread
import pyqtgraph as pg

from config import SAFE_MODE, PI_SERIAL
from core.nanopositioning import Frontend as NanoFrontend, Backend as NanoBackend
from core.shutters import Frontend as ShuttersFrontend, Backend as ShuttersBackend
from pyspectrum.drivers.shamrock_driver import get_shamrock
from pyspectrum.drivers.andor_ccd_driver import get_andor_ccd
from pyspectrum.modules.hardware_session import hardware_session
from pyspectrum.modules.spectroscopy_context import spectroscopy_context
from pyspectrum.ui.left_hardware_panel import LeftHardwarePanel
from pyspectrum.ui.exploration_tab import ExplorationTabWidget, ExplorationWorker

from pyspectrum.modules.spectrum_control import Frontend as SpectrumFrontend, Backend as SpectrumBackend
from pyspectrum.modules.step_and_glue import Frontend as StepGlueFrontend, Backend as StepGlueBackend
from pyspectrum.modules.hyperspectral_confocal import Frontend as ConfocalFrontend, Backend as ConfocalBackend
from pyspectrum.modules.static_raman import StaticRamanBackend
from pyspectrum.ui.static_raman_container import StaticRamanTabContainer
from pyspectrum.modules.calibration_dock import CalibrationFrontend, CalibrationBackend

from pyspectrum.modules.routines.luminescence import LuminescencePanel, LuminescenceBackend
from pyspectrum.modules.routines.growth_kinetics import GrowthKineticsPanel, GrowthKineticsBackend
from pyspectrum.modules.routines.dimers import DimersWidget, DimersBackend
from pyspectrum.modules.routines.linescan_spectroscopy import create_linescan_routine
from modules.hardware_dashboard import HardwareDashboardWindow

# Índices fijos de las pestañas del shell principal (usados por LeftHardwarePanel.set_context()
# y por los tests para no depender de literales dispersos).
TAB_EXPLORATION = 0
TAB_STATIC_RAMAN = 1
TAB_STEP_AND_GLUE = 2
TAB_GROWTH_KINETICS = 3
TAB_CALIBRATION = 4
TAB_CONFOCAL = 5
TAB_LUMINESCENCE = 6


class _EmergencyKeyFilter(QtCore.QObject):
    """Dispara la E-STOP con F12 o Ctrl+E aunque un diálogo modal tape la ventana (H-01 / C-30).

    Hay UN solo filtro por proceso, instalado sobre la aplicación. Cada `PySpectrumWindow` se
    registra con `register()` (referencia débil), así que un filtro por ventana no se acumula ni
    encarece cada evento de Qt.
    - Actúa sobre las teclas que llegan a una ventana registrada o a un diálogo modal que dependa
      de ella, y no sobre otras ventanas del proceso (p. ej. el satélite PyPrinting).
    - Consume el `ShortcutOverride`, así que el `QShortcut` de la ventana no se dispara también, y
      consume el `KeyPress` que lo sigue: una pulsación, una E-STOP.
    """

    _instance: "Optional[_EmergencyKeyFilter]" = None
    _TYPES = (QtCore.QEvent.Type.ShortcutOverride, QtCore.QEvent.Type.KeyPress)

    def __init__(self):
        super().__init__(QtWidgets.QApplication.instance())
        self._windows: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()
        self._armed_by_override = False

    @classmethod
    def register(cls, window: QtWidgets.QWidget, trigger) -> "_EmergencyKeyFilter":
        if cls._instance is None:
            cls._instance = cls()
            QtWidgets.QApplication.instance().installEventFilter(cls._instance)
        # WeakMethod: guardar el método ligado mantendría viva la ventana (el valor la referencia).
        cls._instance._windows[window] = weakref.WeakMethod(trigger)
        return cls._instance

    @staticmethod
    def _is_estop_key(event) -> bool:
        key = event.key()
        mods = event.modifiers() & ~QtCore.Qt.KeyboardModifier.KeypadModifier
        return ((key == QtCore.Qt.Key.Key_F12 and mods == QtCore.Qt.KeyboardModifier.NoModifier)
                or (key == QtCore.Qt.Key.Key_E and mods == QtCore.Qt.KeyboardModifier.ControlModifier))

    def _owner_trigger(self, obj):
        """La acción de E-STOP de la ventana registrada a la que pertenece `obj`, o None."""
        if not isinstance(obj, QtWidgets.QWidget):
            return None
        top = obj.window()
        candidates = [top]
        if isinstance(top, QtWidgets.QDialog) and top.isModal():
            parent = top.parentWidget()
            while parent is not None:
                candidates.append(parent.window())
                parent = parent.window().parentWidget()
        for candidate in candidates:
            try:
                ref = self._windows.get(candidate)
            except TypeError:
                ref = None
            trigger = ref() if ref is not None else None
            if trigger is not None and not sip.isdeleted(candidate):
                return trigger
        return None

    def eventFilter(self, obj, event):
        if event.type() not in self._TYPES or not self._is_estop_key(event) or event.isAutoRepeat():
            return False
        trigger = self._owner_trigger(obj)
        if trigger is None:
            return False
        if event.type() == QtCore.QEvent.Type.ShortcutOverride:
            self._armed_by_override = True
            event.accept()
            trigger()
            return True
        if self._armed_by_override:  # el KeyPress de la misma pulsación
            self._armed_by_override = False
            return True
        trigger()
        return True


class PySpectrumWindow(QtWidgets.QMainWindow):
    """Ventana Principal de PySpectrum 3.0."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("PySpectrum 3.0 — Espectroscopía & Mapeo Hiperespectral (UNSAM Nanofotónica)")
        self.resize(1440, 880)
        self.setMinimumSize(1100, 700)

        self.work_dir = Path.home() / "Documents" / "Data_PySpectrum"
        self.work_dir.mkdir(parents=True, exist_ok=True)

        self._setup_styles()
        self._setup_menu()
        self._setup_toolbar()
        self._setup_ui()
        self._setup_threads_and_backends()

    def _setup_styles(self):
        pg.setConfigOption('background', '#11111B')
        pg.setConfigOption('foreground', '#CDD6F4')
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
            QTabWidget::pane {
                border: 1px solid #313244;
                background-color: #11111B;
            }
            QTabBar::tab {
                background-color: #181825;
                color: #A6ADC8;
                padding: 8px 14px;
                border: 1px solid #313244;
                border-bottom: none;
                font-weight: bold;
            }
            QTabBar::tab:selected {
                background-color: #313244;
                color: #89B4FA;
            }
            QTabBar::tab:hover {
                color: #CDD6F4;
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

        tools_menu.addSeparator()
        act_spec_legacy = QtGui.QAction("Control Legado del Espectrógrafo (compatibilidad)", self)
        act_spec_legacy.setToolTip("Panel de control del Shamrock previo a la Fase 1. Sus mismos controles ya están disponibles en el Panel Izquierdo permanente.")
        act_spec_legacy.triggered.connect(self._open_spectrometer_legacy_dialog)
        tools_menu.addAction(act_spec_legacy)

        tools_menu.addSeparator()
        act_contrapropagante = QtGui.QAction("Microscopio Contrapropagante (Ventana Satélite Subyugada)", self)
        act_contrapropagante.setShortcut(QtGui.QKeySequence("Ctrl+M"))
        act_contrapropagante.setToolTip(
            "Abre el microscopio Contrapropagante como ventana satélite. Se subyuga automáticamente "
            "a Modo Solo Monitoreo mientras PySpectrum tenga el control exclusivo del hardware (Fase 5)."
        )
        act_contrapropagante.triggered.connect(self._open_contrapropagante)
        tools_menu.addAction(act_contrapropagante)

        act_microscopio_derecho = QtGui.QAction("Microscopio Derecho / PyPrinting (Ventana Satélite Subyugada)", self)
        act_microscopio_derecho.setToolTip(
            "Abre el Microscopio Derecho (app.py) como ventana satélite subyugada compartiendo el proceso de PySpectrum "
            "y evitando colisiones de bus USB con la platina piezoeléctrica PI."
        )
        act_microscopio_derecho.triggered.connect(self._open_microscopio_derecho)
        tools_menu.addAction(act_microscopio_derecho)

        # ── Menú Rutinas Especializadas ───────────────────────────────────────
        routines_menu = menubar.addMenu("🧪 Rutinas")

        act_dimers = QtGui.QAction("Caracterización de Dímeros Plasmónicos", self)
        act_dimers.triggered.connect(self._open_dimers)
        routines_menu.addAction(act_dimers)

        act_linescan = QtGui.QAction("Escaneo Lineal Espectral (Transmisión/Extinción)", self)
        act_linescan.triggered.connect(self._open_linescan)
        routines_menu.addAction(act_linescan)

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

        # Indicador de acoplamiento con la platina PI y la ventana satélite (Fase 5, DEC-019)
        self.lbl_stage_status = QtWidgets.QLabel("🔗 Platina PI: Conectada [Libre]")
        self.lbl_stage_status.setStyleSheet("""
            QLabel {
                color: #89B4FA;
                font-weight: bold;
                font-size: 9.5pt;
                padding: 4px 10px;
                background-color: #1E1E2E;
                border: 1px solid #313244;
                border-radius: 4px;
            }
        """)
        self.lbl_stage_status.setToolTip("Estado de acoplamiento de la platina PI E-517 y de la ventana satélite Contrapropagante (Libre = control manual disponible / Subyugada = PySpectrum tiene el control exclusivo).")
        toolbar.addWidget(self.lbl_stage_status)

        # Insignia de orden cero (paso 7, Ronda 3 §1.2 con H-33/H-34): visible en condición especular,
        # incluido el estado desconocido, que cuenta como especular. Clic → foco al espejo rápido.
        self.lbl_specular_badge = QtWidgets.QPushButton("ORDEN CERO · EM 0 bloqueada")
        self.lbl_specular_badge.setFlat(True)
        self.lbl_specular_badge.setStyleSheet(
            "QPushButton { color: #181825; background-color: #fab387; font-weight: bold; font-size: 9.5pt;"
            " padding: 4px 10px; border-radius: 4px; }")
        self.lbl_specular_badge.setToolTip("Condición especular: la red refleja la luz sin dispersarla. "
                                           "La ganancia EM queda bloqueada en 0.")
        self.lbl_specular_badge.clicked.connect(lambda: self.left_panel.btn_zero_order.setFocus())
        self.lbl_specular_badge.hide()
        self._specular_badge_action = toolbar.addWidget(self.lbl_specular_badge)
        self._specular_badge_action.setVisible(False)

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

    def _on_subjugation_status_changed(self, subjugated: bool):
        """Actualiza el indicador de acoplamiento de la platina PI / ventana satélite
        Contrapropagante (Fase 5, DEC-019)."""
        if subjugated:
            self.lbl_stage_status.setText("🔒 Platina PI: Conectada [Subyugada]")
            self.lbl_stage_status.setStyleSheet("""
                QLabel {
                    color: #11111B;
                    font-weight: bold;
                    font-size: 9.5pt;
                    padding: 4px 10px;
                    background-color: #FAB387;
                    border: 1px solid #FAB387;
                    border-radius: 4px;
                }
            """)
        else:
            self.lbl_stage_status.setText("🔗 Platina PI: Conectada [Libre]")
            self.lbl_stage_status.setStyleSheet("""
                QLabel {
                    color: #89B4FA;
                    font-weight: bold;
                    font-size: 9.5pt;
                    padding: 4px 10px;
                    background-color: #1E1E2E;
                    border: 1px solid #313244;
                    border-radius: 4px;
                }
            """)

    def _setup_ui(self):
        """Shell principal: Panel Izquierdo Permanente (Andor + Shamrock, ~1/3) y pestañas de
        flujo de trabajo a la derecha (~2/3), reemplazando el DockArea flotante anterior."""
        self.camera = get_andor_ccd()
        self.spectrometer = get_shamrock()
        # Estado operativo base de la cámara (paso 8, DEC-040): enfriador a −60 °C, ventilador en bajo,
        # velocidades por valor, ganancia EM 0 confirmada. No toca el espectrógrafo ni la calibración.
        from pyspectrum.modules.camera_baseline import apply_camera_baseline
        self.camera_baseline_report = apply_camera_baseline(self.camera)
        print(f"[PySpectrum] Estado base de la cámara: {self.camera_baseline_report.summary()}")

        self.main_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        self.setCentralWidget(self.main_splitter)

        self.left_panel = LeftHardwarePanel(self.camera, self.spectrometer, step_glue_tab_index=TAB_STEP_AND_GLUE)
        self.left_panel.setMinimumWidth(320)
        self.left_panel.apply_camera_baseline_report(self.camera_baseline_report)
        self.left_panel.specularStateChanged.connect(self._on_specular_state_changed)
        self._on_specular_state_changed(self.left_panel._last_mode or "unknown")
        self.main_splitter.addWidget(self.left_panel)

        self.tabs_workflow = QtWidgets.QTabWidget()
        self.main_splitter.addWidget(self.tabs_workflow)

        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 2)
        self.main_splitter.setSizes([440, 900])

        # ── Pestaña 1: Exploración (Live View 2D + ROI vertical interactivo) ──
        self.exploration_widget = ExplorationTabWidget()
        self.exploration_widget.setToolTip("Vista en vivo del detector Andor CCD con ROI vertical interactivo ligado a SpectroscopyContext.")
        self.tabs_workflow.addTab(self.exploration_widget, "🔭 1. Exploración")

        # ── Pestaña 2: Static Raman ────────────────────────────────────────────
        self.raman_container = StaticRamanTabContainer()
        # Alias de compatibilidad: apunta al widget de Sub-pestaña A (Espectro 1D & Análisis),
        # que es donde vivían btn_live y demás controles antes del contenedor de la Fase 3.
        self.raman_widget = self.raman_container.spectrum_widget
        self.tabs_workflow.addTab(self.raman_container, "🔬 2. Static Raman")

        # ── Pestaña 3: Step & Glue ─────────────────────────────────────────────
        self.sandg_widget = StepGlueFrontend()
        self.tabs_workflow.addTab(self.sandg_widget, "🧩 3. Step & Glue")

        # ── Pestaña 4: Cinética de Crecimiento (embebida vía GrowthKineticsPanel) ──
        self.growth_widget = GrowthKineticsPanel()
        self.tabs_workflow.addTab(self.growth_widget, "🌱 4. Cinética")

        # ── Pestaña 5: Calibraciones del Sistema ──────────────────────────────
        self.calib_widget = CalibrationFrontend()
        # Paso 14: la calibración automática de λ va primero; la pestaña de siempre queda al lado.
        from pyspectrum.ui.auto_calibration_panel import AutoCalibrationController, AutoCalibrationPanel
        self.auto_cal_controller = AutoCalibrationController(self.camera, self.spectrometer, parent=self)
        self.auto_cal_panel = AutoCalibrationPanel(self.auto_cal_controller)
        self.calib_tabs = QtWidgets.QTabWidget()
        self.calib_tabs.addTab(self.auto_cal_panel, "Calibración de λ (automática)")
        self.calib_tabs.addTab(self.calib_widget, "Offsets, historial, ranura y lámpara")
        self.tabs_workflow.addTab(self.calib_tabs, "🎯 5. Calibraciones")

        # ── Pestaña 6: Mapeo Confocal Hiperespectral ──────────────────────────
        self.confocal_widget = ConfocalFrontend()
        self.tabs_workflow.addTab(self.confocal_widget, "🧬 6. Mapeo Confocal")

        # ── Pestaña 7: Luminiscencia & Anti-Stokes (embebida vía LuminescencePanel, Fase 7) ──
        # Agregada al final (no insertada en la posición 6 que sugeriría su nombre "Pestaña 6"
        # en la directiva original) para no reordenar/renumerar las 6 pestañas ya existentes:
        # TAB_CALIBRATION/TAB_CONFOCAL y los tests que dependen de esos índices quedan intactos.
        self.lumin_widget = LuminescencePanel()
        self.tabs_workflow.addTab(self.lumin_widget, "✨ 7. Luminiscencia")

        self.tabs_workflow.currentChanged.connect(self._on_main_tab_changed)
        self._setup_shortcuts()

        self.statusBar().showMessage(f"PySpectrum 3.0 Listo. Carpeta de trabajo: {self.work_dir}")
        self._observe_calibration_at_startup()
        if self.camera_baseline_report.blocks_acquisition:
            self.statusBar().showMessage(
                "⚠️ Cámara: el estado base no se confirmó (" + self.camera_baseline_report.summary()
                + "). Las adquisiciones deben quedar bloqueadas hasta resolverlo.")

    def _observe_calibration_at_startup(self):
        """Paso 9 (DEC-040): lee los offsets del Shamrock sólo con Get*, registra OBSERVED en el archivo de
        calibraciones y compara. Nunca escribe al equipo (R4-B-1). Si algo difiere, un aviso persistente y
        no modal (Ronda 3 §1.11); el arranque sigue."""
        self.lbl_calibration_warning = QtWidgets.QPushButton("")
        self.lbl_calibration_warning.setFlat(True)
        self.lbl_calibration_warning.clicked.connect(lambda: self.tabs_workflow.setCurrentIndex(TAB_CALIBRATION))
        self.lbl_calibration_warning.hide()
        self.statusBar().addPermanentWidget(self.lbl_calibration_warning)
        self.calibration_startup_report = None
        if not getattr(self.spectrometer, "available", True):
            return
        try:
            from pyspectrum.calibration.repository import get_repository, observe_spectrograph
            report = observe_spectrograph(self.spectrometer, get_repository())
        except Exception as e:
            print(f"[PySpectrum] No se pudo comparar los offsets con el archivo de calibraciones: {e}")
            return
        self.calibration_startup_report = report
        warnings = report.warnings()
        for w in warnings:
            print(f"[PySpectrum] Calibración: {w}")
        if warnings:
            more = f"  (+{len(warnings) - 1} avisos)" if len(warnings) > 1 else ""
            self.lbl_calibration_warning.setText(f"⚠️ {warnings[0]}{more}")
            self.lbl_calibration_warning.setToolTip("\n".join(warnings) + "\n\nNada se escribió al equipo. "
                                                    "Clic: ir a Calibraciones.")
            self.lbl_calibration_warning.setStyleSheet("QPushButton { color: #F9E2AF; font-weight: bold; }")
            self.lbl_calibration_warning.show()
        elif report.first_use:
            self.lbl_calibration_warning.setText("ℹ️ No había archivo de calibraciones: se creó uno con lo leído "
                                                 "del equipo (OBSERVED).")
            self.lbl_calibration_warning.setToolTip(str(getattr(get_repository(), "path", "")))
            self.lbl_calibration_warning.setStyleSheet("QPushButton { color: #89B4FA; }")
            self.lbl_calibration_warning.show()

    def _on_main_tab_changed(self, idx: int):
        self.left_panel.set_context(idx)

    def _setup_shortcuts(self):
        """Atajos de teclado globales del shell (Fase 7, DEC-021). Ctrl+M ya existe como
        QAction del menú Herramientas (Fase 5) — no se duplica aquí."""
        self.shortcut_live_view = QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Space"), self)
        self.shortcut_live_view.activated.connect(self._shortcut_toggle_live_view)

        self.shortcut_measure = QtGui.QShortcut(QtGui.QKeySequence("Ctrl+R"), self)
        self.shortcut_measure.activated.connect(self._shortcut_trigger_measurement)

        self.shortcut_zero_order = QtGui.QShortcut(QtGui.QKeySequence("Ctrl+0"), self)
        self.shortcut_zero_order.setAutoRepeat(False)   # sostenida no entra y vuelve (H-11a)
        self.shortcut_zero_order.activated.connect(self._shortcut_goto_zero_order)

        self.shortcut_estop_ctrl = QtGui.QShortcut(QtGui.QKeySequence("Ctrl+E"), self)
        self.shortcut_estop_ctrl.activated.connect(self._on_emergency_stop_clicked)
        self.shortcut_estop_f12 = QtGui.QShortcut(QtGui.QKeySequence("F12"), self)
        self.shortcut_estop_f12.activated.connect(self._on_emergency_stop_clicked)
        # Con un diálogo modal abierto, Qt bloquea los atajos de esta ventana en cualquier
        # contexto, y la E-STOP por teclado quedaba muerta justo cuando el operador confirma algo
        # sobre el equipo (H-01 / C-30). El filtro de aplicación la dispara igual.
        self._estop_key_filter = _EmergencyKeyFilter.register(self, self._on_emergency_stop_clicked)

        self.shortcuts_tabs = []
        for i in range(self.tabs_workflow.count()):
            sc = QtGui.QShortcut(QtGui.QKeySequence(f"Ctrl+{i + 1}"), self)
            sc.activated.connect(lambda idx=i: self.tabs_workflow.setCurrentIndex(idx))
            self.shortcuts_tabs.append(sc)

    def _shortcut_toggle_live_view(self):
        """Ctrl+Space: alterna Live View en la pestaña activa (Exploración o Static Raman;
        no-op en las demás pestañas, que no tienen un concepto de vista continua)."""
        idx = self.tabs_workflow.currentIndex()
        if idx == TAB_EXPLORATION:
            self.exploration_widget.btn_live.click()
        elif idx == TAB_STATIC_RAMAN:
            self.raman_container.spectrum_widget.btn_live.click()

    def _shortcut_trigger_measurement(self):
        """Ctrl+R: dispara la acción de medición/adquisición primaria de la pestaña activa."""
        idx = self.tabs_workflow.currentIndex()
        if idx == TAB_STATIC_RAMAN:
            self.raman_container.spectrum_widget.btn_single.click()
        elif idx == TAB_STEP_AND_GLUE:
            self.sandg_widget.btn_single.click()
        elif idx == TAB_GROWTH_KINETICS:
            self.growth_widget.btn_run.click()
        elif idx == TAB_CONFOCAL:
            self.confocal_widget.btn_scan.click()
        elif idx == TAB_LUMINESCENCE:
            self.lumin_widget.btn_run.click()

    def _shortcut_goto_zero_order(self):
        """Ctrl+0: el espejo rápido del panel izquierdo (el mismo botón, sin diálogo). Entra al orden cero
        con la red actual desde primer orden y vuelve desde especular (H-11e)."""
        self.left_panel.btn_zero_order.click()

    def _on_specular_state_changed(self, mode: str):
        if mode == "first_order":
            self._specular_badge_action.setVisible(False)
            return
        self.lbl_specular_badge.setText("ORDEN CERO · EM 0 bloqueada" if mode == "specular"
                                        else "ORDEN CERO (estado del Shamrock desconocido) · EM 0 bloqueada")
        self.lbl_specular_badge.show()
        self._specular_badge_action.setVisible(True)

    def _setup_threads_and_backends(self):
        from core.hardware_manager import hardware_manager
        from config import pi
        hardware_manager.set_profile("pyspectrum", rescan=False)
        pi.connect()

        # self.camera / self.spectrometer ya se crearon en _setup_ui() (LeftHardwarePanel los necesita
        # antes de existir los backends legados que también los consumen).

        self.spec_widget = SpectrumFrontend()
        self.spec_backend = SpectrumBackend(self.spectrometer)
        self.spec_backend.make_connection(self.spec_widget)

        # Exploración (Pestaña 1): tercera excepción arquitectónica con Worker en QThread real
        # (junto a Escaneo Lineal Espectral — DEC-006 — y Mapeo Confocal — ANOM-HYPERSPEC-01),
        # para sostener Live View a 20-30 fps sin bloquear el hilo GUI ni el botón E-STOP.
        self.exploration_worker = ExplorationWorker(self.camera)
        self.exploration_thread = QThread(self)
        self.exploration_worker.moveToThread(self.exploration_thread)
        self.exploration_thread.start()
        self.exploration_widget.liveToggledSignal.connect(self.exploration_worker.set_live)
        self.exploration_worker.imageUpdatedSignal.connect(self.exploration_widget.update_image)
        self.exploration_worker.liveErrorSignal.connect(self.exploration_widget.on_live_error)

        self.sandg_backend = StepGlueBackend(self.camera, self.spectrometer)
        self.sandg_backend.make_connection(self.sandg_widget)
        self.sandg_backend.data_dir = self.work_dir / "step_and_glue"

        self.raman_backend = StaticRamanBackend(self.camera, self.spectrometer)
        self.raman_backend.make_connection(self.raman_widget, self.raman_container.inspector_widget)
        self.raman_backend.statusMessageSignal.connect(lambda msg: self.statusBar().showMessage(msg, 4000))

        # ANOM-HYPERSPEC-01: excepción arquitectónica con Worker en QThread real — cada punto
        # del mapeo bloquea con un pi.MOV() + una exposición/lectura CCD completa; en el hilo
        # GUI eso congelaba toda la ventana (incluido el Stop/E-STOP) por la duración de cada
        # exposición, cientos o miles de veces por mapa. moveToThread() también arrastra a
        # self.scan_timer, que se parenta a self dentro de ConfocalBackend.__init__.
        self.confocal_backend = ConfocalBackend(self.camera, self.spectrometer)
        self.confocal_thread = QThread(self)
        self.confocal_backend.moveToThread(self.confocal_thread)
        self.confocal_thread.start()
        self.confocal_backend.make_connection(self.confocal_widget)

        self.calib_backend = CalibrationBackend(self.camera, self.spectrometer)
        self.calib_backend.make_connection(self.calib_widget)
        self.calib_backend.statusSignal.connect(lambda msg: self.statusBar().showMessage(msg, 4000))

        self.lumin_backend = LuminescenceBackend(self.camera, self.spectrometer)
        self.lumin_backend.make_connection(self.lumin_widget)

        self.growth_backend = GrowthKineticsBackend(self.camera, self.spectrometer)
        self.growth_backend.make_connection(self.growth_widget)

        self.dimers_widget = DimersWidget(self)
        self.dimers_backend = DimersBackend(self.camera, self.spectrometer)
        self.dimers_backend.make_connection(self.dimers_widget)

        # Escaneo Lineal Espectral: única rutina con Worker en QThread real (DEC-006),
        # a diferencia de las demás (Backend(QObject) + QTimer en el hilo GUI).
        self.linescan_widget, self.linescan_worker, self.linescan_thread = create_linescan_routine(
            self.camera, self.spectrometer, parent=self
        )
        self.linescan_worker.data_dir = self.work_dir / "linescan"

        self.nano_dialog = QtWidgets.QDialog(self)
        self.nano_dialog.setWindowTitle("Control de Platina PI Piezoeléctrica")
        nano_vlo = QtWidgets.QVBoxLayout(self.nano_dialog)
        self.nano_fe = NanoFrontend()
        self.nano_be = NanoBackend()
        self.nano_fe.make_connection(self.nano_be)
        self.installEventFilter(self.nano_fe)
        self.nano_dialog.installEventFilter(self.nano_fe)
        nano_vlo.addWidget(self.nano_fe)

        self.shutters_dialog = QtWidgets.QDialog(self)
        self.shutters_dialog.setWindowTitle("Obturadores Láser & Flippers")
        sh_vlo = QtWidgets.QVBoxLayout(self.shutters_dialog)
        self.shutters_fe = ShuttersFrontend()
        self.shutters_be = ShuttersBackend()
        self.shutters_fe.make_connection(self.shutters_be)
        sh_vlo.addWidget(self.shutters_fe)

        self.spectrometer_legacy_dialog = QtWidgets.QDialog(self)
        self.spectrometer_legacy_dialog.setWindowTitle("Control Legado del Espectrógrafo (compatibilidad)")
        spec_vlo = QtWidgets.QVBoxLayout(self.spectrometer_legacy_dialog)
        spec_vlo.addWidget(self.spec_widget)

        self.hw_dashboard = None

        # Registrar controladores Live en el HardwareSessionManager
        def pause_camera_live():
            if self.exploration_widget.btn_live.isChecked():
                self.exploration_widget.btn_live.setChecked(False)
                self.exploration_widget.btn_live.setText("▶️ Iniciar Live View")
                self.exploration_widget.btn_live.setStyleSheet("background-color: #313244; color: #CDD6F4; font-weight: bold;")
            self.exploration_widget.liveToggledSignal.emit(False)

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

        # Subyugación Master-Slave (Fase 5, DEC-019): cualquier rutina de PySpectrum que
        # adquiera la sesión exclusiva de hardware (Step & Glue, Mapeo Confocal, Cinética,
        # etc.) subyuga automáticamente la ventana satélite Contrapropagante/PyPrinting a
        # Modo Solo Monitoreo; al liberarla, la restaura a modo autónomo. Wireado UNA sola
        # vez aquí (no en cada rutina individualmente) porque todas ya pasan por el mismo
        # hardware_session.acquire_session()/release_session() singleton.
        hardware_session.sessionChangedSignal.connect(lambda owner, busy: spectroscopy_context.set_subjugated(busy))
        spectroscopy_context.subjugatedModeChanged.connect(self._on_subjugation_status_changed)
        self.contrapropagante_satellite = None
        self._contrapropagante_backend = None
        self._contrapropagante_threads = []
        self.microscopio_derecho_satellite = None
        self._microscopio_derecho_backend = None
        self._microscopio_derecho_threads = []

    def _select_directory(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Seleccionar Carpeta de Trabajo", str(self.work_dir))
        if d:
            self.work_dir = Path(d)
            self._propagate_work_dir()
            self.statusBar().showMessage(f"Carpeta activa: {self.work_dir}")

    def _create_daily_directory(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Seleccionar Directorio Base", str(self.work_dir))
        if d:
            today_str = time.strftime("%Y-%m-%d")
            daily = Path(d) / today_str
            daily.mkdir(parents=True, exist_ok=True)
            self.work_dir = daily
            self._propagate_work_dir()
            self.statusBar().showMessage(f"Carpeta del día creada y activa: {self.work_dir}")

    def _propagate_work_dir(self):
        """Las rutinas que guardan por su cuenta (Step & Glue, paso 11) escriben en la carpeta de trabajo."""
        if hasattr(self, "sandg_backend"):
            self.sandg_backend.data_dir = self.work_dir / "step_and_glue"
        if hasattr(self, "linescan_worker"):
            self.linescan_worker.data_dir = self.work_dir / "linescan"
        if hasattr(self, "auto_cal_controller"):
            self.auto_cal_controller.data_dir = self.work_dir / "calibration"
        if hasattr(self, "confocal_backend"):
            self.confocal_backend.data_dir = self.work_dir / "confocal_map"
        if hasattr(self, "lumin_backend"):
            self.lumin_backend.data_dir = str(self.work_dir / "luminescence")
        if hasattr(self, "growth_backend"):
            self.growth_backend.data_dir = str(self.work_dir / "growth")
        if hasattr(self, "dimers_backend"):
            self.dimers_backend.data_dir = str(self.work_dir / "dimers")

    def _open_directory(self):
        if self.work_dir.exists():
            os.startfile(str(self.work_dir))

    def _open_nano_dialog(self):
        self.nano_dialog.show()

    def _open_shutters_dialog(self):
        self.shutters_dialog.show()

    def _open_spectrometer_legacy_dialog(self):
        self.spectrometer_legacy_dialog.show()

    def _open_hardware_dashboard(self):
        if self.hw_dashboard is None:
            self.hw_dashboard = HardwareDashboardWindow()
        self.hw_dashboard.show()
        self.hw_dashboard.raise_()

    def _open_dimers(self):
        self.dimers_widget.show()

    def _open_linescan(self):
        self.linescan_widget.show()

    def _open_contrapropagante(self):
        """Abre (o trae al frente) el microscopio Contrapropagante como ventana satélite
        Master-Slave (Fase 5, DEC-019): mismo QApplication/contexto global, subyugada
        automáticamente mientras PySpectrum tenga el control exclusivo del hardware."""
        if self.contrapropagante_satellite is None:
            import contrapropagante
            from core.host_context import HostContext
            # Huésped (paso 13; decisión del investigador del 2026-09-29): no conecta la platina.
            win, backend, threads = contrapropagante.create_contrapropagante_satellite(
                parent=self, host=HostContext("PySpectrum 3.0"))
            self.contrapropagante_satellite = win
            self._contrapropagante_backend = backend
            self._contrapropagante_threads = threads
            win.closeSignal.connect(self._forget_contrapropagante)
        self.contrapropagante_satellite.show()
        self.contrapropagante_satellite.raise_()
        self.contrapropagante_satellite.activateWindow()

    def _open_microscopio_derecho(self):
        """Abre (o trae al frente) el Microscopio Derecho (PyPrinting / app.py) como ventana satélite
        subyugada, compartiendo la misma sesión y evitando conflictos con la platina PI (DEC-019)."""
        if self.microscopio_derecho_satellite is None:
            import app
            # Huésped (paso 13): no conecta la platina ni cambia el perfil; su cierre no la desconecta.
            win, backend, threads = app.create_app_satellite(parent=self, host=app.HostContext("PySpectrum 3.0"))
            self.microscopio_derecho_satellite = win
            self._microscopio_derecho_backend = backend
            self._microscopio_derecho_threads = threads
            win.closeSignal.connect(self._forget_microscopio_derecho)
        self.microscopio_derecho_satellite.show()
        self.microscopio_derecho_satellite.raise_()
        self.microscopio_derecho_satellite.activateWindow()

    def _forget_microscopio_derecho(self):
        """El operador cerró el satélite (ya se liberó y terminó sus hilos): reabrirlo crea uno nuevo."""
        self.microscopio_derecho_satellite = None
        self._microscopio_derecho_backend = None
        self._microscopio_derecho_threads = []

    def _forget_contrapropagante(self):
        self.contrapropagante_satellite = None
        self._contrapropagante_backend = None
        self._contrapropagante_threads = []

    def _open_guests(self):
        from pyspectrum.services.shutdown import GuestHandle
        guests = []
        if self.microscopio_derecho_satellite is not None:
            be = self._microscopio_derecho_backend
            guests.append(GuestHandle("PyPrinting", release=be.release_as_guest,
                                      threads=list(self._microscopio_derecho_threads),
                                      close_from_host=self.microscopio_derecho_satellite.close_from_host))
        if self.contrapropagante_satellite is not None:
            guests.append(GuestHandle("El contrapropagante", release=lambda: None,
                                      threads=list(self._contrapropagante_threads),
                                      close_from_host=self.contrapropagante_satellite.close_from_host))
        return guests

    def _build_shutdown(self, guests):
        """Orden de cierre (paso 13, DEC-040; R2-arq §3.3). window.py sólo arma la lista."""
        from config import pi, PI_HOME_POS
        from core.nidaq import close_all_shutters, flipper_notch532
        from pyspectrum.services import shutdown as sd
        from pyspectrum.services.spectrometer_shutter import close_spectrometer_shutter

        def both(*fns):
            for fn in fns:
                fn()

        def spectrometer_shutter():
            r = close_spectrometer_shutter(self.camera, self.spectrometer)
            return sd.ShutdownStep("obturador del espectrómetro", bool(r.ok), r.detail)

        def shamrock():
            self.spectrometer.close()        # ShamrockClose en el driver real

        def camera():
            try:
                self.camera.abort_acquisition()
            finally:
                self.camera.close()          # como el legado (pylablib close): el enfriador deja de enfriar

        routines = [
            ("Live de exploración", lambda: sd.stop_in_thread(self.exploration_worker, "stop_live",
                                                              self.exploration_thread, "Live de exploración")),
            ("hilo de exploración", lambda: sd.quit_thread(self.exploration_thread, "de exploración")),
            ("Live Raman", lambda: self.raman_backend.toggle_live(False)),
            # ConfocalBackend vive en confocal_thread (ANOM-HYPERSPEC-01): stop_scan corre en su hilo.
            # request_stop corta una exposición en curso desde este hilo; stop_scan cierra en el suyo
            ("escaneo confocal", lambda: (self.confocal_backend.request_stop(),
                                          sd.stop_in_thread(self.confocal_backend, "stop_scan",
                                                            self.confocal_thread, "escaneo confocal"))[1]),
            ("hilo confocal", lambda: sd.quit_thread(self.confocal_thread, "confocal")),
            ("luminiscencia", self.lumin_backend.shutdown),
            ("cinética", self.growth_backend.shutdown),
            ("dímeros", self.dimers_backend.shutdown),
            ("Step & Glue", self.sandg_backend.shutdown),
            ("calibración λ", self.auto_cal_controller.shutdown),
            ("escaneo lineal", self.linescan_worker.cancel_scan),
            ("hilo del escaneo lineal", lambda: sd.quit_thread(self.linescan_thread, "del escaneo lineal")),
        ]
        devices = [("obturador del espectrómetro", spectrometer_shutter), ("Shamrock", shamrock), ("cámara", camera)]
        def mirror_down():
            ok = flipper_notch532("down")            # como el legado al cerrar (Shutters_ps.py:201)
            return sd.ShutdownStep("espejo de detección", bool(ok), "abajo" if ok else "la placa no confirmó el pulso")

        return sd.ShutdownCoordinator(estop=hardware_session.emergency_stop, routines=routines, guests=guests,
                                      close_shutters=close_all_shutters, devices=devices,
                                      park=lambda: sd.park_stage(pi, PI_HOME_POS), mirror=mirror_down)

    def closeEvent(self, event):
        from config import PI_HOME_POS
        from pyspectrum.services.shutdown import closing_question_text
        if getattr(self, "_shut_down", False):
            event.accept()          # los equipos ya se cerraron: no se repite la secuencia
            return
        guests = self._open_guests()
        reply = QtWidgets.QMessageBox.question(
            self, '¿Cerrar PySpectrum?', closing_question_text(
                PI_HOME_POS, [g.name for g in guests],
                ["Hay una calibración en curso: se cancela y se guarda lo medido."]
                if self.auto_cal_controller.running else []),
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No,
        )
        if reply != QtWidgets.QMessageBox.StandardButton.Yes:
            event.ignore()
            return
        self._shut_down = True
        report = self._build_shutdown(guests).run()
        self.contrapropagante_satellite = self.microscopio_derecho_satellite = None
        if report.problems:
            QtWidgets.QMessageBox.warning(self, "Cierre de PySpectrum",
                                          "Estos pasos del cierre no se confirmaron:\n\n" + report.summary())
        event.accept()
