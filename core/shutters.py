# -*- coding: utf-8 -*-
"""
shutters.py — Control de shutters, flippers y láser 532 nm
PyPrinting — UNSAM Nanofotónica  —  PyQt6

Control MANUAL de obturadores digitales y sincronización bidireccional UI.

La operación manual no tiene plazo (DEC-052): un obturador abierto desde este dock queda abierto hasta que el
operador lo cierre. El watchdog vigila sólo a las rutinas; su plazo se elige en el Control Panel de impresión y en el
panel izquierdo de PySpectrum (`core/ui/routine_watchdog_widget.py`).
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
                            get_watchdog_remaining_time,
                            register_watchdog_callback, unregister_watchdog_callback,
                            register_flipper_callback, unregister_flipper_callback,
                            is_flipper_high_power,
                            register_shutter_fault_callback, unregister_shutter_fault_callback,
                            get_unconfirmed_shutters,
                            operator_close_all, operator_close_shutter, is_close_confirmed,
                            _shutter_signal)
except ImportError:
    from nidaq   import (open_shutter, close_shutter, close_all_shutters, up_flipper, down_flipper,
                         flipper_notch532, set_laser532_voltage, close_all_tasks,
                         get_watchdog_remaining_time,
                         register_watchdog_callback, unregister_watchdog_callback,
                         register_flipper_callback, unregister_flipper_callback,
                         is_flipper_high_power,
                         register_shutter_fault_callback, unregister_shutter_fault_callback,
                         get_unconfirmed_shutters,
                         operator_close_all, operator_close_shutter, is_close_confirmed,
                         _shutter_signal)


# ══════════════════════════════════════════════════════════════════════════════

# "Cerrar todos" no detiene la grilla (gui_design_v2.md §5.2; R4-17 fases 3 y 4c)
CLOSE_ALL_TOOLTIP = ("<b>Cerrar todos los obturadores</b><br>Cierra los cuatro ahora. <b>No detiene la grilla</b>: el "
                     "nodo en curso termina como \"interrumpido\" y el siguiente vuelve a abrir a los 3 s.<br>Para "
                     "detener todo: <b>PARADA DE EMERGENCIA</b> (Ctrl+E / F12). Para detener sólo la grilla: "
                     "<b>Pausa</b> (F2).")

class Frontend(QFrame):

    shutter0_signal          = pyqtSignal(bool)
    shutter1_signal          = pyqtSignal(bool)
    shutter2_signal          = pyqtSignal(bool)
    shutter3_signal          = pyqtSignal(bool)
    flipper_signal           = pyqtSignal(bool)
    flipper_notch532_signal  = pyqtSignal(bool)
    laser532_signal          = pyqtSignal(float)
    watchdog_triggered_signal = pyqtSignal()
    flipper_hardware_signal  = pyqtSignal(bool)
    shutter_fault_signal     = pyqtSignal(str, str, bool)   # (obturador, detalle, confirmado)
    closeSignal              = pyqtSignal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._unconfirmed: set[str] = set()
        self._setup_gui()
        self._setup_hardware_bridges()

    def _setup_hardware_bridges(self):
        self.watchdog_triggered_signal.connect(self._on_watchdog_triggered)
        register_watchdog_callback(self._watchdog_callback_bridge)

        # DEC-036: el callback llega desde el hilo del watchdog o desde el que accionó el
        # obturador; la señal lo trae al hilo de la GUI.
        self.shutter_fault_signal.connect(self._on_shutter_fault)
        register_shutter_fault_callback(self._shutter_fault_bridge)

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

    def _shutter_fault_bridge(self, name: str, detail: str, confirmed: bool):
        try:
            self.shutter_fault_signal.emit(name, detail, confirmed)
        except Exception:
            pass

    def _shutter_button(self, name: str):
        buttons = (self.shutter0button, self.shutter1button, self.shutter2button, self.shutter3button)
        idx = SHUTTERS.index(name) if name in SHUTTERS else -1
        return buttons[idx] if 0 <= idx < len(buttons) else None

    @staticmethod
    def _set_checked_silently(btn, checked: bool):
        if btn is not None and btn.isChecked() != checked:
            btn.blockSignals(True)
            btn.setChecked(checked)
            btn.blockSignals(False)

    @pyqtSlot(str, str, bool)
    def _on_shutter_fault(self, name: str, detail: str, confirmed: bool):
        """Refleja el estado REAL del obturador (DEC-036), no el que se pidió con el clic.

        Un cierre sin confirmar se muestra marcado (tratado como abierto), en rojo, con un
        banner que persiste hasta que el cierre se confirma. Una apertura fallida o bloqueada
        desmarca la casilla y explica por qué."""
        btn = self._shutter_button(name)
        if confirmed:
            self._unconfirmed.discard(name)
            # "estado confirmado (abierto)": una línea abierta a propósito que una escritura fallida dejó sin
            # confirmar (R4-17 fase 1) sigue abierta; sólo vuelve el estilo normal.
            if "abierto" not in detail:
                self._set_checked_silently(btn, False)
            if btn is not None:
                btn.setStyleSheet(self._default_shutter_styles.get(name, ""))
            self._last_open_failure = ""
        elif "cierre" in detail or "sin confirmar" in detail:
            self._unconfirmed.add(name)
            self._set_checked_silently(btn, True)
            if btn is not None:
                btn.setStyleSheet("color: #f38ba8; font-weight: bold; background-color: rgba(243, 139, 168, 0.18);")
        else:
            self._set_checked_silently(btn, False)
            self._last_open_failure = f"No se abrió {name}: {detail}"
        self._refresh_fault_banner()
        self._update_security_status()

    def _refresh_fault_banner(self):
        pending = [n for n in SHUTTERS if n in self._unconfirmed]
        if pending:
            self.lbl_fault_banner.setText(
                "⚠️ CIERRE SIN CONFIRMAR: " + ", ".join(pending)
                + " — se tratan como ABIERTOS; se sigue reintentando el cierre.")
            self.lbl_fault_banner.setStyleSheet(
                "color: #11111b; background-color: #f38ba8; font-weight: bold; font-size: 8pt; "
                "padding: 3px; border-radius: 3px;")
            self.lbl_fault_banner.setVisible(True)
        elif getattr(self, "_last_open_failure", ""):
            self.lbl_fault_banner.setText("⚠️ " + self._last_open_failure)
            self.lbl_fault_banner.setStyleSheet(
                "color: #11111b; background-color: #fab387; font-weight: bold; font-size: 8pt; "
                "padding: 3px; border-radius: 3px;")
            self.lbl_fault_banner.setVisible(True)
        else:
            self.lbl_fault_banner.setVisible(False)

    @pyqtSlot()
    def _on_watchdog_triggered(self):
        """Sincroniza la UI cuando el watchdog de una rutina fuerza el cierre de todos los obturadores (también los
        abiertos a mano, DEC-052). Un obturador cuyo cierre no se confirmó sigue marcado (DEC-036)."""
        for name, btn in zip(SHUTTERS, (self.shutter0button, self.shutter1button,
                                        self.shutter2button, self.shutter3button)):
            if name in self._unconfirmed:
                continue
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

    def _refresh_close_all_label(self):
        try:
            from core.emergency_stop import get_emergency_coordinator
            running = get_emergency_coordinator().any_routine_running()
        except Exception:
            running = False
        text = "Cerrar todos · la grilla sigue" if running else "Cerrar Todos"
        if self.btn_close_all.text() != text:
            self.btn_close_all.setText(text)

    def _close_all_shutters_clicked(self):
        """Cierra los cuatro y desmarca sólo si la placa lo confirmó (R4-17 fase 1). Antes desmarcaba primero e
        ignoraba el resultado: un cierre fallido quedaba como si nada. Si falla, los avisos de DEC-036 dejan cada
        obturador marcado en rojo con el banner, y el hilo del watchdog reintenta el cierre.

        Es un corte del operador (R4-17 fase 3): con una grilla corriendo, el nodo en exposición queda
        "interrumpido" y las aperturas se retienen `OPERATOR_HOLD_S`; la grilla sigue después."""
        from core.emergency_stop import get_emergency_coordinator
        epoch = get_emergency_coordinator().operator_close_all("Cerrar todos")
        if is_close_confirmed(epoch):
            for btn in (self.shutter0button, self.shutter1button, self.shutter2button, self.shutter3button):
                if btn is not None and btn.isChecked():
                    btn.blockSignals(True)
                    btn.setChecked(False)
                    btn.blockSignals(False)
        self._update_security_status()

    MANUAL_STATUS_TEXT = "Operación manual: sin auto-cierre"
    MANUAL_OPEN_TEXT = "Láser abierto a mano: queda abierto hasta que lo cierres"

    def _update_security_status(self):
        """La operación manual no tiene plazo (DEC-052): la etiqueta sólo recuerda que un láser abierto acá sigue
        abierto. El plazo de las rutinas se muestra en el Control Panel de impresión y en PySpectrum."""
        any_open = any(
            btn.isChecked() for btn in (self.shutter0button, self.shutter1button, self.shutter2button, self.shutter3button)
            if btn is not None
        )
        if any_open:
            text, style = self.MANUAL_OPEN_TEXT, "color: #fab387; font-weight: bold; font-size: 8pt;"
        else:
            text, style = self.MANUAL_STATUS_TEXT, "color: #a6adc8; font-size: 8pt;"
        if self.lbl_security_status.text() != text:
            self.lbl_security_status.setText(text)
        self.lbl_security_status.setStyleSheet(style)

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
        self.btn_close_all.setToolTip(CLOSE_ALL_TOOLTIP)
        self.btn_close_all.clicked.connect(self._close_all_shutters_clicked)
        # La parada de emergencia al lado de "Cerrar todos": la vecindad enseña la diferencia (gui_design_v2.md
        # §5.1-§5.2). Con una rutina corriendo, el rótulo dice que la grilla sigue (R4-17 fase 4c).
        from core.ui.emergency_widgets import EmergencyStopButton
        self.btn_estop = EmergencyStopButton(source="dock de obturadores", compact=True)
        self._close_all_label_timer = QTimer(self)
        self._close_all_label_timer.setInterval(500)
        self._close_all_label_timer.timeout.connect(self._refresh_close_all_label)
        self._close_all_label_timer.start()

        # ── Layout Superior ───────────────────────────────────────────────────
        grid.addWidget(self.shutter0button,  0, 0)
        grid.addWidget(self.shutter1button,  1, 0)
        grid.addWidget(self.shutter2button,  2, 0)
        if self.shutter3button is not None:
            grid.addWidget(self.shutter3button, 3, 0)
        grid.addWidget(self.powerbutton,     0, 1)
        grid.addWidget(self.notch532button,  1, 1)
        grid.addWidget(self.btn_close_all,   2, 1)
        grid.addWidget(self.btn_estop,       3, 1)

        main_layout.addLayout(grid)

        # ── Seguridad (DEC-052: la operación manual no tiene plazo; el watchdog es sólo de las rutinas) ──
        sec_box = QGroupBox("Seguridad")
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

        self.lbl_security_status = QLabel(self.MANUAL_STATUS_TEXT)
        self.lbl_security_status.setStyleSheet("color: #a6adc8; font-size: 8pt;")
        self.lbl_security_status.setToolTip(
            "<b>Operación manual</b><br>Un obturador abierto desde este dock queda abierto hasta que lo cierres: "
            "no hay cierre automático por tiempo.<br>El <b>watchdog de rutinas</b> (Control Panel de impresión, "
            "panel izquierdo de PySpectrum) vigila sólo a las rutinas; si una se cuelga con un láser abierto, "
            "cierra todos los obturadores, también los abiertos a mano (DEC-052).")
        sec_layout.addWidget(self.lbl_security_status)

        # DEC-036: banner persistente de obturadores sin confirmar / aperturas rechazadas.
        self.lbl_fault_banner = QLabel("")
        self.lbl_fault_banner.setWordWrap(True)
        self.lbl_fault_banner.setVisible(False)
        sec_layout.addWidget(self.lbl_fault_banner)
        self._default_shutter_styles = {
            name: btn.styleSheet()
            for name, btn in zip(SHUTTERS, (self.shutter0button, self.shutter1button,
                                            self.shutter2button, self.shutter3button))
            if btn is not None
        }
        self._last_open_failure = ""

        main_layout.addWidget(sec_box)

    def set_actuators_enabled(self, enabled: bool):
        """Habilita/deshabilita la apertura manual de obturadores/flipper/notch (Fase 5,
        subyugación Master-Slave, DEC-019). btn_close_all queda SIEMPRE habilitado por
        seguridad — es una vía de escape manual válida incluso subyugado a un master
        externo (PySpectrum 3.0), nunca debe bloquearse."""
        widgets = [self.shutter0button, self.shutter1button, self.shutter2button, self.powerbutton, self.notch532button]
        if self.shutter3button is not None:
            widgets.append(self.shutter3button)
        for w in widgets:
            w.setEnabled(enabled)

    def closeEvent(self, event):
        if hasattr(self, '_status_timer') and self._status_timer.isActive():
            self._status_timer.stop()
        unregister_watchdog_callback(self._watchdog_callback_bridge)
        unregister_flipper_callback(self._flipper_hardware_bridge)
        unregister_shutter_fault_callback(self._shutter_fault_bridge)
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

    # Los botones del dock son operación manual (DEC-052): abrir no arma ningún plazo.
    # Cerrar uno es un corte del operador, igual que "Cerrar todos" (R4-17 fase 3; BANCO-67):
    # el nodo de una grilla en exposición queda "interrumpido" y no "timeout".
    @pyqtSlot(bool)
    def shutter0(self, state: bool):
        if state:
            open_shutter(SHUTTERS[0], )
        else:
            operator_close_shutter(SHUTTERS[0])

    @pyqtSlot(bool)
    def shutter1(self, state: bool):
        if state:
            open_shutter(SHUTTERS[1], )
        else:
            operator_close_shutter(SHUTTERS[1])

    @pyqtSlot(bool)
    def shutter2(self, state: bool):
        if state:
            open_shutter(SHUTTERS[2], )
        else:
            operator_close_shutter(SHUTTERS[2])

    @pyqtSlot(bool)
    def shutter3(self, state: bool):
        if len(SHUTTERS) > 3:
            if state:
                open_shutter(SHUTTERS[3], )
            else:
                operator_close_shutter(SHUTTERS[3])

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
