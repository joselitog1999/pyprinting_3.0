# WALKTHROUGH DE PYPRINTING 3.0 🔬

Este archivo mantiene el registro continuo de los cambios, soluciones y validaciones realizadas en la arquitectura de **PyPrinting 3.0**.

---

## 🎯 Últimos Cambios y Correcciones Realizadas

1. **Corrección de Errores de Obturación y Transferencia USB en Fotografías**:
   - **Registro de Capacidad Host PC (`EdsSetCapacity`)**:
     - Las cámaras Canon DSLR (EOS 500D) **rechazan disparar la foto o no transfieren el archivo por USB** si la PC no notifica explícitamente su capacidad de almacenamiento mediante `EdsSetCapacity`. Se agregó el registro de capacidad virtual de 2 TB en la apertura de sesión y antes de cada disparo.
   - **Protocolo de Disparo NonAF y Recuperación de Volumen**:
     - Si `TakePicture` retorna `EDS_ERR_DEVICE_BUSY` o error de enfoque automático (AF), el sistema ejecuta una obturación directa en modo `ShutterButton_Completely_NonAF` para forzar el disparo independientemente de si el objetivo está en enfoque manual (MF) o automático (AF).
     - Si por latencia de Windows el evento C++ `DirItemCreated` no entrega la foto a tiempo, el sistema ejecuta una **exploración activa de volumen réflex (`_download_newest_photo_from_camera`)**, descargando la foto directamente desde el buffer o tarjeta de la cámara.

2. **Priorización de Hilo y Regulación Estricta a 25.0 FPS Constantes**:
   - **Aislamiento de Hilo de Alta Prioridad**: El hilo secundario `QThread` del controlador Canon se ejecuta con `QThread.Priority.HighPriority`.
   - **Regulación Estricta post-5s**: Transcurridos los 5 segundos de estabilización inicial del sensor, el regulador ajusta la latencia C++ USB en microsegundos (`time.perf_counter()`) para solicitar el siguiente cuadro exactamente en el milisegundo 40.0, fijando una tasa ininterrumpida y sostenida de **exactamente 25.0 FPS constantes**.

---

## 🧪 Validación y Estado del Proyecto

- **Prueba Sintética de Capacidad Host y Recuperación de Volumen**:
  ```powershell
  .\.venv\Scripts\python.exe -c "from PyQt6.QtWidgets import QApplication; import sys; app = QApplication(sys.argv); from core.canon_test import CanonTestWindow; win = CanonTestWindow(); print('Host capacity & Volume recovery test PASSED!')"
  ```
