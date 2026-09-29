# -*- coding: utf-8 -*-
"""
offset_transaction.py — Escritura de un offset de red en el Shamrock (paso 10 del bloque A, DEC-040)

La **única** ruta de `ShamrockSetGratingOffset` en PySpectrum (test de AST). Una escritura cambia lo que ven
Solis y el legado, y puede girar la torreta, así que es una máquina de estados sin Qt. El diálogo de la
Ronda 3 sólo la conduce. Contrato R2-arq §2.6 y R2-inst §3.3, reconciliado en la Ronda 4 (D-07b, D-07c,
H-07, H-18, R4-C-4, R4-C-5 y R4-D-3).

    IDLE → prepare() → DIFF_READY --confirm_diff(token1)--> BACKED_UP --confirm_write(token2)--> resultado
             |              |                                   |
        READ_FAILED     CANCELLED                        BACKUP_FAILED (no escribe)
        REFUSED                                          STALE_TOKEN / PRECONDITION_FAILED (no escribe)
                                                         WRITE_FAILED / READBACK_FAILED / MISMATCH / CONFIRMED

Reglas:
- **Alcance:** sólo redes 1 y 2 (el espejo no se calibra). El detector queda en 0 por convención y el
  cero de ranura no se escribe (R2-inst §3.2).
- **Validez, no política** (D-07c, H-07): |offset| ≤ 20 000 pasos, el rango del SDK. Sin tope de cambio.
- **Confirmaciones:** la 2.ª exige teclear el número de líneas de la red. Un |Δ| mayor que
  `config.THIRD_CONFIRMATION_STEPS` pide una 3.ª. Cada token vence a los 60 s.
- **Respaldo:** PRE_WRITE registrado con fsync **antes** de tocar el equipo. Si falla, no se escribe.
- **Antes de escribir:**
  - se relee el offset; si cambió desde `prepare`, STALE_TOKEN;
  - sesión "Calibración — escritura" (sin E-STOP ni otra rutina);
  - cámara IDLE, ganancia EM 0 releída y obturadores cerrados con confirmación (R2-inst §3.1: una
    escritura de offset es una orden de movimiento).
- **Después:** relectura, APPLIED con el resultado. Si la red escrita es la activa, se re-emite
  SetWavelength a la λc vigente (no se sabe si SetGratingOffset mueve el motor; BANCO-40).
- **Vuelta:** con WRITE_FAILED, READBACK_FAILED o MISMATCH, `backup_return()` arma una transacción
  **nueva y completa** hacia el valor del respaldo, con su `source_record_id` (R4-D-3). Es el único caso
  en que se escribe un valor del historial.
"""
from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

from pyspectrum.calibration.repository import CalibrationEntry, CalibrationKey, CalibrationRepository
from pyspectrum.drivers.andor_ccd_driver import DRV_ACQUIRING, DRV_SUCCESS

GRAT_OFFSET_MAX_STEPS = 20000          # SHAMROCK_GRAT_OFFSET_MAX del SDK (R2-inst §3.1): validez, no política
TOKEN_TTL_S = 60.0                     # R2-inst §3.3, O4
WRITABLE_GRATINGS = (1, 2)
_SHAMROCK_SUCCESS = 20202
_DEVICE = 0


class TxState(Enum):
    IDLE = "IDLE"
    DIFF_READY = "DIFF_READY"
    READ_FAILED = "READ_FAILED"
    REFUSED = "REFUSED"
    CANCELLED = "CANCELLED"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    BACKED_UP = "BACKED_UP"
    BACKUP_FAILED = "BACKUP_FAILED"
    STALE_TOKEN = "STALE_TOKEN"
    PRECONDITION_FAILED = "PRECONDITION_FAILED"
    WRITE_FAILED = "WRITE_FAILED"
    READBACK_FAILED = "READBACK_FAILED"
    MISMATCH = "MISMATCH"
    CONFIRMED = "CONFIRMED"


_BACKUP_RETURN_STATES = (TxState.WRITE_FAILED, TxState.READBACK_FAILED, TxState.MISMATCH)


