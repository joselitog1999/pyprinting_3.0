# -*- coding: utf-8 -*-
"""Transacción de escritura de offsets del Shamrock (paso 10 del bloque A, DEC-040).

Contrato (R2-arq §2.6, R2-inst §3.3; reconciliado en la Ronda 4 con D-07b, D-07c, H-07, H-18, R4-C-4,
R4-C-5 y R4-D-3). La secuencia es:

    leer → diff → 1.ª confirmación → respaldo (PRE_WRITE) → 2.ª confirmación → releer → escribir →
    releer → APPLIED

- La 2.ª confirmación exige teclear el número de líneas de la red ("1200").
- Un |Δ| mayor que `THIRD_CONFIRMATION_STEPS` (50) pide una 3.ª confirmación. No hay tope de política
  (D-07c). Quedan sólo los chequeos de validez: red 1 o 2 y |offset| ≤ 20 000 (rango del SDK).
- Un token vence a los 60 s.
- Si el equipo cambió entre `prepare` y `confirm_write`, el resultado es STALE_TOKEN y no se escribe.
- Sin respaldo registrado no se escribe (BACKUP_FAILED).
- Antes de escribir: sesión tomada, cámara IDLE, ganancia 0 confirmada y obturadores cerrados, porque una
  escritura puede girar la torreta.
- Tras escribir la red activa se re-emite SetWavelength a la λc vigente.
- Con MISMATCH, la única vuelta es "Volver al valor del respaldo": una transacción completa nueva, con
  `source_record_id` del respaldo (R4-D-3). No hay restauración desde el historial.
"""
import pytest

from pyspectrum.calibration.offset_transaction import (
    GRAT_OFFSET_MAX_STEPS, OffsetWriteTransaction, TxState,
)
from pyspectrum.calibration.repository import CalibrationRepository
from pyspectrum.drivers.andor_ccd_driver import DRV_SUCCESS, get_andor_ccd
from pyspectrum.drivers.shamrock_driver import (
    DEVICE, GRATING_150_LINES, GRATING_1200_LINES, GRATING_MIRROR, SHAMROCK_SUCCESS, get_shamrock,
)
from pyspectrum.modules.hardware_session import HardwareSessionManager


class _Clock:
    def __init__(self): self.t = 1000.0
    def __call__(self): return self.t


class _Rig:
    def __init__(self, tmp_path):
        self.cam = get_andor_ccd(force_mock=True)
        self.cam.abort_acquisition()
        self.cam.set_emccd_gain(150)
        self.spec = get_shamrock(force_mock=True)
        self.spec._grating_offsets = {1: 87, 2: 195, 3: 60}
        self.spec._detector_offset = 0
        self.repo = CalibrationRepository(tmp_path / "cal.jsonl")
        self.session = HardwareSessionManager()
        self.clock = _Clock()
        self.closed = []
        self.writes = []
        real = self.spec.ShamrockSetGratingOffset

        def _spy(device=DEVICE, grating=1, offset=0):
            self.writes.append((grating, offset))
            return real(device, grating, offset)
        self.spec.ShamrockSetGratingOffset = _spy

    def tx(self, grating=GRATING_1200_LINES, requested=192, source="rec-proposed"):
        return OffsetWriteTransaction(self.spec, self.cam, self.repo, grating=grating, requested_offset=requested,
                                      source_record_id=source, session=self.session,
                                      close_all_shutters=lambda: self.closed.append(1) or True,
                                      clock=self.clock, sleep=lambda s: None)


@pytest.fixture
def rig(tmp_path):
    r = _Rig(tmp_path)
    yield r
    del r.spec.ShamrockSetGratingOffset          # vuelve al método de la clase


def _run_to_write(tx, typed="1200", third=False):
    diff = tx.prepare()
    assert tx.state == TxState.DIFF_READY, diff
    assert tx.confirm_diff(tx.diff_token()) == TxState.BACKED_UP
    return tx.confirm_write(tx.write_token(typed_lines=typed, third_confirmed=third))


def _kinds(repo):
    return [e.kind for e in repo.history()]


def _gain(cam):
    g = cam.get_emccd_gain()
    return g[1] if isinstance(g, tuple) else g


def test_full_transaction_writes_once_and_records_backup_and_result(rig):
    tx = rig.tx()
    diff = tx.prepare()
    assert (diff.offset_read, diff.requested, diff.delta) == (195, 192, -3)
    assert not diff.needs_third_confirmation
    assert rig.writes == [] and _kinds(rig.repo) == []
    assert tx.confirm_diff(tx.diff_token()) == TxState.BACKED_UP
    assert rig.writes == [] and _kinds(rig.repo) == ["PRE_WRITE"]
    res = tx.confirm_write(tx.write_token(typed_lines="1200", third_confirmed=False))
    assert res.state == TxState.CONFIRMED and (res.before, res.after) == (195, 192)
    assert rig.writes == [(GRATING_1200_LINES, 192)]
    assert _kinds(rig.repo) == ["PRE_WRITE", "APPLIED"]
    applied = rig.repo.history()[-1]
    assert applied.values["outcome"] == "CONFIRMED" and applied.values["source_record_id"] == "rec-proposed"
    assert rig.closed and _gain(rig.cam) == 0          # precondiciones de movimiento
    assert not rig.session.is_busy
    assert rig.repo.reference_state(tx.key).value == 192


