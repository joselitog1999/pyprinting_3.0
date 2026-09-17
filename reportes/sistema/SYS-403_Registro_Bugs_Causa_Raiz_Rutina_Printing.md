# SYS-403: Registro de Incidencias Críticas, Análisis de Causa Raíz y Debugging 🐛

**PyPrinting 3.0 / PySpectrum 3.0 — Suite de Nanofotónica y Control Instrumental**  
**Laboratorio de Nanofotónica — Instituto de Nanosistemas (INS-UNSAM / CONICET)**  
**Autor Principal:** José Luis González Peñafiel (*Becario Doctoral CONICET*)  
**Código del Documento:** `SYS-403` | **Eje Temático:** `[AUD] (Auditoría de Incidencias, Causa Raíz y Pruebas)`  
**Fecha de Emisión:** Septiembre 2026 | **Estado:** Aprobado / Producción

---

## 🔗 Matriz de Referencias Cruzadas

- **Reportes de Sistema Conexos:**
  - `[[SYS-001_Estandares_Diseno_Arquitectura_PyPrinting3]]`
  - `[[SYS-101_Arquitectura_Hilos_Concurrencia_QThread]]`
  - `[[SYS-103_Regimenes_Coordenadas_e_Invariancia_Cinematica]]`
  - `[[SYS-201_Seguridad_Optica_Watchdog_y_Obturadores]]`
  - `[[SYS-205_Resiliencia_Platina_PI_y_Tolerancia_Fallas]]`
  - `[[SYS-401_Auditoria_Comparativa_PyPrinting_v2_vs_v3]]`
- **Fundamentos Científicos Asociados:**
  - `[[CAT-101_Protocolo_Operativo_Impresion_Fototermica_Grillas_2D]]`
  - `[[CAT-104_Compensacion_Inclinacion_Z_Confocal_y_Healing_Pass]]`
- **Decisiones Arquitectónicas:** `DEC-010`, `DEC-011` (`docs/decisions/DECISION_LOG.md`)
- **Módulos de Código Fuente:** `modules/measurements.py`, `core/nanopositioning.py`, `config.py`, `core/nidaq.py`

---

## 1. Resumen de la Auditoría

Se ha completado una revisión código por código sobre **`main.py`** y todas sus dependencias ejecutivas (`app.py`, `measurements.py`, `trace.py`, `focus.py`, `confocal.py`, `config.py`, `nidaq.py`) contrastando el comportamiento esperado según la **Guía Protocolar Actualizada de Impresión ("DO PRINTING")** (`CAT-101_Protocolo_Operativo_Impresion_Fototermica_Grillas_2D.md`).

El análisis identificó **8 hallazgos clave**: 3 de Severidad Alta (BUG 1-3), 2 de Severidad Media (BUG 4-5), 1 de Severidad Alta adicional sobre el watchdog de obturadores (BUG 7) y 1 de Severidad Crítica sobre la platina PI E-517 (BUG 8), incorporados en una auditoría posterior de resiliencia y experimentos no supervisados.

> [!NOTE]
> Numeración con salto observado (BUG 6 no está documentado en este registro): BUG 7 y BUG 8 provienen de una auditoría de estabilidad crítica posterior (`DEC-010`/`DEC-011`) que continuó la numeración asumiendo un BUG 6 ya registrado en otro canal. Se preserva la numeración tal como fue asignada, sin renumerar retroactivamente, para no invalidar referencias cruzadas ya existentes a BUG 1-5.

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

### 🔴 Hallazgos Críticos Adicionales (Auditoría de Estabilidad No Supervisada, `DEC-010`/`DEC-011`)

