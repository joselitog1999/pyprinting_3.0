# C-01 / R4-17 — mini Ronda 1 — Abogado del diablo (`devil-advocate`)

Estado: COMPLETO (2026-10-01). Análisis solamente: no se modificó código ni tests, no se ejecutó nada
contra hardware. Único archivo escrito: este.

**Objeto.** La parte de hardware de lo que se decidió en las Rondas 1-3 de C-01 y que falta validar
antes de implementar:
- la parada de emergencia propia de PyPrinting (`c01_ronda3/gui_design_v2.md` §5.1, N-1, N-2);
- "Cerrar todos · la grilla sigue" (§5.2, [INV7] P-H, N-3, N-4, N-5, [INV9] P-a, P-b);
- la confirmación a baja potencia (R4-3, [INV6] P4, P13);
- retomar después de rearmar ([INV8] Q-4) y la parada única en modo satélite ([INV8] Q-5).

**Qué leí.** `gui_design_v2.md` §0-§6 y §10-§12; `qa_ux_audit.md` §7; `RESPUESTAS_INVESTIGADOR.md`
rondas 1 a 9; `DEC-036` y `DEC-037`; y, orientado con `graphify explain/query`, el código de
`core/nidaq.py`, `core/shutters.py`, `modules/measurements.py`, `modules/trace.py`,
`modules/focus.py`, `modules/confocal.py`, `app.py`, `config.py`, `pyspectrum/window.py` y
`pyspectrum/modules/hardware_session.py`. Además, `git diff --stat 7f5d10a HEAD` sobre el camino de
impresión.

**Marcas.** [CÓDIGO] archivo:línea leído en `main` (HEAD `7aab0d8`); [DERIVADO] cuenta mía, con los
supuestos a la vista; [BANCO] sólo se resuelve en el banco; [INVn] respuesta del investigador de la
ronda n. **Ninguna cifra de probabilidad es medida**: son juicios ordinales (alta/media/baja) con su
razón.

**Regla que me apliqué** (`.claude/agents/devil-advocate.md` §5, R1-12): "el legado no podía
funcionar" es una alarma, no un hallazgo. Nada de lo que sigue afirma que `7f5d10a` o el legado no
funcionen; lo que se señala es que el código que se va a tocar **no es** el que imprime en el banco
(§6).

---

## 0. Lo más crítico, en una tabla

| # | Hallazgo | Evidencia | Gravedad |
|---|---|---|---|
| 1 | **El orden de §5.1 (cerrar, después interlock) tiene una carrera**: entre los dos pasos, un hilo de rutina puede reabrir. El orden seguro (interlock, después cerrar) ya existe en `trip_shutter_interlock` | `nidaq.py:305-308`; rutinas en `confocalThread`, `app.py:728-732`; aperturas en `measurements.py:2319`, `trace.py:586`, `focus.py:376` | ALTA |
| 2 | **La cadena de la grilla no consulta ningún estado entre etapas**: el autofoco emite su fin "siempre" y la grilla mueve la platina y llama a abrir. Una pausa o una parada que llega por señal se procesa **después** de esa apertura. La afirmación "la grilla detenida no emite más movimientos" es falsa hoy | `focus.py:395`; `measurements.py:2294-2322`; `grid_pause` encolado, `measurements.py:1683-1684, 2937-2946` | ALTA |
| 3 | **"Retomar desde el nodo pendiente" reimprime un nodo ya impreso** si la parada cae entre la decisión `success` y el avance del índice (escaneo posterior, `sleep`): el índice sólo avanza en `_grid_detect` y el reanudar usa `i_global` | `measurements.py:2413-2415, 2442-2446, 2517-2521, 2840, 1966-1972` | ALTA (doble partícula) |
| 4 | **"4 de 4 confirmados cerrados" puede ser falso**: si la escritura falla y el software no creía nada abierto, `_all_closed_confirmed()` da verdadero y no queda ningún obturador "sin confirmar". Rearmar se habilitaría sin una sola escritura exitosa | `nidaq.py:409-411, 553-562`; `DEC-036` ("confirmado" = la placa aceptó la escritura) | ALTA |
| 5 | **La bandera de cierre del operador no alcanza si sólo la mira el detector**: la traza vuelve a abrir el obturador por su cuenta al arrancar, y el cierre que cae en el `sleep(0.5)` previo a la apertura se deshace medio segundo después, sin "nodo en curso" que lo registre | `measurements.py:2318-2322`; `trace.py:580-589` | ALTA |
| 6 | **Un falso "no se ve la NP" es peor que un falso "se ve"**: el primero reexpone 50 s a alta potencia sobre una NP impresa y puede fabricar un dímero, que en este laboratorio es un objeto de estudio y por lo tanto un artefacto que se confunde con señal | §5; `measurements.py:2860` (T_max + 10 s en el Healing Pass) | ALTA (científica) |

**Veredicto: `HIGH_RISK_ASSUMPTIONS`.** El diseño de la GUI es correcto en lo que promete al operador,
pero tres de sus promesas de hardware se apoyan en supuestos que el código actual contradice (orden de
cierre, cadena que no se detiene, índice pendiente). Ninguna es una objeción a P-E, P-H o Q-4: son
condiciones de implementación que tienen que estar en el contrato de la Ronda 2 de R4-17.

---

## 1. Supuestos del diseño contra el código (pregunta 6)

