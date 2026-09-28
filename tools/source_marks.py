# -*- coding: utf-8 -*-
"""
source_marks.py — Marcas de fuente: detector de cifras, validador de marcas y verificador de
informes de procedencia.

PyPrinting 3.0 / PySpectrum 3.0 — UNSAM Nanofotónica.
Diseño: `docs/evidence/auditoria_2026-09-27/F3_verificador_ronda2.md` §3 y §5 (`DEC-038`).

POR QUÉ EXISTE
--------------
La auditoría documental del 2026-09-27 encontró que la mitad de las afirmaciones de los
documentos eran falsas o estaban desactualizadas, y que los valores viajaban de un documento a
otro con atribuciones falsas. Este módulo es la parte **mecánica** del control de procedencia:
encuentra cifras físicas (también las escritas en LaTeX), valida las marcas `[fuente: …]` y
comprueba que un informe del agente `provenance-verifier` cite claves, páginas, citas textuales y
símbolos que existen. El juicio (qué respalda qué) es del agente; esto sólo evita que ese juicio
se apoye en una referencia rota o inventada.

REGLAS DE DISEÑO
----------------
* Sólo biblioteca estándar. No importa `config`, PyQt6 ni `core`: lee el código como texto o
  como AST, para no arrancar hilos ni exigir el stack de hardware (el mismo motivo que en
  `tests/test_prompt_corpus_integrity.py`).
* La raíz se calcula desde este archivo, así cada worktree se resuelve contra sí mismo.
* Nunca escribe en el repositorio, salvo `index-bib --update-counts`, que regenera
  `tools/bib_page_counts.json` (un paso de mantenimiento, no del agente). El índice por página
  va a `scratch/bib_index/`, que git ignora.

CLI
---
    python tools/source_marks.py scan <rutas> | --cached | --diff <rango>  [--code] [--json] [--strict]
    python tools/source_marks.py bib "<regex>" [--key M24]
    python tools/source_marks.py check-report <informe.md | ->
    python tools/source_marks.py index-bib [--update-counts]

Códigos de salida: 0 ante huecos de cobertura (siempre, salvo `--strict`); 1 con marcas mal
formadas, con `--strict` y huecos, o con filas rechazadas por `check-report`; 2 ante un error de
uso.
"""
from __future__ import annotations

import argparse
import ast
import functools
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tokenize
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

# ==============================================================================
# Rutas y constantes
# ==============================================================================
ROOT = Path(__file__).resolve().parent.parent
INVARIANTS = ROOT / ".claude" / "shared" / "lab-invariants.md"
RESPUESTAS = ROOT / "docs" / "evidence" / "auditoria_2026-09-27" / "RESPUESTAS_INVESTIGADOR.md"
DECISION_LEDGER = ROOT / "docs" / "decisions" / "DECISION_LOG.md"
BIB_DIR = ROOT / "docs" / "bibliografia"
BIB_INDEX_DIR = ROOT / "scratch" / "bib_index"
PAGE_COUNTS_FILE = ROOT / "tools" / "bib_page_counts.json"
CONFIG_FILE = ROOT / "config.py"

# Árboles que viven dentro del directorio pero NO son este repositorio (worktrees de Claude
# Code, entorno virtual, base de git). Ver la explicación en el gate.
FOREIGN_TREES = (".claude/worktrees", ".venv", ".git")

# Árboles que el detector y la validación de marcas no miran (§5.2 del diseño): las auditorías
# fechadas citan valores viejos a propósito, el ledger de decisiones es historia append-only y
# los documentos archivados se conservan sin reescribir (R1-11).
EXCLUDED_PREFIXES = ("docs/evidence/auditoria_", "reportes/archivo/")
EXCLUDED_FILES = ("docs/decisions/DECISION_LOG.md",)

# Documentos adheridos al test de cobertura (`tests/test_source_marks.py`). Un documento entra
# acá sólo después de que `provenance-verifier` lo verificó en modo `documento` y se marcaron sus
# cifras (fase 4 del plan). Cada uno lleva además, en su encabezado, la línea de adhesión
# `**Fuentes:** marcadas (AAAA-MM-DD, provenance-verifier)`. Rutas relativas a la raíz.
ADHERED_DOCUMENTS: tuple[str, ...] = ()
ADHESION_LINE = re.compile(r"\*\*Fuentes:\*\*\s*marcadas\s*\(\d{4}-\d{2}-\d{2},\s*provenance-verifier\)")

# Carpetas del legado, que son la referencia de funcionamiento del sistema (R1-12). Una ruta
# `legado <ruta>:<línea>` se resuelve contra estas bases, en orden.
LEGACY_BASES = (ROOT, ROOT.parent, ROOT.parent.parent)
LEGACY_TOPS = ("scratch/pyspectrum-legacy", "printing2", "Obsidian_Vault/printing2")

LABELS = ("fuente", "derivado", "experimental", "sin fuente", "a verificar", "ilustrativo", "refutado")
VERDICTS = ("RESPALDADO", "DERIVADO", "EXPERIMENTAL", "SIN FUENTE", "CONTRADICHO", "ESTRUCTURAL-A-VERIFICAR")
SECTION0_LABELS = ("RESPALDADO", "DERIVADO", "EXPERIMENTAL", "SIN FUENTE")
CITA_VALUES = ("verificada", "no contiene", "interna", "sin acceso", "ninguna")

# Un documento del repositorio nunca es respaldo (regla 1 de §2.4 del diseño). Tampoco una
# auditoría, un triage o las respuestas del investigador (que van en `[experimental: …]`).
_INTERNAL_SOURCE = re.compile(
    r"\b(?:CAT|SYS|MOD)-\d+|\bDEC-\d+|MANUAL_USUARIO|DECISION_LOG|EVIDENCE_LEDGER|lab-invariants"
    r"|\.claude/|CLAUDE\.md|CONSOLIDADO|TRIAGE_|auditoria_\d|/lotes/|PLAN_CORRECCIONES"
    r"|RESPUESTAS_INVESTIGADOR|\bR[123]-\w+",
    re.IGNORECASE,
)

# Negación e historización que el gate ya reconoce: una línea que cita un valor para rechazarlo
# es contenido correcto, no una afirmación.
NEGATING = re.compile(
    r"\bno es\b|\bno era\b|\bnunca\b|\bnot\b|≠|superad|supersed|históric|historic"
    r"|obsolet|equivocad|incorrect|stale|ya no\b",
    re.IGNORECASE,
)


# ==============================================================================
# Helpers compartidos con el gate (factorizados de tests/test_prompt_corpus_integrity.py)
# ==============================================================================
def in_foreign_tree(path: Path, root: Path = ROOT) -> bool:
    """¿La ruta está dentro de un árbol ajeno (worktree, .venv, .git)? Fuera de la raíz: no."""
    try:
        rel = Path(path).relative_to(root).as_posix()
    except ValueError:
        try:
            rel = Path(path).resolve().relative_to(root).as_posix()
        except ValueError:
            return False
    return any(rel == d or rel.startswith(d + "/") for d in FOREIGN_TREES)


def _blank_keep_newlines(match: re.Match) -> str:
    return "\n" * match.group(0).count("\n")


def strip_code_fences(text: str) -> str:
    """Vacía los bloques de código (plantillas y pseudocódigo) **conservando las líneas**.

    La versión anterior del gate los borraba, así que todo `archivo:línea` informado después de
    un bloque salía corrido (defecto D4 del diseño). Ahora cada bloque se reemplaza por tantos
    saltos de línea como tenía.
    """
    text = re.sub(r"````.*?````", _blank_keep_newlines, text, flags=re.DOTALL)
    return re.sub(r"```.*?```", _blank_keep_newlines, text, flags=re.DOTALL)


def _read(path: Path) -> str:
    return Path(path).read_text(encoding="utf-8", errors="ignore")


@functools.lru_cache(maxsize=64)
def _parse_py(abs_path: str, mtime: float) -> ast.Module | None:
    try:
        return ast.parse(_read(Path(abs_path)))
    except (SyntaxError, ValueError):
        return None


def _tree(rel_path: str, root: Path = ROOT) -> ast.Module | None:
    src = root / rel_path
    if not src.is_file():
        return None
    return _parse_py(str(src), src.stat().st_mtime)


def _module_level_value(tree: ast.Module, symbol: str):
    """Nodo del valor de la última asignación de módulo a `symbol`, o None."""
    node = None
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign):
            targets = stmt.targets
        elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
            targets = [stmt.target]
        else:
            continue
        if any(isinstance(t, ast.Name) and t.id == symbol for t in targets):
            node = stmt.value
    return node


def _find_function(tree: ast.Module, symbol: str):
    """Definición de función (a cualquier profundidad) con ese nombre; `Clase.metodo` también."""
    parts = symbol.split(".")
    if len(parts) == 2:
        for cls in ast.walk(tree):
            if isinstance(cls, ast.ClassDef) and cls.name == parts[0]:
                for node in cls.body:
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == parts[1]:
                        return node
        return None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == symbol:
            return node
    return None


def _first_sleep_literal(func: ast.AST):
    """Primer `time.sleep(<literal>)` **del cuerpo de la función**, en orden de fuente."""
    calls = []
    for node in ast.walk(func):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "sleep" and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "time" and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, (int, float))
                and not isinstance(node.args[0].value, bool)):
            calls.append((node.lineno, node.col_offset, float(node.args[0].value)))
    return min(calls)[2] if calls else None


def resolve_code_number(rel_path: str, symbol: str, root: Path = ROOT):
    """`ruta.py::SIMBOLO` a un número, leyendo el fuente sin importar el módulo.

    Dos formas: una asignación de módulo a un literal numérico (`SIMBOLO = 30.0`, con o sin
    anotación) y, si el símbolo es una función, el primer literal de `time.sleep(...)` **dentro
    de su cuerpo** (así se expresa el poll del watchdog y el pulso del filtro de densidad). La
    versión anterior buscaba el `time.sleep` con una regex que podía salirse de la función y
    tomar el de la siguiente; ahora se acota con el AST. Devuelve None si no resuelve.
    """
    tree = _tree(rel_path, root)
    if tree is None:
        return None
    node = _module_level_value(tree, symbol)
    if node is not None:
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub) and isinstance(node.operand, ast.Constant):
            node, sign = node.operand, -1.0
        else:
            sign = 1.0
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return sign * float(node.value)
        return None
    func = _find_function(tree, symbol)
    return _first_sleep_literal(func) if func is not None else None


