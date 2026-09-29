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
    ANDOR_FLIP_X_IMAGE,
    SHUTTERS,
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
from pyspectrum.drivers.andor_ccd_driver import (
    get_andor_ccd, READ_MODE_IMAGE, DETECTOR_PIXEL_PITCH_UM, DETECTOR_WIDTH_PX, DETECTOR_HEIGHT_PX,
)
from pyspectrum.modules.spectroscopy_context import spectroscopy_context
from pyspectrum.calibration.halogen_lamp import HalogenLampCalibration
from pyspectrum.calibration.fit_raman_water import fit_signal_raman, calc_r2
from core.sif_processor import characterize_background_noise
from core.nidaq import open_shutter, close_shutter, close_all_shutters, heartbeat_shutter
from pyspectrum.modules.hardware_session import hardware_session

# Perfil de sustracción de ruido oscuro persistido (Fase 7, DEC-021)
DARK_NOISE_PROFILE_FILE = Path(__file__).resolve().parent.parent / "calibration" / "dark_noise_profile.npz"

# Archivo de persistencia de calibración local (.txt y fallback .json)
CALIBRATION_TXT_FILE = Path(__file__).resolve().parent.parent / "calibration" / "pyspectrum_calibration_last.txt"
CALIBRATION_FILE = Path(__file__).resolve().parent.parent / "calibration" / "pyspectrum_calibration.json"


GRAT_OFFSET_MAX_STEPS = 20000      # rango del SDK (SHAMROCK_GRAT_OFFSET_MAX, R2-inst §3.1)
DET_OFFSET_MAX_STEPS = 240000      # rango del SDK (SHAMROCK_DET_OFFSET_MAX, R2-inst §3.1)


def _steps(value) -> str:
    """Offset leído para el .txt: el número, o "desconocido" si no se pudo leer (nunca un valor inventado)."""
    return "desconocido" if value is None else str(int(value))


