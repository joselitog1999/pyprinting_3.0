# -*- coding: utf-8 -*-
"""El fondo en las rutinas de grilla (R4-N; DEC-040): GridRunner y la fila "Fondo".

- El oscuro se toma con el mismo modo que `spectrum_1d` va a usar (FVB, o Single-Track si la cámara está en
  Single-Track), la exposición de la medición y, por defecto, un cuadro (como la medición).
- Se reutiliza si las condiciones no cambiaron; con "obturador cerrado" se toma solo y el obturador vuelve a
  abrirse (verificado) antes de medir; con "todo apagado" nunca se toma solo.
- La fila muestra el estado con el motivo y resta sólo para mostrar.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYPRINTING_SAFE", "1")

import numpy as np
import pytest
from PyQt6 import QtWidgets

from pyspectrum.drivers.andor_ccd_driver import READ_MODE_FVB, READ_MODE_IMAGE, READ_MODE_SINGLE_TRACK, get_andor_ccd
from pyspectrum.modules.routines import grid_runner as gr
from pyspectrum.modules.routines.grid_runner import GridAbort, GridRunner, expected_1d_conditions
from pyspectrum.services import procedure_background as pb

_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["pytest"])
_KEEP = []


class _Spec:
    def __init__(self, ok=True):
        self.ok, self.calls = ok, []

    def ShamrockSetShutter(self, dev, state):
        self.calls.append(state)
        return 20202 if self.ok else 20201


@pytest.fixture
def cam():
    c = get_andor_ccd(force_mock=True, reset=True)
    c.set_read_mode(READ_MODE_IMAGE)
    return c


def _runner(cam, exposures):
    r = GridRunner(cam, tick=lambda: None, sleep=lambda s: None)
    real = r.expose

    def expose(shape, exposure_s):
        exposures.append((tuple(shape), exposure_s))
        return np.full(shape, 7.0)
    r.expose = expose
    return r


def test_the_dark_uses_the_mode_spectrum_1d_will_use(cam):
    exposures, store = [], pb.DarkStore()
    r = _runner(cam, exposures)
    d = r.ensure_dark_1d(0.2, spectrometer=_Spec(), method=pb.METHOD_SHUTTER, n_frames=1, store=store)
    assert cam.get_read_mode() == READ_MODE_FVB                      # Imagen → FVB, como spectrum_1d
    assert exposures == [((1004,), 0.2)] and d.conditions.read_mode == READ_MODE_FVB
    assert d.conditions == expected_1d_conditions(cam, 0.2)


def test_single_track_is_respected(cam):
    cam.set_read_mode(READ_MODE_SINGLE_TRACK)
    d = _runner(cam, []).ensure_dark_1d(0.1, spectrometer=_Spec(), method=pb.METHOD_SHUTTER, n_frames=1,
                                        store=pb.DarkStore())
    assert d.conditions.read_mode == READ_MODE_SINGLE_TRACK and cam.get_read_mode() == READ_MODE_SINGLE_TRACK


def test_the_dark_is_reused_without_measuring_while_conditions_do_not_change(cam):
    exposures, store, spec = [], pb.DarkStore(), _Spec()
    r = _runner(cam, exposures)
    d1 = r.ensure_dark_1d(0.2, spectrometer=spec, method=pb.METHOD_SHUTTER, n_frames=1, store=store)
    d2 = r.ensure_dark_1d(0.2, spectrometer=spec, method=pb.METHOD_SHUTTER, n_frames=1, store=store)
    assert d1 is d2 and len(exposures) == 1
    r.ensure_dark_1d(0.3, spectrometer=spec, method=pb.METHOD_SHUTTER, n_frames=1, store=store)
    assert len(exposures) == 2                                        # otra exposición, otro fondo


def test_shutter_method_closes_and_reopens_the_spectrometer_shutter(cam):
    spec = _Spec()
    _runner(cam, []).ensure_dark_1d(0.1, spectrometer=spec, method=pb.METHOD_SHUTTER, n_frames=1,
                                    store=pb.DarkStore())
    assert spec.calls == [0, 1]                                       # cerrado para el fondo, abierto para medir


def test_a_shutter_that_does_not_close_aborts_without_a_dark(cam):
    store = pb.DarkStore()
    with pytest.raises(GridAbort, match="fondo"):
        _runner(cam, []).ensure_dark_1d(0.1, spectrometer=_Spec(ok=False), method=pb.METHOD_SHUTTER, n_frames=1,
                                        store=store)
    assert store.get_valid(expected_1d_conditions(cam, 0.1)) is None


def test_all_off_is_never_taken_automatically(cam):
    exposures = []
    with pytest.raises(GridAbort, match="todo apagado"):
        _runner(cam, exposures).ensure_dark_1d(0.1, spectrometer=_Spec(), method=pb.METHOD_ALL_OFF, n_frames=1,
                                               store=pb.DarkStore())
    assert exposures == []


def test_take_dark_1d_always_measures_and_stores(cam, monkeypatch):
    monkeypatch.setattr("core.nidaq.get_open_shutter_names", lambda: [])
    exposures, store = [], pb.DarkStore()
    r = _runner(cam, exposures)
    d1 = r.take_dark_1d(0.1, spectrometer=_Spec(), method=pb.METHOD_ALL_OFF, n_frames=2, store=store)
    d2 = r.take_dark_1d(0.1, spectrometer=_Spec(), method=pb.METHOD_ALL_OFF, n_frames=2, store=store)
    assert len(exposures) == 4 and d2 is not d1 and store.get_valid(d2.conditions) is d2


def test_expected_conditions_do_not_touch_the_camera(cam):
    expected_1d_conditions(cam, 0.1)
    assert cam.get_read_mode() == READ_MODE_IMAGE


# ── La fila "Fondo" ─────────────────────────────────────────────────────────────────────────

def _row():
    from pyspectrum.ui.background_row import BackgroundRow
    row = BackgroundRow(default_frames=1)
    _KEEP.append(row)
    return row


def _dark(value=5.0, n=4):
    c = pb.DarkConditions(0.1, 0, 0, 1, 0, 1, 0, None, (n,), -60.0)
    return pb.Dark("abc123", np.full(n, value, np.float32), np.zeros(n, np.float32), 1, pb.METHOD_SHUTTER, c,
                   "2026-09-30T12:00:00", "obturador cerrado", -59.9)


def test_row_defaults_and_signals():
    row = _row()
    assert row.method() == pb.METHOD_SHUTTER and row.n_frames() == 1 and row.subtract()
    got = []
    row.takeNowRequested.connect(lambda m, n: got.append((m, n)))
    row.discardRequested.connect(lambda: got.append("discard"))
    row.cmb_method.setCurrentIndex(row.cmb_method.findData(pb.METHOD_ALL_OFF))
    row.spin_frames.setValue(3)
    row.btn_take.click()
    row.btn_discard.click()
    assert got == [(pb.METHOD_ALL_OFF, 3), "discard"]


def test_row_status_texts():
    row = _row()
    row.show_status("valid", _dark(), "")
    assert "válido" in row.lbl_status.text() and "#A6E3A1" in row.lbl_status.styleSheet()
    row.show_status("none", None, "")
    assert "se toma al iniciar" in row.lbl_status.text()
    row.cmb_method.setCurrentIndex(row.cmb_method.findData(pb.METHOD_ALL_OFF))
    row.show_status("none", None, "")
    assert "Tomar fondo ahora" in row.lbl_status.text() and "#F9E2AF" in row.lbl_status.styleSheet()
    row.show_status("invalid", _dark(), "exposición: 0.1 → 0.2 s")
    assert "no válido" in row.lbl_status.text() and "exposición" in row.lbl_status.text()


def test_row_subtracts_only_for_display_and_only_with_a_valid_matching_dark():
    row = _row()
    spec = np.full(4, 12.0)
    assert row.for_display(spec) is spec                              # sin fondo
    row.show_status("valid", _dark(5.0, 4), "")
    np.testing.assert_allclose(row.for_display(spec), 7.0)
    np.testing.assert_allclose(spec, 12.0)                            # el crudo no cambia
    row.chk_subtract.setChecked(False)
    assert row.for_display(spec) is spec
    row.chk_subtract.setChecked(True)
    assert row.for_display(np.full(5, 12.0)).shape == (5,)            # otra forma: no resta
    np.testing.assert_allclose(row.for_display(np.full(5, 12.0)), 12.0)
    row.show_status("invalid", _dark(5.0, 4), "x")
    np.testing.assert_allclose(row.for_display(spec), 12.0)          # no válido: no resta


# ── Luminiscencia (el patrón de las rutinas de grilla) ──────────────────────────────────────

@pytest.fixture
def lum(tmp_path, monkeypatch):
    import config
    from core import nidaq
    from pyspectrum.drivers.shamrock_driver import get_shamrock
    from pyspectrum.modules.hardware_session import hardware_session
    from pyspectrum.modules.routines import luminescence as lm
    hardware_session.clear_emergency()
    monkeypatch.setattr(lm, "run_z_autofocus", lambda **kw: True)
    b = lm.LuminescenceBackend(get_andor_ccd(force_mock=True, reset=True), get_shamrock(force_mock=True))
    b.data_dir = str(tmp_path / "lum")
    b.generate_grid(1, 2, 3.0, 0.0, 40.0, 40.0, 5.0)
    _KEEP.append(b)
    yield b, lm, config.SHUTTERS[0]
    b.abort_grid()
    b.stop_luminescence()
    b.grid_thread.wait_finished(10)
    b.point_thread.wait_finished(10)
    hardware_session.clear_emergency()
    nidaq.close_all_shutters()


def _grid_cfg(laser, **kw):
    c = {"laser": laser, "exp_time": 0.02, "autofocus_every": 5, "save_dir": "", "mirror": "up"}
    c.update(kw)
    return c


def test_all_off_without_a_dark_does_not_start(lum):
    from pyspectrum.modules.hardware_session import hardware_session
    b, lm, laser = lum
    msgs = []
    b.statusSignal.connect(msgs.append)
    b.grid_dark.set_settings(pb.METHOD_ALL_OFF, 1)
    b.start_grid(_grid_cfg(laser))
    assert not b._grid_running and not hardware_session.is_busy
    assert msgs and "Tomar fondo ahora" in msgs[-1]


def test_a_second_run_with_the_same_conditions_reuses_the_dark(lum, monkeypatch):
    from pyspectrum.modules import acquisition
    b, lm, laser = lum
    shapes = []
    real = acquisition.single_exposure
    monkeypatch.setattr(acquisition, "single_exposure", lambda *a, **k: shapes.append(a[1].shape) or real(*a, **k))
    b.start_grid(_grid_cfg(laser))
    assert b.grid_thread.wait_finished(20)
    first = b.run_dark
    b.generate_grid(1, 2, 3.0, 0.0, 40.0, 40.0, 5.0)
    b.start_grid(_grid_cfg(laser))
    assert b.grid_thread.wait_finished(20)
    assert b.run_dark is first and len(shapes) == 1 + 2 + 2          # un solo fondo para las dos corridas
    b.generate_grid(1, 2, 3.0, 0.0, 40.0, 40.0, 5.0)
    b.start_grid(_grid_cfg(laser, exp_time=0.03))                     # otra exposición: otro fondo
    assert b.grid_thread.wait_finished(20)
    assert b.run_dark is not first and len(shapes) == 1 + 2 + 2 + 1 + 2


def test_the_point_series_integrates_without_the_dark(lum, monkeypatch):
    from pyspectrum.modules import acquisition
    from pyspectrum.modules.acquisition import Frame
    b, lm, laser = lum
    values = iter([100.0, 150.0, 160.0])                              # fondo, cuadro 1, cuadro 2

    def fake(cam, req, **kw):
        return Frame(np.full(req.shape, next(values)), req.exposure_s, None, 0.0, 0.0)
    monkeypatch.setattr(acquisition, "single_exposure", fake)
    b.confirm_mirror("down")
    b.start_luminescence(laser, 0.02, 2, 0.0)
    assert b.point_thread.wait_finished(20)
    np.testing.assert_allclose(b.i_points, [50.0 * 1004, 60.0 * 1004])


def test_the_panel_subtracts_only_for_display(lum):
    b, lm, laser = lum
    w = lm.LuminescencePanel()
    _KEEP.append(w)
    b.make_connection(w)
    w.bg_row_grid.show_status("valid", _dark(5.0, 4), "")
    spec = np.full(4, 12.0)
    w.update_grid_spectrum(np.arange(4.0), spec)
    np.testing.assert_allclose(w.curve_grid_spec.getData()[1], 7.0)
    np.testing.assert_allclose(spec, 12.0)
    w.bg_row_grid.chk_subtract.setChecked(False)
    w.update_grid_spectrum(np.arange(4.0), spec)
    np.testing.assert_allclose(w.curve_grid_spec.getData()[1], 12.0)


# ── Crecimiento, dímeros y mapa hiperespectral ──────────────────────────────────────────────

def _fixed_frames(monkeypatch, values):
    from pyspectrum.modules import acquisition
    from pyspectrum.modules.acquisition import Frame
    it = iter(values)
    monkeypatch.setattr(acquisition, "single_exposure",
                        lambda cam, req, **kw: Frame(np.full(req.shape, float(next(it))), req.exposure_s, None, 0.0, 0.0))


def test_growth_point_fits_lambda_max_without_the_dark(monkeypatch):
    from pyspectrum.drivers.shamrock_driver import get_shamrock
    from pyspectrum.modules.hardware_session import hardware_session
    from pyspectrum.modules.routines import growth_kinetics as gk
    hardware_session.clear_emergency()
    b = gk.GrowthKineticsBackend(get_andor_ccd(force_mock=True, reset=True), get_shamrock(force_mock=True))
    _KEEP.append(b)
    seen = []
    monkeypatch.setattr(gk.GrowthKineticsBackend, "_fit", staticmethod(
        lambda wave, spec: (seen.append(np.asarray(spec).copy()) or (wave, spec, 600.0))))
    _fixed_frames(monkeypatch, [100.0, 130.0])
    b.confirm_mirror("down")
    b.start_growth("532 nm (green)", 0.02, 1, 0.0)
    assert b.point_thread.wait_finished(20)
    assert len(seen) == 1 and np.allclose(seen[0], 30.0)             # el ajuste ve crudo − fondo


def test_growth_grid_saves_the_dark_apart_and_references_it(tmp_path, monkeypatch):
    from pyspectrum.drivers.shamrock_driver import get_shamrock
    from pyspectrum.modules.hardware_session import hardware_session
    from pyspectrum.modules.routines import growth_kinetics as gk
    hardware_session.clear_emergency()
    monkeypatch.setattr(gk, "run_z_autofocus", lambda **kw: True)
    monkeypatch.setattr(gk, "run_confocal_centering", lambda **kw: None)
    b = gk.GrowthKineticsBackend(get_andor_ccd(force_mock=True, reset=True), get_shamrock(force_mock=True))
    _KEEP.append(b)
    b.data_dir = str(tmp_path / "growth")
    b.generate_grid(1, 1, 3.0, 0.0, 40.0, 40.0, 5.0)
    b.start_grid({"laser": "532 nm (green)", "exp_time": 0.01, "autofocus_every": 10, "center_seed": False,
                  "use_lambda_stop": False, "lambda_target_nm": None, "use_photodiode_stop": False,
                  "photodiode_drop_pct": None, "t_max_s": 0.05, "interval_s": 0.02, "save_dir": "", "mirror": "up"})
    assert b.grid_thread.wait_finished(20)
    files = sorted(p.name for p in (tmp_path / "growth").iterdir())
    dark_files = [f for f in files if f.startswith("GrowthGrid_background_")]
    assert len(dark_files) == 1
    dark_id = dark_files[0][len("GrowthGrid_background_"):-len(".npz")]
    for name in ("GrowthNode_000_final_spectrum.txt", "GrowthNode_000_kinetics.txt"):
        assert f"background_id: {dark_id}" in (tmp_path / "growth" / name).read_text(encoding="utf-8")


def test_dimers_polarization_refuses_all_off_without_a_dark():
    from pyspectrum.drivers.shamrock_driver import get_shamrock
    from pyspectrum.modules.hardware_session import hardware_session
    from pyspectrum.modules.routines import dimers as dm
    hardware_session.clear_emergency()
    b = dm.DimersBackend(get_andor_ccd(force_mock=True, reset=True), get_shamrock(force_mock=True))
    _KEEP.append(b)
    msgs = []
    b.statusSignal.connect(msgs.append)
    b.pol_dark.set_settings(pb.METHOD_ALL_OFF, 1)
    b.acquire_polarization("parallel", 0.02)
    assert not b.pol_thread.running and msgs and "Tomar fondo ahora" in msgs[-1]


def test_hyperspectral_map_value_without_the_dark_and_h5_background(tmp_path, monkeypatch):
    h5py = pytest.importorskip("h5py")
    from core import nidaq
    from pyspectrum.drivers.shamrock_driver import get_shamrock
    from pyspectrum.modules import hyperspectral_confocal as hc
    from pyspectrum.modules.hardware_session import hardware_session
    hardware_session.clear_emergency()
    b = hc.Backend(get_andor_ccd(force_mock=True, reset=True), get_shamrock(force_mock=True))
    _KEEP.append(b)
    b.data_dir = tmp_path
    b.scan_timer.stop()
    monkeypatch.setattr(b.scan_timer, "start", lambda *a: None)
    _fixed_frames(monkeypatch, [100.0, 110.0])
    try:
        b.confirm_mirror("up")
        b.start_scan(45.0, 45.0, 45.0, 45.0, 1.0, 0.01, "532 nm (green)")
        while b._scanning:
            b._scan_step()
        assert float(b.map_2d[0, 0]) == pytest.approx(10.0 * 1004)
        with h5py.File(b._saved_path, "r") as f:
            np.testing.assert_allclose(f["cube"][0, 0, :], 110.0)       # el cubo es crudo
            np.testing.assert_allclose(f["background/mean"][()], 100.0)
    finally:
        b.stop_scan()
        hardware_session.release_session("Mapeo Confocal")
        hardware_session.clear_emergency()
        nidaq.close_all_shutters()


# ── Raman estático: a pedido, como en Exploración ───────────────────────────────────────────

def _raman():
    from pyspectrum.drivers.shamrock_driver import get_shamrock
    from pyspectrum.modules.static_raman import StaticRamanBackend, StaticRamanWidget
    cam = get_andor_ccd(force_mock=True, reset=True)
    cam.set_read_mode(READ_MODE_FVB)
    be = StaticRamanBackend(cam, get_shamrock(force_mock=True))
    w = StaticRamanWidget()
    _KEEP.extend([be, w])
    be.make_connection(w)
    for chk in (w.chk_despike, w.chk_baseline, w.chk_savgol):
        chk.setChecked(False)
    return be, w


def test_raman_processing_subtracts_the_dark_first_and_keeps_the_raw():
    be, w = _raman()
    w.bg_row.show_status("valid", _dark(100.0, 1004), "")
    raw = np.full(1004, 160.0)
    w.update_spectrum_data(np.linspace(540.0, 640.0, 1004), raw)
    np.testing.assert_allclose(w.processed_y, 60.0)
    np.testing.assert_allclose(w.raw_counts, 160.0)
    w.bg_row.chk_subtract.setChecked(False)
    w._reprocess_current_spectrum()
    np.testing.assert_allclose(w.processed_y, 160.0)


def test_raman_txt_has_a_separate_background_column(tmp_path):
    be, w = _raman()
    d = _dark(100.0, 1004)
    meta = {"Laser_Excitacion_nm": 532.0, "_raw_counts": [160.0] * 1004, "_raw_wl": list(np.linspace(540, 640, 1004)),
            "_background": d}
    be.save_spectrum_to_file(str(tmp_path / "r.txt"), meta)
    text = (tmp_path / "r.txt").read_text(encoding="utf-8")
    assert f"# background_id: {d.id}" in text and "Background_Counts" in text
    data = np.loadtxt(tmp_path / "r.txt", comments="#", skiprows=text.splitlines().index(next(l for l in text.splitlines() if l.startswith("Wavelength_nm"))) + 1)
    assert data.shape == (1004, 4)
    np.testing.assert_allclose(data[:, 2], 160.0)               # el crudo
    np.testing.assert_allclose(data[:, 3], 100.0)               # el fondo, aparte
    meta.pop("_background")
    be.save_spectrum_to_file(str(tmp_path / "s.txt"), meta)
    t2 = (tmp_path / "s.txt").read_text(encoding="utf-8")
    assert "Background_Counts" not in t2 and t2.splitlines()[-1].count("	") == 2
    assert "# background_id: ninguno" in (tmp_path / "s.txt").read_text(encoding="utf-8")


def test_raman_dark_conditions_follow_the_camera_mode_and_exposure():
    be, w = _raman()
    be.camera.set_exposure_time(0.3)
    c = be.dark_ctl.conditions(be.camera.get_exposure_time())
    assert c.read_mode == READ_MODE_FVB and c.shape == (1004,) and c.exposure_s == pytest.approx(0.3)


def test_raman_txt_ignores_a_background_of_another_shape(tmp_path):
    be, w = _raman()
    meta = {"Laser_Excitacion_nm": 532.0, "_raw_counts": [160.0] * 1004, "_raw_wl": list(np.linspace(540, 640, 1004)),
            "_background": _dark(100.0, 512)}
    be.save_spectrum_to_file(str(tmp_path / "r.txt"), meta)
    text = (tmp_path / "r.txt").read_text(encoding="utf-8")
    assert "Background_Counts" not in text and "# background_id: ninguno" in text
    assert len([l for l in text.splitlines() if not l.startswith("#")]) == 1 + 1004


def test_luminescence_point_all_off_without_a_dark_is_refused_before_the_thread(lum):
    from pyspectrum.modules.hardware_session import hardware_session
    b, lm, laser = lum
    msgs = []
    b.statusSignal.connect(msgs.append)
    b.confirm_mirror("down")
    b.point_dark.set_settings(pb.METHOD_ALL_OFF, 1)
    b.start_luminescence(laser, 0.02, 2, 0.0)
    assert not b.point_thread.running and not hardware_session.is_busy      # ni hilo ni sesión
    assert msgs and "Tomar fondo ahora" in msgs[-1]


def test_growth_point_all_off_without_a_dark_is_refused_before_the_thread():
    from pyspectrum.drivers.shamrock_driver import get_shamrock
    from pyspectrum.modules.hardware_session import hardware_session
    from pyspectrum.modules.routines import growth_kinetics as gk
    hardware_session.clear_emergency()
    b = gk.GrowthKineticsBackend(get_andor_ccd(force_mock=True, reset=True), get_shamrock(force_mock=True))
    _KEEP.append(b)
    msgs = []
    b.statusSignal.connect(msgs.append)
    b.confirm_mirror("down")
    b.point_dark.set_settings(pb.METHOD_ALL_OFF, 1)
    b.start_growth("532 nm (green)", 0.02, 1, 0.0)
    assert not b.point_thread.running and not hardware_session.is_busy
    assert msgs and "Tomar fondo ahora" in msgs[-1]


def test_growth_grid_all_off_without_a_dark_is_refused_before_the_thread():
    from pyspectrum.drivers.shamrock_driver import get_shamrock
    from pyspectrum.modules.hardware_session import hardware_session
    from pyspectrum.modules.routines import growth_kinetics as gk
    hardware_session.clear_emergency()
    b = gk.GrowthKineticsBackend(get_andor_ccd(force_mock=True, reset=True), get_shamrock(force_mock=True))
    _KEEP.append(b)
    b.generate_grid(1, 1, 3.0, 0.0, 40.0, 40.0, 5.0)
    msgs = []
    b.statusSignal.connect(msgs.append)
    b.grid_dark.set_settings(pb.METHOD_ALL_OFF, 1)
    b.start_grid({"laser": "532 nm (green)", "exp_time": 0.01, "autofocus_every": 10, "center_seed": False,
                  "use_lambda_stop": False, "lambda_target_nm": None, "use_photodiode_stop": False,
                  "photodiode_drop_pct": None, "t_max_s": 0.05, "interval_s": 0.02, "save_dir": "", "mirror": "up"})
    assert not b.grid_thread.running and not hardware_session.is_busy
    assert msgs and "Tomar fondo ahora" in msgs[-1]


def test_hyperspectral_all_off_without_a_dark_is_refused_before_the_session(tmp_path):
    from pyspectrum.drivers.shamrock_driver import get_shamrock
    from pyspectrum.modules import hyperspectral_confocal as hc
    from pyspectrum.modules.hardware_session import hardware_session
    hardware_session.clear_emergency()
    cam = get_andor_ccd(force_mock=True, reset=True)
    cam.set_read_mode(READ_MODE_IMAGE)
    b = hc.Backend(cam, get_shamrock(force_mock=True))
    _KEEP.append(b)
    b.data_dir = tmp_path
    b.scan_timer.stop()
    msgs = []
    b.statusSignal.connect(msgs.append)
    b.dark.set_settings(pb.METHOD_ALL_OFF, 1)
    b.confirm_mirror("up")
    b.start_scan(45.0, 45.0, 45.0, 45.0, 1.0, 0.01, "532 nm (green)")
    try:
        assert not b._scanning and not hardware_session.is_busy
        assert msgs and "Tomar fondo ahora" in msgs[-1]
        assert cam.get_read_mode() == READ_MODE_IMAGE                    # no tocó la cámara
        assert not any(tmp_path.rglob("*"))                              # ni guardó un mapa vacío
    finally:
        b.stop_scan()
        hardware_session.release_session("Mapeo Confocal")
