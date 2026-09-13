#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Mar 19 17:39:51 2026

@author: joseluis
"""

from scipy.optimize import curve_fit
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
import pandas as pd
from scipy.ndimage import gaussian_filter
from scipy.signal import find_peaks
from tqdm import tqdm
from joblib import Parallel, delayed
from scipy.spatial import cKDTree
import seaborn as sns
from matplotlib_scalebar.scalebar import ScaleBar
import os

# --- CONFIGURACIÓN DE ESTILO TIPO ARTÍCULO ---
plt.rcParams.update({
    'font.family': 'sans-serif',
    'font.sans-serif': ['DejaVu Sans', 'Arial', 'Liberation Sans'],
    'font.size': 8,
    'axes.labelsize': 8,
    'xtick.labelsize': 8,
    'ytick.labelsize': 8,
    'legend.fontsize': 8,
    'axes.linewidth' : 0.8,
    'xtick.major.size' : 2.5,
    'xtick.major.width' : 0.8,
    'ytick.major.size' : 2.5,
    'ytick.major.width' : 0.8,
    'figure.dpi': 150,
    'savefig.dpi': 300 
})

def gaussian(x, A, x0, sigma, offset):
    return A * np.exp(-0.5 * ((x - x0) / sigma)**2) + offset

def not_gaussian(x,A,q,off):
    return A * np.exp(-0.5*(np.abs(q)**2)*(x**2))+off

def _find_rotation_angle(logP_viz, cy, cx):
    """Encuentra el ángulo del pico más brillante fuera del centro."""
    logP_masked = np.copy(logP_viz)
    mask_size = 10 
    logP_masked[cy - mask_size : cy + mask_size, cx - mask_size : cx + mask_size] = 0
    (py, px) = np.unravel_index(np.argmax(logP_masked), logP_masked.shape)
    theta_rad = np.arctan2(py - cy, px - cx)
    theta_deg = np.rad2deg(theta_rad)
    return theta_rad, theta_deg, (px, py)

def _rotate_coordinates(data_df, angle_rad):
    """Rota las coordenadas 'x' e 'y' en un DataFrame por 'angle_rad'."""
    cm_x = data_df['x'].mean()
    cm_y = data_df['y'].mean()
    x_c = data_df['x'] - cm_x
    y_c = data_df['y'] - cm_y
    cos_t = np.cos(angle_rad)
    sin_t = np.sin(angle_rad)
    x_rot = (x_c * cos_t) - (y_c * sin_t) + cm_x
    y_rot = (x_c * sin_t) + (y_c * cos_t) + cm_y
    return pd.DataFrame({'x': x_rot, 'y': y_rot})

def _detect_and_fit(
    profile_analysis,  # Perfil para encontrar picos (logP_viz)
    profile_fit,       # Perfil para ajustar y reportar (P)
    freqs,
    center_idx,
    label,
    ax_plot,
    fft_peak_distance,
    fft_fit_window,
    fft_plot_xlim):
    """
    Función interna para detectar, ajustar y graficar picos.
    """
    results = []

    # --- Detección de picos en el perfil de ANÁLISIS (logP_viz) ---
    peaks, _ = find_peaks(profile_analysis, height=np.median(profile_analysis) * 1.5, distance=fft_peak_distance)
    peaks = [p for p in peaks if abs(p - center_idx) > 2]

    # --- Gráfico Principal (usando el perfil de ANÁLISIS, logP_viz) ---
    ax_plot.plot(freqs, profile_analysis, '-', linewidth=1.0, label=f'Profile {label}')
    ax_plot.plot(freqs[peaks], profile_analysis[peaks], 'ro', markersize=3, label=f'Peaks {label}')
    ax_plot.set_ylabel('Power [A.U]') 

    for p in peaks:
        win = fft_fit_window
        i0, i1 = max(0, p - win), min(len(freqs) - 1, p + win)
        xdata = freqs[i0:i1+1]
        ydata = profile_fit[i0:i1+1]

        if len(xdata) <= 4:
            continue

        # Parámetros iniciales (del perfil LINEAL)
        A0 = ydata.max() - ydata.min() if ydata.max() > ydata.min() else 1.0
        x00 = freqs[p]
        sigma0 = (xdata[-1] - xdata[0]) / 4 if len(xdata) > 1 else 0.1
        offset0 = np.median(ydata)

        try:
            # --- Ajuste sobre el perfil LINEAL (P) ---
            popt, _ = curve_fit(gaussian, xdata, ydata, p0=[A0, x00, sigma0, offset0],
                                bounds=([0, -np.inf, 0, -np.inf], np.inf))

            A, x0, sigma, offset = popt
            fwhm = 2 * np.sqrt(2 * np.log(2)) * abs(sigma)
            xi = 1 / (2 * np.pi * fwhm) if fwhm > 0 else np.inf
            a_nm = 1 / abs(x0) if x0 != 0 else np.inf
            peak_height_linear = profile_fit[p]

            results.append({
                'label': label,
                'pixel_pos': p,
                'freq_cyc_per_nm': x0,
                'a_nm': a_nm,
                'peak': peak_height_linear,
                'FWHM_cyc_per_nm': fwhm,
                'xi_nm': xi,
                'A': A,
                'sigma': sigma,
                'offset': offset
            })

            # Graficar ajuste transformado a log para visualización
            x_fit_main = np.linspace(xdata.min(), xdata.max(), 100)
            y_fit_log = np.log10(1 + gaussian(x_fit_main, *popt))
            ax_plot.plot(x_fit_main, y_fit_log, '--', linewidth=0.8, alpha=0.8)

        except (RuntimeError, ValueError) as e:
            pass

    ax_plot.set_xlabel(f'Frecuency {label} (nm$^{-1}$)')
    ax_plot.ticklabel_format(style='sci', axis='both',scilimits=(0, 0))
    ax_plot.legend(fontsize=6, frameon=False)
    ax_plot.grid(True, linestyle=':', alpha=0.6)
    return results, peaks

def _detect_and_fit_combo(profile_fit, profile_fit1, freqs, center_idx, label, ax_plot, fft_peak_distance, fft_fit_window, fft_plot_xlim,analysis_dir=None):
    """Detecta, ajusta y grafica picos combinados."""
    ticks = [1/500, 1/450, 1/400]
    labels = [
    r"$\frac{1}{500}$",
    r"$\frac{1}{450}$",
    r"$\frac{1}{400}$"
    ]
    peaks, _ = find_peaks(profile_fit, height=np.median(profile_fit) * 1.2, distance=fft_peak_distance)
    peaks = [p for p in peaks if abs(p - center_idx) > 1]
    
    # Forzar estilo manual sobre seaborn para respetar rcParams
    ax_plot.plot(freqs, profile_fit, '-', linewidth=1, label='X (log)')
    ax_plot.plot(freqs, profile_fit1, '-', linewidth=1, alpha=0.7, label='Y (log)')
    
    ax_plot.set_xlabel(r'Spatial Frecuency $[nm]^{-1}$')
    ax_plot.set_xlim(0.0014,0.0028)
    ax_plot.set_ylim(0,profile_fit[peaks].max()+1000)
    ax_plot.ticklabel_format(style='sci', axis='y', scilimits=(0,0))
    ax_plot.set_ylabel('Power [u.a]')
    ax_plot.set_xticks(ticks, labels)
    #sns.despine(ax=ax_plot)
    #ax_plot.legend(frameon=False)
    plt.savefig(os.path.join(analysis_dir, 'xyFourierPeaks_1.5x1.5_red.svg'))
    plt.show()

def analizar_red_de_particulas_fin_1(file_path, dx_nm, N, a_nm, sigma_nm, w_size_px, **kwargs):
    """Wrapper para mantener compatibilidad."""
    return analizar_red_de_particulas_fin_2(file_path, dx_nm, N, a_nm, sigma_nm, w_size_px, 
                                            savedir=".", auto_rotate_threshold_deg=None, **kwargs)

def analizar_red_de_particulas_fin_2(
    file_path: str,
    dx_nm: float,
    N: int,
    a_nm: float,
    sigma_nm: float,
    w_size_px: int,
    savedir,
    delimiter: str = ',',
    fft_peak_distance: int = 10,
    fft_fit_window: int = 5,
    fft_plot_xlim: tuple = (0.0015, 0.0025),
    auto_rotate_threshold_deg: float = 1.0
):
    print(f"--- Iniciando Análisis para: {os.path.basename(file_path)} ---")
    
    # Crear estructura de carpetas
    analysis_dir = os.path.join(savedir, "Analysis")
    zooms_dir = os.path.join(savedir, "Zooms")
    os.makedirs(analysis_dir, exist_ok=True)
    os.makedirs(zooms_dir, exist_ok=True)

    # 1. Cargar Datos
    try:
        data_original = pd.read_csv(file_path, delimiter=delimiter)
    except Exception as e:
        print(f"Error al leer el archivo: {e}")
        return None, 0, 0
        
    data = data_original.copy()
    data["x"] = data["x"] - data["x"].min()
    data["y"] = data["y"] - data["y"].min()
    coords_px_pre = data[['x','y']].values

    # 2. Pre-Análisis de Rotación
    img_size_pre = int(np.ceil(coords_px_pre.max()) + 100)
    img_pre = build_image(coords_px_pre, sigma_nm/dx_nm, sf=50, img_size=img_size_pre)
    
    
    # Recorte seguro para FFT
    cm_pre = int(img_size_pre // 2) # Aprox
    b_l = max(0, cm_pre - w_size_px//2)
    b_r = min(img_size_pre, cm_pre + w_size_px//2)
    crop_pre = img_pre[b_l:b_r, b_l:b_r]
    
    if crop_pre.shape[0] != w_size_px: crop_pre = img_pre

    logP_pre = np.log10(1 + np.abs(np.fft.fftshift(np.fft.fft2(crop_pre)))**2)
    cy_pre, cx_pre = np.array(logP_pre.shape) // 2

    data_final = data_original.copy()
    if auto_rotate_threshold_deg is not None:
        theta_rad, theta_deg, _ = _find_rotation_angle(logP_pre, cy_pre, cx_pre)
        if abs(theta_deg) > auto_rotate_threshold_deg:
            print(f"Rotación detectada: {theta_deg:.2f}°. Corrigiendo...")
            data_final = _rotate_coordinates(data_original, -theta_rad)
    
    # 4. Procesamiento Final
    data = data_final
    coords_px = data[['x','y']].values
    coords_px = coords_px - coords_px.min(axis=0) # Re-centrar a 0,0
    coords_nm = coords_px * dx_nm

    # KDTree
    x_grid, y_grid = np.meshgrid(np.arange(N) * a_nm, np.arange(N) * a_nm)
    tree = cKDTree(coords_nm)
    dist, _ = tree.query(np.column_stack([x_grid.ravel(), y_grid.ravel()]), k=1)
    sigma_posicional_nm = np.std(dist)

    # Generar Imagen Final Centrada
    sf = (w_size_px / 2) - coords_px.mean(axis=0)
    img_final = build_image(coords_px, sigma_nm/dx_nm, sf=sf[0], img_size=w_size_px)
    
    plt.figure(figsize=(6, 6))
    plt.imshow(img_final, cmap="inferno", origin="lower")
    plt.title(f"Imagen Gaussiana (sigma={sigma_nm} nm)")
    plt.grid(True)
    plt.show()
    
    # FFT Final
    P = np.abs(np.fft.fftshift(np.fft.fft2(img_final)))**2
    logP_viz = np.log10(1 + P)
    ny, nx = P.shape
    cy, cx = ny // 2, nx // 2
    
    freq_x = np.fft.fftshift(np.fft.fftfreq(nx, d=dx_nm))
    freq_y = np.fft.fftshift(np.fft.fftfreq(ny, d=dx_nm))
    
    # =========================================================
    # NUEVO: Guardar perfiles de intensidad de la FFT (Experimental)
    # =========================================================
    # --- Perfil X: Fila horizontal central (cy) ---
    plt.figure(figsize=(2.5,2))
    plt.plot(freq_x, np.log10(1 + P[cy, :]), color='blue', linewidth=1)
    plt.title('Perfil X (Experimental)', fontsize=10)
    plt.xlabel('Frecuencia ($nm^{-1}$)', fontsize=9)
    plt.ylabel('Intensidad Log(1+P)', fontsize=9)
    plt.xlim([0,0.005])
    plt.grid(True, linestyle='--', alpha=0.5)
    plt.tight_layout()
    
    # Guardar en la carpeta Analysis
    base_name_exp_x = os.path.join(analysis_dir, 'experimental_fft_profile_x')
    plt.savefig(f"{base_name_exp_x}.svg", format='svg', bbox_inches='tight')
    plt.savefig(f"{base_name_exp_x}.png", format='png', bbox_inches='tight', dpi=300)
    plt.close()
    
    # --- Perfil Y: Columna vertical central (cx) ---
    plt.figure(figsize=(2.5, 2))
    plt.plot(freq_y, np.log10(1 + P[:, cx]), color='red', linewidth=1)
    plt.title('Perfil Y (Experimental)', fontsize=10)
    plt.xlabel('Frecuencia ($nm^{-1}$)', fontsize=9)
    plt.ylabel('Intensidad Log(1+P)', fontsize=9)
    plt.xlim([0,0.005])
    plt.grid(True, linestyle='--', alpha=0.5)
    plt.tight_layout()
    
    # Guardar en la carpeta Analysis
    base_name_exp_y = os.path.join(analysis_dir, 'experimental_fft_profile_y')
    plt.savefig(f"{base_name_exp_y}.svg", format='svg', bbox_inches='tight')
    plt.savefig(f"{base_name_exp_y}.png", format='png', bbox_inches='tight', dpi=300)
    plt.close()
    
    
    
    # --- Perfil X: Fila horizontal central (cy) ---
    plt.figure(figsize=(2.5,1.5))
    plt.plot(freq_x,(P[cy, :]), color='blue', linewidth=1)
    plt.title('Perfil X (Experimental)', fontsize=10)
    plt.xlabel('Frecuencia ($nm^{-1}$)', fontsize=9)
    plt.ylabel('Intensidad Log(1+P)', fontsize=9)
    plt.xlim([0,0.005])
    plt.ylim([0,35000])
    plt.grid(True, linestyle='--', alpha=0.5)
    plt.tight_layout()
    
    # Guardar en la carpeta Analysis
    base_name_exp_x = os.path.join(analysis_dir, 'experimental_fft_profile_x_no_log')
    plt.savefig(f"{base_name_exp_x}.svg", format='svg', bbox_inches='tight')
    plt.savefig(f"{base_name_exp_x}.png", format='png', bbox_inches='tight', dpi=300)
    plt.close()
    
    # --- Perfil Y: Columna vertical central (cx) ---
    plt.figure(figsize=(2.5, 1.5))
    plt.plot(freq_y,(P[:, cx]), color='red', linewidth=1)
    plt.title('Perfil Y (Experimental)', fontsize=10)
    plt.xlabel('Frecuencia ($nm^{-1}$)', fontsize=9)
    plt.ylabel('Intensidad Log(1+P)', fontsize=9)
    plt.xlim([0,0.005])
    plt.ylim([0,35000])
    plt.grid(True, linestyle='--', alpha=0.5)
    plt.tight_layout()
    
    # Guardar en la carpeta Analysis
    base_name_exp_y = os.path.join(analysis_dir, 'experimental_fft_profile_y_no_log')
    plt.savefig(f"{base_name_exp_y}.svg", format='svg', bbox_inches='tight')
    plt.savefig(f"{base_name_exp_y}.png", format='png', bbox_inches='tight', dpi=300)
    plt.close()
    # =========================================================
    # ==========================================
    # GRÁFICA: ANÁLISIS COMPLETO
    # ==========================================
    fig = plt.figure(figsize=(5, 4))
    gs = fig.add_gridspec(2, 2)

    # 1. Imagen Real
    ax_img = fig.add_subplot(gs[0, 0])
    ax_img.imshow(img_final, cmap="cividis", origin="lower")
    #ax_img.set_title(f"Imagen (σ={sigma_posicional_nm:.1f} nm)")
    ax_img.axis("off")

    # 2. FFT Log
    ax_fft = fig.add_subplot(gs[0, 1])
    extent = [freq_x[0], freq_x[-1], freq_y[0], freq_y[-1]]
    ax_fft.imshow(logP_viz[cy-50:cy+50, cx-50:cx+50], cmap='inferno', origin='lower', extent=extent)
    #ax_fft.set_title("FFT (Log)")
    ax_fft.ticklabel_format(style='sci', axis='both',scilimits=(0, 0))
    ax_fft.set_xlabel(r'$f_x$ (nm$^{-1}$)')
    ax_fft.set_ylabel(r'$f_y$ (nm$^{-1}$)')

    # 3. Perfil X
    ax_prof_x = fig.add_subplot(gs[1, 0])
    results_x, _ = _detect_and_fit(logP_viz[cy, :], P[cy, :], freq_x, cx, 'X', ax_prof_x, fft_peak_distance, fft_fit_window, fft_plot_xlim)

    # 4. Perfil Y
    ax_prof_y = fig.add_subplot(gs[1, 1])
    results_y, _ = _detect_and_fit(logP_viz[:, cx], P[:, cx], freq_y, cy, 'Y', ax_prof_y, fft_peak_distance, fft_fit_window, fft_plot_xlim)

    plt.tight_layout()
    plt.savefig(os.path.join(analysis_dir, 'Analisis_Completo.svg'))
    plt.close(fig)

    # ==========================================
    # GRÁFICA: xyFourierPeaks.svg (Combo)
    # ==========================================
    fig_combo, ax_combo = plt.subplots(figsize=(1.8, 1.5),dpi=600)
    _detect_and_fit_combo(P[cy, :], P[:, cx], freq_x, cx, 'Combo', ax_combo, fft_peak_distance, fft_fit_window, fft_plot_xlim,analysis_dir=analysis_dir)
    #plt.savefig(os.path.join(analysis_dir, 'xyFourierPeaks_1.5x1.5.svg'))
    plt.close(fig_combo)

    # ==========================================
    # GRÁFICA: ZOOMS y xyFourierPeaksSpec (Overview)
    # ==========================================
    margin = 15
    peaks_info = []
    
    for r in results_x: peaks_info.append({'px': r['pixel_pos'], 'py': cy, 'lbl': f"X_{r['pixel_pos']}"})
    for r in results_y: peaks_info.append({'px': cx, 'py': r['pixel_pos'], 'lbl': f"Y_{r['pixel_pos']}"})

    # 1. Zooms Individuales
    for p in peaks_info:
        px, py = p['px'], p['py']
        y0, y1 = max(0, py - margin), min(ny, py + margin)
        x0, x1 = max(0, px - margin), min(nx, px + margin)
        
        zoom_img = logP_viz[y0:y1, x0:x1]
        
        plt.figure(figsize=(2, 2))
        plt.imshow(zoom_img, cmap='inferno', origin='lower')
        plt.axis('off')
        plt.title(f"{p['lbl']}", fontsize=6)
        plt.savefig(os.path.join(zooms_dir, f"Zoom_{p['lbl']}.svg"), bbox_inches='tight', dpi=600)
        plt.close()
        
    # 2. FFT General Sin Marcas (Nuevo Requerimiento)
    plt.figure(figsize=(6, 6))
    plt.imshow(logP_viz, cmap='inferno', origin='lower')
    plt.axis('off')
    plt.savefig(os.path.join(zooms_dir, "FFT_General_SinMarcas.svg"), bbox_inches='tight', pad_inches=0, dpi=600)
    plt.show()
    plt.close()
    
    # --- 2. Zoom Central ---
    # Usamos subplots para obtener 'fig' y 'ax' explícitamente
    fig, ax = plt.subplots(figsize=(2, 2))
    
    # Dibujar el recorte
    mapa='gray'
    ax.imshow(logP_viz[cy-50:cy+50, cx-50:cx+50], cmap=mapa, origin='lower')
    
    # A) Guardar versión SIN ejes (limpia)
    ax.axis('off')
    plt.savefig(os.path.join(zooms_dir, f"FFT_General_SinMarcas_zoom_100_borde_{mapa}.svg"), bbox_inches='tight', pad_inches=0.01, dpi=600)
    
    # B) Guardar versión CON ejes

    plt.savefig(os.path.join(zooms_dir, "FFT_General_SinMarcas_zoom_100_borde_{mapa}_axis.svg"), pad_inches=0.01, bbox_inches='tight', dpi=600)

    # C) Guardar versión CON Scalebar
    # Nota: Asegúrate de que el primer argumento (dx) sea correcto para tu calibración
    scalebar = ScaleBar((1/(w_size_px*0.05)), units="µm", location='lower right', frameon=False, color='white')
    ax.add_artist(scalebar)
    
    plt.savefig(os.path.join(zooms_dir, "FFT_General_SinMarcas_zoom_100_borde_inferno_axis_scalebar.svg"),  bbox_inches='tight', pad_inches=0.1, dpi=600)
    
    plt.show()
    plt.close()

    # 3. xyFourierPeaksSpec (Todos los picos señalados)
    fig_ov, ax_ov = plt.subplots(figsize=(6, 6))
    ax_ov.imshow(logP_viz, cmap='gray', origin='lower')
    ax_ov.set_title("Ubicación de Picos (Spec)")
    ax_ov.axis("off")
    
    for p in peaks_info:
        px, py = p['px'], p['py']
        rect = patches.Rectangle((px - margin, py - margin), 2*margin, 2*margin, 
                                 linewidth=1, edgecolor='cyan', facecolor='none')
        ax_ov.add_patch(rect)
        ax_ov.text(px, py+margin+2, p['lbl'].split('_')[0], color='cyan', fontsize=5, ha='center')

    plt.savefig(os.path.join(analysis_dir, "xyFourierPeaksSpec.svg"), dpi=600)
    plt.close(fig_ov)

    # Retorno
    df_results = pd.DataFrame(results_x + results_y)
    if not df_results.empty:
        df_results.to_csv(os.path.join(analysis_dir, "resultados_picos.csv"), index=False)
        print(f"Análisis completado. Gráficas guardadas en: {analysis_dir}")
    
    return df_results, sigma_posicional_nm, len(coords_nm)

def build_image(coords_px, spot_sigma_px, sf, img_size=None):
    if coords_px.size == 0:
        raise ValueError("No hay coordenadas para construir la imagen.")
    if img_size is None:
        img_size = int(np.ceil(coords_px.max() + 4*spot_sigma_px))
    
    # Vectorización para velocidad
    x = coords_px[:, 0] + sf
    y = coords_px[:, 1] + sf
    
    mask = (x >= 0) & (x < img_size) & (y >= 0) & (y < img_size)
    x = x[mask]
    y = y[mask]
    
    img, _, _ = np.histogram2d(y, x, bins=img_size, range=[[0, img_size], [0, img_size]])
    
    if spot_sigma_px > 0:
        img = gaussian_filter(img, sigma=spot_sigma_px)
    img=img/img.max()
    return img

def build_displacement_map(coords_k, coords_base, spot_sigma_px, sf, img_size=None):
    """
    Genera una imagen donde la intensidad de cada spot representa la magnitud 
    del desplazamiento (ruido) respecto a la red base.
    
    Requiere: coords_k (con ruido), coords_base (ideal)
    """
    if coords_k.size == 0:
        raise ValueError("No hay coordenadas para construir la imagen.")
        
    if img_size is None:
        img_size = int(np.ceil(coords_k.max() + 4*spot_sigma_px))

    # 1. Emparejamiento: Encontrar para cada punto k, su 'padre' en base
    # Usamos KDTree para encontrar el vecino más cercano en la red ideal
    tree = cKDTree(coords_base)
    # dists: distancia al vecino más cercano
    # idxs: índice del vecino en coords_base (no lo usamos aquí, pero es útil saberlo)
    dists, _ = tree.query(coords_k)
    
    # NOTA: 'dists' contiene la magnitud del error para cada partícula en coords_k

    # 2. Preparar coordenadas (igual que build_image)
    x = coords_k[:, 0] + sf
    y = coords_k[:, 1] + sf
    
    # 3. Filtrar dentro de la imagen
    mask = (x >= 0) & (x < img_size) & (y >= 0) & (y < img_size)
    x = x[mask]
    y = y[mask]
    weights = dists[mask]*50 # Solo usamos las distancias de los puntos visibles

    # 4. Crear histograma ponderado (Weighted Histogram)
    # Aquí está la magia: en vez de sumar 1 por partícula, sumamos su 'distancia'
    img_disp, _, _ = np.histogram2d(y, x, bins=img_size, 
                                    range=[[0, img_size], [0, img_size]], 
                                    weights=weights)
    
    # 5. Aplicar filtro gaussiano
    if spot_sigma_px > 0:
        img_disp = gaussian_filter(img_disp, sigma=spot_sigma_px)
        
    return img_disp

import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection

def plot_displacement_vectors(coords_k, coords_base, sf, img_size, save_path=None):
    """
    Genera un gráfico vectorial mostrando la red base, la red con ruido 
    y líneas conectando los puntos correspondientes.
    """
    if coords_k.size == 0:
        return

    # 1. Emparejamiento (KDTree)
    # Buscamos quién es el "padre" en coords_base de cada punto en coords_k
    tree = cKDTree(coords_base)
    dists, idxs = tree.query(coords_k)
    
    # Obtenemos las coordenadas base correspondientes a cada punto ruidoso
    matched_base = coords_base[idxs]

    # 2. Ajuste de coordenadas al espacio de la imagen (Shift Factor)
    # Para que coincida con las imágenes TIFF generadas
    k_shifted = coords_k + sf
    base_shifted = matched_base + sf

    # 3. Configurar el gráfico
    fig, ax = plt.subplots(figsize=(3, 3))
    
    # A) Dibujar puntos Base (Solo los que tienen correspondencia para no saturar)
    # Opcional: Graficar TODOS los base si quieres ver vacancias (usando coords_base + sf)
    ax.scatter(base_shifted[:, 0], base_shifted[:, 1], c='gray', marker='x', s=5, alpha=0.5, label='Base (Pristina)')
    
    # B) Dibujar puntos Con Ruido
    ax.scatter(k_shifted[:, 0], k_shifted[:, 1], c='blue', marker='.', s=5, alpha=0.7, label='Con Ruido')

    # C) Dibujar Líneas (Vectores)
    # Usamos LineCollection para eficiencia (mucho más rápido que un bucle for)
    # Formato de segmentos: lista de [(x1, y1), (x2, y2)]
    segments = np.column_stack((base_shifted, k_shifted)).reshape(-1, 2, 2)
    lc = LineCollection(segments, colors='red', linewidths=0.5, alpha=0.5)
    ax.add_collection(lc)

    # Decoración
    ax.set_xlim(0, img_size)
    ax.set_ylim(0, img_size)
    ax.set_aspect('equal')
    ax.invert_yaxis() # Para coincidir con coordenadas de imagen (origen arriba-izq) o quitar si origin='lower'
    ax.legend(loc='upper right')
    ax.set_title("Mapa de Desplazamiento Vectorial")
    
    if save_path:
        plt.savefig(save_path, dpi=600, bbox_inches='tight')
        plt.close()
    else:
        plt.show()

def add_noise_and_vacancies(coords_px, sigma_nm, frac_vac, rng, dx_nm):
    sigma_px = sigma_nm / dx_nm
    noisy = coords_px + rng.normal(scale=sigma_px, size=coords_px.shape)
    if frac_vac > 0:
        n_sites = noisy.shape[0]
        n_remove = int(round(n_sites * frac_vac))
        if n_remove > 0:
            idx_remove = rng.choice(n_sites, n_remove, replace=False)
            noisy = np.delete(noisy, idx_remove, axis=0)
    return noisy

def add_noise_and_vacancies_tracked(coords_px, sigma_nm, frac_vac, rng, dx_nm):
    sigma_px = sigma_nm / dx_nm
    
    # 1. Aplicar ruido a TODAS las coordenadas (correspondencia directa)
    noisy_full = coords_px + rng.normal(scale=sigma_px, size=coords_px.shape)
    
    # 2. Manejo de Vacancias
    n_sites = coords_px.shape[0]
    mask = np.ones(n_sites, dtype=bool) # Inicialmente todas existen (True)
    
    if frac_vac > 0:
        n_remove = int(round(n_sites * frac_vac))
        if n_remove > 0:
            idx_remove = rng.choice(n_sites, n_remove, replace=False)
            mask[idx_remove] = False # Marcamos las eliminadas
            
    # Retornamos las coordenadas filtradas Y la máscara para filtrar las originales después
    return noisy_full[mask], mask

def build_displacement_map_direct(coords_k, coords_base_surviving, spot_sigma_px, sf, img_size):
    """
    Crea el mapa de calor de error usando correspondencia directa.
    coords_k: Coordenadas con ruido (ya filtradas)
    coords_base_surviving: Coordenadas base (ya filtradas con la misma máscara)
    """
    if coords_k.size == 0: return None

    # 1. Calcular distancias (Vectorizado y directo)
    # Como los índices están alineados, la distancia es simplemente la norma de la resta
    dists = np.linalg.norm(coords_k - coords_base_surviving, axis=1)

    # 2. Coordenadas para la imagen (+ shift factor)
    x = coords_k[:, 0] + sf
    y = coords_k[:, 1] + sf
    
    # 3. Filtrar dentro de la imagen
    mask_bounds = (x >= 0) & (x < img_size) & (y >= 0) & (y < img_size)
    
    # 4. Histograma ponderado por 'dists'
    img_disp, _, _ = np.histogram2d(
        y[mask_bounds], x[mask_bounds], 
        bins=img_size, 
        range=[[0, img_size], [0, img_size]], 
        weights=dists[mask_bounds]*50 # <--- La intensidad es la distancia
    )
    
    if spot_sigma_px > 0:
        img_disp = gaussian_filter(img_disp, sigma=spot_sigma_px)
        
    return img_disp

def plot_displacement_vectors_direct(coords_k, coords_base_surviving, sf, img_size, save_path=None):
    """
    Grafica vectores de desplazamiento usando correspondencia directa.
    """
    if coords_k.size == 0: return

    # Ajustar coordenadas al espacio de imagen
    k_shifted = coords_k + sf
    base_shifted = coords_base_surviving + sf

    fig, ax = plt.subplots(figsize=(3, 3))
    
    # Puntos Base (Gris) y Reales (Azul)
    ax.scatter(base_shifted[:, 0], base_shifted[:, 1], c='gray', marker='x', s=3, alpha=0.5, label='Base')
    ax.scatter(k_shifted[:, 0], k_shifted[:, 1], c='blue', marker='.', s=3, alpha=0.7, label='Ruido')

    # Líneas (Directas index-to-index)
    segments = np.column_stack((base_shifted, k_shifted)).reshape(-1, 2, 2)
    lc = LineCollection(segments, colors='red', linewidths=0.5, alpha=0.5)
    ax.add_collection(lc)

    ax.set_xlim(0, img_size)
    ax.set_ylim(0, img_size)
    ax.set_aspect('equal')
    ax.invert_yaxis()
    ax.legend()
    ax.set_title("Desplazamiento Vectorial (Mapeo Directo)")
    
    if save_path:
        plt.savefig(save_path, dpi=600, bbox_inches='tight')
        plt.close()
    else:
        plt.show()

def detect_single_peak_and_fit(profile, freqs, target_f, label):
    results = {'label': label, 'A': np.nan, 'x0': np.nan, 'sigma': np.nan, 'offset': np.nan, 'H': np.nan}
    
    # 1. Encontrar índice teórico
    idx_target = np.argmin(np.abs(freqs - target_f))
    
    # 2. Definir ventana de búsqueda
    search_win = 15
    i0 = max(0, idx_target - search_win)
    i1 = min(len(freqs), idx_target + search_win)
    
    sub_profile = profile[i0:i1]
    sub_freqs = freqs[i0:i1]
    
    if len(sub_profile) < 5: return results
    
    # --- CORRECCIÓN: Enmascarar componente DC (frecuencia 0) ---
    # Ignoramos puntos donde la frecuencia sea prácticamente 0
    valid_mask = np.abs(sub_freqs) > 1e-6 
    
    if not np.any(valid_mask):
        return results # La ventana solo contenía el DC
        
    # Buscamos el máximo SOLO en las frecuencias válidas
    # Obtenemos el índice relativo dentro de los válidos, luego mapeamos al sub_profile
    valid_indices = np.where(valid_mask)[0]
    idx_max_valid = np.argmax(sub_profile[valid_mask])
    rel_idx_peak = valid_indices[idx_max_valid]
    
    idx_peak = i0 + rel_idx_peak
    # ------------------------------------------------------------
    
    results['H'] = profile[idx_peak]
    
    # 3. Ajuste Gaussiano (Fit)
    fit_win = 20
    fi0, fi1 = max(0, idx_peak - fit_win), min(len(freqs), idx_peak + fit_win)
    xdata, ydata = freqs[fi0:fi1], profile[fi0:fi1]
    
    if len(xdata) < 5: return results

    try:
        # Bounds para evitar ajustes negativos o absurdos
        # A > 0, x0 dentro del rango, sigma > 0
        p0 = [ydata.max()-ydata.min(), freqs[idx_peak], (xdata[-1]-xdata[0])/6, np.median(ydata)]
        bounds = ([0, xdata[0], 1e-6, -np.inf], [np.inf, xdata[-1], np.inf, np.inf])
        
        popt, _ = curve_fit(gaussian, xdata, ydata, p0=p0, bounds=bounds, maxfev=1000)
        results.update({'A': popt[0], 'x0': popt[1], 'sigma': popt[2], 'offset': popt[3]})
    except:
        pass
    
    return results

def run_iteration(k, sigma_noise_nm, coords_base, frac_vac, window_size, cx, cy, freq_x, freq_y, f0, dx_nm, spot_sigma_px, sf, save_path=None,save_path_1=None):
    rng = np.random.default_rng(seed=int(sigma_noise_nm * 1000) + k)
    coords_k, mask_surviving = add_noise_and_vacancies_tracked(coords_base, sigma_noise_nm, frac_vac, rng, dx_nm)
    coords_base_surviving = coords_base[mask_surviving]
    img = build_image(coords_k, spot_sigma_px, sf, img_size=window_size)
    
    if save_path:
        try:
            plt.imsave(save_path, img, cmap='gray')
        except: pass
    P = np.abs(np.fft.fftshift(np.fft.fft2(img)))**2
    if save_path_1:
        try:
            logP_viz = np.log10(1 + P)
            plt.figure(figsize=(3, 3))
            plt.imshow(logP_viz[cy-50:cy+50, cx-50:cx+50], cmap='afmhot', origin='lower')
            plt.axis('off')
            plt.savefig(os.path.join(save_path_1, f'sim_sigma_fft_{sigma_noise_nm}nm.svg'), bbox_inches='tight',pad_inches=0.1, dpi=600)
            plt.savefig(os.path.join(save_path_1, f'sim_sigma_fft_{sigma_noise_nm}nm.png'), bbox_inches='tight',pad_inches=0.1, dpi=600)

            plt.close()
            
            # =========================================================
            # NUEVO: Guardar perfiles de intensidad de la FFT como PLOTS (3x3 in)
            # =========================================================
            # --- Perfil X: Fila horizontal central (cy) ---
            plt.figure(figsize=(2.5, 2))
            # Graficamos intensidad en log10 para que los picos sean visibles igual que en la imagen 2D
            plt.plot(freq_x, np.log10(1 + P[cy, :]), color='blue', linewidth=1)
            plt.xlim([0,0.005])
            plt.title(f'Perfil X (Noise: {sigma_noise_nm} nm)', fontsize=10)
            plt.xlabel('Frecuencia ($nm^{-1}$)', fontsize=9)
            plt.ylabel('Intensidad Log(1+P)', fontsize=9)
            plt.grid(True, linestyle='--', alpha=0.5)
            plt.tight_layout()
            
            # Guardar en SVG y PNG
            base_name_x = os.path.join(save_path_1, f'sim_sigma_fft_profile_x_{sigma_noise_nm}nm')
            plt.savefig(f"{base_name_x}.svg", format='svg', bbox_inches='tight')
            plt.savefig(f"{base_name_x}.png", format='png', bbox_inches='tight', dpi=600)
            plt.close()
            
            # --- Perfil Y: Columna vertical central (cx) ---
            plt.figure(figsize=(2.5, 2))
            plt.plot(freq_y, np.log10(1 + P[:, cx]), color='red', linewidth=1)
            plt.xlim([0,0.005])
            plt.title(f'Perfil Y (Noise: {sigma_noise_nm} nm)', fontsize=10)
            plt.xlabel('Frecuencia ($nm^{-1}$)', fontsize=9)
            plt.ylabel('Intensidad Log(1+P)', fontsize=9)
            plt.grid(True, linestyle='--', alpha=0.5)
            plt.tight_layout()
            
            # Guardar en SVG y PNG
            base_name_y = os.path.join(save_path_1, f'sim_sigma_fft_profile_y_{sigma_noise_nm}nm')
            plt.savefig(f"{base_name_y}.svg", format='svg', bbox_inches='tight')
            plt.savefig(f"{base_name_y}.png", format='png', bbox_inches='tight', dpi=600)
            plt.close()
            
            
            # --- Perfil X: Fila horizontal central (cy) ---
            plt.figure(figsize=(2.5, 2))
            # Graficamos intensidad en log10 para que los picos sean visibles igual que en la imagen 2D
            plt.plot(freq_x,(P[cy, :]), color='blue', linewidth=1)
            plt.xlim([0,0.005])
            plt.ylim([0,80000])
            plt.title(f'Perfil X (Noise: {sigma_noise_nm} nm)', fontsize=10)
            plt.xlabel('Frecuencia ($nm^{-1}$)', fontsize=9)
            plt.ylabel('Intensidad Log(1+P)', fontsize=9)
            plt.grid(True, linestyle='--', alpha=0.5)
            plt.tight_layout()
            
            # Guardar en SVG y PNG
            base_name_x = os.path.join(save_path_1, f'sim_sigma_fft_profile_x_no_log_{sigma_noise_nm}nm')
            plt.savefig(f"{base_name_x}.svg", format='svg', bbox_inches='tight')
            plt.savefig(f"{base_name_x}.png", format='png', bbox_inches='tight', dpi=600)
            plt.close()
            
            # --- Perfil Y: Columna vertical central (cx) ---
            plt.figure(figsize=(2.5, 2))
            plt.plot(freq_y, (P[:, cx]), color='red', linewidth=1)
            plt.xlim([0,0.005])
            plt.ylim([0,80000])
            plt.title(f'Perfil Y (Noise: {sigma_noise_nm} nm)', fontsize=10)
            plt.xlabel('Frecuencia ($nm^{-1}$)', fontsize=9)
            plt.ylabel('Intensidad Log(1+P)', fontsize=9)
            plt.grid(True, linestyle='--', alpha=0.5)
            plt.tight_layout()
            
            # Guardar en SVG y PNG
            base_name_y = os.path.join(save_path_1, f'sim_sigma_fft_profile_y_no_log_{sigma_noise_nm}nm')
            plt.savefig(f"{base_name_y}.svg", format='svg', bbox_inches='tight')
            plt.savefig(f"{base_name_y}.png", format='png', bbox_inches='tight', dpi=600)
            plt.close()
            # =========================================================
            
            img_disp = build_displacement_map_direct(coords_k, coords_base_surviving, spot_sigma_px, sf, img_size=window_size)
            
            plt.figure(figsize=(3, 3))
            # Usamos un colormap tipo 'jet' o 'inferno' donde:
            # Negro/Azul = Poco movimiento
            # Rojo/Amarillo = Mucho movimiento
            plt.imshow(img_disp, cmap='inferno', origin='lower')
            plt.colorbar(label='Desplazamiento (nm)')
            plt.axis('off')
            plt.title(f"Mapa de Error (Noise: {sigma_noise_nm} nm)")
            
            plt.savefig(os.path.join(save_path_1, f'disp_map_{sigma_noise_nm}nm.svg'), bbox_inches='tight', dpi=600)
            plt.savefig(os.path.join(save_path_1, f'disp_map_{sigma_noise_nm}nm.png'), bbox_inches='tight', dpi=600)
            plt.close()
            
            vec_filename = os.path.join(save_path_1, f'vector_map_{sigma_noise_nm}nm.svg')
            
            plot_displacement_vectors_direct(coords_k, coords_base_surviving, sf, window_size, vec_filename)
        except Exception as e: print(e)
        except: pass
    
    
    res_x = detect_single_peak_and_fit(P[cy, :], freq_x, f0, 'X')
    res_y = detect_single_peak_and_fit(P[:, cx], freq_y, f0, 'Y')
    return res_x, res_y

def simulacion(N, a_nm, frac_vac, window_size, slim=150, dx_nm=50.0, spot_sigma_nm=120.0, n_iter=50, n_jobs=-1, savedir="sim_output"):
    
    # Directorios de salida
    samples_dir = os.path.join(savedir, "Simulation_Samples")
    results_dir = os.path.join(savedir, "Simulation_Results")
    os.makedirs(samples_dir, exist_ok=True)
    os.makedirs(results_dir, exist_ok=True)

    sf = (window_size - (N-1)*a_nm/dx_nm)/2.0
    a_px = a_nm / dx_nm
    spot_sigma_px = spot_sigma_nm / dx_nm

    coords_base = np.array([[j * a_px, i * a_px] for i in range(N) for j in range(N)])
    
    # Pre-cálculo de frecuencias
    freq_axis = np.fft.fftshift(np.fft.fftfreq(window_size, d=dx_nm))
    cy = cx = window_size // 2
    f0 = 1.0 / a_nm
    
    sigmas_range = range(0, slim, 2)
    
    records = []
    print("--- Iniciando Simulación ---")

    for sigma_nm in tqdm(sigmas_range, desc="Simulando"):
        
        iter_args = []
        for k in range(n_iter):
            # --- MODIFICACIÓN CLAVE ---
            # Solo definimos path de guardado si es la primera iteración (k=0)
            # Esto genera 1 imagen representativa por cada nivel de sigma.
            s_path = None
            s_path_1 = None
            if k == 0:
                s_path = os.path.join(samples_dir, f"sim_sigma_{sigma_nm}nm.png")
                s_path_1=samples_dir
            
            iter_args.append((k, sigma_nm, coords_base, frac_vac, window_size, cx, cy, freq_axis, freq_axis, f0, dx_nm, spot_sigma_px, sf, s_path,s_path_1))

        results = Parallel(n_jobs=n_jobs)(delayed(run_iteration)(*args) for args in iter_args)

        # Procesar Resultados
        temp_data = {'X': [], 'Y': []}
        for rx, ry in results:
            temp_data['X'].append(rx)
            temp_data['Y'].append(ry)
        
        for label in ['X', 'Y']:
            df_iter = pd.DataFrame(temp_data[label])
            row = {'sigma_noise_nm': sigma_nm, 'label': label}
            
            for col in ['A', 'x0', 'sigma', 'offset', 'H']:
                vals = df_iter[col].dropna()
                if not vals.empty:
                    row[f'{col}_mean'] = vals.mean()
                    row[f'{col}_std'] = vals.std()
                else:
                    row[f'{col}_mean'] = np.nan
                    row[f'{col}_std'] = np.nan
            records.append(row)

    df_summary = pd.DataFrame(records)
    csv_path = os.path.join(results_dir, f"sim_params_a{a_nm}_N{N}.csv")
    df_summary.to_csv(csv_path, index=False)
    
    # Graficar Resumen
    params = ['x0', 'sigma', 'H']
    fig, axes = plt.subplots(2, 4, figsize=(9, 3), sharex=True)
    
    for j, p in enumerate(params):
        for i, lbl in enumerate(['X', 'Y']):
            m = df_summary['label'] == lbl
            ax = axes[i, j]
            ax.errorbar(df_summary.loc[m, 'sigma_noise_nm'], df_summary.loc[m, f'{p}_mean'], 
                        yerr=df_summary.loc[m, f'{p}_std'], fmt='o', ms=2, label=lbl)
            #ax.set_title(f'{lbl}: {p}')
            ax.grid(True, alpha=0.3)
            ax.ticklabel_format(style='sci', axis='y', scilimits=(0,0))
            if i == 1: ax.set_xlabel('Noise $\sigma$ (nm)')

    plt.tight_layout()
    plt.savefig(os.path.join(results_dir, "Simulation_Plots_1.svg"))
    plt.close()
    
    return df_summary

def det_sigma(df, a, A_x, A_y, savedir="."):
    
    # NUEVO: Guardar en carpeta 'sigma' en lugar de 'Calibration'
    sigma_dir = os.path.join(savedir, "sigma")
    os.makedirs(sigma_dir, exist_ok=True)
    
    A_obj = {"X": A_x, "Y": A_y}
    fit_results = {}

    for label, color in zip(["X", "Y"], ["tab:blue", "tab:red"]):
        mask = df["label"] == label
        xvals = df.loc[mask, "sigma_noise_nm"].values
        yvals = df.loc[mask, "H_mean"].values
        yerr  = df.loc[mask, "H_std"].values

        # Ajuste
        p0 = [yvals.max(),0, 50, yvals.min()]
        try:
            popt, _ = curve_fit(gaussian, xvals, yvals, p0=p0, maxfev=2000)
            x_fine = np.linspace(0, xvals.max(), 1000)
            y_fit = gaussian(x_fine, *popt)
            print(popt)
            
            idx = np.argmin(np.abs(y_fit - A_obj[label]))
            sigma_obj = x_fine[idx]
            
            # Derivada para error
            dH = (gaussian(sigma_obj+0.1, *popt) - gaussian(sigma_obj-0.1, *popt))/0.2
            dsigma = abs(np.mean(yerr)/dH) if dH != 0 else np.nan
            
            fit_results[label] = {"sigma_obj": sigma_obj, "dsigma": dsigma}

            # Plot
            plt.figure(figsize=(3, 2))
            plt.errorbar(xvals, yvals, yerr=yerr, fmt=".", color=color, alpha=0.3)
            plt.plot(x_fine, y_fit, "k-", lw=1)
            plt.axhline(A_obj[label], color="gray", ls="--")
            plt.axvline(sigma_obj, color="gray", ls="--")
            plt.plot(sigma_obj, A_obj[label], "ko", label=f"$\sigma$={sigma_obj:.1f} nm")
            
            plt.title(f"Atenuation {label} ")
            plt.ticklabel_format(style='sci', axis='y', scilimits=(0,0))
            plt.xlabel("$\sigma_{a}$ [nm]")
            plt.ylabel("Peak Amplitude [A.U] ")
            plt.legend(frameon=False)
            plt.tight_layout()
            plt.savefig(os.path.join(sigma_dir, f"Atenuacion_{label}.svg"), dpi=300)
            plt.show()
            plt.close()
            
        except Exception as e:
            print(f"Error en ajuste {label}: {e}")

    prom = np.mean([v['sigma_obj'] for v in fit_results.values()]) if fit_results else 0
    print(f"Sigma Promedio Estimado: {prom:.2f} nm")

    return prom, fit_results