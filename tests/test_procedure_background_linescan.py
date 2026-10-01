# -*- coding: utf-8 -*-
"""El fondo en el escaneo lineal (R4-N; DEC-040).

- La referencia sigue tomando señal (obturador abierto) y fondo en 1D y 2D, con la misma configuración.
- "Obturador cerrado" (por defecto): el fondo se toma con el obturador del espectrómetro cerrado y se
  **reutiliza** en la referencia siguiente si las condiciones no cambiaron (modo, exposiciones, ROI, centros
  y la configuración de la cámara).
- "Todo apagado": [Tomar fondo ahora] mide sólo el fondo con el obturador ABIERTO y la luz apagada; la
  referencia toma sólo las señales y usa ese fondo. Sin un fondo que coincida, la referencia no arranca.
- El HDF5 guarda el método y si el fondo se reutilizó; el fondo sigue aparte de la señal (B3).
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYPRINTING_SAFE", "1")

import h5py
import pytest

from test_linescan_step12 import _collect, _ref_cfg, _scan_cfg, worker  # noqa: F401  (fixture)

from pyspectrum.modules.routines import linescan_spectroscopy as ls
from pyspectrum.services import procedure_background as pb


def _spy(monkeypatch):
    """Registra sólo lo que acciona el escaneo lineal: en la suite completa, un objeto que dejó otro test puede
    cerrar el obturador del mismo espectrómetro simulado (visto el 2026-09-30)."""
    import sys
    shutter, exposures = [], []

    def record(what):
        def fn(c, s):
            if sys._getframe(1).f_globals.get("__name__") == ls.__name__:
                shutter.append(what)
            return type("R", (), {"ok": True, "detail": ""})()
        return fn
    monkeypatch.setattr("pyspectrum.services.spectrometer_shutter.open_spectrometer_shutter", record("open"))
    monkeypatch.setattr("pyspectrum.services.spectrometer_shutter.close_spectrometer_shutter", record("close"))
    real = ls.single_exposure
    monkeypatch.setattr(ls, "single_exposure", lambda *a, **k: exposures.append(a[1].shape) or real(*a, **k))
    return shutter, exposures


def test_a_second_reference_with_the_same_conditions_reuses_the_background(worker, monkeypatch):
    shutter, exposures = _spy(monkeypatch)
    got = _collect(worker)
    worker.acquire_reference(_ref_cfg("single_window"))
    assert "error" not in got, got
    assert exposures == [(1004,), (1004,), (16, 1004), (16, 1004)]
    shutter.clear()
    exposures.clear()
    worker.acquire_reference(_ref_cfg("single_window"))
    assert exposures == [(1004,), (16, 1004)]                    # sólo las señales
    assert "close" not in shutter[:-1]                           # no se cerró para el fondo (sí al final)
    assert worker.background_info["reused"] is True


def test_other_conditions_take_the_background_again(worker, monkeypatch):
    shutter, exposures = _spy(monkeypatch)
    worker.acquire_reference(_ref_cfg("single_window"))
    exposures.clear()
    worker.acquire_reference(_ref_cfg("single_window", exp_1d=0.02))
    assert exposures == [(1004,), (1004,), (16, 1004), (16, 1004)]
    assert worker.background_info["reused"] is False


def test_all_off_without_a_background_does_not_start(worker, monkeypatch):
    shutter, exposures = _spy(monkeypatch)
    got = _collect(worker)
    worker.set_dark_method(pb.METHOD_ALL_OFF)
    worker.acquire_reference(_ref_cfg("single_window"))
    assert "Tomar fondo ahora" in got.get("error", "") and exposures == []
    assert worker._reference is None


def test_all_off_background_is_taken_with_the_shutter_open_and_used_by_the_reference(worker, monkeypatch):
    shutter, exposures = _spy(monkeypatch)
    monkeypatch.setattr(ls, "_open_lasers", lambda: [])
    got = _collect(worker)
    worker.set_dark_method(pb.METHOD_ALL_OFF)
    worker.acquire_background_only(_ref_cfg("single_window"))
    assert "error" not in got, got
    assert exposures == [(1004,), (16, 1004)] and "close" not in shutter[:-1]
    exposures.clear()
    worker.acquire_reference(_ref_cfg("single_window"))
    assert "error" not in got, got
    assert exposures == [(1004,), (16, 1004)]                    # señales; el fondo es el tomado antes
    assert worker.background_info == {"method": pb.METHOD_ALL_OFF, "reused": True}


def test_all_off_refuses_with_an_open_laser(worker, monkeypatch):
    shutter, exposures = _spy(monkeypatch)
    monkeypatch.setattr(ls, "_open_lasers", lambda: ["532 nm (green)"])
    got = _collect(worker)
    worker.set_dark_method(pb.METHOD_ALL_OFF)
    worker.acquire_background_only(_ref_cfg("single_window"))
    assert "532" in got.get("error", "") and exposures == []


def test_discard_forces_a_new_background(worker, monkeypatch):
    shutter, exposures = _spy(monkeypatch)
    worker.acquire_reference(_ref_cfg("single_window"))
    worker.discard_background()
    exposures.clear()
    worker.acquire_reference(_ref_cfg("single_window"))
    assert len(exposures) == 4


def test_h5_records_the_background_method_and_reuse(worker):
    got = _collect(worker)
    worker.acquire_reference(_ref_cfg("single_window"))
    worker.run_scan(_scan_cfg("single_window"))
    assert "path" in got, got
    with h5py.File(got["path"], "r") as f:
        attrs = dict(f["metadata"].attrs)
        assert attrs["background_method"] == pb.METHOD_SHUTTER and attrs["background_reused"] in (False, 0)
        assert "background_1d" in f["reference"]                  # el fondo sigue aparte de la señal


def test_another_em_gain_takes_the_background_again(worker, monkeypatch):
    shutter, exposures = _spy(monkeypatch)
    worker.acquire_reference(_ref_cfg("single_window"))
    old = worker.camera.get_emccd_gain()
    worker.camera.set_emccd_gain(37)
    try:
        exposures.clear()
        worker.acquire_reference(_ref_cfg("single_window"))
        assert len(exposures) == 4 and worker.background_info["reused"] is False
    finally:
        worker.camera.set_emccd_gain(old[1] if isinstance(old, tuple) else old)
