# -*- coding: utf-8 -*-
"""
shutters.py — Control de shutters, flippers y láser 532 nm
PyPrinting — UNSAM Nanofotónica  —  PyQt6

Reemplaza Shutters_pp.py + Laser_532.py + Laseres.py.
Correcciones respecto al original:
  - shutter0button.clicked conectado a su método check, no a la señal directa
  - Lógica de polaridad delegada a nidaq.open_shutter / close_shutter
  - Laser 532 integrado en el mismo panel (no DearPyGui separado)
"""
from __future__ import annotations

from PyQt6.QtCore    import Qt, QObject, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (QApplication, QFrame, QWidget, QGridLayout,
                              QHBoxLayout, QVBoxLayout, QLabel, QCheckBox,
                              QDoubleSpinBox, QSlider, QPushButton)

from config  import SHUTTERS, LASER_532_V_MIN, LASER_532_V_MAX
from nidaq   import (open_shutter, close_shutter, up_flipper, down_flipper,
                     flipper_notch532, set_laser532_voltage, close_all_tasks)


# ══════════════════════════════════════════════════════════════════════════════
class Frontend(QFrame):

    shutter0_signal         = pyqtSignal(bool)
    shutter1_signal         = pyqtSignal(bool)
    shutter2_signal         = pyqtSignal(bool)
    shutter3_signal         = pyqtSignal(bool)
    flipper_signal          = pyqtSignal(bool)
    flipper_notch532_signal = pyqtSignal(bool)
    laser532_signal         = pyqtSignal(float)
    closeSignal             = pyqtSignal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._setup_gui()

    # ── Handlers de botones ───────────────────────────────────────────────────

    def _shutter0_check(self):
        self.shutter0_signal.emit(self.shutter0button.isChecked())

    def _shutter1_check(self):
        self.shutter1_signal.emit(self.shutter1button.isChecked())

    def _shutter2_check(self):
        self.shutter2_signal.emit(self.shutter2button.isChecked())

    def _shutter3_check(self):
        if hasattr(self, 'shutter3button') and self.shutter3button is not None:
            self.shutter3_signal.emit(self.shutter3button.isChecked())

    def _power_check(self):
        checked = self.powerbutton.isChecked()
        self.flipper_signal.emit(checked)
        if checked:
            self.powerbutton.setText("High\npower")
            self.powerbutton.setStyleSheet("color: rgb(200, 80, 40);")
        else:
            self.powerbutton.setText("Low\npower")
            self.powerbutton.setStyleSheet("color: rgb(12, 183, 242);")

    def _notch532_check(self):
        checked = self.notch532button.isChecked()
        self.flipper_notch532_signal.emit(checked)
        self.notch532button.setText("Mirror down" if checked else "Mirror up")

    def _on_laser_slider(self, value: int):
        v = value / 100.0
        self._laser_spin.blockSignals(True)
        self._laser_spin.setValue(v)
        self._laser_spin.blockSignals(False)
        self.laser532_signal.emit(v)

    def _on_laser_spin(self, v: float):
        self._laser_slider.blockSignals(True)
        self._laser_slider.setValue(int(v * 100))
        self._laser_slider.blockSignals(False)
        self.laser532_signal.emit(v)

    # ── GUI ───────────────────────────────────────────────────────────────────

    def _setup_gui(self):
        grid = QGridLayout(self)

        # ── Shutters ──────────────────────────────────────────────────────────
        self.shutter0button = QCheckBox(SHUTTERS[0])
        self.shutter0button.clicked.connect(self._shutter0_check)
        self.shutter0button.setStyleSheet("color: green;")
        self.shutter0button.setToolTip("Abrir/cerrar shutter 532 nm (verde)")

        self.shutter1button = QCheckBox(SHUTTERS[1])
        self.shutter1button.clicked.connect(self._shutter1_check)
        self.shutter1button.setStyleSheet("color: red;")
        self.shutter1button.setToolTip("Abrir/cerrar shutter 637 nm (rojo)")

        self.shutter2button = QCheckBox(SHUTTERS[2])
        self.shutter2button.clicked.connect(self._shutter2_check)
        self.shutter2button.setStyleSheet("color: #d4ac0d; font-weight: bold;")
        self.shutter2button.setToolTip("Abrir/cerrar shutter 592 nm (amarillo)")

        if len(SHUTTERS) > 3:
            self.shutter3button = QCheckBox(SHUTTERS[3])
            self.shutter3button.clicked.connect(self._shutter3_check)
            self.shutter3button.setStyleSheet("color: #ad1457; font-weight: bold;")
            self.shutter3button.setToolTip("Abrir/cerrar shutter 808 nm (infrarrojo)")
        else:
            self.shutter3button = None

        # ── Flippers ─────────────────────────────────────────────────────────
        self.powerbutton = QCheckBox("Low\npower")
        self.powerbutton.clicked.connect(self._power_check)

        self.notch532button = QCheckBox("Mirror up")
        self.notch532button.clicked.connect(self._notch532_check)

        # ── Láser 532 ─────────────────────────────────────────────────────────
        laser_label = QLabel("Láser 532 nm (ao2)")
        laser_label.setStyleSheet("color: #55cc55; font-weight: bold;")

        self._laser_slider = QSlider(Qt.Orientation.Horizontal)
        self._laser_slider.setMinimum(int(LASER_532_V_MIN * 100))
        self._laser_slider.setMaximum(int(LASER_532_V_MAX * 100))
        self._laser_slider.setValue(int(LASER_532_V_MIN * 100))
        self._laser_slider.setTickInterval(50)
        self._laser_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._laser_slider.valueChanged.connect(self._on_laser_slider)

        self._laser_spin = QDoubleSpinBox()
        self._laser_spin.setRange(LASER_532_V_MIN, LASER_532_V_MAX)
        self._laser_spin.setSingleStep(0.05)
        self._laser_spin.setDecimals(3)
        self._laser_spin.setSuffix(" V")
        self._laser_spin.setValue(LASER_532_V_MIN)
        self._laser_spin.valueChanged.connect(self._on_laser_spin)

        btn_off = QPushButton(f"Apagar ({LASER_532_V_MIN:.1f} V mín)")
        btn_off.setStyleSheet("color: #cc4444;")
        btn_off.clicked.connect(lambda: self._laser_spin.setValue(LASER_532_V_MIN))

        # ── Layout ────────────────────────────────────────────────────────────
        grid.addWidget(self.shutter0button,  0, 0)
        grid.addWidget(self.shutter1button,  1, 0)
        grid.addWidget(self.shutter2button,  2, 0)
        if self.shutter3button is not None:
            grid.addWidget(self.shutter3button, 3, 0)
        grid.addWidget(self.powerbutton,     1, 1)
        grid.addWidget(self.notch532button,  2, 1)

    def closeEvent(self, event):
        self.closeSignal.emit()
        super().closeEvent(event)

    def make_connection(self, backend: Backend):
        backend.make_connection(self)


