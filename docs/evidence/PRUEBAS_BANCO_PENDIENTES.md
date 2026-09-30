# Pruebas de Banco Pendientes — Verificación en Hardware Real

**Laboratorio**: Nanofotónica — Instituto de Nanosistemas (INS-UNSAM / CONICET)
**Ubicación**: `docs/evidence/PRUEBAS_BANCO_PENDIENTES.md`
**Vinculado a**: `docs/evidence/EVIDENCE_LEDGER.md`, `docs/decisions/DECISION_LOG.md`, [[SYS-301]], [[SYS-303]], [[MOD-06]]
**Última actualización**: 2026-09-27

---

## Para qué es esta lista

Todo lo que PyPrinting 3.0 y PySpectrum 3.0 afirman sobre el hardware y que **ningún test automático puede
comprobar** — porque el simulador sólo reproduce lo que sabemos, no lo que ignoramos — está
acá, con el procedimiento para comprobarlo en el banco y el criterio que decide si pasó.
También están acá **todas las dudas que el investigador dejó "para verificar en el banco"**
(grupo F), así se resuelven de una sola vez en una misma visita.

Cómo usarla:

1. Hacer las pruebas en el orden de los grupos: cada grupo exige menos que el siguiente.
2. Al terminar una, tildarla, completar **Resultado** (fecha, operador, valores medidos) y
   pegar la salida textual si la prueba la produce (las sondas imprimen un bloque `RESUMEN`).
3. **Si una prueba falla, no se corrige nada en el momento**: se anota el resultado y se
   reabre la decisión o el reclamo que figura en **Depende de**. Un resultado de banco que
   contradice al código es evidencia, no un bug a parchear en caliente.

**Seguridad (`CLAUDE.md` §4)**: todas las pruebas las ejecuta el operador. Ninguna requiere
láser, salvo BANCO-32 y BANCO-33, que están marcadas y necesitan aprobación explícita. Si se elige la línea del láser o una banda Raman como referencia de longitud de onda,
aplica el protocolo completo de obturadores y watchdog. Las sondas de `tools/bench/` sólo tocan
la cámara Andor: no accionan obturadores, láseres, DAQmx, platina ni espectrógrafo.

> Las dos sondas (`tools/bench/legacy_console_probe.py` y
> `tools/bench/andor_acquisition_mode_probe.py`) están versionadas junto con
> `tools/bench/INSTRUCCIONES.txt`, que explica paso a paso cómo ejecutarlas.

## Resumen

| ID | Verifica | Depende de | Requisitos | Estado |
| :--- | :--- | :--- | :--- | :--- |
| BANCO-01 | Pitch, tamaño y modelo del detector leídos del hardware | `DEC-033`, `SW-003` | Legado abierto (sólo lectura) | ✅ 2026-09-28 |
| BANCO-02 | Por qué el Live del legado se congelaba | Protocolo de adquisición | Legado abierto (sólo lectura) | ◐ 2026-09-28 (parcial) |
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
| BANCO-14 | Corrimiento del eje del legado (1002 vs 1004 px) | `SW-004` | Legado y 3.0 + lámpara de calibración | ◐ premisa confirmada |
| BANCO-15 | Mapeo línea DAQ ↔ servo de cada obturador y polaridad | `DEC-036` | PyPrinting 3.0, **láseres apagados** | ☐ |
| BANCO-16 | Posición del servo de 532 nm al encender, reiniciar NI y cerrar el programa | `DEC-036` | **Láseres apagados** | ☐ |
| BANCO-17 | Modelo y recorrido real de la platina (qCST, qTMN/qTMX) | `DEC-036` | PyPrinting cerrado; `tools/bench/pi_stage_probe.py` | ☐ |
| BANCO-18 | Aviso de "cierre sin confirmar" ante una falla real de la placa | `DEC-036` | PyPrinting 3.0, **láseres apagados** | ☐ |
| BANCO-19 | Pérdida de comunicación con la platina durante una rutina | `DEC-036` | PyPrinting 3.0, **láseres apagados** | ☐ |
| BANCO-20 | Qué está conectado en `ai3`: trigger Z de la E-517 o fotodiodo de 808 nm | C-44, R2-6 | Inspección del cableado | ✅ 2026-09-28 (reabre C-44) |
| BANCO-21 | Posición del espejo de detección (`line7`) al encender y tras un cierre forzado | C-08, R2-4/5 | **Láseres apagados** | ◐ 2026-09-28 (parcial) |
| BANCO-22 | Inventario: placa en NI MAX, BNC-2110 ↔ líneas, fotodiodos, láseres, flipper, iXon | R1-1, D-11, C-01 R1 | Inspección, NI MAX | ◐ 2026-09-28 (parcial) |
| BANCO-23 | Versiones de software en la PC del banco | C-01 R1 | Consola | ◐ 2026-09-28 (parcial) |
| BANCO-24 | Δt entre filas y filas tras el escalón en `NP_xxx.txt` del legado y de 3.0 | C-01 R1 | Archivos ya guardados | ◐ 2026-09-28 (reabre C-01) |
| BANCO-25 | Offsets del Shamrock leídos del equipo | C-04, R2-9 | Legado abierto (sólo lectura) | ✅ 2026-09-28 (**difiere de lo anotado**) |
| BANCO-26 | Tamaño real del buffer DAQmx de una tarea continua a 10 kS/s | C-01 | Sin láser; sólo entradas analógicas | ☐ |
| BANCO-27 | La traza sigue en tiempo real a una señal conocida | C-01, `DEC-037` | Generador o LED en un AI libre | ☐ |
| BANCO-28 | Cadencia real de la traza y costo de cada lectura | C-01 | Sin láser | ☐ |
| BANCO-29 | Latencia escalón → línea DO del obturador (eléctrica) | C-01, Ronda 1 | Osciloscopio, LED o generador | ☐ |
| BANCO-30 | Tiempo mecánico de apertura y cierre de cada obturador | C-01 R1 Q7 | LED + fotodiodo a través del obturador | ☐ |
| BANCO-31 | Robustez de la traza ante GUI congelada y error −50103 | C-01 | Sin láser | ☐ |
| BANCO-34 | Revisión de trazas y nodos ya guardados en producción | C-01, Ronda 2 (metrología) | Archivos del banco | ☐ |
| BANCO-35 | Convivencia de PySpectrum y PyPrinting sobre la misma placa | C-01 Ronda 2, `DEC-036` | Dos programas abiertos, **láseres apagados** | ☐ |
| BANCO-36 | Accesorios, límites y ejes del Shamrock | PySpectrum bloque A (Ronda 2) | Sin accionar | ☐ |
| BANCO-37 | Persistencia de los offsets vigentes | PySpectrum bloque A (Ronda 2) | Sin accionar | ☐ |
| BANCO-37b | Persistencia de un offset **escrito** | PySpectrum bloque A (Ronda 2) | **Acciona hardware, con aprobación** | ☐ |
| BANCO-38 | Tablas y capacidades de la cámara | PySpectrum bloque A (Ronda 2) | Sin accionar | ☐ |
| BANCO-39 | ¿Bloquean `SetWavelength`, `SetGrating` y `SetAutoSlitWidth`? | PySpectrum bloque A (Ronda 2) | **Acciona hardware, con aprobación** | ☐ |
| BANCO-40 | Pasos por píxel y signo del offset de red | PySpectrum bloque A (Ronda 2) | **Acciona hardware, con aprobación** | ☐ |
| BANCO-41 | `SetEMCCDGain` durante una adquisición | PySpectrum bloque A (Ronda 2) | Sin accionar | ☐ |
| BANCO-42 | Umbral especular por red | PySpectrum bloque A (Ronda 2) | **Acciona hardware, con aprobación** | ☐ |
| BANCO-43 | Exposición y ranura seguras en orden cero; píxel de referencia | PySpectrum bloque A (Ronda 2) | **Acciona hardware, con aprobación** | ☐ |
| BANCO-44 | Un cuadro nuevo por ventana, sin ceros | PySpectrum bloque A (Ronda 2) | **Acciona hardware, con aprobación** | ☐ |
| BANCO-45 | Arranque sin escrituras ni mock | PySpectrum bloque A (Ronda 2) | Sin accionar | ☐ |
| BANCO-46 | Stop y E-STOP bajo espera larga | PySpectrum bloque A (Ronda 2) | **Acciona hardware, con aprobación** | ☐ |
| BANCO-47 | Un solo camino al orden cero | PySpectrum bloque A (Ronda 2) | **Acciona hardware, con aprobación** | ☐ |
| BANCO-48 | Repetibilidad e histéresis de la torreta | PySpectrum bloque A (Ronda 2) | **Acciona hardware, con aprobación** | ☐ |
| BANCO-49 | "La línea que camina" | PySpectrum bloque A (Ronda 2) | **Acciona hardware, con aprobación** | ☐ |
| BANCO-50 | Linealidad y saturación en la calibración | PySpectrum bloque A (Ronda 2) | **Acciona hardware, con aprobación** | ☐ |
| BANCO-51 | Deriva del eje λ en la sesión | PySpectrum bloque A (Ronda 2) | **Acciona hardware, con aprobación** | ☐ |
| BANCO-52 | Línea contra ancho de ranura | PySpectrum bloque A (Ronda 2) | **Acciona hardware, con aprobación** | ☐ |
| BANCO-53 | Uniones de Step & Glue con la lámpara | PySpectrum bloque A (Ronda 2) | **Acciona hardware, con aprobación** | ☐ |
| BANCO-54 | Tiempo de reenfriado del iXon3 a −60 °C después de "Reconectar cámara" | PySpectrum bloque A (Ronda 3, qa-ux) | Sin láser; tapa puesta | ☐ |
| BANCO-55 | Driver propio de la cámara contra pylablib, la referencia probada en el banco (R4-E) | PySpectrum bloque A (DEC-040) | Solis cerrado, sin láser, tapa puesta | ☐ |
| BANCO-56 | Orientación de la imagen del Andor en orden cero frente a la cámara | PySpectrum bloque A, paso 7 (espejo rápido) | Orden cero, lámpara, sin láser | ◐ 2026-09-28 (observación) |
| BANCO-57 | Cierre de PySpectrum 3.0 con el satélite PyPrinting abierto | PySpectrum bloque A, paso 13 | Sin láser; platina conectada | ☐ |
| BANCO-58 | Primera calibración automática de λ en SÓLO MEDIR | PySpectrum bloque A, paso 14 | **532 atenuado por el filtro de densidad y el notch; con aprobación** | ☐ |
| BANCO-59 | Rutinas de grilla de 3.0: espejo, potencia y láser por fase | PySpectrum AND-1 (R4-K) | **Láser; con aprobación** | ☐ |
| BANCO-32 | Corte de impresión real a baja potencia | C-01 | **Láser a baja potencia, con aprobación** | ☐ |
| BANCO-33 | Deriva del sistema (≥ 1 h tras termalizar) | `lab-invariants` §6 (deriva 30 nm/min provisoria) | **Láser a baja potencia, con aprobación** | ☐ |

