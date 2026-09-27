# Pruebas de Banco Pendientes — Verificación en Hardware Real

**Laboratorio**: Nanofotónica — Instituto de Nanosistemas (INS-UNSAM / CONICET)
**Ubicación**: `docs/evidence/PRUEBAS_BANCO_PENDIENTES.md`
**Vinculado a**: `docs/evidence/EVIDENCE_LEDGER.md`, `docs/decisions/DECISION_LOG.md`, [[SYS-301]], [[SYS-303]], [[MOD-06]]
**Última actualización**: 2026-09-26

---

## Para qué es esta lista

Todo lo que PySpectrum 3.0 afirma sobre el hardware y que **ningún test automático puede
comprobar** — porque el simulador sólo reproduce lo que sabemos, no lo que ignoramos — está
acá, con el procedimiento para comprobarlo en el banco y el criterio que decide si pasó.

Cómo usarla:

1. Hacer las pruebas en el orden de los grupos: cada grupo exige menos que el siguiente.
2. Al terminar una, tildarla, completar **Resultado** (fecha, operador, valores medidos) y
   pegar la salida textual si la prueba la produce (las sondas imprimen un bloque `RESUMEN`).
3. **Si una prueba falla, no se corrige nada en el momento**: se anota el resultado y se
   reabre la decisión o el reclamo que figura en **Depende de**. Un resultado de banco que
   contradice al código es evidencia, no un bug a parchear en caliente.

**Seguridad (`CLAUDE.md` §4)**: todas las pruebas las ejecuta el operador. Ninguna requiere
láser. Si se elige la línea del láser o una banda Raman como referencia de longitud de onda,
aplica el protocolo completo de obturadores y watchdog. Las sondas de `tools/bench/` sólo tocan
la cámara Andor: no accionan obturadores, láseres, DAQmx, platina ni espectrógrafo.

> Las dos sondas (`tools/bench/legacy_console_probe.py` y
> `tools/bench/andor_acquisition_mode_probe.py`) están versionadas junto con
> `tools/bench/INSTRUCCIONES.txt`, que explica paso a paso cómo ejecutarlas.

## Resumen

| ID | Verifica | Depende de | Requisitos | Estado |
| :--- | :--- | :--- | :--- | :--- |
| BANCO-01 | Pitch, tamaño y modelo del detector leídos del hardware | `DEC-033`, `SW-003` | Legado abierto (sólo lectura) | ☐ |
| BANCO-02 | Por qué el Live del legado se congelaba | Protocolo de adquisición | Legado abierto (sólo lectura) | ☐ |
| BANCO-03 | Protocolo de adquisición del iXon3 (T0–T4) | `DEC-032`, protocolo de adquisición | Legado y Solis **cerrados**, cámara a temperatura ambiente | ☐ |
| BANCO-04 | El Shamrock acepta y relee la geometría del detector | `DEC-033` | PySpectrum 3.0 en hardware | ☐ |
| BANCO-05 | Ancho real de la ventana espectral por red | `DEC-033` | PySpectrum 3.0 en hardware | ☐ |
| BANCO-06 | Exactitud del eje λ con líneas conocidas | `DEC-033`, `SYS-303` | 3.0 en hardware + lámpara de calibración | ☐ |
| BANCO-07 | Step & Glue sin huecos ni saltos | `DEC-033` | 3.0 en hardware + lámpara halógena | ☐ |
| BANCO-08 | Asentamiento real de la red tras mover λ | `SW-002` | 3.0 en hardware + lámpara de calibración | ☐ |
| BANCO-09 | Obturador del espectrógrafo: existe, actúa y confirma | `DEC-031`, `DEC-034` | 3.0 en hardware | ☐ |
| BANCO-10 | Un cuadro real nunca es todo-ceros | `DEC-032` | 3.0 en hardware | ☐ |
| BANCO-11 | Live Raman rechazado si Exploración ya adquiere | `DEC-032` | 3.0 en hardware | ☐ |
| BANCO-12 | Imagen 2D con ROI: forma y filas correctas | `DEC-030` | 3.0 en hardware | ☐ |
| BANCO-13 | Banda de ranura objetivo en Orden Cero | `DEC-031`, `DEC-033` | 3.0 en hardware | ☐ |
| BANCO-14 | Corrimiento del eje del legado (1002 vs 1004 px) | `SW-004` | Legado y 3.0 + lámpara de calibración | ☐ |
| BANCO-15 | Mapeo línea DAQ ↔ servo de cada obturador y polaridad | `DEC-036` | PyPrinting 3.0, **láseres apagados** | ☐ |
| BANCO-16 | Posición del servo de 532 nm al encender, reiniciar NI y cerrar el programa | `DEC-036` | **Láseres apagados** | ☐ |
| BANCO-17 | Modelo y recorrido real de la platina (qCST, qTMN/qTMX) | `DEC-036` | PyPrinting cerrado; `tools/bench/pi_stage_probe.py` | ☐ |
| BANCO-18 | Aviso de "cierre sin confirmar" ante una falla real de la placa | `DEC-036` | PyPrinting 3.0, **láseres apagados** | ☐ |
| BANCO-19 | Pérdida de comunicación con la platina durante una rutina | `DEC-036` | PyPrinting 3.0, **láseres apagados** | ☐ |

