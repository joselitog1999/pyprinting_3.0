# -*- coding: utf-8 -*-
"""
test_spectral_geometry_and_step_coverage.py — Geometría espectral verificada y Step & Glue sin huecos.

PyPrinting 3.0 — UNSAM Nanofotónica (DEC-033)

El pitch del detector estuvo declarado como 13 µm cuando el iXon3 885 (cabezal `DU8285_VP`,
sensor TI TC285SPD) tiene 8 µm. El error no vivía sólo en un overlay: las dispersiones
0.175 / 0.022 nm/px planificaban el Step & Glue con ventanas de 176 / 22 nm cuando las reales
son de 103 / 11.6 nm, y en hardware el barrido habría dejado ~30 % del rango sin medir. Ningún
test lo vio porque el mock usaba el MISMO número equivocado que el planificador.

Por eso el oráculo de este archivo son las hojas de datos escritas como literales, no las
constantes del código: si el test derivara su expectativa de la constante que verifica, un
valor equivocado se confirmaría a sí mismo.

Cubre:
1. Pitch y dispersión contra las hojas de datos, y consistencia con la ventana medida del legado.
2. Paridad del mock: su calibración se deriva del ancho de píxel configurado.
3. `configure_detector_geometry()`: el driver real le informa la geometría al SDK del Shamrock
   y la relee antes de declararla verificada; la fábrica lo hace antes de cualquier calibración.
4. Planificación: ventana medida, precedencia y regla de corte sin ventana sobrante.
5. `coverage_gaps_nm()` y el Step & Glue de punta a punta sin huecos.
"""
import math
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ["PYPRINTING_SAFE"] = "1"
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import numpy as np
from PyQt6 import QtWidgets

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

from pyspectrum.drivers import shamrock_driver as sd
from pyspectrum.drivers.andor_ccd_driver import get_andor_ccd, READ_MODE_FVB
from pyspectrum.drivers.shamrock_driver import (
    _MockShamrock, ShamrockDriver, get_shamrock,
    SHAMROCK_SUCCESS, SHAMROCK_COMMUNICATION_ERROR, SHAMROCK_P2INVALID,
)
from pyspectrum.calibration.halogen_lamp import compute_step_centers
from pyspectrum.modules.hardware_session import hardware_session
from pyspectrum.modules.step_and_glue import Frontend, Backend

# ── Oráculo independiente del código bajo prueba ─────────────────────────────
DATASHEET_PITCH_UM = 8.0          # Andor iXon3 885 y TI TC285SPD-30: "8 x 8 µm"
DATASHEET_WIDTH_PX = 1004         # 1004 (H) x 1002 (V) píxeles activos
# Andor Shamrock 500i, "Nominal dispersion (nm/mm)": 150 l/mm blaze 800 y 1200 l/mm blaze 500,
# las dos redes instaladas en el laboratorio (encabezado de los .sif de Solis en reserva/).
DATASHEET_DISPERSION_NM_PER_MM = {1: 12.83, 2: 1.44}
# Ventana "estimativa" que el legado usó durante años (StepandGlue_ps.py:576).
LEGACY_WINDOW_NM = {1: 103.0, 2: 12.0}


def _datasheet_window_nm(grating):
    return DATASHEET_DISPERSION_NM_PER_MM[grating] * DATASHEET_WIDTH_PX * DATASHEET_PITCH_UM / 1000.0


def _span(axis):
    axis = np.asarray(axis, dtype=np.float64)
    return float(axis.max() - axis.min())


# ── 1. Pitch y dispersión ────────────────────────────────────────────────────

class TestGeometryAgainstDatasheets(unittest.TestCase):

    def test_pitch_constant_is_datasheet_value(self):
        from pyspectrum.drivers.andor_ccd_driver import DETECTOR_PIXEL_PITCH_UM
        self.assertEqual(DETECTOR_PIXEL_PITCH_UM, DATASHEET_PITCH_UM)

    def test_nominal_window_matches_datasheet_and_legacy(self):
        from pyspectrum.drivers.shamrock_driver import nominal_window_nm
        for g in (1, 2):
            self.assertAlmostEqual(nominal_window_nm(g), _datasheet_window_nm(g), places=6)
            # Contraste independiente: la ventana que el legado midió en el banco.
            self.assertLess(abs(nominal_window_nm(g) - LEGACY_WINDOW_NM[g]), 0.5)

    def test_mirror_has_no_dispersion(self):
        from pyspectrum.drivers.shamrock_driver import nominal_dispersion_nm_per_px, GRATING_MIRROR
        self.assertEqual(nominal_dispersion_nm_per_px(GRATING_MIRROR), 0.0)