| S | Supuesto (dónde) | Qué dice el código | Veredicto |
|---|---|---|---|
| S1 | "`close_all_shutters()`… es seguro entre hilos por `_nidaq_lock`. **No espera a ningún hilo**" (§5.1 paso 1) | Toma el `RLock` bloqueando (`nidaq.py:537`). Con la placa en falla, cada uno de los 3 reintentos vuelve a intentar **crear** la tarea DAQmx dentro del candado (`nidaq.py:541-546` → `352-375`), con un costo que no está medido | **REFUTADO** (confirma N-2 y lo agrava: el peor caso no es un hilo colgado, es también la placa ausente) |
| S2 | Orden "1 cierra · 2 activa el interlock `E-STOP`" (§5.1) | `open_shutter` consulta los interlocks **dentro** del candado (`nidaq.py:466-471`), así que interlock-después-cierre deja una ventana en la que una rutina del `confocalThread` abre después del cierre y antes del interlock. `trip_shutter_interlock` hace el orden correcto (`nidaq.py:305-308`) | **REFUTADO** el orden; la primitiva correcta ya existe |
| S3 | "La grilla detenida simplemente no emite más movimientos" (§5.1, "Lo que no hace") | `focus_autocorr_lin_x2` emite `autofinishSignal` "siempre, éxito o abort" (`focus.py:395`); `grid_finish_autofoco` mueve XY, pulsa el flipper y llama a `_grid_trace` sin mirar ningún estado (`measurements.py:2305-2315`); `on_scan_finished` mueve y llama a `_grid_detect` → `_grid_move` (`2499`, `2521`, `2843`). Los retornos de `open_shutter` se ignoran (`2319`, `focus.py:376`) | **REFUTADO** hoy. Con el interlock, el láser no se abre, pero la platina se mueve y la traza corre a oscuras |
| S4 | "Rearmar se habilita sólo cuando los cuatro obturadores están confirmados cerrados" (§5.1) | Ver hallazgo 4: con falla de escritura y nada abierto según el software, no queda ninguno en `_unconfirmed_shutters` | **REFUTADO** como condición suficiente |
| S5 | "Cerrar todos" "cierra los cuatro obturadores ya, igual que hoy" (§5.2) | Hoy corre en el hilo GUI (`shutters.py:308-315`), **desmarca los botones antes de escribir** (`309-313`) e **ignora el retorno** (`314`). Si la escritura falla y el software no creía nada abierto, no hay banner: falla en silencio | **CONFIRMADO** que cierra; **REFUTADO** que avise si no puede |
| S6 | N-4: en `legacy_timer`, el cierre del operador termina en "timeout" y el Healing Pass lo reexpone | La rama `I_new < I_old·umbral_down` rotula "timeout" (`measurements.py:2408, 2416-2418`) y el Healing Pass toma todos los "timeout" (`2828`). Además, `umbral_down` arranca en **0.0** en el backend (`1614`): con un preset que no lo fije, el nodo lee oscuridad hasta `T_max` | **CONFIRMADO** y ampliado |
| S7 | N-3: el autofoco y la deriva aplican sin validar lo que miden | El autofoco mueve Z al `argmax` de la correlación (`focus.py:418-424`) y abre una sola vez antes de las dos iteraciones (`376-381`): un cierre a mitad de la primera deja la segunda a oscuras. La deriva reemplaza `startX/startY` por el centro de masa (`measurements.py:2462-2466`) | **CONFIRMADO** |
| S8 | Q-5: "una sola parada" en modo satélite resuelve el choque de atajos | La E-STOP de PySpectrum **no activa ningún interlock de obturadores** (`hardware_session.py:150-208`; fuera de `nidaq.py` y `config.py` nadie llama a `set/trip_shutter_interlock`). Su filtro de teclas **excluye** a propósito las ventanas del satélite (`pyspectrum/window.py:87-95`) | **PARCIAL**: el choque de atajos se resuelve con un solo filtro, pero hoy una E-STOP de PySpectrum no impide que la grilla de PyPrinting reabra |
| S9 | "Retomar desde el nodo pendiente" (Q-4) es el nodo en el que se paró | El reanudar llama a `_grid_move()` en `i_global` (`measurements.py:1966-1972`); `i_global` sólo avanza en `_grid_detect` (`2840`) | **REFUTADO** como definición implícita (hallazgo 3) |
| S10 | La espera de 3 s (P-b) va "antes de que abra el nodo siguiente" | La primera apertura después de un cierre no es la de impresión del nodo siguiente: es el escaneo confocal posterior (`grid_scan`, `measurements.py:2442-2446`), o el autofoco (`focus.py:376`), o la traza (`trace.py:586`) | **PARCIAL**: la espera tiene que ir antes de la **primera apertura de cualquier tipo** |

Diez supuestos revisados: uno confirmado tal cual (S7), dos confirmados con ampliaciones (S5, S6), dos
parciales (S8, S10) y cinco refutados (S1, S2, S3, S4, S9).

---

## 2. "Cerrar todos · la grilla sigue" (pregunta 1)

P-H no se reabre: la decisión es del investigador. Lo que se audita es si **es seguro cuando el operador
lo usa en pánico**, que es justamente cuando no lee rótulos.

### 2.1 Supuestos ocultos

- **H-1. El operador lee el rótulo antes de apretar.** Falsificación: el rótulo cambia sólo con la
  grilla corriendo ("Cerrar todos" ↔ "Cerrar todos · la grilla sigue"). Un rótulo que cambia según el
  contexto es lo primero que no se lee bajo estrés; el operador aprieta **el lugar** donde siempre
  estuvo el botón. Encima, hoy "Cerrar Todos" tiene el mismo rojo que el diseño le da a la parada
  (`shutters.py:381` `#f38ba8`, igual que §5.1), y el diseño pone las dos cosas juntas en el dock.
  Dos botones rojos de "cortar", uno al lado del otro, que hacen cosas opuestas con la grilla.
