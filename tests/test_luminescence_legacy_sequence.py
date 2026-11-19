# -*- coding: utf-8 -*-
"""Luminiscencia con la secuencia completa del legado y sus bases (DEC-054).

Bases:
- un solo eje λ (EEPROM, GetCalibration de respaldo) con su fuente;
- el fotodiodo del láser elegido, no siempre ai0;
- la fila de la fibra en Single-Track (438 ± 12 del legado = SDK 439, alto 25);
- los archivos del legado con su formato, y el TIFF NPscan crudo también en PyPrinting.
Secuencia, contra un satélite simulado:
- sin satélite, o con autofoco y sin lock, no arranca ni toma la sesión;
- por nodo: centrado (TIFF crudos), espejo abajo, mini-mapa con el láser abierto todo el mapa y cerrado al
  terminar, espejo arriba; archivos del legado y el .h5;
- un Stop a mitad del mapa guarda lo medido como interrumpido;
- refrescar la referencia corre el resto de la grilla por (centro del mapa − nodo nominal).
"""
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYPRINTING_SAFE", "1")

import numpy as np
import pytest
from PyQt6 import QtCore

import config
from core import nidaq
from pyspectrum.drivers.andor_ccd_driver import get_andor_ccd
from pyspectrum.drivers.shamrock_driver import get_shamrock, SHAMROCK_SUCCESS
from pyspectrum.modules.hardware_session import hardware_session
from pyspectrum.modules.routines import luminescence as lm
from pyspectrum.modules.routines import luminescence_grid as lg
from pyspectrum.modules.routines.grid_runner import FiberROI
from pyspectrum.services import legacy_files as lf
from pyspectrum.services.satellite_optics import (CenterResult, CenterScanSpec, OpticsUnavailable, SatelliteOptics,
                                                  FOCUS_LOCK_MISSING, SATELLITE_MISSING)
from pyspectrum.services.spectral_axis import spectral_axis, SOURCE_EEPROM, SOURCE_GETCALIBRATION

LASER = config.SHUTTERS[0]


# ── bases ───────────────────────────────────────────────────────────────────────

def test_the_spectral_axis_comes_from_the_eeprom_with_its_source():
    sh = get_shamrock(force_mock=True)
    ax = spectral_axis(sh, 1004)
    ret, a, b, c, d = sh.ShamrockGetPixelCalibrationCoefficients(0)
    p = np.arange(1004.0)
    np.testing.assert_allclose(ax.nm, a + b * p + c * p ** 2 + d * p ** 3)
    assert ax.source == SOURCE_EEPROM and ax.n_pixels == 1004


def test_the_spectral_axis_falls_back_to_getcalibration_and_never_invents_one():
    class NoEeprom:
        def ShamrockGetPixelCalibrationCoefficients(self, dev):
            return (20201, 0.0, 0.0, 0.0, 0.0)

        def ShamrockGetCalibration(self, dev, n):
            return (SHAMROCK_SUCCESS, np.linspace(600.0, 500.0, n))     # decreciente: también vale

    ax = spectral_axis(NoEeprom(), 1004)
    assert ax.source == SOURCE_GETCALIBRATION and ax.nm[0] == 600.0

    class Broken(NoEeprom):
        def ShamrockGetCalibration(self, dev, n):
            return (20201, np.full(n, np.nan))
    assert spectral_axis(Broken(), 1004) is None


def test_the_photodiode_is_the_one_of_the_chosen_laser():
    from pyspectrum.modules.optical_support import photodiode_index
    for laser, ai in config.PD_CHANNELS.items():
        assert config.PD_CHANS_LIST[photodiode_index(laser)] == ai
    assert photodiode_index(None) == 0
    with pytest.raises(ValueError):
        photodiode_index("405 nm (blue)")


def test_the_fiber_roi_matches_the_legacy_rows_and_the_sdk_track():
    roi = FiberROI()
    assert roi.rows == (426, 450) and roi.sdk_track == (439, 25)
    with pytest.raises(ValueError):
        FiberROI(5, 25)                                      # sale del detector


