# -*- coding: utf-8 -*-
"""
step_and_glue.py — Medición Espectral, Cosido Continuo (Step & Glue) y Cinéticas
PySpectrum 3.0 — UNSAM Nanofotónica

Fase 4 del Rework Arquitectónico (docs/decisions/DECISION_LOG.md#DEC-018): algoritmo de cosido
raised-cosine (cos²/sin²) con solapamiento configurable 10-50% (default 20%), cálculo de
centros espectrales según la dispersión real de la red activa, soporte multimodal 1D (FVB/
Single-Track) y 2D (Imagen), verificación de referencia Raman de agua (banda O-H ~3400 cm⁻¹) y
exportación HDF5 estructurada. Las funciones puras del algoritmo viven en
pyspectrum/calibration/halogen_lamp.py (testeables sin GUI); glue_steps() (blending logístico
preexistente) permanece sin cambios y sigue siendo usado por linescan_spectroscopy.py.
"""
from __future__ import annotations
import time
from pathlib import Path
from typing import Optional, List, Dict
import numpy as np
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import pyqtSignal, pyqtSlot, QTimer
import pyqtgraph as pg

from pyspectrum.drivers.shamrock_driver import DEVICE, get_shamrock, NAME_GRATINGS
from pyspectrum.drivers.andor_ccd_driver import (
    get_andor_ccd, READ_MODE_FVB, READ_MODE_SINGLE_TRACK, READ_MODE_IMAGE,
)
from pyspectrum.calibration.halogen_lamp import (
    HalogenLampCalibration, glue_steps,
    compute_step_centers, sigmoidal_step_and_glue, sigmoidal_step_and_glue_2d,
    export_step_and_glue_to_hdf5,
)
from pyspectrum.calibration.fit_polynomial import fit_signal_polynomial
from pyspectrum.calibration.fit_raman_water import fit_signal_raman
from core.nidaq import heartbeat_shutter

GRATING_SETTLE_TIMEOUT_S = 6.0