def resolve_code_string(rel_path: str, symbol: str, root: Path = ROOT):
    """`ruta.py::SIMBOLO` a una cadena, si es una asignación de módulo a un literal de texto."""
    tree = _tree(rel_path, root)
    if tree is None:
        return None
    node = _module_level_value(tree, symbol)
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _subscript_node(tree: ast.Module, symbol: str, keys):
    node = _module_level_value(tree, symbol)
    for key in keys:
        if not isinstance(node, ast.Dict):
            return None, False
        node = next((v for k, v in zip(node.keys, node.values)
                     if isinstance(k, ast.Constant) and k.value == key), None)
        if node is None:
            return None, False
    return node, True


def resolve_code_subscript(rel_path: str, symbol: str, keys, root: Path = ROOT):
    """`ruta.py::SIMBOLO["k1"]["k2"]` al literal numérico de ese diccionario de módulo."""
    tree = _tree(rel_path, root)
    if tree is None:
        return None
    node, _ = _subscript_node(tree, symbol, keys)
    if (isinstance(node, ast.Constant) and isinstance(node.value, (int, float))
            and not isinstance(node.value, bool)):
        return float(node.value)
    return None


@dataclass
class CodeRef:
    exists: bool
    value: float | str | None = None
    unit: str | None = None
    detail: str = ""


_UNIT_SUFFIXES = (
    ("_NM_PER_MM", "nm/mm"), ("_US", "µs"), ("_MS", "ms"), ("_UM", "µm"), ("_NM", "nm"),
    ("_MM", "mm"), ("_HZ", "Hz"), ("_PX", "px"), ("_S", "s"), ("_V", "V"),
)


def _infer_unit(symbol: str) -> str | None:
    up = symbol.upper()
    for suffix, unit in _UNIT_SUFFIXES:
        if up.endswith(suffix):
            return unit
    return None


def _symbol_exists(tree: ast.Module, symbol: str) -> bool:
    parts = symbol.split(".")
    if len(parts) == 2:
        for cls in ast.walk(tree):
            if isinstance(cls, ast.ClassDef) and cls.name == parts[0]:
                for node in cls.body:
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == parts[1]:
                        return True
                    if isinstance(node, (ast.Assign, ast.AnnAssign)):
                        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                        if any(isinstance(t, ast.Name) and t.id == parts[1] for t in targets):
                            return True
        return False
    if _module_level_value(tree, symbol) is not None:
        return True
    for stmt in tree.body:  # asignación anotada sin valor, o import con alias
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name) and stmt.target.id == symbol:
            return True
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == symbol:
            return True
        if isinstance(node, ast.ClassDef):
            for sub in node.body:
                if isinstance(sub, (ast.Assign, ast.AnnAssign)):
                    targets = sub.targets if isinstance(sub, ast.Assign) else [sub.target]
                    if any(isinstance(t, ast.Name) and t.id == symbol for t in targets):
                        return True
    return False


_CODE_REF_TEXT = re.compile(r'^(?P<path>[\w/.\-]+\.py)::(?P<sym>[A-Za-z_][\w.]*)(?P<sub>(?:\["[^"\]]+"\])*)$')


def resolve_code_ref(ref: str, root: Path = ROOT) -> CodeRef:
    """`ruta.py::SIMBOLO` o `ruta.py::SIMBOLO["clave"]["campo"]`: ¿existe, y cuánto vale?

    A diferencia de los resolvers del gate, que extraen valores, esto comprueba primero la
    **existencia** (funciones, clases, atributos y diccionarios incluidos). La unidad se infiere
    del sufijo del símbolo (`_S`, `_MS`, `_UM`, `_NM`, `_MM`, `_V`, `_HZ`, `_PX`) o de
    `time.sleep` (segundos); si no se infiere, queda None y no hay comparación de valores.
    """
    m = _CODE_REF_TEXT.match(ref.strip().strip("`"))
    if not m:
        return CodeRef(False, detail=f"referencia de código mal formada: {ref!r}")
    rel_path, symbol = m.group("path"), m.group("sym")
    keys = re.findall(r'\["([^"\]]+)"\]', m.group("sub") or "")
    tree = _tree(rel_path, root)
    if tree is None:
        return CodeRef(False, detail=f"no existe el archivo `{rel_path}` (o no es Python válido)")
    if keys:
        node, found = _subscript_node(tree, symbol, keys)
        if not found:
            return CodeRef(False, detail=f"`{rel_path}::{symbol}` no tiene la entrada {keys}")
        value = None
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float, str)) and not isinstance(node.value, bool):
            value = float(node.value) if isinstance(node.value, (int, float)) else node.value
        unit = "NA" if keys[-1].lower() == "na" else _infer_unit(keys[-1])
        return CodeRef(True, value, unit if isinstance(value, float) else None)
    if not _symbol_exists(tree, symbol):
        return CodeRef(False, detail=f"`{symbol}` no existe en `{rel_path}`")
    num = resolve_code_number(rel_path, symbol, root)
    if num is not None:
        func = _find_function(tree, symbol) if _module_level_value(tree, symbol) is None else None
        return CodeRef(True, num, "s" if func is not None else _infer_unit(symbol))
    text = resolve_code_string(rel_path, symbol, root)
    return CodeRef(True, text, None)


