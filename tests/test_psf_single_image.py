# -*- coding: utf-8 -*-
"""
test_psf_single_image.py — Test de Integración para el Modo Foto Única & Líneas de Corte
PyPrinting 3.0 — UNSAM Nanofotónica
"""
import sys
import os
from pathlib import Path
import numpy as np

# Configurar entorno headless
os.environ["QT_QPA_PLATFORM"] = "offscreen"

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
for sub in [BASE_DIR / "core", BASE_DIR / "modules", BASE_DIR / "analysis"]:
    if str(sub) not in sys.path:
        sys.path.insert(0, str(sub))

from PyQt6.QtWidgets import QApplication
from analysis.psf_analyzer import (
    extract_arbitrary_line_profile,
    extract_radial_profile,
    fit_1d_gaussian,
    SingleImageProfileWidget,
    PSFAnalyzerWindow
)


def test_psf_single_image_mode():
    app = QApplication.instance() or QApplication(sys.argv)

    # 1. Test matemático de extract_arbitrary_line_profile
    Z_synth = np.zeros((100, 100), dtype=np.float64)
    # Colocar una línea vertical brillante en X=50
    Z_synth[:, 50] = 1000.0
    s_axis, prof = extract_arbitrary_line_profile(Z_synth, (0, 20), (99, 20), pixel_size_um=0.05, line_width_px=1)
    assert len(s_axis) == 100
    assert prof[50] == 1000.0
    assert prof[0] == 0.0
    print("PASS: extract_arbitrary_line_profile verificado matemáticamente.")

    # 2. Test matemático de fit_1d_gaussian
    s_test = np.linspace(-2.0, 2.0, 200)
    sigma_true = 0.35
    fwhm_true = 2.0 * np.sqrt(2.0 * np.log(2.0)) * sigma_true
    y_test = 100.0 + 5000.0 * np.exp(-0.5 * (s_test / sigma_true)**2)
    fit_res = fit_1d_gaussian(s_test, y_test)
    assert fit_res is not None
    assert abs(fit_res["fwhm"] - fwhm_true) < 1e-3
    assert abs(fit_res["amplitude"] - 5000.0) < 1e-2
    assert abs(fit_res["offset"] - 100.0) < 1e-2
    assert fit_res["r_squared"] > 0.999
    print(f"PASS: fit_1d_gaussian recuperó FWHM exacto ({fit_res['fwhm']:.4f} um, R²={fit_res['r_squared']:.4f}).")

    # 3. Test de SingleImageProfileWidget
    win = PSFAnalyzerWindow()
    win.show()
    assert win.main_tabs.count() == 2
    assert win.main_tabs.tabText(0) == "📸 Foto Única & Líneas de Corte"
    assert win.main_tabs.tabText(1) == "🔬 Co-Alineación Dual Confocal"

    single_w = win.tab_single
    assert single_w.Z is not None
    assert single_w.Z.shape == (100, 100)

    # Probar diferentes modos de corte
    for cut_idx in range(6):
        single_w.combo_cut_mode.setCurrentIndex(cut_idx)
        assert len(single_w.current_dist) > 0
        assert len(single_w.current_profile) == len(single_w.current_dist)
    print("PASS: Modos de corte (libre, horizontal, vertical, diagonales, radial 360°) ejecutados sin error.")

    # Probar conmutación de unidades (um vs px)
    single_w.combo_units.setCurrentIndex(1)
    assert single_w.unit_mode == "px"
    single_w.combo_units.setCurrentIndex(0)
    assert single_w.unit_mode == "um"

    # Probar espesor de corte promediado
    single_w.spin_line_width.setValue(5)
    assert single_w.spin_line_width.value() == 5

    # Probar reglas duales A y B
    single_w.cursor_a.setValue(0.2)
    single_w.cursor_b.setValue(1.8)
    single_w._on_cursors_moved()

    # Probar copia de TSV
    single_w._on_copy_tsv()

    # 4. Probar carga de imagen única y dual
    x_c = np.linspace(-2, 2, 60)
    Xc, Yc = np.meshgrid(x_c, x_c)
    img_custom = 100.0 + 4000.0 * np.exp(-0.5 * (Xc**2 + Yc**2) / 0.4**2)
    win.load_single_image(img_custom, px_size_um=0.06)
    assert win.main_tabs.currentIndex() == 0
    assert win.tab_single.Z.shape == (60, 60)

    # Probar carga dual (compatibilidad con app.py)
    x_d = np.linspace(-2, 2, 50)
    Xd, Yd = np.meshgrid(x_d, x_d)
    Z1 = 100.0 + 3000.0 * np.exp(-0.5 * (Xd**2 + Yd**2) / 0.35**2)
    Z2 = 100.0 + 2500.0 * np.exp(-0.5 * ((Xd - 0.1)**2 + (Yd + 0.1)**2) / 0.4**2)
    win.load_dual_images(Z1, Z2, px_size_um=0.05)
    assert win.main_tabs.currentIndex() == 1
    print("PASS: Métodos load_single_image y load_dual_images verificados.")

    win.close()
    print("PASS: Ciclo de vida completo de PSFAnalyzerWindow superado al 100%!")
    return True


if __name__ == "__main__":
    if test_psf_single_image_mode():
        sys.exit(0)
    else:
        sys.exit(1)
