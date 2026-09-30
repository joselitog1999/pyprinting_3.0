# -*- coding: utf-8 -*-
"""
repository.py — Repositorio de calibraciones del Shamrock (paso 9 del bloque A, DEC-040)

El historial de los offsets del espectrógrafo: lo leído en cada arranque, lo que registró el operador,
lo propuesto por la calibración automática y cada escritura con su respaldo y su relectura. Contrato
R2-arq §2.5, reconciliado en la Ronda 4 (D-03, D-04) y con las respuestas R4-A-5, R4-B-1 y R4-G.

- **Ubicación:** local a la PC y **fuera de git**. Por defecto
  `%LOCALAPPDATA%\\PyPrinting\\pyspectrum\\shamrock_calibration.jsonl`; se cambia con
  `config.SHAMROCK_CALIBRATION_PATH`. El constructor rechaza una ruta dentro del repositorio.
- **Formato:** JSON Lines con `schema_version`. Sólo se agregan entradas, con flush + fsync y un lock
  contra dos escritores. Nunca se reescribe una línea: la corrección de un error es otra línea.
- **Clave:** (serie, índice de red, líneas/mm leídas con `GetGratingInfo`, puerto de entrada, puerto de
  salida). Un orden distinto en la torreta no aplica un offset a la red equivocada.
- **Referencia:** el APPLIED(CONFIRMED) más reciente por clave; si no hay, el MANUAL_ENTRY más reciente.
  El detector se compara contra 0 por convención (R4-A-2).
- **Al arrancar** (`observe_spectrograph`): se lee con Get* y se registra OBSERVED. Después se compara y
  se informa. **Nunca se escribe al equipo** (R4-B-1: "leer al inicio" es cargar y comparar).
"""
from __future__ import annotations

import datetime as _dt
import getpass
import json
import os
import subprocess
import threading
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = 1
LINES_PER_MM_TOL = 0.5
KINDS = ("OBSERVED", "MANUAL_ENTRY", "PROPOSED", "PRE_WRITE", "APPLIED", "SOFTWARE_CORRECTION")
OUTCOMES = ("CONFIRMED", "MISMATCH", "WRITE_FAILED", "READBACK_FAILED")

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SHAMROCK_SUCCESS = 20202


class CalibrationVerdict(Enum):
    """Veredicto metrológico de una calibración (D-03). Ninguno dice "validado"."""
    ACEPTADA = "ACEPTADA"
    ACEPTADA_CON_RESERVA = "ACEPTADA_CON_RESERVA"
    RECHAZADA = "RECHAZADA"
    EN_SECO = "EN_SECO"
    CANCELADA = "CANCELADA"


@dataclass(frozen=True)
class CalibrationKey:
    serial: str
    grating_index: int
    lines_per_mm: float
    entrance_port: int
    exit_port: int

    def matches(self, other: "CalibrationKey") -> bool:
        return (self.serial == other.serial and int(self.grating_index) == int(other.grating_index)
                and abs(float(self.lines_per_mm) - float(other.lines_per_mm)) <= LINES_PER_MM_TOL
                and int(self.entrance_port) == int(other.entrance_port)
                and int(self.exit_port) == int(other.exit_port))

    def to_dict(self) -> Dict[str, Any]:
        return {"serial": self.serial, "grating_index": int(self.grating_index),
                "lines_per_mm": float(self.lines_per_mm), "entrance_port": int(self.entrance_port),
                "exit_port": int(self.exit_port)}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> Optional["CalibrationKey"]:
        try:
            return cls(str(d["serial"]), int(d["grating_index"]), float(d["lines_per_mm"]),
                       int(d["entrance_port"]), int(d["exit_port"]))
        except (KeyError, TypeError, ValueError):
            return None


def _software_version() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=_REPO_ROOT, capture_output=True,
                             text=True, timeout=2)
        return out.stdout.strip() or "desconocida"
    except Exception:
        return "desconocida"


