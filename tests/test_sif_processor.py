"""
tests/test_sif_processor.py
===========================
Pruebas unitarias para core/sif_processor.py usando los archivos reales en reserva/
y matrices sintéticas de validación numérica.
"""

import os
import sys
import unittest
import numpy as np

# Asegurar path del workspace
WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from core.sif_processor import (
    read_sif_file,
    spatial_roi_reduce,
    set_average,
    roi_and_set_average,
    filter_savitzky_golay,
    filter_fourier_lowpass,
    filter_moving_average,
    filter_despike_median,
    apply_spectral_filter,
    compute_transmittance,
    compute_transmittance_with_errors,
    compute_extinction,
    compute_residuals,
    export_spectrum_txt,
    MICROSCOPE_OBJECTIVES
)


class TestSifProcessor(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.reserva_dir = os.path.join(WORKSPACE_ROOT, "reserva")
        cls.fbin_path = os.path.join(cls.reserva_dir, "Fbin_hex_100umslit_50ms_nopol_pos_0.sif")
        cls.oblicua_path = os.path.join(cls.reserva_dir, "oblicua_100umslit_1seg_176deg.sif")

    def test_01_read_1d_binned_sif(self):
        """Verifica la lectura correcta del archivo 1D binned en reserva."""
        if not os.path.isfile(self.fbin_path):
            self.skipTest(f"Archivo de prueba no encontrado: {self.fbin_path}")

        spec = read_sif_file(self.fbin_path)
        self.assertFalse(spec.is_2d)
        self.assertEqual(spec.height, 1)
        self.assertEqual(spec.width, 5020)
        self.assertEqual(len(spec.wavelengths), 5020)

        # Verificación de rango de longitudes de onda (400 nm a 900 nm)
        self.assertAlmostEqual(spec.wavelengths[0], 400.0, delta=1.0)
        self.assertAlmostEqual(spec.wavelengths[-1], 900.0, delta=1.0)

        # Verificación de metadatos extraídos
        meta = spec.metadata
        self.assertEqual(meta.slit_width_um, 100.0)
        self.assertAlmostEqual(meta.exposure_time, 0.05, delta=1e-3)
        self.assertEqual(meta.detector_temp_c, -65.0)
        self.assertEqual(meta.ybin, 53)
        self.assertIn("transmittance", meta.data_type.lower())

    def test_02_read_2d_multipixel_sif_with_corrected_calibration(self):
        """Verifica que la calibración 2D multi-pixel no se corrompa por el bug de ImageLength."""
        if not os.path.isfile(self.oblicua_path):
            self.skipTest(f"Archivo de prueba no encontrado: {self.oblicua_path}")

        spec = read_sif_file(self.oblicua_path)
        self.assertTrue(spec.is_2d)
        self.assertEqual(spec.height, 71)
        self.assertEqual(spec.width, 5020)
        self.assertEqual(len(spec.wavelengths), 5020)

        # CRÍTICO: Las longitudes de onda deben ir de 400 a 900 nm, NO hasta 35000 nm!
        self.assertAlmostEqual(spec.wavelengths[0], 400.0, delta=1.0)
        self.assertAlmostEqual(spec.wavelengths[-1], 900.0, delta=1.0)

        # Metadatos
        meta = spec.metadata
        self.assertEqual(meta.slit_width_um, 100.0)
        self.assertAlmostEqual(meta.exposure_time, 1.0, delta=1e-3)
        self.assertEqual(meta.polarization_angle_deg, 176.0)

    def test_03_spatial_roi_reduction(self):
        """Verifica el promediado espacial dentro de un ROI en el archivo 2D."""
        if not os.path.isfile(self.oblicua_path):
            self.skipTest("Archivo oblicua no encontrado")

        spec = read_sif_file(self.oblicua_path)
        y_min, y_max = 20, 40
        profile, std, sem = spatial_roi_reduce(spec.raw_data, y_min=y_min, y_max=y_max, method='mean')

        self.assertEqual(len(profile), 5020)
        self.assertEqual(len(std), 5020)
        self.assertEqual(len(sem), 5020)
        # La media debe ser finita
        self.assertTrue(np.all(np.isfinite(profile)))
        # SEM debe ser std / sqrt(21)
        np.testing.assert_allclose(sem, std / np.sqrt(21), rtol=1e-5)

    def test_04_filters_and_despiking(self):
        """Verifica los filtros espectrales y remoción de rayos cósmicos."""
        x = np.linspace(400, 900, 500)
        # Señal sintética con pico plasmónico y ruido
        clean_peak = 100.0 * np.exp(-((x - 650) ** 2) / (2 * (30 ** 2)))
        noise = np.random.normal(0, 1.0, size=len(x))
        y = clean_peak + noise

        # Insertar un rayo cósmico en el índice 250
        y[250] += 50.0  # Espiga enorme

        # 1. Despiking
        y_despiked = filter_despike_median(y, threshold_sigma=5.0, kernel_size=5)
        self.assertLess(y_despiked[250], 110.0)  # Debe haber eliminado la espiga

        # 2. Savitzky-Golay
        y_sg = filter_savitzky_golay(y_despiked, window_length=15, polyorder=3)
        self.assertEqual(len(y_sg), len(y))
        # Debe haber reducido la varianza del ruido en la línea base
        self.assertLess(np.std(y_sg[:100]), np.std(y[:100]))

        # 3. Fourier Lowpass
        y_fft = filter_fourier_lowpass(y_despiked, cutoff_ratio=0.08)
        self.assertEqual(len(y_fft), len(y))

        # 4. Moving Average
        y_ma = filter_moving_average(y_despiked, window_size=5)
        self.assertEqual(len(y_ma), len(y))

    def test_05_transmittance_and_error_propagation(self):
        """Verifica el cálculo analítico de transmitancia con covarianza y umbral de ruido."""
        n = 200
        bg = np.full(n, 500.0)
        ref = np.full(n, 10000.0)
        signal = np.full(n, 8000.0)

        # Transmitancia esperada: (8000 - 500) / (10000 - 500) = 7500 / 9500 = 78.947%
        t, sigma_t, valid = compute_transmittance_with_errors(
            signal, ref, bg, in_percentage=True
        )

        self.assertTrue(np.all(valid))
        np.testing.assert_allclose(t, (7500.0 / 9500.0) * 100.0, rtol=1e-5)
        self.assertTrue(np.all(sigma_t > 0))

        # Test de Noise Gate: Si ref - bg < threshold, valid_mask = False y T = NaN
        ref_low = np.full(n, 505.0)  # ref - bg = 5 < 10
        t_low, _, valid_low = compute_transmittance_with_errors(
            signal, ref_low, bg, noise_threshold=10.0
        )
        self.assertFalse(np.any(valid_low))
        self.assertTrue(np.all(np.isnan(t_low)))

    def test_06_extinction_and_residuals(self):
        """Verifica la conversión a extinción óptica y residuos."""
        t = np.array([100.0, 10.0, 1.0])  # Transmitancias del 100%, 10%, 1%
        A, sigma_a = compute_extinction(t)
        np.testing.assert_allclose(A, [0.0, 1.0, 2.0], atol=1e-4)

        res = compute_residuals(np.array([80.0, 85.0]), np.array([79.0, 86.0]))
        np.testing.assert_allclose(res, [1.0, -1.0])

    def test_07_export_txt(self):
        """Verifica la exportación a archivo .dat con encabezado científico legible por np.loadtxt."""
        out_path = os.path.join(WORKSPACE_ROOT, "reserva", "test_export.dat")
        wl = np.linspace(400, 900, 10)
        cols = {
            "T_calc": np.linspace(80, 90, 10),
            "Error_T": np.full(10, 0.5)
        }
        meta = {
            "Slit": "100 um",
            "Objective": "50x LWD"
        }
        export_spectrum_txt(out_path, wl, cols, metadata_header=meta)
        self.assertTrue(os.path.isfile(out_path))

        # Carga con np.loadtxt omitiendo comentarios '#'
        loaded = np.loadtxt(out_path, comments='#', encoding='utf-8')
        self.assertEqual(loaded.shape, (10, 3))
        np.testing.assert_allclose(loaded[:, 0], wl)
        np.testing.assert_allclose(loaded[:, 1], cols["T_calc"])

        # Limpieza
        if os.path.exists(out_path):
            os.remove(out_path)

    def test_08_wavelength_uncertainty(self):
        """Verifica el cálculo de incertidumbre de longitud de onda u_c(lambda)."""
        from core.sif_processor import compute_wavelength_uncertainty
        wl = np.linspace(400.0, 900.0, 5020)
        u_100 = compute_wavelength_uncertainty(wl, slit_width_um=100.0)
        u_50 = compute_wavelength_uncertainty(wl, slit_width_um=50.0)

        self.assertEqual(len(u_100), 5020)
        self.assertEqual(len(u_50), 5020)
        # Ranura más angosta debe producir menor incertidumbre espectral
        self.assertLess(np.mean(u_50), np.mean(u_100))
        # Incertidumbre física esperada en rango ~0.1 a 0.5 nm
        self.assertTrue(np.all(u_100 > 0.05))
        self.assertTrue(np.all(u_100 < 1.0))

    def test_09_external_calibration_loader(self):
        """Verifica la carga de calibraciones externas desde INI / Shamrock EEPROM y tablas."""
        from core.sif_processor import load_external_calibration_file
        calib_txt = os.path.join(WORKSPACE_ROOT, "pyspectrum", "calibration", "pyspectrum_calibration_last.txt")
        if os.path.isfile(calib_txt):
            wl_loaded = load_external_calibration_file(calib_txt, width=1004)
            self.assertEqual(len(wl_loaded), 1004)
            # En el archivo: coeff_a=450.124500, coeff_b=0.301450
            self.assertAlmostEqual(wl_loaded[0], 450.1245, places=3)
            self.assertAlmostEqual(wl_loaded[-1], 450.1245 + 0.30145 * 1003, delta=1.0)

    def test_10_noise_characterization_and_wiener(self):
        """Verifica la caracterización de ruido de fondo y filtrado adaptativo de Wiener."""
        from core.sif_processor import characterize_background_noise, filter_wiener_adaptive, filter_despike_adaptive, NoiseProfile
        # Fondo sintético con offset continuo + ruido gaussiano
        np.random.seed(42)
        n = 500
        bg_synth = 450.0 + np.random.normal(0, 5.0, size=(10, n))
        profile = characterize_background_noise(bg_synth)

        self.assertAlmostEqual(profile.mean_counts, 450.0, delta=2.0)
        self.assertAlmostEqual(profile.std_counts, 5.0, delta=1.0)
        self.assertEqual(len(profile.noise_std_spectral), n)
        self.assertEqual(len(profile.noise_psd), n // 2 + 1)

        # Señal con ruido para probar Wiener
        clean = 1000.0 + 200.0 * np.sin(np.linspace(0, 3 * np.pi, n))
        noisy = clean + np.random.normal(0, 5.0, size=n)
        filtered = filter_wiener_adaptive(noisy, profile, alpha=1.0)

        self.assertEqual(len(filtered), n)
        # Debe haber reducido el desvío estándar respecto al ruido puro
        self.assertLess(np.std(filtered - clean), np.std(noisy - clean))

    def test_11_microscope_objectives_real_turret(self):
        """Verifica que consten los 5 objetivos reales de la torreta del laboratorio."""
        from core.sif_processor import MICROSCOPE_OBJECTIVES
        self.assertEqual(len(MICROSCOPE_OBJECTIVES), 5)
        expected_keys = [
            "Olympus MPLN 10x Aire (NA 0.25)",
            "Olympus 20x Aire (NA 0.40)",
            "Nikon CFI S Plan Fluor 40x Aire (NA 0.60)",
            "Olympus LUMPlanFLN 60x W (NA 1.00)",
            "Nikon S Plan Fluor 100x Oil (NA 0.50-1.30)"
        ]
        for k in expected_keys:
            self.assertIn(k, MICROSCOPE_OBJECTIVES)
            obj = MICROSCOPE_OBJECTIVES[k]
            self.assertIn("pixel_scale_um", obj)
            self.assertIn("m_spec", obj)
            self.assertIn("na", obj)
            self.assertGreater(obj["pixel_scale_um"], 0.0)

    def test_12_multichannel_unpacking_and_master_role(self):
        """Verifica el desempaquetado de los 4 canales (Ruido, Ref, Live, Transmitancia) y detección de Maestro."""
        if not os.path.isfile(self.fbin_path):
            self.skipTest("Archivo fbin no encontrado")

        spec = read_sif_file(self.fbin_path)
        self.assertEqual(spec.channels_count, 4)
        self.assertTrue(spec.is_master)
        self.assertIn("transmittance", spec.channels)
        self.assertIn("reference", spec.channels)
        self.assertIn("dark", spec.channels)
        self.assertIn("live", spec.channels)

        # Corroborar formas y tipos
        self.assertEqual(spec.transmittance_data.shape, (1, 1, 5020))
        self.assertEqual(spec.reference_data.shape, (1, 1, 5020))
        self.assertEqual(spec.dark_data.shape, (1, 1, 5020))
        self.assertEqual(spec.live_data.shape, (1, 1, 5020))

    def test_13_dual_route_transmittance(self):
        """Verifica el cálculo de transmitancia en Ruta A vs Ruta B para matrices 2D."""
        if not os.path.isfile(self.oblicua_path):
            self.skipTest("Archivo oblicua no encontrado")

        from core.sif_processor import compute_transmittance_dual_route
        spec = read_sif_file(self.oblicua_path)
        live = spec.channels['live']
        ref = spec.channels['reference']
        dark = spec.channels['dark']

        t_a, t_b, mask = compute_transmittance_dual_route(live, ref, dark, roi_ymin=20, roi_ymax=50, noise_gate=5.0)
        self.assertEqual(len(t_a), 5020)
        self.assertEqual(len(t_b), 5020)
        self.assertTrue(np.any(mask))
        # Ambas rutas deben correlacionar fuertemente en la banda con alta señal (> 0.90)
        corr = np.corrcoef(t_a[mask], t_b[mask])[0, 1]
        self.assertGreater(corr, 0.90)

    def test_14_advanced_peak_fitting(self):
        """Verifica el ajuste avanzado de picos con modelos Gaussiano, Lorentziano y Fano + incertidumbre combinada."""
        from core.sif_processor import fit_peak_advanced
        # Crear resonancia de Fano sintética con ruido
        wls = np.linspace(600, 800, 300)
        l0_true, gamma_true, q_true = 700.0, 35.0, -2.0
        eps = 2.0 * (wls - l0_true) / gamma_true
        y_clean = 0.6 * ((q_true + eps) ** 2) / (1.0 + eps ** 2) + 0.05
        np.random.seed(42)
        y_noisy = y_clean + np.random.normal(0, 0.015, len(wls))

        # 1. Ajuste Fano
        res_fano = fit_peak_advanced(wls, y_noisy, roi_range=(620, 780), model_type="fano", slit_width_um=100.0)
        self.assertAlmostEqual(res_fano['peak_center'], l0_true, delta=2.0)
        self.assertAlmostEqual(res_fano['fwhm'], gamma_true, delta=3.0)
        self.assertAlmostEqual(res_fano['q_factor'], q_true, delta=0.5)
        self.assertGreater(res_fano['r_squared'], 0.95)
        self.assertGreater(res_fano['u_peak_center_combined'], res_fano['u_peak_center_fit'])

        # 2. Ajuste Gaussiano
        res_gauss = fit_peak_advanced(wls, y_noisy, roi_range=(650, 750), model_type="gaussian")
        self.assertGreater(res_gauss['r_squared'], 0.80)
        self.assertGreater(res_gauss['fwhm'], 0.0)


if __name__ == '__main__':
    unittest.main()

