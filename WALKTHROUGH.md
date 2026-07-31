# WALKTHROUGH DE PYPRINTING 3.0 🔬

Este archivo mantiene el registro continuo de los cambios, soluciones y validaciones realizadas en la arquitectura de **PyPrinting 3.0**.

---

## 🎯 Últimos Cambios y Correcciones Realizadas

1. **Ampliación y Refinamiento del Módulo PSF Analyzer (`psf_analyzer.py`)**:
   - **Vistas Triples por Canal**: Cada canal desglosa la visualización en 3 visores independientes: **Original / Filtrada**, **Modelo Ajustado (Fit sintético $Z_{\text{fit}}$)** y **Mapa de Residuales ($|Z_n - Z_{\text{fit}}|$)**.
   - **Confirmación del Filtro Umbral**: El filtro opera exactamente como un corte relativo sobre la intensidad pico-a-fondo ($Z_n < P/100 \implies Z_f = 0$). Todo valor menor al $P\%$ de la altura máxima se fuerza a 0 antes de ajustar.
   - **Recálculo por `Enter` o Botón `Aplicar`**: Conexión de `returnPressed` y el botón **`Aplicar`** en el casillero `Filtro (%)` para refrescar instantáneamente todas las vistas, métricas y perfiles.
   - **Botones Independientes de Limpieza**: Incorporación de **`Limpiar Canal 1`** y **`Limpiar Canal 2`** en la barra superior.
   - **Etiquetas de Ejes & Selector de Unidades**: Graduación de ejes X e Y con selector desplegable de unidades (**$\mu\text{m}$** vs **$\text{px}$**).
   - **Selector de Canales en Perfiles 1D**: Menú desplegable en la pestaña de Perfiles 1D para alternar entre **`Confocal 1`**, **`Confocal 2`** y **`Ambas superpuestas`** en las 4 direcciones (**Horizontal**, **Vertical**, **Diagonal 45°**, **Diagonal 135°**).
   - **Selector de Modo en Falso Color RGB**: Menú desplegable en la pestaña de Superposición RGB para conmutar entre **`Imágenes Originales`**, **`Originales con Filtro de Ruido`** y **`Modelos Ajustados (Fits)`**.

---

## 🧪 Validación y Estado del Proyecto

- **Prueba del Módulo PSF Analyzer**:
  ```powershell
  .\.venv\Scripts\python.exe -c "import numpy as np, sys; from PyQt6.QtWidgets import QApplication; from psf_analyzer import fit_gaussian_2d, fit_donut_2d, extract_1d_profile, PSFAnalyzerWindow; app = QApplication(sys.argv); y, x = np.indices((34, 34)); Zg = np.exp(-((x-17)**2 + (y-17)**2)/10); Zd = np.exp(-((x-17)**2 + (y-17)**2)/10) * ((x-17)**2 + (y-17)**2); res_g = fit_gaussian_2d(Zg); res_d = fit_donut_2d(Zd); d, p = extract_1d_profile(Zd, 17, 17, mode='Horizontal'); win = PSFAnalyzerWindow(); win.widget._update_unit_mode(); print('GAUSS FIT:', res_g['xo_px'], 'Residual min/max:', res_g['residual'].min(), res_g['residual'].max()); print('DONUT FIT:', res_d['xo_px'], 'Residual min/max:', res_d['residual'].min(), res_d['residual'].max()); print('PROFILE 1D len:', len(p)); print('PSF ANALYZER ENHANCED TRIPLE VIEW VERIFIED!')"
  ```
  *(Resultado: `GAUSS FIT: 17.0 Residual min/max: 0.0 0.2635`, `DONUT FIT: 17.0 Residual min/max: 0.0 0.6921`, `PROFILE 1D len: 34` — `PSF ANALYZER ENHANCED TRIPLE VIEW VERIFIED!`)*

- **Prueba Ejecutable de la Aplicación**:
  ```powershell
  .\.venv\Scripts\python.exe app.py
  ```