---

## Grupo A — Con el PySpectrum legado abierto (sólo lectura; se puede hacer ya)

La sonda se ejecuta dentro del proceso legado, desde su consola (menú Console Widget), con:

```python
exec(open(r"C:\Users\josel\Documents\Obsidian_Vault\printing3\tools\bench\legacy_console_probe.py", encoding="utf-8").read())
```

No llama a nada que modifique la cámara: sólo getters de pylablib y funciones `Get*` del SDK.

### ☐ BANCO-01 — Geometría del detector leída del hardware
- **Verifica**: que el detector es el que `DEC-033` estableció con hojas de datos.
- **Procedimiento**: correr la sonda; leer las líneas `C.pixel_size`, `C.detector_size` y `C.sdk`.
- **Aceptación**: `GetPixelSize = 8.00 x 8.00 um`, `GetDetector = 1004x1002`,
  `GetHeadModel = 'DU8285_VP'`.
- **Si falla**: reabrir `DEC-033` y `SW-003`. El valor vive en un solo lugar
  (`andor_ccd_driver.DETECTOR_PIXEL_PITCH_UM`) y los tests usan las hojas de datos como oráculo,
  así que fallarían a propósito hasta revisar esas fuentes.
- **Resultado**: fecha — / operador — / valores —

### ☐ BANCO-02 — Por qué el Live del legado se congelaba
- **Verifica**: la hipótesis de que "REC Liveview Kinetics" (Step & Glue) deja la cámara en modo
  cinético y ninguna restauración posterior funciona, porque `set_acquisition_mode = '...'`
  tapa el método de pylablib en vez de llamarlo.
- **Procedimiento**: correr la sonda (secciones A y B). Con el Live del legado encendido,
  ejecutar además `observar_live()`. Idealmente repetir antes y después de usar REC Liveview
  Kinetics.
- **Aceptación de la hipótesis**: A dice `TAPADO`; B dice `kinetic` después de haber usado
  REC Liveview Kinetics; `observar_live()` dice `NO AVANZA` en ese estado.
- **Si no se confirma**: la causa del Live congelado es otra. Anotarlo antes de diseñar la
  Ronda 2 del protocolo de adquisición.
- **Resultado**: —

---

## Grupo B — Con el legado y Solis CERRADOS, cámara a temperatura ambiente

### ☐ BANCO-03 — Protocolo de adquisición del iXon3 (sonda T0–T4)
- **Verifica**: cuatro supuestos de los que depende el rediseño pendiente del protocolo de
  adquisición y la premisa de `DEC-032` sobre el orden de arranque.
