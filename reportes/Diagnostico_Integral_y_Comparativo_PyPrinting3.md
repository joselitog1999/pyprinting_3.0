# Diagnóstico Integral y Análisis Comparativo de PyPrinting 3.0 vs PyPrinting 2

**Fecha de Ejecución**: 7 de Agosto de 2026  
**Ámbito del Diagnóstico**: `main.py`, `app.py`, `contrapropagante.py`, `modules/measurements.py`, `modules/trace.py`, `modules/focus.py`, `modules/confocal.py`, `modules/camera.py`, `config.py`, `nidaq.py`, `pi.py`.  
**Referencia Ground Truth**: `c:\Users\josel\Documents\Obsidian_Vault\printing2` (PyPrinting 2).

---

## 1. Resumen Ejecutivo

Se ha realizado una auditoría exhaustiva y un análisis estático/dinámico sobre la totalidad del código fuente de **PyPrinting 3.0**, contrastándolo línea por línea con **PyPrinting 2**. Se evaluaron los flujos de control de hardware, temporización de obturadores, adquisición de fotodiodos en NI-DAQ, servocontrol de la platina piezoeléctrica PI, hilos de ejecución `QThread`, señales/slots PyQt6, criterios de parada y el nuevo módulo de microscopía contrapropagante.

Se han identificado **10 hallazgos principales** (divididos en 5 Críticos, 3 Medios y 2 Menores/Optimización), destacándose una desconexión fundamental en el cálculo de las promedios móviles para los criterios de parada de la traza, así como vulnerabilidades en la conmutación de baja/alta potencia del láser (flipper) y en el manejo de imágenes TIFF.

---

## 2. Diagnóstico Detallado de Hallazgos por Gravedad

### 🔴 Hallazgos Críticos (Afectan la Operación Correcta e Impresión en Laboratorio)

#### 1. Cálculo Desconectado de Baseline ($I_{\text{old}}$) y Señal Actual ($I_{\text{new}}$) en Criterios de Parada
- **Ubicación**: `modules/trace.py` y `modules/measurements.py` (`grid_trace_detect`).
- **Comportamiento en PyPrinting 2**:
  En `Trace_pp.py`, el backend de la traza calculaba ventanas temporales móviles de integración:
  - $I_{\text{old}} = \text{promedio}(I[N - M - M_2 : N - M])$ (promedio de la señal previa al evento, de tamaño `steps_before` $M_2$).
  - $I_{\text{new}} = \text{promedio}(I[N - M : N])$ (promedio de la señal actual del evento, de tamaño `steps_after` $M$).
- **Falla en PyPrinting 3**:
  En `modules/measurements.py`, `grid_trace_detect` calculaba:
  ```python
  I_old = float(self.data1[0])   # ¡Toma la primera muestra estática de toda la sesión!
  I_new = float(self.data1[-1])  # ¡Toma una única muestra instantánea ruidosa!
  ```
- **Impacto**: Los casilleros de la interfaz `steps_before` y `steps_after` eran completamente ignorados. Un solo pico de ruido térmico o eléctrico en `I_new` disparaba un falso positivo de impresión, cerrando el obturador instantáneamente antes de la llegada real de una nanopartícula.
- **Solución Requerida**: Restaurar el cálculo exacto de ventanas móviles $M$ y $M_2$ en `modules/trace.py` y transmitir `I_old` e `I_new` integrados en el vector de datos hacia `grid_trace_detect`.

---

#### 2. `AttributeError` por Obturador/Láser No Inicializado en Autofoco Axial (`modules/focus.py`)
- **Ubicación**: `modules/focus.py` (`focus_autocorr_lin_x2`).
- **Falla**: El método `focus_autocorr_lin_x2` ejecuta `open_shutter(self.laser)`. Sin embargo, `self.laser` solo se define cuando el usuario presiona manualmente los botones "Go to maximum" (`focus_go_to_maximum`) o "Lock focus" (`focus_lock_lin`).
- **Impacto**: Si la grilla de impresión dispara el autofoco automático ($N$ partículas) o el usuario presiona **F10** directamente al iniciar la aplicación, se produce la caída inmediata del programa con el error:
  `AttributeError: 'Backend' object has no attribute 'laser'`.
