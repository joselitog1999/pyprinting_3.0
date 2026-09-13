#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PyPrinting 3.0 — Panel de Inicio Principal (main.py)
UNSAM — Nanofotónica

Launcher principal interactivo con interfaz gráfica moderna PyQt6 organizada en 3 categorías:
Bloque 1: Aplicaciones Instrumentales (Control y Adquisición en Vivo)
  1. Microscopio Derecho (app.py — PyPrinting 3.0 completo)
  2. PySpectrum 3.0 (pyspectrum.py — Espectrometría, Shamrock y Andor CCD)
  3. Microscopio Contrapropagante (contrapropagante.py — Excitación Doble TOP/BOT)
  4. Cámara Live View (camera.py — Adquisición en tiempo real y LUTs)
  5. Modulación Láser 532 nm (camera.py / Laser532Window)
  6. Diseñador de Redes 2D (grid_generator.py — Cristalografía, Bravais y P0)

── Subtítulo 1: Herramientas de Análisis y Procesamiento ──
  7. Analizador SIF (sif_analyzer.py — Andor Solis, Transmitancia y Extinción)
  8. Analizador Raman & SERS (raman_analyzer.py — Línea base, picos y termometría)
  9. PSF Analyzer (psf_analyzer.py — Ajuste analítico Gauss/Donut 2D)
  10. Analizador de Imágenes (image_analyzer.py — Medición estática y tracking)

── Subtítulo 2: Documentación, Diagnósticos y Configuración ──
  11. Tablero de Conexiones (modules/hardware_dashboard.py — Seguridad e I/O)
  12. Documentación y Créditos (Manual de Usuario, README y Créditos)
