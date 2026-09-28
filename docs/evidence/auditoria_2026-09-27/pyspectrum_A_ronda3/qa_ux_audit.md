# PySpectrum 3.0, bloque A — Ronda 3 (segunda mitad): auditoría QA/UX del diseño de GUI

- **Fecha:** 2026-09-28. **Agente:** `qa-ux-auditor`. **Ronda:** 3 ("Human-in-the-Loop", `CLAUDE.md` §5).
- **Objeto auditado:** `gui_design.md` (esta carpeta), §0-§9, propuesto por `scientific-gui-designer`. No se rediseña: cada hallazgo trae la corrección mínima.
- **Contraste:** `RESPUESTAS_INVESTIGADOR.md` §R4, §R4-A, §R4-B y **§R4-C** (respuestas del investigador a las Q1-Q6 del diseño, llegadas durante esta auditoría); `../pyspectrum_A_ronda2/` (README, `software_architect.md` §2.6-§2.10, `instrumentation.md` §2-§7, `metrology.md` §4-§5); DEC-040; código actual (`pyspectrum/window.py`, `docs/MANUAL_USUARIO.md` §4, `docs/modulos/MOD-06_*.md`).
- **Método:** Graphify (`graphify query`) para orientarse; lectura del diseño, de los contratos de la Ronda 2 y de los puntos del código que el diseño cita. Nada contra hardware. Sin código de producción.
- **Fuentes nuevas de esta auditoría:** [SDK p.146-147] índice alfabético de funciones de `atmcd`: después de `GetCurrentCamera` viene `GetCurrentPreAmpGain` y luego `GetCYMGShift`; **no existe `GetCurrentHSSpeed` ni `GetCurrentVSSpeed`** (leído en `docs/bibliografia/Software Development Kit.pdf`). [V-código] `window.py:543-546`: los `QShortcut` de la E-STOP se crean con padre `self` y el contexto por defecto (`WindowShortcut`).

> Estado del documento: **completo** (§0-§9).

---

## 0. Veredicto en una línea

**`MINOR_UX_POLISH_NEEDED`, condicionado.** La arquitectura de la información está bien resuelta y cumple casi todo R4-B: un único control por acción peligrosa, lo leído separado de lo pedido, sin diálogo en el orden cero, escritura sólo por transacción. No hace falta rehacerla. Sí hay 1 hallazgo CRÍTICO y 9 ALTOS que se cierran con correcciones locales (dos de ellos, H-18 y H-34, salen de R4-C, que invalida el tope de 10 ms en orden cero y los caminos de restauración). **Tienen que cerrarse antes de que la Ronda 4 escriba los pasos 7, 8, 10, 11 y 14** (§7).

---

## 1. Tabla de hallazgos

Severidad: **CRÍTICA** = se pierde el acceso a la parada o hay un camino de irradiación o daño sin protección; **ALTA** = contradice una decisión vinculante, o puede dañar el detector o arruinar una medición en silencio; **MEDIA** = error probable del operador o rótulo engañoso; **BAJA** = pulido.

