# -*- coding: utf-8 -*-
"""Cierre de PySpectrum con el satélite PyPrinting abierto, en un subproceso (paso 13; R2-arq §7.2).

Un deadlock en el proceso de pytest colgaría la suite entera. En un subproceso con tope de tiempo, el
cuelgue es una falla. Además se verifica, sobre el proceso real (SAFE_MODE):
- una sola pregunta, que nombra la posición de la platina y al satélite;
- el satélite se abrió como huésped y no desconectó la platina ni cerró las tareas DAQ;
- la platina terminó en `config.PI_HOME_POS`.
"""
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

SCRIPT = textwrap.dedent(r'''
    import json, os, sys
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["PYPRINTING_SAFE"] = "1"
    sys.path.insert(0, os.getcwd())
    import config
    from PyQt6 import QtWidgets, QtCore
    app = QtWidgets.QApplication(["close-test"])
    questions = []
    Btn = QtWidgets.QMessageBox.StandardButton
    QtWidgets.QMessageBox.question = staticmethod(lambda *a, **k: questions.append(a[2] if len(a) > 2 else "") or Btn.Yes)
    for name in ("information", "warning", "critical"):
        setattr(QtWidgets.QMessageBox, name, staticmethod(lambda *a, **k: Btn.Ok))
    calls = []
    import core.nidaq as nd
    config.pi.disconnect = lambda *a, **k: calls.append("pi.disconnect")
    import app as pyprinting_app
    pyprinting_app.close_all_tasks = lambda *a, **k: calls.append("close_all_tasks")
    nd.close_all_tasks = lambda *a, **k: calls.append("close_all_tasks")
    from pyspectrum.window import PySpectrumWindow
    win = PySpectrumWindow()
    win.show()
    win._open_microscopio_derecho()
    hosted = getattr(win._microscopio_derecho_backend, "host", None) is not None
    config.pi.MOV([1, 2, 3], [20.0, 30.0, 5.0])
    nd.flipper_notch532("up")
    for _ in range(20):
        app.processEvents()
    win.close()
    for _ in range(20):
        app.processEvents()
    pos = config.pi.qPOS()
    print("RESULT " + json.dumps({"questions": questions, "calls": calls, "hosted": hosted,
                                   "visible": win.isVisible(), "mirror_up": bool(nd._flipper_notch532_up),
                                   "pos": [pos["1"], pos["2"], pos["3"]]}), flush=True)
    os._exit(0)
''')


def test_closing_pyspectrum_with_the_hosted_satellite_does_not_hang_and_parks_the_stage(tmp_path):
    script = tmp_path / "close_test.py"
    script.write_text(SCRIPT, encoding="utf-8")
    env = dict(os.environ)
    try:
        r = subprocess.run([sys.executable, str(script)], cwd=ROOT, env=env, capture_output=True,
                           text=True, errors="replace", timeout=180)
    except subprocess.TimeoutExpired as e:
        pytest.fail(f"El cierre de PySpectrum con el satélite abierto se colgó (V3):\n{(e.stdout or '')[-3000:]}")
    lines = [l for l in r.stdout.splitlines() if l.startswith("RESULT ")]
    assert lines, f"código {r.returncode}\n{r.stdout[-3000:]}\n{r.stderr[-3000:]}"
    res = json.loads(lines[-1][len("RESULT "):])
    import config
    assert res["hosted"] is True
    assert not res["visible"]
    assert len(res["questions"]) == 1, res["questions"]
    q = res["questions"][0]
    x, y, z = (f"{v:g}" for v in config.PI_HOME_POS)
    assert f"({x}, {y}, {z}) µm" in q and "PyPrinting" in q, q
    assert "pi.disconnect" not in res["calls"] and "close_all_tasks" not in res["calls"], res["calls"]
    assert res["mirror_up"] is False                     # el espejo quedó abajo, como en el legado
    assert res["pos"] == pytest.approx([float(v) for v in config.PI_HOME_POS], abs=1e-3), res["pos"]
