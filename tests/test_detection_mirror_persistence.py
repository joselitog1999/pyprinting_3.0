# -*- coding: utf-8 -*-
"""El espejo de detección entre sesiones (C-08; R4-N 3, P6, P7; DEC-040).

- El último estado se guarda junto al archivo de calibraciones después de cada pulso que salió bien y de cada
  confirmación del operador.
- Al arrancar se muestra como "último conocido, sin confirmar": la posición que leen las rutinas sigue siendo
  "unknown" (D-01), así que siguen pidiendo la confirmación. El último conocido sí guía el próximo pulso.
- Un archivo dañado es "sin información".
- [Está arriba] / [Está abajo] sólo registran lo que ve el operador: no mueven el espejo.
- `set_detection_mirror` es el nombre nuevo; `flipper_notch532` queda como alias (P6).
- El archivo de estado del legado se lee, sólo lectura, si `config` da su ruta (P7).
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYPRINTING_SAFE", "1")

import json

import pytest
from PyQt6 import QtWidgets

import config
from core import detection_mirror_state as dms
from core import nidaq

_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["pytest"])
_KEEP_ALIVE = []


@pytest.fixture
def state_file(tmp_path, monkeypatch):
    path = tmp_path / "estado" / "detection_mirror.json"
    monkeypatch.setattr(config, "DETECTION_MIRROR_STATE_PATH", str(path), raising=False)
    monkeypatch.setattr(config, "LEGACY_DETECTION_MIRROR_STATUS_FILE", None, raising=False)
    monkeypatch.setattr(nidaq, "_flipper_notch532_up", True)
    monkeypatch.setattr(nidaq, "_mirror_belief_source", "none")
    monkeypatch.setattr(nidaq, "_mirror_belief_since", None)
    monkeypatch.setattr(nidaq, "_mirror_last_known", None)
    return path


# ── El archivo ──────────────────────────────────────────────────────────────────────────────

def test_save_and_load_round_trip_without_leftovers(state_file):
    assert dms.save_state("down", "operator_confirmed", 1000.0)
    got = dms.load_state()
    assert got == dms.SavedMirrorState("down", "operator_confirmed", 1000.0)
    assert [p.name for p in state_file.parent.iterdir()] == ["detection_mirror.json"]   # sin el temporal


@pytest.mark.parametrize("content", ["no es json", json.dumps({"position": "sideways", "source": "commanded",
                                                                "since": 1.0}),
                                     json.dumps({"position": "down"}), ""])
def test_a_damaged_file_is_no_information(state_file, content):
    state_file.parent.mkdir(parents=True)
    state_file.write_text(content, encoding="utf-8")
    assert dms.load_state() is None


def test_the_default_path_is_next_to_the_calibration_file(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DETECTION_MIRROR_STATE_PATH", None, raising=False)
    monkeypatch.setattr(config, "SHAMROCK_CALIBRATION_PATH", str(tmp_path / "cal" / "shamrock_calibration.jsonl"))
    assert dms.state_path() == tmp_path / "cal" / "detection_mirror.json"


def test_a_write_failure_returns_false_and_does_not_raise(tmp_path):
    blocker = tmp_path / "archivo"
    blocker.write_text("x", encoding="utf-8")
    assert dms.save_state("up", "commanded", path=blocker / "dentro" / "m.json") is False


# ── La creencia en nidaq ────────────────────────────────────────────────────────────────────

def test_a_pulse_and_a_confirmation_are_saved(state_file):
    assert nidaq.set_detection_mirror("down")
    assert dms.load_state().position == "down" and dms.load_state().source == "commanded"
    nidaq.confirm_detection_mirror_belief("up")
    saved = dms.load_state()
    assert saved.position == "up" and saved.source == "operator_confirmed"


def test_at_startup_the_last_known_is_shown_but_not_trusted(state_file):
    dms.save_state("down", "operator_confirmed", 1234.0)
    nidaq.load_last_known_mirror_state()
    b = nidaq.get_detection_mirror_belief()
    assert b.position == "unknown" and b.source == "none"                 # las rutinas siguen pidiendo (D-01)
    assert b.last_known == "down" and b.last_known_since == 1234.0
    assert nidaq._flipper_notch532_up is False                            # guía el próximo pulso


def test_after_a_confirmation_the_last_known_is_the_new_state(state_file):
    dms.save_state("down", "commanded", 1.0)
    nidaq.load_last_known_mirror_state()
    nidaq.confirm_detection_mirror_belief("up")
    b = nidaq.get_detection_mirror_belief()
    assert b.position == "up" and b.source == "operator_confirmed" and b.last_known == "up"


def test_a_damaged_file_at_startup_leaves_no_information(state_file):
    state_file.parent.mkdir(parents=True)
    state_file.write_text("{", encoding="utf-8")
    nidaq.load_last_known_mirror_state()
    b = nidaq.get_detection_mirror_belief()
    assert b.position == "unknown" and b.last_known is None and nidaq._flipper_notch532_up is True


def test_the_old_name_is_an_alias_of_the_new_one(state_file, monkeypatch):
    seen = []
    monkeypatch.setattr(nidaq, "set_detection_mirror", lambda d: seen.append(d) or True)
    assert nidaq.flipper_notch532("down") and seen == ["down"]


def test_a_failed_save_does_not_fail_the_pulse(state_file, monkeypatch):
    monkeypatch.setattr(dms, "save_state", lambda *a, **k: False)
    assert nidaq.set_detection_mirror("down")
    assert nidaq.get_detection_mirror_belief().position == "down"


def test_step_and_glue_still_asks_with_only_a_last_known(state_file, monkeypatch):
    """Con "último conocido: abajo" el Step & Glue abre el diálogo del espejo, como sin información."""
    from pyspectrum.modules.step_and_glue import Frontend
    dms.save_state("down", "operator_confirmed", 1.0)
    nidaq.load_last_known_mirror_state()
    asked = []
    monkeypatch.setattr(QtWidgets.QMessageBox, "exec", lambda self: asked.append(self.text()) or 0)
    fe = Frontend()
    _KEEP_ALIVE.append(fe)
    assert fe._confirm_mirror() is False                                  # cancelado: no siguió solo
    assert asked and "no sabe" in asked[0]


# ── El legado (P7) ──────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("content,expected", [("0", "up"), ("1\n", "down"), ("x", None), ("", None)])
def test_the_legacy_file_is_read_only_if_configured(tmp_path, monkeypatch, content, expected):
    legacy = tmp_path / "flipper_notch532_status.txt"
    legacy.write_text(content, encoding="utf-8")
    monkeypatch.setattr(config, "LEGACY_DETECTION_MIRROR_STATUS_FILE", str(legacy), raising=False)
    assert dms.read_legacy_state() == expected
    assert legacy.read_text(encoding="utf-8") == content                  # no lo toca
    monkeypatch.setattr(config, "LEGACY_DETECTION_MIRROR_STATUS_FILE", None, raising=False)
    assert dms.read_legacy_state() is None and dms.read_legacy_states() == []


def test_both_legacy_files_are_shown(tmp_path, monkeypatch):
    a, b = tmp_path / "ppl.txt", tmp_path / "psl.txt"
    a.write_text("1", encoding="utf-8")
    b.write_text("0", encoding="utf-8")
    monkeypatch.setattr(config, "LEGACY_DETECTION_MIRROR_STATUS_FILE", f"{a};{b}", raising=False)
    assert dms.read_legacy_states() == [(str(a), "down"), (str(b), "up")]


# ── El panel izquierdo ──────────────────────────────────────────────────────────────────────

@pytest.fixture
def panel(state_file):
    from pyspectrum.drivers.andor_ccd_driver import get_andor_ccd
    from pyspectrum.drivers.shamrock_driver import get_shamrock
    from pyspectrum.ui.left_hardware_panel import LeftHardwarePanel
    p = LeftHardwarePanel(get_andor_ccd(force_mock=True), get_shamrock(force_mock=True))
    _KEEP_ALIVE.append(p)
    p._refresh_timer.stop()
    return p


def test_the_resync_buttons_only_record_what_the_operator_sees(panel, monkeypatch):
    moved = []
    monkeypatch.setattr(nidaq, "set_detection_mirror", lambda d: moved.append(d) or True)
    panel.btn_mirror_is_down.click()
    b = nidaq.get_detection_mirror_belief()
    assert moved == [] and b.position == "down" and b.source == "operator_confirmed"
    assert "abajo" in panel.lbl_mirror_state.text() and "confirmado" in panel.lbl_mirror_state.text()
    panel.btn_mirror_is_up.click()
    assert moved == [] and nidaq.get_detection_mirror_belief().position == "up"
    assert dms.load_state().position == "up"


def test_the_panel_says_last_known_unconfirmed(panel):
    dms.save_state("down", "commanded", 1.0)
    nidaq.load_last_known_mirror_state()
    panel._refresh_mirror()
    text = panel.lbl_mirror_state.text()
    assert "abajo" in text and "último conocido" in text and "sin confirmar" in text


def test_the_panel_says_unknown_without_information(panel):
    panel._refresh_mirror()
    assert "desconocido" in panel.lbl_mirror_state.text()


def test_the_panel_shows_what_the_legacy_says(panel, tmp_path, monkeypatch):
    legacy = tmp_path / "flipper_notch532_status.txt"
    legacy.write_text("1", encoding="utf-8")
    monkeypatch.setattr(config, "LEGACY_DETECTION_MIRROR_STATUS_FILE", str(legacy), raising=False)
    panel._refresh_mirror()
    assert "el legado dice: abajo" in panel.lbl_mirror_legacy.text() and not panel.lbl_mirror_legacy.isHidden()
    monkeypatch.setattr(config, "LEGACY_DETECTION_MIRROR_STATUS_FILE", None, raising=False)
    panel._refresh_mirror()
    assert panel.lbl_mirror_legacy.isHidden()


def test_loading_starts_a_new_session_without_a_confirmation(state_file):
    nidaq.confirm_detection_mirror_belief("down")
    nidaq.load_last_known_mirror_state()                                  # como al abrir el programa otra vez
    b = nidaq.get_detection_mirror_belief()
    assert b.position == "unknown" and b.source == "none" and b.last_known == "down"
