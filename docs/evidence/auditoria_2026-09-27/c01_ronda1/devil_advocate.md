# C-01 — Ronda 1 — Abogado del diablo

Fecha: 2026-09-27. Árbol: `main` @ `7ae2d07`. Sólo lectura: no se tocó el repositorio. Los dos scripts de sondeo (`thread_probe.py`, `timer_probe.py`) están en esta carpeta del scratchpad y usan PyQt6 solo, sin código del repo ni hardware.

Marcas de evidencia: **[CÓDIGO]** leído en la línea citada · **[MEDIDO]** ejecutado en esta PC · **[INFERIDO]** razonamiento no probado · **[NO VERIFICADO]** depende del banco o de documentación de NI que no se pudo leer.

---

## 0. Hechos verificados que cambian el marco

1. **[CÓDIGO]** `trace.py:627-628, 633, 703`: tarea continua, QTimer de "35 ms", `read(10)` sin `relative_to` ni `overwrite`. Si la lectura lanza una excepción se registra `0.0` en los tres canales (`:734-736`), no NaN.
2. **[CÓDIGO]** `_bs_task` (`trace.py:521-526, 550, 554-556`) tiene **exactamente el mismo patrón**: continua, `read(10)` cada 35 ms, y 0.0 V ante una excepción.
3. **[MEDIDO] La cadencia no es de 35 ms.** Un `QTimer.start(35)` con el tipo por defecto (Coarse), dentro de un `QThread` en esta PC con Windows 11: media **47.05 ms**, mediana 47.4, p5-p95 41-49, rango 31-63 ms. Con `PreciseTimer` da 35.00 ms (34.1-35.9). Un Coarse de 10 ms da 10.0 ms: Qt usa el temporizador preciso por debajo de 20 ms. La PC del banco puede dar otra cosa, porque la resolución del temporizador de Windows depende de los demás procesos abiertos.
4. **[MEDIDO] La decisión de parada corre en el hilo de la GUI.** `data_printingSignal` se conecta a `self._dispatch_trace` (`app.py:473`), un método Python del `Backend` contenedor (`app.py:421`), que nunca se mueve a otro hilo (`app.py:634-644` mueve sólo los sub-workers). El sondeo reproduce ese cableado: la señal se emite en el worker y el slot corre en el **hilo principal**. `_dispatch_trace` llama directamente a `printingWorker.grid_trace_detect` (`app.py:529-538`). Por lo tanto el criterio, `close_shutter` y `_save_trace` se ejecutan en el hilo de la GUI, mientras que el temporizador de la traza vive en `confocalThread`. `contrapropagante.py:1225-1229` repite el mismo esquema.
5. **[CÓDIGO] En el legado esto era síncrono.** `printing2/PyPrinting_UNSAM.py:421` conecta directamente `traceWorker.data_printingSignal` con `printingWorker.grid_trace_detect`. Ambos workers están en el mismo hilo (`:489` mueve el contenedor), así que la secuencia tick → decisión → `stop()` ocurría dentro del mismo tick.
6. **[CÓDIGO] El criterio cuenta ticks, no tiempo.** M = M2 = 10 (`config.py:127-128, 155-156`), `N_hold` y el `dI_dt` sobre `timeaxis[-1]-timeaxis[-5]` (4 ticks, `measurements.py:2345-2348`) están en ticks. `T_max` está en segundos de reloj de pared.
7. **[CÓDIGO + MEDIDO]** Con n = M, `I_old = mean(intensity_l1[0:0])` = **NaN** (`trace.py:759`; comprobado con numpy 2.4.6). En ese tick todas las comparaciones dan falso. Para M < n < M+M2, la línea base es el promedio de los primeros n−M ticks, justo los que caen sobre la apertura del obturador. El legado hace lo mismo (`Trace_pp.py:414-421`), así que esto es heredado.
8. **[CÓDIGO]** `_save_trace` (`measurements.py:2971`) guarda `t = np.linspace(0.01, timer_real, ptr)`, un eje **sintético y uniforme**. Los `NP_xxx.txt` no permiten ver el jitter, sólo la cadencia media (`t_print / filas`). El eje real de reloj de pared sólo se guarda en `trace.txt` (`trace.py:782`).
9. **[CÓDIGO]** nidaqmx 1.5.0: `Task.read(..., timeout=10.0)` (`.venv/.../nidaqmx/task/_task.py:517`). `Task.__del__` **sólo emite un aviso** si la tarea no se cerró y "los recursos pueden seguir reservados" (`:126-133`).
10. **[CÓDIGO]** Los modos de parada 1-4, con `N_hold`, `slope_flat` y `umbral_abs_v`, entraron en `d56a1c4` (2026-08-04). En ese momento la cadencia era `start(0)`, es decir, lo más rápido posible. Nunca se recalibraron para 35 o 47 ms.
11. **[CÓDIGO]** DEC-013 (`DECISION_LOG.md:166`) justifica ANOM-TRACE-01 sólo con que la cadencia "dependía del scheduler" y que eso socavaba la etiqueta de "10 kHz". **No cita ninguna medición ni ninguna falla observada en el banco.**

