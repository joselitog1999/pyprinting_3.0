# -*- coding: utf-8 -*-
"""La sonda de la cámara de 3.0 (tools/bench/pyspectrum_camera_probe.py; R4-N 2b, P5; BANCO-55).

Contrato:
- conecta como 3.0 (`PylablibAndorCCD`, `CONNECT_KWARGS`) y, sin `--estado-base`, después sólo lee con getters;
- con `--estado-base` aplica el estado base de 3.0 una vez y vuelve a leer; nunca adquiere;
- el JSON va sólo a `--salida`, con el formato de `guardar_info` del legado (comparable);
- `--comparar` muestra las diferencias con el JSON del legado;
- la cámara se cierra siempre, también si algo falla.
"""
import importlib.util
import json
from pathlib import Path

import pytest

PROBE = Path(__file__).resolve().parent.parent / "tools" / "bench" / "pyspectrum_camera_probe.py"
_spec = importlib.util.spec_from_file_location("pyspectrum_camera_probe", PROBE)
probe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(probe)

FORBIDDEN = ("start_acquisition", "stop_acquisition", "snap", "grab", "read_", "wait_for_frame", "setup_shutter",
             "open_shutter", "clear_acquisition", "set_", "setup_")


class _FakeCam:
    def __init__(self, values=None):
        self.calls, self.closed = [], False
        self._values = {"get_full_info": {"temperature_monitor": -60.0, "amp_mode": {"channel": 0, "preamp": 1}},
                        "get_EMCCD_gain": (0, False), "get_fan_mode": "low", "get_pixel_size": (8e-6, 8e-6)}
        self._values.update(values or {})

    def __getattr__(self, attr):
        if attr.startswith("_"):
            raise AttributeError(attr)

        def call(*a, **k):
            self.calls.append(attr)
            v = self._values.get(attr, f"{attr}-ok")
            if isinstance(v, Exception):
                raise v
            return v
        return call

    def close(self):
        self.calls.append("close")
        self.closed = True


def _assert_only_getters(calls):
    for c in calls:
        assert c.startswith(("get_", "is_", "acquisition_in_progress")) or c == "close", f"llamada no permitida: {c}"


def _lines():
    got = []
    return got, got.append


def test_without_base_state_it_only_reads_and_writes_no_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cam = _FakeCam()
    got, out = _lines()
    assert probe.run([], camera_factory=lambda: cam, out=out) == 0
    _assert_only_getters(cam.calls)
    for name in probe.BANCO55_GETTERS + ("get_full_info",):
        assert name in cam.calls, name
    assert cam.closed and list(tmp_path.iterdir()) == []
    assert any("cámara cerrada" in l for l in got)


def test_the_json_goes_only_to_the_requested_path_and_matches_the_legacy_format(tmp_path):
    cam = _FakeCam()
    path = tmp_path / "sub" / "3.0.json"
    assert probe.run(["--salida", str(path)], camera_factory=lambda: cam, out=lambda s: None) == 0
    info = json.loads(path.read_text(encoding="utf-8"))
    assert info["origen"] == "pyspectrum3" and info["estado_base_aplicado"] is False
    assert set(info["settings"]) == set(probe.BANCO55_GETTERS)            # las mismas claves que guardar_info
    assert info["camera_full_info"]["temperature_monitor"] == -60.0
    assert info["conexion"]["temperature"] == -60 and info["conexion"]["fan_mode"] == "low"
    assert all(c["ok"] for c in info["llamadas"]) and info["llamadas"][0]["stage"] == "al conectar"
    assert [p.name for p in tmp_path.rglob("*") if p.is_file()] == ["3.0.json"]


def test_base_state_is_applied_once_only_when_asked_and_read_again(tmp_path):
    cam = _FakeCam()
    applied = []

    class _Report:
        items = []

        def summary(self):
            return "fan_mode=OK"

    def baseline(drv):
        applied.append(drv._cam)
        return _Report()
    path = tmp_path / "base.json"
    assert probe.run(["--estado-base", "--salida", str(path)], camera_factory=lambda: cam, baseline_fn=baseline,
                     out=lambda s: None) == 0
    assert applied == [cam]
    _assert_only_getters(cam.calls)                                       # la sonda misma sólo lee
    info = json.loads(path.read_text(encoding="utf-8"))
    assert info["estado_base"]["resumen"] == "fan_mode=OK"
    assert set(info["despues_estado_base"]["settings"]) == set(probe.BANCO55_GETTERS)
    assert {c["stage"] for c in info["llamadas"]} == {"al conectar", "después del estado base"}
    applied.clear()
    probe.run([], camera_factory=lambda: _FakeCam(), baseline_fn=baseline, out=lambda s: None)
    assert applied == []                                                  # sin la opción, nunca


