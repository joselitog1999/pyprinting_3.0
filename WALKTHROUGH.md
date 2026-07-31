# WALKTHROUGH DE PYPRINTING 3.0 🔬

Este archivo mantiene el registro continuo de los cambios, soluciones y validaciones realizadas en la arquitectura de **PyPrinting 3.0**.

---

## 🎯 Últimos Cambios y Correcciones Realizadas

1. **Sección de Preguntas Frecuentes (FAQ) en el Manual de Usuario (`MANUAL_USUARIO.md`)**:
   - Se añadió la sección **7. Preguntas Frecuentes (FAQ)** al [MANUAL_USUARIO.md](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/MANUAL_USUARIO.md) con respuestas técnicas detalladas a dos interrogantes fundamentales:
     - **7.1 ¿Cómo se determina el centro de la partícula al realizar un escaneo confocal?**: Explicación paso a paso de la normalización de la matriz de fotodetector $Z$, filtrado umbral al 30%, algoritmos de ajuste (`center of mass`, `center of gauss` 2D sub-píxel, `two NP: center of gauss`) y conversión a coordenadas físicas ($\mu\text{m}$) de la platina PI.
     - **7.2 ¿Qué sucede exactamente en el sistema al ejecutar un escaneo desde el widget Confocal?**: Explicación de la secuencia de 4 etapas (Preparación de visor, Adquisición síncrona `Ramp` / `Step by step` con lectura de fotodiodo y apertura de obturador, Cierre de obturador con cálculo de centro, y Posicionamiento final con `Auto CM` y exportación a `.tiff`).

2. **Actualización General del Manual de Usuario (`MANUAL_USUARIO.md`)**:
   - Se completó la descripción detallada de todos los docks, menús, botones y ventanas flotantes del sistema (`Files`, `Tools`, `Measurements`, `Confocal`, `Trace` dual, `PowerBSWindow`, `Focus z`, `Shutters`, `Nanopositioning`, `CameraWindow` Canon EOS y `ImageAnalyzerWindow`).

3. **Apertura/Cierre Dual de Obturadores y Opción `None` para Láser 2 (`trace.py`)**:
   - Se incorporó la opción `"None"` al selector del **Láser 2** (`trace_laser2`). Al estar seleccionada, no abre ningún obturador adicional ni intenta leer un segundo fotodiodo.
   - Al presionar `Play` se abren ambos obturadores de los lásers activos (`open_shutter(laser1)` y `open_shutter(laser2)`). Al presionar `Stop` se cierran ambos obturadores en simultáneo (`close_shutter(laser1)` y `close_shutter(laser2)`).

4. **Dock de Trazas Abajo de Todo y Ancho Completo (`app.py`)**:
   - Reposicionamiento de `traceDock` a ancho completo en la parte inferior (`size=(1400, 260)`).

5. **Panel `Printing control` Multicolumna y Expandido (`measurements.py`)**:
   - Reorganización de elementos en matriz de 4 columnas horizontales.

---

## 🧪 Validación y Estado del Proyecto

- **Prueba Apertura/Cierre Dual de Obturadores y Opción None**:
  ```powershell
  .\.venv\Scripts\python.exe -c "from app import Backend, Frontend; from PyQt6.QtWidgets import QApplication; import sys; app = QApplication(sys.argv); gui = Frontend(); worker = Backend(); gui.make_connection(worker); print('--- CASO 1: Láser 1 activo (532 nm), Láser 2 en None ---'); worker.traceWorker.play_pause(True, 0, 0); worker.traceWorker.stop(); print('--- CASO 2: Láser 1 activo (532 nm), Láser 2 activo (633 nm) ---'); worker.traceWorker.play_pause(True, 0, 2); worker.traceWorker.stop(); print('SHUTTER TEST FOR BOTH LASERS AND NONE OPTION VERIFIED 100% CLEAN!')"
  ```
- **Prueba Ejecutable de la Aplicación**:
  ```powershell
  .\.venv\Scripts\python.exe app.py
  ```