---

## 1. Supuestos del diagnóstico que podrían ser falsos

| # | Supuesto | Estado | Qué lo rompería |
|---|---|---|---|
| S1 | El banco corrió un commit ≥ `6abbbfc` | **NO VERIFICADO** (el triage lo admite) | `git log -1` en la PC del banco; fecha y encabezado de los `NP_xxx.txt` |
| S2 | Buffer de 10 kS/canal, desborde a ≈ 1.03 s | **NO VERIFICADO.** Sale de un *resumen de búsqueda* de la tabla de NI, no del Help instalado. 10 000 S/s cae **exactamente en la frontera** entre las filas "101-10 000" y "10 001-1 000 000". Si el borde es exclusivo o la tasa se ajusta un poco hacia arriba, el buffer es de 100 kS y el desborde llega a ≈ 10.3 s | Leer `task.in_stream.input_buf_size` y `task.timing.samp_clk_rate` después de `start()` en el banco |
| S3 | "Tras el desborde, cada lectura falla de inmediato" | **NO VERIFICADO** (la fuente es un post de foro) | Si una lectura posterior **bloquea** hasta `timeout=10 s` en lugar de fallar, el `confocalThread` se congela, no llegan ticks, `grid_trace_detect` no evalúa `T_max` y el láser queda abierto hasta que actúa el watchdog (30 s). Es peor que el escenario del triage. B-07 tiene que cronometrar cada `read()` |
| S4 | "El criterio nunca da success" | **PARCIALMENTE FALSO [INFERIDO]**. Antes del desborde, la traza reproduce los primeros ≈ 29 ms de exposición estirados a ≈ 1 s. Si el obturador tarda más de ≈ 10 ms más el tiempo de creación de la tarea en abrir (`measurements.py:2318-2319`: `open_shutter` + `sleep(0.01)`, y después la tarea se crea en `_start`), el flanco de subida queda en los primeros ticks y **I_old** sale bajo. Entonces `I_new > 1.2·I_old` da un **"success" espurio a ≈ 0.5-1 s**. Una captura real dentro de los primeros 29 ms también da "success", con ≈ 34× de retraso | La firma "todo timeout" no sirve como falsador limpio. Una mezcla de "success" tempranos y timeouts también es compatible con el defecto |
| S5 | Tratar 0.0 V como "caída" | **VERIFICADO**, pero condicional: con `umbral_down = 0.8`, el tercer cero produce un timeout; con 0 (el default, `config.py:153`) el nodo sigue hasta T_max. Con `slope_min > 0`, el modo queda anulado | — |
| S6 | Cadencia de 35 ms | **REFUTADO en esta PC [MEDIDO]: 47 ms.** Todas las cifras de C-01b (3.5×, 105 ms, 245 ms, ventanas de 350 ms) son ≈ 1.34× optimistas. La dependencia del scheduler que ANOM-TRACE-01 quería eliminar viene sobre todo del **tipo de QTimer**, no de crear y destruir la tarea, y esa parte nunca se tocó | `timer_real / (filas − 1)` de cualquier `NP_xxx.txt` del banco, o `np.diff` de un `trace.txt` |
| S7 | "El legado es la referencia" y "volver a la tarea finita equivale al legado" | **FALSO en tres ejes [CÓDIGO]**: (a) la cadencia del legado era ~10 ms (`start(0)`) y la de 3.0 es 47 ms; (b) en el legado la decisión era síncrona en el mismo hilo y en 3.0 es asíncrona, en el hilo de la GUI (§0.4-0.5); (c) el legado sólo tenía el modo 0, y los modos 1-4 son nuevos y nunca se calibraron en el banco | — |
| S8 | `_bs_task` tiene el mismo defecto | **VERIFICADO [CÓDIGO].** Síntoma que el investigador tendría que haber visto: la lectura de Power BS se congela y cae a 0 V al segundo | Si después del 19-09 alguien usó Power BS o dio Play a la traza y la señal siguió viva más de 1 s, el diagnóstico cuantitativo es falso (o el banco no corre esa versión) |
| S9 | No hay otros consumidores de la traza | **FALSO [CÓDIGO]**: Frontend y FFT (`trace.py:443-458`), `TimeVoltTrackingDialog` (t_step calculado sobre el eje sintético), HDF5 (`measurements.py:2984-2990`), ETA (`t_raw_history`), el Healing Pass y el contrapropagante. Todos los datos de sesiones ≥ `6abbbfc` están contaminados | — |