def test_a_getter_that_fails_is_recorded_and_the_probe_goes_on(tmp_path):
    cam = _FakeCam({"get_vsspeed": RuntimeError("sin SDK")})
    path = tmp_path / "x.json"
    assert probe.run(["--salida", str(path)], camera_factory=lambda: cam, out=lambda s: None) == 0
    info = json.loads(path.read_text(encoding="utf-8"))
    assert "no disponible" in info["settings"]["get_vsspeed"]
    bad = [c for c in info["llamadas"] if not c["ok"]]
    assert [c["call"] for c in bad] == ["get_vsspeed"] and "sin SDK" in bad[0]["detail"]
    assert cam.closed


def test_the_camera_is_closed_even_if_the_base_state_fails():
    cam = _FakeCam()

    def boom(drv):
        raise RuntimeError("falló el estado base")
    with pytest.raises(RuntimeError):
        probe.run(["--estado-base"], camera_factory=lambda: cam, baseline_fn=boom, out=lambda s: None)
    assert cam.closed


def test_without_a_camera_it_says_why_and_exits_2():
    def no_camera():
        raise RuntimeError("Solis abierto")
    got, out = _lines()
    assert probe.run([], camera_factory=no_camera, out=out) == 2
    assert any("Solis abierto" in l for l in got)


def test_compare_shows_the_differences_with_the_legacy_json(tmp_path):
    legacy = {"origen": "legado", "settings": {"get_fan_mode": "full", "get_EMCCD_gain": [0, False]},
              "camera_full_info": {"temperature_monitor": -60.0, "amp_mode": {"channel": 0, "preamp": 2},
                                   "solo_legado": 1}}
    lp = tmp_path / "legado.json"
    lp.write_text(json.dumps(legacy), encoding="utf-8")
    got, out = _lines()
    path = tmp_path / "3.0.json"
    assert probe.run(["--comparar", str(lp), "--salida", str(path)], camera_factory=lambda: _FakeCam(), out=out) == 0
    diffs = json.loads(path.read_text(encoding="utf-8"))["diferencias_con_legado"]
    assert "settings.get_fan_mode: legado 'full' · 3.0 'low'" in diffs
    assert "camera_full_info.amp_mode.preamp: legado 2 · 3.0 1" in diffs
    assert "camera_full_info.solo_legado: legado 1 · 3.0 sin dato" in diffs
    assert not any("get_EMCCD_gain" in d for d in diffs)                  # lista y tupla valen lo mismo
    assert not any("temperature_monitor" in d for d in diffs)
    assert any("Diferencias con el legado" in l for l in got)


def test_an_unreadable_legacy_file_exits_3_and_still_closes(tmp_path):
    cam = _FakeCam()
    assert probe.run(["--comparar", str(tmp_path / "no_existe.json")], camera_factory=lambda: cam,
                     out=lambda s: None) == 3
    assert cam.closed


def test_the_legacy_and_the_3_0_probes_read_the_same_settings():
    legacy_src = (PROBE.parent / "legacy_console_probe.py").read_text(encoding="utf-8")
    ns = {}
    start = legacy_src.index("_BANCO55_GETTERS = (")
    end = legacy_src.index(")\n", start) + 1
    exec(legacy_src[start:end], ns)
    assert tuple(ns["_BANCO55_GETTERS"]) == probe.BANCO55_GETTERS


def test_the_base_state_report_items_go_into_the_json(tmp_path):
    from pyspectrum.modules.camera_baseline import OK, BaselineItem, BaselineReport
    rep = BaselineReport([BaselineItem("fan_mode", 1, 20002, 1, OK)])
    path = tmp_path / "b.json"
    probe.run(["--estado-base", "--salida", str(path)], camera_factory=lambda: _FakeCam(),
              baseline_fn=lambda drv: rep, out=lambda s: None)
    items = json.loads(path.read_text(encoding="utf-8"))["estado_base"]["items"]
    assert items == [{"name": "fan_mode", "requested": 1, "set_code": 20002, "readback": 1, "outcome": "OK",
                      "detail": ""}]
