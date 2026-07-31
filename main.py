#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PyPrinting 3.0 — Panel de Inicio Principal (main.py)
UNSAM — Nanofotónica

Launcher principal interactivo con interfaz gráfica moderna PyQt6 para lanzar:
1. Microscopio Derecho (app.py)
2. PSF Analyzer (psf_analyzer.py)
3. Analizador de Imágenes (image_analyzer.py)
4. Cámara Réflex Live View (camera.py / canon_test.py)
"""

import sys
import os
import subprocess
from pathlib import Path
from typing import List

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QGridLayout, QCheckBox, QMessageBox,
    QStatusBar, QGraphicsDropShadowEffect
)
from PyQt6.QtCore import Qt, QProcess
from PyQt6.QtGui import QFont, QColor, QIcon

# Importar configuración global para verificar SAFE_MODE
try:
    from config import SAFE_MODE
except ImportError:
    SAFE_MODE = False


class ApplicationCard(QFrame):
    """Tarjeta gráfica representativa para cada programa ejecutable."""

    def __init__(self, icon_str: str, title: str, subtitle: str, description: str,
                 button_text: str, button_color: str, launch_callback, parent=None):
        super().__init__(parent)
        self.launch_callback = launch_callback

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: #1E1E2E;
                border: 1px solid #313244;
                border-radius: 12px;
                padding: 16px;
            }}
            QFrame:hover {{
                border: 1px solid {button_color};
                background-color: #252538;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Header de la tarjeta (Icono + Titulo)
        header_hlo = QHBoxLayout()
        lbl_icon = QLabel(icon_str)
        lbl_icon.setStyleSheet("font-size: 28pt; background: transparent; border: none;")

        title_vlo = QVBoxLayout()
        title_vlo.setSpacing(2)

        lbl_title = QLabel(title)
        lbl_title.setStyleSheet("font-size: 13pt; font-weight: bold; color: #CDD6F4; background: transparent; border: none;")

        lbl_sub = QLabel(subtitle)
        lbl_sub.setStyleSheet("font-size: 9pt; color: #A6ADC8; background: transparent; border: none;")

        title_vlo.addWidget(lbl_title)
        title_vlo.addWidget(lbl_sub)

        header_hlo.addWidget(lbl_icon)
        header_hlo.addLayout(title_vlo)
        header_hlo.addStretch()

        layout.addLayout(header_hlo)

        # Descripción
        lbl_desc = QLabel(description)
        lbl_desc.setWordWrap(True)
        lbl_desc.setStyleSheet("font-size: 9pt; color: #BAC2DE; line-height: 1.3; background: transparent; border: none;")
        layout.addWidget(lbl_desc)

        layout.addStretch()

        # Botón de lanzamiento
        btn_launch = QPushButton(button_text)
        btn_launch.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_launch.setStyleSheet(f"""
            QPushButton {{
                background-color: {button_color};
                color: #11111B;
                font-weight: bold;
                font-size: 10pt;
                padding: 10px;
                border-radius: 8px;
                border: none;
            }}
            QPushButton:hover {{
                background-color: #F5E0DC;
            }}
            QPushButton:pressed {{
                background-color: #B4BEFE;
            }}
        """)
        btn_launch.clicked.connect(self.launch_callback)
        layout.addWidget(btn_launch)


class MainWindowLauncher(QMainWindow):
    """Ventana de Inicio Principal — Bienvenidos al Printing."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("PyPrinting 3.0 — Panel de Inicio Principal")
        self.resize(1000, 680)
        self.processes: List[QProcess] = []

        self._setup_styles()
        self._setup_ui()

    def _setup_styles(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #11111B;
            }
            QLabel {
                color: #CDD6F4;
            }
            QStatusBar {
                background-color: #181825;
                color: #A6ADC8;
                font-size: 9pt;
            }
        """)

    def _setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_vlo = QVBoxLayout(central_widget)
        main_vlo.setContentsMargins(30, 30, 30, 20)
        main_vlo.setSpacing(20)

        # ── Banner de Bienvenida ──────────────────────────────────────────────
        banner_box = QFrame()
        banner_box.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1E1E2E, stop:1 #313244);
                border: 1px solid #45475A;
                border-radius: 14px;
                padding: 20px;
            }
        """)
        banner_hlo = QHBoxLayout(banner_box)

        banner_vlo = QVBoxLayout()
        banner_vlo.setSpacing(4)

        lbl_welcome = QLabel("Bienvenidos al printing")
        lbl_welcome.setStyleSheet("font-size: 22pt; font-weight: bold; color: #89B4FA; background: transparent;")

        lbl_subtitle = QLabel("UNSAM — Nanofotónica  |  Plataforma Modular de Espectroscopía y Nanofabricación Óptica")
        lbl_subtitle.setStyleSheet("font-size: 10pt; color: #A6ADC8; background: transparent;")

        banner_vlo.addWidget(lbl_welcome)
        banner_vlo.addWidget(lbl_subtitle)
        banner_hlo.addLayout(banner_vlo)
        banner_hlo.addStretch()

        # Selector / Indicador de Modo Seguro (SAFE_MODE)
        safe_vlo = QVBoxLayout()
        self.chk_safe_mode = QCheckBox("Modo Seguro (Simulación)")
        self.chk_safe_mode.setChecked(SAFE_MODE or os.environ.get("PYPRINTING_SAFE", "0") == "1")
        self.chk_safe_mode.setToolTip("Habilita la simulación completa de platina PI, NI-DAQmx y cámara sin hardware físico.")
        self.chk_safe_mode.setStyleSheet("""
            QCheckBox {
                font-size: 10pt;
                font-weight: bold;
                color: #A6E3A1;
                background: transparent;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
            }
        """)
        self.chk_safe_mode.toggled.connect(self._toggle_safe_mode_env)

        safe_vlo.addWidget(self.chk_safe_mode)
        banner_hlo.addLayout(safe_vlo)

        main_vlo.addWidget(banner_box)

        # ── Grilla de Aplicaciones (Cards) ────────────────────────────────────
        grid = QGridLayout()
        grid.setSpacing(20)

        # Card 1: Microscopio Derecho (app.py)
        card_app = ApplicationCard(
            icon_str="🔬",
            title="Microscopio Derecho",
            subtitle="PyPrinting 3.0 Suite Completa",
            description="Plataforma orquestadora principal: microscopía confocal 2D/3D síncrona, impresión óptica fototérmica, ensamblado de dímeros plasmónicos, autofoco Z y trazas temporales.",
            button_text="🚀 Iniciar Microscopio Derecho",
            button_color="#89B4FA",
            launch_callback=lambda: self._launch_script("app.py", "Microscopio Derecho")
        )

        # Card 2: PSF Analyzer (psf_analyzer.py)
        card_psf = ApplicationCard(
            icon_str="🧬",
            title="PSF Analyzer",
            subtitle="Caracterización Analítica 2D",
            description="Ajuste analítico no lineal de 7 parámetros (Gaussiana 2D y Donut LG01), mapa de residuales, perfiles 1D por canal, barras Z dinámicas y métricas sub-nanométricas de alineación.",
            button_text="📊 Iniciar PSF Analyzer",
            button_color="#A6E3A1",
            launch_callback=lambda: self._launch_script("psf_analyzer.py", "PSF Analyzer")
        )

        # Card 3: Analizador de Imágenes (image_analyzer.py)
        card_img = ApplicationCard(
            icon_str="🖼️",
            title="Analizador de Imágenes",
            subtitle="Procesamiento y Detección Estática",
            description="Visualización y análisis gráfico sobre fotos estáticas (.tiff, .png, .jpg), calibración de escala µm/píxel, reglas tri-estado, regiones ROI y seguimiento trackpy.",
            button_text="📐 Iniciar Analizador de Imágenes",
            button_color="#F9E2AF",
            launch_callback=lambda: self._launch_script("image_analyzer.py", "Analizador de Imágenes")
        )

        # Card 4: Cámara Live View (camera.py / canon_test.py)
        card_cam = ApplicationCard(
            icon_str="📷",
            title="Cámara Réflex Live View",
            subtitle="Control Canon EOS & OpenCV",
            description="Transmisión Live View en tiempo real, balance de blancos, contraste CLim, paletas LUT (Thermal, Viridis, Inferno), disparo de alta resolución (15 MP) y modulación láser 532 nm.",
            button_text="📷 Iniciar Cámara Live View",
            button_color="#FAB387",
            launch_callback=lambda: self._launch_script("canon_test.py", "Cámara Live View")
        )

        grid.addWidget(card_app, 0, 0)
        grid.addWidget(card_psf, 0, 1)
        grid.addWidget(card_img, 1, 0)
        grid.addWidget(card_cam, 1, 1)

        main_vlo.addLayout(grid)

        # Status Bar
        self.statusBar().showMessage("Sistema listo — Seleccione un módulo para iniciar.")

    def _toggle_safe_mode_env(self, checked: bool):
        if checked:
            os.environ["PYPRINTING_SAFE"] = "1"
            self.statusBar().showMessage("Modo Seguro activado (Simulación de Hardware habilitada).")
        else:
            os.environ["PYPRINTING_SAFE"] = "0"
            self.statusBar().showMessage("Modo Laboratorio activado (Hardware físico requerido).")

    def _launch_script(self, script_name: str, app_title: str):
        script_path = Path(__file__).parent / script_name
        if not script_path.exists():
            QMessageBox.critical(self, "Error de Lanzamiento", f"No se encontró el archivo ejecutable:\n{script_path}")
            return

        env = os.environ.copy()
        if self.chk_safe_mode.isChecked():
            env["PYPRINTING_SAFE"] = "1"

        try:
            # Lanzamiento desacoplado vía subprocess.Popen para aislar procesos
            proc = subprocess.Popen([sys.executable, str(script_path)], env=env, cwd=str(script_path.parent))
            self.statusBar().showMessage(f"Lanzado '{app_title}' con PID {proc.pid}.")
        except Exception as e:
            QMessageBox.critical(self, "Error de Ejecución", f"Fallo al ejecutar {script_name}:\n{e}")

    def closeEvent(self, event):
        """Confirmación al cerrar la ventana de inicio."""
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindowLauncher()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
