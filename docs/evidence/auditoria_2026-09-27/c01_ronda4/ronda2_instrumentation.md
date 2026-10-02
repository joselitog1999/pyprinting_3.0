# C-01 / R4-17 — Ronda 2 — Panel de instrumentación (`instrumentation`)

Estado: COMPLETO (2026-10-02). Ronda de **diseño**: no se modificó código ni tests y no se ejecutó
nada contra hardware. Único archivo escrito en el repositorio: este. Árbol: `main` @ `927e818`
(después de `DEC-041`, el arreglo de la Pausa, y de `DEC-042`).

**Parto de** mis notas de la mini Ronda 1 (`c01_ronda4/instrumentation.md`, acá **[R1-INS]**) y de la
síntesis (`SINTESIS_RONDA1.md`). No repito lo que ya está ahí salvo cuando cambia.

**Qué leí.** `CLAUDE.md`; `.claude/shared/lab-invariants.md` §1-§2; `SINTESIS_RONDA1.md`;
`instrumentation.md`, `devil_advocate.md` y `experimentalist.md` de esta carpeta;
`RESPUESTAS_INVESTIGADOR.md` ("C-01, Ronda 4 — mini Ronda 1", 2026-10-01); `DEC-036`, `DEC-037` y
`DEC-041` en `docs/decisions/DECISION_LOG.md`; `c01_ronda3/gui_design_v2.md` §5;
`PRUEBAS_BANCO_PENDIENTES.md` (BANCO-16, -30, -65 a -70); `docs/PERSPECTIVAS.md` §1.9. Código,
orientado con `graphify query/explain` (`close_all_shutters()`, `up_flipper()`, `._grid_trace()`):
`core/nidaq.py`, `core/shutters.py`, `config.py` (`_PIController`, `wait_on_target`),
`modules/measurements.py`, `modules/trace.py`, `modules/focus.py`, `app.py`,
`pyspectrum/window.py`, `pyspectrum/modules/hardware_session.py` y el test
`tests/test_shutter_confirmation_and_interlocks.py`.

**Marcas.** **[CÓDIGO]** archivo:línea leído en `927e818` · **[NI-DOC]** firma o docstring de
`nidaqmx` 1.5.0 del `.venv` (citada en [R1-INS]) · **[MEDIDO-R1]** sonda de la Ronda 1, en
`SAFE_MODE`, sin hardware · **[INFERIDO]** razonamiento no probado · **[DERIVADO]** cuenta propia con
los insumos a la vista · **[SUPUESTO]** sin respaldo, se mide · **[BANCO]** se resuelve en el banco ·
**[INV-R4]** respuesta del investigador del 2026-10-01 (número de la pregunta de la síntesis) ·
**[DA]**, **[EXP]** notas hermanas de la Ronda 1.

**Decisiones vinculantes que este diseño respeta** ([INV-R4]):
- 3: si el cerrador no consigue la placa, banner persistente "cortá con la llave del láser" y
  reintentos. **No hay escritura sin candado.**
- 4: la parada sube el filtro de densidad **después** del cierre confirmado, y antes de cualquier
  autofoco o movimiento posterior hay que esperar **≈ 100 ms** desde que subió.
- 5: se retoma desde el primer nodo nunca expuesto; el interrumpido va a revisión; si la parada pasó
  de 60 s, deriva y autofoco antes.
- 6: un segundo "Cerrar todos" **no** pausa.
- 7: topes de plausibilidad provisorios: rechazar, repetir una vez, pausar.
- 8, 9, 10-11: confirmación a baja potencia **sin BS**, diferida para los nodos que cortó el
  operador; "no sé" → revisión.
- 14: el láser de 532 **no** tiene interlock remoto: la única parada que no depende del software es
  la llave del láser.
- 15: no se corren PySpectrum legacy y PyPrinting 3.0 a la vez durante una grilla. El diseño supone
  **un solo proceso escritor** de las cuatro líneas (PyPrinting 3.0, solo o como satélite de
  PySpectrum 3.0).

---

## Resumen ejecutivo

1. **La parada se parte en dos mitades que no comparten candado.**
   - **Hilo GUI, sin `_nidaq_lock`:** marca un estado de parada de un módulo nuevo sin dependencias
     (`core/estop_state.py`: un `threading.Event` y una generación), sube la **época de cierre** de
     las cuatro líneas, despierta al cerrador y pone las banderas de alto de las rutinas. Todo en
     < 1 ms, sin E/S [INFERIDO; se prueba con el candado tomado por un hilo colgado, §8].
   - **Hilo cerrador** (`EStopCloser`, uno por proceso, de larga vida): `_nidaq_lock.acquire(timeout =
     0.25 s)`, interlock `"E-STOP"`, escritura de las cuatro líneas a su polaridad de cierre (el 532
     en `line11` queda en **ALTO**), hasta 3 intentos con 50 ms. Sin candado o sin confirmación:
     reintenta cada 0.25 s mientras la parada siga, y el banner rojo lo pone la GUI con su **propio**
     plazo (0.5 s), sin esperar a que el cerrador informe.
   - **"Confirmado"** es el `ok` de una escritura **del cerrador**, sellada con la generación de la
     parada vigente. Nunca `_all_closed_confirmed()`.
2. **Defecto que hay que arreglar antes (o junto con R4-17):** una escritura de cierre fallida con
   nada "creído abierto" no deja nada sin confirmar (`core/nidaq.py:553-562`), y "Cerrar Todos"
   desmarca los botones antes de escribir e ignora el retorno (`core/shutters.py:308-315`).
   - **Regla nueva, en un solo lugar (`_apply_shutter_lines`):** toda escritura fallida en la tarea
     de obturadores deja **sin confirmar** a los que se creían abiertos **y siempre al 532**, porque
     es activo en BAJO: si la falla viene de una placa reiniciada, la línea sin manejar cae a BAJO
     por el pull-down de 50 kΩ y el 532 queda **abierto** (`BANCO-16`). Los otros tres, activos en
     ALTO, quedan cerrados en ese caso.
   - **"Cerrar Todos"** pasa por el cerrador, no desmarca nada hasta el resultado sellado, y con una
     falla deja el banner rojo persistente con el remedio físico.
3. **Época de cierre por línea** (`core/nidaq.py`): un contador por obturador que suben todos los
   cierres pedidos por alguien que no es la rutina dueña (operador, parada, watchdog, interlocks,
   excepthook, fallas de platina). Se sube **antes** de pedir el candado. Las aperturas de la grilla
   pasan la época que anotaron al decidir (`open_shutter(..., expected_epoch=e)`) y `open_shutter` la
   compara **dentro** del candado. Una apertura en vuelo que perdió la carrera se rechaza sin
   escribir; una que la ganó escribe y el cierre llega en el acto, porque el cerrador estaba
   esperando el mismo candado. No hay orden de escrituras que deje la línea abierta después del
   cierre (§2.3).
4. **El filtro y los 100 ms se garantizan en quien abre, no en `up_flipper`.** `up_flipper` anota la
   hora del pulso confirmado (`_flipper_low_since`). La reanudación espera lo que falte hasta
   100 ms en el hilo del worker, y las aperturas de baja potencia de la grilla pasan
   `require_low_power=True`, que `open_shutter` verifica dentro del candado. Retener `_nidaq_lock`
   100 ms dentro de `up_flipper` bloquearía al cerrador: no va ahí.
5. **Platina:** se confirma que la parada **no** manda `STP` ni `HLT` ([R1-INS] §1.4). Para que no
   salga ningún `MOV`: las guardas de entrada de `DEC-041` se extienden a la parada (y a `_grid_move`,
   que no la tiene), y agrego una **retención de movimiento** en `_PIController.MOV` y en los
   comandos de onda (`WGO`, `MVR`), que lee el mismo `estop_state` dentro del candado de la PI. Es la
   última barrera: devuelve `False` sin escribir por USB, sin `_stage_fault` y sin reconexión.
6. **Satélite:** el filtro de teclas de PySpectrum pasa a `core/` con alcance sobre **toda** ventana
   del proceso y llama a un único coordinador. La E-STOP de PySpectrum deja de cerrar por su cuenta y
   de abrir un `QMessageBox` desde el filtro: llama al mismo `request_emergency_stop`, de modo que el
   interlock bloquea las aperturas del satélite aunque el satélite no se haya registrado.
   `is_emergency_stopped` pasa a leer el estado de `core`, sin el candado de sesión.
7. **Lectura a baja potencia sin BS:** filtro arriba con el obturador cerrado → oscuro D de 100 ms
   **durante** la espera de 100 ms → abrir con `expected_epoch` y `require_low_power` → asentamiento
   del obturador → 100 ms en 5 bloques de 20 ms con una tarea **finita** (`channels_photodiodos`,
   como `DEC-037`, cerrada en `finally`, con timeout explícito) → cerrar. **Sin el BS no hay forma
   directa de saber que el filtro subió.** El riesgo no es nuevo (el autofoco abre 1.2-2 s con el
   mismo filtro sin verificar); la lectura le suma ≈ 0.2 s por nodo. Propongo un testigo indirecto
   con el propio fotodiodo de detección (Q-3).
8. **Tiempos** (§6): tecla → líneas cerradas, en software, ≤ 7 ms típico y ≤ ≈ 110 ms en el peor caso
   conocido con la GUI libre, más L_mec (`BANCO-30`). **Con la GUI ocupada sigue el `TIMING_HAZARD`
   de [R1-INS] §5.1**: `DEC-041` no movió el fin del autofoco fuera del hilo GUI, así que una tecla
   puede esperar hasta ≈ 1.2 s más. Es condición de R4-17 mover ese despacho al worker.

**Veredicto:** `HARDWARE_SAFE` **en diseño**, condicionado a: el arreglo de la regla de escrituras
fallidas (§1.7), mover el fin del autofoco al hilo del worker (§6.2), y `BANCO-66`, `-67`, `-68` y
`-16` antes de usar la parada con los láseres encendidos. **`TIMING_HAZARD`** mientras el hilo GUI
ejecute las esperas entre nodos.

