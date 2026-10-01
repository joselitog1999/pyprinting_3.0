# -*- coding: utf-8 -*-
"""La sonda de la consola del legado (tools/bench/legacy_console_probe.py), sobre pylablib (2a, 2026-09-30).

Corre DENTRO del proceso legado, que tiene datos importantes: sólo puede leer. Contrato:
- la cámara, sólo con getters de pylablib sobre el objeto que el legado ya abrió (R4-F/R4-L): nada de
  ctypes contra la DLL, ni set_*, setup_*, start/stop/abort, clear, close ni snap;
- el Shamrock, sólo Get* del objeto del legado (sección D);
- lo que BANCO-55 compara: versión de pylablib, ventilador, VS, amplificador, ganancia, modo de lectura,
  capacidades, tiempos y `get_full_info`;
- `guardar_info(ruta)` escribe un JSON sólo donde se le pide;
- `observar_live()` usa el contador de cuadros de pylablib e informa los cuadros sin leer (BANCO-60).
"""
import builtins
import json
from collections import namedtuple
from pathlib import Path

import pytest

PROBE = Path(__file__).resolve().parent.parent / "tools" / "bench" / "legacy_console_probe.py"
TFramesStatus = namedtuple("TFramesStatus", ["acquired", "unread", "skipped", "buffer_size"])


class _Recorder:
    def __init__(self, name, values):
        self._name, self._values, self.calls = name, values, []

    def __getattr__(self, attr):
        if attr.startswith("_"):
            raise AttributeError(attr)

        def call(*a, **k):
            self.calls.append(attr)
            if attr in self._values:
                v = self._values[attr]
                return v() if callable(v) else v
            return f"{attr}-ok"
        return call


def _cam():
    reads = {"n": 0}

    def status():                                   # cada lectura: 20 cuadros más, 20 más sin leer
        reads["n"] += 1
        return TFramesStatus(100 + 20 * reads["n"], min(3 + 20 * reads["n"], 50), 0, 50)
    cam = _Recorder("cam", {"get_full_info": {"temperature_monitor": -60.0, "amp_mode": (0, 14, 0, 1, 0)},
                            "get_frames_status": status, "acquisition_in_progress": True,
                            "get_pixel_size": (8e-6, 8e-6)})
    type(cam).__name__  # noqa: B018
    return cam


def _run(monkeypatch, cam, spec):
    import __main__
    monkeypatch.setattr(__main__, "myAndor", cam, raising=False)
    monkeypatch.setattr(__main__, "mySpectrometer", spec, raising=False)
    ns = {"__name__": "legacy_probe_test"}
    real_import = builtins.__import__

    def guarded(name, *a, **k):
        if name == "ctypes" or name.startswith("ctypes."):
            raise AssertionError("la sonda no puede usar ctypes contra la cámara (R4-F/R4-L)")
        return real_import(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", guarded)
    exec(compile(PROBE.read_text(encoding="utf-8"), str(PROBE), "exec"), ns)
    monkeypatch.setattr(builtins, "__import__", real_import)
    return ns


def _assert_read_only(calls):
    for c in calls:
        assert c.startswith(("get_", "is_", "acquisition_in_progress", "ShamrockGet")), f"llamada no permitida: {c}"


def test_probe_only_reads_the_camera_and_the_spectrograph(monkeypatch, capsys):
    cam, spec = _cam(), _Recorder("spec", {"ShamrockGetNumberGratings": (20202, 2)})
    ns = _run(monkeypatch, cam, spec)
    out = capsys.readouterr().out
    _assert_read_only(cam.calls + spec.calls)
    assert all(c.startswith("ShamrockGet") for c in spec.calls)
    for needed in ("get_fan_mode", "get_vsspeed", "get_amp_mode", "get_EMCCD_gain", "get_read_mode",
                   "get_capabilities", "get_frame_timings", "get_full_info"):
        assert needed in cam.calls, needed
    assert "pylablib" in out and "RESUMEN" in out
    assert "observar_live" in ns and "guardar_info" in ns


def test_guardar_info_writes_json_only_where_asked(monkeypatch, tmp_path, capsys):
    cam = _cam()
    ns = _run(monkeypatch, cam, _Recorder("spec", {}))
    target = tmp_path / "legado.json"
    ns["guardar_info"](str(target))
    _assert_read_only(cam.calls)
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["origen"] == "legado" and data["camera_full_info"]["temperature_monitor"] == -60.0
    assert "pylablib_version" in data and "resumen" in data


def test_observar_live_uses_the_pylablib_frame_counter(monkeypatch, capsys):
    cam, spec = _cam(), _Recorder("spec", {})
    ns = _run(monkeypatch, cam, spec)
    capsys.readouterr()
    ns["observar_live"](segundos=0.01)
    _assert_read_only(cam.calls + spec.calls)
    out = capsys.readouterr().out
    assert "cuadros en 0.0 s = 20" in out and "CONTINUO" in out
    assert "sin leer = 50 de un búfer de 50" in out       # el puntero de lectura del legado no avanza