- **Requisitos**: cerrar el PySpectrum legado, Solis y PySpectrum 3.0 (la cámara admite un solo
  proceso). Enfriador apagado: la sonda se niega a seguir por debajo de −20 °C.
- **Procedimiento**: `python tools\bench\andor_acquisition_mode_probe.py` (o con la ruta de la DLL
  como argumento). Hace `Initialize`, exposiciones cortas y `AbortAcquisition` + `ShutDown` en
  `finally`.
- **Lectura del resultado**:

  | Prueba | Pregunta | Qué cambia según la respuesta |
  | :--- | :--- | :--- |
  | T0 | Modelo, tamaño y pitch | Contraste independiente de BANCO-01 |
  | T1 | Modo por defecto tras `Initialize` (nadie en 3.0 lo fija) | Si es *single scan*, el Live de 3.0 mostraría un único cuadro |
  | T2 | ¿La exposición arranca en `StartAcquisition()` o al leer? | Si arranca en `StartAcquisition`, el primer cuadro de Live integra en parte con el obturador cerrado: `DEC-032` se basó en que no |
  | T3 | ¿Releer el buffer devuelve el cuadro viejo o `NO_NEW_DATA`? | Riesgo de datos viejos con aspecto válido en `acquire_single()` |
  | T4 | ¿Funcionan *Run Till Abort* y *Single* + `WaitForAcquisition`? | Base técnica del rediseño |
- **Resultado**: pegar el bloque `RESUMEN`.

---

## Grupo C — PySpectrum 3.0 contra el hardware real (sin láser)

> ⛔ **BLOQUEADO — no ejecutar PySpectrum 3.0 contra el hardware real hasta corregir estos
> defectos** (auditoría documental del 2026-09-27, verificados contra el código, el SDK y la DLL):
>
> 1. **Escritura de offsets al arrancar.** El dock de calibración carga
>    `pyspectrum/calibration/pyspectrum_calibration_last.txt` al iniciar y escribe sus valores en el
>    Shamrock (`ShamrockSetGratingOffset`, `ShamrockSetDetectorOffset`,
>    `ShamrockSetSlitZeroPosition`; `calibration_dock.py:634` → `1010-1017`). Ese archivo es un
>    ejemplo ilustrativo (red 1 = 12, red 2 = −35, detector = 5 pasos): el primer arranque
>    **reemplazaría los offsets de fábrica del espectrógrafo**, que viven en el equipo y afectan
>    también a Solis y al legado.
> 2. **Ranura motorizada.** El driver llama a `ShamrockSetSlit` con 3 argumentos; el SDK la define
>    con 2 (`device, width`). La DLL leería el ancho de un registro que el código no carga: la
>    ranura se movería a un ancho indeterminado, y el recorte a 10–2500 µm no tendría efecto.
>    `ShamrockGetSlit` tiene el mismo problema.
> 3. **Flipper.** `ShamrockSetFlipper` no existe en la DLL (la función real es
>    `ShamrockSetFlipperMirror`).
> 4. **Modo de lectura.** `READ_MODE_SINGLE_TRACK = 1` en 3.0; en el SDK (y en el wrapper legado
>    `ccd_ps.py:892-893`) Single-Track es 3 y 1 es Multi-Track.
>
> **Antes de la primera ejecución de 3.0 contra el equipo**, respaldar los offsets actuales del
> Shamrock (red 1, red 2, espejo, detector, cero de ranura) leyéndolos con el legado o con Solis.
> Anotarlos acá: —

Requisito común: legado cerrado; PySpectrum 3.0 con `SAFE_MODE = False`; cámara enfriada y
estable si la prueba adquiere datos.

### ☐ BANCO-04 — El Shamrock acepta y relee la geometría del detector
- **Verifica**: que `get_shamrock()` pudo configurar `SetNumberPixels(1004)` y
  `SetPixelWidth(8.0)` y releerlos. 3.0 nunca lo había hecho antes de `DEC-033`.
