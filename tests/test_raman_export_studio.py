# -*- coding: utf-8 -*-
"""Estudio de Exportación en el analizador Raman (investigador, 2026-10-02).

- Panel de espectro individual: un botón por gráfico (el original con la línea base y el corregido con los
  picos). Cada uno abre `FigureExportStudioDialog` con las capas de SU gráfico.
- Suite multi-espectro: un botón que abre el estudio con el gráfico de la pestaña activa.
- Sin datos, avisa y no abre nada.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYPRINTING_SAFE", "1")

from pathlib import Path

import numpy as np
import pytest
from PyQt6.QtWidgets import QApplication, QMessageBox

import analysis.figure_export_studio as fes

_app = QApplication.instance() or QApplication(["pytest"])
_KEEP_ALIVE = []
CUMULO = Path(__file__).resolve().parent.parent / "reserva" / "cumulo_594.sif"


@pytest.fixture
def opened(monkeypatch):
    seen = []

    def exec_(self):
        seen.append(self)
        _KEEP_ALIVE.append(self)
        return 0
    monkeypatch.setattr(fes.FigureExportStudioDialog, "exec", exec_)
    return seen


@pytest.fixture
def analyzer(monkeypatch):
    from analysis.raman_analyzer import RamanAnalyzerWindow
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: (_ for _ in ()).throw(AssertionError(a[2])))
    w = RamanAnalyzerWindow()
    _KEEP_ALIVE.append(w)
    return w


def _names(dlg):
    return [l.get("name") for l in dlg.layers]


@pytest.mark.skipif(not CUMULO.exists(), reason="falta reserva/cumulo_594.sif")
def test_each_button_opens_the_studio_with_its_own_plot(analyzer, opened):
    analyzer.load_spectrum_file(CUMULO)
    analyzer.btn_studio_top.click()
    analyzer.btn_studio_bottom.click()
    assert len(opened) == 2
    top, bottom = opened
    assert "Espectro (Crudo)" in _names(top) and "Raman Neto" not in _names(top)
    assert "Raman Neto" in _names(bottom) and "Espectro (Crudo)" not in _names(bottom)
    assert "Fondo del SIF" in _names(top)                    # el fondo del SIF también es una capa
    assert top.default_filename.startswith("Raman_cumulo_594")


def test_without_data_it_warns_and_does_not_open(analyzer, opened, monkeypatch):
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warned.append(a[2]))
    analyzer.raw_wls = np.array([])                          # al abrir carga el demo: se vacía a mano
    analyzer.btn_studio_bottom.click()
    assert opened == [] and warned


def test_the_multi_spectrum_suite_opens_the_active_tab(analyzer, opened, monkeypatch):
    m = analyzer.tab_multi
    x = np.linspace(500.0, 700.0, 200)
    for i in range(3):
        m._add_spectrum_to_collection(f"s{i}", Path(f"s{i}.txt"), x, 100.0 + 10.0 * i + np.sin(x / 5.0), {})
    for tab, plot in ((m.tab_plot, m.plot_multi), (m.tab_raw_base, m.plot_raw_baseline), (m.tab_mean, m.plot_mean)):
        m.tabs_views.setCurrentWidget(tab)
        m.btn_export_studio.click()
        assert opened[-1].source_plot is plot
    assert len(opened) == 3