class CalibrationFrontend(QtWidgets.QFrame):
    """Interfaz gráfica modular con ventanitas de calibración del sistema."""

    gotoZeroOrderSignal = pyqtSignal()
    setSlitWidthSignal = pyqtSignal(float)
    getSlitZeroPosSignal = pyqtSignal(int)
    saveSlitPixelSignal = pyqtSignal(float)
    autoCalibrateSlitSignal = pyqtSignal()

    # Los offsets se leen; no se escriben desde acá (pasos 9-10, G-10). El offset entero se escribe sólo
    # con la transacción (pyspectrum/calibration/offset_transaction.py), desde la rutina (R4-B-1).
    getGratingOffsetSignal = pyqtSignal(int)
    getDetectorOffsetSignal = pyqtSignal()
    registerReadOffsetsSignal = pyqtSignal()

    readCubicCoeffsSignal = pyqtSignal()
    loadLampCalibSignal = pyqtSignal(str)

    saveCalibrationTxtSignal = pyqtSignal(str)
    loadCalibrationTxtSignal = pyqtSignal(str)
    reloadLastCalibrationSignal = pyqtSignal()

    verifyWaterCalibrationSignal = pyqtSignal()
    measureDarkNoiseSignal = pyqtSignal()
    saveDarkNoiseProfileSignal = pyqtSignal()

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
        spectroscopy_context.slitParametersChanged.connect(self._on_context_slit_changed)

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
        self.spin_slit_zero.setReadOnly(True)
        self.spin_slit_zero.setButtonSymbols(QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_slit_zero.setToolTip("Cero de la ranura en pasos de motor, leído del Shamrock. PySpectrum no lo "
                                       "escribe (R2-inst §3.2).")
        slit_layout.addWidget(self.spin_slit_zero, 5, 1)

        vbox.addWidget(box_slit)

        # ── 2. Ventanita: Offset de Rejillas & Detector (SDK) ─────────────────
        box_offset = QtWidgets.QGroupBox("⚙️ 2. Offsets de red y detector (leídos del Shamrock)")
        box_offset.setToolTip(
            "Offsets de la torreta, en pasos de motor, leídos del Shamrock. Uno por red (150 y 1200) y uno del\n"
            "detector, que por convención del laboratorio vale 0 (R4-A-2). Solis y el PySpectrum legado ven estos\n"
            "mismos valores. Cuántos píxeles corre un paso no está medido en este equipo (BANCO-40).\n"
            "Se escriben sólo desde la calibración, con la transacción de doble confirmación.")
        off_layout = QtWidgets.QGridLayout(box_offset)
        off_layout.setSpacing(6)

        off_layout.addWidget(QtWidgets.QLabel("Rejilla / Torret:"), 0, 0)
        self.combo_grating = QtWidgets.QComboBox()
        self.combo_grating.addItem("1: 150 l/mm", 1)
        self.combo_grating.addItem("2: 1200 l/mm", 2)
        self.combo_grating.addItem("3: espejo (no se calibra)", 3)
        self.combo_grating.setToolTip("Red cuyo offset se muestra. Las líneas por mm y el blaze se leen del equipo "
                                      "(GetGratingInfo). El espejo no se calibra.")
        self.combo_grating.currentIndexChanged.connect(self._on_grating_combo_changed)
        off_layout.addWidget(self.combo_grating, 0, 1, 1, 2)

        off_layout.addWidget(QtWidgets.QLabel("Grating Offset (pasos):"), 1, 0)
        self.spin_grating_off = self._read_only_steps_spin(GRAT_OFFSET_MAX_STEPS)
        off_layout.addWidget(self.spin_grating_off, 1, 1)
        self.lbl_grating_mark = QtWidgets.QLabel("[?] sin leer")
        off_layout.addWidget(self.lbl_grating_mark, 1, 2)

        off_layout.addWidget(QtWidgets.QLabel("Detector Offset (pasos):"), 2, 0)
        self.spin_detector_off = self._read_only_steps_spin(DET_OFFSET_MAX_STEPS)
        self.spin_detector_off.setToolTip("Offset del detector, leído. Por convención del laboratorio vale 0 (R4-A-2); "
                                          "PySpectrum no lo escribe.")
        off_layout.addWidget(self.spin_detector_off, 2, 1)
        self.lbl_detector_mark = QtWidgets.QLabel("[?] sin leer")
        off_layout.addWidget(self.lbl_detector_mark, 2, 2)

        btn_read_offsets = QtWidgets.QPushButton("📥 Releer el equipo")
        btn_read_offsets.setStyleSheet("background-color: #F9E2AF; color: #11111B;")
        btn_read_offsets.setToolTip("Lee los offsets actuales del Shamrock. No escribe nada.")
        btn_read_offsets.clicked.connect(self._on_read_all_offsets)
        off_layout.addWidget(btn_read_offsets, 3, 0, 1, 3)

        self.btn_register_read = QtWidgets.QPushButton("📝 Registrar lo leído en el archivo")
        self.btn_register_read.setToolTip(
            "Agrega al archivo de calibraciones una entrada MANUAL_ENTRY (EXPERIMENTAL) con los offsets de las\n"
            "redes 1 y 2 tal como se leen ahora del equipo. No toca el equipo.")
        self.btn_register_read.clicked.connect(self.registerReadOffsetsSignal.emit)
        off_layout.addWidget(self.btn_register_read, 4, 0, 1, 3)

        off_layout.addWidget(QtWidgets.QLabel("Historial (archivo local; sólo se agregan entradas):"), 5, 0, 1, 3)
        self.table_history = QtWidgets.QTableWidget(0, 6)
        self.table_history.setHorizontalHeaderLabels(["Fecha", "Tipo", "Red", "Valor (pasos)", "Resultado", "Operador"])
        self.table_history.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_history.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_history.setMinimumHeight(160)
        self.table_history.horizontalHeader().setStretchLastSection(True)
        off_layout.addWidget(self.table_history, 6, 0, 1, 3)

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

        # ── 6. Ventanita: Verificación Raman de Agua ──────────────────────────
        box_water = QtWidgets.QGroupBox("💧 6. Verificación de Calibración con Agua (~649 nm / 3400 cm⁻¹)")
        box_water.setToolTip("Verifica la exactitud de la calibración de longitud de onda usando las bandas Raman intrínsecas del agua (O-H stretch).")
        water_layout = QtWidgets.QGridLayout(box_water)
        water_layout.setSpacing(6)

        self.lbl_water_status = QtWidgets.QLabel("Sin verificar. Colocar cubeta con agua en el foco antes de medir.")
        self.lbl_water_status.setStyleSheet("color: #A6ADC8; font-size: 8.5pt;")
        self.lbl_water_status.setWordWrap(True)
        water_layout.addWidget(self.lbl_water_status, 0, 0, 1, 2)

        self.btn_verify_water = QtWidgets.QPushButton("💧 Verificar Calibración con Agua (3400 cm⁻¹)")
        self.btn_verify_water.setStyleSheet("background-color: #89DCEB; color: #11111B;")
        self.btn_verify_water.setToolTip(
            "Adquiere un espectro con láser 532 nm, ajusta las bandas Raman del agua (~649/702 nm) con\n"
            "fit_signal_raman() y reporta el corrimiento respecto a la posición teórica y la calidad del ajuste (R²)."
        )
        self.btn_verify_water.clicked.connect(self.verifyWaterCalibrationSignal.emit)
        water_layout.addWidget(self.btn_verify_water, 1, 0, 1, 2)

        vbox.addWidget(box_water)

        # ── 7. Ventanita: Perfil de Ruido Oscuro (Dark Current) ───────────────
        box_dark = QtWidgets.QGroupBox("🌑 7. Perfil de Ruido Oscuro (Dark Current)")
        box_dark.setToolTip("Caracteriza el ruido de fondo del detector con todos los obturadores cerrados, para sustracción automática.")
        dark_layout = QtWidgets.QGridLayout(box_dark)
        dark_layout.setSpacing(6)

        self.lbl_dark_status = QtWidgets.QLabel("Sin medir.")
        self.lbl_dark_status.setStyleSheet("color: #A6ADC8; font-size: 8.5pt;")
        self.lbl_dark_status.setWordWrap(True)
        dark_layout.addWidget(self.lbl_dark_status, 0, 0, 1, 2)

        self.btn_measure_dark = QtWidgets.QPushButton("🌑 Medir Ruido Oscuro (Dark Current)")
        self.btn_measure_dark.setStyleSheet("background-color: #313244; color: #CDD6F4;")
        self.btn_measure_dark.setToolTip(
            "Cierra todos los obturadores de cámara y láser, adquiere un cuadro de fondo, y calcula\n"
            "la media y desviación estándar de cuentas por píxel (core/sif_processor.py::characterize_background_noise)."
        )
        self.btn_measure_dark.clicked.connect(self.measureDarkNoiseSignal.emit)
        dark_layout.addWidget(self.btn_measure_dark, 1, 0, 1, 2)

        self.btn_save_dark_profile = QtWidgets.QPushButton("💾 Guardar como Perfil de Sustracción")
        self.btn_save_dark_profile.setEnabled(False)
        self.btn_save_dark_profile.setToolTip("Persiste el último fondo oscuro medido en pyspectrum/calibration/dark_noise_profile.npz para sustracción automática futura.")
        self.btn_save_dark_profile.clicked.connect(self.saveDarkNoiseProfileSignal.emit)
        dark_layout.addWidget(self.btn_save_dark_profile, 2, 0, 1, 2)

        vbox.addWidget(box_dark)

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
        self.plot_widget.setBackground("#11111B")
        self.plot_widget.setLabel('bottom', "Coordenada / Pixel X", color='#CDD6F4')
        self.plot_widget.setLabel('left', "Intensidad (Cuentas)", color='#CDD6F4')
        self.plot_widget.setTitle("<b>Perfil Óptico / Ajuste de Calibración</b>", color='#CDD6F4')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.addLegend(offset=(10, 10))
        self.plot_widget.setToolTip("Visualizador del perfil de intensidad 1D medido en el CCD y curva del ajuste Gaussiano del slit.")

        self.curve_profile = self.plot_widget.plot(name="Perfil Medido", pen=pg.mkPen("#89B4FA", width=2.0))
        self.curve_fit = self.plot_widget.plot(name="Ajuste Gaussiano", pen=pg.mkPen("#F38BA8", width=2.5, style=QtCore.Qt.PenStyle.DashLine))
        self.line_center = pg.InfiniteLine(pos=501.25, angle=90, pen=pg.mkPen("#A6E3A1", width=2.0, style=QtCore.Qt.PenStyle.DotLine), label="Centro Slit")
        self.plot_widget.addItem(self.line_center)

        main_layout.addWidget(self.plot_widget, stretch=3)

    def _on_context_slit_changed(self, width: float, center_px: float, zero_pos: int):
        if abs(self.spin_slit_width.value() - width) > 0.05:
            self.spin_slit_width.blockSignals(True)
            self.spin_slit_width.setValue(width)
            self.spin_slit_width.blockSignals(False)
        if abs(self.spin_pixel_x.value() - center_px) > 0.05:
            self.spin_pixel_x.blockSignals(True)
            self.spin_pixel_x.setValue(center_px)
            self.line_center.setValue(center_px)
            self.spin_pixel_x.blockSignals(False)
        if self.spin_slit_zero.value() != zero_pos:
            self.spin_slit_zero.blockSignals(True)
            self.spin_slit_zero.setValue(zero_pos)
            self.spin_slit_zero.blockSignals(False)

    def _quick_set_slit(self, val: float):
        self.spin_slit_width.setValue(val)
        self.setSlitWidthSignal.emit(val)

    def _on_grating_combo_changed(self):
        grating = self.combo_grating.currentData()
        if grating is not None:
            self.getGratingOffsetSignal.emit(int(grating))

    @staticmethod
    def _read_only_steps_spin(limit: int) -> QtWidgets.QSpinBox:
        spin = QtWidgets.QSpinBox()
        spin.setRange(-int(limit) - 1, int(limit))
        spin.setSpecialValueText("desconocido")      # el mínimo se muestra así: nunca un valor viejo
        spin.setSuffix(" pasos")
        spin.setReadOnly(True)
        spin.setButtonSymbols(QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons)
        return spin

    @staticmethod
    def _show_read(spin: QtWidgets.QSpinBox, mark: QtWidgets.QLabel, value, code) -> None:
        spin.blockSignals(True)
        if value is None:
            spin.setValue(spin.minimum())
            mark.setText(f"[!] no leído (código {code})")
            mark.setStyleSheet("color: #F38BA8;")
        else:
            spin.setValue(int(value))
            mark.setText(f"[L {time.strftime('%H:%M:%S')}]")
            mark.setStyleSheet("color: #A6ADC8;")
        spin.blockSignals(False)

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

    @pyqtSlot(int, object, object)
    def update_grating_offset(self, grating: int, offset, code):
        if self.combo_grating.currentData() != grating:
            return
        self._show_read(self.spin_grating_off, self.lbl_grating_mark, offset, code)
        self.lbl_status.setText(f"Offset de la red {grating}: "
                                + (f"{offset} pasos (leído)." if offset is not None else "desconocido (falló la lectura)."))

    @pyqtSlot(object, object)
    def update_detector_offset(self, offset, code):
        self._show_read(self.spin_detector_off, self.lbl_detector_mark, offset, code)

    @pyqtSlot(object)
    def set_history(self, entries):
        """Llenado inicial del historial, del más nuevo al más viejo."""
        self.table_history.setRowCount(0)
        for entry in entries:
            self._append_history_row(entry, at_top=False)

    @pyqtSlot(object)
    def prepend_history(self, entries):
        """Entradas nuevas arriba, sin reconstruir la tabla (Ronda 3 §4.1)."""
        for entry in entries:
            self._append_history_row(entry, at_top=True)

    def _append_history_row(self, entry, at_top: bool):
        v = entry.values
        value = v.get("offset", v.get("readback", v.get("offset_read")))
        result = v.get("outcome") or ("respaldo" if entry.kind == "PRE_WRITE" else
                                      "arranque" if entry.kind == "OBSERVED" else v.get("provenance", ""))
        if entry.kind == "OBSERVED":
            g = v.get("gratings", {})
            value = "/".join(str(g.get(k, {}).get("offset")) for k in sorted(g))
        cells = [entry.ts.replace("T", " ")[:19], entry.kind,
                 str(entry.key.grating_index) if entry.key else "todas", str(value), str(result), entry.operator]
        row = 0 if at_top else self.table_history.rowCount()
        self.table_history.insertRow(row)
        for col, text in enumerate(cells):
            item = QtWidgets.QTableWidgetItem(text)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, entry.record_id)
            self.table_history.setItem(row, col, item)

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

    @pyqtSlot(float, float, float, np.ndarray, np.ndarray, np.ndarray, np.ndarray)
    def update_water_verification(self, shift_nm: float, observed_peak_nm: float, r2: float,
                                  wave_raw: np.ndarray, spec_raw: np.ndarray, wave_fit: np.ndarray, spec_fit: np.ndarray):
        precision_txt = "ALTA" if abs(shift_nm) < 0.5 else ("MODERADA" if abs(shift_nm) < 2.0 else "BAJA — recalibrar")
        self.lbl_water_status.setText(
            f"Pico O-H observado: <b>{observed_peak_nm:.2f} nm</b> (teórico 649.00 nm) | "
            f"Corrimiento: <b>{shift_nm:+.2f} nm</b> | Ajuste R²={r2:.3f} | Precisión: <b>{precision_txt}</b>"
        )
        if len(wave_raw) > 0:
            self.curve_profile.setData(wave_raw, spec_raw)
        if len(wave_fit) > 0:
            self.curve_fit.setData(wave_fit, spec_fit)

    @pyqtSlot(float, float)
    def update_dark_noise_result(self, mean_counts: float, std_counts: float):
        self.lbl_dark_status.setText(f"Fondo oscuro: media = <b>{mean_counts:.2f}</b> cuentas, σ = <b>{std_counts:.2f}</b> cuentas/píxel.")
        self.btn_save_dark_profile.setEnabled(True)


