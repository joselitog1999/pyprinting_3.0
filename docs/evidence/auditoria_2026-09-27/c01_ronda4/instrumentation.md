# C-01 / R4-17 — mini Ronda 1 — Panel de instrumentación (`instrumentation`)

Estado: COMPLETO (2026-10-01). Ronda de análisis: no se modificó código ni tests y no se ejecutó nada
contra hardware. Único archivo escrito en el repositorio: este. Árbol: `main` @ `7aab0d8`.

**Objeto.** La secuencia de hardware de la parada de emergencia de PyPrinting (R4-17, N-2), su
disparo con un modal abierto y en modo satélite (N-1, Q-5), "Cerrar todos · la grilla sigue" con el
backend `legacy_timer` (P-H, N-4) y los pasos entre nodos que abren obturadores (N-3, P-a).

**Qué leí.** `CLAUDE.md`, `lab-invariants.md` §1-§2, `gui_design_v2.md` §5 y §6.5-6.7,
`qa_ux_audit.md` §7, `c01_ronda2/instrumentation.md` y `architecture.md` (§0, §2, §5.9),
`RESPUESTAS_INVESTIGADOR.md` (rondas 1 a 9), `DEC-036` y `DEC-037`. Código, orientado con
`graphify query/explain`: `core/nidaq.py`, `core/shutters.py`, `config.py` (`_PIController`,
`wait_on_target`), `modules/measurements.py`, `modules/trace.py`, `modules/focus.py`,
`modules/confocal.py`, `app.py`, `pyspectrum/modules/hardware_session.py`, `pyspectrum/window.py` y,
como referencia, el legado `printing2/Printing_pp.py` y `PyPrinting_UNSAM.py`. Leí también las notas
hermanas de esta ronda (`devil_advocate.md`, `experimentalist.md`) para no contradecirlas sin decirlo.

**Marcas.** **[CÓDIGO]** archivo:línea leído en `7aab0d8` · **[MEDIDO]** sonda ejecutada en esta PC,
sin hardware · **[NI-DOC]** firma o docstring de `nidaqmx` 1.5.0 del `.venv` · **[INFERIDO]**
razonamiento no probado · **[BANCO]** se resuelve en el banco · **[INVn]** respuesta del investigador
de la ronda n · **[DA]**, **[EXP]** notas hermanas `devil_advocate.md` y `experimentalist.md`.

**Sondas** (en el scratchpad de la sesión, no en el repositorio; PyQt6 6.6.1 del `.venv`,
`QT_QPA_PLATFORM = offscreen`, `SAFE_MODE = True`):
- `ins_estop_probe.py`: atajo de aplicación contra filtro de eventos con un modal de aplicación,
  ambigüedad de `Ctrl+E`, hilo en el que corre un cierre conectado a la señal de un worker, y
  `RLock.acquire(timeout)` frente a un dueño colgado.
- `ins_pause_during_af_probe.py`: reproduce, con los backends reales de `measurements` y `trace` en
  `SAFE_MODE`, el orden de eventos de una Pausa y de una "parada sólo con interlock" que llegan
  durante el autofoco entre nodos.

---

## Resumen ejecutivo

1. **Hallazgo nuevo, `SAFETY_VIOLATION` en el código actual (regresión respecto del legado).** Una
   **Pausa durante el autofoco entre nodos deja el 532 nm abierto a alta potencia, sin detección y
   con el watchdog renovado indefinidamente** [MEDIDO, `ins_pause_during_af_probe.py`, caso A].
   - Causa: `app.py:487-490` conecta `autofinishSignal` a un cierre (closure). Ese cierre corre en el
     **hilo GUI** [MEDIDO, sonda 4], así que `grid_finish_autofoco` y `_grid_trace` también.
   - La Pausa, encolada al `confocalThread`, corre **antes** de que el hilo GUI llegue a abrir, porque
     `grid_finish_autofoco` empieza con `sleep(0.1)` y sigue con más esperas (`measurements.py:2272,
     2310-2311, 2318`). Pone `mode_printing = "none"` (`:2945`).
   - `_grid_trace` abre igual (`:2318-2319`) y arranca la traza con modo `"none"`, que no emite datos
     al criterio (`trace.py:738-740`): nadie cierra.
   - La traza llama `heartbeat_shutter(30.0)` cada 30 ticks (`trace.py:643-644`), así que el plazo de
     30 s no vence nunca, ni siquiera en "Sin límite" (C-29).
   - En el legado, `autofinishSignal` iba al slot del worker (`printing2/PyPrinting_UNSAM.py:418`): el
     fin del autofoco corría en el mismo hilo, antes de la Pausa, y la Pausa cerraba después. Es una
     regresión de 3.0 y entra en R4-17 como bloqueante. Ver §1.6.
2. **La parada tiene que detener la máquina de estados, no sólo cerrar.** Con "interlock + cierre" y
   nada más, la grilla sigue: mueve la platina, arranca la traza en oscuridad, rotula "timeout" y
   avanza [MEDIDO, caso B]. Y si después se rearma, el nodo siguiente abre **sin Play**. Coincide con
   [DA] §0-2.
3. **N-2 confirmado y ampliado.** `close_all_shutters()` toma `_nidaq_lock` sin plazo
   (`nidaq.py:537`). Lo mismo hacen el botón "Cerrar Todos" (hilo GUI, `shutters.py:308-315`), el
   watchdog (`nidaq.py:187`), el excepthook, el `atexit` y la E-STOP de PySpectrum (hilo GUI, con el
   candado de sesión tomado, `hardware_session.py:158-165`).
   - También `set_shutter_interlock` lo toma (`nidaq.py:286`).
   - Con un hilo colgado adentro **no cierra nadie**, y la GUI se congela.
   - Además, dentro del candado hay **E/S de disco**: `set_detection_mirror` guarda el estado del
     espejo (`nidaq.py:811` → `:730`).
   - **Propuesta (§1):** bandera de parada sin candado, consultada por `open_shutter`; un hilo
     cerrador con `acquire(timeout = 0.25 s)` que reintenta sin rendirse; y un banner con el remedio
     físico.
4. **Platina PI: no mandar `STP`/`HLT`.** Sólo dejar de emitir `MOV`, con una guarda en cada entrada
   de la máquina de estados (§1.4). Un comando extra por USB espera el `RLock` de `_PIController`
   (`config.py:381`), que `connect()` retiene ≥ 3 s (`config.py:471-474`). Si se mandara sin ese
   candado, podría fabricar un `−1004` que `DEC-036` clasifica como falla de comunicación: interlock,
   reconexión del operador y home. Todos los generadores de onda están en un solo ciclo
   (`WGC(eje, 1)`, `focus.py:438`, `confocal.py:906, 928`).
5. **N-1 confirmado** [MEDIDO]:
   - el `QShortcut` de aplicación no dispara con un modal de aplicación abierto, y un filtro en
     `QApplication` sí;
   - dos registros de `Ctrl+E` dan `activatedAmbiguously` y ninguno dispara;
   - un filtro único dispara una vez por pulsación y anula la ambigüedad.

   El filtro de PySpectrum (`window.py:87-160`) **no ve las teclas de la ventana satélite de
   PyPrinting** (es su propia ventana: `window()` la devuelve a ella misma, [MEDIDO]), pero **sí** las
   de un modal del satélite, que suben por la cadena de padres hasta PySpectrum. Esa E-STOP de
   PySpectrum, además, **no activa ningún interlock**: la grilla del satélite reabre en el nodo
   siguiente.
   - **Propuesta (§2):** el filtro pasa a `core/`, con alcance sobre **toda ventana del proceso** y un
     único coordinador de parada.
