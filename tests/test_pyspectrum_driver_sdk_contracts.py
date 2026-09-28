# -*- coding: utf-8 -*-
"""Bloque A de PySpectrum 3.0, paso 5: el driver llama al SDK con los códigos y las firmas reales (DEC-040).

- **C-05**: códigos de `SetReadMode` según el SDK2 de Andor v2.104 (`docs/bibliografia/Software
  Development Kit.pdf`, p. 305): 0 FVB, 1 Multi-Track, 2 Random-Track, 3 Single-Track, 4 Image.
  El driver tenía Single-Track = 1, Multi = 2 y Random = 3, así que pedía Multi-Track creyendo
  pedir Single-Track.
- **C-06**: la rendija de entrada se lee y se escribe con `ShamrockGetAutoSlitWidth(device, index,
  float*)` / `ShamrockSetAutoSlitWidth(device, index, float)`, como el legado
  (`scratch/pyspectrum-legacy/Shamrock_ps.py`, docstrings del SDK; `Spectrum_ps.py:206`). El
  driver llamaba a `ShamrockGetSlit(device, index, &w)`, una función de DOS argumentos
  (`ShamrockGetSlit(device, float*)`): el índice se usaba como puntero de salida y la DLL
  escribía en la dirección 0x1.
- **C-07**: el espejo de entrada/salida se maneja con `ShamrockGetFlipperMirror` /
  `ShamrockSetFlipperMirror`; `ShamrockGetFlipper` / `ShamrockSetFlipper` no existen en el SDK.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYPRINTING_SAFE", "1")

import math
from ctypes import c_float, c_int

import pytest

from pyspectrum.drivers import andor_ccd_driver as andor_mod
from pyspectrum.drivers import shamrock_driver as shamrock_mod


# ── C-05: códigos de modo de lectura ──────────────────────────────────────────────────────────

def test_read_mode_codes_match_the_sdk():
    assert andor_mod.READ_MODE_FVB == 0
    assert andor_mod.READ_MODE_MULTI_TRACK == 1
    assert andor_mod.READ_MODE_RANDOM_TRACK == 2
    assert andor_mod.READ_MODE_SINGLE_TRACK == 3
    assert andor_mod.READ_MODE_IMAGE == 4


class _RecordingAndorDll:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def _call(*args):
            self.calls.append((name, tuple(a.value if hasattr(a, "value") else a for a in args)))
            return andor_mod.DRV_SUCCESS
        return _call


def test_driver_sends_single_track_code_3_to_setreadmode(monkeypatch):
    monkeypatch.setattr(andor_mod.AndorCCDDriver, "_init_dll", lambda self: None)
    cam = andor_mod.AndorCCDDriver()
    cam._dll = _RecordingAndorDll()
    cam._connected = True
    assert cam.set_read_mode(andor_mod.READ_MODE_SINGLE_TRACK) == andor_mod.DRV_SUCCESS
    assert ("SetReadMode", (3,)) in cam._dll.calls


def test_step_and_glue_single_spectrum_uses_1d_read_in_single_track():
    """El literal `in (0, 1)` de step_and_glue trataba Multi-Track como 1D y Single-Track como 2D
    una vez corregidos los códigos."""
    from pyspectrum.modules import step_and_glue
    from pyspectrum.modules.hardware_session import hardware_session
    # La sesión de hardware es un singleton de proceso: un test anterior puede dejar la E-STOP
    # armada, y entonces la rutina no arranca y este test no mediría nada.
    hardware_session.clear_emergency()
    cam = andor_mod._MockAndorCCD()
    spec = shamrock_mod._MockShamrock()
    backend = step_and_glue.Backend(cam, spec)
    cam.set_read_mode(andor_mod.READ_MODE_SINGLE_TRACK)
    used = []
    real_1d, real_2d = cam.get_1d_spectrum, cam.get_most_recent_image
    cam.get_1d_spectrum = lambda *a, **k: (used.append("1d"), real_1d(*a, **k))[1]
    cam.get_most_recent_image = lambda *a, **k: (used.append("2d"), real_2d(*a, **k))[1]
    backend.measure_single_spectrum(600.0, 0.01)
    assert used and used[0] == "1d"


# ── C-06 y C-07: firmas reales del SDK del Shamrock ───────────────────────────────────────────

class _FakeShamrockDll:
    """Expone sólo las funciones que existen en el SDK, con su número de argumentos real."""

    def __init__(self):
        self.calls = []
        self.slit_um = {1: 75.0}
        self.flipper = {1: 1, 2: 0}

    def _log(self, name, *args):
        self.calls.append((name, tuple(getattr(a, "value", a) for a in args)))

    # unsigned int ShamrockGetSlit(int device, float* width)  — DOS argumentos
    def ShamrockGetSlit(self, device, width_ptr):
        raise AssertionError("ShamrockGetSlit no recibe índice: se usa GetAutoSlitWidth")

    def ShamrockSetSlit(self, device, width):
        raise AssertionError("ShamrockSetSlit no recibe índice: se usa SetAutoSlitWidth")

    def ShamrockGetAutoSlitWidth(self, device, index, width_ptr):
        self._log("ShamrockGetAutoSlitWidth", device, index)
        width_ptr._obj.value = self.slit_um[index.value]
        return shamrock_mod.SHAMROCK_SUCCESS

    def ShamrockSetAutoSlitWidth(self, device, index, width):
        self._log("ShamrockSetAutoSlitWidth", device, index, width)
        self.slit_um[index.value] = width.value
        return shamrock_mod.SHAMROCK_SUCCESS

    def ShamrockGetFlipperMirror(self, device, flipper, port_ptr):
        self._log("ShamrockGetFlipperMirror", device, flipper)
        port_ptr._obj.value = self.flipper[flipper.value]
        return shamrock_mod.SHAMROCK_SUCCESS

    def ShamrockSetFlipperMirror(self, device, flipper, port):
        self._log("ShamrockSetFlipperMirror", device, flipper, port)
        self.flipper[flipper.value] = port.value
        return shamrock_mod.SHAMROCK_SUCCESS


@pytest.fixture
def connected_shamrock(monkeypatch):
    monkeypatch.setattr(shamrock_mod.ShamrockDriver, "_init_dll", lambda self: None)
    drv = shamrock_mod.ShamrockDriver()
    drv._dll = _FakeShamrockDll()
    drv._connected = True
    return drv


def test_get_slit_uses_auto_slit_width_with_index(connected_shamrock):
    ret, width = connected_shamrock.ShamrockGetSlit(shamrock_mod.DEVICE, shamrock_mod.INPUT_SLIT_PORT)
    assert ret == shamrock_mod.SHAMROCK_SUCCESS
    assert width == pytest.approx(75.0)
    assert ("ShamrockGetAutoSlitWidth", (shamrock_mod.DEVICE, shamrock_mod.INPUT_SLIT_PORT)) in connected_shamrock._dll.calls


def test_set_slit_uses_auto_slit_width_with_index(connected_shamrock):
    ret = connected_shamrock.ShamrockSetSlit(shamrock_mod.DEVICE, shamrock_mod.INPUT_SLIT_PORT, 100.0)
    assert ret == shamrock_mod.SHAMROCK_SUCCESS
    name, args = connected_shamrock._dll.calls[-1]
    assert name == "ShamrockSetAutoSlitWidth"
    assert args[:2] == (shamrock_mod.DEVICE, shamrock_mod.INPUT_SLIT_PORT)
    assert args[2] == pytest.approx(100.0)


def test_unconnected_slit_read_is_not_a_plausible_width(monkeypatch):
    monkeypatch.setattr(shamrock_mod.ShamrockDriver, "_init_dll", lambda self: None)
    drv = shamrock_mod.ShamrockDriver()
    ret, width = drv.ShamrockGetSlit()
    assert ret != shamrock_mod.SHAMROCK_SUCCESS
    assert math.isnan(width), "un ancho de 50 µm inventado pasaría por leído"


def test_flipper_uses_flipper_mirror_functions(connected_shamrock):
    ret, port = connected_shamrock.ShamrockGetFlipper(shamrock_mod.DEVICE, 1)
    assert ret == shamrock_mod.SHAMROCK_SUCCESS and port == 1
    assert connected_shamrock.ShamrockSetFlipper(shamrock_mod.DEVICE, 2, 1) == shamrock_mod.SHAMROCK_SUCCESS
    names = [c[0] for c in connected_shamrock._dll.calls]
    assert names == ["ShamrockGetFlipperMirror", "ShamrockSetFlipperMirror"]


def test_random_track_uses_the_exported_sdk_name(monkeypatch):
    """La DLL del banco (atmcd64d.dll 2.104.33065.0, la misma copia que el legado) exporta
    `SetRandomTracks`, en plural (SDK p. 311); `SetRandomTrack` no existe, así que Random-Track
    nunca llegaba a la cámara (verificado leyendo la tabla de exportaciones de la DLL)."""
    class _Dll:
        def __init__(self):
            self.calls = []

        def SetRandomTracks(self, n, areas):
            self.calls.append(("SetRandomTracks", n.value, list(areas)))
            return andor_mod.DRV_SUCCESS

    monkeypatch.setattr(andor_mod.AndorCCDDriver, "_init_dll", lambda self: None)
    cam = andor_mod.AndorCCDDriver()
    cam._dll = _Dll()
    cam._connected = True
    assert cam.set_random_track([(10, 20), (40, 60)]) == andor_mod.DRV_SUCCESS
    assert cam._dll.calls == [("SetRandomTracks", 2, [10, 20, 40, 60])]
