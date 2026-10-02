# -*- coding: utf-8 -*-
"""Archivos .sif de Andor Solis en el analizador Raman (investigador, 2026-10-02).

Un .sif tiene casilleros fijos, en este orden: Señal, Referencia, Fondo, Live y Fuente, cada uno precedido por
una bandera de presencia. Cada canal declara además su tipo (`Counts`, `Counts (Bg Corrected)`,
`Transmittance`). El muestreo de `reserva/cumulo_594.sif` (Raman) trae la Señal ya corregida por Solis y el Fondo
(el "ruido", ≈ 320 cuentas de bias).

Contrato (respuestas del 2026-10-02):
- los canales se identifican por casillero, no por posición: un Raman con señal y fondo ya no se lee como
  "transmitancia + live" (también en el analizador de transmitancia);
- si la Señal dice `Counts (Bg Corrected)`, Solis ya restó el fondo: se usa tal cual, nunca se resta otra vez, y el
  fondo queda para ver; si dice `Counts`, se muestra señal − fondo por defecto, con una casilla para el crudo;
- sólo se resta si el fondo tiene la misma forma y la misma exposición; si no, se avisa;
- con varias filas, el promedio de un rango de filas (por defecto todas); con varios cuadros, el promedio o uno;
- el eje λ sale de la calibración del SIF (sin ella, píxeles, con aviso); el láser lo pone siempre el usuario: el
  `RamanExWavelength` del SIF no se usa;
- al exportar, el fondo va en una columna aparte.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYPRINTING_SAFE", "1")

from pathlib import Path

import numpy as np
import pytest

from core import sif_processor as sp

RESERVA = Path(__file__).resolve().parent.parent / "reserva"
CUMULO = RESERVA / "cumulo_594.sif"
FBIN = RESERVA / "Fbin_hex_100umslit_50ms_nopol_pos_0.sif"
OBLICUA = RESERVA / "oblicua_100umslit_1seg_176deg.sif"
_KEEP_ALIVE = []

pytestmark = pytest.mark.skipif(not CUMULO.exists(), reason="falta reserva/cumulo_594.sif")


# ── Casilleros ──────────────────────────────────────────────────────────────────────────────

def test_the_raman_sif_has_a_signal_and_a_background_slot():
    slots = sp.read_sif_slots(CUMULO)
    assert list(slots) == ["signal", "background"]
    sig, bg = slots["signal"], slots["background"]
    assert sig.data_type == "Counts (Bg Corrected)" and bg.data_type == "Counts"
    assert sig.data.shape == bg.data.shape == (1, 1, 1004)
    assert sig.exposure_s == pytest.approx(3.0) and bg.exposure_s == pytest.approx(3.0)
    assert 300.0 <= float(bg.data.mean()) <= 341.0                  # el bias


@pytest.mark.parametrize("path", [FBIN, OBLICUA])
def test_the_transmittance_files_keep_their_four_slots(path):
    slots = sp.read_sif_slots(path)
    assert list(slots) == ["signal", "reference", "background", "live"]
    assert slots["signal"].data_type == "Transmittance"
    assert slots["reference"].data_type == "Counts (Bg Corrected)"
    assert slots["background"].data_type == "Counts"


@pytest.mark.parametrize("path", [FBIN, OBLICUA])
def test_the_transmittance_analyzer_reads_the_same_as_before(path):
    named, n, ref_bg = sp.parse_all_sif_channels(str(path), return_details=True)
    slots = sp.read_sif_slots(path)
    assert n == 4 and ref_bg is True
    for key, slot in (("transmittance", "signal"), ("reference", "reference"), ("dark", "background"),
                      ("live", "live")):
        np.testing.assert_array_equal(named[key], slots[slot].data)


def test_the_raman_sif_is_signal_and_dark_for_the_transmittance_analyzer():
    """Antes se leía por posición: "transmittance" + "live" (mal)."""
    named, n = sp.parse_all_sif_channels(str(CUMULO))
    assert n == 2 and set(named) == {"live", "dark"}
    assert 300.0 <= float(named["dark"].mean()) <= 341.0


# ── Lectura Raman ───────────────────────────────────────────────────────────────────────────

def test_a_bg_corrected_signal_is_never_subtracted_again():
    r = sp.read_raman_sif(CUMULO)
    sig = sp.read_sif_slots(CUMULO)["signal"].data[0, 0]
    assert r.signal_bg_corrected and not r.subtracted
    np.testing.assert_allclose(r.counts, sig)
    np.testing.assert_allclose(r.raw_signal, sig)
    assert r.background is not None and 300.0 <= float(r.background.mean()) <= 341.0
    assert "ya restó" in r.note
    r2 = sp.read_raman_sif(CUMULO, subtract=True)
    assert not r2.subtracted                                          # ni pidiéndolo


def test_the_axis_comes_from_the_sif_calibration_and_the_laser_is_not_taken():
    r = sp.read_raman_sif(CUMULO)
    assert r.axis_from_calibration and r.wavelengths.shape == (1004,)
    assert r.wavelengths[0] == pytest.approx(609.896 + 0.10388, abs=0.01)   # a0 + a1·1
    assert np.all(np.diff(r.wavelengths) > 0)
    for k in ("Laser Wavelength", "Laser Wavelength (nm)", "Excitation (nm)", "Laser", "Excitation Wavelength"):
        assert k not in r.metadata                                   # el RamanExWavelength (422) no se usa
    assert r.metadata["Exposure Time (secs)"] == "3.0"


def _fake_slots(monkeypatch, sig, bg, sig_type="Counts", sig_exp=1.0, bg_exp=1.0, calib=True):
    info = {"Calibration_data": [500.0, 0.1, 0.0, 0.0]} if calib else {}
    slots = {"signal": sp.SifSlot("signal", np.asarray(sig, float), sig_type, sig_exp, dict(info))}
    if bg is not None:
        slots["background"] = sp.SifSlot("background", np.asarray(bg, float), "Counts", bg_exp, dict(info))
    monkeypatch.setattr(sp, "read_sif_slots", lambda path: slots)


def test_a_raw_signal_is_shown_minus_the_background_by_default(monkeypatch):
    _fake_slots(monkeypatch, np.full((1, 1, 10), 500.0), np.full((1, 1, 10), 300.0))
    r = sp.read_raman_sif("x.sif")
    assert r.subtracted and not r.signal_bg_corrected
    np.testing.assert_allclose(r.counts, 200.0)
    np.testing.assert_allclose(r.raw_signal, 500.0)
    r_raw = sp.read_raman_sif("x.sif", subtract=False)
    assert not r_raw.subtracted
    np.testing.assert_allclose(r_raw.counts, 500.0)


def test_a_background_with_another_exposure_is_not_subtracted(monkeypatch):
    _fake_slots(monkeypatch, np.full((1, 1, 10), 500.0), np.full((1, 1, 10), 300.0), bg_exp=2.0)
    r = sp.read_raman_sif("x.sif")
    assert not r.subtracted and "exposición" in r.note
    np.testing.assert_allclose(r.counts, 500.0)


def test_a_background_of_another_shape_is_not_subtracted(monkeypatch):
    _fake_slots(monkeypatch, np.full((1, 1, 10), 500.0), np.full((1, 1, 8), 300.0))
    r = sp.read_raman_sif("x.sif")
    assert not r.subtracted and "forma" in r.note


def test_rows_and_frames_are_averaged_or_chosen(monkeypatch):
    sig = np.zeros((3, 4, 10))
    for f in range(3):
        for row in range(4):
            sig[f, row] = 100.0 * f + row
    _fake_slots(monkeypatch, sig, None)
    r = sp.read_raman_sif("x.sif")
    assert (r.n_frames, r.n_rows) == (3, 4)
    np.testing.assert_allclose(r.counts, 100.0 + 1.5)                 # todos los cuadros, todas las filas
    r = sp.read_raman_sif("x.sif", frame=2, rows=(0, 2))
    np.testing.assert_allclose(r.counts, 200.0 + 0.5)                 # cuadro 2, filas 0 y 1
    with pytest.raises(ValueError):
        sp.read_raman_sif("x.sif", rows=(3, 3))
    with pytest.raises(ValueError):
        sp.read_raman_sif("x.sif", frame=5)


def test_the_background_is_reduced_with_the_same_rows(monkeypatch):
    sig = np.full((1, 4, 10), 500.0)
    bg = np.zeros((1, 4, 10))
    for row in range(4):
        bg[0, row] = 100.0 * row                                      # 0, 100, 200, 300
    _fake_slots(monkeypatch, sig, bg)
    r = sp.read_raman_sif("x.sif", rows=(2, 4))
    np.testing.assert_allclose(r.background, 250.0)
    np.testing.assert_allclose(r.counts, 250.0)


def test_without_calibration_the_axis_is_pixels_with_a_note(monkeypatch):
    _fake_slots(monkeypatch, np.full((1, 1, 10), 500.0), None, calib=False)
    r = sp.read_raman_sif("x.sif")
    assert not r.axis_from_calibration and "píxeles" in r.note
    np.testing.assert_allclose(r.wavelengths, np.arange(10))


def test_the_generic_loader_accepts_sif_and_text(tmp_path):
    from core.raman_engine import parse_spectrum_file
    meta, wls, counts = parse_spectrum_file(CUMULO)
    assert wls.shape == counts.shape == (1004,) and meta["Exposure Time (secs)"] == "3.0"
    txt = tmp_path / "a.txt"
    txt.write_text("500.0\t10.0\n501.0\t11.0\n502.0\t12.0\n", encoding="utf-8")
    meta, wls, counts = parse_spectrum_file(txt)
    np.testing.assert_allclose(counts, [10.0, 11.0, 12.0])


# ── El analizador ───────────────────────────────────────────────────────────────────────────

@pytest.fixture
def analyzer(monkeypatch):
    from PyQt6.QtWidgets import QApplication, QMessageBox
    from analysis.raman_analyzer import RamanAnalyzerWindow
    QApplication.instance() or QApplication(["pytest"])
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: (_ for _ in ()).throw(AssertionError(a[2])))
    w = RamanAnalyzerWindow()
    _KEEP_ALIVE.append(w)
    return w


def test_the_file_dialogs_offer_sif(analyzer, monkeypatch):
    from PyQt6.QtWidgets import QFileDialog
    seen = []
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: seen.append(a[3]) or ("", ""))
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **k: seen.append(a[3]) or ([], ""))
    analyzer._on_browse_file()
    analyzer.tab_multi._on_load_files()
    analyzer.tab_multi._on_load_reference_file()
    assert len(seen) == 3 and all("*.sif" in f for f in seen), seen


def test_loading_the_raman_sif(analyzer):
    analyzer.set_laser_wavelength(594.0)                            # el láser lo pone el usuario
    analyzer.load_spectrum_file(CUMULO)
    sig = sp.read_sif_slots(CUMULO)["signal"].data[0, 0]
    np.testing.assert_allclose(analyzer.raw_counts, sig)
    assert analyzer.laser_nm == pytest.approx(594.0)               # no lo pisa el 422 del SIF
    assert not analyzer.chk_sif_subtract.isEnabled()                 # Solis ya restó
    assert "ya restó" in analyzer.lbl_sif_info.text()
    assert analyzer.curve_sif_background.getData()[1] is not None
    assert not analyzer.spin_sif_frame.isEnabled() and not analyzer.spin_sif_row_min.isEnabled()


def test_a_raw_sif_can_be_seen_raw_or_minus_background(analyzer, monkeypatch, tmp_path):
    _fake_slots(monkeypatch, np.full((1, 1, 50), 500.0) + np.arange(50), np.full((1, 1, 50), 300.0))
    fake = tmp_path / "raw.sif"
    fake.write_bytes(b"")
    analyzer.load_spectrum_file(fake)
    assert analyzer.chk_sif_subtract.isEnabled() and analyzer.chk_sif_subtract.isChecked()
    np.testing.assert_allclose(analyzer.raw_counts, 200.0 + np.arange(50))
    analyzer.chk_sif_subtract.setChecked(False)
    np.testing.assert_allclose(analyzer.raw_counts, 500.0 + np.arange(50))


def test_the_export_carries_the_background_apart(analyzer, monkeypatch, tmp_path):
    from PyQt6.QtWidgets import QFileDialog, QMessageBox
    analyzer.load_spectrum_file(CUMULO)
    out = tmp_path / "proc.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(out), ""))
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    analyzer._on_export_csv()
    text = out.read_text(encoding="utf-8")
    header = [l for l in text.splitlines() if l.startswith("Wavelength_nm")][0]
    assert header.endswith(",SIF_Background_Counts")
    assert "Solis ya restó" in text
    data = np.loadtxt(out, delimiter=",", comments="#", skiprows=text.splitlines().index(header) + 1)
    assert data.shape[1] == 7
    assert 300.0 <= float(data[:, 6].mean()) <= 341.0


# ── El analizador de transmitancia no resta dos veces (2026-10-02, defecto de DEC-042) ───────

PL400 = RESERVA / "pl_400.sif"


@pytest.mark.skipif(not PL400.exists(), reason="falta reserva/pl_400.sif")
@pytest.mark.parametrize("path", [CUMULO, PL400])
def test_a_bg_corrected_live_is_marked(path):
    spec = sp.read_sif_file(str(path))
    assert spec.live_is_bg_corrected is True
    assert set(spec.channels) == {"live", "dark"}


@pytest.mark.parametrize("path", [FBIN, OBLICUA])
def test_the_live_slot_of_a_transmittance_file_is_not_marked(path):
    assert sp.read_sif_file(str(path)).live_is_bg_corrected is False


@pytest.mark.skipif(not PL400.exists(), reason="falta reserva/pl_400.sif")
def test_the_sif_analyzer_does_not_subtract_the_dark_from_a_corrected_live(monkeypatch):
    from PyQt6.QtWidgets import QApplication, QMessageBox
    import sif_analyzer as sa
    QApplication.instance() or QApplication(["pytest"])
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: (_ for _ in ()).throw(AssertionError(a[2])))
    w = sa.SifAnalyzerWindow()
    _KEEP_ALIVE.append(w)
    w._load_file_list([str(PL400)])
    w.chk_live_sub_dark.setChecked(True)                 # aunque se pida restar
    w._recalculate_all()
    sig = sp.read_sif_slots(PL400)["signal"].data[0, 0]
    assert w.current_live_1d is not None
    np.testing.assert_allclose(np.nanmean(w.current_live_1d), sig.mean(), rtol=0.02)
    assert np.nanmin(w.current_live_1d) > 0                # antes: ≈ −2600 (resta doble)
