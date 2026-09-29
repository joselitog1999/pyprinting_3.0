# -*- coding: utf-8 -*-
"""
exploration_tab.py — Pestaña 1 (Exploración): Live View 2D y ROI Vertical Automático
PySpectrum 3.0 — UNSAM Nanofotónica

Fase 2 del Rework Arquitectónico: reemplaza definitivamente el frontend legado
camera_andor.py::Frontend en la Pestaña 1. No duplica ningún control de hardware (temperatura,
exposición, EM Gain, pre-amp, etc.) — esos ya viven de forma permanente en LeftHardwarePanel
(Fase 1). Sólo contiene el visor 2D de alto rendimiento, sus herramientas de imagen y el
selector interactivo de ROI vertical, que propaga automáticamente a spectroscopy_context.

Excepción arquitectónica (tercera en este proyecto, junto a Escaneo Lineal Espectral — DEC-006 —
y Mapeo Confocal — ANOM-HYPERSPEC-01): ExplorationWorker corre en un QThread real en vez del
patrón QTimer-en-hilo-GUI usado por la mayoría de las rutinas de pyspectrum, para sostener
Live View a 20-30 fps sin arriesgar que el heartbeat de obturadores o el botón E-STOP queden
sin respuesta durante la adquisición de cada cuadro.
"""
from __future__ import annotations
from typing import Any, Optional
import numpy as np
from PyQt6 import QtCore, QtWidgets
from PyQt6.QtCore import pyqtSignal, pyqtSlot, QTimer
import pyqtgraph as pg

from pyspectrum.modules.spectroscopy_context import spectroscopy_context
from pyspectrum.drivers.shamrock_driver import DEVICE, get_shamrock
from core.sif_processor import compute_robust_contrast_levels

# El pitch del detector se importa de su driver (fuente canónica única, DEC-031) en vez
# de transcribirlo acá: era una de las cinco copias que no concordaban.
from pyspectrum.drivers.andor_ccd_driver import DETECTOR_PIXEL_PITCH_UM, DeviceUnavailable  # noqa: E402

# (nombre visible, nombre interno de pyqtgraph, fuente ["" = built-in, "matplotlib" = vía mpl])
COLORMAP_OPTIONS = [
    ("Viridis", "viridis", ""),
    ("Inferno", "inferno", ""),
    ("Greys", "gray", "matplotlib"),
    ("Jet", "jet", "matplotlib"),
]


def _build_fallback_colormap(display_name: str) -> pg.ColorMap:
    """Colormap construido a mano para cuando el backend matplotlib no está disponible en el
    entorno (Greys/Jet dependen de él en pyqtgraph 0.14); nunca deja el selector sin efecto."""
    if display_name == "Greys":
        return pg.ColorMap(pos=[0.0, 1.0], color=[(0, 0, 0, 255), (255, 255, 255, 255)])
    if display_name == "Jet":
        return pg.ColorMap(
            pos=[0.0, 0.35, 0.66, 0.89, 1.0],
            color=[(0, 0, 143, 255), (0, 255, 255, 255), (255, 255, 0, 255), (255, 0, 0, 255), (128, 0, 0, 255)],
        )
    return pg.colormap.get("viridis")


def get_colormap(display_name: str) -> pg.ColorMap:
    """Resuelve un colormap por su nombre visible, con reintento de respaldo si la fuente
    (ej. matplotlib) no está disponible en el entorno."""
    for name, pg_name, source in COLORMAP_OPTIONS:
        if name == display_name:
            try:
                cmap = pg.colormap.get(pg_name, source=source) if source else pg.colormap.get(pg_name)
                if cmap is not None:
                    return cmap
            except Exception:
                pass
            return _build_fallback_colormap(display_name)
    return pg.colormap.get("viridis")


