# -*- coding: utf-8 -*-
"""
focus.py — Control de enfoque Z (platina PI + fotodiodo NI-DAQ)
PyPrinting — UNSAM Nanofotónica  —  PyQt6

Funcionalidades (idénticas al original Focus_pp.py):
  - Go to maximum  (F8): barre Z, encuentra el pico de intensidad
  - Lock focus     (F9): guarda el perfil de intensidad del Z actual
  - Autocorrelation x2 (F10): correlaciona con el perfil lockeado y va al Z óptimo
  - Señales de plot abriendo ventanas pyqtgraph flotantes (igual que el original)
  - autofinishSignal(mode) unificada — ya no hay dos señales paralelas

Correcciones respecto al original:
  - isChecked() con paréntesis
  - pi importado desde config (singleton)
  - Señales autofinishSignal_printing y autofinishSignal_dimers unificadas en
    autofinishSignal(str) donde el str es el mode_printing
"""
from __future__ import annotations
import time
import numpy as np
from scipy import signal as scipy_signal

import pyqtgraph as pg
from PyQt6.QtCore    import Qt, QObject, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (QApplication, QFrame, QWidget, QGridLayout,
                              QComboBox, QPushButton)
from PyQt6.QtGui     import QShortcut, QKeySequence

from config  import pi, SHUTTERS
from nidaq   import (open_shutter, close_shutter, channels_photodiodos,
                     channels_triggers, RATE_MULTICHANNEL, PD_CHANNELS,
                     PD_CHANS_LIST)
from config  import PI_SERIAL