def test_legacy_files_have_the_legacy_format(tmp_path):
    from PIL import Image
    img = np.arange(12, dtype=float).reshape(3, 4) * 1.5e-3
    paths = lf.write_npscan_tiffs(str(tmp_path), 7, img, img + 1, img + 2)
    assert [os.path.basename(p) for p in paths] == ["NPscan_007.tiff", "gone_NPscan_007.tiff", "back_NPscan_007.tiff"]
    back = np.array(Image.open(paths[0]))
    np.testing.assert_allclose(back, img.T.astype(np.float32))           # crudo y traspuesto, como el legado
    w = lf.write_wavelength(str(tmp_path), np.linspace(500, 600, 1004), stamp="X")
    assert np.loadtxt(w).shape == (1004,)
    s = lf.write_pixel_spectrum(str(tmp_path), 2, 3, np.ones(1004))
    assert os.path.basename(s) == "Spectrum_i0002_j0003.txt" and np.loadtxt(s).shape == (1004,)
    t = lf.write_trace_bs(str(tmp_path), [0.1, 0.2], [1.0, 1.1])
    assert np.loadtxt(t).shape == (2, 2)
    assert lf.node_folder_name("Slow_Confocal_Spectrum", 1, 2) == "Slow_Confocal_Spectrum_Col_001_NP_002"


def test_pyprinting_npscan_tiff_is_raw(tmp_path, app):
    from PIL import Image
    import modules.measurements as meas
    be = meas.Backend(mode="printing")
    be.new_folder = str(tmp_path)
    be.i_global = 4
    be.node_results = {}
    img = np.array([[0.123, 0.456], [1.5, 2.25]])
    be._save_scan(img, img * 2, img * 3)
    back = np.array(Image.open(tmp_path / "NPscan_004.tiff"))
    assert back.dtype == np.float32
    np.testing.assert_allclose(back, img.T, rtol=1e-6)   # intensidad absoluta, no normalizada a uint16


# ── cálculos del legado ─────────────────────────────────────────────────────────

def test_band_value_and_minimap_geometry_follow_the_legacy():
    wave = np.array([530.0, 540.0, 560.0, 580.0, 590.0])
    assert lg.band_value(wave, [1, 2, 3, 4, 5], (540, 580)) == 9.0
    xs, ys = lg.minimap_positions(50.0, 40.0, 1.0, 4, 2)
    np.testing.assert_allclose(xs, [49.5, 49.75, 50.0, 50.25])
    np.testing.assert_allclose(ys, [39.5, 40.0])


def test_map_center_of_mass_follows_the_legacy():
    Z = np.zeros((5, 5))
    Z[3, 1] = 10.0                                         # j = 3 (y), i = 1 (x)
    x, y, xcm, ycm = lg.map_center_of_mass(Z, 50.0, 50.0, 1.0, 0.7)
    assert (xcm, ycm) == (1.0, 3.0)
    assert (x, y) == (round(49.5 + 1 * 0.2, 3), round(49.5 + 3 * 0.2, 3))
    assert lg.map_center_of_mass(np.ones((3, 3)), 0, 0, 1.0) is None


# ── satélite ────────────────────────────────────────────────────────────────────

class _FakeConfocal(QtCore.QObject):
    scanfinishedSignal = QtCore.pyqtSignal(np.ndarray, list, np.ndarray, np.ndarray, str, str)

    def __init__(self):
        super().__init__()
        self.range_x = self.range_y = 2.0
        self.Nx = self.Ny = 34
        self.scan_mode_option, self.psf_mode_option = "Step by step", "x/z"
        self.method_center_opt, self.threshold_filter_val = "center of gauss", 0.5
        self.started = []

    @QtCore.pyqtSlot(str)
    def scan_mode(self, v): self.scan_mode_option = v

    @QtCore.pyqtSlot(str)
    def psf_mode(self, v): self.psf_mode_option = v

    @QtCore.pyqtSlot(str)
    def method_center(self, v): self.method_center_opt = v

    @QtCore.pyqtSlot(float)
    def set_threshold_filter(self, v): self.threshold_filter_val = v

    @QtCore.pyqtSlot(list)
    def scan_ramp_parameters(self, p): self.range_x, self.range_y, self.Nx, self.Ny = p

    @QtCore.pyqtSlot()
    def stop_scan(self): pass

    @QtCore.pyqtSlot(str, str, str)
    def start_scan_routines(self, laser, mode, number):
        self.started.append((laser, mode, number, self.range_x, self.Nx, self.scan_mode_option,
                             self.method_center_opt, self.threshold_filter_val))
        img = np.ones((self.Ny, self.Nx))
        self.scanfinishedSignal.emit(img, [41.0, 42.0], img, img, mode, number)


