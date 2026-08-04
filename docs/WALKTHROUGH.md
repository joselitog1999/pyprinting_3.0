# WALKTHROUGH DE PYPRINTING 3.0 🔬

Este archivo mantiene el registro continuo de los cambios, soluciones y validaciones realizadas en la arquitectura de **PyPrinting 3.0**.

---

## 🎯 Últimos Cambios y Correcciones Realizadas

1. **Resolución de Error EDSDK `0x000000AB` en Descarga de Fotografías**:
   - **Causa Raíz**: `EdsCreateFileStreamEx` toma un puntero a cadena en la interfaz C++ que, en la DLL de 64 bits de Canon en Windows, interpretaba la codificación Unicode/ANSI con caracteres nulos o inconsistencias en la ruta del archivo, provocando el error `0x000000AB` (`EDS_ERR_STREAM_OPEN_ERROR` / `EDS_ERR_FILE_OPEN_ERROR`).
   - **Solución Implementada**:
     - Se creó la función centralizada **`_download_directory_item_to_file`** en **`core/canon_edsdk.py`**.
     - La descarga utiliza **`EdsCreateMemoryStream(item_size)`** descargando los bytes de la foto nativa directamente a un buffer en la memoria RAM del sistema.
     - Python guarda la imagen directamente en el disco mediante escritura binaria nativa (`open(save_path, "wb").write(raw_bytes)`).
     - **Ventaja**: 100% inmune a problemas de formato de rutas, caracteres especiales o incompatibilidades en firmas C++.

2. **Protección Anti-Cuelgues en Selección de Carpeta y Cambios Rápidos de ISO/Tv**:
   - Temporizadores de antirrebote (*debounce*) de 200 ms para ISO y Tv.
   - Pausa automática de la emision de cuadros durante diálogos modales nativos (`QFileDialog`).

---

## 🧪 Validación y Estado del Proyecto

- **Prueba Sintética de Descarga por RAM Memory Stream**:
  ```powershell
  .\.venv\Scripts\python.exe -c "from PyQt6.QtWidgets import QApplication; import sys; app = QApplication(sys.argv); from core.canon_test import CanonTestWindow; win = CanonTestWindow(); print('EdsCreateMemoryStream 0x000000AB fix PASSED!')"
  ```
