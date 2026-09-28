# Bloque A de PySpectrum 3.0 — Ronda 1, sonda de falsación (`devil-advocate`)

**Fecha:** 2026-09-28. **Alcance:** primer arranque seguro contra el banco (orden cero, offsets y eje λ del Shamrock, Step & Glue, inicialización de la Andor iXon3 885). **Método:** leí el código (orientado con `graphify query`/`explain`), el legado local (`scratch/pyspectrum-legacy/`), el historial de git, `TRIAGE_SISTEMA_VS_LEGADO.md` (C-03 a C-07, AND), `RESPUESTAS_INVESTIGADOR.md` (§7, §10, R2-2, R2-9 a R2-11, R4), `PRUEBAS_BANCO_PENDIENTES.md` y dos fuentes primarias: el **Andor SDK2 User's Guide v2.104** (`docs/bibliografia/Software Development Kit.pdf`, SDK de **cámaras**; lo cito por nombre de función) y la hoja de datos del iXon3 885 (`docs/bibliografia/Andor_iXon3_885_Specifications.pdf`). **No ejecuté nada contra el hardware ni corrí `pytest`.**

**Qué no tiene fuente primaria.** El repositorio **no tiene el manual del SDK del Shamrock**. Para el Shamrock, lo único que se parece a una fuente son los docstrings de Andor en el wrapper del legado (`scratch/pyspectrum-legacy/Shamrock_ps.py`). Todo lo que digo aquí sobre la persistencia de los offsets, sus unidades y la semántica del offset del detector es **inferencia** y lo marco como tal.

**Etiquetas:** [código] = verificado leyendo el código · [SDK] = Andor SDK2 v2.104 · [DS] = hoja de datos del iXon3 885 · [legado] = copia local del legado · [inferencia] = razonamiento sin verificar.

**Veredicto:** `HIGH_RISK_ASSUMPTIONS`. El plan ataca bien los defectos que ya estaban catalogados. Pero da por sentado (a) que el estado actual del equipo es conocido e intacto, (b) que leer es inocuo y (c) que lo que el software muestra coincide con lo que la cámara tiene configurado. Ninguna de las tres cosas está probada, y hay evidencia en contra de las tres.

---

## 0. Dos hechos que condicionan todo el bloque

**0.1. La PC del banco ya tiene un PySpectrum 3.0 que escribe los offsets al arrancar.**
- Según R2-2, la PC del laboratorio corre el commit `7f5d10a` (2026-09-09). Verifiqué con git que el commit `0ebd7c6`, que introdujo la escritura automática, es **ancestro** de `7f5d10a`.
- En esa versión, `git show 7f5d10a:pyspectrum/modules/calibration_dock.py` ya hace `load_calibration_from_txt` en el constructor (l. 526) y escribe los offsets de red y el cero de rendija (l. 800-802).
- El lanzador de esa versión tiene activa la tarjeta "Iniciar PySpectrum 3.0" (`git show 7f5d10a:main.py`, l. 375-384).
- "PySpectrum 3.0 no fue probado" (§6) **no equivale** a "nunca se abrió en la PC del banco". Si alguien lo abrió una sola vez en modo laboratorio con el Shamrock encendido, el equipo puede tener hoy 12 / −35 / 0, detector = 5 y **cero de rendija = 0**.
- Además, el valor del investigador para la red de 150 l/mm cambió de 87 (R2-9) a 85 (R4-3) en un día. Eso es compatible con un valor recordado o tomado de distintas fuentes, no con una lectura del equipo.
- **Consecuencia:** no hay un "valor actual" confiable hasta leer el equipo (BANCO-25) y compararlo con lo que dice el investigador. Si la lectura da 12 / −35 / 5, la corrupción ya ocurrió y el plan necesita un paso de recuperación que hoy no tiene.

**0.2. ¿Con qué código se prueba el bloque A en el banco?**
- R2-2 fija una regla: no desplegar `main` en la PC del laboratorio hasta corregir C-01 y pasar el Grupo E.
- El bloque A se va a escribir sobre `main`. Y el punto 6 del plan es PyPrinting como ventana satélite **del mismo proceso**, o sea, el PyPrinting de `main`, **con C-01**.
- El plan no dice cómo se sale de esa contradicción: ¿una rama sobre `7f5d10a`, una carpeta separada, o PySpectrum sin satélite durante el bloque A? Sin esa decisión, la primera prueba de banco del bloque A viola R2-2 o se hace con otro código.

---

## 1. Supuestos no declarados

### Los tres más peligrosos

**S1. "Leer al arrancar no cambia nada y los getters son inocuos."** Es falso en cuatro puntos, todos [código]:
1. **Un getter corrompe memoria.**
   - `CalibrationBackend.read_initial_values` (`calibration_dock.py:680-710`) empieza por `ShamrockGetSlit(DEVICE, INPUT_SLIT_PORT)` (`:683`). El driver pasa tres argumentos a una función que recibe dos (`shamrock_driver.py:488-494`, C-06), así que la DLL escribe en la dirección 0x1: una violación de acceso *dentro* de `ShamrockCIF.dll`.
   - El `try` de `:709-710` la atrapa, pero **antes** de leer los offsets. Lo que la pestaña muestra como offsets "del equipo" son los del archivo inventado.
   - Tampoco sabemos en qué estado interno queda la DLL después de esa violación [inferencia].
