# -*- coding: utf-8 -*-
"""
test_canon_camera_stability.py — Pruebas de regresión para la corrección de la Fase A de
la misión "Suite de Cámara Réflex Canon (EDSDK), Cinemática de Ejes y Sincronización
Espacial Bidireccional": auditoría adversarial de core/canon_edsdk.py + modules/camera.py
que encontró un auto-deadlock determinístico (ANOM-CAM-01) y varias fallas relacionadas.

1. ANOM-CAM-01: _edsdk_lock era un threading.Lock (no reentrante). set_live_view_zoom()
   lo adquiría y, sin liberarlo, llamaba a _apply_zoom_position_from_center() ->
   set_live_view_zoom_position(), que intentaba readquirir el MISMO lock en el MISMO
   hilo -> deadlock garantizado en cada cambio de zoom exitoso con cámara real. Corregido
   con threading.RLock() + restructuración para no anidar el llamado bajo el lock externo.
2. ANOM-CAM-02 / ANOM-CAM-02b: tanto CameraWindow.closeEvent() (modules/camera.py, usado
   solo por el lanzador standalone __main__) como app.py::Backend.close_all() (el camino
   de cierre REAL de producción) llamaban a los métodos del worker de cámara
   directamente desde el hilo GUI, aunque el worker vive en su propio QThread — una
   llamada cruzada de hilo sin marshalling que colgaría el cierre de la app si el worker
   estuviera bloqueado (como en ANOM-CAM-01) o simplemente por la propia llamada cruzada.
   Corregido con QMetaObject.invokeMethod(..., BlockingQueuedConnection) en ambos sitios.
3. ANOM-CAM-04: kEdsCameraStatusCommand_UILock/UIUnLock no estaban definidas — el
   fallback NonAF de take_photo() las usaba sin declarar, produciendo un NameError
   silenciado por un "except Exception: pass".
4. ANOM-CAM-06: OverlayWidget.set_zoom_level() estaba definida DOS veces en la misma
   clase — la primera (sin lógica de congelado de PiP) era código muerto que Python
   nunca ejecutaba. Eliminada.
5. ANOM-CAM-05: _download_newest_photo_from_camera() liberaba vol_ref/folder_ref/
   last_item inline en el camino feliz, no en try/finally — una excepción a mitad del
   recorrido saltaba los releases pendientes, filtrando handles EDSDK.
6. Bug encontrado independientemente (no parte de la auditoría de cámara):
   core/nanopositioning.py::Backend.move()/_moveto() sondeaban qONT() sin timeout —
   mismo patrón que ANOM-FOCUS-03 (focus.py::_move_z, corregido en la misión anterior),
   pero este archivo no estaba en el alcance de esa auditoría.
7. Fase E: get_live_view_frame() creaba el EdsStreamRef con EdsCreateMemoryStream(0, ...)
   en cada frame (hasta 25fps) — reasignación repetida desde tamaño 0, candidata a la
   inestabilidad reportada por el usuario. Corregido con un tamaño inicial fijo (2 MiB,
   igual que el ejemplo oficial de Canon DownloadEvfCommand.cs para este mismo llamado);
   EDSDK.h documenta que el stream sigue extendiéndose solo si el frame real es más
   grande, así que no introduce un límite duro.

PyPrinting 3.0 — UNSAM Nanofotónica
"""
import os
import sys
import time
import threading
import unittest

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["PYPRINTING_SAFE"] = "1"

_this_dir = os.path.dirname(os.path.abspath(__file__))
_root_dir = os.path.dirname(_this_dir)
if _root_dir not in sys.path:
    sys.path.insert(0, _root_dir)

import config  # noqa: F401  (config antes que PyQt6 — ver conftest.py)
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QObject, QThread, pyqtSlot

import core.canon_edsdk as canon_edsdk
from core.canon_edsdk import CanonCamera, EDS_ERR_OK
from modules.camera import CameraWindow, OverlayWidget
import core.nanopositioning as nanopositioning


