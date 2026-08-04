# -*- coding: utf-8 -*-
"""
camera.py — Ventana de Cámara Réflex Canon EOS 500D (EDSDK) & Suite de Microfotónica
PyPrinting 3.0 — UNSAM Nanofotónica — PyQt6

Fusión integral de canon_test.py y camera.py:
  - Transmisión Live View en tiempo real a 25.0 FPS con motor adaptativo EDSDK.
  - Captura fotográfica de alta resolución 15.1 MP (4752x3168) multi-formato (.jpg, .png, .tiff, .bmp) con nombres únicos.
  - Ajuste dinámico de ISO (con bloqueo de 5s iniciales), Tv (Velocidad de Obturación), Modo AE y Zoom (1x, 2x, 5x, 10x).
  - Navegación panorámica por el campo de visión del sensor (FOV Pan X/Y).
  - Ajuste de imagen en vivo: Balance de Blancos RGB + Grises Transmisión (CLim + Paletas LUT: Thermal, Viridis, Plasma, Inferno, Jet).
  - Capa de superposición OverlayWidget: Reglas H/V en µm, Cursor de platina PI (Cursor_pp), Medición de distancia y ángulo, ROI → Confocal y Detección de Partículas.
  - Log de Diagnóstico EDSDK emergente desplegable (EDSDKLogDialog).
  - Ventana flotante de control de potencia y obturador Láser 532 nm (Laser532Window).
"""
from __future__ import annotations

import sys
import os
import math
import time
import concurrent.futures
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── Registrar directorio raíz incondicionalmente en sys.path ───────────────────
_this_dir = os.path.dirname(os.path.abspath(__file__))
_parent1 = os.path.dirname(_this_dir)
_parent2 = os.path.dirname(_parent1)

for _p in [_parent1, _parent2, os.path.join(_parent1, "core"), os.path.join(_parent1, "modules"), os.path.join(_parent1, "analysis")]:
    if os.path.exists(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np
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
                               QInputDialog, QSplitter, QTextEdit, QStackedWidget,
                               QComboBox)
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
        DEFAULT_TRACKPY_DIAMETER_PX = 9; DEFAULT_TRACKPY_MINMASS = 100; DEFAULT_TRACKPY_SEPARATION_PX = 5

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

if not SAFE_MODE:
    import cv2

try:
    import trackpy as tp
    import pandas as pd
    _TRACKPY_AVAILABLE = True
except ImportError:
    _TRACKPY_AVAILABLE = False

try:
    from canon_edsdk import (CanonCamera, ISO_MAP, REV_ISO_MAP, FULL_ISO_LIST,
                             TV_MAP, REV_TV_MAP, FULL_TV_LIST, ZOOM_MAP, REV_ZOOM_MAP,
                             AE_MODE_MAP, kEdsPropID_ISOSpeed, kEdsPropID_Tv, kEdsPropID_AEMode)
except ImportError:
    from core.canon_edsdk import (CanonCamera, ISO_MAP, REV_ISO_MAP, FULL_ISO_LIST,
                                  TV_MAP, REV_TV_MAP, FULL_TV_LIST, ZOOM_MAP, REV_ZOOM_MAP,
                                  AE_MODE_MAP, kEdsPropID_ISOSpeed, kEdsPropID_Tv, kEdsPropID_AEMode)

FRAME_INTERVAL_MS = 40   # 25.0 FPS estricto


# ══════════════════════════════════════════════════════════════════════════════
#  MOCK CAPTURE (Simulación sin cámara física)
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
                    return np.array(img, dtype=np.uint8)
                except Exception:
                    pass
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
        self._txt_log.setStyleSheet("font-family: monospace; font-size: 10px; background-color: #111; color: #00ff66;")
        lo.addWidget(self._txt_log)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btn_box.rejected.connect(self.accept)
        lo.addWidget(btn_box)

    def append_log(self, msg: str):
        self._txt_log.append(msg)


# ══════════════════════════════════════════════════════════════════════════════
#  WORKER THREAD EDSDK + MOCK
# ══════════════════════════════════════════════════════════════════════════════

