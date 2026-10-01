# -*- coding: utf-8 -*-
"""
procedure_background.py — El fondo de los procedimientos (R4-N; Rondas 1 a 3 aprobadas el 2026-09-30; DEC-040)

Contrato:
- **Una referencia de la medición:** la misma exposición, la misma configuración de la cámara y, por
  defecto, la misma cantidad de cuadros que la medición.
- **Condiciones** (`DarkConditions`): exposición, ganancia EM, amplificador, preamplificador, HS, VS, modo
  de lectura y sus parámetros, forma del cuadro y setpoint de temperatura. Sin luz, el fondo no depende de
  la red ni de λc: no son condiciones (por eso un solo fondo sirve a todas las ventanas de Step & Glue).
- **Se reutiliza** mientras las condiciones no cambien (`DarkStore`, sólo en memoria: al reiniciar, el
  sensor vuelve a enfriarse y se toma de nuevo).
- **Método:** "obturador cerrado" (por defecto; se cierra el del espectrómetro y se verifica) o "todo
  apagado" (el operador apaga la lámpara y los láseres; se rechaza si se cree que hay un láser abierto).
- **Se guarda aparte** de los datos: crudo y fondo por separado, nunca sólo la resta.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

METHOD_SHUTTER = "shutter"
METHOD_ALL_OFF = "all_off"
METHOD_LABELS = {METHOD_SHUTTER: "obturador cerrado", METHOD_ALL_OFF: "todo apagado"}
_DRV_SUCCESS = 20002
_SHAMROCK_SUCCESS = 20202


class DarkError(RuntimeError):
    """El fondo no se pudo tomar; el motivo va en el mensaje."""


class DarkMissing(DarkError):
    """Con "todo apagado" el fondo nunca se toma solo y no hay uno válido."""


# ── Condiciones ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class DarkConditions:
    exposure_s: Optional[float]
    em_gain: Optional[int]
    output_amplifier: Optional[int]
    preamp_index: Optional[int]
    hs_index: Optional[int]
    vs_index: Optional[int]
    read_mode: Optional[int]
    read_params: Optional[Tuple]
    shape: Optional[Tuple[int, ...]]
    temperature_setpoint_c: Optional[float]


_LABELS = {"exposure_s": "exposición", "em_gain": "ganancia EM", "output_amplifier": "amplificador",
           "preamp_index": "preamplificador", "hs_index": "velocidad HS", "vs_index": "velocidad VS",
           "read_mode": "modo de lectura", "read_params": "parámetros del modo de lectura",
           "shape": "forma del cuadro", "temperature_setpoint_c": "setpoint de temperatura"}
_READ_MODE_SINGLE_TRACK = 3
_READ_MODE_IMAGE = 4


def _value(fn):
    """Una lectura; si devuelve (código, valor), el valor sólo con código de éxito. Falla → None."""
    if fn is None:
        return None
    try:
        res = fn()
    except Exception:
        return None
    if isinstance(res, (tuple, list)) and len(res) == 2 and isinstance(res[0], int) and res[0] > 20000:
        return res[1] if res[0] == _DRV_SUCCESS else None
    return res


def _as_int(v):
    try:
        return None if v is None else int(v)
    except (TypeError, ValueError):
        return None


def _as_float(v):
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def read_conditions(camera, shape: Sequence[int], *, exposure_s: float,
                    read_mode: Optional[int] = None) -> DarkConditions:
    """Las condiciones de la medición. `exposure_s` es la de la medición (la que se pide), no la que la cámara
    tenga en ese momento; `read_mode`, si se da, es el modo con el que se va a medir."""
    g = lambda name: getattr(camera, name, None)   # noqa: E731
    mode = _as_int(read_mode) if read_mode is not None else _as_int(_value(g("get_read_mode")))
    params = None
    if mode == _READ_MODE_SINGLE_TRACK:
        tr = _value(g("get_single_track"))
        params = tuple(int(v) for v in tr) if tr is not None else None
    elif mode == _READ_MODE_IMAGE:
        im = _value(g("get_image_params"))
        params = tuple(int(v) for v in im) if im is not None else None
    return DarkConditions(
        exposure_s=float(exposure_s),
        em_gain=_as_int(_value(g("get_emccd_gain"))),
        output_amplifier=_as_int(_value(g("get_output_amplifier"))),
        preamp_index=_as_int(_value(g("get_preamp_gain_index"))),
        hs_index=_as_int(_value(g("get_hs_speed_index"))),
        vs_index=_as_int(_value(g("get_vs_speed_index"))),
        read_mode=mode, read_params=params,
        shape=tuple(int(v) for v in shape),
        temperature_setpoint_c=_as_float(_value(g("get_temperature_setpoint"))))


def differences(ref: DarkConditions, now: DarkConditions) -> List[str]:
    """Qué cambió respecto de `ref`, en palabras. Una lectura que ahora falla también invalida."""
    out = []
    for key, label in _LABELS.items():
        a, b = getattr(ref, key), getattr(now, key)
        if b is None and a is not None:
            out.append(f"no se pudo leer {label}")
        elif key == "exposure_s" and a is not None and b is not None:
            if abs(a - b) > 1e-6 * max(abs(a), abs(b), 1e-9):
                out.append(f"{label}: {a:g} → {b:g} s")
        elif a != b:
            out.append(f"{label}: {a} → {b}")
    return out


# ── El fondo ────────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Dark:
    id: str
    mean: np.ndarray            # float32, la forma del cuadro
    std: np.ndarray             # float32, desviación entre cuadros (0 con un cuadro)
    n_frames: int
    method: str
    conditions: DarkConditions
    t_wall: str                 # fecha y hora local, ISO
    shutter_note: str
    temperature_c: Optional[float]

    def metadata(self, file: Optional[Path] = None) -> Dict:
        d = {"id": self.id, "method": self.method, "method_label": METHOD_LABELS.get(self.method, self.method),
             "n_frames": self.n_frames, "t_wall": self.t_wall, "shutter_note": self.shutter_note,
             "temperature_c": self.temperature_c, "conditions": _conditions_dict(self.conditions)}
        if file is not None:
            d["file"] = str(file)
        return d


def _conditions_dict(c: DarkConditions) -> Dict:
    d = asdict(c)
    for k in ("read_params", "shape"):
        if d[k] is not None:
            d[k] = list(d[k])
    return d


def acquire_dark(camera, spectrometer, conditions: DarkConditions, *, n_frames: int, method: str,
                 expose: Callable[[Tuple[int, ...], float], np.ndarray],
                 open_lasers: Callable[[], List[str]]) -> Dark:
    """Toma el fondo con `expose` (una exposición real por cuadro). No reabre el obturador: lo decide quien
    llama, que sabe si después mide."""
    if method not in METHOD_LABELS:
        raise DarkError(f"método de fondo desconocido: {method}")
    if method == METHOD_SHUTTER:
        from pyspectrum.services.spectrometer_shutter import close_spectrometer_shutter
        res = close_spectrometer_shutter(camera, spectrometer)
        if not res.ok:
            raise DarkError(f"el obturador del espectrómetro no confirmó el cierre: {res.detail}")
        note = "obturador del espectrómetro cerrado (confirmado)"
    else:
        lasers = list(open_lasers())
        if lasers:
            raise DarkError(f"hay láseres abiertos ({', '.join(lasers)}): con \"todo apagado\" tienen que estar "
                            f"cerrados")
        note = "todo apagado (lo apagó el operador)"
        fn = getattr(spectrometer, "ShamrockGetShutter", None) if spectrometer is not None else None
        if fn is not None:
            try:
                ret, state = fn(0)
                if ret == _SHAMROCK_SUCCESS:
                    note += f"; obturador del espectrómetro {'abierto' if int(state) == 1 else 'cerrado'} (USB)"
            except Exception:
                pass
    n = max(1, int(n_frames))
    frames = np.stack([np.asarray(expose(tuple(conditions.shape), float(conditions.exposure_s)), dtype=np.float64)
                       for _ in range(n)])
    mean = frames.mean(axis=0).astype(np.float32)
    std = (frames.std(axis=0, ddof=1) if n > 1 else np.zeros_like(mean)).astype(np.float32)
    temperature = _as_float(_value(getattr(camera, "get_temperature", None)))
    return Dark(uuid.uuid4().hex[:12], mean, std, n, method, conditions,
                time.strftime("%Y-%m-%dT%H:%M:%S"), note, temperature)


def take_dark(camera, spectrometer, conditions: DarkConditions, *, method: str, n_frames: int,
              expose: Callable[[Tuple[int, ...], float], np.ndarray], store: Optional["DarkStore"] = None,
              open_lasers: Optional[Callable[[], List[str]]] = None, reopen: bool = True) -> Dark:
    """Toma un fondo nuevo y lo guarda en el almacén. Con "obturador cerrado" lo reabre (y lo verifica) aunque
    la toma falle: quien llama va a medir después."""
    if open_lasers is None:
        from core.nidaq import get_open_shutter_names as open_lasers
    store = store if store is not None else get_dark_store()
    reopened = None
    try:
        dark = acquire_dark(camera, spectrometer, conditions, n_frames=n_frames, method=method, expose=expose,
                            open_lasers=open_lasers)
    finally:
        if method == METHOD_SHUTTER and reopen:
            from pyspectrum.services.spectrometer_shutter import open_spectrometer_shutter
            reopened = open_spectrometer_shutter(camera, spectrometer)
    if reopened is not None and not reopened.ok:
        raise DarkError(f"el fondo se tomó, pero el obturador del espectrómetro no volvió a abrir: {reopened.detail}")
    store.put(dark)
    return dark


def ensure_dark(camera, spectrometer, conditions: DarkConditions, *, method: str, n_frames: int,
                expose: Callable[[Tuple[int, ...], float], np.ndarray], store: Optional["DarkStore"] = None,
                open_lasers: Optional[Callable[[], List[str]]] = None, reopen: bool = True) -> Dark:
    """El fondo de la corrida: el del almacén si las condiciones no cambiaron; si no, con "obturador cerrado" se
    toma; con "todo apagado", `DarkMissing` (lo toma el operador con [Tomar fondo ahora])."""
    store = store if store is not None else get_dark_store()
    dark = store.get_valid(conditions)
    if dark is not None:
        return dark
    if method == METHOD_ALL_OFF:
        state, _old, reason = store.status(conditions)
        why = f" (el anterior no vale: {reason})" if state == "invalid" and reason else ""
        raise DarkMissing(f"Falta el fondo con \"todo apagado\"{why}: apagá la lámpara y los láseres y apretá "
                          f"[Tomar fondo ahora] antes de iniciar.")
    return take_dark(camera, spectrometer, conditions, method=method, n_frames=n_frames, expose=expose, store=store,
                     open_lasers=open_lasers, reopen=reopen)


# ── Almacén de la sesión ────────────────────────────────────────────────────────────────────

class DarkStore:
    """Un fondo por juego de condiciones. Sólo en memoria."""

    def __init__(self):
        self._lock = threading.Lock()
        self._darks: Dict[DarkConditions, Dark] = {}
        self._latest: Optional[Dark] = None

    def put(self, dark: Dark) -> None:
        with self._lock:
            self._darks[dark.conditions] = dark
            self._latest = dark

    def get_valid(self, conditions: DarkConditions) -> Optional[Dark]:
        with self._lock:
            return self._darks.get(conditions)

    def status(self, conditions: DarkConditions) -> Tuple[str, Optional[Dark], str]:
        """("valid", fondo, "") · ("invalid", último fondo, qué cambió) · ("none", None, "")."""
        with self._lock:
            d = self._darks.get(conditions)
            if d is not None:
                return "valid", d, ""
            if self._latest is None:
                return "none", None, ""
            return "invalid", self._latest, "; ".join(differences(self._latest.conditions, conditions))

    def discard(self, conditions: DarkConditions) -> None:
        with self._lock:
            d = self._darks.pop(conditions, None)
            if d is not None and self._latest is d:
                self._latest = next(reversed(self._darks.values()), None) if self._darks else None

    def clear(self) -> None:
        with self._lock:
            self._darks.clear()
            self._latest = None


_STORE = DarkStore()


def get_dark_store() -> DarkStore:
    return _STORE


# ── Guardado: crudo y fondo por separado ────────────────────────────────────────────────────

def save_dark_npz(dark: Dark, directory, prefix: str) -> Path:
    d = Path(directory)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{prefix}_background_{dark.id}.npz"
    np.savez(path, mean=dark.mean, std=dark.std, metadata=np.array(json.dumps(dark.metadata(), ensure_ascii=False)))
    return path


def dark_header_lines(dark: Optional[Dark], path: Optional[Path]) -> List[str]:
    """Líneas de encabezado para los txt: qué fondo corresponde a este espectro (que se guarda crudo)."""
    if dark is None:
        return ["background_id: ninguno"]
    lines = [f"background_id: {dark.id}", f"background_method: {METHOD_LABELS.get(dark.method, dark.method)}",
             f"background_n_frames: {dark.n_frames}", "background_subtracted: no (el espectro es crudo)"]
    if path is not None:
        lines.append(f"background_file: {Path(path).name}")
    return lines


def write_dark_h5(h5, dark: Dark, name: str = "background") -> None:
    g = h5.create_group(name)
    g.create_dataset("mean", data=dark.mean, compression="gzip", shuffle=True)
    g.create_dataset("std", data=dark.std, compression="gzip", shuffle=True)
    meta = dark.metadata()
    for k in ("id", "method", "method_label", "t_wall", "shutter_note"):
        g.attrs[k] = str(meta[k])
    g.attrs["n_frames"] = int(dark.n_frames)
    g.attrs["temperature_c"] = float(dark.temperature_c) if dark.temperature_c is not None else float("nan")
    g.attrs["conditions_json"] = json.dumps(meta["conditions"], ensure_ascii=False)
