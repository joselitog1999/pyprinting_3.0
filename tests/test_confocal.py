# -*- coding: utf-8 -*-
"""
test_confocal.py — Pruebas unitarias para las correcciones de seguridad de
modules/confocal.py y contrapropagante.py (auditoría multi-agente 2026-09-18,
hallazgos ANOM-CONFOCAL-02/03/04 y ANOM-CONTRAPROP-01a):

1. ANOM-CONFOCAL-02: los 7 sitios que llamaban heartbeat_shutter(30.0) (6 en
   confocal.py, 1 en contrapropagante.py) ahora llaman heartbeat_shutter() sin
   argumentos, respetando la política global de timeout configurada en el dock de
   Shutters en vez de sobreescribirla en cada iteración de scan.
2. ANOM-CONFOCAL-03: en _scan_step_xy, el asentamiento largo (35ms) ahora se aplica
   al primer píxel de cada fila (el que sigue al flyback real, self.i==0), no en la
   rama de fin de fila anterior — donde el pi.MOV del flyback todavía no se había
   ejecutado (ocurre recién en el tick siguiente).
3. ANOM-CONFOCAL-04 / ANOM-CONTRAPROP-01a: las transiciones de fila en modo rampa
   (_scan_ramp_xy en ambos archivos) confirman asentamiento físico (qONT, acotado en
   tiempo) antes de disparar el wave-table (pi.WGO), en vez de hacerlo inmediatamente
   tras el pi.MOV().
4. Paridad de modos PSF en el confocal dual (contrapropagante.py): x/z, y/x, y/z ahora
   están realmente implementados (antes el combo era decorativo — start_scan() siempre
   corría x/y sin importar la selección), mirando la implementación ya existente en
   modules/confocal.py.

PyPrinting 3.0 — UNSAM Nanofotónica
"""
import os
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ["PYPRINTING_SAFE"] = "1"

# Ver conftest.py: config debe importarse antes que PyQt6 en este entorno.
import config  # noqa: F401
import numpy as np
import pytest
import modules.confocal as confocal_mod
import contrapropagante as cp_mod


class _FakeStepTask:
    def __init__(self, n_channels: int, samps: int):
        self.n_channels = n_channels
        self.samps = samps
        self.close_calls = 0

    def read(self, samps=None):
        n = samps or self.samps
        return [list(np.full(n, 0.5)) for _ in range(self.n_channels)]

    def close(self):
        self.close_calls += 1


# ── ANOM-CONFOCAL-04 — helper de asentamiento acotado ───────────────────────

def test_wait_axis_settle_returns_promptly_when_stalled(app, monkeypatch):
    backend = confocal_mod.Backend()
    monkeypatch.setattr(confocal_mod.pi, "qONT", lambda axes=None: {2: False})

    t0 = time.time()
    backend._wait_axis_settle(2, timeout_s=0.1)  # no debe lanzar, no debe colgar
    elapsed = time.time() - t0

    assert elapsed < 1.0, "El poll de asentamiento debe respetar timeout_s, no colgar"


def test_wait_axis_settle_returns_immediately_when_on_target(app):
    backend = confocal_mod.Backend()  # mock qONT() siempre True por defecto
    t0 = time.time()
    backend._wait_axis_settle(2, timeout_s=0.1)
    assert time.time() - t0 < 0.1


# ── ANOM-CONFOCAL-03 — settle largo solo en el primer píxel post-flyback ────

