# -*- coding: utf-8 -*-
"""Lo que la ventana de PySpectrum le pasa al coordinador de cierre (paso 13; R2-arq §3.3-6).

- Equipos, en orden: obturador del espectrómetro, Shamrock y cámara. El Shamrock va primero porque
  versiones viejas de `ShamrockClose` cerraban la cámara (lo confirma BANCO-23).
- Todas las rutinas que tienen hilo propio, incluido el barrido de Step & Glue (paso 11), que antes
  quedaba corriendo al cerrar.
- Step & Glue se detiene con tope: un hilo que no termina se informa, no se espera para siempre.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYPRINTING_SAFE", "1")

import pytest
from PyQt6 import QtCore, QtWidgets

from pyspectrum.modules import step_and_glue
from pyspectrum.modules.hardware_session import hardware_session
from pyspectrum.window import PySpectrumWindow


# Las ventanas con gráficos de pyqtgraph quedan vivas hasta el final de la sesión: si el recolector
# destruye una, su ViewBox con nombre queda registrado en pyqtgraph y rompe la próxima ImageView.
_KEEP_ALIVE = []


@pytest.fixture
def window(monkeypatch):
    hardware_session.clear_emergency()
    monkeypatch.setattr(QtWidgets.QMessageBox, "question",
                        lambda *a, **k: QtWidgets.QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QtWidgets.QMessageBox, "warning",
                        lambda *a, **k: QtWidgets.QMessageBox.StandardButton.Ok)
    win = PySpectrumWindow()
    _KEEP_ALIVE.append(win)
    yield win
    win.close()
    hardware_session.clear_emergency()


def test_devices_close_shamrock_first_and_every_threaded_routine_is_stopped(window):
    coord = window._build_shutdown([])
    assert [name for name, _ in coord._devices] == ["obturador del espectrómetro", "Shamrock", "cámara"]
    assert coord._mirror is not None                    # el espejo se baja, como en el legado
    routines = [name for name, _ in coord._routines]
    for expected in ("Live de exploración", "escaneo confocal", "Step & Glue", "escaneo lineal",
                     "hilo del escaneo lineal"):
        assert expected in routines, routines


def test_the_window_closes_once_and_reports_nothing_in_safe_mode(monkeypatch):
    hardware_session.clear_emergency()
    asked, warned = [], []
    monkeypatch.setattr(QtWidgets.QMessageBox, "question",
                        lambda *a, **k: asked.append(1) or QtWidgets.QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QtWidgets.QMessageBox, "warning", lambda *a, **k: warned.append(a[2]))
    win = PySpectrumWindow()
    _KEEP_ALIVE.append(win)
    win.close()
    win.close()                      # un segundo cierre no repite la secuencia ni vuelve a preguntar
    hardware_session.clear_emergency()
    assert asked == [1]
    assert warned == [], warned


class _FakeSatellite(QtCore.QObject):
    closeSignal = QtCore.pyqtSignal()

    def show(self):
        pass

    raise_ = activateWindow = close_from_host = show


def test_the_contrapropagante_is_opened_as_a_guest(window, monkeypatch):
    import contrapropagante
    seen = {}

    def fake_create(parent=None, host=None):
        seen["host"] = host
        return _FakeSatellite(), object(), []
    monkeypatch.setattr(contrapropagante, "create_contrapropagante_satellite", fake_create)
    window._open_contrapropagante()
    assert seen["host"] is not None and seen["host"].name == "PySpectrum 3.0"
    window._forget_contrapropagante()


class _StuckThread:
    def quit(self):
        pass

    def wait(self, ms):
        return False


def test_step_and_glue_shutdown_is_bounded():
    be = step_and_glue.Backend()
    assert be.shutdown().ok
    be._thread = _StuckThread()
    step = be.shutdown(timeout_ms=10)
    assert not step.ok and "no terminó" in step.detail
    be._thread = None