class ExplorationWorker(QtCore.QObject):
    """Motor de adquisición continua de Live View, destinado a moveToThread(). El QTimer se
    crea de forma perezosa dentro de start_live() (ejecutado ya en el hilo del worker vía
    conexión en cola), para que quede correctamente afín a ese hilo."""

    imageUpdatedSignal = pyqtSignal(np.ndarray)
    liveErrorSignal = pyqtSignal(str)  # motivo por el que el Live no arrancó o se detuvo

    def __init__(self, camera: Any, spectrometer: Optional[Any] = None, parent=None):
        super().__init__(parent)
        self.camera = camera
        self.spectrometer = spectrometer if spectrometer is not None else get_shamrock()
        self._timer: Optional[QTimer] = None

    @pyqtSlot()
    def start_live(self):
        # Sin cámara conectada el Live no arranca (DEC-040): antes leía cuadros de ceros, o del
        # simulador, cada 35 ms como si fueran del detector.
        if not getattr(self.camera, "available", True):
            self.liveErrorSignal.emit(
                "Live no disponible: " + (getattr(self.camera, "unavailable_reason", "") or "la cámara no está conectada."))
            return
        if self._timer is None:
            self._timer = QTimer(self)
            self._timer.setInterval(35)  # ~28 fps, mismo intervalo que camera_andor.py::Backend
            self._timer.timeout.connect(self._acquire_frame)
        try:
            # El obturador del espectrómetro se abre en el Live (investigador, 2026-09-29), por los dos
            # caminos del legado: USB del Shamrock y TTL de la cámara.
            from pyspectrum.services.spectrometer_shutter import open_spectrometer_shutter
            res = open_spectrometer_shutter(self.camera, self.spectrometer)
            if not res.ok:
                self.liveErrorSignal.emit(res.detail)
        except Exception:
            pass
        self.camera.start_acquisition()
        self._timer.start()

    @pyqtSlot()
    def stop_live(self):
        if self._timer is not None:
            self._timer.stop()
        self.camera.abort_acquisition()
        try:
            from pyspectrum.services.spectrometer_shutter import close_spectrometer_shutter
            res = close_spectrometer_shutter(self.camera, self.spectrometer)
            if not res.ok:
                self.liveErrorSignal.emit(res.detail)
        except Exception:
            pass

    @pyqtSlot(bool)
    def set_live(self, active: bool):
        self.start_live() if active else self.stop_live()

    def _acquire_frame(self):
        try:
            frame = self.camera.get_most_recent_image()
        except DeviceUnavailable as exc:
            self.stop_live()
            self.liveErrorSignal.emit(f"Live detenido: {exc}")
            return
        except Exception as exc:
            # FrameNotReady de la cámara sobre pylablib: todavía no hay cuadro; se espera al tick siguiente.
            if type(exc).__name__ == "FrameNotReady":
                return
            raise
        self.imageUpdatedSignal.emit(frame)


