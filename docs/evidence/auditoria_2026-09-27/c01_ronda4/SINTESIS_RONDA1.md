# C-01, Ronda 4 — Síntesis de la mini Ronda 1 de instrumentación (2026-10-01)

**Alcance:**
- R4-17: la parada de emergencia propia de PyPrinting;
- P-H: "Cerrar todos · la grilla sigue";
- R4-3: la confirmación a baja potencia;
- N-1 a N-4 (R4-25 a R4-28).

Todo toca obturadores, así que nada de esto es exento.

**Panel:** `instrumentation.md`, `experimentalist.md` y `devil_advocate.md`, en esta carpeta. Ninguno tocó código ni hardware.

**Veredictos:**
- instrumentación: `SAFETY_VIOLATION` en el código actual y `HARDWARE_SAFE` en el diseño, condicionado al banco;
- experimental: `MODIFICATION_REQUIRED`;
- abogado del diablo: `HIGH_RISK_ASSUMPTIONS`.

---

## 1. Hallazgo de seguridad en el código que ya está instalado

**Una Pausa durante el autofoco de una grilla deja el 532 abierto a alta potencia, sin detección, y el watchdog no vence nunca.** Instrumentación lo reprodujo en `SAFE_MODE` con los backends reales. La revisión del código lo confirma.

- **El despacho del fin del autofoco corre en el hilo GUI:** `app.py:487-490`, un cierre conectado a `autofinishSignal`.
- **La Pausa no detiene esa cadena.** Llega encolada al `confocalThread`, cierra el obturador y pone `mode_printing = "none"`.
- **El hilo GUI sigue con `grid_finish_autofoco` → `_grid_trace`:** baja el filtro y abre el 532 (`measurements.py:2311, 2318-2319`).
- **Nada cierra el obturador.** Con `"none"`, la traza no le manda datos al criterio (`trace.py:738-740`).
- **El watchdog no vence.** `heartbeat_shutter(30.0)`, cada 30 ticks (`trace.py:643-644`), le renueva el plazo para siempre.
- **Está también en `7f5d10a`, el commit de la PC del banco** (el mismo despacho en `app.py:296-300`, y la misma Pausa).
  - El legado conectaba la señal al slot del worker (`printing2/PyPrinting_UNSAM.py:418`), así que esto es una regresión de 3.0.
  - Hoy el banco imprime con el PyPrinting legado: según la quinta ronda, PyPrinting 3.0 sólo se probó por separado.

**Recomendación operativa inmediata:** no correr grillas de impresión con PyPrinting 3.0 (ni `7f5d10a` ni `main`) hasta que esto se corrija. Si alguna se corre igual, no usar Pausa: cortar con la llave del láser.

## 2. Lo que el código actual contradice del diseño (§5 de `gui_design_v2.md`)

1. **El orden "cerrar y después interlock" tiene una carrera.**
   - En esa ventana, una rutina en `confocalThread` puede volver a abrir (`measurements.py:2319`, `trace.py:586`, `focus.py:376`).
   - El orden seguro ya existe en `trip_shutter_interlock` (`nidaq.py:305-308`): interlock primero, cierre después.
2. **"La grilla detenida no emite más movimientos" es falso hoy.**
   - Las entradas de la grilla no miran ningún estado.
   - El autofoco avisa que terminó también cuando se abortó (`focus.py:395`).
   - Los retornos de `open_shutter` se ignoran.
   - Hace falta una guarda al principio de cada entrada (`measurements.py:2134, 2223, 2271, 2317, 2325, 2442, 2456, 2817, 2845`), puesta con una bandera directa, nunca con una señal encolada.
3. **Cualquier cierre puede bloquear.**
   - `close_all_shutters` toma `_nidaq_lock` sin plazo (`nidaq.py:537`).
   - Con un hilo colgado adentro del candado, no cierra nadie.
   - Dentro del candado hay escritura a disco: el estado del espejo, de R4-N 3.
   - `Task.write` tiene un plazo de 10 s por defecto.
4. **"4 de 4 confirmados" puede mentir.**
   - Si la escritura falla y el software no creía nada abierto, `_all_closed_confirmed()` da verdadero (`nidaq.py:409-411, 553-560`), aunque `close_all_shutters` devuelve `False`.
   - Además, "Cerrar Todos" desmarca los botones antes de escribir e ignora el retorno (`shutters.py:308-315`).
5. **"Cerrar todos" se deshace solo en dos casos:**
   - la traza vuelve a abrir al arrancar (`trace.py:586`);
   - un cierre que cae en el `sleep(0.5)` previo a la apertura se deshace medio segundo después (`measurements.py:2318`).
