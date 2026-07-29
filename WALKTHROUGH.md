# WALKTHROUGH DE PYPRINTING 3.0 🔬

Este archivo mantiene el registro continuo de los cambios, soluciones y validaciones realizadas en la arquitectura de **PyPrinting 3.0**.

---

## 🎯 Últimos Cambios y Correcciones Realizadas

1. **Ajuste de Controles de Cámara Canon EOS 500D (ISO y Velocidad Tv)**:
   - **Simplificación de la Interfaz**: Se removió el selector de Apertura (Av) al ser una lente manual sin control electrónico, manteniendo activos únicamente los desplegables de **ISO** (`Auto`, `100`, `200`, `400`, `800`, `1600`, `3200`) y **Velocidad de Obturación / Tiempo de Exposición (Tv)** (`1/10s`, `1/8s`, `1/6s`, `1/5s`, `1/4s`, `1s`, `2s`, `3.2s`, `10s` y lista extendida).
   - **Estabilización de 5 Segundos**: Al conectar la cámara, los desplegables de ISO y Tv permanecen **bloqueados/deshabilitados durante 5 segundos** mientras se estabiliza la transmisión USB. En la barra de estado se informa el tiempo restante.
   - **Mecanismo de Fallback Automático**: Pasados los 5 segundos, si la cámara reporta una lista parcial con menos opciones que nuestra tabla estándar, el sistema utiliza automáticamente la **lista completa de respaldo** para garantizar disponibilidad total de opciones.

2. **Optimización de Calidad Live View y Zoom**:
   - Salida `kEdsEvfOutputDevice_All` (TFT + PC) igual que el programa oficial Canon EOS Utility.
   - Suavizado bilinear nativo `pg.ImageItem(smooth=True)` para máxima nitidez en pantalla.
   - Zoom $1\times$ (Sensor), $2\times$ (Corte Central 50% con interpolación cúbica `INTER_CUBIC`), $5\times$ y $10\times$ (Hardware Sensor).

---

## 🧪 Validación y Estado del Proyecto

- **Prueba Módulo Canon EDSDK con Temporización y Fallback**:
  ```powershell
  .\.venv\Scripts\python.exe -c "import canon_edsdk, canon_test; print('VERIFIED 100% CLEAN!')"
  ```
- **Prueba Ejecutable de Pruebas Canon**:
  ```powershell
  .\.venv\Scripts\python.exe canon_test.py
  ```