class Frontend(QtWidgets.QFrame):
    """Interfaz para adquisición de espectros simples, cosido Step & Glue y cinéticas."""

    measureSingleSignal = pyqtSignal(float, float)  # (lambda_center, exp_time)
    measureStepGlueSignal = pyqtSignal(float, float, float, float, bool, bool)  # (start, end, overlap_pct, exp_time, normalize, check_water)
    stopMeasurementSignal = pyqtSignal()
    saveSpectrumSignal = pyqtSignal(str)
    exportHDF5Signal = pyqtSignal(str)

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
            QCheckBox {
                color: #CDD6F4;
            }
        """)
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QtWidgets.QHBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(12)

        # ── Panel de Controles Izquierdo ──────────────────────────────────────
        controls_vlo = QtWidgets.QVBoxLayout()
        controls_vlo.setSpacing(10)

        lbl_title = QtWidgets.QLabel("🧩 <b>Adquisición & Step and Glue</b>")
        lbl_title.setStyleSheet("font-size: 10.5pt; color: #89B4FA;")
        controls_vlo.addWidget(lbl_title)

        # 1. Parámetros Básicos
        param_grid = QtWidgets.QGridLayout()
        param_grid.setSpacing(6)

        param_grid.addWidget(QtWidgets.QLabel("Tiempo Exp (s):"), 0, 0)
        self.edit_exp = QtWidgets.QLineEdit("1.0")
        self.edit_exp.setToolTip("Tiempo de integración en segundos para cada cuadro espectral individual.")
        param_grid.addWidget(self.edit_exp, 0, 1)

        param_grid.addWidget(QtWidgets.QLabel("Paso Único λ (nm):"), 1, 0)
        self.edit_center_wl = QtWidgets.QLineEdit("532.0")
        self.edit_center_wl.setToolTip("Longitud de onda central (nm) para la adquisición simple de paso único.")
        param_grid.addWidget(self.edit_center_wl, 1, 1)

        controls_vlo.addLayout(param_grid)

        # Botón Medición Simple
        self.btn_single = QtWidgets.QPushButton("🔬 Medir Espectro Simple")
        self.btn_single.setStyleSheet("background-color: #89B4FA; color: #11111B;")
        self.btn_single.setToolTip("Posiciona el espectrógrafo y adquiere un único espectro centrado en la longitud de onda especificada.")
        self.btn_single.clicked.connect(self._on_single_measure)
        controls_vlo.addWidget(self.btn_single)

        # 2. Rango Step & Glue
        box_sandg = QtWidgets.QGroupBox("Parámetros Step & Glue (Cosido Amplio)")
        box_sandg.setStyleSheet("color: #CDD6F4; font-weight: bold; border: 1px solid #45475A; padding: 6px;")
        sandg_grid = QtWidgets.QGridLayout(box_sandg)
        sandg_grid.setSpacing(6)

        sandg_grid.addWidget(QtWidgets.QLabel("λ Inicial (nm):"), 0, 0)
        self.edit_start_wl = QtWidgets.QLineEdit("450.0")
        self.edit_start_wl.setToolTip("Longitud de onda inicial (nm) para el barrido multi-paso concatenado.")
        sandg_grid.addWidget(self.edit_start_wl, 0, 1)

        sandg_grid.addWidget(QtWidgets.QLabel("λ Final (nm):"), 1, 0)
        self.edit_end_wl = QtWidgets.QLineEdit("950.0")
        self.edit_end_wl.setToolTip("Longitud de onda final (nm) para el barrido multi-paso concatenado.")
        sandg_grid.addWidget(self.edit_end_wl, 1, 1)

        sandg_grid.addWidget(QtWidgets.QLabel("Solapamiento (%):"), 2, 0)
        self.spin_overlap_pct = QtWidgets.QSpinBox()
        self.spin_overlap_pct.setRange(10, 50)
        self.spin_overlap_pct.setValue(20)
        self.spin_overlap_pct.setSuffix(" %")
        self.spin_overlap_pct.setToolTip(
            "Porcentaje de solapamiento espectral entre ventanas consecutivas de la red activa "
            "(10% a 50%, 20% por defecto). El cosido raised-cosine funde suavemente cada región "
            "de solapamiento real, garantizando continuidad sin escalones de intensidad."
        )
        sandg_grid.addWidget(self.spin_overlap_pct, 2, 1)

        controls_vlo.addWidget(box_sandg)

        # Opciones de procesamiento
        self.chk_norm_lamp = QtWidgets.QCheckBox("Normalizar con Lámpara Halógena")
        self.chk_norm_lamp.setChecked(True)
        self.chk_norm_lamp.setToolTip("Corrige la curva de respuesta instrumental espectral dividiendo por el perfil de la lámpara halógena.")
        controls_vlo.addWidget(self.chk_norm_lamp)

        self.chk_fit_poly = QtWidgets.QCheckBox("Ajuste Polinomial SPR (λ_max)")
        self.chk_fit_poly.setChecked(True)
        self.chk_fit_poly.setToolTip("Ajusta un modelo polinomial de 4to orden para estimar el pico máximo de resonancia plasmónica (SPR).")
        controls_vlo.addWidget(self.chk_fit_poly)

        self.chk_fit_raman = QtWidgets.QCheckBox("Verificar Referencia Raman Agua (banda O-H, ~3400 cm⁻¹)")
        self.chk_fit_raman.setToolTip("Ajusta la banda O-H del agua (~650 nm a 532 nm de excitación) sobre el espectro cosido, para detectar distorsión espectral introducida por el cosido.")
        controls_vlo.addWidget(self.chk_fit_raman)

        # Botones de Acción Step & Glue y Detención
        btn_box = QtWidgets.QHBoxLayout()
        self.btn_sandg = QtWidgets.QPushButton("🧩 Ejecutar Step and Glue")
        self.btn_sandg.setStyleSheet("background-color: #A6E3A1; color: #11111B;")
        self.btn_sandg.setToolTip("Inicia la rutina automática: cálculo de centros intermedios, rotación de red, lectura y cosido suave de espectros.")
        self.btn_sandg.clicked.connect(self._on_sandg_measure)
        btn_box.addWidget(self.btn_sandg)

        self.btn_stop = QtWidgets.QPushButton("⏹ Detener")
        self.btn_stop.setStyleSheet("background-color: #F38BA8; color: #11111B;")
        self.btn_stop.setToolTip("Detiene de manera inmediata y segura la rutina de adquisición y movimiento en curso, entregando el cosido parcial obtenido hasta ese momento.")
        self.btn_stop.clicked.connect(self._on_stop_measure)
        btn_box.addWidget(self.btn_stop)
        controls_vlo.addLayout(btn_box)

        # Barra de Progreso No Bloqueante
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Paso %v / %m")
        self.progress_bar.setToolTip("Progreso del barrido secuencial de longitudes de onda centrales.")
        controls_vlo.addWidget(self.progress_bar)

        self.lbl_water_ref = QtWidgets.QLabel("")
        self.lbl_water_ref.setWordWrap(True)
        self.lbl_water_ref.setStyleSheet("color: #F9E2AF; font-size: 8.5pt;")
        controls_vlo.addWidget(self.lbl_water_ref)

        self.btn_save = QtWidgets.QPushButton("💾 Guardar Espectro (.txt)...")
        self.btn_save.setStyleSheet("background-color: #313244; color: #CDD6F4;")
        self.btn_save.setToolTip("Guarda los datos espectrales procesados (longitud de onda e intensidad) en formato de texto (.txt).")
        self.btn_save.clicked.connect(self._on_save_spectrum)
        controls_vlo.addWidget(self.btn_save)

        self.btn_export_hdf5 = QtWidgets.QPushButton("💾 Exportar HDF5 Estructurado...")
        self.btn_export_hdf5.setStyleSheet("background-color: #313244; color: #CDD6F4;")
        self.btn_export_hdf5.setToolTip("Exporta el cosido completo (/glued_spectrum, /wavelengths, /raw_steps por paso) con metadatos de red, ranura, pasos y timestamp a HDF5 estructurado.")
        self.btn_export_hdf5.clicked.connect(self._on_export_hdf5)
        controls_vlo.addWidget(self.btn_export_hdf5)

        # Barra de Estado / Info
        self.lbl_status = QtWidgets.QLabel("Listo para medir.")
        self.lbl_status.setStyleSheet("color: #A6ADC8; font-size: 8.5pt;")
        controls_vlo.addWidget(self.lbl_status)

        controls_vlo.addStretch()
        main_layout.addLayout(controls_vlo, stretch=1)

        # ── Gráfico Espectral Derecho ─────────────────────────────────────────
        self.plot_widget = pg.PlotWidget(title="<b>Espectro Adquirido / Step & Glue</b>")
        self.plot_widget.setLabels(bottom="Longitud de Onda (nm)", left="Intensidad (Cuentas / Normalizado)")
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.addLegend(offset=(10, 10))

        self.curve_raw = self.plot_widget.plot(name="Espectro Crudo", pen=pg.mkPen("#89B4FA", width=2.0))
        self.curve_norm = self.plot_widget.plot(name="Normalizado Lámpara", pen=pg.mkPen("#A6E3A1", width=2.0))
        self.curve_fit = self.plot_widget.plot(name="Ajuste Analítico", pen=pg.mkPen("#F38BA8", width=2.5, style=QtCore.Qt.PenStyle.DashLine))

        main_layout.addWidget(self.plot_widget, stretch=3)

    def _on_single_measure(self):
        try:
            wl = float(self.edit_center_wl.text())
            exp = float(self.edit_exp.text())
            self.lbl_status.setText(f"Midiendo espectro simple en {wl:.1f} nm...")
            self.measureSingleSignal.emit(wl, exp)
        except ValueError:
            pass

    def _on_sandg_measure(self):
        try:
            start_wl = float(self.edit_start_wl.text())
            end_wl = float(self.edit_end_wl.text())
            overlap_pct = float(self.spin_overlap_pct.value()) / 100.0
            exp = float(self.edit_exp.text())
            norm = self.chk_norm_lamp.isChecked()
            check_water = self.chk_fit_raman.isChecked()
            self.lbl_water_ref.setText("")
            self.lbl_status.setText(f"Ejecutando Step & Glue [{start_wl:.0f} - {end_wl:.0f} nm], solapamiento {self.spin_overlap_pct.value()}%...")
            self.measureStepGlueSignal.emit(start_wl, end_wl, overlap_pct, exp, norm, check_water)
        except ValueError:
            pass

    def _on_stop_measure(self):
        self.lbl_status.setText("⏹ Detención solicitada por el usuario...")
        self.stopMeasurementSignal.emit()

    def _on_save_spectrum(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Guardar Espectro", "", "Datos ASCII (*.txt *.csv);;NumPy (*.npz);;Todos (*.*)")
        if path:
            self.lbl_status.setText(f"Guardando espectro en {Path(path).name}...")
            self.saveSpectrumSignal.emit(path)

    def _on_export_hdf5(self):
        default_name = f"StepAndGlue_{time.strftime('%Y%m%d_%H%M%S')}.h5"
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Exportar HDF5 Estructurado", default_name, "HDF5 (*.h5 *.hdf5)")
        if path:
            self.lbl_status.setText(f"Exportando HDF5 estructurado a {Path(path).name}...")
            self.exportHDF5Signal.emit(path)

    @pyqtSlot(int, int, float)
    def update_progress(self, step_idx: int, n_steps: int, wl_center: float):
        self.progress_bar.setRange(0, max(1, n_steps))
        self.progress_bar.setValue(step_idx)
        self.progress_bar.setFormat(f"Paso {step_idx} / {n_steps} (λ_c = {wl_center:.1f} nm)")

    @pyqtSlot(str)
    def update_water_reference_status(self, message: str):
        self.lbl_water_ref.setText(message)

    @pyqtSlot(np.ndarray, np.ndarray, np.ndarray, np.ndarray, float)
    def update_spectrum_plot(self, wave_raw: np.ndarray, spec_raw: np.ndarray,
                             wave_norm: np.ndarray, spec_norm: np.ndarray, lambda_max: float):
        self.curve_raw.setData(wave_raw, spec_raw)
        if len(wave_norm) > 0:
            self.curve_norm.setData(wave_norm, spec_norm)
        else:
            self.curve_norm.clear()

        if lambda_max > 0:
            self.lbl_status.setText(f"Medición finalizada. Pico SPR: <b>λ_max = {lambda_max:.2f} nm</b>")
        else:
            self.lbl_status.setText("Medición finalizada con éxito.")

    @pyqtSlot(np.ndarray, np.ndarray)
    def update_fit_plot(self, wave_fit: np.ndarray, spec_fit: np.ndarray):
        self.curve_fit.setData(wave_fit, spec_fit)


class Backend(QtCore.QObject):
    """Motor de adquisición y cosido espectral continuo."""

    spectrumFinishedSignal = pyqtSignal(np.ndarray, np.ndarray, np.ndarray, np.ndarray, float)
    fitFinishedSignal = pyqtSignal(np.ndarray, np.ndarray)
    stepProgressSignal = pyqtSignal(int, int, float)  # (step_idx, n_steps, wl_center)
    waterReferenceCheckedSignal = pyqtSignal(str)

    def __init__(self, camera=None, spectrometer=None, parent=None):
        super().__init__(parent)
        self.camera = camera or get_andor_ccd()
        self.spectrometer = spectrometer or get_shamrock()
        self.lamp_calib = HalogenLampCalibration()
        self._abort_requested = False
        self._last_wave = np.array([])
        self._last_spec = np.array([])
        self._last_norm = np.array([])
        self._raw_wave_steps: List[np.ndarray] = []
        self._raw_spec_steps: List[np.ndarray] = []
        self._last_frame_2d: Optional[np.ndarray] = None  # matriz cosida (H, W_total) en modo Imagen 2D

    def make_connection(self, frontend: Frontend):
        frontend.measureSingleSignal.connect(self.measure_single_spectrum)
        frontend.measureStepGlueSignal.connect(self.measure_step_and_glue)
        frontend.stopMeasurementSignal.connect(self.stop_measurement)
        frontend.saveSpectrumSignal.connect(self.save_spectrum)
        frontend.exportHDF5Signal.connect(self.export_hdf5)
        self.spectrumFinishedSignal.connect(frontend.update_spectrum_plot)
        self.fitFinishedSignal.connect(frontend.update_fit_plot)
        self.stepProgressSignal.connect(frontend.update_progress)
        self.waterReferenceCheckedSignal.connect(frontend.update_water_reference_status)

    @pyqtSlot()
    def stop_measurement(self):
        self._abort_requested = True
        print("[Step & Glue] Solicitud de detención recibida.")

    def _settle_wavelength(self, wl_center: float, timeout_s: float = GRATING_SETTLE_TIMEOUT_S) -> bool:
        """Settle del grating SIN sleep fijo: polling real de is_moving()/wait_until_ready()
        del driver Shamrock (patrón idéntico a
        linescan_spectroscopy.py::LineScanSpectroscopyWorker._settle_wavelength, DEC-009),
        con heartbeat del obturador renovado en cada tick de espera."""
        self.spectrometer.ShamrockSetWavelength(DEVICE, wl_center)
        t_end = time.time() + timeout_s
        while self.spectrometer.is_moving():
            if self._abort_requested:
                return False
            heartbeat_shutter(30.0)
            if time.time() > t_end:
                print(f"[Step & Glue] Timeout de asentamiento del grating a {wl_center:.1f} nm (> {timeout_s}s).")
                return False
            time.sleep(0.01)
        heartbeat_shutter(30.0)
        return True

    @pyqtSlot(str)
    def save_spectrum(self, filepath: str):
        if len(self._last_wave) == 0:
            print("[Step & Glue] No hay espectro registrado para guardar.")
            return
        try:
            p = Path(filepath)
            if p.suffix == ".npz":
                np.savez_compressed(p, wavelength=self._last_wave, intensity=self._last_spec, normalized=self._last_norm)
            else:
                data = np.column_stack([self._last_wave, self._last_spec])
                header = "Wavelength_nm\tIntensity_Counts"
                if len(self._last_norm) == len(self._last_wave) and len(self._last_norm) > 0:
                    data = np.column_stack([self._last_wave, self._last_spec, self._last_norm])
                    header += "\tNormalized_Intensity"
                np.savetxt(p, data, delimiter="\t", header=header, comments="# ")
            print(f"[Step & Glue] Espectro guardado con éxito en: {p}")
        except Exception as e:
            print(f"[Step & Glue] Error al guardar espectro: {e}")

    @pyqtSlot(str)
    def export_hdf5(self, filepath: str):
        """Exporta el último cosido a HDF5 estructurado: /glued_spectrum, /wavelengths y un
        grupo /raw_steps por cada paso crudo, con metadatos de red, ranura y timestamp."""
        if len(self._last_wave) == 0:
            print("[Step & Glue] No hay cosido registrado para exportar a HDF5.")
            return
        try:
            ret_g, grating = self.spectrometer.ShamrockGetGrating(DEVICE)
            ret_s, slit_width = self.spectrometer.ShamrockGetSlit(DEVICE)
            metadata = {
                "grating": int(grating),
                "grating_name": NAME_GRATINGS[grating - 1] if 1 <= grating <= len(NAME_GRATINGS) else str(grating),
                "slit_width_um": float(slit_width),
            }
            # /glued_spectrum es la matriz 2D completa (H, W_total) cuando el barrido se hizo en
            # modo Imagen; de lo contrario, el vector 1D cosido.
            glued_for_export = self._last_frame_2d if self._last_frame_2d is not None else self._last_spec
            export_step_and_glue_to_hdf5(
                filepath, self._last_wave, glued_for_export,
                self._raw_wave_steps, self._raw_spec_steps, metadata,
            )
            print(f"[Step & Glue] HDF5 estructurado exportado con éxito en: {filepath}")
        except Exception as e:
            print(f"[Step & Glue] Error al exportar HDF5: {e}")

    def _check_water_reference(self, wave: np.ndarray, spec: np.ndarray, laser_nm: float = 532.0) -> str:
        """Ajusta la banda O-H del agua (~3400 cm⁻¹, ~650 nm a 532 nm) sobre el espectro cosido
        para detectar distorsión espectral introducida por el cosido (reutiliza
        pyspectrum/calibration/fit_raman_water.py::fit_signal_raman sin modificarlo)."""
        try:
            _, _, params = fit_signal_raman(wave, spec, ends_notch=wave[0], final_wave=wave[-1], laser_nm=laser_nm)
            amplitude_oh = float(params[3])  # I_2: amplitud de la banda O-H principal (peak1, ~3400 cm⁻¹)
            if amplitude_oh > 50.0:
                return f"✅ Referencia Raman Agua: banda O-H (~3400 cm⁻¹) detectada, amplitud {amplitude_oh:.0f} — cosido sin distorsión aparente."
            return f"⚠️ Referencia Raman Agua: banda O-H (~3400 cm⁻¹) débil o no detectada (amplitud {amplitude_oh:.0f}) — verificar el cosido."
        except Exception as e:
            return f"⚠️ No se pudo verificar la referencia Raman de agua: {e}"

    @pyqtSlot(float, float)
    def measure_single_spectrum(self, lambda_center: float, exp_time: float):
        from pyspectrum.modules.hardware_session import hardware_session
        if not hardware_session.acquire_session("Step & Glue — Espectro Único"):
            return
        try:
            # 1. Configurar espectrógrafo y cámara
            if not self._settle_wavelength(lambda_center):
                return
            self.camera.set_exposure_time(exp_time)

            # 2. Adquirir y leer (prioriza lectura 1D por hardware de bajo ruido si está activa)
            if hasattr(self.camera, "get_1d_spectrum") and getattr(self.camera, "_read_mode", 4) in (0, 1):
                spec_1d = self.camera.get_1d_spectrum()
            else:
                frame = self.camera.get_most_recent_image()
                spec_1d = np.mean(frame, axis=0)

            # Calibración cúbica de EEPROM o estándar
            if hasattr(self.spectrometer, "get_wavelength_axis_cubic"):
                ret, wave_1d = self.spectrometer.get_wavelength_axis_cubic(DEVICE, len(spec_1d))
            else:
                ret, wave_1d = self.spectrometer.ShamrockGetCalibration(DEVICE, len(spec_1d))

            # 3. Ajuste opcional
            wave_fit, spec_fit, lambda_max = fit_signal_polynomial(wave_1d, spec_1d, ends_notch=lambda_center - 10, final_wave=wave_1d[-1])
            if len(wave_fit) > 0:
                self.fitFinishedSignal.emit(wave_fit, spec_fit)

            self.spectrumFinishedSignal.emit(wave_1d, spec_1d, np.array([]), np.array([]), lambda_max)
        finally:
            hardware_session.release_session("Step & Glue — Espectro Único")

    @pyqtSlot(float, float, float, float, bool, bool)
    def measure_step_and_glue(self, start_wl: float, end_wl: float, overlap_pct: float, exp_time: float,
                               normalize: bool, check_water: bool = False):
        from pyspectrum.modules.hardware_session import hardware_session
        if not hardware_session.acquire_session("Step & Glue", auto_pause_live=True):
            return

        try:
            # Centros espectrales según la dispersión real de la red activa (Fase 4)
            ret_g, grating = self.spectrometer.ShamrockGetGrating(DEVICE)
            centers = compute_step_centers(start_wl, end_wl, overlap_pct, grating=grating, num_pixels=1004)
            n_steps = len(centers)

            # Modo 1D (FVB/Single-Track) vs 2D (Imagen): según el modo de lectura REAL de la
            # cámara en este instante (mismo criterio que static_raman.py::_acquire_and_emit,
            # Fase 3 — la cámara es un singleton compartido entre pestañas).
            is_2d_mode = (self.camera.get_read_mode() == READ_MODE_IMAGE)

            raw_waves: List[np.ndarray] = []
            raw_data: List[np.ndarray] = []  # espectros 1D o cuadros 2D según is_2d_mode

            self._abort_requested = False
            self.camera.set_exposure_time(exp_time)

            for i, wl_c in enumerate(centers):
                if self._abort_requested:
                    print(f"[Step & Glue] Escaneo abortado en {wl_c:.1f} nm por el usuario ({i}/{n_steps} pasos completados).")
                    break

                # 1. Pausar la cámara (aborta cualquier adquisición residual antes de mover la red)
                self.camera.abort_acquisition()

                # 2. Mover el Shamrock y esperar asentamiento mecánico real
                if not self._settle_wavelength(wl_c):
                    print(f"[Step & Glue] Escaneo abortado en {wl_c:.1f} nm por fallo/timeout de asentamiento del grating.")
                    break

                if hasattr(self.spectrometer, "get_wavelength_axis_cubic"):
                    ret, w_cal = self.spectrometer.get_wavelength_axis_cubic(DEVICE, 1004)
                else:
                    ret, w_cal = self.spectrometer.ShamrockGetCalibration(DEVICE, 1004)

                # 3. Adquirir espectro (1D) o cuadro (2D)
                if is_2d_mode:
                    data_i = self.camera.get_most_recent_image()
                else:
                    data_i = self.camera.get_1d_spectrum()

                raw_waves.append(w_cal)
                raw_data.append(data_i)

                # 4. Barra de progreso no bloqueante
                self.stepProgressSignal.emit(i + 1, n_steps, wl_c)

            # Cosido resiliente: incluso si se abortó a mitad de camino, cose y entrega lo
            # obtenido hasta ese punto (no se descartan datos parciales).
            if not raw_waves:
                print("[Step & Glue] Adquisición abortada sin datos.")
                return

            if is_2d_mode:
                glued_w, glued_frame = sigmoidal_step_and_glue_2d(raw_waves, raw_data)
                glued_s = np.mean(glued_frame, axis=0)  # curva representativa 1D para el gráfico
            else:
                glued_w, glued_s = sigmoidal_step_and_glue(raw_waves, raw_data)
                glued_frame = None
            self._last_frame_2d = glued_frame

            # Normalización con lámpara halógena (broadcast fila a fila en modo 2D)
            norm_w, norm_s = np.array([]), np.array([])
            lambda_max = 0.0

            if normalize:
                norm_w = glued_w
                if is_2d_mode:
                    norm_frame = self.lamp_calib.normalize_spectrum(glued_w, glued_frame)
                    norm_s = np.mean(norm_frame, axis=0)
                else:
                    norm_s = self.lamp_calib.normalize_spectrum(glued_w, glued_s)
                target_w, target_s = norm_w, norm_s
            else:
                target_w, target_s = glued_w, glued_s

            # Ajuste de SPR
            wave_fit, spec_fit, lambda_max = fit_signal_polynomial(target_w, target_s, ends_notch=start_wl + 10, final_wave=end_wl - 10)
            if len(wave_fit) > 0:
                self.fitFinishedSignal.emit(wave_fit, spec_fit)

            # Verificación de referencia Raman de agua (banda O-H ~3400 cm⁻¹)
            if check_water:
                msg = self._check_water_reference(target_w, target_s)
                self.waterReferenceCheckedSignal.emit(msg)

            # Cachear último resultado (para Guardar TXT/NPZ y Exportar HDF5)
            self._last_wave = glued_w
            self._last_spec = glued_s
            self._last_norm = norm_s
            self._raw_wave_steps = raw_waves
            self._raw_spec_steps = raw_data

            self.spectrumFinishedSignal.emit(glued_w, glued_s, norm_w, norm_s, lambda_max)
        finally:
            hardware_session.release_session("Step & Glue")