- **Procedimiento**: arrancar PySpectrum 3.0 y revisar la consola durante el inicio.
- **Aceptación**: **no** aparece `ADVERTENCIA: geometría del detector NO verificada`.
- **Si falla**: anotar el código que imprime. Hasta resolverlo, el eje λ de
  `ShamrockGetCalibration` no es confiable y el Step & Glue planifica con la ventana nominal.
- **Resultado**: —

### ☐ BANCO-05 — Ancho real de la ventana espectral por red
- **Verifica**: la dispersión nominal de la hoja de datos contra la calibración real, y cuánto
  varía con la longitud de onda (el planificador supone que el solapamiento lo absorbe).
- **Procedimiento**: en Raman estático, adquirir con cada red en tres centros (150 l/mm: 450,
  650 y 850 nm; 1200 l/mm: 500, 550 y 600 nm) y leer el rango que muestra el indicador de rango
  espectral después de adquirir (eje real).
- **Aceptación**: 150 l/mm ≈ 103 nm y 1200 l/mm ≈ 11.6 nm, dentro de ±5 %; la variación entre
  centros de una misma red, por debajo del solapamiento mínimo (10 %).
- **Resultado**: tabla red × centro → ancho medido.

### ☐ BANCO-06 — Exactitud del eje λ con líneas conocidas
- **Verifica**: que el eje que entrega el SDK, ahora con la geometría correcta, ubica las líneas
  donde corresponde, en el centro **y en los bordes** del detector (el pitch afecta sobre todo
  los bordes).
- **Requisitos**: lámpara de calibración (Hg-Ar o Ne; líneas de referencia en `SYS-303`
  Paso 2.1). Alternativa sin lámpara: fonón del Si a 520.7 cm⁻¹, que requiere láser y el
  protocolo de seguridad completo.
- **Procedimiento**: para cada red, poner una línea conocida en el centro, cerca del borde
  izquierdo y cerca del borde derecho; registrar la posición medida del pico.
- **Aceptación**: error de cada línea ≤ 1 píxel (0.10 nm con 150 l/mm; 0.012 nm con
  1200 l/mm). La hoja de datos del SR-500i da 0.04 nm de exactitud en longitud de onda.
- **Si falla**: un error uniforme es un offset de red o de detector (`SYS-303` Fase 2); un
  error que crece hacia los bordes apunta al pitch o a la dispersión.
- **Resultado**: —

### ☐ BANCO-07 — Step & Glue sin huecos ni saltos
- **Verifica**: la planificación de `DEC-033` en el equipo real: ventana medida, margen en los
  extremos y verificación de cobertura.
- **Procedimiento**: con la lámpara halógena, barrer 400–900 nm con red de 150 l/mm, al 20 % y
  al 10 %. Exportar el HDF5.
- **Aceptación**: 7 ventanas al 20 %; atributos del HDF5 `window_source = measured`,
  `window_nm` ≈ 103 y `coverage_gaps_nm` vacío; sin advertencia de rango sin medir en la
  consola; saltos de empalme < 3 % (`SYS-303`, criterio Δ_stitch); anotar la duración.
- **Resultado**: —

### ☐ BANCO-08 — Asentamiento real de la red tras mover λ
- **Verifica**: `SW-002` — el software da por asentada la red por tiempo transcurrido
  (0.3 s para λ, 4 s para cambio de red), no por una consulta al hardware.
- **Procedimiento**: con una línea de la lámpara en pantalla y Live Raman activo, mover el
  centro ±20 nm y volver; registrar la posición del pico cuadro a cuadro durante los primeros
  5 s.
- **Aceptación**: la posición es estable desde el primer cuadro posterior a 0.3 s. Si
  `ShamrockSetWavelength` bloquea hasta terminar el movimiento, el riesgo de `SW-002` se cierra.
- **Resultado**: —

### ☐ BANCO-09 — Obturador del espectrógrafo: existe, actúa y confirma
- **Verifica**: que el Shamrock tiene el accesorio de obturador y que `ShamrockSetShutter`
  devuelve éxito cuando actúa. Si el accesorio no estuviera, el SDK devolvería un código de
  error y Raman estático mostraría "SIN confirmar" siempre (`DEC-031`, `DEC-034`).
