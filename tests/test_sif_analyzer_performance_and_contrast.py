"""
tests/test_sif_analyzer_performance_and_contrast.py
====================================================
Pruebas automatizadas de la Fase 2 del Analizador SIF (`sif_analyzer.py` y
`core/sif_processor.py`): niveles de contraste robustos por percentiles,
renderizado perezoso (Lazy Rendering) de mapas de calor 2D desacoplado de
`_recalculate_all()`, presets de contraste 2D, y sincronización bidireccional
de ROI entre las reglas arrastrables 2D y los spinboxes del panel izquierdo.
"""

import os
import sys
import unittest
import numpy as np

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from PyQt6.QtWidgets import QApplication

app = QApplication.instance()
if app is None:
    app = QApplication([sys.argv[0], "-platform", "offscreen"])

from core.sif_processor import compute_robust_contrast_levels
from sif_analyzer import SifAnalyzerWindow, CONTRAST_PRESETS, CONTRAST_MANUAL_LABEL


class TestComputeRobustContrastLevels(unittest.TestCase):
    """Agente de Algoritmos Científicos — Punto 1 del plan de verificación."""

    def test_extreme_outlier_does_not_corrupt_vmax(self):
        rng = np.random.default_rng(42)
        data = rng.normal(100.0, 10.0, size=(64, 256))
        data[5, 5] = 1e7  # rayo cósmico / píxel caliente
        vmin, vmax = compute_robust_contrast_levels(data, p_low=1.0, p_high=99.0)

        expected_vmax = float(np.percentile(data[np.isfinite(data)], 99.0))
        self.assertAlmostEqual(vmax, expected_vmax, places=6)
        self.assertLess(vmax, 1e6, "vmax no debe verse arrastrado por el outlier de 10^7 cuentas")
        self.assertGreater(vmin, 0.0)
        self.assertLess(vmin, vmax)

    def test_dead_pixel_does_not_corrupt_vmin(self):
        rng = np.random.default_rng(7)
        data = rng.normal(500.0, 20.0, size=(32, 128))
        data[0, 0] = -1e6  # píxel muerto / subdesbordado
        vmin, vmax = compute_robust_contrast_levels(data, p_low=1.0, p_high=99.0)
        self.assertGreater(vmin, -1e5, "vmin no debe verse arrastrado por el píxel muerto")

    def test_empty_or_all_nan_returns_safe_default(self):
        data = np.full((10, 10), np.nan)
        vmin, vmax = compute_robust_contrast_levels(data)
        self.assertEqual((vmin, vmax), (0.0, 1.0))

    def test_degenerate_constant_matrix_avoids_zero_width(self):
        data = np.full((10, 10), 42.0)
        vmin, vmax = compute_robust_contrast_levels(data, p_low=1.0, p_high=99.0)
        self.assertGreater(vmax, vmin)


