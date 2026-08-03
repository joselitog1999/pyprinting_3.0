# WALKTHROUGH DE PYPRINTING 3.0 🔬

Este archivo mantiene el registro continuo de los cambios, soluciones y validaciones realizadas en la arquitectura de **PyPrinting 3.0**.

---

## 🎯 Últimos Cambios y Correcciones Realizadas

1. **Remoción de PyPrinting 2 y Reorganización de la Grilla Principal (`main.py`)**:
   - Se eliminó la tarjeta legacy de PyPrinting 2 de la grilla de `main.py` para evitar ejecuciones accidentales con versiones antiguas de Python/PyQt5.
   - La grilla principal ahora cuenta con 8 tarjetas integradas limpiamente:
     - **Fila 1**: Microscopio Derecho (`app.py`), PySpectrum (Próximamente), Microscopio Contrapropagante (`contrapropagante.py`).
     - **Fila 2**: Cámara Live View (`camera.py`), Modulación Láser 532 nm, PSF Analyzer (`psf_analyzer.py`).
     - **Fila 3**: Analizador de Imágenes (`image_analyzer.py`), Documentación y Créditos Institucionales.

2. **Protección de Exclusión Mutua para Hardware Real (Modo Laboratorio)**:
   - Se implementó un control en `_launch_script` en `main.py` que previene lanzar **Microscopio Derecho** (`app.py`) y **Microscopio Contrapropagante** (`contrapropagante.py`) simultáneamente cuando el **Modo Seguro (Simulación)** está desmarcado.
   - Si se intenta lanzar un segundo microscopio en Modo Laboratorio, el sistema interrumpe el lanzamiento y despliega una advertencia modal:
     > *"No es posible iniciar el microscopio en MODO LABORATORIO mientras la otra suite se encuentra en ejecución para evitar conflictos de competencia física por la platina PI E-517 y la tarjeta NI-DAQmx."*
   - En **Modo Seguro (Simulación)** se permite la ejecución simultánea de ambas instancias para depuración sin hardware.

3. **Verificación de Delimitadores ($0.0 - 100.0\ \mu\text{m}$)**:
   - Clampeo estricto de límites en `nanopositioning.py` y `contrapropagante.py`.

---

## 🧪 Validación y Estado del Proyecto

- **Prueba Sintética en MODO SEGURO (SAFE_MODE)**:
  ```powershell
  .\.venv\Scripts\python.exe -c "from PyQt6.QtWidgets import QApplication; import sys; app = QApplication(sys.argv); from main import MainWindowLauncher; win = MainWindowLauncher(); print('Lanzador OK')"
  ```
- **Ejecución del Lanzador Principal**:
  ```powershell
  .\.venv\Scripts\python.exe main.py
  ```
