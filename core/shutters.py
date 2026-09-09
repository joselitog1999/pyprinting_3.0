# -*- coding: utf-8 -*-
"""
shutters.py — Control de shutters, flippers y láser 532 nm
PyPrinting — UNSAM Nanofotónica  —  PyQt6

Control de obturadores digitales con fail-safe watchdog,
selector de auto-cierre / modo alineación continua y sincronización bidireccional UI.
"""
from __future__ import annotations

import time
from PyQt6.QtCore    import Qt, QObject, QThread, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (QApplication, QFrame, QWidget, QGridLayout,
                              QHBoxLayout, QVBoxLayout, QLabel, QCheckBox,
                              QDoubleSpinBox, QSlider, QPushButton, QComboBox,
                              QGroupBox)

import sys
if __name__ == "core.shutters":
    sys.modules["shutters"] = sys.modules[__name__]
elif __name__ == "shutters":
    sys.modules["core.shutters"] = sys.modules[__name__]

from config  import SHUTTERS, SHUTTER_POLARITY, LASER_532_V_MIN, LASER_532_V_MAX
try:
    from core.nidaq import (open_shutter, close_shutter, close_all_shutters, up_flipper, down_flipper,
                            flipper_notch532, set_laser532_voltage, close_all_tasks,
                            heartbeat_shutter, get_watchdog_remaining_time,
                            register_watchdog_callback, unregister_watchdog_callback,
                            register_flipper_callback, unregister_flipper_callback,
                            is_flipper_high_power,
                            _shutter_signal)
except ImportError:
    from nidaq   import (open_shutter, close_shutter, close_all_shutters, up_flipper, down_flipper,
                         flipper_notch532, set_laser532_voltage, close_all_tasks,
                         heartbeat_shutter, get_watchdog_remaining_time,
                         register_watchdog_callback, unregister_watchdog_callback,
                         register_flipper_callback, unregister_flipper_callback,
                         is_flipper_high_power,
                         _shutter_signal)


