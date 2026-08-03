# WALKTHROUGH DE PYPRINTING 3.0 🔬

Este archivo mantiene el registro continuo de los cambios, soluciones y validaciones realizadas en la arquitectura de **PyPrinting 3.0**.

---

## 🎯 Últimos Cambios y Correcciones Realizadas

1. **Organización de Generación de PDFs en la Carpeta `pdfs/`**:
   - Todo lo referente a la documentación metrológica y la compilación PDF ha sido trasladado a la carpeta dedicada `pdfs/`.
   - **`pdfs/Incertidumbre_Metrologica_PyPrinting3.tex`**: Documento fuente en **LaTeX nativo** formateado para publicación académica (`amsmath`, `amssymb`, `booktabs`, `tcolorbox`, `fancyhdr`, `geometry`).
   - **`pdfs/compile_latex.py`**: Script de automatización que compila el código LaTeX utilizando **MiKTeX (`pdflatex`)** instalado en el sistema.
   - **`pdfs/Incertidumbre_Metrologica_PyPrinting3.pdf`**: Documento PDF final de alta calidad vectorial (4 páginas, 294 KB).
   - **`pdfs/build_pdf.py`**: Script alternativo de generación mediante ReportLab y Matplotlib Mathtext.

2. **Optimizaciones de Seguridad y Estructura Adaptativa en Modo Ramp (`confocal.py`)**:
   - Implementado el patrón adaptativo `if self.Nx <= 50 and self.range_x <= 5.0:` para escaneos típicos ($2 \times 2\ \mu\text{m}$, $34 \times 34\ \text{px}$).
   - Escalado adaptativo `Nramp` y clampeo dinámico de puntos de onda `Npoints = min(4000, ...)` para campos grandes ($20 \times 20\ \mu\text{m}$, $400 \times 400\ \text{px}$).
   - Clampeo de origen de rampa a límites físicos piezoeléctricos $X_{\text{inicio}}, Y_{\text{inicio}} \in [0.0, 100.0 - Range_{\text{total}}]\ \mu\text{m}$.

---

## 🧪 Validación y Estado del Proyecto

- **Compilación Nativa MiKTeX en `pdfs/`**:
  ```powershell
  .\.venv\Scripts\python.exe pdfs/compile_latex.py
  ```
  *(Resultado: `Output written on pdfs/Incertidumbre_Metrologica_PyPrinting3.pdf (4 pages, 294396 bytes)` — Éxito absoluto)*

- **Prueba Ejecutable de la Aplicación**:
  ```powershell
  .\.venv\Scripts\python.exe main.py
  ```