# ==============================================================================
# Normalización de LaTeX (§5.1: el 74 % de las cifras de los documentos está en LaTeX)
# ==============================================================================
_SUPERSCRIPT = str.maketrans("0123456789-−+", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁻⁺")
_LATEX_SYMBOLS = {
    r"\pm": "±", r"\approx": "≈", r"\sim": "∼", r"\simeq": "≃", r"\leq": "≤", r"\geq": "≥",
    r"\le": "≤", r"\ge": "≥", r"\times": "×", r"\cdot": "·", r"\degree": "°", r"\AA": "Å",
    r"\Omega": "Ω", r"\micro": "µ", r"\mu": "µ", r"\lambda": "λ", r"\sigma": "σ", r"\tau": "τ",
    r"\kappa": "κ", r"\to": "→", r"\infty": "∞", r"\%": "%", r"\;": " ", r"\:": " ", r"\,": " ",
    r"\!": "", r"\ ": " ", r"\quad": " ", r"\qquad": " ",
}


def latex_to_plain(s: str) -> str:
    """Lleva una cifra escrita en LaTeX a texto plano, para que los detectores la vean.

    Cubre las formas que aparecen en los documentos reales: `\\text{}`, `\\mathrm{}` (y sus
    parientes), `\\,`, `\\ `, `~`, `\\mu` → µ, `\\times 10^{-n}` → × 10⁻ⁿ, `^\\circ` → °, `\\%` y
    los exponentes de unidad (`\\text{cm}^{-1}` → cm⁻¹). Unifica µ/μ y −/-. No cambia la
    cantidad de líneas, así que los números de línea se conservan.
    """
    s = s.replace("μ", "µ")
    # \mu antes de quitar \text{}: si no, `\mu\text{m}` queda `\mum` y la unidad se pierde
    s = re.sub(r"\\(?:mu|micro)(?![A-Za-z])", "µ", s)
    # \text{..}, \mathrm{..} y parientes: se queda el contenido (dos pasadas por anidación simple)
    for _ in range(2):
        s = re.sub(r"\\(?:text|mathrm|textrm|rm|mathit|textit|mathsf|mathbf|textbf|operatorname|unit|si)\s*\{([^{}]*)\}", r"\1", s)
    # \SI{valor}{unidad} de siunitx
    s = re.sub(r"\\SI\s*\{([^{}]*)\}\s*\{([^{}]*)\}", r"\1 \2", s)
    # × 10^{-n}  y  · 10^{n}
    s = re.sub(r"\\(?:times|cdot)\s*10\s*\^\s*\{?\s*([−+-]?\s*\d+)\s*\}?",
               lambda m: "× 10" + m.group(1).replace(" ", "").translate(_SUPERSCRIPT), s)
    # grados: ^\circ, ^{\circ}
    s = re.sub(r"\^\s*\{?\s*\\circ\s*\}?", "°", s)
    s = s.replace(r"\circ", "°")
    # exponentes de unidad: cm^{-1} → cm⁻¹, s^{-1} → s⁻¹ (sólo tras una letra)
    s = re.sub(r"(?<=[A-Za-zµ])\s*\^\s*\{\s*([−+-]?\d+)\s*\}", lambda m: m.group(1).translate(_SUPERSCRIPT), s)
    s = re.sub(r"(?<=[A-Za-zµ])\^([−+-]?\d)", lambda m: m.group(1).translate(_SUPERSCRIPT), s)
    # símbolos y espacios (los comandos con nombre, sólo si no siguen letras: \mu no es \mum)
    for cmd, rep in sorted(_LATEX_SYMBOLS.items(), key=lambda kv: -len(kv[0])):
        if cmd[1:].isalpha():
            s = re.sub(re.escape(cmd) + r"(?![A-Za-z])", rep, s)
        else:
            s = s.replace(cmd, rep)
    s = s.replace("~", " ")
    s = s.replace("{", "").replace("}", "")
    s = s.replace("−", "-")
    return re.sub(r"[ \t]{2,}", " ", s)


# ==============================================================================
# Detector de cifras físicas (§5.2)
# ==============================================================================
_UNITS = (
    "nm/min", "nm/mm", "nm/s", "µm/s", "l/mm", "mg/mL", "g/L", "mol/L", "kS/s", "MS/s", "S/s",
    "cm⁻¹", "cm-1", "cm^-1",
    "km", "mm", "cm", "µm", "um", "nm", "pm", "Å", "m",
    "min", "ms", "µs", "us", "ns", "ps", "fs", "s", "h",
    "THz", "GHz", "MHz", "kHz", "Hz",
    "kV", "mV", "µV", "V", "mA", "µA", "nA", "A",
    "kW", "mW", "µW", "nW", "W", "meV", "eV", "mJ", "µJ", "nJ", "J",
    "°C", "mK", "K",
    "mM", "µM", "nM", "pM", "M",
    "px", "bits", "bit", "AU",
)
_UNIT_ALT = "|".join(re.escape(u) for u in sorted(_UNITS, key=len, reverse=True))
_SUP = "⁰¹²³⁴⁵⁶⁷⁸⁹"
_NUM = rf"[−-]?\d+(?:[.,]\d+)?(?:\s*(?:×|x|·)\s*10\s*\^?\s*[⁻−-]?[{_SUP}\d]+)?"
_FIGURE = re.compile(
    rf"(?<![\w.,/:^−\-])(?P<num>{_NUM})"
    rf"(?:\s*(?:±|\+/-)\s*(?P<unc>\d+(?:[.,]\d+)?))?"
    rf"(?:\s*(?:–|—|-|−|\ba\b|\bto\b|\by\b)\s*(?P<num2>{_NUM}))?"
    rf"(?:\s*|-)(?P<unit>{_UNIT_ALT})(?![\w/{_SUP}⁻])"
)
_NA_OD = re.compile(r"\b(?P<unit>NA|OD)\s*(?:=|>|<|≥|≤|∼|~|≈)?\s*(?P<num>\d+(?:[.,]\d+)?)(?!\w|[.,]\d)")

_TIME = {"s": 1.0, "ms": 1e-3, "µs": 1e-6, "us": 1e-6, "ns": 1e-9, "ps": 1e-12, "fs": 1e-15, "min": 60.0, "h": 3600.0}
_LENGTH = {"m": 1.0, "km": 1e3, "cm": 1e-2, "mm": 1e-3, "µm": 1e-6, "um": 1e-6, "nm": 1e-9, "pm": 1e-12, "Å": 1e-10}
_FREQ = {"Hz": 1.0, "kHz": 1e3, "MHz": 1e6, "GHz": 1e9, "THz": 1e12}
_VOLT = {"V": 1.0, "mV": 1e-3, "µV": 1e-6, "kV": 1e3}
_DIMENSIONS = (_TIME, _LENGTH, _FREQ, _VOLT, {"px": 1.0}, {"nm/mm": 1.0}, {"µm/s": 1.0}, {"nm/min": 1.0},
               {"NA": 1.0})


def _dimension(unit: str):
    for dim in _DIMENSIONS:
        if unit in dim:
            return dim
    return None


@dataclass
class Figure:
    line: int
    raw: str
    value: float | None
    unit: str
    in_latex: bool
    in_table: bool
    context: str
    col: int = 0
    values: tuple = ()
    decimals: int = 0
    exempt: str = ""


def _parse_number(s: str) -> tuple[float | None, int]:
    """'2.1 × 10⁻²⁰' → (2.1e-20, 1). Devuelve también los decimales escritos."""
    s = s.strip().replace("−", "-")
    m = re.match(rf"(-?\d+(?:[.,](\d+))?)(?:\s*(?:×|x|·)\s*10\s*\^?\s*([⁻-]?[{_SUP}\d]+))?$", s)
    if not m:
        return None, 0
    mant = float(m.group(1).replace(",", "."))
    decimals = len(m.group(2) or "")
    if m.group(3):
        exp = m.group(3).translate(str.maketrans(_SUP + "⁻", "0123456789-"))
        try:
            return mant * 10 ** int(exp), decimals
        except ValueError:
            return None, decimals
    return mant, decimals


@functools.lru_cache(maxsize=4)
def configured_laser_wavelengths(config_path: str = str(CONFIG_FILE)) -> frozenset:
    """Longitudes de onda de `config.py::SHUTTERS` (los nombres de los láseres configurados).

    Esas cifras se usan como **nombre** del láser, no como afirmación física, y sin la exención
    el ruido del detector rondaría el 45 % en SYS-202 (§5.2). Una longitud de onda fuera de este
    conjunto no se exime: el "642 nm" de SYS-202 es justamente un identificador equivocado.
    """
    path = Path(config_path)
    if not path.is_file():
        return frozenset()
    tree = ast.parse(_read(path))
    node = _module_level_value(tree, "SHUTTERS")
    names = []
    if isinstance(node, (ast.List, ast.Tuple)):
        names = [e.value for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
    return frozenset(float(m.group(1)) for n in names for m in [re.match(r"\s*(\d+(?:\.\d+)?)\s*nm", n)] if m)


_CODE_SPAN = re.compile(r"(`+)(.+?)\1")


def _code_spans(line: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in _CODE_SPAN.finditer(line)]


def _blank_spans(line: str, spans) -> str:
    chars = list(line)
    for a, b in spans:
        for i in range(a, b):
            chars[i] = " "
    return "".join(chars)


def _strip_quote(line: str) -> str:
    return re.sub(r"^\s*(?:>\s?)+", "", line)


def _latex_segments(lines: list[str]) -> list[list[tuple[int, int, bool]]]:
    """Por línea, segmentos (inicio, fin, es_latex). Sigue los `$$` de varias líneas."""
    out = []
    in_display = False
    for line in lines:
        segs = []
        core = line.strip()
        if in_display:
            if "$$" in line:
                end = line.index("$$") + 2
                segs.append((0, end, True))
                rest_start = end
                in_display = False
            else:
                out.append([(0, len(line), True)])
                continue
        else:
            rest_start = 0
            if core.startswith("$$") and core.count("$$") == 1:
                out.append([(0, len(line), True)])
                in_display = True
                continue
        pos = rest_start
        for m in re.finditer(r"\$\$(.+?)\$\$|\$([^$\n]+?)\$", line[rest_start:]):
            a, b = m.start() + rest_start, m.end() + rest_start
            if a > pos:
                segs.append((pos, a, False))
            segs.append((a, b, True))
            pos = b
        if pos < len(line):
            segs.append((pos, len(line), False))
        out.append(segs)
    return out


def iter_figures(text: str, *, path: Path | None = None, exempt_wavelengths=None) -> Iterator[Figure]:
    """Cifras físicas del texto, con su línea **real** (los bloques de código quedan en blanco).

    Aplica las exclusiones de §5.2: bloques y spans de código, líneas con `[refutado: …]` o con
    una negación, identificadores, fechas, páginas y referencias a líneas, y los nombres de los
    láseres configurados (que se devuelven con `exempt="láser configurado"`).
    """
    if exempt_wavelengths is None:
        exempt_wavelengths = configured_laser_wavelengths()
    lines = strip_code_fences(text).splitlines()
    segments = _latex_segments(lines)
    for lineno, (line, segs) in enumerate(zip(lines, segments), start=1):
        if not line.strip():
            continue
        if "[refutado:" in line or NEGATING.search(re.sub(r"[*_`]", "", line)):
            continue
        blanked = _blank_spans(line, _code_spans(line))
        in_table = _strip_quote(line).lstrip().startswith("|")
        context = line.strip()[:160]
        for a, b, is_latex in segs:
            seg = blanked[a:b]
            if is_latex:
                seg = latex_to_plain(seg.replace("$", " "))
            else:
                seg = seg.replace("μ", "µ")
            for m in _FIGURE.finditer(seg):
                value, decimals = _parse_number(m.group("num"))
                values = (value,)
                if m.group("num2"):
                    values = (value, _parse_number(m.group("num2"))[0])
                unit = m.group("unit")
                unit = {"um": "µm", "us": "µs", "cm-1": "cm⁻¹", "cm^-1": "cm⁻¹", "bits": "bit"}.get(unit, unit)
                exempt = ""
                if (unit == "nm" and not m.group("num2") and not m.group("unc")
                        and value in exempt_wavelengths):
                    exempt = "láser configurado"
                col = a + (0 if is_latex else m.start())
                yield Figure(lineno, m.group(0).strip(), value, unit, is_latex, in_table, context,
                             col, values, decimals, exempt)
            for m in _NA_OD.finditer(seg):
                value, decimals = _parse_number(m.group("num"))
                col = a + (0 if is_latex else m.start())
                yield Figure(lineno, m.group(0).strip(), value, m.group("unit"), is_latex, in_table,
                             context, col, (value,), decimals, "")


# ==============================================================================
# Marcas de fuente (§3)
# ==============================================================================
@dataclass
class Mark:
    line: int
    label: str
    items: list
    scope: str
    raw: str
    col: int = 0
    content: str = ""
    in_latex: bool = False
    label_as_written: str = ""
    syntax_error: str = ""


_MARK_START = re.compile(r"\[\s*(" + "|".join(re.escape(lbl) for lbl in LABELS) + r")\b", re.IGNORECASE)


def _split_items(content: str) -> list[str]:
    """Divide por `;` fuera de backticks y de corchetes anidados."""
    items, buf, depth, i = [], [], 0, 0
    while i < len(content):
        ch = content[i]
        if ch == "`":
            j = content.find("`", i + 1)
            j = len(content) - 1 if j == -1 else j
            buf.append(content[i:j + 1])
            i = j + 1
            continue
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
        if ch == ";" and depth == 0:
            items.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
        i += 1
    if "".join(buf).strip():
        items.append("".join(buf).strip())
    return items


def _scan_marks_in_line(line: str) -> list[tuple[int, int, str, str, bool, str]]:
    """(inicio, fin, rótulo escrito, contenido, cerrada, error de sintaxis) de cada marca.

    Los backticks son un átomo: `]` y `;` dentro de un símbolo de código no cierran la marca.
    Una marca cuyo `[` cae dentro de un span de código se ignora (D1: los ejemplos de marcas en
    la documentación van entre backticks). `[texto](url)` es un enlace, no una marca.
    """
    spans = _code_spans(line)
    found = []
    pos = 0
    while True:
        m = _MARK_START.search(line, pos)
        if not m:
            break
        start = m.start()
        if any(a <= start < b for a, b in spans):
            pos = start + 1
            continue
        i, depth, closed = m.end(), 1, False
        while i < len(line):
            ch = line[i]
            span = next(((a, b) for a, b in spans if a == i), None)
            if span:
                i = span[1]
                continue
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    closed = True
                    break
            i += 1
        end = i + 1 if closed else len(line)
        if closed and end < len(line) and line[end] in "([":
            pos = end  # enlace markdown [texto](url) o [texto][ref]
            continue
        body = line[m.end():i] if closed else line[m.end():]
        if body.lstrip().startswith(":"):
            content, syntax = body.lstrip()[1:].strip(), ""
        elif body.strip():
            content, syntax = body.strip(), "falta ':' entre el rótulo y el contenido"
        else:
            content, syntax = "", ""
        found.append((start, end, m.group(1), content, closed, syntax))
        pos = end
    return found


# ==============================================================================
# Contexto de validación (claves de §9, puntos R-n, páginas, decisiones)
# ==============================================================================
def load_bib_keys(invariants: Path = INVARIANTS) -> dict[str, str]:
    """Clave de `lab-invariants` §9 (sin corchetes) → archivo relativo a `docs/bibliografia/`."""
    keys = {}
    text = _read(invariants)
    start = text.find("## 9.")
    section = text[start:] if start != -1 else ""
    end = section.find("\n## ", 5)
    section = section[:end] if end != -1 else section
    for m in re.finditer(r"^\|\s*\[([^\]]+)\]\s*\|[^|]*\|\s*`([^`]+)`", section, re.MULTILINE):
        keys[m.group(1).strip()] = m.group(2).strip()
    return keys


def load_answer_points(respuestas: Path = RESPUESTAS) -> set[str]:
    """Puntos citables de `RESPUESTAS_INVESTIGADOR.md`.

    * R1-n: los encabezados `## n.` **anteriores** a `# Segunda ronda` (no son literales, D2).
    * R2-n: los encabezados `## R2-n.`.
    * R3-X: los ítems `- **X.**` de la sección "R3 — Fase 1" (la forma que ya usa `lab-invariants`).
    """
    points = set()
    if not Path(respuestas).is_file():
        return points
    text = _read(respuestas)
    first, _, rest = text.partition("# Segunda ronda")
    points |= {f"R1-{n}" for n in re.findall(r"^## (\d+)\.", first, re.MULTILINE)}
    points |= {f"R2-{n}" for n in re.findall(r"^## R2-(\d+)\.", rest, re.MULTILINE)}
    m = re.search(r"^## R3 — Fase 1.*?(?=^## |\Z)", rest, re.MULTILINE | re.DOTALL)
    if m:
        points |= {f"R3-{x}" for x in re.findall(r"^- \*\*([A-Z])\.\*\*", m.group(0), re.MULTILINE)}
    return points


def load_page_counts(path: Path = PAGE_COUNTS_FILE) -> dict[str, int]:
    if not Path(path).is_file():
        return {}
    data = json.loads(_read(path))
    return {k: int(v) for k, v in data.get("pages", data).items() if isinstance(v, (int, float, str)) and str(v).isdigit()}


def load_decisions(ledger: Path = DECISION_LEDGER) -> set[str]:
    return set(re.findall(r"\bDEC-\d+\b", _read(ledger))) if Path(ledger).is_file() else set()


@dataclass
class Context:
    keys: dict
    answer_points: set
    page_counts: dict
    decisions: set
    root: Path = ROOT
    exempt_wavelengths: frozenset = frozenset()
    index_dir: Path = BIB_INDEX_DIR

    def is_pdf_key(self, key: str) -> bool:
        return self.keys.get(key, "").lower().endswith(".pdf")


@functools.lru_cache(maxsize=1)
def default_context() -> Context:
    return Context(load_bib_keys(), load_answer_points(), load_page_counts(), load_decisions(),
                   ROOT, configured_laser_wavelengths())


# ==============================================================================
# Análisis de un documento: unidades (oración, fila, bloque), marcas y cobertura
# ==============================================================================
@dataclass
class Unit:
    kind: str                 # sentence | row | heading | display | blockmark
    start: tuple              # (línea, columna)
    end: tuple                # (línea, columna) inclusive
    block_id: int = -1        # tabla o lista a la que pertenece
    column_covered: bool = False
    block_covered: bool = False
    marks: list = field(default_factory=list)
    figures: list = field(default_factory=list)

    def contains(self, line: int, col: int) -> bool:
        return self.start <= (line, col) <= self.end


@dataclass
class Analysis:
    path: str
    figures: list
    marks: list
    units: list
    notices: list = field(default_factory=list)

    def uncovered(self) -> list:
        out = []
        for u in self.units:
            covered = bool(u.marks) or u.column_covered or u.block_covered
            for f in u.figures:
                if not f.exempt and not covered:
                    out.append(f)
        return out

    def covered_figures(self, mark: Mark) -> list:
        for u in self.units:
            if mark in u.marks:
                if u.kind == "blockmark":
                    return [f for v in self.units if v.block_covered and getattr(v, "_by", None) is u for f in v.figures]
                return list(u.figures)
        return []


_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_HEADING = re.compile(r"^\s*#{1,6}\s")
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{3,}")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ¿¡(*\"“])")


def _split_cells(row: str) -> list[tuple[int, int]]:
    """Rangos (inicio, fin) de las celdas de una fila, ignorando `\\|` y pipes entre backticks."""
    spans = _code_spans(row)
    bars = [i for i, ch in enumerate(row) if ch == "|" and (i == 0 or row[i - 1] != "\\")
            and not any(a <= i < b for a, b in spans)]
    return [(bars[k] + 1, bars[k + 1]) for k in range(len(bars) - 1)]


def _cell_is_backed(cell: str) -> bool:
    c = re.sub(r"[*_`]", "", cell).strip()
    return bool(_MARK_START.search(cell)) or c.startswith(SECTION0_LABELS)


def analyze(text: str, path: str = "<texto>", ctx: Context | None = None) -> Analysis:
    """Cifras, marcas y unidades de alcance de un documento markdown."""
    ctx = ctx or default_context()
    lines = strip_code_fences(text).splitlines()
    figures = list(iter_figures(text, exempt_wavelengths=ctx.exempt_wavelengths))
    segments = _latex_segments(lines)
    units: list[Unit] = []
    marks: list[Mark] = []
    block_counter = [0]

    def new_block() -> int:
        block_counter[0] += 1
        return block_counter[0]

    # --- marcas ---------------------------------------------------------------
    for lineno, line in enumerate(lines, start=1):
        for start, end, label_written, content, closed, syntax in _scan_marks_in_line(line):
            latex = any(is_l and a <= start < b for a, b, is_l in segments[lineno - 1])
            core = _strip_quote(line).strip()
            scope = ("block" if core == line[start:end].strip() else "inline") if closed else "unclosed"
            items = _split_items(content) if content else []
            marks.append(Mark(lineno, label_written.lower(), items, scope, line[start:end], start,
                              content, latex, label_written, syntax))

    # --- unidades ---------------------------------------------------------------
    i, n = 0, len(lines)
    para: list[tuple[int, str]] = []   # (línea, texto) del párrafo en curso
    para_block = [-1]

    def flush_para():
        if not para:
            return
        joined, coords = "", []
        for k, (ln, txt) in enumerate(para):
            if k:  # el espacio que une dos líneas pertenece al comienzo de la siguiente
                joined += " "
                coords.append((ln, 0))
            coords.extend((ln, c) for c in range(len(txt)))
            joined += txt
        cuts = [0] + [m.end() for m in _SENTENCE_SPLIT.finditer(joined)] + [len(joined)]
        for a, b in zip(cuts, cuts[1:]):
            if b <= a or not coords:
                continue
            units.append(Unit("sentence", coords[a], coords[min(b, len(coords)) - 1], para_block[0]))
        para.clear()

    list_block = -1
    while i < n:
        line = lines[i]
        core = _strip_quote(line)
        lineno = i + 1
        if not core.strip():
            flush_para()
            list_block = -1
            i += 1
            continue
        if core.lstrip().startswith("|"):
            flush_para()
            list_block = -1
            bid = new_block()
            header, j = None, i
            source_cols: list[int] = []
            while j < n and _strip_quote(lines[j]).lstrip().startswith("|"):
                row = lines[j]
                cells = _split_cells(row)
                u = Unit("row", (j + 1, 0), (j + 1, max(len(row) - 1, 0)), bid)
                if header is None:
                    header = [re.sub(r"[*_`]", "", row[a:b]).strip().lower() for a, b in cells]
                    source_cols = [k for k, name in enumerate(header) if name in ("fuente", "respaldo")]
                elif not _TABLE_SEP.match(_strip_quote(row)):
                    u.column_covered = any(k < len(cells) and _cell_is_backed(row[cells[k][0]:cells[k][1]])
                                           for k in source_cols)
                    for mk in marks:  # una marca en la celda Fuente/Respaldo tiene alcance de columna
                        if mk.line == j + 1 and any(k < len(cells) and cells[k][0] <= mk.col < cells[k][1]
                                                    for k in source_cols):
                            mk.scope = "column"
                units.append(u)
                j += 1
            i = j
            continue
        if core.strip().startswith("$$"):
            flush_para()
            list_block = -1
            j = i
            if core.strip().count("$$") < 2:
                j = i + 1
                while j < n and "$$" not in lines[j]:
                    j += 1
            j = min(j, n - 1)
            units.append(Unit("display", (i + 1, 0), (j + 1, max(len(lines[j]) - 1, 0)), new_block()))
            i = j + 1
            continue
        line_marks = [mk for mk in marks if mk.line == lineno]
        if len(line_marks) == 1 and line_marks[0].scope == "block":
            flush_para()
            list_block = -1
            units.append(Unit("blockmark", (lineno, 0), (lineno, max(len(line) - 1, 0))))
            i += 1
            continue
        if _HEADING.match(core):
            flush_para()
            list_block = -1
            units.append(Unit("heading", (lineno, 0), (lineno, max(len(line) - 1, 0))))
            i += 1
            continue
        if _LIST_ITEM.match(core):
            flush_para()
            if list_block == -1:
                list_block = new_block()
            para_block[0] = list_block
        elif not para:
            para_block[0] = -1
        para.append((lineno, line))
        i += 1
    flush_para()

    # --- alcance de las marcas de bloque ---------------------------------------------
    for k, u in enumerate(units):
        if u.kind != "blockmark":
            continue
        nxt = units[k + 1] if k + 1 < len(units) else None
        prv = units[k - 1] if k > 0 else None
        target = None
        if nxt is not None and nxt.block_id != -1 and nxt.kind in ("row", "sentence") and nxt.start[0] - u.end[0] <= 2:
            target = nxt.block_id
        elif prv is not None and prv.kind == "display" and u.start[0] - prv.end[0] <= 1:
            target = prv.block_id
        if target is None:
            continue
        for v in units:
            if v.block_id == target:
                v.block_covered = True
                v._by = u  # type: ignore[attr-defined]

    # --- asignación de cifras y marcas a unidades ----------------------------------
    def owner(line: int, col: int):
        for u in units:
            if u.contains(line, col):
                return u
        return None

    notices = []
    for f in figures:
        u = owner(f.line, f.col)
        if u is None:
            u = next((v for v in units if v.start[0] <= f.line <= v.end[0]), None)
        if u is not None:
            u.figures.append(f)
    for mk in marks:
        u = owner(mk.line, mk.col) or next((v for v in units if v.start[0] <= mk.line <= v.end[0]), None)
        if u is not None:
            u.marks.append(mk)
            if u.kind == "blockmark" and not any(getattr(v, "_by", None) is u for v in units):
                notices.append(f"{path}:{mk.line}: marca de bloque sin tabla, lista ni ecuación inmediatamente contigua: no cubre nada")
    return Analysis(path, figures, marks, units, notices)


def coverage(text: str, path: str = "<texto>", ctx: Context | None = None) -> list[Figure]:
    """Cifras no cubiertas por una marca en línea, una columna Fuente/Respaldo o una marca de bloque."""
    return analyze(text, path, ctx).uncovered()


# ==============================================================================
# Validación de marcas (§5.4, test 1)
# ==============================================================================
_BIB_ITEM = re.compile(r"^(?P<key>[A-Za-z][\w-]*)(?:\s+p\.\s*(?P<p1>\d+)(?:\s*[-–]\s*(?P<p2>\d+))?)?(?P<rest>.*)$")
# `ruta.py:línea` (código ejecutable). Un `.md` del repositorio nunca es fuente (regla 1).
_FILE_LINE = re.compile(r"^`?(?P<path>[\w/.\-]+\.py):(?P<l1>\d+)(?:\s*[-–]\s*(?P<l2>\d+))?`?$")
_DOI = re.compile(r"^DOI\s+(?P<doi>10\.\d{4,9}/\S+)$", re.IGNORECASE)
_LEGACY = re.compile(r"^legado\s+(?P<path>\S+?):(?P<l1>\d+)(?:\s*[-–]\s*(?P<l2>\d+))?$", re.IGNORECASE)
_POINT = re.compile(r"\bR[123]-(?:\d+|[A-Z])\b")
_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_REF_ID = re.compile(r"\b(?:DEC-\d+|[A-Z]{1,3}\d{0,2}-[\w-]+|BANCO-\d+)\b")


def _line_count(path: Path) -> int:
    return len(_read(path).splitlines())


def _resolve_legacy(rel: str, ctx: Context):
    """(ruta existente | None, ¿el legado está disponible en esta máquina?)."""
    for base in LEGACY_BASES if ctx.root == ROOT else (ctx.root,):
        cand = base / rel
        if cand.is_file():
            return cand, True
    available = any((base / top).is_dir() for base in LEGACY_BASES for top in LEGACY_TOPS
                    if rel.replace("\\", "/").startswith(top.split("/")[0]))
    return None, available


def _values_match(documented: float, decimals: int, doc_unit: str, actual: float, act_unit: str) -> bool:
    """¿El valor del código, llevado a la unidad del texto, coincide al redondeo escrito?

    "12.8 nm/mm" coincide con 12.83 (un decimal declarado); "20 µm" tiene que ser exactamente 20.
    """
    dim = _dimension(doc_unit)
    if dim is None or act_unit not in dim:
        return False
    converted = actual * dim[act_unit] / dim[doc_unit]
    if decimals:
        tol = 0.5 * 10 ** (-decimals) * (1 + 1e-9)
    else:
        tol = 1e-9 * max(1.0, abs(documented))
    return abs(converted - documented) <= tol


def validate_mark(mark: Mark, ctx: Context | None = None, covered_figures: Iterable[Figure] = (),
                  notices: list | None = None) -> list[str]:
    """Errores de una marca (lista vacía si es válida). Reglas de §5.4, test 1, del diseño."""
    ctx = ctx or default_context()
    notices = notices if notices is not None else []
    errors = []
    label = mark.label
    if mark.scope == "unclosed":
        return [f"marca sin cerrar: {mark.raw!r}"]
    if mark.syntax_error:
        errors.append(mark.syntax_error)
    if mark.label_as_written != mark.label_as_written.lower():
        errors.append(f"el rótulo va en minúsculas: [{mark.label_as_written.lower()}: …]")
    if mark.in_latex:
        errors.append("la marca nunca va dentro de $…$: se escribe afuera, en la misma oración")
    content = mark.content

    if label == "ilustrativo":
        if content:
            errors.append("[ilustrativo] no lleva contenido")
        return errors
    if label == "sin fuente":
        return errors
    if not content:
        errors.append(f"[{label}: …] requiere contenido")
        return errors
    if label == "derivado":
        if "=" not in content:
            errors.append("[derivado: …] tiene que incluir la fórmula, con un '='")
        return errors
    if label == "a verificar":
        return errors
    if label == "refutado":
        ids = _REF_ID.findall(content)
        if not ids:
            errors.append("[refutado: …] tiene que nombrar el hallazgo o la decisión que lo refuta (DEC-xxx, T-05…)")
        for dec in re.findall(r"\bDEC-\d+\b", content):
            if dec not in ctx.decisions:
                errors.append(f"{dec} no existe en DECISION_LOG.md")
        return errors
    if label == "experimental":
        points = _POINT.findall(content)
        if not points and "método en desarrollo" not in content.lower():
            errors.append("[experimental: …] tiene que citar un punto de RESPUESTAS_INVESTIGADOR.md (R1-n, R2-n, R3-X) o decir 'método en desarrollo'")
        for p in points:
            if p not in ctx.answer_points:
                errors.append(f"el punto {p} no existe en RESPUESTAS_INVESTIGADOR.md")
        if "investigador" in content.lower() and not _DATE.search(content):
            errors.append("un dato del investigador lleva su fecha (AAAA-MM-DD)")
        return errors

    # --- fuente ---------------------------------------------------------------
    figures = [f for f in covered_figures if not f.exempt]
    for item in mark.items:
        plain = item.strip()
        if not plain:
            errors.append("ítem vacío (dos ';' seguidos)")
            continue
        code = _CODE_REF_TEXT.match(plain.strip("`"))
        lg = _LEGACY.match(plain)
        if not code and not lg:
            if _INTERNAL_SOURCE.search(plain.replace("`", "")) or re.search(r"\.md\b", plain):
                errors.append(f"'{plain}': un documento del repositorio, una auditoría o un punto del "
                              "investigador no es fuente (usá la fuente primaria, o [experimental: …])")
                continue
            if plain.startswith("[") or "]" in plain:
                errors.append(f"'{plain}': la clave de §9 va sin corchetes dentro de la marca")
                continue
        if code:
            ref = resolve_code_ref(plain, ctx.root)
            if not ref.exists:
                errors.append(ref.detail)
                continue
            if isinstance(ref.value, float) and ref.unit:
                comparable = [f for f in figures if _dimension(f.unit) is not None and ref.unit in _dimension(f.unit)]
                if comparable and not any(
                        _values_match(v, f.decimals, f.unit, ref.value, ref.unit)
                        for f in comparable for v in f.values if v is not None):
                    written = ", ".join(f.raw for f in comparable)
                    errors.append(f"el valor no coincide (D3): `{plain.strip('`')}` vale {ref.value:g} {ref.unit} "
                                  f"y el texto dice {written}")
            continue
        fl = _FILE_LINE.match(plain)
        if fl:
            target = ctx.root / fl.group("path")
            if not target.is_file():
                errors.append(f"no existe `{fl.group('path')}`")
            else:
                last = int(fl.group("l2") or fl.group("l1"))
                if last > _line_count(target):
                    errors.append(f"`{fl.group('path')}` tiene {_line_count(target)} líneas, no {last}")
            continue
        if _DOI.match(plain):
            continue
        if lg:
            found, available = _resolve_legacy(lg.group("path"), ctx)
            if found is None:
                if available:
                    errors.append(f"no existe en el legado: {lg.group('path')}")
                else:
                    notices.append(f"legado no disponible en esta máquina; se omite {lg.group('path')}")
            else:
                last = int(lg.group("l2") or lg.group("l1"))
                if last > _line_count(found):
                    errors.append(f"legado {lg.group('path')} tiene {_line_count(found)} líneas, no {last}")
            continue
        if plain.lower().startswith("doi"):
            errors.append(f"DOI mal formado: '{plain}' (forma: DOI 10.xxxx/…)")
            continue
        bib = _BIB_ITEM.match(plain)
        if bib and bib.group("key") in ctx.keys:
            key = bib.group("key")
            if ctx.is_pdf_key(key):
                if not bib.group("p1"):
                    errors.append(f"'{plain}': falta la página física (KEY p. N)")
                    continue
                pages = ctx.page_counts.get(key)
                p1, p2 = int(bib.group("p1")), int(bib.group("p2") or bib.group("p1"))
                if pages is None:
                    errors.append(f"{key} no figura en tools/bib_page_counts.json (python tools/source_marks.py index-bib --update-counts)")
                elif not (1 <= p1 <= p2 <= pages):
                    errors.append(f"{key} p. {bib.group('p1')}{'-' + bib.group('p2') if bib.group('p2') else ''}: "
                                  f"fuera del PDF, que tiene {pages} páginas")
            continue
        if bib:
            errors.append(f"'{bib.group('key')}' no es una clave de lab-invariants §9")
            continue
        errors.append(f"ítem no reconocido: '{plain}' (formas: KEY p. N · `ruta.py::SIMBOLO` · ruta:línea · DOI 10.… · legado ruta:línea)")
    return errors


def validate_text(text: str, path: str = "<texto>", ctx: Context | None = None) -> tuple[list[str], list[str]]:
    """(errores, avisos) de todas las marcas de un texto."""
    ctx = ctx or default_context()
    if not _MARK_START.search(text):
        return [], []
    an = analyze(text, path, ctx)
    errors, notices = [], list(an.notices)
    for mk in an.marks:
        for err in validate_mark(mk, ctx, an.covered_figures(mk), notices):
            errors.append(f"{path}:{mk.line}: {mk.raw} — {err}")
    return errors, notices


def _excluded(rel: str) -> bool:
    return rel in EXCLUDED_FILES or any(rel.startswith(p) for p in EXCLUDED_PREFIXES)


def marked_surface(root: Path = ROOT) -> list[Path]:
    """Archivos donde toda marca tiene que ser válida: `docs/`, `reportes/`, `CLAUDE.md`, `.claude/`."""
    files = [root / "CLAUDE.md"]
    for base in ("docs", "reportes", ".claude"):
        files.extend(sorted((root / base).rglob("*.md")))
    out = []
    for f in files:
        if not f.is_file() or in_foreign_tree(f, root):
            continue
        rel = f.relative_to(root).as_posix()
        if not _excluded(rel):
            out.append(f)
    return out


def validate_corpus_marks(root: Path = ROOT, ctx: Context | None = None) -> tuple[list[str], list[str]]:
    ctx = ctx or default_context()
    errors, notices = [], []
    for f in marked_surface(root):
        e, n = validate_text(_read(f), f.relative_to(root).as_posix(), ctx)
        errors += e
        notices += n
    return errors, notices


def adhered_coverage_findings(documents: Iterable = None, root: Path = ROOT, ctx: Context | None = None) -> list[str]:
    """Advertencias de cobertura de los documentos adheridos (test 2: sólo advierte)."""
    ctx = ctx or default_context()
    check_unlisted = documents is None
    documents = ADHERED_DOCUMENTS if documents is None else documents
    findings = []
    listed = set()
    for doc in documents:
        p = Path(doc) if Path(doc).is_absolute() else root / doc
        label = p.relative_to(root).as_posix() if p.is_relative_to(root) else str(p)
        listed.add(label)
        if not p.is_file():
            findings.append(f"{label}: está en ADHERED_DOCUMENTS pero no existe")
            continue
        text = _read(p)
        if not ADHESION_LINE.search(text):
            findings.append(f"{label}: falta la línea de adhesión '**Fuentes:** marcadas (AAAA-MM-DD, provenance-verifier)'")
        for fig in coverage(text, label, ctx):
            where = "LaTeX" if fig.in_latex else ("tabla" if fig.in_table else "texto")
            findings.append(f"{label}:{fig.line}: cifra sin marca ({where}): {fig.raw}  ::  {fig.context[:90]}")
    if check_unlisted:
        for f in marked_surface(root):
            label = f.relative_to(root).as_posix()
            if label not in listed and ADHESION_LINE.search(_read(f)):
                findings.append(f"{label}: tiene la línea de adhesión pero no está en ADHERED_DOCUMENTS (tools/source_marks.py)")
    return findings


# ==============================================================================
# Comentarios, docstrings y textos de la GUI (modo `comentarios`, sólo CLI)
# ==============================================================================
_UI_CALLS = {"QLabel", "QPushButton", "QGroupBox", "QCheckBox", "QRadioButton", "QAction", "QToolButton",
             "setToolTip", "setText", "setWindowTitle", "setStatusTip", "setPlaceholderText", "setTitle",
             "addTab", "setTabText", "setWhatsThis", "showMessage", "information", "warning", "critical", "question"}


def _call_name(node: ast.Call) -> str:
    f = node.func
    return f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else "")


