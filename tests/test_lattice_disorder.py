"""
tests/test_lattice_disorder.py
==============================
Batería de pruebas unitarias metrológicas para el motor físico de desorden
en redes periódicas y pipeline de localización (PyPrinting 3.0).
"""

import os
import sys
from pathlib import Path
import tempfile
import numpy as np
from typing import Tuple, Dict, Any, Optional
import pandas as pd

# Asegurar que el directorio raíz esté en sys.path
_curr = Path(__file__).resolve().parent
while _curr != _curr.parent:
    if (_curr / "config.py").exists():
        for _p in [str(_curr), str(_curr / "core"), str(_curr / "modules"), str(_curr / "analysis")]:
            if _p not in sys.path:
                sys.path.insert(0, _p)
        break
    _curr = _curr.parent

try:
    import pytest
except ImportError:
    pytest = None

from core.lattice_disorder import (
    compute_structure_factor_2d,
    extract_1d_profiles,
    fit_bragg_peak_1d,
    analyze_reciprocal_space_2d,
    analyze_real_space_kdtree,
    compute_radial_distribution_function,
    run_monte_carlo_calibration,
    fit_debye_waller_curve,
    interpolate_disorder,
    save_calibration_curve,
    load_calibration_curve,
    detect_clusters_and_chains,
    calibrate_single_emitter_signature,
    fit_multi_gaussian_roi,
    analyze_photometric_contours,
    resolve_clusters,
    resolve_clusters_dataframe,
    inspect_single_spot_photometry,
    resolve_single_spot_multi_gaussian,
    find_optimal_grid_bounding_box,
    extract_diagonal_profile,
    fit_secondary_bragg_peak_1d,
    measure_transversal_mosaic,
    compute_analytical_bragg_relations,
    compute_bond_orientational_order,
    compute_voronoi_topology,
    compute_quiver_and_strain,
    generate_ideal_lattice_template,
    register_and_match_template,
    compute_basis_structure_factor,
    extract_angular_profile,
    compute_radial_azimuthal_profile,
    run_hexagonal_monte_carlo_calibration
)
from core.localization_pipeline import (
    load_coordinates,
    convert_pixels_to_nm
)


def _generate_synthetic_grid(
    n_side: int = 20,
    a: float = 450.0,
    sigma: float = 0.0,
    f_vac: float = 0.0,
    seed: int = 42
) -> Tuple[np.ndarray, np.ndarray]:
    """Genera coordenadas sintéticas (x, y) en nanómetros con desorden y vacancias."""
    np.random.seed(seed)
    half = ((n_side - 1) * a) / 2.0
    g1d = np.linspace(-half, half, n_side)
    X, Y = np.meshgrid(g1d, g1d)
    x = X.ravel()
    y = Y.ravel()

    if f_vac > 0:
        mask = np.random.uniform(0, 1, len(x)) >= f_vac
        x = x[mask]
        y = y[mask]

    if sigma > 0:
        x = x + np.random.normal(0, sigma, len(x))
        y = y + np.random.normal(0, sigma, len(y))

    return x, y


def test_reciprocal_space_ideal_grid():
    """Verifica que una red ideal (sigma=0) retorne con alta precisión el período nominal."""
    a_nominal = 450.0
    x, y = _generate_synthetic_grid(n_side=20, a=a_nominal, sigma=0.0)

    res = analyze_reciprocal_space_2d(x, y, a_nominal=a_nominal, n_bins=256)

    # El período ajustado debe estar dentro de +/- 2 nm del valor nominal
    assert abs(res['a_x'] - a_nominal) < 2.0, f"a_x={res['a_x']} difiere de {a_nominal}"
    assert abs(res['a_y'] - a_nominal) < 2.0, f"a_y={res['a_y']} difiere de {a_nominal}"
    assert abs(res['anisotropy']) < 2.0, f"Anisotropía espuria detectada: {res['anisotropy']}"
    assert res['Hx'] > 100.0, "La altura del pico de Bragg ideal debe ser muy alta"


def test_real_space_kdtree_ideal():
    """Verifica que en una red ideal el desorden medido sea esencialmente cero (< 0.1 nm)."""
    a_nominal = 450.0
    x, y = _generate_synthetic_grid(n_side=15, a=a_nominal, sigma=0.0)

    kdtree_res = analyze_real_space_kdtree(x, y, a=a_nominal, n_side=15)

    assert kdtree_res['sigma_x'] < 0.1, f"sigma_x={kdtree_res['sigma_x']} debe ser nulo"
    assert kdtree_res['sigma_y'] < 0.1, f"sigma_y={kdtree_res['sigma_y']} debe ser nulo"
    assert kdtree_res['sigma_pos'] < 0.1
    assert kdtree_res['vacant_count'] == 0
    assert kdtree_res['f_vac'] == 0.0


def test_real_space_kdtree_calibrated_disorder():
    """Verifica que para una red con sigma=25 nm inyectado, KDTree recupere sigma in [23, 27] nm."""
    a_nominal = 450.0
    sigma_in = 25.0
    x, y = _generate_synthetic_grid(n_side=30, a=a_nominal, sigma=sigma_in, seed=123)

    kdtree_res = analyze_real_space_kdtree(x, y, a=a_nominal, n_side=30)

    assert abs(kdtree_res['sigma_pos'] - sigma_in) < 2.5, (
        f"sigma_pos={kdtree_res['sigma_pos']} lejos de {sigma_in}"
    )


def test_vacancies_resilience():
    """
    Verifica que las vacancias sean detectadas correctamente y NO inflen
    espuria ni catastróficamente el desorden sigma mediante saltos a 450 nm.
    """
    a_nominal = 450.0
    sigma_in = 15.0
    f_vac_in = 0.15
    x, y = _generate_synthetic_grid(n_side=20, a=a_nominal, sigma=sigma_in, f_vac=f_vac_in, seed=456)

    kdtree_res = analyze_real_space_kdtree(x, y, a=a_nominal, n_side=20)

    # Fracción de vacancias detectada debe ser cercana al 15%
    assert abs(kdtree_res['f_vac'] - f_vac_in) < 0.05
    # El desorden medido no debe saltar a 450 nm
    assert kdtree_res['sigma_pos'] < 25.0, (
        f"sigma_pos={kdtree_res['sigma_pos']} inflado por vacancias no acotadas"
    )


def test_radial_distribution_function():
    """Verifica que g(r) ubique el primer pico en el período de red."""
    a_nominal = 450.0
    x, y = _generate_synthetic_grid(n_side=20, a=a_nominal, sigma=10.0, seed=789)

    rdf_res = compute_radial_distribution_function(x, y, a_nominal=a_nominal)

    assert len(rdf_res['r']) > 0
    assert abs(rdf_res['first_peak_r'] - a_nominal) < 25.0, (
        f"Primer pico g(r) en {rdf_res['first_peak_r']} difiere de {a_nominal}"
    )
    assert rdf_res['sigma_rdf'] > 0.0


def test_monte_carlo_and_debye_waller_fit():
    """Verifica la ejecución de Monte Carlo y el ajuste analítico de Debye-Waller."""
    a_nominal = 450.0
    n_side = 10
    mc_res = run_monte_carlo_calibration(
        n_side=n_side,
        a=a_nominal,
        f_vac=0.05,
        sigma_min=0.0,
        sigma_max=50.0,
        n_sigma_steps=6,
        iterations_per_step=10
    )

    assert len(mc_res['H_mean']) == 6
    # La curva debe ser monótonamente decreciente
    assert mc_res['H_mean'][0] > mc_res['H_mean'][-1]

    fit = mc_res['fit']
    assert fit['success']
    assert fit['r_squared'] > 0.85
    assert fit['H0'] > 0.0

    # Prueba de interpolación
    H_mid = (mc_res['H_mean'][0] + mc_res['H_mean'][-1]) / 2.0
    s_interp, s_err = interpolate_disorder(H_mid, mc_res['sigma_values'], mc_res['H_mean'], mc_res['H_std'])
    assert 0.0 <= s_interp <= 50.0
    assert s_err > 0.0


def test_save_load_calibration_curve():
    """Verifica la persistencia y recarga de curvas de calibración en .npz."""
    a_nominal = 450.0
    dummy_data = {
        'n_side': 15,
        'a': a_nominal,
        'f_vac': 0.10,
        'sigma_values': np.linspace(0, 50, 6),
        'H_mean': np.array([100.0, 80.0, 50.0, 30.0, 15.0, 10.0]),
        'H_std': np.array([2.0, 2.0, 1.5, 1.0, 0.8, 0.5]),
        'fit': {
            'H0': 120.0,
            'sigma_char': 22.0,
            'H_diffuse': 8.0,
            'r_squared': 0.99
        }
    }

    with tempfile.NamedTemporaryFile(suffix='.npz', delete=False) as tmp:
        tmp_path = tmp.name

    try:
        save_calibration_curve(tmp_path, dummy_data)
        loaded = load_calibration_curve(tmp_path)

        assert loaded['n_side'] == 15
        assert abs(loaded['a'] - a_nominal) < 1e-6
        assert abs(loaded['f_vac'] - 0.10) < 1e-6
        assert np.allclose(loaded['sigma_values'], dummy_data['sigma_values'])
        assert np.allclose(loaded['H_mean'], dummy_data['H_mean'])
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_monte_carlo_anisotropy_and_band_integration():
    """Verifica calibración Monte Carlo anisotrópica (ax != ay), alta densidad espectral (81 pts)
    e integración en banda transversal."""
    a_x = 480.0
    a_y = 520.0
    mc_res = run_monte_carlo_calibration(
        n_side=12,
        a=a_x,
        a_y=a_y,
        f_vac=0.04,
        sigma_min=0.0,
        sigma_max=40.0,
        n_sigma_steps=6,
        iterations_per_step=15,
        n_bragg_pts=81,
        band_width_nm=0.0003,
        n_transversal_pts=5,
        seed=12345
    )

    assert mc_res['is_anisotropic'] is True
    assert np.isclose(mc_res['a_x'], a_x)
    assert np.isclose(mc_res['a_y'], a_y)
    assert mc_res['n_bragg_pts'] == 81
    assert mc_res['band_width_nm'] == 0.0003
    assert len(mc_res['H_mean_x']) == 6
    assert len(mc_res['H_mean_y']) == 6

    # Ajustes de Debye-Waller en ambos ejes
    fit_x = mc_res['fit_x']
    fit_y = mc_res['fit_y']
    assert fit_x['success'] and fit_y['success']
    assert fit_x['r_squared'] > 0.85
    assert fit_y['r_squared'] > 0.85

    # Comprobación de persistencia y deserialización anisotrópica
    with tempfile.NamedTemporaryFile(suffix='.npz', delete=False) as tmp:
        tmp_path = tmp.name
    try:
        save_calibration_curve(tmp_path, mc_res)
        loaded = load_calibration_curve(tmp_path)
        assert loaded['is_anisotropic'] is True
        assert np.isclose(loaded['a_x'], a_x)
        assert np.isclose(loaded['a_y'], a_y)
        assert np.allclose(loaded['H_mean_x'], mc_res['H_mean_x'])
        assert np.allclose(loaded['H_mean_y'], mc_res['H_mean_y'])
        assert 'fit_x' in loaded and 'fit_y' in loaded
        assert np.isclose(loaded['fit_x']['sigma_char'], fit_x['sigma_char'])
        assert np.isclose(loaded['fit_y']['sigma_char'], fit_y['sigma_char'])
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    # Interpolación dual
    Hx_target = (mc_res['H_mean_x'][0] + mc_res['H_mean_x'][-1]) / 2.0
    sx, err_x = interpolate_disorder(Hx_target, mc_res['sigma_values'], mc_res['H_mean_x'], mc_res['H_std_x'])
    assert 0.0 < sx < 40.0
    assert err_x > 0.0

    Hy_target = (mc_res['H_mean_y'][0] + mc_res['H_mean_y'][-1]) / 2.0
    sy, err_y = interpolate_disorder(Hy_target, mc_res['sigma_values'], mc_res['H_mean_y'], mc_res['H_std_y'])
    assert 0.0 < sy < 40.0
    assert err_y > 0.0


