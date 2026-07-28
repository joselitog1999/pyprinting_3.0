# -*- coding: utf-8 -*-
"""
camera.py — Cámara Canon EOS, cursor de platina y láser 532 nm
PyPrinting — UNSAM Nanofotónica  —  PyQt6

Funcionalidades:
  - Stream en tiempo real (Canon EOS vía cv2, ~30 FPS) en cameraThread
  - Overlay: reglas H/V arrastrables, cursor de platina, anillos de partículas,
    medición interactiva de distancia y ángulo entre dos puntos
  - Set referencia imagen ↔ platina (misma lógica que el Cursor_pp original)
  - Detección de partículas con PSF_pp (ThreadPoolExecutor, no bloquea el stream)
  - Captura de foto al directorio activo
  - ROI dibujable que se puede enviar a scan confocal
  - Ventana flotante Laser532Window para control de potencia ao2
  - Cursor_pp integrado: calcula posición del cursor en la imagen a partir de
    la posición de la platina (señal read_pos_signal de Nanopositioning)
"""
from __future__ import annotations

import math
import time
import concurrent.futures
from datetime import datetime
from pathlib import Path

import numpy as np

import pyqtgraph as pg
from PyQt6.QtCore    import (Qt, QObject, QThread, QTimer, QRectF,
                              pyqtSignal, pyqtSlot, QMetaObject, Q_ARG)
from PyQt6.QtWidgets import (QApplication, QFrame, QWidget, QGridLayout,
                              QHBoxLayout, QVBoxLayout, QLabel, QLineEdit,
                              QPushButton, QCheckBox, QDoubleSpinBox,
                              QSlider, QTableWidget, QTableWidgetItem,
                              QHeaderView, QSplitter, QSizePolicy)
from PyQt6.QtGui     import (QPainter, QPen, QColor, QFont, QAction,
                              QKeySequence)

from config import (SAFE_MODE, CAMERA_INDEX, CAMERA_WIDTH, CAMERA_HEIGHT,
                    PIXEL_SIZE_UM, LASER_532_V_MIN, LASER_532_V_MAX,
                    DEFAULT_DATA_PATH, pi)
from nidaq  import set_laser532_voltage

if not SAFE_MODE:
    import cv2


# ══════════════════════════════════════════════════════════════════════════════
#  MOCK CAPTURE  — misma interfaz que cv2.VideoCapture
# ══════════════════════════════════════════════════════════════════════════════

class _MockCapture:
    """
    Genera frames RGB sintéticos sin necesitar cv2 ni cámara física.
    Fondo gris con ruido, dos partículas brillantes que se mueven suavemente,
    y una cruz central que simula el punto del láser.
    """
    _frame_count = 0

    def isOpened(self) -> bool: return True
    def release(self):          pass
    def set(self, *a, **k):     pass

    def read(self):
        self._frame_count += 1
        W, H  = CAMERA_WIDTH, CAMERA_HEIGHT
        frame = (np.random.rand(H, W, 3) * 25 + 30).astype(np.uint8)
        t = self._frame_count * 0.04

        for cx, cy, r, col in [
            (int(W*0.38 + 4*np.sin(t)),     int(H*0.52 + 3*np.cos(t*0.7)),
             12, (180, 220, 255)),
            (int(W*0.61 + 3*np.sin(t*0.5)), int(H*0.38 + 4*np.cos(t*0.3)),
             9,  (140, 255, 200)),
        ]:
            ys, xs = np.ogrid[-cy:H-cy, -cx:W-cx]
            glow   = np.exp(-(xs*xs + ys*ys) / (2*(r*2)**2))
            for c, base in enumerate(col):
                frame[:, :, c] = np.clip(
                    frame[:, :, c] + (glow * base).astype(np.uint8), 0, 255)

        mx, my = W // 2, H // 2
        frame[my-1:my+2, mx-20:mx+20] = [255, 80, 80]
        frame[my-20:my+20, mx-1:mx+2] = [255, 80, 80]
        return True, frame

