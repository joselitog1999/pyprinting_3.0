# WALKTHROUGH DE PYPRINTING 3.0 🔬

Este archivo mantiene el registro continuo de los cambios, soluciones y validaciones realizadas en la arquitectura de **PyPrinting 3.0**.

---

## 🎯 Últimos Cambios y Correcciones Realizadas

1. **Inclusión de la Sección de Dependencia del Tamaño de Píxel y Resolución Sub-píxel en `reportes/Incertidumbre_Metrologica_PyPrinting3.md`**:
   - Agregada la **Sección 7 (Dependencia del Tamaño de Píxel ($\Delta x$) con la Resolución Sub-píxel y la Incertidumbre Combinada)**:
     - **Relación de Escala Haz vs. Nanopartícula:** Modelado de convolución espacial entre el haz de excitación ($\text{FWHM}_{\text{spot}} \approx 266\,\text{nm}$) y la nanopartícula típica de Au ($d_{\text{NP}} \approx 100\,\text{nm}$), resultando en una envolvente Gaussiana efectiva de $\text{FWHM}_{\text{efectivo}} \approx 284\,\text{nm}$.
     - **Criterio de Nyquist-Shannon vs. Ajuste Sub-píxel Centroidal:** Nyquist exige $\Delta x \le 142\,\text{nm/px}$ para evitar aliasing, mientras que el ajuste sub-píxel no lineal sub-nanométrico ($u_{\text{fit}} < 0.6\,\text{nm}$) exige $\Delta x \le 28 - 56\,\text{nm/px}$ ($5 - 10$ píxeles a lo largo de la FWHM).
     - **Curva de Compromiso Metrológico y Tamaño de Píxel Óptimo:** Demostración cuantitativa de que el tamaño de píxel óptimo para el sistema iSCAT/Confocal en PyPrinting 3.0 es **$\Delta x_{\text{óptimo}} = 15 - 25\,\text{nm/px}$**, logrando una **incertidumbre combinada mínima de $7.10\,\text{nm}$**.
   - **Correcciones Físicas de Hardware Solicitadas**:
     - Removida la aberración por interfaz vidrio/agua ($u_{\text{aberration}} = 0$) debido a que el objetivo $60\times$ agua observa las nanopartículas montadas directamente sobre la superficie del cubreobjetos en medio líquido.
     - Removida la desalineación vectorial inter-láser ($\Delta r_{\text{nm}}$) puesto que cada línea láser posee su propio fotodiodo y pinhole alineados de forma independiente.

2. **Optimizaciones de Seguridad y Estructura Adaptativa en Modo Ramp (`confocal.py`)**:
   - Implementado el patrón adaptativo `if self.Nx <= 50 and self.range_x <= 5.0:` para escaneos típicos ($2 \times 2\ \mu\text{m}$, $34 \times 34\ \text{px}$).
   - Escalado adaptativo `Nramp` y clampeo dinámico de puntos de onda `Npoints = min(4000, ...)` para campos grandes ($20 \times 20\ \mu\text{m}$, $400 \times 400\ \text{px}$).
   - Clampeo de origen de rampa a límites físicos piezoeléctricos $X_{\text{inicio}}, Y_{\text{inicio}} \in [0.0, 100.0 - Range_{\text{total}}]\ \mu\text{m}$.

---

## 🧪 Validación y Estado del Proyecto

- **Documentación Metrológica iSCAT**:
  - `reportes/Incertidumbre_Metrologica_PyPrinting3.md` actualizado y validado con cálculos ópticos completos y gráficos de compromiso de píxel.

- **Prueba Ejecutable de la Aplicación**:
  ```powershell
  .\.venv\Scripts\python.exe main.py
  ```
