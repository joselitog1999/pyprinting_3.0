# PySpectrum 3.0, bloque A: Ronda 4, reconciliación de contratos motor ↔ GUI

**Fecha:** 2026-09-28.
**Entradas:**
- el motor aprobado en la Ronda 2 (`../pyspectrum_A_ronda2/`);
- el diseño de la Ronda 3 (`../pyspectrum_A_ronda3/gui_design.md`: 64 controles en §6.1, discrepancias D-01 a D-17 en §6.2);
- la auditoría (`../pyspectrum_A_ronda3/qa_ux_audit.md`: H-01 a H-34, D-18);
- las decisiones del investigador R4, R4-A, R4-B, R4-C y R4-D (`../RESPUESTAS_INVESTIGADOR.md`).

**Regla** (CLAUDE.md §5, Ronda 4): no se escribe el código de un paso mientras quede abierta una discrepancia que ese paso consume. Esta tabla cierra las 21 filas (D-07 y D-09 van partidas, y se suma D-18).

## 1. Discrepancias resueltas

| ID | Resolución | Fuente de la decisión | Paso |
| :-- | :--- | :--- | :-- |
| D-01 | Un solo contrato: `AutoCalibrationPlan(configs: tuple[OffsetCalibrationConfig, ...], reference_mode: Literal["notch_leak", "attenuated_no_notch"], operator_confirmed: frozenset[str])`, con los nombres de `metrology`. `operator_confirmed` incluye `"notch_at_input"` y `"detection_mirror_down"`, que el software no puede sensar | diseñador + R4-D-1 (el notch lo pone el operador) | 14 |
| D-02 | `CAL_EXPOSURE_S = 0.10` fijo y `CAL_MAX_DURATION_S = 600` para la rutina completa, en `config.py`. Si se alcanza el tope: se detiene, cierra el 532 y registra `CANCELADA` con el resultado parcial | **R4-D-4** | 14 |
| D-03 | Un enum `CalibrationVerdict`: `ACEPTADA`, `ACEPTADA_CON_RESERVA`, `RECHAZADA`, `EN_SECO`, `CANCELADA`. Ninguno dice "validado" | diseñador + auditor (H-24) | 9, 14 |
| D-04 | `kind = "SOFTWARE_CORRECTION"`, con el `record_id` de la calibración de origen. Se guarda **aparte** del eje λ, como metadato. Al arrancar se aplica sólo si coinciden offset, serie, puertos y geometría; si no, queda suspendida y se avisa | **R4-C-6** + diseñador §4.6 | 9 |
| D-05 | `retry_arrival(seed_px, search_range_px)` y la bandera `SEEDED_BY_OPERATOR` | diseñador (no bloquea) | 14 |
| D-06 | En orden cero, la saturación **avisa y no aborta**, con la escala de H-21 para no producir fatiga de alarma. La ganancia EM bloqueada en 0 protege el detector | auditor + R4-C-1 (se mira con 0.1-0.5 s) | 7 |
| D-07a | Umbral especular = `(1 + SPECULAR_MARGIN_FRAC) · W/2`, con `SPECULAR_MARGIN_FRAC = 0.10`: 56.7 nm con la red de 150 y 6.4 nm con la de 1200. Los tooltips usan la misma fórmula. BANCO-42 lo mide | los números de `instrumentation`, con el texto corregido | 7 |
| D-07b | `THIRD_CONFIRMATION_STEPS = 50`, en el contrato de `OffsetWriteTransaction`. El diálogo muestra el cambio estimado en nm | **R4-B-10** | 10 |
| D-07c | **Sin tope rígido de offset en el driver**: se quitan los 2000 pasos absolutos y los 300 por escritura. La protección es la transacción | **R4-B-10** (H-07) | 5, 10 |
| D-08 | `enter_specular(target, restart_live)`, la firma de `instrumentation` | diseñador | 7 |
| D-09a | `StepGlueRequest.grating: int`, leído del snapshot. El preflight comprueba que no cambió | diseñador | 11 |
| D-09b | **Sale `light_source` del contrato.** La rutina renueva el latido mientras `get_open_shutter_names()` no esté vacío, y registra por ventana qué láseres estaban abiertos. No abre ningún obturador | **R4-B-5, R4-C-3** (H-03) | 11 |
| D-10 | `MirrorBelief.source = "operator_confirmed"` y `confirm_detection_mirror_belief("down")` en `core/nidaq.py` | diseñador (C-08) | 11 |
| D-11 | `StepGlueRequest.em_gain: int`, en unidades DAC, tomado del panel y mostrado en el preflight. Si el barrido cruza la λ de un láser abierto con ganancia > 0, se avisa (H-06) | diseñador + auditor | 11 |
| D-12 | `SpectrographWorker.requestSlit` y `requestPorts`, con "Moviendo…" igual que Ir | diseñador + auditor | 8 |
| D-13 | `CameraControlService`: `set_temperature`, `set_cooler` y `set_fan_mode` (low/high, R4-A-6), con relectura y aplicados entre adquisiciones | diseñador + auditor | 8 |
| D-14 | La lista blanca del arranque incluye `SetPreAmpGain` (el SDK lo exige, p. 16) y `SetHSSpeed`, elegida **por valor**: 13 MHz, modificable dentro de lo que ofrezca la cámara | **R4-B-8** + SDK (H-08) | 8 |
| D-15 | `ReadStatus.SENT_OK` para los **seis** parámetros sin getter: modo de lectura, modo de adquisición, ventilador, modo de ganancia, índice de VS e índice de HS. La GUI los marca [E] | auditor (SDK pp. 146-147) | 8 |
| D-16 | `StepGluePlan.estimated_duration_s` y `exposureProgress(float)` por tramo | diseñador (no bloquea) | 11 |
| D-17 | `StepGlueWorker.resume()` y el estado `PAUSED_NO_SIGNAL`. La pausa sigue renovando el latido si hay láseres abiertos (H-04) | diseñador + auditor | 11 |
| D-18 | En condición especular **no hay tope de exposición**. `set_exposure_time` deja de recortar, y el interlock especular actúa sólo sobre la ganancia EM. Al entrar al orden cero se fija la exposición recordada de ese modo; la primera de la sesión es `SPECULAR_DEFAULT_EXPOSURE_S = 0.1` | **R4-C-1, R4-D-2** | 7 |