class ExplorationTabWidget(QtWidgets.QWidget):
    """Widget de la Pestaña 1 (Exploración): visor 2D de alto rendimiento + ROI vertical
    interactivo, sin controles de hardware duplicados con LeftHardwarePanel."""

    liveToggledSignal = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._last_frame: Optional[np.ndarray] = None
        self.setStyleSheet("""
            QLabel { color: #CDD6F4; }
            QPushButton {
                background-color: #313244; color: #CDD6F4; border: 1px solid #45475A;
                border-radius: 4px; padding: 5px 10px; font-weight: bold;
            }
            QPushButton:hover { background-color: #45475A; color: #89B4FA; }
            QComboBox { background-color: #11111B; color: #CDD6F4; border: 1px solid #45475A; border-radius: 4px; padding: 3px 6px; }
        """)
        self._setup_ui()

    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # ── Cabecera: Live View, herramientas de imagen, estado de ROI ────────
        header = QtWidgets.QHBoxLayout()

        self.btn_live = QtWidgets.QPushButton("▶️ Iniciar Live View")
        self.btn_live.setCheckable(True)
        self.btn_live.setToolTip("Inicia o detiene la adquisición continua (Live View) del detector.")
        self.btn_live.clicked.connect(self._on_toggle_live)
        header.addWidget(self.btn_live)

        header.addWidget(QtWidgets.QLabel("Colormap:"))
        self.cmb_colormap = QtWidgets.QComboBox()
        self.cmb_colormap.addItems([name for name, _, _ in COLORMAP_OPTIONS])
        self.cmb_colormap.currentTextChanged.connect(self._on_colormap_changed)
        header.addWidget(self.cmb_colormap)

        self.btn_autorange = QtWidgets.QPushButton("🔍 Auto-Rango")
        self.btn_autorange.setToolTip("Ajusta la vista para encuadrar la imagen completa.")
        self.btn_autorange.clicked.connect(self._on_autorange)
        header.addWidget(self.btn_autorange)

        self.btn_autolevels = QtWidgets.QPushButton("🎚️ Auto-Contraste")
        self.btn_autolevels.setToolTip("Recalcula los niveles de contraste con percentiles robustos (1–99%) del cuadro actual.")
        self.btn_autolevels.clicked.connect(self._on_autolevels)
        header.addWidget(self.btn_autolevels)

        self.btn_crosshair = QtWidgets.QPushButton("✛ Retícula Slit")
        self.btn_crosshair.setCheckable(True)
        self.btn_crosshair.setToolTip("Muestra u oculta la retícula central guía y la zona de apertura proyectada de la ranura.")
        self.btn_crosshair.clicked.connect(self._on_toggle_crosshair)
        header.addWidget(self.btn_crosshair)

        header.addWidget(QtWidgets.QLabel("🎯 Slit Objetivo:"))
        self.spin_target_slit = QtWidgets.QDoubleSpinBox()
        self.spin_target_slit.setRange(10.0, 2500.0)
        self.spin_target_slit.setValue(spectroscopy_context.slit_width_um)
        self.spin_target_slit.setSuffix(" µm")
        self.spin_target_slit.setToolTip(
            "Ancho de ranura objetivo para el experimento.\n"
            "Permite visualizar la zona donde se cerrará el slit mientras se opera con apertura amplia (ej. 2500 µm) en Orden Cero."
        )
        self.spin_target_slit.valueChanged.connect(self._on_target_slit_changed)
        header.addWidget(self.spin_target_slit)

        header.addStretch()
        layout.addLayout(header)

        self.lbl_roi_status = QtWidgets.QLabel("ROI Slit: [-- : --] (Centro: --, Alto: -- px)")
        self.lbl_roi_status.setStyleSheet("background-color: #11111B; padding: 4px 8px; border-radius: 4px; border: 1px solid #45475A;")
        layout.addWidget(self.lbl_roi_status)

        # En orden cero toda la luz cae en la imagen de la ranura: pico − bias como fracción del ADC de
        # 14 bit. Sólo informa, no detiene el Live (D-06); amarillo desde 50 %, rojo desde 80 % (H-21).
        self.lbl_saturation = QtWidgets.QLabel("")
        self.lbl_saturation.setToolTip(
            "Pico − bias del cuadro como fracción del ADC de 14 bit (16 383 cuentas).\n"
            "Amarillo desde el 50 %, rojo desde el 80 %. En orden cero sólo informa: bajá la luz o la ranura.")
        self.lbl_saturation.hide()
        layout.addWidget(self.lbl_saturation)

        # ── Visor 2D: pg.PlotItem + pg.ImageItem + HistogramLUTWidget lateral ──
        viewer_row = QtWidgets.QHBoxLayout()

        self.graphics_widget = pg.GraphicsLayoutWidget()
        self.graphics_widget.setBackground("#11111B")
        self.plot_item = self.graphics_widget.addPlot()
        self.plot_item.setAspectLocked(False)
        self.plot_item.invertY(True)
        self.plot_item.setLabel('bottom', "Pixel X (eje espectral)", color='#CDD6F4')
        self.plot_item.setLabel('left', "Pixel Y (altura de ranura)", color='#CDD6F4')

        self.image_item = pg.ImageItem()
        self.plot_item.addItem(self.image_item)

        # ROI vertical interactivo: propagación automática y silenciosa a spectroscopy_context
        self.roi_region = pg.LinearRegionItem(
            values=[480, 520], orientation=pg.LinearRegionItem.Horizontal,
            brush=pg.mkBrush(137, 180, 250, 40),
        )
        self.plot_item.addItem(self.roi_region)
        self.roi_region.sigRegionChanged.connect(self._on_roi_changed)

        # Visualización de Slit Objetivo (franja sombreada proyectada) y Retícula central guía
        c_x = spectroscopy_context.slit_center_px
        self.slit_region = pg.LinearRegionItem(
            values=[c_x - 2, c_x + 2],
            orientation=pg.LinearRegionItem.Vertical,
            brush=pg.mkBrush(243, 139, 168, 35),
            pen=pg.mkPen('#F38BA8', width=1, style=QtCore.Qt.PenStyle.DotLine),
            movable=False
        )
        self.crosshair_v = pg.InfiniteLine(pos=c_x, angle=90, pen=pg.mkPen('#F38BA8', width=1, style=QtCore.Qt.PenStyle.DashLine))
        self.crosshair_h = pg.InfiniteLine(pos=501, angle=0, pen=pg.mkPen('#F38BA8', width=1, style=QtCore.Qt.PenStyle.DashLine))
        self.slit_region.hide()
        self.crosshair_v.hide()
        self.crosshair_h.hide()
        self.plot_item.addItem(self.slit_region)
        self.plot_item.addItem(self.crosshair_v)
        self.plot_item.addItem(self.crosshair_h)

        viewer_row.addWidget(self.graphics_widget, stretch=1)

        self.histogram = pg.HistogramLUTWidget()
        self.histogram.setBackground("#11111B")
        self.histogram.setImageItem(self.image_item)
        self.histogram.setFixedWidth(110)
        viewer_row.addWidget(self.histogram)

        layout.addLayout(viewer_row, stretch=1)

        spectroscopy_context.slitParametersChanged.connect(self._on_context_slit_changed)
        spectroscopy_context.colormapChanged.connect(self._on_context_colormap_changed)

        self._on_roi_changed()
        self._on_colormap_changed(self.cmb_colormap.currentText())
        self._update_slit_overlay()

    # ── Live View ──────────────────────────────────────────────────────────

    def _on_toggle_live(self, checked: bool):
        if checked:
            self.btn_live.setText("⏹️ Detener Live View")
            self.btn_live.setStyleSheet("background-color: #F38BA8; color: #11111B; font-weight: bold;")
        else:
            self.btn_live.setText("▶️ Iniciar Live View")
            self.btn_live.setStyleSheet("background-color: #313244; color: #CDD6F4; font-weight: bold;")
        self.liveToggledSignal.emit(checked)

    @pyqtSlot(str)
    def on_live_error(self, message: str):
        """El worker no pudo arrancar o sostener el Live: vuelve el botón a "Iniciar" sin
        re-emitir la orden y deja el motivo a la vista (DEC-040)."""
        self.btn_live.blockSignals(True)
        self.btn_live.setChecked(False)
        self.btn_live.blockSignals(False)
        self.btn_live.setText("▶️ Iniciar Live View")
        self.btn_live.setStyleSheet("background-color: #313244; color: #CDD6F4; font-weight: bold;")
        self.btn_live.setToolTip(message)
        self.lbl_roi_status.setText(message)

    @pyqtSlot(np.ndarray)
    def update_image(self, img: np.ndarray):
        self._last_frame = img
        self.image_item.setImage(img.T, autoLevels=False)
        self._update_saturation(img)

    def _update_saturation(self, img: np.ndarray):
        from pyspectrum.drivers.specular_interlock import get_interlock
        from pyspectrum.modules.zero_order_service import ZeroOrderService
        if not get_interlock().is_specular_or_unknown():
            self.lbl_saturation.hide()
            return
        frac, level = ZeroOrderService.saturation_level(img)
        color = {"ok": "#A6ADC8", "warn": "#F9E2AF", "alarm": "#F38BA8"}[level]
        text = f"pico: {frac * 100:.0f} % del ADC"
        if level == "alarm":
            text += " · saturación en orden cero: reducir luz o ranura"
        self.lbl_saturation.setText(text)
        self.lbl_saturation.setStyleSheet(f"color: {color}; font-weight: bold; padding: 2px 8px;")
        self.lbl_saturation.show()

    # ── Herramientas de imagen ────────────────────────────────────────────

    def _on_colormap_changed(self, name: str):
        cmap = get_colormap(name)
        self.histogram.gradient.setColorMap(cmap)
        spectroscopy_context.set_colormap(name)

    def _on_context_colormap_changed(self, name: str):
        if self.cmb_colormap.currentText() != name:
            self.cmb_colormap.blockSignals(True)
            self.cmb_colormap.setCurrentText(name)
            self.cmb_colormap.blockSignals(False)
            cmap = get_colormap(name)
            self.histogram.gradient.setColorMap(cmap)

    def _on_autorange(self):
        self.plot_item.getViewBox().autoRange()

    def _on_autolevels(self):
        if self._last_frame is not None:
            levels = compute_robust_contrast_levels(self._last_frame)
            self.image_item.setLevels(levels)
            self.histogram.setLevels(*levels)

    def _on_toggle_crosshair(self, checked: bool):
        if checked:
            self.crosshair_v.show()
            self.crosshair_h.show()
            self.slit_region.show()
            self.btn_crosshair.setStyleSheet("background-color: #89B4FA; color: #11111B; font-weight: bold;")
        else:
            self.crosshair_v.hide()
            self.crosshair_h.hide()
            self.slit_region.hide()
            self.btn_crosshair.setStyleSheet("background-color: #313244; color: #CDD6F4; font-weight: bold;")

    def _update_slit_overlay(self):
        w_um = float(self.spin_target_slit.value())
        center_x = float(self.crosshair_v.value())
        w_px = max(1.0, w_um / DETECTOR_PIXEL_PITCH_UM)
        half_w = w_px / 2.0
        self.slit_region.setRegion([center_x - half_w, center_x + half_w])

    def _on_target_slit_changed(self, val: float):
        self._update_slit_overlay()

    def _on_context_slit_changed(self, width_um: float, center_px: float, zero_pos: int):
        self.crosshair_v.setValue(center_px)
        self._update_slit_overlay()

    # ── ROI vertical: propagación automática y silenciosa ─────────────────

    def _on_roi_changed(self):
        y1, y2 = self.roi_region.getRegion()
        y_min, y_max = int(round(min(y1, y2))), int(round(max(y1, y2)))
        y_center = (y_min + y_max) // 2
        y_height = max(1, y_max - y_min)
        self.lbl_roi_status.setText(f"ROI Slit: [{y_min} : {y_max}] (Centro: {y_center}, Alto: {y_height} px)")
        spectroscopy_context.set_vertical_roi(y_min, y_max)
