# -*- coding: utf-8 -*-
"""
camera.py — Ventana de cámara Canon EOS (ventana secundaria)
PyPrinting — UNSAM Nanofotónica  —  PyQt6

Arquitectura:
  CameraWindow   → ventana secundaria QMainWindow (Tools → Cámara)
  OverlayWidget  → capas SVG sobre el viewfinder (transparent, sin bloquear eventos)
  ZoomWindow     → sub-ventana flotante con ROI ampliado
  SetScaleDialog → calibración µm/px con trackpy
  TrackpyDialog  → configuración de parámetros de detección
  ROIConfirmDialog → confirmación de ROI→Confocal con validación 100×100µm
  Backend        → corre en cameraThread; QTimer 33ms + ThreadPoolExecutor

Guards de estado:
  scale_set  → habilita Reglas H/V, Medir, Zoom
  ref_set    → habilita ROI → Confocal
  roi_active → la detección se restringe al ROI dibujado

Requisitos extra: trackpy, scipy, numpy, cv2, Pillow
"""
from __future__ import annotations

import math
import time
import concurrent.futures
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np

import pyqtgraph as pg
from PyQt6.QtCore    import (Qt, QObject, QThread, QTimer, QRectF,
                              pyqtSignal, pyqtSlot, QMetaObject, Q_ARG,
                              QPoint, QPointF, QSize)
from PyQt6.QtWidgets import (QApplication, QMainWindow, QFrame, QWidget,
                              QGridLayout, QHBoxLayout, QVBoxLayout,
                              QLabel, QLineEdit, QPushButton, QCheckBox,
                              QDoubleSpinBox, QSlider, QSpinBox,
                              QTableWidget, QTableWidgetItem, QHeaderView,
                              QDialog, QDialogButtonBox, QFormLayout,
                              QGroupBox, QMessageBox, QSizePolicy,
                              QScrollArea, QSplitter, QComboBox)
from PyQt6.QtGui     import (QPainter, QPen, QColor, QFont, QPixmap,
                              QImage, QKeySequence, QAction)

from config import (SAFE_MODE, CAMERA_INDEX, CAMERA_WIDTH, CAMERA_HEIGHT,
                    PIXEL_SIZE_UM, LASER_532_V_MIN, LASER_532_V_MAX,
                    DEFAULT_DATA_PATH, PI_AXES)
from nidaq import set_laser532_voltage

if not SAFE_MODE:
    import cv2

# Trackpy: opcional pero requerido para Detectar y Set Scale
try:
    import trackpy as tp
    import pandas as pd
    _TRACKPY_AVAILABLE = True
except ImportError:
    _TRACKPY_AVAILABLE = False
    print("[Camera] trackpy no disponible — detección deshabilitada.")

FRAME_INTERVAL_MS = 33   # ~30 FPS
PI_STAGE_RANGE_UM = 100.0  # rango total de la platina en X e Y


# ══════════════════════════════════════════════════════════════════════════════
#  MOCK CAPTURE
# ══════════════════════════════════════════════════════════════════════════════

class _MockCapture:
    _n = 0
    def isOpened(self): return True
    def release(self):  pass
    def set(self, *a):  pass
    def read(self):
        self._n += 1
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
#  OVERLAY WIDGET
# ══════════════════════════════════════════════════════════════════════════════