def test_no_backup_confirmation_no_write(rig):
    tx = rig.tx()
    tx.prepare()
    res = tx.confirm_write(tx.write_token(typed_lines="1200", third_confirmed=False))
    assert res.state == TxState.REFUSED and rig.writes == []


def test_second_confirmation_needs_the_typed_line_count(rig):
    tx = rig.tx()
    tx.prepare()
    tx.confirm_diff(tx.diff_token())
    assert tx.write_token(typed_lines="150", third_confirmed=False) is None
    assert tx.write_token(typed_lines="", third_confirmed=False) is None
    assert rig.writes == []


def test_backup_failure_aborts_without_writing(rig, monkeypatch):
    tx = rig.tx()
    tx.prepare()
    monkeypatch.setattr(rig.repo, "append", lambda e: (_ for _ in ()).throw(OSError("disco lleno")))
    assert tx.confirm_diff(tx.diff_token()) == TxState.BACKUP_FAILED
    assert tx.write_token(typed_lines="1200", third_confirmed=False) is None
    assert rig.writes == []


def test_device_changed_between_prepare_and_write_is_stale(rig):
    tx = rig.tx()
    tx.prepare()
    tx.confirm_diff(tx.diff_token())
    rig.spec._grating_offsets[GRATING_1200_LINES] = 199         # alguien lo cambió (Solis, el legado)
    res = tx.confirm_write(tx.write_token(typed_lines="1200", third_confirmed=False))
    assert res.state == TxState.STALE_TOKEN and rig.writes == []
    assert "195" in res.detail and "199" in res.detail


def test_tokens_expire_after_60_s(rig):
    tx = rig.tx()
    tx.prepare()
    token = tx.diff_token()
    rig.clock.t += 61
    assert tx.confirm_diff(token) == TxState.TOKEN_EXPIRED
    assert _kinds(rig.repo) == []
    tx.prepare()
    tx.confirm_diff(tx.diff_token())
    wtoken = tx.write_token(typed_lines="1200", third_confirmed=False)
    rig.clock.t += 61
    assert tx.confirm_write(wtoken).state == TxState.TOKEN_EXPIRED and rig.writes == []


def test_large_change_needs_a_third_confirmation_but_has_no_policy_cap(rig):
    tx = rig.tx(requested=195 + 2500)
    diff = tx.prepare()
    assert diff.needs_third_confirmation and diff.delta == 2500
    tx.confirm_diff(tx.diff_token())
    assert tx.write_token(typed_lines="1200", third_confirmed=False) is None
    res = tx.confirm_write(tx.write_token(typed_lines="1200", third_confirmed=True))
    assert res.state == TxState.CONFIRMED and rig.writes == [(GRATING_1200_LINES, 2695)]


@pytest.mark.parametrize("grating, requested", [(GRATING_MIRROR, 61), (4, 10), (GRATING_150_LINES, GRAT_OFFSET_MAX_STEPS + 1),
                                                (GRATING_150_LINES, 87)])
def test_validity_checks_refuse_before_anything(rig, grating, requested):
    tx = rig.tx(grating=grating, requested=requested)
    tx.prepare()
    assert tx.state == TxState.REFUSED and rig.writes == [] and _kinds(rig.repo) == []


def test_read_failure_writes_nothing(rig, monkeypatch):
    monkeypatch.setattr(rig.spec, "ShamrockGetGratingOffset", lambda device=DEVICE, grating=1: (20201, 0))
    tx = rig.tx()
    tx.prepare()
    assert tx.state == TxState.READ_FAILED and rig.writes == []


def test_other_spectrograph_in_the_file_is_refused(rig):
    from pyspectrum.calibration.repository import CalibrationEntry
    rig.repo.append(CalibrationEntry.observed({"serial": "SR-9999", "gratings": {}}))
    tx = rig.tx()
    diff = tx.prepare()
    assert not diff.serial_matches_file
    assert tx.confirm_diff(tx.diff_token()) == TxState.REFUSED
    assert rig.writes == []