| ID | Sev. | Pantalla | Defecto | Corrección mínima |
| :-- | :-- | :--- | :--- | :--- |
| **H-01** | **CRÍTICA** | Todos los modales del bloque: escritura de offsets (§1.7), Reconectar (§1.12), espejo de Step & Glue (§1.9.1), cierre (§1.13) | El diseño promete la E-STOP "siempre a la vista" (§1.1-4), pero agrega cuatro modales que la tapan. Con un `QDialog` modal activo, el botón de la barra no recibe clics, y `Ctrl+E`/`F12` no disparan: son `QShortcut` de contexto `WindowShortcut` sobre la ventana principal (`window.py:543-546`), que no es la ventana activa. En la escritura de offsets la torreta puede girar (R2-inst §3.1) y el diálogo puede quedar abierto 60 s. | (a) `Ctrl+E` y `F12` con `Qt.ShortcutContext.ApplicationShortcut`. (b) Cada modal del bloque lleva un botón E-STOP rojo en su propia barra, conectado al **mismo** `QAction` (principio §1.1-2). (c) Prueba S-01 (§5.1). El defecto ya existe hoy (`closeEvent`, `ZeroOrderSafetyDialog`), pero el diseño nuevo no puede heredarlo. |
| **H-02** | ALTA | Atajos (§3.6) | `Ctrl+R` pasa a "Iniciar calibración" en la pestaña Calibraciones. La calibración **abre el obturador de 532** (R2-inst §4.1, K7), así que un atajo de teclado dispara irradiación láser. Es el caso "¿puede un Enter o un atajo disparar el láser?" de la lista de control. | `Ctrl+R` **no** inicia la calibración: sólo el clic en [Iniciar calibración]. En Step & Glue puede quedar, porque con H-03 la rutina no abre láseres. La tabla §3.6 y `lab-invariants` §4 lo dicen. |
| **H-03** | ALTA | Step & Glue, selector "Luz" (§1.9, T-SG-4, Q3) | R4-B 5 decidió que **la rutina renueva el latido** porque a veces hay un láser abierto, y R4-C 3 agrega que **ese obturador lo abre el operador, no la rutina**. El diseño proponía dos cosas que eso contradice: "con láser, la rutina lo abre" y "con lámpara, no renueva". Si el operador abrió el láser a mano y dejó "lámpara" marcado, el watchdog cierra el láser a los 30 s **en medio del barrido**. Las ventanas siguientes salen oscuras sin ningún aviso, lo que viola "el watchdog nunca corta una rutina sana". El README de la Ronda 2 ("sólo late si abrió él mismo un obturador") es anterior a R4-B 5 y quedó superado. | Regla única y sin selector: **la rutina renueva el latido mientras haya algún obturador láser abierto** (`get_open_shutter_names()` en cada tramo), sin importar quién lo abrió. El selector "Luz" se reemplaza por una línea de sólo lectura, "Láseres abiertos al iniciar: ninguno / 532", que queda en el metadato de cada ventana. Si ese conjunto cambia durante el barrido (se cerró o se abrió un láser), las ventanas siguientes llevan la bandera `LIGHT_CHANGED` y aparece un aviso amarillo en la tabla. La rutina nunca abre ni cierra un láser (R4-C 3). T-SG-4 se escribe con esta regla. |
| **H-04** | ALTA | Step & Glue, pausa "ventana sin luz" (§1.9.1, D-17); calibración, "Reintentar con la semilla" (§3.1, D-05) | Las dos rutinas quedan **pausadas esperando a una persona** sin que esté definido qué pasa con el latido. Si la rutina sigue latiendo, un láser queda abierto por tiempo indefinido y se anula la protección contra obturadores abandonados. Si deja de latir, el watchdog cierra el láser y, al pulsar [Seguir], la rutina sigue a oscuras. En la calibración el 532 está abierto por la propia rutina (K7). | Pausa = **no late**. [Seguir] vuelve a correr el preflight de luz: si falta un láser que estaba abierto al iniciar, bloquea con "el 532 se cerró durante la pausa: reábralo o cancele". En la calibración, `NO_LINE` **cierra el 532 y termina esa red** con el mensaje, en vez de esperar un clic con el láser abierto. La búsqueda por clic (D-05) se difiere fuera del bloque A. |
| **H-05** | ALTA | Pastilla "Restituir 150" al volver del espejo rápido (§1.4, T-ZO-3) | Uno de los usos del orden cero es ver el punto del láser para centrarlo en la ranura (R4-B 3), "con filtro de densidad **o** notch", así que puede hacerse sin notch. Al volver a primer orden, el láser abierto durante el orden cero sigue abierto y la pastilla pone la ganancia EM en 150 con **un clic**. Si el notch no está, la línea láser dispersada cae sobre una columna con ganancia EM alta. El software no puede leer el notch (R2-arq §2.7). | La pastilla muestra los láseres abiertos ("Restituir 150 · 532 abierto"). Si alguno de ellos se abrió durante el episodio especular y sigue abierto, restituir pide una confirmación de una línea en la misma pastilla ("Notch puesto: sí, restituir"), sin modal. Sin láser abierto, sigue siendo un clic. Pregunta P1. |
| **H-06** | ALTA | Step & Glue, preflight (§1.9.1) | El barrido usa la ganancia EM del panel (D-11) y puede cruzar la λ de un láser abierto (500-900 nm contiene 532, 592 y 637). No hay bloqueante ni advertencia para "ventana que contiene la línea de un láser abierto, con ganancia > 0". | Con H-03 aplicado, el preflight agrega un bloqueante: "La ventana 1 contiene 532 nm, el 532 está abierto y la ganancia EM es 150". Se resuelve bajando la ganancia a 0 o con una casilla "notch puesto (confirmo)" en la lista de advertencias. |
| **H-07** | ALTA | Diálogo de escritura (§1.7), D-07c | R4-B 10 decidió **sin tope rígido**. El diseño deja abierta la discrepancia ("preguntar a `instrumentation`"). Si los topes del driver quedan (2000 pasos absolutos y 300 por escritura, R2-inst §3.3), el operador pasa tres confirmaciones y recibe "ESCRITURA FALLIDA" (`SHAMROCK_P3INVALID`) sin saber por qué: es un fallo defensivo invisible. | Se aplica R4-B 10: salen del driver `OFFSET_ABS_MAX` y `OFFSET_STEP_MAX`. Quedan sólo los chequeos de validez: red ∈ {1, 2} y \|offset\| ≤ `SHAMROCK_GRAT_OFFSET_MAX` (20 000, rango del SDK, no una política). El `max_total_change_steps = 200` de `metrology` sigue siendo un **criterio de parada del lazo automático** (`reason = "limit_exceeded"`, que se muestra) y no se aplica a una restauración. Se informa a `instrumentation`; no hay nada que preguntar. |
| **H-08** | ALTA | Panel, fila "Velocidades" (§1.3, §2.2), D-14 | R4-B 8 fija 13 MHz por defecto, pero la lista blanca del arranque (R2-arq §6.2) no incluye `SetHSSpeed` ni `SetPreAmpGain`. Tal como está, el panel muestra "HS 13 MHz" mientras la cámara lee a la velocidad que dejó Solis o pylablib. El ruido de lectura de cada espectro guardado queda mal atribuido. | D-14 se resuelve como propone el diseño, con dos precisiones: la HS se elige **por valor** en la tabla de `GetHSSpeed`, y si 13 MHz no está en la tabla (BANCO-38) el campo va a `[!]` y no se adivina; el pre-amp va al índice 0 con relectura `GetCurrentPreAmpGain` [SDK p.147]. Bloquea el paso 8. |
| **H-09** | MEDIA | Panel, marcas de procedencia (§1.3) | El mockup marca `[L] VS 1.9 µs · [L] HS 13 MHz`, pero el SDK no tiene getter del índice vigente de HS ni de VS [SDK p.146-147; R2-inst §6.1: "no hay getter del índice vigente"]. Es exactamente el defecto G-01 que el diseño dice eliminar ("lo que se ve es lo leído"). D-15 agrega `SENT_OK` sólo para cuatro parámetros. | VS y HS van con `[E]`. D-15 cubre seis parámetros: modo de lectura, modo de adquisición, ventilador, modo de ganancia, índice VS e índice HS. El pre-amp sí puede llevar `[L]`. |
| **H-10** | MEDIA | Todos los `QSpinBox`/`QDoubleSpinBox` (§2.1-3) | El filtro de rueda cubre sólo los combos. El panel izquierdo tiene 300 px de ancho y grupos plegables, así que se desplaza con la rueda, y un spinbox bajo el puntero cambia el pedido en silencio. Ejemplos: exposición 0.05 → 0.4 s con "×2 por paso"; setpoint −60 → −59 °C; **λ_ref 532.000 → 532.003 nm** en Preparación, que corre la calibración entera. | El mismo filtro (sin foco no hay rueda) para todo spinbox de pedido de hardware y de parámetros de rutina. Si λ_ref ≠ 532.000, el spinbox se pinta de amarillo con "Δ = +0.003 nm del nominal". |
| **H-11** | MEDIA | Espejo rápido, `Ctrl+0` (§1.4, §3.6) | La semántica de alternar tiene huecos. (a) `QShortcut` repite con la tecla sostenida: dos disparos entran y vuelven. (b) `Ctrl+0` con "Moviendo…" en curso o con la sesión tomada por una rutina no está especificado. (c) En estado **desconocido**, que cuenta como especular, `Ctrl+0` intentaría "Volver". (d) Si el Shamrock arranca en orden cero (lo dejó Solis), no hay destino recordado. (e) La última opción elegida queda como acción principal en `QSettings`, así que `Ctrl+0` puede significar "red espejo" mañana: un atajo frecuente con estado oculto. | (a) `setAutoRepeat(False)`. (b) El `QAction` se deshabilita durante el movimiento y con la sesión tomada, con el motivo en el tooltip. (c) En estado desconocido, el control ofrece [Releer estado] y no se mueve. (d) Sin destino recordado, "Volver" pide red y λ en línea, sin modal. (e) `Ctrl+0` = **siempre** orden cero con la red actual (R4-A 3); la red espejo sólo desde el menú y sin quedar fija. |
| **H-12** | MEDIA | Espejo rápido, "si un paso falla" (§1.4) | Se ve el paso que falló, pero no **en qué estado quedaron** los recursos. Si Z4 falla (ganancia leída 12), Z2 ya detuvo la cámara y el Live quedó pausado; los obturadores no se tocaron (Z6 va después). El operador no sabe si el Live vuelve, si los láseres siguen abiertos ni si la sesión se liberó. | La lista de pasos cierra con el estado final de cada recurso: "red: no se movió · Live: detenido · obturadores: sin cambios (532 abierto) · ganancia: desconocida · sesión: libre". El Live no se reanuda solo si la ganancia no se confirmó. [Reintentar] rehace la secuencia desde Z1. |
| **H-13** | MEDIA | Espejo rápido, ida y vuelta (§1.4) | En el diseño, la exposición queda acotada al volver y hay que restituirla a mano, igual que la ganancia. Con R4-C 1 la exposición del orden cero **depende de la muestra** (0.1-0.5 s en Solis): el operador la va a ajustar en cada visita al orden cero y la va a tener que reajustar al volver. Son 2 a 4 acciones de más por ida y vuelta, en una acción que se hace **decenas de veces por sesión** (R4-A 3). R4-B 4 sólo exige que la **ganancia** no vuelva sola. | Dos exposiciones recordadas por sesión: la de orden cero (la primera vez, `config.SPECULAR_DEFAULT_EXPOSURE_S`, PROVISORIO; después, la última que usó el operador) y la de primer orden (la que había). Cada transición restituye la suya **sola**, y la pastilla queda sólo para la ganancia. La ida y vuelta típica cuesta 2 pulsaciones (`Ctrl+0` ×2), más 1 si había ganancia (§3). Pregunta P2. |
| **H-14** | MEDIA | Calibraciones, "Preparación" (§1.6) | Tres rótulos contradicen el contrato. (a) "CCD −60 °C estabilizada ✓" figura como paso que impide arrancar, pero K3 dice "aviso, no bloquea" (R2-inst §4.1). (b) "filtro de densidad en baja ✓" pone un ✓ a un **pulso enviado** (K4: "no es una medición"). (c) La casilla "espejo abajo" arranca **tildada** si la creencia es `down`: una confirmación pretildada no confirma nada, contradice "no se recuerdan" y se vuelve rutina. (d) En el modo "532 atenuado, sin notch" nada pide confirmar que el filtro de densidad está físicamente en baja. | (a) K3 en amarillo, sin bloquear. (b) "[E] filtro de densidad: pulso *baja* enviado (sin sensor)". (c) Se quita la casilla del espejo: se muestra la creencia y se confía en K8 (sin luz → cierra el 532 y aborta). (d) En el modo sin notch, la casilla dice "filtro de densidad en baja, verificado a ojo", además de "notch retirado". |
| **H-15** | MEDIA | Calibraciones, "Resultado por red" (§1.6, §4.4) | (a) El mockup muestra "EN SECO", el término que el propio diseño prohibió (§2.3); en la misma corrida en seco, una red dice CON RESERVA y otra EN SECO, y el operador no puede saber por qué. (b) El modo (sólo medir) y el veredicto metrológico comparten columna. (c) El "·" de K2 (que en este modo no aplica, R2-met §4.2) se lee como criterio fallido. (d) [Aplicar corrección fina] junto a "SÓLO MEDIR" se lee como "escribe al equipo". | (a) y (b) `EN_SECO` sale del enum de veredictos (es `dry_run = True`, D-03) y el modo va en una insignia aparte. (c) "n/a" en texto. (d) El botón se llama "Guardar corrección fina (sólo PySpectrum; no toca el Shamrock)". El rótulo del modo, en palabras: "SÓLO MEDIR: esta rutina no cambia nada en el Shamrock. Para escribir offsets falta medir cuántos píxeles corre un paso (prueba de banco BANCO-40)". |
| **H-16** | MEDIA | Calibraciones, exposición (D-02, §2.3) | Con el tope de 10 s de `metrology` (que cita R4-4, una decisión **para Raman**), una corrida de 25 llegadas × 5 cuadros × 3 λc × 2 redes dura del orden de horas con el 532 abierto [I: ≈ 6 s por llegada a 1 s, ≈ 16 min las dos redes; ×10 a 10 s]. Tampoco se muestra una duración estimada antes de iniciar. | Un símbolo, `config.CAL_MAX_EXPOSURE_S = 1.0`, PROVISORIO (R2-inst §4.5; se revisa con BANCO-50). `OffsetCalibrationConfig.exposure_max_s` lo toma de ahí. Preparación muestra "duración estimada: ≈ N min con el 532 abierto" antes de [Iniciar]. |
| **H-17** | MEDIA | Cierre (§1.13, §4.2) | El texto del cierre cubre la calibración en curso, pero no: (a) Step & Glue en curso, incluida una exposición de 10 s; (b) una transacción entre `confirm_write` y la relectura; (c) la platina no conectada o con el interlock armado ("la platina va a (50, 50, 10)" sería falso); (d) un `PRE_WRITE` sin `APPLIED` si el proceso muere a mitad de la escritura. | (a) "Barrido en curso (ventana 3 de 5): se detiene; las ventanas 1-2 ya están en disco". (b) Entre `confirm_write` y la relectura, el diálogo de escritura ignora `Esc`, `Alt+F4` y Cancelar. (c) El texto de la platina depende de su estado ("no conectada: no se mueve"). (d) Al arrancar, un `PRE_WRITE` huérfano genera una fila roja en la franja: "escritura del 14:31 sin confirmar: releído 85, respaldo 85". |
| **H-18** | ALTA | Caminos de restauración: menú del historial (§1.8), aviso de estado desconocido (§4.2), página 5 del diálogo (§1.7), §4.5 | R4-C 4: **no se restaura un offset desde el historial; para eso se recalibra.** El diseño tiene tres caminos de restauración. Además, §4.2 describe que, cuando la escritura se habilite, "el motor restaura O₀ y relee" al cancelar. Eso es una escritura automática sin su transacción, que contradice R4-C 5 ("una escritura por confirmación"), como también el lazo de 2 a 4 escrituras de `metrology`. | Sale "Restaurar este valor en el equipo…" del historial. En el aviso de estado desconocido y en la página 5 (NO COINCIDE o DESCONOCIDO), la acción ofrecida es [Recalibrar (Verificar)], con el aviso rojo persistente hasta la próxima relectura correcta. El lazo de calibración **nunca escribe** (como ya dice R2-inst §4.3): cada escritura sale de "Proponer offset…" con su transacción, y cancelar no restaura nada porque no se escribió nada. Si la vuelta inmediata al respaldo después de una escritura que no coincidió cuenta o no como "restaurar", es la pregunta P3. |
| **H-19** | MEDIA | Atajos: `Esc` = Stop de rutina (§3.6) | `Esc` es la tecla universal para descartar: cierra el desplegable de un combo, un menú, [Avanzado] o un tooltip. Con el foco en la pestaña, un `Esc` reflejo detiene un barrido de 9 min con la red de 1200. | Sin `Esc`. Stop sólo con el botón; la parada global sigue en `Ctrl+E`/`F12`. |
| **H-20** | MEDIA | Panel izquierdo (§1.3) | El mockup tiene filas de ≈ 95 caracteres, pero el ancho mínimo declarado es 300 px (≈ 45 caracteres a 9 pt). En la práctica el panel va a medir ≈ 600 px o va a partir las líneas, y le quita espacio a la imagen del Live, que es lo que se mira en el orden cero. | Las filas de Capa 0 (Lectura, Velocidades, Geometría y el detalle de offsets) pasan a un grupo "Detalles", plegado por defecto. Ancho objetivo de 360 px, verificado a 1920 × 1080 y a 1366 × 768 (S-18). |
| **H-21** | MEDIA | Orden cero, indicador de saturación (§1.4, D-06) | El uso para centrar el láser (R4-B 3), ahora con exposiciones de 0.1-0.5 s (R4-C 1), lleva la imagen **seguido** por encima del 50 % del ADC. Un indicador rojo casi permanente produce fatiga de alarma. Además D-06 (Z10 aborta frente a sólo avisar) sigue abierta y es una política de protección del detector de la Ronda 2. | Mostrar siempre "pico: N % del ADC": amarillo entre 50 y 80 %, rojo desde el 80 % (el tope de recorte de `check_saturation`, R2-met §5.1). D-06 la firma `instrumentation` antes del paso 7 (§2). |
| **H-22** | MEDIA | Paleta (§1.1-6, §3.3) | `#6c7086` sobre `#1e1e2e` da **≈ 3.4:1** [cálculo WCAG de esta auditoría], por debajo del 4.5:1 AA para texto chico, en un laboratorio a oscuras. Ese color se usa en **texto**: la línea "destino", la marca `[?]` y el rótulo "suponiendo imagen 1:1". | Para texto, `#a6adc8` (Catppuccin *subtext0*, ≈ 7.4:1); `#6c7086` sólo para trazos y decoración. Durazno con `#181825` da ≈ 9.9:1 y el rojo con texto claro está bien. Las insignias durazno, amarillo y rojo se confunden con deuteranopía: **siempre** con su palabra, como ya propone el diseño. |
| **H-23** | MEDIA | Botón por defecto en los modales (§1.7, §1.9.1, §1.12, §1.13) | No se especifica. Con el cierre, un Enter reflejo **mueve la platina** a (50, 50, 10) y apaga el enfriador. Con Reconectar, un Enter apaga el enfriador. En la página 2 de la escritura, un Enter confirma el diff. | Cierre y Reconectar: botón por defecto = Cancelar. Espejo de Step & Glue: Cancelar. Escritura: ningún `autoDefault` en las páginas 2 y 4 (en la 4 ya protege el número tecleado). |
| H-24 | BAJA | Unidades (§1.2, §1.3, §1.6) | Faltan unidades en varias filas: offsets "red 1: 85 · red 2: 0" y la franja "equipo 87, archivo 85" sin "pasos"; "media +2.38 · u_A 0.29" sin "px". | Sufijo de unidad en todo número mostrado (regla §2.1-1, extendida a las etiquetas). |
| H-25 | BAJA | Franja de avisos (§1.11) | "[Recordar al próximo inicio]" dice lo contrario de lo que hace: la oculta hasta el próximo inicio. | "Ocultar hasta el próximo inicio". |
| H-26 | BAJA | Franja de avisos (§1.2) | Se apila sin límite: tres o cuatro filas empujan el visor hacia abajo. | Como máximo 2 filas visibles, más "(+N avisos)" desplegable. |
| H-27 | BAJA | Panel, cámara (§1.3, §2.2) | El setpoint no tiene [Aplicar] y actúa con `editingFinished`, que también se dispara al perder el foco. El combo de HS no tiene [Aplicar] (contra la regla §2.1-2). "Apagar enfriador" es un clic directo, mientras que Reconectar, que tiene el mismo costo (minutos de reenfriado), lleva un diálogo. | [Aplicar] para setpoint y HS (la HS se aplica entre adquisiciones, porque `DRV_ACQUIRING` la rechaza). "Apagar enfriador" pide confirmación con la temperatura actual. |
| H-28 | BAJA | Referencias del diseño | (a) El tiempo de reenfriado se manda a "BANCO-45", que es "arranque sin escrituras". (b) Se usan IDs anteriores a la consolidación: BANCO-A3 → 48, A7 → 43, A5 → 51. (c) T-SPEC-1 cita las filas 119-121 de `lab-invariants` para el margen 1.1, que es [I]. (d) El reenfriado tiene que ir a la batería de banco (memoria *bench-pending-items*). | Corregir las referencias. El orquestador agrega un ítem nuevo a `PRUEBAS_BANCO_PENDIENTES.md`: "tiempo de reenfriado a −60 °C tras Reconectar". Esta auditoría no puede editar ese archivo. |
| H-29 | BAJA | Tablero, Reconectar (§1.12) | Si la cámara está `NOT_CONNECTED` (Solis abierto), el diálogo de "el enfriador deja de enfriar" no tiene sentido y enseña a aceptarlo sin leer. | Sin diálogo cuando el equipo no está conectado; sólo [Reintentar]. |
| H-30 | BAJA | Espejo rápido, lista de pasos (§1.4) | La lista se despliega dentro del panel y lo alarga: los controles de abajo (Ir, λ) se corren mientras el puntero está encima. | Espacio reservado de alto fijo, o un recuadro superpuesto que no desplace el panel. |
| H-31 | BAJA | Live con exposición larga (§2.2) | El driver acepta hasta 60 s (R4-B 9). Sin progreso de la exposición, el Live parece colgado. | La barra de exposición en curso de §1.9.2 también en el Live cuando la exposición es mayor que 1 s. |
| H-32 | BAJA | Preguntas del diseño (§7) | Q2 ya tenía respuesta en R4-B 3 ("abrir a voluntad") y Q3 en R4-B 5. Hoy las seis están contestadas en R4-C. | La Ronda 4 incorpora R4-C al diseño: §1.4, §1.7, §1.8, §4.2, §4.5, §4.6, T-SPEC-4, T-ZO-2, T-SG-4 y la verificación M-05 (ver H-13, H-18, H-34 y H-35). |
| H-33 | BAJA | Insignia "ESPECULAR" (§1.2) | Es jerga: el operador dice "orden cero" o "espejo". | "ORDEN CERO · sin dispersión", y en el tooltip, "condición especular". |
| **H-34** | ALTA | Espejo rápido y panel: tope de exposición en especular (§1.2 insignia "exp ≤ 10 ms", §1.4, §2.2, T-ZO-2, M-05, D-06) | R4-C 1: en orden cero la muestra se mira con **0.1-0.5 s** y no hay valor estándar, así que **el espejo rápido no impone 10 ms**; lo único fijo es la ganancia EM en 0. Con 10 ms, el espejo rápido mostraría una imagen oscura y el operador volvería a Solis, que es el riesgo principal que el propio diseño identifica (§9). El tope vive además en tres contratos de la Ronda 2: Z5 (R2-inst §2.2), el recorte del driver en especular (R2-inst §2.5-4) y el rechazo `EM_GAIN_INTERLOCK_REFUSED` de `set_exposure_time(t > tope)` (R2-arq §2.8). | La exposición en especular sale del interlock: Z5 pasa de "acotar" a "fijar `SPECULAR_DEFAULT_EXPOSURE_S` al entrar" (con el recuerdo de H-13), y el driver deja de recortar la exposición por condición especular (conserva el tope global de 60 s, R4-B 9). La insignia pasa a decir "ORDEN CERO · EM 0 bloqueada". T-ZO-2 se reescribe como tooltip de saturación (H-21). Es un cambio de un contrato de seguridad de la Ronda 2 que decidió el investigador: `instrumentation` lo registra (D-18, §2). |
| **H-35** | MEDIA | Corrección fina: T-SPEC-4, eje del Live (§1.5, §3.1) | R4-C 6: la corrección fina va **aparte**, como metadato con procedencia, y no dentro del eje λ; el dato crudo queda intacto. T-SPEC-4 dice "el eje queda λ(p) = λ_SDK(p + c)", que da a entender que el eje mostrado y guardado ya está corregido. | T-SPEC-4: "El eje guardado y el mostrado son los del SDK. La corrección va en el metadato de cada espectro (`c_sw_px`, convenio, `record_id`). Para aplicarla en el análisis: λ(p) = λ_SDK(p + c)". Si se ofrece una segunda fila de ticks "corregido" en el visor, va apagada por defecto y rotulada "vista, no se guarda". |