2. **Una lectura fallida se muestra como si fuera buena, aun con C-06 corregido.** Si `GetGratingOffset` o `GetDetectorOffset` fallan, `:701` y `:706` emiten el valor anterior (el del archivo o el valor por defecto) sin marcarlo. No hay procedencia por valor: "leído del equipo", "del archivo" y "falló la lectura" se ven igual.
3. **Consultar el estado reinicia el hardware.**
   - Abrir *Herramientas → Tablero de Hardware* llama a `rescan_hardware()` desde el constructor del tablero (`modules/hardware_dashboard.py:95`). Eso termina en `connect_device`, que ejecuta `get_shamrock(reset=True)` y `get_andor_ccd(reset=True)` (`core/hardware_manager.py:223, 247`).
   - Resultado: `ShamrockClose` y reinicialización, más `ShutDown` y `Initialize` de la cámara.
   - Como `initialize()` fija `SetCoolerMode(0)` (`andor_ccd_driver.py:400`), el `ShutDown` apaga el enfriador. Según [SDK] (`SetCoolerMode`), el modo 0 significa que la cámara "vuelve a ambiente al cerrar".
   - La ventana y **todos** los backends conservan la instancia vieja, ya cerrada (`window.py:471-472` la reparte a cada `Backend`). Desde ese momento cada llamada devuelve `DRV_NOT_INITIALIZED` o un cuadro de ceros, mientras el tablero dice "conectada".
4. **`Initialize` es en sí una escritura de estado.**
   - [SDK], notas de versión: tras `Initialize`, "cameras now default to fastest readout speed", "EM gain set to off" y "non-Frame Transfer mode" por defecto.
   - "Leer al arrancar" lee valores por defecto del SDK, no el estado que dejó el legado.

**S2. "Lo que muestra la GUI es lo que tiene la cámara."** No lo es:
- `_read_mode = READ_MODE_IMAGE` (`andor_ccd_driver.py:359`) es una creencia: nadie llama a `SetReadMode` al arrancar.
- **Nadie llama a `SetAcquisitionMode` en todo `pyspectrum/` ni en `core/`** (grep). El modo queda en el que tenga el SDK por defecto; [SDK] no documenta cuál es (BANCO-03, T1).
- El botón muestra "❄️ Enfriador: ON" marcado desde la construcción (`left_hardware_panel.py:103-106`), pero `initialize()` no enciende el enfriador (`andor_ccd_driver.py:392-409`).
- La etiqueta de temperatura dice "Enfriando…" para cualquier estado distinto de *STABILIZED*, incluido `DRV_TEMP_OFF` (`left_hardware_panel.py:331-337`).
- `is_hardware_alive()` no incluye `DRV_TEMP_OFF` entre sus estados válidos (`andor_ccd_driver.py:370-371`). Con el enfriador apagado, que es el estado de todo primer arranque, el tablero reporta que la cámara falla.
- El combo de red muestra 150 l/mm al arrancar, cualquiera sea la red montada. Nunca se sincroniza con el hardware (`left_hardware_panel.py:171-174`; `_refresh_status`, `:331-343`, actualiza el contexto pero no el combo).
- Lo mismo pasa con los combos de puertos (Fibra / Cámara), aunque el puerto real es *Side* (R2-11).
- **Contraste con el legado:** fijaba un estado base conocido al arrancar. Temperatura 10 °C y ventilador "low" (`PySpectrum_UNSAM.py:785`); Image 1002 × 1002, preamp 0, EM 0, VS 2, *frame transfer* activado, obturador cerrado y exposición de 1 s (`Camera_ps.py:566-651`); obturador del Shamrock abierto (`PySpectrum_UNSAM.py:793`); puertos Side/Direct y red 150 (`Spectrum_ps.py:157-166`).

**S3. "El offset es un número portable y hay uno por red."** Cuatro grietas:
1. **Geometría.** El legado declara `NumberofPixel = 1002` y `PixelWidth = 8` (`Instrument_Shamrock_ps.py:23-24`) y lee 1002 columnas (`Camera_ps.py:40, 570`). 3.0 declara 1004. El "85" se calibró con la geometría del legado; aplicado a la de 3.0, se esperan ≈ 0.10 nm de corrimiento con la red de 150 l/mm, que es la hipótesis de BANCO-14. **El 85 se revalida, no se copia.**
2. **Identificabilidad del offset del detector** [inferencia; hace falta el manual del Shamrock].
   - Si el offset de red y el del detector son los dos pasos del mismo motor de la torreta, en cada red sólo se observa su suma.
   - Con una línea por red hay tres incógnitas (detector, red 1, red 2) y dos datos. El offset del detector es **no identificable** salvo por convención: por ejemplo, fijarlo con el orden cero del espejo y dejar las redes para la línea conocida.
   - Si es así, "idear un protocolo para calibrar el offset del detector" (R4-3) es un problema mal planteado mientras no se fije esa convención.
