# WALKTHROUGH DE PYPRINTING 3.0 🔬

Este archivo mantiene el registro continuo de los cambios, soluciones y validaciones realizadas en la arquitectura de **PyPrinting 3.0**.

---

## 🎯 Últimos Cambios y Correcciones Realizadas

1. **Creación e Integración del Módulo "Microscopio Contrapropagante" (`contrapropagante.py`)**:
   - Diseñada e implementada la suite completa para microscopía con excitación e iluminación dual síncrona por objetivo derecho (TOP) e invertido (BOT).
   - **Mapeo Óptico Dicroico / Notch & Fotodiodos Acoplados**:
     - **Fotodiodo 1 (`ai0`)**: Acoplado ópticamente al láser TOP seleccionado (`532 nm green`, `637 nm red`, `592 nm yellow`).
     - **Fotodiodo 2 (`ai1`)**: Acoplado ópticamente al láser BOT de excitación inferior (`532 nm green`).
   - **Disposición Visual Horizontal**:
     - **Izquierda**: `Display Confocal TOP (Derecho — Fotodiodo 1 / ai0)` con mapa de falso color, histograma LUT y marcas del centrado.
     - **Centro**: `Controles Compartidos` (selectores de láser TOP `Green/Red/Yellow` y BOT `Green`, rango, píxeles, modo rampa/paso, botón `Analyze with PSF Analyzer` y widget de centrado sub-nanométrico CM Dual).
     - **Derecha**: `Display Confocal BOT (Invertido — Fotodiodo 2 / ai1)` con mapa de falso color e histograma LUT.
   - **Adquisición Dual en Paralelo**: Adquisición síncrona de 2 canales analógicos de fotodiodo (Canal AI0 TOP y Canal AI1 BOT) mediante la misma trayectoria rampa de la platina PI.
   - **Módulo de Centrado CM Dual & Selector de Referencia Preferencial**:
     - Eliminado `Go to NP2` (microscopio de nanopartícula única en el foco).
     - Casilleros de filtro independientes: `Filtro TOP (%)` y `Filtro BOT (%)`.
     - Deslizador de 2 posiciones para elegir la referencia activa (`TOP` vs `BOT`).
     - Botón `Go to NP`: Mueve la platina PI a las coordenadas $(x_{\text{ref}}, y_{\text{ref}})$ de la partícula detectada en la referencia activa.
     - **Despliegue del Vector Diferencia Sub-nanométrico**: Calcula y visualiza en tiempo real $(x_{\text{TOP}}, y_{\text{TOP}})$, $(x_{\text{BOT}}, y_{\text{BOT}})$ y la diferencia vectorial $\mathbf{r}_{\text{TOP}} - \mathbf{r}_{\text{BOT}}$ ($\Delta x, \Delta y, \|\mathbf{\Delta r}\|$ en nm).
   - **Integración Directa con PSF Analyzer**: El botón `Analyze with PSF Analyzer` transfiere las imágenes recien adquiridas TOP y BOT a `PSFAnalyzerWindow` como Canal 1 y Canal 2 para caracterización analítica y superposición RGB.

2. **Reubicación de Drift Measurement**:
   - Eliminado `Drift Measurement` del dock confocal predeterminado en `confocal.py` para mantener la interfaz centrada en la inspección visual.

3. **Habilitación en el Lanzador Principal (`main.py`)**:
   - Habilitada la tarjeta 3 de la Fila 1 en el lanzador 3x3 de `main.py` ("Microscopio Contrapropagante"), apuntando directamente a `contrapropagante.py`.

---

## 🧪 Validación y Estado del Proyecto

- **Prueba Sintética en MODO SEGURO (SAFE_MODE)**:
  ```powershell
  .\.venv\Scripts\python.exe -c "import contrapropagante; print('Contrapropagante OK')"
  ```
- **Ejecución del Lanzador Principal**:
  ```powershell
  .\.venv\Scripts\python.exe main.py
  ```