6. **N-4 confirmado.** Con `legacy_timer`, "Cerrar todos" durante un nodo termina por la rama de
   caída (≈ M/2 ticks, ≈ 0.5 s con 20/20) o por T_max, rotulado **"timeout"**
   (`measurements.py:2408, 2416-2418`). El Healing Pass lo **reexpone 50 s** (`:2828, :2860`).
   - **Propuesta (§3):** una **época de cierre** en `core/nidaq.py` que se incrementa al pedir el
     cierre (antes de tomar el candado).
   - `_grid_trace` la anota **antes** de abrir, y `grid_trace_detect` la compara en su primera línea,
     antes del `heartbeat_shutter()` de `:2333`.
   - El nodo queda **"interrumpido"**, que el Healing Pass no selecciona.
7. **N-3 (§4).** El autofoco (`focus.py:376-386`), la deriva sobre P0 (`confocal.py:790, 857` →
   `measurements.py:2463-2466`) y los escaneos previo y posterior abren, ignoran el `bool` de
   `open_shutter` y aplican su corrección sin validarla.
   - **Predicado primario:** la misma época, más el `bool` de la apertura.
   - **Repetición (P-a):** sin aplicar la corrección y **restituyendo `last_af_time/last_af_index`**,
     que hoy se pisan antes de correr el paso (`:2243-2244`).
   - **Topes:** adopto los de [EXP] §5 (no propongo otros números). Agrego dónde se miden en el
     código, y que el BS ya está en la lectura del autofoco pero no en el escaneo por pasos.
8. **Riesgo de tiempo (§5).** Hoy el hilo GUI ejecuta ≈ 1.2 s de esperas por nodo con autofoco
   (`grid_finish_autofoco` + `_grid_trace`), además de `grid_trace_detect` con su guardado. Mientras
   tanto **no procesa teclas**: la parada por teclado o por botón puede tardar hasta ≈ 1.2 s más
   L_mec. `TIMING_HAZARD`, que se cierra con el mismo arreglo que el punto 1.

**Veredicto:**
- **código actual: `SAFETY_VIOLATION`** (punto 1, y la E-STOP de PySpectrum que no bloquea al
  satélite);
- **propuesta de este documento: `HARDWARE_SAFE` en diseño**, condicionada a `BANCO-66` a `BANCO-69`
  y a mover el fin del autofoco fuera del hilo GUI;
- **`TIMING_HAZARD`** hasta que eso ocurra.

---

## 0. Hechos del código que condicionan todo

| # | Hecho | Evidencia |
|---|---|---|
| H1 | `_nidaq_lock` es un `RLock` único para toda escritura DO/AO y para el diccionario de interlocks | [CÓDIGO] `nidaq.py:123`, `:286`, `:293`, `:301`, `:466`, `:501`, `:537`, `:659`, `:790` |
| H2 | `open_shutter` revisa los interlocks **dentro** del candado y antes de escribir; arma el watchdog dentro del candado | [CÓDIGO] `nidaq.py:466-479` |
| H3 | `close_all_shutters`: hasta 3 escrituras con 2 × 50 ms entre ellas. Retención normal del candado ≈ 0.1 ms; en el peor caso conocido, ≈ 100 ms + 3 escrituras | [CÓDIGO] `nidaq.py:131-132, 541-546` |
| H4 | Otras retenciones: pulso del filtro 5 ms + 2 escrituras; si falla, cierra y vuelve a crear las dos tareas AO dentro del candado. Espejo: 3 ms + 2 escrituras + **reemplazo de archivo** en disco | [CÓDIGO] `nidaq.py:659-694`; `:790-812`, `:724-730` |
| H5 | `Task.write` tiene `timeout = 10.0` s por defecto. Para una DO estática por demanda probablemente no limita nada; un driver colgado puede retener el candado | [NI-DOC] `Task.write(self, data, auto_start=…, timeout=10.0)`; [INFERIDO] |
| H6 | El watchdog cierra con `close_all_shutters()`, es decir, con el mismo candado | [CÓDIGO] `nidaq.py:173-206` (`:187`) |
| H7 | Hilos: `printingWorker`, `focusWorker`, `traceWorker` y `confocalWorker` en `confocalThread`; `shuttersWorker` en `instrumentThread`. **`grid_trace_detect` (por `_dispatch_trace`) y `grid_finish_autofoco` (por el cierre `_on_autofinish`) corren en el hilo GUI** | [CÓDIGO] `app.py:724-734, 487-490, 499, 556-564`; [MEDIDO] sonda 4: "el cierre … corre en el hilo: GUI" |
| H8 | La Pausa es un slot encolado al `confocalThread` (`grid_pause`): corre recién cuando termina el slot en curso de ese hilo (un autofoco entero, por ejemplo) | [CÓDIGO] `measurements.py:1683-1684, 2936-2946` |
| H9 | Ninguna etapa de la grilla revisa `is_paused`, `mode_printing` ni otro estado al entrar | [CÓDIGO] `measurements.py:2134, 2223, 2271, 2317, 2325, 2442, 2456, 2817, 2845` |
| H10 | `open_shutter` devuelve `bool` y nadie lo mira en la ruta de impresión ni en los pasos entre nodos | [CÓDIGO] `measurements.py:2319`, `trace.py:586`, `focus.py:376`, `confocal.py:790, 873-891` |
| H11 | Doble apertura en cada nodo: `_grid_trace` abre y `trace._start` vuelve a abrir | [CÓDIGO] `measurements.py:2319`, `trace.py:586` ([R2-ARQ] §0.5) |
| H12 | La E-STOP de PySpectrum pone `_emergency_active` y cierra, pero **no** activa ningún interlock de `core/nidaq.py`. Ningún módulo de PyPrinting consulta `hardware_session` | [CÓDIGO] `hardware_session.py:150-212`; `grep is_emergency_stopped` en `modules/`, `core/`, `app.py`: sólo `core/hardware_manager.py:343` |
| H13 | Generadores de onda de la PI en un solo ciclo: terminan solos | [CÓDIGO] `focus.py:438, 443`; `confocal.py:906, 928, 941, 950`; `contrapropagante.py:637, 658` |
| H14 | Esperas acotadas más largas del `confocalThread`: `_move_z` 10 s, `wait_on_target` 5 s, `task.read` de la rampa con el timeout por defecto de DAQmx (10 s) | [CÓDIGO] `focus.py:484`, `config.py:690`; [NI-DOC] |

---

## 1. R4-17 / N-2: secuencia de la parada de emergencia de PyPrinting

### 1.1 Lo que pasa hoy

- **¿`close_all_shutters()` puede bloquear la GUI?** Sí.
  - El botón "Cerrar Todos" llama `close_all_shutters()` en el hilo GUI (`shutters.py:308-315`), sin
    mirar el `bool` que devuelve.
  - Bloquea mientras otro hilo tenga `_nidaq_lock`:
    - lo normal: < 1 ms;
    - el peor caso conocido: ≈ 100 ms (H3, un cierre ajeno reintentando);
    - un pulso del filtro: ≈ 5-10 ms (H4);
    - un cambio del espejo: lo que tarde el disco;
    - sin cota si el dueño quedó colgado.
- **Con un hilo colgado dentro de `_nidaq_lock`, no cierra nadie:**
  - el hilo GUI se congela en el botón;
  - el watchdog se cuelga en su propio cierre (H6) y deja de vigilar;
  - el excepthook y el `atexit` (`nidaq.py:328-335`) esperan igual;
  - la E-STOP de PySpectrum se congela con el candado de sesión tomado, y arrastra a todo hilo que
    consulte `hardware_session.is_busy` o `current_owner`;
  - activar un interlock tampoco es posible, porque `set_shutter_interlock` toma el mismo candado
    (`nidaq.py:286`; [DA] F-4).
