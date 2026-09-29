# -*- coding: utf-8 -*-
"""Diálogo de escritura de offsets (paso 10, Ronda 3 §1.7 y §2.4, reconciliado en la Ronda 4).

El diálogo conduce la máquina de estados de `OffsetWriteTransaction` y no decide nada por su cuenta:
- Página "Diferencias": lo leído, lo propuesto y el cambio; 1.ª confirmación.
- Respaldo automático.
- Página "Escribir": se habilita al teclear el número de líneas de la red (2.ª confirmación) y, si
  |Δ| > 50 pasos, al tildar la 3.ª confirmación.
- Página "Resultado", con los colores de hardware. Con NO COINCIDE, DESCONOCIDO o ESCRITURA FALLIDA se
  ofrece sólo "Volver al valor del respaldo", que es una transacción nueva (R4-D-3).
- El token vence a los 60 s y el diálogo relee.
- Tiene su propio botón E-STOP (H-01) y ningún botón por defecto (H-23).
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYPRINTING_SAFE", "1")

import pytest
from PyQt6 import QtWidgets

from pyspectrum.calibration.offset_transaction import OffsetWriteTransaction, TxState
from pyspectrum.calibration.repository import CalibrationRepository
from pyspectrum.drivers.andor_ccd_driver import get_andor_ccd
from pyspectrum.drivers.shamrock_driver import DEVICE, GRATING_1200_LINES, SHAMROCK_SUCCESS, get_shamrock
from pyspectrum.modules.hardware_session import HardwareSessionManager
from pyspectrum.ui.offset_write_dialog import OffsetWriteDialog

_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["pytest"])


class _Clock:
    def __init__(self): self.t = 500.0
    def __call__(self): return self.t


@pytest.fixture
def env(tmp_path):
    cam = get_andor_ccd(force_mock=True)
    cam.abort_acquisition()
    spec = get_shamrock(force_mock=True)
    spec._grating_offsets = {1: 87, 2: 195, 3: 60}
    repo = CalibrationRepository(tmp_path / "cal.jsonl")
    session = HardwareSessionManager()
    clock = _Clock()
    estops = []

    def make(requested=192, source="rec-1"):
        return OffsetWriteTransaction(spec, cam, repo, grating=GRATING_1200_LINES, requested_offset=requested,
                                      source_record_id=source, session=session,
                                      close_all_shutters=lambda: True, clock=clock, sleep=lambda s: None)

    def dialog(requested=192):
        return OffsetWriteDialog(lambda: make(requested), estop_callback=lambda: estops.append(1), clock=clock)

    yield dialog, spec, repo, clock, estops
    spec.__dict__.pop("ShamrockSetGratingOffset", None)


def test_opens_on_the_differences_page_without_writing(env):
    dialog, spec, repo, clock, estops = env
    dlg = dialog()
    assert dlg.current_page() == "diff"
    text = dlg.lbl_diff.text()
    assert "195" in text and "192" in text and "−3" in text.replace("-", "−")
    assert "sin S medida" in text                       # sin BANCO-40 no hay estimación en nm
    assert spec.ShamrockGetGratingOffset(DEVICE, GRATING_1200_LINES)[1] == 195 and repo.history() == []


def test_full_flow_with_the_typed_line_count(env):
    dialog, spec, repo, clock, estops = env
    dlg = dialog()
    dlg.btn_confirm_diff.click()
    assert dlg.current_page() == "write"
    assert [e.kind for e in repo.history()] == ["PRE_WRITE"]
    assert not dlg.btn_write.isEnabled()
    dlg.edit_lines.setText("150")
    assert not dlg.btn_write.isEnabled()
    dlg.edit_lines.setText("1200")
    assert dlg.btn_write.isEnabled()
    dlg.btn_write.click()
    assert dlg.current_page() == "result"
    assert "CONFIRMADO" in dlg.lbl_result.text() and "#a6e3a1" in dlg.lbl_result.styleSheet().lower()
    assert spec.ShamrockGetGratingOffset(DEVICE, GRATING_1200_LINES)[1] == 192
    assert dlg.btn_backup_return.isHidden()


def test_large_change_requires_the_third_confirmation(env):
    dialog, spec, repo, clock, estops = env
    dlg = dialog(requested=195 + 312)
    dlg.btn_confirm_diff.click()
    assert not dlg.chk_third.isHidden() and "312" in dlg.chk_third.text()
    dlg.edit_lines.setText("1200")
    assert not dlg.btn_write.isEnabled()
    dlg.chk_third.setChecked(True)
    assert dlg.btn_write.isEnabled()


def test_mismatch_offers_only_the_backup_return(env):
    dialog, spec, repo, clock, estops = env
    def corrupt(device=DEVICE, grating=1, offset=0):          # guarda otro valor: 193 en lugar de 192
        spec._grating_offsets[grating] = offset + 1
        return SHAMROCK_SUCCESS
    spec.ShamrockSetGratingOffset = corrupt
    dlg = dialog()
    dlg.btn_confirm_diff.click()
    dlg.edit_lines.setText("1200")
    dlg.btn_write.click()
    assert "NO COINCIDE" in dlg.lbl_result.text()
    assert not dlg.btn_backup_return.isHidden() and "195" in dlg.btn_backup_return.text()
    child = dlg.build_backup_return_dialog()
    assert child is not None and child.transaction.requested_offset == 195
    assert child.transaction.source_record_id == [e for e in repo.history() if e.kind == "PRE_WRITE"][0].record_id
    assert child.current_page() == "diff"


def test_stale_device_shows_reread(env):
    dialog, spec, repo, clock, estops = env
    dlg = dialog()
    dlg.btn_confirm_diff.click()
    spec._grating_offsets[GRATING_1200_LINES] = 199
    dlg.edit_lines.setText("1200")
    dlg.btn_write.click()
    assert "No se escribió nada" in dlg.lbl_result.text() and not dlg.btn_reread.isHidden()
    dlg.btn_reread.click()
    assert dlg.current_page() == "diff" and "199" in dlg.lbl_diff.text()


def test_confirmation_expires_and_the_dialog_rereads(env):
    dialog, spec, repo, clock, estops = env
    dlg = dialog()
    dlg.btn_confirm_diff.click()
    first = dlg.transaction
    clock.t += 61
    dlg._tick()
    assert dlg.current_page() == "diff" and dlg.transaction is not first


def test_own_estop_button_and_no_default_buttons(env):
    dialog, spec, repo, clock, estops = env
    dlg = dialog()
    dlg.btn_estop.click()
    assert estops == [1]
    for b in dlg.findChildren(QtWidgets.QPushButton):
        assert not b.autoDefault() and not b.isDefault()


def test_backup_return_with_the_device_already_at_the_backup_has_nothing_to_write(env):
    dialog, spec, repo, clock, estops = env
    spec.ShamrockSetGratingOffset = lambda device=DEVICE, grating=1, offset=0: SHAMROCK_SUCCESS   # EEPROM terca
    dlg = dialog()
    dlg.btn_confirm_diff.click()
    dlg.edit_lines.setText("1200")
    dlg.btn_write.click()
    child = dlg.build_backup_return_dialog()
    assert child.current_page() == "read" and "ya tiene 195" in child.lbl_read.text()
