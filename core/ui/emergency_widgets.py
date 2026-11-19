# -*- coding: utf-8 -*-
"""Botón de parada y banner de la parada de emergencia (C-01 Ronda 4, R4-17 fase 4c; `gui_design_v2.md` §5.1;
`ronda4_conciliacion_fase4c.md`; DEC-049).

Los usan PyPrinting (ventana principal, panel de impresión, traza, dock de obturadores) y PySpectrum. Los dos
programas comparten el coordinador y el puente del proceso, así que una parada y un Rearmar valen para los dos.

El banner no es modal y nunca dice "confirmado" sin un `CloseResult` exitoso del cerrador para esa parada. Si a los
0.5 s no lo hay, o la placa no aceptó el cierre, dice que se corte con la llave del láser: es la única parada física
independiente del software (el láser no tiene interlock remoto).
"""
from __future__ import annotations

import time
from typing import Callable, Optional

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy

from core import nidaq
from core.emergency_stop import get_emergency_coordinator
from core.ui.emergency_keys import get_emergency_bridge

RED = "#f38ba8"
BASE = "#1e1e2e"
GREEN = "#a6e3a1"
PEACH = "#fab387"
ESTOP_TOOLTIP = ("<b>Parada de emergencia</b><br>Cierra los cuatro obturadores, detiene todas las rutinas y retiene "
                 "la platina. Nada vuelve a abrir ni a moverse hasta <b>Rearmar</b> y después <b>Play</b>.<br>"
                 "Atajos: <b>Ctrl+E</b> o <b>F12</b>, desde cualquier ventana.<br>"
                 "La única parada física independiente del programa es la <b>llave del láser</b>.")


def _hms(t_wall: Optional[float]) -> str:
    if not t_wall:
        return "--:--:--"
    lt = time.localtime(t_wall)
    return time.strftime("%H:%M:%S", lt) + f".{int((t_wall % 1) * 1000):03d}"


class EmergencyStopButton(QPushButton):
    """"■ PARADA DE EMERGENCIA · Ctrl+E · F12" (o "EMERGENCIA", chico). Dispara el coordinador del proceso."""

    def __init__(self, source: str = "botón", compact: bool = False, parent=None):
        super().__init__("■ EMERGENCIA" if compact else "■ PARADA DE EMERGENCIA · Ctrl+E · F12", parent)
        self._source = source
        self.setToolTip(ESTOP_TOOLTIP)
        self.setMinimumHeight(24 if compact else 32)
        self.setStyleSheet(f"QPushButton {{ background-color: {RED}; color: {BASE}; font-weight: bold; "
                           f"border-radius: 4px; padding: 4px 12px; }}"
                           f"QPushButton:hover {{ background-color: #eba0ac; }}")
        self.clicked.connect(self._trigger)

    def _trigger(self):
        get_emergency_coordinator().trigger(self._source)