def test_the_center_scan_uses_the_routine_settings_and_restores_the_operators(app):
    cf = _FakeConfocal()
    opt = SatelliteOptics(focus_backend=None, confocal_backend=cf)
    res = opt.center_scan("637 nm (red)", CenterScanSpec(range_um=1.5, pixels=10, threshold=0.2),
                          lambda: False, lambda: None, number="003")
    assert (res.x_um, res.y_um) == (41.0, 42.0) and res.image.shape == (10, 10)
    assert cf.started == [("637 nm (red)", "luminescence", "003", 1.5, 10, "Ramp", "center of mass", 0.2)]
    # lo que el operador tenía en el panel del satélite vuelve
    assert (cf.range_x, cf.Nx, cf.scan_mode_option, cf.method_center_opt, cf.threshold_filter_val) == \
           (2.0, 34, "Step by step", "center of gauss", 0.5)


def test_the_autofocus_needs_the_operators_lock():
    focus = type("F", (), {"locked_focus": False})()
    with pytest.raises(OpticsUnavailable, match="lock"):
        SatelliteOptics(focus, None).autofocus(LASER, lambda: False, lambda: None)


# ── secuencia completa ──────────────────────────────────────────────────────────

class _FakeOptics:
    """El satélite simulado: el centro está siempre 0.1 µm a la derecha de donde está la platina."""

    def __init__(self, lock=True):
        self.lock, self.calls = lock, []

    def has_focus_lock(self):
        return self.lock

    def autofocus(self, laser, should_abort, tick, timeout_s=30.0):
        self.calls.append(("af", laser))
        return True

    def center_scan(self, laser, spec, should_abort, tick, label="luminescence", number="none", timeout_s=120.0):
        pos = config.pi.qPOS()
        self.calls.append(("center", laser, spec.range_um, spec.pixels))
        img = np.random.default_rng(0).random((spec.pixels, spec.pixels))
        return CenterResult(float(pos["1"]) + 0.1, float(pos["2"]), img, img, img)


@pytest.fixture
def be(tmp_path):
    hardware_session.clear_emergency()
    b = lm.LuminescenceBackend(get_andor_ccd(force_mock=True), get_shamrock(force_mock=True))
    b.data_dir = str(tmp_path / "lum")
    b.generate_grid(1, 2, 3.0, 0.0, 40.0, 40.0, 5.0)
    yield b
    b.abort_grid()
    b.grid_thread.wait_finished(10)
    hardware_session.clear_emergency()
    nidaq.close_all_shutters()


def _cfg(**kw):
    c = {"laser": LASER, "exp_time": 0.01, "autofocus_every": 1, "center_enabled": True, "center_range_um": 1.0,
         "center_pixels": 8, "minimap_enabled": True, "map_range_um": 0.4, "map_nx": 2, "map_ny": 2,
         "band_lo_nm": 0.0, "band_hi_nm": 5000.0, "save_dir": "", "mirror": "up"}
    c.update(kw)
    return c


def test_without_the_satellite_the_grid_does_not_start(be):
    msgs = []
    be.gridPreflightSignal.connect(msgs.append)
    be.start_grid(_cfg())
    assert not be._grid_running and not hardware_session.is_busy
    assert msgs == [SATELLITE_MISSING]


def test_autofocus_without_the_lock_does_not_start(be):
    be.optics_provider = lambda: _FakeOptics(lock=False)
    msgs = []
    be.gridPreflightSignal.connect(msgs.append)
    be.start_grid(_cfg())
    assert not be._grid_running and msgs == [FOCUS_LOCK_MISSING]


