# -*- coding: utf-8 -*-
"""Corrección fina por software (paso 14c; D-04; R4-B 2; R4-C-6; R3-gui §1.6 y §4.6).

- [Aplicar corrección fina] agrega una entrada SOFTWARE_CORRECTION con el `record_id` de la calibración de
  origen. No escribe al equipo. Sólo desde ACEPTADA o CON RESERVA: nunca RECHAZADA, EN_SECO ni CANCELADA.
- Al arrancar, la corrección de una red vale sólo si el offset leído es el mismo con el que se midió, y
  coinciden serie, puertos y geometría. Si no, queda SUSPENDIDA con el motivo, y el arranque lo avisa.
- Se guarda aparte del eje λ, como metadato: el dato crudo no cambia.
"""
import pytest

from pyspectrum.calibration import repository as rp
from pyspectrum.calibration.repository import (CalibrationEntry, CalibrationKey, CalibrationRepository,
                                               apply_fine_correction, active_software_correction)

KEY = CalibrationKey("SR-1611", 1, 150.0, 1, 0)
GEOM = {"n_px": 1004, "pixel_width_um": 8.0}


def _calibration(repo, verdict="ACEPTADA_CON_RESERVA", offset=87, c_sw=-0.41, key=KEY):
    e = CalibrationEntry("PROPOSED", key, method="auto_offset_laser_leak_v1",
                         values={"verdict": verdict, "c_sw_px": c_sw, "u_c_sw_px": 0.2, "grating_offset_after": offset,
                                 "declared_geometry": GEOM, "dry_run": True})
    repo.append(e)
    return e


@pytest.fixture
def repo(tmp_path):
    return CalibrationRepository(tmp_path / "cal.jsonl")


def test_applying_adds_a_software_correction_tied_to_its_calibration(repo):
    cal = _calibration(repo)
    entry = apply_fine_correction(repo, cal)
    assert entry.kind == "SOFTWARE_CORRECTION" and entry.key == KEY
    v = entry.values
    assert v["source_record_id"] == cal.record_id and v["c_sw_px"] == -0.41 and v["grating_offset"] == 87
    assert v["c_sw_convention"] == "lambda(p) = lambda_SDK(p + c_sw)"
    assert repo.history()[-1].record_id == entry.record_id


@pytest.mark.parametrize("verdict", ["RECHAZADA", "EN_SECO", "CANCELADA"])
def test_it_is_refused_from_a_verdict_that_does_not_allow_it(repo, verdict):
    with pytest.raises(ValueError):
        apply_fine_correction(repo, _calibration(repo, verdict=verdict))
    assert not [e for e in repo.history() if e.kind == "SOFTWARE_CORRECTION"]


def test_it_applies_when_offset_and_geometry_match(repo):
    apply_fine_correction(repo, _calibration(repo))
    st = active_software_correction(repo, KEY, offset_read=87, geometry=GEOM)
    assert st.status == "APLICADA" and st.c_sw_px == -0.41 and st.record_id


def test_it_is_suspended_when_the_offset_changed(repo):
    apply_fine_correction(repo, _calibration(repo))
    st = active_software_correction(repo, KEY, offset_read=90, geometry=GEOM)
    assert st.status == "SUSPENDIDA" and "87" in st.reason and "90" in st.reason


def test_it_is_suspended_when_the_geometry_changed(repo):
    apply_fine_correction(repo, _calibration(repo))
    st = active_software_correction(repo, KEY, offset_read=87, geometry={"n_px": 1024, "pixel_width_um": 13.0})
    assert st.status == "SUSPENDIDA" and "geometría" in st.reason


def test_another_spectrograph_or_port_has_none(repo):
    apply_fine_correction(repo, _calibration(repo))
    other = CalibrationKey("SR-9999", 1, 150.0, 1, 0)
    assert active_software_correction(repo, other, offset_read=87, geometry=GEOM).status == "NINGUNA"
    assert active_software_correction(repo, CalibrationKey("SR-1611", 1, 150.0, 2, 0), offset_read=87,
                                      geometry=GEOM).status == "NINGUNA"


def test_the_latest_correction_wins(repo):
    apply_fine_correction(repo, _calibration(repo, c_sw=-0.41))
    apply_fine_correction(repo, _calibration(repo, c_sw=+0.12))
    assert active_software_correction(repo, KEY, offset_read=87, geometry=GEOM).c_sw_px == 0.12


class _Spec:
    """Shamrock mínimo para observe_spectrograph."""
    def __init__(self, offset):
        self.offset = offset

    def ShamrockGetSerialNumber(self, d):
        return 20202, "SR-1611"

    def ShamrockGetFlipper(self, d, f):
        return 20202, {1: 1, 2: 0}[f]

    def ShamrockGetNumberGratings(self, d):
        return 20202, 1

    def ShamrockGetGratingInfo(self, d, g):
        return 20202, 150.0, "800", 0, 0

    def ShamrockGetGratingOffset(self, d, g):
        return 20202, self.offset

    def ShamrockGetDetectorOffset(self, d):
        return 20202, 0

    def ShamrockGetSlitZeroPosition(self, d, i):
        return 20202, 0

    def ShamrockGetNumberPixels(self, d):
        return 20202, 1004

    def ShamrockGetPixelWidth(self, d):
        return 20202, 8.0


def test_startup_reports_a_suspended_correction(repo):
    apply_fine_correction(repo, _calibration(repo))
    ok = rp.observe_spectrograph(_Spec(87), repo)
    assert [c.status for c in ok.software_corrections] == ["APLICADA"]
    assert not any("corrección fina" in w for w in ok.warnings())
    bad = rp.observe_spectrograph(_Spec(90), repo)
    assert [c.status for c in bad.software_corrections] == ["SUSPENDIDA"]
    assert any("corrección fina" in w and "suspendida" in w for w in bad.warnings())
