# -*- coding: utf-8 -*-
"""
hardware_dashboard.py — Tablero de Conexiones, Seguridad y Aislamiento de Hardware
PyPrinting 3.0 — UNSAM Nanofotónica

Widget gráfico interactivo para monitorear, conectar, desconectar y aislar instrumentos
(NI-DAQmx, PI Piezo, Cámara, Láser, Espectrómetro) en caliente (Hot-Plug & Soft Mock Isolation),
con bitácora I/O en tiempo real.
"""
from __future__ import annotations
import os
from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtWidgets import (QMainWindow, QWidget, QFrame, QVBoxLayout, QHBoxLayout, QGridLayout,
                               QLabel, QPushButton, QCheckBox, QTextEdit, QGroupBox,
                               QHeaderView, QTableWidget, QTableWidgetItem, QComboBox)
from PyQt6.QtGui import QColor, QFont

from core.hardware_manager import hardware_manager, HardwareManager
from config import (REGIME_LEGACY, REGIME_LASER_REF, REGIME_SAMPLE_REF, DEFAULT_COORDINATE_REGIME)
from core.nanopositioning import set_global_coordinate_regime


class HardwareDashboardWidget(QFrame):
    """
    Tablero de Conexiones y Seguridad de Hardware.
    Permite evaluar condiciones de comunicación, conectar/desconectar instrumentos en caliente,
    aislarlos individualmente (Soft Mock) y visualizar la bitácora de telemetría del microscopio.
    """

    STATUS_COLORS = {
        "connected":    ("#a6e3a1", "🟢 Conectado"),
        "mock":         ("#f9e2af", "🟡 Simulado (Mock)"),
        "disconnected": ("#f38ba8", "🔴 Desconectado"),
        "inactive":     ("#6c7086", "⚪ Inactivo (PySpectrum)")
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("""
            HardwareDashboardWidget {
                background-color: #1e1e2e;
                border: 1px solid #313244;
                border-radius: 6px;
            }
            QGroupBox {
                color: #cdd6f4;
                font-weight: bold;
                border: 1px solid #45475a;
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QLabel {
                color: #cdd6f4;
            }
            QPushButton {
                background-color: #313244;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 4px;
                padding: 5px 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45475a;
                color: #89b4fa;
            }
            QPushButton:pressed {
                background-color: #89b4fa;
                color: #11111b;
            }
            QTextEdit {
                background-color: #11111b;
                color: #a6adc8;
                font-family: monospace;
                font-size: 9pt;
                border: 1px solid #313244;
                border-radius: 4px;
            }
        """)

        self._setup_ui()
        self._connect_signals()
        try:
            from core.nanopositioning import register_regime_listener
            register_regime_listener(self.on_global_regime_changed)
        except Exception:
            pass
        hardware_manager.rescan_hardware()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # ── Título y Barra de Controles ───────────────────────────────────────
        header_hlo = QHBoxLayout()
        lbl_title = QLabel("🛡️ <b>Tablero de Conexiones & Seguridad de Hardware</b>")
        lbl_title.setStyleSheet("font-size: 11pt; color: #89b4fa;")

        self.lbl_summary = QLabel("")
        self.lbl_summary.setStyleSheet("font-size: 9pt; font-weight: bold; color: #cdd6f4; background-color: #313244; border-radius: 4px; padding: 2px 8px;")

        self.combo_profile = QComboBox()
        self.combo_profile.addItems(["Perfil: PyPrinting", "Perfil: PySpectrum", "Perfil: Cámara", "Perfil: Completo (All)"])
        self.combo_profile.setStyleSheet("background-color: #313244; color: #89b4fa; font-weight: bold; border-radius: 4px; padding: 2px 6px;")
        prof_map = {"pyprinting": 0, "pyspectrum": 1, "camera": 2, "all": 3}
        self.combo_profile.setCurrentIndex(prof_map.get(hardware_manager.active_profile, 3))
        self.combo_profile.currentIndexChanged.connect(self._on_profile_changed)

        self.btn_rescan = QPushButton("🔄 Re-scan")
        self.btn_rescan.setToolTip("Re-escanea y reconecta en caliente todos los instrumentos físicos detectados.")
        self.btn_rescan.clicked.connect(lambda: hardware_manager.rescan_hardware())

        self.btn_clear_log = QPushButton("🧹 Limpiar Bitácora")
        self.btn_clear_log.setToolTip("Limpia la consola de eventos de telemetría.")
        self.btn_clear_log.clicked.connect(self._clear_log)

        header_hlo.addWidget(lbl_title)
        header_hlo.addSpacing(10)
        header_hlo.addWidget(self.lbl_summary)
        header_hlo.addSpacing(10)
        header_hlo.addWidget(self.combo_profile)
        header_hlo.addStretch()
        header_hlo.addWidget(self.btn_rescan)
        header_hlo.addWidget(self.btn_clear_log)
        main_layout.addLayout(header_hlo)

        # ── Matriz de Estado e Instrumentos ───────────────────────────────────
        devices_box = QGroupBox("Matriz de Conexión de Instrumentos, Hot-Plug & Aislamiento")
        devices_glo = QGridLayout(devices_box)
        devices_glo.setHorizontalSpacing(15)
        devices_glo.setVerticalSpacing(8)

        self.dev_widgets = {}

        headers = ["Instrumento", "Estado de Conexión", "Detalle de Telemetría", "Acción I/O", "Aislamiento (Soft Mock)"]
        for col, h in enumerate(headers):
            lbl_h = QLabel(f"<b>{h}</b>")
            lbl_h.setStyleSheet("color: #a6adc8; font-size: 9pt;")
            devices_glo.addWidget(lbl_h, 0, col)

        for row, dev_name in enumerate(HardwareManager.DEVICES, start=1):
            lbl_dev = QLabel(dev_name)
            lbl_dev.setStyleSheet("font-weight: bold;")

            lbl_status = QLabel("⚪ Inactivo")
            lbl_status.setFixedWidth(160)
            lbl_status.setStyleSheet("font-family: monospace; font-weight: bold; padding: 2px 6px; border-radius: 3px; background-color: #313244;")

            lbl_detail = QLabel("Esperando verificación...")
            lbl_detail.setStyleSheet("color: #a6adc8; font-size: 9pt;")

            btn_action = QPushButton("🔌 Conectar")
            btn_action.setFixedWidth(110)
            btn_action.setToolTip(f"Conectar o desconectar {dev_name} en caliente.")

            chk_isolate = QCheckBox("Aislar (Mock)")
            chk_isolate.setToolTip(f"Aísla {dev_name} conmutando a modo simulación (Soft Mock) para pruebas seguras.")

            if dev_name == "Espectrómetro USB (PySpectrum)":
                btn_action.setEnabled(False)
                chk_isolate.setEnabled(False)
                chk_isolate.setToolTip("Módulo Espectrómetro Inactivo — Pendiente de integración con PySpectrum.")
                lbl_dev.setStyleSheet("font-weight: bold; color: #6c7086;")
                lbl_detail.setStyleSheet("color: #6c7086; font-size: 9pt; font-style: italic;")

            btn_action.clicked.connect(lambda _, d=dev_name: self._handle_action_button(d))
            chk_isolate.toggled.connect(lambda chk, d=dev_name: hardware_manager.toggle_isolation(d, chk))

            devices_glo.addWidget(lbl_dev, row, 0)
            devices_glo.addWidget(lbl_status, row, 1)
            devices_glo.addWidget(lbl_detail, row, 2)
            devices_glo.addWidget(btn_action, row, 3)
            devices_glo.addWidget(chk_isolate, row, 4)

            self.dev_widgets[dev_name] = {
                "status":     lbl_status,
                "detail":     lbl_detail,
                "action_btn": btn_action,
                "isolate":    chk_isolate
            }

        main_layout.addWidget(devices_box)

        # ── Cinemática y Régimen de Coordenadas de Platina PI ──────────────────
        kinematics_box = QGroupBox("Cinemática de Platina Piezoeléctrica PI (Régimen de Coordenadas & Teclado)")
        kin_vlo = QVBoxLayout(kinematics_box)
        kin_vlo.setSpacing(6)

        kin_top_hlo = QHBoxLayout()
        lbl_kin_title = QLabel("<b>Régimen Activo:</b>")
        lbl_kin_title.setStyleSheet("font-size: 9pt; color: #cdd6f4;")

        self.combo_kin_regime = QComboBox()
        self.combo_kin_regime.addItem("🏛️ Legacy (Ejes brutos PI 1/2)", REGIME_LEGACY)
        self.combo_kin_regime.addItem("🎯 Laser Ref (Spot en Pantalla)", REGIME_LASER_REF)
        self.combo_kin_regime.addItem("🔬 Sample Ref (Objetos en Muestra)", REGIME_SAMPLE_REF)
        self.combo_kin_regime.setStyleSheet("""
            QComboBox {
                background-color: #181825; color: #89b4fa; border: 1px solid #45475a;
                border-radius: 4px; padding: 3px 8px; font-weight: bold; font-size: 9pt;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background-color: #1e1e2e; color: #cdd6f4; selection-background-color: #313244;
            }
        """)
        self.combo_kin_regime.currentIndexChanged.connect(self._on_kin_regime_changed)

        self.lbl_kin_keyboard_badge = QLabel("⌨️ Flechas Teclado: [← ↑ → ↓] Paso 1x (Shift: 10x)")
        self.lbl_kin_keyboard_badge.setStyleSheet(
            "color: #a6e3a1; background-color: #11111b; border: 1px solid #313244; "
            "border-radius: 4px; padding: 3px 8px; font-weight: bold; font-size: 8.5pt;"
        )
        self.lbl_kin_keyboard_badge.setToolTip("Control por flechas activo en la aplicación: [← ↑ → ↓] mueven 1 paso la platina según el régimen activo.")

        kin_top_hlo.addWidget(lbl_kin_title)
        kin_top_hlo.addWidget(self.combo_kin_regime, stretch=1)
        kin_top_hlo.addSpacing(10)
        kin_top_hlo.addWidget(self.lbl_kin_keyboard_badge)

        self.lbl_kin_description = QLabel("")
        self.lbl_kin_description.setStyleSheet(
            "color: #bac2de; font-size: 8.5pt; background-color: #181825; border-radius: 4px; "
            "padding: 4px 8px; border: 1px dashed #45475a;"
        )
        self._update_kin_description(DEFAULT_COORDINATE_REGIME)

        kin_vlo.addLayout(kin_top_hlo)
        kin_vlo.addWidget(self.lbl_kin_description)

        main_layout.addWidget(kinematics_box)

        # ── Console / Hardware Log ────────────────────────────────────────────
        log_box = QGroupBox("Bitácora de Eventos I/O & Telemetría en Tiempo Real")
        log_vlo = QVBoxLayout(log_box)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFixedHeight(140)
        log_vlo.addWidget(self.log_text)

        main_layout.addWidget(log_box)

    def _update_kin_description(self, regime: str):
        if regime == REGIME_LEGACY:
            desc = "<b>Legacy (Ejes Brutos):</b> [→] Eje físico 1 (+) | [←] Eje físico 1 (-) | [↑] Eje físico 2 (+) | [↓] Eje físico 2 (-)"
        elif regime == REGIME_LASER_REF:
            desc = "<b>Laser Ref (Spot en Pantalla):</b> [→] Spot Láser a la DERECHA (Eje 2 +) | [←] Spot Láser a la IZQUIERDA (Eje 2 -) | [↑] Spot Láser hacia ARRIBA (Eje 1 -) | [↓] Spot Láser hacia ABAJO (Eje 1 +)"
        elif regime == REGIME_SAMPLE_REF:
            desc = "<b>Sample Ref (Objetos en Muestra):</b> [→] Objetos a la DERECHA (Eje 2 -) | [←] Objetos a la IZQUIERDA (Eje 2 +) | [↑] Objetos hacia ARRIBA (Eje 1 +) | [↓] Objetos hacia ABAJO (Eje 1 -)"
        else:
            desc = ""
        self.lbl_kin_description.setText(desc)

    def _on_kin_regime_changed(self, idx: int):
        regime = self.combo_kin_regime.currentData()
        if regime:
            self._update_kin_description(regime)
            set_global_coordinate_regime(regime)
            hardware_manager.log("INFO", f"[Kinematics] Régimen de coordenadas de platina conmutado a: {regime}")

    def on_global_regime_changed(self, regime: str):
        if hasattr(self, "combo_kin_regime"):
            for i in range(self.combo_kin_regime.count()):
                if self.combo_kin_regime.itemData(i) == regime:
                    if self.combo_kin_regime.currentIndex() != i:
                        self.combo_kin_regime.blockSignals(True)
                        self.combo_kin_regime.setCurrentIndex(i)
                        self.combo_kin_regime.blockSignals(False)
                        self._update_kin_description(regime)
                    break

    def closeEvent(self, event):
        try:
            from core.nanopositioning import unregister_regime_listener
            unregister_regime_listener(self.on_global_regime_changed)
        except Exception:
            pass
        super().closeEvent(event)

    def _connect_signals(self):
        hardware_manager.deviceStatusSignal.connect(self._on_device_status_update)
        hardware_manager.hardwareLogSignal.connect(self._on_hardware_log)

    def _on_profile_changed(self, idx: int):
        profiles = ["pyprinting", "pyspectrum", "camera", "all"]
        if 0 <= idx < len(profiles):
            hardware_manager.set_profile(profiles[idx], rescan=True)

    def _handle_action_button(self, dev_name: str):
        state = hardware_manager.device_states.get(dev_name, "disconnected")
        if state == "connected":
            hardware_manager.disconnect_device(dev_name)
        else:
            hardware_manager.connect_device(dev_name)

    @pyqtSlot(str, str, str)
    def _on_device_status_update(self, dev_name: str, status_str: str, detail_msg: str):
        if dev_name in self.dev_widgets:
            w = self.dev_widgets[dev_name]
            color_hex, label_text = self.STATUS_COLORS.get(status_str, ("#cdd6f4", status_str))
            w["status"].setText(label_text)
            w["status"].setStyleSheet(
                f"font-family: monospace; font-weight: bold; padding: 2px 6px; border-radius: 3px; "
                f"background-color: #11111b; color: {color_hex}; border: 1px solid {color_hex};"
            )
            w["detail"].setText(detail_msg)

            # Sincronizar checkbox de aislamiento
            w["isolate"].blockSignals(True)
            w["isolate"].setChecked(hardware_manager.device_isolated.get(dev_name, False))
            w["isolate"].blockSignals(False)

            # Actualizar botón de acción dinámica
            if dev_name != "Espectrómetro USB (PySpectrum)":
                if status_str == "connected":
                    w["action_btn"].setText("⏏️ Desconectar")
                    w["action_btn"].setStyleSheet("background-color: #f38ba8; color: #111; font-weight: bold;")
                else:
                    w["action_btn"].setText("🔌 Conectar")
                    w["action_btn"].setStyleSheet("background-color: #a6e3a1; color: #111; font-weight: bold;")

            # Actualizar contador global
            n_conn = sum(1 for s in hardware_manager.device_states.values() if s == "connected")
            n_mock = sum(1 for s in hardware_manager.device_states.values() if s == "mock")
            n_disc = sum(1 for s in hardware_manager.device_states.values() if s == "disconnected")
            self.lbl_summary.setText(f"[ 🟢 {n_conn} Conectados | 🟡 {n_mock} Simulados | 🔴 {n_disc} Desconectados ]")

    @pyqtSlot(str, str, str)
    def _on_hardware_log(self, ts: str, level: str, msg: str):
        color_map = {
            "INFO":    "#89b4fa",
            "SUCCESS": "#a6e3a1",
            "WARNING": "#f9e2af",
            "ERROR":   "#f38ba8"
        }
        c = color_map.get(level, "#cdd6f4")
        html_msg = f"<span style='color: #6c7086;'>[{ts}]</span> <b style='color: {c};'>[{level}]</b> {msg}"
        self.log_text.append(html_msg)

    def _clear_log(self):
        self.log_text.clear()


class HardwareDashboardWindow(QMainWindow):
    """
    Ventana independiente para el Tablero de Conexiones, Seguridad y Aislamiento de Hardware.
    Permite visualizar la matriz de estado de instrumentos, conectar/desconectar dispositivos por software
    y revisar la bitácora I/O sin saturar el espacio de trabajo de la GUI principal.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tablero de Conexiones, Seguridad y Aislamiento de Hardware 🛡️ — PyPrinting 3.0")
        self.resize(880, 590)
        self.setMinimumSize(750, 500)
        self.setStyleSheet("""
            QMainWindow {
                background-color: #11111b;
            }
        """)

        self.widget = HardwareDashboardWidget(self)
        self.setCentralWidget(self.widget)


if __name__ == "__main__":
    import sys
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    win = HardwareDashboardWindow()
    win.show()
    sys.exit(app.exec())