---

## 2. Modo de falla más probable de cada opción en el banco

**Regla transversal.** Ninguna opción es aceptable si no cambia el centinela `0.0` de `trace.py:736` y `:556` a NaN, y si el criterio no trata NaN de forma explícita. Hoy NaN deja todas las comparaciones en falso y el nodo llega a T_max. Con cualquier opción, un error esporádico sigue pareciendo una "caída".

### (A) Tarea finita por tick, como antes del 19-09
- **¿Reintroduce lo que motivó ANOM-TRACE-01?** Sólo "en la etiqueta". DEC-013 no presenta ninguna falla medida, y el criterio cuenta ticks, así que el jitter no lo invalida. La mayor parte del jitter la pone el QTimer (§0.3) y está presente también en A, B y C. **Es la única opción con evidencia empírica a favor:** imprimió entre el 07-28 y el 09-18, y también en el legado.
- **Falla probable:** (1) el costo de crear, confirmar, arrancar y cerrar la tarea en cada tick bloquea el `confocalThread`. No está medido, y si la placa fuera USB (ver §4-N6) serían decenas de ms. (2) Aparecen **-50103 intermitentes** cuando existe otra tarea de AI: Power BS abierto, una tarea filtrada o una lectura de PySpectrum. Eso da ceros sueltos, y con `umbral_down = 0.8` bastan 3 ceros en una ventana de 10 para un "timeout" espurio. (3) Se lee una ráfaga de 1 ms cada 47 ms (≈ 2 % de ciclo útil): las partículas que pasan se pierden casi siempre y los 50 Hz de red se pliegan a ≈ 7 Hz.
- **Supuesto que la rompe:** que el costo por tick sea ≪ 35 ms en la placa real.

### (B) Continua, leyendo todo lo disponible en cada tick
- **Cambia el significado de cada punto:** pasa de una instantánea de 1 ms a un promedio de ≈ 470 muestras (35-47 ms). El ruido blanco baja ≈ √47, el zumbido de 50 Hz se atenúa ≈ 8× (sinc) y **las partículas de paso se integran siempre**, atenuadas, en lugar de perderse. El cociente 1.2 no depende de la escala, pero `umbral_abs_v`, `slope_flat` (V/s), `N_hold` y `slope_min` sí cambian de sentido. También los presets (`presets/*.txt`).
- **Falla probable:** (1) una lectura vacía (`avail = 0`) da `np.mean([])` = NaN, que contamina la ventana de 10 ticks y deja el criterio ciego ≈ 0.5 s. (2) Si ya había una tarea abierta (§4-N4), la falla es **persistente**, no intermitente. (3) Si el `confocalThread` se traba más que la duración del buffer, vuelve el -200279 y hace falta un camino de recuperación.
- **Supuesto que la rompe:** que los umbrales calibrados sobre instantáneas de 1 ms sirvan igual para promedios de 35-47 ms.

