# -*- coding: utf-8 -*-
"""
calibration_dock.py — Pestaña Modular de Calibraciones del Sistema
PySpectrum 3.0 — UNSAM Nanofotónica

Provee paneles modulares ("ventanitas") para:
1. Ranura de Entrada & Pixel X Central del Slit: centro de la ranura en orden cero, una gaussiana por fila del
   ROI vertical (R4-N 1a; `pyspectrum/calibration/slit_center.py`), aplicado sólo con [Aplicar].
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
    get_andor_ccd, DETECTOR_PIXEL_PITCH_UM, DETECTOR_WIDTH_PX, DETECTOR_HEIGHT_PX,
)
from pyspectrum.modules.spectroscopy_context import spectroscopy_context
from pyspectrum.calibration.halogen_lamp import HalogenLampCalibration


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
    autoCalibrateSlitSignal = pyqtSignal(float, int)      # exposición (s), cuadros (R4-N 1a)
    applySlitCenterSignal = pyqtSignal()                  # [Aplicar como centro de ranura] (P3)

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

        self.btn_save_px = QtWidgets.QPushButton("💾 Guardar Pixel X")
        self.btn_save_px.setToolTip("Guarda este valor a mano como centro de la ranura. Queda registrado en el "
                                    "archivo de calibraciones (SLIT_CENTER, a mano).")
        self.btn_save_px.clicked.connect(lambda: self.saveSlitPixelSignal.emit(self.spin_pixel_x.value()))
        slit_layout.addWidget(self.btn_save_px, 3, 2)

        # Autocalibración del centro (R4-N 1a): una gaussiana por fila del ROI vertical, en orden cero.
        exp_row = QtWidgets.QHBoxLayout()
        exp_row.addWidget(QtWidgets.QLabel("Exposición:"))
        self.spin_slit_exp = QtWidgets.QDoubleSpinBox()
        self.spin_slit_exp.setRange(0.001, 10.0)
        self.spin_slit_exp.setDecimals(3)
        self.spin_slit_exp.setSingleStep(0.01)
        self.spin_slit_exp.setValue(0.05)
        self.spin_slit_exp.setSuffix(" s")
        self.spin_slit_exp.setToolTip("Exposición de los cuadros de la ranura. Si el crudo llega al 80 % del ADC, "
                                      "la medición se rechaza: bajala.")
        exp_row.addWidget(self.spin_slit_exp)
        exp_row.addWidget(QtWidgets.QLabel("Cuadros:"))
        self.spin_slit_frames = QtWidgets.QSpinBox()
        self.spin_slit_frames.setRange(1, 20)
        self.spin_slit_frames.setValue(1)
        self.spin_slit_frames.setToolTip("Cuadros nuevos. La estadística sale de las filas; con 3 o más, cada píxel "
                                         "es la mediana en el tiempo y los rayos cósmicos se descartan.")
        exp_row.addWidget(self.spin_slit_frames)
        exp_row.addStretch()
        slit_layout.addLayout(exp_row, 4, 0, 1, 3)

        self.btn_auto_slit = QtWidgets.QPushButton("🔍 Auto-Calibrar Centro de la Ranura (una gaussiana por fila)")
        self.btn_auto_slit.setStyleSheet("background-color: #A6E3A1; color: #11111B;")
        self.btn_auto_slit.setToolTip(
            "En orden cero, con luz sobre la ranura: toma cuadros nuevos de las filas del ROI vertical\n"
            "(Exploración), ajusta una gaussiana en cada fila y promedia la posición del máximo.\n"
            "Abre el obturador del espectrómetro sólo mientras mide; no toca láseres.\n"
            "No cambia nada hasta [Aplicar]. Si falla, no guarda nada y dice por qué."
        )
        self.btn_auto_slit.clicked.connect(lambda: self.autoCalibrateSlitSignal.emit(
            float(self.spin_slit_exp.value()), int(self.spin_slit_frames.value())))
        slit_layout.addWidget(self.btn_auto_slit, 5, 0, 1, 3)

        self.lbl_slit_result = QtWidgets.QLabel("Sin medición.")
        self.lbl_slit_result.setWordWrap(True)
        self.lbl_slit_result.setStyleSheet("color: #A6ADC8; font-size: 8.5pt;")
        self.lbl_slit_result.setToolTip(
            "Centro ± u (Tipo A, de las filas), FWHM en px y µm (× 8 µm), dispersión de los centros respecto de la\n"
            "recta, inclinación de la ranura sobre el sensor y filas usadas. TILT: el centro corre más de 1 px de\n"
            "punta a punta del ROI (el promedio es el centro en la mitad del ROI). EXPERIMENTAL.")
        slit_layout.addWidget(self.lbl_slit_result, 6, 0, 1, 3)

        self.btn_apply_slit_center = QtWidgets.QPushButton("✔ Aplicar como centro de ranura")
        self.btn_apply_slit_center.setEnabled(False)
        self.btn_apply_slit_center.setToolTip("Adopta el centro medido: lo guarda en el archivo de calibración del "
                                              "programa y lo registra en el archivo de calibraciones (SLIT_CENTER, "
                                              "EXPERIMENTAL). Sólo con una medición que salió bien.")
        self.btn_apply_slit_center.clicked.connect(self.applySlitCenterSignal.emit)
        slit_layout.addWidget(self.btn_apply_slit_center, 7, 0, 1, 3)

        # Slit Zero Position SDK
        lbl_sz = QtWidgets.QLabel("Slit Zero Pos (SDK steps):")
        lbl_sz.setToolTip("Posición mecánica cero de calibración del slit en pasos de motor del SDK Shamrock.")
        slit_layout.addWidget(lbl_sz, 8, 0)
        self.spin_slit_zero = QtWidgets.QSpinBox()
        self.spin_slit_zero.setRange(-10000, 10000)
        self.spin_slit_zero.setReadOnly(True)
        self.spin_slit_zero.setButtonSymbols(QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_slit_zero.setToolTip("Cero de la ranura en pasos de motor, leído del Shamrock. PySpectrum no lo "
                                       "escribe (R2-inst §3.2).")
        slit_layout.addWidget(self.spin_slit_zero, 8, 1)

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

        # Verificación con agua y ruido oscuro: RETIRADAS (investigador, 2026-09-30; DEC-040). La primera abría
        # el 532, leía un cuadro sin adquirir y, sin banda, informaba corrimiento 0; la segunda no verificaba el
        # cierre de los obturadores y caracterizaba con un cuadro viejo.
        self.lbl_retired = QtWidgets.QLabel(
            "Verificación con agua y ruido oscuro: <b>retiradas</b> (2026-09-30). "
            "La λ se verifica en la sub-pestaña <b>Calibración de λ (automática)</b>. "
            "El fondo se toma en cada procedimiento, con la misma configuración (exposición, ganancia, "
            "modo de lectura) y todo apagado o el obturador del espectrómetro cerrado, a elección.")
        self.lbl_retired.setWordWrap(True)
        self.lbl_retired.setStyleSheet("color: #A6ADC8; font-size: 8.5pt;")
        vbox.addWidget(self.lbl_retired)

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
        # El centro medido, todavía sin aplicar (R4-N 1a)
        self.line_candidate = pg.InfiniteLine(pos=501.25, angle=90, pen=pg.mkPen("#F9E2AF", width=1.5,
                                              style=QtCore.Qt.PenStyle.DashLine), label="medido")
        self.line_candidate.hide()
        self.plot_widget.addItem(self.line_candidate)

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
        target = str(entry.key.grating_index) if entry.key else "todas"
        if entry.kind == "SLIT_CENTER":
            value, target = f"{float(v.get('center_px', float('nan'))):.2f} px", "ranura"
        cells = [entry.ts.replace("T", " ")[:19], entry.kind, target, str(value), str(result), entry.operator]
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

    @pyqtSlot(object)
    def update_slit_fit_result(self, result):
        """El resultado de la autocalibración (R4-N 1a). No cambia el centro: eso es [Aplicar]."""
        ok = bool(getattr(result, "ok", False))
        text = result.summary() if result is not None else "Sin medición."
        color = "#A6E3A1" if ok else "#F38BA8"
        self.lbl_slit_result.setText(f"<span style='color:{color}'>{text}</span>")
        self.btn_apply_slit_center.setEnabled(ok)
        if ok and result.profile is not None:
            self.curve_profile.setData(np.arange(result.profile.size, dtype=np.float64), result.profile)
            if result.fit_x is not None:
                self.curve_fit.setData(result.fit_x, result.fit_y)
            self.line_candidate.setValue(result.center_px)
            self.line_candidate.show()
        else:
            self.curve_fit.setData([], [])
            self.line_candidate.hide()
        self.lbl_status.setText("Ranura: medición lista, sin aplicar." if ok else "Ranura: la medición no sirvió.")

    @pyqtSlot(bool)
    def set_slit_running(self, running: bool):
        self.btn_auto_slit.setEnabled(not running)
        if running:
            self.btn_apply_slit_center.setEnabled(False)
            self.lbl_slit_result.setText("Midiendo la ranura…")

    @pyqtSlot()
    def slit_center_applied(self):
        self.btn_apply_slit_center.setEnabled(False)
        self.line_candidate.hide()

    @pyqtSlot(str)
    def show_status(self, msg: str):
        self.lbl_status.setText(msg)



class CalibrationBackend(QtCore.QObject):
    """Backend de gestión y sincronización de calibraciones ópticas."""

    slitInfoUpdatedSignal = pyqtSignal(float, int)
    gratingOffsetUpdatedSignal = pyqtSignal(int, object, object)    # (red, offset leído o None, código)
    detectorOffsetUpdatedSignal = pyqtSignal(object, object)        # (offset leído o None, código)
    historyInitSignal = pyqtSignal(object)
    historyAppendedSignal = pyqtSignal(object)
    cubicCoeffsUpdatedSignal = pyqtSignal(float, float, float, float)
    slitFitResultSignal = pyqtSignal(object)        # SlitCenterResult (R4-N 1a)
    slitRunningSignal = pyqtSignal(bool)
    slitCenterAppliedSignal = pyqtSignal()
    activeCalibFileUpdatedSignal = pyqtSignal(str)
    statusSignal = pyqtSignal(str)


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

        # Autocalibración de la ranura (R4-N 1a): en su propio hilo, con su sesión; nada se aplica sin [Aplicar].
        from pyspectrum.calibration.slit_center import SESSION_NAME
        from pyspectrum.modules.routines.routine_thread import RoutineThread
        self.slit_thread = RoutineThread(SESSION_NAME, self)
        self.slit_thread.finished.connect(self._on_slit_finished)
        self.pending_slit = None              # la última medición que salió bien, sin aplicar
        self._slit_result = None
        self._slit_meta: dict = {}

        # Cargar calibración previa al inicializar (prioridad .txt, fallback .json)
        if not self.load_calibration_from_txt(str(CALIBRATION_TXT_FILE)):
            self._load_saved_calibration()

    def make_connection(self, frontend: CalibrationFrontend):
        frontend.gotoZeroOrderSignal.connect(self.goto_zero_order)
        frontend.setSlitWidthSignal.connect(self.set_slit_width)
        frontend.getSlitZeroPosSignal.connect(self.get_slit_zero_position)
        frontend.saveSlitPixelSignal.connect(self.save_slit_pixel)
        frontend.autoCalibrateSlitSignal.connect(self.auto_calibrate_slit)
        frontend.applySlitCenterSignal.connect(self.apply_slit_center)
        self.slitRunningSignal.connect(frontend.set_slit_running)
        self.slitCenterAppliedSignal.connect(frontend.slit_center_applied)

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
        registered = self._register_slit_center({"center_px": float(pixel_x), "provenance": "EXPERIMENTAL"},
                                                method="manual_entry", note="escrito a mano")
        self.statusSignal.emit(f"Pixel X central {pixel_x:.2f} px guardado en configuración."
                               + ("" if registered else " ⚠️ No se pudo registrar en el archivo de calibraciones."))

    # ── Autocalibración del centro de la ranura (R4-N 1a) ──
    def _slit_data_dir(self) -> Path:
        base = os.getenv("PYSPECTRUM_ROUTINE_DATA_DIR") or str(Path.home() / "Documents" / "Data_PySpectrum")
        return Path(base) / "calibration"

    @pyqtSlot(float, int)
    def auto_calibrate_slit(self, exposure_s: float = 0.05, n_frames: int = 1):
        """Mide el centro en orden cero sobre las filas del ROI vertical. No aplica nada (P3)."""
        from pyspectrum.calibration import slit_center as sc
        from pyspectrum.modules.routines.grid_runner import GridAbort, NodeFailed
        if self.slit_thread.running:
            self.statusSignal.emit("La calibración de la ranura ya está corriendo.")
            return
        y_min, y_max, _c, height = spectroscopy_context.vertical_roi
        try:
            rows = sc.check_rows((y_min, y_max) if height > 0 else (0, 0))
            sc.check_zero_order(sc.zero_order_mode(self.camera, self.spectrometer))
        except sc.SlitCalibrationRefused as e:
            self.statusSignal.emit(f"⛔ {e}")
            return
        self.pending_slit = None
        self._slit_result = None
        self._slit_meta = {"exposure_s": float(exposure_s), "n_frames": int(n_frames),
                           "slit_width_um": float(self.slit_width)}
        frames_box = []

        def expose_recording(runner):
            def expose(shape, exp):
                fr = runner.expose(shape, exp)
                frames_box.append(fr)
                return fr
            return expose

        def body(runner, ctl):
            try:
                res = sc.measure_slit_center(self.camera, expose_recording(runner), exposure_s=float(exposure_s),
                                             rows=rows, n_frames=int(n_frames),
                                             mode_fn=lambda: sc.zero_order_mode(self.camera, self.spectrometer))
            except sc.SlitCalibrationRefused as e:
                res = sc.failed_result(str(e), rows, 0, 0.0, ["REFUSED"])
            except NodeFailed as e:
                res = sc.failed_result(str(e), rows, len(frames_box), 0.0, ["ACQUISITION_FAILED"])
            except GridAbort:
                res = sc.failed_result("detenida (Stop o E-STOP)", rows, len(frames_box), 0.0, ["STOPPED"])
            if res.ok:
                path = sc.save_slit_frames(self._slit_data_dir(), np.stack(frames_box), res, self._slit_meta)
                res = sc.with_frames_file(res, path)
            self._slit_result = res
            return "done"
        err = self.slit_thread.start(body, camera=self.camera, spectrometer=self.spectrometer, mirror=None,
                                     needs_spectrometer=True, require_mirror=False, restore_mirror=False)
        if err:
            self.statusSignal.emit(f"⛔ La calibración de la ranura no arrancó: {err}")
            return
        self.slitRunningSignal.emit(True)
        self.statusSignal.emit("Midiendo el centro de la ranura…")

    @pyqtSlot(str)
    def _on_slit_finished(self, outcome: str):
        from pyspectrum.calibration import slit_center as sc
        res = self._slit_result
        if res is None:
            res = sc.failed_result(f"la medición terminó sin resultado ({outcome})", (0, 0), 0, 0.0, ["ERROR"])
        self.pending_slit = res if res.ok else None
        self.slitRunningSignal.emit(False)
        self.slitFitResultSignal.emit(res)
        self.statusSignal.emit(("Ranura medida, sin aplicar: " if res.ok else "Ranura: ") + res.summary())

    @pyqtSlot()
    def apply_slit_center(self):
        """[Aplicar como centro de ranura] (P3): adopta la última medición buena y la registra (P4)."""
        res = self.pending_slit
        if res is None or not res.ok:
            self.statusSignal.emit("No hay una medición de la ranura para aplicar.")
            return
        self.slit_center_x = float(res.center_px)
        self.slit_fwhm = float(res.fwhm_px)
        self._save_calibration_file()
        self.save_calibration_to_txt()
        spectroscopy_context.set_slit_parameters(slit_center_px=self.slit_center_x)
        values = dict(res.values())
        values.update(self._slit_meta)
        registered = self._register_slit_center(values, method="row_gaussian_mean",
                                                note="autocalibración en orden cero (R4-N 1a)")
        self.pending_slit = None
        self.slitCenterAppliedSignal.emit()
        self.statusSignal.emit(f"Centro de la ranura aplicado: {res.center_px:.2f} ± {res.u_center_px:.2f} px."
                               + ("" if registered else " ⚠️ No se pudo registrar en el archivo de calibraciones."))

    def _register_slit_center(self, values: dict, *, method: str, note: str) -> bool:
        """Una entrada SLIT_CENTER (EXPERIMENTAL) en el archivo de calibraciones, con el equipo que se leyó."""
        from pyspectrum.calibration.repository import CalibrationEntry
        spec = self.spectrometer
        ident = {"serial": None, "entrance_port": None, "exit_port": None}
        try:
            ret_s, serial = spec.ShamrockGetSerialNumber(DEVICE)
            ident["serial"] = str(serial) if ret_s == SHAMROCK_SUCCESS else None
            for name, flipper in (("entrance_port", 1), ("exit_port", 2)):
                ret_p, port = spec.ShamrockGetFlipper(DEVICE, flipper)
                ident[name] = int(port) if ret_p == SHAMROCK_SUCCESS else None
        except Exception:
            pass
        v = dict(values)
        v.update(ident)
        v.setdefault("slit_width_um", float(self.slit_width))
        entry = CalibrationEntry("SLIT_CENTER", None, method=method, note=note, values=v)
        try:
            self.repository.append(entry)
        except OSError as e:
            print(f"[Calib Backend] No se pudo registrar SLIT_CENTER: {e}")
            return False
        self.historyAppendedSignal.emit([entry])
        return True

    def shutdown(self, timeout_ms: int = 3000):
        """Cierre de PySpectrum (paso 13): detiene la medición de la ranura en curso."""
        return self.slit_thread.shutdown(timeout_ms)

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
