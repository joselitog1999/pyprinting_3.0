# C-01 — Ronda 3 — Auditoría QA/UX del diseño de GUI (`qa-ux-auditor`)

Estado: COMPLETO (2026-09-27). Secciones 1 a 6: primera pasada sobre `gui_design.md` (v1). Sección
7: segunda pasada sobre `gui_design_v2.md`.

Objeto auditado: `c01_ronda3/gui_design.md` (autor: `scientific-gui-designer`). Esta auditoría es
el segundo par de ojos, independiente: señala defectos, riesgos y omisiones con severidad y
propuesta concreta. **No rediseña.** No se modificó ningún archivo del repositorio salvo este.

**Marcas.**
- **[CÓDIGO]**: leído por mí en la línea citada (printing3 `main`, salvo que diga `printing2/`).
- **[DISEÑO §n]**: sección de `gui_design.md`.
- **[R2-ARQ]**, **[R2-MET]**, **[R2-INS]**: `c01_ronda2/architecture.md`, `metrology.md`,
  `instrumentation.md`.
- **[INV]**: `RESPUESTAS_INVESTIGADOR.md` (rondas 3 a 5). Vinculante.
- **[FUENTE]**: verificado por mí en `docs/bibliografia/`, con la página física del PDF.
- **[DERIVADO]**: cálculo mío con las fórmulas de [R2-MET] §2.1. Script:
  `scratchpad/qa_p0_candidates.py` de esta sesión.

**Severidad.**
- **CRÍTICA**: puede abrir un obturador, dejarlo abierto, mover la platina bajo el haz, o registrar
  como válido un dato que no lo es, sin que el operador lo vea.
- **ALTA**: induce a error al operador en una decisión de impresión, o pierde o corrompe datos.
- **MEDIA**: fricción ergonómica o inconsistencia que un operador atento detecta.
- **BAJA**: pulido.

**Orden.** 1 el dato nuevo (PyPrinting legacy a ≈ 10 ms) · 2 tabla de hallazgos · 3 revisión de
G-1 a G-10 y de R4-1 a R4-15 · 4 lista de verificación manual en `SAFE_MODE` · 5 preguntas para el
investigador · 6 veredicto.

---

## 1. El dato nuevo: el hábito "20/20" probablemente viene de PyPrinting legacy

### 1.1 Lo que verifiqué en el código del legado

| Hecho | Dónde | Consecuencia para el diseño |
|---|---|---|
| La traza del legado corre con `pointtimer.start(0)` | `printing2/Trace_pp.py:373` [CÓDIGO] | la cadencia no la fija un temporizador, sino lo que tarda cada tick |
| Cada tick crea una tarea finita, lee `N = 10` muestras a `rateNI/100` = 10 kS/s y la cierra | `Trace_pp.py:312-313, 379-382`; `rateNI = 1·10⁶` en `Instrument_nidaqmx_pp.py:26` [CÓDIGO] | un punto del legado promedia **1 ms de señal**, igual que un tick de 3.0 con `DEC-037` ([R2-MET] §1.1). Los ≈ 10 ms del comentario de 2019 (`Trace_pp.py:398`; el diseño cita `:392`) son casi todo costo de crear y cerrar la tarea, así que dependen de la PC y del driver: en la PC actual pueden ser otros |
| El eje que guarda el legado es `linspace(0.01, timer_real, ptr)`, con `timer_real` de reloj de pared | `Printing_pp.py:801-811` (`NP_xxx.txt`, `:808`), `Trace_pp.py:471` [CÓDIGO] | **la cadencia real del legado en la PC del banco se puede medir hoy, sin hardware**: en cualquier `NP_xxx.txt` del legado, la cadencia media es `(t_final − 0.01 s) / (n − 1)`, con n filas. Lo mismo vale para los `NP_xxx.txt` de 3.0 en `7f5d10a` (`measurements.py:2971`), que darían `T_ref` de 3.0 en la PC del banco y adelantarían BANCO-24 |
| `Steps before/after umbral` son `QLineEdit('10')` del widget de la **traza**, no del panel de impresión | `Trace_pp.py:90-95` [CÓDIGO] | el operador que viene del legado busca las ventanas en la traza, no en el panel |
| El legado **no guarda** los Steps: no tiene presets, y `grid_info.txt` no los lista | `Printing_pp.py:468-471` [CÓDIGO] | no existe ningún archivo del legado que convertir. Un 20/20 del legado se reescribe a mano en cada sesión: es un hábito fuerte, que vive en la cabeza del operador |
| El criterio del legado es `I_new > u·I_old` **o** `I_new < d·I_old` **o** T_max, en la primera evaluación, sin persistencia ni umbral absoluto | `Printing_pp.py:793` [CÓDIGO] | confirma [DISEÑO §0.4]: N_hold y el umbral absoluto sólo existen en 3.0 |

**Dos fuentes independientes apuntan en la misma dirección** (compatibles con el hábito del
legado, no prueba):
- [FUENTE] [M24] p. 69 (tesis de Martínez, que usó PyPrinting): "u(t) = I(t+dt)/I(t−dt), donde dt es
  del orden de 10 a 100 ms". `dt` es la **semiseparación** entre las dos lecturas. Con dos ventanas
  contiguas de ancho W, dt ≈ W/2, así que el método documentado usa ventanas de **≈ 20 a 200 ms**.
  20/20 a 10 ms (200 ms) cae en el borde superior; 20/20 a 47 ms (940 ms) queda 4.7 veces afuera.
- [FUENTE] [M24] p. 112: "el láser sigue iluminando a la NP durante un tiempo de respuesta de la
  detección automatizada que varía entre 10 y 100 ms". Con 200 ms y u = 1.5, un escalón ×2 decide a
  los 100-110 ms; con 940 ms, a los 570-580 ms [DERIVADO].
- Además, `docs/MANUAL_USUARIO.md:474` dice que N_hold = 5 son "∼ 30-50 ms" y `:1769` habla de
  saltos "< 20 ms": la documentación de 3.0 también se escribió pensando en ticks de ≈ 10 ms. El
  modelo mental del laboratorio es el del legado.

### 1.2 Tres candidatos a "P0 como hoy"

[DERIVADO], T_b = 10 ms, u = 1.5, modelo sin ruido de [R2-MET] §2.1:

| Candidato | W_old / W_new | τ_hold (efectiva) | Escalón mínimo | Latencia ×2 / ×1.6 / ×1.4 | Transitorio ×2 que se toma por captura | Armado (W_new + W_old) |
|---|---|---|---|---|---|---|
| **P0-3.0**: los números leídos como 3.0 a 47 ms (lo que propone el diseño) | 940 / 940 ms | 94 (100) ms | ×1.534 | 570-580 / 883-893 ms / no detecta | > 470 ms | 1.88 s |
| **P0-legado**: el comportamiento literal de `printing2` (modo 0, sin persistencia) | 200 / 200 ms | 0 | ×1.500 | 100-110 / 167-177 ms / no detecta | > 100 ms | 0.40 s |
| **P0-intención**: 20/20 y N_hold 3 pensados en ticks de 10 ms (modo 1) | 200 / 200 ms | 20 (20) ms | ×1.532 | 120-130 / 187-197 ms / no detecta | > 100 ms | 0.40 s |

- Entre P0-3.0 y P0-legado, la parte del criterio de la dosis después de la captura cambia por un
  factor **≈ 5.7** para un escalón ×2.
- Los tres heredan el hueco: ×1.40 a ×1.50-1.53 sólo lo detecta el umbral absoluto.
- Ninguno de los tres es "el correcto" hasta que conteste el investigador (P-A, §5). **El diseño
  elige uno sin decirlo como supuesto de diseño**: lo pone en defectos, maquetas, tooltips y en la
  lista de verificación.

### 1.3 Qué partes del diseño dependen de la suposición, y qué cambiar en cada una

| # | Parte del diseño | Qué supone | Qué cambiar |
|---|---|---|---|
| D-1 | §0.4: "la práctica (1.5, N_hold 3, 20/20) sólo puede ser de 3.0" | que los cuatro números vienen del mismo programa | Decir "puede ser una mezcla": N_hold 3 y el modo 1 son de 3.0, pero 20/20 puede ser un hábito del legado ([INV] quinta ronda, 3: hoy el banco trabaja con el legado; 3.0 se probó aparte). Reformular P1 (P-A, §5) |
| D-2 | §2.3, columna "Defecto → P0": 940 / 940 / 94 | T_ref = 47 ms | Dejar la columna P0 **pendiente de P-A**, con los tres candidatos de §1.2. Distribuir dos presets con nombre y procedencia, "P0-3.0 (paridad `7f5d10a`)" y "P0-legado (paridad `printing2`)", en vez de un único "P0 como hoy" |
| D-3 | §1.2, maqueta: 940 ms, 94 bl., ×1.53, 570 ms, aviso ×1.40-1.53 | P0-3.0 | Son cifras de ejemplo: rotularlas "(ejemplo, P0-3.0)". En la implementación salen en vivo del motor (regla del propio diseño, §4.1) |
| D-4 | §2.6: el banner convierte con T_ref = 47 ms por defecto | que los archivos en ticks son de 3.0 | **Correcto para archivos**: el legado no escribe presets (§1.1), así que todo `.txt` en ticks es de 3.0. Se mantiene. El riesgo real no son los archivos sino los números que el operador trae del legado, que el banner nunca ve (ver D-5) |
| D-5 | §2.6 punto 2: "Cambiar T_ref…" es "la herramienta para el operador que llega con sus números del legado", pero sólo aparece al **cargar un archivo** en ticks, y el cajón "Avanzado" (§1.1, punto 5) está cerrado por defecto | que el operador del legado trae un archivo | Poner junto a W_old / W_new un botón visible "Tengo valores en pasos…", que abra el mismo diálogo de conversión (origen 3.0 a 47 ms o legado a T_ref medido) y rellene los campos en ms mostrando las consecuencias de cada origen lado a lado. Es el primer contacto del usuario del legado con 3.0: no puede estar escondido |
| D-6 | §2.6 fila del legado: "≈ 10 ms, **sin medir**" | que medirlo exige ir al banco | Medirlo de los `NP_xxx.txt` del legado que ya existen en la PC del banco (§1.1) y, del mismo modo, T_ref de 3.0 con sus `NP_xxx.txt` de `7f5d10a`. El diálogo muestra el T_ref medido con su procedencia ("medido en 12 archivos del 2026-09, mediana 11.3 ms"), no un ≈ 10 ms de un comentario de 2019 |
| D-7 | §2.6: el texto del banner dice "Se convirtió con T_ref = 47 ms" | que convertir conserva el criterio | Agregar qué se conserva y qué no: "conserva la duración de las ventanas; no el ruido por punto (antes 1 ms de señal por paso, ahora 10 ms por bloque)" ([R2-ARQ] K4) |
| D-8 | §4.3, tooltip de τ_hold: "En PyPrinting 3.0, N_hold = 3 ticks equivalía a ≈ 94 ms" (texto fijo) | que el lector viene de 3.0 | Agregar "En PyPrinting legacy no había persistencia: paraba en la primera evaluación (τ_hold = 0)" [fuente: `printing2/Printing_pp.py:793`] |
| D-9 | §4.3, tooltip de W_new: "El legado de CIBION usaba ventanas de 10 a 100 ms" | que el `dt` de [M24] p. 69 es un ancho de ventana | Corregir: "[M24] p. 69 usa u(t) = I(t+dt)/I(t−dt) con dt de 10 a 100 ms; con ventanas contiguas equivale a W ≈ 20-200 ms". Lo mismo en §2.3 ("Por qué estos rangos") |
| D-10 | §2.4 y P13: la confirmación queda apagada en P0 "porque con ventanas largas el rechazo de transitorios ya lo da la ventana" | P0 = 940 ms | Con P0-legado o P0-intención, un transitorio ×2 de más de 100 ms ya se toma por captura: el argumento se debilita. P13 queda condicionada a P-A |
| D-11 | §3.9, indicador "legacy · ≈ 47 ms/tick" | que "legacy" no tiene otro significado | "Legacy" ya significa tres cosas en el diseño: PyPrinting legacy (≈ 10 ms), los modos "0 · Legacy" y "1 · Legacy + …", y el backend `legacy_timer` (47 ms). Un operador que lee "legacy · 47 ms/tick" concluye que su legado corría a 47 ms. Renombrar el backend en la GUI ("tick finito, `DEC-037`") y mostrar su cadencia **medida en vivo** (media de Δt de la sesión), no una cifra fija |
| D-12 | §7.1, lista de verificación: "940 / 940 / 94 ms: ×1.53; 570-580 ms…" | P0 = 940 | Son buenos vectores de prueba. Rotularlos "vector de prueba A" y agregar el vector legado (200 / 200 / 0 ms, modo 0: ×1.50; 100-110 / 167-177 ms) |
| D-13 | [R2-ARQ] §5.9: "la conversión ida y vuelta es exacta para los presets en uso" (lo toma el diseño en §3.9) | presets de 470/940 ms | Con 200 ms en `legacy_timer`: round(200/47) = 4 pasos = 188 ms (−6 %). Ya está previsto mostrar el valor efectivo; verificarlo en la lista (§4) |
| D-14 | §0.4: "Mostrar las ventanas en ms elimina esta trampa" | — | Sólo si la conversión de los números **del operador** es la correcta. Queda eliminada recién con D-5 y D-6 |

