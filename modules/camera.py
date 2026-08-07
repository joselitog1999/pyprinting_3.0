# -*- coding: utf-8 -*-
"""
camera.py — Ventana de Cámara Réflex Canon EOS 500D (EDSDK) & Suite de Microfotónica
PyPrinting 3.0 — UNSAM Nanofotónica — PyQt6

Fusión completa de camera_20260804.py y canon_test_20260804.py:

  Backend (Canon EDSDK — CanonWorker):
    - Transmisión Live View a 25.0 FPS con motor adaptativo EDSDK.
    - Captura fotográfica 15.1 MP (4752×3168) multi-formato (.jpg, .png, .tiff, .bmp).
    - Ajuste dinámico de ISO (bloqueo de 5s iniciales), Tv, Modo AE y Zoom (1×, 2×, 5×, 10×).
    - Ajuste en vivo: Balance RGB + Grises Transmisión (CLim + Paletas LUT).
    - Modo MOCK automático cuando no hay cámara física conectada.

  Frontend (CameraWindow):
    - Panel de Detección de Partículas con Trackpy (ROI, preview en vivo).
    - Panel de Mediciones de Distancia y Ángulo (tabla exportable).
    - OverlayWidget: Reglas H/V deslizables en µm, snap a partículas, zoom, pan, medición, ROI.
    - Calibración espacial (SetScaleDialog: 3 métodos µm/px).
    - ROI → Confocal: transforma un ROI de cámara en coordenadas de escaneo confocal.
    - Controles Canon EDSDK: ISO, Tv, Zoom, Modo Color, CLim, LUT, Ganancias RGB.
    - Log de Diagnóstico EDSDK emergente (EDSDKLogDialog).

  Laser 532 nm:
    - Laser532Window: control de potencia (slider + presets) y obturador.
    - Laser532Backend: worker que aplica el voltaje via NI-DAQ.

Mapeo de coordenadas para Confocal:
  - Cámara Hacia la DERECHA = Platina +Y
  - Cámara Hacia ABAJO     = Platina +X
  - Rango físico platina PI: 0.0 a 100.0 µm
"""
from __future__ import annotations

import sys
import os
import math
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── Registrar directorio raíz e incondicionalmente .venv en sys.path ───────────
_this_dir = os.path.dirname(os.path.abspath(__file__))
_parent1 = os.path.dirname(_this_dir)
_parent2 = os.path.dirname(_parent1)

_venv_site = os.path.join(_parent1, ".venv", "Lib", "site-packages")
if os.path.exists(_venv_site) and sys.version_info[:2] == (3, 13) and _venv_site not in sys.path:
    sys.path.insert(0, _venv_site)

