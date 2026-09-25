"""
tests/test_sif_analyzer_phase4_fair.py
=======================================
Pruebas automatizadas de la Fase 4 (final) del Analizador SIF: expansión a 7
pestañas (Multi-Espectro & Polarización, Ficha Metrológica & FAIR), detección
de ángulos de polarización, ajuste de la Ley de Malus y factor de anisotropía
g, exportación de sesión FAIR a HDF5/NeXus, e integración con
FigureExportStudioDialog y ScientificWikiBrowserDialog.
"""

import os
import shutil
import sys
import tempfile
import unittest
import numpy as np

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from PyQt6.QtWidgets import QApplication, QCheckBox, QMessageBox

app = QApplication.instance()
if app is None:
    app = QApplication([sys.argv[0], "-platform", "offscreen"])

from core.sif_processor import (
    extract_polarization_angle_from_name,
    fit_malus_law,
    export_sif_session_to_hdf5,
    H5PY_AVAILABLE,
)
from sif_analyzer import SifAnalyzerWindow
from analysis.figure_export_studio import FigureExportStudioDialog
from analysis.scientific_wiki_browser import ScientificWikiBrowserDialog


class TestExtractPolarizationAngleFromName(unittest.TestCase):
    """Agente QA — Punto 1."""

    def test_deg_suffix_pattern(self):
        self.assertEqual(extract_polarization_angle_from_name("muestra_45deg.sif"), 45.0)

    def test_pol_prefix_pattern(self):
        self.assertEqual(extract_polarization_angle_from_name("espectro_pol90.sif"), 90.0)

    def test_no_angle_returns_none(self):
        self.assertIsNone(extract_polarization_angle_from_name("sin_angulo.sif"))

    def test_nopol_returns_none_even_with_digits_nearby(self):
        self.assertIsNone(extract_polarization_angle_from_name("Fbin_hex_100umslit_50ms_nopol_pos_0.sif"))

    def test_real_reserva_filename_176deg(self):
        self.assertEqual(extract_polarization_angle_from_name("oblicua_100umslit_1seg_176deg.sif"), 176.0)

    def test_pol_with_underscore_separator(self):
        self.assertEqual(extract_polarization_angle_from_name("pol_0.sif"), 0.0)

    def test_full_path_not_just_basename(self):
        angle = extract_polarization_angle_from_name(r"C:\datos\lote1\muestra_135deg.sif")
        self.assertEqual(angle, 135.0)


class TestFitMalusLaw(unittest.TestCase):
    """Agente QA — Punto 2."""

    def test_recovers_known_parameters_from_synthetic_series(self):
        angles = np.array([0, 30, 45, 60, 90, 120, 135, 150])
        i_min_true, i_max_true, theta0_true = 0.1, 1.0, 37.0
        rng = np.random.default_rng(3)
        intensities = i_min_true + (i_max_true - i_min_true) * np.cos(np.radians(angles - theta0_true)) ** 2
        intensities += rng.normal(0, 0.005, size=intensities.shape)

        res = fit_malus_law(angles, intensities)
        self.assertAlmostEqual(res["theta0_deg"], theta0_true, delta=2.0)
        self.assertAlmostEqual(res["i_min"], i_min_true, delta=0.03)
        self.assertAlmostEqual(res["i_max"], i_max_true, delta=0.03)
        self.assertGreater(res["r_squared"], 0.98)

    def test_anisotropy_factor_g_for_ideal_dichroic_case(self):
        # Caso ideal: I_perp=0 (extinción total en la dirección perpendicular) -> g debe acercarse a 2.0
        angles = np.linspace(0, 150, 6)
        i_min_true, i_max_true, theta0_true = 1e-6, 1.0, 0.0
        intensities = i_min_true + (i_max_true - i_min_true) * np.cos(np.radians(angles - theta0_true)) ** 2
        res = fit_malus_law(angles, intensities)
        self.assertAlmostEqual(res["g_factor"], 2.0, delta=0.05)
        self.assertGreater(res["contrast"], 0.95)

    def test_isotropic_case_gives_near_zero_g_and_contrast(self):
        angles = np.array([0, 30, 60, 90, 120, 150])
        intensities = np.full_like(angles, 0.5, dtype=np.float64)
        res = fit_malus_law(angles, intensities)
        self.assertAlmostEqual(res["g_factor"], 0.0, delta=0.05)
        self.assertAlmostEqual(res["contrast"], 0.0, delta=0.05)

    def test_raises_with_fewer_than_three_angles(self):
        with self.assertRaises(ValueError):
            fit_malus_law(np.array([0.0, 45.0]), np.array([1.0, 0.5]))


