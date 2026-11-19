# -*- coding: utf-8 -*-
"""La parada de emergencia en la interfaz: teclas, banner, Rearmar, controles de la grilla, "Cerrar todos",
PySpectrum y el satélite (C-01 Ronda 4, R4-17 fase 4c; `ronda4_conciliacion_fase4c.md`; DEC-049).

Contrato:
11. `Ctrl+E` y `F12` desde cualquier ventana del proceso (también con un `QMessageBox` y un `QFileDialog` no nativo
    abiertos) disparan la parada una vez por pulsación;
12. en modo satélite hay una sola parada: la tecla en la ventana de PySpectrum o en la de PyPrinting detiene los dos,
    y una apertura de una rutina de PyPrinting falla;
13. el banner dice "confirmada" sólo con el cierre del cerrador; sin él (placa tomada), nombra la llave del láser;
14. Rearmar espera a que todo esté quieto, informa a quién espera y, al vencer el plazo, por qué no rearmó;
15. los controles de la grilla siguen su estado; 16. `F2` pausa la grilla que corre y, si no corre, deja pasar la
    tecla; 17. el rótulo de "Cerrar todos" dice que la grilla sigue; 18. la grilla toma la sesión de hardware al
    arrancar y la suelta al terminar; 19. la cuenta y el aviso de un nodo interrumpido;
20. la sesión de PySpectrum como participante: la cámara en un hilo, los Live en el hilo GUI, y la sesión de la
    grilla de PyPrinting no se suelta con la parada.
"""
import os
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYPRINTING_SAFE", "1")

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QFileDialog, QMainWindow, QMessageBox, QWidget

from core import estop_state, nidaq
from core.emergency_stop import get_emergency_coordinator
from core.ui import emergency_keys
from core.ui.emergency_keys import get_emergency_bridge, install_emergency_key_filter

_app = QApplication.instance() or QApplication(["pytest"])
_KEEP_ALIVE = []


def _pump(cond=lambda: False, timeout=1.0):
    t_end = time.monotonic() + timeout
    while time.monotonic() < t_end:
        QApplication.processEvents()
        if cond():
            return True
        time.sleep(0.005)
    QApplication.processEvents()
    return bool(cond())


def _close_windows(monkeypatch, windows, gui=None, threads=()):
    """Oculta las ventanas y detiene los hilos del satélite. No las cierra: la secuencia de cierre de PySpectrum
    cierra la cámara y el Shamrock simulados, que son del proceso y los usan los tests siguientes."""
    if gui is not None:
        gui.closeSignal.emit()
        gui.hide()
    for t in threads:
        t.quit()
    for t in threads:
        t.wait(3000)
    for w in windows:
        w.hide()
    _pump(timeout=0.3)
    if estop_state.is_active():
        _rearm_now()


class _Counter:
    def __init__(self):
        self.calls = []

    def trigger(self, source):
        self.calls.append(source)
        return 1


@pytest.fixture
def key_filter(monkeypatch):
    flt = install_emergency_key_filter(_app)
    counter = _Counter()
    monkeypatch.setattr(flt, "_coordinator", counter)
    return flt, counter


def _rearm_now():
    coordinator = get_emergency_coordinator()
    gen = estop_state.generation()
    assert _pump(lambda: coordinator.rearm_check(gen).ok, timeout=3.0), coordinator.rearm_check(gen)
    assert coordinator.rearm(gen)[0]


# ── 11. Las teclas, desde cualquier ventana ─────────────────────────────────────────────────

def test_estop_keys_fire_once_per_press_from_every_window(key_filter):
    flt, counter = key_filter
    main = QMainWindow(); main.show()
    other = QWidget(); other.show()
    box = QMessageBox(QMessageBox.Icon.Warning, "Aviso", "Un modal abierto", parent=main)
    box.setModal(True); box.show()
    dlg = QFileDialog(main, "Guardar")
    dlg.setOption(QFileDialog.Option.DontUseNativeDialog, True)
    dlg.setModal(True); dlg.show()
    _KEEP_ALIVE.extend([main, other, box, dlg])
    _pump()
    try:
        windows = [main, other, box, dlg]
        for w in windows:
            for key, mod in ((Qt.Key.Key_F12, Qt.KeyboardModifier.NoModifier),
                             (Qt.Key.Key_E, Qt.KeyboardModifier.ControlModifier)):
                before = len(counter.calls)
                QTest.keyClick(w, key, mod)
                _pump()
                assert len(counter.calls) - before == 1, (w, key)
        assert set(counter.calls) == {emergency_keys.ESTOP_SOURCE_KEY}
    finally:
        for w in (dlg, box, other, main):
            w.close()


# ── 12. El satélite: una sola parada ────────────────────────────────────────────────────────

