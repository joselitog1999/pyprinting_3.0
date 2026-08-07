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

from config import (SHUTTERS, DEFAULT_DATA_PATH,
                    DEFAULT_TRACE_STEPS_BEFORE, DEFAULT_TRACE_STEPS_AFTER,
                    DEFAULT_POWER_BS_HIGH_MW, DEFAULT_POWER_BS_LOW_MW,
                    DEFAULT_POWER_BS_INTERCEPT, DEFAULT_POWER_BS_SLOPE,
                    PD_CHANNELS, PD_CHANS_LIST)
from nidaq  import (open_shutter, close_shutter,
                    channels_photodiodos, RATE_MULTICHANNEL, SAFE_MODE)

SHUTTERS_LASER2 = ["None"] + list(SHUTTERS)


class PowerBSWindow(QWidget):
    """Ventana independiente para calibración y monitoreo de potencia en BS (Trace on BS)."""
    powerBsActiveSignal = pyqtSignal(bool)
    calibrationBSSignal = pyqtSignal(float, float)
    saveBsSignal        = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Calibración & Power in BS — PyPrinting")
        self.resize(580, 520)

        self.mean_BS = 0.0
        self._setup_ui()

    def _setup_ui(self):
        vlo = QVBoxLayout(self)

        # ── Controles de Calibración BS ───────────────────────────────────────
        cal_box = QWidget()
        lo = QGridLayout(cal_box)

        self.High_mW = QLineEdit(str(DEFAULT_POWER_BS_HIGH_MW))
        self.Low_mW  = QLineEdit(str(DEFAULT_POWER_BS_LOW_MW))
        self.High_BS = QLabel("NaN")
        self.Low_BS  = QLabel("NaN")

        self.High_Button = QPushButton("Set High")
        self.High_Button.clicked.connect(lambda: self.High_BS.setText(f"{self.mean_BS:.3f}"))
        self.Low_Button  = QPushButton("Set Low")
        self.Low_Button.clicked.connect(lambda: self.Low_BS.setText(f"{self.mean_BS:.3f}"))

        self.calibration_Button = QPushButton("Set Calibration")
        self.calibration_Button.clicked.connect(self._set_calibration)

        self.intercept_Edit = QLineEdit(str(int(DEFAULT_POWER_BS_INTERCEPT) if DEFAULT_POWER_BS_INTERCEPT.is_integer() else DEFAULT_POWER_BS_INTERCEPT))
        self.slope_Edit     = QLineEdit(str(int(DEFAULT_POWER_BS_SLOPE) if DEFAULT_POWER_BS_SLOPE.is_integer() else DEFAULT_POWER_BS_SLOPE))
        self.power_mean_BS  = QLabel("0.00 mW")
        self.power_mean_BS.setStyleSheet("QLabel { color: #e5534b; font-size: 14pt; font-weight: bold; }")

        self.btn_power_bs = QPushButton("⚡ Active Power BS Measurement")
        self.btn_power_bs.setCheckable(True)
        self.btn_power_bs.setChecked(False)
        self.btn_power_bs.setStyleSheet("QPushButton:checked { background-color: #3ecf8e; color: #111; font-weight: bold; }")
        self.btn_power_bs.toggled.connect(lambda chk: self.powerBsActiveSignal.emit(chk))

        self.save_bs_button = QPushButton("💾 Save Trace BS")
        self.save_bs_button.setStyleSheet("QPushButton { background-color: #d4ac0d; color: #111; font-weight: bold; }")
        self.save_bs_button.clicked.connect(lambda: self.saveBsSignal.emit())

        lo.addWidget(self.btn_power_bs,        0, 0, 1, 3)
        lo.addWidget(self.save_bs_button,     0, 3, 1, 1)
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

        # ── Gráfico "Trace on BS" ─────────────────────────────────────────────
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
        if timeaxis is not None and bs_data is not None and len(timeaxis) > 0 and len(bs_data) == len(timeaxis):
            self.curve_BS.setData(np.asarray(timeaxis, dtype=np.float64), np.asarray(bs_data, dtype=np.float64))
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
    saveBsSignal         = pyqtSignal()
    bsOnlyActiveSignal   = pyqtSignal(bool)
    parametersSignal     = pyqtSignal(list)           # [after, before]
    calibrationBS_Signal = pyqtSignal(float, float)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mean_BS = 0.0
        self.powerBSWindow = PowerBSWindow()
        self.powerBSWindow.powerBsActiveSignal.connect(lambda act: self.bsOnlyActiveSignal.emit(act))
        self.powerBSWindow.saveBsSignal.connect(lambda: self.saveBsSignal.emit())
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

    def _on_laser_changed(self):
        l1_name = self.trace_laser1.currentText()
        l2_name = self.trace_laser2.currentText()
        self.pL1.setTitle(f"Trace {l1_name}")
        self.pL2.setTitle(f"Trace {l2_name}")
        self._color_menu1()
        self._color_menu2()

    def _color_menu1(self):
        color_map = {"532": "color: green;", "637": "color: red;", "592": "color: #d4ac0d; font-weight: bold;"}
        txt = self.trace_laser1.currentText()
        c = next((v for k, v in color_map.items() if k in txt), "color: white;")
        self.trace_laser1.setStyleSheet(f"QComboBox {{ {c} }}")

    def _color_menu2(self):
        color_map = {"532": "color: green;", "637": "color: red;", "592": "color: #d4ac0d; font-weight: bold;"}
        txt = self.trace_laser2.currentText()
        c = next((v for k, v in color_map.items() if k in txt), "color: white;")
        self.trace_laser2.setStyleSheet(f"QComboBox {{ {c} }}")

    # ── GUI ───────────────────────────────────────────────────────────────────

    def _setup_gui(self):
        sc_f1 = QShortcut(QKeySequence("F1"), self)
        sc_f1.activated.connect(lambda: self.traceButton.click())
        sc_f2 = QShortcut(QKeySequence("F2"), self)
        sc_f2.activated.connect(self._get_stop)

        # Selección de Lásers Simultáneos (Ambos desplegables contienen la lista completa de SHUTTERS)
        self.trace_laser1 = QComboBox(); self.trace_laser1.addItems(SHUTTERS); self.trace_laser1.setFixedWidth(120)
        self.trace_laser2 = QComboBox(); self.trace_laser2.addItems(SHUTTERS); self.trace_laser2.setFixedWidth(120)
        if len(SHUTTERS) > 1:
            self.trace_laser2.setCurrentIndex(1) # Default 637 nm

        self.trace_laser1.currentIndexChanged.connect(self._on_laser_changed)
        self.trace_laser2.currentIndexChanged.connect(self._on_laser_changed)

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

        # ── Área de Trazas Dobles en Vivo (Láser 1 y Láser 2 con Títulos Dinámicos) ──
        self.traceWidget = pg.GraphicsLayoutWidget()
        self.pL1  = self.traceWidget.addPlot(row=0, col=0, title=f"Trace {self.trace_laser1.currentText()}")
        self.pL2  = self.traceWidget.addPlot(row=0, col=1, title=f"Trace {self.trace_laser2.currentText()}")

        for p in (self.pL1, self.pL2):
            p.showGrid(x=True, y=True)
            p.setLabel("left", "Fotodiodo (V)")
            p.setLabel("bottom", "Tiempo (s)")

        self.curve_L1 = self.pL1.plot(pen=pg.mkPen("#3ecf8e", width=1.5))
        self.curve_L2 = self.pL2.plot(pen=pg.mkPen("#e5534b", width=1.5))

        self._on_laser_changed()

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
        if not data or len(data) < 8:
            return
        n, timeaxis, intensity_l1, intensity_l2, med2, med, intensity_BS, mean_BS = data
        if timeaxis is None or len(timeaxis) == 0:
            return

        SHOW = 1000
        sl  = slice(max(0, n - SHOW), n)
        t   = np.asarray(timeaxis[sl] if n >= SHOW else timeaxis, dtype=np.float64)
        i1  = np.asarray(intensity_l1[sl] if n >= SHOW else intensity_l1, dtype=np.float64)
        i2  = np.asarray(intensity_l2[sl] if n >= SHOW else intensity_l2, dtype=np.float64)
        bs  = np.asarray(intensity_BS[sl] if n >= SHOW else intensity_BS, dtype=np.float64)

        if len(t) > 0 and len(i1) == len(t):
            self.curve_L1.setData(t, i1)
        if len(t) > 0 and len(i2) == len(t):
            self.curve_L2.setData(t, i2)

        self.PointLabel.setText(f"<b>{med2:.3f} | {med:.3f}</b>")

        self.mean_BS = round(mean_BS, 3)
        if self.powerBSWindow.isVisible():
            self.powerBSWindow.update_bs_data(t, bs, mean_BS)

    def make_connection(self, backend: Backend):
        backend.make_connection(self)