Nada de esto cambia el motor: `from_legacy_ticks(params, mode, t_ref_ms)` ya recibe T_ref ([R2-ARQ]
§4.2). Cambia qué se ofrece por defecto, dónde y con qué rótulo.

---

## 2. Tabla de hallazgos

Resumen: **3 CRÍTICAS, 17 ALTAS, 18 MEDIAS, 4 BAJAS** (42 hallazgos). Las tres críticas son del
mismo tipo: el diseño no dice qué pasa con la grilla cuando el operador corta el haz a mano, y
PyPrinting no tiene hoy con qué cortarlo desde las ventanas que se miran durante una grilla.

### 2.A Seguridad, pánico y bloqueos

| ID | Sección del diseño | Sev. | Problema | Propuesta |
|---|---|---|---|---|
| QA-01 | §3.11 ("`Ctrl+E` y `F12` … no cambian"), §1.2, §1.4, §3.8 | **CRÍTICA** | **PyPrinting 3.0 no tiene parada de emergencia propia.** `Ctrl+E` / `F12` existen sólo en PySpectrum (`pyspectrum/window.py::_setup_shortcuts`; `lab-invariants.md:166`). En PyPrinting no hay ningún atajo de pánico: el único recurso es el botón "Cerrar Todos", de 8 pt, en el dock de obturadores de la ventana principal (`core/shutters.py:380-383`). El panel de impresión y la cámara son **ventanas separadas** (`app.py:215-225`), que es justo donde mira el operador durante una grilla. El banco corre PyPrinting como proceso aparte ([INV] Q16 y quinta ronda, 3), así que el E-STOP de PySpectrum no lo cubre. La frase "no cambian" da a entender que la cobertura existe | Agregar a esta ronda un E-STOP de PyPrinting: botón rojo siempre visible en el panel de impresión y en la barra de la traza, más `Ctrl+E` / `F12` con `Qt.ShortcutContext.ApplicationShortcut` en todas las ventanas de PyPrinting (principal, impresión, dímeros, cámara). Tiene que escribir el estado **cerrado** de cada línea según su polaridad (`close_all_shutters()`, el 532 nm en ALTO, `DEC-036`), detener la sesión (predicado de aborto, [R2-ARQ] §2.3), dejar la grilla **detenida** y activar un interlock `"E-STOP"` que sólo libera el operador. Toca obturadores: nunca exento, así que pasa por las Rondas 1-2 de instrumentación. Sumar la fila ✅ a `lab-invariants` |
| QA-02 | §3.6 (tabla de bloqueos), §3.8, §3.4 | **CRÍTICA** | **"Cerrar Todos", o apagar a mano el obturador de impresión, no detiene la grilla.** `close_all_shutters()` no activa ningún interlock ni avisa a la rutina (`core/nidaq.py:525-556`, `core/shutters.py:308-315`) [CÓDIGO]. Con el diseño, la sesión sigue leyendo oscuridad: la rama de caída (d = 0.5) da "caída de señal", el nodo va a la cola ([DISEÑO §3.5]) y la grilla sigue sola con el nodo siguiente, que **vuelve a abrir el obturador** unos segundos después. Con d = 0, el nodo espera T_max y después sigue igual. El gesto de pánico del operador lo deshace el nodo siguiente. El diseño no menciona "Cerrar Todos" en ningún lugar | Todo cierre iniciado por el operador (Cerrar Todos, el botón del obturador del láser de impresión, E-STOP) con una sesión activa se vuelve predicado de aborto: la sesión termina `aborted` ("cierre del operador") y la grilla queda en **pausa**. Banner: "Cerraste los obturadores durante el nodo 17: la grilla quedó en pausa. Pulsá Play para seguir." Agregar el panel de obturadores a la tabla de §3.6: "Cerrar Todos" siempre habilitado y cableado a la pausa; los botones de apertura, deshabilitados durante un nodo. Test de mutación: después de "Cerrar Todos", ningún `open_shutter` hasta un Play del operador |
| QA-03 | §3.3 (fila "abortada": "según §3.7"), §3.4, §8.2 R4-5 | **CRÍTICA** | **La política de continuación después de `aborted` no está definida por causa.** Sólo están definidas `acq_fault` (sigue sola, [INV] quinta ronda, 1) y el corte del watchdog (pausa, §3.7). "Abortada" agrupa watchdog, interlock y parada de emergencia, y remite a §3.7, que sólo trata el watchdog. Si la Ronda 4 lo implementa como `acq_fault` ("seguir con el próximo nodo"), después de un E-STOP o de un interlock `"Platina PI"` la grilla abre el nodo siguiente | Tabla explícita en §3.4, fila por causa: `acq_fault` → sigue (con las excepciones de §3.4); watchdog → pausa, interlock liberado solo (§3.7); interlock `"NI-DAQmx"` o `"Platina PI"` → pausa, sin liberación automática (`DEC-036`); E-STOP → grilla **detenida**, interlock hasta que el operador lo reconozca; cierre del operador → pausa (QA-02). La liberación automática de R4-9 **nunca** aplica al E-STOP. Test: para cada causa de `aborted`, ningún `open_shutter` hasta una acción del operador |
| QA-04 | §3.6, tabla "Qué se bloquea y cuándo" | ALTA | **Faltan actuadores que cambian la señal a mitad de un nodo:** (a) el panel de obturadores: botones por láser, "Low power" (filtro de densidad) y "Mirror up" (espejo de detección) (`core/shutters.py:372, 377`); ya tienen `set_actuators_enabled` (`:468-477`) pero el diseño no los incluye; (b) `Laser532Window` (`modules/camera.py:3686-3774`), que cambia la tensión de modulación del 532 nm (`ao2`) con un deslizador en vivo y no tiene ningún bloqueo, **ni siquiera el de `DEC-019`**; (c) el Play del panel de dímeros, otra instancia de `MeasFrontend` (`app.py:224-225`). Subir la potencia ×1.6 a mitad de un nodo da un "success" falso; bajar el filtro o el espejo da "caída" o 40 s de exposición sin señal | Sumar las filas: durante un nodo, bloqueados con motivo; en pausa, habilitados; "Cerrar Todos" siempre habilitado (QA-02). `Laser532Window` gana `set_actuators_enabled` con motivos: sirve también para la subyugación. Registrar `ao2` por intento (§5.2 ya lo pide); con el bloqueo, ese valor es único por intento |
| QA-05 | §3.8 ("`F2` pausa la grilla"), §3.11 | ALTA | **Los atajos de la traza no llegan desde donde mira el operador.** `F1` / `F2` son `QShortcut` con el contexto por defecto (`WindowShortcut`) sobre el widget de la traza, en la ventana principal (`modules/trace.py:332-335`). El panel de impresión y la cámara son ventanas propias (`app.py:215-225`). Con el foco en la cámara, `F2` no hace nada, y el diseño presenta a `F2` como la forma rápida de "cortar el haz ya". Tampoco hay atajo de Pausa en el panel de impresión | `F2` (pausar la grilla) y el E-STOP con `ApplicationShortcut` en todas las ventanas de PyPrinting. `F1` queda con su contexto actual, porque abrir un obturador no debe tener alcance global. Sumar a la lista: "con el foco en la ventana de la cámara, F2 pausa la grilla" |
| QA-06 | §3.8, tabla de botones: "Saltar nodo ►\|" en pausa: "marca el nodo pendiente como salteada y pasa al siguiente" | ALTA | "Pasa al siguiente" es ambiguo. Hoy `grid_next_index` llama a `_grid_move()` **aunque la grilla esté en pausa** (`measurements.py:2948-2952`) [CÓDIGO]: un clic en "Next" en pausa arranca el nodo siguiente con exposición. Un operador que espera un cambio de índice inofensivo abre el láser | Especificar: **en pausa**, "Saltar" sólo marca y avanza el índice; no mueve la platina ni abre, y la grilla sigue en pausa. **Corriendo**: cierra, marca y sigue con el nodo siguiente, como hoy. El tooltip dice cuál de los dos va a pasar según el estado. Sumar a la lista de verificación: "Saltar en pausa no cambia ninguna línea DO" |
| QA-07 | §3.6, fila "Play de la grilla: en pausa, habilitado salvo foco o confocal manual en curso" | ALTA | En pausa se habilitan la traza manual (F1) y Power BS. La traza manual abre `laser1` y, si se eligió, un segundo láser físico (`trace.py:582-585`). Si el operador reanuda la grilla con una traza manual corriendo: (a) el nodo arranca con el obturador **ya abierto**, así que los bloques previos a la apertura miden la muestra iluminada y se viola "adquirir antes de exponer"; (b) puede haber dos láseres abiertos; (c) la "promoción en el lugar" de [R2-INS] §4.2 engancha el detector a una tarea de monitor cuyo obturador no es de la sesión | Play de la grilla deshabilitado mientras haya una traza manual activa, con el tooltip "Detené la traza manual (F2) para reanudar". Otra opción: Play detiene la sesión manual y **confirma cerrados** sus obturadores antes de los bloques previos del nodo. Power BS en `bs_monitor` no abre obturadores y puede seguir. Sumar a la lista de verificación |
| QA-08 | §3.7, paso 2 ("Limpiando: esperando que la rutina termine…") | ALTA | **El paso 2 no tiene plazo.** El latido de vida existe justamente para el hilo colgado dentro del driver ([R2-ARQ] K5). Ese hilo no termina nunca de limpiar: el banner queda en "Limpiando…" para siempre, sin decir qué hacer. Es una falla silenciosa con otra apariencia | Plazo explícito: por ejemplo `TraceSession.stop(timeout_s=0.5)` más `read_timeout_s`. Vencido el plazo: "La rutina de impresión no terminó: el hilo de adquisición quedó colgado. Los obturadores están confirmados cerrados; el bloqueo sigue. Guardá los datos y reiniciá PyPrinting." El interlock queda hasta reiniciar. Sumar el caso a la lista (gancho de depuración que cuelga el hilo **y** no lo deja salir) |
| QA-09 | §8.2 R4-15, §3.9, §4.3 (tooltip del indicador), §3.7 | ALTA | Con `legacy_timer`, que es el backend por defecto al entrar en la Ronda 4 ([R2-ARQ] §5.9 a) y por lo tanto lo primero que va a usar el operador, **no hay concesión ni latido de vida de 1.0 s**: el latido es `heartbeat_shutter()` por tick y rige el plazo global (30 s o "Sin límite"). La matriz de R4-15 no incluye el latido ni la liberación automática. El tooltip "Plazo del latido de vida: 1.0 s" y los banners de §3.7 serían falsos con ese backend | Sumar a R4-15 las filas "latido de vida y concesión" y "liberación automática del interlock": con `legacy_timer`, "no disponible: rige el plazo global del panel de obturadores (30 s / Sin límite)". Con ese backend la GUI nunca muestra "1.0 s". Lo mismo para "garantía de sistema ≤ 20 ms": con `legacy_timer`, "no aplica" |
| QA-10 | §3.7 ("no se duplican: el banner remite al panel de obturadores") | MEDIA | **El estado del watchdog durante una rutina sana no se ve.** El rótulo `lbl_security_status` muestra "Auto-cierre en N s" con el plazo **global** (`core/shutters.py:317-331`). Con la concesión, el obturador de impresión queda fuera de ese plazo ([R2-INS] §3.2), así que el rótulo va a mostrar una cuenta regresiva o un "—" que no tienen que ver con la rutina. La regla del investigador es que el watchdog nunca corte una rutina sana ([INV] §10). El operador necesita ver que la rutina está sana, no inferirlo | Mientras haya una concesión, el rótulo dice: "532 nm: en uso por la traza de impresión · latido OK (hace 10 ms) · plazo 1.0 s · el plazo global no aplica". Cambiar a "Sin límite" a mitad de un nodo no toca la concesión, y el tooltip lo dice. Con `legacy_timer`, el rótulo sigue como hoy (QA-09) |

