# -*- coding: utf-8 -*-
import subprocess
import os

# 1. Recuperar el manual completo de 530 líneas de 9280215
old_manual = subprocess.check_output(
    ['C:/Program Files/Git/cmd/git.exe', 'show', '9280215:docs/MANUAL_USUARIO.md'],
    text=True, encoding='utf-8'
)

# 2. Secciones a expandir e integrar sin borrar nada:
section_3_7_replacement = """### 3.7 Ventana de Mediciones (Printing Automatizado de Grillas, Dímeros & 5 Modos de Criterio de Parada)
* **Pestaña `Printing` (Impresión de Grillas)**:
  - **`Create Grid`**: Define el número de filas, columnas y el espaciamiento en $\mu\text{m}$ ($d_n \times d_N$).
  - **`Set reference`**: Congela las coordenadas capacitivas de origen $(X_0, Y_0, Z_0)$ de la platina PI.
  - **Selector de Criterio de Parada (`Criterio Parada`)**: Desplegable con 5 modos de realimentación óptica:
    - **`Modo 0: Legacy (Salto Relativo Estándar)`**: Evalúa $I_{\text{new}} / I_{\text{old}} > \text{Umbral}$ (100% compatible con secuencias históricas).
    - **`Modo 1: Salto Relativo + Umbral Absoluto (V) & Anti-Paso`**: Evalúa $I_{\text{new}} / I_{\text{old}} > \text{Umbral}$ **o** $I_{\text{new}} > \text{Umbral Abs (V)}$, solucionando impresiones instantáneas a $t=0$. Exige $N_{\text{hold}}$ pasos consecutivos para ignorar partículas "de paso" o transitorias.
    - **`Modo 2: Derivada Temporal Adaptativa & Aplanamiento (dI/dt)`**: Evalúa $|dI/dt| < \text{Slope Flat}$ con $I_{\text{new}} > I_{\text{old}} + \Delta V$, detectando la meseta asíntota en alto nivel para curvas exponenciales ($1 - e^{-t/\tau}$) y escalones suaves.
    - **`Modo 3: Calibración Confocal Raw & Umbral Absoluto Reescalado`**: Mide el voltaje de fondo de vidrio limpio $V_{\text{vidrio}} = \min(V_{\text{raw}})$ de la confocal previa y aplica la relación de atenuación de potencia $K_{\text{scale}} = P_{\text{print}} / P_{\text{scan}}$ para determinar el umbral absoluto cuantitativo en Volts al porcentaje $P\%$ deseado:
      $$V_{\text{umbral}} = V_{\text{vidrio}} + \\frac{P}{100} \\cdot (V_{\text{pico\_reescalado}} - V_{\text{vidrio}})$$
      Guarda la matriz confocal reescalada en archivos `.txt` y `.tiff` (`NPscan_rescaled_00i.txt`).
    - **`Modo 4: Criterio Híbrido Tri-Factor (All-In-One)`**: Combina simultáneamente salto relativo, aplanamiento de derivada $dI/dt$ y umbral absoluto en Volts bajo la protección anti-paso de $N_{\text{hold}}$ pasos.
  - **`T max (s)`**: Tiempo límite de exposición por nodo antes de abortar.
  - **`Steps before / after`**: Número de puntos promediados para la línea base ($I_{\text{old}}$) y la señal entrante ($I_{\text{new}}$).
  - **`Play ►`**: Inicia la secuencia automatizada de deposición nodo a nodo.
* **Pestaña `Dimers` (Ensamblado de Dímeros)**:
  - Posicionamiento guiado a distancia gap sub-100 nm asistido por escaneo confocal local (`center_scan` $\\rightarrow$ Offset $\\Delta x, \\Delta y \\rightarrow$ `pree_scan` $\\rightarrow$ Impresión $\\rightarrow$ `post_scan`).

> [!NOTE]
> Para consultar la formulación matemática detallada y el diagrama de flujo multihilo completo, consulte el reporte técnico dedicado:
> [Reporte Técnico: Algoritmo de Impresión Óptica y Ensamblado de Nanodímeros (reportes/Algoritmo_Printing_y_Dimers_PyPrinting3.md)](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/reportes/Algoritmo_Printing_y_Dimers_PyPrinting3.md)"""

# Buscar el bloque de la sección 3.7 en el manual antiguo y reemplazarlo conservando TODO el resto
start_marker = "### 3.7 Ventana de Mediciones (Printing Automatizado de Grillas & Dímeros)"
end_marker = "## 4. Módulo 2: PySpectrum *(En Construcción)*"

if start_marker in old_manual and end_marker in old_manual:
    part1 = old_manual.split(start_marker)[0]
    part2 = old_manual.split(end_marker)[1]
    new_manual = part1 + section_3_7_replacement + "\n\n---\n\n## 4. Módulo 2: PySpectrum *(En Desarrollo: Espectrometría, Termometría & Scattering)*" + part2
else:
    new_manual = old_manual

# Guardar nuevo manual completo en disco
target_path = r"c:\Users\josel\Documents\Obsidian_Vault\printing3\docs\MANUAL_USUARIO.md"
with open(target_path, "w", encoding="utf-8") as f:
    f.write(new_manual)

print(f"Manual de Usuario reestructurado exitosamente con {len(new_manual.splitlines())} líneas!")