# ══════════════════════════════════════════════════════════════════════════════
class Frontend(QFrame):

    focus_gotomax_signal  = pyqtSignal(int)           # color_laser index
    focus_lock_signal     = pyqtSignal(bool, int)     # lock_bool, color_laser
    focus_auto_signal     = pyqtSignal()
    focus_autox2_signal   = pyqtSignal(str)           # mode_printing

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._setup_gui()

    def _setup_gui(self):
        QShortcut(QKeySequence("F8"),  self, self._go_max)
        QShortcut(QKeySequence("F9"),  self, self._lock)
        QShortcut(QKeySequence("F10"), self, self._autocorr_x2)

        self.focus_laser = QComboBox()
        self.focus_laser.addItems(SHUTTERS)
        self.focus_laser.setFixedWidth(100)
        self.focus_laser.currentIndexChanged.connect(self._color_menu)
        self._color_menu()

        self.focus_gotomax_button    = QPushButton("Go to maximum  (F8)")
        self.focus_lock_button       = QPushButton("Lock Focus  (F9)")
        self.focus_lock_button.setCheckable(True)
        self.focus_lock_button.setStyleSheet(
            "QPushButton { background-color: orange; }"
            "QPushButton:checked { background-color: #3a8a3a; color: white; }")
        self.focus_autocorrx2_button = QPushButton("Autocorrelation ×2  (F10)")
        self.show_autocorr_btn       = QPushButton("📊 Plot Autocorr: ON")
        self.show_autocorr_btn.setCheckable(True)
        self.show_autocorr_btn.setChecked(True)
        self.show_autocorr_btn.setToolTip("Activa o desactiva la visualización de la ventana gráfica emergente de Autocorrelación.")
        self.show_autocorr_btn.setStyleSheet(
            "QPushButton { background-color: #2b5b84; color: white; font-weight: bold; }"
            "QPushButton:unchecked { background-color: #444; color: #aaa; font-weight: normal; }"
        )
        self.show_autocorr_btn.toggled.connect(
            lambda chk: self.show_autocorr_btn.setText("📊 Plot Autocorr: ON" if chk else "🚫 Plot Autocorr: OFF")
        )

        self.focus_gotomax_button.clicked.connect(self._go_max)
        self.focus_lock_button.clicked.connect(self._lock)
        self.focus_autocorrx2_button.clicked.connect(self._autocorr_x2)

        lo = QGridLayout(self)
        lo.addWidget(self.focus_laser,             0, 0)
        lo.addWidget(self.focus_gotomax_button,    1, 0)
        lo.addWidget(self.focus_lock_button,       2, 0)
        lo.addWidget(self.focus_autocorrx2_button, 3, 0)
        lo.addWidget(self.show_autocorr_btn,       4, 0)

    def _color_menu(self):
        colors = ["color: green;", "color: red;", "color: #d4ac0d; font-weight: bold;", "color: #ad1457; font-weight: bold;", "color: blue;"]
        idx = self.focus_laser.currentIndex()
        if 0 <= idx < len(colors):
            self.focus_laser.setStyleSheet(f"QComboBox {{ {colors[idx]} }}")

    def _go_max(self):
        self.focus_gotomax_signal.emit(self.focus_laser.currentIndex())

    def _lock(self):
        self.focus_lock_signal.emit(
            self.focus_lock_button.isChecked(),
            self.focus_laser.currentIndex(),
        )

    def _autocorr_x2(self):
        self.focus_autox2_signal.emit("none")

    # ── Slots de plot (ventanas flotantes, igual que el original) ─────────────

    @pyqtSlot(np.ndarray, np.ndarray, np.ndarray, np.ndarray,
              np.ndarray, np.ndarray, np.ndarray, np.ndarray)
    def plot_focus(self, z_gone, prof_gone, prof_gone_f, prof_gone_max,
                   z_back, prof_back, prof_back_f, prof_back_max):
        win = pg.GraphicsLayoutWidget(title="Go to maximum")
        win.show()
        p = win.addPlot(title="Go to maximum")
        p.showGrid(x=True, y=True)
        p.setLabel("left",   "Photodiode (V)")
        p.setLabel("bottom", "z position (µm)")
        p.plot(z_gone, prof_gone,    pen=pg.mkPen("y", width=1))
        p.plot(z_gone, prof_gone_f,  pen=pg.mkPen("g", width=1))
        p.plot(z_gone, prof_gone_max,pen=pg.mkPen("g", width=3))
        p.plot(z_back, prof_back,    pen=pg.mkPen("b", width=1))
        p.plot(z_back, prof_back_f,  pen=pg.mkPen("m", width=1))
        p.plot(z_back, prof_back_max,pen=pg.mkPen("m", width=3))
        self._plot_win_focus = win   # evita que el GC lo cierre

    @pyqtSlot(np.ndarray, np.ndarray)
    def plot_lock(self, profile, profile_filter):
        win = pg.GraphicsLayoutWidget(title="Lock focus")
        win.show()
        p = win.addPlot(title="Lock focus")
        p.showGrid(x=True, y=True)
        p.setLabel("left", "Photodiode (V)")
        p.plot(profile,        pen=pg.mkPen("y", width=1))
        p.plot(profile_filter, pen=pg.mkPen("g", width=1))
        self._plot_win_lock = win

    @pyqtSlot(np.ndarray, np.ndarray, np.ndarray)
    def plot_auto(self, new_f, lock_f, corr):
        if hasattr(self, "show_autocorr_btn") and not self.show_autocorr_btn.isChecked():
            return
        win = pg.GraphicsLayoutWidget(title="Autocorrelation")
        win.show()
        p = win.addPlot(title="Autocorrelation")
        p.showGrid(x=True, y=True)
        p.setLabel("left", "Photodiode (V)")
        mx_prof = max(float(new_f.max()), float(lock_f.max()), 1e-9)
        mx_corr = max(float(corr.max()), 1e-9)
        corr_scaled = (corr / mx_corr) * mx_prof
        p.plot(new_f,       pen=pg.mkPen("r", width=1), name="new profile")
        p.plot(lock_f,      pen=pg.mkPen("g", width=1), name="lock profile")
        p.plot(corr_scaled, pen=pg.mkPen("b", width=1), name="correlation")
        self._plot_win_auto = win

    def make_connection(self, backend: Backend):
        backend.plot_focusSignal.connect(self.plot_focus)
        backend.plot_lockSignal.connect(self.plot_lock)
        backend.plot_autoSignal.connect(self.plot_auto)


