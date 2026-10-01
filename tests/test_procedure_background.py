# -*- coding: utf-8 -*-
"""Fondo de los procedimientos (R4-N, Rondas 1 a 3 aprobadas el 2026-09-30; DEC-040).

Contrato:
- el fondo se toma como una referencia de la medición: la misma exposición, la misma configuración de la
  cámara y, por defecto, la misma cantidad de cuadros (pregunta 6);
- vale mientras no cambien las condiciones (exposición, ganancia EM, amplificador, preamplificador, HS,
  VS, modo de lectura y sus parámetros, forma del cuadro y setpoint de temperatura). Sin luz no depende
  de la red ni de λc: no forman parte de las condiciones (pregunta 1);
- un fondo por corrida y reutilizado mientras las condiciones sigan iguales; sólo en memoria (pregunta 2);
- método "obturador cerrado" (por defecto; se verifica el cierre) o "todo apagado" (lo apaga el operador;
  se rechaza si hay un láser abierto);
- se guarda aparte de los datos: crudo y fondo por separado (B3).
"""
import json

import numpy as np
import pytest

from pyspectrum.services import procedure_background as pb

OK = 20002


class _Cam:
    def __init__(self, **kw):
        self.values = dict(exposure=0.1, gain=0, oamp=0, preamp=1, hs=0, vs=1, read_mode=0, track=(501, 40),
                           setpoint=-60.0, temperature=-59.8)
        self.values.update(kw)
        self.exposures = []

    def get_exposure_time_checked(self): return (OK, self.values["exposure"])
    def get_emccd_gain(self): return (OK, self.values["gain"])
    def get_output_amplifier(self): return self.values["oamp"]
    def get_preamp_gain_index(self): return self.values["preamp"]
    def get_hs_speed_index(self): return self.values["hs"]
    def get_vs_speed_index(self): return self.values["vs"]
    def get_read_mode(self): return self.values["read_mode"]
    def get_single_track(self): return self.values["track"]
    def get_temperature_setpoint(self): return self.values["setpoint"]
    def get_temperature(self): return (OK, self.values["temperature"])


class _Spec:
    def __init__(self, shutter_ok=True):
        self.shutter_ok, self.calls = shutter_ok, []

    def ShamrockSetShutter(self, dev, state):
        self.calls.append(("usb", state))
        return 20202 if self.shutter_ok else 20201

    def ShamrockGetShutter(self, dev):
        return (20202, 0)


def _expose_factory(values):
    it = iter(values)

    def expose(shape, exposure_s):
        return np.full(shape, float(next(it)))
    return expose


# ── Condiciones ─────────────────────────────────────────────────────────────────────────────

def test_conditions_use_the_requested_exposure_and_ignore_grating_and_lambda():
    c = pb.read_conditions(_Cam(exposure=0.5), (1004,), exposure_s=0.1)
    assert c.exposure_s == 0.1 and c.shape == (1004,) and c.read_mode == 0
    assert not hasattr(c, "grating") and not hasattr(c, "center_nm")
    assert c.temperature_setpoint_c == -60.0


def test_single_track_parameters_are_part_of_the_conditions():
    a = pb.read_conditions(_Cam(read_mode=3, track=(501, 40)), (1004,), exposure_s=0.1)
    b = pb.read_conditions(_Cam(read_mode=3, track=(480, 40)), (1004,), exposure_s=0.1)
    assert a.read_params == (501, 40) and pb.differences(a, b)


@pytest.mark.parametrize("kw,word", [(dict(gain=10), "ganancia EM"), (dict(oamp=1), "amplificador"),
                                     (dict(preamp=2), "preamplificador"), (dict(hs=1), "HS"), (dict(vs=0), "VS"),
                                     (dict(read_mode=3), "modo de lectura"), (dict(setpoint=-50.0), "temperatura")])
def test_every_condition_invalidates(kw, word):
    a = pb.read_conditions(_Cam(), (1004,), exposure_s=0.1)
    b = pb.read_conditions(_Cam(**kw), (1004,), exposure_s=0.1)
    assert any(word in d for d in pb.differences(a, b))


def test_exposure_and_shape_invalidate():
    a = pb.read_conditions(_Cam(), (1004,), exposure_s=0.1)
    assert any("exposición" in d for d in pb.differences(a, pb.read_conditions(_Cam(), (1004,), exposure_s=0.2)))
    assert any("forma" in d for d in pb.differences(a, pb.read_conditions(_Cam(), (1, 1004), exposure_s=0.1)))


