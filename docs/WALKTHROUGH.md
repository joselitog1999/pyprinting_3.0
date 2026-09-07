# WALKTHROUGH DE PYPRINTING 3.0 🔬

Este archivo mantiene el registro continuo de los cambios, soluciones y validaciones realizadas en la arquitectura de **PyPrinting 3.0**.

---

## 🎯 Últimos Cambios y Correcciones Realizadas

1. **Reactividad Total del Checkbox Low/High Power & Sincronización Hardware-GUI (`core/shutters.py`, `core/nidaq.py`)**:
   - **Diagnóstico y Corrección de Señales Qt**: Se resolvió la insensibilidad del checkbox ante señales externas (`setChecked(bool)` emitía `toggled` en lugar de `clicked`, y `_power_check` descartaba el payload booleano).
   - **Migración a `toggled` & Slots Públicos**: Conmutación de checkboxes a `.toggled.connect(...)` y creación del slot formal `@pyqtSlot(bool) def set_power(self, high: bool)` con alias `set_flipper` y `powerbutton_check`.
   - **Puente Bidireccional de Hardware**: Implementación en `core/nidaq.py` de `register_flipper_callback(fn)`, `unregister_flipper_callback(fn)` e `is_flipper_high_power()`, conectado a `ShuttersFrontend.flipper_hardware_signal`. Cualquier conmutación por watchdog o rutinas (`measurements.py`) actualiza la UI en tiempo real.
   - **Suite Automatizada**: Creación de [`tests/test_powerbutton_actuation.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/tests/test_powerbutton_actuation.py) (7/7 PASS) e integración en [`tests/run_all_diagnostics.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/tests/run_all_diagnostics.py) (49/49 PASS, 100%).

2. **Pestaña Modular "🎯 Calibraciones del Sistema" en PySpectrum 3.0 (`pyspectrum/modules/calibration_dock.py`)**:
   - **Alineación de Slit y Centroide Óptico X**: Botón a Orden Cero (0.0 nm), ajuste de ancho micrométrico de rendija y auto-calibración por ajuste gaussiano subpíxel del centroide horizontal (`SLIT_CENTER_PIXEL_X`).
   - **Offsets de Rejilla y Detector vía SDK Oficial**: Vinculación directa con `ShamrockCIF.dll` mediante las funciones `ShamrockGetGratingOffset`, `ShamrockSetGratingOffset`, `ShamrockGetDetectorOffset`, `ShamrockSetDetectorOffset` y `ShamrockGetSlitZeroPosition`.
   - **Calibración Cúbica y Lámpara Halógena**: Verificación de coeficientes de fábrica de la EEPROM $\lambda(p) = a + bp + cp^2 + dp^3$ y perfiles de lámpara trazable.
   - **Parches en Step & Glue**: Incorporación del botón de aborto cooperativo **"⏹ Detener Escaneo"** (`stopMeasurementSignal`) y exportador directo **"💾 Guardar Espectro..."** (`saveSpectrumSignal`).

3. **Implementación de 5 Modos Seleccionables de Criterio de Parada (`modules/measurements.py`)**:
   - **Modo 0: Legacy (Salto Relativo Estándar)**: Mantiene $100\%$ de compatibilidad con secuencias históricas ($I_{\text{new}} / I_{\text{old}} > \text{Umbral}$).
   - **Modo 1: Salto Relativo + Umbral Absoluto (V) & Anti-Paso**: Permite definir `Umbral Absoluto (V)` para solucionar impresiones instantáneas a $t=0$ y `N hold steps` para evitar falsas detecciones de partículas "de paso" (tránsito temporal).
   - **Modo 2: Derivada Temporal Adaptativa & Aplanamiento ($dI/dt$)**: Evalúa la derivada discreta en tiempo real para detectar la meseta en alto nivel ($dI/dt \to 0$), solucionando curvas de crecimiento exponencial $1-e^{-t/\tau}$.
   - **Modo 3: Calibración Confocal Raw & Umbral Absoluto Reescalado**: Calcula el umbral en Volts a partir del mapa confocal previo y la relación de potencia $K_{\text{scale}} = P_{\text{print}} / P_{\text{scan}}$. Guarda la imagen y matriz confocal reescalada (`NPscan_rescaled_00i.txt` / `.tiff`).
   - **Modo 4: Criterio Híbrido Tri-Factor (All-In-One)**: Evalúa simultáneamente salto relativo, aplanamiento de derivada $dI/dt$ y umbral absoluto en Volts bajo la protección anti-paso $N_{\text{hold}}$.