"""

import sys
import os
import subprocess
import webbrowser
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
        lbl_title.setStyleSheet(f"font-size: 11.5pt; font-weight: bold; color: {title_color}; background: transparent; border: none;")

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
                    font-size: 9pt;
                    padding: 8px;
                    border-radius: 7px;
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
                    font-size: 9pt;
                    padding: 8px;
                    border-radius: 7px;
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


class DocAndCreditsCard(QFrame):
    """Tarjeta especial de Documentación, Guías de Usuario y Créditos del Autor."""

    def __init__(self, open_doc_callback, show_credits_callback, parent=None):
        super().__init__(parent)
        self.open_doc_callback = open_doc_callback
        self.show_credits_callback = show_credits_callback

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("""
            QFrame {
                background-color: #1E1E2E;
                border: 1px solid #B4BEFE;
                border-radius: 12px;
                padding: 14px;
            }
            QFrame:hover {
                border: 1px solid #89B4FA;
                background-color: #252538;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # Header
        header_hlo = QHBoxLayout()
        lbl_icon = QLabel("📚")
        lbl_icon.setStyleSheet("font-size: 26pt; background: transparent; border: none;")

        title_vlo = QVBoxLayout()
        title_vlo.setSpacing(2)

        lbl_title = QLabel("Documentación y Créditos")
        lbl_title.setStyleSheet("font-size: 11.5pt; font-weight: bold; color: #B4BEFE; background: transparent; border: none;")

        lbl_sub = QLabel("Manual, README & Créditos")
        lbl_sub.setStyleSheet("font-size: 8.5pt; color: #A6ADC8; background: transparent; border: none;")

        title_vlo.addWidget(lbl_title)
        title_vlo.addWidget(lbl_sub)

        header_hlo.addWidget(lbl_icon)
        header_hlo.addLayout(title_vlo)
        header_hlo.addStretch()

        layout.addLayout(header_hlo)

        # Descripción con Crédito explícito
        lbl_desc = QLabel(
            "Desarrollado por <b>José Luis González Peñafiel</b> (Becario Doctoral CONICET, INS-UNSAM, San Martín, Buenos Aires, Argentina). Acceda al manual de usuario y documentación técnica."
        )
        lbl_desc.setWordWrap(True)
        lbl_desc.setStyleSheet("font-size: 8.5pt; color: #BAC2DE; line-height: 1.3; background: transparent; border: none;")
        layout.addWidget(lbl_desc)

        layout.addStretch()

        # Fila de Botones
        btns_hlo = QHBoxLayout()
        btns_hlo.setSpacing(6)

        btn_manual = QPushButton("📘 Manual")
        btn_manual.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_manual.setStyleSheet("""
            QPushButton {
                background-color: #89B4FA;
                color: #11111B;
                font-weight: bold;
                font-size: 8.5pt;
                padding: 7px;
                border-radius: 6px;
                border: none;
            }
            QPushButton:hover { background-color: #B4BEFE; }
        """)
        btn_manual.clicked.connect(lambda: self.open_doc_callback("MANUAL_USUARIO.md"))

        btn_readme = QPushButton("📖 README")
        btn_readme.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_readme.setStyleSheet("""
            QPushButton {
                background-color: #74C7EC;
                color: #11111B;
                font-weight: bold;
                font-size: 8.5pt;
                padding: 7px;
                border-radius: 6px;
                border: none;
            }
            QPushButton:hover { background-color: #89DCEB; }
        """)
        btn_readme.clicked.connect(lambda: self.open_doc_callback("README.md"))

        btn_credits = QPushButton("🎓 Créditos")
        btn_credits.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_credits.setStyleSheet("""
            QPushButton {
                background-color: #F5C2E7;
                color: #11111B;
                font-weight: bold;
                font-size: 8.5pt;
                padding: 7px;
                border-radius: 6px;
                border: none;
            }
            QPushButton:hover { background-color: #CBA6F7; }
        """)
        btn_credits.clicked.connect(self.show_credits_callback)

        btns_hlo.addWidget(btn_manual)
        btns_hlo.addWidget(btn_readme)
        btns_hlo.addWidget(btn_credits)

        layout.addLayout(btns_hlo)


class SectionHeader(QFrame):
    """Subtítulo visual divisorio con icono, título de categoría, descripción y línea estilizada con gradiente."""

    def __init__(self, icon_str: str, title: str, subtitle: str = "",
                 accent_color: str = "#89B4FA", parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QFrame {
                background-color: transparent;
                border: none;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 18, 4, 6)
        layout.setSpacing(6)

        # Fila de Título y Subtítulo
        hlo = QHBoxLayout()
        hlo.setSpacing(10)

        lbl_icon = QLabel(icon_str)
        lbl_icon.setStyleSheet("font-size: 16pt; background: transparent; border: none;")

        lbl_title = QLabel(title)
        lbl_title.setStyleSheet(f"""
            font-size: 13.5pt;
            font-weight: bold;
            color: {accent_color};
            background: transparent;
            border: none;
            letter-spacing: 0.5px;
        """)

        hlo.addWidget(lbl_icon)
        hlo.addWidget(lbl_title)

        if subtitle:
            lbl_sub = QLabel(f"|   {subtitle}")
            lbl_sub.setStyleSheet("""
                font-size: 9pt;
                color: #A6ADC8;
                background: transparent;
                border: none;
            """)
            hlo.addWidget(lbl_sub)

        hlo.addStretch()
        layout.addLayout(hlo)

        # Línea divisoria decorativa con gradiente
        line = QFrame()
        line.setFixedHeight(2)
        line.setStyleSheet(f"""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 {accent_color},
                stop:0.45 {accent_color}99,
                stop:0.80 #313244,
                stop:1 transparent);
            border: none;
        """)
        layout.addWidget(line)


class MainWindowLauncher(QMainWindow):
    """Ventana de Inicio Principal — Bienvenidos al Printing."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("PyPrinting 3.0 — Panel de Inicio Principal")
        self.resize(1200, 780)
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

        # ── Grilla de Aplicaciones (3 opciones por fila) ──────────────────────
        grid = QGridLayout()
        grid.setSpacing(16)

        # ── FILA 1 ── (Microscopio derecho, PySpectrum, Contrapropagante)
        # 1. Microscopio Derecho (app.py)
        card_app = ApplicationCard(
            icon_str="🔬",
            title="Microscopio Derecho",
            subtitle="PyPrinting 3.0 Suite Completa",
            description="Plataforma orquestadora principal: microscopía confocal 2D/3D síncrona, impresión óptica, dímeros plasmónicos, autofoco Z y trazas.",
            button_text="🚀 Iniciar Microscopio Derecho",
            button_color="#89B4FA",
            launch_callback=lambda: self._launch_script("app.py", "Microscopio Derecho")
        )

        # 2. PySpectrum 3.0 (pyspectrum.py)
        card_pyspectrum = ApplicationCard(
            icon_str="🌈",
            title="PySpectrum 3.0",
            subtitle="Espectroscopía & Mapeo Hiperespectral",
            description="Control de espectrógrafo Andor Shamrock, cámara Andor CCD, cosido continuo Step & Glue, mapeo hiperespectral 2D/3D y cinéticas.",
            button_text="🌈 Iniciar PySpectrum 3.0",
            button_color="#CBA6F7",
            launch_callback=lambda: self._launch_script("pyspectrum.py", "PySpectrum 3.0")
        )

        # 3. Microscopio Contrapropagante (contrapropagante.py)
        card_contra = ApplicationCard(
            icon_str="🔍",
            title="Microscopio Contrapropagante",
            subtitle="Excitación Dual & Confocales TOP/BOT",
            description="Plataforma extendida para observación e iluminación síncrona por objetivo derecho (TOP) e invertido (BOT), centrado sub-nanométrico y vector diferencia.",
            button_text="🔍 Iniciar Contrapropagante",
            button_color="#F38BA8",
            launch_callback=lambda: self._launch_script("contrapropagante.py", "Microscopio Contrapropagante")
        )

        # 4. Cámara Live View (camera.py)
        card_cam = ApplicationCard(
            icon_str="📷",
            title="Cámara Live View",
            subtitle="Control Réflex & OpenCV (camera.py)",
            description="Transmisión Live View en tiempo real, balance de blancos, contraste CLim, paletas LUT (Thermal, Viridis, Inferno) y captura fotográfica.",
            button_text="📷 Iniciar Cámara Live View",
            button_color="#FAB387",
            launch_callback=lambda: self._launch_script("camera.py", "Cámara Live View")
        )

        # 5. Modulación Láser 532 nm (camera.py Laser532Window)
        card_laser = ApplicationCard(
            icon_str="⚡",
            title="Láser verde (532 nm)",
            subtitle="Control de Potencia & Shutter 532",
            description="Ventana flotante de control de voltaje analógico DAC (1.0 V a 5.0 V) y conmutador directo del obturador verde de 532 nm.",
            button_text="⚡ Iniciar Control Láser 532",
            button_color="#CBA6F7",
            launch_callback=self._launch_laser_532
        )

        # 6. PSF Analyzer (psf_analyzer.py)
        card_psf = ApplicationCard(
            icon_str="🧬",
            title="PSF Analyzer",
            subtitle="Caracterización Analítica 2D",
            description="Ajuste analítico no lineal de 7 parámetros (Gaussiana 2D y Donut LG01), residuales, perfiles 1D por canal y métricas sub-nanométricas.",
            button_text="📊 Iniciar PSF Analyzer",
            button_color="#A6E3A1",
            launch_callback=lambda: self._launch_script("psf_analyzer.py", "PSF Analyzer")
        )

        # 7. Analizador de Imágenes (image_analyzer.py)
        card_img = ApplicationCard(
            icon_str="🖼️",
            title="Analizador de Imágenes",
            subtitle="Procesamiento y Detección Estática",
            description="Visualización y análisis gráfico sobre fotos estáticas (.tiff, .png, .jpg), calibración de escala µm/píxel, reglas tri-estado y tracking trackpy.",
            button_text="📐 Iniciar Analizador de Imágenes",
            button_color="#F9E2AF",
            launch_callback=lambda: self._launch_script("image_analyzer.py", "Analizador de Imágenes")
        )

        # 8. Diseñador de Redes Cristalinas 2D (grid_generator.py)
        card_lattice = ApplicationCard(
            icon_str="📐",
            title="Diseñador de Redes 2D",
            subtitle="Cristalografía, Superredes & P0",
            description="Generador universal de redes de Bravais 2D, Grafeno, Kagome, Lieb, superredes Moiré rotadas, figuras contenedoras (hexágonos, círculos) y cuadratura P0.",
            button_text="📐 Iniciar Diseñador de Redes",
            button_color="#CBA6F7",
            launch_callback=lambda: self._launch_script("grid_generator.py", "Diseñador de Redes 2D")
        )

        # 9. Tablero de Conexiones & Hardware (modules/hardware_dashboard.py)
        card_hardware = ApplicationCard(
            icon_str="🛡️",
            title="Tablero de Conexiones",
            subtitle="Seguridad & Aislamiento I/O",
            description="Monitoreo en vivo de matriz de instrumentos (NI-DAQmx, PI Piezo, Cámara, Láser, Espectrómetro), aislamiento por software (Mock) y bitácora I/O.",
            button_text="🛡️ Abrir Tablero de Conexiones",
            button_color="#A6E3A1",
            launch_callback=self._launch_hardware_dashboard
        )

        # 10. Analizador Raman & SERS (raman_analyzer.py)
        card_raman = ApplicationCard(
            icon_str="📊",
            title="Analizador Raman & SERS",
            subtitle="Andor Solis, Línea Base & Picos",
            description="Procesamiento espectroscópico cuantitativo: supresión de fluorescencia (AsLS/AirPLS), rayos cósmicos, conversión a cm⁻¹, reglas duales y termometría.",
            button_text="📊 Iniciar Analizador Raman",
            button_color="#89B4FA",
            launch_callback=lambda: self._launch_script("raman_analyzer.py", "Analizador Raman & SERS")
        )

        # 11. Analizador SIF (sif_analyzer.py)
        card_sif = ApplicationCard(
            icon_str="🔬",
            title="Analizador SIF (Andor)",
            subtitle="Transmitancia, 1D/2D & Sets",
            description="Procesamiento de espectros SIF de Andor Solis (1D binned y 2D multi-pixel), ROI espacial de ranura, sustracción de fondo, transmitancia, extinción, filtros y propagación de errores.",
            button_text="🔬 Iniciar Analizador SIF",
            button_color="#A6E3A1",
            launch_callback=lambda: self._launch_script("sif_analyzer.py", "Analizador SIF (Andor)")
        )

        # 12. Documentación y Créditos
        card_docs = DocAndCreditsCard(
            open_doc_callback=self._open_document,
            show_credits_callback=self._show_credits
        )

        # Ubicación en grilla organizada en 3 categorías mediante dos subtítulos visuales:

        # ── BLOQUE 1: APLICACIONES INSTRUMENTALES (Control & Adquisición) ─────
        # Fila 0: Microscopio Derecho, PySpectrum 3.0, Microscopio Contrapropagante
        grid.addWidget(card_app, 0, 0)
        grid.addWidget(card_pyspectrum, 0, 1)
        grid.addWidget(card_contra, 0, 2)

        # Fila 1: Cámara Live View, Modulación Láser 532 nm, Diseñador de Redes 2D
        grid.addWidget(card_cam, 1, 0)
        grid.addWidget(card_laser, 1, 1)
        grid.addWidget(card_lattice, 1, 2)

        # ── SUBTÍTULO 1: HERRAMIENTAS DE ANÁLISIS Y PROCESAMIENTO ────────────
        sub_analisis = SectionHeader(
            icon_str="📊",
            title="Herramientas de Análisis y Procesamiento",
            subtitle="Espectroscopía cuantitativa SIF / Raman, caracterización PSF y análisis de imágenes",
            accent_color="#A6E3A1"
        )
        grid.addWidget(sub_analisis, 2, 0, 1, 3)

        # ── BLOQUE 2: HERRAMIENTAS DE ANÁLISIS ────────────────────────────────
        # Fila 3: Analizador SIF (Andor), Analizador Raman & SERS, PSF Analyzer
        grid.addWidget(card_sif, 3, 0)
        grid.addWidget(card_raman, 3, 1)
        grid.addWidget(card_psf, 3, 2)

        # 12. Analizador de Desorden y Redes 2D (lattice_disorder_gui.py)
        card_lattice_disorder = ApplicationCard(
            icon_str="✨",
            title="Analizador de Redes & Desorden",
            subtitle="Fourier 2D, Debye-Waller & Monte Carlo",
            description="Metrología de desorden posicional en redes periódicas 2D a partir de confocales o coordenadas: SMLM (Picasso/Trackpy), NUFFT 2D continua, KDTree acotado, g(r) y atenuación de Debye-Waller.",
            button_text="✨ Iniciar Analizador de Desorden",
            button_color="#CBA6F7",
            launch_callback=lambda: self._launch_script("lattice_disorder_gui.py", "Analizador de Desorden y Redes 2D")
        )

        # Fila 4: Analizador de Imágenes, Analizador de Redes & Desorden
        grid.addWidget(card_img, 4, 0)
        grid.addWidget(card_lattice_disorder, 4, 1)

        # ── SUBTÍTULO 2: DOCUMENTACIÓN Y CONFIGURACIÓN (SETTINGS) ─────────────
        sub_docs_settings = SectionHeader(
            icon_str="⚙️",
            title="Documentación, Diagnósticos y Configuración",
            subtitle="Manuales operativos, arquitectura de hardware, telemetría y metadatos",
            accent_color="#F9E2AF"
        )
        grid.addWidget(sub_docs_settings, 5, 0, 1, 3)

        # ── BLOQUE 3: DOCUMENTACIÓN Y SETTINGS ────────────────────────────────
        # Fila 6: Tablero de Conexiones & Hardware, Documentación y Créditos
        grid.addWidget(card_hardware, 6, 0)
        grid.addWidget(card_docs, 6, 1)

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

    def _find_script(self, script_name: str) -> Optional[Path]:
        root = Path(__file__).parent
        candidates = [
            root / script_name,
            root / "modules" / script_name,
            root / "analysis" / script_name,
            root / "core" / script_name,
        ]
        for c in candidates:
            if c.exists():
                return c
        return None

    def _launch_script(self, script_name: str, app_title: str):
        script_path = self._find_script(script_name)
        if not script_path or not script_path.exists():
            QMessageBox.critical(self, "Error de Lanzamiento", f"No se encontró el archivo ejecutable:\n{script_name}")
            return

        # Limpiar lista de procesos terminados
        self.processes = [p for p in self.processes if p.poll() is None]

        # Protección de exclusión mutua de hardware físico en Modo Laboratorio
        is_safe_mode = self.chk_safe_mode.isChecked()
        if not is_safe_mode and script_name in ("app.py", "contrapropagante.py"):
            other_script = "contrapropagante.py" if script_name == "app.py" else "app.py"
            other_title = "Microscopio Contrapropagante" if script_name == "app.py" else "Microscopio Derecho"

            for proc in self.processes:
                if proc.poll() is None and getattr(proc, "_script_name", None) == other_script:
                    QMessageBox.warning(
                        self,
                        "Recurso de Hardware Bloqueado",
                        f"No es posible iniciar '{app_title}' en MODO LABORATORIO mientras '{other_title}' se encuentra en ejecución.\n\n"
                        f"Ambos programas compiten de forma directa por los recursos físicos de la platina PI E-517 y la tarjeta NI-DAQmx.\n\n"
                        f"Por favor, cierre la sesión de '{other_title}' antes de continuar o active la casilla de 'Modo Seguro (Simulación)'."
                    )
                    return

        env = os.environ.copy()
        env["PYPRINTING_SAFE"] = "1" if is_safe_mode else "0"

        try:
            proc = subprocess.Popen([sys.executable, str(script_path)], env=env, cwd=str(Path(__file__).parent))
            proc._script_name = script_name
            self.processes.append(proc)
            self.statusBar().showMessage(f"Lanzado '{app_title}' con PID {proc.pid}.")
        except Exception as e:
            QMessageBox.critical(self, "Error de Ejecución", f"Fallo al ejecutar {script_name}:\n{e}")

    def _launch_laser_532(self):
        env = os.environ.copy()
        env["PYPRINTING_SAFE"] = "1" if self.chk_safe_mode.isChecked() else "0"

        code = (
            "import sys; from PyQt6.QtWidgets import QApplication; "
            "from modules.camera import Laser532Window, Laser532Backend; "
            "app = QApplication(sys.argv); "
            "win = Laser532Window(); backend = Laser532Backend(); "
            "backend.make_connection(win); "
            "win.show(); sys.exit(app.exec())"
        )
        try:
            proc = subprocess.Popen([sys.executable, "-c", code], env=env, cwd=str(Path(__file__).parent))
            self.processes.append(proc)
            self.statusBar().showMessage(f"Lanzado 'Modulación Láser 532 nm' con PID {proc.pid}.")
        except Exception as e:
            QMessageBox.critical(self, "Error de Ejecución", f"Fallo al ejecutar Modulación Láser 532 nm:\n{e}")

    def _launch_hardware_dashboard(self):
        env = os.environ.copy()
        env["PYPRINTING_SAFE"] = "1" if self.chk_safe_mode.isChecked() else "0"

        code = (
            "import sys; from PyQt6.QtWidgets import QApplication; "
            "from modules.hardware_dashboard import HardwareDashboardWindow; app = QApplication(sys.argv); "
            "win = HardwareDashboardWindow(); win.show(); sys.exit(app.exec())"
        )
        try:
            proc = subprocess.Popen([sys.executable, "-c", code], env=env, cwd=str(Path(__file__).parent))
            self.processes.append(proc)
            self.statusBar().showMessage(f"Lanzado 'Tablero de Conexiones & Hardware' con PID {proc.pid}.")
        except Exception as e:
            QMessageBox.critical(self, "Error de Ejecución", f"Fallo al ejecutar Tablero de Conexiones:\n{e}")


    def _open_document(self, filename: str):
        root = Path(__file__).parent
        doc_path = root / filename if (root / filename).exists() else root / "docs" / filename
        if not doc_path.exists():
            QMessageBox.warning(self, "Archivo No Encontrado", f"No se encontró el archivo de documentación:\n{doc_path}")
            return

        try:
            if sys.platform == "win32":
                os.startfile(str(doc_path))
            else:
                webbrowser.open(doc_path.as_uri())
            self.statusBar().showMessage(f"Abierto documento: {filename}")
        except Exception as e:
            QMessageBox.critical(self, "Error al abrir documento", f"No se pudo abrir el archivo {filename}:\n{e}")

    def _show_credits(self):
        msg = QMessageBox(self)
        msg.setWindowTitle("Créditos e Información Institucional")
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.setText("""
            <h3>🔬 PyPrinting 3.0 — UNSAM Nanofotónica</h3>
            <p><b>Autor Principal:</b> José Luis González Peñafiel</p>
            <p><b>Cargo:</b> Becario Doctoral CONICET</p>
            <p><b>Institución:</b> Instituto de Nanosistemas (INS-UNSAM)</p>
            <p><b>Ubicación:</b> San Martín, Buenos Aires, Argentina</p>
            <hr>
            <p><b>Contacto:</b> <a href="mailto:jose.lito.g.1999@gmail.com">jose.lito.g.1999@gmail.com</a></p>
            <p><b>Repositorio GitHub:</b> <a href="https://github.com/joselitog1999/pyprinting_3.0">github.com/joselitog1999/pyprinting_3.0</a></p>
        """)
        msg.exec()

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
