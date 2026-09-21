# -*- coding: utf-8 -*-
"""
test_scientific_wiki_browser.py — Pruebas del Navegador de Documentación
Científica (Paquete 9): ScientificWikiBrowserDialog.

Cubre:
1. Descubrimiento y categorización del índice de notas reales del repositorio
   (reportes/cientificos, reportes/sistema, docs/modulos).
2. Preprocesamiento de enlaces estilo Obsidian [[CAT-xxx]] / [[CAT-xxx|Alias]]
   (con y sin ancla '#seccion') a sintaxis Markdown intermedia real.
3. navigate_to() carga contenido real y empuja historial; una segunda llamada
   con nota distinta crece el historial en una entrada (no lo duplica/resetea).
4. Navegación Atrás/Adelante a través de >= 3 entradas de historial.
5. El filtro de búsqueda reduce el árbol a las entradas coincidentes
   (insensible a mayúsculas/minúsculas).
6. Un note_id inexistente pasado a navigate_to() no produce una excepción —
   muestra un estado de error controlado.
7. Resolución de anchorClicked para URLs 'wiki://' — se determina empíricamente
   si el ID cae en host() o en path() para esta versión de Qt.

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

import pytest
from PyQt6.QtCore import QUrl, Qt
from PyQt6.QtWidgets import QApplication

from analysis.scientific_wiki_browser import (
    ScientificWikiBrowserDialog,
    discover_notes,
    preprocess_wikilinks,
)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture
def dlg(app):
    d = ScientificWikiBrowserDialog(initial_note_id="CAT-001")
    yield d
    d.close()
    d.deleteLater()


# ==============================================================================
# 1. Índice de notas — descubrimiento y categorización real
# ==============================================================================
class TestNoteIndexDiscovery:

    def test_discovers_real_cat_note(self):
        index, titles, categories = discover_notes()
        assert "CAT-001" in index
        assert index["CAT-001"].is_file()
        assert categories["CAT-001"] == "CAT"
        assert titles["CAT-001"]  # título no vacío, extraído del '# ' inicial

    def test_discovers_real_sys_note(self):
        index, titles, categories = discover_notes()
        assert "SYS-001" in index
        assert categories["SYS-001"] == "SYS"

    def test_discovers_real_mod_note(self):
        index, titles, categories = discover_notes()
        assert "MOD-08" in index
        assert categories["MOD-08"] == "MOD"

    def test_readme_in_modulos_is_not_indexed(self):
        # docs/modulos/README.md no cumple el patrón MOD-xxx_*.md y no debe colarse.
        index, _, _ = discover_notes()
        assert "README" not in index

    def test_index_paths_are_absolute_and_readable(self):
        index, _, _ = discover_notes()
        for note_id, path in index.items():
            assert path.is_absolute(), f"{note_id} no tiene ruta absoluta"
            assert path.suffix == ".md"


# ==============================================================================
# 2. Preprocesamiento de wikilinks estilo Obsidian
# ==============================================================================
class TestWikilinkPreprocessing:

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


# ==============================================================================
# 3. navigate_to() — carga real y crecimiento de historial
# ==============================================================================
class TestNavigateToAndHistory:

    def test_navigate_to_loads_real_note_content(self, dlg):
        dlg.navigate_to("CAT-001")
        html = dlg.text_browser.toHtml()
        assert "CAT-001" in html or "Apéndice" in html
        assert dlg._current_note_id == "CAT-001"

    def test_navigate_to_pushes_history_entry(self, dlg):
        dlg.navigate_to("CAT-001")
        n_before = len(dlg._history)
        dlg.navigate_to("SYS-001")
        assert len(dlg._history) == n_before + 1
        assert dlg._history[dlg._history_pos] == "SYS-001"

    def test_navigate_to_same_note_does_not_duplicate_history(self, dlg):
        dlg.navigate_to("CAT-001")
        n_before = len(dlg._history)
        dlg.navigate_to("CAT-001")
        assert len(dlg._history) == n_before

    def test_window_title_reflects_current_note(self, dlg):
        dlg.navigate_to("CAT-001")
        assert "CAT-001" in dlg.windowTitle()


# ==============================================================================
# 4. Navegación Atrás / Adelante
# ==============================================================================
class TestBackForwardNavigation:

    def test_back_forward_across_three_entries(self, dlg):
        dlg.navigate_to("CAT-001")
        dlg.navigate_to("SYS-001")
        dlg.navigate_to("MOD-08")
        assert dlg._current_note_id == "MOD-08"

        dlg._go_back()
        assert dlg._current_note_id == "SYS-001"

        dlg._go_back()
        assert dlg._current_note_id == "CAT-001"

        # Ya no se puede retroceder más allá del primer elemento.
        assert not dlg.btn_back.isEnabled()

        dlg._go_forward()
        assert dlg._current_note_id == "SYS-001"

        dlg._go_forward()
        assert dlg._current_note_id == "MOD-08"
        assert not dlg.btn_forward.isEnabled()

    def test_navigating_after_back_truncates_forward_history(self, dlg):
        dlg.navigate_to("CAT-001")
        dlg.navigate_to("SYS-001")
        dlg.navigate_to("MOD-08")
        dlg._go_back()  # ahora en SYS-001, con MOD-08 en el "futuro"
        dlg.navigate_to("MOD-09")  # descarta el futuro (MOD-08)
        assert dlg._history[-1] == "MOD-09"
        assert not dlg.btn_forward.isEnabled()


# ==============================================================================
# 5. Filtro de búsqueda del árbol
# ==============================================================================
class TestSearchFiltering:

    def test_search_narrows_to_matching_note_id(self, dlg):
        dlg.search_edit.setText("cat-001")  # minúsculas deliberadamente
        visible_ids = _collect_visible_note_ids(dlg)
        assert "CAT-001" in visible_ids
        assert "SYS-001" not in visible_ids

    def test_search_matches_title_case_insensitively(self, dlg):
        # Buscar un fragmento del título de CAT-001 en minúsculas.
        title = dlg._note_titles["CAT-001"]
        fragment = title.split()[0].lower()
        dlg.search_edit.setText(fragment)
        visible_ids = _collect_visible_note_ids(dlg)
        assert "CAT-001" in visible_ids

    def test_clearing_search_restores_all_entries(self, dlg):
        dlg.search_edit.setText("cat-001")
        dlg.search_edit.setText("")
        visible_ids = _collect_visible_note_ids(dlg)
        assert "SYS-001" in visible_ids
        assert "MOD-08" in visible_ids


def _collect_visible_note_ids(dlg):
    visible = []
    for i in range(dlg.tree.topLevelItemCount()):
        top = dlg.tree.topLevelItem(i)
        if top.isHidden():
            continue
        for j in range(top.childCount()):
            child = top.child(j)
            if not child.isHidden():
                note_id = child.data(0, Qt.ItemDataRole.UserRole)
                visible.append(note_id)
    return visible


# ==============================================================================
# 6. Manejo elegante de note_id inexistente
# ==============================================================================
class TestMissingNoteGraceful:

    def test_nonexistent_note_id_does_not_crash(self, dlg):
        dlg.navigate_to("CAT-999999")  # no existe
        assert dlg._current_note_id == "CAT-999999"
        html = dlg.text_browser.toHtml()
        assert "no disponible" in html.lower() or "no se pudo cargar" in html.lower()

    def test_nonexistent_note_id_shows_error_status(self, dlg):
        dlg.navigate_to("XYZ-000")
        assert "no se encontró" in dlg.status_label.text().lower()


# ==============================================================================
# 7. Resolución de URLs wiki:// (anchorClicked) — host() vs path()
# ==============================================================================
class TestWikiUrlResolution:

    def test_resolve_wiki_url_simple(self):
        url = QUrl("wiki://CAT-105")
        note_id, anchor = ScientificWikiBrowserDialog.resolve_wiki_url(url)
        assert note_id == "CAT-105"
        assert anchor is None

    def test_resolve_wiki_url_with_fragment(self):
        url = QUrl("wiki://CAT-105#seccion")
        note_id, anchor = ScientificWikiBrowserDialog.resolve_wiki_url(url)
        assert note_id == "CAT-105"
        assert anchor == "seccion"

    def test_qurl_authority_form_lands_in_host_not_path(self):
        # Verificación empírica directa y explícita (requerida por la tarea):
        # para 'wiki://CAT-105', PyQt6 coloca el identificador en host()
        # (normalizado a minúsculas por las reglas de autoridad de URL),
        # y deja path() vacío.
        url = QUrl("wiki://CAT-105")
        assert url.host() == "cat-105"
        assert url.path() == ""

    def test_non_wiki_scheme_returns_none(self):
        url = QUrl("https://example.org/CAT-105")
        note_id, anchor = ScientificWikiBrowserDialog.resolve_wiki_url(url)
        assert note_id is None
        assert anchor is None

    def test_anchor_clicked_navigates_for_known_note(self, dlg):
        dlg.navigate_to("CAT-001")
        url = QUrl("wiki://sys-001")
        dlg._on_anchor_clicked(url)
        assert dlg._current_note_id == "SYS-001"

    def test_anchor_clicked_reports_broken_link_without_crash(self, dlg):
        dlg.navigate_to("CAT-001")
        url = QUrl("wiki://does-not-exist-999")
        dlg._on_anchor_clicked(url)
        # No navega (la nota actual no cambia) y no lanza excepción.
        assert dlg._current_note_id == "CAT-001"
        assert "no existe" in dlg.status_label.text().lower()
