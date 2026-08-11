# -*- coding: utf-8 -*-
"""
hardware_dashboard.py — Tablero de Conexiones, Seguridad y Aislamiento de Hardware
PyPrinting 3.0 — UNSAM Nanofotónica

Widget gráfico para visualizar la matriz de conexiones de instrumentos (NI-DAQmx, PI Piezo,
Cámara, Láser, Espectrómetro), gestionar el aislamiento por software (Soft Mock Isolation)
y monitorear la bitácora de eventos I/O en tiempo real.
"""
from __future__ import annotations
import os
from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtWidgets import (QWidget, QFrame, QVBoxLayout, QHBoxLayout, QGridLayout,
                               QLabel, QPushButton, QCheckBox, QTextEdit, QGroupBox,
                               QHeaderView, QTableWidget, QTableWidgetItem)
from PyQt6.QtGui import QColor, QFont

from core.hardware_manager import hardware_manager, HardwareManager


class HardwareDashboardWidget(QFrame):
    """
    Tablero de Conexiones y Seguridad de Hardware.
    Permite evaluar condiciones de comunicación, aislar instrumentos individualmente
    y visualizar la bitácora de telemetría del microscopio.
    """

    STATUS_COLORS = {
        "connected": ("#a6e3a1", "🟢 Conectado"),
        "mock":      ("#f9e2af", "🟡 Simulado (Mock)"),
        "disconnected": ("#f38ba8", "🔴 Desconectado"),
        "inactive":  ("#6c7086", "⚪ Inactivo (PySpectrum Pending)")
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
        hardware_manager.rescan_hardware()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # ── Título y Barra de Controles ───────────────────────────────────────
        header_hlo = QHBoxLayout()
        lbl_title = QLabel("🛡️ <b>Tablero de Conexiones & Seguridad de Hardware</b>")
        lbl_title.setStyleSheet("font-size: 11pt; color: #89b4fa;")

        self.btn_rescan = QPushButton("🔄 Re-scan Hardware")
        self.btn_rescan.setToolTip("Re-escanea en caliente la presencia de conexiones físicas USB/GPIB/NI-DAQ.")
        self.btn_rescan.clicked.connect(lambda: hardware_manager.rescan_hardware())

        self.btn_clear_log = QPushButton("🧹 Limpiar Bitácora")
        self.btn_clear_log.setToolTip("Limpia la consola de eventos de telemetría.")
        self.btn_clear_log.clicked.connect(self._clear_log)

        header_hlo.addWidget(lbl_title)
        header_hlo.addStretch()
        header_hlo.addWidget(self.btn_rescan)
        header_hlo.addWidget(self.btn_clear_log)
        main_layout.addLayout(header_hlo)

        # ── Matriz de Estado e Instrumentos ───────────────────────────────────
        devices_box = QGroupBox("Matriz de Conexión de Instrumentos & Aislamiento por Software")
        devices_glo = QGridLayout(devices_box)
        devices_glo.setHorizontalSpacing(15)
        devices_glo.setVerticalSpacing(8)

        self.dev_widgets = {}

        headers = ["Instrumento", "Estado de Conexión", "Detalle de Telemetría", "Aislamiento (Soft Mock)"]
        for col, h in enumerate(headers):
            lbl_h = QLabel(f"<b>{h}</b>")
            lbl_h.setStyleSheet("color: #a6adc8; font-size: 9pt;")
            devices_glo.addWidget(lbl_h, 0, col)

        for row, dev_name in enumerate(HardwareManager.DEVICES, start=1):
            lbl_dev = QLabel(dev_name)
            lbl_dev.setStyleSheet("font-weight: bold;")

            lbl_status = QLabel("⚪ Inactivo")
            lbl_status.setFixedWidth(150)
            lbl_status.setStyleSheet("font-family: monospace; font-weight: bold; padding: 2px 6px; border-radius: 3px; background-color: #313244;")

            lbl_detail = QLabel("Esperando inicialización...")
            lbl_detail.setStyleSheet("color: #a6adc8; font-size: 9pt;")

            chk_isolate = QCheckBox("Aislar (Mock)")
            chk_isolate.setToolTip(f"Aísla {dev_name} conmutando a modo simulación (Soft Mock) para pruebas seguras.")
            
            if dev_name == "Espectrómetro USB (PySpectrum)":
                chk_isolate.setEnabled(False)
                chk_isolate.setToolTip("Módulo Espectrómetro Inactivo — Pendiente de integración con PySpectrum en futuros desarrollos.")
                lbl_dev.setStyleSheet("font-weight: bold; color: #6c7086;")
                lbl_detail.setStyleSheet("color: #6c7086; font-size: 9pt; font-style: italic;")

            chk_isolate.toggled.connect(lambda chk, d=dev_name: hardware_manager.toggle_isolation(d, chk))

            devices_glo.addWidget(lbl_dev, row, 0)
            devices_glo.addWidget(lbl_status, row, 1)
            devices_glo.addWidget(lbl_detail, row, 2)
            devices_glo.addWidget(chk_isolate, row, 3)

            self.dev_widgets[dev_name] = {
                "status": lbl_status,
                "detail": lbl_detail,
                "isolate": chk_isolate
            }

        main_layout.addWidget(devices_box)

        # ── Console / Hardware Log ────────────────────────────────────────────
        log_box = QGroupBox("Bitácora de Eventos I/O & Telemetría en Tiempo Real")
        log_vlo = QVBoxLayout(log_box)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFixedHeight(140)
        log_vlo.addWidget(self.log_text)

        main_layout.addWidget(log_box)

    def _connect_signals(self):
        hardware_manager.deviceStatusSignal.connect(self._on_device_status_update)
        hardware_manager.hardwareLogSignal.connect(self._on_hardware_log)

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

    @pyqtSlot(str, str, str)
    def _on_hardware_log(self, ts: str, level: str, msg: str):
        color_map = {
            "INFO": "#89b4fa",
            "SUCCESS": "#a6e3a1",
            "WARNING": "#f9e2af",
            "ERROR": "#f38ba8"
        }
        c = color_map.get(level, "#cdd6f4")
        html_msg = f"<span style='color: #6c7086;'>[{ts}]</span> <b style='color: {c};'>[{level}]</b> {msg}"
        self.log_text.append(html_msg)

    def _clear_log(self):
        self.log_text.clear()


class HardwareDashboardWindow(QMainWindow):
    """
    Ventana independiente para el Tablero de Conexiones, Seguridad y Aislamiento de Hardware.
    Permite visualizar la matriz de estado de instrumentos, aislar dispositivos por software
    y revisar la bitácora I/O sin saturar el espacio de trabajo de la GUI principal.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tablero de Conexiones, Seguridad y Aislamiento de Hardware 🛡️ — PyPrinting 3.0")
        self.resize(850, 580)
        self.setMinimumSize(720, 480)
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