class TestSifAnalyzerPerformanceAndContrastGUI(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.reserva_dir = os.path.join(WORKSPACE_ROOT, "reserva")
        cls.oblicua_path = os.path.join(cls.reserva_dir, "oblicua_100umslit_1seg_176deg.sif")

    def setUp(self):
        self.window = SifAnalyzerWindow()
        if os.path.isfile(self.oblicua_path):
            self.window._load_file_list([self.oblicua_path])
            self.window._select_file_index(0)

    def tearDown(self):
        self.window.close()

    def _require_reserva(self):
        if not os.path.isfile(self.oblicua_path):
            self.skipTest("Archivo oblicua no encontrado")

    # --------------------------------------------------------------------
    # 2. Lazy Rendering: desacoplamiento de pestañas ocultas
    # --------------------------------------------------------------------
    def test_lazy_rendering_defers_hidden_2d_tabs_and_renders_on_demand(self):
        self._require_reserva()

        self.window.tabs_process.setCurrentIndex(4)  # Extinción (sin mapa 2D)
        app.processEvents()
        self.window._recalculate_all()

        # Las 3 pestañas con mapas 2D deben quedar marcadas como "sucias" (no renderizadas)
        self.assertTrue(self.window._tab_2d_dirty[0])
        self.assertTrue(self.window._tab_2d_dirty[1])
        self.assertTrue(self.window._tab_2d_dirty[2])

        # Al conmutar a la pestaña 1 (Referencia), debe renderizarse bajo demanda y limpiar la bandera
        self.window.tabs_process.setCurrentIndex(1)
        app.processEvents()
        self.assertFalse(self.window._tab_2d_dirty[1])
        self.assertIsNotNone(self.window._ref_2d_plot_cache)
        self.assertIsNotNone(self.window.img_ref_2d.image)

        # Ruido y Live/Señal siguen sucias: no se tocaron sus texturas
        self.assertTrue(self.window._tab_2d_dirty[0])
        self.assertTrue(self.window._tab_2d_dirty[2])

    def test_active_tab_renders_immediately_during_recalculate_all(self):
        self._require_reserva()

        self.window.tabs_process.setCurrentIndex(2)  # Live / Señal
        app.processEvents()
        self.window._recalculate_all()

        # La pestaña activa (2) se renderiza de inmediato -> no queda sucia
        self.assertFalse(self.window._tab_2d_dirty[2])
        # Las otras dos pestañas 2D quedan diferidas
        self.assertTrue(self.window._tab_2d_dirty[0])
        self.assertTrue(self.window._tab_2d_dirty[1])

    # --------------------------------------------------------------------
    # 3. Presets de Contraste 2D
    # --------------------------------------------------------------------
    def test_contrast_preset_change_updates_image_levels_without_error(self):
        self._require_reserva()

        self.window.tabs_process.setCurrentIndex(1)
        app.processEvents()
        self.assertIsNotNone(self.window.img_ref_2d.levels)

        for preset_name in list(CONTRAST_PRESETS.keys()):
            self.window.combo_ref_contrast.setCurrentText(preset_name)
            app.processEvents()
            levels = self.window.img_ref_2d.levels
            self.assertIsNotNone(levels)
            self.assertEqual(len(levels), 2)
            self.assertLess(levels[0], levels[1])

    def test_manual_lut_preset_does_not_raise_and_preserves_last_levels(self):
        self._require_reserva()
        self.window.tabs_process.setCurrentIndex(1)
        app.processEvents()
        self.window.combo_ref_contrast.setCurrentText("✨ Auto-Robusto (1% - 99%)")
        levels_before = tuple(self.window.img_ref_2d.levels)
        self.window.combo_ref_contrast.setCurrentText(CONTRAST_MANUAL_LABEL)
        app.processEvents()
        levels_after = tuple(self.window.img_ref_2d.levels)
        self.assertEqual(levels_before, levels_after)

    def test_contrast_preset_all_three_panes_present(self):
        for combo_name in ("combo_dark_contrast", "combo_ref_contrast", "combo_live_contrast"):
            self.assertTrue(hasattr(self.window, combo_name))
            combo = getattr(self.window, combo_name)
            self.assertGreaterEqual(combo.count(), len(CONTRAST_PRESETS))

    # --------------------------------------------------------------------
    # 4. Sincronización de ROI (bidireccional)
    # --------------------------------------------------------------------
    def test_roi_region_drag_updates_spinboxes(self):
        self._require_reserva()
        self.window.roi_ref_region.setRegion([20, 60])
        app.processEvents()
        self.assertEqual(self.window.spin_ref_ymin.value(), 20)
        self.assertEqual(self.window.spin_ref_ymax.value(), 60)

    def test_spinbox_change_updates_roi_region(self):
        self._require_reserva()
        self.window.spin_ref_ymin.setValue(12)
        self.window.spin_ref_ymax.setValue(48)
        y0, y1 = self.window.roi_ref_region.getRegion()
        self.assertEqual(int(round(min(y0, y1))), 12)
        self.assertEqual(int(round(max(y0, y1))), 48)

    def test_copy_ref_roi_button_alias_present_and_functional(self):
        self._require_reserva()
        self.assertTrue(hasattr(self.window, 'btn_copy_ref_roi'))
        self.window.spin_ref_ymin.setValue(30)
        self.window.spin_ref_ymax.setValue(70)
        self.window.btn_copy_ref_roi.click()
        self.assertEqual(self.window.spin_live_ymin.value(), 30)
        self.assertEqual(self.window.spin_live_ymax.value(), 70)

    # --------------------------------------------------------------------
    # Extras: Crosshair HUD y HistogramLUTWidget
    # --------------------------------------------------------------------
    def test_crosshair_hud_updates_on_mouse_move(self):
        self._require_reserva()
        self.window.tabs_process.setCurrentIndex(1)
        app.processEvents()
        from PyQt6.QtCore import QPointF
        pos_scene = self.window.plot_ref_2d.plotItem.vb.mapViewToScene(QPointF(600.0, 20.0))
        self.window._on_mouse_moved_ref_2d(pos_scene)
        hud_text = self.window.lbl_ref_2d_hud.text()
        self.assertIn("λ", hud_text)
        self.assertIn("Intensidad", hud_text)
        self.assertNotIn("λ = -- ", hud_text)

    def test_histogram_lut_toggle_controls_visibility(self):
        self.assertTrue(self.window.hist_ref_2d.isHidden())
        self.window.chk_ref_hist.setChecked(True)
        self.assertFalse(self.window.hist_ref_2d.isHidden())
        self.window.chk_ref_hist.setChecked(False)
        self.assertTrue(self.window.hist_ref_2d.isHidden())


if __name__ == '__main__':
    unittest.main()
