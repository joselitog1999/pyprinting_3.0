# -*- coding: utf-8 -*-
"""Tipos de argumento de la DLL de la cámara (refuerzo de R4-E, DEC-040).

Con `argtypes` declarados, una llamada con otra cantidad o tipo de argumentos da un error de Python
en lugar de que la DLL lea o escriba memoria arbitraria (lo que pasó con la ranura del Shamrock, C-06).
La tabla `_ANDOR_ARGTYPES` se escribió desde los prototipos del SDK2 v2.104
(`docs/bibliografia/Software Development Kit.pdf`). Estos tests comprueban que:
1. cada función que el driver llama tiene su declaración;
2. el driver le pasa a cada función argumentos que ctypes acepta con esa declaración, usando una
   DLL falsa cuyas funciones son punteros ctypes con exactamente esos prototipos.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYPRINTING_SAFE", "1")

import ctypes
import re
from pathlib import Path

import pytest

from pyspectrum.drivers import andor_ccd_driver as andor_mod

ROOT = Path(__file__).resolve().parent.parent


def test_every_called_camera_function_has_declared_argtypes():
    src = (ROOT / "pyspectrum/drivers/andor_ccd_driver.py").read_text(encoding="utf-8")
    called = set(re.findall(r"self\._dll\.([A-Za-z_]\w*)\(", src))
    missing = sorted(called - set(andor_mod._ANDOR_ARGTYPES))
    assert missing == [], f"funciones de la cámara sin argtypes: {missing}"


class _PrototypedDll:
    """Cada función es un puntero ctypes con el prototipo declarado: ctypes valida los argumentos."""

    def __init__(self):
        self._keep = []
        self.reached = set()
        for name, argtypes in andor_mod._ANDOR_ARGTYPES.items():
            proto = ctypes.CFUNCTYPE(ctypes.c_uint, *argtypes)
            fn = proto(self._make_impl(name))
            self._keep.append(fn)
            setattr(self, name, fn)

    def _make_impl(self, name):
        def impl(*args):
            self.reached.add(name)
            return andor_mod.DRV_SUCCESS
        return impl


@pytest.fixture
def cam(monkeypatch):
    monkeypatch.setattr(andor_mod.AndorCCDDriver, "_init_dll", lambda self: None)
    drv = andor_mod.AndorCCDDriver()
    drv._dll = _PrototypedDll()
    drv._connected = True
    return drv


def test_driver_calls_match_the_declared_prototypes(cam):
    calls = [
        lambda: cam.set_temperature(-60), lambda: cam.get_temperature(), lambda: cam.cooler_on(),
        lambda: cam.cooler_off(), lambda: cam.set_cooler_mode(0), lambda: cam.set_output_amplifier(0),
        lambda: cam.set_emccd_gain(0), lambda: cam.get_emccd_gain(), lambda: cam.set_exposure_time(0.1),
        lambda: cam.start_acquisition(), lambda: cam.abort_acquisition(), lambda: cam.get_most_recent_image(),
        lambda: cam.set_read_mode(andor_mod.READ_MODE_SINGLE_TRACK), lambda: cam.set_single_track(501, 40),
        lambda: cam.set_image(1, 1, 1, 1004, 1, 1002), lambda: cam.get_1d_spectrum(),
        lambda: cam.set_acquisition_mode(1), lambda: cam.get_status_checked(),
        lambda: cam.wait_for_acquisition_timeout(250), lambda: cam.get_acquisition_timings(),
        lambda: cam.get_total_number_images_acquired(), lambda: cam.get_acquired_data_checked(1004),
        lambda: cam.get_status(), lambda: cam.get_number_preamp_gains(), lambda: cam.get_preamp_gain(0),
        lambda: cam.set_preamp_gain(0), lambda: cam.get_number_hs_speeds(), lambda: cam.get_hs_speed(0),
        lambda: cam.set_hs_speed(0), lambda: cam.set_shutter_mode(0), lambda: cam.set_multi_track(2, 10, 0),
        lambda: cam.set_random_track([(10, 20), (40, 60)]), lambda: cam.get_tracks_2d_spectrum(2),
    ]
    calls += [lambda: cam.initialize(), lambda: cam.close()]
    for call in calls:
        try:
            call()
        except ctypes.ArgumentError as exc:
            pytest.fail(f"argumento mal tipado para la DLL: {exc}")
        except andor_mod.DeviceUnavailable:
            pass  # close() deja la cámara sin conexión
    # Varios métodos del driver atrapan cualquier excepción (incluido un ArgumentError de ctypes) y
    # devuelven un valor por defecto, así que no alcanza con que no salte nada: cada función tiene
    # que haber llegado de verdad a la DLL con los argumentos que el prototipo acepta.
    src = (ROOT / "pyspectrum/drivers/andor_ccd_driver.py").read_text(encoding="utf-8")
    called = set(re.findall(r"self\._dll\.([A-Za-z_]\w*)\(", src))
    not_reached = sorted(called - cam._dll.reached)
    assert not_reached == [], f"estas llamadas no llegaron a la DLL (¿argumento mal tipado?): {not_reached}"