# ══════════════════════════════════════════════════════════════════════════════
class Frontend(QFrame):

    shutter0_signal          = pyqtSignal(bool)
    shutter1_signal          = pyqtSignal(bool)
    shutter2_signal          = pyqtSignal(bool)
    shutter3_signal          = pyqtSignal(bool)
    flipper_signal           = pyqtSignal(bool)
    flipper_notch532_signal  = pyqtSignal(bool)
    laser532_signal          = pyqtSignal(float)
    autoclose_timeout_signal = pyqtSignal(object)
    watchdog_triggered_signal = pyqtSignal()
    flipper_hardware_signal  = pyqtSignal(bool)
    closeSignal              = pyqtSignal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._setup_gui()
        self._setup_hardware_bridges()

    def _setup_hardware_bridges(self):
        self.watchdog_triggered_signal.connect(self._on_watchdog_triggered)
        register_watchdog_callback(self._watchdog_callback_bridge)

        self.flipper_hardware_signal.connect(self.update_power_ui)
        register_flipper_callback(self._flipper_hardware_bridge)

        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._update_security_status)
        self._status_timer.start(1000)

    _setup_watchdog_bridge = _setup_hardware_bridges

    def _watchdog_callback_bridge(self):
        try:
            self.watchdog_triggered_signal.emit()
        except Exception:
            pass

    def _flipper_hardware_bridge(self, high: bool):
        try:
            self.flipper_hardware_signal.emit(high)
        except Exception:
            pass

    @pyqtSlot()
    def _on_watchdog_triggered(self):
        """Sincroniza la UI cuando el watchdog de hardware fuerza el cierre de obturadores."""
        for btn in (self.shutter0button, self.shutter1button, self.shutter2button, self.shutter3button):
            if btn is not None and btn.isChecked():
                btn.blockSignals(True)
                btn.setChecked(False)
                btn.blockSignals(False)
        self._update_security_status()

    # ── Handlers de botones y Slots de Actuación ──────────────────────────────

    @pyqtSlot(bool)
    @pyqtSlot()
    def _shutter0_check(self, checked: bool | None = None):
        if checked is None:
            checked = self.shutter0button.isChecked()
        elif self.shutter0button.isChecked() != checked:
            self.shutter0button.blockSignals(True)
            self.shutter0button.setChecked(checked)
            self.shutter0button.blockSignals(False)
        self.shutter0_signal.emit(checked)
        self._update_security_status()

    @pyqtSlot(bool)
    @pyqtSlot()
    def _shutter1_check(self, checked: bool | None = None):
        if checked is None:
            checked = self.shutter1button.isChecked()
        elif self.shutter1button.isChecked() != checked:
            self.shutter1button.blockSignals(True)
            self.shutter1button.setChecked(checked)
            self.shutter1button.blockSignals(False)
        self.shutter1_signal.emit(checked)
        self._update_security_status()

    @pyqtSlot(bool)
    @pyqtSlot()
    def _shutter2_check(self, checked: bool | None = None):
        if checked is None:
            checked = self.shutter2button.isChecked()
        elif self.shutter2button.isChecked() != checked:
            self.shutter2button.blockSignals(True)
            self.shutter2button.setChecked(checked)
            self.shutter2button.blockSignals(False)
        self.shutter2_signal.emit(checked)
        self._update_security_status()

    @pyqtSlot(bool)
    @pyqtSlot()
    def _shutter3_check(self, checked: bool | None = None):
        if hasattr(self, 'shutter3button') and self.shutter3button is not None:
            if checked is None:
                checked = self.shutter3button.isChecked()
            elif self.shutter3button.isChecked() != checked:
                self.shutter3button.blockSignals(True)
                self.shutter3button.setChecked(checked)
                self.shutter3button.blockSignals(False)
            self.shutter3_signal.emit(checked)
            self._update_security_status()

    def _power_clicked(self):
        """Maneja el clic directo del usuario en el checkbox de potencia (Low/High)."""
        checked = self.powerbutton.isChecked()
        self._apply_power_style(checked)
        self.flipper_signal.emit(checked)

    def _apply_power_style(self, high: bool):
        if high:
            self.powerbutton.setText("High\npower")
            self.powerbutton.setStyleSheet("color: rgb(200, 80, 40); font-weight: bold;")
        else:
            self.powerbutton.setText("Low\npower")
            self.powerbutton.setStyleSheet("color: rgb(12, 183, 242); font-weight: bold;")

    @pyqtSlot(bool)
    def update_power_ui(self, high: bool):
        """Actualiza exclusivamente el estado visual, texto y color del checkbox sin re-emitir señal."""
        if self.powerbutton.isChecked() != high:
            self.powerbutton.blockSignals(True)
            self.powerbutton.setChecked(high)
            self.powerbutton.blockSignals(False)
        self._apply_power_style(high)

    @pyqtSlot(bool)
    def set_power(self, high: bool):
        """Slot público para conmutar la potencia vía señal externa o llamada programática."""
        if self.powerbutton.isChecked() != high:
            self.powerbutton.blockSignals(True)
            self.powerbutton.setChecked(high)
            self.powerbutton.blockSignals(False)
        self._apply_power_style(high)
        self.flipper_signal.emit(high)

    set_flipper = set_power

    @pyqtSlot(bool)
    @pyqtSlot()
    def _power_check(self, checked: bool | None = None):
        """Soporta llamadas de slots Qt y señales booleanas externas."""
        if checked is None:
            checked = self.powerbutton.isChecked()
        self.set_power(checked)

    powerbutton_check = _power_check

    @pyqtSlot(bool)
    @pyqtSlot()
    def _notch532_check(self, checked: bool | None = None):
        if checked is None:
            checked = self.notch532button.isChecked()
        else:
            if self.notch532button.isChecked() != checked:
                self.notch532button.blockSignals(True)
                self.notch532button.setChecked(checked)
                self.notch532button.blockSignals(False)

        self.update_notch532_ui(checked)
        self.flipper_notch532_signal.emit(checked)

    @pyqtSlot(bool)
    def update_notch532_ui(self, down: bool):
        if self.notch532button.isChecked() != down:
            self.notch532button.blockSignals(True)
            self.notch532button.setChecked(down)
            self.notch532button.blockSignals(False)
        self.notch532button.setText("Mirror down" if down else "Mirror up")

    @pyqtSlot(bool)
    def set_notch532(self, down: bool):
        self._notch532_check(down)

    def get_selected_timeout(self) -> float | None:
        if not self.chk_autoclose.isChecked():
            return None
        return self.combo_timeout.currentData()

    def _on_security_mode_changed(self):
        to = self.get_selected_timeout()
        self.combo_timeout.setEnabled(self.chk_autoclose.isChecked())
        self.autoclose_timeout_signal.emit(to)
        self._update_security_status()

    def _close_all_shutters_clicked(self):
        for btn in (self.shutter0button, self.shutter1button, self.shutter2button, self.shutter3button):
            if btn is not None and btn.isChecked():
                btn.blockSignals(True)
                btn.setChecked(False)
                btn.blockSignals(False)
        close_all_shutters()
        self._update_security_status()

    def _update_security_status(self):
        to = self.get_selected_timeout()
        any_open = any(
            btn.isChecked() for btn in (self.shutter0button, self.shutter1button, self.shutter2button, self.shutter3button)
            if btn is not None
        )
        if to is None:
            self.lbl_security_status.setText("⚠️ MODO ALINEACIÓN (Sin auto-cierre)")
            self.lbl_security_status.setStyleSheet("color: #fab387; font-weight: bold; font-size: 8pt;")
        elif any_open:
            rem = get_watchdog_remaining_time()
            if rem is not None:
                self.lbl_security_status.setText(f"⏱️ Auto-cierre en: {rem:.0f} s")
            else:
                self.lbl_security_status.setText(f"⏱️ Auto-cierre activo ({int(to)} s)")
            self.lbl_security_status.setStyleSheet("color: #a6e3a1; font-weight: bold; font-size: 8pt;")
        else:
            self.lbl_security_status.setText(f"⏱️ Auto-cierre armado ({int(to)} s)")
            self.lbl_security_status.setStyleSheet("color: #a6adc8; font-size: 8pt;")

    # ── GUI ───────────────────────────────────────────────────────────────────

    def _setup_gui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(6)

        grid = QGridLayout()
        grid.setSpacing(6)

        # ── Shutters ──────────────────────────────────────────────────────────
        self.shutter0button = QCheckBox(SHUTTERS[0])
        self.shutter0button.toggled.connect(self._shutter0_check)
        self.shutter0button.setStyleSheet("color: green; font-weight: bold;")
        self.shutter0button.setToolTip("Abrir/cerrar shutter 532 nm (verde)")

        self.shutter1button = QCheckBox(SHUTTERS[1])
        self.shutter1button.toggled.connect(self._shutter1_check)
        self.shutter1button.setStyleSheet("color: red; font-weight: bold;")
        self.shutter1button.setToolTip("Abrir/cerrar shutter 637 nm (rojo)")

        self.shutter2button = QCheckBox(SHUTTERS[2])
        self.shutter2button.toggled.connect(self._shutter2_check)
        self.shutter2button.setStyleSheet("color: #d4ac0d; font-weight: bold;")
        self.shutter2button.setToolTip("Abrir/cerrar shutter 592 nm (amarillo)")

        if len(SHUTTERS) > 3:
            self.shutter3button = QCheckBox(SHUTTERS[3])
            self.shutter3button.toggled.connect(self._shutter3_check)
            self.shutter3button.setStyleSheet("color: #ad1457; font-weight: bold;")
            self.shutter3button.setToolTip("Abrir/cerrar shutter 808 nm (infrarrojo)")
        else:
            self.shutter3button = None

        # ── Flippers ─────────────────────────────────────────────────────────
        self.powerbutton = QCheckBox("Low\npower")
        self.powerbutton.clicked.connect(self._power_clicked)
        self.powerbutton.setStyleSheet("color: rgb(12, 183, 242); font-weight: bold;")
        self.powerbutton.setToolTip("Conmutar potencia del láser (Low power / High power)")

        self.notch532button = QCheckBox("Mirror up")
        self.notch532button.toggled.connect(self._notch532_check)

        self.btn_close_all = QPushButton("Cerrar Todos")
        self.btn_close_all.setStyleSheet("color: #f38ba8; font-weight: bold; font-size: 8pt; padding: 3px;")
        self.btn_close_all.setToolTip("Cierra inmediatamente todos los shutters ópticos")
        self.btn_close_all.clicked.connect(self._close_all_shutters_clicked)

        # ── Layout Superior ───────────────────────────────────────────────────
        grid.addWidget(self.shutter0button,  0, 0)
        grid.addWidget(self.shutter1button,  1, 0)
        grid.addWidget(self.shutter2button,  2, 0)
        if self.shutter3button is not None:
            grid.addWidget(self.shutter3button, 3, 0)
        grid.addWidget(self.powerbutton,     0, 1)
        grid.addWidget(self.notch532button,  1, 1)
        grid.addWidget(self.btn_close_all,   2, 1)

        main_layout.addLayout(grid)

        # ── Control de Seguridad / Watchdog / Modo Alineación (Opción 3) ───────
        sec_box = QGroupBox("Seguridad & Watchdog")
        sec_box.setStyleSheet("""
            QGroupBox {
                font-size: 8.5pt;
                font-weight: bold;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 5px;
                margin-top: 6px;
                padding-top: 8px;
                background-color: rgba(30, 30, 46, 0.6);
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 3px;
            }
        """)
        sec_layout = QVBoxLayout(sec_box)
        sec_layout.setContentsMargins(6, 6, 6, 6)
        sec_layout.setSpacing(4)

        row_ctrl = QHBoxLayout()
        self.chk_autoclose = QCheckBox("Auto-cierre")
        self.chk_autoclose.setChecked(True)
        self.chk_autoclose.setStyleSheet("color: #cdd6f4; font-size: 8.5pt;")
        self.chk_autoclose.setToolTip("Cierra los shutters automáticamente tras el tiempo seleccionado si no hay actividad.")
        self.chk_autoclose.toggled.connect(self._on_security_mode_changed)

        self.combo_timeout = QComboBox()
        self.combo_timeout.addItem("30 s (Predeterminado)", 30.0)
        self.combo_timeout.addItem("60 s (1 min)", 60.0)
        self.combo_timeout.addItem("300 s (5 min)", 300.0)
        self.combo_timeout.addItem("600 s (10 min)", 600.0)
        self.combo_timeout.addItem("Sin límite (Alineación)", None)
        self.combo_timeout.setStyleSheet("""
            QComboBox {
                background-color: #1e1e2e;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 3px;
                padding: 2px 6px;
                font-size: 8.5pt;
            }
        """)
        self.combo_timeout.currentIndexChanged.connect(self._on_security_mode_changed)

        row_ctrl.addWidget(self.chk_autoclose)
        row_ctrl.addWidget(self.combo_timeout)
        sec_layout.addLayout(row_ctrl)

        self.lbl_security_status = QLabel("⏱️ Auto-cierre armado (30 s)")
        self.lbl_security_status.setStyleSheet("color: #a6adc8; font-size: 8pt;")
        sec_layout.addWidget(self.lbl_security_status)

        main_layout.addWidget(sec_box)

    def closeEvent(self, event):
        if hasattr(self, '_status_timer') and self._status_timer.isActive():
            self._status_timer.stop()
        unregister_watchdog_callback(self._watchdog_callback_bridge)
        unregister_flipper_callback(self._flipper_hardware_bridge)
        self.closeSignal.emit()
        super().closeEvent(event)

    def make_connection(self, backend: Backend):
        backend.make_connection(self)


