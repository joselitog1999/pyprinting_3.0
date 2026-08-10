# Reporte Técnico de Bugs, Errores Lógicos y Plan de Acción: Rutina de Impresión ("DO PRINTING") en PyPrinting 3.0 🔬

**Laboratorio de Nanofotónica — Instituto de Nanosistemas (INS-UNSAM / CONICET)**  
**Autor Principal**: José Luis González Peñafiel (*Becario Doctoral CONICET*)  
**Fecha de Evaluación**: 10 de Agosto de 2026  
**Documentos de Referencia Auditados**:
- `reportes/Protocolo_y_Guia_de_Impresion_de_Grillas_PyPrinting3.md` *(Modificado recientemente por el usuario)*
- `reportes/Algoritmo_Printing_y_Dimers_PyPrinting3.md`
- `reportes/Correccion_de_Deriva_Termomecanica_Drift_Correction_PyPrinting3.md`
- `main.py`, `app.py`, `modules/measurements.py`, `modules/trace.py`, `modules/focus.py`, `modules/confocal.py`, `config.py`

---

## 1. Resumen de la Auditoría

Se ha completado una revisión código por código sobre **`main.py`** y todas sus dependencias ejecutivas (`app.py`, `measurements.py`, `trace.py`, `focus.py`, `confocal.py`, `config.py`, `nidaq.py`) contrastando el comportamiento esperado según la **Guía Protocolar Actualizada de Impresión ("DO PRINTING")** (`Protocolo_y_Guia_de_Impresion_de_Grillas_PyPrinting3.md`).

El análisis identificó **6 hallazgos clave** (3 de Severidad Alta/Crítica, 2 de Severidad Media y 1 de Interfaz y Documentación):

---

## 2. Diagnóstico Detallado de Bugs y Errores Lógicos

### 🔴 Hallazgos Críticos (Severidad Alta)

#### BUG 1: Desalineación de Conmutación de Potencia Láser (Flipper) en Rutinas de Escaneo Pre/Post y Dímeros
- **Ubicación**: `modules/measurements.py` (`grid_finish_autofoco`, `_grid_center_scan`, `on_scan_finished`).
- **Descripción Físico-Lógica**:  
  Según el protocolo protocolar actualizado (Paso 2 y Paso 4):
  - Los escaneos confocales 2D y el autofoco Z **DEBEN** ejecutarse a **baja potencia** (`up_flipper()`).
  - La traza de fotodiodo para la impresión foto-térmica **DEBE** ejecutarse a **alta potencia** (`down_flipper()`).
- **Falla en Código**:  
  En el modo `dimers` o al retornar de escaneos, `down_flipper()` se ejecutaba justo antes de llamar a `_grid_center_scan()`. Esto provocaba que el escaneo confocal 2D de centrado sobre la partícula 1 se realizara a **alta potencia**, corriendo el riesgo de fotodesintegrar, mover o fundir la nanopartícula de oro por sobrecalentamiento.
- **Impacto**: Daño a las muestras coloidales en experimentos de ensamble de nanodímeros o falsos escaneos quemados.

---

#### BUG 2: Desconexión de los Parámetros `steps_before` y `steps_after` entre `measurements.py` y `trace.py`
- **Ubicación**: `modules/measurements.py` (`_emit_parameters`) $\leftrightarrow$ `modules/trace.py` (`Backend.parameters`).
- **Falla en Código**:  
  Cuando el usuario modifica los casilleros `Steps before` ($M_2$) y `Steps after` ($M$) en el panel gráfico de *Printing Control* y presiona *Play ►*, `MeasBackend.grid_parameters` recibía dichos valores. Sin embargo, **nunca se reemitían ni transmitían a `TraceBackend` (`traceWorker`)**.
- **Impacto**: `TraceBackend` utilizaba de forma permanente sus valores por defecto iniciales ($10$ y $10$), ignorando completamente la configuración de integración fijada por el usuario en la GUI.

---

#### BUG 3: Riesgo de Excepción `IndexError` en `_grid_move()` por Desbordamiento del Índice `i_global`
- **Ubicación**: `modules/measurements.py` (`_grid_move`, `_grid_detect`).
- **Falla en Código**:  
  Si el usuario altera manualmente el casillero `Target Index` o presiona `Next index ►` cuando se encuentra en el último nodo de la grilla ($i = N_{\text{max}}$), el método `_grid_move()` intentaba acceder a `self.grid_x[self.i_global]` sin validar si `i_global < len(self.grid_x)`.
- **Impacto**: Invocación de `IndexError: index X is out of bounds for axis 0 with size X` lanzada desde el hilo secundario, deteniendo la ejecución de la GUI.

