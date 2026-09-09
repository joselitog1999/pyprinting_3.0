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

from PyQt6.QtCore    import Qt, QObject, QThread, pyqtSignal, pyqtSlot, QEvent
from PyQt6.QtWidgets import (QApplication, QFrame, QWidget, QGridLayout,
                              QHBoxLayout, QVBoxLayout, QLabel, QLineEdit, QPushButton,
                              QComboBox, QTextEdit, QPlainTextEdit)
from PyQt6.QtGui     import QFont, QKeyEvent
from pyqtgraph.dockarea import DockArea, Dock

from config import (pi, PI_AXES,
                    DEFAULT_NANO_STEP_XY, DEFAULT_NANO_STEP_Z,
                    DEFAULT_NANO_GOTO_X, DEFAULT_NANO_GOTO_Y, DEFAULT_NANO_GOTO_Z,
                    REGIME_LEGACY, REGIME_LASER_REF, REGIME_SAMPLE_REF, DEFAULT_COORDINATE_REGIME)


# ══════════════════════════════════════════════════════════════════════════════
_ACTIVE_FRONTENDS: list[Frontend] = []
_REGIME_LISTENERS: list = []

COORDINATE_NOMENCLATURE = {
    REGIME_LEGACY: {
        "axis1_name": "x",
        "axis1_display": "<b>x =</b>",
        "axis1_goto": "X [µm]",
        "axis1_tooltip": "Legacy: Eje físico 1 de platina PI (desplazamiento vertical en cámara)",
        "axis2_name": "y",
        "axis2_display": "<b>y =</b>",
        "axis2_goto": "Y [µm]",
        "axis2_tooltip": "Legacy: Eje físico 2 de platina PI (desplazamiento horizontal en cámara)",
        "axis3_name": "z",
        "axis3_display": "<b>z =</b>",
        "axis3_goto": "Z [µm]",
        "axis3_tooltip": "Eje axial Z de platina PI (enfoque)",
        "step_xy_label": "step x/y [µm]",
        # Confocal
        "confocal_psf_modes": ["x/y", "x/z", "y/x", "y/z"],
        "confocal_range_1": "Range x (µm)",
        "confocal_range_2": "Range y (µm)",
        "confocal_pixels_1": "Pixels x",
        "confocal_pixels_2": "Pixels y",
        "confocal_plot_left": "X",
        "confocal_plot_bottom": "Y",
        # Printing
        "print_ref_1": "X ref:",
        "print_ref_2": "Y ref:",
        "print_dist_np": "Dist NP (µm)",
        "print_dist_col": "Dist col (µm)",
        "print_shift_1": "Shift X (µm)",
        "print_shift_2": "Shift Y (µm)",
        "print_dimer_1": "dx (µm)",
        "print_dimer_2": "dy (µm)",
        "grid_plot_left": "Y (µm)",
        "grid_plot_bottom": "X (µm)",
        # Grid Generator 2D
        "grid_gen_off_x": "Offset X (µm):",
        "grid_gen_off_y": "Offset Y (µm):",
        "grid_gen_start_x": "startX Red (µm):",
        "grid_gen_start_y": "startY Red (µm):",
        "grid_gen_delta_x": "Offset Δx (µm):",
        "grid_gen_delta_y": "Offset Δy (µm):",
        "grid_gen_p0_x": "P0 X (µm):",
        "grid_gen_p0_y": "P0 Y (µm):",
        "grid_gen_dim_lx": "Ancho Lx (µm):",
        "grid_gen_dim_ly": "Alto Ly (µm):",
        "grid_gen_cells_nx": "Celdas Nx:",
        "grid_gen_cells_ny": "Celdas Ny:",
    },
    REGIME_LASER_REF: {
        "axis1_name": "Y (Vert)",
        "axis1_display": "<b>Y (Vert) =</b>",
        "axis1_goto": "Y (Vert) [µm]",
        "axis1_tooltip": "Laser Ref: Eje vertical del spot láser en cámara (Eje físico 1 de platina PI)",
        "axis2_name": "X (Horiz)",
        "axis2_display": "<b>X (Horiz) =</b>",
        "axis2_goto": "X (Horiz) [µm]",
        "axis2_tooltip": "Laser Ref: Eje horizontal del spot láser en cámara (Eje físico 2 de platina PI)",
        "axis3_name": "Z",
        "axis3_display": "<b>Z =</b>",
        "axis3_goto": "Z [µm]",
        "axis3_tooltip": "Eje axial Z de platina PI (enfoque)",
        "step_xy_label": "step laser [µm]",
        # Confocal
        "confocal_psf_modes": ["Y/X (Vert/Horiz)", "Y/Z (Vert/Z)", "X/Y (Horiz/Vert)", "X/Z (Horiz/Z)"],
        "confocal_range_1": "Range Y (Vert) [µm]",
        "confocal_range_2": "Range X (Horiz) [µm]",
        "confocal_pixels_1": "Pixels Y (Vert)",
        "confocal_pixels_2": "Pixels X (Horiz)",
        "confocal_plot_left": "Y (Vert)",
        "confocal_plot_bottom": "X (Horiz)",
        # Printing
        "print_ref_1": "Y ref (Vert):",
        "print_ref_2": "X ref (Horiz):",
        "print_dist_np": "Paso Y (Col) [µm]",
        "print_dist_col": "Dist X (Cols) [µm]",
        "print_shift_1": "Shift Y (Vert) [µm]",
        "print_shift_2": "Shift X (Horiz) [µm]",
        "print_dimer_1": "dy (Vert) [µm]",
        "print_dimer_2": "dx (Horiz) [µm]",
        "grid_plot_left": "Y (Vert) [µm]",
        "grid_plot_bottom": "X (Horiz) [µm]",
        # Grid Generator 2D
        "grid_gen_off_x": "Offset X (Horiz) [µm]:",
        "grid_gen_off_y": "Offset Y (Vert) [µm]:",
        "grid_gen_start_x": "startX (Horiz) [µm]:",
        "grid_gen_start_y": "startY (Vert) [µm]:",
        "grid_gen_delta_x": "Offset Δx (Horiz) [µm]:",
        "grid_gen_delta_y": "Offset Δy (Vert) [µm]:",
        "grid_gen_p0_x": "P0 X (Horiz) [µm]:",
        "grid_gen_p0_y": "P0 Y (Vert) [µm]:",
        "grid_gen_dim_lx": "Ancho Lx (Horiz) [µm]:",
        "grid_gen_dim_ly": "Alto Ly (Vert) [µm]:",
        "grid_gen_cells_nx": "Celdas Nx (Horiz):",
        "grid_gen_cells_ny": "Celdas Ny (Vert):",
    },
    REGIME_SAMPLE_REF: {
        "axis1_name": "Y (Muestra)",
        "axis1_display": "<b>Y (Muestra) =</b>",
        "axis1_goto": "Y (Muestra) [µm]",
        "axis1_tooltip": "Sample Ref: Eje vertical de objetos en muestra (Eje físico 1 de platina PI)",
        "axis2_name": "X (Muestra)",
        "axis2_display": "<b>X (Muestra) =</b>",
        "axis2_goto": "X (Muestra) [µm]",
        "axis2_tooltip": "Sample Ref: Eje horizontal de objetos en muestra (Eje físico 2 de platina PI)",
        "axis3_name": "Z",
        "axis3_display": "<b>Z =</b>",
        "axis3_goto": "Z [µm]",
        "axis3_tooltip": "Eje axial Z de platina PI (enfoque)",
        "step_xy_label": "step sample [µm]",
        # Confocal
        "confocal_psf_modes": ["Y/X (Muestra)", "Y/Z (Muestra)", "X/Y (Muestra)", "X/Z (Muestra)"],
        "confocal_range_1": "Range Y (Muestra) [µm]",
        "confocal_range_2": "Range X (Muestra) [µm]",
        "confocal_pixels_1": "Pixels Y",
        "confocal_pixels_2": "Pixels X",
        "confocal_plot_left": "Y (Muestra)",
        "confocal_plot_bottom": "X (Muestra)",
        # Printing
        "print_ref_1": "Y ref (Muestra):",
        "print_ref_2": "X ref (Muestra):",
        "print_dist_np": "Paso Y (Col) [µm]",
        "print_dist_col": "Dist X (Cols) [µm]",
        "print_shift_1": "Shift Y [µm]",
        "print_shift_2": "Shift X [µm]",
        "print_dimer_1": "dy [µm]",
        "print_dimer_2": "dx [µm]",
        "grid_plot_left": "Y (Muestra) [µm]",
        "grid_plot_bottom": "X (Muestra) [µm]",
        # Grid Generator 2D
        "grid_gen_off_x": "Offset X (Muestra) [µm]:",
        "grid_gen_off_y": "Offset Y (Muestra) [µm]:",
        "grid_gen_start_x": "startX (Muestra) [µm]:",
        "grid_gen_start_y": "startY (Muestra) [µm]:",
        "grid_gen_delta_x": "Offset Δx (Muestra) [µm]:",
        "grid_gen_delta_y": "Offset Δy (Muestra) [µm]:",
        "grid_gen_p0_x": "P0 X (Muestra) [µm]:",
        "grid_gen_p0_y": "P0 Y (Muestra) [µm]:",
        "grid_gen_dim_lx": "Ancho Lx (Muestra) [µm]:",
        "grid_gen_dim_ly": "Alto Ly (Muestra) [µm]:",
        "grid_gen_cells_nx": "Celdas Nx (Muestra):",
        "grid_gen_cells_ny": "Celdas Ny (Muestra):",
    }
}


