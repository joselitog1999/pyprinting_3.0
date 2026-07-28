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
from tkinter import filedialog
import tkinter as tk

from PyQt6.QtCore    import QObject, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget,
                              QGridLayout, QMessageBox)
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
from camera          import (Frontend as CameraFrontend,  Backend as CameraBackend,
                              Laser532Window, Laser532Backend)


# ══════════════════════════════════════════════════════════════════════════════
class Frontend(QMainWindow):

    selectDirSignal    = pyqtSignal()
    createDirSignal    = pyqtSignal()
    openDirSignal      = pyqtSignal()
    loadPositionSignal = pyqtSignal()
    loadGridSignal     = pyqtSignal()
    closeSignal        = pyqtSignal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        title = "PyPrinting — UNSAM Nanofotónica"
        if SAFE_MODE:
            title += "  [MODO SEGURO — sin hardware]"
        self.setWindowTitle(title)
        self._cwidget = QWidget()
        self.setCentralWidget(self._cwidget)
        self.setGeometry(30, 30, 1440, 980)
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
        self._add_action(tm, "Láser 532",  self.tools_laser532)
        self._add_action(tm, "Load Grid",  self.load_grid)
        mm = mb.addMenu("&Measurements")
        self._add_action(mm, "Printing",   self.measurement_printing)
        self._add_action(mm, "Dimers",     self.measurement_dimers)
        dm = mb.addMenu("&Docks")
        self._add_action(dm, "Guardar configuración",   self.save_docks)
        self._add_action(dm, "Restaurar configuración", self.load_docks)

    def _setup_docks(self):
        grid = QGridLayout(self._cwidget)
        grid.setContentsMargins(0, 0, 0, 0)
        self.dockArea = DockArea()
        grid.addWidget(self.dockArea)

        # ══════════════════════════════════════════════════════════════════════
        # Matriz 3×4 (filas × cols):
        #
        #  col →   1            2            3            4
        #  f 1  │  Cámara    │  Cámara    │  Confocal  │  Confocal  │
        #  f 2  │  Cámara    │  Cámara    │  Trace     │  Trace     │
        #  f 3  │  Shutters  │  Focus z   │  Nano      │  Nano      │
        #
        # En términos de pyqtgraph DockArea (posicionamiento relativo):
        #   - Confocal   → ancla principal (fila 1, cols 3-4)
        #   - Trace      → bottom de Confocal   (fila 2, cols 3-4)
        #   - Nano       → bottom de Trace       (fila 3, cols 3-4)
        #   - Cámara     → left de Confocal      (filas 1-2, cols 1-2)
        #   - Shutters   → bottom de Cámara      (fila 3, col 1)
        #   - Focus z    → right de Shutters     (fila 3, col 2)
        #
        # Proporciones (w, h) son relativas dentro de la DockArea.
        # Confocal y Cámara comparten la misma h → mismo número.
        # Trace ≈ 45% de la h de Confocal.
        # Nano ≈ 35% de la h de Confocal.
        # Shutters y Focus z comparten la h de Nano; Shutters ≈ Focus z.
        # ══════════════════════════════════════════════════════════════════════

        # 1. Confocal — ancla principal (fila 1, cols 3-4).
        #    Su DockArea interna organiza: Viewbox | Params | CM | Drift.
        confocalDock = Dock("Confocal", size=(580, 380))
        self.confocalWidget = ConfocalFrontend()
        confocalDock.addWidget(self.confocalWidget)
        self.dockArea.addDock(confocalDock)

        # 2. Trace — bajo Confocal (fila 2, cols 3-4).
        traceDock = Dock("Trace", size=(580, 175))
        self.traceWidget = TraceFrontend()
        traceDock.addWidget(self.traceWidget)
        self.dockArea.addDock(traceDock, "bottom", confocalDock)

        # 3. Nano — bajo Trace (fila 3, cols 3-4).
        nanoDock = Dock("Nanopositioning", size=(580, 140))
        self.nanoWidget = NanoFrontend()
        nanoDock.addWidget(self.nanoWidget)
        self.dockArea.addDock(nanoDock, "bottom", traceDock)

        # 4. Cámara — izquierda de Confocal, ocupa filas 1-2 (cols 1-2).
        #    La altura se fija igual a Confocal + Trace para que las dos
        #    filas de la izquierda coincidan con las dos de la derecha.
        cameraDock = Dock("Cámara — Canon EOS", size=(280, 555))
        self.cameraWidget = CameraFrontend()
        cameraDock.addWidget(self.cameraWidget)
        self.dockArea.addDock(cameraDock, "left", confocalDock)

        # 5. Shutters — bajo Cámara (fila 3, col 1).
        shuttersDock = Dock("Shutters / Flipper / Láser 532", size=(140, 140))
        self.shuttersWidget = ShuttersFrontend()
        shuttersDock.addWidget(self.shuttersWidget)
        self.dockArea.addDock(shuttersDock, "bottom", cameraDock)

        # 6. Focus z — derecha de Shutters (fila 3, col 2).
        focusDock = Dock("Focus z", size=(140, 140))
        self.focusWidget = FocusFrontend()
        focusDock.addWidget(self.focusWidget)
        self.dockArea.addDock(focusDock, "right", shuttersDock)

        # ── Ventanas flotantes (bajo demanda desde el menú) ───────────────────
        self.laser532Window = Laser532Window()
        self.printingWidget = MeasFrontend(mode="printing")
        self.dimersWidget   = MeasFrontend(mode="dimers")

        # En modo seguro: deshabilitar menú Measurements
        if SAFE_MODE:
            for action in self.menuBar().actions():
                if action.text() == "&Measurements":
                    action.setEnabled(False)
                    action.setToolTip("No disponible en modo seguro")

    def get_selectDir(self):        self.selectDirSignal.emit()
    def get_createDir(self):        self.createDirSignal.emit()
    def get_openDir(self):          self.openDirSignal.emit()
    def load_last_position(self):   self.loadPositionSignal.emit()
    def load_grid(self):            self.loadGridSignal.emit()
    def measurement_printing(self): self.printingWidget.show()
    def measurement_dimers(self):   self.dimersWidget.show()
    def tools_laser532(self):       self.laser532Window.show()

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
        backend.cameraWorker.make_connection(self.cameraWidget)
        backend.laser532Backend.make_connection(self.laser532Window)
        backend.printingWorker.make_connection(self.printingWidget)
        backend.dimersWorker.make_connection(self.dimersWidget)

        def _on_set_reference(x_px: float, y_px: float):
            try:
                pos = pi.qPOS()
                backend.cameraWorker.set_reference(
                    x_px, y_px, round(pos["1"], 3), round(pos["2"], 3))
            except Exception as e:
                print(f"[App] Error al leer posición PI: {e}")

        self.cameraWidget.setReferenceSignal.connect(_on_set_reference)