- **El orden de `gui_design_v2.md` §5.1 (cerrar y después el interlock) tiene una carrera**, como
  señala [DA] §0-1: una rutina puede reabrir entre los dos pasos. El orden seguro ya existe en
  `trip_shutter_interlock` (`nidaq.py:305-308`): primero el interlock, después el cierre.

### 1.2 Secuencia propuesta

| Paso | Qué | Hilo | Candado | Plazo |
|---|---|---|---|---|
| 0 | El filtro de `QApplication` o el botón llama `EmergencyCoordinator.trigger(fuente)` (§2) | GUI | ninguno | vuelve en < 1 ms, sin `exec()` ni diálogos |
| 1 | `nidaq.request_emergency_stop(fuente)`: pone `_estop_event` (`threading.Event`), incrementa `_estop_generation` y la **época de cierre** (§3), anota la hora y despierta al hilo cerrador | GUI | **ninguno** (asignaciones atómicas y un `Condition` propio, nunca `_nidaq_lock`) | < 1 ms |
| 2 | Desde ese instante, `open_shutter` **rechaza sin escribir**: revisa `_estop_event` antes de pedir el candado (rechazo inmediato) y otra vez adentro, junto a los interlocks. Una apertura que ya tenía el candado termina, y el cerrador la deshace enseguida | cualquiera | — | — |
| 3 | Pedir el alto a las rutinas con banderas seguras entre hilos, **sin depender de slots encolados** (§1.5): `printingWorker` y `dimersWorker.request_stop("estop")`, el predicado de aborto de la traza, `focus.abort_requested`, `confocal.signal_scan_stop = True` | GUI | ninguno | < 1 ms |
| 4 | Banner rojo no modal: "PARADA DE EMERGENCIA — cerrando…" | GUI | — | — |
| 5 | **Hilo cerrador** (`EStopCloser`, uno por proceso, de larga vida): `_nidaq_lock.acquire(timeout = ESTOP_LOCK_TIMEOUT_S)`. Con el candado: `_shutter_interlocks["E-STOP"] = …` y después el cierre de las cuatro líneas, cada una con su polaridad (el 532 nm en ALTO), con los 3 intentos de hoy. Suelta el candado y avisa el resultado **de su propia escritura**, sellado con `_estop_generation` | cerrador | `_nidaq_lock` con plazo | ≤ 0.25 s para el primer aviso (§1.3) |
| 6 | Si no consigue el candado: aviso "placa tomada por otro hilo" (una vez por episodio) y **sigue intentando** cada 0.25 s mientras la parada esté activa. Nunca se rinde | cerrador | ídem | — |
| 7 | Con el cierre confirmado: `up_flipper()` (filtro de densidad en baja potencia), como hacen `_emergency_shutdown` (`nidaq.py:330-331`) y `grid_pause` (`measurements.py:2940`). Una falla se informa pero no cambia el resultado de la parada (pregunta Q-E) | cerrador | `_nidaq_lock` | ≤ 10 ms |
| 8 | **No se toca:** el espejo de detección (es un conmutador de posición desconocida, C-08: un pulso en una emergencia lo desincroniza más), la modulación del 532 en `ao2` (no baja de 1.0 V, `lab-invariants` §2) ni la platina (§1.4) | — | — | — |
| 9 | Banner final, a partir del resultado sellado del paso 5: "obturadores: 4 de 4 cerrados (escritura confirmada 14:31:52.214)", o "**NO confirmado**: …" | GUI (por señal) | — | — |

- **"Confirmado" es el `ok` de la escritura del paso 5**, posterior a la parada. No es
  `_all_closed_confirmed()`, que puede dar verdadero sin ninguna escritura exitosa si el software no
  creía nada abierto ([DA] §0-4, F-5).
- `request_close_all(causa)`, para "Cerrar todos", es la misma maquinaria **sin** `_estop_event` y
  **sin** interlock: no bloquea la GUI y deja la época de cierre incrementada.
- **API propuesta para la Ronda 2** (en `core/nidaq.py`, sin Qt):

```text
ESTOP_INTERLOCK = "E-STOP"
ESTOP_LOCK_TIMEOUT_S = 0.25                 # se fija con BANCO-68
request_emergency_stop(source: str) -> int  # no bloquea; devuelve la generación
request_close_all(cause: str) -> int        # no bloquea; devuelve la época de cierre
get_close_epoch() -> tuple[int, str]        # (época, causa del último cierre total pedido)
get_emergency_state() -> EStopState         # activa, generación, hora, cierre confirmado (sellado), último error
clear_emergency_stop(generation: int) -> bool  # rearme (§1.6)
register_emergency_callback(fn)             # el cerrador avisa por acá; los puentes Qt sólo emiten señales
```

### 1.3 Plazos

| Plazo | Valor | Por qué |
|---|---|---|
| `ESTOP_LOCK_TIMEOUT_S` | **0.25 s** (provisorio) | ≥ 2 veces la mayor retención normal conocida (≈ 0.1 s, H3). Con 0.2 s (N-2) el margen sobre un cierre ajeno en reintento es justo. `BANCO-68` lo fija como ≥ 2 × la máxima retención observada |
| Reintento del cerrador | cada 0.25 s, sin límite mientras la parada esté activa | el watchdog reintenta cada 1.0 s (`WATCHDOG_RETRY_INTERVAL_S`), pero acá hay un operador esperando el banner |
| Latencia tecla → línea DO, con la GUI libre | ≤ 1 ms (filtro) + despertar del hilo (≤ 5 ms, intervalo de conmutación del GIL) + L_lock (0 típico, ≤ 100 ms) + < 1 ms de escritura, más L_mec (`BANCO-30`) | [INFERIDO]; se mide en `BANCO-66` |
| Latencia con la GUI ocupada, **hoy** | + hasta ≈ 1.2 s | H7: esperas de `grid_finish_autofoco` y `_grid_trace` en el hilo GUI (`measurements.py:2272, 2310-2311, 2318`), más `_save_trace` y HDF5 en `grid_trace_detect` (`:2420`, `:2981-2994`). Ver §5.1 |

### 1.4 ¿Comandos a la platina PI (`HLT`/`STP`)? No: sólo dejar de emitir movimientos

1. **Con los cuatro obturadores cerrados, un movimiento del piezo no es un riesgo óptico ni para la
   muestra.**
   - Todo `MOV` está acotado por eje en el driver (`config.py`, `_PIController.MOV`, `clamp_axis_um`).
   - Un `MOV` que ya salió es corto (ms a decenas de ms).
   - Los generadores de onda terminan solos en un ciclo (H13).