for _p in [_parent1, _parent2, os.path.join(_parent1, "core"),
           os.path.join(_parent1, "modules"), os.path.join(_parent1, "analysis")]:
    if os.path.exists(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np
import cv2
import pyqtgraph as pg
from PyQt6.QtCore    import (Qt, QObject, QThread, QTimer, QRectF,
                               pyqtSignal, pyqtSlot, QPointF, QPoint)
from PyQt6.QtWidgets import (QApplication, QMainWindow, QFrame, QWidget,
                               QGridLayout, QHBoxLayout, QVBoxLayout,
                               QLabel, QLineEdit, QPushButton, QCheckBox,
                               QDoubleSpinBox, QSlider, QSpinBox,
                               QTableWidget, QTableWidgetItem, QHeaderView,
                               QDialog, QDialogButtonBox, QFormLayout,
                               QGroupBox, QMessageBox, QFileDialog,
                               QInputDialog, QSplitter, QTextEdit,
                               QStackedWidget, QComboBox, QStatusBar)
from PyQt6.QtGui     import (QPainter, QPen, QColor, QFont, QPixmap, QImage)

try:
    from config import (SAFE_MODE, CAMERA_INDEX, CAMERA_WIDTH, CAMERA_HEIGHT,
                        PIXEL_SIZE_UM, LASER_532_V_MIN, LASER_532_V_MAX,
                        DEFAULT_DATA_PATH, PI_STAGE_RANGE_UM,
                        DEFAULT_TRACKPY_DIAMETER_PX, DEFAULT_TRACKPY_MINMASS,
                        DEFAULT_TRACKPY_SEPARATION_PX)
except ImportError:
    try:
        from ..config import (SAFE_MODE, CAMERA_INDEX, CAMERA_WIDTH, CAMERA_HEIGHT,
                              PIXEL_SIZE_UM, LASER_532_V_MIN, LASER_532_V_MAX,
                              DEFAULT_DATA_PATH, PI_STAGE_RANGE_UM,
                              DEFAULT_TRACKPY_DIAMETER_PX, DEFAULT_TRACKPY_MINMASS,
                              DEFAULT_TRACKPY_SEPARATION_PX)
    except ImportError:
        SAFE_MODE = True; CAMERA_INDEX = 1; CAMERA_WIDTH = 1280; CAMERA_HEIGHT = 720
        PIXEL_SIZE_UM = 0.059; LASER_532_V_MIN = 1.0; LASER_532_V_MAX = 5.0
        DEFAULT_DATA_PATH = Path("C:/Data"); PI_STAGE_RANGE_UM = 100.0
        DEFAULT_TRACKPY_DIAMETER_PX = 9; DEFAULT_TRACKPY_MINMASS = 100
        DEFAULT_TRACKPY_SEPARATION_PX = 5

try:
    from nidaq import set_laser532_voltage, open_shutter, close_shutter, SHUTTERS
except ImportError:
    try:
        from core.nidaq import set_laser532_voltage, open_shutter, close_shutter, SHUTTERS
    except ImportError:
        def set_laser532_voltage(v): pass
        def open_shutter(s): pass
        def close_shutter(s): pass
        SHUTTERS = ["shutter532"]

try:
    import trackpy as tp
    import pandas as pd
    _TRACKPY_AVAILABLE = True
except ImportError:
    _TRACKPY_AVAILABLE = False
    print("[Camera] trackpy no disponible — detección deshabilitada.")

try:
    import picasso.localize as picasso_loc
    _PICASSO_AVAILABLE = True
except Exception as _e_picasso:
    _PICASSO_AVAILABLE = False
    print(f"[Camera] picasso no disponible — {_e_picasso}")

try:
    from canon_edsdk import (CanonCamera, ISO_MAP, REV_ISO_MAP, FULL_ISO_LIST,
                             TV_MAP, REV_TV_MAP, FULL_TV_LIST, ZOOM_MAP, REV_ZOOM_MAP,
                             AE_MODE_MAP, kEdsPropID_ISOSpeed, kEdsPropID_Tv, kEdsPropID_AEMode)
except ImportError:
    try:
        from core.canon_edsdk import (CanonCamera, ISO_MAP, REV_ISO_MAP, FULL_ISO_LIST,
                                      TV_MAP, REV_TV_MAP, FULL_TV_LIST, ZOOM_MAP, REV_ZOOM_MAP,
                                      AE_MODE_MAP, kEdsPropID_ISOSpeed, kEdsPropID_Tv, kEdsPropID_AEMode)
    except ImportError:
        # Stub mínimo para ejecutar sin EDSDK (SAFE_MODE)
        CanonCamera = None
        ISO_MAP = {}; REV_ISO_MAP = {}; FULL_ISO_LIST = []
        TV_MAP  = {}; REV_TV_MAP  = {}; FULL_TV_LIST  = []
        ZOOM_MAP = {}; REV_ZOOM_MAP = {}
        AE_MODE_MAP = {}
        kEdsPropID_ISOSpeed = 0x0; kEdsPropID_Tv = 0x0; kEdsPropID_AEMode = 0x0


# ══════════════════════════════════════════════════════════════════════════════
#  MOCK CAPTURE (Imagen estática de referencia o frame sintético animado)
# ══════════════════════════════════════════════════════════════════════════════

class _MockCapture:
    def __init__(self):
        self._n = 0
        self._static_frame = self._load_ref_image()

    def _load_ref_image(self) -> Optional[np.ndarray]:
        contenido_dir = Path(__file__).parent / "contenido"
        possible_files = [
            contenido_dir / "foto_ref.JPG",
            contenido_dir / "foto_ref.jpg",
            contenido_dir / "foto_ref.jpeg",
            contenido_dir / "foto_ref.png",
        ]
        for filepath in possible_files:
            if filepath.exists():
                try:
                    from PIL import Image as PILImage
                    img = PILImage.open(filepath).convert("RGB")
                    img = img.resize((CAMERA_WIDTH, CAMERA_HEIGHT))
                    print(f"[Camera MOCK] Cargada imagen estática de referencia: {filepath.name}")
                    return np.array(img, dtype=np.uint8)
                except Exception as e:
                    print(f"[Camera MOCK] Error cargando {filepath}: {e}")
        return None

    def isOpened(self): return True
    def release(self):  pass
    def set(self, *a):  pass

    def read(self):
        self._n += 1
        if self._static_frame is not None:
            return True, self._static_frame.copy()

        W, H = CAMERA_WIDTH, CAMERA_HEIGHT
        frame = (np.random.rand(H, W, 3) * 20 + 35).astype(np.uint8)
        t = self._n * 0.04
        for cx, cy, r, col in [
            (int(W*0.38 + 4*np.sin(t)),     int(H*0.52 + 3*np.cos(t*0.7)),  12, (180,220,255)),
            (int(W*0.61 + 3*np.sin(t*0.5)), int(H*0.38 + 4*np.cos(t*0.3)),   9, (140,255,200)),
        ]:
            ys, xs = np.ogrid[-cy:H-cy, -cx:W-cx]
            glow   = np.exp(-(xs*xs + ys*ys) / (2*(r*2)**2))
            for c, b in enumerate(col):
                frame[:, :, c] = np.clip(frame[:, :, c] + (glow*b).astype(np.uint8), 0, 255)
        mx, my = W//2, H//2
        frame[my-1:my+2, mx-20:mx+20] = [255, 80, 80]
        frame[my-20:my+20, mx-1:mx+2] = [255, 80, 80]
        return True, frame


# ══════════════════════════════════════════════════════════════════════════════
#  VENTANA FLOTANTE DE LOGS Y DIAGNÓSTICO EDSDK
# ══════════════════════════════════════════════════════════════════════════════

class EDSDKLogDialog(QDialog):
    """Ventana emergente desplegable para logs y eventos en tiempo real de la cámara Canon EDSDK."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Diagnóstico & Eventos Canon EDSDK")
        self.resize(650, 400)
        lo = QVBoxLayout(self)

        self._txt_log = QTextEdit()
        self._txt_log.setReadOnly(True)
        self._txt_log.setStyleSheet(
            "font-family: monospace; font-size: 10px; background-color: #111; color: #00ff66;")
        lo.addWidget(self._txt_log)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btn_box.rejected.connect(self.accept)
        lo.addWidget(btn_box)

    def append_log(self, msg: str):
        self._txt_log.append(msg)


# ══════════════════════════════════════════════════════════════════════════════
#  LIVE VIEW WORKER THREAD  —  Canon EDSDK (verbatim de canon_test_20260804.py)
# ══════════════════════════════════════════════════════════════════════════════

class CanonWorker(QObject):
    frameSignal      = pyqtSignal(np.ndarray)
    fullFrameSignal  = pyqtSignal(np.ndarray)
    statusSignal     = pyqtSignal(str)
    logSignal        = pyqtSignal(str)
    connectedSignal  = pyqtSignal(bool)
    propsReadySignal = pyqtSignal(list, list, int, int, int)  # iso_vals, tv_vals, ae_mode, curr_iso, curr_tv
    photoSavedSignal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._cam = CanonCamera(log_callback=self._emit_log) if CanonCamera else None
        self._running = False
        self._timer = None
        self._last_valid_frame = None
        self._mock_n = 0
        self._mode_color = "Color RGB"
        self._clim_min   = 0
        self._clim_max   = 255
        self._lut_idx    = 0
        self._r_gain     = 1.0
        self._g_gain     = 1.0
        self._b_gain     = 1.0
        self._noise_floor = 0
        self._denoise     = False

    def _emit_log(self, msg: str):
        self.logSignal.emit(msg)

    @pyqtSlot()
    def start_camera(self):
        self.statusSignal.emit("Conectando con cámara Canon EOS por USB...")
        self._emit_log("Iniciando conexión USB con cámara Canon EOS...")
        self._connect_time = time.time()
        ok = self._cam.open_session() if self._cam else False
        if ok:
            # 1. Emitir inmediatamente lista completa para asegurar disponibilidad instantánea
            self.propsReadySignal.emit(FULL_ISO_LIST, FULL_TV_LIST, 0, 0, 0)
            self.statusSignal.emit("Cámara Canon EOS 500D Conectada | Estabilizando sensor (5s)...")

            # 2. Habilitar Live View y arrancar bucle de frames adaptativo
            self._cam.enable_live_view()
            self._running = True
            self.connectedSignal.emit(True)
            QTimer.singleShot(10, self._fetch_frame_adaptive)

            # 3. Programar temporizador de 5 segundos para consulta segura de hardware
            QTimer.singleShot(5000, self._query_properties_after_delay)
        else:
            self.connectedSignal.emit(False)
            msg = "⚠ No se detectó cámara Canon EOS por USB — Modo Simulación MOCK Activo"
            self.statusSignal.emit(msg)
            self._emit_log(msg)
            self._running = True
            self.propsReadySignal.emit(FULL_ISO_LIST, FULL_TV_LIST, 0, 0, 0)
            QTimer.singleShot(10, self._fetch_frame_adaptive)

    def _fetch_frame_adaptive(self):
        if not self._running: return
        t0 = time.perf_counter()

        self._fetch_frame()

        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        is_stabilized = (time.time() - getattr(self, '_connect_time', 0)) >= 5.0
        target_ms = 40.0  # 25.0 FPS estrictos

        if is_stabilized:
            delay_ms = max(1, int(round(target_ms - elapsed_ms)))
        else:
            delay_ms = max(10, int(round(target_ms - elapsed_ms)))

        if self._running:
            QTimer.singleShot(delay_ms, self._fetch_frame_adaptive)

    def _query_properties_after_delay(self):
        if not self._running or not self._cam or not self._cam._is_session_open: return

        self._running = False
        time.sleep(0.05)

        try:
            ae_mode  = self._cam.get_property_value(kEdsPropID_AEMode)
            cam_iso = self._cam.get_property_desc(kEdsPropID_ISOSpeed)
            cam_tv  = self._cam.get_property_desc(kEdsPropID_Tv)
            curr_iso = self._cam.get_property_value(kEdsPropID_ISOSpeed)
            curr_tv  = self._cam.get_property_value(kEdsPropID_Tv)

            combined_iso = list(FULL_ISO_LIST)
            for v in cam_iso:
                if v not in combined_iso: combined_iso.append(v)

            combined_tv = list(FULL_TV_LIST)
            for v in cam_tv:
                if v not in combined_tv: combined_tv.append(v)

            self.propsReadySignal.emit(combined_iso, combined_tv, ae_mode, curr_iso, curr_tv)
            self.statusSignal.emit("Cámara Canon EOS 500D Estabilizada | Live View a 25 FPS Constantes")
            self._emit_log("✓ Periodo de 5s completado. Live View estabilizado a 25.0 FPS continuos.")
        except Exception as _e:
            self._emit_log(f"Advertencia durante consulta diferida: {_e}")
        finally:
            self._running = True
            QTimer.singleShot(10, self._fetch_frame_adaptive)

    @pyqtSlot()
    def stop_camera(self):
        self._running = False
        if self._cam:
            self._cam.close_session()
            self._cam.terminate_sdk()
        self.statusSignal.emit("Cámara desconectada.")
        self._emit_log("Cámara desconectada y recursos liberados.")

        self._mode_color = "Color RGB"
        self._clim_min   = 0
        self._clim_max   = 255
        self._lut_idx    = 0
        self._r_gain     = 1.0
        self._g_gain     = 1.0
        self._b_gain     = 1.0
        self._noise_floor = 0
        self._denoise     = False

    @pyqtSlot()
    def close(self):
        """Alias para stop_camera() invocado durante el cierre de la app."""
        self.stop_camera()

    def _fetch_frame(self):
        if not self._running: return
        if self._cam and self._cam._is_session_open and self._cam._evf_enabled:
            jpeg_bytes = self._cam.get_live_view_frame()
            if jpeg_bytes:
                img_array = np.frombuffer(jpeg_bytes, dtype=np.uint8)
                frame_bgr = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                if frame_bgr is not None:
                    frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                    # Emitir el frame completo 1x para la miniatura PiP
                    unzoomed_frame = cv2.rotate(frame_rgb, cv2.ROTATE_90_CLOCKWISE)
                    unzoomed_frame = cv2.flip(unzoomed_frame, 1)
                    self.fullFrameSignal.emit(unzoomed_frame)

                    # Procesar rotación 90° + espejo + zoom + supresión de ruido + ajustes en vivo
                    processed = self._cam.process_frame_live_adjustments(
                        frame_rgb, mode=self._mode_color, clim_min=self._clim_min,
                        clim_max=self._clim_max, lut_idx=self._lut_idx,
                        r_gain=self._r_gain, g_gain=self._g_gain, b_gain=self._b_gain,
                        noise_floor=self._noise_floor, denoise=self._denoise)
                    self._last_valid_frame = processed
                    self.frameSignal.emit(processed)
                    return
            if self._last_valid_frame is not None:
                self.frameSignal.emit(self._last_valid_frame)
                return

        # Frame de prueba (Simulador MOCK)
        self._mock_n += 1
        W, H = 1056, 704
        t = self._mock_n * 0.05
        frame = np.full((H, W, 3), 35, dtype=np.uint8)
        cx, cy = int(W/2 + 20*np.sin(t)), int(H/2 + 15*np.cos(t))
        cv2.circle(frame, (cx, cy), 18, (62, 207, 142), -1)
        cv2.circle(frame, (cx, cy), 45, (74, 158, 255), 2)
        cv2.putText(frame, "CANON EOS 500D MOCK STREAM (1056x704)", (30, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (245, 166, 35), 2)
        self.fullFrameSignal.emit(frame.copy())

        if self._cam:
            processed = self._cam.process_frame_live_adjustments(
                frame, mode=self._mode_color, clim_min=self._clim_min,
                clim_max=self._clim_max, lut_idx=self._lut_idx,
                r_gain=self._r_gain, g_gain=self._g_gain, b_gain=self._b_gain,
                noise_floor=self._noise_floor, denoise=self._denoise)
        else:
            processed = frame
            if self._denoise:
                processed = cv2.medianBlur(processed, 3)
            if self._noise_floor > 0:
                mask = np.max(processed, axis=2) < self._noise_floor
                processed[mask] = 0

        self._last_valid_frame = processed
        self.frameSignal.emit(processed)

    @pyqtSlot(str, int, int, int, float, float, float, int, bool)
    def set_live_adjustments(self, mode: str, cmin: int, cmax: int,
                             lut_idx: int, r_g: float, g_g: float, b_g: float,
                             noise_floor: int = 0, denoise: bool = False):
        self._mode_color = mode
        self._clim_min   = cmin
        self._clim_max   = cmax
        self._lut_idx    = lut_idx
        self._r_gain     = r_g
        self._g_gain     = g_g
        self._b_gain     = b_g
        self._noise_floor = noise_floor
        self._denoise     = denoise

    @pyqtSlot(float, float)
    def set_zoom_center(self, cx: float, cy: float):
        if self._cam:
            self._cam.set_zoom_center(cx, cy)
            if self._cam._is_session_open and getattr(self._cam, '_active_zoom', 1) in (5, 10):
                hw_x = int(cx * 4752)
                hw_y = int(cy * 3168)
                self._cam.set_live_view_zoom_position(hw_x, hw_y)

    @pyqtSlot(int)
    def set_zoom(self, zoom_val: int):
        if self._cam:
            self._cam.set_live_view_zoom(zoom_val)
            self._emit_log(f"Zoom Live View configurado a: {ZOOM_MAP.get(zoom_val, zoom_val)}")

    @pyqtSlot(int)
    def set_iso(self, val: int):
        if self._cam and self._cam._is_session_open:
            was_running = self._running
            self._running = False
            ok = self._cam.set_property_value(kEdsPropID_ISOSpeed, val)
            if ok:
                lbl = ISO_MAP.get(val, f"0x{val:02X}")
                self.statusSignal.emit(f"ISO configurado a: {lbl}")
                self._emit_log(f"ISO cambiado exitosamente a {lbl}")
            self._running = was_running
            if self._running:
                QTimer.singleShot(10, self._fetch_frame_adaptive)

    @pyqtSlot(int)
    def set_tv(self, val: int):
        if self._cam and self._cam._is_session_open:
            was_running = self._running
            self._running = False
            ok = self._cam.set_property_value(kEdsPropID_Tv, val)
            if ok:
                lbl = TV_MAP.get(val, f"0x{val:02X}")
                self.statusSignal.emit(f"Velocidad (Tv) configurada a: {lbl}")
                self._emit_log(f"Velocidad Tv cambiada exitosamente a {lbl}")
            self._running = was_running
            if self._running:
                QTimer.singleShot(10, self._fetch_frame_adaptive)

    @pyqtSlot(str)
    def take_photo(self, target_format: str = "jpg"):
        ext = target_format.lower().strip(".")
        if ext not in ("jpg", "jpeg", "png", "tiff", "tif", "bmp"):
            ext = "jpg"

        if self._cam and self._cam._is_session_open:
            was_running = self._running
            self._running = False
            self.statusSignal.emit(f"📸 Capturando foto de 15 MP (4752×3168)... Formato .{ext.upper()}")
            ok, saved_path = self._cam.take_photo(target_format=ext)
            if ok and saved_path:
                self.statusSignal.emit(f"✅ ¡Foto 15 MP guardada!: {saved_path}")
                self._emit_log(f"✅ ¡FOTO GUARDADA EN DISCO!: {saved_path}")
                self.photoSavedSignal.emit(saved_path)
            else:
                self._emit_log("❌ Error en el comando de obturación de foto.")
            self._running = was_running
            if self._running:
                QTimer.singleShot(350, self._fetch_frame_adaptive)
        else:
            # En modo MOCK: crear foto sintética de alta resolución
            save_dir = self._cam._save_dir if self._cam else str(DEFAULT_DATA_PATH)
            os.makedirs(save_dir, exist_ok=True)
            t_str = time.strftime("%Y%m%d_%H%M%S")
            mock_photo_path = os.path.join(save_dir, f"CANON_EOS500D_MOCK_{t_str}.{ext}")

            img = np.full((3168, 4752, 3), 45, dtype=np.uint8)
            cv2.circle(img, (2376, 1584), 350, (62, 207, 142), -1)
            cv2.circle(img, (2376, 1584), 800, (74, 158, 255), 4)
            cv2.putText(img, f"CANON EOS 500D - MOCK PHOTO 15.1 MP (4752x3168) - .{ext.upper()}",
                        (150, 200), cv2.FONT_HERSHEY_SIMPLEX, 2.2, (255, 255, 255), 4)
            cv2.imwrite(mock_photo_path, img)

            msg = f"✅ FOTO SIMULACIÓN MOCK 15.1 MP CREADA EXITOSAMENTE EN: {mock_photo_path}"
            self.statusSignal.emit(msg)
            self._emit_log(msg)
            self.photoSavedSignal.emit(mock_photo_path)

    @pyqtSlot(str)
    def set_save_dir(self, path: str):
        if self._cam:
            self._cam.set_save_directory(path)

    @pyqtSlot(str)
    def set_directory(self, path: str):
        self.set_save_dir(path)

    @pyqtSlot()
    def start_stream(self):
        self.start_camera()

    @pyqtSlot()
    def stop_stream(self):
        self.stop_camera()

    def make_connection(self, window: 'CameraWindow'):
        """Conecta este worker a la CameraWindow."""
        window.startCameraSignal.connect(self.start_camera)
        window.stopCameraSignal.connect(self.stop_camera)
        window.setZoomSignal.connect(self.set_zoom)
        window.setZoomCenterSignal.connect(self.set_zoom_center)
        window.setIsoSignal.connect(self.set_iso)
        window.setTvSignal.connect(self.set_tv)
        window.takePhotoSignal.connect(self.take_photo)
        window.liveParamsSignal.connect(self.set_live_adjustments)
        window.sendRoiSignal.connect(lambda roi: None)

        self.frameSignal.connect(window._update_frame)
        self.fullFrameSignal.connect(window._update_full_frame)
        self.statusSignal.connect(window._update_status)
        self.logSignal.connect(window._append_log)
        self.connectedSignal.connect(window._on_connected)
        self.propsReadySignal.connect(window._populate_properties)
        self.photoSavedSignal.connect(window._on_photo_saved)


# ══════════════════════════════════════════════════════════════════════════════
#  OVERLAY WIDGET (Sincronizado al 100% con PyQtGraph mapToScene)
# ══════════════════════════════════════════════════════════════════════════════

class OverlayWidget(QWidget):
    pointClickedSignal = pyqtSignal(float, float)   # (fx, fy) en fracción global de imagen (0-1)
    zoomChangedSignal  = pyqtSignal(float, float, float, float) # (fx0, fy0, fx1, fy1)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)

        self._graphics_widget = None
        self._img_item        = None

        self._scale_set   = False
        self._um_per_px   = PIXEL_SIZE_UM

        self._ref_pos: Optional[tuple[float, float]] = None
        self._particles: list[tuple[float, float, float]] = [] # [(fx, fy, mass)]
        self._measure_pts: list[tuple[float, float]] = []     # [(fx, fy)]
        self._roi_rect: Optional[tuple[float, float, float, float]] = None # (fx0,fy0,fx1,fy1)

        # Reglas Tri-estado: 0 = desactivadas, 1 = Par 1 (H1, V1), 2 = Par 1 y Par 2
        self._rulers_state = 0
        self._ruler1_h = 0.5; self._ruler1_v = 0.5
        self._ruler2_h = 0.3; self._ruler2_v = 0.7
        self._drag_ruler = None

        # Zoom In-Window: levels (1.0, 2.0, 4.0)
        self._zoom_level = 1.0
        self._zoom_center = (0.5, 0.5)
        self._is_panning = False
        self._pan_start_pos = None

        # Dragging ROI
        self._drag_roi = False
        self._roi_start = None

        self._mode = "none" # "ref" | "measure" | "roi" | "none"
        self._snap_highlight: Optional[tuple[float, float]] = None
        self._pip_enabled = False

    def set_pip_enabled(self, enabled: bool):
        self._pip_enabled = enabled
        self.update()

    def bind_views(self, graphics_widget: pg.GraphicsLayoutWidget, img_item: pg.ImageItem):
        self._graphics_widget = graphics_widget
        self._img_item        = img_item

    def get_img_dims(self) -> tuple[float, float]:
        """Obtiene las dimensiones reales (W, H) de la imagen actualmente renderizada."""
        if self._img_item is not None:
            try:
                img = self._img_item.image
                if img is not None:
                    s = img.shape
                    return (float(s[0]), float(s[1]))
            except Exception:
                pass
        return (float(CAMERA_WIDTH), float(CAMERA_HEIGHT))

    # ── Transformaciones Geométricas Nativas (100% Sincronizadas) ─────────────

    def screen_to_frac(self, sx: float, sy: float) -> tuple[float, float]:
        if self._img_item is not None and self._graphics_widget is not None:
            try:
                scene_pt = self._graphics_widget.mapToScene(QPoint(int(sx), int(sy)))
                img_pt = self._img_item.mapFromScene(scene_pt)
                W, H = self.get_img_dims()
                fx = max(0.0, min(1.0, img_pt.x() / W))
                fy = max(0.0, min(1.0, img_pt.y() / H))
                return (fx, fy)
            except Exception:
                pass
        W, H = self.width(), self.height()
        if W <= 0 or H <= 0: return (0.5, 0.5)
        fx0, fy0, fx1, fy1 = self.viewport_bounds()
        fx = fx0 + (sx / W) * (fx1 - fx0)
        fy = fy0 + (sy / H) * (fy1 - fy0)
        return (max(0.0, min(1.0, fx)), max(0.0, min(1.0, fy)))

    def frac_to_screen(self, fx: float, fy: float) -> tuple[float, float]:
        if self._img_item is not None and self._graphics_widget is not None:
            try:
                W, H = self.get_img_dims()
                px = fx * W
                py = fy * H
                scene_pt = self._img_item.mapToScene(QPointF(px, py))
                widget_pt = self._graphics_widget.mapFromScene(scene_pt)
                return (widget_pt.x(), widget_pt.y())
            except Exception:
                pass
        W, H = self.width(), self.height()
        fx0, fy0, fx1, fy1 = self.viewport_bounds()
        sx = ((fx - fx0) / (fx1 - fx0)) * W
        sy = ((fy - fy0) / (fy1 - fy0)) * H
        return (sx, sy)

    # ── Métodos de Zoom y Pan ──────────────────────────────────────────────────

    def set_zoom_level(self, level: float, center: Optional[tuple[float, float]] = None):
        self._zoom_level = max(1.0, min(10.0, level))
        if center is not None:
            self._zoom_center = center
        self._clamp_zoom_center()
        fx0, fy0, fx1, fy1 = self.viewport_bounds()
        self.zoomChangedSignal.emit(fx0, fy0, fx1, fy1)
        self.update()

    def zoom_in(self):
        if self._zoom_level < 2.0:
            self.set_zoom_level(2.0)
        elif self._zoom_level < 5.0:
            self.set_zoom_level(5.0)
        elif self._zoom_level < 10.0:
            self.set_zoom_level(10.0)

    def zoom_out(self):
        if self._zoom_level > 5.0:
            self.set_zoom_level(5.0)
        elif self._zoom_level > 2.0:
            self.set_zoom_level(2.0)
        else:
            self.set_zoom_level(1.0)

    def zoom_home(self):
        if self._ref_pos is not None:
            self.set_zoom_level(1.0, center=self._ref_pos)
        else:
            self.set_zoom_level(1.0, center=(0.5, 0.5))

    def _clamp_zoom_center(self):
        half_w = 0.5 / self._zoom_level
        half_h = 0.5 / self._zoom_level
        cx = max(half_w, min(1.0 - half_w, self._zoom_center[0]))
        cy = max(half_h, min(1.0 - half_h, self._zoom_center[1]))
        self._zoom_center = (cx, cy)

    def viewport_bounds(self) -> tuple[float, float, float, float]:
        half_w = 0.5 / self._zoom_level
        half_h = 0.5 / self._zoom_level
        cx, cy = self._zoom_center
        return (cx - half_w, cy - half_h, cx + half_w, cy + half_h)

    # ── API pública ────────────────────────────────────────────────────────────

    def set_scale(self, um_per_px: float):
        self._um_per_px = um_per_px
        self._scale_set  = True
        self.update()

    def set_mode(self, mode: str):
        self._mode = mode
        self.update()

    def set_ref(self, fx: float, fy: float):
        self._ref_pos = (fx, fy)
        self.update()

    def clear_ref(self):
        self._ref_pos = None
        self.update()

    def set_particles(self, pts: list):
        self._particles = pts
        self.update()

    def clear_particles(self):
        self._particles = []
        self.update()

    def set_measure_points(self, pts: list):
        self._measure_pts = pts
        self.update()

    def clear_measure(self):
        self._measure_pts = []
        self.update()

    def set_roi(self, rect: Optional[tuple]):
        self._roi_rect = rect
        self.update()

    def clear_roi(self):
        self._roi_rect = None
        self.update()

    def cycle_rulers(self) -> int:
        self._rulers_state = (self._rulers_state + 1) % 3
        self.update()
        return self._rulers_state

    def roi_fractions(self) -> Optional[tuple[float, float, float, float]]:
        if self._roi_rect is None: return None
        x0, y0, x1, y1 = self._roi_rect
        return (min(x0,x1), min(y0,y1), max(x0,x1), max(y0,y1))

    # ── Snap con Shift ─────────────────────────────────────────────────────────

    def find_nearest_snap_point(self, fx: float, fy: float, max_dist_frac=0.05) -> Optional[tuple[float, float]]:
        candidates = []
        if self._ref_pos:
            candidates.append(self._ref_pos)
        for pt in self._particles:
            candidates.append((pt[0], pt[1]))

        best_pt = None
        best_d = max_dist_frac
        for cx, cy in candidates:
            d = math.hypot(cx - fx, cy - fy)
            if d < best_d:
                best_d = d
                best_pt = (cx, cy)
        return best_pt

    def set_full_unzoomed_frame(self, frame: np.ndarray):
        self._last_live_unzoomed_frame = frame
        if self._zoom_level == 1.0 or not hasattr(self, '_frozen_pip_frame') or self._frozen_pip_frame is None:
            self._frozen_pip_frame = frame
            self.update()

    def set_zoom_level(self, level: float, center: Optional[tuple[float, float]] = None):
        old_level = self._zoom_level
        self._zoom_level = max(1.0, min(10.0, level))
        if center is not None:
            self._zoom_center = center
        self._clamp_zoom_center()

        # Congelar fotograma completo de 1x al hacer zoom para no degradar resolución/FPS
        if old_level == 1.0 and self._zoom_level > 1.0:
            if hasattr(self, '_last_live_unzoomed_frame') and self._last_live_unzoomed_frame is not None:
                self._frozen_pip_frame = self._last_live_unzoomed_frame.copy()
        elif self._zoom_level == 1.0:
            if hasattr(self, '_last_live_unzoomed_frame') and self._last_live_unzoomed_frame is not None:
                self._frozen_pip_frame = self._last_live_unzoomed_frame

        fx0, fy0, fx1, fy1 = self.viewport_bounds()
        self.zoomChangedSignal.emit(fx0, fy0, fx1, fy1)
        self.update()

    def pan_by_arrow(self, key: int):
        if self._zoom_level <= 1.0:
            return
        step = 0.5 / self._zoom_level
        cx, cy = self._zoom_center
        if key == Qt.Key.Key_Left:
            cx -= step
        elif key == Qt.Key.Key_Right:
            cx += step
        elif key == Qt.Key.Key_Up:
            cy -= step
        elif key == Qt.Key.Key_Down:
            cy += step
        self.set_zoom_level(self._zoom_level, center=(cx, cy))

    def get_pip_rect(self) -> QRectF:
        mw, mh = 190.0, 125.0
        mx0 = 15.0
        my0 = max(10.0, float(self.height()) - mh - 15.0)
        return QRectF(mx0, my0, mw, mh)

    def _draw_pip_minimap(self, p: QPainter):
        pip_rect = self.get_pip_rect()
        mx0, my0, mw, mh = pip_rect.x(), pip_rect.y(), pip_rect.width(), pip_rect.height()

        # Dibujar contenedor fondo oscuro translúcido y borde dorado
        p.setPen(QPen(QColor(245, 166, 35, 220), 1.5))
        p.setBrush(QColor(15, 23, 42, 220))
        p.drawRoundedRect(QRectF(mx0 - 4, my0 - 22, mw + 8, mh + 26), 6, 6)

        # Título
        p.setPen(QColor(245, 166, 35, 255))
        p.setFont(QFont("Monospace", 8, QFont.Weight.Bold))
        p.drawText(int(mx0), int(my0 - 6), f"Navegación Zoom ({self._zoom_level:.1f}x)")

        # Renderizar imagen miniatura estática congelada (1x)
        pip_frame = getattr(self, '_frozen_pip_frame', None)
        if pip_frame is None:
            pip_frame = getattr(self, '_last_live_unzoomed_frame', None)

        if pip_frame is not None:
            try:
                img = pip_frame
                h, w, c = img.shape
                qimg = QImage(img.data, w, h, w * c, QImage.Format.Format_RGB888)
                p.drawImage(pip_rect, qimg)
            except Exception:
                p.fillRect(pip_rect, QColor(30, 30, 30))
        else:
            p.fillRect(pip_rect, QColor(30, 30, 30))

        # Recuadro dinámico cian mapeado estrictamente al área de imagen (sin bordes negros)
        fx0, fy0, fx1, fy1 = self.viewport_bounds()
        bx0 = mx0 + fx0 * mw
        by0 = my0 + fy0 * mh
        bw  = (fx1 - fx0) * mw
        bh  = (fy1 - fy0) * mh

        # Dibujar recuadro cian dinámico con transparencia
        p.setPen(QPen(QColor(0, 255, 255, 240), 2))
        p.setBrush(QColor(0, 255, 255, 35))
        p.drawRect(QRectF(bx0, by0, bw, bh))

        # Retículo central en la miniatura
        mcx = bx0 + bw / 2.0
        mcy = by0 + bh / 2.0
        p.setPen(QPen(QColor(255, 200, 0, 200), 1))
        p.drawLine(QPointF(mcx - 4, mcy), QPointF(mcx + 4, mcy))
        p.drawLine(QPointF(mcx, mcy - 4), QPointF(mcx, mcy + 4))

    # ── Paint Event ───────────────────────────────────────────────────────────

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self._rulers_state > 0:
            self._draw_rulers(p)
        if self._ref_pos:
            self._draw_ref(p)
        if self._particles:
            self._draw_particles(p)
        if self._measure_pts:
            self._draw_measure(p)
        if self._roi_rect:
            self._draw_roi(p)
        if self._snap_highlight:
            self._draw_snap_highlight(p)

        if getattr(self, '_pip_enabled', True):
            self._draw_pip_minimap(p)

    def _draw_rulers(self, p: QPainter):
        pen1 = QPen(QColor(245, 166, 35, 220), 1, Qt.PenStyle.DashLine)
        p.setPen(pen1)
        p.setFont(QFont("Monospace", 9))
        W, H = self.get_img_dims()

        sx1_v, _ = self.frac_to_screen(self._ruler1_v, 0)
        _, sy1_h = self.frac_to_screen(0, self._ruler1_h)
        p.drawLine(0, int(sy1_h), self.width(), int(sy1_h))
        p.drawLine(int(sx1_v), 0, int(sx1_v), self.height())

        if self._scale_set:
            p.drawText(int(sx1_v) + 5, 16, f"R1-V: {self._ruler1_v*W*self._um_per_px:.3f}µm")
            p.drawText(5, int(sy1_h) - 5, f"R1-H: {self._ruler1_h*H*self._um_per_px:.3f}µm")
        else:
            p.drawText(int(sx1_v) + 5, 16, f"R1-V: {self._ruler1_v*W:.2f}px")
            p.drawText(5, int(sy1_h) - 5, f"R1-H: {self._ruler1_h*H:.2f}px")

        if self._rulers_state >= 2:
            pen2 = QPen(QColor(74, 158, 255, 220), 1, Qt.PenStyle.DashLine)
            p.setPen(pen2)
            sx2_v, _ = self.frac_to_screen(self._ruler2_v, 0)
            _, sy2_h = self.frac_to_screen(0, self._ruler2_h)
            p.drawLine(0, int(sy2_h), self.width(), int(sy2_h))
            p.drawLine(int(sx2_v), 0, int(sx2_v), self.height())

            if self._scale_set:
                p.drawText(int(sx2_v) + 5, 32, f"R2-V: {self._ruler2_v*W*self._um_per_px:.3f}µm")
                p.drawText(5, int(sy2_h) - 18, f"R2-H: {self._ruler2_h*H*self._um_per_px:.3f}µm")
            else:
                p.drawText(int(sx2_v) + 5, 32, f"R2-V: {self._ruler2_v*W:.2f}px")
                p.drawText(5, int(sy2_h) - 18, f"R2-H: {self._ruler2_h*H:.2f}px")

    def _draw_ref(self, p: QPainter):
        sx, sy = self.frac_to_screen(self._ref_pos[0], self._ref_pos[1])
        r = 14
        pen = QPen(QColor(74, 158, 255, 240), 2)
        p.setPen(pen)
        p.drawEllipse(int(sx-r), int(sy-r), 2*r, 2*r)
        p.drawLine(int(sx-r-6), int(sy), int(sx+r+6), int(sy))
        p.drawLine(int(sx), int(sy-r-6), int(sx), int(sy+r+6))
        p.setFont(QFont("Monospace", 9, QFont.Weight.Bold))
        p.drawText(int(sx + r + 4), int(sy - 4), "REF (Láser)")

    def _draw_particles(self, p: QPainter):
        p.setPen(QPen(QColor(62, 207, 142, 220), 1.5))
        p.setFont(QFont("Monospace", 8, QFont.Weight.Bold))
        for i, (fx, fy, *_) in enumerate(self._particles):
            sx, sy = self.frac_to_screen(fx, fy)
            p.drawEllipse(int(sx-10), int(sy-10), 20, 20)
            p.drawText(int(sx + 12), int(sy - 3), str(i+1))

    def _draw_measure(self, p: QPainter):
        pts = self._measure_pts
        p.setPen(QPen(QColor(229, 83, 75, 240), 2))
        p.setFont(QFont("Monospace", 9, QFont.Weight.Bold))
        W, H = self.get_img_dims()

        for i, (fx, fy) in enumerate(pts):
            sx, sy = self.frac_to_screen(fx, fy)
            p.drawEllipse(int(sx-5), int(sy-5), 10, 10)
            p.drawText(int(sx+8), int(sy-4), str(i+1))

        if len(pts) == 2:
            (fx1, fy1), (fx2, fy2) = pts
            sx1, sy1 = self.frac_to_screen(fx1, fy1)
            sx2, sy2 = self.frac_to_screen(fx2, fy2)
            p.setPen(QPen(QColor(229, 83, 75, 180), 1.5, Qt.PenStyle.DashLine))
            p.drawLine(QPointF(sx1, sy1), QPointF(sx2, sy2))

            dx_px = (fx2 - fx1) * W
            dy_px = (fy2 - fy1) * H
            dist_px = math.hypot(dx_px, dy_px)
            angle   = math.degrees(math.atan2(dy_px, dx_px))

            mx, my = int((sx1+sx2)/2), int((sy1+sy2)/2)
            p.setPen(QPen(QColor(245, 166, 35, 255)))

            if self._scale_set:
                dist_um = dist_px * self._um_per_px
                lbl = f"d={dist_um:.3f}µm θ={angle:.1f}°"
            else:
                lbl = f"d={dist_px:.1f}px θ={angle:.1f}°"
            p.drawText(mx+6, my-6, lbl)

    def _draw_roi(self, p: QPainter):
        x0, y0, x1, y1 = self._roi_rect
        sx0, sy0 = self.frac_to_screen(min(x0,x1), min(y0,y1))
        sx1, sy1 = self.frac_to_screen(max(x0,x1), max(y0,y1))
        p.setPen(QPen(QColor(139, 124, 248, 220), 1.5, Qt.PenStyle.DashLine))
        p.drawRect(int(sx0), int(sy0), int(sx1-sx0), int(sy1-sy0))
        p.setFont(QFont("Monospace", 8, QFont.Weight.Bold))
        p.setPen(QPen(QColor(139, 124, 248, 255)))
        p.drawText(int(sx0+4), int(sy0+14), "ROI Confocal")

    def _draw_snap_highlight(self, p: QPainter):
        if not self._snap_highlight: return
        sx, sy = self.frac_to_screen(self._snap_highlight[0], self._snap_highlight[1])
        p.setPen(QPen(QColor(0, 255, 255, 240), 2))
        p.drawEllipse(int(sx-14), int(sy-14), 28, 28)

    # ── Mouse Interaction ─────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        sx, sy = event.position().x(), event.position().y()
        fx, fy = self.screen_to_frac(sx, sy)

        # Clic dentro de la miniatura PiP (si está activa)
        pip_rect = self.get_pip_rect()
        if getattr(self, '_pip_enabled', True) and pip_rect.contains(QPointF(sx, sy)):
            mw, mh = pip_rect.width(), pip_rect.height()
            cx = max(0.0, min(1.0, (sx - pip_rect.x()) / mw))
            cy = max(0.0, min(1.0, (sy - pip_rect.y()) / mh))
            self.set_zoom_level(self._zoom_level, center=(cx, cy))
            self._drag_pip = True
            return

        if self._zoom_level > 1.0 and (event.button() == Qt.MouseButton.MiddleButton or
                                        (event.button() == Qt.MouseButton.LeftButton and self._mode == "none")):
            self._is_panning = True
            self._pan_start_pos = (sx, sy)
            return

        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            snap = self.find_nearest_snap_point(fx, fy)
            if snap: fx, fy = snap

        if self._rulers_state > 0:
            sx1_v, _ = self.frac_to_screen(self._ruler1_v, 0)
            _, sy1_h = self.frac_to_screen(0, self._ruler1_h)
            if abs(sy - sy1_h) < 10: self._drag_ruler = 'h1'; return
            if abs(sx - sx1_v) < 10: self._drag_ruler = 'v1'; return

            if self._rulers_state >= 2:
                sx2_v, _ = self.frac_to_screen(self._ruler2_v, 0)
                _, sy2_h = self.frac_to_screen(0, self._ruler2_h)
                if abs(sy - sy2_h) < 10: self._drag_ruler = 'h2'; return
                if abs(sx - sx2_v) < 10: self._drag_ruler = 'v2'; return

        if self._mode == "roi":
            self._roi_start = (fx, fy)
            self._drag_roi  = True
            return

        self.pointClickedSignal.emit(fx, fy)

    def mouseMoveEvent(self, event):
        sx, sy = event.position().x(), event.position().y()
        fx, fy = self.screen_to_frac(sx, sy)

        # Arrastrado dentro de la miniatura PiP
        if getattr(self, '_drag_pip', False):
            pip_rect = self.get_pip_rect()
            mw, mh = pip_rect.width(), pip_rect.height()
            cx = max(0.0, min(1.0, (sx - pip_rect.x()) / mw))
            cy = max(0.0, min(1.0, (sy - pip_rect.y()) / mh))
            self.set_zoom_level(self._zoom_level, center=(cx, cy))
            return

        if self._is_panning and self._pan_start_pos:
            dsx = sx - self._pan_start_pos[0]
            dsy = sy - self._pan_start_pos[1]
            self._pan_start_pos = (sx, sy)
            fx0, fy0, fx1, fy1 = self.viewport_bounds()
            dfx = -(dsx / self.width()) * (fx1 - fx0)
            dfy = -(dsy / self.height()) * (fy1 - fy0)
            self.set_zoom_level(self._zoom_level, center=(self._zoom_center[0] + dfx, self._zoom_center[1] + dfy))
            return

        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self._snap_highlight = self.find_nearest_snap_point(fx, fy)
            self.update()
        else:
            if self._snap_highlight:
                self._snap_highlight = None
                self.update()

        if self._drag_ruler:
            if self._drag_ruler == 'h1': self._ruler1_h = fy
            elif self._drag_ruler == 'v1': self._ruler1_v = fx
            elif self._drag_ruler == 'h2': self._ruler2_h = fy
            elif self._drag_ruler == 'v2': self._ruler2_v = fx
            self.update()
            return

        if self._drag_roi and self._roi_start:
            self._roi_rect = (*self._roi_start, fx, fy)
            self.update()

    def mouseReleaseEvent(self, _event):
        self._is_panning = False
        self._drag_pip   = False
        self._drag_ruler = None
        if self._drag_roi:
            self._drag_roi = False
            self._mode     = "none"


# ══════════════════════════════════════════════════════════════════════════════
#  EXTERNAL PIP WIDGET (Minimapa fuera de la imagen principal)
# ══════════════════════════════════════════════════════════════════════════════

class ExternalPiPWidget(QWidget):
    positionClickedSignal = pyqtSignal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(220, 130)
        self.setMaximumHeight(160)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self._unzoomed_frame: Optional[np.ndarray] = None
        self._cx = 0.5
        self._cy = 0.5
        self._zoom_level = 1.0
        self._is_dragging = False
        self._locked = False

    def set_locked(self, locked: bool):
        self._locked = locked
        if locked:
            self.setCursor(Qt.CursorShape.WaitCursor)
        else:
            self.setCursor(Qt.CursorShape.CrossCursor)
        self.update()

    def set_full_unzoomed_frame(self, frame: np.ndarray):
        self._unzoomed_frame = frame
        self.update()

    def set_zoom_state(self, cx: float, cy: float, zoom_level: float):
        if not self._is_dragging:
            self._cx = max(0.0, min(1.0, cx))
            self._cy = max(0.0, min(1.0, cy))
        self._zoom_level = zoom_level
        self.update()

    def mousePressEvent(self, event):
        if self._locked:
            event.ignore()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging = True
            self._update_preview_pos(event.position())

    def mouseMoveEvent(self, event):
        if self._locked:
            event.ignore()
            return
        if self._is_dragging and (event.buttons() & Qt.MouseButton.LeftButton):
            self._update_preview_pos(event.position())

    def mouseReleaseEvent(self, event):
        if self._locked:
            event.ignore()
            return
        if event.button() == Qt.MouseButton.LeftButton and self._is_dragging:
            self._is_dragging = False
            self._update_preview_pos(event.position())
            self.set_locked(True)
            self.positionClickedSignal.emit(self._cx, self._cy)

    def _update_preview_pos(self, pos):
        W, H = self.width(), self.height()
        if W > 0 and H > 0:
            self._cx = max(0.0, min(1.0, pos.x() / W))
            self._cy = max(0.0, min(1.0, pos.y() / H))
            self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()

        p.fillRect(self.rect(), QColor(15, 23, 42))

        if self._unzoomed_frame is not None:
            try:
                img = self._unzoomed_frame
                ih, iw, ic = img.shape
                qimg = QImage(img.data, iw, ih, iw * ic, QImage.Format.Format_RGB888)
                p.drawImage(self.rect(), qimg)
            except Exception:
                pass

        p.setPen(QPen(QColor(245, 166, 35, 220), 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(0, 0, W - 1, H - 1)

        if self._zoom_level > 1.0:
            scale = float(self._zoom_level)
            bw = W / scale
            bh = H / scale
            bx = max(0.0, min(W - bw, self._cx * W - bw / 2.0))
            by = max(0.0, min(H - bh, self._cy * H - bh / 2.0))

            p.setPen(QPen(QColor(255, 68, 68, 255), 2))
            p.setBrush(QColor(255, 68, 68, 50))
            p.drawRect(QRectF(bx, by, bw, bh))

            mcx = bx + bw / 2.0
            mcy = by + bh / 2.0
            p.setPen(QPen(QColor(255, 220, 0, 240), 1))
            p.drawLine(QPointF(mcx - 5, mcy), QPointF(mcx + 5, mcy))
            p.drawLine(QPointF(mcx, mcy - 5), QPointF(mcx, mcy + 5))

        if self._locked:
            p.fillRect(self.rect(), QColor(0, 0, 0, 150))
            p.setPen(QPen(QColor(255, 220, 0, 240), 1))
            font = p.font()
            font.setPointSize(9)
            font.setBold(True)
            p.setFont(font)
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "⏳ Actualizando Canon...")


# ══════════════════════════════════════════════════════════════════════════════
#  CAMERA WINDOW  —  Fusión completa: UI camera_20260804 + Controles Canon EDSDK
# ══════════════════════════════════════════════════════════════════════════════

class CameraWindow(QMainWindow):
    # ── Señales Canon EDSDK ───────────────────────────────────────────────────
    startCameraSignal        = pyqtSignal()
    stopCameraSignal         = pyqtSignal()
    setZoomSignal            = pyqtSignal(int)
    setZoomCenterSignal      = pyqtSignal(float, float)
    setIsoSignal             = pyqtSignal(int)
    setTvSignal              = pyqtSignal(int)
    takePhotoSignal          = pyqtSignal(str)  # formato: "jpg", "png", "tiff", "bmp"
    liveParamsSignal         = pyqtSignal(str, int, int, int, float, float, float, int, bool)
    sendRoiSignal            = pyqtSignal(tuple)

    # ── Señales de Utilidades de Microfotónica ────────────────────────────────
    setReferenceSignal  = pyqtSignal(float, float)              # fx, fy
    roiToConfocalSignal = pyqtSignal(float, float, float, float) # range_x, range_y, px_x, px_y
    scaleChangedSignal  = pyqtSignal(float)
    directorySignal     = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cámara Canon EOS 500D — Suite de Microfotónica PyPrinting")
        self.setMinimumSize(1150, 720)
        self.resize(1350, 820)

        # ── Estado ────────────────────────────────────────────────────────────
        self._scale_set   = False
        self._ref_set     = False
        self._um_per_px   = PIXEL_SIZE_UM
        self._ref_frac    = (0.5, 0.5)
        self._ref_pos_um  = (50.0, 50.0)
        self._current_frame: Optional[np.ndarray] = None
        self._particles: list[tuple[float, float, float]] = []
        self._saved_measures: list[dict] = []
        self._trackpy_params  = dict(
            diameter=DEFAULT_TRACKPY_DIAMETER_PX,
            minmass=DEFAULT_TRACKPY_MINMASS,
            separation=DEFAULT_TRACKPY_SEPARATION_PX,
            threshold=0)
        self._measure_pts: list = []
        self._measure_mode = False
        self._is_camera_active = False

        # Estado del Zoom Óptico Canon (1x, 5x, 10x)
        self._canon_zoom_levels = [1, 5, 10]
        self._canon_zoom_idx = 0
        self._canon_cx = 0.5
        self._canon_cy = 0.5

        # Temporizadores de Antirrebote (Debounce 200 ms) para ISO y Tv
        self._debounce_iso_timer = QTimer(self)
        self._debounce_iso_timer.setSingleShot(True)
        self._debounce_iso_timer.setInterval(200)
        self._debounce_iso_timer.timeout.connect(self._apply_debounced_iso)

        self._debounce_tv_timer = QTimer(self)
        self._debounce_tv_timer.setSingleShot(True)
        self._debounce_tv_timer.setInterval(200)
        self._debounce_tv_timer.timeout.connect(self._apply_debounced_tv)

        # Temporizador de Antirrebote / Delay de Hardware (1800 ms) para Zoom Óptico Canon EVF
        self._debounce_zoom_timer = QTimer(self)
        self._debounce_zoom_timer.setSingleShot(True)
        self._debounce_zoom_timer.setInterval(1800)
        self._debounce_zoom_timer.timeout.connect(self._apply_debounced_canon_zoom)

        # ── Widget central ────────────────────────────────────────────────────
        central = QWidget()
        self.setCentralWidget(central)
        main_vlo = QVBoxLayout(central)
        main_vlo.setContentsMargins(4, 4, 4, 4)
        main_vlo.setSpacing(4)

        # ── Toolbar Superior ─────────────────────────────────────────────────
        tb = QWidget()
        tb_lo = QHBoxLayout(tb)
        tb_lo.setContentsMargins(2, 2, 2, 2)
        tb_lo.setSpacing(4)

        self._btn_live      = self._mkbtn("▶ Live", checkable=True, color="#4a9eff")
        self._btn_photo     = self._mkbtn("📸 Foto", color="#3ecf8e")
        self._btn_setref    = self._mkbtn("Set ref.", checkable=True, color="#4a9eff")
        self._btn_setscale  = self._mkbtn("Set scale", color="#f5a623")
        self._btn_rulers    = self._mkbtn("Reglas (0)", color="#f5a623")
        self._btn_confocal  = self._mkbtn("→ Confocal", color="#8b7cf8")
        self._btn_log       = self._mkbtn("Log EDSDK", color="#888")
        self._btn_diag      = self._mkbtn("🛡 Obturador", color="#ffaa00")
        self._btn_clear_all = self._mkbtn("Limpiar Todo", color="#e5534b")

        self._btn_live.clicked.connect(self._toggle_live)
        self._btn_photo.clicked.connect(self._on_take_photo_clicked)
        self._btn_setref.clicked.connect(self._start_set_ref)
        self._btn_setscale.clicked.connect(self._open_set_scale)
        self._btn_rulers.clicked.connect(self._cycle_rulers)
        self._btn_confocal.clicked.connect(self._send_roi_to_confocal)
        self._btn_log.clicked.connect(self._open_log_dialog)
        self._btn_diag.clicked.connect(self._force_shutter_cleanup)
        self._btn_clear_all.clicked.connect(self._global_clear_with_confirm)

        for w in (self._btn_live, self._btn_photo, self._btn_setref, self._btn_setscale,
                  self._btn_rulers, self._btn_confocal, self._btn_log, self._btn_diag, self._btn_clear_all):
            tb_lo.addWidget(w)
        tb_lo.addStretch()
        main_vlo.addWidget(tb, stretch=0)

        # ── Splitter Principal ───────────────────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 1. Panel Izquierdo: Controles Canon + Detección
        left_panel = QWidget()
        left_lo    = QVBoxLayout(left_panel)
        left_lo.setContentsMargins(4, 4, 4, 4)
        left_lo.setSpacing(6)

        # ── Sub-panel: Conexión Cámara ─────────────────────────────────────
        conn_box = QGroupBox("Cámara Canon EOS 500D")
        conn_lo  = QVBoxLayout(conn_box)

        self._btn_connect = QPushButton("▶ Iniciar Cámara Canon")
        self._btn_connect.setStyleSheet("font-weight: bold; color: #4a9eff; padding: 6px;")
        self._btn_connect.clicked.connect(self._toggle_camera)
        conn_lo.addWidget(self._btn_connect)

        form_cam = QFormLayout()
        self._lbl_mode = QLabel("Desconectado")
        self._lbl_mode.setStyleSheet("font-weight: bold; color: #3ecf8e; font-size: 10px;")
        form_cam.addRow("Modo:", self._lbl_mode)

        self._combo_iso = QComboBox(); self._combo_iso.setEnabled(False)
        self._combo_tv  = QComboBox(); self._combo_tv.setEnabled(False)

        self._combo_iso.currentIndexChanged.connect(self._on_iso_changed)
        self._combo_tv.currentIndexChanged.connect(self._on_tv_changed)

        form_cam.addRow("ISO:", self._combo_iso)
        form_cam.addRow("Tv:", self._combo_tv)

        self._combo_photo_format = QComboBox()
        self._combo_photo_format.addItems([
            "JPG (15.1 MP - 4752×3168)",
            "PNG (Sin Pérdida - 4752×3168)",
            "TIFF (Metrología - 4752×3168)",
            "BMP (Sin comprimir)"
        ])
        form_cam.addRow("Formato:", self._combo_photo_format)

        # Cambiar carpeta de guardado
        self._btn_dir = QPushButton("📁 Carpeta Guardado")
        self._btn_dir.clicked.connect(self._select_save_dir)
        self._lbl_dir = QLabel(f"📂 {os.path.abspath(DEFAULT_DATA_PATH)}")
        self._lbl_dir.setStyleSheet("font-family: monospace; font-size: 9px; color: #aaa;")
        self._lbl_dir.setWordWrap(True)
        conn_lo.addLayout(form_cam)
        conn_lo.addWidget(self._btn_dir)
        conn_lo.addWidget(self._lbl_dir)
        left_lo.addWidget(conn_box)

        # ── Sub-panel: Zoom Óptico Canon (EVF Hardware) ──────────────────────
        canon_zoom_box = QGroupBox("Zoom Óptico Canon (EVF Hardware)")
        cz_lo = QVBoxLayout(canon_zoom_box)

        # Botones de Nivel + / -
        row_z = QHBoxLayout()
        self._btn_zoom_out_canon = QPushButton("🔍 − Zoom")
        self._btn_zoom_out_canon.setToolTip("Disminuir Zoom Óptico Canon (10x -> 5x -> 1x) [Teclas - o _]")
        self._lbl_canon_zoom_val = QLabel("Zoom: 1x (Campo Completo)")
        self._lbl_canon_zoom_val.setStyleSheet("font-weight: bold; color: #4a9eff; font-size: 11px;")
        self._lbl_canon_zoom_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._btn_zoom_in_canon = QPushButton("🔍 + Zoom")
        self._btn_zoom_in_canon.setToolTip("Aumentar Zoom Óptico Canon (1x -> 5x -> 10x) [Teclas + o =]")

        self._btn_zoom_out_canon.clicked.connect(self._zoom_out_canon)
        self._btn_zoom_in_canon.clicked.connect(self._zoom_in_canon)

        row_z.addWidget(self._btn_zoom_out_canon)
        row_z.addWidget(self._lbl_canon_zoom_val, stretch=1)
        row_z.addWidget(self._btn_zoom_in_canon)
        cz_lo.addLayout(row_z)

        # Pad Direccional con Flechas
        pad_layout = QHBoxLayout()
        pad_grid = QGridLayout()
        self._btn_up = QPushButton("▲")
        self._btn_down = QPushButton("▼")
        self._btn_left = QPushButton("◄")
        self._btn_right = QPushButton("►")
        self._btn_center = QPushButton("🎯")
        self._btn_center.setToolTip("Recentrar recuadro de zoom al centro (50%, 50%)")

        for b in (self._btn_up, self._btn_down, self._btn_left, self._btn_right, self._btn_center):
            b.setFixedSize(30, 26)
            b.setStyleSheet("font-weight: bold; font-size: 11px;")

        self._btn_up.clicked.connect(lambda: self._pan_canon(0, -1))
        self._btn_down.clicked.connect(lambda: self._pan_canon(0, 1))
        self._btn_left.clicked.connect(lambda: self._pan_canon(-1, 0))
        self._btn_right.clicked.connect(lambda: self._pan_canon(1, 0))
        self._btn_center.clicked.connect(self._recenter_canon)

        pad_grid.addWidget(self._btn_up, 0, 1)
        pad_grid.addWidget(self._btn_left, 1, 0)
        pad_grid.addWidget(self._btn_center, 1, 1)
        pad_grid.addWidget(self._btn_right, 1, 2)
        pad_grid.addWidget(self._btn_down, 2, 1)

        pad_layout.addStretch()
        pad_layout.addLayout(pad_grid)
        pad_layout.addStretch()
        cz_lo.addLayout(pad_layout)

        # External PiP (Minimapa fuera de la imagen principal)
        self._ext_pip = ExternalPiPWidget(self)
        self._ext_pip.positionClickedSignal.connect(self._on_ext_pip_click)
        cz_lo.addWidget(self._ext_pip)

        left_lo.addWidget(canon_zoom_box)

        # ── Sub-panel: Ajustes de Imagen en Vivo ─────────────────────────
        live_box = QGroupBox("Ajustes de Imagen en Vivo")
        live_lo  = QVBoxLayout(live_box)

        self._combo_color_mode = QComboBox()
        self._combo_color_mode.addItems(["Color RGB", "Grises (Transmisión)"])
        self._combo_color_mode.currentIndexChanged.connect(self._on_color_mode_changed)

        self._stack_live = QStackedWidget()

        # Pág 0: Modo Grises / Transmisión
        page_gray = QWidget()
        pg_lo = QFormLayout(page_gray)
        pg_lo.setContentsMargins(0, 0, 0, 0)
        self._slider_live_cmin = QSlider(Qt.Orientation.Horizontal)
        self._slider_live_cmin.setRange(0, 255); self._slider_live_cmin.setValue(0)
        self._slider_live_cmax = QSlider(Qt.Orientation.Horizontal)
        self._slider_live_cmax.setRange(0, 255); self._slider_live_cmax.setValue(255)
        self._combo_live_lut   = QComboBox()
        self._combo_live_lut.addItems([
            "Gris (Original)", "Thermal (Confocal/Láser)", "Viridis", "Plasma", "Inferno", "Jet / Arcoíris"])
        pg_lo.addRow("Intensidad Mín.:", self._slider_live_cmin)
        pg_lo.addRow("Intensidad Máx.:", self._slider_live_cmax)
        pg_lo.addRow("Paleta LUT:", self._combo_live_lut)
        self._stack_live.addWidget(page_gray)

        # Pág 1: Modo Color RGB
        page_rgb = QWidget()
        pr_lo = QFormLayout(page_rgb)
        pr_lo.setContentsMargins(0, 0, 0, 0)
        self._slider_live_r = QSlider(Qt.Orientation.Horizontal)
        self._slider_live_r.setRange(5, 20); self._slider_live_r.setValue(10)
        self._slider_live_g = QSlider(Qt.Orientation.Horizontal)
        self._slider_live_g.setRange(5, 20); self._slider_live_g.setValue(10)
        self._slider_live_b = QSlider(Qt.Orientation.Horizontal)
        self._slider_live_b.setRange(5, 20); self._slider_live_b.setValue(10)
        btn_reset_rgb = QPushButton("Restablecer Blancos")
        btn_reset_rgb.clicked.connect(self._reset_live_rgb)
        pr_lo.addRow("Ganancia R:", self._slider_live_r)
        pr_lo.addRow("Ganancia G:", self._slider_live_g)
        pr_lo.addRow("Ganancia B:", self._slider_live_b)
        pr_lo.addRow(btn_reset_rgb)
        self._stack_live.addWidget(page_rgb)

        self._stack_live.setCurrentIndex(1)  # Iniciar en RGB

        for s in (self._slider_live_cmin, self._slider_live_cmax,
                  self._slider_live_r, self._slider_live_g, self._slider_live_b):
            s.valueChanged.connect(self._sync_live_adjustments)
        self._combo_live_lut.currentIndexChanged.connect(self._sync_live_adjustments)

        # ── Sub-panel: Supresión de Ruido de Fondo ───────────────────────
        noise_box = QWidget()
        noise_lo = QFormLayout(noise_box)
        noise_lo.setContentsMargins(0, 4, 0, 0)

        self._chk_denoise = QCheckBox("Filtro Mediano (3x3)")
        self._slider_noise_floor = QSlider(Qt.Orientation.Horizontal)
        self._slider_noise_floor.setRange(0, 50)
        self._slider_noise_floor.setValue(0)
        self._lbl_noise_floor_val = QLabel("0")
        self._lbl_noise_floor_val.setStyleSheet("font-family: monospace; font-size: 10px; color: #f5a623;")

        self._chk_denoise.toggled.connect(self._sync_live_adjustments)
        self._slider_noise_floor.valueChanged.connect(self._on_noise_floor_changed)

        h_noise = QHBoxLayout()
        h_noise.addWidget(self._slider_noise_floor)
        h_noise.addWidget(self._lbl_noise_floor_val)

        noise_lo.addRow(self._chk_denoise)
        noise_lo.addRow("Umbral Fondo:", h_noise)

        live_lo.addWidget(self._combo_color_mode)
        live_lo.addWidget(self._stack_live)
        live_lo.addWidget(noise_box)
        left_lo.addWidget(live_box)
        left_lo.addStretch()

        # 2. Visor Central: PyQtGraph + OverlayWidget
        visor_container = QWidget()
        visor_lo        = QVBoxLayout(visor_container)
        visor_lo.setContentsMargins(0, 0, 0, 0)
        visor_lo.setSpacing(0)
        visor_container.setMinimumWidth(400)

        self._view = pg.GraphicsLayoutWidget()
        self._view.setBackground('#0b0f19')  # Tema oscuro continuo, elimina bordes/márgenes de caja
        self._view.ci.layout.setContentsMargins(0, 0, 0, 0)
        self._view.ci.layout.setSpacing(0)

        self._vb = self._view.addViewBox(lockAspect=True)
        self._vb.invertY(True)
        self._vb.setMenuEnabled(False)
        self._vb.setMouseEnabled(x=False, y=False)
        self._img_item = pg.ImageItem()
        self._img_item.setOpts(axisOrder='row-major', smooth=True)
        self._vb.addItem(self._img_item)

        # Reparentar OverlayWidget al viewport interno de QGraphicsView para alineación limpia
        self._overlay = OverlayWidget(self._view.viewport())
        self._overlay.bind_views(self._view, self._img_item)
        self._overlay.setGeometry(self._view.viewport().rect())
        self._view.resizeEvent = self._on_view_resize
        self._overlay.pointClickedSignal.connect(self._on_overlay_click)
        self._overlay.zoomChangedSignal.connect(self._on_zoom_changed_overlay)
        visor_lo.addWidget(self._view)

        # 3. Panel Derecho: Mediciones + Detección & ROI
        right_panel = QWidget()
        right_lo    = QVBoxLayout(right_panel)
        right_lo.setContentsMargins(4, 4, 4, 4)
        right_lo.setSpacing(6)

        # Sub-panel: Mediciones
        meas_box = QGroupBox("Mediciones")
        meas_lo  = QVBoxLayout(meas_box)

        self._btn_medir     = self._mkbtn("Medir", checkable=True, color="#e5534b")
        self._btn_save_meas = self._mkbtn("Guardar Medida", color="#3ecf8e")
        self._btn_exp_meas  = self._mkbtn("Exportar (.txt)", color="#4a9eff")
        self._btn_clr_meas  = self._mkbtn("Limpiar Lista")

        self._btn_medir.clicked.connect(self._toggle_measure)
        self._btn_save_meas.clicked.connect(self._save_current_measurement)
        self._btn_exp_meas.clicked.connect(self._export_measurements_txt)
        self._btn_clr_meas.clicked.connect(self._clear_measurements_list)

        btn_row_r = QHBoxLayout()
        btn_row_r.addWidget(self._btn_medir)
        btn_row_r.addWidget(self._btn_save_meas)
        meas_lo.addLayout(btn_row_r)

        self._table_measures = QTableWidget(0, 4)
        self._table_measures.setHorizontalHeaderLabels(["#", "Dist (µm)", "Δx/Δy (px)", "Ángulo"])
        self._table_measures.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table_measures.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table_measures.setMaximumHeight(130)
        meas_lo.addWidget(self._table_measures)

        btn_row_r2 = QHBoxLayout()
        btn_row_r2.addWidget(self._btn_exp_meas)
        btn_row_r2.addWidget(self._btn_clr_meas)
        meas_lo.addLayout(btn_row_r2)
        right_lo.addWidget(meas_box)

        # Sub-panel: Detección & ROI (trasladado a la columna derecha)
        detect_box = QGroupBox("Detección & ROI")
        detect_lo  = QVBoxLayout(detect_box)

        self._btn_roi    = self._mkbtn("ROI detect", checkable=True, color="#8b7cf8")
        self._btn_detect = self._mkbtn("Detectar", color="#3ecf8e")
        self._btn_exp_part    = self._mkbtn("Exportar Partículas (.txt)", color="#3ecf8e")
        self._btn_clear_particles = self._mkbtn("Limpiar Partículas")

        self._btn_roi.clicked.connect(self._toggle_roi_mode)
        self._btn_detect.clicked.connect(self._open_trackpy_dialog)
        self._btn_exp_part.clicked.connect(self._export_particles_txt)
        self._btn_clear_particles.clicked.connect(self._clear_particles)

        btn_row_d = QHBoxLayout()
        btn_row_d.addWidget(self._btn_roi)
        btn_row_d.addWidget(self._btn_detect)
        detect_lo.addLayout(btn_row_d)

        self._table_particles = QTableWidget(0, 4)
        self._table_particles.setHorizontalHeaderLabels(["#", "x (µm)", "y (µm)", "Int."])
        self._table_particles.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table_particles.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table_particles.setMaximumHeight(130)
        detect_lo.addWidget(self._table_particles)

        btn_row_d2 = QHBoxLayout()
        btn_row_d2.addWidget(self._btn_exp_part)
        btn_row_d2.addWidget(self._btn_clear_particles)
        detect_lo.addLayout(btn_row_d2)
        right_lo.addWidget(detect_box)
        right_lo.addStretch()

        # Delimitación de anchos equilibrada para ambas columnas laterales
        left_panel.setMinimumWidth(280)
        left_panel.setMaximumWidth(340)
        right_panel.setMinimumWidth(280)
        right_panel.setMaximumWidth(340)

        splitter.addWidget(left_panel)
        splitter.addWidget(visor_container)
        splitter.addWidget(right_panel)
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        splitter.setCollapsible(2, False)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        main_vlo.addWidget(splitter, stretch=1)

        # ── Barra de Estado ───────────────────────────────────────────────────
        status_bar = QHBoxLayout()
        self._lbl_scale  = QLabel("Escala: no calibrada")
        self._lbl_scale.setStyleSheet("color: #e5534b; font-family: monospace; font-size: 10px;")
        self._lbl_status = QLabel("Inicializando controlador Canon EDSDK...")
        self._lbl_status.setStyleSheet("font-family: monospace; font-size: 10px; color: #aaa;")
        self._lbl_result = QLabel("")
        self._lbl_result.setStyleSheet("font-family: monospace; font-size: 10px; color: #aaa;")
        status_bar.addWidget(self._lbl_scale)
        status_bar.addWidget(self._lbl_status, 1)
        status_bar.addWidget(self._lbl_result)
        main_vlo.addLayout(status_bar, stretch=0)

        # ── Log EDSDK (flotante) ──────────────────────────────────────────────
        self._log_dialog = EDSDKLogDialog(self)

        self._update_guards()

    # ── Helpers UI ────────────────────────────────────────────────────────────

    def _mkbtn(self, text, checkable=False, color=None) -> QPushButton:
        b = QPushButton(text)
        b.setCheckable(checkable)
        if color:
            b.setStyleSheet(f"QPushButton {{ color: {color}; }}"
                            f"QPushButton:checked {{ background-color: {color}; color: #111; }}")
        return b

    def _fit_camera_view_lateral(self):
        if hasattr(self, '_img_item') and self._img_item is not None and hasattr(self, '_overlay'):
            W, H = self._overlay.get_img_dims()
            if W > 0 and H > 0:
                if self._overlay._zoom_level == 1.0:
                    self._vb.autoRange(padding=0)
                else:
                    fx0, fy0, fx1, fy1 = self._overlay.viewport_bounds()
                    self._vb.setXRange(fx0 * W, fx1 * W, padding=0)
                    self._vb.setYRange(fy0 * H, fy1 * H, padding=0)

    def _on_view_resize(self, event):
        if hasattr(self, '_overlay') and hasattr(self, '_view'):
            self._overlay.setGeometry(self._view.viewport().rect())
        pg.GraphicsLayoutWidget.resizeEvent(self._view, event)
        self._fit_camera_view_lateral()

    def _on_zoom_changed_overlay(self, fx0: float, fy0: float, fx1: float, fy1: float):
        W, H = self._overlay.get_img_dims()
        if self._overlay._zoom_level == 1.0:
            self._vb.autoRange(padding=0)
        else:
            self._vb.setXRange(fx0 * W, fx1 * W, padding=0)
            self._vb.setYRange(fy0 * H, fy1 * H, padding=0)
        cx, cy = self._overlay._zoom_center
        if self._is_camera_active:
            self.setZoomCenterSignal.emit(cx, cy)

    def _update_guards(self):
        scale_needed = self._scale_set and self._ref_set
        self._btn_confocal.setEnabled(scale_needed)

    # ── Cámara Canon: Conexión / Desconexión ──────────────────────────────────

    def _toggle_camera(self):
        if not self._is_camera_active:
            self._combo_iso.setEnabled(False)
            self._combo_tv.setEnabled(False)
            self._btn_connect.setText("⏹ Desconectar Cámara Canon")
            self._btn_connect.setStyleSheet(
                "font-weight: bold; color: #ff6666; background-color: #3a1c1c; padding: 6px; border: 1px solid #ff4444;")
            self._is_camera_active = True
            self.startCameraSignal.emit()
        else:
            self.stopCameraSignal.emit()
            self._combo_iso.setEnabled(False)
            self._combo_tv.setEnabled(False)
            self._lbl_mode.setText("Desconectado")
            self._btn_connect.setText("▶ Iniciar Cámara Canon")
            self._btn_connect.setStyleSheet("font-weight: bold; color: #4a9eff; padding: 6px;")
            self._is_camera_active = False

    def _on_take_photo_clicked(self):
        text = self._combo_photo_format.currentText()
        if "PNG" in text:  ext = "png"
        elif "TIFF" in text: ext = "tiff"
        elif "BMP" in text: ext = "bmp"
        else: ext = "jpg"
        self.takePhotoSignal.emit(ext)

    def _select_save_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta de guardado", str(DEFAULT_DATA_PATH))
        if d:
            self._lbl_dir.setText(f"📂 {d}")
            self.directorySignal.emit(d)

    def _force_shutter_cleanup(self):
        """Diagnóstico & Cierre Forzado de Obturador — propaga la acción al worker vía señal."""
        self._append_log("🛡️ Solicitud de cierre forzado de obturador — desconectando...")
        self.stopCameraSignal.emit()
        self._combo_iso.setEnabled(False)
        self._combo_tv.setEnabled(False)
        self._lbl_mode.setText("Desconectado")
        self._btn_connect.setText("▶ Iniciar Cámara Canon")
        self._btn_connect.setStyleSheet("font-weight: bold; color: #4a9eff; padding: 6px;")
        self._is_camera_active = False
        QMessageBox.information(self, "Diagnóstico", "Obturador cerrado y sesión de cámara restablecida.")

    def keyPressEvent(self, event):
        k = event.key()
        if k in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self._zoom_in_canon()
            event.accept()
            return
        elif k in (Qt.Key.Key_Minus, Qt.Key.Key_Underscore):
            self._zoom_out_canon()
            event.accept()
            return
        elif k == Qt.Key.Key_Left:
            self._pan_canon(-1, 0)
            event.accept()
            return
        elif k == Qt.Key.Key_Right:
            self._pan_canon(1, 0)
            event.accept()
            return
        elif k == Qt.Key.Key_Up:
            self._pan_canon(0, -1)
            event.accept()
            return
        elif k == Qt.Key.Key_Down:
            self._pan_canon(0, 1)
            event.accept()
            return
        super().keyPressEvent(event)

    # ── Controles de Zoom Hardware Canon (EVF 1x, 5x, 10x) ───────────────────

    def _zoom_in_canon(self):
        if self._canon_zoom_idx < len(self._canon_zoom_levels) - 1:
            self._canon_zoom_idx += 1
            self._sync_canon_zoom_hardware()

    def _zoom_out_canon(self):
        if self._canon_zoom_idx > 0:
            self._canon_zoom_idx -= 1
            self._sync_canon_zoom_hardware()

    def _pan_canon(self, dx: int, dy: int):
        step = 0.05
        self._canon_cx = max(0.0, min(1.0, self._canon_cx + dx * step))
        self._canon_cy = max(0.0, min(1.0, self._canon_cy + dy * step))
        self._sync_canon_zoom_hardware()

    def _recenter_canon(self):
        self._canon_cx = 0.5
        self._canon_cy = 0.5
        self._sync_canon_zoom_hardware()

    def _on_ext_pip_click(self, cx: float, cy: float):
        self._canon_cx = cx
        self._canon_cy = cy
        self._sync_canon_zoom_hardware()

    def _set_zoom_controls_enabled(self, enabled: bool):
        btns = (getattr(self, '_btn_up', None), getattr(self, '_btn_down', None),
                getattr(self, '_btn_left', None), getattr(self, '_btn_right', None),
                getattr(self, '_btn_center', None), getattr(self, '_btn_zoom_in_canon', None),
                getattr(self, '_btn_zoom_out_canon', None))
        for b in btns:
            if b is not None:
                b.setEnabled(enabled)

    def _sync_canon_zoom_hardware(self):
        val = self._canon_zoom_levels[self._canon_zoom_idx]
        txt = "Zoom: 1x (Campo Completo)" if val == 1 else (f"Zoom: {val}x (Hardware Canon)" if val < 10 else f"Zoom: {val}x (Máximo Enfoque)")
        if hasattr(self, '_lbl_canon_zoom_val'):
            self._lbl_canon_zoom_val.setText(txt)

        if hasattr(self, '_ext_pip'):
            self._ext_pip.set_zoom_state(self._canon_cx, self._canon_cy, float(val))

        if self._is_camera_active:
            if hasattr(self, '_ext_pip'):
                self._ext_pip.set_locked(True)
            self._set_zoom_controls_enabled(False)
            if hasattr(self, '_lbl_status'):
                self._lbl_status.setText("⏳ Aplicando Zoom Canon en hardware... (Bloqueado ~2s)")
            self._debounce_zoom_timer.start()

    def _apply_debounced_canon_zoom(self):
        val = self._canon_zoom_levels[self._canon_zoom_idx]
        if self._is_camera_active:
            self.setZoomSignal.emit(val)
            self.setZoomCenterSignal.emit(self._canon_cx, self._canon_cy)
            if hasattr(self, '_lbl_status'):
                self._lbl_status.setText("Transmisión en Vivo Canon activa.")
        if hasattr(self, '_ext_pip'):
            self._ext_pip.set_locked(False)
        self._set_zoom_controls_enabled(True)

    def _open_log_dialog(self):
        self._log_dialog.show()
        self._log_dialog.raise_()

    # ── Ajustes de Imagen en Vivo ─────────────────────────────────────────────

    def _on_color_mode_changed(self, idx: int):
        # idx 0: Color RGB, idx 1: Grises (Transmisión)
        self._stack_live.setCurrentIndex(0 if idx == 1 else 1)
        self._sync_live_adjustments()

    def _on_noise_floor_changed(self, val: int):
        self._lbl_noise_floor_val.setText(str(val))
        self._sync_live_adjustments()

    def _reset_live_rgb(self):
        for s in (self._slider_live_r, self._slider_live_g, self._slider_live_b):
            s.blockSignals(True)
            s.setValue(10)
            s.blockSignals(False)
        self._sync_live_adjustments()

    def _sync_live_adjustments(self):
        mode  = self._combo_color_mode.currentText()
        cmin  = self._slider_live_cmin.value()
        cmax  = self._slider_live_cmax.value()
        lut   = self._combo_live_lut.currentIndex()
        r_g   = self._slider_live_r.value() / 10.0
        g_g   = self._slider_live_g.value() / 10.0
        b_g   = self._slider_live_b.value() / 10.0
        noise_floor = self._slider_noise_floor.value() if hasattr(self, '_slider_noise_floor') else 0
        denoise = self._chk_denoise.isChecked() if hasattr(self, '_chk_denoise') else False
        self.liveParamsSignal.emit(mode, cmin, cmax, lut, r_g, g_g, b_g, noise_floor, denoise)

    # ── ISO / Tv (con Debounce) ───────────────────────────────────────────────

    def _on_iso_changed(self, idx: int):
        val = self._combo_iso.itemData(idx)
        if val is not None:
            self._pending_iso = val
            self._debounce_iso_timer.start()

    def _apply_debounced_iso(self):
        if hasattr(self, '_pending_iso') and self._pending_iso is not None:
            self.setIsoSignal.emit(self._pending_iso)

    def _on_tv_changed(self, idx: int):
        val = self._combo_tv.itemData(idx)
        if val is not None:
            self._pending_tv = val
            self._debounce_tv_timer.start()

    def _apply_debounced_tv(self):
        if hasattr(self, '_pending_tv') and self._pending_tv is not None:
            self.setTvSignal.emit(self._pending_tv)

    # ── Stream y Foto (Live) ─────────────────────────────────────────────────

    def _toggle_live(self, checked: bool):
        self._btn_live.setText("⏹ Stop" if checked else "▶ Live")
        if checked: self.startCameraSignal.emit()
        else: self.stopCameraSignal.emit()

    # ── Slots del Worker ──────────────────────────────────────────────────────

    @pyqtSlot(np.ndarray)
    def _update_frame(self, frame: np.ndarray):
        self._current_frame = frame
        self._img_item.setImage(frame.transpose(1, 0, 2))
        if not hasattr(self, '_range_initialized'):
            self._fit_camera_view_lateral()
            self._range_initialized = True

    @pyqtSlot(np.ndarray)
    def _update_full_frame(self, frame: np.ndarray):
        if hasattr(self, '_overlay'):
            self._overlay.set_full_unzoomed_frame(frame)
        if hasattr(self, '_ext_pip'):
            self._ext_pip.set_full_unzoomed_frame(frame)

    # Alias público para compatibilidad con código antiguo
    @pyqtSlot(np.ndarray)
    def update_frame(self, frame: np.ndarray):
        self._update_frame(frame)

    @pyqtSlot(str)
    def _update_status(self, msg: str):
        self._lbl_status.setText(msg)

    @pyqtSlot(str)
    def _append_log(self, msg: str):
        self._log_dialog.append_log(msg)

    @pyqtSlot(bool)
    def _on_connected(self, connected: bool):
        self._is_camera_active = True
        self._btn_connect.setText("⏹ Desconectar Cámara Canon")
        self._btn_connect.setStyleSheet(
            "font-weight: bold; color: #ff6666; background-color: #3a1c1c; padding: 6px; border: 1px solid #ff4444;")

    @pyqtSlot(str)
    def _on_photo_saved(self, saved_path: str):
        msg = f"📸 ¡Foto de 15.1 MP guardada exitosamente!\n\nRuta:\n{saved_path}"
        QMessageBox.information(self, "Foto Guardada", msg)

    @pyqtSlot(list, list, int, int, int)
    def _populate_properties(self, iso_vals: list, tv_vals: list,
                             ae_mode: int, curr_iso: int = 0, curr_tv: int = 0):
        mode_str = AE_MODE_MAP.get(ae_mode, f"Modo 0x{ae_mode:02X}")
        self._lbl_mode.setText(mode_str)

        self._combo_iso.blockSignals(True)
        self._combo_iso.clear()
        target_iso_idx = 0
        for idx, v in enumerate(iso_vals):
            lbl = ISO_MAP.get(v, f"0x{v:02X}")
            self._combo_iso.addItem(lbl, userData=v)
            if curr_iso != 0 and v == curr_iso:
                target_iso_idx = idx
        if curr_iso != 0:
            self._combo_iso.setCurrentIndex(target_iso_idx)
        self._combo_iso.blockSignals(False)
        self._combo_iso.setEnabled(True)

        self._combo_tv.blockSignals(True)
        self._combo_tv.clear()
        target_tv_idx = 0
        for idx, v in enumerate(tv_vals):
            lbl = TV_MAP.get(v, f"0x{v:02X}")
            self._combo_tv.addItem(lbl, userData=v)
            if curr_tv != 0 and v == curr_tv:
                target_tv_idx = idx
        if curr_tv != 0:
            self._combo_tv.setCurrentIndex(target_tv_idx)
        self._combo_tv.blockSignals(False)
        self._combo_tv.setEnabled(True)

    @pyqtSlot(list)
    def set_ref_pos_um(self, pos: list):
        self._ref_pos_um = (pos[0], pos[1])

    # ── Set Reference y Reglas ─────────────────────────────────────────────────

    def _start_set_ref(self, checked: bool):
        if checked:
            self._overlay.set_mode("ref")
            self._btn_setref.setText("Click en haz/partícula...")
        else:
            self._overlay.set_mode("none")
            self._btn_setref.setText("Set ref.")

    def _cycle_rulers(self):
        st = self._overlay.cycle_rulers()
        names = ["Reglas (0)", "Reglas (1 Par)", "Reglas (2 Pares)"]
        self._btn_rulers.setText(names[st])

    # ── Manejo de Clics en la Imagen ──────────────────────────────────────────

    def _on_overlay_click(self, fx: float, fy: float):
        mode = self._overlay._mode

        if mode == "ref":
            snap = self._overlay.find_nearest_snap_point(fx, fy)
            if snap: fx, fy = snap
            self._ref_frac = (fx, fy)
            self._ref_set  = True
            self._overlay.set_ref(fx, fy)
            self._overlay.set_mode("none")
            self._btn_setref.setChecked(False)
            self._btn_setref.setText("Set ref.")
            self.setReferenceSignal.emit(fx, fy)
            self._update_guards()
            return

        if self._measure_mode:
            self._measure_pts.append((fx, fy))
            if len(self._measure_pts) > 2:
                self._measure_pts = self._measure_pts[-2:]
            self._overlay.set_measure_points(self._measure_pts)
            if len(self._measure_pts) == 2:
                W, H = self._overlay.get_img_dims()
                (fx1, fy1), (fx2, fy2) = self._measure_pts
                dx_px = (fx2 - fx1) * W
                dy_px = (fy2 - fy1) * H
                dist_um = math.hypot(dx_px, dy_px) * self._um_per_px
                angle   = math.degrees(math.atan2(dy_px, dx_px))
                self._lbl_result.setText(
                    f"Medida: {dist_um:.3f} µm (Δx={dx_px:.1f}px, Δy={dy_px:.1f}px) | θ={angle:.1f}°")

    # ── Guardar y Exportar Mediciones ─────────────────────────────────────────

    def _toggle_measure(self, checked: bool):
        self._measure_mode = checked
        if checked:
            self._overlay.set_mode("measure")
        else:
            self._overlay.set_mode("none")

    def _save_current_measurement(self):
        pts = self._overlay._measure_pts
        if len(pts) != 2:
            QMessageBox.warning(self, "Medición", "Primero colocá 2 puntos sobre la imagen.")
            return
        W, H = self._overlay.get_img_dims()
        (fx1, fy1), (fx2, fy2) = pts
        dx_px = (fx2 - fx1) * W
        dy_px = (fy2 - fy1) * H
        dist_um = math.hypot(dx_px, dy_px) * self._um_per_px
        angle   = math.degrees(math.atan2(dy_px, dx_px))

        m = dict(index=len(self._saved_measures)+1, dist=dist_um, dx_px=dx_px,
                 dy_px=dy_px, angle=angle, p1=(fx1, fy1), p2=(fx2, fy2))
        self._saved_measures.append(m)

        row = self._table_measures.rowCount()
        self._table_measures.insertRow(row)
        self._table_measures.setItem(row, 0, QTableWidgetItem(str(m["index"])))
        self._table_measures.setItem(row, 1, QTableWidgetItem(f"{dist_um:.3f}"))
        self._table_measures.setItem(row, 2, QTableWidgetItem(f"{dx_px:.1f} / {dy_px:.1f}"))
        self._table_measures.setItem(row, 3, QTableWidgetItem(f"{angle:.1f}°"))

    def _export_measurements_txt(self):
        if not self._saved_measures:
            QMessageBox.warning(self, "Exportar", "La lista de mediciones está vacía.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Guardar mediciones", str(DEFAULT_DATA_PATH / "mediciones.txt"),
            "Archivos Texto (*.txt)")
        if not path: return
        with open(path, "w", encoding="utf-8") as f:
            f.write("# Mediciones de Cámara - PyPrinting\n")
            f.write(f"# Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# Escala: {self._um_per_px:.5f} µm/px\n\n")
            f.write("Index\tDist_um\tDeltaX_px\tDeltaY_px\tAngulo_deg\n")
            for m in self._saved_measures:
                f.write(f"{m['index']}\t{m['dist']:.4f}\t{m['dx_px']:.1f}\t{m['dy_px']:.1f}\t{m['angle']:.2f}\n")
        QMessageBox.information(self, "Exportar", f"Mediciones guardadas en:\n{path}")

    def _clear_measurements_list(self):
        self._saved_measures = []
        self._table_measures.setRowCount(0)
        self._overlay.clear_measure()
        self._lbl_result.setText("— Lista de mediciones vaciada —")

    # ── Detección y Exportación de Partículas ──────────────────────────────────

    def _export_particles_txt(self):
        if not self._particles:
            QMessageBox.warning(self, "Exportar", "No hay partículas detectadas para exportar.")
            return
        W, H = self._overlay.get_img_dims()
        path, _ = QFileDialog.getSaveFileName(
            self, "Guardar partículas detectadas",
            str(DEFAULT_DATA_PATH / "particulas_detectadas.txt"),
            "Archivos Texto (*.txt)")
        if not path: return
        with open(path, "w", encoding="utf-8") as f:
            f.write("# Partículas Detectadas - PyPrinting\n")
            f.write(f"# Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# Escala: {self._um_per_px:.5f} µm/px\n\n")
            f.write("Index\tX_frac\tY_frac\tX_um\tY_um\tIntensidad\n")
            for i, (fx, fy, mass) in enumerate(self._particles):
                x_um = fx * W * self._um_per_px
                y_um = fy * H * self._um_per_px
                f.write(f"{i+1}\t{fx:.5f}\t{fy:.5f}\t{x_um:.3f}\t{y_um:.3f}\t{mass:.1f}\n")
        QMessageBox.information(self, "Exportar", f"Lista de partículas exportada en:\n{path}")

    def _clear_particles(self):
        self._particles = []
        self._table_particles.setRowCount(0)
        self._overlay.clear_particles()

    def _toggle_roi_mode(self, checked: bool):
        if checked:
            self._overlay.set_mode("roi")
            self._overlay.clear_roi()
        else:
            self._overlay.set_mode("none")

    def _open_trackpy_dialog(self):
        if self._current_frame is None:
            QMessageBox.warning(self, "Detectar", "Esperá a tener un frame activo.")
            return
        roi = self._overlay.roi_fractions()
        dlg = TrackpyDialog(self._current_frame.copy(), roi_frac=roi,
                            um_per_px=self._um_per_px if self._scale_set else None, parent=self)
        dlg.paramsAccepted.connect(self._on_trackpy_params)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._run_detection()

    def _on_trackpy_params(self, params: dict):
        self._trackpy_params = params

    def _run_detection(self):
        if not _TRACKPY_AVAILABLE or self._current_frame is None: return
        import warnings
        frame = self._current_frame
        roi   = self._overlay.roi_fractions()
        H, W  = frame.shape[:2]

        if roi:
            x0, y0, x1, y1 = roi
            ix0, ix1 = int(round(x0*W)), int(round(x1*W))
            iy0, iy1 = int(round(y0*H)), int(round(y1*H))
            crop = frame[iy0:iy1, ix0:ix1]
            offset = (ix0, iy0)
        else:
            crop = frame
            offset = (0, 0)

        gray = np.mean(crop, axis=2) if crop.ndim == 3 else crop.astype(float)
        p    = self._trackpy_params.copy()
        d    = p.pop("diameter"); d = d if d % 2 == 1 else d + 1

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                df = tp.locate(gray, diameter=d, separation=p.get("separation", 8),
                               threshold=p.get("threshold", None))
        except Exception as e:
            QMessageBox.warning(self, "Detección fallida", str(e))
            return

        pts = []
        self._table_particles.setRowCount(len(df))
        for i, row in df.iterrows():
            gx = (row["x"] + offset[0]) / W
            gy = (row["y"] + offset[1]) / H
            pts.append((gx, gy, row.get("mass", 0)))
            x_um = gx * W * self._um_per_px
            y_um = gy * H * self._um_per_px
            self._table_particles.setItem(i, 0, QTableWidgetItem(str(i+1)))
            self._table_particles.setItem(i, 1, QTableWidgetItem(f"{x_um:.2f}"))
            self._table_particles.setItem(i, 2, QTableWidgetItem(f"{y_um:.2f}"))
            self._table_particles.setItem(i, 3, QTableWidgetItem(f"{row.get('mass',0):.1f}"))

        self._particles = pts
        self._overlay.set_particles(pts)

    # ── Limpiar Todo con Confirmación ─────────────────────────────────────────

    def _global_clear_with_confirm(self):
        reply = QMessageBox.question(
            self, "Confirmar Limpieza Global",
            "¿Estás seguro de que querés limpiar todas las partículas, la referencia, las reglas y las mediciones?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            self._clear_particles()
            self._clear_measurements_list()
            self._overlay.clear_ref()
            self._overlay.clear_roi()
            self._ref_set = False
            self._update_guards()

    # ── ROI → Confocal ────────────────────────────────────────────────────────

    def _send_roi_to_confocal(self):
        if not self._ref_set:
            QMessageBox.warning(self, "ROI → Confocal", "Primero fijá la referencia con Set ref.")
            return
        roi = self._overlay.roi_fractions()
        if not roi:
            QMessageBox.warning(self, "ROI → Confocal", "Dibujá un ROI de escaneo primero.")
            return

        fx0, fy0, fx1, fy1 = roi
        ref_fx, ref_fy    = self._ref_frac
        xref, yref        = self._ref_pos_um

        W, H = self._overlay.get_img_dims()
        roi_center_fx = (fx0 + fx1) / 2.0
        roi_center_fy = (fy0 + fy1) / 2.0

        dy_cam_um = (roi_center_fx - ref_fx) * W * self._um_per_px
        dx_cam_um = (roi_center_fy - ref_fy) * H * self._um_per_px

        target_x_stage = xref + dx_cam_um
        target_y_stage = yref + dy_cam_um

        range_y_um = abs(fx1 - fx0) * W * self._um_per_px
        range_x_um = abs(fy1 - fy0) * H * self._um_per_px

        x_min = target_x_stage - range_x_um / 2.0
        x_max = target_x_stage + range_x_um / 2.0
        y_min = target_y_stage - range_y_um / 2.0
        y_max = target_y_stage + range_y_um / 2.0

        ok_x = (0.0 <= x_min) and (x_max <= PI_STAGE_RANGE_UM)
        ok_y = (0.0 <= y_min) and (y_max <= PI_STAGE_RANGE_UM)

        if not (ok_x and ok_y):
            msg = (f"⚠ El escaneo confocal excede los límites físicos de la platina (0.0 – {PI_STAGE_RANGE_UM:.0f} µm).\n\n"
                   f"Centro Objetivo Platina: X={target_x_stage:.2f} µm, Y={target_y_stage:.2f} µm\n"
                   f"Rango X: [{x_min:.2f}, {x_max:.2f}] µm {'(OK)' if ok_x else '(EXCEDIDO)'}\n"
                   f"Rango Y: [{y_min:.2f}, {y_max:.2f}] µm {'(OK)' if ok_y else '(EXCEDIDO)'}")
            QMessageBox.warning(self, "ROI → Confocal (Límites Excedidos)", msg)
            return

        res_nm, ok = QInputDialog.getDouble(
            self, "Resolución Confocal",
            f"El escaneo en la posición ({target_x_stage:.2f}, {target_y_stage:.2f}) µm es POSIBLE.\n\n"
            f"Tamaño ROI: {range_x_um:.2f} µm (X) × {range_y_um:.2f} µm (Y)\n"
            f"Ingresá la resolución deseada en nanómetros/píxel (nm/px):",
            value=50.0, min=5.0, max=1000.0, decimals=1)

        if not ok: return

        pixels_x = max(4, int(round((range_x_um * 1000.0) / res_nm)))
        pixels_y = max(4, int(round((range_y_um * 1000.0) / res_nm)))

        print(f"[Camera -> Confocal] Target: ({target_x_stage:.2f}, {target_y_stage:.2f}) µm | "
              f"Range: ({range_x_um:.2f}, {range_y_um:.2f}) µm | Pixels: ({pixels_x}, {pixels_y})")
        self.roiToConfocalSignal.emit(range_x_um, range_y_um, float(pixels_x), float(pixels_y))

    # ── Set Scale ─────────────────────────────────────────────────────────────

    def _open_set_scale(self):
        if self._current_frame is None:
            QMessageBox.warning(self, "Set Scale", "Activá el Live antes de calibrar.")
            return
        roi = self._overlay.roi_fractions()
        frame = self._current_frame
        if roi:
            H, W = frame.shape[:2]
            x0, y0, x1, y1 = roi
            frame = frame[int(round(y0*H)):int(round(y1*H)), int(round(x0*W)):int(round(x1*W))]
        dlg = SetScaleDialog(frame, parent=self)
        dlg.scaleAccepted.connect(self._on_scale_accepted)
        dlg.exec()

    def _on_scale_accepted(self, um_per_px: float):
        self._um_per_px = um_per_px
        self._scale_set = True
        self._overlay.set_scale(um_per_px)
        self._lbl_scale.setText(f"Escala: {um_per_px:.5f} µm/px")
        self._lbl_scale.setStyleSheet("color: #3ecf8e; font-family: monospace; font-size: 10px;")
        self.scaleChangedSignal.emit(um_per_px)
        self._update_guards()

    def closeEvent(self, event):
        try:
            self.stopCameraSignal.emit()
        except Exception:
            pass
        event.accept()


# ══════════════════════════════════════════════════════════════════════════════
#  SET SCALE DIALOG (3 Métodos: Puntos con Snap, nm/px directo, µm/px directo)
# ══════════════════════════════════════════════════════════════════════════════

class SetScaleDialog(QDialog):
    scaleAccepted = pyqtSignal(float)

    def __init__(self, frame: np.ndarray, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Calibrar Escala Espacial (Set Scale)")
        self.setMinimumSize(740, 620)
        self._frame = frame
        self._pts   = []
        self._particles = []
        self._um_per_px = None

        lo = QVBoxLayout(self)
        lo.setContentsMargins(8, 8, 8, 8)

        intro_lbl = QLabel(
            "<b>Instrucciones de Calibración:</b> Seleccioná uno de los 3 métodos siguientes para definir "
            "la relación entre píxeles y micrómetros (µm)."
        )
        intro_lbl.setWordWrap(True)
        intro_lbl.setStyleSheet("color: #aaa; margin-bottom: 4px;")
        lo.addWidget(intro_lbl)

        self._view = pg.GraphicsLayoutWidget()
        self._vb = self._view.addViewBox(lockAspect=True); self._vb.invertY(True)
        self._img_item = pg.ImageItem(); self._vb.addItem(self._img_item)
        self._scatter  = pg.ScatterPlotItem(size=14, pen=pg.mkPen("r", width=2), brush=pg.mkBrush(None))
        self._part_scatter = pg.ScatterPlotItem(size=18, pen=pg.mkPen("#3ecf8e", width=2), brush=pg.mkBrush(None))
        self._vb.addItem(self._part_scatter)
        self._vb.addItem(self._scatter)

        self._img_item.setImage(frame.transpose(1, 0, 2))
        self._view.scene().sigMouseClicked.connect(self._on_click)
        lo.addWidget(self._view, stretch=1)

        group = QGroupBox("Opciones de Calibración (Seleccionar un Método)")
        glo = QGridLayout(group)

        lbl_a = QLabel("<b>Método A: Medición en Pantalla (2 Puntos)</b>")
        lbl_a.setToolTip("Hacé clic sobre 2 puntos conocidos en la foto. Mantené Shift presionado para encajar (Snap) al centro de la partícula.")
        glo.addWidget(lbl_a, 0, 0, 1, 2)
        btn_detect = QPushButton("Detectar Partículas (Snap)")
        btn_detect.clicked.connect(self._detect_particles)
        glo.addWidget(btn_detect, 0, 2)

        lbl_dist = QLabel("Distancia física conocida entre los 2 puntos (µm):")
        glo.addWidget(lbl_dist, 1, 0)
        self._dist_edit = QLineEdit("5.3"); self._dist_edit.setFixedWidth(90)
        glo.addWidget(self._dist_edit, 1, 1)

        lbl_b = QLabel("<b>Método B: Resolución en nm/px</b>")
        lbl_b.setToolTip("Ingresá directamente la resolución óptica del objetivo en nanómetros por píxel (ej: 50.0 nm/px).")
        glo.addWidget(lbl_b, 2, 0)
        self._nm_edit = QLineEdit(); self._nm_edit.setPlaceholderText("ej: 50.0")
        self._nm_edit.setFixedWidth(90)
        glo.addWidget(self._nm_edit, 2, 1)

        lbl_c = QLabel("<b>Método C: Factor de Escala en µm/px</b>")
        lbl_c.setToolTip("Ingresá directamente la escala calibrada en micrómetros por píxel (ej: 0.0500 µm/px).")
        glo.addWidget(lbl_c, 3, 0)
        self._um_edit = QLineEdit(); self._um_edit.setPlaceholderText("ej: 0.05")
        self._um_edit.setFixedWidth(90)
        glo.addWidget(self._um_edit, 3, 1)

        self._result_lbl = QLabel("— Seleccioná 2 puntos sobre la foto o ingresá la resolución directa")
        self._result_lbl.setStyleSheet("font-family: monospace; color: orange; font-weight: bold;")
        glo.addWidget(self._result_lbl, 4, 0, 1, 3)

        lo.addWidget(group)

        self._dist_edit.textChanged.connect(self._update_result_pts)
        self._nm_edit.textChanged.connect(self._update_result_nm)
        self._um_edit.textChanged.connect(self._update_result_um)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._accept); btns.rejected.connect(self.reject)
        self._ok_btn = btns.button(QDialogButtonBox.StandardButton.Ok)
        self._ok_btn.setEnabled(False)
        lo.addWidget(btns)

    def _detect_particles(self):
        if not _TRACKPY_AVAILABLE: return
        import warnings
        gray = np.mean(self._frame, axis=2).astype(float) if self._frame.ndim == 3 else self._frame.astype(float)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                df = tp.locate(gray, diameter=11, separation=8)
            self._particles = list(zip(df["x"].values, df["y"].values))
            self._part_scatter.setData([p[0] for p in self._particles], [p[1] for p in self._particles])
            QMessageBox.information(self, "Partículas", f"Se detectaron {len(self._particles)} partículas. Mantené Shift presionado al hacer clic para encajar automáticamente.")
        except Exception as e:
            QMessageBox.warning(self, "Error Detección", str(e))

    def _on_click(self, event):
        if event.button() != Qt.MouseButton.LeftButton: return
        pos = self._img_item.mapFromScene(event.scenePos())
        H, W = self._frame.shape[:2]
        px, py = pos.x(), pos.y()
        if not (0 <= px < W and 0 <= py < H): return

        modifiers = QApplication.keyboardModifiers()
        if (modifiers & Qt.KeyboardModifier.ShiftModifier) or self._particles:
            best_p = None; best_d = 20.0
            for cx, cy in self._particles:
                d = math.hypot(cx - px, cy - py)
                if d < best_d:
                    best_d = d; best_p = (cx, cy)
            if best_p: px, py = best_p

        self._pts.append((px, py))
        if len(self._pts) > 2: self._pts = self._pts[-2:]
        self._scatter.setData([p[0] for p in self._pts], [p[1] for p in self._pts])
        self._update_result_pts()

    def _update_result_pts(self):
        if len(self._pts) < 2: return
        (px1, py1), (px2, py2) = self._pts[-2], self._pts[-1]
        dist_px = math.hypot(px2-px1, py2-py1)
        if dist_px < 1: return
        try: known_um = float(self._dist_edit.text().replace(",", "."))
        except ValueError: return
        if known_um <= 0: return
        um_per_px = known_um / dist_px
        self._um_per_px = um_per_px
        self._result_lbl.setText(f"✓ Método A: {dist_px:.1f} px = {known_um} µm → {um_per_px:.5f} µm/px ({um_per_px*1000:.1f} nm/px)")
        self._ok_btn.setEnabled(True)

    def _update_result_nm(self, text: str):
        if not text.strip(): return
        try:
            nm_val = float(text.replace(",", "."))
            if nm_val <= 0: return
            um_per_px = nm_val / 1000.0
            self._um_per_px = um_per_px
            self._result_lbl.setText(f"✓ Método B: {nm_val:.1f} nm/px → {um_per_px:.5f} µm/px")
            self._ok_btn.setEnabled(True)
        except ValueError:
            pass

    def _update_result_um(self, text: str):
        if not text.strip(): return
        try:
            um_val = float(text.replace(",", "."))
            if um_val <= 0: return
            self._um_per_px = um_val
            self._result_lbl.setText(f"✓ Método C: {um_val:.5f} µm/px ({um_val*1000:.1f} nm/px)")
            self._ok_btn.setEnabled(True)
        except ValueError:
            pass

    def _accept(self):
        if self._um_per_px: self.scaleAccepted.emit(self._um_per_px)
        self.accept()


# ══════════════════════════════════════════════════════════════════════════════
#  TRACKPY CONFIG DIALOG
# ══════════════════════════════════════════════════════════════════════════════

class TrackpyDialog(QDialog):
    paramsAccepted = pyqtSignal(dict)

    def __init__(self, frame: np.ndarray, roi_frac: Optional[tuple] = None,
                 um_per_px: Optional[float] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configurar Detección de Partículas (Trackpy / Picasso)")
        self.setMinimumSize(780, 640)
        self._frame = frame; self._roi_frac = roi_frac; self._crop = None
        self._um_per_px = um_per_px if (um_per_px and um_per_px > 0) else None

        lo = QVBoxLayout(self)

        self._view = pg.GraphicsLayoutWidget()
        vb = self._view.addViewBox(lockAspect=True); vb.invertY(True)
        self._img_item = pg.ImageItem(); vb.addItem(self._img_item)
        self._scatter  = pg.ScatterPlotItem(size=18, pen=pg.mkPen("#3ecf8e", width=2), brush=pg.mkBrush(None))
        vb.addItem(self._scatter)
        lo.addWidget(self._view, stretch=1)

        self._count_lbl = QLabel("Detectadas: —")
        self._count_lbl.setStyleSheet("font-weight: bold; color: #3ecf8e;")
        lo.addWidget(self._count_lbl)

        params_box = QGroupBox("Parámetros de Detección"); box_vlo = QVBoxLayout(params_box)

        # Selector de Motor de Detección (Trackpy vs Picasso)
        engine_row = QHBoxLayout()
        engine_row.addWidget(QLabel("Motor de Detección:"))
        self._engine_combo = QComboBox()
        self._engine_combo.addItem("Trackpy (Crocker-Grier — Filtrado Paso-Banda)", "trackpy")
        if _PICASSO_AVAILABLE:
            self._engine_combo.addItem("Picasso (SMLM — Maximum Likelihood MLE / LQ)", "picasso")
        else:
            self._engine_combo.addItem("Picasso (No disponible)", "picasso")
            self._engine_combo.model().item(1).setEnabled(False)
        self._engine_combo.setStyleSheet("font-weight: bold; color: #4a9eff;")
        engine_row.addWidget(self._engine_combo, stretch=1)
        box_vlo.addLayout(engine_row)

        # Invertir mapa solo para el cálculo (Valles -> Picos)
        self._invert_cb = QCheckBox("Invertir imagen solo para análisis (Detectar Valles / Puntos Oscuros)")
        self._invert_cb.setToolTip("Invierte la matriz de intensidad solo para el cálculo de detección (útil si las partículas son puntos oscuros/valles en TIFF). La visualización de la imagen se mantendrá sin cambios.")
        box_vlo.addWidget(self._invert_cb)

        # Stacked Widget de Parámetros por Motor
        self._stack_params = QStackedWidget()

        # ── PÁGINA 0: TRACKPY ──────────────────────────────────────────────────
        w_tp = QWidget(); form_tp = QFormLayout(w_tp)
        form_tp.setContentsMargins(0, 0, 0, 0)

        if self._um_per_px:
            self._diam_spin = QDoubleSpinBox(); self._diam_spin.setRange(0.05, 500.0); self._diam_spin.setSingleStep(0.1); self._diam_spin.setValue(max(0.1, 11 * self._um_per_px)); self._diam_spin.setSuffix(" µm")
            self._sep_spin  = QDoubleSpinBox(); self._sep_spin.setRange(0.05, 1000.0); self._sep_spin.setSingleStep(0.2); self._sep_spin.setValue(max(0.1, 8 * self._um_per_px)); self._sep_spin.setSuffix(" µm")
            self._equiv_lbl = QLabel("—"); self._equiv_lbl.setStyleSheet("color: #3ecf8e; font-family: monospace; font-size: 11px;")
            form_tp.addRow("Diámetro estimado (µm):", self._diam_spin)
            form_tp.addRow("Separación Mínima (µm):", self._sep_spin)
            form_tp.addRow("Conversión a píxeles:", self._equiv_lbl)
            self._thr = QDoubleSpinBox(); self._thr.setRange(0, 1e6); self._thr.setValue(0)
            form_tp.addRow("Umbral de Intensidad (0 = auto):", self._thr)
            for w in (self._diam_spin, self._sep_spin, self._thr): w.valueChanged.connect(self._run_preview)
        else:
            self._diam = QSpinBox(); self._diam.setRange(3, 201); self._diam.setSingleStep(2); self._diam.setValue(11)
            self._sep  = QDoubleSpinBox(); self._sep.setRange(1, 500); self._sep.setValue(8); self._sep.setSingleStep(1)
            self._thr  = QDoubleSpinBox(); self._thr.setRange(0, 1e6); self._thr.setValue(0)
            form_tp.addRow("Diámetro estimado (px, impar):", self._diam)
            form_tp.addRow("Separación Mínima (px):", self._sep)
            form_tp.addRow("Umbral de Intensidad (0 = auto):", self._thr)
            for w in (self._diam, self._sep, self._thr): w.valueChanged.connect(self._run_preview)

        self._minmass_spin = QDoubleSpinBox(); self._minmass_spin.setRange(0, 1e7); self._minmass_spin.setValue(0)
        self._noise_size_spin = QDoubleSpinBox(); self._noise_size_spin.setRange(0.1, 20.0); self._noise_size_spin.setValue(1.0); self._noise_size_spin.setSingleStep(0.1)
        self._smoothing_size_spin = QDoubleSpinBox(); self._smoothing_size_spin.setRange(0.0, 100.0); self._smoothing_size_spin.setValue(0.0); self._smoothing_size_spin.setSingleStep(0.5)
        self._maxsize_spin = QDoubleSpinBox(); self._maxsize_spin.setRange(0.0, 200.0); self._maxsize_spin.setValue(0.0)
        self._percentile_spin = QDoubleSpinBox(); self._percentile_spin.setRange(0.0, 100.0); self._percentile_spin.setValue(64.0)

        form_tp.addRow("Masa Mínima (minmass, 0 = desact):", self._minmass_spin)
        form_tp.addRow("Filtro de Ruido (noise_size):", self._noise_size_spin)
        form_tp.addRow("Filtro Suavizado (smoothing_size, 0=auto):", self._smoothing_size_spin)
        form_tp.addRow("Tamaño Máx (maxsize, 0 = desact):", self._maxsize_spin)
        form_tp.addRow("Percentil candidatos (percentile):", self._percentile_spin)

        for w in (self._minmass_spin, self._noise_size_spin, self._smoothing_size_spin,
                  self._maxsize_spin, self._percentile_spin):
            w.valueChanged.connect(self._run_preview)

        # ── PÁGINA 1: PICASSO ──────────────────────────────────────────────────
        w_picasso = QWidget(); form_picasso = QFormLayout(w_picasso)
        form_picasso.setContentsMargins(0, 0, 0, 0)

        self._picasso_grad_spin = QDoubleSpinBox()
        self._picasso_grad_spin.setRange(1.0, 1000000.0)
        self._picasso_grad_spin.setValue(1000.0)
        self._picasso_grad_spin.setSingleStep(100.0)
        self._picasso_grad_spin.setToolTip("Gradiente neto mínimo para identificar candidatos en Picasso (min_net_gradient).")

        self._picasso_box_spin = QSpinBox()
        self._picasso_box_spin.setRange(3, 31)
        self._picasso_box_spin.setSingleStep(2)
        self._picasso_box_spin.setValue(7)
        self._picasso_box_spin.setSuffix(" px")
        self._picasso_box_spin.setToolTip("Tamaño de la caja cuadrada (impar) para cortar y ajustar el perfil 2D (box_size).")

        self._picasso_fit_combo = QComboBox()
        self._picasso_fit_combo.addItem("gaussmle (Máxima Verosimilitud MLE)", "gaussmle")
        self._picasso_fit_combo.addItem("gausslq (Mínimos Cuadrados LQ)", "gausslq")
        self._picasso_fit_combo.addItem("avg (Centro de Masas)", "avg")
        self._picasso_fit_combo.setToolTip("Algoritmo de ajuste de centroide sub-píxel de Picasso.")

        form_picasso.addRow("Gradiente Neto Mínimo (min_net_gradient):", self._picasso_grad_spin)
        form_picasso.addRow("Tamaño Caja Ajuste (box_size, px):", self._picasso_box_spin)
        form_picasso.addRow("Método de Ajuste Sub-píxel:", self._picasso_fit_combo)

        for w in (self._picasso_grad_spin, self._picasso_box_spin):
            w.valueChanged.connect(self._run_preview)
        self._picasso_fit_combo.currentIndexChanged.connect(self._run_preview)

        self._stack_params.addWidget(w_tp)
        self._stack_params.addWidget(w_picasso)
        box_vlo.addWidget(self._stack_params)

        lo.addWidget(params_box)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._accept); btns.rejected.connect(self.reject)
        lo.addWidget(btns)

        self._engine_combo.currentIndexChanged.connect(self._on_engine_changed)
        self._invert_cb.toggled.connect(self._run_preview)

        self._show_crop()
        self._run_preview()

    def _on_engine_changed(self, idx: int):
        self._stack_params.setCurrentIndex(idx)
        self._run_preview()

    def _show_crop(self):
        frame = self._frame
        if self._roi_frac:
            H, W = frame.shape[:2]
            x0, y0, x1, y1 = self._roi_frac
            frame = frame[int(round(y0*H)):int(round(y1*H)), int(round(x0*W)):int(round(x1*W))]
        self._crop = frame
        if frame.ndim == 3:
            self._img_item.setImage(frame.transpose(1, 0, 2))
        else:
            self._img_item.setImage(frame.transpose())

    def _get_pixel_params(self) -> tuple[int, float]:
        if self._um_per_px:
            d_um = self._diam_spin.value()
            s_um = self._sep_spin.value()
            raw_d = d_um / self._um_per_px
            d_px  = int(round(raw_d))
            if d_px % 2 == 0: d_px += 1
            if d_px < 3: d_px = 3
            sep_px = max(1.0, s_um / self._um_per_px)
            if hasattr(self, "_equiv_lbl"):
                self._equiv_lbl.setText(f"Diámetro: {d_px} px (impar) | Separación: {sep_px:.1f} px")
            return d_px, sep_px
        else:
            d = self._diam.value(); d = d if d % 2 == 1 else d + 1
            return d, self._sep.value()

    def _run_preview(self):
        if self._crop is None: return
        import warnings

        engine = self._engine_combo.currentData()
        gray = np.mean(self._crop, axis=2).astype(float) if self._crop.ndim == 3 else self._crop.astype(float)
        if self._invert_cb.isChecked():
            gray_for_calc = float(np.max(gray)) - gray
        else:
            gray_for_calc = gray

        if engine == "picasso" and _PICASSO_AVAILABLE:
            try:
                import picasso.localize as loc
                g_min, g_max = np.min(gray_for_calc), np.max(gray_for_calc)
                if g_max > g_min:
                    img_uint = ((gray_for_calc - g_min) / (g_max - g_min) * 65535.0).astype(np.uint16)
                else:
                    img_uint = gray_for_calc.astype(np.uint16)

                movie = np.expand_dims(img_uint, axis=0)
                min_grad = self._picasso_grad_spin.value()
                box_sz = self._picasso_box_spin.value()
                box_sz = box_sz if box_sz % 2 == 1 else box_sz + 1
                fit_m = self._picasso_fit_combo.currentData()

                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    ids = loc.identify(movie, min_grad, box_sz, progress_callback=None)
                    if ids is not None and len(ids) > 0:
                        spots = loc._cut_spots(movie, ids, box_sz)
                        if fit_m == "gausslq":
                            df = loc._fit2d_gausslq(spots, ids, box_sz)
                        elif fit_m == "avg":
                            df = loc._fit2d_avg(spots, ids, box_sz)
                        else:
                            df = loc._fit2d_gaussmle(spots, ids, box_sz, multiprocess=False)
                    else:
                        df = None

                if df is not None and len(df) > 0:
                    xs = df["x"].values
                    ys = df["y"].values
                    self._scatter.setData(xs, ys)
                    inv_tag = " [Invertida]" if self._invert_cb.isChecked() else ""
                    self._count_lbl.setText(f"Detectadas: {len(df)} partículas con Picasso ({fit_m}){inv_tag}")
                else:
                    self._scatter.clear()
                    self._count_lbl.setText("Detectadas: 0 partículas con Picasso.")
            except Exception as e:
                self._count_lbl.setText(f"Error Picasso: {e}")
        else:
            if not _TRACKPY_AVAILABLE: return
            d_px, sep_px = self._get_pixel_params()
            thr = self._thr.value() if self._thr.value() > 0 else None
            minmass = self._minmass_spin.value() if self._minmass_spin.value() > 0 else None
            noise_sz = self._noise_size_spin.value() if self._noise_size_spin.value() > 0 else 1.0
            smooth_sz = self._smoothing_size_spin.value() if self._smoothing_size_spin.value() > 0 else None
            max_sz = self._maxsize_spin.value() if self._maxsize_spin.value() > 0 else None
            percentile = self._percentile_spin.value() if self._percentile_spin.value() > 0 else 64.0

            kwargs = dict(diameter=d_px, separation=sep_px, threshold=thr, minmass=minmass,
                          noise_size=noise_sz, percentile=percentile)
            if smooth_sz is not None: kwargs["smoothing_size"] = smooth_sz
            if max_sz is not None: kwargs["maxsize"] = max_sz

            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    df = tp.locate(gray_for_calc, **kwargs)
                self._scatter.setData(df["x"].values, df["y"].values) if len(df) else self._scatter.clear()
                inv_tag = " [Invertida]" if self._invert_cb.isChecked() else ""
                self._count_lbl.setText(f"Detectadas: {len(df)} partículas con Trackpy (diámetro = {d_px} px){inv_tag}")
            except Exception as e:
                self._count_lbl.setText(f"Error Trackpy: {e}")

    def get_params(self) -> dict:
        engine = self._engine_combo.currentData()
        invert = self._invert_cb.isChecked()
        if engine == "picasso":
            box_sz = self._picasso_box_spin.value()
            box_sz = box_sz if box_sz % 2 == 1 else box_sz + 1
            return dict(
                engine="picasso",
                min_net_gradient=self._picasso_grad_spin.value(),
                box_size=box_sz,
                fit_method=self._picasso_fit_combo.currentData(),
                invert=invert
            )
        else:
            d_px, sep_px = self._get_pixel_params()
            thr = self._thr.value() if self._thr.value() > 0 else None
            minmass = self._minmass_spin.value() if self._minmass_spin.value() > 0 else None
            noise_sz = self._noise_size_spin.value() if self._noise_size_spin.value() > 0 else 1.0
            smooth_sz = self._smoothing_size_spin.value() if self._smoothing_size_spin.value() > 0 else None
            max_sz = self._maxsize_spin.value() if self._maxsize_spin.value() > 0 else None
            percentile = self._percentile_spin.value() if self._percentile_spin.value() > 0 else 64.0

            p = dict(engine="trackpy", diameter=d_px, separation=sep_px, threshold=thr, minmass=minmass,
                     noise_size=noise_sz, percentile=percentile, invert=invert)
            if smooth_sz is not None: p["smoothing_size"] = smooth_sz
            if max_sz is not None: p["maxsize"] = max_sz
            return p

    def _accept(self):
        self.paramsAccepted.emit(self.get_params())
        self.accept()


# ══════════════════════════════════════════════════════════════════════════════
#  LASER 532 NM — VENTANA FLOTANTE
# ══════════════════════════════════════════════════════════════════════════════

class Laser532Window(QWidget):
    voltageChangedSignal = pyqtSignal(float)
    shutter532Signal     = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Láser 532 nm — Dev1/ao2")
        self.setWindowFlags(
            Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.setFixedSize(440, 200)
        self._shutter_open = False

        lo = QVBoxLayout(self)
        lbl = QLabel("Láser 532 nm  —  Dev1/ao2")
        lbl.setStyleSheet("font-weight: bold; color: #55cc55; font-size: 11pt;")
        lo.addWidget(lbl)

        row = QWidget(); rlo = QHBoxLayout(row)
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setMinimum(int(LASER_532_V_MIN * 100))
        self._slider.setMaximum(int(LASER_532_V_MAX * 100))
        self._slider.setValue(int(LASER_532_V_MIN * 100))
        self._slider.setTickInterval(50)
        self._slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._slider.valueChanged.connect(self._on_slider)

        self._spin = QDoubleSpinBox()
        self._spin.setRange(LASER_532_V_MIN, LASER_532_V_MAX)
        self._spin.setSingleStep(0.05); self._spin.setDecimals(3)
        self._spin.setSuffix(" V"); self._spin.setValue(LASER_532_V_MIN)
        self._spin.valueChanged.connect(self._on_spin)

        rlo.addWidget(QLabel("Potencia:")); rlo.addWidget(self._slider, 1)
        rlo.addWidget(self._spin); lo.addWidget(row)

        presets = QWidget(); plo = QHBoxLayout(presets)
        for v in [1.0, 2.0, 3.0, 4.0, 5.0]:
            b = QPushButton(f"{v:.1f}V")
            b.clicked.connect(lambda _, val=v: self._spin.setValue(val))
            plo.addWidget(b)
        lo.addWidget(presets)

        self.btn_shutter = QPushButton("► Abrir Shutter 532 nm (Cerrado)")
        self.btn_shutter.setCheckable(True)
        self.btn_shutter.setChecked(False)
        self.btn_shutter.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_shutter.setStyleSheet(
            "background-color: #2e7d32; color: white; font-weight: bold; padding: 7px; border-radius: 4px;"
        )
        self.btn_shutter.toggled.connect(self._toggle_shutter_532)
        lo.addWidget(self.btn_shutter)

    def _toggle_shutter_532(self, checked: bool):
        self._shutter_open = checked
        if checked:
            self.btn_shutter.setText("■ Cerrar Shutter 532 nm (Abierto)")
            self.btn_shutter.setStyleSheet(
                "background-color: #c62828; color: white; font-weight: bold; padding: 7px; border-radius: 4px;"
            )
            try:
                open_shutter(SHUTTERS[0])
            except Exception as e:
                print(f"[Laser532] Error abriendo shutter: {e}")
        else:
            self.btn_shutter.setText("► Abrir Shutter 532 nm (Cerrado)")
            self.btn_shutter.setStyleSheet(
                "background-color: #2e7d32; color: white; font-weight: bold; padding: 7px; border-radius: 4px;"
            )
            try:
                close_shutter(SHUTTERS[0])
            except Exception as e:
                print(f"[Laser532] Error cerrando shutter: {e}")
        self.shutter532Signal.emit(checked)

    def _on_slider(self, val: int):
        v = val / 100.0
        self._spin.blockSignals(True); self._spin.setValue(v)
        self._spin.blockSignals(False); self.voltageChangedSignal.emit(v)

    def _on_spin(self, v: float):
        self._slider.blockSignals(True); self._slider.setValue(int(v*100))
        self._slider.blockSignals(False); self.voltageChangedSignal.emit(v)


class Laser532Backend(QObject):
    @pyqtSlot(float)
    def set_voltage(self, v: float):
        try:
            set_laser532_voltage(v)
        except Exception as e:
            print(f"[Laser532] Error: {e}")

    def make_connection(self, window: Laser532Window):
        window.voltageChangedSignal.connect(self.set_voltage)


# ══════════════════════════════════════════════════════════════════════════════
#  PUNTO DE ENTRADA (Ejecución directa)
# ══════════════════════════════════════════════════════════════════════════════

def main():
    """Punto de entrada público — llamado por el launcher raíz camera.py."""
    qapp = QApplication.instance() or QApplication(sys.argv)

    worker = CanonWorker()
    thread = QThread()
    worker.moveToThread(thread)

    win = CameraWindow()
    worker.make_connection(win)
    thread.start(QThread.Priority.HighPriority)

    win.show()
    sys.exit(qapp.exec())


if __name__ == "__main__":
    import sys
    qapp = QApplication(sys.argv)

    worker = CanonWorker()
    thread = QThread()
    worker.moveToThread(thread)

    win = CameraWindow()
    worker.make_connection(win)
    thread.start(QThread.Priority.HighPriority)

    win.show()
    sys.exit(qapp.exec())