---

## 0. Hechos que cambiaron desde la Ronda 1 o que condicionan el diseño

| # | Hecho | Evidencia |
|---|---|---|
| H1 | `DEC-041` está implementado: `is_paused` es un `threading.Event`; el clic en Pausa lo marca con conexión directa (`request_pause`); `_halted()` se consulta en `grid_autofoco`, `grid_finish_autofoco` (después de su `sleep(0.1)`), `_grid_trace` (dos veces), `grid_scan`, `_grid_center_scan`, `on_scan_finished`, `grid_finish`, `_grid_detect`, `_advance_healing_pass` | [CÓDIGO] `measurements.py:1566-1594, 2270-2272, 2320-2323, 2368-2378, 1721-1724` |
| H2 | **`_grid_move` y `grid_next_index` no consultan `_halted()`.** `_grid_move` mueve después de `_check_physical_connection_or_pause` (`:2181-2189`); `grid_next_index` (botón del operador) llama `_grid_move` directo (`:3022-3025`) | [CÓDIGO] |
| H3 | Entre la última guarda de `_grid_trace` y la escritura queda una ventana sin candado: la guarda corre a las `:2374-2376` y `open_shutter` a la `:2378`, fuera de `_nidaq_lock`. Además, `open_shutter` devuelve `bool` y nadie lo mira | [CÓDIGO] |
| H4 | El fin del autofoco **sigue** despachándose en el hilo GUI (`app.py:486-490`, el cierre `_on_autofinish`), y el criterio también (`_dispatch_trace`, `app.py:499, 556-564`). `DEC-041` lo dejó explícitamente fuera ("moving the chain onto one thread") | [CÓDIGO]; `DEC-041` "Not in this fix" |
| H5 | `close_all_shutters` con escritura fallida: `_shutter_signal[:] = desired` y sólo los `previously_open` pasan a `_unconfirmed_shutters`. Si no había ninguno, no queda nada sin confirmar, no se arma `_retry_due` y `_all_closed_confirmed()` da `True` aunque la función devolvió `False` | [CÓDIGO] `nidaq.py:409-411, 553-562` |
| H6 | El test vigente fija ese comportamiento: después de abrir el 637 y fallar el cierre, `get_unconfirmed_shutters() == [LASER]` con `LASER = SHUTTERS[1]` (637) | [CÓDIGO] `tests/test_shutter_confirmation_and_interlocks.py:136, 199-204` |
| H7 | "Cerrar Todos": desmarca los cuatro botones con `blockSignals`, después llama `close_all_shutters()` en el hilo GUI e ignora el retorno | [CÓDIGO] `shutters.py:308-315` |
| H8 | `_pulse_flipper` retiene `_nidaq_lock` durante el pulso: `write(5.0)`, `sleep(0.005)`, `write(0.0)`; si falla, cierra y recrea la tarea AO **dentro** del candado. El *up* (baja potencia) va por `_flipper_task1` = `FLIPPER_AO_UP` = `Dev1/ao0`; el *down* por `_flipper_task0` = `ao1` | [CÓDIGO] `nidaq.py:578-613, 654-704`; `config.py:119-120` |
| H9 | Al importar, `_flipper_high_power = False`: el software **cree** que está en baja potencia sin haber pulsado nada. El flag no sirve como prueba de "baja potencia" | [CÓDIGO] `nidaq.py:116` |
| H10 | La traza y el autofoco renuevan con `heartbeat_shutter(30.0)` explícito (C-29): imponen 30 s aun en "Sin límite" | [CÓDIGO] `trace.py:589, 644`; `focus.py:241, 267, 326, 380` |
| H11 | `channels_photodiodos` con falla de creación llama `close_all_shutters()` **bloqueante** desde el hilo que lee (`nidaq.py:866-876`); el watchdog también cierra bloqueando (`:187`) | [CÓDIGO] |
| H12 | `hardware_session.emergency_stop()` cierra con `close_all_shutters()` en el hilo GUI con el candado de sesión tomado, después aborta la cámara Andor y pone la ganancia EM en 0 con relectura, todo bajo ese candado (`hardware_session.py:150-209`). `window.py:459-482` abre un `QMessageBox.critical` modal después. `is_emergency_stopped` toma el candado de sesión (`:71-74`) y lo consultan una docena de rutinas de PySpectrum | [CÓDIGO]; `grep is_emergency_stopped` en `pyspectrum/` |
| H13 | `nidaq` y `core.nidaq` son el mismo objeto de módulo: el propio módulo se aliasa en `sys.modules` (`nidaq.py:26-29`). Es la condición para que un interlock valga para todo el proceso, incluidos `focus.py` y `confocal.py`, que importan `nidaq` sin el prefijo | [CÓDIGO] |
| H14 | La grilla de PyPrinting **no** toma la sesión exclusiva de `hardware_session`: sólo escucha `sessionChangedSignal` para el modo "subyugado" (`app.py:102-135`) | [CÓDIGO] |
| H15 | `_PIController.MOV` toma su `RLock` de clase, acota por eje y escribe; los comandos de onda (`WGO`, `WGC`, `WAV_LIN`) pasan por `__getattr__` → `_locked_call` con el mismo candado | [CÓDIGO] `config.py:381, 605-655, 664-680` |
| H16 | `BANCO-69` (BS como testigo a baja potencia) quedó **en suspenso**, porque el BS no está habilitado | `docs/PERSPECTIVAS.md:115`; [INV-R4] 10-11 |
| H17 | La lectura de la traza es finita a 10 kS/s (`RATE_MULTICHANNEL / 100`, `trace.py:501`), con `PD_CHANS_LIST = [0, 1, 2, 3, 6]` | [CÓDIGO] `config.py:112, 126` |

---

## 1. Secuencia exacta de la parada de emergencia

### 1.1 Estado nuevo y por qué vive en un módulo aparte

- **`core/estop_state.py`** (sin importar `config` ni `nidaq`, para que lo puedan importar los dos sin
  ciclo):
  - `_active = threading.Event()`;
  - `_gen: int`, `_t0_mono`, `_t0_wall`, `_source`, protegidos por un `threading.Lock` **hoja**
    (`_state_lock`): se toma sólo para asignar esos campos, nunca con E/S ni con otro candado
    adentro;
  - API: `trip(source) -> int` (idempotente: si ya está activo, no cambia `t0` ni la fuente, y
    devuelve la generación vigente), `is_active() -> bool` (lee el `Event`, sin candado),
    `snapshot() -> EStopSnapshot`, `clear(gen) -> bool` (sólo si `gen` es la vigente).
- **Por qué no `_shutter_interlocks`:** el diccionario vive bajo `_nidaq_lock`
  (`set_shutter_interlock`, `nidaq.py:284-289`), y la parada no puede depender de ese candado
  ([DA] F-4). El interlock `"E-STOP"` se sigue poniendo en el diccionario (lo ven las pantallas que ya
  listan interlocks), pero **la autoridad es el `Event`**.

### 1.2 Lo que corre en el hilo GUI (sin `_nidaq_lock`)

El filtro de teclas (§3.2), el botón de la parada o un participante llaman
`EmergencyCoordinator.trigger(fuente)`, que llama `nidaq.request_emergency_stop(fuente)` y después a
los participantes:

| Paso | Qué | Candado que toma | Costo |
|---|---|---|---|
| G1 | `estop_state.trip(fuente)`: `Event.set()`, generación, `t0` | `_state_lock` (hoja) | µs |
| G2 | `_bump_close_epoch(TODAS, causa = "parada: fuente")`: sube la época de las cuatro líneas (§2) | `_epoch_lock` (hoja) | µs |
| G3 | Encola el pedido para el cerrador y lo despierta (`Condition.notify`) | `_closer_cv` (hoja) | µs |
| G4 | Banderas de alto, por **llamada directa**, nunca por señal encolada: `printingWorker.request_stop("parada")` y `dimersWorker.request_stop("parada")` (un `Event` propio, que `grid_halted()` suma a `is_paused`); el predicado de aborto de la traza; `focusWorker.abort_requested = True`; `confocalWorker.signal_scan_stop = True`. Las rutinas de PySpectrum ya consultan `is_emergency_stopped`, que pasa a leer `estop_state` (§3) | ninguno | µs |
| G5 | Banner rojo no modal "PARADA DE EMERGENCIA hh:mm:ss.mmm — cerrando…" y un `QTimer.singleShot(CLOSE_CONFIRM_DEADLINE_S)` propio de la GUI | ninguno | < 1 ms |
| G6 | Encola el trabajo de la cámara Andor de PySpectrum (abortar, ganancia EM en 0, relectura) y las pausas de los Live a un hilo de trabajo, **después** del pedido de cierre | ninguno | — |

- **Nada de esto escribe en la placa, en la PI ni en disco, ni abre diálogos.** Si `_nidaq_lock` está
  tomado por un hilo colgado, el hilo GUI no se entera: vuelve en < 1 ms [INFERIDO; test T1, §8].
- **Desde G1, toda apertura falla sin escribir** (§1.5), aunque el cerrador todavía no haya
  conseguido el candado. Desde G2, la grilla ve la interrupción aunque no se haya escrito nada.

### 1.3 Lo que corre en el hilo cerrador

**`EStopCloser`**: un hilo daemon por proceso, creado al importar `core/nidaq.py` como el
`ShutterWatchdog` (`nidaq.py:208-209`). Su bucle está envuelto en `try/except` y no termina nunca.
Atiende dos clases de pedido, que se juntan (una escritura sirve a todos los pendientes):
- **parada** (`request_emergency_stop`): lleva generación;
- **cierre total** (`request_close_all(causa)`, para "Cerrar todos", el watchdog y los cierres de
  falla): lleva una secuencia.

