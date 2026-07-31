# -*- coding: utf-8 -*-
"""
nanopositioning.py — Control de la platina PI E-517 (XYZ)
PyPrinting — UNSAM Nanofotónica  —  PyQt6

Funcionalidades (idénticas al original Nanopositioning_pp.py):
  - Lectura de posición XYZ en tiempo real
  - Botones de movimiento relativo (×1 y ×10) en X, Y, Z
  - Go to absoluto con campos editables
  - Set reference / get reference
  - Señal read_pos_signal → [x, y, z] consumida por Cursor y Camera

Correcciones respecto al original:
  - isChecked() con paréntesis en todos los botones
  - pi_device importado desde config (singleton, sin ConnectUSB duplicado)
  - pressed → clicked en botones de movimiento (pressed no respetaba isEnabled)
"""
from __future__ import annotations
import time
import numpy as np

from PyQt6.QtCore    import Qt, QObject, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (QApplication, QFrame, QWidget, QGridLayout,
                              QHBoxLayout, QLabel, QLineEdit, QPushButton)
from PyQt6.QtGui     import QFont
from pyqtgraph.dockarea import DockArea, Dock

from config import (pi, PI_AXES,
                    DEFAULT_NANO_STEP_XY, DEFAULT_NANO_STEP_Z,
                    DEFAULT_NANO_GOTO_X, DEFAULT_NANO_GOTO_Y, DEFAULT_NANO_GOTO_Z)