### (C) Continua, leyendo sólo las N más recientes con sobrescritura
- Es la más parecida al legado en semántica (instantánea de 1 ms, pero con reloj de hardware). **Sigue descartando el 98 % de las muestras**, así que el plegado de 50 Hz y la pérdida de transitorios son iguales que en A. Sólo evita el costo de crear y cerrar la tarea.
- **Falla probable:** (1) `MOST_RECENT_SAMPLE` con `offset = −N` antes de tener N muestras produce un error en la primera lectura. (2) "Más reciente en el buffer de la PC" no es "más reciente en el ADC": con DMA la diferencia es chica y con USB es un pedido de transferencia completo. (3) El mismo problema persistente de tareas filtradas y -50103 que en B. (4) Con sobrescritura **nunca** hay error de desborde, así que perdemos el único síntoma ruidoso de un atraso.
- **Supuesto que la rompe:** el modelo de placa y el mecanismo de transferencia.

### (D) Continua con callback en un hilo de adquisición
- **Falla probable [INFERIDO a partir de §0.4]:** la decisión corre en el hilo de la GUI. Un callback cada N muestras (p. ej. 100 Hz) encola eventos en la GUI, y si la GUI va más lenta que el productor (cámara en vivo, pyqtgraph) **la cola crece sin límite y sin ningún error**. Es C-01 trasladado del buffer de DAQmx, que por lo menos falla con ruido, a la cola de Qt, que falla en silencio. A eso se suman la contención por el GIL, las excepciones que se tragan dentro del callback, el orden entre desregistrar y cerrar, y que no se puede probar en `SAFE_MODE` sin un doble con temporización.
- **Supuesto que la rompe:** que el consumidor sea más rápido que el productor. Hoy no está garantizado.

### Umbrales y tiempos calibrados implícitamente para una cadencia
| Parámetro | Unidad real | Legado (~10 ms) | 3.0 hoy (47 ms medidos) | Efecto de cambiar la cadencia u optar por B |
|---|---|---|---|---|
| M, M2 = 10 | ticks | ≈ 100 ms | ≈ 470 ms | Si se arregla C-01b volviendo a 10 ms, la ventana se reduce 4.7× |
| `N_hold` = 5 (modos 1-4) | ticks | ≈ 50 ms (cadencia de cuando se agregó) | ≈ 235 ms | Se agregó sobre `start(0)` y nunca se calibró |
| `slope_flat` (V/s, `dI_dt` sobre 4 ticks) | V/s | Δt ≈ 40 ms | Δt ≈ 190 ms | σ(dI/dt) ∝ σ_tick/Δt: con 10 ms es 4.7× más ruidoso; con B, σ_tick es ≈ 7× menor |
| Umbral 1.2 (modo 0) | adimensional | Afinado sobre instantáneas de 1 ms | Igual con A y C | Con B baja la tasa de falsos positivos por ruido y sube la de partículas de paso |
| `SEND_WINDOW` = 2000 | ticks | — | 94 s | **A 10 ms son 20 s.** El Healing Pass (T_max + 10 = 30 s) supera 2000 ticks y `_save_trace` lanza ValueError (medido con numpy: `np.transpose` de un arreglo irregular). Pasa en el hilo de la GUI, después de `close_shutter`, pero **no se emite `grid_detectSignal`** y la impresión queda detenida |
| Heartbeat cada 30 ticks | ticks | — | ≈ 1.4 s | Irrelevante mientras sea ≪ 30 s |

---

## 3. Criterios de falsación

**F1 — del diagnóstico, en el banco y con el código actual.** Registrar en cada tick `input_buf_size`, `samp_clk_rate`, `avail_samp_per_chan`, `total_samp_acquired`, `curr_read_pos`, la duración de `read()` y el código de excepción. Hay que usar un **escalón** con una marca de tiempo (obturador o chopper conmutado con TTL en una AI libre), no un reflector estable: B-07, tal como está redactado, detecta los ceros pero **no el atraso**. Predicción del diagnóstico: buffer de 10 000, `avail` crece ≈ 460 por tick, la primera excepción es -200279 a ≈ 1.0 s y las siguientes llegan en menos de 1 ms. **El diagnóstico queda falsado si** el buffer es de 100 000, si no hay excepción en 30 s o si `read()` bloquea.
- Variante sin banco: un dispositivo **simulado** PCIe-6353 en NI MAX en la PC de desarrollo. Hay que confirmar que el simulador modela el desborde.
- Variante gratis: la respuesta a Q2 (Power BS o Play cayendo a 0 al segundo).