| Paso | Qué | Candado | Plazo |
|---|---|---|---|
| C1 | `_nidaq_lock.acquire(timeout = ESTOP_LOCK_TIMEOUT_S)` | `_nidaq_lock` con plazo | **0.25 s** (provisorio, `BANCO-68`) |
| C2 | Si es parada: `_shutter_interlocks["E-STOP"] = f"parada de emergencia ({fuente}, gen {g})"` | dentro | µs |
| C3 | Cierre de las cuatro líneas en **una** escritura, cada una a su polaridad de cierre: `desired = [not SHUTTER_POLARITY[s] for s in SHUTTERS]`, es decir `line11` (532) en **ALTO** y `line8`, `line9`, `line10` (637, 592, 808) en **BAJO**. Hasta `SHUTTER_CLOSE_RETRIES = 3` intentos con `SHUTTER_RETRY_DELAY_S = 0.05` s (`nidaq.py:131-132`). Con falla: la regla de §1.7 | dentro | < 1 ms por intento [INFERIDO]; ≤ ≈ 100 ms + 3 escrituras con falla |
| C4 | Con éxito: `_watchdog_deadline = None`, `_retry_due = None` (como hoy, `nidaq.py:547-552`) | dentro | — |
| C5 | Suelta el candado. **Fuera del candado:** despacha las notas de obturadores (`_dispatch_shutter_notes`) y publica `CloseResult(seq, gen, ok, t_write_mono, t_write_wall, err)` por `register_close_result_callback` | ninguno | — |
| C6 | Si es parada y `ok`: `up_flipper(lock_timeout_s = ESTOP_LOCK_TIMEOUT_S)` (filtro a baja potencia, `Dev1/ao0`), que anota `_flipper_low_since` (§1.6) y publica `FilterResult(ok, t)`. Una falla se informa y no cambia el resultado de la parada | `_nidaq_lock` con plazo | ≈ 5 ms + 2 escrituras |
| C7 | Si C1 vence: publica `CloseResult(ok = False, err = "placa tomada por otro hilo")` **una vez por episodio** y vuelve a C1 | — | cada 0.25 s |
| C8 | Si C3 falla y es una parada: espera `ESTOP_RETRY_INTERVAL_S = 0.25` s y vuelve a C1, **sin límite** mientras la parada esté activa ([INV-R4] 3). Si es un cierre total: después de sus 3 intentos lo sigue el reintento del watchdog cada 1 s, como hoy (`DEC-036`) | — | — |

**No hay escritura de cierre sin candado** ([INV-R4] 3). Si el dueño del candado está colgado adentro
del driver, otra escritura sobre la misma tarea probablemente también se trabaría, y si no lo está,
podría cruzarse con una apertura que vuelve a abrir [R1-INS] §1.8.

**`Task.write` y su plazo.** `Task.write(data, auto_start=…, timeout=10.0)` [NI-DOC]. Para una
escritura DO estática por demanda el plazo casi no actúa, pero si el driver se colgara retendría el
candado hasta 10 s. Propongo pasar `timeout = 1.0` explícito en `_write_shutter_lines`
(`nidaq.py:388`). Es una cota, no una garantía: si el cuelgue es dentro del driver, el plazo de
DAQmx tampoco vuelve [INFERIDO]. El banner de §1.4 no depende de eso.

### 1.4 Cuándo se declara "confirmado" y qué dice el banner

- **Confirmado** = existe un `CloseResult` con `ok = True` **del cerrador**, con la generación de la
  parada vigente. Como el cerrador sólo atiende pedidos posteriores al `trip`, toda escritura suya
  es posterior a la parada. Es exactamente el criterio de `DEC-036` ("la placa aceptó la escritura"):
  no prueba que el servo se movió (`BANCO-15`/`16`).
- **No es** `_all_closed_confirmed()` ni `get_open_shutter_names() == []`. Esos dos son condiciones
  **adicionales** para rearmar ([R1-INS] §1.7), no la prueba del cierre.
- **El banner lo maneja la GUI con su propio plazo**, `CLOSE_CONFIRM_DEADLINE_S = 0.5 s`:
  - llega un `CloseResult(ok)` de la generación vigente antes del plazo → "PARADA DE EMERGENCIA
    14:31:52.207 — obturadores: escritura de cierre confirmada 14:31:52.211 (los cuatro). La grilla
    quedó DETENIDA en el nodo 17. Revisá el banco y pulsá [Rearmar]";
  - vence el plazo sin un `ok`, o llega un `ok = False` → banner rojo **persistente**: "PARADA SIN
    CONFIRMAR: la placa no aceptó el cierre (motivo). **Cortá la emisión con la llave del láser.**
    PyPrinting sigue reintentando." El texto nombra la llave porque el láser no tiene interlock
    remoto ([INV-R4] 14).
  - El banner no depende de que el cerrador informe: si el cerrador quedó trabado dentro del driver,
    el plazo de la GUI lo detecta igual.
- **"Reiniciá PyPrinting" no va en el banner** como remedio: con la placa reiniciada, el 532 sin
  manejar queda abierto ([R1-INS] §1.8, `BANCO-16`). El remedio es la llave.

### 1.5 `open_shutter` y `heartbeat_shutter` durante la parada

**`open_shutter(name, timeout_s=_SENTINEL, *, expected_epoch=None, require_low_power=False) -> bool`**

```text
1. si estop_state.is_active():            rechaza SIN pedir el candado → False, nota "parada activa"
2. with _nidaq_lock:
3.     si estop_state.is_active() o hay interlocks:            rechaza → False
4.     si expected_epoch is not None y _line_epoch[name] != expected_epoch:
                                                               rechaza → False, nota "cierre posterior a la decisión"
5.     si require_low_power y no _low_power_settled():         rechaza → False, nota "filtro sin confirmar en baja"
6.     escribe; arma el watchdog (como hoy)
```

- El chequeo 1 evita que una rutina **espere** el candado durante la parada; el 3 cierra la carrera
  con un `trip` que llega mientras la rutina esperaba.
- En el rechazo **no se arma el watchdog** (no se escribió nada), igual que hoy con un interlock
  (`nidaq.py:467-471`).
- Una apertura que ya estaba escribiendo cuando llegó el `trip` termina (< 1 ms) y suelta; el
  cerrador, que esperaba el candado, cierra enseguida (§2.3).

**`heartbeat_shutter()`: no hace nada mientras `estop_state.is_active()`.**
- Después del cierre confirmado `_watchdog_deadline` queda en `None` (C4). Hoy lo vuelven a armar los
  latidos de la traza y del criterio hasta que se detienen (`trace.py:644`, `measurements.py:2392`),
  y un vencimiento posterior dispara los avisos del watchdog **después** de la parada ([R1-INS] §5.2).
- El reintento de un cierre sin confirmar **no** depende del plazo: va por `_retry_due`
  (`nidaq.py:201-206`), así que silenciar el latido no apaga ningún reintento.
- Toca la política del watchdog: no es exento y entra en esta deliberación ([R1-INS] §5.2).

### 1.6 El filtro de densidad y la espera de 100 ms

**Qué hace el pulso** [CÓDIGO] (H8): `up_flipper()` → `_pulse_flipper(False)` → tarea AO de
`Dev1/ao0`: `write(5.0)`, `sleep(0.005)`, `write(0.0)`, bajo `_nidaq_lock`. Retención ≈ 5 ms + 2
escrituras. El servo es casero y no tiene realimentación (`BANCO-22`); "confirmado" es que la placa
aceptó las dos escrituras. El pulso *up* es idempotente: el filtro tiene una salida por posición
(`DEC-036`, decisión 5), no es un conmutador como el espejo.

**Dónde se garantizan los 100 ms: en quien abre después, no en `up_flipper`.**
- **No en `up_flipper`:** esperar 100 ms ahí retendría `_nidaq_lock` (el pulso corre adentro) o
  bloquearía al cerrador. Una parada que llegue en ese lapso esperaría 100 ms el candado.
- **Lo que agrega `up_flipper`:** sólo anota `_flipper_low_since = time.monotonic()` **después** del
  `write(0.0)` exitoso (el fin del pulso: es la cota conservadora, porque el servo arranca en el
  flanco de subida). `down_flipper` lo pone en `None`. Al importar es `None`: el flag
  `_flipper_high_power = False` inicial es una creencia sin pulso (H9) y no cuenta.
- **`_low_power_settled(min_s = FLIPPER_SETTLE_S)`** (`FLIPPER_SETTLE_S = 0.10`, provisorio por
  [INV-R4] 4, se valida con el tránsito de `BANCO-65` A): verdadero sólo si hubo un *up* confirmado,
  no hubo un *down* después, y pasaron ≥ 100 ms.
- **`wait_low_power_settled(min_s, abort=None) -> bool`**: duerme lo que falte, **en el hilo del
  worker** (nunca en el hilo GUI), y devuelve `False` si no hubo *up* confirmado o si `abort()` se
  vuelve verdadero.
- **Respaldo en la apertura:** las aperturas de baja potencia **de la grilla** (autofoco, deriva,
  escaneo posterior, lectura de confirmación) pasan `require_low_power=True`. Las aperturas manuales
  desde los paneles no lo pasan: no cambia la operación de alineación.

**La secuencia que pidió el investigador, después de una parada** ([INV-R4] 4):

| Paso | Qué | Dónde |
|---|---|---|
| 1 | La parada sube el filtro **después** del cierre confirmado (C6) | cerrador |
| 2 | Rearmar y Play (acciones del operador) | GUI |
| 3 | La reanudación vuelve a pulsar *up* (idempotente; cubre un C6 fallido) y exige `True`; si falla, la grilla queda en pausa con el banner "el filtro de densidad no confirmó baja potencia" | worker (`confocalThread`) |
| 4 | `wait_low_power_settled(0.10)` | worker |
| 5 | Recién ahora se mueve la platina (ancla o nodo) y corre el autofoco, que abre con `require_low_power=True` | worker |