---

## 2. Discrepancias D-01 a D-17 del diseñador (y una nueva, D-18)

"Bloquea" = la Ronda 4 no puede escribir ese paso sin resolverla. La resolución es la mínima que deja coherentes GUI, motor y decisiones del investigador.

| ID | ¿Bloquea? | Paso | Evaluación | Resolución mínima |
| :-- | :-- | :-- | :--- | :--- |
| D-01 | **Sí** | 14 | Correcta. Dos contratos para una rutina son la receta de la discrepancia de parámetros que la Ronda 4 tiene que evitar. | La del diseñador: `AutoCalibrationPlan(configs: tuple[OffsetCalibrationConfig, ...], reference_mode, operator_confirmed)`, con los nombres de `metrology`. Con H-14, `operator_confirmed` ⊂ {`notch_in`, `notch_out_nd_low_visual`} y **sin** el espejo (lo cubre K8). |
| **D-02** | **Sí** | 14 | El 10 s de `metrology` cita R4-4, que es una decisión **para Raman**. Con 10 s la corrida duraría horas con el 532 abierto (H-16). | `config.CAL_MAX_EXPOSURE_S = 1.0`, PROVISORIO (R2-inst §4.5); se revisa con BANCO-50. `exposure_max_s` toma ese valor por defecto. La GUI muestra el tope y la duración estimada. |
| D-03 | **Sí** | 14 | La corrección va más allá de lo que propone el diseñador: `EN_SECO` no es un veredicto sino un modo. | Enum de cuatro: `ACEPTADA`, `ACEPTADA_CON_RESERVA`, `RECHAZADA`, `CANCELADA`. El modo va en `dry_run` y la GUI lo muestra como insignia aparte (H-15). |
| D-04 | **Sí** | 9 y 14 | Sin `kind` ni regla de validez, el arranque no puede decidir si aplica la corrección fina. R4-C 6 confirma que va como metadato. | `kind = "SOFTWARE_CORRECTION"` con el `record_id` de origen. Vale si coinciden el offset leído, el número de serie, los puertos y la geometría. Adoptar un valor del equipo ([Registrar lo leído]) **no** la reactiva. |
| D-05 | No | — | La búsqueda por clic pausa una corrida con el 532 abierto (H-04). No es necesaria para el bloque A. | Se difiere. En el bloque A, `NO_LINE` cierra el 532, termina esa red y lo informa. |
| D-06 | **Sí** (decisión) | 7 | Es coherente con R4-C 1: sin tope de exposición en especular, abortar en el primer cuadro saturado haría inútil el espejo rápido. | Avisar sin abortar, con la escala de H-21. La firma `instrumentation`, junto con D-18. |
| **D-07a** | **Sí** | 7 | El número que ve el operador tiene que ser el que usa el motor. Las dos fórmulas son provisorias (BANCO-42). 1.1 · W/2 deja ≈ 50 px de margen con las dos redes [I: 5.15 nm / 0.1026 nm/px y 0.58 nm / 0.01152 nm/px], de sobra para la imagen de una ranura de 100 µm (≈ 12.5 px si fuera 1:1). | Se conservan 56.7 / 6.4 nm, que ya están en el README, en `instrumentation` y en el diseño. Se corrige el texto: "margen del 10 % **sobre W/2**". Un símbolo, `config.SPECULAR_MARGIN_FRAC = 0.10`, rotulado PROVISORIO (BANCO-42). T-SPEC-1 lo marca como [I]. |
| D-07b | **Sí** | 10 | Correcta. | `config.THIRD_CONFIRMATION_STEPS = 50`. La transacción devuelve `needs_third_confirmation`, y la GUI no calcula nada por su cuenta. |
| **D-07c** | **Sí** | 10 | R4-B 10 ya decidió: sin tope rígido. No hay que preguntar a nadie (H-07). | Salen `OFFSET_ABS_MAX` y `OFFSET_STEP_MAX`. Quedan red ∈ {1, 2} y \|offset\| ≤ 20 000 (rango del SDK). El `max_total_change_steps` de `metrology` es un criterio de parada del lazo, no un tope de escritura. |
| D-08 | **Sí** (trivial) | 7 | Correcta. | La firma de `instrumentation`, con `target`. Con H-11(e), `Ctrl+0` siempre pasa `"zero_order"`. |
| D-09a | No | 11 | Útil para que el preflight detecte un cambio de red entre el plan y el inicio. | `grating: int`, tomado del snapshot. |
| D-09b | **Sí** | 11 | R4-B 5 y R4-C 3 la resuelven de otra forma: el latido no depende de un selector (H-03). | `light_source` sale del contrato. La rutina renueva el latido mientras `get_open_shutter_names()` no esté vacío, y registra el conjunto de láseres abiertos por ventana. |
| D-10 | **Sí** | 11 | Correcta; G4 no funciona sin eso. | `MirrorBelief.source = "operator_confirmed"` y `confirm_detection_mirror_belief("down")`. |
| D-11 | **Sí** | 11 | Hace falta para H-06: el preflight tiene que ver la ganancia del barrido. | `em_gain: int` en el request, tomado del panel y mostrado en el plan. |
| D-12 | **Sí** | 8 | Correcta: la ranura es un motor (0.8 s) y hoy la llama directo el panel. | `requestSlit` / `requestPorts` en `SpectrographWorker`, con "Moviendo…" igual que Ir. |
| D-13 | **Sí** | 8 | Correcta. | `CameraControlService` con relectura, aplicado entre adquisiciones. |
| **D-14** | **Sí** | 8 | Contradicción real entre `software-architect`, `instrumentation` y R4-B 8 (H-08). | `SetHSSpeed` (por valor) y `SetPreAmpGain(0)` entran a la lista blanca. La HS se muestra `[E]` (sin getter, [SDK p.146-147]) y el pre-amp `[L]` (`GetCurrentPreAmpGain`, [SDK p.147]). Si 13 MHz no está en la tabla: `[!]`, sin fijar, hasta BANCO-38. |
| D-15 | **Sí** | 8 | Correcta, pero incompleta (H-09). | `SENT_OK` para seis parámetros: modo de lectura, modo de adquisición, ventilador, modo de ganancia, índice VS e índice HS. Sin `Reading[int] \| None`: todo campo es un `Reading`. |
| D-16 | No | 11 | La duración se puede calcular en la GUI con el plan y la exposición. La fracción de la exposición en curso importa ergonómicamente con 10 s, pero no bloquea. | `exposureProgress(float)` por tramo de 250 ms, recomendado. |
| D-17 | **Sí** | 11 | Sin slot para seguir, la pausa G8 no tiene salida. | `resume()` y `PAUSED_NO_SIGNAL`, con la regla de H-04: en pausa no se late, y al seguir se vuelve a chequear la luz. |
| **D-18** (nueva) | **Sí** | 7 | R4-C 1 elimina el tope de exposición en especular, que vive en Z5, en el driver y en el interlock (H-34). | Z5 = fijar `SPECULAR_DEFAULT_EXPOSURE_S` al entrar. `set_exposure_time` deja de recortar por condición especular. El interlock especular queda **sólo sobre la ganancia EM**. `instrumentation` actualiza sus §2.2 y §2.5-4. |

