# C-01 — Ronda 2 — Panel de instrumentación (opción E)

Estado: COMPLETO (2026-09-27). Sólo lectura del repo salvo este archivo. Árbol: `main` @ `7ae2d07` con el paso 0
(`DEC-037`) aplicado en la copia de trabajo.

Marcas: **[CÓDIGO]** leído en la línea citada · **[NI-DOC]** docstring de `nidaqmx` 1.5.0 instalado en `.venv`
(generado del C API de NI; `task/_in_stream.py`, `task/_task.py`, `constants.py`, `error_codes.py`,
`stream_readers/_analog_multi_channel_reader.py`, `system/watchdog.py`) · **[NI-HELP]** Help de NI-DAQmx (fuente P1 de
la Ronda 1) · **[PY-DOC]** documentación de Python · **[MEDIDO]** ejecutado en esta PC · **[INFERIDO]** razonamiento no
probado · **[BANCO]** se decide en el banco.

## 0. Hechos del código que condicionan el diseño (estado posterior al paso 0)

1. **Un solo punto de entrada a las entradas analógicas [CÓDIGO].** Toda tarea AI del proceso sale de
   `core/nidaq.py::channels_photodiodos()` (`:729-776`): traza y Power BS (`modules/trace.py:528, 658`), confocal
   (`modules/confocal.py:817, 938, 947`), foco (`modules/focus.py:430`), contrapropagante (`contrapropagante.py:722`) y
   PySpectrum (`pyspectrum/modules/optical_support.py:81`). Es el lugar natural para el árbitro del motor de AI (§4).
2. **Paso 0 sin `finally` [CÓDIGO].** `_trace_update` (`trace.py:656-694`) y `_bs_only_update` (`:526-537`) crean la
   tarea, leen y la cierran dentro del `try`; si `read()` lanza, `task.close()` no corre. `Task.__del__` sólo emite un
   aviso ("Resources on the task device may still be reserved") y no libera nada [NI-DOC `_task.py:126-133`]. Si la
   excepción llega con la tarea ya arrancada (p. ej. un timeout), la reserva del motor de AI puede quedar tomada por el
   resto de la sesión y cada tick siguiente leería 0.0 V (−50103). Probabilidad baja (el `read(10)` a 10 kS/s con
   timeout de 10 s casi no puede vencer), severidad alta. Arreglo de una línea (`try/finally`), exento por §5.0 si
   parte de un test que falla. **Hallazgo nuevo; no está en `DEC-037`.**
3. **Quién abre y quién cierra hoy [CÓDIGO].** `_grid_trace` abre el obturador en `confocalThread`
   (`measurements.py:2319`), `trace._start()` lo vuelve a abrir y llama `heartbeat_shutter(30.0)` explícito
   (`trace.py:583, 586, 641`, C-29), la decisión y `close_shutter` corren en el hilo de la GUI
   (`app.py:530-538` → `measurements.py:2408-2410`).
4. **El watchdog [CÓDIGO].** Un único plazo global `_watchdog_deadline` (`nidaq.py:117`), renovable desde cualquier hilo
   por `heartbeat_shutter()` (`:204-216`), revisado cada 100 ms con `time.time()` (`:165-198`, **reloj no monotónico**).
   Al vencer cierra los cuatro obturadores con una escritura.
5. **El candado del hardware [CÓDIGO].** `_nidaq_lock` (`RLock`, `:115`) se toma en toda escritura DO/AO. Adentro hay
   esperas: `_pulse_flipper` duerme 5 ms (`:662`), `flipper_notch532` 3 ms (`:718`), y un cierre que falla reintenta
   con dos esperas de 50 ms (`:498-503`). Un `close_shutter` desde otro hilo puede esperar ese tiempo.
6. **La llamada DAQmx libera el GIL [CÓDIGO + PY-DOC].** `nidaqmx` llama `DAQmxReadAnalogF64` por
   `lib_importer.windll` (`_library_interpreter.py:4256`), cargada con `ctypes.windll.LoadLibrary` (`_lib.py:192`). La
   documentación de `ctypes` dice que el GIL se libera antes de llamar a una función de una biblioteca `CDLL`/`WinDLL`
   y se vuelve a tomar después. Un `read(N_b)` bloqueante en un hilo propio no frena a los demás hilos de Python.
7. **Canales [CÓDIGO].** `config.PD_CHANS_LIST = [0, 1, 2, 3, 6]` (5 canales), `RATE_MULTICHANNEL = 1.0e6`,
   `Backend.rate = RATE_MULTICHANNEL / 100 = 1e4` S/s por canal (`trace.py:501`) → 50 kS/s agregados. `ai3` figura
   también como trigger Z (`TRIGGER_CHANNELS`, C-44, `BANCO-20`).

---

## 1. Configuración DAQmx exacta de la tarea de la traza

### 1.1 Parámetros

