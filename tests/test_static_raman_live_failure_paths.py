# -*- coding: utf-8 -*-
"""
test_static_raman_live_failure_paths.py — Caminos de fallo de hardware en Static Raman.

PyPrinting 3.0 — UNSAM Nanofotónica (DEC-032)

Contra el mock estos caminos son INALCANZABLES: `_MockAndorCCD.start_acquisition()` y
`_MockShamrock.ShamrockSetShutter()` devuelven siempre éxito. Por eso los tests inyectan
cámara y espectrógrafo espía que fallan a demanda y registran el orden de las llamadas. No
se parchea el singleton del mock: los espías envuelven instancias y se descartan con el
test, así que no contaminan a otros archivos (ver `_isolate_andor_mock_geometry`).

Cubre:
1. `start_acquisition()` informa fallos por CÓDIGO, no por excepción: si no devuelve
   DRV_SUCCESS, el obturador del espectrógrafo nunca se abre y el lazo no arranca.
2. Orden de arranque: cámara primero, obturador después (seguro porque StartAcquisition
   no integra hasta el primer tick — confirmado por el operador).
3. Política acordada: si el obturador no confirma, Live sigue pero ADVIERTE, y esa
   advertencia es el mensaje final (no la pisa un "iniciada" posterior).
4. `liveStateChangedSignal` devuelve el estado REAL a ambos botones de Live, para que un
   arranque fallido no deje la UI mostrando "Detener" con nada corriendo.
5. Adquisición única: un cuadro todo-ceros (centinela de lectura fallida del driver real)
   no se reporta como "exitosamente".
"""
import os
import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ["PYPRINTING_SAFE"] = "1"
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import numpy as np
from PyQt6 import QtWidgets

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

from pyspectrum.drivers.andor_ccd_driver import (
    get_andor_ccd, DRV_SUCCESS, DRV_NOT_INITIALIZED, DRV_ACQUIRING,
    READ_MODE_FVB, READ_MODE_IMAGE,
)
from pyspectrum.drivers.shamrock_driver import (
    get_shamrock, SHAMROCK_SUCCESS, SHAMROCK_NOT_INITIALIZED,
)
from pyspectrum.modules.static_raman import StaticRamanBackend, StaticRamanWidget
from pyspectrum.ui.raman_2d_inspector import Raman2DInspectorWidget


class _SpyCamera:
    """Cámara que falla a demanda y registra el orden de llamadas. Los datos son
    deterministas (constantes, no el ruido del mock) para que el test no dependa de él."""

    def __init__(self, log, start_ret=DRV_SUCCESS, start_raises=None, zeros=False,
                 read_mode=READ_MODE_FVB):
        self._inner = get_andor_ccd(force_mock=True)
        self._log = log
        self._start_ret = start_ret
        self._start_raises = start_raises
        self._zeros = zeros
        self._read_mode = read_mode

    def start_acquisition(self):
        self._log.append("camera.start")
        if self._start_raises is not None:
            raise self._start_raises
        return self._start_ret

    def abort_acquisition(self):
        self._log.append("camera.abort")
        return DRV_SUCCESS

    def get_read_mode(self):
        return self._read_mode

    def get_1d_spectrum(self):
        return np.zeros(1004) if self._zeros else np.full(1004, 600.0)

    def get_most_recent_image(self):
        return np.zeros((1002, 1004)) if self._zeros else np.full((1002, 1004), 600.0)

    def __getattr__(self, name):
        return getattr(self._inner, name)


class _SpySpectrometer:
    def __init__(self, log, open_ret=SHAMROCK_SUCCESS, close_ret=SHAMROCK_SUCCESS):
        self._inner = get_shamrock(force_mock=True)
        self._log = log
        self._open_ret = open_ret
        self._close_ret = close_ret

    def ShamrockSetShutter(self, device, mode):
        self._log.append(f"shutter({mode})")
        return self._open_ret if mode == 1 else self._close_ret

    def __getattr__(self, name):
        return getattr(self._inner, name)


class _Harness(unittest.TestCase):
    def _make(self, **cam_kw):
        spec_kw = {k: cam_kw.pop(k) for k in ("open_ret", "close_ret") if k in cam_kw}
        self.log = []
        self.cam = _SpyCamera(self.log, **cam_kw)
        self.spec = _SpySpectrometer(self.log, **spec_kw)
        self.be = StaticRamanBackend(self.cam, self.spec)
        self.messages, self.live_states = [], []
        self.be.statusMessageSignal.connect(self.messages.append)
        self.be.liveStateChangedSignal.connect(self.live_states.append)

    def tearDown(self):
        if hasattr(self, "be"):
            self.be.live_timer.stop()

    @property
    def last_message(self):
        # La barra de estado muestra SÓLO el último mensaje: es lo que el operador ve.
        return self.messages[-1] if self.messages else ""


