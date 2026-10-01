# -*- coding: utf-8 -*-
"""La corrección fina `c_sw` en el metadato de cada espectro guardado (R3-gui §4.6, pendiente del paso 14).

Contrato aprobado en la Ronda 3 del bloque A:
- se muestra **siempre**, con su veredicto y su fecha: `c_sw_px`, `c_sw_convention`, `record_id`;
- un espectro sin ella no se puede reinterpretar, porque Solis y el legado no la ven (R4-B 2);
- no mueve el eje λ guardado: es metadato (R4-C-6);
- vale con la misma regla del arranque (§4.6): mismo offset, serie, puertos y geometría; si no, SUSPENDIDA
  con el motivo. Se calcula al guardar, con lo que el equipo tiene en ese momento.
"""
import json

import numpy as np
import pytest

from pyspectrum.calibration import repository as rp
from pyspectrum.calibration.repository import (CalibrationEntry, CalibrationKey, CalibrationRepository,
                                               apply_fine_correction, correction_header_lines,
                                               spectrum_software_correction, write_correction_attrs)

KEY = CalibrationKey("SR-1611", 1, 150.0, 1, 0)
GEOM = {"n_px": 1004, "pixel_width_um": 8.0}
OK = 20202


class _Spec:
    def __init__(self, *, serial=(OK, "SR-1611"), grating=1, offset=87, lines=150.0, n_px=1004, width=8.0):
        self.serial, self.grating, self.offset, self.lines = serial, grating, offset, lines
        self.n_px, self.width = n_px, width

    def ShamrockGetSerialNumber(self, dev): return self.serial
    def ShamrockGetFlipper(self, dev, flipper): return (OK, 1 if flipper == 1 else 0)
    def ShamrockGetGrating(self, dev): return (OK, self.grating)
    def ShamrockGetGratingInfo(self, dev, g): return (OK, self.lines, "500nm", 0)
    def ShamrockGetGratingOffset(self, dev, g): return (OK, self.offset)
    def ShamrockGetNumberPixels(self, dev): return (OK, self.n_px)
    def ShamrockGetPixelWidth(self, dev): return (OK, self.width)


@pytest.fixture
def repo(tmp_path):
    return CalibrationRepository(tmp_path / "cal.jsonl")


def _correct(repo, c_sw=-0.41, offset=87):
    cal = CalibrationEntry("PROPOSED", KEY, method="auto_offset_laser_leak_v1",
                           values={"verdict": "ACEPTADA", "c_sw_px": c_sw, "u_c_sw_px": 0.2,
                                   "grating_offset_after": offset, "declared_geometry": GEOM, "dry_run": True})
    repo.append(cal)
    return cal, apply_fine_correction(repo, cal)


def test_applied_correction_is_reported_with_its_provenance(repo):
    cal, entry = _correct(repo)
    m = spectrum_software_correction(_Spec(), repo)
    assert m["c_sw_status"] == "APLICADA"
    assert m["c_sw_px"] == -0.41 and m["u_c_sw_px"] == 0.2
    assert m["c_sw_convention"] == "lambda(p) = lambda_SDK(p + c_sw)"
    assert m["c_sw_record_id"] == entry.record_id and m["c_sw_source_record_id"] == cal.record_id
    assert m["c_sw_ts"] and m["c_sw_grating"] == 1
    assert "no aplicada al eje" in m["c_sw_policy"]


def test_none_when_there_is_no_correction(repo):
    m = spectrum_software_correction(_Spec(), repo)
    assert m["c_sw_status"] == "NINGUNA" and m["c_sw_px"] is None


def test_suspended_when_the_offset_changed_since_it_was_measured(repo):
    _correct(repo, offset=87)
    m = spectrum_software_correction(_Spec(offset=90), repo)
    assert m["c_sw_status"] == "SUSPENDIDA" and "87" in m["c_sw_reason"] and m["c_sw_px"] == -0.41


def test_the_active_grating_decides(repo):
    _correct(repo)
    assert spectrum_software_correction(_Spec(grating=2), repo)["c_sw_status"] == "NINGUNA"


def test_mirror_grating_does_not_apply(repo):
    m = spectrum_software_correction(_Spec(lines=0.0, grating=3), repo)
    assert m["c_sw_status"] == "NO_APLICA" and "espejo" in m["c_sw_reason"]


def test_unknown_when_the_spectrograph_cannot_be_identified(repo):
    _correct(repo)
    m = spectrum_software_correction(_Spec(serial=(20201, "")), repo)
    assert m["c_sw_status"] == "DESCONOCIDA" and "serie" in m["c_sw_reason"]
    m = spectrum_software_correction(None, repo)
    assert m["c_sw_status"] == "DESCONOCIDA"