# ══════════════════════════════════════════════════════════════════════════════
class Backend(QObject):

    flipper_state_signal          = pyqtSignal(bool)
    flipper_notch532_state_signal = pyqtSignal(bool)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.current_timeout: float | None = 30.0

    @pyqtSlot(object)
    def set_autoclose_timeout(self, timeout_val: float | None):
        self.current_timeout = timeout_val
        # Si hay obturadores abiertos en hardware, actualizar el watchdog inmediatamente
        try:
            any_open = any(s == SHUTTER_POLARITY[sh] for s, sh in zip(_shutter_signal, SHUTTERS))
            if any_open:
                heartbeat_shutter(timeout_val)
        except Exception:
            pass

    @pyqtSlot(bool)
    def shutter0(self, state: bool):
        if state:
            open_shutter(SHUTTERS[0], timeout_s=self.current_timeout)
        else:
            close_shutter(SHUTTERS[0])

    @pyqtSlot(bool)
    def shutter1(self, state: bool):
        if state:
            open_shutter(SHUTTERS[1], timeout_s=self.current_timeout)
        else:
            close_shutter(SHUTTERS[1])

    @pyqtSlot(bool)
    def shutter2(self, state: bool):
        if state:
            open_shutter(SHUTTERS[2], timeout_s=self.current_timeout)
        else:
            close_shutter(SHUTTERS[2])

    @pyqtSlot(bool)
    def shutter3(self, state: bool):
        if len(SHUTTERS) > 3:
            if state:
                open_shutter(SHUTTERS[3], timeout_s=self.current_timeout)
            else:
                close_shutter(SHUTTERS[3])

    @pyqtSlot(bool)
    def power_change(self, high: bool):
        down_flipper() if high else up_flipper()
        self.flipper_state_signal.emit(high)

    @pyqtSlot(bool)
    def notch532_change(self, down: bool):
        flipper_notch532("down" if down else "up")
        self.flipper_notch532_state_signal.emit(down)

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
        frontend.autoclose_timeout_signal.connect(self.set_autoclose_timeout)
        frontend.closeSignal.connect(self.close)

        # Sincronización Backend -> Frontend
        self.flipper_state_signal.connect(frontend.update_power_ui)
        self.flipper_notch532_state_signal.connect(frontend.update_notch532_ui)


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
