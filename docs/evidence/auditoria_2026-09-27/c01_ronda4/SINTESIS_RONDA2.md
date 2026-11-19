# C-01, Ronda 4 — Síntesis de la Ronda 2 de R4-17 (2026-10-02)

**Panel:** `ronda2_architecture.md` (arquitectura de software) y `ronda2_instrumentation.md` (instrumentación). Los dos trabajaron sobre `main` en `927e818` y no tocaron código ni hardware. Parten de la Ronda 1 (`SINTESIS_RONDA1.md`) y de las respuestas del 2026-10-01 (`RESPUESTAS_INVESTIGADOR.md`).

**Veredictos:**
- **arquitectura:** el código actual tiene `CONCURRENCY_RISK`. El diseño es `CLEAN_ARCHITECTURE`, con dos condiciones: la línea de base dorada se graba antes de tocar nada, y la fase 2 entra sola;
- **instrumentación:** `HARDWARE_SAFE` con condiciones. Mientras el fin del autofoco y el criterio sigan en el hilo GUI, queda `TIMING_HAZARD`: una parada por teclado puede llegar ≈ 1.2 s tarde.

## 1. Lo que acuerdan los dos paneles

- **Toda la cadena de la grilla pasa a `confocalThread`.** Es la condición previa de todo lo demás.
  - Se quitan los dos despachadores que hoy corren en el hilo GUI: `app.py::_on_autofinish` y `app.py::_dispatch_trace`.
  - En su lugar van slots de cada worker.
  - Así corría el legado (`printing2/PyPrinting_UNSAM.py:416-427`).
  - El criterio es la misma función con los mismos datos. Lo controla un test dorado, que exige decisiones, índice de tick y log DO idénticos a los de `927e818`.
  - **Hallazgo nuevo, sin probar:** con el criterio en el hilo GUI, un tick encolado después de la decisión podría decidir dos veces el mismo nodo. Avanzaría `i_global` dos veces y movería la platina con el nodo siguiente abierto. La fase 0 lo mide.
- **La parada:**
  1. **En el hilo GUI, sin candado y en menos de 1 ms:** un evento con número de generación, la época de cierre de las cuatro líneas, las banderas de alto de cada rutina (por llamada directa) y un banner no modal.
  2. **En un hilo cerrador, uno por proceso:**
     - toma `_nidaq_lock` con plazo de 0.25 s (provisorio, lo fija BANCO-68);
     - activa el interlock "E-STOP" y escribe las cuatro líneas con su polaridad: el 532 en ALTO en `line11`, las otras en BAJO;
     - hace hasta 3 intentos y, si no confirma, reintenta cada 0.25 s sin límite, siempre con el candado.
  3. **"Confirmado"** es la escritura del cerrador con la generación vigente, no `_all_closed_confirmed()`.
  4. **El banner "cortá con la llave del láser"** lo levanta la GUI a los 0.5 s si no hay confirmación.
- **Durante la parada:**
  - `open_shutter` rechaza la apertura: mira la parada antes del candado y otra vez adentro;
  - `heartbeat_shutter` no hace nada;
  - `_PIController.MOV`, `MVR` y `WGO` devuelven `False` sin escribir por USB, y lo mismo el simulador. **No se envía `STP` ni `HLT`.**
- **Los ≈ 100 ms de baja potencia** (pregunta 4 de la Ronda 1):
  - `up_flipper` anota el momento sólo después de un pulso confirmado;
  - el que abre después espera lo que falte de los 100 ms;
  - las aperturas de baja potencia de la grilla piden `require_low_power=True`, que `open_shutter` verifica dentro del candado.
- **La época de cierre:**
  - hay un contador por línea, que suben los cierres del operador, la parada, el watchdog, los interlocks y las fallas de la platina; los cierres propios de las rutinas no lo suben;
  - la grilla abre con `expected_epoch`, y una apertura con una época vieja se rechaza sin escribir;
  - la grilla adopta la época nueva sólo con Play, o al terminar la espera de 3 s después de un cierre del operador;
  - la traza deja de reabrir en modo grilla.