try:
    from psf import center_of_mass, find_two_centers
    _PSF_AVAILABLE = True
except ImportError:
    _PSF_AVAILABLE = False
    print("[Camera] psf.py no disponible — detección deshabilitada.")

FRAME_INTERVAL_MS = 33   # ~30 FPS


# ══════════════════════════════════════════════════════════════════════════════
#  OVERLAY WIDGET
# ══════════════════════════════════════════════════════════════════════════════

class OverlayWidget(QWidget):
    """Widget transparente superpuesto sobre el viewfinder."""

    pointClickedSignal = pyqtSignal(float, float)  # x_px, y_px en imagen

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)

        self._show_rulers   = False
        self._ruler_h_frac  = 0.5
        self._ruler_v_frac  = 0.5
        self._cursor_pos    = None       # (x_px, y_px)
        self._particles     = []         # [(x_px, y_px), ...]
        self._measure_pts   = []         # 0..2 puntos
        self._roi_rect      = None       # (x0, y0, x1, y1) en fracciones
        self._roi_start     = None
        self._drag_ruler    = None       # 'h' | 'v' | None
        self._drag_roi      = False

    # ── API ───────────────────────────────────────────────────────────────────

    def set_rulers(self, v: bool):       self._show_rulers = v; self.update()
    def set_cursor(self, x, y):         self._cursor_pos = (x, y); self.update()
    def set_particles(self, pts):       self._particles = pts; self.update()
    def set_measure_points(self, pts):  self._measure_pts = pts; self.update()
    def clear_measure(self):            self._measure_pts = []; self.update()
    def clear_roi(self):                self._roi_rect = None; self.update()

    def ruler_h_um(self) -> float:
        return self._ruler_h_frac * CAMERA_HEIGHT * PIXEL_SIZE_UM

    def ruler_v_um(self) -> float:
        return self._ruler_v_frac * CAMERA_WIDTH * PIXEL_SIZE_UM

    def roi_um(self) -> tuple | None:
        if self._roi_rect is None:
            return None
        x0, y0, x1, y1 = self._roi_rect
        W, H = self.width(), self.height()
        return (min(x0, x1)*W*PIXEL_SIZE_UM, min(y0, y1)*H*PIXEL_SIZE_UM,
                abs(x1-x0)*W*PIXEL_SIZE_UM, abs(y1-y0)*H*PIXEL_SIZE_UM)

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        if self._show_rulers:     self._draw_rulers(p, W, H)
        if self._cursor_pos:      self._draw_cursor(p)
        if self._particles:       self._draw_particles(p)
        if self._measure_pts:     self._draw_measure(p, W, H)
        if self._roi_rect:        self._draw_roi(p, W, H)

    def _draw_rulers(self, p, W, H):
        pen = QPen(QColor(245, 166, 35, 200), 1, Qt.PenStyle.DashLine)
        p.setPen(pen)
        hy = int(self._ruler_h_frac * H)
        vx = int(self._ruler_v_frac * W)
        p.drawLine(0, hy, W, hy)
        p.drawLine(vx, 0, vx, H)
        p.setPen(QPen(QColor(245, 166, 35, 220)))
        p.setFont(QFont("Monospace", 8))
        p.drawText(vx + 4, 14, f"{self.ruler_v_um():.1f} µm")
        p.drawText(4, hy - 4, f"{self.ruler_h_um():.1f} µm")

    def _draw_cursor(self, p):
        x, y = int(self._cursor_pos[0]), int(self._cursor_pos[1])
        pen = QPen(QColor(74, 158, 255, 220), 1)
        p.setPen(pen)
        r = 12
        p.drawEllipse(x-r, y-r, 2*r, 2*r)
        p.drawLine(x-r-5, y, x+r+5, y)
        p.drawLine(x, y-r-5, x, y+r+5)
        p.setFont(QFont("Monospace", 8))
        p.drawText(x + r + 3, y - 3, "ref")

    def _draw_particles(self, p):
        p.setPen(QPen(QColor(62, 207, 142, 200), 1))
        for (px, py) in self._particles:
            ix, iy = int(px), int(py)
            p.drawEllipse(ix-9, iy-9, 18, 18)

    def _draw_measure(self, p, W, H):
        pts = self._measure_pts
        p.setPen(QPen(QColor(229, 83, 75, 220), 2))
        for i, (px, py) in enumerate(pts):
            ix, iy = int(px), int(py)
            p.drawEllipse(ix-5, iy-5, 10, 10)
            p.setFont(QFont("Monospace", 8))
            p.drawText(ix+7, iy-3, str(i+1))
        if len(pts) == 2:
            p1, p2 = pts
            p.setPen(QPen(QColor(229, 83, 75, 150), 1, Qt.PenStyle.DashLine))
            p.drawLine(int(p1[0]), int(p1[1]), int(p2[0]), int(p2[1]))
            dx = (p2[0]-p1[0])*PIXEL_SIZE_UM
            dy = (p2[1]-p1[1])*PIXEL_SIZE_UM
            d  = math.hypot(dx, dy)
            θ  = math.degrees(math.atan2(dy, dx))
            mx, my = int((p1[0]+p2[0])/2), int((p1[1]+p2[1])/2)
            p.setPen(QPen(QColor(245, 166, 35, 230)))
            p.setFont(QFont("Monospace", 8))
            p.drawText(mx+5, my-5, f"d={d:.2f}µm  θ={θ:.1f}°")

    def _draw_roi(self, p, W, H):
        x0, y0, x1, y1 = self._roi_rect
        rect_px = (int(min(x0,x1)*W), int(min(y0,y1)*H),
                   int(abs(x1-x0)*W), int(abs(y1-y0)*H))
        p.setPen(QPen(QColor(139, 124, 248, 180), 1, Qt.PenStyle.DashLine))
        p.drawRect(*rect_px)
        p.setFont(QFont("Monospace", 8))
        p.setPen(QPen(QColor(139, 124, 248, 200)))
        p.drawText(rect_px[0]+4, rect_px[1]+12, "ROI → scan")

    # ── Mouse ─────────────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        W, H = self.width(), self.height()
        x, y = event.position().x(), event.position().y()

        if self._show_rulers:
            hy = int(self._ruler_h_frac * H)
            vx = int(self._ruler_v_frac * W)
            if abs(y - hy) < 8:
                self._drag_ruler = 'h'; return
            if abs(x - vx) < 8:
                self._drag_ruler = 'v'; return

        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self._roi_start   = (x/W, y/H)
            self._drag_roi    = True
            return

        self._drag_ruler = None
        self._drag_roi   = False
        self.pointClickedSignal.emit(float(x), float(y))

    def mouseMoveEvent(self, event):
        W, H = self.width(), self.height()
        x, y = event.position().x(), event.position().y()
        if self._drag_ruler == 'h':
            self._ruler_h_frac = max(0.0, min(1.0, y/H)); self.update()
        elif self._drag_ruler == 'v':
            self._ruler_v_frac = max(0.0, min(1.0, x/W)); self.update()
        elif self._drag_roi and self._roi_start:
            self._roi_rect = (*self._roi_start, x/W, y/H); self.update()

    def mouseReleaseEvent(self, event):
        self._drag_ruler = None
        self._drag_roi   = False


