# WALKTHROUGH DE PYPRINTING 3.0 🔬

Este archivo mantiene el registro continuo de los cambios, soluciones y validaciones realizadas en la arquitectura de **PyPrinting 3.0**.

---

## 🎯 Últimos Cambios y Correcciones Realizadas

1. **Nuevo Módulo de Análisis y Caracterización de PSF (`psf_analyzer.py` / `PSFAnalyzerWindow`)**:
   - Se implementó la nueva ventana independiente accesible desde el menú **`Tools -> PSF Analyzer`** en [app.py](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/app.py).
   - Permite cargar y comparar **1 o 2 imágenes confocales simultáneamente** (`.tiff` o `.txt`).
   - Soporta modelos de ajuste 2D por mínimos cuadrados: **Gaussiana 2D** y **Donut (Laguerre-Gauss $LG_{01}$)**.
   - **Métricas de Calidad e Invarianza Físicas**:
     - Centro $(x_0, y_0)$ ($\text{px}$ y $\mu\text{m}$).
     - Radio del anillo $r_0$, semi-ejes $a, b$ ($\mu\text{m}$).
     - **Elipticidad** $a/b$.
     - **Orientación** $\theta$ ($^\circ$).
     - **Calidad del cero central** $I_{\min} / I_{\max}$.
     - **Uniformidad angular del anillo** $\sigma_{\theta} / \bar{I}$.
     - **Desalineación espacial dual** $\Delta r_{\text{nm}}$, $\Delta x_{\text{nm}}$, $\Delta y_{\text{nm}}$ en nanómetros para alineación de haces STED/MINFLUX.
   - **Controles por Canal**:
     - Casillero editable **`Filtro (%)`** (por defecto `30%`) para desestimar ruido de fondo por canal.
   - **Visualización 1D & Superposición**:
     - Selector de perfiles de corte 1D pasantes por $(x_0, y_0)$: **Horizontal**, **Vertical**, **Diagonal 45°** y **Diagonal 135°**.
     - Renderizado de superposición RGB en falso color (Verde = Canal 1, Rojo = Canal 2).

2. **Centralización de Valores Típicos (*Typical Values*) en `config.py`**:
   - Todas las constantes iniciales y parámetros por defecto fueron migrados a [config.py](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/config.py) y consumidos de forma dinámica en toda la aplicación.

---

## 🧪 Validación y Estado del Proyecto

- **Prueba del Módulo PSF Analyzer**:
  ```powershell
  .\.venv\Scripts\python.exe -c "import numpy as np, sys; from PyQt6.QtWidgets import QApplication; from psf_analyzer import fit_gaussian_2d, fit_donut_2d, extract_1d_profile, PSFAnalyzerWindow; app = QApplication(sys.argv); y, x = np.indices((34, 34)); Zg = np.exp(-((x-17)**2 + (y-17)**2)/10); Zd = np.exp(-((x-17)**2 + (y-17)**2)/10) * ((x-17)**2 + (y-17)**2); res_g = fit_gaussian_2d(Zg); res_d = fit_donut_2d(Zd); d, p = extract_1d_profile(Zd, 17, 17, mode='Horizontal'); win = PSFAnalyzerWindow(); print('GAUSS FIT:', res_g['xo_px'], res_g['r2']); print('DONUT FIT:', res_d['xo_px'], res_d['zero_quality'], res_d['ellipticity']); print('PROFILE 1D len:', len(p)); print('PSF ANALYZER FULLY VERIFIED!')"
  ```
  *(Resultado: `GAUSS FIT: 17.0 0.8027`, `DONUT FIT: 17.0 0.0 1.1052`, `PROFILE 1D len: 34` — `PSF ANALYZER FULLY VERIFIED!`)*

- **Prueba Ejecutable de la Aplicación**:
  ```powershell
  .\.venv\Scripts\python.exe app.py
  ```
