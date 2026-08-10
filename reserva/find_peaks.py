#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Jun 22 23:08:03 2025

@author: joseluis
"""

import numpy as np
import matplotlib.pyplot as plt
import tifffile
import os
from scipy.optimize import curve_fit

# ==========================
#   Funciones auxiliares
# ==========================

def gaussian_2d(xy, amplitude, xo, yo, sigma_x, sigma_y, theta, offset):
    x, y = xy
    a = (np.cos(theta)**2)/(2*sigma_x**2) + (np.sin(theta)**2)/(2*sigma_y**2)
    b = -(np.sin(2*theta))/(4*sigma_x**2) + (np.sin(2*theta))/(4*sigma_y**2)
    c = (np.sin(theta)**2)/(2*sigma_x**2) + (np.cos(theta)**2)/(2*sigma_y**2)
    return (offset + amplitude * np.exp(
        -(a*((x-xo)**2) + 2*b*(x-xo)*(y-yo) + c*((y-yo)**2))
    )).ravel()

def calculate_fwhm(sigma):
    return 2 * np.sqrt(2 * np.log(2)) * abs(sigma)

def fit_gaussian_to_image(image):
    y_coords, x_coords = np.indices(image.shape)
    xy_data = np.vstack((x_coords.ravel(), y_coords.ravel()))

    # Parámetros iniciales usando el máximo real
    max_idx = np.argmax(image)
    yo, xo = np.unravel_index(max_idx, image.shape)
    p0 = [image.max(), xo, yo, image.shape[1]/6, image.shape[0]/6, 0, image.min()]

    bounds = (
        [0, 0, 0, 0, 0, -np.pi, 0],
        [np.inf, image.shape[1], image.shape[0], np.inf, np.inf, np.pi, np.max(image)]
    )

    try:
        popt, _ = curve_fit(gaussian_2d, xy_data, image.ravel(), p0=p0, bounds=bounds)
    except (RuntimeError, ValueError):
        return None

    # Reconstruir imagen ajustada
    fit_image = gaussian_2d(xy_data, *popt).reshape(image.shape)
    residuals = image - fit_image

    # Calcular métricas
    N = image.size
    p = len(popt)
    RMS = np.sqrt(np.mean(residuals**2))
    chi_squared_reduced = np.sum(residuals**2) / (N - p)

    return popt, fit_image, residuals, RMS, chi_squared_reduced

def save_fit_plot(image, fit_image, residuals, save_path,xo,yo):
    fig, axs = plt.subplots(1, 3, figsize=(15, 5))

    axs[0].imshow(image, cmap='magma')
    axs[0].scatter(xo, yo, color='cyan', s=50, marker='x', label='Centro ajuste')
    axs[0].set_title("Imagen original")

    axs[1].imshow(fit_image, cmap='magma')
    axs[1].scatter(xo, yo, color='cyan', s=50, marker='x', label='Centro ajuste')
    axs[1].set_title("Ajuste gaussiano 2D")

    im = axs[2].imshow(residuals, cmap='bwr')
    axs[2].scatter(xo, yo, color='cyan', s=50, marker='x', label='Centro ajuste')
    axs[2].set_title("Mapa de residuales")
    fig.colorbar(im, ax=axs[2], fraction=0.046, pad=0.04)

    plt.tight_layout()
    plt.savefig(save_path, dpi=150)
    plt.close()

def process_scan(prefix):
    # Crear carpeta de imágenes procesadas
    output_dir = os.path.join("proc_img", prefix)
    os.makedirs(output_dir, exist_ok=True)

    output_file = f'proc_img/gaussfit_{prefix}.txt'
    with open(output_file, 'w') as f:
        f.write("File_Number\tMax_PosX\tMax_PosY\tFWHM_X\tFWHM_Y\tTheta\tRMS\tChi2\n")

        for i in range(1, 100):
            file_number = f"{i:03d}"
            image_path = f'{prefix}_{file_number}.tiff'

            if not os.path.exists(image_path):
                continue

            # Leer imagen
            try:
                image = tifffile.imread(image_path)
            except Exception as e:
                print(f"Error leyendo {image_path}: {e}")
                continue

            # Ajuste
            result = fit_gaussian_to_image(image)
            if result is None:
                continue

            popt, fit_image, residuals, RMS, chi2 = result
            amplitude, xo, yo, sigma_x, sigma_y, theta, offset = popt

            # Calcular FWHM
            fwhm_x = calculate_fwhm(sigma_x)
            fwhm_y = calculate_fwhm(sigma_y)

            # Guardar resultados en archivo
            f.write(f"{file_number}\t{xo:.2f}\t{yo:.2f}\t{fwhm_x:.2f}\t{fwhm_y:.2f}\t{theta:.4f}\t{RMS:.3f}\t{chi2:.3f}\n")

            # Guardar imagen de ajuste
            save_path = os.path.join(output_dir, f"{prefix}_{file_number}_fit.png")
            save_fit_plot(image, fit_image, residuals, save_path,xo,yo)

    print(f"Resultados guardados en {output_file} y figuras en {output_dir}/")

# ==========================
#      Ejecutar script
# ==========================

prefixes = ['NPscan', 'back_NPscan', 'gone_NPscan']
for prefix in prefixes:
    process_scan(prefix)