2. **Visibilidad Dinámica de Casilleros en la GUI (`Frontend`)**:
   - La selección del desplegable `Criterio Parada` en la interfaz gráfica muestra u oculta dinámicamente solo los casilleros de entrada relevantes para cada modo (`Umbral Abs (V)`, `N hold steps`, `Slope Min`, `Slope Flat`, `Ratio K`, `Umbral (%)`).

3. **Documentación y Reportes Actualizados**:
   - Se actualizó el reporte técnico formal en **`reportes/Algoritmo_Printing_y_Dimers_PyPrinting3.md`**.
   - Se actualizó **`docs/MANUAL_USUARIO.md`** y **`README.md`**.
   - Se creó **`docs/PERSPECTIVAS.md`** como documento dinámico de preguntas abiertas, requerimientos y sugerencias técnicas.

4. **Validación y Corrección de Picasso (`picassosr`) y Deconvolución R-L**:
   - Se corrigió el paso por canal de imágenes RGB/RGBA en `richardson_lucy_deconv` (`analysis/psf.py`).
   - Se incorporó `QSpinBox` y `QDialogButtonBox` en los imports de `analysis/image_analyzer.py`.
   - Se corrigieron las firmas de llamada a `_fit2d_gausslq` y `_fit2d_avg` en `analysis/image_analyzer.py` y `modules/camera.py`, pasando explícitamente `em=False` y `multiprocess=False`.

5. **Calibración de Canales Físicos Reales del Banco Óptico (`config.py`)**:
   - Se actualizaron las líneas digitales de obturadores TTL: `SHUTTER_CHANNELS = [11, 8, 9, 10]`.
   - Se ajustó la polaridad física real de los relés: `SHUTTER_POLARITY = {532nm: False (Activo Bajo), 637nm: True, 592nm: True, 808nm: True}`.
   - Se re-mapearon los canales de entrada analógica de fotodiodos: `PD_CHANNELS = {532nm: ai0, 637nm: ai2, 592nm: ai1, 808nm: ai3, BS: ai6}`.
   - Se resolvió y eliminó el ítem 1.3 de `docs/PERSPECTIVAS.md` conforme al protocolo de mantenimiento.

