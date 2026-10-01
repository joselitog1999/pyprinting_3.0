# -*- coding: utf-8 -*-
"""Autocalibración del centro de la ranura (R4-N 1a; P1-P4; DEC-040).

- La ranura es vertical: en orden cero se ve una línea brillante. Se ajusta una gaussiana en cada fila del ROI
  vertical y se promedia la posición del máximo; esa columna, cruzada con el ROI, es la zona de trabajo (P1).
- La estadística sale de las filas (P2): u de Tipo A, dispersión respecto de la recta e inclinación.
- Orden cero exigido; cuadros nuevos; si falla, no se guarda nada.
- Se aplica sólo con [Aplicar] (P3), y cada aplicación queda en el archivo de calibraciones como SLIT_CENTER,
  EXPERIMENTAL (P4).
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYPRINTING_SAFE", "1")

import sys

import numpy as np
import pytest
from PyQt6 import QtWidgets

from pyspectrum.calibration import slit_center as sc
from pyspectrum.drivers import specular_interlock as si
from pyspectrum.drivers.andor_ccd_driver import READ_MODE_FVB, READ_MODE_IMAGE, READ_MODE_SINGLE_TRACK

_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["pytest"])
_KEEP = []


def _slit(k=1, rows=40, center=500.3, tilt=0.0, sigma=2.2, amp=3000.0, bias=500.0, noise=8.0, seed=0,
          lit_rows=None):
    rng = np.random.default_rng(seed)
    x = np.arange(1004, dtype=np.float64)
    r = np.arange(rows, dtype=np.float64)
    c = center + tilt * (r - (rows - 1) / 2.0)
    line = amp * np.exp(-0.5 * ((x[None, :] - c[:, None]) / sigma) ** 2)
    if lit_rows is not None:
        mask = np.zeros(rows, bool)
        mask[lit_rows] = True
        line[~mask] = 0.0
    frames = bias + line[None, :, :] + rng.normal(0.0, noise, (k, rows, 1004))
    return frames


# ── Análisis (puro) ─────────────────────────────────────────────────────────────────────────

def test_recovers_the_center_and_the_width_from_the_rows():
    res = sc.analyze_slit_frames(_slit(), (480, 520))
    assert res.ok, res.reason
    assert res.center_px == pytest.approx(500.3, abs=0.05)
    assert res.fwhm_px == pytest.approx(2.2 * 2.3548, abs=0.15)
    assert res.fwhm_um == pytest.approx(res.fwhm_px * 8.0)
    assert len(res.rows_used) == 40 and res.rows_used[0] == 480 and res.rows_used[-1] == 519
    assert 0 < res.u_center_px < 0.05 and res.scatter_px < 0.2
    assert "TILT" not in res.flags
    assert res.profile is not None and res.profile.shape == (1004,) and res.fit_x.size == res.fit_y.size > 0


def test_a_tilted_slit_is_flagged_and_the_mean_is_the_center_of_the_roi():
    res = sc.analyze_slit_frames(_slit(tilt=0.05), (480, 520))
    assert res.ok, res.reason
    assert res.tilt_px_per_row == pytest.approx(0.05, abs=0.005)
    assert "TILT" in res.flags
    assert res.center_px == pytest.approx(500.3, abs=0.05)
    assert res.scatter_px < 0.2                      # respecto de la recta, no de la media


def test_a_cosmic_ray_on_one_row_is_rejected():
    frames = _slit()
    frames[0, 7, 503:506] += 5000.0
    res = sc.analyze_slit_frames(frames, (480, 520))
    assert res.ok, res.reason
    assert 487 not in res.rows_used and len(res.rows_used) == 39
    assert res.center_px == pytest.approx(500.3, abs=0.05)
    assert "ROWS_REJECTED" in res.flags


def test_a_saturating_cosmic_ray_drops_its_row_only():
    frames = _slit()
    frames[0, 7, 700:702] = 16383.0
    res = sc.analyze_slit_frames(frames, (480, 520))
    assert res.ok, res.reason
    assert 487 not in res.rows_used and "ROWS_SATURATED" in res.flags
    assert res.saturation_frac < 0.5                       # la de las filas usadas


def test_with_several_frames_a_cosmic_ray_is_rejected_in_time():
    frames = _slit(k=3)
    frames[1, 7, 503:506] += 5000.0
    res = sc.analyze_slit_frames(frames, (480, 520))
    assert res.ok and len(res.rows_used) == 40 and res.n_frames == 3


def test_saturation_is_refused():
    res = sc.analyze_slit_frames(_slit(amp=15000.0), (480, 520))
    assert not res.ok and "SATURATED" in res.flags and "satura" in res.reason
    assert res.center_px != res.center_px                # NaN: nunca un centro de una medición rechazada


def test_without_a_line_nothing_is_found():
    res = sc.analyze_slit_frames(_slit(amp=0.0), (480, 520))
    assert not res.ok and "NO_LINE" in res.flags


def test_too_few_lit_rows_is_refused():
    res = sc.analyze_slit_frames(_slit(lit_rows=slice(0, 10)), (480, 520))
    assert not res.ok and "filas" in res.reason


def test_summary_and_values_for_the_file():
    res = sc.analyze_slit_frames(_slit(), (480, 520))
    text = res.summary()
    assert "500.3" in text and "±" in text and "µm" in text
    v = res.values()
    assert v["provenance"] == "EXPERIMENTAL" and v["center_px"] == pytest.approx(res.center_px)
    assert v["rows"] == [480, 520] and v["n_rows_used"] == 40 and "profile" not in v


# ── Medición contra la cámara ───────────────────────────────────────────────────────────────

class _Cam:
    def __init__(self, mode=READ_MODE_FVB):
        self.mode, self.calls = mode, []
        self.track = (501, 40)

    def get_read_mode(self):
        return self.mode

    def set_read_mode(self, m):
        self.calls.append(("set_read_mode", m))
        self.mode = m
        return 20002

    def set_image(self, *a):
        self.calls.append(("set_image",) + tuple(a))
        self.mode = READ_MODE_IMAGE
        return 20002

    def get_single_track(self):
        return self.track

    def set_single_track(self, c, h):
        self.calls.append(("set_single_track", c, h))
        return 20002


def _expose_with(frames, shapes):
    it = iter(frames)

    def expose(shape, exposure_s):
        shapes.append((tuple(shape), exposure_s))
        return next(it)
    return expose


def test_measure_refuses_outside_zero_order_without_touching_the_camera():
    cam, shapes = _Cam(), []
    with pytest.raises(sc.SlitCalibrationRefused, match="orden cero"):
        sc.measure_slit_center(cam, _expose_with(_slit()[:, :, :], shapes), exposure_s=0.05, rows=(480, 520),
                               n_frames=1, mode_fn=lambda: si.FIRST_ORDER)
    assert cam.calls == [] and shapes == []


@pytest.mark.parametrize("rows", [(0, 0), (500, 502), (990, 1010), (-3, 40)])
def test_measure_refuses_a_bad_roi(rows):
    with pytest.raises(sc.SlitCalibrationRefused, match="ROI"):
        sc.measure_slit_center(_Cam(), lambda *a: None, exposure_s=0.05, rows=rows, n_frames=1,
                               mode_fn=lambda: si.SPECULAR)


def test_measure_reads_the_roi_rows_and_restores_the_mode():
    cam, shapes = _Cam(READ_MODE_SINGLE_TRACK), []
    frames = _slit(k=2)
    res = sc.measure_slit_center(cam, _expose_with(list(frames), shapes), exposure_s=0.07, rows=(480, 520),
                                 n_frames=2, mode_fn=lambda: si.SPECULAR)
    assert res.ok and res.n_frames == 2
    assert shapes == [((40, 1004), 0.07), ((40, 1004), 0.07)]
    assert cam.calls[0] == ("set_image", 1, 1, 1, 1004, 481, 520)
    assert cam.calls[1:] == [("set_read_mode", READ_MODE_SINGLE_TRACK), ("set_single_track", 501, 40)]


def test_measure_restores_the_mode_when_the_exposure_fails():
    cam = _Cam(READ_MODE_FVB)

    def boom(shape, exp):
        raise RuntimeError("falló")
    with pytest.raises(RuntimeError):
        sc.measure_slit_center(cam, boom, exposure_s=0.05, rows=(480, 520), n_frames=1,
                               mode_fn=lambda: si.SPECULAR)
    assert cam.calls[-1] == ("set_read_mode", READ_MODE_FVB)


# ── Backend y panel ─────────────────────────────────────────────────────────────────────────

@pytest.fixture
def dock(tmp_path, monkeypatch):
    from pyspectrum.calibration.repository import CalibrationRepository
    from pyspectrum.drivers.andor_ccd_driver import get_andor_ccd
    from pyspectrum.drivers.shamrock_driver import get_shamrock
    from pyspectrum.modules import calibration_dock as cd
    from pyspectrum.modules.hardware_session import hardware_session
    from pyspectrum.modules.spectroscopy_context import spectroscopy_context
    hardware_session.clear_emergency()
    monkeypatch.setattr(cd, "CALIBRATION_TXT_FILE", tmp_path / "calib_last.txt")
    monkeypatch.setattr(cd, "CALIBRATION_FILE", tmp_path / "calib.json")
    monkeypatch.setenv("PYSPECTRUM_ROUTINE_DATA_DIR", str(tmp_path / "data"))
    old_roi = spectroscopy_context.vertical_roi
    spectroscopy_context.set_vertical_roi(480, 520)
    repo = CalibrationRepository(tmp_path / "repo" / "cal.jsonl")
    fe = cd.CalibrationFrontend()
    be = cd.CalibrationBackend(get_andor_ccd(force_mock=True), get_shamrock(force_mock=True), repository=repo)
    be.make_connection(fe)
    _KEEP.extend([fe, be])
    yield fe, be, repo, tmp_path
    be.shutdown()
    spectroscopy_context.set_vertical_roi(old_roi[0], old_roi[1])
    hardware_session.clear_emergency()


def _feed(monkeypatch, frames, specular=True):
    from pyspectrum.modules import acquisition
    from pyspectrum.modules.acquisition import Frame
    it = iter(frames)
    monkeypatch.setattr(acquisition, "single_exposure",
                        lambda cam, req, **kw: Frame(np.asarray(next(it)), req.exposure_s, None, 0.0, 0.0))
    monkeypatch.setattr(sc, "zero_order_mode", lambda camera, spectrometer: si.SPECULAR if specular
                        else si.FIRST_ORDER)


def _run(fe, be, exposure=0.05, frames=1):
    fe.spin_slit_exp.setValue(exposure)
    fe.spin_slit_frames.setValue(frames)
    fe.btn_auto_slit.click()
    assert be.slit_thread.wait_finished(20)


def test_the_panel_sends_exposure_and_frames():
    from pyspectrum.modules import calibration_dock as cd
    fe = cd.CalibrationFrontend()
    _KEEP.append(fe)
    got = []
    fe.autoCalibrateSlitSignal.connect(lambda e, n: got.append((e, n)))
    fe.spin_slit_exp.setValue(0.2)
    fe.spin_slit_frames.setValue(3)
    fe.btn_auto_slit.click()
    assert got == [(pytest.approx(0.2), 3)]
    assert fe.spin_slit_frames.value() == 3 and not fe.btn_apply_slit_center.isEnabled()


def test_a_run_shows_the_result_and_saves_nothing_until_apply(dock, monkeypatch):
    fe, be, repo, tmp = dock
    before = be.slit_center_x
    _feed(monkeypatch, list(_slit()))
    _run(fe, be)
    res = be.pending_slit
    assert res is not None and res.ok, getattr(res, "reason", None)
    assert fe.btn_apply_slit_center.isEnabled() and "500.3" in fe.lbl_slit_result.text()
    assert be.slit_center_x == before                        # sin [Aplicar] no cambia nada
    assert not (tmp / "calib_last.txt").exists() and not (tmp / "calib.json").exists()
    assert [e for e in repo.history() if e.kind == "SLIT_CENTER"] == []
    h5 = list((tmp / "data" / "calibration").glob("slit_center_*.h5"))
    assert len(h5) == 1 and res.frames_file == str(h5[0])   # el crudo de una medición buena, aparte


def test_apply_writes_the_center_once_and_registers_it(dock, monkeypatch):
    from pyspectrum.modules.spectroscopy_context import spectroscopy_context
    fe, be, repo, tmp = dock
    _feed(monkeypatch, list(_slit()))
    _run(fe, be)
    res = be.pending_slit
    fe.btn_apply_slit_center.click()
    assert be.slit_center_x == pytest.approx(res.center_px)
    assert spectroscopy_context.slit_center_px == pytest.approx(res.center_px)
    assert fe.spin_pixel_x.value() == pytest.approx(res.center_px, abs=0.01)
    assert "slit_center_pixel_x" in (tmp / "calib_last.txt").read_text(encoding="utf-8")
    entries = [e for e in repo.history() if e.kind == "SLIT_CENTER"]
    assert len(entries) == 1
    v = entries[0].values
    assert v["provenance"] == "EXPERIMENTAL" and entries[0].method == "row_gaussian_mean"
    assert v["center_px"] == pytest.approx(res.center_px) and v["frames_file"] == res.frames_file
    assert not fe.btn_apply_slit_center.isEnabled() and be.pending_slit is None
    be.apply_slit_center()                                   # sin una medición nueva no vuelve a escribir
    assert len([e for e in repo.history() if e.kind == "SLIT_CENTER"]) == 1
    assert fe.table_history.item(0, 1).text() == "SLIT_CENTER"


def test_a_failed_run_saves_nothing_and_cannot_be_applied(dock, monkeypatch):
    fe, be, repo, tmp = dock
    before = be.slit_center_x
    _feed(monkeypatch, list(_slit(amp=0.0)))
    _run(fe, be)
    assert be.pending_slit is None and not fe.btn_apply_slit_center.isEnabled()
    assert "NO_LINE" in fe.lbl_slit_result.text() or "línea" in fe.lbl_slit_result.text()
    be.apply_slit_center()
    assert be.slit_center_x == before and repo.history() == []
    assert not (tmp / "data" / "calibration").exists() or not any((tmp / "data" / "calibration").iterdir())


def test_outside_zero_order_the_run_does_not_start(dock, monkeypatch):
    from pyspectrum.modules.hardware_session import hardware_session
    fe, be, repo, tmp = dock
    _feed(monkeypatch, [], specular=False)
    msgs = []
    be.statusSignal.connect(msgs.append)
    fe.btn_auto_slit.click()
    assert not be.slit_thread.running and not hardware_session.is_busy
    assert msgs and "orden cero" in msgs[-1]


def test_without_a_roi_the_run_does_not_start(dock, monkeypatch):
    from pyspectrum.modules.spectroscopy_context import spectroscopy_context
    fe, be, repo, tmp = dock
    _feed(monkeypatch, [])
    spectroscopy_context.set_vertical_roi(0, 0)
    msgs = []
    be.statusSignal.connect(msgs.append)
    fe.btn_auto_slit.click()
    assert not be.slit_thread.running and msgs and "ROI" in msgs[-1]


def test_the_spectrometer_shutter_is_opened_only_for_the_run(dock, monkeypatch):
    fe, be, repo, tmp = dock
    seq = []

    def record(what):
        def fn(c, s):
            if sys._getframe(1).f_globals.get("__name__") == "pyspectrum.modules.routines.routine_thread":
                seq.append(what)
            return type("R", (), {"ok": True, "detail": ""})()
        return fn
    monkeypatch.setattr("pyspectrum.services.spectrometer_shutter.open_spectrometer_shutter", record("open"))
    monkeypatch.setattr("pyspectrum.services.spectrometer_shutter.close_spectrometer_shutter", record("close"))
    _feed(monkeypatch, list(_slit()))
    _run(fe, be)
    assert seq == ["open", "close"]


def test_manual_save_is_registered_too(dock):
    fe, be, repo, tmp = dock
    fe.spin_pixel_x.setValue(498.5)
    fe.btn_save_px.click()
    entries = [e for e in repo.history() if e.kind == "SLIT_CENTER"]
    assert len(entries) == 1 and entries[0].method == "manual_entry"
    assert entries[0].values["center_px"] == pytest.approx(498.5)


# ── Cierre: los hilos de fondo y de la ranura ───────────────────────────────────────────────

def test_shutdown_stops_a_dark_being_taken(monkeypatch):
    import time
    from pyspectrum.drivers.andor_ccd_driver import get_andor_ccd
    from pyspectrum.drivers.shamrock_driver import get_shamrock
    from pyspectrum.modules import acquisition
    from pyspectrum.modules.acquisition import AcquisitionFailure, AcquisitionFailureKind
    from pyspectrum.modules.hardware_session import hardware_session
    from pyspectrum.modules.routines import routine_dark as rd
    hardware_session.clear_emergency()

    def slow(cam, req, should_abort=lambda: False, **kw):
        t_end = time.monotonic() + 10.0
        while time.monotonic() < t_end:
            if should_abort():
                return AcquisitionFailure(AcquisitionFailureKind.USER_STOP, None, None, "detenida")
            time.sleep(0.01)
        raise AssertionError("no se detuvo")
    monkeypatch.setattr(acquisition, "single_exposure", slow)
    ctl = rd.RoutineDark(get_andor_ccd(force_mock=True), get_shamrock(force_mock=True), "Prueba", "Prueba")
    _KEEP.append(ctl)
    ctl.take_now(0.05)
    assert ctl.thread.running
    steps = rd.shutdown_all_darks(timeout_ms=3000)
    assert steps and all(s.ok for s in steps), steps
    assert ctl.thread.wait_finished(2) and not hardware_session.is_busy


def test_the_window_stops_the_dark_and_slit_threads_on_close(monkeypatch):
    from pyspectrum.modules.hardware_session import hardware_session
    from pyspectrum.window import PySpectrumWindow
    hardware_session.clear_emergency()
    monkeypatch.setattr(QtWidgets.QMessageBox, "question", lambda *a, **k: QtWidgets.QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QtWidgets.QMessageBox, "warning", lambda *a, **k: QtWidgets.QMessageBox.StandardButton.Ok)
    win = PySpectrumWindow()
    _KEEP.append(win)
    try:
        names = [n for n, _ in win._build_shutdown([])._routines]
        assert "fondos" in names and "calibración de ranura" in names
    finally:
        win.close()
        hardware_session.clear_emergency()
