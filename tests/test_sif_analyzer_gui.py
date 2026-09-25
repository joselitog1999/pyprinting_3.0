"""
tests/test_sif_analyzer_gui.py
==============================
Pruebas automatizadas de la interfaz gráfica SifAnalyzerWindow (PyQt6)
con las 5 Ventanas de Proceso Separadas y la Arquitectura de Archivo Maestro.
"""

import os
import sys
import unittest
import numpy as np

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from PyQt6.QtWidgets import QApplication
from sif_analyzer import SifAnalyzerWindow

app = QApplication.instance()
if app is None:
    app = QApplication([sys.argv[0], "-platform", "offscreen"])


class TestSifAnalyzerGUI(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.reserva_dir = os.path.join(WORKSPACE_ROOT, "reserva")
        cls.fbin_path = os.path.join(cls.reserva_dir, "Fbin_hex_100umslit_50ms_nopol_pos_0.sif")
        cls.oblicua_path = os.path.join(cls.reserva_dir, "oblicua_100umslit_1seg_176deg.sif")

    def setUp(self):
        self.window = SifAnalyzerWindow()

    def tearDown(self):
        self.window.close()

    def test_01_instantiation_and_empty_state(self):
        """Verifica que la ventana se instancie limpiamente con las 7 ventanas de proceso (Fase 4)."""
        self.assertIn("Andor Solis", self.window.windowTitle())
        self.assertEqual(len(self.window.loaded_spectra), 0)
        self.assertEqual(self.window.active_index, -1)
        self.assertIsNone(self.window.master_spectrum)

        # Corroborar 7 pestañas de proceso (5 originales + Fase 4: Multi-Espectro y Ficha Metrológica)
        self.assertEqual(self.window.tabs_process.count(), 7)
        tab_titles = [self.window.tabs_process.tabText(i) for i in range(self.window.tabs_process.count())]
        self.assertTrue(any("Ruido" in t for t in tab_titles))
        self.assertTrue(any("Referencia" in t for t in tab_titles))
        self.assertTrue(any("Live" in t for t in tab_titles))
        self.assertTrue(any("Transmisión" in t or "Transmision" in t for t in tab_titles))
        self.assertTrue(any("Extinción" in t or "Extincion" in t for t in tab_titles))
        self.assertTrue(any("Multi-Espectro" in t for t in tab_titles))
        self.assertTrue(any("Ficha Metrológica" in t or "Ficha Metrologica" in t for t in tab_titles))

    def test_02_load_reserva_files_and_master_detection(self):
        """Carga los archivos de reserva y verifica la detección del Archivo Maestro."""
        if not (os.path.isfile(self.fbin_path) and os.path.isfile(self.oblicua_path)):
            self.skipTest("Archivos de reserva no encontrados")

        self.window._load_file_list([self.fbin_path, self.oblicua_path])
        self.assertEqual(len(self.window.loaded_spectra), 2)
        self.assertEqual(self.window.table_files.rowCount(), 2)

        # El archivo maestro debe haberse asignado automáticamente
        self.assertIsNotNone(self.window.master_spectrum)
        self.assertTrue(self.window.master_spectrum.is_master)
        self.assertIn("Fbin", self.window.master_spectrum.custom_name)
        self.assertIn("Maestro", self.window.lbl_master_status.text())

    def test_03_tab1_dark_noise_inspection(self):
        """Verifica los controles y gráficos de la Ventana 1 (Ruido / Dark)."""
        if not os.path.isfile(self.fbin_path):
            self.skipTest("Archivo fbin no encontrado")

        self.window._load_file_list([self.fbin_path])
        self.window._select_file_index(0)

        # Cambiar a pestaña 0 (Ruido)
        self.window.tabs_process.setCurrentIndex(0)
        self.assertIsNotNone(self.window.current_dark_1d)
        self.assertEqual(len(self.window.current_dark_1d), 5020)

        # Probar cambio de filtro en Ruido
        self.window.combo_dark_filter.setCurrentText("Savitzky-Golay")
        self.window.spin_dark_param.setValue(17)
        self.window._recalculate_all()

        self.assertIn("Bias Medio", self.window.lbl_dark_metrics.text())
        self.assertGreater(len(self.window.plot_dark_1d.listDataItems()), 0)

    def test_04_tab2_reference_roi_and_comparator(self):
        """Verifica la Ventana 2 (Referencia), ajuste de ROI y comparador de referencias."""
        if not os.path.isfile(self.oblicua_path):
            self.skipTest("Archivo oblicua no encontrado")

        self.window._load_file_list([self.oblicua_path])
        self.window._select_file_index(0)

        # Cambiar a pestaña 1 (Referencia)
        self.window.tabs_process.setCurrentIndex(1)
        self.assertIsNotNone(self.window.current_ref_1d)

        # Modificar spinners de ROI de referencia
        self.window.spin_ref_ymin.setValue(15)
        self.window.spin_ref_ymax.setValue(45)
        self.window._recalculate_all()

        y0, y1 = self.window.roi_ref_region.getRegion()
        self.assertEqual(int(round(y0)), 15)
        self.assertEqual(int(round(y1)), 45)
        self.assertIn("Cuentas Medias ROI", self.window.lbl_ref_metrics.text())

    def test_05_tab3_live_signal_and_sample_selector(self):
        """Verifica la Ventana 3 (Live / Señal) y selector directo de muestra del lote."""
        if not (os.path.isfile(self.fbin_path) and os.path.isfile(self.oblicua_path)):
            self.skipTest("Archivos de reserva no encontrados")

        self.window._load_file_list([self.fbin_path, self.oblicua_path])

        # Cambiar a pestaña 2 (Live / Señal)
        self.window.tabs_process.setCurrentIndex(2)
        self.assertEqual(self.window.combo_live_sample.count(), 2)

        # Cambiar muestra desde el combo de la pestaña Live
        self.window.combo_live_sample.setCurrentIndex(1)
        self.assertEqual(self.window.active_index, 1)
        self.assertIsNotNone(self.window.current_live_1d)
        self.assertIn("SBR", self.window.lbl_live_metrics.text())

    def test_06_tab4_transmittance_and_route_comparison(self):
        """Verifica la Ventana 4 (Transmisión) con comparación de Ruta A y Ruta B."""
        if not os.path.isfile(self.oblicua_path):
            self.skipTest("Archivo oblicua no encontrado")

        self.window._load_file_list([self.oblicua_path])
        self.window._select_file_index(0)

        # Cambiar a pestaña 3 (Transmisión)
        self.window.tabs_process.setCurrentIndex(3)

        # Seleccionar Ruta B
        self.window.radio_route_b.setChecked(True)
        self.window._recalculate_all()
        self.assertIsNotNone(self.window.current_t_calc)

        # Activar comparación de rutas
        self.window.chk_compare_routes.setChecked(True)
        self.window._refresh_transmittance_plots()

        # Debe contener curvas de transmitancia en el gráfico
        items = self.window.plot_trans_main.listDataItems()
        self.assertGreater(len(items), 0)
        self.assertIn("T_media", self.window.lbl_trans_metrics.text())

    def test_06b_transmittance_cascaded_filters(self):
        """Verifica la ejecución en cascada de las 3 fases (Despike -> Wiener -> Savitzky-Golay)."""
        if not os.path.isfile(self.fbin_path):
            self.skipTest("Archivo fbin no encontrado")

        self.window._load_file_list([self.fbin_path])
        self.window._select_file_index(0)
        self.window.tabs_process.setCurrentIndex(3)

        # Activar simultáneamente Fase 1 (Despike), Fase 2 (Wiener) y Fase 3 (Savitzky-Golay)
        self.window.chk_trans_despike.setChecked(True)
        self.window.spin_trans_despike_k.setValue(4.0)

        self.window.chk_trans_wiener.setChecked(True)
        self.window.spin_trans_wiener_alpha.setValue(1.2)

        self.window.combo_trans_filter.setCurrentText("Savitzky-Golay")
        self.window.spin_trans_param1.setValue(17)
        self.window.spin_trans_param2.setValue(3)

        self.window._recalculate_all()

        t_calc = self.window.current_t_calc
        self.assertIsNotNone(t_calc)
        self.assertEqual(len(t_calc), len(self.window.loaded_spectra[0].wavelengths))
        fin = np.isfinite(t_calc)
        self.assertGreater(np.sum(fin), 500)
        self.assertGreater(float(np.nanmean(t_calc)), 0.0)

    def test_06c_context_sensitive_parameter_panel(self):
        """Verifica que el panel de parámetros se adapte dinámicamente según el filtro seleccionado."""
        # 1. Savitzky-Golay
        self.window.combo_trans_filter.setCurrentText("Savitzky-Golay")
        self.assertEqual(self.window.lbl_trans_param1.text(), "Ventana:")
        self.assertFalse(self.window.lbl_trans_param1.isHidden())
        self.assertFalse(self.window.spin_trans_param1.isHidden())
        self.assertTrue(self.window.spin_trans_fc.isHidden())
        self.assertEqual(self.window.lbl_trans_param2.text(), "Orden p:")
        self.assertFalse(self.window.lbl_trans_param2.isHidden())
        self.assertFalse(self.window.spin_trans_param2.isHidden())

        # Probar que el orden p no supere a Ventana - 1
        self.window.spin_trans_param1.setValue(9)
        self.assertLessEqual(self.window.spin_trans_param2.maximum(), 8)

        # 2. Fourier Lowpass
        self.window.combo_trans_filter.setCurrentText("Fourier Lowpass")
        self.assertEqual(self.window.lbl_trans_param1.text(), "Corte fc:")
        self.assertFalse(self.window.lbl_trans_param1.isHidden())
        self.assertTrue(self.window.spin_trans_param1.isHidden())
        self.assertFalse(self.window.spin_trans_fc.isHidden())
        self.assertTrue(self.window.lbl_trans_param2.isHidden())
        self.assertTrue(self.window.spin_trans_param2.isHidden())

        # 3. Media Móvil
        self.window.combo_trans_filter.setCurrentText("Media Móvil")
        self.assertEqual(self.window.lbl_trans_param1.text(), "Ventana:")
        self.assertFalse(self.window.lbl_trans_param1.isHidden())
        self.assertFalse(self.window.spin_trans_param1.isHidden())
        self.assertTrue(self.window.spin_trans_fc.isHidden())
        self.assertTrue(self.window.lbl_trans_param2.isHidden())
        self.assertTrue(self.window.spin_trans_param2.isHidden())

        # 4. Ninguno
        self.window.combo_trans_filter.setCurrentText("Ninguno")
        self.assertTrue(self.window.lbl_trans_param1.isHidden())
        self.assertTrue(self.window.spin_trans_param1.isHidden())
        self.assertTrue(self.window.spin_trans_fc.isHidden())
        self.assertTrue(self.window.lbl_trans_param2.isHidden())
        self.assertTrue(self.window.spin_trans_param2.isHidden())

    def test_06d_uncertainty_band_attribution(self):
        """Verifica que la banda de incertidumbre ±σ_T corresponda exclusivamente a T_calc bajo ISO/GUM."""
        if not os.path.isfile(self.fbin_path):
            self.skipTest("Archivo fbin no encontrado")

        self.window._load_file_list([self.fbin_path])
        self.window._select_file_index(0)
        self.window.tabs_process.setCurrentIndex(3)
        self.window._recalculate_all()

        sigma_t = self.window.current_sigma_t
        t_calc = self.window.current_t_calc
        self.assertIsNotNone(sigma_t)
        self.assertIsNotNone(t_calc)
        self.assertEqual(len(sigma_t), len(t_calc))
        # sigma_t en índices finitos debe ser no negativo
        fin = np.isfinite(sigma_t)
        self.assertGreater(np.sum(fin), 500)
        self.assertTrue(np.all(sigma_t[fin] >= 0.0))
        # La incertidumbre promedio debe ser finita y positiva
        self.assertGreater(float(np.nanmean(sigma_t)), 0.0)

    def test_07_tab5_extinction_and_fano_peak_fitting(self):
        """Verifica la Ventana 5 (Extinción y Ajuste) con ajuste de resonancia de Fano y errores."""
        if not os.path.isfile(self.fbin_path):
            self.skipTest("Archivo fbin no encontrado")

        self.window._load_file_list([self.fbin_path])
        self.window._select_file_index(0)

        # Cambiar a pestaña 4 (Extinción)
        self.window.tabs_process.setCurrentIndex(4)
        self.assertIsNotNone(self.window.current_extinction)

        # Ajuste multi-pico (1 pico) de Fano en rango 600 - 750 nm
        self.window.spin_fit_n_peaks.setValue(1)
        self.window.combo_fit_model.setCurrentText("Resonancia de Fano")
        self.window.spin_fit_lmin.setValue(620.0)
        self.window.spin_fit_lmax.setValue(720.0)
        self.window._on_run_peak_fit()

        fit_res = self.window.last_peak_fit_results
        self.assertIsNotNone(fit_res)
        self.assertIn("fano", fit_res['model'].lower())
        self.assertEqual(len(fit_res['peaks_params']), 1)
        peak0 = fit_res['peaks_params'][0]
        self.assertGreater(peak0['lambda_0'], 600.0)
        self.assertGreater(peak0['u_lambda_0'], 0.0)
        self.assertGreater(fit_res['r_squared'], 0.50)
        self.assertEqual(self.window.table_fit_peaks.rowCount(), 1)
        self.assertIn("λ_res", self.window.lbl_fit_results.text())

    def test_08_manual_master_designation(self):
        """Verifica la designación manual de otro archivo como Maestro del lote."""
        if not (os.path.isfile(self.fbin_path) and os.path.isfile(self.oblicua_path)):
            self.skipTest("Archivos de reserva no encontrados")

        self.window._load_file_list([self.fbin_path, self.oblicua_path])
        self.assertEqual(self.window.master_spectrum.custom_name, self.window.loaded_spectra[0].custom_name)

        # Seleccionar la fila 1 y designar como Maestro
        self.window.table_files.selectRow(1)
        self.window._on_designate_master_clicked()
        self.assertEqual(self.window.master_spectrum.custom_name, self.window.loaded_spectra[1].custom_name)

    def test_10_adaptive_wiener_noise_cleaning_tabs_2_to_5(self):
        """Verifica la limpieza adaptativa por ruido BG (Wiener) en las Pestañas 2 a 5."""
        if not os.path.isfile(self.oblicua_path):
            self.skipTest("Archivo oblicua no encontrado")

        self.window._load_file_list([self.oblicua_path])
        self.window._select_file_index(0)

        # 1. Pestaña 2: Referencia
        r_raw = self.window.current_ref_1d.copy()
        self.window.chk_ref_adaptive.setChecked(True)
        self.window._recalculate_all()
        r_filt = self.window.current_ref_1d.copy()
        self.assertLess(np.nanstd(np.diff(r_filt)), np.nanstd(np.diff(r_raw)))

        # 2. Pestaña 3: Live / Señal
        l_raw = self.window.current_live_1d.copy()
        self.window.chk_live_adaptive.setChecked(True)
        self.window._recalculate_all()
        l_filt = self.window.current_live_1d.copy()
        self.assertLess(np.nanstd(np.diff(l_filt)), np.nanstd(np.diff(l_raw)))

        # 3. Pestaña 4: Transmisión
        t_raw = self.window.current_t_calc.copy()
        self.window.chk_trans_adaptive.setChecked(True)
        self.window._recalculate_all()
        t_filt = self.window.current_t_calc.copy()
        fin_t = np.isfinite(t_raw) & np.isfinite(t_filt)
        self.assertLess(np.nanstd(np.diff(t_filt[fin_t])), np.nanstd(np.diff(t_raw[fin_t])))

        # 4. Pestaña 5: Extinción
        e_raw = self.window.current_extinction.copy()
        self.window.chk_ext_adaptive.setChecked(True)
        self.window._recalculate_all()
        e_filt = self.window.current_extinction.copy()
        fin_e = np.isfinite(e_raw) & np.isfinite(e_filt)
        self.assertLessEqual(np.nanstd(np.diff(e_filt[fin_e])), np.nanstd(np.diff(e_raw[fin_e])))

    def test_11_transmittance_physical_accuracy_vs_sif_measured(self):
        """Verifica que T_calc coincida con T_meas dentro de márgenes físicos (< 1% discrepancia mediana)."""
        if not (os.path.isfile(self.fbin_path) and os.path.isfile(self.oblicua_path)):
            self.skipTest("Archivos de reserva no encontrados")

        self.window._load_file_list([self.fbin_path, self.oblicua_path])

        # Test 1D Fbin
        self.window._select_file_index(0)
        diff_0 = np.abs(self.window.current_t_calc - self.window.current_t_meas)
        med_diff_0 = np.nanmedian(diff_0[np.isfinite(diff_0)])
        self.assertLess(med_diff_0, 0.05)  # Concordancia ultra-alta (<0.05%)

        # Test 2D oblicua
        self.window._select_file_index(1)
        diff_1 = np.abs(self.window.current_t_calc - self.window.current_t_meas)
        med_diff_1 = np.nanmedian(diff_1[np.isfinite(diff_1)])
        self.assertLess(med_diff_1, 0.50)  # Concordancia excelente (<0.5%)

    def test_12_2d_heatmap_visibility_1d_and_2d(self):
        """Verifica que los mapas de calor 2D nunca se oculten y se visualicen correctamente."""
        if not os.path.isfile(self.fbin_path):
            self.skipTest("Archivo fbin no encontrado")

        self.window._load_file_list([self.fbin_path])
        self.window._select_file_index(0)

        # En archivo 1D, los 3 widgets 2D deben permanecer activos (no ocultos)
        self.assertFalse(self.window.widget_dark_2d.isHidden())
        self.assertFalse(self.window.widget_ref_2d.isHidden())
        self.assertFalse(self.window.widget_live_2d.isHidden())

        # Probar cambio a cada pestaña
        for idx in range(3):
            self.window.tabs_process.setCurrentIndex(idx)
            app.processEvents()
            widget_map = {0: self.window.widget_dark_2d, 1: self.window.widget_ref_2d, 2: self.window.widget_live_2d}
            self.assertFalse(widget_map[idx].isHidden())

    def test_13_reference_source_selection_priority(self):
        """Verifica que el selector de referencia priorice la propia en Auto y respete Maestro."""
        if not (os.path.isfile(self.fbin_path) and os.path.isfile(self.oblicua_path)):
            self.skipTest("Archivos de reserva no encontrados")

        self.window._load_file_list([self.fbin_path, self.oblicua_path])
        # Ambos archivos tienen su propia referencia
        self.window._select_file_index(1) # Oblicua

        # En Auto debe ser Archivo Activo
        self.assertIn("Archivo Activo", self.window.lbl_ref_source.text())

        # Si forzamos Maestro
        self.window.combo_ref_source.setCurrentText("Forzar 👑 Maestro")
        self.window._recalculate_all()
        self.assertIn("Heredado de 👑", self.window.lbl_ref_source.text())

        # Si forzamos Propia
        self.window.combo_ref_source.setCurrentText("Forzar Propia del Archivo")
        self.window._recalculate_all()
        self.assertIn("Archivo Activo", self.window.lbl_ref_source.text())

    def test_14_2d_and_1d_filter_propagation_pipeline(self):
        """Verifica que los filtros aplicados en 2D y 1D en Tabs 2 y 3 se propaguen a Tab 4 y Tab 5."""
        if not os.path.isfile(self.oblicua_path):
            self.skipTest("Archivo oblicua no encontrado")

        self.window._load_file_list([self.oblicua_path])
        self.window._select_file_index(0)

        # 1. Estado Crudo (Raw)
        self.window._on_reset_ref_filters()
        self.window._on_reset_live_filters()
        t_raw = self.window.current_t_calc.copy()
        ext_raw = self.window.current_extinction.copy()

        self.assertIsNotNone(t_raw)
        self.assertIsNotNone(ext_raw)

        # 2. Aplicar filtro Savitzky-Golay en Referencia (Tab 2) y Live (Tab 3)
        self.window.combo_ref_filter.setCurrentText("Savitzky-Golay")
        self.window.spin_ref_param.setValue(25)
        self.window.combo_live_filter.setCurrentText("Savitzky-Golay")
        self.window.spin_live_param.setValue(25)
        self.window._recalculate_all()

        t_filt_pre = self.window.current_t_calc.copy()
        ext_filt_pre = self.window.current_extinction.copy()

        # El filtrado en Tabs 2 y 3 debe modificar T_calc y Extinción
        diff_t = np.nanmean(np.abs(t_filt_pre - t_raw))
        self.assertGreater(diff_t, 1e-4, "El filtrado en Tab 2 y 3 debe propagarse a T_calc")

        # La derivada discreta (ruido de alta frecuencia) debe ser menor tras el filtrado
        fin_raw = np.isfinite(t_raw)
        fin_filt = np.isfinite(t_filt_pre)
        mask = fin_raw & fin_filt
        roughness_raw = np.nanstd(np.diff(t_raw[mask]))
        roughness_filt = np.nanstd(np.diff(t_filt_pre[mask]))
        self.assertLess(roughness_filt, roughness_raw, "T_calc con filtros 2D debe ser más suave que T_raw")

        # 3. Aplicar Post-Filtro en Transmisión (Tab 4) y verificar propagación a Extinción (Tab 5)
        self.window.combo_trans_filter.setCurrentText("Savitzky-Golay")
        self.window.spin_trans_param.setValue(31)
        self.window._recalculate_all()

        t_post = self.window.current_t_calc.copy()
        ext_post = self.window.current_extinction.copy()

        diff_post = np.nanmean(np.abs(t_post - t_filt_pre))
        self.assertGreater(diff_post, 1e-4, "El post-filtro de Tab 4 debe modificar T_calc")

        # Extinción en Tab 5 debe reflejar el post-filtro de Tab 4
        diff_ext = np.nanmean(np.abs(ext_post - ext_filt_pre))
        self.assertGreater(diff_ext, 1e-5, "La extinción de Tab 5 debe calcularse directamente con el T_calc post-procesado de Tab 4")

    def test_15_ergonomics_and_reset_buttons(self):
        """Verifica la ergonomía de la interfaz: paneles colapsables, sincronización ROI y botones de reset."""
        if not os.path.isfile(self.oblicua_path):
            self.skipTest("Archivo oblicua no encontrado")

        self.window._load_file_list([self.oblicua_path])
        self.window._select_file_index(0)

        # 1. Panel Izquierdo único con opciones contextuales sincronizadas al tab activo
        self.window.tabs_process.setCurrentIndex(1)
        self.assertEqual(self.window.stack_options.currentIndex(), 1)

        # 2. Sincronización de ROI vertical Ref -> Live
        self.window.spin_ref_ymin.setValue(18)
        self.window.spin_ref_ymax.setValue(62)
        self.window._on_sync_roi_to_live()
        self.assertEqual(self.window.spin_live_ymin.value(), 18)
        self.assertEqual(self.window.spin_live_ymax.value(), 62)

        # 3. Opciones de cálculo mutuamente excluyentes en Tab 4 (Ruta A y Ruta B)
        self.window.radio_route_b.setChecked(True)
        self.assertTrue(self.window.radio_route_b.isChecked())
        self.assertFalse(self.window.radio_route_a.isChecked())
        self.window.radio_route_a.setChecked(True)
        self.assertTrue(self.window.radio_route_a.isChecked())
        self.assertFalse(self.window.radio_route_b.isChecked())

        # 4. Botones Reset (↺ Raw)
        self.window.chk_ref_despike.setChecked(True)
        self.window.combo_ref_filter.setCurrentText("Fourier Lowpass")
        self.window._on_reset_ref_filters()
        self.assertFalse(self.window.chk_ref_despike.isChecked())
        self.assertEqual(self.window.combo_ref_filter.currentIndex(), 0)

        self.window.chk_live_despike.setChecked(True)
        self.window.combo_live_filter.setCurrentText("Fourier Lowpass")
        self.window._on_reset_live_filters()
        self.assertFalse(self.window.chk_live_despike.isChecked())
        self.assertEqual(self.window.combo_live_filter.currentIndex(), 0)


if __name__ == '__main__':
    unittest.main()
