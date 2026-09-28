# -*- coding: utf-8 -*-
"""
test_prompt_corpus_integrity.py — Quality gate for the agent/skill prompt corpus.

PyPrinting 3.0 — UNSAM Nanofotónica

MOTIVACIÓN (auditoría de prompts, 2026-09-26)
---------------------------------------------
El corpus de prompts (`CLAUDE.md`, `.claude/agents/*.md`, `.claude/skills/*/SKILL.md`) se
escribió el 2026-09-21 y desde entonces shippearon varias fases de implementación. Una
auditoría encontró que NADA verificaba lo que los prompts afirman contra el código real, y
como consecuencia el corpus acumuló afirmaciones falsas sobre hardware:

  * el watchdog de obturadores se documentaba como "500 ms" en 4 archivos, cuando
    `core/nidaq.py` tiene un deadline de 30 s con poll de 100 ms (nunca hubo un 500 ms);
  * el botón de pánico se documentaba en `Escape`/`Space`, cuando está en `Ctrl+E`/`F12`
    — y `Ctrl+Space` es Toggle Live View, o sea la tecla documentada como pánico hacía
    otra cosa;
  * `core/nidaq_base.py` y `analysis/lattice_disorder.py` se citaban como rutas reales y
    no existen.

Un prompt con un número de seguridad equivocado es un riesgo de laboratorio, no una errata:
un agente que presupueste un lazo de adquisición contra 500 ms calcula mal los márgenes de
heartbeat en ambas direcciones. Este módulo convierte esa clase de defecto de "se descubre
por suerte en una auditoría" a "lo agarra `pytest tests/`".

Cubre:
1. Toda temporización de watchdog citada en el corpus coincide con `core/nidaq.py`.
2. Todo atajo de parada de emergencia citado coincide con `pyspectrum/window.py`.
3. Toda ruta de código citada entre backticks existe en el repositorio.
4. Toda referencia `CAT-xxx` / `SYS-xxx` / `MOD-xx` resuelve a un monográfico real
   (regla que `qa-ux-auditor.md` §2C exige y que hasta ahora nada verificaba).
5. Toda referencia `DEC-xxx` resuelve a una sección del ledger único `DECISION_LOG.md`.
6. Los registros de agentes/skills de `CLAUDE.md` §6/§7 coinciden con los archivos reales.
7. Frontmatter válido y coherente con el nombre de archivo/directorio.
8. No reaparece el vocabulario del protocolo de 2 rondas ya superado.

ALCANCE: sólo la superficie de instrucción VIVA — `CLAUDE.md` y `.claude/**`, es decir lo
que un agente carga efectivamente en contexto. Los monográficos (`reportes/`) y el ledger
(`docs/decisions/DECISION_LOG.md`) quedan deliberadamente fuera: un ledger de decisiones
*debe* preservar valores superados como registro histórico. `DEC-002` (2026-08-20) decidió
genuinamente 500 ms y `DEC-010` (2026-09-17) lo reemplazó por 30 s/100 ms; la causa raíz del
defecto no fue que DEC-002 exista, sino que su fila no estaba anotada como superada y los
prompts la copiaron como si fuera vigente. Esa anotación ya se aplicó; lo que este gate
impide es que el dato viejo vuelva a filtrarse a la superficie de instrucción.

Este módulo es deliberadamente hermético: NO importa PyQt6, nidaqmx ni `core.nidaq`. Lee
`core/nidaq.py` como texto para no arrancar el hilo watchdog ni requerir el stack de
hardware, de modo que el gate corra rápido y en cualquier plataforma.

Los helpers de lectura (árboles ajenos, bloques de código, resolvers de símbolos) viven en
`tools/source_marks.py` y se importan de ahí (`DEC-038`): el gate de marcas de fuente
(`tests/test_source_marks.py`) usa los mismos, y dos copias que divergen serían el mismo defecto
que este módulo existe para atajar. Ese módulo es sólo biblioteca estándar, así que el gate sigue
siendo hermético.
"""
import functools
import importlib.util
import os
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_source_marks():
    """Carga `tools/source_marks.py` por ruta: un paquete `tools` instalado en site-packages le
    ganaría al del repositorio si se importara por nombre."""
    name = "pyprinting_tools_source_marks"
    module = sys.modules.get(name)
    if module is None:
        spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / "source_marks.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return module


_sm = _load_source_marks()


# ==============================================================================
# Recolección del corpus
# ==============================================================================
# Árboles que viven dentro del directorio pero NO son este repositorio: otros checkouts (los
# worktrees de git que Claude Code crea bajo .claude/worktrees/, cada uno una copia completa del
# repo en otra rama), el entorno virtual y la base de git. Recorrerlos es incorrecto, no sólo
# lento: una copia del repo trae sus propios CLAUDE.md, ledgers y reserva/ bajo rutas que las
# exclusiones de este módulo no reconocen (falsos positivos), y una ruta citada podría "resolver"
# contra un archivo que existe sólo en otra rama (falso negativo).
_FOREIGN_TREES = _sm.FOREIGN_TREES


def _in_foreign_tree(path: Path) -> bool:
    return _sm.in_foreign_tree(path, ROOT)