class OverlayWidget(QWidget):
    """Capa transparente sobre el viewfinder — dibuja todos los elementos gráficos."""

    pointClickedSignal = pyqtSignal(float, float)   # coordenadas en fracción (0-1)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)

        # Estado
        self._scale_set   = False     # µm/px calibrado
        self._um_per_px   = PIXEL_SIZE_UM

        self._ref_pos: Optional[tuple] = None        # (fx, fy) en fracciones
        self._particles: list[tuple]   = []          # [(fx, fy, mass), ...]
        self._measure_pts: list        = []          # 0..2 (fx, fy)
        self._roi_rect: Optional[tuple]= None        # (fx0,fy0,fx1,fy1)
        self._zoom_rect: Optional[tuple]= None       # (fx0,fy0,fx1,fy1)

        self._ruler_h_frac = 0.5
        self._ruler_v_frac = 0.5
        self._show_rulers  = False

        self._drag_ruler = None        # 'h' | 'v' | None
        self._drag_roi   = False
        self._drag_zoom  = False
        self._roi_start  = None
        self._mode       = "none"      # "ref" | "measure" | "roi" | "zoom" | "scale" | "none"

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

    def set_particles(self, pts: list):
        self._particles = pts
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

    def set_zoom_rect(self, rect: Optional[tuple]):
        self._zoom_rect = rect
        self.update()

    def set_rulers(self, show: bool):
        self._show_rulers = show
        self.update()

    def roi_fractions(self) -> Optional[tuple]:
        if self._roi_rect is None:
            return None
        x0, y0, x1, y1 = self._roi_rect
        return (min(x0,x1), min(y0,y1), max(x0,x1), max(y0,y1))

    def roi_um(self, img_w_px: int, img_h_px: int) -> Optional[tuple]:
        r = self.roi_fractions()
        if r is None:
            return None
        x0, y0, x1, y1 = r
        return (x0*img_w_px*self._um_per_px, y0*img_h_px*self._um_per_px,
                (x1-x0)*img_w_px*self._um_per_px, (y1-y0)*img_h_px*self._um_per_px)

    def measure_distance_angle(self, img_w: int, img_h: int):
        if len(self._measure_pts) != 2:
            return None
        (fx1, fy1), (fx2, fy2) = self._measure_pts
        dx = (fx2 - fx1) * img_w * self._um_per_px
        dy = (fy2 - fy1) * img_h * self._um_per_px
        return math.hypot(dx, dy), math.degrees(math.atan2(dy, dx))

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()

        if self._show_rulers and self._scale_set:
            self._draw_rulers(p, W, H)
        if self._ref_pos:
            self._draw_ref(p, W, H)
        if self._particles:
            self._draw_particles(p, W, H)
        if self._measure_pts and self._scale_set:
            self._draw_measure(p, W, H)
        if self._roi_rect:
            self._draw_roi(p, W, H)
        if self._zoom_rect:
            self._draw_zoom_box(p, W, H)

    def _draw_rulers(self, p, W, H):
        pen = QPen(QColor(245, 166, 35, 200), 1, Qt.PenStyle.DashLine)
        p.setPen(pen)
        hy = int(self._ruler_h_frac * H)
        vx = int(self._ruler_v_frac * W)
        p.drawLine(0, hy, W, hy)
        p.drawLine(vx, 0, vx, H)
        p.setPen(QPen(QColor(245, 166, 35, 230)))
        p.setFont(QFont("Monospace", 9))
        h_um = self._ruler_h_frac * H * self._um_per_px
        v_um = self._ruler_v_frac * W * self._um_per_px
        p.drawText(vx + 5, 16, f"{v_um:.2f} µm")
        p.drawText(5, hy - 5, f"{h_um:.2f} µm")

    def _draw_ref(self, p, W, H):
        fx, fy = self._ref_pos
        x, y   = int(fx * W), int(fy * H)
        r      = 14
        pen    = QPen(QColor(74, 158, 255, 230), 1.5)
        p.setPen(pen)
        p.drawEllipse(x-r, y-r, 2*r, 2*r)
        p.drawLine(x-r-6, y, x+r+6, y)
        p.drawLine(x, y-r-6, x, y+r+6)
        p.setFont(QFont("Monospace", 9))
        p.drawText(x + r + 4, y - 4, "ref")

    def _draw_particles(self, p, W, H):
        p.setPen(QPen(QColor(62, 207, 142, 210), 1.2))
        p.setFont(QFont("Monospace", 8))
        for i, (fx, fy, *_) in enumerate(self._particles):
            ix, iy = int(fx * W), int(fy * H)
            p.drawEllipse(ix-10, iy-10, 20, 20)
            p.drawText(ix + 12, iy - 3, str(i+1))

    def _draw_measure(self, p, W, H):
        pts  = self._measure_pts
        pen  = QPen(QColor(229, 83, 75, 230), 2)
        p.setPen(pen)
        p.setFont(QFont("Monospace", 9))
        for i, (fx, fy) in enumerate(pts):
            ix, iy = int(fx*W), int(fy*H)
            p.drawEllipse(ix-5, iy-5, 10, 10)
            p.drawText(ix+8, iy-4, str(i+1))
        if len(pts) == 2:
            (fx1,fy1),(fx2,fy2) = pts
            p1 = QPointF(fx1*W, fy1*H)
            p2 = QPointF(fx2*W, fy2*H)
            p.setPen(QPen(QColor(229,83,75,130), 1, Qt.PenStyle.DashLine))
            p.drawLine(p1, p2)
            dx = (fx2-fx1)*W*self._um_per_px
            dy = (fy2-fy1)*H*self._um_per_px
            d  = math.hypot(dx, dy)
            θ  = math.degrees(math.atan2(dy, dx))
            mx, my = int((fx1+fx2)*W/2), int((fy1+fy2)*H/2)
            p.setPen(QPen(QColor(245, 166, 35, 240)))
            p.drawText(mx+6, my-6, f"d={d:.3f}µm  θ={θ:.1f}°")

    def _draw_roi(self, p, W, H):
        x0,y0,x1,y1 = self._roi_rect
        rx = int(min(x0,x1)*W); ry = int(min(y0,y1)*H)
        rw = int(abs(x1-x0)*W); rh = int(abs(y1-y0)*H)
        p.setPen(QPen(QColor(139, 124, 248, 200), 1.2, Qt.PenStyle.DashLine))
        p.drawRect(rx, ry, rw, rh)
        p.setFont(QFont("Monospace", 8))
        p.setPen(QPen(QColor(139, 124, 248, 230)))
        p.drawText(rx+4, ry+14, "ROI")

    def _draw_zoom_box(self, p, W, H):
        x0,y0,x1,y1 = self._zoom_rect
        rx = int(min(x0,x1)*W); ry = int(min(y0,y1)*H)
        rw = int(abs(x1-x0)*W); rh = int(abs(y1-y0)*H)
        p.setPen(QPen(QColor(255, 200, 50, 220), 1.5, Qt.PenStyle.SolidLine))
        p.drawRect(rx, ry, rw, rh)
        p.setFont(QFont("Monospace", 8))
        p.setPen(QPen(QColor(255, 200, 50, 240)))
        p.drawText(rx+4, ry+14, "ZOOM")

    # ── Mouse ─────────────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        W, H = self.width(), self.height()
        x, y = event.position().x(), event.position().y()
        fx, fy = x/W, y/H

        # Arrastrar reglas si están activas y el cursor está cerca
        if self._show_rulers and self._scale_set:
            hy = int(self._ruler_h_frac * H)
            vx = int(self._ruler_v_frac * W)
            if abs(y - hy) < 8:
                self._drag_ruler = 'h'; return
            if abs(x - vx) < 8:
                self._drag_ruler = 'v'; return

        # Modos especiales
        if self._mode == "roi":
            self._roi_start = (fx, fy)
            self._drag_roi  = True
            return
        if self._mode == "zoom":
            self._roi_start = (fx, fy)
            self._drag_zoom = True
            return

        # En otros modos: emitir click
        self._drag_ruler = None
        self.pointClickedSignal.emit(fx, fy)

    def mouseMoveEvent(self, event):
        W, H = self.width(), self.height()
        x, y = event.position().x(), event.position().y()
        fx, fy = x/W, y/H

        if self._drag_ruler == 'h':
            self._ruler_h_frac = max(0.0, min(1.0, fy)); self.update()
        elif self._drag_ruler == 'v':
            self._ruler_v_frac = max(0.0, min(1.0, fx)); self.update()
        elif self._drag_roi and self._roi_start:
            self._roi_rect = (*self._roi_start, fx, fy); self.update()
        elif self._drag_zoom and self._roi_start:
            self._zoom_rect = (*self._roi_start, fx, fy); self.update()

    def mouseReleaseEvent(self, _event):
        self._drag_ruler = None
        if self._drag_roi:
            self._drag_roi = False
            self._mode     = "none"
        if self._drag_zoom:
            self._drag_zoom = False
            self._mode      = "none"


