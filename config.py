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
import sys
import logging
import threading
import time
from pathlib import Path

# Silenciar advertencia benigna de registro de pipython (GCSTranslator en Windows)
logging.getLogger("PIlogger").setLevel(logging.ERROR)
logging.getLogger("pipython").setLevel(logging.ERROR)

# ── Registro de Rutas del Proyecto en sys.path ─────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
_venv_site = BASE_DIR / ".venv" / "Lib" / "site-packages"
if _venv_site.exists() and sys.version_info[:2] == (3, 13):
    if str(_venv_site) not in sys.path:
        sys.path.insert(0, str(_venv_site))

for sub in [BASE_DIR, BASE_DIR / "core", BASE_DIR / "modules", BASE_DIR / "analysis"]:
    sub_str = str(sub)
    if sub_str not in sys.path:
        sys.path.insert(0, sub_str)

# ── Modo seguro ───────────────────────────────────────────────────────────────
SAFE_MODE: bool = os.getenv("PYPRINTING_SAFE", "0") == "1"
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
PI_STAGE_RANGE_UM = 100.0          # recorrido X e Y en lazo cerrado
# Recorrido Z en lazo cerrado (DEC-036). La platina declarada es una PI P-517.3CD, cuya hoja de
# datos da 100 x 100 x 20 µm; antes se acotaba Z a 100 µm como X e Y. Se adopta la cota más
# restrictiva hasta confirmar con el propio controlador (qTMN/qTMX, prueba BANCO-17): un límite
# más estricto sólo puede rechazar movimientos, nunca dañar nada.
PI_Z_RANGE_UM = 20.0
PI_AXIS_RANGE_UM = {1: PI_STAGE_RANGE_UM, 2: PI_STAGE_RANGE_UM, 3: PI_Z_RANGE_UM}


def clamp_axis_um(axis: int, value: float) -> float:
    """Acota una coordenada al recorrido físico de su eje (1 = X, 2 = Y, 3 = Z)."""
    return max(0.0, min(PI_AXIS_RANGE_UM.get(int(axis), PI_STAGE_RANGE_UM), float(value)))
PI_SERVO_TIME = 50e-6

# ── NI-DAQ ────────────────────────────────────────────────────────────────────
NIDAQ_DEVICE        = "Dev1"
RATE_SINGLE_CHANNEL = 1.25e6
RATE_MULTICHANNEL   = 1.0e6

SHUTTERS         = ["532 nm (green)", "637 nm (red)", "592 nm (yellow)", "808 nm (IR)"]
SHUTTER_CHANNELS = [11, 8, 9, 10]
SHUTTER_POLARITY = {SHUTTERS[0]: False, SHUTTERS[1]: True, SHUTTERS[2]: True, SHUTTERS[3]: True}

FLIPPER_532_CHAN = 7
FLIPPER_AO_UP   = "Dev1/ao0"
FLIPPER_AO_DOWN = "Dev1/ao1"

PD_CHAN_BS    = 6
PD_CHANNELS   = {SHUTTERS[0]: 0, SHUTTERS[1]: 2, SHUTTERS[2]: 1, SHUTTERS[3]: 3, "BS": PD_CHAN_BS}
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


# ── Espectrómetro Andor Shamrock & Cámara CCD/EMCCD ───────────────────────────
ANDOR_FLIP_Y_IMAGE: bool = True     # Inversión vertical activa por defecto (corrige telescopio Czerny-Turner/Flipper)
ANDOR_FLIP_X_IMAGE: bool = False    # Inversión horizontal
ANDOR_DEFAULT_READ_MODE: int = 4    # 0: FVB, 1: Single Track, 4: Image 2D
SHAMROCK_USE_FACTORY_EEPROM: bool = True  # Calibración cúbica certificada de EEPROM
SHAMROCK_SLIT_CENTER_PIXEL_X: float = 501.0  # Pixel X central de referencia donde enfoca el slit sobre el sensor CCD