3. **Mapeo índice → red.** El código asume 1 = 150, 2 = 1200 y 3 = espejo (`shamrock_driver.py:21-23`). El legado dice lo mismo (`Instrument_Shamrock_ps.py:12-14`), y [P25] confirma que la torreta tiene esas tres piezas (`lab-invariants` fila 125), **pero no en qué orden van**. Se verifica con `ShamrockGetNumberGratings` y `ShamrockGetGratingInfo`, que sólo leen.
4. **El plan olvida el cero de rendija.** El arranque también escribe `ShamrockSetSlitZeroPosition(…, 0)` (`calibration_dock.py:1015`). Según el docstring de Andor, el rango admitido es −200 a 0 (`Shamrock_ps.py:2672`), así que 0 es un extremo. Si el valor de fábrica era negativo, cada arranque de 3.0 descalibra el ancho real de la rendija, y eso afecta la resolución, el flujo y el `slit_fwhm`. **El punto 1 del plan nombra 12 / −35 / 0 y el detector 5, pero no esto.**

### Otros supuestos

**S4. Persistencia de los offsets** [inferencia]. No sabemos si `ShamrockSet*Offset` escribe en la EEPROM o en la RAM del SDK:
- **Si escribe en la EEPROM,** una escritura equivocada es permanente hasta recalibrar, y el punto 0.1 se vuelve grave.
- **Si escribe en la RAM,** "nunca escribir" significa que en cada sesión rige el valor de la EEPROM, no el de la calibración del investigador.
- La casilla del legado arranca en '100' (`Spectrum_ps.py:66`) y nadie la retipeaba en cada sesión. Eso sugiere persistencia, pero no la prueba.

**S5. Orden y acoplamiento de inicialización.**
- 3.0 inicializa la Andor antes que el Shamrock (`window.py:471-472`), igual que el legado (`PySpectrum_UNSAM.py:785-791`). Eso está bien.
- Pero los caminos de reset (S1.3) reinicializan cada equipo por separado.
- Según el docstring de Andor, `ShamrockInitialize` recibe la ruta al DETECTOR.ini de la cámara (`Shamrock_ps.py:1790`). Si el Shamrock se comunica **a través de la cámara** (cable I2C) y no por USB propio, un `ShutDown` de la cámara lo deja sin comunicación [inferencia].
- El legado forzaba al arrancar el obturador del Shamrock y los puertos; 3.0 hereda lo que haya quedado de Solis o de un cierre forzado.

**S6. "El mismo proceso no duplica sesiones ni pisa estado."** Pisa estado [código]:
1. `app.Backend.__init__` cambia el perfil **global** a `"pyprinting"` (`app.py:429`). Desde ese momento, un reescaneo del tablero marca la Andor y el Shamrock como "desconectados por perfil".
2. Cerrar la ventana de PyPrinting ejecuta `close_all`:
   - `close_all_tasks()` (`app.py:599`; `core/nidaq.py:814-827`) cierra las tareas DAQmx compartidas;
   - `flipper_notch532("down")` (`:600`) pulsa el espejo de detección si el estado en memoria dice *up*;
   - `pi.disconnect()` (`:601`) **desconecta la platina que usa PySpectrum**. DEC-036 prohíbe la reconexión automática, así que las rutinas de PySpectrum que mueven la platina quedan sin ella.
3. **Probable cuelgue al cerrar** [inferencia, alta confianza]. `closeEvent` de PySpectrum primero detiene los hilos del satélite (`window.py:807-814`) y después cierra la ventana (`:816`). Eso dispara `close_all`, que hace `invokeMethod(cameraWorker, BlockingQueuedConnection)` (`app.py:596`) sobre un objeto cuyo hilo ya terminó: la llamada no vuelve nunca. Si se cuelga ahí, el `close_all_shutters()` final (`window.py:818`) no se ejecuta.
4. **El watchdog es compartido.** El latido de una aplicación enmascara una rutina colgada de la otra, cosa que el diseño de R2-8 tendrá que contemplar.
- **Lo que sí está bien:** no hay duplicación de sesión de la Andor, porque PyPrinting no la usa (su cámara es otra) y el driver es un singleton del proceso.

**S7. "Las exposiciones llegan a 10 s."** Nada lo impone:
- en Step & Glue la exposición es un `QLineEdit` libre, sin rango (`step_and_glue.py:105, 255, 266`);
- en el panel izquierdo va de 0.0001 a 60 s (`left_hardware_panel.py:143`);
- en luminiscencia, crecimiento y dímeros llega a 60 s (TRIAGE C-29).
- Con el latido explícito de 30 s (`step_and_glue.py:423, 428`), una exposición de 40 s tipeada a mano corta la rutina, contra §10.

**S8. "Esperar el cuadro" es sólo agregar una espera.** No alcanza [código]:
- **Stop y E-STOP quedan muertos.** El backend de Step & Glue vive en el hilo de la GUI: se crea en `window.py:605` y nunca pasa por `moveToThread`. Con esperas reales de hasta 10 s por ventana, el `stop_measurement` de `step_and_glue.py:394-397` y el botón E-STOP no se procesan hasta el final del barrido. Hoy no se nota sólo porque el bucle no espera nada.
- **`get_status()` no sirve para saber si terminó.** Devuelve `DRV_IDLE` ante cualquier falla (`andor_ccd_driver.py:602-610`). Un bucle "esperar hasta IDLE" terminaría enseguida si falla la consulta.
- **La espera tiene que tener un límite.** [SDK] `WaitForAcquisition` duerme hasta el evento; para salir hace falta `CancelWait` o `AbortAcquisition`. El tiempo real hay que sacarlo de `GetAcquisitionTimings` ([SDK]: "the actual times used"), no de la exposición pedida.

