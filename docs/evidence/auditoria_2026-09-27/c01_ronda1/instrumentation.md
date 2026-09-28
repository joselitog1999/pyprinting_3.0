# C-01 — Ronda 1 — Panel de instrumentación

Estado: COMPLETO (2026-09-27). Sólo lectura del repo.

## 0. Hechos del código verificados (main)

- `config.RATE_MULTICHANNEL = 1.0e6` → `Backend.rate = 1e4` S/s por canal; `N = 10`.
- `PD_CHANS_LIST = [0, 1, 2, 3, PD_CHAN_BS]` → 5 canales AI → 50 kS/s agregados.
- `channels_photodiodos(rate, N, continuous=True)` → `cfg_samp_clk_timing(rate=1e4, CONTINUOUS, samps_per_chan=max(100,1000)=1000)`.
- `_start()` crea `self._task` continua una vez, `.start()`, `QTimer.start(35)`.
- `_trace_update()` lee `self._task.read(self.N)` (10 muestras/canal) por tick; excepción → `val_l1 = val_l2 = val_bs = 0.0`.
- Heartbeat: `heartbeat_shutter(30.0)` en `_start()` y cada 30 ticks (`self._n % 30 == 0`).
- `_bs_only_update()`: mismo patrón con `self._bs_task`, excepción → `val_bs = 0.0`.

(sigue)

## 1. Semántica NI-DAQmx relevante (con fuente)

Fuentes primarias usadas: (P1) NI-DAQmx Help "How Is Buffer Size Determined?" (texto descargado del espejo
del Help de NI `ge.infn.it/.../mxcncpts.chm/buffersize.html`; la página oficial `ni.com/docs/.../buffersize.html`
no devuelve el cuerpo a un fetch automático). (P2) `nidaqmx-python` 1.5.0 instalado en `.venv`
(`constants.py`, `task/_task.py`, `error_codes.py`): docstrings generados del C API de NI. (P3) Foro NI,
"Stuck in Error -200279", respuesta aceptada de un empleado de NI (Mcdan). (P4) KB NI "Error -200279: Unable to
Keep Up With Acquisition" (el fetch falló por certificado; se cita el resumen del buscador).

### 1.1 Tamaño del buffer de entrada en adquisición continua (P1, verbatim)
"If the acquisition is continuous [...] NI-DAQmx allocates a buffer equal in size to the value of the samples per
channel attribute/property, unless that value is less than the value listed in the following table. If the value
[...] is less than the value in the table, NI-DAQmx uses the value in the table."
Tabla: no rate → 10 kS; 0–100 S/s → 1 kS; **100–10,000 S/s → 10 kS; 10,000–1,000,000 S/s → 100 kS**; >1 MS/s → 1 MS.
"You can override the default buffer size by calling the Input Buffer Config function/VI." Es por canal.

**Observación nueva:** 10 000 S/s exactos figuran en DOS filas (el límite es ambiguo en el propio Help). El
buffer real de la traza es 10 kS (1.0 s → desborde a ≈1.03 s) o 100 kS (10 s → desborde a ≈10.3 s). El triage
supuso 10 kS. No hace falta adivinar: `task.in_stream.input_buf_size` lo informa en la PC del banco sin láser
(ver §3, medición M0). Cualquier arreglo debe fijarlo explícitamente (`task.in_stream.input_buf_size = ...`) para
no depender de la tabla. En ambos casos el mecanismo es el mismo: el atraso crece a 0.97·t_reloj y el desborde
llega (en 1 s o en 10 s); con T_max = 20 s los dos casos terminan en ceros dentro del nodo.

### 1.2 Posición de lectura y `ReadRelativeTo` / `ReadOffset` (P2, docstrings de NI)
- `CURRENT_READ_POSITION` (default): "Start reading samples relative to the last sample returned by the previous
  read." → cada `read(10)` devuelve las 10 muestras siguientes a las ya leídas, no las actuales. Es la causa del
  atraso de C-01.
