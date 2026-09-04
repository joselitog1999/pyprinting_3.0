# -*- coding: utf-8 -*-
"""
run_all_diagnostics.py — Suite Unificada de Diagnóstico y Pruebas Automatizadas
PyPrinting 3.0 — UNSAM Nanofotónica
"""
from __future__ import annotations
import sys
import os
import time
import tempfile
from pathlib import Path

# Configurar encoding UTF-8 seguro para Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import numpy as np

# Asegurar que el directorio raíz de printing3 esté en sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Forzar modo simulación seguro para el runner de pruebas
os.environ["PYPRINTING_SAFE"] = "1"

def run_tests():
    print("=" * 70)
    print("SUITE DE DIAGNOSTICO INTEGRAL Y VERIFICACION — PyPrinting 3.0")
    print(f"Directorio Base: {BASE_DIR}")
    print(f"Interprete Python: {sys.executable}")
    print("=" * 70)

    passed_count = 0
    total_count = 0

    def assert_test(name: str, condition: bool, details: str = ""):
        nonlocal passed_count, total_count
        total_count += 1
        if condition:
            passed_count += 1
            print(f"  [PASS] {name} {details}")
        else:
            print(f"  [FAIL] {name} {details}")

    # ── 1. Entorno y Dependencias ─────────────────────────────────────────────
    print("\n1. Dependencias y Bibliotecas Principales")
    for pkg in ['PyQt6', 'pyqtgraph', 'numpy', 'scipy', 'nidaqmx', 'pipython', 'tifffile', 'cv2', 'trackpy']:
        try:
            mod = __import__(pkg)
            ver = getattr(mod, '__version__', 'instalado')
            assert_test(f"Biblioteca {pkg}", True, f"({ver})")
        except Exception as e:
            assert_test(f"Biblioteca {pkg}", False, f"(Error: {e})")

    # ── 2. Configuración Global y Canales I/O ─────────────────────────────────
    print("\n2. Configuracion Global y Mapeo I/O")
    import config
    assert_test("SAFE_MODE configurado", isinstance(config.SAFE_MODE, bool), f"(SAFE_MODE={config.SAFE_MODE})")
    assert_test("Lineas de Shutter (4 canales)", len(config.SHUTTERS) == 4, f"{config.SHUTTERS}")
    assert_test("Canales de Shutter", config.SHTER_CHANNELS if hasattr(config, 'SHTER_CHANNELS') else config.SHUTTER_CHANNELS == [11, 8, 9, 10])
    assert_test("Linea 808 nm presente", "808 nm (IR)" in config.SHUTTERS)
    assert_test("Canal Divisor BS configurado", config.PD_CHANNELS.get("BS") == 6)

    # ── 3. Controladores de Hardware & Mocks ──────────────────────────────────
    print("\n3. Controladores de Hardware y Tolerancia a Fallos")
    from core.nanopositioning import pi
    pos = pi.qPOS()
    assert_test("Platina PI Resiliente", isinstance(pos, dict) and '1' in pos, f"(Pos: {pos})")

    from core.nidaq import open_shutter, close_shutter
    for sh in config.SHUTTERS:
        try:
            open_shutter(sh)
            close_shutter(sh)
            assert_test(f"Obturador [{sh}]", True)
        except Exception as e:
            assert_test(f"Obturador [{sh}]", False, f"({e})")

    from pyspectrum.drivers.shamrock_driver import get_shamrock, DEVICE
    sh_driver = get_shamrock()
    ret, sn = sh_driver.ShamrockGetSerialNumber(DEVICE)
    assert_test("Espectrografo Shamrock", sh_driver is not None)

    from pyspectrum.drivers.andor_ccd_driver import get_andor_ccd
    cam_ccd = get_andor_ccd()
    ret, temp = cam_ccd.get_temperature()
    frame = cam_ccd.get_most_recent_image()
    assert_test("Camara Andor CCD", frame.shape == (1002, 1002), f"(Temp: {temp:.1f} °C, Frame: {frame.shape})")

    # ── 4. Calibración y Procesamiento Espectral ──────────────────────────────
    print("\n4. Calibracion y Cosido Espectral Step & Glue")
    from pyspectrum.calibration.halogen_lamp import HalogenLampCalibration, glue_steps
    lamp = HalogenLampCalibration()
    assert_test("Perfil Lampara Halogena", lamp.is_loaded)

    wl1 = np.linspace(450, 600, 100)
    sp1 = np.exp(-((wl1 - 530) / 30)**2)
    wl2 = np.linspace(580, 750, 100)
    sp2 = np.exp(-((wl2 - 530) / 30)**2)
    w_concat = np.concatenate([wl1, wl2])
    s_concat = np.concatenate([sp1, sp2])
    w_glue, s_glue = glue_steps(w_concat, s_concat, number_pixel=100)
    assert_test("Algoritmo Step & Glue Continuo", len(w_glue) > 0 and len(s_glue) > 0)

    from pyspectrum.calibration.fit_polynomial import fit_signal_polynomial
    w_fit, s_fit, lmax = fit_signal_polynomial(w_glue, s_glue, ends_notch=460, final_wave=740)
    assert_test("Ajuste Polinomial SPR", 500 <= lmax <= 560, f"(λ_max={lmax:.2f} nm)")

    # ── 5. Formatos de Archivos y Exportadores ────────────────────────────────
    print("\n5. Intercambio de Archivos y Formatos")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        import tifffile
        test_img = (np.random.rand(80, 80) * 65535).astype(np.uint16)
        tif_file = str(tmp_path / "test.tiff")
        tifffile.imwrite(tif_file, test_img)
        assert_test("Exportador TIFF 16-bit", tifffile.imread(tif_file).shape == (80, 80))

        npy_file = str(tmp_path / "test.npy")
        np.save(npy_file, test_img)
        assert_test("Formato NumPy .npy", np.load(npy_file).shape == (80, 80))

        csv_file = str(tmp_path / "test.csv")
        np.savetxt(csv_file, test_img, delimiter=",", fmt="%d")
        assert_test("Formato CSV Tabular", np.loadtxt(csv_file, delimiter=",").shape == (80, 80))

    # ── 6. Interfaz Gráfica y Aplicaciones Principales ────────────────────────
    print("\n6. Instanciacion de Ventanas y Modulos Graficos PyQt6")
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)

    from main import MainWindowLauncher
    main_win = MainWindowLauncher()
    assert_test("Lanzador Principal (main.py)", main_win is not None)

    from pyspectrum import PySpectrumWindow
    spec_win = PySpectrumWindow()
    assert_test("PySpectrum 3.0 (pyspectrum.py)", spec_win is not None)

    from analysis.psf_analyzer import PSFAnalyzerWindow
    psf_win = PSFAnalyzerWindow()
    assert_test("PSF Analyzer (psf_analyzer.py)", psf_win is not None)

    from analysis.image_analyzer import ImageAnalyzerWidget
    img_win = ImageAnalyzerWidget()
    assert_test("Image Analyzer (image_analyzer.py)", img_win is not None)

    from modules.hardware_dashboard import HardwareDashboardWindow
    hw_win = HardwareDashboardWindow()
    assert_test("Tablero de Hardware (hardware_dashboard.py)", hw_win is not None)

    from core.lattice_generator import CrystalGridComposer, LatticeLayer
    composer = CrystalGridComposer()
    composer.layers = [LatticeLayer(name="Test", lattice_type="hexagonal", a=3.0)]
    composer.bounding_shape = "hexagon"
    composer.bounding_params = {"ap": 5.0}
    res_test = composer.generate()
    assert_test("Motor Cristalográfico (core/lattice_generator.py)", res_test["stats"]["total"] > 0)

    from grid_generator import GridGeneratorWindow
    grid_win = GridGeneratorWindow()
    assert_test("Diseñador de Redes 2D (grid_generator.py)", grid_win is not None)

    import app as app_module
    app_fe = app_module.Frontend()
    app_be = app_module.Backend()
    app_fe.make_connection(app_be)
    assert_test("PyPrinting Principal (app.py)", app_fe is not None and app_be is not None)

    import contrapropagante as cp_module
    cp_fe = cp_module.ContrapropaganteMainWindow()
    cp_be = cp_module.Backend()
    cp_fe.make_connection(cp_be)
    assert_test("Contrapropagante (contrapropagante.py)", cp_fe is not None and cp_be is not None)

    # 7. Nuevas Funcionalidades: Confocal Tilt y Autocompletitud Healing Pass
    print("\n7. Nuevas Funcionalidades (Confocal Tilt & Healing Pass)")
    from modules.confocal import Frontend as ConfocalFE, Backend as ConfocalBE
    from modules.focus import Backend as FocusBE
    c_fe = ConfocalFE()
    c_be = ConfocalBE()
    f_be = FocusBE()
    c_be.focus_backend = f_be
    c_be.make_connection(c_fe)
    c_fe.make_connection(c_be)
    f_be.locked_focus = True
    f_be.z_profile_lock_filter = np.ones(50)
    tilt_ok = c_be._measure_4_corners_tilt(50.0, 50.0, 10.0, 10.0)
    z_eval = c_be._evaluate_tilt_z(45.0, 55.0)
    assert_test("Confocal Inclinación Dinámica Z (4 esquinas)", tilt_ok and z_eval > 0.0)

    from modules.measurements import InteractiveGridWidget, Backend as MeasBE
    igw = InteractiveGridWidget()
    igw.set_grid(np.array([[0.0, 2.0], [0.0, 2.0], [0.0, 0.0]]))
    igw.set_node_status(1, "retrying")
    m_be = MeasBE(mode="printing")
    m_be.grid_create([2, 1, 2.0, 2.0, 2.0, 2.0, False])
    m_be.auto_complete_enabled = True
    m_be.node_results[0] = "success"
    m_be.node_results[1] = "timeout"
    m_be.particulas = 2
    m_be.i_global = 1
    m_be._grid_detect()
    healing_active = m_be.is_healing_pass and (m_be.healing_failed_queue == [1])
    assert_test("Autocompletitud de Redes (Healing Pass)", igw.node_states[1] == "retrying" and healing_active)

    from core.lattice_generator import CrystalGridComposer as Comp, LatticeLayer as Lay
    test_comp = Comp()
    test_comp.layers = [Lay(name="Square", lattice_type="square", a=3.0)]
    test_comp.bounding_shape = "cells"
    test_comp.bounding_params = {"nx": 2, "ny": 2}
    test_comp.anchor_config.enabled = True
    test_comp.anchor_config.mode = "printing_reference"
    test_comp.anchor_config.start_x_um = 2.0
    test_comp.anchor_config.start_y_um = 2.0
    res_start = test_comp.generate()
    p0_ok = res_start["anchor"]["x"] == 0.0 and res_start["anchor"]["y"] == 0.0
    first_node_ok = res_start["nodes"][0]["x"] == 2.0 and res_start["nodes"][0]["y"] == 2.0
    assert_test("Referencia P0 (0,0) y Primera Partícula (startX, startY)", p0_ok and first_node_ok)

    # 8. Contenedor Científico HDF5 (Batch & Unpack)
    from core.hdf5_container import BatchHDF5Container
    tmp_h5_dir = tempfile.mkdtemp()
    tmp_h5_file = os.path.join(tmp_h5_dir, "diag_batch.h5")
    diag_h5 = BatchHDF5Container(tmp_h5_file, metadata={"test": "ok"}, recipe={"grid_name": "DiagGrid"})
    diag_h5.add_node_data(0, trace=np.zeros((10, 3)), scan=np.zeros((8, 8)), status="SUCCESS")
    diag_h5.set_telemetry(drift_xy=[{"node": 0, "time": 0.0, "dx_nm": 0.0, "dy_nm": 0.0, "mag_nm": 0.0, "v_xy": 0.0}])
    diag_h5.close()
    unpacked_diag = BatchHDF5Container.unpack_to_legacy(tmp_h5_file)
    h5_valid = os.path.exists(tmp_h5_file) and os.path.exists(os.path.join(unpacked_diag, "NP_000.txt"))
    assert_test("Contenedor Científico HDF5 (.h5 & Desempaquetado 1-Click)", h5_valid)

    # ── 9. Suite Raman Multi-Espectro & PSF Analyzer Modo Foto Única ─────────
    print("\n9. Espectroscopía Multi-Espectro & Caracterización de PSF")
    from core.raman_engine import (
        interpolate_spectra_to_common_grid, normalize_spectrum_matrix,
        compute_mean_std_spectrum, extract_band_kinetics, compute_spectral_pca
    )
    # Test matemático multi-espectro
    x_test = np.linspace(500, 1800, 100)
    Y_test = np.array([
        100.0 + 2000.0 * np.exp(-0.5 * ((x_test - 1078.0) / 15.0)**2),
        100.0 + 3500.0 * np.exp(-0.5 * ((x_test - 1078.0) / 15.0)**2)
    ])
    Y_norm_max = normalize_spectrum_matrix(x_test, Y_test, mode="max")
    assert_test("Normalización Multi-Espectro (Max = 1.0)", np.isclose(np.max(Y_norm_max), 1.0))

    mean_s, std_s, rsd_s = compute_mean_std_spectrum(Y_test)
    assert_test("Espectro Promedio ± Desvío (μ ± σ & RSD%)", len(mean_s) == 100 and len(rsd_s) == 100)

    pca_res = compute_spectral_pca(Y_test, n_components=2)
    assert_test("PCA Quimiométrico Raman (SVD)", pca_res["scores"].shape == (2, 2))

    # Test PSF Analyzer Single Image
    from analysis.psf_analyzer import extract_arbitrary_line_profile, fit_1d_gaussian
    Z_psf = np.zeros((60, 60))
    x_grid = np.linspace(-1.5, 1.5, 60)
    Xg, Yg = np.meshgrid(x_grid, x_grid)
    Z_psf = 50.0 + 5000.0 * np.exp(-0.5 * (Xg**2 + Yg**2) / 0.35**2)
    s_cut, p_cut = extract_arbitrary_line_profile(Z_psf, (0, 30), (59, 30), pixel_size_um=0.05, line_width_px=3)
    fit_gauss = fit_1d_gaussian(s_cut, p_cut)
    assert_test("Corte de Línea Arbitraria PSF con Espesor", len(s_cut) == 60)
    assert_test("Ajuste Gaussiano 1D PSF & FWHM Analítico", fit_gauss is not None and fit_gauss["r_squared"] > 0.99)

    # ── 10. Telemetría de Hardware & Aislamiento de Instrumentos ──────────────
    print("\n10. Telemetría de Hardware & Aislamiento de Instrumentos")
    from core.hardware_manager import HardwareManager
    from pyspectrum.drivers.shamrock_driver import _MockShamrock, get_shamrock
    from pyspectrum.drivers.andor_ccd_driver import _MockAndorCCD, get_andor_ccd
    from core.nanopositioning import Frontend as NanoFE, Backend as NanoBE

    mock_sh = _MockShamrock()
    mock_ccd = _MockAndorCCD()
    assert_test("Detección de Mock Espectrógrafo y Cámara (is_mock=True)", mock_sh.is_mock and mock_ccd.is_mock)

    hw_diag = HardwareManager()
    hw_diag.connect_device("Espectrógrafo Andor Shamrock")
    hw_diag.connect_device("Cámara Andor CCD (Espectros)")
    no_false_connected = (hw_diag.device_states.get("Espectrógrafo Andor Shamrock") != "connected") and \
                         (hw_diag.device_states.get("Cámara Andor CCD (Espectros)") != "connected")
    assert_test("Protección Contra Falso Positivo Conectado en Espectroscopía", no_false_connected)

    nano_fe = NanoFE()
    nano_be = NanoBE()
    nano_fe.make_connection(nano_be)
    nano_ok = nano_fe.conn_status_label.text() != "⚪ Verificando..." and hasattr(nano_be, "reconnect")
    nano_fe.close()
    assert_test("Telemetría y Reconexión en Nanopositioning Dock", nano_ok)


    # ── Resumen Final ─────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print(f"RESULTADOS FINALES: {passed_count} / {total_count} pruebas superadas ({passed_count/total_count*100:.1f}%)")
    if passed_count == total_count:
        print("TODOS LOS DIAGNOSTICOS Y PRUEBAS PASARON AL 100% CON EXITO!")
    else:
        print("ALGUNAS PRUEBAS FALLARON. REVISAR DETALLES ARRIBA.")
    print("=" * 70)
    return passed_count == total_count

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