2. **`STP` desde la parada choca con `DEC-036`.**
   - **Bloquearía.** El envoltorio toma el `RLock` de clase de `_PIController` (`config.py:381`;
     `__getattr__` → `_locked_call`), que `connect()` retiene durante la espera del home
     (`config.py:471-474`, ≥ 3 s) y cualquier lectura o espera en curso. La parada no puede esperar
     eso.
   - **Sin ese candado, desordenaría el USB.** Un `STP` intercalado con una lectura en curso puede
     producir `−1004` (`PI_UNEXPECTED_RESPONSE`). `_is_stage_comm_error` lo clasifica como falla de
     comunicación (código negativo) → `_stage_fault` → interlock `"Platina PI"` → sólo el operador
     reconecta → `connect()` manda la platina a home.
   - Es decir: la parada **fabricaría** justo el evento que `DEC-036` quiere evitar ("no re-homing ni
     reconexión automática"), y el rearme exigiría una reconexión con home.
   - **Deja estado.** `STP` deja el código de error 10 en el controlador y el eje en una posición
     intermedia. Lo primero es inocuo para el clasificador (código positivo); lo segundo obliga a
     releer la posición antes de retomar.
3. **Lo que sí hace falta: guardas.** Ninguna entrada de la máquina de estados puede emitir un `MOV`
   después de la parada (§1.5).
   - El confocal manual, al abortar por la parada, no vuelve a la posición inicial. Hoy `stop_scan`
     lo hace con `mode_printing == "none"` (`confocal.py:768-769`); la parada usa un camino como
     `_abort_scan_on_stage_fault` (`confocal.py:985-995`), sin movimiento de retorno.
   - Ni la parada ni el rearme llaman `pi.connect()` o `disconnect()`.

### 1.5 Que la grilla deje de avanzar: una guarda en cada entrada

[MEDIDO] caso B: con sólo "interlock + cierre", `grid_finish_autofoco` emite un `MOV` y arranca la
traza en modo `"printing"` sobre oscuridad. La cadena sigue nodo tras nodo, rotulando "timeout"
(confirma [DA] §0-2).

- **Bandera propia del worker:** `request_stop(reason)` asigna `self._stop_reason` y un
  `threading.Event`. Es una asignación atómica, llamada **directamente** desde el hilo GUI, no por
  una señal encolada (H8).
- **`_entry_ok(etapa)`** se consulta en la primera línea de las entradas siguientes:
  - `_grid_move` (`:2134`), `grid_autofoco` (`:2223`), `grid_finish_autofoco` (`:2271`) y
    `_grid_trace` (`:2317`);
  - `grid_trace_detect` (`:2325`), `grid_scan` (`:2442`), `on_scan_finished` (`:2456`) y
    `grid_finish` (`:2552`);
  - `_grid_detect` (`:2817`), `_advance_healing_pass` (`:2845`) y `grid_next_index` (`:2949`).
- **Si la guarda corta:** la etapa deja el nodo como corresponde ("expuesto sin decisión" si hubo
  `t_open`; si no, pendiente), marca `self._idle_ack.set()` y vuelve sin emitir nada.
- **`focus_autocorr_lin_x2`:** un predicado inyectado que se consulta entre las dos iteraciones y
  **antes** de `_move_z(z_gone[i_max])` (`focus.py:379-381, 423`). Con la parada, no se aplica la
  corrección.
- **Traza `legacy_timer`:** `_trace_update` revisa el predicado al principio (`trace.py:641`) y, si
  corresponde, detiene su `QTimer` sin latir.
- **La misma guarda sirve para la Pausa**, y arregla el hallazgo 1 (§1.6).
- **El índice de reanudación** lo define el contrato de [DA] §4: se calcula desde `node_results` y
  `t_open_s`, nunca desde `i_global`. No lo repito.

### 1.6 Hallazgo: la Pausa durante el autofoco reabre a alta potencia, sin detección

**Secuencia** (H7 + H8), [MEDIDO] caso A:
1. El autofoco termina en `confocalThread` y emite `autofinishSignal` (`focus.py:395`), que va
   encolada al hilo GUI por el cierre `_on_autofinish` (`app.py:487-490`).
2. `confocalThread` saca de su cola la Pausa: `grid_pause` cierra, detiene la traza, sube el filtro y
   pone `is_paused = True` y `mode_printing = "none"` (`measurements.py:2936-2946`).
3. El hilo GUI ejecuta `grid_finish_autofoco`:
   - `sleep(0.1)` (`:2272`);
   - `MOV` (`:2309`);
   - `down_flipper()`, es decir alta potencia (`:2311`);
   - `_grid_trace()`: otro `down_flipper()` y `open_shutter(self.laser)` (`:2318-2319`), que **abre**
     porque la Pausa no pone interlock;
   - `grid_traceSignal.emit(laser, "none")` (`:2322`).
4. `trace_configuration(laser, "none")` → `_start` vuelve a abrir, llama `heartbeat_shutter(30.0)` y
   arranca el `QTimer` (`trace.py:580-603`).
5. Con modo `"none"` no hay `data_printingSignal` (`trace.py:738-740`) ni `grid_trace_detect`: no hay
   criterio ni cierre.
6. `_trace_update` renueva el plazo de 30 s cada 30 ticks (`trace.py:643-644`): **el watchdog no
   vence**.

Resultado de la sonda:

> A pausa durante AF: is_paused = True | mode_printing grid = none | traza mode = none |
> QTimer traza activo = True | abiertos = ['532 nm (green)'] | deadline (s) = 30.0 |
> flipper alta potencia = True

**Consecuencias:**
- el 532 queda abierto a **alta potencia** sobre el nodo siguiente, que no se imprimió, sin
  detección, hasta que el operador lo note;
- el botón del 532 en el dock se ve cerrado (N-6);
- es la receta de una partícula múltiple o de un nodo sobrecalentado.

**Comparación con el legado y arreglo:**
- el legado conectaba `autofinishSignal` al slot del worker (`PyPrinting_UNSAM.py:418`), así que no
  tenía esta carrera;
- **arreglo mínimo:** volver a esa topología (un slot del worker en `confocalThread`) y agregar la
  guarda de §1.5 al principio de `grid_finish_autofoco` y de `_grid_trace`;
- abre un obturador: no es exento aunque parta de un test que falla (`CLAUDE.md` §5.0). Pregunta Q-B.

### 1.7 Rearmar

**Condiciones** (las cuatro; "Rearmar" queda deshabilitado mientras falte alguna):
1. existe un resultado del cerrador **con la generación vigente** y `ok = True`, y además
   `get_open_shutter_names() == []` y `get_unconfirmed_shutters() == []`;
2. todas las rutinas de PyPrinting confirmaron que están quietas (`_idle_ack`): grilla y dímeros,
   foco y confocal fuera de un paso, `QTimer` de la traza detenido;
3. no hubo una parada nueva desde que se pulsó Rearmar: `clear_emergency_stop(gen)` falla si
   `_estop_generation != gen`;
4. el candado se consigue dentro de `ESTOP_LOCK_TIMEOUT_S`. Si no, se rechaza el rearme y se informa.

**Plazo para la confirmación de las rutinas: 12 s.**
- Es la espera acotada más larga que puede estar en curso en `confocalThread` (H14: `_move_z` 10 s,
  `task.read` 10 s), más un margen.
- Mientras tanto: "esperando que termine el paso en curso (autofoco, ≤ 12 s)".
- Si vence: "La rutina no respondió en 12 s. Los obturadores están confirmados cerrados; la parada
  sigue. Guardá los datos y reiniciá PyPrinting." No se rearma.

**Qué hace `clear_emergency_stop(gen)`:**
- bajo `_nidaq_lock` (con plazo), quita `"E-STOP"` de `_shutter_interlocks` y limpia `_estop_event`;
- en modo satélite, el coordinador llama también `hardware_session.clear_emergency()`. Hoy ese método
  no verifica nada (`hardware_session.py:74-79`);
- la grilla pasa de DETENIDA a EN PAUSA; Play es una acción aparte (`gui_design_v2.md` §5.1).

### 1.8 Remedio cuando el software no puede cerrar

- **El banner con el candado tomado o el cierre sin confirmar** dice: "Cortá la emisión con la llave
  del láser (o el interlock de emisión) y reiniciá PyPrinting".
- **"Reiniciá" sólo no alcanza.** Si el proceso muere, las líneas quedan en su último valor. Si la
  placa se reinicia, quedan sin manejar y caen a BAJO por el pull-down: el 532 queda **abierto**
  (`BANCO-16`).
- **No propongo una escritura sin candado como plan B** (Q-A):
  - si el dueño colgado está dentro del driver, otra escritura sobre la misma tarea probablemente
    también se traba [INFERIDO];
  - si no está en el driver, se cruza con una apertura en curso, que puede volver a abrir después.
- **La protección real ante un proceso o un driver colgado es de hardware.** Es el `WatchdogTask` de
  la placa ([R2-INS] §6.1-2, fase 6.2), o un corte físico. Queda registrado, no se afirma.

---

## 2. N-1 y Q-5: el disparo por teclado

### 2.1 Verificación

`qa_modal_shortcut.py` (de la sesión de qa-ux) está en el scratchpad de la sesión. Lo reproduje y
lo amplié en `ins_estop_probe.py` [MEDIDO]:

| Caso | Resultado |
|---|---|
| 1a. `QShortcut(F12)` con `ApplicationShortcut` en la principal; tecla en otra ventana, sin modal | dispara (1) |
| 1b. Con un `QMessageBox` modal de aplicación (`exec()`) abierto, sin filtro; `F12` y `Ctrl+E` | **no dispara** (0) |
| 1c. Ídem, con un filtro en `QApplication` que atiende `ShortcutOverride` / `KeyPress` | el filtro dispara **2 de 2** |
| 2. `Ctrl+E` de ventana en A (PySpectrum) y de aplicación en B (PyPrinting); foco en A | `activatedAmbiguously` en A; **ninguno dispara** |
| 3. Mismo escenario, con un filtro único | **1 disparo por pulsación** (2 de 2), ningún atajo ambiguo |

**Límite de la verificación:** las sondas usan diálogos de Qt en `offscreen`. Un `QFileDialog`
**nativo** de Windows corre su propio bucle Win32 y puede no pasar por el filtro ([DA] F-1). Va a
`BANCO-66`.

### 2.2 Cómo lo hace PySpectrum y por qué no alcanza para el satélite

- **Diseño** (`window.py:87-160`): un único filtro por proceso, instalado en `QApplication`. Consume
  el `ShortcutOverride` y el `KeyPress` siguiente (una pulsación, una E-STOP) y actúa sólo sobre
  ventanas **registradas** o sobre un `QDialog` modal cuya cadena de padres llega a una de ellas
  (`_owner_trigger`, `:123-142`).
- **Con el satélite, los dos lados fallan distinto:**
  - **Teclas en la ventana satélite: no dispara.** El satélite se crea con `parent = PySpectrumWindow`
    (`window.py:959`), pero un `QMainWindow` es siempre ventana. [MEDIDO]: `B.window() is B` → `True`,
    y lo mismo para cualquier hijo. `_owner_trigger` no lo encuentra registrado, y como no es un
    `QDialog` no sube por los padres.
  - **Teclas en un modal del satélite: dispara la E-STOP de PySpectrum**, porque la cadena
    diálogo → satélite → PySpectrum llega a una ventana registrada.
- Y esa E-STOP **no activa ningún interlock** (H12): la grilla del satélite sigue y reabre en el
  nodo siguiente.
- **Además, la acción de PySpectrum bloquea:**
  - `_on_emergency_stop_clicked` abre un `QMessageBox.critical` modal **desde dentro del filtro**
    (`window.py:474`): un bucle de eventos anidado en plena emergencia;
  - `emergency_stop()` llama a la cámara Andor (abortar y ganancia EM, con relectura) en el hilo GUI
    y con el candado de sesión tomado (`hardware_session.py:167-190`).

### 2.3 Propuesta: un filtro y un coordinador por proceso

- **El filtro pasa a `core/`** (por ejemplo `core/emergency_keys.py`, sin dependencias de
  `pyspectrum/`). Alcance: **toda ventana del proceso**, sin registro por ventana. Así una ventana
  nueva no queda afuera en silencio ([DA] F-2). Conserva la lógica de una pulsación por disparo de
  `window.py:144-160`.
- **`EmergencyCoordinator`** (`core/`, un `QObject` por proceso):
  - `trigger()` hace los pasos 1 y 2 de §1.2 una sola vez y después llama, sin bloquear, a los
    participantes registrados;
  - participantes: PyPrinting (grilla, dímeros, traza, foco y confocal) y, en el satélite, PySpectrum;
  - `hardware_session.emergency_stop` queda como participante sin la parte de obturadores (o con ella
    idempotente). La parte de la cámara va a un hilo propio, **después** del cierre;
  - un único **Rearmar** para los dos programas (§1.7), que reemplaza el `clear_emergency` sin
    condiciones.
- **Instalación:**
  - PyPrinting suelto crea su coordinador en `app.py` (`__main__`);
  - en el satélite lo crea PySpectrum y `create_app_satellite(..., host=…)` registra a PyPrinting;
  - se quitan los `QShortcut` de `Ctrl+E` / `F12` de `window.py:693-696`. Con el filtro ya no
    disparan, pero son el registro doble que produce la ambigüedad si el filtro falta.
- **Disparo:** sin `exec()` ni diálogos modales. Banner.
- **Tests (`SAFE_MODE`):**
  - `Ctrl+E` y `F12` desde cada ventana de nivel superior (`QApplication.topLevelWidgets()`) y desde
    un `QMessageBox` y un `QFileDialog` (no nativo) abiertos → un disparo por pulsación;
  - después de la parada, `open_shutter` desde una rutina de PyPrinting devuelve `False`;
  - tres pulsaciones seguidas → un solo episodio ([DA] F-8).

---

## 3. "Cerrar todos · la grilla sigue" (P-H) y N-4 con `legacy_timer`

### 3.1 Lo que pasa hoy

- **El botón** (`shutters.py:308-315`) desmarca los botones y llama `close_all_shutters()` en el hilo
  GUI. No avisa a ninguna rutina.
- **`grid_trace_detect`** (hilo GUI, H7) no tiene forma de enterarse. En cada tick:
  - llama `heartbeat_shutter()` (`:2333`) y vuelve a armar el plazo aunque no quede nada abierto;
  - evalúa el criterio sobre una señal que cae a oscuridad.
- **El nodo termina por una de dos ramas:**
  - **la de caída**, `I_new < I_old·umbral_down` con `umbral_down = 0.5` (`:2408`). Con I_new = media
    de los últimos M ticks e I_old la de los M2 anteriores, dispara cuando más de la mitad de la
    ventana nueva está a oscuras: ≈ M/2 ticks, es decir ≈ 0.5 s con 20/20 a ≈ 47 ms/tick, o ≈ 0.24 s
    con 10/10 [DERIVADO, con oscuridad ≈ 0 V];
  - **T_max** (40 s; 50 s en el Healing Pass) si el nivel oscuro queda por encima de 0.5·I_old (fondo
    alto o señal débil) o si `umbral_down = 0`.
- **En los dos casos queda `node_results = "timeout"`** (`:2416-2418`). `_save_trace` escribe
  "TIMEOUT (Primary Pass…)", con la cola oscura dentro (`:2976-2981`).
- **El Healing Pass selecciona `status == "timeout"`** (`:2828`) y lo **reexpone** con T_max + 10 s
  (`:2860`), que es lo que prohíbe P4.
- **Un hueco más** ([DA] §0-5): un cierre que cae entre la apertura de `_grid_trace` (`:2319`) y la de
  `trace._start` (`trace.py:586`) se deshace con la segunda apertura (H11).

### 3.2 Mecanismo mínimo: la época de cierre

**En `core/nidaq.py`:**
- un entero `_close_epoch` y la causa del último pedido;
- `request_close_all(causa)`, `request_emergency_stop`, `close_all_shutters(cause=…)` (watchdog,
  interlocks, excepthook, `atexit`, `_move_z`, confocal) y `trip_shutter_interlock` lo incrementan
  **al pedir el cierre, antes de tomar el candado**. Así el consumidor ve la interrupción aunque el
  cerrador siga esperando;
- se lee con `get_close_epoch()`.

**Por qué una época y no una bandera:**
- es monótona y no hay que "limpiarla", así que no tiene dueño ni carreras de reinicio;
- cada consumidor (un nodo, un autofoco, un escaneo de deriva) compara contra el valor que anotó, de
  modo que sirve igual para el nodo (N-4) y para los pasos entre nodos (N-3);
- distingue la causa: el operador (la grilla sigue) de la parada, el watchdog y los interlocks (la
  grilla se detiene o se pausa, `gui_design_v2.md` §5.3).

**Dónde se anota y dónde se consulta** (`legacy_timer`, que es el camino de `DEC-037` más estas
guardas):

| Lugar | Qué |
|---|---|
| `_grid_trace`, `measurements.py:2317-2322` | `self._node_epoch = get_close_epoch()[0]` **antes** de `open_shutter` (`:2319`). Si un cierre cae entre la anotación y la apertura, el nodo queda interrumpido y se cierra en el tick siguiente: es el lado seguro. Se mira el `bool` de la apertura: `False` → nodo "apertura rechazada", sin exponer |
| `trace._start`, `trace.py:585-588` | con `mode_printing != "none"`, **no vuelve a abrir**: la apertura es de la grilla (quita H11 y el hueco de [DA] §0-5) |
| `grid_trace_detect`, **primera línea**, antes del `heartbeat_shutter()` de `:2333` | guarda de reentrada `_node_decided` ([R2-ARQ] §2.4-4). Después: `epoch, causa = get_close_epoch()`; si `epoch != self._node_epoch`, el nodo termina **interrumpido**: no late, `grid_trace_stopSignal.emit()`, `node_results[i] = "interrupted"` (en pantalla, "expuesto sin decisión (cierre del operador)"), `t_exp = elapsed`, `_save_trace` con el encabezado `INTERRUPTED (causa, t_exp = 12.3 s)` |
| Continuación | causa "operador": `grid_detectSignal.emit()` **después** de la espera visible de 3 s ([INV9] P-b), con un `QTimer.singleShot` en el mismo hilo que se cancela si llega una Pausa o una parada. La época se vuelve a mirar al terminar la espera. Cualquier otra causa: no se emite nada; queda EN PAUSA o DETENIDA según §5.3 |
| `_grid_detect`, `:2828` | sin cambio: sigue seleccionando sólo `"timeout"`. `"interrupted"` queda afuera y pasa a la cola "en revisión" (P4) |

- **Ventaja de que todo corra en el hilo GUI:** con `legacy_timer`, el botón y `grid_trace_detect`
  están en el mismo hilo, así que el cierre se ve en el tick siguiente (≤ ≈ 47 ms) sin carreras.
  Con el backend de bloques, la misma época se consulta entre bloques ([R2-ARQ] §2.3).
- **El latido:** la consulta va antes del `heartbeat_shutter()` de `:2333`. Un nodo interrumpido no
  vuelve a armar el plazo.

---

## 4. N-3: pasos entre nodos que abren obturadores

### 4.1 Inventario

| Paso | Abre | Cierra | Corrección que aplica | Validación hoy |
|---|---|---|---|---|
| Autofoco (`focus_autocorr_lin_x2`), en cada nodo de autofoco (`measurements.py:2223-2265`) | `focus.py:376`, sin mirar el `bool`. Si no había lock, también `focus_lock_lin` (`:325-330`) | `:386` (en `finally`) | `_move_z(z_gone[i_max])` (`:423`): Z sigue al `argmax` de la correlación, hasta ±3 µm (rampa de 6 µm, `:205`) | ninguna |
| Deriva sobre P0 (`drift_scan`), con `driftbool` (`:2296-2303`) | `confocal.py:790` (por pasos) u `:873-891` (rampas), sin mirar el `bool` | `:857`, `:1040` | `startX/startY ← centro de masa` (`measurements.py:2463-2466`), para todos los nodos siguientes. El centro sale de una imagen normalizada por min-max (`confocal.py:1169-1185`), así que la amplitud absoluta se pierde | ninguna |
| Escaneo posterior (`grid_scan`, `scanbool`, `:2442-2446`) | ídem confocal | ídem | `_grid_printing_error(center_mass)` (`:2519`): registra el error de impresión | ninguna |
| Dímeros: `center_scan` y `pree_scan` (`:2523-2544`) | ídem | ídem | `MOV` al centro + (dx, dy) e imprime ahí | ninguna (fuera del rediseño, [INV7] P-K, pero el mecanismo es el mismo) |
| Muestreo de inclinación (`_measure_4_corners_tilt`), si está activa | `confocal.py:546` | `:571` | plano de Z | ninguna |

**Qué pasa hoy con un cierre durante uno de ellos:**
- el paso sigue leyendo oscuridad y aplica la corrección sin aviso (como dice N-3);
- en el autofoco, el `argmax` de la correlación del ruido mueve Z hasta ±3 µm ([EXP] §5.2);
- en la deriva, el centro de masa del ruido umbralizado reemplaza `startX/startY`;
- además, `grid_autofoco` anota `last_af_time = now` y `last_af_index = i_global` **antes** de
  correr el autofoco (`:2243-2244`). Un autofoco que no sirvió cuenta igual como hecho, y el disparo
  por conteo o por tiempo no lo repite.

### 4.2 Invalidar y repetir (P-a)

**Al empezar el paso:**
- anotar `epoch0 = get_close_epoch()[0]` **antes** de abrir;
- mirar el `bool` de `open_shutter`: `False` invalida el paso.

**Al terminar, antes de aplicar la corrección:**

| Momento | Línea | Qué |
|---|---|---|
| Autofoco, entre las dos iteraciones y antes de cada `_move_z(z_gone[i_max])` | `focus.py:379-381, 423` | si cambió la época, la apertura falló o el BS de la rampa dice oscuridad (§4.3): no se mueve Z; se vuelve a `z_before`; se emite `autofinishSignal(mode, valid=False)` |
| Fin del autofoco en la grilla | `measurements.py:2271-2292` | si `valid=False`: no se anota en `drift_history_z`; se restituyen `last_af_time` y `last_af_index` a sus valores anteriores; la etapa vuelve a "pendiente de autofoco" |
| Deriva | `measurements.py:2462-2487` | si cambió la época desde la anotación del escaneo, o no pasa los topes: no se toca `startX/startY`, no se agrega a `drift_history_xy`, no se llama `_update_drift_velocity` (con un centro absurdo da v enorme y N_eff = 1, `:2194-2205`) |

**Repetición:**
- causa "operador": el paso se repite antes de imprimir, después de la espera visible de 3 s (P-b),
  con el banner de N-3: "Cerraste los obturadores durante el autofoco del nodo 18: se repite antes
  de imprimir";
- causa parada, watchdog o interlock: no se repite; queda pendiente y se hace primero al reanudar;
- **regla general:** toda reapertura automática después de un cierre del operador espera 3 s
  visibles, sea un nodo (§3.2) o un paso.

**Tope de repeticiones:** dos cierres del operador seguidos sobre el mismo paso o el mismo nodo
pausan la grilla (pregunta Q-C). Sin ese tope, un operador que cierra cada vez que ve algo raro y una
grilla que reabre cada 3 s forman un ciclo.

### 4.3 Topes de plausibilidad

**No propongo números distintos de [EXP] §5.** El panel experimental ya armó la tabla (T1-T6 para la
deriva, F1-F5 para el autofoco) con sus fuentes. Sus valores y los insumos que los respaldan:

| Valor | Respaldo |
|---|---|
| Paso de la deriva: ≤ 50 nm + 2 nm/s·Δt por eje, con techo de 500 nm | deriva de 30 nm/min, con caso peor de 0.5 nm/s por eje (`lab-invariants` §6, fila "Deriva mecánica en XY", [M24], [INV2] R2-13; rango publicado 5-50 nm/min) |
| Acumulado de la deriva: ≤ 3 µm | `drift_margin = 3.0` del pre-flight (`measurements.py:1989`). Es el único tope que está en el código: más allá, la grilla puede salirse del recorrido que se verificó antes de empezar |
| Paso del autofoco: ≤ 100 nm + 2 nm/s·Δt, con techo de 300 nm | sin dato de deriva en Z: **SIN FUENTE**. `lab-invariants` sólo tiene XY |

**Coincido con [EXP]:** **el tope de distancia solo no alcanza**. El centro de masa de una imagen
oscura normalizada cae cerca del centro del escaneo y pasa cualquier tope razonable. Por eso los
predicados primarios son la época y la apertura (deterministas, sin umbrales). Los topes son una
segunda barrera.

**Lo que agrega instrumentación:**
- **El BS ya está en la lectura del autofoco.** `_ramp_lin` lee los cinco canales de `PD_CHANS_LIST`
  más el trigger (`focus.py:431, 445-449`), y el BS (`ai6`) está ahí. Ve la luz después del
  obturador y del filtro, no del espejo ([INV9] P-c). El chequeo F1 de [EXP] no necesita ninguna
  lectura nueva: es la media del BS sobre el tramo `first_asc:first_dsc` de la rampa.
- **En el escaneo por pasos, el BS se lee y se descarta.** `raw` trae todas las filas, pero sólo se
  guarda la del láser (`confocal.py:819-820`). T1 exige guardar también la del BS por píxel (otra
  matriz del tamaño de la imagen). En las rampas (`confocal.py:938-955`) pasa lo mismo.
- **La correlación del autofoco** usa `np.correlate(…, "same")` (`focus.py:417`). Con un retardo L,
  el solapamiento de los perfiles es (N − |L|)/N: en el borde de la rampa se compara medio perfil con
  medio perfil. El tope F5 de [EXP] (argmax fuera del 10 % extremo) es coherente con eso
  [DERIVADO].
- **A baja potencia, el BS puede no tener señal suficiente.** El autofoco y la deriva corren con el
  filtro arriba (`measurements.py:2252, 2263, 2300, 2501`), así que T1/F1 sólo valen si el BS a baja
  potencia queda bien por encima de su nivel oscuro. Se mide en `BANCO-69`, junto con el `BANCO-65`
  de [EXP].

---

## 5. Riesgos de tiempo

### 5.1 El hilo GUI ocupado retrasa la parada

- **Hoy el hilo GUI ejecuta, por nodo con autofoco** (H7):
  - en `grid_finish_autofoco`: `sleep(0.1)`, `qPOS` y `MOV` por USB, `up_flipper` o `down_flipper`
    con `sleep(0.5)` (`:2272-2311`);
  - en `_grid_trace`: `down_flipper` con `sleep(0.5)` y la apertura (`:2318-2319`).
- Suman ≈ 1.2 s sin procesar eventos. En la rama de deriva, ≈ 0.7 s.
- **Con cada decisión,** `grid_trace_detect` escribe el archivo y el HDF5 en el mismo hilo
  (`:2420`, `:2981-2994`).
- **Mientras dura cualquiera de las dos cosas,** ni el filtro, ni el botón, ni "Cerrar todos"
  disparan: se ejecutan después.
- **Arreglo:** el mismo de §1.6 (fin del autofoco en un slot del worker en `confocalThread`). Además,
  [DA] F-3 propone un `QTimer` que mida el atraso del hilo GUI durante una grilla; lo apoyo y lo sumo
  a `BANCO-66`.

### 5.2 El latido durante la parada y el rearme

- **Hoy, después de un cierre total confirmado, `_watchdog_deadline = None`** (`nidaq.py:549-551`).
  Pero los latidos que siguen llegando lo vuelven a armar:
  - el `QTimer` de la traza (`trace.py:589, 643-644`) y `grid_trace_detect` (`:2333`), hasta que se
    detienen;
  - `ShuttersBackend.set_autoclose_timeout` (`shutters.py:514`).
- **Por qué importa aunque no haya nada abierto:**
  - el vencimiento llama `close_all_shutters()` otra vez, que es inocuo e idempotente pero toma el
    candado;
  - y dispara los callbacks del watchdog: el dock muestra "watchdog" y, con §6.6 de la v2, un banner
    de "Corte de seguridad" **después** de una parada, que confunde.
- **Propuesta:**
  - `heartbeat_shutter()` no hace nada mientras `_estop_event` esté puesto;
  - después del rearme, el plazo queda en `None` hasta la próxima apertura, que lo arma
    (`nidaq.py:479`).
  - Toca la política del watchdog: nunca exento, y entra en esta deliberación.
- **Durante el rearme:** no hay nada abierto ni latidos legítimos. Play recorre el camino normal y la
  primera apertura arma el plazo.

### 5.3 La parada en medio de un `open_shutter`

| Momento de la parada | Qué pasa con la propuesta |
|---|---|
| Antes de que `open_shutter` pida el candado | rechazo inmediato por `_estop_event` (revisado antes del candado); devuelve `False` |
| Con `open_shutter` esperando el candado | al entrar ve `_estop_event` (revisado otra vez adentro): no escribe |
| Con `open_shutter` adentro, escribiendo | termina su escritura (< 1 ms) y suelta. El cerrador estaba esperando: escribe el cierre enseguida. Luz durante ≈ L_lock + < 1 ms + la mecánica. La rutina recibe `True`, pero su guarda de §1.5 la detiene en la entrada siguiente |
| Entre `down_flipper()` y `open_shutter` en `_grid_trace` | la apertura se rechaza; la guarda de `_grid_trace` (o el `bool`) deja el nodo pendiente, sin exponer |
| Con un cierre ajeno reintentando (≤ 100 ms) | el cerrador espera hasta 0.25 s; si no alcanza, avisa "placa tomada" y sigue intentando |

### 5.4 Reentrada

| Caso | Qué pasa con la propuesta |
|---|---|
| Parada pulsada varias veces | `request_emergency_stop` es idempotente: incrementa la generación y la época, y el cerrador ya despierto junta los pedidos. Un solo episodio; el banner conserva la hora de la primera |
| Parada mientras se rearma | `clear_emergency_stop(gen)` falla si cambió la generación: no se rearma |
| Parada de PySpectrum y de PyPrinting a la vez (satélite) | un solo coordinador, un solo episodio |
| Watchdog, excepthook o `_stage_fault` cerrando a la vez | se serializan en `_nidaq_lock`; todos escriben "cerrar", que es idempotente; la época sube por cada uno |
| "Cerrar todos" durante la parada | sólo incrementa la época; el interlock sigue |
| Señales viejas encoladas (`grid_detectSignal` del hilo GUI a `confocalThread`, `autofinishSignal`) que llegan después de la parada | las corta la guarda de entrada (§1.5). Sin la guarda, mueven la platina ([DA] §0-2, [MEDIDO] caso B) |
| Un callback de UI dentro del candado | no puede pasar: `_dispatch_shutter_notes` se llama fuera (`nidaq.py:267-268`). El cerrador avisa también fuera del candado |
| Orden de candados | `_PIController._lock` → `_nidaq_lock` (`_stage_fault`, `connect`, `disconnect`); no encontré el orden inverso. El cerrador sólo toma `_nidaq_lock`: no hay abrazo mortal |

---

## 6. Qué queda para el banco

`BANCO-65` es de [EXP] (confirmación a baja potencia y topes). Propongo `BANCO-66` a `BANCO-69`; la
consolidación decide la numeración final. Todos se hacen **con los láseres apagados**, salvo
`BANCO-69`.

| ID | Qué valida | Procedimiento | Aceptación |
|---|---|---|---|
| **BANCO-66** | La parada de emergencia de PyPrinting de punta a punta | Osciloscopio en `P0.8` a `P0.11` de la BNC-2110 y registro de escrituras DO y de `MOV`. `Ctrl+E` y `F12` desde la principal, la de impresión, la cámara y Láser 532, con un `QFileDialog` **nativo** abierto desde la cámara y con un `QMessageBox` abierto. Con la grilla en cada etapa: movimiento, autofoco, deriva, traza y la espera de 3 s. Repetir en modo satélite. Registrar el atraso del hilo GUI ([DA] F-3) | Cierre de las cuatro líneas, cada una con su polaridad (el 532 en ALTO), ≤ 50 ms desde la tecla con la GUI libre. Hoy, con la GUI ocupada, se predice hasta ≈ 1.2 s, que tiene que desaparecer con el arreglo de §1.6. **Cero aperturas y cero `MOV`** después de la parada, hasta Rearmar + Play. Rearmar habilitado sólo con un cierre confirmado posterior a la parada. En el satélite, una parada para los dos, desde cualquier ventana. Con el diálogo nativo: si no dispara, se adopta `DontUseNativeDialog` en todo el proceso |
| **BANCO-67** | "Cerrar todos · la grilla sigue" con `legacy_timer` | Generador de funciones en `ai0` (escalón de prueba) o LED. "Cerrar todos" durante un nodo, durante el autofoco y durante la deriva | Nodo **"interrumpido"**, nunca "timeout"; el Healing Pass no lo reexpone; el paso entre nodos se repite y su corrección no se aplica (Z y `startX` iguales a los anteriores); la reapertura llega ≥ 3 s después del cierre (osciloscopio); dos cierres seguidos pausan (si se aprueba Q-C) |
| **BANCO-68** | Cuánto tiempo se retiene `_nidaq_lock` en uso real | Registro temporal, de sólo lectura, del tiempo de cada `with _nidaq_lock` por función (abrir, cerrar, cerrar todos, filtro, espejo con su escritura en disco, primera creación de tareas), durante una sesión de alineación y una grilla en `SAFE_MODE` y en la placa | p50, p99 y máximo por función. `ESTOP_LOCK_TIMEOUT_S` = 2 × el máximo observado, con un piso de 0.25 s. Si el espejo retiene más de 10 ms por el disco, la escritura del estado sale del candado |
| **BANCO-69** ⚠️ | Si el BS sirve como testigo de luz a baja potencia | Láser de 532 nm a baja potencia, con aprobación, sin coloide: BS con el obturador abierto y cerrado, con el filtro arriba, durante 20 rampas de autofoco y 5 escaneos de deriva | BS abierto ≥ 5 veces el ruido del BS cerrado, para que T1 y F1 de [EXP] sean válidos. Si no lo es, la validez del paso descansa sólo en la época y en el `bool` de la apertura, y se dice así en la GUI. Comparte la visita con `BANCO-65` |

Relacionados que siguen abiertos: `BANCO-16` (posición del 532 con la línea sin manejar, que
condiciona el remedio de §1.8), `BANCO-30` (L_mec) y `BANCO-31`.

---

## 7. Preguntas conceptuales para el investigador

**Q-A. ¿Qué hace la parada si la placa está tomada por otro hilo y no confirma el cierre en 0.25 s?**
- (a) Banner rojo persistente que indica cortar la emisión con la llave del láser; sigue reintentando
  y no se rearma hasta un cierre confirmado.
- (b) Lo mismo y, además, una escritura de cierre "de emergencia" sin el candado. Puede ser más
  rápida si el hilo trabado no está dentro del driver, pero se puede cruzar con una apertura en curso,
  y no está probada.
- **Recomiendo (a).** La protección ante un cuelgue real es de hardware (fase 6.2).

**Q-B. Pausa durante el autofoco (hallazgo 1, reproducido en `SAFE_MODE`). ¿Cuándo se arregla?**
- (a) Ya, antes de R4-17: volver a la topología del legado (fin del autofoco en el hilo del worker) y
  agregar la guarda de estado al principio de `grid_finish_autofoco` y de `_grid_trace`, con un test
  que hoy falla y una Ronda 2 corta. No es exento porque toca una apertura.
- (b) Junto con R4-17.
- **Recomiendo (a).** Hoy deja el 532 abierto a alta potencia sin detección, y la PC del banco podría
  recibir `main` antes que R4-17.

**Q-C. Si cerrás dos veces seguidas en el mismo nodo o en el mismo paso entre nodos:**
- (a) la grilla sigue siempre, como dice P-H;
- (b) al segundo cierre consecutivo, la grilla pasa a pausa.
- **Recomiendo (b).** Evita el ciclo "cierro, reabre a los 3 s, cierro" y no cambia P-H para un
  cierre aislado.

**Q-D. Topes de deriva y autofoco mientras falten los datos de banco:**
- (a) aplicar los provisorios de [EXP] §5: no se aplica la corrección, se repite una vez y, si vuelve
  a fallar, pausa;
- (b) sólo avisar, sin rechazar, hasta medir.
- **Recomiendo (a).** Una corrección absurda corre todos los nodos que siguen y el Healing Pass no la
  arregla.

**Q-E. Después de cerrar, ¿la parada pone el filtro de densidad en baja potencia (`up_flipper`)?**
- (a) Sí, como ya hacen el cierre al salir del programa y la Pausa.
- (b) No: la parada sólo toca los obturadores.
- **Recomiendo (a).** Con los obturadores cerrados es inocuo, y toda reapertura manual después del
  rearme empieza en baja potencia. La grilla vuelve a poner alta potencia antes de imprimir, como hoy.

---

## Veredicto

- **Código actual: `SAFETY_VIOLATION`.**
  - Una Pausa durante el autofoco reabre el 532 a alta potencia sin detección, con el watchdog
    renovado indefinidamente (§1.6, [MEDIDO]). Es una regresión respecto del legado.
  - La E-STOP de PySpectrum no bloquea las aperturas del satélite (H12).
  - Los dos son independientes de C-01, pero R4-17 no se puede implementar encima sin resolverlos.
- **Propuesta de este documento: `HARDWARE_SAFE` en diseño**, con estas condiciones:
  1. bandera de parada sin candado, consultada por `open_shutter`, y cierre desde un hilo propio con
     candado con plazo;
  2. guardas de entrada en toda la máquina de estados de la grilla, y fin del autofoco fuera del hilo
     GUI;
  3. época de cierre para el nodo (N-4) y para los pasos entre nodos (N-3), con el BS como testigo
     sólo si `BANCO-69` lo valida;
  4. ningún comando nuevo a la platina;
  5. un filtro y un coordinador por proceso;
  6. `BANCO-66` a `BANCO-69` aprobados antes de usar la parada con los láseres encendidos.
- **`TIMING_HAZARD`** mientras el hilo GUI ejecute las esperas entre nodos (§5.1): hasta ≈ 1.2 s más
  de latencia de la parada.