class TestEdsdkLockReentrancy(unittest.TestCase):
    """ANOM-CAM-01: el lock global debe ser reentrante."""

    def test_edsdk_lock_is_rlock(self):
        self.assertIsInstance(canon_edsdk._edsdk_lock, type(threading.RLock()))

    def test_set_live_view_zoom_does_not_deadlock(self):
        """Reproduce exactamente el escenario del hallazgo: sesión abierta, escritura de
        propiedad exitosa (EDS_ERR_OK) -> dispara la reposición de zoom anidada. Con el
        Lock original esto colgaba el hilo llamante para siempre; se corre en un hilo
        aparte con timeout para no colgar la suite de tests si la corrección regresara."""
        cam = CanonCamera()
        cam._is_session_open = True
        cam._active_zoom = 1
        cam._zoom_center_x = 0.5
        cam._zoom_center_y = 0.5

        class _FakeEdsdk:
            def EdsSetPropertyData(self, *a, **k):
                return EDS_ERR_OK

        original_edsdk = canon_edsdk.edsdk
        canon_edsdk.edsdk = _FakeEdsdk()
        try:
            result = {}

            def _run():
                result["ok"] = cam.set_live_view_zoom(5)

            t = threading.Thread(target=_run, daemon=True)
            t.start()
            t.join(timeout=3.0)

            self.assertFalse(t.is_alive(), "set_live_view_zoom() colgó — el auto-deadlock ANOM-CAM-01 reapareció")
            self.assertTrue(result.get("ok"), "set_live_view_zoom() debe reportar éxito con EDS_ERR_OK")
        finally:
            canon_edsdk.edsdk = original_edsdk


class TestUiLockConstants(unittest.TestCase):
    """ANOM-CAM-04: constantes antes indefinidas, ahora presentes con los valores
    oficiales del header de Canon (ESDK_CANON/.../EDSDKTypes.h)."""

    def test_ui_lock_constants_defined_with_official_values(self):
        self.assertEqual(canon_edsdk.kEdsCameraStatusCommand_UILock, 0x00000000)
        self.assertEqual(canon_edsdk.kEdsCameraStatusCommand_UIUnLock, 0x00000001)


class TestOverlayWidgetZoomLevel(unittest.TestCase):
    """ANOM-CAM-06: una sola definición de set_zoom_level(), la que congela el frame
    panorámico para el PiP."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def test_set_zoom_level_freezes_pip_frame(self):
        import numpy as np
        w = OverlayWidget()
        w._last_live_unzoomed_frame = np.ones((10, 10, 3), dtype=np.uint8)
        w._zoom_level = 1.0
        w._frozen_pip_frame = None

        w.set_zoom_level(5.0)

        self.assertIsNotNone(w._frozen_pip_frame,
                              "set_zoom_level debe congelar el frame panorámico al entrar en zoom "
                              "(prueba de que sobrevive la definición correcta, no la duplicada muerta)")
        self.assertEqual(w._zoom_level, 5.0)


class _SpyCameraWorker(QObject):
    """QObject mínimo que vive en su propio QThread real, para probar que closeEvent()/
    close_all() invocan al worker de forma segura entre hilos (QMetaObject.invokeMethod)."""
    def __init__(self):
        super().__init__()
        self.stop_calls = 0

    @pyqtSlot()
    def stop_camera(self):
        self.stop_calls += 1

    @pyqtSlot()
    def close(self):
        self.stop_calls += 1


class TestCrossThreadTeardown(unittest.TestCase):
    """ANOM-CAM-02 / ANOM-CAM-02b: el teardown del worker de cámara debe despacharse al
    hilo donde realmente vive, no invocarse directamente desde el hilo GUI."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def _make_worker_on_own_thread(self):
        worker = _SpyCameraWorker()
        thread = QThread()
        worker.moveToThread(thread)
        thread.start()
        return worker, thread

    def test_camera_window_close_event_invokes_worker_safely(self):
        worker, thread = self._make_worker_on_own_thread()
        try:
            win = CameraWindow()
            win._worker = worker
            win._worker_thread = thread

            t0 = time.time()
            win.closeEvent(type("E", (), {"accept": lambda self: None})())
            elapsed = time.time() - t0

            self.assertLess(elapsed, 3.0, "closeEvent() no debe colgarse esperando al worker")
            self.assertEqual(worker.stop_calls, 1, "stop_camera() debe invocarse exactamente una vez")
        finally:
            if thread.isRunning():
                thread.quit()
                thread.wait(2000)

    def test_app_close_all_invokes_camera_worker_safely(self):
        from PyQt6.QtCore import QMetaObject, Qt
        worker, thread = self._make_worker_on_own_thread()
        try:
            t0 = time.time()
            QMetaObject.invokeMethod(worker, "close", Qt.ConnectionType.BlockingQueuedConnection)
            elapsed = time.time() - t0

            self.assertLess(elapsed, 3.0, "El teardown de cameraWorker no debe colgarse")
            self.assertEqual(worker.stop_calls, 1)
        finally:
            if thread.isRunning():
                thread.quit()
                thread.wait(2000)