- En el flujo normal de la grilla esto ya se cumple con margen: `grid_autofoco` espera 1.0 s después
  de `up_flipper` (`measurements.py:2301, 2312`) y `grid_finish_autofoco` 0.5 s (`:2351`). Este
  diseño **no** acorta esas esperas; sólo pone la cota mínima donde hoy no hay ninguna (la
  reanudación) y una verificación en la apertura.

### 1.7 Arreglo de `close_all_shutters` (y de toda escritura fallida)

**Hoy** (H5): con escritura fallida y ningún obturador "creído abierto", `_unconfirmed_shutters`
queda vacío, no se arma el reintento y `_all_closed_confirmed()` da `True`. Si la falla viene de una
placa reiniciada (`DEC-036`: "placa ausente"), las líneas quedan sin manejar, el pull-down de 50 kΩ
de la PCIe-6353 las lleva a BAJO, y para el 532, activo en BAJO, eso es **abierto** (`BANCO-16`). El
software diría "todo cerrado" con el 532 posiblemente abierto.

**Regla propuesta, en un solo lugar: `_apply_shutter_lines`** (`nidaq.py:394-406`), que usan las
cuatro funciones que escriben (abrir, cerrar uno, cerrar todos, reintento):

```text
si la escritura falló:
    en_riesgo = {obturadores creídos abiertos según _shutter_signal}
              ∪ {s for s in SHUTTERS if SHUTTER_POLARITY[s] is False}     # el 532: activo en BAJO
    para cada s en en_riesgo que no esté ya en _unconfirmed_shutters:
        agregarlo y emitir la nota "cierre NO confirmado: la placa no aceptó la escritura (err)"
    _shutter_signal[i] = cerrar para cada s en en_riesgo                    # el comandado sigue siendo "cerrar"
    _arm_retry()                                                            # siempre: hay al menos uno
```

- **Por qué no los cuatro:** los activos en ALTO (637, 592, 808) sin manejar caen a BAJO = cerrados,
  y si la placa sigue manejándolas, conservan el último valor escrito con éxito, que el software
  conoce. Marcar los cuatro llenaría el banner de falsos "sin confirmar" (pregunta Q-1).
- **La nota dice "cierre"** a propósito: el panel de obturadores ya trata así el caso, con la casilla
  marcada y roja y el banner persistente (`shutters.py:118-160`).
- **Consecuencia en `close_shutter` y `open_shutter`:** heredan la regla sin cambios propios. Una
  apertura fallida del 637 deja también al 532 sin confirmar: es correcto, porque una placa
  reiniciada lo dejó abierto.
- **`_all_closed_confirmed()`** pasa a dar `False` después de cualquier escritura fallida, hasta un
  reintento exitoso.
- **El test `test_close_all_failure_marks_previously_open_shutters`** (H6) cambia su expectativa de
  `[LASER]` a `["532 nm (green)", LASER]`, y se agregan: falla con nada abierto → `[532]`, `False`,
  `_retry_due` armado; falla de apertura del 637 → `[532]`. Es un cambio de contrato deliberado:
  queda en el ADR.
- **`close_all_shutters(cause="sistema", *, lock_timeout_s=None) -> bool`** sigue existiendo como
  función sincrónica (la usan el cerrador por dentro, `_move_z`, el confocal, `_grid_move`), con dos
  agregados: sube la época de las cuatro líneas **antes** de pedir el candado (§2), y acepta un plazo
  de candado. Con plazo vencido devuelve `False` sin escribir y sin marcar nada (no hubo escritura).
- **Quién deja de llamarla bloqueando:** el watchdog (`nidaq.py:187`), `channels_photodiodos` con
  falla (`:875`), el excepthook y `hardware_session.emergency_stop` pasan a `request_close_all(causa)`
  o `request_emergency_stop`. Si el hilo cerrador no estuviera vivo (por ejemplo, una excepción en el
  propio cerrador que llega al excepthook), cierran sincrónicamente con `lock_timeout_s = 1.0`. El
  `atexit` (`nidaq.py:328-335`) cierra sincrónicamente con `lock_timeout_s = 1.0`: al salir del
  intérprete los hilos daemon ya pueden no correr, y un `atexit` sin plazo cuelga el cierre del
  programa.

### 1.8 Arreglo de "Cerrar Todos" (`core/shutters.py:308-315`)

```text
_close_all_shutters_clicked():
    seq = request_close_all(cause="operador: Cerrar todos")     # no bloquea; la época ya subió
    self._pending_close_seq = seq
    estado visual "cerrando…" en el botón; NO se desmarca ninguna casilla
    QTimer.singleShot(CLOSE_CONFIRM_DEADLINE_S, self._check_close_confirmed)

_on_close_result(res):            # señal Qt desde el callback del cerrador (fuera del candado)
    si res.seq < self._pending_close_seq: ignorar                # resultado viejo
    si res.ok:   desmarcar las casillas (salvo las que siguen sin confirmar) y mostrar
                 "Cerrados los cuatro (escritura confirmada hh:mm:ss.mmm)" unos segundos
    si no:       las casillas en riesgo ya quedaron marcadas en rojo por las notas (§1.7);
                 banner rojo persistente "Cerrar todos NO confirmado: cortá la emisión con la
                 llave del láser. PyPrinting sigue reintentando."

_check_close_confirmed():         # plazo propio de la GUI
    si no llegó un ok de self._pending_close_seq: el mismo banner rojo
```

- No bloquea la GUI aunque otro hilo tenga el candado: la escritura la hace el cerrador.
- **Las casillas reflejan la placa, no el clic**, igual que la regla de `DEC-036` para un obturador
  solo (mini Ronda 3 del panel).
- **Los botones individuales del dock** (`Backend.shutter0..3`, `shutters.py:519-545`) también son
  cierres del operador: `close_shutter(name, cause="operador: <nombre>")` sube la época **de esa
  línea**. Sin eso, apagar el botón del 532 durante un nodo reproduce N-4 por otro camino. Los
  cierres propios de las rutinas (fin de la traza, `finally` del autofoco, `grid_pause`) no pasan
  `cause` y no la suben.
- **Con la grilla corriendo**, el rótulo y el banner de `gui_design_v2.md` §5.2 no cambian; lo que
  cambia es que el aviso de éxito o de falla sale del resultado sellado.

### 1.9 Rearmar (sin cambios de fondo respecto de [R1-INS] §1.7)

- Condiciones: un `CloseResult(ok)` de la generación vigente; `get_open_shutter_names() == []` y
  `get_unconfirmed_shutters() == []`; todas las rutinas confirmaron que están quietas (plazo 12 s, la
  espera acotada más larga del `confocalThread`); `estop_state.clear(gen)` sólo con la generación
  vigente; el candado dentro de su plazo para quitar `"E-STOP"` del diccionario.
- **Un único Rearmar por proceso**, el del coordinador: el botón "Rearmar Sistema" de PySpectrum
  (`window.py:484-498`) y el de PyPrinting llaman al mismo. `hardware_session.clear_emergency()`
  (`hardware_session.py:74-79`), que hoy no verifica nada, pasa a ser un participante del rearme.
- Ni la parada ni el rearme llaman `pi.connect()`/`disconnect()`.

### 1.10 Inventario de parámetros y firmas para `core/` (Ronda 2)

| Nombre | Tipo / valor | Dónde | Respaldo |
|---|---|---|---|
| `ESTOP_LOCK_TIMEOUT_S` | `0.25` s | `core/nidaq.py` | provisorio; `BANCO-68` lo fija en 2 × la retención máxima observada, con piso de 0.25 s |
| `ESTOP_RETRY_INTERVAL_S` | `0.25` s | `core/nidaq.py` | [R1-INS] §1.3 |
| `CLOSE_CONFIRM_DEADLINE_S` | `0.5` s | GUI (coordinador) | 2 × `ESTOP_LOCK_TIMEOUT_S`; [INFERIDO] |
| `FLIPPER_SETTLE_S` | `0.10` s | `core/nidaq.py` | [INV-R4] 4; tránsito en `BANCO-65` A |
| `REARM_IDLE_TIMEOUT_S` | `12.0` s | coordinador | [R1-INS] §1.7 |
| `LONG_STOP_S` | `60.0` s | grilla | [INV-R4] 5; [EXP] §2.3 |
| `OPERATOR_CLOSE_HOLD_S` | `3.0` s | grilla (no `core`) | P-b de la novena ronda |
| `estop_state.trip(source: str) -> int` | | `core/estop_state.py` | |
| `estop_state.is_active() -> bool` | sin candado | ídem | |
| `estop_state.snapshot() -> EStopSnapshot(active, gen, source, t0_mono, t0_wall)` | | ídem | |
| `estop_state.clear(gen: int) -> bool` | | ídem | |
| `request_emergency_stop(source: str) -> int` | no bloquea; generación | `core/nidaq.py` | |
| `request_close_all(cause: str) -> int` | no bloquea; secuencia | ídem | |
| `close_all_shutters(cause: str = "sistema", *, lock_timeout_s: float \| None = None) -> bool` | sincrónica | ídem | |
| `close_shutter(name: str, *, cause: str \| None = None) -> bool` | `cause` sólo para cierres del operador | ídem | |
| `open_shutter(name, timeout_s=_SENTINEL, *, expected_epoch: int \| None = None, require_low_power: bool = False) -> bool` | | ídem | |
| `get_close_epoch(name: str) -> int`; `get_last_close(name) -> CloseEpoch(n, cause, t_mono)` | sin candado | ídem | |
| `register_close_result_callback(fn: Callable[[CloseResult], None])` | se llama fuera del candado | ídem | |
| `CloseResult(seq, gen, ok, t_write_mono, t_write_wall, err)` | `NamedTuple` | ídem | |
| `up_flipper(*, lock_timeout_s=None) -> bool`; `down_flipper(*, lock_timeout_s=None) -> bool` | anotan `_flipper_low_since` | ídem | |
| `flipper_low_since() -> float \| None`; `wait_low_power_settled(min_s=FLIPPER_SETTLE_S, abort=None) -> bool` | | ídem | |
| `_PIController.MOV` / `WGO` / `MVR`: retención de movimiento | devuelve `False` con `estop_state.is_active()` | `config.py` (y `_MockPI`, paridad) | §4 |

