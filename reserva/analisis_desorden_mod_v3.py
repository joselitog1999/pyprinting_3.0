#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Mar  9 14:36:16 2026

@author: joseluis
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import tifffile
from picasso import localize
from scipy.ndimage import gaussian_laplace
from matplotlib_scalebar.scalebar import ScaleBar
import trackpy as tp
from skimage import restoration

# ==========================================================
# CONFIGURACIONES
# ==========================================================
pixel_size_um = 0.05  # tamaño de pixel en micrómetros

base_locs_dir = 'locs'
base_img_dir = 'img'
os.makedirs(base_locs_dir, exist_ok=True)
os.makedirs(base_img_dir, exist_ok=True)

image_paths = ['ultimas_450/10x10_1_50nm_px.tiff','ultimas_450/10x10_2_50nm_px.tiff','ultimas_450/20x20_1_50nm_px.tiff','ultimas_450/20x20_2_50nm_px.tiff','40x40_450_verde.tiff']
names = ['a=450_N=10_50_nm_px_1','a=450_N=10_50_nm_px_2','a=450_N=20_50_nm_px_1','a=450_N=20_50_nm_px_2','a=450_N=40_50_nm_px']

esp = [30,30,30,30, 30]
diameters = [7,7,7,7,7]
rl=[15,15,15,15,15]

camera_info = {
    "Baseline": 100,
    "Gain": 1.0,
    "Sensitivity": 1.0
}
# --- NUEVA CONFIGURACIÓN: Selección de propiedades para el mapa de color ---
# Opciones comunes para Picasso: 'photons', 'net_gradient', 'likelihood', 'bg'
picasso_prop_to_map = 'photons'

# Opciones comunes para Trackpy: 'mass', 'size', 'ecc', 'signal', 'raw_mass'
trackpy_prop_to_map = 'mass'
# --------------------------------------------------------------------------

print('Iniciando el procesamiento general...')

# ==========================================================
# FUNCIONES AUXILIARES
# ==========================================================