| Propiedad | Valor | Por qué | Fuente |
|---|---|---|---|
| Canales | `Dev1/ai0, ai1, ai2, ai3, ai6` en ese orden (`PD_CHANS_LIST`), nombres `chan_PD{n}` | Paridad con producción: el mismo índice de fila que usan traza, Power BS y criterio | [CÓDIGO] `nidaq.py:751-754` |
| `terminal_config`, `min_val`/`max_val` | **Los mismos de hoy** (defaults del driver, que hoy no se fijan). Se leen y registran (`ai_term_cfg`, `ai_min`, `ai_max`) en `BANCO-26` | Cambiar el rango o la referencia cambia la escala de los umbrales en V (`umbral_abs_v`): es una decisión de metrología, no de C-01 | [CÓDIGO] |
| Temporización | `cfg_samp_clk_timing(rate=10_000.0, sample_mode=CONTINUOUS, samps_per_chan=BUF)` | Reloj de la placa, tasa de producción | [NI-DOC] |
| Tasa efectiva | **Se lee** `task.timing.samp_clk_rate` después de `commit` y es la que usa el eje de tiempo | El driver puede ajustar la tasa pedida; el eje no debe suponer 10 000 | [INFERIDO]; lectura en `BANCO-26` |
| `in_stream.input_buf_size` | `BUF = 100_000` muestras/canal (10 s a 10 kS/s; ≈ 1 MB en crudo de 16 bits) | "Setting this property overrides the automatic input buffer allocation" [NI-DOC]; quita la ambigüedad de la tabla en 10 kS/s (Ronda 1 §1.1). El buffer no fija la latencia: sólo cuánto puede atrasarse el hilo antes de −200279. El atraso se corta mucho antes (§1.3) | [NI-DOC] `_in_stream.py:273-285` |
| `in_stream.overwrite` | `OverwriteMode.DO_NOT_OVERWRITE_UNREAD_SAMPLES`, **explícito** | E lee todas las muestras en orden: no hay nada que pisar. Si el lector se atrasa más que el buffer, el driver da −200279, un error ruidoso (el abogado del diablo, Ronda 1 §2-C). `over_write` está deprecado desde 0.7.0; usar `overwrite` | [NI-DOC] `constants.py:460-462`, `_in_stream.py:729-744, 1256` |
| `in_stream.relative_to` / `offset` | `ReadRelativeTo.CURRENT_READ_POSITION` / `0`, **explícitos** | "Start reading samples relative to the last sample returned by the previous read": cada bloque sigue al anterior, sin huecos ni solapes. No es la opción C (`MOST_RECENT_SAMPLE`) | [NI-DOC] `constants.py:558` |
| `N_b` (muestras por canal por lectura) | **100** (T_b = 10.0 ms). Permitidos 50 / 100 / 200 | 10 ms es la cadencia del legado. El rechazo de 50 Hz **no depende del bloque**: lo dan las ventanas del criterio si son múltiplos de 20 ms (cambio respecto de la Ronda 1, que lo ataba a N_b = 200). N_b = 50 sólo si `BANCO-29` muestra que la espera de bloque domina | [INFERIDO] |
| Lectura | `AnalogMultiChannelReader(task.in_stream).read_many_sample(buf, N_b, timeout=T_read)` sobre un `numpy` `float64` de forma `(5, N_b)` preasignado; `verify_array_shape=False` después de la primera lectura | Sin listas Python por bloque; mismo arreglo en cada llamada ("valuable in continuous acquisition scenarios") | [NI-DOC] `_analog_multi_channel_reader.py` |
| `T_read` (timeout de la lectura) | **0.2 s** (20 bloques de 10 ms) | Un hilo sano recibe un bloque cada 10 ms; vencer 0.2 s significa que la placa no produce muestras (reloj detenido, placa reseteada). 0.2 s es el techo de latencia propuesto: la ruta de falla lo respeta. Muy por encima de una pausa normal de Windows (a medir en `BANCO-28`) | [NI-DOC] timeout: "If the time elapses, the method returns an error" |
| `in_stream.wait_mode` | **Default** al principio; se registra en `BANCO-26` y se compara `YIELD` contra `WAIT_FOR_INTERRUPT` en `BANCO-28` (p99 de despertar y CPU) | El docstring no dice cuál es el default. `WAIT_FOR_INTERRUPT` es "the most CPU efficient" y su límite de tasa no pesa a 100 lecturas/s; `POLL` gasta un núcleo | [NI-DOC] `constants.py:965-969` |
| `ai_data_xfer_mech` | Se lee; se espera `DMA` (PCIe) | Con `USB_BULK` o `INTERRUPT` cambia el término de transferencia | [NI-DOC] `constants.py:212-216` |
| `ai_data_xfer_req_cond` | `ON_BOARD_MEMORY_NOT_EMPTY`, **explícito si la placa lo acepta**; si no, se registra el valor por defecto | Con `ON_BOARD_MEMORY_MORE_THAN_HALF_FULL` la muestra espera en la FIFO de la placa hasta que se llene a medias: con 50 kS/s agregados, eso suma `input_onbrd_buf_size / 2 / 50 000` s de latencia (el tamaño de la FIFO se lee en `BANCO-26`) | [NI-DOC] `constants.py:373-377`, `_ai_channel.py:1183-1191`, `_in_stream.py:328-333` |
| Ciclo de vida | `Task()` → canales → temporización → propiedades → `control(TaskMode.TASK_COMMIT)` → lectura de verificación de propiedades → `start()` → lazo → `finally: stop(); close()` **en el mismo hilo** | `close()` "aborts the task, if necessary, and releases any resources the task reserved" [NI-DOC `_task.py:325-335`]. El commit explícito hace que un −50103 aparezca antes de `start()`, fuera del lazo | [NI-DOC] |
| Vida útil | **Un nodo** en modo impresión, o la sesión de Play/Power BS en modo monitor (§4). Nunca se deja una tarea continua corriendo entre rutinas | Mientras la tarea existe comprometida, tiene reservado el motor de AI (Ronda 1 §1.7) | [NI-HELP] |

### 1.2 Lo que se mide en cada bloque (frescura, eje de tiempo)

