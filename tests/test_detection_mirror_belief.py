# -*- coding: utf-8 -*-
"""Creencia sobre la posición del espejo de detección (D-10; R2-arq §2.10; C-08; BANCO-21).

El espejo es un Thorlabs MFF101 en modo conmutador, sin realimentación (BANCO-21): el software sólo sabe lo
que ordenó. La creencia tiene una fuente:
- "none": sin información; la posición es "unknown";
- "commanded": el software lo movió en esta sesión;
- "operator_confirmed": el operador confirmó la posición, sin mover nada (D-10).

El Step & Glue advierte si la creencia no es "down" (R4-A-4).
"""
import pytest

from core import nidaq


@pytest.fixture
def fresh(monkeypatch):
    monkeypatch.setattr(nidaq, "_flipper_notch532_up", True)
    monkeypatch.setattr(nidaq, "_mirror_belief_source", "none")
    monkeypatch.setattr(nidaq, "_mirror_belief_since", None)


def test_without_information_the_position_is_unknown(fresh):
    b = nidaq.get_detection_mirror_belief()
    assert b.position == "unknown" and b.source == "none"


def test_commanding_the_mirror_sets_a_commanded_belief(fresh):
    assert nidaq.flipper_notch532("down")
    b = nidaq.get_detection_mirror_belief()
    assert b.position == "down" and b.source == "commanded" and b.since is not None


def test_operator_confirmation_resyncs_without_moving(fresh, monkeypatch):
    moved = []
    monkeypatch.setattr(nidaq, "flipper_notch532", lambda d: moved.append(d) or True)
    nidaq.confirm_detection_mirror_belief("down")
    b = nidaq.get_detection_mirror_belief()
    assert b.position == "down" and b.source == "operator_confirmed" and moved == []
    with pytest.raises(ValueError):
        nidaq.confirm_detection_mirror_belief("sideways")
