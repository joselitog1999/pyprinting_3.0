# -*- coding: utf-8 -*-
"""
linescan_spectroscopy.py — Escaneo Lineal Espectral (Transmisión/Extinción ROI 1D + 2D)
PySpectrum 3.0 — UNSAM Nanofotónica

Mide perfiles espaciales de transmisión/extinción a lo largo de una recta con la platina
PI E-517, usando el espectrómetro Andor Shamrock 500i / iXon3. Soporta dos modos de
adquisición espectral: "Ventana Única" (un único grating fijo durante todo el barrido) y
"Espectro Completo" (Step & Glue en cada posición X, para cubrir un rango espectral más
amplio que una sola ventana del sensor).

Arquitectura: a diferencia de las demás rutinas de pyspectrum (que usan Backend(QObject) +
QTimer en el hilo GUI), esta usa un QThread real (`moveToThread`) porque un solo paso puede
bloquear desde cientos de ms (ventana única) hasta varios segundos/minutos (Step & Glue) —
ver docs/decisions/DECISION_LOG.md DEC-006. El tiempo de espera entre eventos NUNCA está
hardcodeado: el settle del piezo se confirma vía polling real `pi.qONT()` (igual que
core/nanopositioning.py), el settle del grating vía `spectrometer.wait_until_ready()` (ya
implementado en el driver pero no usado en ningún otro módulo), y la espera de exposición se
deriva del tiempo de exposición realmente configurado.
"""
from __future__ import annotations
import os
import time
from typing import Optional, List
import numpy as np
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import pyqtSignal, pyqtSlot, QThread
import pyqtgraph as pg

from config import SAFE_MODE, PI_AXES, PI_STAGE_RANGE_UM, SHUTTERS, pi
from core.nidaq import open_shutter, close_shutter, heartbeat_shutter
from core.sif_processor import compute_transmittance_with_errors, compute_extinction
from core.hdf5_container import write_linescan_spectroscopy_hdf5
from pyspectrum.drivers.shamrock_driver import DEVICE, get_shamrock
from pyspectrum.drivers.andor_ccd_driver import (
    get_andor_ccd, READ_MODE_SINGLE_TRACK, READ_MODE_IMAGE,
)
from pyspectrum.calibration.halogen_lamp import glue_steps
from pyspectrum.modules.hardware_session import hardware_session
from analysis.figure_export_studio import FigureExportStudioDialog

# Constante fija documentada: no existe modelo de readout del EMCCD iXon3 en el proyecto
# (confirmado por auditoría de instrumentation). Placeholder conservador a calibrar
# empíricamente en una tarea de instrumentación separada — no bloqueante para esta rutina.
ACQUISITION_READOUT_MARGIN_S = 0.05

PIEZO_SETTLE_TIMEOUT_S = 5.0
GRATING_SETTLE_TIMEOUT_S = 6.0
PIEZO_POSITION_TOLERANCE_UM = 0.05

# Cota inferior de transmission_*_physical (DEC-008, Brecha 1): igual al epsilon interno
# que compute_extinction() usa para evitar -log10(0)=inf. clip(T, 0, None) permitía que un
# consumidor externo que aplique -log10() directamente sobre _physical obtuviera +inf en vez
# de un valor finito grande — este epsilon lo evita sin reintroducir sesgo relevante (GUM).
EPSILON_TRANS = 1e-6


def compute_glue_centers(start_wl: float, end_wl: float, overlap: float) -> List[float]:
    """Centros espectrales para Step & Glue. Réplica intencional de la misma fórmula
    determinista usada en pyspectrum/modules/step_and_glue.py:315-320 (no se modifica ese
    archivo para evitar tocar una rutina no relacionada con este cambio)."""
    step_span = 240.0 * (1.0 - overlap)
    centers = []
    c = start_wl + 120.0
    while c <= end_wl + 50.0:
        centers.append(c)
        c += step_span
    if not centers:
        centers = [0.5 * (start_wl + end_wl)]
    return centers


