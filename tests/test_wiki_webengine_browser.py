# -*- coding: utf-8 -*-
"""
tests/test_wiki_webengine_browser.py
====================================
Pruebas automatizadas del navegador de documentación científica modernizado:
- Motor Chromium QWebEngineView y detección de dependencias
- Preprocesamiento de Callouts de Obsidian/GitHub (> [!NOTE], > [!TIP], etc.)
- Preservación de sintaxis matemática LaTeX para MathJax 3 SVG
- Integración con Obsidian nativo (obsidian:// URL)
- Navegación interna y resolución de wikilinks

PyPrinting 3.0 — UNSAM Nanofotónica
"""

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["PYPRINTING_SAFE"] = "1"

import pytest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QUrl

from analysis.scientific_wiki_browser import (
    HAS_WEBENGINE,
    MATHJAX_PATH,
    ScientificWikiBrowserDialog,
    preprocess_obsidian_callouts,
    preprocess_wikilinks,
)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


class TestObsidianCalloutsPreprocessing:
    """Verifica que los callouts de Obsidian se transformen correctamente en HTML Catppuccin."""

    def test_note_callout_transformation(self):
        text = "> [!NOTE] Nota Metrológica\n> Contenido de prueba con **negrita**."
        html = preprocess_obsidian_callouts(text)
        assert 'class="callout callout-note"' in html
        assert "Nota Metrológica" in html
        assert "Contenido de prueba con **negrita**." in html

    def test_all_callout_types(self):
        types = ['NOTE', 'TIP', 'IMPORTANT', 'WARNING', 'CAUTION']
        for ctype in types:
            text = f"> [!{ctype}]\n> Texto del bloque {ctype}."
            html = preprocess_obsidian_callouts(text)
            assert f'class="callout callout-{ctype.lower()}"' in html

    def test_multiline_callout(self):
        text = "> [!WARNING] Advertencia Crítica\n> Línea 1\n>\n> Línea 2 con fórmula $E=mc^2$."
        html = preprocess_obsidian_callouts(text)
        assert "Advertencia Crítica" in html
        assert "Línea 1" in html
        assert "Línea 2 con fórmula $E=mc^2$." in html

    def test_text_without_callout_unaltered(self):
        text = "Párrafo normal sin ningún callout ni cita."
        assert preprocess_obsidian_callouts(text) == text


class TestWebEngineAndMathJaxEnvironment:
    """Verifica la presencia de WebEngine y el archivo standalone de MathJax."""

    def test_webengine_is_available(self):
        assert HAS_WEBENGINE is True

    def test_mathjax_vendor_asset_exists(self):
        assert MATHJAX_PATH.is_file()
        assert MATHJAX_PATH.stat().st_size > 1_000_000  # ~2.1 MB bundle


class TestScientificWikiBrowserDialogWebEngine:
    """Pruebas de inicialización y navegación del diálogo con QWebEngineView."""

    def test_dialog_initialization(self, qapp):
        dialog = ScientificWikiBrowserDialog(initial_note_id="CAT-315")
        assert dialog is not None
        assert dialog.web_view is not None
        assert dialog._current_note_id == "CAT-315"
        assert dialog.btn_open_obsidian.isEnabled() is True
        dialog.close()

    def test_markdown_rendering_with_matrix_and_callout(self, qapp):
        dialog = ScientificWikiBrowserDialog()
        sample_md = r"""# CAT-999 Test
> [!IMPORTANT] Nota Tensorial
> Tensor de covarianza:
$$
\mathbf{\Sigma} = \begin{pmatrix} \sigma_x^2 & \sigma_{xy} \\ \sigma_{xy} & \sigma_y^2 \end{pmatrix}
$$
Ver también [[CAT-105|Deriva Térmica]].
"""
        html = dialog._render_markdown(sample_md)
        # MathJax script tag must be included
        assert "MathJax-script" in html
        assert "tex-svg.js" in html
        # Matrix syntax must be preserved intact without escaped backslashes
        assert r"\begin{pmatrix}" in html
        assert r"\end{pmatrix}" in html
        # Callout markup must be present
        assert "callout-important" in html
        # Wikilink must be resolved
        assert "wiki://CAT-105" in html
        dialog.close()

    def test_navigation_history(self, qapp):
        dialog = ScientificWikiBrowserDialog(initial_note_id="CAT-001")
        assert dialog._current_note_id == "CAT-001"
        assert dialog.btn_back.isEnabled() is False

        dialog.navigate_to("CAT-105")
        assert dialog._current_note_id == "CAT-105"
        assert dialog.btn_back.isEnabled() is True

        dialog._go_back()
        assert dialog._current_note_id == "CAT-001"
        assert dialog.btn_forward.isEnabled() is True
        dialog.close()

    def test_open_in_obsidian_url_construction(self, qapp):
        dialog = ScientificWikiBrowserDialog(initial_note_id="CAT-315")
        assert dialog._current_note_path is not None
        rel_path = dialog._current_note_path.relative_to(BASE_DIR).as_posix()
        assert "CAT-315" in rel_path
        dialog.close()
