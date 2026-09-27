# -*- coding: utf-8 -*-
"""
test_shamrock_driver_error_propagation.py — El driver real del Shamrock no inventa éxitos.

PyPrinting 3.0 — UNSAM Nanofotónica (DEC-034)

Cuatro métodos de `ShamrockDriver` (Get/Set del obturador y del flipper) respondían
`SHAMROCK_SUCCESS` desde su propia rama `except`: si la DLL lanzaba, el software informaba que
el obturador se había accionado sin que el hardware lo confirmara (`DEC-014`). El resto de la
clase ya devolvía `SHAMROCK_COMMUNICATION_ERROR` en el mismo caso; estos tests fijan la paridad.

Contra el mock este camino es inalcanzable (`_MockShamrock` nunca lanza), así que se construye
el driver real SIN cargar ninguna DLL (`__new__` + atributos) y se le inyecta una DLL falsa.
Nada de esto toca hardware.
"""
import os
import sys
import threading
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ["PYPRINTING_SAFE"] = "1"
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6 import QtWidgets

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

from pyspectrum.drivers.andor_ccd_driver import get_andor_ccd
from pyspectrum.drivers.shamrock_driver import (
    ShamrockDriver, get_shamrock,
    SHAMROCK_SUCCESS, SHAMROCK_COMMUNICATION_ERROR, SHAMROCK_NOT_INITIALIZED,
    SHAMROCK_NOT_AVAILABLE,
)
from pyspectrum.modules.static_raman import StaticRamanBackend


class _RaisingDll:
    """DLL cuyos exports lanzan todos, como una violación de acceso de ctypes."""

    def __getattr__(self, name):
        def _boom(*args, **kwargs):
            raise OSError(f"exception: access violation in {name}")
        return _boom


class _ReturningDll:
    """DLL cuyos exports devuelven siempre el mismo código."""

    def __init__(self, code):
        self.code = code

    def __getattr__(self, name):
        return lambda *args, **kwargs: self.code


def _driver_with(dll, connected=True):
    drv = ShamrockDriver.__new__(ShamrockDriver)
    drv._lock = threading.RLock()
    drv._dll = dll
    drv._connected = connected
    drv._settling_until = 0.0
    drv._last_motion_type = ""
    drv.geometry_verified = False
    return drv


class TestDllExceptionIsReportedAsError(unittest.TestCase):

    def setUp(self):
        self.drv = _driver_with(_RaisingDll())

    def test_set_shutter_open(self):
        self.assertEqual(self.drv.ShamrockSetShutter(0, 1), SHAMROCK_COMMUNICATION_ERROR)

    def test_set_shutter_close(self):
        self.assertEqual(self.drv.ShamrockSetShutter(0, 0), SHAMROCK_COMMUNICATION_ERROR)

    def test_get_shutter_reports_error_and_keeps_placeholder(self):
        ret, mode = self.drv.ShamrockGetShutter(0)
        self.assertEqual(ret, SHAMROCK_COMMUNICATION_ERROR)
        # El relleno no cambia: el contrato es el código de retorno, no el valor.
        self.assertEqual(mode, 1)

    def test_set_flipper(self):
        self.assertEqual(self.drv.ShamrockSetFlipper(0, 2, 0), SHAMROCK_COMMUNICATION_ERROR)

    def test_get_flipper_reports_error_and_keeps_placeholder(self):
        ret, port = self.drv.ShamrockGetFlipper(0, 1)
        self.assertEqual(ret, SHAMROCK_COMMUNICATION_ERROR)
        self.assertEqual(port, 0)


class TestNormalPathsUnchanged(unittest.TestCase):
    """El arreglo toca sólo la rama `except`: los códigos de la DLL pasan intactos."""

    def test_dll_codes_pass_through(self):
        for code in (SHAMROCK_SUCCESS, SHAMROCK_COMMUNICATION_ERROR, SHAMROCK_NOT_AVAILABLE):
            drv = _driver_with(_ReturningDll(code))
            self.assertEqual(drv.ShamrockSetShutter(0, 1), code)
            self.assertEqual(drv.ShamrockSetFlipper(0, 2, 0), code)
            self.assertEqual(drv.ShamrockGetShutter(0)[0], code)
            self.assertEqual(drv.ShamrockGetFlipper(0, 1)[0], code)

    def test_uninitialized_driver_unchanged(self):
        drv = _driver_with(None, connected=False)
        self.assertEqual(drv.ShamrockSetShutter(0, 1), SHAMROCK_NOT_INITIALIZED)
        self.assertEqual(drv.ShamrockSetFlipper(0, 2, 0), SHAMROCK_NOT_INITIALIZED)
        self.assertEqual(drv.ShamrockGetShutter(0), (SHAMROCK_NOT_INITIALIZED, 1))
        self.assertEqual(drv.ShamrockGetFlipper(0, 1), (SHAMROCK_NOT_INITIALIZED, 0))


class _DriverBackedShutterSpectrometer:
    """Mock para todo salvo el obturador, que pasa por el driver REAL con una DLL que lanza."""

    def __init__(self):
        self._inner = get_shamrock(force_mock=True)
        self._real = _driver_with(_RaisingDll())

    def ShamrockSetShutter(self, device, mode):
        return self._real.ShamrockSetShutter(device, mode)

    def __getattr__(self, name):
        return getattr(self._inner, name)


class TestStaticRamanSeesTheDriverFailure(unittest.TestCase):
    """De punta a punta: la excepción de la DLL llega al operador como "SIN confirmar".

    Antes de DEC-034 el docstring de `_set_spectrograph_shutter` documentaba este hueco: el
    chequeo del código de retorno era correcto, pero el driver le entregaba un éxito falso.
    """

    def test_acquire_single_warns_when_dll_raises_on_shutter(self):
        be = StaticRamanBackend(get_andor_ccd(force_mock=True), _DriverBackedShutterSpectrometer())
        messages = []
        be.statusMessageSignal.connect(messages.append)
        try:
            be.acquire_single()
        finally:
            be.live_timer.stop()
        self.assertTrue(messages, "acquire_single no informó nada")
        self.assertIn("SIN confirmar", messages[-1])
        self.assertNotIn("exitosamente", messages[-1])


if __name__ == "__main__":
    unittest.main()