# ══════════════════════════════════════════════════════════════════════════════
#  FRONTEND
# ══════════════════════════════════════════════════════════════════════════════

class Frontend(QFrame):

    startStreamSignal   = pyqtSignal()
    stopStreamSignal    = pyqtSignal()
    takePhotoSignal     = pyqtSignal()
    detectSignal        = pyqtSignal(np.ndarray)
    setReferenceSignal  = pyqtSignal(float, float)   # x_px, y_px

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._current_frame: np.ndarray | None = None
        self._measure_pts: list = []
        self._measure_mode      = False
        self._ref_mode          = False
        self._setup_gui()

    # ── GUI ───────────────────────────────────────────────────────────────────

    def _setup_gui(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(4, 4, 4, 4)

        # Viewfinder
        self._view = pg.GraphicsLayoutWidget()
        self._view.setMinimumSize(480, 360)
        vb = self._view.addViewBox(row=0, col=0, lockAspect=True)
        vb.invertY(True)
        self._img_item = pg.ImageItem()
        vb.addItem(self._img_item)

        self._overlay = OverlayWidget(self._view)
        self._overlay.resize(self._view.size())
        self._view.resizeEvent = self._on_view_resize
        self._overlay.pointClickedSignal.connect(self._on_click)

        main.addWidget(self._view, stretch=4)

        # Toolbar
        tb = QWidget()
        tb_lo = QGridLayout(tb)
        tb_lo.setContentsMargins(2, 2, 2, 2)
        tb_lo.setSpacing(3)

        self._btn_stream  = QPushButton("▶  Live")
        self._btn_stream.setCheckable(True)
        self._btn_stream.clicked.connect(self._toggle_stream)

        self._btn_photo   = QPushButton("Foto")
        self._btn_photo.clicked.connect(self.takePhotoSignal)

        self._btn_rulers  = QPushButton("Reglas H/V")
        self._btn_rulers.setCheckable(True)
        self._btn_rulers.clicked.connect(lambda c: self._overlay.set_rulers(c))

        self._btn_measure = QPushButton("Medir")
        self._btn_measure.setCheckable(True)
        self._btn_measure.clicked.connect(self._toggle_measure)

        self._btn_clear   = QPushButton("Limpiar")
        self._btn_clear.clicked.connect(self._clear_measure)

        self._btn_detect  = QPushButton("Detectar")
        self._btn_detect.clicked.connect(self._request_detect)

        self._btn_ref     = QPushButton("Set ref.")
        self._btn_ref.setCheckable(True)
        self._btn_ref.setToolTip(
            "Activar y hacer click en la imagen para fijar la referencia\n"
            "entre la posición de la platina y el píxel de la imagen.")
        self._btn_ref.clicked.connect(lambda c: setattr(self, '_ref_mode', c))

        self._btn_roi     = QPushButton("ROI → Confocal")
        self._btn_roi.clicked.connect(self._send_roi)

        self._lbl_result  = QLabel("—")
        self._lbl_result.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        for col, w in enumerate([self._btn_stream, self._btn_photo,
                                  self._btn_rulers, self._btn_measure,
                                  self._btn_clear,  self._btn_detect,
                                  self._btn_ref,    self._btn_roi]):
            tb_lo.addWidget(w, 0, col)
        tb_lo.addWidget(self._lbl_result, 1, 0, 1, 8)

        main.addWidget(tb, stretch=0)

        # Tabla de partículas
        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["x (µm)", "y (µm)", "σ (px)"])
        self._table.setMaximumHeight(90)
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        main.addWidget(self._table, stretch=0)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _on_view_resize(self, event):
        self._overlay.resize(self._view.size())
        pg.GraphicsLayoutWidget.resizeEvent(self._view, event)

    def _toggle_stream(self, checked: bool):
        self._btn_stream.setText("⏹  Stop" if checked else "▶  Live")
        (self.startStreamSignal if checked else self.stopStreamSignal).emit()

    def _toggle_measure(self, checked: bool):
        self._measure_mode = checked
        if not checked:
            self._clear_measure()

    def _clear_measure(self):
        self._measure_pts = []
        self._overlay.clear_measure()
        self._lbl_result.setText("—")
        self._btn_measure.setChecked(False)
        self._measure_mode = False

    def _on_click(self, x: float, y: float):
        if self._ref_mode:
            self.setReferenceSignal.emit(x, y)
            self._btn_ref.setChecked(False)
            self._ref_mode = False
            return
        if self._measure_mode:
            self._measure_pts.append((x, y))
            if len(self._measure_pts) > 2:
                self._measure_pts = self._measure_pts[-2:]
            self._overlay.set_measure_points(self._measure_pts)
            if len(self._measure_pts) == 2:
                self._show_measurement()

    def _show_measurement(self):
        p1, p2 = self._measure_pts
        dx = (p2[0]-p1[0])*PIXEL_SIZE_UM
        dy = (p2[1]-p1[1])*PIXEL_SIZE_UM
        d  = math.hypot(dx, dy)
        θ  = math.degrees(math.atan2(dy, dx))
        self._lbl_result.setText(
            f"Distancia: {d:.3f} µm   |   Ángulo: {θ:.2f}°")

    def _request_detect(self):
        if self._current_frame is not None:
            self.detectSignal.emit(self._current_frame.copy())

    def _send_roi(self):
        roi = self._overlay.roi_um()
        if roi:
            print(f"[Camera] ROI → confocal: x={roi[0]:.2f}µm  y={roi[1]:.2f}µm  "
                  f"w={roi[2]:.2f}µm  h={roi[3]:.2f}µm")

    # ── Slots desde Backend ───────────────────────────────────────────────────

    @pyqtSlot(np.ndarray)
    def update_frame(self, frame: np.ndarray):
        self._current_frame = frame
        self._img_item.setImage(frame.transpose(1, 0, 2))

    @pyqtSlot(list)
    def show_particles(self, particles: list):
        self._overlay.set_particles([(p[0], p[1]) for p in particles])
        self._table.setRowCount(len(particles))
        for i, (px, py, sigma) in enumerate(particles):
            self._table.setItem(i, 0, QTableWidgetItem(f"{px*PIXEL_SIZE_UM:.3f}"))
            self._table.setItem(i, 1, QTableWidgetItem(f"{py*PIXEL_SIZE_UM:.3f}"))
            self._table.setItem(i, 2, QTableWidgetItem(f"{sigma:.2f}"))

    @pyqtSlot(float, float)
    def update_cursor(self, x_px: float, y_px: float):
        self._overlay.set_cursor(x_px, y_px)

    def make_connection(self, backend: 'Backend'):
        backend.frameSignal.connect(self.update_frame)
        backend.particlesSignal.connect(self.show_particles)
        backend.cursorPxSignal.connect(self.update_cursor)