def richardson_lucy_restoration(image_2d, psf_sigma=1.5, num_iter=15):
    """
    Función de restauración Richardson-Lucy. 
    """
    size = int(6 * psf_sigma)
    if size % 2 == 0:
        size += 1
    x = np.arange(-size//2 + 1, size//2 + 1)
    x, y = np.meshgrid(x, x)
    psf = np.exp(-(x**2 + y**2) / (2 * psf_sigma**2))
    psf /= psf.sum()
    
    img_float = image_2d.astype(float)
    img_min = img_float.min()
    img_float -= img_min
    img_max = img_float.max()
    if img_max > 0:
        img_float /= img_max
        
    restored = restoration.richardson_lucy(img_float, psf, num_iter=num_iter, clip=False)
    restored = (restored * img_max) + img_min
    return restored

def save_and_plot_locs(img_2d, df_locs, name, method, state, folder_img, folder_locs, x_col='x', y_col='y'):
    """
    Guarda las localizaciones en CSV y exporta la imagen estándar.
    """
    csv_path = os.path.join(folder_locs, f"{name}_{state}_{method}.csv")
    df_locs.to_csv(csv_path, index=False)
    
    fig, ax = plt.subplots(figsize=(4, 4))
    im = ax.imshow(img_2d, cmap='afmhot', origin='lower')
    
    if len(df_locs) > 0:
        ax.scatter(df_locs[x_col], df_locs[y_col], s=3, c='cyan', marker='v')
    
    scalebar = ScaleBar(pixel_size_um, units="µm", location='lower right', frameon=False, color='white')
    ax.add_artist(scalebar)
    ax.axis("off")
    plt.tight_layout()
    
    svg_path = os.path.join(folder_img, f"svgs/{name}_{state}_{method}.svg")
    png_path = os.path.join(folder_img, f"pngs/{name}_{state}_{method}.png")
    os.makedirs(os.path.join(folder_img, "svgs"), exist_ok=True)
    os.makedirs(os.path.join(folder_img, "pngs"), exist_ok=True)
    plt.savefig(svg_path, dpi=600, bbox_inches='tight')
    plt.savefig(png_path, dpi=600, bbox_inches='tight')
    plt.close()
    
    return len(df_locs)

def plot_property_map(img_2d, df_locs, name, method, state, folder_img, property_col, x_col='x', y_col='y'):
    """
    NUEVA FUNCIÓN: Grafica las detecciones con un mapa de color según una propiedad.
    Fondo: Escala de grises. Puntos: afmhot.
    """
    # Verificación de seguridad por si la propiedad no existe en el DataFrame
    if df_locs.empty or property_col not in df_locs.columns:
        print(f"    [!] Advertencia: La propiedad '{property_col}' no existe en los resultados de {method}. Saltando mapa de color.")
        return
        
    fig, ax = plt.subplots(figsize=(4.5, 4)) # Ligeramente más ancho para acomodar el colorbar
    
    # Imagen de fondo en escala de grises
    ax.imshow(img_2d, cmap='gray', origin='lower')
    
    # Scatter plot con colores mapeados a la propiedad elegida
    sc = ax.scatter(df_locs[x_col], df_locs[y_col], 
                    c=df_locs[property_col], cmap='afmhot', 
                    s=5, marker='o', alpha=0.9)
    
    # Añadir barra de color
    cbar = plt.colorbar(sc, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label(f'{property_col.capitalize()} ({method})', rotation=270, labelpad=15)
    
    scalebar = ScaleBar(pixel_size_um, units="µm", location='lower right', frameon=False, color='white')
    ax.add_artist(scalebar)
    ax.axis("off")
    plt.title(f"Mapa de {property_col}", fontsize=10)
    plt.tight_layout()
    
    # Guardar la imagen adicional
    svg_path = os.path.join(folder_img, f"svgs/{name}_{state}_{method}_mapa_{property_col}.svg")
    png_path = os.path.join(folder_img, f"pngs/{name}_{state}_{method}_mapa_{property_col}.png")
    os.makedirs(os.path.join(folder_img, "svgs"), exist_ok=True)
    os.makedirs(os.path.join(folder_img, "pngs"), exist_ok=True)
    plt.savefig(svg_path, dpi=600, bbox_inches='tight')
    plt.savefig(png_path, dpi=600, bbox_inches='tight')
    plt.close()

# ==========================================================
# PROCESAMIENTO PRINCIPAL
# ==========================================================
localization_summary = []

for i in range(len(image_paths)):
    print(f"\n--- Procesando {names[i]} ---")
    try:
        folder_img = os.path.join(base_img_dir, names[i])
        folder_locs = os.path.join(base_locs_dir, names[i])
        os.makedirs(folder_img, exist_ok=True)
        os.makedirs(folder_locs, exist_ok=True)
        
        image_stack = tifffile.imread(image_paths[i])

        image_2d_orig = image_stack[3:, :]  
        image_3d_orig = image_2d_orig[np.newaxis, :, :] 
        
        print("  -> Restaurando imagen (Richardson-Lucy)...")
        image_2d_rest = richardson_lucy_restoration(image_2d_orig, psf_sigma=1.5, num_iter=rl[i])
        image_3d_rest = image_2d_rest[np.newaxis, :, :]

        counts = {'Nombre_Muestra': names[i]}
        
        # --- A. ORIGINAL + PICASSO ---
        print("  -> Detectando: Picasso (Original)")
        picasso_params = {"Min. Net Gradient": 1, "Box Size": diameters[i]}
        locs_picasso_orig = pd.DataFrame(localize.localize(image_3d_orig, camera_info, picasso_params))
        
        if not locs_picasso_orig.empty:
            box_radius = diameters[i] // 2
            locs_picasso_orig['x'] = locs_picasso_orig['x'] - box_radius
            locs_picasso_orig['y'] = locs_picasso_orig['y'] - box_radius
            
        counts['Orig_Picasso'] = save_and_plot_locs(image_2d_orig, locs_picasso_orig, names[i], 'picasso', 'original', folder_img, folder_locs)
        plot_property_map(image_2d_orig, locs_picasso_orig, names[i], 'picasso', 'original', folder_img, picasso_prop_to_map)

        # --- B. ORIGINAL + TRACKPY ---
        print("  -> Detectando: Trackpy (Original)")
        locs_tp_orig = tp.locate(image_2d_orig, diameter=5, minmass=0) 
        counts['Orig_Trackpy'] = save_and_plot_locs(image_2d_orig, locs_tp_orig, names[i], 'trackpy', 'original', folder_img, folder_locs)
        plot_property_map(image_2d_orig, locs_tp_orig, names[i], 'trackpy', 'original', folder_img, trackpy_prop_to_map)

        # --- C. RESTAURADA + PICASSO ---
        print("  -> Detectando: Picasso (Restaurada)")
        locs_picasso_rest = pd.DataFrame(localize.localize(image_3d_rest, camera_info, picasso_params))
        
        if not locs_picasso_rest.empty:
            box_radius = diameters[i] // 2
            locs_picasso_rest['x'] = locs_picasso_rest['x'] - box_radius
            locs_picasso_rest['y'] = locs_picasso_rest['y'] - box_radius
            
        counts['Rest_Picasso'] = save_and_plot_locs(image_2d_rest, locs_picasso_rest, names[i], 'picasso', 'restaurada', folder_img, folder_locs)
        plot_property_map(image_2d_rest, locs_picasso_rest, names[i], 'picasso', 'restaurada', folder_img, picasso_prop_to_map)

        # --- D. RESTAURADA + TRACKPY ---
        print("  -> Detectando: Trackpy (Restaurada)")
        locs_tp_rest = tp.locate(image_2d_rest, diameter=5, minmass=0)
        counts['Rest_Trackpy'] = save_and_plot_locs(image_2d_rest, locs_tp_rest, names[i], 'trackpy', 'restaurada', folder_img, folder_locs)
        plot_property_map(image_2d_rest, locs_tp_rest, names[i], 'trackpy', 'restaurada', folder_img, trackpy_prop_to_map)

        localization_summary.append(counts)

    except FileNotFoundError:
        print(f"❌ Archivo no encontrado: {image_paths[i]}")
    except Exception as e:
        print(f"❌ Error procesando {names[i]}: {e}")

# ==========================================================
# RESUMEN COMPARATIVO FINAL
# ==========================================================
print("\n==========================================================")
print("PROCESAMIENTO COMPLETO")
print("==========================================================")

if localization_summary:
    summary_df = pd.DataFrame(localization_summary)
    summary_output_path = os.path.join(base_locs_dir, 'resumen_comparativo_localizaciones.txt')
    
    summary_df.to_csv(summary_output_path, index=False, sep='\t')
    
    print(f"✔ Resumen comparativo guardado exitosamente en: {summary_output_path}")
    print("\nResumen de localizaciones encontradas:")
    print(summary_df.to_string(index=False))
else:
    print("No se procesó ninguna imagen exitosamente.")