6. **"Retomar desde el nodo pendiente" (Q-4) puede reimprimir una NP ya impresa.** `i_global` avanza recién en `_grid_detect`, después de la decisión, del escaneo posterior y de un `sleep(1)` (`measurements.py:2414, 2442-2446, 2517-2521, 2840`).
7. **Modo satélite:**
   - la E-STOP de PySpectrum no activa ningún interlock de `core/nidaq.py`;
   - ningún módulo de PyPrinting consulta `hardware_session`;
   - por eso, una E-STOP de PySpectrum no impide que la grilla del satélite reabra.
8. **N-1, confirmado con una sonda:**
   - con un modal abierto, el atajo de aplicación no dispara;
   - un filtro de eventos en `QApplication` sí dispara;
   - dos registros de `Ctrl+E` son ambiguos y no dispara ninguno;
   - falta probarlo con un `QFileDialog` nativo de Windows.
9. **N-3, confirmado y ampliado:**
   - el autofoco mueve Z al `argmax` sin validar la señal (`focus.py:418-424`);
   - el escaneo de deriva reemplaza `startX/startY` sin tope;
   - un tope de distancia solo no detecta un escaneo oscuro, porque la imagen se normaliza entre su mínimo y su máximo: también hace falta un tope de amplitud;
   - hay que restituir Z, `startX/startY` y `last_af_*`, no sólo repetir el paso.
10. **N-4, confirmado:** con `legacy_timer`, un "Cerrar todos" deja el nodo rotulado "timeout", y el Healing Pass lo reexpone 50 s (`measurements.py:2408, 2416-2418, 2828, 2860`).

## 3. Propuesta técnica del panel (para la Ronda 2)

- **Parada de emergencia:**
  1. **en el hilo GUI, sin candado:** un evento de parada y una época de cierre, que `open_shutter` revisa antes del candado y otra vez adentro; banderas de alto en grilla, traza, foco y confocal;
  2. **en un hilo cerrador propio,** con candado de plazo 0.25 s (provisorio, BANCO-68): interlock "E-STOP" y después el cierre de las cuatro líneas con su polaridad, con reintentos;
  3. **"confirmado"** es una escritura exitosa posterior a la parada.
- **Platina:** no se envía `STP`/`HLT`. Esperaría el candado del controlador, y un `−1004` dispararía la reconexión y el home que `DEC-036` prohíbe. Alcanza con no emitir más `MOV`.
- **Rearmar exige:**
  - un cierre confirmado de la parada vigente;
  - las rutinas quietas, con un plazo de 12 s;
  - que no haya habido otra parada en el medio.
- **Latidos:** `heartbeat_shutter` no hace nada mientras la parada esté activa.
- **Un solo filtro de teclas en `core/`** y un único coordinador de paradas por proceso, con un Rearmar común (Q-5).
- **"Cerrar todos":**
  - la misma época de cierre: `_grid_trace` la anota antes de abrir y `grid_trace_detect` la compara en su primera línea;
  - el nodo queda "interrumpido", y como el Healing Pass sólo toma los "timeout", va a revisión;
  - la traza deja de reabrir cuando la apertura es de la grilla;
  - la espera visible de 3 s (P-b) va antes de cualquier apertura, y no se hace con `sleep`.
- **Pasos entre nodos:**
  - control de época y del `bool` de la apertura;
  - si hubo cierre, la corrección no se aplica, se restituye el estado y el paso se repite;
  - topes de plausibilidad de `experimentalist.md` §5: amplitud, ancho y paso de la deriva; correlación y |Δz| del autofoco.
- **Confirmación a baja potencia:**
  - **Magnitud:** R = (V − D)/(V_base − D), normalizada por el BS, con el oscuro D obligatorio.
  - **Lectura:** 100 ms, en bloques de 20 ms.
  - **Tres salidas:** "ve la NP", "no la ve" y "no sé". Un "no sé" nunca reexpone.
  - **Secuencia:** filtro arriba con el obturador cerrado; verificación del filtro con el BS; lectura; cierre.
  - **Calibración:** con "Medir escalón".
  - **Después de una pausa larga (> 60 s):** primero deriva y autofoco, después la lectura.
  - **Costo:** ≈ 0.7-1.2 s por nodo.
- **Test de integración:** cada forma de corte (6) por cada etapa de la cadena (7), con mutaciones. Además, un test dorado de `legacy_timer`: con la bandera nunca activada, las decisiones y el log de escrituras DO tienen que quedar idénticos.

## 4. Preguntas para el investigador (cada una con la recomendación del panel)