### 2.B Valores, unidades, rangos y validación

| ID | Sección del diseño | Sev. | Problema | Propuesta |
|---|---|---|---|---|
| QA-11 | §2.3 (V_abs: rango 0.000-10.000 V), §2.1 ("un umbral en 0 que significa desactivado usa `setSpecialValueText`"), §3.2 ("aviso, nunca bloqueo") | ALTA | **V_abs no tiene valor "desactivado", y un valor bajo para todos los nodos en el acto.** El motor evalúa `c_abs = I_new > V_abs` desde el primer bloque (`measurements.py:2365`; [R2-ARQ] §4.2). Con V_abs = 0, o con cualquier V_abs por debajo de la base iluminada, cada nodo termina "success" apenas se cumple τ_hold después del asentamiento (≈ 150 ms): no se imprime nada y el mapa queda todo verde. En el mismo panel, V_min y d usan 0 = "desactivado", y el operador va a leer el 0 de V_abs igual, por analogía. Con contraste −1 el peligro está en el otro extremo: V_abs por encima de la base | (a) Mínimo de V_abs en 0.010 V, sin texto especial. Si hace falta desactivar la rama absoluta, que sea un checkbox que el motor entienda (FALTA-CONTRATO: `umbral_abs_enabled`). (b) Salvaguarda en el motor: si `c_abs` ya es verdadera en el **primer** bloque evaluado después del asentamiento (la señal estaba por encima de V_abs desde que se abrió, así que no hubo escalón), la parada se rotula "parada inmediata por V_abs", no "success". Una captura real temprana no la dispara, porque antes de ella `c_abs` fue falsa. Con 2 seguidas, la grilla se pausa: "V_abs está por debajo de la base". (c) La línea "V_abs ≡ ×1.37 sobre la base" de §3.2 pasa a Red si la razón es ≤ 1.05 (o ≥ 0.95 con contraste −1) |
| QA-12 | §2.1 ("Adiós al `QLineEdit` numérico… `QDoubleSpinBox`") | ALTA | **El separador decimal pasa a depender del Windows del banco.** Hoy `float(text)` exige punto. `QDoubleSpinBox` usa el `QLocale()` del sistema, y la aplicación no fija ninguno: no hay ningún `QLocale` en `app.py`, `modules/`, `core/` ni `pyspectrum/` [CÓDIGO]. Con la región Español (Argentina), la coma es el separador decimal y el punto el de miles. "1.5" puede quedar rechazado, y entonces el spinbox conserva el valor anterior sin avisar, o, si el validador acepta el punto como separador de miles, leerse como 15 y recortarse a 5.00. Cuál de las dos pasa depende de la versión de Qt: no lo verifiqué, y por eso va a la lista de verificación. En los dos casos el u en uso no es el que el operador cree haber escrito. Los presets se escriben con punto | Fijar `QLocale.c()` (o inglés) en todos los spinbox del panel, del asistente y del diálogo de conversión, y aceptar la coma como sinónimo. Sumar a la lista: con la región de Windows en es-AR, escribir 1.5 y 1,5 en u da 1.50 en los dos casos. Pregunta P-J |
| QA-13 | §2.3 (T_max de 1.0 a 60.0 s) | MEDIA | Con T_max < W_new + W_old, la rama relativa **nunca** puede decidir: el armado de P0-3.0 dura 1.88 s ([DERIVADO], §1.2). Todo nodo termina "sin captura" o por V_abs, y nada lo advierte. Pasa también si alguien baja T_max para probar | Aviso de pre-flight, no bloqueante: "T_max (1.5 s) es menor que el armado del criterio relativo (W_new + W_old = 1.88 s): esa rama no va a decidir". Lo calcula el motor: `StopCriterion.validate` devuelve advertencias además de errores |
| QA-14 | §2.3 (contraste), §3.1.1 (línea `u`: "con contraste −1 se dibuja en 1/u"), §4.3 (tooltip de V_abs: "Condición: `I_new > V_abs`") | MEDIA | (a) Con contraste −1 la condición absoluta se invierte (`I_new < V_abs`, [R2-ARQ] §4.2), pero el tooltip de V_abs y el rótulo de su línea son fijos. (b) [R2-MET] §5.2 pide un `u_down` **propio** (por defecto 1/u: "no se reusa el u de subida"), mientras que [R2-ARQ] §4.2 y el diseño usan 1/u fijo. Es una discrepancia entre paneles que no está en R4-1 a R4-15 | (a) Tooltip y rótulo con la condición del signo activo, calculados en vivo. (b) Sumarla a la reconciliación (R4-20, §3.2 de esta auditoría). El impacto práctico es bajo: no hay contraste negativo en el banco ([INV] Q13) |
| QA-15 | §1.2 mock ("+ sistema ≤ 20 ms (garantizado)"), §3.2 ("Presupuesto"), §4.3 (tooltip del indicador: "Garantía de sistema: ≤ 20 ms"; "Verde: ≤ 20 ms") | MEDIA | (a) "≤ 20 ms" es el **objetivo** que fijó el investigador ([INV] Q1). [R2-ARQ] §6.2 lo registra en el ledger como **no verificado hasta BANCO-29**. La GUI lo presenta como "garantizado" antes de medirlo. (b) El tooltip fija "Verde: ≤ 20 ms", pero la regla de color es "atraso ≤ 2·T_b" (§3.9). Con `TRACE_BLOCK_MS = 20` ([R2-ARQ] §4.3) serían 40 ms, y el texto quedaría mal | (a) "objetivo de sistema ≤ 20 ms (sin verificar: BANCO-29)" hasta que el ledger lo cambie; después de ≥ 1 nodo, mostrar el valor medido, como ya propone la fila "Sistema medido". (b) Calcular el umbral del texto en vivo desde `StreamConfig` |

### 2.C Presets y conversión desde pasos

| ID | Sección del diseño | Sev. | Problema | Propuesta |
|---|---|---|---|---|
| QA-16 | §2.6 ("al cargar un preset con claves viejas… el panel lo convierte"), §3.10 | ALTA | **El cargador actual no permite detectar bien el formato y no valida nada.** `PresetManager.load_preset_file` parte de `DEFAULT_PRESET_FIELDS`, que ya trae `steps_before = 10`, `steps_after = 10` y `n_hold = 5`, y descarta en silencio toda clave que no conoce (`core/preset_manager.py:114-131`) [CÓDIGO]. Consecuencias: (a) si la detección de "preset en pasos" mira el diccionario resultante, **todo** preset parece en pasos, y a uno en ms se le inyectan 10/10/5; (b) no está definido qué gana si un archivo tiene claves en ms y en pasos; (c) un preset guardado en ms y abierto con una versión anterior, como `7f5d10a` en la PC del banco ([INV] R2-2), pierde las claves en ms sin aviso y corre con 10/10/5 a 47 ms; (d) un valor inválido ("1,5", "abc") hoy explota en `float()`, y con spinbox explotaría en `setValue`; (e) un valor fuera de rango se **recorta en silencio** con `setValue` (tmax = 90 → 60; ventana 3000 → 2000), y "(modificado)" aparece apenas se carga, sin explicación; (f) `_create_default_preset_files` (`:57-112`) vuelve a escribir presets en pasos si la carpeta queda vacía | El cargador devuelve valores, procedencia por clave y una lista de problemas: claves desconocidas, valores inválidos, valores recortados, modo ambiguo (QA-17). La detección de formato usa las **claves crudas del archivo**. Si hay claves en ms y en pasos, ganan las de ms y se avisa. El banner de §2.6 lista cada problema con su valor original. Se escribe `format_version = 2` y una línea `# Requiere PyPrinting con C-01: las versiones anteriores ignoran las claves en ms`. Los presets por defecto se regeneran en ms. Tests: cargar un archivo con cada problema y verificar el mensaje |
| QA-17 | §0.3 G-8, §1.2 ("clave estable e índice, por compatibilidad"), §8.2 R4-12 | ALTA | **Un preset viejo con `stop_mode = 3` es ambiguo, y la clave estable no lo resuelve** porque los archivos viejos no la tienen: "aviso si no coinciden" no tiene con qué comparar. Además de `Grilla_Extensa_10x10.txt` (que G-8 cita), `presets/AgNP_80nm_Nanodimeros.txt` también tiene `stop_mode = 3`, y ambos los genera el código (`preset_manager.py:83-105`). El modo 3 del panel (confocal reescalado) y el Híbrido se comportan distinto | Archivo sin clave de modo y con `stop_mode = 3`: el banner dice "Modo ambiguo: en el panel es Confocal reescalado y en el asistente, Híbrido. Elegí uno" y **Play queda bloqueado** hasta elegir, porque es un problema de validez del criterio, no una preferencia. El nombre del preset ("Híbrido") se ofrece sólo como sugerencia. Corregir los dos archivos del repositorio en la Ronda 4 con la respuesta del investigador (P-F) |
| QA-18 | §0.4, §2.3 (columna P0), §2.6, §1.2, §3.2, §4.3, §7.1 | ALTA | **P0 = 940 / 940 / 94 ms está fijado como si fuera "como hoy"**, y lo más probable es que "hoy" sea el legado a ≈ 10 ms: ≈ 200 ms de ventana, sin persistencia (§1). Con P0-3.0, la parte del criterio de la dosis después de la captura es ≈ 5.7 veces la del legado (570-580 ms contra 100-110 ms para ×2), y el rechazo de transitorios cambia de > 100 ms a > 470 ms ([DERIVADO], §1.2). Es un cambio de protocolo que el operador no pidió y que la GUI presentaría como continuidad | Lo de §1.3 (D-1 a D-14): dos presets con nombre y procedencia, ningún "P0 como hoy" hasta que conteste P-A, y las cifras de ejemplo rotuladas como ejemplos |
| QA-19 | §2.6 punto 2, §1.1 punto 5 (conversión dentro de "Avanzado", cerrado por defecto) | MEDIA | La herramienta para quien trae números en pasos sólo aparece al cargar un archivo o dentro del cajón "Avanzado". Pero el legado no escribe archivos (§1.1): el usuario del legado llega con números en la cabeza, y en su primer contacto con 3.0 no la va a encontrar | Botón visible "Tengo valores en pasos…" junto a W_old / W_new (D-5), con T_ref medido y su procedencia (D-6) |
| QA-20 | §3.9, §1.2 (nombres de los modos), §2.6 | MEDIA | **"Legacy" significa tres cosas**: PyPrinting legacy (≈ 10 ms/paso), los modos "0 · Legacy" y "1 · Legacy + …", y el backend `legacy_timer` (≈ 47 ms/paso). "legacy · ≈ 47 ms/tick" en el indicador lleva a concluir que el legado del banco corría a 47 ms (D-11) | En la GUI el backend se llama "tick finito (`DEC-037`)" y muestra su cadencia medida en vivo. "Legacy" queda sólo en los nombres de modo, que es el vocabulario del investigador ([INV] R3) |
| QA-21 | §1.2 (nombre "1 · Legacy + voltaje absoluto (con persistencia)") | MEDIA | El "+" se lee como un **Y**, que es el malentendido que G-1d corrige en el asistente. El combo actual ("Salto Relativo + Umbral Absoluto (V) & Anti-Paso", `measurements.py:669`) tiene el mismo problema. `MANUAL_USUARIO.md` §2.9 ya dice **OR**, con la fórmula | "1 · Legacy o voltaje absoluto (con persistencia)". Si el investigador prefiere su rótulo, agregarle "(lo que ocurra primero)". Vale también para el 2, "Meseta o voltaje absoluto", que ya lo hace bien |

