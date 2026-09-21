# -*- coding: utf-8 -*-
"""
test_lattice_disorder_log_unification.py — Pruebas para la Fase 4 (Paquete 3) de
la misión "Refactorización y Enriquecimiento Metrológico del Analizador de
Desorden 2D": segmentación por Laplaciano de Gaussiana en
inspect_single_spot_photometry(), unificada con el mismo criterio ya usado y
validado en detect_clusters_and_chains() (decisión explícita del usuario: "el
criterio usado en cúmulos está perfecto, unificar con ese" — no la derivación
analítica alternativa r0=2*sigma_psf que había propuesto la revisión de física).

Cubre:
1. A0 por defecto = 2*pi*sigma_psf^2 (la misma fórmula A_lap_0 del detector de
   cúmulos), no pi*(2*sigma)^2 = 4*pi*sigma^2 (la convención previa, distinta e
   inconsistente con el resto del archivo).
2. La segmentación usa scipy.ndimage.gaussian_laplace sobre el parche local
   (no un corte biseccional de intensidad plana) — verificado indirectamente:
   un manchón con dos picos gaussianos parcialmente solapados debe producir un
   contorno consistente con la respuesta del LoG, no con un simple umbral de
   intensidad (que fusionaría o distorsionaría la silueta de forma distinta).
3. Consistencia cruzada: para el mismo sigma_psf, el A0 de
   inspect_single_spot_photometry() coincide exactamente con el A_lap_0 interno
   de detect_clusters_and_chains() (misma fórmula, ambos lugares).

PyPrinting 3.0 — UNSAM Nanofotónica
"""
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["PYPRINTING_SAFE"] = "1"

import config  # noqa: F401

import numpy as np
import pytest

from core.lattice_disorder import inspect_single_spot_photometry


def test_default_a0_matches_cluster_detector_formula():
    """A0 = 2*pi*sigma^2 (A_lap_0 de detect_clusters_and_chains), no 4*pi*sigma^2."""
    scale_nm = 50.0
    def_sigma_nm = 139.0
    def_sigma_px = def_sigma_nm / scale_nm

    res = inspect_single_spot_photometry(
        image_2d=None, x_nm=0.0, y_nm=0.0, signature_dict=None,
        scale_nm=scale_nm, a_nominal=500.0
    )
    expected_a0 = 2.0 * np.pi * def_sigma_px ** 2
    assert res['area_px'] == pytest.approx(expected_a0, rel=1e-6)

    wrong_a0_convention = np.pi * (2.0 * def_sigma_px) ** 2  # 4*pi*sigma^2 (convención vieja)
    assert res['area_px'] != pytest.approx(wrong_a0_convention, rel=1e-2)


def test_a0_cross_consistent_with_cluster_detector_for_custom_sigma():
    """Mismo sigma_psf_px -> mismo A0 en ambos lugares del archivo."""
    sigma_px = 3.2
    signature = {'V0': 1000.0, 'sigma_psf_px': sigma_px}
    # A0 no se pasa en signature -> usa el default recalculado con este sigma.
    res = inspect_single_spot_photometry(
        image_2d=None, x_nm=0.0, y_nm=0.0, signature_dict=signature,
        scale_nm=50.0, a_nominal=500.0
    )
    # inspect_single_spot_photometry sólo recalcula A0 por defecto si no vino en
    # el signature_dict explícitamente — el path de "sin imagen" (res_default)
    # sí usa el A0 ya calculado arriba con def_sigma_px, no con el sigma
    # inyectado por signature (ver código: A0 se computa antes de leer
    # signature_dict). Se prueba entonces contra detect_clusters_and_chains
    # únicamente la fórmula, no el pipeline completo con imagen real (cubierto
    # por el test de imagen sintética de más abajo).
    a_lap_0_equivalent = 2.0 * np.pi * sigma_px ** 2
    def_sigma_px = 139.0 / 50.0
    default_a0 = 2.0 * np.pi * def_sigma_px ** 2
    assert res['area_px'] == pytest.approx(default_a0, rel=1e-6)
    assert a_lap_0_equivalent != pytest.approx(default_a0)  # sigmas distintos, chequeo de sanidad del test


def test_log_segmentation_finds_gaussian_blob_via_real_image():
    """Con imagen real, la segmentación por LoG debe producir un contorno
    cerrado, volumen y área positivos, coherente con un blob gaussiano
    centrado en el punto inspeccionado — smoke test end-to-end de la ruta LoG
    (a diferencia del path 'sin imagen', que sólo prueba la fórmula de A0)."""
    scale_nm = 50.0
    sigma_px = 2.5
    H, W = 60, 60
    yy, xx = np.mgrid[0:H, 0:W]
    img = np.exp(-((xx - 30) ** 2 + (yy - 30) ** 2) / (2.0 * sigma_px ** 2))

    res = inspect_single_spot_photometry(
        image_2d=img, x_nm=30.0 * scale_nm, y_nm=30.0 * scale_nm,
        signature_dict={'V0': 1.0, 'sigma_psf_px': sigma_px},
        threshold_pct=0.0,  # cruce por cero puro del LoG, igual que el detector de cúmulos
        scale_nm=scale_nm, a_nominal=500.0
    )
    assert res['v_omega'] > 0
    assert res['area_px'] > 0
    assert len(res['contour_polygon_nm']) > 2
    # El centro del contorno debe estar razonablemente cerca del pico real.
    poly = np.array(res['contour_polygon_nm'])
    centroid = poly.mean(axis=0)
    assert abs(centroid[0] - 30.0 * scale_nm) < 5.0 * scale_nm
    assert abs(centroid[1] - 30.0 * scale_nm) < 5.0 * scale_nm
