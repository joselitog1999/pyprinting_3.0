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

# Una sola QApplication para toda la suite, creada acá CON argv. Si el primer test que la crea
# usa `QApplication([])`, QtWebEngine (el navegador del wiki científico) mata el proceso con
# código 127 sin traza al crear su vista: el argv vacío llega a Chromium. Pasó el 2026-09-28,
# cuando un archivo nuevo quedó primero en el orden alfabético. Con la aplicación creada acá,
# el `QApplication.instance() or QApplication(...)` de cada archivo reutiliza ésta.
from PyQt6.QtWidgets import QApplication

_QT_APP = QApplication.instance() or QApplication([sys.argv[0] if sys.argv else "pytest"])

import pytest


@pytest.fixture(autouse=True)
def _isolate_specular_interlock():
    """Cada test arranca con el interlock especular en PRIMER ORDEN y sin ganancia 0 confirmada.

    En producción el interlock nace DESCONOCIDO (falla cerrada, R2-inst §2.1-4): la ganancia EM queda
    bloqueada hasta que se lee el estado del Shamrock. Los tests que no tratan del orden cero usan el
    simulador sin publicar ese estado, así que acá se parte de primer orden. El arranque desconocido
    lo prueba `tests/test_specular_interlock.py` con una instancia nueva.
    """
    from pyspectrum.drivers import specular_interlock as si
    lock = si.get_interlock()
    lock.publish(si.FIRST_ORDER, "estado inicial de los tests (conftest)")
    lock.note_gain_reading(-1, 0)          # sin confirmación de ganancia 0
    # El simulador del Shamrock es un singleton: un test que lo dejó en orden cero o en el espejo
    # haría especular el destino del siguiente. Se lo vuelve a primer orden (red 1, 532 nm), sin
    # pasar por el interlock, para que coincida con el estado publicado.
    sh_mod = sys.modules.get("pyspectrum.drivers.shamrock_driver")
    inst = getattr(sh_mod, "_shamrock_instance", None) if sh_mod else None
    if inst is not None and isinstance(inst, sh_mod._MockShamrock):
        inst._raw_set_grating(sh_mod.GRATING_150_LINES)
        inst._raw_set_wavelength(532.0)
    yield
    lock.publish(si.FIRST_ORDER, "estado inicial de los tests (conftest)")
    lock.note_gain_reading(-1, 0)


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
# Excepciones no manejadas en slots de Qt: una falla del test, nunca un aborto de la suite
# ------------------------------------------------------------------------------
# Con el `sys.excepthook` de fábrica, PyQt6 aborta el proceso (qFatal, "Fatal Python error:
# Aborted") ante una excepción no manejada dentro de un slot o de un método virtual de Qt. En la
# suite eso mata la corrida entera sin traceback, en el test que haya llamado a processEvents()
# (visto repetidamente en test_sif_analyzer_gui.py::test_12, según el orden de los tests). Este
# hook registra la excepción y hace fallar el test en curso con su traceback, como la captura de
# excepciones de pytest-qt. No cambia el comportamiento de producción: la aplicación instala su
# propio hook (core/safety_excepthook.py, DEC-036). test_safety_excepthook.py guarda y restaura
# el hook vigente, y sus subprocesos no cargan este conftest.
import traceback as _traceback

_QT_UNHANDLED: list = []


def _record_unhandled_exception(exc_type, exc_value, exc_tb):
    _QT_UNHANDLED.append((exc_type, exc_value, exc_tb))


def pytest_configure(config):
    sys.excepthook = _record_unhandled_exception


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    _QT_UNHANDLED.clear()
    outcome = yield
    if _QT_UNHANDLED:
        caught = list(_QT_UNHANDLED)
        _QT_UNHANDLED.clear()
        detail = "\n".join("".join(_traceback.format_exception(*exc)) for exc in caught)
        outcome.force_exception(pytest.fail.Exception(
            f"{len(caught)} excepción(es) no manejada(s) en un slot de Qt durante el test "
            f"(con el hook de fábrica PyQt6 habría abortado toda la suite):\n{detail}",
            pytrace=False))


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


# ------------------------------------------------------------------------------
# Cierre del proceso de la suite: sin la destrucción nativa de las ventanas que quedan vivas
# ------------------------------------------------------------------------------
# Los tests dejan miles de ventanas de nivel superior vivas (fuga registrada en DEC-039, arreglo de
# fondo pendiente en la capa de tests). Desde el 2026-09-28 la suite completa terminaba, después de
# imprimir "N passed", con "Windows fatal exception: access violation" en el hilo principal sin
# ningún frame de Python (faulthandler), mientras Qt destruía esas ventanas al finalizar el
# intérprete; el único otro hilo vivo era el watchdog de obturadores. Cada archivo de test corre
# limpio por separado. Mitigación: al final de la sesión se detiene el watchdog y se termina el
# proceso con `os._exit`, con el código de salida real de pytest, para saltear esa destrucción. No
# cambia producción (una sola ventana, que se cierra normalmente) y no oculta fallas de los tests:
# se aplica después de que pytest calculó el resultado e imprimió el resumen.
_SESSION_EXIT_STATUS: list = []


def pytest_sessionfinish(session, exitstatus):
    _SESSION_EXIT_STATUS.append(int(exitstatus))


@pytest.hookimpl(trylast=True)
def pytest_unconfigure(config):
    if not _SESSION_EXIT_STATUS or os.environ.get("PYPRINTING_TEST_NORMAL_EXIT") == "1":
        return
    try:
        from core import nidaq
        nidaq._watchdog_active = False
        nidaq._watchdog_thread.join(timeout=1.0)
    except Exception:
        pass
    sys.stdout.flush()
    sys.stderr.flush()
    code = _SESSION_EXIT_STATUS[-1]
    if sys.platform == "win32":
        # `os._exit` todavía notifica a cada DLL cargada (DLL_PROCESS_DETACH), y Qt, con su aplicación
        # viva, abortaba ahí (0x80000003, código 3). TerminateProcess termina sin esas notificaciones.
        # Los tipos se declaran: sin ellos ctypes pasa el HANDLE de 64 bits como un int de 32 y la
        # llamada falla en silencio.
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.TerminateProcess.argtypes = (wintypes.HANDLE, wintypes.UINT)
        kernel32.TerminateProcess.restype = wintypes.BOOL
        kernel32.TerminateProcess(kernel32.GetCurrentProcess(), code)
    os._exit(code)


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