**Cuenta:** de 21 filas (D-07 y D-09 partidas, más D-18), 18 bloquean y 3 no (D-05, D-09a, D-16). Casi todas las que bloquean se cierran con una línea de contrato; las que requieren una decisión, y no sólo una edición, son D-06 y D-18 (firma de `instrumentation`). Por paso:
- paso 7: D-06, D-07a, D-08, D-18;
- paso 8: D-12, D-13, D-14, D-15;
- paso 9: D-04;
- paso 10: D-07b, D-07c;
- paso 11: D-09b, D-10, D-11, D-17;
- paso 14: D-01, D-02, D-03, D-04.

---

## 3. Consistencia con las decisiones del investigador y ergonomía en uso real

### 3.1 Matriz contra R4, R4-A, R4-B y R4-C

| Decisión | ¿El diseño la cumple? | Nota |
| :--- | :--- | :--- |
| R4-A 3: el orden cero es frecuente, sin diálogo | **Sí** | El diálogo se retira y el Override desaparece. |
| R4-B 3: al entrar se cierran todos los obturadores; se abren a voluntad | **Sí** | "Obturadores abiertos en especular: 532" es un buen rótulo. |
| R4-B 3 / R4-C 1: ganancia EM bloqueada en 0 en especular | **Sí** | Candado visible en el spinbox. |
| R4-C 1: sin tope de exposición en especular | **No** | 10 ms en la insignia, §1.4, T-ZO-2 y M-05 (H-34, D-18). |
| R4-C 2: filtro de densidad en alta en especular → avisar | **Sí** | Era la propuesta del diseño. |
| R4-B 4: el Live se reanuda solo; la ganancia no vuelve sola | **Sí** | La pastilla necesita la salvaguarda de H-05. |
| R4-B 4: Live en cualquier configuración | **Sí** | §1.5. |
| R4-B 1: no se escribe al arrancar; se compara y se avisa | **Sí** | §1.11, más el `PRE_WRITE` huérfano de H-17(d). |
| R4-B 1: la calibración es una rutina independiente de la pestaña Calibraciones | **Sí** | Con H-02: sin `Ctrl+R`. |
| R4-A 5 / R4-B 10: doble confirmación y tercera por encima de ±50 pasos con Δ en nm | **Sí** | La confirmación tecleada es buena. Falta el botón por defecto (H-23). |
| R4-B 10: sin tope rígido | **Queda abierta** | D-07c sin cerrar (H-07). |
| R4-C 4: no se restaura desde el historial | **No** | Tres caminos de restauración (H-18). |
| R4-C 5: una escritura por confirmación | **Parcial** | El diálogo sí; §4.2 describe una restauración automática al cancelar (H-18). |
| R4-C 6: corrección fina aparte, eje crudo intacto | **Parcial** | §4.6 sí; T-SPEC-4 no (H-35). |
| R4-A 4: Step & Glue con lámpara en 500-900 nm, y aviso si el espejo no está abajo | **Sí** | El diálogo de tres opciones está justificado. |
| R4-B 5 / R4-C 3: la rutina renueva el latido; el obturador lo abre el operador | **No** | Selector "Luz" que apaga el latido y propuesta "la rutina lo abre" (H-03). |
| R4-B 6: cierre con la platina a (50, 50, 10) | **Sí** | Desde `PI_HOME_POS`; falta la variante sin platina (H-17c). |
| R4-B 7: Reconectar con aviso | **Sí** | Sin diálogo si el equipo no está conectado (H-29). |
| R4-B 8: HS 13 MHz, modificable | **Sí en la GUI, no en el contrato** | D-14 (H-08) y marca `[E]` (H-09). |
| R4-B 9: tope de exposición del driver de 60 s | **Sí** | Rotulado junto al de 10 s de las rutinas. |
| R4-A 9: criterios provisorios; nada dice "validado" | **Sí** | Con H-15, para que CON RESERVA y SÓLO MEDIR se entiendan. |

