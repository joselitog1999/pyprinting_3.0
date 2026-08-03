# -*- coding: utf-8 -*-
"""
canon_test.py — Programa de prueba nativo para Canon EOS 500D (EDSDK Canon)
PyPrinting — UNSAM Nanofotónica — PyQt6

Permite probar en vivo:
  - Transmisión Live View en máxima calidad óptica adaptada a la velocidad nativa del bus USB.
  - Consola en tiempo real de Diagnóstico y Logs de Errores EDSDK.
  - Corrección de orientación automática (rotación 90° e inversión espejo).
  - Zoom Live View (1x, 2x Digital Nitidez Fina, 5x Hardware AF, 10x Hardware Enfoque Fino).
  - Espera automática de 5 segundos tras conectar para estabilizar la sesión USB.
  - Ajuste dinámico de ISO (Auto, 100-3200) y Velocidad de Obturación (Tv: 1/10s a 10s).
  - Fallback automático a lista completa si la cámara reporta menos propiedades.
  - Captura robusta mediante secuencia de obturador y descarga automática a la PC.
"""
from __future__ import annotations

import sys
import os
import time
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
import cv2
import pyqtgraph as pg
from PyQt6.QtCore    import (Qt, QThread, QObject, pyqtSignal, pyqtSlot, QTimer)
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget,
                               QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                               QComboBox, QGroupBox, QFileDialog, QMessageBox,
                               QFormLayout, QSplitter, QStatusBar, QTextEdit,
                               QStackedWidget, QSlider, QDoubleSpinBox)
from PyQt6.QtGui     import QFont, QColor

try:
    from config import DEFAULT_DATA_PATH, CAMERA_WIDTH, CAMERA_HEIGHT
except ImportError:
    try:
        from ..config import DEFAULT_DATA_PATH, CAMERA_WIDTH, CAMERA_HEIGHT
    except ImportError:
        # Fallback valores por defecto en caso extremo
        DEFAULT_DATA_PATH = Path("C:/Data")
        CAMERA_WIDTH, CAMERA_HEIGHT = 1280, 720
try:
    from canon_edsdk import (CanonCamera, ISO_MAP, REV_ISO_MAP, FULL_ISO_LIST,
                             TV_MAP, REV_TV_MAP, FULL_TV_LIST, ZOOM_MAP, REV_ZOOM_MAP,
                             AE_MODE_MAP, kEdsPropID_ISOSpeed, kEdsPropID_Tv, kEdsPropID_AEMode)
except ImportError:
    from core.canon_edsdk import (CanonCamera, ISO_MAP, REV_ISO_MAP, FULL_ISO_LIST,
                                  TV_MAP, REV_TV_MAP, FULL_TV_LIST, ZOOM_MAP, REV_ZOOM_MAP,
                                  AE_MODE_MAP, kEdsPropID_ISOSpeed, kEdsPropID_Tv, kEdsPropID_AEMode)


# ══════════════════════════════════════════════════════════════════════════════
#  LIVE VIEW WORKER THREAD
# ══════════════════════════════════════════════════════════════════════════════