def register_regime_listener(callback):
    """Registra una función callback(regime: str) que se invocará al cambiar el régimen global."""
    if callback not in _REGIME_LISTENERS:
        _REGIME_LISTENERS.append(callback)


def unregister_regime_listener(callback):
    """Desregistra una función callback de régimen."""
    if callback in _REGIME_LISTENERS:
        _REGIME_LISTENERS.remove(callback)


def set_global_coordinate_regime(regime: str):
    """Sincroniza el régimen de coordenadas en todas las instancias activas y módulos suscritos."""
    if regime not in (REGIME_LEGACY, REGIME_LASER_REF, REGIME_SAMPLE_REF):
        return
    for fe in list(_ACTIVE_FRONTENDS):
        try:
            if fe.current_regime != regime:
                fe.set_regime(regime)
        except Exception:
            pass
    for cb in list(_REGIME_LISTENERS):
        try:
            cb(regime)
        except Exception:
            pass


class Frontend(QFrame):

    read_pos_button_signal = pyqtSignal()
    move_signal            = pyqtSignal(str, float)
    go_to_pos_signal       = pyqtSignal(list)
    set_reference_signal   = pyqtSignal()
    reconnect_signal       = pyqtSignal()
    regime_changed_signal  = pyqtSignal(str)

    DIRECTION_MAP = {
        REGIME_LEGACY: {
            "right": ("x",  1.0),
            "left":  ("x", -1.0),
            "up":    ("y",  1.0),
            "down":  ("y", -1.0),
        },
        REGIME_LASER_REF: {
            "right": ("y",  1.0),
            "left":  ("y", -1.0),
            "up":    ("x", -1.0),
            "down":  ("x",  1.0),
        },
        REGIME_SAMPLE_REF: {
            "right": ("y", -1.0),
            "left":  ("y",  1.0),
            "up":    ("x",  1.0),
            "down":  ("x", -1.0),
        },
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.current_regime = DEFAULT_COORDINATE_REGIME
        if self not in _ACTIVE_FRONTENDS:
            _ACTIVE_FRONTENDS.append(self)
        self._setup_gui()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.installEventFilter(self)
        self.set_regime(self.current_regime)

    # ── Slots de actualización de UI ──────────────────────────────────────────

    @pyqtSlot(bool, str)
    def update_connection_status(self, is_physical: bool, status_text: str):
        if is_physical:
            self.conn_status_label.setText(f"🟢 {status_text}")
            self.conn_status_label.setStyleSheet(
                "color: #a6e3a1; background-color: #181825; border: 1px solid #a6e3a1; "
                "border-radius: 4px; padding: 2px 8px; font-weight: bold; font-size: 8pt;"
            )
            self.conn_status_label.setToolTip("Platina física conectada y calibrada.")
        else:
            self.conn_status_label.setText(f"🟡 {status_text}")
            self.conn_status_label.setStyleSheet(
                "color: #f9e2af; background-color: #181825; border: 1px solid #f9e2af; "
                "border-radius: 4px; padding: 2px 8px; font-weight: bold; font-size: 8pt;"
            )
            self.conn_status_label.setToolTip("Modo Virtual: sin movimiento físico real. Pulse 'Reconectar' para reintentar.")

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

    # ── Acciones de botones y movimiento ──────────────────────────────────────

    def get_read_pos(self):
        self.read_pos_button_signal.emit()

    def _step(self):
        try:
            return float(self.StepEdit.text())
        except ValueError:
            return DEFAULT_NANO_STEP_XY

    def _zstep(self):
        try:
            return float(self.zStepEdit.text())
        except ValueError:
            return DEFAULT_NANO_STEP_Z

    def move_direction(self, direction: str, multiplier: float = 1.0):
        """Despacha movimiento en el eje físico y signo según el régimen de coordenadas activo."""
        mapping = self.DIRECTION_MAP.get(self.current_regime, self.DIRECTION_MAP[REGIME_LEGACY])
        if direction not in mapping:
            return
        axis, sign = mapping[direction]
        dist = sign * multiplier * self._step()
        self.move_signal.emit(axis, dist)

    def xUp(self):    self.move_direction("right", 1.0)
    def xUp2(self):   self.move_direction("right", 10.0)
    def xDown(self):  self.move_direction("left", 1.0)
    def xDown2(self): self.move_direction("left", 10.0)
    def yUp(self):    self.move_direction("up", 1.0)
    def yUp2(self):   self.move_direction("up", 10.0)
    def yDown(self):  self.move_direction("down", 1.0)
    def yDown2(self): self.move_direction("down", 10.0)
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

    # ── Gestión de Régimen de Coordenadas ─────────────────────────────────────

    @pyqtSlot(int)
    def _on_regime_changed(self, index: int):
        regime = self.cmb_regime.currentData()
        if regime:
            self.set_regime(regime)
            set_global_coordinate_regime(regime)

    def closeEvent(self, event):
        if self in _ACTIVE_FRONTENDS:
            _ACTIVE_FRONTENDS.remove(self)
        super().closeEvent(event)

    def set_regime(self, regime: str):
        if regime not in (REGIME_LEGACY, REGIME_LASER_REF, REGIME_SAMPLE_REF):
            return
        self.current_regime = regime
        for i in range(self.cmb_regime.count()):
            if self.cmb_regime.itemData(i) == regime:
                if self.cmb_regime.currentIndex() != i:
                    self.cmb_regime.blockSignals(True)
                    self.cmb_regime.setCurrentIndex(i)
                    self.cmb_regime.blockSignals(False)
                break
        self._update_button_labels_and_tooltips()
        self.regime_changed_signal.emit(regime)

    def _update_nomenclature_labels(self):
        nomen = COORDINATE_NOMENCLATURE.get(self.current_regime, COORDINATE_NOMENCLATURE[REGIME_LEGACY])
        if hasattr(self, "xname"):
            self.xname.setText(nomen["axis1_display"])
            self.xname.setToolTip(nomen["axis1_tooltip"])
        if hasattr(self, "yname"):
            self.yname.setText(nomen["axis2_display"])
            self.yname.setToolTip(nomen["axis2_tooltip"])
        if hasattr(self, "zname"):
            self.zname.setText(nomen["axis3_display"])
            self.zname.setToolTip(nomen["axis3_tooltip"])
        if hasattr(self, "lbl_goto_1"):
            self.lbl_goto_1.setText(nomen["axis1_goto"])
            self.lbl_goto_1.setToolTip(nomen["axis1_tooltip"])
        if hasattr(self, "lbl_goto_2"):
            self.lbl_goto_2.setText(nomen["axis2_goto"])
            self.lbl_goto_2.setToolTip(nomen["axis2_tooltip"])
        if hasattr(self, "lbl_goto_3"):
            self.lbl_goto_3.setText(nomen["axis3_goto"])
            self.lbl_goto_3.setToolTip(nomen["axis3_tooltip"])
        if hasattr(self, "lbl_step_xy"):
            self.lbl_step_xy.setText(nomen["step_xy_label"])

    def _update_button_labels_and_tooltips(self):
        self._update_nomenclature_labels()
        if self.current_regime == REGIME_LEGACY:
            self.xUpButton.setText("x ►")
            self.xUp2Button.setText("x ►►")
            self.xDownButton.setText("◄ x")
            self.xDown2Button.setText("◄◄ x")
            self.yUpButton.setText("y ▲")
            self.yUp2Button.setText("y ▲▲")
            self.yDownButton.setText("y ▼")
            self.yDown2Button.setText("y ▼▼")
            self.xUpButton.setToolTip("Legacy: Eje físico 1 (+) paso 1x")
            self.xUp2Button.setToolTip("Legacy: Eje físico 1 (+) paso 10x")
            self.xDownButton.setToolTip("Legacy: Eje físico 1 (-) paso 1x")
            self.xDown2Button.setToolTip("Legacy: Eje físico 1 (-) paso 10x")
            self.yUpButton.setToolTip("Legacy: Eje físico 2 (+) paso 1x")
            self.yUp2Button.setToolTip("Legacy: Eje físico 2 (+) paso 10x")
            self.yDownButton.setToolTip("Legacy: Eje físico 2 (-) paso 1x")
            self.yDown2Button.setToolTip("Legacy: Eje físico 2 (-) paso 10x")
            self.lbl_keyboard_info.setToolTip("Régimen Legacy: [→]=Eje1+, [←]=Eje1-, [↑]=Eje2+, [↓]=Eje2-")
        elif self.current_regime == REGIME_LASER_REF:
            self.xUpButton.setText("Laser ►")
            self.xUp2Button.setText("Laser ►►")
            self.xDownButton.setText("◄ Laser")
            self.xDown2Button.setText("◄◄ Laser")
            self.yUpButton.setText("Laser ▲")
            self.yUp2Button.setText("Laser ▲▲")
            self.yDownButton.setText("Laser ▼")
            self.yDown2Button.setText("Laser ▼▼")
            self.xUpButton.setToolTip("Laser Ref: Desplaza el spot láser a la DERECHA en pantalla (Eje físico 2 +)")
            self.xUp2Button.setToolTip("Laser Ref: Desplaza el spot láser a la DERECHA 10x (Eje físico 2 +)")
            self.xDownButton.setToolTip("Laser Ref: Desplaza el spot láser a la IZQUIERDA en pantalla (Eje físico 2 -)")
            self.xDown2Button.setToolTip("Laser Ref: Desplaza el spot láser a la IZQUIERDA 10x (Eje físico 2 -)")
            self.yUpButton.setToolTip("Laser Ref: Desplaza el spot láser hacia ARRIBA en pantalla (Eje físico 1 -)")
            self.yUp2Button.setToolTip("Laser Ref: Desplaza el spot láser hacia ARRIBA 10x (Eje físico 1 -)")
            self.yDownButton.setToolTip("Laser Ref: Desplaza el spot láser hacia ABAJO en pantalla (Eje físico 1 +)")
            self.yDown2Button.setToolTip("Laser Ref: Desplaza el spot láser hacia ABAJO 10x (Eje físico 1 +)")
            self.lbl_keyboard_info.setToolTip("Régimen Laser Ref: [→]=Láser Derecha, [←]=Láser Izquierda, [↑]=Láser Arriba, [↓]=Láser Abajo")
        elif self.current_regime == REGIME_SAMPLE_REF:
            self.xUpButton.setText("Sample ►")
            self.xUp2Button.setText("Sample ►►")
            self.xDownButton.setText("◄ Sample")
            self.xDown2Button.setText("◄◄ Sample")
            self.yUpButton.setText("Sample ▲")
            self.yUp2Button.setText("Sample ▲▲")
            self.yDownButton.setText("Sample ▼")
            self.yDown2Button.setText("Sample ▼▼")
            self.xUpButton.setToolTip("Sample Ref: Desplaza los objetos de la muestra a la DERECHA en pantalla (Eje físico 2 -)")
            self.xUp2Button.setToolTip("Sample Ref: Desplaza los objetos de la muestra a la DERECHA 10x (Eje físico 2 -)")
            self.xDownButton.setToolTip("Sample Ref: Desplaza los objetos de la muestra a la IZQUIERDA en pantalla (Eje físico 2 +)")
            self.xDown2Button.setToolTip("Sample Ref: Desplaza los objetos de la muestra a la IZQUIERDA 10x (Eje físico 2 +)")
            self.yUpButton.setToolTip("Sample Ref: Desplaza los objetos de la muestra hacia ARRIBA en pantalla (Eje físico 1 +)")
            self.yUp2Button.setToolTip("Sample Ref: Desplaza los objetos de la muestra hacia ARRIBA 10x (Eje físico 1 +)")
            self.yDownButton.setToolTip("Sample Ref: Desplaza los objetos de la muestra hacia ABAJO en pantalla (Eje físico 1 -)")
            self.yDown2Button.setToolTip("Sample Ref: Desplaza los objetos de la muestra hacia ABAJO 10x (Eje físico 1 -)")
            self.lbl_keyboard_info.setToolTip("Régimen Sample Ref: [→]=Muestra Derecha, [←]=Muestra Izquierda, [↑]=Muestra Arriba, [↓]=Muestra Abajo")

    # ── Control por Teclado (Flechas paso 1x, Shift paso 10x) ─────────────────

    def keyPressEvent(self, event: QKeyEvent):
        focused = self.focusWidget() or QApplication.focusWidget()
        if isinstance(focused, (QLineEdit, QTextEdit, QPlainTextEdit)):
            super().keyPressEvent(event)
            return

        k = event.key()
        step_mult = 10.0 if (event.modifiers() & Qt.KeyboardModifier.ShiftModifier) else 1.0

        if k == Qt.Key.Key_Right:
            self.move_direction("right", step_mult)
            event.accept()
            return
        elif k == Qt.Key.Key_Left:
            self.move_direction("left", step_mult)
            event.accept()
            return
        elif k == Qt.Key.Key_Up:
            self.move_direction("up", step_mult)
            event.accept()
            return
        elif k == Qt.Key.Key_Down:
            self.move_direction("down", step_mult)
            event.accept()
            return
        elif k == Qt.Key.Key_PageUp:
            if step_mult > 1.0:
                self.zUp2()
            else:
                self.zUp()
            event.accept()
            return
        elif k == Qt.Key.Key_PageDown:
            if step_mult > 1.0:
                self.zDown2()
            else:
                self.zDown()
            event.accept()
            return

        super().keyPressEvent(event)

    def eventFilter(self, watched, event: QEvent):
        if event.type() == QEvent.Type.KeyPress:
            focused = self.focusWidget() or QApplication.focusWidget()
            if not isinstance(focused, (QLineEdit, QTextEdit, QPlainTextEdit)):
                if isinstance(event, QKeyEvent):
                    k = event.key()
                    if k in (Qt.Key.Key_Right, Qt.Key.Key_Left, Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_PageUp, Qt.Key.Key_PageDown):
                        self.keyPressEvent(event)
                        return True
        return super().eventFilter(watched, event)

    # ── Construcción de la GUI ────────────────────────────────────────────────

    def _setup_gui(self):
        S = 46   # tamaño fijo de botones de flecha

        bold = QFont(); bold.setBold(True)

        # ── Posicionador ──────────────────────────────────────────────────────
        self.read_pos_button = QPushButton("Read position")
        self.read_pos_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.read_pos_button.clicked.connect(self.get_read_pos)
        self.set_ref_button  = QPushButton("Set reference")
        self.set_ref_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
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
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
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
        positioner.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
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
        self.lbl_step_xy = QLabel("step x/y [µm]")
        lo.addWidget(self.lbl_step_xy,     4, 6, 1, 2)
        lo.addWidget(self.StepEdit,        5, 6)
        lo.addWidget(self.zname,           4, 0)
        lo.addWidget(self.zLabel,          4, 1)
        lo.addWidget(self.zUp2Button,      0, 9, 2, 1)
        lo.addWidget(self.zUpButton,       1, 9, 3, 1)
        lo.addWidget(self.zDownButton,     3, 9, 2, 1)
        lo.addWidget(self.zDown2Button,    4, 9, 2, 1)
        self.lbl_step_z = QLabel("step z [µm]")
        lo.addWidget(self.lbl_step_z,      4, 10)
        lo.addWidget(self.zStepEdit,       5, 10)
        lo.addWidget(self.set_ref_button,  5, 0)

        # ── Go to ─────────────────────────────────────────────────────────────
        gotoWidget = QWidget()
        lo2 = QGridLayout(gotoWidget)

        self.lbl_goto_1 = QLabel("X [µm]")
        self.lbl_goto_2 = QLabel("Y [µm]")
        self.lbl_goto_3 = QLabel("Z [µm]")
        lo2.addWidget(self.lbl_goto_1, 1, 1)
        lo2.addWidget(self.lbl_goto_2, 2, 1)
        lo2.addWidget(self.lbl_goto_3, 3, 1)

        self.xgotoLabel = QLineEdit(str(int(DEFAULT_NANO_GOTO_X) if DEFAULT_NANO_GOTO_X.is_integer() else DEFAULT_NANO_GOTO_X))
        self.ygotoLabel = QLineEdit(str(int(DEFAULT_NANO_GOTO_Y) if DEFAULT_NANO_GOTO_Y.is_integer() else DEFAULT_NANO_GOTO_Y))
        self.zgotoLabel = QLineEdit(str(int(DEFAULT_NANO_GOTO_Z) if DEFAULT_NANO_GOTO_Z.is_integer() else DEFAULT_NANO_GOTO_Z))
        for w in (self.xgotoLabel, self.ygotoLabel, self.zgotoLabel):
            w.setFixedWidth(54)

        self.gotoButton = QPushButton("Go to")
        self.gotoButton.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.gotoButton.clicked.connect(self.go_to_action)

        lo2.addWidget(self.gotoButton,    1, 5, 2, 2)
        lo2.addWidget(self.xgotoLabel,    1, 2)
        lo2.addWidget(self.ygotoLabel,    2, 2)
        lo2.addWidget(self.zgotoLabel,    3, 2)

        # ── Barra de Estado de Conexión y Reconexión ─────────────────────────
        self.conn_status_label = QLabel("⚪ Verificando...")
        self.conn_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.conn_status_label.setStyleSheet(
            "color: #a6adc8; background-color: #181825; border: 1px solid #45475a; "
            "border-radius: 4px; padding: 2px 8px; font-size: 8pt; font-weight: bold;"
        )

        self.reconnect_button = QPushButton("🔌 Reconectar")
        self.reconnect_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.reconnect_button.setToolTip("Reintenta conectar la platina física si fue encendida o reconectada por USB.")
        self.reconnect_button.setStyleSheet("""
            QPushButton {
                background-color: #313244; color: #cdd6f4; border: 1px solid #45475a;
                border-radius: 4px; padding: 2px 8px; font-size: 8pt; font-weight: bold;
            }
            QPushButton:hover { background-color: #45475a; color: #89b4fa; }
            QPushButton:pressed { background-color: #89b4fa; color: #11111b; }
        """)
        self.reconnect_button.clicked.connect(self.reconnect_signal.emit)

        status_bar = QHBoxLayout()
        status_bar.setSpacing(6)
        status_bar.addWidget(self.conn_status_label, stretch=1)
        status_bar.addWidget(self.reconnect_button)

        # ── Selector de Régimen de Coordenadas & Atajos de Teclado ─────────
        regime_hlo = QHBoxLayout()
        regime_hlo.setSpacing(6)
        lbl_regime = QLabel("<b>Régimen:</b>")
        lbl_regime.setStyleSheet("font-size: 8pt; color: #cdd6f4;")
        self.cmb_regime = QComboBox()
        self.cmb_regime.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.cmb_regime.addItem("🏛️ Legacy (Ejes PI 1/2)", REGIME_LEGACY)
        self.cmb_regime.addItem("🎯 Laser Ref (Spot en Pantalla)", REGIME_LASER_REF)
        self.cmb_regime.addItem("🔬 Sample Ref (Objetos en Muestra)", REGIME_SAMPLE_REF)
        self.cmb_regime.setStyleSheet("""
            QComboBox {
                background-color: #181825; color: #89b4fa; border: 1px solid #45475a;
                border-radius: 4px; padding: 2px 6px; font-size: 8pt; font-weight: bold;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background-color: #1e1e2e; color: #cdd6f4; selection-background-color: #313244;
            }
        """)
        self.cmb_regime.currentIndexChanged.connect(self._on_regime_changed)

        self.lbl_keyboard_info = QLabel("⌨️ [←↑→↓] Paso 1x")
        self.lbl_keyboard_info.setStyleSheet(
            "color: #a6e3a1; background-color: #11111b; border: 1px solid #313244; "
            "border-radius: 4px; padding: 2px 6px; font-size: 8pt; font-weight: bold;"
        )
        self.lbl_keyboard_info.setToolTip("Control por flechas activo: Pulse [← ↑ → ↓] para mover 1 paso (Shift: 10 pasos, PgUp/PgDn: Eje Z).")

        regime_hlo.addWidget(lbl_regime)
        regime_hlo.addWidget(self.cmb_regime, stretch=1)
        regime_hlo.addWidget(self.lbl_keyboard_info)

        pos_container = QWidget()
        pos_vlo = QVBoxLayout(pos_container)
        pos_vlo.setContentsMargins(2, 2, 2, 2)
        pos_vlo.setSpacing(6)
        pos_vlo.addLayout(status_bar)
        pos_vlo.addLayout(regime_hlo)
        pos_vlo.addWidget(positioner)

        # ── Docks ─────────────────────────────────────────────────────────────
        hbox = QHBoxLayout(self)
        dock_area = DockArea()

        posDock = Dock("Positioners", size=(1, 1))
        posDock.addWidget(pos_container)
        dock_area.addDock(posDock)

        gotoDock = Dock("Go to", size=(1, 1))
        gotoDock.addWidget(gotoWidget)
        dock_area.addDock(gotoDock, "left", posDock)

        hbox.addWidget(dock_area)
        self.setLayout(hbox)

    def make_connection(self, backend: Backend):
        backend.read_pos_signal.connect(self.read_pos_list)
        backend.reference_signal.connect(self.get_go_to_reference)
        backend.connection_status_signal.connect(self.update_connection_status)
        self.reconnect_signal.connect(backend.reconnect)
        self.regime_changed_signal.connect(backend.set_regime)
        is_phys = hasattr(pi, "is_physically_connected") and pi.is_physically_connected()
        txt = f"PI Física ({pi.qIDN().strip().split()[0]})" if is_phys else "Modo Virtual (Desconectada)"
        self.update_connection_status(is_phys, txt)


# ══════════════════════════════════════════════════════════════════════════════
class Backend(QObject):

    read_pos_signal          = pyqtSignal(list)       # → [x_um, y_um, z_um]
    reference_signal         = pyqtSignal(list)       # → [x_um, y_um, z_um] al set_reference
    connection_status_signal = pyqtSignal(bool, str)  # → (is_physical, status_text)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.current_regime = DEFAULT_COORDINATE_REGIME
        self.reconnect()

    @pyqtSlot(str)
    def set_regime(self, regime: str):
        if regime in (REGIME_LEGACY, REGIME_LASER_REF, REGIME_SAMPLE_REF):
            self.current_regime = regime

    @pyqtSlot()
    def reconnect(self):
        from config import PI_SERIAL
        ok = pi.connect(PI_SERIAL)
        is_phys = hasattr(pi, "is_physically_connected") and pi.is_physically_connected()
        if is_phys:
            txt = f"PI Física ({pi.qIDN().strip().split()[0]})"
        else:
            txt = "Modo Virtual (Desconectada)"
        self.connection_status_signal.emit(is_phys, txt)
        self.read_pos()

    @pyqtSlot()
    def read_pos(self) -> tuple[float, float, float]:
        pos   = pi.qPOS()
        x_pos = round(pos["1"], 3)
        y_pos = round(pos["2"], 3)
        z_pos = round(pos["3"], 3)
        self.read_pos_signal.emit([x_pos, y_pos, z_pos])
        is_phys = hasattr(pi, "is_physically_connected") and pi.is_physically_connected()
        txt = f"PI Física ({pi.qIDN().strip().split()[0]})" if is_phys else "Modo Virtual (Desconectada)"
        self.connection_status_signal.emit(is_phys, txt)
        return x_pos, y_pos, z_pos

    @pyqtSlot()
    def set_reference(self):
        x_pos, y_pos, z_pos = self.read_pos()
        self.reference_signal.emit([x_pos, y_pos, z_pos])

    @pyqtSlot(str, float)
    def move(self, axis: str, dist: float):
        """Movimiento relativo en el eje indicado clampeado al rango físico de la platina (0 a 100 µm)."""
        from config import PI_STAGE_RANGE_UM
        x_pos, y_pos, z_pos = self.read_pos()
        axis_map = {"x": (1, x_pos), "y": (2, y_pos), "z": (3, z_pos)}
        if axis not in axis_map:
            print(f"[Nano] Eje desconocido: {axis}")
            return
        ax_num, current = axis_map[axis]
        target = max(0.0, min(PI_STAGE_RANGE_UM, current + dist))
        pi.MOV(ax_num, target)
        while not all(pi.qONT(ax_num).values()):
            time.sleep(0.01)
        self.read_pos()

    @pyqtSlot(list)
    def goto(self, go_to_pos: list):
        from config import PI_STAGE_RANGE_UM
        target = [
            max(0.0, min(PI_STAGE_RANGE_UM, float(go_to_pos[0]))),
            max(0.0, min(PI_STAGE_RANGE_UM, float(go_to_pos[1]))),
            max(0.0, min(PI_STAGE_RANGE_UM, float(go_to_pos[2]))),
        ]
        self._moveto(target)
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
        frontend.reconnect_signal.connect(self.reconnect)
        self.read_pos_signal.connect(frontend.read_pos_list)
        self.reference_signal.connect(frontend.get_go_to_reference)
        self.connection_status_signal.connect(frontend.update_connection_status)
        is_phys = hasattr(pi, "is_physically_connected") and pi.is_physically_connected()
        txt = f"PI Física ({pi.qIDN().strip().split()[0]})" if is_phys else "Modo Virtual (Desconectada)"
        frontend.update_connection_status(is_phys, txt)


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
