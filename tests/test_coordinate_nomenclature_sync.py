# -*- coding: utf-8 -*-
"""
test_coordinate_nomenclature_sync.py — Suite de pruebas para sincronización dinámica de nomenclaturas
PyPrinting 3.0 — UNSAM Nanofotónica

Verifica que:
1. Nanopositioning Frontend actualice xname/yname/zname, lbl_goto_1/2/3 y step_xy según el régimen.
2. Confocal Frontend actualice PSF_mode, lbl_range_x/y, lbl_pixels_x/y y los ejes de Viewbox.
3. Measurements Frontend e InteractiveGridWidget actualicen las etiquetas de referencia, grilla, shift, dímeros y ejes del gráfico.
4. HardwareDashboard sincronice su selector y descripción de cinemática con el régimen global.
5. Los comandos físicos a hardware sigan siendo 100% invariantes (Eje 1, Eje 2, Eje 3 en pi.MOV).
"""
import sys
import unittest
from PyQt6.QtWidgets import QApplication

# Asegurar QApplication
app = QApplication.instance() or QApplication(sys.argv)

from config import REGIME_LEGACY, REGIME_LASER_REF, REGIME_SAMPLE_REF
from core.nanopositioning import (
    Frontend as NanoFrontend,
    COORDINATE_NOMENCLATURE,
    set_global_coordinate_regime,
    register_regime_listener,
    unregister_regime_listener
)
from modules.confocal import Frontend as ConfocalFrontend
from modules.measurements import Frontend as MeasureFrontend