# ══════════════════════════════════════════════════════════════════════════════
#  ZOOM WINDOW
# ══════════════════════════════════════════════════════════════════════════════

class ZoomWindow(QWidget):
    """Muestra el ROI de zoom ampliado con overlay a escala."""

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Tool)
        self.setWindowTitle("Zoom")
        self.setMinimumSize(320, 240)
        self.resize(480, 360)
        lo = QVBoxLayout(self)
        lo.setContentsMargins(4, 4, 4, 4)

        self._view = pg.GraphicsLayoutWidget()
        vb = self._view.addViewBox(lockAspect=True)
        vb.invertY(True)
        self._img  = pg.ImageItem()
        vb.addItem(self._img)
        lo.addWidget(self._view)

        self._info = QLabel("")
        self._info.setStyleSheet("font-family: monospace; font-size: 11px;")
        lo.addWidget(self._info)

        self._um_per_px = PIXEL_SIZE_UM
        self._zoom_factor = 1.0

    def update_frame(self, frame: np.ndarray, roi_frac: tuple, um_per_px: float):
        if frame is None:
            return
        self._um_per_px = um_per_px
        H, W = frame.shape[:2]
        x0, y0, x1, y1 = roi_frac
        px0 = int(min(x0,x1)*W); px1 = int(max(x0,x1)*W)
        py0 = int(min(y0,y1)*H); py1 = int(max(y0,y1)*H)
        if px1 <= px0 or py1 <= py0:
            return
        crop = frame[py0:py1, px0:px1]
        self._img.setImage(crop.transpose(1, 0, 2))
        w_um = (px1-px0) * um_per_px
        h_um = (py1-py0) * um_per_px
        self._zoom_factor = (px1-px0)
        self._info.setText(
            f"ROI: {px1-px0}×{py1-py0} px  |  {w_um:.2f}×{h_um:.2f} µm  "
            f"|  escala: {um_per_px:.4f} µm/px")


# ══════════════════════════════════════════════════════════════════════════════
#  SET SCALE DIALOG
# ══════════════════════════════════════════════════════════════════════════════

