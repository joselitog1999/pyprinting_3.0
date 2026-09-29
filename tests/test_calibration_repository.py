# -*- coding: utf-8 -*-
"""Repositorio de calibraciones del Shamrock y observación al arrancar (paso 9 del bloque A, DEC-040).

Contrato (R2-arq §2.5, reconciliado en la Ronda 4 con D-03 y D-04; R4-A-5, R4-B-1, R4-G):
- Archivo local a la PC, **fuera de git**. Es JSON Lines en el que sólo se agregan entradas: nunca se
  reescribe una línea.
- `append` hace flush + fsync, y un `OSError` se propaga: sin registro no hay escritura.
- Clave: (serie, índice de red, líneas/mm, puerto de entrada, puerto de salida).
- Tipos de entrada: OBSERVED, MANUAL_ENTRY, PROPOSED, PRE_WRITE, APPLIED, SOFTWARE_CORRECTION.
- Estado de referencia: el APPLIED(CONFIRMED) más reciente por clave; si no hay, el MANUAL_ENTRY más
  reciente. El detector se compara contra 0 por convención (R4-A-2).
- Al arrancar se lee el equipo sólo con Get*, se registra OBSERVED y se compara. **Nunca se escribe.**
- Un PRE_WRITE sin APPLIED es una escritura sin confirmar (H-17d).
- Ningún veredicto dice "validado" (D-03).
"""
import json
from pathlib import Path

import pytest

from pyspectrum.calibration import repository as repo_mod
from pyspectrum.calibration.repository import (
    CalibrationEntry, CalibrationKey, CalibrationRepository, CalibrationVerdict, observe_spectrograph,
)
from pyspectrum.drivers.shamrock_driver import DEVICE, SHAMROCK_SUCCESS, get_shamrock

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def repo(tmp_path):
    return CalibrationRepository(tmp_path / "cal" / "shamrock_calibration.jsonl")


def _key(g=1, lines=150.0):
    return CalibrationKey(serial="SR-1611", grating_index=g, lines_per_mm=lines, entrance_port=1, exit_port=0)


# ── Archivo ───────────────────────────────────────────────────────────────────

def test_repository_rejects_a_path_inside_the_git_tree():
    with pytest.raises(ValueError):
        CalibrationRepository(REPO_ROOT / "pyspectrum" / "calibration" / "shamrock_calibration.jsonl")


def test_default_path_is_outside_the_repo_and_overridable(monkeypatch, tmp_path):
    import config
    monkeypatch.setattr(config, "SHAMROCK_CALIBRATION_PATH", str(tmp_path / "x.jsonl"))
    assert repo_mod.default_repository_path() == tmp_path / "x.jsonl"
    monkeypatch.setattr(config, "SHAMROCK_CALIBRATION_PATH", None)
    default = repo_mod.default_repository_path()
    assert default.name == "shamrock_calibration.jsonl"
    assert REPO_ROOT not in default.resolve().parents


def test_append_only_one_json_line_per_entry_with_common_fields(repo):
    repo.append(CalibrationEntry.manual_entry(_key(), 87, source="leído del equipo (BANCO-25)"))
    repo.append(CalibrationEntry.manual_entry(_key(2, 1200.0), 195, source="leído del equipo (BANCO-25)"))
    lines = repo.path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    for field in ("schema_version", "record_id", "kind", "ts", "operator", "software", "method", "note"):
        assert field in first
    assert first["kind"] == "MANUAL_ENTRY" and first["provenance"] == "EXPERIMENTAL"
    before = lines[0]
    repo.append(CalibrationEntry.manual_entry(_key(), 88, source="otra lectura"))
    assert repo.path.read_text(encoding="utf-8").splitlines()[0] == before      # nunca se reescribe


def test_append_failure_propagates(repo, monkeypatch):
    def boom(*a, **k):
        raise OSError("disco lleno")
    monkeypatch.setattr(repo_mod.os, "fsync", boom)
    with pytest.raises(OSError):
        repo.append(CalibrationEntry.manual_entry(_key(), 87, source="x"))


def test_a_truncated_last_line_is_skipped_and_reported(repo):
    repo.append(CalibrationEntry.manual_entry(_key(), 87, source="x"))
    with open(repo.path, "a", encoding="utf-8") as fh:
        fh.write('{"kind": "APPLI')                          # corte de luz en medio de una línea
    hist = repo.history()
    assert len(hist) == 1 and repo.unreadable_lines == 1


# ── Estado de referencia ──────────────────────────────────────────────────────

def test_reference_prefers_the_latest_confirmed_write_over_manual_entries(repo):
    assert repo.reference_state(_key()) is None
    repo.append(CalibrationEntry.manual_entry(_key(), 87, source="Solis"))
    assert repo.reference_state(_key()).value == 87
    repo.append(CalibrationEntry.applied(_key(), transaction_id="t1", requested=90, readback=90,
                                         outcome="CONFIRMED", code_write=SHAMROCK_SUCCESS,
                                         code_read=SHAMROCK_SUCCESS, source_record_id=None))
    repo.append(CalibrationEntry.manual_entry(_key(), 70, source="posterior, pero manual"))
    ref = repo.reference_state(_key())
    assert ref.value == 90 and ref.kind == "APPLIED"
    repo.append(CalibrationEntry.applied(_key(), transaction_id="t2", requested=95, readback=91,
                                         outcome="MISMATCH", code_write=SHAMROCK_SUCCESS,
                                         code_read=SHAMROCK_SUCCESS, source_record_id=None))
    assert repo.reference_state(_key()).value == 90                             # un MISMATCH no es referencia