- **Atraso:** `lag = in_stream.avail_samp_per_chan / f` después de cada lectura ("the number of samples available to
  read per channel") [NI-DOC `_in_stream.py:139-146`]. Es exactamente lo adquirido y todavía no leído.
- **Eje de tiempo exacto:** la muestra i del nodo está en `t_i = i / f_efectiva` desde `start()`. La apertura del
  obturador se marca como índice de muestra: `i_open = total_samp_per_chan_acquired` leído justo después de que
  `open_shutter()` devuelve `True` [NI-DOC `_in_stream.py:953-963`], con incertidumbre de ±1 bloque. Si hay un AI libre,
  cablear la línea del obturador a ese AI da la apertura y el cierre en la misma base de tiempo, sin incertidumbre
  (pregunta §6).
- **Diagnóstico de reloj de pared:** en cada bloque se guarda `time.perf_counter()` de llegada (monotónico). No entra en
  el criterio; sirve para medir el jitter de despertar y verificar que el reloj de la placa y el de la PC no divergen.
- **Sobrecarga:** `overloaded_chans_exist` cada 10 bloques (leerla limpia el estado) [NI-DOC `_in_stream.py:689-698`].
  Una sobrecarga en el canal del láser invalida el bloque (§1.3).

### 1.3 Qué es un bloque válido y qué pasa si no lo es

Un bloque es **válido** si la lectura no lanzó, sus valores son finitos, no hay sobrecarga en el canal del láser y
`lag ≤ LAG_FAULT_S`. Sólo un bloque válido alimenta el detector y emite el latido de vida (§3).

| Umbral | Valor propuesto | Qué hace |
|---|---|---|
| `LAG_WARN_S` | 0.05 s (5 bloques) | Se registra y se cuenta. El hilo **se pone al día** leyendo los bloques acumulados en orden: procesar un bloque cuesta décimas de ms, así que 5 bloques atrasados se recuperan en ≈ 1 ms y el detector ve el escalón sin perder muestras. No se saltea al presente (saltear perdería el flanco y contaminaría I_old) |
| `LAG_FAULT_S` | 0.5 s | Falla de adquisición: el láser estuvo 0.5 s sin evaluación, por encima del techo de 200 ms. Cierra el obturador, nodo "falla de adquisición", rutina en pausa. Menor que el plazo de vida del watchdog (1.0 s, §3), para que el propio hilo corte primero cuando se despierta |

### 1.4 Códigos de error y respuesta

Nombres de `nidaqmx/error_codes.py` (1.5.0). "Falla" = cerrar el obturador del nodo (si está en modo impresión),
`stop()` + `close()` en el mismo hilo, nodo "falla de adquisición" (reintentable en el healing pass), rutina en pausa,
mensaje al operador. **Nunca** 0.0 V ni NaN silencioso.

| Código | Nombre | Cuándo aparece en E | Respuesta |
|---|---|---|---|
| −200279 | `SAMPLES_NO_LONGER_AVAILABLE` | El hilo se atrasó más que el buffer (> 10 s). No debería ocurrir: `LAG_FAULT_S` corta a 0.5 s. El KB de NI lo titula "Unable to Keep Up With Acquisition" (Ronda 1, P4) | Falla. En modo monitor: reiniciar la tarea (`stop`/`start`) y marcar un hueco en el registro. No se reintenta la lectura sobre la misma posición (Ronda 1 §1.6: vuelve a apuntar a datos perdidos) |
| −200284 | `SAMPLES_NOT_YET_AVAILABLE` | Venció `T_read` = 0.2 s: la placa no produce muestras | Falla. Si además `total_samp_per_chan_acquired` no avanzó, se trata como placa caída y se activa el interlock `"NI-DAQmx"` |
| −50103 / −200022 | `PAL_RESOURCE_RESERVED` / `RESOURCE_ALREADY_RESERVED` | En `commit`/`start`: otra tarea tiene el motor de AI (otro proceso, un panel de NI MAX, una tarea filtrada) | La tarea no arranca, **el obturador nunca se abre** (primero adquirir, §3.1), nodo "falla de adquisición: placa ocupada", rutina en pausa. Sin reintento automático: una fuga en el proceso no se libera sola. Dentro del proceso no puede pasar si todos pasan por el árbitro (§4) |
| −200088 | `INVALID_TASK` | Usar una tarea ya cerrada. Se evita por construcción: sólo el hilo de adquisición toca la tarea; los demás piden la parada con un `threading.Event` y el hilo cierra en su `finally` | Si aparece es un defecto: falla + traza completa en el log |
| −200361 / −200010 | `INPUT_FIFO_OVERFLOW_2` / `INPUT_FIFO_OVERFLOW` | La FIFO de la placa se llenó antes de la transferencia. Improbable con DMA a 50 kS/s | Falla |
| −200019 | `ADC_OVERRUN` | Conversión demasiado rápida para la configuración | Falla en el primer bloque, antes de abrir |
| −201003, −50405 | `DEV_CANNOT_BE_ACCESSED`, `PAL_TRANSFER_ABORTED` | Placa reseteada o quitada (el caso de `BANCO-18`) | Falla + interlock `"NI-DAQmx"` (como `_daq_fault`, `nidaq.py:338-341`) |
| Cualquier otra excepción, incluidas las de Python | — | Defecto en el hilo | Capturada en el nivel superior del hilo: falla. `threading.excepthook` de `DEC-036` queda como última barrera |

**Paridad con el mock (§3.8 del prompt de instrumentación):** `_MockNITask` y `_UnavailableNITask` no tienen
`in_stream`, `control` ni lectores. La tarea de E no debe salir de la rama que devuelve `_UnavailableNITask` (NaN): si la
placa no está, la función que crea el flujo **lanza** (y activa el interlock como hoy), no devuelve un sustituto. En
`SAFE_MODE` hace falta un doble que modele reloj, buffer finito, posición de lectura, `avail_samp_per_chan`,
`total_samp_per_chan_acquired` y los errores −200279/−200284/−50103 (el de `tests/test_trace_acquisition_freshness.py`
es la base).

---

## 2. Presupuesto de latencia: del escalón físico al haz bloqueado

### 2.1 Etapas

L = L_pd + L_xfer + L_bloque + L_crit + L_sched + L_proc + L_lock + L_do + L_mec

| Etapa | Qué es | Valor esperado | ¿Depende del software? | Cómo se sabe |
|---|---|---|---|---|
| L_pd | Subida del fotodiodo y su amplificador | Modelo y ganancia desconocidos. Un amplificador de ancho de banda ≥ 1 kHz aporta ≲ 0.4 ms (10–90 %) | No | `BANCO-22` (modelo) |
| L_xfer | Del ADC al buffer de la PC | 0.1 ms (un período de muestreo) + DMA, µs con `ON_BOARD_MEMORY_NOT_EMPTY`. Con "más de media FIFO": `input_onbrd_buf_size`/2/50 kS/s | Sí (una propiedad, §1.1) | `BANCO-26` |
| L_bloque | La muestra que decide espera a que se complete su bloque | U(0, T_b): 0–10 ms con N_b = 100 | Sí (N_b) | Por construcción |
| L_crit | Cuánta señal posterior al escalón necesita el criterio (ventanas y hold) | **Domina.** Ver §2.2 | Sí (parámetros del criterio) | Simulación §2.2, `BANCO-29` |
| L_sched | Despertar del hilo y esperar el GIL | p50 < 1 ms; p95 ≲ 5 ms; pausas raras de decenas de ms con la cámara en vivo [INFERIDO] | Sí (topología) | `BANCO-28` |
| L_proc | Media de 5 × 100 muestras + criterio en `numpy` | < 0.2 ms [INFERIDO] | Sí | `BANCO-28` |
| L_lock | Espera de `_nidaq_lock` si otro hilo escribe DO/AO | 0 típico; 5–10 ms si coincide con un pulso de flipper; ≤ 100 ms si otro cierre está reintentando (§0.5) | Sí (compartido) | `BANCO-29` (p99) |
| L_do | `write()` de las cuatro líneas, tarea DO estática ya creada | < 1 ms [INFERIDO; registro en PCIe] | No | `BANCO-29` |
| L_mec | De la línea DO al haz bloqueado: electrónica del servo (una trama PWM de un servo de modelismo dura ~20 ms [INFERIDO]) + recorrido del brazo hasta tapar el haz | **Desconocido.** Obturadores de fabricación propia, sin medir (R3) | **No** | **`BANCO-30`** |

### 2.2 El término que manda: el criterio

Simulación sin ruido, 400 escalones con fase aleatoria, criterio del modo 1 (el preset "umbral + valor absoluto", sólo
la parte relativa `I_new > u·I_old`) con `hold_counter ≥ N_hold` (`measurements.py:2362-2399`), reimplementado sin
código del repo. Valores de práctica del investigador: u = 1.5,
N_hold = 3 (R3). Escalón de ×1.4 a ×2 (R3). Los scripts (`latency_sim.py`, `latency_sim2.py`) quedaron en el scratchpad
de la sesión, no en el repositorio. Cifras = de escalón a decisión (L_bloque + L_crit):

| Caso | r = 2 | r = 1.6 | r = 1.4 |
|---|---|---|---|
| **Producción hoy** (`7f5d10a`): tick 47 ms, ráfaga de 1 ms, M = M2 = 10 ticks | **≈ 354 ms** (p95 374) | **≈ 494 ms** (p95 515) | **nunca** (r < u) |
| E, T_b = 10 ms, W_new = 20 ms, W_old = 100 ms, **sin guarda**, N_hold 3 | 35 ms (p95 39) | **nunca** | nunca |
| **E, T_b = 10 ms, W_new = 20 ms, W_old = 100 ms, guarda 40 ms, N_hold 3** | **35 ms (p95 39)** | **41 ms (p95 46)** | nunca |
| Ídem, N_hold 1 | 15 ms (p95 20) | 22 ms (p95 26) | nunca |
| E, T_b = 10 ms, W_new = 40 ms, W_old = 100 ms, guarda 40 ms, N_hold 3 | 45 ms (p95 49) | 58 ms (p95 63) | nunca |
| E, T_b = 20 ms, W_new = 20 ms, W_old = 100 ms, guarda 40 ms, N_hold 2 | 39 ms (p95 49) | 46 ms (p95 55) | nunca |
| Con u = 1.3 (r = 1.4), E 10 ms, W_new 20, W_old 100, guarda 40, N_hold 3 | — | — | 40 ms (p95 44) |

Tres conclusiones, las tres fuera de la capa DAQmx pero determinadas por ella:

1. **La latencia la fijan las ventanas, no la adquisición.** E con las ventanas de hoy pasadas a ms (470/470 ms) sigue
   en ≈ 260 ms para r = 2 (primera simulación). E sirve porque permite ventanas cortas **sin perder señal**: una
   ventana de 20 ms tiene 200 muestras por canal, el doble que las 100 que suman hoy 10 ticks de 470 ms.
2. **Con ventanas cortas hace falta una guarda entre I_old e I_new** (o congelar I_old al primer bloque que cumple la
   condición). Sin ella, el escalón entra en la base antes de que se cumpla el hold y un ×1.6 **no se detecta nunca**.
   La guarda debe ser ≥ T_hold + T_b. Es un requisito para quien diseñe las ventanas en ms (metrología / experimental).
3. **Con u = 1.5 un escalón de ×1.4 nunca dispara el criterio relativo**, ni hoy ni con E: queda sólo el umbral
   absoluto (`umbral_abs_v`). Es coherente con "algunos TIMEOUT" (R3), pero hay que confirmarlo (pregunta §6).

El valor de producción supone `steps_before = steps_after = 10` (default de `config.py:127-128`) y el tick de 47 ms medido
en la PC de desarrollo; no incluye la cola del hilo GUI. Se confirma con `BANCO-24`. Con el QTimer de 35 ms exactos
(`PreciseTimer`) sería ≈ 262 ms: cambiar el tipo de temporizador no alcanza.

### 2.3 Contra el objetivo propuesto (mediana ≤ 50 ms, p95 ≤ 100 ms, techo 200 ms; no confirmado)

Caso de referencia: E con T_b = 10 ms, W_new = 20 ms, W_old = 100 ms, guarda 40 ms, N_hold 3, r = 1.6.

| Término | Mediana | p95 | Peor caso razonable |
|---|---|---|---|
| L_pd + L_xfer | < 1 | < 1 | 1 (si la transferencia es por FIFO a medias, sumar su término) |
| L_bloque + L_crit (simulado) | 41 | 46 | 47 |
| L_sched + L_proc | 1 | 5 | 50 (pausa de GIL con la cámara; a medir) |
| L_lock + L_do | < 1 | 1 | 100 (cierre ajeno reintentando) |
| **Parte de software** | **≈ 43** | **≈ 52** | **≈ 200** |
| L_mec | ? | ? | ? |

- **Con L_mec ≈ 0 el objetivo se cumple** (43 / 52 ms), y el peor caso toca el techo sólo si coinciden una pausa larga y
  un cierre ajeno en reintento.
- **L_mec entra entero.** Si el servo tarda 30 ms en tapar el haz, la mediana queda en ≈ 73 ms: el objetivo de 50 ms
  exige N_hold 1 (22 + 30 ≈ 52 ms) o un obturador más rápido. Si tarda ≥ 60 ms, ninguna configuración de software cumple
  50 ms. Por eso `BANCO-30` va antes que cualquier ajuste fino.
- **Comparación honesta con hoy:** la producción está en ≈ 0.35–0.5 s de software más la mecánica, 3 a 5 veces por
  encima del 10–100 ms del legado (Martínez p. 112). E con ventanas en ms la baja ≈ 10 veces.
- La parte de software que depende de este diseño de adquisición es L_bloque, L_sched, L_proc, L_lock y L_do
  (≈ 7 ms de mediana, ≈ 5 de ellos por la espera de bloque); L_crit depende de los parámetros del criterio, que se fijan
  en ms en otra parte de esta ronda.

---

## 3. Latido de vida de la traza de impresión (R2-8)

Es un cambio de política del watchdog: nunca exento (§5.0). Se diseña acotado a la exposición de un nodo; la fase 6.2
del plan lo generaliza a las demás rutinas con la misma primitiva.

### 3.1 Secuencia de un nodo (quién abre, quién late, quién cierra)

Todo lo que toca el obturador durante la exposición ocurre **en el hilo de adquisición**, en este orden:

1. La rutina (`confocalThread`) deja la platina en el nodo (`wait_on_target()` = `True`) y la potencia en alta. Hoy
   `_grid_trace` ignora el `bool` de `down_flipper()` (`measurements.py:2318`): con E, un `False` aborta el nodo sin abrir.
2. La rutina pide `iniciar_nodo(láser, parámetros en ms, T_max_efectivo)` al servicio de adquisición.
3. El hilo arranca la tarea (o reutiliza la que ya corre en modo monitor, §4) y lee **un primer bloque válido**. Si no
   lo consigue en `T_read`, el nodo termina en "falla de adquisición" **sin abrir** (primero adquirir, después exponer).
4. El hilo toma la **concesión de exposición** (§3.2) y llama `open_shutter(láser)`. Si devuelve `False` (interlock,
   escritura no confirmada): libera la concesión, nodo "apertura rechazada".
5. Marca `i_open` (§1.2) y descarta del criterio los primeros `T_blank` ms (transitorio de apertura del servo; el valor
   sale de `BANCO-30`: p99 del tiempo de apertura + 10 ms). Así el flanco de apertura no entra en I_old (S4 del abogado
   del diablo, Ronda 1).
6. Lazo: leer bloque → validar (§1.3) → **latir** → detector → ¿parar? El T_max se mide **por conteo de muestras**,
   `(i − i_open) / f`, con el reloj de la placa.
7. Al parar: `close_shutter(láser)`. Si confirma, libera la concesión; si no, la concesión queda tomada y el camino de
   `DEC-036` (reintentos, banner) sigue a cargo. Emite el resultado del nodo a la rutina. Detiene la tarea salvo que haya
   un consumidor en modo monitor.

La rutina no abre ni cierra el obturador de la traza; el hilo GUI tampoco. Desaparecen el doble despacho (Ronda 1
§2.6-5) y la cola del hilo GUI en la latencia. `grid_trace_detect` deja de llamar `heartbeat_shutter()` por muestra y
`trace._start` deja de llamar `heartbeat_shutter(30.0)` (C-29) en esta ruta.

### 3.2 La concesión de exposición (propuesta de API, `core/nidaq.py`)

```text
lease = acquire_exposure_lease(owner="Traza de impresión", shutters=("532",),
                               beat_timeout_s=1.0, max_exposure_s=T_max_efectivo + 2.0)
lease.beat()      # sólo desde el hilo de adquisición, tras cada bloque válido
lease.release()   # sólo con el cierre confirmado
lease.expired     # el hilo lo consulta en cada bloque
```

| Pregunta | Respuesta |
|---|---|
| **Quién late** | Sólo el hilo de adquisición, después de validar un bloque. Ni el QTimer, ni la GUI, ni el criterio sobre datos inválidos. Un bloque inválido no late |
| **Período** | Uno por bloque: 10 ms con N_b = 100. `beat()` es una asignación de `time.monotonic()` bajo un candado propio (no `_nidaq_lock`) |
| **Reloj** | `time.monotonic()`. El watchdog actual usa `time.time()` (`nidaq.py:169`), que un ajuste de NTP puede adelantar o atrasar; la concesión no debe heredarlo (y conviene migrar el watchdog, §6) |
| **Qué revisa el watchdog** (en su poll de 100 ms) | (a) `now − último_latido > beat_timeout_s` → rutina colgada; (b) `now − t_apertura > max_exposure_s` → la rutina superó su propio T_max, aunque lata |
| **Qué cierra si falta** | `close_all_shutters()` (una escritura, las cuatro líneas a su polaridad de cierre; el 532 nm en ALTO), activa el interlock `"Rutina: Traza de impresión"` (que un hilo que se despierte tarde no pueda reabrir), marca `lease.expired` y avisa por los callbacks del watchdog (banner). No hay forma de saber qué más abrió una rutina colgada: se cierra todo, como hoy |
| **Tiempo de corte de una rutina colgada** | ≤ 1.0 s + 0.1 s (poll) + L_do + L_mec |
| **Por qué 1.0 s y no 30 s** | 30 s sobre una NP ya impresa a ≈ 570 °C es la fila de "daño y defecto casi seguros" del panel experimental (Ronda 1). 1.0 s es ≥ 5 veces la mayor pausa sana esperada (≤ 200 ms, a medir en `BANCO-28`) y mayor que `LAG_FAULT_S` (0.5 s): un hilo vivo pero demorado se corta a sí mismo primero, con el diagnóstico exacto |
| **Relación con la política global** (30 s / "Sin límite") | Mientras una concesión sana es dueña de un obturador, ese obturador queda **fuera** del plazo global: el vencimiento global cierra sólo los obturadores abiertos sin dueño (p. ej. uno abierto a mano desde el panel). La concesión no re-arma el plazo global. Al liberarla con el cierre confirmado no queda nada; si quedara algo abierto, la política global lo toma desde ese instante |

### 3.3 Cómo se evita cortar una rutina sana

| Caso | Qué pasa |
|---|---|
| Captura a los 20 s | ≈ 2000 latidos antes de la captura; el plazo de 1 s nunca vence; el detector cierra |
| Nodo de 40 s sin captura (T_max) | El hilo cierra a los 40.0 s por conteo de muestras ("timeout" del nodo, decisión de la rutina). `max_exposure_s` = 42 s no se alcanza |
| Healing pass (T_max + 10 = 50 s, `measurements.py:2406`) | La concesión se crea con el T_max efectivo de ese nodo (52 s) |
| El operador pasa a "Sin límite" durante el nodo | No afecta a la concesión (C-29 resuelto en esta ruta) |
| La GUI se congela (arrastrar la ventana, diálogo modal) | El hilo de adquisición no depende de la GUI; sigue latiendo. El gráfico se pone al día después |
| Cámara en vivo a 25 fps | Compite por el GIL; sube L_sched pero no llega a 1 s. `BANCO-28` lo mide con la cámara encendida |
| Pausa del sistema de 0.3 s | El hilo lee los bloques atrasados (`LAG_WARN_S`), no pierde muestras, sigue latiendo |
| Pausa del sistema de 0.7 s | Al despertar, `lag > LAG_FAULT_S`: el propio hilo cierra y marca "falla de adquisición" (nodo reintentable). No es el watchdog quien corta |

---

## 4. Coexistencia sobre la misma placa: un único dueño del motor de AI

### 4.1 Recursos de la placa y quién los usa

| Subsistema | Consumidores | ¿Conflicto con la traza? |
|---|---|---|
| **Motor de temporización de AI** (uno solo en la placa; Ronda 1 §1.7) | Traza, Power BS, confocal (paso y rampas), foco (rampa con trigger), contrapropagante, PySpectrum (`read_photodiode_level`) | **Sí.** Una segunda tarea AI temporizada no arranca mientras la primera esté comprometida (−50103) |
| DO estática `port0/line8-11` (obturadores) | Traza (cierre), panel, watchdog, excepthook, rutinas | No hay motor de temporización; las escrituras se serializan con `_nidaq_lock` (L_lock, §2.1) |
| DO `port0/line7` (espejo), AO `ao0/ao1` (filtro de densidad), AO `ao2` (láser 532) | Rutinas, panel | Tareas propias, sin temporización por hardware; `DEC-001` las mantiene separadas de los obturadores |

### 4.2 El árbitro (propuesta, `core/nidaq.py`)

Como todas las tareas AI del proceso salen de `channels_photodiodos()` (§0.1), el árbitro se aplica ahí, sin tocar la
lógica de cada consumidor. Cada concesión tiene un dueño y una clase:

| Pide \ Tiene | Libre | `monitor` (Play / Power BS, sin obturador a cargo) | `impresión` (nodo en curso) | `finita` (confocal, foco, PySpectrum) |
|---|---|---|---|---|
| `impresión` | Concede | **Promoción en el lugar**: la misma tarea sigue corriendo, se engancha el detector. Sin parada, sin hueco, sin −50103 | — | **Rechaza**: el nodo no abre, la rutina pausa ("placa ocupada por …"). En el flujo secuencial de la impresión no debería ocurrir |
| `monitor` | Concede | Se suma como consumidor | Se suma como consumidor (recibe datos decimados) | Rechaza con mensaje |
| `finita` | Concede | **Desaloja al monitor**: el hilo detiene y cierra su tarea (≤ T_b + cierre), avisa "Traza / Power BS en pausa: la placa la usa …", y concede | **Rechaza siempre**, de inmediato, con `AIEngineBusy` ("la placa la tiene la Traza de impresión, nodo n"). Nunca desaloja una impresión y nunca espera bloqueando (congelaría la GUI) | Rechaza |

- **Liberación:** el hilo de la traza libera el motor **en su `finally`**, después de `task.close()`, y recién entonces
  emite el fin del nodo a la rutina. Así el autofoco o el escaneo de deriva siguiente encuentran la placa libre. El
  cierre del obturador ocurrió antes (§3.1-7): la liberación no está en la ruta de latencia.
- **Power BS** deja de tener su propia tarea (`_bs_task`, Ronda 1 §2.6-4): es un consumidor del flujo. Si el flujo corre,
  recibe la media del canal BS por bloque; si no, lo arranca en modo `monitor`. Con eso, abrir Power BS durante una
  impresión ya no puede dejar la traza en −50103.
- **Play manual** es modo `monitor`: sin detector ni concesión de exposición. Si Play abre el obturador (hoy lo hace,
  `trace.py:583`), esa apertura queda bajo la política global, como cualquier apertura manual.
- **PySpectrum en el mismo proceso** (satélite, `DEC-019`): sus rutinas pasan por el mismo `channels_photodiodos()` y
  quedan cubiertas. Además la rutina de impresión debería tomar `hardware_session` mientras corre, para que una rutina de
  PySpectrum no arranque a mitad de una grilla (tema de `software-architect`).
- **Otro proceso** (PySpectrum autónomo, un panel de NI MAX): el árbitro no lo ve. Si el otro tiene la placa, el flujo
  no arranca y el obturador nunca se abre (§1.4, −50103). Si el flujo ya corre, es el otro el que recibe −50103: la
  impresión no se entera. Es el comportamiento correcto para un único dueño; el costo es que el otro proceso falla
  (pregunta §6).
- **Parada de emergencia** (PyPrinting o `_on_emergency_stop_clicked` de PySpectrum): cierra los obturadores
  directamente (seguro entre hilos por `_nidaq_lock`), activa el evento de parada del flujo y no espera al hilo. El hilo,
  al ver el evento, vuelve a cerrar (inocuo), cierra la tarea y libera el motor.
- **`ai3`** está en la tarea de la traza como fotodiodo de 808 nm y en la de foco como trigger Z (C-44). Con el árbitro
  nunca corren a la vez; qué lee la traza en `ai3` depende de `BANCO-20`.

---

## 5. Protocolo de banco que valida E (mapa a `BANCO-26` … `BANCO-32`)

Condiciones comunes: **láseres apagados** (llave o interlock de emisión) salvo `BANCO-32`; las ejecuta el operador. La
señal la da un generador de funciones: en un AI libre para las sondas, o en la entrada `ai0` con el fotodiodo de 532 nm
desconectado para las pruebas con la aplicación. Cada prueba se corre también con la versión revertida (`DEC-037`) cuando
se indica: da la línea de base real de producción.

| ID | Qué valida de E | Procedimiento | Aceptación numérica |
|---|---|---|---|
| **BANCO-26** | La configuración de §1.1 y lo que la placa realmente hace | Sonda de sólo lectura AI (a escribir en `tools/bench/`): crea la tarea de §1.1 y lee `input_buf_size` con y sin fijarlo, `samp_clk_rate`, `ai_data_xfer_mech`, `ai_data_xfer_req_cond` (después de intentar fijar `ON_BOARD_MEMORY_NOT_EMPTY`), `input_onbrd_buf_size`, `wait_mode`, `ai_term_cfg`, `ai_min`, `ai_max`; tiempo desde `start()` hasta el primer bloque. Versiones (`BANCO-23`) | Buffer = 100 000 tras fijarlo; `samp_clk_rate` = 10 000.0 (si no, el eje usa el valor leído y se anota); `DMA`; primer bloque ≤ 2·T_b. Rediseño si la transferencia no es DMA o si la condición no admite `NOT_EMPTY` y `FIFO/2/50 kS/s > 5 ms`. El buffer automático (sin fijar) resuelve la ambigüedad 10 k / 100 k de la Ronda 1 |
| **BANCO-27** | Frescura: la traza sigue a una señal conocida sin atraso creciente | Cuadrada de 1 Hz, 0.10 → 0.20 V, y su salida de sincronismo en un segundo AI libre de la misma tarea; 10 min | Período aparente 1.000 s ± 0.1 %; `lag` p99 ≤ 20 ms, máx ≤ 50 ms; pendiente del `lag` < 1 ms/min; flanco registrado contra sincronismo constante (misma base de tiempo) ± 1 muestra; **cero muestras exactamente 0.000000 V** y cero excepciones. Con `DEC-037`: 1 Hz sin atraso creciente (valida el paso 0) |
| **BANCO-28** | Cadencia, costo y la base del plazo de vida | 60 s en tres condiciones: (A) sin carga; (B) cámara en vivo a 25 fps + gráfico de la traza; (C) B + arrastrar la ventana 5 s tres veces + ventana FFT abierta. Por bloque: llegada (`perf_counter`), duración de la lectura, del procesamiento y `lag`. Comparar `wait_mode` `YIELD` y `WAIT_FOR_INTERRUPT`. Con `DEC-037`: Δt entre ticks y costo de crear-leer-cerrar | Llegadas: mediana 10.0 ± 0.2 ms, p95 ≤ 12 ms, p99 ≤ 20 ms, **máx ≤ 200 ms** en C (si lo supera, `beat_timeout_s` pasa a 5 × máx y se revisa §3); procesamiento p99 ≤ 1 ms; CPU del hilo ≤ 5 % de un núcleo. Con `DEC-037`: el costo por tick p95 (criterio del abogado del diablo: ≤ 20 ms) y el tick real (se predicen ≈ 47 ms) |
| **BANCO-29** | Latencia de software (escalón → línea DO) | Escalones en instantes aleatorios en `ai0`: 0.10 → 0.20 V (r = 2), → 0.16 (r = 1.6), → 0.14 (r = 1.4, con umbral absoluto en 0.12 V) y, si el criterio lo acepta, 0.10 → 0.07 (contraste negativo); ≥ 100 eventos por caso. Osciloscopio: canal 1 el escalón (disparo), canal 2 `P0.11` en la BNC-2110. Opcional: `P0.11` también a un AI libre de la tarea, para medir en la base de tiempo de la placa sin osciloscopio. Repetir con cámara en vivo | Para la configuración elegida: mediana y p95 dentro de ± 5 ms de la simulación de §2.2 más 1 ms; **ningún evento > 100 ms**; con cámara en vivo, p95 ≤ 60 ms en el caso de referencia. **Control con `DEC-037`**: se predicen ≈ 350 ms para r = 2 y ≈ 490 ms para r = 1.6. Ese número, medido, es la respuesta con datos a la pregunta de latencia del investigador |
| **BANCO-30** | El término que el software no controla | LED y fotodiodo a través de la apertura de cada obturador (sin láser). Canal 1 la línea DO, canal 2 el fotodiodo. 20 aperturas y 20 cierres por obturador | Sin umbral a priori; decide el objetivo: p95 de cierre ≤ 20 ms → el objetivo 50 / 100 ms es alcanzable con N_hold 3; 20–50 ms → exige N_hold 1 o reformular; > 50 ms → el objetivo se reformula como "software ≤ X + mecánica medida". Fija `T_blank` = p99 de apertura + 10 ms |
| **BANCO-31** | Robustez y el camino de falla | Con la señal de prueba: (a) congelar la GUI y cámara en vivo; (b) un Test Panel de AI de NI MAX sobre Dev1 **antes** de un nodo; (c) el mismo panel **durante** un nodo; (d) Power BS abierto al empezar un nodo; (e) confocal o foco pedidos a mano durante un nodo; (f) "Reset Device" de NI MAX durante un nodo; (g) con un gancho de depuración sólo para el banco, congelar el hilo de adquisición 3 s | (a) sin `LAG_FAULT`, sin −200279, índice de muestra continuo. (b) nodo "placa ocupada", `P0.11` **nunca cambia** (osciloscopio), rutina en pausa. (c) el error lo recibe NI MAX; el nodo sigue sin hueco. (d) promoción sin hueco ni −50103. (e) rechazo con mensaje en < 100 ms; traza intacta. (f) falla detectada ≤ 0.25 s, interlock `"NI-DAQmx"`; anotar el nivel de `P0.11` tras el reset (depende de `BANCO-16`: sin manejar cae a BAJO = 532 abierto). (g) cierre de todos ≤ 1.2 s en `P0.11`, interlock de rutina y banner; al despertar, el hilo aborta sin reabrir. En todos: **ningún 0.0 V registrado como dato válido**, y después de cada escenario un escaneo confocal arranca (el motor quedó libre) |
| **BANCO-32** ⚠️ | E en impresión real (láser a baja potencia, con aprobación, sólo con 26–31 aprobadas) | Grilla de 5 × 5 con campo oscuro grabando y un control sin coloide (panel experimental, Ronda 1) | ≥ 95 % de nodos "success" con una NP; sin ceros; latencia escalón → `i_close` leída en la traza guardada (misma base de tiempo) dentro del objetivo que se acepte; el control sin coloide: cero paradas antes de T_max |

---

## 6. Riesgos residuales y preguntas

### 6.1 Riesgos que E no elimina

1. **La mecánica del obturador** (L_mec) puede ser por sí sola mayor que el objetivo. Sólo `BANCO-30` lo dice.
2. **Muerte o congelamiento del proceso entero.** Si el proceso muere o un llamado en C retiene el GIL, nadie escribe:
   las líneas quedan en su último valor o, sin manejar, caen a BAJO por el pull-down, y el 532 nm queda **abierto**
   (`BANCO-16`). Tampoco lo cubre el watchdog de software si un hilo queda bloqueado **dentro** de `_nidaq_lock`, porque
   `close_all_shutters()` toma el mismo candado. Opción a evaluar en la fase 6.2, **sin afirmarla**: el temporizador
   watchdog de la propia placa (`nidaqmx.system.WatchdogTask`: "If this time elapses, the device sets the physical
   channels to the states you specify" [NI-DOC `system/watchdog.py`]). Si la PCIe-6353 lo admite en `port0` y cómo
   convive con la tarea estática de obturadores se verifica en el manual de la serie X, que no está en
   `docs/bibliografia/`.
3. **GIL.** L_sched depende de lo que hagan los otros hilos (cámara, pyqtgraph); sólo se acota midiendo (`BANCO-28`).
4. **Reloj del watchdog.** `time.time()` (`nidaq.py:169`) no es monotónico; un ajuste de NTP puede adelantar o demorar un
   corte. La concesión usa `time.monotonic()`; conviene migrar el watchdog.
5. **`_nidaq_lock` compartido.** Un cierre desde el hilo de la traza puede esperar hasta ≈ 100 ms si otro hilo está en
   un cierre que reintenta (§0.5). Está en el peor caso de §2.3.
6. **El árbitro cubre sólo este proceso.** Otro programa sobre Dev1 recibe −50103 o bloquea a la impresión (seguro por
   "primero adquirir", pero corta al otro).
7. **Criterio.** Con u = 1.5, un escalón de ×1.4 no dispara el criterio relativo; con ventanas cortas hace falta una
   guarda entre I_old e I_new (§2.2). Las ventanas en ms las fija otro panel; sin eso, E no baja la latencia.
8. **Fuga de tarea en el paso 0** (§0.2): sin `finally`, una excepción de lectura puede dejar tomado el motor de AI.
9. **`down_flipper()` ignorado** (`measurements.py:2318`): la traza puede arrancar en baja potencia sin que nadie lo sepa.
10. **Eje de tiempo de `NP_*.txt`.** `_save_trace` escribe un eje sintético (`np.linspace`, Ronda 1 del abogado del
    diablo §0.8). E da el eje exacto por índice de muestra; si no se guarda, la latencia no se puede verificar sobre los
    archivos. La emisión a la GUI debe ser con "último valor" (coalescente), nunca una cola de señales sin límite
    (abogado del diablo, Ronda 1 §2-D).
11. **`ai3`** doble uso (C-44, `BANCO-20`).

### 6.2 Preguntas para el investigador (una línea cada una)

1. **Latencia, explicada:** hoy, con umbral 1.5 y N_hold 3, calculamos que la orden de cierre sale ≈ 0.35 s después del
   escalón (≈ 0.5 s si es ×1.6), más lo que tarde el servo; el legado cortaba en 10–100 ms. ¿Aceptás como objetivo, del
   escalón al haz tapado, mediana ≤ 50 ms, p95 ≤ 100 ms y techo 200 ms, o preferís fijarlo después de medir el servo
   (`BANCO-30`)?
2. ¿Qué `steps_before` / `steps_after` tiene el preset "umbral + valor absoluto"? (confirma el ≈ 0.35 s)
3. Con umbral 1.5, ¿los escalones de ×1.4 los detecta el umbral absoluto? ¿Qué `umbral_abs_v` usan?
4. ¿Hay un AI libre que pueda quedar cableado a `P0.11` (línea del 532) para registrar apertura y cierre?
5. En el obturador de fabricación propia, ¿la línea TTL entra a un microcontrolador que genera el PWM del servo?
6. Si pedís un confocal o un foco a mano con la traza en Play, ¿preferís que la traza se pause sola o que el escaneo se niegue?
7. ¿Corren alguna vez PySpectrum y PyPrinting como dos programas separados a la vez sobre la misma placa?
8. ¿Aceptás que un nodo con más de 0.5 s sin evaluar se cierre como "falla de adquisición" y se reintente en el healing pass?
9. ¿Aceptás 1.0 s como plazo del latido de vida de la traza (una rutina colgada se corta en ≈ 1.1 s, no en 30 s)?
10. Si el watchdog corta una rutina colgada, ¿el interlock lo libera sólo el operador (propuesta) o también la rutina al abortar?

### 6.3 Si se cae a la alternativa C

Misma tarea de §1.1 salvo `overwrite = OVERWRITE_UNREAD_SAMPLES`, `relative_to = MOST_RECENT_SAMPLE` y
`offset = −N_ventana`, esperando `total_samp_per_chan_acquired ≥ N_ventana` antes de la primera lectura (−200277).
Temporizador `PreciseTimer` de 10 ms. La latencia sigue dominada por las ventanas del criterio (§2.2) y hay que sacar
igual la decisión del hilo GUI. Se pierde el síntoma ruidoso del atraso (−200279): hay que medir el atraso con
`total_samp_per_chan_acquired` contra el reloj de pared en cada tick.

---

## 7. Veredicto

- **Diseño E, tal como está especificado aquí: `HARDWARE_SAFE` en diseño**, condicionado a `BANCO-26` … `BANCO-31`.
  - Cada falla de lectura cierra el obturador.
  - El obturador no se abre sin un bloque válido.
  - La concesión de exposición corta una rutina colgada en ≈ 1.1 s y no corta una sana.
  - Un único dueño del motor de AI, sin 0.0 V inventados.
- **Objetivo de latencia: `TIMING_HAZARD` abierto** hasta medir el servo (`BANCO-30`) y fijar las ventanas en ms con
  guarda. La parte de software de E (≈ 43 / 52 ms mediana / p95 en el caso de referencia) cumple el objetivo sólo si el
  servo tapa el haz en pocos ms.
- **Producción actual (`7f5d10a`) y paso 0: `TIMING_HAZARD` conocido**, mayor que lo estimado en la Ronda 1.
  - Los 105–140 ms de entonces eran para el modo 0 con u = 1.2.
  - Con la práctica real (u = 1.5, N_hold 3) son ≈ 0.35–0.5 s de software.
  - Se suma el defecto de §0.2 (sin `finally`), de arreglo inmediato.