# ══════════════════════════════════════════════════════════════════════════════
#  PARÁMETROS Y VALORES TÍPICOS DE CONFIGURACIÓN (TYPICAL VALUES)
# ══════════════════════════════════════════════════════════════════════════════

# ── Confocal (`confocal.py`) ─────────────────────────────────────────────────
DEFAULT_CONFOCAL_RANGE_X        = 2.0     # µm campo de visión X
DEFAULT_CONFOCAL_RANGE_Y        = 2.0     # µm campo de visión Y
DEFAULT_CONFOCAL_PIXELS_X       = 34      # px resolución X
DEFAULT_CONFOCAL_PIXELS_Y       = 34      # px resolución Y
DEFAULT_CONFOCAL_FILTER_PERCENT = 30.0    # % umbral de filtro de fondo
DEFAULT_DRIFT_TOTAL_MINUTES     = 20.0    # min tiempo total de medición de deriva
DEFAULT_DRIFT_REFRESH_SECONDS   = 40.0    # s intervalo de refresco de deriva

# ── Trace & Power in BS (`trace.py`) ─────────────────────────────────────────
DEFAULT_TRACE_STEPS_BEFORE      = 10      # puntos promedio pre-umbral
DEFAULT_TRACE_STEPS_AFTER       = 10      # puntos promedio post-umbral
DEFAULT_POWER_BS_HIGH_MW        = 3.3     # mW medidos comercialmente en nivel alto
DEFAULT_POWER_BS_LOW_MW         = 1.0     # mW medidos comercialmente en nivel bajo
DEFAULT_POWER_BS_INTERCEPT      = 0.0     # mW intersección de calibración
DEFAULT_POWER_BS_SLOPE          = 3.0     # mW/V pendiente de calibración

# ── Nanopositioning PI (`nanopositioning.py`) ────────────────────────────────
DEFAULT_NANO_STEP_XY            = 1.0     # µm paso relativo XY
DEFAULT_NANO_STEP_Z             = 0.2     # µm paso relativo Z
DEFAULT_NANO_GOTO_X             = 50.0    # µm coordenada inicial Go to X
DEFAULT_NANO_GOTO_Y             = 50.0    # µm coordenada inicial Go to Y
DEFAULT_NANO_GOTO_Z             = 10.0    # µm coordenada inicial Go to Z

# ── Regímenes de Coordenadas de Platina PI ────────────────────────────────────
REGIME_LEGACY                   = "legacy"      # Ejes brutos PI: x=Eje 1, y=Eje 2
REGIME_LASER_REF                = "laser_ref"   # Referencia spot láser: Right=Eje 2 (+), Up=Eje 1 (-)
REGIME_SAMPLE_REF               = "sample_ref"  # Referencia muestra: Right=Eje 2 (-), Up=Eje 1 (+)
DEFAULT_COORDINATE_REGIME       = REGIME_LEGACY

# ── Impresión y Dímeros (`measurements.py`) ──────────────────────────────────
DEFAULT_GRID_NPS_COL            = 4       # número de filas/partículas por columna
DEFAULT_GRID_COLS               = 4       # número de columnas de la grilla
DEFAULT_GRID_DIST_NP            = 3.0     # µm distancia entre partículas en una columna
DEFAULT_GRID_DIST_COL           = 3.0     # µm distancia entre columnas
DEFAULT_PRINTING_UMBRAL         = 1.2     # salto multiplicativo de intensidad (120%)
DEFAULT_PRINTING_UMBRAL_DOWN    = 0.0     # umbral inferior de desprendimiento
DEFAULT_PRINTING_TMAX           = 20.0    # s tiempo máximo de exposición por celda
DEFAULT_PRINTING_STEPS_BEFORE   = 10      # puntos promediados pre-exposición
DEFAULT_PRINTING_STEPS_AFTER    = 10      # puntos promediados post-exposición
DEFAULT_PRINTING_AUTOFOCUS_EVERY = 2      # frecuencia de ciclos de autofoco Z (cada N celdas)
DEFAULT_PRINTING_SHIFT_X        = 0.0     # µm offset óptico X
DEFAULT_PRINTING_SHIFT_Y        = 0.0     # µm offset óptico Y
DEFAULT_DIMERS_DX               = 0.0     # µm separación nanométrica X entre dímeros
DEFAULT_DIMERS_DY               = 0.0     # µm separación nanométrica Y entre dímeros