- **H-2. 3 s alcanzan para leer el banner y decidir.** Falsificación [DERIVADO, sin medir]: leer dos
  líneas, decidir entre "Pausa" y "PARADA" y llevar el ratón al botón es del orden de 1.5 a 3 s. Con la
  mano en el ratón, `F2` no ayuda. El margen es nulo o negativo. Lo único que el operador puede hacer
  en menos de 0.5 s es **repetir el gesto que acaba de hacer**: el cursor ya está sobre "Cerrar todos".
- **H-3. La espera de 3 s es una espera de verdad.** Falsificación: las rutinas viven en el mismo hilo
  (`confocalThread`, `app.py:728-732`) y hoy esperan con `time.sleep` (`measurements.py:2252, 2263,
  2300, 2311, 2318`). Si la cuenta regresiva se implementa con `sleep`, la Pausa que el operador aprieta
  a los 1.5 s queda en la cola del hilo y se procesa **después** de la apertura: el láser abre y se
  cierra un instante después. La cuenta regresiva tiene que ser un `QTimer` no bloqueante, y la
  apertura tiene que comprobar la pausa **en el momento de abrir**, bajo `_nidaq_lock`.
- **H-4. "El nodo en curso" es el único que importa.** Falsificación: si el cierre cae entre nodos
  (en el `sleep(0.5)` de `_grid_trace`, `measurements.py:2318`, o en el autofoco), no hay sesión
  activa y el predicado de aborto no tiene a quién avisar. La apertura que sigue lo deshace en
  ≈ 0.5 s, **sin banner** (el banner de §5.2 se define "al usarlo durante un nodo").
- **H-5. Una sola apertura por nodo.** Falsificación: `_grid_trace` abre (`measurements.py:2319`) y
  la traza vuelve a abrir al arrancar (`trace.py:586`). Una compuerta que sólo mire la primera deja
  pasar la segunda.

### 2.2 Dos pulsaciones, o una durante la espera

El diseño no lo define. Hoy cada pulsación llama a `close_all_shutters()`, que es idempotente. Con la
grilla que sigue, una segunda pulsación es **información nueva**: el operador sigue viendo algo que no
le gusta, o duda de que la primera haya funcionado. Las tres lecturas posibles, y su falsificación:

| Alternativa | Qué hace | Cómo se rompe | Juicio |
|---|---|---|---|
| **A1. Escalar a pausa** | Una segunda pulsación durante la cuenta regresiva, o hasta N s después de la primera (propuesta: 10 s), pausa la grilla | (i) Doble clic por hábito → pausa sin querer: el error es **hacia el lado seguro**, se deshace con Play. (ii) Si el operador aprende "doble clic = pausa" y deja de usar `F2`: no es un problema de seguridad. (iii) Choca con P-H sólo si P-H se lee como "nunca pausa, aunque se apriete dos veces" | **Sobrevive.** Es la única que el operador puede ejecutar dentro de los 3 s con la mano en el ratón. Respeta P-H para una pulsación |
| A2. Reiniciar la cuenta | Cada pulsación vuelve a 3 s | El operador no tiene forma de parar con el mismo botón; un temblor del dedo extiende la espera; no comunica nada | Rechazada |
| A3. Pausar si hay actividad durante la cuenta | Mover el ratón o tocar una tecla pausa | Falsos disparos con el uso normal (mirar la cámara, hacer zoom) | Rechazada |
| A4. El banner toma el foco y `Enter` pausa | Atajo grande en el banner | Robar el foco mientras el operador escribe en un campo: un `Enter` en NaCl pausa la grilla | Rechazada |
| A5. Cambiar el color, no sólo el texto | Con la grilla corriendo, "Cerrar todos" pasa a un color neutro (Peach) y la parada queda como el único rojo | En pánico se aprieta igual el lugar de siempre; mejora el aprendizaje, no el reflejo | Complementaria de A1 |
| A6. Parada física | Hongo cableado a la entrada de interlock del láser, si la tiene | Si el láser no tiene esa entrada, no aplica [BANCO] | Complementaria e independiente del software |

**Desafío de falsificación de P-H con A1+A5** (barato, en `SAFE_MODE`): 5 a 10 usuarios del
laboratorio sin aviso previo; a mitad de una grilla simulada, un estímulo "raro" en la cámara
(un destello o una mancha que aparece). Medir qué aprietan, en cuánto tiempo, y si esperaban que el
láser quedara cerrado. **Si uno solo** aprieta "Cerrar todos", no llega a pausar en 3 s y se sorprende
con la reapertura, el diseño no es seguro para el pánico tal como está, y A1 deja de ser opcional.

### 2.3 Qué tiene que garantizar la implementación (para el contrato de la Ronda 2)

1. **El cierre del operador se modela como un interlock corto** (`"CIERRE-OPERADOR"`), que se activa
   **antes** de cerrar y que libera **sólo** el fin de la cuenta regresiva. Así cualquier camino de
   apertura (impresión, traza, autofoco, confocal) queda bloqueado durante la espera de forma atómica,
   sin depender de que cada rutina mire una bandera.