def _operator() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return os.environ.get("USERNAME", "desconocido")


_SOFTWARE = None


def _software() -> str:
    global _SOFTWARE
    if _SOFTWARE is None:
        _SOFTWARE = _software_version()
    return _SOFTWARE


@dataclass
class CalibrationEntry:
    kind: str
    key: Optional[CalibrationKey] = None
    method: str = ""
    note: str = ""
    values: Dict[str, Any] = field(default_factory=dict)
    record_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    ts: str = field(default_factory=lambda: _dt.datetime.now().astimezone().isoformat(timespec="seconds"))
    operator: str = field(default_factory=_operator)
    software: str = field(default_factory=_software)
    schema_version: int = SCHEMA_VERSION

    # ── Accesos cómodos ──
    @property
    def transaction_id(self) -> Optional[str]:
        return self.values.get("transaction_id")

    @property
    def provenance(self) -> Optional[str]:
        return self.values.get("provenance")

    # ── Constructores por tipo ──
    @classmethod
    def observed(cls, values: Dict[str, Any], note: str = "arranque") -> "CalibrationEntry":
        return cls("OBSERVED", None, method="startup_read_only", note=note, values=values)

    @classmethod
    def manual_entry(cls, key: CalibrationKey, offset_steps: int, *, source: str, note: str = "",
                     measured_geometry: Optional[Dict[str, Any]] = None) -> "CalibrationEntry":
        return cls("MANUAL_ENTRY", key, method="manual_entry", note=note,
                   values={"offset": int(offset_steps), "provenance": "EXPERIMENTAL", "source": source,
                           "measured_geometry": measured_geometry})

    @classmethod
    def pre_write(cls, key: CalibrationKey, *, transaction_id: str, offset_read: int, requested: int,
                  source_record_id: Optional[str], note: str = "") -> "CalibrationEntry":
        return cls("PRE_WRITE", key, method="offset_write_transaction", note=note,
                   values={"transaction_id": transaction_id, "offset_read": int(offset_read),
                           "requested": int(requested), "source_record_id": source_record_id})

    @classmethod
    def applied(cls, key: CalibrationKey, *, transaction_id: str, requested: int, readback: Optional[int],
                outcome: str, code_write: Optional[int], code_read: Optional[int],
                source_record_id: Optional[str], note: str = "") -> "CalibrationEntry":
        if outcome not in OUTCOMES:
            raise ValueError(f"outcome {outcome!r} desconocido")
        return cls("APPLIED", key, method="offset_write_transaction", note=note,
                   values={"transaction_id": transaction_id, "requested": int(requested),
                           "readback": None if readback is None else int(readback), "outcome": outcome,
                           "code_write": code_write, "code_read": code_read,
                           "source_record_id": source_record_id})

    # ── Serialización ──
    def to_json(self) -> str:
        d = {"schema_version": self.schema_version, "record_id": self.record_id, "kind": self.kind,
             "ts": self.ts, "operator": self.operator, "software": self.software, "method": self.method,
             "note": self.note, "key": self.key.to_dict() if self.key else None}
        d.update(self.values)
        return json.dumps(d, ensure_ascii=False, sort_keys=False)

    @classmethod
    def from_json(cls, line: str) -> "CalibrationEntry":
        d = json.loads(line)
        common = {"schema_version", "record_id", "kind", "ts", "operator", "software", "method", "note", "key"}
        values = {k: v for k, v in d.items() if k not in common}
        return cls(kind=d["kind"], key=CalibrationKey.from_dict(d["key"]) if d.get("key") else None,
                   method=d.get("method", ""), note=d.get("note", ""), values=values,
                   record_id=d.get("record_id", ""), ts=d.get("ts", ""), operator=d.get("operator", ""),
                   software=d.get("software", ""), schema_version=int(d.get("schema_version", 0)))

    def __getattr__(self, name):
        # provenance, etc. también como atributo del JSON (sólo para campos de `values`)
        values = self.__dict__.get("values", {})
        if name in values:
            return values[name]
        raise AttributeError(name)