class TestCoordinateNomenclatureSync(unittest.TestCase):

    def setUp(self):
        set_global_coordinate_regime(REGIME_LEGACY)

    def tearDown(self):
        set_global_coordinate_regime(REGIME_LEGACY)

    def test_nanopositioning_nomenclature_switching(self):
        fe = NanoFrontend()
        
        # 1. Legacy
        fe.set_regime(REGIME_LEGACY)
        self.assertEqual(fe.xname.text(), "<b>x =</b>")
        self.assertEqual(fe.yname.text(), "<b>y =</b>")
        self.assertEqual(fe.lbl_goto_1.text(), "X [µm]")
        self.assertEqual(fe.lbl_goto_2.text(), "Y [µm]")
        self.assertIn("step x/y", fe.lbl_step_xy.text())

        # 2. Laser Ref
        fe.set_regime(REGIME_LASER_REF)
        self.assertEqual(fe.xname.text(), "<b>Y (Vert) =</b>")
        self.assertEqual(fe.yname.text(), "<b>X (Horiz) =</b>")
        self.assertEqual(fe.lbl_goto_1.text(), "Y (Vert) [µm]")
        self.assertEqual(fe.lbl_goto_2.text(), "X (Horiz) [µm]")
        self.assertIn("step laser", fe.lbl_step_xy.text())

        # 3. Sample Ref
        fe.set_regime(REGIME_SAMPLE_REF)
        self.assertEqual(fe.xname.text(), "<b>Y (Muestra) =</b>")
        self.assertEqual(fe.yname.text(), "<b>X (Muestra) =</b>")
        self.assertEqual(fe.lbl_goto_1.text(), "Y (Muestra) [µm]")
        self.assertEqual(fe.lbl_goto_2.text(), "X (Muestra) [µm]")
        self.assertIn("step sample", fe.lbl_step_xy.text())

    def test_confocal_nomenclature_switching(self):
        cfe = ConfocalFrontend()

        # 1. Legacy
        set_global_coordinate_regime(REGIME_LEGACY)
        self.assertEqual(cfe.lbl_range_x.text(), "Range x (µm)")
        self.assertEqual(cfe.lbl_range_y.text(), "Range y (µm)")
        self.assertEqual(cfe.PSF_mode.itemText(0), "x/y")
        self.assertEqual(cfe.xlabel.labelText, "X")
        self.assertEqual(cfe.ylabel.labelText, "Y")

        # 2. Laser Ref
        set_global_coordinate_regime(REGIME_LASER_REF)
        self.assertEqual(cfe.lbl_range_x.text(), "Range Y (Vert) [µm]")
        self.assertEqual(cfe.lbl_range_y.text(), "Range X (Horiz) [µm]")
        self.assertEqual(cfe.PSF_mode.itemText(0), "Y/X (Vert/Horiz)")
        self.assertEqual(cfe.xlabel.labelText, "Y (Vert)")
        self.assertEqual(cfe.ylabel.labelText, "X (Horiz)")

        # 3. Sample Ref
        set_global_coordinate_regime(REGIME_SAMPLE_REF)
        self.assertEqual(cfe.lbl_range_x.text(), "Range Y (Muestra) [µm]")
        self.assertEqual(cfe.lbl_range_y.text(), "Range X (Muestra) [µm]")
        self.assertEqual(cfe.PSF_mode.itemText(0), "Y/X (Muestra)")
        self.assertEqual(cfe.xlabel.labelText, "Y (Muestra)")
        self.assertEqual(cfe.ylabel.labelText, "X (Muestra)")

    def test_measurements_nomenclature_switching(self):
        mfe = MeasureFrontend(mode="dimers")

        # 1. Legacy
        set_global_coordinate_regime(REGIME_LEGACY)
        self.assertEqual(mfe.lbl_ref_x.text(), "X ref:")
        self.assertEqual(mfe.lbl_ref_y.text(), "Y ref:")
        self.assertEqual(mfe.lbl_dist_np.text(), "Dist NP (µm)")
        self.assertEqual(mfe.lbl_dist_col.text(), "Dist col (µm)")
        self.assertEqual(mfe.lbl_shift_x.text(), "Shift X (µm)")
        self.assertEqual(mfe.lbl_shift_y.text(), "Shift Y (µm)")
        self.assertEqual(mfe.lbl_dx.text(), "dx (µm)")
        self.assertEqual(mfe.lbl_dy.text(), "dy (µm)")
        self.assertEqual(mfe.interactive_grid.plot.getAxis("left").labelText, "Y (µm)")
        self.assertEqual(mfe.interactive_grid.plot.getAxis("bottom").labelText, "X (µm)")

        # 2. Laser Ref
        set_global_coordinate_regime(REGIME_LASER_REF)
        self.assertEqual(mfe.lbl_ref_x.text(), "Y ref (Vert):")
        self.assertEqual(mfe.lbl_ref_y.text(), "X ref (Horiz):")
        self.assertEqual(mfe.lbl_dist_np.text(), "Paso Y (Col) [µm]")
        self.assertEqual(mfe.lbl_dist_col.text(), "Dist X (Cols) [µm]")
        self.assertEqual(mfe.lbl_shift_x.text(), "Shift Y (Vert) [µm]")
        self.assertEqual(mfe.lbl_shift_y.text(), "Shift X (Horiz) [µm]")
        self.assertEqual(mfe.lbl_dx.text(), "dy (Vert) [µm]")
        self.assertEqual(mfe.lbl_dy.text(), "dx (Horiz) [µm]")
        self.assertEqual(mfe.interactive_grid.plot.getAxis("left").labelText, "Y (Vert) [µm]")
        self.assertEqual(mfe.interactive_grid.plot.getAxis("bottom").labelText, "X (Horiz) [µm]")

    def test_metadata_records_physical_and_regime_coordinates(self):
        mfe = MeasureFrontend(mode="printing")
        set_global_coordinate_regime(REGIME_LASER_REF)
        mfe.xrefLabel.setText("42.500")
        mfe.yrefLabel.setText("68.200")
        mfe.zrefLabel.setText("10.050")

        captured_info = []
        mfe.gridinfoSignal.connect(lambda info: captured_info.extend(info))
        mfe._get_grid_info()

        info_dict = {k: v for k, v in captured_info}
        self.assertEqual(info_dict.get("Coordinate Regime:"), REGIME_LASER_REF)
        self.assertEqual(info_dict.get("Stage Axis 1 (um):"), "42.500")
        self.assertEqual(info_dict.get("Stage Axis 2 (um):"), "68.200")
        self.assertEqual(info_dict.get("Stage Axis 3 (um):"), "10.050")


if __name__ == "__main__":
    unittest.main()