### 3.2 Espejo rápido: costo por ida y vuelta

Conteo de acciones del operador en una ida y vuelta [I, sobre los mockups]:

| Uso | Diseño tal como está | Con H-11, H-13 y H-34 |
| :--- | :--- | :--- |
| Mirar la muestra (la ganancia ya era 0) | `Ctrl+0` · la exposición queda en 10 ms y no deja ver, sin salida · `Ctrl+0` · [Restituir exposición] | `Ctrl+0` · (sólo la primera vez de la sesión, ajustar la exposición) · `Ctrl+0` = **2** |
| Centrar el láser (Raman con ganancia 150) | `Ctrl+0` · [Obturadores] · abrir 532 · `Ctrl+0` · [Restituir 150] · [Restituir exposición] = 6 | `Ctrl+0` · [Obturadores] · abrir 532 · `Ctrl+0` · [Restituir 150] con "Notch puesto: sí" (H-05) = **5 a 6**, y ninguna sobra |
| Lo que se ve si falla un paso | el paso en rojo y el detalle | además, el estado final de cada recurso (H-12) |

La fricción que queda es el giro de la torreta (Z7), que existe igual en Solis. Con estas correcciones, el espejo rápido no debería ser más lento que tipear "0" en Solis. La medición real va en la prueba B-04 (§5.2).

### 3.3 Calibración y escritura: ¿la confirmación protege sin volverse rutina?

- **Frecuencia:** la calibración se hace ≈ cada 2 meses (`lab-invariants` fila 129, EXPERIMENTAL), y la escritura es todavía más rara (R4-C 5). Con esa frecuencia, tres pasos no se vuelven rutina. El número de líneas tecleado (2.ª confirmación) es la barrera correcta, porque no sale por reflejo.
- **El riesgo real de rutina** está en las confirmaciones de **cada corrida** de Preparación. Por eso H-14 saca la casilla del espejo (pretildada = rutina) y deja sólo la del notch, que el software no puede leer y que cambia el método.
- **"SÓLO MEDIR":** el rótulo solo no alcanza. "(la escritura se habilita tras BANCO-40)" no le dice nada a un becario, y [Aplicar corrección fina] al lado sugiere que algo se escribe al equipo. H-15 da el texto.
- **Cuenta regresiva de 60 s:** mostrarla todo el tiempo presiona a confirmar rápido. Propuesta: que aparezca sólo en los últimos 20 s (BAJA; no se agrega a la tabla).

### 3.4 Defensa ante errores: los casos pedidos

| Caso | ¿Lo cubre el diseño? | Hallazgo |
| :--- | :--- | :--- |
| E-STOP y Stop siempre visibles | En la barra sí; en los modales no | H-01 |
| Doble clic en Ir, espejo rápido o escritura | Sí: el botón se deshabilita en el mismo slot y el diálogo bloquea entre la emisión y la respuesta | La autorrepetición de `Ctrl+0` no está cubierta (H-11a) |
| Rueda del ratón | Sólo sobre combos | H-10 |
| Cambio de pestaña a mitad de una rutina | Sí: la habilitación sigue a la sesión, no a la pestaña | `Ctrl+R` y `Ctrl+0` durante una rutina, con el motivo (H-11b) |
| Cerrar la ventana durante una escritura | No | H-17(b) y (d) |
| Cerrar durante una exposición de 10 s | Sólo para la calibración | H-17(a) |
| Estados imposibles alcanzables | En parte | estado desconocido con `Ctrl+0` y sin destino recordado (H-11c, d); pausa con láser (H-04); láseres que cambian a mitad del barrido (H-03) |