- **Procedimiento**: en Raman estático, **Adquirir** con la lámpara encendida y luego con el
  obturador cerrado manualmente desde Control de Espectro; escuchar o ver la actuación.
- **Aceptación**: en operación normal no aparece "SIN confirmar"; con el obturador cerrado el
  cuadro es oscuro (sólo bias y ruido).
- **Resultado**: —

### ☐ BANCO-10 — Un cuadro real nunca es todo-ceros
- **Verifica**: la regla de `DEC-032`: un cuadro idénticamente cero se trata como lectura
  fallida, porque un EMCCD real siempre tiene offset de bias.
- **Procedimiento**: adquirir un cuadro oscuro (obturador cerrado, exposición mínima) en 1D y
  en 2D; anotar el mínimo y la media de las cuentas.
- **Aceptación**: mínimo claramente mayor que 0 (bias típico: cientos de cuentas).
- **Resultado**: —

### ☐ BANCO-11 — Live Raman rechazado si Exploración ya adquiere
- **Verifica**: que con el Live de Exploración activo, iniciar Live Raman devuelve
  `DRV_ACQUIRING` y el mensaje lo explica, en vez de correr dos lazos sobre un mismo sensor.
- **Aceptación**: Live Raman no arranca, el botón vuelve a "Iniciar" y el mensaje menciona
  Exploración.
- **Resultado**: —

### ☐ BANCO-12 — Imagen 2D con ROI: forma y filas correctas
- **Verifica**: que en el hardware real el sub-área configurada con `SetImage` produce cuadros
  de N_ROI × 1004 filas en Raman estático (modo Imagen) y en la referencia de LineScan, y que el
  desplazamiento `roi_ymin + 1` en `vstart` (el SDK indexa filas desde 1) toma las filas
  correctas.
- **Procedimiento**: definir un ROI de ~40 filas alrededor de la traza de la ranura; adquirir;
  comparar la forma del cuadro y la posición de la traza con una imagen completa.
- **Aceptación**: forma exacta, sin cuadros de ceros, sin corrimiento de una fila.
- **Resultado**: —

### ☐ BANCO-13 — Banda de ranura objetivo en Orden Cero
- **Verifica**: que la banda dibujada con 8 µm/px coincide con la ranura real.
- **Procedimiento**: en Orden Cero, con la ranura abierta, fijar `Slit Objetivo` en 100 µm; luego
  cerrar la ranura por hardware a 100 µm y comparar el ancho de la imagen de la ranura con la
  banda.
- **Aceptación**: diferencia de pocos píxeles (con 13 µm la banda salía 38 % más angosta).
- **Resultado**: —

---

## Grupo D — Comparación legado vs PySpectrum 3.0

### ☐ BANCO-14 — Corrimiento del eje del legado
- **Verifica**: `SW-004` — el legado configura 1002 píxeles (el eje vertical) en el Shamrock;
  su eje λ estaría corrido ~1 píxel respecto de 3.0.
- **Procedimiento**: misma línea de la lámpara, misma red y mismo centro, medida con el legado y
  con 3.0.
- **Aceptación de la hipótesis**: diferencia ≈ 0.10 nm con 150 l/mm (≈ 0.012 nm con 1200 l/mm).
- **Relevancia**: sólo para comparar cuantitativamente datos viejos con nuevos.
- **Resultado**: —

---

## Grupo E — PyPrinting 3.0 con los LÁSERES APAGADOS (bloque de seguridad, DEC-036)

Requisito común: **todos los láseres apagados** (llave o interlock de emisión del propio
láser), de modo que abrir un obturador no emita luz. Estas pruebas verifican la lógica de
control, no la óptica. PyPrinting 3.0 no se usa en producción hasta completarlas.

