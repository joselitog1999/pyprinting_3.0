# -*- coding: utf-8 -*-
"""Estado leído del espectrómetro (paso 8 del bloque A, D-15; R2-arq §2.4, Ronda 3 §1.1).

- Todo lo que muestra la GUI sale de una instantánea en la que cada campo es un `Reading`:
  - READ_OK, [L]: leído;
  - SENT_OK, [E]: enviado; el SDK no tiene getter y sólo consta el DRV_SUCCESS;
  - READ_FAILED, [!]: falló, con el código;
  - NOT_READ, [?]: sin leer;
  - NOT_CONNECTED, [X]: no conectado.
- **Un valor viejo nunca se muestra como leído.** Con la lectura fallida, `value` es None.
- Seis parámetros sin getter se muestran [E]: modo de lectura, modo de adquisición, ventilador, modo de
  ganancia, índice de VS e índice de HS (D-15, H-09).
- Con pylablib el pre-amp también es [E]: su `get_preamp` es un eco del último valor enviado, no
  `GetCurrentPreAmpGain` (hallazgo del relevamiento del paso 8).
"""
import pytest

from pyspectrum.drivers import specular_interlock as si
from pyspectrum.drivers.andor_ccd_driver import DRV_SUCCESS, DRV_TEMP_STABILIZED, get_andor_ccd
from pyspectrum.drivers.shamrock_driver import DEVICE, get_shamrock
from pyspectrum.modules.camera_baseline import apply_camera_baseline
from pyspectrum.services.spectrometer_state import (
    ReadStatus, Reading, SentRegistry, SpectrometerStateService, read_camera_state, read_spectrograph_state,
)


class _Clock:
    def __init__(self): self.t = 100.0
    def __call__(self): return self.t


def test_marks_and_age():
    clock = _Clock()
    assert Reading(1.0, ReadStatus.READ_OK, DRV_SUCCESS, 100.0).mark(clock) == "[L]"
    assert Reading(1.0, ReadStatus.READ_OK, DRV_SUCCESS, 90.0).mark(clock) == "[L hace 10 s]"
    assert Reading(1, ReadStatus.SENT_OK, DRV_SUCCESS, 100.0).mark(clock) == "[E]"
    assert Reading(None, ReadStatus.READ_FAILED, 20075, 100.0).mark(clock) == "[! 20075]"
    assert Reading(None, ReadStatus.NOT_READ, None, None).mark(clock) == "[?]"
    assert Reading(None, ReadStatus.NOT_CONNECTED, None, None).mark(clock) == "[X]"


def test_sent_registry_marks_sent_or_failed_and_unknown_as_unread():
    reg = SentRegistry(clock=_Clock())
    assert reg.get("fan_mode").status == ReadStatus.NOT_READ
    reg.record("fan_mode", 1, DRV_SUCCESS)
    assert reg.get("fan_mode") == Reading(1, ReadStatus.SENT_OK, DRV_SUCCESS, 100.0)
    reg.record("fan_mode", 0, 20013)
    r = reg.get("fan_mode")
    assert r.status == ReadStatus.READ_FAILED and r.value is None and r.code == 20013


def test_baseline_feeds_the_sent_registry():
    cam = get_andor_ccd(force_mock=True)
    report = apply_camera_baseline(cam)
    reg = SentRegistry()
    reg.record_baseline(report)
    for name in ("fan_mode", "read_mode", "acquisition_mode", "em_gain_mode", "vs_speed_us", "hs_speed_mhz"):
        assert reg.get(name).status == ReadStatus.SENT_OK, name
    assert reg.get("hs_speed_mhz").value == pytest.approx(13.0)
    assert reg.get("vs_speed_us").value == pytest.approx(1.9)