def test_key_matches_lines_per_mm_with_tolerance_and_the_ports_exactly(repo):
    repo.append(CalibrationEntry.manual_entry(_key(), 87, source="x"))
    near = CalibrationKey("SR-1611", 1, 150.3, 1, 0)
    assert repo.reference_state(near).value == 87
    other_port = CalibrationKey("SR-1611", 1, 150.0, 0, 0)
    assert repo.reference_state(other_port) is None
    other_serial = CalibrationKey("SR-9999", 1, 150.0, 1, 0)
    assert repo.reference_state(other_serial) is None


def test_orphan_pre_write_is_reported(repo):
    repo.append(CalibrationEntry.pre_write(_key(), transaction_id="t9", offset_read=87, requested=90,
                                           source_record_id=None))
    assert [e.transaction_id for e in repo.orphan_pre_writes()] == ["t9"]
    repo.append(CalibrationEntry.applied(_key(), transaction_id="t9", requested=90, readback=90,
                                         outcome="CONFIRMED", code_write=SHAMROCK_SUCCESS,
                                         code_read=SHAMROCK_SUCCESS, source_record_id=None))
    assert repo.orphan_pre_writes() == []


def test_no_verdict_says_validated():
    names = [v.name for v in CalibrationVerdict]
    assert names == ["ACEPTADA", "ACEPTADA_CON_RESERVA", "RECHAZADA", "EN_SECO", "CANCELADA"]
    assert not any("VALID" in n for n in names)


# ── Observación al arrancar ───────────────────────────────────────────────────

class _RecordingShamrock:
    """Registra toda llamada que no sea de lectura."""
    def __init__(self, inner):
        self._inner, self.writes = inner, []

    def __getattr__(self, name):
        attr = getattr(self._inner, name)
        if callable(attr) and not (name.startswith("ShamrockGet") or name.startswith("get_")
                                   or name.startswith("ShamrockAt") or name.startswith("is_")):
            def rec(*a, **k):
                self.writes.append(name)
                return attr(*a, **k)
            return rec
        return attr


@pytest.fixture
def spec():
    s = get_shamrock(force_mock=True)
    s._grating_offsets = {1: 87, 2: 195, 3: 60}
    s._detector_offset = 0
    return s


def test_first_start_records_observed_and_writes_nothing(repo, spec):
    rec = _RecordingShamrock(spec)
    report = observe_spectrograph(rec, repo)
    assert rec.writes == []
    assert report.first_use and report.observed_record_id
    [obs] = [e for e in repo.history() if e.kind == "OBSERVED"]
    assert obs.values["gratings"]["1"]["offset"] == 87
    assert obs.values["gratings"]["2"]["offset"] == 195
    assert obs.values["gratings"]["3"]["offset"] == 60
    assert obs.values["detector_offset"]["value"] == 0
    assert {r.status for r in report.rows if r.grating_index in (1, 2)} == {"SIN_REFERENCIA"}


def test_equal_and_different_offsets_are_classified(repo, spec):
    serial = spec.ShamrockGetSerialNumber(DEVICE)[1]
    repo.append(CalibrationEntry.manual_entry(CalibrationKey(serial, 1, 150.0, 1, 0), 85, source="Solis (R4-3)"))
    repo.append(CalibrationEntry.manual_entry(CalibrationKey(serial, 2, 1200.0, 1, 0), 195, source="BANCO-25"))
    report = observe_spectrograph(spec, repo, entrance_port=1, exit_port=0)
    by = {r.grating_index: r for r in report.rows}
    assert by[1].status == "DISTINTO" and by[1].device == 87 and by[1].reference == 85
    assert by[2].status == "IGUAL"
    assert report.has_warnings
    assert any("red 1 (150 l/mm): equipo 87 pasos, archivo 85 pasos" in w for w in report.warnings())


def test_unreadable_offset_is_unknown_never_the_old_file_value(repo, spec, monkeypatch):
    real = spec.ShamrockGetGratingOffset
    monkeypatch.setattr(spec, "ShamrockGetGratingOffset",
                        lambda device=DEVICE, grating=1: (20201, 0) if grating == 2 else real(device, grating))
    report = observe_spectrograph(spec, repo)
    by = {r.grating_index: r for r in report.rows}
    assert by[2].status == "NO_LEIDO" and by[2].device is None
    assert any("red 2" in w and "desconocido" in w for w in report.warnings())


def test_detector_is_compared_against_zero_by_convention(repo, spec):
    spec._detector_offset = 5
    report = observe_spectrograph(spec, repo)
    assert report.detector_status == "DISTINTO"
    assert any("detector" in w and "0 por convención" in w for w in report.warnings())


def test_startup_reports_orphan_pre_write(repo, spec):
    serial = spec.ShamrockGetSerialNumber(DEVICE)[1]
    repo.append(CalibrationEntry.pre_write(CalibrationKey(serial, 1, 150.0, 1, 0), transaction_id="t7",
                                           offset_read=87, requested=90, source_record_id=None))
    report = observe_spectrograph(spec, repo)
    assert any("escritura" in w and "sin confirmar" in w for w in report.warnings())


def test_startup_survives_a_repository_that_cannot_be_written(repo, spec, monkeypatch):
    monkeypatch.setattr(repo, "append", lambda e: (_ for _ in ()).throw(OSError("sin permiso")))
    report = observe_spectrograph(spec, repo)
    assert report.append_error and any("no se pudo registrar" in w.lower() for w in report.warnings())
