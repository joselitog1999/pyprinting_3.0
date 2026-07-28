# -*- coding: utf-8 -*-
"""
trace.py — Traza temporal de fotodiodo (NI-DAQ)
PyPrinting — UNSAM Nanofotónica  —  PyQt6

Funcionalidades (idénticas al original Trace_pp.py):
  - Plot principal (fotodiodo) + plot BS en tiempo real
  - Selección de láser por color
  - Steps after/before umbral configurables
  - Save trace automático al detener
  - Ventana de calibración BS (View Power BS) con slope/intercept
  - Señal data_printingSignal unificada con mode como campo del dict
  - Atajos F1 (play) y F2 (stop)
"""
from __future__ import annotations
import os
import time
import numpy as np

import pyqtgraph as pg
from PyQt6.QtCore    import Qt, QObject, QThread, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (QApplication, QFrame, QWidget, QGridLayout,
                              QHBoxLayout, QLabel, QLineEdit, QComboBox,
                              QPushButton)
from PyQt6.QtGui     import QShortcut, QKeySequence
from pyqtgraph.dockarea import DockArea, Dock

from config  import SHUTTERS, DEFAULT_DATA_PATH
from nidaq   import (open_shutter, close_shutter, channels_photodiodos,
                     PD_CHANNELS, PD_CHANS_LIST, RATE_MULTICHANNEL)


