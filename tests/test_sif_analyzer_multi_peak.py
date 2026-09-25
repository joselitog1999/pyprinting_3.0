"""
tests/test_sif_analyzer_multi_peak.py
======================================
Pruebas automatizadas de la Fase 3 del Analizador SIF (`sif_analyzer.py` y
`core/sif_processor.py`): deconvolución multi-pico (1-5 picos, Gaussiano /
Lorentziano / Pseudo-Voigt / Fano), sustracción de línea base AsLS Whittaker,
integración con la Pestaña 5 (tabla de parámetros de ajuste) y los 5 cuadros
de Metrología Unitaria al pie de cada gráfico 1D.
"""

import os
import sys
import unittest
import numpy as np

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from PyQt6.QtWidgets import QApplication, QMessageBox

app = QApplication.instance()
if app is None:
    app = QApplication([sys.argv[0], "-platform", "offscreen"])

from core.sif_processor import fit_extinction_multi_peak, baseline_asls
from sif_analyzer import SifAnalyzerWindow


def _gauss(x, a, c, w):
    sigma = w / 2.3548
    return a * np.exp(-0.5 * ((x - c) / sigma) ** 2)


class TestFitExtinctionMultiPeakSynthetic(unittest.TestCase):
    """Agente QA — Punto 1: Ajuste Multi-Pico Sintético."""

    def test_recovers_two_known_peak_centers_within_1nm(self):
        wl = np.linspace(550.0, 800.0, 900)
        rng = np.random.default_rng(1)
        background = 0.04 + 0.10 / (1.0 + np.exp(-(wl - 690.0) / 25.0))
        signal = background + _gauss(wl, 0.28, 620.0, 22.0) + _gauss(wl, 0.16, 710.0, 26.0)
        signal += rng.normal(0.0, 0.0025, size=wl.shape)

        res = fit_extinction_multi_peak(
            wl, signal, roi_range=(560.0, 780.0), n_peaks=2,
            model_type="pseudo_voigt", baseline_mode="asls",
            asls_lam=1.0e6, asls_p=0.01, slit_width_um=100.0
        )

        self.assertEqual(len(res["peaks_params"]), 2)
        centers = sorted(p["lambda_0"] for p in res["peaks_params"])
        self.assertLess(abs(centers[0] - 620.0), 1.0)
        self.assertLess(abs(centers[1] - 710.0), 1.0)
        self.assertGreater(res["r_squared"], 0.95)

    def test_single_peak_gaussian_recovers_center(self):
        wl = np.linspace(600.0, 700.0, 400)
        signal = 0.02 + _gauss(wl, 0.5, 650.0, 15.0)
        res = fit_extinction_multi_peak(
            wl, signal, roi_range=(620.0, 680.0), n_peaks=1,
            model_type="gaussian", baseline_mode="constant"
        )
        self.assertEqual(len(res["peaks_params"]), 1)
        self.assertLess(abs(res["peaks_params"][0]["lambda_0"] - 650.0), 0.5)
        self.assertEqual(res["peaks_params"][0]["ratio_h0"], 1.0)
        self.assertIsNone(res["peaks_params"][0]["ratio_h2_h1"])

    def test_five_peaks_clamped_and_supported(self):
        wl = np.linspace(400.0, 900.0, 1200)
        centers = [480.0, 560.0, 640.0, 720.0, 800.0]
        signal = 0.05 * np.ones_like(wl)
        for c in centers:
            signal += _gauss(wl, 0.15, c, 20.0)
        res = fit_extinction_multi_peak(
            wl, signal, roi_range=(420.0, 880.0), n_peaks=5,
            model_type="lorentzian", baseline_mode="constant"
        )
        self.assertEqual(res["n_peaks"], 5)
        self.assertEqual(len(res["peaks_params"]), 5)
        self.assertEqual(len(res["individual_peaks"]), 5)

    def test_n_peaks_clamped_above_five(self):
        wl = np.linspace(600.0, 700.0, 300)
        signal = 0.02 + _gauss(wl, 0.4, 650.0, 15.0)
        res = fit_extinction_multi_peak(wl, signal, roi_range=(620.0, 680.0), n_peaks=99, model_type="gaussian", baseline_mode="none")
        self.assertLessEqual(res["n_peaks"], 5)

    def test_ratio_h2_h1_and_h0_are_coherent(self):
        wl = np.linspace(550.0, 800.0, 700)
        signal = 0.03 + _gauss(wl, 0.5, 620.0, 20.0) + _gauss(wl, 0.2, 710.0, 20.0)
        res = fit_extinction_multi_peak(wl, signal, roi_range=(560.0, 780.0), n_peaks=2, model_type="pseudo_voigt", baseline_mode="linear")
        peaks_sorted = res["peaks_params"]
        h1, h2 = peaks_sorted[0]["amplitude"], peaks_sorted[1]["amplitude"]
        self.assertAlmostEqual(peaks_sorted[0]["ratio_h2_h1"], h2 / h1, places=6)
        principal = max(peaks_sorted, key=lambda p: p["amplitude"])
        self.assertEqual(principal["ratio_h0"], 1.0)


