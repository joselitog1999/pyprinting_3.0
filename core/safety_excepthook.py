# -*- coding: utf-8 -*-
"""
safety_excepthook.py — Red de seguridad ante excepciones no manejadas (DEC-036).
PyPrinting 3.0 — UNSAM Nanofotónica

Con el `sys.excepthook` de fábrica, PyQt6 ABORTA el proceso ante una excepción no manejada
dentro de un slot o de un método virtual de Qt (verificado en este proyecto el 2026-09-27).
Un aborto no ejecuta `atexit`, es decir, tampoco el cierre de emergencia de los obturadores,
y el watchdog muere con el proceso: un láser abierto quedaría abierto sin nada que lo vigile.

`install_safety_excepthook()` reemplaza ese comportamiento por uno seguro: registra el error,
cierra todos los obturadores y avisa, y el programa sigue vivo. PyQt6 no aborta cuando el
hook fue reemplazado. Cubre también las excepciones de hilos (`threading.excepthook`).

No es el mecanismo para manejar fallas conocidas (para la platina está el interlock de
`core.nidaq`); es la última barrera ante lo imprevisto.
"""
from __future__ import annotations

import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Callable

LOG_PATH = Path(__file__).resolve().parent.parent / "logs" / "excepciones_no_manejadas.log"

_callbacks: list[Callable[[str, str], None]] = []
_installed = False


def register_unhandled_exception_callback(fn: Callable[[str, str], None]) -> None:
    """fn(resumen, traza): para que una ventana muestre el aviso (se llama desde el hilo en el
    que ocurrió la excepción; la ventana debe reenviarlo a la GUI con una señal)."""
    if fn not in _callbacks:
        _callbacks.append(fn)


def unregister_unhandled_exception_callback(fn: Callable[[str, str], None]) -> None:
    if fn in _callbacks:
        _callbacks.remove(fn)


def _close_all_shutters() -> bool:
    try:
        from core.nidaq import close_all_shutters
        return bool(close_all_shutters())
    except Exception as e:  # noqa: BLE001 — la red de seguridad nunca debe lanzar
        try:
            print(f"[SEGURIDAD] No se pudo cerrar los obturadores: {e}", file=sys.stderr)
        except Exception:
            pass
        return False


def handle_unhandled_exception(exc_type, exc_value, exc_tb, origin: str = "hilo principal") -> None:
    """Registra, cierra todos los obturadores y avisa. Nunca lanza."""
    try:
        if exc_type is not None and issubclass(exc_type, KeyboardInterrupt):
            # Ctrl+C conserva su comportamiento habitual, pero sin dejar un láser abierto.
            _close_all_shutters()
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        trace = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        closed = _close_all_shutters()
        summary = (f"Excepción no manejada en {origin}: {getattr(exc_type, '__name__', exc_type)}: "
                   f"{exc_value}. Obturadores {'CERRADOS' if closed else 'SIN CONFIRMAR (ver panel)'}; "
                   f"el programa sigue en ejecución.")
        try:
            print(trace, file=sys.stderr)
            print(f"[SEGURIDAD] {summary}", file=sys.stderr)
        except Exception:
            pass
        try:
            LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(LOG_PATH, "a", encoding="utf-8") as f:
                f.write(f"==== {time.strftime('%Y-%m-%d %H:%M:%S')} — {summary}\n{trace}\n")
        except Exception:
            pass
        for cb in list(_callbacks):
            try:
                cb(summary, trace)
            except Exception:
                pass
    except Exception:
        pass


def install_safety_excepthook() -> None:
    """Instala la red de seguridad para el hilo principal y para los hilos de Python."""
    global _installed
    sys.excepthook = lambda t, v, tb: handle_unhandled_exception(t, v, tb, "hilo principal")
    threading.excepthook = lambda a: handle_unhandled_exception(
        a.exc_type, a.exc_value, a.exc_traceback, f"hilo '{getattr(a.thread, 'name', '?')}'")
    _installed = True


def is_installed() -> bool:
    return _installed