class EmergencyBanner(QFrame):
    """Banner persistente de la parada, con su botón Rearmar. Oculto mientras no haya parada."""

    def __init__(self, detail_provider: Optional[Callable[[], str]] = None, parent=None):
        super().__init__(parent)
        self.detail_provider = detail_provider
        self._bridge = get_emergency_bridge()
        self._gen = 0
        self._confirmed = False
        self._t_trigger = None
        self._active = False                            # hay una parada que este banner está mostrando
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 4)
        self.label = QLabel("")
        self.label.setWordWrap(True)
        self.label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.btn_rearm = QPushButton("Rearmar")
        self.btn_rearm.setToolTip("Habilita de nuevo la apertura de obturadores y los movimientos. Se habilita sólo con "
                                  "el cierre confirmado y todas las rutinas detenidas. La grilla queda en pausa: "
                                  "seguir es un Play aparte.")
        self.btn_rearm.setEnabled(False)
        self.btn_rearm.clicked.connect(self._request_rearm)
        lay.addWidget(self.label, 1)
        lay.addWidget(self.btn_rearm)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)
        self._bridge.stopTriggered.connect(self._on_stop)
        self._bridge.closeResult.connect(self._on_close_result)
        self._bridge.deadlineExpired.connect(self._on_deadline)
        self._bridge.rearmProgress.connect(self._on_rearm_progress)
        self._bridge.rearmed.connect(self._on_rearmed)
        self.hide()
        st = nidaq.get_emergency_state()
        if st.active:                                   # creado durante una parada: mostrarla
            self._on_stop(st.generation, st.source, st.t_trigger_wall or time.time())
            if st.confirmed and st.last_result is not None:
                self._on_close_result(st.last_result)

    # ── estados ──
    def _style(self, color: str):
        self.setStyleSheet(f"EmergencyBanner {{ background-color: #311b24; border: 2px solid {color}; "
                           f"border-radius: 4px; }} QLabel {{ color: {color}; font-weight: bold; }}")

    def _detail(self) -> str:
        try:
            d = self.detail_provider() if self.detail_provider else ""
        except Exception:
            d = ""
        return f" {d}" if d else ""

    def _on_stop(self, gen: int, source: str, t_wall: float):
        if gen == self._gen and self._active:
            return                                        # otra pulsación del mismo episodio
        self._gen, self._confirmed, self._t_trigger, self._active = int(gen), False, t_wall, True
        self._hide_timer.stop()
        self._style(RED)
        self.label.setText(f"PARADA DE EMERGENCIA {_hms(t_wall)} ({source}) — cerrando los obturadores…")
        self.btn_rearm.setEnabled(False)
        self.show()

    def _on_close_result(self, r):
        if r.estop_generation != self._gen or not self._gen:
            return
        if r.ok:
            self._confirmed = True
            self._style(RED)
            self.label.setText(f"PARADA DE EMERGENCIA {_hms(self._t_trigger)} — obturadores: escritura de cierre "
                               f"confirmada {_hms(r.t_written_wall)} (los cuatro).{self._detail()} Revisá el banco "
                               f"y pulsá [Rearmar].")
            self.btn_rearm.setEnabled(True)
        else:
            self._unconfirmed(r.error or "sin detalle")

    def _on_deadline(self, gen: int):
        if gen == self._gen and not self._confirmed:
            self._unconfirmed(f"sin respuesta de la placa en {int(0.5 * 1000)} ms")

    def _unconfirmed(self, why: str):
        if self._confirmed:
            return
        self._style(RED)
        self.label.setText(f"PARADA SIN CONFIRMAR {_hms(self._t_trigger)}: la placa no aceptó el cierre ({why}). "
                           f"<b>Cortá la emisión con la llave del láser.</b> El programa sigue reintentando.")
        self.btn_rearm.setEnabled(False)
        self.show()

    def _request_rearm(self):
        self.btn_rearm.setEnabled(False)
        self.label.setText(self.label.text().split(" Rearmando")[0] + " Rearmando…")
        self._bridge.request_rearm(self._gen)

    def _on_rearm_progress(self, check):
        if check.ok or not self._active:
            return
        if self._bridge.is_rearming():
            if check.reason:
                base = self.label.text().split(" Rearmando")[0]
                self.label.setText(f"{base} Rearmando… {check.reason}")
            return
        base = self.label.text().split(" Rearmando")[0]
        self.label.setText(f"{base} No se pudo rearmar: {check.reason}")
        self.btn_rearm.setEnabled(self._confirmed)

    def _on_rearmed(self, gen: int):
        if gen != self._gen:
            return
        self._active = False
        self._style(GREEN)
        self.label.setText("Rearmado: se pueden volver a abrir los obturadores. La grilla quedó en pausa: Play para "
                           "seguir.")
        self.btn_rearm.setEnabled(False)
        self._hide_timer.start(6000)

    # ── para los tests ──
    def state_text(self) -> str:
        return self.label.text()

    def is_active(self) -> bool:
        return self._active