**Seguridad inmediata**
1. **La Pausa durante el autofoco (§1):** (a) corregirla ya, aparte de R4-17, con un test que hoy falla y una Ronda 2 corta (toca una apertura: no es exenta), o (b) junto con R4-17. **Recomendado: (a).**
2. **Mientras tanto, ¿PyPrinting 3.0 queda sin uso para grillas?** **Recomendado: sí.** Que el banco siga con el PyPrinting legado.

**Parada de emergencia**

3. **Si el cerrador no consigue la placa en 0.25 s:** (a) banner persistente "cortá con la llave del láser" más reintentos, o (b) además, una escritura de cierre sin candado. **Recomendado: (a).**
4. **¿La parada sube el filtro de densidad (baja potencia) después del cierre confirmado?** **Recomendado: sí**, como ya hacen la Pausa y el cierre al salir.
5. **¿Desde dónde se retoma después de rearmar?** Afina Q-4. La propuesta: desde el primer nodo **nunca expuesto**; el interrumpido va a revisión; y si la parada duró más de un minuto, autofoco y deriva antes. **Recomendado: sí.**

**"Cerrar todos"**

6. **¿Un segundo "Cerrar todos" pausa la grilla?** El caso: durante la espera de 3 s o en los 10 s siguientes. Es lo que alcanza a hacer en pánico un operador que ya tiene el cursor sobre el botón, y si se dispara sin querer el resultado es una pausa, el lado seguro. **Recomendado: sí.**

**Pasos entre nodos y confirmación**

7. **Una deriva o un autofoco no plausibles,** aun después de repetir el paso: (a) pausar o (b) avisar y seguir. Un corrimiento afecta todos los nodos siguientes, y el Healing Pass no lo arregla. **Recomendado: (a)**, con los topes provisorios hasta medirlos.
8. **¿Cuándo se confirma un nodo cortado por "Cerrar todos", la pausa o la parada?** (a) En el acto, o (b) en diferido, en el Healing Pass o al reanudar, después de la deriva y el autofoco. **Recomendado: (b).** El corte por el criterio y la falla con exposición se confirman en el acto.
9. **"No sé" después de dos lecturas:** (a) en revisión, (b) reintentar, o (c) marcar como impresa. Un falso "no la ve" puede fabricar un dímero, y en este laboratorio eso se confunde con señal. **Recomendado: (a).** Además, la lectura vale para todos los presets, incluido P0.
10. **El BS indica que el filtro no subió:** (a) cortar y pausar, o (b) cortar y avisar. Si no se pausa, el autofoco y los escaneos siguientes quedarían a alta potencia. **Recomendado: (a).**
11. **Confirmar P-c, que quedó para esta ronda.** El caso: el BS ve luz y el fotodiodo de detección no, o sea espejo arriba o detección desalineada. La recomendación es cortar el nodo y pausar la grilla. **Recomendado: confirmar.**

**Datos que sólo vos tenés**

12. **¿Qué OD tiene el filtro de densidad casero?** 1, 2, 3 o no se sabe. Si es menor que 1, la lectura a baja potencia necesita otra deliberación. Se mide igual en el banco.
13. **¿Usan el "Scan" después de imprimir?** Si lo usan, su imagen puede reemplazar la lectura puntual como confirmación.
14. **¿El láser de 532 tiene una entrada de interlock remoto,** para una parada física independiente del software? Se verifica en el banco.
15. **¿Corren PySpectrum legacy y PyPrinting 3.0 a la vez durante una grilla?** Cada programa escribe las cuatro líneas con su propio estado, y ninguna parada conoce lo que abrió el otro. **Recomendado:** no correrlos juntos durante una grilla hasta probarlo en el banco.

## 5. Pruebas de banco propuestas

Numeración provisoria: se asientan en `PRUEBAS_BANCO_PENDIENTES.md` con las respuestas.

- **BANCO-65 ⚠️ (láser a baja potencia, con aprobación):** confirmación a baja potencia.
  - A: atenuación del filtro, linealidad PD/BS, oscuro y σ_R;
  - B: r a baja potencia contra r a alta potencia, en el tiempo, y matriz de confusión de 20 nodos;
  - C: ruido de la deriva y del autofoco en oscuridad.
- **BANCO-66:** parada de punta a punta, con osciloscopio en las líneas de los obturadores, desde cada ventana, con modales (incluido un `QFileDialog` nativo) y en modo satélite.
- **BANCO-67:** "Cerrar todos" con `legacy_timer`.
- **BANCO-68:** cuánto tiempo se retiene `_nidaq_lock`, para fijar el plazo del cerrador.
- **BANCO-69 ⚠️ (baja potencia, con aprobación):** si el BS distingue luz de oscuridad a baja potencia.
- **Del abogado del diablo:** interlock remoto del láser, y dos procesos sobre la misma placa.