def test_scan_step_xy_applies_long_settle_only_on_flyback_pixel(app, monkeypatch):
    backend = confocal_mod.Backend()
    backend._scan_step_parameters([2, 2, 3, 2])  # Nx=3, Ny=2
    backend.matrix_scan_step = [np.array([0.0, 1.0, 2.0]), np.array([0.0, 1.0])]
    backend.i = 0
    backend.j = 0
    backend.signal_scan_stop = False
    backend._step_task = None
    backend.image = np.zeros((2, 3))

    fake_task = _FakeStepTask(len(confocal_mod.PD_CHANS_LIST), backend.Nph)
    monkeypatch.setattr(confocal_mod, "channels_photodiodos", lambda rate, n: fake_task)
    monkeypatch.setattr(confocal_mod, "heartbeat_shutter", lambda *a, **k: None)

    # `confocal_mod.time` es el módulo `time` global: el reemplazo alcanza a todos los hilos del
    # proceso. Se registran sólo las llamadas de este hilo; las demás (p. ej. el `sleep(0.1)` del
    # ShutterWatchdog, vivo por tests anteriores) siguen con el `sleep` real. Sin esto, el test
    # capturaba decenas de miles de llamadas ajenas según el orden de la suite (DEC-039).
    import threading
    real_sleep = confocal_mod.time.sleep
    test_thread = threading.current_thread()
    sleeps = []

    def _record_sleep(s):
        if threading.current_thread() is test_thread:
            sleeps.append(s)
        else:
            real_sleep(s)

    monkeypatch.setattr(confocal_mod.time, "sleep", _record_sleep)

    backend._scan_step_xy()  # i=0 (flyback real del inicio) -> settle largo
    backend._scan_step_xy()  # i=1 -> settle normal
    backend._scan_step_xy()  # i=2 -> settle normal
    backend._scan_step_xy()  # i==Nx -> fin de fila: sin sleep propio (i=0, j=1)
    backend._scan_step_xy()  # i=0 de la fila 2 -> este SÍ es el pixel post-flyback real

    assert sleeps == [0.035, 0.003, 0.003, 0.035], (
        "Solo el píxel que sigue al flyback real (self.i==0 antes del MOV) debe usar "
        "el asentamiento largo; la rama de fin de fila no debe agregar su propio sleep"
    )


# ── ANOM-CONFOCAL-02 / 04 — _scan_ramp_xy: heartbeat sin hardcodear + settle ─

def test_scan_ramp_xy_confirms_settle_before_ramp_and_uses_bare_heartbeat(app, monkeypatch):
    backend = confocal_mod.Backend()
    backend._scan_ramp_parameters([2, 2, 3, 3])
    backend.i = 0
    backend.image_gone = np.zeros((3, 3))
    backend.image_back = np.zeros((3, 3))
    backend.image = np.zeros((3, 3))
    backend.tic = time.time()
    backend.tilt_correction_enabled = False

    settle_calls = []
    monkeypatch.setattr(backend, "_wait_axis_settle",
                         lambda axes, timeout_s=0.05: settle_calls.append(axes) or True)
    monkeypatch.setattr(backend, "_ramp_x_line", lambda: (np.ones(30), np.ones(30)))

    hb_calls = []
    monkeypatch.setattr(confocal_mod, "heartbeat_shutter",
                         lambda *a, **k: hb_calls.append((a, k)))

    backend._scan_ramp_xy()

    assert settle_calls == [2], "Debe confirmar asentamiento del eje Y (2) antes de disparar la rampa"
    assert hb_calls == [((), {})], "Debe usar heartbeat_shutter() sin argumentos (política global)"


def test_scan_ramp_xy_tilt_correction_settles_both_axes(app, monkeypatch):
    backend = confocal_mod.Backend()
    backend._scan_ramp_parameters([2, 2, 3, 3])
    backend.i = 0
    backend.image_gone = np.zeros((3, 3))
    backend.image_back = np.zeros((3, 3))
    backend.image = np.zeros((3, 3))
    backend.tic = time.time()
    backend.tilt_correction_enabled = True
    backend.tilt_plane = None  # _evaluate_tilt_z cae a z_pos

    settle_calls = []
    monkeypatch.setattr(backend, "_wait_axis_settle",
                         lambda axes, timeout_s=0.05: settle_calls.append(axes) or True)
    monkeypatch.setattr(backend, "_ramp_x_line", lambda: (np.ones(30), np.ones(30)))
    monkeypatch.setattr(confocal_mod, "heartbeat_shutter", lambda *a, **k: None)

    backend._scan_ramp_xy()

    assert settle_calls == [[2, 3]], "Con corrección de inclinación activa debe confirmar Y y Z"


