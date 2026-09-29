# -*- coding: utf-8 -*-
"""Calibraciones: offsets de sólo lectura y registro en el archivo (pasos 9 y 10, Ronda 3 §1.8, DEC-040).

- Ninguna escritura sale de un botón directo: "Escribir Rejilla", "Escribir Detector" y "Escribir SDK"
  desaparecen (G-10). El offset entero se escribe sólo con la transacción, desde la rutina (R4-B-1).
- Lo mostrado es lo leído, con su marca [L] y la hora; una lectura fallida se muestra "desconocido",
  nunca el valor viejo (R2-inst S8, §1.1).
- Cargar un archivo .txt no cambia lo mostrado como leído: los offsets del archivo son informativos.
- [Registrar lo leído en el archivo] agrega entradas MANUAL_ENTRY (EXPERIMENTAL). No toca el equipo.
- El historial se agrega arriba (`insertRow(0)`), sin reconstruir la tabla (§4.1).
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYPRINTING_SAFE", "1")

import pytest
from PyQt6 import QtWidgets

from pyspectrum.calibration.repository import CalibrationRepository
from pyspectrum.drivers.shamrock_driver import DEVICE, get_shamrock
from pyspectrum.modules import calibration_dock as dock_mod
from pyspectrum.modules.calibration_dock import CalibrationBackend, CalibrationFrontend

_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["pytest"])


@pytest.fixture
def dock(tmp_path, monkeypatch):
    monkeypatch.setattr(dock_mod, "CALIBRATION_TXT_FILE", tmp_path / "no_existe.txt")
    spec = get_shamrock(force_mock=True)
    spec._grating_offsets = {1: 87, 2: 195, 3: 60}
    spec._detector_offset = 0
    spec._slit_zero_pos = -45
    repo = CalibrationRepository(tmp_path / "cal.jsonl")
    fe = CalibrationFrontend()
    be = CalibrationBackend(spectrometer=spec, repository=repo)
    be.make_connection(fe)
    yield fe, be, spec, repo
    fe.deleteLater()


def test_no_direct_write_controls_remain(dock):
    fe, be, spec, repo = dock
    texts = [b.text() for b in fe.findChildren(QtWidgets.QPushButton)]
    assert not [t for t in texts if "Escribir" in t]
    for sig in ("setGratingOffsetSignal", "setDetectorOffsetSignal", "setSlitZeroPosSignal"):
        assert not hasattr(fe, sig)
    for meth in ("set_grating_offset", "set_detector_offset", "set_slit_zero_position"):
        assert not hasattr(be, meth)
    for spin in (fe.spin_grating_off, fe.spin_detector_off, fe.spin_slit_zero):
        assert spin.isReadOnly()


def test_shown_values_are_the_read_ones_with_their_mark(dock):
    fe, be, spec, repo = dock
    fe.combo_grating.setCurrentIndex(0)
    fe._on_read_all_offsets()
    assert fe.spin_grating_off.value() == 87 and "[L" in fe.lbl_grating_mark.text()
    fe.combo_grating.setCurrentIndex(1)
    assert fe.spin_grating_off.value() == 195
    assert fe.spin_detector_off.value() == 0 and "[L" in fe.lbl_detector_mark.text()
    assert fe.spin_slit_zero.value() == -45


def test_failed_read_shows_unknown_not_the_old_value(dock, monkeypatch):
    fe, be, spec, repo = dock
    fe.combo_grating.setCurrentIndex(0)
    fe._on_read_all_offsets()
    monkeypatch.setattr(spec, "ShamrockGetGratingOffset", lambda device=DEVICE, grating=1: (20201, 0))
    fe._on_read_all_offsets()
    assert fe.spin_grating_off.text() == "desconocido"
    assert "no leído" in fe.lbl_grating_mark.text() and "20201" in fe.lbl_grating_mark.text()
    assert be.grating_offsets.get(1) is None


def test_loading_a_txt_file_does_not_change_what_is_shown_as_read(dock, tmp_path):
    fe, be, spec, repo = dock
    fe.combo_grating.setCurrentIndex(0)
    fe._on_read_all_offsets()
    txt = tmp_path / "cal.txt"
    txt.write_text("[OFFSETS_HARDWARE_SDK]\ngrating_1_offset_steps = 12\ngrating_2_offset_steps = -35\n"
                   "detector_offset_steps = 5\n", encoding="utf-8")
    assert be.load_calibration_from_txt(str(txt))
    assert be.grating_offsets[1] == 87 and be.detector_offset == 0
    assert fe.spin_grating_off.value() == 87 and fe.spin_detector_off.value() == 0
    assert be.file_offsets == {"grating_1": 12, "grating_2": -35, "detector": 5}


def test_register_read_adds_manual_entries_and_touches_nothing(dock):
    fe, be, spec, repo = dock
    writes = []
    for name in ("ShamrockSetGratingOffset", "ShamrockSetDetectorOffset", "ShamrockSetSlitZeroPosition"):
        setattr(spec, name, lambda *a, _n=name, **k: writes.append(_n))
    rows_before = fe.table_history.rowCount()
    fe.btn_register_read.click()
    manual = [e for e in repo.history() if e.kind == "MANUAL_ENTRY"]
    assert sorted((e.key.grating_index, e.values["offset"]) for e in manual) == [(1, 87), (2, 195)]
    assert all(e.values["provenance"] == "EXPERIMENTAL" for e in manual)
    assert writes == []
    assert fe.table_history.rowCount() == rows_before + 2
    assert fe.table_history.item(0, 1).text() == "MANUAL_ENTRY"
    for name in ("ShamrockSetGratingOffset", "ShamrockSetDetectorOffset", "ShamrockSetSlitZeroPosition"):
        delattr(spec, name)


def test_saved_txt_holds_read_values_and_unknown_as_such(dock, tmp_path, monkeypatch):
    fe, be, spec, repo = dock
    be.read_initial_values()
    out = tmp_path / "saved.txt"
    be.save_calibration_to_txt(str(out))
    text = out.read_text(encoding="utf-8")
    assert "grating_1_offset_steps = 87" in text and "grating_2_offset_steps = 195" in text
    monkeypatch.setattr(spec, "ShamrockGetDetectorOffset", lambda device=DEVICE: (20201, 0))
    be.read_initial_values()
    be.save_calibration_to_txt(str(out))
    assert "detector_offset_steps = desconocido" in out.read_text(encoding="utf-8")
    assert be.load_calibration_from_txt(str(out))            # el lector tolera "desconocido"


def test_window_startup_observes_the_shamrock_and_warns_without_writing(monkeypatch, tmp_path):
    """Paso 9 al arrancar: lectura con Get*, OBSERVED en el archivo y aviso no modal si difiere."""
    import config
    from pyspectrum.calibration.repository import CalibrationEntry, CalibrationKey, get_repository
    from pyspectrum.modules.hardware_session import hardware_session
    from pyspectrum.window import PySpectrumWindow
    monkeypatch.setattr(config, "SHAMROCK_CALIBRATION_PATH", str(tmp_path / "startup.jsonl"))
    monkeypatch.setattr(QtWidgets.QMessageBox, "question", lambda *a, **k: QtWidgets.QMessageBox.StandardButton.No)
    monkeypatch.setattr(QtWidgets.QMessageBox, "critical", lambda *a, **k: None)
    hardware_session.clear_emergency()
    spec = get_shamrock(force_mock=True)
    spec._grating_offsets = {1: 87, 2: 195, 3: 60}
    serial = spec.ShamrockGetSerialNumber(DEVICE)[1]
    ports = (spec.ShamrockGetFlipper(DEVICE, 1)[1], spec.ShamrockGetFlipper(DEVICE, 2)[1])
    get_repository().append(CalibrationEntry.manual_entry(CalibrationKey(serial, 1, 150.0, *ports), 85,
                                                          source="Solis (R4-3)"))
    writes = []
    for name in ("ShamrockSetGratingOffset", "ShamrockSetDetectorOffset", "ShamrockSetSlitZeroPosition"):
        monkeypatch.setattr(spec, name, lambda *a, _n=name, **k: writes.append(_n))
    win = PySpectrumWindow()
    try:
        assert writes == []
        assert [e.kind for e in get_repository().history()].count("OBSERVED") == 1
        assert not win.lbl_calibration_warning.isHidden()
        assert "equipo 87 pasos, archivo 85 pasos" in win.lbl_calibration_warning.toolTip()
    finally:
        win.left_panel._refresh_timer.stop()
        win.close()