- **"Cerrar Todos" deja de mentir:**
  - una escritura fallida marca como sin confirmar las líneas que podían quedar abiertas;
  - el botón ya no desmarca antes de escribir y mira el resultado;
  - los botones individuales del dock suben la época de su línea. Sin esto, apagar el 532 durante un nodo reproduce N-4 por otro camino.
- **El modo satélite:**
  - un único filtro de teclas para todo el proceso, en `core/`;
  - un único `EmergencyCoordinator`, con un Rearmar común;
  - la E-STOP de PySpectrum pasa por él;
  - la grilla del satélite se frena por tres barreras independientes: su bandera, el rechazo en `open_shutter` y la retención de la platina.
- **Lectura a baja potencia sin BS:**
  - **secuencia:** filtro arriba con el obturador cerrado → oscuro de 100 ms → abrir → 100 ms en 5 bloques de 20 ms → cerrar;
  - **lectura:** una tarea finita de DAQmx por lectura, como en DEC-037; ≈ 0.3 s por nodo;
  - **queda apagada** hasta BANCO-65;
  - **riesgo:** sin el BS, el filtro no se puede verificar. Si quedara trabado en alta, el nodo recibiría ≈ 0.2 s a potencia de impresión. Ese riesgo ya existe hoy en cada autofoco.

## 2. Fases (cada una con su test que falla primero)

0. **Banco de pruebas de la cadena,** con hilos reales y `nidaqmx` y PI falsos. Graba la línea de base dorada sobre `927e818` y arma el esqueleto de la matriz de 6 cortes por 7 etapas. Es exenta: sólo tests.
1. **"Cerrar Todos" y `close_all_shutters` dejan de mentir.**
2. **La cadena pasa a un solo hilo,** sin cambios de lógica, con el test dorado.
3. **Época de cierre, nodo "interrumpido" y espera de 3 s** con `legacy_timer`. `grid_trace_detect` también mira la Pausa: hoy una Pausa durante la exposición termina como "timeout" y el Healing Pass la reexpone.
4. **Parada y rearme:**
   - cerrador, coordinador, filtro de teclas y satélite;
   - el estado DETENIDA y el índice de reanudación calculado (reemplaza a `_detect_pending`);
   - el reenfoque si pasaron más de 60 s y el piso de 100 ms en baja potencia;
   - ningún `print` dentro de `_nidaq_lock`.
5. **Pasos entre nodos:** copia del estado antes del paso, restitución, y los topes provisorios (sin los que necesitaban el BS).
6. **Confirmación a baja potencia,** apagada hasta BANCO-65.

BANCO-70 (la Pausa en cada etapa) se corre después de la fase 2, porque antes validaría una topología que va a desaparecer.

## 3. Parámetros nuevos del motor

- **`core/nidaq.py`:**
  - constantes: `ESTOP_LOCK_TIMEOUT_S = 0.25`, `ESTOP_RETRY_INTERVAL_S = 0.25`, `OPERATOR_HOLD_S = 3.0` y `LOW_POWER_SETTLE_S = 0.10`;
  - tipos: `CloseCause`, `CloseEpoch` y `CloseResult`;
  - pedidos que no bloquean: `request_close_all(cause, detail="", hold_s=0.0) -> int` y `request_emergency_stop(source) -> int`;
  - `close_all_shutters(cause=ROUTINE, detail="")`: con valores por defecto, así que ningún llamador cambia;
  - `clear_emergency_stop(generation) -> (bool, str)`;
  - `open_shutter(..., expected_epoch=None, require_low_power=False)`.