class SetScaleDialog(QDialog):
    """
    Calibración µm/px usando dos puntos sobre la imagen actual.
    Flujo:
      1. Muestra el frame (o ROI) en un visor interno.
      2. El usuario hace click en punto 1 y punto 2.
      3. El usuario escribe la distancia conocida en µm.
      4. Se calcula µm/px y se acepta.
    """

    scaleAccepted = pyqtSignal(float)   # emite µm/px

    def __init__(self, frame: np.ndarray, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Calibrar escala (Set Scale)")
        self.setMinimumSize(640, 540)
        self._frame    = frame
        self._pts      = []        # [(px, py), ...]  coordenadas en imagen original
        self._um_per_px = None

        lo = QVBoxLayout(self)
        lo.setContentsMargins(8, 8, 8, 8)

        # Instrucciones
        instr = QLabel(
            "1. Hacé click en dos puntos cuya distancia real conocés.\n"
            "2. Ingresá la distancia en µm.\n"
            "3. Aceptá para calibrar.")
        instr.setStyleSheet("font-size: 12px; padding: 4px;")
        lo.addWidget(instr)

        # Visor de imagen
        self._view = pg.GraphicsLayoutWidget()
        self._view.setMinimumHeight(340)
        vb = self._view.addViewBox(lockAspect=True)
        vb.invertY(True)
        self._img_item = pg.ImageItem()
        vb.addItem(self._img_item)
        self._scatter  = pg.ScatterPlotItem(size=14, pen=pg.mkPen("r", width=2),
                                             brush=pg.mkBrush(None))
        vb.addItem(self._scatter)
        self._img_item.setImage(frame.transpose(1, 0, 2))
        self._view.scene().sigMouseClicked.connect(self._on_click)
        lo.addWidget(self._view, stretch=1)

        # Distancia conocida
        dist_row = QWidget()
        dist_lo  = QHBoxLayout(dist_row)
        dist_lo.setContentsMargins(0, 0, 0, 0)
        dist_lo.addWidget(QLabel("Distancia conocida (µm):"))
        self._dist_edit = QDoubleSpinBox()
        self._dist_edit.setRange(0.001, 10000.0)
        self._dist_edit.setDecimals(4)
        self._dist_edit.setSuffix(" µm")
        self._dist_edit.setValue(5.0)
        dist_lo.addWidget(self._dist_edit)
        self._result_lbl = QLabel("—  (necesitás 2 puntos)")
        self._result_lbl.setStyleSheet("font-family: monospace; color: orange;")
        dist_lo.addWidget(self._result_lbl)
        lo.addWidget(dist_row)

        self._dist_edit.valueChanged.connect(self._update_result)

        # Botones
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._accept)
        btns.rejected.connect(self.reject)
        self._ok_btn = btns.button(QDialogButtonBox.StandardButton.Ok)
        self._ok_btn.setEnabled(False)
        lo.addWidget(btns)

        # Botón limpiar puntos
        clear_btn = QPushButton("Limpiar puntos")
        clear_btn.clicked.connect(self._clear_pts)
        lo.addWidget(clear_btn)

    def _on_click(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = self._img_item.mapFromScene(event.scenePos())
        H, W = self._frame.shape[:2]
        px, py = int(pos.x()), int(pos.y())
        if not (0 <= px < W and 0 <= py < H):
            return
        self._pts.append((px, py))
        if len(self._pts) > 2:
            self._pts = self._pts[-2:]
        self._scatter.setData(
            [p[0] for p in self._pts],
            [p[1] for p in self._pts])
        self._update_result()

    def _clear_pts(self):
        self._pts = []
        self._scatter.clear()
        self._result_lbl.setText("—  (necesitás 2 puntos)")
        self._ok_btn.setEnabled(False)

    def _update_result(self):
        if len(self._pts) < 2:
            return
        (px1, py1), (px2, py2) = self._pts[-2], self._pts[-1]
        dist_px = math.hypot(px2-px1, py2-py1)
        if dist_px < 1:
            return
        known_um  = self._dist_edit.value()
        um_per_px = known_um / dist_px
        self._um_per_px = um_per_px
        self._result_lbl.setText(
            f"Distancia: {dist_px:.1f} px  →  {um_per_px:.5f} µm/px  "
            f"({1/um_per_px:.1f} px/µm)")
        self._result_lbl.setStyleSheet("font-family: monospace; color: #3ecf8e;")
        self._ok_btn.setEnabled(True)

    def _accept(self):
        if self._um_per_px is not None:
            self.scaleAccepted.emit(self._um_per_px)
        self.accept()


# ══════════════════════════════════════════════════════════════════════════════
#  TRACKPY CONFIG DIALOG
# ══════════════════════════════════════════════════════════════════════════════

class TrackpyDialog(QDialog):
    """
    Configura y previsualiza la detección con trackpy.
    Parámetros: diameter, minmass, separation, threshold, percentile, max_iterations.
    Preview en tiempo real sobre el frame (o ROI) actual.
    """

    paramsAccepted = pyqtSignal(dict)   # emite dict con parámetros elegidos

    def __init__(self, frame: np.ndarray, roi_frac: Optional[tuple] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configurar detección trackpy")
        self.setMinimumSize(700, 560)
        self._frame    = frame
        self._roi_frac = roi_frac
        self._last_df  = None

        lo = QVBoxLayout(self)
        lo.setContentsMargins(8, 8, 8, 8)

        if not _TRACKPY_AVAILABLE:
            lo.addWidget(QLabel("⚠ trackpy no instalado. Ejecutá: pip install trackpy"))
            lo.addWidget(QDialogButtonBox(QDialogButtonBox.StandardButton.Close))
            return

        # Visor + overlay
        self._view = pg.GraphicsLayoutWidget()
        self._view.setMinimumHeight(300)
        vb = self._view.addViewBox(lockAspect=True)
        vb.invertY(True)
        self._img_item = pg.ImageItem()
        vb.addItem(self._img_item)
        self._scatter  = pg.ScatterPlotItem(
            size=18, pen=pg.mkPen("#3ecf8e", width=2), brush=pg.mkBrush(None))
        vb.addItem(self._scatter)
        lo.addWidget(self._view, stretch=1)

        self._count_lbl = QLabel("Detectadas: —")
        self._count_lbl.setStyleSheet("font-family: monospace; font-size: 12px;")
        lo.addWidget(self._count_lbl)

        # Parámetros
        params_box = QGroupBox("Parámetros trackpy")
        form = QFormLayout(params_box)

        self._diam   = QSpinBox();  self._diam.setRange(3, 201); self._diam.setSingleStep(2); self._diam.setValue(11)
        self._minm   = QDoubleSpinBox(); self._minm.setRange(0, 1e9); self._minm.setValue(100); self._minm.setDecimals(1)
        self._sep    = QDoubleSpinBox(); self._sep.setRange(1, 500); self._sep.setValue(8); self._sep.setDecimals(1)
        self._thr    = QDoubleSpinBox(); self._thr.setRange(0, 1); self._thr.setValue(0.1); self._thr.setDecimals(3); self._thr.setSingleStep(0.01)
        self._perc   = QDoubleSpinBox(); self._perc.setRange(0, 100); self._perc.setValue(64); self._perc.setDecimals(1)
        self._maxiter= QSpinBox();  self._maxiter.setRange(1, 100); self._maxiter.setValue(10)

        form.addRow("diameter (px, impar):", self._diam)
        form.addRow("minmass:", self._minm)
        form.addRow("separation (px):", self._sep)
        form.addRow("threshold:", self._thr)
        form.addRow("percentile:", self._perc)
        form.addRow("max_iterations:", self._maxiter)

        for w in (self._diam, self._minm, self._sep, self._thr, self._perc, self._maxiter):
            w.valueChanged.connect(self._run_preview)

        lo.addWidget(params_box)

        # Botones
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._accept)
        btns.rejected.connect(self.reject)
        lo.addWidget(btns)

        self._show_crop()
        self._run_preview()

    def _show_crop(self):
        frame = self._frame
        if self._roi_frac:
            H, W = frame.shape[:2]
            x0, y0, x1, y1 = self._roi_frac
            frame = frame[int(min(y0,y1)*H):int(max(y0,y1)*H),
                          int(min(x0,x1)*W):int(max(x0,x1)*W)]
        self._crop = frame
        self._img_item.setImage(frame.transpose(1, 0, 2))

    def _run_preview(self):
        if not _TRACKPY_AVAILABLE or self._crop is None:
            return
        import warnings
        gray = np.mean(self._crop, axis=2) if self._crop.ndim == 3 else self._crop
        diam = self._diam.value()
        if diam % 2 == 0: diam += 1
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                df = tp.locate(gray, diameter=diam,
                               minmass=self._minm.value(),
                               separation=self._sep.value(),
                               threshold=self._thr.value() if self._thr.value() > 0 else None,
                               percentile=self._perc.value(),
                               max_iterations=self._maxiter.value())
            self._last_df = df
            if len(df):
                self._scatter.setData(df["x"].values, df["y"].values)
            else:
                self._scatter.clear()
            self._count_lbl.setText(f"Detectadas: {len(df)}")
        except Exception as e:
            self._scatter.clear()
            self._count_lbl.setText(f"Error: {e}")

    def get_params(self) -> dict:
        d = self._diam.value()
        if d % 2 == 0: d += 1
        return dict(diameter=d, minmass=self._minm.value(),
                    separation=self._sep.value(),
                    threshold=self._thr.value() if self._thr.value() > 0 else None,
                    percentile=self._perc.value(),
                    max_iterations=self._maxiter.value())

    def _accept(self):
        self.paramsAccepted.emit(self.get_params())
        self.accept()


# ══════════════════════════════════════════════════════════════════════════════
#  ROI → CONFOCAL CONFIRM DIALOG
# ══════════════════════════════════════════════════════════════════════════════

class ROIConfirmDialog(QDialog):
    """
    Muestra el ROI seleccionado en µm, calcula el movimiento respecto
    de la referencia y valida que el destino esté dentro del rango
    100×100 µm de la platina. Pide confirmación antes de enviar.
    """

    confirmed = pyqtSignal(float, float, float, float)  # cx, cy, w, h en µm

    def __init__(self, roi_um: tuple, ref_um: tuple, parent=None):
        """
        roi_um  : (x_origin_um, y_origin_um, w_um, h_um) desde esquina sup-izq de imagen
        ref_um  : (xref, yref) posición de platina al fijar la referencia
        """
        super().__init__(parent)
        self.setWindowTitle("ROI → Confocal — Confirmar movimiento")
        self.setMinimumWidth(420)

        x0, y0, w, h = roi_um
        cx_img = x0 + w/2   # centro del ROI en coordenadas de imagen
        cy_img = y0 + h/2

        xref, yref = ref_um
        # Δ desde la referencia (platina) al centro del ROI
        # Signos: en cámara +X es derecha; en platina +X es derecha también.
        # La diferencia es el desplazamiento que hay que aplicar.
        dx = cx_img - x0        # simplificado: posición absoluta en imagen
        dy = cy_img - y0
        # Coordenadas absolutas en platina:
        cx_plat = xref + (cx_img - 0)   # se recalcula en backend, aquí solo display
        cy_plat = yref + (cy_img - 0)

        # Validación: ¿el ROI completo cabe dentro del rango 0–100?
        ok_x = 0 <= cx_img <= PI_STAGE_RANGE_UM
        ok_y = 0 <= cy_img <= PI_STAGE_RANGE_UM
        ok   = ok_x and ok_y

        lo = QVBoxLayout(self)
        lo.setContentsMargins(12, 12, 12, 12)
        lo.setSpacing(8)

        def row(label, value, color=None):
            lbl = QLabel(f"<b>{label}</b>  {value}")
            lbl.setTextFormat(Qt.TextFormat.RichText)
            if color:
                lbl.setStyleSheet(f"color: {color};")
            lo.addWidget(lbl)

        row("ROI origen (imagen):", f"({x0:.2f}, {y0:.2f}) µm")
        row("ROI tamaño:", f"{w:.2f} × {h:.2f} µm")
        row("Centro ROI (imagen):", f"({cx_img:.2f}, {cy_img:.2f}) µm")
        row("Referencia platina:", f"({xref:.3f}, {yref:.3f}) µm")

        range_lbl = QLabel(
            f"<b>Rango platina:</b>  0 – {PI_STAGE_RANGE_UM:.0f} µm  ×  "
            f"0 – {PI_STAGE_RANGE_UM:.0f} µm")
        range_lbl.setTextFormat(Qt.TextFormat.RichText)
        lo.addWidget(range_lbl)

        if ok:
            status = QLabel("✓ Destino dentro del rango de la platina.")
            status.setStyleSheet("color: #3ecf8e; font-weight: bold;")
        else:
            status = QLabel(
                "⚠ El destino está fuera del rango de la platina (0–100 µm).\n"
                "Revisá la referencia y el ROI antes de continuar.")
            status.setStyleSheet("color: #e5534b; font-weight: bold;")
        lo.addWidget(status)

        self._roi_um = (cx_img, cy_img, w, h)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._confirm)
        btns.rejected.connect(self.reject)
        if not ok:
            btns.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        lo.addWidget(btns)

    def _confirm(self):
        self.confirmed.emit(*self._roi_um)
        self.accept()


