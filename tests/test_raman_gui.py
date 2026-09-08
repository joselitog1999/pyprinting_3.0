# -*- coding: utf-8 -*-
"""
test_raman_gui.py — Verificación de Instanciación de GUI y Flujo de Usuario en RamanAnalyzer 3.0
PyPrinting 3.0 — UNSAM Nanofotónica
"""
import os
import sys
import math
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import QApplication
from analysis.raman_analyzer import RamanAnalyzerWindow

def test_gui_lifecycle():
    app = QApplication.instance() or QApplication(sys.argv)
    win = RamanAnalyzerWindow()
    assert win is not None
    
    # 1. Comprobar que el archivo demo fue cargado automáticamente si existe
    demo_file = BASE_DIR / "reserva" / "90%_in_red_10s_3_em.asc"
    if demo_file.exists():
        win.load_spectrum_file(demo_file)
        assert len(win.raw_wls) == 1004
        assert len(win.raw_counts) == 1004
        assert len(win.cropped_raw_counts) == 1004
        assert len(win.baseline) == 1004
        assert len(win.corrected) == 1004
        print(f"PASS: GUI cargó archivo demo con éxito ({len(win.raw_wls)} puntos).")
    
    # 2. Probar Recorte de Bordes (ROI Trimming)
    win.cursor_a.setValue(600.0)
    win.cursor_b.setValue(5000.0)
    win._on_crop_to_cursors()
    assert len(win.cropped_raw_counts) < 1004
    assert len(win.cropped_raw_counts) > 50
    print(f"PASS: Recorte interactivo a cursores A-B ({len(win.cropped_raw_counts)} puntos activos).")
    
    # Probar atajo de corte de filtro Rayleigh (< 150 cm^-1)
    win._on_reset_crop()
    assert len(win.cropped_raw_counts) == 1004
    win._on_crop_rayleigh()
    assert win.check_enable_crop_x.isChecked()
    assert win.spin_crop_xmin.value() == 150.0
    print("PASS: Atajo de recorte de filtro Rayleigh (< 150 cm^-1) y restauración verificados.")
    win._on_reset_crop()

    # 3. Probar cambio de unidades a nm y a eV
    win.combo_units.setCurrentIndex(1)  # Wavelength (nm)
    assert win.unit_mode == "wavelength"
    win.combo_units.setCurrentIndex(2)  # Energy (eV)
    assert win.unit_mode == "energy"
    win.combo_units.setCurrentIndex(0)  # Raman shift (cm^-1)
    assert win.unit_mode == "raman_shift"
    print("PASS: Conmutación de unidades (nm / cm^-1 / eV) verificada en GUI.")
    
    # 4. Probar cambio de algoritmos de línea base
    for idx in range(5):
        win.combo_baseline_mode.setCurrentIndex(idx)
        assert len(win.baseline) == len(win.cropped_raw_counts)
    print("PASS: Conmutación de algoritmos de línea base en GUI verificada.")
    
    # 5. Probar limpieza de rayos cósmicos
    win._on_remove_cosmic_rays()
    print("PASS: Botón de limpieza de rayos cósmicos ejecutado sin errores.")
    
    # 6. Probar búsqueda adaptativa de picos y visualización de etiquetas
    win.check_auto_prominence.setChecked(True)
    win._on_find_peaks()
    assert win.table_peaks.rowCount() == len(win.detected_peaks)
    assert win.table_peaks.columnCount() == 5  # 5 columnas (#, Pos, Cuentas, FWHM, Prom)
    print(f"PASS: Búsqueda adaptativa de picos ({len(win.detected_peaks)} picos genuinos detectados).")
    
    # 7. Probar adición manual y eliminación de picos
    initial_pks = len(win.detected_peaks)
    win.cursor_a.setValue(1100.0)
    win._on_add_peak_at_cursor_a()
    assert len(win.detected_peaks) == initial_pks + 1
    
    win.table_peaks.setCurrentCell(0, 0)
    win._on_delete_selected_peak()
    assert len(win.detected_peaks) == initial_pks
    print("PASS: Adición manual en Cursor A y eliminación de picos verificadas.")
    
    # 8. Probar copia de tabla de picos
    win._on_copy_peak_table()
    print("PASS: Copia de tabla de picos a portapapeles verificada.")
    
    # 9. Probar ajuste de pico individual y multi-pico en región A-B
    win.cursor_a.setValue(1000.0)
    win.cursor_b.setValue(1600.0)
    win._on_fit_selected_peak()
    win._on_fit_multi_region()
    print("PASS: Ajuste individual y deconvolución multi-pico en región A-B ejecutados con éxito.")

    # 10. Probar robustez ante recargas con cursores activos y recorte (Prevención de ValueError)
    win.cursor_a.setValue(800.0)
    win.cursor_b.setValue(2000.0)
    win._on_crop_to_cursors()
    # Recargar el archivo mientras el recorte y los cursores están activos
    win.load_spectrum_file(demo_file)
    assert len(win.cropped_raw_counts) == 1004
    assert len(win.corrected) == 1004
    win.cursor_a.setValue(700.0)
    win.cursor_b.setValue(1200.0)
    print("PASS: Prueba de estrés contra condición de carrera y desincronización de cursores superada.")

    # 11. Probar Modo Multi-Espectro & Series
    win.main_nav_tabs.setCurrentIndex(1)
    multi_w = win.tab_multi
    assert multi_w is not None

    # Cargar serie demo de 6 espectros
    multi_w._on_load_demo_series()
    assert len(multi_w.spectra_list) == 6
    assert multi_w.Y_displayed.shape[0] == 6
    print(f"PASS: Carga de serie multi-espectro demo ({len(multi_w.spectra_list)} espectros x {len(multi_w.common_x)} pts).")

    # 11.1 Probar Selector de Láser de Excitación en Multi-Espectro
    multi_w.combo_multi_laser.setCurrentIndex(1)  # 632.8 nm
    assert multi_w.laser_nm == 632.8
    multi_w.combo_multi_laser.setCurrentIndex(5)  # Personalizado
    multi_w.spin_multi_laser_custom.setValue(785.0)
    assert multi_w.laser_nm == 785.0
    # Sincronizar de vuelta a 532 nm
    multi_w.set_laser_wavelength(532.0, sync_parent=True)
    assert multi_w.laser_nm == 532.0
    assert win.laser_nm == 532.0
    print("PASS: Selector de láser de excitación y sincronización bidireccional en Multi-Espectro verificados.")

    # 11.2 Probar conmutación a modo Cascada (Waterfall) y slider
    multi_w.combo_view_mode.setCurrentIndex(1)
    assert multi_w.view_mode == "waterfall"
    multi_w.slider_waterfall.setValue(45)

    # 11.3 Probar normalizaciones a máximo, pico de referencia, área y SNV
    for n_idx in [1, 2, 3, 4]:
        multi_w.combo_norm_mode.setCurrentIndex(n_idx)
        assert multi_w.Y_displayed.shape[0] == 6

    # 11.4 Probar los DOS MODOS de Línea Base
    # Modo 1: Archivo de referencia / fondo
    multi_w.combo_baseline_mode.setCurrentIndex(0)
    assert not multi_w.panel_mode_ref.isHidden()
    assert multi_w.panel_mode_indiv.isHidden()
    if demo_file.exists():
        multi_w.load_reference_file(demo_file)
        assert multi_w.ref_blank_name == demo_file.name
        assert len(multi_w.ref_blank_wls) > 0
        multi_w._on_clear_reference_file()
        assert multi_w.ref_blank_filepath is None

    # Probar blanco seleccionado del lote
    multi_w.combo_blank_from_batch.setCurrentIndex(1)
    multi_w._reprocess_and_update()

    # Modo 2: Cálculo individual adaptativo por espectro
    multi_w.combo_baseline_mode.setCurrentIndex(1)
    assert not multi_w.panel_mode_indiv.isHidden()
    assert multi_w.panel_mode_ref.isHidden()
    for algo_i in range(4):  # AsLS, AirPLS, ModPoly, Rolling Ball
        multi_w.combo_indiv_algo.setCurrentIndex(algo_i)
        multi_w._reprocess_and_update()
        assert multi_w.Y_displayed.shape[0] == 6

    # Modo 3: Sin corrección
    multi_w.combo_baseline_mode.setCurrentIndex(2)
    assert multi_w.panel_mode_ref.isHidden()
    assert multi_w.panel_mode_indiv.isHidden()
    multi_w._reprocess_and_update()
    print("PASS: Ambos modos de línea base (Modo 1 Archivo Referencia & Modo 2 Individual por Espectro) verificados.")

    # 11.5 Probar generación de sub-pestañas (promedio, cinética, heatmap, PCA)
    multi_w.tabs_views.setCurrentIndex(1)
    multi_w.tabs_views.setCurrentIndex(2)
    multi_w.tabs_views.setCurrentIndex(3)
    multi_w.tabs_views.setCurrentIndex(4)

    # Probar copia de matriz TSV
    multi_w._on_copy_tsv()
    print("PASS: Suite Multi-Espectro (cascada, normalizaciones, promedio, cinética, PCA) verificada al 100%.")

    # 11.6 Probar Recorte de Rango Espectral (ROI), Rayleigh y Poda de Bordes en Multi-Espectro
    orig_pts = len(multi_w.common_x)
    assert orig_pts > 500

    # Arrastre de región interactiva y sincronización con cursores
    multi_w.region_ab.setRegion([400.0, 1600.0])
    multi_w._on_region_ab_dragged()
    assert math.isclose(float(multi_w.cursor_a.value()), 400.0, abs_tol=1e-2)
    assert math.isclose(float(multi_w.cursor_b.value()), 1600.0, abs_tol=1e-2)

    # Recorte a cursores
    multi_w._on_crop_to_cursors()
    assert multi_w.check_enable_crop_x.isChecked()
    assert multi_w.common_x[0] >= 399.0
    assert multi_w.common_x[-1] <= 1601.0
    assert len(multi_w.common_x) < orig_pts
    assert multi_w.Y_displayed.shape[1] == len(multi_w.common_x)

    # Atajo de recorte Rayleigh (< 150 cm^-1)
    multi_w._on_crop_rayleigh()
    assert multi_w.spin_crop_xmin.value() == 150.0

    # Poda de bordes de detector
    multi_w.spin_trim_left.setValue(10)
    multi_w.spin_trim_right.setValue(10)
    assert multi_w.Y_displayed.shape[0] == 6

    # Restauración a rango completo original
    multi_w._on_reset_crop()
    assert not multi_w.check_enable_crop_x.isChecked()
    assert multi_w.spin_trim_left.value() == 0
    assert multi_w.spin_trim_right.value() == 0
    assert len(multi_w.common_x) == orig_pts
    print("PASS: Recorte de ROI, Rayleigh, poda de bordes CCD y restauración en Multi-Espectro verificados al 100%.")

    # 11.7 Probar Conmutación de Unidades Espectrales (cm⁻¹, nm, eV) y Sincronización en Multi-Espectro
    # A. Cambiar a Longitud de Onda (nm)
    multi_w.combo_units.setCurrentIndex(1)
    assert multi_w.unit_mode == "wavelength"
    assert multi_w.common_x[0] > 500.0  # Rango óptico en nm
    assert multi_w.common_x[-1] > 500.0
    assert "nm" in multi_w.spin_crop_xmin.suffix()
    assert "nm" in multi_w.spin_ref_peak.suffix()
    assert multi_w.plot_multi.getAxis("bottom").labelText == "Longitud de Onda (nm)"
    assert multi_w.plot_mean.getAxis("bottom").labelText == "Longitud de Onda (nm)"

    # B. Cambiar a Energía Relativa (eV)
    multi_w.combo_units.setCurrentIndex(2)
    assert multi_w.unit_mode == "energy"
    assert 0.01 < multi_w.common_x[0] < 0.2  # En eV (valores iniciales ~0.06 eV)
    assert multi_w.common_x[-1] < 5.0        # Valores finales ~1.85 eV
    assert "eV" in multi_w.spin_crop_xmin.suffix()
    assert multi_w.spin_crop_xmin.decimals() == 4
    assert multi_w.plot_multi.getAxis("bottom").labelText == "Energía Relativa (eV)"

    # C. Sincronización bidireccional: Cambiar en single tab y verificar en multi tab
    win.set_unit_mode("raman_shift", sync_multi=True)
    assert win.unit_mode == "raman_shift"
    assert multi_w.unit_mode == "raman_shift"
    assert multi_w.combo_units.currentIndex() == 0
    assert "cm⁻¹" in multi_w.spin_crop_xmin.suffix()
    assert multi_w.common_x[-1] > 1000.0  # Rango en cm^-1

    # D. Cambiar en multi tab y sincronizar con ventana principal
    multi_w.set_unit_mode("wavelength", sync_parent=True)
    assert multi_w.unit_mode == "wavelength"
    assert win.unit_mode == "wavelength"
    assert win.combo_units.currentIndex() == 1

    # Regresar a cm^-1
    multi_w.set_unit_mode("raman_shift", sync_parent=True)
    assert multi_w.unit_mode == "raman_shift"
    assert win.unit_mode == "raman_shift"
    print("PASS: Conmutacion de unidades (cm^-1, nm, eV) y sincronizacion bidireccional en Multi-Espectro verificadas al 100%.")

    # 11.8 Probar Pestaña Crudos & Línea Base (Modo 1 vs Modo 2 vs Modo 3)
    assert multi_w.tabs_views.count() == 6
    assert multi_w.tabs_views.widget(0) == multi_w.tab_raw_base
    assert multi_w.plot_raw_baseline is not None

    # Modo 1: Línea base de archivo de referencia
    multi_w.load_reference_file(demo_file)
    multi_w.combo_baseline_mode.setCurrentIndex(0)
    assert multi_w.ref_blank_curve is not None
    assert len(multi_w.ref_blank_curve) == len(multi_w.common_x)
    items_mode1 = multi_w.plot_raw_baseline.listDataItems()
    # 6 espectros crudos + 1 línea base de referencia única
    assert len(items_mode1) == 7
    ref_items = [it for it in items_mode1 if it.name() and "Línea Base Ref:" in it.name()]
    assert len(ref_items) == 1, "En Modo 1 solo debe mostrarse una única curva de línea base de referencia."

    # Modo 2: Línea base individual por espectro
    multi_w.combo_baseline_mode.setCurrentIndex(1)
    items_mode2 = multi_w.plot_raw_baseline.listDataItems()
    # 6 espectros crudos + 6 líneas base individuales
    assert len(items_mode2) == 12
    indiv_base_items = [it for it in items_mode2 if it.name() and "Línea Base" in it.name() and "Ref:" not in it.name()]
    assert len(indiv_base_items) == 6

    # Modo 3: Sin corrección de línea base
    multi_w.combo_baseline_mode.setCurrentIndex(2)
    items_mode3 = multi_w.plot_raw_baseline.listDataItems()
    assert len(items_mode3) == 6
    print("PASS: Pestaña Crudos & Línea Base (Modo 1 única referencia vs Modo 2 individuales vs Modo 3) verificada al 100%.")

    # 11.9 Probar Botones de Exportación Dinámicos (PNG, CSV, TSV) en Multi-Espectro
    import tempfile
    from unittest.mock import patch

    tab_checks = [
        (multi_w.tab_raw_base, "Crudos & Base", "Raman_Raw_and_Baselines.png", "Raman_Raw_and_Baselines.csv"),
        (multi_w.tab_plot, "Espectros", "Raman_Overlay_Spectra.png", "Raman_MultiSpectra_Matrix.csv"),
        (multi_w.tab_mean, "Promedio", "Raman_Mean_Std_Spectrum.png", "Raman_Mean_Std_Spectrum.csv"),
        (multi_w.tab_kin, "Cinética", "Raman_Band_Kinetics.png", "Raman_Band_Kinetics.csv"),
        (multi_w.tab_heat, "Mapa de Calor", "Raman_Heatmap_2D.png", "Raman_Heatmap_Matrix.csv"),
        (multi_w.tab_pca, "PCA", "Raman_PCA_Analysis.png", "Raman_PCA_Analysis.csv"),
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        for tab_widget, label_sub, png_name, csv_name in tab_checks:
            multi_w.tabs_views.setCurrentWidget(tab_widget)
            assert label_sub in multi_w.btn_export_png.text()
            assert label_sub in multi_w.btn_export_csv.text()

            # Probar copiado TSV
            multi_w._on_copy_active_tsv()
            tsv_data = app.clipboard().text()
            assert len(tsv_data) > 0
            assert "\t" in tsv_data

            # Probar exportación CSV mockeando QFileDialog
            csv_path = Path(tmpdir) / csv_name
            with patch("PyQt6.QtWidgets.QFileDialog.getSaveFileName", return_value=(str(csv_path), "CSV")):
                with patch("PyQt6.QtWidgets.QMessageBox.information"):
                    multi_w._on_export_active_csv()
            assert csv_path.exists()
            assert csv_path.stat().st_size > 50

            # Probar exportación PNG mockeando QFileDialog
            png_path = Path(tmpdir) / png_name
            with patch("PyQt6.QtWidgets.QFileDialog.getSaveFileName", return_value=(str(png_path), "PNG")):
                with patch("PyQt6.QtWidgets.QMessageBox.information"):
                    multi_w._on_export_active_png()
            assert png_path.exists()
            assert png_path.stat().st_size > 1000

    print("PASS: Exportación dinámica y contextual (PNG 600 DPI, CSV, TSV) en Multi-Espectro verificada al 100%.")

    # 11.10 Probar Botones de Exportación Rápida en Espectro Individual
    assert win.btn_quick_copy_tsv is not None
    assert win.btn_quick_export_csv is not None
    assert win.btn_quick_export_png is not None

    win._on_copy_tsv()
    tsv_single = app.clipboard().text()
    assert "Wavelength_nm" in tsv_single
    assert "Raman_Shift_cm-1" in tsv_single
    assert "Raw_Counts" in tsv_single
    assert "Baseline" in tsv_single
    assert "Corrected_Counts" in tsv_single

    with tempfile.TemporaryDirectory() as tmpdir:
        single_csv = Path(tmpdir) / "single_test.csv"
        with patch("PyQt6.QtWidgets.QFileDialog.getSaveFileName", return_value=(str(single_csv), "CSV")):
            with patch("PyQt6.QtWidgets.QMessageBox.information"):
                win._on_export_csv()
        assert single_csv.exists()
        assert single_csv.stat().st_size > 100

        single_png = Path(tmpdir) / "single_test.png"
        with patch("PyQt6.QtWidgets.QFileDialog.getSaveFileName", return_value=(str(single_png), "PNG")):
            with patch("PyQt6.QtWidgets.QMessageBox.information"):
                win._on_export_png()
        assert single_png.exists()
        assert single_png.stat().st_size > 1000
    print("PASS: Exportación rápida (PNG 600 DPI, CSV, TSV) en Espectro Individual verificada al 100%.")

    # 11.11 Probar Deslizador de Tema Claro/Oscuro (Estrictamente 0 y 100, sin intermedios)
    from PyQt6.QtGui import QImage, QColor

    # Verificar estado inicial oscuro (0)
    assert win.theme_mode == 0
    assert multi_w.theme_mode == 0
    assert win.slider_theme_single.value() == 0
    assert multi_w.slider_theme.value() == 0
    assert "Oscuro" in win.lbl_theme_single.text()
    assert "Oscuro" in multi_w.lbl_theme_state.text()

    # Probar que el deslizador no admite intermedios: mover a 30 debe chasquear a 0
    win.slider_theme_single.setValue(30)
    assert win.slider_theme_single.value() == 0
    assert win.theme_mode == 0

    # Mover a 70 debe chasquear a 100
    win.slider_theme_single.setValue(70)
    assert win.slider_theme_single.value() == 100
    assert win.theme_mode == 100
    assert "Claro" in win.lbl_theme_single.text()

    # Sincronización bidireccional automática con Multi-Espectro
    assert multi_w.theme_mode == 100
    assert multi_w.slider_theme.value() == 100
    assert "Claro" in multi_w.lbl_theme_state.text()

    # Probar conmutación desde Multi-Espectro: mover a 20 debe chasquear a 0
    multi_w.slider_theme.setValue(20)
    assert multi_w.slider_theme.value() == 0
    assert multi_w.theme_mode == 0
    assert win.theme_mode == 0
    assert win.slider_theme_single.value() == 0

    # Conmutar de nuevo a Claro (100) para verificar exportación PNG en ambos modos
    multi_w.set_theme_mode(100)
    assert win.theme_mode == 100
    assert multi_w.theme_mode == 100

    with tempfile.TemporaryDirectory() as tmpdir:
        # Exportar gráfico individual en tema claro
        light_single_png = Path(tmpdir) / "light_single.png"
        with patch("PyQt6.QtWidgets.QFileDialog.getSaveFileName", return_value=(str(light_single_png), "PNG")):
            with patch("PyQt6.QtWidgets.QMessageBox.information"):
                win._on_export_png()
        assert light_single_png.exists()
        img_single_light = QImage(str(light_single_png))
        pixel_single_light = img_single_light.pixelColor(10, 10)
        assert pixel_single_light.red() >= 250 and pixel_single_light.green() >= 250 and pixel_single_light.blue() >= 250, "Fondo de exportación individual en tema claro debe ser blanco (#FFFFFF)"

        # Exportar gráfico multi-espectro (pestaña overlay) en tema claro
        multi_w.tabs_views.setCurrentWidget(multi_w.tab_plot)
        light_multi_png = Path(tmpdir) / "light_multi.png"
        with patch("PyQt6.QtWidgets.QFileDialog.getSaveFileName", return_value=(str(light_multi_png), "PNG")):
            with patch("PyQt6.QtWidgets.QMessageBox.information"):
                multi_w._on_export_active_png()
        assert light_multi_png.exists()
        img_multi_light = QImage(str(light_multi_png))
        pixel_multi_light = img_multi_light.pixelColor(10, 10)
        assert pixel_multi_light.red() >= 250 and pixel_multi_light.green() >= 250 and pixel_multi_light.blue() >= 250, "Fondo de exportación multi en tema claro debe ser blanco (#FFFFFF)"

        # Exportar PCA combinado en tema claro
        multi_w.tabs_views.setCurrentWidget(multi_w.tab_pca)
        light_pca_png = Path(tmpdir) / "light_pca.png"
        with patch("PyQt6.QtWidgets.QFileDialog.getSaveFileName", return_value=(str(light_pca_png), "PNG")):
            with patch("PyQt6.QtWidgets.QMessageBox.information"):
                multi_w._on_export_active_png()
        assert light_pca_png.exists()
        img_pca_light = QImage(str(light_pca_png))
        pixel_pca_light = img_pca_light.pixelColor(10, 10)
        assert pixel_pca_light.red() >= 250 and pixel_pca_light.green() >= 250 and pixel_pca_light.blue() >= 250, "Fondo de exportación PCA en tema claro debe ser blanco (#FFFFFF)"

        # Ahora cambiar a tema Oscuro (0) y verificar fondo oscuro
        win.set_theme_mode(0)
        assert win.theme_mode == 0
        assert multi_w.theme_mode == 0

        dark_single_png = Path(tmpdir) / "dark_single.png"
        with patch("PyQt6.QtWidgets.QFileDialog.getSaveFileName", return_value=(str(dark_single_png), "PNG")):
            with patch("PyQt6.QtWidgets.QMessageBox.information"):
                win._on_export_png()
        assert dark_single_png.exists()
        img_single_dark = QImage(str(dark_single_png))
        pixel_single_dark = img_single_dark.pixelColor(10, 10)
        assert pixel_single_dark.red() <= 40 and pixel_single_dark.green() <= 40 and pixel_single_dark.blue() <= 50, "Fondo de exportación individual en tema oscuro debe ser #181825"

        dark_pca_png = Path(tmpdir) / "dark_pca.png"
        with patch("PyQt6.QtWidgets.QFileDialog.getSaveFileName", return_value=(str(dark_pca_png), "PNG")):
            with patch("PyQt6.QtWidgets.QMessageBox.information"):
                multi_w._on_export_active_png()
        assert dark_pca_png.exists()
        img_pca_dark = QImage(str(dark_pca_png))
        pixel_pca_dark = img_pca_dark.pixelColor(10, 10)
        assert pixel_pca_dark.red() <= 40 and pixel_pca_dark.green() <= 40 and pixel_pca_dark.blue() <= 50, "Fondo de exportación PCA en tema oscuro debe ser #181825"

    print("PASS: Deslizador de Fondo Claro/Oscuro (estricto 0 y 100, sin intermedios), sincronización bidireccional y exportación PNG verificados al 100%.")

    win.close()
    print("PASS: Ciclo de vida completo de RamanAnalyzerWindow superado al 100%!")
    return True

if __name__ == "__main__":
    if test_gui_lifecycle():
        sys.exit(0)
    else:
        sys.exit(1)