2. **Consecuencia que hay que resolver antes**: con cualquier interlock activo, las rutinas que hoy
   ignoran el retorno de `open_shutter` corren a oscuras y aplican lo que miden (S3, S7). Antes de
   este interlock, o junto con él, cada paso entre nodos tiene que **invalidarse** si su apertura fue
   rechazada o si hubo un cierre durante el paso, y **restaurar** Z y `startX/startY` a los valores
   previos al paso, no sólo "repetirlo" (P-a). Repetir el autofoco desde un Z movido al `argmax` del
   ruido parte de un lugar equivocado.
3. **La cuenta regresiva empieza antes de la primera apertura de cualquier tipo** (S10), y el banner
   aparece también si el cierre cayó entre nodos (H-4).

---

## 3. ¿La parada de emergencia puede fallar en silencio? (pregunta 2)

| Modo de falla | Mecanismo | Prob. | Impacto | Qué lo detecta |
|---|---|---|---|---|
| F-1. **Diálogo nativo de Windows** | N-1 se probó con `QT_QPA_PLATFORM = offscreen` y un `QDialog` de Qt ([QA] §7). Un `QFileDialog` **nativo** (el que usa Windows por defecto) corre su propio bucle Win32: las teclas van a la ventana nativa y, con alta probabilidad, no pasan por el filtro de `QApplication`. La prueba de N-1 no cubre este caso | Media (66 llamadas modales, varias de guardar archivo) | Alto: la parada queda sin atajo ni botón | [BANCO] con la PC del laboratorio: abrir "Guardar imagen" de la cámara y pulsar `F12`; mirar el log DO. Remedio candidato: `QFileDialog.Option.DontUseNativeDialog` en todo el proceso |
| F-2. **Ventana sin registrar** | El filtro de PySpectrum actúa sólo sobre ventanas **registradas** y sus modales (`window.py:123-142`); una ventana nueva de nivel superior que nadie registró (o un diálogo **no** modal) queda fuera. Cada ventana nueva de PyPrinting sería un agujero silencioso | Media | Alto | Test: recorrer `QApplication.topLevelWidgets()` durante una grilla y enviar `F12` a cada una; exactamente una parada por pulsación. Diseño: en PyPrinting, el filtro actúa sobre **toda** ventana del proceso salvo exclusión explícita |
| F-3. **Hilo GUI ocupado** | El filtro, los botones y "Cerrar todos" corren en el hilo GUI. Si ese hilo está bloqueado (por el propio `_nidaq_lock`, S1, o por una escritura de HDF5 al cerrar el nodo), la parada espera sin decir nada | Baja-media | Alto | Un `QTimer` de latido en el hilo GUI que mida su atraso durante una grilla y lo registre en `trace_backend_health.csv` |
| F-4. **Candado tomado o placa colgada** | N-2 propone un hilo propio con `acquire(timeout = 0.2 s)`. Dos huecos: (a) `set_shutter_interlock` también toma `_nidaq_lock` (`nidaq.py:286`): con el candado tomado, tampoco se puede activar el interlock; (b) si el cuelgue está dentro de una llamada de DAQmx en C, otra escritura desde otro hilo puede quedar trabada en el driver igual | Baja | Muy alto | Test con un `nidaqmx` falso que no vuelve; el interlock tiene que poder activarse sin `_nidaq_lock` (un `threading.Event` propio que `open_shutter` consulte dentro del candado) |
| F-5. **Placa ausente** (`DEC-036`) | Hallazgo 4: el cierre falla, el software no creía nada abierto, y el banner diría "4 de 4 confirmados". Con el 532 activo en BAJO y la línea sin manejar, el estado físico es justamente el de `BANCO-16`, que sigue abierto | Baja | Muy alto | Test: placa ausente → parada → el banner no dice "confirmados" y Rearmar sigue deshabilitado hasta una **escritura exitosa posterior** a la parada |
| F-6. **Satélite con dos E-STOP** | S8: una E-STOP de PySpectrum no activa el interlock. Si "una sola parada" se implementa como "PySpectrum llama a la de PyPrinting", y el satélite no está cargado o falla al importarse, la mitad del proceso queda sin parar | Media en modo satélite | Alto | Test de Q-5: E-STOP desde PySpectrum → `open_shutter` de una rutina de PyPrinting devuelve `False`. Y un solo **Rearmar** para los dos: hoy PySpectrum tiene su `_emergency_active` y su botón de reset aparte |
| F-7. **Dos procesos en el banco** | El banco corre PySpectrum legacy y PyPrinting 3.0 como **dos procesos** sobre la misma placa ([INV4] Q16, [INV5] 3). Ninguna parada conoce las líneas que abrió el otro proceso. Además, cada `open_shutter` de 3.0 escribe **las cuatro líneas** con su propio `_shutter_signal` (`nidaq.py:473-476`): o cierra lo que abrió el otro proceso, o falla por reserva de líneas. No se sabe cuál | **Alta** (es la configuración real) | Alto | [BANCO]: con PySpectrum legacy abriendo un obturador, escribir desde PyPrinting y mirar la línea con un multímetro; registrar el error de DAQmx si lo hay. El rótulo "cierra los cuatro" sólo es verdad si PyPrinting es el único escritor |
| F-8. **Pulsaciones repetidas** | Un operador en pánico martilla `F12`. Si la parada no es idempotente, la segunda puede reiniciar el banner, la hora o, peor, el estado de Rearmar | Media | Medio | Test: tres paradas seguidas → un solo episodio, la hora de la primera, Rearmar deshabilitado hasta las condiciones |

