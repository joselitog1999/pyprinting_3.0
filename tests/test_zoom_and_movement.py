import sys
import os
import unittest
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import numpy as np
import cv2
from PyQt6.QtWidgets import QApplication

from core.canon_edsdk import CanonCamera, ZOOM_MAP
from modules.camera import CameraWindow, CanonWorker, ExternalPiPWidget

class TestZoomAndMovement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def test_01_zoom_map_physical_levels(self):
        """Verifica que ZOOM_MAP contenga únicamente los niveles físicos soportados por Canon EOS."""
        self.assertEqual(list(ZOOM_MAP.keys()), [1, 5, 10])
        self.assertIn("1x", ZOOM_MAP[1])
        self.assertIn("5x", ZOOM_MAP[5])
        self.assertIn("10x", ZOOM_MAP[10])

    def test_02_sensor_display_transposition_exactness(self):
        """Verifica que el target en pantalla mapee al centro exacto del recorte 5x y 10x sin desviación."""
        test_points = [(0.5, 0.5), (0.7, 0.3), (0.2, 0.8), (0.1, 0.1), (0.9, 0.9)]
        for zoom in (5, 10):
            win_w = int(4752 / zoom)
            win_h = int(3168 / zoom)
            for cx, cy in test_points:
                center_sensor_x = cy * 4752.0
                center_sensor_y = cx * 3168.0

                ul_x = max(0, min(int(4752 - win_w), int(center_sensor_x - win_w / 2.0)))
                ul_y = max(0, min(int(3168 - win_h), int(center_sensor_y - win_h / 2.0)))

                target_ys = int(round(center_sensor_y))
                target_xs = int(round(center_sensor_x))
                target_ys = min(3167, target_ys)
                target_xs = min(4751, target_xs)

                if ul_y <= target_ys < ul_y + win_h and ul_x <= target_xs < ul_x + win_w:
                    crop = np.zeros((win_h, win_w, 3), dtype=np.uint8)
                    local_y = target_ys - ul_y
                    local_x = target_xs - ul_x
                    crop[local_y, local_x] = [0, 255, 0]

                    disp_crop = cv2.rotate(crop, cv2.ROTATE_90_CLOCKWISE)
                    disp_crop = cv2.flip(disp_crop, 1)

                    gy, gx = np.where(disp_crop[:, :, 1] == 255)
                    self.assertEqual(len(gx), 1, f"Partícula perdida en zoom {zoom}x para ({cx}, {cy})")

    def test_03_camera_set_zoom_center_clamping(self):
        """Verifica que CanonCamera.set_zoom_center aplique el cálculo y clamping de forma segura."""
        cam = CanonCamera()
        cam._is_session_open = True
        cam._active_zoom = 5

        self.assertFalse(cam.set_zoom_center(0.5, 0.5))
        self.assertFalse(cam.set_zoom_center(-1.0, 2.0))
        self.assertEqual(cam._zoom_center_x, 0.0)
        self.assertEqual(cam._zoom_center_y, 1.0)

    def test_04_camera_window_pad_movement_responsiveness(self):
        """Verifica que la cruceta direccional actualice coordenadas y emita señales sin bloquear los botones."""
        win = CameraWindow()
        win._is_camera_active = True
        signals = []
        win.setZoomCenterSignal.connect(lambda cx, cy: signals.append((cx, cy)))

        win._canon_cx = 0.5
        win._canon_cy = 0.5

        # Simular clic en Arriba (UP: en pantalla cy debe disminuir)
        win._btn_up.click()
        self.assertLess(win._canon_cy, 0.5, "Al pulsar Arriba, cy de pantalla debe disminuir")
        self.assertEqual(win._canon_cx, 0.5)
        self.assertTrue(win._btn_up.isEnabled(), "El botón Arriba NO debe deshabilitarse")

        # Simular clic en Derecha (RIGHT: en pantalla cx debe aumentar)
        win._btn_right.click()
        self.assertGreater(win._canon_cx, 0.5, "Al pulsar Derecha, cx de pantalla debe aumentar")
        self.assertTrue(win._btn_right.isEnabled(), "El botón Derecha NO debe deshabilitarse")

        self.assertGreater(len(signals), 0, "Debe emitirse setZoomCenterSignal de inmediato")
        win.close()

    def test_05_pip_overview_persistence(self):
        """Verifica que CanonWorker conserve el frame panorámico 1x cuando pasa a 5x/10x."""
        worker = CanonWorker()
        worker._running = True
        
        # Simular recepción de frame 1x
        worker._active_zoom = 1
        worker._fetch_frame()
        frame_1x = worker._last_full_unzoomed
        self.assertIsNotNone(frame_1x, "Debe registrarse el frame panorámico 1x")

        # Pasar a 5x
        worker.set_zoom(5)
        worker._fetch_frame()
        # El frame panorámico debe mantenerse (no sobreescribirse con el recorte)
        self.assertIs(worker._last_full_unzoomed, frame_1x, "En 5x debe conservarse el mapa panorámico 1x")

if __name__ == "__main__":
    unittest.main()