def test_an_unreadable_condition_invalidates():
    a = pb.read_conditions(_Cam(), (1004,), exposure_s=0.1)
    cam = _Cam()
    cam.get_vs_speed_index = lambda: (_ for _ in ()).throw(RuntimeError("USB"))
    assert any("no se pudo leer" in d for d in pb.differences(a, pb.read_conditions(cam, (1004,), exposure_s=0.1)))


# ── Adquisición ─────────────────────────────────────────────────────────────────────────────

def test_shutter_method_confirms_the_close_and_averages_fresh_frames():
    cam, spec = _Cam(), _Spec()
    cond = pb.read_conditions(cam, (4,), exposure_s=0.1)
    d = pb.acquire_dark(cam, spec, cond, n_frames=3, method=pb.METHOD_SHUTTER,
                        expose=_expose_factory([1, 2, 6]), open_lasers=lambda: [])
    assert ("usb", 0) in spec.calls
    np.testing.assert_allclose(d.mean, 3.0)
    assert d.n_frames == 3 and d.method == pb.METHOD_SHUTTER and "cerrado" in d.shutter_note
    assert d.conditions == cond and d.temperature_c == -59.8 and d.id
    assert d.mean.dtype == np.float32 and d.std.shape == (4,)


def test_shutter_method_refuses_if_the_close_is_not_confirmed():
    cam = _Cam()
    with pytest.raises(pb.DarkError, match="obturador"):
        pb.acquire_dark(cam, _Spec(shutter_ok=False), pb.read_conditions(cam, (4,), exposure_s=0.1), n_frames=1,
                        method=pb.METHOD_SHUTTER, expose=_expose_factory([1]), open_lasers=lambda: [])


def test_all_off_method_touches_nothing_and_refuses_with_an_open_laser():
    cam, spec = _Cam(), _Spec()
    cond = pb.read_conditions(cam, (4,), exposure_s=0.1)
    d = pb.acquire_dark(cam, spec, cond, n_frames=1, method=pb.METHOD_ALL_OFF,
                        expose=_expose_factory([5]), open_lasers=lambda: [])
    assert spec.calls == [] and d.method == pb.METHOD_ALL_OFF and "apagado" in d.shutter_note
    with pytest.raises(pb.DarkError, match="532"):
        pb.acquire_dark(cam, spec, cond, n_frames=1, method=pb.METHOD_ALL_OFF,
                        expose=_expose_factory([5]), open_lasers=lambda: ["532 nm (green)"])


def test_single_frame_dark_has_zero_std():
    cam = _Cam()
    d = pb.acquire_dark(cam, _Spec(), pb.read_conditions(cam, (4,), exposure_s=0.1), n_frames=1,
                        method=pb.METHOD_SHUTTER, expose=_expose_factory([7]), open_lasers=lambda: [])
    np.testing.assert_allclose(d.std, 0.0)


# ── Almacén: se reutiliza mientras no cambien las condiciones ───────────────────────────────

def _dark(cam=None, exposure=0.1, value=1.0):
    cam = cam or _Cam()
    return pb.acquire_dark(cam, _Spec(), pb.read_conditions(cam, (4,), exposure_s=exposure), n_frames=1,
                           method=pb.METHOD_SHUTTER, expose=_expose_factory([value]), open_lasers=lambda: [])


def test_store_reuses_while_conditions_do_not_change_and_says_what_changed():
    store = pb.DarkStore()
    d = _dark()
    store.put(d)
    assert store.get_valid(d.conditions) is d
    other = pb.read_conditions(_Cam(gain=5), (4,), exposure_s=0.1)
    assert store.get_valid(other) is None
    state, dark, reason = store.status(other)
    assert state == "invalid" and dark is d and "ganancia EM" in reason
    assert store.status(d.conditions)[0] == "valid"
    assert pb.DarkStore().status(d.conditions)[0] == "none"


def test_store_keeps_one_dark_per_condition_set_and_discards():
    store = pb.DarkStore()
    a, b = _dark(exposure=0.1), _dark(exposure=0.2)
    store.put(a)
    store.put(b)
    assert store.get_valid(a.conditions) is a and store.get_valid(b.conditions) is b
    store.discard(a.conditions)
    assert store.get_valid(a.conditions) is None and store.get_valid(b.conditions) is b
    store.clear()
    assert store.get_valid(b.conditions) is None