---

### 🟡 Hallazgos de Gravedad Media (Estabilidad y Comunicación)

#### BUG 4: Silencio Operativo y Falta de Notificación al Guardar `grid_info.txt` sin Carpeta Creada
- **Ubicación**: `modules/measurements.py` (`grid_info`).
- **Falla en Código**:  
  Si el usuario presiona el botón **`Save info`** antes de haber presionado **`PRINTING folder`** (Paso 8 del protocolo), la función comprobaba `if os.path.exists(self.new_folder):`. Al no existir la carpeta personalizada del lote, finalizaba en silencio sin guardar el archivo y sin informar al usuario.
- **Impacto**: Pérdida inaudita de la metainformación del experimento (`grid_info.txt`).

---

#### BUG 5: Ambigüedad en la Búsqueda del Canal del Fotodiodo (`PD_CHANNELS`) para Lásers en `trace.py`
- **Ubicación**: `modules/trace.py` (`_trace_update`).
- **Falla en Código**:  
  El diccionario `PD_CHANNELS` en `config.py` utiliza como claves los nombres de texto completos:
  `"532 nm (green)"`, `"637 nm (red)"`, `"592 nm (yellow)"`.  
  Si desde la traza se enviaba un texto abreviado como `"637"` o `"red"`, la llamada `PD_CHANNELS.get(active_l1_name, 0)` no encontraba la coincidencia exacta y retornaba por defecto `0` (canal del láser verde 532 nm).
- **Impacto**: Adquisición de la señal analógica en el fotodiodo incorrecto cuando se opera con líneas de excitación secundarias (rojo 637 nm / amarillo 592 nm).

---

## 3. Matriz Comparativa de Cumplimiento del Protocolo "DO PRINTING"

| Paso del Protocolo (`Protocolo_y_Guia_de_Impresion_de_Grillas_PyPrinting3.md`) | Requerimiento Operativo en Software | Estado en Código Actual | Acción Correctiva Propuesta |
|---|---|---|---|
| **Paso 2: Acomodación Óptica** | Selección de Láser en `Low Power` para búsqueda, luego `High Power` para imprimir | ✅ Soportado en UI | Mantener sintonía |
| **Paso 4: Enfoque y Lock Focus** | `Go to maximum (F8)` $\rightarrow$ Shift lateral $\rightarrow$ `Lock Focus (F9)` | ✅ Operativo | Validado |
| **Paso 6: Focus shift & Drift** | Configurar `Autofocus every N`, `Shift x/y`, `Drift Correction`, `Start X/Y` | 🟡 Parcial | Conectar `steps_before` / `steps_after` a `trace.py` |
| **Paso 8: PRINTING folder** | Crear subcarpeta fechada `YYYYMMDD-HHMMSS_Printing_<Grid>` y habilitar metadatos | 🟡 Parcial | Notificar si se pulsa `Save info` antes de crear carpeta |
| **Paso 9: Criterios de Parada** | Soporte de Modos 0 a 3 con Umbral Mínimo permanente y filtro anti-paso $N_{\text{hold}}$ | ✅ Operativo | Integrado y validado |
| **Paso 10: Impresión (`Play ►`)** | Secuencia síncrona: Mover $\rightarrow$ Autofoco $\rightarrow$ Drift $\rightarrow$ Traza $\rightarrow$ Cierre $<1\text{ ms}$ | 🔴 Falla | Corregir estado de Flipper a `up_flipper()` en escaneos 2D |

---

## 4. Plan de Acción Recomendado

1. **Fase 1: Corrección de Potencias y Flipper (BUG 1)**:
   - Garantizar que todo escaneo confocal 2D (`_grid_center_scan`, escaneos de pre-impresión o comprobación) llame explícitamente a `up_flipper()` (baja potencia) antes de emitir `grid_scanSignal`.
   - Conmutar a `down_flipper()` (alta potencia) estrictamente al iniciar `_grid_trace()`.
2. **Fase 2: Interconexión de Parámetros de Integración (BUG 2 & BUG 5)**:
   - Re-emitir `steps_before` y `steps_after` desde `MeasBackend.grid_parameters` hacia `TraceBackend`.
   - Implementar un resolutor de nombres en `trace.py` que soporte claves parciales (`"532"`, `"637"`, `"592"`) asociándolas correctamente a `PD_CHANNELS`.
3. **Fase 3: Protección de Límites y Manejo de Información (BUG 3 & BUG 4)**:
   - Clampear `self.i_global` en `_grid_move()` a `min(self.i_global, len(self.grid_x) - 1)`.
   - Agregar alerta visual y fallback para `grid_info.txt` si la carpeta del lote aún no ha sido creada.
