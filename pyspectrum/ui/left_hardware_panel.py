# -*- coding: utf-8 -*-
"""
left_hardware_panel.py — Panel Izquierdo Permanente y Dinámico (Andor + Shamrock)
PySpectrum 3.0 — UNSAM Nanofotónica

Widget permanente del tercio izquierdo del shell principal, con los controles centrales de la
cámara Andor EMCCD y el espectrógrafo Shamrock 500i. A diferencia del patrón Frontend/Backend
separado usado en camera_andor.py / spectrum_control.py, este panel posee una única instancia
en toda la aplicación (no hay una segunda cámara/espectrógrafo con la que multiplexar), así que
combina UI y despacho directo al driver en una sola clase, con un QTimer propio de refresco
periódico (mismo patrón 1 Hz que camera_andor.py::Backend._read_temperature).
"""
from __future__ import annotations
from typing import Any, Optional
from PyQt6 import QtCore, QtWidgets
from PyQt6.QtCore import QTimer

from pyspectrum.drivers.shamrock_driver import (
    DEVICE, NAME_GRATINGS, NAME_PORTS_IN, NAME_PORTS_OUT, GRATING_MIRROR,
)
from pyspectrum.ui.zero_order_dialog import ZeroOrderSafetyDialog
from pyspectrum.modules.spectroscopy_context import spectroscopy_context


SHUTTER_MODE_NAMES = ["Auto (sincronizado)", "Siempre Abierto", "Siempre Cerrado"]