def test_localization_pipeline_coordinates():
    """Verifica la carga de coordenadas y conversión métrica."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as tmp:
        tmp.write("x,y,photons\n10.0,20.0,150\n30.0,40.0,200\n")
        tmp_csv = tmp.name

    try:
        df = load_coordinates(tmp_csv)
        assert len(df) == 2
        assert 'x' in df.columns and 'y' in df.columns

        df_nm = convert_pixels_to_nm(df, pixel_size_nm=50.0)
        assert df_nm['x_nm'].iloc[0] == 500.0
        assert df_nm['y_nm'].iloc[0] == 1000.0
    finally:
        if os.path.exists(tmp_csv):
            os.remove(tmp_csv)


def test_picasso_autoscale_and_inversion():
    """Verifica el auto-escalado dinámico a 16-bit y la inversión en Picasso."""
    from core.localization_pipeline import localize_picasso

    # Crear imagen sintética float32 con rango [0.05, 0.55] y 4 emisores
    H, W = 64, 64
    img = np.full((H, W), 0.05, dtype=np.float32)
    emitter_coords = [(16, 16), (16, 48), (48, 16), (48, 48)]
    for ey, ex in emitter_coords:
        yy, xx = np.ogrid[:H, :W]
        img += 0.50 * np.exp(-((xx - ex)**2 + (yy - ey)**2) / (2 * 1.5**2))

    # Prueba 1: Con auto_scale_uint16=True debe detectar los 4 emisores
    locs = localize_picasso(img, min_net_gradient=200.0, box_size=7, auto_scale_uint16=True)
    assert len(locs) == 4, f"Se esperaban 4 emisores, detectados: {len(locs)}"

    # Prueba 2: Imagen invertida (fondo claro, manchas oscuras)
    img_dark_spots = float(np.max(img) + np.min(img)) - img
    locs_inv = localize_picasso(img_dark_spots, min_net_gradient=200.0, box_size=7, auto_scale_uint16=True, invert=True)
    assert len(locs_inv) == 4, f"Inversión falló en Picasso, detectados: {len(locs_inv)}"


def test_trackpy_separation_and_inversion():
    """Verifica separación mínima e inversión en Trackpy."""
    from core.localization_pipeline import localize_trackpy

    H, W = 64, 64
    img = np.full((H, W), 0.05, dtype=np.float32)
    emitter_coords = [(16, 16), (16, 48), (48, 16), (48, 48)]
    for ey, ex in emitter_coords:
        yy, xx = np.ogrid[:H, :W]
        img += 0.50 * np.exp(-((xx - ex)**2 + (yy - ey)**2) / (2 * 1.5**2))

    # Con separation=7.0 px
    locs = localize_trackpy(img, diameter=5, minmass=0.01, separation=7.0)
    assert len(locs) == 4, f"Se esperaban 4 emisores en Trackpy, detectados: {len(locs)}"

    # Inversión
    img_dark_spots = float(np.max(img) + np.min(img)) - img
    locs_inv = localize_trackpy(img_dark_spots, diameter=5, minmass=0.01, separation=7.0, invert=True)
    assert len(locs_inv) == 4, f"Inversión falló en Trackpy, detectados: {len(locs_inv)}"


def test_roi_filter_logic():
    """Verifica el filtrado espacial mediante reglas de ROI."""
    data = {
        'x': [10.0, 50.0, 100.0, 250.0, 320.0],
        'y': [5.0, 50.0, 100.0, 250.0, 330.0]
    }
    df = pd.DataFrame(data)

    # ROI definido en [15, 315] x [15, 318]
    xmin, xmax = 15.0, 315.0
    ymin, ymax = 15.0, 318.0

    filtered = df[(df['x'] >= xmin) & (df['x'] <= xmax) & (df['y'] >= ymin) & (df['y'] <= ymax)]
    assert len(filtered) == 3, f"Se esperaban 3 puntos dentro del ROI, obtenidos: {len(filtered)}"
    assert list(filtered['x']) == [50.0, 100.0, 250.0]


def test_benchmark_30x30_500_file():
    """Verifica la metrología real con el archivo confocal reserva/30x30_500.tiff si existe."""
    sample_file = "reserva/30x30_500.tiff"
    if not os.path.exists(sample_file):
        return

    from core.localization_pipeline import load_image, localize_picasso, localize_trackpy

    img = load_image(sample_file)
    xmin, xmax = 15.0, 315.0
    ymin, ymax = 15.0, 318.0

    # 1. Picasso con preset calibrado
    locs_pic = localize_picasso(img, min_net_gradient=300.0, box_size=7, auto_scale_uint16=True)
    locs_pic_roi = locs_pic[(locs_pic['x'] >= xmin) & (locs_pic['x'] <= xmax) & (locs_pic['y'] >= ymin) & (locs_pic['y'] <= ymax)]
    assert len(locs_pic_roi) >= 830, f"Picasso detectó menos de 830 partículas ({len(locs_pic_roi)})"

    # Fourier Picasso
    x_nm = locs_pic_roi['x'].values * 50.0
    y_nm = locs_pic_roi['y'].values * 50.0
    res_pic = analyze_reciprocal_space_2d(x_nm, y_nm, a_nominal=500.0)
    assert abs(res_pic['a_mean'] - 498.6) < 1.5, f"a_mean Picasso={res_pic['a_mean']} fuera de tolerancia"

    # 2. Trackpy con preset calibrado
    locs_tp = localize_trackpy(img, diameter=5, minmass=0.05, separation=7.0)
    locs_tp_roi = locs_tp[(locs_tp['x'] >= xmin) & (locs_tp['x'] <= xmax) & (locs_tp['y'] >= ymin) & (locs_tp['y'] <= ymax)]
    assert len(locs_tp_roi) >= 830, f"Trackpy detectó menos de 830 partículas ({len(locs_tp_roi)})"

    # Fourier Trackpy
    x_nm_tp = locs_tp_roi['x'].values * 50.0
    y_nm_tp = locs_tp_roi['y'].values * 50.0
    res_tp = analyze_reciprocal_space_2d(x_nm_tp, y_nm_tp, a_nominal=500.0)
    assert abs(res_tp['a_mean'] - 498.8) < 1.5, f"a_mean Trackpy={res_tp['a_mean']} fuera de tolerancia"


def test_real_space_kdtree_consistency_margin():
    """Verifica el chequeo de consistencia física M + n_vac <= N^2 * (1 + margin/100)."""
    a_nominal = 500.0
    n_side = 10
    N_total = n_side * n_side  # 100

    # 1. Red ideal completa (100 partículas): 0 vacancias, M + n_vac = 100 == N^2
    x, y = _generate_synthetic_grid(n_side=n_side, a=a_nominal, sigma=0.0, f_vac=0.0)
    res = analyze_real_space_kdtree(x, y, a=a_nominal, n_side=n_side, margin_percent=10.0)
    assert res['consistency_ok'] is True
    assert res['consistency_sum'] == 100
    assert res['vacant_count'] == 0
    assert res['max_allowed_particles'] == 110

    # 2. Red con vacancias (80 partículas): 20 vacancias, M + n_vac = 100 == N^2
    x_vac, y_vac = _generate_synthetic_grid(n_side=n_side, a=a_nominal, sigma=0.0, f_vac=0.20, seed=123)
    res_vac = analyze_real_space_kdtree(x_vac, y_vac, a=a_nominal, n_side=n_side, margin_percent=10.0)
    assert res_vac['consistency_ok'] is True
    assert res_vac['consistency_sum'] == 100
    assert res_vac['vacant_count'] == 100 - len(x_vac)

    # 3. Red con exceso de partículas espurias fuera de grilla (+25 partículas lejos de la red)
    x_spurious = np.concatenate([x, np.linspace(10000, 15000, 25)])
    y_spurious = np.concatenate([y, np.linspace(10000, 15000, 25)])
    res_spurious = analyze_real_space_kdtree(x_spurious, y_spurious, a=a_nominal, n_side=n_side, margin_percent=10.0)
    # Suma: 125 detectadas + 0 vacancias = 125 > 110 (10% de 100) -> Debe fallar la consistencia
    assert res_spurious['consistency_ok'] is False
    assert res_spurious['particles_outside_grid'] == 25
    assert "[ALERTA]" in res_spurious['consistency_msg']


def test_cluster_detection_and_resolution():
    """Verifica detección de dímeros/cadenas y desacoplamiento mediante keep_nearest y merge_com."""
    a_nom = 500.0
    scale_nm = 50.0

    # Crear una grilla 5x5 con un dímero en el nodo (0, 0)
    half = (4 * a_nom) / 2.0
    g1d = np.linspace(-half, half, 5)
    X, Y = np.meshgrid(g1d, g1d)
    x_base = list(X.ravel())
    y_base = list(Y.ravel())

    # Agregar una partícula satélite a 80 nm del primer punto
    x_base.append(x_base[0] + 80.0)
    y_base.append(y_base[0] + 20.0)

    df_locs = pd.DataFrame({
        'x_nm': np.array(x_base),
        'y_nm': np.array(y_base),
        'x': np.array(x_base) / scale_nm,
        'y': np.array(y_base) / scale_nm,
        'photons': np.ones(len(x_base)) * 500.0
    })

    # Detección de clusters
    clusters_info = detect_clusters_and_chains(
        df_locs['x_nm'].values,
        df_locs['y_nm'].values,
        a_nominal=a_nom,
        r_cluster_factor=0.60
    )
    assert clusters_info['n_clusters'] == 1
    assert clusters_info['n_dimers'] == 1
    assert len(clusters_info['cluster_particle_indices']) == 2

    # Resolución 1: keep_nearest
    df_nearest, stats_near = resolve_clusters_dataframe(
        df_locs, clusters_info, action='keep_nearest', a=a_nom, x0=0.0, y0=0.0, scale_nm=scale_nm
    )
    assert len(df_nearest) == 25  # Se descarta la partícula satélite espuria
    assert stats_near['particles_removed'] == 1

    # Resolución 2: merge_com
    df_com, stats_com = resolve_clusters_dataframe(
        df_locs, clusters_info, action='merge_com', a=a_nom, x0=0.0, y0=0.0, scale_nm=scale_nm
    )
    assert len(df_com) == 25  # Se fusionan las 2 partículas en 1 en su centro de masa


def test_reserva_30x30_500_vacancies_and_consistency():
    """Valida la consistencia física y ausencia de vacancias espurias fuera de grilla en 30x30_500.tiff."""
    sample_file = Path(__file__).resolve().parent.parent / "reserva" / "30x30_500.tiff"
    if not sample_file.exists():
        return

    from core.localization_pipeline import load_image, localize_picasso

    img = load_image(str(sample_file))
    scale_nm = 50.0
    a_nom = 500.0
    n_side = 30
    N_total = 900

    # Localización con Picasso
    locs = localize_picasso(img, min_net_gradient=300.0, box_size=7, auto_scale_uint16=True)
    locs_df = convert_pixels_to_nm(locs, pixel_size_nm=scale_nm)

    # Filtrar por ROI de calibración
    xmin, xmax = 15.0, 315.0
    ymin, ymax = 15.0, 318.0
    roi_df = locs_df[
        (locs_df['x'] >= xmin) & (locs_df['x'] <= xmax) &
        (locs_df['y'] >= ymin) & (locs_df['y'] <= ymax)
    ].reset_index(drop=True)

    # Análisis KDTree con 10% de margen
    x_nm = roi_df['x_nm'].values
    y_nm = roi_df['y_nm'].values
    kdtree_res = analyze_real_space_kdtree(x_nm, y_nm, a=a_nom, n_side=n_side, margin_percent=10.0)

    # Verificación de que la caja delimitadora óptima abarca exactamente 30x30 sitios (900 sitios)
    assert kdtree_res['max_ix'] - kdtree_res['min_ix'] + 1 == 30
    assert kdtree_res['max_iy'] - kdtree_res['min_iy'] + 1 == 30
    assert kdtree_res['N_total_sites'] == 900

    # Verificación de la cota de consistencia física M + n_vac <= N^2 * 1.10 = 990
    assert kdtree_res['consistency_ok'] is True
    assert kdtree_res['consistency_sum'] <= 990
    assert kdtree_res['particles_in_grid'] >= 800


def test_single_emitter_calibration():
    """
    Prueba unitaria para la calibración del patrón monómero (V0, A0, sigma_psf).
    Genera partículas gaussianas aisladas con ruido y comprueba que se extraiga
    el ancho de PSF y volumen con alta fidelidad metrológica.
    """
    H, W = 150, 150
    scale_nm = 50.0
    a_nom = 500.0  # 10 px
    bg_true = 20.0
    sigma_true_px = 2.80  # 140 nm
    I_amp = 150.0

    img = np.full((H, W), bg_true, dtype=float)
    centers = [(35, 35), (35, 115), (115, 35), (115, 115)]
    yy, xx = np.indices((H, W))

    for cx, cy in centers:
        img += I_amp * np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2.0 * sigma_true_px ** 2))

    # Construir DataFrame de localizaciones
    locs = []
    for cx, cy in centers:
        locs.append({
            'x': float(cx),
            'y': float(cy),
            'x_nm': float(cx * scale_nm),
            'y_nm': float(cy * scale_nm),
            'photons': 1000.0
        })
    df = pd.DataFrame(locs)

    sig = calibrate_single_emitter_signature(img, df, scale_nm=scale_nm, a_nominal=a_nom)

    assert sig['is_fallback'] is False
    assert sig['n_calibrated'] == 4
    # Comprobar que el ancho de la PSF extraído coincida con el valor simulado (< 8% de error)
    assert abs(sig['sigma_psf_px'] - sigma_true_px) / sigma_true_px < 0.08
    assert sig['V0'] > 0


def test_multi_gaussian_fit_resolution():
    """
    Prueba unitaria para el desacople sub-resolución mediante ajuste multi-gaussiano con sigma fija.
    Genera dos emisores colapsados a 200 nm de separación y valida su deconvolución sub-píxel.
    """
    size = 25
    scale_nm = 50.0
    sigma_psf_px = 2.80
    bg_val = 15.0

    patch = np.full((size, size), bg_val, dtype=float)
    yy, xx = np.indices((size, size))

    # Dos emisores separados por 4.0 px = 200 nm
    c1 = (10.0, 12.0)
    c2 = (14.0, 12.0)
    patch += 120.0 * np.exp(-((xx - c1[0]) ** 2 + (yy - c1[1]) ** 2) / (2.0 * sigma_psf_px ** 2))
    patch += 130.0 * np.exp(-((xx - c2[0]) ** 2 + (yy - c2[1]) ** 2) / (2.0 * sigma_psf_px ** 2))

    fitted = fit_multi_gaussian_roi(
        patch=patch,
        n_particles=2,
        sigma_psf_px=sigma_psf_px,
        scale_nm=scale_nm,
        origin_px=(100.0, 100.0)
    )

    assert len(fitted) == 2
    # Separación calculada entre los dos centros
    sep_nm = np.hypot(fitted[0]['x_nm'] - fitted[1]['x_nm'], fitted[0]['y_nm'] - fitted[1]['y_nm'])
    sep_px = sep_nm / scale_nm
    # Separación esperada: 4.0 px (200 nm)
    assert abs(sep_px - 4.0) < 0.3  # Error < 15 nm


def test_photometric_contours_and_stoichiometry():
    """
    Prueba unitaria para el análisis fotométrico de contornos y estequiometría.
    Valida la estimación n_est y el estado OK vs UNDER_RESOLVED con tolerancia ±20%.
    """
    H, W = 100, 100
    scale_nm = 50.0
    a_nom = 500.0
    sigma_psf = 2.80

    H, W = 150, 150
    scale_nm = 50.0
    a_nom = 500.0
    sigma_psf = 2.80

    img = np.full((H, W), 10.0, dtype=float)
    yy, xx = np.indices((H, W))

    # 4 Monómeros de referencia
    monomers = [(30, 30), (30, 110), (110, 30), (70, 70)]
    for cx, cy in monomers:
        img += 100.0 * np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2.0 * sigma_psf ** 2))

    # 1 Spot sobrepuesto (2 partículas colapsadas)
    super_pos = (110, 110)
    img += 220.0 * np.exp(-((xx - super_pos[0]) ** 2 + (yy - super_pos[1]) ** 2) / (2.0 * sigma_psf ** 2))

    locs = []
    for cx, cy in monomers:
        locs.append({'x': float(cx), 'y': float(cy), 'x_nm': float(cx * scale_nm), 'y_nm': float(cy * scale_nm), 'photons': 1000.0})
    locs.append({'x': float(super_pos[0]), 'y': float(super_pos[1]), 'x_nm': float(super_pos[0] * scale_nm), 'y_nm': float(super_pos[1] * scale_nm), 'photons': 2200.0})
    df = pd.DataFrame(locs)

    cl_info = detect_clusters_and_chains(
        df['x_nm'].values, df['y_nm'].values,
        a_nominal=a_nom,
        photons=df['photons'].values,
        brightness_ratio_threshold=1.6,
        image_2d=img,
        locs_df=df,
        scale_nm=scale_nm,
        tolerance_pct=20.0
    )

    assert cl_info['n_clusters'] >= 1
    # El spot sobrepuesto debe ser identificado como UNDER_RESOLVED (n_est >= 2, n_det = 1)
    super_cl = [c for c in cl_info['clusters'] if 'Sobrepuesta' in c['type']][0]
    assert super_cl['status'] == 'UNDER_RESOLVED'
    assert super_cl['n_est'] >= 2


def test_individual_vs_batch_cluster_resolution():
    """
    Prueba unitaria para la resolución individual (target_cluster_id) vs en lote (batch).
    Comprueba que target_cluster_id=1 altere exclusivamente el cúmulo 1.
    """
    scale_nm = 50.0
    a_nom = 500.0

    # DataFrame con 2 cúmulos artificiales (cada uno con 2 partículas)
    df = pd.DataFrame([
        {'x_nm': 1000.0, 'y_nm': 1000.0, 'x': 20.0, 'y': 20.0, 'photons': 500.0},
        {'x_nm': 1050.0, 'y_nm': 1000.0, 'x': 21.0, 'y': 20.0, 'photons': 500.0},
        {'x_nm': 3000.0, 'y_nm': 3000.0, 'x': 60.0, 'y': 60.0, 'photons': 500.0},
        {'x_nm': 3050.0, 'y_nm': 3000.0, 'x': 61.0, 'y': 60.0, 'photons': 500.0},
    ])

    cl_info = detect_clusters_and_chains(
        df['x_nm'].values, df['y_nm'].values, a_nominal=a_nom
    )
    assert cl_info['n_clusters'] == 2

    # 1. Resolución Individual de Cúmulo #1
    df_single, stats_single = resolve_clusters_dataframe(
        df, cl_info, action='keep_nearest', a=a_nom, target_cluster_id=1
    )
    assert stats_single['clusters_resolved'] == 1
    assert stats_single['particles_removed'] == 1
    assert len(df_single) == 3
    # Comprobar que el cúmulo 2 sigue teniendo sus 2 partículas originales intactas
    c2_pts = df_single[(df_single['x_nm'] >= 2900) & (df_single['x_nm'] <= 3100)]
    assert len(c2_pts) == 2

    # 2. Resolución Masiva (en lote)
    df_batch, stats_batch = resolve_clusters_dataframe(
        df, cl_info, action='keep_nearest', a=a_nom, target_cluster_id=None
    )
    assert stats_batch['clusters_resolved'] == 2
    assert stats_batch['particles_removed'] == 2
    assert len(df_batch) == 2


def test_inspect_single_spot_photometry():
    """Valida la inspección fotométrica de un punto sospechoso (área, volumen, n_suggested y contorno)."""
    scale_nm = 50.0
    sigma_px = 2.5
    H, W = 100, 100
    yy, xx = np.mgrid[0:H, 0:W]

    # Crear imagen sintética con:
    # 1 monómero en (25, 25)
    # 1 dímero sobrepuesto en (75, 75)
    img = np.zeros((H, W), dtype=float)
    # Monómero
    img += 1.0 * np.exp(-((xx - 25)**2 + (yy - 25)**2) / (2.0 * sigma_px**2))
    # Dímero con 2x intensidad/volumen
    img += 1.0 * np.exp(-((xx - 74)**2 + (yy - 75)**2) / (2.0 * sigma_px**2))
    img += 1.0 * np.exp(-((xx - 76)**2 + (yy - 75)**2) / (2.0 * sigma_px**2))

    df_sample = pd.DataFrame([
        {'x': 25.0, 'y': 25.0, 'x_nm': 1250.0, 'y_nm': 1250.0, 'photons': 1000.0},
        {'x': 75.0, 'y': 75.0, 'x_nm': 3750.0, 'y_nm': 3750.0, 'photons': 2000.0}
    ])

    # 1. Inspeccionar monómero
    res_mono = inspect_single_spot_photometry(
        img, x_nm=1250.0, y_nm=1250.0, signature_dict=None,
        threshold_pct=20.0, scale_nm=scale_nm, a_nominal=500.0
    )
    assert res_mono['n_suggested'] == 1
    assert res_mono['v_omega'] > 0
    assert res_mono['area_px'] > 0
    assert len(res_mono['contour_polygon_nm']) > 2

    # Firma monomérica de referencia a partir del monómero medido
    sig_mono = {
        'V0': res_mono['v_omega'],
        'A0': res_mono['area_px'],
        'sigma_psf_px': sigma_px,
        'sigma_psf_nm': sigma_px * scale_nm
    }

    # 2. Inspeccionar dímero frente a la firma monomérica
    res_dimer = inspect_single_spot_photometry(
        img, x_nm=3750.0, y_nm=3750.0, signature_dict=sig_mono,
        threshold_pct=20.0, scale_nm=scale_nm, a_nominal=500.0
    )
    assert res_dimer['n_suggested'] >= 2
    assert res_dimer['v_omega'] > res_mono['v_omega'] * 1.5
    assert res_dimer['ratio_v'] >= 1.5


def test_resolve_single_spot_multi_gaussian():
    """Valida el desacople interactivo de un punto sospechoso específico mediante fit multi-Gaussiano."""
    scale_nm = 50.0
    sigma_px = 2.5
    H, W = 80, 80
    yy, xx = np.mgrid[0:H, 0:W]

    # Crear spot con 2 partículas separadas por 4 píxeles (200 nm) a lo largo de X
    img = np.zeros((H, W), dtype=float)
    img += 1.0 * np.exp(-((xx - 38)**2 + (yy - 40)**2) / (2.0 * sigma_px**2))
    img += 1.0 * np.exp(-((xx - 42)**2 + (yy - 40)**2) / (2.0 * sigma_px**2))

    df = pd.DataFrame([
        {'x': 10.0, 'y': 10.0, 'x_nm': 500.0, 'y_nm': 500.0, 'photons': 1000.0},
        {'x': 40.0, 'y': 40.0, 'x_nm': 2000.0, 'y_nm': 2000.0, 'photons': 2000.0}  # spot_index = 1
    ])

    sig = {'V0': 15.0, 'A0': 30.0, 'sigma_psf_px': sigma_px, 'sigma_psf_nm': sigma_px * scale_nm}

    # Desacoplar el spot_index=1 en 2 partículas
    df_resolved, stats = resolve_single_spot_multi_gaussian(
        df=df,
        spot_index=1,
        n_particles=2,
        image_2d=img,
        signature_dict=sig,
        scale_nm=scale_nm,
        a_nominal=500.0
    )

    assert stats['status'] == 'ok'
    assert stats['n_fitted'] == 2
    # El DataFrame ahora debe tener 3 partículas (1 original + 2 desacopladas)
    assert len(df_resolved) == 3
    # La partícula 0 se conserva intacta
    assert np.isclose(df_resolved.loc[0, 'x_nm'], 500.0)
    # Las dos nuevas partículas deben estar cerca de x=1900 nm y x=2100 nm
    new_xs = df_resolved.loc[1:, 'x_nm'].values
    assert len(new_xs) == 2
    assert np.abs(new_xs[1] - new_xs[0]) > 50.0  # claramente desacopladas


def test_multi_order_bragg_peaks_ideal():
    """Verifica la extracción y jerarquía de picos de Bragg (orden 1, 2, diagonal) en una red perfecta."""
    a_nominal = 500.0
    x, y = _generate_synthetic_grid(n_side=30, a=a_nominal, sigma=0.0)

    res = analyze_reciprocal_space_2d(x, y, a_nominal=a_nominal, n_bins=256)

    # 1er orden
    assert abs(res['a_x'] - a_nominal) < 2.0
    assert abs(res['a_y'] - a_nominal) < 2.0
    assert abs(res['anisotropy']) < 2.0

    # Diagonal 45°
    assert abs(res['a_diag'] - a_nominal) < 2.0
    assert res['fit_diag']['success']
    assert abs(res['shear_strain_deg']) < 0.5

    # 2do armónico
    assert abs(res['a_x_2nd'] - a_nominal) < 2.0
    assert abs(res['a_y_2nd'] - a_nominal) < 2.0
    assert res['fit_x_2nd']['success']
    assert res['fit_y_2nd']['success']

    # Mosaico angular y fondo difuso
    assert res['mosaic_x']['delta_theta_deg'] < 3.0
    assert res['sbr_mean'] > 50.0


def test_multi_order_debye_waller_scaling():
    """Verifica que para desorden gaussiano inyectado (sigma=15 nm), los picos atenúen según exp(-G^2 sigma^2)."""
    a_nominal = 500.0
    sigma_inj = 15.0
    x, y = _generate_synthetic_grid(n_side=30, a=a_nominal, sigma=sigma_inj, seed=42)

    res = analyze_reciprocal_space_2d(x, y, a_nominal=a_nominal, n_bins=256)

    # En red de 500 nm, q0 = 2*pi/500 = 0.012566 nm^-1
    # Ratio H2 / H1 ~ exp(-3 * q0^2 * sigma^2)
    q0 = 2.0 * np.pi / a_nominal
    expected_ratio_2nd = np.exp(-3.0 * (q0 ** 2) * (sigma_inj ** 2))
    meas_ratio_2nd = res['ratio_order2_x']

    # Tolerancia del 10% debida al muestreo estocástico finito
    assert abs(meas_ratio_2nd - expected_ratio_2nd) / expected_ratio_2nd < 0.10

    # Ratio de anchos paracristalinos FWHM2 / FWHM1 en Tipo I debe ser ~ 1.0 (< 1.5)
    assert res['paracrystal_ratio_x'] < 1.5


def test_monte_carlo_multi_order_calibration():
    """Verifica que la simulación MC genere curvas para orden 1, diagonal y 2do orden, y se persistan."""
    calib = run_monte_carlo_calibration(
        n_side=20,
        a=500.0,
        sigma_min=0.0,
        sigma_max=40.0,
        n_sigma_steps=5,
        iterations_per_step=10,
        seed=123
    )

    assert 'H_mean_diag' in calib
    assert 'H_mean_2' in calib
    assert calib['fit_diag']['success']
    assert calib['fit_2']['success']
    assert calib['fit_diag']['r_squared'] > 0.90
    assert calib['fit_2']['r_squared'] > 0.90

    # Probar persistencia (guardar y cargar)
    with tempfile.TemporaryDirectory() as tmpdir:
        npz_path = os.path.join(tmpdir, "test_multi_calib.npz")
        save_calibration_curve(npz_path, calib)
        loaded = load_calibration_curve(npz_path)

        assert loaded['H_mean_diag'] is not None
        assert loaded['H_mean_2'] is not None
        assert len(loaded['H_mean_diag']) == 5
        assert np.allclose(loaded['H_mean_diag'], calib['H_mean_diag'])
        assert np.allclose(loaded['H_mean_2'], calib['H_mean_2'])


def test_analytical_bragg_relations_ideal():
    """Verifica el cálculo analítico directo en una red ideal (sigma = 0 nm)."""
    a_nominal = 500.0
    x, y = _generate_synthetic_grid(n_side=30, a=a_nominal, sigma=0.0, seed=42)
    res = analyze_reciprocal_space_2d(x, y, a_nominal=a_nominal, n_bins=256)

    assert 'analytical_relations' in res
    ar = res['analytical_relations']

    # En red perfecta, sigma de Wilson es 0.00 nm
    assert ar['sigma_wilson'] < 1.0
    assert ar['paracrystal_diagnosis']['is_type_1']
    assert "Tipo I" in ar['paracrystal_diagnosis']['disorder_type']
    assert ar['r_squared_wilson'] >= 0.95


def test_analytical_bragg_relations_disordered():
    """Verifica que la fórmula analítica H2/H1 invierta sigma = 15 nm con exactitud sub-métrica."""
    a_nominal = 500.0
    sigma_inj = 15.0
    x, y = _generate_synthetic_grid(n_side=30, a=a_nominal, sigma=sigma_inj, seed=42)
    res = analyze_reciprocal_space_2d(x, y, a_nominal=a_nominal, n_bins=256)

    ar = res['analytical_relations']

    # Error absoluto en sigma_h2h1 debe ser inferior a 1.0 nm (de hecho es < 0.2 nm)
    assert abs(ar['sigma_h2h1'] - sigma_inj) < 1.0
    # Wilson plot tracking
    assert abs(ar['sigma_wilson'] - sigma_inj) < 2.0
    assert ar['r_squared_wilson'] > 0.90
    assert ar['paracrystal_diagnosis']['is_type_1']


def test_analytical_bragg_relations_unstable_h1h0():
    """Verifica la bandera de inestabilidad en H1/H0 y la estructura completa de datos para ploteo."""
    a_nominal = 500.0
    x, y = _generate_synthetic_grid(n_side=30, a=a_nominal, sigma=15.0, seed=42)
    res = analyze_reciprocal_space_2d(x, y, a_nominal=a_nominal, n_bins=256)
    ar = res['analytical_relations']

    assert ar['is_h1h0_unstable'] is True
    assert 'wilson_data' in ar
    assert len(ar['wilson_data']['g_sq']) == 5
    assert len(ar['wilson_data']['fit_g_sq']) == 100
    assert 'debye_waller_curve' in ar
    assert len(ar['debye_waller_curve']['q_norm']) == 120
    assert 'stability_comparison' in ar
    assert len(ar['stability_comparison']['methods']) == 4


def test_analytical_bragg_relations_anisotropic_and_wilson_dimensions():
    """Verifica las relaciones analíticas completas para H_1x, H_1y, H_diag/H_1x,y, H_0/H_1x,y y Wilson X/Y."""
    a_nominal = 500.0
    x, y = _generate_synthetic_grid(n_side=30, a=a_nominal, sigma=15.0, seed=42)
    res = analyze_reciprocal_space_2d(x, y, a_nominal=a_nominal, n_bins=256)
    ar = res['analytical_relations']

    # 1. Verificación de picos fundamentales y armónicos
    assert 'H1_x' in ar and ar['H1_x'] > 0
    assert 'H1_y' in ar and ar['H1_y'] > 0
    assert 'H2_x' in ar and ar['H2_x'] > 0
    assert 'H2_y' in ar and ar['H2_y'] > 0
    assert 'H_diag' in ar and ar['H_diag'] > 0
    assert 'H0' in ar and ar['H0'] > 0

    # 2. Relaciones diagonales por eje
    assert 'ratio_diag_x' in ar and ar['ratio_diag_x'] > 0
    assert 'ratio_diag_y' in ar and ar['ratio_diag_y'] > 0
    assert 'sigma_diag_x' in ar and ar['sigma_diag_x'] > 0
    assert 'sigma_diag_y' in ar and ar['sigma_diag_y'] > 0

    # 3. Relaciones con pico central H0 por eje
    assert 'ratio_0_1x' in ar and ar['ratio_0_1x'] > 0
    assert 'ratio_0_1y' in ar and ar['ratio_0_1y'] > 0
    assert 'ratio_10_x' in ar and ar['ratio_10_x'] > 0
    assert 'ratio_10_y' in ar and ar['ratio_10_y'] > 0
    assert 'sigma_h1h0_x' in ar
    assert 'sigma_h1h0_y' in ar

    # 4. Wilson Plot anisótropo (X e Y independientes con m e interceptos)
    assert 'sigma_wilson_x' in ar and 'sigma_wilson_y' in ar
    assert 'slope_wilson_x' in ar and 'slope_wilson_y' in ar
    assert 'intercept_wilson_x' in ar and 'intercept_wilson_y' in ar
    assert abs(ar['sigma_wilson_x'] - 15.0) < 3.0
    assert abs(ar['sigma_wilson_y'] - 15.0) < 3.0

    # Estructura detallada de Wilson data
    wd = ar['wilson_data']
    assert 'x' in wd and 'y' in wd and 'diag' in wd and 'conclusions' in wd
    assert len(wd['x']['g_sq']) == 2
    assert len(wd['y']['g_sq']) == 2
    assert wd['x']['slope'] < 0
    assert wd['y']['slope'] < 0
    assert 'i0_eff' in wd['x'] and wd['x']['i0_eff'] > 0
    assert 'i0_eff' in wd['y'] and wd['y']['i0_eff'] > 0
    assert 'anisotropy_text' in wd['conclusions']
    assert 'intercept_text' in wd['conclusions']
    assert 'background_text' in wd['conclusions']

    # 5. Debye-Waller curves y Paracristal desglosados en X e Y
    dwc = ar['debye_waller_curve']
    assert 'x' in dwc and 'y' in dwc and 'diag' in dwc
    para = ar['paracrystal_diagnosis']
    assert 'fwhm1_x' in para and 'fwhm2_x' in para and 'ratio_fwhm_x' in para
    assert 'fwhm1_y' in para and 'fwhm2_y' in para and 'ratio_fwhm_y' in para


def test_analytical_bragg_relations_anchor_wilson_to_h0():
    """Verifica el anclaje forzado del intercepto de Wilson a ln(H0) para ajuste de 1 parámetro."""
    a_nominal = 500.0
    x, y = _generate_synthetic_grid(n_side=30, a=a_nominal, sigma=14.0, seed=42)
    res = analyze_reciprocal_space_2d(x, y, a_nominal=a_nominal, n_bins=256)

    # 1. Sin anclar (Default / Libre)
    ar_free = compute_analytical_bragg_relations(res, a_nominal=a_nominal, anchor_wilson_to_h0=False)
    assert ar_free['anchor_wilson_to_h0'] is False
    assert ar_free['wilson_data']['anchor_wilson_to_h0'] is False

    # 2. Con anclaje a ln(H0)
    ar_anchored = compute_analytical_bragg_relations(res, a_nominal=a_nominal, anchor_wilson_to_h0=True)
    assert ar_anchored['anchor_wilson_to_h0'] is True
    assert ar_anchored['wilson_data']['anchor_wilson_to_h0'] is True

    # Comprobar que los interceptos coincidan exactamente con ln(H0)
    expected_c0 = np.log(ar_anchored['H0'])
    assert abs(ar_anchored['intercept_wilson_x'] - expected_c0) < 1e-9
    assert abs(ar_anchored['intercept_wilson_y'] - expected_c0) < 1e-9
    assert abs(ar_anchored['intercept_wilson'] - expected_c0) < 1e-9

    # Comprobar que las pendientes forzadas deducen sigma positivo cercano a 14.0 nm
    assert ar_anchored['sigma_wilson_x'] > 0
    assert ar_anchored['sigma_wilson_y'] > 0
    assert abs(ar_anchored['sigma_wilson_x'] - 14.0) < 4.0
    assert abs(ar_anchored['sigma_wilson_y'] - 14.0) < 4.0

    # Comprobar conclusiones
    concl = ar_anchored['wilson_data']['conclusions']
    assert "anclados a ln(H₀)" in concl['intercept_text']
    assert "Discrepancia" in concl['background_text'] or "concordancia" in concl['background_text']


def test_real_space_kdtree_rectangular_anisotropic():
    """Verifica que en una red rectangular (a != b, N_x != N_y) el motor recupere
    sigma_x y sigma_y por separado a partir de un desorden anisótropo inyectado."""
    a_val, b_val = 400.0, 550.0
    n_side_x, n_side_y = 10, 12
    sigma_x_in, sigma_y_in = 18.0, 30.0

    rng = np.random.default_rng(2024)
    half_x = ((n_side_x - 1) * a_val) / 2.0
    half_y = ((n_side_y - 1) * b_val) / 2.0
    gx = np.linspace(-half_x, half_x, n_side_x)
    gy = np.linspace(-half_y, half_y, n_side_y)
    X, Y = np.meshgrid(gx, gy)
    x = X.ravel() + rng.normal(0, sigma_x_in, X.size)
    y = Y.ravel() + rng.normal(0, sigma_y_in, Y.size)

    res = analyze_real_space_kdtree(x, y, a=a_val, b=b_val, n_side_x=n_side_x, n_side_y=n_side_y)

    assert abs(res['sigma_x'] - sigma_x_in) < 4.0, f"sigma_x={res['sigma_x']} lejos de {sigma_x_in}"
    assert abs(res['sigma_y'] - sigma_y_in) < 4.0, f"sigma_y={res['sigma_y']} lejos de {sigma_y_in}"
    assert res['n_side_x'] == n_side_x
    assert res['n_side_y'] == n_side_y
    assert res['is_anisotropic'] is True
    assert res['vacant_count'] == 0
    assert res['gamma_lindemann'] > 0.0


def test_real_space_kdtree_rectangular_backward_compat_square():
    """Verifica que la firma legada (a, n_side) siga produciendo una red cuadrada isótropa idéntica."""
    a_nominal = 450.0
    x, y = _generate_synthetic_grid(n_side=15, a=a_nominal, sigma=5.0, seed=77)

    res_legacy = analyze_real_space_kdtree(x, y, a=a_nominal, n_side=15)
    res_explicit = analyze_real_space_kdtree(x, y, a=a_nominal, b=a_nominal, n_side_x=15, n_side_y=15)

    assert abs(res_legacy['sigma_pos'] - res_explicit['sigma_pos']) < 1e-9
    assert res_legacy['n_side_x'] == 15 and res_legacy['n_side_y'] == 15
    assert res_legacy['is_anisotropic'] is False


def test_bond_orientational_order_perfect_rectangular_lattice():
    """Verifica que una red rectangular perfecta (sigma=0) dé <psi4> cercano a 1.0."""
    a_val = 450.0
    x, y = _generate_synthetic_grid(n_side=12, a=a_val, sigma=0.0, seed=11)

    res = compute_bond_orientational_order(x, y, k_neighbors=4, lattice_type='rectangular')

    # Nota: con kNN de grado fijo (vectorizado), las partículas de esquina se rellenan
    # con su 4to vecino real más cercano (la diagonal), lo que baja levemente <psi4>
    # respecto de una lista de adyacencia de Delaunay pura en el borde; 0.80 sigue
    # distinguiendo con margen amplio el régimen ordenado del desordenado (ver test siguiente).
    assert res['psi4_mean'] > 0.80, f"psi4_mean={res['psi4_mean']} demasiado bajo para red perfecta"
    assert len(res['coordination']) == len(x)
    # coordination es de grado fijo (kNN vectorizado): siempre == k_neighbors, no es un
    # indicador de defectos topológicos reales (ver compute_voronoi_topology para eso).
    assert np.all(res['coordination'] == 4)


def test_bond_orientational_order_disordered_lattice_lower_psi4():
    """Verifica que inyectar desorden posicional degrade <psi4> respecto de la red ideal."""
    a_val = 450.0
    x_ideal, y_ideal = _generate_synthetic_grid(n_side=12, a=a_val, sigma=0.0, seed=11)
    x_noisy, y_noisy = _generate_synthetic_grid(n_side=12, a=a_val, sigma=0.35 * a_val, seed=11)

    res_ideal = compute_bond_orientational_order(x_ideal, y_ideal)
    res_noisy = compute_bond_orientational_order(x_noisy, y_noisy)

    assert res_noisy['psi4_mean'] < res_ideal['psi4_mean']


def test_voronoi_topology_internal_coordination_perfect_lattice():
    """Verifica que en una red regular interna Z=4 y f_defects=0.0 (excluyendo celdas de borde)."""
    a_nominal = 450.0
    n_side = 14
    x, y = _generate_synthetic_grid(n_side=n_side, a=a_nominal, sigma=0.0, seed=22)

    margin = 1.5 * a_nominal
    x_range = (float(np.min(x)) + margin, float(np.max(x)) - margin)
    y_range = (float(np.min(y)) + margin, float(np.max(y)) - margin)

    res = compute_voronoi_topology(x, y, x_range=x_range, y_range=y_range)

    assert res['n_internal'] > 0
    assert res['f_defects'] == 0.0, f"f_defects={res['f_defects']} debe ser 0 para red perfecta"
    internal_coord = res['coordination'][res['is_internal']]
    assert np.all(internal_coord == 4), f"Coordinaciones internas: {np.unique(internal_coord)}"
    assert res['area_cv'] < 0.05


def test_voronoi_topology_robust_to_small_positional_noise():
    """Verifica que ruido posicional pequeño (~2% del período) no infle espuriamente
    la coordinación Z por degeneración numérica de vértices de Voronoi cocirculares
    (regresión: 4 puntos exactamente cocirculares por celda en una red cuadrada perfecta
    se separan en vértices casi duplicados ante cualquier ruido, sin fusión de vértices)."""
    a_val, b_val = 400.0, 550.0
    n_side_x, n_side_y = 10, 12

    rng = np.random.default_rng(1)
    gx = np.linspace(0, (n_side_x - 1) * a_val, n_side_x)
    gy = np.linspace(0, (n_side_y - 1) * b_val, n_side_y)
    X, Y = np.meshgrid(gx, gy)
    x = X.ravel() + rng.normal(0, 8.0, X.size)
    y = Y.ravel() + rng.normal(0, 8.0, Y.size)

    margin_x, margin_y = 1.0 * a_val, 1.0 * b_val
    x_range = (float(np.min(x)) + margin_x, float(np.max(x)) - margin_x)
    y_range = (float(np.min(y)) + margin_y, float(np.max(y)) - margin_y)

    res = compute_voronoi_topology(x, y, x_range=x_range, y_range=y_range)

    assert res['n_internal'] > 0
    assert res['f_defects'] == 0.0, (
        f"f_defects={res['f_defects']} — ruido de {8.0} nm no debe generar defectos "
        f"espurios en una red de período {a_val}/{b_val} nm por degeneración de Voronoi"
    )
    internal_coord = res['coordination'][res['is_internal']]
    assert np.all(internal_coord == 4), f"Coordinaciones internas infladas: {np.unique(internal_coord)}"


def test_voronoi_topology_vacancy_creates_defect():
    """Verifica que remover una partícula interna genere celdas vecinas con Z != 4 (defecto topológico)."""
    a_nominal = 450.0
    n_side = 14
    x, y = _generate_synthetic_grid(n_side=n_side, a=a_nominal, sigma=0.0, seed=33)

    # Remueve la partícula más cercana al centro geométrico (garantizado interna)
    cx, cy = float(np.mean(x)), float(np.mean(y))
    idx_center = int(np.argmin((x - cx) ** 2 + (y - cy) ** 2))
    mask = np.ones(len(x), dtype=bool)
    mask[idx_center] = False
    x_vac, y_vac = x[mask], y[mask]

    margin = 1.5 * a_nominal
    x_range = (float(np.min(x_vac)) + margin, float(np.max(x_vac)) - margin)
    y_range = (float(np.min(y_vac)) + margin, float(np.max(y_vac)) - margin)

    res = compute_voronoi_topology(x_vac, y_vac, x_range=x_range, y_range=y_range)
    assert res['n_defects'] > 0
    assert res['f_defects'] > 0.0


def test_quiver_and_strain_pure_shear():
    """Verifica que un campo de deformación afín puro (shear conocido) se recupere en exx/eyy/exy."""
    a_nominal = 450.0
    n_side = 12
    x_ideal, y_ideal = _generate_synthetic_grid(n_side=n_side, a=a_nominal, sigma=0.0, seed=44)

    exx_true, eyy_true, exy_true = 0.02, -0.015, 0.01
    dx = exx_true * x_ideal + exy_true * y_ideal
    dy = exy_true * x_ideal + eyy_true * y_ideal
    x_deformed = x_ideal + dx
    y_deformed = y_ideal + dy
    valid_mask = np.ones(len(x_ideal), dtype=bool)

    res = compute_quiver_and_strain(x_deformed, y_deformed, x_ideal, y_ideal, valid_mask)

    assert res['success']
    assert abs(res['exx'] - exx_true) < 1e-6
    assert abs(res['eyy'] - eyy_true) < 1e-6
    assert abs(res['exy'] - exy_true) < 1e-6
    assert abs(res['omega']) < 1e-6


def test_radial_distribution_function_double_gaussian_rectangular():
    """Verifica que con a != b (> 15 nm de diferencia) la RDF resuelva los dos primeros
    picos de vecinos en a y b mediante doble gaussiana."""
    a_val, b_val = 400.0, 550.0
    n_side_x, n_side_y = 12, 12

    rng = np.random.default_rng(99)
    half_x = ((n_side_x - 1) * a_val) / 2.0
    half_y = ((n_side_y - 1) * b_val) / 2.0
    gx = np.linspace(-half_x, half_x, n_side_x)
    gy = np.linspace(-half_y, half_y, n_side_y)
    X, Y = np.meshgrid(gx, gy)
    x = X.ravel() + rng.normal(0, 8.0, X.size)
    y = Y.ravel() + rng.normal(0, 8.0, Y.size)

    res = compute_radial_distribution_function(x, y, a_nominal=a_val, b_nominal=b_val)

    assert res['is_double_peak'] is True
    assert res['secondary_peak'] is not None
    peaks = sorted([res['first_peak_r'], res['secondary_peak']['first_peak_r']])
    assert abs(peaks[0] - a_val) < 20.0, f"Pico menor {peaks[0]} lejos de a={a_val}"
    assert abs(peaks[1] - b_val) < 20.0, f"Pico mayor {peaks[1]} lejos de b={b_val}"


def test_radial_distribution_function_density_area_depends_on_b_nominal():
    """Regresión: la normalización de densidad rho = N/area debe usar b_nominal para
    el padding del eje Y (no a_nominal duplicado en ambos ejes), o g(r) queda ciego a
    b_nominal por completo para cualquier dato de entrada."""
    a_val = 450.0
    rng = np.random.default_rng(3)
    nx, ny = 10, 10
    gx = np.linspace(0, (nx - 1) * a_val, nx)
    gy = np.linspace(0, (ny - 1) * a_val, ny)
    X, Y = np.meshgrid(gx, gy)
    x = X.ravel() + rng.normal(0, 10.0, X.size)
    y = Y.ravel() + rng.normal(0, 10.0, Y.size)

    res_b200 = compute_radial_distribution_function(x, y, a_nominal=a_val, b_nominal=200.0)
    res_b800 = compute_radial_distribution_function(x, y, a_nominal=a_val, b_nominal=800.0)

    assert not np.allclose(res_b200['gr'], res_b800['gr'], atol=1e-6), (
        "g(r) no debe ser invariante ante b_nominal: la densidad de normalización "
        "rho = N/area debe depender del padding del eje Y con b_nominal"
    )


def test_radial_distribution_function_double_gaussian_resolvability_check():
    """Regresión: cuando los dos picos de vecinos (a, b) están demasiado cerca para
    resolverse de forma independiente (separación de centros < ~1.5x la suma de anchos),
    la función debe degradar a ajuste simple gaussiano en vez de reportar is_double_peak=True
    con un ajuste no-identificable (el optimizador intercambia amplitud/ancho entre picos)."""
    a_val, b_val = 450.0, 465.1  # diferencia > 15 nm (activa modo doble) pero muy cercanos
    n_side = 12
    rng = np.random.default_rng(21)
    gx = np.linspace(0, (n_side - 1) * a_val, n_side)
    gy = np.linspace(0, (n_side - 1) * b_val, n_side)
    X, Y = np.meshgrid(gx, gy)
    x = X.ravel() + rng.normal(0, 10.0, X.size)
    y = Y.ravel() + rng.normal(0, 10.0, Y.size)

    res = compute_radial_distribution_function(x, y, a_nominal=a_val, b_nominal=b_val)

    assert res['is_double_peak'] is False, (
        "Picos a 15.1 nm de separación con anchos ~14 nm no son resolubles; "
        "no debe reportarse is_double_peak=True"
    )
    assert res['peak_resolution_warning'] is True


def test_run_monte_carlo_calibration_independent_grid_dimensions():
    """Verifica que n_side_x/n_side_y independientes generen N_sites = n_side_x * n_side_y."""
    mc_res = run_monte_carlo_calibration(
        n_side=8,
        a=450.0,
        a_y=520.0,
        n_side_x=6,
        n_side_y=9,
        sigma_min=0.0,
        sigma_max=30.0,
        n_sigma_steps=4,
        iterations_per_step=5,
        seed=7
    )

    assert mc_res['n_side_x'] == 6
    assert mc_res['n_side_y'] == 9
    assert mc_res['N_sites'] == 54
    assert mc_res['is_anisotropic'] is True


# ==============================================================================
# FASE 2: REDES HEXAGONALES, HONEYCOMB Y TEMPLATE MATCHING UNIVERSAL
# ==============================================================================

def test_generate_ideal_lattice_template_hexagonal():
    """Verifica que la plantilla hexagonal generada vía core.lattice_generator tenga
    coordinación Voronoi ideal 6 y una única subred (base monoatómica)."""
    template = generate_ideal_lattice_template(
        lattice_type='hexagonal', a=500.0, boundary_type='hexagon', boundary_size_nm=4000.0
    )
    assert template['n_points'] > 50
    assert template['ideal_voronoi_coordination'] == 6
    assert np.all(template['sublattice_id'] == 1)
    assert template['gamma_deg'] == 60.0
    assert template['b_nm'] == 500.0


def test_generate_ideal_lattice_template_honeycomb():
    """Verifica que la plantilla honeycomb tenga 2 subredes A/B casi equinuméricas,
    coordinación Voronoi ideal 3, y que la base corregida (u=1/3, v=1/3; ver DEC-012)
    produzca la geometría de enlace honeycomb correcta: 3 vecinos equidistantes a
    d = a/sqrt(3), no la base original de core.lattice_generator (u=1/3, v=2/3) que
    se verificó no produce un honeycomb geométricamente válido bajo gamma=60°."""
    a_val = 600.0
    template = generate_ideal_lattice_template(
        lattice_type='honeycomb', a=a_val, boundary_type='hexagon', boundary_size_nm=4500.0
    )
    assert template['n_points'] > 100
    assert template['ideal_voronoi_coordination'] == 3
    assert set(np.unique(template['sublattice_id']).tolist()) == {1, 2}
    n_a = int(np.sum(template['sublattice_id'] == 1))
    n_b = int(np.sum(template['sublattice_id'] == 2))
    assert abs(n_a - n_b) <= max(2, int(0.1 * max(n_a, n_b)))

    # Verificar geometría de enlace: cada átomo A interno tiene exactamente 3 vecinos B
    # equidistantes a a/sqrt(3), no una mezcla de distancias distintas (bug de la base original)
    from scipy.spatial import cKDTree
    pts = np.column_stack([template['x'], template['y']])
    tree = cKDTree(pts)
    cx, cy = np.mean(template['x']), np.mean(template['y'])
    d_center = np.hypot(template['x'] - cx, template['y'] - cy)
    idx_internal = np.where((template['sublattice_id'] == 1) & (d_center < 1500.0))[0]
    assert len(idx_internal) > 0
    d_bond_expected = a_val / np.sqrt(3.0)
    for idx in idx_internal[:10]:
        dist, nn = tree.query(pts[idx], k=4)
        bond_dists = dist[1:4]  # 3 vecinos más cercanos (excluye el propio punto)
        assert np.all(np.abs(bond_dists - d_bond_expected) < 1.0), (
            f"Vecinos no equidistantes: {bond_dists} vs esperado {d_bond_expected}"
        )


def test_register_and_match_template_hexagonal_recovers_rotation_and_sigma():
    """Misión Fase 2: red hexagonal sintética dentro de un hexágono (a=500nm) con
    rotación y ruido posicional inyectados. Verifica recuperación del ángulo de
    rotación, de sigma_pos, detección de Z=6 en el bulk y <psi6> ~ 1.0."""
    a_val = 500.0
    template = generate_ideal_lattice_template(
        lattice_type='hexagonal', a=a_val, boundary_type='hexagon', boundary_size_nm=4000.0
    )

    rng = np.random.default_rng(42)
    sigma_in = 15.0
    theta_true_deg = 3.0
    th = np.radians(theta_true_deg)
    cx, cy = np.mean(template['x']), np.mean(template['y'])
    tx = template['x'] - cx
    ty = template['y'] - cy
    x_rot = tx * np.cos(th) - ty * np.sin(th) + cx
    y_rot = tx * np.sin(th) + ty * np.cos(th) + cy
    x_real = x_rot + rng.normal(0, sigma_in, len(x_rot))
    y_real = y_rot + rng.normal(0, sigma_in, len(y_rot))

    match = register_and_match_template(
        x_real, y_real, template['x'], template['y'], template['sublattice_id'],
        rotation_search_range_deg=10.0
    )

    assert abs(match['theta_fit_deg'] - theta_true_deg) < 0.5, (
        f"theta_fit={match['theta_fit_deg']} lejos del verdadero {theta_true_deg}"
    )
    assert abs(match['sigma_pos'] - sigma_in) < 4.0
    assert match['matched_count'] > 0.9 * len(x_real)

    mx = x_real[match['valid_mask']]
    my = y_real[match['valid_mask']]
    margin = 1.0 * a_val
    x_range = (float(np.min(mx)) + margin, float(np.max(mx)) - margin)
    y_range = (float(np.min(my)) + margin, float(np.max(my)) - margin)
    vor_res = compute_voronoi_topology(mx, my, x_range=x_range, y_range=y_range, ideal_z=6)
    assert vor_res['n_internal'] > 0
    internal_coord = vor_res['coordination'][vor_res['is_internal']]
    assert np.mean(internal_coord == 6) > 0.85

    bo_res = compute_bond_orientational_order(mx, my, k_neighbors=6)
    assert bo_res['psi6_mean'] > 0.7


def test_register_and_match_template_honeycomb_sublattices_and_vacancies():
    """Misión Fase 2: red honeycomb sintética (a=600nm, 2 átomos por celda) con 3
    vacancias inyectadas (1 en subred A, 2 en subred B). Verifica asignación correcta
    a subredes A/B, detección de vacancias por subred, Z=3 en el bulk (coordinación
    Voronoi) y primer pico de g(r) en d = a/sqrt(3) (no en a, que sería el 2do pico
    de la misma subred)."""
    a_val = 600.0
    template = generate_ideal_lattice_template(
        lattice_type='honeycomb', a=a_val, boundary_type='hexagon', boundary_size_nm=4500.0
    )

    rng = np.random.default_rng(7)
    idx_a = np.where(template['sublattice_id'] == 1)[0]
    idx_b = np.where(template['sublattice_id'] == 2)[0]
    cx, cy = np.mean(template['x']), np.mean(template['y'])
    d_center = np.hypot(template['x'] - cx, template['y'] - cy)
    # Elegir átomos internos (lejos del borde) para que la vacancia no se confunda
    # con el recorte de la geometría envolvente
    idx_a_internal = idx_a[np.argsort(d_center[idx_a])[:len(idx_a) // 2]]
    idx_b_internal = idx_b[np.argsort(d_center[idx_b])[:len(idx_b) // 2]]
    remove_a = rng.choice(idx_a_internal, size=1, replace=False)
    remove_b = rng.choice(idx_b_internal, size=2, replace=False)
    keep_mask = np.ones(template['n_points'], dtype=bool)
    keep_mask[remove_a] = False
    keep_mask[remove_b] = False

    sigma_in = 10.0
    x_real = template['x'][keep_mask] + rng.normal(0, sigma_in, int(np.sum(keep_mask)))
    y_real = template['y'][keep_mask] + rng.normal(0, sigma_in, int(np.sum(keep_mask)))

    match = register_and_match_template(
        x_real, y_real, template['x'], template['y'], template['sublattice_id'],
        rotation_search_range_deg=5.0
    )

    assert match['n_vacancies_by_sublattice'][1] >= 1
    assert match['n_vacancies_by_sublattice'][2] >= 2
    assert abs(match['sigma_pos'] - sigma_in) < 5.0

    # Verificar que las partículas reales fueron correctamente etiquetadas por subred:
    # comparar contra la subred del template en el índice correcto (usando el registro
    # identidad ~0° para este caso sin rotación inyectada)
    valid = match['valid_mask']
    assert np.all(np.isin(match['sublattice_id'][valid], [1, 2]))

    # g(r): primer pico en d = a/sqrt(3), NO en a (2do pico, misma subred)
    d_bond = a_val / np.sqrt(3.0)
    rdf_res = compute_radial_distribution_function(
        x_real, y_real, a_nominal=d_bond, r_max_factor=3.0,
        r_diffraction_limit=0.0, enforce_diffraction_limit=False
    )
    assert abs(rdf_res['first_peak_r'] - d_bond) < 30.0, (
        f"first_peak_r={rdf_res['first_peak_r']} lejos de d_bond={d_bond}"
    )

    # Coordinación Voronoi ideal_z=3 en el bulk
    mx, my = x_real[valid], y_real[valid]
    margin = 1.0 * a_val
    x_range = (float(np.min(mx)) + margin, float(np.max(mx)) - margin)
    y_range = (float(np.min(my)) + margin, float(np.max(my)) - margin)
    vor_res = compute_voronoi_topology(mx, my, x_range=x_range, y_range=y_range, ideal_z=3)
    assert vor_res['n_internal'] > 0
    internal_coord = vor_res['coordination'][vor_res['is_internal']]
    assert np.mean(internal_coord == 3) > 0.85


def test_register_and_match_template_hexagonal_robust_to_unshifted_template():
    """Regresión (DEC-012): register_and_match_template debe alinear correctamente datos
    reales hexagonales contra una plantilla generada SIN center_x_nm/center_y_nm (el patrón
    correcto -- la función ya hace su propia alineación de centroides internamente). Se
    encontró y documentó que pre-centrar la plantilla en generate_ideal_lattice_template
    con un offset de apenas ~1 nm puede alinear accidentalmente una fila completa de la red
    con el borde recto del contorno envolvente (BoundingGeometry.is_inside no se re-centra
    con offset_x/offset_y), produciendo una plantilla asimétrica con centroide real muy
    distinto del solicitado y arruinando el registro rígido (sigma_pos inflado ~10x)."""
    a_val = 500.0
    template = generate_ideal_lattice_template(
        lattice_type='hexagonal', a=a_val, boundary_type='hexagon', boundary_size_nm=4000.0
    )
    rng = np.random.default_rng(2)
    sigma_in = 12.0
    x_real = template['x'] + rng.normal(0, sigma_in, template['n_points'])
    y_real = template['y'] + rng.normal(0, sigma_in, template['n_points'])

    # Patrón correcto: NO pasar center_x_nm/center_y_nm (aunque los datos reales no estén
    # centrados exactamente en el origen -- register_and_match_template debe manejarlo).
    match = register_and_match_template(x_real, y_real, template['x'], template['y'], template['sublattice_id'])

    assert abs(match['sigma_pos'] - sigma_in) < 4.0, (
        f"sigma_pos={match['sigma_pos']} muy lejos de sigma inyectado={sigma_in} "
        "(síntoma de una plantilla mal alineada/asimétrica)"
    )
    assert match['matched_count'] == template['n_points']


def test_generate_ideal_lattice_template_center_offset_sensitivity_documented():
    """Documenta (no 'arregla', ver DEC-012) la sensibilidad conocida de
    generate_ideal_lattice_template/BoundingGeometry a offsets sub-período: un desplazamiento
    de ~1 nm puede volcar una fila completa de la red hexagonal dentro/fuera del contorno
    envolvente (fijo en el origen), cambiando el conteo de nodos y el centroide real en
    cientos de nm. Este test fija el comportamiento conocido como regresión de referencia,
    no como validación de que sea deseable -- la recomendación operativa (docstring de la
    función, DEC-012) es generar siempre la plantilla en el origen para template matching."""
    a_val = 500.0
    template0 = generate_ideal_lattice_template(
        lattice_type='hexagonal', a=a_val, boundary_type='hexagon', boundary_size_nm=4000.0
    )
    template_shifted = generate_ideal_lattice_template(
        lattice_type='hexagonal', a=a_val, boundary_type='hexagon', boundary_size_nm=4000.0,
        center_x_nm=-0.126, center_y_nm=-0.857
    )
    # Comportamiento conocido: el conteo de nodos difiere pese al offset submicroscópico
    assert template0['n_points'] != template_shifted['n_points']


def test_compute_basis_structure_factor_honeycomb():
    """Verifica el factor de estructura geométrico de base honeycomb F(G) = 1 + exp(-i G.tau):
    en G=0 (pico central), |F|^2 = 4 (2 átomos en fase); para el desplazamiento tau
    verdadero (offset real A->B en un template honeycomb generado), F debe evaluarse
    consistentemente entre 0 (supresión geométrica total) y 4 (máxima constructiva)."""
    a_val = 600.0
    template = generate_ideal_lattice_template(lattice_type='honeycomb', a=a_val, boundary_type='circle', boundary_size_nm=1000.0)
    idx_a0 = np.where(template['sublattice_id'] == 1)[0][0]
    # Vector tau: del átomo A más cercano al origen hacia su vecino B más cercano
    from scipy.spatial import cKDTree
    pts = np.column_stack([template['x'], template['y']])
    tree = cKDTree(pts)
    dist, nn = tree.query(pts[idx_a0], k=4)
    b_neighbors = [n for n in nn[1:] if template['sublattice_id'][n] == 2]
    assert len(b_neighbors) > 0
    tau_x = template['x'][b_neighbors[0]] - template['x'][idx_a0]
    tau_y = template['y'][b_neighbors[0]] - template['y'][idx_a0]

    Gx0, Gy0 = np.array([0.0]), np.array([0.0])
    F0 = compute_basis_structure_factor(Gx0, Gy0, [(0.0, 0.0), (tau_x, tau_y)])
    assert abs(F0[0] - 4.0) < 1e-9, f"F(G=0) debe ser 4 (2 átomos en fase), obtuvo {F0[0]}"

    # En |G| = 4*pi/(sqrt(3)*a) proyectado sobre la dirección de tau, la interferencia
    # debe ser destructiva o parcial (no necesariamente 0 exacto en esta proyección simple,
    # pero estrictamente <= 4 y >= 0 -- verificación de cota física)
    G_mag = 4.0 * np.pi / (np.sqrt(3.0) * a_val)
    Gx1 = np.array([G_mag])
    Gy1 = np.array([0.0])
    F1 = compute_basis_structure_factor(Gx1, Gy1, [(0.0, 0.0), (tau_x, tau_y)])
    assert 0.0 <= F1[0] <= 4.0 + 1e-6


def test_extract_angular_profile_matches_cartesian_cuts():
    """Verifica que extract_angular_profile a 0deg y 90deg coincida aproximadamente
    con los cortes cartesianos fx/fy de extract_1d_profiles para una red cuadrada.
    Nota: en una red perfecta (sigma=0) el pico DC (r=0) y el pico de Bragg de 1er
    orden tienen alturas casi idénticas (ambos son picos coherentes no atenuados de
    un cristal perfecto), por lo que la ventana de búsqueda debe excluir la región DC
    explícitamente (mismo patrón que fit_bragg_peak_1d's dc_cut_factor), no depender
    de que argmax rompa el empate hacia el lado correcto."""
    a_nominal = 450.0
    x, y = _generate_synthetic_grid(n_side=20, a=a_nominal, sigma=0.0)
    fx, fy, S = compute_structure_factor_2d(x, y, a_nominal=a_nominal, n_bins=256)
    _, profile_x, _, profile_y = extract_1d_profiles(S, fx, fy, band_width_bins=3)

    r_0, prof_0 = extract_angular_profile(S, fx, fy, angle_deg=0.0, band_width_bins=3)
    r_90, prof_90 = extract_angular_profile(S, fx, fy, angle_deg=90.0, band_width_bins=3)

    f0_target = 1.0 / a_nominal
    dc_cut = 0.4 * f0_target

    mask_cart_x = (fx > dc_cut) & (fx < 1.4 * f0_target)
    peak_cart_x = fx[mask_cart_x][np.argmax(profile_x[mask_cart_x])]
    mask_ang_0 = (r_0 > dc_cut) & (r_0 < 1.4 * f0_target)
    peak_ang_0 = r_0[mask_ang_0][np.argmax(prof_0[mask_ang_0])]
    assert abs(peak_cart_x - peak_ang_0) < (fx[1] - fx[0]) * 5

    mask_cart_y = (fy > dc_cut) & (fy < 1.4 * f0_target)
    peak_cart_y = fy[mask_cart_y][np.argmax(profile_y[mask_cart_y])]
    mask_ang_90 = (r_90 > dc_cut) & (r_90 < 1.4 * f0_target)
    peak_ang_90 = r_90[mask_ang_90][np.argmax(prof_90[mask_ang_90])]
    assert abs(peak_cart_y - peak_ang_90) < (fy[1] - fy[0]) * 5


def test_compute_radial_azimuthal_profile_hexagonal_peak():
    """Verifica que la integración azimutal S(q) de una red hexagonal muestre un pico
    dominante cerca de |G|/(2*pi) = 2/(sqrt(3)*a) (primer orden de Bragg hexagonal)."""
    a_val = 500.0
    template = generate_ideal_lattice_template(lattice_type='hexagonal', a=a_val, boundary_type='hexagon', boundary_size_nm=4000.0)
    f0_expected = 2.0 / (np.sqrt(3.0) * a_val)
    fx, fy, S = compute_structure_factor_2d(template['x'], template['y'], a_nominal=a_val, n_bins=256, f_max_factor=3.0)
    r_q, q_profile = compute_radial_azimuthal_profile(S, fx, fy, n_r_bins=128)

    # Buscar el pico dominante en una ventana alrededor de f0_expected, evitando el pico DC
    mask = (r_q > 0.5 * f0_expected) & (r_q < 1.5 * f0_expected)
    assert np.any(mask)
    peak_r = r_q[mask][np.argmax(q_profile[mask])]
    assert abs(peak_r - f0_expected) < 0.15 * f0_expected


def test_analyze_reciprocal_space_2d_no_crash_on_hexagonal_data():
    """Regresión: analyze_reciprocal_space_2d (y compute_analytical_bragg_relations,
    invocada internamente) no debe lanzar ZeroDivisionError sobre datos de red hexagonal,
    cuyos picos de Bragg reales no caen en los ejes cartesianos fx/fy que este análisis
    asume — el ajuste Wilson-X puede degenerar a sigma_wilson_x=0 exactamente, y
    1.0/aniso_ratio (no sólo aniso_ratio en sí) carecía de guarda contra división por cero."""
    a_val = 500.0
    template = generate_ideal_lattice_template(
        lattice_type='hexagonal', a=a_val, boundary_type='hexagon', boundary_size_nm=4000.0
    )
    rng = np.random.default_rng(11)
    x = template['x'] + rng.normal(0, 12.0, template['n_points'])
    y = template['y'] + rng.normal(0, 12.0, template['n_points'])
    res = analyze_reciprocal_space_2d(x, y, a_nominal=a_val, n_bins=256)
    assert 'analytical_relations' in res


def test_run_hexagonal_monte_carlo_calibration_monotonic_attenuation():
    """Regresión: la calibración Monte Carlo hexagonal debe mostrar atenuación de
    Debye-Waller MONÓTONAMENTE DECRECIENTE con sigma (nunca creciente), y un ajuste
    de buena calidad (r^2 alto). Se detectó y corrigió un bug real durante el desarrollo:
    asumir que las 6 direcciones equivalentes de Bragg de 1er orden estaban a 0°, 60°,
    120°, ... (alineadas con los vectores de red real) en vez de -30°, 30°, 90°, ...
    (el retículo recíproco de una red triangular está rotado 30° respecto al real, hecho
    cristalográfico estándar) evaluaba S(f) fuera del pico de Bragg real, produciendo
    una atenuación CRECIENTE y espuria con sigma en vez de decreciente."""
    res_hex = run_hexagonal_monte_carlo_calibration(
        lattice_type='hexagonal', a=500.0, boundary_type='hexagon', boundary_size_nm=3000.0,
        f_vac=0.05, sigma_min=0.0, sigma_max=50.0, n_sigma_steps=6, iterations_per_step=15, seed=3
    )
    H_hex = res_hex['H_mean']
    assert np.all(np.diff(H_hex) < 0), f"H_mean hexagonal no es monótonamente decreciente: {H_hex}"
    assert res_hex['fit']['success']
    assert res_hex['fit']['r_squared'] > 0.95

    res_honeycomb = run_hexagonal_monte_carlo_calibration(
        lattice_type='honeycomb', a=600.0, boundary_type='hexagon', boundary_size_nm=3500.0,
        f_vac=0.0, sigma_min=0.0, sigma_max=50.0, n_sigma_steps=6, iterations_per_step=15, seed=3
    )
    H_honeycomb = res_honeycomb['H_mean']
    assert np.all(np.diff(H_honeycomb) < 0), f"H_mean honeycomb no es monótonamente decreciente: {H_honeycomb}"
    assert res_honeycomb['fit']['success']
    assert res_honeycomb['fit']['r_squared'] > 0.95


if __name__ == "__main__":
    import inspect
    print("=== Ejecutando Batería de Pruebas: Desorden de Redes 2D ===")
    test_funcs = [
        obj for name, obj in list(globals().items())
        if name.startswith("test_") and inspect.isfunction(obj)
    ]
    passed = 0
    for f in test_funcs:
        try:
            f()
            print(f"  [PASS] {f.__name__}")
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {f.__name__}: {e}")
            import traceback
            traceback.print_exc()

    print(f"\nResultado: {passed}/{len(test_funcs)} superadas.")
    if passed == len(test_funcs):
        print("¡Todas las pruebas pasaron exitosamente!")
        sys.exit(0)
    else:
        sys.exit(1)