# ══════════════════════════════════════════════════════════════════════════════
#  CAMERA FRONTEND  (ventana secundaria completa)
# ══════════════════════════════════════════════════════════════════════════════

class CameraWindow(QMainWindow):
    """
    Ventana secundaria completa de la cámara.
    Se abre desde Tools → Cámara en la ventana principal.
    """

    # Señales hacia app.py / Backend
    setReferenceSignal   = pyqtSignal(float, float)    # fx, fy (fracción)
    roiToConfocalSignal  = pyqtSignal(float, float, float, float)  # cx,cy,w,h µm
    scaleChangedSignal   = pyqtSignal(float)            # µm/px
    directorySignal      = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cámara — Canon EOS")
        self.setMinimumSize(700, 580)
        self.resize(900, 680)

        # Estado
        self._scale_set   = False
        self._ref_set     = False
        self._um_per_px   = PIXEL_SIZE_UM
        self._ref_frac    = (0.5, 0.5)
        self._ref_pos_um  = (0.0, 0.0)
        self._current_frame: Optional[np.ndarray] = None
        self._particles: list = []
        self._trackpy_params  = dict(diameter=11, minmass=100, separation=8,
                                      percentile=64, max_iterations=10)
        self._measure_pts: list = []
        self._measure_mode = False

        self._zoom_window: Optional[ZoomWindow] = None

        central = QWidget()
        self.setCentralWidget(central)
        main_lo = QVBoxLayout(central)
        main_lo.setContentsMargins(4, 4, 4, 4)
        main_lo.setSpacing(4)

        # ── Viewfinder ────────────────────────────────────────────────────────
        self._view = pg.GraphicsLayoutWidget()
        self._view.setMinimumSize(480, 320)
        vb = self._view.addViewBox(lockAspect=True)
        vb.invertY(True)
        self._img_item = pg.ImageItem()
        vb.addItem(self._img_item)

        self._overlay = OverlayWidget(self._view)
        self._overlay.resize(self._view.size())
        self._view.resizeEvent  = self._on_view_resize
        self._overlay.pointClickedSignal.connect(self._on_overlay_click)

        main_lo.addWidget(self._view, stretch=4)

        # ── Toolbar ───────────────────────────────────────────────────────────
        tb = QWidget()
        tb_lo = QHBoxLayout(tb)
        tb_lo.setContentsMargins(2, 2, 2, 2)
        tb_lo.setSpacing(4)

        self._btn_live    = self._mkbtn("▶  Live",        checkable=True)
        self._btn_photo   = self._mkbtn("Foto")
        self._btn_setref  = self._mkbtn("Set ref.",       checkable=True, color="#4a9eff")
        self._btn_setscale= self._mkbtn("Set scale",      color="#f5a623")
        self._btn_rulers  = self._mkbtn("Reglas H/V",     checkable=True, color="#f5a623")
        self._btn_medir   = self._mkbtn("Medir",          checkable=True, color="#e5534b")
        self._btn_clear   = self._mkbtn("Limpiar")
        self._btn_roi     = self._mkbtn("ROI detect",     checkable=True, color="#8b7cf8")
        self._btn_detect  = self._mkbtn("Detectar",       color="#3ecf8e")
        self._btn_zoom    = self._mkbtn("Zoom ROI",       checkable=True, color="#ffc832")
        self._btn_confocal= self._mkbtn("→ Confocal",     color="#8b7cf8")

        self._btn_live.clicked.connect(self._toggle_live)
        self._btn_photo.clicked.connect(self._take_photo)
        self._btn_setref.clicked.connect(self._start_set_ref)
        self._btn_setscale.clicked.connect(self._open_set_scale)
        self._btn_rulers.clicked.connect(self._toggle_rulers)
        self._btn_medir.clicked.connect(self._toggle_measure)
        self._btn_clear.clicked.connect(self._clear_measure)
        self._btn_roi.clicked.connect(self._toggle_roi_mode)
        self._btn_detect.clicked.connect(self._open_trackpy_dialog)
        self._btn_zoom.clicked.connect(self._toggle_zoom_mode)
        self._btn_confocal.clicked.connect(self._send_roi_to_confocal)

        for w in (self._btn_live, self._btn_photo, self._btn_setref,
                  self._btn_setscale, self._btn_rulers, self._btn_medir,
                  self._btn_clear, self._btn_roi, self._btn_detect,
                  self._btn_zoom, self._btn_confocal):
            tb_lo.addWidget(w)
        tb_lo.addStretch()

        main_lo.addWidget(tb, stretch=0)

        # ── Barra de estado / resultado ───────────────────────────────────────
        status_row = QWidget()
        sr_lo      = QHBoxLayout(status_row)
        sr_lo.setContentsMargins(2, 0, 2, 0)
        self._lbl_scale  = QLabel("Escala: no calibrada")
        self._lbl_scale.setStyleSheet("color: #e5534b; font-family: monospace; font-size: 11px;")
        self._lbl_result = QLabel("—")
        self._lbl_result.setStyleSheet("font-family: monospace; font-size: 11px;")
        sr_lo.addWidget(self._lbl_scale)
        sr_lo.addStretch()
        sr_lo.addWidget(self._lbl_result)
        main_lo.addWidget(status_row, stretch=0)

        # ── Tabla de partículas ───────────────────────────────────────────────
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["#", "x (µm)", "y (µm)", "masa"])
        self._table.setMaximumHeight(100)
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        main_lo.addWidget(self._table, stretch=0)

        self._update_guards()

    # ── Helpers ───────────────────────────────────────────────────────────────

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

    def _update_guards(self):
        """Habilita/deshabilita botones según el estado de calibración y referencia."""
        self._btn_rulers.setEnabled(self._scale_set)
        self._btn_medir.setEnabled(self._scale_set)
        self._btn_zoom.setEnabled(self._scale_set)
        self._btn_confocal.setEnabled(self._ref_set)
        if not self._scale_set:
            self._btn_rulers.setToolTip("Requiere calibración de escala (Set scale)")
            self._btn_medir.setToolTip("Requiere calibración de escala (Set scale)")
            self._btn_zoom.setToolTip("Requiere calibración de escala (Set scale)")

    # ── Live / Foto ───────────────────────────────────────────────────────────

    def _toggle_live(self, checked: bool):
        self._btn_live.setText("⏹  Stop" if checked else "▶  Live")

    def _take_photo(self):
        """Slot conectado al Backend vía señal."""
        pass  # emitido desde Backend.take_photo()

    # ── Set Reference ─────────────────────────────────────────────────────────

    def _start_set_ref(self, checked: bool):
        if checked:
            self._overlay.set_mode("ref")
            self._btn_setref.setText("Click en imagen...")
        else:
            self._overlay.set_mode("none")
            self._btn_setref.setText("Set ref.")

    def _on_overlay_click(self, fx: float, fy: float):
        mode = self._overlay._mode

        if mode == "ref":
            self._ref_frac = (fx, fy)
            self._ref_set  = True
            self._overlay.set_ref(fx, fy)
            self._overlay.set_mode("none")
            self._btn_setref.setChecked(False)
            self._btn_setref.setText("Set ref.")
            self.setReferenceSignal.emit(fx, fy)
            self._update_guards()
            return

        if self._measure_mode and self._scale_set:
            self._measure_pts.append((fx, fy))
            if len(self._measure_pts) > 2:
                self._measure_pts = self._measure_pts[-2:]
            self._overlay.set_measure_points(self._measure_pts)
            if len(self._measure_pts) == 2 and self._current_frame is not None:
                H, W = self._current_frame.shape[:2]
                result = self._overlay.measure_distance_angle(W, H)
                if result:
                    d, θ = result
                    self._lbl_result.setText(
                        f"Distancia: {d:.4f} µm   |   Ángulo: {θ:.2f}°")

    # ── Set Scale ─────────────────────────────────────────────────────────────

    def _open_set_scale(self):
        if self._current_frame is None:
            QMessageBox.warning(self, "Set Scale",
                "Activá el stream (Live) y esperá un frame antes de calibrar.")
            return
        # Usar el ROI de detección si está activo, si no la imagen completa
        frame = self._get_roi_frame()
        dlg = SetScaleDialog(frame, parent=self)
        dlg.scaleAccepted.connect(self._on_scale_accepted)
        dlg.exec()

    def _on_scale_accepted(self, um_per_px: float):
        self._um_per_px = um_per_px
        self._scale_set = True
        self._overlay.set_scale(um_per_px)
        self._lbl_scale.setText(f"Escala: {um_per_px:.5f} µm/px  "
                                f"({1/um_per_px:.2f} px/µm)")
        self._lbl_scale.setStyleSheet(
            "color: #3ecf8e; font-family: monospace; font-size: 11px;")
        self.scaleChangedSignal.emit(um_per_px)
        self._update_guards()

    # ── Reglas / Medir / Limpiar ──────────────────────────────────────────────

    def _toggle_rulers(self, checked: bool):
        self._overlay.set_rulers(checked)

    def _toggle_measure(self, checked: bool):
        self._measure_mode = checked
        if not checked:
            self._clear_measure()

    def _clear_measure(self):
        self._measure_pts = []
        self._overlay.clear_measure()
        self._lbl_result.setText("—")
        self._btn_medir.setChecked(False)
        self._measure_mode = False

    # ── ROI de detección ──────────────────────────────────────────────────────

    def _toggle_roi_mode(self, checked: bool):
        if checked:
            self._overlay.set_mode("roi")
            self._overlay.clear_roi()
        else:
            self._overlay.set_mode("none")
            if not self._btn_roi.isChecked():
                self._overlay.clear_roi()

    def _get_roi_frame(self) -> np.ndarray:
        """Recorta el frame al ROI activo, o devuelve el frame completo."""
        frame = self._current_frame
        if frame is None:
            return np.zeros((240, 320, 3), dtype=np.uint8)
        roi = self._overlay.roi_fractions()
        if roi is None:
            return frame
        H, W = frame.shape[:2]
        x0, y0, x1, y1 = roi
        return frame[int(y0*H):int(y1*H), int(x0*W):int(x1*W)]

    # ── Detectar (trackpy) ────────────────────────────────────────────────────

    def _open_trackpy_dialog(self):
        if self._current_frame is None:
            QMessageBox.warning(self, "Detectar",
                "Activá el stream (Live) antes de detectar.")
            return
        roi = self._overlay.roi_fractions()
        dlg = TrackpyDialog(self._current_frame.copy(), roi_frac=roi, parent=self)
        dlg.paramsAccepted.connect(self._on_trackpy_params)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._run_detection()

    def _on_trackpy_params(self, params: dict):
        self._trackpy_params = params

    def _run_detection(self):
        if not _TRACKPY_AVAILABLE or self._current_frame is None:
            return
        import warnings
        frame      = self._current_frame
        roi        = self._overlay.roi_fractions()
        H, W       = frame.shape[:2]

        if roi:
            x0, y0, x1, y1 = roi
            ix0 = int(x0*W); ix1 = int(x1*W)
            iy0 = int(y0*H); iy1 = int(y1*H)
            crop = frame[iy0:iy1, ix0:ix1]
            offset = (ix0, iy0)
        else:
            crop  = frame
            offset = (0, 0)

        gray = np.mean(crop, axis=2) if crop.ndim == 3 else crop.astype(float)
        p    = self._trackpy_params.copy()
        d    = p.pop("diameter"); d = d if d % 2 == 1 else d + 1

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                df = tp.locate(gray, diameter=d, **p)
        except Exception as e:
            QMessageBox.warning(self, "Detección fallida", str(e))
            return

        # Convertir a fracciones globales de la imagen
        pts = []
        self._table.setRowCount(len(df))
        for i, row in df.iterrows():
            gx = (row["x"] + offset[0]) / W
            gy = (row["y"] + offset[1]) / H
            pts.append((gx, gy, row.get("mass", 0)))
            x_um = gx * W * self._um_per_px
            y_um = gy * H * self._um_per_px
            self._table.setItem(i, 0, QTableWidgetItem(str(i+1)))
            self._table.setItem(i, 1, QTableWidgetItem(f"{x_um:.3f}"))
            self._table.setItem(i, 2, QTableWidgetItem(f"{y_um:.3f}"))
            self._table.setItem(i, 3, QTableWidgetItem(f"{row.get('mass',0):.1f}"))

        self._particles = pts
        self._overlay.set_particles(pts)

    # ── Zoom ──────────────────────────────────────────────────────────────────

    def _toggle_zoom_mode(self, checked: bool):
        if not self._scale_set:
            self._btn_zoom.setChecked(False)
            return
        if checked:
            self._overlay.set_mode("zoom")
            self._overlay.set_zoom_rect(None)
        else:
            self._overlay.set_mode("none")
            if self._overlay._zoom_rect and self._current_frame is not None:
                self._open_zoom_window()

    def _open_zoom_window(self):
        if self._zoom_window is None:
            self._zoom_window = ZoomWindow(parent=self)
        zr = self._overlay._zoom_rect
        if zr and self._current_frame is not None:
            self._zoom_window.update_frame(
                self._current_frame, zr, self._um_per_px)
        self._zoom_window.show()
        self._zoom_window.raise_()

    # ── ROI → Confocal ────────────────────────────────────────────────────────

    def _send_roi_to_confocal(self):
        if not self._ref_set:
            QMessageBox.warning(self, "ROI → Confocal",
                "Primero fijá la referencia con Set ref.")
            return
        if self._current_frame is None:
            return
        H, W = self._current_frame.shape[:2]
        roi_um = self._overlay.roi_um(W, H)
        if roi_um is None:
            QMessageBox.warning(self, "ROI → Confocal",
                "Dibujá un ROI primero (botón ROI detect y arrastrar).")
            return

        dlg = ROIConfirmDialog(roi_um, self._ref_pos_um, parent=self)
        dlg.confirmed.connect(self.roiToConfocalSignal)
        dlg.exec()

    # ── Actualización de frame desde Backend ───────────────────────────────────

    @pyqtSlot(np.ndarray)
    def update_frame(self, frame: np.ndarray):
        self._current_frame = frame
        self._img_item.setImage(frame.transpose(1, 0, 2))
        # Si el zoom está abierto, actualizar
        if (self._zoom_window is not None and
                self._zoom_window.isVisible() and
                self._overlay._zoom_rect):
            self._zoom_window.update_frame(
                frame, self._overlay._zoom_rect, self._um_per_px)

    @pyqtSlot(float, float)
    def update_cursor(self, fx: float, fy: float):
        """Actualiza la cruz de cursor (posición de platina en imagen)."""
        # No actualiza _ref_frac, solo mueve el cursor visual
        # La cruz de referencia queda fija en _ref_frac
        pass   # La referencia ya está en overlay; el cursor de platina
               # podría mostrarse como un segundo símbolo si se desea.
               # Por ahora la posición de la platina se refleja solo cuando
               # el usuario hace Set ref. explícitamente.

    @pyqtSlot(list)
    def set_ref_pos_um(self, pos: list):
        """Recibe [x, y, z] µm de la platina cuando se fija la referencia."""
        self._ref_pos_um = (pos[0], pos[1])

    def make_connection(self, backend: 'Backend'):
        backend.frameSignal.connect(self.update_frame)
        self._btn_live.clicked.connect(
            lambda checked: (backend.start_stream if checked else backend.stop_stream)())
        self._btn_photo.clicked.connect(backend.take_photo)


