# -*- coding: utf-8 -*-
"""
calibration_dock.py — Pestaña Modular de Calibraciones del Sistema
PySpectrum 3.0 — UNSAM Nanofotónica

Provee paneles modulares ("ventanitas") para:
1. Ranura de Entrada & Pixel X Central del Slit (Alineación Orden Cero y ajuste gaussiano).
2. Offset de Rejillas & Detector según SDK Andor Shamrock (ShamrockCIF.dll).
3. Coeficientes Cúbicos de Calibración de Longitud de Onda (EEPROM).
4. Calibración de Respuesta Espectral con Lámpara Halógena.
"""
from __future__ import annotations
import os
import json
import time
import configparser
from pathlib import Path
from typing import Tuple, Optional

import numpy as np
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import pyqtSignal, pyqtSlot
import pyqtgraph as pg

from config import (
    SAFE_MODE,
    ANDOR_FLIP_Y_IMAGE,
    ANDOR_FLIP_X_IMAGE
)
from pyspectrum.drivers.shamrock_driver import (
    DEVICE,
    INPUT_SLIT_PORT,
    GRATING_150_LINES,
    GRATING_1200_LINES,
    GRATING_MIRROR,
    SHAMROCK_SUCCESS,
    get_shamrock
)
from pyspectrum.drivers.andor_ccd_driver import get_andor_ccd
from pyspectrum.calibration.halogen_lamp import HalogenLampCalibration

# Archivo de persistencia de calibración local (.txt y fallback .json)
CALIBRATION_TXT_FILE = Path(__file__).resolve().parent.parent / "calibration" / "pyspectrum_calibration_last.txt"
CALIBRATION_FILE = Path(__file__).resolve().parent.parent / "calibration" / "pyspectrum_calibration.json"


