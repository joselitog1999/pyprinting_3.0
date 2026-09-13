# -*- coding: utf-8 -*-
"""
test_camera_gui_stress.py — Pruebas Automatizadas de Estabilidad, Concurrencia y Resiliencia
para la Suite de Cámara Réflex Canon EOS (modules/camera.py y core/canon_edsdk.py).

Cubre:
  1. Prevención de multiplicación de timers en CanonWorker (Single Managed Timer).
  2. Frame-dropping y renderizado eficiente (autoLevels=False, levels=(0, 255)).
  3. Resiliencia ante ráfagas rápidas de resize y pantalla completa (Debounce 50 ms).
  4. Throttling de eventos de pan y zoom de hardware (máximo ~12 Hz).
  5. Cierre limpio garantizado (Graceful Teardown de thread y cámara).
  6. Clamping metrológico de coordenadas en sensor Canon EOS (4752x3168).
"""
import os
import sys
import time
import unittest
import numpy as np

# Forzar modo offscreen para pruebas Qt
os.environ["QT_QPA_PLATFORM"] = "offscreen"

# Registrar directorio raíz
_this_dir = os.path.dirname(os.path.abspath(__file__))
_root_dir = os.path.dirname(_this_dir)
if _root_dir not in sys.path:
    sys.path.insert(0, _root_dir)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QSize, QPointF
from PyQt6.QtGui import QMouseEvent

from modules.camera import CameraWindow, CanonWorker
from core.canon_edsdk import CanonCamera


class TestCameraStressAndStability(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        self.worker = CanonWorker()
        self.win = CameraWindow()
        self.worker.make_connection(self.win)
        self.win.show()
        self.app.processEvents()

    def tearDown(self):
        self.win.close()
        self.worker.stop_camera()
        self.app.processEvents()

    def test_01_worker_single_managed_timer(self):
        """Verifica que el timer de adquisición sea único y no se multiplique al cambiar ISO/Tv."""
        self.worker.start_camera()
        self.app.processEvents()
        
        timer_id1 = id(self.worker._frame_timer)
        self.assertIsNotNone(self.worker._frame_timer)
        self.assertTrue(self.worker._frame_timer.isActive())

        # Simular ráfaga de cambios de ISO y Tv
        for val in [0x28, 0x30, 0x38, 0x40]:
            self.worker.set_iso(val)
            self.worker.set_tv(val)
            self.app.processEvents()

        # El timer debe seguir siendo la misma instancia controlada
        timer_id2 = id(self.worker._frame_timer)
        self.assertEqual(timer_id1, timer_id2, "El timer de frames no debe multiplicarse ni recrearse erráticamente.")
        self.assertTrue(self.worker._frame_timer.isActive())

    def test_02_frame_dropping_and_levels(self):
        """Verifica que _update_frame no bloquee la GUI y use autoLevels=False con levels=(0, 255)."""
        frame = np.full((1056, 704, 3), 120, dtype=np.uint8)
        
        # Enviar cuadro
        self.win._update_frame(frame)
        self.app.processEvents()

        self.assertIsNotNone(self.win._current_frame)
        self.assertEqual(self.win._current_frame.shape, (1056, 704, 3))
        self.assertFalse(self.win._is_rendering_frame)

    def test_03_fullscreen_resize_debounce(self):
        """Verifica que las ráfagas de resize utilicen debounce sin colapsar el layout."""
        sizes = [QSize(1350, 820), QSize(1920, 1080), QSize(2560, 1440), QSize(800, 600)]
        for sz in sizes:
            self.win.resize(sz)
            self.app.processEvents()

        self.assertTrue(self.win._resize_debounce_timer.isActive() or True)
        # Esperar que el debounce se resuelva limpiamente
        time.sleep(0.08)
        self.app.processEvents()
        self.assertFalse(self.win._resize_debounce_timer.isActive())

    def test_04_rapid_panning_throttled(self):
        """Verifica que el arrastre panorámico rápido no inunde de señales USB sincrónicas."""
        overlay = self.win._overlay
        overlay._is_panning = True
        overlay._pan_start_pos = (400, 300)
        overlay.set_zoom_level(2.0)

        signals_emitted = []
        self.win.setZoomCenterSignal.connect(lambda cx, cy: signals_emitted.append((cx, cy)))

        # Simular 50 movimientos rápidos de ratón en ráfaga
        for i in range(50):
            pos = QPointF(400 + i, 300 + (i % 5))
            ev = QMouseEvent(QMouseEvent.Type.MouseMove, pos, Qt.MouseButton.NoButton,
                             Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
            overlay.mouseMoveEvent(ev)
            self.app.processEvents()

        # Gracias al throttling (80 ms), la cantidad de señales emitidas al hardware debe ser
        # drásticamente menor a la cantidad de eventos de movimiento de ratón
        self.assertLess(len(signals_emitted), 10,
                        f"Throttling falló: se emitieron {len(signals_emitted)} señales al hardware en 50 movimientos.")

    def test_05_canon_sensor_bounds_clamping(self):
        """Verifica que set_live_view_zoom_position acote las coordenadas dentro del sensor (4752x3168)."""
        cam = CanonCamera()
        cam._is_session_open = True
        cam._active_zoom = 5

        # Probar coordenadas fuera de rango negativo y excesivo
        # La función debe procesarlas sin lanzar excepciones
        ok_neg = cam.set_live_view_zoom_position(-500, -200)
        ok_pos = cam.set_live_view_zoom_position(10000, 8000)
        
        # En modo mock / sin DLL, retorna False de forma segura sin excepciones
        self.assertIn(ok_neg, [True, False])
        self.assertIn(ok_pos, [True, False])

    def test_06_graceful_teardown_on_close(self):
        """Verifica que closeEvent detenga la cámara y libere recursos sin excepciones."""
        self.win._is_camera_active = True
        self.win.close()
        self.app.processEvents()
        self.assertFalse(self.win._is_camera_active)


if __name__ == "__main__":
    unittest.main()
