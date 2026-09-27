# -*- coding: utf-8 -*-
"""
static_raman.py — Módulo de Adquisición y Procesamiento Raman Estático & Termometría
PySpectrum 3.0 — UNSAM Nanofotónica

Funcionalidades:
  - Adquisición estática ultra-rápida (Single-Shot y Live Raman) sin escaneo mecánico de red.
  - Preconfiguración automática de ventanas:
      * Huella Dactilar Raman (Stokes): Centrado para cubrir ~500 a 2000 cm⁻¹.
      * Stokes + Anti-Stokes Simétrico: Centrado en la línea láser para termometría in-situ.
      * Manual: Definición libre del centro espectral.
  - Selección de láseres compartidos con PyPrinting (config.SHUTTERS): 532 nm, 637 nm, 592 nm, 808 nm.
  - Red por defecto: 150 l/mm (exploratoria de amplio ancho de banda), conmutación ágil a 1200 l/mm.
  - Procesamiento numérico en vivo con core/raman_engine.py:
      * Conversión directa nm <-> Raman Shift (cm⁻¹).
      * Despiking de rayos cósmicos.
      * Sustracción de línea base (AsLS, AirPLS, ModPoly).
      * Suavizado Savitzky-Golay.
  - Cursores interactivos duales (A y B) con cálculo en vivo de:
      * Cociente de intensidades I_Stokes / I_Anti-Stokes.
      * Termometría fototérmica instantánea (K y °C).
  - Exportación 1-clic a TXT con metadatos completos y portapapeles TSV.

Fase 3 del Rework Arquitectónico (docs/decisions/DECISION_LOG.md#DEC-017): selector de modo de
lectura Andor (FVB/Single-Track/Multi-Track/Imagen 2D) con herencia automática del ROI vertical
de SpectroscopyContext en Single-Track, transición segura vía transition_read_mode()
(Fase 1). Las adquisiciones 2D (Multi-Track/Imagen 2D) se propagan a
pyspectrum/ui/raman_2d_inspector.py::Raman2DInspectorWidget mediante frame2DAcquiredSignal,
consumido por el contenedor pyspectrum/ui/static_raman_container.py::StaticRamanTabContainer.
"""
from __future__ import annotations
import math
import time
from pathlib import Path
from typing import Optional, Dict, Tuple, Any

import numpy as np
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import pyqtSignal, pyqtSlot, QTimer
import pyqtgraph as pg

from config import SHUTTERS, SAFE_MODE
from pyspectrum.drivers.shamrock_driver import (
    DEVICE, GRATING_150_LINES, GRATING_1200_LINES, NAME_GRATINGS, SHAMROCK_SUCCESS, get_shamrock,
    nominal_dispersion_nm_per_px,
)
from pyspectrum.drivers.andor_ccd_driver import (
    get_andor_ccd, DRV_SUCCESS, DRV_ACQUIRING, DETECTOR_WIDTH_PX,
    READ_MODE_FVB, READ_MODE_SINGLE_TRACK, READ_MODE_MULTI_TRACK, READ_MODE_IMAGE,
)
from pyspectrum.modules.spectroscopy_context import spectroscopy_context
from pyspectrum.ui.acquisition_setup_dialog import AcquisitionSetupDialog, transition_read_mode
from core.raman_engine import (
    wavelength_to_raman_shift,
    raman_shift_to_wavelength,
    remove_cosmic_rays,
    baseline_asls,
    baseline_airpls,
    baseline_modpoly,
    smooth_savgol,
    calculate_photothermal_temperature,
    compute_dual_cursor_metrics,
    RAMAN_REFERENCE_STANDARDS,
    BOLTZMANN_CONST,
    PLANCK_CONSTANT,
    SPEED_OF_LIGHT
)


# Mapeo de nombres en config.SHUTTERS a longitudes de onda nominales (nm)
LASER_WAVELENGTH_MAP = {
    "532 nm (green)": 532.0,
    "637 nm (red)": 637.0,
    "592 nm (yellow)": 592.0,
    "808 nm (IR)": 808.0
}