# ══════════════════════════════════════════════════════════════════════════════
#  BACKEND
# ══════════════════════════════════════════════════════════════════════════════

class Backend(QObject):
    """Corre en cameraThread. QTimer 33ms para captura."""

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
        self._save_dir   = str(DEFAULT_DATA_PATH)

    @pyqtSlot()
    def start_stream(self):
        if self._running:
            return
        if SAFE_MODE:
            self._cap = _MockCapture()
        else:
            self._cap = cv2.VideoCapture(CAMERA_INDEX)
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH,  CAMERA_WIDTH)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
            if not self._cap.isOpened():
                print(f"[Camera] No se pudo abrir índice {CAMERA_INDEX}.")
                return
        self._running = True
        self._timer.start()
        print(f"[Camera] Stream {'(MOCK) ' if SAFE_MODE else ''}iniciado.")

    @pyqtSlot()
    def stop_stream(self):
        self._timer.stop()
        self._running = False
        if self._cap:
            self._cap.release()
            self._cap = None

    def _capture_frame(self):
        if not self._cap or not self._running:
            return
        ret, frame = self._cap.read()
        if not ret:
            return
        rgb = frame if SAFE_MODE else cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        self._last_frame = rgb
        self.frameSignal.emit(rgb)

    @pyqtSlot()
    def take_photo(self):
        if self._last_frame is None:
            return
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = Path(self._save_dir) / f"camera_{ts}.png"
        if SAFE_MODE:
            from PIL import Image as PILImage
            PILImage.fromarray(self._last_frame).save(str(name))
        else:
            cv2.imwrite(str(name),
                        cv2.cvtColor(self._last_frame, cv2.COLOR_RGB2BGR))
        print(f"[Camera] Foto: {name}")
        self.photoSavedSignal.emit(str(name))

    @pyqtSlot(str)
    def set_directory(self, path: str):
        self._save_dir = path

    def close(self):
        self.stop_stream()

    def make_connection(self, window: CameraWindow):
        window.directorySignal.connect(self.set_directory)


# ══════════════════════════════════════════════════════════════════════════════
#  LASER 532 — VENTANA FLOTANTE (sin cambios respecto a versión anterior)
# ══════════════════════════════════════════════════════════════════════════════

class Laser532Window(QWidget):
    voltageChangedSignal = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Láser 532 nm — Dev1/ao2")
        self.setWindowFlags(
            Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.setFixedSize(420, 180)
        lo = QVBoxLayout(self)
        lbl = QLabel("Láser 532 nm  —  Dev1/ao2")
        lbl.setStyleSheet("font-weight: bold; color: #55cc55;")
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
        btn_off = QPushButton(f"Apagar ({LASER_532_V_MIN:.1f} V mínimo)")
        btn_off.setStyleSheet("color: #cc4444;")
        btn_off.clicked.connect(lambda: self._spin.setValue(LASER_532_V_MIN))
        lo.addWidget(btn_off)

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
if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    win    = CameraWindow()
    worker = Backend()
    worker.make_connection(win)
    win.make_connection(worker)
    thread = QThread()
    worker.moveToThread(thread)
    thread.start()
    win.show()
    sys.exit(app.exec())