**S9. "Hay tres caminos al orden cero."** Hay por lo menos cinco. La protección de `spectrum_control.py:230` sólo se activa con λ ≤ 0.05 nm, pero el orden cero entra al chip siempre que |λc| < W/2:
- **Derivación:** `GetCalibration` cubre λc ± W/2. Con W = 12.83 nm/mm × 8.032 mm = 103 nm (red de 150) y 1.44 × 8.032 = 11.6 nm (red de 1200), valores de `lab-invariants` filas 119-120, el umbral real es ≈ 52 nm con la red de 150 y ≈ 5.8 nm con la de 1200.
- **Caminos sin protección:**
  1. el campo λ del panel izquierdo (0-2000 nm, `left_hardware_panel.py:207, 320-322`);
  2. **el combo de red con el espejo**, sin salvaguarda (`left_hardware_panel.py:310-312`, a diferencia de `spectrum_control.py:221`);
  3. el **inicio del barrido de Step & Glue**, sin rango (`step_and_glue.py:263`);
  4. `calibration_dock.py:713-718`;
  5. el panel oculto, con el umbral equivocado.

**S10. "Calibrar con el láser de 532 nm es suficiente."**
- Una sola línea en el centro del detector **no detecta** una inversión del eje ni un error de dispersión, porque cae en el centro en cualquier caso.
- **Con la red de 1200 l/mm,** 1 píxel = 0.012 nm: hay que conocer la λ verdadera del láser mejor que eso. No está verificado que el 532 esté especificado a ±0.01 nm [inferencia: la especificación típica de un DPSS es mucho más holgada].
- **Si hay un filtro de borde o notch en el camino,** puede recortar un ala de la línea y correr el centroide.
- Para el eje absoluto con la red de 1200 hace falta una lámpara de líneas (BANCO-06). El láser sirve para el corrimiento Raman, que es relativo a él.

---

## 2. Modos de falla del primer arranque que el plan no cubre

| # | Escenario concreto | Qué ve el operador | Qué pasa en el equipo |
|---|---|---|---|
| F1 | **Solis (o el legado) quedó abierto**, justamente para leer los offsets antes del primer arranque (Q8 / BANCO-25). `Initialize` falla porque la cámara admite un solo proceso (BANCO-03). | PySpectrum arranca "normal", con espectros **simulados**. `get_andor_ccd` cae **en silencio** al mock (`andor_ccd_driver.py:749`) y `get_shamrock` también (`shamrock_driver.py:786`). Viola la regla "sin mock silencioso en producción". | Nada, o una mezcla peor: Shamrock real con Andor simulada. El operador puede "calibrar" una línea sintética y, con el botón nuevo, escribir el offset resultante en el Shamrock real. |
| F2 | La DLL empaquetada (`pyspectrum/drivers/libs/atmcd64d.dll`, 2021) no coincide con el driver del sistema. | Lo mismo que F1: mock silencioso. | — |
| F3 | Primer arranque con el cabezal a temperatura ambiente. | "Enfriador: ON" y "🟡 Enfriando…" para siempre; el tablero, si se abre, dice que la cámara falla (S2). | El enfriador está apagado. El Raman de 10 s se toma a ≈ 20 °C: la corriente oscura invalida los datos sin ningún aviso. |
| F4 | **Cuadro viejo con aspecto válido.** Step & Glue actual: `abort_acquisition()` (`step_and_glue.py:567`), mueve la red y lee `get_1d_spectrum()` (`:583`) sin `StartAcquisition`. El driver cae a `GetAcquiredData` (`andor_ccd_driver.py:579-597`). | Un espectro cosido suave y creíble. | Cada ventana es **el mismo** último cuadro del Live, rotulado con otro eje λ. No son ceros, así que la regla "nunca un cuadro de ceros" **no lo detecta**. Tras el arreglo del punto 4, hay que probar explícitamente que ventanas consecutivas son cuadros distintos. |
| F5 | **Obturador del Shamrock cerrado por la pausa del Live.** Step & Glue pide la sesión con `auto_pause_live=True`; eso llama a `pause_camera_live` → `stop_live` → `ShamrockSetShutter(DEVICE, 0)` (`exploration_tab.py:98-105`), y Step & Glue nunca lo reabre (grep). | Una vez corregido el punto 4, todas las ventanas salen oscuras. El operador sube la ganancia o la exposición. | Al volver a abrir (Live), satura. |
| F6 | **Efecto colateral del arreglo de C-05.** `step_and_glue.py:505` compara con el literal `in (0, 1)`, y `config.py:109` dice "1: Single Track". | Con Single-Track = 3, el camino "espectro único" lo trata como 2D. | Pide un búfer de 1004 × 1002 en Single-Track y [SDK] `GetMostRecentImage` lo rechaza ("the array must be exactly the same size"). Con Multi-Track = 1, lo trata como 1D. |
| F7 | **Unidades de la ganancia EM.** El driver acota a 0-1000 (`andor_ccd_driver.py:474`), pero [SDK] `SetEMGainMode`: el modo por defecto es 0, "DAC 0-255". | Tipea 300: el SDK lo rechaza y el panel no mira el código de retorno (`left_hardware_panel.py:274-275`), así que la GUI muestra 300. La salvaguarda "5x" en realidad es DAC 5. | La ganancia real no es la que se cree. En el diálogo de orden cero, si `get_emccd_gain` falla devuelve 0 y el diálogo pinta 🟢 "segura" (`zero_order_dialog.py:23-29`). |
| F8 | Se elige "Espejo" en el combo del panel izquierdo. | Ningún diálogo. | Reflexión especular sobre el detector con la ganancia EM que haya: el camino número 5 de S9. |
| F9 | Se abre el tablero "para ver si todo está conectado". | Todo "conectado" en verde. | La Andor y el Shamrock quedaron reiniciados; los backends tienen instancias muertas; el enfriador se apagó (S1.3). |
| F10 | `read_initial_values` provoca la violación de acceso en la DLL del Shamrock (S1.1). | Los offsets del archivo, presentados como leídos. | Estado interno de la DLL desconocido: las llamadas siguientes pueden fallar o colgarse [inferencia]. |
| F11 | Se cierra PySpectrum con PyPrinting satélite abierto (S6.3). | La aplicación queda colgada al cerrar. | `close_all_shutters()` final no se ejecuta. Además, `closeEvent` nunca llama a `ShutDown` de la cámara ni a `ShamrockClose` (`window.py:770-822`), así que el arranque siguiente puede encontrar la cámara tomada y volver a F1 [inferencia]. |