### ☐ BANCO-15 — Mapeo línea DAQ ↔ servo de cada obturador y polaridad
- **Verifica**: que cada obturador responde a la línea que el código le asigna. `config.py`
  dice 532 nm → `port0/line11` (activo en BAJO), 637 nm → `line8`, 592 nm → `line9`,
  808 nm → `line10`. La documentación anterior decía `line0:3`.
- **Procedimiento**: desde el panel de obturadores, abrir y cerrar cada uno por separado;
  observar qué servo se mueve y en qué posición queda en cada caso.
- **Aceptación**: cada casilla mueve su propio servo; "abierto" y "cerrado" coinciden con la
  posición física; el panel no muestra "CIERRE SIN CONFIRMAR".
- **Si falla**: no corregir en el momento. Anotar el mapeo real y reabrir `DEC-036`.
- **Resultado**: tabla obturador → servo → posición abierto/cerrado.

### ☐ BANCO-16 — Posición del servo de 532 nm sin la línea manejada
- **Verifica**: el riesgo que abre la polaridad invertida del 532 nm. La placa PCIe-6353 tiene
  un pull-down de 50 kΩ (hoja de datos NI 6353): con la línea sin manejar queda en BAJO, que
  para el 532 nm significa "abrir".
- **Procedimiento**: observar la posición del servo de 532 nm (a) al encender la PC,
  (b) al reiniciar la placa desde NI MAX ("Reset Device"), (c) al cerrar PyPrinting
  normalmente y (d) al terminarlo desde el Administrador de tareas.
- **Aceptación**: el servo queda en "cerrado" en los cuatro casos.
- **Si falla**: el problema es de hardware, no de software. Opciones: invertir la lógica en el
  driver del servo, o agregar un pull-up externo en la línea 11. Hasta resolverlo, el láser
  de 532 nm sólo se enciende con PyPrinting ya iniciado.
- **Resultado**: posición en (a), (b), (c) y (d).

### ☐ BANCO-17 — Modelo y recorrido real de la platina
- **Verifica**: que la platina es la P-517.3CD que declaran README y METACONTEXT (hoja de datos
  de PI: 100 × 100 × 20 µm) y que el límite de 20 µm en Z que adoptó `DEC-036` es el correcto.
- **Procedimiento**: `python tools\bench\pi_stage_probe.py`, con PyPrinting y PIMikroMove
  cerrados. Es de sólo lectura: no activa el servo ni mueve la platina.
- **Aceptación**: `tipo_platina` = P-517.3CD y `recorrido_max` ≈ {1: 100, 2: 100, 3: 20}.
- **Si falla**: anotar el modelo y el recorrido; el límite se ajusta en `config.PI_Z_RANGE_UM`
  y en `lab-invariants.md`.
- **Resultado**: pegar el bloque `RESUMEN`.

### ☐ BANCO-18 — Aviso de "cierre sin confirmar" ante una falla real de la placa
- **Verifica**: que un cierre que la placa no confirma se trata como abierto, con el watchdog
  reintentando y el banner persistente.
- **Procedimiento**: con un obturador abierto desde el panel, reiniciar la placa desde NI MAX
  ("Reset Device") para invalidar la tarea; luego cerrarlo desde el panel.
- **Aceptación**: el panel muestra "CIERRE SIN CONFIRMAR" en rojo y la casilla sigue marcada;
  la consola registra los reintentos; al reiniciar PyPrinting el obturador cierra.
- **Resultado**: —

### ☐ BANCO-19 — Pérdida de comunicación con la platina durante una rutina
- **Verifica**: la política de `DEC-036`: sin reconexión automática; obturadores cerrados,
  rutina abortada y aviso. La platina **no debe ir a home**.
- **Procedimiento**: iniciar una grilla de prueba corta y desconectar el cable USB del
  controlador E-517 a mitad de camino.
- **Aceptación**: la rutina se detiene, los obturadores quedan cerrados, la platina no se
  mueve a (50, 50, 10) µm y reconectar requiere una acción del operador desde el Dashboard.
- **Resultado**: —