# ── Cámara & Análisis de Imágenes ─────────────────────────────────────────────
DEFAULT_CAMERA_FPS              = 30      # FPS objetivo de captura en cámara
DEFAULT_TRACKPY_DIAMETER_PX     = 11      # px diámetro estimado de partícula para trackpy
DEFAULT_TRACKPY_SEPARATION_PX   = 8       # px separación mínima entre partículas
DEFAULT_TRACKPY_MINMASS         = 100.0   # masa mínima para detección trackpy


# ══════════════════════════════════════════════════════════════════════════════
#  MOCK PI  — misma interfaz que _PIController, sin hardware real
# ══════════════════════════════════════════════════════════════════════════════

try:
    from pipython import GCSError
except ImportError:
    class GCSError(Exception):
        """Stand-in cuando pipython no está instalado (entorno mock/test): permite que
        `except GCSError:` siga siendo válido sintácticamente en _PIController sin que
        pipython sea una dependencia dura. En este caso self._dev siempre es None, así que
        las ramas que lo capturan nunca se ejecutan de todas formas."""
        pass


STAGE_INTERLOCK = "Platina PI"


def _is_stage_comm_error(exc: Exception) -> bool:
    """True si la excepción es una falla de comunicación o de la interfaz, no un rechazo del
    firmware (DEC-036). pipython usa GCSError también para las fallas del bus: los códigos
    negativos son de la interfaz (COM_ERROR -1 ... COM_TIMEOUT -7, o PI_UNEXPECTED_RESPONSE
    -1004); los positivos son del controlador (p.ej. 7, posición fuera de límites). Cualquier
    excepción que no sea un GCSError es, por definición, una falla de bajo nivel. Un código
    ausente o no numérico (pipython lo acepta: GCSError("x").val == "x") no se puede clasificar
    y se trata como falla de comunicación, que es el lado seguro."""
    if not isinstance(exc, GCSError):
        return True
    try:
        return int(getattr(exc, "val", None)) < 0
    except (TypeError, ValueError):
        return True


def _close_shutters_for_stage(reason: str, trip: bool) -> None:
    """Cierra todos los obturadores por una falla de la platina y, si `trip`, activa el
    interlock que bloquea toda apertura hasta que el operador reconecte (DEC-036). Import
    diferido: core.nidaq importa este módulo."""
    try:
        from core import nidaq
        if trip:
            nidaq.trip_shutter_interlock(STAGE_INTERLOCK, reason)
        else:
            nidaq.close_all_shutters()
    except Exception as e:
        print(f"[PI] No se pudieron cerrar los obturadores tras la falla de la platina: {e}")