@dataclass(frozen=True)
class ReferenceValue:
    value: int
    kind: str
    record_id: str
    ts: str


def default_repository_path() -> Path:
    try:
        from config import SHAMROCK_CALIBRATION_PATH
    except Exception:
        SHAMROCK_CALIBRATION_PATH = None
    if SHAMROCK_CALIBRATION_PATH:
        return Path(SHAMROCK_CALIBRATION_PATH)
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "PyPrinting" / "pyspectrum" / "shamrock_calibration.jsonl"


def _lock_file(fh) -> None:
    if os.name == "nt":
        import msvcrt
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
    else:  # pragma: no cover
        import fcntl
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)


def _unlock_file(fh) -> None:
    if os.name == "nt":
        import msvcrt
        fh.seek(0)
        try:
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
    else:  # pragma: no cover
        import fcntl
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


class CalibrationRepository:
    def __init__(self, path: Optional[Path] = None):
        path = Path(path) if path is not None else default_repository_path()
        resolved = path.resolve()
        if resolved == _REPO_ROOT or _REPO_ROOT in resolved.parents:
            raise ValueError(f"El archivo de calibraciones no puede estar dentro del repositorio ({path}): "
                             f"tiene que ser local a la PC y quedar fuera de git.")
        self.path = path
        self._lock = threading.Lock()
        self.unreadable_lines = 0

    # ── Escritura ──
    def append(self, entry: CalibrationEntry) -> None:
        """Agrega una línea con flush + fsync. Un OSError se propaga: sin registro no hay escritura."""
        line = entry.to_json() + "\n"
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a+", encoding="utf-8") as fh:
                _lock_file(fh)
                try:
                    fh.seek(0, os.SEEK_END)
                    fh.write(line)
                    fh.flush()
                    os.fsync(fh.fileno())
                finally:
                    _unlock_file(fh)

    # ── Lectura ──
    def history(self, key: Optional[CalibrationKey] = None) -> List[CalibrationEntry]:
        entries: List[CalibrationEntry] = []
        bad = 0
        if self.path.exists():
            with open(self.path, "r", encoding="utf-8") as fh:
                for raw in fh:
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        entries.append(CalibrationEntry.from_json(raw))
                    except (ValueError, KeyError, TypeError):
                        bad += 1
        self.unreadable_lines = bad
        if key is not None:
            entries = [e for e in entries if e.key is not None and e.key.matches(key)]
        return entries

    def reference_state(self, key: CalibrationKey) -> Optional[ReferenceValue]:
        confirmed = manual = None
        for e in self.history(key):
            if e.kind == "APPLIED" and e.values.get("outcome") == "CONFIRMED":
                confirmed = e
            elif e.kind == "MANUAL_ENTRY":
                manual = e
        if confirmed is not None:
            return ReferenceValue(int(confirmed.values["readback"]), "APPLIED", confirmed.record_id, confirmed.ts)
        if manual is not None:
            return ReferenceValue(int(manual.values["offset"]), "MANUAL_ENTRY", manual.record_id, manual.ts)
        return None

    def orphan_pre_writes(self) -> List[CalibrationEntry]:
        """PRE_WRITE sin APPLIED de la misma transacción: una escritura que no se sabe si ocurrió (H-17d)."""
        hist = self.history()
        applied = {e.values.get("transaction_id") for e in hist if e.kind == "APPLIED"}
        return [e for e in hist if e.kind == "PRE_WRITE" and e.values.get("transaction_id") not in applied]


# ── Observación al arrancar ──────────────────────────────────────────────────

FINE_CORRECTION_VERDICTS = ("ACEPTADA", "ACEPTADA_CON_RESERVA")
C_SW_CONVENTION = "lambda(p) = lambda_SDK(p + c_sw)"