def _corpus_files():
    """CLAUDE.md + todo prompt bajo .claude/ (agentes, skills, exemplars)."""
    files = [ROOT / "CLAUDE.md"]
    files.extend(f for f in sorted((ROOT / ".claude").glob("**/*.md")) if not _in_foreign_tree(f))
    return [f for f in files if f.is_file()]


@functools.lru_cache(maxsize=1)
def _repo_entry_names():
    """Nombres de archivos y directorios del repositorio, sin entrar en árboles ajenos."""
    names = set()
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if not _in_foreign_tree(Path(dirpath) / d)]
        names.update(dirnames)
        names.update(filenames)
    return frozenset(names)


CORPUS = _corpus_files()

# Marcadores de plantilla: un token que los contenga es un placeholder documental
# (`CAT-XXX.md`, `path/to/module.py`, `.claude/skills/*/SKILL.md`), no una ruta real.
_PLACEHOLDER_MARKS = ("*", "<", ">", "{", "}", "path/to", "XX", "xx", "[", "]")


def _strip_code_fences(text: str) -> str:
    """Los bloques de código contienen plantillas y pseudocódigo ilustrativo. Se vacían
    conservando las líneas, para que cada `archivo:línea` informado sea el real (D4)."""
    return _sm.strip_code_fences(text)


