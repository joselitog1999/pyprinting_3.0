# -*- coding: utf-8 -*-
"""
zero_order_dialog.py — Interlock de Seguridad para Movimiento a Orden Cero (0 nm)
PySpectrum 3.0 — UNSAM Nanofotónica

Al ir a Orden Cero el espectrógrafo refleja el haz incidente especularmente hacia el detector
sin dispersar: si el láser de excitación está abierto y/o la ganancia EM está activa, el flujo
de fotones puede saturar o dañar el sensor EMCCD. Este diálogo modal inspecciona ambas
condiciones de riesgo y exige una elección explícita del operador antes de mover la red.

Nota de diseño: pyspectrum/modules/spectrum_control.py::Backend.goto_zero_order() ya aplica
una salvaguarda automática incondicional (fuerza EM Gain=0 y cierra todos los shutters) para el
dock legado — este diálogo la reemplaza en el nuevo shell por una elección explícita del
operador con 4 alternativas + cancelar, en vez de imponer siempre el modo seguro por defecto.
"""
from __future__ import annotations
from typing import Any, Optional
from PyQt6 import QtCore, QtWidgets

from core.nidaq import close_all_shutters, close_shutter, get_open_shutter_names


def _read_em_gain(camera: Any) -> int:
    """Normaliza el valor de retorno de get_emccd_gain(), que difiere entre el mock
    (int directo) y el driver real (Tuple[ret_code, gain])."""
    val = camera.get_emccd_gain()
    if isinstance(val, tuple):
        return int(val[1])
    return int(val)