# ══════════════════════════════════════════════════════════════════════════════
class Frontend(QFrame):

    read_pos_button_signal = pyqtSignal()
    move_signal            = pyqtSignal(str, float)
    go_to_pos_signal       = pyqtSignal(list)
    set_reference_signal   = pyqtSignal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._setup_gui()

    # ── Slots de actualización de UI ──────────────────────────────────────────

    @pyqtSlot(list)
    def read_pos_list(self, positions: list):
        self.xLabel.setText(f"{positions[0]:.3f}")
        self.yLabel.setText(f"{positions[1]:.3f}")
        self.zLabel.setText(f"{positions[2]:.3f}")

    @pyqtSlot(list)
    def get_go_to_reference(self, positions: list):
        self.xgotoLabel.setText(f"{positions[0]:.3f}")
        self.ygotoLabel.setText(f"{positions[1]:.3f}")
        self.zgotoLabel.setText(f"{positions[2]:.3f}")

    # ── Acciones de botones ───────────────────────────────────────────────────

    def get_read_pos(self):
        self.read_pos_button_signal.emit()

    def _step(self): return float(self.StepEdit.text())
    def _zstep(self): return float(self.zStepEdit.text())

    def xUp(self):    self.move_signal.emit('x',   self._step())
    def xUp2(self):   self.move_signal.emit('x',  10*self._step())
    def xDown(self):  self.move_signal.emit('x',  -self._step())
    def xDown2(self): self.move_signal.emit('x', -10*self._step())
    def yUp(self):    self.move_signal.emit('y',   self._step())
    def yUp2(self):   self.move_signal.emit('y',  10*self._step())
    def yDown(self):  self.move_signal.emit('y',  -self._step())
    def yDown2(self): self.move_signal.emit('y', -10*self._step())
    def zUp(self):    self.move_signal.emit('z',   self._zstep())
    def zUp2(self):   self.move_signal.emit('z',  10*self._zstep())
    def zDown(self):  self.move_signal.emit('z',  -self._zstep())
    def zDown2(self): self.move_signal.emit('z', -10*self._zstep())

    def set_reference(self):
        self.set_reference_signal.emit()

    def go_to_action(self):
        go_to_pos = [
            float(self.xgotoLabel.text()),
            float(self.ygotoLabel.text()),
            float(self.zgotoLabel.text()),
        ]
        self.go_to_pos_signal.emit(go_to_pos)

    # ── Construcción de la GUI ────────────────────────────────────────────────

    def _setup_gui(self):
        S = 46   # tamaño fijo de botones de flecha

        bold = QFont(); bold.setBold(True)

        # ── Posicionador ──────────────────────────────────────────────────────
        self.read_pos_button = QPushButton("Read position")
        self.read_pos_button.clicked.connect(self.get_read_pos)
        self.set_ref_button  = QPushButton("Set reference")
        self.set_ref_button.clicked.connect(self.set_reference)

        self.StepEdit  = QLineEdit(str(int(DEFAULT_NANO_STEP_XY) if DEFAULT_NANO_STEP_XY.is_integer() else DEFAULT_NANO_STEP_XY))
        self.zStepEdit = QLineEdit(str(int(DEFAULT_NANO_STEP_Z) if DEFAULT_NANO_STEP_Z.is_integer() else DEFAULT_NANO_STEP_Z))
        self.StepEdit.setFixedWidth(44)
        self.zStepEdit.setFixedWidth(44)

        def axis_label(text):
            lbl = QLabel(f"<b>{text} =</b>")
            lbl.setTextFormat(Qt.TextFormat.RichText)
            return lbl

        def val_label():
            lbl = QLabel("NaN")
            lbl.setFixedWidth(64)
            return lbl

        self.xname  = axis_label("x"); self.xLabel  = val_label()
        self.yname  = axis_label("y"); self.yLabel  = val_label()
        self.zname  = axis_label("z"); self.zLabel  = val_label()

        def btn(text, slot, w=S):
            b = QPushButton(text)
            b.setFixedWidth(w)
            b.clicked.connect(slot)
            return b

        self.xUpButton    = btn("x ►",  self.xUp)
        self.xUp2Button   = btn("x ►►", self.xUp2)
        self.xDownButton  = btn("◄ x",  self.xDown)
        self.xDown2Button = btn("◄◄ x", self.xDown2)
        self.yUpButton    = btn("y ▲",  self.yUp)
        self.yUp2Button   = btn("y ▲▲", self.yUp2)
        self.yDownButton  = btn("y ▼",  self.yDown)
        self.yDown2Button = btn("y ▼▼", self.yDown2)
        self.zUpButton    = btn("z ▲",  self.zUp)
        self.zUp2Button   = btn("z ▲▲", self.zUp2)
        self.zDownButton  = btn("z ▼",  self.zDown)
        self.zDown2Button = btn("z ▼▼", self.zDown2)

        positioner = QWidget()
        lo = QGridLayout(positioner)

        lo.addWidget(self.read_pos_button, 0, 0, 1, 2)
        lo.addWidget(self.xname,           1, 0)
        lo.addWidget(self.xLabel,          1, 1)
        lo.addWidget(self.xDown2Button,    2, 3, 2, 1)
        lo.addWidget(self.xDownButton,     2, 4, 2, 1)
        lo.addWidget(self.xUpButton,       2, 6, 2, 1)
        lo.addWidget(self.xUp2Button,      2, 7, 2, 1)
        lo.addWidget(self.yname,           2, 0)
        lo.addWidget(self.yLabel,          2, 1)
        lo.addWidget(self.yUp2Button,      0, 5, 2, 1)
        lo.addWidget(self.yUpButton,       1, 5, 3, 1)
        lo.addWidget(self.yDownButton,     3, 5, 2, 1)
        lo.addWidget(self.yDown2Button,    4, 5, 2, 1)
        lo.addWidget(QLabel("step x/y [µm]"), 4, 6, 1, 2)
        lo.addWidget(self.StepEdit,        5, 6)
        lo.addWidget(self.zname,           4, 0)
        lo.addWidget(self.zLabel,          4, 1)
        lo.addWidget(self.zUp2Button,      0, 9, 2, 1)
        lo.addWidget(self.zUpButton,       1, 9, 3, 1)
        lo.addWidget(self.zDownButton,     3, 9, 2, 1)
        lo.addWidget(self.zDown2Button,    4, 9, 2, 1)
        lo.addWidget(QLabel("step z [µm]"), 4, 10)
        lo.addWidget(self.zStepEdit,       5, 10)
        lo.addWidget(self.set_ref_button,  5, 0)

        # ── Go to ─────────────────────────────────────────────────────────────
        gotoWidget = QWidget()
        lo2 = QGridLayout(gotoWidget)

        lo2.addWidget(QLabel("X [µm]"), 1, 1)
        lo2.addWidget(QLabel("Y [µm]"), 2, 1)
        lo2.addWidget(QLabel("Z [µm]"), 3, 1)

        self.xgotoLabel = QLineEdit(str(int(DEFAULT_NANO_GOTO_X) if DEFAULT_NANO_GOTO_X.is_integer() else DEFAULT_NANO_GOTO_X))
        self.ygotoLabel = QLineEdit(str(int(DEFAULT_NANO_GOTO_Y) if DEFAULT_NANO_GOTO_Y.is_integer() else DEFAULT_NANO_GOTO_Y))
        self.zgotoLabel = QLineEdit(str(int(DEFAULT_NANO_GOTO_Z) if DEFAULT_NANO_GOTO_Z.is_integer() else DEFAULT_NANO_GOTO_Z))
        for w in (self.xgotoLabel, self.ygotoLabel, self.zgotoLabel):
            w.setFixedWidth(54)

        self.gotoButton = QPushButton("Go to")
        self.gotoButton.clicked.connect(self.go_to_action)

        lo2.addWidget(self.gotoButton,    1, 5, 2, 2)
        lo2.addWidget(self.xgotoLabel,    1, 2)
        lo2.addWidget(self.ygotoLabel,    2, 2)
        lo2.addWidget(self.zgotoLabel,    3, 2)

        # ── Docks ─────────────────────────────────────────────────────────────
        hbox = QHBoxLayout(self)
        dock_area = DockArea()

        posDock = Dock("Positioners", size=(1, 1))
        posDock.addWidget(positioner)
        dock_area.addDock(posDock)

        gotoDock = Dock("Go to", size=(1, 1))
        gotoDock.addWidget(gotoWidget)
        dock_area.addDock(gotoDock, "left", posDock)

        hbox.addWidget(dock_area)
        self.setLayout(hbox)

    def make_connection(self, backend: Backend):
        backend.read_pos_signal.connect(self.read_pos_list)
        backend.reference_signal.connect(self.get_go_to_reference)


