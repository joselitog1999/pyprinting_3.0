# -*- coding: utf-8 -*-
"""
config.py — Constantes globales, singleton PI y modo seguro
PyPrinting — UNSAM Nanofotónica

SAFE_MODE = True  →  arranca sin hardware físico conectado.
  - La PI es reemplazada por _MockPI (posición fija, MOV = no-op)
  - La NI-DAQ es reemplazada por mocks en nidaq.py
  - La cámara genera frames sintéticos en camera.py

Activar via variable de entorno (recomendado):
    PYPRINTING_SAFE=1 python app.py

O directamente aquí para desarrollo:
    SAFE_MODE = True
"""
from __future__ import annotations
import os
import threading
from pathlib import Path

# ── Modo seguro ───────────────────────────────────────────────────────────────
#SAFE_MODE: bool = os.getenv("PYPRINTING_SAFE", "0") == "1"
SAFE_MODE= True
# ── Cámara ────────────────────────────────────────────────────────────────────
CAMERA_INDEX  = 1
CAMERA_WIDTH  = 1280
CAMERA_HEIGHT = 720
PIXEL_SIZE_UM = 0.059      # µm/pixel — actualizar si cambia el objetivo

# ── Láser 532 nm (NI-DAQ ao2) ────────────────────────────────────────────────
LASER_532_CHANNEL = "Dev1/ao2"
LASER_532_V_MIN   = 1.0
LASER_532_V_MAX   = 5.0

# ── Platina PI E-517 ──────────────────────────────────────────────────────────
PI_SERIAL    = "0119048050"
PI_AXES      = [1, 2, 3]
PI_HOME_POS  = [50.0, 50.0, 10.0]
PI_STAGE_RANGE_UM = 100.0
PI_SERVO_TIME = 50e-6

# ── NI-DAQ ────────────────────────────────────────────────────────────────────
NIDAQ_DEVICE        = "Dev1"
RATE_SINGLE_CHANNEL = 1.25e6
RATE_MULTICHANNEL   = 1.0e6

SHUTTERS         = ["532 nm (green)", "637 nm (red)", "592 nm (yellow)"]
SHUTTER_CHANNELS = [12, 11, 10]
SHUTTER_POLARITY = {SHUTTERS[0]: True, SHUTTERS[1]: False, SHUTTERS[2]: True}

FLIPPER_532_CHAN = 7
FLIPPER_AO_UP   = "Dev1/ao0"
FLIPPER_AO_DOWN = "Dev1/ao1"

PD_CHAN_BS    = 6
PD_CHANNELS   = {SHUTTERS[0]: 0, SHUTTERS[1]: 1, SHUTTERS[2]: 3, "BS": PD_CHAN_BS}
PD_CHANS_LIST = [0, 1, 2, 3, PD_CHAN_BS]
TRIGGER_CHANNELS = {"X": 4, "Y": 5, "Z": 3}

# ── Rutas ─────────────────────────────────────────────────────────────────────
_default_base = Path("C:/Users/PRINTING/Documents/Data_Printing")
_fallback_base = Path(os.path.expanduser("~/Documents/Data_Printing"))
if _default_base.exists():
    DEFAULT_DATA_PATH = _default_base
else:
    _fallback_base.mkdir(parents=True, exist_ok=True)
    DEFAULT_DATA_PATH = _fallback_base

_last_pos_default = Path("C:/Users/PRINTING/Desktop/PyPrinting/Last_position.txt")
if _last_pos_default.parent.exists():
    LAST_POS_FILE = _last_pos_default
else:
    LAST_POS_FILE = DEFAULT_DATA_PATH / "Last_position.txt"


# ══════════════════════════════════════════════════════════════════════════════
#  MOCK PI  — misma interfaz que _PIController, sin hardware real
# ══════════════════════════════════════════════════════════════════════════════

