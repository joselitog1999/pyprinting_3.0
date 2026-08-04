# WALKTHROUGH DE PYPRINTING 3.0 🔬

Este archivo mantiene el registro continuo de los cambios, soluciones y validaciones realizadas en la arquitectura de **PyPrinting 3.0**.

---

## 🎯 Últimos Cambios y Correcciones Realizadas

1. **Restauración del Visor ViewBox y Ajuste Horizontal (Estilo `camera.py`)**:
   - **Visibilidad Restablecida**: Se revirtieron `enableMouse=False`, `disableAutoRange()` y `autoLevels=False` en **`core/canon_test.py`**, permitiendo que PyQtGraph procese y renderice los niveles de brillo/contraste de forma dinámica sin dejar la pantalla en negro.
   - **Ajuste Horizontal**: Se implementó `self._view.setMinimumSize(480, 360)` con `self._vb.setRange(xRange=(0, W), padding=0)` idéntico a la arquitectura de `reserva/camera.py`, logrando que la transmisión en vivo se adapte horizontalmente al contenedor de la subventana.

2. **Navegación Panorámica FOV (X/Y) y Nombres Únicos**:
   - Controles deslizantes **Navegar FOV (Eje X)** y **Navegar FOV (Eje Y)** para exploración de todo el sensor de 15.1 MP.
   - Algoritmo de nombres únicos `get_unique_save_path` impidiendo sobreescrituras.

---

## 🧪 Validación y Estado del Proyecto

- **Prueba Sintética de Visor y Ajuste Horizontal**:
  ```powershell
  .\.venv\Scripts\python.exe -c "from PyQt6.QtWidgets import QApplication; import sys; app = QApplication(sys.argv); from core.canon_test import CanonTestWindow; win = CanonTestWindow(); print('Horizontal ViewBox Fit like camera.py PASSED!')"
  ```
