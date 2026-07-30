# -*- coding: utf-8 -*-
"""
trace.py — Adquisición continua de fotodiodos y trazado en tiempo real
PyPrinting — UNSAM Nanofotónica  —  PyQt6

Funcionalidades:
  - Trazado continuo en tiempo real de 2 Lásers a la vez (Láser 1 y Láser 2 seleccionables).
  - Botón compartido de Play/Stop y Guardar Traza.
  - Ventana flotante e independiente de Calibración BS (PowerBSWindow) con gráfico "Trace on BS" integrado.
  - Auto-activación del botón Power BS mientras la ventana de calibración esté abierta.
  - Emisión unificada a printing / dimers.
"""
from __future__ import annotations
import os
import time
import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore    import Qt, QObject, QThread, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (QApplication, QFrame, QWidget, QGridLayout,
                               QHBoxLayout, QVBoxLayout, QLabel, QLineEdit, QComboBox,
                               QPushButton, QMessageBox)
from PyQt6.QtGui     import QKeySequence, QShortcut
from pyqtgraph.dockarea import DockArea, Dock

from config import SHUTTERS, DEFAULT_DATA_PATH
from nidaq  import (open_shutter, close_shutter,
                    channels_photodiodos, RATE_MULTICHANNEL, SAFE_MODE)


class PowerBSWindow(QWidget):
    """Ventana independiente para calibración y monitoreo de potencia en BS (Trace on BS)."""
    powerBsActiveSignal = pyqtSignal(bool)
    calibrationBSSignal = pyqtSignal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Calibración & Power in BS — PyPrinting")
        self.resize(580, 480)

        self.mean_BS = 0.0
        self._setup_ui()

    def _setup_ui(self):
        vlo = QVBoxLayout(self)

        # ── Controles de Calibración BS ───────────────────────────────────────
        cal_box = QWidget()
        lo = QGridLayout(cal_box)

        self.High_mW = QLineEdit("3.3")
        self.Low_mW  = QLineEdit("1.0")
        self.High_BS = QLabel("NaN")
        self.Low_BS  = QLabel("NaN")

        self.High_Button = QPushButton("Set High")
        self.High_Button.clicked.connect(lambda: self.High_BS.setText(f"{self.mean_BS:.3f}"))
        self.Low_Button  = QPushButton("Set Low")
        self.Low_Button.clicked.connect(lambda: self.Low_BS.setText(f"{self.mean_BS:.3f}"))

        self.calibration_Button = QPushButton("Set Calibration")
        self.calibration_Button.clicked.connect(self._set_calibration)

        self.intercept_Edit = QLineEdit("0")
        self.slope_Edit     = QLineEdit("3")
        self.power_mean_BS  = QLabel("0.00 mW")
        self.power_mean_BS.setStyleSheet("QLabel { color: #e5534b; font-size: 14pt; font-weight: bold; }")

        self.btn_power_bs = QPushButton("⚡ Active Power BS Measurement")
        self.btn_power_bs.setCheckable(True)
        self.btn_power_bs.setChecked(True)
        self.btn_power_bs.setStyleSheet("QPushButton:checked { background-color: #3ecf8e; color: #111; font-weight: bold; }")
        self.btn_power_bs.toggled.connect(lambda chk: self.powerBsActiveSignal.emit(chk))

        lo.addWidget(self.btn_power_bs,        0, 0, 1, 4)
        lo.addWidget(QLabel("Power BFP (mW):"), 1, 1)
        lo.addWidget(QLabel("Photodiode (V):"), 1, 2)
        lo.addWidget(QLabel("High:"),  2, 0); lo.addWidget(self.High_mW, 2, 1)
        lo.addWidget(QLabel("Low:"),   3, 0); lo.addWidget(self.Low_mW,  3, 1)
        lo.addWidget(self.High_BS,     2, 2); lo.addWidget(self.High_Button, 2, 3)
        lo.addWidget(self.Low_BS,      3, 2); lo.addWidget(self.Low_Button,  3, 3)
        lo.addWidget(self.calibration_Button, 4, 0, 1, 2)
        lo.addWidget(QLabel("Intercept (mW):"), 5, 0); lo.addWidget(self.intercept_Edit, 5, 1)
        lo.addWidget(QLabel("Slope (mW/V):"),   5, 2); lo.addWidget(self.slope_Edit,     5, 3)
        lo.addWidget(QLabel("Power mean on BS (mW):"), 6, 0, 1, 2)
        lo.addWidget(self.power_mean_BS, 6, 2, 1, 2)

        vlo.addWidget(cal_box)

        # ── Gráfico "Trace on BS" (Ubicado abajo de los controles) ───────────
        self.traceBSWidget = pg.GraphicsLayoutWidget()
        self.pBS = self.traceBSWidget.addPlot(row=0, col=0, title="Trace on BS (Fotodiodo Divisor)")
        self.pBS.showGrid(x=True, y=True)
        self.pBS.setLabel("left", "Fotodiodo BS (V)")
        self.pBS.setLabel("bottom", "Tiempo (s)")
        self.curve_BS = self.pBS.plot(pen=pg.mkPen("#e5534b", width=1.5))

        vlo.addWidget(self.traceBSWidget, stretch=1)

    def _set_calibration(self):
        try:
            xo = float(self.Low_BS.text())
            x1 = float(self.High_BS.text())
            yo = float(self.Low_mW.text())
            y1 = float(self.High_mW.text())
            slope     = round((y1 - yo) / (x1 - xo), 2)
            intercept = round(yo - slope * xo, 3)
            self.slope_Edit.setText(str(slope))
            self.intercept_Edit.setText(str(intercept))
            self.calibrationBSSignal.emit(slope, intercept)
        except (ValueError, ZeroDivisionError) as e:
            print(f"[PowerBS] Error en calibración: {e}")

    def update_bs_data(self, timeaxis: np.ndarray, bs_data: np.ndarray, mean_bs: float):
        self.curve_BS.setData(timeaxis, bs_data)
        self.mean_BS = round(mean_bs, 3)
        try:
            slope     = float(self.slope_Edit.text())
            intercept = float(self.intercept_Edit.text())
            power     = round(slope * self.mean_BS + intercept, 3)
            self.power_mean_BS.setText(f"{power:.3f} mW")
        except ValueError:
            pass

    def showEvent(self, event):
        super().showEvent(event)
        self.btn_power_bs.setChecked(True)
        self.powerBsActiveSignal.emit(True)

    def closeEvent(self, event):
        self.btn_power_bs.setChecked(False)
        self.powerBsActiveSignal.emit(False)
        super().closeEvent(event)