class LineScanSpectroscopyWidget(QtWidgets.QDialog):
    """Panel de control y visualización del escaneo lineal espectral."""

    takeRefPositionSignal = pyqtSignal()
    previewFrameSignal = pyqtSignal()
    acquireReferenceSignal = pyqtSignal(dict)
    runScanSignal = pyqtSignal(dict)
    cancelScanSignal = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Escaneo Lineal Espectral (Transmisión/Extinción) — PySpectrum 3.0")
        self.resize(1180, 760)
        self.setStyleSheet("""
            QDialog { background-color: #11111B; }
            QLabel { color: #CDD6F4; }
            QGroupBox { color: #CDD6F4; font-weight: bold; border: 1px solid #45475A; border-radius: 4px; margin-top: 8px; padding-top: 6px; }
            QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }
            QPushButton { background-color: #313244; color: #CDD6F4; border: 1px solid #45475A; border-radius: 4px; padding: 6px 10px; font-weight: bold; }
            QPushButton:hover { background-color: #45475A; color: #89B4FA; }
            QPushButton:disabled { background-color: #181825; color: #585B70; }
            QDoubleSpinBox, QSpinBox, QComboBox, QLineEdit { background-color: #1E1E2E; color: #CDD6F4; border: 1px solid #45475A; border-radius: 4px; padding: 3px; }
        """)
        self._updating_roi_internally = False
        self._setup_ui()

    # ── UI ──────────────────────────────────────────────────────────────────
    def _setup_ui(self):
        root = QtWidgets.QHBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(12)

        ctrl_scroll = QtWidgets.QScrollArea()
        ctrl_scroll.setWidgetResizable(True)
        ctrl_scroll.setFixedWidth(360)
        ctrl_widget = QtWidgets.QWidget()
        ctrl = QtWidgets.QVBoxLayout(ctrl_widget)
        ctrl.setSpacing(8)

        # Cabecera fija (fuera del scroll): cancelar siempre visible
        header = QtWidgets.QVBoxLayout()
        lbl_title = QtWidgets.QLabel("📏 <b>Escaneo Lineal Espectral</b>")
        lbl_title.setStyleSheet("font-size: 11pt; color: #89B4FA;")
        header.addWidget(lbl_title)

        self.btn_cancel_local = QtWidgets.QPushButton("⏹ Cancelar Escaneo")
        self.btn_cancel_local.setStyleSheet("background-color: #F38BA8; color: #11111B;")
        self.btn_cancel_local.setEnabled(False)
        self.btn_cancel_local.setToolTip("Detiene el escaneo en curso al finalizar el punto actual y cierra el obturador de la lámpara.")
        self.btn_cancel_local.clicked.connect(self._on_cancel_clicked)
        header.addWidget(self.btn_cancel_local)

        self.lbl_warning = QtWidgets.QLabel("")
        self.lbl_warning.setWordWrap(True)
        self.lbl_warning.setStyleSheet(
            "background-color: #45381E; color: #F9E2AF; border: 1px solid #F9E2AF; "
            "border-radius: 4px; padding: 6px; font-size: 9pt;"
        )
        self.lbl_warning.hide()
        header.addWidget(self.lbl_warning)

        # ── Grupo Referencia (Fase A) ──────────────────────────────────────
        grp_ref = QtWidgets.QGroupBox("A. Posición de Referencia")
        lay_ref = QtWidgets.QGridLayout(grp_ref)
        lay_ref.addWidget(QtWidgets.QLabel("X_ref (µm):"), 0, 0)
        self.spin_xref = self._make_spin(0.0, 100.0, 50.0)
        lay_ref.addWidget(self.spin_xref, 0, 1)
        lay_ref.addWidget(QtWidgets.QLabel("Y_ref (µm):"), 1, 0)
        self.spin_yref = self._make_spin(0.0, 100.0, 50.0)
        lay_ref.addWidget(self.spin_yref, 1, 1)
        lay_ref.addWidget(QtWidgets.QLabel("Z_ref (µm):"), 2, 0)
        self.spin_zref = self._make_spin(0.0, 100.0, 50.0)
        lay_ref.addWidget(self.spin_zref, 2, 1)

        self.btn_take_pos = QtWidgets.QPushButton("📍 Tomar Posición Actual")
        self.btn_take_pos.setToolTip("Lee la posición actual de la platina PI E-517 y la usa como punto de referencia fijo.")
        self.btn_take_pos.clicked.connect(self.takeRefPositionSignal.emit)
        lay_ref.addWidget(self.btn_take_pos, 3, 0, 1, 2)
        ctrl.addWidget(grp_ref)

        # ── Grupo ROI vertical + preview ────────────────────────────────────
        grp_roi = QtWidgets.QGroupBox("ROI Vertical (Integración Espectral)")
        lay_roi = QtWidgets.QVBoxLayout(grp_roi)

        self.btn_preview = QtWidgets.QPushButton("🔍 Vista Previa del Sensor")
        self.btn_preview.setToolTip("Captura un cuadro único de la cámara para ajustar visualmente el ROI vertical (arrastrando la banda).")
        self.btn_preview.clicked.connect(self.previewFrameSignal.emit)
        lay_roi.addWidget(self.btn_preview)

        self.preview_imv = pg.ImageView()
        self.preview_imv.ui.roiBtn.hide()
        self.preview_imv.ui.menuBtn.hide()
        self.preview_imv.setFixedHeight(140)
        self.roi_line = pg.LinearRegionItem(values=[481, 521], orientation=pg.LinearRegionItem.Horizontal,
                                            brush=pg.mkBrush(137, 180, 250, 40))
        self.roi_line.sigRegionChangeFinished.connect(self._on_roi_line_changed)
        self.preview_imv.getView().addItem(self.roi_line)
        lay_roi.addWidget(self.preview_imv)

        h_roi_sp = QtWidgets.QHBoxLayout()
        h_roi_sp.addWidget(QtWidgets.QLabel("Centro (px):"))
        self.spin_roi_center = QtWidgets.QSpinBox()
        self.spin_roi_center.setRange(1, 1002)
        self.spin_roi_center.setValue(501)
        self.spin_roi_center.valueChanged.connect(self._on_roi_spin_changed)
        h_roi_sp.addWidget(self.spin_roi_center)
        h_roi_sp.addWidget(QtWidgets.QLabel("Altura (px):"))
        self.spin_roi_height = QtWidgets.QSpinBox()
        self.spin_roi_height.setRange(2, 200)
        self.spin_roi_height.setValue(40)
        self.spin_roi_height.valueChanged.connect(self._on_roi_spin_changed)
        h_roi_sp.addWidget(self.spin_roi_height)
        lay_roi.addLayout(h_roi_sp)
        ctrl.addWidget(grp_roi)

        # ── Grupo Adquisición ────────────────────────────────────────────
        grp_acq = QtWidgets.QGroupBox("Adquisición")
        lay_acq = QtWidgets.QGridLayout(grp_acq)
        lay_acq.addWidget(QtWidgets.QLabel("Fuente (Lámpara):"), 0, 0)
        self.combo_lamp = QtWidgets.QComboBox()
        self.combo_lamp.addItems(SHUTTERS)
        lay_acq.addWidget(self.combo_lamp, 0, 1)

        lay_acq.addWidget(QtWidgets.QLabel("Exp. 1D (s):"), 1, 0)
        self.spin_exp1d = self._make_spin(0.001, 60.0, 0.05, decimals=3)
        lay_acq.addWidget(self.spin_exp1d, 1, 1)
        lay_acq.addWidget(QtWidgets.QLabel("Exp. 2D (s):"), 2, 0)
        self.spin_exp2d = self._make_spin(0.001, 60.0, 0.10, decimals=3)
        lay_acq.addWidget(self.spin_exp2d, 2, 1)

        lay_acq.addWidget(QtWidgets.QLabel("Modo Espectral:"), 3, 0)
        self.combo_mode = QtWidgets.QComboBox()
        self.combo_mode.addItems(["Ventana Única", "Espectro Completo (Step & Glue)"])
        self.combo_mode.currentIndexChanged.connect(self._on_mode_changed)
        lay_acq.addWidget(self.combo_mode, 3, 1)

        self.box_glue = QtWidgets.QWidget()
        lay_glue = QtWidgets.QGridLayout(self.box_glue)
        lay_glue.setContentsMargins(0, 0, 0, 0)
        lay_glue.addWidget(QtWidgets.QLabel("λ Inicial (nm):"), 0, 0)
        self.spin_glue_start = self._make_spin(200.0, 1100.0, 450.0)
        lay_glue.addWidget(self.spin_glue_start, 0, 1)
        lay_glue.addWidget(QtWidgets.QLabel("λ Final (nm):"), 1, 0)
        self.spin_glue_end = self._make_spin(200.0, 1100.0, 950.0)
        lay_glue.addWidget(self.spin_glue_end, 1, 1)
        lay_glue.addWidget(QtWidgets.QLabel("Solapamiento:"), 2, 0)
        self.spin_glue_overlap = self._make_spin(0.0, 0.9, 0.20, decimals=2)
        lay_glue.addWidget(self.spin_glue_overlap, 2, 1)
        lay_acq.addWidget(self.box_glue, 4, 0, 1, 2)
        self.box_glue.setVisible(False)

        for sp in (self.spin_exp1d, self.spin_exp2d, self.spin_glue_start, self.spin_glue_end, self.spin_glue_overlap):
            sp.valueChanged.connect(self._update_eta_preview)

        # Cajón avanzado (Layer 3)
        self.box_advanced = QtWidgets.QGroupBox("⚙️ Avanzado")
        self.box_advanced.setCheckable(True)
        self.box_advanced.setChecked(False)
        lay_adv = QtWidgets.QGridLayout(self.box_advanced)
        lay_adv.addWidget(QtWidgets.QLabel("Multiplicador σ_dark:"), 0, 0)
        self.spin_noise_mult = self._make_spin(1.0, 10.0, 3.0, decimals=1)
        lay_adv.addWidget(self.spin_noise_mult, 0, 1)
        lay_acq.addWidget(self.box_advanced, 5, 0, 1, 2)
        ctrl.addWidget(grp_acq)

        self.btn_take_ref = QtWidgets.QPushButton("📥 Tomar Referencia (Fase A)")
        self.btn_take_ref.setStyleSheet("background-color: #89B4FA; color: #11111B;")
        self.btn_take_ref.clicked.connect(self._on_take_reference)
        ctrl.addWidget(self.btn_take_ref)

        # ── Grupo Barrido (Fase B) ─────────────────────────────────────────
        grp_scan = QtWidgets.QGroupBox("B. Recta de Barrido")
        lay_scan = QtWidgets.QGridLayout(grp_scan)
        lay_scan.addWidget(QtWidgets.QLabel("X inicial (µm):"), 0, 0)
        self.spin_xstart = self._make_spin(0.0, 100.0, 20.0)
        lay_scan.addWidget(self.spin_xstart, 0, 1)
        lay_scan.addWidget(QtWidgets.QLabel("X final (µm):"), 1, 0)
        self.spin_xend = self._make_spin(0.0, 100.0, 80.0)
        lay_scan.addWidget(self.spin_xend, 1, 1)
        lay_scan.addWidget(QtWidgets.QLabel("Y fijo (µm):"), 2, 0)
        self.spin_yfixed = self._make_spin(0.0, 100.0, 50.0)
        lay_scan.addWidget(self.spin_yfixed, 2, 1)
        lay_scan.addWidget(QtWidgets.QLabel("Z fijo (µm):"), 3, 0)
        self.spin_zfixed = self._make_spin(0.0, 100.0, 50.0)
        lay_scan.addWidget(self.spin_zfixed, 3, 1)
        lay_scan.addWidget(QtWidgets.QLabel("Paso ΔX (µm):"), 4, 0)
        self.spin_step = self._make_spin(0.05, 50.0, 2.0, decimals=2)
        lay_scan.addWidget(self.spin_step, 4, 1)
        for sp in (self.spin_xstart, self.spin_xend, self.spin_step):
            sp.valueChanged.connect(self._update_eta_preview)
        ctrl.addWidget(grp_scan)

        self.lbl_eta = QtWidgets.QLabel("⏱ Tiempo estimado: —")
        self.lbl_eta.setStyleSheet("color: #A6ADC8; font-size: 9pt;")
        ctrl.addWidget(self.lbl_eta)

        self.btn_start_scan = QtWidgets.QPushButton("🚀 Iniciar Escaneo")
        self.btn_start_scan.setStyleSheet("background-color: #A6E3A1; color: #11111B;")
        self.btn_start_scan.setEnabled(False)
        self.btn_start_scan.setToolTip("Requiere una Referencia válida (Fase A) antes de habilitarse.")
        self.btn_start_scan.clicked.connect(self._on_start_scan)
        ctrl.addWidget(self.btn_start_scan)

        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setValue(0)
        ctrl.addWidget(self.progress_bar)
        self.lbl_eta_live = QtWidgets.QLabel("")
        self.lbl_eta_live.setStyleSheet("color: #A6ADC8; font-size: 9pt;")
        ctrl.addWidget(self.lbl_eta_live)

        ctrl.addStretch()
        ctrl_scroll.setWidget(ctrl_widget)

        left_col = QtWidgets.QVBoxLayout()
        left_col.addLayout(header)
        left_col.addWidget(ctrl_scroll)
        root.addLayout(left_col)

        # ── Visualización en vivo ───────────────────────────────────────────
        right_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)

        self.plot_1d = pg.PlotWidget(title="<b>T(λ) / Ext(λ) — Último Punto</b>")
        self.plot_1d.setLabels(bottom="Longitud de Onda (nm)", left="Transmisión (%) / Extinción")
        self.plot_1d.addLegend(offset=(10, 10))
        self.curve_t = self.plot_1d.plot(name="T (%)", pen=pg.mkPen("#89B4FA", width=2.0))
        self.curve_ext = self.plot_1d.plot(name="Extinción", pen=pg.mkPen("#F38BA8", width=2.0))
        btn_exp_1d = QtWidgets.QPushButton("🎨 Exportar Curva")
        btn_exp_1d.clicked.connect(lambda: self._export_plot(self.plot_1d, "linescan_transmitancia_1d"))

        box_1d = QtWidgets.QWidget()
        lay_1d = QtWidgets.QVBoxLayout(box_1d)
        lay_1d.setContentsMargins(0, 0, 0, 0)
        lay_1d.addWidget(self.plot_1d)
        lay_1d.addWidget(btn_exp_1d)
        right_splitter.addWidget(box_1d)

        self.imv_heatmap = pg.ImageView(view=pg.PlotItem())
        self.imv_heatmap.ui.roiBtn.hide()
        self.imv_heatmap.ui.menuBtn.hide()
        self.imv_heatmap.getView().setLabels(bottom="Longitud de Onda (nm)", left="Posición X (µm)")
        right_splitter.addWidget(self.imv_heatmap)

        root.addWidget(right_splitter, stretch=1)

    def _make_spin(self, lo, hi, val, decimals=2):
        sp = QtWidgets.QDoubleSpinBox()
        sp.setRange(lo, hi)
        sp.setDecimals(decimals)
        sp.setValue(val)
        return sp

    # ── Handlers de UI ──────────────────────────────────────────────────────
    def _on_mode_changed(self, idx: int):
        self.box_glue.setVisible(idx == 1)
        self._update_eta_preview()

    def _on_roi_line_changed(self):
        if self._updating_roi_internally:
            return
        r = self.roi_line.getRegion()
        y1, y2 = min(r), max(r)
        self._updating_roi_internally = True
        self.spin_roi_center.setValue(int(round((y1 + y2) / 2.0)))
        self.spin_roi_height.setValue(max(2, int(round(abs(y2 - y1)))))
        self._updating_roi_internally = False

    def _on_roi_spin_changed(self):
        if self._updating_roi_internally:
            return
        center = self.spin_roi_center.value()
        height = self.spin_roi_height.value()
        self._updating_roi_internally = True
        self.roi_line.setRegion([center - height / 2.0, center + height / 2.0])
        self._updating_roi_internally = False

    @pyqtSlot(np.ndarray)
    def show_preview_frame(self, frame: np.ndarray):
        self.preview_imv.setImage(frame.T, autoRange=True, autoLevels=True)
        if self.roi_line.scene() is None:
            self.preview_imv.getView().addItem(self.roi_line)

    @pyqtSlot(list)
    def set_reference_position_fields(self, pos: list):
        self.spin_xref.setValue(pos[0])
        self.spin_yref.setValue(pos[1])
        self.spin_zref.setValue(pos[2])

    def _glue_params(self) -> dict:
        return dict(
            glue_start=self.spin_glue_start.value(),
            glue_end=self.spin_glue_end.value(),
            glue_overlap=self.spin_glue_overlap.value(),
        )

    def _mode_key(self) -> str:
        return 'single_window' if self.combo_mode.currentIndex() == 0 else 'step_and_glue'

    def _on_take_reference(self):
        cfg = dict(
            x_ref=self.spin_xref.value(), y_ref=self.spin_yref.value(), z_ref=self.spin_zref.value(),
            roi_center=self.spin_roi_center.value(), roi_height=self.spin_roi_height.value(),
            exp_1d=self.spin_exp1d.value(), exp_2d=self.spin_exp2d.value(),
            mode=self._mode_key(), lamp=self.combo_lamp.currentText(),
            noise_mult=self.spin_noise_mult.value(),
        )
        cfg.update(self._glue_params())
        self.btn_take_ref.setEnabled(False)
        self.acquireReferenceSignal.emit(cfg)

    @pyqtSlot(dict)
    def on_reference_done(self, summary: dict):
        self.btn_take_ref.setEnabled(True)
        self.btn_start_scan.setEnabled(True)
        self.lbl_warning.hide()
        self._update_eta_preview()

    @pyqtSlot(str)
    def on_reference_warning(self, msg: str):
        self.btn_take_ref.setEnabled(True)
        self.lbl_warning.setText("⚠️ " + msg)
        self.lbl_warning.show()

    def _estimate_total_time_s(self) -> float:
        try:
            x0, x1, step = self.spin_xstart.value(), self.spin_xend.value(), max(0.01, self.spin_step.value())
            n = max(1, int(round(abs(x1 - x0) / step)) + 1)
            if self._mode_key() == 'single_window':
                per_point = self.spin_exp1d.value() + self.spin_exp2d.value() + 2 * ACQUISITION_READOUT_MARGIN_S + 0.2
            else:
                centers = compute_glue_centers(self.spin_glue_start.value(), self.spin_glue_end.value(), self.spin_glue_overlap.value())
                per_point_1d = len(centers) * (0.3 + self.spin_exp1d.value() + ACQUISITION_READOUT_MARGIN_S) + 0.3
                per_point_2d = len(centers) * (0.3 + self.spin_exp2d.value() + ACQUISITION_READOUT_MARGIN_S) + 0.3
                per_point = per_point_1d + per_point_2d
            return n * per_point
        except Exception:
            return 0.0

    def _update_eta_preview(self):
        total_s = self._estimate_total_time_s()
        self.lbl_eta.setText(f"⏱ Tiempo estimado: {self._fmt_time(total_s)}")

    @staticmethod
    def _fmt_time(seconds: float) -> str:
        if seconds < 60:
            return f"{seconds:.0f} s"
        m, s = divmod(int(seconds), 60)
        if m < 60:
            return f"{m} min {s} s"
        h, m = divmod(m, 60)
        return f"{h} h {m} min"

    def _on_start_scan(self):
        total_s = self._estimate_total_time_s()
        if total_s > 600:
            reply = QtWidgets.QMessageBox.question(
                self, "Escaneo Prolongado",
                f"El tiempo estimado de este escaneo es {self._fmt_time(total_s)}.\n\n"
                f"¿Desea continuar?",
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
            )
            if reply != QtWidgets.QMessageBox.StandardButton.Yes:
                return

        cfg = dict(
            x_start=self.spin_xstart.value(), x_end=self.spin_xend.value(),
            y_fixed=self.spin_yfixed.value(), z_fixed=self.spin_zfixed.value(),
            step_um=self.spin_step.value(),
            exp_1d=self.spin_exp1d.value(), exp_2d=self.spin_exp2d.value(),
            mode=self._mode_key(), lamp=self.combo_lamp.currentText(),
        )
        cfg.update(self._glue_params())
        self.btn_start_scan.setEnabled(False)
        self.btn_cancel_local.setEnabled(True)
        self._n_steps_expected = max(1, int(round(abs(cfg['x_end'] - cfg['x_start']) / max(0.01, cfg['step_um']))) + 1)
        self._heatmap_buffer = None
        self.runScanSignal.emit(cfg)

    def _on_cancel_clicked(self):
        self.btn_cancel_local.setText("Cancelando… finalizando punto actual")
        self.btn_cancel_local.setEnabled(False)
        self.cancelScanSignal.emit()

    @pyqtSlot(np.ndarray, int, np.ndarray, np.ndarray)
    def update_1d_curve(self, wavelengths: np.ndarray, step: int, T: np.ndarray, Ext: np.ndarray):
        self.curve_t.setData(wavelengths, T)
        self.curve_ext.setData(wavelengths, Ext)
        if self._heatmap_buffer is None:
            self._heatmap_buffer = np.full((self._n_steps_expected, len(wavelengths)), np.nan, dtype=np.float32)
            self._heatmap_wavelengths = wavelengths
        if step < self._heatmap_buffer.shape[0]:
            self._heatmap_buffer[step, :] = Ext
            self.imv_heatmap.setImage(self._heatmap_buffer, autoRange=False, autoLevels=True)

    @pyqtSlot(int)
    def update_progress(self, pct: int):
        self.progress_bar.setValue(pct)

    @pyqtSlot(float)
    def update_eta_live(self, remaining_s: float):
        self.lbl_eta_live.setText(f"Restante: {self._fmt_time(max(0.0, remaining_s))}")

    @pyqtSlot(str)
    def on_scan_completed(self, h5_path: str):
        self._reset_scan_buttons()
        QtWidgets.QMessageBox.information(self, "Escaneo Finalizado", f"Escaneo completado y guardado en:\n{h5_path}")

    @pyqtSlot(str, str)
    def on_scan_aborted(self, h5_path: str, reason: str):
        """Distinto de on_scan_completed a propósito (hallazgo qa-ux-auditor): un escaneo
        interrumpido por timeout mecánico NUNCA debe reportarse con el mismo diálogo de éxito
        que uno completo, aunque el HDF5 parcial sí se haya guardado para recuperación forense."""
        self._reset_scan_buttons()
        msg = f"El escaneo se interrumpió antes de completarse:\n\n{reason}"
        if h5_path:
            msg += f"\n\nSe guardó un archivo PARCIAL (metadata['scan_aborted']=True) en:\n{h5_path}"
        QtWidgets.QMessageBox.warning(self, "Escaneo Incompleto — Fallo Mecánico", msg)

    @pyqtSlot()
    def on_scan_cancelled(self):
        self._reset_scan_buttons()
        self.btn_cancel_local.setText("⏹ Cancelar Escaneo")
        self.statusBar_message("Escaneo cancelado por el usuario.")

    @pyqtSlot(str)
    def on_error(self, msg: str):
        self._reset_scan_buttons()
        QtWidgets.QMessageBox.warning(self, "Error en Escaneo Lineal", msg)

    def _reset_scan_buttons(self):
        self.btn_start_scan.setEnabled(True)
        self.btn_cancel_local.setEnabled(False)
        self.btn_cancel_local.setText("⏹ Cancelar Escaneo")

    def statusBar_message(self, msg: str):
        print(f"[LineScan] {msg}")

    def _export_plot(self, plot_widget, default_name: str):
        try:
            dlg = FigureExportStudioDialog(plot_widget, parent=self, title="Exportar Figura — Escaneo Lineal", default_filename=default_name)
            dlg.exec()
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Error de Exportación", str(e))


