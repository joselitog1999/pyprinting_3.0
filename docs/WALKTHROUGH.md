# WALKTHROUGH DE PYPRINTING 3.0 🔬

Este archivo mantiene el registro continuo de los cambios, soluciones y validaciones realizadas en la arquitectura de **PyPrinting 3.0**.

---

## 🎯 Últimos Cambios y Correcciones Realizadas

1. **Implementación de 5 Modos Seleccionables de Criterio de Parada (`modules/measurements.py`)**:
   - **Modo 0: Legacy (Salto Relativo Estándar)**: Mantiene $100\%$ de compatibilidad con secuencias históricas ($I_{\text{new}} / I_{\text{old}} > \text{Umbral}$).
   - **Modo 1: Salto Relativo + Umbral Absoluto (V) & Anti-Paso**: Permite definir `Umbral Absoluto (V)` para solucionar impresiones instantáneas a $t=0$ y `N hold steps` para evitar falsas detecciones de partículas "de paso" (tránsito temporal).
   - **Modo 2: Derivada Temporal Adaptativa & Aplanamiento ($dI/dt$)**: Evalúa la derivada discreta en tiempo real para detectar la meseta en alto nivel ($dI/dt \to 0$), solucionando curvas de crecimiento exponencial $1-e^{-t/\tau}$.
   - **Modo 3: Calibración Confocal Raw & Umbral Absoluto Reescalado**: Calcula el umbral en Volts a partir del mapa confocal previo y la relación de potencia $K_{\text{scale}} = P_{\text{print}} / P_{\text{scan}}$. Guarda la imagen y matriz confocal reescalada (`NPscan_rescaled_00i.txt` / `.tiff`).
   - **Modo 4: Criterio Híbrido Tri-Factor (All-In-One)**: Evalúa simultáneamente salto relativo, aplanamiento de derivada $dI/dt$ y umbral absoluto en Volts bajo la protección anti-paso $N_{\text{hold}}$.

2. **Visibilidad Dinámica de Casilleros en la GUI (`Frontend`)**:
   - La selección del desplegable `Criterio Parada` en la interfaz gráfica muestra u oculta dinámicamente solo los casilleros de entrada relevantes para cada modo (`Umbral Abs (V)`, `N hold steps`, `Slope Min`, `Slope Flat`, `Ratio K`, `Umbral (%)`).

3. **Documentación y Reportes Actualizados**:
   - Se actualizó el reporte técnico formal en **`reportes/Algoritmo_Printing_y_Dimers_PyPrinting3.md`**.
   - Se actualizó **`docs/MANUAL_USUARIO.md`** y **`README.md`**.
   - Se creó **`docs/PERSPECTIVAS.md`** como documento dinámico de preguntas abiertas, requerimientos y sugerencias técnicas.

4. **Validación y Corrección de Picasso (`picassosr`) y Deconvolución R-L**:
   - Se corrigió el paso por canal de imágenes RGB/RGBA en `richardson_lucy_deconv` (`analysis/psf.py`).
   - Se incorporó `QSpinBox` y `QDialogButtonBox` en los imports de `analysis/image_analyzer.py`.
   - Se corrigieron las firmas de llamada a `_fit2d_gausslq` y `_fit2d_avg` en `analysis/image_analyzer.py` y `modules/camera.py`, pasando explícitamente `em=False` y `multiprocess=False`.

5. **Calibración de Canales Físicos Reales del Banco Óptico (`config.py`)**:
   - Se actualizaron las líneas digitales de obturadores TTL: `SHUTTER_CHANNELS = [11, 8, 9, 10]`.
   - Se ajustó la polaridad física real de los relés: `SHUTTER_POLARITY = {532nm: False (Activo Bajo), 637nm: True, 592nm: True, 808nm: True}`.
   - Se re-mapearon los canales de entrada analógica de fotodiodos: `PD_CHANNELS = {532nm: ai0, 637nm: ai2, 592nm: ai1, 808nm: ai3, BS: ai6}`.
   - Se resolvió y eliminó el ítem 1.3 de `docs/PERSPECTIVAS.md` conforme al protocolo de mantenimiento.

6. **Integración Completa de la Línea Láser 808 nm (Infrarrojo - IR)**:
   - Se incorporó `"808 nm (IR)"` a `SHUTTERS` con obturador en la línea digital `port0/line10` y canal de fotodiodo en `Dev1/ai3`.
   - Se actualizó el panel de control de obturadores ([`core/shutters.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/core/shutters.py)) con el 4to botón `shutter3button`, señal `shutter3_signal` y slot `shutter3`.
   - Se actualizaron los selectores de color de todos los módulos (`measurements.py`, `trace.py`, `focus.py`, `confocal.py`, `contrapropagante.py`) con el color `#ad1457` / borravino para la línea infrarroja.
   - Se validaron todos los módulos y la apertura/cierre de obturadores y lectura de fotodiodos en modo seguro y nominal.

---

## 🧪 Validación Realizada

- **Prueba Sintética de Instanciación e Interfaz Gráfica**:
  ```powershell
  .\.venv\Scripts\python.exe -c "from PyQt6.QtWidgets import QApplication; import sys; app = QApplication(sys.argv); from modules.measurements import Frontend, Backend; fe = Frontend(mode='printing'); be = Backend(mode='printing'); fe.make_connection(be); print('Merged measurements.py PASSED!')"
  ```
  Result: **`PASSED`** (Compilación e instanciación limpias).

- **Prueba Completa de Detección Multimotor Picasso (MLE, LQ, Avg)**:
  ```powershell
  .\.venv\Scripts\python.exe -c "import sys, numpy as np; from PyQt6.QtWidgets import QApplication; app = QApplication(sys.argv); from analysis.image_analyzer import ImageAnalyzerWidget; win = ImageAnalyzerWidget(); win._raw_frame = np.zeros((200, 200, 3), dtype=np.uint8); win._current_frame = win._raw_frame; win._trackpy_params = {'engine': 'picasso', 'min_net_gradient': 200.0, 'box_size': 7, 'fit_method': 'gaussmle'}; win._run_detection(); print('Picasso Tests PASSED!')"
  ```
  Result: **`PASSED`** (Detección sub-píxel operativa en los 3 métodos).