---

## 3. Dónde el plan confía en documentación o comentarios que pueden estar mal

| Afirmación en la que se apoya el plan o el código | Dónde | Estado | Fuente primaria que la decide |
|---|---|---|---|
| Los offsets se guardan en el equipo (persistencia) | implícito en el punto 1 | sin fuente | Manual del SDK del **Shamrock** (no está en `docs/bibliografia/`; viene con la instalación de Andor SDK/Solis). En el banco: escribir el mismo valor + 1 en la red nunca calibrada, cerrar, reinicializar y releer; después restaurar. Requiere aprobación. |
| Offset del detector y de red: unidades, signo y si se suman | R4-3 ("idear protocolo") | sin fuente | Manual del SDK del Shamrock, y la pantalla de calibración de Solis |
| 85 / 0 / 0 son los valores del equipo | R4-3; `lab-invariants` fila 128 (📄) | EXPERIMENTAL, cambió 87 → 85 en un día | Lectura del equipo (BANCO-25) con Solis **y** con el legado; los dos tienen que coincidir |
| Índice 1 = 150, 2 = 1200, 3 = espejo | `shamrock_driver.py:21-23`, `NAME_GRATINGS` | legado coincidente; [P25] da las piezas, no el orden | `ShamrockGetGratingInfo(1..3)` (líneas/mm, blaze), sólo lectura |
| Cero de rendija = 0 | `pyspectrum_calibration_last.txt`, `slit_zero_position_steps = 0` | inventado (archivo de `0ebd7c6`) | `ShamrockGetSlitZeroPosition` leído **antes** de cualquier arranque de 3.0 corregido; valor de fábrica, si Andor lo documenta |
| `ShamrockSetSlit(device, width)` corrige C-06 | punto 2 del plan | ambiguo: "Input Slit" de 2 argumentos frente a `SetAutoSlitWidth(dev, 1 = INPUT_SLIT_SIDE, w)` del legado (`Spectrum_ps.py:204-207`; `Shamrock_ps.py:2016-2031`) | Manual del SDK del Shamrock; en el banco, `ShamrockGetAutoSlitWidth(1)` después de escribir |
| El polinomio cúbico es "de fábrica, EEPROM", y p = 0..N−1 | `shamrock_driver.py:633, 754-762`; `config.py:110` | sin fuente; la base del índice (0 o 1) decide 1 px | Manual del Shamrock. En el banco, sólo lectura: comparar `GetCalibration` con el eje cúbico en la misma posición; la diferencia debe ser < 0.1 px |
| La red y λ se asientan en 4 s / 0.3 s | `shamrock_driver.py:25-28` | temporizador de software, no medición (`lab-invariants` fila 126) | BANCO-08; o el manual, si `SetWavelength` bloquea |
| Modo de lectura: 1 = Single-Track | `andor_ccd_driver.py:36-40`, `config.py:109` | **refutado** por [SDK] `SetReadMode` (1 = Multi-Track, 3 = Single-Track) | ya decidido |
| Amplificador "convencional" disponible | `left_hardware_panel.py:108-113`, `andor_ccd_driver.py:458-467` | [DS] sólo lista lectura por el amplificador EMCCD a 35/27/13 MHz, lo que respalda D-18 | En el banco, `GetNumberAmp` (sólo lectura) |
| El iXon tiene obturador interno | `set_shutter_mode`, cuadros oscuros | [DS]: el obturador es **opcional** ("0: No shutter") | Placa del cabezal, o `GetCapabilities`/`IsInternalMechanicalShutter` |
| "RealGain no soportado en nuestro iXon+ 885" | comentario del legado, `Camera_ps.py:588` | [DS] dice "1-1000x via RealGain": contradicción | `GetEMGainRange` después de `SetEMGainMode(3)`, en el banco |
| La copia local del legado describe el banco | todo el plan | memoria del proyecto: su cableado DAQ está desactualizado; sus constantes del Shamrock (1002 px, `INPUT_SLIT_PORT = 1`) podrían estarlo también | La copia del legado que corre en la PC del banco |
| El SDK es la v2.104 | nota del orquestador | la DLL empaquetada es de 2021-08-31; el manual es de 2023 | Versión de `atmcd64d.dll` y `ShamrockCIF.dll` en la PC del banco (propiedades del archivo, o `GetVersionInfo`) |