---

## 4. Unidades, rótulos y accesibilidad

### 4.1 Unidades y procedencia

- **Bien resuelto:** sufijos SI en los spinbox (nm, µm, s, °C, DAC, pasos, %), ganancia en **DAC** y no "×" (T-CAM-4), marcas `[L]/[E]/[!]/[?]/[X]/[D]` **en texto** además del color, "λc (SDK)" en lugar de "λ actual", y el valor viejo que pasa al tooltip cuando falla una lectura (§1.1-1). Es de lo mejor del diseño.
- **A corregir:** VS y HS con `[E]` (H-09); unidades en etiquetas y avisos (H-24); el `✓` de la Preparación sólo para lo **releído**, y `[E]` para lo enviado (H-14b).
- **"Validado":** no aparece, y ACEPTADA lleva "(criterios PROVISORIOS)". Falta que el eje del modo no se mezcle con el del veredicto (H-15).
- **Tooltips con fórmulas:** cumplen la regla "números de este equipo con su fuente". Aritmética revisada en esta auditoría: D (0.1026 y 0.01152 nm/px), W (103.05 y 11.57 nm), 1.1 · W/2 (56.7 y 6.4 nm), 10 pm ≈ 0.87 px con 1200, k = t₀.₉₇₅(8) ≈ 2.31, y el agua a 649 nm desde 532 nm con 3400 cm⁻¹. Todas son coherentes. El ejemplo de la tercera confirmación (312 pasos × 0.15 px/paso = 46.8 px ≈ 4.8 nm, no "≈ 48 px, 4.9 nm") está redondeado de más; no afecta a nada porque es ilustrativo. T-ZO-2 se reescribe (H-34) y T-SPEC-4 también (H-35).

### 4.2 Contraste y texto

| Par (texto sobre fondo) | Contraste [cálculo WCAG, esta auditoría] | Uso en el diseño | Veredicto |
| :--- | :--- | :--- | :--- |
| `#cdd6f4` sobre `#1e1e2e` | ≈ 11:1 | texto general | OK |
| `#6c7086` sobre `#1e1e2e` | **≈ 3.4:1** | línea "destino", `[?]`, "suponiendo 1:1", fondo lineal | **falla AA** (H-22) |
| `#a6adc8` sobre `#1e1e2e` | ≈ 7.4:1 | propuesto para texto secundario | OK |
| `#181825` sobre `#fab387` (insignia durazno) | ≈ 9.9:1 | insignia de orden cero | OK |

- **Tamaño:** la barra actual usa 9.5-10 pt (`window.py:248, 295`). En un laboratorio a oscuras y a ≈ 1 m de la pantalla, conviene que la insignia de orden cero y la de latido vayan en ≥ 11 pt y en negrita, y la E-STOP como hoy o más grande (BAJA; sin fila propia).
- **Daltonismo:** durazno, amarillo y rojo son pasteles cálidos muy parecidos para deuteranopía. El diseño no depende del color, porque cada insignia lleva su palabra. Hay que mantenerlo así en la implementación: nunca un punto de color solo.

### 4.3 Teclado

- **Recorrido completo sin ratón:** Preparación → [Iniciar]; diálogo de escritura con el campo tecleado; tablas con flechas (`currentCellChanged`, ya previsto). Tiene que figurar como prueba (S-20).
- **Tooltips:** con el teclado no se alcanzan (Qt los muestra al pasar el puntero). Las fórmulas de T-CAL-* también tienen que estar en el `[Ayuda]` de la sección, no sólo en el tooltip.
- **Atajos:** `Ctrl+0` sin autorrepetición (H-11a); sin `Esc` = Stop (H-19); `Ctrl+R` fuera de la calibración (H-02); `Ctrl+E`/`F12` a nivel de aplicación (H-01).

---

## 5. Checklist de pruebas manuales

Complementa las M-01 a M-17 del diseño (§8 de `gui_design.md`), que se conservan con dos cambios: **M-05** ya no espera "exposición ≤ tope", sino "exposición = la de orden cero recordada" (H-34); y **M-07** espera además que la exposición de primer orden vuelva sola (H-13).

### 5.1 SAFE_MODE, con los dobles del SDK (Ronda 4, antes de cualquier banco)

| ID | Prueba | Resultado esperado | Hallazgo |
| :-- | :--- | :--- | :--- |
| S-01 | Abrir cada modal (escritura en las páginas 2 y 4, Reconectar, espejo de Step & Glue, cierre) y pulsar `Ctrl+E`, `F12` y el botón E-STOP del propio diálogo | En los tres casos: `close_all_shutters()` registrado, cámara abortada, `SetEMCCDGain(0)` releído | H-01 |
| S-02 | En Calibraciones, con Preparación completa, pulsar `Ctrl+R` | No arranca nada; la barra dice "Iniciar con el botón" | H-02 |
| S-03 | Mantener `Ctrl+0` apretado 2 s; pulsarlo durante "Moviendo…"; pulsarlo con Step & Glue corriendo | Una sola entrada; ignorado durante el movimiento; deshabilitado con el motivo | H-11 |
| S-04 | Arrancar con el doble del Shamrock ya en orden cero (sin destino recordado) | Insignia de orden cero; ganancia bloqueada; "Volver" pide red y λ en línea | H-11d |
| S-05 | Arrancar con `GetWavelength` fallando | "ORDEN CERO (estado desconocido)"; `Ctrl+0` ofrece [Releer], no mueve | H-11c |
| S-06 | Pasar la rueda sobre cada spinbox del panel, de Preparación (incluida λ_ref) y de Step & Glue, sin foco | Ningún valor cambia | H-10 |
| S-07 | Espejo rápido desde ganancia 150 → abrir el 532 en especular → volver | La pastilla dice "532 abierto" y pide "Notch puesto: sí"; sin láser abierto, un clic basta | H-05 |
| S-08 | Ida y vuelta al orden cero dos veces, cambiando la exposición de orden cero a 0.3 s la primera vez | La segunda entrada usa 0.3 s; al volver, la exposición de primer orden reaparece sola; la ganancia no | H-13, H-34 |
| S-09 | Doble de ganancia que devuelve 12 en Z4 | Paso rojo; estado final de cada recurso: red sin mover, Live detenido, obturadores sin cambios, ganancia desconocida, sesión libre | H-12 |
| S-10 | Step & Glue con el 532 abierto desde [Obturadores]; esperar 60 s sin tocar nada | El watchdog no cierra el 532; la insignia dice "Latido: Step & Glue (532 abierto)"; el metadato de cada ventana registra el 532 | H-03 |
| S-11 | Step & Glue: cerrar el 532 a mano en la ventana 3 | Ventanas 4 en adelante con `LIGHT_CHANGED` y aviso amarillo en la tabla | H-03 |
| S-12 | Step & Glue con el doble sin señal en la ventana 1 y el 532 abierto; esperar 40 s en la pausa; [Seguir] | Sin latido durante la pausa; el watchdog cierra el 532; [Seguir] bloquea con "el 532 se cerró durante la pausa" | H-04 |
| S-13 | Plan de 500-900 nm, 532 abierto, ganancia 50 | Bloqueante "la ventana 1 contiene 532 nm…"; con ganancia 0, arranca | H-06 |
| S-14 | Calibración con el doble sin línea (`NO_LINE`) | El 532 se cierra; esa red termina con el mensaje; nunca queda esperando un clic con el láser abierto | H-04 |
| S-15 | Transacción con un Δ de 2500 pasos (en el doble, con S simulada) | No hay rechazo por tope de política; se exige la 3.ª confirmación | H-07 |
| S-16 | Página 5 con NO COINCIDE; historial | No existe "Restaurar"; se ofrece [Recalibrar (Verificar)]; el aviso rojo persiste | H-18 |
| S-17 | Matar el proceso entre `PRE_WRITE` y `APPLIED` (doble) y volver a arrancar | Fila roja "escritura sin confirmar" con lo releído y el respaldo | H-17d |
| S-18 | Capturas a 1920 × 1080 y a 1366 × 768 | Panel ≤ 360 px, sin líneas partidas; visor del Live ≥ 60 % del ancho; texto secundario ≥ 4.5:1 | H-20, H-22 |
| S-19 | Calibración con el doble de temperatura en `NOT_STABILIZED` | Aviso amarillo; la corrida arranca; la línea del filtro de densidad dice `[E]` | H-14 |
| S-20 | Recorrido completo sin ratón: Preparación → Iniciar → resultado → diálogo de escritura | Todo alcanzable con Tab/flechas/Enter; Enter nunca confirma el diff ni cierra el programa por defecto | H-23 |
| S-21 | Cerrar la ventana en la ventana 3 de 5 de Step & Glue con 10 s de exposición; repetir con el doble de platina no conectada | El texto menciona el barrido; las ventanas 1-2 quedan en disco; con la platina no conectada, el texto no promete moverla | H-17a, c |
| S-22 | `Esc` con Step & Glue corriendo y el foco en su pestaña | No detiene nada | H-19 |
| S-23 | Elegir 27 MHz en el combo de HS sin [Aplicar]; después [Aplicar] | Nada se envía sin [Aplicar]; después la HS muestra `[E] 27 MHz` y la VS `[E] 1.9 µs` | H-09, H-27 |