def _const_text(node) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(v.value if isinstance(v, ast.Constant) else "{…}" for v in node.values)
    return None


def extract_code_text(py: Path | None = None, src: str | None = None) -> Iterator[tuple[int, str, str]]:
    """(línea, tipo, texto) de los comentarios, docstrings y textos de UI de un `.py`.

    Los comentarios salen de `tokenize`; los docstrings y los textos de UI (argumentos de
    `QLabel`, `QPushButton`, `QGroupBox`, `setToolTip`, `setText`, diálogos…), del AST, que ve
    también los tooltips de varias líneas armados por concatenación implícita (D7). Acepta el
    fuente como texto (`src`) para leer una versión de git sin escribir ningún archivo.
    """
    src = _read(py) if src is None else src
    out = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                out.append((tok.start[0], "comment", tok.string.lstrip("#").strip()))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass
    try:
        tree = ast.parse(src)
    except SyntaxError:
        tree = None
    if tree is not None:
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                body = getattr(node, "body", [])
                if body and isinstance(body[0], ast.Expr):
                    text = _const_text(body[0].value)
                    if text is not None:
                        for k, ln in enumerate(text.splitlines()):
                            if ln.strip():
                                out.append((body[0].lineno + k, "docstring", ln.strip()))
            if isinstance(node, ast.Call) and _call_name(node) in _UI_CALLS:
                for arg in list(node.args) + [kw.value for kw in node.keywords]:
                    text = _const_text(arg)
                    if text and text.strip():
                        out.append((arg.lineno, "ui_string", " ".join(text.split())))
    return iter(sorted(out))