# ══════════════════════════════════════════════════════════════════════════════
class Backend(QObject):

    fileSignal = pyqtSignal(str)
    gridSignal = pyqtSignal(str, np.ndarray)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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
        # Posición → cámara
        self.nanoWorker.read_pos_signal.connect(
            self.cameraWorker.update_cursor_from_pos)

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

        # Printing cycle
        self.printingWorker.grid_move_finishSignal.connect(
            self.printingWorker.grid_autofoco)
        self.printingWorker.grid_autofocusSignal.connect(
            self.focusWorker.focus_autocorr_lin_x2)
        self.printingWorker.grid_traceSignal.connect(
            self.traceWorker.trace_configuration)
        self.traceWorker.data_printingSignal.connect(self._dispatch_trace)
        self.printingWorker.grid_trace_stopSignal.connect(self.traceWorker.stop)
        self.printingWorker.grid_detectSignal.connect(self.printingWorker.grid_scan)
        self.printingWorker.grid_scanSignal.connect(
            self.confocalWorker.start_scan_routines)
        self.printingWorker.grid_scan_stopSignal.connect(
            self.confocalWorker.stop_scan)

        # Dimers cycle
        self.dimersWorker.grid_move_finishSignal.connect(
            self.dimersWorker.grid_autofoco)
        self.dimersWorker.grid_autofocusSignal.connect(
            self.focusWorker.focus_autocorr_lin_x2)
        self.dimersWorker.grid_traceSignal.connect(
            self.traceWorker.trace_configuration)
        self.traceWorker.data_printingSignal.connect(self._dispatch_trace)
        self.dimersWorker.grid_trace_stopSignal.connect(self.traceWorker.stop)
        self.dimersWorker.grid_detectSignal.connect(self.dimersWorker.grid_finish)
        self.dimersWorker.grid_scanSignal.connect(
            self.confocalWorker.start_scan_routines)
        self.dimersWorker.grid_scan_stopSignal.connect(
            self.confocalWorker.stop_scan)

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

    @pyqtSlot()
    def selectDir(self):
        root = tk.Tk(); root.withdraw()
        path = filedialog.askdirectory()
        if path:
            self.file_path = path; self.fileSignal.emit(path)

    @pyqtSlot()
    def openDir(self):
        os.startfile(self.file_path)

    @pyqtSlot()
    def create_daily_directory(self):
        root = tk.Tk(); root.withdraw()
        path = filedialog.askdirectory()
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

    @pyqtSlot()
    def load_grid(self):
        root = tk.Tk(); root.withdraw()
        name = filedialog.askopenfilename()
        if name:
            datos = np.loadtxt(name, unpack=True)
            self.gridSignal.emit("Load_grid", datos)

    @pyqtSlot()
    def close_all(self):
        try:
            pos = pi.qPOS()
            last_pos = [round(pos["1"], 3), round(pos["2"], 3), round(pos["3"], 3)]
            np.savetxt(LAST_POS_FILE, last_pos)
            print(f"[App] Posición guardada: {last_pos}")
        except Exception as e:
            print(f"[App] No se pudo guardar posición: {e}")
        self.cameraWorker.close()
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