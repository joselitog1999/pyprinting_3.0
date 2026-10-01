# -*- coding: utf-8 -*-
"""
background_row.py — La fila "Fondo" de las rutinas (R4-N, Ronda 3 aprobada el 2026-09-30; DEC-040)

    Fondo: [Obturador cerrado ▾] [1 ▲▼] cuadros
    [Tomar fondo ahora] [Descartar] ☑ Restar
    ● válido · 1 cuadro · 0.2 s · obturador cerrado · hace 3 min

- El método va por defecto en "obturador cerrado"; "todo apagado" siempre está disponible.
- La cantidad de cuadros copia la medición (un cuadro por punto en las rutinas de grilla); se puede subir.
- El estado lo da la rutina (`show_status`): verde válido, gris "se toma al iniciar", ámbar con el motivo.
- La resta es sólo para mostrar (`for_display`): los datos se guardan crudos, con el fondo aparte.
- El método y los cuadros se recuerdan durante la sesión, en cada rutina.
"""
from __future__ import annotations

import time
from typing import Optional

import numpy as np
from PyQt6 import QtCore, QtWidgets
from PyQt6.QtCore import pyqtSignal

from pyspectrum.services import procedure_background as pb

_GREEN, _AMBER, _DIM = "#A6E3A1", "#F9E2AF", "#A6ADC8"

TOOLTIP = (
    "Fondo de la medición: se toma como una referencia, con la misma exposición y configuración de la cámara\n"
    "(ganancia EM, amplificador, preamplificador, velocidades HS y VS, modo de lectura, setpoint de temperatura)\n"
    "y, por defecto, la misma cantidad de cuadros que la medición.\n"
    "Sin luz no depende de la red ni de λc: un solo fondo sirve a todas las ventanas y a toda la grilla.\n"
    "Se reutiliza mientras esas condiciones no cambien; si cambian, se toma de nuevo.\n"
    "• Obturador cerrado: la rutina cierra el obturador del espectrómetro, lo verifica, toma el fondo y lo abre.\n"
    "• Todo apagado: apagá la lámpara y cerrá los láseres y apretá [Tomar fondo ahora] antes de iniciar.\n"
    "Los datos se guardan crudos y el fondo aparte; \"Restar\" es sólo para mostrar.")


class BackgroundRow(QtWidgets.QWidget):
    takeNowRequested = pyqtSignal(str, int)      # método, cuadros
    discardRequested = pyqtSignal()
    settingsChanged = pyqtSignal(str, int)

    def __init__(self, default_frames: int = 1, parent=None):
        super().__init__(parent)
        self._state, self._dark = "none", None
        lay = QtWidgets.QGridLayout(self)            # compacta: entra en la columna de controles de cada rutina
        lay.setContentsMargins(0, 4, 0, 4)
        lay.setHorizontalSpacing(6)
        lay.setVerticalSpacing(3)
        lay.addWidget(QtWidgets.QLabel("Fondo:"), 0, 0)
        self.cmb_method = QtWidgets.QComboBox()
        self.cmb_method.addItem("Obturador cerrado", pb.METHOD_SHUTTER)
        self.cmb_method.addItem("Todo apagado", pb.METHOD_ALL_OFF)
        lay.addWidget(self.cmb_method, 0, 1)
        self.spin_frames = QtWidgets.QSpinBox()
        self.spin_frames.setRange(1, 100)
        self.spin_frames.setValue(int(default_frames))
        self.spin_frames.setSuffix(" cuadros")
        self.spin_frames.setToolTip("Por defecto, los mismos cuadros que la medición. Más cuadros bajan el ruido del fondo.")
        lay.addWidget(self.spin_frames, 0, 2)
        self.btn_take = QtWidgets.QPushButton("Tomar fondo ahora")
        self.btn_take.setToolTip("Toma un fondo nuevo con las condiciones actuales, con el método elegido.")
        lay.addWidget(self.btn_take, 1, 0, 1, 2)
        self.btn_discard = QtWidgets.QPushButton("Descartar")
        self.btn_discard.setToolTip("Descarta el fondo de estas condiciones; se toma de nuevo al iniciar (obturador) "
                                    "o con [Tomar fondo ahora] (todo apagado).")
        lay.addWidget(self.btn_discard, 1, 2)
        self.chk_subtract = QtWidgets.QCheckBox("Restar")
        self.chk_subtract.setChecked(True)
        self.chk_subtract.setToolTip("Muestra crudo − fondo. Lo guardado es siempre el crudo, con el fondo aparte.")
        lay.addWidget(self.chk_subtract, 1, 3)
        self.lbl_status = QtWidgets.QLabel("")
        self.lbl_status.setWordWrap(True)
        lay.addWidget(self.lbl_status, 2, 0, 1, 4)
        self.setToolTip(TOOLTIP)
        self.btn_take.clicked.connect(lambda: self.takeNowRequested.emit(self.method(), self.n_frames()))
        self.btn_discard.clicked.connect(self.discardRequested.emit)
        self.cmb_method.currentIndexChanged.connect(self._on_settings)
        self.spin_frames.valueChanged.connect(self._on_settings)
        self.show_status("none", None, "")

    def method(self) -> str:
        return self.cmb_method.currentData()

    def n_frames(self) -> int:
        return int(self.spin_frames.value())

    def subtract(self) -> bool:
        return self.chk_subtract.isChecked()

    @property
    def dark(self) -> Optional[pb.Dark]:
        return self._dark if self._state == "valid" else None

    def _on_settings(self, *_):
        self.show_status(self._state, self._dark, getattr(self, "_reason", ""))
        self.settingsChanged.emit(self.method(), self.n_frames())

    def show_status(self, state: str, dark: Optional[pb.Dark], reason: str) -> None:
        self._state, self._dark, self._reason = state, dark, reason
        all_off = self.method() == pb.METHOD_ALL_OFF
        if state == "valid" and dark is not None:
            text = (f"● válido · {dark.n_frames} {'cuadro' if dark.n_frames == 1 else 'cuadros'} · "
                    f"{dark.conditions.exposure_s:g} s · {pb.METHOD_LABELS.get(dark.method, dark.method)} · "
                    f"{_age(dark.t_wall)}")
            color = _GREEN
        elif state == "valid":
            text, color = f"● válido · {reason}" if reason else "● válido", _GREEN
        elif state == "invalid":
            then = "tomalo de nuevo con [Tomar fondo ahora]" if all_off else "se toma de nuevo al iniciar"
            text, color = f"● no válido: {reason}; {then}", _AMBER
        elif all_off:
            text, color = "● falta: apagá la lámpara y los láseres y apretá [Tomar fondo ahora]", _AMBER
        else:
            text, color = "● se toma al iniciar (obturador cerrado)", _DIM
        self.lbl_status.setText(text)
        self.lbl_status.setStyleSheet(f"color: {color};")

    def for_display(self, spec):
        """crudo − fondo si "Restar" está marcado y hay un fondo válido de la misma forma; si no, el crudo."""
        d = self.dark
        arr = np.asarray(spec)
        if not self.subtract() or d is None or d.mean.shape != arr.shape:
            return spec
        return arr.astype(np.float64) - d.mean


def _age(t_wall: str) -> str:
    try:
        t = time.mktime(time.strptime(t_wall, "%Y-%m-%dT%H:%M:%S"))
    except (TypeError, ValueError):
        return t_wall
    minutes = max(0, int((time.time() - t) // 60))
    return "recién" if minutes == 0 else f"hace {minutes} min"