**F2 — de la opción elegida, con un doble de tarea que modele el buffer** (cierra S-12). El doble necesita un contador de muestras gobernado por el reloj, un buffer finito, -200279 al desbordar, y la semántica de `relative_to`/`overwrite`. La opción queda falsada si no cumple cualquiera de estas condiciones:
1. Un escalón inyectado en el instante de adquisición t_a aparece en `I_new` antes de t_a + (M + 1)·Δt.
2. 60 s sin excepción.
3. Un error produce NaN y **no** un "timeout" por `umbral_down`.
4. Dos `trace_configuration` seguidos no dejan una tarea filtrada (contar las tareas abiertas).
5. Con Power BS activo, empezar a imprimir lo detiene o se niega a arrancar.

Criterios propios de cada opción:
- **A:** falsada si en el banco el p95 del costo de crear a cerrar una tarea supera ≈ 20 ms, o si aparece -50103 en una sesión normal.
- **C:** debería ser estadísticamente idéntica a A tick por tick, porque toma la misma instantánea. Si no lo es, hay un efecto de transferencia.
- **B:** falsada si, sobre la misma muestra coloidal y con la misma potencia, la proporción de "success" o de falsos positivos por partículas de paso difiere de A más que la dispersión entre corridas.
- **D:** falsada si la latencia entre la emisión y `grid_trace_detect` crece a lo largo de un nodo de 20 s.

**F3 — de extremo a extremo (B-01).** Un fotodiodo rápido detrás del obturador, un osciloscopio y una marca TTL en el instante de la decisión. La latencia medida debería ser ≈ M·Δt + N_hold·Δt + cola de la GUI + cierre mecánico. Si es mayor, falta un término (probablemente la cola de la GUI).

**F4 — ticks rezagados (§4-N1).** Test unitario: dos llamadas a `_dispatch_trace` con un payload que dispara la parada deberían emitir `grid_detectSignal` **una sola vez**. Por el código van a ser dos, porque `grid_trace_detect` (`measurements.py:2325`) no tiene guarda contra la reentrada. En el banco: buscar índices de nodo salteados o escaneos duplicados en los logs.

---

## 4. Lo que no estamos preguntando

- **N1. Topología de la decisión (§0.4, MEDIDO).** Entre la emisión del tick decisivo en `confocalThread` y el momento en que se procesa `stop()` en ese mismo hilo pasa la latencia de la cola de la GUI más una vuelta. Los ticks emitidos en ese intervalo ya están en la cola de la GUI y vuelven a evaluar el criterio sobre el mismo nodo. Como no hay guarda, pueden disparar un segundo `grid_detectSignal`, que en `_grid_detect` hace `i_global += 1` dos veces (**un nodo saltado**), o un segundo `_save_trace` y una ETA sesgada. [INFERIDO: depende de que la latencia de la GUI supere un tick.] Volver a 10 ms o usar D **amplifica** el problema. En el legado no existía porque todo corría en el mismo hilo.
- **N2. Tipo de QTimer (§0.3).** Cambiar a `PreciseTimer` es una línea y corrige parte de C-01b, pero cambia el sentido de todos los parámetros medidos en ticks (§2). Hay que decidir si las ventanas se expresan en **ticks o en segundos** antes de tocar la cadencia.
- **N3. Ciclo de vida de las tareas.** `trace_configuration` no cierra `_bs_task` ni un `self._task` anterior (`trace.py:624` lo pisa). No hay nada que impida imprimir con la traza en Play (grep: ningún `play_pause`/`stop` en el arranque de la impresión). Con B, C o D, una tarea filtrada **reserva la AI hasta que termina el proceso** (§0.9), y fallan también el confocal, las rampas de foco y `read_photodiode_level`. Con A la falla es intermitente.
- **N4. La placa tiene un solo motor de temporización de AI.** Una tarea continua persistente bloquea a cualquier otro consumidor: confocal (`confocal.py:817, 938, 947`), foco (`focus.py:430`), contrapropagante (`:722`) y PySpectrum `read_photodiode_level` (`dimers.py:539`, `growth_kinetics.py:760`) si corren en la misma sesión (DEC-019, modo satélite).
- **N5. Los criterios de PySpectrum tienen la misma familia de defectos.** `read_photodiode_level()` usa por defecto `channel_index = 0`, que es **siempre ai0, el fotodiodo del 532 nm** (`config.py:86-87`), sea cual sea el láser. Toma `i_old` de una única lectura en t = 0, justo en el transitorio de apertura, y lee 5 muestras a 1 kS/s (`optical_support.py:73-88`).
- **N6. Modelo de placa contradictorio en la documentación.** `SYS-101:74, 99` dice USB-6343; `SYS-305:155` dice PCIe-6353 (según la tesis). La tasa multicanal de 1.0e6 de `config.py:75` encaja con la 6353; de memoria, la USB-6343 no llega a 1 MS/s, pero hay que confirmarlo con la hoja de datos. USB o PCIe cambia el costo por tick de A y la latencia de C.
- **N7. Datos viejos contaminados.** Todos los `NP_xxx.txt`, HDF5, histogramas de TimeVolt y umbrales elegidos mirando trazas de sesiones ≥ `6abbbfc` son inválidos. Además, el eje de los NP es sintético (§0.8).
- **N8. Aliasing en la ventana FFT de la traza.** Con instantáneas cada 47 ms, la red de 50 Hz aparece a ≈ 7 Hz y puede leerse como vibración mecánica.
- **N9. La etiqueta de "10 kHz" (S-6).** Ninguna de las opciones A-D decide más rápido que un tick. Una parada con latencia de milisegundos requiere un disparo por hardware (disparo por flanco analógico o contador que actúe sobre la línea del obturador). No es tema de C-01, pero conviene nombrarlo para que nadie presente B o D como "10 kHz".