class TestLiveStartFailures(_Harness):

    def test_camera_failure_code_never_opens_shutter(self):
        """El defecto original: el código de retorno se descartaba y el lazo arrancaba."""
        self._make(start_ret=DRV_NOT_INITIALIZED)
        self.be.toggle_live(True)
        self.assertNotIn("shutter(1)", self.log,
                         "El obturador se abrió aunque la cámara no arrancó")
        self.assertFalse(self.be.live_timer.isActive(), "El lazo Live arrancó sin cámara")
        self.assertEqual(self.live_states, [False])
        self.assertIn("NO se inició", self.last_message)
        self.assertIn(str(DRV_NOT_INITIALIZED), self.last_message)

    def test_camera_already_acquiring_hints_at_exploration(self):
        self._make(start_ret=DRV_ACQUIRING)
        self.be.toggle_live(True)
        self.assertFalse(self.be.live_timer.isActive())
        self.assertIn("Exploración", self.last_message)

    def test_driver_exception_is_handled_as_failure(self):
        self._make(start_raises=OSError("access violation"))
        self.be.toggle_live(True)
        self.assertNotIn("shutter(1)", self.log)
        self.assertFalse(self.be.live_timer.isActive())
        self.assertEqual(self.live_states, [False])
        self.assertIn("excepción", self.last_message)


class TestLiveStartSuccessAndPolicy(_Harness):

    def test_camera_starts_before_shutter_opens(self):
        self._make()
        self.be.toggle_live(True)
        self.assertLess(self.log.index("camera.start"), self.log.index("shutter(1)"),
                        f"Orden incorrecto: {self.log}")
        self.assertTrue(self.be.live_timer.isActive())
        self.assertEqual(self.live_states, [True])
        self.assertEqual(self.last_message, "Adquisición Live Raman iniciada.")

    def test_unconfirmed_shutter_keeps_live_running_but_warns_last(self):
        """Política acordada (A): seguir en vivo con advertencia — y que sea el ÚLTIMO
        mensaje, porque uno intermedio lo pisaría un 'iniciada' posterior."""
        self._make(open_ret=SHAMROCK_NOT_INITIALIZED)
        self.be.toggle_live(True)
        self.assertTrue(self.be.live_timer.isActive())
        self.assertEqual(self.live_states, [True])
        self.assertIn("SIN confirmar", self.last_message)
        self.assertNotIn("iniciada.", self.last_message)

    def test_stop_closes_shutter_and_reports_real_state(self):
        self._make()
        self.be.toggle_live(True)
        self.be.toggle_live(False)
        self.assertFalse(self.be.live_timer.isActive())
        self.assertIn("shutter(0)", self.log)
        self.assertEqual(self.live_states, [True, False])

    def test_stop_with_unconfirmed_close_warns(self):
        self._make(close_ret=SHAMROCK_NOT_INITIALIZED)
        self.be.toggle_live(True)
        self.be.toggle_live(False)
        self.assertIn("no confirmó el cierre", self.last_message)


class TestSingleAcquisitionReporting(_Harness):

    def test_all_zero_frame_is_not_reported_as_success(self):
        self._make(zeros=True)
        self.be.acquire_single()
        self.assertIn("cuadro vacío", self.last_message)
        self.assertNotIn("exitosamente", self.last_message)
        self.assertIn("shutter(0)", self.log, "El obturador no se cerró tras la adquisición")

    def test_all_zero_2d_frame_is_detected_too(self):
        self._make(zeros=True, read_mode=READ_MODE_IMAGE)
        self.be.acquire_single()
        self.assertIn("cuadro vacío", self.last_message)

    def test_unconfirmed_shutter_warning_survives_as_final_message(self):
        """Regresión de DEC-031: la advertencia existía pero la pisaba 'exitosamente'."""
        self._make(open_ret=SHAMROCK_NOT_INITIALIZED)
        self.be.acquire_single()
        self.assertIn("SIN confirmar", self.last_message)
        self.assertNotIn("exitosamente", self.last_message)

    def test_valid_acquisition_reports_success(self):
        self._make()
        self.be.acquire_single()
        self.assertEqual(self.last_message, "Espectro único adquirido exitosamente.")
        self.assertEqual(self.log.count("shutter(1)"), 1)
        self.assertEqual(self.log.count("shutter(0)"), 1)


class TestLiveStateReachesTheButtons(_Harness):

    def test_widget_setter_does_not_bounce_back_to_backend(self):
        w = StaticRamanWidget()
        emitted = []
        w.toggleLiveRamanSignal.connect(emitted.append)
        w.set_live_state(True)
        self.assertTrue(w.btn_live.isChecked())
        w.set_live_state(False)
        self.assertFalse(w.btn_live.isChecked())
        self.assertEqual(emitted, [], "set_live_state re-emitió hacia el backend")

    def test_failed_start_unchecks_both_live_buttons(self):
        """End-to-end: el operador presiona Live, la cámara falla, y ningún botón queda
        mostrando 'Detener' con nada corriendo."""
        self._make(start_ret=DRV_NOT_INITIALIZED)
        w = StaticRamanWidget()
        insp = Raman2DInspectorWidget()
        self.be.make_connection(w, insp)

        w.btn_live.click()

        self.assertFalse(self.be.live_timer.isActive())
        self.assertFalse(w.btn_live.isChecked(), "El botón de espectro quedó en 'Detener'")
        self.assertIn("Live Raman", w.btn_live.text())
        self.assertFalse(insp.btn_live.isChecked(), "El botón del Inspector quedó en 'Detener'")
        self.assertTrue(insp.btn_single.isEnabled())


if __name__ == "__main__":
    unittest.main()
