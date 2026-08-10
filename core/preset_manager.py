# -*- coding: utf-8 -*-
"""
preset_manager.py — Gestión y Persistencia de Presets en Archivos .txt Especificados
PyPrinting 3.0 — UNSAM Nanofotónica

Lectura, escritura, validación y exploración de perfiles experimentales almacenados
en formato de texto plano (.txt) dentro del directorio `presets/`.
"""
from __future__ import annotations
import os
import glob
from typing import Dict, Any, List, Optional

PRESETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "presets")


class PresetManager:
    """Administra la carga y guardado de presets experimentales en archivos .txt."""

    DEFAULT_PRESET_FIELDS = {
        "name": "Preset Personalizado",
        "description": "Sin descripción",
        "stop_mode": "0",
        "umbral_rel": "1.20",
        "umbral_abs": "2.500",
        "umbral_min": "0.000",
        "umbral_down": "0.80",
        "slope_flat": "2.0",
        "tmax": "20",
        "n_hold": "5",
        "steps_before": "10",
        "steps_after": "10",
        "autofocus_every": "2",
        "shift_x": "2.0",
        "shift_y": "2.0",
        "dx": "0.03",
        "dy": "0.03",
        "scan_preprint": "True",
        "postscan": "False",
        "drift_correction": "True"
    }

    @staticmethod
    def ensure_presets_dir() -> str:
        """Garantiza la existencia del directorio `presets/` y crea perfiles .txt por defecto si está vacío."""
        if not os.path.exists(PRESETS_DIR):
            os.makedirs(PRESETS_DIR, exist_ok=True)

        txt_files = glob.glob(os.path.join(PRESETS_DIR, "*.txt"))
        if not txt_files:
            PresetManager._create_default_preset_files()
        return PRESETS_DIR

    @staticmethod
    def _create_default_preset_files():
        """Genera archivos .txt plantilla por defecto en la carpeta presets/."""
        defaults = [
            ("AuNP_60nm_ImpresionRapida.txt", {
                "name": "AuNP 60nm — Impresión Rápida",
                "description": "Configuración estándar para fototermia rápida de nanopartículas de oro de 60nm",
                "stop_mode": "0",
                "umbral_rel": "1.20",
                "umbral_down": "0.80",
                "tmax": "20",
                "autofocus_every": "2",
                "shift_x": "2.0",
                "shift_y": "2.0",
                "drift_correction": "True"
            }),
            ("AuNP_60nm_AltaPotencia.txt", {
                "name": "AuNP 60nm — Alta Potencia (Anti-Paso)",
                "description": "Salto relativo con umbral absoluto y retención n_hold anti-paso",
                "stop_mode": "1",
                "umbral_rel": "1.35",
                "umbral_abs": "2.500",
                "n_hold": "5",
                "tmax": "15",
                "autofocus_every": "2",
                "drift_correction": "True"
            }),
            ("AgNP_80nm_Nanodimeros.txt", {
                "name": "AgNP 80nm — Nanodímeros Plasmónicos",
                "description": "Impresión de alta precisión para parejas de dímeros con gap sub-50nm",
                "stop_mode": "3",
                "umbral_rel": "1.30",
                "umbral_abs": "2.000",
                "n_hold": "5",
                "slope_flat": "1.5",
                "dx": "0.03",
                "dy": "0.03",
                "scan_preprint": "True",
                "postscan": "True"
            }),
            ("Grilla_Extensa_10x10.txt", {
                "name": "Grilla Extensa 10x10 (Criterio Híbrido)",
                "description": "Grilla de 100 posiciones con autofoco Z cada 2 partículas y corrección de deriva",
                "stop_mode": "3",
                "autofocus_every": "2",
                "shift_x": "2.0",
                "shift_y": "2.0",
                "drift_correction": "True"
            })
        ]

        for fname, override_dict in defaults:
            data = PresetManager.DEFAULT_PRESET_FIELDS.copy()
            data.update(override_dict)
            path = os.path.join(PRESETS_DIR, fname)
            PresetManager.save_preset_file(path, data)

    @staticmethod
    def load_preset_file(filepath: str) -> Dict[str, str]:
        """Lee un archivo .txt de preset con formato clave = valor y retorna un diccionario estructurado."""
        data = PresetManager.DEFAULT_PRESET_FIELDS.copy()
        if not os.path.exists(filepath):
            return data

        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip().lower()
                    val = val.strip()
                    if key in data:
                        data[key] = val
        return data

    @staticmethod
    def save_preset_file(filepath: str, data: Dict[str, str]) -> str:
        """Guarda un diccionario de parámetros en un archivo .txt con el formato especificado."""
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        if not filepath.endswith(".txt"):
            filepath += ".txt"

        lines = [
            "# ==================================================================",
            f"# PyPrinting 3.0 — Preset Experimental: {data.get('name', 'Sin nombre')}",
            "# Formato de Archivo de Configuración de Impresión Fototérmica",
            "# ==================================================================",
            f"name = {data.get('name', 'Preset Personalizado')}",
            f"description = {data.get('description', 'Sin descripción')}",
            "",
            "# ── Criterio de Parada y Umbrales ──",
            f"stop_mode = {data.get('stop_mode', '0')}",
            f"umbral_rel = {data.get('umbral_rel', '1.20')}",
            f"umbral_abs = {data.get('umbral_abs', '2.500')}",
            f"umbral_min = {data.get('umbral_min', '0.000')}",
            f"umbral_down = {data.get('umbral_down', '0.80')}",
            f"slope_flat = {data.get('slope_flat', '2.0')}",
            "",
            "# ── Tiempos y Muestreo ──",
            f"tmax = {data.get('tmax', '20')}",
            f"n_hold = {data.get('n_hold', '5')}",
            f"steps_before = {data.get('steps_before', '10')}",
            f"steps_after = {data.get('steps_after', '10')}",
            "",
            "# ── Autofoco Z y Corrección de Deriva ──",
            f"autofocus_every = {data.get('autofocus_every', '2')}",
            f"shift_x = {data.get('shift_x', '2.0')}",
            f"shift_y = {data.get('shift_y', '2.0')}",
            f"dx = {data.get('dx', '0.03')}",
            f"dy = {data.get('dy', '0.03')}",
            f"scan_preprint = {data.get('scan_preprint', 'True')}",
            f"postscan = {data.get('postscan', 'False')}",
            f"drift_correction = {data.get('drift_correction', 'True')}",
            ""
        ]

        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return filepath

    @staticmethod
    def get_available_presets() -> List[Dict[str, str]]:
        """Escanea el directorio presets/ y retorna la lista de presets parseados con sus rutas."""
        pdir = PresetManager.ensure_presets_dir()
        files = glob.glob(os.path.join(pdir, "*.txt"))
        presets = []
        for f in files:
            pdict = PresetManager.load_preset_file(f)
            pdict["_filepath"] = f
            presets.append(pdict)
        return sorted(presets, key=lambda x: x.get("name", ""))