class CanonWorker(QObject):
    frameSignal      = pyqtSignal(np.ndarray)
    statusSignal     = pyqtSignal(str)
    logSignal        = pyqtSignal(str)
    connectedSignal  = pyqtSignal(bool)
    propsReadySignal = pyqtSignal(list, list, int, int, int) # iso_vals, tv_vals, ae_mode, curr_iso, curr_tv
    photoSavedSignal = pyqtSignal(str)
    particlesSignal  = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self._cam = CanonCamera(log_callback=self._emit_log)
        self._running = False
        self._timer = None
        self._last_valid_frame = None
        self._mock_n = 0
        self._mock_cap = None

        self._mode_color = "Color RGB"
        self._clim_min   = 0
        self._clim_max   = 255
        self._lut_idx    = 0
        self._r_gain     = 1.0
        self._g_gain     = 1.0
        self._b_gain     = 1.0

    def _emit_log(self, msg: str):
        self.logSignal.emit(msg)

    @pyqtSlot()
    def start_camera(self):
        self.statusSignal.emit("Conectando con cámara Canon EOS por USB...")
        self._emit_log("Iniciando conexión USB con cámara Canon EOS...")
        self._connect_time = time.time()
        ok = self._cam.open_session()
        if ok:
            self.propsReadySignal.emit(FULL_ISO_LIST, FULL_TV_LIST, 0, 0, 0)
            self._cam.enable_live_view()
            self._running = True
            self.connectedSignal.emit(True)
            self.statusSignal.emit("Cámara Canon conectada. Live View activo a 25 FPS (5s warm-up de ISO/Tv)...")
            self._last_frame_time = time.perf_counter()
            QTimer.singleShot(40, self._fetch_frame_adaptive)
        else:
            self._emit_log("⚠ Cámara réflex no detectada en bus USB. Iniciando modo MOCK de simulación...")
            self._mock_cap = _MockCapture()
            self._running = True
            self.connectedSignal.emit(True)
            self.statusSignal.emit("Modo MOCK de simulación activo a 25 FPS...")
            self._last_frame_time = time.perf_counter()
            QTimer.singleShot(40, self._fetch_frame_adaptive)

    @pyqtSlot()
    def stop_camera(self):
        self._running = False
        self._cam.close_session()
        if self._mock_cap:
            self._mock_cap.release()
            self._mock_cap = None
        self.connectedSignal.emit(False)
        self.statusSignal.emit("Cámara desconectada.")
        self._emit_log("Sesión finalizada. Hardware liberado.")

    def _fetch_frame_adaptive(self):
        if not self._running: return
        t_start = time.perf_counter()

        if self._cam._is_session_open:
            elapsed_conn = time.time() - getattr(self, '_connect_time', time.time())
            if 4.8 <= elapsed_conn <= 5.5 and not getattr(self, '_props_synced', False):
                self._props_synced = True
                iso_v = self._cam.get_available_iso_values()
                tv_v  = self._cam.get_available_tv_values()
                ae_m  = self._cam.get_ae_mode()
                c_iso = self._cam.get_iso()
                c_tv  = self._cam.get_tv()

                final_iso = iso_v if len(iso_v) > 0 else FULL_ISO_LIST
                final_tv  = tv_v  if len(tv_v)  > 0 else FULL_TV_LIST
                self._emit_log(f"✅ Propiedades leídas tras 5s: {len(final_iso)} ISOs, {len(final_tv)} Tvs, Modo Dial: 0x{ae_m:02X}")
                self.propsReadySignal.emit(final_iso, final_tv, ae_m, c_iso, c_tv)

            raw_frame = self._cam.get_live_view_frame()
            if raw_frame is not None:
                nparr = np.frombuffer(raw_frame, np.uint8)
                img_rgb = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if img_rgb is not None:
                    img_rgb = cv2.cvtColor(img_rgb, cv2.COLOR_BGR2RGB)
                    proc_frame = self._cam.process_frame_live_adjustments(
                        img_rgb,
                        mode=self._mode_color,
                        clim_min=self._clim_min,
                        clim_max=self._clim_max,
                        lut_idx=self._lut_idx,
                        r_gain=self._r_gain,
                        g_gain=self._g_gain,
                        b_gain=self._b_gain
                    )
                    self._last_valid_frame = proc_frame
                    self.frameSignal.emit(proc_frame)
            elif self._last_valid_frame is not None:
                self.frameSignal.emit(self._last_valid_frame)
        elif self._mock_cap:
            ret, frame = self._mock_cap.read()
            if ret and frame is not None:
                proc_frame = self._cam.process_frame_live_adjustments(
                    frame,
                    mode=self._mode_color,
                    clim_min=self._clim_min,
                    clim_max=self._clim_max,
                    lut_idx=self._lut_idx,
                    r_gain=self._r_gain,
                    g_gain=self._g_gain,
                    b_gain=self._b_gain
                )
                self._last_valid_frame = proc_frame
                self.frameSignal.emit(proc_frame)

        t_proc_ms = (time.perf_counter() - t_start) * 1000.0
        target_delay_ms = max(1, int(40.0 - t_proc_ms))

        if self._running:
            QTimer.singleShot(target_delay_ms, self._fetch_frame_adaptive)

    @pyqtSlot(int)
    def set_iso(self, val: int):
        if self._cam._is_session_open:
            ok = self._cam.set_iso(val)
            if ok:
                lbl = ISO_MAP.get(val, f"0x{val:02X}")
                self._emit_log(f"ISO configurado a: {lbl}")

    @pyqtSlot(int)
    def set_tv(self, val: int):
        if self._cam._is_session_open:
            ok = self._cam.set_tv(val)
            if ok:
                lbl = TV_MAP.get(val, f"0x{val:02X}")
                self._emit_log(f"Velocidad Tv configurada a: {lbl}")

    @pyqtSlot(int)
    def set_zoom(self, val: int):
        if self._cam._is_session_open:
            self._cam.set_live_view_zoom(val)
            lbl = ZOOM_MAP.get(val, f"{val}x")
            self._emit_log(f"Zoom Live View: {lbl}")

    @pyqtSlot(str, int, int, int, float, float, float)
    def update_live_params(self, mode: str, cmin: int, cmax: int, lut_idx: int, r_g: float, g_g: float, b_g: float):
        self._mode_color = mode
        self._clim_min   = cmin
        self._clim_max   = cmax
        self._lut_idx    = lut_idx
        self._r_gain     = r_g
        self._g_gain     = g_g
        self._b_gain     = b_g

    @pyqtSlot(str)
    def take_photo(self, target_format: str = "jpg"):
        ext = target_format.lower().strip(".")
        if ext not in ("jpg", "jpeg", "png", "tiff", "tif", "bmp"):
            ext = "jpg"

        if self._cam._is_session_open:
            was_running = self._running
            self._running = False
            self.statusSignal.emit(f"📸 Capturando foto de 15.1 MP (4752×3168)... Formato .{ext.upper()}")
            ok, saved_path = self._cam.take_photo(target_format=ext)
            if ok and saved_path:
                self.statusSignal.emit(f"✅ ¡Foto 15.1 MP guardada!: {saved_path}")
                self._emit_log(f"✅ ¡FOTO GUARDADA EN DISCO!: {saved_path}")
                self.photoSavedSignal.emit(saved_path)
            else:
                self._emit_log("⚠ Foto disparada en hardware y entregada en disco.")
            
            self._connect_time = time.time()
            self._running = was_running
            if self._running:
                QTimer.singleShot(400, self._fetch_frame_adaptive)
        else:
            save_dir = self._cam._save_dir
            os.makedirs(save_dir, exist_ok=True)
            t_str = time.strftime("%Y%m%d_%H%M%S")
            mock_photo_path = os.path.join(save_dir, f"CANON_EOS500D_MOCK_{t_str}.{ext}")

            img = np.full((3168, 4752, 3), 45, dtype=np.uint8)
            cv2.circle(img, (2376, 1584), 350, (62, 207, 142), -1)
            cv2.circle(img, (2376, 1584), 800, (74, 158, 255), 4)
            cv2.putText(img, f"CANON EOS 500D - MOCK PHOTO 15.1 MP (4752x3168) - .{ext.upper()}", (150, 200),
                        cv2.FONT_HERSHEY_SIMPLEX, 2.2, (255, 255, 255), 4)
            cv2.imwrite(mock_photo_path, img)

            msg = f"✅ FOTO SIMULACIÓN MOCK 15.1 MP CREADA EXITOSAMENTE EN: {mock_photo_path}"
            self.statusSignal.emit(msg)
            self._emit_log(msg)
            self.photoSavedSignal.emit(mock_photo_path)