# ── 2. Paridad del mock ──────────────────────────────────────────────────────

class TestMockSpectrographParity(unittest.TestCase):
    """Instancias propias del mock: mutar el pitch del singleton contaminaría otros tests."""

    def setUp(self):
        self.m = _MockShamrock()

    def test_mock_window_matches_datasheet_physics(self):
        for g in (1, 2):
            self.m.ShamrockSetGrating(0, g)
            self.m.ShamrockSetWavelength(0, 650.0)
            _, wl = self.m.ShamrockGetCalibration(0, DATASHEET_WIDTH_PX)
            self.assertAlmostEqual(_span(wl), _datasheet_window_nm(g), places=6,
                                   msg=f"red {g}: el mock no reproduce la ventana física")

    def test_mock_cubic_dispersion_matches_datasheet(self):
        self.m.ShamrockSetGrating(0, 1)
        ret, (a, b, c, d) = self.m.get_pixel_calibration_coefficients(0)
        self.assertEqual(ret, SHAMROCK_SUCCESS)
        self.assertAlmostEqual(b, 12.83 * DATASHEET_PITCH_UM / 1000.0, places=9)

    def test_mock_window_follows_configured_pixel_width(self):
        self.m.ShamrockSetGrating(0, 1)
        _, wl8 = self.m.ShamrockGetCalibration(0, DATASHEET_WIDTH_PX)
        self.assertEqual(self.m.set_pixel_width(0, 13.0), SHAMROCK_SUCCESS)
        _, wl13 = self.m.ShamrockGetCalibration(0, DATASHEET_WIDTH_PX)
        self.assertAlmostEqual(_span(wl13) / _span(wl8), 13.0 / 8.0, places=9)

    def test_mock_models_geometry_configuration(self):
        self.assertFalse(self.m.geometry_verified)
        self.assertEqual(self.m.configure_detector_geometry(), SHAMROCK_SUCCESS)
        self.assertEqual(self.m.get_number_pixels(0), (SHAMROCK_SUCCESS, DATASHEET_WIDTH_PX))
        self.assertEqual(self.m.get_pixel_width(0), (SHAMROCK_SUCCESS, DATASHEET_PITCH_UM))
        self.assertTrue(self.m.geometry_verified)

    def test_mock_rejects_nonphysical_geometry(self):
        self.assertEqual(self.m.set_pixel_width(0, 0.0), SHAMROCK_P2INVALID)
        self.assertEqual(self.m.set_number_pixels(0, 0), SHAMROCK_P2INVALID)

    def test_factory_configures_the_mock(self):
        with patch.object(sd, "_shamrock_instance", None):
            inst = get_shamrock(force_mock=True)
            self.assertTrue(inst.geometry_verified)


# ── 3. Driver real con DLL falsa ─────────────────────────────────────────────

class _GeometryDll:
    """DLL falsa del Shamrock: guarda la geometría que recibe y registra el orden de llamadas."""

    def __init__(self, readback_width=None, set_width_ret=SHAMROCK_SUCCESS, raise_on=()):
        self.calls = []
        self._n = 0
        self._w = 0.0
        self._readback_width = readback_width
        self._set_width_ret = set_width_ret
        self._raise_on = set(raise_on)

    def _log(self, name, *args):
        self.calls.append((name,) + args)
        if name in self._raise_on:
            raise OSError(f"exception: access violation in {name}")

    def ShamrockInitialize(self, inipath):
        self._log("ShamrockInitialize")
        return SHAMROCK_SUCCESS

    def ShamrockClose(self):
        self._log("ShamrockClose")
        return SHAMROCK_SUCCESS

    def ShamrockSetNumberPixels(self, device, n):
        self._log("ShamrockSetNumberPixels", device.value, n.value)
        self._n = n.value
        return SHAMROCK_SUCCESS

    def ShamrockSetPixelWidth(self, device, width):
        self._log("ShamrockSetPixelWidth", device.value, round(width.value, 6))
        if self._set_width_ret == SHAMROCK_SUCCESS:
            self._w = width.value
        return self._set_width_ret

    def ShamrockGetNumberPixels(self, device, p_n):
        self._log("ShamrockGetNumberPixels")
        p_n._obj.value = self._n
        return SHAMROCK_SUCCESS

    def ShamrockGetPixelWidth(self, device, p_w):
        self._log("ShamrockGetPixelWidth")
        p_w._obj.value = self._w if self._readback_width is None else self._readback_width
        return SHAMROCK_SUCCESS

    def ShamrockGetCalibration(self, device, arr, n):
        self._log("ShamrockGetCalibration")
        return SHAMROCK_SUCCESS