def test_satellite_mode_has_a_single_stop_for_both_programs(monkeypatch):
    import app as pyprinting_app
    from pyspectrum.window import PySpectrumWindow
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.No))
    win = PySpectrumWindow()
    gui, worker, threads = pyprinting_app.create_app_satellite()
    _KEEP_ALIVE.extend([win, gui, worker])
    win.show(); gui.show()
    _pump()
    try:
        assert getattr(_app, "_emergency_key_filter", None) is not None
        QTest.keyClick(gui, Qt.Key.Key_E, Qt.KeyboardModifier.ControlModifier)   # desde la ventana de PyPrinting
        _pump()
        gen = estop_state.generation()
        assert estop_state.is_active()
        QTest.keyClick(win, Qt.Key.Key_F12)                                       # y desde la de PySpectrum
        _pump()
        assert estop_state.generation() == gen                                    # un solo episodio
        import measurements                                                        # el módulo de las rutinas
        assert measurements.open_shutter(nidaq.SHUTTERS[0]) is False              # una apertura de PyPrinting falla
        from pyspectrum.modules.hardware_session import hardware_session
        assert hardware_session.is_emergency_stopped                              # PySpectrum también la ve
        _rearm_now()
    finally:
        _close_windows(monkeypatch, [win], gui, threads)


# ── 13. El banner ───────────────────────────────────────────────────────────────────────────

def test_the_banner_says_confirmed_only_with_the_closer_result():
    from core.ui.emergency_widgets import EmergencyBanner
    banner = EmergencyBanner(detail_provider=lambda: "La grilla quedó DETENIDA en el nodo 17.")
    _KEEP_ALIVE.append(banner)
    get_emergency_coordinator().trigger("test")
    assert _pump(lambda: "confirmada" in banner.state_text(), timeout=1.0), banner.state_text()
    assert "nodo 17" in banner.state_text() and banner.btn_rearm.isEnabled() and banner.is_active()
    _rearm_now()
    _pump(lambda: not banner.is_active())
    assert "Rearmado" in banner.state_text() and not banner.btn_rearm.isEnabled()


def test_the_banner_names_the_laser_key_when_the_board_is_held():
    from core.ui.emergency_widgets import EmergencyBanner
    banner = EmergencyBanner()
    _KEEP_ALIVE.append(banner)
    held, release = threading.Event(), threading.Event()

    def hang():
        with nidaq._nidaq_lock:
            held.set()
            release.wait(5.0)
    th = threading.Thread(target=hang, daemon=True)
    th.start()
    assert held.wait(1.0)
    try:
        get_emergency_coordinator().trigger("test")
        assert _pump(lambda: "llave del láser" in banner.state_text(), timeout=1.0), banner.state_text()
        assert "SIN CONFIRMAR" in banner.state_text() and not banner.btn_rearm.isEnabled()
    finally:
        release.set()
        th.join(2.0)
    assert _pump(lambda: "confirmada" in banner.state_text(), timeout=2.0)       # la placa volvió: confirma
    _rearm_now()


def test_the_banner_does_not_wait_for_the_closer_to_report(monkeypatch):
    """Si el cerrador quedó trabado dentro del driver y no informa nada, el plazo propio del banner (0.5 s) lo
    detecta igual (instrumentación §1.4)."""
    from core.ui.emergency_widgets import EmergencyBanner
    monkeypatch.setattr(nidaq, "_closer_attempt", lambda: None)
    banner = EmergencyBanner()
    _KEEP_ALIVE.append(banner)
    get_emergency_coordinator().trigger("test")
    assert not _pump(lambda: "llave del láser" in banner.state_text(), timeout=0.3)   # todavía no venció
    assert _pump(lambda: "llave del láser" in banner.state_text(), timeout=1.0), banner.state_text()
    monkeypatch.undo()
    with nidaq._closer_cv:
        nidaq._closer_cv.notify_all()
    _rearm_now()


def test_the_pyspectrum_button_is_the_process_stop_without_a_modal(monkeypatch):
    from pyspectrum.window import PySpectrumWindow
    modals = []
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: modals.append(a)))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.No))
    win = PySpectrumWindow()
    _KEEP_ALIVE.append(win)
    win.btn_estop.click()
    assert estop_state.is_active() and modals == []          # respuesta 2: sólo el banner
    assert _pump(lambda: "confirmada" in win.estop_banner.state_text(), timeout=1.0)
    assert win.btn_reset_estop.isEnabled()
    win.btn_reset_estop.click()                              # el Rearmar del proceso
    assert _pump(lambda: not estop_state.is_active(), timeout=2.0)
    _close_windows(monkeypatch, [win])


# ── 14. Rearmar ─────────────────────────────────────────────────────────────────────────────

