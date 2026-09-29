# -*- coding: utf-8 -*-
"""
left_hardware_panel.py — Panel izquierdo permanente (Andor + Shamrock)
PySpectrum 3.0 — UNSAM Nanofotónica

Paso 8 del bloque A (Ronda 3 §1.3, §2.1-2.2, DEC-040). El panel tiene **dos columnas**:
- **Izquierda, lo leído:** sale de la instantánea de `SpectrometerStateService`. Cada valor lleva su marca:
  - [L] leído, con la edad si pasa de 3 s;
  - [E] enviado: el SDK no tiene getter;
  - [! código] falló;
  - [?] sin leer;
  - [X] no conectado.
  Un valor viejo nunca se muestra como leído.
- **Derecha, lo que el operador pide:** nunca actúa al cambiar. Hace falta [Aplicar], [Fijar] o [Ir] (G-04,
  H-27), y la rueda del ratón no cambia un control sin foco (H-10).

Por dónde pasa cada pedido:
- **Cámara** (setpoint, enfriador, ventilador, HS): `CameraControlService`, que verifica y aplica entre
  adquisiciones (D-13).
- **Ganancia y exposición:** los drivers, con el interlock especular (paso 7).
- **Red y λ:** el servicio de orden cero (paso 7): un destino especular entra por el espejo rápido.
- **Ranura y puertos:** con relectura (D-12). Los movimientos todavía corren en el hilo de la GUI. El
  `SpectrographWorker` en su propio hilo queda para después de BANCO-39, que dice si `SetGrating` y
  `SetWavelength` bloquean.
"""
from __future__ import annotations

import math
from typing import Any, Optional

from PyQt6 import QtCore, QtWidgets
from PyQt6.QtCore import QTimer, pyqtSignal

from pyspectrum.drivers import specular_interlock as si
from pyspectrum.drivers.shamrock_driver import (
    DEVICE, NAME_GRATINGS, NAME_PORTS_IN, NAME_PORTS_OUT, GRATING_MIRROR, SHAMROCK_SUCCESS,
)
from pyspectrum.modules.spectroscopy_context import spectroscopy_context
from pyspectrum.modules.zero_order_service import get_zero_order_service
from pyspectrum.services.camera_control import CameraControlService, ControlState
from pyspectrum.services.spectrometer_state import (
    ReadStatus, SpectrometerStateService, get_sent_registry,
)

PEACH = "#fab387"          # condición especular: un modo de operación, no una falla (Ronda 3 §1.1-6)
GAIN_RESTORE_PILL_S = 300  # la pastilla "Restituir" desaparece a los 5 min (Ronda 3 §1.4)
TEXT_SECONDARY = "#a6adc8"  # contraste AA (H-22)
RED, GREEN, BLUE = "#f38ba8", "#a6e3a1", "#74c7ec"
_DRV_SUCCESS = 20002

SHUTTER_MODE_NAMES = ["Auto (sincronizado)", "Siempre Abierto", "Siempre Cerrado"]
READ_MODE_NAMES = {0: "FVB", 1: "Multi-Track", 2: "Random-Track", 3: "Single-Track", 4: "Image"}
ACQ_MODE_NAMES = {1: "Single Scan", 2: "Accumulate", 3: "Kinetics", 4: "Fast Kinetics", 5: "Run till abort"}
FAN_NAMES = {0: "high", 1: "low", 2: "off"}


class _NoWheelUnlessFocused(QtCore.QObject):
    """La rueda del ratón no cambia un spinbox ni un combo de hardware sin foco (G-04, H-10)."""

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.Type.Wheel and not obj.hasFocus():
            event.ignore()
            return True
        return super().eventFilter(obj, event)