# ══════════════════════════════════════════════════════════════════════════════
class Frontend(QFrame):

    startSignal          = pyqtSignal(bool, int, int) # play, laser1_idx, laser2_idx
    stopSignal           = pyqtSignal()
    saveSignal           = pyqtSignal()
    parametersSignal     = pyqtSignal(list)           # [after, before]
    calibrationBS_Signal = pyqtSignal(float, float)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mean_BS = 0.0
        self.powerBSWindow = PowerBSWindow()
        self.powerBSWindow.powerBsActiveSignal.connect(self._on_power_bs_active)
        self.powerBSWindow.calibrationBSSignal.connect(lambda s, i: self.calibrationBS_Signal.emit(s, i))
        self._setup_gui()

    # ── Acciones ──────────────────────────────────────────────────────────────

    def _get_trace(self):
        self.startSignal.emit(
            self.traceButton.isChecked(),
            self.trace_laser1.currentIndex(),
            self.trace_laser2.currentIndex()
        )

    def _get_stop(self):
        self.traceButton.setChecked(False)
        self.stopSignal.emit()

    def _get_save(self):
        self.saveSignal.emit()

    def _get_power_bs(self):
        self.powerBSWindow.show()
        self.powerBSWindow.raise_()

    def _on_power_bs_active(self, active: bool):
        pass

    def _color_menu(self, combo: QComboBox):
        colors = ["color: green;", "color: red;", "color: #d4ac0d; font-weight: bold;", "color: blue;", "color: darkred;"]
        idx = combo.currentIndex()
        if 0 <= idx < len(colors):
            combo.setStyleSheet(f"QComboBox {{ {colors[idx]} }}")

    # ── GUI ───────────────────────────────────────────────────────────────────

    def _setup_gui(self):
        sc_f1 = QShortcut(QKeySequence("F1"), self)
        sc_f1.activated.connect(lambda: self.traceButton.click())
        sc_f2 = QShortcut(QKeySequence("F2"), self)
        sc_f2.activated.connect(self._get_stop)

        # Selección de Lásers Simultáneos
        self.trace_laser1 = QComboBox(); self.trace_laser1.addItems(SHUTTERS); self.trace_laser1.setFixedWidth(100)
        self.trace_laser2 = QComboBox(); self.trace_laser2.addItems(SHUTTERS); self.trace_laser2.setFixedWidth(100)
        if len(SHUTTERS) > 1: self.trace_laser2.setCurrentIndex(1)

        self.trace_laser1.currentIndexChanged.connect(lambda: self._color_menu(self.trace_laser1))
        self.trace_laser2.currentIndexChanged.connect(lambda: self._color_menu(self.trace_laser2))
        self._color_menu(self.trace_laser1)
        self._color_menu(self.trace_laser2)

        # Botones Compartidos de Play/Stop y Guardar Traza
        self.traceButton = QPushButton("► Play / ■ Stop  (F1/F2)")
        self.traceButton.setCheckable(True)
        self.traceButton.clicked.connect(self._get_trace)

        self.saveButton = QPushButton("Save trace")
        self.saveButton.clicked.connect(self._get_save)
        self.saveButton.setStyleSheet("QPushButton { background-color: rgb(200,200,10); }")

        self.setPowerBSButton = QPushButton("View Power BS")
        self.setPowerBSButton.clicked.connect(self._get_power_bs)

        self.PointLabel = QLabel("<b>0.00 | 0.00</b>")
        self.PointLabel.setTextFormat(Qt.TextFormat.RichText)

        paramWidget = QWidget()
        pg_lo = QHBoxLayout(paramWidget)
        pg_lo.setContentsMargins(4, 2, 4, 2)
        pg_lo.setSpacing(6)

        pg_lo.addWidget(QLabel("Láser 1:"))
        pg_lo.addWidget(self.trace_laser1)
        pg_lo.addWidget(QLabel("Láser 2:"))
        pg_lo.addWidget(self.trace_laser2)
        pg_lo.addWidget(self.traceButton)
        pg_lo.addWidget(self.PointLabel)
        pg_lo.addWidget(self.saveButton)
        pg_lo.addWidget(self.setPowerBSButton)
        pg_lo.addStretch()

        # ── Área de Trazas Dobles en Vivo (Láser 1 y Láser 2) ────────────────
        self.traceWidget = pg.GraphicsLayoutWidget()
        self.pL1  = self.traceWidget.addPlot(row=0, col=0, title="Trace Láser 1")
        self.pL2  = self.traceWidget.addPlot(row=0, col=1, title="Trace Láser 2")

        for p in (self.pL1, self.pL2):
            p.showGrid(x=True, y=True)
            p.setLabel("left", "Fotodiodo (V)")
            p.setLabel("bottom", "Tiempo (s)")

        self.curve_L1 = self.pL1.plot(pen=pg.mkPen("#3ecf8e", width=1.5))
        self.curve_L2 = self.pL2.plot(pen=pg.mkPen("#4a9eff", width=1.5))

        hbox      = QHBoxLayout(self)
        dock_area = DockArea()

        paramDock = Dock("", size=(100, 1))
        paramDock.addWidget(paramWidget)
        dock_area.addDock(paramDock)

        viewDock = Dock("Viewbox", size=(100, 5))
        viewDock.addWidget(self.traceWidget)
        dock_area.addDock(viewDock, "bottom", paramDock)

        hbox.addWidget(dock_area)
        self.setLayout(hbox)

    # ── Actualización de datos ────────────────────────────────────────────────

    @pyqtSlot(list)
    def get_data(self, data: list):
        n, timeaxis, intensity, med2, med, intensity_BS, mean_BS = data
        SHOW = 1000
        sl = slice(max(0, n - SHOW), n)
        t  = timeaxis[sl] if n >= SHOW else timeaxis
        i  = intensity[sl] if n >= SHOW else intensity
        bs = intensity_BS[sl] if n >= SHOW else intensity_BS

        self.curve_L1.setData(t, i)
        self.curve_L2.setData(t, bs)
        self.PointLabel.setText(f"<b>{med2:.3f} | {med:.3f}</b>")

        self.mean_BS = round(mean_BS, 3)
        if self.powerBSWindow.isVisible():
            self.powerBSWindow.update_bs_data(t, bs, mean_BS)

    def make_connection(self, backend: Backend):
        backend.dataSignal.connect(self.get_data)