---

## 5. Preguntas para el investigador (se contestan en una línea)

1. ¿Qué commit corre hoy la PC del banco (`git log -1 --format="%h %ad"`)?
2. Después del 19-09, al dar Play a la traza o abrir Power BS, ¿la señal seguía viva más de 1 s o caía a 0 V?
3. "Imprime bien", ¿se refiere al legado (PyPrinting 2) o a 3.0? ¿De qué fecha es la última impresión con 3.0?
4. En esa sesión, ¿los NP quedaron "SUCCESS" o "TIMEOUT" en el encabezado, y cuántas filas y qué `t_print` tiene uno típico?
5. En NI MAX, ¿la placa `Dev1` es una PCIe-6353 o una USB-6343?
6. ¿Qué obturador tiene el láser de impresión y cuántos ms tarda en abrir?
7. ¿Qué modo de parada y qué `umbral_down` usan en la práctica: el preset (0.8) o "Personalizado" (0)?
8. Una captura típica, ¿ocurre a los ms, a los cientos de ms o a los segundos de abrir el obturador?
9. Mientras imprimen, ¿tienen abiertas la cámara en vivo, la traza o Power BS?
10. ¿Vieron alguna vez en 3.0 un nodo saltado o dos escaneos seguidos del mismo nodo?
11. ¿Prefieren que las ventanas M, M2 y N_hold se expresen en segundos (independientes de la cadencia) o en puntos, como en el legado?

---

## 6. Veredicto

**`HIGH_RISK_ASSUMPTIONS`.**
- El **mecanismo** de C-01 está verificado en el código y resiste el análisis.
- La **predicción cuantitativa** (1.03 s y ceros) descansa sobre una tabla de NI leída en un resumen, justo en la frontera de fila, y sobre un post de foro.
- La **firma** "nunca hay success" no sirve como falsador (S4).
- La premisa de que **el legado es la referencia** oculta tres diferencias: la cadencia (10 frente a 47 ms medidos), la topología (decisión síncrona frente a decisión en el hilo de la GUI) y los modos 1-4, que nunca se calibraron.
- **Sobre las opciones:**
  - **A** es la única con evidencia empírica a favor: es exactamente lo que imprimió hasta el 18-09.
  - **B** y **D** cambian el significado físico de cada punto o el lugar donde se acumula el atraso, sin evidencia de que haga falta.
  - **C** sólo ahorra el costo por tick y pierde el síntoma ruidoso del atraso.
- **Lo que decide:** F1 (o Q2) confirma el diagnóstico; F2 permite elegir entre opciones; N1, N2 y N3 hay que resolverlos antes de tocar la cadencia.