@dataclass(frozen=True)
class SoftwareCorrectionState:
    """Estado de la corrección fina de una red al arrancar (R3-gui §4.6)."""
    grating_index: int
    status: str                        # APLICADA / SUSPENDIDA / NINGUNA
    c_sw_px: Optional[float] = None
    u_c_sw_px: Optional[float] = None
    record_id: Optional[str] = None
    source_record_id: Optional[str] = None
    ts: Optional[str] = None
    reason: str = ""


def apply_fine_correction(repo: "CalibrationRepository", calibration: CalibrationEntry) -> CalibrationEntry:
    """[Aplicar corrección fina] (paso 14c; D-04): agrega una SOFTWARE_CORRECTION con la c_sw de una
    calibración ACEPTADA o CON RESERVA. No escribe al equipo: la corrección es sólo de PySpectrum (R4-B 2),
    y se guarda aparte del eje λ, como metadato (R4-C-6)."""
    v = calibration.values
    verdict = v.get("verdict")
    if verdict not in FINE_CORRECTION_VERDICTS:
        raise ValueError(f"La corrección fina sólo se aplica desde ACEPTADA o CON RESERVA, no desde {verdict}.")
    if calibration.key is None or v.get("c_sw_px") is None or v.get("grating_offset_after") is None:
        raise ValueError("La calibración no tiene identidad, corrección u offset con el que se midió.")
    entry = CalibrationEntry("SOFTWARE_CORRECTION", calibration.key, method="fine_correction",
                             note=f"desde la calibración {calibration.record_id}",
                             values={"source_record_id": calibration.record_id, "c_sw_px": float(v["c_sw_px"]),
                                     "u_c_sw_px": v.get("u_c_sw_px"), "grating_offset": int(v["grating_offset_after"]),
                                     "declared_geometry": v.get("declared_geometry"), "c_sw_convention": C_SW_CONVENTION,
                                     "source_verdict": verdict, "provenance": "EXPERIMENTAL"})
    repo.append(entry)
    return entry


def active_software_correction(repo: "CalibrationRepository", key: CalibrationKey, *, offset_read: Optional[int],
                               geometry: Optional[Dict[str, Any]]) -> SoftwareCorrectionState:
    """La última corrección fina de esa red (misma serie, puertos y líneas). Vale sólo si el offset leído es
    el mismo con el que se midió y la geometría coincide; si no, SUSPENDIDA con el motivo."""
    entries = [e for e in repo.history(key) if e.kind == "SOFTWARE_CORRECTION"]
    g = int(key.grating_index)
    if not entries:
        return SoftwareCorrectionState(g, "NINGUNA")
    e = entries[-1]
    v = e.values
    base = dict(c_sw_px=v.get("c_sw_px"), u_c_sw_px=v.get("u_c_sw_px"), record_id=e.record_id,
                source_record_id=v.get("source_record_id"), ts=e.ts)
    if offset_read is None:
        return SoftwareCorrectionState(g, "SUSPENDIDA", reason="no se pudo leer el offset de la red", **base)
    if int(offset_read) != int(v.get("grating_offset", -10 ** 9)):
        return SoftwareCorrectionState(g, "SUSPENDIDA", reason=f"se midió con el offset {v.get('grating_offset')} y "
                                                                 f"el equipo tiene {offset_read}", **base)
    ref_geom = v.get("declared_geometry")
    if ref_geom and geometry and (int(ref_geom.get("n_px", -1)) != int(geometry.get("n_px", -2)) or
                                  abs(float(ref_geom.get("pixel_width_um", -1)) - float(geometry.get("pixel_width_um", -2))) > 1e-9):
        return SoftwareCorrectionState(g, "SUSPENDIDA", reason=f"la geometría del detector cambió ({ref_geom} → {geometry})",
                                       **base)
    return SoftwareCorrectionState(g, "APLICADA", **base)