# ══════════════════════════════════════════════════════════════════════════════
class Backend(QObject):

    read_pos_signal  = pyqtSignal(list)    # → [x_um, y_um, z_um]
    reference_signal = pyqtSignal(list)    # → [x_um, y_um, z_um] al set_reference

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        pi.connect()
        self.read_pos()

    @pyqtSlot()
    def read_pos(self) -> tuple[float, float, float]:
        pos   = pi.qPOS()
        x_pos = round(pos["1"], 3)
        y_pos = round(pos["2"], 3)
        z_pos = round(pos["3"], 3)
        self.read_pos_signal.emit([x_pos, y_pos, z_pos])
        return x_pos, y_pos, z_pos

    @pyqtSlot()
    def set_reference(self):
        x_pos, y_pos, z_pos = self.read_pos()
        self.reference_signal.emit([x_pos, y_pos, z_pos])

    @pyqtSlot(str, float)
    def move(self, axis: str, dist: float):
        """Movimiento relativo en el eje indicado."""
        x_pos, y_pos, z_pos = self.read_pos()
        axis_map = {"x": (1, x_pos), "y": (2, y_pos), "z": (3, z_pos)}
        if axis not in axis_map:
            print(f"[Nano] Eje desconocido: {axis}")
            return
        ax_num, current = axis_map[axis]
        target = current + dist
        pi.MOV(ax_num, target)
        while not all(pi.qONT(ax_num).values()):
            time.sleep(0.01)
        self.read_pos()

    @pyqtSlot(list)
    def goto(self, go_to_pos: list):
        if go_to_pos[2] < 0:
            print("[Nano] Z no puede ser negativo.")
            return
        self._moveto(go_to_pos)
        self.read_pos()

    def _moveto(self, pos: list):
        pi.MOV(PI_AXES, pos)
        while not all(pi.qONT(PI_AXES).values()):
            time.sleep(0.01)

    def make_connection(self, frontend: Frontend):
        frontend.read_pos_button_signal.connect(self.read_pos)
        frontend.move_signal.connect(self.move)
        frontend.set_reference_signal.connect(self.set_reference)
        frontend.go_to_pos_signal.connect(self.goto)


# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    gui    = Frontend()
    worker = Backend()
    worker.make_connection(gui)
    gui.make_connection(worker)
    thread = QThread()
    worker.moveToThread(thread)
    thread.start()
    gui.show()
    sys.exit(app.exec())