### 5.2 Banco, sin láser (Grupo E ya hecho; R4-A 11) — coherente con el Grupo H

| ID | Ítem de banco | Qué se mira en la GUI | ¿Aprobación? |
| :-- | :--- | :--- | :--- |
| B-01 | BANCO-45 (y BANCO-25 antes) | Cada valor mostrado coincide con BANCO-25 y lleva la marca correcta (`[L]` o `[E]`); ningún `Set*Offset` en el registro de llamadas; con Solis abierto, grupo "no conectado" con el motivo y [Reintentar] sin diálogo del enfriador (H-29) | No |
| B-02 | BANCO-38 | El combo de HS muestra la tabla real (35, 27, 13 MHz esperados); si 13 MHz falta, `[!]`; pre-amp `[L]` índice 0; rango de ganancia en DAC desde `GetEMGainRange` | No |
| B-03 | BANCO-36 | Rótulos de red con el blaze leído de `GetGratingInfo`; el rango del spinbox de λ = `GetWavelengthLimits`; el espejo no figura en Calibraciones | No |
| B-04 | BANCO-42, 43 y 47 (lámpara al mínimo, EM 0, láseres cerrados) | Los cinco caminos (`Ctrl+0`, botón, λ bajo el umbral con "Ir (espejo rápido)", menú "red espejo", Step & Glue con un centro bajo el umbral) muestran la **misma** lista de pasos y el mismo registro. **Cronometrar** la ida y la vuelta por red (comparar con Solis). Anotar dónde aparece la imagen especular frente a la línea "destino" (56.7 / 6.4 nm). Con la lámpara del microscopio, ¿qué exposición de orden cero hace falta para ver la muestra? (fija `SPECULAR_DEFAULT_EXPOSURE_S`, R4-C 1) | **Sí** |
| B-05 | BANCO-46 (lámpara) | Stop a los 2 s de una exposición de 10 s: "Deteniendo…" y fin en ≤ 0.25 s más la lectura; las dos barras de progreso se mueven; con la E-STOP, la ganancia queda en 0 | **Sí** |
| B-06 | BANCO-53 (lámpara) | Cantidad de ventanas y duración estimada frente a lo real; cada ventana en disco al terminar; con el espejo en `up` o `unknown`, el diálogo de tres opciones | **Sí** |
| B-07 | BANCO-09 | El estado del obturador del Shamrock se muestra en el panel y se relee (G6) | No (sin láser) |
| B-08 | BANCO-21 | Tras un ciclo de energía, la creencia del espejo en el panel dice DESCONOCIDA o la persistida, con su fuente | No |
| B-09 | **nuevo** (H-28) | Reconectar la cámara: el diálogo se ve; cronometrar el reenfriado hasta −60 °C estabilizada con el ventilador en low y en high | No |

### 5.3 Banco, con el 532 atenuado (filtro de densidad en baja, EM 0; aprobación en todos)

| ID | Ítem de banco | Qué se mira en la GUI |
| :-- | :--- | :--- |
| B-10 | BANCO-13 (existente) y R4-B 3 | Centrar el láser en la ranura en orden cero: banda **medida** frente a la **esperada 1:1**. La diferencia mide la magnificación, que el manual hoy da por hecha (§6). El indicador de saturación en amarillo o rojo según H-21, sin abortar el Live |
| B-11 | BANCO-44 | Step & Glue con la fuga del 532 y el obturador abierto por el operador (R4-C 3): latido activo (S-10 en hardware), un cuadro nuevo por ventana |
| B-12 | BANCO-48, 49, 50 y 52 | Calibración SÓLO MEDIR por red: gráfico de llegadas; veredictos rotulados PROVISORIO; ninguna escritura en el registro de llamadas; el 532 se cierra al terminar y al cancelar (M-09 en hardware); duración real frente a la estimada (H-16) |
| B-13 | BANCO-51 | Una entrada por corrida en el historial, sin reconstruir la tabla ni perder la selección |
| B-14 | BANCO-37b y BANCO-40 (con BANCO-25 hecho) | Primera escritura real con el diálogo (red de 1200): las tres confirmaciones (la 3.ª si Δ > 50), la relectura, Solis lee el mismo valor, y la E-STOP alcanzable desde el diálogo (S-01 en hardware). Hasta que BANCO-40 dé S, "Proponer offset…" sigue deshabilitado. BANCO-40 no puede hacerse desde la calibración en SÓLO MEDIR, que no escribe: su herramienta la define `instrumentation` |

---

## 6. Manual: qué escribir o corregir

**Cuándo:** en la Ronda 4, **junto con el código de cada paso**, no antes. Un manual que describe botones que todavía no existen es el caso de la memoria *archive-docs-describing-nonexistent-code*. Lo que hoy describe código que se retira (el `ZeroOrderSafetyDialog` y las escrituras directas) se archiva con su categoría cuando ese código se borre, no se reescribe en el lugar.

### 6.1 `docs/MANUAL_USUARIO.md`

| Sección | Qué está mal hoy | Qué hay que escribir |
| :--- | :--- | :--- |
| §4.1, maqueta del panel | "−65 °C", "Enfriador: ON" (G-01, G-02), "Pre-Amp Gain 1.0x", "Velocidad de lectura 5.0 MHz" (el iXon3 885 da 35 / 27 / 13 MHz, [DS-iXon p.2]), EM Gain sin unidad, "λ actual", "Ir a Orden Cero (0 nm)" | La maqueta nueva, con dos columnas (leído / pedido) y las marcas `[L]/[E]/[!]/[?]/[X]/[D]` explicadas en una tabla |
| §4.1, atajos | `Ctrl+0` "Abrir Diálogo de Seguridad de Orden Cero" | `Ctrl+0` = espejo rápido: entrar y volver (siempre orden cero con la red actual). `Ctrl+R` **no** inicia la calibración. Sin `Esc`. `Ctrl+E`/`F12` funcionan también con un diálogo abierto (H-01) |
| §4.2, pestaña 1 | "En Orden Cero el espectrógrafo forma imagen 1:1, así que la banda representa el ancho físico": afirmado **sin verificar** (el diseño §0.5 lo marca [I]) | Banda medida y banda esperada "suponiendo 1:1 (no verificado; B-10)"; centrado del láser en la ranura; menú "Usar esta fila como traza" |
| §4.2, pestaña 2 | "Single-Track por hardware (Modo 1), Multi-Track (Modo 2)": contradice el SDK (0 FVB, 1 Multi-Track, 2 Random-Track, 3 Single-Track, 4 Image; [SDK p.305], C-05). "Un cuadro en ceros es la forma en que el driver informa una lectura fallida" deja de ser cierto con `single_exposure` | Números de modo corregidos junto con C-05; "sin datos, no hay espectro" en lugar de la frase de los ceros |
| §4.2, pestaña 3 | "normalización por lámpara halógena trazable NIST" (sin fuente, G-18) | Plan antes de arrancar; preflight (bloqueantes y advertencias); diálogo del espejo; "Láseres abiertos al iniciar" y latido (H-03); Stop ≤ 0.25 s; ventanas a disco; [Coser lo adquirido] |
| §4.2, pestaña 5 | Los siete puntos están desactualizados: escritura directa de offsets, "calibración no volátil" (no confirmada, BANCO-37), el Espejo como calibrable, "Calibración Cúbica EEPROM", "NIST", persistencia en `.txt`, "movimiento a Orden Cero" propio | Reescritura completa: calibración de λ en SÓLO MEDIR (qué mide, qué no hace), veredictos y criterios PROVISORIOS, corrección fina (sólo PySpectrum, en el metadato, R4-C 6), historial append-only, escritura con tres confirmaciones y sin restauración desde el historial (R4-C 4) |
| §4.5, interlocks | Describe el `ZeroOrderSafetyDialog` de cinco opciones y el "clampeo a 5× si la exposición supera 1 s" (se elimina; además eran 5 DAC, no ×5) | Espejo rápido: qué protege (ganancia EM 0 confirmada, obturadores cerrados al entrar) y qué **no** (la exposición es del operador, R4-C 1). E-STOP: también baja la ganancia. Los tiempos de asentamiento son **esperas del software**, no mediciones (`lab-invariants` fila 126) |
| §15 / §17, SOP | No hay SOP de calibración de λ ni de centrado en la ranura | SOP "Calibración de λ con la fuga del 532 (SÓLO MEDIR)" y SOP "Centrar el láser en la ranura en orden cero" |
| §21, atajos | Igual que §4.1 | Igual que §4.1 |
| §22, resolución de problemas | Sin entradas de PySpectrum 3.0 | "Andor/Shamrock no conectado (¿Solis o el legado abiertos?)"; "Offsets del equipo distintos del archivo"; "ORDEN CERO (estado desconocido)"; "Escritura sin confirmar"; "Step & Glue: ventana sin luz" |
| §23.4, límites de validez | Sin filas del bloque A | Las filas de §6.2 abajo |

