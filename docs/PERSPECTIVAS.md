# 🔮 Perspectivas, Preguntas y Sugerencias Futuras — PyPrinting 3.0

**Laboratorio de Nanofotónica — Instituto de Nanosistemas (INS-UNSAM / CONICET)**  
**Ubicación**: `docs/PERSPECTIVAS.md`  
**Regla de Mantenimiento**: *Cuando una perspectiva, pregunta o sugerencia sea resuelta o ejecutada en el código/laboratorio, se eliminará de este documento y se añadirán nuevas propuestas según el avance del proyecto.*

---

## ❓ 1. Preguntas Abiertas y Alineación de Requerimientos

- [ ] **1.1 Integración del Módulo `PySpectrum` (Hardware & Drivers)**:
  - En el panel principal `main.py` y en el Tablero de Hardware se contempla el canal de espectrometría (`⚪ Inactivo — Pendiente de integración`).
  - **Puntos a definir**:
    - Fabricante y modelo del espectrómetro a utilizar (ej. Ocean Optics / Ocean Insight, Andor Shamrock, Horiba, etc.).
    - Tipo de protocolo/driver de comunicación (SDK C/C++, SeaBreeze, VISA, o comunicación serie/USB directa).
    - Modalidad prioritaria: espectroscopía de dispersión (scattering), termometría fototérmica anti-Stokes o espectroscopía de fluorescencia/fotoluminiscencia.

- [ ] **1.2 Desacoplamiento Modular de `Backend` (Refactorización de Arquitectura)**:
  - Según la evaluación arquitectónica de Graphify (`reportes/sistema/Respuestas_Graphify_y_Evaluacion_Arquitectonica_PyPrinting3.md`), la clase `Backend` en `modules/measurements.py` centraliza 4 responsabilidades distintas (grillas, criterios de parada, autofoco y corrección de deriva).
  - **Puntos a definir**:
    - Determinar si se procede a dividir la clase en 3 subsistemas desacoplados (`GridCoordinatesManager`, `PrintingExecutionEngine` y `DriftCorrectionEngine`) para cumplir con el Principio de Responsabilidad Única (SRP) y elevar la cohesión del código.

---

## 💡 2. Sugerencias Técnicas, Metrológicas y de Usabilidad

- [ ] **2.1 Watchdog de Seguridad para Obturadores Láser (*Hardware Heartbeat*)**:
  - **Problema**: Si el hilo principal GUI o el hilo `confocalThread` sufrieran un bloqueo imprevisto mientras un láser de alta potencia está abierto (`down_flipper()` o pulso TTL activo), existe riesgo de fotodaño térmico al sustrato o fotodesintegración de la muestra.
  - **Solución propuesta**: Implementar un temporizador de seguridad *Watchdog* en `core/shutters.py` o a nivel de tarea NI-DAQmx que fuerce el cierre incondicional de los obturadores si no se recibe un pulso periódico de confirmación (*heartbeat*) dentro de una ventana máxima $T_{\text{max}} + \delta t$.

- [ ] **2.2 Registro Unificado de Metadatos del Experimento (HDF5 / JSON Estructurado)**:
  - **Problema**: Los datos de un lote se distribuyen actualmente en múltiples archivos sueltos (`NP_00i.txt`, `NPscan_00i.tiff`, `.npy`, `.csv`, `grid_info.txt`, `Last_position.txt`).
  - **Solución propuesta**: Generar al finalizar cada lote de impresión un archivo consolidado `session_metadata.json` o contenedor binario **HDF5** (`.h5`) que empaquete las trazas temporales completas, los vectores de deriva acumulados $(\Delta x_{\text{nm}}, \Delta y_{\text{nm}})$, las curvas de correlación de autofoco Z y la configuración del preset utilizado, simplificando el procesamiento masivo (*batch processing*) en Jupyter Notebooks o scripts de análisis.

- [ ] **2.3 Mapa de Calor y Representación Vectorial de Deriva en el Visor 2D**:
  - **Problema**: En `InteractiveGridWidget` (`Grid Pattern & Path Viewer 🗺️`), los nodos solo indican estado binario (verde: impresa / rojo: timeout).
  - **Solución propuesta**:
    - Añadir una capa visual (*toggle*) con flechas vectoriales que ilustren la magnitud y dirección de la deriva compensada por la partícula ancla P0 en cada nodo.
    - Incorporar una vista de mapa de calor (*heatmap*) basada en el tiempo de deposición $t_{\text{print}}$ (en segundos) de cada nanopartícula para evaluar la cinética de adhesión a lo largo de la grilla.

- [ ] **2.4 Suite de Pruebas Automatizadas Unitarias en Modo Seguro (`pytest-qt`)**:
  - **Problema**: Al contar con 5 criterios de parada y múltiples hilos concurrentes, las modificaciones en `modules/measurements.py` o `modules/trace.py` pueden generar regresiones no deseadas.
  - **Solución propuesta**: Crear un directorio `tests/` con pruebas sintéticas automáticas bajo `SAFE_MODE=True` usando `pytest` y `pytest-qt` para validar:
    - Disparo y detención en los 5 criterios de parada ante curvas sintéticas.
    - Correcta conmutación del flipper (baja potencia para escaneo 2D/autofoco, alta potencia para traza).
    - Carga, guardado e integridad de presets en `presets/*.txt`.

- [ ] **2.5 Pre-Calibración Automática de Línea Base y Umbral Mínimo $V_{\text{min}}$**:
  - **Problema**: Las fluctuaciones diarias de potencia láser residual, turbidez del medio coloidal o ruido térmico pueden alterar el piso de ruido.
  - **Solución propuesta**: Emplear las muestras previas a la apertura del obturador (`steps_before` $M_2$) para autocalibrar el umbral mínimo absoluto $V_{\text{min}}$ y emitir una advertencia al operador si el ruido de fondo supera los umbrales típicos antes de iniciar la corrida.

---
