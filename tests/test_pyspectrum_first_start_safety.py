# -*- coding: utf-8 -*-
"""Bloque A de PySpectrum 3.0, pasos 1 a 3: primer arranque seguro contra el equipo (DEC-040).

Diseño aprobado en la Ronda 2 (`docs/evidence/auditoria_2026-09-27/pyspectrum_A_ronda2/`):
- **Paso 2** — ni el arranque ni "Cargar"/"Recargar" un archivo de calibración escriben al
  Shamrock. Antes, el constructor del dock de Calibraciones escribía offsets inventados (redes
  12/−35/0, detector 5, cero de ranura 0) en cada arranque (C-04); esos offsets viven en el equipo
  y los comparten Solis y el legado. Escribir un offset queda como acción explícita del operador
  (R4-3, R4-B-1).
- **Paso 3** — fuera de SAFE_MODE, una cámara o un Shamrock que no inicializan quedan "no
  conectados" con un motivo legible; nunca se reemplazan por el simulador (DEC-036) y ninguna
  lectura devuelve datos sintéticos (ni un cuadro de ceros ni un eje λ inventado).
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYPRINTING_SAFE", "1")

import numpy as np
import pytest
from PyQt6.QtWidgets import QApplication

from pyspectrum.drivers import andor_ccd_driver as andor_mod
from pyspectrum.drivers import shamrock_driver as shamrock_mod

_app = QApplication.instance() or QApplication([])

_OFFSET_WRITERS = {
    "ShamrockSetGratingOffset", "ShamrockSetDetectorOffset", "ShamrockSetDetectorOffsetEx",
    "ShamrockSetDetectorOffsetPort2", "ShamrockSetSlitZeroPosition", "ShamrockEepromSetOpticalParams",
}

_CALIBRATION_TXT = """\
[GEOMETRIA_SLIT]
slit_width_um = 50.0
slit_center_pixel_x = 502.00
slit_fwhm_pixels = 4.12
slit_zero_position_steps = 0