**Lo que no se dice en ningún lado** y conviene escribir en el banner y en el manual: la parada de
emergencia es de **software**. Si la placa o el driver están colgados, la única parada es física (la
llave del láser, o la entrada de interlock si existe, A6). N-2 ya lo propone para un caso; tiene que
valer para F-4, F-5 y F-7.

---

## 4. Rearmar + Play y la doble partícula (pregunta 3)

**Supuesto oculto: "el nodo pendiente" es el que se estaba imprimiendo.** Hoy no lo es en tres
ventanas (S9):

1. **Parada durante la exposición** (antes de la decisión): el nodo 17 quedó expuesto sin decisión.
   Con el reanudar de hoy (`measurements.py:1966-1972`), Play vuelve a `_grid_move()` en el 17 y lo
   **reexpone**. El diseño dice "sigue la regla P4" (§5.1), pero Q-4 dice "se retoma desde el nodo
   pendiente", y la implementación natural reutiliza ese camino. Hay que escribirlo: **el pendiente es
   el primer nodo no expuesto (el 18)**; el 17 va a la cola "en revisión".
2. **Parada entre la decisión `success` y el avance del índice**: `node_results[17] = "success"`
   (`2414`), pero `i_global` sigue en 17 hasta `_grid_detect` (`2840`), que llega después del escaneo
   posterior (`grid_scan`, `2442-2446`), un `sleep(1)` y `down_flipper` (`2520-2521`). Una parada ahí
   y Play **reimprime sobre una NP impresa**. Es la ventana más larga con el escaneo posterior
   activado (≈ segundos), y hoy también la tiene la Pausa.
3. **Parada durante el autofoco o la deriva del nodo siguiente** (P-a): el paso se repite, pero desde
   el Z o el `startX` que dejó el paso invalidado (§2.3, punto 2).

**Contrato propuesto.** El índice de reanudación se **calcula** desde `node_results` y desde el registro
de exposición (`t_open_s`), nunca se toma de `i_global`. Regla: el primer nodo sin resultado y sin
exposición. Todo nodo con exposición y sin decisión va a revisión.

**Segundo supuesto oculto: la muestra no se movió durante la parada.** Una parada de emergencia dura lo
que tarda el operador en revisar el banco: minutos. Con la deriva de Martínez, ≈ 30 nm/min
(`lab-invariants`, [INV2] R2-13), y la tolerancia por defecto de 25 nm (`measurements.py:1582`),
cualquier parada de más de ≈ 50 s ya excede la tolerancia [DERIVADO]. Retomar sin corregir la deriva
imprime el resto de la red **corrido** respecto de la parte ya impresa: una costura en la red, que en
una red de a = 400 nm es un defecto estructural, no ruido. La corrección por tiempo existe sólo con el
autofoco adaptativo (`measurements.py:2235`) y no corrige XY si `driftbool` está apagado.
**Propuesta:** después de rearmar, el primer nodo hace siempre autofoco y, si la deriva XY está
activada, la corrección sobre P0, cuando la parada duró más que `tau_safe` (pregunta Q-B).

**¿Rearmar + Play son "dos acciones deliberadas"?** Rearmar sí (botón nuevo, condiciones). Play no:
es el mismo botón que se aprieta después de cada pausa, un gesto habitual. La protección contra la
doble partícula no puede depender de que Play sea deliberado; depende del índice calculado.

---

## 5. Confirmación a baja potencia (pregunta 4)

### 5.1 Qué tan fácil es un falso "no se ve la NP"

Mecanismos, con su orden de magnitud [DERIVADO, a medir en el banco]:

- **Deriva lateral entre la exposición y la lectura.** Spot de detección con NA 1.0 a 532 nm:
  FWHM ≈ 0.51·λ/NA ≈ 270 nm. Con 30 nm/min, a los 5 min la NP está a ≈ 150 nm del centro. Con un perfil
  gaussiano, la intensidad relativa ahí es exp(−4·ln2·(150/270)²) ≈ 0.43. Si el exceso de señal de la
  NP escala con la intensidad, un escalón de ×1.4 se lee como 1 + 0.4·0.43 ≈ **×1.17, debajo del
  umbral propuesto de ×1.20** ([v1 §2.4]); si escala con el campo (√0.43 ≈ 0.65), ≈ ×1.26, apenas
  arriba. A los 2 min (60 nm) da ×1.35: sin problema. **El riesgo crece con el tiempo entre el corte y
  la lectura**, que es justamente lo que el Healing Pass alarga (la lectura llega al final de la
  grilla) y lo que una parada de emergencia alarga (minutos).
- **Desenfoque.** El autofoco corre cada N nodos; Z deriva entre medio. Mismo efecto, sin cifra hasta
  medir la profundidad de foco efectiva.
- **NP chica o escalón chico.** El investigador mide ×1.4 a ×2 ([INV3]); los ×1.4 son los que primero
  caen debajo de 1.20 con cualquier pérdida.
- **El filtro no está puesto.** Los pulsos del flipper de potencia ignoran su retorno en toda la grilla
  (`measurements.py:2252, 2263, 2300, 2311, 2318`). Si el `up_flipper` falló, la "lectura a baja
  potencia" es a **alta** potencia: ya no es una lectura, es una exposición que puede imprimir.
- **Cierre del operador o parada durante la lectura.** La lectura ve oscuridad, que es indistinguible
  de "no hay NP" mirando sólo el fotodiodo de detección.

Los cinco tienen un testigo físico que ya existe: **el fotodiodo del BS** está después del obturador y
del filtro ([INV4] Q14, [INV9] P-c). Con él se puede exigir, durante la lectura, que la potencia sea la
de baja (ni oscuridad, ni alta). Sin eso, la lectura no es válida.

