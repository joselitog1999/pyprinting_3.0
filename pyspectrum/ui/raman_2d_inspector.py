# -*- coding: utf-8 -*-
"""
raman_2d_inspector.py — Sub-pestaña "Resultado Medición / Inspector 2D" del Static Raman
PySpectrum 3.0 — UNSAM Nanofotónica

Fase 3 del Rework Arquitectónico: explora adquisiciones bidimensionales (Multi-Track o Imagen
2D) del detector Andor CCD, píxel por píxel mediante un slider vertical interactivo o mediante
el promedio espacial ± desviación estándar del ROI heredado de SpectroscopyContext.
"""
from __future__ import annotations
import os
import time
from typing import Any, Optional, Tuple
import numpy as np
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import pyqtSignal, pyqtSlot
import pyqtgraph as pg

from pyspectrum.modules.spectroscopy_context import spectroscopy_context

try:
    import h5py
    H5PY_AVAILABLE = True
except ImportError:
    H5PY_AVAILABLE = False


def compute_roi_mean_std(frame_2d: np.ndarray, roi_rows: Tuple[int, int]) -> Tuple[np.ndarray, np.ndarray]:
    """μ(λ) y σ(λ) sobre las filas del ROI [y_min:y_max) de un cuadro 2D (H, W)."""
    y_min, y_max = roi_rows
    y0 = max(0, min(int(y_min), frame_2d.shape[0] - 1))
    y1 = max(y0 + 1, min(int(y_max), frame_2d.shape[0]))
    sub = frame_2d[y0:y1, :]
    return np.mean(sub, axis=0), np.std(sub, axis=0)


def export_raman_2d_to_hdf5(
    filepath: str, frame_2d: np.ndarray, wavelengths: np.ndarray, roi_rows: Tuple[int, int],
    laser_nm: Optional[float] = None, grating_name: str = "", read_mode_name: str = "",
    acquired_at: str = "",
) -> str:
    """Exporta un cuadro 2D Raman a HDF5 estructurado (/raw_2d, /spectrum_mean, /std,
    /wavelengths + metadatos de ROI/láser/Shamrock/timestamp). Degradación segura si h5py no
    está disponible: no escribe nada y retorna la ruta solicitada sin crear el archivo (mismo
    comportamiento que core/sif_processor.py::export_sif_session_to_hdf5)."""
    if not H5PY_AVAILABLE:
        print("[Raman2D HDF5 Warning] h5py no está disponible. No se generará el archivo.")
        return filepath

    os.makedirs(os.path.dirname(os.path.abspath(filepath)) or ".", exist_ok=True)
    mean, std = compute_roi_mean_std(frame_2d, roi_rows)
    comp = dict(compression="gzip", compression_opts=4, shuffle=True)

    with h5py.File(filepath, "w") as f:
        f.attrs["NX_class"] = "NXentry"
        f.attrs["laser_nm"] = float(laser_nm) if laser_nm is not None else -1.0
        f.attrs["grating"] = grating_name or ""
        f.attrs["read_mode"] = read_mode_name or ""
        f.attrs["acquired_at"] = acquired_at or ""
        f.attrs["roi_y_min"] = int(roi_rows[0])
        f.attrs["roi_y_max"] = int(roi_rows[1])
        f.create_dataset("raw_2d", data=np.asarray(frame_2d, dtype=np.float32), **comp)
        f.create_dataset("spectrum_mean", data=mean.astype(np.float64), **comp)
        f.create_dataset("std", data=std.astype(np.float64), **comp)
        f.create_dataset("wavelengths", data=np.asarray(wavelengths, dtype=np.float64), **comp)
    return filepath