---

## Grupo A — Con el PySpectrum legado abierto (sólo lectura; se puede hacer ya)

La sonda se ejecuta dentro del proceso legado, desde su consola (menú Console Widget), con:

```python
exec(open(r"C:\Users\josel\Documents\Obsidian_Vault\printing3\tools\bench\legacy_console_probe.py", encoding="utf-8").read())
```

No llama a nada que modifique la cámara: sólo getters de pylablib y funciones `Get*` del SDK.

### ✅ BANCO-01 — Geometría del detector leída del hardware
- **Verifica**: que el detector es el que `DEC-033` estableció con hojas de datos.
- **Estado (2026-09-28, investigador):** el tamaño de píxel queda **validado por la hoja de datos** ([DS-iXon] p. 1: 8 × 8 µm, 1004 × 1002 activos), que es fuente primaria. Esta lectura es una confirmación opcional, **no un bloqueante**: si el equipo devolviera otra cosa, el cabezal instalado no sería el de la hoja de datos, y eso se reabre en `DEC-033`.
- **Procedimiento**: correr la sonda; leer las líneas `C.pixel_size`, `C.detector_size` y `C.sdk`.
- **Aceptación**: `GetPixelSize = 8.00 x 8.00 um`, `GetDetector = 1004x1002`,
  `GetHeadModel = 'DU8285_VP'`.
- **Si falla**: reabrir `DEC-033` y `SW-003`. El valor vive en un solo lugar
  (`andor_ccd_driver.DETECTOR_PIXEL_PITCH_UM`) y los tests usan las hojas de datos como oráculo,
  así que fallarían a propósito hasta revisar esas fuentes.
- **Resultado (2026-09-28, investigador, sonda de consola en la sesión del legado; `reserva/PRUEBAS_BANCO_28-09-2026.md`):**
  - `C.device_info` = `TDeviceInfo(controller_model='CCI-23', head_model='DU8285_VP', serial_number=2457)`;
  - `C.detector_size` = `(1004, 1002)`;
  - `C.pixel_size` = `(8e-06, 8e-06)`, es decir 8.00 × 8.00 µm.
  - **Pasa**: coincide con [DS-iXon] y con `DEC-033`. Lo leyó pylablib, no el SDK directo: la línea
    `C.sdk` no salió porque la sonda buscaba `atmcd64d.dll` y el legado tiene cargada
    `atmcd64d_legacy.dll`. La sonda ya prueba los dos nombres.