# ── ANOM-CONTRAPROP-01a — mismo patrón en el confocal dual ──────────────────

def test_contraprop_scan_ramp_xy_confirms_settle_and_bare_heartbeat(app, monkeypatch):
    backend = cp_mod.ConfocalDualBackend()
    backend.Nx = backend.Ny = 3
    backend.i = 0
    backend.y_pos = 50.0  # getattr(..., "y_min", self.y_pos - ...) evalúa el default siempre
    backend.y_min = 50.0
    backend.range_y = 2.0
    backend.image_top = np.zeros((3, 3))
    backend.image_bot = np.zeros((3, 3))

    settle_calls = []
    monkeypatch.setattr(backend, "_wait_axis_settle",
                         lambda axes, timeout_s=0.05: settle_calls.append(axes) or True)

    hb_calls = []
    monkeypatch.setattr(cp_mod, "heartbeat_shutter", lambda *a, **k: hb_calls.append((a, k)))

    backend._scan_ramp_xy()  # SAFE_MODE: usa el camino sintético, no toca DAQmx real

    assert settle_calls == [2], "Debe confirmar asentamiento del eje Y (2) antes del WGO"
    assert hb_calls == [((), {})], "Debe usar heartbeat_shutter() sin argumentos (política global)"


# ── Paridad de modos PSF en el confocal dual (x/z, y/x, y/z) ────────────────

def _prepared_dual_backend():
    backend = cp_mod.ConfocalDualBackend()
    backend.scan_ramp_parameters([2, 2, 3, 3])  # Nx=Ny=3; calcula extra/range_total(_y)
    backend.i = 0
    backend.x_pos = backend.y_pos = backend.z_pos = 50.0
    backend.x_min = backend.y_min = backend.z_min = 49.0
    backend.image_top = np.zeros((3, 3))
    backend.image_bot = np.zeros((3, 3))
    return backend


def test_start_scan_dispatches_to_correct_timer_and_configure_per_psf_mode(app, monkeypatch):
    monkeypatch.setattr(cp_mod, "open_shutter", lambda name: None)

    expectations = {
        cp_mod.PSF_MODES[0]: ("PDtimer_rampxy", "_configure_ramp_x"),
        cp_mod.PSF_MODES[1]: ("PDtimer_rampxz", "_configure_ramp_x"),
        cp_mod.PSF_MODES[2]: ("PDtimer_rampyx", "_configure_ramp_y"),
        cp_mod.PSF_MODES[3]: ("PDtimer_rampyz", "_configure_ramp_y"),
    }
    for mode, (timer_attr, configure_attr) in expectations.items():
        backend = cp_mod.ConfocalDualBackend()
        backend.psf_mode_opt = mode

        configure_calls = []
        monkeypatch.setattr(backend, "_configure_ramp_x", lambda p: configure_calls.append("_configure_ramp_x"))
        monkeypatch.setattr(backend, "_configure_ramp_y", lambda p: configure_calls.append("_configure_ramp_y"))

        backend.start_scan(0, 0)

        assert configure_calls == [configure_attr], f"Modo {mode}: debe llamar {configure_attr}"
        timer = getattr(backend, timer_attr)
        assert timer is not None and timer.isActive(), f"Modo {mode}: debe iniciar {timer_attr}"
        backend.stop_scan()


def test_scan_ramp_xz_moves_z_and_settles_z_axis(app, monkeypatch):
    backend = _prepared_dual_backend()
    settle_calls = []
    monkeypatch.setattr(backend, "_wait_axis_settle", lambda axes, timeout_s=0.05: settle_calls.append(axes) or True)
    hb_calls = []
    monkeypatch.setattr(cp_mod, "heartbeat_shutter", lambda *a, **k: hb_calls.append(True))

    backend._scan_ramp_xz()  # SAFE_MODE: camino sintético

    assert settle_calls == [3], "x/z debe confirmar asentamiento del eje Z (3)"
    assert hb_calls == [True]
    assert backend.i == 1
    assert np.any(backend.image_top[0, :] != 0.0), "Debe haber escrito la fila 0 de image_top"