@dataclass(frozen=True)
class OffsetComparison:
    grating_index: int
    lines_per_mm: Optional[float]
    device: Optional[int]
    reference: Optional[int]
    reference_kind: Optional[str]
    status: str               # IGUAL / DISTINTO / SIN_REFERENCIA / NO_LEIDO
    code: Optional[int] = None


@dataclass
class StartupCalibrationReport:
    serial: Optional[str]
    entrance_port: Optional[int]
    exit_port: Optional[int]
    rows: List[OffsetComparison]
    detector_offset: Optional[int]
    detector_status: str
    orphan_pre_writes: List[CalibrationEntry]
    first_use: bool
    observed_record_id: Optional[str]
    append_error: Optional[str] = None
    software_corrections: List[SoftwareCorrectionState] = field(default_factory=list)

    def warnings(self) -> List[str]:
        out: List[str] = []
        if self.append_error:
            out.append(f"No se pudo registrar la lectura del arranque en el archivo de calibraciones: "
                       f"{self.append_error}")
        for r in self.rows:
            label = f"red {r.grating_index}" + (f" ({r.lines_per_mm:.0f} l/mm)" if r.lines_per_mm else "")
            if r.status == "DISTINTO":
                out.append(f"Offsets del equipo distintos del archivo de calibraciones: {label}: equipo "
                           f"{r.device} pasos, archivo {r.reference} pasos.")
            elif r.status == "NO_LEIDO":
                out.append(f"Offset de la {label} desconocido (falló la lectura, código {r.code}): no se "
                           f"puede comparar con el archivo.")
        if self.detector_status == "DISTINTO":
            out.append(f"Offset del detector: equipo {self.detector_offset} pasos, 0 por convención (R4-A-2).")
        elif self.detector_status == "NO_LEIDO":
            out.append("Offset del detector desconocido (falló la lectura).")
        for c in self.software_corrections:
            if c.status == "SUSPENDIDA":
                out.append(f"La corrección fina de la red {c.grating_index} ({c.c_sw_px:+.2f} px) está suspendida: "
                           f"{c.reason}. Volvé a calibrar esa red.")
        for e in self.orphan_pre_writes:
            v = e.values
            out.append(f"Hay una escritura de offset sin confirmar ({e.ts}, red "
                       f"{e.key.grating_index if e.key else '?'}): respaldo {v.get('offset_read')} pasos, "
                       f"pedido {v.get('requested')} pasos. Releé el equipo en Calibraciones.")
        return out

    @property
    def has_warnings(self) -> bool:
        return bool(self.warnings())


def _grating_indices(spec) -> List[int]:
    try:
        ret, n = spec.ShamrockGetNumberGratings(0)
        if ret == _SHAMROCK_SUCCESS and int(n) > 0:
            return list(range(1, int(n) + 1))
    except Exception:
        pass
    return [1, 2, 3]