# ══════════════════════════════════════════════════════════════════════════════
#  BACKEND
# ══════════════════════════════════════════════════════════════════════════════

class Backend(QObject):
    """Corre en cameraThread. QTimer a 33 ms para captura. ThreadPoolExecutor
    para detección puntual de partículas."""

    frameSignal      = pyqtSignal(np.ndarray)
    particlesSignal  = pyqtSignal(list)
    cursorPxSignal   = pyqtSignal(float, float)
    photoSavedSignal = pyqtSignal(str)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cap: cv2.VideoCapture | None = None
        self._running      = False
        self._timer        = QTimer(self)
        self._timer.setInterval(FRAME_INTERVAL_MS)
        self._timer.timeout.connect(self._capture_frame)
        self._executor     = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self._last_frame: np.ndarray | None = None
        self._save_dir     = DEFAULT_DATA_PATH

        # Referencia cámara ↔ platina (lógica ex-Cursor_pp)
        self._ref_set      = False
        self._ref_x_pos    = 0.0   # µm
        self._ref_y_pos    = 0.0
        self._ref_x_px     = 0.0
        self._ref_y_px     = 0.0

    # ── Stream ────────────────────────────────────────────────────────────────

    @pyqtSlot()
    def start_stream(self):
        if self._running:
            return
        if SAFE_MODE:
            self._cap     = _MockCapture()
            self._running = True
            self._timer.start()
            print("[Camera] Stream iniciado (MOCK).")
            return
        self._cap = cv2.VideoCapture(CAMERA_INDEX)
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH,  CAMERA_WIDTH)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
        if not self._cap.isOpened():
            print(f"[Camera] No se pudo abrir índice {CAMERA_INDEX}.")
            return
        self._running = True
        self._timer.start()
        print("[Camera] Stream iniciado.")

    @pyqtSlot()
    def stop_stream(self):
        self._timer.stop()
        self._running = False
        if self._cap:
            self._cap.release()
            self._cap = None
        print("[Camera] Stream detenido.")

    def _capture_frame(self):
        if not self._cap or not self._running:
            return
        ret, frame = self._cap.read()
        if not ret:
            return
        # _MockCapture ya devuelve RGB; cv2 devuelve BGR
        rgb = frame if SAFE_MODE else cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        self._last_frame = rgb
        self.frameSignal.emit(rgb)

    # ── Foto ─────────────────────────────────────────────────────────────────

    @pyqtSlot()
    def take_photo(self):
        if self._last_frame is None:
            return
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = Path(self._save_dir) / f"camera_{ts}.png"
        if SAFE_MODE:
            # Guardar como PNG con PIL sin necesitar cv2
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

    # ── Detección de partículas ───────────────────────────────────────────────

    @pyqtSlot(np.ndarray)
    def detect_particles(self, frame: np.ndarray):
        self._executor.submit(self._run_detection, frame)

    def _run_detection(self, frame: np.ndarray):
        if not _PSF_AVAILABLE:
            return
        gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY).astype(float)
        m = gray.max()
        if m > 0:
            gray /= m
        try:
            x1, y1, x2, y2 = find_two_centers(gray)
            results = [(float(x1), float(y1), 2.0), (float(x2), float(y2), 2.0)]
        except Exception:
            try:
                xo, yo = center_of_mass(gray)
                results = [(float(xo), float(yo), 2.0)]
            except Exception as e:
                print(f"[Camera] Detección fallida: {e}")
                results = []
        # Devolver al hilo Qt de forma segura
        QMetaObject.invokeMethod(
            self, "_emit_particles",
            Qt.ConnectionType.QueuedConnection,
            Q_ARG(object, results),
        )

    @pyqtSlot(object)
    def _emit_particles(self, results):
        self.particlesSignal.emit(results)

    # ── Cursor platina ↔ imagen ───────────────────────────────────────────────

    @pyqtSlot(float, float, float, float)
    def set_reference(self, x_px: float, y_px: float,
                      x_pos_um: float, y_pos_um: float):
        """Fija la correspondencia píxel ↔ µm."""
        self._ref_x_px  = x_px
        self._ref_y_px  = y_px
        self._ref_x_pos = x_pos_um
        self._ref_y_pos = y_pos_um
        self._ref_set   = True
        print(f"[Camera] Ref: px({x_px:.0f},{y_px:.0f}) ↔ "
              f"platina({x_pos_um:.3f},{y_pos_um:.3f})µm")

    @pyqtSlot(list)
    def update_cursor_from_pos(self, pos: list):
        """
        Slot conectado a nanopositioningWorker.read_pos_signal → [x,y,z].
        Convierte posición de platina en píxel de imagen (ex-Cursor_pp.real_cursor).
        """
        if not self._ref_set:
            return
        dx_um = pos[0] - self._ref_x_pos
        dy_um = pos[1] - self._ref_y_pos
        x_px  = self._ref_x_px - dx_um / PIXEL_SIZE_UM
        y_px  = self._ref_y_px + dy_um / PIXEL_SIZE_UM
        self.cursorPxSignal.emit(x_px, y_px)

    # ── Cierre ────────────────────────────────────────────────────────────────

    def close(self):
        self.stop_stream()
        self._executor.shutdown(wait=False)

    def make_connection(self, frontend: Frontend):
        frontend.startStreamSignal.connect(self.start_stream)
        frontend.stopStreamSignal.connect(self.stop_stream)
        frontend.takePhotoSignal.connect(self.take_photo)
        frontend.detectSignal.connect(self.detect_particles)