def test_scan_ramp_yx_moves_x_and_stores_by_column(app, monkeypatch):
    backend = _prepared_dual_backend()
    settle_calls = []
    monkeypatch.setattr(backend, "_wait_axis_settle", lambda axes, timeout_s=0.05: settle_calls.append(axes) or True)

    backend._scan_ramp_yx()

    assert settle_calls == [1], "y/x debe confirmar asentamiento del eje X (1)"
    assert backend.i == 1
    assert np.any(backend.image_top[:, 0] != 0.0), "Debe haber escrito la columna 0 de image_top (no la fila)"
    assert np.all(backend.image_top[:, 1] == 0.0), "La columna 1 todavía no debe tocarse"


def test_scan_ramp_yz_moves_z_and_settles_z_axis(app, monkeypatch):
    backend = _prepared_dual_backend()
    settle_calls = []
    monkeypatch.setattr(backend, "_wait_axis_settle", lambda axes, timeout_s=0.05: settle_calls.append(axes) or True)

    backend._scan_ramp_yz()

    assert settle_calls == [3], "y/z debe confirmar asentamiento del eje Z (3)"
    assert backend.i == 1
    assert np.any(backend.image_top[0, :] != 0.0)


def test_all_four_ramp_modes_run_to_completion_without_error(app, monkeypatch):
    """Barrido de humo: corre cada uno de los 4 modos PSF de punta a punta (grilla 3x3
    en SAFE_MODE) y confirma que terminan limpiamente, emiten scanfinishedSignal y no
    lanzan excepciones — ningún modo debe quedar a mitad de camino."""
    monkeypatch.setattr(cp_mod, "open_shutter", lambda name: None)

    for mode in cp_mod.PSF_MODES:
        backend = cp_mod.ConfocalDualBackend()
        backend.psf_mode_opt = mode
        backend.top_laser_idx = 0
        backend.bot_laser_idx = 0

        finished = []
        backend.scanfinishedSignal.connect(lambda *a: finished.append(True))

        backend.start_scan(0, 0)
        timer_attr = {
            cp_mod.PSF_MODES[0]: "PDtimer_rampxy", cp_mod.PSF_MODES[1]: "PDtimer_rampxz",
            cp_mod.PSF_MODES[2]: "PDtimer_rampyx", cp_mod.PSF_MODES[3]: "PDtimer_rampyz",
        }[mode]
        step_fn = getattr(backend, {
            cp_mod.PSF_MODES[0]: "_scan_ramp_xy", cp_mod.PSF_MODES[1]: "_scan_ramp_xz",
            cp_mod.PSF_MODES[2]: "_scan_ramp_yx", cp_mod.PSF_MODES[3]: "_scan_ramp_yz",
        }[mode])
        limit = backend.Ny if mode in (cp_mod.PSF_MODES[0], cp_mod.PSF_MODES[1]) else backend.Nx

        for _ in range(limit + 1):  # +1: la última llamada dispara la rama de finalización
            step_fn()

        assert finished == [True], f"Modo {mode} no emitió scanfinishedSignal al completar"
        assert not getattr(backend, timer_attr).isActive()


# ── DEC-036 — la platina en falla aborta el escaneo; una demora con la platina sana, no ──

class _FaultyStage:
    """Platina real (no mock) que dejó de estar conectada y no fue aislada por el operador."""
    is_mock = False
    connected = False
    _isolated = False


class _SlowHealthyStage:
    is_mock = False
    connected = True
    _isolated = False