def _real_driver(dll):
    drv = ShamrockDriver.__new__(ShamrockDriver)
    drv._lock = threading.RLock()
    drv._dll = dll
    drv._connected = True
    drv._settling_until = 0.0
    drv._last_motion_type = ""
    drv.geometry_verified = False
    return drv


class TestRealDriverGeometryConfiguration(unittest.TestCase):

    def test_configure_sends_geometry_and_verifies_readback(self):
        dll = _GeometryDll()
        drv = _real_driver(dll)
        self.assertEqual(drv.configure_detector_geometry(), SHAMROCK_SUCCESS)
        self.assertIn(("ShamrockSetNumberPixels", 0, DATASHEET_WIDTH_PX), dll.calls)
        self.assertIn(("ShamrockSetPixelWidth", 0, DATASHEET_PITCH_UM), dll.calls)
        names = [c[0] for c in dll.calls]
        self.assertIn("ShamrockGetPixelWidth", names, "No se releyó lo configurado")
        self.assertTrue(drv.geometry_verified)

    def test_readback_mismatch_is_not_verified(self):
        drv = _real_driver(_GeometryDll(readback_width=13.0))
        self.assertNotEqual(drv.configure_detector_geometry(), SHAMROCK_SUCCESS)
        self.assertFalse(drv.geometry_verified)

    def test_sdk_rejection_propagates(self):
        drv = _real_driver(_GeometryDll(set_width_ret=SHAMROCK_P2INVALID))
        self.assertEqual(drv.configure_detector_geometry(), SHAMROCK_P2INVALID)
        self.assertFalse(drv.geometry_verified)

    def test_dll_exception_is_communication_error(self):
        drv = _real_driver(_GeometryDll(raise_on={"ShamrockSetPixelWidth"}))
        self.assertEqual(drv.configure_detector_geometry(), SHAMROCK_COMMUNICATION_ERROR)
        self.assertFalse(drv.geometry_verified)

    def _factory_with(self, dll):
        """`get_shamrock()` por la rama de hardware real, con la DLL falsa en lugar de la real."""
        with patch.object(sd, "_shamrock_instance", None), \
             patch.object(sd, "SAFE_MODE", False), \
             patch.object(ShamrockDriver, "_init_dll", lambda self: setattr(self, "_dll", dll)):
            inst = get_shamrock()
            inst.ShamrockGetCalibration(0, DATASHEET_WIDTH_PX)
            return inst

    def test_factory_configures_real_driver_before_any_calibration(self):
        dll = _GeometryDll()
        inst = self._factory_with(dll)
        self.assertIsInstance(inst, ShamrockDriver)
        self.assertTrue(inst.geometry_verified)
        names = [c[0] for c in dll.calls]
        first_calibration = names.index("ShamrockGetCalibration")
        self.assertLess(names.index("ShamrockSetNumberPixels"), first_calibration)
        self.assertLess(names.index("ShamrockSetPixelWidth"), first_calibration)

    def test_factory_keeps_real_driver_when_geometry_fails(self):
        # Esconder un espectrógrafo vivo detrás del mock sería peor que marcarlo no verificado.
        inst = self._factory_with(_GeometryDll(readback_width=13.0))
        self.assertIsInstance(inst, ShamrockDriver)
        self.assertFalse(inst.geometry_verified)


# ── 4. Planificación de ventanas ─────────────────────────────────────────────

