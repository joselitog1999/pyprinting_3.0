# -*- coding: utf-8 -*-
"""
conftest.py — Fixtures compartidas de pytest para la suite PyPrinting 3.0 / PySpectrum 3.0

Se carga antes que cualquier módulo de test, así que también es el lugar correcto para
fijar las variables de entorno de modo seguro/headless que la mayoría de los archivos de
test repiten individualmente, y para resolver el conflicto de instalación de PyQt6 (ver
abajo) antes de que ningún archivo de test tenga oportunidad de importarlo primero.
"""
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("PYPRINTING_SAFE", "1")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Causa raíz real de "ImportError: DLL load failed while importing QtWidgets" (visto de
# forma intermitente en toda la sesión, antes atribuido incorrectamente a un problema de
# entorno no accionable): este entorno tiene DOS instalaciones de PyQt6 para Python 3.13 —
# la del entorno conda base (rota: falla al cargar sus DLLs nativas de Qt6) y la de
# `.venv/Lib/site-packages` (funcional). `config.py` antepone `.venv/Lib/site-packages` a
# sys.path (línea ~31), pero solo si `config` ya se importó. Si algún archivo de test
# importa `PyQt6.QtWidgets` ANTES de que `config` se haya importado nunca en el proceso,
# Python resuelve `PyQt6` desde el paquete roto del conda base y la importación falla —
# de forma determinística, no intermitente (confirmado). Importar `config` aquí, antes de
# que pytest coleccione ningún archivo de test, garantiza que sys.path ya esté corregido
# para TODOS los imports de PyQt6 posteriores, sin depender del orden de imports interno
# de cada archivo de test individual.
import config  # noqa: F401

import pytest


@pytest.fixture(autouse=True)
def _isolate_spectroscopy_context():
    """Aísla el singleton global `spectroscopy_context` entre tests.

    `SpectroscopyContext` es un singleton de proceso (el bus de parámetros ópticos compartido
    entre pestañas) y sus setters emiten SÓLO si el valor difiere del actual. Por eso un test
    que deja el contexto mutado convierte el `set_*` de un test posterior en un no-op
    silencioso: el segundo test cree ejercitar la propagación señal→slot, no se emite nada, y
    pasa en verde sin haber probado lo que declara probar.

    Eso estaba ocurriendo de hecho: `test_pyspectrum_calibration_and_fixes.py` dejaba el
    colormap en "Inferno", y como pytest colecciona ese archivo antes que
    `test_pyspectrum_raman_2d_inspector.py` (orden alfabético),
    `test_colormap_reaction_from_spectroscopy_context` era un no-op. Verificado
    empíricamente antes de escribir este fixture, no deducido.

    La restauración es deliberadamente **silenciosa** — escribe los atributos en vez de llamar
    a los setters — para no emitir señales hacia widgets que ya están siendo destruidos al
    final del test. Se usa `update()` y no `clear()` porque el `__dict__` de un QObject no es
    exclusivamente nuestro.
    """
    from pyspectrum.modules.spectroscopy_context import spectroscopy_context as ctx
    snapshot = dict(ctx.__dict__)
    yield
    ctx.__dict__.update(snapshot)


@pytest.fixture(autouse=True)
def _isolate_andor_mock_geometry():
    """Aísla la geometría de adquisición del mock de cámara Andor entre tests.

    `get_andor_ccd()` devuelve un SINGLETON de proceso, y `_MockAndorCCD.set_image()` pasó a
    registrar el sub-área vertical (`_image_vstart`/`_image_vend`) para honrarlo en
    `get_most_recent_image()`, igual que el hardware real. Eso es correcto, pero convierte a
    esos atributos en estado global persistente: `test_linescan_h5.py` configura el sub-área
    [482:521] en `acquire_reference()` y nunca lo deshace, así que
    `test_pyspectrum_exploration_tab.py` (que corre después por orden alfabético) recibía un
    cuadro de 40 filas en vez de las 1002 del sensor y fallaba. Verificado empíricamente:
    aislado pasa 21/21, junto a linescan falla.

    Deliberadamente NO se resetea el sub-área dentro de `set_read_mode()` del mock: en el SDK
    de Andor la configuración de `SetImage` persiste hasta que se la cambia, así que hacer que
    el mock la olvide al cambiar de modo reintroduciría una divergencia de paridad con el
    hardware — exactamente el problema que el cambio del mock vino a arreglar. La fuga es un
    problema de aislamiento de tests y se resuelve en la capa de tests.

    Sólo actúa si el singleton ya existe, para no instanciar el mock (ni imprimir su banner)
    en los cientos de tests que no usan la cámara.
    """
    from pyspectrum.drivers import andor_ccd_driver as drv

    cam = getattr(drv, "_andor_instance", None)
    attrs = ("_read_mode", "_image_vstart", "_image_vend")
    snapshot = {a: getattr(cam, a) for a in attrs if cam is not None and hasattr(cam, a)}
    yield
    cam_after = getattr(drv, "_andor_instance", None)
    if cam_after is not None and cam_after is cam:
        for a, v in snapshot.items():
            setattr(cam_after, a, v)


@pytest.fixture(autouse=True)
def _purge_deleted_pyqtgraph_views():
    """Quita del registro global de pyqtgraph las vistas cuyo objeto C++ ya se destruyó.

    `ViewBox.NamedViews` (un `WeakValueDictionary`) conserva la entrada mientras viva el envoltorio
    de Python. Si un test destruye un `ImageView` sin cerrarlo y el envoltorio queda en un ciclo que
    el recolector todavía no juntó, la entrada sobrevive al objeto C++; el siguiente `ViewBox` con
    nombre que se registra llama a `updateAllViewLists()`, que invoca `window()` sobre la vista
    muerta y lanza "wrapped C/C++ object of type ViewBox has been deleted". Que ocurra o no depende
    del momento en que corre el recolector, así que agregar tests *antes* en el orden de colección lo
    hace aparecer: al sumarse `DEC-038`, `test_slider_and_spinbox_sync` pasó a fallar de forma
    reproducible en la suite completa y a pasar aislado (verificado: el mismo prefijo de la suite
    pasa sin `test_prompt_corpus_integrity.py`, que no usa Qt).

    Es un problema de aislamiento de tests y se resuelve en la capa de tests, como
    `_isolate_spectroscopy_context` (`DEC-026`) y `_isolate_andor_mock_geometry` (`DEC-030`). Sólo
    actúa si pyqtgraph ya está importado, para no cargar Qt en los tests que no lo usan.
    """
    vb_module = sys.modules.get("pyqtgraph.graphicsItems.ViewBox.ViewBox")
    if vb_module is not None:
        from PyQt6 import sip
        view_box = vb_module.ViewBox
        for name, view in list(view_box.NamedViews.items()):
            if sip.isdeleted(view):
                view_box.NamedViews.pop(name, None)
        for view in list(view_box.AllViews.keys()):
            if sip.isdeleted(view):
                view_box.AllViews.pop(view, None)
    yield


# ------------------------------------------------------------------------------
# Cobertura de fuentes (DEC-038): una advertencia con sección propia, que nunca bloquea
# ------------------------------------------------------------------------------
# El investigador decidió que el test de cobertura de marcas de fuente sólo advierta
# (`RESPUESTAS_INVESTIGADOR.md`, "R3 — Ronda 2 del verificador", punto 4). Un `warnings.warn`
# quedaría agrupado y truncado en el resumen de warnings, `--disable-warnings` lo ocultaría y
# `-W error` lo convertiría en fallo sin querer; `xfail` significa "bug conocido". Por eso el test
# deja sus hallazgos en el stash de la sesión y este hook los imprime en una sección propia.
SOURCE_COVERAGE_KEY = pytest.StashKey[list]()
SOURCE_COVERAGE_TITLE = "Cobertura de fuentes (advertencia, no bloquea)"


@pytest.fixture
def source_coverage_report(request):
    """Lista donde `tests/test_source_marks.py` deja las advertencias de cobertura de los
    documentos adheridos; `pytest_terminal_summary` las imprime al final de la corrida."""
    return request.config.stash.setdefault(SOURCE_COVERAGE_KEY, [])


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    findings = config.stash.get(SOURCE_COVERAGE_KEY, None)
    if findings is None:  # el test de cobertura no corrió en esta sesión
        return
    terminalreporter.write_sep("=", SOURCE_COVERAGE_TITLE)
    if not findings:
        terminalreporter.write_line(
            "Sin advertencias en los documentos adheridos (tools/source_marks.py::ADHERED_DOCUMENTS).")
        return
    for finding in findings:
        terminalreporter.write_line(finding)
    terminalreporter.write_line(
        f"{len(findings)} advertencia(s). No hacen fallar el suite: se resuelven marcando la cifra "
        "o anotándola en el trailer Fuentes-verificadas del commit (CLAUDE.md §9).")


@pytest.fixture(scope="session")
def app():
    """QApplication compartida para toda la sesión de pytest. Requerida por
    test_shutter_alignment_and_heartbeat.py::test_watchdog_callback_and_ui_sync /
    test_ui_alignment_mode_selection, que la reciben como parámetro de test — sin este
    fixture, pytest los rechazaba con 'fixture app not found' (2 errores reproducibles
    en toda corrida de la suite completa, ver DECISION_LOG.md). Reutiliza la instancia de
    QApplication ya existente si otro módulo de test la creó primero a nivel de módulo
    (patrón dominante en el resto de la suite), en vez de crear una segunda."""
    from PyQt6.QtWidgets import QApplication
    instance = QApplication.instance() or QApplication(sys.argv)
    yield instance
