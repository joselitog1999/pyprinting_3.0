# -*- coding: utf-8 -*-
"""
camera.py — Ventana de cámara y análisis de imágenes
PyPrinting — UNSAM Nanofotónica  —  PyQt6

Mapeo de coordenadas para Confocal:
  - Cámara Hacia la DERECHA = Platina +Y
  - Cámara Hacia ABAJO   = Platina +X
  - Rango físico platina PI: 0.0 a 100.0 µm
"""
from __future__ import annotations

import math
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

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
                               QInputDialog, QSplitter)
from PyQt6.QtGui     import (QPainter, QPen, QColor, QFont, QPixmap, QImage)

from config import (SAFE_MODE, CAMERA_INDEX, CAMERA_WIDTH, CAMERA_HEIGHT,
                    PIXEL_SIZE_UM, LASER_532_V_MIN, LASER_532_V_MAX,
                    DEFAULT_DATA_PATH, PI_STAGE_RANGE_UM,
                    DEFAULT_TRACKPY_DIAMETER_PX, DEFAULT_TRACKPY_MINMASS,
                    DEFAULT_TRACKPY_SEPARATION_PX)
from nidaq import set_laser532_voltage, open_shutter, close_shutter, SHUTTERS

if not SAFE_MODE:
    import cv2

try:
    import trackpy as tp
    import pandas as pd
    _TRACKPY_AVAILABLE = True
except ImportError:
    _TRACKPY_AVAILABLE = False
    print("[Camera] trackpy no disponible — detección deshabilitada.")

FRAME_INTERVAL_MS = 33   # ~30 FPS


# ══════════════════════════════════════════════════════════════════════════════
#  MOCK CAPTURE
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

        # Reglas Tri-estado: 0 = desactivadas, 1 = Par 1 (H1, V1), 2 = Par 2 (H1, V1 y H2, V2)
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
        self._zoom_level = max(1.0, min(4.0, level))
        if center is not None:
            self._zoom_center = center
        self._clamp_zoom_center()
        fx0, fy0, fx1, fy1 = self.viewport_bounds()
        self.zoomChangedSignal.emit(fx0, fy0, fx1, fy1)
        self.update()

    def zoom_in(self):
        if self._zoom_level < 2.0:
            self.set_zoom_level(2.0)
        elif self._zoom_level < 4.0:
            self.set_zoom_level(4.0)

    def zoom_out(self):
        if self._zoom_level > 2.0:
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
        self._drag_ruler = None
        if self._drag_roi:
            self._drag_roi = False
            self._mode     = "none"


# ══════════════════════════════════════════════════════════════════════════════
#  CAMERA FRONTEND  (Ventana Principal)
# ══════════════════════════════════════════════════════════════════════════════