class _MockPI:
    """
    Simula la platina PI E-517.
    Mantiene una posición interna mutable para que qPOS() devuelva
    valores coherentes después de cada MOV().
    Todos los métodos de wave generator (WAV_LIN, WGO, etc.) son no-op.
    """
    _lock = threading.RLock()
    is_mock = True

    def __init__(self):
        with self._lock:
            self._pos       = {1: PI_HOME_POS[0],
                               2: PI_HOME_POS[1],
                               3: PI_HOME_POS[2]}
            self._connected = False

    def connect(self, serial: str = PI_SERIAL) -> bool:
        with self._lock:
            self._connected = True
            print(f"[PI MOCK] Conectada (serial ignorado: {serial})")
            return True

    def disconnect(self) -> None:
        with self._lock:
            self._connected = False
            print("[PI MOCK] Desconectada.")

    def is_physically_connected(self) -> bool:
        return False

    @property
    def connected(self) -> bool:
        with self._lock:
            return self._connected

    # ── Lectura de posición ───────────────────────────────────────────────────

    def qPOS(self, axes=None):
        """Devuelve posición actual como dict con claves string '1','2','3'."""
        with self._lock:
            return {"1": self._pos[1], "2": self._pos[2], "3": self._pos[3]}

    def qONT(self, axes=None):
        """Siempre 'on target' — no hay movimiento real que esperar."""
        if isinstance(axes, int):
            return {axes: True}
        axes = axes or PI_AXES
        return {a: True for a in axes}

    # ── Movimiento ────────────────────────────────────────────────────────────

    def MOV(self, axes, targets):
        with self._lock:
            if isinstance(axes, int):
                axes    = [axes]
                targets = [targets]
            axes = list(axes)
            targets = list(targets)
            clamped_any = False
            for i, (ax, tg) in enumerate(zip(axes, targets)):
                clamped = clamp_axis_um(ax, tg)
                if clamped != float(tg):
                    clamped_any = True
                targets[i] = clamped
            if clamped_any:
                print(f"[PI Driver Clamped] MOV solicitado fuera de rango, acotado por eje {PI_AXIS_RANGE_UM} µm: {dict(zip(axes, targets))}")
            for ax, tg in zip(axes, targets):
                if ax in self._pos:
                    self._pos[ax] = round(float(tg), 4)
            print(f"[PI MOCK] MOV {dict(zip(axes, targets))}")
            return True

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
    Singleton real / resiliente: envuelve GCSDevice con conexión idempotente, thread-safe (RLock)
    y tolerancia a fallas.
    Si la platina está desconectada o apagada, opera en modo virtual transparente
    sin arrojar excepciones fatales que bloqueen el inicio de la aplicación.
    Permite conexión y desconexión segura en caliente (Hot-Plug).
    """
    _lock = threading.RLock()
    is_mock = False

    def __init__(self):
        self._dev = None
        self._connected = False
        self._isolated = False
        self._last_error = ""
        self._idn = ""          # leído una sola vez al conectar (DEC-036: sin *IDN? en cada lectura)
        self._pos = {1: float(PI_HOME_POS[0]),
                     2: float(PI_HOME_POS[1]),
                     3: float(PI_HOME_POS[2])}
        try:
            from pipython import GCSDevice
            self._dev = GCSDevice()
        except Exception as e:
            print(f"[PI] pipython no disponible: {e}")
            self._dev = None

    def is_physically_connected(self) -> bool:
        """Comprueba si la platina física está verdaderamente en línea. NO envía *IDN? por
        el bus USB en cada llamada (root cause de saturación del buffer serie mientras la
        platina se desplaza, ver DEC-011): usa GCSDevice.IsConnected(), una consulta de
        estado del lado del host sin tráfico hacia el controlador, cuando está disponible."""
        with self._lock:
            if not self._connected or self._isolated or self._dev is None:
                return False
            try:
                if hasattr(self._dev, "IsConnected"):
                    return bool(self._dev.IsConnected())
                # Fallback si esta versión de pipython no expone IsConnected(): confiar en
                # el estado en memoria en vez de sondear con qIDN().
                return self._connected
            except Exception as e:
                # Misma política que el resto de las fallas de comunicación (DEC-036): antes
                # sólo se apagaba _connected, sin cerrar los obturadores ni bloquear aperturas.
                self._stage_fault(f"IsConnected() falló ({e})")
                return False

    def connect(self, serial: str = PI_SERIAL) -> bool:
        import time
        with self._lock:
            # 1. Si ya figuraba conectada, verificar salud con consulta real a la controladora
            if self._connected and not self._isolated and self._dev is not None:
                try:
                    idn = self._dev.qIDN().strip()
                    if idn and "Virtual" not in idn:
                        return True
                except Exception:
                    print("[PI] Conexión física previa interrumpida. Reintentando...")
                    self._connected = False

            # 2. Inicializar o limpiar instancia GCSDevice
            if self._dev is None:
                try:
                    from pipython import GCSDevice
                    self._dev = GCSDevice()
                except Exception as e:
                    print(f"[PI] No se puede conectar: pipython no disponible ({e}).")
                    return False
            else:
                try:
                    self._dev.CloseConnection()
                except Exception:
                    pass

            try:
                # 3. Auto-enumerar controladores USB PI conectados si están disponibles
                conn_target = serial
                try:
                    devices = self._dev.EnumerateUSB()
                    if devices:
                        print(f"[PI] Dispositivos USB PI detectados en sistema: {devices}")
                        matched = [d for d in devices if serial in str(d) or str(d) in serial]
                        if matched:
                            conn_target = matched[0]
                        else:
                            conn_target = devices[0]
                        print(f"[PI] Usando identificador USB: '{conn_target}'")
                except Exception as enum_err:
                    print(f"[PI] Aviso al enumerar USB PI: {enum_err}")

                # 4. Conectar al controlador seleccionado. Antes de mandar la platina a home,
                # cerrar todos los obturadores: el home mueve decenas de µm (DEC-036).
                self._dev.ConnectUSB(conn_target)
                _close_shutters_for_stage("conexión de la platina (home)", trip=False)
                self._dev.SVO(PI_AXES, [True] * 3)
                self._dev.VCO(PI_AXES, [False] * 3)
                self._dev.MOV(PI_AXES, PI_HOME_POS)
                t_start = time.time()
                while not all(self._dev.qONT(PI_AXES).values()):
                    time.sleep(0.01)
                    if time.time() - t_start > 3.0:
                        break
                self._connected = True
                # Sincronizar posición leída
                try:
                    real_pos = self._dev.qPOS()
                    for k in (1, 2, 3):
                        if str(k) in real_pos:
                            self._pos[k] = float(real_pos[str(k)])
                        elif k in real_pos:
                            self._pos[k] = float(real_pos[k])
                except Exception:
                    pass
                try:
                    self._idn = self._dev.qIDN().strip()
                except Exception:
                    self._idn = "PI E-517"
                print(f"[PI] Conectada exitosamente: {self._idn}")
                self._last_error = ""
                # La reconexión es la acción explícita del operador que libera el interlock.
                try:
                    from core import nidaq
                    nidaq.clear_shutter_interlock(STAGE_INTERLOCK)
                except Exception:
                    pass
                return True
            except Exception as e:
                self._last_error = str(e)
                print(f"[PI] Platina no conectada o apagada (USB '{serial}'): {e}. Modo virtual activo.")
                self._connected = False
                return False

    @property
    def last_error(self) -> str:
        with self._lock:
            return getattr(self, "_last_error", "")

    def disconnect(self) -> None:
        import time
        with self._lock:
            if not self._connected or self._dev is None:
                self._connected = False
                return
            _close_shutters_for_stage("desconexión de la platina", trip=False)
            try:
                self._dev.MOV(PI_AXES, [0, 0, 0])
                time.sleep(0.05)
                self._dev.CloseConnection()
            except Exception as e:
                print(f"[PI] Error al desconectar: {e}")
            self._connected = False
            print("[PI] Desconectada de forma segura.")

    @property
    def connected(self) -> bool:
        with self._lock:
            return self._connected and not self._isolated

    def set_isolated(self, isolated: bool):
        with self._lock:
            self._isolated = isolated

    def _retry_read(self, fn, max_retries: int = 2, delay_s: float = 0.02):
        """Reintenta una lectura (qPOS/qONT) hasta max_retries veces ante fallos transitorios
        de bus ocupado (p.ej. colisión con otra lectura durante un movimiento activo), sin
        tocar self._connected. Relanza la última excepción si todos los reintentos fallan —
        el llamador decide entonces cómo degradar (nunca desconectando, ver qPOS/qONT)."""
        import time
        last_exc = None
        for attempt in range(max_retries + 1):
            try:
                return fn()
            except Exception as e:
                last_exc = e
                if attempt < max_retries:
                    time.sleep(delay_s)
        raise last_exc

    def _stage_fault(self, reason: str) -> None:
        """Pérdida de comunicación con una platina que ESTABA conectada (DEC-036): se declara
        desconectada, se cierran los obturadores y se activa el interlock. No se reconecta:
        eso lo decide el operador desde el Dashboard, y connect() cierra los obturadores antes
        del home. El legado nunca se desconectaba; si pasa, es un evento a investigar."""
        self._connected = False
        self._last_error = reason
        print(f"[PI] FALLA DE COMUNICACIÓN: {reason}. Platina declarada desconectada; obturadores "
              f"cerrados y aperturas bloqueadas hasta reconectar desde el Dashboard.")
        _close_shutters_for_stage(f"falla de comunicación con la platina ({reason})", trip=True)

    def _virtual_ok(self) -> bool:
        """Sólo el aislamiento EXPLÍCITO del operador permite operar la platina en virtual."""
        return self._isolated

    def qPOS(self, axes=None):
        with self._lock:
            if self._connected and not self._isolated and self._dev is not None:
                try:
                    real = self._retry_read(lambda: self._dev.qPOS(axes))
                    for k in (1, 2, 3):
                        if str(k) in real:
                            self._pos[k] = float(real[str(k)])
                        elif k in real:
                            self._pos[k] = float(real[k])
                    return real
                except Exception as e:
                    if _is_stage_comm_error(e):
                        self._stage_fault(f"qPOS falló tras reintentos ({e})")
                    else:
                        print(f"[PI] qPOS rechazado por firmware (GCSError {e}) — la conexión física se mantiene.")
            # Última posición conocida: es un valor en caché, nunca una lectura confirmada.
            return {"1": self._pos[1], "2": self._pos[2], "3": self._pos[3]}

    def qONT(self, axes=None):
        """Estado on-target REAL. Ante cualquier falla devuelve False para todos los ejes: nunca
        se asume que la platina llegó (DEC-036; antes se asumía on-target y cualquier espera
        terminaba como si la platina hubiera llegado)."""
        with self._lock:
            if isinstance(axes, int):
                axes_list = [axes]
            else:
                axes_list = list(axes) if axes else list(PI_AXES)
            if self._connected and not self._isolated and self._dev is not None:
                try:
                    return self._retry_read(lambda: self._dev.qONT(axes))
                except Exception as e:
                    if _is_stage_comm_error(e):
                        self._stage_fault(f"qONT falló tras reintentos ({e})")
                    else:
                        print(f"[PI] qONT rechazado por firmware (GCSError {e}) — se informa no on-target.")
                return {a: False for a in axes_list}
            return {a: self._virtual_ok() for a in axes_list}

    def MOV(self, axes, targets):
        with self._lock:
            if isinstance(axes, int):
                axes_list = [axes]
                targets_list = [targets]
            else:
                axes_list = list(axes)
                targets_list = list(targets)

            # Clampeo preventivo obligatorio (CLAUDE.md §4): ninguna coordenada sale de este
            # driver fuera del recorrido de su eje (PI_AXIS_RANGE_UM: X e Y 100 µm, Z 20 µm),
            # sin importar si el llamador ya clampeó o no. Evita en la fuente el error GCS 7
            # ("position out of limits"). Nota (auditoría 2026-09-27): el -1004 que se citaba
            # antes acá es PI_UNEXPECTED_RESPONSE, no un error de límites.
            clamped_any = False
            for i, (ax, tg) in enumerate(zip(axes_list, targets_list)):
                clamped = clamp_axis_um(ax, tg)
                if clamped != float(tg):
                    clamped_any = True
                targets_list[i] = clamped
            if clamped_any:
                print(f"[PI Driver Clamped] MOV solicitado fuera de rango, acotado por eje {PI_AXIS_RANGE_UM} µm: {dict(zip(axes_list, targets_list))}")

            if self._connected and not self._isolated and self._dev is not None:
                try:
                    self._dev.MOV(axes_list, targets_list)
                except Exception as e:
                    if _is_stage_comm_error(e):
                        # Sin reconexión automática (DEC-036): una reconexión llama a connect(),
                        # que manda la platina a home a mitad de la rutina y con el láser abierto.
                        self._stage_fault(f"MOV falló ({e})")
                    else:
                        # Rechazo del firmware: la conexión sigue viva, el comando no se ejecutó.
                        print(f"[PI] MOV rechazado por firmware (GCSError {e}) — comando no ejecutado.")
                    return False
                for ax, tg in zip(axes_list, targets_list):
                    if ax in self._pos:
                        self._pos[ax] = round(float(tg), 4)
                return True
            if self._virtual_ok():
                for ax, tg in zip(axes_list, targets_list):
                    if ax in self._pos:
                        self._pos[ax] = round(float(tg), 4)
                print(f"[PI VIRTUAL] MOV {dict(zip(axes_list, targets_list))} (platina aislada por el operador)")
                return True
            # Platina desconectada y NO aislada: sin modo virtual silencioso en producción. No se
            # activa el interlock si nunca estuvo conectada (p.ej. una sesión sin platina); la
            # rutina que dependa del movimiento abortará al no confirmarse on-target.
            print(f"[PI] MOV rechazado: platina desconectada {dict(zip(axes_list, targets_list))}")
            return False

    def qIDN(self):
        """Identificación leída una vez al conectar. No consulta el bus: el *IDN? en cada lectura
        saturaba el USB y un solo fallo declaraba desconectada la platina (auditoría 2026-09-27)."""
        with self._lock:
            if self._connected and not self._isolated and self._dev is not None:
                return self._idn or "PI E-517"
            return "PI E-517 [Virtual/Desconectado]"

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        if self._connected and not self._isolated and self._dev is not None:
            try:
                attr = getattr(self._dev, name)
                if callable(attr):
                    def _locked_call(*args, **kwargs):
                        with self._lock:
                            return attr(*args, **kwargs)
                    return _locked_call
                return attr
            except AttributeError:
                pass

        # Si no está conectado o es no-op virtual
        def _noop_safe(*args, **kwargs):
            if name in ("qIDN",):
                return "PI E-517 [Virtual/Desconectado]"
            return None
        return _noop_safe


# ── Instancia global — el resto del código solo importa `pi` ─────────────────
pi: _MockPI | _PIController = _MockPI() if SAFE_MODE else _PIController()

STAGE_SETTLE_TIMEOUT_S = 5.0


def wait_on_target(axes=None, timeout_s: float = STAGE_SETTLE_TIMEOUT_S, poll_s: float = 0.01,
                   on_tick=None, stage=None) -> bool:
    """Espera a que el controlador CONFIRME on-target, con tope de tiempo (DEC-036).

    Devuelve True sólo con la confirmación real del lazo cerrado. Devuelve False si vence el
    tiempo, si la lectura falla o si la platina está desconectada (y no aislada por el
    operador): quien llama debe cerrar los obturadores y abortar, nunca seguir como si la
    platina hubiera llegado. `on_tick` se llama en cada vuelta (p.ej. heartbeat_shutter),
    para que una espera larga no agote el watchdog."""
    st = stage if stage is not None else pi
    axes = axes if axes is not None else PI_AXES
    t0 = time.time()
    while True:
        if (not getattr(st, "is_mock", False) and not getattr(st, "connected", True)
                and not getattr(st, "_isolated", False)):
            print(f"[PI] wait_on_target({axes}): platina desconectada — no se confirma la llegada.")
            return False
        try:
            state = st.qONT(axes)
        except Exception as e:
            print(f"[PI] wait_on_target({axes}): lectura qONT falló ({e}).")
            return False
        if state and all(state.values()):
            return True
        if on_tick is not None:
            try:
                on_tick()
            except Exception:
                pass
        if time.time() - t0 > timeout_s:
            print(f"[PI] wait_on_target({axes}): sin confirmación on-target en {timeout_s:.1f} s.")
            return False
        time.sleep(poll_s)

if SAFE_MODE:
    print("=" * 60)
    print("  MODO SEGURO ACTIVO — sin hardware físico conectado")
    print("  PI:     simulada  |  NI-DAQ: simulada  |  Cámara: sintética")
    print("=" * 60)