# ══════════════════════════════════════════════════════════════════════════════
class Frontend(QFrame):

    traceSignal          = pyqtSignal(bool, int)    # play/stop, laser_index
    stopSignal           = pyqtSignal()
    playSignal           = pyqtSignal()
    saveSignal           = pyqtSignal()
    parametersSignal     = pyqtSignal(list)         # [after, before]
    calibrationBS_Signal = pyqtSignal(float, float) # slope, intercept

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mean_BS = 0.0
        self._setup_gui()
        self._calibration_widget()

    # ── Acciones ──────────────────────────────────────────────────────────────

    def _get_trace(self):
        self.traceSignal.emit(
            self.traceButton.isChecked(),
            self.trace_laser.currentIndex(),
        )

    def _get_play(self):   self.playSignal.emit()
    def _get_stop(self):   self.stopSignal.emit()

    def _get_save(self):
        self.saveSignal.emit()

    def _parameters_trace(self):
        try:
            after  = int(self.steps_after_Edit.text())
            before = int(self.steps_before_Edit.text())
            self.parametersSignal.emit([after, before])
        except ValueError:
            pass

    def _get_power_bs(self):
        self.calWidget.show()

    # ── GUI principal ─────────────────────────────────────────────────────────

    def _setup_gui(self):
        sc_f1 = QShortcut(QKeySequence("F1"), self)
        sc_f1.activated.connect(self._get_play)
        sc_f2 = QShortcut(QKeySequence("F2"), self)
        sc_f2.activated.connect(self._get_stop)

        self.trace_laser = QComboBox()
        self.trace_laser.addItems(SHUTTERS)
        self.trace_laser.setFixedWidth(100)
        self.trace_laser.currentIndexChanged.connect(self._color_menu)
        self._color_menu()

        self.traceButton = QPushButton("► Play / ■ Stop  (F1/F2)")
        self.traceButton.setCheckable(True)
        self.traceButton.clicked.connect(self._get_trace)

        self.saveButton = QPushButton("Save trace")
        self.saveButton.clicked.connect(self._get_save)
        self.saveButton.setStyleSheet("QPushButton { background-color: rgb(200,200,10); }")

        self.setPowerBSButton = QPushButton("View Power BS")
        self.setPowerBSButton.clicked.connect(self._get_power_bs)

        self.steps_after_Edit  = QLineEdit("10")
        self.steps_before_Edit = QLineEdit("10")
        self.steps_after_Edit.textChanged.connect(self._parameters_trace)
        self.steps_before_Edit.textChanged.connect(self._parameters_trace)

        self.PointLabel = QLabel("<b>0.00 | 0.00</b>")
        self.PointLabel.setTextFormat(Qt.TextFormat.RichText)

        paramWidget = QWidget()
        pg_lo = QGridLayout(paramWidget)
        pg_lo.addWidget(self.trace_laser,          0, 0)
        pg_lo.addWidget(self.traceButton,          0, 1)
        pg_lo.addWidget(QLabel("Steps before:"),   0, 2)
        pg_lo.addWidget(self.steps_before_Edit,    0, 3)
        pg_lo.addWidget(QLabel("Steps after:"),    0, 4)
        pg_lo.addWidget(self.steps_after_Edit,     0, 5)
        pg_lo.addWidget(self.PointLabel,           0, 6)
        pg_lo.addWidget(self.saveButton,           0, 8)
        pg_lo.addWidget(self.setPowerBSButton,     0, 9)

        self.traceWidget = pg.GraphicsLayoutWidget()
        self.p6  = self.traceWidget.addPlot(row=0, col=0, title="Trace")
        self.pBS = self.traceWidget.addPlot(row=0, col=1, title="Trace on BS")
        for p, ylabel in [(self.p6, "Photodiode (V)"), (self.pBS, "Photodiode BS (V)")]:
            p.showGrid(x=True, y=True)
            p.setLabel("left",   ylabel)
            p.setLabel("bottom", "Time (s)")
        self.curve    = self.p6.plot(pen=pg.mkPen("y", width=1))
        self.curve_BS = self.pBS.plot(pen=pg.mkPen("r", width=1))

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

    def _color_menu(self):
        colors = ["color: green;", "color: red;", "color: #d4ac0d; font-weight: bold;", "color: blue;", "color: darkred;"]
        idx = self.trace_laser.currentIndex()
        if 0 <= idx < len(colors):
            self.trace_laser.setStyleSheet(f"QComboBox {{ {colors[idx]} }}")

    # ── Widget de calibración BS ───────────────────────────────────────────────

    def _calibration_widget(self):
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
        self.power_mean_BS  = QLabel("")
        self.power_mean_BS.setStyleSheet("QLabel { color: red; font-size: 14pt; }")

        self.calWidget = QWidget()
        lo = QGridLayout(self.calWidget)
        lo.addWidget(QLabel("Power BFP (mW):"), 0, 1)
        lo.addWidget(QLabel("Photodiode (V):"), 0, 2)
        lo.addWidget(QLabel("High:"),  1, 0); lo.addWidget(self.High_mW, 1, 1)
        lo.addWidget(QLabel("Low:"),   2, 0); lo.addWidget(self.Low_mW,  2, 1)
        lo.addWidget(self.High_BS,     1, 2); lo.addWidget(self.High_Button, 1, 3)
        lo.addWidget(self.Low_BS,      2, 2); lo.addWidget(self.Low_Button,  2, 3)
        lo.addWidget(self.calibration_Button, 3, 0)
        lo.addWidget(QLabel("Intercept (mW):"), 4, 0)
        lo.addWidget(self.intercept_Edit, 4, 1)
        lo.addWidget(QLabel("Slope (mW/V):"),   5, 0)
        lo.addWidget(self.slope_Edit,     5, 1)
        lo.addWidget(QLabel("Power mean on BS (mW):"), 6, 0)
        lo.addWidget(self.power_mean_BS, 7, 0)
        self.calWidget.setWindowTitle("Calibración BS")

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
            self.calibrationBS_Signal.emit(slope, intercept)
        except (ValueError, ZeroDivisionError) as e:
            print(f"[Trace] Error en calibración: {e}")

    # ── Actualización de datos ────────────────────────────────────────────────

    @pyqtSlot(list)
    def get_data(self, data: list):
        n, timeaxis, intensity, med2, med, intensity_BS, mean_BS = data
        SHOW = 1000
        sl = slice(max(0, n - SHOW), n)
        t  = timeaxis[sl] if n >= SHOW else timeaxis
        i  = intensity[sl] if n >= SHOW else intensity
        bs = intensity_BS[sl] if n >= SHOW else intensity_BS

        self.curve.setData(t, i, pen=pg.mkPen("y", width=1))
        self.curve_BS.setData(t, bs, pen=pg.mkPen("r", width=1))
        self.PointLabel.setText(f"<b>{med2:.3f} | {med:.3f}</b>")

        self.mean_BS = round(mean_BS, 3)
        try:
            slope     = float(self.slope_Edit.text())
            intercept = float(self.intercept_Edit.text())
            power     = round(slope * self.mean_BS + intercept, 3)
            self.power_mean_BS.setText(str(power))
        except ValueError:
            pass

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

    @pyqtSlot(bool, int)
    def play_pause(self, play: bool, color_laser: int):
        self.laser = SHUTTERS[color_laser]
        self.mode_printing = "none"
        if play:
            self._start()
        else:
            self._stop_and_save()

    @pyqtSlot()
    def start_trace(self):
        open_shutter(self.laser)
        time.sleep(0.01)
        self._configure(self.laser, self.mode_printing)

    @pyqtSlot()
    def stop_trace(self):
        self._stop_and_save()

    def _start(self):
        open_shutter(self.laser)
        time.sleep(0.01)
        self._configure(self.laser, self.mode_printing)

    def _stop_and_save(self):
        self.timer_end = time.time()
        self.stop()
        close_shutter(self.laser)
        self.timer_real = round(self.timer_end - self.timer_inicio, 2)
        print(f"[Trace] Tiempo real: {self.timer_real}s  "
              f"no real: {round(self.timeaxis[-1], 2) if self.timeaxis else 0}s")
        self.save_trace()

    @pyqtSlot()
    def stop(self):
        self.pointtimer.stop()

    @pyqtSlot(str, str)
    def trace_configuration(self, laser: str, mode_printing: str):
        self._configure(laser, mode_printing)

    def _configure(self, laser: str, mode_printing: str):
        self.laser         = laser
        self.mode_printing = mode_printing
        self.ptr           = 0
        self.step_time     = 0.0
        self.timeaxis      = []
        self.data1         = []
        self.data_BS       = []
        self.timer_inicio  = time.time()
        self.pointtimer.start(0)

    # ── Loop de traza ─────────────────────────────────────────────────────────

    def _trace_update(self):
        tic  = time.time()
        task = channels_photodiodos(self.rate, self.N)
        raw  = task.read(self.N)
        task.wait_until_done()
        task.close()

        pts    = raw[PD_CHANS_LIST.index(PD_CHANNELS[self.laser])]
        pts_BS = raw[PD_CHANS_LIST.index(PD_CHANNELS["BS"])]

        self.data1.append(np.mean(pts))
        self.data_BS.append(np.mean(pts_BS))

        M  = self.steps_after
        M2 = self.steps_before
        p  = self.ptr

        if p < M:
            med  = np.mean(self.data1[:p]) if p else 0.0
            med2 = np.mean(self.data1[:p]) if p < M2 else np.mean(self.data1[:max(0, p-M2)])
            bs   = np.mean(self.data_BS[:p]) if p else 0.0
        else:
            med  = np.mean(self.data1[p-M:p])
            med2 = np.mean(self.data1[max(0, p-M-M2):p-M])
            bs   = np.mean(self.data_BS[p-M:p])

        self.step_time += time.time() - tic
        self.timeaxis.append(self.step_time)
        self.ptr += 1

        data = [self.ptr, self.timeaxis, self.data1,
                med2, med, self.data_BS, bs]
        self.dataSignal.emit(data)

        if self.mode_printing in ("printing", "dimers"):
            self.data_printingSignal.emit(data + [self.mode_printing])

    # ── Parámetros y guardado ─────────────────────────────────────────────────

    @pyqtSlot(list)
    def get_trace_parameters(self, steps: list):
        self.steps_after  = steps[0]
        self.steps_before = steps[1]

    @pyqtSlot(str)
    def direction(self, file_name: str):
        self.file_path = file_name

    @pyqtSlot()
    def save_trace(self):
        timestr = time.strftime("%Y%m%d-%H%M%S")
        os.makedirs(self.file_path, exist_ok=True)
        name    = os.path.join(self.file_path, f"timetrace-{timestr}.txt")
        n       = self.ptr
        t_real  = list(np.linspace(0.01, self.timer_real, n))
        np.savetxt(name, np.transpose([t_real, self.data1[:n], self.data_BS[:n]]),
                   fmt="%.3e")
        print(f"[Trace] Guardado: {name}")

    @pyqtSlot(float, float)
    def save_calibration_BS(self, slope: float, intercept: float):
        timestr = time.strftime("%Y%m%d-%H%M%S")
        os.makedirs(self.file_path, exist_ok=True)
        name    = os.path.join(self.file_path, f"Calibration_Power-{timestr}.txt")
        np.savetxt(name, [[self.laser, str(slope), str(intercept)]],
                   fmt="%s", header="Laser, Slope (mW/V), Intercept (mW)")
        print(f"[Trace] Calibración guardada: {name}")

    def make_connection(self, frontend: Frontend):
        frontend.traceSignal.connect(self.play_pause)
        frontend.stopSignal.connect(self.stop_trace)
        frontend.playSignal.connect(self.start_trace)
        frontend.saveSignal.connect(self.save_trace)
        frontend.parametersSignal.connect(self.get_trace_parameters)
        frontend.calibrationBS_Signal.connect(self.save_calibration_BS)


# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    gui    = Frontend()
    worker = Backend()
    worker.make_connection(gui)
    gui.make_connection(worker)
    thread = QThread()
    worker.moveToThread(thread)
    thread.start()
    gui.show()
    sys.exit(app.exec())
