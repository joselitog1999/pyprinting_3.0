# -*- coding: utf-8 -*-
"""Escaneo lineal sobre los contratos de los pasos 6 a 11 (paso 12 del bloque A; R4-I; R2-arq §7.2).

- **Luz** (R4-I, como Step & Glue): la rutina nunca abre ni cierra un láser. La señal se toma con el
  obturador del espectrómetro abierto y el fondo con ese obturador cerrado.
- **Una exposición real por cuadro** (`single_exposure`), nunca "dormir y leer el último cuadro" (R4-5).
- **Movimiento:** por el servicio, con λ releída y el eje verificado. Si algo falla, se informa; nunca
  queda un eje NaN ni un paso en la λ anterior.
- **Latido:** sólo con un láser abierto y nunca con argumento (C-29).
- **HDF5:** en la carpeta de datos de las rutinas (nunca el directorio actual), con red, ventana, centros y
  láseres abiertos en los metadatos.
- **Cosido:** `glue_steps`, sin cambios (R4-I).
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYPRINTING_SAFE", "1")

from pathlib import Path

import h5py
import numpy as np
import pytest

from pyspectrum.drivers.shamrock_driver import DEVICE
from pyspectrum.modules import step_glue_engine as eng
from pyspectrum.modules.hardware_session import hardware_session
from pyspectrum.modules.routines import linescan_spectroscopy as ls
from pyspectrum.modules.routines.linescan_spectroscopy import LineScanSpectroscopyWorker


def _ref_cfg(mode, **kw):
    cfg = dict(x_ref=50.0, y_ref=50.0, z_ref=10.0, roi_center=501, roi_height=16, exp_1d=0.01, exp_2d=0.01,
               mode=mode, noise_mult=3.0, glue_start=450.0, glue_end=750.0, glue_overlap=0.2)
    cfg.update(kw)
    return cfg


def _scan_cfg(mode, **kw):
    cfg = dict(x_start=20.0, x_end=24.0, y_fixed=50.0, z_fixed=10.0, step_um=4.0, exp_1d=0.01, exp_2d=0.01,
               mode=mode, glue_start=450.0, glue_end=750.0, glue_overlap=0.2)
    cfg.update(kw)
    return cfg


@pytest.fixture
def worker(monkeypatch):
    hardware_session.clear_emergency()

    def no_laser(*a, **k):
        raise AssertionError("el escaneo lineal no abre ni cierra láseres (R4-I)")
    monkeypatch.setattr(ls, "open_shutter", no_laser, raising=False)
    monkeypatch.setattr(ls, "close_shutter", no_laser, raising=False)
    w = LineScanSpectroscopyWorker()
    yield w
    hardware_session.release_session("Escaneo Lineal Espectroscópico")
    hardware_session.release_session("Escaneo Lineal Espectroscópico — Referencia")
    hardware_session.clear_emergency()


def _collect(w):
    got = {}
    w.scanCompletedSignal.connect(lambda p: got.setdefault("path", p))
    w.errorSignal.connect(lambda m: got.setdefault("error", m))
    w.referenceWarningSignal.connect(lambda m: got.setdefault("warning", m))
    return got


def test_reference_uses_the_spectrometer_shutter_for_the_background_and_real_exposures(worker, monkeypatch):
    shutter, exposures = [], []
    monkeypatch.setattr("pyspectrum.services.spectrometer_shutter.open_spectrometer_shutter",
                        lambda c, s: shutter.append("open") or type("R", (), {"ok": True, "detail": ""})())
    monkeypatch.setattr("pyspectrum.services.spectrometer_shutter.close_spectrometer_shutter",
                        lambda c, s: shutter.append("close") or type("R", (), {"ok": True, "detail": ""})())
    real = ls.single_exposure
    monkeypatch.setattr(ls, "single_exposure", lambda *a, **k: exposures.append(a[1].shape) or real(*a, **k))
    got = _collect(worker)
    worker.acquire_reference(_ref_cfg("single_window"))
    assert "error" not in got, got
    # Señal con el obturador abierto y fondo cerrado, dos veces (1D y 2D), en ese orden. Otros componentes
    # (un Live pausado) pueden agregar cierres propios en la suite completa.
    it = iter(shutter)
    assert all(step in it for step in ["open", "close", "open", "close"]), shutter
    assert shutter.count("open") == 2
    assert exposures == [(1004,), (1004,), (16, 1004), (16, 1004)]


def test_full_scan_writes_hdf5_in_the_routine_data_dir_with_metadata(worker):
    got = _collect(worker)
    worker.acquire_reference(_ref_cfg("step_and_glue"))
    assert worker._reference is not None, got
    worker.run_scan(_scan_cfg("step_and_glue"))
    assert "error" not in got and "path" in got, got
    path = Path(got["path"])
    assert Path(os.environ["PYSPECTRUM_ROUTINE_DATA_DIR"]) in path.parents
    with h5py.File(path, "r") as f:
        attrs = dict(f["metadata"].attrs)
        assert attrs["grating"] == 1
        assert attrs["glue_window_source"] in ("measured", "nominal")
        assert len(attrs["glue_centers_nm"]) >= 3
        assert "open_lasers_at_start" in attrs and attrs["stitching"] == "glue_steps"
        # c_sw siempre en el metadato (R3-gui §4.6), también sin corrección fina
        assert attrs["c_sw_status"] in ("APLICADA", "SUSPENDIDA", "NINGUNA", "NO_APLICA", "DESCONOCIDA")
        assert "no aplicada al eje" in attrs["c_sw_policy"] and "c_sw_px" in attrs


def test_a_failed_move_is_reported_not_acquired_at_the_old_wavelength(worker, monkeypatch):
    got = _collect(worker)
    real = worker.spectrometer.ShamrockSetWavelength
    state = {"n": 0}

    def flaky(device=DEVICE, wavelength=0.0):
        state["n"] += 1
        return 20201 if state["n"] == 2 else real(device, wavelength)
    monkeypatch.setattr(worker.spectrometer, "ShamrockSetWavelength", flaky)
    worker.acquire_reference(_ref_cfg("step_and_glue"))
    assert "error" in got and "20201" in got["error"]
    assert worker._reference is None


def test_a_failed_axis_aborts_instead_of_a_nan_axis(worker, monkeypatch):
    got = _collect(worker)
    monkeypatch.setattr(worker.spectrometer, "get_wavelength_axis_cubic",
                        lambda device=DEVICE, num_pixels=1004: (20201, np.full(num_pixels, np.nan)))
    worker.acquire_reference(_ref_cfg("single_window"))
    assert "error" in got and "eje" in got["error"]
    assert worker._reference is None


def test_heartbeat_is_never_called_with_an_argument():
    import ast
    src = Path(ls.__file__).read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", "")) == "heartbeat_shutter":
            assert not node.args and not node.keywords, node.lineno


def test_a_wavelength_that_does_not_reread_is_reported(worker, monkeypatch):
    got = _collect(worker)
    monkeypatch.setattr(worker.spectrometer, "ShamrockGetWavelength", lambda device=DEVICE: (20202, 999.0))
    worker.acquire_reference(_ref_cfg("step_and_glue"))
    assert "error" in got and "999" in got["error"]
    assert worker._reference is None