# ==============================================================================
# Bibliografía: índice por página física, búsqueda y verificación de citas (sólo CLI)
# ==============================================================================
def _find_pdftotext() -> str | None:
    exe = shutil.which("pdftotext")
    if exe:
        return exe
    for cand in (r"C:\Program Files\Git\mingw64\bin\pdftotext.exe",
                 r"C:\Program Files (x86)\Git\mingw64\bin\pdftotext.exe"):
        if Path(cand).is_file():
            return cand
    return None


def index_bib(ctx: Context | None = None, index_dir: Path = BIB_INDEX_DIR, force: bool = False) -> dict[str, int]:
    """Construye `scratch/bib_index/<CLAVE>/p<N>.txt` con `pdftotext` (una página por archivo).

    Se reconstruye una clave sólo cuando cambia la fecha de su PDF. Devuelve clave → páginas.
    """
    ctx = ctx or default_context()
    exe = _find_pdftotext()
    if exe is None:
        raise RuntimeError("pdftotext no está en el PATH (en esta máquina viene con Git Bash, /mingw64/bin)")
    counts = {}
    for key, rel in sorted(ctx.keys.items()):
        pdf = BIB_DIR / rel
        if not rel.lower().endswith(".pdf") or not pdf.is_file():
            continue
        kdir = index_dir / key
        meta = kdir / "meta.json"
        mtime = pdf.stat().st_mtime
        if meta.is_file() and not force:
            data = json.loads(_read(meta))
            if abs(data.get("mtime", 0) - mtime) < 1e-6:
                counts[key] = int(data["pages"])
                continue
        out = subprocess.run([exe, "-enc", "UTF-8", str(pdf), "-"], capture_output=True, check=True).stdout
        pages = out.decode("utf-8", errors="replace").split("\f")
        if pages and not pages[-1].strip():
            pages = pages[:-1]
        kdir.mkdir(parents=True, exist_ok=True)
        for old in kdir.glob("p*.txt"):
            old.unlink()
        for k, page in enumerate(pages, start=1):
            (kdir / f"p{k}.txt").write_text(page, encoding="utf-8")
        meta.write_text(json.dumps({"mtime": mtime, "pages": len(pages), "file": rel}, ensure_ascii=False), encoding="utf-8")
        counts[key] = len(pages)
    return counts


