# -*- coding: utf-8 -*-
"""
detection_mirror_state.py — Último estado conocido del espejo de detección, entre sesiones (C-08; R4-N 3, P7)

El espejo de detección es un Thorlabs MFF101 en modo conmutador, sin realimentación (BANCO-21): cada pulso lo
cambia de lado y el software sólo sabe lo que ordenó. Este módulo guarda esa creencia en disco para que la
sesión siguiente arranque sabiendo qué se ordenó por última vez.

- **Archivo:** `detection_mirror.json`, junto al archivo de calibraciones del Shamrock (fuera del repositorio;
  `config.SHAMROCK_CALIBRATION_PATH` o `%LOCALAPPDATA%\\PyPrinting\\pyspectrum\\`), o donde diga
  `config.DETECTION_MIRROR_STATE_PATH`. Lo comparten PySpectrum 3.0 y PyPrinting 3.0, que manejan el mismo
  espejo.
- **Se escribe** después de cada pulso que salió bien y de cada confirmación del operador; en forma atómica.
- **Al leerlo** es sólo "último conocido": las rutinas lo siguen tratando como no confirmado (D-01). Un archivo
  ausente o dañado es "sin información".
- **Los legados** guardaban su propio estado en `flipper_notch532_status.txt` ("0" arriba, "1" abajo), uno el
  PyPrinting legado y otro el PySpectrum legado. Si `config.LEGACY_DETECTION_MIRROR_STATUS_FILE` da una ruta (o
  varias, separadas por `;`), se leen, sólo lectura, como información (P7).

Sin Qt ni hardware. Una falla al escribir nunca rompe el movimiento: se informa por consola.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import List, NamedTuple, Optional, Tuple

FILE_NAME = "detection_mirror.json"
SCHEMA_VERSION = 1
_POSITIONS = ("up", "down")
_SOURCES = ("commanded", "operator_confirmed")


class SavedMirrorState(NamedTuple):
    position: str          # "up" / "down"
    source: str            # "commanded" / "operator_confirmed"
    since: float           # time.time() de cuando se ordenó o confirmó


def state_path() -> Path:
    try:
        from config import DETECTION_MIRROR_STATE_PATH
    except Exception:
        DETECTION_MIRROR_STATE_PATH = None
    if DETECTION_MIRROR_STATE_PATH:
        return Path(DETECTION_MIRROR_STATE_PATH)
    try:
        from config import SHAMROCK_CALIBRATION_PATH
    except Exception:
        SHAMROCK_CALIBRATION_PATH = None
    if SHAMROCK_CALIBRATION_PATH:
        return Path(SHAMROCK_CALIBRATION_PATH).parent / FILE_NAME
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "PyPrinting" / "pyspectrum" / FILE_NAME


def save_state(position: str, source: str, since: Optional[float] = None, path: Optional[Path] = None) -> bool:
    """Escribe el estado (temporal + reemplazo). Devuelve False si no pudo; nunca lanza."""
    if position not in _POSITIONS or source not in _SOURCES:
        return False
    target = Path(path) if path is not None else state_path()
    data = {"schema_version": SCHEMA_VERSION, "position": position, "source": source,
            "since": float(since if since is not None else time.time()),
            "since_text": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(since or time.time()))}
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, target)
        return True
    except OSError as e:
        print(f"[Espejo de detección] No se pudo guardar el estado en {target}: {e}")
        return False


def load_state(path: Optional[Path] = None) -> Optional[SavedMirrorState]:
    """El último estado guardado, o None si no hay archivo o está dañado."""
    target = Path(path) if path is not None else state_path()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        pos, src, since = data["position"], data["source"], float(data["since"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if pos not in _POSITIONS or src not in _SOURCES or since != since:
        return None
    return SavedMirrorState(pos, src, since)


def _legacy_paths() -> List[Path]:
    try:
        from config import LEGACY_DETECTION_MIRROR_STATUS_FILE as value
    except Exception:
        return []
    if not value:
        return []
    if isinstance(value, (str, os.PathLike)):
        value = [part for part in str(value).split(os.pathsep) if part]
    return [Path(v) for v in value]


def _read_one(path: Path) -> Optional[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    return {"0": "up", "1": "down"}.get(text[:1] if text else "")


def read_legacy_states() -> List[Tuple[str, Optional[str]]]:
    """Lo que dice cada archivo de estado de los legados: [(ruta, "up" / "down" / None)], sólo lectura.

    El PyPrinting y el PySpectrum legados guardaban cada uno su archivo para el mismo espejo y se
    desincronizaban (TRIAGE_SISTEMA_VS_LEGADO, C-08): por eso se muestran todos, sin elegir."""
    return [(str(p), _read_one(p)) for p in _legacy_paths()]


def read_legacy_state() -> Optional[str]:
    """El estado del primer archivo del legado configurado, o None."""
    states = read_legacy_states()
    return states[0][1] if states else None