class _Busy:
    def __init__(self):
        self.name, self.quiet = "grilla de prueba", False

    def on_emergency_stop(self, gen): pass
    def is_quiescent(self): return self.quiet
    def on_rearmed(self, gen): pass
    def is_running(self): return False


def test_rearm_waits_for_the_routines_and_reports_who(monkeypatch):
    from core.ui.emergency_widgets import EmergencyBanner
    p = _Busy()
    coordinator = get_emergency_coordinator()
    coordinator.register(p)
    banner = EmergencyBanner()
    _KEEP_ALIVE.append(banner)
    coordinator.trigger("test")
    assert _pump(lambda: banner.btn_rearm.isEnabled(), timeout=1.0)
    banner.btn_rearm.click()
    assert _pump(lambda: "grilla de prueba" in banner.state_text(), timeout=1.0), banner.state_text()
    assert estop_state.is_active()
    p.quiet = True
    assert _pump(lambda: not estop_state.is_active(), timeout=1.0)
    assert _pump(lambda: "Rearmado" in banner.state_text())


def test_rearm_gives_up_after_the_quiescence_deadline(monkeypatch):
    from core.ui.emergency_widgets import EmergencyBanner
    monkeypatch.setattr(emergency_keys, "ESTOP_QUIESCENCE_TIMEOUT_S", 0.3)
    p = _Busy()
    get_emergency_coordinator().register(p)
    banner = EmergencyBanner()
    _KEEP_ALIVE.append(banner)
    get_emergency_coordinator().trigger("test")
    assert _pump(lambda: banner.btn_rearm.isEnabled(), timeout=1.0)
    banner.btn_rearm.click()
    assert _pump(lambda: "no respondió" in banner.state_text(), timeout=2.0), banner.state_text()
    assert estop_state.is_active() and banner.btn_rearm.isEnabled()              # se puede volver a intentar
    p.quiet = True
    _rearm_now()


# ── 15, 18 y 19. El panel de impresión ──────────────────────────────────────────────────────

@pytest.fixture
def panel():
    import modules.measurements as meas
    fe = meas.Frontend("printing")
    be = meas.Backend(mode="printing")
    _KEEP_ALIVE.extend([fe, be])
    fe.make_connection(be)
    return fe, be


def test_the_grid_controls_follow_the_run_state(panel):
    from core.grid_state import GridRunState as S
    fe, be = panel
    expected = {S.IDLE: (True, False, True), S.RUNNING: (False, True, True), S.PAUSED: (True, False, True),
                S.STOPPED: (False, False, False)}
    for state, (play, pause, nxt) in expected.items():
        be.run_state = state
        assert (fe.play_button.isEnabled(), fe.pause_button.isEnabled(), fe.next_button.isEnabled()) == \
               (play, pause, nxt), state
        if state == S.STOPPED:
            assert "DETENIDA" in fe.lbl_run_state.text()


def test_the_grid_takes_the_hardware_session_and_gives_it_back(panel, monkeypatch):
    from core.grid_state import GridRunState as S
    from pyspectrum.modules.hardware_session import hardware_session
    fe, be = panel
    started = []
    fe.gridSignal.connect(lambda: started.append(1))
    monkeypatch.setattr(fe, "_emit_parameters", lambda: None)
    hardware_session.acquire_session("Step & Glue")                    # una rutina de PySpectrum la tiene
    try:
        fe.play_button.click()
        assert started == [] and "Step & Glue" in fe.lbl_cut_notice.text()
    finally:
        hardware_session.release_session("Step & Glue")
    fe.play_button.click()
    assert started == [1] and hardware_session.current_owner.startswith("PyPrinting")
    be.run_state = S.RUNNING
    be.run_state = S.PAUSED
    be.run_state = S.STOPPED
    assert hardware_session.current_owner.startswith("PyPrinting")     # la conserva en pausa y detenida
    be.run_state = S.IDLE
    assert not hardware_session.is_busy


def test_the_countdown_and_the_interrupted_node_notice(panel):
    fe, be = panel
    be.countdownSignal.emit(18, time.time() + 2.0)
    _pump()
    assert "nodo 18" in fe.lbl_countdown.text()
    be.nodeInterruptedSignal.emit(17, "operator", 1.2)
    _pump()
    assert "Cerraste los obturadores en el nodo 17" in fe.lbl_cut_notice.text() and "nodo 18" in fe.lbl_cut_notice.text()


# ── 16. F2 ──────────────────────────────────────────────────────────────────────────────────