### 5.2 ¿Qué es peor, el falso positivo o el falso negativo?

| | Falso "se ve" (no hay NP) | Falso "no se ve" (hay NP) |
|---|---|---|
| Qué pasa | el nodo queda "impreso" vacío | el Healing Pass reexpone hasta `T_max + 10 s` = 50 s a alta potencia (`measurements.py:2860`) |
| Resultado físico | una vacancia | una segunda NP al lado (dímero o agregado), o calentamiento sostenido de la NP impresa (reformado, daño del PDDA/PSS). El criterio no ve escalón porque la NP ya está en la base, así que el nodo corre los 50 s enteros |
| ¿Se ve después? | sí: la vacancia se cuenta con la cámara o el confocal y entra en p ([INV2] R2-17) | a veces; un dímero de dos NP de 60 nm no se resuelve con la cámara |
| Daño a la ciencia | baja la eficiencia, pero el defecto es **honesto**: una ausencia | fabrica un objeto que el laboratorio estudia (dímeros, puntos calientes de SERS): un **artefacto que se confunde con señal**. En una red, un sitio doble rompe la periodicidad igual que una vacancia, pero no se detecta igual |
| Reversible | no | no |

**El falso negativo es peor.** Consecuencia de diseño: la regla tiene que estar **sesgada hacia no
reexponer**. Tres resultados, no dos:
- **"se ve"** → impresa (verificada);
- **"no se ve, con certeza"** → reintento, sólo si: el BS estuvo en el nivel de baja potencia, la base
  es reciente, y el ruido de la lectura habría detectado el escalón mínimo (que la lectura tenga la
  potencia estadística para ver ×1.4, no sólo que no lo vio);
- **"indeterminado"** → en revisión, nunca reintento automático.

Alternativa que conviene falsificar en la Ronda 2: en vez de una lectura en un punto, un **escaneo
chico** a baja potencia alrededor del sitio (como el `center_scan` de dímeros, `measurements.py:2450`),
que no depende de que la NP siga en el centro. Cómo se rompe: con a = 400 nm, una ventana de más de
≈ ±200 nm incluye a los vecinos ya impresos (falso positivo). Hay que medir cuál de los dos errores
domina con la red real.

### 5.3 Un hueco entre P4 y P13

P4 y P-H dependen de la lectura para **todo** nodo expuesto sin decisión. P13 dice que la confirmación
viene activada **sólo en los presets de ventana corta**, y P0 (el preset por defecto) no la trae. Si la
"lectura de P4" es la misma función que la "confirmación de P13", en P0 todos los nodos interrumpidos
quedan en revisión para siempre, y R4-3 no resuelve P4 en el caso más común. Puede ser lo que se
quiere, pero tiene que decidirse (pregunta Q-C).

---

## 6. `legacy_timer` con la bandera de cierre (pregunta 5)

**Supuesto oculto: "lo que imprime bien" es el código que se va a tocar.** No lo es. El banco corre
`7f5d10a` ([INV2] R2-2); `main` nunca se desplegó. Entre `7f5d10a` y `HEAD`, el camino de impresión
cambió en 1537 líneas agregadas y 344 quitadas (`git diff --stat` sobre `measurements.py`, `trace.py`,
`focus.py`, `nidaq.py`, `shutters.py`, `app.py`). Ejemplos que tocan la decisión del nodo: el
`heartbeat_shutter()` por muestra en `grid_trace_detect` es nuevo (ANOM-MEASURE-02), y toda la
semántica de `DEC-036` también. `DEC-037` revirtió **la lectura** de la traza a la de `7f5d10a`, no
todo el camino. Así que no se puede "romper lo que anda" en el sentido literal; lo que se puede romper
es **la línea de base de BANCO-32**, que usa `legacy_timer` como referencia.

**Cómo puede romper la bandera:**

| Riesgo | Mecanismo | Remedio que se prueba |
|---|---|---|
| Bandera rancia | un "Cerrar todos" sin grilla, o en un nodo anterior, deja la bandera puesta; el nodo siguiente termina en el primer tick como "expuesto sin decisión", y así en cascada: cada nodo abre ≈ 47 ms a alta potencia y se marca en revisión | contador de generación capturado al abrir el nodo, no una bandera booleana |
| Orden con el cierre | si la bandera se pone **después** de cerrar, un tick intermedio ve oscuridad y la rama de caída lo rotula "timeout" (`2408`) | bandera (o interlock corto, §2.3) **antes** del cierre; la bandera se evalúa antes que la rama de caída |
| Segunda apertura | la traza reabre al arrancar (`trace.py:586`); una bandera que sólo mire `grid_trace_detect` no impide esa apertura | el interlock corto de §2.3, que vale para toda apertura |
| Bandera consumida al arrancar el nodo | si el nodo "limpia" la bandera al empezar, borra el cierre que cayó en el `sleep(0.5)` previo (H-4) | la limpia el fin de la cuenta regresiva, no el nodo |
| No es un no-op | cualquier cambio de orden de las escrituras DO en la ausencia de cierres cambia la línea de base | test dorado (abajo) |

**Test dorado que lo decide** (ninguna de las tres pruebas de la concesión está hoy; esta es la que
falta): reproducir trazas registradas (`NP_xxx.txt` de BANCO-24, o el guion de 11 nodos de §10) a
través de `grid_trace_detect` con la bandera **nunca activada**, antes y después del cambio, y exigir
decisiones idénticas nodo a nodo y el mismo log de escrituras DO (orden y nivel). Y una referencia de
`grid_trace_detect` de `7f5d10a`, copiada sólo en los tests, para medir cuánto difiere ya `main` del
programa que imprime en el banco.