@pytest.mark.parametrize("mod_name,factory", [
    ("confocal", lambda: confocal_mod.Backend()),
    ("contrapropagante", lambda: cp_mod.ConfocalDualBackend()),
])
def test_wait_axis_settle_aborts_the_scan_on_stage_fault(app, monkeypatch, mod_name, factory):
    mod = confocal_mod if mod_name == "confocal" else cp_mod
    backend = factory()
    closes = []
    monkeypatch.setattr(mod, "wait_on_target", lambda *a, **k: False)
    monkeypatch.setattr(mod, "pi", _FaultyStage())
    monkeypatch.setattr(mod, "close_all_shutters", lambda: closes.append(1) or True)
    backend.signal_scan_stop = False
    assert backend._wait_axis_settle(2) is False, "Con la platina en falla el llamador debe retornar"
    assert closes == [1], "Se cierran los obturadores"
    assert backend.signal_scan_stop is True, "El escaneo queda detenido"


@pytest.mark.parametrize("mod_name,factory", [
    ("confocal", lambda: confocal_mod.Backend()),
    ("contrapropagante", lambda: cp_mod.ConfocalDualBackend()),
])
def test_wait_axis_settle_tolerates_a_slow_but_healthy_stage(app, monkeypatch, mod_name, factory):
    mod = confocal_mod if mod_name == "confocal" else cp_mod
    backend = factory()
    closes = []
    monkeypatch.setattr(mod, "wait_on_target", lambda *a, **k: False)
    monkeypatch.setattr(mod, "pi", _SlowHealthyStage())
    monkeypatch.setattr(mod, "close_all_shutters", lambda: closes.append(1) or True)
    backend.signal_scan_stop = False
    assert backend._wait_axis_settle(2) is True
    assert closes == [] and backend.signal_scan_stop is False


def test_scan_row_is_not_acquired_when_the_stage_fails(app, monkeypatch):
    backend = confocal_mod.Backend()
    backend._scan_ramp_parameters([2, 2, 3, 3])
    backend.i = 0
    backend.image_gone = np.zeros((3, 3))
    backend.image_back = np.zeros((3, 3))
    backend.image = np.zeros((3, 3))
    backend.tic = time.time()
    backend.tilt_correction_enabled = False
    ramps = []
    monkeypatch.setattr(backend, "_wait_axis_settle", lambda axes, timeout_s=0.05: False)
    monkeypatch.setattr(backend, "_ramp_x_line", lambda: ramps.append(1) or (np.ones(30), np.ones(30)))
    monkeypatch.setattr(confocal_mod, "heartbeat_shutter", lambda *a, **k: None)
    backend._scan_ramp_xy()
    assert ramps == [], "Sin asentamiento confirmado por falla no se dispara la rampa"
    assert backend.i == 0


# ── C-21 — centrado Gauss/Donut al final del escaneo del confocal dual ──────
# `_compute_center` llamaba `center_of_gauss2D(Zf)` / `center_of_donut2D(Zf)` sin la semilla
# `xo, yo` que ambas exigen (`analysis/psf.py`): con el centrado Gauss o Donut, el `TypeError`
# saltaba en `_finish_ramp_scan` después de cerrar los obturadores y antes del retorno de la
# platina y de la señal de fin del escaneo.

_C21_METHODS = [  # (TOP, BOT): los tres métodos, cada uno en el canal que lo ofrece
    ("center of mass", "center of mass"),
    ("center of gauss", "center of gauss"),
    ("center of mass", "donut (Laguerre-Gauss)"),  # TOP por CM: el Donut falla por sí mismo
]
_C21_TRUTH_TOP, _C21_TRUTH_BOT = (20.0, 14.0), (15.0, 18.0)  # (columna, fila) en píxeles


def _psf_image(n, col, row, donut=False):
    yy, xx = np.mgrid[0:n, 0:n].astype(float)
    r2 = ((xx - col) ** 2 + (yy - row) ** 2) / (2.0 * 3.0 ** 2)
    return 7.0 * (r2 * np.exp(-r2) if donut else np.exp(-r2))


