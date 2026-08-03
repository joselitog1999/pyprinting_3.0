# -*- coding: utf-8 -*-
"""
image_analyzer.py — Herramienta independiente y Dockable para análisis de imágenes
PyPrinting — UNSAM Nanofotónica — PyQt6

Permite abrir fotos (.jpg, .png, .bmp, .tiff, .tif 8/16/32-bit), analizarlas con trackpy,
ajustar niveles de intensidad (CLim) y paleta de falso color (LUT) para TIFF (estilo Confocal)
o Brillo/Contraste/Gamma/RGB para JPG/PNG, aplicar reglas tri-estado, medir distancias (px / µm adaptativo),
guardar mediciones y exportar partículas e imagen final anotada.
"""
import sys
import math
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── Registrar directorio raíz para resolver config y librerías ─────────────────
_curr = Path(__file__).resolve().parent
while _curr != _curr.parent:
    if (_curr / "config.py").exists():
        for _p in [str(_curr), str(_curr / "core"), str(_curr / "modules"), str(_curr / "analysis")]:
            if _p not in sys.path:
                sys.path.insert(0, _p)
        break
    _curr = _curr.parent

import cv2
import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore    import (Qt, pyqtSignal, pyqtSlot)
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget,
                               QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                               QTableWidget, QTableWidgetItem, QHeaderView,
                               QGroupBox, QMessageBox, QFileDialog, QSplitter,
                               QDialog, QSlider, QDoubleSpinBox, QComboBox, QFormLayout,
                               QStackedWidget)
from PyQt6.QtGui     import (QPainter, QPen, QColor, QFont, QPixmap, QImage)

from config import (DEFAULT_DATA_PATH, PIXEL_SIZE_UM,
                    DEFAULT_TRACKPY_DIAMETER_PX, DEFAULT_TRACKPY_MINMASS,
                    DEFAULT_TRACKPY_SEPARATION_PX)
try:
    from camera import OverlayWidget, SetScaleDialog, TrackpyDialog
except ImportError:
    from modules.camera import OverlayWidget, SetScaleDialog, TrackpyDialog


COLORMAP_MODES = ["Gris (Original)", "Thermal (Confocal/Láser)", "Viridis", "Plasma", "Inferno", "Jet / Arcoíris"]


