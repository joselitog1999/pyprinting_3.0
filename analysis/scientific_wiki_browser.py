# -*- coding: utf-8 -*-
"""
analysis/scientific_wiki_browser.py
====================================
Navegador de Documentación Científica (PyPrinting 3.0 — Nanofotónica UNSAM/CONICET).

Diálogo FLOTANTE y NO MODAL que permite a los usuarios de laboratorio leer, sin
abandonar la aplicación principal, los compendios científicos en Markdown del
proyecto:
    - reportes/cientificos/CAT-xxx_*.md  (Compendios Científicos)
    - reportes/sistema/SYS-xxx_*.md      (Reportes de Sistema)
    - docs/modulos/MOD-xxx_*.md          (Manuales de Módulo)

Soporta enlaces cruzados estilo Obsidian (``[[CAT-105]]``, ``[[CAT-105|Alias]]``,
``[[CAT-105#Seccion]]``, ``[[CAT-105#Seccion|Alias]]``) y navegación directa a
anclas de sección (``#seccion``) generadas automáticamente por la extensión
``toc`` de la librería ``markdown``.

Sigue las convenciones de construcción/estilo de
``analysis/figure_export_studio.py::FigureExportStudioDialog`` (docstrings,
paleta Catppuccin Mocha, estructura de ``QDialog``) con una diferencia
arquitectónica deliberada: mientras ``FigureExportStudioDialog`` se lanza de
forma MODAL vía ``.exec()``, este diálogo se lanza con ``.show()`` (no modal),
ya que está pensado para permanecer abierto junto a la ventana principal
mientras el usuario de laboratorio sigue trabajando (patrón singleton
gestionado por el llamador, ver ``navigate_to()``).
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import markdown

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QSplitter, QTreeWidget,
    QTreeWidgetItem, QLineEdit, QTextBrowser, QPushButton, QLabel, QWidget
)
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices


# ==============================================================================
# CONSTANTES DE UBICACIÓN Y CATEGORIZACIÓN DE NOTAS
# ==============================================================================
BASE_DIR = Path(__file__).resolve().parent.parent

CATEGORY_DIRS: Dict[str, str] = {
    'CAT': 'reportes/cientificos',
    'SYS': 'reportes/sistema',
    'MOD': 'docs/modulos',
}

CATEGORY_LABELS: Dict[str, str] = {
    'CAT': 'Compendios Científicos',
    'SYS': 'Reportes de Sistema',
    'MOD': 'Manuales de Módulo',
}

# Prefijo-Numero al inicio del nombre de archivo, ej. "CAT-105_Algo.md" -> "CAT-105"
_NOTE_ID_RE = re.compile(r'^([A-Z]{2,4}-\d+)_')

# Enlaces estilo Obsidian: [[CAT-105]], [[CAT-105|Alias]], [[CAT-105#Seccion]],
# [[CAT-105#Seccion|Alias]]. El grupo 2 conserva el '#' inicial cuando existe.
WIKILINK_RE = re.compile(r'\[\[([A-Z]{2,4}-\d+)(#[^\]|]+)?(?:\|([^\]]+))?\]\]')


def _sort_key(note_id: str) -> int:
    """Extrae la parte numérica de un note_id (ej. 'CAT-001' -> 1) para poder
    ordenar numéricamente en vez de lexicográficamente (CAT-9 antes que CAT-10)."""
    m = re.search(r'-(\d+)$', note_id)
    return int(m.group(1)) if m else 0


def _extract_title(path: Path, default: str) -> str:
    """Extrae la primera línea '# Encabezado' de un archivo Markdown como título."""
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            for line in fh:
                line = line.strip()
                if line.startswith('# '):
                    return line[2:].strip()
    except Exception:
        pass
    return default


def discover_notes(base_dir: Optional[Path] = None) -> Tuple[Dict[str, Path], Dict[str, str], Dict[str, str]]:
    """
    Escanea reportes/cientificos, reportes/sistema y docs/modulos en busca de
    notas CAT-xxx / SYS-xxx / MOD-xxx.

    Retorna una tupla (índice, títulos, categorías):
        índice:     note_id -> Path absoluto del archivo .md
        títulos:    note_id -> título (primera línea '# ...' del archivo)
        categorías: note_id -> prefijo de categoría ('CAT' / 'SYS' / 'MOD')
    """
    root = base_dir if base_dir is not None else BASE_DIR
    index: Dict[str, Path] = {}
    titles: Dict[str, str] = {}
    categories: Dict[str, str] = {}

    for prefix, rel_dir in CATEGORY_DIRS.items():
        dir_path = root / rel_dir
        if not dir_path.is_dir():
            continue
        for f in sorted(dir_path.glob(f'{prefix}-*.md')):
            m = _NOTE_ID_RE.match(f.name)
            if not m:
                continue
            note_id = m.group(1)
            index[note_id] = f
            categories[note_id] = prefix
            titles[note_id] = _extract_title(f, default=note_id)

    return index, titles, categories


def _wikilink_repl(match: 're.Match') -> str:
    note_id = match.group(1)
    anchor = match.group(2)   # ej. "#Seccion" o None (ya incluye el '#')
    alias = match.group(3)

    target = f"wiki://{note_id}{anchor or ''}"
    if alias:
        display = alias
    elif anchor:
        display = f"{note_id}{anchor}"
    else:
        display = note_id
    return f"[{display}]({target})"


def preprocess_wikilinks(text: str) -> str:
    """
    Pre-procesa enlaces estilo Obsidian ``[[CAT-105]]`` (y variantes con alias
    ``|`` y/o ancla ``#seccion``) en enlaces Markdown reales resolubles por la
    librería ``markdown`` estándar, ANTES de invocar ``markdown.markdown()``.

    La sintaxis ``[[...]]`` no es Markdown estándar y la librería ``markdown``
    la deja intacta como texto plano; este preprocesamiento es el único punto
    donde se traduce a un esquema de URL propio ``wiki://<NOTE_ID>[#ancla]``
    que luego se resuelve en ``ScientificWikiBrowserDialog._on_anchor_clicked``.

    Ejemplos:
        [[CAT-105]]                      -> [CAT-105](wiki://CAT-105)
        [[CAT-105|Deriva Térmica]]       -> [Deriva Térmica](wiki://CAT-105)
        [[CAT-105#Metodologia]]          -> [CAT-105#Metodologia](wiki://CAT-105#Metodologia)
        [[CAT-105#Metodologia|Ver más]]  -> [Ver más](wiki://CAT-105#Metodologia)
    """
    return WIKILINK_RE.sub(_wikilink_repl, text)


# ==============================================================================
# PLANTILLA HTML — PALETA CATPPUCCIN MOCHA (subset CSS soportado por QTextBrowser)
# ==============================================================================
_WRAP_TEMPLATE = """<html>
<head>
<style>
body {{
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-family: 'Segoe UI', sans-serif;
    font-size: 13px;
    line-height: 1.55;
}}
h1, h2 {{ color: #cba6f7; }}
h3, h4, h5, h6 {{ color: #89b4fa; }}
a {{ color: #74c7ec; text-decoration: none; }}
code {{
    background-color: #313244;
    color: #f9e2af;
    padding: 1px 4px;
    border-radius: 3px;
}}
pre {{
    background-color: #313244;
    color: #cdd6f4;
    padding: 8px;
    border-radius: 4px;
}}
table {{
    border-collapse: collapse;
}}
th, td {{
    border: 1px solid #45475a;
    padding: 4px 10px;
}}
th {{
    background-color: #313244;
    color: #cba6f7;
}}
blockquote {{
    border-left: 3px solid #cba6f7;
    color: #bac2de;
    padding-left: 10px;
    margin-left: 0;
}}
hr {{
    border: none;
    border-top: 1px solid #45475a;
}}
</style>
</head>
<body>
{body}
</body>
</html>
"""


class ScientificWikiBrowserDialog(QDialog):
    """
    Navegador flotante NO MODAL de la Wiki Científica de PyPrinting 3.0.

    A diferencia de ``FigureExportStudioDialog`` (modal, ``.exec()``), este
    diálogo se invoca con ``.show()`` para permanecer abierto en paralelo a la
    ventana principal mientras el investigador consulta la fundamentación
    física/metrológica de la herramienta que está utilizando.

    Patrón de uso recomendado (singleton gestionado por el llamador, ej. desde
    múltiples botones "[📖 Ayuda]" repartidos en ``lattice_disorder_gui.py``)::

        if self._wiki_dialog is None:
            self._wiki_dialog = ScientificWikiBrowserDialog(parent=self)
        self._wiki_dialog.navigate_to("CAT-206")
        self._wiki_dialog.show()
        self._wiki_dialog.raise_()
        self._wiki_dialog.activateWindow()
    """

    #: Nota de aterrizaje por defecto si no se especifica initial_note_id.
    DEFAULT_LANDING_NOTE = "CAT-001"

    def __init__(
        self,
        parent=None,
        initial_note_id: Optional[str] = None,
        initial_anchor: Optional[str] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("📖 Wiki Científica — PyPrinting 3.0")
        self.resize(1150, 760)
        self.setMinimumSize(820, 520)
        # Ventana flotante independiente (no modal): coexiste con la app principal.
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.Window)

        self._note_index: Dict[str, Path] = {}
        self._note_titles: Dict[str, str] = {}
        self._note_categories: Dict[str, str] = {}
        self._category_items: Dict[str, QTreeWidgetItem] = {}

        self._history: List[str] = []
        self._history_pos: int = -1
        self._current_note_id: Optional[str] = None

        self._init_ui()
        self._refresh_index()

        start_id = initial_note_id
        if not start_id and self.DEFAULT_LANDING_NOTE in self._note_index:
            start_id = self.DEFAULT_LANDING_NOTE

        if start_id:
            self.navigate_to(start_id, initial_anchor)
        else:
            self._show_landing_page()

    # ------------------------------------------------------------------
    # Construcción de interfaz
    # ------------------------------------------------------------------
    def _init_ui(self) -> None:
        self.setStyleSheet(
            "QDialog { background-color: #181825; }"
            "QTreeWidget { background-color: #1e1e2e; color: #cdd6f4; "
            "border: 1px solid #313244; }"
            "QTreeWidget::item { padding: 3px; }"
            "QTreeWidget::item:selected { background-color: #45475a; }"
            "QLineEdit { background-color: #313244; color: #cdd6f4; "
            "border: 1px solid #45475a; border-radius: 4px; padding: 4px; }"
            "QPushButton { background-color: #313244; color: #cdd6f4; "
            "border: 1px solid #45475a; border-radius: 4px; padding: 5px 10px; }"
            "QPushButton:disabled { color: #6c7086; }"
            "QPushButton:hover:!disabled { background-color: #45475a; }"
            "QLabel { color: #bac2de; }"
            "QTextBrowser { background-color: #1e1e2e; border: 1px solid #313244; }"
        )

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)

        # ── Panel Izquierdo: Búsqueda + Árbol de Categorías ───────────────
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(2, 2, 2, 2)
        left_layout.setSpacing(6)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("🔎 Buscar por ID o título...")
        self.search_edit.textChanged.connect(self._on_search_changed)
        left_layout.addWidget(self.search_edit)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.currentItemChanged.connect(self._on_tree_current_item_changed)
        left_layout.addWidget(self.tree, stretch=1)

        self.btn_refresh = QPushButton("🔄 Refrescar")
        self.btn_refresh.setToolTip(
            "Reescanea reportes/cientificos, reportes/sistema y docs/modulos "
            "en busca de notas nuevas o modificadas."
        )
        self.btn_refresh.clicked.connect(self._on_refresh_clicked)
        left_layout.addWidget(self.btn_refresh)

        left_widget.setMinimumWidth(280)
        splitter.addWidget(left_widget)

        # ── Panel Derecho: Barra de Navegación + Contenido Renderizado ────
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(2, 2, 2, 2)
        right_layout.setSpacing(6)

        toolbar = QHBoxLayout()
        self.btn_back = QPushButton("⬅ Atrás")
        self.btn_back.setEnabled(False)
        self.btn_back.clicked.connect(self._go_back)
        toolbar.addWidget(self.btn_back)

        self.btn_forward = QPushButton("➡ Adelante")
        self.btn_forward.setEnabled(False)
        self.btn_forward.clicked.connect(self._go_forward)
        toolbar.addWidget(self.btn_forward)

        toolbar.addStretch()

        self.status_label = QLabel("")
        toolbar.addWidget(self.status_label)

        right_layout.addLayout(toolbar)

        self.text_browser = QTextBrowser()
        self.text_browser.setReadOnly(True)
        self.text_browser.setOpenLinks(False)
        self.text_browser.setOpenExternalLinks(False)
        self.text_browser.anchorClicked.connect(self._on_anchor_clicked)
        right_layout.addWidget(self.text_browser, stretch=1)

        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)

    # ------------------------------------------------------------------
    # Índice de notas y árbol de categorías
    # ------------------------------------------------------------------
    def _refresh_index(self) -> None:
        self._note_index, self._note_titles, self._note_categories = discover_notes()
        self._populate_tree()

    def _on_refresh_clicked(self) -> None:
        current = self._current_note_id
        self._refresh_index()
        if current and current in self._note_index:
            self._display_note(current, push_history=False)
        self._show_status("Índice de la Wiki Científica actualizado.")

    def _populate_tree(self) -> None:
        # Defensa de señales: evita disparar _on_tree_current_item_changed
        # (y por lo tanto navigate_to) mientras reconstruimos el árbol.
        self.tree.blockSignals(True)
        try:
            self.tree.clear()
            self._category_items = {}
            for prefix in ('CAT', 'SYS', 'MOD'):
                label = CATEGORY_LABELS.get(prefix, prefix)
                top = QTreeWidgetItem([label])
                top.setFlags(top.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                font = top.font(0)
                font.setBold(True)
                top.setFont(0, font)
                self.tree.addTopLevelItem(top)
                self._category_items[prefix] = top

                ids_in_cat = sorted(
                    (nid for nid, p in self._note_categories.items() if p == prefix),
                    key=_sort_key,
                )
                for note_id in ids_in_cat:
                    title = self._note_titles.get(note_id, note_id)
                    child = QTreeWidgetItem([f"{note_id} — {title}"])
                    child.setData(0, Qt.ItemDataRole.UserRole, note_id)
                    top.addChild(child)
            self.tree.expandAll()
        finally:
            self.tree.blockSignals(False)

    def _on_search_changed(self, text: str) -> None:
        query = text.strip().lower()
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            any_visible = False
            for j in range(top.childCount()):
                child = top.child(j)
                note_id = child.data(0, Qt.ItemDataRole.UserRole) or ""
                title = self._note_titles.get(note_id, "")
                match = (not query) or (query in note_id.lower()) or (query in title.lower())
                child.setHidden(not match)
                any_visible = any_visible or match
            top.setHidden(bool(query) and not any_visible)

    def _sync_tree_selection(self, note_id: str) -> None:
        self.tree.blockSignals(True)
        try:
            for i in range(self.tree.topLevelItemCount()):
                top = self.tree.topLevelItem(i)
                for j in range(top.childCount()):
                    child = top.child(j)
                    if child.data(0, Qt.ItemDataRole.UserRole) == note_id:
                        self.tree.setCurrentItem(child)
                        return
        finally:
            self.tree.blockSignals(False)

    def _on_tree_current_item_changed(self, current: Optional[QTreeWidgetItem], previous) -> None:
        if current is None:
            return
        note_id = current.data(0, Qt.ItemDataRole.UserRole)
        if note_id:
            self.navigate_to(note_id)

    # ------------------------------------------------------------------
    # Renderizado Markdown -> HTML
    # ------------------------------------------------------------------
    def _render_markdown(self, raw_text: str) -> str:
        processed = preprocess_wikilinks(raw_text)
        body_html = markdown.markdown(processed, extensions=['tables', 'fenced_code', 'toc'])
        return _WRAP_TEMPLATE.format(body=body_html)

    def _render_error(self, note_id: str, detail: str = "") -> str:
        detail_html = f"<p style='color:#f38ba8;'>{detail}</p>" if detail else ""
        body = (
            f"<h2 style='color:#f38ba8;'>⚠️ Nota no disponible: {note_id}</h2>"
            f"<p style='color:#cdd6f4;'>No se pudo cargar el archivo Markdown correspondiente a "
            f"<b>{note_id}</b>. Verifique que el archivo exista en "
            f"<code>reportes/cientificos/</code>, <code>reportes/sistema/</code> o "
            f"<code>docs/modulos/</code>, y que su nombre comience con el ID correcto "
            f"(ej. <code>{note_id}_Titulo_Descriptivo.md</code>).</p>{detail_html}"
        )
        return _WRAP_TEMPLATE.format(body=body)

    def _show_landing_page(self) -> None:
        body = (
            "<h1 style='color:#cba6f7;'>📖 Wiki Científica de PyPrinting 3.0</h1>"
            "<p style='color:#cdd6f4;'>Seleccione una nota del árbol de la izquierda, o utilice el "
            "buscador, para navegar por los Compendios Científicos (<b>CAT</b>), los Reportes de "
            "Sistema (<b>SYS</b>) y los Manuales de Módulo (<b>MOD</b>) de PyPrinting 3.0.</p>"
        )
        self.text_browser.setHtml(_WRAP_TEMPLATE.format(body=body))
        self.setWindowTitle("📖 Wiki Científica — PyPrinting 3.0")
        self._show_status("Seleccione una nota para comenzar.")

    def _show_status(self, message: str) -> None:
        self.status_label.setText(message)

    # ------------------------------------------------------------------
    # Navegación pública y gestión de historial
    # ------------------------------------------------------------------
    def navigate_to(self, note_id: str, anchor: Optional[str] = None) -> None:
        """
        Punto de entrada público único: muestra ``note_id`` (con ancla
        opcional) en el visor y empuja una nueva entrada de historial.

        Si el diálogo ya está visible cuando el llamador invoca este método
        (patrón singleton, ej. desde múltiples botones "[📖 Ayuda]"), el
        llamador es responsable de además hacer ``.show()``, ``.raise_()`` y
        ``.activateWindow()`` — este método únicamente cambia el contenido
        mostrado y la historia de navegación interna.
        """
        if not note_id:
            return
        self._display_note(note_id, anchor=anchor, push_history=True)

    def _display_note(self, note_id: str, anchor: Optional[str] = None, push_history: bool = True) -> None:
        note_id = note_id.upper()
        path = self._note_index.get(note_id)

        if path is None or not path.is_file():
            html = self._render_error(note_id)
            self.text_browser.setHtml(html)
            self.setWindowTitle(f"📖 Wiki Científica — Nota no encontrada ({note_id})")
            self._show_status(f"No se encontró la nota '{note_id}' en el índice.")
        else:
            try:
                raw_text = path.read_text(encoding='utf-8')
            except Exception as exc:
                html = self._render_error(note_id, detail=str(exc))
                self.text_browser.setHtml(html)
                self.setWindowTitle(f"📖 Wiki Científica — Error de Lectura ({note_id})")
                self._show_status(f"Error al leer '{note_id}': {exc}")
                raw_text = None
            else:
                html = self._render_markdown(raw_text)
                self.text_browser.setHtml(html)
                title = self._note_titles.get(note_id, note_id)
                self.setWindowTitle(f"📖 Wiki Científica — {note_id}: {title}")
                self._show_status(f"Mostrando {note_id}.")
                if anchor:
                    self.text_browser.scrollToAnchor(anchor)

        self._current_note_id = note_id

        if push_history:
            self._push_history(note_id)

        self._sync_tree_selection(note_id)
        self._update_nav_buttons()

    def _push_history(self, note_id: str) -> None:
        if (
            self._history
            and 0 <= self._history_pos < len(self._history)
            and self._history[self._history_pos] == note_id
        ):
            return  # Evita entradas consecutivas duplicadas.
        # Navegar a una nota nueva tras haber retrocedido descarta el "futuro"
        # previo (comportamiento estándar de historial de navegador).
        self._history = self._history[: self._history_pos + 1]
        self._history.append(note_id)
        self._history_pos = len(self._history) - 1

    def _go_back(self) -> None:
        if self._history_pos > 0:
            self._history_pos -= 1
            self._display_note(self._history[self._history_pos], push_history=False)

    def _go_forward(self) -> None:
        if self._history_pos < len(self._history) - 1:
            self._history_pos += 1
            self._display_note(self._history[self._history_pos], push_history=False)

    def _update_nav_buttons(self) -> None:
        self.btn_back.setEnabled(self._history_pos > 0)
        self.btn_forward.setEnabled(self._history_pos < len(self._history) - 1)

    # ------------------------------------------------------------------
    # Resolución de enlaces (wikilinks, anclas locales, http/https externos)
    # ------------------------------------------------------------------
    @staticmethod
    def resolve_wiki_url(url: QUrl) -> Tuple[Optional[str], Optional[str]]:
        """
        Resuelve una QUrl de esquema ``wiki://`` a ``(note_id, anchor)``.

        Comportamiento empírico verificado en este entorno PyQt6: para una URL
        con autoridad tipo ``wiki://CAT-105``, Qt coloca el identificador en
        ``QUrl.host()`` (normalizado a minúsculas por las reglas de autoridad
        de URL — de ahí el ``.upper()``), NO en ``QUrl.path()`` (que queda
        vacío). ``QUrl.fragment()`` extrae correctamente el ``#seccion`` en
        ``wiki://CAT-105#seccion`` de forma independiente del host. Se
        conserva un fallback a ``path()`` (despojado de '/') por robustez
        ante variaciones de formato de URL (ej. ``wiki:CAT-105`` sin '//').
        """
        if url.scheme() != 'wiki':
            return None, None
        raw_id = url.host()
        if not raw_id:
            raw_id = url.path().lstrip('/')
        note_id = raw_id.upper() if raw_id else None
        anchor = url.fragment() or None
        return note_id, anchor

    def _on_anchor_clicked(self, url: QUrl) -> None:
        note_id, anchor = self.resolve_wiki_url(url)
        if note_id is not None:
            if note_id in self._note_index:
                self.navigate_to(note_id, anchor)
            else:
                self._show_status(f"Enlace roto: la nota '{note_id}' no existe en el índice.")
            return

        scheme = url.scheme()
        if scheme in ('http', 'https'):
            QDesktopServices.openUrl(url)
            return

        if not scheme and url.hasFragment():
            # Ancla local dentro del mismo documento (ej. generada por la
            # extensión 'toc' sobre los encabezados del propio archivo).
            self.text_browser.scrollToAnchor(url.fragment())
            return

        self._show_status(f"Enlace no soportado: {url.toString()}")