- `MOST_RECENT_SAMPLE`: "Start reading samples relative to the next sample acquired. For example, use this value
  and set offset to -1 to read the last sample acquired." → con `offset = -N`, `read(N)` devuelve las N últimas
  muestras ya adquiridas, sin esperar. Si todavía no hay N muestras desde `start()` (primer ms a 10 kS/s), el
  driver da −200277 (`NEGATIVE_READ_SAMPLE_NUMBER`) o espera; hay que tolerarlo en el primer tick.
- Las propiedades son de la tarea (`task.in_stream.relative_to`, `task.in_stream.offset`) y persisten entre lecturas.

### 1.3 `OverwriteMode` (P2)
- `DO_NOT_OVERWRITE_UNREAD_SAMPLES` (default): "The acquisition stops when it encounters a sample in the buffer
  that you have not read."
- `OVERWRITE_UNREAD_SAMPLES`: "the acquisition continues and overwrites the unread samples with new ones. You can
  read the new samples by setting relative_to to MOST_RECENT_SAMPLE and setting offset to the appropriate number of
  samples." → Es la combinación que NI documenta para "leer lo último" en un buffer circular: sin sobrescritura,
  saltar muestras con MOST_RECENT no está documentado como libre de −200279 si una pausa de la GUI supera el
  buffer; con sobrescritura, el desborde deja de ser un error por construcción.

### 1.4 `READ_ALL_AVAILABLE` (P2, `constants.READ_ALL_AVAILABLE = -1`)
"If the task acquires samples continuously and you set this input to READ_ALL_AVAILABLE, this method reads all
the samples currently available in the buffer." En nidaqmx-python 1.5 el tamaño del array se calcula antes de
leer (`_calculate_num_samps_per_chan`: `avail_samp_per_chan`, o el atributo 0x31E8 con driver ≥ 24.5). Si hay 0
disponibles devuelve listas vacías (→ `np.mean([])` = NaN con warning; hay que contemplarlo). No evita el
−200279 si la GUI se congela más que el buffer (el KB de NI incluso sugiere NO leer "todo lo disponible" como
remedio de −200279, porque el bloque es de tamaño variable).

### 1.5 Callbacks `register_every_n_samples_acquired_into_buffer_event` (P2)
"Registers a callback function to receive an event when the specified number of samples is written from the
device to the buffer. [...] When you stop a task explicitly any pending events are discarded." Debe registrarse
antes de `start()`. nidaqmx-python registra con opciones 0 → el callback corre en un hilo del driver DAQmx, no
en el hilo de Qt; necesita el GIL, no debe tocar widgets y debe leer exactamente `number_of_samples` dentro del
callback. Si el callback tarda más que el intervalo, los eventos se encolan y reaparece el atraso.

