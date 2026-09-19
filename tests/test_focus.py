# -*- coding: utf-8 -*-
"""
test_focus.py — Pruebas unitarias para las correcciones de seguridad de modules/focus.py
(auditoría multi-agente 2026-09-18, hallazgos ANOM-FOCUS-01/02/03):

1. ANOM-FOCUS-02: self.zo se clampea al mismo rango físico [0, PI_STAGE_RANGE_UM] que
   pi.MOV() aplica a nivel de driver, evitando el desfase entre la geometría de trigger
   (WOS/CTO/WAV_LIN, sin clamping propio) y el movimiento físico real cerca de los
   límites de recorrido Z.
2. ANOM-FOCUS-03: _move_z() levanta TimeoutError ante un fallo de servo/piezo simulado
   (qONT() que nunca reporta on-target), en vez de colgar indefinidamente.
3. ANOM-FOCUS-01: las tres rutinas de rampa Z (go_to_maximum, lock_lin, autocorr_x2)
   abortan tras MAX_RAMP_RETRIES intentos de detección de trigger fallidos en vez de
   reintentar para siempre, y garantizan el cierre del obturador incluso en el abort.
   Estas pruebas cierran el punto ciego que el propio panel de auditoría señaló:
   _MockNITask siempre sintetiza triggers limpios, así que sin inyección de fallos
   explícita esta rama nunca se ejercita en SAFE_MODE.

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
import modules.focus as focus_mod


def _make_backend(app):
    backend = focus_mod.Backend()
    backend.laser = focus_mod.SHUTTERS[0]
    return backend


# ── ANOM-FOCUS-02 — clamp de self.zo ─────────────────────────────────────────

def test_clamped_zo_within_bounds_near_lower_limit(app):
    backend = _make_backend(app)
    zo = backend._clamped_zo(1.0)   # muy cerca del límite inferior de recorrido
    assert zo >= 0.0
    assert zo + backend.range_total <= focus_mod.PI_STAGE_RANGE_UM + 1e-9


def test_clamped_zo_within_bounds_near_upper_limit(app):
    backend = _make_backend(app)
    zo = backend._clamped_zo(99.0)  # muy cerca del límite superior (100 µm)
    assert zo >= 0.0
    assert zo + backend.range_total <= focus_mod.PI_STAGE_RANGE_UM + 1e-9


def test_clamped_zo_matches_unclamped_formula_in_safe_interior(app):
    backend = _make_backend(app)
    center = 50.0
    zo = backend._clamped_zo(center)
    assert abs(zo - (center - backend.range_total / 2)) < 1e-9


# ── ANOM-FOCUS-03 — timeout de _move_z ───────────────────────────────────────

def test_move_z_raises_timeout_on_stalled_servo(app, monkeypatch):
    backend = _make_backend(app)
    monkeypatch.setattr(focus_mod.pi, "qONT", lambda axes=None: {3: False})

    t0 = time.time()
    raised = False
    try:
        backend._move_z(50.0, timeout_s=0.3)
    except TimeoutError:
        raised = True
    elapsed = time.time() - t0

    assert raised, "Se esperaba TimeoutError ante un servo que nunca reporta on-target"
    assert elapsed < 2.0, "El timeout debe respetar el límite configurado, no colgar"


def test_move_z_succeeds_immediately_when_on_target(app):
    backend = _make_backend(app)
    backend._move_z(50.0, timeout_s=0.3)  # no debe lanzar (mock qONT default = True)


# ── ANOM-FOCUS-01 — cota de reintentos + cierre garantizado de obturador ─────

def _inject_trigger_not_found(monkeypatch, backend):
    """Simula _ramp_lin() fallando siempre en detectar flancos de trigger válidos
    (cableado/controller degradado) — el _MockNITask normal nunca produce este caso,
    por eso hay que inyectarlo explícitamente para ejercitar la rama de abort."""
    calls = {"n": 0}

    def fake_ramp_lin():
        calls["n"] += 1
        return np.zeros(10), np.zeros(10), True   # flag=True -> "no encontrado"
    monkeypatch.setattr(backend, "_ramp_lin", fake_ramp_lin)
    return calls


def test_go_to_maximum_aborts_after_retry_cap_and_closes_shutter_every_attempt(app, monkeypatch):
    backend = _make_backend(app)
    calls = _inject_trigger_not_found(monkeypatch, backend)

    close_calls = {"n": 0}
    monkeypatch.setattr(focus_mod, "open_shutter", lambda name: None)
    monkeypatch.setattr(focus_mod, "close_shutter",
                         lambda name: close_calls.__setitem__("n", close_calls["n"] + 1))

    backend.focus_go_to_maximum(0)   # no debe lanzar, no debe colgar

    assert calls["n"] == backend.MAX_RAMP_RETRIES, \
        "Debe abortar exactamente tras MAX_RAMP_RETRIES intentos, no reintentar sin límite"
    assert close_calls["n"] == backend.MAX_RAMP_RETRIES, \
        "El obturador debe cerrarse en cada intento, incluyendo el último (abort)"


def test_lock_lin_aborts_after_retry_cap_and_resets_locked_focus(app, monkeypatch):
    backend = _make_backend(app)
    calls = _inject_trigger_not_found(monkeypatch, backend)
    monkeypatch.setattr(focus_mod, "open_shutter", lambda name: None)
    monkeypatch.setattr(focus_mod, "close_shutter", lambda name: None)

    backend.locked_focus = True  # estado previo — debe quedar en False tras el abort
    backend.focus_lock_lin(True, 0)

    assert calls["n"] == backend.MAX_RAMP_RETRIES
    assert backend.locked_focus is False, \
        "No debe quedar un estado 'lockeado' fantasma tras un abort de detección de trigger"


def test_autocorr_x2_aborts_but_closes_shutter_and_still_unblocks_printing_state_machine(app, monkeypatch):
    backend = _make_backend(app)
    # Pre-condición: perfil ya lockeado (si no, el propio método intenta auto-lock primero).
    backend.locked_focus = True
    backend.z_profile_lock_filter = np.zeros(10)

    calls = _inject_trigger_not_found(monkeypatch, backend)

    shutter_events = []
    monkeypatch.setattr(focus_mod, "open_shutter", lambda name: shutter_events.append("open"))
    monkeypatch.setattr(focus_mod, "close_shutter", lambda name: shutter_events.append("close"))

    autofinish_calls = []
    backend.autofinishSignal.connect(lambda mode: autofinish_calls.append(mode))

    backend.focus_autocorr_lin_x2("printing")

    assert calls["n"] == backend.MAX_RAMP_RETRIES, \
        "Debe abortar tras la cota de reintentos, no colgar el hilo confocal compartido"
    assert shutter_events == ["open", "close"], (
        "El obturador se abre una sola vez (antes de las 2 pasadas) y debe cerrarse "
        "garantizado en el abort — no quedar abierto indefinidamente (ANOM-FOCUS-01)"
    )
    assert autofinish_calls == ["printing"], (
        "autofinishSignal debe emitirse igual en el abort: grid_finish_autofoco() de "
        "impresión/dímeros queda esperando este callback y se colgaría sin él"
    )


def test_ramp_succeeds_within_retry_cap_does_not_abort(app, monkeypatch):
    """Control: si el trigger se detecta antes de agotar la cota, el flujo normal debe
    completar sin disparar el abort — la cota no debe introducir falsos positivos."""
    backend = _make_backend(app)
    state = {"n": 0}

    def flaky_ramp_lin():
        state["n"] += 1
        if state["n"] < 2:
            return np.zeros(10), np.zeros(10), True
        n = backend.Nz  # f_gone=1: suficiente para _average/_filter sin recorte
        return np.random.rand(n), np.random.rand(n), False

    monkeypatch.setattr(backend, "_ramp_lin", flaky_ramp_lin)
    monkeypatch.setattr(focus_mod, "open_shutter", lambda name: None)
    monkeypatch.setattr(focus_mod, "close_shutter", lambda name: None)

    done_calls = []
    backend.gotomaxdoneSignal.connect(lambda: done_calls.append(True))

    backend.focus_go_to_maximum(0)

    assert state["n"] == 2, "Debe reintentar una vez y tener éxito en el segundo intento"
    assert done_calls == [True], \
        "Con éxito dentro de la cota, el flujo normal debe completar y emitir gotomaxdoneSignal"
