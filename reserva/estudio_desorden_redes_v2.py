#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script Principal de Análisis y Simulación
Optimizado para modulos_sigma_v4 con Reporte TXT
"""

import os
import modulos_sigma_v7 as ms

# --- 1. Configuración de Parámetros ---
window_size = {
    '400_30x30': 260,
    '450_30x30': 300,
    '500_30x30': 320,
    '550_30x30': 360,
    '450_10x10': 100,
    '450_20x20': 205,
    '450_40x40': 405
}

# === INPUTS ===
MI_DX_NM = 50.0       # nm/pixel
MI_N_RED = 30         # Red de 30x30
MI_A_NM = 450.0       # Periodo esperado (400 nm)
MI_SIGMA_NM = 100.0   # Ancho de partícula (visualización)
MI_W_SIZE_PX = window_size[f'{int(MI_A_NM)}_{MI_N_RED}x{MI_N_RED}']  # Ventana FFT
TAG = 'ult_'

# Variable para observaciones manuales (puedes escribir aquí lo que quieras)
obs = '' 

# Configuración de Rutas
base_name = f'a={int(MI_A_NM)}_N={MI_N_RED}_{int(MI_DX_NM)}_nm_px_{TAG}'
file_input = f'{base_name}picasso.csv'

# Ajusta tus rutas locales aquí
BASE_DIR = '/Users/joseluis/Documents/articulo redes/codigo maestro'
file_path = os.path.join(BASE_DIR, 'locs', file_input)
savedir = os.path.join(BASE_DIR, 'results', base_name)

os.makedirs(savedir, exist_ok=True)

# --- 2. Análisis Experimental (FFT y Picos) ---
print(f"Procesando: {file_input}")

# NOTA: fft_plot_xlim ajustado a unidades de frecuencia (1/nm)
# Para 400nm, f = 0.0025. Usamos rango (0.001, 0.005)
df_fft, sigma_pos, n_counts = ms.analizar_red_de_particulas_fin_2(
    file_path=file_path,
    dx_nm=MI_DX_NM,
    N=MI_N_RED,
    a_nm=MI_A_NM,
    sigma_nm=MI_SIGMA_NM,
    w_size_px=MI_W_SIZE_PX,
    delimiter=',',
    fft_plot_xlim=(0.0, 0.006), 
    savedir=savedir
)

print("\n--- RESULTADOS EXPERIMENTALES ---")
print(f"Sigma posicional (KDTree): {sigma_pos:.2f} nm")

# Filtrar resultados
df_fft['diff'] = (df_fft['a_nm'] - MI_A_NM).abs()
indices_cercanos = df_fft.groupby('label')['diff'].idxmin()
resultado = df_fft.loc[indices_cercanos, ['label', 'a_nm', 'peak', 'A']]

# Cálculo de Vacancias
frac_vac = 1 - n_counts / (MI_N_RED**2)
print(f'Fracción de vacancias calculada: {frac_vac:.4f}')
print("Picos seleccionados:")
print(resultado)

try:
    target_peak_x = resultado.loc[resultado['label'] == 'X', 'peak'].values[0]
    target_peak_y = resultado.loc[resultado['label'] == 'Y', 'peak'].values[0]
    a_nm_mean = resultado['a_nm'].mean()
except IndexError:
    print("Error: No se detectaron picos en X o Y. Revisar datos.")
    target_peak_x = 0
    target_peak_y = 0
    a_nm_mean = MI_A_NM

# --- 3. Simulación (Barrido de Ruido) ---
print("\n--- INICIANDO SIMULACIÓN ---")
df_summary = ms.simulacion(
    N=MI_N_RED,
    a_nm=a_nm_mean,
    frac_vac=frac_vac,
    window_size=MI_W_SIZE_PX,
    slim=150,           
    dx_nm=MI_DX_NM,
    spot_sigma_nm=MI_SIGMA_NM,
    n_iter=10,          
    n_jobs=-1,
    savedir=savedir
)

# --- 4. Calibración (Determinación de Sigma Real) ---
print("\n--- DETERMINANDO SIGMA REAL ---")
prom_sigma, fit_results = ms.det_sigma(
    df=df_summary,
    a=a_nm_mean,
    A_x=target_peak_x,
    A_y=target_peak_y,
    savedir=savedir
)

# --- 5. Generación de Reporte (.txt) ---
print("\n--- GUARDANDO RESUMEN TXT ---")
txt_filename = "resumen_analisis.txt"
txt_path = os.path.join(savedir, txt_filename)

with open(txt_path, 'w', encoding='utf-8') as f:
    f.write("========================================\n")
    f.write(f"      REPORTE DE ANÁLISIS: {base_name}\n")
    f.write("========================================\n\n")
    
    # Observaciones
    if obs:
        f.write(f"OBSERVACIONES:\n{obs}\n\n")
    else:
        f.write("OBSERVACIONES:\n(Sin observaciones)\n\n")

    # Información General de la Red
    f.write("--- INFORMACIÓN DE LA RED ---\n")
    f.write(f"Archivo Origen: {file_input}\n")
    f.write(f"Dimensiones Red (N): {MI_N_RED}x{MI_N_RED}\n")
    f.write(f"Pixel Size (dx): {MI_DX_NM} nm\n")
    f.write(f"Window Size: {MI_W_SIZE_PX} px\n")
    f.write(f"Periodo Detectado (promedio): {a_nm_mean:.2f} nm\n")
    f.write(f"Vacancias Calculadas: {frac_vac*100:.2f}%\n")
    f.write(f"Partículas Detectadas: {n_counts}\n")
    f.write(f"Sigma Posicional (Directo KDTree): {sigma_pos:.2f} nm\n\n")

    # Resultados Experimentales (FFT)
    f.write("--- RESULTADOS FFT (EXPERIMENTAL) ---\n")
    # Formatear el dataframe como string alineado
    f.write(resultado.to_string(index=False))
    f.write("\n\n")

    # Resultados Finales (Calibración)
    f.write("--- RESULTADOS SIGMA REAL (SIMULACIÓN) ---\n")
    for label in fit_results:
        res = fit_results[label]
        sigma_val = res['sigma_obj']
        error_val = res['dsigma']
        f.write(f"Eje {label}: {sigma_val:.2f} ± {error_val:.2f} nm\n")
    
    f.write("-" * 30 + "\n")
    f.write(f"SIGMA PROMEDIO FINAL: {prom_sigma:.2f} nm\n")
    f.write("========================================\n")

print(f"Reporte guardado exitosamente en: {txt_path}")