### 1.6 Estado de la tarea tras −200279 (P2 + P3)
`error_codes.py`: −200279 = `SAMPLES_NO_LONGER_AVAILABLE` ("Attempted to read samples that are no longer
available. The requested sample was previously available, but has since been overwritten."). P3 (empleado de NI):
"unread data starting at 'current read position' got over-written with new data"; para seguir hay que mover la
posición de lectura (`DAQmxSetReadRelativeTo` = MostRecentSamp, `DAQmxSetReadOffset`) "to skip over any
over-written samples", o detener y reiniciar la tarea (lo recomendado a alta velocidad). Consecuencia en `main`:
el `read(10)` siguiente vuelve a apuntar a datos pisados → −200279 en cada tick → 0.0 V hasta `_stop_and_save`.
Otros códigos relevantes: −200088 `INVALID_TASK` (usar una tarea ya cerrada: p.ej. un tick pendiente del
`QTimer` después de `_task.close()`), −50103 `PAL_RESOURCE_RESERVED` (dos tareas AI en la misma placa: caso
`_bs_task` corriendo cuando arranca la traza), −200284 `SAMPLES_NOT_YET_AVAILABLE`, −200277 `NEGATIVE_READ_SAMPLE_NUMBER`,
−200361/−200010 desborde de FIFO de placa.

### 1.7 Modelo de tarea finita y costo de re-arme (Help de NI, espejo INFN)
- "Starting a Finite Measurement Task [...] Calling the Read function/VI starts your task, performs the finite
  measurement, and stops the task after the last sample is read. The task returns to its state before you called
  the read operation." (`startfunction.html`)
- "Calling the Read function/VI implicitly commits the task if the task is not already committed."
  (`statetransitions.html`). "NI-DAQmx programs some of the settings for the resources when the task is committed
  [...] the rate of a clock or the input limits of a channel [...] the size of the buffer memory" (`committed.html`).
- Consecuencia: una tarea FINITE creada una vez y **comprometida explícitamente** (`task.control(TaskMode.TASK_COMMIT)`)
  vuelve a *Committed* tras cada `read(N)` y el re-arme por tick es barato; sin commit explícito vuelve a
  *Verified* y cada lectura re-reserva y re-programa. El factor "~70×" entre ambos es de un foro de NI (no
  primario); hay que medirlo (M3).
- Una tarea comprometida **retiene la reserva del motor de AI** (X-series: un único motor de temporización AI):
  mientras exista, focus/confocal no pueden crear la suya (−50103). Vida útil = un nodo, como hoy.

### 1.8 Cadencia real del `QTimer` (código fuente de Qt 6.6.1, `qeventdispatcher_win.cpp:300-373`; versión del .venv)
- `Qt::CoarseTimer` (default) con 20 < intervalo < 20 000 ms → tolerancia = intervalo/20 → **`SetCoalescableTimer`
  (WM_TIMER)**, no el temporizador multimedia. WM_TIMER se resuelve al tick del reloj del sistema (15.625 ms por
  defecto en Windows, salvo que el propio proceso haya subido la resolución) y es un mensaje de baja prioridad.
  Predicción para 35 ms: **≈ 46.9 ms (3 ticks de 15.625 ms)** con resolución por defecto, o ≈ 35–36 ms si el
  proceso tiene resolución de 1 ms. Más los atrasos del event loop del `confocalThread`.
- Intervalo ≤ 20 ms → se convierte en `PreciseTimer` → `timeSetEvent` (multimedia, 1 ms), que postea un
  `QTimerEvent`. Un timer de 10 ms es, por eso, mucho más regular que uno de 35 ms.
- La traza NO corre en el hilo GUI: `traceWorker.moveToThread(confocalThread)` (`app.py:639`), junto con
  focus/confocal/printing/dimers. Pero la decisión de parada **sí pasa por el hilo GUI**:
  `data_printingSignal → app.Backend._dispatch_trace` (`app.py:473, 530-538`; `app.Backend` no se mueve de hilo,
  `app.py:625-644`) llama **directamente** a `printingWorker.grid_trace_detect(payload)`, que hace
  `close_shutter(self.laser)` (`measurements.py:2408-2410`). Latencia de decisión = tick + cola del hilo GUI
  (plots, cámara) + escritura DO + mecánica. (Afinidad de hilo a confirmar por `software-architect`.)
- Reloj de la traza: `time.time()` (no monotónico, ajustable por NTP). En Python ≥ 3.13 es
  `GetSystemTimePreciseAsFileTime` (0.1 µs; verificado en el .venv 3.13.9); en Python < 3.13 en Windows su
  resolución es ≈ 15.6 ms → los `Time_s` de `NP_*.txt` estarían cuantizados. Versión del banco: pregunta.

## 2. Opciones de diseño

### 2.0 Latencia del criterio en ticks (común a todas las opciones)
Con ventanas móviles de M = M2 = 10 ticks (`config.py:127-128`) y un escalón de razón r sobre la línea de base,
modo 0 (`I_new > u·I_old`): tras k ticks, I_new/I_old = 1 + k(r−1)/M → k* = ⌊M(u−1)/(r−1)⌋ + 1.
u = 1.2, r = 2 → k* = 3; r = 1.5 → 5; r = 1.2 → 11 (I_old empieza a absorber el escalón). Modos 1-4 con
N_hold = 5: k* + 4. **Latencia de software ≈ k*·T_tick + fase + cola GUI**; el término dominante es T_tick,
no la lectura DAQmx. Por eso C-01b (10 → 35 ms, en la práctica quizá 47 ms) importa tanto como C-01, y los
parámetros M, M2 y N_hold (en ticks) cambian de significado físico con cualquier cambio de T_tick.

| Opción | Datos por tick | T_tick | Latencia r=2, modo 0 | Riesgos principales |
|---|---|---|---|---|
| A finita por tick (7f5d10a) | ráfaga nueva de 1 ms | 35 ms nom. (≈35–47 real) + costo de crear tarea | ≈105–140 ms | create/close por tick (legado: ciclo total ≈10 ms); ciclo de trabajo 3 % |
| A' finita comprometida 1×/nodo | ídem | igual que A (o 10 ms) | ≈105–140 ms (≈30 ms a 10 ms) | retiene la reserva AI; auto-start + commit a verificar |
| B continua, READ_ALL_AVAILABLE | bloque de ≈T_tick (≈350 muestras) | QTimer | ≈90–105 ms | bloque de tamaño variable; −200279 si el hilo se congela > buffer; timestamp = centro del bloque |
| C continua, MOST_RECENT −N + OVERWRITE | últimas N (1 ms) | QTimer | ≈105 ms (≈30 ms a 10 ms) | −200277 en el primer tick; ciclo 3 %; mock sin `in_stream` |
| D continua, callback cada N_b | bloque fijo N_b | reloj de la placa | ≈3·N_b/f (30 ms con N_b=100) | callback fuera de Qt, excepciones tragadas, GIL, orden stop/unregister/close (−200088) |
| E continua, hilo propio, `read(N_b)` bloqueante | bloque fijo, todas las muestras | reloj de la placa | ≈3·N_b/f | hilo nuevo; parada por flag + timeout; el detector debe ir en ese hilo |

### 2.1 (A) Volver a la tarea finita por tick de producción
- **Pros:** es exactamente lo que imprime hoy en el banco (7f5d10a), sin incógnitas del driver; datos siempre
  actuales (cada tick es una adquisición nueva de 1 ms); una falla no persiste entre ticks; no hay buffer que
  desbordar; misma estadística (10 muestras) con la que se ajustaron los presets del legado.
- **Contras:** cadencia fijada por software (QTimer de 35 ms: C-01b sigue); crear/configurar/cerrar 5 canales en
  cada tick cuesta milisegundos en el `confocalThread` (el legado lo hacía ≈100 veces/s con `start(0)`, así que es
  tolerable, no un error); ciclo de trabajo 1/35: un tránsito de < 35 ms puede no verse.
- **ANOM-TRACE-01** (la razón del cambio a continua) era un problema de *regularidad de la cadencia*, no de
  corrección: las 10 muestras de la ráfaga sí son a 10 kS/s por hardware. Volver a A no reabre un defecto de
  seguridad.
- **A' (variante):** misma semántica, tarea creada y comprometida una vez por nodo; cada tick hace `read(N)` con
  auto-start (vuelve a Committed). Quita el costo por tick sin cambiar lo que se mide. Validar en el banco que
  auto-start + commit explícito entregan datos nuevos en cada lectura (M3).

### 2.2 (B) Continua, leer todo lo disponible y promediar el bloque nuevo
- **Pros:** usa el 100 % de las muestras (sin huecos; σ del promedio ≈ √35 menor con ruido blanco); una tarea por
  nodo; datos al día mientras el hilo no se atrase.
- **Contras:** el bloque dura lo que dura el intervalo real del QTimer (variable con el jitter), así que cada tick
  pesa distinto en I_new/I_old; el promedio de 35 ms suaviza el escalón (aparece a medias en el tick en que
  ocurre); una congelación del `confocalThread` más larga que el buffer vuelve a dar −200279 (hay que recuperarse
  reposicionando con MOST_RECENT o reiniciando); `Time_s` debe ser el centro del bloque, no el instante de lectura;
  con 0 disponibles devuelve vacío (NaN). Sigue pautado por el QTimer.
- Cambia la estadística respecto del legado: los umbrales relativos valen lo mismo en media, pero hay menos
  disparos por ruido y otro filtrado del ripple de 50/100 Hz. Obliga a revalidar presets.

### 2.3 (C) Continua, las N más recientes (`MOST_RECENT_SAMPLE`, offset −N) con sobrescritura
- **Pros:** cambio mínimo sobre `main` (tres propiedades de `in_stream` más buffer explícito); reproduce la
  semántica del legado (1 ms de señal actual por tick) sin crear tareas; con `OVERWRITE_UNREAD_SAMPLES` el
  desborde deja de existir por construcción, aunque la GUI o el hilo se congelen; la lectura no espera.
- **Contras:** descarta el 97 % de las muestras; la cadencia sigue siendo la del QTimer (C-01b); el primer tick
  puede pedir muestras anteriores a la 0 (−200277), así que hay que esperar `total_samp_per_chan_acquired ≥ N`;
  el mock y `_FakeContinuousTask` no tienen `in_stream` y necesitan paridad (§3.8 del prompt).
- Con `DO_NOT_OVERWRITE` y MOST_RECENT, según el empleado de NI (P3), leer "relative to most recent" descarta lo
  que hay entre la posición de lectura y la última muestra, así que en régimen normal tampoco desborda; pero eso
  no está documentado para una pausa mayor que el buffer. Recomiendo OVERWRITE + MOST_RECENT juntos, como dice el
  docstring de NI.

### 2.4 (D) Continua con callback cada N_b muestras
- **Pros:** cadencia fijada por el reloj de la placa (sin cuantización de WM_TIMER); la decisión puede tomarse en
  el mismo callback, sin pasar por el hilo GUI, con latencia más baja y determinista.
- **Contras:** el callback corre en un hilo del driver: no puede tocar QObjects ni widgets (sólo emitir señales en
  cola o encolar en una `queue.Queue`); una excepción dentro del callback no llega a Qt (hay que capturarlo todo y
  convertirlo en falla); N_b = 10 son 1000 callbacks/s peleando el GIL (inviable); N_b = 100 son 100/s
  (razonable); ciclo de vida delicado: registrar antes de `start()`, `stop()` descarta los eventos pendientes,
  pero un callback que ya corre mientras otro hilo hace `close()` da −200088, y hay que desregistrar con la tarea
  detenida. El `_MockNITask` no tiene eventos.

### 2.5 (E) Continua con hilo de adquisición propio y `read(N_b)` bloqueante (propuesta propia)
- Tarea continua con buffer explícito (`input_buf_size` fijo, p. ej. 10 s) y `read(N_b, timeout ≈ 3·N_b/f)` desde la
  posición actual en un hilo dedicado: DAQmx bloquea hasta tener N_b muestras nuevas (libera el GIL durante la
  llamada C), así que el lazo queda **pautado por el reloj de la placa**, con todas las muestras y sin la
  cuantización de Windows. N_b = 100 da un bloque cada 10.0 ms exactos (la cadencia del legado); N_b = 200, cada
  20 ms (un período entero de 50 Hz: rechazo del zumbido de red).
- Frescura verificable: en cada bloque, `in_stream.avail_samp_per_chan` es el atraso; si supera un umbral (p. ej.
  50 ms) se salta al presente (una lectura MOST_RECENT) y se marca un hueco; −200279 es una falla explícita.
- Eje de tiempo exacto: t_k = (k·N_b + N_b/2)/f desde `start()`, no `time.time()` después de leer.
- El detector (I_old/I_new/criterio) corre en ese hilo y cierra el obturador ahí, sin la cola del hilo GUI; a la
  GUI se le emite una versión decimada (≈30 Hz) para graficar (gold exemplar: adquirir, emitir decimado).
- Lectura con `AnalogMultiChannelReader.read_many_sample` sobre un `numpy` preasignado (sin listas Python).
- **Pros:** cadencia determinista, 100 % de las muestras, latencia ≈ 3·N_b/f + escritura DO, errores en nuestro
  hilo (no tragados por un callback), frescura medida y no supuesta.
- **Contras:** arquitectura nueva (ronda 2 con `software-architect`): un hilo más; parada por flag + timeout (nunca
  `close()` desde otro hilo mientras lee: −200088); el detector sale de `measurements.py` o se invoca desde el
  hilo de adquisición; hay que polear `hardware_session.is_emergency_stopped` en el lazo.

### 2.6 Puntos transversales (valen para cualquier opción)
1. **Error de lectura ≠ 0.0 V.** Hoy `trace.py:734-736` registra 0.0 V y el criterio lo trata como dato
   (umbral_down 0.80 → "timeout" a ≈1.1 s). Cambiarlo a NaN **sin nada más** dispara el caso opuesto: toda
   comparación con NaN es falsa y el láser queda abierto hasta T_max (20 s) sin detección. Tiene que ir con una
   ruta de falla: K lecturas fallidas seguidas (p. ej. 3) → cerrar el obturador del nodo, marcar el nodo como
   "falla de adquisición" (no "timeout") y pausar la rutina (DEC-036: adquisición ciega = interlock).
2. **Latido de vida sólo con datos válidos.** Hoy late el temporizador (`trace.py:680-681`, cada 30 ticks) y
   `grid_trace_detect` (`measurements.py:2333`, en cada muestra, aunque sea un 0.0 V de error): el watchdog nunca ve
   una traza muerta. Con la nueva política (latido de vida de la rutina), el latido debe salir de donde se obtuvo
   una lectura válida y actual, en cada tick o bloque, y no salir en ticks fallidos. Además `trace.py` llama
   `heartbeat_shutter(30.0)` con valor explícito (`:612, :681`), que pisa "Sin límite" y contradice la regla del
   timeout centralizado; debe usar la política global o el nuevo latido de rutina.
3. **Adquirir antes de exponer.** `measurements._grid_trace` abre el obturador (`:2319`) y recién después la traza
   crea e inicia la tarea (`trace._start`, `:603-633`). Si `start()` falla (p. ej. −50103), el láser queda abierto
   sin detección. Orden correcto: tarea iniciada y primer bloque válido → abrir → `timer_inicio` desde la apertura
   confirmada.
4. **`_bs_task` y el motor de AI único.** El X-series tiene un solo motor de temporización AI: si `_bs_task` (Power
   BS) está corriendo cuando la impresión arranca la traza por `trace_configuration` (que no la detiene, a
   diferencia de `play_pause`), el `start()` da −50103 y la traza lee ceros. Diseño recomendado: **un único dueño**
   de la adquisición de fotodiodos (una tarea, dos consumidores: traza y ventana BS) y liberación explícita antes
   del autofoco y del confocal, que crean sus propias tareas AI. `_bs_only_update` tiene el mismo defecto de C-01 y
   debe usar la misma lectura corregida.
5. **Doble despacho posible.** La decisión corre en el hilo GUI y detiene la traza con una señal en cola
   (`grid_trace_stopSignal` → `traceWorker.stop` en el `confocalThread`). Si el hilo GUI está atrasado y tiene
   encolados dos o más `data_printingSignal` del mismo nodo, `grid_trace_detect` vuelve a ejecutarse sobre datos
   que siguen cumpliendo la condición: segundo `grid_detectSignal.emit()` para el mismo nodo. No hay guarda al
   inicio de `grid_trace_detect`. A verificar por `software-architect`; con E desaparece (decisión y parada en el
   mismo hilo).
6. **Historia con `np.append` por tick** (`trace.py:742-745`): O(n) por tick. A 10 ms por tick, en una traza manual
   de 1 h son 3.6·10⁵ puntos × 4 arrays copiados en cada tick: atrasa el hilo y rompe cualquier cadencia.
   Irrelevante con T_max = 20 s, relevante si se baja T_tick. Buffer preasignado.
7. **El test que hubiera atrapado C-01 (S-6/S-12):** un doble de tarea con reloj (muestras = f·t), buffer finito,
   posición de lectura, `relative_to`/`offset`/`over_write` y −200279 cuando la escritura alcanza a la lectura, más
   un test que avance el reloj 35 ms por tick y exija que la muestra leída tenga una edad < 2·T_tick.

## 3. Qué medir en el banco

Nota de nombres: "B-07" de la auditoría (L4 `lotes/L4_protocolos_laboratorio.md:305`, desborde de buffer) **no es**
"BANCO-07" de `PRUEBAS_BANCO_PENDIENTES.md` (Step & Glue). Conviene registrar estas mediciones como entradas
BANCO-2x nuevas para que no se confundan.

| ID | Condición | Qué se mide | Predicción / criterio de aceptación |
|---|---|---|---|
| M0 | Sin láser, PyPrinting cerrado; script de sólo lectura AI | versión de Python, driver NI-DAQmx y nidaqmx-python; `in_stream.input_buf_size` y `timing.samp_clk_rate` de una tarea continua a 10 kS/s con `samps_per_chan=1000` | Resuelve la ambigüedad de la tabla: 10 000 (desborde ≈1.03 s) o 100 000 (≈10.3 s) |
| M1 = B-07 | Sin láser; `main` actual; generador de funciones en ai0 (onda cuadrada de 1 Hz, 0–1 V) | período aparente en la traza; instante del primer −200279; ceros posteriores | Período aparente ≈35 s (35× más lento) hasta el desborde, luego 0.0 V. Si no se ve, la hipótesis C-01 cae |
| M2 = B-02 | Opción elegida; 60 s; cámara en vivo encendida y apagada | Δt entre ticks/bloques (`perf_counter`); mediana, p95, p99, máx | QTimer de 35 ms: modal ≈46.9 ms o ≈35 ms. E: 10.0 ms ± jitter de proceso. Aceptación: p99 < 1.5·T, ningún hueco > 3·T |
| M3 | Sin láser | costo por llamada (1000 repeticiones): create+cfg+read+close (A), read con commit explícito (A'), read MOST_RECENT (C), read bloqueante (E) | Da el número real detrás de ANOM-TRACE-01 y del "70×" del foro |
| M4 = B-01 | Sin láser: escalón eléctrico del generador en ai0 (r = 2 y r = 1.2) | osciloscopio: canal 1 = escalón (disparo); canal 2 = línea DO del obturador (o un marcador TTL en una línea libre escrito en el instante de la decisión); canal 3 = fotodiodo rápido detrás del obturador con un LED (láser apagado) para la parte mecánica; ≥ 100 eventos | Software: k*·T_tick + fase (≈105–140 ms en A, ≈30 ms en E con N_b = 100). Mecánica por separado con cierre manual (control) |
| M5 | Sin láser | robustez: congelar la GUI (arrastrar ventana, cámara a 25 fps); forzar −50103 abriendo un panel de prueba AI de NI MAX sobre Dev1 | Sin −200279 y atraso ≤ umbral; con −50103: obturador cerrado, nodo en "falla de adquisición", ningún 0.0 V registrado |
| M6 | Con láser a baja potencia, sólo después de M0–M5 y con aprobación humana | 10+ nodos sobre muestra de prueba: tasa de "success", t_raw y trazas guardadas, comparado con 7f5d10a | Sin ceros en `NP_*.txt`; tasa de éxito ≥ la de 7f5d10a |

Opcional para M4/M6: cablear la línea DO del obturador (o el marcador) a un canal AI libre, para tener el
instante de apertura/cierre en la misma base de tiempo de hardware que el fotodiodo (t = 0 de exposición exacto).
Depende de qué canal AI esté libre (ver Q7 del triage sobre ai3).

## 4. Preguntas para el investigador (una línea cada una)

1. ¿Aceptás, como paso 0 antes de volver a imprimir, revertir sólo la lectura de la traza y de Power BS a la tarea
   finita por tick de 7f5d10a (revertir un cambio deliberado está exento por §5.0), y dejar el rediseño para la ronda 2?
2. ¿Cuál es la latencia máxima tolerable entre la captura y el obturador cerrado, en ms?
3. ¿Qué modelo tiene cada obturador y cuánto tarda en cerrar (el de 532 nm es un servo)?
4. En una captura típica, ¿la señal sube o baja, y en qué razón (×1.2, ×2, …)?
5. ¿Los presets se ajustaron con el legado (≈10 ms por punto)? ¿Preferís volver a ticks de 10 ms o reexpresar M, M2 y N_hold en ms?
6. ¿Te interesa ver en la traza guardada eventos más cortos que un tick (tránsitos de NP), o sólo importa la decisión de parada?
7. ¿Se usa la ventana Power BS durante una impresión?
8. ¿Qué modelo y ganancia tienen los fotodiodos (ancho de banda del amplificador)?
9. ¿Hay en el banco generador de funciones, osciloscopio y una línea DO/PFI libre para un marcador TTL?
10. ¿Qué versiones de Python, driver NI-DAQmx y nidaqmx-python tiene la PC del banco?
11. ¿Se ve zumbido de 50/100 Hz en los fotodiodos? (define si el bloque de E es de 10 o de 20 ms)

## 5. Recomendación y veredicto

**Veredicto sobre `main` actual: `SAFETY_VIOLATION`.** El criterio de parada decide con el láser abierto sobre
datos atrasados (atraso ≈ 0.97·t_reloj) y después sobre ceros inventados por un error persistente (−200279):
nodos cerrados a ≈1.1 s como "timeout" con umbral_down 0.80, o **láser abierto 20 s sin detección** con
umbral_down = 0 (el default). `_bs_task` tiene el mismo defecto y además puede bloquear la traza (−50103).

**Paso 0 (inmediato, antes de imprimir):** revertir la lectura de `trace.py` (traza y Power BS) a la tarea finita
por tick de 7f5d10a (opción A), conservando DEC-036. Es la única variante probada en el banco. Veredicto esperado:
`TIMING_HAZARD` conocido y aceptado hoy (≈105–140 ms de latencia de software, C-01b), no un defecto nuevo.
Confirmar con M0 + M1 sin láser que `main` falla como se predice y que la reversión no.

**Definitivo (rondas 2-4): opción E**, adquisición continua pautada por el reloj de la placa en un hilo propio,
bloques fijos de 10 ms (o 20 ms si hay 50 Hz), buffer explícito, frescura medida en cada bloque, detector y cierre
en ese hilo, GUI decimada. Junto con los puntos transversales: error → falla con cierre (nunca 0.0 V ni NaN
silencioso), latido de vida sólo con lectura válida, adquirir antes de exponer, un único dueño del motor AI,
guarda contra doble despacho y un doble de tarea que modele el buffer. Si el equipo prefiere un cambio menor,
**C con un QTimer de 10 ms** (MOST_RECENT + OVERWRITE) es el segundo mejor: arregla C-01 sin crear tareas, pero
sigue pautado por Windows y descarta el 97 % de las muestras. **B y D los descarto:** B mantiene el QTimer y el
riesgo de desborde con bloques variables; D logra la cadencia de E con un ciclo de vida más frágil.
