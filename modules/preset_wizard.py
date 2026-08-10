# -*- coding: utf-8 -*-
"""
preset_wizard.py — Asistente Guiado (Wizard) de Creación de Presets .txt
PyPrinting 3.0 — UNSAM Nanofotónica

Diálogo interactivo multipaso (QWizard) para la creación fácil, metrológica y asistida
de perfiles experimentales guardados en archivos .txt.
"""
from __future__ import annotations
import os
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QWizard, QWizardPage, QVBoxLayout, QHBoxLayout,
                               QGridLayout, QLabel, QLineEdit, QComboBox,
                               QCheckBox, QTextEdit, QMessageBox)
from PyQt6.QtGui import QFont

from core.preset_manager import PresetManager, PRESETS_DIR


class IntroPage(QWizardPage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("🧙 Paso 1: Identificación del Preset Experimental")
        self.setSubTitle("Define el nombre descriptivo y las observaciones generales del nuevo perfil de impresión.")

        lo = QGridLayout(self)
        lo.setSpacing(10)

        self.nameEdit = QLineEdit("Nuevo Preset AuNP 60nm")
        self.nameEdit.setToolTip("Nombre claro y reconocible para el preset (ej. AuNP 60nm - Alta Potencia).")

        self.descEdit = QTextEdit("Configuración de impresión óptica optimizada.")
        self.descEdit.setFixedHeight(80)

        lo.addWidget(QLabel("<b>Nombre del Preset:</b>"), 0, 0)
        lo.addWidget(self.nameEdit, 0, 1)
        lo.addWidget(QLabel("<b>Descripción / Notas:</b>"), 1, 0)
        lo.addWidget(self.descEdit, 1, 1)

        self.registerField("preset_name*", self.nameEdit)
        self.registerField("preset_desc", self.descEdit, "plainText")


class StoppingModePage(QWizardPage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("🎯 Paso 2: Criterio de Parada y Umbrales Detección")
        self.setSubTitle("Selecciona el algoritmo de detección en tiempo real y sus umbrales fototérmicos.")

        lo = QGridLayout(self)
        lo.setSpacing(10)

        self.stop_mode_combo = QComboBox()
        self.stop_mode_combo.addItems([
            "Modo 0: Salto Relativo Estándar (I_new / I_old > Umbral)",
            "Modo 1: Salto Relativo + Umbral Absoluto (V) & Anti-Paso",
            "Modo 2: Derivada Temporal Adaptativa (dI/dt -> 0)",
            "Modo 3: Criterio Híbrido Tri-Factor (All-In-One)"
        ])
        self.stop_mode_combo.currentIndexChanged.connect(self._on_mode_changed)

        self.lbl_explanation = QLabel()
        self.lbl_explanation.setWordWrap(True)
        self.lbl_explanation.setStyleSheet("color: #89b4fa; font-style: italic; background-color: #1e1e2e; padding: 6px; border-radius: 4px;")

        self.umbral_rel_edit  = QLineEdit("1.20")
        self.umbral_abs_edit  = QLineEdit("2.500")
        self.umbral_min_edit  = QLineEdit("0.000")
        self.umbral_down_edit = QLineEdit("0.80")
        self.slope_flat_edit  = QLineEdit("2.0")

        lo.addWidget(QLabel("<b>Algoritmo de Parada:</b>"), 0, 0)
        lo.addWidget(self.stop_mode_combo, 0, 1, 1, 3)
        lo.addWidget(self.lbl_explanation, 1, 0, 1, 4)

        lo.addWidget(QLabel("Umbral Relativo:"), 2, 0); lo.addWidget(self.umbral_rel_edit, 2, 1)
        lo.addWidget(QLabel("Umbral Absoluto (V):"), 2, 2); lo.addWidget(self.umbral_abs_edit, 2, 3)

        lo.addWidget(QLabel("Umbral Mínimo (V):"), 3, 0); lo.addWidget(self.umbral_min_edit, 3, 1)
        lo.addWidget(QLabel("Umbral Caída (Down):"), 3, 2); lo.addWidget(self.umbral_down_edit, 3, 3)

        lo.addWidget(QLabel("Slope Flat (V/s):"), 4, 0); lo.addWidget(self.slope_flat_edit, 4, 1)

        self._on_mode_changed(0)

        self.registerField("stop_mode", self.stop_mode_combo)
        self.registerField("umbral_rel", self.umbral_rel_edit)
        self.registerField("umbral_abs", self.umbral_abs_edit)
        self.registerField("umbral_min", self.umbral_min_edit)
        self.registerField("umbral_down", self.umbral_down_edit)
        self.registerField("slope_flat", self.slope_flat_edit)

    def _on_mode_changed(self, idx: int):
        explanations = [
            "Modo 0: Evalúa únicamente el salto proporcional I_new / I_old > Umbral. Ideal para rápida impresión estándar.",
            "Modo 1: Requiere tanto el salto relativo como superar un voltaje absoluto en Volts y confirma con n_hold pasos anti-paso.",
            "Modo 2: Detecta la meseta de saturación cuando la derivada temporal dI/dt cae por debajo de Slope Flat.",
            "Modo 3: Algoritmo Híbrido Completo. Evalúa salto relativo, voltaje absoluto, confirmación anti-paso y pendiente meseta."
        ]
        self.lbl_explanation.setText(explanations[idx])


class TimingPage(QWizardPage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("⏱️ Paso 3: Tiempos y Adquisición Analógica")
        self.setSubTitle("Configura el tiempo máximo de irradiación por nodo y las ventanas de muestreo previo/posterior.")

        lo = QGridLayout(self)
        lo.setSpacing(10)

        self.tmax_edit         = QLineEdit("20")
        self.n_hold_edit       = QLineEdit("5")
        self.steps_before_edit = QLineEdit("10")
        self.steps_after_edit  = QLineEdit("10")

        lo.addWidget(QLabel("<b>Tiempo Máximo Tmax (s):</b>"), 0, 0); lo.addWidget(self.tmax_edit, 0, 1)
        lo.addWidget(QLabel("<b>Pasos Anti-Paso (N hold):</b>"), 0, 2); lo.addWidget(self.n_hold_edit, 0, 3)

        lo.addWidget(QLabel("Steps Before (Base):"), 1, 0); lo.addWidget(self.steps_before_edit, 1, 1)
        lo.addWidget(QLabel("Steps After (Post):"), 1, 2); lo.addWidget(self.steps_after_edit, 1, 3)

        self.registerField("tmax", self.tmax_edit)
        self.registerField("n_hold", self.n_hold_edit)
        self.registerField("steps_before", self.steps_before_edit)
        self.registerField("steps_after", self.steps_after_edit)


class FocusAndDriftPage(QWizardPage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("🔍 Paso 4: Autofoco Z y Corrección de Deriva")
        self.setSubTitle("Configura la frecuencia del autofoco Z y los desplazamientos en zonas limpias.")

        lo = QGridLayout(self)
        lo.setSpacing(10)

        self.autofocus_edit = QLineEdit("2")
        self.shift_x_edit   = QLineEdit("2.0")
        self.shift_y_edit   = QLineEdit("2.0")

        self.dx_edit = QLineEdit("0.03")
        self.dy_edit = QLineEdit("0.03")

        self.scan_preprint_check = QCheckBox("Escaneo Confocal Pre-impresión (Scan pre-print)")
        self.scan_preprint_check.setChecked(True)

        self.postscan_check = QCheckBox("Escaneo Confocal Post-impresión (Post-scan dímeros)")
        self.postscan_check.setChecked(False)

        self.drift_check = QCheckBox("Corrección Activa de Deriva Térmica/Mecánica")
        self.drift_check.setChecked(True)

        lo.addWidget(QLabel("Autofoco cada N partículas:"), 0, 0); lo.addWidget(self.autofocus_edit, 0, 1)
        lo.addWidget(QLabel("Desplazamiento Shift X (µm):"), 1, 0); lo.addWidget(self.shift_x_edit, 1, 1)
        lo.addWidget(QLabel("Desplazamiento Shift Y (µm):"), 1, 2); lo.addWidget(self.shift_y_edit, 1, 3)

        lo.addWidget(QLabel("Nanodímeros dx (µm):"), 2, 0); lo.addWidget(self.dx_edit, 2, 1)
        lo.addWidget(QLabel("Nanodímeros dy (µm):"), 2, 2); lo.addWidget(self.dy_edit, 2, 3)

        lo.addWidget(self.scan_preprint_check, 3, 0, 1, 4)
        lo.addWidget(self.postscan_check, 4, 0, 1, 4)
        lo.addWidget(self.drift_check, 5, 0, 1, 4)

        self.registerField("autofocus_every", self.autofocus_edit)
        self.registerField("shift_x", self.shift_x_edit)
        self.registerField("shift_y", self.shift_y_edit)
        self.registerField("dx", self.dx_edit)
        self.registerField("dy", self.dy_edit)
        self.registerField("scan_preprint", self.scan_preprint_check)
        self.registerField("postscan", self.postscan_check)
        self.registerField("drift_correction", self.drift_check)


class PreviewPage(QWizardPage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("📋 Paso 5: Vista Previa y Guardado del Archivo .txt")
        self.setSubTitle("Revisa el contenido formateado del archivo .txt antes de escribirlo en disco.")

        vlo = QVBoxLayout(self)
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setStyleSheet("background-color: #11111b; color: #a6e3a1; font-family: monospace; font-size: 9pt;")
        vlo.addWidget(self.preview_text)

    def initializePage(self):
        pname = self.field("preset_name") or "Nuevo Preset"
        fname = pname.replace(" ", "_").replace("—", "_") + ".txt"

        data = {
            "name": pname,
            "description": self.field("preset_desc") or "",
            "stop_mode": str(self.field("stop_mode")),
            "umbral_rel": str(self.field("umbral_rel")),
            "umbral_abs": str(self.field("umbral_abs")),
            "umbral_min": str(self.field("umbral_min")),
            "umbral_down": str(self.field("umbral_down")),
            "slope_flat": str(self.field("slope_flat")),
            "tmax": str(self.field("tmax")),
            "n_hold": str(self.field("n_hold")),
            "steps_before": str(self.field("steps_before")),
            "steps_after": str(self.field("steps_after")),
            "autofocus_every": str(self.field("autofocus_every")),
            "shift_x": str(self.field("shift_x")),
            "shift_y": str(self.field("shift_y")),
            "dx": str(self.field("dx")),
            "dy": str(self.field("dy")),
            "scan_preprint": str(self.field("scan_preprint")),
            "postscan": str(self.field("postscan")),
            "drift_correction": str(self.field("drift_correction"))
        }

        self.created_data = data
        self.suggested_path = os.path.join(PRESETS_DIR, fname)

        lines = [
            f"# Archivo de Preset Experimental: {fname}",
            f"# Ubicación Objetivo: {self.suggested_path}",
            "----------------------------------------------------------------",
            f"name = {data['name']}",
            f"description = {data['description']}",
            f"stop_mode = {data['stop_mode']}",
            f"umbral_rel = {data['umbral_rel']}",
            f"umbral_abs = {data['umbral_abs']}",
            f"umbral_min = {data['umbral_min']}",
            f"umbral_down = {data['umbral_down']}",
            f"slope_flat = {data['slope_flat']}",
            f"tmax = {data['tmax']}",
            f"n_hold = {data['n_hold']}",
            f"steps_before = {data['steps_before']}",
            f"steps_after = {data['steps_after']}",
            f"autofocus_every = {data['autofocus_every']}",
            f"shift_x = {data['shift_x']}",
            f"shift_y = {data['shift_y']}",
            f"dx = {data['dx']}",
            f"dy = {data['dy']}",
            f"scan_preprint = {data['scan_preprint']}",
            f"postscan = {data['postscan']}",
            f"drift_correction = {data['drift_correction']}"
        ]
        self.preview_text.setText("\n".join(lines))


class PresetWizardDialog(QWizard):
    """Wizard multipaso para crear y guardar presets experimentales en archivos .txt."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🧙 Asistente de Creación de Presets .txt — PyPrinting")
        self.resize(680, 520)

        self.created_preset_path = ""

        self.addPage(IntroPage())
        self.addPage(StoppingModePage())
        self.addPage(TimingPage())
        self.addPage(FocusAndDriftPage())
        self.preview_page = PreviewPage()
        self.addPage(self.preview_page)

        self.setStyleSheet("""
            QWizard {
                background-color: #1e1e2e;
                color: #cdd6f4;
            }
            QWizardPage {
                background-color: #1e1e2e;
                color: #cdd6f4;
            }
            QLabel {
                color: #cdd6f4;
            }
            QLineEdit, QComboBox, QTextEdit {
                background-color: #313244;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 4px;
                padding: 4px;
            }
            QPushButton {
                background-color: #45475a;
                color: #cdd6f4;
                border-radius: 4px;
                padding: 6px 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #89b4fa;
                color: #11111b;
            }
        """)

    def accept(self):
        try:
            data = getattr(self.preview_page, "created_data", {})
            path = getattr(self.preview_page, "suggested_path", "")
            if data and path:
                self.created_preset_path = PresetManager.save_preset_file(path, data)
                QMessageBox.information(
                    self, "Preset Creado",
                    f"¡Preset .txt creado con éxito!\n\nGuardado en:\n{self.created_preset_path}"
                )
        except Exception as e:
            QMessageBox.critical(self, "Error al Guardar Preset", f"No se pudo guardar el archivo .txt: {e}")
        super().accept()