def test_the_full_legacy_sequence_writes_both_formats(be, tmp_path, monkeypatch):
    optics = _FakeOptics()
    be.optics_provider = lambda: optics
    log = []
    real_open, real_close, real_mirror = lm.open_shutter, lm.close_shutter, lm.flipper_notch532
    monkeypatch.setattr(lm, "open_shutter", lambda n, *a, **k: log.append(("open", n)) or real_open(n))
    monkeypatch.setattr(lm, "close_shutter", lambda n: log.append(("close", n)) or real_close(n))
    monkeypatch.setattr(lm, "flipper_notch532", lambda p: log.append(("mirror", p)) or real_mirror(p))
    be.start_grid(_cfg())
    assert be.grid_thread.wait_finished(30)
    assert be.states == [lm.NODE_DONE, lm.NODE_DONE]
    assert be.camera.get_single_track() == (439, 25)              # la fila de la fibra, en Single-Track
    assert [c[0] for c in optics.calls] == ["af", "center", "af", "center"]
    # el láser de la rutina se abre una vez por nodo, con el espejo ya abajo, y se cierra al terminar el mapa
    opens = [i for i, e in enumerate(log) if e == ("open", LASER)]
    assert len(opens) == 2
    for i in opens:
        assert ("mirror", "down") in log[:i] and log[i + 1:].index(("close", LASER)) >= 0
    assert log[-1] == ("mirror", "up")
    assert not nidaq.get_open_shutter_names()

    run = next(p for p in (tmp_path / "lum").iterdir() if p.is_dir())
    assert run.name.endswith("_Luminescence_1x2_3umx0um")
    assert {p.name for p in run.glob("*NPscan_*.tiff")} == {
        f"{pre}NPscan_{k:03d}.tiff" for pre in ("", "gone_", "back_") for k in (0, 1)}
    node = run / "Slow_Confocal_Spectrum_Col_001_NP_000"
    spectra = sorted(p.name for p in node.glob("Spectrum_i*_j*.txt"))
    assert spectra == ["Spectrum_i0000_j0000.txt", "Spectrum_i0000_j0001.txt",
                       "Spectrum_i0001_j0000.txt", "Spectrum_i0001_j0001.txt"]
    assert np.loadtxt(node / spectra[0]).shape == (1004,)
    assert np.loadtxt(next(node.glob("wavelength_*.txt"))).shape == (1004,)
    assert len(list(node.glob("Slow_Confocal_Spectrum*.tiff"))) == 1
    assert np.loadtxt(node / "Trace_BS.txt").shape == (4, 2)
    info = (run / "Info.txt").read_text(encoding="utf-8")
    assert "Axis_source EEPROM" in info and "Read_mode Single-Track" in info and "Nodes_done 2" in info
    import h5py
    with h5py.File(next(run.glob("*.h5")), "r") as f:
        assert f.attrs["wavelength_source"] == SOURCE_EEPROM and f["wavelength_nm"].shape == (1004,)
        g = f["node_000"]
        assert g.attrs["status"] == "done" and g["cube"].shape == (2, 2, 1004)
        assert g["center_image"].shape == (8, 8) and "map_cm_um" in g.attrs


def test_a_stop_during_the_map_keeps_what_was_measured(be, tmp_path, monkeypatch):
    be.optics_provider = lambda: _FakeOptics()
    real = lg.LuminescenceRunWriter.write_pixel

    def stop_after_first(self, d, i, j, spec):
        real(self, d, i, j, spec)
        be.abort_grid()
    monkeypatch.setattr(lg.LuminescenceRunWriter, "write_pixel", stop_after_first)
    be.start_grid(_cfg(autofocus_every=0, map_nx=3, map_ny=3))
    assert be.grid_thread.wait_finished(30)
    assert not nidaq.get_open_shutter_names()
    run = next(p for p in (tmp_path / "lum").iterdir() if p.is_dir())
    import h5py
    with h5py.File(next(run.glob("*.h5")), "r") as f:
        g = f["node_000"]
        assert g.attrs["status"] == "interrupted"
        assert np.isfinite(g["map_image"][0, 0]) and np.isnan(g["map_image"][2, 2])


def test_refresh_reference_shifts_the_rest_of_the_grid(be):
    be.optics_provider = lambda: _FakeOptics()
    targets = []
    real = lg.LuminescenceGridEngine.run_node

    def spy(self, index, node):
        rec = real(self, index, node)
        targets.append((rec.nominal[:2], rec.target[:2], rec.map_cm))
        return rec
    import unittest.mock as um
    with um.patch.object(lg.LuminescenceGridEngine, "run_node", spy):
        be.start_grid(_cfg(autofocus_every=0, refresh_reference=True))
        assert be.grid_thread.wait_finished(30)
    (n0, t0, cm0), (n1, t1, _cm1) = targets
    assert t0 == n0                                           # el primer nodo, sin corrimiento
    assert t1 == pytest.approx((n1[0] + cm0[0] - n0[0], n1[1] + cm0[1] - n0[1]))