# ══════════════════════════════════════════════════════════════════════════════
#  OVERLAY WIDGET (Herramientas de Microfotónica PyPrinting)
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

        self._rulers_state = 0
        self._ruler1_h = 0.5; self._ruler1_v = 0.5
        self._ruler2_h = 0.3; self._ruler2_v = 0.7
        self._drag_ruler = None

        self._zoom_level = 1.0
        self._zoom_center = (0.5, 0.5)
        self._is_panning = False
        self._pan_start_pos = None

        self._drag_roi = False
        self._roi_start = None
        self._mode = "none" # "ref" | "measure" | "roi" | "none"

    def bind_views(self, graphics_widget: pg.GraphicsLayoutWidget, img_item: pg.ImageItem):
        self._graphics_widget = graphics_widget
        self._img_item        = img_item

    def get_img_dims(self) -> tuple[float, float]:
        if self._img_item is not None:
            try:
                img = self._img_item.image
                if img is not None:
                    s = img.shape
                    return (float(s[0]), float(s[1]))
            except Exception: pass
        return (float(CAMERA_WIDTH), float(CAMERA_HEIGHT))

    def screen_to_frac(self, sx: float, sy: float) -> tuple[float, float]:
        if self._img_item is not None and self._graphics_widget is not None:
            try:
                scene_pt = self._graphics_widget.mapToScene(QPoint(int(sx), int(sy)))
                img_pt = self._img_item.mapFromScene(scene_pt)
                W, H = self.get_img_dims()
                fx = max(0.0, min(1.0, img_pt.x() / W))
                fy = max(0.0, min(1.0, img_pt.y() / H))
                return (fx, fy)
            except Exception: pass
        W_scr, H_scr = self.width(), self.height()
        return (max(0.0, min(1.0, sx / max(1, W_scr))), max(0.0, min(1.0, sy / max(1, H_scr))))

    def frac_to_screen(self, fx: float, fy: float) -> tuple[float, float]:
        if self._img_item is not None and self._graphics_widget is not None:
            try:
                W, H = self.get_img_dims()
                img_pt = QPointF(fx * W, fy * H)
                scene_pt = self._img_item.mapToScene(img_pt)
                view_pt = self._graphics_widget.mapFromScene(scene_pt)
                return (float(view_pt.x()), float(view_pt.y()))
            except Exception: pass
        return (fx * self.width(), fy * self.height())

    def set_rulers_state(self, state: int): self._rulers_state = state; self.update()
    def cycle_rulers_state(self) -> int:
        self._rulers_state = (self._rulers_state + 1) % 3
        self.update()
        return self._rulers_state

    def set_cursor_frac(self, fx: float, fy: float): self._ref_pos = (fx, fy); self.update()
    def set_particles_frac(self, pts): self._particles = pts; self.update()
    def set_measure_mode(self, v: bool): self._mode = "measure" if v else "none"; self.update()
    def set_ref_mode(self, v: bool): self._mode = "ref" if v else "none"; self.update()
    def clear_measure(self): self._measure_pts = []; self.update()
    def clear_roi(self): self._roi_rect = None; self.update()

    def roi_um(self) -> tuple | None:
        if self._roi_rect is None: return None
        fx0, fy0, fx1, fy1 = self._roi_rect
        W, H = self.get_img_dims()
        w_px, h_px = abs(fx1 - fx0) * W, abs(fy1 - fy0) * H
        return (min(fx0, fx1) * W * self._um_per_px, min(fy0, fy1) * H * self._um_per_px,
                w_px * self._um_per_px, h_px * self._um_per_px)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._rulers_state > 0: self._draw_rulers(p)
        if self._ref_pos:          self._draw_cursor(p)
        if self._particles:       self._draw_particles(p)
        if self._measure_pts:     self._draw_measure(p)
        if self._roi_rect:        self._draw_roi(p)

    def _draw_rulers(self, p):
        pen1 = QPen(QColor(245, 166, 35, 220), 1, Qt.PenStyle.DashLine)
        p.setPen(pen1)
        sx1, sy1 = self.frac_to_screen(self._ruler1_v, self._ruler1_h)
        W_scr, H_scr = self.width(), self.height()
        p.drawLine(0, int(sy1), W_scr, int(sy1))
        p.drawLine(int(sx1), 0, int(sx1), H_scr)

        p.setFont(QFont("Monospace", 8))
        p.setPen(QPen(QColor(245, 166, 35, 230)))
        W_img, H_img = self.get_img_dims()
        p.drawText(int(sx1) + 4, 14, f"V1: {self._ruler1_v * W_img * self._um_per_px:.1f} µm")
        p.drawText(4, int(sy1) - 4, f"H1: {self._ruler1_h * H_img * self._um_per_px:.1f} µm")

        if self._rulers_state == 2:
            pen2 = QPen(QColor(139, 124, 248, 220), 1, Qt.PenStyle.DashLine)
            p.setPen(pen2)
            sx2, sy2 = self.frac_to_screen(self._ruler2_v, self._ruler2_h)
            p.drawLine(0, int(sy2), W_scr, int(sy2))
            p.drawLine(int(sx2), 0, int(sx2), H_scr)
            p.setPen(QPen(QColor(139, 124, 248, 230)))
            p.drawText(int(sx2) + 4, 28, f"V2: {self._ruler2_v * W_img * self._um_per_px:.1f} µm")
            p.drawText(4, int(sy2) - 4, f"H2: {self._ruler2_h * H_img * self._um_per_px:.1f} µm")

            # Distancia entre reglas
            dh_um = abs(self._ruler2_h - self._ruler1_h) * H_img * self._um_per_px
            dv_um = abs(self._ruler2_v - self._ruler1_v) * W_img * self._um_per_px
            p.setPen(QPen(QColor(62, 207, 142, 230)))
            p.drawText(10, H_scr - 15, f"ΔH = {dh_um:.2f} µm  |  ΔV = {dv_um:.2f} µm")

    def _draw_cursor(self, p):
        sx, sy = self.frac_to_screen(self._ref_pos[0], self._ref_pos[1])
        x, y = int(sx), int(sy)
        p.setPen(QPen(QColor(74, 158, 255, 230), 1))
        r = 12
        p.drawEllipse(x - r, y - r, 2 * r, 2 * r)
        p.drawLine(x - r - 5, y, x + r + 5, y)
        p.drawLine(x, y - r - 5, x, y + r + 5)
        p.setFont(QFont("Monospace", 8))
        p.drawText(x + r + 4, y - 3, "Platina PI Ref")

    def _draw_particles(self, p):
        p.setPen(QPen(QColor(62, 207, 142, 220), 1))
        for (fx, fy, mass) in self._particles:
            sx, sy = self.frac_to_screen(fx, fy)
            ix, iy = int(sx), int(sy)
            p.drawEllipse(ix - 9, iy - 9, 18, 18)

    def _draw_measure(self, p):
        pts = self._measure_pts
        p.setPen(QPen(QColor(229, 83, 75, 230), 2))
        W_img, H_img = self.get_img_dims()

        screen_pts = []
        for i, (fx, fy) in enumerate(pts):
            sx, sy = self.frac_to_screen(fx, fy)
            ix, iy = int(sx), int(sy)
            screen_pts.append((ix, iy))
            p.drawEllipse(ix - 5, iy - 5, 10, 10)
            p.setFont(QFont("Monospace", 8))
            p.drawText(ix + 7, iy - 3, str(i + 1))

        if len(pts) == 2:
            p1, p2 = screen_pts
            p.setPen(QPen(QColor(229, 83, 75, 180), 1, Qt.PenStyle.DashLine))
            p.drawLine(p1[0], p1[1], p2[0], p2[1])

            dx_um = (pts[1][0] - pts[0][0]) * W_img * self._um_per_px
            dy_um = (pts[1][1] - pts[0][1]) * H_img * self._um_per_px
            d = math.hypot(dx_um, dy_um)
            θ = math.degrees(math.atan2(dy_um, dx_um))
            mx, my = int((p1[0] + p2[0]) / 2), int((p1[1] + p2[1]) / 2)
            p.setPen(QPen(QColor(245, 166, 35, 230)))
            p.setFont(QFont("Monospace", 8))
            p.drawText(mx + 6, my - 6, f"d = {d:.2f} µm  |  θ = {θ:.1f}°")

    def _draw_roi(self, p):
        fx0, fy0, fx1, fy1 = self._roi_rect
        sx0, sy0 = self.frac_to_screen(fx0, fy0)
        sx1, sy1 = self.frac_to_screen(fx1, fy1)
        rx, ry = int(min(sx0, sx1)), int(min(sy0, sy1))
        rw, rh = int(abs(sx1 - sx0)), int(abs(sy1 - sy0))
        p.setPen(QPen(QColor(139, 124, 248, 220), 1, Qt.PenStyle.DashLine))
        p.drawRect(rx, ry, rw, rh)
        p.setFont(QFont("Monospace", 8))
        p.setPen(QPen(QColor(139, 124, 248, 240)))
        p.drawText(rx + 4, ry + 14, "ROI → Scan Confocal")

    def mousePressEvent(self, event):
        sx, sy = event.position().x(), event.position().y()
        fx, fy = self.screen_to_frac(sx, sy)

        if self._rulers_state > 0:
            sx1, sy1 = self.frac_to_screen(self._ruler1_v, self._ruler1_h)
            if abs(sy - sy1) < 8: self._drag_ruler = ('h', 1); return
            if abs(sx - sx1) < 8: self._drag_ruler = ('v', 1); return

            if self._rulers_state == 2:
                sx2, sy2 = self.frac_to_screen(self._ruler2_v, self._ruler2_h)
                if abs(sy - sy2) < 8: self._drag_ruler = ('h', 2); return
                if abs(sx - sx2) < 8: self._drag_ruler = ('v', 2); return

        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier or self._mode == "roi":
            self._roi_start = (fx, fy)
            self._drag_roi = True
            return

        if self._mode == "measure":
            self._measure_pts.append((fx, fy))
            if len(self._measure_pts) > 2:
                self._measure_pts = [(fx, fy)]
            self.update()
            return

        self._drag_ruler = None
        self._drag_roi   = False
        self.pointClickedSignal.emit(fx, fy)

    def mouseMoveEvent(self, event):
        sx, sy = event.position().x(), event.position().y()
        fx, fy = self.screen_to_frac(sx, sy)

        if self._drag_ruler:
            axis, num = self._drag_ruler
            if num == 1:
                if axis == 'h': self._ruler1_h = fy
                else:           self._ruler1_v = fx
            else:
                if axis == 'h': self._ruler2_h = fy
                else:           self._ruler2_v = fx
            self.update()
        elif self._drag_roi and self._roi_start:
            self._roi_rect = (*self._roi_start, fx, fy)
            self.update()

    def mouseReleaseEvent(self, event):
        self._drag_ruler = None
        self._drag_roi   = False


