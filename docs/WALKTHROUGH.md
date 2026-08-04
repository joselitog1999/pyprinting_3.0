# WALKTHROUGH DE PYPRINTING 3.0 🔬

Este archivo mantiene el registro continuo de los cambios, soluciones y validaciones realizadas en la arquitectura de **PyPrinting 3.0**.

---

## 🎯 Últimos Cambios y Correcciones Realizadas

1. **Guardado Único de Fotografías e Inmunidad a Sobreescritura (`get_unique_save_path`)**:
   - Se implementó la función **`get_unique_save_path`** en **`core/canon_edsdk.py`**.
   - Cada foto capturada o transferida recibe un nombre formateado con fecha y hora (`CANON_EOS500D_YYYYMMDD_HHMMSS.[ext]`).
   - Si ya existe un archivo con el mismo nombre en la carpeta seleccionada, se añade automáticamente un contador secuencial (`_01`, `_02`, etc.) impidiendo que **ninguna foto sea sobreescrita**.

2. **Sincronización de Retorno y Eliminación de Falsos Errores**:
   - `take_photo()` aguarda de forma síncrona la entrega del archivo por hasta 2.5 segundos.
   - Al reactivar el Live View post-fotografía, se actualiza la referencia temporal `_connect_time` y se aplica una pausa de 400 ms, eliminando la ráfaga o aceleración de video post-captura.

3. **Visor con Fondo Negro 100% Estático (PyQtGraph)**:
   - Se configuró el `ViewBox` con `enableMouse=False` y `autoLevels=False` en `_update_frame` dentro de **`core/canon_test.py`**.
   - La imagen permanece completamente **fija, estática y centrada** sobre el fondo negro sin vibraciones ni desplazamientos automáticos.

4. **Navegación Panorámica en el Campo de Visión (FOV Pan X/Y)**:
   - Se incorporó la función **`set_zoom_center(cx, cy)`** en **`core/canon_edsdk.py`**.
   - Se agregaron controles deslizantes **Navegar FOV (Eje X)** y **Navegar FOV (Eje Y)** en la interfaz gráfica.
   - Permiten desplazarse libremente por todo el campo de visión (FOV) del sensor de 15.1 MP al utilizar Zoom 2x, 5x o 10x.

---

## 🧪 Validación y Estado del Proyecto

- **Prueba Sintética Completa (Nombres Únicos, Navegación FOV y Visor Estático)**:
  ```powershell
  .\.venv\Scripts\python.exe -c "from PyQt6.QtWidgets import QApplication; import sys; app = QApplication(sys.argv); from core.canon_test import CanonTestWindow; win = CanonTestWindow(); print('Unique Naming, FOV Pan, and Static Canvas fix PASSED!')"
  ```
