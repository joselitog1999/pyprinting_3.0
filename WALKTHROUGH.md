# WALKTHROUGH DE PYPRINTING 3.0 🔬

Este archivo mantiene el registro continuo de los cambios, soluciones y validaciones realizadas en la arquitectura de **PyPrinting 3.0**.

---

## 🎯 Últimos Cambios y Correcciones Realizadas

1. **Incorporación del Modelo Óptico iSCAT / Confocal (60x Agua, NA=1.0) en `reportes/Incertidumbre_Metrologica_PyPrinting3.md`**:
   - Agregada la derivación completa de la **Magnificación Óptica Total del Sistema**:
     $$M_{\text{total}} = \left(\frac{f_1}{f_{\text{obj}}}\right) \times \left(\frac{f_3}{f_2}\right) = \left(\frac{250\,\text{mm}}{3.0\,\text{mm}}\right) \times \left(\frac{150\,\text{mm}}{200\,\text{mm}}\right) = \mathbf{62.5\times}$$
   - Deducción del **Disco de Airy proyectado** ($D_{\text{Airy, img}} = 40.56\,\mu\text{m}$) y normalización del **Pinhole de $50\,\mu\text{m}$** a **$1.23\ \text{Unidades de Airy (AU)}$** (transmisión del $85\%$ de luz central).
   - Cálculo del **seccionado óptico axial** ($\text{FWHM}_z = 1.165\,\mu\text{m}$).
   - Cálculo de incertidumbres ópticas adicionales:
     - **Incertidumbre por desalineación mecánica del pinhole ($u_{\text{pinhole\_shift}} = 4.62\,\text{nm}$)**.
     - **Incertidumbre por desacople de índice agua/vidrio / aberración esférica ($u_{\text{aberration}} = 1.80\,\text{nm}$)**.
   - Tabla GUM completa de incertidumbre combinada ($15.48\,\text{nm}$ para $\Delta x = 50\,\text{nm}$ y **$6.08\,\text{nm}$** para escaneo fino $\Delta x = 10\,\text{nm}$).

2. **Optimizaciones de Seguridad y Estructura Adaptativa en Modo Ramp (`confocal.py`)**:
   - Implementado el patrón adaptativo `if self.Nx <= 50 and self.range_x <= 5.0:` para escaneos típicos ($2 \times 2\ \mu\text{m}$, $34 \times 34\ \text{px}$).
   - Escalado adaptativo `Nramp` y clampeo dinámico de puntos de onda `Npoints = min(4000, ...)` para campos grandes ($20 \times 20\ \mu\text{m}$, $400 \times 400\ \text{px}$).
   - Clampeo de origen de rampa a límites físicos piezoeléctricos $X_{\text{inicio}}, Y_{\text{inicio}} \in [0.0, 100.0 - Range_{\text{total}}]\ \mu\text{m}$.

---

## 🧪 Validación y Estado del Proyecto

- **Documentación Metrológica iSCAT**:
  - `reportes/Incertidumbre_Metrologica_PyPrinting3.md` actualizado y validado con cálculos ópticos completos.

- **Prueba Ejecutable de la Aplicación**:
  ```powershell
  .\.venv\Scripts\python.exe main.py
  ```