def _label(path: Path) -> str:
    """Ruta relativa a la raíz para los mensajes; absoluta si el archivo es sintético."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def test_strip_code_fences_preserves_line_numbers():
    """D4: el texto posterior a un bloque de código conserva su número de línea.

    Control negativo: la versión anterior del gate (reproducida acá) borraba el bloque con sus
    saltos de línea, y la cifra de la línea 6 aparecía en la 3.
    """
    text = "a\n```python\nx = 1\ny = 2\n```\nb 500 ms\n"
    out = _strip_code_fences(text).splitlines()
    assert len(out) == len(text.splitlines())
    assert out[5] == "b 500 ms"

    def _old_strip(t):
        t = re.sub(r"````.*?````", "", t, flags=re.DOTALL)
        return re.sub(r"```.*?```", "", t, flags=re.DOTALL)

    assert _old_strip(text).splitlines().index("b 500 ms") != 5, (
        "el control negativo dejó de reproducir el defecto D4: revisá este test"
    )


def test_corpus_is_discoverable():
    """Sanity: el corpus existe y tiene el tamaño esperado."""
    assert (ROOT / "CLAUDE.md").is_file(), "Falta la constitución CLAUDE.md"
    agents = sorted((ROOT / ".claude" / "agents").glob("*.md"))
    skills = sorted((ROOT / ".claude" / "skills").glob("*/SKILL.md"))
    assert len(agents) >= 10, f"Se esperaban >=10 subagentes, se hallaron {len(agents)}"
    assert len(skills) >= 10, f"Se esperaban >=10 skills, se hallaron {len(skills)}"
    assert len(CORPUS) >= 20, f"Corpus demasiado chico: {len(CORPUS)} archivos"


# ==============================================================================
# 1. Temporización del watchdog — el corpus debe citar los valores del código
# ==============================================================================
def _watchdog_ground_truth():
    """Extrae (deadline_s, poll_s) de core/nidaq.py SIN importarlo.

    Importar `core.nidaq` arranca el hilo `ShutterWatchdog` a nivel de módulo; un test de
    integridad documental no debe tener ese efecto colateral. Si el parseo falla, el test
    falla ruidosamente en vez de pasar en silencio: eso significa que `core/nidaq.py` se
    refactorizó y este gate necesita actualizarse junto con él.
    """
    src = (ROOT / "core" / "nidaq.py").read_text(encoding="utf-8", errors="ignore")

    m_deadline = re.search(r"_default_timeout_s\s*:[^=]*=\s*([0-9]+(?:\.[0-9]+)?)", src)
    assert m_deadline, (
        "No se pudo leer `_default_timeout_s` de core/nidaq.py. Si el watchdog se "
        "refactorizó, actualizá _watchdog_ground_truth() en este test."
    )

    m_poll = re.search(
        r"def _watchdog_loop\(\).*?time\.sleep\(\s*([0-9]*\.?[0-9]+)\s*\)",
        src,
        flags=re.DOTALL,
    )
    assert m_poll, (
        "No se pudo leer el intervalo de poll dentro de `_watchdog_loop()` en "
        "core/nidaq.py. Actualizá _watchdog_ground_truth() si cambió la estructura."
    )

    return float(m_deadline.group(1)), float(m_poll.group(1))


def test_watchdog_ground_truth_is_parseable():
    deadline_s, poll_s = _watchdog_ground_truth()
    assert deadline_s > 0 and poll_s > 0
    # Invariante física: el poll debe ser mucho más rápido que el deadline, o el
    # fail-safe llegaría tarde.
    assert poll_s < deadline_s / 10.0


def _watchdog_offenders(paths, deadline_s: float, poll_s: float) -> list:
    """Temporizaciones de watchdog/heartbeat/deadline que no coinciden con el código.

    Cada línea pasa antes por el normalizador de LaTeX (`tools/source_marks.py::latex_to_plain`):
    la fase 2 de la auditoría del 2026-09-27 comprobó que `$500\\ \\text{ms}$`,
    `$\\tau_{wd} = 500\\,\\mathrm{ms}$` y una celda `$500~\\text{ms}$` pasaban sin ser vistas.
    """
    allowed_s = {deadline_s, poll_s}

    # El corpus necesita poder citar un valor histórico EQUIVOCADO para documentar su
    # corrección ("el watchdog no es de 500 ms", la anotación SUPERSEDED de DEC-002). Una
    # línea que niega o historiza el número es contenido correcto, no una afirmación falsa;
    # marcarla sería el mismo falso positivo que se corrigió en el guard de atajos de pánico.
    negating = _sm.NEGATING

    # Captura "500 ms heartbeat", "30 s deadline", "watchdog de 30s", "100 ms poll"...
    pattern = re.compile(
        r"(?:(\d+(?:[.,]\d+)?)\s*(ms|s)\b[^.\n]{0,40}?(?:heartbeat|watchdog|deadline)"
        r"|(?:heartbeat|watchdog|deadline)[^.\n]{0,40}?(\d+(?:[.,]\d+)?)\s*(ms|s)\b)",
        re.IGNORECASE,
    )

    offenders = []
    for path in paths:
        body = _strip_code_fences(path.read_text(encoding="utf-8", errors="ignore"))
        for lineno, raw_line in enumerate(body.splitlines(), start=1):
            line = _sm.latex_to_plain(raw_line)
            # El énfasis markdown rompe los límites de palabra ("**no** es" no contiene
            # "no es"), así que la detección de negación corre sobre la línea despojada de
            # `*`, `_` y backticks. Detectado por control negativo: sin esto, una negación
            # legítima sólo se libraba si además contenía otra palabra de la lista.
            if negating.search(re.sub(r"[*_`]", "", line)):
                continue
            for match in pattern.finditer(line):
                value = match.group(1) or match.group(3)
                unit = match.group(2) or match.group(4)
                seconds = float(value.replace(",", ".")) / (1000.0 if unit.lower() == "ms" else 1.0)
                if not any(abs(seconds - ok) < 1e-9 for ok in allowed_s):
                    offenders.append(
                        f"{_label(path)}:{lineno}: cita {value} {unit} "
                        f"({seconds} s) — core/nidaq.py tiene deadline={deadline_s}s, "
                        f"poll={poll_s}s :: {raw_line.strip()[:110]}"
                    )
    return offenders


def test_corpus_watchdog_timings_match_code():
    """Ninguna temporización de watchdog/heartbeat en el corpus contradice al código.

    Guarda contra la regresión concreta que motivó este módulo: "500 ms heartbeat
    watchdog" citado en 4 archivos contra un deadline real de 30 s / poll de 100 ms.
    """
    deadline_s, poll_s = _watchdog_ground_truth()
    offenders = _watchdog_offenders(CORPUS, deadline_s, poll_s)
    assert not offenders, (
        "Temporización de watchdog en los prompts que no coincide con core/nidaq.py:\n  "
        + "\n  ".join(offenders)
    )


@pytest.mark.parametrize("line", [
    "El watchdog corta a los 500 ms.",
    r"El watchdog corta a los $500\ \text{ms}$.",
    r"El watchdog, con $\tau_{wd} = 500\,\mathrm{ms}$, cierra el obturador.",
    r"| watchdog | $500~\text{ms}$ |",
], ids=["plano", "latex-text", "latex-mathrm", "latex-tilde-celda"])
def test_watchdog_check_catches_wrong_timings_in_latex(tmp_path, line):
    """Control negativo del test del watchdog: el mismo valor falso, en texto plano y en las tres
    formas de LaTeX que la fase 2 encontró sin detectar, tiene que marcarse."""
    synthetic = tmp_path / "sintetico.md"
    synthetic.write_text("# Sintético\n\n" + line + "\n", encoding="utf-8")
    assert _watchdog_offenders([synthetic], 30.0, 0.1), f"no se detectó: {line}"


@pytest.mark.parametrize("line", [
    r"El deadline del watchdog es de $30\ \text{s}$.",
    r"El poll del watchdog es de $100\,\mathrm{ms}$.",
    r"El watchdog **no** es de $500\ \text{ms}$ (DEC-002, superada).",
], ids=["deadline-correcto", "poll-correcto", "negacion"])
def test_watchdog_check_accepts_correct_or_negated_latex(tmp_path, line):
    """Control positivo: normalizar el LaTeX no tiene que convertir un valor correcto, ni una
    negación documentada, en un falso positivo."""
    synthetic = tmp_path / "sintetico.md"
    synthetic.write_text("# Sintético\n\n" + line + "\n", encoding="utf-8")
    assert not _watchdog_offenders([synthetic], 30.0, 0.1)


# ==============================================================================
# 2. Atajos de parada de emergencia
# ==============================================================================
def test_corpus_estop_shortcuts_match_window():
    """Todo atajo citado como parada de emergencia debe estar realmente bindeado a ella.

    Guarda contra la regresión de `Escape`/`Space`: `Ctrl+Space` existe, pero está
    bindeado a Toggle Live View — documentarlo como tecla de pánico es un riesgo real de
    laboratorio, no una errata de documentación.
    """
    window_src = (ROOT / "pyspectrum" / "window.py").read_text(encoding="utf-8", errors="ignore")

    estop_keys = set()
    for m in re.finditer(
        r'QKeySequence\(\s*"([^"]+)"\s*\)\s*,\s*self\s*\)\s*\n\s*self\.\w+\.activated'
        r'\.connect\(\s*self\.(\w+)\s*\)',
        window_src,
    ):
        if "emergency" in m.group(2).lower() or "estop" in m.group(2).lower():
            estop_keys.add(m.group(1).lower())

    assert estop_keys, (
        "No se detectó ningún atajo de parada de emergencia en pyspectrum/window.py. "
        "Si `_setup_shortcuts()` se refactorizó, actualizá este test."
    )

    # Solo se examinan atajos en POSICIÓN DE AFIRMACIÓN, es decir los que siguen a un verbo
    # de binding ("mapped to `Escape`/`Space`" era la forma exacta del bug original). Una
    # advertencia explícita en contra de una tecla — "`Ctrl+Space` is Toggle Live View,
    # never document it as a panic key" — es contenido correcto y no debe marcarse.
    binding = re.compile(
        r"(?:bound to|mapped to|bindeado a|asignado a|assigned to)(?P<clause>[^.;—\n]*)",
        re.IGNORECASE,
    )
    shortcut = re.compile(
        r"`((?:(?:Ctrl|Alt|Shift|Meta)\+)*(?:F\d{1,2}|Space|Escape|Esc|Enter|Return|[A-Z0-9]))`",
        re.IGNORECASE,
    )

    offenders = []
    for path in CORPUS:
        body = _strip_code_fences(path.read_text(encoding="utf-8", errors="ignore"))
        for lineno, line in enumerate(body.splitlines(), start=1):
            low = line.lower()
            # Solo líneas que hablen de pánico / parada de emergencia.
            if not any(k in low for k in ("panic", "pánico", "emergency", "e-stop", "estop")):
                continue
            for b in binding.finditer(line):
                for m in shortcut.finditer(b.group("clause")):
                    token = m.group(1).strip()
                    if token.lower() not in estop_keys:
                        offenders.append(
                            f"{path.relative_to(ROOT)}:{lineno}: presenta `{token}` como "
                            f"atajo de pánico; los reales son {sorted(estop_keys)} "
                            f":: {line.strip()[:110]}"
                        )

    assert not offenders, (
        "Atajos de parada de emergencia mal documentados:\n  " + "\n  ".join(offenders)
    )


# ==============================================================================
# 3. Rutas de código citadas
# ==============================================================================
_PATHY = re.compile(r"`([A-Za-z0-9_][A-Za-z0-9_./\\-]*\.(?:py|md|json|txt|tiff|tif|ps1|yaml|yml))(?:::[A-Za-z0-9_.]+)?`")


def _resolves(token: str, containing: Path) -> bool:
    """Resuelve un token de ruta con tres estrategias, como lo haría un lector humano."""
    token = token.replace("\\", "/")
    # (a) relativa a la raíz del repo
    if (ROOT / token).exists():
        return True
    # (b) relativa al archivo que la cita (p.ej. `exemplars/..._gold.md` dentro de agents/)
    if (containing.parent / token).exists():
        return True
    # (c) por nombre de archivo en cualquier parte del repo (referencias abreviadas
    #     como `lattice_disorder_gui.py` o `instrumentation.md`)
    return Path(token).name in _repo_entry_names()


def test_cited_code_paths_exist():
    """Toda ruta entre backticks en el corpus resuelve a un archivo real."""
    offenders = []
    for path in CORPUS:
        body = _strip_code_fences(path.read_text(encoding="utf-8", errors="ignore"))
        for lineno, line in enumerate(body.splitlines(), start=1):
            for m in _PATHY.finditer(line):
                token = m.group(1)
                if any(mark in token for mark in _PLACEHOLDER_MARKS):
                    continue
                if not _resolves(token, path):
                    offenders.append(f"{path.relative_to(ROOT)}:{lineno}: `{token}`")

    assert not offenders, (
        "Rutas citadas en los prompts que no existen en el repositorio:\n  "
        + "\n  ".join(offenders)
    )


# ==============================================================================
# 4-5. Referencias cruzadas a monográficos y al ledger de decisiones
# ==============================================================================
def _existing_monograph_ids():
    ids = set()
    for pattern, prefix in (
        ("reportes/cientificos/*.md", "CAT"),
        ("reportes/sistema/*.md", "SYS"),
        ("docs/modulos/*.md", "MOD"),
    ):
        for f in ROOT.glob(pattern):
            m = re.match(rf"({prefix}-\d+)", f.name)
            if m:
                ids.add(m.group(1).upper())
    return ids


def test_monograph_cross_references_resolve():
    """`qa-ux-auditor.md` §2C exige cero referencias cruzadas rotas — acá se verifica."""
    existing = _existing_monograph_ids()
    assert existing, "No se halló ningún monográfico CAT/SYS/MOD; ¿cambió el layout?"

    ref = re.compile(r"\b((?:CAT|SYS|MOD)-\d{2,3})\b")
    offenders = []
    for path in CORPUS:
        body = _strip_code_fences(path.read_text(encoding="utf-8", errors="ignore"))
        for lineno, line in enumerate(body.splitlines(), start=1):
            for m in ref.finditer(line):
                token = m.group(1).upper()
                if token not in existing:
                    offenders.append(f"{path.relative_to(ROOT)}:{lineno}: {token}")

    assert not offenders, (
        "Referencias a monográficos inexistentes:\n  " + "\n  ".join(offenders)
    )


def test_decision_references_resolve_in_single_ledger():
    """Toda `DEC-xxx` citada existe como sección del ledger único DECISION_LOG.md.

    El ledger es un solo archivo append-only; nunca un `DEC-xxx_Titulo.md` por decisión.
    """
    ledger = ROOT / "docs" / "decisions" / "DECISION_LOG.md"
    assert ledger.is_file(), "Falta docs/decisions/DECISION_LOG.md"
    logged = set(re.findall(r"\b(DEC-\d+)\b", ledger.read_text(encoding="utf-8", errors="ignore")))
    assert logged, "DECISION_LOG.md no contiene ninguna entrada DEC-xxx"

    offenders = []
    for path in CORPUS:
        body = _strip_code_fences(path.read_text(encoding="utf-8", errors="ignore"))
        for lineno, line in enumerate(body.splitlines(), start=1):
            for m in re.finditer(r"\b(DEC-\d+)\b", line):
                if m.group(1) not in logged:
                    offenders.append(f"{path.relative_to(ROOT)}:{lineno}: {m.group(1)}")

    assert not offenders, (
        "Decisiones citadas que no están en DECISION_LOG.md:\n  " + "\n  ".join(offenders)
    )


def test_no_per_decision_files_referenced():
    """Guarda la convención de ledger único (regresión de knowledge-integrator)."""
    bad = re.compile(r"DEC-\d+_[A-Za-z0-9_]+\.md")
    offenders = []
    for path in CORPUS:
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1
        ):
            if bad.search(line):
                offenders.append(f"{path.relative_to(ROOT)}:{lineno}: {line.strip()[:110]}")
    assert not offenders, (
        "Se referencia un archivo por decisión; el ledger es único "
        "(docs/decisions/DECISION_LOG.md):\n  " + "\n  ".join(offenders)
    )


# ==============================================================================
# 6. Sincronía de los registros de CLAUDE.md §6 / §7
# ==============================================================================
def _claude_section(title_prefix: str, next_prefix: str) -> str:
    text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8", errors="ignore")
    start = text.find(title_prefix)
    assert start != -1, f"No se halló la sección '{title_prefix}' en CLAUDE.md"
    end = text.find(next_prefix, start)
    return text[start : end if end != -1 else len(text)]


def test_claude_md_agent_registry_matches_files():
    """CLAUDE.md §6 no debe quedar desfasada al agregar/renombrar un subagente."""
    on_disk = {f.stem for f in (ROOT / ".claude" / "agents").glob("*.md")}
    section = _claude_section("## 6. Subagent Dispatch Matrix", "## 7.")
    listed = {t for t in re.findall(r"`([a-z0-9-]+)`", section)} & (on_disk | {"x"})

    missing = on_disk - listed
    assert not missing, (
        f"Subagentes existentes ausentes de la matriz de despacho de CLAUDE.md §6: "
        f"{sorted(missing)}"
    )


def test_claude_md_skill_registry_matches_files():
    """CLAUDE.md §7 no debe quedar desfasada al agregar/renombrar un skill."""
    on_disk = {p.parent.name for p in (ROOT / ".claude" / "skills").glob("*/SKILL.md")}
    section = _claude_section("## 7. Procedural Skills Directory", "## 8.")
    listed = {t for t in re.findall(r"`([a-z0-9-]+)`", section)}

    missing = on_disk - listed
    assert not missing, (
        f"Skills existentes ausentes del directorio de CLAUDE.md §7: {sorted(missing)}"
    )


# ==============================================================================
# 7. Frontmatter
# ==============================================================================
def _frontmatter_name(path: Path):
    text = path.read_text(encoding="utf-8", errors="ignore")
    if not text.startswith("---"):
        return None, None
    block = text.split("---", 2)[1]
    name = re.search(r"^name:\s*(.+)$", block, re.MULTILINE)
    desc = re.search(r"^description:\s*(.+)$", block, re.MULTILINE)
    return (name.group(1).strip() if name else None, desc.group(1).strip() if desc else None)


@pytest.mark.parametrize(
    "path", sorted((ROOT / ".claude" / "agents").glob("*.md")), ids=lambda p: p.stem
)
def test_agent_frontmatter_is_valid(path):
    name, desc = _frontmatter_name(path)
    assert name, f"{path.name}: falta `name:` en el frontmatter YAML"
    assert desc, f"{path.name}: falta `description:` (es el texto de ruteo del agente)"
    assert name == path.stem, f"{path.name}: name '{name}' != nombre de archivo '{path.stem}'"


_INVARIANTS_FILE = ROOT / ".claude" / "shared" / "lab-invariants.md"
_CODE_REF = re.compile(r"`([\w/.\-]+\.py)::(\w+)`")
# Entrada de un diccionario de módulo: `ruta.py::SIMBOLO["clave"]["campo"]` (p. ej. la NA de un
# objetivo en `MICROSCOPE_OBJECTIVES`, cuyas claves llevan espacios y paréntesis).
_CODE_SUBSCRIPT_REF = re.compile(r'`([\w/.\-]+\.py)::(\w+)((?:\["[^"\]]+"\])+)`')
_NUMBER_TOKEN = re.compile(r"`[−-]?([0-9]+(?:\.[0-9]+)?)`")
_BACKTICK_TOKEN = re.compile(r"`([^`]+)`")


def _resolve_code_number(rel_path: str, symbol: str):
    """`ruta.py::SIMBOLO` a un número, leyendo el fuente sin importar el módulo.

    Se lee como texto (AST) en vez de importar por la misma razón que en
    `_watchdog_ground_truth()`: importar `core.nidaq` arranca el hilo `ShutterWatchdog` a nivel de
    módulo. Dos formas: una asignación de módulo a un literal numérico y, si el símbolo es una
    función, el primer `time.sleep(<literal>)` de **su** cuerpo. Devuelve `None` si no resuelve, y
    el llamador lo trata como fallo explícito. Implementación en `tools/source_marks.py`.
    """
    return _sm.resolve_code_number(rel_path, symbol, ROOT)


def _resolve_code_string(rel_path: str, symbol: str):
    """`ruta.py::SIMBOLO` a una cadena, si el símbolo es una asignación de módulo a un literal de
    texto (`FLIPPER_AO_UP = "Dev1/ao0"`). Devuelve `None` si no es una cadena, para que el
    llamador pruebe la vía numérica. Implementación en `tools/source_marks.py`."""
    return _sm.resolve_code_string(rel_path, symbol, ROOT)


def _resolve_code_subscript(rel_path: str, symbol: str, keys):
    """`ruta.py::SIMBOLO["k1"]["k2"]` al literal numérico de ese diccionario de módulo, o `None`
    si alguna clave falta o el valor final no es un número. Implementación en
    `tools/source_marks.py`."""
    return _sm.resolve_code_subscript(rel_path, symbol, keys, ROOT)


def _table_value_cell(line: str) -> str:
    """Segunda celda de una fila de tabla markdown: la columna Valor de lab-invariants."""
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    return cells[1] if len(cells) > 1 else ""


def test_lab_invariants_file_exists():
    """`.claude/shared/lab-invariants.md` es la fuente única de los valores de hardware."""
    assert _INVARIANTS_FILE.is_file(), (
        "Falta .claude/shared/lab-invariants.md, la tabla canónica de valores volátiles "
        "citados por los prompts (DEC-028). Si se movió, actualizá este test y CLAUDE.md §2."
    )


def test_lab_invariants_match_code():
    """Cada fila ✅ de lab-invariants.md coincide con el símbolo real del código.

    Esto es lo que vuelve confiable a la tabla: sin verificación mecánica, una hoja de
    "fuente única de verdad" es sólo un cuarto lugar donde el mismo número puede estar mal.
    Si alguien cambia `PI_STAGE_RANGE_UM` o `_default_timeout_s` y no actualiza la tabla, el
    suite falla y nombra la fila.

    Se verifican las filas ✅ que tengan una referencia de código, con la primera que aparezca:
    * `ruta.py::SIMBOLO` asignado a una **cadena**: se compara con el primer valor entre
      backticks de la columna Valor (p. ej. `Dev1/ao0` contra `config.FLIPPER_AO_UP`);
    * `ruta.py::SIMBOLO` numérico, o `ruta.py::SIMBOLO["clave"]["campo"]` de un diccionario:
      se compara con el primer número entre backticks de la fila.
    Las filas ✅ sin valor verificable (atajos de teclado, rutas de ledger, líneas de
    obturadores) las cubren los tests dedicados de este módulo —
    `test_corpus_estop_shortcuts_match_window`, `test_cited_code_paths_exist`,
    `test_monograph_cross_references_resolve` y `test_shutter_lines_match_config`.
    """
    assert _INVARIANTS_FILE.is_file(), "Falta lab-invariants.md"
    body = _strip_code_fences(_INVARIANTS_FILE.read_text(encoding="utf-8", errors="ignore"))

    checked, checked_str, offenders = [], [], []
    for lineno, line in enumerate(body.splitlines(), start=1):
        if not line.lstrip().startswith("|") or "✅" not in line:
            continue
        refs = [m for m in (_CODE_SUBSCRIPT_REF.search(line), _CODE_REF.search(line)) if m]
        if not refs:
            continue  # fila ✅ sin símbolo de código: la cubre un test dedicado
        ref = min(refs, key=lambda m: m.start())
        rel_path, symbol = ref.group(1), ref.group(2)
        keys = re.findall(r'\["([^"\]]+)"\]', ref.group(3)) if ref.re is _CODE_SUBSCRIPT_REF else []

        if not keys:
            actual_str = _resolve_code_string(rel_path, symbol)
            if actual_str is not None:
                token = _BACKTICK_TOKEN.search(_table_value_cell(line))
                documented_str = token.group(1) if token else None
                if documented_str != actual_str:
                    offenders.append(
                        f"lab-invariants.md:{lineno}: la tabla dice {documented_str!r} pero "
                        f"{rel_path}::{symbol} vale {actual_str!r}."
                    )
                else:
                    checked_str.append(f"{symbol}={actual_str}")
                continue

        num = _NUMBER_TOKEN.search(line)
        if not num:
            continue  # fila ✅ sin par (valor, símbolo): la cubre un test dedicado

        documented = float(num.group(1))
        if keys:
            actual = _resolve_code_subscript(rel_path, symbol, keys)
            symbol = symbol + "".join(f"[{k!r}]" for k in keys)
        else:
            actual = _resolve_code_number(rel_path, symbol)

        if actual is None:
            offenders.append(
                f"lab-invariants.md:{lineno}: no se pudo resolver `{rel_path}::{symbol}` — "
                f"¿se renombró o refactorizó? La fila declara {documented}."
            )
        elif abs(actual - documented) > 1e-9:
            offenders.append(
                f"lab-invariants.md:{lineno}: la tabla dice {documented} pero "
                f"{rel_path}::{symbol} vale {actual}."
            )
        else:
            checked.append(f"{symbol}={actual}")

    assert not offenders, (
        "Invariantes de laboratorio desincronizados respecto del código:\n  "
        + "\n  ".join(offenders)
    )
    # Guarda contra el fallo silencioso: si el parseo de la tabla se rompe (por un cambio de
    # formato), este test pasaría sin verificar nada. Exigir un mínimo lo convierte en ruidoso.
    assert len(checked) >= 4, (
        f"Sólo se verificaron {len(checked)} invariantes ({checked}); se esperaban >= 4. "
        "Probablemente cambió el formato de la tabla y el parseo dejó de encontrar filas."
    )
    # Mismo resguardo para la vía de cadenas (canales analógicos del filtro de densidad y del
    # láser de 532 nm): si deja de encontrar filas, falla en vez de pasar sin verificar nada.
    assert len(checked_str) >= 2, (
        f"Sólo se verificaron {len(checked_str)} invariantes de texto ({checked_str}); se "
        "esperaban >= 2. Probablemente cambió el formato de la columna Valor."
    )


def test_delegation_cross_references_resolve():
    """Toda derivación "(use <otro-agente>)" en una `description:` apunta a algo que existe.

    Las descripciones llevan fronteras explícitas del tipo "Do NOT use for X (use
    computational-physicist)" para que el ruteo no dependa de adivinar. Esas derivaciones son
    referencias frágiles: renombrar o borrar un agente las deja colgadas, y una derivación
    colgada es peor que ninguna — manda al lector a un especialista inexistente.

    Limitación conocida: sólo se validan los nombres con guion (`qa-ux-auditor`,
    `scientific-gui-designer`, ...), que son los renombrables de facto. Los de una sola
    palabra (`physicist`, `metrology`, `instrumentation`, `experimentalist`) no se distinguen
    sintácticamente del inglés corriente y se omiten a propósito, para no producir falsos
    positivos sobre prosa legítima.
    """
    known = {f.stem for f in (ROOT / ".claude" / "agents").glob("*.md")}
    known |= {p.parent.name for p in (ROOT / ".claude" / "skills").glob("*/SKILL.md")}

    ref = re.compile(r"\buse ([a-z0-9]+(?:-[a-z0-9]+)+)\b")
    offenders = []
    for path in sorted((ROOT / ".claude" / "agents").glob("*.md")):
        _, desc = _frontmatter_name(path)
        if not desc:
            continue
        for m in ref.finditer(desc):
            token = m.group(1)
            if token not in known:
                offenders.append(f"{path.name}: deriva a '{token}', que no existe")

    assert not offenders, (
        "Derivaciones colgadas entre agentes:\n  " + "\n  ".join(offenders)
    )


@pytest.mark.parametrize(
    "path", sorted((ROOT / ".claude" / "skills").glob("*/SKILL.md")), ids=lambda p: p.parent.name
)
def test_skill_frontmatter_is_valid(path):
    name, desc = _frontmatter_name(path)
    assert name, f"{path.parent.name}/SKILL.md: falta `name:` en el frontmatter YAML"
    assert desc, f"{path.parent.name}/SKILL.md: falta `description:`"
    assert name == path.parent.name, (
        f"{path.parent.name}/SKILL.md: name '{name}' != nombre de directorio "
        f"'{path.parent.name}'"
    )


# ==============================================================================
# 8. Vocabulario del protocolo deliberativo
# ==============================================================================
def test_no_superseded_two_round_protocol_vocabulary():
    """El protocolo tiene 4 rondas; 'Phase 4' como etapa del ciclo ya no existe.

    `interactive-tool-design/SKILL.md` numera sus PROPIAS fases 1-5 para el audit de DoF,
    lo cual es legítimo y no debe marcarse — de ahí que se busquen las frases fechadas
    concretas y no la palabra suelta.
    """
    dated = (
        "Phase 4 Execution",
        "Phase 4: Hard Implementation",
        "Optional Round 3",
        "Round 3: Hybrid Clarification",
    )
    offenders = []
    for path in CORPUS:
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1
        ):
            for phrase in dated:
                if phrase.lower() in line.lower():
                    offenders.append(
                        f"{path.relative_to(ROOT)}:{lineno}: '{phrase}' :: {line.strip()[:110]}"
                    )

    assert not offenders, (
        "Vocabulario del protocolo de 2 rondas ya superado (usar Rondas 1-4, con la "
        "Ronda 3 obligatoria para cambios de GUI):\n  " + "\n  ".join(offenders)
    )


# ==============================================================================
# Líneas DAQ de los obturadores (DEC-036)
# ==============================================================================
def _shutter_channels_ground_truth():
    """`config.SHUTTER_CHANNELS` leído como texto, sin importar config (que instancia drivers)."""
    src = (ROOT / "config.py").read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"^SHUTTER_CHANNELS\s*=\s*\[([^\]]*)\]", src, re.MULTILINE)
    assert m, "No se encontró SHUTTER_CHANNELS en config.py"
    return [int(x) for x in re.findall(r"\d+", m.group(1))]


def test_shutter_lines_match_config():
    """CLAUDE.md y lab-invariants.md citan las líneas reales de los obturadores.

    Durante meses el corpus dijo `Dev1/port0/line0:3` mientras el código usaba las líneas
    11, 8, 9 y 10 (auditoría documental 2026-09-27, DEC-036). En seguridad láser, citar una
    línea equivocada es un error de procedimiento: este test la ata al código.
    """
    channels = _shutter_channels_ground_truth()
    offenders = []
    for path in dict.fromkeys(CORPUS + [_INVARIANTS_FILE]):
        body = _strip_code_fences(path.read_text(encoding="utf-8", errors="ignore"))
        for lineno, line in enumerate(body.splitlines(), start=1):
            if re.search(r"port0/line0:3|line0:3", line):
                offenders.append(f"{path.relative_to(ROOT)}:{lineno}: cita `line0:3`; el código usa {channels}")
    for path in (ROOT / "CLAUDE.md", _INVARIANTS_FILE):
        body = path.read_text(encoding="utf-8", errors="ignore")
        missing = [ch for ch in channels if not re.search(rf"line{ch}\b", body)]
        if missing:
            offenders.append(f"{path.relative_to(ROOT)}: no cita las líneas {missing} de config.SHUTTER_CHANNELS")
    assert not offenders, "Líneas de obturadores desincronizadas del código:\n  " + "\n  ".join(offenders)


def _digital_lines_ground_truth() -> set[int]:
    """Líneas digitales que el código usa: obturadores + flipper del notch de 532 nm."""
    src = (ROOT / "config.py").read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"^FLIPPER_532_CHAN\s*=\s*(\d+)", src, re.MULTILINE)
    assert m, "No se encontró FLIPPER_532_CHAN en config.py"
    return set(_shutter_channels_ground_truth()) | {int(m.group(1))}


def test_documents_cite_only_real_digital_lines():
    """Ningún documento (CAT/SYS/MOD, manual, ledgers de evidencia, corpus de agentes) cita una
    línea `port0/lineN` que el código no usa.

    El test anterior sólo miraba CLAUDE.md y .claude/, y sólo la cadena `line0:3`: SYS-305 siguió
    ubicando el obturador de 532 nm en `port0/line0` después de que DEC-036 lo diera por
    corregido. Se revisan también los bloques de código (un diagrama ASCII con la línea
    equivocada engaña igual). Quedan fuera DECISION_LOG.md (historia append-only, con los
    valores viejos anotados en el punto de reemplazo) y las auditorías fechadas de
    `docs/evidence/auditoria_*/`, que citan los valores viejos a propósito para documentarlos.
    """
    allowed = _digital_lines_ground_truth()
    ledger = ROOT / "docs" / "decisions" / "DECISION_LOG.md"
    audits = ROOT / "docs" / "evidence"

    def _is_dated_audit(p: Path) -> bool:
        rel = p.relative_to(audits).parts if audits in p.parents else ()
        return bool(rel) and rel[0].startswith("auditoria_")

    paths = [p for base in ("docs", "reportes") for p in sorted((ROOT / base).rglob("*.md"))
             if not _in_foreign_tree(p) and p != ledger and not _is_dated_audit(p)]
    paths += [p for p in CORPUS if p.suffix == ".md"]
    offenders = []
    for path in dict.fromkeys(paths):
        for lineno, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
            for m in re.finditer(r"port0/line(\d+)(?::(\d+))?", line):
                lo = int(m.group(1))
                hi = int(m.group(2)) if m.group(2) else lo
                cited = set(range(min(lo, hi), max(lo, hi) + 1))
                if not cited <= allowed:
                    offenders.append(f"{path.relative_to(ROOT)}:{lineno}: `{m.group(0)}` "
                                     f"(el código usa {sorted(allowed)})")
    assert not offenders, ("Documentos que citan líneas digitales que el código no usa:\n  "
                           + "\n  ".join(offenders))