class TestStepPlanning(unittest.TestCase):

    def test_explicit_window_sets_spacing(self):
        centers = compute_step_centers(450.0, 950.0, 0.20, grating=1, window_nm=100.0)
        np.testing.assert_allclose(np.diff(centers), 80.0)

    def test_optical_core_takes_precedence_over_measured_window(self):
        centers = compute_step_centers(450.0, 950.0, 0.20, grating=1, use_optical_core=True, window_nm=50.0)
        np.testing.assert_allclose(np.diff(centers), LEGACY_WINDOW_NM[1] * 0.8)

    def test_invalid_measured_window_falls_back_to_nominal(self):
        for bad in (None, 0.0, -5.0, float("nan"), float("inf")):
            centers = compute_step_centers(450.0, 950.0, 0.20, grating=1, window_nm=bad)
            np.testing.assert_allclose(np.diff(centers), _datasheet_window_nm(1) * 0.8,
                                       err_msg=f"window_nm={bad!r}")

    def test_resolve_step_window_reports_source(self):
        from pyspectrum.calibration.halogen_lamp import resolve_step_window_nm
        self.assertEqual(resolve_step_window_nm(1, 1004, False, 99.0), (99.0, "measured"))
        self.assertEqual(resolve_step_window_nm(1, 1004, True, 99.0), (LEGACY_WINDOW_NM[1], "optical_core"))
        span, source = resolve_step_window_nm(1, 1004, False, None)
        self.assertEqual(source, "nominal")
        self.assertAlmostEqual(span, _datasheet_window_nm(1), places=6)

    def test_plan_covers_range_without_surplus_window(self):
        """Los extremos llevan el mismo margen que cada lado de un solapamiento interno."""
        cases = ((1, 400.0, 900.0), (1, 450.0, 700.0), (2, 540.0, 600.0))
        for g, a, b in cases:
            w = _datasheet_window_nm(g)
            for ov in (0.10, 0.20, 0.50):
                c = compute_step_centers(a, b, ov, grating=g, window_nm=w)
                label = f"red {g} [{a}-{b}] solap {ov}"
                margin = 0.5 * ov * w
                self.assertAlmostEqual(c[0] - w / 2, a - margin, places=9, msg=label)
                self.assertGreaterEqual(c[-1] + w / 2, b + margin, msg=label)
                if len(c) > 1:
                    self.assertLess(c[-2] + w / 2, b + margin, msg=f"{label}: ventana final sobrante")
                    overlaps = (np.asarray(c[:-1]) + w / 2) - (np.asarray(c[1:]) - w / 2)
                    np.testing.assert_allclose(overlaps, ov * w, err_msg=label)

    def test_mirror_grating_terminates(self):
        centers = compute_step_centers(450.0, 950.0, 0.20, grating=3)
        self.assertTrue(0 < len(centers) < 100)


# ── 5. Cobertura ─────────────────────────────────────────────────────────────

def _win(lo, hi):
    return np.linspace(lo, hi, DATASHEET_WIDTH_PX)


class TestCoverageGaps(unittest.TestCase):

    def test_overlapping_windows_have_no_gaps(self):
        from pyspectrum.calibration.halogen_lamp import coverage_gaps_nm
        self.assertEqual(coverage_gaps_nm([_win(400, 500), _win(490, 600)], 400.0, 600.0), [])

    def test_internal_gap_is_reported(self):
        from pyspectrum.calibration.halogen_lamp import coverage_gaps_nm
        gaps = coverage_gaps_nm([_win(400, 500), _win(520, 600)], 400.0, 600.0)
        self.assertEqual(len(gaps), 1)
        np.testing.assert_allclose(gaps[0], (500.0, 520.0))

    def test_edge_shortfalls_are_reported(self):
        from pyspectrum.calibration.halogen_lamp import coverage_gaps_nm
        gaps = coverage_gaps_nm([_win(410, 500), _win(490, 590)], 400.0, 600.0)
        np.testing.assert_allclose(gaps, [(400.0, 410.0), (590.0, 600.0)])

    def test_window_order_does_not_matter(self):
        from pyspectrum.calibration.halogen_lamp import coverage_gaps_nm
        gaps = coverage_gaps_nm([_win(520, 600), _win(400, 500)], 400.0, 600.0)
        np.testing.assert_allclose(gaps, [(500.0, 520.0)])

    def test_no_windows_means_whole_range_missing(self):
        from pyspectrum.calibration.halogen_lamp import coverage_gaps_nm
        self.assertEqual(coverage_gaps_nm([], 400.0, 600.0), [(400.0, 600.0)])