### 2.D Estados de falla, reintentos y datos

| ID | Sección del diseño | Sev. | Problema | Propuesta |
|---|---|---|---|---|
| QA-22 | §3.4 ("cuándo sí se pausa"), §3.5 | ALTA | **No hay aviso ante rachas de "sin captura" o de "caída".** Sólo 3 `acq_fault` seguidas pausan la grilla. Una causa sistemática (espejo abajo, filtro en baja potencia, láser apagado por su propio interlock, foco perdido, coloide agotado) da "caída" o "sin captura" en todos los nodos. La grilla recorre entonces 64 nodos × 40 s ≈ 43 min, y en el Healing Pass 64 × 50 s más, exponiendo sin imprimir. Una racha de "caída" es, por el propio tooltip del diseño, "pérdida de señal (láser, obturador, alineación)" | "Caída" 3 veces seguidas → pausa con diálogo, como `acq_fault`, mostrando el nivel del BS (el fotodiodo BS ve la apertura y el cierre, [INV] Q14): "3 nodos seguidos perdieron la señal. BS: 0.02 V (esperado ≈ 1.1 V). Revisá láser, espejo y filtro." "Sin captura" N veces seguidas (propuesta: 5; P-D) → banner no bloqueante con las causas probables. El conteo lo lleva `printingWorker` |
| QA-23 | §3.4 ("Falla con el obturador ya abierto"), P4, §3.7 (nodo "abortada (watchdog)" → cola) | ALTA | La mitigación que propone el diseño para no reimprimir sobre una NP que pudo haberse impreso usa la **confirmación a baja potencia**, que no existe en el motor (FALTA-CONTRATO, nunca exenta). Mientras no exista, el camino por defecto ("marcado revisar") **igual reexpone 50 s** en el Healing Pass sin que nadie mire. La decisión del investigador ([INV] quinta ronda, 1) es reintentar en el Healing Pass, pero la pregunta se hizo sin distinguir si el nodo estuvo expuesto | Hasta que conteste P4: un nodo con exposición > 0 y sin decisión (`acq_fault` con `t_open_s`, abortado por watchdog, pausa a mitad de nodo, QA-24) entra a la cola como "en revisión", y el Healing Pass lo **saltea** salvo que el operador lo pase a "pendiente" desde la cola, mirando la cámara. El nodo sin exposición (`t_open_s is None`) se reintenta como decidió el investigador. Es la opción conservadora que P4 puede revertir |
| QA-24 | §3.8 ("Pausa a mitad de un nodo: vuelve a pendiente… al reanudar se reimprime") | MEDIA | Es el mismo riesgo de doble NP que el diseño trata para la falla con exposición (§3.4), pero acá no lo trata: un nodo pausado durante la ventana de latencia (0.1-0.9 s después de la captura) pudo haber impreso | El mismo tratamiento que QA-23: "interrumpido por pausa, expuesto X s", y al reanudar se pregunta en una línea no modal "¿Reimprimir el nodo 17 (expuesto 12.3 s)? [Sí] [Marcar impresa] [Saltar]". La cámara en vivo está al lado |
| QA-25 | §1.4 (opción "R" en `Láser 2`; capas `I_old(t)` e `I_new(t)`; zona de asentamiento; "\|0 apertura confirmada"), §8.1 | ALTA | **Contratos que la GUI necesita y el §8 no lista.** (a) `TraceView` trae `i_old` e `i_new` **escalares** ([R2-ARQ] §4.4), no series. Para dibujar R(t) y las medias de ventana, la GUI tendría que recalcular las ventanas por su cuenta, que es la "física propia" que el diseño prohíbe (§1.5, §2.1; lección R1-6). El operador calibraría u sobre una curva que no es la que evalúa el detector, justo en el arranque y en la cuantización de τ_hold. (b) `TraceView` no trae la fase (previa, asentamiento, evaluando, decidido) ni `t_open`. (c) `NodeOutcome.time_s` empieza en t ≥ `open_settle` ([R2-ARQ] §4.4): la zona de asentamiento que dibuja §1.4 **no tiene datos**, y los primeros 50 ms después de abrir se pierden de `NP_xxx.txt` y del HDF5. Es el único registro rutinario de la apertura del obturador que ve el BS ([INV] Q14), útil para BANCO-30 | Sumar a §8.1: `TraceView.i_old_v`, `i_new_v` (series decimadas como `pd_v`, salidas de `PrintStopDetector.window_means()` bloque a bloque), `phase` y `t_open_s`. `NodeOutcome` conserva los bloques de asentamiento marcados `excluded_from_criterion` en lugar de descartarlos. Hasta que existan, la opción "R" queda deshabilitada: no se recalcula en la GUI |
| QA-26 | §2.4, §1.2 (grupo "Confirmación después del corte") | MEDIA | La confirmación a baja potencia aparece en la GUI aunque no está en el contrato (R4-3) y abre un obturador (nunca exenta, requiere Rondas 1-2 de instrumentación). El propio diseño aplica a P1/P2 la regla opuesta: "no se exponen en la GUI hasta que el motor las tenga" (R4-13) | La misma regla: el grupo no aparece hasta que el motor tenga la secuencia. Si se quiere anticipar, un rótulo gris "Confirmación a baja potencia: en diseño (R4-3)" sin controles |
| QA-27 | §3.3 (contadores), §3.5 ("Marcar como impresa (operador)") | MEDIA | (a) `NP events` y `NP success` hoy muestran **el mismo número** con nombres distintos (`measurements.py:1376-1380`), y el diseño los redefine igual ("cuentan sólo impresa en sus tres variantes"). (b) Entre esas tres variantes está "impresa (operador)": la eficiencia de impresión, que el investigador reporta por conteo ([INV] R2-17), mezclaría la decisión del detector con el juicio del operador | Definir cada contador: por ejemplo "eventos" = paradas del criterio y "éxito" = impresas confirmadas. Las marcadas por el operador se cuentan aparte en el resumen, en `grid_info.txt` y en `intentos_<lote>.csv` (`kind = "success_operator"`), con un comentario opcional sobre la evidencia |
| QA-28 | §5.2 ("NaCl (mM)… con 0.50 por defecto") | ALTA | **Un valor por defecto en un metadato de análisis se convierte en un dato falso.** Si el operador no toca el campo, un lote a 1.5 mM queda registrado a 0.50 mM, y el PCA posterior que motiva el campo ([INV] Q10) lo toma como verdad. Lo mismo con la potencia en la pupila | Valor especial "no informado" por defecto, o "heredado del lote anterior (fecha)" con esa procedencia visible. Antes de Play, un aviso no bloqueante con los campos sin informar. `grid_info.txt` y el HDF5 escriben "no informado", nunca un número por defecto |

### 2.E Accesibilidad: el color no puede ser el único canal

| ID | Sección del diseño | Sev. | Problema | Propuesta |
|---|---|---|---|---|
| QA-29 | §3.3 (tabla de estados del mapa); §7.1 ("cada estado se reconoce **sólo por la forma**, en escala de grises") | ALTA | Con la tabla del propio diseño, ese punto de la lista **falla**. Luminancia relativa calculada de los colores de la paleta [DERIVADO]: (a) "impresa" (círculo Green `#a6e3a1`) contra "impresa en el reintento" (círculo Green con borde Teal `#94e2d5`): contraste **1.00**, se distinguen sólo por el color del borde; (b) "imprimiendo" contra "reintentando": mismo círculo con anillo, Yellow contra Peach, contraste 1.39; (c) "abortada" (cruz Overlay0 con anillo Red) contra "falla con exposición" (cruz Red con anillo Peach): la misma forma, contraste 2.11. El par (c) es el que más importa, porque las dos causas tienen políticas de reintento distintas (QA-03, QA-23). Además, cinco de los trece estados son círculos | Glifo propio para cada estado: "impresa en el reintento" = círculo con un punto interior o una "H"; "reintentando" = anillo punteado; "abortada" = cuadrado con cruz; "falla con exposición" = cruz con reloj o la cifra de exposición al pasar el cursor. Verificar la lista con un filtro de escala de grises y otro de deuteranopía (una captura de pantalla procesada alcanza) |
| QA-30 | §3.1.1 (líneas de umbral: "punteadas y de 1 px"; bloqueadas: "atenuada al 60 %") | MEDIA | Una línea punteada de 1 px, atenuada, no se lee a 1 m en un laboratorio a oscuras, que es lo que pide el propio punto de §7.1. El estado "fija" se comunica sólo por opacidad | 2 px, trazo discontinuo largo, y rótulo con fondo opaco. El estado bloqueado va en el texto del rótulo ("V_abs = 2.500 V · fija: nodo 17"), no sólo en la opacidad |

### 2.F Ergonomía y carga cognitiva durante una grilla larga

| ID | Sección del diseño | Sev. | Problema | Propuesta |
|---|---|---|---|---|
| QA-31 | §1.2 (maqueta del panel) | MEDIA | (a) La maqueta no muestra "Autofocus every N", "Shift x/y (µm)", la corrección de deriva ni los widgets de referencia y de creación de grilla (`measurements.py:865-990`, en otros docks), y no dice si se bloquean durante la grilla. Cambiar "Autofocus every N" a mitad de una grilla cambia el plan de autofoco. (b) Durante la corrida, "Consecuencias del preset" es estática (el criterio está bloqueado) y ocupa el espacio que necesita "Ejecución", que es lo que el operador mira durante 40 min | (a) Decir qué pasa con cada uno: bloqueados durante un nodo y editables en pausa, con efecto desde el nodo siguiente, como el criterio. (b) Con la grilla corriendo, "Consecuencias" se pliega a una línea ("×1.53 · ×2 → 570-580 ms") y "Ejecución" gana la altura |
| QA-32 | todo el diseño | MEDIA | **No menciona el modo dímeros.** La misma clase `MeasFrontend` sirve a "dimers" (`app.py:224-225`; ramas `mode == "dimers"` en `measurements.py`), y [R2-ARQ] §4.7 cablea `dimersWorker.on_trace_outcome`. No se dice si los estados nuevos, la cola, el Healing Pass, los bloqueos y los cambios de §0.3 se aplican a dímeros (dos NP por sitio, post-scan, dx/dy) | Declarar el alcance: o el diseño cubre dímeros, con sus estados (NP1 impresa, NP2 pendiente…), o dímeros conserva el panel actual hasta un hallazgo propio. En los dos casos, QA-01 a QA-07 aplican igual, porque el E-STOP y los bloqueos son del proceso |
| QA-33 | §3.6 ("Target Index… bloqueado"), §2.1 | MEDIA | "Target Index" es un `QLineEdit` que emite en **cada tecla** (`textChanged` → `new_index_Signal`, `measurements.py:795-797, 1238-1240`). Escribir "17" pasa por el nodo 1, y no hay tope: 999 se acepta. §2.1 convierte los parámetros numéricos, pero no nombra este campo | `QSpinBox` acotado a [0, N−1], con `keyboardTracking(False)`, bloqueado con la grilla corriendo |
| QA-34 | §3.6 (Go/Set reference en pausa: habilitados) | MEDIA | "Set reference" en pausa corre el origen de **todos los nodos que faltan** respecto de los ya impresos. Puede ser intencional (re-referenciar después de una deriva) o un error, y hoy nada lo distingue | Con una grilla con resultados, confirmar: "La referencia nueva desplaza los 47 nodos que faltan ΔX = +0.12 µm, ΔY = −0.05 µm respecto de los ya impresos. ¿Seguir?" |
| QA-35 | §3.10 ("aplica desde el nodo 18") | BAJA | Después de pausar, editar y reanudar, el registro guarda el criterio por nodo, pero ni el mapa ni la cola muestran dónde cambió. Para el análisis posterior importa | Marca en el tooltip del nodo ("criterio 2 de 2, desde el nodo 18") y una fila en `grid_info.txt` |
| QA-36 | §1.4 | BAJA | El usuario del legado tiene las ventanas en el widget de la traza (`printing2/Trace_pp.py:90-95`) y las va a buscar ahí | Durante la impresión, rótulo de sólo lectura en la barra de la traza: "ventanas en uso: 940 / 940 ms · τ 100 ms". Respeta el principio "se configura en el panel" |