### 6.2 `docs/modulos/MOD-06_PySpectrum_Espectroscopia_Shamrock.md`

| Sección | Problema | Acción |
| :--- | :--- | :--- |
| §2 Maqueta y §3 Catálogo | Maqueta de la Fase 1 | Maqueta y catálogo del panel de estado, del espejo rápido, de Calibraciones y de Step & Glue (enlazados desde los `[Ayuda]` del diseño §5.7) |
| §5 Resiliencia y Modo Simulación | "Si los instrumentos no están conectados **o** `SAFE_MODE = True`, se activan de forma transparente `_MockShamrock` y `_MockAndorCCD`": **contradice DEC-036 y DEC-040** (sin simulador fuera de SAFE_MODE) | Reescribir: el simulador sólo existe con SAFE_MODE; fuera de él, "no conectado" con el motivo (`available`/`unavailable_reason`) |
| §7 Control térmico y ganancia | Setpoint "típico −65 o −80 °C" (el de arranque es −60, R4-A 6); código de colores en "×" (0-100, 101-300, > 300), cuando el modo 0 va de 0 a 255 DAC; "Selector de amplificador" sin aclarar que se oculta si `GetNumberAmp` = 1 | Verificar contra R2-inst §6 antes de enlazarla (lo pide el diseño §5.7); unidades DAC; setpoint −60 °C con la fila 124 de `lab-invariants` |
| §8.1-§8.3 Calibraciones | Botón propio de orden cero; píxel central con "predeterminado 501.0 px" (el valor inventado de G-15); escritura de red, detector, cero de ranura **y Espejo**; "EEPROM" y "trazable" sin fuente | Reescribir junto con los pasos 10 y 14; archivar la descripción de las escrituras directas cuando se borre ese código |
| §8.4 Step & Glue | Describe los botones de hoy | Reescribir con el paso 11 (plan, preflight, Stop, latido) |
| §9 Límites de validez | Saturación a "65 535 ADU" (el ADC es de 14 bit, **16 383**, [DS-iXon p.2], `lab-invariants` fila 118); "−10 a −60 °C" sin fuente; faltan todos los modos de falla del bloque A | Corregir el ADC. Filas nuevas (condición → síntoma en la GUI → qué hace el operador): estado del Shamrock desconocido → "ORDEN CERO (desconocido)" → [Releer]; espejo sin sensor → "según el software" / DESCONOCIDA → confirmar a ojo; S desconocido → "Proponer offset" deshabilitado → BANCO-40; persistencia del offset no confirmada → T-WR-2 → BANCO-37; corrección fina suspendida → aviso de arranque → recalibrar; láser abierto durante Step & Glue → insignia de latido → cerrar el láser que no se use; `PRE_WRITE` huérfano → fila roja → recalibrar (R4-C 4) |
| §12.2 `LeftHardwarePanel` y §12.3 `ZeroOrderSafetyDialog` | Describen código que el paso 7 y el paso 8 retiran | Archivar al retirar el código (categoría *implementable* no aplica: se retira por decisión, R4-A 3). En su lugar, §"Espejo rápido (orden cero)" y §"Estado leído del espectrómetro" |
| §12.5 driver | "`HSSPEEDS_MHZ_MOCK = [5.0, 3.0, 1.0]`" sin decir que son del simulador y no del 885 | Aclarar "valores del simulador; el equipo real da 35 / 27 / 13 MHz" |
| Nueva | — | §"Escritura de offsets" y el monográfico `CAT-252` propuesto por el diseño, a partir de `metrology.md` §1-§4 |

---

## 7. Qué tiene que cerrarse antes de cada paso de la Ronda 4

CRÍTICA y ALTA son condición para escribir el paso. MEDIA se incorpora a la revisión del diseño, que es barata porque son cambios de texto o de habilitación. BAJA puede resolverse al implementar.

| Paso | Hallazgos (CRÍTICA/ALTA en negrita) | Discrepancias |
| :-- | :--- | :--- |
| 7, espejo rápido | **H-01, H-05, H-34**; H-11, H-12, H-13, H-21, H-33 | D-06, D-07a, D-08, D-18 |
| 8, panel de estado | **H-08**; H-09, H-10, H-20, H-22, H-27 | D-12, D-13, D-14, D-15 |
| 9, diff al arrancar | H-17d, H-25, H-26 | D-04 |
| 10, escritura | **H-01, H-07, H-18**; H-17b, H-23 | D-07b, D-07c |
| 11 y 12, Step & Glue y escaneo lineal | **H-03, H-04, H-06**; H-17a, H-19, H-31 | D-09b, D-10, D-11, D-17 |
| 14, calibración | **H-02, H-04**; H-14, H-15, H-16, H-35 | D-01, D-02, D-03, D-04 |

---

## 8. Preguntas para el investigador (4)

Las seis del diseño ya tienen respuesta (R4-C). Éstas son las que quedan abiertas después de esta auditoría.

**P1. Cuando centra el láser en la ranura en orden cero, ¿saca el notch, o lo mira con el notch puesto?**
- *Desbloquea:* H-05, es decir, si "Restituir ganancia" con un láser abierto pide "Notch puesto: sí" o si basta con mostrar qué láser está abierto.

**P2. ¿Acepta que PySpectrum recuerde dos exposiciones por sesión, una para orden cero y otra para primer orden, y que cada una vuelva sola al pasar de un modo al otro?** (La ganancia sigue sin volver sola, R4-B 4.) ¿Con qué valor arranca la primera entrada al orden cero de la sesión: 0.1 s?
- *Desbloquea:* H-13 y H-34 (`SPECULAR_DEFAULT_EXPOSURE_S`).

**P3. Si una escritura sale mal (el valor releído no es el escrito), ¿se ofrece volver al valor del respaldo, como una escritura más con su transacción completa, o también en ese caso se recalibra?**
- *Contexto:* R4-C 4 descarta restaurar "desde el historial". La vuelta inmediata al respaldo tras un fallo es un caso distinto: el equipo quedó en un estado que nadie pidió.
- *Desbloquea:* la página 5 del diálogo y el aviso de estado desconocido (H-18).

**P4. ¿Cuánto tiempo acepta que dure una calibración de las dos redes, con el 532 abierto todo ese tiempo?**
- *Contexto:* con 1 s de exposición y hasta 25 llegadas por punto se estima ≈ 16 min [I]; con 10 s, horas.
- *Desbloquea:* D-02 (`CAL_MAX_EXPOSURE_S`) y el máximo de llegadas por defecto.

---

## 9. Veredicto

**`MINOR_UX_POLISH_NEEDED`**, con la condición de §7.

- **No es `MAJOR_REWORK_REQUIRED`:** la estructura es la correcta. Un único camino por acción peligrosa, lo leído separado de lo pedido, el espejo rápido sin diálogo, la escritura como transacción, los veredictos en dos ejes y la palabra "validado" ausente. Todos los hallazgos se corrigen sin mover esa estructura: un contexto de atajo, un botón en los modales, una regla de latido, habilitaciones y textos.
- **No es `APPROVED`:** H-01 (E-STOP tapada por los modales) es CRÍTICA según el criterio del laboratorio, y nueve ALTAS contradicen decisiones vinculantes (R4-B 5, R4-B 8, R4-B 10, R4-C 1, R4-C 3, R4-C 4) o abren un camino de daño al detector o de datos arruinados en silencio (H-02, H-04, H-05, H-06).
- **Riesgo principal que confirma esta auditoría:** el mismo que el diseño identifica en su §9 (que el espejo rápido sea más oscuro o más lento que Solis). Con R4-C 1 aparece una causa concreta, el tope de 10 ms (H-34), y su corrección es sacarlo.

---
