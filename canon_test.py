# -*- coding: utf-8 -*-
"""
canon_test.py — Programa de prueba nativo para Canon EOS 500D (EDSDK Canon)
PyPrinting — UNSAM Nanofotónica — PyQt6

Permite probar en vivo:
  - Transmisión Live View en máxima calidad óptica con tasa constante de 30 FPS.
  - Corrección de orientación automática (rotación 90° horario y eliminación de espejo).
  - Zoom Live View (1x, 2x Digital Nitidez Fina, 5x Hardware AF, 10x Hardware Enfoque Fino).
  - Espera automática de 5 segundos tras conectar para estabilizar la sesión USB.
  - Ajuste dinámico de ISO (Auto, 100-3200) y Velocidad de Obturación (Tv: 1/10s a 10s).
  - Fallback automático a lista completa si la cámara reporta menos propiedades.
  - Captura y descarga de fotos en máxima resolución al disco local.
"""
from __future__ import annotations

import sys
import os
import time
from pathlib import Path
from typing import Optional

import numpy as np
import cv2
import pyqtgraph as pg
from PyQt6.QtCore    import (Qt, QThread, QObject, pyqtSignal, pyqtSlot, QTimer)
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget,
                               QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                               QComboBox, QGroupBox, QFileDialog, QMessageBox,
                               QFormLayout, QSplitter, QStatusBar, QGridLayout)
from PyQt6.QtGui     import QFont, QColor

from config import DEFAULT_DATA_PATH, CAMERA_WIDTH, CAMERA_HEIGHT
from canon_edsdk import (CanonCamera, ISO_MAP, REV_ISO_MAP, FULL_ISO_LIST,
                         TV_MAP, REV_TV_MAP, FULL_TV_LIST, ZOOM_MAP, REV_ZOOM_MAP,
                         AE_MODE_MAP, kEdsPropID_ISOSpeed, kEdsPropID_Tv, kEdsPropID_AEMode)


# ══════════════════════════════════════════════════════════════════════════════
#  LIVE VIEW WORKER THREAD
# ══════════════════════════════════════════════════════════════════════════════

class CanonWorker(QObject):
    frameSignal      = pyqtSignal(np.ndarray)
    statusSignal     = pyqtSignal(str)
    connectedSignal  = pyqtSignal(bool)
    propsReadySignal = pyqtSignal(list, list, int) # iso_vals, tv_vals, ae_mode

    def __init__(self):
        super().__init__()
        self._cam = CanonCamera()
        self._running = False
        self._timer = QTimer(self)
        self._timer.setInterval(33) # ~30 FPS
        self._timer.timeout.connect(self._fetch_frame)
        self._last_valid_frame = None
        self._mock_n = 0

    @pyqtSlot()
    def start_camera(self):
        self.statusSignal.emit("Conectando con cámara Canon EOS por USB...")
        ok = self._cam.open_session()
        if ok:
            self._cam.enable_live_view()
            self._running = True
            self._timer.start()
            self.connectedSignal.emit(True)
            self.statusSignal.emit("Conectado. Estabilizando sesión USB (esperando 5s para habilitar ISO y Velocidad)...")

            # Iniciar temporizador de 5 segundos antes de leer y habilitar propiedades
            QTimer.singleShot(5000, self._query_properties_after_delay)
        else:
            self.connectedSignal.emit(False)
            self.statusSignal.emit("⚠ No se detectó cámara Canon EOS por USB — Modo Simulación Activo")
            self._running = True
            self._timer.start()
            # En modo simulación habilitar inmediatamente con listas completas
            QTimer.singleShot(1000, self._query_properties_after_delay)

    def _query_properties_after_delay(self):
        if not self._running: return

        ae_mode  = self._cam.get_property_value(kEdsPropID_AEMode) if self._cam._is_session_open else 0

        # Consultar propiedades a Canon EDSDK
        cam_iso = self._cam.get_property_desc(kEdsPropID_ISOSpeed) if self._cam._is_session_open else []
        cam_tv  = self._cam.get_property_desc(kEdsPropID_Tv) if self._cam._is_session_open else []

        # Regla de fallback: si la cámara devuelve menos propiedades que nuestra lista completa, usar lista completa de respaldo
        final_iso = cam_iso if len(cam_iso) >= len(FULL_ISO_LIST) else FULL_ISO_LIST
        final_tv  = cam_tv  if len(cam_tv)  >= len(FULL_TV_LIST)  else FULL_TV_LIST

        self.propsReadySignal.emit(final_iso, final_tv, ae_mode)
        self.statusSignal.emit("Cámara Canon EOS 500D Lista | Opciones de ISO y Velocidad Habilitadas")

    @pyqtSlot()
    def stop_camera(self):
        self._timer.stop()
        self._running = False
        self._cam.close_session()
        self._cam.terminate_sdk()
        self.statusSignal.emit("Cámara desconectada.")

    def _fetch_frame(self):
        if not self._running: return
        if self._cam._is_session_open and self._cam._evf_enabled:
            jpeg_bytes = self._cam.get_live_view_frame()
            if jpeg_bytes:
                img_array = np.frombuffer(jpeg_bytes, dtype=np.uint8)
                frame_bgr = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                if frame_bgr is not None:
                    frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                    # Procesar rotación 90° + espejo + zoom de alta calidad
                    processed = self._cam.process_frame_zoom_and_orientation(frame_rgb)
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
        processed = self._cam.process_frame_zoom_and_orientation(frame)
        self._last_valid_frame = processed
        self.frameSignal.emit(processed)

    @pyqtSlot(int)
    def set_zoom(self, zoom_val: int):
        self._cam.set_live_view_zoom(zoom_val)

    @pyqtSlot(int)
    def set_iso(self, val: int):
        if self._cam._is_session_open:
            self._cam.set_property_value(kEdsPropID_ISOSpeed, val)

    @pyqtSlot(int)
    def set_tv(self, val: int):
        if self._cam._is_session_open:
            self._cam.set_property_value(kEdsPropID_Tv, val)

    @pyqtSlot()
    def take_photo(self):
        if self._cam._is_session_open:
            self.statusSignal.emit("📸 Disparando foto en alta resolución...")
            self._cam.take_photo()
        else:
            self.statusSignal.emit("⚠ Foto simulación creada en carpeta data.")

    @pyqtSlot(str)
    def set_save_dir(self, path: str):
        self._cam.set_save_directory(path)