def test_a_failing_spectrograph_never_breaks_a_save(repo):
    class Broken:
        def __getattr__(self, name):
            def fail(*a):
                raise RuntimeError("USB")
            return fail
    m = spectrum_software_correction(Broken(), repo)
    assert m["c_sw_status"] == "DESCONOCIDA"


def test_header_lines_and_h5_attrs_carry_every_field(repo, tmp_path):
    _correct(repo)
    m = spectrum_software_correction(_Spec(), repo)
    lines = correction_header_lines(m)
    assert "c_sw_status: APLICADA" in lines and any(l.startswith("c_sw_px: -0.41") for l in lines)
    assert all(": " in l for l in lines) and len(lines) == len(m)
    h5py = pytest.importorskip("h5py")
    with h5py.File(tmp_path / "a.h5", "w") as f:
        write_correction_attrs(f.attrs, m)
        m2 = spectrum_software_correction(_Spec(grating=2), repo)
    with h5py.File(tmp_path / "a.h5", "r") as f:
        assert f.attrs["c_sw_status"] == "APLICADA" and f.attrs["c_sw_px"] == -0.41
    with h5py.File(tmp_path / "b.h5", "w") as f:
        write_correction_attrs(f.attrs, m2)                   # None se guarda como texto vacío
    with h5py.File(tmp_path / "b.h5", "r") as f:
        assert f.attrs["c_sw_px"] == ""


# ── Cada lugar que guarda un espectro lo lleva ──────────────────────────────────────────────

@pytest.fixture
def corrected(monkeypatch, repo):
    """El repositorio global apunta a uno temporal con una corrección aplicada para la red 1."""
    _correct(repo)
    monkeypatch.setattr(rp, "get_repository", lambda: repo)
    return _Spec()


def test_step_and_glue_window_npz(tmp_path, corrected):
    from pyspectrum.modules import step_glue_engine as eng
    from pyspectrum.modules.acquisition import Frame
    req = type("R", (), {"exposure_s": 0.1, "grating": 1, "read_mode": 0, "em_gain": 0})()
    plan = type("P", (), {"window_nm": 100.0, "window_source": "x"})()
    path = eng._save_window(tmp_path, 0, 600.0, 600.0, np.arange(4.0), np.ones(4),
                            Frame(np.ones(4), 0.1, 1, 0.0, 0.1), [], False, req, plan,
                            correction=spectrum_software_correction(corrected))
    meta = json.loads(str(np.load(path)["metadata"]))
    assert meta["c_sw_status"] == "APLICADA" and meta["c_sw_px"] == -0.41


def test_text_savers_write_the_header(tmp_path, corrected):
    from pyspectrum.calibration.repository import correction_header_text
    text = correction_header_text(corrected)
    assert "c_sw_status: APLICADA" in text and "c_sw_convention: lambda(p) = lambda_SDK(p + c_sw)" in text


def test_luminescence_growth_and_glued_spectra_headers(tmp_path, corrected):
    from pyspectrum.modules.routines import growth_kinetics, luminescence
    lum = luminescence.LuminescenceBackend.__new__(luminescence.LuminescenceBackend)
    lum.spectrometer = corrected
    lum.run_dark = None
    lum.grid_dark = type("D", (), {"header_text": lambda self, d, folder: "background_id: ninguno"})()
    lum._save_node_result(0, np.arange(3.0), np.ones(3), str(tmp_path / "lum"), "FVB")
    gro = growth_kinetics.GrowthKineticsBackend.__new__(growth_kinetics.GrowthKineticsBackend)
    gro.spectrometer = corrected
    gro.run_dark = None
    gro.grid_dark = type("D", (), {"header_text": lambda self, d, folder: "background_id: ninguno"})()
    gro._save_node_result(0, np.arange(3.0), np.ones(3), [0.0], [600.0], str(tmp_path / "gro"))
    for p in (tmp_path / "lum" / "LuminescenceNode_000_spectrum.txt",
              tmp_path / "gro" / "GrowthNode_000_final_spectrum.txt"):
        assert "c_sw_status: APLICADA" in p.read_text(encoding="utf-8"), p
    np.testing.assert_allclose(np.loadtxt(tmp_path / "lum" / "LuminescenceNode_000_spectrum.txt"),
                               np.column_stack([np.arange(3.0), np.ones(3)]))   # el dato no cambia