class TestBaselineAsLS(unittest.TestCase):
    """Agente QA — Punto 2: Sustracción AsLS."""

    def test_asls_extracts_sigmoidal_background_without_degrading_peak_height(self):
        x = np.linspace(0.0, 1000.0, 1000)
        true_baseline = 50.0 + 200.0 / (1.0 + np.exp(-(x - 600.0) / 60.0))
        peak = _gauss(x, 300.0, 400.0, 30.0)
        y = true_baseline + peak

        z = baseline_asls(y, lam=1.0e6, p=0.001)

        # La línea base estimada debe seguir la tendencia sigmoidal, no la del pico
        self.assertLess(np.max(np.abs(z - true_baseline)) / np.max(true_baseline), 0.25)

        # La altura neta del pico tras sustraer la línea base estimada no debe degradarse (>90% de la real)
        net = y - z
        recovered_height = float(np.max(net))
        self.assertGreater(recovered_height, 0.9 * 300.0)

    def test_asls_lam_and_p_change_rigidity(self):
        x = np.linspace(0.0, 500.0, 500)
        y = 10.0 + 0.5 * np.sin(x / 20.0) * 0.0 + _gauss(x, 100.0, 250.0, 15.0) + 50.0
        z_rigid = baseline_asls(y, lam=1.0e7, p=0.001)
        z_soft = baseline_asls(y, lam=1.0e2, p=0.001)
        # Una linea base mas rigida (lam grande) debe variar menos que una blanda (lam chico)
        self.assertLessEqual(np.std(np.diff(z_rigid)), np.std(np.diff(z_soft)) + 1e-6)