class LineScanSpectroscopyWorker(QtCore.QObject):
    """Motor de adquisición del escaneo lineal. Vive en un QThread real (moveToThread) —
    ver DEC-006 en docs/decisions/DECISION_LOG.md. Nunca confía en que emergencyStopSignal
    lo interrumpa durante una espera bloqueante: consulta hardware_session.is_emergency_stopped
    activamente entre cada paso (mismo patrón que step_and_glue.py::_abort_requested)."""

    referencePositionSignal = pyqtSignal(list)
    previewFrameReadySignal = pyqtSignal(np.ndarray)
    referenceDoneSignal = pyqtSignal(dict)
    referenceWarningSignal = pyqtSignal(str)
    stepFinished1dSignal = pyqtSignal(np.ndarray, int, np.ndarray, np.ndarray)  # wavelengths, step, T, Ext
    frame2dUpdatedSignal = pyqtSignal(int, np.ndarray)
    progressSignal = pyqtSignal(int)
    etaSignal = pyqtSignal(float)
    scanCompletedSignal = pyqtSignal(str)
    scanAbortedSignal = pyqtSignal(str, str)  # h5_path (parcial, puede ser ""), motivo
    cancelledSignal = pyqtSignal()
    errorSignal = pyqtSignal(str)

    def __init__(self, camera=None, spectrometer=None, parent=None):
        super().__init__(parent)
        self.camera = camera or get_andor_ccd()
        self.spectrometer = spectrometer or get_shamrock()
        self._cancel_requested = False
        self._scan_failed = False
        self._reference: Optional[dict] = None
        self._wavelengths: Optional[np.ndarray] = None
        self._glue_reference_grid: Optional[np.ndarray] = None
        self._glue_centers: List[float] = []
        self.mode = 'single_window'
        self.roi_ycenter = 501
        self.roi_height = 40
        self.roi_ymin = 481
        self.roi_ymax = 521
        self.noise_threshold_1d = 10.0
        self.noise_threshold_2d = None
        self._t_step_history: List[float] = []
        hardware_session.emergencyStopSignal.connect(self._on_emergency_stop)

    def _on_emergency_stop(self):
        self._cancel_requested = True

    def _should_abort(self) -> bool:
        return self._cancel_requested or hardware_session.is_emergency_stopped

    # ── Temporización dinámica (no hardcodeada) ─────────────────────────────
    def _sleep_with_heartbeat(self, duration_s: float, tick_s: float = 0.1) -> bool:
        """Espera `duration_s`, renovando el heartbeat de obturadores y chequeando
        cancelación/E-STOP en cada tick. Devuelve False si fue interrumpida."""
        t_end = time.time() + max(0.0, duration_s)
        while time.time() < t_end:
            if self._should_abort():
                return False
            heartbeat_shutter(30.0)
            time.sleep(min(tick_s, max(0.0, t_end - time.time())))
        heartbeat_shutter(30.0)
        return not self._should_abort()

    def _move_and_settle(self, axes, targets, timeout_s: float = PIEZO_SETTLE_TIMEOUT_S) -> bool:
        """Settle del piezo SIN sleep fijo: polling real pi.qONT(), igual que
        core/nanopositioning.py, con timeout de seguridad propio (ese archivo no tiene uno)."""
        if isinstance(axes, int):
            axes_list, targets_list = [axes], [targets]
        else:
            axes_list, targets_list = list(axes), list(targets)
        targets_list = [max(0.0, min(PI_STAGE_RANGE_UM, float(t))) for t in targets_list]

        pi.MOV(axes_list, targets_list)
        t_end = time.time() + timeout_s
        settled = False
        while time.time() < t_end:
            if self._should_abort():
                return False
            heartbeat_shutter(30.0)
            if all(pi.qONT(axes_list).values()):
                settled = True
                break
            time.sleep(0.01)
        if not settled:
            self._scan_failed = True
            self.errorSignal.emit(f"Timeout de asentamiento del piezo (ejes {axes_list}, > {timeout_s}s). Escaneo abortado.")
            return False

        # Verificación real post-settle (recomendación de instrumentation), no espera ciega
        pos = pi.qPOS(axes_list)
        for ax, tgt in zip(axes_list, targets_list):
            actual = pos.get(str(ax))
            if actual is not None and abs(float(actual) - tgt) > PIEZO_POSITION_TOLERANCE_UM:
                print(f"[LineScan] Aviso: eje {ax} en {float(actual):.3f} µm, difiere "
                      f"{abs(float(actual) - tgt):.3f} µm del objetivo tras confirmación on-target.")
        return True

    def _settle_wavelength(self, wl_center: float, timeout_s: float = GRATING_SETTLE_TIMEOUT_S) -> bool:
        """Settle del grating SIN constante propia: usa is_moving()/_settling_until del
        propio driver Shamrock (ya implementado, nunca invocado en el resto del proyecto),
        con heartbeat intercalado en el polling."""
        self.spectrometer.ShamrockSetWavelength(DEVICE, wl_center)
        t_end = time.time() + timeout_s
        while self.spectrometer.is_moving():
            if self._should_abort():
                return False
            heartbeat_shutter(30.0)
            if time.time() > t_end:
                self._scan_failed = True
                self.errorSignal.emit(f"Timeout de asentamiento del grating a {wl_center:.1f} nm (> {timeout_s}s).")
                return False
            time.sleep(0.01)
        heartbeat_shutter(30.0)
        return True

    # ── Adquisición ──────────────────────────────────────────────────────────
    def _get_wavelength_axis(self, n_pixels: int) -> np.ndarray:
        if hasattr(self.spectrometer, 'get_wavelength_axis_cubic'):
            ret, wl = self.spectrometer.get_wavelength_axis_cubic(DEVICE, n_pixels)
        else:
            ret, wl = self.spectrometer.ShamrockGetCalibration(DEVICE, n_pixels)
        return np.asarray(wl, dtype=np.float64)

    def _acquire_1d(self) -> np.ndarray:
        return np.asarray(self.camera.get_1d_spectrum(), dtype=np.float64)

    def _acquire_2d_roi(self, roi_ymin: int, roi_ymax: int, width: int = 1004) -> np.ndarray:
        """Resuelve la inconsistencia de firma mock/real de get_most_recent_image()
        (hallazgo de instrumentation): el mock no acepta width/height."""
        if getattr(self.camera, 'is_mock', False):
            frame = self.camera.get_most_recent_image()
            return np.asarray(frame[roi_ymin:roi_ymax, :], dtype=np.float64)
        return np.asarray(self.camera.get_most_recent_image(width, roi_ymax - roi_ymin), dtype=np.float64)

    def _acquire_glued_spectrum(self, centers: List[float], exp_time_s: float):
        """Devuelve (grilla, espectro_interpolado, native_mismatch). La primera vez que se
        llama en una sesión de escaneo, la grilla nativa se convierte en la grilla común de
        referencia; las siguientes llamadas se interpolan a esa grilla (glue_steps() produce
        una longitud emergente de los datos, no garantizada fija entre puntos — hallazgo de
        software-architect)."""
        self.camera.set_exposure_time(exp_time_s)
        raw_waves, raw_specs = [], []
        for wl_c in centers:
            if self._should_abort():
                return np.array([]), np.array([]), True
            if not self._settle_wavelength(wl_c):
                return np.array([]), np.array([]), True
            if not self._sleep_with_heartbeat(exp_time_s + ACQUISITION_READOUT_MARGIN_S):
                return np.array([]), np.array([]), True
            spec = self._acquire_1d()
            wave = self._get_wavelength_axis(len(spec))
            raw_waves.append(wave)
            raw_specs.append(spec)
        self._settle_wavelength(centers[0])  # flyback antes del próximo punto espacial
        if not raw_waves:
            return np.array([]), np.array([]), True

        native_w, native_s = glue_steps(np.concatenate(raw_waves), np.concatenate(raw_specs), number_pixel=1004, grade=2.0)
        if self._glue_reference_grid is None:
            self._glue_reference_grid = native_w
            return native_w, native_s, False
        mismatch = (len(native_w) != len(self._glue_reference_grid))
        spec_interp = np.interp(self._glue_reference_grid, native_w, native_s) if len(native_w) > 1 else np.full_like(self._glue_reference_grid, np.nan)
        return self._glue_reference_grid, spec_interp, mismatch

    def _acquire_glued_2d(self, centers: List[float], exp_time_s: float) -> Optional[np.ndarray]:
        """Análogo fila-a-fila de _acquire_glued_spectrum para el modo imagen 2D."""
        self.camera.set_exposure_time(exp_time_s)
        frames, waves = [], []
        for wl_c in centers:
            if self._should_abort():
                return None
            if not self._settle_wavelength(wl_c):
                return None
            if not self._sleep_with_heartbeat(exp_time_s + ACQUISITION_READOUT_MARGIN_S):
                return None
            frame = self._acquire_2d_roi(self.roi_ymin, self.roi_ymax)
            wave = self._get_wavelength_axis(frame.shape[1])
            frames.append(frame)
            waves.append(wave)
        self._settle_wavelength(centers[0])
        if not frames:
            return None
        concat_w = np.concatenate(waves)
        n_rows = frames[0].shape[0]
        ref_grid = self._glue_reference_grid if self._glue_reference_grid is not None else self._get_wavelength_axis(frames[0].shape[1])
        glued_rows = []
        for row in range(n_rows):
            concat_s_row = np.concatenate([f[row, :] for f in frames])
            native_w, native_s = glue_steps(concat_w, concat_s_row, number_pixel=1004, grade=2.0)
            s_interp = np.interp(ref_grid, native_w, native_s) if len(native_w) > 1 else np.full_like(ref_grid, np.nan)
            glued_rows.append(s_interp)
        return np.array(glued_rows)

    # ── Slots públicos ───────────────────────────────────────────────────────
    @pyqtSlot()
    def read_current_position(self):
        pos = pi.qPOS(PI_AXES)
        self.referencePositionSignal.emit([
            round(float(pos.get("1", 0.0)), 3),
            round(float(pos.get("2", 0.0)), 3),
            round(float(pos.get("3", 0.0)), 3),
        ])

    @pyqtSlot()
    def capture_preview_frame(self):
        self.camera.set_read_mode(READ_MODE_IMAGE)
        self.camera.set_image(1, 1, 1, 1004, 1, 1002)
        frame = self.camera.get_most_recent_image() if getattr(self.camera, 'is_mock', False) else self.camera.get_most_recent_image(1004, 1002)
        self.previewFrameReadySignal.emit(np.asarray(frame, dtype=np.float32))

    @pyqtSlot(dict)
    def acquire_reference(self, cfg: dict):
        if not hardware_session.acquire_session("Escaneo Lineal Espectroscópico — Referencia"):
            self.errorSignal.emit("No se pudo tomar el control del hardware (sesión ocupada o E-STOP activo).")
            return
        self._cancel_requested = False
        lamp = cfg['lamp']
        try:
            self.mode = cfg['mode']
            self.roi_ycenter = int(cfg['roi_center'])
            self.roi_height = int(cfg['roi_height'])
            self.roi_ymin = max(0, self.roi_ycenter - self.roi_height // 2)
            self.roi_ymax = min(1002, self.roi_ymin + self.roi_height)
            self._glue_reference_grid = None

            if not self._move_and_settle(PI_AXES, [cfg['x_ref'], cfg['y_ref'], cfg['z_ref']]):
                return

            if self.mode == 'step_and_glue':
                self._glue_centers = compute_glue_centers(cfg['glue_start'], cfg['glue_end'], cfg['glue_overlap'])

            # ── 1D: señal (lámpara abierta) y fondo (lámpara cerrada) ──────
            open_shutter(lamp)
            self.camera.set_read_mode(READ_MODE_SINGLE_TRACK)
            self.camera.set_single_track(self.roi_ycenter, self.roi_height)
            if self.mode == 'single_window':
                if not self._sleep_with_heartbeat(cfg['exp_1d'] + ACQUISITION_READOUT_MARGIN_S):
                    return
                sig_1d = self._acquire_1d()
                self._wavelengths = self._get_wavelength_axis(len(sig_1d))
            else:
                w, sig_1d, _ = self._acquire_glued_spectrum(self._glue_centers, cfg['exp_1d'])
                self._wavelengths = w

            close_shutter(lamp)
            if self.mode == 'single_window':
                if not self._sleep_with_heartbeat(cfg['exp_1d'] + ACQUISITION_READOUT_MARGIN_S):
                    return
                bg_1d = self._acquire_1d()
            else:
                _, bg_1d, _ = self._acquire_glued_spectrum(self._glue_centers, cfg['exp_1d'])

            # ── 2D: señal y fondo, pixel a pixel en el mismo ROI vertical ──
            open_shutter(lamp)
            self.camera.set_read_mode(READ_MODE_IMAGE)
            self.camera.set_image(1, 1, 1, 1004, self.roi_ymin + 1, self.roi_ymax)
            if self.mode == 'single_window':
                if not self._sleep_with_heartbeat(cfg['exp_2d'] + ACQUISITION_READOUT_MARGIN_S):
                    return
                sig_2d = self._acquire_2d_roi(self.roi_ymin, self.roi_ymax)
            else:
                sig_2d = self._acquire_glued_2d(self._glue_centers, cfg['exp_2d'])
                if sig_2d is None:
                    return

            close_shutter(lamp)
            if self.mode == 'single_window':
                if not self._sleep_with_heartbeat(cfg['exp_2d'] + ACQUISITION_READOUT_MARGIN_S):
                    return
                bg_2d = self._acquire_2d_roi(self.roi_ymin, self.roi_ymax)
            else:
                bg_2d = self._acquire_glued_2d(self._glue_centers, cfg['exp_2d'])
                if bg_2d is None:
                    return

            mult = float(cfg.get('noise_mult', 3.0))
            sigma_dark_1d = float(np.std(bg_1d))
            sigma_dark_2d = np.std(bg_2d, axis=1)
            self.noise_threshold_1d = mult * sigma_dark_1d
            self.noise_threshold_2d = mult * sigma_dark_2d
            self.noise_multiplier = mult

            self._reference = dict(
                signal_1d=sig_1d, background_1d=bg_1d, signal_2d=sig_2d, background_2d=bg_2d,
                sigma_dark_1d=np.full_like(sig_1d, sigma_dark_1d), sigma_dark_2d=sigma_dark_2d,
                noise_threshold_2d=self.noise_threshold_2d,
            )

            net_ref = sig_1d - bg_1d
            weak_frac = float(np.mean(net_ref < self.noise_threshold_1d))
            if weak_frac > 0.5:
                self.referenceWarningSignal.emit(
                    f"Señal de referencia débil: (I_ref-BG_ref) < {mult:.0f}σ en {weak_frac * 100:.0f}% del "
                    f"espectro. Verifique lámpara/obturador y repita la referencia."
                )
                return

            self.referenceDoneSignal.emit({
                'sigma_dark_1d': sigma_dark_1d, 'weak_fraction': weak_frac, 'n_lambda': len(self._wavelengths),
            })
        finally:
            hardware_session.release_session("Escaneo Lineal Espectroscópico — Referencia")

    @pyqtSlot()
    def cancel_scan(self):
        self._cancel_requested = True

    @pyqtSlot(dict)
    def run_scan(self, cfg: dict):
        if self._reference is None:
            self.errorSignal.emit("Debe adquirir la Referencia (Fase A) antes de iniciar el escaneo.")
            return
        if not hardware_session.acquire_session("Escaneo Lineal Espectroscópico"):
            self.errorSignal.emit("No se pudo tomar el control del hardware (sesión ocupada o E-STOP activo).")
            return

        self._cancel_requested = False
        self._scan_failed = False
        lamp = cfg['lamp']
        self.mode = cfg['mode']
        self._t_step_history = []
        lamp_open = False
        try:
            x_start = max(0.0, min(PI_STAGE_RANGE_UM, float(cfg['x_start'])))
            x_end = max(0.0, min(PI_STAGE_RANGE_UM, float(cfg['x_end'])))
            step_um = max(0.01, abs(float(cfg['step_um'])))
            if x_start > x_end:
                x_start, x_end = x_end, x_start
            xs = np.arange(x_start, x_end + step_um * 0.5, step_um)
            n_steps = len(xs)

            if self.mode == 'step_and_glue':
                self._glue_centers = compute_glue_centers(cfg['glue_start'], cfg['glue_end'], cfg['glue_overlap'])

            if not self._move_and_settle([2, 3], [cfg['y_fixed'], cfg['z_fixed']]):
                return

            n_lambda = len(self._wavelengths)
            sample_1d = np.full((n_steps, n_lambda), np.nan, dtype=np.float64)
            t_1d_all = np.full((n_steps, n_lambda), np.nan, dtype=np.float64)
            ext_1d_all = np.full((n_steps, n_lambda), np.nan, dtype=np.float64)
            native_mismatch = np.zeros(n_steps, dtype=bool)

            open_shutter(lamp)
            lamp_open = True

            # ── Pasada 1: recorrer toda la recta en modo 1D ─────────────────
            if self.mode == 'single_window':
                self.camera.set_read_mode(READ_MODE_SINGLE_TRACK)
                self.camera.set_single_track(self.roi_ycenter, self.roi_height)

            last_i = -1
            for i, x in enumerate(xs):
                if self._should_abort():
                    break
                t0 = time.time()
                if not self._move_and_settle(1, float(x)):
                    break
                if self.mode == 'single_window':
                    if not self._sleep_with_heartbeat(cfg['exp_1d'] + ACQUISITION_READOUT_MARGIN_S):
                        break
                    spec = self._acquire_1d()
                    mism = False
                else:
                    _, spec, mism = self._acquire_glued_spectrum(self._glue_centers, cfg['exp_1d'])
                    if spec.size == 0:
                        break

                sample_1d[i, :] = spec
                native_mismatch[i] = mism
                T, _, _ = compute_transmittance_with_errors(
                    spec, self._reference['signal_1d'], bg_spec=self._reference['background_1d'],
                    sigma_bg=self._reference['sigma_dark_1d'], noise_threshold=self.noise_threshold_1d,
                    in_percentage=True, ref_is_bg_subtracted=False,
                )
                Ext, _ = compute_extinction(T)
                t_1d_all[i, :] = T
                ext_1d_all[i, :] = Ext
                last_i = i

                self._t_step_history.append(time.time() - t0)
                self.stepFinished1dSignal.emit(self._wavelengths, i, T, Ext)
                self.progressSignal.emit(int(50.0 * (i + 1) / n_steps))
                self._emit_eta(i, n_steps)

            if not self._should_abort():
                self._move_and_settle(1, float(x_start))

            # ── Pasada 2: recorrer toda la recta en modo 2D ─────────────────
            sample_2d = np.full((n_steps, self.roi_height, n_lambda), np.nan, dtype=np.float32)
            t_2d_all = np.full((n_steps, self.roi_height, n_lambda), np.nan, dtype=np.float64)
            ext_2d_all = np.full((n_steps, self.roi_height, n_lambda), np.nan, dtype=np.float64)

            if not self._should_abort():
                if self.mode == 'single_window':
                    self.camera.set_read_mode(READ_MODE_IMAGE)
                    self.camera.set_image(1, 1, 1, 1004, self.roi_ymin + 1, self.roi_ymax)

                for i, x in enumerate(xs):
                    if self._should_abort():
                        break
                    if not self._move_and_settle(1, float(x)):
                        break
                    if self.mode == 'single_window':
                        if not self._sleep_with_heartbeat(cfg['exp_2d'] + ACQUISITION_READOUT_MARGIN_S):
                            break
                        frame = self._acquire_2d_roi(self.roi_ymin, self.roi_ymax)
                    else:
                        frame = self._acquire_glued_2d(self._glue_centers, cfg['exp_2d'])
                        if frame is None:
                            break

                    rows = min(frame.shape[0], self.roi_height)
                    sample_2d[i, :rows, :] = frame[:rows, :]
                    for row in range(rows):
                        Trow, _, _ = compute_transmittance_with_errors(
                            frame[row], self._reference['signal_2d'][row], bg_spec=self._reference['background_2d'][row],
                            noise_threshold=float(self.noise_threshold_2d[row]) if self.noise_threshold_2d is not None else 10.0,
                            in_percentage=True, ref_is_bg_subtracted=False,
                        )
                        Erow, _ = compute_extinction(Trow)
                        t_2d_all[i, row, :] = Trow
                        ext_2d_all[i, row, :] = Erow

                    self.frame2dUpdatedSignal.emit(i, ext_2d_all[i])
                    self.progressSignal.emit(int(50.0 + 50.0 * (i + 1) / n_steps))

            close_shutter(lamp)
            lamp_open = False

            if self._cancel_requested and not hardware_session.is_emergency_stopped:
                self.cancelledSignal.emit()
                return
            if hardware_session.is_emergency_stopped:
                self.errorSignal.emit("Escaneo interrumpido por PARADA DE EMERGENCIA.")
                return

            t_phys_1d = np.clip(t_1d_all, EPSILON_TRANS, None)
            t_phys_2d = np.clip(t_2d_all, EPSILON_TRANS, None)

            metadata = dict(
                timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
                t_exp_1d_s=cfg['exp_1d'], t_exp_2d_s=cfg['exp_2d'],
                roi_ymin=self.roi_ymin, roi_ymax=self.roi_ymax,
                acquisition_mode=self.mode,
                extinction_formula="-log10(T)",
                acquisition_readout_margin_s=ACQUISITION_READOUT_MARGIN_S,
                noise_threshold_1d=float(self.noise_threshold_1d),
                noise_multiplier=float(getattr(self, 'noise_multiplier', 3.0)),
                scan_aborted=bool(self._scan_failed),
            )
            if self.mode == 'step_and_glue':
                metadata.update(
                    glue_start_wl_nm=cfg['glue_start'], glue_end_wl_nm=cfg['glue_end'],
                    glue_overlap_pct=cfg['glue_overlap'] * 100.0,
                )

            out_dir = os.path.join(os.getcwd(), "data_linescan_spectroscopy")
            filename = f"linescan_{time.strftime('%Y%m%d_%H%M%S')}.h5"
            filepath = os.path.join(out_dir, filename)

            h5_path = write_linescan_spectroscopy_hdf5(
                filepath=filepath,
                metadata=metadata,
                x_positions_um=xs,
                wavelengths_nm=self._wavelengths,
                reference=self._reference,
                raw_data=dict(sample_1d=sample_1d, sample_2d=sample_2d, native_length_mismatch=native_mismatch),
                processed=dict(
                    transmission_1d=t_1d_all, transmission_1d_physical=t_phys_1d, extinction_1d=ext_1d_all,
                    transmission_2d=t_2d_all, transmission_2d_physical=t_phys_2d, extinction_2d=ext_2d_all,
                ),
            )
            if self._scan_failed:
                self.scanAbortedSignal.emit(
                    h5_path,
                    "Fallo de asentamiento mecánico (piezo o grating) durante el escaneo — ver el aviso "
                    "de timeout anterior. Los puntos posteriores al punto de fallo quedaron como NaN. "
                    "Se guardó un archivo PARCIAL para recuperación forense (metadata['scan_aborted']=True)."
                )
            else:
                self.scanCompletedSignal.emit(h5_path)
        finally:
            if lamp_open:
                close_shutter(lamp)
            hardware_session.release_session("Escaneo Lineal Espectroscópico")

    def _emit_eta(self, i: int, n_steps: int):
        if not self._t_step_history:
            return
        mean_t = float(np.mean(self._t_step_history[-10:]))
        remaining_1d = (n_steps - (i + 1)) * mean_t
        remaining_2d_est = n_steps * mean_t  # aproximación: la pasada 2D aún no empezó
        self.etaSignal.emit(remaining_1d + remaining_2d_est)


def create_linescan_routine(camera=None, spectrometer=None, parent=None):
    """Fábrica de conveniencia: crea Widget + Worker + QThread ya conectados,
    replicando el patrón moveToThread estándar de Qt (ver DEC-006)."""
    widget = LineScanSpectroscopyWidget(parent=parent)
    worker = LineScanSpectroscopyWorker(camera=camera, spectrometer=spectrometer)
    thread = QThread()
    worker.moveToThread(thread)

    widget.takeRefPositionSignal.connect(worker.read_current_position)
    widget.previewFrameSignal.connect(worker.capture_preview_frame)
    widget.acquireReferenceSignal.connect(worker.acquire_reference)
    widget.runScanSignal.connect(worker.run_scan)
    widget.cancelScanSignal.connect(worker.cancel_scan)

    worker.referencePositionSignal.connect(widget.set_reference_position_fields)
    worker.previewFrameReadySignal.connect(widget.show_preview_frame)
    worker.referenceDoneSignal.connect(widget.on_reference_done)
    worker.referenceWarningSignal.connect(widget.on_reference_warning)
    worker.stepFinished1dSignal.connect(widget.update_1d_curve)
    worker.progressSignal.connect(widget.update_progress)
    worker.etaSignal.connect(widget.update_eta_live)
    worker.scanCompletedSignal.connect(widget.on_scan_completed)
    worker.scanAbortedSignal.connect(widget.on_scan_aborted)
    worker.cancelledSignal.connect(widget.on_scan_cancelled)
    worker.errorSignal.connect(widget.on_error)

    thread.start()

    def _cleanup():
        # Red de seguridad secundaria: el cierre normal ya lo maneja
        # PySpectrumWindow.closeEvent() explícitamente. Durante el apagado del
        # intérprete o en fixtures de test, el objeto C++ de QThread puede haber
        # sido liberado ya por Qt antes de que se dispare esta señal — no debe
        # propagar una excepción en ese caso.
        try:
            thread.quit()
            thread.wait(3000)
        except RuntimeError:
            pass
    widget.destroyed.connect(_cleanup)

    widget._linescan_thread = thread
    widget._linescan_worker = worker
    return widget, worker, thread
