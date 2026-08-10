# -*- coding: utf-8 -*-
import subprocess

# Recuperar README antiguo completo de c0ff0d8
old_readme = subprocess.check_output(
    ['C:/Program Files/Git/cmd/git.exe', 'show', 'c0ff0d8:README.md'],
    text=True, encoding='utf-8'
)

# Insertar detalles de la fusión de camera.py y los 5 modos de criterio de parada en measurements.py
editions = """### 5. Visión por Computadora y Cámara (`camera.py` / `canon_edsdk.py`)
- Live View en tiempo real (25.0 FPS estricto), paletas LUT de falso color, tracking `trackpy`, navegación panorámica por FOV (ejes X/Y), captura réflex de 15.1 MP multi-formato (JPG, PNG, TIFF, BMP) sin sobreescritura (`get_unique_save_path`), transferencia en RAM mediante `EdsCreateMemoryStream` (inmune a errores `0x000000AB` / `0x00000061`), capa `OverlayWidget` con reglas en µm, cursor de platina PI, ROI confocal y log de diagnóstico emergente desplegable `EDSDKLogDialog`.

### 6. Rutina de Impresión Óptica y 5 Modos de Criterio de Parada (`modules/measurements.py`)
- Incorpora 5 Modos de Criterio de Parada Seleccionables en tiempo real (`Modo 0: Legacy`, `Modo 1: Salto Relativo + Absoluto & Anti-Paso`, `Modo 2: Derivada dI/dt & Aplanamiento`, `Modo 3: Calibración Confocal Raw & Umbral Absoluto Reescalado`, `Modo 4: Criterio Híbrido Tri-Factor`).
- Protección universal contra partículas "de paso" o transitorias mediante el contador de sostenimiento $N_{\text{hold}}$ steps.
- Guardado de imágenes y matrices confocales reescaladas (`NPscan_rescaled_00i.txt` / `.tiff`).
- Documentado formalmente en el reporte técnico: [Algoritmo de Impresión Óptica y Ensamblado de Nanodímeros (reportes/Algoritmo_Printing_y_Dimers_PyPrinting3.md)](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/reportes/Algoritmo_Printing_y_Dimers_PyPrinting3.md)."""

if "### 5. Visión por Computadora y Cámara (`camera.py` / `canon_edsdk.py`)" in old_readme:
    part1 = old_readme.split("### 5. Visión por Computadora y Cámara (`camera.py` / `canon_edsdk.py`)")[0]
    part2 = old_readme.split("---")[2] # despues de la seccion
    new_readme = part1 + editions + "\n\n---\n" + part2
else:
    new_readme = old_readme

with open("README.md", "w", encoding="utf-8") as f:
    f.write(new_readme)

print(f"README.md reestructurado exitosamente con {len(new_readme.splitlines())} líneas!")