### 2.G Tooltips, fuentes y documentación

| ID | Sección del diseño | Sev. | Problema | Propuesta |
|---|---|---|---|---|
| QA-37 | §4.4 (plan de documentación) | ALTA | **`docs/MANUAL_USUARIO.md` no está en el plan**: el diseño no lo menciona ni una vez. Partes del manual que ya contradicen al código o que van a contradecir a la GUI nueva [CÓDIGO y manual leídos]: `:293` (nombre del modo 1); `:458` (Timeout en rojo); `:465-468` y `:1732` (el Healing Pass usa "τ_safe = 30 s", pero el código usa T_max + 10 s, `measurements.py:2860`); `:471-472` (justificación de T_max con τ ≈ 8.9 s y "89 % de Poisson", que no verifiqué contra [G17]; el diseño usa en su lugar [INV] R3, "de 1 a 20 s"); `:473-475` (N_hold = 5 "∼ 30-50 ms", cuando a 47 ms son 188 ms); `:476-478` (Steps before/after con la misma descripción falsa de G-1a y G-1b); `:514`; `:634` (asistente); `:1682-1683` (`F2`, que cambia de sentido durante la impresión); `:1769` ("< 20 ms", N_hold 5-8); `:394` y `:815` ("Cerrar Todos… desde cualquier ventana", cuando está en un dock de la ventana principal y no detiene la grilla, QA-02) | Sumar a la tabla de §4.4 una fila por sección del manual, con la misma regla de "en el mismo commit". Las cifras nuevas se verifican contra fuentes (memoria del proyecto) |
| QA-38 | §4.4, `lab-invariants` | MEDIA | Si se agrega el E-STOP de PyPrinting (QA-01), `lab-invariants.md:166` queda incompleto. La cadencia del legado no tiene fila | Fila ✅ para el E-STOP de PyPrinting (símbolo verificable por el test del corpus) y fila 📄 "cadencia de `printing2`: medida en N archivos (fecha)" junto a `TRACE_LEGACY_TICK_MS` |
| QA-39 | §4.3 (tooltip de W_new: "El legado de CIBION usaba ventanas de 10 a 100 ms"; §2.3 "Por qué estos rangos") | MEDIA | Lectura errónea de la fuente. [FUENTE] [M24] p. 69 da `u(t) = I(t+dt)/I(t−dt)` con "dt del orden de 10 a 100 ms": `dt` es la semiseparación, no el ancho de la ventana. Con ventanas contiguas, W ≈ 2·dt ≈ 20-200 ms. La cita de p. 112 (respuesta de 10-100 ms, T ≈ 570 °C) sí está bien leída | Corregir los dos textos (D-9). El `provenance-verifier` debería marcar este tipo de paso de una magnitud a otra |
| QA-40 | §4.3 (tooltip de V_abs: "Arrastrá la línea naranja") | BAJA | El color es la única referencia a la línea en el texto | "Arrastrá la línea rotulada V_abs" |
| QA-41 | Veredicto del diseño ("G-2, G-3, G-5, G-6 … califican como exentos según `CLAUDE.md` §5.0") | MEDIA | `CLAUDE.md` §5.0 dice que **nunca** es exento "anything that moves a stage, opens a shutter", "regardless of how small the diff is". Arreglar G-6 cambia cuándo se abre el obturador y cuándo se mueve la platina ("Next" mueve sin cerrar). G-5 cambia si `F8` / `F10` pueden mover la platina en Z y abrir el obturador del foco. Que haya un test que falla no los vuelve exentos. G-2 y G-3 sí califican | Corregir el veredicto: G-2 y G-3 exentos; G-5 y G-6 requieren al menos las Rondas 1-2, aunque sean cortos |
| QA-42 | §7.1 ("Con W_new = 940, el aviso de 50 Hz no aparece. Con W_new = 30 ms, sí.") | BAJA | La lista de verificación prueba un aviso de 50 Hz que la especificación de §3.2 no define: no está en la tabla de líneas de "Consecuencias", ni con su umbral ni con su texto | Especificarlo en §3.2 (condición, por ejemplo "W_new < 200 ms y no múltiplo de 20 ms", y texto con fuente [R2-MET] §2.4 y §3.2), o sacarlo de la lista |

---

## 3. Revisión de lo que encontró el diseño

### 3.1 Defectos de la GUI actual (G-n)

Leí cada uno en el código.

| G | Veredicto | Comentario |
|---|---|---|
| G-1a, G-1b | **CONFIRMADO** | `measurements.py:685, 687`. `MANUAL_USUARIO.md:476-478` repite la misma descripción falsa: corregirla en el mismo commit (QA-37) |
| G-1c | **CONFIRMADO** | `preset_wizard.py:120-121` |
| G-1d | **CONFIRMADO** | `preset_wizard.py:96`. El combo del panel sugiere lo mismo con "+ … &" (`measurements.py:669`), y el nombre nuevo propuesto lo conserva (QA-21) |
| G-1e | **CONFIRMADO**, con matiz | Los "≈ 94 ms" valen para 3.0 a 47 ms; en el legado no existe N_hold (D-8) |
| G-2 | **CONFIRMADO y más amplio** | Además de la traza, `add_node_data` también borra `confocal_scan` y pisa los atributos `status` y `t_print_s` del nodo (`core/hdf5_container.py:150-181`): el escaneo del primer intento también se pierde. R4-8 tiene que cubrir los tres |
| G-3 | **CONFIRMADO** | `measurements.py:224-227`: dentro de `if st == "active"`, la condición `not in ("timeout", "pending")` es siempre verdadera |
| G-4 | **CONFIRMADO** | `measurements.py:161-165`: 4 insignias, falta "retrying" y "Timeout" está en `#f38ba8`. `MANUAL_USUARIO.md:458` lo documenta así |
| G-5 | **CONFIRMADO** | `focus.py:50-52` (atajos), `:90-95` (sólo botones), `:103-113` (emiten sin mirar). **Defecto aparte, fuera de C-01:** `F9` llama a `_lock`, que emite `focus_lock_button.isChecked()` **sin alternar** el botón (`focus.py:106-110`), y `focus_lock_lin` sólo bloquea con `True` (`:309-321`). Desde el teclado, F9 nunca bloquea el foco: con el foco suelto reenvía `False`, y con el foco bloqueado lo vuelve a bloquear en la Z actual. El flujo "F8 y después F9" de `MANUAL_USUARIO.md:1728` no funciona por teclado. Conviene registrarlo como hallazgo propio. Para C-01: la guarda de motivos va antes de esa lectura |
| G-6 | **CONFIRMADO y más amplio** | `measurements.py:1976-1978` y `:2948-2952`. Además, "Next" **en pausa** arranca el nodo siguiente con exposición (QA-06). No es exento (QA-41) |
| G-7 | **CONFIRMADO** | `trace.py:625-633` cambia `laser1` y `laser2 = "None"` en el backend sin tocar los combos; `F1` → `traceButton.click()` → `_start()` reabre (`:332-333, 582-585`). Con `F2`, en `legacy_timer` el nodo queda colgado para siempre: `grid_trace_detect` sólo corre cuando llega un dato (`measurements.py:2406-2408`) |
| G-8 | **CONFIRMADO y más amplio** | También `presets/AgNP_80nm_Nanodimeros.txt` tiene `stop_mode = 3`. La clave estable no resuelve los archivos viejos (QA-17) |
| G-9 | **CONFIRMADO** | `measurements.py:837-839`. Al tiparlos, no usar un valor por defecto numérico (QA-28) |
| G-10 | **CONFIRMADO** | `trace.py:372, 454` |

Todos los hallazgos G están bien fundados. Lo que falta no es un G mal visto, sino defectos que el
diseño no buscó: el pánico (QA-01 a QA-03), los actuadores sin bloqueo (QA-04) y "Next" en pausa
(QA-06).

### 3.2 Discrepancias de la reconciliación (R4-n)

| R4 | Posición de esta auditoría |
|---|---|
| R4-1 | De acuerdo con redondear hacia arriba. Agregar: con `legacy_timer`, [R2-ARQ] §5.9 reconvierte con `N_hold = 1 + round(hold_ms / T_ref)`. La etiqueta "efectiva" sale del backend activo, no de una regla única |
| R4-2 | De acuerdo con un solo par de valores en `StreamConfig`, menores que el plazo del latido. El texto del tooltip también sale de ahí (QA-15 b) |
| R4-3 | De acuerdo en que falta. Mientras falte, la GUI no la muestra (QA-26) |
| R4-4 | De acuerdo. Que el motor devuelva además las advertencias de pre-flight (QA-13) y la "parada inmediata por V_abs" (QA-11) |
| R4-5 | De acuerdo con aplicar la decisión del investigador. Faltan la política de `aborted` por causa (QA-03), las rachas de "caída" (QA-22) y el nodo que estuvo expuesto (QA-23) |
| R4-6 | De acuerdo |
| R4-7 | De acuerdo |
| R4-8 | De acuerdo. Extender a `confocal_scan` y a los atributos del nodo (G-2 ampliado) |
| R4-9 | De acuerdo para el watchdog. **Nunca** para el E-STOP ni para los interlocks de hardware (QA-03). Con plazo para el paso "Limpiando" (QA-08). No existe con `legacy_timer` (QA-09) |
| R4-10 | De acuerdo, con "no informado" como valor inicial (QA-28) |
| R4-11 | De acuerdo. Extender al panel de obturadores (el mecanismo ya existe), a `Laser532Window` (no tiene ninguno) y al Play de dímeros (QA-04). "Cerrar Todos" y el E-STOP quedan fuera del conjunto de motivos: nunca se bloquean |
| R4-12 | De acuerdo, pero no resuelve los archivos sin clave (QA-17) |
| R4-13 | De acuerdo. La misma regla vale para la confirmación (QA-26) |
| R4-14 | Sin objeción desde la GUI: se muestra lo que devuelva `blocks()` |
| R4-15 | De acuerdo con la matriz de disponibilidad. Faltan las filas del latido y de la liberación automática (QA-09) y el cambio de nombre del backend (QA-20). Las cifras de "Consecuencias" se calculan con la cadencia de evaluación de ese backend: para el vector A, 564-611 ms para ×2, no 570-580 [DERIVADO]. La forma cerrada de [R2-MET] §2.1 se validó para bloques (±2 ms); con pasos de 47 ms el cruce se cuantiza a pasos enteros y se aparta hasta ≈ 30 ms (×1.6: 846-893 contra 877-924 ms). `detection_model` necesita la versión discreta para ese backend, o rotular la cifra "±1 paso" |

**Discrepancias nuevas** para la matriz de la Ronda 4:

| # | Tema | Hallazgos |
|---|---|---|
| R4-16 | Series de ventanas, fase y `t_open` en `TraceView`; bloques de asentamiento en `NodeOutcome` | QA-25 |
| R4-17 | E-STOP de PyPrinting y cierre del operador como predicados de aborto, con el estado de la grilla definido por causa | QA-01, QA-02, QA-03 |
| R4-18 | `umbral_abs_enabled` y "parada inmediata por V_abs" | QA-11 |
| R4-19 | Cargador de presets: claves crudas, `format_version`, lista de problemas, modo ambiguo | QA-16, QA-17 |
| R4-20 | `u_down` propio ([R2-MET] §5.2) o 1/u fijo ([R2-ARQ] §4.2) | QA-14 |
| R4-21 | Locale numérico de los spinbox | QA-12 |
| R4-22 | Alcance del modo dímeros | QA-32 |
| R4-23 | T_ref medido de los dos programas, con procedencia, en `config` y en `lab-invariants` | D-6, QA-38 |

---

## 4. Lista de verificación manual en `SAFE_MODE`

Completa la de [DISEÑO §7.1], que sigue valiendo salvo lo que se corrige al final. Se corre con la
GUI completa en `SAFE_MODE` (skill `run`), **dos veces**: con `TRACE_ACQ_BACKEND = "stream"` y con
`"legacy_timer"`. La verificación de cada punto que toca obturadores se hace **en el log**, con
marcas de tiempo de cada escritura DO y su nivel: la GUI sola no alcanza como evidencia.

**Guion de `SimulatedBlockSource`**, que amplía el del diseño (6 nodos) a 11:
1. captura ×2 a 1.2 s;
2. sin captura;
3. falla antes de abrir;
4. falla a los 2 s de exposición;
5. captura con contraste −1;
6. captura ×1.45 con u = 1.5;
7. base de 1.8 V con V_abs = 1.5 V (por debajo de la base);
8. transitorio ×2 de 300 ms sin captura;
9, 10 y 11. señal que cae a 0.02 V (tres "caídas" seguidas).

### 4.1 Pánico y bloqueos (nuevos)

- [ ] El botón E-STOP se ve en el panel de impresión y en la barra de la traza sin desplazar nada.
      `Ctrl+E` y `F12` funcionan con el foco en cada una de estas ventanas: principal, impresión,
      dímeros y cámara. El log muestra `close_all_shutters` con el 532 nm en ALTO, la grilla queda
      "detenida" con el interlock `"E-STOP"`, y Play está deshabilitado hasta reconocerlo (QA-01).
- [ ] "Cerrar Todos" durante el nodo 1: la grilla queda en pausa, y en el log no hay ningún
      `open_shutter` hasta el Play siguiente (QA-02).
- [ ] Para cada causa de `aborted` (E-STOP, interlock `"NI-DAQmx"` simulado, `"Platina PI"`
      simulado, cierre del operador, watchdog): el comportamiento del nodo siguiente es el de la
      tabla por causa (QA-03). **Ninguna** causa lleva a una apertura sin acción del operador,
      salvo `acq_fault`.
- [ ] Con un nodo en curso están deshabilitados, con motivo: los botones de apertura del panel de
      obturadores, "Low power", "Mirror up", el deslizador y el campo de `Laser532Window`, y el
      Play de dímeros. "Cerrar Todos" sigue habilitado (QA-04).
- [ ] Con el foco en la ventana de la cámara, `F2` pausa la grilla; `F1` no hace nada (QA-05).
- [ ] En pausa, "Saltar nodo" avanza el índice, **no cambia ninguna línea DO** (log) ni mueve la
      platina, y la grilla sigue en pausa (QA-06).
- [ ] En pausa, `F1` arranca la traza manual: el Play de la grilla queda deshabilitado con su
      motivo. Al detener la traza manual, Play se habilita, y los bloques previos del nodo siguiente
      se registran con el obturador cerrado (QA-07).
- [ ] Un gancho de depuración cuelga el hilo de adquisición y no lo deja salir: el banner pasa de
      "Limpiando…" a "hilo colgado… reiniciá PyPrinting" al vencer el plazo, y el interlock sigue
      (QA-08).
- [ ] Con `legacy_timer`, ningún texto de la GUI dice "1.0 s" ni "garantía ≤ 20 ms", y el rótulo del
      panel de obturadores muestra la política global (QA-09, QA-15).
- [ ] Con `stream`, el rótulo del panel de obturadores dice "en uso por la traza de impresión ·
      latido OK". Pasar a "Sin límite" a mitad de un nodo no lo corta (QA-10).
- [ ] **Rutina sana larga**: Healing Pass con T_max 50 s y captura a los 45 s. El watchdog no corta
      ([INV] §10).

### 4.2 Valores y validación

- [ ] V_abs no baja de 0.010 V. Nodo 7 del guion (V_abs debajo de la base): termina "parada
      inmediata por V_abs", no "success". Repetido dos veces seguidas, pausa la grilla con el
      mensaje. Nodo 1 (captura real a 1.2 s) no lo dispara (QA-11).
- [ ] Región de Windows en Español (Argentina): escribir `1.5` y `1,5` en u da 1.50 las dos veces.
      Lo mismo en V_abs y en T_max (QA-12).
- [ ] T_max = 1.5 s con el vector A: aparece la advertencia del armado (QA-13).
- [ ] Contraste −1: el tooltip y el rótulo de V_abs dicen `I_new < V_abs` (QA-14).
- [ ] Se mantienen los puntos "Widgets y validación" del diseño.

### 4.3 Presets y conversión

- [ ] `AgNP_80nm_Nanodimeros.txt` y `Grilla_Extensa_10x10.txt` (`stop_mode = 3`, sin clave):
      banner "modo ambiguo", y Play bloqueado hasta elegir (QA-17).
- [ ] Presets armados a propósito, uno por problema: clave desconocida, `umbral_rel = 1,5`,
      `tmax = 90`, claves en ms y en pasos a la vez, sólo claves en ms. Cada uno muestra su mensaje;
      el de sólo ms **no** muestra el banner de pasos (QA-16).
- [ ] "Guardar en ms" escribe `format_version = 2` y la línea de versión mínima. Al recargar, no
      hay banner.
- [ ] "Tengo valores en pasos…" está a la vista junto a W_old / W_new. Con origen "legacy" y el
      T_ref medido (por ejemplo 10 ms), 20 / 20 da 200 / 200 ms, y la tarjeta muestra las
      consecuencias de los dos orígenes lado a lado (QA-19, D-5).
- [ ] "Consecuencias" con los dos vectores [DERIVADO]:

  | Vector | Backend | Escalón mínimo | ×2 | ×1.6 | ×1.4 |
  |---|---|---|---|---|---|
  | A: 940 / 940 / 94 ms, modo 1, u = 1.5 | `stream` | ×1.53 | 570-580 ms | 883-893 ms | no detecta |
  | A | `legacy_timer` (47 ms) | ×1.53 | 564-611 ms | lo que dé `detection_model` del motor: con pasos de 47 ms el cruce se cuantiza (17 pasos, ≈ 846-893 ms) y el modelo continuo (877-924 ms) no vale | no detecta |
  | L: 200 / 200 / 0 ms, modo 0, u = 1.5 | `stream` | ×1.50 | 100-110 ms | 167-177 ms | no detecta |

### 4.4 Estados, cola y datos

- [ ] Nodos 9 a 11 (tres caídas): pausa con diálogo que muestra el nivel del BS. Cinco "sin captura"
      seguidos: banner no bloqueante (QA-22).
- [ ] Nodo 4 (falla con exposición): entra a la cola como "en revisión", y el Healing Pass lo
      saltea salvo que el operador lo pase a pendiente (QA-23, hasta que conteste P4).
- [ ] Pausa a los 3 s de un nodo y Play: aparece la pregunta de una línea con la exposición (QA-24).
- [ ] La curva "R" de `Láser 2` coincide bloque a bloque con `window_means()` del detector (se
      compara con la marca de "Re-evaluar"). Si el contrato de R4-16 no está, la opción aparece
      deshabilitada (QA-25).
- [ ] "Marcar como impresa (operador)" se cuenta aparte en el resumen y en `intentos_<lote>.csv`
      (QA-27).
- [ ] Sin tocar "Extra info", `grid_info.txt` y el HDF5 dicen "no informado" (QA-28).
- [ ] Healing Pass: el primer intento conserva traza, `confocal_scan` y atributos en el HDF5
      (G-2 ampliado).

### 4.5 Accesibilidad

- [ ] Captura del mapa con los 13 estados, pasada por un filtro de escala de grises y otro de
      deuteranopía. Se distinguen sin color, en especial: impresa / impresa en el reintento,
      imprimiendo / reintentando, abortada / falla con exposición (QA-29).
- [ ] Con el brillo al mínimo, a 1 m: las líneas de umbral y su estado "fija" se leen en el rótulo
      (QA-30).

### 4.6 Lo que no se tiene que perder (regresión del uso actual)

- [ ] Durante una grilla, la cámara sigue en vivo con la misma cadencia que sin grilla.
- [ ] En cada nodo la traza se activa sola en su widget. Curvas, colores y botones FFT como hoy.
- [ ] "Save trace" funciona durante la impresión. Power BS muestra el canal BS de la sesión.
- [ ] Fuera de la impresión, `F1` y `F2` hacen lo mismo que hoy, y `F8`, `F9` y `F10` también. `F9`
      hereda su defecto actual (§3.1, G-5) hasta que se corrija por separado.

### 4.7 Correcciones a la lista del diseño

- "Cada estado del mapa se reconoce sólo por la forma": correcto como requisito, pero **falla** con
  la tabla actual de §3.3. Se mantiene y se corrige la tabla (QA-29).
- "Con W_new = 940 el aviso de 50 Hz no aparece": el aviso no está especificado (QA-42).
- "Con u = 1.5, 940 / 940 / 94 ms: ×1.53; 570-580 ms…": se rotula como vector A y se agregan el
  vector L y la fila de `legacy_timer` (D-12).
- "Tres fallas seguidas pausan la grilla": se agregan las tres caídas (QA-22).

---

## 5. Preguntas para el investigador (se contestan en una línea)

La P1 del diseño se reemplaza por P-A y P-B. La P13 depende de P-A. Las P2 a P12 y P14-P15 siguen
en pie.

1. **P-A.** Los 20/20, ¿los escribís en el widget de la **traza** de PyPrinting legacy
   (`printing2`) o en el panel de impresión de 3.0? Define qué es "como hoy" (§1.2).
2. **P-B.** ¿Podés copiar 5 a 10 `NP_xxx.txt` recientes del legado (y, si hay, de 3.0 en
   `7f5d10a`)? De su eje sale la cadencia real de cada programa en la PC del banco, sin tocar el
   hardware (§1.1, D-6).
3. **P-C.** En el legado, ¿qué `Umbral` y `Umbral down` usás? ¿También 1.5 y 0.5?
4. **P-D.** ¿Cuántos nodos seguidos "sin captura" te harían sospechar de una falla del banco?
   (propuesta: 5, QA-22)
5. **P-E.** Después de un E-STOP en PyPrinting, ¿la grilla queda **detenida** y hay que reconocer el
   bloqueo (propuesta), o sólo en pausa? (QA-01, QA-03)
6. **P-F.** Los presets "AgNP 80 nm — Nanodímeros" y "Grilla Extensa 10×10" tienen `stop_mode = 3`:
   ¿querían el Híbrido o el Confocal reescalado? (QA-17)
7. **P-G.** ¿Ajustás la potencia del 532 (ventana Láser 532), el filtro o el espejo durante una
   grilla? Si sí, ¿entre nodos o dentro de un nodo? (QA-04)
8. **P-H.** Si apretás "Cerrar Todos" durante un nodo, ¿la grilla se pausa (propuesta)? (QA-02)
9. **P-I.** Un nodo que estuvo expuesto y no llegó a decidir (falla, watchdog o pausa), ¿se
   reintenta solo en el Healing Pass, o queda "en revisión" hasta que lo mires (propuesta mientras
   no conteste P4)? (QA-23, QA-24)
10. **P-J.** ¿La PC del banco tiene Windows en español (Argentina)? ¿Qué separador decimal usa?
    (QA-12)
