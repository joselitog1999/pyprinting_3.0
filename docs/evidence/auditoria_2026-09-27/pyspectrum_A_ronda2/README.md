# PySpectrum 3.0, bloque A: Ronda 2 (diseño técnico)

**Fecha:** 2026-09-28.
**Panel:**
- `software-architect` (`software_architect.md`): CONCURRENCY_RISK para el código actual; el diseño llega a CLEAN_ARCHITECTURE.
- `instrumentation` (`instrumentation.md`): TIMING_HAZARD para el diseño; el código actual sigue en SAFETY_VIOLATION.
- `metrology` (`metrology.md`): INADEQUATE_ERROR_BUDGET. El algoritmo funciona en la simulación, pero falta medir términos de la incertidumbre.

**Base:** la Ronda 1 (`../pyspectrum_A_ronda1/README.md`) y las respuestas R4 y R4-A (`../RESPUESTAS_INVESTIGADOR.md`).

## 1. Hallazgos nuevos, verificados por el orquestador

- **Cerrar el satélite PyPrinting desarma a PySpectrum** (`app.py:576-602`, `config.py:461-475`). Cierra todas las tareas de la NI-DAQ, pulsa el espejo, cierra los obturadores, mueve la platina a (0, 0, 0) y la desconecta.
  - Hasta corregirlo: **no cerrar la ventana de PyPrinting con PySpectrum abierto.**
- **`GetTemperature`** devuelve el estado `DRV_TEMP_*` y nunca `DRV_SUCCESS` (SDK p. 200). Por eso `is_hardware_alive()` interpreta mal el resultado.
- **Getters que no existen.** El SDK2 v2.104 no trae `GetReadMode`, `GetAcquisitionMode`, `GetFanMode` ni `GetEMGainMode`. Para esos cuatro parámetros la GUI tiene que mostrar "enviado", no "leído".

## 2. Hallazgos de los agentes, no verificados uno por uno

- **Cierre y reinicio:**
  - cerrar PySpectrum con el satélite abierto produce un deadlock determinista;
  - el tablero de hardware reinicia la cámara y el Shamrock, deja los backends con instancias cerradas y apaga el enfriador;
  - el cierre nunca llama a `ShutDown` ni a `ShamrockClose`.
- **Escrituras y ganancia:**
  - "Cargar" y "Recargar" del archivo de calibración también escriben los offsets;
  - la E-STOP no baja la ganancia EM.
- **Satélite:** abrirlo llama a `pi.connect()`, que hace home y libera el interlock de la platina.
- **Escaneo lineal:** tiene su propia copia del bucle de Step & Glue, sin adquisición real y con otro método de cosido.
- **SDK (instrumentación):**
  - según las notas de versión (p. 16), **escribir un offset puede mover la torreta**, así que se trata como una orden de movimiento;
  - el pre-amp tiene que fijarse antes de adquirir;
  - `WaitForAcquisitionTimeOut` devuelve lo mismo por timeout que por `CancelWait`.
- **Legado:** arrancaba el enfriador a +10 °C, según pylablib (fuente secundaria).
- **Metrología:**
  - `fit_peak_advanced` suma al centro una "incertidumbre de ranura" de ≈ 3.6 px, y cuenta el pixelado dos veces;
  - `compute_wavelength_uncertainty` usa un default de 0.08 nm sin fuente;
  - `filter_despike_median` degrada una línea angosta.

## 3. Diseño propuesto

- **`DeviceRegistry`:** dueño único de los drivers. Sin simulador fuera de SAFE_MODE: un equipo que no inicializa es "no conectado", con su motivo.
- **Estado leído.** `SpectrometerStateService`/`SpectrometerSnapshot` es la única fuente de lo que muestra la GUI, y cada valor dice si fue leído, enviado o falló.
- **Arranque.** `apply_operating_baseline` fija el estado operativo con relectura:
  - modo de lectura y de adquisición;
  - velocidad vertical del legado y pre-amp;
  - ventilador low, con opción high;
  - enfriador a −60 °C;
  - ganancia EM 0;
  - entrada lateral.

  **No escribe ninguna constante de calibración.**
- **Orden cero.** `ZeroOrderService` es un único camino, sin diálogo y que falla cerrado:
  - aborta la adquisición;
  - fija la ganancia EM en 0 y la confirma;
  - acota la exposición.

  Además, `SpecularInterlock` vive dentro de los dos drivers:
  - con la red en condición especular (|λc| < W/2 + 10 %, es decir 56.7 nm con la red de 150 y 6.4 nm con la de 1200, o en posición espejo), rechaza una ganancia EM > 0;
  - el Shamrock no va a un destino especular sin ganancia 0 confirmada.

  Los movimientos del espectrógrafo corren en su propio hilo.