class CameraWindow(QMainWindow):

    startStreamSignal   = pyqtSignal()
    stopStreamSignal    = pyqtSignal()
    takePhotoSignal     = pyqtSignal()
    setReferenceSignal  = pyqtSignal(float, float)     # fx, fy
    roiToConfocalSignal = pyqtSignal(float, float, float, float) # range_x, range_y, px_x, px_y
    scaleChangedSignal  = pyqtSignal(float)
    directorySignal     = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cámara Canon EOS — Análisis Óptico")
        self.setMinimumSize(950, 650)
        self.resize(1150, 720)

        # Estado
        self._scale_set   = False
        self._ref_set     = False
        self._um_per_px   = PIXEL_SIZE_UM
        self._ref_frac    = (0.5, 0.5)
        self._ref_pos_um  = (50.0, 50.0)
        self._current_frame: Optional[np.ndarray] = None
        self._particles: list[tuple[float, float, float]] = []
        self._saved_measures: list[dict] = []
        self._trackpy_params  = dict(diameter=DEFAULT_TRACKPY_DIAMETER_PX, minmass=DEFAULT_TRACKPY_MINMASS, separation=DEFAULT_TRACKPY_SEPARATION_PX, threshold=0)
        self._measure_pts: list = []
        self._measure_mode = False

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

        self._btn_live     = self._mkbtn("▶ Live", checkable=True)
        self._btn_photo    = self._mkbtn("Foto")
        self._btn_setref   = self._mkbtn("Set ref.", checkable=True, color="#4a9eff")
        self._btn_setscale = self._mkbtn("Set scale", color="#f5a623")
        self._btn_rulers   = self._mkbtn("Reglas (0)", color="#f5a623")
        self._btn_zoom_in  = self._mkbtn("Zoom +", color="#ffc832")
        self._btn_zoom_out = self._mkbtn("Zoom -", color="#ffc832")
        self._btn_home     = self._mkbtn("Home", color="#ffc832")
        self._btn_confocal = self._mkbtn("→ Confocal", color="#8b7cf8")
        self._btn_clear_all= self._mkbtn("Limpiar Todo", color="#e5534b")

        self._btn_live.clicked.connect(self._toggle_live)
        self._btn_photo.clicked.connect(self._take_photo)
        self._btn_setref.clicked.connect(self._start_set_ref)
        self._btn_setscale.clicked.connect(self._open_set_scale)
        self._btn_rulers.clicked.connect(self._cycle_rulers)
        self._btn_zoom_in.clicked.connect(lambda: self._overlay.zoom_in())
        self._btn_zoom_out.clicked.connect(lambda: self._overlay.zoom_out())
        self._btn_home.clicked.connect(lambda: self._overlay.zoom_home())
        self._btn_confocal.clicked.connect(self._send_roi_to_confocal)
        self._btn_clear_all.clicked.connect(self._global_clear_with_confirm)

        for w in (self._btn_live, self._btn_photo, self._btn_setref,
                  self._btn_setscale, self._btn_rulers, self._btn_zoom_in,
                  self._btn_zoom_out, self._btn_home, self._btn_confocal,
                  self._btn_clear_all):
            tb_lo.addWidget(w)

        tb_lo.addStretch()
        main_vlo.addWidget(tb, stretch=0)

        # ── Layout Central con Splitter ───────────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 1. Panel Izquierdo: Detección de Partículas y ROI
        left_panel = QGroupBox("Detección & ROI")
        left_lo    = QVBoxLayout(left_panel)
        left_lo.setContentsMargins(6, 6, 6, 6)

        self._btn_roi    = self._mkbtn("ROI detect", checkable=True, color="#8b7cf8")
        self._btn_detect = self._mkbtn("Detectar", color="#3ecf8e")
        self._btn_exp_part = self._mkbtn("Exportar Partículas (.txt)", color="#3ecf8e")
        self._btn_clear_particles = self._mkbtn("Limpiar Partículas")

        self._btn_roi.clicked.connect(self._toggle_roi_mode)
        self._btn_detect.clicked.connect(self._open_trackpy_dialog)
        self._btn_exp_part.clicked.connect(self._export_particles_txt)
        self._btn_clear_particles.clicked.connect(self._clear_particles)

        btn_row_left = QHBoxLayout()
        btn_row_left.addWidget(self._btn_roi)
        btn_row_left.addWidget(self._btn_detect)
        left_lo.addLayout(btn_row_left)

        self._table_particles = QTableWidget(0, 4)
        self._table_particles.setHorizontalHeaderLabels(["#", "x (µm)", "y (µm)", "Int."])
        self._table_particles.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table_particles.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        left_lo.addWidget(self._table_particles)

        btn_row_left2 = QHBoxLayout()
        btn_row_left2.addWidget(self._btn_exp_part)
        btn_row_left2.addWidget(self._btn_clear_particles)
        left_lo.addLayout(btn_row_left2)

        # 2. Visor Central de Cámara
        visor_container = QWidget()
        visor_lo        = QVBoxLayout(visor_container)
        visor_lo.setContentsMargins(0, 0, 0, 0)

        self._view = pg.GraphicsLayoutWidget()
        self._vb = self._view.addViewBox(lockAspect=True)
        self._vb.invertY(True)
        self._img_item = pg.ImageItem()
        self._vb.addItem(self._img_item)

        self._overlay = OverlayWidget(self._view)
        self._overlay.bind_views(self._view, self._img_item)
        self._overlay.resize(self._view.size())
        self._view.resizeEvent = self._on_view_resize
        self._overlay.pointClickedSignal.connect(self._on_overlay_click)
        self._overlay.zoomChangedSignal.connect(self._on_zoom_changed)
        visor_lo.addWidget(self._view)

        # 3. Panel Derecho: Mediciones
        right_panel = QGroupBox("Mediciones")
        right_lo    = QVBoxLayout(right_panel)
        right_lo.setContentsMargins(6, 6, 6, 6)

        self._btn_medir     = self._mkbtn("Medir", checkable=True, color="#e5534b")
        self._btn_save_meas = self._mkbtn("Guardar Medida", color="#3ecf8e")
        self._btn_exp_meas  = self._mkbtn("Exportar (.txt)", color="#4a9eff")
        self._btn_clr_meas  = self._mkbtn("Limpiar Lista")

        self._btn_medir.clicked.connect(self._toggle_measure)
        self._btn_save_meas.clicked.connect(self._save_current_measurement)
        self._btn_exp_meas.clicked.connect(self._export_measurements_txt)
        self._btn_clr_meas.clicked.connect(self._clear_measurements_list)

        btn_row_right = QHBoxLayout()
        btn_row_right.addWidget(self._btn_medir)
        btn_row_right.addWidget(self._btn_save_meas)
        right_lo.addLayout(btn_row_right)

        self._table_measures = QTableWidget(0, 4)
        self._table_measures.setHorizontalHeaderLabels(["#", "Dist (µm)", "Δx/Δy (px)", "Ángulo"])
        self._table_measures.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table_measures.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        right_lo.addWidget(self._table_measures)

        btn_row_right2 = QHBoxLayout()
        btn_row_right2.addWidget(self._btn_exp_meas)
        btn_row_right2.addWidget(self._btn_clr_meas)
        right_lo.addLayout(btn_row_right2)

        splitter.addWidget(left_panel)
        splitter.addWidget(visor_container)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 5)
        splitter.setStretchFactor(2, 2)

        main_vlo.addWidget(splitter, stretch=1)

        # ── Barra de Estado ───────────────────────────────────────────────────
        status_bar = QHBoxLayout()
        self._lbl_scale  = QLabel("Escala: no calibrada")
        self._lbl_scale.setStyleSheet("color: #e5534b; font-family: monospace; font-size: 11px;")
        self._lbl_result = QLabel("Shift: Activa Snap a partículas / referencia al medir")
        self._lbl_result.setStyleSheet("font-family: monospace; font-size: 11px; color: #aaa;")
        status_bar.addWidget(self._lbl_scale)
        status_bar.addStretch()
        status_bar.addWidget(self._lbl_result)
        main_vlo.addLayout(status_bar, stretch=0)

        self._update_guards()

    # ── Helpers UI ────────────────────────────────────────────────────────────

    def _mkbtn(self, text, checkable=False, color=None) -> QPushButton:
        b = QPushButton(text)
        b.setCheckable(checkable)
        if color:
            b.setStyleSheet(f"QPushButton {{ color: {color}; }}"
                            f"QPushButton:checked {{ background-color: {color}; color: #111; }}")
        return b

    def _on_view_resize(self, event):
        self._overlay.resize(self._view.size())
        pg.GraphicsLayoutWidget.resizeEvent(self._view, event)

    def _on_zoom_changed(self, fx0: float, fy0: float, fx1: float, fy1: float):
        W, H = self._overlay.get_img_dims()
        x0, x1 = fx0 * W, fx1 * W
        y0, y1 = fy0 * H, fy1 * H
        self._vb.setXRange(x0, x1, padding=0)
        self._vb.setYRange(y0, y1, padding=0)

    def _update_guards(self):
        scale_needed = self._scale_set and self._ref_set
        self._btn_confocal.setEnabled(scale_needed)

    # ── Stream y Foto ─────────────────────────────────────────────────────────

    def _toggle_live(self, checked: bool):
        self._btn_live.setText("⏹ Stop" if checked else "▶ Live")
        if checked: self.startStreamSignal.emit()
        else: self.stopStreamSignal.emit()

    def _take_photo(self):
        self.takePhotoSignal.emit()

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

        m = dict(index=len(self._saved_measures)+1, dist=dist_um, dx_px=dx_px, dy_px=dy_px, angle=angle,
                 p1=(fx1, fy1), p2=(fx2, fy2))
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
        path, _ = QFileDialog.getSaveFileName(self, "Guardar mediciones", str(DEFAULT_DATA_PATH / "mediciones.txt"), "Archivos Texto (*.txt)")
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
        path, _ = QFileDialog.getSaveFileName(self, "Guardar partículas detectadas", str(DEFAULT_DATA_PATH / "particulas_detectadas.txt"), "Archivos Texto (*.txt)")
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
        dlg = TrackpyDialog(self._current_frame.copy(), roi_frac=roi, parent=self)
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

    # ── Rediseño Completo de ROI → Confocal (CONVENCIÓN PLATINA EXCLUSIVA) ──────

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
                   f"Rango requerido X: [{x_min:.2f}, {x_max:.2f}] µm {'(OK)' if ok_x else '(EXCEDIDO)'}\n"
                   f"Rango requerido Y: [{y_min:.2f}, {y_max:.2f}] µm {'(OK)' if ok_y else '(EXCEDIDO)'}")
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

        print(f"[Camera -> Confocal] Target Stage: ({target_x_stage:.2f}, {target_y_stage:.2f}) µm | Range: ({range_x_um:.2f}, {range_y_um:.2f}) µm | Pixels: ({pixels_x}, {pixels_y})")
        self.roiToConfocalSignal.emit(range_x_um, range_y_um, float(pixels_x), float(pixels_y))

    # ── Actualización de Frame desde Backend ───────────────────────────────────

    @pyqtSlot(np.ndarray)
    def update_frame(self, frame: np.ndarray):
        self._current_frame = frame
        self._img_item.setImage(frame.transpose(1, 0, 2))

    @pyqtSlot(list)
    def set_ref_pos_um(self, pos: list):
        self._ref_pos_um = (pos[0], pos[1])

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
        self._lbl_scale.setStyleSheet("color: #3ecf8e; font-family: monospace; font-size: 11px;")
        self.scaleChangedSignal.emit(um_per_px)
        self._update_guards()


# ══════════════════════════════════════════════════════════════════════════════
#  SET SCALE DIALOG (3 Métodos: Puntos con Snap, nm/px directo, µm/px directo)
# ══════════════════════════════════════════════════════════════════════════════
#  SET SCALE DIALOG (3 Métodos con Explicación Detallada)
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

class Backend(QObject):
    frameSignal      = pyqtSignal(np.ndarray)
    photoSavedSignal = pyqtSignal(str)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cap      = None
        self._running  = False
        self._timer    = QTimer(self)
        self._timer.setInterval(FRAME_INTERVAL_MS)
        self._timer.timeout.connect(self._capture_frame)
        self._last_frame = None
    @pyqtSlot(str)
    def set_directory(self, path: str):
        self._save_dir = path
        print(f"[Camera Backend] Directorio de guardado actualizado: {path}")

    @pyqtSlot()
    def start_stream(self):
        if self._running: return
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
        self._timer.stop()
        self._running = False
        if self._cap:
            self._cap.release(); self._cap = None

    def close(self):
        self.stop_stream()

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

        # Botón de Shutter 532 nm (Abrir / Cerrar)
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
