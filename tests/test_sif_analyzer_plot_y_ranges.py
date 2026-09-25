"""
tests/test_sif_analyzer_plot_y_ranges.py
=========================================
Pruebas automatizadas de los menús contextuales de clic derecho en los gráficos
del Analizador SIF (`sif_analyzer.py`): presets semánticos de escala vertical (Eje Y),
cálculo dinámico 0 a Máximo, diálogo de rango manual y auto-rango independiente.
"""

import os
import sys
import unittest
import numpy as np

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from PyQt6.QtWidgets import QApplication
from sif_analyzer import SifAnalyzerWindow, CustomYRangeDialog

app = QApplication.instance()
if app is None:
    app = QApplication([sys.argv[0], "-platform", "offscreen"])


class TestSifAnalyzerPlotYRanges(unittest.TestCase):

    def setUp(self):
        self.window = SifAnalyzerWindow()

    def tearDown(self):
        self.window.close()

    def test_01_presets_structure_for_all_categories(self):
        """Verifica que cada categoría espectroscópica tenga sus presets semánticos definidos."""
        # Extinción
        ext_presets = self.window._get_y_presets_for_category("extinction")
        ext_ranges = [r for _, r in ext_presets]
        self.assertIn((0.0, 100.0), ext_ranges)
        self.assertIn((0.0, 50.0), ext_ranges)
        self.assertIn((0.0, 25.0), ext_ranges)
        self.assertIn((0.0, 10.0), ext_ranges)
        self.assertIn(None, ext_ranges)  # 0 a Máximo dinámico

        # Transmitancia
        trans_presets = self.window._get_y_presets_for_category("transmittance")
        trans_ranges = [r for _, r in trans_presets]
        self.assertIn((0.0, 100.0), trans_ranges)
        self.assertIn((50.0, 100.0), trans_ranges)
        self.assertIn((0.0, 50.0), trans_ranges)
        self.assertIn((0.0, 120.0), trans_ranges)
        self.assertIn(None, trans_ranges)

        # Cuentas ADC
        counts_presets = self.window._get_y_presets_for_category("counts")
        counts_ranges = [r for _, r in counts_presets]
        self.assertIn((0.0, 65535.0), counts_ranges)
        self.assertIn((0.0, 10000.0), counts_ranges)
        self.assertIn((0.0, 5000.0), counts_ranges)
        self.assertIn(None, counts_ranges)

        # Residuos
        res_presets = self.window._get_y_presets_for_category("residuals")
        res_ranges = [r for _, r in res_presets]
        self.assertIn((-10.0, 10.0), res_ranges)
        self.assertIn((-5.0, 5.0), res_ranges)
        self.assertIn((-2.0, 2.0), res_ranges)
        self.assertIn((-1.0, 1.0), res_ranges)

        # Multi y Polar
        multi_presets = self.window._get_y_presets_for_category("multi")
        self.assertIn((0.0, 1.0), [r for _, r in multi_presets])
        polar_presets = self.window._get_y_presets_for_category("polar")
        self.assertIn((0.0, 1.0), [r for _, r in polar_presets])

    def test_02_apply_extinction_y_ranges(self):
        """Aplica rangos en el gráfico de extinción y valida el ViewBox."""
        plot = self.window.plot_ext_main

        # Preset (0, 50)
        plot.setYRange(0.0, 50.0, padding=0)
        app.processEvents()
        y_range = plot.getViewBox().viewRange()[1]
        self.assertAlmostEqual(y_range[0], 0.0, delta=0.5)
        self.assertAlmostEqual(y_range[1], 50.0, delta=0.5)

        # Preset (0, 25)
        plot.setYRange(0.0, 25.0, padding=0)
        app.processEvents()
        y_range = plot.getViewBox().viewRange()[1]
        self.assertAlmostEqual(y_range[0], 0.0, delta=0.5)
        self.assertAlmostEqual(y_range[1], 25.0, delta=0.5)

    def test_03_apply_transmittance_y_ranges(self):
        """Aplica rangos en el gráfico de transmitancia y valida el ViewBox."""
        plot = self.window.plot_trans_main

        # Preset (50, 100)
        plot.setYRange(50.0, 100.0, padding=0)
        app.processEvents()
        y_range = plot.getViewBox().viewRange()[1]
        self.assertAlmostEqual(y_range[0], 50.0, delta=0.5)
        self.assertAlmostEqual(y_range[1], 100.0, delta=0.5)

        # Preset (0, 120)
        plot.setYRange(0.0, 120.0, padding=0)
        app.processEvents()
        y_range = plot.getViewBox().viewRange()[1]
        self.assertAlmostEqual(y_range[0], 0.0, delta=0.5)
        self.assertAlmostEqual(y_range[1], 120.0, delta=0.5)

    def test_04_set_plot_y_zero_to_max(self):
        """Verifica el cálculo reactivo de 0 a Máximo con margen del 5%."""
        plot = self.window.plot_ext_main
        # Añadir curva sintética con pico en 80.0
        x_vals = np.linspace(500, 700, 50)
        y_vals = np.exp(-((x_vals - 600) ** 2) / (2 * 15 ** 2)) * 80.0
        plot.plot(x_vals, y_vals)
        app.processEvents()

        self.window._set_plot_y_zero_to_max(plot)
        app.processEvents()
        y_range = plot.getViewBox().viewRange()[1]
        self.assertAlmostEqual(y_range[0], 0.0, delta=0.5)
        self.assertAlmostEqual(y_range[1], 80.0 * 1.05, delta=1.0)

    def test_05_custom_y_range_dialog(self):
        """Verifica la inicialización y retorno del diálogo CustomYRangeDialog."""
        dlg = CustomYRangeDialog(12.5, 87.5)
        self.assertEqual(dlg.spin_min.value(), 12.5)
        self.assertEqual(dlg.spin_max.value(), 87.5)

        dlg.spin_min.setValue(0.0)
        dlg.spin_max.setValue(45.0)
        ymin, ymax = dlg.get_range()
        self.assertEqual(ymin, 0.0)
        self.assertEqual(ymax, 45.0)
        dlg.close()


if __name__ == '__main__':
    unittest.main()
