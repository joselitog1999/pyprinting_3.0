"""
tests/test_sif_analyzer_ergonomics.py
======================================
Pruebas automatizadas de la reestructuración ergonómica de UI del
Analizador SIF (`sif_analyzer.py`): navegación por teclado en la tabla de
archivos, tarjeta de metadatos con insignia FVB (1D) vs Imagen 2D,
sincronización del panel de opciones contextuales (`stack_options`) con la
pestaña activa (`tabs_process`), y disposición ergonómica en 3 paneles
(Izquierda: Archivos/Óptica, Centro: Gráficos, Derecha: Opciones colapsable).
"""

import os
import sys
import unittest

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from PyQt6.QtWidgets import QApplication
from sif_analyzer import SifAnalyzerWindow

app = QApplication.instance()
if app is None:
    app = QApplication([sys.argv[0], "-platform", "offscreen"])


class TestSifAnalyzerErgonomics(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.reserva_dir = os.path.join(WORKSPACE_ROOT, "reserva")
        cls.fbin_path = os.path.join(cls.reserva_dir, "Fbin_hex_100umslit_50ms_nopol_pos_0.sif")
        cls.oblicua_path = os.path.join(cls.reserva_dir, "oblicua_100umslit_1seg_176deg.sif")

    def setUp(self):
        self.window = SifAnalyzerWindow()

    def tearDown(self):
        self.window.close()

    # --------------------------------------------------------------------
    # 1. Navegación por teclado / currentCellChanged en la tabla de archivos
    # --------------------------------------------------------------------
    def test_01_keyboard_navigation_switches_active_file(self):
        """Al cambiar la celda actual de la tabla (equivalente a flechas ↑/↓), el espectro activo cambia."""
        if not (os.path.isfile(self.fbin_path) and os.path.isfile(self.oblicua_path)):
            self.skipTest("Archivos de reserva no encontrados")

        self.window._load_file_list([self.fbin_path, self.oblicua_path])
        self.window._select_file_index(0)
        self.assertEqual(self.window.active_index, 0)

        # Simula navegación por teclado: mover la celda actual a la fila 1
        self.window.table_files.setCurrentCell(1, 1)
        app.processEvents()
        self.assertEqual(self.window.active_index, 1)

        # Volver a la fila 0
        self.window.table_files.setCurrentCell(0, 1)
        app.processEvents()
        self.assertEqual(self.window.active_index, 0)

        # Re-emitir la misma fila activa no debe forzar un recálculo redundante
        # (la lambda de currentCellChanged descarta cur_r == active_index)
        self.window.table_files.setCurrentCell(0, 2)
        app.processEvents()
        self.assertEqual(self.window.active_index, 0)

    # --------------------------------------------------------------------
    # 2. Insignia de metadatos: Imagen Espacial 2D vs Espectro 1D (FVB)
    # --------------------------------------------------------------------
    def test_02_metadata_badge_distinguishes_1d_and_2d(self):
        """La tarjeta de metadatos muestra insignias y campos distintos para archivos 1D (FVB) y 2D."""
        if not (os.path.isfile(self.fbin_path) and os.path.isfile(self.oblicua_path)):
            self.skipTest("Archivos de reserva no encontrados")

        self.window._load_file_list([self.fbin_path, self.oblicua_path])

        # Fbin es 1D (FVB)
        self.window._select_file_index(0)
        spec0 = self.window.loaded_spectra[0]
        self.assertFalse(spec0.is_2d)
        self.assertIn("Espectro 1D", self.window.lbl_meta_badge.text())
        self.assertIn("FVB", self.window.lbl_meta_badge.text())
        self.assertIn("px", self.window.lbl_meta_dims.text())
        self.assertIn("Rango espectral", self.window.lbl_meta_scale_range.text())
        self.assertIn("Dispersión", self.window.lbl_meta_scale_range.text())

        # Oblicua es 2D
        self.window._select_file_index(1)
        spec1 = self.window.loaded_spectra[1]
        self.assertTrue(spec1.is_2d or spec1.height > 1)
        self.assertIn("2D", self.window.lbl_meta_badge.text())
        self.assertIn(f"{spec1.height}", self.window.lbl_meta_dims.text())
        self.assertIn(f"{spec1.width}", self.window.lbl_meta_dims.text())
        self.assertIn("FOV_Y", self.window.lbl_meta_scale_range.text())
        self.assertIn("µm/px", self.window.lbl_meta_scale_range.text())

    # --------------------------------------------------------------------
    # 3. Sincronización de stack_options con tabs_process.currentChanged
    # --------------------------------------------------------------------
    def test_03_stack_options_syncs_with_active_tab(self):
        """El índice de stack_options sigue sincrónicamente al índice de tabs_process."""
        self.assertEqual(self.window.stack_options.count(), self.window.tabs_process.count())
        for idx in range(self.window.tabs_process.count()):
            self.window.tabs_process.setCurrentIndex(idx)
            app.processEvents()
            self.assertEqual(self.window.stack_options.currentIndex(), idx)

    # --------------------------------------------------------------------
    # 4. Topología ergonómica de 3 paneles y panel derecho de opciones
    # --------------------------------------------------------------------
    def test_04_three_panel_layout_with_right_options(self):
        """El splitter principal posee 3 paneles: Izquierdo (archivos/óptica), Central (gráficos) y Derecho (opciones)."""
        # El splitter principal debe tener exactamente 3 hojas
        self.assertEqual(self.window.main_splitter.count(), 3)
        self.assertEqual(self.window.main_splitter.widget(0), self.window.left_panel)
        self.assertEqual(self.window.main_splitter.widget(1), self.window.center_panel)
        self.assertEqual(self.window.main_splitter.widget(2), self.window.right_panel)

        # Panel izquierdo contiene la instrumentación óptica
        self.assertTrue(hasattr(self.window, "combo_objective"))
        self.assertTrue(self.window.left_panel.isAncestorOf(self.window.combo_objective))

        # Panel derecho contiene el stack de opciones contextuales
        self.assertTrue(hasattr(self.window, "stack_options"))
        self.assertTrue(self.window.right_panel.isAncestorOf(self.window.stack_options))

        # Controles de toggle (botón en barra superior y acción de menú con atajo Ctrl+D)
        self.assertTrue(hasattr(self.window, "btn_toggle_right"))
        self.assertTrue(hasattr(self.window, "act_toggle_right"))
        self.assertFalse(self.window.right_panel.isHidden())
        self.assertTrue(self.window.btn_toggle_right.isChecked())
        self.assertTrue(self.window.act_toggle_right.isChecked())

        # Probar colapso y restauración del panel derecho
        self.window._on_toggle_right_panel()
        self.assertTrue(self.window.right_panel.isHidden())
        self.assertFalse(self.window.btn_toggle_right.isChecked())
        self.assertFalse(self.window.act_toggle_right.isChecked())

        self.window._on_toggle_right_panel()
        self.assertFalse(self.window.right_panel.isHidden())
        self.assertTrue(self.window.btn_toggle_right.isChecked())
        self.assertTrue(self.window.act_toggle_right.isChecked())


if __name__ == '__main__':
    unittest.main()