class StaticRamanWidget(QtWidgets.QWidget):
    """Interfaz gráfica para el módulo de Raman Estático y Termometría."""

    requestAcquireSingleSignal = pyqtSignal()
    toggleLiveRamanSignal = pyqtSignal(bool)
    applySpectrometerConfigSignal = pyqtSignal(int, float)  # grating_idx (1-based), wl_center_nm
    saveSpectrumSignal = pyqtSignal(str, dict)  # path, metadata
    copyClipboardSignal = pyqtSignal()
    setReadModeSignal = pyqtSignal(int, int)  # (read_mode, n_tracks)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.laser_nm: float = 532.0
        self.use_raman_shift: bool = True
        self.raw_wl: np.ndarray = np.array([])
        self.raw_counts: np.ndarray = np.array([])
        self.processed_x: np.ndarray = np.array([])
        self.processed_y: np.ndarray = np.array([])
        self.baseline_y: np.ndarray = np.array([])

        self._setup_styles()
        self._setup_ui()
        self._connect_internal_signals()

    def _setup_styles(self):
        self.setStyleSheet("""
            QWidget {
                background-color: #181825;
                color: #CDD6F4;
            }
            QGroupBox {
                border: 1px solid #313244;
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 10px;
                font-weight: bold;
                color: #89B4FA;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 4px;
            }
            QLabel {
                color: #CDD6F4;
            }
            QPushButton {
                background-color: #313244;
                color: #CDD6F4;
                border: 1px solid #45475A;
                border-radius: 4px;
                padding: 5px 10px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45475A;
                color: #89B4FA;
            }
            QPushButton:disabled {
                background-color: #1E1E2E;
                color: #585B70;
            }
            QComboBox, QLineEdit, QDoubleSpinBox, QSpinBox {
                background-color: #11111B;
                color: #CDD6F4;
                border: 1px solid #45475A;
                border-radius: 4px;
                padding: 3px 6px;
            }
            QCheckBox {
                color: #CDD6F4;
                spacing: 6px;
            }
        """)

    def _setup_ui(self):
        main_vlo = QtWidgets.QVBoxLayout(self)
        main_vlo.setContentsMargins(8, 8, 8, 8)
        main_vlo.setSpacing(6)

        # ── 1. Barra Superior: Parámetros del Espectrómetro & Láser ───────────
        grp_hw = QtWidgets.QGroupBox("⚙️ Configuración Óptica & Ventana Espectral")
        hw_vlo = QtWidgets.QVBoxLayout(grp_hw)
        hw_vlo.setSpacing(6)

        # Fila 1: Láser y Red de difracción
        row1 = QtWidgets.QHBoxLayout()
        row1.addWidget(QtWidgets.QLabel("Láser Excitación:"))
        self.cmb_laser = QtWidgets.QComboBox()
        for s in SHUTTERS:
            self.cmb_laser.addItem(f"🔦 {s}", LASER_WAVELENGTH_MAP.get(s, 532.0))
        self.cmb_laser.addItem("✏️ Personalizado...", -1.0)
        self.cmb_laser.setToolTip("Láser de bombeo óptico utilizado para la excitación inelástica Raman.")
        row1.addWidget(self.cmb_laser)

        self.spin_laser_custom = QtWidgets.QDoubleSpinBox()
        self.spin_laser_custom.setRange(200.0, 1500.0)
        self.spin_laser_custom.setValue(532.0)
        self.spin_laser_custom.setDecimals(2)
        self.spin_laser_custom.setSuffix(" nm")
        self.spin_laser_custom.setFixedWidth(90)
        self.spin_laser_custom.setEnabled(False)
        self.spin_laser_custom.setToolTip("Longitud de onda personalizada en nm para fuentes láser externas no convencionales.")
        row1.addWidget(self.spin_laser_custom)

        row1.addWidget(QtWidgets.QLabel("Red Shamrock:"))
        self.cmb_grating = QtWidgets.QComboBox()
        # Red 1 (150 l/mm) por defecto (exploratorio)
        self.cmb_grating.addItem("150 l/mm (Blaze 800 nm)", 1)
        self.cmb_grating.addItem("1200 l/mm (Blaze 500 nm)", 2)
        self.cmb_grating.setToolTip(
            "Red de difracción del Shamrock:\n"
            "• 150 l/mm: Cobertura amplia para Stokes y Anti-Stokes simultáneo (termometría).\n"
            "• 1200 l/mm: Alta resolución para desdoblamiento de picos y fonones finos."
        )
        row1.addWidget(self.cmb_grating)

        row1.addStretch()
        hw_vlo.addLayout(row1)

        # Fila 1b: Modo de Lectura Andor (FVB / Single-Track / Multi-Track / Imagen 2D)
        row1b = QtWidgets.QHBoxLayout()
        row1b.addWidget(QtWidgets.QLabel("Modo de Lectura:"))
        self.cmb_read_mode = QtWidgets.QComboBox()
        self.cmb_read_mode.addItem("FVB (1D Spectrum)", READ_MODE_FVB)
        self.cmb_read_mode.addItem("Single-Track (Hardware ROI)", READ_MODE_SINGLE_TRACK)
        self.cmb_read_mode.addItem("Multi-Track", READ_MODE_MULTI_TRACK)
        self.cmb_read_mode.addItem("Imagen 2D (Hardware ROI)", READ_MODE_IMAGE)
        self.cmb_read_mode.setToolTip(
            "Modo de lectura del sensor Andor para esta adquisición Raman:\n"
            "• FVB: Binnizado vertical completo en hardware (espectro 1D).\n"
            "• Single-Track: Lee sólo las filas del ROI vertical heredado automáticamente de la Pestaña 1 (Exploración).\n"
            "• Multi-Track: N pistas paralelas simultáneas (ej. señal vs fondo), visualizadas en el Inspector 2D.\n"
            "• Imagen 2D: Matriz 2D acotada estrictamente por hardware al ROI vertical para análisis espacial en el Inspector 2D."
        )
        self.cmb_read_mode.currentIndexChanged.connect(self._on_read_mode_changed)
        row1b.addWidget(self.cmb_read_mode)

        self.lbl_multi_track_n = QtWidgets.QLabel("N Pistas:")
        row1b.addWidget(self.lbl_multi_track_n)
        self.spin_multi_track_n = QtWidgets.QSpinBox()
        self.spin_multi_track_n.setRange(2, 8)
        self.spin_multi_track_n.setValue(2)
        self.spin_multi_track_n.setToolTip("Número de pistas paralelas a leer simultáneamente en modo Multi-Track.")
        self.spin_multi_track_n.valueChanged.connect(lambda _v: self._on_read_mode_changed())
        row1b.addWidget(self.spin_multi_track_n)

        self.lbl_roi_inherited = QtWidgets.QLabel("")
        self.lbl_roi_inherited.setStyleSheet("color: #A6E3A1; font-style: italic;")
        self.lbl_roi_inherited.setToolTip("ROI vertical heredado automáticamente de spectroscopy_context (Pestaña 1: Exploración).")
        row1b.addWidget(self.lbl_roi_inherited)

        row1b.addStretch()
        hw_vlo.addLayout(row1b)

        # Fila 2: Modos de Ventana Preconfigurados
        row2 = QtWidgets.QHBoxLayout()
        row2.addWidget(QtWidgets.QLabel("Modo Ventana:"))
        self.cmb_mode = QtWidgets.QComboBox()
        self.cmb_mode.addItem("🔍 Huella Dactilar Raman (Stokes)", "stokes")
        self.cmb_mode.addItem("⚖️ Stokes + Anti-Stokes Simétrico (Termometría)", "symmetric")
        self.cmb_mode.addItem("🖐️ Manual", "manual")
        self.cmb_mode.setToolTip(
            "Ventana espectral preconfigurada:\n"
            "• Huella Dactilar: Centrado en rango Stokes (500 a 2000 cm⁻¹).\n"
            "• Simétrico: Centrado en la línea láser para cocientes Stokes/Anti-Stokes (termometría in-situ).\n"
            "• Manual: Control libre del centroide espectral."
        )
        row2.addWidget(self.cmb_mode)

        row2.addWidget(QtWidgets.QLabel("Centro Espectrógrafo:"))
        self.spin_center_wl = QtWidgets.QDoubleSpinBox()
        self.spin_center_wl.setRange(300.0, 1200.0)
        self.spin_center_wl.setValue(565.0)
        self.spin_center_wl.setDecimals(2)
        self.spin_center_wl.setSuffix(" nm")
        self.spin_center_wl.setFixedWidth(95)
        self.spin_center_wl.setToolTip("Longitud de onda central (nm) configurada en el espectrógrafo Shamrock.")
        row2.addWidget(self.spin_center_wl)

        self.lbl_shift_center = QtWidgets.QLabel("≈ +1098 cm⁻¹")
        self.lbl_shift_center.setStyleSheet("color: #89B4FA; font-weight: bold;")
        self.lbl_shift_center.setToolTip("Corrimiento Raman equivalente correspondiente al centro espectral actual.")
        row2.addWidget(self.lbl_shift_center)

        self.btn_apply_spectrometer = QtWidgets.QPushButton("🚀 Sintonizar Espectrógrafo")
        self.btn_apply_spectrometer.setStyleSheet("background-color: #89B4FA; color: #11111B;")
        self.btn_apply_spectrometer.setToolTip("Comanda al espectrógrafo para posicionar la red y el centroide de longitud de onda seleccionado.")
        row2.addWidget(self.btn_apply_spectrometer)

        row2.addStretch()
        hw_vlo.addLayout(row2)

        # Fila 2b: Cartel de Rango Espectral Dinámico
        row2b = QtWidgets.QHBoxLayout()
        self.lbl_spectral_range = QtWidgets.QLabel("📊 Rango Espectral Cubierto: —")
        self.lbl_spectral_range.setStyleSheet("""
            QLabel {
                color: #A6E3A1;
                background-color: #11111B;
                border: 1px solid #313244;
                border-radius: 4px;
                padding: 4px 8px;
                font-weight: bold;
            }
        """)
        self.lbl_spectral_range.setToolTip("Rango espectral cubierto en el detector Andor según la red de difracción y centro seleccionados.")
        row2b.addWidget(self.lbl_spectral_range)
        row2b.addStretch()
        hw_vlo.addLayout(row2b)

        main_vlo.addWidget(grp_hw)

        # ── 2. Barra de Procesamiento Numérico en Vivo ────────────────────────
        grp_proc = QtWidgets.QGroupBox("🧮 Algoritmos de Procesamiento en Tiempo Real")
        proc_hlo = QtWidgets.QHBoxLayout(grp_proc)
        proc_hlo.setSpacing(12)

        # Eje X: cm^-1 vs nm
        self.chk_raman_shift = QtWidgets.QCheckBox("Mostrar Raman Shift (cm⁻¹)")
        self.chk_raman_shift.setChecked(True)
        self.chk_raman_shift.setToolTip("Alterna el eje horizontal entre longitud de onda (nm) y corrimiento Raman relativo (cm⁻¹).")
        proc_hlo.addWidget(self.chk_raman_shift)

        # Despiking
        self.chk_despike = QtWidgets.QCheckBox("Despiking Rayos Cósmicos")
        self.chk_despike.setChecked(True)
        self.chk_despike.setToolTip("Elimina automáticamente picos espurios y estrechos provocados por rayos cósmicos sobre el CCD.")
        proc_hlo.addWidget(self.chk_despike)

        # Línea Base
        self.chk_baseline = QtWidgets.QCheckBox("Sustraer Línea Base:")
        self.chk_baseline.setChecked(False)
        self.chk_baseline.setToolTip("Calcula y sustrae el fondo de fluorescencia y dispersión no resonante.")
        proc_hlo.addWidget(self.chk_baseline)

        self.cmb_baseline = QtWidgets.QComboBox()
        self.cmb_baseline.addItem("AsLS (Asymmetric Least Squares)", "asls")
        self.cmb_baseline.addItem("AirPLS (Adaptive Iterative Reweighted)", "airpls")
        self.cmb_baseline.addItem("ModPoly (Polinomial Modificado)", "modpoly")
        self.cmb_baseline.setToolTip(
            "Algoritmo de ajuste de línea base:\n"
            "• AsLS: Mínimos cuadrados asimétricos.\n"
            "• AirPLS: Mínimos cuadrados ponderados iterativos adaptativos.\n"
            "• ModPoly: Ajuste polinomial modificado."
        )
        proc_hlo.addWidget(self.cmb_baseline)

        # Suavizado Savitzky-Golay
        self.chk_savgol = QtWidgets.QCheckBox("Suavizado Savitzky-Golay")
        self.chk_savgol.setChecked(False)
        self.chk_savgol.setToolTip("Filtro polinomial Savitzky-Golay para suavizado reduciendo el ruido de alta frecuencia.")
        proc_hlo.addWidget(self.chk_savgol)

        self.spin_savgol_win = QtWidgets.QSpinBox()
        self.spin_savgol_win.setRange(5, 51)
        self.spin_savgol_win.setSingleStep(2)
        self.spin_savgol_win.setValue(11)
        self.spin_savgol_win.setSuffix(" pts")
        self.spin_savgol_win.setFixedWidth(70)
        self.spin_savgol_win.setToolTip("Tamaño de la ventana de puntos impares para el filtro Savitzky-Golay.")
        proc_hlo.addWidget(self.spin_savgol_win)

        proc_hlo.addStretch()
        main_vlo.addWidget(grp_proc)

        # ── 3. Visualizador Gráfico PyQtGraph ─────────────────────────────────
        self.plot_widget = pg.PlotWidget(title="Espectro Raman Estático")
        self.plot_widget.setBackground("#11111B")
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.setLabel('bottom', "Corrimiento Raman (cm⁻¹)", color='#CDD6F4', size='10pt')
        self.plot_widget.setLabel('left', "Intensidad / Cuentas (ADC)", color='#CDD6F4', size='10pt')

        # Curvas
        self.curve_raw = self.plot_widget.plot(name="Espectro Crudo", pen=pg.mkPen(color="#585B70", width=1, style=QtCore.Qt.PenStyle.DotLine))
        self.curve_baseline = self.plot_widget.plot(name="Línea Base", pen=pg.mkPen(color="#FAB387", width=1.5, style=QtCore.Qt.PenStyle.DashLine))
        self.curve_proc = self.plot_widget.plot(name="Espectro Procesado", pen=pg.mkPen(color="#A6E3A1", width=2))

        # Cursores duales A y B
        self.cursor_a = pg.InfiniteLine(pos=520.0, angle=90, movable=True, pen=pg.mkPen(color="#89B4FA", width=2))
        self.cursor_b = pg.InfiniteLine(pos=-520.0, angle=90, movable=True, pen=pg.mkPen(color="#F38BA8", width=2))
        self.plot_widget.addItem(self.cursor_a)
        self.plot_widget.addItem(self.cursor_b)

        # Etiquetas flotantes sobre los cursores
        self.lbl_cursor_a_tag = pg.TextItem(text="A", color="#89B4FA", anchor=(0.5, 1.2))
        self.lbl_cursor_b_tag = pg.TextItem(text="B", color="#F38BA8", anchor=(0.5, 1.2))
        self.plot_widget.addItem(self.lbl_cursor_a_tag)
        self.plot_widget.addItem(self.lbl_cursor_b_tag)

        main_vlo.addWidget(self.plot_widget, stretch=1)

        # ── 4. Panel Inferior: Telemetría de Cursores & Termometría ───────────
        telemetry_box = QtWidgets.QFrame()
        telemetry_box.setStyleSheet("background-color: #11111B; border-radius: 4px; padding: 4px; border: 1px solid #313244;")
        tel_hlo = QtWidgets.QHBoxLayout(telemetry_box)
        tel_hlo.setSpacing(15)

        self.lbl_cursor_a_info = QtWidgets.QLabel("🔵 <b>Cursor A:</b> -- cm⁻¹ | -- cts")
        self.lbl_cursor_b_info = QtWidgets.QLabel("🔴 <b>Cursor B:</b> -- cm⁻¹ | -- cts")
        self.lbl_diff_info = QtWidgets.QLabel("📏 <b>Δν:</b> -- cm⁻¹ | <b>IA/IB:</b> --")
        self.lbl_temp_info = QtWidgets.QLabel("🌡️ <b>Temp Fototérmica:</b> -- K (-- °C)")
        self.lbl_temp_info.setStyleSheet("color: #F9E2AF; font-weight: bold;")

        self.lbl_cursor_a_info.setToolTip("Posición espectral e intensidad del Cursor A (azul).")
        self.lbl_cursor_b_info.setToolTip("Posición espectral e intensidad del Cursor B (rojo).")
        self.lbl_diff_info.setToolTip("Diferencia de frecuencia (Δν) y cociente de intensidades (IA/IB) entre ambos cursores.")
        self.lbl_temp_info.setToolTip("Temperatura fototérmica estimada mediante la ley de distribución de Boltzmann para los modos Stokes y Anti-Stokes.")

        tel_hlo.addWidget(self.lbl_cursor_a_info)
        tel_hlo.addWidget(self.lbl_cursor_b_info)
        tel_hlo.addWidget(self.lbl_diff_info)
        tel_hlo.addWidget(self.lbl_temp_info)
        tel_hlo.addStretch()

        main_vlo.addWidget(telemetry_box)

        # ── 5. Botones de Acción & Exportación ─────────────────────────────────
        actions_hlo = QtWidgets.QHBoxLayout()

        self.btn_single = QtWidgets.QPushButton("📸 Capturar Espectro Único")
        self.btn_single.setToolTip("Adquiere un único cuadro Raman estático de alta fidelidad.")
        self.btn_single.clicked.connect(self._on_acquire_single)
        actions_hlo.addWidget(self.btn_single)

        self.btn_live = QtWidgets.QPushButton("▶️ Live Raman (Continuo)")
        self.btn_live.setCheckable(True)
        self.btn_live.setToolTip("Inicia o detiene la adquisición continua en tiempo real (Live Raman) actualizando termometría.")
        self.btn_live.clicked.connect(self._on_toggle_live)
        actions_hlo.addWidget(self.btn_live)

        actions_hlo.addStretch()

        self.btn_copy_tsv = QtWidgets.QPushButton("📋 Copiar Datos (TSV)")
        self.btn_copy_tsv.setToolTip("Copia los datos de dispersión e intensidad al portapapeles en formato TSV compatible con Excel y Origin.")
        self.btn_copy_tsv.clicked.connect(self._on_copy_tsv)
        actions_hlo.addWidget(self.btn_copy_tsv)

        self.btn_save = QtWidgets.QPushButton("💾 Guardar Espectro (.txt)")
        self.btn_save.setToolTip("Guarda el espectro procesado con metadatos completos en un archivo de texto (.txt).")
        self.btn_save.clicked.connect(self._on_save_spectrum)
        actions_hlo.addWidget(self.btn_save)

        main_vlo.addLayout(actions_hlo)

    def _connect_internal_signals(self):
        self.cmb_laser.currentIndexChanged.connect(self._on_laser_combo_changed)
        self.spin_laser_custom.valueChanged.connect(self._on_laser_value_changed)
        self.cmb_mode.currentIndexChanged.connect(self._on_mode_changed)
        self.cmb_grating.currentIndexChanged.connect(self._on_mode_changed)
        self.spin_center_wl.valueChanged.connect(self._on_center_wl_changed)
        self.btn_apply_spectrometer.clicked.connect(self._on_apply_spectrometer)

        self.chk_raman_shift.toggled.connect(self._reprocess_current_spectrum)
        self.chk_raman_shift.toggled.connect(self._update_spectral_range_badge)
        self.chk_despike.toggled.connect(self._reprocess_current_spectrum)
        self.chk_baseline.toggled.connect(self._reprocess_current_spectrum)
        self.cmb_baseline.currentIndexChanged.connect(self._reprocess_current_spectrum)
        self.chk_savgol.toggled.connect(self._reprocess_current_spectrum)
        self.spin_savgol_win.valueChanged.connect(self._reprocess_current_spectrum)

        self.cursor_a.sigPositionChanged.connect(self._update_telemetry)
        self.cursor_b.sigPositionChanged.connect(self._update_telemetry)

        # Mantiene la etiqueta de ROI heredado sincronizada en vivo si el operador mueve el
        # ROI en la Pestaña 1 (Exploración) mientras Static Raman está en modo Single-Track o Imagen 2D.
        spectroscopy_context.verticalRoiChanged.connect(self._on_context_roi_changed)

        # Configuración inicial de modo y centro
        self._on_mode_changed()
        self._on_read_mode_changed()
        self._update_spectral_range_badge()

    # ── Manejadores de Interfaz ───────────────────────────────────────────────
    def _on_laser_combo_changed(self, idx: int):
        val = self.cmb_laser.currentData()
        if val < 0:
            self.spin_laser_custom.setEnabled(True)
            self.laser_nm = float(self.spin_laser_custom.value())
        else:
            self.spin_laser_custom.setEnabled(False)
            self.laser_nm = float(val)
            self.spin_laser_custom.setValue(self.laser_nm)
        self._on_mode_changed()
        self._reprocess_current_spectrum()

    def _on_laser_value_changed(self, val: float):
        if self.cmb_laser.currentData() < 0:
            self.laser_nm = float(val)
            self._on_mode_changed()
            self._reprocess_current_spectrum()

    def _on_mode_changed(self):
        mode = self.cmb_mode.currentData()
        grating = self.cmb_grating.currentData()

        if mode == "symmetric":
            # Modo simétrico centrado exactamente en la longitud de onda láser
            center = self.laser_nm
            self.spin_center_wl.setValue(center)
            self.spin_center_wl.setEnabled(False)
        elif mode == "stokes":
            # Modo Huella Dactilar: centrado a ~1100 cm^-1 hacia el Stokes
            # Con 150 l/mm a 532 nm, centro ~565 nm cubre de ~478 a 652 nm (-2100 a +3400 cm^-1)
            # Con 1200 l/mm a 532 nm, centro ~562 nm cubre ~1000 cm^-1
            target_shift = 1100.0 if grating == 1 else 1000.0
            center = float(raman_shift_to_wavelength(target_shift, self.laser_nm))
            self.spin_center_wl.setValue(center)
            self.spin_center_wl.setEnabled(False)
        else:
            # Modo manual
            self.spin_center_wl.setEnabled(True)

        self._on_center_wl_changed(self.spin_center_wl.value())

    def _on_center_wl_changed(self, wl: float):
        if wl > 0 and self.laser_nm > 0:
            shift = float(wavelength_to_raman_shift(wl, self.laser_nm))
            sign = "+" if shift >= 0 else ""
            self.lbl_shift_center.setText(f"≈ {sign}{shift:.1f} cm⁻¹")
        self._update_spectral_range_badge()

    def _update_spectral_range_badge(self):
        center_wl = float(self.spin_center_wl.value())
        grating_data = self.cmb_grating.currentData()
        grating_idx = int(grating_data) if grating_data is not None else 1

        if len(self.raw_wl) > 1 and math.isclose(self.raw_wl[len(self.raw_wl) // 2], center_wl, abs_tol=2.0):
            wl_min = float(self.raw_wl[0])
            wl_max = float(self.raw_wl[-1])
        else:
            # Estimación previa a la primera adquisición: dispersión nominal (DEC-033).
            if grating_idx in (GRATING_150_LINES, GRATING_1200_LINES):
                dispersion = nominal_dispersion_nm_per_px(grating_idx)
            else:
                dispersion = 0.10
            half_span = (DETECTOR_WIDTH_PX / 2.0) * dispersion
            wl_min = max(0.0, center_wl - half_span)
            wl_max = center_wl + half_span

        wl_span = wl_max - wl_min

        if self.chk_raman_shift.isChecked() and self.laser_nm > 0:
            shift_at_wl_min = float(wavelength_to_raman_shift(wl_min, self.laser_nm))
            shift_at_wl_max = float(wavelength_to_raman_shift(wl_max, self.laser_nm))
            s_min, s_max = min(shift_at_wl_min, shift_at_wl_max), max(shift_at_wl_min, shift_at_wl_max)
            self.lbl_spectral_range.setText(
                f"📊 Rango Espectral Cubierto: [{s_min:+.0f} a {s_max:+.0f}] cm⁻¹  (λ: {wl_min:.1f} a {wl_max:.1f} nm, Δλ ≈ {wl_span:.1f} nm)"
            )
        else:
            self.lbl_spectral_range.setText(
                f"📊 Rango Espectral Cubierto: [{wl_min:.1f} a {wl_max:.1f}] nm  (Δλ ≈ {wl_span:.1f} nm)"
            )

    def _on_apply_spectrometer(self):
        grating_idx = int(self.cmb_grating.currentData())
        wl_center = float(self.spin_center_wl.value())
        self.applySpectrometerConfigSignal.emit(grating_idx, wl_center)

    def _on_read_mode_changed(self, _idx: int = -1):
        mode = self.cmb_read_mode.currentData()
        is_multi = (mode == READ_MODE_MULTI_TRACK)
        self.lbl_multi_track_n.setVisible(is_multi)
        self.spin_multi_track_n.setVisible(is_multi)

        if mode in (READ_MODE_SINGLE_TRACK, READ_MODE_IMAGE):
            self._update_inherited_roi_label()
        else:
            self.lbl_roi_inherited.setText("")

        n_tracks = int(self.spin_multi_track_n.value()) if is_multi else 1
        self.setReadModeSignal.emit(int(mode), n_tracks)

    def _update_inherited_roi_label(self):
        y_min, y_max, y_center, y_height = spectroscopy_context.vertical_roi
        self.lbl_roi_inherited.setText(f"ROI heredado: [{y_min}:{y_max}] (Centro: {y_center}, Alto: {y_height} px)")

    def _on_context_roi_changed(self, y_min: int, y_max: int, y_center: int, y_height: int):
        if self.cmb_read_mode.currentData() in (READ_MODE_SINGLE_TRACK, READ_MODE_IMAGE):
            self.lbl_roi_inherited.setText(f"ROI heredado: [{y_min}:{y_max}] (Centro: {y_center}, Alto: {y_height} px)")

    def _on_acquire_single(self):
        self.requestAcquireSingleSignal.emit()

    def _apply_live_appearance(self, running: bool):
        if running:
            self.btn_live.setText("⏹️ Detener Live Raman")
            self.btn_live.setStyleSheet("background-color: #F38BA8; color: #11111B;")
        else:
            self.btn_live.setText("▶️ Live Raman (Continuo)")
            self.btn_live.setStyleSheet("background-color: #313244; color: #CDD6F4;")

    def _on_toggle_live(self, checked: bool):
        self._apply_live_appearance(checked)
        self.toggleLiveRamanSignal.emit(bool(checked))

    def set_live_state(self, running: bool):
        """Refleja el estado REAL de Live informado por el backend, sin re-emitir
        toggleLiveRamanSignal. Existe para que un arranque fallido pueda devolver el botón a
        'Live Raman' en vez de dejarlo mostrando 'Detener' con nada corriendo (estado de
        software adelantado al de hardware — DEC-014). blockSignals evita que el setChecked
        programático vuelva a disparar _on_toggle_live y rebote hacia el backend."""
        self.btn_live.blockSignals(True)
        self.btn_live.setChecked(bool(running))
        self.btn_live.blockSignals(False)
        self._apply_live_appearance(bool(running))

    # ── Pipeline de Procesamiento en Tiempo Real ──────────────────────────────
    @pyqtSlot(np.ndarray, np.ndarray)
    def update_spectrum_data(self, wl_axis: np.ndarray, counts: np.ndarray):
        """Recibe un nuevo espectro adquirido (longitudes de onda y cuentas)."""
        self.raw_wl = wl_axis
        self.raw_counts = counts
        self._reprocess_current_spectrum()
        self._update_spectral_range_badge()

    def _reprocess_current_spectrum(self):
        if len(self.raw_wl) == 0 or len(self.raw_counts) == 0:
            return

        y_proc = self.raw_counts.copy().astype(np.float64)

        # 1. Despiking de Rayos Cósmicos
        if self.chk_despike.isChecked() and len(y_proc) > 7:
            y_proc, _ = remove_cosmic_rays(y_proc, threshold=6.0, window_size=5)

        # 2. Corrección de Línea Base
        base = np.zeros_like(y_proc)
        if self.chk_baseline.isChecked() and len(y_proc) > 10:
            algo = self.cmb_baseline.currentData()
            try:
                if algo == "asls":
                    base = baseline_asls(y_proc, lam=1e5, p=0.001)
                elif algo == "airpls":
                    base = baseline_airpls(y_proc, lam=1e5)
                elif algo == "modpoly":
                    base = baseline_modpoly(y_proc, poly_order=4)
                y_proc = np.maximum(0.0, y_proc - base)
            except Exception:
                base = np.zeros_like(y_proc)

        # 3. Suavizado Savitzky-Golay
        if self.chk_savgol.isChecked() and len(y_proc) > 15:
            win = self.spin_savgol_win.value()
            if win % 2 == 0:
                win += 1
            if win > len(y_proc):
                win = len(y_proc) - 1 if (len(y_proc) - 1) % 2 != 0 else len(y_proc) - 2
            if win >= 5:
                y_proc = smooth_savgol(y_proc, window_length=win, polyorder=3)

        # 4. Eje X: Longitud de Onda o Raman Shift
        self.use_raman_shift = self.chk_raman_shift.isChecked()
        if self.use_raman_shift:
            x_axis = wavelength_to_raman_shift(self.raw_wl, self.laser_nm)
            self.plot_widget.setLabel('bottom', "Corrimiento Raman (cm⁻¹)", color='#CDD6F4', size='10pt')
        else:
            x_axis = self.raw_wl
            self.plot_widget.setLabel('bottom', "Longitud de Onda (nm)", color='#CDD6F4', size='10pt')

        self.processed_x = x_axis
        self.processed_y = y_proc
        self.baseline_y = base

        # 5. Renderizado en Plot
        self.curve_raw.setData(x_axis, self.raw_counts)
        if self.chk_baseline.isChecked():
            self.curve_baseline.setData(x_axis, base)
            self.curve_baseline.show()
        else:
            self.curve_baseline.hide()
        self.curve_proc.setData(x_axis, y_proc)

        self._update_telemetry()

    def _update_telemetry(self):
        if len(self.processed_x) == 0 or len(self.processed_y) == 0:
            return

        pos_a = self.cursor_a.value()
        pos_b = self.cursor_b.value()

        # Posicionar etiquetas A y B
        view_box = self.plot_widget.getViewBox()
        view_range_y = view_box.viewRange()[1]
        y_top = view_range_y[1] if view_range_y else 0
        self.lbl_cursor_a_tag.setPos(pos_a, y_top * 0.95)
        self.lbl_cursor_b_tag.setPos(pos_b, y_top * 0.95)

        # Interpolar intensidad en posición del cursor
        idx_a = int(np.clip(np.argmin(np.abs(self.processed_x - pos_a)), 0, len(self.processed_y) - 1))
        idx_b = int(np.clip(np.argmin(np.abs(self.processed_x - pos_b)), 0, len(self.processed_y) - 1))

        val_a_x = self.processed_x[idx_a]
        val_a_y = self.processed_y[idx_a]
        val_b_x = self.processed_x[idx_b]
        val_b_y = self.processed_y[idx_b]

        unit = "cm⁻¹" if self.use_raman_shift else "nm"
        self.lbl_cursor_a_info.setText(f"🔵 <b>Cursor A:</b> {val_a_x:.1f} {unit} | <b>{val_a_y:.0f}</b> cts")
        self.lbl_cursor_b_info.setText(f"🔴 <b>Cursor B:</b> {val_b_x:.1f} {unit} | <b>{val_b_y:.0f}</b> cts")

        delta_x = abs(val_b_x - val_a_x)
        ratio = (val_a_y / val_b_y) if val_b_y > 1e-6 else 0.0
        self.lbl_diff_info.setText(f"📏 <b>|Δ|:</b> {delta_x:.1f} {unit} | <b>IA/IB:</b> {ratio:.2f}")

        # Cálculo de Termometría Fototérmica Anti-Stokes / Stokes
        if self.use_raman_shift:
            # Determinar cuál cursor está en Anti-Stokes (<0) y cuál en Stokes (>0)
            if (val_a_x < -20.0 and val_b_x > 20.0) or (val_b_x < -20.0 and val_a_x > 20.0):
                if val_a_x < 0:
                    i_as, i_stokes = val_a_y, val_b_y
                    shift = abs(val_b_x)
                else:
                    i_as, i_stokes = val_b_y, val_a_y
                    shift = abs(val_a_x)

                if i_as > 10.0 and i_stokes > 10.0:
                    try:
                        t_k = calculate_photothermal_temperature(
                            i_anti_stokes=i_as,
                            i_stokes=i_stokes,
                            delta_nu_cm1=shift,
                            laser_wavelength_nm=self.laser_nm
                        )
                        t_c = t_k - 273.15
                        if 100.0 <= t_k <= 2000.0:
                            self.lbl_temp_info.setText(f"🌡️ <b>Temp Fototérmica:</b> {t_k:.1f} K (<b>{t_c:.1f} °C</b>)")
                            return
                    except Exception:
                        pass
        self.lbl_temp_info.setText("🌡️ <b>Temp Fototérmica:</b> -- K (-- °C)")

    # ── Exportación y Portapapeles ────────────────────────────────────────────
    def _on_copy_tsv(self):
        if len(self.processed_x) == 0:
            return
        unit = "Raman_Shift_cm-1" if self.use_raman_shift else "Wavelength_nm"
        lines = [f"{unit}\tRaw_Counts\tProcessed_Counts\tBaseline"]
        for x, y_raw, y_proc, b in zip(self.processed_x, self.raw_counts, self.processed_y, self.baseline_y):
            lines.append(f"{x:.3f}\t{y_raw:.1f}\t{y_proc:.1f}\t{b:.1f}")
        tsv_data = "\n".join(lines)

        clipboard = QtWidgets.QApplication.clipboard()
        clipboard.setText(tsv_data)
        self.copyClipboardSignal.emit()
        QtWidgets.QToolTip.showText(QtGui.QCursor.pos(), "✅ Datos copiados al portapapeles (TSV)")

    def _on_save_spectrum(self):
        if len(self.processed_x) == 0:
            return
        default_name = f"Raman_Static_{int(self.laser_nm)}nm_{time.strftime('%Y%m%d_%H%M%S')}.txt"
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Guardar Espectro Raman Estático", default_name, "Archivos de Texto (*.txt);;CSV (*.csv)"
        )
        if not path:
            return

        metadata = {
            "Fecha": time.strftime("%Y-%m-%d %H:%M:%S"),
            "Laser_Excitacion_nm": f"{self.laser_nm:.2f}",
            "Red_Difraccion": self.cmb_grating.currentText(),
            "Centro_Espectrografo_nm": f"{self.spin_center_wl.value():.2f}",
            "Modo_Ventana": self.cmb_mode.currentText(),
            "Despiking": str(self.chk_despike.isChecked()),
            "Linea_Base": f"{self.cmb_baseline.currentText()}" if self.chk_baseline.isChecked() else "Ninguna",
            "Savitzky_Golay": f"Ventana {self.spin_savgol_win.value()}" if self.chk_savgol.isChecked() else "No",
            "_raw_wl": self.raw_wl.copy(),
            "_raw_counts": self.raw_counts.copy(),
            "_processed_x": self.processed_x.copy(),
            "_processed_y": self.processed_y.copy(),
            "_baseline_y": self.baseline_y.copy() if len(self.baseline_y) else np.zeros_like(self.raw_counts),
        }
        self.saveSpectrumSignal.emit(path, metadata)


class StaticRamanBackend(QtCore.QObject):
    """Controlador y orquestador físico para Raman Estático y Cámara CCD."""

    spectrumAcquiredSignal = pyqtSignal(np.ndarray, np.ndarray)  # wl_axis, counts (FVB/Single-Track)
    frame2DAcquiredSignal = pyqtSignal(np.ndarray, np.ndarray, str)  # wl_axis, frame2d, read_mode_name (Multi-Track/Imagen 2D)
    statusMessageSignal = pyqtSignal(str)
    # Estado Live efectivamente alcanzado en el hardware (no el pedido por la UI). Es la vía
    # de retorno que faltaba: sin ella, un arranque fallido dejaba el botón en 'Detener'.
    liveStateChangedSignal = pyqtSignal(bool)

    READ_MODE_NAMES = {
        READ_MODE_FVB: "FVB",
        READ_MODE_SINGLE_TRACK: "Single-Track",
        READ_MODE_MULTI_TRACK: "Multi-Track",
        READ_MODE_IMAGE: "Imagen 2D",
    }

    def __init__(self, camera=None, spectrometer=None, parent=None):
        super().__init__(parent)
        self.camera = camera or get_andor_ccd()
        self.spectrometer = spectrometer or get_shamrock()
        self.current_read_mode = READ_MODE_FVB

        self.live_timer = QTimer(self)
        self.live_timer.setInterval(40)  # ~25 FPS
        self.live_timer.timeout.connect(self._acquire_live_frame)

    def make_connection(self, widget: StaticRamanWidget, inspector: Optional[Any] = None):
        widget.requestAcquireSingleSignal.connect(self.acquire_single)
        widget.toggleLiveRamanSignal.connect(self.toggle_live)
        widget.applySpectrometerConfigSignal.connect(self.apply_spectrometer_config)
        widget.saveSpectrumSignal.connect(self.save_spectrum_to_file)
        widget.setReadModeSignal.connect(self.set_read_mode)

        self.spectrumAcquiredSignal.connect(widget.update_spectrum_data)
        self.liveStateChangedSignal.connect(widget.set_live_state)

        if inspector is not None:
            self.frame2DAcquiredSignal.connect(inspector.set_frame_2d)
            if hasattr(inspector, "set_live_state"):
                self.liveStateChangedSignal.connect(inspector.set_live_state)

    @pyqtSlot(int, int)
    def set_read_mode(self, mode: int, n_tracks: int):
        """Ejecuta la transición segura de modo de lectura (Fase 1: transition_read_mode()
        envuelto en AcquisitionSetupDialog). En Single-Track e Imagen 2D hereda automáticamente
        el centro, alto o límites del ROI vertical publicado por la Pestaña 1 vía SpectroscopyContext."""
        kwargs: Dict[str, Any] = {}
        if mode == READ_MODE_SINGLE_TRACK:
            _, _, y_center, y_height = spectroscopy_context.vertical_roi
            kwargs["single_track_center"] = y_center if y_height > 0 else 501
            kwargs["single_track_height"] = y_height if y_height > 0 else 40
        elif mode == READ_MODE_MULTI_TRACK:
            kwargs["n_tracks"] = max(1, int(n_tracks))
            kwargs["multi_track_height"] = 5
        elif mode == READ_MODE_IMAGE:
            y_min, y_max, _, y_height = spectroscopy_context.vertical_roi
            if y_height > 0:
                kwargs["image_vstart"] = y_min + 1
                kwargs["image_vend"] = y_max

        dlg = AcquisitionSetupDialog(message="Configurando modo de lectura Raman...")
        result = dlg.run(transition_read_mode, self.camera, int(mode), **kwargs)
        self.current_read_mode = int(mode)
        self.statusMessageSignal.emit(
            f"Modo de lectura Raman: {self.READ_MODE_NAMES.get(mode, mode)} (buffer {result['buffer_shape']})"
        )

    def _current_wavelength_axis(self) -> np.ndarray:
        from config import SHAMROCK_USE_FACTORY_EEPROM
        if SHAMROCK_USE_FACTORY_EEPROM and hasattr(self.spectrometer, "get_wavelength_axis_cubic"):
            _, wl_arr = self.spectrometer.get_wavelength_axis_cubic(DEVICE, 1004)
        else:
            _, wl_arr = self.spectrometer.ShamrockGetCalibration(DEVICE, 1004)
        return wl_arr

    def _acquire_and_emit(self):
        """Adquiere según el modo de lectura REAL de la cámara (camera.get_read_mode(), no el
        último valor pedido por este widget): el detector es un singleton compartido por otras
        pestañas (Exploración, Step & Glue), así que confiar únicamente en self.current_read_mode
        podría desincronizarse si otra pestaña reconfiguró el modo entretanto. 1D (FVB/Single-
        Track) va al gráfico principal; 2D (Multi-Track/Imagen 2D) va al Inspector 2D."""
        wl_arr = self._current_wavelength_axis()
        read_mode = self.camera.get_read_mode()
        if read_mode in (READ_MODE_FVB, READ_MODE_SINGLE_TRACK):
            data = self.camera.get_1d_spectrum()
            self.spectrumAcquiredSignal.emit(wl_arr, data)
        elif read_mode == READ_MODE_MULTI_TRACK:
            data = self.camera.get_tracks_2d_spectrum()
            self.frame2DAcquiredSignal.emit(wl_arr, data, self.READ_MODE_NAMES.get(READ_MODE_MULTI_TRACK, "Multi-Track"))
        else:  # READ_MODE_IMAGE (o cualquier otro no contemplado)
            data = self.camera.get_most_recent_image()
            self.frame2DAcquiredSignal.emit(wl_arr, data, self.READ_MODE_NAMES.get(READ_MODE_IMAGE, "Imagen 2D"))
        # El driver real no lanza ante un fallo de lectura: devuelve un array de CEROS
        # (andor_ccd_driver.py, get_1d_spectrum/get_most_recent_image). Un EMCCD real nunca
        # entrega un cuadro idénticamente nulo — el offset de bias solo ya son cientos de
        # cuentas —, así que todo-ceros es un centinela fiable de lectura fallida.
        arr = np.asarray(data)
        return bool(arr.size) and bool(np.any(arr))

    @pyqtSlot(int, float)
    def apply_spectrometer_config(self, grating_idx: int, wl_center: float):
        """Aplica la red y longitud de onda central al espectrógrafo Shamrock."""
        try:
            self.spectrometer.ShamrockSetGrating(DEVICE, grating_idx)
            self.spectrometer.ShamrockSetWavelength(DEVICE, wl_center)
            # Leer el vector de calibración actualizado del detector
            _, wl_arr = self.spectrometer.ShamrockGetCalibration(DEVICE, 1004)
            self.statusMessageSignal.emit(f"Espectrógrafo configurado: Red {grating_idx}, Centro {wl_center:.2f} nm")
        except Exception as e:
            self.statusMessageSignal.emit(f"Error al configurar espectrógrafo: {e}")

    @pyqtSlot()
    def acquire_single(self):
        """Adquiere un único cuadro de la cámara, según el modo de lectura activo (FVB/Single-
        Track hacia el espectro 1D principal, Multi-Track/Imagen 2D hacia el Inspector 2D).

        El mensaje de estado final es el ÚNICO autoritativo y se emite al terminar, después de
        cerrar el obturador: la barra de estado muestra sólo el último mensaje, así que emitir
        advertencias intermedias y luego "exitosamente" las borraba antes de que el operador
        pudiera leerlas (defecto introducido en DEC-031, corregido en DEC-032). Política de
        obturador acordada: si no confirma la apertura se adquiere igual, pero se advierte."""
        shutter_opened = False
        valid = False
        error: Optional[Exception] = None
        try:
            shutter_opened = self._set_spectrograph_shutter(True, report=False)
            valid = self._acquire_and_emit()
        except Exception as e:
            error = e
        finally:
            shutter_closed = self._set_spectrograph_shutter(False, report=False)

        if error is not None:
            parts = [f"❌ Error en adquisición única: {error}"]
        elif not valid:
            parts = ["⚠️ El detector devolvió un cuadro vacío (todo ceros): la adquisición NO es "
                     "válida. Verificar conexión e inicialización de la cámara."]
        elif not shutter_opened:
            parts = ["⚠️ Espectro adquirido con el obturador del espectrógrafo SIN confirmar: "
                     "puede estar oscuro."]
        else:
            parts = ["Espectro único adquirido exitosamente."]
        if not shutter_closed:
            parts.append("⚠️ Además, el obturador del espectrógrafo no confirmó el cierre.")
        self.statusMessageSignal.emit(" ".join(parts))

    def _set_spectrograph_shutter(self, open_shutter: bool, report: bool = True) -> bool:
        """Acciona el obturador del espectrógrafo verificando el código de retorno.

        `DEC-014` y `metrology.md` §5 fijan que un estado de obturador es una afirmación
        metrológica y no puede darse por válida sin confirmación del hardware: una escritura
        fallida que se traga en silencio deja al software creyendo que el camino óptico está
        abierto mientras el espectro sale oscuro, sin nada que lo señale. Devuelve True sólo
        si el driver confirmó la operación, y avisa por la barra de estado si no.

        Desde `DEC-034` el driver real devuelve `SHAMROCK_COMMUNICATION_ERROR` cuando la DLL
        lanza (antes respondía `SHAMROCK_SUCCESS` desde su propia rama `except`), así que este
        chequeo detecta tanto un espectrógrafo no inicializado como una excepción de la DLL.

        `report=False` suprime el aviso propio para que el llamador componga un único mensaje
        final con el resultado completo, en vez de que cada paso pise al anterior.
        """
        if not hasattr(self.spectrometer, "ShamrockSetShutter"):
            return True
        action = "apertura" if open_shutter else "cierre"
        try:
            ret = self.spectrometer.ShamrockSetShutter(DEVICE, 1 if open_shutter else 0)
        except Exception as e:
            if report:
                self.statusMessageSignal.emit(f"⚠️ Falló la {action} del obturador del espectrógrafo: {e}")
            return False
        if ret != SHAMROCK_SUCCESS:
            if report:
                self.statusMessageSignal.emit(
                f"⚠️ El obturador del espectrógrafo no confirmó la {action} (código {ret}). "
                "El espectro puede no ser válido."
            )
            return False
        return True

    @pyqtSlot(bool)
    def toggle_live(self, active: bool):
        """Inicia o detiene la adquisición Raman continua, verificando cada paso de hardware.

        Orden de arranque (DEC-032): la cámara se arranca PRIMERO y el obturador del
        espectrógrafo se abre sólo si `start_acquisition()` confirmó. Así un arranque fallido
        nunca deja el obturador abierto — no hace falta limpieza porque nunca se abrió. Es
        seguro porque `StartAcquisition()` no integra hasta el primer tick de `live_timer`
        (confirmado por el operador), así que el primer cuadro ya ve el camino óptico abierto.

        `start_acquisition()` informa fallos por código de retorno, no por excepción: antes
        ese código se descartaba y el lazo arrancaba igual, con la cámara sin adquirir. Tras
        cada transición se emite `liveStateChangedSignal` con el estado REAL alcanzado, para
        que ningún botón de Live quede mostrando 'Detener' con nada corriendo.
        """
        if active:
            try:
                ret = self.camera.start_acquisition()
            except Exception as e:
                ret, detail = None, f"excepción del driver: {e}"
            else:
                detail = f"código {ret}"
            if ret != DRV_SUCCESS:
                self.live_timer.stop()
                hint = (" El detector ya está adquiriendo: ¿está activo el Live View de Exploración?"
                        if ret == DRV_ACQUIRING else "")
                self.statusMessageSignal.emit(
                    f"❌ La cámara no pudo iniciar la adquisición ({detail}). Live Raman NO se inició "
                    f"y el obturador del espectrógrafo no se abrió.{hint}"
                )
                self.liveStateChangedSignal.emit(False)
                return

            shutter_ok = self._set_spectrograph_shutter(True, report=False)
            self.live_timer.start()
            if shutter_ok:
                self.statusMessageSignal.emit("Adquisición Live Raman iniciada.")
            else:
                # Política acordada: seguir en vivo, pero advertirlo en el mensaje final en
                # lugar de en uno intermedio que sería pisado.
                self.statusMessageSignal.emit(
                    "⚠️ Live Raman iniciado con el obturador del espectrógrafo SIN confirmar: "
                    "los espectros pueden estar oscuros."
                )
            self.liveStateChangedSignal.emit(True)
        else:
            self.live_timer.stop()
            self.camera.abort_acquisition()
            shutter_closed = self._set_spectrograph_shutter(False, report=False)
            msg = "Adquisición Live Raman detenida."
            if not shutter_closed:
                msg += " ⚠️ El obturador del espectrógrafo no confirmó el cierre."
            self.statusMessageSignal.emit(msg)
            self.liveStateChangedSignal.emit(False)

    def _acquire_live_frame(self):
        try:
            self._acquire_and_emit()
        except Exception:
            pass

    @pyqtSlot(str, dict)
    def save_spectrum_to_file(self, filepath: str, metadata: dict):
        """Exporta el espectro con cabecera detallada de metadatos experimentales."""
        try:
            laser_nm = float(metadata.get("Laser_Excitacion_nm", 532.0))
            if "_raw_counts" in metadata and len(metadata["_raw_counts"]) > 0:
                counts = np.asarray(metadata["_raw_counts"], dtype=np.float64)
                if "_raw_wl" in metadata and len(metadata["_raw_wl"]) == len(counts):
                    wl_arr = np.asarray(metadata["_raw_wl"], dtype=np.float64)
                else:
                    wl_arr = self._current_wavelength_axis()
            else:
                wl_arr = self._current_wavelength_axis()
                read_mode = self.camera.get_read_mode()
                if read_mode in (READ_MODE_FVB, READ_MODE_SINGLE_TRACK):
                    counts = np.asarray(self.camera.get_1d_spectrum(), dtype=np.float64)
                else:
                    frame = self.camera.get_most_recent_image()
                    counts = np.mean(frame, axis=0) if frame.ndim > 1 else np.asarray(frame, dtype=np.float64)

            raman_shift = wavelength_to_raman_shift(wl_arr, laser_nm)

            p = Path(filepath)
            with open(p, "w", encoding="utf-8") as f:
                f.write("# PySpectrum 3.0 — Adquisición Raman Estática\n")
                f.write("# UNSAM Nanofotónica\n")
                for k, v in metadata.items():
                    if not k.startswith("_"):
                        f.write(f"# {k}: {v}\n")
                f.write("# ------------------------------------------------------------\n")
                f.write("Wavelength_nm\tRaman_Shift_cm-1\tCounts_ADC\n")
                for w, rs, c in zip(wl_arr, raman_shift, counts):
                    f.write(f"{w:.4f}\t{rs:.3f}\t{c:.2f}\n")

            self.statusMessageSignal.emit(f"Espectro guardado en: {p.name}")
        except Exception as e:
            self.statusMessageSignal.emit(f"Error al guardar espectro: {e}")