## 2. Decisiones del investigador que agregan contrato

- **Exposiciones recordadas (R4-D-2).** `SpectrometerSession.exposure_by_mode = {"specular": 0.1, "first_order": <el último del operador>}`. Cada una se restituye al cambiar de modo; la ganancia no se restituye.
- **Restituir la ganancia con un láser abierto (R4-D-1, H-05).** El botón pide confirmar "notch puesto a la entrada", porque el software no puede sensarlo.
- **Escritura fallida (R4-D-3).** Si la relectura falla o no coincide, `OffsetWriteTransaction` entra en `MISMATCH` y ofrece "Volver al valor del respaldo". Esa vuelta es una transacción completa nueva, con `source_record_id` del respaldo. Es el único camino que escribe un valor del historial, y no hay ningún "restaurar desde el historial" en la GUI (R4-C-4, H-18).
- **Una escritura por confirmación (R4-C-5).** La calibración automática nunca escribe dentro del lazo. Cuando termina, propone un valor, y escribirlo es una transacción aparte.
- **Láser con el filtro de densidad en alta, en especular (R4-C-2).** Se avisa y no se bloquea.

## 3. Correcciones de la auditoría sin decisión pendiente

| ID | Corrección | Paso |
| :-- | :--- | :-- |
| **H-01 (CRÍTICA)** | La E-STOP funciona con cualquier diálogo abierto, y cada diálogo modal nuevo lleva además un botón E-STOP conectado a la misma acción. **Corrección de la propuesta del auditor:** pasar los atajos a `ApplicationShortcut` **no alcanza**. Se verificó que Qt bloquea los atajos de una ventana tapada por un modal en cualquier contexto. Se implementó un filtro de eventos de aplicación (`_EmergencyKeyFilter`) que dispara la E-STOP una vez por pulsación, sólo desde la ventana de PySpectrum o sus diálogos modales | **hecho** (DEC-040) |
| H-02 | `Ctrl+R` no inicia la calibración | 14 |
| H-05 | Ver R4-D-1 arriba | 7 |
| H-06 | Aviso si el barrido cruza la línea de un láser abierto con ganancia > 0 | 11 |
| H-18 | Un solo camino de vuelta, el de R4-D-3; se borra la "restauración al cancelar" de §4.2 | 10 |
| H-21 | Escala de saturación sin fatiga de alarma | 7 |
| Contraste | El texto gris `#6c7086` pasa a `#a6adc8` | 8 |