---

## 7. Escenarios de falla: probabilidad, impacto y detección

| # | Escenario | Prob. | Impacto | Detección (test en `SAFE_MODE` con `nidaqmx` falso y log DO, o banco) |
|---|---|---|---|---|
| E-1 | Parada → una rutina abre entre el cierre y el interlock (S2) | Baja por evento, segura con el tiempo | Muy alto | Test de estrés: un hilo abre en bucle, la GUI dispara la parada 1000 veces; ninguna apertura exitosa posterior. **Mutación**: invertir el orden tiene que hacer fallar el test |
| E-2 | Pausa o cierre durante el autofoco → apertura de impresión antes de que la cola procese la pausa (S3, H-3) | Media | Alto | Test: pausa a mitad de `focus_autocorr_lin_x2`; ninguna escritura DO "abrir" posterior a la pausa |
| E-3 | Parada en el escaneo posterior de un nodo `success` → Play reimprime (hallazgo 3) | Media con el escaneo posterior activado | Muy alto (doble partícula) | Test: parada entre `2414` y `2840`; la primera apertura después de Play es en la posición del nodo siguiente |
| E-4 | Placa ausente → "4 de 4 confirmados" → Rearmar habilitado (hallazgo 4) | Baja | Muy alto | Test con `_get_shutter_task` → `None` |
| E-5 | Cerrar todos en el `sleep(0.5)` previo a abrir → reapertura en 0.5 s sin banner (H-4) | Media | Alto | Test: cierre programado en ese `sleep`; nada abre durante la cuenta regresiva por ninguno de los tres caminos (`measurements.py:2319`, `trace.py:586`, `focus.py:376`) |
| E-6 | Cierre durante la segunda iteración del autofoco → Z al `argmax` del ruido → nodos desenfocados registrados como válidos (S7) | Media | Alto (datos) | Test: el paso invalidado restaura Z previo; el log de `pi.MOV` no muestra el Z del ruido |
| E-7 | Lectura a baja potencia con el filtro sin poner → exposición a alta potencia (§5.1) | Baja | Muy alto | Test: `up_flipper` → `False`; la lectura se rechaza por el nivel del BS |
| E-8 | Falso "no se ve" por deriva → reexposición de 50 s → dímero (§5) | Media en el Healing Pass | Muy alto (científico) | [BANCO]: sitios impresos y vacíos, leídos con desplazamientos controlados de ±100 y ±200 nm y desenfoque; curva de falsos negativos contra el umbral |
| E-9 | `F12` con un diálogo nativo abierto no dispara (F-1) | Media | Alto | [BANCO] en Windows, con el `QFileDialog` de la cámara |
| E-10 | Dos procesos: la parada de PyPrinting no cubre lo que abrió PySpectrum legacy, o lo cierra sin que este se entere (F-7) | Alta | Alto | [BANCO] con multímetro en la línea |
| E-11 | Retomar tras minutos sin corregir deriva → costura en la red (§4) | Alta tras una parada larga | Medio-alto (datos) | Test: Play tras una parada de más de `tau_safe` dispara autofoco y deriva antes del primer nodo |
| E-12 | Bandera rancia en `legacy_timer` → cascada de nodos "en revisión" (§6) | Media | Medio | Test: "Cerrar todos" sin grilla, después Play: el nodo 0 imprime normalmente |

---

## 8. Síntesis del abogado del diablo

### 8.1 Los tres supuestos ocultos más peligrosos

1. **"Detener la grilla" es enviarle una señal.** Las rutinas comparten un hilo con `sleep` y una
   cadena síncrona que no mira ningún estado (S3). Lo único que de verdad detiene una apertura hoy es
   un interlock consultado **dentro** de `open_shutter`. Todo corte (parada, pausa, cierre del
   operador, espera de 3 s) tiene que terminar ahí, con el orden interlock-antes-de-cerrar.
2. **"El nodo pendiente" es `i_global`.** No lo es entre la decisión y el avance (S9). La doble
   partícula no la previene la deliberación del operador, sino un índice calculado desde los
   resultados y la exposición.
3. **"Confirmado cerrado" es un hecho físico.** Es "la placa aceptó la escritura" (`DEC-036`), y en un
   caso ni siquiera eso (hallazgo 4). En un banco con dos procesos sobre la misma placa (F-7), ni
   siquiera es "todas las líneas que importan". El BS es el único testigo físico disponible para el
   láser de impresión.

### 8.2 Explicaciones más simples (navaja de Ockham)

- Si en el banco "Cerrar todos" parece "no funcionar" (el láser vuelve), la primera sospecha no es un
  defecto del cierre: es la apertura legítima de la etapa siguiente de la cadena (E-5, S10).
- Si después de rearmar aparecen dímeros en sitios aislados, la primera sospecha no es la química del
  coloide: es una reexposición por índice (E-3) o por falso negativo (E-8). Se distingue mirando en
  el registro por intento si el sitio tuvo dos exposiciones.
- Si un nodo tras un cierre del operador queda "timeout" en `legacy_timer`, no es una captura fallida:
  es la rama de caída leyendo oscuridad (S6).

### 8.3 El desafío de falsificación de mayor palanca