---

## 4. Qué falsaría "PySpectrum 3.0 está listo para el banco" en el bloque A

**Precondición para todas las pruebas:** un registro de llamadas. El driver o el mock escriben **cada** llamada `Set*` / `Goto*` / `Initialize` / `ShutDown` a un log con marca de tiempo. Sin eso, "no escribe al arrancar" no se puede verificar, sólo creer.

### Fase 0 — sin luz, sin láser
Láseres apagados con su llave, lámpara apagada, Solis y legado cerrados.

| Prueba | Cómo se hace | Qué resultado la hace fallar |
|---|---|---|
| **P0 — Respaldo** | Antes de tocar 3.0, leer con el legado o con Solis (BANCO-25) los offsets de las tres posiciones de la torreta, el del detector, los ceros de rendija, la red montada y `GetGratingInfo`. | Si da 12 / −35 / 0 / 5, **se detiene el bloque**: la corrupción del punto 0.1 ya ocurrió. |
| **P1 — Arranque sin escrituras** | Arrancar 3.0 corregido. | Aparece en el log alguna `ShamrockSet{Grating,Detector}Offset`, `SetSlitZeroPosition`, `SetGrating` o `SetWavelength`; o los valores que muestra 3.0 difieren **en algo** de P0; o algún valor mostrado no dice "leído del equipo" o "falló la lectura". |
| **P2 — Negativa al mock** | Arrancar 3.0 con Solis abierto. | Aparece un espectro o un cuadro. El resultado correcto es "Andor no conectada", con las adquisiciones bloqueadas. |
| **P3 — La GUI coincide con el hardware** | Después del arranque, releer: `IsCoolerOn`, estado de `GetTemperature`, modo de lectura y de adquisición, velocidades HS y VS, preamp, `GetEMCCDGain`, `GetEMGainMode`, `GetNumberAmp`, `GetAcquisitionTimings`. | Algún indicador de la GUI contradice la relectura, por ejemplo "Enfriador: ON" con `IsCoolerOn = 0`. |
| **P4 — Cuadro oscuro real y nuevo** | Obturador cerrado, exposición mínima, 1D y 2D, dos adquisiciones seguidas. | Mínimo = 0 (debe verse el *bias*, BANCO-10); o **los dos cuadros son idénticos bit a bit**, es decir, un cuadro viejo (F4). |
| **P5 — Stop y E-STOP bajo espera** | Step & Glue con 10 s por ventana; pulsar Stop a los 2 s y, en otra corrida, E-STOP. | La GUI no responde, o el aborto tarda más de ~1 s más la lectura en curso, o la rutina sigue a la ventana siguiente. |
| **P6 — Un solo camino al orden cero** | Probar λc = 30 nm con la red de 150; elegir "Espejo" en el panel; Step & Glue desde 0 nm; `Ctrl+0`. | Alguno llega al hardware (el log lo muestra) sin pasar por la salvaguarda. |
| **P7 — Consultar no reinicia** | Abrir el tablero de hardware con la sesión en reposo y después adquirir. | Aparece `DRV_NOT_INITIALIZED`, cambian los parámetros o la temperatura sube. |

### Fase 1 — lámpara, sin láser

| Prueba | Cómo se hace | Qué resultado la hace fallar |
|---|---|---|
| **P8 — "Línea que camina"** (la prueba de mayor rendimiento) | Una línea conocida (lámpara Hg-Ar o Ne). Para cada red, poner λc en λ₀ − 0.35 W, λ₀ y λ₀ + 0.35 W. Con una sola línea prueba a la vez el signo del eje, la dispersión y el offset, y en los tres puntos (centro y bordes). | La línea no aparece en la misma λ, dentro de 1 px, en las tres posiciones. En la misma prueba, sólo leyendo: `GetCalibration` frente al eje cúbico difieren en más de 0.1 px. |
| **P9 — Step & Glue con halógena** | BANCO-07, más una huella (*hash*) de cada ventana y la marca de tiempo de cada adquisición. | Hay dos ventanas con la misma huella; o el intervalo entre ventanas es menor que la exposición más la lectura; o aparecen huecos de cobertura. |
| **P10 — Obturador del espectrógrafo** | BANCO-09, más una segunda corrida con el Live previo encendido. | Step & Glue sale oscuro después de la pausa del Live (F5). |

### Fase 2 — láser de 532 nm a baja potencia
Filtro de densidad en baja potencia, ganancia EM 0, con aprobación.

