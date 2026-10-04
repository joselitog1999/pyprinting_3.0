# R4-17 fase 4c — Conciliación del contrato del motor con el de la interfaz

**Laboratorio:** Nanofotónica — INS-UNSAM / CONICET
**Ubicación:** `docs/evidence/auditoria_2026-09-27/c01_ronda4/ronda4_conciliacion_fase4c.md`
**Fuentes:**
- motor: `ronda2_architecture.md` §4.2-§4.4, §4.9, §5.2-§5.3; `ronda2_instrumentation.md` §1.4, §3;
- interfaz: `../c01_ronda3/gui_design_v2.md` §5.1, §5.2, §6.7 y §10.1;
- decisiones: `RESPUESTAS_INVESTIGADOR.md`, conciliación de la fase 4c (2026-10-03).

**Fecha:** 2026-10-03

Es el paso 1 de la Ronda 4 (`CLAUDE.md` §5): cada fila cruza lo que el motor expone con lo que la interfaz usa. Una
fila sin coincidencia exacta dice cuál manda y por qué.

## 1. Alcance

Entra lo que la parada necesita en la interfaz:
- los botones y el filtro de teclas;
- el banner y Rearmar;
- los controles de la grilla según su estado;
- "Cerrar todos" con la grilla corriendo: rótulo, tooltip, banner y cuenta regresiva;
- PySpectrum como parte de la parada del proceso;
- el satélite;
- la sesión de hardware de la grilla.

No entra el resto de `gui_design_v2.md`: el rediseño del panel de impresión, "Saltar nodo", los presets, la cola de
revisión y los glifos completos de §6.3.

## 2. Matriz

