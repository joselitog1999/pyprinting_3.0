# -*- coding: utf-8 -*-
"""
app.py — Entry point de PyPrinting (versión final migrada a PyQt6)
PyPrinting — UNSAM Nanofotónica

Todos los módulos están migrados. No quedan importaciones _pp legacy.

Threads:
  instrumentThread  → nanoWorker, shuttersWorker, laser532Backend
  confocalThread    → confocalWorker, focusWorker, traceWorker,
                      printingWorker, dimersWorker
  cameraThread      → cameraWorker
"""
from __future__ import annotations
import os, sys, time
from pathlib import Path
from datetime import datetime

import numpy as np

from PyQt6.QtCore    import QObject, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget,
                              QGridLayout, QMessageBox, QFileDialog)
from PyQt6.QtGui     import QAction, QKeySequence
from pyqtgraph.dockarea import DockArea, Dock

from config          import pi, DEFAULT_DATA_PATH, LAST_POS_FILE, SAFE_MODE
from nidaq           import flipper_notch532, close_all_tasks
from nanopositioning import Frontend as NanoFrontend,    Backend as NanoBackend
from shutters        import Frontend as ShuttersFrontend, Backend as ShuttersBackend
from focus           import Frontend as FocusFrontend,    Backend as FocusBackend
from trace           import Frontend as TraceFrontend,    Backend as TraceBackend
from confocal        import Frontend as ConfocalFrontend, Backend as ConfocalBackend
from measurements    import Frontend as MeasFrontend,     Backend as MeasBackend
from camera          import (CameraWindow, CanonWorker as CameraBackend,
                              Laser532Window, Laser532Backend)
from image_analyzer  import ImageAnalyzerWidget, ImageAnalyzerWindow
from psf_analyzer    import PSFAnalyzerWidget, PSFAnalyzerWindow