| Prueba | Cómo se hace | Qué resultado la hace fallar |
|---|---|---|
| **P11 — Calibración en seco** | Calcular el offset que propondría el ajuste gaussiano **sin escribirlo**, y compararlo con el valor leído en P0. | Con 85 leído y la geometría de 1004 px, la línea queda a más de 1 px de 532.0 nm. Antes de culpar al offset, descartar la geometría 1002/1004 (BANCO-14), la base del índice del polinomio y la λ real del láser. |
| **P12 — Escritura explícita** | Una sola, en la red de 1200 l/mm, con relectura; después reinicializar y releer (persistencia); después restaurar. | La relectura difiere de lo escrito, o el valor no sobrevive a la reinicialización, lo que obliga a rediseñar el punto 1. |
| **P13 — Watchdog** | Raman de 10 s con el obturador abierto, en varias ventanas seguidas. | El watchdog cierra en medio de una exposición; o el log no muestra la renovación del latido en cada ventana; o el obturador no se cierra al terminar. |

### Explicaciones simples que hay que descartar antes que las "físicas"
- **Línea corrida ~1 px:** la geometría 1002/1004, la base del índice del polinomio, la λ real del láser o un filtro de borde. Todo eso antes que un "offset mal calibrado".
- **Espectro oscuro:** el obturador del Shamrock (F5), el espejo de `line7` arriba (R2-4) o la polaridad del TTL de la cámara (en `setup_shutter` el legado usa `ttl_mode` 0 para cerrar y 1 para abrir, `Camera_ps.py:645, 657`; 3.0 usa siempre `typ = 1`). Todo eso antes que la alineación.
- **Live congelado:** el modo *single scan* por defecto (BANCO-03, T1), antes que el USB.
- **"La cámara falla" en el tablero:** `DRV_TEMP_OFF` o `DRV_ACQUIRING` durante una exposición (según [SDK], `GetTemperature` devuelve `DRV_ACQUIRING`), antes que un desenchufe.

---

## 5. Contraargumentos serios al plan

**C1. "Nunca escribir los offsets al arrancar" está bien, pero "al arrancar sólo leer" es demasiado absoluto.**
- Hay que separar dos clases de estado:
  - **Constantes de calibración persistentes** (offsets, cero de rendija): nunca se escriben automáticamente.
  - **Estado operativo reversible**: modo de adquisición, modo de lectura, VS, ventilador, *frame transfer*, ganancia EM = 0, obturador de la cámara, puertos Side/Direct y obturador del Shamrock. Éste **debe** fijarse al arrancar en una línea base declarada, con relectura, como hacía el legado.
- Si sólo se lee, se heredan los valores por defecto del SDK o lo que dejó Solis, y la GUI muestra algo que no es cierto (S2). Por lo mismo, la geometría (`configure_detector_geometry`) ya es una escritura al arrancar necesaria: el principio "sólo leer" no se puede cumplir tal como está escrito.

**C2. El diseño tiene que funcionar sea cual sea la persistencia.** Como no sabemos si los offsets viven en la EEPROM o en la RAM (S4), la opción que es correcta en los dos casos es:
1. al arrancar, leer el equipo;
2. compararlo con el archivo de calibración, que registra fecha, método y operador;
3. si coinciden, marcarlo en verde;
4. si difieren, mostrar un aviso con **los dos valores** y tres acciones: *aplicar archivo*, *adoptar el valor del equipo* o *ignorar*.

Y una escritura explícita sólo debería habilitarse si:
- hubo una lectura exitosa del equipo en esta sesión, porque no se puede deshacer lo que nunca se leyó;
- se guardó el valor previo en el archivo, para poder deshacer;
- se relee después de escribir y se rechaza si no coincide con lo escrito (el patrón de DEC-014).

"Escribir sólo con acción explícita" sin estas cuatro condiciones es apenas un botón.

**C3. Un orden cero "protegido" que cierra todos los obturadores es inútil para lo que se usa.**
- El orden cero sirve para ver la imagen de la rendija o del láser atenuado y centrar el píxel de la ranura (`auto_calibrate_slit`), y es la convención natural para el offset del detector (S3.2). **Necesita luz.**
- Si el camino único siempre cierra los láseres, el operador se va a acostumbrar a "Override experto" (`zero_order_dialog.py:150-157`) y la protección se vuelve un clic.
- La protección debería actuar **del lado del detector**: forzar ganancia EM 0 con relectura, exposición mínima y filtro de densidad en baja potencia (`ao0`). La luz se deja entrar.
- Además, el peligro debería definirse como "la ventana contiene λ = 0" y no "λ ≤ 0.05 nm", e incluir el espejo y el Step & Glue (S9).

**C4. "Corregir las firmas de la rendija" puede corregirla hacia la función equivocada.**
- El legado, que funcionaba, usaba `ShamrockSetAutoSlitWidth(dev, 1, w)`, con índice 1 = entrada lateral según el docstring de Andor.
- La `ShamrockSetSlit(device, width)` de dos argumentos dice "Input Slit", sin puerto, y la entrada que se usa es la lateral (R2-11).
- Sin el manual del Shamrock, **hay que copiar el legado**, no la firma de dos argumentos.

**C5. "Un latido por ventana" no alcanza por sí solo.** Hacen falta además:
- una espera acotada (con `GetAcquisitionTimings`, más la lectura y un margen), con `CancelWait` y `AbortAcquisition` al pulsar Stop;
- sacar el Step & Glue del hilo de la GUI, o Stop y E-STOP mueren (S8);
- un tope de exposición en la GUI que sea compatible con el plazo del watchdog (S7).