# ── interfaz (Ronda 3) ──────────────────────────────────────────────────────────

def test_the_tab_sends_the_engine_contract_and_keeps_its_controls_in_sync(app):
    panel = lm.LuminescencePanel()
    sent = []
    panel.startGridSignal.connect(sent.append)
    rois = []
    panel.fiberRoiChangedSignal.connect(lambda c, h: rois.append((c, h)))
    panel.spin_map_nx.setValue(7)
    assert panel.spin_map_ny.value() == 7                     # candado Ny = Nx
    panel.band_region.setRegion((550.0, 600.0))
    assert (panel.spin_band_lo.value(), panel.spin_band_hi.value()) == (550.0, 600.0)
    panel.spin_band_hi.setValue(610.0)
    assert panel.band_region.getRegion()[1] == pytest.approx(610.0)
    panel.spin_roi_center.setValue(440)
    assert rois[-1] == (440, 25)
    panel.cmb_grid_mirror.setCurrentIndex(2)
    panel._on_start_grid()
    cfg = sent[0]
    backend = lm.LuminescenceBackend(get_andor_ccd(force_mock=True), get_shamrock(force_mock=True))
    params = backend._params_from_config(cfg)                 # 0 discrepancias GUI ↔ motor
    assert params.minimap.nx == params.minimap.ny == 7 and params.minimap.band_nm == (550.0, 610.0)
    assert params.roi == FiberROI(440, 25) and params.minimap.exposure_s == 2.0
    assert params.center.pixels == 34 and params.autofocus_every == 2 and params.laser == LASER
    panel.show_preflight(SATELLITE_MISSING)
    assert not panel.lbl_preflight.isHidden()
    panel.show_preflight("")
    assert panel.lbl_preflight.isHidden()
    assert "Estimado" in panel.lbl_estimate.text()
    panel.deleteLater()
    backend.deleteLater()


# ── Luminiscencia S&G (DEC-055) ─────────────────────────────────────────────────

def _frame(fiber_value=100.0, bkg_value=10.0):
    f = np.zeros((1002, 1004))
    f[426:451, :] = fiber_value                                # filas de la fibra (438 ± 12)
    f[188:213, :] = bkg_value                                  # filas del fondo (200 ± 12)
    return f


def test_rows_mean_and_the_legacy_step_glue_files(tmp_path):
    from PIL import Image
    np.testing.assert_allclose(lf.rows_mean(_frame(), FiberROI()), np.full(1004, 100.0))
    np.testing.assert_allclose(lf.rows_mean(_frame(), FiberROI(200, 25)), np.full(1004, 10.0))
    axes = [np.linspace(400, 500, 1004), np.linspace(480, 580, 1004)]
    paths = lf.write_step_glue(str(tmp_path), axes, [_frame(), _frame()], [np.ones(1004)] * 2, [np.zeros(1004)] * 2,
                               stamp="20261119_120000")
    names = sorted(os.path.basename(p) for p in paths)
    assert names == ["20261119_120000_Calibration_Shamrock_Spectrum_step_0002.txt",
                     "20261119_120000_Picture_Andor_Spectrum_step_0002.tiff",
                     "Background_Line_Spectrum_step_0002.txt", "Line_Spectrum_step_0002.txt"]
    assert np.loadtxt(tmp_path / "Line_Spectrum_step_0002.txt").shape == (2 * 1004,)       # sin coser
    img = np.array(Image.open(tmp_path / "20261119_120000_Picture_Andor_Spectrum_step_0002.tiff"))
    assert img.shape == (1002, 2 * 1004) and img.dtype == np.uint16                     # como el legado


