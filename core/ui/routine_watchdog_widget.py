# -*- coding: utf-8 -*-
"""Selector del watchdog de rutinas (DEC-052).

El plazo del watchdog vigila sólo a las rutinas (grilla, escaneo confocal, autofoco, contrapropagante, Step & Glue,
escaneo lineal, rutinas de grilla de PySpectrum, calibración de λ, mapa hiperespectral). La operación manual de los
láseres —el dock de Shutters, la ventana Láser 532 y la traza F1— no tiene plazo: un láser abierto a mano queda
abierto hasta que el operador lo cierre.

El valor es uno por proceso (`core.nidaq.set_routine_watchdog_timeout`). Este widget aparece en el Control Panel
de impresión de PyPrinting y en el panel izquierdo de PySpectrum; si los dos están en el mismo proceso (modo
satélite), cada uno se resincroniza con el valor vigente en cada refresco.
"""
from __future__ import annotations

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QWidget

from core import nidaq

TIMEOUT_CHOICES = (
    ("30 s (predeterminado)", 30.0),
    ("60 s (1 min)", 60.0),
    ("300 s (5 min)", 300.0),
    ("600 s (10 min)", 600.0),
    ("Sin límite", None),
)

ROUTINE_WATCHDOG_TOOLTIP = (
    "<b>Watchdog de rutinas</b><br>"
    "Mientras corre una rutina con un láser abierto, la rutina late en cada iteración. Si deja de latir durante "
    "este plazo (por ejemplo, porque se colgó), se cierran <b>todos</b> los obturadores y la rutina se aborta.<br>"
    "Vale para todas las rutinas de este proceso: grilla, escaneo confocal, autofoco, contrapropagante, "
    "Step &amp; Glue, escaneo lineal, rutinas de grilla de PySpectrum, calibración de λ y mapa hiperespectral.<br>"
    "<b>No afecta la operación manual</b>: un láser abierto desde el dock de Shutters o la ventana Láser 532 "
    "queda abierto hasta que lo cierres.<br>"
    "Elegí un plazo mayor que el paso más largo de la rutina (una exposición larga, un asentamiento lento). "
    "<b>Sin límite</b> desactiva el corte por tiempo también en las rutinas (DEC-052)."
)

_DIM = "color: #a6adc8; font-size: 8pt;"
_ARMED = "color: #a6e3a1; font-weight: bold; font-size: 8pt;"
_WARN = "color: #fab387; font-weight: bold; font-size: 8pt;"


class RoutineWatchdogSelector(QWidget):
    """Fila "Watchdog de rutinas: [30 s ▾]" con el estado vigente debajo o al lado."""

    REFRESH_MS = 500

    def __init__(self, parent=None, compact: bool = False):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.lbl_title = QLabel("Watchdog de rutinas:")
        self.lbl_title.setToolTip(ROUTINE_WATCHDOG_TOOLTIP)
        self.combo = QComboBox()
        for text, value in TIMEOUT_CHOICES:
            self.combo.addItem(text, value)
        self.combo.setToolTip(ROUTINE_WATCHDOG_TOOLTIP)
        self.lbl_state = QLabel("")
        self.lbl_state.setToolTip(ROUTINE_WATCHDOG_TOOLTIP)
        lay.addWidget(self.lbl_title)
        lay.addWidget(self.combo)
        lay.addWidget(self.lbl_state, 1)
        self._sync_combo_from_engine()
        self.combo.currentIndexChanged.connect(self._on_changed)
        self._timer = QTimer(self)
        self._timer.setInterval(self.REFRESH_MS)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        self.refresh()

    def selected_timeout(self):
        return self.combo.currentData()

    def _on_changed(self, _index: int) -> None:
        nidaq.set_routine_watchdog_timeout(self.combo.currentData())
        self.refresh()

    def _sync_combo_from_engine(self) -> None:
        current = nidaq.get_routine_watchdog_timeout()
        idx = self.combo.findData(current)
        if idx >= 0 and idx != self.combo.currentIndex():
            self.combo.blockSignals(True)
            self.combo.setCurrentIndex(idx)
            self.combo.blockSignals(False)

    def refresh(self) -> None:
        """Resincroniza el combo con el valor del proceso y muestra el estado."""
        self._sync_combo_from_engine()
        timeout = nidaq.get_routine_watchdog_timeout()
        routines = nidaq.get_watchdog_routines()
        remaining = nidaq.get_watchdog_remaining_time()
        if timeout is None:
            text, style = "sin corte por tiempo", _WARN
        elif not routines:
            text, style = "sin rutina en curso", _DIM
        elif remaining is None:
            text, style = f"{', '.join(routines)} · sin láser abierto", _DIM
        else:
            text, style = f"{', '.join(routines)} · cierre en {remaining:.0f} s si deja de latir", _ARMED
        if self.lbl_state.text() != text:
            self.lbl_state.setText(text)
        if self.lbl_state.styleSheet() != style:
            self.lbl_state.setStyleSheet(style)

    def closeEvent(self, event):
        self._timer.stop()
        super().closeEvent(event)