# ══════════════════════════════════════════════════════════════════════════════
class Backend(QObject):

    gotomaxdoneSignal = pyqtSignal()
    lockdoneSignal    = pyqtSignal()
    autodoneSignal    = pyqtSignal()
    autofinishSignal  = pyqtSignal(str)   # emite mode_printing — unificada

    plot_focusSignal = pyqtSignal(
        np.ndarray, np.ndarray, np.ndarray, np.ndarray,
        np.ndarray, np.ndarray, np.ndarray, np.ndarray)
    plot_lockSignal  = pyqtSignal(np.ndarray, np.ndarray)
    plot_autoSignal  = pyqtSignal(np.ndarray, np.ndarray, np.ndarray)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        pi.connect()
        self.laser = SHUTTERS[0] if len(SHUTTERS) > 0 else "532"
        self.locked_focus = False
        self._ramp_params()

    # ── Parámetros de rampa (idénticos al original) ───────────────────────────

    def _ramp_params(self):
        self.range       = 6.0
        self.extra       = self.range / 8
        self.range_total = self.range + 2 * self.extra

        self.frequency       = RATE_MULTICHANNEL / 100
        self.frequency_ramp  = self.frequency / 3000
        Nramp                = int(self.frequency / self.frequency_ramp)
        self.Ntot_read       = 2 * Nramp
        self.Npoints         = 1500
        self.Nspeed          = 10
        tau                  = 1 / self.frequency_ramp
        from config import PI_SERVO_TIME
        self.WTRtime         = int(tau / (PI_SERVO_TIME * self.Npoints))
        size_point           = self.range_total / self.Npoints
        self.Nz              = int(self.range / size_point)

    # ── Go to maximum ─────────────────────────────────────────────────────────

    @pyqtSlot(int)
    def focus_go_to_maximum(self, color_laser: int):
        self.laser = SHUTTERS[color_laser]
        pos        = pi.qPOS()
        z_pos      = pos["3"]
        self.zo    = z_pos - self.range_total / 2

        self._move_z(self.zo)
        pi.WOS(3, self.zo)

        flag = True
        while flag:
            open_shutter(self.laser)
            gone, back, flag = self._ramp_lin()
            close_shutter(self.laser)

        f_gone = int(len(gone) / self.Nz)
        gone_m = _average(gone, f_gone)
        gone_f = _filter(gone_m)

        f_back = int(len(back) / self.Nz)
        back_m = _average(back, f_back)
        back_f = _filter(back_m)

        dz     = self.range / self.Nz
        z_gone = np.linspace(z_pos - self.range/2 + dz/2,
                             z_pos + self.range/2 - dz/2, len(gone_m))
        z_back = np.linspace(z_pos + self.range/2 - dz/2,
                             z_pos - self.range/2 + dz/2, len(back_m))

        i_gone = np.argmax(gone_f)
        i_back = np.argmax(back_f)
        gone_max_arr = np.zeros_like(gone_f); gone_max_arr[i_gone] = gone_f[i_gone]
        back_max_arr = np.zeros_like(back_f); back_max_arr[i_back] = back_f[i_back]

        z_max = np.around((z_gone[i_gone] + z_back[i_back]) / 2, 3)
        self._move_z(z_max)
        self.gotomaxdoneSignal.emit()
        self.plot_focusSignal.emit(z_gone, gone_m, gone_f, gone_max_arr,
                                   z_back, back_m, back_f, back_max_arr)

    # ── Lock focus ────────────────────────────────────────────────────────────

    @pyqtSlot(bool, int)
    def focus_lock_lin(self, lock_bool: bool, color_laser: int):
        self.laser = SHUTTERS[color_laser]

        if lock_bool:
            pos    = pi.qPOS()
            z_lock = pos["3"]
            self.zo = z_lock - self.range_total / 2
            self._move_z(self.zo)
            pi.WOS(3, self.zo)

            flag = True
            while flag:
                open_shutter(self.laser)
                gone, _, flag = self._ramp_lin()
                close_shutter(self.laser)

            f_gone = int(len(gone) / self.Nz)
            self.z_profile_gone_lock  = _average(gone, f_gone)
            self.z_profile_lock_filter = _filter(self.z_profile_gone_lock)

            self._move_z(z_lock)
            self.locked_focus = True
            self.lockdoneSignal.emit()
            self.plot_lockSignal.emit(self.z_profile_gone_lock,
                                      self.z_profile_lock_filter)
            print("[Focus] Foco lockeado.")
        else:
            self.locked_focus = False
            print("[Focus] Lock desactivado.")

    # ── Autocorrelation ×2 ────────────────────────────────────────────────────

    @pyqtSlot(str)
    def focus_autocorr_lin_x2(self, mode_printing: str):
        if not self.locked_focus:
            print("[Focus] ⚠️ No había perfil axial bloqueado previo (Lock focus) — Ejecutando auto-lock en Z actual...")
            laser_idx = SHUTTERS.index(self.laser) if hasattr(self, 'laser') and self.laser in SHUTTERS else 0
            self.focus_lock_lin(True, laser_idx)
            if not self.locked_focus:
                print("[Focus] ⚠️ No se pudo realizar auto-lock.")
                self.autofinishSignal.emit(mode_printing)
                return

        open_shutter(self.laser)
        for _ in range(2):
            self._focus_autocorr_lin()
        close_shutter(self.laser)

        self.plot_autoSignal.emit(self.new_profile_filter,
                                  self.z_profile_lock_filter,
                                  self.correlation_filter)
        self.autodoneSignal.emit()
        self.autofinishSignal.emit(mode_printing)

    @pyqtSlot()
    def focus_autocorr_lin(self):
        self._focus_autocorr_lin()

    def _focus_autocorr_lin(self):
        pos     = pi.qPOS()
        z_before = pos["3"]
        self.zo  = z_before - self.range_total / 2
        self._move_z(self.zo)
        pi.WOS(3, self.zo)

        flag = True
        while flag:
            gone, _, flag = self._ramp_lin()

        f_gone          = int(len(gone) / self.Nz)
        new_profile     = _average(gone, f_gone)
        new_f           = _filter(new_profile)
        lock_f          = self.z_profile_lock_filter
        corr            = np.correlate(new_f, lock_f, "same")
        i_max           = np.argmax(corr)

        dz     = self.range / self.Nz
        z_gone = np.linspace(z_before - self.range/2 + dz/2,
                             z_before + self.range/2 - dz/2, len(new_f))
        self._move_z(z_gone[i_max])

        self.new_profile_filter  = new_f
        self.correlation_filter  = corr

    # ── Rampa lineal PI (idéntica al original) ────────────────────────────────

    def _ramp_lin(self):
        task = channels_photodiodos(self.frequency, self.Ntot_read)
        channels_triggers(task, "Z")

        pi.TWC()
        pi.CTO(3, 3, 3)
        pi.CTO(3, 5, self.zo + self.extra)
        pi.CTO(3, 6, self.zo + self.range_total - self.extra)
        pi.WGC(3, 1)
        pi.WTR(0, self.WTRtime, 0)
        pi.WAV_LIN(3, 0, self.Npoints, "X",  self.Nspeed,  self.range_total, 0,                self.Npoints)
        pi.WAV_LIN(3, 0, self.Npoints, "&",  self.Nspeed, -self.range_total, self.range_total, self.Npoints)
        pi.WSL(3, 3)
        pi.WGO(3, 1)

        data_read  = task.read(self.Ntot_read)
        task.close()

        data_ph      = np.array(data_read[PD_CHANS_LIST.index(PD_CHANNELS[self.laser])])
        data_trigger = np.array(data_read[len(PD_CHANS_LIST)])
        return self._z_profiles(data_ph, data_trigger)

    def _z_profiles(self, ph, trig):
        deriv       = np.diff(trig)
        L           = len(trig)
        asc         = np.where(deriv >= 1.5)[0]
        dsc         = np.where(deriv <= -1.5)[0]
        _empty      = (np.zeros(1), np.zeros(1), True)

        if not len(asc):
            return _empty
        first_asc = asc[0]

        dt_asc2 = np.where(asc > first_asc + L / 3)[0]
        if not len(dt_asc2):
            return _empty
        second_asc = asc[dt_asc2[0]]

        dt_dsc1 = np.where(dsc > first_asc + L / 4)[0]
        if not len(dt_dsc1):
            return _empty
        first_dsc = dsc[dt_dsc1[0]]

        dt_dsc2 = np.where(dsc > first_dsc + L / 3)[0]
        if not len(dt_dsc2):
            return _empty
        second_dsc = dsc[dt_dsc2[0]]

        gone = ph[first_asc:first_dsc]
        back = ph[second_asc:second_dsc]
        return gone, back, False

    # ── Movimiento Z ─────────────────────────────────────────────────────────

    def _move_z(self, z: float):
        pi.MOV(3, z)
        while not all(pi.qONT(3).values()):
            time.sleep(0.1)

    def make_connection(self, frontend: Frontend):
        frontend.focus_gotomax_signal.connect(self.focus_go_to_maximum)
        frontend.focus_lock_signal.connect(self.focus_lock_lin)
        frontend.focus_auto_signal.connect(self.focus_autocorr_lin)
        frontend.focus_autox2_signal.connect(self.focus_autocorr_lin_x2)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _average(arr: np.ndarray, n: int) -> np.ndarray:
    end = n * int(len(arr) / n)
    return np.mean(arr[:end].reshape(-1, n), axis=1)

def _filter(arr: np.ndarray) -> np.ndarray:
    n = len(arr)
    w = int(n / 80) if n % 2 == 0 else int((n - 1) / 80)
    return scipy_signal.savgol_filter(arr, max(w, 3), 1)


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
