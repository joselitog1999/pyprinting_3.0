# -*- coding: utf-8 -*-
"""
test_wiki_math_rendering.py — Pruebas de la Misión "Critical Enhancements
& Physical Modeling Corrections": Paquete A del navegador de wiki
científica (analysis/scientific_wiki_browser.py) — motor offline de
renderizado LaTeX/mathtext y extensión de wikilinks con título
descriptivo/extensión .md.

Cubre:
1. Expresiones LaTeX en bloque ($$...$$) e inline ($...$) se compilan a
   imágenes PNG embebidas como data-URI base64.
2. El cacheo LRU (_render_latex_data_uri) funciona: llamadas repetidas con
   la misma expresión retornan resultados idénticos sin recomputar.
3. LaTeX malformado no propaga excepción — cae a un <code> visible con el
   texto crudo.
4. Wikilinks con título descriptivo completo y/o extensión .md
   ([[CAT-105_Titulo_Descriptivo.md]]) resuelven al note_id canónico y
   generan un título legible.
5. Regresión: los 6 casos de wikilinks preexistentes (simple, alias, ancla,
   ancla+alias, múltiples, texto no-wikilink) no cambian de comportamiento.

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

import config  # noqa: F401

from analysis.scientific_wiki_browser import (
    _render_latex_data_uri,
    _render_math_img_tag,
    preprocess_latex_math,
    preprocess_wikilinks,
)


class TestLatexDataUriRendering:

    def test_simple_expression_renders_png_data_uri(self):
        uri = _render_latex_data_uri(r"E=mc^2")
        assert uri.startswith("data:image/png;base64,")
        assert len(uri) > len("data:image/png;base64,")

    def test_lru_cache_returns_identical_result(self):
        uri1 = _render_latex_data_uri(r"\sigma_L = \sigma_{pos}/a")
        uri2 = _render_latex_data_uri(r"\sigma_L = \sigma_{pos}/a")
        assert uri1 == uri2

    def test_different_expressions_produce_different_uris(self):
        uri1 = _render_latex_data_uri(r"a^2")
        uri2 = _render_latex_data_uri(r"b^2")
        assert uri1 != uri2

    def test_malformed_latex_does_not_raise(self):
        # mathtext inválido (llave sin cerrar) no debe propagar excepción.
        tag = _render_math_img_tag(r"\frac{1}{")
        assert "<code" in tag
        assert "img src" not in tag


class TestBlockAndInlineMathPreprocessing:

    def test_block_math_becomes_centered_img_div(self):
        out = preprocess_latex_math(r"Texto antes. $$E=mc^2$$ Texto después.")
        assert '<div align="center"' in out
        assert "<img src=\"data:image/png;base64," in out
        assert "$$" not in out

    def test_inline_math_becomes_inline_img(self):
        out = preprocess_latex_math(r"El parámetro $\gamma_L$ es adimensional.")
        assert "<img src=\"data:image/png;base64," in out
        assert '<div align="center"' not in out

    def test_mixed_block_and_inline(self):
        text = r"Vale $\sigma$ y también: $$\gamma_L = \sigma_{pos}/a$$ fin."
        out = preprocess_latex_math(text)
        assert out.count("<img src=\"data:image/png;base64,") == 2

    def test_text_without_math_is_untouched(self):
        text = "Sin fórmulas acá, solo texto plano."
        assert preprocess_latex_math(text) == text

    def test_malformed_latex_falls_back_to_code_tag_in_pipeline(self):
        out = preprocess_latex_math(r"Fórmula rota: $\frac{1}{$ fin.")
        assert "<code" in out
        assert "img src" not in out


class TestWikilinkDescriptiveTitleAndMdExtension:

    def test_wikilink_with_md_extension_only(self):
        out = preprocess_wikilinks("Ver [[CAT-105_Deriva_Termica_Compensacion.md]] aquí.")
        assert out == "Ver [Deriva Termica Compensacion](wiki://CAT-105) aquí."

    def test_wikilink_with_descriptive_title_no_extension(self):
        out = preprocess_wikilinks("[[CAT-206_Pipeline_SMLM_Picasso]]")
        assert out == "[Pipeline SMLM Picasso](wiki://CAT-206)"

    def test_wikilink_descriptive_title_alias_still_wins(self):
        out = preprocess_wikilinks("[[CAT-105_Deriva_Termica.md|Ver detalle]]")
        assert out == "[Ver detalle](wiki://CAT-105)"

    def test_wikilink_plain_id_still_works_unchanged(self):
        out = preprocess_wikilinks("[[CAT-105]]")
        assert out == "[CAT-105](wiki://CAT-105)"


# ==============================================================================
# Regresión: los 6 casos preexistentes de wikilinks no cambian de comportamiento
# tras extender WIKILINK_RE/_wikilink_repl para títulos descriptivos.
# ==============================================================================
class TestWikilinkRegressionUnchanged:

    def test_simple_wikilink(self):
        out = preprocess_wikilinks("Ver [[CAT-105]] para más detalles.")
        assert out == "Ver [CAT-105](wiki://CAT-105) para más detalles."

    def test_wikilink_with_alias(self):
        out = preprocess_wikilinks("Ver [[CAT-105|Deriva Térmica]] para más detalles.")
        assert out == "Ver [Deriva Térmica](wiki://CAT-105) para más detalles."

    def test_wikilink_with_anchor_no_alias(self):
        out = preprocess_wikilinks("[[CAT-105#Metodologia]]")
        assert out == "[CAT-105#Metodologia](wiki://CAT-105#Metodologia)"

    def test_wikilink_with_anchor_and_alias(self):
        out = preprocess_wikilinks("[[CAT-105#Metodologia|Ver más]]")
        assert out == "[Ver más](wiki://CAT-105#Metodologia)"

    def test_multiple_wikilinks_in_same_text(self):
        out = preprocess_wikilinks("Combina [[CAT-105]] con [[SYS-201|Watchdog]].")
        assert "[CAT-105](wiki://CAT-105)" in out
        assert "[Watchdog](wiki://SYS-201)" in out

    def test_non_wikilink_text_untouched(self):
        text = "Esto es texto normal [no es wikilink] y esto tampoco [[minuscula-1]]."
        out = preprocess_wikilinks(text)
        assert out == text