### ◐ BANCO-02 — Por qué el Live del legado se congelaba
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
- **Resultado (2026-09-28, parcial; `reserva/PRUEBAS_BANCO_28-09-2026.md`):**
  - con el Live apagado y sin haberlo usado: A intacto, modo `cont`, estado `idle`, exposición 1.0 s,
    temperatura 23.9 °C (enfriador apagado);
  - con el Live encendido: A **`TAPADO`** (la instancia tiene `set_acquisition_mode = 'cont'`, un
    `str`), modo `cont`, estado `acquiring`, exposición 0.1 s. La **temperatura no se puede leer**:
    `GetTemperatureF raised error 20072 (DRV_ACQUIRING)`.
  - Queda confirmado que la asignación del legado tapa el método de pylablib ya desde el Live, no
    sólo desde REC Liveview Kinetics. Falta: repetir después de REC Liveview Kinetics (¿`kinetic`?) y
    correr `observar_live()`, que falló por el mismo motivo que `C.sdk` (ya corregido en la sonda).
  - **Consecuencia en 3.0 (ya implementada):** mientras la cámara adquiere, `get_temperature`
    devuelve la última lectura con `DRV_ACQUIRING`, y el panel y el módulo de cámara la muestran como
    "⏸ última lectura; adquiriendo", nunca como "Estabilizado"
    (`tests/test_andor_pylablib_backend.py`).

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
  - **Intento del 2026-09-28 (no concluyente, se repite):** con sólo la terminal abierta y el
    espectrómetro reiniciado, la sonda informó `Initialize falló: 0`, que no es un código del SDK.
  - Diagnóstico manual con la DLL del legado (`C:\Users\PRINTING\Desktop\PySpectrum\atmcd64d.dll`):
    `GetAvailableCameras` → 20002 con **0 cámaras**, y `Initialize("")` → 0. El SDK no veía ninguna
    cámara, así que el problema está en la conexión PC ↔ cámara (alimentación, USB, driver o un
    proceso que la retiene), no en la sonda.
  - Además, en la copia clonada `C:\PyPrinting3_banco` faltaba `pyspectrum\drivers\libs\atmcd64d.dll`,
    aunque está en `origin/main`: clon incompleto o DLL en cuarentena del antivirus.
  - La sonda se corrigió después: `Initialize` con cadena vacía, como pylablib, e informe previo de
    `GetAvailableCameras`.
  - **Causa encontrada (2026-09-28):** el legado carga `C:\Program Files\Andor SOLIS\atmcd64d_legacy.dll`, que pylablib busca primero. La sonda usaba `atmcd64d.dll`. Ahora busca en el mismo orden que pylablib; mientras tanto se corre pasándole esa ruta como argumento.

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
> Anotarlos acá:
> - **Dato del investigador (2026-09-27), EXPERIMENTAL hasta leerlo del equipo:**
>   - offset de la red de 150 l/mm = **85**. Es el valor del 2026-09-28 (R4-3), que reemplaza al 87 del 2026-09-27.
>     **Superado por R4-G:** valen los guardados en el equipo (87, 195, espejo 60, detector 0; BANCO-25);
>   - red de 1200 l/mm = 0, **sin calibrar** (a medir: BANCO-25 a);
>   - offset del detector = **0**.
> - Falta: el valor leído del equipo con `tools/bench/legacy_console_probe.py` (sección D), el
>   offset del espejo y los ceros de ranura.
> - Para comparar: 3.0 escribe hoy red 1 = 12, red 2 = −35 y detector = 5 en cada arranque
>   (C-04); con estos datos, eso **pisaría** el 85 de la red de 150 l/mm.

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
- **Además (R4-H, 2026-09-29): cuál de los dos caminos manda.**
  - Qué sabemos:
    - el único obturador está en el Shamrock y hay un cable TTL de la cámara al Shamrock (BANCO-22);
    - el legado lo abre por USB **una vez al arrancar** (`ShamrockSetShutter(DEVICE, 1)`) y después lo
      abre y cierra por el TTL de la cámara (`setup_shutter('open', 1)` / `('closed', 0)`).
  - Qué hace 3.0: no abre al arrancar. Abre a pedido, en las rutinas o en el Live, **por los dos
    caminos**, y cierra también por los dos (`pyspectrum/services/spectrometer_shutter.py`).
  - Anotar con la tapa y la lámpara:
    - (a) si con sólo el USB abierto (y el TTL de la cámara cerrado) el cuadro es oscuro o no;
    - (b) lo mismo al revés;
    - (c) si al encender el Shamrock el obturador arranca cerrado.
  - Con eso se sabe si uno de los dos caminos sobra, y si el TTL de "cerrado" con tipo 0 cierra de verdad.
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

### ◐ BANCO-14 — Corrimiento del eje del legado
- **Verifica**: `SW-004` — el legado configura 1002 píxeles (el eje vertical) en el Shamrock;
  su eje λ estaría corrido ~1 píxel respecto de 3.0.
- **Procedimiento**: misma línea de la lámpara, misma red y mismo centro, medida con el legado y
  con 3.0.
- **Aceptación de la hipótesis**: diferencia ≈ 0.10 nm con 150 l/mm (≈ 0.012 nm con 1200 l/mm).
- **Relevancia**: sólo para comparar cuantitativamente datos viejos con nuevos.
- **Resultado (2026-09-28, premisa):** en la sesión del legado, el Shamrock tiene
  `ShamrockGetNumberPixels = 1002` y `ShamrockGetPixelWidth = 8.0` µm, mientras que la cámara tiene
  1004 columnas. La premisa de `SW-004` queda confirmada; falta la medición con la lámpara.

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

---

## Grupo F — Relevamiento del banco (dudas del investigador; sin láser y sin accionar nada)

Todo lo que el investigador contestó "lo verifico en el banco" durante la auditoría del
2026-09-27 (`docs/evidence/auditoria_2026-09-27/RESPUESTAS_INVESTIGADOR.md`) y lo que la
auditoría no pudo cerrar sin mirar el equipo. Son inspecciones y lecturas: no se abre ningún
obturador ni se mueve nada.

### ✅ BANCO-20 — Qué está conectado en `ai3`
- **Verifica**: `config.py` usa `ai3` a la vez como fotodiodo de 808 nm (`PD_CHANNELS`) y como
  trigger del eje Z de la E-517 (`TRIGGER_CHANNELS`). Un barrido Z con 808 nm leería el mismo
  canal como trigger y como señal (C-44).
- **Procedimiento**: seguir el cable que llega a `AI 3` de la BNC-2110 correspondiente.
- **Resultado (2026-09-28, investigador):** `ai3` está conectado a la **PI, eje Z** (el trigger de
  la E-517). **Reabre C-44:** `config.PD_CHANNELS` asigna `ai3` al fotodiodo de 808 nm, y eso está
  mal.
- **Decisión (investigador, R4-G):** hoy el fotodiodo de 808 nm no está conectado; se deja
  `PD_CHANNELS` como está anotado en PyPrinting. El conflicto no tiene efecto mientras el 808 no esté
  conectado. Al conectarlo, hay que asignarle un `ai` libre.

### ◐ BANCO-21 — Espejo de detección (`line7`) al encender y tras un cierre forzado
- **Verifica**: el espejo es un conmutador (el mismo pulso cambia de posición) y el software no
  conoce su posición real (R2-5). El espectrómetro sólo recibe luz con el espejo abajo (R2-4).
- **Procedimiento**: con los láseres apagados, anotar la posición física del espejo (a) al
  encender todo, (b) después de cerrar PyPrinting normalmente, (c) después de terminarlo desde
  el Administrador de tareas; y comparar con lo que muestra el rótulo "Mirror" al reabrir.
- **Resuelve**: el diseño de la persistencia y la resincronización del espejo (fase 6.3 del plan).
- **Resultado (2026-09-28, investigador, parcial):**
  - el espejo es un conmutador **Thorlabs MFF101**;
  - al encender, **conserva la posición** en la que estaba;
  - el checkbox del programa lo mueve a la posición **opuesta**, sin respetar si el rótulo dice
    arriba o abajo. Confirma R2-5: el software no conoce la posición real.
  - Falta: (b) y (c), la posición después de un cierre normal y de uno forzado; y el modo de
    entrada configurado en el MFF101 (conmutación por flanco o posición por nivel).

### ◐ BANCO-22 — Inventario de hardware
Anotar para cada ítem el modelo leído de la etiqueta o de NI MAX:
- [ ] **Placa**: modelo y número de serie en NI MAX (se espera PCIe-6353); qué BNC-2110 va al
  conector 0 y cuál al conector 1, y en cuál están P0.7–P0.11 (R1-1).
- [ ] **Fotodiodos**: modelo y ganancia de cada uno, y a qué `ai` va (C-01, Ronda 1, pregunta 8).
- [ ] **Láseres**: modelos del 637, 592 y 808 nm (el verde es Excelsior-532-150-CDRH) (D-11).
- [ ] **Flipper del filtro de densidad**: ¿es un Thorlabs MFF101? Fuente de alimentación y modo
  de entrada (pregunta 9 de la Ronda 2 del verificador).