# ══════════════════════════════════════════════════════════════════════════════
class Backend(QObject):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @pyqtSlot(bool)
    def shutter0(self, state: bool):
        if state:
            open_shutter(SHUTTERS[0])
        else:
            close_shutter(SHUTTERS[0])

    @pyqtSlot(bool)
    def shutter1(self, state: bool):
        if state:
            open_shutter(SHUTTERS[1])
        else:
            close_shutter(SHUTTERS[1])

    @pyqtSlot(bool)
    def shutter2(self, state: bool):
        if state:
            open_shutter(SHUTTERS[2])
        else:
            close_shutter(SHUTTERS[2])

    @pyqtSlot(bool)
    def shutter3(self, state: bool):
        if len(SHUTTERS) > 3:
            if state:
                open_shutter(SHUTTERS[3])
            else:
                close_shutter(SHUTTERS[3])

    @pyqtSlot(bool)
    def power_change(self, high: bool):
        down_flipper() if high else up_flipper()

    @pyqtSlot(bool)
    def notch532_change(self, down: bool):
        flipper_notch532("down" if down else "up")

    @pyqtSlot(float)
    def set_laser532(self, v: float):
        set_laser532_voltage(v)

    @pyqtSlot()
    def close(self):
        flipper_notch532("down")
        close_all_tasks()

    def make_connection(self, frontend: Frontend):
        frontend.shutter0_signal.connect(self.shutter0)
        frontend.shutter1_signal.connect(self.shutter1)
        frontend.shutter2_signal.connect(self.shutter2)
        if hasattr(frontend, 'shutter3_signal'):
            frontend.shutter3_signal.connect(self.shutter3)
        frontend.flipper_signal.connect(self.power_change)
        frontend.flipper_notch532_signal.connect(self.notch532_change)
        frontend.laser532_signal.connect(self.set_laser532)
        frontend.closeSignal.connect(self.close)


# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    gui    = Frontend()
    worker = Backend()
    worker.make_connection(gui)
    thread = QThread()
    worker.moveToThread(thread)
    thread.start()
    gui.show()
    sys.exit(app.exec())
