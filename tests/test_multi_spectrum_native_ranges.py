# -*- coding: utf-8 -*-
"""Suite multi-espectro: cada espectro con su rango completo en Overlay y Crudos (investigador, 2026-10-02).

Antes, la suite pasaba todo a una grilla común que es la intersección de los rangos: con `pl_400.sif` (698-802 nm) y
`cumulo_594.sif` (610-714 nm) quedaban 154 de 1004 puntos, sin aviso. Ahora:
- "Overlay" y "Crudos & Línea Base" dibujan cada espectro sobre su propio eje, con la misma línea base, el mismo
  suavizado y la misma normalización; un fondo de referencia más corto no se extrapola (fuera de su rango, NaN);
- promedio, cinética, mapa y PCA siguen en la grilla común (la necesitan) y un aviso dice su rango y cuántos puntos
  quedan, sólo cuando dejan datos afuera;
- el CSV de Overlay y de Crudos exporta cada espectro con su propio eje.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYPRINTING_SAFE", "1")

from pathlib import Path

import numpy as np
import pyqtgraph as pg
import pytest
from PyQt6.QtWidgets import QApplication, QMessageBox

_app = QApplication.instance() or QApplication(["pytest"])
_KEEP_ALIVE = []


@pytest.fixture
def suite(monkeypatch):
    from analysis.raman_analyzer import RamanAnalyzerWindow
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: (_ for _ in ()).throw(AssertionError(a[2])))
    w = RamanAnalyzerWindow()
    _KEEP_ALIVE.append(w)
    m = w.tab_multi
    m.set_unit_mode("wavelength")
    return m


def _add(m, name, x, y):
    m._add_spectrum_to_collection(name, Path(f"{name}.txt"), np.asarray(x, float), np.asarray(y, float), {})


def _curves(plot):
    out = {}
    for it in plot.plotItem.items:
        if isinstance(it, pg.PlotDataItem):
            x, y = it.getData()
            if x is not None and len(x):
                out[it.opts.get("name")] = (np.asarray(x), np.asarray(y))
    return out


def _two_ranges(m):
    xa = np.linspace(610.0, 714.0, 300)
    xb = np.linspace(698.0, 802.0, 300)
    _add(m, "a", xa, 100.0 + np.exp(-((xa - 650.0) / 3.0) ** 2))
    _add(m, "b", xb, 200.0 + np.exp(-((xb - 750.0) / 3.0) ** 2))
    m._reinterpolate_all()
    return xa, xb


def test_overlay_shows_each_spectrum_with_its_full_range(suite):
    m = suite
    m.combo_baseline_mode.setCurrentIndex(2)            # sin línea base
    xa, xb = _two_ranges(m)
    c = _curves(m.plot_multi)
    assert c["a"][0].min() == pytest.approx(610.0, abs=0.5) and c["a"][0].max() == pytest.approx(714.0, abs=0.5)
    assert c["b"][0].min() == pytest.approx(698.0, abs=0.5) and c["b"][0].max() == pytest.approx(802.0, abs=0.5)
    assert len(c["a"][0]) == 300 and len(c["b"][0]) == 300
    assert m.common_x.min() >= 698.0 - 0.5 and m.common_x.max() <= 714.0 + 0.5      # la grilla común no cambia


def test_the_raw_tab_shows_each_full_range_with_its_own_baseline(suite):
    m = suite
    m.combo_baseline_mode.setCurrentIndex(1)            # línea base por espectro
    _two_ranges(m)
    c = _curves(m.plot_raw_baseline)
    raw_b = [v for k, v in c.items() if k.startswith("b") and "Crudo" in k][0]
    base_b = [v for k, v in c.items() if "Línea Base b" in k][0]
    assert raw_b[0].max() == pytest.approx(802.0, abs=0.5) and len(base_b[0]) == len(raw_b[0]) == 300


def test_the_common_range_notice_appears_only_when_data_is_left_out(suite):
    m = suite
    _two_ranges(m)
    text = m.lbl_common_range.text()
    assert not m.lbl_common_range.isHidden()
    assert "698" in text and "714" in text and "promedio" in text.lower()
    m._on_clear_all()
    x = np.linspace(600.0, 700.0, 200)
    _add(m, "c", x, 100.0 + x * 0)
    _add(m, "d", x, 120.0 + x * 0)
    m._reinterpolate_all()
    assert m.lbl_common_range.isHidden()


def test_normalization_is_per_spectrum_on_its_own_axis(suite):
    m = suite
    m.combo_baseline_mode.setCurrentIndex(2)
    idx = m.combo_norm_mode.findText("Máximo") if hasattr(m, "combo_norm_mode") else -1
    m.norm_mode = "max"
    _two_ranges(m)
    m._reprocess_and_update()
    c = _curves(m.plot_multi)
    assert c["a"][0].min() == pytest.approx(610.0, abs=0.5)          # sobre su propio eje
    for name in ("a", "b"):
        assert np.nanmax(c[name][1]) == pytest.approx(1.0)


def test_a_shorter_reference_blank_is_not_extrapolated(suite):
    m = suite
    m.combo_baseline_mode.setCurrentIndex(0)            # archivo de referencia
    m.ref_blank_wls = np.linspace(600.0, 720.0, 200)
    m.ref_blank_counts = np.full(200, 50.0)
    m.ref_blank_name = "blanco"
    _two_ranges(m)
    m._reprocess_and_update()
    xb, yb = _curves(m.plot_multi)["b"]
    assert xb.max() == pytest.approx(802.0, abs=0.5)               # el rango completo de "b"
    inside, outside = xb <= 720.0, xb > 720.0
    assert np.all(np.isfinite(yb[inside])) and np.all(np.isnan(yb[outside]))


def test_the_overlay_csv_has_each_spectrum_with_its_own_axis(suite, monkeypatch, tmp_path):
    from PyQt6.QtWidgets import QFileDialog
    m = suite
    m.combo_baseline_mode.setCurrentIndex(2)
    _two_ranges(m)
    m.tabs_views.setCurrentWidget(m.tab_plot)
    out = tmp_path / "overlay.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(out), ""))
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    m._on_export_active_csv()
    header = out.read_text(encoding="utf-8").splitlines()[0].split(",")
    assert header[:4] == ["X_a", "a", "X_b", "b"] or header[:4] == ["Wavelength_nm_a", "a", "Wavelength_nm_b", "b"]
    data = np.genfromtxt(out, delimiter=",", skip_header=1)
    assert data.shape == (300, 4)
    assert np.nanmax(data[:, 2]) == pytest.approx(802.0, abs=0.5)