class LeftHardwarePanel(QtWidgets.QWidget):
    """Panel permanente de la cámara Andor EMCCD y del espectrógrafo Shamrock 500i."""

    specularStateChanged = pyqtSignal(str)   # si.FIRST_ORDER / si.SPECULAR / si.UNKNOWN

    def __init__(self, camera: Any, spectrometer: Any, parent=None, step_glue_tab_index: int = 2):
        super().__init__(parent)
        self.camera = camera
        self.spectrometer = spectrometer
        self.step_glue_tab_index = step_glue_tab_index
        self.zero_order = get_zero_order_service(camera, spectrometer)
        self.control = CameraControlService(camera, get_sent_registry())
        self.state_service = SpectrometerStateService(camera, spectrometer, self.control.sent)
        self.snapshot = None
        self._last_mode: Optional[str] = None
        self._gain_restore_value: Optional[int] = None
        self._grating_dirty = False
        self._wheel_filter = _NoWheelUnlessFocused(self)

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
            QPushButton:disabled { color: #6c7086; }
            QComboBox, QDoubleSpinBox, QSpinBox {
                background-color: #11111B; color: #CDD6F4; border: 1px solid #45475A;
                border-radius: 4px; padding: 3px 6px;
            }
        """)
        self._setup_ui()
        self._populate_hardware_dependent_combos()
        for w in (self.spin_temp, self.spin_gain, self.spin_exposure, self.cmb_hsspeed, self.cmb_amp,
                  self.cmb_shutter_mode, self.cmb_grating, self.edit_wavelength, self.spin_slit,
                  self.cmb_flipper_in, self.cmb_flipper_out, self.cmb_colormap):
            w.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
            w.installEventFilter(self._wheel_filter)
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

    @staticmethod
    def _read_label(text: str = "[?]") -> QtWidgets.QLabel:
        lbl = QtWidgets.QLabel(text)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color: {TEXT_SECONDARY};")
        return lbl

    def _build_andor_group(self) -> QtWidgets.QGroupBox:
        grp = QtWidgets.QGroupBox("📷 Cámara Andor EMCCD (iXon3)")
        self.andor_group = grp
        grid = QtWidgets.QGridLayout(grp)
        grid.setSpacing(6)
        row = 0

        self.lbl_camera_connection = self._read_label("[?] cámara")
        grid.addWidget(self.lbl_camera_connection, row, 0, 1, 3)
        row += 1

        # Temperatura: lo leído, el setpoint enviado y el pedido con [Aplicar]
        self.lbl_temp_badge = self._read_label("[?] Temp: sin leer")
        self.lbl_temp_badge.setToolTip(
            "Temperatura del sensor, en °C, con el estado que devuelve GetTemperature: estabilizada · enfriando,\n"
            "todavía no llega · llegó pero no se estabilizó · deriva · enfriador apagado · adquiriendo (el SDK no\n"
            "la lee; se muestra el último valor sólo como referencia).\n"
            "Setpoint de arranque: −60 °C (R4-A-6). Si no llega en ~15 min con el ventilador en low, probá high.")
        grid.addWidget(self.lbl_temp_badge, row, 0, 1, 3)
        row += 1
        self.lbl_setpoint = self._read_label("setpoint [?]")
        grid.addWidget(self.lbl_setpoint, row, 0)
        self.spin_temp = QtWidgets.QSpinBox()
        self.spin_temp.setSuffix(" °C")
        self.spin_temp.setRange(-100, 25)
        self.spin_temp.setValue(-60)
        self.spin_temp.setToolTip("Setpoint pedido. El rango se lee de la cámara (GetTemperatureRange). "
                                  "Arranque: −60 °C (R4-A-6).")
        grid.addWidget(self.spin_temp, row, 1)
        self.btn_apply_temp = QtWidgets.QPushButton("Aplicar")
        self.btn_apply_temp.clicked.connect(self._on_apply_temperature)
        grid.addWidget(self.btn_apply_temp, row, 2)
        row += 1

        # Enfriador: refleja IsCoolerOn; apagarlo pide confirmación (H-27)
        self.lbl_cooler_read = self._read_label("Enfriador [?]")
        grid.addWidget(self.lbl_cooler_read, row, 0, 1, 2)
        self.btn_cooler = QtWidgets.QPushButton("Enfriador…")
        self.btn_cooler.clicked.connect(self._on_toggle_cooler)
        grid.addWidget(self.btn_cooler, row, 2)
        row += 1

        # Ventilador: low / high, sin "off" (R4-A-6; SDK p. 273)
        self.lbl_fan = self._read_label("Ventilador [?]")
        grid.addWidget(self.lbl_fan, row, 0)
        fan_box = QtWidgets.QHBoxLayout()
        self.rb_fan_low = QtWidgets.QRadioButton("low")
        self.rb_fan_high = QtWidgets.QRadioButton("high")
        self.rb_fan_low.setChecked(True)
        for rb in (self.rb_fan_low, self.rb_fan_high):
            rb.setToolTip("low (arranque, R4-A-6) o high (= \"full\" del SDK). \"Apagado\" no se ofrece: con el\n"
                          "sensor frío el manual lo permite sólo por períodos cortos. No se puede cambiar\n"
                          "durante una adquisición: se aplica al terminar.")
            fan_box.addWidget(rb)
        self.rb_fan_low.clicked.connect(lambda: self._on_fan("low"))
        self.rb_fan_high.clicked.connect(lambda: self._on_fan("high"))
        grid.addLayout(fan_box, row, 1, 1, 2)
        row += 1

        grid.addWidget(QtWidgets.QLabel("Amplificador:"), row, 0)
        self.cmb_amp = QtWidgets.QComboBox()
        self.cmb_amp.addItem("EMCCD (Multiplicador)", 0)
        self.cmb_amp.addItem("Convencional (Bajo Ruido)", 1)
        grid.addWidget(self.cmb_amp, row, 1)
        self.btn_apply_amp = QtWidgets.QPushButton("Aplicar")
        self.btn_apply_amp.clicked.connect(self._on_apply_amp)
        grid.addWidget(self.btn_apply_amp, row, 2)
        row += 1

        # Ganancia EM: pedido + [Aplicar]; en especular queda bloqueada en 0 (paso 7)
        self.lbl_gain_read = self._read_label("Ganancia EM [?]")
        grid.addWidget(self.lbl_gain_read, row, 0)
        self.spin_gain = QtWidgets.QSpinBox()
        self.spin_gain.setRange(0, 255)
        self.spin_gain.setSuffix(" DAC")
        self.spin_gain.setToolTip("Ganancia del registro multiplicador, en unidades DAC (modo 0), no en \"×\". El rango\n"
                                  "se lee de la cámara (GetEMGainRange). En condición especular queda bloqueada en 0.")
        grid.addWidget(self.spin_gain, row, 1)
        self.btn_apply_gain = QtWidgets.QPushButton("Aplicar")
        self.btn_apply_gain.clicked.connect(self._on_gain_changed)
        grid.addWidget(self.btn_apply_gain, row, 2)
        row += 1

        self.lbl_gain_lock = QtWidgets.QLabel("🔒 bloqueada en 0: condición especular")
        self.lbl_gain_lock.setStyleSheet(f"color: {PEACH};")
        self.lbl_gain_lock.hide()
        grid.addWidget(self.lbl_gain_lock, row, 0, 1, 3)
        row += 1

        # Pastilla "Restituir": la ganancia no vuelve sola al salir del orden cero (R4-B-4). Con un
        # láser abierto pide confirmar el notch, que el software no puede sensar (H-05, R4-D-1).
        self.btn_restore_gain = QtWidgets.QPushButton("↺ Restituir")
        self.btn_restore_gain.setToolTip(
            "La ganancia EM no vuelve sola al salir del orden cero (R4-B-4): así un error en la salida\n"
            "nunca deja ganancia alta con la red en especular. Este botón la restituye con un clic.")
        self.btn_restore_gain.clicked.connect(self._on_restore_gain)
        self.btn_restore_gain.hide()
        grid.addWidget(self.btn_restore_gain, row, 0, 1, 3)
        row += 1
        self.chk_notch = QtWidgets.QCheckBox("Notch puesto a la entrada: sí, restituir")
        self.chk_notch.setToolTip("Hay un láser abierto. Si el notch no está, la línea láser dispersada cae\n"
                                  "sobre una columna con ganancia EM alta. El software no puede leer el notch.")
        self.chk_notch.hide()
        grid.addWidget(self.chk_notch, row, 0, 1, 3)
        row += 1
        self._restore_timer = QTimer(self)
        self._restore_timer.setSingleShot(True)
        self._restore_timer.timeout.connect(self._hide_restore_pill)

        # Exposición: la real (GetAcquisitionTimings) y el pedido
        self.lbl_exposure_read = self._read_label("Exposición [?]")
        grid.addWidget(self.lbl_exposure_read, row, 0)
        self.spin_exposure = QtWidgets.QDoubleSpinBox()
        self.spin_exposure.setDecimals(4)
        self.spin_exposure.setRange(0.0001, 60.0)
        self.spin_exposure.setValue(0.05)
        self.spin_exposure.setSuffix(" s")
        self.spin_exposure.setToolTip("Tiempo de integración pedido; a la izquierda, el real que informa la cámara.\n"
                                      "Tope del driver: 60 s (R4-B-9). Las rutinas aceptan hasta 10 s (R4-4).")
        grid.addWidget(self.spin_exposure, row, 1)
        self.btn_apply_exposure = QtWidgets.QPushButton("Aplicar")
        self.btn_apply_exposure.clicked.connect(self._on_exposure_changed)
        grid.addWidget(self.btn_apply_exposure, row, 2)
        row += 1

        # Lectura y velocidades: sin getter en el SDK → [E] (D-15, H-09)
        self.lbl_modes = self._read_label("Lectura [?]")
        self.lbl_modes.setToolTip("[L] leído del equipo · [E] enviado: el SDK no permite leerlo, sólo consta que el\n"
                                  "equipo aceptó el valor · [!] falló · [?] sin leer · [X] no conectado.\n"
                                  "Los modos de lectura, de adquisición y de ganancia, el ventilador y los índices\n"
                                  "de VS y HS no tienen función de lectura en el SDK2.")
        grid.addWidget(self.lbl_modes, row, 0, 1, 3)
        row += 1
        self.lbl_speeds = self._read_label("Velocidades [?]")
        self.lbl_speeds.setToolTip(self.lbl_modes.toolTip())
        grid.addWidget(self.lbl_speeds, row, 0, 1, 3)
        row += 1
        grid.addWidget(QtWidgets.QLabel("Velocidad HS:"), row, 0)
        self.cmb_hsspeed = QtWidgets.QComboBox()
        self.cmb_hsspeed.setToolTip("Velocidad de lectura del registro, de la tabla del equipo. 13 MHz por defecto\n"
                                    "(R4-B-8): el menor ruido de lectura de las tres, todas de 14 bit.")
        grid.addWidget(self.cmb_hsspeed, row, 1)
        self.btn_apply_hs = QtWidgets.QPushButton("Aplicar")
        self.btn_apply_hs.clicked.connect(self._on_apply_hs)
        grid.addWidget(self.btn_apply_hs, row, 2)
        row += 1

        grid.addWidget(QtWidgets.QLabel("Obturador:"), row, 0)
        self.cmb_shutter_mode = QtWidgets.QComboBox()
        self.cmb_shutter_mode.addItems(SHUTTER_MODE_NAMES)
        self.cmb_shutter_mode.setToolTip("Modo del obturador que la cámara comanda por TTL (el del Shamrock, BANCO-22).")
        grid.addWidget(self.cmb_shutter_mode, row, 1)
        self.btn_apply_shutter = QtWidgets.QPushButton("Aplicar")
        self.btn_apply_shutter.clicked.connect(self._on_apply_shutter_mode)
        grid.addWidget(self.btn_apply_shutter, row, 2)
        row += 1

        grid.addWidget(QtWidgets.QLabel("Paleta 2D:"), row, 0)
        self.cmb_colormap = QtWidgets.QComboBox()
        self.cmb_colormap.addItems(["Viridis", "Inferno", "Greys", "Jet"])
        self.cmb_colormap.currentTextChanged.connect(self._on_colormap_changed)
        self.cmb_colormap.setToolTip("Mapa de falso color para visualizadores 2D (Exploración e Inspector Raman).")
        grid.addWidget(self.cmb_colormap, row, 1, 1, 2)
        return grp

    def _build_shamrock_group(self) -> QtWidgets.QGroupBox:
        grp = QtWidgets.QGroupBox("🌈 Espectrógrafo Shamrock 500i")
        self.shamrock_group = grp
        grid = QtWidgets.QGridLayout(grp)
        grid.setSpacing(6)
        row = 0

        self.lbl_grating_read = self._read_label("Red [?]")
        grid.addWidget(self.lbl_grating_read, row, 0, 1, 2)
        row += 1
        grid.addWidget(QtWidgets.QLabel("Red pedida:"), row, 0)
        self.cmb_grating = QtWidgets.QComboBox()
        self.cmb_grating.addItems(NAME_GRATINGS)
        self.cmb_grating.setToolTip("Red pedida. No se mueve al elegirla: se mueve con [Ir] (G-04).")
        self.cmb_grating.currentIndexChanged.connect(self._on_grating_changed)
        grid.addWidget(self.cmb_grating, row, 1)
        row += 1

        self.lbl_wavelength = self._read_label("λc (SDK) [?]")
        self.lbl_wavelength.setToolTip(
            "Longitud de onda central que informa el Shamrock (ShamrockGetWavelength), en nm. Es la λ que el SDK\n"
            "calcula para la posición ordenada: el motor es paso a paso, sin sensor de ángulo.")
        grid.addWidget(self.lbl_wavelength, row, 0, 1, 2)
        row += 1
        grid.addWidget(QtWidgets.QLabel("λc pedida (nm):"), row, 0)
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

        # Ranura: lo leído (GetAutoSlitWidth) y el pedido con [Fijar]
        self.lbl_slit_read = self._read_label("Ranura [?]")
        grid.addWidget(self.lbl_slit_read, row, 0, 1, 2)
        row += 1
        slit_row = QtWidgets.QHBoxLayout()
        self.spin_slit = QtWidgets.QDoubleSpinBox()
        self.spin_slit.setRange(10.0, 2500.0)
        self.spin_slit.setValue(50.0)
        self.spin_slit.setSuffix(" µm")
        slit_row.addWidget(self.spin_slit)
        self.btn_set_slit = QtWidgets.QPushButton("Fijar")
        self.btn_set_slit.clicked.connect(self._on_slit_changed)
        slit_row.addWidget(self.btn_set_slit)
        grid.addLayout(slit_row, row, 0, 1, 2)
        row += 1

        # Puertos: lo leído (GetFlipperMirror) y el pedido con [Fijar]
        self.lbl_ports_read = self._read_label("Puertos [?]")
        grid.addWidget(self.lbl_ports_read, row, 0, 1, 2)
        row += 1
        grid.addWidget(QtWidgets.QLabel("Entrada:"), row, 0)
        self.cmb_flipper_in = QtWidgets.QComboBox()
        self.cmb_flipper_in.addItems(NAME_PORTS_IN)
        grid.addWidget(self.cmb_flipper_in, row, 1)
        row += 1
        grid.addWidget(QtWidgets.QLabel("Salida:"), row, 0)
        self.cmb_flipper_out = QtWidgets.QComboBox()
        self.cmb_flipper_out.addItems(NAME_PORTS_OUT)
        grid.addWidget(self.cmb_flipper_out, row, 1)
        row += 1
        self.btn_set_ports = QtWidgets.QPushButton("Fijar puertos")
        self.btn_set_ports.clicked.connect(self._on_set_ports)
        grid.addWidget(self.btn_set_ports, row, 0, 1, 2)
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
        self.cmb_hsspeed.blockSignals(True)
        self.cmb_hsspeed.clear()
        if getattr(self.camera, "available", True):
            try:
                for mhz in self.control.hs_table():
                    self.cmb_hsspeed.addItem(f"{mhz:g} MHz", mhz)
            except Exception as e:
                print(f"[Panel] No se pudo leer la tabla de HS: {e}")
            rng = self.camera.get_temperature_range() if hasattr(self.camera, "get_temperature_range") else None
            if rng and rng[0] == _DRV_SUCCESS:
                self.spin_temp.setRange(int(rng[1]), int(rng[2]))
            grng = self.camera.get_em_gain_range() if hasattr(self.camera, "get_em_gain_range") else None
            if grng and grng[0] == _DRV_SUCCESS:
                self.spin_gain.setRange(int(grng[1]), int(grng[2]))
        self.cmb_hsspeed.blockSignals(False)

    # ── Adaptabilidad dinámica por pestaña ────────────────────────────────────

    def set_context(self, tab_index: int) -> None:
        """En la pestaña de Step & Glue el motor de cosido comanda la red: el campo manual y [Ir a λ]
        quedan inhabilitados. El orden cero sigue disponible como acción explícita."""
        managed_by_recipe = (tab_index == self.step_glue_tab_index)
        self.edit_wavelength.setEnabled(not managed_by_recipe)
        self.btn_goto_wavelength.setEnabled(not managed_by_recipe)

    # ── Handlers Andor ────────────────────────────────────────────────────────

    def apply_camera_baseline_report(self, report) -> None:
        """Registra lo que el arranque envió (paso 8) para mostrarlo como [E], y deja el pedido de setpoint
        en el valor enviado. Lo demás lo muestra la instantánea leída."""
        if report is None:
            return
        self.control.sent.record_baseline(report)
        temp = report.item("temperature_c")
        if temp is not None and temp.outcome in ("OK", "SENT"):
            self.control.sent.record("temperature_setpoint_c", int(temp.requested),
                                     temp.set_code if temp.set_code is not None else _DRV_SUCCESS)
            self.spin_temp.blockSignals(True)
            self.spin_temp.setValue(int(temp.requested))
            self.spin_temp.blockSignals(False)
        hs = report.item("hs_speed_mhz")
        if hs is not None and isinstance(hs.readback, (int, float)):
            idx = self.cmb_hsspeed.findData(float(hs.readback))
            if idx >= 0:
                self.cmb_hsspeed.setCurrentIndex(idx)
        self._refresh_status()

    def _show_control_result(self, res):
        color = {ControlState.APPLIED: GREEN, ControlState.PENDING: "#f9e2af"}.get(res.state, RED)
        self.lbl_zo_steps.setText(res.detail)
        self.lbl_zo_steps.setStyleSheet(f"font-size: 8.5pt; color: {color};")

    def _on_apply_temperature(self):
        self._show_control_result(self.control.request_temperature(int(self.spin_temp.value())))
        self._refresh_status()

    def _on_toggle_cooler(self):
        snap = self.snapshot
        on_now = bool(snap and snap.camera.cooler_on.status == ReadStatus.READ_OK and snap.camera.cooler_on.value)
        if on_now:
            t = snap.camera.temperature_c
            temp = f"{t.value:.1f} °C" if t.status == ReadStatus.READ_OK else "temperatura sin leer"
            ans = QtWidgets.QMessageBox.question(
                self, "Apagar enfriador",
                f"El sensor está a {temp}. ¿Apagar el enfriador? El sensor vuelve a temperatura ambiente.",
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                QtWidgets.QMessageBox.StandardButton.No)
            if ans != QtWidgets.QMessageBox.StandardButton.Yes:
                return
        self._show_control_result(self.control.request_cooler(not on_now))
        self._refresh_status()

    def _on_fan(self, mode: str):
        self._show_control_result(self.control.request_fan(mode))
        self._refresh_status()

    def _on_apply_amp(self):
        code = self.camera.set_output_amplifier(self.cmb_amp.currentData())
        self.control.sent.record("output_amplifier", self.cmb_amp.currentData(), code)
        self._populate_hardware_dependent_combos()

    def _on_apply_hs(self):
        mhz = self.cmb_hsspeed.currentData()
        if mhz is None:
            return
        self._show_control_result(self.control.request_hs_speed_mhz(float(mhz)))
        self._refresh_status()

    def _on_gain_changed(self):
        requested = int(self.spin_gain.value())
        ret = self.camera.set_emccd_gain(requested)
        if ret != _DRV_SUCCESS and requested > 0 and si.get_interlock().is_specular_or_unknown():
            # El driver la rechazó por condición especular: el spinbox vuelve a mostrar la real
            self.spin_gain.blockSignals(True)
            self.spin_gain.setValue(0)
            self.spin_gain.blockSignals(False)
        self._hide_restore_pill()
        self._refresh_camera_readings()

    def _on_restore_gain(self):
        value = self._gain_restore_value
        if value is None:
            return
        if self.zero_order.gain_restore_needs_notch_confirmation() and not self.chk_notch.isChecked():
            self.chk_notch.show()
            self.lbl_zo_steps.setText("Hay un láser abierto: confirmá que el notch está puesto antes de restituir.")
            return
        if self.camera.set_emccd_gain(value) == _DRV_SUCCESS:
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

    def _on_exposure_changed(self):
        self.camera.set_exposure_time(float(self.spin_exposure.value()))
        self._refresh_camera_readings()

    def _on_apply_shutter_mode(self):
        """Obturador del espectrómetro a pedido del operador (investigador, 2026-09-29). "Abierto" y
        "Cerrado" actúan por los dos caminos del legado (USB del Shamrock y TTL de la cámara); "Auto" deja
        que la cámara lo maneje en cada exposición."""
        from pyspectrum.services.spectrometer_shutter import close_spectrometer_shutter, open_spectrometer_shutter
        idx = self.cmb_shutter_mode.currentIndex()
        if idx == 1:
            res = open_spectrometer_shutter(self.camera, self.spectrometer)
        elif idx == 2:
            res = close_spectrometer_shutter(self.camera, self.spectrometer)
        else:
            code = self.camera.set_shutter_mode(0) if hasattr(self.camera, "set_shutter_mode") else None
            self.control.sent.record("shutter_mode", idx, code)
            return
        self.control.sent.record("shutter_mode", idx, _DRV_SUCCESS if res.ok else -1)
        self.lbl_zo_steps.setText(res.detail)

    def _on_colormap_changed(self, name: str):
        spectroscopy_context.set_colormap(name)

    def _on_context_colormap_changed(self, name: str):
        if self.cmb_colormap.currentText() != name:
            self.cmb_colormap.blockSignals(True)
            self.cmb_colormap.setCurrentText(name)
            self.cmb_colormap.blockSignals(False)

    def _on_context_slit_changed(self, width_um: float, center_px: float, zero_pos: int):
        if not self.spin_slit.hasFocus() and abs(self.spin_slit.value() - width_um) > 0.05:
            self.spin_slit.blockSignals(True)
            self.spin_slit.setValue(width_um)
            self.spin_slit.blockSignals(False)

    # ── Handlers Shamrock ─────────────────────────────────────────────────────

    def _on_grating_changed(self, idx: int):
        """Elegir la red no mueve nada (G-04): sólo cambia el destino; se mueve con [Ir]."""
        self._grating_dirty = True
        self._update_destination()

    def _on_slit_changed(self):
        val = float(self.spin_slit.value())
        ret = self.spectrometer.ShamrockSetSlit(DEVICE, 1, val)
        ret_r, width = self.spectrometer.ShamrockGetSlit(DEVICE, 1)
        if ret != SHAMROCK_SUCCESS:
            self.lbl_zo_steps.setText(f"La ranura no se fijó (código {ret}).")
        elif ret_r != SHAMROCK_SUCCESS or not math.isfinite(float(width)) or abs(float(width) - val) > 1.0:
            self.lbl_zo_steps.setText(f"Ranura: se pidió {val:.1f} µm; relectura {width} (código {ret_r}).")
        else:
            spectroscopy_context.set_slit_parameters(slit_width_um=float(width))
        self._refresh_status()

    def _on_set_ports(self):
        want = (self.cmb_flipper_in.currentIndex(), self.cmb_flipper_out.currentIndex())
        codes = [self.spectrometer.ShamrockSetFlipper(DEVICE, 1, want[0]),
                 self.spectrometer.ShamrockSetFlipper(DEVICE, 2, want[1])]
        got = (self.spectrometer.ShamrockGetFlipper(DEVICE, 1), self.spectrometer.ShamrockGetFlipper(DEVICE, 2))
        if any(c != SHAMROCK_SUCCESS for c in codes) or any(g[0] != SHAMROCK_SUCCESS for g in got) \
                or (got[0][1], got[1][1]) != want:
            self.lbl_zo_steps.setText(f"Puertos: se pidió {want}; códigos {codes}; relectura "
                                      f"{(got[0][1], got[1][1])}.")
        self._refresh_status()

    def _on_goto_wavelength(self):
        wl = float(self.edit_wavelength.value())
        grating = self.cmb_grating.currentIndex() + 1
        self._grating_dirty = False
        if grating == GRATING_MIRROR:
            self._run_specular(lambda: self.zero_order.enter_specular("mirror"), "red espejo")
        else:
            self._run_specular(lambda: self.zero_order.move(grating, wl), f"red {grating} · λc {wl:.2f} nm")

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
        """Tras entrar o volver: la exposición y la ganancia pedidas pasan a ser las que tiene la cámara."""
        try:
            exp = float(self.camera.get_exposure_time())
            self.spin_exposure.blockSignals(True)
            self.spin_exposure.setValue(exp)
            self.spin_exposure.blockSignals(False)
        except Exception:
            pass
        g = self.camera.get_emccd_gain()
        ret, gain = (g[0], g[1]) if isinstance(g, (tuple, list)) else (_DRV_SUCCESS, g)
        if ret == _DRV_SUCCESS:
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
            self.lbl_destination.setStyleSheet(f"color: {TEXT_SECONDARY};")
            self.btn_goto_wavelength.setText("➡️ Ir a λ")
        else:
            why = "red espejo" if grating == GRATING_MIRROR else f"λc < {si.specular_threshold_nm(grating):.1f} nm"
            self.lbl_destination.setText(f"destino: ESPECULAR ({why}): se entra por el espejo rápido")
            self.lbl_destination.setStyleSheet(f"color: {PEACH}; font-weight: bold;")
            self.btn_goto_wavelength.setText("➡️ Ir (espejo rápido)")

    def _apply_specular_ui(self, mode: str):
        specular = mode != si.FIRST_ORDER
        self.spin_gain.setEnabled(not specular)
        self.btn_apply_gain.setEnabled(not specular)
        self.lbl_gain_lock.setVisible(specular)
        self.btn_reread.setVisible(mode == si.UNKNOWN)
        self.btn_mirror.setEnabled(mode == si.FIRST_ORDER)
        if mode == si.FIRST_ORDER:
            self.lbl_specular_state.setText("Estado: PRIMER ORDEN")
            self.lbl_specular_state.setStyleSheet(f"color: {TEXT_SECONDARY};")
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
            self.lbl_light.setStyleSheet(f"color: {'#F9E2AF' if warning else TEXT_SECONDARY};")
            self.lbl_light.show()
        else:
            self.lbl_light.hide()
        if mode != self._last_mode:
            self._last_mode = mode
            self.specularStateChanged.emit(mode)

    # ── Refresco periódico: la instantánea leída ─────────────────────────────

    @staticmethod
    def _paint(label: QtWidgets.QLabel, reading, text_ok: str, name: str):
        mark = reading.mark()
        if reading.status == ReadStatus.READ_OK or reading.status == ReadStatus.SENT_OK:
            label.setText(f"{mark} {name}: {text_ok}" if name else f"{mark} {text_ok}")
            label.setStyleSheet(f"color: {TEXT_SECONDARY};")
        else:
            extra = f" · {reading.detail}" if reading.detail else ""
            label.setText(f"{mark} {name}: sin valor{extra}" if name else f"{mark} sin valor{extra}")
            label.setStyleSheet(f"color: {RED if reading.status == ReadStatus.READ_FAILED else TEXT_SECONDARY};")

    def _refresh_camera_readings(self):
        self._refresh_status()

    def _refresh_status(self):
        snap = self.state_service.poll()
        self.snapshot = snap
        cam, spec = snap.camera, snap.spectrograph
        connected = cam.connection.status == ReadStatus.READ_OK

        # ── Cámara ──
        if connected:
            self.lbl_camera_connection.setText(f"{cam.connection.mark()} cámara conectada")
            self.lbl_camera_connection.setStyleSheet(f"color: {TEXT_SECONDARY};")
        else:
            self.lbl_camera_connection.setText(f"[X] cámara no conectada: {cam.connection.detail}")
            self.lbl_camera_connection.setStyleSheet(f"color: {RED}; font-weight: bold;")
        for w in (self.btn_apply_temp, self.btn_cooler, self.rb_fan_low, self.rb_fan_high, self.btn_apply_gain,
                  self.btn_apply_exposure, self.btn_apply_hs, self.btn_apply_amp, self.btn_apply_shutter):
            w.setEnabled(connected)

        t = cam.temperature_c
        if t.status == ReadStatus.READ_OK:
            self.lbl_temp_badge.setText(f"{t.mark()} Temp: {t.value:.1f} °C · {cam.temperature_word}")
            self.lbl_temp_badge.setStyleSheet(f"color: {TEXT_SECONDARY};")
        elif t.status == ReadStatus.NOT_READ and t.code == 20072:
            self.lbl_temp_badge.setText(f"⏸ Temp: {t.detail.replace('; último:', ' · último:')} (última lectura; adquiriendo)")
            self.lbl_temp_badge.setStyleSheet(f"color: {TEXT_SECONDARY};")
        else:
            self.lbl_temp_badge.setText(f"{t.mark()} Temp: sin lectura" + (f" · {t.detail}" if t.detail else ""))
            self.lbl_temp_badge.setStyleSheet(f"color: {RED if t.status == ReadStatus.READ_FAILED else TEXT_SECONDARY};")
        sp = self.control.sent.get("temperature_setpoint_c")
        self.lbl_setpoint.setText(f"setpoint {sp.mark()} {sp.value} °C" if sp.ok else f"setpoint {sp.mark()}")

        c = cam.cooler_on
        if c.status == ReadStatus.READ_OK:
            self.lbl_cooler_read.setText(f"{c.mark()} Enfriador {'encendido' if c.value else 'apagado'}")
            self.btn_cooler.setText("Apagar enfriador" if c.value else "Encender enfriador")
            self.lbl_cooler_read.setStyleSheet(f"color: {TEXT_SECONDARY};")
        else:
            self.lbl_cooler_read.setText(f"{c.mark()} Enfriador: estado sin leer")
            self.lbl_cooler_read.setStyleSheet(f"color: {RED if c.status == ReadStatus.READ_FAILED else TEXT_SECONDARY};")
            self.btn_cooler.setText("Enfriador…")

        fan = cam.fan_mode
        if fan.ok:
            self.lbl_fan.setText(f"Ventilador {fan.mark()} {FAN_NAMES.get(fan.value, fan.value)}")
            for rb, code in ((self.rb_fan_low, 1), (self.rb_fan_high, 0)):
                rb.blockSignals(True)
                rb.setChecked(fan.value == code)
                rb.blockSignals(False)
        else:
            self.lbl_fan.setText(f"Ventilador {fan.mark()}")
        pending = self.control.pending_names()
        if pending:
            self.lbl_fan.setText(self.lbl_fan.text() + f" · pendiente: {', '.join(pending)}")

        g = cam.em_gain
        self.lbl_gain_read.setText(f"{g.mark()} {g.value} DAC" if g.status == ReadStatus.READ_OK
                                   else f"{g.mark()} ganancia sin leer")
        e = cam.exposure_s
        self.lbl_exposure_read.setText(f"{e.mark()} {e.value:.4f} s (real)" if e.status == ReadStatus.READ_OK
                                       else f"{e.mark()} exposición sin leer")
        rm, am = cam.read_mode, cam.acquisition_mode
        rm_txt = f"{rm.mark()} {READ_MODE_NAMES.get(rm.value, rm.value)}" if rm.ok else rm.mark()
        am_txt = f"{am.mark()} {ACQ_MODE_NAMES.get(am.value, am.value)}" if am.ok else am.mark()
        self.lbl_modes.setText(f"Lectura: {rm_txt} · {am_txt}")
        vs, hs, pa = cam.vs_speed_us, cam.hs_speed_mhz, cam.preamp
        vs_txt = f"{vs.mark()} VS {vs.value:g} µs" if vs.ok else f"{vs.mark()} VS"
        hs_txt = f"{hs.mark()} HS {hs.value:g} MHz" if hs.ok else f"{hs.mark()} HS"
        pa_txt = f"{pa.mark()} pre-amp {pa.value}" if pa.ok else f"{pa.mark()} pre-amp"
        self.lbl_speeds.setText(f"Velocidades: {vs_txt} · {hs_txt} · {pa_txt}")
        if connected:
            self.control.apply_pending()

        # ── Espectrógrafo ──
        gr, lines, wl = spec.grating, spec.grating_lines_per_mm, spec.wavelength_nm
        if gr.status == ReadStatus.READ_OK:
            lines_txt = f" · {lines.value:.0f} l/mm" if lines.status == ReadStatus.READ_OK and lines.value else \
                (" · espejo" if gr.value == GRATING_MIRROR else "")
            self.lbl_grating_read.setText(f"{gr.mark()} Red {gr.value}{lines_txt}")
            if not self._grating_dirty and not self.cmb_grating.hasFocus() and 1 <= gr.value <= self.cmb_grating.count():
                self.cmb_grating.blockSignals(True)
                self.cmb_grating.setCurrentIndex(gr.value - 1)
                self.cmb_grating.blockSignals(False)
        else:
            self.lbl_grating_read.setText(f"{gr.mark()} Red: sin lectura")
        moving = " ⏳ asentando…" if (hasattr(self.spectrometer, "is_moving") and self.spectrometer.is_moving()) else ""
        self.lbl_wavelength.setText(f"{wl.mark()} λc (SDK): {wl.value:.2f} nm{moving}" if wl.status == ReadStatus.READ_OK
                                    else f"{wl.mark()} λc (SDK): sin lectura")
        sl = spec.slit_width_um
        self.lbl_slit_read.setText(f"{sl.mark()} {sl.value:.1f} µm" if sl.status == ReadStatus.READ_OK
                                   else f"{sl.mark()} ranura sin leer")
        ports = spec.ports
        if ports.status == ReadStatus.READ_OK:
            p_in, p_out = ports.value
            name_in = NAME_PORTS_IN[p_in] if 0 <= p_in < len(NAME_PORTS_IN) else str(p_in)
            name_out = NAME_PORTS_OUT[p_out] if 0 <= p_out < len(NAME_PORTS_OUT) else str(p_out)
            self.lbl_ports_read.setText(f"{ports.mark()} entrada {name_in} · salida {name_out}")
        else:
            self.lbl_ports_read.setText(f"{ports.mark()} puertos sin leer")
        if gr.status == ReadStatus.READ_OK and wl.status == ReadStatus.READ_OK:
            spectroscopy_context.set_spectrograph_position(wl.value, gr.value)
        # La condición especular se publica desde la lectura: una lectura fallida es "desconocido" y
        # bloquea la ganancia (falla cerrada, R2-inst §2.1-4).
        mode = spec.specular
        self.zero_order.interlock.publish(mode, "leído por el panel")
        self._apply_specular_ui(mode)
        self._update_destination()
