#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Aug 12 09:57:17 2025

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

# ==========================================================
# CONFIGURACIONES
# ==========================================================
pixel_size_um = 0.05  # tamaño de pixel en micrómetros

os.makedirs('locs', exist_ok=True)
os.makedirs('img', exist_ok=True)

image_paths = ['ultimas_450/10x10_1_50nm_px.tiff','ultimas_450/10x10_2_50nm_px.tiff',
               'ultimas_450/20x20_1_50nm_px.tiff','ultimas_450/20x20_2_50nm_px.tiff',
               'ultimas_450/30x30_50nm_px.tiff']
  
names = ['a=450_N=10_50_nm_px_ult','a=450_N=10_50_nm_px_ult_2','a=450_N=20_50_nm_px_ult',
         'a=450_N=20_50_nm_px_ult_2','a=450_N=30_50_nm_px_ult']

esp=[10,10,20,20,30,30]


diameters = [5,5,5,5,9]

camera_info = {
    "Baseline": 100,
    "Gain": 1.0,
    "Sensitivity": 1.0
}

# ==========================================================
# FUNCIONES
# ==========================================================

def auto_parameters(image, name=""):
    """Visualiza el gradiente neto (Laplaciano de Gauss) de la primera imagen."""
    frame = image[0].astype(np.float32)
    lap = gaussian_laplace(frame, sigma=1)
    ng = np.abs(lap)

    fig, ax = plt.subplots(figsize=(12, 12))
    im = ax.imshow(ng, cmap="magma", origin='lower')
    ax.set_title(f"Gradiente neto (|Laplaciano|) - {name}")
    ax.axis("off")
    
    # Barra de escala
    scalebar = ScaleBar(pixel_size_um, units="µm", location='lower right', frameon=False, color='white')
    ax.add_artist(scalebar)
    
    plt.tight_layout()
    plt.show()

# ==========================================================
# PROCESAMIENTO PRINCIPAL
# ==========================================================
localization_summary = []
for i in range(len(image_paths)):
    try:
        # Leer imagen TIFF
        image_stack = tifffile.imread(image_paths[i])
        ny, nx = image_stack.shape
        
        # Recorte de bordes
        crop_pixels = 1
        cropped_image = image_stack[crop_pixels:ny - crop_pixels, crop_pixels:nx - crop_pixels]
        image = cropped_image[np.newaxis, 3:, :]
        
        print(f"Original image shape: {image_stack.shape}")
        print(f"Cropped image shape: {cropped_image.shape}")
        
        # Mostrar imagen recortada (sin bordes ni labels)
        fig, ax = plt.subplots(figsize=(5, 5))
        im = ax.imshow(cropped_image, cmap='afmhot', origin='lower')
        ax.set_title(f'Imagen recortada - {image_paths[i]}')
        ax.axis("off")
        scalebar = ScaleBar(pixel_size_um, units="µm", location='lower right', frameon=False, color='white')
        ax.add_artist(scalebar)
        plt.tight_layout()
        plt.show()
        
        # Análisis automático de parámetros
        auto_parameters(image, name=names[i])
        
        # Parámetros de localización
        parameters = {
            "Min. Net Gradient": 0.5,
            "Box Size": diameters[i]
        }
        print(parameters)
        
        # Localización
        df_localizations = localize.localize(image, camera_info, parameters)
        print(f"→ {len(df_localizations)} localizaciones encontradas.")
        
        num_locs = len(df_localizations)
        print(f"→ {num_locs} localizaciones encontradas.")
        
        current_esp = esp[i]
        if current_esp == 0:
            print(f"ADVERTENCIA: esp[{i}] es cero. Densidad no se puede calcular.")
            density = np.nan # Usar 'Not a Number'
        else:
            density = num_locs / (current_esp**2)
        
        # Añadir los datos a nuestra lista de resumen
        localization_summary.append({
            'nombre_archivo': names[i],
            'num_localizaciones': num_locs,
            'locs_div_esp2': density
        })
        
        # Guardar resultados CSV
        output_name = os.path.splitext(image_paths[i])[0] + '_locs.csv'
        df = pd.DataFrame(df_localizations)
        df.to_csv(f'locs/{names[i]}_picasso.csv', index=False)
        print(f"✔ Guardado: {output_name}")
        
        # Mostrar imagen con localizaciones
        fig, ax = plt.subplots(figsize=(3, 3))
        im = ax.imshow(image[0], cmap='afmhot', origin='lower')
        ax.scatter(df_localizations['x'], df_localizations['y'], s=2, c='cyan', marker='v')
        
        # Barra de escala
        scalebar = ScaleBar(pixel_size_um, units="µm", location='lower right', frameon=False, color='white')
        ax.add_artist(scalebar)
        
        # Sin bordes ni labels
        #ax.set_title(f'Locs - {names[i]}')
        ax.axis("off")
        
        plt.tight_layout()
        plt.savefig(f'img/locs_picasso_{names[i]}.png', dpi=600, bbox_inches='tight')
        plt.show()

    except FileNotFoundError:
        print(f"❌ Archivo no encontrado: {image_paths[i]}")


print("\n==========================================================")
print("PROCESAMIENTO COMPLETO")
print("==========================================================")
print("\nGenerando archivo de resumen de localizaciones...")

try:
    # Convertir la lista de diccionarios en un DataFrame
    summary_df = pd.DataFrame.from_records(localization_summary)
    
    # Definir la ruta del archivo de salida
    summary_output_path = os.path.join('locs', 'resumen_localizaciones.txt')
    
    # Guardar como archivo de texto separado por tabuladores (más legible)
    summary_df.to_csv(summary_output_path, index=False, sep='\t', float_format='%.4f')
    
    print(f"✔ Resumen guardado exitosamente en: {summary_output_path}")
    print("\nContenido del resumen:")
    print(summary_df)

except Exception as e:
    print(e)