- **Solución Requerida**: Inicializar `self.laser = SHUTTERS[0]` en el `__init__` de `FocusBackend` y validar su asignación previa a la apertura del obturador.

---

#### 3. Desfase en Conmutación de Potencia (Flipper) durante Autofoco y Drift Correction
- **Ubicación**: `modules/measurements.py` (`grid_autofoco`, `grid_finish_autofoco`, `on_scan_finished`).
- **Comportamiento Requerido**:
  1. Durante el escaneo confocal de **Drift Correction** y durante el **Autofoco Z**, el flipper DEBE estar ARRIBA (`up_flipper()`, baja potencia).
  2. Para la **Impresión por Traza**, el flipper DEBE estar ABAJO (`down_flipper()`, alta potencia).
- **Falla**: En `grid_finish_autofoco()`, si `driftbool` estaba activo, el flipper permanecía arriba para el escaneo de drift, pero al concluir en `on_scan_finished()`, no se garantizaba la restitución del flipper si el próximo nodo desencadenaba inmediatamente un autofoco sin impresión intermedia.
- **Solución Requerida**: Unificar la máquina de estados del flipper garantizando que la transición a alta potencia ocurra estrictamente al inicio de la llamada a `_grid_trace()`.

---

#### 4. `TypeError` en Guardado de Imágenes TIFF Confocales (`modules/measurements.py` / `contrapropagante.py`)
- **Ubicación**: `modules/measurements.py` (`_save_scan`) y `contrapropagante.py`.
- **Falla**: La función de guardado ejecuta `Image.fromarray(np.transpose(image)).save(...)`. Cuando los datos del escaneo confocal provienen directamente de NI-DAQ en punto flotante 64-bit (`np.float64` con valores en Voltios), la librería `PIL.Image` falla lanzando `TypeError: Cannot handle this data type`.
- **Solución Requerida**: Normalizar y reescalar las matrices escaneadas a `uint16` o utilizar `tifffile` / reescalado lineal 8/16-bit antes de llamar a `Image.fromarray()`.

---

#### 5. Sincronización Incompleta de Hilos en `contrapropagante.py` (Microscopio Dual)
- **Ubicación**: `contrapropagante.py` (`Backend._connect_backends`).
- **Falla**: El módulo contrapropagante instancia `ConfocalDualBackend` para escanear simultáneamente las confocales TOP (arriba) y BOT (abajo). No obstante, las señales `scanfinishedSignal` de escaneo dual no están interconectadas con `printingWorker` ni `dimersWorker`, impidiendo que el protocolo de impresión automática opere en la suite contrapropagante.
- **Solución Requerida**: Cablear las señales de fin de escaneo `scanfinishedSignal` en `contrapropagante.py` al igual que en `app.py`.

---

### 🟡 Hallazgos de Gravedad Media (Estabilidad y Flujo de Trabajo)

#### 6. Ausencia de Verificación de Estabilización Mecánica de Platina PI
- **Ubicación**: `modules/measurements.py` (`_grid_move`).
- **Comparación con PyPrinting 2**: En PyPrinting 2, la función `moveto()` incluía un bucle de espera explícito:
  ```python
  while not all(pi_device.qONT(axis).values()):
      time.sleep(0.01)
  ```
- **Falla en PyPrinting 3**: En `_grid_move()`, solo se coloca `time.sleep(0.1)`. En saltos largos entre columnas de la grilla (ej. 10–50 µm), 100 ms puede no ser suficiente para amortiguar la oscilación mecánica de la platina piezoeléctrica, abriendo el obturador mientras la platina aún está en movimiento.
- **Solución Requerida**: Insertar la verificación explícita `pi.qONT([1, 2])` en `_grid_move()`.

---

#### 7. Reinicio Incompleto del Estado al Pausar o Cancelar Impresión
- **Ubicación**: `modules/measurements.py` (`grid_pause`).
- **Falla**: Al pausar la impresión, se cierran los obturadores, pero `self.mode_printing` no se resetea a `"none"`. Si el usuario presiona "Play" nuevamente, el flujo intenta continuar sin reposicionar el índice o verificar si la referencia ha sido modificada.
- **Solución Requerida**: Asegurar que `grid_pause` detenga la traza, cierre obturadores y restablezca los estados de flags de forma segura.