@dataclass(frozen=True)
class OffsetDiff:
    key: CalibrationKey
    offset_read: int
    requested: int
    delta: int
    read_at: float
    needs_third_confirmation: bool
    estimated_nm: Optional[float]
    serial_matches_file: bool
    digest: str


@dataclass(frozen=True)
class ConfirmationToken:
    stage: str               # "diff" o "write"
    digest: str
    issued_at: float


@dataclass(frozen=True)
class TransactionResult:
    state: TxState
    detail: str
    before: Optional[int] = None
    requested: Optional[int] = None
    after: Optional[int] = None
    code_write: Optional[int] = None
    code_read: Optional[int] = None
    applied_record_id: Optional[str] = None
    record_error: Optional[str] = None


def _default_session():
    from pyspectrum.modules.hardware_session import hardware_session
    return hardware_session


def _default_close_all() -> bool:
    from core.nidaq import close_all_shutters
    return close_all_shutters()


def _gain_reading(cam):
    g = cam.get_emccd_gain()
    if isinstance(g, (tuple, list)) and len(g) >= 2:
        return int(g[0]), int(g[1])
    return DRV_SUCCESS, int(g)


class OffsetWriteTransaction:
    SESSION_NAME = "Calibración — escritura"

    def __init__(self, spectrometer, camera, repo: CalibrationRepository, *, grating: int, requested_offset: int,
                 source_record_id: Optional[str], session=None,
                 close_all_shutters: Callable[[], bool] = _default_close_all,
                 clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep,
                 token_ttl_s: float = TOKEN_TTL_S, third_threshold_steps: Optional[int] = None,
                 nm_per_step: Optional[float] = None, entrance_port: Optional[int] = None,
                 exit_port: Optional[int] = None, idle_timeout_s: float = 0.5):
        self.spectrometer = spectrometer
        self.camera = camera
        self.repo = repo
        self.grating = int(grating)
        self.requested_offset = int(requested_offset)
        self.source_record_id = source_record_id
        self._session = session
        self._close_all = close_all_shutters
        self._clock = clock
        self._sleep = sleep
        self.token_ttl_s = float(token_ttl_s)
        if third_threshold_steps is None:
            try:
                from config import THIRD_CONFIRMATION_STEPS as third_threshold_steps
            except Exception:
                third_threshold_steps = 50
        self.third_threshold_steps = int(third_threshold_steps)
        self.nm_per_step = nm_per_step          # sin S medida (BANCO-40) no hay estimación en nm
        self._ports = (entrance_port, exit_port)
        self.idle_timeout_s = float(idle_timeout_s)
        self.transaction_id = uuid.uuid4().hex
        self.state = TxState.IDLE
        self.detail = ""
        self.diff: Optional[OffsetDiff] = None
        self.key: Optional[CalibrationKey] = None
        self.pre_write_record_id: Optional[str] = None
        self.result: Optional[TransactionResult] = None

    @property
    def session(self):
        return self._session if self._session is not None else _default_session()

    def _set(self, state: TxState, detail: str = "") -> TxState:
        self.state, self.detail = state, detail
        return state

    # ── Lectura ──
    def _read_identity(self):
        spec = self.spectrometer
        ret_s, serial = spec.ShamrockGetSerialNumber(_DEVICE)
        info = spec.ShamrockGetGratingInfo(_DEVICE, self.grating)
        ports = []
        for flipper, override in ((1, self._ports[0]), (2, self._ports[1])):
            if override is not None:
                ports.append(int(override))
                continue
            try:
                ret, port = spec.ShamrockGetFlipper(_DEVICE, flipper)
                ports.append(int(port) if ret == _SHAMROCK_SUCCESS else None)
            except Exception:
                ports.append(None)
        if ret_s != _SHAMROCK_SUCCESS or not info or info[0] != _SHAMROCK_SUCCESS or None in ports:
            return None
        return CalibrationKey(str(serial), self.grating, float(info[1]), ports[0], ports[1])

    def _read_offset(self):
        ret, value = self.spectrometer.ShamrockGetGratingOffset(_DEVICE, self.grating)
        return (ret, int(value) if ret == _SHAMROCK_SUCCESS else None)

    def _digest(self, key: CalibrationKey, offset_read: int) -> str:
        raw = f"{key.serial}|{key.grating_index}|{key.lines_per_mm}|{key.entrance_port}|{key.exit_port}|" \
              f"{offset_read}|{self.requested_offset}|{self.transaction_id}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def prepare(self) -> Optional[OffsetDiff]:
        """Lee todo lo que está en juego y arma el diff. No escribe nada, ni al equipo ni al archivo."""
        if self.grating not in WRITABLE_GRATINGS:
            self._set(TxState.REFUSED, f"La red {self.grating} no se calibra: sólo se escriben las redes 1 y 2.")
            return None
        if abs(self.requested_offset) > GRAT_OFFSET_MAX_STEPS:
            self._set(TxState.REFUSED, f"{self.requested_offset} pasos está fuera del rango del SDK "
                                       f"(±{GRAT_OFFSET_MAX_STEPS}).")
            return None
        key = self._read_identity()
        if key is None:
            self._set(TxState.READ_FAILED, "No se pudo leer la serie, la red o los puertos del Shamrock. "
                                           "No se escribe nada.")
            return None
        ret, offset_read = self._read_offset()
        if offset_read is None:
            self._set(TxState.READ_FAILED, f"No se pudo leer el offset de la red {self.grating} (código {ret}). "
                                           f"No se escribe nada.")
            return None
        delta = self.requested_offset - offset_read
        if delta == 0:
            self._set(TxState.REFUSED, f"El equipo ya tiene {offset_read} pasos: no hay nada que escribir.")
            return None
        serials = {e.values.get("serial") for e in self.repo.history() if e.kind == "OBSERVED"}
        serials |= {e.key.serial for e in self.repo.history() if e.key is not None}
        serials.discard(None)
        matches = not serials or key.serial in serials
        self.key = key
        self.diff = OffsetDiff(key, offset_read, self.requested_offset, delta, self._clock(),
                               abs(delta) > self.third_threshold_steps,
                               None if self.nm_per_step is None else delta * self.nm_per_step,
                               matches, self._digest(key, offset_read))
        self._set(TxState.DIFF_READY, "")
        return self.diff

    # ── Confirmaciones ──
    def diff_token(self) -> Optional[ConfirmationToken]:
        if self.state != TxState.DIFF_READY or self.diff is None:
            return None
        return ConfirmationToken("diff", self.diff.digest, self._clock())

    def _token_ok(self, token: Optional[ConfirmationToken], stage: str) -> Optional[TxState]:
        """None si el token sirve; si no, el estado de rechazo."""
        if token is None or token.stage != stage or self.diff is None or token.digest != self.diff.digest:
            return TxState.REFUSED
        if self._clock() - token.issued_at > self.token_ttl_s:
            return TxState.TOKEN_EXPIRED
        return None

    def confirm_diff(self, token: Optional[ConfirmationToken]) -> TxState:
        """1.ª confirmación: registra el respaldo (PRE_WRITE). Si el registro falla, no se escribe."""
        if self.state != TxState.DIFF_READY:
            return self._set(TxState.REFUSED, "La transacción no está esperando la 1.ª confirmación.")
        bad = self._token_ok(token, "diff")
        if bad is not None:
            return self._set(bad, "La confirmación venció: volvé a leer." if bad == TxState.TOKEN_EXPIRED
                             else "Confirmación inválida.")
        if not self.diff.serial_matches_file:
            return self._set(TxState.REFUSED, f"El archivo de calibraciones es de otro espectrógrafo "
                                              f"(serie leída {self.diff.key.serial}): no se escribe.")
        entry = CalibrationEntry.pre_write(self.diff.key, transaction_id=self.transaction_id,
                                           offset_read=self.diff.offset_read, requested=self.requested_offset,
                                           source_record_id=self.source_record_id)
        try:
            self.repo.append(entry)
        except OSError as e:
            return self._set(TxState.BACKUP_FAILED, f"No se pudo guardar el respaldo ({e}): no se escribe.")
        self.pre_write_record_id = entry.record_id
        return self._set(TxState.BACKED_UP, f"Respaldo guardado: {self.diff.offset_read} pasos.")

    def write_token(self, *, typed_lines: str, third_confirmed: bool) -> Optional[ConfirmationToken]:
        """2.ª confirmación (y 3.ª si |Δ| > umbral). Sin ellas no hay token."""
        if self.state != TxState.BACKED_UP or self.diff is None:
            return None
        if str(typed_lines).strip() != str(int(round(self.diff.key.lines_per_mm))):
            return None
        if self.diff.needs_third_confirmation and not third_confirmed:
            return None
        return ConfirmationToken("write", self.diff.digest, self._clock())

    def cancel(self) -> None:
        if self.state in (TxState.IDLE, TxState.DIFF_READY, TxState.BACKED_UP):
            self._set(TxState.CANCELLED, "Cancelada: no se escribió nada."
                      + (" El respaldo queda en el archivo." if self.pre_write_record_id else ""))

    # ── Escritura ──
    def _result(self, state: TxState, detail: str, **kw) -> TransactionResult:
        self._set(state, detail)
        self.result = TransactionResult(state, detail, before=self.diff.offset_read if self.diff else None,
                                        requested=self.requested_offset, **kw)
        return self.result

    def _preconditions(self) -> Optional[str]:
        cam = self.camera
        status = cam.get_status_checked()[1] if hasattr(cam, "get_status_checked") else cam.get_status()
        if status == DRV_ACQUIRING:
            cam.abort_acquisition()
        deadline = self._clock() + self.idle_timeout_s
        while True:
            status = cam.get_status_checked()[1] if hasattr(cam, "get_status_checked") else cam.get_status()
            if status != DRV_ACQUIRING:
                break
            if self._clock() >= deadline:
                return "la cámara sigue adquiriendo"
            self._sleep(0.02)
        ret = cam.set_emccd_gain(0)
        ret_r, gain = _gain_reading(cam)
        if ret != DRV_SUCCESS or ret_r != DRV_SUCCESS or gain != 0:
            return f"la ganancia EM no quedó en 0 (leída {gain}, códigos {ret}/{ret_r})"
        try:
            closed = bool(self._close_all())
        except Exception as e:
            closed = False
            print(f"[Offset] close_all_shutters: {e}")
        if not closed:
            return "el cierre de obturadores no se confirmó"
        return None

    def confirm_write(self, token: Optional[ConfirmationToken]) -> TransactionResult:
        if self.state != TxState.BACKED_UP:
            return self._result(TxState.REFUSED, "Sin respaldo confirmado no se escribe.")
        bad = self._token_ok(token, "write")
        if bad is not None:
            return self._result(bad, "La confirmación venció: volvé a leer." if bad == TxState.TOKEN_EXPIRED
                                else "Confirmación inválida.")
        session = self.session
        if session.is_emergency_stopped or not session.acquire_session(self.SESSION_NAME, auto_pause_live=True):
            why = "E-STOP activa" if session.is_emergency_stopped else f"hardware ocupado por '{session.current_owner}'"
            return self._result(TxState.PRECONDITION_FAILED, f"{why}: no se escribió nada.")
        try:
            return self._write_locked()
        finally:
            session.release_session(self.SESSION_NAME, restore_live=True)

    def _write_locked(self) -> TransactionResult:
        ret, now = self._read_offset()
        if now is None:
            return self._result(TxState.STALE_TOKEN, f"No se pudo releer el offset antes de escribir (código {ret}): "
                                                     f"no se escribió nada.")
        if now != self.diff.offset_read:
            return self._result(TxState.STALE_TOKEN, f"El equipo cambió entre la lectura y la escritura: la red "
                                                     f"{self.grating} tenía {self.diff.offset_read} y ahora tiene "
                                                     f"{now}. No se escribió nada.", after=now)
        why = self._preconditions()
        if why:
            return self._result(TxState.PRECONDITION_FAILED, f"{why}: no se escribió nada.")

        spec = self.spectrometer
        ret_g, active = spec.ShamrockGetGrating(_DEVICE)
        ret_w, wl = spec.ShamrockGetWavelength(_DEVICE)
        code_write = spec.ShamrockSetGratingOffset(_DEVICE, self.grating, self.requested_offset)
        code_read, after = self._read_offset()
        if code_write != _SHAMROCK_SUCCESS:
            state, outcome = TxState.WRITE_FAILED, "WRITE_FAILED"
            detail = (f"SetGratingOffset devolvió {code_write}; releído "
                      f"{after if after is not None else 'desconocido'} pasos.")
        elif after is None:
            state, outcome = TxState.READBACK_FAILED, "READBACK_FAILED"
            detail = f"Se escribió, pero la relectura falló (código {code_read}): estado desconocido."
        elif after != self.requested_offset:
            state, outcome = TxState.MISMATCH, "MISMATCH"
            detail = f"Se pidió {self.requested_offset}, se releyó {after}."
        else:
            state, outcome = TxState.CONFIRMED, "CONFIRMED"
            detail = f"Escrito {self.diff.offset_read} → releído {after} pasos."
        # Si la red escrita es la activa, re-emitir la λc vigente (inocuo si no hacía falta)
        if (code_write == _SHAMROCK_SUCCESS and ret_g == _SHAMROCK_SUCCESS and int(active) == self.grating
                and ret_w == _SHAMROCK_SUCCESS):
            spec.ShamrockSetWavelength(_DEVICE, float(wl))
        entry = CalibrationEntry.applied(self.diff.key, transaction_id=self.transaction_id,
                                         requested=self.requested_offset, readback=after, outcome=outcome,
                                         code_write=code_write, code_read=code_read,
                                         source_record_id=self.source_record_id)
        record_error = None
        try:
            self.repo.append(entry)
        except OSError as e:
            record_error = str(e)
            detail += f" (No se pudo registrar el resultado: {e}.)"
        return self._result(state, detail, after=after, code_write=code_write, code_read=code_read,
                            applied_record_id=None if record_error else entry.record_id, record_error=record_error)

    def clone(self) -> "OffsetWriteTransaction":
        """Una transacción nueva con los mismos parámetros, para releer (token vencido u obsoleto)."""
        return OffsetWriteTransaction(self.spectrometer, self.camera, self.repo, grating=self.grating,
                                      requested_offset=self.requested_offset, source_record_id=self.source_record_id,
                                      session=self._session, close_all_shutters=self._close_all, clock=self._clock,
                                      sleep=self._sleep, token_ttl_s=self.token_ttl_s,
                                      third_threshold_steps=self.third_threshold_steps, nm_per_step=self.nm_per_step,
                                      entrance_port=self._ports[0], exit_port=self._ports[1],
                                      idle_timeout_s=self.idle_timeout_s)

    # ── Vuelta al respaldo (R4-D-3) ──
    def backup_return(self) -> Optional["OffsetWriteTransaction"]:
        if self.state not in _BACKUP_RETURN_STATES or self.diff is None or self.pre_write_record_id is None:
            return None
        return OffsetWriteTransaction(self.spectrometer, self.camera, self.repo, grating=self.grating,
                                      requested_offset=self.diff.offset_read,
                                      source_record_id=self.pre_write_record_id, session=self._session,
                                      close_all_shutters=self._close_all, clock=self._clock, sleep=self._sleep,
                                      token_ttl_s=self.token_ttl_s, third_threshold_steps=self.third_threshold_steps,
                                      nm_per_step=self.nm_per_step, entrance_port=self._ports[0],
                                      exit_port=self._ports[1], idle_timeout_s=self.idle_timeout_s)