**Orden de candados.** `_state_lock`, `_epoch_lock`, `_closer_cv` y `_watchdog_lock` son hojas: no
toman nada adentro. El hilo GUI sólo toma hojas. El cerrador toma `_nidaq_lock` (y hojas). El orden
existente `_PIController._lock` → `_nidaq_lock` (`_stage_fault`, `connect`) no cambia, y la
retención de movimiento sólo lee un `Event`. No aparece ningún ciclo.

---

## 2. Época de cierre en `core/nidaq.py`

### 2.1 Qué es

- `_line_epoch: dict[str, int]`, una por obturador, y `_last_close: dict[str, CloseEpoch]` con la
  causa y la hora.
- `_bump_close_epoch(names, cause)` las sube bajo `_epoch_lock` (hoja). `+=` sobre un entero no es
  atómico entre hilos en CPython (leer, sumar, guardar son pasos distintos), por eso el candado hoja.
- **Monótona y sin limpieza:** nadie la "baja", así que no tiene dueño ni carrera de reinicio
  ([R1-INS] §3.2). Cada consumidor compara contra el valor que anotó.
- **Por línea y no global:** cerrar a mano el 637 no interrumpe un nodo de 532.

### 2.2 Quién la sube y quién la lee

| Sube (antes de pedir `_nidaq_lock`) | Líneas |
|---|---|
| `request_emergency_stop` (paso G2) | las cuatro |
| `request_close_all(causa)`: "Cerrar todos", watchdog, `channels_photodiodos` con falla, excepthook | las cuatro |
| `close_all_shutters(cause)` sincrónica: `_move_z` sin llegada (`focus.py:488-490`), `_grid_move` sin llegada (`measurements.py:2189-2196`), aborto del confocal por la platina (`confocal.py:994`), `atexit` | las cuatro |
| `trip_shutter_interlock` y `_stage_fault` (`config.py:253-258`) | las cuatro |
| `close_shutter(name, cause=...)` desde los botones del dock | esa línea |
| **No la suben:** `close_shutter` sin `cause` (fin de traza, `finally` del autofoco, `grid_pause`, `stop_scan`) | — |

| Lee | Para qué |
|---|---|
| `open_shutter(..., expected_epoch=e)`, **dentro** de `_nidaq_lock` | rechaza una apertura decidida antes de un cierre |
| La grilla, en la primera línea de cada entrada, junto con `_halted()` | detecta la interrupción y decide (nodo "interrumpido", paso inválido, espera de 3 s o pausa) |
| `grid_trace_detect`, primera línea, **antes** del `heartbeat_shutter()` de `measurements.py:2392` | un nodo interrumpido no vuelve a armar el plazo ([R1-INS] §3.2) |
| `focus_autocorr_lin_x2` entre las dos iteraciones y antes de cada `_move_z(z_gone[i_max])`; la deriva y el escaneo posterior antes de aplicar el centro de masa | invalidan el paso (N-3, [R1-INS] §4.2) |
| La lectura a baja potencia, al terminar | resultado "no sé" si cambió (§5) |

**La época de la grilla.** La grilla guarda `self._grid_epoch[laser]`, la época que **aceptó** por
última vez, y la pasa a todas sus aperturas (impresión, autofoco, deriva, escaneo, lectura). Sólo
la actualiza en dos momentos:
1. en Play (después de una pausa o de un rearme);
2. al terminar la espera visible de 3 s después de un cierre del operador, si durante la espera no
   hubo otro cierre.

Así, después de cualquier cierre ajeno, **ninguna** apertura de la grilla prospera hasta que la
grilla adopte la época nueva: no hace falta un interlock global para la espera de 3 s ([DA] §2.3
punto 1), y las aperturas manuales de los paneles no quedan afectadas.

**Un segundo "Cerrar todos" durante la espera** ([INV-R4] 6: no pausa) sube la época otra vez; al
terminar la espera, la grilla ve que cambió y la **reinicia** desde el último cierre. Es la regla
"toda reapertura automática espera 3 s visibles después de un cierre del operador" aplicada al
último cierre (pregunta Q-4).

Las señales que llevan una apertura a otro hilo agregan la época como argumento:
`grid_autofocusSignal(str mode, int epoch)` → `focus_autocorr_lin_x2(mode, epoch)`;
`grid_scanSignal(str laser, str mode, str kind, int epoch)` → `start_scan_routines`. La traza, en
modo grilla (`mode_printing != "none"`), **no abre**: la apertura es de `_grid_trace` (quita la doble
apertura de `trace.py:586` y el hueco de [DA] §0-5).

### 2.3 Por qué una apertura en vuelo no reabre después de un cierre del operador

La apertura revisa la época **dentro** de `_nidaq_lock`; el cierre sube la época **fuera** y escribe
**dentro**. Con eso, los casos posibles:

| Cuándo cae el cierre respecto de la apertura de la grilla | Qué pasa | Luz |
|---|---|---|
| Antes de que la grilla anote su época (la entrada de la etapa) | La grilla anota la época nueva, pero su `_grid_epoch` es el viejo: la primera línea de la etapa ve la diferencia y no abre | ninguna |
| Entre la anotación y el pedido del candado (el `sleep(0.5)` de `_grid_trace`, `measurements.py:2373`) | `open_shutter` ve `_line_epoch != expected_epoch` dentro del candado → `False` sin escribir. El nodo queda pendiente, sin exposición | ninguna |
| Con la apertura esperando el candado | Ídem: al entrar ve la época nueva | ninguna |
| Con la apertura **dentro** del candado, entre el chequeo y la escritura | La apertura escribe (ya decidió). El cerrador está esperando ese candado: lo toma al soltarse y escribe el cierre. La escritura de cierre es **siempre posterior** | ≈ suelta + toma + escritura (< 1 ms) + despertar (≤ 5 ms, intervalo del GIL) + L_mec. El nodo queda "expuesto sin decisión" (P4) y `grid_trace_detect` lo ve en su primera línea |
| Después de la escritura de apertura | Es un cierre común durante el nodo: se escribe enseguida, y el criterio lo ve en el tick siguiente | la del nodo hasta el cierre |

No hay ningún orden de las dos escrituras que deje la línea abierta después del cierre: el candado
las serializa y la apertura que pierde la carrera no escribe. La única ventana de luz es la de la
cuarta fila, que equivale a "el operador cerró justo después de que abrió", y no se puede reducir
sin hardware.

---

## 3. Modo satélite

### 3.1 Qué pasa hoy

- La E-STOP de PySpectrum cierra con `close_all_shutters()` y marca `_emergency_active`, pero **no**
  pone ningún interlock de `core/nidaq.py` (H12): la grilla del satélite reabre en el nodo siguiente
  ([R1-INS] §2.2).
- Su filtro de teclas actúa sobre ventanas registradas y sus modales: las teclas en la ventana del
  satélite no disparan, las de un modal del satélite sí ([MEDIDO-R1]).
- La acción bloquea: cámara Andor en el hilo GUI con el candado de sesión, y un `QMessageBox`
  modal abierto desde el filtro (`window.py:474`).

### 3.2 Diseño: un filtro, un coordinador, un estado

- **`core/emergency_keys.py`**: el filtro de `window.py:87-160` se muda acá sin dependencias de
  `pyspectrum/`.
  - Alcance: **toda ventana del proceso**, sin registro (una ventana nueva no queda afuera, [DA]
    F-2).
  - Conserva la lógica de una pulsación por disparo (consume `ShortcutOverride` y el `KeyPress`
    siguiente) y `isAutoRepeat()`.
  - `install(app, coordinator)` es idempotente: si PySpectrum ya lo instaló, la llamada del satélite
    no hace nada.
  - Se quitan los `QShortcut` de `Ctrl+E`/`F12` de `window.py:693-696`: con el filtro no disparan, y
    son el registro doble que da `activatedAmbiguously` si el filtro falta ([MEDIDO-R1]).
- **`EmergencyCoordinator`** (`core/`, un `QObject` por proceso): `trigger(fuente)` hace G1 a G6
  (§1.2) **una sola vez por pulsación** y llama sin bloquear a los participantes.
  - **PyPrinting** suelto lo crea en `app.py` (`__main__`); en el satélite lo crea PySpectrum y
    `create_app_satellite(..., host=…)` registra a PyPrinting como participante
    (`window.py:959`).
  - **PySpectrum:** el botón y el filtro llaman a `coordinator.trigger("PySpectrum")`.
    `hardware_session.emergency_stop()` queda como participante **sin** la parte de obturadores:
    marca su estado, y la cámara (abortar, ganancia EM en 0 con relectura) y las pausas de los Live
    corren en un hilo de trabajo, **después** del pedido de cierre y **sin** el candado de sesión
    tomado durante la E/S de la cámara. El `QMessageBox` se reemplaza por el banner.
  - **`hardware_session.is_emergency_stopped`** devuelve `estop_state.is_active()` (sin candado). Las
    rutinas de PySpectrum que ya lo consultan (`grid_runner.py:63`, `step_and_glue.py:552`,
    `linescan_spectroscopy.py:618`, …) quedan detenidas por la parada de PyPrinting también, y dejan
    de poder trabarse en el candado de sesión mientras la E-STOP hace E/S.