# ══════════════════════════════════════════════════════════════════════════════
class Frontend(QMainWindow):

    selectDirSignal    = pyqtSignal(str)
    createDirSignal    = pyqtSignal(str)
    openDirSignal      = pyqtSignal()
    loadPositionSignal = pyqtSignal()
    loadGridSignal     = pyqtSignal(str)
    closeSignal        = pyqtSignal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        title = "PyPrinting — UNSAM Nanofotónica"
        if SAFE_MODE:
            title += "  [MODO SEGURO — sin hardware]"
        self.setWindowTitle(title)
        self._cwidget = QWidget()
        self.setCentralWidget(self._cwidget)
        self.setMinimumSize(1000, 600)
        self.resize(1440, 900)
        self._setup_menu()
        self._setup_docks()

    def _add_action(self, menu, label, slot, shortcut=None):
        a = QAction(label, self)
        a.triggered.connect(slot)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        menu.addAction(a)

    def _setup_menu(self):
        mb = self.menuBar()
        fm = mb.addMenu("&Files")
        self._add_action(fm, "Seleccionar directorio",  self.get_selectDir,      "Ctrl+A")
        self._add_action(fm, "Crear directorio diario", self.get_createDir,      "Ctrl+S")
        self._add_action(fm, "Abrir directorio",        self.get_openDir,        "Ctrl+D")
        self._add_action(fm, "Cargar última posición",  self.load_last_position)
        tm = mb.addMenu("&Tools")
        self._add_action(tm, "Tablero de Conexiones", self.tools_hardware_dashboard, "Ctrl+H")
        self._add_action(tm, "Cámara",                self.tools_camera)
        self._add_action(tm, "Analizador de Imágenes", self.tools_image_analyzer)
        self._add_action(tm, "PSF Analyzer",          self.tools_psf_analyzer)
        self._add_action(tm, "Diseñador de Redes 2D", self.tools_grid_generator,   "Ctrl+G")
        self._add_action(tm, "Láser 532",             self.tools_laser532)
        self._add_action(tm, "Load Grid",             self.load_grid)
        mm = mb.addMenu("&Measurements")
        self._add_action(mm, "Printing",   self.measurement_printing)
        self._add_action(mm, "Dimers",     self.measurement_dimers)
        dm = mb.addMenu("&Docks")
        self._add_action(dm, "Guardar configuración",   self.save_docks)
        self._add_action(dm, "Restaurar configuración", self.load_docks)
        
        # Barra de Estado Global
        self.statusBar().showMessage("🟢 PyPrinting listo | Todos los sistemas en estado nominal")

    def _setup_docks(self):
        grid = QGridLayout(self._cwidget)
        grid.setContentsMargins(0, 0, 0, 0)
        self.dockArea = DockArea()
        grid.addWidget(self.dockArea)

        # 1. Confocal — arriba izquierda
        confocalDock = Dock("Confocal", size=(600, 400))
        self.confocalWidget = ConfocalFrontend()
        confocalDock.addWidget(self.confocalWidget)
        self.dockArea.addDock(confocalDock)

        # 2. Focus z — bajo el confocal
        focusDock = Dock("Focus z", size=(260, 180))
        self.focusWidget = FocusFrontend()
        focusDock.addWidget(self.focusWidget)
        self.dockArea.addDock(focusDock, "bottom", confocalDock)

        # 3. Shutters / Flipper / Láser 532 — a la derecha de focus
        shuttersDock = Dock("Shutters / Flipper / Láser 532", size=(360, 180))
        self.shuttersWidget = ShuttersFrontend()
        shuttersDock.addWidget(self.shuttersWidget)
        self.dockArea.addDock(shuttersDock, "right", focusDock)

        # 4. Nanopositioning — a la izquierda de focus
        nanoDock = Dock("Nanopositioning", size=(200, 180))
        self.nanoWidget = NanoFrontend()
        nanoDock.addWidget(self.nanoWidget)
        self.dockArea.addDock(nanoDock, "left", focusDock)

        # 5. Trace — abajo de todo ocupando todo el ancho de la ventana
        traceDock = Dock("Trace", size=(1400, 260))
        self.traceWidget = TraceFrontend()
        traceDock.addWidget(self.traceWidget)
        self.dockArea.addDock(traceDock, "bottom")

        # ── Ventanas flotantes (bajo demanda desde menú) ─────────────────────
        from modules.hardware_dashboard import HardwareDashboardWindow
        self.hardwareWindow      = HardwareDashboardWindow()# Tools → Tablero de Conexiones (Ctrl+H)
        self.hardwareWidget      = self.hardwareWindow.widget  # Para compatibilidad de señal
        self.cameraWindow        = CameraWindow()          # Tools → Cámara
        self.imageAnalyzerWindow = ImageAnalyzerWindow()   # Tools → Analizador de Imágenes
        self.psfAnalyzerWindow   = PSFAnalyzerWindow()     # Tools → PSF Analyzer
        self.laser532Window      = Laser532Window()         # Tools → Láser 532
        self.printingWidget      = MeasFrontend(mode="printing")
        self.dimersWidget        = MeasFrontend(mode="dimers")

        # Nota: El menú Measurements está desbloqueado tanto en MODO REAL como en MODO MOCK/SAFE_MODE para depuración.

    def get_selectDir(self):
        path = QFileDialog.getExistingDirectory(self, "Seleccionar directorio de datos", "")
        if path:
            self.selectDirSignal.emit(path)

    def get_createDir(self):
        path = QFileDialog.getExistingDirectory(self, "Seleccionar directorio base", "")
        if path:
            self.createDirSignal.emit(path)

    def get_openDir(self):          self.openDirSignal.emit()
    def load_last_position(self):   self.loadPositionSignal.emit()

    def load_grid(self):
        name, _ = QFileDialog.getOpenFileName(
            self, "Cargar Grilla de Coordenadas", "", "Archivos (*.txt *.csv *.dat);;Todos (*.*)"
        )
        if name:
            self.loadGridSignal.emit(name)
    def measurement_printing(self): self.printingWidget.show()
    def measurement_dimers(self):   self.dimersWidget.show()
    def tools_camera(self):         self.cameraWindow.show(); self.cameraWindow.raise_()
    def tools_image_analyzer(self): self.imageAnalyzerWindow.show(); self.imageAnalyzerWindow.raise_()
    def tools_psf_analyzer(self):   self.psfAnalyzerWindow.show(); self.psfAnalyzerWindow.raise_()
    def tools_grid_generator(self):
        if not hasattr(self, "_gridGenWindow") or self._gridGenWindow is None:
            from grid_generator import GridGeneratorWindow
            self._gridGenWindow = GridGeneratorWindow(self)
        self._gridGenWindow.show()
        self._gridGenWindow.raise_()
        self._gridGenWindow.activateWindow()
    def tools_laser532(self):       self.laser532Window.show()
    def tools_hardware_dashboard(self):
        self.hardwareWindow.show()
        self.hardwareWindow.raise_()
        self.hardwareWindow.activateWindow()


    def save_docks(self):
        self._dock_state = self.dockArea.saveState()

    def load_docks(self):
        if hasattr(self, "_dock_state"):
            self.dockArea.restoreState(self._dock_state)

    def closeEvent(self, event):
        reply = QMessageBox.question(
            self, "Salir", "¿Cerrar PyPrinting?",
            QMessageBox.StandardButton.No | QMessageBox.StandardButton.Yes)
        if reply == QMessageBox.StandardButton.Yes:
            self.closeSignal.emit(); event.accept()
        else:
            event.ignore()

    def make_connection(self, backend: Backend):
        backend.nanoWorker.make_connection(self.nanoWidget)
        backend.shuttersWorker.make_connection(self.shuttersWidget)
        backend.focusWorker.make_connection(self.focusWidget)
        backend.traceWorker.make_connection(self.traceWidget)
        backend.confocalWorker.make_connection(self.confocalWidget)
        backend.cameraWorker.make_connection(self.cameraWindow)
        backend.laser532Backend.make_connection(self.laser532Window)
        backend.printingWorker.make_connection(self.printingWidget)
        backend.dimersWorker.make_connection(self.dimersWidget)

        # Conectar barra de estado global en tiempo real (Frontend es el QMainWindow con statusBar)
        backend.printingWorker.indexSignal.connect(
            lambda i: self.statusBar().showMessage(f"📍 Posicionando e imprimiendo partícula {i}..."))
        backend.printingWorker.grid_autofocusSignal.connect(
            lambda m: self.statusBar().showMessage("🔍 Ejecutando autofoco Z por correlación axial..."))
        backend.printingWorker.grid_traceSignal.connect(
            lambda l, m: self.statusBar().showMessage(f"⚡ Adquiriendo traza fototérmica ({l}) a ALTA potencia..."))
        backend.printingWorker.grid_scanSignal.connect(
            lambda l, m, n: self.statusBar().showMessage(f"🔬 Escaneo confocal 2D en curso ({n})..."))
        backend.printingWorker.patternFinishedSignal.connect(
            lambda path: self.statusBar().showMessage(f"🎉 Patrón completado en: {path}"))

        backend.dimersWorker.indexSignal.connect(
            lambda i: self.statusBar().showMessage(f"📍 Posicionando y ensamblando dímero {i}..."))
        backend.dimersWorker.grid_autofocusSignal.connect(
            lambda m: self.statusBar().showMessage("🔍 Ejecutando autofoco Z por correlación axial..."))
        backend.dimersWorker.grid_traceSignal.connect(
            lambda l, m: self.statusBar().showMessage(f"⚡ Adquiriendo traza dímero ({l})..."))
        backend.dimersWorker.grid_scanSignal.connect(
            lambda l, m, n: self.statusBar().showMessage(f"🔬 Escaneo confocal 2D dímero ({n})..."))
        backend.dimersWorker.patternFinishedSignal.connect(
            lambda path: self.statusBar().showMessage(f"🎉 Lote de dímeros completado en: {path}"))

        # Referencia cámara ↔ platina: cuando el usuario hace Set ref. en la
        # CameraWindow, se lee la posición actual de la platina y se envía al Backend.
        def _on_set_reference(fx: float, fy: float):
            try:
                from config import pi
                pos   = pi.qPOS()
                x_um  = round(pos["1"], 3)
                y_um  = round(pos["2"], 3)
                # Informar a la CameraWindow la posición de platina en ref.
                self.cameraWindow.set_ref_pos_um([x_um, y_um, 0])
                print(f"[App] Referencia fijada: px({fx:.3f},{fy:.3f}) ↔ "
                      f"platina({x_um},{y_um})µm")
            except Exception as e:
                print(f"[App] Error leyendo posición PI para referencia: {e}")

        self.cameraWindow.setReferenceSignal.connect(_on_set_reference)

        # Propagar cambio de directorio a la cámara
        def _on_file_signal(path: str):
            self.cameraWindow.directorySignal.emit(path)
        backend.fileSignal.connect(_on_file_signal)