class TestStepAndGlueCoverageEndToEnd(unittest.TestCase):

    def setUp(self):
        hardware_session.clear_emergency()
        self.camera = get_andor_ccd(force_mock=True)
        self.camera.set_read_mode(READ_MODE_FVB)
        self.spectrometer = get_shamrock(force_mock=True)

    def _backend(self, spectrometer=None):
        be = Backend(self.camera, spectrometer or self.spectrometer)
        be.make_connection(Frontend())
        return be

    def _independent_gaps(self, waves, a, b):
        """Cobertura calculada acá, sin usar `coverage_gaps_nm`: el test no confía en el
        detector que también está verificando."""
        grid = np.linspace(a, b, 20001)
        covered = np.zeros_like(grid, dtype=bool)
        for w in waves:
            covered |= (grid >= np.min(w)) & (grid <= np.max(w))
        return float((~covered).mean())

    def test_scans_leave_no_gaps_at_any_overlap(self):
        for g, a, b in ((1, 400.0, 900.0), (2, 540.0, 560.0)):
            self.spectrometer.ShamrockSetGrating(0, g)
            for ov in (0.10, 0.20, 0.50):
                be = self._backend()
                be.measure_step_and_glue(a, b, ov, 0.01, normalize=False, check_water=False)
                label = f"red {g} solap {ov}"
                self.assertEqual(be._last_window_source, "measured", label)
                self.assertEqual(be._last_coverage_gaps, [], label)
                self.assertEqual(self._independent_gaps(be._raw_wave_steps, a, b), 0.0, label)
        self.spectrometer.ShamrockSetGrating(0, 1)

    def test_planning_with_the_old_13um_window_is_caught(self):
        """El defecto histórico, reproducido: planificar con 0.175 nm/px contra ventanas de
        103 nm deja huecos, y la verificación de cobertura los reporta."""
        self.spectrometer.ShamrockSetGrating(0, 1)
        be = self._backend()
        with patch.object(be, "_measured_window_nm", return_value=0.175 * 1004):
            be.measure_step_and_glue(400.0, 900.0, 0.20, 0.01, normalize=False, check_water=False)
        self.assertTrue(be._last_coverage_gaps, "La verificación de cobertura no vio los huecos")
        self.assertGreater(self._independent_gaps(be._raw_wave_steps, 400.0, 900.0), 0.2)

    def test_unverified_geometry_plans_with_nominal_window(self):
        fresh = _MockShamrock()  # sin configurar: geometry_verified == False
        be = self._backend(fresh)
        be.measure_step_and_glue(450.0, 600.0, 0.20, 0.01, normalize=False, check_water=False)
        self.assertEqual(be._last_window_source, "nominal")
        fresh.configure_detector_geometry()
        be.measure_step_and_glue(450.0, 600.0, 0.20, 0.01, normalize=False, check_water=False)
        self.assertEqual(be._last_window_source, "measured")

    def test_export_records_window_and_coverage(self):
        import h5py
        self.spectrometer.ShamrockSetGrating(0, 1)
        be = self._backend()
        be.measure_step_and_glue(450.0, 700.0, 0.20, 0.01, normalize=False, check_water=False)
        # La ventana medida es la del eje que el barrido usa (cúbico, con curvatura), no la
        # nominal lineal: se compara contra ese eje, y la nominal sólo acota.
        _, axis = self.spectrometer.get_wavelength_axis_cubic(0, DATASHEET_WIDTH_PX)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "sg.h5")
            be.export_hdf5(path)
            with h5py.File(path, "r") as f:
                self.assertAlmostEqual(float(f.attrs["window_nm"]), _span(axis), places=6)
                self.assertLess(abs(float(f.attrs["window_nm"]) / _datasheet_window_nm(1) - 1.0), 0.02)
                self.assertEqual(str(f.attrs["window_source"]), "measured")
                self.assertEqual(np.asarray(f.attrs["coverage_gaps_nm"]).size, 0)


if __name__ == "__main__":
    unittest.main()
