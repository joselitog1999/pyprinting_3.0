# -*- coding: utf-8 -*-
"""
hyperspectral_confocal.py — Mapeo Confocal Hiperespectral 2D/3D (PI Piezo + Andor CCD)
PySpectrum 3.0 — UNSAM Nanofotónica
"""
from __future__ import annotations
import os
import threading
import time
from pathlib import Path
import numpy as np
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import pyqtSignal, pyqtSlot, QTimer
import pyqtgraph as pg

from config import pi, SHUTTERS
from core.nidaq import open_shutter, close_shutter, heartbeat_shutter  # noqa: F401 (compatibilidad)
from pyspectrum.drivers.shamrock_driver import DEVICE, get_shamrock
from pyspectrum.drivers.andor_ccd_driver import get_andor_ccd
from pyspectrum.modules.hardware_session import hardware_session
from pyspectrum.ui.viewbox_tools import LinePlotWidget


class Frontend(QtWidgets.QFrame):
    """Interfaz para escaneo confocal hiperespectral y visualización de cubos (X, Y, λ)."""

    # (xmin, xmax, ymin, ymax, step, exp, laser) — el láser se agregó en ANOM-HYPERSPEC-02:
    # antes este mapeo no tenía ningún selector de excitación ni ciclo de vida de obturador.
    mirrorConfirmedSignal = pyqtSignal(str)
    startScanSignal = pyqtSignal(float, float, float, float, float, float, str)
    stopScanSignal = pyqtSignal()
    pointSelectedSignal = pyqtSignal(int, int)

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
            QPushButton {
                background-color: #313244;
                color: #CDD6F4;
                border: 1px solid #45475A;
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45475A;
                color: #89B4FA;
            }
            QLineEdit {
                background-color: #11111B;
                color: #CDD6F4;
                border: 1px solid #45475A;
                border-radius: 4px;
                padding: 4px;
            }
        """)
        self._setup_ui()
        try:
            from core.nanopositioning import register_regime_listener
            from config import DEFAULT_COORDINATE_REGIME
            register_regime_listener(self.on_regime_changed)
            self.on_regime_changed(DEFAULT_COORDINATE_REGIME)
        except Exception:
            pass

    def closeEvent(self, event):
        try:
            from core.nanopositioning import unregister_regime_listener
            unregister_regime_listener(self.on_regime_changed)
        except Exception:
            pass
        super().closeEvent(event)

    def on_regime_changed(self, regime: str):
        try:
            from core.nanopositioning import COORDINATE_NOMENCLATURE
            from config import REGIME_LEGACY
            nomen = COORDINATE_NOMENCLATURE.get(regime, COORDINATE_NOMENCLATURE[REGIME_LEGACY])
            if hasattr(self, "lbl_x_range"):
                self.lbl_x_range.setText(f"{nomen['axis1_name']} Min / Max (µm):")
                self.lbl_y_range.setText(f"{nomen['axis2_name']} Min / Max (µm):")
        except Exception:
            pass

    def _setup_ui(self):
        main_layout = QtWidgets.QHBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(12)

        # ── Controles de Escaneo ──────────────────────────────────────────────
        ctrl_vlo = QtWidgets.QVBoxLayout()
        ctrl_vlo.setSpacing(8)

        lbl_title = QtWidgets.QLabel("🧬 <b>Mapeo Confocal Hiperespectral (X, Y, λ)</b>")
        lbl_title.setStyleSheet("font-size: 10pt; color: #89B4FA;")
        ctrl_vlo.addWidget(lbl_title)

        grid = QtWidgets.QGridLayout()
        grid.setSpacing(6)

        self.lbl_x_range = QtWidgets.QLabel("X Min / Max (µm):")
        grid.addWidget(self.lbl_x_range, 0, 0)
        self.edit_xmin = QtWidgets.QLineEdit("45.0")
        self.edit_xmax = QtWidgets.QLineEdit("55.0")
        self.edit_xmin.setToolTip("Límite inferior en X (µm) para la grilla de escaneo piezoeléctrico. Rango: 0.0 a 100.0 µm.")
        self.edit_xmax.setToolTip("Límite superior en X (µm) para la grilla de escaneo piezoeléctrico. Rango: 0.0 a 100.0 µm.")
        hlo_x = QtWidgets.QHBoxLayout()
        hlo_x.addWidget(self.edit_xmin); hlo_x.addWidget(self.edit_xmax)
        grid.addLayout(hlo_x, 0, 1)

        self.lbl_y_range = QtWidgets.QLabel("Y Min / Max (µm):")
        grid.addWidget(self.lbl_y_range, 1, 0)
        self.edit_ymin = QtWidgets.QLineEdit("45.0")
        self.edit_ymax = QtWidgets.QLineEdit("55.0")
        self.edit_ymin.setToolTip("Límite inferior en Y (µm) para la grilla de escaneo piezoeléctrico. Rango: 0.0 a 100.0 µm.")
        self.edit_ymax.setToolTip("Límite superior en Y (µm) para la grilla de escaneo piezoeléctrico. Rango: 0.0 a 100.0 µm.")
        hlo_y = QtWidgets.QHBoxLayout()
        hlo_y.addWidget(self.edit_ymin); hlo_y.addWidget(self.edit_ymax)
        grid.addLayout(hlo_y, 1, 1)

        grid.addWidget(QtWidgets.QLabel("Paso Δ (µm):"), 2, 0)
        self.edit_step = QtWidgets.QLineEdit("1.0")
        self.edit_step.setToolTip("Resolución espacial / Paso de muestreo Δ (µm) entre puntos sucesivos.")
        grid.addWidget(self.edit_step, 2, 1)

        grid.addWidget(QtWidgets.QLabel("Tiempo Exp (s):"), 3, 0)
        self.edit_exp = QtWidgets.QLineEdit("0.05")
        self.edit_exp.setToolTip("Tiempo de integración/exposición del sensor CCD Andor (segundos) por cada punto del mapa.")
        grid.addWidget(self.edit_exp, 3, 1)

        grid.addWidget(QtWidgets.QLabel("Láser de Excitación:"), 4, 0)
        self.combo_mirror = QtWidgets.QComboBox()
        self.combo_mirror.addItems(["— confirmá dónde está —", "abajo (espectrómetro)", "arriba (confocal / cámara)"])
        self.combo_mirror.setToolTip("El espejo de detección no tiene sensor: confirmá dónde está ahora. La rutina "
                                     "lo baja sola para medir y al terminar lo devuelve a esta posición (R4-K).")
        ctrl_vlo.addWidget(QtWidgets.QLabel("Espejo de detección ahora:"))
        ctrl_vlo.addWidget(self.combo_mirror)
        self.combo_laser = QtWidgets.QComboBox()
        self.combo_laser.addItems(SHUTTERS)
        self.combo_laser.setToolTip("Línea láser cuyo obturador se abre durante el mapeo hiperespectral.")
        grid.addWidget(self.combo_laser, 4, 1)

        ctrl_vlo.addLayout(grid)

        # Botón Iniciar Escaneo
        self.btn_scan = QtWidgets.QPushButton("🚀 Iniciar Escaneo Hiperespectral")
        self.btn_scan.setToolTip("Inicia o aborta el barrido confocal raster bidimensional (PI Piezo + CCD Andor).")
        self.btn_scan.setCheckable(True)
        self.btn_scan.setStyleSheet("background-color: #89B4FA; color: #11111B;")
        self.btn_scan.clicked.connect(self._on_toggle_scan)
        ctrl_vlo.addWidget(self.btn_scan)

        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setToolTip("Porcentaje de avance del escaneo hiperespectral (puntos completados / total).")
        self.progress_bar.setStyleSheet("QProgressBar { border: 1px solid #45475A; border-radius: 4px; text-align: center; color: #CDD6F4; } QProgressBar::chunk { background-color: #A6E3A1; }")
        self.progress_bar.setValue(0)
        ctrl_vlo.addWidget(self.progress_bar)

        self.lbl_info = QtWidgets.QLabel("Matriz: 11x11 pts (121 espectros)")
        self.lbl_info.setToolTip("Dimensiones de la matriz de escaneo espacial y cantidad total de espectros a adquirir.")
        self.lbl_info.setStyleSheet("color: #A6ADC8; font-size: 8.5pt;")
        ctrl_vlo.addWidget(self.lbl_info)

        # Conectar campos de texto para actualizar información de matriz dinámicamente
        self.edit_xmin.textChanged.connect(self._update_matrix_info)
        self.edit_xmax.textChanged.connect(self._update_matrix_info)
        self.edit_ymin.textChanged.connect(self._update_matrix_info)
        self.edit_ymax.textChanged.connect(self._update_matrix_info)
        self.edit_step.textChanged.connect(self._update_matrix_info)

        ctrl_vlo.addStretch()
        main_layout.addLayout(ctrl_vlo, stretch=1)

        # ── Visores: Mapa 2D de Intensidad Integrada + Espectro Local ─────────
        right_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)

        # Mapa 2D
        self.imv_map = pg.ImageView()
        self.imv_map.setToolTip("Mapa 2D de intensidad espectral integrada ∫I(λ)dλ en falso color.")
        self.imv_map.ui.roiBtn.hide()
        self.imv_map.ui.menuBtn.hide()
        right_splitter.addWidget(self.imv_map)

        # Espectro del punto seleccionado
        self.plot_point = LinePlotWidget(title="Espectro del Punto Seleccionado", x_label="Longitud de Onda (nm)", y_label="Intensidad")
        self.plot_point.setToolTip("Gráfico espectral I(λ) adquirido en el punto actual o seleccionado del mapa confocal.")
        self.plot_point.setFixedHeight(160)
        right_splitter.addWidget(self.plot_point)

        main_layout.addWidget(right_splitter, stretch=3)

    def _update_matrix_info(self):
        try:
            xmin = float(self.edit_xmin.text())
            xmax = float(self.edit_xmax.text())
            ymin = float(self.edit_ymin.text())
            ymax = float(self.edit_ymax.text())
            step = float(self.edit_step.text())
            if step > 0:
                nx = max(1, int(round(abs(xmax - xmin) / step)) + 1)
                ny = max(1, int(round(abs(ymax - ymin) / step)) + 1)
                self.lbl_info.setText(f"Matriz: {nx}x{ny} pts ({nx * ny} espectros)")
        except (ValueError, ZeroDivisionError):
            pass

    def _on_toggle_scan(self, checked: bool):
        if checked:
            try:
                xmin = float(self.edit_xmin.text())
                xmax = float(self.edit_xmax.text())
                ymin = float(self.edit_ymin.text())
                ymax = float(self.edit_ymax.text())
                step = float(self.edit_step.text())
                exp = float(self.edit_exp.text())
                laser = self.combo_laser.currentText()
                mirror = {1: "down", 2: "up"}.get(self.combo_mirror.currentIndex())
                if mirror is None:
                    self.btn_scan.setChecked(False)
                    self.lbl_info.setText("Confirmá dónde está el espejo de detección antes de iniciar.")
                    return
                self.mirrorConfirmedSignal.emit(mirror)
                self.combo_mirror.setCurrentIndex(0)        # la confirmación no se recuerda

                self.btn_scan.setText("⏹️ Detener Escaneo")
                self.btn_scan.setStyleSheet("background-color: #F38BA8; color: #11111B;")
                self.startScanSignal.emit(xmin, xmax, ymin, ymax, step, exp, laser)
            except ValueError:
                self.btn_scan.setChecked(False)
        else:
            self.btn_scan.setText("🚀 Iniciar Escaneo Hiperespectral")
            self.btn_scan.setStyleSheet("background-color: #89B4FA; color: #11111B;")
            self.stopScanSignal.emit()

    @pyqtSlot(np.ndarray)
    def update_map(self, map_2d: np.ndarray):
        self.imv_map.setImage(map_2d.T, autoRange=False, autoLevels=True)

    @pyqtSlot(int)
    def update_progress(self, val: int):
        self.progress_bar.setValue(val)
        if val >= 100:
            self.btn_scan.setChecked(False)
            self.btn_scan.setText("🚀 Iniciar Escaneo Hiperespectral")
            self.btn_scan.setStyleSheet("background-color: #89B4FA; color: #11111B;")

    @pyqtSlot(np.ndarray, np.ndarray)
    def update_point_spectrum(self, wave_axis: np.ndarray, spec: np.ndarray):
        self.plot_point.set_data(wave_axis, spec, pen_color="#F9E2AF")


class Backend(QtCore.QObject):
    """Mapa confocal hiperespectral sobre las primitivas de grilla (AND-1, parte 2; C-10; R4-K).

    Por píxel: la platina confirma la llegada y se toma una exposición real (FVB). Una exposición fallida
    deja el píxel en NaN, marcado en `failed`; una platina que no llega detiene el mapa con los obturadores
    cerrados. El espejo lo confirma el operador; la rutina lo baja para medir y lo devuelve al terminar. El
    cubo se guarda en HDF5 en `data_dir`, también si el mapa se detiene."""

    mapUpdatedSignal = pyqtSignal(np.ndarray)
    progressSignal = pyqtSignal(int)
    pointSpectrumSignal = pyqtSignal(np.ndarray, np.ndarray)
    scanFinishedSignal = pyqtSignal()
    statusSignal = pyqtSignal(str)

    SESSION = "Mapeo Confocal"

    def __init__(self, camera=None, spectrometer=None, parent=None):
        super().__init__(parent)
        self.camera = camera or get_andor_ccd()
        self.spectrometer = spectrometer or get_shamrock()
        self._scanning = False
        self._datacube = None  # (Nx, Ny, N_lambda)
        self.wave_axis = np.linspace(450, 750, 1004)
        self.laser_in_use = ""
        self._stop_event = threading.Event()
        self._mirror_confirmed = None
        self._runner = None
        self._failed = None
        self._exp_time = 0.0
        self._saved_path = None
        base = os.getenv("PYSPECTRUM_ROUTINE_DATA_DIR") or str(Path.home() / "Documents" / "Data_PySpectrum")
        self.data_dir = Path(base) / "confocal_map"

        self.scan_timer = QTimer(self)
        self.scan_timer.setInterval(20)
        self.scan_timer.timeout.connect(self._scan_step)
        hardware_session.emergencyStopSignal.connect(self.stop_scan)

    def make_connection(self, frontend: Frontend):
        frontend.mirrorConfirmedSignal.connect(self.confirm_mirror)
        frontend.startScanSignal.connect(self.start_scan)
        frontend.stopScanSignal.connect(self.stop_scan)
        self.mapUpdatedSignal.connect(frontend.update_map)
        self.progressSignal.connect(frontend.update_progress)
        self.pointSpectrumSignal.connect(frontend.update_point_spectrum)
        self.statusSignal.connect(frontend.lbl_info.setText)

    @pyqtSlot(str)
    def confirm_mirror(self, position: str):
        """El operador dice dónde está el espejo ahora (R4-K, P2). Vale para la próxima corrida."""
        from core.nidaq import confirm_detection_mirror_belief
        if position not in ("up", "down"):
            return
        confirm_detection_mirror_belief(position)
        self._mirror_confirmed = position

    def request_stop(self):
        """Se puede llamar desde cualquier hilo: corta la exposición en curso en el tramo siguiente."""
        self._stop_event.set()

    @pyqtSlot(float, float, float, float, float, float, str)
    def start_scan(self, xmin: float, xmax: float, ymin: float, ymax: float, step: float,
                   exp_time: float, laser: str = ""):
        from pyspectrum.drivers.andor_ccd_driver import READ_MODE_FVB
        from pyspectrum.drivers.shamrock_driver import SHAMROCK_SUCCESS
        from pyspectrum.modules.routines.grid_runner import GridRunner, GridAbort, GridSafetyPause
        from pyspectrum.services.spectrometer_shutter import open_spectrometer_shutter
        if self._scanning:
            return
        if self._mirror_confirmed is None:
            self.statusSignal.emit("⛔ Confirmá dónde está el espejo de detección antes de iniciar el mapa.")
            return
        if not hardware_session.acquire_session(self.SESSION):
            self.statusSignal.emit("⛔ El hardware está ocupado o la E-STOP está activa.")
            return

        xmin, xmax = sorted((max(0.0, min(100.0, float(xmin))), max(0.0, min(100.0, float(xmax)))))
        ymin, ymax = sorted((max(0.0, min(100.0, float(ymin))), max(0.0, min(100.0, float(ymax)))))
        step = max(0.01, float(step))
        self.xs = np.arange(xmin, xmax + step * 0.5, step)
        self.ys = np.arange(ymin, ymax + step * 0.5, step)
        self.nx, self.ny = len(self.xs), len(self.ys)

        ret, axis = self.spectrometer.ShamrockGetCalibration(DEVICE, 1004)
        axis = np.asarray(axis, dtype=np.float64)
        if ret != SHAMROCK_SUCCESS or axis.size != 1004 or not np.all(np.isfinite(axis)):
            hardware_session.release_session(self.SESSION)
            print(f"[Mapeo Confocal] Eje λ no confiable: código {ret}, {axis.size} puntos, "
                  f"finito={bool(np.all(np.isfinite(axis))) if axis.size else False}")
            self.statusSignal.emit(f"⛔ No se pudo leer el eje λ del Shamrock (código {ret}): el mapa no arranca.")
            return
        self.wave_axis = axis
        self._datacube = np.full((self.nx, self.ny, 1004), np.nan, dtype=np.float32)
        self._failed = np.zeros((self.nx, self.ny), dtype=bool)
        self.map_2d = np.zeros((self.nx, self.ny), dtype=np.float32)
        self.curr_ix = self.curr_iy = 0
        self.total_points = self.nx * self.ny
        self.points_done = 0
        self._exp_time = float(exp_time)
        self._complete = False
        self._saved_path = None
        self._stop_event.clear()
        self._runner = GridRunner(self.camera, should_abort=self._stop_event.is_set)
        self.laser_in_use = laser or (SHUTTERS[0] if SHUTTERS else "")
        self._scanning = True
        try:
            self.camera.set_read_mode(READ_MODE_FVB)
            res = open_spectrometer_shutter(self.camera, self.spectrometer)
            if not res.ok:
                raise GridSafetyPause(f"El obturador del espectrómetro no abrió: {res.detail}")
            self._runner.set_mirror("down")          # el espectro se mide con el espejo abajo (R4-K)
            if self.laser_in_use:
                self._runner.laser(self.laser_in_use, True)
        except (GridSafetyPause, GridAbort) as e:
            self._finish(str(e))
            return
        self.scan_timer.start()

    @pyqtSlot()
    def stop_scan(self):
        self._stop_event.set()
        if self._scanning:
            self._finish("Mapa detenido.")

    def _finish(self, reason: str = ""):
        """Cierra láser y obturador del espectrómetro, devuelve el espejo, guarda el cubo y suelta la sesión.
        Una sola vez por corrida."""
        from pyspectrum.services.spectrometer_shutter import close_spectrometer_shutter
        if not self._scanning:
            return
        self._scanning = False
        self.scan_timer.stop()
        runner = self._runner
        try:
            if runner is not None and not runner.close_lasers():
                reason += " El cierre del láser no se confirmó."
            elif runner is None and self.laser_in_use:
                close_shutter(self.laser_in_use)
        finally:
            self.laser_in_use = ""
        close_spectrometer_shutter(self.camera, self.spectrometer)
        if (runner is not None and self._mirror_confirmed and not hardware_session.is_emergency_stopped):
            try:
                runner.hw.flipper_notch532(self._mirror_confirmed)
            except Exception as e:
                reason += f" No se pudo devolver el espejo: {e}."
        self._mirror_confirmed = None                 # la confirmación vale para una corrida
        self._save()
        hardware_session.release_session(self.SESSION)
        self.progressSignal.emit(100)
        if reason:
            print(f"[Mapeo Confocal] {reason.strip()}")
            self.statusSignal.emit(reason.strip())
        self.scanFinishedSignal.emit()

    def _save(self):
        if self._datacube is None:
            return
        try:
            import h5py
            d = Path(self.data_dir)
            d.mkdir(parents=True, exist_ok=True)
            path = d / time.strftime("map_%Y%m%d_%H%M%S.h5")
            k = 1
            while path.exists():
                path = d / time.strftime(f"map_%Y%m%d_%H%M%S_{k}.h5")
                k += 1
            with h5py.File(path, "w") as f:
                f.create_dataset("cube", data=self._datacube, compression="gzip", shuffle=True)
                f.create_dataset("failed", data=self._failed)
                f.create_dataset("map_2d", data=self.map_2d)
                f.create_dataset("x_um", data=self.xs)
                f.create_dataset("y_um", data=self.ys)
                f.create_dataset("wavelength_nm", data=self.wave_axis)
                f.attrs["exposure_s"] = self._exp_time
                f.attrs["read_mode"] = "FVB"
                f.attrs["complete"] = bool(self._complete)
                f.attrs["points_done"] = int(self.points_done)
                ret_g, grating = self.spectrometer.ShamrockGetGrating(DEVICE)
                f.attrs["grating"] = int(grating) if ret_g == 20202 else -1
                f.attrs["cube_axes"] = "x, y, lambda"
                from pyspectrum.calibration.repository import spectrum_software_correction, write_correction_attrs
                write_correction_attrs(f.attrs, spectrum_software_correction(self.spectrometer))   # R3-gui §4.6
            self._saved_path = str(path)
        except Exception as e:
            self.statusSignal.emit(f"⚠️ No se pudo guardar el cubo: {e}")

    def _scan_step(self):
        from pyspectrum.modules.routines.grid_runner import GridAbort, GridSafetyPause, NodeFailed
        if not self._scanning:
            return
        if hardware_session.is_emergency_stopped or self._stop_event.is_set():
            self._finish("Mapa detenido.")
            return
        x = float(self.xs[self.curr_ix])
        y = float(self.ys[self.curr_iy])
        try:
            self._runner.move_to(x, y)
            spec = self._runner.expose((1004,), self._exp_time)
            self._datacube[self.curr_ix, self.curr_iy, :] = spec
            self.map_2d[self.curr_ix, self.curr_iy] = float(np.sum(spec))
            self.pointSpectrumSignal.emit(self.wave_axis, spec)
        except NodeFailed as e:
            self._failed[self.curr_ix, self.curr_iy] = True
            self.statusSignal.emit(f"Píxel ({x:.2f}, {y:.2f}) µm fallido: {e}")
        except GridSafetyPause as e:
            self._finish(f"⛔ {e}")
            return
        except GridAbort:
            self._finish("Mapa detenido.")
            return

        self.points_done += 1
        self.progressSignal.emit(int(100.0 * self.points_done / self.total_points))
        self.mapUpdatedSignal.emit(self.map_2d)
        self.curr_ix += 1
        if self.curr_ix >= self.nx:
            self.curr_ix = 0
            self.curr_iy += 1
            if self.curr_iy >= self.ny:
                self._complete = True
                self._finish("Mapa completo." + (f" Guardado en {self.data_dir}." if self.data_dir else ""))