class Raman2DInspectorWidget(QtWidgets.QWidget):
    """Inspector 2D: visor de cuadro + slider de fila + extracción 1D con conmutador a
    promedio espacial ± σ del ROI."""

    frameReceivedSignal = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.frame_2d: Optional[np.ndarray] = None
        self.wavelengths: Optional[np.ndarray] = None
        self.roi_rows: Tuple[int, int] = (0, 0)
        self.laser_nm: Optional[float] = None
        self.grating_name: str = ""
        self.read_mode_name: str = ""
        self.acquired_at: str = ""

        self.setStyleSheet("""
            QLabel { color: #CDD6F4; }
            QPushButton {
                background-color: #313244; color: #CDD6F4; border: 1px solid #45475A;
                border-radius: 4px; padding: 5px 10px; font-weight: bold;
            }
            QPushButton:hover { background-color: #45475A; color: #89B4FA; }
            QCheckBox { color: #CDD6F4; spacing: 6px; }
        """)
        self._setup_ui()

    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        header = QtWidgets.QHBoxLayout()
        self.chk_spatial_mean = QtWidgets.QCheckBox("Promedio Espacial ROI ± σ")
        self.chk_spatial_mean.setToolTip("Reemplaza la fila individual por el promedio espacial y la desviación estándar entre píxeles del ROI vertical heredado de la Pestaña 1.")
        self.chk_spatial_mean.toggled.connect(self._on_spatial_mean_toggled)
        header.addWidget(self.chk_spatial_mean)

        header.addStretch()

        self.btn_export = QtWidgets.QPushButton("💾 Exportar")
        self.btn_export.setToolTip("Exporta la fila actual o el promedio ROI a TXT/CSV, o el cuadro 2D completo a HDF5 estructurado.")
        self.btn_export.clicked.connect(self._on_export_clicked)
        header.addWidget(self.btn_export)
        layout.addLayout(header)

        self.lbl_row_status = QtWidgets.QLabel("Fila Y: [--] (Cuentas pico: --)")
        self.lbl_row_status.setStyleSheet("background-color: #11111B; padding: 4px 8px; border-radius: 4px; border: 1px solid #45475A;")
        layout.addWidget(self.lbl_row_status)

        # ── Panel Superior: Visor 2D + slider vertical de fila ────────────────
        top_row = QtWidgets.QHBoxLayout()

        self.graphics_widget = pg.GraphicsLayoutWidget()
        self.plot_2d = self.graphics_widget.addPlot()
        self.plot_2d.setAspectLocked(False)
        self.plot_2d.invertY(True)
        self.plot_2d.setLabels(bottom="Pixel X (eje espectral)", left="Pixel Y (fila)")
        self.image_item = pg.ImageItem()
        self.plot_2d.addItem(self.image_item)

        self.row_line = pg.InfiniteLine(pos=0, angle=0, movable=True, pen=pg.mkPen('#F38BA8', width=2))
        self.row_line.sigPositionChanged.connect(self._on_row_line_dragged)
        self.plot_2d.addItem(self.row_line)

        top_row.addWidget(self.graphics_widget, stretch=1)

        self.slider_row = QtWidgets.QSlider(QtCore.Qt.Orientation.Vertical)
        self.slider_row.setRange(0, 0)
        self.slider_row.setToolTip("Recorre las filas Y del cuadro 2D píxel a píxel.")
        self.slider_row.valueChanged.connect(self._on_row_changed)
        top_row.addWidget(self.slider_row)

        layout.addLayout(top_row, stretch=1)

        # ── Panel Inferior: Espectro 1D Extraído ──────────────────────────────
        self.plot_1d = pg.PlotWidget(title="Espectro Extraído")
        self.plot_1d.setBackground("#11111B")
        self.plot_1d.showGrid(x=True, y=True, alpha=0.3)
        self.plot_1d.setLabel('bottom', "Longitud de Onda (nm)")
        self.plot_1d.setLabel('left', "Intensidad (cts)")
        self.curve_1d = self.plot_1d.plot(pen=pg.mkPen("#A6E3A1", width=2))
        self.curve_upper = self.plot_1d.plot(pen=None)
        self.curve_lower = self.plot_1d.plot(pen=None)
        self.fill = pg.FillBetweenItem(self.curve_upper, self.curve_lower, brush=pg.mkBrush(166, 227, 161, 60))
        self.plot_1d.addItem(self.fill)
        self.fill.hide()
        layout.addWidget(self.plot_1d, stretch=1)

    def set_extra_metadata(self, laser_nm: Optional[float] = None, grating_name: Optional[str] = None):
        if laser_nm is not None:
            self.laser_nm = laser_nm
        if grating_name is not None:
            self.grating_name = grating_name

    @pyqtSlot(np.ndarray, np.ndarray, str)
    def set_frame_2d(self, wl_axis: np.ndarray, frame2d: np.ndarray, read_mode_name: str = ""):
        self.frame_2d = frame2d
        self.wavelengths = wl_axis
        self.read_mode_name = read_mode_name
        self.acquired_at = time.strftime("%Y-%m-%d %H:%M:%S")

        y_min, y_max, _, _ = spectroscopy_context.vertical_roi
        if y_max <= y_min:
            y_min, y_max = 0, frame2d.shape[0]
        self.roi_rows = (y_min, min(y_max, frame2d.shape[0]))

        self.image_item.setImage(frame2d.T, autoLevels=True)

        h = frame2d.shape[0]
        self.slider_row.blockSignals(True)
        self.slider_row.setRange(0, max(0, h - 1))
        self.slider_row.setValue(min(self.slider_row.value(), h - 1))
        self.slider_row.blockSignals(False)

        self._refresh_display()
        self.frameReceivedSignal.emit()

    # ── Slider ↔ Línea guía: sincronización bidireccional defensiva ──────────

    def _on_row_changed(self, y: int):
        self.row_line.blockSignals(True)
        self.row_line.setValue(y)
        self.row_line.blockSignals(False)
        self._refresh_display()

    def _on_row_line_dragged(self):
        if self.frame_2d is None:
            return
        y = int(round(self.row_line.value()))
        y = max(0, min(self.frame_2d.shape[0] - 1, y))
        self.slider_row.blockSignals(True)
        self.slider_row.setValue(y)
        self.slider_row.blockSignals(False)
        self._refresh_display()

    def _on_spatial_mean_toggled(self, checked: bool):
        self.slider_row.setEnabled(not checked)
        self.row_line.setMovable(not checked)
        self._refresh_display()

    def _refresh_display(self):
        if self.frame_2d is None or self.wavelengths is None:
            return
        if self.chk_spatial_mean.isChecked():
            mu, sigma = compute_roi_mean_std(self.frame_2d, self.roi_rows)
            self.curve_1d.setData(self.wavelengths, mu)
            self.curve_upper.setData(self.wavelengths, mu + sigma)
            self.curve_lower.setData(self.wavelengths, mu - sigma)
            self.fill.show()
            y0, y1 = self.roi_rows
            self.lbl_row_status.setText(f"Promedio Espacial ROI: filas [{y0}:{y1}] (Pico μ: {np.max(mu):.0f} cts)")
        else:
            y = self.slider_row.value()
            spec = self.frame_2d[y, :]
            self.curve_1d.setData(self.wavelengths, spec)
            self.fill.hide()
            self.lbl_row_status.setText(f"Fila Y: [{y}] (Cuentas pico: {np.max(spec):.0f})")

    # ── Exportación ───────────────────────────────────────────────────────

    def export_txt_to_path(self, path: str):
        if self.frame_2d is None or self.wavelengths is None:
            return
        if self.chk_spatial_mean.isChecked():
            mu, sigma = compute_roi_mean_std(self.frame_2d, self.roi_rows)
            with open(path, "w", encoding="utf-8") as f:
                f.write("Wavelength_nm\tMean_Counts\tStd_Counts\n")
                for w, m, s in zip(self.wavelengths, mu, sigma):
                    f.write(f"{w:.4f}\t{m:.2f}\t{s:.2f}\n")
        else:
            y = self.slider_row.value()
            spec = self.frame_2d[y, :]
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"# Fila Y: {y}\n")
                f.write("Wavelength_nm\tCounts\n")
                for w, c in zip(self.wavelengths, spec):
                    f.write(f"{w:.4f}\t{c:.2f}\n")

    def export_hdf5_to_path(self, path: str):
        if self.frame_2d is None or self.wavelengths is None:
            return
        export_raman_2d_to_hdf5(
            path, self.frame_2d, self.wavelengths, self.roi_rows,
            laser_nm=self.laser_nm, grating_name=self.grating_name,
            read_mode_name=self.read_mode_name, acquired_at=self.acquired_at,
        )

    def _on_export_clicked(self):
        if self.frame_2d is None:
            return
        menu = QtWidgets.QMenu(self)
        act_txt = menu.addAction("📄 Exportar TXT/CSV")
        act_h5 = menu.addAction("💾 Exportar HDF5 Estructurado")
        action = menu.exec(QtGui.QCursor.pos())
        if action == act_txt:
            default_name = f"Raman2D_{time.strftime('%Y%m%d_%H%M%S')}.txt"
            path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Exportar Espectro", default_name, "Texto (*.txt);;CSV (*.csv)")
            if path:
                self.export_txt_to_path(path)
        elif action == act_h5:
            default_name = f"Raman2D_{time.strftime('%Y%m%d_%H%M%S')}.h5"
            path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Exportar HDF5 Estructurado", default_name, "HDF5 (*.h5 *.hdf5)")
            if path:
                self.export_hdf5_to_path(path)
