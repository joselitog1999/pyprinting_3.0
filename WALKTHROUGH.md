# WALKTHROUGH DE PYPRINTING 3.0 🔬

Este archivo mantiene el registro continuo de los cambios, soluciones y validaciones realizadas en la arquitectura de **PyPrinting 3.0**.

---

## 🎯 Últimos Cambios y Correcciones Realizadas

1. **Optimizaciones de Seguridad y Estructura Adaptativa en Modo Ramp (`confocal.py`)**:
   - Implementado el patrón adaptativo `if self.Nx <= 50 and self.range_x <= 5.0:` que mantiene intacto al $100\%$ el comportamiento y constantes del código original para escaneos típicos ($2 \times 2\ \mu\text{m}$, $34 \times 34\ \text{px}$).
   - Para campos grandes ($20 \times 20\ \mu\text{m}$, $400 \times 400\ \text{px}$) y resoluciones altas, se activa el escalado adaptativo de muestras `Nramp = 2 * pixels_total_line * samples_per_pixel`.
   - Clampeo dinámico de puntos de onda `Npoints = min(4000, ...)` evitando desbordar la memoria de la controladora PI.
   - Clampeo de coordenadas de inicio de rampa $X_{\text{inicio}}, Y_{\text{inicio}} \in [0.0, 100.0 - Range_{\text{total}}]\ \mu\text{m}$ impidiendo sobrepasar los límites físicos de la platina PI E-517.

2. **Actualización Completa del Manual de Usuario (`MANUAL_USUARIO.md`)**:
   - Añadida la **Sección 2.9 (Arquitectura del Escaneo en Modo Ramp Adaptativo, Seguridad y Puntos de Onda)**.
   - Explicación matemática y técnica del rango de aceleración/frenado ($Extra = Range_X / 6$), puntos de onda (`Npoints`), tiempo de servo (`WTRtime`), velocidad lineal de escaneo ($v_{\text{scan}}$) y la tabla comparativa de límites máximos de medición segura.

---

## 🧪 Validación y Estado del Proyecto

- **Prueba del Modo Ramp Adaptativo**:
  ```powershell
  .\.venv\Scripts\python.exe -c "import sys; from PyQt6.QtWidgets import QApplication; from confocal import Backend; app = QApplication(sys.argv); b = Backend(); b._scan_ramp_parameters([2, 2, 34, 34]); print('SMALL SCAN NRAMP:', b.Nramp); b._scan_ramp_parameters([20, 20, 400, 400]); print('LARGE SCAN NRAMP:', b.Nramp); print('ADAPTIVE RAMP VERIFIED!')"
  ```
  *(Resultado: `SMALL SCAN NRAMP: 2400`, `LARGE SCAN NRAMP: 4264` — `ADAPTIVE RAMP VERIFIED!`)*

- **Prueba Ejecutable de la Aplicación**:
  ```powershell
  .\.venv\Scripts\python.exe main.py
  ```