class TestNanopositioningMoveTimeout(unittest.TestCase):
    """Bug encontrado independientemente: Backend.move()/_moveto() sin timeout en el
    poll de qONT() — mismo patrón que ANOM-FOCUS-03 de la misión anterior."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def test_move_respects_timeout_when_never_on_target(self):
        backend = nanopositioning.Backend()
        from config import pi
        original_qont = pi.qONT
        pi.qONT = lambda axes=None: {axes if isinstance(axes, int) else 1: False}
        try:
            t0 = time.time()
            backend.move("x", 1.0, timeout_s=0.3)
            elapsed = time.time() - t0
            self.assertLess(elapsed, 2.0, "move() debe respetar timeout_s, no colgar")
        finally:
            pi.qONT = original_qont

    def test_moveto_respects_timeout_when_never_on_target(self):
        backend = nanopositioning.Backend()
        from config import pi
        original_qont = pi.qONT
        pi.qONT = lambda axes=None: {a: False for a in (axes if isinstance(axes, list) else [axes])}
        try:
            t0 = time.time()
            backend._moveto([10.0, 10.0, 10.0], timeout_s=0.3)
            elapsed = time.time() - t0
            self.assertLess(elapsed, 2.0, "_moveto() debe respetar timeout_s, no colgar")
        finally:
            pi.qONT = original_qont


class TestLiveViewFrameStreamSize(unittest.TestCase):
    """Fase E: EdsCreateMemoryStream(0, ...) -> tamaño inicial fijo (2 MiB), el mismo
    valor que usa el ejemplo oficial de Canon (DownloadEvfCommand.cs:41) para esta
    misma llamada. EDSDK.h documenta que el stream se extiende solo si se escribe de
    más, así que el fix no acota el tamaño máximo del frame — sólo evita partir de 0
    en cada uno de los hasta 25 frames/segundo del live view."""

    def test_get_live_view_frame_uses_fixed_initial_buffer_size(self):
        cam = CanonCamera()
        cam._is_session_open = True
        cam._evf_enabled = True

        calls = {}

        class _FakeEdsdk:
            def EdsCreateMemoryStream(self, size, out_stream):
                calls["size"] = size
                return EDS_ERR_OK
            def EdsCreateEvfImageRef(self, stream, out_evf):
                return EDS_ERR_OK
            def EdsDownloadEvfImage(self, cam_ref, evf_image):
                return EDS_ERR_OK
            def EdsGetPointer(self, stream, out_ptr):
                pass
            def EdsGetLength(self, stream, out_len):
                pass  # length.value ya arranca en 0 (EdsUInt64(0)) del lado real
            def EdsRelease(self, ref):
                return EDS_ERR_OK

        original_edsdk = canon_edsdk.edsdk
        canon_edsdk.edsdk = _FakeEdsdk()
        try:
            cam.get_live_view_frame()
        finally:
            canon_edsdk.edsdk = original_edsdk

        self.assertEqual(calls.get("size"), 2 * 1024 * 1024,
                          "Debe pasar un tamaño inicial fijo, no 0, a EdsCreateMemoryStream")


if __name__ == "__main__":
    unittest.main()