class LeftHardwarePanel(QtWidgets.QWidget):
    """Panel permanente de instrumentación central: cámara Andor EMCCD y espectrógrafo
    Shamrock 500i, con adaptabilidad dinámica de campos según la pestaña activa del shell."""

    def __init__(self, camera: Any, spectrometer: Any, parent=None, step_glue_tab_index: int = 2):
        super().__init__(parent)
        self.camera = camera
        self.spectrometer = spectrometer
        self.step_glue_tab_index = step_glue_tab_index

        self.setStyleSheet("""
            QGroupBox {
                color: #89B4FA; font-weight: bold; border: 1px solid #313244;
                border-radius: 6px; margin-top: 10px; padding-top: 8px;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }
            QLabel { color: #CDD6F4; }
            QPushButton {
                background-color: #313244; color: #CDD6F4; border: 1px solid #45475A;
                border-radius: 4px; padding: 5px 10px; font-weight: bold;
            }
            QPushButton:hover { background-color: #45475A; color: #89B4FA; }
            QComboBox, QDoubleSpinBox, QSpinBox {
                background-color: #11111B; color: #CDD6F4; border: 1px solid #45475A;
                border-radius: 4px; padding: 3px 6px;
            }
        """)
        self._setup_ui()
        self._populate_hardware_dependent_combos()
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(1000)
        self._refresh_timer.timeout.connect(self._refresh_status)
        self._refresh_timer.start()
        self._refresh_status()

    # ── Construcción de UI ────────────────────────────────────────────────────

    def _setup_ui(self):
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(10)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        container = QtWidgets.QWidget()
        vlo = QtWidgets.QVBoxLayout(container)
        vlo.setSpacing(10)

        vlo.addWidget(self._build_andor_group())
        vlo.addWidget(self._build_shamrock_group())
        vlo.addStretch()
        scroll.setWidget(container)
        outer.addWidget(scroll)

    def _build_andor_group(self) -> QtWidgets.QGroupBox:
        grp = QtWidgets.QGroupBox("📷 Cámara Andor EMCCD (iXon3)")
        grid = QtWidgets.QGridLayout(grp)
        grid.setSpacing(6)
        row = 0

        self.lbl_temp_badge = QtWidgets.QLabel("⚪ Temp: -- °C")
        self.lbl_temp_badge.setStyleSheet("background-color: #11111B; padding: 4px 8px; border-radius: 4px; border: 1px solid #45475A;")
        grid.addWidget(self.lbl_temp_badge, row, 0, 1, 2)
        row += 1

        grid.addWidget(QtWidgets.QLabel("Set T (°C):"), row, 0)
        self.spin_temp = QtWidgets.QSpinBox()
        self.spin_temp.setRange(-100, 25)
        self.spin_temp.setValue(-65)
        self.spin_temp.editingFinished.connect(self._on_temp_changed)
        grid.addWidget(self.spin_temp, row, 1)
        row += 1

        self.btn_cooler = QtWidgets.QPushButton("❄️ Enfriador: ON")
        self.btn_cooler.setCheckable(True)
        self.btn_cooler.setChecked(True)
        self.btn_cooler.setStyleSheet("background-color: #89B4FA; color: #11111B;")
        self.btn_cooler.clicked.connect(self._on_toggle_cooler)
        grid.addWidget(self.btn_cooler, row, 0, 1, 2)
        row += 1

        grid.addWidget(QtWidgets.QLabel("Amplificador:"), row, 0)
        self.cmb_amp = QtWidgets.QComboBox()
        self.cmb_amp.addItem("EMCCD (Multiplicador)", 0)
        self.cmb_amp.addItem("Convencional (Bajo Ruido)", 1)
        self.cmb_amp.currentIndexChanged.connect(self._on_amp_changed)
        grid.addWidget(self.cmb_amp, row, 1)
        row += 1

        grid.addWidget(QtWidgets.QLabel("EM Gain:"), row, 0)
        self.spin_gain = QtWidgets.QSpinBox()
        self.spin_gain.setRange(0, 1000)
        self.spin_gain.setToolTip("Salvaguarda automática del driver: si la exposición supera 1.0 s, se clampea a máx. 5x.")
        self.spin_gain.editingFinished.connect(self._on_gain_changed)
        grid.addWidget(self.spin_gain, row, 1)
        row += 1

        grid.addWidget(QtWidgets.QLabel("Pre-Amp Gain:"), row, 0)
        self.cmb_preamp = QtWidgets.QComboBox()
        self.cmb_preamp.currentIndexChanged.connect(self._on_preamp_changed)
        grid.addWidget(self.cmb_preamp, row, 1)
        row += 1

        grid.addWidget(QtWidgets.QLabel("Velocidad Lectura:"), row, 0)
        self.cmb_hsspeed = QtWidgets.QComboBox()
        self.cmb_hsspeed.currentIndexChanged.connect(self._on_hsspeed_changed)
        grid.addWidget(self.cmb_hsspeed, row, 1)
        row += 1

        grid.addWidget(QtWidgets.QLabel("Exposición (s):"), row, 0)
        self.spin_exposure = QtWidgets.QDoubleSpinBox()
        self.spin_exposure.setDecimals(4)
        self.spin_exposure.setRange(0.0001, 60.0)
        self.spin_exposure.setValue(0.05)
        self.spin_exposure.editingFinished.connect(self._on_exposure_changed)
        grid.addWidget(self.spin_exposure, row, 1)
        row += 1

        grid.addWidget(QtWidgets.QLabel("Obturador Cámara:"), row, 0)
        self.cmb_shutter_mode = QtWidgets.QComboBox()
        self.cmb_shutter_mode.addItems(SHUTTER_MODE_NAMES)
        self.cmb_shutter_mode.currentIndexChanged.connect(self._on_shutter_mode_changed)
        grid.addWidget(self.cmb_shutter_mode, row, 1)

        return grp

    def _build_shamrock_group(self) -> QtWidgets.QGroupBox:
        grp = QtWidgets.QGroupBox("🌈 Espectrógrafo Shamrock 500i")
        grid = QtWidgets.QGridLayout(grp)
        grid.setSpacing(6)
        row = 0

        grid.addWidget(QtWidgets.QLabel("Red de Difracción:"), row, 0)
        self.cmb_grating = QtWidgets.QComboBox()
        self.cmb_grating.addItems(NAME_GRATINGS)
        self.cmb_grating.currentIndexChanged.connect(self._on_grating_changed)
        grid.addWidget(self.cmb_grating, row, 1)
        row += 1

        grid.addWidget(QtWidgets.QLabel("Ranura Entrada (µm):"), row, 0)
        self.spin_slit = QtWidgets.QDoubleSpinBox()
        self.spin_slit.setRange(10.0, 2500.0)
        self.spin_slit.setValue(50.0)
        self.spin_slit.editingFinished.connect(self._on_slit_changed)
        grid.addWidget(self.spin_slit, row, 1)
        row += 1

        grid.addWidget(QtWidgets.QLabel("Puerto Entrada:"), row, 0)
        self.cmb_flipper_in = QtWidgets.QComboBox()
        self.cmb_flipper_in.addItems(NAME_PORTS_IN)
        self.cmb_flipper_in.currentIndexChanged.connect(lambda idx: self.spectrometer.ShamrockSetFlipper(DEVICE, 1, idx))
        grid.addWidget(self.cmb_flipper_in, row, 1)
        row += 1

        grid.addWidget(QtWidgets.QLabel("Puerto Salida:"), row, 0)
        self.cmb_flipper_out = QtWidgets.QComboBox()
        self.cmb_flipper_out.addItems(NAME_PORTS_OUT)
        self.cmb_flipper_out.currentIndexChanged.connect(lambda idx: self.spectrometer.ShamrockSetFlipper(DEVICE, 2, idx))
        grid.addWidget(self.cmb_flipper_out, row, 1)
        row += 1

        self.lbl_wavelength = QtWidgets.QLabel("λ actual: -- nm")
        self.lbl_wavelength.setStyleSheet("background-color: #11111B; padding: 4px 8px; border-radius: 4px; border: 1px solid #45475A;")
        grid.addWidget(self.lbl_wavelength, row, 0, 1, 2)
        row += 1

        grid.addWidget(QtWidgets.QLabel("λ Central (nm):"), row, 0)
        self.edit_wavelength = QtWidgets.QDoubleSpinBox()
        self.edit_wavelength.setRange(0.0, 2000.0)
        self.edit_wavelength.setDecimals(2)
        self.edit_wavelength.setValue(532.0)
        grid.addWidget(self.edit_wavelength, row, 1)
        row += 1

        self.btn_goto_wavelength = QtWidgets.QPushButton("➡️ Ir a λ")
        self.btn_goto_wavelength.clicked.connect(self._on_goto_wavelength)
        grid.addWidget(self.btn_goto_wavelength, row, 0, 1, 2)
        row += 1

        self.btn_zero_order = QtWidgets.QPushButton("🪞 Ir a Orden Cero (0 nm)")
        self.btn_zero_order.setStyleSheet("background-color: #313244; color: #89B4FA; border: 1px solid #89B4FA;")
        self.btn_zero_order.clicked.connect(self._on_goto_zero_order)
        grid.addWidget(self.btn_zero_order, row, 0, 1, 2)

        return grp

    # ── Población dinámica de combos dependientes del hardware ────────────────

    def _populate_hardware_dependent_combos(self):
        self.cmb_preamp.blockSignals(True)
        self.cmb_preamp.clear()
        n_preamp = self.camera.get_number_preamp_gains()
        for i in range(n_preamp):
            _, gain = self.camera.get_preamp_gain(i)
            self.cmb_preamp.addItem(f"{gain:.1f}x", i)
        self.cmb_preamp.blockSignals(False)

        self.cmb_hsspeed.blockSignals(True)
        self.cmb_hsspeed.clear()
        n_hs = self.camera.get_number_hs_speeds()
        for i in range(n_hs):
            _, speed = self.camera.get_hs_speed(i)
            self.cmb_hsspeed.addItem(f"{speed:.1f} MHz", i)
        self.cmb_hsspeed.blockSignals(False)

    # ── Adaptabilidad dinámica por pestaña ────────────────────────────────────

    def set_context(self, tab_index: int) -> None:
        """Adapta la disponibilidad de campos manuales de λ según la pestaña activa. En la
        pestaña de Step & Glue el motor de cosido comanda la red, así que el campo manual y el
        botón 'Ir a λ' quedan inhabilitados (gestionados por la receta), no así Orden Cero,
        que sigue siendo una acción manual explícita del operador en cualquier pestaña."""
        managed_by_recipe = (tab_index == self.step_glue_tab_index)
        self.edit_wavelength.setEnabled(not managed_by_recipe)
        self.btn_goto_wavelength.setEnabled(not managed_by_recipe)

    # ── Handlers Andor ────────────────────────────────────────────────────────

    def _on_temp_changed(self):
        self.camera.set_temperature(float(self.spin_temp.value()))

    def _on_toggle_cooler(self, checked: bool):
        if checked:
            self.camera.cooler_on()
            self.btn_cooler.setText("❄️ Enfriador: ON")
            self.btn_cooler.setStyleSheet("background-color: #89B4FA; color: #11111B;")
        else:
            self.camera.cooler_off()
            self.btn_cooler.setText("❄️ Enfriador: OFF")
            self.btn_cooler.setStyleSheet("background-color: #45475A; color: #A6ADC8;")

    def _on_amp_changed(self, idx: int):
        self.camera.set_output_amplifier(self.cmb_amp.currentData())
        self._populate_hardware_dependent_combos()

    def _on_gain_changed(self):
        self.camera.set_emccd_gain(int(self.spin_gain.value()))

    def _on_preamp_changed(self, idx: int):
        if idx >= 0:
            self.camera.set_preamp_gain(self.cmb_preamp.currentData())

    def _on_hsspeed_changed(self, idx: int):
        if idx >= 0:
            self.camera.set_hs_speed(self.cmb_hsspeed.currentData())
            self._populate_hardware_dependent_combos()

    def _on_exposure_changed(self):
        self.camera.set_exposure_time(float(self.spin_exposure.value()))

    def _on_shutter_mode_changed(self, idx: int):
        if idx >= 0 and hasattr(self.camera, "set_shutter_mode"):
            self.camera.set_shutter_mode(idx)

    # ── Handlers Shamrock ─────────────────────────────────────────────────────

    def _on_grating_changed(self, idx: int):
        grating = idx + 1
        self.spectrometer.ShamrockSetGrating(DEVICE, grating)
        spectroscopy_context.set_spectrograph_position(spectroscopy_context.wavelength_nm, grating)

    def _on_slit_changed(self):
        self.spectrometer.ShamrockSetSlit(DEVICE, 1, float(self.spin_slit.value()))

    def _on_goto_wavelength(self):
        wl = float(self.edit_wavelength.value())
        self.spectrometer.ShamrockSetWavelength(DEVICE, wl)

    def _on_goto_zero_order(self):
        dlg = ZeroOrderSafetyDialog(self.camera, self.spectrometer, parent=self)
        dlg.execute_and_move()
        self._refresh_status()

    # ── Refresco periódico ────────────────────────────────────────────────────

    def _refresh_status(self):
        status, temp = self.camera.get_temperature()
        DRV_TEMP_STABILIZED = 20036
        if status == DRV_TEMP_STABILIZED:
            self.lbl_temp_badge.setText(f"🟢 Temp: {temp:.1f} °C (Estabilizado)")
        else:
            self.lbl_temp_badge.setText(f"🟡 Temp: {temp:.1f} °C (Enfriando…)")

        ret, wl = self.spectrometer.ShamrockGetWavelength(DEVICE)
        moving = " ⏳ Moviendo…" if (hasattr(self.spectrometer, "is_moving") and self.spectrometer.is_moving()) else ""
        self.lbl_wavelength.setText(f"λ actual: {wl:.2f} nm{moving}")
        _, grating = self.spectrometer.ShamrockGetGrating(DEVICE)
        spectroscopy_context.set_spectrograph_position(wl, grating)
