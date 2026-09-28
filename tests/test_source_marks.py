# -*- coding: utf-8 -*-
"""
test_source_marks.py — Gate de las marcas de fuente (fase 3 del plan de correcciones, DEC-038).

PyPrinting 3.0 / PySpectrum 3.0 — UNSAM Nanofotónica

MOTIVACIÓN
----------
La auditoría documental del 2026-09-27 encontró que 700 de 1377 afirmaciones eran falsas o
estaban desactualizadas, y que los valores viajaban de un documento a otro con atribuciones que
la fuente citada no respaldaba. El control es el agente `provenance-verifier`; este módulo es su
complemento mecánico (`tools/source_marks.py`), con dos políticas distintas que decidió el
investigador (`RESPUESTAS_INVESTIGADOR.md`, "R3 — Ronda 2 del verificador", puntos 3 y 4):

1. `test_source_marks_are_valid` **falla**: una marca mal formada, o que cita una clave, una
   página, un punto del investigador o un símbolo que no existe, es una referencia rota, igual que
   un `DEC-xxx` inexistente. Una marca de código que contradice al código es peor que ninguna.
2. `test_adhered_documents_cover_their_figures` **sólo advierte**: imprime sus hallazgos en la
   sección "Cobertura de fuentes (advertencia, no bloquea)" del resumen de pytest
   (`tests/conftest.py::pytest_terminal_summary`) y pasa siempre. Mira sólo los documentos
   adheridos (`tools/source_marks.py::ADHERED_DOCUMENTS`), que hoy son cero.

Cada comportamiento tiene su control negativo: un caso sintético que tiene que fallar o advertir.
Las páginas se comparan con `tools/bib_page_counts.json`; ningún test depende de `pdftotext`.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load_source_marks():
    name = "pyprinting_tools_source_marks"
    module = sys.modules.get(name)
    if module is None:
        spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / "source_marks.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return module


sm = _load_source_marks()
CTX = sm.default_context()


def _errors(text: str) -> list:
    return sm.validate_text(text, "sintético", CTX)[0]


# ==============================================================================
# Contexto: claves, páginas y puntos del investigador (si el parseo se rompe, fallar ruidosamente)
# ==============================================================================
def test_context_parses_keys_pages_and_answer_points():
    """Guarda contra el fallo silencioso: si cambia el formato de `lab-invariants` §9 o de
    `RESPUESTAS_INVESTIGADOR.md`, todas las marcas pasarían a ser inválidas (o, peor, válidas)."""
    for key in ("P25", "M24", "G17", "AN17", "DS-iXon", "BNC", "DW-1"):
        assert key in CTX.keys, f"la clave {key} de lab-invariants §9 no se parseó"
    expected = ({f"R1-{n}" for n in range(1, 13)} | {f"R2-{n}" for n in range(1, 21)}
                | {f"R3-{x}" for x in "ABCDE"})
    missing = expected - CTX.answer_points
    assert not missing, f"puntos de RESPUESTAS_INVESTIGADOR.md que no se parsearon: {sorted(missing)}"
    assert "R1-13" not in CTX.answer_points and "R2-21" not in CTX.answer_points
    assert CTX.exempt_wavelengths == {532.0, 637.0, 592.0, 808.0}, (
        "los láseres configurados salen de config.py::SHUTTERS; si cambió, revisá la exención")


def test_bib_page_counts_cover_every_pdf_key():
    """Toda clave de §9 cuyo archivo es un PDF tiene su cantidad de páginas en
    `tools/bib_page_counts.json`, y el PDF existe. Si se agrega una clave sin regenerar el JSON
    (`python tools/source_marks.py index-bib --update-counts`), sus marcas no se podrían validar."""
    missing, absent = [], []
    for key, rel in CTX.keys.items():
        if not rel.lower().endswith(".pdf"):
            continue
        if not (sm.BIB_DIR / rel).is_file():
            absent.append(f"[{key}] {rel}")
        if CTX.page_counts.get(key, 0) < 1:
            missing.append(key)
    assert not absent, "claves de lab-invariants §9 cuyo PDF no está en docs/bibliografia/:\n  " + "\n  ".join(absent)
    assert not missing, f"claves sin páginas en tools/bib_page_counts.json: {missing}"


# ==============================================================================
# 1. Validez de las marcas: FALLA (respuesta 3 del investigador)
# ==============================================================================
def test_source_marks_are_valid():
    """Toda marca explícita en `docs/`, `reportes/`, `CLAUDE.md` y `.claude/` está bien formada y
    resuelve. Quedan fuera los spans de código (D1), las auditorías fechadas, `DECISION_LOG.md` y
    `reportes/archivo/` (§5.2 del diseño)."""
    surface = sm.marked_surface()
    assert len(surface) >= 100, f"superficie sospechosamente chica ({len(surface)} archivos): ¿cambió el layout?"
    errors, _notices = sm.validate_corpus_marks()
    assert not errors, "Marcas de fuente inválidas:\n  " + "\n  ".join(errors)


@pytest.mark.parametrize("text, needle", [
    ("La constante vale 2.5 × 10⁻¹⁹ J [fuente: CAT-110].", "no es fuente"),
    ("Vale 3 nm [fuente: M99 p. 3].", "'M99' no es una clave"),
    ("Deriva 30 nm/min [fuente: M24 p. 999].", "fuera del PDF"),
    ("Fuerza iónica 0.5 mM [experimental: investigador, 2026-09-27, R1-13].", "R1-13 no existe"),
    ("Recorrido en Z: 100 µm [fuente: `config.py::PI_Z_RANGE_UM`].", "no coincide (D3)"),
    ("Vale 5 ms [fuente: `core/nidaq.py::NO_EXISTE`].", "`NO_EXISTE` no existe"),
    ("Deriva 30 nm/min [fuente: [M24] p. 75].", "sin corchetes"),
    ("κ⁻¹ ≈ 13.6 nm [derivado: sale de la teoría].", "con un '='"),
    (r"El pulso $5\ \text{ms} [fuente: M24 p. 75]$.", "dentro de $…$"),
    ("No es 500 ms [refutado: DEC-999].", "DEC-999 no existe"),
    ("Vale 5 ms [fuente M24 p. 75].", "falta ':'"),
    ("Vale 5 ms [fuente: docs/MANUAL_USUARIO.md:12].", "no es fuente"),
    ("Vale 30 nm/min [Fuente: M24 p. 75].", "minúsculas"),
    ("Vale 30 nm/min [fuente: M24 p. 75", "sin cerrar"),
    ("Vale 0.5 mM [fuente: R2-14].", "no es fuente"),
    ("Vale 0.5 mM [experimental: investigador, R2-14].", "fecha"),
    ("Vale 3 ms [experimental: lo dijo alguien].", "punto de RESPUESTAS_INVESTIGADOR"),
    ("Vale 3 nm [fuente: M24].", "falta la página"),
    ("Vale 3 nm [fuente: DOI 10.12/x].", "DOI mal formado"),
    ("Vale 3 nm [fuente: config.py:99999].", "líneas, no 99999"),
    ("NA 0.90 [fuente: `core/sif_processor.py::MICROSCOPE_OBJECTIVES[\"Olympus LUMPlanFLN 60x W (NA 1.00)\"][\"na\"]`].",
     "no coincide (D3)"),
    ("[ilustrativo: ejemplo]", "no lleva contenido"),
    ("Vale 3 nm [a verificar].", "requiere contenido"),
], ids=["interno", "clave", "pagina", "punto", "D3-valor", "simbolo", "corchetes", "derivado", "en-latex",
        "refutado-DEC", "sin-dos-puntos", "md-como-fuente", "mayuscula", "sin-cerrar", "punto-en-fuente",
        "sin-fecha", "sin-punto", "sin-pagina", "doi", "linea", "D3-NA", "ilustrativo", "a-verificar"])
def test_invalid_marks_are_rejected(text, needle):
    """Controles negativos de §5.4: cada marca rota da el error **de su causa** (no otro que la
    rechace por casualidad: así un control no queda cubierto por una regla vecina)."""
    errors = _errors(text)
    assert any(needle in e for e in errors), f"se esperaba {needle!r}; errores: {errors}"


@pytest.mark.parametrize("text", [
    "Recorrido en Z: 20 µm [fuente: `config.py::PI_Z_RANGE_UM`].",
    "El pulso del filtro de densidad dura $5\\ \\text{ms}$ [fuente: `core/nidaq.py::_pulse_flipper`].",
    "La deriva en XY es de 30 nm/min [fuente: M24 p. 75], y la usamos hasta medirla en el banco.",
    "Fuerza iónica de trabajo: 0.5 mM [experimental: investigador, 2026-09-27, R2-14].",
    "Sal del protocolo: NaCl [experimental: investigador, 2026-09-27, R3-A].",
    "σ_MC = 3 nm [experimental: método en desarrollo, R1-9].",
    "κ⁻¹ ≈ 13.6 nm a 0.5 mM [derivado: κ⁻¹ = 0.304 nm / √(I [M]) para un electrolito 1:1 a 25 °C].",
    "[sin fuente] [sin fuente: medir con BANCO-17] [a verificar: bornera de P0.8–P0.11, NI MAX] [ilustrativo] [refutado: DEC-023]",
    "El espectrómetro sólo recibe luz con el espejo abajo [fuente: legado scratch/pyspectrum-legacy/Luminescence_ps.py:695] [experimental: investigador, 2026-09-27, R2-4].",
    "Precisión de impresión 50 nm [fuente: DOI 10.1021/acsnano.7b04136].",
    "Recorrido en Z: 20 µm [fuente: config.py:63].",
    "NA 1.0 [fuente: `core/sif_processor.py::MICROSCOPE_OBJECTIVES[\"Olympus LUMPlanFLN 60x W (NA 1.00)\"][\"na\"]`].",
    "Dispersión 12.8 nm/mm [fuente: `pyspectrum/drivers/shamrock_driver.py::NOMINAL_DISPERSION_150_NM_PER_MM`].",
    "Deadline de 30 s [fuente: `core/nidaq.py::_default_timeout_s`] y poll de 100 ms [fuente: `core/nidaq.py::_watchdog_loop`].",
    "Emergencia [fuente: `pyspectrum/window.py::_setup_shortcuts`] y una fuente múltiple [fuente: M24 p. 75; G17 p. 65].",
])
def test_valid_marks_are_accepted(text):
    """Controles positivos: las formas del §3.2 del diseño no dan errores."""
    assert not _errors(text), _errors(text)


@pytest.mark.parametrize("text", [
    "El formato es `[fuente: M99 p. 3]` y se documenta entre backticks.",
    "Ver [fuente](https://ejemplo.org) para el detalle.",
    "Un bloque:\n```\n[fuente: M99 p. 3]\n```\n",
])
def test_marks_in_code_or_links_are_not_marks(text):
    """D1: los ejemplos de marcas entre backticks o en bloques de código, y los enlaces markdown,
    no son marcas: no se validan (el control positivo es que `[fuente: M99 p. 3]` fuera de código
    sí se rechaza, en `test_invalid_marks_are_rejected`)."""
    assert not sm.analyze(text, "sintético", CTX).marks
    assert not _errors(text)


def test_symbol_resolution_stays_inside_the_function(tmp_path):
    """`resolve_code_number` toma el `time.sleep` del cuerpo de la función, no el de la siguiente.

    Control negativo: la regex anterior del gate (`def X(.*?time.sleep(`) se salía de una función
    sin `sleep` y devolvía el de la función siguiente."""
    (tmp_path / "m.py").write_text(
        "import time\n\ndef a():\n    pass\n\ndef b():\n    time.sleep(0.5)\n", encoding="utf-8")
    assert sm.resolve_code_number("m.py", "a", tmp_path) is None
    assert sm.resolve_code_number("m.py", "b", tmp_path) == 0.5
    import re
    old = re.search(r"def a\(.*?time\.sleep\(\s*([0-9]*\.?[0-9]+)\s*\)",
                    (tmp_path / "m.py").read_text(encoding="utf-8"), re.DOTALL)
    assert old and float(old.group(1)) == 0.5, "el control negativo dejó de reproducir el defecto"
    ref = sm.resolve_code_ref("`m.py::a`", tmp_path)
    assert ref.exists and ref.value is None
    assert not sm.resolve_code_ref("`m.py::c`", tmp_path).exists


# ==============================================================================
# Normalización de LaTeX y detector de cifras (§5.1, §5.2)
# ==============================================================================
@pytest.mark.parametrize("latex, plain", [
    (r"$500\ \text{ms}$", "500 ms"),
    (r"$\tau_{wd} = 500\,\mathrm{ms}$", "500 ms"),
    (r"$500~\text{ms}$", "500 ms"),
    (r"$10\,\mu\text{m}$", "10 µm"),
    (r"$13\ \mu\mathrm{m}$", "13 µm"),
    (r"$2.1 \times 10^{-20}\ \text{J}$", "2.1 × 10⁻²⁰ J"),
    (r"$25^\circ\text{C}$", "25°C"),
    (r"$520.7\ \text{cm}^{-1}$", "520.7 cm⁻¹"),
    (r"$0.2\%$", "0.2%"),
    ("5 μm", "5 µm"),
])
def test_latex_to_plain(latex, plain):
    assert plain in sm.latex_to_plain(latex)


@pytest.mark.parametrize("text, expected", [
    ("La deriva es 30 nm/min.", ["30 nm/min"]),
    (r"El pulso dura $5\ \text{ms}$.", ["5 ms"]),
    (r"| pitch | $13\ \mu\text{m}$ |", ["13 µm"]),
    ("$$\n\\kappa^{-1} = 13.6\\ \\text{nm}\n$$", ["13.6 nm"]),
    ("Rango −60 a −80 °C y 0.5-1.5 mM.", ["−60 a −80 °C", "0.5-1.5 mM"]),
    ("NA 1.0 y OD > 6.", ["NA 1.0", "OD > 6"]),
    ("A_H ≈ 2.1 × 10⁻²⁰ J.", ["2.1 × 10⁻²⁰ J"]),
    ("El láser de 642 nm.", ["642 nm"]),
    ("CAT-207, DEC-036, R2-14, 2026-09-27, p. 75, l. 695 y 51 %.", []),
    ("El valor `20 µm` está en código.", []),
    ("El watchdog no es de 500 ms.", []),
    ("No es 500 ms [refutado: DEC-023].", []),
])
def test_figure_detector(text, expected):
    got = [f.raw for f in sm.iter_figures(text, exempt_wavelengths=CTX.exempt_wavelengths) if not f.exempt]
    assert got == expected


def test_configured_laser_names_are_exempt_but_other_wavelengths_are_not():
    """§5.2: "532 nm" como nombre de un láser configurado se exime; "642 nm" no (L2 202-02)."""
    figs = list(sm.iter_figures("Láseres de 532 nm y de 642 nm.", exempt_wavelengths=CTX.exempt_wavelengths))
    assert [(f.raw, f.exempt) for f in figs] == [("532 nm", "láser configurado"), ("642 nm", "")]


# ==============================================================================
# 2. Cobertura de los documentos adheridos: SÓLO ADVIERTE (respuesta 4 del investigador)
# ==============================================================================
_COVERAGE_DOC = r"""# Documento adherido sintético