#### BUG 7 (Severidad Alta): Cierre Intempestivo de Obturadores por Watchdog a los 30 s en Escaneos Confocales Grandes y Anulación Silenciosa del Menú de Auto-Cierre
- **Ubicación**: `core/nidaq.py` (`open_shutter`, `heartbeat_shutter`), `modules/confocal.py`, `modules/focus.py`, `contrapropagante.py`.
- **Descripción Físico-Lógica**: Dos defectos independientes con el mismo síntoma final (corte prematuro de obturadores):
  1. `open_shutter(name, timeout_s=30.0)` hardcodeaba `30.0` como valor de parámetro por defecto. Toda rutina experimental que abriera un obturador sin pasar `timeout_s` explícito —la inmensa mayoría de las llamadas en el código base— ignoraba silenciosamente cualquier política seleccionada por el operador en el dock de Shutters, incluyendo `Sin límite (Modo Alineación)`.
  2. `modules/confocal.py` (rampas de escaneo en X/Y/Z, escaneo paso a paso, corrección de inclinación de 4 esquinas), `modules/focus.py` (reintentos de autofoco por autocorrelación) y `contrapropagante.py` (rampa dual top/bottom) abrían el obturador una sola vez al inicio de un bucle de adquisición y **nunca renovaban el latido** (`heartbeat_shutter()`) durante su ejecución.
- **Falla en Código**: Un escaneo confocal de área grande, una corrección de inclinación de 4 esquinas con Lock Focus por esquina, o una serie de reintentos de autofoco podían superar los 30 s de watchdog sin que ningún latido se renovara — el watchdog forzaba el cierre físico del obturador a mitad de escaneo, mientras la platina seguía barriendo la grilla en completa oscuridad.
- **Impacto**: Datos confocales parcialmente adquiridos en oscuridad, indistinguibles a simple vista de un escaneo válido hasta un análisis posterior detallado; frustración operativa por la anulación silenciosa de "Modo Alineación".
- **Corrección**: Ver `[[SYS-201_Seguridad_Optica_Watchdog_y_Obturadores]]` Secciones 3.3-3.4 (política global centralizada con patrón centinela) y 5.3 (auditoría de cobertura de latido activo, tabla completa por módulo).

---

#### BUG 8 (Severidad Crítica): Desconexión Artificial y Permanente de la Platina PI E-517 a "Modo Virtual" Durante Impresión y Escaneos
- **Ubicación**: `config.py` (`_PIController.MOV`, `qPOS`, `qONT`, `is_physically_connected`).
- **Descripción Físico-Lógica**: `MOV()`, `qPOS()` y `qONT()` envolvían cada llamada real al hardware en `except Exception: self._connected = False`, sin distinguir entre:
  1. Un **rechazo de comando de firmware** (`pipython.GCSError`, típicamente `-1004 "Position out of limits"` cuando una coordenada de grilla con corrección de deriva y desplazamiento de autofoco caía fraccionalmente fuera de $[0, 100]\ \mu\text{m}$).
  2. Una **colisión transitoria de bus USB** durante el polling activo de `qONT()` en bucles de espera de asentamiento.
  3. Una **desconexión física real** (cable USB desenchufado, controladora apagada).
- **Falla en Código**: Los tres casos apagaban `self._connected` de forma indistinguible e **irreversible** (sin ningún mecanismo de auto-recuperación). Una vez activada, la platina física quedaba congelada mientras el software continuaba emitiendo comandos `MOV` "virtuales" que solo actualizaban una posición simulada en memoria — el experimento continuaba corriendo en el vacío, sin que ninguna nanopartícula adicional se imprimiera realmente, hasta que el operador lo notara.
- **Impacto**: Pérdida total de mediciones nocturnas no supervisadas (impresión de grillas grandes, escaneos de deriva de larga duración) a partir del primer nodo que provocara el disparador — sin ningún aviso en la interfaz gráfica más allá del indicador pasivo `🟡 Modo Virtual`.
- **Corrección**: Ver `[[SYS-205_Resiliencia_Platina_PI_y_Tolerancia_Fallas]]` (informe dedicado): clampeo matemático incondicional en el driver, aislamiento de `GCSError` respecto a fallas de comunicación reales, reintentos con degradación segura, eliminación del spam de `*IDN?`, auto-reconexión transparente, validación pre-flight de rango en `modules/measurements.py`, y máquina de estados de pausa/reanudación que preserva el progreso del experimento (`i_global`, partículas ya impresas, logs de deriva) ante una desconexión real.

---

## 3. Matriz Comparativa de Cumplimiento del Protocolo "DO PRINTING"

| Paso del Protocolo (`CAT-101_Protocolo_Operativo_Impresion_Fototermica_Grillas_2D.md`) | Requerimiento Operativo en Software | Estado en Código Actual | Acción Correctiva Propuesta |
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