- **Cómo se detiene la grilla del satélite** (tres barreras independientes):
  1. su bandera de alto, por llamada directa del coordinador (participante registrado);
  2. aunque el registro haya fallado ([DA] F-6), sus aperturas fallan en `open_shutter` por
     `estop_state`, que es del proceso (H13: un solo `nidaq`);
  3. sus movimientos fallan en `_PIController.MOV` por la retención (§4).
- **Rearmar:** uno solo para los dos programas (§1.9).

### 3.3 Contención de recursos en el satélite

- **La grilla de PyPrinting no toma la sesión exclusiva** (H14). Una rutina de PySpectrum puede
  arrancar durante una grilla y competir por el motor de entradas analógicas (−50103) y por los
  obturadores. Propongo que la grilla haga `hardware_session.acquire_session("PyPrinting: grilla")`
  al empezar y la suelte al terminar o al detenerse. Es una línea por extremo, pero cambia una
  interacción entre programas: lo dejo para la arquitectura de esta ronda.
- **No hay `*IDN?` por USB en ningún paso de la parada:** la retención de movimiento lee un `Event`,
  y `qIDN()` ya devuelve el valor leído al conectar (`config.py:657-662`).

---

## 4. Platina PI

### 4.1 No se manda `STP` ni `HLT` (confirmado)

Las razones de [R1-INS] §1.4 siguen:
- con los cuatro obturadores cerrados, un movimiento del piezo no es un riesgo óptico; todo `MOV`
  está acotado por eje en el driver (`clamp_axis_um`, `config.py:615-624`), y los generadores de onda
  hacen un solo ciclo (`WGC(eje, 1)`) y terminan solos;
- `STP` esperaría el `RLock` de `_PIController`, que `connect()` retiene ≥ 3 s durante el home;
- sin ese candado se intercalaría con una lectura y podría producir `−1004`, que
  `_is_stage_comm_error` clasifica como falla de comunicación → `_stage_fault` → interlock
  `"Platina PI"` → reconexión del operador → **home**: el evento que `DEC-036` prohíbe;
- `STP` deja el error 10 en el controlador y el eje en una posición intermedia.

### 4.2 Cómo se garantiza que no salga ningún `MOV` después de la parada

| Barrera | Qué hace | Estado |
|---|---|---|
| 1. Guardas de entrada de `DEC-041` | `grid_halted()` pasa a ser `is_paused or _stop_event.is_set() or estop_state.is_active()`. Cada entrada de la lista de H1 la consulta antes de mover | existe; se extiende |
| 2. Guardas que faltan | `_grid_move` (`measurements.py:2181`), antes del `MOV`; `grid_next_index` (`:3022`) en parada (con pausa sigue como hoy: es un botón del operador) | nuevo |
| 3. Época de la grilla | una entrada que llega por una señal vieja encolada (por ejemplo `autofinishSignal` o `scanfinishedSignal` después de la parada) ve `_line_epoch != _grid_epoch` y vuelve sin mover | nuevo (§2) |
| 4. **Retención de movimiento** en el driver | `_PIController.MOV`, `MVR` y `WGO` (este último por `_locked_call`, H15) consultan `estop_state.is_active()` **dentro** del candado de la PI, antes de escribir por USB. Si está activa: no escriben, imprimen "[PI] MOV retenido por la parada de emergencia", no tocan la posición en caché, **no** llaman `_stage_fault` y devuelven `False`. `_MockPI` hace lo mismo (paridad de `SAFE_MODE`) | nuevo; última barrera |
| 5. Movimientos de retorno | `stop_scan` del confocal no vuelve a la posición inicial en una parada (`confocal.py:768-769`); usa un camino como `_abort_scan_on_stage_fault` (`confocal.py:985-995`) | nuevo |

- **Un `MOV` que ya salió** cuando llegó la parada termina (ms a decenas de ms) y una onda en curso
  termina su ciclo (≈ 0.3 s en el autofoco [EXP] H5). No se interrumpe.
- **Un `MOV` retenido devuelve `False`.** Los llamadores que hoy lo ignoran siguen a una
  `wait_on_target` que no confirma; por eso la barrera 1 y la 2 van primero, para que la 4 casi
  nunca actúe. `_grid_move` mira el `bool`: con la parada activa vuelve sin cerrar ni mostrar
  "la platina no confirmó la llegada" (mensaje equivocado en ese caso).
- **`connect()` y `disconnect()`** (acciones del operador, cierran los obturadores antes de mover,
  `DEC-036`) quedan fuera de la retención: el operador puede cerrar el programa durante una parada
  sin que el `MOV [0, 0, 0]` de `disconnect` falle. La parada y el rearme no los llaman.
- **Movimientos manuales del operador** (flechas y campos del panel de nanoposicionamiento) quedan
  retenidos hasta Rearmar (pregunta Q-2).
- Es un cambio de comportamiento de la platina: no es exento y entra en esta deliberación.

---

## 5. Lectura a baja potencia sin BS

### 5.1 Secuencia de hardware

Vale para la confirmación inmediata (corte por el criterio en presets de ventana corta) y para la
diferida (nodos que cortó el operador, la pausa o la parada, [INV-R4] 8). Corre como **slot del
worker en `confocalThread`**, encolado **después** de `traceWorker.stop`, así que la traza ya no lee
(evita −50103 por el motor AI) y nada del hilo GUI espera.

| Paso | Qué | Tarea DAQmx / candado | Tiempo |
|---|---|---|---|
| L0 | Anotar `e = self._grid_epoch[laser]`; verificar que el obturador está cerrado y que no hay parada | — | — |
| L1 | Diferida con > 60 s desde el cierre: deriva sobre P0 y autofoco in situ antes ([INV-R4] 5; [EXP] §2.3). Inmediata: verificar ≥ 1 s desde el cierre, para que una NP atrapada se vaya ([EXP] §1.4, [AN17]) | — | según el caso |
| L2 | `up_flipper()` con el obturador **cerrado**. Debe devolver `True`; si no, no se lee: "no sé" → revisión, y la grilla pausa (sin filtro confirmado, el autofoco siguiente tampoco sería seguro). Si el filtro ya estaba arriba por el autofoco, no se pulsa: vale la hora anotada | tarea AO de `ao0`, bajo `_nidaq_lock` ≈ 5 ms | 5 ms |
| L3 | **Oscuro D**: una lectura finita de 100 ms con el obturador cerrado, mismas luces y misma ganancia. **Ocupa la espera de 100 ms del filtro**: la luz del láser no llega con el obturador cerrado, así que la posición del filtro no cambia D | `channels_photodiodos(1e4, 1000)` finita, creada, leída y cerrada en `finally` (`DEC-037`) | 100 ms + creación |
| L4 | `wait_low_power_settled(0.10)` (normalmente ya se cumplió durante L3) | — | 0 a 100 ms |
| L5 | `open_shutter(laser, expected_epoch=e, require_low_power=True)`; `False` → "no sé" | DO, bajo `_nidaq_lock` | < 1 ms |
| L6 | Asentamiento del obturador: `t_settle` = p99 de apertura de `BANCO-30` + 10 ms (hasta medirlo, 50 ms [SUPUESTO, EXP]) | — | ≈ 50 ms |
| L7 | **Lectura: 100 ms en 5 bloques de 20 ms** (un período de 50 Hz por bloque). Una sola tarea finita de 1000 muestras por canal a 10 kS/s, `task.read(1000, timeout = 0.6)` explícito: un `read` colgado no puede dejar el obturador abierto los 10 s del plazo por defecto. `heartbeat_shutter()` **sin argumento** antes de leer (C-29) | finita, sin candado de la placa (el AI no usa `_nidaq_lock`) | 100 ms + creación |
| L8 | `close_shutter(laser)` en un `finally` que envuelve L5-L7 | DO | < 1 ms + L_mec |
| L9 | Validez: si `get_close_epoch(laser) != e` o `estop_state.is_active()` → "no sé" (el operador o la parada cortaron durante la lectura). El filtro **no** se baja acá: lo pide el paso siguiente ([EXP] §4.1 paso 8) | — | — |

- **Costo:** ≈ 100 ms (L3, que cubre L4) + 50 ms + 100 ms + dos creaciones de tarea ≈ **0.3 s** más la
  creación (sin medir, `BANCO-68`). En la inmediata se suma el ≥ 1 s desde el cierre, que en la
  práctica cubre todo lo anterior si L2 y L3 corren dentro de ese segundo.
- **Por qué crear la tarea dentro de la ventana abierta y no antes:** a baja potencia la dosis no
  importa (el autofoco abre ≈ 1.2-2 s, [EXP] H5); lo que importa es no dejar el obturador abierto sin
  cota, y eso lo da el `timeout` del `read` y el `finally`. Si `BANCO-68` muestra que crear la tarea
  tarda más de ≈ 50 ms, se crea antes de L5.
- **Bloques:** la síntesis y [INV-R4] fijan 100 ms en bloques de 20 ms: son **5** bloques. El texto de
  `BANCO-65` dice "20 lecturas de 100 ms (10 bloques de 20 ms)", que son 200 ms: hay que corregir uno
  de los dos (§7). Con 5 bloques, la dispersión entre bloques es gruesa; el estadístico lo decide
  metrología.
- **Guardas de nivel que no necesitan el BS:**
  - base sobre el oscuro: `V_base − D` ≥ el mínimo de `BANCO-65` A4 (hoy, [EXP]: ≥ 2 mV) o "no sé".
    Con el espejo de detección abajo (C-08: su posición real no se conoce), la lectura ve ≈ D y cae
    acá o en R < 0.85, nunca en "no la ve";
  - `D` dentro de su rango habitual de la sesión, o "no sé".

### 5.2 La verificación del filtro sin el BS

- **Hoy no se puede verificar el filtro.** Es casero, sin realimentación (`BANCO-22`), y "confirmado"
  sólo dice que la placa aceptó el pulso. El único testigo previsto era el BS ([EXP] §4.1 paso 5), y
  no está habilitado ([INV-R4] 10-11).