11. **P-K.** ¿Usás el modo dímeros con este mismo criterio? ¿Entra en C-01? (QA-32)
12. **P-L.** La concentración de NaCl y la potencia en la pupila, ¿se miden en cada lote, o preferís
    heredar las del lote anterior, marcadas como heredadas? (QA-28)

---

## 6. Veredicto

**`ERGONOMIC_HAZARD_REJECTED`** en la forma actual del diseño.

**Por qué.** Tres hallazgos críticos del mismo tipo:
- PyPrinting no tiene un corte de emergencia al alcance de las ventanas que se miran durante una
  grilla (QA-01);
- el corte que sí existe, "Cerrar Todos", no detiene la grilla, y el nodo siguiente vuelve a abrir
  (QA-02);
- el diseño no dice qué hace la grilla después de un aborto que no sea del watchdog (QA-03).

Los tres son omisiones, no errores del diseño. El problema de fondo existe hoy en `main`, pero una
ronda que define ejecución, pausa y bloqueos no puede dejarlo sin definir.

**Qué lo destraba.** Pasa a **`MINOR_UX_POLISH_NEEDED`** cuando incorpore:
- QA-01 a QA-03, con su pasaje por las Rondas 1-2 de instrumentación (tocan obturadores);
- QA-04 a QA-09, que son los bloqueos y estados de ejecución que faltan;
- la corrección del supuesto de P0 (§1, QA-18), sin decidirlo antes de P-A y P-B.

El resto (QA-10 a QA-42 salvo QA-18) puede resolverse en la reconciliación de la Ronda 4 (R4-16 a
R4-23).

**Lo que el diseño hace bien y conviene no perder:**
- las ventanas en ms con su equivalente en bloques calculado por el motor;
- "Consecuencias del preset": avisa, no bloquea, y no inventa un objetivo de latencia;
- los motivos de bloqueo componibles, con dos barreras independientes para los atajos (G-5);
- el registro por intento sin pisar datos;
- estados con forma además de color, aunque todavía no alcance (QA-29);
- "Re-evaluar con el panel" usando la misma clase del motor;
- la disciplina de `[fuente: …]` en los tooltips;
- no tocar la cámara ni la disposición de la traza, que es lo que el investigador usa hoy.

Los hallazgos G-1 a G-10 están todos confirmados en el código (§3.1).

---

## 7. Segunda pasada sobre v2

Objeto: `c01_ronda3/gui_design_v2.md`, sobre todo §1 (disposición de los 42 hallazgos), §5 (los tres
cortes del haz) y §6, más la paridad de P0 con el legado. Las decisiones de la sexta y la séptima
ronda ([INV6], [INV7]) son vinculantes. **P-H no se reabre**: "Cerrar todos" no pausa la grilla. Lo
que se audita es si la v2 hace esa decisión segura y explícita.

**Evidencia nueva de esta pasada**, en el scratchpad de la sesión:
- `qa_legacy_arming.py`: reproduce las ventanas de `printing2/Trace_pp.py:405-420` y la regla de
  `Printing_pp.py:793` frente a la regla de arranque del motor ([R2-ARQ] §4.2);
- `qa_modal_shortcut.py`: prueba, con el PyQt6 del `.venv` del repositorio (`QT_QPA_PLATFORM =
  offscreen`), un `QShortcut` con `ApplicationShortcut` y un diálogo modal de aplicación abierto.

### 7.1 Hallazgos cerrados

La v2 da disposición a los 42 hallazgos, y la de cada uno es correcta. **Cerrados en el diseño**
(la Ronda 4 los implementa y los prueba con la lista de la v2, §10):

- **Sin observaciones:** QA-04 a QA-09, QA-11 a QA-17, QA-19 a QA-21, QA-23 a QA-28, QA-30 a QA-42 y
  D-1 a D-14.
- **QA-03:** cerrado. La tabla por causa (§5.3) y el invariante que se prueba en el log DO son lo
  que pedía la auditoría. Le faltan las filas de N-3 (§7.3).
- **QA-11 y QA-22**, aviso en vez de pausa: aceptable. Es coherente con [INV6] P3 y [INV7] P-D, y
  queda como Q-3.
- **QA-17**, sin bloquear Play: aceptable. Lo resolvió [INV7] P-F con la numeración del panel.
- **QA-29:** cerrado. Queda un detalle menor (N-9).

### 7.2 Hallazgos que siguen abiertos

| ID | Qué resolvió la v2 | Qué falta | Nuevo |
|---|---|---|---|
| QA-01 (parada de emergencia) | botón en tres lugares; `Ctrl+E` / `F12` de alcance de aplicación; grilla DETENIDA; Rearmar como acción aparte; una sola parada en modo satélite; nunca se libera sola. Bien resuelto en la GUI | el atajo y los botones **no funcionan con un diálogo modal abierto**, y el cierre puede quedar trabado en el hilo GUI | N-1, N-2 |
| QA-02 ("Cerrar todos · la grilla sigue") | rótulo que cambia con la grilla corriendo; tooltip que nombra la pausa y la parada; banner; manual; tabla de los cuatro cortes; predicado de aborto para no leer 40 s de oscuridad; nodo "expuesto sin decisión" con la regla P4. La decisión queda **explícita** | no queda **segura** en tres casos: entre nodos, con el backend de tick finito, y en la reapertura inmediata | N-3, N-4, N-5 |
| QA-10 (estado del watchdog y de los obturadores) | rótulo "en uso por la traza de impresión · latido OK" con la concesión | con el tick finito, y en todos los backends para los botones del dock, el operador ve el 532 "cerrado" mientras está abierto | N-6 |
| QA-18 (P0) | P0 = legado: modo 0, u = 1.5, d = 0.5, 200 / 200 ms, sin persistencia, 40 s | la paridad es parcial (§7.4) y nadie la prueba contra el legado | N-7, N-8, N-10 |

### 7.3 Hallazgos nuevos que introduce la v2 (o que la v2 deja a la vista)

| ID | Sección de la v2 | Sev. | Problema | Propuesta |
|---|---|---|---|---|
| N-1 | §5.1 ("registrados una sola vez en la ventana principal"), §6.7 (`F2`) | ALTA | **Con un diálogo modal de aplicación abierto, el atajo de emergencia no dispara**, y los botones de emergencia tampoco se pueden pulsar, porque el modal bloquea las demás ventanas. Lo probé: `QShortcut(F12)` con `ApplicationShortcut` en la ventana principal dispara desde otra ventana sin modal (1 de 1), y **no dispara** con un `QDialog` modal de aplicación abierto (0 de 1). Un filtro de eventos instalado en `QApplication` sí ve la tecla (`qa_modal_shortcut.py`). Hay 66 llamadas a diálogos modales en `measurements.py`, `camera.py` y `app.py` (`QMessageBox` estáticos, `QFileDialog.get…`, `.exec()`). Por ejemplo, un diálogo de guardar imagen de la cámara abierto a mitad de una grilla deja la parada sin atajo ni botón. Afecta igual a `F2` | Implementar `Ctrl+E` / `F12` (y `F2`) con un **filtro de eventos en `QApplication`** que atienda `ShortcutOverride` / `KeyPress` una sola vez por pulsación. Funciona con modales y resuelve de paso el atajo ambiguo del modo satélite: un único manejador por proceso. Regla adicional: ningún diálogo modal de aplicación mientras la grilla corre o hay un obturador abierto; usar no modales o banners. Sumar a la lista de verificación: con un `QFileDialog` abierto desde la cámara, `Ctrl+E` cierra los cuatro obturadores |
| N-2 | §5.1, paso 1 ("desde el hilo GUI… No espera a ningún hilo") | ALTA | `close_all_shutters()` toma `_nidaq_lock` bloqueando (`core/nidaq.py:529`). Si otro hilo lo tiene, la parada **espera**: ≈ 100 ms en el peor caso normal (3 reintentos de cierre de 50 ms), y sin cota si un hilo quedó colgado dentro del candado, que es el caso que [R2-INS] §6.1 punto 2 señala como no cubierto. La GUI se congela justo en la emergencia, sin decir nada. Con un hilo colgado, además, "Rearmar" no se habilita nunca | La parada cierra desde un hilo propio, con `acquire(timeout = 0.2 s)`. Si no consigue el candado o el cierre no se confirma: banner rojo persistente "No se pudo confirmar el cierre: la placa está tomada por otro hilo. **Cortá la emisión con la llave del láser** y reiniciá PyPrinting". La GUI no se bloquea. Con un hilo colgado, el banner de Rearmar dice que hay que reiniciar. Va a las Rondas 1-2 de R4-17 |
| N-3 | §5.2 ("Con una sesión de impresión activa…"), §5.3, §6.5 ("entre nodos incluido") | ALTA | **"Cerrar todos" entre nodos no está definido.** La grilla también abre obturadores en el autofoco, el escaneo de deriva sobre P0 y el escaneo previo a imprimir. Si el operador cierra durante uno de ellos, la grilla sigue ([INV7] P-H) y la corrección se calcula sobre oscuridad, y se aplica sin aviso: el escaneo de deriva **reemplaza** `startX/startY` por el centro de masa sin ningún tope (`measurements.py:2463-2466`), y el autofoco mueve Z al `argmax` del perfil, sin validar la señal (`focus.py:291-297`). Los nodos siguientes se imprimen corridos o desenfocados, y se registran como válidos. La parada de emergencia aborta esos escaneos (§5.1, paso 3) sin decir si su corrección se aplica | Filas nuevas en §5.3: "Cierre del operador o parada durante el autofoco, la deriva o el escaneo previo" → el paso se **invalida**: no se aplica su corrección, se conserva la anterior y el paso se repite antes del nodo siguiente (P-a, §7.6). Banner: "Cerraste los obturadores durante el autofoco del nodo 18: se repite antes de imprimir". Aparte, y previo a C-01: un tope de plausibilidad para la corrección de deriva (rechazar \|Δ\| mayor que k veces la tolerancia) y para el autofoco (sin pico, no se mueve) |
| N-4 | §5.3 ("Con el backend de tick finito… La tabla vale para … Cerrar todos") | ALTA | El predicado de aborto es un concepto de la sesión nueva. En `legacy_timer`, que es el backend por defecto en la fase (a) y lo primero que corre en el banco, el camino es el de `DEC-037` "sin tocar" ([R2-ARQ] §5.9). Si no se agrega ahí, "Cerrar todos" deja el nodo leyendo oscuridad: la rama d = 0.5 lo rotula "timeout" (`measurements.py:2408, 2416-2418`), y el Healing Pass lo **reexpone 50 s**, que es justo lo que la regla P4 prohíbe. La v2 afirma que la tabla vale sin decir cómo | Sumar a R4-15 / R4-17: en `legacy_timer`, `grid_trace_detect` consulta una bandera de cierre del operador, marca el nodo "expuesto sin decisión" y lo deja "en revisión". Toca el camino de `DEC-037` y decide sobre la reexposición: nunca exento. Sumar el punto a la lista con ese backend |
| N-5 | §5.2 ("el nodo siguiente … vuelve a abrir su obturador de la forma normal") | MEDIA | Después de "Cerrar todos", el nodo siguiente abre en ≈ 0.6-1 s (movimiento, `down_flipper` y 0.5 s de espera, bloques previos). Si el operador cerró por algo que vio en el banco, el haz vuelve antes de que pueda leer el banner. La decisión P-H se respeta igual si la grilla sigue **después de una espera visible** | Espera de, por ejemplo, 3 s después de un cierre del operador, con cuenta regresiva en el banner: "El nodo 18 abre en 3 s · [Pausa (F2)] [PARADA]". La grilla sigue sola al terminar la cuenta. Pregunta P-b (§7.6) |
| N-6 | §6.5 (botones por láser bloqueados durante la grilla), §6.6 | MEDIA | Los botones del dock de obturadores reflejan clics y cierres forzados (`core/shutters.py:117-190`), no las aperturas de las rutinas: durante la impresión, el botón del 532 se ve **sin marcar y deshabilitado** mientras el obturador está abierto. Con la concesión, la v2 agrega un rótulo; con el tick finito, "sigue como hoy". Los indicadores de estado abierto/cerrado son un requisito de alto contraste | El temporizador de 1 s del dock (`shutters.py:81-83`) pinta cada botón con el estado real, que ya existe en `get_open_shutter_names()` (`nidaq.py:559`): marcado y rojo "ABIERTO (rutina)" aunque esté deshabilitado. En todos los backends |
| N-7 | §4.3, §4.6 (P0 = vector L), §6.2 (advertencia "armado … W_new + W_old = 0.40 s") | MEDIA | **P0 no reproduce el arranque del legado** (§7.4): el legado no evalúa nada hasta el paso M + M2 = 40 (≈ 400 ms) y pierde toda captura de los primeros ≈ 100 ms; el motor evalúa desde el bloque M + 1 = 21 con una base creciente ([R2-ARQ] §4.2). Además, la v2 se contradice: su advertencia de pre-flight supone un armado de W_new + W_old (la regla del legado y la recomendación de "armado" de [R2-MET] §4.2), pero el contrato del motor arma a W_new + T_b | Decidir en la reconciliación entre la regla de [R2-ARQ] §4.2 y el armado de [R2-MET] §4.2 (propuesta: el armado de [R2-MET], que coincide con el legado y evita el éxito espurio por la apertura del obturador). La advertencia de §6.2 tiene que usar el armado que devuelva el motor. Documentar las diferencias de §7.4 en la descripción de P0. Pregunta P-d |
| N-8 | §4.6, §11 (no hay fila de paridad con el legado) | ALTA | La paridad de [R2-ARQ] §5.1 (`tests/test_print_stop_detector_parity.py`) compara el motor con el **3.0 actual** (pasos de 47 ms). Ahora el blanco de P0 es `printing2`, y ningún test lo compara con él. Tampoco BANCO-32, cuyo A/B es `legacy_timer` contra `stream`, dos caminos de 3.0. "P0 reproduce el legado" queda como una afirmación sin prueba | Fila nueva en §11: una referencia de `printing2/Trace_pp.py:405-420` más `Printing_pp.py:793`, **sólo en los tests**, con la paridad exigida en régimen (±1 paso) y las diferencias del arranque documentadas como tales. La línea de base de BANCO-32 incluye el comportamiento del legado (la tasa de éxito que el investigador ve hoy con `printing2`) |
| N-9 | §6.3 (glifos) | BAJA | "Caída de señal" (triángulo hacia abajo) y "parada sin escalón" (triángulo a la derecha) tienen el mismo relleno Peach: sólo los distingue la orientación, a 14 px | Otra familia de glifo para uno de los dos (por ejemplo, cuadrado con barra para "parada sin escalón") |
| N-10 | §6.9 (`presets/P0_paridad_legacy.txt`) | BAJA | P0 = 200 ms depende de un T_ref del legado sin medir (R4-23, Q-1). Si el legado corría a 12 ms, 20/20 son 240 ms | El archivo guarda `t_ref_ms = 10`, `t_ref_fuente = "comentario de 2019, sin medir"` y los pasos originales (20/20). Cuando llegue Q-1, se regenera y queda la procedencia |
| N-11 | §5.3, §5.4 | ALTA | **Con la detección ciega desde el arranque, ninguna salvaguarda actúa antes de exponer varios nodos.** Si la grilla arranca con el espejo abajo, la luz va al espectrómetro ([INV] R2-4) y el fotodiodo confocal no ve nada; el software no conoce la posición del espejo ([INV] R2-5). No hay caída, porque R ≈ 1 desde el principio: cada nodo expone 40 s, imprime sin ser detectado, y el aviso llega al 5.º nodo "sin captura" ([INV7] P-D), ≈ 3.5 min después. La v2 ya tiene los datos para verlo en el **primer** nodo: los bloques previos (oscuros) y los primeros después del asentamiento, en el fotodiodo y en el BS, que ve la apertura ([INV] Q14) | Regla del motor: si al abrir el BS sube y el fotodiodo de detección no sube por encima de, por ejemplo, 1.1 veces su nivel oscuro, el nodo se corta en el acto como "sin señal de detección" (causa nueva de §5.3) y aparece un banner: "El fotodiodo no ve luz y el BS sí: revisá el espejo de detección". Si **ninguno** sube, es "el obturador no abrió o el láser está apagado". Pausar o sólo avisar lo decide el investigador (P-c). No es una pausa por fallas seguidas: el Healing Pass no la arregla |