| # | Motor (firma y unidades) | Interfaz (qué la usa) | Coincide | Resolución |
|---|---|---|---|---|
| 1 | `EmergencyCoordinator.trigger(source: str) -> int` (generación); no bloquea | botones "■ PARADA DE EMERGENCIA · Ctrl+E · F12" (panel de impresión, barra de la ventana principal, dock de obturadores), "EMERGENCIA" chico en la traza, `Ctrl+E`/`F12`, el botón de PySpectrum | sí | la fuente es un `str` para el banner y el registro ("tecla", "PyPrinting", "PySpectrum") |
| 2 | el cierre lo hace el cerrador: primero el evento, después la escritura | v2 §5.1, pasos 1-2: "cierra desde el hilo GUI… después el interlock" | **no** | **manda el motor** (preconciliación §10, [DA] S2): el hilo GUI nunca espera la placa |
| 3 | `CloseResult(epoch, estop_generation, ok, t_written_mono, t_written_wall, error, lock_wait_s, attempts)` por `register_close_listener`, desde el hilo cerrador | banner: "escritura de cierre confirmada hh:mm:ss.mmm (los cuatro)" o "cortá la emisión con la llave del láser" | sí, con traducción | el puente Qt (`EmergencyBridge`) lo pasa al hilo GUI en una señal encolada. El texto "4 de 4 confirmados" de la v2 se reemplaza (preconciliación §10: "confirmado" = la placa aceptó la escritura) |
| 4 | — | plazo del banner: `CLOSE_CONFIRM_DEADLINE_S` = 0.5 s (2 × `ESTOP_LOCK_TIMEOUT_S`) | sí | vive en la interfaz (instrumentación §1.4): el banner no depende de que el cerrador informe |
| 5 | `rearm_check(gen) -> RearmCheck(ok, closer_confirmed, nothing_open, routines_quiescent, waiting_on: tuple[str], generation_current, reason: str)` | "Rearmar" habilitado sólo con `ok`; el texto muestra `reason` | sí | el puente lo consulta cada 100 ms durante `ESTOP_QUIESCENCE_TIMEOUT_S` = 12 s. Al vencer: "La rutina no respondió en 12 s: {waiting_on}. Reiniciá PyPrinting" (v2 §5.1 decía "el plazo de §6.6"; manda el motor, preconciliación §10) |
| 6 | `rearm(gen) -> (bool, str)` | el clic en "Rearmar" | sí | uno solo por proceso: el de PySpectrum y el de PyPrinting llaman al mismo |
| 7 | `runStateChanged(str)` con `GridRunState.value` ∈ {idle, running, paused, stopped, finished} | v2 §6.7: Play deshabilitado corriendo y detenida; Pausa sólo corriendo; "Next index" deshabilitado detenida; rótulo del estado | sí | el panel mapea los cinco valores; `finished` se trata como `idle` |
| 8 | `countdownSignal(int nodo, float hora_de_pared)` | cuenta visible "La grilla sigue con el nodo N en S s" | sí | la interfaz la descuenta con un `QTimer` de 200 ms; la hora es de pared (`time.time()`), en s |
| 9 | `nodeInterruptedSignal(int nodo, str causa, float s)` | banner Peach de 20 s si la causa es `operator` (v2 §5.2) | sí | otra causa no muestra este banner (la pausa y la parada tienen el suyo) |
| 10 | `coordinator.any_routine_running() -> bool` | rótulo "Cerrar todos · la grilla sigue" con una rutina corriendo; si no, "Cerrar Todos" | sí | el dock lo consulta con un `QTimer` de 500 ms (no conoce la grilla) |
| 11 | `coordinator.operator_close_all(source) -> int` (época); `nidaq.is_close_confirmed(epoch) -> bool` | "Cerrar todos" desmarca las casillas sólo con el cierre confirmado | sí | sincrónico hasta que "Cerrar todos" pase al cerrador (fuera de R4-17) |
| 12 | `install_emergency_key_filter(app, coordinator, pause_handler=None) -> EmergencyKeyFilter`, idempotente; `add_pause_handler(fn: Callable[[], bool])` | `F2` con alcance de aplicación (v2 §6.7): grilla corriendo → pausa; si no, deja pasar (el `QShortcut` de la traza la detiene, como hoy) | sí | la v2 pedía un `QShortcut` de aplicación en la principal; manda el filtro (preconciliación §10, N-1) |
| 13 | `ESTOP_KEYS = ((Key_F12, NoModifier), (Key_E, ControlModifier))` | `lab-invariants` §4 | sí | se agrega la fuente nueva con su verificación (`test_prompt_corpus_integrity`) |
| 14 | `HardwareSessionManager` como participante: `on_emergency_stop`, `is_quiescent`, `on_rearmed`, `is_running`; `is_emergency_stopped` = parada del proceso o su bandera heredada | botón E-STOP de PySpectrum → `trigger("PySpectrum")`; "Rearmar Sistema" → el `rearm` del coordinador; **sin `QMessageBox`** (respuesta 2) | sí | la cámara (abortar, ganancia EM a 0 releída) va en un hilo propio después del pedido de cierre; las pausas de los Live, en el hilo GUI con `QTimer.singleShot(0)`, fuera del filtro |
| 15 | `hardware_session.emergency_stop()` y `clear_emergency()` (API heredada) | el cierre ordenado de PySpectrum (`ShutdownCoordinator`), las rutinas y 96 usos en los tests | — | se conservan. `emergency_stop()` dispara la parada del proceso y espera, con plazo, el cierre y la cámara: es sincrónica, como hoy. `clear_emergency()` intenta el rearme con plazo. La interfaz nueva no las usa |
| 16 | la sesión de la grilla: `acquire_session("PyPrinting: grilla de …", auto_pause_live=True)` / `release_session(…, restore_live=True)` | Play de la grilla (en el hilo GUI, porque las pausas de los Live tocan widgets) | sí | se toma al arrancar y se suelta al terminar o al reiniciar (respuestas 3 y 4). Con la sesión ocupada por otra rutina, Play no arranca y avisa. Sólo si PySpectrum está en el proceso |
| 17 | la parada no libera la sesión de la grilla de PyPrinting | v2 no lo dice | — | `emergency_stop` libera la sesión de una rutina de PySpectrum (como hoy) y **no** la de la grilla (respuesta 3) |

## 3. Unidades y valores por defecto

| Valor | Unidad | Dónde | Expuesto |
|---|---|---|---|
| `CLOSE_CONFIRM_DEADLINE_S` = 0.5 | s | `core/ui/emergency_keys.py` | no |
| sondeo del rearme = 100 | ms | ídem | no |
| `ESTOP_QUIESCENCE_TIMEOUT_S` = 12 | s | `core/emergency_stop.py` | no |
| banner Peach de "Cerrar todos" = 20 | s | panel de impresión | no |
| refresco del rótulo de "Cerrar todos" = 500 | ms | dock de obturadores | no |

**Discrepancias de parámetros que quedan:** ninguna. Las tres filas que no coincidían (2, 5 y 12) las resuelve la
preconciliación aprobada en la Ronda 2.