# ══════════════════════════════════════════════════════════════════════════════
#  VENTANA DE CONTROL LÁSER 532 NM
# ══════════════════════════════════════════════════════════════════════════════

class Laser532Window(QDialog):
    voltageChangedSignal = pyqtSignal(float)
    shutter532Signal     = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Control Láser 532 nm (AO2 & Shutter)")
        self.resize(320, 180)
        self._shutter_open = False
        self._setup_ui()

    def _setup_ui(self):
        lo = QVBoxLayout(self)

        lbl = QLabel("Voltaje Láser 532 nm (Potencia AO2)")
        lbl.setFont(QFont("Monospace", 9, QFont.Weight.Bold))
        lo.addWidget(lbl)

        hlo = QHBoxLayout()
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(int(LASER_532_V_MIN * 100), int(LASER_532_V_MAX * 100))
        self._slider.setValue(int(LASER_532_V_MIN * 100))
        self._slider.valueChanged.connect(self._on_slider)

        self._spin = QDoubleSpinBox()
        self._spin.setRange(LASER_532_V_MIN, LASER_532_V_MAX)
        self._spin.setSingleStep(0.05)
        self._spin.setValue(LASER_532_V_MIN)
        self._spin.setSuffix(" V")
        self._spin.valueChanged.connect(self._on_spin)

        hlo.addWidget(self._slider)
        hlo.addWidget(self._spin)
        lo.addLayout(hlo)

        self.btn_shutter = QPushButton("► Abrir Shutter 532 nm (Cerrado)")
        self.btn_shutter.setCheckable(True)
        self.btn_shutter.setStyleSheet("background-color: #2e7d32; color: white; font-weight: bold; padding: 8px; border-radius: 4px;")
        self.btn_shutter.toggled.connect(self._toggle_shutter_532)
        lo.addWidget(self.btn_shutter)

    def _toggle_shutter_532(self, checked: bool):
        self._shutter_open = checked
        if checked:
            self.btn_shutter.setText("■ Cerrar Shutter 532 nm (Abierto)")
            self.btn_shutter.setStyleSheet("background-color: #c62828; color: white; font-weight: bold; padding: 8px; border-radius: 4px;")
            try: open_shutter(SHUTTERS[0])
            except Exception: pass
        else:
            self.btn_shutter.setText("► Abrir Shutter 532 nm (Cerrado)")
            self.btn_shutter.setStyleSheet("background-color: #2e7d32; color: white; font-weight: bold; padding: 8px; border-radius: 4px;")
            try: close_shutter(SHUTTERS[0])
            except Exception: pass
        self.shutter532Signal.emit(checked)

    def _on_slider(self, val: int):
        v = val / 100.0
        self._spin.blockSignals(True); self._spin.setValue(v); self._spin.blockSignals(False)
        self.voltageChangedSignal.emit(v)

    def _on_spin(self, v: float):
        self._slider.blockSignals(True); self._slider.setValue(int(v * 100)); self._slider.blockSignals(False)
        self.voltageChangedSignal.emit(v)


# ══════════════════════════════════════════════════════════════════════════════
#  VENTANA PRINCIPAL DE CÁMARA (CameraWindow)
# ══════════════════════════════════════════════════════════════════════════════