def test_global_store_is_a_singleton():
    assert pb.get_dark_store() is pb.get_dark_store()


# ── Guardado: crudo y fondo por separado ────────────────────────────────────────────────────

def test_npz_and_header_lines(tmp_path):
    d = _dark(value=3.0)
    path = pb.save_dark_npz(d, tmp_path, "LuminescenceGrid")
    with np.load(path) as z:
        np.testing.assert_allclose(z["mean"], 3.0)
        meta = json.loads(str(z["metadata"]))
    assert meta["id"] == d.id and meta["method"] == pb.METHOD_SHUTTER and meta["conditions"]["exposure_s"] == 0.1
    assert path.name == f"LuminescenceGrid_background_{d.id}.npz"
    lines = pb.dark_header_lines(d, path)
    assert f"background_id: {d.id}" in lines and any(l.startswith("background_file: ") for l in lines)
    assert pb.dark_header_lines(None, None) == ["background_id: ninguno"]


def test_h5_group(tmp_path):
    h5py = pytest.importorskip("h5py")
    d = _dark(value=2.0)
    with h5py.File(tmp_path / "a.h5", "w") as f:
        pb.write_dark_h5(f, d)
    with h5py.File(tmp_path / "a.h5", "r") as f:
        g = f["background"]
        np.testing.assert_allclose(g["mean"][()], 2.0)
        assert g.attrs["id"] == d.id and g.attrs["method"] == pb.METHOD_SHUTTER
        assert json.loads(g.attrs["conditions_json"])["exposure_s"] == 0.1


# ── ensure_dark / take_dark: la lógica común de rutinas de grilla y Step & Glue ─────────────

class _SpecReopen(_Spec):
    """Cierra bien y no vuelve a abrir."""
    def ShamrockSetShutter(self, dev, state):
        self.calls.append(("usb", state))
        return 20202 if state == 0 else 20201


def test_ensure_dark_reuses_and_takes_with_shutter(monkeypatch):
    cam, spec, store = _Cam(), _Spec(), pb.DarkStore()
    cond = pb.read_conditions(cam, (4,), exposure_s=0.1)
    d1 = pb.ensure_dark(cam, spec, cond, method=pb.METHOD_SHUTTER, n_frames=1, expose=_expose_factory([1, 9]),
                        store=store, open_lasers=lambda: [])
    d2 = pb.ensure_dark(cam, spec, cond, method=pb.METHOD_SHUTTER, n_frames=1, expose=_expose_factory([9]),
                        store=store, open_lasers=lambda: [])
    assert d1 is d2 and spec.calls == [("usb", 0), ("usb", 1)]       # cerrado, tomado, reabierto; una vez


def test_ensure_dark_never_takes_all_off_by_itself():
    cam, store = _Cam(), pb.DarkStore()
    cond = pb.read_conditions(cam, (4,), exposure_s=0.1)
    with pytest.raises(pb.DarkMissing, match="Tomar fondo ahora"):
        pb.ensure_dark(cam, _Spec(), cond, method=pb.METHOD_ALL_OFF, n_frames=1, expose=_expose_factory([1]),
                       store=store, open_lasers=lambda: [])


def test_take_dark_fails_if_the_shutter_does_not_reopen():
    cam, store = _Cam(), pb.DarkStore()
    cond = pb.read_conditions(cam, (4,), exposure_s=0.1)
    with pytest.raises(pb.DarkError, match="no volvió a abrir"):
        pb.take_dark(cam, _SpecReopen(), cond, method=pb.METHOD_SHUTTER, n_frames=1, expose=_expose_factory([1]),
                     store=store, open_lasers=lambda: [])
    assert store.get_valid(cond) is None


def test_take_dark_reopens_even_if_the_exposure_fails():
    cam, spec = _Cam(), _Spec()
    cond = pb.read_conditions(cam, (4,), exposure_s=0.1)

    def boom(shape, exp):
        raise pb.DarkError("la exposición falló")
    with pytest.raises(pb.DarkError):
        pb.take_dark(cam, spec, cond, method=pb.METHOD_SHUTTER, n_frames=1, expose=boom, store=pb.DarkStore(),
                     open_lasers=lambda: [])
    assert spec.calls == [("usb", 0), ("usb", 1)]