- **`core/emergency_stop.py`:** el `EmergencyCoordinator`, `RearmCheck` y `ESTOP_QUIESCENCE_TIMEOUT_S = 12.0`.
- **`core/ui/emergency_keys.py`:** el filtro de `F12`, `Ctrl+E` y `F2` para todo el proceso.
- **`core/grid_state.py`:**
  - `GridRunState` (IDLE, RUNNING, PAUSED, STOPPED, FINISHED);
  - `RESUME_REFOCUS_AFTER_S = 60.0`;
  - `StepSnapshot`, `CAUSE_POLICY` y `compute_resume_index(...)`.
- **`core/step_plausibility.py`** (`StepLimits`, provisorios) y **`core/confirm_read.py`** (`ConfirmConfig(enabled=False, read_ms=100, block_ms=20, ratio_seen_min=1.20, …)`).

El detalle, con los diagramas de doble carril, está en `ronda2_architecture.md`; los tiempos, en `ronda2_instrumentation.md` §6.

## 4. Preguntas para el investigador (cada una con la recomendación del panel)

1. **¿La Pausa sigue la misma regla de reanudación que el rearme?** Es decir, primer nodo nunca expuesto y el cortado a revisión, en lugar del "¿Reimprimirlo?" de `gui_design_v2.md` §6.7 y de DEC-041. Cambia un test de DEC-041. **Recomendado: sí.**
2. **Un segundo "Cerrar todos" durante la espera de 3 s:** (a) la espera vuelve a 3 s desde el último cierre, o (b) cuenta desde el primero. **Recomendado: (a).** No pausa, como ya decidiste.
3. **Después de una escritura fallida, ¿qué líneas quedan "sin confirmar"?**
   - (a) las que se creían abiertas, más el 532 siempre. Es activo en BAJO: si la placa se reinicia, su línea cae a BAJO, que es abierto;
   - (b) las cuatro;
   - (c) sólo las que se creían abiertas, como hoy.

   **Instrumentación recomienda (a); arquitectura, (b).** Las dos son seguras. La (b) deja más reintentos y avisos.
4. **¿Hasta Rearmar se bloquean todos los movimientos de la platina, también los manuales?** La alternativa es bloquear sólo los de las rutinas. **Recomendado: todos.**
5. **Si el filtro no confirma el paso a baja potencia** (`up_flipper` devuelve `False`): ¿se pausa la grilla? **Recomendado: sí.**
6. **Verificación indirecta del filtro con el fotodiodo de detección,** mientras el BS no esté habilitado. Si el primer bloque de 20 ms de una lectura a baja potencia lee más de ≈ 3 veces la base de baja potencia de la sesión: cerrar, "no sé" y pausar. Sólo si el filtro atenúa al menos 10 veces (BANCO-65). **Recomendado: sí.** La alternativa es dejar el riesgo asentado.
7. **¿La E-STOP de PySpectrum pasa a ser la parada de todo el proceso,** también con PySpectrum solo, y bloquea las aperturas hasta Rearmar? **Recomendado: sí.**
8. **¿La grilla de PyPrinting toma la sesión de hardware** (`hardware_session`) mientras corre, para que una rutina de PySpectrum no pueda arrancar en el medio? **Recomendado: sí.**
9. **¿Cuál es la base de la confirmación sin BS?** La recomendación es la meseta previa a la captura, dividida por la atenuación del filtro medida en la sesión. Queda sujeta a BANCO-65 A y a una revisión de metrología antes de habilitarla. **Recomendado: esa.**

## 5. Banco

- **Agregados:**
  - BANCO-66: el pulso del filtro en `ao0`;
  - BANCO-68: un `print` con la consola de Windows en modo selección, por si deja el candado tomado.
- **Precondiciones:** BANCO-16 y BANCO-30.
- **Nuevo, BANCO-71:** la llave del láser como única parada física: dónde está, cuánto tarda en cortar y cómo se recupera después.

Se asientan en `PRUEBAS_BANCO_PENDIENTES.md` con las respuestas.