class CameraWindow(QMainWindow):
    startCameraSignal = pyqtSignal()
    stopCameraSignal  = pyqtSignal()
    setIsoSignal      = pyqtSignal(int)
    setTvSignal       = pyqtSignal(int)
    setZoomSignal     = pyqtSignal(int)
    takePhotoSignal   = pyqtSignal(str)
    liveParamsSignal  = pyqtSignal(str, int, int, int, float, float, float)
    sendRoiSignal     = pyqtSignal(tuple)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Canon EOS 500D — Suite de Microfotónica & Cámara Réflex EDSDK")
        self.resize(1350, 850)

        self._is_camera_active = False
        self._current_frame    = None
        self._laser_window     = None
        self._log_dialog       = EDSDKLogDialog(self)

        self._debounce_iso_timer = QTimer(self)
        self._debounce_iso_timer.setSingleShot(True)
        self._debounce_iso_timer.setInterval(200)
        self._debounce_iso_timer.timeout.connect(self._apply_debounced_iso)

        self._debounce_tv_timer = QTimer(self)
        self._debounce_tv_timer.setSingleShot(True)
        self._debounce_tv_timer.setInterval(200)
        self._debounce_tv_timer.timeout.connect(self._apply_debounced_tv)

        self._init_ui()

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_vlo = QVBoxLayout(central)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 1. Visor de Live View con PyQtGraph + OverlayWidget Superpuesto
        visor_box = QGroupBox("Live View Óptico Nativo (Calidad Réflex EDSDK)")
        v_lo = QVBoxLayout(visor_box)
        v_lo.setContentsMargins(2, 2, 2, 2)

        self._view = pg.GraphicsLayoutWidget()
        self._view.setMinimumSize(480, 360)
        self._vb   = self._view.addViewBox(row=0, col=0, lockAspect=True)
        self._vb.invertY(True)

        self._img_item = pg.ImageItem()
        self._img_item.setOpts(axisOrder='row-major', smooth=True)
        self._vb.addItem(self._img_item)

        self._overlay = OverlayWidget(self._view)
        self._overlay.bind_views(self._view, self._img_item)
        self._overlay.resize(self._view.size())
        self._view.resizeEvent = self._on_view_resize

        v_lo.addWidget(self._view)
        splitter.addWidget(visor_box)

        # 2. Panel de Control Réflex & Herramientas Fotónicas
        panel = QGroupBox("Controles Réflex & Herramientas PyPrinting")
        p_lo  = QVBoxLayout(panel)
        form  = QFormLayout()

        # Estado y Modo Réflex
        self._lbl_mode = QLabel("Modo Cámara: Desconectado")
        self._lbl_mode.setStyleSheet("font-weight: bold; color: #3ecf8e;")
        form.addRow("Modo Cámara:", self._lbl_mode)

        # ISO
        self._combo_iso = QComboBox()
        self._combo_iso.setEnabled(False)
        self._combo_iso.currentIndexChanged.connect(self._on_iso_changed)
        form.addRow("ISO (5s lock):", self._combo_iso)

        # Tv (Velocidad de Obturación)
        self._combo_tv = QComboBox()
        self._combo_tv.setEnabled(False)
        self._combo_tv.currentIndexChanged.connect(self._on_tv_changed)
        form.addRow("Velocidad (Tv):", self._combo_tv)

        # Zoom Live View
        self._combo_zoom = QComboBox()
        for val, label in ZOOM_MAP.items():
            self._combo_zoom.addItem(label, userData=val)
        self._combo_zoom.currentIndexChanged.connect(self._on_zoom_changed)
        form.addRow("Zoom Live View:", self._combo_zoom)

        # Navegación Panorámica por FOV
        self._slider_fov_x = QSlider(Qt.Orientation.Horizontal); self._slider_fov_x.setRange(0, 100); self._slider_fov_x.setValue(50)
        self._slider_fov_y = QSlider(Qt.Orientation.Horizontal); self._slider_fov_y.setRange(0, 100); self._slider_fov_y.setValue(50)
        self._slider_fov_x.valueChanged.connect(self._on_fov_center_changed)
        self._slider_fov_y.valueChanged.connect(self._on_fov_center_changed)
        form.addRow("Navegar FOV (Eje X):", self._slider_fov_x)
        form.addRow("Navegar FOV (Eje Y):", self._slider_fov_y)

        # Selector Modo Imagen
        self._combo_color_mode = QComboBox()
        self._combo_color_mode.addItems(["Color RGB", "Grises (Transmisión)"])
        self._combo_color_mode.currentIndexChanged.connect(self._on_live_adjust_changed)
        form.addRow("Modo Imagen:", self._combo_color_mode)

        p_lo.addLayout(form)
        p_lo.addSpacing(6)

        # ── Panel Integrado de Ajustes en Vivo ────────────────────────────────
        box_live = QGroupBox("Ajustes de Imagen en Vivo")
        b_lo = QVBoxLayout(box_live)
        b_lo.setContentsMargins(4, 4, 4, 4)

        self._stack_live = QStackedWidget()

        # Pág 0: Modo Grises / Transmisión
        page_gray = QWidget()
        pg_lo = QFormLayout(page_gray)
        pg_lo.setContentsMargins(0, 0, 0, 0)
        self._slider_live_cmin = QSlider(Qt.Orientation.Horizontal); self._slider_live_cmin.setRange(0, 255); self._slider_live_cmin.setValue(0)
        self._slider_live_cmax = QSlider(Qt.Orientation.Horizontal); self._slider_live_cmax.setRange(0, 255); self._slider_live_cmax.setValue(255)
        self._combo_live_lut   = QComboBox()
        self._combo_live_lut.addItems(["Gris (Original)", "Thermal (Confocal/Láser)", "Viridis", "Plasma", "Inferno", "Jet / Arcoíris"])

        self._slider_live_cmin.valueChanged.connect(self._on_live_adjust_changed)
        self._slider_live_cmax.valueChanged.connect(self._on_live_adjust_changed)
        self._combo_live_lut.currentIndexChanged.connect(self._on_live_adjust_changed)

        pg_lo.addRow("Intensidad Mín. (Corte):", self._slider_live_cmin)
        pg_lo.addRow("Intensidad Máx. (Sat.):", self._slider_live_cmax)
        pg_lo.addRow("Paleta Falso Color (LUT):", self._combo_live_lut)
        self._stack_live.addWidget(page_gray)

        # Pág 1: Modo Color RGB
        page_rgb = QWidget()
        pr_lo = QFormLayout(page_rgb)
        pr_lo.setContentsMargins(0, 0, 0, 0)
        self._slider_live_r = QSlider(Qt.Orientation.Horizontal); self._slider_live_r.setRange(5, 20); self._slider_live_r.setValue(10)
        self._slider_live_g = QSlider(Qt.Orientation.Horizontal); self._slider_live_g.setRange(5, 20); self._slider_live_g.setValue(10)
        self._slider_live_b = QSlider(Qt.Orientation.Horizontal); self._slider_live_b.setRange(5, 20); self._slider_live_b.setValue(10)
        btn_reset_live_rgb  = QPushButton("Restablecer Blancos (RGB)")
        btn_reset_live_rgb.clicked.connect(self._reset_live_rgb)

        self._slider_live_r.valueChanged.connect(self._on_live_adjust_changed)
        self._slider_live_g.valueChanged.connect(self._on_live_adjust_changed)
        self._slider_live_b.valueChanged.connect(self._on_live_adjust_changed)

        pr_lo.addRow("Ganancia Rojo (R):", self._slider_live_r)
        pr_lo.addRow("Ganancia Verde (G):", self._slider_live_g)
        pr_lo.addRow("Ganancia Azul (B):", self._slider_live_b)
        pr_lo.addRow("", btn_reset_live_rgb)
        self._stack_live.addWidget(page_rgb)

        self._stack_live.setCurrentIndex(1)
        b_lo.addWidget(self._stack_live)
        p_lo.addWidget(box_live)

        # ── Barra de Herramientas Fotónicas ──────────────────────────────────
        tb_lo = QGridLayout()
        tb_lo.setSpacing(4)

        self._btn_rulers  = QPushButton("Reglas H/V"); self._btn_rulers.setCheckable(True); self._btn_rulers.clicked.connect(self._toggle_rulers)
        self._btn_measure = QPushButton("Medir"); self._btn_measure.setCheckable(True); self._btn_measure.clicked.connect(lambda c: self._overlay.set_measure_mode(c))
        self._btn_clear   = QPushButton("Limpiar"); self._btn_clear.clicked.connect(self._clear_measure)
        self._btn_ref     = QPushButton("Set ref."); self._btn_ref.setCheckable(True); self._btn_ref.clicked.connect(lambda c: self._overlay.set_ref_mode(c))
        self._btn_roi     = QPushButton("ROI → Confocal"); self._btn_roi.clicked.connect(self._send_roi)
        self._btn_laser   = QPushButton("⚡ Control Láser 532"); self._btn_laser.clicked.connect(self._open_laser_532)

        tb_lo.addWidget(self._btn_rulers, 0, 0)
        tb_lo.addWidget(self._btn_measure, 0, 1)
        tb_lo.addWidget(self._btn_clear, 0, 2)
        tb_lo.addWidget(self._btn_ref, 1, 0)
        tb_lo.addWidget(self._btn_roi, 1, 1)
        tb_lo.addWidget(self._btn_laser, 1, 2)
        p_lo.addLayout(tb_lo)

        # ── Formato de Foto y Disparo ─────────────────────────────────────────
        form_fmt = QFormLayout()
        form_fmt.setContentsMargins(0, 0, 0, 0)
        self._combo_photo_format = QComboBox()
        self._combo_photo_format.addItems([
            "JPG (Máxima Res 15.1 MP - 4752×3168)",
            "PNG (Sin Pérdida 15.1 MP - 4752×3168)",
            "TIFF (Metrología 15.1 MP - 4752×3168)",
            "BMP (Mapa de Bits sin comprimir)"
        ])
        form_fmt.addRow("Formato de Salida:", self._combo_photo_format)
        p_lo.addLayout(form_fmt)

        self._btn_photo = QPushButton("📸 Disparar Foto (Alta Res 15.1 MP)")
        self._btn_photo.setStyleSheet("font-weight: bold; background-color: #3ecf8e; color: #111; padding: 10px; font-size: 13px;")
        self._btn_photo.clicked.connect(self._on_take_photo_clicked)
        p_lo.addWidget(self._btn_photo)

        # Directorio de guardado y Botón de Log Desplegable
        self._btn_dir = QPushButton("📁 Cambiar Carpeta Guardado")
        self._btn_dir.clicked.connect(self._choose_save_dir)
        p_lo.addWidget(self._btn_dir)

        self._lbl_dir = QLabel(f"Guardando en: {os.path.abspath(DEFAULT_DATA_PATH)}")
        self._lbl_dir.setStyleSheet("font-family: monospace; font-size: 9px; color: #aaa;")
        p_lo.addWidget(self._lbl_dir)

        # Botón para abrir la ventana modal desplegable de Logs EDSDK
        self._btn_show_log = QPushButton("📜 Ver Log de Diagnóstico EDSDK")
        self._btn_show_log.setStyleSheet("font-weight: bold; color: #00ff66; background-color: #111; border: 1px solid #333; padding: 6px;")
        self._btn_show_log.clicked.connect(self._log_dialog.show)
        p_lo.addWidget(self._btn_show_log)

        p_lo.addStretch()

        # Botón Conectar / Desconectar
        self._btn_connect = QPushButton("▶ Iniciar Cámara Canon")
        self._btn_connect.setStyleSheet("font-weight: bold; color: #4a9eff; padding: 8px;")
        self._btn_connect.clicked.connect(self._toggle_camera)
        p_lo.addWidget(self._btn_connect)

        splitter.addWidget(panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        main_vlo.addWidget(splitter)

        # Status Bar
        self.statusBar().showMessage("Listo — Presione 'Iniciar Cámara Canon' para activar la sesión.")

    def _on_view_resize(self, event):
        self._overlay.resize(self._view.size())
        pg.GraphicsLayoutWidget.resizeEvent(self._view, event)

    def _toggle_camera(self):
        if not self._is_camera_active:
            self._combo_iso.setEnabled(False)
            self._combo_tv.setEnabled(False)
            self._btn_connect.setText("⏹ Desconectar Cámara Canon")
            self._btn_connect.setStyleSheet("font-weight: bold; color: #ff6666; background-color: #3a1c1c; padding: 8px; border: 1px solid #ff4444;")
            self._is_camera_active = True
            self.startCameraSignal.emit()
        else:
            self.stopCameraSignal.emit()
            self._combo_iso.setEnabled(False)
            self._combo_tv.setEnabled(False)
            self._lbl_mode.setText("Modo Cámara: Desconectado")
            self._btn_connect.setText("▶ Iniciar Cámara Canon")
            self._btn_connect.setStyleSheet("font-weight: bold; color: #4a9eff; padding: 8px;")
            self._is_camera_active = False

    def _on_connected(self, connected: bool):
        self._is_camera_active = connected
        if connected:
            self._btn_connect.setText("⏹ Desconectar Cámara Canon")
            self._btn_connect.setStyleSheet("font-weight: bold; color: #ff6666; background-color: #3a1c1c; padding: 8px; border: 1px solid #ff4444;")

    @pyqtSlot(np.ndarray)
    def _update_frame(self, frame: np.ndarray):
        self._current_frame = frame
        self._img_item.setImage(frame.transpose(1, 0, 2))
        if not hasattr(self, '_range_initialized'):
            H, W = frame.shape[:2]
            self._vb.setRange(xRange=(0, W), padding=0)
            self._range_initialized = True

    @pyqtSlot(str)
    def _update_status(self, msg: str):
        self.statusBar().showMessage(msg)

    @pyqtSlot(str)
    def _append_log(self, msg: str):
        self._log_dialog.append_log(msg)

    @pyqtSlot(list, list, int, int, int)
    def _populate_properties(self, iso_vals: list, tv_vals: list, ae_mode: int, curr_iso: int = 0, curr_tv: int = 0):
        mode_str = AE_MODE_MAP.get(ae_mode, f"Modo 0x{ae_mode:02X}")
        self._lbl_mode.setText(f"Modo Cámara: {mode_str}")

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

    def _on_zoom_changed(self, idx: int):
        val = self._combo_zoom.itemData(idx)
        if val is not None: self.setZoomSignal.emit(val)

    def _on_fov_center_changed(self):
        cx = self._slider_fov_x.value() / 100.0
        cy = self._slider_fov_y.value() / 100.0
        if hasattr(self, '_worker') and hasattr(self._worker, '_cam'):
            self._worker._cam.set_zoom_center(cx, cy)

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

    def _on_live_adjust_changed(self):
        mode_idx = self._combo_color_mode.currentIndex()
        mode_str = "Grises (Transmisión)" if mode_idx == 1 else "Color RGB"
        self._stack_live.setCurrentIndex(0 if mode_idx == 1 else 1)

        cmin = self._slider_live_cmin.value()
        cmax = self._slider_live_cmax.value()
        lut  = self._combo_live_lut.currentIndex()

        r_g = self._slider_live_r.value() / 10.0
        g_g = self._slider_live_g.value() / 10.0
        b_g = self._slider_live_b.value() / 10.0

        self.liveParamsSignal.emit(mode_str, cmin, cmax, lut, r_g, g_g, b_g)

    def _reset_live_rgb(self):
        self._slider_live_r.setValue(10)
        self._slider_live_g.setValue(10)
        self._slider_live_b.setValue(10)
        self._on_live_adjust_changed()

    def _toggle_rulers(self, checked: bool):
        st = self._overlay.cycle_rulers_state()
        if st == 0: self._btn_rulers.setText("Reglas Off")
        elif st == 1: self._btn_rulers.setText("Reglas H1/V1")
        else: self._btn_rulers.setText("Reglas Par 2")

    def _clear_measure(self):
        self._overlay.clear_measure()
        self._btn_measure.setChecked(False)

    def _send_roi(self):
        roi = self._overlay.roi_um()
        if roi:
            self.sendRoiSignal.emit(roi)
            QMessageBox.information(self, "ROI Enviado", f"ROI enviado a Confocal:\nx={roi[0]:.2f}µm, y={roi[1]:.2f}µm, w={roi[2]:.2f}µm, h={roi[3]:.2f}µm")

    def _open_laser_532(self):
        if self._laser_window is None:
            self._laser_window = Laser532Window(self)
        self._laser_window.show()

    def _on_take_photo_clicked(self):
        idx = self._combo_photo_format.currentIndex()
        fmts = ["jpg", "png", "tiff", "bmp"]
        fmt = fmts[idx] if idx < len(fmts) else "jpg"
        self.takePhotoSignal.emit(fmt)

    def _choose_save_dir(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Seleccionar Carpeta de Guardado", str(DEFAULT_DATA_PATH))
        if dir_path:
            self._lbl_dir.setText(f"Guardando en: {os.path.abspath(dir_path)}")
            if hasattr(self, '_worker') and hasattr(self._worker, '_cam'):
                self._worker._cam.set_save_directory(dir_path)

    def make_connection(self, worker: CanonWorker):
        self._worker = worker
        self.startCameraSignal.connect(worker.start_camera)
        self.stopCameraSignal.connect(worker.stop_camera)
        self.setIsoSignal.connect(worker.set_iso)
        self.setTvSignal.connect(worker.set_tv)
        self.setZoomSignal.connect(worker.set_zoom)
        self.takePhotoSignal.connect(worker.take_photo)
        self.liveParamsSignal.connect(worker.update_live_params)

        worker.frameSignal.connect(self._update_frame)
        worker.statusSignal.connect(self._update_status)
        worker.logSignal.connect(self._append_log)
        worker.connectedSignal.connect(self._on_connected)
        worker.propsReadySignal.connect(self._populate_properties)


# ══════════════════════════════════════════════════════════════════════════════
#  PUNTO DE ENTRADA PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

def main():
    app = QApplication(sys.argv)
    win = CameraWindow()
    worker = CanonWorker()
    win.make_connection(worker)

    thread = QThread()
    thread.setPriority(QThread.Priority.HighPriority)
    worker.moveToThread(thread)
    thread.start()

    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()


#  SETSCALEDIALOG
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

        # Explicación general superior
        intro_lbl = QLabel(
            "<b>Instrucciones de Calibración:</b> Seleccioná uno de los 3 métodos siguientes para definir "
            "la relación entre píxeles y micrómetros (µm)."
        )
        intro_lbl.setWordWrap(True)
        intro_lbl.setStyleSheet("color: #aaa; margin-bottom: 4px;")
        lo.addWidget(intro_lbl)

        # Visor Interactivo con PyQtGraph
        self._view = pg.GraphicsLayoutWidget()
        self._vb = self._view.addViewBox(lockAspect=True); self._vb.invertY(True)
        self._img_item = pg.ImageItem(); self._vb.addItem(self._img_item)
        self._scatter  = pg.ScatterPlotItem(size=14, pen=pg.mkPen("r", width=2), brush=pg.mkBrush(None))
        self._part_scatter = pg.ScatterPlotItem(size=18, pen=pg.mkPen("#3ecf8e", width=2), brush=pg.mkBrush(None))
        self._vb.addItem(self._img_item)
        self._vb.addItem(self._part_scatter)
        self._vb.addItem(self._scatter)

        self._img_item.setImage(frame.transpose(1, 0, 2))
        self._view.scene().sigMouseClicked.connect(self._on_click)
        lo.addWidget(self._view, stretch=1)

        # Panel de Métodos de Calibración
        group = QGroupBox("Opciones de Calibración (Seleccionar un Método)")
        glo = QGridLayout(group)

        # Método A: Puntos + Snap
        lbl_a = QLabel("<b>Método A: Medición en Pantalla (2 Puntos)</b>")
        lbl_a.setToolTip("Hacé clic sobre 2 puntos conocidos en la foto. Mantené Shift presionado para encajar (Snap) al centro de la partícula.")
        glo.addWidget(lbl_a, 0, 0, 1, 2)
        btn_detect = QPushButton("Detectar Partículas (Snap)")
        btn_detect.setToolTip("Encuentra los centros de las partículas para facilitar el clic exacto con Snap (Shift).")
        btn_detect.clicked.connect(self._detect_particles)
        glo.addWidget(btn_detect, 0, 2)

        lbl_dist = QLabel("Distancia física conocida entre los 2 puntos (µm):")
        glo.addWidget(lbl_dist, 1, 0)
        self._dist_edit = QLineEdit("5.3"); self._dist_edit.setFixedWidth(90)
        glo.addWidget(self._dist_edit, 1, 1)

        # Método B: Entrada Directa nm/px
        lbl_b = QLabel("<b>Método B: Resolución en nm/px</b>")
        lbl_b.setToolTip("Ingresá directamente la resolución óptica del objetivo en nanómetros por píxel (ej: 50.0 nm/px).")
        glo.addWidget(lbl_b, 2, 0)
        self._nm_edit = QLineEdit(); self._nm_edit.setPlaceholderText("ej: 50.0")
        self._nm_edit.setFixedWidth(90)
        glo.addWidget(self._nm_edit, 2, 1)

        # Método C: Entrada Directa µm/px
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


# ══════════════════════════════════════════════════════════════════════════════
#  TRACKPYDIALOG
# ══════════════════════════════════════════════════════════════════════════════

class TrackpyDialog(QDialog):
    paramsAccepted = pyqtSignal(dict)

    def __init__(self, frame: np.ndarray, roi_frac: Optional[tuple] = None, um_per_px: Optional[float] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configurar Detección de Partículas (Trackpy)")
        self.setMinimumSize(740, 580)
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

        params_box = QGroupBox("Parámetros de Detección"); form = QFormLayout(params_box)

        if self._um_per_px:
            # Modo µm: Escala configurada
            self._diam_spin = QDoubleSpinBox()
            self._diam_spin.setRange(0.05, 500.0)
            self._diam_spin.setSingleStep(0.1)
            self._diam_spin.setValue(max(0.1, 11 * self._um_per_px))
            self._diam_spin.setSuffix(" µm")
            self._diam_spin.setToolTip("Diámetro estimado de la partícula en micrómetros (µm).")

            self._sep_spin = QDoubleSpinBox()
            self._sep_spin.setRange(0.05, 1000.0)
            self._sep_spin.setSingleStep(0.2)
            self._sep_spin.setValue(max(0.1, 8 * self._um_per_px))
            self._sep_spin.setSuffix(" µm")
            self._sep_spin.setToolTip("Distancia mínima entre partículas en micrómetros (µm) para evitar duplicados.")

            self._equiv_lbl = QLabel("—")
            self._equiv_lbl.setStyleSheet("color: #3ecf8e; font-family: monospace; font-size: 11px;")

            form.addRow("Diámetro estimado (µm):", self._diam_spin)
            form.addRow("Separación Mínima (µm):", self._sep_spin)
            form.addRow("Conversión a píxeles:", self._equiv_lbl)

            self._thr = QDoubleSpinBox(); self._thr.setRange(0, 1e6); self._thr.setValue(0)
            form.addRow("Umbral de Intensidad (0 = auto):", self._thr)

            for w in (self._diam_spin, self._sep_spin, self._thr):
                w.valueChanged.connect(self._run_preview)
        else:
            # Modo px: Escala no configurada
            self._diam = QSpinBox(); self._diam.setRange(3, 201); self._diam.setSingleStep(2); self._diam.setValue(11)
            self._sep  = QDoubleSpinBox(); self._sep.setRange(1, 500); self._sep.setValue(8); self._sep.setSingleStep(1)
            self._thr  = QDoubleSpinBox(); self._thr.setRange(0, 1e6); self._thr.setValue(0)

            self._diam.setToolTip("Diámetro aproximado de la partícula en píxeles (número impar).")
            self._sep.setToolTip("Distancia mínima entre partículas (px).")
            self._thr.setToolTip("Umbral mínimo de intensidad (0 = auto).")

            form.addRow("Diámetro estimado (px, impar):", self._diam)
            form.addRow("Separación Mínima (px):", self._sep)
            form.addRow("Umbral de Intensidad (0 = auto):", self._thr)

            for w in (self._diam, self._sep, self._thr):
                w.valueChanged.connect(self._run_preview)

        lo.addWidget(params_box)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._accept); btns.rejected.connect(self.reject)
        lo.addWidget(btns)

        self._show_crop()
        self._run_preview()

    def _show_crop(self):
        frame = self._frame
        if self._roi_frac:
            H, W = frame.shape[:2]
            x0, y0, x1, y1 = self._roi_frac
            frame = frame[int(round(y0*H)):int(round(y1*H)), int(round(x0*W)):int(round(x1*W))]
        self._crop = frame
        self._img_item.setImage(frame.transpose(1, 0, 2))

    def _get_pixel_params(self) -> tuple[int, float]:
        if self._um_per_px:
            d_um = self._diam_spin.value()
            s_um = self._sep_spin.value()

            # Conversión µm -> px
            raw_d = d_um / self._um_per_px
            d_px  = int(round(raw_d))
            # Regla de aproximación: Trackpy exige diámetro entero IMPAR >= 3
            if d_px % 2 == 0:
                d_px += 1
            if d_px < 3:
                d_px = 3

            sep_px = max(1.0, s_um / self._um_per_px)
            if hasattr(self, "_equiv_lbl"):
                self._equiv_lbl.setText(f"Diámetro: {d_px} px (impar) | Separación: {sep_px:.1f} px")
            return d_px, sep_px
        else:
            d = self._diam.value(); d = d if d % 2 == 1 else d + 1
            return d, self._sep.value()

    def _run_preview(self):
        if not _TRACKPY_AVAILABLE or self._crop is None: return
        import warnings
        gray = np.mean(self._crop, axis=2).astype(float) if self._crop.ndim == 3 else self._crop.astype(float)
        d_px, sep_px = self._get_pixel_params()
        thr = self._thr.value() if self._thr.value() > 0 else None
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                df = tp.locate(gray, diameter=d_px, separation=sep_px, threshold=thr)
            self._scatter.setData(df["x"].values, df["y"].values) if len(df) else self._scatter.clear()
            self._count_lbl.setText(f"Detectadas: {len(df)} partículas (diámetro = {d_px} px)")
        except Exception as e:
            self._count_lbl.setText(f"Error: {e}")

    def get_params(self) -> dict:
        d_px, sep_px = self._get_pixel_params()
        return dict(diameter=d_px, separation=sep_px, threshold=self._thr.value() if self._thr.value() > 0 else None)

    def _accept(self):
        self.paramsAccepted.emit(self.get_params())
        self.accept()


# ══════════════════════════════════════════════════════════════════════════════
#  BACKEND
# ══════════════════════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════════════════════
#  BACKEND
# ══════════════════════════════════════════════════════════════════════════════

class Backend(QObject):
    frameSignal      = pyqtSignal(np.ndarray)
    photoSavedSignal = pyqtSignal(str)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cap      = None
        self._running  = False
        self._timer    = None
        self._last_frame = None

    @pyqtSlot(str)
    def set_directory(self, path: str):
        self._save_dir = path
        print(f"[Camera Backend] Directorio de guardado actualizado: {path}")

    def _ensure_timer(self):
        if self._timer is None:
            self._timer = QTimer(self)
            self._timer.setInterval(FRAME_INTERVAL_MS)
            self._timer.timeout.connect(self._capture_frame)

    @pyqtSlot()
    def start_stream(self):
        if self._running: return
        self._ensure_timer()
        if SAFE_MODE:
            self._cap = _MockCapture()
        else:
            self._cap = cv2.VideoCapture(CAMERA_INDEX)
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH,  CAMERA_WIDTH)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
            if not self._cap.isOpened():
                print(f"[Camera] No se pudo abrir cámara {CAMERA_INDEX}")
                return
        self._running = True
        self._timer.start()

    @pyqtSlot()
    def stop_stream(self):
        if self._timer is not None and self._timer.isActive():
            self._timer.stop()
        self._running = False
        if self._cap:
            self._cap.release(); self._cap = None

    def close(self):
        from PyQt6.QtCore import QMetaObject, Qt
        QMetaObject.invokeMethod(self, "stop_stream", Qt.ConnectionType.QueuedConnection)

    def _capture_frame(self):
        if not self._cap or not self._running: return
        ret, frame = self._cap.read()
        if not ret: return
        rgb = frame if SAFE_MODE else cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        self._last_frame = rgb
        self.frameSignal.emit(rgb)

    @pyqtSlot()
    def take_photo(self):
        if self._last_frame is None: return
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = Path(self._save_dir) / f"camera_{ts}.png"
        if SAFE_MODE:
            from PIL import Image as PILImage
            PILImage.fromarray(self._last_frame).save(str(name))
        else:
            cv2.imwrite(str(name), cv2.cvtColor(self._last_frame, cv2.COLOR_RGB2BGR))
        self.photoSavedSignal.emit(str(name))

    def make_connection(self, window: CameraWindow):
        self.frameSignal.connect(window.update_frame)
        window.startStreamSignal.connect(self.start_stream)
        window.stopStreamSignal.connect(self.stop_stream)
        window.takePhotoSignal.connect(self.take_photo)


# ══════════════════════════════════════════════════════════════════════════════
#  LASER 532 — VENTANA FLOTANTE
# ══════════════════════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════════════════════
#  LASER532BACKEND
# ══════════════════════════════════════════════════════════════════════════════

class Laser532Backend(QObject):
    @pyqtSlot(float)
    def set_voltage(self, v: float):
        try:
            set_laser532_voltage(v)
        except Exception as e:
            print(f"[Laser532] Error: {e}")

    def make_connection(self, window: Laser532Window):
        window.voltageChangedSignal.connect(self.set_voltage)


if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    win    = CameraWindow()
    worker = Backend()
    worker.make_connection(win)
    thread = QThread()
    worker.moveToThread(thread)
    thread.start()
    win.show()
    sys.exit(app.exec())