# ══════════════════════════════════════════════════════════════════════════════
class Backend(QObject):

    fileSignal = pyqtSignal(str)
    gridSignal = pyqtSignal(str, np.ndarray)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from core.hardware_manager import hardware_manager
        hardware_manager.set_profile("pyprinting", rescan=False)
        pi.connect()

        self.nanoWorker      = NanoBackend()
        self.shuttersWorker  = ShuttersBackend()
        self.focusWorker     = FocusBackend()
        self.traceWorker     = TraceBackend()
        self.confocalWorker  = ConfocalBackend()
        self.printingWorker  = MeasBackend(mode="printing")
        self.dimersWorker    = MeasBackend(mode="dimers")
        self.cameraWorker    = CameraBackend()
        self.laser532Backend = Laser532Backend()

        self.file_path = str(DEFAULT_DATA_PATH)
        self._connect_backends()

    def _connect_backends(self):
        # Vincular focus worker a confocal worker para escaneo con corrección dinámica de inclinación Z
        self.confocalWorker.focus_backend = self.focusWorker

        # Focus done → leer posición
        for sig in (self.focusWorker.gotomaxdoneSignal,
                    self.focusWorker.lockdoneSignal,
                    self.focusWorker.autodoneSignal,
                    self.confocalWorker.scandoneSignal,
                    self.printingWorker.grid_move_finishSignal,
                    self.printingWorker.goSignal,
                    self.dimersWorker.grid_move_finishSignal,
                    self.dimersWorker.goSignal):
            sig.connect(self.nanoWorker.read_pos)

        # autofinishSignal(mode) → dispatch
        def _on_autofinish(mode: str):
            if mode == "printing": self.printingWorker.grid_finish_autofoco()
            elif mode == "dimers": self.dimersWorker.grid_finish_autofoco()
        self.focusWorker.autofinishSignal.connect(_on_autofinish)

        # scanfinishedSignal unificada
        self.confocalWorker.scanfinishedSignal.connect(
            self.printingWorker.on_scan_finished)
        self.confocalWorker.scanfinishedSignal.connect(
            self.dimersWorker.on_scan_finished)

        # Shared trace cycle (conectado una sola vez para evitar disparos dobles)
        self.traceWorker.data_printingSignal.connect(self._dispatch_trace)

        # Printing cycle
        self.printingWorker.grid_move_finishSignal.connect(
            self.printingWorker.grid_autofoco)
        self.printingWorker.grid_autofocusSignal.connect(
            self.focusWorker.focus_autocorr_lin_x2)
        self.printingWorker.grid_traceSignal.connect(
            self.traceWorker.trace_configuration)
        self.printingWorker.grid_trace_stopSignal.connect(self.traceWorker.stop)
        self.printingWorker.grid_detectSignal.connect(self.printingWorker.grid_scan)
        self.printingWorker.grid_scanSignal.connect(
            self.confocalWorker.start_scan_routines)
        self.printingWorker.grid_scan_stopSignal.connect(
            self.confocalWorker.stop_scan)

        self.printingWorker.stepsParametersSignal.connect(
            self.traceWorker.parameters)

        # Dimers cycle
        self.dimersWorker.grid_move_finishSignal.connect(
            self.dimersWorker.grid_autofoco)
        self.dimersWorker.grid_autofocusSignal.connect(
            self.focusWorker.focus_autocorr_lin_x2)
        self.dimersWorker.grid_traceSignal.connect(
            self.traceWorker.trace_configuration)
        self.dimersWorker.stepsParametersSignal.connect(
            self.traceWorker.parameters)
        self.dimersWorker.grid_trace_stopSignal.connect(self.traceWorker.stop)
        self.dimersWorker.grid_detectSignal.connect(self.dimersWorker.grid_finish)
        self.dimersWorker.grid_scanSignal.connect(
            self.confocalWorker.start_scan_routines)
        self.dimersWorker.grid_scan_stopSignal.connect(
            self.confocalWorker.stop_scan)

        # Carga de Grilla (Load Grid) -> propagate to printingWorker and dimersWorker
        def _on_grid_loaded(name: str, datos: np.ndarray):
            for worker in (self.printingWorker, self.dimersWorker):
                worker.grid_x = datos[0, :]
                worker.grid_y = datos[1, :]
                worker.particulas = len(datos[0, :])
                worker.grid_name = name
                worker.particulasSignal.emit(len(datos[0, :]))
                worker.gridplotSignal.emit(datos)
            print(f"[App] Grilla cargada: {datos.shape[1]} partículas")
        self.gridSignal.connect(_on_grid_loaded)

        # Archivos
        for sig_slot in [
            (self.fileSignal, self.traceWorker.direction),
            (self.fileSignal, self.confocalWorker.direction),
            (self.fileSignal, self.cameraWorker.set_directory),
            (self.fileSignal, self.printingWorker.grid_direction),
            (self.fileSignal, self.dimersWorker.grid_direction),
        ]:
            sig_slot[0].connect(sig_slot[1])

    def _dispatch_trace(self, data: list):
        if not data:
            return
        mode    = data[-1] if isinstance(data[-1], str) else "none"
        payload = data[:-1]
        if mode == "printing":
            self.printingWorker.grid_trace_detect(payload)
        elif mode == "dimers":
            self.dimersWorker.grid_trace_detect(payload)

    @pyqtSlot(str)
    def selectDir(self, path: str):
        if path:
            self.file_path = path; self.fileSignal.emit(path)

    @pyqtSlot()
    def openDir(self):
        os.startfile(self.file_path)

    @pyqtSlot(str)
    def create_daily_directory(self, path: str):
        if path:
            newpath = str(Path(path) / time.strftime("%Y-%m-%d"))
            Path(newpath).mkdir(parents=True, exist_ok=True)
            self.file_path = newpath; self.fileSignal.emit(newpath)
            print(f"[App] Directorio: {newpath}")

    @pyqtSlot()
    def load_last_position(self):
        try:
            last_pos = np.loadtxt(LAST_POS_FILE).tolist()
            pi.MOV([1, 2, 3], last_pos); time.sleep(0.1)
            print(f"[App] Última posición: {last_pos}")
        except Exception as e:
            print(f"[App] Error cargando posición: {e}")

    @pyqtSlot(str)
    def load_grid(self, name: str):
        if name and os.path.exists(name):
            try:
                datos = np.loadtxt(name, unpack=True)
                grid_name = os.path.splitext(os.path.basename(name))[0] or "Load_grid"
                self.gridSignal.emit(grid_name, datos)
            except Exception as e:
                print(f"[App] Error cargando grilla: {e}")

    @pyqtSlot()
    def close_all(self):
        try:
            pos = pi.qPOS()
            last_pos = [round(pos["1"], 3), round(pos["2"], 3), round(pos["3"], 3)]
            np.savetxt(LAST_POS_FILE, last_pos)
            print(f"[App] Posición guardada: {last_pos}")
        except Exception as e:
            print(f"[App] No se pudo guardar posición: {e}")
        if hasattr(self, 'cameraWorker') and self.cameraWorker:
            if hasattr(self.cameraWorker, 'close'):
                self.cameraWorker.close()
            elif hasattr(self.cameraWorker, 'stop_camera'):
                self.cameraWorker.stop_camera()
        close_all_tasks()
        flipper_notch532("down")
        pi.disconnect()
        print(f"[App] Cierre limpio — {datetime.now()}")

    def make_connection(self, frontend: Frontend):
        frontend.selectDirSignal.connect(self.selectDir)
        frontend.openDirSignal.connect(self.openDir)
        frontend.createDirSignal.connect(self.create_daily_directory)
        frontend.loadPositionSignal.connect(self.load_last_position)
        frontend.loadGridSignal.connect(self.load_grid)
        frontend.closeSignal.connect(self.close_all)
        frontend.nanoWidget.make_connection(self.nanoWorker)
        frontend.traceWidget.make_connection(self.traceWorker)
        frontend.focusWidget.make_connection(self.focusWorker)
        frontend.confocalWidget.make_connection(self.confocalWorker)
        frontend.printingWidget.make_connection(self.printingWorker)
        frontend.dimersWidget.make_connection(self.dimersWorker)


# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    if not QApplication.instance():
        app = QApplication(sys.argv); open_terminal = True
    else:
        app = QApplication.instance(); open_terminal = False

    gui    = Frontend()
    worker = Backend()
    gui.make_connection(worker)
    worker.make_connection(gui)

    instrumentThread = QThread()
    confocalThread   = QThread()
    cameraThread     = QThread()

    worker.nanoWorker.moveToThread(instrumentThread)
    worker.shuttersWorker.moveToThread(instrumentThread)
    worker.laser532Backend.moveToThread(instrumentThread)

    worker.focusWorker.moveToThread(confocalThread)
    worker.traceWorker.moveToThread(confocalThread)
    worker.confocalWorker.moveToThread(confocalThread)
    worker.printingWorker.moveToThread(confocalThread)
    worker.dimersWorker.moveToThread(confocalThread)

    worker.cameraWorker.moveToThread(cameraThread)

    instrumentThread.start()
    confocalThread.start()
    cameraThread.start()

    gui.show()
    if open_terminal:
        sys.exit(app.exec())