- [ ] **iXon3 885**: opción de enfriamiento DV o DU y temperatura alcanzable (`lab-invariants` §3).
- [ ] **Láser de 532 nm**: el investigador dice que es **de diodo** (R4-A-8), pero acá figura
  Excelsior-532-150-CDRH, que es DPSS. Leer la etiqueta. El tipo define cuán estable es su λ como
  referencia de la calibración automática.
- [ ] **Obturadores ópticos del espectrómetro**: ¿el Shamrock tiene obturador propio? ¿El iXon3
  tiene el obturador interno opcional? ¿Hay un cable TTL de la cámara al Shamrock? (Ronda 1 del
  bloque A, D-3.)
- [ ] **Referencia absoluta de λ** (R4-B-11):
  - ¿hay una λ medida del láser de 532?
  - ¿se puede acercar un tubo fluorescente (Hg 546.07 nm, que cae en el mismo cuadro que el 532 con
    la red de 150) a la entrada del espectrómetro?
  - una vez, comparar la posición del pico de 532 visto a través del notch con la del 532
    atenuado sin notch (láser en baja, filtro de densidad, ganancia EM 0).
- [ ] **Cámara desmontada alguna vez** (R4-A-7): anotar la fecha si se sabe. Un desmontaje puede
  mover el corrimiento común a las dos redes.
- [ ] **Obturadores de fabricación propia**: ¿la línea TTL entra a un microcontrolador que
  genera el PWM del servo? Anotar el circuito (C-01, Ronda 2, pregunta 15).
- **Resultado (2026-09-28, investigador, parcial):**
  - **Placa:** PCIe-6353. En la BNC-2110 "A" están P0.0–P0.7. Falta dónde están P0.8–P0.11 y el
    número de serie.
  - **Fotodiodos:** Thorlabs **PDA36A**. Falta la ganancia de cada uno y a qué `ai` va cada uno.
  - **Láseres:** el verde es el **Excelsior** (revisado en la etiqueta), es decir DPSS, no de
    diodo: se corrige R4-A-8. Los modelos del resto quedan pendientes; el investigador los considera
    no relevantes por ahora.
  - **Flippers:** el del filtro de densidad es **de fabricación casera**; el del espejo up/down es
    el Thorlabs MFF101.
  - **iXon3 885:** opción de enfriamiento **DU**, llega a **−80 °C** (el valor con aire de
    [DS-iXon] para DU).
  - **Obturador del espectrómetro:** hay un **cable TTL de la cámara al Shamrock**. Suena un solo
    obturador, y por el sonido parece comandado por la cámara; según el investigador, el único
    obturador es el del Shamrock. Es decir: `SetShutter` de la cámara acciona el obturador del
    Shamrock a través de ese TTL. Falta confirmar si el iXon3 tiene además obturador interno.
  - Pendientes: la referencia absoluta de λ, la fecha de desmontaje de la cámara y el circuito de
    los obturadores de fabricación propia.

### ◐ BANCO-23 — Versiones de software en la PC del banco
- **Procedimiento**: en la consola del entorno de PyPrinting, anotar la versión del driver
  NI-DAQmx (NI MAX → Software) y las de `nidaqmx`, `pipython`, `PyQt6` y `numpy`
  (`python -m pip show nidaqmx pipython PyQt6 numpy`). Python ya se sabe: 3.11.13.
- **Resultado (2026-09-28, investigador, parcial):**
  - pylablib 1.4.3 en el entorno del legado;
  - el resto, "son las de `requirements.txt`" según el investigador. Queda como dato EXPERIMENTAL
    hasta pegar la salida de `pip show`;
  - falta la versión del driver NI-DAQmx;
  - "spectrog": es un archivo de `C:\Program Files\Andor SOLIS` (investigador, R4-G).
  - **Requisito para correr PySpectrum 3.0 en el banco (2026-09-28):** pylablib 1.4.3 trae la extensión
    compilada de Andor sólo para ciertas versiones de Python. En el banco está `utils.cp311-win_amd64.pyd`
    (Python 3.11, entorno `envspectrum`). En la PC de desarrollo (Python 3.13) no está, y
    `pylablib.devices.Andor` no se puede importar: los tests usan una cámara falsa. El entorno de 3.0 en
    el banco tiene que ser Python 3.11 con pylablib 1.4.3, como el del legado. Verificar con
    `python -c "from pylablib.devices.Andor import AndorSDK2Camera"` antes del primer arranque.

### ◐ BANCO-24 — Cadencia real de la traza (legado y 3.0), desde archivos guardados
- **Procedimiento**: abrir 5 a 10 `NP_xxx.txt` de impresiones recientes hechas con el
  **legado** (el que se usa a diario) y, si hay, con 3.0 en `7f5d10a`, y anotar para cada
  programa el Δt típico entre filas y cuántas filas hay después del escalón. Conviene copiar
  esos archivos a `docs/evidence/` para que el cálculo quede reproducible (octava ronda, Q-1).
- **Verifica**: la predicción de ≈ 47 ms reales para el QTimer de 35 ms (medida en la PC de
  desarrollo, `auditoria_2026-09-27/c01_ronda1/timer_probe.py`). Ojo: si el eje de tiempo de
  esos archivos es sintético (`np.linspace`), el Δt no es medido; anotarlo.
- **Resultado (2026-09-28, investigador):**
  - el Δt entre filas no es constante: **47–57 ms en 3.0** (acorde con la predicción de ≈ 47 ms) y
    **30–50 ms en el legado**;
  - **el eje de tiempo no coincide con el reloj:** en una traza que duró 8 s por reloj, el archivo
    marca 7 s (≈ −12 %).
  - **Reabre C-01:** o el eje de tiempo no se mide (se reconstruye de un período nominal) o se
    pierden muestras sin registrarlo. Hay que ver cómo arma cada programa la columna de tiempo antes
    de usar esas trazas para medir tiempos de impresión. Conviene copiar esos archivos a
    `docs/evidence/`.

### ✅ BANCO-25 — Offsets del Shamrock leídos del equipo
- **Procedimiento**: con el legado abierto, correr `tools/bench/legacy_console_probe.py`
  (sección D, sólo lectura) y anotar los offsets de las dos redes, del detector, del espejo y
  los ceros de ranura. Valores del investigador al 2026-09-28 (R4-3, que reemplaza al 87 de R2-9):
  red de 150 l/mm = **85**, red de 1200 l/mm = 0, detector = 0, **leídos en Solis** (calibración de
  ≈ 2026-08-28). PySpectrum 3.0 nunca se abrió en esa PC. Con la sonda falta leer el offset del
  espejo y los ceros de ranura, y comparar. Ver la nota del Grupo C.
- **Además (R4-3):**
  - (a) **medir el offset de la red de 1200 l/mm**, que hoy vale 0 y nunca se calibró, con la
    rutina de 532 nm + filtro de densidad una vez que esté extendida;
  - (b) **aplicar el protocolo de calibración del offset del detector**, que falta idear en la
    Ronda 1 del bloque A de PySpectrum.
  Los dos resultados van al archivo de calibraciones, con fecha y método.
- **Resuelve**: el respaldo previo al primer arranque de PySpectrum 3.0 y el diseño de los
  offsets dinámicos (C-04).