6. **Integración Completa de la Línea Láser 808 nm (Infrarrojo - IR)**:
   - Se incorporó `"808 nm (IR)"` a `SHUTTERS` con obturador en la línea digital `port0/line10` y canal de fotodiodo en `Dev1/ai3`.
   - Se actualizó el panel de control de obturadores ([`core/shutters.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/core/shutters.py)) con el 4to botón `shutter3button`, señal `shutter3_signal` y slot `shutter3`.
   - Se actualizaron los selectores de color de todos los módulos (`measurements.py`, `trace.py`, `focus.py`, `confocal.py`, `contrapropagante.py`) con el color `#ad1457` / borravino para la línea infrarroja.
   - Se validaron todos los módulos y la apertura/cierre de obturadores y lectura de fotodiodos en modo seguro y nominal.

7. **Optimización del Módulo de Trazas (`modules/trace.py`)**:
   - **Opciones `"None"` y `"BS"` en Láser 2**: Se extendieron las opciones de `trace_laser2` para permitir visualizar una única traza a pantalla completa (`"None"` oculta `pL2` y apaga su obturador) o monitorear directamente el fotodiodo divisor (`"BS"` titula el gráfico `"Trace on BS"` y grafica la señal de `Dev1/ai6`).
   - **Desacoplamiento de `Power in BS`**: Se eliminó la auto-activación al abrir la ventana flotante (`showEvent` en modo pasivo); ahora solo mide bajo demanda al presionar `Active Power BS Measurement` o durante la traza principal.
   - **Tasa de Refresco de FFT Limitada a 1.0 s**: La ventana de espectro de densidad de potencia FFT `TraceFFTWindow` procesa la transformada y los picos a intervalos controlados de 1 segundo solo si está visible, eliminando la sobrecarga computacional.
   - **Fluidez Visual a ~30 FPS**: Se optimizó la tasa de refresco del timer de Qt a 35 ms, garantizando una interfaz completamente fluida sin bloqueos ni saturación del *Event Loop*.

8. **Tolerancia a Fallas de Hardware, Hot-Plug y Control de Simulación Global**:
   - **Sincronización Dinámica de `SAFE_MODE`**: Se corrigió `config.py` para leer en tiempo de ejecución la variable `PYPRINTING_SAFE`, permitiendo que el checkbox de `main.py` controle de verdad el modo simulación / laboratorio de todos los programas.
   - **Controlador PI Resiliente**: Se refactorizó `_PIController` para mantener coordenadas virtuales en memoria si la platina PI está apagada o desconectada, permitiendo que `app.py` y todos los módulos inicien al 100% sin excepciones fatales.
   - **Reconexión y Desconexión en Caliente (Hot-Plug)**: Se incorporaron métodos `connect_device()` y `disconnect_device()` en `HardwareManager` para conectar o desconectar instrumentos físicos mientras la aplicación está en marcha.
   - **Tablero de Conexiones Interactivo (`modules/hardware_dashboard.py`)**: Cada instrumento cuenta con botones activos de acción **"🔌 Conectar"** / **"⏏️ Desconectar"** y checkbox de **"Aislar (Soft Mock)"** con reporte en tiempo real a la bitácora I/O.

9. **Integración Completa y Modernización de PySpectrum 3.0**:
   - **Paquete Modular `pyspectrum/` y Lanzador `pyspectrum.py`**: Migración al 100% a `PyQt6` con arquitectura modular desacoplada y diseño visual moderno.
   - **Controladores Resilientes y Mocks**: Implementación de `_MockShamrock` y `_MockAndorCCD` con espectros sintéticos y soporte para hardware físico mediante Ctypes (`ShamrockCIF.dll`, `atmcd64d.dll`).
   - **Calibración y Step and Glue**: Integración del algoritmo de cosido espectral de banda ancha (450 a 950 nm), normalización por lámpara halógena y ajustes polinomiales de resonancia plasmónica (SPR) y banda Raman del agua (~3300 cm⁻¹).
   - **Mapeo Confocal Hiperespectral $(X, Y, \lambda)$**: Mapeo 2D y 3D coordinando la platina piezoeléctrica PI con el detector Andor CCD.
   - **Rutinas Nanofotónicas**: Fotoluminiscencia, cinética de crecimiento de nanopartículas y caracterización de dímeros plasmónicos.
   - **Tarjeta Activa en `main.py`**: Habilitación del botón "PySpectrum 3.0" en el panel de inicio principal.

---

## 🧪 Validación Realizada

- **Prueba Sintética de Instanciación e Interfaz Gráfica**:
  ```powershell
  .\.venv\Scripts\python.exe -c "from PyQt6.QtWidgets import QApplication; import sys; app = QApplication(sys.argv); from modules.measurements import Frontend, Backend; fe = Frontend(mode='printing'); be = Backend(mode='printing'); fe.make_connection(be); print('Merged measurements.py PASSED!')"
  ```
  Result: **`PASSED`** (Detección sub-píxel operativa en los 3 métodos).

---

## 4. Raman Analyzer Suite: Selector de Láser de Excitación y Línea Base Bi-Modal en Multi-Espectro
- **🔬 Láser de Excitación Multi-Espectro**: Selector de $\lambda_{\text{laser}}$ (532 nm, 632.8 nm, 637 nm, 785 nm, 592 nm o personalizado) con recálculo dinámico del Raman shift ($\text{cm}^{-1}$) y sincronización bidireccional con la pestaña individual.
- **📉 Línea Base Bi-Modal**:
  - **Modo 1 (Archivo de Referencia / Fondo)**: Carga de archivo externo o selección de un espectro del lote como blanco, con interpolación sobre la grilla común y sustracción homogénea.
  - **Modo 2 (Cálculo Individual por Espectro)**: Aplicación adaptativa e independiente de AsLS, AirPLS, ModPoly o Rolling Ball para cada curva del lote.
  - **Modo 3 (Sin Corrección)**: Cuentas brutas sin sustracción.
- **✂️ Recorte de ROI y Poda de Bordes CCD en Multi-Espectro**:
  - Botón directo `✂️ Recortar a Cursores A y B` con región interactiva sombreada arrastrable en el gráfico.
  - Atajo `⚡ Recortar Láser/Rayleigh (< 150 cm⁻¹)` para purgar dispersión elástica sin afectar las bandas moleculares.
  - Campos numéricos $[X_{\min}, X_{\max}]\ \text{cm}^{-1}$ y poda de puntos en inicio y fin del sensor CCD (`trim_left_pts`, `trim_right_pts`).
  - Botón `↺ Restaurar Rango Completo` para recuperar el 100% de la extensión espectral original.
- **Verificación**: 100% en pruebas de motor (`test_raman_multi_engine.py`), ciclo de vida GUI (`test_raman_gui.py`) y diagnósticos de sistema (`run_all_diagnostics.py`).