- **Qué queda como riesgo** (filtro trabado en alta potencia):
  - la lectura sería a alta potencia durante `t_settle` + 100 ms + el cierre ≈ **0.2 s** sobre el
    nodo;
  - en un nodo vacío puede imprimir: con un tiempo de captura de 1 a 20 s ([INV3]) y una
    distribución exponencial [SUPUESTO], P(captura en 0.2 s) = 1 − e^(−0.2/τ) ≈ **1 % a 18 %**
    [DERIVADO];
  - sobre una NP impresa, 0.2 s más a la potencia de impresión (la impresión misma dura 1-20 s): menor;
  - el valor leído sería ≈ A veces mayor que la base de baja potencia: R ≫ u_c, o sea un falso "ve la
    NP". Ese error deja una **vacancia**, el error benigno ([DA] §5.2).
- **El riesgo no es nuevo:** el autofoco abre ≈ 1.2-2 s por nodo con el mismo filtro sin verificar
  ([EXP] H5), y los escaneos ≈ 4 s. La lectura le suma ≈ 10 % de la exposición de un autofoco. No
  cambia el orden de magnitud de un riesgo que el banco corre desde el legado [DERIVADO].
- **Testigo indirecto posible, sin el BS (pregunta Q-3):** el fotodiodo de detección mismo.
  - Con el filtro arriba, el nivel del sustrato (`V − D`) es ≈ 1/A del de alta potencia. La NP sube
    la señal ×1.4 a ×2 ([INV3]). Si el primer bloque de 20 ms da `V − D` > k·(`V_base,baja − D`), con
    2 < k < A (por ejemplo k = 3), el filtro **no** subió: se cierra en el acto, "no sé" y pausa.
  - La referencia de baja potencia es la de la propia sesión (la base previa a baja potencia, o el
    nivel del perfil del autofoco, que ya se mide a baja potencia).
  - Exposición a alta potencia en ese caso: `t_settle` + 20 ms + el cierre ≈ 0.1 s: P ≈ 0.5 % a 10 %.
  - Vale sólo si A ≥ 10 (OD ≥ 1, `BANCO-65` A) y si el espejo está arriba. Es análogo a la idea
    descartada con el BS, pero usa un sensor que ya está habilitado; por eso lo pregunto y no lo
    adopto.
- **Qué mide `BANCO-65` para esto** (sin BS): la OD del filtro con un medidor de potencia (alta y baja);
  el **tránsito** del filtro registrando el fotodiodo de detección sobre el sustrato a 10 kS/s durante
  10 ciclos de *up* y *down*, con el obturador abierto y **sin coloide** (valida los 100 ms, o los
  corrige); y, si se aprueba Q-3, el cociente de niveles del fotodiodo de detección en alta y en baja
  sobre el sustrato (A_PD), que fija k.

---

## 6. Tiempos del peor caso

### 6.1 Tabla

| Tramo | Típico | Peor caso conocido | Qué lo acota | Fuente |
|---|---|---|---|---|
| **Parada → líneas cerradas** (software, GUI libre): filtro + G1-G3 + despertar del cerrador + `acquire` + escritura | ≤ 1 ms + ≤ 5 ms + 0 + < 1 ms ≈ **≤ 7 ms** | + L_lock: pulso del filtro ≈ 5-10 ms; cierre ajeno reintentando ≈ 100 ms + 3 escrituras; espejo 3 ms + **escritura del estado en disco** (sin medir, `nidaq.py:724-730, 811`); creación de tarea en la ruta de falla (sin medir) → **≈ 110 ms** | `ESTOP_LOCK_TIMEOUT_S` = 0.25 s y el banner a 0.5 s | [INFERIDO]; `BANCO-66`, `BANCO-68` |
| Ídem, más la mecánica | + L_mec | + L_mec | — | `BANCO-30` |
| **Ídem con la GUI ocupada (hoy, después de `DEC-041`)** | + 0 | + **≈ 1.2 s**: `grid_finish_autofoco` (`sleep(0.1)`, `qPOS`, `MOV`, `down_flipper` + `sleep(0.5)`) y `_grid_trace` (`down_flipper` + `sleep(0.5)`) en el hilo GUI (H4), más `_save_trace` y el HDF5 de `grid_trace_detect` | mover el despacho al worker (§6.2) | [CÓDIGO] `measurements.py:2320-2380`; [R1-INS] §5.1 |
| Placa tomada (dueño colgado) | — | aviso "placa tomada" a 0.25 s; banner "cortá con la llave" a 0.5 s; reintento cada 0.25 s, sin fin | la llave del láser | [INV-R4] 3, 14 |
| Placa ausente | — | 3 intentos ≈ 100 ms + intentos de crear la tarea (sin medir) → banner a ≤ 0.5 s; el 532 queda sin confirmar (§1.7) | ídem | `BANCO-16`, `BANCO-68` |
| **Cierre del operador → nodo marcado "interrumpido"** con `legacy_timer` | ≤ 1 tick ≈ **47.5 ms** | + el atraso de la GUI (el criterio corre en el hilo GUI) | el tick | [MEDIDO] `c01_ronda1/timer_probe.py` (`DEC-037`) |
| Ídem con el backend de bloques (opción E) | ≤ 1 bloque (10-20 ms) | + `L_sis` p95 ≤ 20 ms | el bloque | `c01_ronda2/architecture.md:974, 1015` |
| Cierre del operador **entre nodos** → paso invalidado | el próximo punto de control: entre las dos rampas del autofoco (≤ ≈ 0.6 s), antes de `_move_z`, al terminar el escaneo de deriva (≈ 4 s) | ídem | la corrección no se aplica aunque el paso termine a oscuras | [EXP] H5, H7 |
| **Cierre del operador → primera reapertura de la grilla** | ≥ 3 s desde el **último** cierre | ídem | `_grid_epoch` (§2.2) | P-b; [INV-R4] 6 |
| **Rearmar + Play → primera apertura**, parada ≤ 60 s, sin autofoco pendiente | `_grid_move` (`MOV` + `wait_on_target`, decenas de ms) + `down_flipper` + 0.5 s → apertura a alta potencia ≈ **0.6 s** después de Play | `wait_on_target` ≤ 5 s | — | [CÓDIGO] `measurements.py:2181-2196, 2368-2380` |
| Ídem, parada > 60 s o autofoco pendiente | *up* + ≥ 100 ms + `MOV` al ancla + 0.1 s + *up* + 1.0 s → apertura del autofoco a baja potencia ≈ **1.2 s** después de Play | ídem | `require_low_power` en la apertura | §1.6; `measurements.py:2301, 2312` |

### 6.2 Relación con el watchdog y con la latencia aceptada

- **La parada no depende del watchdog.** Después del cierre confirmado el plazo queda en `None` y los
  latidos no hacen nada mientras dure la parada (§1.5). El reintento de un cierre sin confirmar sigue
  por dos caminos: el cerrador cada 0.25 s y el watchdog cada 1.0 s (`WATCHDOG_RETRY_INTERVAL_S`).
  Los dos se serializan en `_nidaq_lock` y escriben "cerrar": es idempotente.
- **El watchdog deja de colgarse en su propio cierre** (H11): pide `request_close_all("watchdog")` y
  sigue sondeando cada 100 ms. Su latencia de corte queda en plazo (30 s) + ≤ 100 ms de sondeo + la
  del cerrador. No cambia la política (30 s, "Sin límite"), sólo la mecánica.
- **≤ 20 ms (diseño de la opción E)** es la latencia del **corte por el criterio** en el hilo de
  adquisición. Con `legacy_timer` no aplica: el criterio corre en el tick de ≈ 47.5 ms en el hilo
  GUI.
- **La latencia de la parada** es independiente del backend de la traza, porque el cerrador es un
  hilo propio: la aceptación de `BANCO-66` es **≤ 20 ms de software** (de la tecla al flanco de la
  línea DO) con la GUI libre, con cualquiera de los dos backends, y la mecánica aparte (`BANCO-30`).
- **Con la GUI ocupada la parada llega tarde, y eso no lo arregla el cerrador:** la tecla se procesa
  en el hilo GUI. Condición de R4-17: conectar `autofinishSignal` a un slot del worker en
  `confocalThread`, como el legado (`printing2/PyPrinting_UNSAM.py:418`), y sacar de
  `grid_trace_detect` la escritura a disco (o dejarla en un hilo de E/S). Con eso, el peor atraso
  esperado del hilo GUI baja a lo que tarde un `repaint` [INFERIDO]; `BANCO-66` lo mide con el `QTimer`
  de atraso de [DA] F-3.
- **Alternativa, sólo si `BANCO-66` muestra que un `QFileDialog` nativo traga la tecla:** un
  `RegisterHotKey` de Win32 en un hilo propio con su bucle de mensajes, que dispara aunque el hilo GUI
  esté ocupado o haya un diálogo nativo. Costo: la tecla queda tomada en **todo** Windows mientras
  PyPrinting corre (`F12` de los navegadores, `Ctrl+E` de muchos programas). No la propongo ahora; la
  otra salida es `DontUseNativeDialog` en todo el proceso ([R1-INS] §2.1).

---

## 7. Qué medir en el banco antes de habilitarlo