def test_step_glue_params_and_validation():
    sg = lg.NodeStepGlueSpec()
    assert (sg.start_nm, sg.end_nm, sg.overlap, sg.exposure_s) == (400.0, 800.0, 0.2, 1.0)
    assert sg.background_roi.rows == (188, 212)
    with pytest.raises(ValueError):
        lg.NodeStepGlueSpec(start_nm=800, end_nm=400)
    p = lg.LuminescenceGridParams(laser=LASER, measure="step_glue")
    assert p.mode == "step_glue" and p.exposure_s == 1.0
    assert lg.LuminescenceGridParams(laser=LASER, minimap=lg.MiniMapSpec(enabled=False)).mode == "single"
    with pytest.raises(ValueError):
        lg.LuminescenceGridParams(laser=LASER, measure="growth")


class _FakeRunner:
    """Registra el orden de potencia, espejo y láser."""

    def __init__(self):
        self.log, self.camera, self.tick = [], object(), (lambda: None)
        self._should_abort = lambda: False

    def aborted(self):
        return False

    def move_to(self, x, y, z=None):
        self.log.append(("move", round(x, 3), round(y, 3)))
        return x, y, z

    def set_power(self, level):
        self.log.append(("power", level))

    def set_mirror(self, pos):
        self.log.append(("mirror", pos))

    def laser(self, name, open_):
        self.log.append(("laser", open_))


def _fake_run_windows(frames, complete=True, reason=None):
    from types import SimpleNamespace
    from pyspectrum.modules.step_glue_engine import StopReason

    def run(the_plan, request, camera, spectrometer, *, run_dir, should_abort, on_tick, is_estopped, on_window,
            on_no_signal):
        wins = []
        for i, f in enumerate(frames):
            w = SimpleNamespace(index=i, data=f, wavelength_axis=np.linspace(400 + 80 * i, 503 + 80 * i, 1004),
                                center_nm_requested=451.5 + 80 * i, path=None)
            on_window(w)
            wins.append(w)
        return SimpleNamespace(complete=complete, detail="ventanas" if complete else "barrido detenido",
                               stop_reason=reason or StopReason.COMPLETED, windows=tuple(wins))
    return run


def test_the_step_glue_node_follows_the_legacy_sequence_and_writes_both_formats(tmp_path):
    import h5py
    from types import SimpleNamespace
    p = lg.LuminescenceGridParams(laser=LASER, measure="step_glue", autofocus_every=1, grid_name="1x1")
    w = lg.LuminescenceRunWriter(str(tmp_path), p, np.linspace(400, 503, 1004), "EEPROM")
    assert "_Luminescence_Steps_1x1" in w.run_dir
    r = _FakeRunner()
    eng = lg.LuminescenceGridEngine(r, _FakeOptics(), p, np.linspace(400, 503, 1004), w, lambda: 1.0,
                                    sg_plan=SimpleNamespace(centers=[451.5, 531.5]), sg_request=object(),
                                    run_windows=_fake_run_windows([_frame(), _frame(120.0, 12.0)]))
    rec = eng.run_node(0, (40.0, 40.0, None))
    assert rec.status == "done" and rec.sg_complete
    kinds = [e for e in r.log if e[0] in ("power", "mirror", "laser")]
    # potencia baja para enfocar y centrar, alta para medir; espejo abajo antes de abrir el láser
    assert kinds.index(("power", "low")) < kinds.index(("power", "high")) < kinds.index(("mirror", "down")) \
        < kinds.index(("laser", True)) < kinds.index(("laser", False))
    assert kinds[-1] == ("mirror", "up")
    np.testing.assert_allclose(rec.sg_fiber[1], np.full(1004, 120.0))
    np.testing.assert_allclose(rec.sg_background[0], np.full(1004, 10.0))
    node = os.path.join(w.run_dir, "Spectrum_luminescence_Col_001_NP_000")
    assert np.loadtxt(os.path.join(node, "Line_Spectrum_step_0002.txt")).shape == (2008,)
    assert np.loadtxt(os.path.join(node, "Background_Line_Spectrum_step_0002.txt")).shape == (2008,)
    with h5py.File(w.h5_path, "r") as f:
        g = f["node_000"]
        assert g["sg_fiber_mean"].shape == (2, 1004) and g.attrs["sg_complete"]
        assert g["glued"].size > 1004 and g["glued_nm"][0] < g["glued_nm"][-1]          # el cosido de 3.0
        assert f.attrs["read_mode"] == "Image"