### 7.4 P0 frente al legado

Criterio del legado (`printing2/Printing_pp.py:793`): `I_new > I_old·umbral` **o**
`I_new < I_old·umbral_down` **o** timeout, evaluado una vez por paso, sin persistencia, a ≈ 10 ms.
Ventanas: `Trace_pp.py:405-420`, con `data1.append` antes del cálculo (`:386`).

| Aspecto | Legado (`printing2`) | P0 en el motor (v2) | ¿Paridad? |
|---|---|---|---|
| Fórmula de parada | `I_new > 1.5·I_old` o `I_new < 0.5·I_old` o T_max | modo 0 con u = 1.5, más la rama d = 0.5 y T_max = 40 s | **sí**. El motor agrega `I_old > 0` (`measurements.py:2360`), sin efecto práctico |
| Persistencia | ninguna: para en la primera evaluación verdadera | τ_hold = 0; el modo 0 para en la primera | **sí** |
| Ventanas en régimen | I_new = los M = 20 pasos anteriores, **sin el más nuevo** (`data1[ptr−M:ptr]` después del `append`); I_old = los M2 = 20 anteriores | I_new = los últimos 20 bloques, **con** el más nuevo; I_old = los 20 anteriores | casi: el legado decide **un paso después** (≈ +10 ms). En la simulación: escalón en el paso s ≥ 30 → legado s + 11, motor s + 10 |
| Arranque | **ciego hasta el paso 40** (M + M2): antes, `I_old` es un corte vacío (NaN) y toda comparación da falso. Una captura en los primeros ≈ 10 pasos (≈ 100 ms) **no se detecta nunca**: cuando la base se habilita, ya contiene el escalón. Una captura entre los pasos 19 y 30 se decide en el paso 40-41 | evalúa desde el bloque 21 (M + 1), con una base que crece desde el primer bloque después del asentamiento. Detecta las capturas tempranas en el bloque 20-30 | **no** (N-7). El motor es mejor, pero no es "como el legado"; y la base creciente del arranque es la zona que [R2-MET] §1.2 marca como expuesta al transitorio de apertura |
| Evaluación | una vez por paso de ≈ 10 ms **sin medir**; cada paso promedia 1 ms de señal | una vez por bloque de 10 ms exactos; cada bloque promedia 10 ms | en el tiempo, sí, **si** el legado corre a 10 ms (Q-1, N-10). En el ruido, no (D-7) |
| T_max | reloj de pared desde `openShutter` + 10 ms; 20 s por defecto (`Printing_pp.py:73`), 40 s en la práctica | reloj de muestreo desde la apertura confirmada; 40 s | sí; el valor espera Q-2 |
| Rama de caída | cierra y sigue con el nodo siguiente (el legado no tiene Healing Pass) | "caída de señal", a la cola del Healing Pass | el corte es el mismo; lo que pasa después es política de la grilla, no del criterio |
| Asentamiento | ninguno: el flanco de apertura entra en la base del paso 40 | 50 ms excluidos del criterio | no; es una mejora |

Simulación (`qa_legacy_arming.py`, escalón limpio ×2, M = M2 = 20; paso de decisión, legado / motor):

| Escalón en el paso | 5 | 10 | 19 | 25 | 30 | 40 | 60 |
|---|---|---|---|---|---|---|---|
| Legado | **no detecta** | **no detecta** | 40 | 40 | 41 | 51 | 71 |
| Motor | 20 | 20 | 29 | 35 | 40 | 50 | 70 |

**Conclusión.** P0 reproduce el criterio del legado (fórmula, u, d, ventanas, sin persistencia, una
evaluación por paso) **en régimen, con un paso de diferencia**. No lo reproduce en los primeros
W_new + W_old ≈ 400 ms después de abrir. Como las capturas tardan de 1 a 20 s ([INV] R3), la
diferencia toca pocos nodos, pero la afirmación "P0 reproduce el legado" tiene que decir esto, y un
test tiene que probarlo contra el legado (N-8).

### 7.5 Filas nuevas para la reconciliación de la Ronda 4

| # | Tema | Hallazgos | Estado propuesto |
|---|---|---|---|
| R4-25 | Parada de emergencia y `F2` con un filtro de eventos en `QApplication`; sin modales de aplicación con la grilla corriendo o un obturador abierto | N-1 | BLOQUEANTE, dentro de R4-17 |
| R4-26 | Cierre sin esperar en el hilo GUI (hilo propio, candado con plazo, remedio físico) | N-2 | BLOQUEANTE, dentro de R4-17 |
| R4-27 | Pasos entre nodos invalidados por un cierre o una parada; topes de plausibilidad de la deriva y del autofoco | N-3 | BLOQUEANTE, dentro de R4-17 |
| R4-28 | "Cierre del operador" en el camino `legacy_timer` | N-4 | BLOQUEANTE, dentro de R4-15 y R4-17 |
| R4-29 | Armado del criterio ([R2-ARQ] §4.2 contra [R2-MET] §4.2) y test de paridad contra `printing2` | N-7, N-8 | ABIERTA (metrología + arquitectura) |
| R4-30 | Indicadores de obturador con el estado real | N-6 | CERRADA en diseño con esta propuesta |
| R4-31 | "Sin señal de detección" al abrir (fotodiodo contra BS) | N-11 | ABIERTA; depende de P-c |

### 7.6 Preguntas para el investigador (se contestan en una línea)

1. **P-a.** Si "Cerrar todos" cae durante el autofoco o el escaneo de deriva entre nodos, ¿se
   repite ese paso antes de imprimir (propuesta) o se saltea conservando la corrección anterior?
2. **P-b.** Después de "Cerrar todos" durante un nodo, ¿aceptás una espera visible de 3 s antes de que
   abra el nodo siguiente, con Pausa y PARADA en el banner? La grilla sigue igual.
3. **P-c.** Si al abrir el obturador el BS ve luz y el fotodiodo de detección no (espejo abajo), ¿el
   nodo se corta y avisa (propuesta), o además se pausa la grilla?
4. **P-d.** En P0, ¿querés también la paridad del arranque (el legado no evalúa los primeros
   ≈ 400 ms y pierde las capturas de los primeros ≈ 100 ms), o preferís que P0 detecte esas capturas?

### 7.7 Veredicto de la segunda pasada

**`MINOR_UX_POLISH_NEEDED`**: la v2 **pasa a la Ronda 4**, con condiciones.

- **Por qué pasa.**
  - Los tres críticos de la primera pasada quedan resueltos en el diseño, con las decisiones del
    investigador.
  - "Cerrar todos · la grilla sigue" queda **explícito** en el rótulo, el tooltip, el banner, el
    manual y la tabla de los cuatro cortes.
  - Los 42 hallazgos tienen una disposición correcta.
  - Lo que falta no es de arquitectura de la información: son casos de la secuencia de corte, que la
    v2 ya puso en R4-17 como bloqueante y nunca exento.
- **Condiciones.**
  1. Las Rondas 1-2 de instrumentación de R4-17 incluyen N-1 a N-4 (R4-25 a R4-28). **Sin ellas, §5
     no se implementa**: la parada tiene que funcionar con un modal abierto y sin congelar la GUI, y
     "Cerrar todos" tiene que ser seguro entre nodos y con `legacy_timer`.
  2. Antes de rotular P0 como "paridad con el legado" en la GUI, se resuelve N-7 y existe el test de
     N-8 (R4-29). Mientras tanto, la descripción del preset dice "paridad en régimen; el arranque
     difiere".
  3. N-11 entra en la reconciliación con la respuesta a P-c.
  4. N-5, N-6, N-9 y N-10 se resuelven en la reconciliación normal.
