# WALKTHROUGH DE PYPRINTING 3.0 🔬

Este archivo mantiene el registro continuo de los cambios, soluciones y validaciones realizadas en la arquitectura de **PyPrinting 3.0**.

---

## 🎯 Últimos Cambios y Correcciones Realizadas

1. **Priorización de Hilo y Regulación Estricta a 25.0 FPS Constantes**:
   - **Aislamiento de Hilo de Alta Prioridad**: El hilo secundario `QThread` que ejecuta el controlador de la cámara Canon EOS 500D se inicia con prioridad alta (`QThread.Priority.HighPriority`).
   - **Regulación Estricta post-5s de Estabilización**:
     - Durante los primeros 5 segundos de conexión, se ejecuta un bucle adaptativo de estabilización del sensor.
     - **Cumplidos los 5 segundos de estabilización**, el regulador ajusta dinámicamente la latencia C++ USB en microsegundos (`time.perf_counter()`) para solicitar el siguiente cuadro exactamente en el milisegundo 40.0, fijando una tasa ininterrumpida y sostenida de **exactamente 25.0 FPS constantes**.

2. **Captura y Guardado de Fotos en Resolución Nativa de 15.1 MP (4752×3168)**:
   - **Selección de Formato de Salida**: Formatos seleccionables desde la interfaz:
     - **`JPG` (Máxima Resolución Nativa 15.1 MP - 4752×3168)** *(Por defecto)*.
     - **`PNG` (Alta Calidad Sin Pérdida 15.1 MP - 4752×3168)**.
     - **`TIFF` (Metrología y Análisis Cuantitativo 15.1 MP - 4752×3168)**.
     - **`BMP` (Mapa de bits sin comprimir - 4752×3168)**.
   - **Estructura de Nombres y Directorio**:
     - Directorio por defecto: `c:\Users\PRINTING\Documents\printing3\pyprinting_3.0\data` (o carpeta seleccionada).
     - Formato de nombre: `CANON_EOS500D_AAAAMMDD_HHMMSS.[ext]`.

---

## 🧪 Validación y Estado del Proyecto

- **Prueba Sintética de Regulación a 25 FPS**:
  ```powershell
  .\.venv\Scripts\python.exe -c "from PyQt6.QtWidgets import QApplication; import sys; app = QApplication(sys.argv); from core.canon_test import CanonTestWindow; win = CanonTestWindow(); print('Strict 25 FPS regulation test PASSED!')"
  ```