class CalibrationBackend(QtCore.QObject):
    """Backend de gestión y sincronización de calibraciones ópticas."""

    slitInfoUpdatedSignal = pyqtSignal(float, int)
    gratingOffsetUpdatedSignal = pyqtSignal(int, object, object)    # (red, offset leído o None, código)
    detectorOffsetUpdatedSignal = pyqtSignal(object, object)        # (offset leído o None, código)
    historyInitSignal = pyqtSignal(object)
    historyAppendedSignal = pyqtSignal(object)
    cubicCoeffsUpdatedSignal = pyqtSignal(float, float, float, float)
    slitFitResultSignal = pyqtSignal(float, float, np.ndarray, np.ndarray, np.ndarray)
    activeCalibFileUpdatedSignal = pyqtSignal(str)
    statusSignal = pyqtSignal(str)

    waterVerificationResultSignal = pyqtSignal(float, float, float, np.ndarray, np.ndarray, np.ndarray, np.ndarray)
    darkNoiseResultSignal = pyqtSignal(float, float)

    def __init__(self, camera=None, spectrometer=None, parent=None, repository=None):
        super().__init__(parent)
        self.camera = camera or get_andor_ccd()
        self.spectrometer = spectrometer or get_shamrock()
        self._repository = repository
        self.lamp_calib = HalogenLampCalibration()

        # Estado de parámetros de calibración
        self.slit_width: float = 50.0
        self.slit_center_x: float = 502.00
        self.slit_fwhm: float = 4.12
        self.slit_zero_pos: int = 0
        # Offsets LEÍDOS del equipo; None = desconocido (sin leer o lectura fallida). Nunca un valor por
        # defecto ni del archivo: los del .txt quedan en `file_offsets`, como información (pasos 9-10).
        self.grating_offsets: dict[int, Optional[int]] = {}
        self.detector_offset: Optional[int] = None
        self.file_offsets: dict[str, int] = {}
        self.cubic_coeffs: Tuple[float, float, float, float] = (450.124500, 0.301450, 1.250000e-06, -8.120000e-10)
        self.raman_reference_cm1: float = 520.50
        self.raman_measured_cm1: float = 520.50
        self.raman_offset_cm1: float = 0.00
        self.lamp_file: str = "lamparaIR_450-950_overlap0.2"
        self.lamp_temp_k: float = 3100.0
        self.active_calib_file: str = str(CALIBRATION_TXT_FILE)

        # Fase 7 (DEC-021): último fondo oscuro medido, pendiente de persistir si el usuario lo solicita.
        self._last_dark_frame: Optional[np.ndarray] = None
        self._last_dark_mean: float = 0.0
        self._last_dark_std: float = 0.0

        # Cargar calibración previa al inicializar (prioridad .txt, fallback .json)
        if not self.load_calibration_from_txt(str(CALIBRATION_TXT_FILE)):
            self._load_saved_calibration()

    def make_connection(self, frontend: CalibrationFrontend):
        frontend.gotoZeroOrderSignal.connect(self.goto_zero_order)
        frontend.setSlitWidthSignal.connect(self.set_slit_width)
        frontend.getSlitZeroPosSignal.connect(self.get_slit_zero_position)
        frontend.saveSlitPixelSignal.connect(self.save_slit_pixel)
        frontend.autoCalibrateSlitSignal.connect(self.auto_calibrate_slit)

        frontend.getGratingOffsetSignal.connect(self.get_grating_offset)
        frontend.getDetectorOffsetSignal.connect(self.get_detector_offset)
        frontend.registerReadOffsetsSignal.connect(self.register_read_offsets)
        self.historyInitSignal.connect(frontend.set_history)
        self.historyAppendedSignal.connect(frontend.prepend_history)

        frontend.readCubicCoeffsSignal.connect(self.read_cubic_coefficients)
        frontend.loadLampCalibSignal.connect(self.load_lamp_calibration)

        frontend.saveCalibrationTxtSignal.connect(self.save_calibration_to_txt)
        frontend.loadCalibrationTxtSignal.connect(self.load_calibration_from_txt)
        frontend.reloadLastCalibrationSignal.connect(lambda: self.load_calibration_from_txt(str(CALIBRATION_TXT_FILE)))

        frontend.verifyWaterCalibrationSignal.connect(self.verify_water_calibration)
        frontend.measureDarkNoiseSignal.connect(self.measure_dark_noise)
        frontend.saveDarkNoiseProfileSignal.connect(self.save_dark_noise_profile)
        self.waterVerificationResultSignal.connect(frontend.update_water_verification)
        self.darkNoiseResultSignal.connect(frontend.update_dark_noise_result)

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
        frontend.update_cubic_coefficients(*self.cubic_coeffs)
        frontend.edit_calib_txt_path.setText(self.active_calib_file)
        self.read_initial_values()
        self.publish_history()

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
            spectroscopy_context.set_slit_parameters(
                slit_width_um=self.slit_width,
                slit_center_px=self.slit_center_x,
                slit_zero_pos=self.slit_zero_pos
            )

            for g in (1, 2, 3):
                self.get_grating_offset(g)
            self.get_detector_offset()

            self.read_cubic_coefficients()
        except Exception as e:
            print(f"[Calib Backend] Excepción al leer hardware inicial: {e}")

    @pyqtSlot()
    def goto_zero_order(self):
        # El mismo espejo rápido que el panel y Ctrl+0 (paso 7): ganancia 0 confirmada y obturadores
        # cerrados antes de girar.
        from pyspectrum.modules.zero_order_service import get_zero_order_service
        res = get_zero_order_service(spectrometer=self.spectrometer).enter_specular("zero_order")
        if res.ok:
            self.statusSignal.emit("Orden cero: ganancia EM bloqueada en 0, obturadores cerrados.")
        else:
            self.statusSignal.emit(f"Orden cero no ejecutado: {res.detail}")

    @pyqtSlot(float)
    def set_slit_width(self, width: float):
        self.slit_width = float(width)
        ret = self.spectrometer.ShamrockSetSlit(DEVICE, INPUT_SLIT_PORT, float(width))
        spectroscopy_context.set_slit_parameters(slit_width_um=self.slit_width)
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

    @pyqtSlot(int)
    def get_grating_offset(self, grating: int):
        """Lee el offset de una red. Una lectura fallida deja "desconocido", nunca el valor anterior."""
        ret, off = self.spectrometer.ShamrockGetGratingOffset(DEVICE, int(grating))
        value = int(off) if ret == SHAMROCK_SUCCESS else None
        self.grating_offsets[int(grating)] = value
        self.gratingOffsetUpdatedSignal.emit(int(grating), value, ret)

    @pyqtSlot()
    def get_detector_offset(self):
        ret, off = self.spectrometer.ShamrockGetDetectorOffset(DEVICE)
        self.detector_offset = int(off) if ret == SHAMROCK_SUCCESS else None
        self.detectorOffsetUpdatedSignal.emit(self.detector_offset, ret)

    # ── Archivo de calibraciones (paso 9) ──
    @property
    def repository(self):
        if self._repository is None:
            from pyspectrum.calibration.repository import get_repository
            self._repository = get_repository()
        return self._repository

    def publish_history(self):
        try:
            entries = list(reversed(self.repository.history()))
        except Exception as e:
            self.statusSignal.emit(f"No se pudo leer el archivo de calibraciones: {e}")
            return
        self.historyInitSignal.emit(entries)

    @pyqtSlot()
    def register_read_offsets(self):
        """[Registrar lo leído en el archivo]: una entrada MANUAL_ENTRY (EXPERIMENTAL) por red calibrable, con
        el valor leído ahora. No toca el equipo (Ronda 3 §1.8, §1.11)."""
        from pyspectrum.calibration.repository import CalibrationEntry, CalibrationKey
        spec = self.spectrometer
        ret_s, serial = spec.ShamrockGetSerialNumber(DEVICE)
        ports = []
        for flipper in (1, 2):
            ret_p, port = spec.ShamrockGetFlipper(DEVICE, flipper)
            ports.append(int(port) if ret_p == SHAMROCK_SUCCESS else None)
        if ret_s != SHAMROCK_SUCCESS or None in ports:
            self.statusSignal.emit("No se pudo leer la serie o los puertos del Shamrock: no se registró nada.")
            return
        added = []
        for g in (1, 2):
            info = spec.ShamrockGetGratingInfo(DEVICE, g)
            ret_o, off = spec.ShamrockGetGratingOffset(DEVICE, g)
            if not info or info[0] != SHAMROCK_SUCCESS or ret_o != SHAMROCK_SUCCESS:
                self.statusSignal.emit(f"No se pudo leer la red {g}: no se registró.")
                continue
            key = CalibrationKey(str(serial), g, float(info[1]), ports[0], ports[1])
            entry = CalibrationEntry.manual_entry(key, int(off), source="leído del equipo con PySpectrum 3.0",
                                                  note="adoptado del equipo")
            try:
                self.repository.append(entry)
            except OSError as e:
                self.statusSignal.emit(f"No se pudo escribir el archivo de calibraciones: {e}")
                return
            added.append(entry)
        if added:
            self.historyAppendedSignal.emit(added)
            self.statusSignal.emit(f"Registrado en el archivo: " +
                                   ", ".join(f"red {e.key.grating_index} = {e.values['offset']} pasos" for e in added)
                                   + ". No se escribió nada al equipo.")

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
        spectroscopy_context.set_slit_parameters(slit_center_px=self.slit_center_x)
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
                    profile = np.ones(1004, dtype=np.float64) * 100.0
            else:
                profile = np.ones(1004, dtype=np.float64) * 100.0

            x = np.arange(len(profile), dtype=np.float64)
            y = np.array(profile, dtype=np.float64)

            # 2. Ajuste Gaussiano
            centroid, fwhm, fit_curve = self._fit_gaussian_slit(x, y)
            self.slit_center_x = centroid
            self.slit_fwhm = fwhm
            self._save_calibration_file()
            self.save_calibration_to_txt()
            spectroscopy_context.set_slit_parameters(slit_center_px=centroid)

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

    @pyqtSlot()
    def verify_water_calibration(self):
        """Verifica la exactitud de la calibración de longitud de onda usando las bandas Raman
        intrínsecas del agua (O-H stretch, ~649/702 nm bajo bombeo 532 nm), reutilizando
        fit_signal_raman() de pyspectrum/calibration/fit_raman_water.py sin modificarlo."""
        laser = SHUTTERS[0]  # 532 nm (green)
        if not hardware_session.acquire_session("Verificación Raman de Agua"):
            return
        try:
            self.camera.set_exposure_time(1.0)
            ret, wave_axis = self.spectrometer.ShamrockGetCalibration(DEVICE, 1004)
            open_shutter(laser)
            heartbeat_shutter(30.0)
            if self.camera.get_read_mode() == READ_MODE_IMAGE:
                frame = self.camera.get_most_recent_image()
                spec = np.mean(frame, axis=0)
            else:
                spec = self.camera.get_1d_spectrum()
        finally:
            close_shutter(laser)
            hardware_session.release_session("Verificación Raman de Agua")

        wave_fit, spec_fit, params = fit_signal_raman(np.asarray(wave_axis), np.asarray(spec), laser_nm=532.0)

        # fit_signal_raman() fija peak1/peak2 (649/702 nm) como parámetros del MODELO (sólo ajusta
        # amplitudes), no como posiciones libres — así que el corrimiento real de calibración se
        # mide buscando el máximo observado crudo en una ventana angosta alrededor del pico teórico,
        # sin tocar la función compartida.
        expected_peak_nm = 649.0
        window_nm = 15.0
        wave_arr = np.asarray(wave_axis)
        spec_arr = np.asarray(spec)
        mask = (wave_arr >= expected_peak_nm - window_nm) & (wave_arr <= expected_peak_nm + window_nm)
        if np.any(mask):
            observed_peak_nm = float(wave_arr[mask][np.argmax(spec_arr[mask])])
        else:
            observed_peak_nm = expected_peak_nm
        shift_nm = observed_peak_nm - expected_peak_nm

        r2 = 0.0
        if len(wave_fit) > 0 and len(wave_fit) == len(spec_fit):
            spec_fit_interp = np.interp(wave_arr, wave_fit, spec_fit)
            r2 = calc_r2(spec_arr, spec_fit_interp)

        self.waterVerificationResultSignal.emit(shift_nm, observed_peak_nm, r2, wave_arr, spec_arr, np.asarray(wave_fit), np.asarray(spec_fit))
        self.statusSignal.emit(f"Verificación de agua completada: corrimiento {shift_nm:+.2f} nm respecto a 649.00 nm.")

    @pyqtSlot()
    def measure_dark_noise(self):
        """Cierra todos los obturadores (láser + notch) y caracteriza el ruido de fondo del
        detector con core/sif_processor.py::characterize_background_noise()."""
        if not hardware_session.acquire_session("Perfil de Ruido Oscuro"):
            return
        try:
            close_all_shutters()
            heartbeat_shutter(30.0)
            self.camera.set_exposure_time(0.5)
            if self.camera.get_read_mode() == READ_MODE_IMAGE:
                frame = self.camera.get_most_recent_image()
            else:
                frame = self.camera.get_1d_spectrum()
        finally:
            hardware_session.release_session("Perfil de Ruido Oscuro")

        profile = characterize_background_noise(np.asarray(frame))
        self._last_dark_frame = np.asarray(frame)
        self._last_dark_mean = float(profile.mean_counts)
        self._last_dark_std = float(profile.std_counts)
        self.darkNoiseResultSignal.emit(self._last_dark_mean, self._last_dark_std)
        self.statusSignal.emit(f"Ruido oscuro caracterizado: media={self._last_dark_mean:.2f}, σ={self._last_dark_std:.2f} cuentas/píxel.")

    @pyqtSlot()
    def save_dark_noise_profile(self):
        if self._last_dark_frame is None:
            self.statusSignal.emit("No hay perfil de ruido oscuro medido para guardar.")
            return
        try:
            DARK_NOISE_PROFILE_FILE.parent.mkdir(parents=True, exist_ok=True)
            np.savez(str(DARK_NOISE_PROFILE_FILE), dark_frame=self._last_dark_frame,
                    mean_counts=self._last_dark_mean, std_counts=self._last_dark_std,
                    timestamp=time.strftime("%Y-%m-%d %H:%M:%S"))
            self.statusSignal.emit(f"Perfil de ruido oscuro guardado en: {DARK_NOISE_PROFILE_FILE.name}")
        except Exception as e:
            self.statusSignal.emit(f"Error al guardar perfil de ruido oscuro: {e}")

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
                # Informativos: lo que estaba en el equipo cuando se guardó el archivo. No son una lectura
                # ni se escriben (pasos 9-10); la referencia vive en el archivo de calibraciones.
                self.file_offsets = {}
                for name, field in (("grating_1", "grating_1_offset_steps"), ("grating_2", "grating_2_offset_steps"),
                                    ("grating_3", "grating_3_offset_steps"), ("detector", "detector_offset_steps")):
                    try:
                        self.file_offsets[name] = int(sec.get(field))
                    except (TypeError, ValueError):
                        pass                      # ausente o "desconocido"

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
            spectroscopy_context.set_slit_parameters(
                slit_width_um=self.slit_width,
                slit_center_px=self.slit_center_x,
                slit_zero_pos=self.slit_zero_pos
            )
            self.cubicCoeffsUpdatedSignal.emit(*self.cubic_coeffs)

            # Cargar un archivo NO escribe al Shamrock (DEC-040, C-04). Los offsets viven en el
            # equipo y los comparten Solis y el legado; esta carga corría en cada arranque y pisaba
            # la calibración real con los valores del archivo. Escribir un offset es una acción
            # explícita del operador (R4-3, R4-B-1).
            self.statusSignal.emit(
                f"Calibraciones leídas de {target.name} (no se escribió nada al espectrógrafo).")
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
# Instrumento: Andor Shamrock SR-500i-B2-R | Detector: Andor iXon3 EMCCD ({DETECTOR_WIDTH_PX}x{DETECTOR_HEIGHT_PX}, {DETECTOR_PIXEL_PITCH_UM:g} µm)
# Última actualización: {now_str}
# Archivo de destino: {target.name}
# ==============================================================================

[METADATOS]
instrumento = Andor Shamrock SR-500i
detector = Andor iXon3 EMCCD DU8285 ({DETECTOR_WIDTH_PX}x{DETECTOR_HEIGHT_PX} px, {DETECTOR_PIXEL_PITCH_UM:g} µm)
tamano_pixel_um = {DETECTOR_PIXEL_PITCH_UM:g}
resolucion_horizontal_px = {DETECTOR_WIDTH_PX}
fecha_calibracion = {now_str}
# Guardado por el operador. No es una validación: la aceptación de una calibración la registra
# la rutina de calibración con su procedencia (DEC-040).
estado = GUARDADO_POR_OPERADOR

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
grating_1_offset_steps = {_steps(self.grating_offsets.get(1))}
# Rejilla 2: 1200 l/mm (Blaze 500 nm, alta resolución Raman / plasmónica fina)
grating_2_offset_steps = {_steps(self.grating_offsets.get(2))}
# Rejilla 3: Espejo / Mirror (Alineación confocal de campo claro e imagen directa)
grating_3_offset_steps = {_steps(self.grating_offsets.get(3))}
# Offset mecánico angular de la brida del detector CCD (Shamrock SDK)
detector_offset_steps = {_steps(self.detector_offset)}

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