| ID | Estado | Qué agrega esta ronda |
|---|---|---|
| **BANCO-16** | ☐ abierto | Condiciona la regla de §1.7 (el 532 sin manejar = abierto) y el texto del banner. Si el servo queda cerrado con la línea sin manejar, la regla puede limitarse a los creídos abiertos (Q-1) |
| **BANCO-30** | ☐ abierto | L_mec de cierre y `t_settle` de apertura para la lectura a baja potencia (L6) |
| **BANCO-65** ⚠️ | ☐ abierto | (a) Corregir el texto: "100 ms en 5 bloques de 20 ms" o "200 ms en 10 bloques"; (b) el **tránsito del filtro** con el fotodiodo de detección sobre el sustrato, sin BS y sin coloide (valida `FLIPPER_SETTLE_S` = 0.10 s); (c) si se aprueba Q-3: A_PD, el cociente de niveles del fotodiodo de detección en alta y en baja sobre el sustrato |
| **BANCO-66** | ☐ abierto | Agregar: (a) con el candado retenido por una sonda de diagnóstico (en `SAFE_MODE` no hace falta el banco; en la placa, con los láseres apagados), el banner "cortá con la llave" aparece a ≤ 0.5 s; (b) "Reset Device" de NI MAX con PyPrinting abierto y **láseres apagados**, y después la parada: el banner **no** dice "confirmado" hasta una escritura exitosa, el 532 figura sin confirmar, y se anota la posición física del servo (es el caso (b) de `BANCO-16`); (c) registro de `MOV` de la PI: cero movimientos después de la parada, incluido el botón "siguiente índice", hasta Rearmar; (d) osciloscopio en `ao0` y `line11`: después de rearmar, ≥ 100 ms entre el pulso *up* y la apertura del autofoco; (e) en el satélite, la parada desde PySpectrum bloquea las aperturas y los movimientos de la grilla de PyPrinting, y viceversa, con un solo Rearmar |
| **BANCO-67** | ☐ abierto | Agregar: segundo "Cerrar todos" durante la espera → no pausa; la reapertura llega ≥ 3 s después del **segundo** cierre (osciloscopio); un botón individual del 532 durante un nodo deja el nodo "interrumpido" igual que "Cerrar todos" |
| **BANCO-68** | ☐ abierto | Agregar a las mediciones: la escritura del estado del espejo en disco dentro del candado (si supera 10 ms, sale del candado), la creación de las tareas DO/AO en la ruta de falla, y la creación de la tarea AI finita de la lectura (decide si se crea antes de abrir, §5.1) |
| **BANCO-69** | en suspenso | BS a baja potencia; no se usa en este diseño (H16) |
| **BANCO-70** | ☐ abierto | Sin cambios: es la base sobre la que se monta la parada |

**Ítem nuevo que propongo:**

| ID | Qué valida | Procedimiento | Aceptación |
|---|---|---|---|
| **BANCO-71** | La llave del láser como **única** parada física ([INV-R4] 14), porque el banner la nombra | Anotar dónde está la llave de cada láser (532, 637, 592, 808) y si se alcanza desde la silla del operador; cronometrar el corte; anotar si al volver a encender hay que esperar estabilización o realinear | El manual y el banner nombran la llave correcta de cada láser. Si alguno no tiene llave o no se alcanza, se discute un corte físico (pulsador en la alimentación) en otra ronda |

Todos con los láseres **apagados**, salvo `BANCO-65`.

---

## 8. Tests en `SAFE_MODE` que el diseño exige (para la estrategia de la Ronda 2)

Con el `nidaqmx` falso de `DEC-036`, que registra cada escritura DO/AO con su hilo, y con mutaciones:

| # | Test | Mutación que lo tiene que hacer fallar |
|---|---|---|
| T1 | Un hilo retiene `_nidaq_lock` sin soltarlo: `trigger()` vuelve en < 50 ms; `open_shutter` después devuelve `False` sin escribir; el cerrador publica "placa tomada" a ≈ 0.25 s y confirma al soltarse el candado | `request_emergency_stop` que toma `_nidaq_lock`; quitar el chequeo previo al candado |
| T2 | Escritura fallida con nada abierto: `close_all_shutters()` → `False`, el 532 sin confirmar, `_retry_due` armado, `_all_closed_confirmed()` → `False`, Rearmar deshabilitado | volver a marcar sólo los creídos abiertos |
| T3 | Apertura en vuelo: el hilo A `open_shutter(expected_epoch=e)` espera el candado; el hilo B `request_close_all`; al soltar, A devuelve `False` y el log DO no tiene ninguna escritura "abrir" posterior a la de cierre | subir la época después del candado; comparar la época fuera del candado |
| T4 | Durante la parada `heartbeat_shutter()` no arma el plazo; el reintento de un cierre sin confirmar sigue | quitar la condición del latido |
| T5 | Después del `trip`, `pi.MOV`, `MVR` y `WGO` devuelven `False` sin llegar a `_dev`; no hay `_stage_fault`; `_MockPI` igual | quitar la retención en `MOV`, o sólo en el mock |
| T6 | Satélite: parada desde PySpectrum → la apertura de una rutina de PyPrinting devuelve `False` y la grilla no mueve; un solo Rearmar | conservar el `close_all_shutters` propio de `hardware_session` sin `trip` |
| T7 | Después de la parada, `up_flipper` llega **después** de la escritura de cierre en el log; `open_shutter(require_low_power=True)` antes de 100 ms del pulso → `False`, después → `True`; sin pulso desde el arranque → `False` | anotar `_flipper_low_since` al importar; poner el pulso antes del cierre |
| T8 | "Cerrar Todos" con escritura fallida: las casillas no se desmarcan, aparece el banner rojo; con éxito, se desmarcan al llegar el resultado | desmarcar antes del resultado |
| T9 | Segundo "Cerrar todos" durante la espera: no pausa; la primera apertura de la grilla llega ≥ 3 s después del segundo cierre | no reiniciar la espera |
| T10 | Lectura a baja potencia: orden del log (pulso *up* → lectura con el obturador cerrado → apertura ≥ 100 ms después → lectura finita creada y cerrada en `finally` → cierre); un cierre del operador durante L7 da "no sé"; un `read` que falla igual cierra el obturador | sacar el `finally`; no comparar la época en L9 |
| T11 | El invariante de [DA] §8.3 (cada forma de corte × cada etapa): ninguna apertura exitosa después del corte sin acción del operador, salvo la que permite P-H después de la espera | — |

---

## 9. Preguntas para el investigador

**Q-1. Cuando la placa no acepta una escritura, ¿qué obturadores se muestran "sin confirmar"?**
- (a) Los que se creían abiertos **y siempre el 532**, porque es activo en BAJO: si la placa se
  reinició, su línea sin manejar cae a BAJO, que es abierto (`BANCO-16`).
- (b) Los cuatro.
- (c) Sólo los que se creían abiertos (como hoy): con nada abierto, el software dice "cerrado"
  aunque la placa no haya contestado.
- **Recomiendo (a).** Es exacto según la polaridad. (b) llena el banner de avisos falsos para tres
  líneas que sin manejar quedan cerradas. Si `BANCO-16` muestra que el servo del 532 queda cerrado
  con la línea sin manejar, se revisa.

**Q-2. Durante una parada, ¿se puede mover la platina a mano?**
- (a) No: ningún movimiento (de rutina ni manual) hasta Rearmar. Conectar y desconectar sí.
- (b) Sólo se retienen los movimientos de las rutinas; los manuales siguen.
- **Recomiendo (a).** Es una sola regla, se prueba en un lugar del driver, y Rearmar cuesta un clic
  cuando todo está quieto. Para (b) el driver tendría que distinguir quién pidió el movimiento.

**Q-3. Sin el BS, ¿se usa el fotodiodo de detección como testigo indirecto del filtro en la lectura a
baja potencia?**
- (a) Sí: si el primer bloque de 20 ms da un nivel mayor que k veces la base de baja potencia de la
  sesión (k entre 2 y la atenuación del filtro, por ejemplo 3), se cierra en el acto, el nodo queda
  "no sé" y la grilla pausa. Sólo si `BANCO-65` da una atenuación ≥ 10.
- (b) No: el filtro trabado queda como riesgo registrado hasta habilitar el BS.
- **Recomiendo (a).** Usa un sensor que ya está habilitado, baja la exposición a alta potencia de un
  filtro trabado de ≈ 0.2 s a ≈ 0.1 s por lectura, y además avisa que el autofoco siguiente sería a
  alta potencia. No reemplaza al BS: con el espejo abajo no ve nada.

**Q-4. Un segundo "Cerrar todos" no pausa. ¿Desde cuándo se cuentan los 3 s para reabrir?**
- (a) Desde el **último** cierre: la espera se reinicia.
- (b) Desde el primero: la grilla puede reabrir menos de 3 s después del segundo cierre.
- **Recomiendo (a).** Es la regla de los 3 s aplicada al cierre que el operador acaba de hacer, y no
  convierte el segundo cierre en una pausa.

---

## Veredicto

- **Código actual** (después de `DEC-041`): la Pausa quedó resuelta, pero siguen dos defectos de
  hardware que R4-17 tiene que corregir:
  - una escritura de cierre fallida sin obturadores "creídos abiertos" no deja nada sin confirmar, y
    "Cerrar Todos" desmarca antes de escribir e ignora el resultado (§1.7, §1.8);
  - la E-STOP de PySpectrum no bloquea las aperturas ni los movimientos del satélite (§3).
- **Diseño de este documento: `HARDWARE_SAFE`**, con estas condiciones:
  1. estado de parada sin candado (`core/estop_state.py`), consultado por `open_shutter` antes y
     dentro del candado, y cierre desde un hilo propio con candado de plazo, sin escritura sin
     candado;
  2. regla de escrituras fallidas con el 532 siempre en riesgo;
  3. época de cierre por línea, que las aperturas de la grilla pasan y `open_shutter` compara dentro
     del candado;
  4. 100 ms de filtro garantizados en quien abre, con el pulso confirmado como referencia;
  5. ningún comando nuevo a la platina y una retención de movimiento en el driver;
  6. un filtro de teclas y un coordinador por proceso, con un solo Rearmar;
  7. `BANCO-16`, `-66`, `-67` y `-68` antes de usar la parada con los láseres encendidos, y `BANCO-65`
     antes de la lectura a baja potencia.
- **`TIMING_HAZARD`** mientras el fin del autofoco y la escritura a disco del criterio corran en el
  hilo GUI: la parada por teclado puede llegar hasta ≈ 1.2 s tarde (§6.2).