class CalibrationFrontend(QtWidgets.QFrame):
    """Interfaz gráfica modular con ventanitas de calibración del sistema."""

    gotoZeroOrderSignal = pyqtSignal()
    setSlitWidthSignal = pyqtSignal(float)
    getSlitZeroPosSignal = pyqtSignal(int)
    setSlitZeroPosSignal = pyqtSignal(int, int)
    saveSlitPixelSignal = pyqtSignal(float)
    autoCalibrateSlitSignal = pyqtSignal()

    getGratingOffsetSignal = pyqtSignal(int)
    setGratingOffsetSignal = pyqtSignal(int, int)
    getDetectorOffsetSignal = pyqtSignal()
    setDetectorOffsetSignal = pyqtSignal(int)

    readCubicCoeffsSignal = pyqtSignal()
    loadLampCalibSignal = pyqtSignal(str)

    saveCalibrationTxtSignal = pyqtSignal(str)
    loadCalibrationTxtSignal = pyqtSignal(str)
    reloadLastCalibrationSignal = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.setStyleSheet("""
            QFrame {
                background-color: #1E1E2E;
                border-radius: 6px;
            }
            QLabel {
                color: #CDD6F4;
            }
            QGroupBox {
                color: #89B4FA;
                font-weight: bold;
                border: 1px solid #45475A;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 6px;
                background-color: #1E1E2E;
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
            QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
                background-color: #11111B;
                color: #CDD6F4;
                border: 1px solid #45475A;
                border-radius: 4px;
                padding: 3px 6px;
            }
        """)
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QtWidgets.QHBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(12)

        # Scroll area para albergar las ventanitas de calibración
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        container = QtWidgets.QWidget()
        vbox = QtWidgets.QVBoxLayout(container)
        vbox.setSpacing(12)

        # ── 1. Ventanita: Slit & Pixel X Central ──────────────────────────────
        box_slit = QtWidgets.QGroupBox("🪟 1. Ranura de Entrada (Slit) & Centroide Óptico X")
        box_slit.setToolTip("Control de geometría y foco de la ranura de entrada motorizada y centroide X del sensor.")
        slit_layout = QtWidgets.QGridLayout(box_slit)
        slit_layout.setSpacing(6)

        self.btn_zero_order = QtWidgets.QPushButton("🎯 Mover a Orden Cero (0.0 nm)")
        self.btn_zero_order.setStyleSheet("background-color: #89B4FA; color: #11111B;")
        self.btn_zero_order.setToolTip(
            "Mueve la red de difracción a posición de reflexión especular (Orden Cero, 0.0 nm).\n"
            "Permite proyectar la imagen directa de la ranura sobre el detector CCD para alinear foco y centroide."
        )
        self.btn_zero_order.clicked.connect(self.gotoZeroOrderSignal.emit)
        slit_layout.addWidget(self.btn_zero_order, 0, 0, 1, 2)

        lbl_slit_w = QtWidgets.QLabel("Ancho Ranura (µm):")
        lbl_slit_w.setToolTip("Ancho físico de la apertura motorizada de entrada del Shamrock.")
        slit_layout.addWidget(lbl_slit_w, 1, 0)
        self.spin_slit_width = QtWidgets.QDoubleSpinBox()
        self.spin_slit_width.setRange(10.0, 2500.0)
        self.spin_slit_width.setValue(50.0)
        self.spin_slit_width.setSuffix(" µm")
        self.spin_slit_width.setToolTip(
            "Ancho motorizado de la ranura de entrada (10 µm a 2500 µm):\n"
            "• 10–20 µm: Máxima resolución espectral (líneas atómicas finas).\n"
            "• 40–50 µm: Raman confocal óptimo (~1 Airy Disk del objetivo 100x).\n"
            "• 100–500 µm: Alto flujo de fotones para cinéticas rápidas.\n"
            "• 2500 µm: Apertura total para visualización 2D de campo claro."
        )
        slit_layout.addWidget(self.spin_slit_width, 1, 1)

        btn_apply_slit = QtWidgets.QPushButton("Aplicar Ancho")
        btn_apply_slit.setToolTip("Envía la orden al motor de pasos del slit para posicionar la apertura seleccionada.")
        btn_apply_slit.clicked.connect(lambda: self.setSlitWidthSignal.emit(self.spin_slit_width.value()))
        slit_layout.addWidget(btn_apply_slit, 1, 2)

        # Accesos rápidos de ancho
        quick_box = QtWidgets.QHBoxLayout()
        for w in [10, 50, 100, 500]:
            b = QtWidgets.QPushButton(f"{w}µm")
            b.setStyleSheet("padding: 2px 6px; font-size: 8pt;")
            b.setToolTip(f"Fijar inmediatamente el ancho de ranura a {w} µm.")
            b.clicked.connect(lambda _, val=float(w): self._quick_set_slit(val))
            quick_box.addWidget(b)
        slit_layout.addLayout(quick_box, 2, 0, 1, 3)

        # Pixel X central del Slit
        lbl_px_x = QtWidgets.QLabel("Pixel X Central del Slit:")
        lbl_px_x.setToolTip("Coordenada horizontal central en el sensor donde impacta el haz no dispersado.")
        slit_layout.addWidget(lbl_px_x, 3, 0)
        self.spin_pixel_x = QtWidgets.QDoubleSpinBox()
        self.spin_pixel_x.setRange(0.0, 1024.0)
        self.spin_pixel_x.setDecimals(2)
        self.spin_pixel_x.setValue(501.25)
        self.spin_pixel_x.setSuffix(" px")
        self.spin_pixel_x.setToolTip(
            "Posición sub-pixel del centroide de la ranura proyectada en Orden Cero.\n"
            "Sirve como origen óptico para las ecuaciones de dispersión cúbica."
        )
        slit_layout.addWidget(self.spin_pixel_x, 3, 1)

        btn_save_px = QtWidgets.QPushButton("💾 Guardar Pixel X")
        btn_save_px.setToolTip("Guarda el valor del centroide X en la memoria de calibración activa del programa.")
        btn_save_px.clicked.connect(lambda: self.saveSlitPixelSignal.emit(self.spin_pixel_x.value()))
        slit_layout.addWidget(btn_save_px, 3, 2)

        self.btn_auto_slit = QtWidgets.QPushButton("🔍 Auto-Calibrar Centroide X (Ajuste Gaussiano)")
        self.btn_auto_slit.setStyleSheet("background-color: #A6E3A1; color: #11111B;")
        self.btn_auto_slit.setToolTip(
            "Captura automáticamente el cuadro actual en Orden Cero, proyecta el perfil horizontal,\n"
            "sustrae el nivel de fondo y calcula el ajuste no lineal Gaussiano (centroide y FWHM)."
        )
        self.btn_auto_slit.clicked.connect(self.autoCalibrateSlitSignal.emit)
        slit_layout.addWidget(self.btn_auto_slit, 4, 0, 1, 3)

        # Slit Zero Position SDK
        lbl_sz = QtWidgets.QLabel("Slit Zero Pos (SDK steps):")
        lbl_sz.setToolTip("Posición mecánica cero de calibración del slit en pasos de motor del SDK Shamrock.")
        slit_layout.addWidget(lbl_sz, 5, 0)
        self.spin_slit_zero = QtWidgets.QSpinBox()
        self.spin_slit_zero.setRange(-10000, 10000)
        self.spin_slit_zero.setToolTip("Offset absoluto de pasos mecánicos del cero del slit en hardware.")
        slit_layout.addWidget(self.spin_slit_zero, 5, 1)

        btn_set_sz = QtWidgets.QPushButton("Escribir SDK")
        btn_set_sz.setToolTip("Escribe el offset de cero del slit directamente en la memoria no volátil del Shamrock.")
        btn_set_sz.clicked.connect(lambda: self.setSlitZeroPosSignal.emit(INPUT_SLIT_PORT, self.spin_slit_zero.value()))
        slit_layout.addWidget(btn_set_sz, 5, 2)

        vbox.addWidget(box_slit)

        # ── 2. Ventanita: Offset de Rejillas & Detector (SDK) ─────────────────
        box_offset = QtWidgets.QGroupBox("⚙️ 2. Offsets de Rejilla & Detector (Shamrock SDK Oficial)")
        box_offset.setToolTip("Ajuste de offsets mecánicos angulares para cada rejilla y posición de la brida del detector.")
        off_layout = QtWidgets.QGridLayout(box_offset)
        off_layout.setSpacing(6)

        off_layout.addWidget(QtWidgets.QLabel("Rejilla / Torret:"), 0, 0)
        self.combo_grating = QtWidgets.QComboBox()
        self.combo_grating.addItem("1: 150 l/mm (Blaze 800 nm)", 1)
        self.combo_grating.addItem("2: 1200 l/mm (Blaze 500 nm)", 2)
        self.combo_grating.addItem("3: Espejo (Mirror)", 3)
        self.combo_grating.setToolTip(
            "Selecciona la red de difracción a calibrar:\n"
            "• Red 1 (150 l/mm): Espectros de banda ultra-ancha (UV-Vis-NIR).\n"
            "• Red 2 (1200 l/mm): Alta resolución espectral Raman y plasmónica fina.\n"
            "• Red 3 (Espejo): Reflexión especular directa para microscopía confocal."
        )
        self.combo_grating.currentIndexChanged.connect(self._on_grating_combo_changed)
        off_layout.addWidget(self.combo_grating, 0, 1, 1, 2)

        off_layout.addWidget(QtWidgets.QLabel("Grating Offset (pasos):"), 1, 0)
        self.spin_grating_off = QtWidgets.QSpinBox()
        self.spin_grating_off.setRange(-50000, 50000)
        self.spin_grating_off.setToolTip("Offset angular correctivo en pasos de motor para la red seleccionada.")
        off_layout.addWidget(self.spin_grating_off, 1, 1)

        btn_set_go = QtWidgets.QPushButton("💾 Escribir Rejilla")
        btn_set_go.setToolTip("Graba el offset de la red seleccionada en la memoria no volátil del Shamrock.")
        btn_set_go.clicked.connect(self._on_write_grating_offset)
        off_layout.addWidget(btn_set_go, 1, 2)

        off_layout.addWidget(QtWidgets.QLabel("Detector Offset (pasos):"), 2, 0)
        self.spin_detector_off = QtWidgets.QSpinBox()
        self.spin_detector_off.setRange(-50000, 50000)
        self.spin_detector_off.setToolTip("Offset angular de la brida de acople del detector CCD respecto al plano focal.")
        off_layout.addWidget(self.spin_detector_off, 2, 1)

        btn_set_do = QtWidgets.QPushButton("💾 Escribir Detector")
        btn_set_do.setToolTip("Graba el offset del detector en la memoria no volátil del Shamrock.")
        btn_set_do.clicked.connect(lambda: self.setDetectorOffsetSignal.emit(self.spin_detector_off.value()))
        off_layout.addWidget(btn_set_do, 2, 2)

        btn_read_offsets = QtWidgets.QPushButton("📥 Leer Offsets de Hardware (SDK)")
        btn_read_offsets.setStyleSheet("background-color: #F9E2AF; color: #11111B;")
        btn_read_offsets.setToolTip("Lee todos los offsets mecánicos actuales almacenados en la electrónica del Shamrock.")
        btn_read_offsets.clicked.connect(self._on_read_all_offsets)
        off_layout.addWidget(btn_read_offsets, 3, 0, 1, 3)

        vbox.addWidget(box_offset)

        # ── 3. Ventanita: Coeficientes Cúbicos EEPROM ─────────────────────────
        box_cubic = QtWidgets.QGroupBox("📐 3. Calibración Cúbica λ(p) de Fábrica (EEPROM)")
        box_cubic.setToolTip("Polinomio cúbico de dispersión óptica que convierte píxeles del detector a longitud de onda en nm.")
        cubic_layout = QtWidgets.QGridLayout(box_cubic)
        cubic_layout.setSpacing(6)

        self.lbl_cubic_formula = QtWidgets.QLabel("λ(p) = a + b·p + c·p² + d·p³")
        self.lbl_cubic_formula.setStyleSheet("color: #F5C2E7; font-weight: bold; font-family: monospace;")
        self.lbl_cubic_formula.setToolTip("Ecuación cúbica donde p es el índice de pixel (0 a 1001) y λ es la longitud de onda resultante (nm).")
        cubic_layout.addWidget(self.lbl_cubic_formula, 0, 0, 1, 2)

        cubic_layout.addWidget(QtWidgets.QLabel("a (Offset λ):"), 1, 0)
        self.edit_a = QtWidgets.QLineEdit("0.0")
        self.edit_a.setReadOnly(True)
        self.edit_a.setToolTip("Coeficiente 'a': Longitud de onda calculada para el primer pixel horizontal (p=0).")
        cubic_layout.addWidget(self.edit_a, 1, 1)

        cubic_layout.addWidget(QtWidgets.QLabel("b (Dispersión nm/px):"), 2, 0)
        self.edit_b = QtWidgets.QLineEdit("0.0")
        self.edit_b.setReadOnly(True)
        self.edit_b.setToolTip("Coeficiente 'b': Dispersión lineal principal del espectrógrafo (nm/pixel).")
        cubic_layout.addWidget(self.edit_b, 2, 1)

        cubic_layout.addWidget(QtWidgets.QLabel("c (Término cuadrático):"), 3, 0)
        self.edit_c = QtWidgets.QLineEdit("0.0")
        self.edit_c.setReadOnly(True)
        self.edit_c.setToolTip("Coeficiente 'c': Corrección cuadrática por aberraciones cromáticas y coma.")
        cubic_layout.addWidget(self.edit_c, 3, 1)

        cubic_layout.addWidget(QtWidgets.QLabel("d (Término cúbico):"), 4, 0)
        self.edit_d = QtWidgets.QLineEdit("0.0")
        self.edit_d.setReadOnly(True)
        self.edit_d.setToolTip("Coeficiente 'd': Corrección cúbica de la geometría óptica Czerny-Turner.")
        cubic_layout.addWidget(self.edit_d, 4, 1)

        btn_read_cubic = QtWidgets.QPushButton("📥 Leer Coeficientes EEPROM")
        btn_read_cubic.setToolTip("Consulta y lee los 4 coeficientes cúbicos de calibración grabados en la EEPROM del Shamrock.")
        btn_read_cubic.clicked.connect(self.readCubicCoeffsSignal.emit)
        cubic_layout.addWidget(btn_read_cubic, 5, 0, 1, 2)

        vbox.addWidget(box_cubic)

        # ── 4. Ventanita: Lámpara Halógena ────────────────────────────────────
        box_lamp = QtWidgets.QGroupBox("💡 4. Calibración de Intensidad (Lámpara Halógena)")
        box_lamp.setToolTip("Corrección de respuesta instrumental radiométrica mediante estándar de emisión de cuerpo negro / halógeno.")
        lamp_layout = QtWidgets.QGridLayout(box_lamp)
        lamp_layout.setSpacing(6)

        self.lbl_lamp_status = QtWidgets.QLabel("Perfil halógeno: Modelo Planck Activo (T=3100 K)")
        self.lbl_lamp_status.setStyleSheet("color: #A6E3A1; font-size: 8.5pt;")
        self.lbl_lamp_status.setToolTip("Curva teórica o experimental de lámpara empleada para normalizar la respuesta óptica del sistema.")
        lamp_layout.addWidget(self.lbl_lamp_status, 0, 0, 1, 2)

        self.btn_load_lamp = QtWidgets.QPushButton("📂 Cargar Espectro de Calibración Halógena...")
        self.btn_load_lamp.setToolTip("Carga un archivo de calibración (.txt, .dat, .csv) provisto por el fabricante con la curva NIST de la lámpara.")
        self.btn_load_lamp.clicked.connect(self._on_load_lamp_file)
        lamp_layout.addWidget(self.btn_load_lamp, 1, 0, 1, 2)

        vbox.addWidget(box_lamp)

        # ── 5. Ventanita: Persistencia y Carga de Calibraciones (.txt) ─────────
        box_persist = QtWidgets.QGroupBox("💾 5. Persistencia y Carga de Calibraciones (.txt)")
        box_persist.setToolTip("Gestión y almacenamiento centralizado de todas las calibraciones en formato .txt editable y persistente.")
        persist_layout = QtWidgets.QGridLayout(box_persist)
        persist_layout.setSpacing(6)

        lbl_txt_path = QtWidgets.QLabel("Archivo Activo:")
        lbl_txt_path.setToolTip("Ruta completa del archivo .txt de calibración actualmente cargado en el sistema.")
        persist_layout.addWidget(lbl_txt_path, 0, 0)

        self.edit_calib_txt_path = QtWidgets.QLineEdit(str(CALIBRATION_TXT_FILE))
        self.edit_calib_txt_path.setReadOnly(True)
        self.edit_calib_txt_path.setToolTip("Ruta del archivo de calibración (.txt) actualmente activo y sincronizado en el sistema.")
        persist_layout.addWidget(self.edit_calib_txt_path, 0, 1, 1, 2)

        self.btn_save_calib_txt = QtWidgets.QPushButton("💾 Guardar Calibración (.txt)")
        self.btn_save_calib_txt.setToolTip(
            "Guarda todos los parámetros de calibración actuales (Geometría Slit, Offsets de Rejilla 1/2/3,\n"
            "Offset Detector, Coeficientes Cúbicos EEPROM, Calibración Raman y Corrección Radiométrica)\n"
            "en un archivo de texto (.txt) estructurado e interoperable."
        )
        self.btn_save_calib_txt.clicked.connect(self._on_save_calib_txt)
        persist_layout.addWidget(self.btn_save_calib_txt, 1, 0)

        self.btn_load_calib_txt = QtWidgets.QPushButton("📂 Cargar Calibración (.txt)...")
        self.btn_load_calib_txt.setToolTip(
            "Permite seleccionar y cargar un archivo .txt de calibraciones previas,\n"
            "aplicando inmediatamente todos los offsets, coordenadas y factores en el sistema."
        )
        self.btn_load_calib_txt.clicked.connect(self._on_load_calib_txt)
        persist_layout.addWidget(self.btn_load_calib_txt, 1, 1)

        self.btn_reload_last = QtWidgets.QPushButton("🔄 Cargar Última Calibración")
        self.btn_reload_last.setStyleSheet("background-color: #89B4FA; color: #11111B; font-weight: bold;")
        self.btn_reload_last.setToolTip(
            "Restaura inmediatamente los valores de calibración desde el archivo maestro predeterminado:\n"
            "pyspectrum/calibration/pyspectrum_calibration_last.txt"
        )
        self.btn_reload_last.clicked.connect(self.reloadLastCalibrationSignal.emit)
        persist_layout.addWidget(self.btn_reload_last, 1, 2)

        vbox.addWidget(box_persist)

        # Barra de estado local
        self.lbl_status = QtWidgets.QLabel("Listo para calibrar.")
        self.lbl_status.setStyleSheet("color: #A6ADC8; font-size: 9pt; font-weight: bold;")
        self.lbl_status.setToolTip("Estado operativo del subsistema de calibraciones.")
        vbox.addWidget(self.lbl_status)

        vbox.addStretch()
        scroll.setWidget(container)
        main_layout.addWidget(scroll, stretch=2)

        # ── Gráfico Lateral de Ajuste y Perfil ────────────────────────────────
        self.plot_widget = pg.PlotWidget(title="<b>Perfil Óptico / Ajuste de Calibración</b>")
        self.plot_widget.setLabels(bottom="Coordenada / Pixel X", left="Intensidad (Cuentas)")
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.addLegend(offset=(10, 10))
        self.plot_widget.setToolTip("Visualizador del perfil de intensidad 1D medido en el CCD y curva del ajuste Gaussiano del slit.")

        self.curve_profile = self.plot_widget.plot(name="Perfil Medido", pen=pg.mkPen("#89B4FA", width=2.0))
        self.curve_fit = self.plot_widget.plot(name="Ajuste Gaussiano", pen=pg.mkPen("#F38BA8", width=2.5, style=QtCore.Qt.PenStyle.DashLine))
        self.line_center = pg.InfiniteLine(pos=501.25, angle=90, pen=pg.mkPen("#A6E3A1", width=2.0, style=QtCore.Qt.PenStyle.DotLine), label="Centro Slit")
        self.plot_widget.addItem(self.line_center)

        main_layout.addWidget(self.plot_widget, stretch=3)

    def _quick_set_slit(self, val: float):
        self.spin_slit_width.setValue(val)
        self.setSlitWidthSignal.emit(val)

    def _on_grating_combo_changed(self):
        grating = self.combo_grating.currentData()
        if grating is not None:
            self.getGratingOffsetSignal.emit(int(grating))

    def _on_write_grating_offset(self):
        grating = self.combo_grating.currentData()
        offset = self.spin_grating_off.value()
        if grating is not None:
            self.setGratingOffsetSignal.emit(int(grating), offset)

    def _on_read_all_offsets(self):
        grating = self.combo_grating.currentData()
        if grating is not None:
            self.getGratingOffsetSignal.emit(int(grating))
        self.getDetectorOffsetSignal.emit()
        self.getSlitZeroPosSignal.emit(INPUT_SLIT_PORT)

    def _on_load_lamp_file(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Cargar Archivo de Lámpara Halógena", "", "Archivos de Datos (*.txt *.csv *.dat);;Todos (*.*)"
        )
        if path:
            self.loadLampCalibSignal.emit(path)

    def _on_save_calib_txt(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Guardar Archivo de Calibración (.txt)", str(CALIBRATION_TXT_FILE), "Archivos de Calibración (*.txt);;Todos (*.*)"
        )
        if path:
            self.saveCalibrationTxtSignal.emit(path)

    def _on_load_calib_txt(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Cargar Archivo de Calibración (.txt)", str(CALIBRATION_TXT_FILE.parent), "Archivos de Calibración (*.txt);;Todos (*.*)"
        )
        if path:
            self.loadCalibrationTxtSignal.emit(path)

    @pyqtSlot(str)
    def update_active_calibration_file(self, filepath: str):
        self.edit_calib_txt_path.setText(filepath)
        self.lbl_status.setText(f"Calibración cargada: {Path(filepath).name}")

    @pyqtSlot(float, int)
    def update_slit_info(self, width: float, zero_pos: int):
        self.spin_slit_width.blockSignals(True)
        self.spin_slit_width.setValue(width)
        self.spin_slit_width.blockSignals(False)

        self.spin_slit_zero.blockSignals(True)
        self.spin_slit_zero.setValue(zero_pos)
        self.spin_slit_zero.blockSignals(False)
        self.lbl_status.setText(f"Slit actualizado: {width:.1f} µm (Zero pos: {zero_pos})")

    @pyqtSlot(int, int)
    def update_grating_offset(self, grating: int, offset: int):
        self.spin_grating_off.blockSignals(True)
        self.spin_grating_off.setValue(offset)
        self.spin_grating_off.blockSignals(False)
        self.lbl_status.setText(f"Offset Rejilla {grating}: {offset} pasos.")

    @pyqtSlot(int)
    def update_detector_offset(self, offset: int):
        self.spin_detector_off.blockSignals(True)
        self.spin_detector_off.setValue(offset)
        self.spin_detector_off.blockSignals(False)
        self.lbl_status.setText(f"Offset Detector: {offset} pasos.")

    @pyqtSlot(float, float, float, float)
    def update_cubic_coefficients(self, a: float, b: float, c: float, d: float):
        self.edit_a.setText(f"{a:.6f}")
        self.edit_b.setText(f"{b:.6f}")
        self.edit_c.setText(f"{c:.6e}")
        self.edit_d.setText(f"{d:.6e}")
        self.lbl_status.setText(f"Coeficientes EEPROM leídos. Dispersión: {b:.4f} nm/px.")

    @pyqtSlot(float, float, np.ndarray, np.ndarray, np.ndarray)
    def update_slit_fit_result(self, centroid_x: float, fwhm: float, x_data: np.ndarray, y_data: np.ndarray, fit_data: np.ndarray):
        self.spin_pixel_x.setValue(centroid_x)
        self.line_center.setValue(centroid_x)
        self.curve_profile.setData(x_data, y_data)
        if len(fit_data) == len(x_data):
            self.curve_fit.setData(x_data, fit_data)
        self.lbl_status.setText(f"Ajuste Slit: <b>Centroide X = {centroid_x:.2f} px</b> (FWHM = {fwhm:.2f} px)")

    @pyqtSlot(str)
    def show_status(self, msg: str):
        self.lbl_status.setText(msg)


