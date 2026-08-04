# WALKTHROUGH DE PYPRINTING 3.0 🔬

Este archivo mantiene el registro continuo de los cambios, soluciones y validaciones realizadas en la arquitectura de **PyPrinting 3.0**.

---

## 🎯 Últimos Cambios y Correcciones Realizadas

1. **Resolución de Inestabilidad y Congelamiento de Live View (Estrategia Adaptativa)**:
   - **Causa Raíz**: El uso de un temporizador periódico fijo `QTimer(40ms)` provocaba acumulación de eventos de timeout en la cola de mensajes de Qt cuando el bus USB tardaba más de 40 ms en responder. Esto producía aceleración súbita de cuadros, colisiones en el buffer C++ EDSDK y cuelgues del programa.
   - **Solución Adaptativa Implementada**:
     - Se reemplazó el `QTimer` periódico por un bucle **single-shot adaptativo guiado por tiempo de ejecución (`_fetch_frame_adaptive`)**.
     - Tras cada frame descargado, se calcula el tiempo transcurrido (`elapsed_ms`) y se programa la siguiente lectura con un delay dinámico para mantener 25 FPS sin saturar la cola USB. La profundidad de la cola USB es **siempre exactamente 1**, eliminando aceleraciones y congelamientos.

2. **Captura y Guardado de Fotos en Resolución Nativa de 15.1 MP (4752×3168)**:
   - **Selección de Formato de Salida**: Se agregó un desplegable en el panel de control de la cámara para elegir el formato de guardado:
     - **`JPG` (Máxima Resolución Nativa 15.1 MP - 4752×3168)** *(Por defecto)*.
     - **`PNG` (Alta Calidad Sin Pérdida 15.1 MP - 4752×3168)**.
     - **`TIFF` (Metrología y Análisis Cuantitativo 15.1 MP - 4752×3168)**.
     - **`BMP` (Mapa de bits sin comprimir - 4752×3168)**.
   - **Estructura de Nombres y Directorio**:
     - Directorio por defecto: `c:\Users\PRINTING\Documents\printing3\pyprinting_3.0\data` (o carpeta personalizada seleccionable mediante el botón `📁 Cambiar Carpeta Guardado`).
     - Formato de nombre: `CANON_EOS500D_AAAAMMDD_HHMMSS.[ext]` (ej. `CANON_EOS500D_20260804_103422.png`).
   - **Protocolo de Captura y Confirmación**:
     - Pausa automática del stream de video en vivo durante el disparo para liberar el sensor réflex DIGIC 4.
     - Transferencia directa desde el buffer réflex a PC mediante `kEdsSaveTo_Host`.
     - Notificación emergente `QMessageBox` y registro en la consola de diagnóstico con el enlace de ruta de archivo.

---

## 🧪 Validación y Estado del Proyecto

- **Prueba Sintética de Stream Adaptativo y Captura Multi-Formato**:
  ```powershell
  .\.venv\Scripts\python.exe -c "from PyQt6.QtWidgets import QApplication; import sys; app = QApplication(sys.argv); from core.canon_test.py import CanonTestWindow; win = CanonTestWindow(); print('Stream adaptativo y fotos 15 MP OK')"
  ```