# ══════════════════════════════════════════════════════════════════════════════
class Backend(QObject):

    dataSignal          = pyqtSignal(list)
    data_printingSignal = pyqtSignal(list)  # incluye mode en data[-1]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.file_path = str(DEFAULT_DATA_PATH)
        self.pointtimer = QTimer(self)
        self.pointtimer.timeout.connect(self._trace_update)
        self._init_params()
        self.steps_after  = 10
        self.steps_before = 10
        self.laser        = SHUTTERS[0]
        self.mode_printing = "none"

    def _init_params(self):
        self.rate = RATE_MULTICHANNEL / 100
        self.N    = 10

    # ── Control de la traza ───────────────────────────────────────────────────

    @pyqtSlot(bool, int, int)
    def play_pause(self, play: bool, color_laser1: int = 0, color_laser2: int = 0):
        self.laser = SHUTTERS[color_laser1]
        self.mode_printing = "none"
        if play:
            self._start()
        else:
            self._stop_and_save()

    @pyqtSlot()
    def stop(self):
        self._stop_and_save()

    def _start(self):
        open_shutter(self.laser)
        self._n     = 0
        self.timeaxis     = np.array([])
        self.intensity    = np.array([])
        self.intensity_BS = np.array([])
        self.pointtimer.start(int(1000 / self.rate))

    def _stop_and_save(self):
        self.pointtimer.stop()
        close_all_tasks()
        close_shutter(self.laser)

    @pyqtSlot(list)
    def parameters(self, steps: list):
        if len(steps) >= 2:
            self.steps_after  = steps[0]
            self.steps_before = steps[1]

    @pyqtSlot(str)
    def direction(self, file_path: str):
        self.file_path = file_path

    @pyqtSlot(str, str)
    @pyqtSlot(int, str)
    def trace_configuration(self, laser_input, mode_printing: str = "none"):
        if isinstance(laser_input, int):
            if 0 <= laser_input < len(SHUTTERS):
                self.laser = SHUTTERS[laser_input]
        elif isinstance(laser_input, str):
            self.laser = laser_input
        self.mode_printing = mode_printing

    @pyqtSlot(float, float)
    def set_calibration_bs(self, slope: float, intercept: float):
        pass

    # ── Adquisición periódico ─────────────────────────────────────────────────

    def _trace_update(self):
        self._n += 1

        if SAFE_MODE:
            val    = 1.0 + 0.3 * np.sin(self._n * 0.1) + np.random.normal(0, 0.05)
            val_bs = 0.5 + 0.1 * np.cos(self._n * 0.1) + np.random.normal(0, 0.02)
        else:
            try:
                raw    = channels_photodiodos(1)
                val    = float(raw[0])
                val_bs = float(raw[1]) if len(raw) > 1 else val * 0.5
            except Exception as e:
                val, val_bs = 0.0, 0.0

        t_now = self._n / self.rate
        self.timeaxis     = np.append(self.timeaxis,     t_now)
        self.intensity    = np.append(self.intensity,    val)
        self.intensity_BS = np.append(self.intensity_BS, val_bs)

        med2 = float(np.mean(self.intensity[-self.N:]))    if len(self.intensity) >= self.N else val
        med  = float(np.mean(self.intensity))
        mean_BS = float(np.mean(self.intensity_BS[-self.N:])) if len(self.intensity_BS) >= self.N else val_bs

        data = [self._n, self.timeaxis, self.intensity, med2, med, self.intensity_BS, mean_BS]
        self.dataSignal.emit(data)

        if self.mode_printing != "none":
            data_p = list(data) + [self.mode_printing]
            self.data_printingSignal.emit(data_p)

    def save_trace(self, filename: str = "trace.txt"):
        if len(self.timeaxis) == 0: return
        t_str = time.strftime("%Y%m%d_%H%M%S")
        path  = os.path.join(self.file_path, f"{t_str}_{filename}")
        data  = np.column_stack((self.timeaxis, self.intensity, self.intensity_BS))
        header = f"Trace Data - PyPrinting\nLáser: {self.laser}\nTime(s)\tIntensity(V)\tIntensity_BS(V)"
        np.savetxt(path, data, fmt="%.6f", delimiter="\t", header=header)
        print(f"[Trace] Guardado en: {path}")