def observe_spectrograph(spec, repo: CalibrationRepository, *, entrance_port: Optional[int] = None,
                         exit_port: Optional[int] = None) -> StartupCalibrationReport:
    """Lee el Shamrock sólo con Get*, registra OBSERVED y compara con el estado de referencia.
    Nunca escribe al equipo. Una lectura fallida es "desconocido", nunca el valor viejo del archivo."""
    device = 0
    ret_s, serial = spec.ShamrockGetSerialNumber(device)
    serial = str(serial) if ret_s == _SHAMROCK_SUCCESS else None

    def _port(flipper: int, override: Optional[int]) -> Optional[int]:
        if override is not None:
            return int(override)
        try:
            ret, port = spec.ShamrockGetFlipper(device, flipper)
            return int(port) if ret == _SHAMROCK_SUCCESS else None
        except Exception:
            return None

    p_in, p_out = _port(1, entrance_port), _port(2, exit_port)

    gratings: Dict[str, Dict[str, Any]] = {}
    rows: List[OffsetComparison] = []
    first_use = not repo.path.exists()
    for g in _grating_indices(spec):
        info = spec.ShamrockGetGratingInfo(device, g)
        lines = float(info[1]) if info and info[0] == _SHAMROCK_SUCCESS else None
        blaze = info[2] if info and info[0] == _SHAMROCK_SUCCESS else None
        ret_o, off = spec.ShamrockGetGratingOffset(device, g)
        device_off = int(off) if ret_o == _SHAMROCK_SUCCESS else None
        gratings[str(g)] = {"lines_per_mm": lines, "blaze": blaze if not isinstance(blaze, bytes) else blaze.decode(errors="replace"),
                            "offset": device_off, "ret": ret_o}
        if lines is None or lines == 0.0:
            continue                         # el espejo (0 l/mm) no se calibra; queda registrado
        ref = None
        if serial is not None and p_in is not None and p_out is not None:
            ref = repo.reference_state(CalibrationKey(serial, g, lines, p_in, p_out))
        if device_off is None:
            status = "NO_LEIDO"
        elif ref is None:
            status = "SIN_REFERENCIA"
        else:
            status = "IGUAL" if ref.value == device_off else "DISTINTO"
        rows.append(OffsetComparison(g, lines, device_off, ref.value if ref else None,
                                     ref.kind if ref else None, status, ret_o))

    ret_d, det = spec.ShamrockGetDetectorOffset(device)
    det_off = int(det) if ret_d == _SHAMROCK_SUCCESS else None
    det_status = "NO_LEIDO" if det_off is None else ("IGUAL" if det_off == 0 else "DISTINTO")
    try:
        ret_z, zero = spec.ShamrockGetSlitZeroPosition(device, 1)
    except Exception:
        ret_z, zero = (None, None)

    values = {"serial": serial, "entrance_port": p_in, "exit_port": p_out, "gratings": gratings,
              "detector_offset": {"value": det_off, "ret": ret_d},
              "slit_zero": {"value": int(zero) if ret_z == _SHAMROCK_SUCCESS else None, "ret": ret_z}}
    orphans = repo.orphan_pre_writes() if not first_use else []
    geometry = None
    try:
        ret_n, n_px = spec.ShamrockGetNumberPixels(device)
        ret_w, width = spec.ShamrockGetPixelWidth(device)
        if ret_n == _SHAMROCK_SUCCESS and ret_w == _SHAMROCK_SUCCESS:
            geometry = {"n_px": int(n_px), "pixel_width_um": float(width)}
    except Exception:
        geometry = None
    corrections: List[SoftwareCorrectionState] = []
    if serial is not None and p_in is not None and p_out is not None:
        for r in rows:
            if r.lines_per_mm:
                st = active_software_correction(repo, CalibrationKey(serial, r.grating_index, r.lines_per_mm, p_in, p_out),
                                                offset_read=r.device, geometry=geometry)
                if st.status != "NINGUNA":
                    corrections.append(st)
    values["software_corrections"] = [{"grating": c.grating_index, "status": c.status, "c_sw_px": c.c_sw_px,
                                       "record_id": c.record_id, "reason": c.reason} for c in corrections]
    entry = CalibrationEntry.observed(values)
    append_error = None
    try:
        repo.append(entry)
    except OSError as e:
        append_error = str(e)
    return StartupCalibrationReport(serial, p_in, p_out, rows, det_off, det_status, orphans, first_use,
                                    None if append_error else entry.record_id, append_error, corrections)


_REPOSITORY: Optional[CalibrationRepository] = None


def get_repository() -> CalibrationRepository:
    global _REPOSITORY
    if _REPOSITORY is None or _REPOSITORY.path != default_repository_path():
        _REPOSITORY = CalibrationRepository()
    return _REPOSITORY