def test_raman_2d_export_and_exploration_h5(tmp_path, corrected):
    h5py = pytest.importorskip("h5py")
    from pyspectrum.ui.raman_2d_inspector import export_raman_2d_to_hdf5
    m = spectrum_software_correction(corrected)
    p = export_raman_2d_to_hdf5(str(tmp_path / "r.h5"), np.ones((4, 5)), np.arange(5.0), (0, 2), extra_attrs=m)
    with h5py.File(p, "r") as f:
        assert f.attrs["c_sw_status"] == "APLICADA"
    from pyspectrum.drivers import specular_interlock as si
    from pyspectrum.modules import exploration_analysis as ea
    p = ea.save_exploration_h5(tmp_path / "e.h5", raw=np.ones((4, 5)), background=None, subtract=False,
                               axis=ea.profile_axis(si.SPECULAR, None, 5), cuts={}, metadata={},
                               full_info={}, correction=m)
    with h5py.File(p, "r") as f:
        assert f.attrs["c_sw_status"] == "APLICADA" and f.attrs["c_sw_px"] == -0.41


def test_glued_spectrum_txt_and_npz(tmp_path, corrected):
    from pyspectrum.modules.step_and_glue import Backend
    be = Backend.__new__(Backend)
    be.spectrometer = corrected
    be._last_wave, be._last_spec, be._last_norm = np.arange(3.0), np.ones(3), np.array([])
    be.last_result, be.subtract_dark = None, True
    be.save_spectrum(str(tmp_path / "g.txt"))
    assert "c_sw_status: APLICADA" in (tmp_path / "g.txt").read_text(encoding="utf-8")
    np.testing.assert_allclose(np.loadtxt(tmp_path / "g.txt"), np.column_stack([np.arange(3.0), np.ones(3)]))
    be.save_spectrum(str(tmp_path / "g.npz"))
    assert json.loads(str(np.load(tmp_path / "g.npz")["metadata"]))["c_sw_px"] == -0.41


def test_static_raman_txt(tmp_path, corrected):
    from pyspectrum.modules.static_raman import StaticRamanBackend
    be = StaticRamanBackend.__new__(StaticRamanBackend)
    be.spectrometer = corrected
    msgs = []
    be.statusMessageSignal = type("S", (), {"emit": lambda self, m: msgs.append(m)})()
    be.save_spectrum_to_file(str(tmp_path / "r.txt"), {"Laser_Excitacion_nm": 532.0, "_raw_counts": [1.0, 2.0],
                                                       "_raw_wl": [540.0, 541.0]})
    text = (tmp_path / "r.txt").read_text(encoding="utf-8")
    assert "# c_sw_status: APLICADA" in text and "# c_sw_px: -0.41" in text, msgs


def test_hyperspectral_cube(tmp_path, corrected):
    h5py = pytest.importorskip("h5py")
    from pyspectrum.modules.hyperspectral_confocal import Backend
    be = Backend.__new__(Backend)
    be.spectrometer = corrected
    be.data_dir = str(tmp_path)
    be._datacube = np.zeros((2, 2, 3), np.float32)
    be._failed = np.zeros((2, 2), bool)
    be.map_2d = np.zeros((2, 2), np.float32)
    be.xs, be.ys, be.wave_axis = np.arange(2.0), np.arange(2.0), np.arange(3.0)
    be._exp_time, be._complete, be.points_done = 0.1, True, 4
    be.run_dark = None
    be.statusSignal = type("S", (), {"emit": lambda self, m: None})()
    be._save()
    with h5py.File(be._saved_path, "r") as f:
        assert f.attrs["c_sw_status"] == "APLICADA" and f.attrs["c_sw_px"] == -0.41


def test_raman_backend_gives_the_inspector_its_correction(tmp_path, corrected):
    h5py = pytest.importorskip("h5py")
    from PyQt6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication(["pytest"])
    from pyspectrum.modules.static_raman import StaticRamanBackend, StaticRamanWidget
    from pyspectrum.ui.raman_2d_inspector import Raman2DInspectorWidget
    from pyspectrum.drivers.andor_ccd_driver import get_andor_ccd
    be = StaticRamanBackend(get_andor_ccd(force_mock=True), corrected)
    widget, inspector = StaticRamanWidget(), Raman2DInspectorWidget()
    _KEEP_RAMAN.extend([be, widget, inspector])
    be.make_connection(widget, inspector)
    inspector.frame_2d, inspector.wavelengths, inspector.roi_rows = np.ones((4, 5)), np.arange(5.0), (0, 2)
    inspector.export_hdf5_to_path(str(tmp_path / "i.h5"))
    with h5py.File(tmp_path / "i.h5", "r") as f:
        assert f.attrs["c_sw_status"] == "APLICADA"


_KEEP_RAMAN = []