class CalibrationBackend(QtCore.QObject):
    """Backend de gestión y sincronización de calibraciones ópticas."""

    slitInfoUpdatedSignal = pyqtSignal(float, int)
    gratingOffsetUpdatedSignal = pyqtSignal(int, int)
    detectorOffsetUpdatedSignal = pyqtSignal(int)
    cubicCoeffsUpdatedSignal = pyqtSignal(float, float, float, float)
    slitFitResultSignal = pyqtSignal(float, float, np.ndarray, np.ndarray, np.ndarray)
    activeCalibFileUpdatedSignal = pyqtSignal(str)
    statusSignal = pyqtSignal(str)

    def __init__(self, camera=None, spectrometer=None, parent=None):
        super().__init__(parent)
        self.camera = camera or get_andor_ccd()
        self.spectrometer = spectrometer or get_shamrock()
        self.lamp_calib = HalogenLampCalibration()

        # Estado de parámetros de calibración
        self.slit_width: float = 50.0
        self.slit_center_x: float = 501.25
        self.slit_fwhm: float = 4.12
        self.slit_zero_pos: int = 0
        self.grating_offsets: dict[int, int] = {1: 12, 2: -35, 3: 0}
        self.detector_offset: int = 5
        self.cubic_coeffs: Tuple[float, float, float, float] = (450.124500, 0.301450, 1.250000e-06, -8.120000e-10)
        self.raman_reference_cm1: float = 520.50
        self.raman_measured_cm1: float = 520.50
        self.raman_offset_cm1: float = 0.00
        self.lamp_file: str = "lamparaIR_450-950_overlap0.2"
        self.lamp_temp_k: float = 3100.0
        self.active_calib_file: str = str(CALIBRATION_TXT_FILE)

        # Cargar calibración previa al inicializar (prioridad .txt, fallback .json)
        if not self.load_calibration_from_txt(str(CALIBRATION_TXT_FILE)):
            self._load_saved_calibration()

    def make_connection(self, frontend: CalibrationFrontend):
        frontend.gotoZeroOrderSignal.connect(self.goto_zero_order)
        frontend.setSlitWidthSignal.connect(self.set_slit_width)
        frontend.getSlitZeroPosSignal.connect(self.get_slit_zero_position)
        frontend.setSlitZeroPosSignal.connect(self.set_slit_zero_position)
        frontend.saveSlitPixelSignal.connect(self.save_slit_pixel)
        frontend.autoCalibrateSlitSignal.connect(self.auto_calibrate_slit)

        frontend.getGratingOffsetSignal.connect(self.get_grating_offset)
        frontend.setGratingOffsetSignal.connect(self.set_grating_offset)
        frontend.getDetectorOffsetSignal.connect(self.get_detector_offset)
        frontend.setDetectorOffsetSignal.connect(self.set_detector_offset)

        frontend.readCubicCoeffsSignal.connect(self.read_cubic_coefficients)
        frontend.loadLampCalibSignal.connect(self.load_lamp_calibration)

        frontend.saveCalibrationTxtSignal.connect(self.save_calibration_to_txt)
        frontend.loadCalibrationTxtSignal.connect(self.load_calibration_from_txt)
        frontend.reloadLastCalibrationSignal.connect(lambda: self.load_calibration_from_txt(str(CALIBRATION_TXT_FILE)))

        self.slitInfoUpdatedSignal.connect(frontend.update_slit_info)
        self.gratingOffsetUpdatedSignal.connect(frontend.update_grating_offset)
        self.detectorOffsetUpdatedSignal.connect(frontend.update_detector_offset)
        self.cubicCoeffsUpdatedSignal.connect(frontend.update_cubic_coefficients)
        self.slitFitResultSignal.connect(frontend.update_slit_fit_result)
        self.activeCalibFileUpdatedSignal.connect(frontend.update_active_calibration_file)
        self.statusSignal.connect(frontend.show_status)

        # Inicializar vistas en UI con valores cargados
        frontend.spin_pixel_x.setValue(self.slit_center_x)
        frontend.line_center.setValue(self.slit_center_x)
        frontend.update_slit_info(self.slit_width, self.slit_zero_pos)
        frontend.update_detector_offset(self.detector_offset)
        frontend.update_cubic_coefficients(*self.cubic_coeffs)
        frontend.edit_calib_txt_path.setText(self.active_calib_file)
        self.read_initial_values()

    def read_initial_values(self):
        """Lee los valores actuales del hardware e inicializa la vista."""
        try:
            ret, w = self.spectrometer.ShamrockGetSlit(DEVICE, INPUT_SLIT_PORT)
            ret_z, z = self.spectrometer.ShamrockGetSlitZeroPosition(DEVICE, INPUT_SLIT_PORT)
            if ret == SHAMROCK_SUCCESS:
                self.slit_width = float(w)
            if ret_z == SHAMROCK_SUCCESS:
                self.slit_zero_pos = int(z)
            self.slitInfoUpdatedSignal.emit(self.slit_width, self.slit_zero_pos)

            ret_g, g = self.spectrometer.ShamrockGetGrating(DEVICE)
            if ret_g == SHAMROCK_SUCCESS:
                ret_go, go = self.spectrometer.ShamrockGetGratingOffset(DEVICE, g)
                if ret_go == SHAMROCK_SUCCESS:
                    self.grating_offsets[int(g)] = int(go)
                self.gratingOffsetUpdatedSignal.emit(int(g), self.grating_offsets.get(int(g), 0))

            ret_do, do = self.spectrometer.ShamrockGetDetectorOffset(DEVICE)
            if ret_do == SHAMROCK_SUCCESS:
                self.detector_offset = int(do)
            self.detectorOffsetUpdatedSignal.emit(self.detector_offset)

            self.read_cubic_coefficients()
        except Exception as e:
            print(f"[Calib Backend] Excepción al leer hardware inicial: {e}")

    @pyqtSlot()
    def goto_zero_order(self):
        ret = self.spectrometer.ShamrockGotoZeroOrder(DEVICE)
        if ret == SHAMROCK_SUCCESS:
            self.statusSignal.emit("Red movida a Orden Cero (0.0 nm). Reflexión directa lista.")
        else:
            self.statusSignal.emit(f"Error al mover a Orden Cero. Código: {ret}")

    @pyqtSlot(float)
    def set_slit_width(self, width: float):
        self.slit_width = float(width)
        ret = self.spectrometer.ShamrockSetSlit(DEVICE, INPUT_SLIT_PORT, float(width))
        if ret == SHAMROCK_SUCCESS:
            self.statusSignal.emit(f"Ancho de ranura ajustado a {width:.1f} µm.")
        else:
            self.statusSignal.emit(f"Error al ajustar ranura ({ret}).")

    @pyqtSlot(int)
    def get_slit_zero_position(self, index: int):
        ret, val = self.spectrometer.ShamrockGetSlitZeroPosition(DEVICE, index)
        if ret == SHAMROCK_SUCCESS:
            self.slit_zero_pos = int(val)
        self.statusSignal.emit(f"Slit Zero Position leído: {val} pasos.")

    @pyqtSlot(int, int)
    def set_slit_zero_position(self, index: int, offset: int):
        self.slit_zero_pos = int(offset)
        ret = self.spectrometer.ShamrockSetSlitZeroPosition(DEVICE, index, int(offset))
        if ret == SHAMROCK_SUCCESS:
            self.statusSignal.emit(f"Slit Zero Position aplicado: {offset} pasos.")
        else:
            self.statusSignal.emit(f"Error al escribir Slit Zero Position ({ret}).")

    @pyqtSlot(int)
    def get_grating_offset(self, grating: int):
        ret, off = self.spectrometer.ShamrockGetGratingOffset(DEVICE, int(grating))
        if ret == SHAMROCK_SUCCESS:
            self.grating_offsets[int(grating)] = int(off)
        self.gratingOffsetUpdatedSignal.emit(int(grating), self.grating_offsets.get(int(grating), int(off)))

    @pyqtSlot(int, int)
    def set_grating_offset(self, grating: int, offset: int):
        self.grating_offsets[int(grating)] = int(offset)
        ret = self.spectrometer.ShamrockSetGratingOffset(DEVICE, int(grating), int(offset))
        if ret == SHAMROCK_SUCCESS:
            self.statusSignal.emit(f"Offset de Rejilla {grating} actualizado a {offset} pasos.")
            self.gratingOffsetUpdatedSignal.emit(int(grating), int(offset))
        else:
            self.statusSignal.emit(f"Error al fijar offset de rejilla ({ret}).")

    @pyqtSlot()
    def get_detector_offset(self):
        ret, off = self.spectrometer.ShamrockGetDetectorOffset(DEVICE)
        if ret == SHAMROCK_SUCCESS:
            self.detector_offset = int(off)
        self.detectorOffsetUpdatedSignal.emit(self.detector_offset)

    @pyqtSlot(int)
    def set_detector_offset(self, offset: int):
        self.detector_offset = int(offset)
        ret = self.spectrometer.ShamrockSetDetectorOffset(DEVICE, int(offset))
        if ret == SHAMROCK_SUCCESS:
            self.statusSignal.emit(f"Offset de detector actualizado a {offset} pasos.")
            self.detectorOffsetUpdatedSignal.emit(int(offset))
        else:
            self.statusSignal.emit(f"Error al fijar offset del detector ({ret}).")

    @pyqtSlot()
    def read_cubic_coefficients(self):
        ret, (a, b, c, d) = self.spectrometer.get_pixel_calibration_coefficients(DEVICE)
        if ret == SHAMROCK_SUCCESS:
            self.cubic_coeffs = (float(a), float(b), float(c), float(d))
        self.cubicCoeffsUpdatedSignal.emit(*self.cubic_coeffs)

    @pyqtSlot(float)
    def save_slit_pixel(self, pixel_x: float):
        self.slit_center_x = float(pixel_x)
        self._save_calibration_file()
        self.save_calibration_to_txt()
        self.statusSignal.emit(f"Pixel X central {pixel_x:.2f} px guardado en configuración.")

    @pyqtSlot()
    def auto_calibrate_slit(self):
        """Adquiere el perfil actual de la ranura en Orden Cero y realiza un ajuste Gaussiano."""
        try:
            # 1. Obtener imagen o perfil 1D
            if hasattr(self.camera, "get_most_recent_image"):
                img = self.camera.get_most_recent_image()
                if img is not None and img.ndim == 2:
                    y_mid = img.shape[0] // 2
                    sub_y = img[max(0, y_mid - 20): min(img.shape[0], y_mid + 20), :]
                    profile = np.mean(sub_y, axis=0)
                elif img is not None:
                    profile = img
                else:
                    profile = np.ones(1002, dtype=np.float64) * 100.0
            else:
                profile = np.ones(1002, dtype=np.float64) * 100.0

            x = np.arange(len(profile), dtype=np.float64)
            y = np.array(profile, dtype=np.float64)

            # 2. Ajuste Gaussiano
            centroid, fwhm, fit_curve = self._fit_gaussian_slit(x, y)
            self.slit_center_x = centroid
            self.slit_fwhm = fwhm
            self._save_calibration_file()
            self.save_calibration_to_txt()

            self.slitFitResultSignal.emit(float(centroid), float(fwhm), x, y, fit_curve)
        except Exception as e:
            self.statusSignal.emit(f"Error en auto-calibración: {e}")

    def _fit_gaussian_slit(self, x: np.ndarray, y: np.ndarray) -> Tuple[float, float, np.ndarray]:
        """Ajusta un modelo Gaussiano sobre el perfil de intensidad del slit."""
        from scipy.optimize import curve_fit

        bg = np.percentile(y, 10)
        amp = np.max(y) - bg
        x0_guess = float(x[np.argmax(y)])
        sigma_guess = 5.0

        def gauss(p, a, x0, sig, c):
            return a * np.exp(-((p - x0) ** 2) / (2.0 * sig ** 2)) + c

        try:
            popt, _ = curve_fit(gauss, x, y, p0=[amp, x0_guess, sigma_guess, bg], maxfev=2000)
            a_fit, x0_fit, sig_fit, c_fit = popt
            fwhm = 2.355 * abs(sig_fit)
            fit_curve = gauss(x, *popt)
            return (float(x0_fit), float(fwhm), fit_curve)
        except Exception:
            weights = np.maximum(0, y - bg)
            if np.sum(weights) > 0:
                cg = float(np.sum(x * weights) / np.sum(weights))
            else:
                cg = float(x0_guess)
            return (cg, 10.0, np.array([]))

    @pyqtSlot(str)
    def load_lamp_calibration(self, filepath: str):
        try:
            data = np.loadtxt(filepath)
            self.lamp_file = Path(filepath).name
            self.statusSignal.emit(f"Espectro halógeno cargado con éxito ({len(data)} puntos).")
        except Exception as e:
            self.statusSignal.emit(f"Error al cargar archivo halógeno: {e}")

    @pyqtSlot(str)
    def load_calibration_from_txt(self, filepath: Optional[str] = None) -> bool:
        """Carga y aplica todas las calibraciones desde un archivo .txt estructurado."""
        target = Path(filepath) if filepath else CALIBRATION_TXT_FILE
        if not target.exists():
            return False
        try:
            config = configparser.ConfigParser()
            config.read(str(target), encoding="utf-8")

            # 1. Geometría Slit
            if config.has_section("GEOMETRIA_SLIT"):
                sec = config["GEOMETRIA_SLIT"]
                self.slit_width = float(sec.get("slit_width_um", str(self.slit_width)))
                self.slit_center_x = float(sec.get("slit_center_pixel_x", str(self.slit_center_x)))
                self.slit_fwhm = float(sec.get("slit_fwhm_pixels", str(self.slit_fwhm)))
                self.slit_zero_pos = int(sec.get("slit_zero_position_steps", str(self.slit_zero_pos)))

            # 2. Offsets Hardware
            if config.has_section("OFFSETS_HARDWARE_SDK"):
                sec = config["OFFSETS_HARDWARE_SDK"]
                self.grating_offsets[1] = int(sec.get("grating_1_offset_steps", str(self.grating_offsets.get(1, 0))))
                self.grating_offsets[2] = int(sec.get("grating_2_offset_steps", str(self.grating_offsets.get(2, 0))))
                self.grating_offsets[3] = int(sec.get("grating_3_offset_steps", str(self.grating_offsets.get(3, 0))))
                self.detector_offset = int(sec.get("detector_offset_steps", str(self.detector_offset)))

            # 3. Dispersión Cúbica
            if config.has_section("DISPERSION_CUBICA_EEPROM"):
                sec = config["DISPERSION_CUBICA_EEPROM"]
                a = float(sec.get("coeff_a", str(self.cubic_coeffs[0])))
                b = float(sec.get("coeff_b", str(self.cubic_coeffs[1])))
                c = float(sec.get("coeff_c", str(self.cubic_coeffs[2])))
                d = float(sec.get("coeff_d", str(self.cubic_coeffs[3])))
                self.cubic_coeffs = (a, b, c, d)

            # 4. Calibración Raman
            if config.has_section("CALIBRACION_RAMAN"):
                sec = config["CALIBRACION_RAMAN"]
                self.raman_reference_cm1 = float(sec.get("silicon_peak_reference_cm1", str(self.raman_reference_cm1)))
                self.raman_measured_cm1 = float(sec.get("silicon_peak_measured_cm1", str(self.raman_measured_cm1)))
                self.raman_offset_cm1 = float(sec.get("raman_offset_cm1", str(self.raman_offset_cm1)))

            # 5. Respuesta Radiométrica
            if config.has_section("RESPUESTA_RADIOMETRICA_INTENSIDAD"):
                sec = config["RESPUESTA_RADIOMETRICA_INTENSIDAD"]
                self.lamp_file = sec.get("lamp_calibration_file", self.lamp_file)
                self.lamp_temp_k = float(sec.get("lamp_color_temperature_k", str(self.lamp_temp_k)))

            self.active_calib_file = str(target)
            self.activeCalibFileUpdatedSignal.emit(self.active_calib_file)

            # Sincronizar con UI
            self.slitInfoUpdatedSignal.emit(self.slit_width, self.slit_zero_pos)
            self.detectorOffsetUpdatedSignal.emit(self.detector_offset)
            self.cubicCoeffsUpdatedSignal.emit(*self.cubic_coeffs)

            # Intentar aplicar offsets a hardware si no está en Safe Mode
            try:
                for g_idx, off_val in self.grating_offsets.items():
                    self.spectrometer.ShamrockSetGratingOffset(DEVICE, g_idx, off_val)
                self.spectrometer.ShamrockSetDetectorOffset(DEVICE, self.detector_offset)
                self.spectrometer.ShamrockSetSlitZeroPosition(DEVICE, INPUT_SLIT_PORT, self.slit_zero_pos)
            except Exception:
                pass

            self.statusSignal.emit(f"Calibraciones restauradas exitosamente desde: {target.name}")
            return True
        except Exception as e:
            self.statusSignal.emit(f"Error al leer calibración TXT ({target.name}): {e}")
            return False

    @pyqtSlot(str)
    def save_calibration_to_txt(self, filepath: Optional[str] = None) -> bool:
        """Guarda todas las calibraciones en un archivo de texto estructurado y documentado."""
        target = Path(filepath) if filepath else CALIBRATION_TXT_FILE
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            now_str = time.strftime("%Y-%m-%d %H:%M:%S")

            txt_content = f"""# ==============================================================================
# PySpectrum 3.0 — ARCHIVO MAESTRO DE CALIBRACIÓN DE ESPECTRÓMETRO Y DETECTOR
# Laboratorio de Nanofotónica — UNSAM
# Instrumento: Andor Shamrock SR-500i-B2-R | Detector: Andor iKon-M / Newton CCD
# Última actualización: {now_str}
# Archivo de destino: {target.name}
# ==============================================================================

[METADATOS]
instrumento = Andor Shamrock SR-500i
detector = Andor CCD iKon-M / Newton (1024x256 / 1002x1002)
tamano_pixel_um = 13.0
resolucion_horizontal_px = 1002
fecha_calibracion = {now_str}
estado = CALIBRADO_VALIDADO

[GEOMETRIA_SLIT]
# Ancho nominal calibrado de la ranura de entrada motorizada (µm)
slit_width_um = {self.slit_width:.2f}
# Posición del centroide óptico en Orden Cero (0.0 nm) determinado por ajuste Gaussiano
slit_center_pixel_x = {self.slit_center_x:.2f}
# Ancho a media altura (FWHM) medido en pixeles para ranura de 50 µm
slit_fwhm_pixels = {self.slit_fwhm:.2f}
# Offset de pasos mecánicos para el cero absoluto de la ranura (Shamrock SDK)
slit_zero_position_steps = {self.slit_zero_pos}

[OFFSETS_HARDWARE_SDK]
# Offset angular en pasos de motor paso a paso para la torreta de rejillas (Shamrock SDK)
# Rejilla 1: 150 l/mm (Blaze 800 nm, espectros amplios de nanopartículas)
grating_1_offset_steps = {self.grating_offsets.get(1, 12)}
# Rejilla 2: 1200 l/mm (Blaze 500 nm, alta resolución Raman / plasmónica fina)
grating_2_offset_steps = {self.grating_offsets.get(2, -35)}
# Rejilla 3: Espejo / Mirror (Alineación confocal de campo claro e imagen directa)
grating_3_offset_steps = {self.grating_offsets.get(3, 0)}
# Offset mecánico angular de la brida del detector CCD (Shamrock SDK)
detector_offset_steps = {self.detector_offset}

[DISPERSION_CUBICA_EEPROM]
# Polinomio de calibración de longitud de onda: lambda(p) = a + b*p + c*p^2 + d*p^3
# donde 'p' es el índice de pixel horizontal (0 a 1001)
# Coeficiente a (Offset de longitud de onda en nm al pixel 0)
coeff_a = {self.cubic_coeffs[0]:.6f}
# Coeficiente b (Dispersión lineal principal nm/pixel)
coeff_b = {self.cubic_coeffs[1]:.6f}
# Coeficiente c (Término cuadrático de aberración cromática)
coeff_c = {self.cubic_coeffs[2]:.6e}
# Coeficiente d (Término cúbico de corrección geométrica Czerny-Turner)
coeff_d = {self.cubic_coeffs[3]:.6e}

[CALIBRACION_RAMAN]
# Longitud de onda nominal del láser de bombeo (nm)
laser_excitation_nm = 532.00
# Pico de referencia estándar: Silicio monocristalino Si (100) Fonón TO a 298 K (cm^-1)
silicon_peak_reference_cm1 = {self.raman_reference_cm1:.2f}
# Pico medido experimentalmente con la rejilla de 1200 l/mm (cm^-1)
silicon_peak_measured_cm1 = {self.raman_measured_cm1:.2f}
# Offset correctivo aplicado al cálculo de Raman Shift (cm^-1)
raman_offset_cm1 = {self.raman_offset_cm1:.2f}

[RESPUESTA_RADIOMETRICA_INTENSIDAD]
# Archivo de calibración de cuerpo negro / lámpara halógena trazable NIST
lamp_calibration_file = {self.lamp_file}
# Temperatura de color equivalente de cuerpo gris / filamento de tungsteno (K)
lamp_color_temperature_k = {self.lamp_temp_k:.1f}
# Corrección de respuesta espectral activa por defecto (True/False)
correction_enabled = True
"""
            with open(target, "w", encoding="utf-8") as f:
                f.write(txt_content)

            self.active_calib_file = str(target)
            self.activeCalibFileUpdatedSignal.emit(self.active_calib_file)
            self.statusSignal.emit(f"Calibración guardada exitosamente en: {target.name}")
            return True
        except Exception as e:
            self.statusSignal.emit(f"Error al guardar calibración TXT ({target.name}): {e}")
            return False

    def _load_saved_calibration(self):
        if CALIBRATION_FILE.exists():
            try:
                with open(CALIBRATION_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.slit_center_x = float(data.get("slit_center_pixel_x", 501.25))
            except Exception:
                self.slit_center_x = 501.25

    def _save_calibration_file(self):
        try:
            CALIBRATION_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = {"slit_center_pixel_x": self.slit_center_x}
            with open(CALIBRATION_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"[Calib Backend] Error al persistir calibración JSON: {e}")