def test_camera_state_reads_what_has_a_getter():
    cam = get_andor_ccd(force_mock=True)
    reg = SentRegistry()
    reg.record_baseline(apply_camera_baseline(cam))
    st = read_camera_state(cam, reg)
    assert st.connection.status == ReadStatus.READ_OK
    assert st.temperature_c.status == ReadStatus.READ_OK and isinstance(st.temperature_c.value, float)
    assert st.cooler_on == Reading(True, ReadStatus.READ_OK, DRV_SUCCESS, st.cooler_on.t_read)
    assert st.em_gain.status == ReadStatus.READ_OK and st.em_gain.value == 0
    assert st.exposure_s.status == ReadStatus.READ_OK
    assert st.fan_mode.status == ReadStatus.SENT_OK
    assert st.hs_speed_mhz.status == ReadStatus.SENT_OK


def test_failed_temperature_is_not_shown_as_a_value(monkeypatch):
    cam = get_andor_ccd(force_mock=True)
    monkeypatch.setattr(cam, "get_temperature", lambda: (20075, -65.0))
    monkeypatch.setattr(cam, "is_cooler_on", lambda: (20075, True))
    st = read_camera_state(cam, SentRegistry())
    assert st.temperature_c.status == ReadStatus.READ_FAILED and st.temperature_c.value is None
    assert st.cooler_on.status == ReadStatus.READ_FAILED and st.cooler_on.value is None


def test_temperature_while_acquiring_is_not_a_fresh_reading(monkeypatch):
    cam = get_andor_ccd(force_mock=True)
    monkeypatch.setattr(cam, "get_temperature", lambda: (20072, -60.0))
    st = read_camera_state(cam, SentRegistry())
    assert st.temperature_c.status == ReadStatus.NOT_READ and st.temperature_c.value is None
    assert "adquiriendo" in st.temperature_c.detail and "-60.0" in st.temperature_c.detail


def test_temperature_status_word():
    cam = get_andor_ccd(force_mock=True)
    st = read_camera_state(cam, SentRegistry())
    assert st.temperature_word in ("estabilizada", "enfriando, todavía no llega", "llegó pero no se estabilizó",
                                   "deriva", "enfriador apagado")


def test_disconnected_camera_is_all_not_connected():
    class _Gone:
        available = False
        unavailable_reason = "pylablib no pudo abrir la cámara"
    st = read_camera_state(_Gone(), SentRegistry())
    assert st.connection.status == ReadStatus.NOT_CONNECTED and "pylablib" in st.connection.detail
    assert st.temperature_c.status == ReadStatus.NOT_CONNECTED and st.fan_mode.status == ReadStatus.NOT_CONNECTED


def test_spectrograph_state_reads_grating_wavelength_slit_and_ports():
    spec = get_shamrock(force_mock=True)
    st = read_spectrograph_state(spec)
    assert st.grating.value == 1 and st.grating_lines_per_mm.value == pytest.approx(150.0)
    assert st.wavelength_nm.value == pytest.approx(532.0)
    assert st.slit_width_um.status == ReadStatus.READ_OK
    assert st.ports.status == ReadStatus.READ_OK and len(st.ports.value) == 2
    assert st.specular == si.FIRST_ORDER


def test_failed_wavelength_is_unknown_and_specular(monkeypatch):
    spec = get_shamrock(force_mock=True)
    monkeypatch.setattr(spec, "ShamrockGetWavelength", lambda device=DEVICE: (20201, 0.0))
    st = read_spectrograph_state(spec)
    assert st.wavelength_nm.status == ReadStatus.READ_FAILED and st.wavelength_nm.value is None
    assert st.specular == si.UNKNOWN


def test_service_publishes_a_snapshot_with_increasing_seq():
    cam, spec = get_andor_ccd(force_mock=True), get_shamrock(force_mock=True)
    svc = SpectrometerStateService(cam, spec, SentRegistry())
    got = []
    svc.snapshotChanged.connect(got.append)
    a = svc.poll()
    b = svc.poll()
    assert got == [a, b] and b.seq == a.seq + 1
    assert a.camera.connection.status == ReadStatus.READ_OK