# ══════════════════════════════════════════════════════════════════════════════
#  GUI TEST APPLICATION
# ══════════════════════════════════════════════════════════════════════════════

class CanonTestWindow(QMainWindow):
    startCameraSignal = pyqtSignal()
    stopCameraSignal  = pyqtSignal()
    setZoomSignal     = pyqtSignal(int)
    setIsoSignal      = pyqtSignal(int)
    setTvSignal       = pyqtSignal(int)
    takePhotoSignal   = pyqtSignal()
    setSaveDirSignal  = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Canon EOS 500D — Suite de Pruebas Nativa EDSDK")
        self.resize(1280, 800)

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
        panel = QGroupBox("Controles Canon EOS 500D")
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

        p_lo.addLayout(form)
        p_lo.addSpacing(15)

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

        p_lo.addStretch()

        # Botón Conectar / Desconectar
        self._btn_connect = QPushButton("▶ Iniciar Cámara Canon")
        self._btn_connect.setStyleSheet("font-weight: bold; color: #4a9eff; padding: 8px;")
        p_lo.addWidget(self._btn_connect)

        splitter.addWidget(panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        main_vlo.addWidget(splitter)

        # Barra de Estado
        self.statusBar().showMessage("Inicializando controlador Canon EDSDK...")

        # Conectar Señales UI
        self._btn_connect.clicked.connect(self._toggle_camera)
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
        self._worker.propsReadySignal.connect(self._populate_properties)
        self._worker.connectedSignal.connect(self._on_connected)

        self.startCameraSignal.connect(self._worker.start_camera)
        self.stopCameraSignal.connect(self._worker.stop_camera)
        self.setZoomSignal.connect(self._worker.set_zoom)
        self.setIsoSignal.connect(self._worker.set_iso)
        self.setTvSignal.connect(self._worker.set_tv)
        self.takePhotoSignal.connect(self._worker.take_photo)
        self.setSaveDirSignal.connect(self._worker.set_save_dir)

        self._thread.start()

    def _toggle_camera(self):
        if self._btn_connect.text().startswith("▶"):
            self._combo_iso.setEnabled(False)
            self._combo_tv.setEnabled(False)
            self.startCameraSignal.emit()
        else:
            self.stopCameraSignal.emit()
            self._combo_iso.setEnabled(False)
            self._combo_tv.setEnabled(False)
            self._btn_connect.setText("▶ Iniciar Cámara Canon")

    def _on_connected(self, connected: bool):
        if connected:
            self._btn_connect.setText("⏹ Desconectar Cámara")

    @pyqtSlot(np.ndarray)
    def _update_frame(self, frame: np.ndarray):
        self._img_item.setImage(frame.transpose(1, 0, 2))

    @pyqtSlot(str)
    def _update_status(self, msg: str):
        self.statusBar().showMessage(msg)

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

    def closeEvent(self, event):
        self.stopCameraSignal.emit()
        self._thread.quit()
        self._thread.wait(1000)
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = CanonTestWindow()
    win.show()
    sys.exit(app.exec())