---

#### 8. Calculador de Errores de Impresión ($X, Y$) sin Normalización de Datos Vacíos
- **Ubicación**: `modules/measurements.py` (`_grid_printing_error`).
- **Falla**: Cuando el escaneo post-impresión está desactivado (`scanbool` en Falso), la función `_grid_printing_error` intenta acceder al `center_mass` vacante, generando entradas `NaN` o listas desalineadas en el archivo de texto `printing_error_*.txt`.
- **Solución Requerida**: Condicionar el cálculo y guardado de errores de impresión a la existencia de un `center_mass` válido (longitud $\ge 2$).

---

### 🟢 Hallazgos Menores / Optimizaciones

#### 9. Señales "Huérfanas" o Duplicadas en PyQt6
- **Ubicación**: `app.py`, `contrapropagante.py`.
- **Falla**: Se detectaron señales emitidas que no poseen receptores conectados o conectores redundantes (ej. `gridinfoSignal` en algunos sub-widgets).
- **Solución Requerida**: Limpieza de señales no utilizadas y unificación de conectores.

#### 10. Normalización de Visualización de Traza en Pantalla
- **Ubicación**: `modules/trace.py` (`get_data`).
- **Optimizacion**: Al graficar la traza en tiempo real en `pyqtgraph`, se procesan fragmentos completos del vector. Limitar el arreglo trazado a las últimas $1000$ muestras maximiza el rendimiento de la GUI a $60$ FPS sin consumo excesivo de CPU.

---

## 3. Matriz Comparativa de Lógica: PyPrinting 2 vs PyPrinting 3.0

| Componente / Característica | PyPrinting 2 (Legacy) | PyPrinting 3.0 (Estado Actual) | Estado & Acción Requerida |
| :--- | :--- | :--- | :--- |
| **Integración Muestras Traza ($I_{\text{old}}, I_{\text{new}}$)** | Promedio móvil en ventanas $M$ y $M_2$ | Muestra $0$ e instante final $-1$ (Instantáneo) | 🔴 **Corregir**: Restaurar integradores $M, M_2$ |
| **Selección Láser Autofoco** | Variable global de láser seleccionada | Atributo no garantizado (`AttributeError`) | 🔴 **Corregir**: Inicializar `self.laser` por defecto |
| **Guardado de TIFF Confocal** | Vía PIL / PIL.Image sin reescalado | Vía PIL `fromarray` (Falla en `float64`) | 🔴 **Corregir**: Reescalar/Convertir matriz a `uint16` |
| **Espera de Platina PI (`qONT`)** | Bucle activo `while not qONT()` | Retardo fijo `time.sleep(0.1)` | 🟡 **Corregir**: Agregar `qONT` explícito |
| **Drift Correction Acumulado** | No disponible (solo escaneo manual) | Posición absoluta del ancla en nm | 🟢 **Correcto**: Operativo y comprobado |
| **Casillero Umbral Mínimo (V)** | No disponible | Permanente y restrictivo en todos los modos | 🟢 **Correcto**: Operativo y comprobado |
| **Suite Contrapropagante** | No disponible | Implementado en `contrapropagante.py` | 🟡 **Corregir**: Conectar señales de fin de escaneo |

---

## 4. Plan de Acción Recomendado

1. **Fase 1 (Inmediata - Reparación de Criterios de Parada y Autofoco)**:
   - Modificar `modules/trace.py` para calcular $I_{\text{old}}$ ($M_2$ `steps_before`) e $I_{\text{new}}$ ($M$ `steps_after`) mediante promedios móviles antes de emitir a `grid_trace_detect`.
   - Inicializar `self.laser = SHUTTERS[0]` en `FocusBackend` (`modules/focus.py`).
2. **Fase 2 (Estabilidad de Hardware y Datos)**:
   - Insertar comprobación `pi.qONT([1, 2])` en `_grid_move()` (`modules/measurements.py`).
   - Convertir arreglos de escaneo a `uint16` en `_save_scan()` y `_save_rescaled_scan()`.
3. **Fase 3 (Sincronización Contrapropagante)**:
   - Conectar las señales de escaneo dual en `contrapropagante.py` para habilitar impresión en configuración invertida.