class ImageAnalyzerWidget(QWidget):
    """Widget principal para el analizador de imágenes (operable como Dock o Standalone)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scale_set  = False
        self._ref_set    = False
        self._um_per_px  = PIXEL_SIZE_UM
        self._raw_frame: Optional[np.ndarray]     = None  # Matriz original sin procesar
        self._current_frame: Optional[np.ndarray] = None  # Matriz procesada para renderizado
        self._current_image_path: Optional[Path]  = None
        self._is_tiff = False
        self._raw_min = 0.0
        self._raw_max = 65535.0
        self._particles: list = []
        self._measure_pts: list = []
        self._saved_measures: list[dict] = []
        self._trackpy_params = dict(diameter=DEFAULT_TRACKPY_DIAMETER_PX, minmass=DEFAULT_TRACKPY_MINMASS, separation=DEFAULT_TRACKPY_SEPARATION_PX, threshold=0)
        self._measure_mode = False

        main_vlo = QVBoxLayout(self)
        main_vlo.setContentsMargins(4, 4, 4, 4)
        main_vlo.setSpacing(4)

        # ── Toolbar Superior ─────────────────────────────────────────────────
        tb = QWidget()
        tb_lo = QHBoxLayout(tb)
        tb_lo.setContentsMargins(2, 2, 2, 2)
        tb_lo.setSpacing(4)

        self._btn_open_img  = self._mkbtn("📁 Abrir Foto (.jpg, .tif)", color="#4a9eff")
        self._btn_export_img= self._mkbtn("📷 Exportar Foto", color="#3ecf8e")
        self._btn_setref    = self._mkbtn("Set ref.", checkable=True, color="#4a9eff")
        self._btn_setscale  = self._mkbtn("Set scale", color="#f5a623")
        self._btn_rulers    = self._mkbtn("Reglas (0)", color="#f5a623")
        self._btn_zoom_in   = self._mkbtn("Zoom +", color="#ffc832")
        self._btn_zoom_out  = self._mkbtn("Zoom -", color="#ffc832")
        self._btn_home      = self._mkbtn("Home", color="#ffc832")
        self._btn_clear_all = self._mkbtn("Limpiar Todo", color="#e5534b")

        self._btn_open_img.clicked.connect(self._open_image)
        self._btn_export_img.clicked.connect(self._export_annotated_image)
        self._btn_setref.clicked.connect(self._start_set_ref)
        self._btn_setscale.clicked.connect(self._open_set_scale)
        self._btn_rulers.clicked.connect(self._cycle_rulers)
        self._btn_zoom_in.clicked.connect(lambda: self._overlay.zoom_in())
        self._btn_zoom_out.clicked.connect(lambda: self._overlay.zoom_out())
        self._btn_home.clicked.connect(lambda: self._overlay.zoom_home())
        self._btn_clear_all.clicked.connect(self._global_clear_with_confirm)

        for w in (self._btn_open_img, self._btn_export_img, self._btn_setref,
                  self._btn_setscale, self._btn_rulers, self._btn_zoom_in,
                  self._btn_zoom_out, self._btn_home, self._btn_clear_all):
            tb_lo.addWidget(w)

        tb_lo.addStretch()
        main_vlo.addWidget(tb, stretch=0)

        # ── Layout Central con Splitter ───────────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 1. Panel Izquierdo: Detección, ROI y Ajustes de Imagen
        left_panel = QGroupBox("Detección & Ajustes de Imagen")
        left_lo    = QVBoxLayout(left_panel)
        left_lo.setContentsMargins(6, 6, 6, 6)

        # Botones de ROI y Detección
        self._btn_roi    = self._mkbtn("ROI detect", checkable=True, color="#8b7cf8")
        self._btn_detect = self._mkbtn("Detectar", color="#3ecf8e")
        btn_row_left = QHBoxLayout()
        btn_row_left.addWidget(self._btn_roi)
        btn_row_left.addWidget(self._btn_detect)
        left_lo.addLayout(btn_row_left)

        self._table_particles = QTableWidget(0, 4)
        self._table_particles.setHorizontalHeaderLabels(["#", "x (px)", "y (px)", "Int."])
        self._table_particles.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table_particles.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        left_lo.addWidget(self._table_particles)

        btn_row_left2 = QHBoxLayout()
        self._btn_exp_part = self._mkbtn("Exportar Partículas (.txt)", color="#3ecf8e")
        self._btn_clear_particles = self._mkbtn("Limpiar Partículas")
        self._btn_exp_part.clicked.connect(self._export_particles_txt)
        self._btn_clear_particles.clicked.connect(self._clear_particles)
        btn_row_left2.addWidget(self._btn_exp_part)
        btn_row_left2.addWidget(self._btn_clear_particles)
        left_lo.addLayout(btn_row_left2)

        # ── Panel de Ajustes Adaptativo (TIFF vs RGB) ─────────────────────────
        self._stack_adj = QStackedWidget()

        # Página 0: Ajustes TIFF (Intensidad Mín/Máx CLim estilo Confocal + Deslizadores)
        page_tiff = QWidget()
        pt_lo = QFormLayout(page_tiff)
        pt_lo.setContentsMargins(0, 0, 0, 0)

        self._slider_clim_min = QSlider(Qt.Orientation.Horizontal); self._slider_clim_min.setRange(0, 1000); self._slider_clim_min.setValue(0)
        self._slider_clim_max = QSlider(Qt.Orientation.Horizontal); self._slider_clim_max.setRange(0, 1000); self._slider_clim_max.setValue(1000)

        self._clim_min = QDoubleSpinBox(); self._clim_min.setRange(0, 1e7); self._clim_min.setValue(0)
        self._clim_max = QDoubleSpinBox(); self._clim_max.setRange(0, 1e7); self._clim_max.setValue(65535)

        self._cmap_combo = QComboBox()
        self._cmap_combo.addItems(COLORMAP_MODES)

        pt_lo.addRow("Intensidad Mín (Deslizador):", self._slider_clim_min)
        pt_lo.addRow("Intensidad Mín (Corte):", self._clim_min)
        pt_lo.addRow("Intensidad Máx (Deslizador):", self._slider_clim_max)
        pt_lo.addRow("Intensidad Máx (Sat.):", self._clim_max)
        pt_lo.addRow("Paleta Falso Color (LUT):", self._cmap_combo)

        self._slider_clim_min.valueChanged.connect(self._on_slider_clim_min_changed)
        self._slider_clim_max.valueChanged.connect(self._on_slider_clim_max_changed)
        self._clim_min.valueChanged.connect(self._on_spin_clim_min_changed)
        self._clim_max.valueChanged.connect(self._on_spin_clim_max_changed)
        self._cmap_combo.currentIndexChanged.connect(self._apply_image_adjustments)

        self._stack_adj.addWidget(page_tiff)

        # Página 1: Ajustes RGB (Brillo, Contraste, Gamma, WB)
        page_rgb = QWidget()
        pr_lo = QFormLayout(page_rgb)
        pr_lo.setContentsMargins(0, 0, 0, 0)
        self._slider_bright   = QSlider(Qt.Orientation.Horizontal); self._slider_bright.setRange(-100, 100); self._slider_bright.setValue(0)
        self._slider_contrast = QSlider(Qt.Orientation.Horizontal); self._slider_contrast.setRange(1, 30);  self._slider_contrast.setValue(10) # /10 -> 0.1 a 3.0
        self._slider_gamma    = QSlider(Qt.Orientation.Horizontal); self._slider_gamma.setRange(2, 25);   self._slider_gamma.setValue(10)    # /10 -> 0.2 a 2.5
        self._slider_r_gain   = QSlider(Qt.Orientation.Horizontal); self._slider_r_gain.setRange(5, 20);   self._slider_r_gain.setValue(10)   # /10 -> 0.5 a 2.0
        self._slider_g_gain   = QSlider(Qt.Orientation.Horizontal); self._slider_g_gain.setRange(5, 20);   self._slider_g_gain.setValue(10)   # /10 -> 0.5 a 2.0
        self._slider_b_gain   = QSlider(Qt.Orientation.Horizontal); self._slider_b_gain.setRange(5, 20);   self._slider_b_gain.setValue(10)   # /10 -> 0.5 a 2.0
        btn_reset_adj = QPushButton("Restablecer Ajustes RGB")
        btn_reset_adj.clicked.connect(self._reset_rgb_adjustments)

        pr_lo.addRow("Brillo:", self._slider_bright)
        pr_lo.addRow("Contraste:", self._slider_contrast)
        pr_lo.addRow("Gamma:", self._slider_gamma)
        pr_lo.addRow("Ganancia Rojo (R):", self._slider_r_gain)
        pr_lo.addRow("Ganancia Verde (G):", self._slider_g_gain)
        pr_lo.addRow("Ganancia Azul (B):", self._slider_b_gain)
        pr_lo.addRow(btn_reset_adj)

        for s in (self._slider_bright, self._slider_contrast, self._slider_gamma,
                  self._slider_r_gain, self._slider_g_gain, self._slider_b_gain):
            s.valueChanged.connect(self._apply_image_adjustments)

        self._stack_adj.addWidget(page_rgb)

        box_adj = QGroupBox("Ajustes Tonal de Imagen")
        box_adj_lo = QVBoxLayout(box_adj)
        box_adj_lo.addWidget(self._stack_adj)
        left_lo.addWidget(box_adj)

        self._btn_roi.clicked.connect(self._toggle_roi_mode)
        self._btn_detect.clicked.connect(self._open_trackpy_dialog)

        # 2. Visor Central de Imagen
        visor_container = QWidget()
        visor_lo        = QVBoxLayout(visor_container)
        visor_lo.setContentsMargins(0, 0, 0, 0)

        self._view = pg.GraphicsLayoutWidget()
        self._vb = self._view.addViewBox(lockAspect=True); self._vb.invertY(True)
        self._img_item = pg.ImageItem(); self._vb.addItem(self._img_item)

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
        self._table_measures.setHorizontalHeaderLabels(["#", "Dist (px)", "Δx/Δy (px)", "Ángulo"])
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
        self._lbl_scale  = QLabel("Escala no configurada (mediciones en px)")
        self._lbl_scale.setStyleSheet("color: #e5534b; font-family: monospace; font-size: 11px; font-weight: bold;")
        self._lbl_result = QLabel("Abrí una foto para comenzar a analizar")
        self._lbl_result.setStyleSheet("font-family: monospace; font-size: 11px; color: #aaa;")
        status_bar.addWidget(self._lbl_scale)
        status_bar.addStretch()
        status_bar.addWidget(self._lbl_result)
        main_vlo.addLayout(status_bar, stretch=0)

    # ── Sincronización Deslizadores vs Spinboxes TIFF (CLim) ─────────────────

    def _on_slider_clim_min_changed(self, val: int):
        if self._raw_max <= self._raw_min: return
        spin_val = self._raw_min + (val / 1000.0) * (self._raw_max - self._raw_min)
        self._clim_min.blockSignals(True)
        self._clim_min.setValue(spin_val)
        self._clim_min.blockSignals(False)
        self._apply_image_adjustments()

    def _on_slider_clim_max_changed(self, val: int):
        if self._raw_max <= self._raw_min: return
        spin_val = self._raw_min + (val / 1000.0) * (self._raw_max - self._raw_min)
        self._clim_max.blockSignals(True)
        self._clim_max.setValue(spin_val)
        self._clim_max.blockSignals(False)
        self._apply_image_adjustments()

    def _on_spin_clim_min_changed(self, val: float):
        if self._raw_max <= self._raw_min: return
        frac = (val - self._raw_min) / (self._raw_max - self._raw_min)
        slider_val = int(round(np.clip(frac, 0.0, 1.0) * 1000))
        self._slider_clim_min.blockSignals(True)
        self._slider_clim_min.setValue(slider_val)
        self._slider_clim_min.blockSignals(False)
        self._apply_image_adjustments()

    def _on_spin_clim_max_changed(self, val: float):
        if self._raw_max <= self._raw_min: return
        frac = (val - self._raw_min) / (self._raw_max - self._raw_min)
        slider_val = int(round(np.clip(frac, 0.0, 1.0) * 1000))
        self._slider_clim_max.blockSignals(True)
        self._slider_clim_max.setValue(slider_val)
        self._slider_clim_max.blockSignals(False)
        self._apply_image_adjustments()

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

    # ── Abrir e Importar Imagen (.jpg, .png, .bmp, .tif, .tiff) ─────────────

    def _open_image(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Abrir Imagen", str(DEFAULT_DATA_PATH),
            "Todas las Imágenes (*.tif *.tiff *.jpg *.jpeg *.png *.bmp);;Archivos TIFF (*.tif *.tiff);;Archivos Estándar (*.jpg *.png *.bmp)")
        if not file_path: return

        try:
            path = Path(file_path)
            ext = path.suffix.lower()
            self._is_tiff = ext in (".tif", ".tiff")

            if self._is_tiff:
                # Leer TIFF científico (8-bit, 16-bit, 32-bit)
                try:
                    import tifffile
                    arr = tifffile.imread(str(path))
                except Exception:
                    from PIL import Image as PILImage
                    img = PILImage.open(str(path))
                    arr = np.array(img)

                if arr.ndim == 3 and arr.shape[2] == 4:
                    arr = arr[:, :, :3]
                self._raw_frame = arr
                self._raw_min = float(np.min(arr))
                self._raw_max = float(np.max(arr))
                if self._raw_max <= self._raw_min:
                    self._raw_max = self._raw_min + 1.0

                self._clim_min.blockSignals(True); self._clim_min.setValue(self._raw_min); self._clim_min.blockSignals(False)
                self._clim_max.blockSignals(True); self._clim_max.setValue(self._raw_max); self._clim_max.blockSignals(False)
                self._slider_clim_min.blockSignals(True); self._slider_clim_min.setValue(0); self._slider_clim_min.blockSignals(False)
                self._slider_clim_max.blockSignals(True); self._slider_clim_max.setValue(1000); self._slider_clim_max.blockSignals(False)

                self._stack_adj.setCurrentIndex(0) # Pág TIFF
            else:
                from PIL import Image as PILImage
                pil_img = PILImage.open(str(path)).convert("RGB")
                self._raw_frame = np.array(pil_img, dtype=np.uint8)
                self._reset_rgb_adjustments()
                self._stack_adj.setCurrentIndex(1) # Pág RGB

            self._current_image_path = path
            self._apply_image_adjustments()
            W, H = self._overlay.get_img_dims()
            self._vb.setXRange(0, W, padding=0)
            self._vb.setYRange(0, H, padding=0)
            self._overlay.update()
            self._lbl_result.setText(f"Imagen cargada: {self._current_image_path.name} ({int(W)}x{int(H)} px)")
        except Exception as e:
            QMessageBox.critical(self, "Error al abrir imagen", f"No se pudo cargar la imagen:\n{e}")

    # ── Ajustes de Procesamiento de Imagen (TIFF vs RGB) ──────────────────────

    def _reset_rgb_adjustments(self):
        for s in (self._slider_bright, self._slider_contrast, self._slider_gamma,
                  self._slider_r_gain, self._slider_g_gain, self._slider_b_gain):
            s.blockSignals(True)
        self._slider_bright.setValue(0)
        self._slider_contrast.setValue(10)
        self._slider_gamma.setValue(10)
        self._slider_r_gain.setValue(10)
        self._slider_g_gain.setValue(10)
        self._slider_b_gain.setValue(10)
        for s in (self._slider_bright, self._slider_contrast, self._slider_gamma,
                  self._slider_r_gain, self._slider_g_gain, self._slider_b_gain):
            s.blockSignals(False)
        self._apply_image_adjustments()

    def _apply_image_adjustments(self):
        if self._raw_frame is None: return

        if self._is_tiff:
            cmin = self._clim_min.value()
            cmax = self._clim_max.value()
            if cmax <= cmin: cmax = cmin + 1.0
            norm = np.clip((self._raw_frame.astype(float) - cmin) / (cmax - cmin), 0.0, 1.0)
            u8 = (norm * 255.0).astype(np.uint8)

            cmap_idx = self._cmap_combo.currentIndex()
            if u8.ndim == 2:
                if cmap_idx == 0: # Gris (Original)
                    self._current_frame = np.stack([u8]*3, axis=-1)
                else:
                    cv_maps = [None, cv2.COLORMAP_HOT, cv2.COLORMAP_VIRIDIS, cv2.COLORMAP_PLASMA, cv2.COLORMAP_INFERNO, cv2.COLORMAP_JET]
                    colored = cv2.applyColorMap(u8, cv_maps[cmap_idx])
                    self._current_frame = cv2.cvtColor(colored, cv2.COLOR_BGR2RGB)
            else:
                self._current_frame = u8
        else:
            # Procesar ajustador RGB: Brillo, Contraste, Gamma y WB
            frame = self._raw_frame.astype(float)

            # 1. Balance de Blancos (Gains)
            r_g = self._slider_r_gain.value() / 10.0
            g_g = self._slider_g_gain.value() / 10.0
            b_g = self._slider_b_gain.value() / 10.0
            frame[:, :, 0] *= r_g
            frame[:, :, 1] *= g_g
            frame[:, :, 2] *= b_g

            # 2. Brillo y Contraste
            bright   = self._slider_bright.value()
            contrast = self._slider_contrast.value() / 10.0
            frame = (frame - 128.0) * contrast + 128.0 + bright

            # 3. Gamma
            gamma = self._slider_gamma.value() / 10.0
            frame = np.clip(frame, 0.0, 255.0) / 255.0
            frame = np.power(frame, 1.0 / gamma) * 255.0

            self._current_frame = np.clip(frame, 0, 255).astype(np.uint8)

        self._img_item.setImage(self._current_frame.transpose(1, 0, 2))

    # ── Exportar Imagen Annotada (con Capas) ──────────────────────────────────

    def _export_annotated_image(self):
        if self._current_frame is None:
            QMessageBox.warning(self, "Exportar Foto", "Primero abrí una foto.")
            return

        H, W = self._current_frame.shape[:2]
        qimg = QImage(self._current_frame.data, W, H, W * 3, QImage.Format.Format_RGB888).copy()
        pixmap = QPixmap.fromImage(qimg)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 1. Reglas
        if self._overlay._rulers_state > 0:
            pen1 = QPen(QColor(245, 166, 35, 230), 2, Qt.PenStyle.DashLine)
            painter.setPen(pen1)
            painter.setFont(QFont("Monospace", 12, QFont.Weight.Bold))
            r1_h = int(self._overlay._ruler1_h * H)
            r1_v = int(self._overlay._ruler1_v * W)
            painter.drawLine(0, r1_h, W, r1_h)
            painter.drawLine(r1_v, 0, r1_v, H)

            if self._overlay._rulers_state >= 2:
                pen2 = QPen(QColor(74, 158, 255, 230), 2, Qt.PenStyle.DashLine)
                painter.setPen(pen2)
                r2_h = int(self._overlay._ruler2_h * H)
                r2_v = int(self._overlay._ruler2_v * W)
                painter.drawLine(0, r2_h, W, r2_h)
                painter.drawLine(r2_v, 0, r2_v, H)

        # 2. Referencia
        if self._overlay._ref_pos:
            rx, ry = int(self._overlay._ref_pos[0] * W), int(self._overlay._ref_pos[1] * H)
            r = 18
            painter.setPen(QPen(QColor(74, 158, 255, 255), 3))
            painter.drawEllipse(rx-r, ry-r, 2*r, 2*r)
            painter.drawLine(rx-r-8, ry, rx+r+8, ry)
            painter.drawLine(rx, ry-r-8, rx, ry+r+8)

        # 3. Partículas
        if self._overlay._particles:
            painter.setPen(QPen(QColor(62, 207, 142, 240), 2))
            painter.setFont(QFont("Monospace", 11, QFont.Weight.Bold))
            for i, (fx, fy, *_) in enumerate(self._overlay._particles):
                px, py = int(fx * W), int(fy * H)
                painter.drawEllipse(px-12, py-12, 24, 24)
                painter.drawText(px + 14, py - 4, str(i+1))

        # 4. Mediciones
        if self._overlay._measure_pts:
            pts = self._overlay._measure_pts
            painter.setPen(QPen(QColor(229, 83, 75, 255), 3))
            painter.setFont(QFont("Monospace", 12, QFont.Weight.Bold))
            for i, (fx, fy) in enumerate(pts):
                px, py = int(fx * W), int(fy * H)
                painter.drawEllipse(px-6, py-6, 12, 12)
                painter.drawText(px+10, py-6, str(i+1))
            if len(pts) == 2:
                (fx1, fy1), (fx2, fy2) = pts
                p1x, p1y = int(fx1 * W), int(fy1 * H)
                p2x, p2y = int(fx2 * W), int(fy2 * H)
                painter.setPen(QPen(QColor(229, 83, 75, 200), 2, Qt.PenStyle.DashLine))
                painter.drawLine(p1x, p1y, p2x, p2y)
                dx_px = (fx2 - fx1) * W
                dy_px = (fy2 - fy1) * H
                dist_px = math.hypot(dx_px, dy_px)
                lbl_dist = f"d={dist_px * self._um_per_px:.3f}µm" if self._scale_set else f"d={dist_px:.1f}px"
                painter.setPen(QPen(QColor(245, 166, 35, 255)))
                painter.drawText(int((p1x+p2x)/2)+8, int((p1y+p2y)/2)-8, lbl_dist)

        painter.end()

        save_path, _ = QFileDialog.getSaveFileName(
            self, "Exportar Foto Annotada", str(DEFAULT_DATA_PATH / "analisis_export.png"),
            "Imágenes (*.png *.jpg *.jpeg)")
        if save_path:
            pixmap.save(save_path)
            QMessageBox.information(self, "Exportar Foto", f"Foto annotada exportada exitosamente en:\n{save_path}")

    # ── Handlers de Referencia, Reglas y Clics ───────────────────────────────

    def _start_set_ref(self, checked: bool):
        if checked:
            self._overlay.set_mode("ref")
            self._btn_setref.setText("Click en haz...")
        else:
            self._overlay.set_mode("none")
            self._btn_setref.setText("Set ref.")

    def _cycle_rulers(self):
        st = self._overlay.cycle_rulers()
        names = ["Reglas (0)", "Reglas (1 Par)", "Reglas (2 Pares)"]
        self._btn_rulers.setText(names[st])

    def _on_overlay_click(self, fx: float, fy: float):
        mode = self._overlay._mode

        if mode == "ref":
            snap = self._overlay.find_nearest_snap_point(fx, fy)
            if snap: fx, fy = snap
            self._ref_set = True
            self._overlay.set_ref(fx, fy)
            self._overlay.set_mode("none")
            self._btn_setref.setChecked(False)
            self._btn_setref.setText("Set ref.")
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
                dist_px = math.hypot(dx_px, dy_px)
                angle   = math.degrees(math.atan2(dy_px, dx_px))
                if self._scale_set:
                    dist_um = dist_px * self._um_per_px
                    self._lbl_result.setText(
                        f"Medida: {dist_um:.3f} µm (Δx={dx_px:.1f}px, Δy={dy_px:.1f}px) | θ={angle:.1f}°")
                else:
                    self._lbl_result.setText(
                        f"Medida: {dist_px:.1f} px (Δx={dx_px:.1f}px, Δy={dy_px:.1f}px) | θ={angle:.1f}°")

    # ── Mediciones ────────────────────────────────────────────────────────────

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
        dist_px = math.hypot(dx_px, dy_px)
        angle   = math.degrees(math.atan2(dy_px, dx_px))

        if self._scale_set:
            dist_val = dist_px * self._um_per_px
            unit_str = "µm"
            dist_disp = f"{dist_val:.3f}"
        else:
            dist_val = dist_px
            unit_str = "px"
            dist_disp = f"{dist_val:.1f} px"

        m = dict(index=len(self._saved_measures)+1, dist=dist_val, unit=unit_str, dx_px=dx_px, dy_px=dy_px, angle=angle)
        self._saved_measures.append(m)

        row = self._table_measures.rowCount()
        self._table_measures.insertRow(row)
        self._table_measures.setItem(row, 0, QTableWidgetItem(str(m["index"])))
        self._table_measures.setItem(row, 1, QTableWidgetItem(dist_disp))
        self._table_measures.setItem(row, 2, QTableWidgetItem(f"{dx_px:.1f} / {dy_px:.1f}"))
        self._table_measures.setItem(row, 3, QTableWidgetItem(f"{angle:.1f}°"))

    def _export_measurements_txt(self):
        if not self._saved_measures:
            QMessageBox.warning(self, "Exportar", "La lista de mediciones está vacía.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Guardar mediciones", str(DEFAULT_DATA_PATH / "mediciones_foto.txt"), "Archivos Texto (*.txt)")
        if not path: return
        with open(path, "w", encoding="utf-8") as f:
            f.write("# Mediciones de Foto - PyPrinting Image Analyzer\n")
            f.write(f"# Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            if self._scale_set:
                f.write(f"# Escala: {self._um_per_px:.5f} µm/px\n\n")
                f.write("Index\tDist_um\tDeltaX_px\tDeltaY_px\tAngulo_deg\n")
            else:
                f.write("# Escala: No configurada (unidades en px)\n\n")
                f.write("Index\tDist_px\tDeltaX_px\tDeltaY_px\tAngulo_deg\n")
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
        path, _ = QFileDialog.getSaveFileName(self, "Guardar partículas detectadas", str(DEFAULT_DATA_PATH / "particulas_detectadas_foto.txt"), "Archivos Texto (*.txt)")
        if not path: return
        with open(path, "w", encoding="utf-8") as f:
            f.write("# Partículas Detectadas en Foto - PyPrinting\n")
            f.write(f"# Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            if self._scale_set:
                f.write(f"# Escala: {self._um_per_px:.5f} µm/px\n\n")
                f.write("Index\tX_frac\tY_frac\tX_um\tY_um\tIntensidad\n")
                for i, (fx, fy, mass) in enumerate(self._particles):
                    x_um = fx * W * self._um_per_px
                    y_um = fy * H * self._um_per_px
                    f.write(f"{i+1}\t{fx:.5f}\t{fy:.5f}\t{x_um:.3f}\t{y_um:.3f}\t{mass:.1f}\n")
            else:
                f.write("# Escala: No configurada\n\n")
                f.write("Index\tX_frac\tY_frac\tX_px\tY_px\tIntensidad\n")
                for i, (fx, fy, mass) in enumerate(self._particles):
                    x_px = fx * W
                    y_px = fy * H
                    f.write(f"{i+1}\t{fx:.5f}\t{fy:.5f}\t{x_px:.1f}\t{y_px:.1f}\t{mass:.1f}\n")
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
            QMessageBox.warning(self, "Detectar", "Primero abrí una foto.")
            return
        roi = self._overlay.roi_fractions()
        um_per_px = self._um_per_px if self._scale_set else None
        dlg = TrackpyDialog(self._current_frame.copy(), roi_frac=roi, um_per_px=um_per_px, parent=self)
        dlg.paramsAccepted.connect(self._on_trackpy_params)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._run_detection()

    def _on_trackpy_params(self, params: dict):
        self._trackpy_params = params

    def _run_detection(self):
        if self._current_frame is None: return
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
        d    = p.pop("diameter", 11); d = d if d % 2 == 1 else d + 1
        sep  = p.get("separation", 8)
        thr  = p.get("threshold", None)

        try:
            import trackpy as tp
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                df = tp.locate(gray, diameter=d, separation=sep, threshold=thr)
        except Exception as e:
            QMessageBox.warning(self, "Detección fallida", str(e))
            return

        pts = []
        self._table_particles.setRowCount(len(df))

        if self._scale_set:
            self._table_particles.setHorizontalHeaderLabels(["#", "x (µm)", "y (µm)", "Int."])
        else:
            self._table_particles.setHorizontalHeaderLabels(["#", "x (px)", "y (px)", "Int."])

        for i, row in df.iterrows():
            gx = (row["x"] + offset[0]) / W
            gy = (row["y"] + offset[1]) / H
            mass = float(row.get("mass", 0))
            pts.append((gx, gy, mass))
            if self._scale_set:
                x_val = gx * W * self._um_per_px
                y_val = gy * H * self._um_per_px
            else:
                x_val = gx * W
                y_val = gy * H
            self._table_particles.setItem(i, 0, QTableWidgetItem(str(i+1)))
            self._table_particles.setItem(i, 1, QTableWidgetItem(f"{x_val:.2f}"))
            self._table_particles.setItem(i, 2, QTableWidgetItem(f"{y_val:.2f}"))
            self._table_particles.setItem(i, 3, QTableWidgetItem(f"{mass:.1f}"))

        self._particles = pts
        self._overlay.set_particles(pts)
        self._lbl_result.setText(f"Detección completada: {len(pts)} partículas guardadas.")

    # ── Limpiar Todo ──────────────────────────────────────────────────────────

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

    def _open_set_scale(self):
        if self._current_frame is None:
            QMessageBox.warning(self, "Set Scale", "Primero abrí una foto.")
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
        self._lbl_scale.setText(f"Escala configurada: {um_per_px:.5f} µm/px")
        self._lbl_scale.setStyleSheet("color: #3ecf8e; font-weight: bold; font-family: monospace; font-size: 11px;")
        self._table_measures.setHorizontalHeaderItem(1, QTableWidgetItem("Dist (µm)"))


class StandaloneAnalyzerWindow(QMainWindow):
    """Ventana independiente para ejecutar el analizador de imágenes."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PyPrinting — Analizador de Imágenes Independiente")
        self.resize(1240, 780)
        self._analyzer = ImageAnalyzerWidget(self)
        self.setCentralWidget(self._analyzer)


ImageAnalyzerWindow = StandaloneAnalyzerWindow


if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    win = StandaloneAnalyzerWindow()
    win.show()
    sys.exit(app.exec())
