#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PyPrinting 3.0 — Panel de Inicio Principal (main.py)
UNSAM — Nanofotónica

Launcher principal interactivo con interfaz gráfica moderna PyQt6 para lanzar:
1. Microscopio Derecho (app.py — PyPrinting 3.0 completo)
2. PSF Analyzer (psf_analyzer.py)
3. Analizador de Imágenes (image_analyzer.py)
4. Cámara Live View (camera.py)
5. Modulación Láser 532 nm (camera.py / Laser532Window)
6. PyPrinting 2 (Legacy — PyPrinting_UNSAM.py)
7. PySpectrum (Próximamente — Espectrometría, Termometría y Scattering)
8. Microscopio Contrapropagante (Próximamente — Excitación Doble & Objetivo Invertido)
"""

import sys
import os
import subprocess
from pathlib import Path
from typing import List, Optional

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QGridLayout, QCheckBox, QMessageBox,
    QStatusBar, QScrollArea
)
from PyQt6.QtCore import Qt, QProcess
from PyQt6.QtGui import QFont, QColor

# Importar configuración global para verificar SAFE_MODE
try:
    from config import SAFE_MODE
except ImportError:
    SAFE_MODE = False


class ApplicationCard(QFrame):
    """Tarjeta gráfica representativa para cada programa ejecutable o módulo futuro."""

    def __init__(self, icon_str: str, title: str, subtitle: str, description: str,
                 button_text: str, button_color: str, launch_callback=None,
                 is_disabled: bool = False, parent=None):
        super().__init__(parent)
        self.launch_callback = launch_callback
        self.is_disabled = is_disabled

        bg_color = "#181825" if is_disabled else "#1E1E2E"
        border_color = "#45475A" if is_disabled else "#313244"
        hover_border = "#585B70" if is_disabled else button_color

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 12px;
                padding: 14px;
            }}
            QFrame:hover {{
                border: 1px solid {hover_border};
                background-color: {"#1E1E2E" if is_disabled else "#252538"};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # Header de la tarjeta (Icono + Titulo)
        header_hlo = QHBoxLayout()
        lbl_icon = QLabel(icon_str)
        lbl_icon.setStyleSheet("font-size: 26pt; background: transparent; border: none;")

        title_vlo = QVBoxLayout()
        title_vlo.setSpacing(2)

        lbl_title = QLabel(title)
        title_color = "#A6ADC8" if is_disabled else "#CDD6F4"
        lbl_title.setStyleSheet(f"font-size: 12pt; font-weight: bold; color: {title_color}; background: transparent; border: none;")

        lbl_sub = QLabel(subtitle)
        sub_color = "#6C7086" if is_disabled else "#A6ADC8"
        lbl_sub.setStyleSheet(f"font-size: 8.5pt; color: {sub_color}; background: transparent; border: none;")

        title_vlo.addWidget(lbl_title)
        title_vlo.addWidget(lbl_sub)

        header_hlo.addWidget(lbl_icon)
        header_hlo.addLayout(title_vlo)
        header_hlo.addStretch()

        layout.addLayout(header_hlo)

        # Descripción
        lbl_desc = QLabel(description)
        lbl_desc.setWordWrap(True)
        desc_color = "#9399B2" if is_disabled else "#BAC2DE"
        lbl_desc.setStyleSheet(f"font-size: 8.5pt; color: {desc_color}; line-height: 1.3; background: transparent; border: none;")
        layout.addWidget(lbl_desc)

        layout.addStretch()

        # Botón de lanzamiento
        btn_launch = QPushButton(button_text)
        if is_disabled:
            btn_launch.setEnabled(False)
            btn_launch.setStyleSheet("""
                QPushButton {
                    background-color: #313244;
                    color: #7F849C;
                    font-weight: bold;
                    font-size: 9.5pt;
                    padding: 8px;
                    border-radius: 8px;
                    border: none;
                }
            """)
        else:
            btn_launch.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_launch.setStyleSheet(f"""
                QPushButton {{
                    background-color: {button_color};
                    color: #11111B;
                    font-weight: bold;
                    font-size: 9.5pt;
                    padding: 9px;
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
            if launch_callback:
                btn_launch.clicked.connect(launch_callback)

        layout.addWidget(btn_launch)


class MainWindowLauncher(QMainWindow):
    """Ventana de Inicio Principal — Bienvenidos al Printing."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("PyPrinting 3.0 — Panel de Inicio Principal")
        self.resize(1100, 780)
        self.processes: List[subprocess.Popen] = []

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
            QScrollArea {
                border: none;
                background-color: transparent;
            }
        """)

    def _setup_ui(self):
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        self.setCentralWidget(scroll_area)

        container = QWidget()
        scroll_area.setWidget(container)

        main_vlo = QVBoxLayout(container)
        main_vlo.setContentsMargins(25, 25, 25, 20)
        main_vlo.setSpacing(18)

        # ── Banner de Bienvenida ──────────────────────────────────────────────
        banner_box = QFrame()
        banner_box.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1E1E2E, stop:1 #313244);
                border: 1px solid #45475A;
                border-radius: 14px;
                padding: 18px 22px;
            }
        """)
        banner_hlo = QHBoxLayout(banner_box)

        banner_vlo = QVBoxLayout()
        banner_vlo.setSpacing(4)

        lbl_welcome = QLabel("Bienvenidos al printing")
        lbl_welcome.setStyleSheet("font-size: 22pt; font-weight: bold; color: #89B4FA; background: transparent;")

        lbl_subtitle = QLabel("UNSAM — Nanofotónica  |  Suite de Control, Espectroscopía Confocal y Nanofabricación Óptica")
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
        grid.setSpacing(16)

        # 1. Microscopio Derecho (app.py)
        card_app = ApplicationCard(
            icon_str="🔬",
            title="Microscopio Derecho",
            subtitle="PyPrinting 3.0 Suite Completa",
            description="Plataforma orquestadora principal: microscopía confocal 2D/3D síncrona, impresión óptica fototérmica, ensamblado de dímeros plasmónicos, autofoco Z y trazas.",
            button_text="🚀 Iniciar Microscopio Derecho",
            button_color="#89B4FA",
            launch_callback=lambda: self._launch_script("app.py", "Microscopio Derecho")
        )

        # 2. PSF Analyzer (psf_analyzer.py)
        card_psf = ApplicationCard(
            icon_str="🧬",
            title="PSF Analyzer",
            subtitle="Caracterización Analítica 2D",
            description="Ajuste analítico no lineal de 7 parámetros (Gaussiana 2D y Donut LG01), mapa de residuales, perfiles 1D por canal, barras Z dinámicas y métricas sub-nanométricas.",
            button_text="📊 Iniciar PSF Analyzer",
            button_color="#A6E3A1",
            launch_callback=lambda: self._launch_script("psf_analyzer.py", "PSF Analyzer")
        )

        # 3. Analizador de Imágenes (image_analyzer.py)
        card_img = ApplicationCard(
            icon_str="🖼️",
            title="Analizador de Imágenes",
            subtitle="Procesamiento y Detección Estática",
            description="Visualización y análisis gráfico sobre fotos estáticas (.tiff, .png, .jpg), calibración de escala µm/píxel, reglas tri-estado, regiones ROI y seguimiento trackpy.",
            button_text="📐 Iniciar Analizador de Imágenes",
            button_color="#F9E2AF",
            launch_callback=lambda: self._launch_script("image_analyzer.py", "Analizador de Imágenes")
        )

        # 4. Cámara Live View (camera.py)
        card_cam = ApplicationCard(
            icon_str="📷",
            title="Cámara Live View",
            subtitle="Control Réflex & OpenCV (camera.py)",
            description="Transmisión Live View en tiempo real, balance de blancos, contraste CLim, paletas LUT (Thermal, Viridis, Inferno) y captura fotográfica de alta resolución.",
            button_text="📷 Iniciar Cámara Live View",
            button_color="#FAB387",
            launch_callback=lambda: self._launch_script("camera.py", "Cámara Live View")
        )

        # 5. Modulación Láser 532 nm (camera.py Laser532Window)
        card_laser = ApplicationCard(
            icon_str="⚡",
            title="Modulación Láser 532 nm",
            subtitle="Control de Potencia Analógica DAC",
            description="Ventana flotante de calibración y control de voltaje analógico DAC (1.0 V a 5.0 V) en tarjeta NI-DAQmx (Dev1/ao2) para el láser verde continuo de 532 nm.",
            button_text="⚡ Iniciar Control Láser 532",
            button_color="#CBA6F7",
            launch_callback=self._launch_laser_532
        )

        # 6. PyPrinting 2 (Legacy — PyPrinting_UNSAM.py)
        card_p2 = ApplicationCard(
            icon_str="🏛️",
            title="PyPrinting 2 (Legacy)",
            subtitle="Versión Previa (PyPrinting_UNSAM.py)",
            description="Acceso directo a la versión previa del software de impresión (PyPrinting_UNSAM) para consulta y ejecución de protocolos antiguos de laboratorio.",
            button_text="🏛️ Iniciar PyPrinting 2",
            button_color="#89DCEB",
            launch_callback=self._launch_pyprinting_2
        )

        # 7. PySpectrum (En desarrollo futuro)
        card_pyspectrum = ApplicationCard(
            icon_str="🔮",
            title="PySpectrum",
            subtitle="Próximamente — Espectrometría & Termometría",
            description="Manejo integrado de espectrómetro (equivalente a Andor Solis), rutinas de nano-termometría fotónica, espectros de dispersión (scattering), escaneo de muestra y control láser.",
            button_text="🔮 En Desarrollo Futuro",
            button_color="#585B70",
            is_disabled=True
        )

        # 8. Microscopio Contrapropagante (En desarrollo futuro)
        card_contra = ApplicationCard(
            icon_str="🔍",
            title="Microscopio Contrapropagante",
            subtitle="Próximamente — Excitación Doble & Invertida",
            description="Plataforma extendida basada en PyPrinting 3.0 adaptada para observación simultánea con objetivo invertido y excitación dual por haces contrapropagantes.",
            button_text="🔍 En Desarrollo Futuro",
            button_color="#585B70",
            is_disabled=True
        )

        grid.addWidget(card_app, 0, 0)
        grid.addWidget(card_psf, 0, 1)
        grid.addWidget(card_img, 1, 0)
        grid.addWidget(card_cam, 1, 1)
        grid.addWidget(card_laser, 2, 0)
        grid.addWidget(card_p2, 2, 1)
        grid.addWidget(card_pyspectrum, 3, 0)
        grid.addWidget(card_contra, 3, 1)

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
            proc = subprocess.Popen([sys.executable, str(script_path)], env=env, cwd=str(script_path.parent))
            self.processes.append(proc)
            self.statusBar().showMessage(f"Lanzado '{app_title}' con PID {proc.pid}.")
        except Exception as e:
            QMessageBox.critical(self, "Error de Ejecución", f"Fallo al ejecutar {script_name}:\n{e}")

    def _launch_laser_532(self):
        env = os.environ.copy()
        if self.chk_safe_mode.isChecked():
            env["PYPRINTING_SAFE"] = "1"

        code = (
            "import sys; from PyQt6.QtWidgets import QApplication; "
            "from camera import Laser532Window; app = QApplication(sys.argv); "
            "win = Laser532Window(); win.show(); sys.exit(app.exec())"
        )
        try:
            proc = subprocess.Popen([sys.executable, "-c", code], env=env, cwd=str(Path(__file__).parent))
            self.processes.append(proc)
            self.statusBar().showMessage(f"Lanzado 'Modulación Láser 532 nm' con PID {proc.pid}.")
        except Exception as e:
            QMessageBox.critical(self, "Error de Ejecución", f"Fallo al ejecutar Modulación Láser 532 nm:\n{e}")

    def _launch_pyprinting_2(self):
        p2_path = Path(__file__).parent.parent / "printing2" / "PyPrinting_UNSAM.py"
        if not p2_path.exists():
            QMessageBox.warning(self, "Proyecto No Encontrado", f"No se encontró el archivo de PyPrinting 2 en:\n{p2_path}")
            return

        env = os.environ.copy()
        if self.chk_safe_mode.isChecked():
            env["PYPRINTING_SAFE"] = "1"

        try:
            proc = subprocess.Popen([sys.executable, str(p2_path)], env=env, cwd=str(p2_path.parent))
            self.processes.append(proc)
            self.statusBar().showMessage(f"Lanzado 'PyPrinting 2 (Legacy)' con PID {proc.pid}.")
        except Exception as e:
            QMessageBox.critical(self, "Error de Ejecución", f"Fallo al ejecutar PyPrinting 2:\n{e}")

    def closeEvent(self, event):
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindowLauncher()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