- **Exposición.** `single_exposure` es la única, compartida por la calibración y Step & Glue:
  - `StartAcquisition`;
  - espera en tramos de 250 ms, decidida con `GetStatus`;
  - lectura de tamaño exacto;
  - cancelación con `AbortAcquisition`.

  Nunca devuelve ceros.
- **Calibración:**
  - `CalibrationRepository` es un archivo local, fuera de git, en JSONL, al que sólo se agregan entradas;
  - `OffsetWriteTransaction` es la única que escribe offsets: lee, muestra la diferencia, pide dos confirmaciones, respalda, escribe y relee;
  - la transacción se anula si el equipo cambió entre la lectura y la escritura;
  - topes provisorios: 2000 pasos absolutos y 300 por escritura;
  - sólo escribe las redes 1 y 2; el detector no se toca.
- **Calibración automática** (metrología):
  - mide el residuo entre el pico y la posición de 532 que da el eje del SDK;
  - estima la pendiente px/paso con una sonda de 4 pasos, que se duplica hasta 64 si hace falta;
  - ajusta una gaussiana con fondo lineal, en una ventana de ±3 FWHM;
  - rechaza los rayos cósmicos comparando cuadros;
  - converge en 2 a 4 escrituras y agrega llegadas desde abajo hasta la incertidumbre objetivo, con tope en 25;
  - aplica criterios K1 a K7, PROVISORIOS.

  En la simulación, el sesgo es ≤ 0.02 px. La incertidumbre la domina la repetibilidad de la torreta (10 pm ≈ 0.87 px por llegada con la red de 1200). **Sin lámpara, la exactitud absoluta es la de la λ del láser, que hoy no tiene valor.**
- **Step & Glue.** `StepGlueEngine` y `StepGlueWorker` corren en su propio hilo, con una exposición por ventana, y los usa también el escaneo lineal.
  - Chequea cada retorno.
  - Reabre el obturador del Shamrock.
  - Avisa si el espejo no está abajo, lo que depende de C-08.
  - Sólo late si abrió él mismo un obturador.
- **Satélite PyPrinting como huésped:** no conecta ni desconecta la platina, no cierra las tareas DAQ, no pulsa el espejo y no toca el perfil. `ShutdownCoordinator` ordena el cierre, y ninguna espera es infinita.

Los diagramas duales de arranque, orden cero, calibración y Step & Glue están en `software_architect.md` §5. El inventario de firmas, en §6 de ese archivo y en `instrumentation.md` §1-§5. Los tests, en `software_architect.md` §7 y `metrology.md` §5.

## 4. Orden de implementación (14 pasos atómicos, cada uno con su test que falla primero)

| Paso | Qué incluye | ¿GUI (Ronda 3)? |
|---|---|---|
| 1 | Dobles del SDK y test de "no escribe al arrancar" | No |
| 2 | Arranque sin escrituras de calibración. El archivo inventado se archiva | No |
| 3 | Sin simulador fuera de SAFE_MODE | Mínima ("no conectado") |
| 4 | `DeviceRegistry`; el tablero deja de reiniciar | No |
| 5 | Métodos de driver con `argtypes`: C-05, C-06 (`SetAutoSlitWidth`) y C-07 | No |
| 6 | `single_exposure` | No |
| 7 | Orden cero: interlock, motor, worker y servicio. Se borran los caminos viejos | Sí |
| 8 | Estado operativo base y servicio de estado | Sí (panel izquierdo) |
| 9 | Repositorio de calibraciones y diff al arrancar | No |
| 10 | Transacción de escritura de offsets | Sí |
| 11 | Step & Glue en worker | Sí |
| 12 | Escaneo lineal sobre el mismo motor | Sí |
| 13 | Satélite huésped y orden de cierre | No |
| 14 | Calibración automática: primero sólo mide; la escritura se habilita tras BANCO-40 | Sí |

Precondiciones de banco:
- el Grupo E (BANCO-15 a BANCO-19) antes del bloque A;
- BANCO-25 antes del primer arranque contra el equipo.

## 5. Preguntas para el investigador

Ver el mensaje del 2026-09-28. Las respuestas se registran en `RESPUESTAS_INVESTIGADOR.md`.

## 6. Pruebas de banco

`instrumentation.md` §8 consolida BANCO-36 a BANCO-53 y amplía BANCO-09, 22 y 23. Unifica los A1-A9 del experimentalista, los P0-P11 del abogado del diablo y los BANCO-A1 a A3 del arquitecto. Se incorporan a `PRUEBAS_BANCO_PENDIENTES.md` al aprobarse esta ronda.