# ══════════════════════════════════════════════════════════════════════════════
#  LASER 532 — VENTANA FLOTANTE
# ══════════════════════════════════════════════════════════════════════════════

class Laser532Window(QWidget):
    """Ventana flotante independiente para controlar ao2 (láser 532 nm)."""

    voltageChangedSignal = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Láser 532 nm — Dev1/ao2")
        self.setWindowFlags(
            Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.setFixedSize(420, 180)
        self._setup_gui()

    def _setup_gui(self):
        lo = QVBoxLayout(self)

        lbl = QLabel("Láser 532 nm  —  Dev1/ao2")
        lbl.setStyleSheet("font-weight: bold; color: #55cc55;")
        lo.addWidget(lbl)

        row = QWidget()
        row_lo = QHBoxLayout(row)
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setMinimum(int(LASER_532_V_MIN * 100))
        self._slider.setMaximum(int(LASER_532_V_MAX * 100))
        self._slider.setValue(int(LASER_532_V_MIN * 100))
        self._slider.setTickInterval(50)
        self._slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._slider.valueChanged.connect(self._on_slider)

        self._spin = QDoubleSpinBox()
        self._spin.setRange(LASER_532_V_MIN, LASER_532_V_MAX)
        self._spin.setSingleStep(0.05)
        self._spin.setDecimals(3)
        self._spin.setSuffix(" V")
        self._spin.setValue(LASER_532_V_MIN)
        self._spin.valueChanged.connect(self._on_spin)

        row_lo.addWidget(QLabel("Potencia:"))
        row_lo.addWidget(self._slider, stretch=1)
        row_lo.addWidget(self._spin)
        lo.addWidget(row)

        # Presets rápidos
        presets = QWidget()
        presets_lo = QHBoxLayout(presets)
        for v in [1.0, 2.0, 3.0, 4.0, 5.0]:
            b = QPushButton(f"{v:.1f}V")
            b.clicked.connect(lambda _, val=v: self._spin.setValue(val))
            presets_lo.addWidget(b)
        lo.addWidget(presets)

        btn_off = QPushButton(f"Apagar ({LASER_532_V_MIN:.1f} V mínimo)")
        btn_off.setStyleSheet("color: #cc4444;")
        btn_off.clicked.connect(lambda: self._spin.setValue(LASER_532_V_MIN))
        lo.addWidget(btn_off)

    def _on_slider(self, val: int):
        v = val / 100.0
        self._spin.blockSignals(True)
        self._spin.setValue(v)
        self._spin.blockSignals(False)
        self.voltageChangedSignal.emit(v)

    def _on_spin(self, v: float):
        self._slider.blockSignals(True)
        self._slider.setValue(int(v * 100))
        self._slider.blockSignals(False)
        self.voltageChangedSignal.emit(v)


class Laser532Backend(QObject):
    """Backend para el láser 532 nm; delega en nidaq.set_laser532_voltage."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @pyqtSlot(float)
    def set_voltage(self, v: float):
        try:
            set_laser532_voltage(v)
        except Exception as e:
            print(f"[Laser532] Error: {e}")

    def make_connection(self, window: Laser532Window):
        window.voltageChangedSignal.connect(self.set_voltage)


# ══════════════════════════════════════════════════════════════════════════════
#  STANDALONE TEST
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    from PyQt6.QtWidgets import QVBoxLayout as _VL

    app = QApplication(sys.argv)

    cam_gui    = Frontend()
    cam_worker = Backend()
    cam_worker.make_connection(cam_gui)
    cam_gui.make_connection(cam_worker)

    cam_thread = QThread()
    cam_worker.moveToThread(cam_thread)
    cam_thread.start()

    laser_win     = Laser532Window()
    laser_backend = Laser532Backend()
    laser_backend.make_connection(laser_win)

    cam_gui.show()
    laser_win.show()
    sys.exit(app.exec())