def _page_text(key: str, page: int, index_dir: Path = BIB_INDEX_DIR) -> str | None:
    p = index_dir / key / f"p{page}.txt"
    return _read(p) if p.is_file() else None


def bib_search(pattern: str, keys: list[str] | None = None, index_dir: Path = BIB_INDEX_DIR) -> list[tuple[str, int, str]]:
    """(clave, página física, línea) de cada coincidencia de la regex en el índice por página."""
    rx = re.compile(pattern, re.IGNORECASE)
    hits = []
    if not index_dir.is_dir():
        return hits
    for kdir in sorted(d for d in index_dir.iterdir() if d.is_dir()):
        if keys and kdir.name not in keys:
            continue
        for p in sorted(kdir.glob("p*.txt"), key=lambda q: int(q.stem[1:])):
            for line in _read(p).splitlines():
                if rx.search(line):
                    hits.append((kdir.name, int(p.stem[1:]), line.strip()))
    return hits


def _normalize_quote(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("\u00ad", "")
    s = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", s)            # guion de corte de línea
    s = s.translate(str.maketrans({"‐": "-", "‑": "-", "–": "-", "—": "-", "−": "-",
                                   "“": '"', "”": '"', "„": '"', "«": '"', "»": '"', "‘": "'", "’": "'"}))
    return re.sub(r"\s+", " ", s).strip().casefold()


def check_quote(key: str, page: int, quote: str, index_dir: Path = BIB_INDEX_DIR, last_page: int | None = None) -> bool | None:
    """¿La cita textual está en esa página física (o en el rango)? None si no hay índice."""
    texts = [_page_text(key, p, index_dir) for p in range(page, (last_page or page) + 1)]
    if all(t is None for t in texts):
        return None
    hay = _normalize_quote(" ".join(t for t in texts if t))
    return _normalize_quote(quote) in hay


# ==============================================================================
# check-report: valida la tabla del informe del verificador (§2.5)
# ==============================================================================
_REPORT_BIB = re.compile(r"\[?(?P<key>[A-Z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)?)\]?\s+p\.\s*(?P<p1>\d+)(?:\s*[-–]\s*(?P<p2>\d+))?")
_REPORT_BRACKET_KEY = re.compile(r"\[(?P<key>[A-Z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)?)\]")
_REPORT_QUOTE = re.compile(r'"([^"]+)"|“([^”]+)”|«([^»]+)»')
_REPORT_CODE = re.compile(r'`?(?P<ref>[\w/.\-]+\.py::[A-Za-z_][\w.]*(?:\["[^"\]]+"\])*)`?')
_REPORT_FILE_LINE = re.compile(r'`?(?<![\w/.\-])(?P<path>[\w/.\-]+/[\w.\-]+\.(?:py|md|json|txt|yaml|yml)|[\w.\-]+\.(?:py|md|json|txt|yaml|yml)):(?P<l1>\d+)(?:\s*[-–]\s*(?P<l2>\d+))?`?')


def _norm_header(h: str) -> str:
    h = unicodedata.normalize("NFKD", re.sub(r"[*_`]", "", h)).encode("ascii", "ignore").decode()
    return h.strip().lower()


def _report_rows(text: str):
    """Filas (número de línea, dict columna → celda) de toda tabla con Veredicto y Respaldo."""
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        if lines[i].lstrip().startswith("|"):
            cells = _split_cells(lines[i])
            header = [_norm_header(lines[i][a:b]) for a, b in cells]
            if "veredicto" in header and "respaldo" in header:
                j = i + 1
                while j < len(lines) and lines[j].lstrip().startswith("|"):
                    if not _TABLE_SEP.match(lines[j]):
                        cs = _split_cells(lines[j])
                        yield j + 1, {header[k]: lines[j][a:b].strip() for k, (a, b) in enumerate(cs) if k < len(header)}
                    j += 1
                i = j
                continue
        i += 1


def _check_file_line(path: str, l1: int, l2: int | None, ctx: Context) -> str | None:
    for base in (ctx.root,) + tuple(b for b in LEGACY_BASES if b != ctx.root):
        cand = base / path
        if cand.is_file():
            n = _line_count(cand)
            last = l2 or l1
            return None if last <= n else f"`{path}` tiene {n} líneas, no {last}"
    # nombre abreviado (sin carpeta): se busca en el repo y en el legado
    if "/" not in path:
        for base in (ctx.root, ROOT / "scratch" / "pyspectrum-legacy", ROOT.parent / "printing2"):
            hits = list(base.rglob(path)) if base.is_dir() else []
            hits = [h for h in hits if not in_foreign_tree(h, ctx.root)]
            if hits:
                return None if (l2 or l1) <= _line_count(hits[0]) else f"`{path}` tiene {_line_count(hits[0])} líneas, no {l2 or l1}"
    return f"no existe `{path}`"


def check_report(report_md: Path, ctx: Context | None = None, index_dir: Path | None = None) -> list[str]:
    """Errores de un informe de `provenance-verifier` guardado en un archivo (ver `check_report_text`)."""
    return check_report_text(_read(Path(report_md)), ctx, index_dir)


def check_report_text(text: str, ctx: Context | None = None, index_dir: Path | None = None) -> list[str]:
    """Errores de un informe de `provenance-verifier`: claves, páginas, citas, símbolos, puntos.

    Rechaza, entre otras cosas, una página fuera del PDF, una cita que no está en la página, un
    símbolo de código inexistente y una clave que no está en `lab-invariants` §9 (§7.1 del
    diseño). Una cita que no se puede comprobar porque falta el índice por página también se
    informa: sin cita verificada no hay RESPALDADO de bibliografía (regla 5 del agente).
    """
    ctx = ctx or default_context()
    index_dir = index_dir or ctx.index_dir
    errors = []
    n_rows = 0
    for lineno, row in _report_rows(text):
        n_rows += 1
        where = f"fila l. {lineno} (#{row.get('#', '?')})"
        verdict = re.sub(r"[*_`]", "", row.get("veredicto", "")).strip()
        # veredicto por aspecto: "RESPALDADO (canal) · EXPERIMENTAL (sentido up/down)"
        aspects = [a.strip() for a in verdict.split("·") if a.strip()]
        if not aspects or not all(a.upper().startswith(VERDICTS) for a in aspects):
            errors.append(f"{where}: veredicto no reconocido: {verdict!r}")
        cita = re.sub(r"[*_`]", "", row.get("cita del texto", "")).strip().lower()
        if cita and not cita.startswith(CITA_VALUES):
            errors.append(f"{where}: 'Cita del texto' no reconocida: {cita!r} (valores: {', '.join(CITA_VALUES)})")
        backing = row.get("respaldo", "")
        needs_quote = any(a.upper().startswith(("RESPALDADO", "CONTRADICHO")) for a in aspects)
        # claves y páginas
        bib_refs = []
        for m in _REPORT_BIB.finditer(backing):
            key = m.group("key")
            if key not in ctx.keys:
                errors.append(f"{where}: '{key}' no es una clave de lab-invariants §9")
                continue
            p1, p2 = int(m.group("p1")), int(m.group("p2") or m.group("p1"))
            pages = ctx.page_counts.get(key)
            if ctx.is_pdf_key(key) and pages is not None and not (1 <= p1 <= p2 <= pages):
                errors.append(f"{where}: {key} p. {p1}{'-' + str(p2) if p2 != p1 else ''} fuera del PDF ({pages} páginas)")
                continue
            bib_refs.append((m.end(), key, p1, p2))
        bib_spans = [(m.start(), m.end()) for m in _REPORT_BIB.finditer(backing)]
        for m in re.finditer(r"\bp\.\s*\d+", backing):
            if not any(a <= m.start() < b for a, b in bib_spans):
                errors.append(f"{where}: '{m.group(0)}' sin clave de lab-invariants §9 delante (forma: KEY p. N)")
        for m in _REPORT_BRACKET_KEY.finditer(backing):
            if m.group("key") not in ctx.keys:
                errors.append(f"{where}: '[{m.group('key')}]' no es una clave de lab-invariants §9")
        # citas textuales, asociadas a la referencia bibliográfica que las precede
        quoted_refs = set()
        for m in _REPORT_QUOTE.finditer(backing):
            quote = next(g for g in m.groups() if g is not None)
            prev = [r for r in bib_refs if r[0] <= m.start()]
            if not prev:
                continue
            _, key, p1, p2 = prev[-1]
            quoted_refs.add((key, p1))
            if len(quote.split()) > 15:
                errors.append(f"{where}: la cita de {key} p. {p1} tiene {len(quote.split())} palabras (máximo 15)")
            ok = check_quote(key, p1, quote, index_dir, p2)
            if ok is None:
                errors.append(f"{where}: no se pudo comprobar la cita de {key} p. {p1}: falta el índice por página "
                              "(python tools/source_marks.py index-bib)")
            elif not ok:
                errors.append(f"{where}: la cita \"{quote[:60]}\" no está en {key} p. {p1}{'-' + str(p2) if p2 != p1 else ''}")
        if needs_quote:
            for _, key, p1, _ in bib_refs:
                if (key, p1) not in quoted_refs:
                    errors.append(f"{where}: {key} p. {p1} sin cita textual (toda fila RESPALDADO o CONTRADICHO de bibliografía la lleva)")
        # símbolos de código
        code_spans = []
        for m in _REPORT_CODE.finditer(backing):
            code_spans.append((m.start(), m.end()))
            ref = resolve_code_ref(m.group("ref"), ctx.root)
            if not ref.exists:
                errors.append(f"{where}: {ref.detail}")
        # archivo:línea (también el del legado)
        for m in _REPORT_FILE_LINE.finditer(backing):
            if any(a <= m.start() < b for a, b in code_spans):
                continue
            err = _check_file_line(m.group("path"), int(m.group("l1")), int(m.group("l2")) if m.group("l2") else None, ctx)
            if err:
                errors.append(f"{where}: {err}")
        # puntos del investigador
        for p in _POINT.findall(backing):
            if p not in ctx.answer_points:
                errors.append(f"{where}: el punto {p} no existe en RESPUESTAS_INVESTIGADOR.md")
        # respaldo sólo interno
        if aspects and aspects[0].upper().startswith("RESPALDADO"):
            stripped = _INTERNAL_SOURCE.sub("", backing)
            if (_INTERNAL_SOURCE.search(backing) and not bib_refs and not code_spans
                    and not _REPORT_FILE_LINE.search(stripped) and "DOI" not in backing.upper()):
                errors.append(f"{where}: RESPALDADO con un respaldo sólo interno (un documento del repositorio nunca es respaldo)")
        # ubicación
        loc = row.get("ubicacion", "")
        m = _REPORT_FILE_LINE.search(loc)
        if m and ("/" in m.group("path") or m.group("path").endswith(".py")):
            err = _check_file_line(m.group("path"), int(m.group("l1")), int(m.group("l2")) if m.group("l2") else None, ctx)
            if err:
                errors.append(f"{where}: ubicación: {err}")
    if n_rows == 0:
        errors.append("no se encontró ninguna tabla con las columnas 'Veredicto' y 'Respaldo'")
    return errors


# ==============================================================================
# scan: triage mecánico de un diff o de un documento
# ==============================================================================
_STRUCTURAL = re.compile(
    r"\b(?:port\d/line\d+|line\d+|ao\d|ai\d|flipper|notch|espejo|mirror|obturador(?:es)?|shutters?|filtro|filter|"
    r"BNC(?:-2110)?|SCB-68|polaridad|polarity|activ[oa] en (?:alto|bajo)|active[- ](?:low|high)|canal(?:es)?|"
    r"channels?|actuador|servo|solenoide|pinout|bornera|conector|beamsplitter|divisor de haz)\b",
    re.IGNORECASE,
)
_STATUS = re.compile(r"\b(?:implementad[oa]s?|implemented|certificad[oa]s?|certified|vigente|producci[oó]n|production|"
                     r"validad[oa]s?|validated|\d+\s*/\s*\d+\s+tests?)\b", re.IGNORECASE)
_CITATION = re.compile(r"\bDOI\b|\b10\.\d{4,9}/|\bet al\.|\[[A-Z][A-Za-z]*-?[A-Za-z]*\d*\](?!\()")


def _git(*args: str) -> str:
    res = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0:
        raise RuntimeError(res.stderr.strip() or f"git {' '.join(args)} falló")
    return res.stdout


def _changed_lines(diff_args: list[str]) -> dict[str, set[int]]:
    out = _git("diff", "--unified=0", "--no-color", "--no-ext-diff", *diff_args)
    changed, current = {}, None
    for line in out.splitlines():
        if line.startswith("+++ "):
            current = None if line.strip() == "+++ /dev/null" else line[6:] if line.startswith("+++ b/") else line[4:]
            if current:
                changed.setdefault(current, set())
        elif line.startswith("@@") and current:
            m = re.search(r"\+(\d+)(?:,(\d+))?", line)
            start, count = int(m.group(1)), int(m.group(2) if m.group(2) is not None else 1)
            changed[current].update(range(start, start + count))
    return changed


def _in_scan_scope(rel: str, code: bool) -> bool:
    if _excluded(rel):
        return False
    if rel.endswith(".md"):
        return rel == "CLAUDE.md" or rel.startswith(("docs/", "reportes/", ".claude/")) or "/" not in rel
    return code and rel.endswith(".py")


def _scan_lines(lines_with_no: Iterable[tuple[int, str]], kind: str) -> dict:
    out = {"structural": [], "status": [], "citations": []}
    for ln, txt in lines_with_no:
        clean = _blank_spans(txt, _code_spans(txt)) if kind == "md" else txt
        if _STRUCTURAL.search(clean):
            out["structural"].append({"line": ln, "text": txt.strip()[:160]})
        if _STATUS.search(clean):
            out["status"].append({"line": ln, "text": txt.strip()[:160]})
        if _CITATION.search(clean):
            out["citations"].append({"line": ln, "text": txt.strip()[:160]})
    return out


def scan_text(text: str, rel: str, only_lines: set[int] | None = None, ctx: Context | None = None) -> dict:
    """Informe de `scan` para un `.md`: cifras (con cobertura), marcas (con validez), estructura."""
    ctx = ctx or default_context()
    an = analyze(text, rel, ctx)
    uncovered = {id(f) for f in an.uncovered()}
    keep = (lambda ln: True) if only_lines is None else (lambda ln: ln in only_lines)
    figs = [dict(asdict(f), covered=id(f) not in uncovered) for f in an.figures if keep(f.line)]
    marks, notices = [], list(an.notices)
    for mk in an.marks:
        if not keep(mk.line):
            continue
        errs = validate_mark(mk, ctx, an.covered_figures(mk), notices)
        resolved = []
        for item in mk.items:
            if _CODE_REF_TEXT.match(item.strip().strip("`")):
                r = resolve_code_ref(item, ctx.root)
                resolved.append({"ref": item, "exists": r.exists, "value": r.value, "unit": r.unit})
        marks.append({"line": mk.line, "label": mk.label, "raw": mk.raw, "scope": mk.scope,
                      "errors": errs, "code_refs": resolved})
    body_lines = [(k, ln) for k, ln in enumerate(strip_code_fences(text).splitlines(), start=1) if keep(k)]
    rep = {"path": rel, "kind": "md", "figures": figs, "marks": marks, "notices": notices}
    rep.update(_scan_lines(body_lines, "md"))
    return rep


def scan_code(src: str, rel: str, only_lines: set[int] | None = None, ctx: Context | None = None) -> dict:
    """Informe de `scan --code` para el fuente de un `.py`: comentarios, docstrings y textos de la GUI."""
    ctx = ctx or default_context()
    keep = (lambda ln: True) if only_lines is None else (lambda ln: ln in only_lines)
    texts = [(ln, kind, txt) for ln, kind, txt in extract_code_text(src=src) if keep(ln)]
    figs, marks = [], []
    for ln, kind, txt in texts:
        for f in iter_figures(txt, exempt_wavelengths=ctx.exempt_wavelengths):
            d = asdict(f)
            d.update(line=ln, text_kind=kind)
            figs.append(d)
        for start, end, label_written, content, closed, syntax in _scan_marks_in_line(txt):
            mk = Mark(ln, label_written.lower(), _split_items(content) if content else [],
                      "inline" if closed else "unclosed", txt[start:end], start, content, False,
                      label_written, syntax)
            covered = list(iter_figures(txt, exempt_wavelengths=ctx.exempt_wavelengths))
            marks.append({"line": ln, "label": mk.label, "raw": mk.raw, "scope": mk.scope,
                          "errors": validate_mark(mk, ctx, covered), "text_kind": kind})
    rep = {"path": rel, "kind": "py", "figures": figs, "marks": marks, "notices": [],
           "texts": [{"line": ln, "kind": kind, "text": txt[:160]} for ln, kind, txt in texts
                     if _STRUCTURAL.search(txt) or _FIGURE.search(txt.replace("μ", "µ"))]}
    rep.update(_scan_lines(((ln, txt) for ln, _, txt in texts), "py"))
    return rep


def _triage(reports: list[dict]) -> dict:
    t = {"figures": 0, "uncovered": 0, "citations": 0, "structural": 0, "status": 0, "invalid_marks": 0}
    for r in reports:
        t["figures"] += sum(1 for f in r["figures"] if not f.get("exempt"))
        t["uncovered"] += sum(1 for f in r["figures"] if not f.get("exempt") and not f.get("covered", False))
        t["citations"] += len(r["citations"])
        t["structural"] += len(r["structural"])
        t["status"] += len(r["status"])
        t["invalid_marks"] += sum(1 for m in r["marks"] if m["errors"])
    t["verify"] = bool(t["figures"] or t["citations"] or t["structural"] or t["status"])
    return t


def _print_scan(reports: list[dict], triage: dict) -> None:
    for r in reports:
        n_fig = sum(1 for f in r["figures"] if not f.get("exempt"))
        print(f"== {r['path']} ({n_fig} cifras, {len(r['marks'])} marcas)")
        for f in r["figures"]:
            if f.get("exempt"):
                continue
            where = "LaTeX" if f["in_latex"] else ("tabla" if f["in_table"] else "texto")
            state = "cubierta" if f.get("covered") else "SIN MARCA"
            if r["kind"] == "py":
                state = f.get("text_kind", "")
            print(f"  l. {f['line']:>4}  cifra        {f['raw']!r} ({where})  {state}")
        for m in r["marks"]:
            state = "válida" if not m["errors"] else "INVÁLIDA: " + "; ".join(m["errors"])
            print(f"  l. {m['line']:>4}  marca        {m['raw']}  {state}")
            for c in m.get("code_refs", []):
                print(f"            símbolo      {c['ref']} -> existe={c['exists']} valor={c['value']} unidad={c['unit']}")
        for key, title in (("structural", "estructural"), ("status", "estado"), ("citations", "cita")):
            for e in r[key]:
                print(f"  l. {e['line']:>4}  {title:<12} {e['text'][:110]}")
        for nt in r.get("notices", []):
            print(f"  aviso: {nt}")
    print(f"Triage: cifras={triage['figures']} (sin marca {triage['uncovered']}), citas={triage['citations']}, "
          f"estructurales={triage['structural']}, estado={triage['status']}, marcas inválidas={triage['invalid_marks']}"
          f" -> verificación con provenance-verifier: {'sí' if triage['verify'] else 'no hace falta'}")


def _cmd_scan(args) -> int:
    reports = []
    targets: list[tuple[str, str | None, set | None]] = []   # (rel, contenido o None, líneas)
    if args.cached or args.diff:
        diff_args = ["--cached"] if args.cached else [args.diff]
        changed = _changed_lines(diff_args + (["--"] + args.paths if args.paths else []))
        for rel, lines in sorted(changed.items()):
            if not _in_scan_scope(rel, args.code) or not lines:
                continue
            if args.cached:
                content = _git("show", f":{rel}")
            elif ".." in args.diff:
                rev = args.diff.split("..")[-1].lstrip(".") or "HEAD"
                content = _git("show", f"{rev}:{rel}")
            else:
                p = ROOT / rel
                content = _read(p) if p.is_file() else None
            if content is not None:
                targets.append((rel, content, lines))
    else:
        if not args.paths:
            print("scan: indicá rutas, --cached o --diff <rango>", file=sys.stderr)
            return 2
        for raw in args.paths:
            p = Path(raw)
            p = p if p.is_absolute() else (Path.cwd() / p)
            files = [p] if p.is_file() else sorted(q for q in p.rglob("*") if q.suffix in (".md", ".py")) if p.is_dir() else []
            if not files:
                print(f"scan: no existe {raw}", file=sys.stderr)
                return 2
            for f in files:
                if in_foreign_tree(f):
                    continue
                rel = f.resolve().relative_to(ROOT).as_posix() if f.resolve().is_relative_to(ROOT) else str(f)
                if f.suffix == ".py" and not args.code:
                    continue
                targets.append((rel, None, None))
    for rel, content, lines in targets:
        text = content if content is not None else _read(Path(rel) if Path(rel).is_absolute() else ROOT / rel)
        reports.append(scan_code(text, rel, lines) if rel.endswith(".py") else scan_text(text, rel, lines))
    triage = _triage(reports)
    if args.json:
        print(json.dumps({"files": reports, "triage": triage}, ensure_ascii=False, indent=1, default=str))
    else:
        _print_scan(reports, triage)
    if triage["invalid_marks"]:
        return 1
    if args.strict and triage["uncovered"]:
        return 1
    return 0


def _cmd_bib(args) -> int:
    if not BIB_INDEX_DIR.is_dir():
        print("bib: falta el índice por página; corré primero: python tools/source_marks.py index-bib", file=sys.stderr)
        return 2
    hits = bib_search(args.pattern, [args.key] if args.key else None)
    for key, page, line in hits[: args.max]:
        print(f"{key} p. {page}: {line[:200]}")
    if len(hits) > args.max:
        print(f"… {len(hits) - args.max} coincidencias más (--max)")
    if not hits:
        print("sin coincidencias")
    return 0


def _cmd_check_report(args) -> int:
    if args.report == "-":
        text = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    else:
        text = _read(Path(args.report))
    errors = check_report_text(text)
    if errors:
        print(f"check-report: {len(errors)} problema(s)")
        for e in errors:
            print("  " + e)
        return 1
    print("check-report: todas las filas resuelven (claves, páginas, citas, símbolos y puntos)")
    return 0


def _cmd_index_bib(args) -> int:
    try:
        counts = index_bib(force=args.force)
    except RuntimeError as exc:
        print(f"index-bib: {exc}", file=sys.stderr)
        return 2
    for key, pages in sorted(counts.items()):
        print(f"{key}: {pages} páginas")
    if args.update_counts:
        payload = {"_nota": "Páginas físicas de cada PDF de lab-invariants §9. Lo genera "
                            "`python tools/source_marks.py index-bib --update-counts`; lo lee el gate "
                            "(tests/test_source_marks.py), que no depende de pdftotext.",
                   "pages": dict(sorted(counts.items()))}
        PAGE_COUNTS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"escrito {PAGE_COUNTS_FILE.relative_to(ROOT).as_posix()}")
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # consolas de Windows
    except (AttributeError, ValueError):
        pass
    parser = argparse.ArgumentParser(prog="source_marks.py", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd")
    p = sub.add_parser("scan", help="cifras, marcas y afirmaciones estructurales de un diff o de documentos")
    p.add_argument("paths", nargs="*")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--cached", action="store_true", help="el índice de git (git diff --cached)")
    g.add_argument("--diff", metavar="RANGO", help="un rango de git (A..B) o una revisión contra el árbol de trabajo")
    p.add_argument("--code", action="store_true", help="incluye comentarios, docstrings y textos de UI de los .py")
    p.add_argument("--json", action="store_true")
    p.add_argument("--strict", action="store_true", help="sale con 1 si hay cifras sin marca")
    p.set_defaults(func=_cmd_scan)
    p = sub.add_parser("bib", help="busca una regex en el índice por página de la bibliografía")
    p.add_argument("pattern")
    p.add_argument("--key")
    p.add_argument("--max", type=int, default=40)
    p.set_defaults(func=_cmd_bib)
    p = sub.add_parser("check-report", help="valida claves, páginas, citas y símbolos de un informe")
    p.add_argument("report", help="ruta del informe, o - para leerlo de stdin")
    p.set_defaults(func=_cmd_check_report)
    p = sub.add_parser("index-bib", help="reconstruye scratch/bib_index/ con pdftotext")
    p.add_argument("--update-counts", action="store_true", help="regenera tools/bib_page_counts.json (mantenimiento)")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=_cmd_index_bib)
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 2
    try:
        return args.func(args)
    except RuntimeError as exc:
        print(f"{args.cmd}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