def test_f2_pauses_the_running_grid_and_otherwise_lets_the_key_through():
    from PyQt6.QtGui import QKeySequence, QShortcut
    flt = install_emergency_key_filter(_app)
    paused = []
    running = {"on": True}

    def handler():
        if running["on"]:
            paused.append(1)
            return True
        return False
    flt.add_pause_handler(handler)
    w = QMainWindow()
    w.show()
    _KEEP_ALIVE.append(w)
    window_f2 = []
    sc = QShortcut(QKeySequence("F2"), w)
    sc.activated.connect(lambda: window_f2.append(1))
    _pump()
    try:
        QTest.keyClick(w, Qt.Key.Key_F2)
        _pump()
        assert paused == [1] and window_f2 == []           # la grilla corría: la pausa, y el atajo no
        running["on"] = False
        QTest.keyClick(w, Qt.Key.Key_F2)
        _pump()
        assert paused == [1] and window_f2 == [1]          # sin grilla: la tecla sigue (la traza manual)
    finally:
        flt.remove_pause_handler(handler)
        w.close()


# ── 17. "Cerrar todos" con una grilla corriendo ─────────────────────────────────────────────

def test_the_close_all_label_says_the_grid_goes_on():
    from core.shutters import Frontend
    fe = Frontend()
    _KEEP_ALIVE.append(fe)
    assert fe.btn_close_all.text() == "Cerrar Todos"
    nidaq.set_routine_running("grilla impresión", True)
    assert _pump(lambda: fe.btn_close_all.text() == "Cerrar todos · la grilla sigue", timeout=1.5)
    assert "No detiene la grilla" in fe.btn_close_all.toolTip()
    nidaq.set_routine_running("grilla impresión", False)
    assert _pump(lambda: fe.btn_close_all.text() == "Cerrar Todos", timeout=1.5)


# ── 20. La sesión de PySpectrum como participante ───────────────────────────────────────────

def test_the_session_participant_does_the_camera_off_the_gui_thread_and_keeps_the_grid_session():
    from pyspectrum.drivers.andor_ccd_driver import get_andor_ccd
    from pyspectrum.modules.hardware_session import hardware_session
    cam = get_andor_ccd(force_mock=True)
    cam.set_emccd_gain(150)
    live_threads = []
    hardware_session.register_live_controller("prueba", lambda: live_threads.append(threading.current_thread().name))
    hardware_session.acquire_session("PyPrinting: grilla de impresión", auto_pause_live=False)
    try:
        get_emergency_coordinator().trigger("test")               # la tecla o el botón, no la API heredada
        assert _pump(lambda: hardware_session.is_quiescent() and live_threads, timeout=2.0)
        assert live_threads == [threading.main_thread().name]    # el Live, en el hilo GUI
        read = cam.get_emccd_gain()
        assert (read[1] if isinstance(read, (tuple, list)) else read) == 0
        assert hardware_session.last_estop_report.get("gain") == "0 releído"
        assert hardware_session.current_owner.startswith("PyPrinting")   # la grilla conserva su sesión
        assert hardware_session.is_emergency_stopped
        _rearm_now()
        assert not hardware_session.is_emergency_stopped
    finally:
        hardware_session._live_pause_callbacks.pop("prueba", None)
        hardware_session.release_session("PyPrinting: grilla de impresión")


def test_pyprinting_installs_the_process_filter_with_its_f2_handler_and_removes_it_on_close():
    """PyPrinting suelto o en el satélite suma su manejador de F2 al filtro del proceso, y lo saca al cerrar."""
    import app as pyprinting_app
    flt = install_emergency_key_filter(_app)
    before = list(flt._pause_handlers)
    gui, worker, threads = pyprinting_app.create_app_satellite()
    _KEEP_ALIVE.extend([gui, worker])
    try:
        added = [h for h in flt._pause_handlers if h not in before]
        assert len(added) == 1
        assert added[0]() is False                     # sin grilla corriendo no atiende F2
    finally:
        gui.closeSignal.emit()
        for t in threads:
            t.wait(3000)
    assert flt._pause_handlers == before


def test_queued_stop_work_does_not_land_on_a_routine_started_after_rearm():
    """Si se rearma antes de que el bucle atienda la cola, el trabajo encolado de esa parada (pausar los Live, soltar
    la sesión) no corre después sobre una rutina nueva."""
    from pyspectrum.modules.hardware_session import hardware_session
    coordinator = get_emergency_coordinator()
    gen = coordinator.trigger("test")                         # encola el trabajo de la interfaz, sin atenderlo
    t_end = time.monotonic() + 3.0
    while not coordinator.rearm_check(gen).ok and time.monotonic() < t_end:
        time.sleep(0.01)                                      # sin procesar eventos: la cola queda pendiente
    assert coordinator.rearm(gen)[0]
    assert hardware_session.acquire_session("Rutina nueva", auto_pause_live=False)
    try:
        _pump(timeout=0.3)                                    # ahora sí corre la cola
        assert hardware_session.current_owner == "Rutina nueva"
    finally:
        hardware_session.release_session("Rutina nueva")