En la práctica, el punto 4 del plan es un cambio de topología de hilos, no un parche del bucle.

**C6. "Dejar de devolver ceros" sin decir qué se devuelve a cambio desplaza el problema.**
- Una falla tiene que llegar al llamador como falla, es decir `(código, None)` o una excepción.
- El cosido tiene que tratar una ventana fallida como un **hueco declarado** (los `coverage_gaps` ya existen), no como datos.
- Si no, el primer `try/except` de un llamador vuelve a fabricar un cuadro.

---

## 6. Preguntas para el investigador (máximo 6)

1. **¿Se abrió alguna vez PySpectrum 3.0 en la PC del banco,** aunque sea un momento y aunque no se haya medido, con el Shamrock encendido? Es el commit `7f5d10a`, que ya tiene el botón en el lanzador.
   *Desbloquea:* si los valores del equipo pueden tomarse como respaldo, o si hay que recalibrar offsets y cero de rendija antes que nada (punto 0.1).
2. **¿De dónde sale el 85 (y antes el 87)?** ¿Es una lectura del equipo (Solis o "Get"), un número tipeado en "Set Offsets" del legado, o un registro escrito? ¿Con qué red montada y en qué fecha?
   *Desbloquea:* si el 85 se adopta, se revalida con la geometría de 1004 px (S3.1), o se descarta en favor de la lectura de P0.
3. **¿El Shamrock tiene obturador propio, y el iXon el obturador interno** opcional de la hoja de datos? ¿Hay un cable TTL de la cámara al Shamrock? El legado dice que `setup_shutter` "cierra shutter camera y shamrock".
   *Desbloquea:* el protocolo de cuadro oscuro, el estado del obturador al arrancar (C1) y F5.
4. **¿Para qué y con qué luz se usa el orden cero en la práctica?** Por ejemplo: imagen de la ranura con lámpara, láser atenuado, alineación o centrado del píxel de la ranura.
   *Desbloquea:* si la protección puede cerrar los láseres o sólo debe actuar sobre el detector (C3), y la convención del offset del detector (S3.2).
5. **¿El Shamrock está conectado a la PC por USB propio o a través de la cámara** (cable I2C al cabezal)?
   *Desbloquea:* el orden de inicialización y de reset, y si un reinicio de la cámara deja al Shamrock sin comunicación (S5, F9).
6. **¿Cómo quiere probar el bloque A en el banco,** dado que R2-2 prohíbe desplegar `main` hasta corregir C-01? ¿Una carpeta aparte con PySpectrum sin el satélite PyPrinting, una rama sobre `7f5d10a`, o primero C-01?
   *Desbloquea:* el camino de despliegue, y si durante el bloque A se permite abrir PyPrinting como satélite (punto 0.2, S6).

---

## Resumen

- **Veredicto:** `HIGH_RISK_ASSUMPTIONS`.
- **El estado del equipo puede no ser el que se cree.** La PC del banco ya corre un PySpectrum 3.0 (`7f5d10a`) que escribe 12 / −35 / 0, detector 5 y **cero de rendija 0** en cada arranque, y el lanzador lo ofrece. El "85" cambió de valor en un día. Antes de cualquier arreglo hay que leer el equipo.
- **Leer no es inocuo.** `GetSlit` provoca una violación de acceso antes de que se lean los offsets. Una lectura fallida se muestra como leída. Abrir el tablero de hardware reinicia la cámara y el Shamrock, apaga el enfriador y deja muertos a los backends.
- **La GUI no refleja la cámara.** Nadie fija el modo de adquisición ni el de lectura. Se ve "Enfriador ON" con el enfriador apagado. La ganancia EM está en unidades DAC 0-255 y no en "x".
- **Los offsets son más frágiles de lo que asume el plan.** Dependen de la geometría (1002 frente a 1004 px), el offset del detector puede ser no identificable sin una convención, y el plan olvida el cero de rendija.
- **Faltan modos de falla del arranque.** Con Solis abierto, el programa cae **en silencio** al mock. Step & Glue lee un cuadro viejo con aspecto válido. El Live pausado cierra el obturador del Shamrock. Stop y E-STOP mueren cuando las esperas sean reales.
- **Hay por lo menos cinco caminos al orden cero, no tres.** El peligro existe con |λc| < W/2: ≈ 52 nm con la red de 150 y ≈ 5.8 nm con la de 1200.
- **Mismo proceso:** cerrar PyPrinting desconecta la platina y cambia el perfil global. Cerrar PySpectrum con el satélite abierto probablemente cuelga la aplicación.
- **Contraargumento principal:** hay que forzar al arrancar un estado operativo base con relectura, como el legado, y **nunca** las constantes de calibración. Escribir sólo con lectura previa, respaldo, relectura y resolución de diferencias entre equipo y archivo.
- **Falsación mínima:** un log de llamadas al driver, más P0 a P7 sin luz. La prueba de mayor rendimiento es P8, "la línea que camina": una línea en tres posiciones de λc por red.
- **Hay seis preguntas para el investigador en §6.**

Archivo: `C:\Users\josel\Documents\Obsidian_Vault\printing3\docs\evidence\auditoria_2026-09-27\pyspectrum_A_ronda1\devil_advocate.md`
