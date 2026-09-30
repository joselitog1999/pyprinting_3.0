# -*- coding: utf-8 -*-
"""Pestaña Exploración: regla, perfiles, ajuste, fondo, traza, cuadro único y guardado (paquete 2 de R4-M).

Contrato de las Rondas 2 y 3 (investigador, 2026-09-30). Ver `tests/test_exploration_analysis.py` para las
funciones sin Qt; acá se prueban el worker y el widget en pantalla virtual. La cámara falsa es la de
`test_live_loop.py` (contador de cuadros de pylablib 1.4.3).
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYPRINTING_SAFE", "1")

import numpy as np
import pytest
from PyQt6 import QtCore, QtWidgets

from test_live_loop import _Clock, _driver, _Session, _Spec

from pyspectrum.drivers import specular_interlock as si
from pyspectrum.drivers.live_stream import LiveFrame
from pyspectrum.modules import exploration_analysis as ea
from pyspectrum.ui.exploration_tab import ExplorationTabWidget, ExplorationWorker

_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["pytest"])
_KEEP = []                                           # pyqtgraph: que el recolector no destruya los ViewBox


@pytest.fixture(autouse=True, scope="module")
def _release_kept_widgets():
    """Los widgets quedan vivos (pyqtgraph), pero al terminar el módulo se desconectan del contexto global y
    se apagan el ajuste y el temporizador del fondo: si no, siguen reaccionando a los movimientos del
    espectrógrafo de los tests siguientes (Step & Glue) y cargan el hilo de la interfaz."""
    yield
    from pyspectrum.modules.spectroscopy_context import spectroscopy_context
    for w in _KEEP:
        try:
            spectroscopy_context.spectrographMoved.disconnect(w._on_spectrograph_moved)
        except (TypeError, RuntimeError):
            pass
        w.chk_fit.setChecked(False)
        w._bg_timer.stop()

H, W = 60, 200


def _gauss_frame(x0=100.0, y0=30.0, sx=3.0, sy=5.0, amp=3000.0, bias=500.0):
    yy, xx = np.mgrid[0:H, 0:W]
    rng = np.random.default_rng(1)
    return (bias + amp * np.exp(-((xx - x0) ** 2) / (2 * sx ** 2) - ((yy - y0) ** 2) / (2 * sy ** 2))
            + rng.normal(0, 3.0, (H, W))).astype(np.float32)


def _settings(**kw):
    base = dict(exposure_s=0.1, em_gain=0, output_amplifier=0, preamp_index=1, hs_index=0, vs_index=1,
                read_mode=4, grating=1, center_nm=633.0, shape=(H, W))
    base.update(kw)
    return ea.CameraSettings(**base)


def _widget(mode=si.FIRST_ORDER, settings=None):
    w = ExplorationTabWidget()
    _KEEP.append(w)
    lam = np.linspace(500.0, 500.0 + 0.1 * (W - 1), W)
    w.set_axis_provider(lambda width: ea.profile_axis(mode, lam if width == W else None, width))
    state = {"settings": settings or _settings()}
    w.set_settings_provider(lambda shape: state["settings"])
    return w, state


# ── Worker: traza, fondo y cuadro único ─────────────────────────────────────────────────────

def _worker(shape=(4, 5)):
    drv, cam = _driver(shape=shape)
    spec, sess, clock = _Spec(), _Session(), _Clock()
    w = ExplorationWorker(drv, spectrometer=spec, session=sess, clock=clock)
    return w, drv, cam, spec, sess, clock


def test_worker_trace_follows_its_source_on_every_read_frame_even_hidden():
    w, drv, cam, spec, sess, clock = _worker()
    w.set_display_visible(False)
    w.set_trace_source(ea.TraceSource("row", 1))
    w.start_live()
    for _ in range(3):
        clock.t += 0.1
        cam.produce(1); w._poll()
    t, v = w.trace_points(60.0)
    assert t.size == 3
    np.testing.assert_allclose(v, [0.0, 1.0, 2.0])      # cada cuadro vale su índice en la cámara falsa
    w.set_trace_source(ea.TraceSource("roi", 0, 4))       # cambiar de fuente limpia la traza
    assert w.trace_points(60.0)[0].size == 0


def test_worker_background_averages_n_distinct_frames_and_records_the_shutter():
    w, drv, cam, spec, sess, clock = _worker()
    got, msgs = [], []
    w.backgroundReadySignal.connect(got.append)
    w.messageSignal.connect(msgs.append)
    spec.ShamrockGetShutter = lambda dev: (20202, 0)
    w.start_live()
    w.request_background(3)
    for _ in range(4):
        cam.produce(1); w._poll()
    assert len(got) == 1
    bg = got[0]
    assert bg.n_frames == 3 and bg.first_index == 0 and bg.last_index == 2
    np.testing.assert_allclose(bg.data, 1.0)             # media de 0, 1, 2
    assert "cerrado" in bg.shutter_note and bg.settings.shape == (4, 5)


def test_worker_background_warns_when_the_shutter_reads_open():
    w, drv, cam, spec, sess, clock = _worker()
    msgs = []
    w.messageSignal.connect(msgs.append)
    spec.ShamrockGetShutter = lambda dev: (20202, 1)
    w.start_live()
    w.request_background(2)
    assert any("ABIERTO" in m for m in msgs)


def test_worker_background_needs_the_live_and_is_discarded_if_conditions_change():
    w, drv, cam, spec, sess, clock = _worker()
    got, msgs = [], []
    w.backgroundReadySignal.connect(got.append)
    w.messageSignal.connect(msgs.append)
    w.request_background(3)
    assert got == [] and any("Live" in m for m in msgs)
    w.start_live()
    w.request_background(3)
    cam.produce(1); w._poll()
    drv.set_exposure_time(0.2)                           # el operador cambió la exposición a mitad
    for _ in range(3):
        cam.produce(1); w._poll()
    assert got == [] and any("descartado" in m for m in msgs)


def test_worker_background_is_cancelled_when_the_live_stops():
    w, drv, cam, spec, sess, clock = _worker()
    msgs = []
    w.messageSignal.connect(msgs.append)
    w.start_live()
    w.request_background(3)
    w.halt_now()
    assert any("cancelado" in m for m in msgs)


def test_snap_takes_one_frame_with_the_live_stopped_and_opens_and_closes_the_shutter():
    w, drv, cam, spec, sess, clock = _worker()
    cam.get_data_dimensions = lambda: (4, 5)
    notices = []
    w.frameReadySignal.connect(lambda: notices.append(1))
    w.snap()
    assert notices == [1] and spec.calls == [1, 0]
    lf = w.take_frame()
    assert isinstance(lf, LiveFrame) and lf.data.shape == (4, 5)
    assert not cam.acquiring


@pytest.mark.parametrize("attr", ["busy_nowait", "estopped_nowait"])
def test_snap_is_refused_during_a_routine_or_estop(attr):
    w, drv, cam, spec, sess, clock = _worker()
    msgs = []
    w.messageSignal.connect(msgs.append)
    setattr(sess, attr, True)
    w.snap()
    assert msgs and spec.calls == [] and w.take_frame() is None


def test_snap_is_refused_while_the_live_runs():
    w, drv, cam, spec, sess, clock = _worker()
    msgs = []
    w.messageSignal.connect(msgs.append)
    w.start_live()
    w.snap()
    assert any("Live" in m for m in msgs)
    assert spec.calls == [1] and cam.acquiring            # no le cierra el obturador ni la cámara al Live


# ── Widget: regla y perfiles ────────────────────────────────────────────────────────────────

def test_ruler_profiles_follow_the_ruler_and_the_bands():
    w, _ = _widget()
    f = np.arange(H * W, dtype=np.float32).reshape(H, W)
    w.update_image(f)
    w.set_ruler(50, 10)
    xh, yh = w.hprofile_curve.getData()
    np.testing.assert_allclose(yh, f[10])
    xv, yv = w.vprofile_curve.getData()
    np.testing.assert_allclose(xv, f[:, 50])             # perfil vertical rotado: valor en X, fila en Y
    np.testing.assert_allclose(yv, np.arange(H))
    w.spin_band_h.setValue(3)
    np.testing.assert_allclose(w.hprofile_curve.getData()[1], f[9:12].mean(axis=0))
    w.spin_band_v.setValue(4)                            # par → impar
    assert w.spin_band_v.value() == 5
    np.testing.assert_allclose(w.vprofile_curve.getData()[0], f[:, 48:53].mean(axis=1))


def test_click_on_the_image_places_the_ruler():
    w, _ = _widget()
    w.resize(900, 700)
    w.show()
    w.update_image(np.zeros((H, W), np.float32))
    w.plot_item.vb.setRange(xRange=(0, W), yRange=(0, H), padding=0)
    _app.processEvents()
    scene_pos = w.plot_item.vb.mapViewToScene(QtCore.QPointF(120.0, 25.0))

    class Ev:
        def button(self): return QtCore.Qt.MouseButton.LeftButton
        def double(self): return False
        def scenePos(self): return scene_pos
    w._on_scene_clicked(Ev())
    assert w.ruler_x.value() == pytest.approx(120.0, abs=1.0)
    assert w.ruler_y.value() == pytest.approx(25.0, abs=1.0)
    w.hide()


def test_roi_lines_in_the_vertical_profile_follow_the_roi_and_cannot_move():
    w, _ = _widget()
    w.roi_region.setRegion([12, 40])
    lo, hi = w.vprof_roi_lines
    assert (lo.value(), hi.value()) == (12, 40)
    assert not lo.movable and not hi.movable


def test_display_is_flipped_in_x_but_data_are_not():
    import config
    w, _ = _widget()
    f = np.arange(H * W, dtype=np.float32).reshape(H, W)
    w.update_image(f)
    flip = bool(getattr(config, "EXPLORATION_DISPLAY_FLIP_X"))
    assert flip is True                                  # BANCO-56: invertido en X respecto de la Canon
    assert w.plot_item.vb.state["xInverted"] == flip
    assert w.hprofile_plot.vb.state["xInverted"] == flip
    assert w.plot_item.vb.state["yInverted"] is True
    np.testing.assert_array_equal(w.image_item.image, f.T)   # los datos no se invierten


def test_axis_units_follow_the_interlock():
    w, _ = _widget(si.FIRST_ORDER)
    w.update_image(_gauss_frame())
    assert w.profile_axis.kind == "lambda"
    assert "λ" in w.hprofile_plot.getAxis("bottom").labelText
    w2, _ = _widget(si.SPECULAR)
    w2.update_image(_gauss_frame())
    assert w2.profile_axis.kind == "pixel"
    assert "px" in w2.hprofile_plot.getAxis("bottom").labelText


def test_lambda_axis_ticks_are_round_wavelengths_at_their_pixel():
    w, _ = _widget(si.FIRST_ORDER)
    w.update_image(_gauss_frame())
    ax = w.hprofile_plot.getAxis("bottom")
    levels = ax.tickValues(0, W - 1, 400)
    px = [p for _s, vals in levels for p in vals]
    lam = np.interp(px, np.arange(W), w.profile_axis.values)
    assert px and np.allclose(lam, np.round(lam, 1), atol=1e-6)


# ── Ajuste ──────────────────────────────────────────────────────────────────────────────────

def test_fit_reports_nm_in_first_order_and_um_in_zero_order():
    w, _ = _widget(si.FIRST_ORDER)
    w.update_image(_gauss_frame())
    w.set_ruler(100, 30)
    w.chk_fit.setChecked(True)
    text = w.lbl_readout.text()
    assert "Perfil H: centro 5" in text and " nm (px " in text   # el ajuste H en nm, no sólo la λ de la regla
    assert w.hfit_curve.getData()[0] is not None and len(w.hfit_curve.getData()[0]) > 0
    assert len(w.vfit_curve.getData()[0]) > 0            # los dos perfiles
    w2, _ = _widget(si.SPECULAR)
    w2.update_image(_gauss_frame())
    w2.set_ruler(100, 30)
    w2.chk_fit.setChecked(True)
    assert "µm" in w2.lbl_readout.text()


def test_failed_fit_shows_flags_without_a_dialog():
    w, _ = _widget()
    w.update_image(np.full((H, W), 500.0, np.float32))
    w.chk_fit.setChecked(True)
    assert "sin ajuste" in w.lbl_readout.text()


# ── Saturación, niveles y congelar ──────────────────────────────────────────────────────────

def test_saturation_is_always_shown_and_uses_the_raw_frame():
    w, _ = _widget(si.FIRST_ORDER)
    f = np.full((H, W), 500.0, np.float32)
    f[5, 5] = 0.76 * 16383
    w.update_image(f)
    assert not w.lbl_saturation.isHidden() and "76 %" in w.lbl_saturation.text()
    f[6, 6] = 16383
    w.update_image(f)
    assert "1 píxel" in w.lbl_saturation.text() and "#F38BA8" in w.lbl_saturation.styleSheet()


def test_levels_modes():
    w, _ = _widget()
    w.cmb_levels.setCurrentIndex(w.cmb_levels.findData("adc"))
    w.update_image(_gauss_frame())
    assert tuple(w.image_item.levels) == (0.0, 16383.0)


def test_freeze_stops_painting_but_keeps_draining_the_mailbox():
    w, _ = _widget()
    first = _gauss_frame()
    w.update_image(first)

    class Src:
        def __init__(self): self.taken = 0
        def take_frame(self):
            self.taken += 1
            return LiveFrame(np.zeros((H, W), np.float32), 7, 1.0)
        def trace_points(self, window_s): return np.empty(0), np.empty(0)
    src = Src()
    w._live_source = src
    w.btn_freeze.setChecked(True)
    w._on_frame_ready()
    assert src.taken == 1
    np.testing.assert_array_equal(w.image_item.image, first.T)
    assert "Congelado" in w.lbl_live_stats.text()
    w.btn_freeze.setChecked(False)                       # al descongelar se pinta el último
    np.testing.assert_array_equal(w.image_item.image, np.zeros((W, H)))


def test_snap_button_only_with_the_live_stopped():
    w, _ = _widget()
    assert w.btn_snap.isEnabled()
    w.btn_live.click()
    assert not w.btn_snap.isEnabled()
    w.btn_live.click()
    assert w.btn_snap.isEnabled()


# ── Fondo en el widget ──────────────────────────────────────────────────────────────────────

def test_background_subtraction_keeps_saturation_on_raw_and_invalidates_on_changes():
    w, state = _widget()
    raw = _gauss_frame()
    raw[1, 1] = 0.82 * 16383                             # crudo en rojo; restado el fondo quedaría en amarillo
    bg = ea.Background(np.full((H, W), 500.0, np.float32), 10, _settings(), 0, 9, 1.0, "obturador cerrado (USB)")
    assert not w.chk_bg_subtract.isEnabled()
    w.on_background_ready(bg)
    assert w.chk_bg_subtract.isEnabled() and "válido" in w.lbl_bg_status.text()
    w.chk_bg_subtract.setChecked(True)
    w.update_image(raw)
    np.testing.assert_allclose(w.image_item.image, (raw - bg.data).T)
    assert w.lbl_saturation.styleSheet().count("#F38BA8") == 1   # la saturación mira el crudo
    state["settings"] = _settings(exposure_s=0.2)
    w._check_background()
    assert not w.chk_bg_subtract.isChecked() and not w.chk_bg_subtract.isEnabled()
    assert "exposición" in w.lbl_bg_status.text()
    assert w.background is bg                            # no se descarta en silencio
    state["settings"] = _settings()
    w._check_background()
    assert w.chk_bg_subtract.isEnabled() and not w.chk_bg_subtract.isChecked()


def test_background_of_another_shape_is_not_subtracted():
    w, _ = _widget()
    bg = ea.Background(np.zeros((1, W), np.float32), 10, _settings(shape=(1, W)), 0, 9, 1.0, "")
    w.set_settings_provider(lambda shape: _settings(shape=shape))
    w.on_background_ready(bg)
    w.chk_bg_subtract.setChecked(True)
    f = _gauss_frame()
    w.update_image(f)
    np.testing.assert_allclose(w.image_item.image, f.T)
    assert "forma" in w.lbl_bg_status.text()


# ── Traza en el widget ──────────────────────────────────────────────────────────────────────

def test_trace_section_sets_the_worker_source_row_or_roi():
    w, _ = _widget()

    class Src:
        def __init__(self): self.sources = []
        def set_trace_source(self, s): self.sources.append(s)
        def trace_points(self, window_s): return np.array([0.0, 1.0]), np.array([5.0, 6.0])
        def take_frame(self): return None
        def clear_trace(self): self.sources.append("clear")
    src = Src()
    w._live_source = src
    assert not w.trace_row_line.isVisible() or w.trace_container.isHidden()
    w.btn_trace_toggle.setChecked(True)
    assert src.sources[-1] == ea.TraceSource("row", int(round(w.trace_row_line.value())))
    assert w.trace_row_line.isVisible()
    w.trace_row_line.setValue(17)
    assert src.sources[-1] == ea.TraceSource("row", 17)
    w.cmb_trace_source.setCurrentIndex(w.cmb_trace_source.findData("roi"))
    y1, y2 = w.roi_region.getRegion()
    assert src.sources[-1] == ea.TraceSource("roi", int(round(min(y1, y2))), int(round(max(y1, y2))))
    assert not w.trace_row_line.isVisible()
    w.roi_region.setRegion([100, 140])
    assert src.sources[-1] == ea.TraceSource("roi", 100, 140)
    w.btn_trace_toggle.setChecked(False)
    assert src.sources[-1] is None


# ── Guardado ────────────────────────────────────────────────────────────────────────────────

def test_save_writes_an_h5_in_the_exploration_folder_and_reports_the_path(tmp_path):
    h5py = pytest.importorskip("h5py")
    w, _ = _widget()
    w.data_dir = tmp_path / "exploration"
    msgs = []
    w.statusMessageSignal.connect(msgs.append)
    w.btn_save.click()
    assert msgs and "no hay" in msgs[-1].lower()         # sin cuadro no guarda
    raw = _gauss_frame()
    w.update_image(raw)
    w.set_ruler(100, 30)
    w.btn_save.click()
    files = list((tmp_path / "exploration").glob("exploration_*.h5"))
    assert len(files) == 1 and str(files[0]) in msgs[-1]
    with h5py.File(files[0], "r") as f:
        np.testing.assert_array_equal(f["frame/raw"][()], raw)
        assert f.attrs["display_flip_x"] and f.attrs["axis_kind"] == "lambda"
        assert "cuts/horizontal" in f and "cuts/vertical" in f


def test_save_with_background_subtracted_keeps_the_raw_frame_and_the_background(tmp_path):
    h5py = pytest.importorskip("h5py")
    w, _ = _widget()
    w.data_dir = tmp_path / "exploration"
    bg = ea.Background(np.full((H, W), 500.0, np.float32), 10, _settings(), 0, 9, 1.0, "obturador cerrado (USB)")
    w.on_background_ready(bg)
    w.chk_bg_subtract.setChecked(True)
    raw = _gauss_frame()
    w.update_image(raw)
    w.btn_save.click()
    (path,) = list((tmp_path / "exploration").glob("exploration_*.h5"))
    with h5py.File(path, "r") as f:
        np.testing.assert_array_equal(f["frame/raw"][()], raw)            # nunca sólo la resta
        np.testing.assert_array_equal(f["frame/background"][()], bg.data)
        assert f.attrs["subtract_background"]


def test_an_invalid_background_is_never_subtracted_even_if_the_box_is_forced():
    w, state = _widget()
    bg = ea.Background(np.full((H, W), 500.0, np.float32), 10, _settings(), 0, 9, 1.0, "")
    w.on_background_ready(bg)
    state["settings"] = _settings(em_gain=50)
    w._check_background()
    w.chk_bg_subtract.setChecked(True)                   # a la fuerza, por código
    f = _gauss_frame()
    w.update_image(f)
    np.testing.assert_allclose(w.image_item.image, f.T)


def test_clicking_the_snap_and_background_buttons_reaches_the_worker():
    w, _ = _widget()
    calls = []

    class Src:
        camera = spectrometer = None
        def snap(self): calls.append("snap")
        def request_background(self, n): calls.append(("bg", n))
        def set_display_visible(self, v): pass
        def set_trace_source(self, s): pass

    src = Src()
    for sig in ("frameReadySignal", "statsSignal", "backgroundReadySignal", "messageSignal"):
        setattr(src, sig, type("S", (), {"connect": lambda self, f: None})())
    w.attach_live_source(src)
    w.btn_snap.click()
    w.spin_bg_n.setValue(7)
    w.btn_bg_take.click()
    assert calls == ["snap", ("bg", 7)]


def test_a_destroyed_widget_is_not_kept_alive_by_the_global_context():
    """spectroscopy_context es global: una conexión con un lambda que captura el widget lo mantenía vivo
    (y conectado) para siempre, uno por cada ventana creada. Con métodos ligados PyQt la corta sola."""
    import gc
    import weakref
    w = ExplorationTabWidget()
    ref = weakref.ref(w)
    w.deleteLater()
    del w
    for _ in range(3):
        _app.processEvents()
        gc.collect()
    assert ref() is None


def test_the_axis_is_recomputed_only_when_the_spectrograph_really_moves():
    """El panel izquierdo publica la posición del espectrógrafo en cada sondeo (1 s), se haya movido o no.
    La pestaña no puede releer el eje del Shamrock ni rehacer los ajustes cada segundo: sólo si cambian la
    red o λc. Antes, con varias pestañas vivas, eso saturaba el hilo de la interfaz."""
    from pyspectrum.modules.spectroscopy_context import spectroscopy_context
    saved = (spectroscopy_context._wavelength, spectroscopy_context._grating)   # el contexto es global
    try:
        _check_axis_recompute(spectroscopy_context)
    finally:
        spectroscopy_context._wavelength, spectroscopy_context._grating = saved


def _check_axis_recompute(spectroscopy_context):
    w, _ = _widget()
    calls = []
    lam = np.linspace(500.0, 520.0, W)
    w.set_axis_provider(lambda width: calls.append(width) or ea.profile_axis(si.FIRST_ORDER, lam, width))
    w.update_image(_gauss_frame())
    n0 = len(calls)
    spectroscopy_context.set_spectrograph_position(633.0, 1)
    n1 = len(calls)
    for _ in range(5):
        spectroscopy_context.set_spectrograph_position(633.0, 1)   # el sondeo, sin movimiento
    assert len(calls) == n1 and n1 == n0 + 1
    spectroscopy_context.set_spectrograph_position(700.0, 1)
    spectroscopy_context.set_spectrograph_position(700.0, 2)
    assert len(calls) == n1 + 2