**Fuentes:** marcadas (2026-09-27, provenance-verifier)

Sin marca en texto: 30 nm/min en prosa.
Con marca en línea: 20 µm [fuente: `config.py::PI_Z_RANGE_UM`].
Pulso en LaTeX $5\ \text{ms}$ sin marca.

| Magnitud | Valor |
| :--- | :--- |
| pitch | 8 µm |

| Magnitud | Valor | Fuente |
| :--- | :--- | :--- |
| Z | 20 µm | [fuente: `config.py::PI_Z_RANGE_UM`] |
| deriva | 30 nm/min | RESPALDADO ([M24] p. 75) |
| otra | 3 ms | nada |

[ilustrativo]
| Ejemplo | Valor |
| :--- | :--- |
| a | 50 nm |

$$
\kappa^{-1} = 13.6\ \text{nm}
$$

$$
x = 7\ \text{ms}
$$
[derivado: x = 7 ms por definición]

Láser de 532 nm (exento) y el de 642 nm (no).
"""


def test_coverage_scopes():
    """Los tres alcances de §3.1 (en línea, columna Fuente/Respaldo y bloque) cubren; lo demás,
    en texto, en tabla, en `$…$` y en `$$…$$`, queda sin marca."""
    uncovered = [(f.line, f.raw) for f in sm.coverage(_COVERAGE_DOC, "sintético", CTX)]
    assert uncovered == [(5, "30 nm/min"), (7, "5 ms"), (11, "8 µm"), (17, "3 ms"), (25, "13.6 nm"), (33, "642 nm")]
    scopes = {(m.line, m.label): m.scope for m in sm.analyze(_COVERAGE_DOC, "sintético", CTX).marks}
    assert scopes == {(6, "fuente"): "inline", (15, "fuente"): "column",
                      (19, "ilustrativo"): "block", (31, "derivado"): "block"}


def test_adhered_documents_cover_their_figures(source_coverage_report):
    """Test 2 del diseño: sólo advierte. Nunca falla; sus hallazgos van a la sección
    "Cobertura de fuentes (advertencia, no bloquea)" del resumen de pytest."""
    source_coverage_report.extend(sm.adhered_coverage_findings())


def test_coverage_warns_on_a_synthetic_adhered_document(tmp_path):
    """Control negativo del test 2: un documento adherido con cifras sin marca produce
    advertencias (y no una excepción). Un documento listado que no existe también se advierte."""
    doc = tmp_path / "SYS-999_sintetico.md"
    doc.write_text(_COVERAGE_DOC, encoding="utf-8")
    findings = sm.adhered_coverage_findings([doc, tmp_path / "no_existe.md"], ctx=CTX)
    assert sum("cifra sin marca" in f for f in findings) == 6
    assert any("no existe" in f for f in findings)
    doc.write_text(_COVERAGE_DOC.replace("**Fuentes:** marcadas (2026-09-27, provenance-verifier)", ""), encoding="utf-8")
    assert any("falta la línea de adhesión" in f for f in sm.adhered_coverage_findings([doc], ctx=CTX))


def test_coverage_section_is_printed_and_never_fails(request):
    """El hook de `tests/conftest.py` imprime la sección propia con los hallazgos, y no la imprime
    si el test de cobertura no corrió."""
    conftest = next(p for p in request.config.pluginmanager.get_plugins()
                    if getattr(p, "__file__", "").replace("\\", "/").endswith("tests/conftest.py"))

    class _Reporter:
        def __init__(self):
            self.lines = []

        def write_sep(self, sep, title):
            self.lines.append(f"{sep * 3} {title}")

        def write_line(self, line):
            self.lines.append(line)

    class _Config:
        def __init__(self):
            self.stash = pytest.Stash()

    config, reporter = _Config(), _Reporter()
    conftest.pytest_terminal_summary(reporter, 0, config)
    assert reporter.lines == [], "sin el test de cobertura no tiene que aparecer la sección"
    config.stash[conftest.SOURCE_COVERAGE_KEY] = ["docs/x.md:3: cifra sin marca (texto): 30 nm/min"]
    conftest.pytest_terminal_summary(reporter, 0, config)
    assert any("Cobertura de fuentes (advertencia, no bloquea)" in line for line in reporter.lines)
    assert any("30 nm/min" in line for line in reporter.lines)


# ==============================================================================
# check-report: el verificador de citas del propio informe (§7.1 del diseño)
# ==============================================================================
_REPORT = """## Verificación de procedencia — informe fabricado
| # | Ubicación | Afirmación | Tipo | Veredicto | Sev. | Respaldo | Cita del texto | Acción sugerida |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | `config.py:63` | "deriva 30 nm/min" | valor | RESPALDADO | — | M24 p. 999, "velocidad promedio de 30 nm/min" | ninguna | — |
| 2 | `config.py:63` | "deriva nula" | valor | CONTRADICHO | ALTA | M24 p. 75, "la deriva es nula" | ninguna | — |
| 3 | `config.py:63` | "símbolo" | código | RESPALDADO | — | `config.py::NO_EXISTE` | ninguna | — |
| 4 | `config.py:63` | "clave" | valor | RESPALDADO | — | M99 p. 3, "algo" | ninguna | — |
| 5 | `config.py:63` | "buena" | valor | RESPALDADO | — | M24 p. 75, "velocidad promedio de 30 nm/min" | verificada | — |
| 6 | `config.py:63` | "Z" | valor | RESPALDADO | — | `config.py::PI_Z_RANGE_UM` = 20.0 | ninguna | — |
| 7 | `config.py:63` | "pinhole" | valor | DERIVADO (a partir de un dato EXPERIMENTAL) | — | 1.22 · 532 nm · 50 / 1.0 = 32.5 µm; investigador, 2026-09-27, R2-20 | ninguna | — |
| 8 | `config.py:63` | "canal" | estructural | RESPALDADO (canal) · EXPERIMENTAL (sentido up/down) | — | `config.py::FLIPPER_532_CHAN`; investigador, 2026-09-27, R2-4 | ninguna | — |
"""


def _fake_index(tmp_path):
    (tmp_path / "M24").mkdir()
    (tmp_path / "M24" / "p75.txt").write_text(
        "… revela una veloci-\ndad promedio de 30 nm/min, medida con PyPrinting …", encoding="utf-8")
    return tmp_path


def test_check_report_rejects_the_four_fabricated_rows(tmp_path):
    """§7.1: una página equivocada, una cita que no está en la página, un símbolo inexistente y
    una clave que no está en §9 se rechazan; las filas correctas (incluida una cita con guion de
    corte de línea en el PDF y los veredictos por aspecto) pasan."""
    errors = sm.check_report_text(_REPORT, CTX, _fake_index(tmp_path))
    by_row = {n: [e for e in errors if f"(#{n})" in e] for n in range(1, 9)}
    assert any("fuera del PDF" in e for e in by_row[1]), by_row[1]
    assert any("no está en M24 p. 75" in e for e in by_row[2]), by_row[2]
    assert any("NO_EXISTE" in e for e in by_row[3]), by_row[3]
    assert any("'M99' no es una clave" in e for e in by_row[4]), by_row[4]
    for n in (5, 6, 7, 8):
        assert not by_row[n], by_row[n]


@pytest.mark.parametrize("backing, verdict, needle", [
    ("M24 p. 75", "RESPALDADO", "sin cita textual"),
    ("Martinez p. 75, \"velocidad promedio\"", "RESPALDADO", "no es una clave"),
    ("investigador, 2026-09-27, R2-99", "EXPERIMENTAL", "R2-99 no existe"),
    ("CAT-110 §3", "RESPALDADO", "sólo interno"),
    ("M24 p. 75, \"velocidad promedio de 30 nm/min en todo el rango de trabajo del banco durante veinte minutos\"",
     "RESPALDADO", "máximo 15"),
    ("`config.py::PI_Z_RANGE_UM`", "CONFIRMADO", "veredicto no reconocido"),
])
def test_check_report_rejects_other_broken_rows(tmp_path, backing, verdict, needle):
    report = ("| # | Ubicación | Afirmación | Tipo | Veredicto | Sev. | Respaldo | Cita del texto | Acción sugerida |\n"
              "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n"
              f"| 1 | `config.py:63` | \"x\" | valor | {verdict} | — | {backing} | ninguna | — |\n")
    errors = sm.check_report_text(report, CTX, _fake_index(tmp_path))
    assert any(needle in e for e in errors), errors


def test_check_report_needs_a_verdict_table():
    assert sm.check_report_text("# Sin tabla\n\nNada que verificar.\n", CTX)


def test_check_report_flags_quotes_it_cannot_verify(tmp_path):
    """Sin índice por página, una cita no se da por buena: se informa como no comprobada."""
    report = ("| # | Ubicación | Afirmación | Tipo | Veredicto | Sev. | Respaldo | Cita del texto | Acción sugerida |\n"
              "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n"
              "| 1 | `config.py:63` | \"x\" | valor | RESPALDADO | — | M24 p. 75, \"velocidad promedio\" | ninguna | — |\n")
    errors = sm.check_report_text(report, CTX, tmp_path / "sin_indice")
    assert any("falta el índice" in e for e in errors), errors


# ==============================================================================
# CLI: el contrato de salida que usa el agente
# ==============================================================================
def test_cli_scan_exit_codes(tmp_path, capsys):
    """0 ante huecos de cobertura; 1 con una marca mal formada o con `--strict` y huecos."""
    ok = tmp_path / "ok.md"
    ok.write_text("Recorrido en Z: 20 µm [fuente: `config.py::PI_Z_RANGE_UM`]. La deriva es 30 nm/min.\n", encoding="utf-8")
    bad = tmp_path / "bad.md"
    bad.write_text("Vale 3 nm [fuente: M99 p. 3].\n", encoding="utf-8")
    assert sm.main(["scan", str(ok)]) == 0
    assert "Triage:" in capsys.readouterr().out
    assert sm.main(["scan", "--strict", str(ok)]) == 1
    assert sm.main(["scan", str(bad)]) == 1
    assert sm.main(["scan"]) == 2