[OFFSETS_HARDWARE_SDK]
grating_1_offset_steps = 12
grating_2_offset_steps = -35
grating_3_offset_steps = 0
detector_offset_steps = 5
"""


class _RecordingShamrock:
    """Envuelve el mock del Shamrock y registra el nombre de cada método invocado."""

    def __init__(self, inner):
        self._inner = inner
        self.calls: list[str] = []

    def __getattr__(self, name):
        attr = getattr(self._inner, name)
        if not callable(attr):
            return attr

        def _recorded(*args, **kwargs):
            self.calls.append(name)
            return attr(*args, **kwargs)

        return _recorded

    def offset_writes(self):
        return [c for c in self.calls if c in _OFFSET_WRITERS]


@pytest.fixture
def calibration_file(tmp_path, monkeypatch):
    from pyspectrum.modules import calibration_dock
    path = tmp_path / "pyspectrum_calibration_last.txt"
    path.write_text(_CALIBRATION_TXT, encoding="utf-8")
    monkeypatch.setattr(calibration_dock, "CALIBRATION_TXT_FILE", path)
    return path


def _make_backend():
    from pyspectrum.modules.calibration_dock import CalibrationBackend
    spectrometer = _RecordingShamrock(shamrock_mod._MockShamrock())
    backend = CalibrationBackend(camera=andor_mod._MockAndorCCD(), spectrometer=spectrometer)
    return backend, spectrometer


# ── Paso 2: el arranque y la carga de un archivo no escriben al Shamrock ─────────────────────

def test_calibration_backend_startup_writes_no_offset_to_the_shamrock(calibration_file):
    backend, spectrometer = _make_backend()
    assert spectrometer.offset_writes() == [], (
        "el arranque escribió offsets al Shamrock; deben escribirse sólo por acción explícita")
    # El archivo se sigue leyendo, pero sus offsets son informativos (pasos 9-10): no pasan por leídos.
    assert backend.file_offsets["grating_1"] == 12 and backend.file_offsets["detector"] == 5
    assert backend.grating_offsets.get(1) is None and backend.detector_offset is None


def test_loading_or_reloading_a_calibration_file_writes_no_offset(calibration_file):
    backend, spectrometer = _make_backend()
    spectrometer.calls.clear()
    assert backend.load_calibration_from_txt(str(calibration_file)) is True
    assert backend.load_calibration_from_txt() is True  # "Recargar última"
    assert spectrometer.offset_writes() == []


# ── Paso 3: sin simulador fuera de SAFE_MODE y sin datos sintéticos ──────────────────────────

class _FailingInitAndorDll:
    def Initialize(self, _dir):
        return 20992  # DRV_NOT_AVAILABLE: otro programa tiene la cámara

    def __getattr__(self, name):
        raise AssertionError(f"no debería llamarse {name} si Initialize falló")


@pytest.fixture
def lab_mode_andor(monkeypatch):
    # Estos tests cubren el driver ctypes propio, que queda seleccionable (R4-F).
    import config
    monkeypatch.setattr(config, "ANDOR_BACKEND", "ctypes")
    monkeypatch.setattr(andor_mod, "SAFE_MODE", False)
    monkeypatch.setattr(andor_mod, "_andor_instance", None)
    return monkeypatch


def test_andor_without_dll_is_unavailable_not_mock(lab_mode_andor):
    lab_mode_andor.setattr(andor_mod.AndorCCDDriver, "_init_dll", lambda self: None)
    cam = andor_mod.get_andor_ccd()
    assert cam.is_mock is False
    assert cam.available is False
    assert "atmcd64d.dll" in cam.unavailable_reason


def test_andor_failed_initialize_is_unavailable_with_reason(lab_mode_andor):
    def _init_dll(self):
        self._dll = _FailingInitAndorDll()
    lab_mode_andor.setattr(andor_mod.AndorCCDDriver, "_init_dll", _init_dll)
    cam = andor_mod.get_andor_ccd()
    assert cam.is_mock is False and cam.available is False
    assert "20992" in cam.unavailable_reason and "Solis" in cam.unavailable_reason


@pytest.mark.parametrize("reader", ["get_most_recent_image", "get_1d_spectrum", "get_acquired_data"])
def test_unavailable_andor_never_returns_a_frame(lab_mode_andor, reader):
    lab_mode_andor.setattr(andor_mod.AndorCCDDriver, "_init_dll", lambda self: None)
    cam = andor_mod.get_andor_ccd()
    with pytest.raises(andor_mod.DeviceUnavailable):
        getattr(cam, reader)()


def test_unavailable_andor_never_returns_tracks(lab_mode_andor):
    lab_mode_andor.setattr(andor_mod.AndorCCDDriver, "_init_dll", lambda self: None)
    cam = andor_mod.get_andor_ccd()
    with pytest.raises(andor_mod.DeviceUnavailable):
        cam.get_tracks_2d_spectrum(2)


def test_connected_andor_reports_available(lab_mode_andor):
    class _OkDll:
        def Initialize(self, _dir):
            return andor_mod.DRV_SUCCESS

        def __getattr__(self, name):
            return lambda *a, **k: andor_mod.DRV_SUCCESS

    def _init_dll(self):
        self._dll = _OkDll()
    lab_mode_andor.setattr(andor_mod.AndorCCDDriver, "_init_dll", _init_dll)
    cam = andor_mod.get_andor_ccd()
    assert cam.available is True and cam.unavailable_reason == ""


@pytest.fixture
def lab_mode_shamrock(monkeypatch):
    monkeypatch.setattr(shamrock_mod, "SAFE_MODE", False)
    monkeypatch.setattr(shamrock_mod, "_shamrock_instance", None)
    return monkeypatch


def test_shamrock_without_dll_is_unavailable_not_mock(lab_mode_shamrock):
    lab_mode_shamrock.setattr(shamrock_mod.ShamrockDriver, "_init_dll", lambda self: None)
    spec = shamrock_mod.get_shamrock()
    assert spec.is_mock is False
    assert spec.available is False
    assert "ShamrockCIF.dll" in spec.unavailable_reason


def test_shamrock_failed_initialize_is_unavailable_with_reason(lab_mode_shamrock):
    class _FailingDll:
        def ShamrockInitialize(self, _ini):
            return 20201  # SHAMROCK_COMMUNICATION_ERROR

    def _init_dll(self):
        self._dll = _FailingDll()
    lab_mode_shamrock.setattr(shamrock_mod.ShamrockDriver, "_init_dll", _init_dll)
    spec = shamrock_mod.get_shamrock()
    assert spec.is_mock is False and spec.available is False
    assert "20201" in spec.unavailable_reason


def test_unavailable_shamrock_returns_no_synthetic_wavelength_axis(lab_mode_shamrock):
    lab_mode_shamrock.setattr(shamrock_mod.ShamrockDriver, "_init_dll", lambda self: None)
    spec = shamrock_mod.get_shamrock()
    ret, axis = spec.get_calibration()
    assert ret != shamrock_mod.SHAMROCK_SUCCESS
    assert axis.shape == (shamrock_mod.NUMBER_OF_PIXELS,)
    assert np.all(np.isnan(axis)), "un eje λ inventado (400-700 nm) pasaría por real"


def test_safe_mode_still_uses_the_simulators(monkeypatch):
    monkeypatch.setattr(andor_mod, "_andor_instance", None)
    monkeypatch.setattr(shamrock_mod, "_shamrock_instance", None)
    assert andor_mod.get_andor_ccd().is_mock is True
    assert shamrock_mod.get_shamrock().is_mock is True


# ── Paso 3: el Live no arranca sobre una cámara no conectada ─────────────────────────────────

def test_live_refuses_to_start_on_an_unavailable_camera(lab_mode_andor):
    from pyspectrum.ui.exploration_tab import ExplorationWorker
    lab_mode_andor.setattr(andor_mod.AndorCCDDriver, "_init_dll", lambda self: None)
    cam = andor_mod.get_andor_ccd()
    worker = ExplorationWorker(cam, spectrometer=shamrock_mod._MockShamrock())
    errors, frames = [], []
    worker.liveErrorSignal.connect(errors.append)
    worker.frameReadySignal.connect(lambda: frames.append(1))
    worker.start_live()
    assert worker._timer is None or not worker._timer.isActive()
    assert errors and "atmcd64d.dll" in errors[0]
    assert frames == []


# ── Geometría del detector en el archivo de calibración guardado (DEC-040, DEC-033) ──────────

def test_saved_calibration_declares_datasheet_pixel_geometry_and_no_false_validation(calibration_file, tmp_path):
    """El iXon3 885 tiene píxeles de 8 × 8 µm y 1004 × 1002 activos ([DS-iXon] p. 1). Antes, todo
    archivo guardado declaraba 13 µm y "CALIBRADO_VALIDADO", y propagaba el error y un estado falso."""
    import configparser
    backend, _ = _make_backend()
    out = tmp_path / "guardada.txt"
    assert backend.save_calibration_to_txt(str(out)) is True
    text = out.read_text(encoding="utf-8")
    assert "13 µm" not in text and "13.0 µm" not in text
    cfg = configparser.ConfigParser()
    cfg.read(str(out), encoding="utf-8")
    meta = cfg["METADATOS"]
    assert float(meta["tamano_pixel_um"]) == andor_mod.DETECTOR_PIXEL_PITCH_UM == 8.0
    assert int(meta["resolucion_horizontal_px"]) == andor_mod.DETECTOR_WIDTH_PX == 1004
    assert meta["estado"] != "CALIBRADO_VALIDADO"