class TestExportSifSessionToHdf5(unittest.TestCase):
    """Agente QA — Punto 5."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_hdf5_structure_and_attributes(self):
        if not H5PY_AVAILABLE:
            self.skipTest("h5py no está disponible en este entorno")
        import h5py

        path = os.path.join(self.tmp_dir, "sesion_test.h5")
        session_data = {
            "title": "Sesion de Prueba",
            "filename": "test.sif",
            "detector": {"model": "DU8285_VP", "temp_c": -65.0, "em_gain": 100.0, "xbin": 1, "ybin": 1},
            "optics": {"objective": "60x", "na": 1.0, "scale_um_px": 0.1248},
            "spectrometer": {"slit_um": 100.0, "dispersion_nm_px": 0.0996},
            "processing": {"despike": True, "baseline_mode": "asls"},
            "wavelengths_nm": np.linspace(500, 900, 50),
            "data_1d": {
                "dark": np.ones(50), "reference": np.ones(50) * 500,
                "live": np.ones(50) * 400, "transmittance_calc": np.ones(50) * 80.0,
                "extinction": np.ones(50) * 0.1,
            },
            "data_2d": {"live": np.ones((8, 50))},
            "peaks_params": [{"index": 1, "lambda_0": 650.0, "amplitude": 0.5}],
        }

        out_path = export_sif_session_to_hdf5(path, session_data)
        self.assertTrue(os.path.isfile(out_path))

        with h5py.File(out_path, "r") as f:
            self.assertEqual(f.attrs["NX_class"], "NXroot")
            self.assertIn("entry1", f)
            entry = f["entry1"]
            self.assertEqual(entry.attrs["NX_class"], "NXentry")
            self.assertIn("instrument", entry)
            self.assertIn("detector_emccd", entry["instrument"])
            self.assertEqual(entry["instrument"]["detector_emccd"].attrs["model"], "DU8285_VP")
            self.assertIn("optics", entry["instrument"])
            self.assertIn("data", entry)
            self.assertIn("1d", entry["data"])
            self.assertIn("wavelength_nm", entry["data"]["1d"])
            self.assertIn("extinction", entry["data"]["1d"])
            self.assertIn("2d", entry["data"])
            self.assertIn("live", entry["data"]["2d"])
            self.assertIn("process", entry)
            self.assertIn("multi_peak_fit", entry["process"])
            self.assertIn("peak_1", entry["process"]["multi_peak_fit"])

    def test_graceful_degradation_signature_intact_when_called(self):
        # No debe lanzar excepción incluso con datos mínimos
        path = os.path.join(self.tmp_dir, "minimal.h5")
        out = export_sif_session_to_hdf5(path, {"title": "min", "wavelengths_nm": np.array([1.0, 2.0])})
        if H5PY_AVAILABLE:
            self.assertTrue(os.path.isfile(out))


class TestSifAnalyzerPhase4GUIIntegration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.reserva_dir = os.path.join(WORKSPACE_ROOT, "reserva")
        cls.fbin_path = os.path.join(cls.reserva_dir, "Fbin_hex_100umslit_50ms_nopol_pos_0.sif")
        cls.oblicua_path = os.path.join(cls.reserva_dir, "oblicua_100umslit_1seg_176deg.sif")

    def setUp(self):
        self.window = SifAnalyzerWindow()

    def tearDown(self):
        self.window.close()

    def _require_reserva(self):
        if not (os.path.isfile(self.fbin_path) and os.path.isfile(self.oblicua_path)):
            self.skipTest("Archivos de reserva no encontrados")

    # --------------------------------------------------------------------
    # 2. Sincronía de las 7 pestañas con stack_options
    # --------------------------------------------------------------------
    def test_seven_tabs_present_and_synced_with_stack_options(self):
        self.assertEqual(self.window.tabs_process.count(), 7)
        self.assertEqual(self.window.stack_options.count(), 7)
        tab_titles = [self.window.tabs_process.tabText(i) for i in range(7)]
        self.assertTrue(any("Multi-Espectro" in t for t in tab_titles))
        self.assertTrue(any("Ficha Metrológica" in t for t in tab_titles))
        for idx in range(7):
            self.window.tabs_process.setCurrentIndex(idx)
            app.processEvents()
            self.assertEqual(self.window.stack_options.currentIndex(), idx)

    # --------------------------------------------------------------------
    # 3. Pestaña 6: Overlay vs Cascada y población de curvas
    # --------------------------------------------------------------------
    def test_multi_spectrum_checkbox_selection_and_overlay_vs_waterfall(self):
        self._require_reserva()
        self.window._load_file_list([self.fbin_path, self.oblicua_path])
        self.window._select_file_index(0)

        for row in range(self.window.table_files.rowCount()):
            chk = self.window.table_files.cellWidget(row, 0).findChild(QCheckBox)
            chk.setChecked(True)
        self.assertEqual(self.window._get_checked_spectrum_indices(), [0, 1])

        self.window.tabs_process.setCurrentIndex(5)
        app.processEvents()
        self.assertGreater(len(self.window.plot_multi_curves.listDataItems()), 0)

        overlay_items = self.window.plot_multi_curves.listDataItems()

        self.window.combo_multi_mode.setCurrentText("Cascada (Waterfall 2.5D)")
        self.window.spin_multi_dy.setValue(20.0)
        self.window._refresh_multi_spectrum_plot()
        waterfall_items = self.window.plot_multi_curves.listDataItems()
        self.assertEqual(len(overlay_items), len(waterfall_items))

        # Desmarcar un archivo reduce las curvas dibujadas
        chk0 = self.window.table_files.cellWidget(0, 0).findChild(QCheckBox)
        chk0.setChecked(False)
        self.window._refresh_multi_spectrum_plot()
        self.assertLess(len(self.window.plot_multi_curves.listDataItems()), len(waterfall_items))

    def test_multi_curve_normalization_modes_do_not_raise(self):
        self._require_reserva()
        self.window._load_file_list([self.fbin_path])
        self.window._select_file_index(0)
        chk = self.window.table_files.cellWidget(0, 0).findChild(QCheckBox)
        chk.setChecked(True)
        for norm in ("Ninguna", "Normalizar [0, 1]", "Dividir por Máximo"):
            self.window.combo_multi_norm.setCurrentText(norm)
            self.window._refresh_multi_spectrum_plot()
            self.assertGreaterEqual(len(self.window.plot_multi_curves.listDataItems()), 1)

    def test_malus_fit_wiring_populates_polar_plot(self):
        self._require_reserva()
        tmp_dir = tempfile.mkdtemp()
        try:
            paths = []
            for ang in (0, 45, 90):
                dst = os.path.join(tmp_dir, f"sample_{ang}deg.sif")
                shutil.copy(self.oblicua_path, dst)
                paths.append(dst)
            self.window._load_file_list(paths)
            self.window._select_file_index(0)
            self.window.spin_multi_pol_lambda.setValue(650.0)
            self.window._on_run_malus_fit()

            self.assertIsNotNone(self.window.last_malus_fit_results)
            res = self.window.last_malus_fit_results
            self.assertEqual(sorted(res["angles_deg"].tolist()), [0.0, 45.0, 90.0])
            self.assertIn("g_factor", res)
            self.assertIn("θ₀", self.window.lbl_polar_metrics.text())
            self.assertGreater(len(self.window.plot_multi_polar.listDataItems()), 0)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_malus_fit_warns_with_insufficient_angled_files(self):
        self._require_reserva()
        self.window._load_file_list([self.fbin_path])  # 'nopol' -> sin ángulo detectable
        self.window._select_file_index(0)
        warnings_seen = []
        QMessageBox.warning = staticmethod(lambda *a, **k: warnings_seen.append(True))
        self.window._on_run_malus_fit()
        self.assertEqual(len(warnings_seen), 1)
        self.assertIsNone(self.window.last_malus_fit_results)

    # --------------------------------------------------------------------
    # 4. Pestaña 7: Ficha Metrológica
    # --------------------------------------------------------------------
    def test_metrology_ficha_report_contains_key_fields(self):
        self._require_reserva()
        self.window._load_file_list([self.fbin_path])
        self.window._select_file_index(0)
        self.window.tabs_process.setCurrentIndex(6)
        app.processEvents()

        html = self.window.text_metrology_ficha.toHtml()
        self.assertIn("Ficha Metrológica", html)
        self.assertIn("Detector Andor EMCCD", html)

        data = self.window._build_metrology_report_data()
        self.assertIn("detector", data)
        self.assertIn("optics", data)
        self.assertIn("spectrometer", data)
        self.assertIn("processing", data)

        md = self.window._render_report_markdown(data)
        self.assertIn("# Ficha Metrológica", md)
        self.assertIn("## Hardware: Detector Andor EMCCD", md)
        self.assertIn("## Óptica", md)
        self.assertIn("## Calibración Espectral", md)
        self.assertIn("## Protocolo de Procesamiento", md)

    def test_ficha_reflects_multi_peak_fit_results_when_present(self):
        self._require_reserva()
        self.window._load_file_list([self.fbin_path])
        self.window._select_file_index(0)
        self.window.spin_fit_n_peaks.setValue(1)
        self.window.combo_fit_model.setCurrentText("Lorentziano")
        self.window.spin_fit_lmin.setValue(620.0)
        self.window.spin_fit_lmax.setValue(720.0)
        self.window._on_run_peak_fit()

        data = self.window._build_metrology_report_data()
        self.assertIsNotNone(data["peaks_params"])
        md = self.window._render_report_markdown(data)
        self.assertIn("Resultados del Ajuste Multi-Pico", md)

    def test_export_session_hdf5_writes_valid_file(self):
        self._require_reserva()
        if not H5PY_AVAILABLE:
            self.skipTest("h5py no está disponible en este entorno")
        self.window._load_file_list([self.fbin_path])
        self.window._select_file_index(0)

        tmp_dir = tempfile.mkdtemp()
        try:
            out_path = os.path.join(tmp_dir, "sesion_gui.h5")
            from PyQt6.QtWidgets import QFileDialog
            original_dlg = QFileDialog.getSaveFileName
            original_info = QMessageBox.information
            QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (out_path, ""))
            QMessageBox.information = staticmethod(lambda *a, **k: None)
            try:
                self.window._on_export_session_hdf5()
            finally:
                QFileDialog.getSaveFileName = original_dlg
                QMessageBox.information = original_info
            self.assertTrue(os.path.isfile(out_path))
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_copy_and_export_ficha_do_not_raise(self):
        self._require_reserva()
        self.window._load_file_list([self.fbin_path])
        self.window._select_file_index(0)

        # El portapapeles real del sistema operativo cuelga bajo la plataforma Qt "offscreen"
        # (sin bucle de mensajes de un display server real); se simula con un stand-in ligero
        # para verificar exclusivamente la lógica de _on_copy_ficha_clipboard sin tocar el SO.
        captured = {}
        fake_clipboard = type("FakeClipboard", (), {"setText": lambda self, text: captured.__setitem__("text", text)})()
        original_clipboard_fn = QApplication.clipboard
        QApplication.clipboard = staticmethod(lambda: fake_clipboard)
        try:
            self.window._on_copy_ficha_clipboard()
        finally:
            QApplication.clipboard = original_clipboard_fn
        self.assertIn("Ficha Metrológica", captured.get("text", ""))

        tmp_dir = tempfile.mkdtemp()
        try:
            out_path = os.path.join(tmp_dir, "ficha.md")
            from PyQt6.QtWidgets import QFileDialog
            original = QFileDialog.getSaveFileName
            QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (out_path, ""))
            original_info = QMessageBox.information
            QMessageBox.information = staticmethod(lambda *a, **k: None)
            try:
                self.window._on_export_ficha_markdown()
            finally:
                QFileDialog.getSaveFileName = original
                QMessageBox.information = original_info
            self.assertTrue(os.path.isfile(out_path))
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    # --------------------------------------------------------------------
    # 6. Integración con FigureExportStudio y Wiki Científica
    # --------------------------------------------------------------------
    def test_figure_export_studio_wiring_exists_on_all_principal_plots(self):
        from PyQt6.QtCore import Qt
        principal_plots = [
            "plot_dark_1d", "plot_dark_2d", "plot_ref_1d", "plot_ref_2d", "plot_ref_compare",
            "plot_live_1d", "plot_live_2d", "plot_trans_main", "plot_trans_residuals",
            "plot_ext_main", "plot_ext_residuals", "plot_multi_curves", "plot_multi_polar",
        ]
        for name in principal_plots:
            plot_widget = getattr(self.window, name)
            self.assertEqual(plot_widget.contextMenuPolicy(), Qt.ContextMenuPolicy.CustomContextMenu, msg=name)

    def test_figure_export_studio_dialog_constructible_from_sif_plot(self):
        dlg = FigureExportStudioDialog(self.window.plot_trans_main, parent=self.window, title="T", default_filename="t")
        self.assertIsNotNone(dlg)
        dlg.close()

    def test_wiki_button_and_singleton_pattern(self):
        self.assertTrue(hasattr(self.window, "btn_wiki_global"))
        self.assertIsNone(self.window._wiki_dialog)
        self.window._open_wiki_note("CAT-108")
        self.assertIsInstance(self.window._wiki_dialog, ScientificWikiBrowserDialog)
        first_instance = self.window._wiki_dialog
        self.window._open_wiki_note("CAT-001")
        self.assertIs(self.window._wiki_dialog, first_instance)


if __name__ == '__main__':
    unittest.main()