El resto (H-09 a H-33) son ajustes de texto y disposición. Se aplican en el paso que corresponde, según `qa_ux_audit.md` §7.

## 4. Orden de implementación

Actualizado para bajar primero el riesgo del primer arranque:

1. ✅ **H-01 / C-30: E-STOP a nivel de aplicación** (hecho, DEC-040).
2. ✅ **Paso 5: métodos de driver** (hecho, DEC-040). Incluye:
   - C-05: códigos de modo de lectura del SDK, p. 305;
   - C-06: `SetAutoSlitWidth` / `GetAutoSlitWidth`, como el legado, con `argtypes`;
   - C-07;
   - sin topes de offset (D-07c).

   Es el paso que hoy impide abrir PySpectrum 3.0 contra el equipo.
3. ✅ **Paso 6: `single_exposure`** (hecho, DEC-040). Nunca ceros; espera en tramos.
4. ✅ **Paso 4** (hecho, DEC-040): el tablero deja de reiniciar.
   - La reconexión es en el lugar, sobre la misma instancia, y queda rechazada con una sesión activa o con la E-STOP.
   - `refresh_status()` sólo lee, y hay avisos antes de reiniciar la cámara.
   - En lugar del `DeviceRegistry` completo se optó por la reconexión en el lugar, que da la misma garantía sin tocar 16 módulos.
5. ✅ **Paso 8:** estado base y servicio de estado (D-12 a D-15). Hecho (DEC-040): estado base al arrancar, instantánea leída con marcas, `CameraControlService` y panel leído/pedido. Pendiente: el `SpectrographWorker` en su propio hilo, que espera BANCO-39.
6. ✅ **Paso 7:** orden cero (D-06, D-07a, D-08, D-18). Hecho (DEC-040): red mínima en los drivers, servicio, panel, insignia y E-STOP con ganancia 0 releída.
7. ✅ **Pasos 9 y 10:** repositorio y transacción (D-03, D-04, D-07b, R4-D-3). Hecho (DEC-040): repositorio local fuera de git, observación al arrancar sin escrituras, transacción con respaldo y doble confirmación, dock de sólo lectura y diálogo de escritura. La corrección fina (SOFTWARE_CORRECTION, D-04) se aplica recién cuando la produzca el paso 14.
8. **Pasos 11 y 12:** Step & Glue y escaneo lineal (D-09 a D-11, D-16, D-17). ✅ Paso 11 hecho (DEC-040). ✅ Paso 12 hecho con R4-I: la luz como en Step & Glue, y cada rutina conserva su cosido.
9. ✅ **Paso 13:** satélite huésped y orden de cierre, con la platina a (50, 50, 10) (R4-B-6). Hecho (DEC-040): `HostContext` y `release_as_guest` en `app.py`, y `ShutdownCoordinator` con una sola pregunta. Con R4-J: el espejo se baja al cerrar y el contrapropagante también es huésped.
10. ✅ **Paso 14:** calibración automática (D-01, D-02, D-05). Hecho (DEC-040) en modo SÓLO MEDIR: estimador, rutina, corrección fina con su validez al arrancar y la sub-pestaña. La escritura espera a BANCO-40.

11. ✅ **AND-1:** rutinas de grilla (crecimiento, dímeros, luminiscencia y mapa hiperespectral) sobre los contratos del bloque A, con R4-K. Hecho (DEC-040). **Bloque A completo.**

Cada paso empieza por su test en rojo y termina con la suite completa y `graphify update .`. Los manuales (`qa_ux_audit.md` §6) se corrigen en el paso que cambia cada pantalla.