class ZeroOrderSafetyDialog(QtWidgets.QDialog):
    """Interlock modal mostrado al presionar 'Ir a Orden Cero'. Inspecciona EM Gain y
    obturadores láser abiertos, y exige una acción explícita del operador antes de permitir
    el movimiento del espectrógrafo a 0.0 nm."""

    ACTION_SAFE_DEFAULT = "close_laser_and_gain_off"
    ACTION_LASER_ONLY = "close_laser_only"
    ACTION_GAIN_ONLY = "gain_off_only"
    ACTION_OVERRIDE = "override_ignore"
    ACTION_CANCEL = "cancel"

    SAFE_EXPOSURE_TIME_S = 0.01

    def __init__(self, camera: Any, spectrometer: Any, parent=None):
        super().__init__(parent)
        self.camera = camera
        self.spectrometer = spectrometer
        self.chosen_action: Optional[str] = None

        self.em_gain = _read_em_gain(camera)
        self.open_shutters = get_open_shutter_names()

        self.setWindowTitle("🛡️ Interlock de Seguridad — Orden Cero (0.0 nm)")
        self.setModal(True)
        self.setMinimumWidth(460)
        self.setStyleSheet("""
            QDialog { background-color: #11111B; }
            QLabel { color: #CDD6F4; }
            QPushButton {
                background-color: #313244; color: #CDD6F4; border: 1px solid #45475A;
                border-radius: 4px; padding: 8px 12px; font-weight: bold; text-align: left;
            }
            QPushButton:hover { background-color: #45475A; }
        """)
        self._setup_ui()

    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(10)

        lbl_title = QtWidgets.QLabel(
            "<b>⚠️ Movimiento a Orden Cero (0.0 nm)</b><br>"
            "La red reflejará el haz incidente de forma especular y directa hacia el detector, "
            "sin dispersión espectral."
        )
        lbl_title.setWordWrap(True)
        lbl_title.setStyleSheet("font-size: 10.5pt;")
        layout.addWidget(lbl_title)

        # ── Estado de riesgo ──────────────────────────────────────────────────
        risk_box = QtWidgets.QVBoxLayout()
        if self.em_gain > 0:
            lbl_gain = QtWidgets.QLabel(f"🔴 PELIGRO: Ganancia EM activa en orden especular ({self.em_gain}x).")
            lbl_gain.setStyleSheet("background-color: #311B24; color: #F38BA8; font-weight: bold; padding: 6px; border-radius: 4px;")
        else:
            lbl_gain = QtWidgets.QLabel("🟢 Ganancia EM: 0x (segura).")
            lbl_gain.setStyleSheet("background-color: #1E2B1E; color: #A6E3A1; padding: 6px; border-radius: 4px;")
        risk_box.addWidget(lbl_gain)

        if self.open_shutters:
            names = ", ".join(self.open_shutters)
            lbl_laser = QtWidgets.QLabel(f"🔴 ALERTA: Láser(es) de excitación abierto(s): {names}.")
            lbl_laser.setStyleSheet("background-color: #311B24; color: #F38BA8; font-weight: bold; padding: 6px; border-radius: 4px;")
        else:
            lbl_laser = QtWidgets.QLabel("🟢 Obturadores láser: todos cerrados.")
            lbl_laser.setStyleSheet("background-color: #1E2B1E; color: #A6E3A1; padding: 6px; border-radius: 4px;")
        lbl_laser.setWordWrap(True)
        risk_box.addWidget(lbl_laser)
        layout.addLayout(risk_box)

        # ── Acciones ──────────────────────────────────────────────────────────
        self.btn_safe_default = QtWidgets.QPushButton("🛡️ Cerrar Láser y Apagar EM Gain  (Recomendado)")
        self.btn_safe_default.setStyleSheet("background-color: #A6E3A1; color: #11111B; font-weight: bold; text-align: left; padding: 8px 12px; border-radius: 4px;")
        self.btn_safe_default.clicked.connect(self._on_safe_default)
        layout.addWidget(self.btn_safe_default)

        self.btn_laser_only = QtWidgets.QPushButton("🔴 Solo Cerrar Láser (mantiene EM Gain actual)")
        self.btn_laser_only.clicked.connect(self._on_laser_only)
        layout.addWidget(self.btn_laser_only)

        self.btn_gain_only = QtWidgets.QPushButton("🔻 Solo Apagar EM Gain (mantiene láser actual)")
        self.btn_gain_only.clicked.connect(self._on_gain_only)
        layout.addWidget(self.btn_gain_only)

        self.btn_override = QtWidgets.QPushButton("⚠️ Ignorar y Continuar (Override Experto)")
        self.btn_override.setStyleSheet("background-color: #313244; color: #F9E2AF; border: 1px solid #F9E2AF; text-align: left; padding: 8px 12px; border-radius: 4px;")
        self.btn_override.clicked.connect(self._on_override)
        layout.addWidget(self.btn_override)

        self.btn_cancel = QtWidgets.QPushButton("✖ Cancelar")
        self.btn_cancel.clicked.connect(self.reject)
        layout.addWidget(self.btn_cancel)

    # ── Handlers de acción: ejecutan la salvaguarda elegida y ACEPTAN el diálogo ──

    def _apply_laser_closure(self):
        close_all_shutters()

    def _apply_gain_off(self):
        self.camera.set_emccd_gain(0)
        self.camera.set_exposure_time(self.SAFE_EXPOSURE_TIME_S)

    def _on_safe_default(self):
        self._apply_laser_closure()
        self._apply_gain_off()
        self.chosen_action = self.ACTION_SAFE_DEFAULT
        self.accept()

    def _on_laser_only(self):
        self._apply_laser_closure()
        self.chosen_action = self.ACTION_LASER_ONLY
        self.accept()

    def _on_gain_only(self):
        self._apply_gain_off()
        self.chosen_action = self.ACTION_GAIN_ONLY
        self.accept()

    def _on_override(self):
        print(
            "[ZeroOrderSafetyDialog WARNING] Override experto: movimiento a Orden Cero SIN cerrar "
            f"láseres ni apagar EM Gain (EM Gain={self.em_gain}x, shutters abiertos={self.open_shutters})."
        )
        self.chosen_action = self.ACTION_OVERRIDE
        self.accept()

    def execute_and_move(self) -> Optional[str]:
        """Ejecuta el diálogo modal y, si el operador no canceló, mueve el espectrógrafo a
        Orden Cero (0.0 nm) tras aplicar la salvaguarda elegida. Devuelve la acción tomada
        (o None si se canceló)."""
        result = self.exec()
        if result != QtWidgets.QDialog.DialogCode.Accepted or self.chosen_action is None:
            return None
        if hasattr(self.spectrometer, "goto_zero_order"):
            self.spectrometer.goto_zero_order()
        else:
            self.spectrometer.ShamrockSetWavelength(0, 0.0)
        return self.chosen_action
