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
from PyQt6.QtCore import QTimer, pyqtSignal

from pyspectrum.drivers import specular_interlock as si
from pyspectrum.drivers.shamrock_driver import (
    DEVICE, NAME_GRATINGS, NAME_PORTS_IN, NAME_PORTS_OUT, GRATING_MIRROR, SHAMROCK_SUCCESS,
)
from pyspectrum.modules.spectroscopy_context import spectroscopy_context
from pyspectrum.modules.zero_order_service import get_zero_order_service

PEACH = "#fab387"          # condición especular: un modo de operación, no una falla (Ronda 3 §1.1-6)
GAIN_RESTORE_PILL_S = 300  # la pastilla "Restituir" desaparece a los 5 min (Ronda 3 §1.4)


SHUTTER_MODE_NAMES = ["Auto (sincronizado)", "Siempre Abierto", "Siempre Cerrado"]


class LeftHardwarePanel(QtWidgets.QWidget):
    """Panel permanente de instrumentación central: cámara Andor EMCCD y espectrógrafo
    Shamrock 500i, con adaptabilidad dinámica de campos según la pestaña activa del shell.

    Todo movimiento del espectrógrafo pasa por el servicio de orden cero (paso 7, DEC-040): el "espejo
    rápido", "Ir a λ" y el combo de red. Un destino especular entra por la secuencia protegida."""

    specularStateChanged = pyqtSignal(str)   # si.FIRST_ORDER / si.SPECULAR / si.UNKNOWN

    def __init__(self, camera: Any, spectrometer: Any, parent=None, step_glue_tab_index: int = 2):
        super().__init__(parent)
        self.camera = camera
        self.spectrometer = spectrometer
        self.step_glue_tab_index = step_glue_tab_index
        self.zero_order = get_zero_order_service(camera, spectrometer)
        self._last_mode: Optional[str] = None
        self._gain_restore_value: Optional[int] = None

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
        spectroscopy_context.slitParametersChanged.connect(self._on_context_slit_changed)
        spectroscopy_context.colormapChanged.connect(self._on_context_colormap_changed)
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
        self.spin_gain.setToolTip("Salvaguarda automática del driver: si la exposición supera 1.0 s, se clampea a máx. 5x.\n"
                                  "En condición especular (orden cero, red espejo) queda bloqueada en 0.")
        self.spin_gain.editingFinished.connect(self._on_gain_changed)
        grid.addWidget(self.spin_gain, row, 1)
        row += 1

        self.lbl_gain_lock = QtWidgets.QLabel("🔒 bloqueada en 0: condición especular")
        self.lbl_gain_lock.setStyleSheet(f"color: {PEACH};")
        self.lbl_gain_lock.hide()
        grid.addWidget(self.lbl_gain_lock, row, 0, 1, 2)
        row += 1

        # Pastilla "Restituir": la ganancia no vuelve sola al salir del orden cero (R4-B-4). Con un
        # láser abierto pide confirmar el notch, que el software no puede sensar (H-05, R4-D-1).
        self.btn_restore_gain = QtWidgets.QPushButton("↺ Restituir")
        self.btn_restore_gain.setToolTip(
            "La ganancia EM no vuelve sola al salir del orden cero (R4-B-4): así un error en la salida\n"
            "nunca deja ganancia alta con la red en especular. Este botón la restituye con un clic.")
        self.btn_restore_gain.clicked.connect(self._on_restore_gain)
        self.btn_restore_gain.hide()
        grid.addWidget(self.btn_restore_gain, row, 0, 1, 2)
        row += 1
        self.chk_notch = QtWidgets.QCheckBox("Notch puesto a la entrada: sí, restituir")
        self.chk_notch.setToolTip("Hay un láser abierto. Si el notch no está, la línea láser dispersada cae\n"
                                  "sobre una columna con ganancia EM alta. El software no puede leer el notch.")
        self.chk_notch.hide()
        grid.addWidget(self.chk_notch, row, 0, 1, 2)
        row += 1
        self._restore_timer = QTimer(self)
        self._restore_timer.setSingleShot(True)
        self._restore_timer.timeout.connect(self._hide_restore_pill)

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
        row += 1

        grid.addWidget(QtWidgets.QLabel("Paleta 2D:"), row, 0)
        self.cmb_colormap = QtWidgets.QComboBox()
        self.cmb_colormap.addItems(["Viridis", "Inferno", "Greys", "Jet"])
        self.cmb_colormap.currentTextChanged.connect(self._on_colormap_changed)
        self.cmb_colormap.setToolTip("Mapa de falso color para visualizadores 2D (Exploración e Inspector Raman).")
        grid.addWidget(self.cmb_colormap, row, 1)

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
        self.edit_wavelength.valueChanged.connect(lambda _v: self._update_destination())
        grid.addWidget(self.edit_wavelength, row, 1)
        row += 1

        # Línea derivada (Ronda 3 §3.3): se recalcula mientras se escribe; el umbral es el del motor.
        self.lbl_destination = QtWidgets.QLabel("")
        self.lbl_destination.setWordWrap(True)
        self.lbl_destination.setToolTip(
            "Condición especular: la red refleja la luz hacia el detector sin dispersarla (orden cero, red\n"
            "espejo, o una λc tan chica que el orden cero entra al chip).\n"
            "Umbral = (1 + 0.10) · W/2: 56.7 nm con 150 l/mm y 6.4 nm con 1200 l/mm (PROVISORIO, BANCO-42).\n"
            "En especular la ganancia EM queda bloqueada en 0.")
        grid.addWidget(self.lbl_destination, row, 0, 1, 2)
        row += 1

        self.btn_goto_wavelength = QtWidgets.QPushButton("➡️ Ir a λ")
        self.btn_goto_wavelength.clicked.connect(self._on_goto_wavelength)
        grid.addWidget(self.btn_goto_wavelength, row, 0, 1, 2)
        row += 1

        grid.addWidget(self._build_quick_mirror(), row, 0, 1, 2)
        return grp

    def _build_quick_mirror(self) -> QtWidgets.QGroupBox:
        """Espejo rápido (Ronda 3 §1.4): un único control con dos estados, sin diálogo."""
        box = QtWidgets.QGroupBox("🪞 Espejo rápido")
        lo = QtWidgets.QVBoxLayout(box)
        lo.setSpacing(4)
        self.lbl_specular_state = QtWidgets.QLabel("Estado: —")
        self.lbl_specular_state.setWordWrap(True)
        lo.addWidget(self.lbl_specular_state)

        self.btn_zero_order = QtWidgets.QPushButton("🪞 Orden cero (red actual)")
        self.btn_zero_order.setToolTip(
            "Lleva la red a orden cero para ver la muestra o centrar el láser en la ranura.\n"
            "Antes de girar: detiene la cámara, fija la ganancia EM en 0 y la relee, fija la exposición de\n"
            "orden cero y cierra todos los obturadores (confirmado). Si algo no se confirma, no gira.\n"
            "Después reanuda el Live si estaba corriendo. Podés abrir los obturadores que necesites.\n"
            "Ctrl+0 entra y vuelve.")
        self.btn_zero_order.clicked.connect(self._on_goto_zero_order)
        lo.addWidget(self.btn_zero_order)

        self.btn_mirror = QtWidgets.QPushButton("Red espejo (posición 3 de la torreta)")
        self.btn_mirror.setToolTip("Entra a condición especular con la red espejo, por la misma secuencia protegida.")
        self.btn_mirror.clicked.connect(lambda: self._run_specular(lambda: self.zero_order.enter_specular("mirror"),
                                                                   "red espejo"))
        lo.addWidget(self.btn_mirror)

        self.btn_reread = QtWidgets.QPushButton("🔄 Releer estado del Shamrock")
        self.btn_reread.clicked.connect(self._refresh_status)
        self.btn_reread.hide()
        lo.addWidget(self.btn_reread)

        self.lbl_zo_steps = QtWidgets.QLabel("")
        self.lbl_zo_steps.setWordWrap(True)
        self.lbl_zo_steps.setMinimumHeight(18)   # espacio reservado: no corre los controles de abajo (H-30)
        self.lbl_zo_steps.setStyleSheet("font-size: 8.5pt;")
        lo.addWidget(self.lbl_zo_steps)

        self.lbl_light = QtWidgets.QLabel("")
        self.lbl_light.setWordWrap(True)
        lo.addWidget(self.lbl_light)
        return box

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

    def apply_camera_baseline_report(self, report) -> None:
        """Muestra el setpoint y el enfriador que el arranque ENVIÓ (paso 8, DEC-040), en lugar de los
        valores por defecto de los widgets, que decían −65 °C y "ON" sin haber enviado nada. El panel
        completo con las marcas leído/enviado/falló es el rediseño de la Ronda 3."""
        temp = report.item("temperature_c") if report is not None else None
        if temp is not None and temp.outcome in ("OK", "SENT"):
            self.spin_temp.blockSignals(True)
            self.spin_temp.setValue(int(temp.requested))
            self.spin_temp.blockSignals(False)
        cooler = report.item("cooler_on") if report is not None else None
        on = cooler is not None and cooler.outcome == "OK"
        self.btn_cooler.blockSignals(True)
        self.btn_cooler.setChecked(on)
        self.btn_cooler.blockSignals(False)
        if on:
            self.btn_cooler.setText("❄️ Enfriador: ON")
            self.btn_cooler.setStyleSheet("background-color: #89B4FA; color: #11111B;")
        else:
            self.btn_cooler.setText("❄️ Enfriador: sin confirmar" if cooler is not None else "❄️ Enfriador: OFF")
            self.btn_cooler.setStyleSheet("background-color: #45475A; color: #A6ADC8;")

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
        requested = int(self.spin_gain.value())
        ret = self.camera.set_emccd_gain(requested)
        if ret != 20002 and requested > 0 and si.get_interlock().is_specular_or_unknown():
            # El driver la rechazó por condición especular: el spinbox vuelve a mostrar la real
            self.spin_gain.blockSignals(True)
            self.spin_gain.setValue(0)
            self.spin_gain.blockSignals(False)
        self._hide_restore_pill()

    def _on_restore_gain(self):
        value = self._gain_restore_value
        if value is None:
            return
        if self.zero_order.gain_restore_needs_notch_confirmation() and not self.chk_notch.isChecked():
            self.chk_notch.show()
            self.lbl_zo_steps.setText("Hay un láser abierto: confirmá que el notch está puesto antes de restituir.")
            return
        if self.camera.set_emccd_gain(value) == 20002:
            self.spin_gain.blockSignals(True)
            self.spin_gain.setValue(value)
            self.spin_gain.blockSignals(False)
            self._hide_restore_pill()

    def _hide_restore_pill(self):
        self._gain_restore_value = None
        self.btn_restore_gain.hide()
        self.chk_notch.hide()
        self.chk_notch.setChecked(False)
        self._restore_timer.stop()

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

    def _on_colormap_changed(self, name: str):
        spectroscopy_context.set_colormap(name)

    def _on_context_colormap_changed(self, name: str):
        if self.cmb_colormap.currentText() != name:
            self.cmb_colormap.blockSignals(True)
            self.cmb_colormap.setCurrentText(name)
            self.cmb_colormap.blockSignals(False)

    def _on_context_slit_changed(self, width_um: float, center_px: float, zero_pos: int):
        if abs(self.spin_slit.value() - width_um) > 0.05:
            self.spin_slit.blockSignals(True)
            self.spin_slit.setValue(width_um)
            self.spin_slit.blockSignals(False)

    # ── Handlers Shamrock ─────────────────────────────────────────────────────

    def _on_grating_changed(self, idx: int):
        grating = idx + 1
        if grating == GRATING_MIRROR:
            self._run_specular(lambda: self.zero_order.enter_specular("mirror"), "red espejo")
        else:
            ret, wl = self.spectrometer.ShamrockGetWavelength(DEVICE)
            wl = float(wl) if ret == SHAMROCK_SUCCESS else float(self.edit_wavelength.value())
            self._run_specular(lambda: self.zero_order.move(grating, wl), f"red {grating}")
        self._update_destination()

    def _on_slit_changed(self):
        val = float(self.spin_slit.value())
        self.spectrometer.ShamrockSetSlit(DEVICE, 1, val)
        spectroscopy_context.set_slit_parameters(slit_width_um=val)

    def _on_goto_wavelength(self):
        wl = float(self.edit_wavelength.value())
        grating = self.cmb_grating.currentIndex() + 1
        self._run_specular(lambda: self.zero_order.move(grating, wl), f"λc {wl:.2f} nm")

    def _on_goto_zero_order(self):
        """Ctrl+0 y el botón: entra desde primer orden, vuelve desde especular. En estado desconocido no
        mueve nada: relee (H-11c)."""
        mode = self.zero_order.refresh_state()
        if mode == si.FIRST_ORDER:
            self._run_specular(lambda: self.zero_order.enter_specular("zero_order"), "orden cero")
        elif mode == si.SPECULAR:
            self._run_specular(self.zero_order.leave_specular, "volver a primer orden")
        else:
            self.lbl_zo_steps.setText("Estado del Shamrock desconocido: no se mueve nada. Releé el estado.")
            self._apply_specular_ui(mode)

    def _run_specular(self, action, what: str):
        gain_before = self.zero_order.gain_before_specular
        was = si.get_interlock().mode
        res = action()
        self._show_result(res, what)
        # Pastilla "Restituir" al volver a primer orden con una ganancia previa > 0
        if (res.ok and was != si.FIRST_ORDER and res.mode == si.FIRST_ORDER
                and gain_before is not None and gain_before > 0):
            self._offer_gain_restore(int(gain_before))
        self._sync_camera_widgets()
        self._refresh_status()

    def _show_result(self, res, what: str):
        lines = [("✓ " if st.ok else "✗ ") + st.label + (f" ({st.detail})" if st.detail else "")
                 for st in res.steps]
        if res.ok:
            text = f"✅ {what}: " + " · ".join(lines)
            color = "#A6E3A1"
        else:
            state = " · ".join(f"{k}: {v}" for k, v in res.final_state.items() if v)
            text = f"⛔ {what}: {res.detail}\n" + "\n".join(lines) + (f"\n{state}" if state else "")
            color = "#F38BA8"
        self.lbl_zo_steps.setText(text)
        self.lbl_zo_steps.setStyleSheet(f"font-size: 8.5pt; color: {color};")

    def _offer_gain_restore(self, value: int):
        self._gain_restore_value = value
        names = self.zero_order._open_shutters()
        suffix = f" · {', '.join(names)} abierto" if names else ""
        self.btn_restore_gain.setText(f"↺ Restituir {value} DAC (antes del orden cero){suffix}")
        self.btn_restore_gain.show()
        self.chk_notch.setChecked(False)
        self.chk_notch.setVisible(bool(names))
        self._restore_timer.start(GAIN_RESTORE_PILL_S * 1000)

    def _sync_camera_widgets(self):
        """Tras entrar o volver: la exposición y la ganancia que muestra el panel son las de la cámara."""
        try:
            exp = float(self.camera.get_exposure_time())
            self.spin_exposure.blockSignals(True)
            self.spin_exposure.setValue(exp)
            self.spin_exposure.blockSignals(False)
        except Exception:
            pass
        g = self.camera.get_emccd_gain()
        ret, gain = (g[0], g[1]) if isinstance(g, (tuple, list)) else (20002, g)
        if ret == 20002:
            self.spin_gain.blockSignals(True)
            self.spin_gain.setValue(int(gain))
            self.spin_gain.blockSignals(False)

    def _update_destination(self):
        grating = self.cmb_grating.currentIndex() + 1
        wl = float(self.edit_wavelength.value())
        mode = si.classify(grating, wl)
        if mode == si.FIRST_ORDER:
            thr = si.specular_threshold_nm(grating)
            self.lbl_destination.setText(f"destino: primer orden · umbral de la red {grating}: {thr:.1f} nm")
            self.lbl_destination.setStyleSheet("color: #A6ADC8;")
            self.btn_goto_wavelength.setText("➡️ Ir a λ")
        else:
            why = "red espejo" if grating == GRATING_MIRROR else f"λc < {si.specular_threshold_nm(grating):.1f} nm"
            self.lbl_destination.setText(f"destino: ESPECULAR ({why}): se entra por el espejo rápido")
            self.lbl_destination.setStyleSheet(f"color: {PEACH}; font-weight: bold;")
            self.btn_goto_wavelength.setText("➡️ Ir (espejo rápido)")

    def _apply_specular_ui(self, mode: str):
        specular = mode != si.FIRST_ORDER
        self.spin_gain.setEnabled(not specular)
        self.lbl_gain_lock.setVisible(specular)
        self.btn_reread.setVisible(mode == si.UNKNOWN)
        self.btn_mirror.setEnabled(mode == si.FIRST_ORDER)
        if mode == si.FIRST_ORDER:
            self.lbl_specular_state.setText("Estado: PRIMER ORDEN")
            self.lbl_specular_state.setStyleSheet("color: #A6ADC8;")
            self.btn_zero_order.setText("🪞 Orden cero (red actual)")
        elif mode == si.SPECULAR:
            self.lbl_specular_state.setText("ORDEN CERO · sin dispersión · EM 0 bloqueada")
            self.lbl_specular_state.setStyleSheet(f"color: #181825; background-color: {PEACH}; "
                                                  "padding: 3px 6px; border-radius: 4px; font-weight: bold;")
            target = self.zero_order.return_target
            self.btn_zero_order.setText(f"↩ Volver a red {target[0]} · {target[1]:.2f} nm" if target
                                        else "↩ Volver (indicá red y λ en λ Central e Ir)")
        else:
            self.lbl_specular_state.setText("ORDEN CERO (estado del Shamrock desconocido) · EM 0 bloqueada")
            self.lbl_specular_state.setStyleSheet(f"color: #181825; background-color: {PEACH}; "
                                                  "padding: 3px 6px; border-radius: 4px; font-weight: bold;")
            self.btn_zero_order.setText("🪞 Orden cero (estado desconocido: releer)")
        if specular:
            self.spin_gain.blockSignals(True)
            self.spin_gain.setValue(0)
            self.spin_gain.blockSignals(False)
            names, warning = self.zero_order.specular_light_report()
            light = (f"Obturadores abiertos en especular: {', '.join(names)}" if names
                     else "Obturadores cerrados (abrilos a voluntad desde [Obturadores])")
            if warning:
                light += f"\n⚠️ {warning}"
            self.lbl_light.setText(light)
            self.lbl_light.setStyleSheet(f"color: {'#F9E2AF' if warning else '#A6ADC8'};")
            self.lbl_light.show()
        else:
            self.lbl_light.hide()
        if mode != self._last_mode:
            self._last_mode = mode
            self.specularStateChanged.emit(mode)

    # ── Refresco periódico ────────────────────────────────────────────────────

    def _refresh_status(self):
        status, temp = self.camera.get_temperature()
        DRV_TEMP_STABILIZED = 20036
        DRV_ACQUIRING = 20072  # el SDK no lee la temperatura mientras adquiere: es la última lectura
        if status == DRV_ACQUIRING:
            last = f"{temp:.1f} °C" if temp == temp else "sin lectura"
            self.lbl_temp_badge.setText(f"⏸ Temp: {last} (última lectura; adquiriendo)")
        elif status == DRV_TEMP_STABILIZED:
            self.lbl_temp_badge.setText(f"🟢 Temp: {temp:.1f} °C (Estabilizado)")
        else:
            self.lbl_temp_badge.setText(f"🟡 Temp: {temp:.1f} °C (Enfriando…)")

        ret, wl = self.spectrometer.ShamrockGetWavelength(DEVICE)
        moving = " ⏳ Moviendo…" if (hasattr(self.spectrometer, "is_moving") and self.spectrometer.is_moving()) else ""
        self.lbl_wavelength.setText(f"λ actual: {wl:.2f} nm{moving}" if ret == SHAMROCK_SUCCESS
                                    else f"λ actual: sin lectura (código {ret})")
        ret_g, grating = self.spectrometer.ShamrockGetGrating(DEVICE)
        if ret_g == SHAMROCK_SUCCESS and 1 <= int(grating) <= self.cmb_grating.count():
            self.cmb_grating.blockSignals(True)
            self.cmb_grating.setCurrentIndex(int(grating) - 1)
            self.cmb_grating.blockSignals(False)
        spectroscopy_context.set_spectrograph_position(wl, grating)
        # La condición especular se publica desde la lectura: una lectura fallida es "desconocido"
        # y bloquea la ganancia (falla cerrada, R2-inst §2.1-4).
        self._apply_specular_ui(self.zero_order.refresh_state())
        self._update_destination()