- **Resultado (2026-09-28, sonda de consola en la sesión del legado, sección D; `reserva/PRUEBAS_BANCO_28-09-2026.md`).** Este es
  **el respaldo**: lo que el Shamrock SR-1611 tiene guardado hoy.

  | Posición de la torreta | Líneas/mm | Blaze | Home (pasos) | Offset (pasos) |
  | :--- | ---: | :--- | ---: | ---: |
  | 1 | 150 | 800 nm | −9147 | **87** |
  | 2 | 1200 | 500 nm | 759864 | **195** |
  | 3 | 0 (**espejo**, `Mirr`) | — | 1528009 | **60** |

  - Detector offset = **0**. Ceros de ranura: 1 = −45, 2 = −1, 3 = −45, 4 = −45.
  - Estado al leer: red 1, λ central 863.5 nm, `PixelWidth` 8.0 µm, `NumberPixels` 1002.
    Coeficientes (A, B, C, D) = (811.677, 0.103463, −4.178e−08, −1.378e−11). Con 1002 píxeles dan una
    ventana de ≈ 103.7 nm, que coincide con lo esperado en BANCO-05.
  - **Discrepancias con lo anotado (a resolver con el investigador):**
    - red de 150 l/mm: el equipo tiene **87**, que es el valor de R2-9; R4-3 decía 85;
    - red de 1200 l/mm: el equipo tiene **195**, no 0. Offset nulo no es lo que hay guardado; puede
      venir de fábrica o de una calibración anterior;
    - la **torreta tiene un espejo** en la posición 3. Eso importa para el orden cero y el
      "espejo rápido" (paso 7 del bloque A).
  - **Resuelto (investigador, R4-G):** valen los que el equipo tiene guardados. El archivo de
    calibraciones (pasos 9 y 10) parte de estos valores.
  - 3.0 ya no escribe offsets al arrancar (C-04, `DEC-040`), así que estos valores no se pisan.

---

## Grupo G — Traza de impresión (C-01): adquisición y latencia

Validan la reversión de `DEC-037` y dan los datos para la Ronda 2 de C-01. Las pruebas
BANCO-26 a BANCO-31 no usan láser: la señal la da un generador de funciones o un LED
conectado a un canal analógico libre (el investigador confirmó que hay canales libres).
El detalle de cada una está en `auditoria_2026-09-27/c01_ronda1/instrumentation.md` §3.

### ☐ BANCO-26 — Tamaño real del buffer de una tarea continua a 10 kS/s
- **Verifica**: la regla de NI es ambigua justo en 10 kS/s: el buffer puede ser de 10 000 o de
  100 000 muestras por canal, y eso decide si el defecto de C-01 desbordaba a ≈ 1 s o a ≈ 10 s.
- **Procedimiento**:
  - **Requisitos:** PyPrinting, el PySpectrum legado y Solis cerrados, o al menos sin ninguna lectura de fotodiodos en curso, porque si otro programa tiene las entradas NI-DAQmx da −50103.
  - **Ejecutar:** `python tools\bench\daq_buffer_probe.py`, que sólo usa entradas analógicas. La sonda:
    - crea la tarea continua que tenía la traza en C-01: `Dev1/ai0, ai1, ai2, ai3, ai6`, 10 000 S/s por canal, `samps_per_chan = 1000`;
    - la confirma con un commit, que es cuando NI-DAQmx asigna el buffer, sin arrancar ninguna adquisición;
    - lee `input_buf_size` con el buffer automático y con uno explícito de 100 000 muestras;
    - cierra la tarea.
  - **Resultado:** pegar el bloque `RESUMEN BANCO-26`.
- **Aceptación e interpretación:**
  - buffer automático = 10 000 → el defecto de C-01 desbordaba a ≈ 1 s;
  - buffer automático = 100 000 → desbordaba a ≈ 10 s;
  - el buffer explícito tiene que quedar en 100 000, que es lo que necesita la opción E de C-01.
- **Resultado**: —

### ☐ BANCO-27 — La traza sigue en tiempo real a una señal conocida
- **Procedimiento**: una onda cuadrada de 1 Hz en un AI libre, mirada con la traza de
  PyPrinting configurada sobre ese canal.
- **Aceptación**: con la versión revertida (`DEC-037`) la traza muestra 1 Hz sin atraso
  creciente. Con la tarea continua de `6abbbfc` se predice un período aparente de ≈ 35 s y,
  después, ceros: si se quiere confirmar el diagnóstico, es la prueba más barata.
- **Resultado**: —

### ☐ BANCO-28 — Cadencia real de la traza y costo de cada lectura
- **Procedimiento**: registrar durante 60 s el instante de cada tick y la duración de cada
  lectura finita (crear, leer, cerrar la tarea).
- **Resultado**: —

### ☐ BANCO-29 — Latencia eléctrica: escalón de señal → línea del obturador
- **Procedimiento**: osciloscopio en dos canales: el escalón aplicado al AI (generador o LED
  modulado) y la línea DO del obturador (con el obturador desconectado o los láseres apagados).
  Correr el criterio de impresión en modo de prueba y medir el retardo en al menos 20 eventos.
- **Resuelve**: la latencia de software real frente al objetivo de la Ronda 1 de C-01.
- **Resultado**: —

### ☐ BANCO-30 — Tiempo mecánico de apertura y cierre de cada obturador
- **Verifica**: los obturadores son de fabricación propia y su tiempo de respuesta no fue
  medido (C-01, Ronda 1, pregunta 7).
- **Procedimiento**: un LED y un fotodiodo a través de la apertura de cada obturador (sin
  láser); osciloscopio entre la línea DO y el fotodiodo.
- **Resultado**: —

### ☐ BANCO-31 — Robustez ante GUI congelada y error −50103
- **Procedimiento**: con la traza corriendo sobre la señal de prueba, congelar la GUI unos
  segundos (p. ej. arrastrar la ventana) y abrir a la vez Power BS, para provocar el conflicto
  de recursos −50103.
- **Aceptación**: ningún 0.0 V registrado como dato válido; el error queda en el log.
- **Resultado**: —

### ☐ BANCO-34 — Revisión de trazas y nodos ya guardados en producción
Se hace con archivos que ya están en la PC del banco (impresiones con `7f5d10a`); no hace falta
encender nada. Resuelve preguntas de la Ronda 2 de C-01
(`docs/evidence/auditoria_2026-09-27/c01_ronda2/metrology.md` §7).
- [ ] **Preset en uso** ("umbral + valor absoluto"): anotar `Steps before`, `Steps after`, el
  umbral absoluto (V) y el "Umbral Mín" (V).
- [ ] **Voltajes típicos en ai0**: la base antes de la captura y la meseta después.
- [ ] **Nodos TIMEOUT**: ¿el escaneo o la imagen posterior muestra una NP impresa? En la traza
  guardada, ¿hay un escalón de ×1.4–1.55 que no se detectó? La simulación predice que, con
  umbral 1.5 y ventanas de 10/10, la rama relativa **no** detecta escalones menores que ≈ ×1.57.
  Si esto se confirma, parte de los TIMEOUT serían capturas reales con el láser abierto 40 s.
- [ ] **Nodos SUCCESS con t_print < 1 s** (≈ 0.6 s): serían un artefacto de la apertura del
  obturador.
- [ ] **Subidas transitorias** que no terminan en impresión: de cuánto (×) y cuánto duran (ms).
  Deciden si se pueden usar ventanas cortas sin tomar un transitorio por una captura.
- **Resultado**: —

