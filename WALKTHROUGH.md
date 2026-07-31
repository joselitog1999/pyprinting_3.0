# WALKTHROUGH DE PYPRINTING 3.0 🔬

Este archivo mantiene el registro continuo de los cambios, soluciones y validaciones realizadas en la arquitectura de **PyPrinting 3.0**.

---

## 🎯 Últimos Cambios y Correcciones Realizadas

1. **Accionamiento Directo del Shutter 532 nm en `Laser532Window` (`camera.py`)**:
   - Reemplazada la funcionalidad anterior del botón (que fijaba el voltaje a $1.0\text{ V}$) por un botón interactivo de conmutación de obturador:
     - **`► Abrir Shutter 532 nm (Cerrado)`** (Verde `#2e7d32`): Llama a `open_shutter("532 nm (green)")`.
     - **`■ Cerrar Shutter 532 nm (Abierto)`** (Rojo `#c62828`): Llama a `close_shutter("532 nm (green)")`.
   - Incorporación de la señal `shutter532Signal(bool)` para notificar cambios de estado del obturador.

2. **Lanzador Principal `main.py` ("Bienvenidos al printing")**:
   - Configurado para lanzar `camera.py` en la tarjeta de cámara Live View (mientras `canon_test.py` continúa en fase de pruebas).
   - Incorporadas tarjetas ejecutables para `Laser532Window` y `PyPrinting 2 (Legacy)`.
   - Reservadas tarjetas y documentación de Roadmap para **PySpectrum** y el **Microscopio Contrapropagante**.

---

## 🧪 Validación y Estado del Proyecto

- **Prueba de Conmutación de Shutter 532 nm**:
  ```powershell
  .\.venv\Scripts\python.exe -c "import sys; from PyQt6.QtWidgets import QApplication; from camera import Laser532Window; app = QApplication(sys.argv); win = Laser532Window(); win.show(); win._toggle_shutter_532(True); win._toggle_shutter_532(False); print('LASER 532 SHUTTER TOGGLE VERIFIED!')"
  ```
  *(Resultado: `[NI MOCK] open_shutter(532 nm (green))`, `[NI MOCK] close_shutter(532 nm (green))` — `LASER 532 SHUTTER TOGGLE VERIFIED!`)*

- **Prueba Ejecutable de la Aplicación**:
  ```powershell
  .\.venv\Scripts\python.exe main.py
  ```