# ══════════════════════════════════════════════════════════════════════════════
class Backend(QObject):

    dataSignal          = pyqtSignal(list)
    data_printingSignal = pyqtSignal(list)  # incluye mode en data[-1]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.file_path = str(DEFAULT_DATA_PATH)
        self.pointtimer = None
        self.bs_timer   = None
        self._init_params()
        self.steps_after  = DEFAULT_TRACE_STEPS_AFTER
        self.steps_before = DEFAULT_TRACE_STEPS_BEFORE
        self.laser1       = SHUTTERS[0]
        self.laser2       = SHUTTERS[1] if len(SHUTTERS) > 1 else SHUTTERS[0]
        self.mode_printing = "none"
        self.bs_only_mode = False

    def make_connection(self, frontend: QObject):
        try:
            frontend.startSignal.disconnect(self.play_pause)
            frontend.stopSignal.disconnect(self.stop)
            self.dataSignal.disconnect(frontend.get_data)
        except Exception:
            pass
        frontend.startSignal.connect(self.play_pause)
        frontend.stopSignal.connect(self.stop)
        frontend.saveSignal.connect(lambda: self.save_trace())
        frontend.saveBsSignal.connect(lambda: self.save_bs_trace())
        frontend.bsOnlyActiveSignal.connect(self.set_bs_only_active)
        frontend.calibrationBS_Signal.connect(self.set_calibration_bs)
        if hasattr(frontend, 'parametersSignal'):
            frontend.parametersSignal.connect(self.parameters)
        self.dataSignal.connect(frontend.get_data)

    def _init_params(self):
        self.rate = RATE_MULTICHANNEL / 100
        self.N    = 10

    @pyqtSlot(bool)
    def set_bs_only_active(self, active: bool):
        self.bs_only_mode = active
        if active:
            if self.pointtimer is None or not self.pointtimer.isActive():
                if self.bs_timer is None:
                    self.bs_timer = QTimer(self)
                    self.bs_timer.timeout.connect(self._bs_only_update)
                self._n_bs = 0
                self.timer_bs_inicio = time.time()
                self.bs_timeaxis = np.array([])
                self.bs_intensity = np.array([])
                self.bs_timer.start(10)
        else:
            if self.bs_timer and self.bs_timer.isActive():
                self.bs_timer.stop()

    def _bs_only_update(self):
        self._n_bs += 1
        if SAFE_MODE:
            val_bs = 0.5 + 0.1 * np.cos(self._n_bs * 0.1) + np.random.normal(0, 0.02)
        else:
            try:
                task = channels_photodiodos(self.rate, self.N)
                lectura_total = task.read(self.N)
                task.wait_until_done()
                task.close()
                ch_bs = PD_CHANNELS.get("BS", 6)
                ch_bs_idx = PD_CHANS_LIST.index(ch_bs) if ch_bs in PD_CHANS_LIST else (len(PD_CHANS_LIST) - 1)
                val_bs = float(np.mean(lectura_total[ch_bs_idx]))
            except Exception as e:
                print(f"[PowerBS Error] {e}")
                val_bs = 0.0

        t_now = round(time.time() - self.timer_bs_inicio, 4)
        self.bs_timeaxis  = np.append(self.bs_timeaxis,  t_now)
        self.bs_intensity = np.append(self.bs_intensity, val_bs)
        mean_BS = float(np.mean(self.bs_intensity[-self.N:])) if len(self.bs_intensity) >= self.N else val_bs

        # Emitir estructura compatible con frontend get_data
        data = [self._n_bs, self.bs_timeaxis, np.zeros_like(self.bs_intensity), np.zeros_like(self.bs_intensity),
                0.0, 0.0, self.bs_intensity, mean_BS]
        self.dataSignal.emit(data)

    # ── Control de la traza principal ─────────────────────────────────────────

    @pyqtSlot(bool, int, int)
    def play_pause(self, play: bool, color_laser1: int = 0, color_laser2: int = 0):
        if 0 <= color_laser1 < len(SHUTTERS):
            self.laser1 = SHUTTERS[color_laser1]
        else:
            self.laser1 = SHUTTERS[0]

        if 0 <= color_laser2 < len(SHUTTERS):
            self.laser2 = SHUTTERS[color_laser2]
        else:
            self.laser2 = SHUTTERS[1] if len(SHUTTERS) > 1 else SHUTTERS[0]

        self.mode_printing = "none"
        if play:
            if self.bs_timer and self.bs_timer.isActive():
                self.bs_timer.stop()
            self._start()
        else:
            self._stop_and_save()

    @pyqtSlot()
    def stop(self):
        self._stop_and_save()

    def _start(self):
        if self.pointtimer is None:
            self.pointtimer = QTimer(self)
            self.pointtimer.timeout.connect(self._trace_update)
        if hasattr(self, 'laser1') and self.laser1 != "None":
            open_shutter(self.laser1)
        if hasattr(self, 'laser2') and self.laser2 != "None":
            open_shutter(self.laser2)

        self._n           = 0
        self.timer_inicio = time.time()
        self.timeaxis     = np.array([])
        self.intensity_l1 = np.array([])
        self.intensity_l2 = np.array([])
        self.intensity_BS = np.array([])
        self.pointtimer.start(10)

    def _stop_and_save(self):
        if self.pointtimer and self.pointtimer.isActive():
            self.pointtimer.stop()
        if hasattr(self, 'laser1') and self.laser1 != "None":
            close_shutter(self.laser1)
        if hasattr(self, 'laser2') and self.laser2 != "None":
            close_shutter(self.laser2)

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
                self.laser1 = SHUTTERS[laser_input]
        elif isinstance(laser_input, str):
            self.laser1 = laser_input
        self.mode_printing = mode_printing
        self._start()

    @pyqtSlot(float, float)
    def set_calibration_bs(self, slope: float, intercept: float):
        pass

    # ── Adquisición periódico ─────────────────────────────────────────────────

    def _trace_update(self):
        self._n += 1

        if SAFE_MODE:
            val_l1 = (1.0 + 0.3 * np.sin(self._n * 0.1) + np.random.normal(0, 0.05)) if getattr(self, 'laser1', 'None') != "None" else 0.0
            val_l2 = (0.8 + 0.2 * np.sin(self._n * 0.15) + np.random.normal(0, 0.04)) if getattr(self, 'laser2', 'None') != "None" else 0.0
            val_bs = (0.5 + 0.1 * np.cos(self._n * 0.1) + np.random.normal(0, 0.02))
        else:
            try:
                task = channels_photodiodos(self.rate, self.N)
                lectura_total = task.read(self.N)
                task.wait_until_done()
                task.close()

                active_l1_name = getattr(self, 'laser1', SHUTTERS[0])
                active_l2_name = getattr(self, 'laser2', SHUTTERS[1] if len(SHUTTERS) > 1 else SHUTTERS[0])

                if isinstance(active_l1_name, int):
                    active_l1_name = SHUTTERS[active_l1_name] if 0 <= active_l1_name < len(SHUTTERS) else SHUTTERS[0]
                if isinstance(active_l2_name, int):
                    active_l2_name = SHUTTERS[active_l2_name] if 0 <= active_l2_name < len(SHUTTERS) else SHUTTERS[0]

                ch_l1 = PD_CHANNELS.get(active_l1_name, 0)
                ch_l2 = PD_CHANNELS.get(active_l2_name, 1)
                ch_bs = PD_CHANNELS.get("BS", 6)

                ch_l1_idx = PD_CHANS_LIST.index(ch_l1) if ch_l1 in PD_CHANS_LIST else 0
                ch_l2_idx = PD_CHANS_LIST.index(ch_l2) if ch_l2 in PD_CHANS_LIST else 1
                ch_bs_idx = PD_CHANS_LIST.index(ch_bs) if ch_bs in PD_CHANS_LIST else (len(PD_CHANS_LIST) - 1)

                val_l1 = float(np.mean(lectura_total[ch_l1_idx]))
                val_l2 = float(np.mean(lectura_total[ch_l2_idx]))
                val_bs = float(np.mean(lectura_total[ch_bs_idx]))
            except Exception as e:
                print(f"[Trace Error] Error al leer NI-DAQ: {e}")
                val_l1, val_l2, val_bs = 0.0, 0.0, 0.0

        if not hasattr(self, 'timer_inicio') or self.timer_inicio == 0.0:
            self.timer_inicio = time.time()

        t_now = round(time.time() - self.timer_inicio, 4)
        self.timeaxis     = np.append(self.timeaxis,     t_now)
        self.intensity_l1 = np.append(self.intensity_l1, val_l1)
        self.intensity_l2 = np.append(self.intensity_l2, val_l2)
        self.intensity_BS = np.append(self.intensity_BS, val_bs)

        M  = getattr(self, 'steps_after', 10)
        M2 = getattr(self, 'steps_before', 10)
        n  = len(self.intensity_l1)

        if n < M:
            I_new = float(np.mean(self.intensity_l1[:n])) if n > 0 else val_l1
            if n < M2:
                I_old = float(np.mean(self.intensity_l1[:n])) if n > 0 else 1.0
            else:
                I_old = float(np.mean(self.intensity_l1[:n - M2])) if (n - M2) > 0 else float(self.intensity_l1[0])
        else:
            I_new = float(np.mean(self.intensity_l1[n - M:n]))
            I_old = float(np.mean(self.intensity_l1[max(0, n - M - M2):n - M]))

        med2 = I_old
        med  = I_new
        mean_BS = float(np.mean(self.intensity_BS[-self.N:])) if len(self.intensity_BS) >= self.N else val_bs

        # Estructura unificada: [n, timeaxis, intensity_l1, intensity_l2, I_old, I_new, intensity_BS, mean_BS]
        data = [self._n, self.timeaxis, self.intensity_l1, self.intensity_l2, I_old, I_new, self.intensity_BS, mean_BS]
        self.dataSignal.emit(data)

        if self.mode_printing != "none":
            data_p = list(data) + [self.mode_printing]
            self.data_printingSignal.emit(data_p)

    def save_trace(self, filename: str = "trace.txt"):
        if len(self.timeaxis) == 0: return
        t_str = time.strftime("%Y%m%d_%H%M%S")
        path  = os.path.join(self.file_path, f"{t_str}_{filename}")
        data  = np.column_stack((self.timeaxis, self.intensity_l1, self.intensity_l2, self.intensity_BS))
        header = f"Trace Data - PyPrinting\nLáser 1: {getattr(self, 'laser1', 'None')}\nLáser 2: {getattr(self, 'laser2', 'None')}\nTime(s)\tIntensity_L1(V)\tIntensity_L2(V)\tIntensity_BS(V)"
        np.savetxt(path, data, fmt="%.6f", delimiter="\t", header=header)
        print(f"[Trace] Guardado en: {path}")

    def save_bs_trace(self, filename: str = "power_bs_trace.txt"):
        t_axis = getattr(self, "bs_timeaxis", self.timeaxis)
        i_bs   = getattr(self, "bs_intensity", self.intensity_BS)
        if len(t_axis) == 0: return
        t_str = time.strftime("%Y%m%d_%H%M%S")
        path  = os.path.join(self.file_path, f"{t_str}_{filename}")
        data  = np.column_stack((t_axis, i_bs))
        header = f"Power BS Trace Data - PyPrinting\nTime(s)\tIntensity_BS(V)"
        np.savetxt(path, data, fmt="%.6f", delimiter="\t", header=header)
        print(f"[PowerBS] Traza de potencia guardada en: {path}")