**Un solo test de integración en `SAFE_MODE` que registre cada escritura DO con su hilo y su causa**,
y que para cada forma de corte (parada, pausa, cierre del operador simple y doble, watchdog,
interlock) en cada etapa de la cadena (exposición, escaneo posterior, movimiento, autofoco, deriva,
cuenta regresiva, lectura de confirmación) verifique dos invariantes:
1. ninguna apertura exitosa después del corte sin una acción posterior del operador, salvo la que
   permite P-H **después** de la cuenta regresiva;
2. el primer nodo expuesto después de reanudar es uno que nunca había estado expuesto.

Es el invariante de §5.3 del diseño, pero recorriendo **las etapas**, no sólo las causas. Si cualquiera
de las 6 × 7 combinaciones lo rompe, el diseño todavía no se implementa.

---

## 9. Preguntas para el investigador (se contestan en una línea)

1. **Q-A. Segundo "Cerrar todos".** Si se aprieta otra vez durante la espera de 3 s, o hasta 10 s
   después del primero: (a) **pausa la grilla**; (b) reinicia la espera; (c) no hace nada distinto.
   **Recomiendo (a)**: es lo único que el operador alcanza a hacer en 3 s con la mano en el ratón, y
   el error que puede causar (una pausa sin querer) es hacia el lado seguro. Con una sola pulsación,
   P-H no cambia.
2. **Q-B. Qué nodo se retoma y con qué preparación.** Después de una parada o una pausa a mitad de un
   nodo: (a) **se sigue desde el primer nodo nunca expuesto; el interrumpido va a revisión, y si la
   parada duró más que `tau_safe` se hace autofoco (y corrección de deriva, si está activada) antes de
   imprimir**; (b) se vuelve al nodo interrumpido con la pregunta "¿Reimprimirlo?"; (c) se vuelve al
   nodo interrumpido sin preguntar. **Recomiendo (a)**: (c) puede fabricar dímeros y (b) depende de que
   el operador decida bien mirando una cámara que no resuelve un dímero.
3. **Q-C. La lectura de P4 en P0.** (a) **La lectura a baja potencia de la regla P4 existe en todos los
   presets**, aparte de la confirmación después de cada parada de P13, que sigue activada sólo en los de
   ventana corta; (b) en P0 no hay lectura y todo nodo interrumpido queda en revisión manual.
   **Recomiendo (a)**, con resultado "indeterminado" → revisión, nunca reintento automático: un falso
   "no se ve" fabrica dímeros y una vacancia sólo baja la eficiencia.
4. **Q-D. Parada física.** El Excelsior o su fuente, ¿tienen una entrada de interlock remoto?
   (a) **sí: se cablea un pulsador de emergencia y el banner de la parada de software lo nombra**;
   (b) no: el banner nombra la llave del láser como única parada que no depende del software. Va a la
   batería de banco. **Recomiendo verificarlo**, sea cual sea la respuesta: hoy ningún documento dice
   que la parada de PyPrinting es sólo de software.
5. **Q-E. Dos procesos sobre la misma placa.** Mientras el banco corra PySpectrum legacy y PyPrinting
   3.0 a la vez: (a) **prueba de banco de qué pasa con una línea abierta por un proceso cuando el otro
   escribe las cuatro, y rótulos según el resultado**; (b) prohibir los dos procesos durante una grilla;
   (c) aceptar el riesgo y documentarlo. **Recomiendo (a)**, y (b) hasta tener el resultado.

---

## 10. Veredicto

**`HIGH_RISK_ASSUMPTIONS`.**

- **Lo que pasa:** el diseño de la GUI de §5 promete al operador lo correcto (una parada que no se
  libera sola, un "Cerrar todos" que no miente sobre la grilla, una regla única para lo expuesto sin
  decisión), y las decisiones del investigador (P-E, P-H, Q-4, Q-5) no se discuten acá.
- **Lo que no pasa todavía:** tres promesas de hardware chocan con el código: el orden
  cierre-después-interlock (S2), la cadena que sigue después de una parada o una pausa (S3) y el
  índice de reanudación (S9). Una más falla en silencio con la placa en falla (S4, S5).
- **Condiciones para la Ronda 2 de R4-17** (además de N-1 a N-4):
  1. todo corte termina en un interlock activado **antes** de cerrar, que se puede activar sin
     `_nidaq_lock`;
  2. cada etapa de la cadena de la grilla consulta el estado de forma síncrona antes de mover o de
     abrir, y los pasos entre nodos se invalidan y se restauran si su apertura fue rechazada o hubo un
     corte;
  3. el índice de reanudación se calcula desde los resultados y la exposición;
  4. Rearmar exige una escritura exitosa posterior a la parada, y el banner no dice "confirmados" si
     no la hubo;
  5. la lectura a baja potencia es válida sólo con el BS en el nivel de baja potencia, y tiene un
     resultado "indeterminado" que nunca reexpone;
  6. el test de §8.3, con su mutación, y el test dorado de §6.
- **Lo que me haría conceder** (regla de concesión): el test de §8.3 corriendo y pasando, con las
  mutaciones que lo hacen fallar; las pruebas de banco F-1, F-7 y E-8 con su resultado registrado. Ni
  el diseño ni este informe sustituyen a ninguna de las tres.
- **Pendientes de banco** que tienen que ir a `docs/evidence/PRUEBAS_BANCO_PENDIENTES.md` (regla del
  investigador; no lo edité): `F12` con un diálogo nativo (F-1); dos procesos sobre la misma placa
  (F-7); falsos negativos de la lectura a baja potencia con desplazamientos y desenfoque controlados
  (E-8); entrada de interlock del láser (Q-D); latencia física de la parada medida con el BS.
