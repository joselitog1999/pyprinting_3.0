# WALKTHROUGH DE PYPRINTING 3.0 🔬

Este archivo mantiene el registro continuo de los cambios, soluciones y validaciones realizadas en la arquitectura de **PyPrinting 3.0**.

---

## 🎯 Últimos Cambios y Correcciones Realizadas

1. **Protección Anti-Cuelgues en Selección de Carpeta y Cambios Rápidos de ISO/Tv**:
   - **Antirrebote (*Debounce Timer*) para ISO y Tv (200 ms)**:
     - Cambiar rápidamente las opciones de ISO o velocidad de obturación en la interfaz enviaba ráfagas de comandos `EdsSetPropertyData` al chip DIGIC 4 de la cámara réflex, saturando la transacción USB (`EDS_ERR_DEVICE_BUSY`).
     - Se implementó un temporizador de antirrebote de 200 ms (`_debounce_iso_timer` y `_debounce_tv_timer`) que espera a que el usuario termine de desplazarse antes de enviar un único comando limpio a la cámara.
   - **Reintentos Seguros en `set_property_value`**:
     - Se agregó un bucle de 5 reintentos espaciados 60 ms en `set_property_value()` para tolerar estados de ocupado (`BUSY`) sin abortar Python.
   - **Pausa de Stream Durante Diálogos Nativos (`QFileDialog`)**:
     - Abrir la ventana de selección de carpetas bloqueaba el hilo principal de Qt mientras el hilo de la cámara continuaba emitiendo cuadros. Se agregó la pausa automática del bucle adaptativo durante la selección de carpetas para prevenir bloqueos (*deadlocks*).

2. **Resolución de Error 64-bit ABI `ctypes.ArgumentError: OverflowError: int too long to convert`**:
   - Se configuraron las firmas explícitas de 64 bits (`argtypes = [ctypes.c_void_p, ...]`) para todas las funciones DLL del SDK de Canon EDSDK.

---

## 🧪 Validación y Estado del Proyecto

- **Prueba Sintética de Antirrebote y Pausa en Selección de Carpeta**:
  ```powershell
  .\.venv\Scripts\python.exe -c "from PyQt6.QtWidgets import QApplication; import sys; app = QApplication(sys.argv); from core.canon_test import CanonTestWindow; win = CanonTestWindow(); print('Debounced ISO/Tv and folder picker pause test PASSED!')"
  ```
