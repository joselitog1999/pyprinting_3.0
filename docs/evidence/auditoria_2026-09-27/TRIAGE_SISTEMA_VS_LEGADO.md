# Triage de defectos de sistema / hardware: PyPrinting 3.0 y PySpectrum 3.0 frente al legado

**Fecha:** 2026-09-27. **Autor:** subagente `instrumentation` (sólo lectura; único archivo escrito: este informe).
**Insumos:** `CONSOLIDADO.md`, `RESPUESTAS_INVESTIGADOR.md` (prevalece), el árbol de trabajo actual (rama `main`, con cambios sin commitear), el historial de git y los dos legados:

- **Legado de PySpectrum:** `scratch/pyspectrum-legacy/` (idéntico, por `diff -rq`, a `Obsidian_Vault/pyspectrum-legacy/`). Archivos `*_ps.py`.
- **Legado de PyPrinting (2.x):** **encontrado fuera del repositorio**, en `C:\Users\josel\Documents\Obsidian_Vault\printing2\` (archivos `*_pp.py`: `Trace_pp.py`, `Printing_pp.py`, `Instrument_nidaqmx_pp.py`, `Shutters_pp.py`, `Confocal_pp.py`, `Focus_pp.py`, `Nanopositioning_pp.py`, `Dimers_pp.py`, `PyPrinting_UNSAM.py`). No está en el historial de git de `printing3`. Además se usa como referencia la **primera versión de 3.0 en git** (commit `0a189c8`, 2026-07-28).

**Premisa del investigador:** los dos legados funcionaban en el banco (con bugs no bloqueantes); **PyPrinting 3.0 y la cámara se probaron en el banco y funcionan en general; PySpectrum 3.0 no se probó**. Un hallazgo que implique que el legado no podía funcionar, o que 3.0 no podría imprimir, se re-examina antes de aceptarse.

**Clasificaciones:** REGRESIÓN de 3.0 (el legado lo hacía bien y 3.0 lo rompió) · HEREDADO del legado (el legado ya lo hacía así) · NUEVO en 3.0 (función o camino que el legado no tenía, y que nace con el defecto) · NO ES DEFECTO (el hallazgo no se sostiene).

**Rutas:** `3.0` = `C:\Users\josel\Documents\Obsidian_Vault\printing3\`; `PSL` = `scratch/pyspectrum-legacy/`; `PPL` = `C:\Users\josel\Documents\Obsidian_Vault\printing2\`.

**Estado:** COMPLETO (2026-09-27). Escrito de forma incremental; la tabla resumen se completó al final. No se ejecutó nada contra hardware ni `pytest`: sólo lectura de código, `git` y consulta de documentación de NI.

## Tabla resumen

**Conteo de los 23 ítems pedidos:** REGRESIÓN 5 · HEREDADO 5 · NUEVO 13 · NO ES DEFECTO 0 (dos refutaciones parciales: un camino de C-03 y la premisa física de C-08). **Hallazgos adicionales:** C-01b (REGRESIÓN), ACT-N1 (REGRESIÓN + NUEVO), AND (REGRESIÓN), X-01 (inconsistencia de cableado entre versiones), CP-1…CP-13 (divergencias del contrapropagante, NUEVAS).

| ID | Clasificación | ¿Se sostiene con la premisa? | Pregunta (Q-n, ver al final) |
|---|---|---|---|
| **C-01** traza continua | **REGRESIÓN** (`6abbbfc`, 2026-09-19) | Mecanismo: sí. **Incompatible con "imprime bien"** si se imprimió con un commit ≥ `6abbbfc`; compatible si la prueba fue anterior | Q1 |
| C-01b cadencia de 35 ms | REGRESIÓN (`6444b0d`, 2026-08-27) | Sí (≈ 3.5× más latencia que el legado) | — |
| C-03 orden cero | HEREDADO | Parcial: `spectrum_control` sí protege; `calibration_dock` y λ = 0 en el panel izquierdo no | Q10 |
| C-04 offsets al arrancar | NUEVO | Sí (el legado escribía sólo a mano) | Q8 |
| C-05 modos de lectura | NUEVO | Sí (el legado sólo usaba Image) | — |
| C-06 rendija | REGRESIÓN | Sí (el legado usaba `SetAutoSlitWidth`) | — |
| C-07 puertos del Shamrock | REGRESIÓN | Sí; efecto práctico menor (el espejo mecánico conserva Side/Direct) | Q11 |
| **C-08** estado de `line7` | **REGRESIÓN** (3.0 perdió la persistencia en archivo) | Sí en lo mecánico; **refutada la premisa física** (no es un notch) | Q5, Q6 |
| ACT mapeo de actuadores | — | `ao0`/`ao1` = densidad **CONFIRMADO**; `line7` = espejo **CONFIRMADO**; sentido durante espectros **NO CONFIRMADO** (el legado se contradice) | Q4, Q5 |
| ACT-N1 rutinas de PySpectrum sin conmutación; centrado a oscuras | REGRESIÓN + NUEVO | Sí | Q4 |
| X-01 líneas de obturadores distintas en las 3 versiones | — | El legado no puede ser referencia para las líneas digitales si hubo recableado | **Q2** |
| C-09 532 activo en BAJO | HEREDADO | Sí como riesgo; REQUIERE BANCO | Q3 |
| C-10 mapa hiperespectral | REGRESIÓN | Sí (el legado hacía `start` + `wait_for_frame` y guardaba) | — |
| C-20 HDF5 | NUEVO | Sí, acotado a la réplica `.h5` (los `.txt`/`.tiff` del legado siguen) | — |
| C-21 `TypeError` Gauss/Donut | NUEVO (divergencia de `confocal.py`) | Sí | — |
| C-29 heartbeat de 30 s | NUEVO | Sí, **y peor con §10**: corta exposiciones de más de 30 s en PySpectrum | — |
| C-30 E-STOP `WindowShortcut` | NUEVO | Sí | — |
| C-31 inclinación sin baja potencia | NUEVO | Sí (además, sin `wait_on_target`) | — |
| C-32 confocal sin validador | HEREDADO | Sí; 3.0 cambió el error visible por un recorte silencioso | — |
| C-33 `Laser532Window` sin watchdog | NUEVO | Sí | — |
| C-34 etiqueta del dock | NUEVO | Sí | — |
| C-41 contrapropagante: Save y títulos | NUEVO | Sí | Q9 |
| C-43 última posición al cerrar | HEREDADO (idéntico en los dos legados) | El hecho sí; no es un defecto nuevo | — |
| C-44 `ai3` doble | HEREDADO (de PSL) | Sí como inconsistencia | Q7 |
| C-45 dashboard NI | NUEVO | Sí (sólo indicador) | — |
| C-46 `reshape` fijo | NUEVO | Sí | — |
| C-53 `IsConnected()` | NUEVO | REQUIERE BANCO | — |
| AND sincronía e inicialización de la Andor | REGRESIÓN | Sí | Q12 |
| CP-1…CP-13 contrapropagante | NUEVO | Sí (CP-1 trigger en el BS, CP-3 = C-21, CP-7 abre el 532, CP-9 menús muertos) | Q9 |

## Preguntas para el investigador, por prioridad

1. **Q1 (C-01):** ¿La última impresión con PyPrinting 3.0 en el banco fue antes o después del 19-09-2026, y sus nodos terminaban en "success" o todos en "timeout", con la traza cayendo a 0 V cerca de 1 s (o con el láser abierto los 20 s de T_max)?
2. **Q2 (X-01):** ¿El cableado actual de obturadores es el de 3.0 (532→P0.11, 637→P0.8, 592→P0.9, 808→P0.10), y desde cuándo? ¿El legado de PySpectrum (532→P0.9, 637→P0.11, 808→P0.12) sigue siendo usable con ese cableado?
3. **Q3 (C-09):** ¿El controlador del obturador de 532 se alimenta de forma independiente de la PC, y alguna vez lo viste abierto con la PC apagada o durante el arranque?
4. **Q4 (ACT):** En `Growth_ps.py:788` y `Luminescence_steps_ps.py:733` el legado pone el espejo "up" antes de medir espectros, y en `Luminescence_ps.py:695` "down": ¿cuál es el correcto, o el espectrómetro recibe luz en las dos posiciones (por el beamsplitter)?
5. **Q5 (C-08):** ¿En las sesiones con PyPrinting 3.0 encontraste el rótulo "Mirror up/down" invertido respecto de la posición real, o tuviste que pulsarlo dos veces?
6. **Q6 (C-08):** ¿El espejo de `line7` tiene una posición definida al encender, y en qué posición quedó al cerrar la última sesión?
7. **Q7 (C-44):** ¿Qué está conectado físicamente en `ai3`: el trigger Z de la E-517 o el fotodiodo de 808 nm?
8. **Q8 (C-04):** ¿Qué offsets de red (150 y 1200) y de detector tiene hoy el Shamrock, para respaldarlos antes del primer arranque de PySpectrum 3.0?
9. **Q9 (C-41/CP):** En el contrapropagante, ¿TOP y BOT son dos fotodiodos fijos (ai0 en el derecho, ai1 en el invertido) o el fotodiodo del láser elegido?
10. **Q10 (C-03):** ¿En el legado se bajaba a mano la ganancia EM antes de "Go to zero order"?
11. **Q11 (C-07):** ¿Se usa alguna vez la entrada por fibra o la salida lateral del Shamrock, o siempre rendija lateral → cámara directa?
12. **Q12 (AND):** ¿La luminiscencia del legado se medía con una exposición simple por nodo (láser abierto) y nunca en "live" continuo?

---

## Ítems

### C-01 — Traza de impresión: tarea DAQmx continua leída 10 muestras cada 35 ms

**Clasificación: REGRESIÓN de 3.0** (introducida el 2026-09-19 por `6abbbfc`). **El hallazgo se sostiene** en su mecanismo; lo que queda abierto es si el banco corrió esa versión.

**(a) Cuándo se introdujo y cómo se leía antes.**

| Versión | Cómo lee la traza | Cadencia | ¿Datos actuales? |
|---|---|---|---|
| PPL `Trace_pp.py:375-382` + `Instrument_nidaqmx_pp.py:164-177` | Crea una tarea **FINITE** de 10 muestras a `rateNI/100` = 10 kS/s en cada tick, `read(10)`, `wait_until_done()`, `close()` | `pointtimer.start(0)` (`Trace_pp.py:373`): tan rápido como puede; el propio código anota "mean value of time step = 10 ms" (`:396`) | Sí: cada tick es una ráfaga nueva de 1 ms |
| PSL `Trace_ps.py:411-421` + `Instrument_nidaqmx_ps.py:191-202` | Crea **una** tarea FINITE al configurar la traza y hace `read(10)` en cada tick **sin `start()`**: DAQmx arranca la tarea implícitamente en cada lectura y la detiene al terminar | `start(0)` (`:413`) | Sí: cada lectura es una adquisición finita nueva |
| 3.0 `0a189c8` (2026-07-28) … `4a22652` (2026-09-04) | Igual que PPL: tarea FINITE por tick | 0 ms hasta `db6b67a` (2026-08-07), **10 ms** hasta `6444b0d` (2026-08-27), **35 ms** desde entonces | Sí |
| 3.0 `6abbbfc` (2026-09-19 01:26 −0300, DEC-013 "ANOM-TRACE-01", ya en `origin/main`) y árbol actual | `channels_photodiodos(rate, 10, continuous=True)` una vez por nodo (`modules/trace.py:627-628`), `CONTINUOUS` con `samps_per_chan = max(10·10, 1000) = 1000` (`core/nidaq.py:756-759`), y `self._task.read(10)` en cada tick (`trace.py:703`) sin `relative_to` ni `overwrite` | 35 ms (`trace.py:633`) | **No** (ver b) |

La motivación de DEC-013 (`DECISION_LOG.md:166`) fue que la cadencia por tick "dependía del scheduler". El cambio conservó `read(10)` por tick, es decir, pasó de "10 muestras nuevas cada tick" a "las 10 muestras siguientes de un flujo de 10 kS/s".

**(b) Semántica de DAQmx y cálculo.** Tasa por canal f = `RATE_MULTICHANNEL/100` = 1·10⁶/100 = 10 kS/s (`config.py:75`, `trace.py:501`); 5 canales (`PD_CHANS_LIST = [0, 1, 2, 3, 6]`, `config.py:87`), agregado 50 kS/s (lejos del máximo de 1 MS/s). Reglas de NI-DAQmx: (1) en adquisición continua el buffer es **por canal** e igual a `samps_per_chan`, salvo que sea menor que el valor de tabla para la tasa, y entonces se usa el de tabla (NI, "How Is Buffer Size Determined?" y KB "DAQmx Buffer Size Allocation"; tabla: 0-100 S/s → 1 kS, 101-10 000 S/s → 10 kS, 10 001-1 000 000 S/s → 100 kS, > 1 MS/s → 1 MS). (2) Por defecto se lee desde la posición de lectura actual (la muestra más vieja sin leer) y no se sobrescriben muestras sin leer.

- **Buffer:** max(1000, 10 000) = **10 000 muestras por canal = 1.0 s de señal**. (Si la frontera de 10 000 S/s cayera en la fila siguiente, 100 kS = 10 s; la tabla de NI la ubica en 10 kS. La FIFO de la placa agrega del orden de 10² muestras por canal; no cambia el orden de magnitud y no está verificada contra la hoja del 6353.)
- **Atraso:** el tick k (reloj ≈ 35·k ms) lee las muestras [10(k−1), 10k), es decir el milisegundo k de adquisición. El atraso crece como t_reloj − t_adq ≈ (1 − 1/35)·t_reloj = **0.97·t_reloj**: a 0.5 s de reloj la traza muestra la señal de los 14 ms iniciales; al segundo, la de los primeros 29 ms. Un evento ocurrido en el instante de adquisición t_a aparece en la GUI recién en ≈ 35·t_a, y sólo si t_a < ≈ 29 ms.
- **Desborde:** el atraso acumulado crece a 10 000 − 10/0.035 ≈ 9 714 muestras/s por canal y llena el buffer en **10 000 / 9 714 ≈ 1.03 s** tras cada `start()` (≈ 10.3 s con 100 kS). La cantidad de canales no cambia ese tiempo, porque el buffer es por canal.
- **Después del desborde:** DAQmx devuelve −200279 ("not able to keep up"; −200361 si desborda antes la FIFO). Según NI (foro, respuesta de un empleado de NI), la posición de lectura queda apuntando a datos que ya no existen; para recuperarse hay que detener y reiniciar la tarea, o cambiar `RelativeTo`/`Offset`. `trace.py` no hace ninguna de las dos cosas: cada excepción se registra como **0.0 V en los tres canales** (`trace.py:734-736`). Aun si el driver se recuperara, la lectura seguiría atrasada: en ningún caso vuelve a ser actual dentro del nodo.
- El reinicio por nodo (`_stop_and_save` cierra la tarea, `trace.py:638-644`; `trace_configuration` → `_start` crea otra) hace que **cada nodo** repita el ciclo: ≈ 1 s de señal "congelada" en sus primeros ≈ 29 ms y después ceros.

**(c) Caminos por los que en la práctica no se use la tarea continua.**

1. `SAFE_MODE` o DAQ aislada → `_MockNITask` (`nidaq.py:747-748`). No aplica a una impresión real (en `SAFE_MODE` no hay obturadores reales; el aislamiento se rechaza con placa física, `core/hardware_manager.py:370-376`).
2. Si **crear o configurar** la tarea falla, `channels_photodiodos` **no** lanza: devuelve `_UnavailableNITask` (NaN), cierra los obturadores y activa el interlock (`nidaq.py:763-774`, árbol actual, DEC-036 sin commitear). En `6abbbfc` (versión ya publicada) devolvía **en silencio** un `_MockNITask` que lee 0.5 V ± ruido ("Usando mock", diff de `6abbbfc`). En ninguno de los dos casos se cae al modo por tick.
3. **Único camino al modo por tick:** que `self._task.start()` lance (`trace.py:628-631`), por ejemplo −50103 "recurso reservado" si otra tarea de AI está corriendo. Ejemplo real: `trace_configuration` (`:662-670`, el camino de la impresión) **no** detiene la tarea continua de "Power BS" (`_bs_task`), a diferencia de `play_pause` (`:586-594`). Pero en ese caso la tarea FINITE por tick choca con el mismo recurso y también lee 0.0 V. No hay, por lo tanto, un camino plausible que dé datos buenos con la versión actual.

**(d) Qué hace `modules/measurements.py` con esos datos.** `grid_trace_detect` (`measurements.py:2325-2439`) toma `I_old`/`I_new` (ventanas móviles de `trace.py:747-759`, M = M2 = 10 ticks por defecto, `config.py:127-128`) y detiene el nodo si `should_stop` (según el modo, con `N_hold` = 5 en los modos 1-4) **o** `I_new < I_old·umbral_down` **o** `elapsed > T_max` (`:2408`). Sólo `should_stop` cuenta como "success"; las otras dos, como "timeout" (`:2413-2418`).

- **Datos atrasados (t < 1 s):** sólo los eventos de los primeros ≈ 29 ms de exposición pueden detectarse, y con ≈ 34× de retraso. Una captura que ocurre a los cientos de ms o a los segundos **nunca** se ve.
- **Ceros tras el desborde:** en el modo 0 no hay parada (`I_old > 0` y `I_new > 1.2·I_old` son falsos); en los modos 1-4 `c_abs = I_new > umbral_abs_v` es falso. Lo que decide es `umbral_down`:
  - con `umbral_down = 0.80` (los cuatro presets de `presets/*.txt:13` y `core/preset_manager.py:27, 65`): con M = 10, `I_new < 0.8·I_old` se cumple al tercer tick en cero, así que **todo nodo termina ≈ 1.1 s como "timeout"**;
  - con `umbral_down = 0` (**el caso por defecto**: `config.py:153`, texto inicial de la GUI `measurements.py:680`; al arrancar el combo queda en "Personalizado / Libre" y no se aplica ningún preset, `:1116`): `I_new < 0` nunca se cumple, así que **todo nodo queda con el láser abierto hasta T_max** (20 s por defecto, `config.py:154`) y termina como "timeout". El "Healing Pass" (`measurements.py:2860-2864`) lo reintenta con T_max + 10 s.
- **NaN** (`_UnavailableNITask`): toda comparación es falsa y se llega a T_max, pero con los obturadores ya cerrados por el interlock.

**(e) Conclusión.** El defecto **no es compatible con "PyPrinting 3.0 imprime bien"** si la impresión se hizo con un commit ≥ `6abbbfc` y la placa real: no habría ningún "success" y todas las trazas guardadas (`NP_xxx.txt`) caerían a 0 V cerca de 1 s. Sí es compatible con que **se depositen partículas**: con `umbral_down = 0` cada nodo queda expuesto hasta T_max (20 s), y con 0.80, ≈ 1.1 s. Si la impresión "funcionó", las explicaciones posibles, en orden de probabilidad, son:

1. la prueba de banco fue **anterior al 2026-09-19**, o la PC del banco tenía un `git pull` anterior a `6abbbfc`: entre el 07-28 y el 09-18 la traza usaba tareas FINITE por tick con datos actuales, como el legado;
2. se imprimió con la versión nueva, las NP se depositaron por exposición hasta T_max o hasta el corte a 1.1 s, y el estado "timeout" de los nodos se tomó como uno de los "detalles";
3. un comportamiento del driver distinto del documentado (improbable; B-07 lo mide).

**Hallazgo lateral (C-01b, REGRESIÓN, 2026-08-27, `6444b0d`):** aun con tareas finitas, 3.0 pasó de ≈ 10 ms por punto (legado) a **35 ms** por punto. Con M = 10, un escalón ×2 supera `1.2·I_old` al tercer punto: ≈ 30 ms en el legado frente a ≈ 105 ms en 3.0 (modo 0), o ≈ 245 ms con `N_hold = 5` (modos 1-4). Es sobreexposición después de la captura. Es independiente de C-01 y hay que tenerlo en cuenta al elegir el arreglo.

**Pregunta para el investigador (prioridad 1):** *¿La última impresión con PyPrinting 3.0 en el banco fue antes o después del 19-09-2026, y sus nodos terminaban en "success" o todos en "timeout", con la traza cayendo a 0 V cerca de 1 s?* (Alcanza con mirar la fecha de un `NP_xxx.txt` de esa sesión y si la columna de intensidad termina en ceros.)

---

### C-03 — Caminos al orden cero que no pasan por `ZeroOrderSafetyDialog`

**Clasificación: HEREDADO del legado** (el legado no tenía ninguna protección); 3.0 la agregó sólo en parte. **Se sostiene parcialmente.**

- **Legado:** PSL `Spectrum_ps.py:62-63, 138-139, 223-225`: el botón "Go to zero order" llama directo a `ShamrockGotoZeroOrder`, sin diálogo, sin bajar la ganancia EM y sin cerrar obturadores. `set_wavelength` (`:228-231`) acepta cualquier λ, incluido 0.
- **3.0**, los tres caminos del consolidado:
  1. `pyspectrum/modules/calibration_dock.py:713-718` (dock de Calibraciones, instanciado en `pyspectrum/window.py:509, 623`): `ShamrockGotoZeroOrder` directo. **Sin protección**, igual que el legado.
  2. `pyspectrum/modules/spectrum_control.py:272-280`: **sí tiene protección automática.** Antes de mover llama a `_apply_zero_order_detector_safeguard` (`:249-270`), que fuerza la ganancia EM a 0 y cierra todos los obturadores; `set_wavelength` hace lo mismo con λ ≤ 0.05 nm (`:228-231`). No pasa por el diálogo, pero no es un camino desprotegido. El consolidado lo sobreestima. Además es un panel oculto por defecto (`window.py:18-21`).
  3. `pyspectrum/ui/left_hardware_panel.py:206-207, 320-322`: λ central de 0 a 2000 nm y `ShamrockSetWavelength` sin chequeo. **Sin protección.**
- **Premisa:** el legado operó así sin daño conocido, porque el operador sabía qué hacía el botón. El riesgo es real (EMCCD con ganancia EM alta frente a la reflexión especular), pero no lo introdujo 3.0. Como PySpectrum 3.0 no se probó, la mitigación práctica es la misma del legado: ganancia EM en 0 antes de ir a orden cero.

**Pregunta:** *¿En el legado se bajaba a mano la ganancia EM (y se cerraba el láser) antes de "Go to zero order", o el orden cero se usaba con la ganancia EM encendida?*

### C-04 — Offsets escritos al Shamrock en cada arranque

**Clasificación: NUEVO en 3.0.** **Se sostiene.**

- **Legado:** PSL `Spectrum_ps.py:65-70, 121-125, 211-220`. Los offsets de red y de detector se escriben **sólo al pulsar "Set Offsets"**, con los valores de dos casillas (textos iniciales 100 y 0). No hay escritura automática.
- **3.0:** `calibration_dock.py:618-619` (defaults 12 / −35 / 0; detector 5) y `:1010-1017`: `load_calibration_from_txt`, llamado desde el constructor (`:633-635`), escribe al hardware los offsets de las tres redes, el del detector y el cero de la rendija, sin chequear `SAFE_MODE` y con `except: pass`. El archivo fuente, `pyspectrum/calibration/pyspectrum_calibration_last.txt`, lo creó el commit `0ebd7c6` (2026-09-09), firmado "Ingeniero de Instrumentación y Software"; declara 13 µm y `estado = CALIBRADO_VALIDADO`. No proviene de una medición.
- **Con la respuesta del investigador (§7):** el offset es un valor dinámico y calibrable. El defecto no está en que exista la escritura, sino en que sea **automática y con valores sin procedencia**. El legado (escritura manual con confirmación del operador) es la referencia.

**Pregunta:** *¿Qué offsets de red (150 y 1200) y de detector tiene hoy el Shamrock (según Solis o el último "Set Offsets" del legado), para respaldarlos antes del primer arranque de 3.0?*

### C-05 — Constantes de modo de lectura de la Andor corridas

**Clasificación: NUEVO en 3.0.** **Se sostiene.**

- **Legado:** desde el 18/07/24 la cámara se maneja con `pylablib` (`AndorSDK2Camera`, PSL `PySpectrum_UNSAM.py:45, 785`; `Camera_ps.py:10-22`) y sólo en **modo Image** (`Camera_ps.py:570`, `setup_image_mode(0,1002,0,1002)`). El driver propio anterior, `ccd_ps.py:891-892`, tenía la tabla correcta (FVB 0, Multi-Track 1, Random-Track 2, Single-Track 3, Image 4), pero ya no se importa (`PySpectrum_UNSAM.py:31`, comentado).
- **3.0:** `pyspectrum/drivers/andor_ccd_driver.py:36-40` define `SINGLE_TRACK = 1`, `MULTI_TRACK = 2`, `RANDOM_TRACK = 3` y los pasa sin traducir (`:534-539`). Lo usan `camera_andor.py:179, 396-435`, `linescan_spectroscopy.py:755, 870` y `static_raman.py:49`. Image = 4 y FVB = 0 coinciden con el SDK.
- **Premisa:** el legado nunca usó Single-Track ni FVB por hardware; son caminos nuevos de 3.0, que no se probó. No contradice la premisa.

### C-06 — Rendija con la firma de 2 argumentos llamada con 3

**Clasificación: REGRESIÓN de 3.0.** **Se sostiene.**

- **Legado:** PSL `Spectrum_ps.py:204-207`: `ShamrockSetAutoSlitWidth(DEVICE, INPUT_SLIT_PORT, slit_width)`, que es la función de 3 argumentos (wrapper de Andor, `Shamrock_ps.py:2016`). No lee la rendija.
- **3.0:** `pyspectrum/drivers/shamrock_driver.py:500-512` llama a `ShamrockSetSlit(device, index, width)`, pero la firma es `(device, width)` (`Shamrock_ps.py:2595`); `:488-494` llama a `ShamrockGetSlit(device, index, &w)`, cuya firma es `(device, &width)` (`Shamrock_ps.py:1519`). No hay `argtypes`. Inferencia sobre la convención de llamada x64 de Windows: en `SetSlit` la DLL lee el ancho de un registro XMM1 que el llamador no cargó (el valor queda indeterminado); en `GetSlit` la DLL recibe `1` como puntero y escribe en la dirección 0x1, lo que da una violación de acceso que ctypes convierte en `OSError`. `get_slit` no tiene `try` (`:488-494`).
- Lo llaman `left_hardware_panel.py:317`, `spectrum_control.py:237-239` y `calibration_dock.py:721-723`.

### C-07 — Selector de puertos del Shamrock con funciones inexistentes

**Clasificación: REGRESIÓN de 3.0.** **Se sostiene**, con un efecto práctico menor que el descrito.

- **Legado:** PSL `Spectrum_ps.py:160-163` **fuerza en cada arranque** la entrada Side (rendija) y la salida Direct (cámara) con `ShamrockSetFlipperMirror`, que existe en la DLL (`Shamrock_ps.py:2222`); el selector (`:170-185`) usa la misma función. Nombres: `Instrument_Shamrock_ps.py:26-27` (IN 0 = fibra, 1 = rendija; OUT 0 = cámara Andor, 1 = sin uso).
- **3.0:** `shamrock_driver.py:539-557` llama a `ShamrockSetFlipper`/`GetFlipper`, que no están en la DLL; el `AttributeError` se atrapa y se devuelve `COMMUNICATION_ERROR`. Llamadores: `left_hardware_panel.py:189, 196` y `spectrum_control.py:246-247`. Nadie fuerza los puertos al arrancar.
- **Efecto práctico:** el espejo de puertos del Shamrock es mecánico y conserva su posición. Si el legado o Solis lo dejaron en Side/Direct (el registro de Solis dice Side), 3.0 **seguiría midiendo bien por inercia**, pero la GUI puede mostrar un puerto falso y no podría cambiarlo.

**Pregunta:** *¿Se usa alguna vez la entrada por fibra (puerto directo) o la salida lateral, o siempre rendija lateral → cámara directa?*

---

### ACT — Mapeo de actuadores (verificación de la interpretación del investigador)

**Veredicto: CONFIRMADO para `ao0`/`ao1` (filtro de densidad) y para la identidad de `line7` (espejo, no notch). NO CONFIRMADO el sentido de `line7` durante la adquisición de espectros: el legado de PySpectrum se contradice a sí mismo.**

#### A. `Dev1/ao0` / `Dev1/ao1`: filtro de densidad (potencia alta/baja)

Asignación de canales idéntica en las tres versiones: `upFlipper` pulsa `ao0` y `downFlipper` pulsa `ao1` (PPL `Instrument_nidaqmx_pp.py:98-112`; PSL `Instrument_nidaqmx_ps.py:116-137`; 3.0 `config.py:82-83` y `core/nidaq.py:596-600, 645-697`, donde `_flipper_task0 = FLIPPER_AO_DOWN = ao1` es la de alta potencia). La GUI de los dos legados rotula el botón "Power" con "High power" → `downFlipper` y "Low power" → `upFlipper` (PPL `Shutters_pp.py:53-61, 157-161`; PSL `Shutters_ps.py:61-69, 184-189`, con los comentarios `#potencia alta` / `#potencia baja`). **Down = alta, up = baja: confirmado.**

| Rutina | Legado (archivo:línea, sentido) | 3.0 (archivo:línea, sentido) | ¿Coherente? |
|---|---|---|---|
| Impresión: antes del autofoco | PPL `Printing_pp.py:749` up; PSL `Printing_ps.py:703` up | `measurements.py:2252, 2263, 2501, 2875, 2883` up | Sí |
| Impresión: tras el autofoco, antes de la traza | PPL `Printing_pp.py:768` down; PSL `Printing_ps.py:723` down | `measurements.py:2311, 2318` down | Sí |
| Impresión: escaneo posterior | PPL `Printing_pp.py:818` up (escaneo), `:830` down (siguiente nodo) | `measurements.py:2444` up, `:2520` down | Sí |
| Dímeros: centrado, pre y post-escaneo | PPL `Dimers_pp.py:733` up, `:773, 793, 864` down, `:844` up; PSL `Dimers_ps.py:720…872`, igual | `measurements.py:2451` up (centrado), `:2535, 2543, 2548` down, `:2554` up (post) | Sí |
| Pausa / salida | PPL: sin acción en pausa | `measurements.py:2940` up en pausa; `nidaq.py:321-327` up en `atexit` | Más conservador que el legado (baja potencia) |
| Growth (PSL) | `Growth_ps.py:716, 734` up (autofoco, centrado); `:759, 772` down (irradiación con espectro) | `pyspectrum/modules/routines/growth_kinetics.py:686-707`: **ninguna llamada** | **No** (ver ACT-N1) |
| Luminiscencia por pasos (PSL) | `Luminescence_steps_ps.py:659, 677` up; `:705, 718` down | No existe; `luminescence.py` no conmuta la potencia | **No** |
| Dímeros (PySpectrum 3.0) | PSL `Dimers_ps.py:720-872` (ver arriba) | `pyspectrum/modules/routines/dimers.py:555-620`: **ninguna llamada** | **No** (ver ACT-N1) |

**Documentos que describen mal `ao0`/`ao1`:** `reserva/README_historico.md:200-201, 413-414` **invierte** el sentido ("DOWN (ao1) = filtro ND insertado para confocal; UP (ao0) = retira el filtro para imprimir"); es un archivo de reserva, pero hay que rotularlo. `SYS-202` título y `:212` ("Espejo Rebatible de Potencia", "recorrido angular del espejo"), `SYS-402:111` ("Conmutar el espejo rebatible (`down_flipper()`)"), `SYS-001:127` ("baja potencia, espejo arriba") y `CAT-105:87` ("el espejo flipper") lo llaman **espejo**: con el dato del investigador es un filtro de densidad. El resto (`SYS-201:205`, `SYS-302:159`, `SYS-305:175`, `CAT-103:124`, `MOD-01:127`, `MANUAL:382, 1724`) ya dice "filtro de densidad" o "atenuador" (con los errores de pulso y fuente de D-10, aparte).

#### B. `Dev1/port0/line7`: espejo de detección, no notch

- **Identidad:** los dos legados renombraron el control. PPL `Shutters_pp.py:63` (`def notch532_check(self): #Ahora es un espejo`) y `:101` (`QCheckBox('Mirror')`, textos "Mirror? Down" / "Mirror? Up", `:66, 69`). PSL `Shutters_ps.py:114-115` (`#QCheckBox('Notch 532 nm')` comentado → `QCheckBox('Mirror')`) y `:74-79`. El nombre `Flipper_notch532` sobrevive sólo en el código. **Confirma que "notch 532" es un nombre heredado y que el actuador es un espejo.** El dock de 3.0 conserva el rótulo correcto ("Mirror up/down", `core/shutters.py:291, 377`).
- **Mecanismo:** conmutador por pulso (el mismo pulso de 3 ms en ambos sentidos). El legado **persistía** la posición en un archivo (`flipper_notch532_status.txt`; PPL `Instrument_nidaqmx_pp.py:123-161`, PSL `Instrument_nidaqmx_ps.py:149-185`). Hoy PPL guarda `1` (down) y PSL `0` (up): **los dos legados tenían archivos separados para el mismo actuador**, así que usar uno después del otro desincronizaba el estado.
- **Sentido durante los espectros, llamada por llamada:**

| Rutina | Antes del espectro | Después | Observación |
|---|---|---|---|
| PSL `Luminescence_ps.py:694-695 / 746-747` | **down** | up | Las dos líneas tienen al lado la versión opuesta comentada (`#…'up'` / `#…'down'`): alguien invirtió el sentido |
| PSL `Growth_ps.py:788 / 817` (y `Growth - old_ps.py:728 / 754`, de 2022) | **up** | down | Opuesto a Luminescence |
| PSL `Luminescence_steps_ps.py:733 / 752` | **up** | down | Opuesto a Luminescence |
| PPL `PyPrinting_UNSAM.py:368`, `Shutters_pp.py:173`; PSL `Shutters_ps.py:201` | — | down al cerrar el programa | "Estacionamiento" en down |
| 3.0 `app.py:600`, `core/shutters.py:563` | — | down al cerrar | Igual que el legado |
| 3.0 `pyspectrum/modules/routines/luminescence.py:480-483` | sólo con los botones manuales "Insertar/Retirar Notch" (down/up) | — | La grilla (`:641-690`) **no** conmuta el espejo |

  El investigador afirma que `Luminescence_ps` y `Growth_ps` "lo bajan al adquirir espectros y lo suben al terminar". Eso vale para `Luminescence_ps`, pero **`Growth_ps` y `Luminescence_steps_ps` hacen lo contrario**. Con un conmutador sin realimentación, el rótulo up/down sólo significa algo si el archivo de estado estaba sincronizado; la inversión comentada en `Luminescence_ps` sugiere que alguna vez no lo estuvo.
- **3.0 frente al legado:**
  1. **REGRESIÓN:** 3.0 no persiste el estado. Arranca suponiendo "up" (`core/nidaq.py:107`, `_flipper_notch532_up = True`), pero al cerrar lo manda a "down" (`app.py:600`, `core/shutters.py:563`). En la segunda sesión, la memoria dice "up" y el espejo está físicamente en "down": **los rótulos quedan invertidos desde el arranque**, salvo que el operador lo corrija a mano. El legado evitaba esto con el archivo.
  2. `luminescence.py:435` arranca con `_notch_down = True` ("Dentro del haz"), en contradicción con `nidaq.py:107` (el mismo defecto que señala C-08).
  3. Las rutinas de grilla de PySpectrum 3.0 (luminiscencia, crecimiento, dímeros) **nunca** conmutan el espejo, mientras que las del legado lo hacían en cada nodo.

**Lugares a renombrar o corregir** ("notch 532" → "espejo de detección"; up = confocal y Canon, down = espectrómetro, a confirmar):

- *Código:* `config.py:81` (`FLIPPER_532_CHAN`); `core/nidaq.py:33, 107, 609, 627, 632, 699-725` (`flipper_notch532`, `_flipper_notch532_up`, docstrings); `core/shutters.py:27, 37, 55, 273-295, 377-392, 473, 496, 553-555, 563, 573, 580` (`notch532button`, `flipper_notch532_signal`, `notch532_change`; los rótulos "Mirror up/down" ya están bien); `app.py:28, 600`; `pyspectrum/modules/routines/luminescence.py:8, 24, 49, 54, 77, 176, 190-204, 335-337, 405, 409, 435, 454-483` (**rótulos semánticamente falsos**: "Filtro Notch 532 nm (Supresión Rayleigh)", "Insertar Notch (Bloquea Rayleigh)", "Dentro del haz (bloqueando Rayleigh)"); tests `tests/test_pyspectrum_luminescence_and_calibration.py:4`, `tests/test_hardware_session_master_slave.py:105`, `tests/test_prompt_corpus_integrity.py:665-666` (gate de `FLIPPER_532_CHAN`); `reserva/app.py`, `reserva/app2.py` (archivo).
- *Documentación:* `.claude/shared/lab-invariants.md:46`; `docs/MANUAL_USUARIO.md:384` ("espejo de desviación hacia el filtro Notch"), `:788-789`; `docs/modulos/MOD-01_Microscopio_Derecho_App.md:128`; `docs/modulos/MOD-06_PySpectrum_Espectroscopia_Shamrock.md:376, 380-381, 399` (381 deduce la semántica "down = dentro del haz" del cierre, un razonamiento circular); `reportes/cientificos/CAT-103…:125`; `reportes/cientificos/CAT-251…:75` ("Subir Filtro Notch" como paso 8; los 2 notch **manuales y fijos** de `:55-58, 164` sí existen y no se renombran) y `:215`; `reportes/sistema/SYS-102…:135`; `SYS-307…:95-99` ("el filtro Notch DEBE colocarse", atribuido al flipper); `SYS-305…:174` (ya corregido en el árbol, verificar que las filas 5-9 de `:144-148`, "Flipper Down → Espectrómetro", nombren el espejo y no el flipper de potencia); `docs/decisions/DECISION_LOG.md:32, 260-270` (DEC-021: agregar una nota, no reescribir); `reserva/README_historico.md:424` ("espejo dicroico en la vía de colección").

#### ACT-N1 (no está en el consolidado): las rutinas de grilla de PySpectrum 3.0 no conmutan potencia ni detección (REGRESIÓN), y el centrado confocal barre a oscuras (NUEVO)

- `pyspectrum/modules/routines/growth_kinetics.py:686-707` y `dimers.py:574-620` hacen autofoco, centrado, "impresión" y espectro **sin ninguna llamada** a `up_flipper`/`down_flipper`/`flipper_notch532`. El legado (`Growth_ps.py:716-817`, `Dimers_ps.py:720-872`) bajaba la potencia para autofoco y escaneos, la subía para irradiar o imprimir, y conmutaba el espejo alrededor de cada espectro. En 3.0 el autofoco y el centrado corren con la potencia que haya quedado (puede ser la alta), y los espectros con el espejo donde haya quedado.
- `pyspectrum/modules/optical_support.py:124-160` (`run_confocal_centering`) mueve la platina y lee el fotodiodo **sin abrir ningún obturador**. En `growth_kinetics.py:692-695` se llama **antes** de `open_shutter` (`:703`), y en `dimers.py:588, 612`, **después** de `close_shutter` (`:583, 604`): **el centrado barre en oscuridad** y mueve la platina al centroide del ruido. Además usa `pi.MOV` sin `wait_on_target` en cada píxel (`:143-146`), y `move_stage_to` (`:95-122`) ignora el timeout de `qONT` y sigue adelante (contra DEC-036).
- El legado usaba el módulo confocal (`grid_scanSignal`), que abre su propio obturador. 3.0 reimplementó el centrado en `optical_support` y perdió eso: es la misma clase de defecto por "herramientas duplicadas" que el investigador describe en el contrapropagante.

**Preguntas (prioridad 1-2):**
1. *En `Growth_ps.py:788` y `Luminescence_steps_ps.py:733` el legado pone el espejo "up" antes de medir espectros, y en `Luminescence_ps.py:695` "down": ¿cuál es el correcto, o el espectrómetro recibe luz en las dos posiciones (por el beamsplitter)?*
2. *¿El espejo de `line7` tiene una posición de reposo definida al encender (p. ej., el MFF101 recuerda la última), y en qué posición lo dejaste al cerrar la última sesión?*

### C-08 — Estado del actuador de `line7` sólo en memoria y sin posición comandada al arrancar

**Clasificación: REGRESIÓN de 3.0** (el legado persistía el estado en un archivo). **Se sostiene** en su parte mecánica. Queda **refutada su premisa física** ("el filtro protege al EMCCD de la línea Rayleigh"): por el dato del investigador y por el propio legado (`Shutters_pp.py:63`, "Ahora es un espejo"), no es un filtro. La protección Rayleigh la dan los 2 notch fijos manuales (CAT-251:55-58).

- **3.0:** `core/nidaq.py:107` (memoria, inicial "up"), `:699-725` (conmutador); `luminescence.py:435` (inicial "down"); cierre en "down" (`app.py:600`, `core/shutters.py:563`). La desincronización en la segunda sesión está descrita en ACT-B.
- **Legado:** estado en `flipper_notch532_status.txt` (PPL `:151-161`, PSL `:176-185`). Tampoco comandaba una posición absoluta al arrancar (no puede: es un conmutador sin realimentación), pero **recordaba la última**.
- **Premisa:** compatible. El legado funcionaba porque recordaba el estado, y porque el operador veía en la cámara o el espectrómetro si la luz llegaba.
- **Consecuencia real en 3.0:** tras un cierre limpio, "Mirror up" en el dock de PyPrinting significa físicamente "down" (espectrómetro). Si PyPrinting 3.0 imprimió bien en el banco, lo más probable es que nadie tocara ese botón, o que el operador lo corrigiera mirando.

**Pregunta:** *¿En las sesiones con PyPrinting 3.0 tuviste que pulsar "Mirror" dos veces, o encontraste el rótulo invertido respecto de la posición real?*

### X-01 (lateral, no está en la lista pedida): las tres versiones asignan líneas distintas a los obturadores y a los fotodiodos

Con la premisa "el legado es la referencia", esto no puede valer a la vez para los dos legados y para 3.0 con un mismo cableado.

| | 532 nm | 592/594 nm | 637 nm | 808 nm | BS | Polaridad (abrir) |
|---|---|---|---|---|---|---|
| PPL `Instrument_nidaqmx_pp.py:9-19` | P0.12, ai0 | — | P0.11, ai1 | — | ai6 | 532 y 637 en BAJO (el 532 escribe ALTO y luego BAJO en la misma llamada, `:39-50`) |
| PSL `Instrument_nidaqmx_ps.py:7-24, 61-106` | P0.9, ai0 | P0.10, ai1 | P0.11, ai6 | P0.12, ai3 | ai5 | 532, 594 y 637 en BAJO; **808 en ALTO** |
| 3.0 desde `b91c743`/`427b492` (2026-08-27, "canales físicos reales"), `config.py:77-87` | **P0.11**, ai0 | P0.9, ai1 | P0.8, ai2 | P0.10, ai3 | ai6 | 532 en BAJO; 637, 592 y 808 en ALTO |
| 3.0 `0a189c8` (2026-07-28) | P0.12 (ALTO) | P0.10 | P0.11 (BAJO) | — | ai6 | copia parcial de PPL |

La línea P0.11 es el **637 nm en los dos legados** y el **532 nm en 3.0**. Como 3.0 imprime en el banco con 532, lo más probable es que el cableado haya cambiado entre el último uso del legado y el 2026-08-27 (¿las dos BNC-2110?). En ese caso, el legado de PySpectrum **ya no es referencia para las líneas digitales** y abriría obturadores equivocados si se ejecutara hoy. **Pregunta (prioridad 1):** *¿El cableado actual de obturadores es el de 3.0 (532→P0.11, 637→P0.8, 592→P0.9, 808→P0.10), y desde cuándo? ¿Se puede seguir usando el legado de PySpectrum con ese cableado?*

---

### C-09 — Obturador de 532 nm activo en BAJO: con la línea sin manejar, el pull-down lo abriría

**Clasificación: HEREDADO del legado** (es una propiedad del cableado y del controlador del obturador, y los dos legados la tienen). **Se sostiene como riesgo**; la consecuencia física sigue siendo REQUIERE BANCO.

- **Legado:** en los dos, el estado final de "abrir 532" es BAJO. PPL `Instrument_nidaqmx_pp.py:39-50`: escribe `True` y, por el `else` mal anidado, enseguida `False`. PSL `Instrument_nidaqmx_ps.py:61-83`: lo mismo. El cierre escribe primero `False` (**abierto**) y enseguida `True` (`:65-76` y `:85-106`). **El legado genera en cada cierre un pulso breve de "abrir"** (dos escrituras temporizadas por software, del orden de 1 ms). Un obturador mecánico probablemente no llega a responder, pero es la huella de un código que originalmente suponía activo en ALTO y se parcheó.
- **3.0:** `config.py:79` (`SHUTTER_POLARITY[532] = False`). Las cuatro líneas se escriben juntas y el estado se adopta sólo tras una escritura confirmada (`core/nidaq.py:382-395`), sin el pulso espurio del legado.
- **Premisa:** el legado funcionaba con la misma polaridad. El riesgo sólo aparece con la PC apagada, la placa reseteada o el proceso muerto, estados que un uso normal no ejercita. No contradice la premisa.

**Pregunta (prioridad 1, seguridad):** *¿El controlador del obturador de 532 se alimenta de forma independiente de la PC, y alguna vez lo viste abierto con la PC apagada o durante el arranque?*

### C-10 — Mapa hiperespectral: `MOV` y `GetMostRecentImage` en el mismo tick, sin adquisición sincronizada ni guardado

**Clasificación: REGRESIÓN de 3.0.** **Se sostiene.**

- **Legado:** PSL `Confocal_Spectrum_ps.py:611-625` (`scan_step_xy`): `MOV`, y después `scan_step()` → `taking_picture()` (`:724-743`), que hace `start_acquisition()` + `wait_for_frame()` + `read_oldest_image(shape)`. La espera de la exposición es bloqueante y hay una adquisición nueva por píxel. Cada espectro se guarda (`save_spectrum`, `:794`; `save_calibration_spectrum`, `:583, 783-790`). Lo único que falta es la espera de asentamiento de la platina (`qONT` comentado, `:622-623`), un defecto **heredado** y menor (asentamiento de ms frente a exposiciones de ≥ 0.1 s).
- **3.0:** `pyspectrum/modules/hyperspectral_confocal.py:328-345`: `pi.MOV` y enseguida `camera.get_most_recent_image()`, en el mismo tick del `QTimer`, sin `StartAcquisition` ni espera. `andor_ccd_driver.py:520-532` devuelve ceros ante cualquier falla. El cubo vive sólo en memoria. `scanFinishedSignal` se emite dos veces (`:325` dentro de `stop_scan` y `:370`).
- **Premisa:** PySpectrum 3.0 no se probó; el legado lo hacía bien.

### C-46 — `GetMostRecentImage` con forma fija 1004 × 1002

**Clasificación: NUEVO en 3.0.** **Se sostiene.**

- **Legado:** `pylablib` (`read_oldest_image(self.shape)`, PSL `Confocal_Spectrum_ps.py:743`) recibe la forma de la configuración, y el legado sólo usaba modo Image.
- **3.0:** `andor_ccd_driver.py:520-532` pide 1004·1002 píxeles siempre. En FVB (1 × 1004) o Single-Track, el SDK rechaza el tamaño del buffer y el driver devuelve una imagen de ceros sin avisar. Afecta a los modos nuevos de C-05.

### C-20 — HDF5 del lote: `t_print_s` pisado a 0 y un solo `confocal_scan` por nodo

**Clasificación: NUEVO en 3.0** (el legado no tenía HDF5). **Se sostiene**, con un impacto acotado.

- **Legado:** PPL `Printing_pp.py:800-848` (y PSL `Printing_ps.py`) guarda por nodo `NP_%03d.txt` (traza), `NPscan_%03d.tiff`, `gone_…` y `back_…` (TIFF del array crudo) y `printing_error-*.txt`. No hay contenedor por lote.
- **3.0:** conserva los archivos del legado (`modules/measurements.py:2968-2981`, `NP_xxx.txt` con `t_print` en la cabecera; `:2996-3032`, TIFF, `.npy` y `.csv`) y **agrega** el `.h5`, donde `core/hdf5_container.py:150-151` pisa `t_print_s = 0.0` al registrar el escaneo (`measurements.py:3001-3007`) y `:171-176` reemplaza `confocal_scan`.
- **Premisa:** los datos primarios del legado siguen escribiéndose; la pérdida se limita a la réplica `.h5`. Es lo que ya indica el consolidado ("usar `NP_xxx.txt`").
- **Laterales:** (a) el TIFF primario de 3.0 se **normaliza** min-max a uint16 (`:3024-3031`): pierde la escala en voltios que el TIFF del legado (float) conservaba; el `.npy` y el `.csv` sí la conservan. (b) Desde `6abbbfc`, `grid_trace_detect` guarda `self.data1 = data[2]`, que llega **recortado a 2000 muestras** (`trace.py:44, 769-771`), mientras `self.ptr = data[0]` es el contador global. Una traza de más de 2000 puntos (≈ 70 s, es decir T_max > 60 s con el "Healing Pass" de +10 s, `measurements.py:2860`) arma `t` y `data1` de largos distintos en `_save_trace` (`:2971, 2981`).

---

### CP — Mapa de duplicación del contrapropagante (`contrapropagante.py`)

El contrapropagante **no existe en ninguno de los dos legados**: nace en 3.0 (`18316d1`, 2026-08-03). Por eso todos sus defectos son **NUEVOS en 3.0**. La referencia de funcionamiento es el microscopio derecho de 3.0 (`app.py` + `modules/confocal.py`), que el investigador dice que funciona.

**Qué reutiliza sin duplicar** (importa las mismas clases que `app.py`): `nanopositioning.Backend`, `shutters.Backend`, `focus.Backend`, `trace.Backend`, `measurements.Backend` (impresión y dímeros), `camera.CanonWorker`, `Laser532Backend` (`contrapropagante.py:48-55, 1181-1195`). La máquina de estados de impresión es la misma, así que C-01 le afecta igual.

**Qué duplica:** (1) el confocal completo, en `ConfocalDualBackend` (`:416-922`), frente a `modules/confocal.py::Backend`; (2) el cableado de señales, en `Backend._connect_backends` (`:1197-1262`) y `create_contrapropagante_satellite` (`:1264-1307`), frente a `app.py:440-540, 630-650`.

| # | Divergencia (candidata a "falla de lógica") | Contrapropagante | Microscopio derecho (referencia) | Efecto |
|---|---|---|---|---|
| CP-1 | **Canal de trigger indexado por número físico** | `:737-738` `trig = data[TRIGGER_CHANNELS[axis]]`: para X, `data[4]` es la fila de **ai6 (BS)**, porque las filas siguen `PD_CHANS_LIST = [0,1,2,3,6]` + trigger. Para Y, `data[5]` acierta por coincidencia | `confocal.py:942, 951`: `trigger = data[len(PD_CHANS_LIST)]` | En los modos x/y (el default) y x/z, los flancos se buscan en el fotodiodo del BS, no aparecen y se cae a `ph[:L//2]` (`:747-748`): la ida completa, con los márgenes `extra` (±range/6) y sin recortar por trigger. Resultado: la imagen cubre ≈ 1.33× el rango nominal, pero el centro se convierte con el rango nominal (`:908-911`), así que hay **error de escala en el centrado** fuera del eje. Invisible en `SAFE_MODE` (`:726-727` devuelve datos sintéticos) |
| CP-2 | Fotodiodo indexado por número físico | `:733-736` `data[PD_CHANNELS[láser]]` | `confocal.py:942` `data[PD_CHANS_LIST.index(PD_CHANNELS[láser])]` | Hoy coincide para 0-3; se rompe si cambia `PD_CHANS_LIST` |
| CP-3 | **`center_of_gauss2D`/`center_of_donut2D` sin semilla** (C-21) | `:901, 904`, sobre la imagen umbralizada `Zf` | `confocal.py:1150-1151, 1159-1160`: CM de `Zf` como semilla y ajuste sobre `Zn` sin umbralizar | `TypeError` dentro de `_finish_ramp_scan` (`:762`), después de cerrar los obturadores y **antes** del `MOV` de retorno y de `gridScanFinishedSignal`: la rutina de grilla queda detenida. Aun con la semilla, ajustar sobre `Zf` sesga como en C-17 |
| CP-4 | Sólo segmento de ida y reconstrucción simplificada | `:740-750` | `confocal.py:955-985` (`_profiles`: ida y vuelta, fallbacks con aviso) | Sin imágenes `gone`/`back`: `gridScanFinishedSignal` emite `None, None` (`:769-771`) y `measurements._save_scan` no guarda los TIFF `gone_`/`back_` que sí guarda el derecho |
| CP-5 | Orden `start`/`WGO` | `:722-724`: la tarea se crea, se dispara `WGO` y la adquisición arranca implícitamente en `read` | Igual en `confocal.py:937-941` | Sin divergencia; es heredado del legado (PSL `Confocal_ps.py:1176-1184`) |
| CP-6 | Opciones de GUI que no hacen nada | `scan_mode_opt` e `image_scan_opt` se guardan (`:527, 531`) y nunca se leen: no hay modo por pasos ni inversión de imagen | `confocal.py:1168-1180` (`_norm_image` usa `image_scan_option`); modo por pasos `:775-856` | Combos decorativos |
| CP-7 | Láser BOT fijo en la rutina de grilla | `start_scan_routines` (`:564-570`) fuerza `bot_idx = 0` y `start_scan` abre los dos obturadores (`:605-606`) | `confocal.py` abre sólo `self.laser` | En una impresión con 637/592/808, cada escaneo de la rutina **abre además el 532** |
| CP-8 | Movimiento a la referencia sin espera | `_goto_ref` (`:914-922`) y `stop_scan` (`:619`) hacen `pi.MOV` sin `wait_on_target` | `confocal.py:1203-1208` (`_moveto` con `wait_on_target` y cierre de obturadores si falla, DEC-036) | Contra DEC-036 |
| CP-9 | Directorio y grilla por menú desconectados | `selectDirSignal`, `loadGridSignal` (`:931, 935, 1011, 1022`) sin ningún `connect`; `fileSignal` sólo va a la cámara (`:1168-1170`) | `app.py:516-525` propaga `fileSignal` a traza, confocal, cámara, impresión y dímeros | La impresión guarda en `DEFAULT_DATA_PATH`; el confocal dual no guarda nada. La grilla sí se puede cargar con el botón propio del widget de Mediciones (`measurements.py:1099-1104`) |
| CP-10 | "💾 Save Frame" | `saveSignal` (`:86, 258`) sin conectar | `confocal.py` guarda el TIFF | C-41 |
| CP-11 | Títulos fijos "Fotodiodo 1 / ai0" y "Fotodiodo 2 / ai1" | `:178-179, 345-346`; la adquisición usa el fotodiodo **del láser elegido** (`:733-734`) | — | C-41; ver la pregunta |
| CP-12 | Hilos | Mismo reparto que `app.py:630-644` (`:1274-1296`) | — | Sin divergencia |

### C-21 — `TypeError` en el centrado Gauss/Donut del contrapropagante

**Clasificación: NUEVO en 3.0** (el contrapropagante no existe en el legado); es una **divergencia respecto de `modules/confocal.py`**, que sí pasa la semilla. **Se sostiene** (CP-3).

- En el legado el centrado gaussiano siempre recibió la semilla: `center_of_gauss2D(Zn, x_cm, y_cm)` en PPL `Confocal_pp.py:1284` y PSL `Confocal_ps.py:1386`, igual que el derecho de 3.0.
- **Premisa:** es exactamente la clase de "falla de lógica por herramienta duplicada" que describe el investigador. Con el método por defecto ("center of mass", `contrapropagante.py:61-62`) no se manifiesta.

### C-41 — "Save Frame" sin conectar y títulos de canal fijos

**Clasificación: NUEVO en 3.0.** **Se sostiene** (CP-10, CP-11).

**Pregunta (prioridad 2):** *En el contrapropagante, ¿TOP y BOT son dos fotodiodos fijos (ai0 en el derecho, ai1 en el invertido, como dicen los títulos) o el fotodiodo que corresponde al láser elegido (como hace el código)?*

---

### CP-13 (agregado al mapa): el contrapropagante no guarda la última posición

`ContrapropaganteMainWindow.closeEvent` (`contrapropagante.py:1124-1132`) sólo emite `closeSignal`. `app.py:576-582` (`close_all`) guarda `LAST_POS_FILE` al cerrar. `LAST_POS_FILE` se importa (`contrapropagante.py:41`) y no se usa.

### C-29 — `heartbeat_shutter(30.0)` explícito pisa la política global

**Clasificación: NUEVO en 3.0** (ningún legado tiene watchdog: `grep -i "watchdog|heartbeat"` en PPL y PSL no da resultados). **Se sostiene**, y con la respuesta del investigador (§10: "el watchdog nunca debe dispararse en medio de una rutina") **es más grave** que lo que dice el consolidado.

- **3.0:** `modules/trace.py:612, 681`; `modules/focus.py:240, 266, 325, 379`; PySpectrum: `optical_support.py:52, 61, 146`, `growth_kinetics.py:544, 683, 745`, `luminescence.py:527, 659, 675`, `dimers.py:538`, `linescan_spectroscopy.py:570-624`, `step_and_glue.py:417, 422`, `calibration_dock.py:867, 910`.
- **Corte a mitad de rutina:** `luminescence.py:675-676` renueva 30 s y **después** bloquea una adquisición cuya exposición admite hasta **60 s** (`:248`, `spin_grid_exp.setRange(0.001, 60.0)`); lo mismo `growth_kinetics.py:242` y `dimers.py:200`. Con una exposición de más de 30 s, el watchdog cierra el obturador en plena exposición. PyPrinting 3.0 no lo sufre: la traza renueva cada ≈ 1 s y la impresión usa la política global (`measurements.py:2333`).
- **Premisa:** no la afecta (PySpectrum 3.0 no se probó). El legado no cortaba nunca.

### C-30 — E-STOP por teclado de PySpectrum como `WindowShortcut`

**Clasificación: NUEVO en 3.0** (el legado no tenía E-STOP: sus `QShortcut` son `Ctrl+A/S/D` para directorios, PSL `PySpectrum_UNSAM.py:117-123`, y `F1`/`F2` para la traza, PPL `Trace_pp.py:59-62`). **Se sostiene:** `pyspectrum/window.py:543-546` crea los `QShortcut` de `Ctrl+E`/`F12` con el contexto por defecto (`WindowShortcut`).

### C-31 — Inclinación por 4 esquinas sin pasar a baja potencia

**Clasificación: NUEVO en 3.0** (ningún legado tiene compensación de inclinación). **Se sostiene**, y **agrega un defecto**: `modules/confocal.py:545-570` abre el obturador una vez, recorre las 4 esquinas con `pi.MOV` + `time.sleep(0.05)` **sin `wait_on_target`** (contra DEC-036) y hace autofoco en cada una sin `up_flipper()`. En el camino de impresión del legado, todo autofoco va precedido de `upFlipper()` (PPL `Printing_pp.py:749`; en 3.0, `measurements.py:2252, 2263`).

### C-32 — Range, Pixels y Filtro del confocal sin validador

**Clasificación: HEREDADO del legado** (PPL `Confocal_pp.py:185-198`: `QLineEdit` sin validador), **con otro modo de falla en 3.0.** En el legado, un origen de rampa fuera de recorrido (`Confocal_pp.py:1066-1070`, sin acotar) lo rechazaba el firmware (GCS 7) y el error se veía. 3.0 lo acota en silencio (`_PIController.MOV`, DEC-011) y la imagen sale deformada sin aviso. **Se sostiene.**

### C-33 — `Laser532Window` no se entera del cierre por watchdog

**Clasificación: NUEVO en 3.0** (sin watchdog en el legado; `Laser_532.py` de PPL no tiene estado de obturador). **Se sostiene:** `modules/camera.py` no llama a `register_watchdog_callback` (grep), a diferencia de `core/shutters.py:70-71`.

### C-34 — Etiqueta de seguridad del dock calculada desde sus casillas

**Clasificación: NUEVO en 3.0.** **Se sostiene:** `core/shutters.py:317-321` (`any_open` desde `shutter*button.isChecked()`); no ve los obturadores que abre una rutina.

### C-43 — La última posición sólo se guarda al cerrar

**Clasificación: HEREDADO del legado.** **No es un defecto nuevo;** el legado hacía exactamente lo mismo: PPL `PyPrinting_UNSAM.py:354-359` guarda `Last_position.txt` en el cierre y `:316-326` la carga desde el menú; PSL `PySpectrum_UNSAM.py:345, 547-552`, igual. 3.0: `app.py:559-562, 576-582`. `LAST_POS_FILE` importado y sin uso en `measurements.py:43` y `contrapropagante.py:41` (ver CP-13). Con la premisa, es un comportamiento aceptado. Como mejora: guardar al terminar cada rutina.

### C-44 — `ai3` como fotodiodo de 808 nm y como trigger Z

**Clasificación: HEREDADO del legado de PySpectrum** (PSL `Instrument_nidaqmx_ps.py:20-27`: `PD_channels['808 nm'] = 3` y `Trigger_channels['Z'] = 3`). En PPL no hay colisión (`PDchans = [0, 1, 2, 6]`, trigger Z = 3). En 3.0 `ai3` está en `PD_CHANS_LIST` desde el primer commit (con el 592 nm en `0a189c8`, con el 808 nm desde `427b492`), y el trigger Z sigue en `ai3` (`config.py:86-88`). **Se sostiene** como inconsistencia.

- En el autofoco (`modules/focus.py:430-431, 447-448`) la tarea lleva `ai3` dos veces: como `chan_PD3` y como `trigger_pi_3`. El trigger se toma de la última fila, que es correcta, siempre que DAQmx acepte el canal físico repetido (no verificado).
- **Lo que no puede ser cierto a la vez:** si `ai3` es el trigger Z cableado a la E-517, entonces "fotodiodo de 808" en la traza y el confocal lee el trigger, no luz. Si es el fotodiodo, el autofoco no tiene trigger.

**Pregunta (prioridad 2):** *¿Qué está conectado físicamente en `ai3`: el trigger Z de la E-517 o el fotodiodo de 808 nm?*

### C-45 — Dashboard: "NI-DAQmx conectado" con cualquier dispositivo NI; 532 "conectado" porque lo está la DAQ

**Clasificación: NUEVO en 3.0** (el legado no tiene dashboard). **Se sostiene** (`core/hardware_manager.py:160-170`: `if "Dev1" in devs or len(devs) > 0`; `:208-217`). Es un indicador, no un interlock.

### C-53 — `IsConnected()` no detecta un desenchufe físico

**Clasificación: NUEVO en 3.0** (el legado conecta por USB con número de serie, PPL `Instrument_PI_pp.py:9-10`, y no vigila la conexión). Es una limitación de pipython que sólo importa porque 3.0 muestra un estado. REQUIERE BANCO. **Se sostiene como duda.**

### AND — Inicialización y sincronía de la Andor en PySpectrum 3.0 frente al legado

**Clasificación: REGRESIÓN de 3.0** (el legado usaba `pylablib`, que resuelve estas cuestiones). Complementa C-05, C-10 y C-46.

1. **Adquisición no sincronizada con la exposición en las rutinas de grilla.** Luminiscencia (`luminescence.py:673-678` → `_acquire_read_mode_aware`, `:690-696`), crecimiento (`growth_kinetics.py:720-760`) y dímeros (`dimers.py:614-617`: `start_acquisition()` y en la línea siguiente `get_most_recent_image()`) leen el último cuadro disponible sin esperar a que termine la exposición iniciada con el láser abierto. El legado hacía `start_acquisition()` + `wait_for_frame()` + `read_oldest_image()` (PSL `Confocal_Spectrum_ps.py:737-743`). En 3.0 el espectro puede corresponder a un cuadro anterior a la apertura del obturador, o ser ceros (`andor_ccd_driver.py:520-532`).
2. **Parámetros que el legado fijaba y 3.0 no:** velocidad de desplazamiento vertical (legado `set_vsspeed(2)`, "1.9 µs", PSL `Camera_ps.py:607`) y modo de ventilador (`AndorSDK2Camera(..., fan_mode="low")`, PSL `PySpectrum_UNSAM.py:785`). `andor_ccd_driver.py` no llama a `SetVSSpeed` ni a `SetFanMode` (grep), así que quedan los defaults del SDK tras `Initialize`.
3. `set_output_amplifier(1)` ("convencional", `andor_ccd_driver.py:458-467`; expuesto en `left_hardware_panel.py:271` y `camera_andor.py:460-461`) apunta a un amplificador que el 885 no tiene (D-18).

**Pregunta:** *¿El espectro de luminiscencia del legado se tomaba con la cámara en adquisición simple (una exposición por nodo, con el láser abierto) y nunca en "live" continuo?*

---

## Fuentes externas consultadas (C-01)

- NI, "How Is Buffer Size Determined?" (NI-DAQmx Help), https://www.ni.com/docs/en-US/bundle/ni-daqmx/page/buffersize.html, y KB "DAQmx Buffer Size Allocation for Finite or Continuous Acquisition", https://knowledge.ni.com/KnowledgeArticleDetails?id=kA00Z000000P9PkSAK: regla del buffer continuo y tabla por tasa. El texto de la tabla se obtuvo de resúmenes de búsqueda, porque la página oficial no se pudo descargar; conviene confirmarlo en el NI-DAQmx Help instalado en la PC del banco.
- NI Community, "Stuck in Error -200279", https://forums.ni.com/t5/LabVIEW/Stuck-in-Error-200279/td-p/1450294: tras el desborde, la posición de lectura apunta a datos inexistentes, y hay que reiniciar la tarea o cambiar `RelativeTo`/`Offset`.
- NI KB "Error -200279: Unable to Keep Up With Acquisition in NI-DAQmx", https://knowledge.ni.com/KnowledgeArticleDetails?id=kA00Z0000019KTeSAM.

