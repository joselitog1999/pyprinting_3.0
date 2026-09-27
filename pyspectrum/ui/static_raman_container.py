# -*- coding: utf-8 -*-
"""
static_raman_container.py — Contenedor de Pestaña 2 (Static Raman & Inspector 2D)
PySpectrum 3.0 — UNSAM Nanofotónica

Fase 3 del Rework Arquitectónico: divide la Pestaña 2 en dos sub-pestañas ergonómicas
mediante un QTabWidget interno — "📊 Espectro 1D & Análisis" (pyspectrum/modules/static_raman.py,
sin cambios de comportamiento salvo el nuevo selector de modo de lectura) y
"🗺️ Resultado Medición / Inspector 2D" (pyspectrum/ui/raman_2d_inspector.py, nuevo). Al recibir
un cuadro 2D (Multi-Track o Imagen 2D), conmuta automáticamente a la sub-pestaña del Inspector.
"""
from __future__ import annotations
from PyQt6 import QtWidgets

from pyspectrum.modules.static_raman import StaticRamanWidget
from pyspectrum.ui.raman_2d_inspector import Raman2DInspectorWidget


class StaticRamanTabContainer(QtWidgets.QWidget):
    """Widget embebido en la Pestaña 2 del shell principal."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.spectrum_widget = StaticRamanWidget()
        self.inspector_widget = Raman2DInspectorWidget()

        self.inner_tabs = QtWidgets.QTabWidget()
        self.inner_tabs.addTab(self.spectrum_widget, "📊 Espectro 1D & Análisis")
        self.inner_tabs.addTab(self.inspector_widget, "🗺️ Resultado Medición / Inspector 2D")
        self.inspector_widget.frameReceivedSignal.connect(self._on_inspector_frame_received)

        # Sincronización de disparos de medición e inicio/parada Live
        self.inspector_widget.requestAcquireSingleSignal.connect(self.spectrum_widget.btn_single.click)
        self.inspector_widget.toggleLiveRamanSignal.connect(self._on_inspector_toggle_live)
        self.spectrum_widget.toggleLiveRamanSignal.connect(self.inspector_widget.set_live_state)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.inner_tabs)

    def _on_inspector_frame_received(self):
        self.inner_tabs.setCurrentIndex(1)

    def _on_inspector_toggle_live(self, running: bool):
        if self.spectrum_widget.btn_live.isChecked() != running:
            self.spectrum_widget.btn_live.setChecked(running)
            # DEC-032 cambió la firma a _on_toggle_live(checked); sin el argumento, el TypeError
            # quedaba dentro del slot y Live nunca arrancaba desde el Inspector.
            self.spectrum_widget._on_toggle_live(running)