def test_a_stopped_step_glue_keeps_the_windows_and_marks_the_node_interrupted(tmp_path):
    import h5py
    from types import SimpleNamespace
    from pyspectrum.modules.routines.grid_runner import GridAbort
    from pyspectrum.modules.step_glue_engine import StopReason
    p = lg.LuminescenceGridParams(laser=LASER, measure="step_glue", autofocus_every=0, center_enabled=False)
    w = lg.LuminescenceRunWriter(str(tmp_path), p, np.linspace(400, 503, 1004), "EEPROM")
    r = _FakeRunner()
    eng = lg.LuminescenceGridEngine(r, None, p, np.linspace(400, 503, 1004), w, lambda: 1.0,
                                    sg_plan=SimpleNamespace(centers=[451.5, 531.5, 611.5]), sg_request=object(),
                                    run_windows=_fake_run_windows([_frame()], complete=False,
                                                                  reason=StopReason.USER_STOP))
    with pytest.raises(GridAbort):
        eng.run_node(0, (40.0, 40.0, None))
    assert ("laser", False) in r.log
    with h5py.File(w.h5_path, "r") as f:
        g = f["node_000"]
        assert g.attrs["status"] == "interrupted" and g["sg_fiber_mean"].shape == (1, 1004)
        assert not g.attrs["sg_complete"] and "glued" not in g


def test_the_step_glue_grid_runs_end_to_end_with_the_real_engine(be, tmp_path):
    from pyspectrum.drivers.andor_ccd_driver import READ_MODE_IMAGE
    be.optics_provider = lambda: _FakeOptics()
    be.generate_grid(1, 1, 3.0, 0.0, 40.0, 40.0, 5.0)
    be.start_grid(_cfg(measure="step_glue", autofocus_every=0, sg_start_nm=500.0, sg_end_nm=560.0,
                       sg_overlap=0.2, sg_exposure_s=0.01))
    assert be.grid_thread.wait_finished(60)
    assert be.states == [lm.NODE_DONE], be.states
    assert be.camera.get_read_mode() == READ_MODE_IMAGE
    run = next(p for p in (tmp_path / "lum").iterdir() if p.is_dir())
    assert "_Luminescence_Steps_" in run.name
    node = run / "Spectrum_luminescence_Col_001_NP_000"
    lines = list(node.glob("Line_Spectrum_step_*.txt"))
    assert len(lines) == 1 and np.loadtxt(lines[0]).size % 1004 == 0
    assert list((node / "ventanas_3.0").glob("ventana_*.npz"))                         # el formato de 3.0
    assert not nidaq.get_open_shutter_names() and not hardware_session.is_busy


def test_a_specular_step_glue_range_does_not_start(be):
    be.optics_provider = lambda: _FakeOptics()
    msgs = []
    be.gridPreflightSignal.connect(msgs.append)
    be.start_grid(_cfg(measure="step_glue", autofocus_every=0, sg_start_nm=5.0, sg_end_nm=40.0))
    assert not be._grid_running and msgs and "especular" in msgs[0]


def test_the_tab_sends_the_step_glue_contract(app):
    panel = lm.LuminescencePanel()
    sent, modes = [], []
    panel.startGridSignal.connect(sent.append)
    panel.measureModeChangedSignal.connect(modes.append)
    panel.cmb_measure.setCurrentIndex(panel.cmb_measure.findData("step_glue"))
    assert modes[-1] == "step_glue" and not panel.box_sg.isHidden() and not panel.plot_sg.isHidden()
    assert not panel.spin_map_nx.isEnabled() and not panel.spin_grid_exp.isEnabled()
    panel.spin_sg_start.setValue(450.0)
    panel.spin_sg_overlap.setValue(25.0)
    panel.spin_bkg_center.setValue(210)
    panel.cmb_grid_mirror.setCurrentIndex(2)
    panel._on_start_grid()
    backend = lm.LuminescenceBackend(get_andor_ccd(force_mock=True), get_shamrock(force_mock=True))
    params = backend._params_from_config(sent[0])
    assert params.mode == "step_glue" and params.step_glue.start_nm == 450.0
    assert params.step_glue.overlap == pytest.approx(0.25) and params.step_glue.background_roi == FiberROI(210, 25)
    panel.update_sg_window(np.linspace(400, 500, 1004), np.ones(1004), 0, 2)
    assert len(panel._sg_curves) == 1
    panel.deleteLater()
    backend.deleteLater()
