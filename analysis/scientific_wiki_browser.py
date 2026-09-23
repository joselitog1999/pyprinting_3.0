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
``[[CAT-105#Seccion]]``, ``[[CAT-105#Seccion|Alias]]``), bloques de advertencia
nativos de Obsidian/GitHub (``> [!NOTE]``, ``> [!TIP]``, ``> [!IMPORTANT]``,
``> [!WARNING]``, ``> [!CAUTION]``), renderizado matemático vectorial completo
(matrices, tensores, multilínea) vía MathJax 3 SVG offline sobre motor
Chromium moderno (``QWebEngineView``), navegación directa a anclas de sección
(``#seccion``) y botón de integración directa para abrir la nota en la aplicación
Obsidian nativa.

Incluye arquitectura de fallback transparente a ``QTextBrowser`` en entornos
donde QtWebEngine no esté disponible.
"""

import base64
import functools
import io
import re
import urllib.parse
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import markdown
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QSplitter, QTreeWidget,
    QTreeWidgetItem, QLineEdit, QTextBrowser, QPushButton, QLabel, QWidget
)
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices

# ──────────────────────────────────────────────────────────────────────────────
# DETECCIÓN DE MOTOR WEBENGINE (Chromium Embebido)
# ──────────────────────────────────────────────────────────────────────────────
HAS_WEBENGINE: bool = False
try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWebEngineCore import QWebEnginePage
    HAS_WEBENGINE = True
except (ImportError, Exception):
    HAS_WEBENGINE = False


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

# Recursos de renderizado matemático offline
MATHJAX_PATH = BASE_DIR / 'resources' / 'vendor' / 'tex-svg.js'
KATEX_DIR = BASE_DIR / 'resources' / 'vendor' / 'katex'

# Prefijo-Numero al inicio del nombre de archivo, ej. "CAT-105_Algo.md" -> "CAT-105"
_NOTE_ID_RE = re.compile(r'^([A-Z]{2,4}-\d+)_')

# Enlaces estilo Obsidian: [[CAT-105]], [[CAT-105|Alias]], [[CAT-105#Seccion]], etc.
WIKILINK_RE = re.compile(r'\[\[([A-Z]{2,4}-\d+[^\]|#]*)(#[^\]|]+)?(?:\|([^\]]+))?\]\]')

# Bloques y expresiones matemáticas estándar
_BLOCK_MATH_RE = re.compile(r'\$\$(.+?)\$\$', re.DOTALL)
_INLINE_MATH_RE = re.compile(r'(?<!\$)\$(?!\s)([^\$\n]+?)(?<!\s)\$(?!\$)')


def _sort_key(note_id: str) -> int:
    """Extrae la parte numérica de un note_id para ordenar numéricamente."""
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
    raw_id = match.group(1)   # "CAT-105" o "CAT-105_Titulo_Descriptivo.md"
    anchor = match.group(2)   # ej. "#Seccion" o None (ya incluye el '#')
    alias = match.group(3)

    id_match = re.match(r'^([A-Z]{2,4}-\d+)', raw_id)
    note_id = id_match.group(1) if id_match else raw_id

    target = f"wiki://{note_id}{anchor or ''}"
    if alias:
        display = alias
    elif anchor:
        display = f"{note_id}{anchor}"
    else:
        suffix = raw_id[len(note_id):]
        if suffix:
            title_part = suffix[1:] if suffix.startswith('_') else suffix
            if title_part.lower().endswith('.md'):
                title_part = title_part[:-3]
            title_part = title_part.replace('_', ' ').strip()
            display = title_part if title_part else note_id
        else:
            display = note_id
    return f"[{display}]({target})"


def preprocess_wikilinks(text: str) -> str:
    """Pre-procesa enlaces estilo Obsidian [[CAT-105]] en enlaces Markdown reales."""
    return WIKILINK_RE.sub(_wikilink_repl, text)


# ==============================================================================
# CALLOUTS DE OBSIDIAN Y GITHUB (> [!NOTE], > [!TIP], etc.)
# ==============================================================================
CALLOUT_CONFIG = {
    'NOTE': {
        'icon': 'ℹ️',
        'title': 'Nota',
        'border': '#89b4fa',  # Blue
        'bg': 'rgba(137, 180, 250, 0.08)',
        'title_color': '#89b4fa'
    },
    'TIP': {
        'icon': '💡',
        'title': 'Consejo / Sugerencia',
        'border': '#a6e3a1',  # Green
        'bg': 'rgba(166, 227, 161, 0.08)',
        'title_color': '#a6e3a1'
    },
    'IMPORTANT': {
        'icon': '❗',
        'title': 'Importante',
        'border': '#cba6f7',  # Mauve
        'bg': 'rgba(203, 166, 247, 0.08)',
        'title_color': '#cba6f7'
    },
    'WARNING': {
        'icon': '⚠️',
        'title': 'Advertencia',
        'border': '#fab387',  # Peach
        'bg': 'rgba(250, 179, 135, 0.08)',
        'title_color': '#fab387'
    },
    'CAUTION': {
        'icon': '🛑',
        'title': 'Precaución',
        'border': '#f38ba8',  # Red
        'bg': 'rgba(243, 139, 168, 0.08)',
        'title_color': '#f38ba8'
    },
}


def preprocess_obsidian_callouts(text: str) -> str:
    """
    Transforma bloques de advertencia estilo Obsidian/GitHub:
        > [!NOTE] Título Opcional
        > Contenido del callout...
    en contenedores HTML estructurados con clases de Catppuccin Mocha y markdown='1'.
    """
    lines = text.split('\n')
    out_lines: List[str] = []
    in_callout = False
    callout_type = ""
    callout_custom_title = ""
    callout_lines: List[str] = []

    header_re = re.compile(r'^>\s*\[!([A-Z]+)\](?:[+-])?\s*(.*)$')

    def _flush_callout():
        nonlocal in_callout, callout_type, callout_custom_title, callout_lines
        if not in_callout:
            return
        cfg = CALLOUT_CONFIG.get(callout_type.upper(), CALLOUT_CONFIG['NOTE'])
        title = callout_custom_title.strip() if callout_custom_title.strip() else cfg['title']
        icon = cfg['icon']
        body_text = '\n'.join(callout_lines).strip()

        html_block = (
            f'\n<div class="callout callout-{callout_type.lower()}" markdown="1">\n'
            f'<div class="callout-title">{icon} {title}</div>\n'
            f'<div class="callout-body" markdown="1">\n\n'
            f'{body_text}\n\n'
            f'</div>\n'
            f'</div>\n'
        )
        out_lines.append(html_block)
        in_callout = False
        callout_lines = []
        callout_type = ""
        callout_custom_title = ""

    for line in lines:
        if not in_callout:
            m = header_re.match(line)
            if m:
                in_callout = True
                callout_type = m.group(1).upper()
                callout_custom_title = m.group(2)
                callout_lines = []
            else:
                out_lines.append(line)
        else:
            if line.startswith('>'):
                content = line[1:].lstrip(' ') if len(line) > 1 and line[1] == ' ' else line[1:]
                callout_lines.append(content)
            elif line.strip() == '':
                callout_lines.append('')
            else:
                _flush_callout()
                out_lines.append(line)

    if in_callout:
        _flush_callout()

    return '\n'.join(out_lines)


# ==============================================================================
# RENDERIZADO OFFLINE DE LATEX (MATHTEXT DE FALLBACK PARA QTEXTBROWSER)
# ==============================================================================
@functools.lru_cache(maxsize=1024)
def _render_latex_data_uri(latex: str, fontsize: int = 14, color: str = '#cdd6f4', dpi: int = 150) -> str:
    """Renderiza una expresión mathtext a una imagen PNG en memoria (fallback para QTextBrowser)."""
    fig = Figure(figsize=(0.01, 0.01))
    canvas = FigureCanvasAgg(fig)
    fig.text(0, 0, f"${latex}$", fontsize=fontsize, color=color)
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=dpi, transparent=True,
                bbox_inches='tight', pad_inches=0.03)
    buf.seek(0)
    encoded = base64.b64encode(buf.read()).decode('ascii')
    return f"data:image/png;base64,{encoded}"


def _render_math_img_tag(latex: str) -> str:
    """Envuelve _render_latex_data_uri con manejo defensivo ante mathtext inválido."""
    try:
        uri = _render_latex_data_uri(latex)
        return f'<img src="{uri}" style="vertical-align: middle;"/>'
    except Exception as exc:
        escaped = latex.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        return (f'<code style="color:#f38ba8;" title="Error de renderizado LaTeX: {exc}">'
                f'{escaped}</code>')


def preprocess_latex_math(text: str) -> str:
    """Pre-procesa expresiones LaTeX en imágenes PNG embebidas para QTextBrowser."""
    def _block_repl(m: 're.Match') -> str:
        img_tag = _render_math_img_tag(m.group(1).strip())
        return f'<div align="center" style="margin: 8px 0;">{img_tag}</div>'

    def _inline_repl(m: 're.Match') -> str:
        return _render_math_img_tag(m.group(1).strip())

    text = _BLOCK_MATH_RE.sub(_block_repl, text)
    text = _INLINE_MATH_RE.sub(_inline_repl, text)
    return text


# ==============================================================================
# PLANTILLAS HTML: MODERNA WEBENGINE (MATHJAX 3 SVG) vs CLÁSICA QTEXTBROWSER
# ==============================================================================
_WEBENGINE_HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
* {{
    box-sizing: border-box;
}}
body {{
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, 'Inter', Roboto, sans-serif;
    font-size: 13.5px;
    line-height: 1.68;
    margin: 0;
    padding: 24px 32px;
}}
h1, h2 {{
    color: #cba6f7;
    font-weight: 700;
    border-bottom: 1px solid #313244;
    padding-bottom: 8px;
    margin-top: 26px;
    margin-bottom: 14px;
}}
h1 {{ font-size: 22px; }}
h2 {{ font-size: 18px; }}
h3 {{
    color: #89b4fa;
    font-size: 15px;
    font-weight: 600;
    margin-top: 20px;
    margin-bottom: 10px;
}}
h4, h5, h6 {{
    color: #89dceb;
    font-size: 13.5px;
    font-weight: 600;
}}
a {{
    color: #89b4fa;
    text-decoration: none;
    border-bottom: 1px dotted rgba(137, 180, 250, 0.6);
    transition: color 0.15s ease, border-color 0.15s ease;
}}
a:hover {{
    color: #b4befe;
    border-bottom: 1px solid #b4befe;
}}
code {{
    background-color: #313244;
    color: #f9e2af;
    padding: 2px 6px;
    border-radius: 4px;
    font-family: 'Cascadia Code', 'JetBrains Mono', Consolas, monospace;
    font-size: 12px;
}}
pre {{
    background-color: #181825;
    border: 1px solid #313244;
    color: #cdd6f4;
    padding: 12px 16px;
    border-radius: 6px;
    overflow-x: auto;
    line-height: 1.5;
}}
pre code {{
    background: transparent;
    padding: 0;
    color: inherit;
    border-radius: 0;
}}
table {{
    width: 100%;
    border-collapse: collapse;
    margin: 18px 0;
    font-size: 13px;
}}
th, td {{
    border: 1px solid #45475a;
    padding: 7px 12px;
    text-align: left;
}}
th {{
    background-color: #313244;
    color: #cba6f7;
    font-weight: 600;
}}
tr:nth-child(even) {{
    background-color: rgba(205, 214, 244, 0.02);
}}
tr:hover {{
    background-color: rgba(205, 214, 244, 0.05);
}}
blockquote {{
    border-left: 3px solid #6c7086;
    color: #a6adc8;
    padding-left: 14px;
    margin: 14px 0;
}}
hr {{
    border: none;
    border-top: 1px solid #45475a;
    margin: 22px 0;
}}
/* Callouts estilizados */
.callout {{
    border-radius: 6px;
    padding: 12px 16px;
    margin: 16px 0;
    border-left: 4px solid #89b4fa;
}}
.callout-note {{ border-color: #89b4fa; background-color: rgba(137, 180, 250, 0.08); }}
.callout-tip {{ border-color: #a6e3a1; background-color: rgba(166, 227, 161, 0.08); }}
.callout-important {{ border-color: #cba6f7; background-color: rgba(203, 166, 247, 0.08); }}
.callout-warning {{ border-color: #fab387; background-color: rgba(250, 179, 135, 0.08); }}
.callout-caution {{ border-color: #f38ba8; background-color: rgba(243, 139, 168, 0.08); }}

.callout-title {{
    font-weight: 700;
    font-size: 13px;
    margin-bottom: 6px;
}}
.callout-note .callout-title {{ color: #89b4fa; }}
.callout-tip .callout-title {{ color: #a6e3a1; }}
.callout-important .callout-title {{ color: #cba6f7; }}
.callout-warning .callout-title {{ color: #fab387; }}
.callout-caution .callout-title {{ color: #f38ba8; }}

.callout-body > p:first-child {{ margin-top: 0; }}
.callout-body > p:last-child {{ margin-bottom: 0; }}

/* MathJax SVG Integrado */
mjx-container[jax="SVG"][display="true"] {{
    margin: 14px 0 !important;
    overflow-x: auto;
    overflow-y: hidden;
    text-align: center;
}}
svg {{
    color: #cdd6f4 !important;
}}
mjx-container {{
    color: #cdd6f4 !important;
}}
/* Scrollbar Catppuccin */
::-webkit-scrollbar {{
    width: 8px;
    height: 8px;
}}
::-webkit-scrollbar-track {{
    background: #181825;
}}
::-webkit-scrollbar-thumb {{
    background: #45475a;
    border-radius: 4px;
}}
::-webkit-scrollbar-thumb:hover {{
    background: #585b70;
}}
</style>
<script>
window.MathJax = {{
  tex: {{
    inlineMath: [['$', '$'], ['\\\\(', '\\\\)']],
    displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']],
    processEscapes: true,
    processEnvironments: true
  }},
  options: {{
    skipHtmlTags: ['script', 'noscript', 'style', 'textarea', 'pre', 'code']
  }},
  svg: {{
    fontCache: 'global'
  }}
}};
</script>
<script id="MathJax-script" async src="{mathjax_url}"></script>
</head>
<body>
{body}
</body>
</html>
"""

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
.callout {{
    border-left: 3px solid #89b4fa;
    background-color: #181825;
    padding: 8px 12px;
    margin: 8px 0;
}}
.callout-title {{
    font-weight: bold;
    color: #89b4fa;
    margin-bottom: 4px;
}}
</style>
</head>
<body>
{body}
</body>
</html>
"""


# ──────────────────────────────────────────────────────────────────────────────
# PÁGINA WEBENGINE PERSONALIZADA PARA INTERCEPTAR ENLACES
# ──────────────────────────────────────────────────────────────────────────────
if HAS_WEBENGINE:
    class WikiWebEnginePage(QWebEnginePage):
        """Página especializada de Chromium que intercepta esquemas wiki:// y obsidian://."""

        def __init__(self, parent_dialog):
            super().__init__(parent_dialog)
            self.dialog = parent_dialog

        def acceptNavigationRequest(self, url: QUrl, nav_type, is_main_frame: bool) -> bool:
            if nav_type == QWebEnginePage.NavigationType.NavigationTypeLinkClicked:
                scheme = url.scheme().lower()
                if scheme == 'wiki':
                    self.dialog._on_anchor_clicked(url)
                    return False
                elif scheme in ('http', 'https', 'obsidian'):
                    QDesktopServices.openUrl(url)
                    return False
                elif not scheme and url.hasFragment():
                    # Ancla local (#seccion)
                    return True
            return super().acceptNavigationRequest(url, nav_type, is_main_frame)


# ==============================================================================
# DIÁLOGO PRINCIPAL DEL NAVEGADOR
# ==============================================================================
class ScientificWikiBrowserDialog(QDialog):
    """
    Navegador flotante NO MODAL de la Wiki Científica de PyPrinting 3.0.
    Permite consultar la fundamentación física/metrológica con renderizado
    matemático vectorial y navegación de compendios interactiva.
    """

    DEFAULT_LANDING_NOTE = "CAT-001"

    def __init__(
        self,
        parent=None,
        initial_note_id: Optional[str] = None,
        initial_anchor: Optional[str] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("📖 Wiki Científica — PyPrinting 3.0")
        self.resize(1180, 780)
        self.setMinimumSize(850, 540)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.Window)

        self._note_index: Dict[str, Path] = {}
        self._note_titles: Dict[str, str] = {}
        self._note_categories: Dict[str, str] = {}
        self._category_items: Dict[str, QTreeWidgetItem] = {}

        self._history: List[str] = []
        self._history_pos: int = -1
        self._current_note_id: Optional[str] = None
        self._current_note_path: Optional[Path] = None

        self.web_view: Optional['QWebEngineView'] = None
        self.text_browser: Optional[QTextBrowser] = None

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

        # Botón para abrir la nota actual directamente en Obsidian
        self.btn_open_obsidian = QPushButton("🟣 Abrir en Obsidian ↗")
        self.btn_open_obsidian.setEnabled(False)
        self.btn_open_obsidian.setToolTip(
            "Abre esta nota directamente en la aplicación de escritorio Obsidian con "
            "acceso al grafo de conocimiento y edición en vivo."
        )
        self.btn_open_obsidian.clicked.connect(self._on_open_obsidian_clicked)
        toolbar.addWidget(self.btn_open_obsidian)

        toolbar.addStretch()

        self.status_label = QLabel("")
        toolbar.addWidget(self.status_label)

        right_layout.addLayout(toolbar)

        # Configuración del visor: WebEngine (Chromium) con fallback a QTextBrowser
        if HAS_WEBENGINE:
            self.web_view = QWebEngineView()
            self.web_page = WikiWebEnginePage(self)
            self.web_view.setPage(self.web_page)
            self.web_view.setStyleSheet("background-color: #1e1e2e; border: 1px solid #313244;")
            right_layout.addWidget(self.web_view, stretch=1)
        else:
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
        # 1. Preprocesar Callouts de Obsidian (> [!NOTE], etc.)
        text = preprocess_obsidian_callouts(raw_text)
        # 2. Preprocesar Wikilinks ([[CAT-105]] -> [CAT-105](wiki://CAT-105))
        text = preprocess_wikilinks(text)

        if HAS_WEBENGINE and self.web_view is not None:
            # Modo WebEngine con MathJax 3 SVG:
            # Proteger expresiones matemáticas para evitar que Python-Markdown escape '\\' o '_'
            math_store: Dict[str, str] = {}
            counter = 0

            def _save_block(m: 're.Match') -> str:
                nonlocal counter
                key = f"XXMATHBLOCK{counter}XX"
                math_store[key] = m.group(0)
                counter += 1
                return key

            def _save_inline(m: 're.Match') -> str:
                nonlocal counter
                key = f"XXMATHINLINE{counter}XX"
                math_store[key] = m.group(0)
                counter += 1
                return key

            protected = _BLOCK_MATH_RE.sub(_save_block, text)
            protected = _INLINE_MATH_RE.sub(_save_inline, protected)

            body_html = markdown.markdown(
                protected,
                extensions=['tables', 'fenced_code', 'toc', 'md_in_html']
            )

            # Restaurar bloques y expresiones matemáticas intactas
            for key, original in math_store.items():
                body_html = body_html.replace(key, original)

            mathjax_url = QUrl.fromLocalFile(str(MATHJAX_PATH)).toString()
            return _WEBENGINE_HTML_TEMPLATE.format(body=body_html, mathjax_url=mathjax_url)
        else:
            # Fallback QTextBrowser clásico
            processed = preprocess_latex_math(text)
            body_html = markdown.markdown(
                processed,
                extensions=['tables', 'fenced_code', 'toc', 'md_in_html']
            )
            return _WRAP_TEMPLATE.format(body=body_html)

    def _set_view_html(self, html: str, anchor: Optional[str] = None) -> None:
        """Asigna HTML al visor activo (WebEngine o QTextBrowser) con soporte de anclas."""
        if self.web_view is not None:
            base_url = QUrl.fromLocalFile(str(BASE_DIR) + "/")
            self.web_view.setHtml(html, base_url)
            if anchor:
                self.scroll_to_anchor(anchor)
        elif self.text_browser is not None:
            self.text_browser.setHtml(html)
            if anchor:
                self.text_browser.scrollToAnchor(anchor)

    def scroll_to_anchor(self, anchor: str) -> None:
        """Desplaza el visor hasta el ancla especificada."""
        if not anchor:
            return
        clean_anchor = anchor.lstrip('#')
        if self.web_view is not None:
            js = f"""
            (function() {{
                var el = document.getElementById('{clean_anchor}') || document.querySelector('a[name="{clean_anchor}"]');
                if (el) {{
                    el.scrollIntoView({{behavior: 'smooth', block: 'start'}});
                }}
            }})();
            """
            self.web_view.page().runJavaScript(js)
        elif self.text_browser is not None:
            self.text_browser.scrollToAnchor(clean_anchor)

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
        if HAS_WEBENGINE and self.web_view is not None:
            mathjax_url = QUrl.fromLocalFile(str(MATHJAX_PATH)).toString()
            return _WEBENGINE_HTML_TEMPLATE.format(body=body, mathjax_url=mathjax_url)
        return _WRAP_TEMPLATE.format(body=body)

    def _show_landing_page(self) -> None:
        body = (
            "<h1 style='color:#cba6f7;'>📖 Wiki Científica de PyPrinting 3.0</h1>"
            "<p style='color:#cdd6f4;'>Seleccione una nota del árbol de la izquierda, o utilice el "
            "buscador, para navegar por los Compendios Científicos (<b>CAT</b>), los Reportes de "
            "Sistema (<b>SYS</b>) y los Manuales de Módulo (<b>MOD</b>) de PyPrinting 3.0.</p>"
        )
        self._current_note_path = None
        self.btn_open_obsidian.setEnabled(False)
        if HAS_WEBENGINE and self.web_view is not None:
            mathjax_url = QUrl.fromLocalFile(str(MATHJAX_PATH)).toString()
            html = _WEBENGINE_HTML_TEMPLATE.format(body=body, mathjax_url=mathjax_url)
        else:
            html = _WRAP_TEMPLATE.format(body=body)
        self._set_view_html(html)
        self.setWindowTitle("📖 Wiki Científica — PyPrinting 3.0")
        self._show_status("Seleccione una nota para comenzar.")

    def _show_status(self, message: str) -> None:
        self.status_label.setText(message)

    # ------------------------------------------------------------------
    # Navegación pública y gestión de historial
    # ------------------------------------------------------------------
    def navigate_to(self, note_id: str, anchor: Optional[str] = None) -> None:
        """Muestra ``note_id`` (con ancla opcional) en el visor y actualiza el historial."""
        if not note_id:
            return
        self._display_note(note_id, anchor=anchor, push_history=True)

    def _display_note(self, note_id: str, anchor: Optional[str] = None, push_history: bool = True) -> None:
        note_id = note_id.upper()
        path = self._note_index.get(note_id)
        self._current_note_path = path

        if path is None or not path.is_file():
            self.btn_open_obsidian.setEnabled(False)
            html = self._render_error(note_id)
            self._set_view_html(html)
            self.setWindowTitle(f"📖 Wiki Científica — Nota no encontrada ({note_id})")
            self._show_status(f"No se encontró la nota '{note_id}' en el índice.")
        else:
            self.btn_open_obsidian.setEnabled(True)
            try:
                raw_text = path.read_text(encoding='utf-8')
            except Exception as exc:
                html = self._render_error(note_id, detail=str(exc))
                self._set_view_html(html)
                self.setWindowTitle(f"📖 Wiki Científica — Error de Lectura ({note_id})")
                self._show_status(f"Error al leer '{note_id}': {exc}")
            else:
                html = self._render_markdown(raw_text)
                self._set_view_html(html, anchor=anchor)
                title = self._note_titles.get(note_id, note_id)
                self.setWindowTitle(f"📖 Wiki Científica — {note_id}: {title}")
                self._show_status(f"Mostrando {note_id}.")

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
            return
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
    # Integración con Obsidian
    # ------------------------------------------------------------------
    def _on_open_obsidian_clicked(self) -> None:
        """Abre la nota activa directamente en la aplicación de escritorio Obsidian."""
        if self._current_note_path is None or not self._current_note_path.is_file():
            return
        try:
            rel_path = self._current_note_path.relative_to(BASE_DIR).as_posix()
            vault_name = urllib.parse.quote(BASE_DIR.name)
            file_param = urllib.parse.quote(rel_path)
            obsidian_url = QUrl(f"obsidian://open?vault={vault_name}&file={file_param}")
            QDesktopServices.openUrl(obsidian_url)
            self._show_status(f"Abriendo {self._current_note_id} en Obsidian...")
        except Exception as exc:
            self._show_status(f"Error al abrir en Obsidian: {exc}")

    # ------------------------------------------------------------------
    # Resolución de enlaces (wikilinks, anclas locales, http/https externos)
    # ------------------------------------------------------------------
    @staticmethod
    def resolve_wiki_url(url: QUrl) -> Tuple[Optional[str], Optional[str]]:
        """Resuelve una QUrl de esquema wiki:// a (note_id, anchor)."""
        if url.scheme() != 'wiki':
            return None, None
        raw_id = url.host()
        if not raw_id:
            raw_id = url.path().lstrip('/')
        note_id = raw_id.upper() if raw_id else None
        anchor = url.fragment() or None
        return note_id, anchor

    def _on_anchor_clicked(self, url: QUrl) -> None:
        """Gestiona el clic en un hipervínculo dentro del documento."""
        note_id, anchor = self.resolve_wiki_url(url)
        if note_id is not None:
            if note_id in self._note_index:
                self.navigate_to(note_id, anchor)
            else:
                self._show_status(f"Enlace roto: la nota '{note_id}' no existe en el índice.")
            return

        scheme = url.scheme()
        if scheme in ('http', 'https', 'obsidian'):
            QDesktopServices.openUrl(url)
            return

        if not scheme and url.hasFragment():
            self.scroll_to_anchor(url.fragment())
            return

        self._show_status(f"Enlace no soportado: {url.toString()}")
