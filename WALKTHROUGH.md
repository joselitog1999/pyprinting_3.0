# WALKTHROUGH DE PYPRINTING 3.0 🔬

Este archivo mantiene el registro continuo de los cambios, soluciones y validaciones realizadas en la arquitectura de **PyPrinting 3.0**.

---

## 🎯 Últimos Cambios y Correcciones Realizadas

1. **Nuevo Algoritmo de Detección de Centro para Haces Donut / Laguerre-Gauss ($LG_{01}$) (`psf.py` y `confocal.py`)**:
   - **Modelo Matemático Analítico 2D**:
     $$I_{\text{donut}}(x, y) = I_{\text{offset}} + A \cdot r_n^2(x, y) \cdot \exp\left( - r_n^2(x, y) \right), \quad \text{donde } r_n^2(x, y) = \frac{(x - x_0)^2}{2\sigma_x^2} + \frac{(y - y_0)^2}{2\sigma_y^2}$$
   - **Implementación en `psf.py`**:
     - Se añadieron las funciones `donut2D(...)` y `center_of_donut2D(image, xo, yo)`. La función ejecuta un ajuste por mínimos cuadrados no lineales (`scipy.optimize.curve_fit`) determinando las coordenadas sub-píxel $(x_0, y_0)$ del **mínimo nulo central del haz Donut**.
   - **Integración en `confocal.py`**:
     - Se añadió el elemento `"donut (Laguerre-Gauss)"` a la lista `METHOD_CENTER` y su correspondiente rama en `_CMmeasure()`.
   - **Documentación**: Se actualizaron [MANUAL_USUARIO.md](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/MANUAL_USUARIO.md) y la sección FAQ 7.1 con la descripción técnica de este nuevo algoritmo.

2. **Sección de Preguntas Frecuentes (FAQ) en el Manual de Usuario (`MANUAL_USUARIO.md`)**:
   - Se añadió la sección **7. Preguntas Frecuentes (FAQ)** al [MANUAL_USUARIO.md](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/MANUAL_USUARIO.md) con respuestas técnicas detalladas sobre la determinación del centro de partículas y el flujo completo de escaneo confocal.

3. **Apertura/Cierre Dual de Obturadores y Opción `None` para Láser 2 (`trace.py`)**:
   - Opción `"None"` en el selector del **Láser 2** y apertura/cierre simultáneo de obturadores en `Play` y `Stop`.

---

## 🧪 Validación y Estado del Proyecto

- **Prueba de Ajuste Sintético Donut ($LG_{01}$)**:
  ```powershell
  .\.venv\Scripts\python.exe -c "import numpy as np; from psf import donut2D, center_of_mass, center_of_donut2D; Nx, Ny = 34, 34; x = np.arange(-Nx/2 + 0.5, Nx/2); y = np.arange(-Ny/2 + 0.5, Ny/2); Mx, My = np.meshgrid(x, y); true_xo_px, true_yo_px = 18.5, 14.3; true_x_grid = x[0] + true_xo_px; true_y_grid = y[0] + true_yo_px; img = donut2D((Mx, My), 1.0, true_x_grid, true_y_grid, 2.0, 2.0, 0.05).reshape(Ny, Nx); cm_x, cm_y = center_of_mass(img); fit_x, fit_y = center_of_donut2D(img, cm_x, cm_y); print(f'True: ({true_xo_px}, {true_yo_px}) | CM: ({cm_x}, {cm_y}) | Donut Fit: ({fit_x:.3f}, {fit_y:.3f})')"
  ```
  *(Resultado: `True: (18.5, 14.3) | CM: (17.106, 15.833) | Donut Fit: (18.500, 14.300)`)*

- **Prueba Ejecutable de la Aplicación**:
  ```powershell
  .\.venv\Scripts\python.exe app.py
  ```