def _c21_backend(monkeypatch, method_top, method_bot, grid):
    """Confocal dual al final de un escaneo, con PSF sintéticas de centro conocido. La platina
    y los obturadores se reemplazan por registros: el test no mueve nada, sólo anota qué se
    habría comandado."""
    assert method_top in cp_mod.METHOD_CENTER_TOP and method_bot in cp_mod.METHOD_CENTER_BOT
    backend = cp_mod.ConfocalDualBackend()
    n = backend.Nx
    assert backend.Ny == n, "El test supone una imagen cuadrada, como el default del escaneo"
    backend.x_pos = backend.y_pos = 50.0
    backend.x_start, backend.y_start, backend.z_start = 50.0, 50.0, 10.0
    backend.image_top = _psf_image(n, *_C21_TRUTH_TOP)
    backend.image_bot = _psf_image(n, *_C21_TRUTH_BOT, donut=(method_bot == cp_mod.METHOD_CENTER_BOT[2]))
    backend.method_center_top_opt = method_top
    backend.method_center_bot_opt = method_bot
    backend.is_grid_routine = grid
    log = {"moves": [], "closes": []}
    monkeypatch.setattr(cp_mod, "close_all_shutters", lambda: log["closes"].append(1) or True)
    monkeypatch.setattr(cp_mod.pi, "MOV", lambda axes, pos: log["moves"].append((list(axes), list(pos))) or True)
    return backend, log


@pytest.mark.parametrize("method_top,method_bot", _C21_METHODS)
def test_contraprop_scan_finishes_with_every_centering_method(app, monkeypatch, method_top, method_bot):
    backend, log = _c21_backend(monkeypatch, method_top, method_bot, grid=False)
    finished = []
    backend.scanfinishedSignal.connect(lambda *args: finished.append(args))

    backend._finish_ramp_scan(cp_mod.QTimer())

    assert log["closes"] == [1]
    assert len(finished) == 1, "El escaneo debe emitir scanfinishedSignal"
    # El único movimiento es el retorno al punto de inicio, el mismo con los tres métodos: la
    # corrección no agrega ni cambia ningún movimiento de la platina.
    assert log["moves"] == [([1, 2, 3], [50.0, 50.0, 10.0])]
    n = backend.Nx
    dx, dy = backend.range_x / n, backend.range_y / n
    for cm, (col, row) in ((backend.cm_top, _C21_TRUTH_TOP), (backend.cm_bot, _C21_TRUTH_BOT)):
        x_um, y_um = cm
        assert backend.x_pos - backend.range_x / 2 <= x_um <= backend.x_pos + backend.range_x / 2
        assert backend.y_pos - backend.range_y / 2 <= y_um <= backend.y_pos + backend.range_y / 2
        expected = (backend.x_pos - backend.range_x / 2 + dx / 2 + col * dx,
                    backend.y_pos - backend.range_y / 2 + dy / 2 + row * dy)
        assert abs(x_um - expected[0]) <= dx and abs(y_um - expected[1]) <= dy, (cm, expected)


@pytest.mark.xfail(strict=True, raises=TypeError, reason=(
    "Defecto aparte, no exento (DEC-039): `gridScanFinishedSignal` declara np.ndarray en los "
    "argumentos 3 y 4 y `_finish_ramp_scan` emite None, así que la grilla del contrapropagante "
    "se detiene al final del escaneo con cualquier método de centrado. Corregirlo habilita el "
    "flujo de impresión de `measurements.on_scan_finished` (platina y obturadores): fase 6.4."))
@pytest.mark.parametrize("method_top,method_bot", _C21_METHODS)
def test_contraprop_grid_scan_reaches_the_grid_routine(app, monkeypatch, method_top, method_bot):
    backend, log = _c21_backend(monkeypatch, method_top, method_bot, grid=True)
    finished = []
    backend.gridScanFinishedSignal.connect(lambda *args: finished.append(args))
    backend._finish_ramp_scan(cp_mod.QTimer())
    assert len(finished) == 1