class TestSifAnalyzerMultiPeakGUIIntegration(unittest.TestCase):
    """Agente QA — Puntos 3 y 4: Integración GUI y Metrología Unitaria."""

    @classmethod
    def setUpClass(cls):
        cls.reserva_dir = os.path.join(WORKSPACE_ROOT, "reserva")
        cls.fbin_path = os.path.join(cls.reserva_dir, "Fbin_hex_100umslit_50ms_nopol_pos_0.sif")
        cls.oblicua_path = os.path.join(cls.reserva_dir, "oblicua_100umslit_1seg_176deg.sif")

    def setUp(self):
        self.window = SifAnalyzerWindow()

    def tearDown(self):
        self.window.close()

    def _require_fbin(self):
        if not os.path.isfile(self.fbin_path):
            self.skipTest("Archivo fbin no encontrado")

    def test_two_peak_selection_populates_table_with_two_rows(self):
        self._require_fbin()
        self.window._load_file_list([self.fbin_path])
        self.window._select_file_index(0)
        self.window.tabs_process.setCurrentIndex(4)

        self.window.spin_fit_n_peaks.setValue(2)
        self.window.combo_fit_model.setCurrentText("Pseudo-Voigt")
        self.window.combo_fit_baseline.setCurrentText("AsLS Whittaker")
        self.window.spin_fit_lmin.setValue(600.0)
        self.window.spin_fit_lmax.setValue(850.0)
        self.window._on_run_peak_fit()

        res = self.window.last_peak_fit_results
        self.assertIsNotNone(res)
        self.assertEqual(len(res["peaks_params"]), 2)
        self.assertEqual(self.window.table_fit_peaks.rowCount(), 2)
        self.assertEqual(self.window.table_fit_peaks.columnCount(), 8)

        # Ratios Hi/H0 y H2/H1 numéricamente coherentes
        p1, p2 = res["peaks_params"]
        h0_ratios = [p1["ratio_h0"], p2["ratio_h0"]]
        self.assertIn(1.0, h0_ratios)
        self.assertIsNotNone(p1["ratio_h2_h1"])
        self.assertAlmostEqual(p1["ratio_h2_h1"], p2["amplitude"] / p1["amplitude"], places=6)

        # Limpieza de ajuste deja la tabla vacía
        self.window._on_clear_peak_fit()
        self.assertEqual(self.window.table_fit_peaks.rowCount(), 0)
        self.assertIsNone(self.window.last_peak_fit_results)

    def test_baseline_asls_params_visible_only_when_selected(self):
        self.window.combo_fit_baseline.setCurrentText("AsLS Whittaker")
        self.assertFalse(self.window.spin_fit_asls_lam.isHidden())
        self.assertFalse(self.window.spin_fit_asls_p.isHidden())
        self.window.combo_fit_baseline.setCurrentText("Ninguno")
        self.assertTrue(self.window.spin_fit_asls_lam.isHidden())
        self.assertTrue(self.window.spin_fit_asls_p.isHidden())

    def test_fit_with_invalid_roi_shows_error_dialog_not_crash(self):
        self._require_fbin()
        self.window._load_file_list([self.fbin_path])
        self.window._select_file_index(0)
        self.window.spin_fit_n_peaks.setValue(5)
        self.window.spin_fit_lmin.setValue(699.9)
        self.window.spin_fit_lmax.setValue(700.1)  # ROI demasiado angosto (~2 puntos) para 5 picos
        errors = []
        QMessageBox.critical = staticmethod(lambda *a, **k: errors.append(a))
        self.window._on_run_peak_fit()
        self.assertEqual(len(errors), 1)

    # ----------------------------------------------------------------
    # 4. Metrología Unitaria: los 5 cuadros calculan y despliegan sin error
    # ----------------------------------------------------------------
    def test_all_five_metrology_boxes_populate_without_errors(self):
        self._require_fbin()
        if not os.path.isfile(self.oblicua_path):
            self.skipTest("Archivo oblicua no encontrado")

        self.window._load_file_list([self.fbin_path, self.oblicua_path])
        self.window._select_file_index(0)
        self.window._recalculate_all()

        # 1. Ruido
        dark_text = self.window.lbl_dark_metrics.text()
        self.assertIn("Bias Medio", dark_text)
        self.assertIn("Ruido de Lectura RMS", dark_text)
        self.assertIn("Píxeles Calientes", dark_text)

        # 2. Referencia
        ref_text = self.window.lbl_ref_metrics.text()
        self.assertIn("Cuentas Medias ROI", ref_text)
        self.assertIn("Llenado Dinámico CCD", ref_text)
        self.assertIn("Estabilidad Espectral", ref_text)

        # 3. Live / Señal
        live_text = self.window.lbl_live_metrics.text()
        self.assertIn("SBR", live_text)
        self.assertIn("Señal Neta Máx", live_text)
        self.assertIn("SNR Pico", live_text)
        self.assertIn("SNR Integrado", live_text)

        # 4. Transmisión
        trans_text = self.window.lbl_trans_metrics.text()
        self.assertIn("T_media", trans_text)
        self.assertIn("Contraste", trans_text)
        self.assertIn("Incertidumbre Combinada Media", trans_text)

        # 5. Extinción (sin ajuste todavía: al menos OD_max debe estar presente)
        ext_text = self.window.lbl_fit_results.text()
        self.assertIn("OD_max", ext_text)

        # Todos los cuadros deben estar alojados en un QGroupBox "Metrología Unitaria"
        for lbl_name in ("lbl_dark_metrics", "lbl_ref_metrics", "lbl_live_metrics", "lbl_trans_metrics"):
            lbl = getattr(self.window, lbl_name)
            parent = lbl.parentWidget()
            self.assertIsNotNone(parent)
            self.assertIn("Metrología Unitaria", parent.title())

    def test_extinction_metrology_shows_q_factor_after_fit(self):
        self._require_fbin()
        self.window._load_file_list([self.fbin_path])
        self.window._select_file_index(0)
        self.window.spin_fit_n_peaks.setValue(1)
        self.window.combo_fit_model.setCurrentText("Lorentziano")
        self.window.spin_fit_lmin.setValue(620.0)
        self.window.spin_fit_lmax.setValue(720.0)
        self.window._on_run_peak_fit()
        ext_text = self.window.lbl_fit_results.text()
        self.assertIn("λ_res", ext_text)
        self.assertIn("Q = λ_res/FWHM", ext_text)
        self.assertIn("χ²_red", ext_text)


if __name__ == '__main__':
    unittest.main()