### ☐ BANCO-35 — Convivencia de PySpectrum y PyPrinting sobre la misma placa
- **Verifica**: el investigador usa los dos programas a la vez ("PySpectrum son los ojos,
  PyPrinting el cuerpo"). El legado de PySpectrum define sus propios obturadores con el
  **cableado viejo** (`scratch/pyspectrum-legacy/Instrument_nidaqmx_ps.py`: 532 → `line9`,
  594 → `line10`, 637 → `line11`, 808 → `line12`), que no coincide con el vigente (532 →
  `line11`, 637 → `line8`, 592 → `line9`, 808 → `line10`). Además, la placa admite una sola
  tarea de entradas analógicas a la vez: un programa puede recibir −50103 mientras el otro lee.
- **Contexto (investigador, 2026-09-27)**: hoy el banco trabaja con **PySpectrum legacy +
  PyPrinting legacy**. PySpectrum 3.0 no se probó, y tampoco la combinación 3.0 + 3.0 (en 3.0
  PyPrinting se abre como ventana satélite dentro del proceso de PySpectrum, DEC-019).
- **Primero, leer la configuración de los legados que corren en el banco** (sin accionar
  nada): los canales de obturadores en `Instrument_nidaqmx_pp.py` (PyPrinting) y
  `Instrument_nidaqmx_ps.py` (PySpectrum) de la PC del banco. En las copias del repositorio,
  PyPrinting legacy tiene 532 → `line12` y 637 → `line11` (activo en BAJO): con el cableado
  vigente, **su botón "637" abriría el obturador de 532 nm**. Si la PC del banco tiene esos
  canales, no usar los botones de obturador del legado hasta resolverlo.
  **Respuesta del investigador (2026-09-27): los legados del banco tienen los obturadores
  actualizados**; las copias del repositorio son más viejas. Queda sólo la parte (b) de
  convivencia de entradas analógicas, y confirmar de paso que cada botón mueve lo que dice.
- **Procedimiento** (láseres apagados, obturadores observables): con PySpectrum legacy y
  PyPrinting legacy abiertos a la vez (la combinación en uso) y, por separado, con
  PyPrinting 3.0, (a) accionar desde cada programa cada botón de obturador y
  anotar qué servo se mueve; (b) correr la traza de PyPrinting mientras PySpectrum lee un
  fotodiodo, y anotar errores de cada consola.
- **Combinación 3.0 + 3.0 (R4-2b, 2026-09-28)**: PyPrinting 3.0 se abre **sólo desde el menú
  Herramientas de PySpectrum 3.0**, como ventana satélite en el mismo proceso. En modo laboratorio,
  el lanzador bloquea abrir los dos por separado. Verificar además que:
  - (c) desde la ventana satélite, cada botón de obturador mueve el servo que dice, y hay un
    solo watchdog;
  - (d) con PySpectrum abierto, el lanzador rechaza "Microscopio Derecho" y el mensaje remite a
    Herramientas.
- **Aceptación**: cada botón mueve el obturador que dice, y ningún programa deja una tarea
  tomada al cerrarse. Si el legado mueve el servo equivocado, **no usar sus botones de
  obturador** hasta corregirlo.
- **Resultado**: —

## Grupo H — PySpectrum 3.0, bloque A (primer arranque seguro, orden cero, calibración, Step & Glue)

Consolidado por `instrumentation` en la Ronda 2 (`auditoria_2026-09-27/pyspectrum_A_ronda2/instrumentation.md` §8),
fusionando las pruebas A1-A9 del experimentalista, P0-P11 del abogado del diablo y BANCO-A1 a A3 del arquitecto.

- **Orden (R4-A-11):** primero el Grupo E con los láseres apagados, sobre `main`; después este grupo.
- **Requisitos de todo lo que escriba o mueva:**
  - BANCO-25 hecho (respaldo de offsets leído);
  - ganancia EM en 0 confirmada;
  - láseres cerrados, salvo el 532 atenuado cuando la prueba lo pida.
- **PySpectrum 3.0 no se abre contra el equipo** hasta completar los pasos del bloque A que corrigen la lectura de la rendija (C-06) y la exposición (DEC-040).

| ID | Qué resuelve | Procedimiento resumido | ¿Acciona algo? | ¿Aprobación? |
| :--- | :--- | :--- | :--- | :--- |
| BANCO-36 | Accesorios, límites y ejes del Shamrock | sonda, sólo getters: `GetDetectorOffsetEx` ×4, `Port2`, `GetWavelengthLimits(1..3)`, `AtZeroOrder`, `FlipperMirrorIsPresent`/`GetFlipperMirror(1,2)`, `AutoSlitIsPresent`/`GetAutoSlitWidth(1..4)`, `GetSlitZeroPosition`, `ShutterIsPresent`/`GetShutter`, `EepromGetOpticalParams`, `GetNumberGratings`/`GetGratingInfo`; `GetCalibration(1002)` y `(1004)` frente al cúbico en el mismo estado | No | No |
| BANCO-37 | Persistencia de los offsets vigentes | leer; apagar y encender el Shamrock; releer; fecha y contenido de `SPECTROG.INI` | No (ciclo de energía, sin escrituras) | No |
| BANCO-37b | Persistencia de un offset **escrito** | la primera escritura real (1200 l/mm) con §3.3; leer en Solis; ciclo de energía; releer | **Sí** (escritura y posible giro, §3.1) | **Sí**, y BANCO-25 hecho |
| BANCO-38 | Tablas y capacidades de la cámara | legado abierto, cámara IDLE, sólo getters: `GetNumberAmp`, `GetAmpDesc`, `GetNumberHSSpeeds`/`GetHSSpeed` por amplificador, `GetEMGainRange` en modo 0, `GetCapabilities` (modos de ganancia, `AC_FEATURES_SHUTTEREX`), `GetNumberVSSpeeds`/`GetVSSpeed(i)` (qué índice es 1.9 µs), `GetFastestRecommendedVSSpeed`, `GetTemperatureRange` (DV o DU), `IsInternalMechanicalShutter`, `GetShutterMinTimes`, `IsCoolerOn` | No | No |
| BANCO-39 | ¿Bloquean `SetWavelength`, `SetGrating` y `SetAutoSlitWidth`? | duración de cada llamada para saltos de 20, 200 y 500 nm, cambio de red, y ranura 50 → 100 → 50 µm; relectura al volver | **Sí** (torreta y ranura) | **Sí** (sin láser, EM 0, cámara IDLE) |
| BANCO-40 | Pasos por píxel y signo del offset de red | con la fuga de 532 (filtro de densidad en baja, EM 0) y cada red: leer O₀, escribir O₀ ± 10 y ± 20, medir el corrimiento, **restaurar O₀ y releer**; anotar si la torreta gira y si hace falta repetir `SetWavelength` | **Sí** (escritura reversible, láser de 532 atenuado) | **Sí**, y BANCO-25 hecho |
| BANCO-41 | `SetEMCCDGain` durante una adquisición | tapa puesta, ganancia 0: con Live activo pedir `SetEMCCDGain(0)`; se espera `DRV_ACQUIRING` [SDK p.270] | No (sin luz, pide 0) | No |
| BANCO-42 | Umbral especular por red | lámpara al mínimo, EM 0, 1 ms: con 150 l/mm λc = 70, 60, 55, 50, 45 nm; con 1200 l/mm λc = 8, 7, 6, 5 nm; anotar dónde aparece la imagen especular. Se espera ≈ W/2 (51.5 y 5.8 nm) [I] | **Sí** (torreta) | **Sí** |
| BANCO-43 | Exposición y ranura seguras en orden cero; píxel de referencia | láseres cerrados, EM 0, lámpara al mínimo: 1 ms en orden cero y en espejo con cada red; cuentas por ms y centro de la imagen de la ranura | **Sí** (torreta) | **Sí** |
| BANCO-44 | Un cuadro nuevo por ventana, sin ceros | Step & Glue corregido con la fuga de 532 en un rango que la ponga en ventanas conocidas; contador `GetTotalNumberImagesAcquired` y marca de tiempo por ventana; dos cuadros oscuros seguidos no son idénticos bit a bit | **Sí** (torreta; 532 atenuado) | **Sí** |
| BANCO-45 | Arranque sin escrituras ni mock | (a) 3.0 corregido en hardware con el log de llamadas: ninguna función de §1.4; los valores mostrados coinciden con BANCO-25 y dicen "leído". (b) Con Solis abierto: "Andor no conectada", adquisiciones bloqueadas, ningún espectro | No (el arranque sólo configura la cámara y enfría) | No, pero **después** de BANCO-25 |
| BANCO-46 | Stop y E-STOP bajo espera larga | Step & Glue con 10 s por ventana; Stop a los 2 s; en otra corrida E-STOP. Aborto en ≤ 0.25 s + lectura; E-STOP deja `GetEMCCDGain` = 0 | **Sí** (torreta, lámpara) | **Sí** |
| BANCO-47 | Un solo camino al orden cero | λc = 30 nm con 150 l/mm, combo "Espejo", Step & Glue con un centro bajo el umbral, `Ctrl+0`, y `set_emccd_gain(50)` en condición especular: todo pasa por el servicio (log) y la ganancia queda en 0 | **Sí** (torreta) | **Sí** (EM 0, láseres cerrados) |
| BANCO-48 | Repetibilidad e histéresis de la torreta | 10 ciclos 532 → 600 → 532 y 150 → 1200 → 150 desde abajo; 5 desde abajo contra 5 desde arriba | **Sí** | **Sí** (532 atenuado) |
| BANCO-49 | "La línea que camina" | con la fuga de 532 (no hay lámpara de calibración, R4-A 8): λc = 532 − 0.35 W, 532, 532 + 0.35 W por red; la línea tiene que caer en la misma λ ± 1 px; comparar el eje de `GetCalibration` con el cúbico | **Sí** | **Sí** (532 atenuado) |
| BANCO-50 | Linealidad y saturación en la calibración | exposiciones T, 2T, 4T con la línea en 15-50 % del ADC (16 383) | **Sí** (532 atenuado) | **Sí** |
| BANCO-51 | Deriva del eje λ en la sesión | la línea de 532 cada 5 min durante 2 h desde el encendido, con la temperatura de la sala y del CCD | **Sí** (532 atenuado) | **Sí** |
| BANCO-52 | Línea contra ancho de ranura | centroide del 532 con 10, 25, 50, 100 y 200 µm; se espera ≤ 0.5 px porque la ranura es bilateral (R4-A 8) | **Sí** (ranura) | **Sí** |
| BANCO-53 | Uniones de Step & Glue con la lámpara | 500-900 nm al 20 % y al 10 % con 150 l/mm, ventana repetida al final y barrido invertido; 800-900 nm con 1200 l/mm | **Sí** | **Sí** |
| BANCO-54 | Tiempo de reenfriado a −60 °C después de "Reconectar cámara", que ejecuta `ShutDown` y apaga el enfriador (R4-B-7) | Con la cámara estable a −60 °C, pulsar Reconectar y registrar `GetTemperature` cada 10 s hasta `DRV_TEMP_STABILIZED`, con la temperatura de la sala | Sí (reinicia la cámara; sin luz) | No |

**Ampliaciones de ítems existentes:**
- **BANCO-09:** agregar `ShamrockShutterIsPresent`, y averiguar si el `SetShutter` de la cámara también mueve el obturador del espectrógrafo. El legado dice "abre shutter camera y shamrock".
- **BANCO-22:** la λ nominal del láser de 532 y su tolerancia.
- **BANCO-23:**
  - las versiones de `atmcd64d.dll`, `ShamrockCIF.dll` y `atshamrock.dll`, y la de pylablib si está instalado;
  - que exista `C:\Program Files\Andor SOLIS\SPECTROG.INI`, que usan el legado y 3.0 para inicializar el Shamrock.
  - Las DLL del repo son 2.104.33065.0 (cámara) y 2.103.30023.0 (Shamrock), idénticas a las de la carpeta del legado (DEC-040). Si las del banco difieren, avisar.
  - **Leído el 2026-09-28:**
    - pylablib **1.4.3** en `C:\Users\PRINTING\Envs\envspectrum` (Python 3.11);
    - cámara: `C:\Program Files\Andor SOLIS\atmcd64d_legacy.dll` (falta anotar su versión);
    - Shamrock: `C:\Users\PRINTING\Desktop\PySpectrum\libs\Windows\64\` (ShamrockCIF + atshamrock).
- **Resultado:** —

---

### ☐ BANCO-55 — Driver propio de la cámara contra pylablib
- **Verifica:** que el driver propio de 3.0 (`andor_ccd_driver.py` + `single_exposure`) se comporta como pylablib, que es la referencia probada en el banco porque el legado la usa (R4-E, `pyspectrum_A_ronda4/ANALISIS_pylablib_vs_DLL.md`).
- **Requisitos:**
  - Solis cerrado, láseres cerrados, tapa puesta;
  - BANCO-25 hecho;
  - PySpectrum 3.0 en condiciones de abrirse contra el equipo (pasos del bloque A).
- **Procedimiento:**
  1. **Con el legado abierto:** anotar la versión de pylablib (`pylablib.__version__`, BANCO-23). Desde su consola, con la cámara ya conectada:
     - leer `get_fan_mode()`, `get_vsspeed()`, `get_amp_mode()`, `get_EMCCD_gain()`, `get_temperature()` y `get_read_mode()`;
     - tomar 10 cuadros de 0.1 s en modo Image con ganancia 0, con `snap()` o con `start_acquisition` / `wait_for_frame` / `read_oldest_image`;
     - guardar los cuadros y anotar el tiempo por cuadro.
  2. **Cerrar el legado** y abrir PySpectrum 3.0. Tomar los mismos 10 cuadros con `single_exposure`: Image (1002 × 1004), 0.1 s, ganancia 0, la misma velocidad vertical y el mismo amplificador. Repetir en FVB (1004).
  3. **Comparar:**
     - tamaño y orientación del cuadro;
     - nivel de bias (mediana);
     - ruido de lectura (desviación entre cuadros consecutivos);
     - exposición real (`GetAcquisitionTimings`);
     - que dos cuadros consecutivos nunca sean idénticos;
     - tiempo por cuadro.
- **Aceptación:** mismo tamaño y orientación; bias y ruido que coincidan dentro de la dispersión entre cuadros; exposición real igual; ningún cuadro repetido ni de ceros.
- **Si falla:** anotar la diferencia. Si no se sabe corregir en el driver propio, se evalúa pasar la cámara a pylablib (opción C del análisis) con esa diferencia ya identificada.
- **Resultado:** fecha — / versión de pylablib — / valores —

### ◐ BANCO-56 — Orientación de la imagen del Andor en orden cero frente a la cámara
- **Observación del investigador (2026-09-28):** la imagen en la cámara y la del espectrómetro Andor
  se ven **iguales en Y (vertical)** e **invertidas en X (horizontal)**.
- **Contradice al código:** `config.py` tiene `ANDOR_FLIP_Y_IMAGE = True`, con el comentario "corrige
  telescopio Czerny-Turner/Flipper" y sin fuente, y `ANDOR_FLIP_X_IMAGE = False`. Es decir, lo contrario
  de lo observado.
  - Ese par sólo lo usa `pyspectrum/modules/camera_andor.py`, que la ventana de 3.0 no instancia.
    `calibration_dock.py` lo importa sin usarlo.
  - El visor de Exploración no invierte nada. Sólo `invertY(True)`, que pone la fila 0 del sensor
    arriba, como una imagen.
- **Precisado (investigador, R4-G):** la Canon, en la app de cámara de PyPrinting 3.0, contra el Andor
  en **Solis**, en orden cero.
- **Falta:**
  - ~~saber si Solis invierte la imagen al mostrarla~~: **no la invierte** (investigador, 2026-09-28).
    El cuadro del Andor, tal como lo entrega la cámara, está invertido en X respecto de la Canon;
  - ver el mismo cuadro en el visor de Exploración de PySpectrum 3.0 cuando se abra contra el equipo
    (bloque A completo). El visor de 3.0 muestra el arreglo crudo con la fila 0 arriba. Hasta esa
    comparación no se cambia ninguna inversión por defecto.
- **Importa para:**
  - que el espejo rápido sirva para ubicarse: moverse hacia la derecha en la cámara tiene que verse
    hacia el mismo lado en el visor, o el visor tiene que avisar que está invertido;
  - todo mapeo entre píxeles del Andor y coordenadas de la platina o de la cámara;
  - el sentido del eje λ en primer orden, que se toma del Shamrock (`GetCalibration`) y no depende de
    la paridad de la imagen; conviene anotar en el mismo cuadro hacia qué lado crece λ.
- **Procedimiento sugerido:** con la lámpara y una muestra con una marca asimétrica (una letra o un
  borde de cubreobjetos), en orden cero, mover la platina +X y +Y y anotar hacia dónde se mueve la
  marca en la cámara y en el visor del Andor. Anotar también el programa y la red.

### ☐ BANCO-57 — Cierre de PySpectrum 3.0 con el satélite PyPrinting abierto
- **Qué se prueba:** el orden de cierre del paso 13 sobre el equipo. En el simulador ya se verificó que no se cuelga, que pregunta una vez y que la platina termina en `PI_HOME_POS`.
- **Procedimiento (sin láser):**
  1. Abrir PySpectrum 3.0 y anotar la posición de la platina después del home.
  2. Mover la platina a otra posición y abrir PyPrinting desde el menú: la platina **no** debe moverse.
  3. Cerrar PyPrinting solo: la platina **no** debe moverse, y los obturadores de PySpectrum deben seguir operables. Repetir 2 y 3 con el contrapropagante (R4-J).
  4. Volver a abrir PyPrinting y cerrar PySpectrum. Anotar:
     - el texto de la pregunta;
     - el tiempo total del cierre;
     - la posición final de la platina (se espera 50, 50, 10);
     - el espejo de detección: tiene que quedar abajo (R4-J);
     - si apareció el aviso final.
  5. Abrir Solis o el PySpectrum legado: la cámara y el Shamrock tienen que estar libres (`ShamrockClose` y `ShutDown`, BANCO-23). Anotar la temperatura del CCD al abrir: el enfriador vuelve a ambiente.
  6. Abrir PySpectrum 3.0 otra vez: al conectar, la platina **no** debe moverse, porque ya está en home.
- **Aceptación:** ningún movimiento de la platina fuera de los pasos 4 y 6; el cierre termina sin aviso; los equipos quedan libres.
- **Resultado:** fecha — / tiempo de cierre — / posición final — / observaciones —

### ☐ BANCO-58 — Primera calibración automática de λ en SÓLO MEDIR ⚠️ abre el 532 (atenuado), con aprobación
- **Qué se prueba:** la rutina del paso 14 contra el equipo. No escribe ningún offset; el 532 se abre sólo durante los cuadros.
- **Antes:**
  1. Controles negativos:
     - con el obturador del 532 cerrado desde el panel, la rutina tiene que terminar en "No se ve la línea" y no calibrar ruido;
     - lo mismo con el espejo de detección arriba;
     - con la ganancia EM distinta de 0, el preflight no la deja arrancar.
  2. Anotar en Solis los offsets de las dos redes (control cruzado).
- **Corrida:**
  - con el notch puesto y el espejo abajo, correr las dos redes con los valores por defecto;
  - anotar la duración total (tope de 10 min), el SNR de la línea con 0.10 s y si hubo saturación;
  - si con 0.10 s la línea queda débil (SNR < 20) o satura, anotarlo: la exposición fija es de R4-D-4.
- **Repetibilidad:** con la red de 150, repetir con 25 llegadas mínimas (Avanzado) para medir s_rep por red (#2 del presupuesto).
- **Si el investigador lo aprueba (P3):** la misma corrida con "532 atenuado, sin notch", para comparar el centro con el de la fuga (#5).
- **Aceptación:** el 532 queda cerrado al terminar; no cambia ningún offset (relectura en Solis igual a la de antes); cada red deja su registro PROPOSED y su HDF5.
- **Resultado:** fecha — / r y c_sw por red — / s_rep — / duración — / veredictos — / observaciones —

### ☐ BANCO-59 — Rutinas de grilla de 3.0: espejo, potencia y láser por fase ⚠️ láser, con aprobación
- **Qué se prueba:** AND-1 en el equipo, empezando por una grilla de 1 × 2 nodos sobre una zona sin muestra valiosa.
- **Espejo (R4-K, P2):** con el espejo confirmado arriba, correr una luminiscencia de 1 nodo. Verificar que la luz llega al espectrómetro cuando la rutina lo baja, y que al terminar vuelve arriba.
  - **Crecimiento:** confirmar que el espectro se ve con el espejo **abajo**, como decidió el investigador. El legado lo ponía arriba (`Growth_ps.py:788`). Si con el espejo abajo no hay espectro, anotarlo y no seguir.
- **Potencia (P3):** anotar el pulso de baja antes del centrado y el de alta antes del crecimiento o la impresión, y medir la potencia en la muestra en cada caso.
- **Centrado:** el centrado confocal ahora abre el láser, en potencia baja. Confirmar que la imagen del fotodiodo muestra la partícula.
- **Tiempos:** anotar cuánto tarda un nodo, contando los asentamientos del legado (0.5 s, 2 s en dímeros, 0.15 s del espejo y 0.5 s del láser).
- **Mapa hiperespectral:** un mapa de 3 × 3 con la exposición mínima útil. Comprobar que cada píxel es distinto y que el HDF5 queda en la carpeta de trabajo.
- **Resultado:** fecha — / observaciones —

### ☐ BANCO-32 — Corte de impresión real a baja potencia ⚠️ requiere láser y aprobación
- **Procedimiento**: una grilla de 5×5 con campo oscuro grabando, con un control sin coloide.
- **Aceptación**: cada captura corta en el primer escalón y no hay dobletes.
- **Resultado**: —

### ☐ BANCO-33 — Deriva del sistema ⚠️ requiere láser y aprobación
- **Verifica**: el valor provisorio de 30 nm/min (Martínez, CIBION) que usa `lab-invariants` §6.
- **Procedimiento**: ≥ 1 h después de termalizar, recentrar una partícula de referencia por
  escaneo confocal a intervalos regulares y registrar la posición.
- **Resultado**: —