class _MockPI:
    """
    Simula la platina PI E-517.
    Mantiene una posición interna mutable para que qPOS() devuelva
    valores coherentes después de cada MOV().
    Todos los métodos de wave generator (WAV_LIN, WGO, etc.) son no-op.
    """
    def __init__(self):
        self._pos      = {1: PI_HOME_POS[0],
                          2: PI_HOME_POS[1],
                          3: PI_HOME_POS[2]}
        self._connected = False

    def connect(self, serial: str = PI_SERIAL) -> None:
        self._connected = True
        print(f"[PI MOCK] Conectada (serial ignorado: {serial})")

    def disconnect(self) -> None:
        self._connected = False
        print("[PI MOCK] Desconectada.")

    @property
    def connected(self) -> bool:
        return self._connected

    # ── Lectura de posición ───────────────────────────────────────────────────

    def qPOS(self, axes=None):
        """Devuelve posición actual como dict con claves string '1','2','3'."""
        return {"1": self._pos[1], "2": self._pos[2], "3": self._pos[3]}

    def qONT(self, axes=None):
        """Siempre 'on target' — no hay movimiento real que esperar."""
        if isinstance(axes, int):
            return {axes: True}
        axes = axes or PI_AXES
        return {a: True for a in axes}

    # ── Movimiento ────────────────────────────────────────────────────────────

    def MOV(self, axes, targets):
        if isinstance(axes, int):
            axes   = [axes]
            targets = [targets]
        for ax, tg in zip(axes, targets):
            if ax in self._pos:
                self._pos[ax] = round(float(tg), 4)
        print(f"[PI MOCK] MOV {dict(zip(axes, targets))}")

    # ── Wave generator (no-op) ────────────────────────────────────────────────

    def WOS(self, *a, **k):  pass
    def WGO(self, *a, **k):  pass
    def WGC(self, *a, **k):  pass
    def WTR(self, *a, **k):  pass
    def WAV_LIN(self, *a, **k): pass
    def WSL(self, *a, **k):  pass
    def TWC(self, *a, **k):  pass
    def CTO(self, *a, **k):  pass

    # ── Configuración (no-op) ─────────────────────────────────────────────────

    def SVO(self, *a, **k):  pass
    def VCO(self, *a, **k):  pass
    def ONL(self, *a, **k):  pass
    def DCO(self, *a, **k):  pass

    def qIDN(self): return "PI E-517 [MOCK]"

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        # Cualquier método desconocido → no-op con aviso
        def _noop(*a, **k):
            print(f"[PI MOCK] {name}() — no-op")
        return _noop


# ══════════════════════════════════════════════════════════════════════════════
#  SINGLETON PI  — real o mock según SAFE_MODE
# ══════════════════════════════════════════════════════════════════════════════

class _PIController:
    """
    Singleton real: envuelve GCSDevice con conexión idempotente y thread-safe (RLock).
    Solo se usa cuando SAFE_MODE = False.
    """
    _lock = threading.RLock()

    def __init__(self):
        try:
            from pipython import GCSDevice
            self._dev = GCSDevice()
        except Exception as e:
            print(f"[PI] pipython no disponible: {e}")
            self._dev = None
        self._connected = False

    def connect(self, serial: str = PI_SERIAL) -> None:
        import time
        with self._lock:
            if self._connected:
                return
            if self._dev is None:
                print("[PI] No se puede conectar: pipython no instalado.")
                return
            try:
                self._dev.ConnectUSB(serial)
                self._dev.SVO(PI_AXES, [True] * 3)
                self._dev.VCO(PI_AXES, [False] * 3)
                self._dev.MOV(PI_AXES, PI_HOME_POS)
                while not all(self._dev.qONT(PI_AXES).values()):
                    time.sleep(0.01)
                self._connected = True
                print(f"[PI] Conectada: {self._dev.qIDN().strip()}")
            except IOError as e:
                print(f"[PI] Error de conexión: {e}")

    def disconnect(self) -> None:
        import time
        with self._lock:
            if not self._connected or self._dev is None:
                return
            try:
                self._dev.MOV(PI_AXES, [0, 0, 0])
                time.sleep(0.1)
                self._dev.CloseConnection()
            except Exception as e:
                print(f"[PI] Error al desconectar: {e}")
            self._connected = False

    @property
    def connected(self) -> bool:
        with self._lock:
            return self._connected

    def qPOS(self, axes=None):
        with self._lock:
            return self._dev.qPOS(axes) if axes is not None else self._dev.qPOS()

    def qONT(self, axes=None):
        with self._lock:
            return self._dev.qONT(axes) if axes is not None else self._dev.qONT()

    def MOV(self, axes, targets):
        with self._lock:
            return self._dev.MOV(axes, targets)

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        if self._dev is None:
            raise RuntimeError(f"[PI] Dispositivo no inicializado (attr: {name})")
        attr = getattr(self._dev, name)
        if callable(attr):
            def _locked_call(*args, **kwargs):
                with self._lock:
                    return attr(*args, **kwargs)
            return _locked_call
        return attr


# ── Instancia global — el resto del código solo importa `pi` ─────────────────
pi: _MockPI | _PIController = _MockPI() if SAFE_MODE else _PIController()

if SAFE_MODE:
    print("=" * 60)
    print("  MODO SEGURO ACTIVO — sin hardware físico conectado")
    print("  PI:     simulada  |  NI-DAQ: simulada  |  Cámara: sintética")
    print("=" * 60)