def test_emergency_stop_or_busy_session_refuses_the_write(rig):
    tx = rig.tx()
    tx.prepare()
    tx.confirm_diff(tx.diff_token())
    assert rig.session.acquire_session("Step & Glue", auto_pause_live=False)
    res = tx.confirm_write(tx.write_token(typed_lines="1200", third_confirmed=False))
    assert res.state == TxState.PRECONDITION_FAILED and rig.writes == []
    rig.session.release_session("Step & Glue")


def test_gain_that_cannot_be_confirmed_zero_refuses_the_write(rig, monkeypatch):
    tx = rig.tx()
    tx.prepare()
    tx.confirm_diff(tx.diff_token())
    monkeypatch.setattr(rig.cam, "get_emccd_gain", lambda: 12)
    res = tx.confirm_write(tx.write_token(typed_lines="1200", third_confirmed=False))
    assert res.state == TxState.PRECONDITION_FAILED and "12" in res.detail and rig.writes == []


def test_mismatch_is_recorded_and_offers_only_the_backup_return(rig, monkeypatch):
    real_get = rig.spec.ShamrockGetGratingOffset
    tx = rig.tx()
    tx.prepare()
    tx.confirm_diff(tx.diff_token())
    # EEPROM terca: acepta la orden pero no guarda el valor
    rig.spec.ShamrockSetGratingOffset = lambda device=DEVICE, grating=1, offset=0: (
        rig.writes.append((grating, offset)) or SHAMROCK_SUCCESS)
    res = tx.confirm_write(tx.write_token(typed_lines="1200", third_confirmed=False))
    assert res.state == TxState.MISMATCH and (res.before, res.after) == (195, 195)
    applied = rig.repo.history()[-1]
    assert applied.kind == "APPLIED" and applied.values["outcome"] == "MISMATCH"
    back = tx.backup_return()
    assert back is not None and back.requested_offset == 195
    pre_write_id = [e for e in rig.repo.history() if e.kind == "PRE_WRITE"][0].record_id
    assert back.source_record_id == pre_write_id
    assert back.state == TxState.IDLE                      # es una transacción completa nueva
    ok = rig.tx()
    assert ok.backup_return() is None                      # sin falla no hay vuelta


def test_write_failure_is_reported_with_the_reread_state(rig):
    tx = rig.tx()
    tx.prepare()
    tx.confirm_diff(tx.diff_token())
    rig.spec.ShamrockSetGratingOffset = lambda device=DEVICE, grating=1, offset=0: 20201
    res = tx.confirm_write(tx.write_token(typed_lines="1200", third_confirmed=False))
    assert res.state == TxState.WRITE_FAILED and res.code_write == 20201 and res.after == 195
    assert rig.repo.history()[-1].values["outcome"] == "WRITE_FAILED"
    assert tx.backup_return() is not None


def test_writing_the_active_grating_reissues_the_current_wavelength(rig):
    rig.spec.ShamrockSetGrating(DEVICE, GRATING_1200_LINES)
    rig.spec.ShamrockSetWavelength(DEVICE, 550.0)
    calls = []
    real = rig.spec.ShamrockSetWavelength
    rig.spec.ShamrockSetWavelength = lambda device=DEVICE, wavelength=0.0: calls.append(wavelength) or real(device, wavelength)
    res = _run_to_write(rig.tx())
    assert res.state == TxState.CONFIRMED and calls == [pytest.approx(550.0)]
    del rig.spec.ShamrockSetWavelength


def test_cancel_after_backup_leaves_the_backup_and_writes_nothing(rig):
    tx = rig.tx()
    tx.prepare()
    tx.confirm_diff(tx.diff_token())
    tx.cancel()
    assert tx.state == TxState.CANCELLED and rig.writes == []
    assert _kinds(rig.repo) == ["PRE_WRITE"]
    assert tx.write_token(typed_lines="1200", third_confirmed=False) is None


# ── Arquitectura: una sola puerta de escritura ────────────────────────────────

def test_no_offset_setter_outside_the_transaction():
    """Búsqueda en el AST: fuera de la transacción y de los drivers nadie llama a un setter de offsets
    ni al cero de ranura (R2-arq §7.2)."""
    import ast
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    forbidden = {"ShamrockSetGratingOffset", "ShamrockSetDetectorOffset", "ShamrockSetDetectorOffsetEx",
                 "ShamrockSetDetectorOffsetPort2", "ShamrockSetSlitZeroPosition", "set_grating_offset",
                 "set_detector_offset", "set_slit_zero_position", "ShamrockEepromSetOpticalParams"}
    allowed = {root / "pyspectrum/calibration/offset_transaction.py",
               root / "pyspectrum/drivers/shamrock_driver.py"}
    offenders = []
    for folder in ("pyspectrum", "core", "modules", "analysis", "tools"):
        for path in (root / folder).rglob("*.py"):
            if path in allowed:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in forbidden:
                    offenders.append(f"{path.relative_to(root)}:{node.lineno} {node.func.attr}")
    assert offenders == []