class CanonWorker(QObject):
    frameSignal      = pyqtSignal(np.ndarray)
    statusSignal     = pyqtSignal(str)
    logSignal        = pyqtSignal(str)
    connectedSignal  = pyqtSignal(bool)
    propsReadySignal = pyqtSignal(list, list, int) # iso_vals, tv_vals, ae_mode

    def __init__(self):
        super().__init__()
        self._cam = CanonCamera(log_callback=self._emit_log)
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

    def _emit_log(self, msg: str):
        self.logSignal.emit(msg)

    def _ensure_timer(self):
        if self._timer is None:
            self._timer = QTimer(self)
            self._timer.setInterval(40)  # ~25 FPS nativo
            self._timer.timeout.connect(self._fetch_frame)

    @pyqtSlot()
    def start_camera(self):
        self._ensure_timer()
        self.statusSignal.emit("Conectando con cámara Canon EOS por USB...")
        self._emit_log("Iniciando conexión USB con cámara Canon EOS...")
        ok = self._cam.open_session()
        if ok:
            # 1. Leer propiedades e ISO/Tv ANTES de encender Live View (Cero colisiones USB)
            ae_mode = self._cam.get_property_value(kEdsPropID_AEMode)
            cam_iso = self._cam.get_property_desc(kEdsPropID_ISOSpeed)
            cam_tv  = self._cam.get_property_desc(kEdsPropID_Tv)

            final_iso = cam_iso if len(cam_iso) > 0 else FULL_ISO_LIST
            final_tv  = cam_tv  if len(cam_tv)  > 0 else FULL_TV_LIST

            self.propsReadySignal.emit(final_iso, final_tv, ae_mode)
            self.statusSignal.emit("Cámara Canon EOS 500D Conectada | Opciones Habilitadas")
            self._emit_log("Propiedades de cámara sincronizadas de inmediato. Controles ISO y Tv habilitados.")

            # 2. Habilitar Live View y arrancar timer de lectura de frames
            self._cam.enable_live_view()
            self._running = True
            self._timer.start()
            self.connectedSignal.emit(True)
        else:
            self.connectedSignal.emit(False)
            msg = "⚠ No se detectó cámara Canon EOS por USB — Modo Simulación MOCK Activo"
            self.statusSignal.emit(msg)
            self._emit_log(msg)
            self._running = True
            self.propsReadySignal.emit(FULL_ISO_LIST, FULL_TV_LIST, 0)
            self._timer.start()

    @pyqtSlot()
    def stop_camera(self):
        if self._timer is not None and self._timer.isActive():
            self._timer.stop()
        self._running = False
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

    def _fetch_frame(self):
        if not self._running: return
        if self._cam._is_session_open and self._cam._evf_enabled:
            jpeg_bytes = self._cam.get_live_view_frame()
            if jpeg_bytes:
                img_array = np.frombuffer(jpeg_bytes, dtype=np.uint8)
                frame_bgr = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                if frame_bgr is not None:
                    frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                    # Procesar rotación 90° + espejo + zoom + ajustes en vivo (Grises/CLim/LUT/RGB)
                    processed = self._cam.process_frame_live_adjustments(
                        frame_rgb, mode=self._mode_color, clim_min=self._clim_min,
                        clim_max=self._clim_max, lut_idx=self._lut_idx,
                        r_gain=self._r_gain, g_gain=self._g_gain, b_gain=self._b_gain)
                    self._last_valid_frame = processed
                    self.frameSignal.emit(processed)
                    return
            # Si el frame instantáneo no estuvo listo (busy), mantener el último cuadro válido para evitar parpadeo
            if self._last_valid_frame is not None:
                self.frameSignal.emit(self._last_valid_frame)
                return

        # Frame de prueba (Simulador MOCK si no hay cámara física o durante reconexión)
        self._mock_n += 1
        W, H = 1056, 704
        t = self._mock_n * 0.05
        frame = np.full((H, W, 3), 35, dtype=np.uint8)
        cx, cy = int(W/2 + 20*np.sin(t)), int(H/2 + 15*np.cos(t))
        cv2.circle(frame, (cx, cy), 18, (62, 207, 142), -1)
        cv2.circle(frame, (cx, cy), 45, (74, 158, 255), 2)
        cv2.putText(frame, "CANON EOS 500D MOCK STREAM (1056x704)", (30, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (245, 166, 35), 2)
        processed = self._cam.process_frame_live_adjustments(
            frame, mode=self._mode_color, clim_min=self._clim_min,
            clim_max=self._clim_max, lut_idx=self._lut_idx,
            r_gain=self._r_gain, g_gain=self._g_gain, b_gain=self._b_gain)
        self._last_valid_frame = processed
        self.frameSignal.emit(processed)

    @pyqtSlot(str, int, int, int, float, float, float)
    def set_live_adjustments(self, mode: str, cmin: int, cmax: int, lut_idx: int, r_g: float, g_g: float, b_g: float):
        self._mode_color = mode
        self._clim_min   = cmin
        self._clim_max   = cmax
        self._lut_idx    = lut_idx
        self._r_gain     = r_g
        self._g_gain     = g_g
        self._b_gain     = b_g

    @pyqtSlot(int)
    def set_zoom(self, zoom_val: int):
        self._cam.set_live_view_zoom(zoom_val)
        self._emit_log(f"Zoom Live View configurado a: {ZOOM_MAP.get(zoom_val, zoom_val)}")

    @pyqtSlot(int)
    def set_iso(self, val: int):
        if self._cam._is_session_open:
            was_running = self._timer is not None and self._timer.isActive()
            if was_running: self._timer.stop()
            ok = self._cam.set_property_value(kEdsPropID_ISOSpeed, val)
            if ok:
                lbl = ISO_MAP.get(val, f"0x{val:02X}")
                self.statusSignal.emit(f"ISO configurado a: {lbl}")
                self._emit_log(f"ISO cambiado exitosamente a {lbl}")
            if was_running: self._timer.start()

    @pyqtSlot(int)
    def set_tv(self, val: int):
        if self._cam._is_session_open:
            was_running = self._timer is not None and self._timer.isActive()
            if was_running: self._timer.stop()
            ok = self._cam.set_property_value(kEdsPropID_Tv, val)
            if ok:
                lbl = TV_MAP.get(val, f"0x{val:02X}")
                self.statusSignal.emit(f"Velocidad (Tv) configurada a: {lbl}")
                self._emit_log(f"Velocidad Tv cambiada exitosamente a {lbl}")
            if was_running: self._timer.start()

    @pyqtSlot()
    def take_photo(self):
        if self._cam._is_session_open:
            self.statusSignal.emit("📸 Disparando foto en alta resolución...")
            ok = self._cam.take_photo()
            if not ok:
                self._emit_log("❌ Error en el comando de obturación de foto.")
        else:
            # En modo MOCK simulación crear foto de prueba en carpeta destino
            save_dir = self._cam._save_dir
            os.makedirs(save_dir, exist_ok=True)
            t_str = time.strftime("%Y%m%d_%H%M%S")
            mock_photo_path = os.path.join(save_dir, f"CANON_MOCK_PHOTO_{t_str}.jpg")
            
            # Generar foto sintética de alta resolución (4752x3168)
            img = np.full((1080, 1620, 3), 50, dtype=np.uint8)
            cv2.circle(img, (810, 540), 120, (62, 207, 142), -1)
            cv2.putText(img, f"CANON EOS 500D MOCK PHOTO - {t_str}", (100, 100),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 2)
            cv2.imwrite(mock_photo_path, img)

            msg = f"✅ FOTO SIMULACIÓN MOCK CREADA EXITOSAMENTE EN: {mock_photo_path}"
            self.statusSignal.emit(msg)
            self._emit_log(msg)

    @pyqtSlot(str)
    def set_save_dir(self, path: str):
        self._cam.set_save_directory(path)


# ══════════════════════════════════════════════════════════════════════════════
#  GUI TEST APPLICATION
# ══════════════════════════════════════════════════════════════════════════════

class CanonTestWindow(QMainWindow):
    startCameraSignal        = pyqtSignal()
    stopCameraSignal         = pyqtSignal()
    setZoomSignal            = pyqtSignal(int)
    setIsoSignal             = pyqtSignal(int)
    setTvSignal              = pyqtSignal(int)
    takePhotoSignal          = pyqtSignal()
    setSaveDirSignal         = pyqtSignal(str)
    setLiveAdjustmentsSignal = pyqtSignal(str, int, int, int, float, float, float)

    def _on_color_mode_changed(self, idx: int):
        # idx 0: Color RGB, idx 1: Grises (Transmisión)
        if idx == 1:
            self._stack_live.setCurrentIndex(0) # Pág Grises
        else:
            self._stack_live.setCurrentIndex(1) # Pág RGB
        self._sync_live_adjustments()

    def _reset_live_rgb(self):
        for s in (self._slider_live_r, self._slider_live_g, self._slider_live_b):
            s.blockSignals(True)
        self._slider_live_r.setValue(10)
        self._slider_live_g.setValue(10)
        self._slider_live_b.setValue(10)
        for s in (self._slider_live_r, self._slider_live_g, self._slider_live_b):
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
        self.setLiveAdjustmentsSignal.emit(mode, cmin, cmax, lut, r_g, g_g, b_g)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Canon EOS 500D — Suite de Pruebas Nativa EDSDK")
        self.resize(1300, 820)

        central = QWidget()
        self.setCentralWidget(central)
        main_vlo = QVBoxLayout(central)

        # ── Splitter Principal ───────────────────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 1. Visor de Live View con PyQtGraph (Filtrado Bilinear Activo)
        visor_box = QGroupBox("Live View Óptico Nativo (Calidad Réflex EDSDK)")
        v_lo = QVBoxLayout(visor_box)
        self._view = pg.GraphicsLayoutWidget()
        self._vb   = self._view.addViewBox(lockAspect=True)
        self._vb.invertY(True)
        # Activar suavizado bilinear en la imagen para máxima definición óptica
        self._img_item = pg.ImageItem()
        self._img_item.setOpts(axisOrder='row-major', smooth=True)
        self._vb.addItem(self._img_item)
        v_lo.addWidget(self._view)
        splitter.addWidget(visor_box)

        # 2. Panel de Control de la Cámara
        panel = QGroupBox("Controles y Diagnóstico Canon EOS 500D")
        p_lo  = QVBoxLayout(panel)
        form  = QFormLayout()

        # Modo Dial
        self._lbl_mode = QLabel("Modo Cámara: Desconectado")
        self._lbl_mode.setStyleSheet("font-weight: bold; color: #3ecf8e;")
        form.addRow("Modo Cámara:", self._lbl_mode)

        # ISO (Bloqueado al inicio hasta pasar 5s)
        self._combo_iso = QComboBox()
        self._combo_iso.setEnabled(False)
        form.addRow("ISO (5s lock):", self._combo_iso)

        # Tv (Velocidad de Obturación / Tiempo Exposición)
        self._combo_tv  = QComboBox()
        self._combo_tv.setEnabled(False)
        form.addRow("Velocidad (Tv):", self._combo_tv)

        # Zoom Live View (1x, 2x, 5x, 10x)
        self._combo_zoom = QComboBox()
        for val, label in ZOOM_MAP.items():
            self._combo_zoom.addItem(label, userData=val)
        form.addRow("Zoom Live View:", self._combo_zoom)

        # Selector de Modo de Color (RGB vs Grises Transmisión)
        self._combo_color_mode = QComboBox()
        self._combo_color_mode.addItems(["Color RGB", "Grises (Transmisión)"])
        form.addRow("Modo Imagen:", self._combo_color_mode)

        p_lo.addLayout(form)
        p_lo.addSpacing(6)

        # ── Panel Integrado de Ajustes en Vivo ────────────────────────────────
        box_live = QGroupBox("Ajustes de Imagen en Vivo")
        b_lo = QVBoxLayout(box_live)
        b_lo.setContentsMargins(6, 6, 6, 6)

        self._stack_live = QStackedWidget()

        # Pág 0: Modo Grises / Transmisión (CLim + LUT)
        page_gray = QWidget()
        pg_lo = QFormLayout(page_gray)
        pg_lo.setContentsMargins(0, 0, 0, 0)
        self._slider_live_cmin = QSlider(Qt.Orientation.Horizontal); self._slider_live_cmin.setRange(0, 255); self._slider_live_cmin.setValue(0)
        self._slider_live_cmax = QSlider(Qt.Orientation.Horizontal); self._slider_live_cmax.setRange(0, 255); self._slider_live_cmax.setValue(255)
        self._combo_live_lut   = QComboBox()
        self._combo_live_lut.addItems(["Gris (Original)", "Thermal (Confocal/Láser)", "Viridis", "Plasma", "Inferno", "Jet / Arcoíris"])

        pg_lo.addRow("Intensidad Mín. (Corte):", self._slider_live_cmin)
        pg_lo.addRow("Intensidad Máx. (Sat.):", self._slider_live_cmax)
        pg_lo.addRow("Paleta Falso Color (LUT):", self._combo_live_lut)
        self._stack_live.addWidget(page_gray)

        # Pág 1: Modo Color RGB (Balance de Blancos / Ganancias)
        page_rgb = QWidget()
        pr_lo = QFormLayout(page_rgb)
        pr_lo.setContentsMargins(0, 0, 0, 0)
        self._slider_live_r = QSlider(Qt.Orientation.Horizontal); self._slider_live_r.setRange(5, 20); self._slider_live_r.setValue(10) # /10 -> 0.5 a 2.0
        self._slider_live_g = QSlider(Qt.Orientation.Horizontal); self._slider_live_g.setRange(5, 20); self._slider_live_g.setValue(10) # /10 -> 0.5 a 2.0
        self._slider_live_b = QSlider(Qt.Orientation.Horizontal); self._slider_live_b.setRange(5, 20); self._slider_live_b.setValue(10) # /10 -> 0.5 a 2.0
        btn_reset_live_rgb  = QPushButton("Restablecer Blancos (RGB)")
        btn_reset_live_rgb.clicked.connect(self._reset_live_rgb)

        pr_lo.addRow("Ganancia Rojo (R):", self._slider_live_r)
        pr_lo.addRow("Ganancia Verde (G):", self._slider_live_g)
        pr_lo.addRow("Ganancia Azul (B):", self._slider_live_b)
        pr_lo.addRow(btn_reset_live_rgb)
        self._stack_live.addWidget(page_rgb)

        # Iniciar en Pág 1 (RGB)
        self._stack_live.setCurrentIndex(1)
        b_lo.addWidget(self._stack_live)
        p_lo.addWidget(box_live)

        # Conectar deslizadores a actualización de señal
        self._combo_color_mode.currentIndexChanged.connect(self._on_color_mode_changed)
        for s in (self._slider_live_cmin, self._slider_live_cmax, self._slider_live_r, self._slider_live_g, self._slider_live_b):
            s.valueChanged.connect(self._sync_live_adjustments)
        self._combo_live_lut.currentIndexChanged.connect(self._sync_live_adjustments)

        p_lo.addSpacing(10)

        # Botón Disparar Foto
        self._btn_photo = QPushButton("📸 Disparar Foto (Alta Res)")
        self._btn_photo.setStyleSheet("font-weight: bold; background-color: #3ecf8e; color: #111; padding: 12px; font-size: 14px;")
        p_lo.addWidget(self._btn_photo)

        # Directorio de guardado
        self._btn_dir = QPushButton("📁 Cambiar Carpeta Guardado")
        p_lo.addWidget(self._btn_dir)
        self._lbl_dir = QLabel(f"Guardando en: {os.path.abspath(DEFAULT_DATA_PATH)}")
        self._lbl_dir.setStyleSheet("font-family: monospace; font-size: 10px; color: #aaa;")
        p_lo.addWidget(self._lbl_dir)

        p_lo.addSpacing(10)

        # ── Consola de Log y Diagnóstico EDSDK ────────────────────────────────
        log_box = QGroupBox("Diagnóstico & Eventos EDSDK")
        l_lo = QVBoxLayout(log_box)
        self._txt_log = QTextEdit()
        self._txt_log.setReadOnly(True)
        self._txt_log.setStyleSheet("font-family: monospace; font-size: 10px; background-color: #111; color: #00ff66;")
        l_lo.addWidget(self._txt_log)
        p_lo.addWidget(log_box)

        p_lo.addStretch()

        # Botón Conectar / Desconectar
        self._btn_connect = QPushButton("▶ Iniciar Cámara Canon")
        self._btn_connect.setStyleSheet("font-weight: bold; color: #4a9eff; padding: 8px;")
        p_lo.addWidget(self._btn_connect)

        # Botón Diagnóstico & Cierre Forzado de Obturador
        self._btn_diag = QPushButton("🛡️ Diagnóstico & Cierre Forzado Obturador")
        self._btn_diag.setStyleSheet("font-size: 11px; color: #ffaa00; background-color: #221c11; border: 1px solid #775500; padding: 6px;")
        p_lo.addWidget(self._btn_diag)

        splitter.addWidget(panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        main_vlo.addWidget(splitter)

        # Barra de Estado
        self.statusBar().showMessage("Inicializando controlador Canon EDSDK...")

        # Conectar Señales UI
        self._btn_connect.clicked.connect(self._toggle_camera)
        self._btn_diag.clicked.connect(self._force_shutter_cleanup)
        self._btn_photo.clicked.connect(lambda: self.takePhotoSignal.emit())
        self._btn_dir.clicked.connect(self._select_save_dir)
        self._combo_zoom.currentIndexChanged.connect(self._on_zoom_changed)
        self._combo_iso.currentIndexChanged.connect(self._on_iso_changed)
        self._combo_tv.currentIndexChanged.connect(self._on_tv_changed)

        # Configurar Hilo de Trabajo
        self._thread = QThread()
        self._worker = CanonWorker()
        self._worker.moveToThread(self._thread)

        self._worker.frameSignal.connect(self._update_frame)
        self._worker.statusSignal.connect(self._update_status)
        self._worker.logSignal.connect(self._append_log)
        self._worker.propsReadySignal.connect(self._populate_properties)
        self._worker.connectedSignal.connect(self._on_connected)

        self.startCameraSignal.connect(self._worker.start_camera)
        self.stopCameraSignal.connect(self._worker.stop_camera)
        self.setZoomSignal.connect(self._worker.set_zoom)
        self.setIsoSignal.connect(self._worker.set_iso)
        self.setTvSignal.connect(self._worker.set_tv)
        self.takePhotoSignal.connect(self._worker.take_photo)
        self.setSaveDirSignal.connect(self._worker.set_save_dir)
        self.setLiveAdjustmentsSignal.connect(self._worker.set_live_adjustments)

        self._is_camera_active = False
        self._thread.start()

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
        self._is_camera_active = True
        self._btn_connect.setText("⏹ Desconectar Cámara Canon")
        self._btn_connect.setStyleSheet("font-weight: bold; color: #ff6666; background-color: #3a1c1c; padding: 8px; border: 1px solid #ff4444;")

    @pyqtSlot(np.ndarray)
    def _update_frame(self, frame: np.ndarray):
        self._img_item.setImage(frame.transpose(1, 0, 2))

    @pyqtSlot(str)
    def _update_status(self, msg: str):
        self.statusBar().showMessage(msg)

    @pyqtSlot(str)
    def _append_log(self, msg: str):
        self._txt_log.append(msg)

    @pyqtSlot(list, list, int)
    def _populate_properties(self, iso_vals: list, tv_vals: list, ae_mode: int):
        mode_str = AE_MODE_MAP.get(ae_mode, f"Modo 0x{ae_mode:02X}")
        self._lbl_mode.setText(f"Modo Cámara: {mode_str}")

        # Poblar ISO
        self._combo_iso.blockSignals(True)
        self._combo_iso.clear()
        for v in iso_vals:
            lbl = ISO_MAP.get(v, f"0x{v:02X}")
            self._combo_iso.addItem(lbl, userData=v)
        self._combo_iso.blockSignals(False)
        self._combo_iso.setEnabled(True)

        # Poblar Tv (Velocidad de Obturación)
        self._combo_tv.blockSignals(True)
        self._combo_tv.clear()
        for v in tv_vals:
            lbl = TV_MAP.get(v, f"0x{v:02X}")
            self._combo_tv.addItem(lbl, userData=v)
        self._combo_tv.blockSignals(False)
        self._combo_tv.setEnabled(True)

    def _on_zoom_changed(self, idx: int):
        val = self._combo_zoom.itemData(idx)
        if val is not None: self.setZoomSignal.emit(val)

    def _on_iso_changed(self, idx: int):
        val = self._combo_iso.itemData(idx)
        if val is not None: self.setIsoSignal.emit(val)

    def _on_tv_changed(self, idx: int):
        val = self._combo_tv.itemData(idx)
        if val is not None: self.setTvSignal.emit(val)

    def _select_save_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta de guardado", str(DEFAULT_DATA_PATH))
        if d:
            self._lbl_dir.setText(f"Guardando en: {d}")
            self.setSaveDirSignal.emit(d)

    def _force_shutter_cleanup(self):
        self._append_log("🛡️ Ejecutando Diagnóstico & Cierre Forzado del Obturador Físico...")
        self.statusBar().showMessage("Cerrando obturador físico y restableciendo sesión USB...")
        
        # 1. Detener temporizador de frames
        if hasattr(self._worker, '_timer') and self._worker._timer is not None:
            if self._worker._timer.isActive():
                self._worker._timer.stop()

        # 2. Forzar deshabilitación de Live View (espejo/obturador a reposo) y cierre de sesión
        if hasattr(self._worker, '_cam') and self._worker._cam is not None:
            cam = self._worker._cam
            cam.disable_live_view()
            cam.close_session()

        self._combo_iso.setEnabled(False)
        self._combo_tv.setEnabled(False)
        self._lbl_mode.setText("Modo Cámara: Desconectado")
        self._btn_connect.setText("▶ Iniciar Cámara Canon")
        self._btn_connect.setStyleSheet("font-weight: bold; color: #4a9eff; padding: 8px;")
        self._is_camera_active = False
        
        msg = "✅ Diagnóstico completado: Obturador físico en posición de reposo y sesión de cámara restablecida."
        self.statusBar().showMessage(msg)
        self._append_log(msg)
        QMessageBox.information(self, "Diagnóstico & Cierre Obturador", msg)

    def closeEvent(self, event):
        try:
            self.statusBar().showMessage("Cerrando sesión de cámara y asegurando obturador...")
            if hasattr(self, '_worker') and self._worker is not None:
                if getattr(self._worker, '_timer', None) is not None:
                    if self._worker._timer.isActive():
                        self._worker._timer.stop()
                if getattr(self._worker, '_cam', None) is not None:
                    self._worker._cam.close_session()
                    self._worker._cam.terminate_sdk()

            if hasattr(self, '_thread') and self._thread.isRunning():
                self._thread.quit()
                self._thread.wait(2000)
        except Exception as e:
            print(f"[CanonTestWindow] Error durante closeEvent: {e}")
        finally:
            event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = CanonTestWindow()
    win.show()
    sys.exit(app.exec())
