# PySpectrum 3.0, bloque A ("primer arranque seguro") — Ronda 1, instrumentación

- **Fecha:** 2026-09-28. **Agente:** `instrumentation`. **Alcance:** orden cero, calibración (offsets y eje λ), Step & Glue e inicialización de la Andor iXon3 885 y del Shamrock 500i.
- **Método:** sólo lectura de código, del legado, de las hojas de datos y del manual del SDK. No se ejecutó nada contra hardware y no se escribió código de producción.
- **Graphify:** se consultó primero (`graphify query` sobre orden cero y calibración, Step & Glue, inicialización y calibración con 532; `graphify explain PySpectrumWindow`). Después se leyeron sólo los archivos señalados.

## Rótulos de evidencia

| Rótulo | Significado |
| :--- | :--- |
| **[V-código]** | Verificado leyendo el código actual (archivo:línea). |
| **[V-legado]** | Verificado en la copia local del legado. Vale para comportamiento y algoritmos. Su cableado DAQ puede estar viejo (memoria del proyecto, 2026-09-27). |
| **[V-SDK p.N]** | Andor SDK2 User's Guide v2.104 (`docs/bibliografia/Software Development Kit.pdf`), página N del PDF. Es el SDK de **cámaras**. La versión instalada en el banco puede ser otra (BANCO-23). |
| **[V-DS-iXon p.N]** / **[V-DS-SR500 p.N]** | Hojas de datos en `docs/bibliografia/`. |
| **[2ª-Shamrock]** | Docstring del wrapper legado `scratch/pyspectrum-legacy/Shamrock_ps.py`. Es evidencia **secundaria**: no hay manual del Shamrock SDK en la bibliografía. |
| **[REQ-manual-Shamrock]** | La conclusión depende del manual del Shamrock SDK, que no tenemos. |
| **[I]** | Inferencia mía, con el razonamiento a la vista. |
| **EXPERIMENTAL** | Dato del investigador no publicado. |

DLL incluidas en el repo (propiedades del archivo, sólo lectura) [V-código]:

| DLL | Versión | Fecha |
| :--- | :--- | :--- |
| `pyspectrum/drivers/libs/atmcd64d.dll` | 2.104.33065.0 | 2021-08-31 |
| `pyspectrum/drivers/libs/Windows/64/ShamrockCIF.dll` y `atshamrock.dll` | 2.103.30023.0 | 2018-11-29 |

El legado cargaba otra copia, `C:/Users/PRINTING/Desktop/PySpectrum/libs/Windows/64/ShamrockCIF.dll` (`Shamrock_ps.py:20`), de versión desconocida.

---

## 1. Qué hace hoy 3.0 contra el hardware real, y qué hacía el legado

### 1.1 Secuencia de arranque de PySpectrum 3.0 [V-código]

Es la secuencia que se ejecutaría con `SAFE_MODE = False` al abrir la ventana.

1. **Cámara** (`window.py:471` → `andor_ccd_driver.py:731-751`):
   - carga `libs/atmcd64d.dll` (`:375-389`);
   - llama a `Initialize(b"")` (`:396`) y a `SetCoolerMode(0)` (`:400`).
   - **No hace nada más.** No enciende el enfriador ni fija un setpoint. No llama a `SetAcquisitionMode`, `SetReadMode`, `SetVSSpeed`, `SetFanMode`, `SetShutter`, `SetEMGainMode` ni `SetHSSpeed`/`SetPreAmpGain`: un grep de `SetAcquisitionMode|SetFanMode|SetVSSpeed|SetEMGainMode|WaitForAcquisition` en `pyspectrum/` y `core/` no da ninguna coincidencia.
   - Si `Initialize` falla, **devuelve `_MockAndorCCD` en silencio** (`:748-750`), también fuera de SAFE_MODE.
2. **Espectrógrafo** (`window.py:472` → `shamrock_driver.py:768-792`):
   - carga `ShamrockCIF.dll`;
   - llama a `ShamrockInitialize` con el primer `SPECTROG.INI` que encuentra (`:396-409`);
   - si falla, **cae en silencio a `_MockShamrock`** (`:785-787`);
   - si inicializa, `configure_detector_geometry()` escribe `SetNumberPixels(1004)` y `SetPixelWidth(8.0)` y los relee (`:85-107`, `:612-623`).
3. **Panel izquierdo** (`left_hardware_panel.py:55-63`, `:227-243`):
   - llena los combos de pre-amp y HS speed sólo con getters, con las señales bloqueadas, así que no escribe nada;
   - arranca un `QTimer` de 1 s que llama a `GetTemperature`, `ShamrockGetWavelength` y `ShamrockGetGrating` (`:331-343`).
   - Muestra valores que **nunca se enviaron al equipo**: "Enfriador: ON" (`:103-106`), −65 °C (`:99`), exposición 0.05 s (`:144`). Después de `Initialize` el enfriador real sigue en el estado por defecto del SDK.
4. **Platina** (`window.py:582-586`): `hardware_manager.set_profile("pyspectrum")` y **`pi.connect()`**.
   - Si la platina ya está conectada y sana, `connect()` vuelve sin moverla (`config.py:374-379`).
   - Si está desconectada, por ejemplo por el interlock "Platina PI" que dejó una falla de comunicación en PyPrinting en el mismo proceso, `connect()` **cierra los obturadores, manda la platina a home y levanta el interlock** (`config.py:414-448`). Abrir PySpectrum es una acción del operador, pero no la de "reconectar la platina". Esto choca con DEC-036 ("sólo el operador reconecta").
   - Además, la espera del home sale a los 3 s sin error y da la platina por conectada aunque no haya llegado (`config.py:421-425`).
5. **Dock de Calibraciones** (`window.py:623` → `calibration_dock.py:607-635`). Es el defecto C-04, re-verificado:
   - el constructor carga `pyspectrum/calibration/pyspectrum_calibration_last.txt` y **escribe al Shamrock**, sin preguntar ni releer, `SetGratingOffset` para las redes 1 = 12, 2 = −35 y 3 = 0, `SetDetectorOffset(5)` y `SetSlitZeroPosition(1, 0)` (`:1010-1017`). El `except: pass` descarta tanto las excepciones como los códigos de retorno;
   - recién **después**, `make_connection` → `read_initial_values()` (`:680-710`) intenta leer el equipo. **Los valores originales nunca se leen antes de pisarlos**, así que 3.0 no guarda ningún respaldo;
   - `read_initial_values` empieza con `ShamrockGetSlit(DEVICE, INPUT_SLIT_PORT)`. La firma real es `(device, float* width)` [2ª-Shamrock, `Shamrock_ps.py:1519-1548`], pero el driver pasa 3 argumentos sin `argtypes` (`shamrock_driver.py:488-494`). La DLL recibe `1` como puntero y escribe en la dirección 0x1. Inferencia [I]: ctypes/SEH lo convierte en `OSError` ("access violation") y el `except` genérico de `:709` aborta el resto de la lectura (offsets, detector, coeficientes).
   - [I, no verificable sin hardware] Si la violación de acceso ocurre con un mutex interno de `ShamrockCIF` tomado, las llamadas siguientes al Shamrock podrían colgarse.
6. El `SpectrumBackend` oculto ejecuta `update_calibration()` al conectarse: sólo getters (`spectrum_control.py:205-217`, `:284-293`).

**Limitación:** no revisé uno por uno los constructores de las demás rutinas (Raman, confocal, luminiscencia, crecimiento, dímeros, escaneo lineal) en busca de escrituras al hardware. Queda como tarea para la Ronda 2.

### 1.2 Arranque del legado [V-legado]

1. **Cámara**: `AndorSDK2Camera(temperature=10, fan_mode="low")` (`PySpectrum_UNSAM.py:785`), a través de pylablib.
   - `set_camera_parameters` (`Camera_ps.py:566-607`) configura `setup_image_mode(0,1002,0,1002)`, pre-amp índice 0, `set_EMCCD_gain(0)` y `set_vsspeed(2)` ("1.9 µs"). No verifiqué en qué momento la llama el legado.
2. **Espectrógrafo**: `ShamrockInitialize(inipath)` (`:791`), después de la cámara, igual que el orden de 3.0.
3. **Backend de espectro** (`Spectrum_ps.py:157-166`):
   - `SetNumberPixels(1002)` y `SetPixelWidth(8)`. `NumberofPixel = 1002` sale de `Instrument_Shamrock_ps.py:23`;
   - fuerza la entrada *Side* y la salida *Direct* con `ShamrockSetFlipperMirror`;
   - **mueve la torreta a la red de 150 l/mm en cada arranque.**
4. **Offsets: nunca se escriben solos.** Sólo el botón "Set Offsets" los escribe (`Spectrum_ps.py:121-125`, `:210-220`), a la red activa y con el valor de las casillas (textos iniciales 100 y 0).

### 1.3 Orden cero

**3.0 [V-código].** Hay **seis** caminos. Re-verifiqué los tres de C-03 y encontré dos más:

| # | Camino | Protección |
| :-- | :--- | :--- |
| a | Diálogo `ZeroOrderSafetyDialog` (`zero_order_dialog.py:158-169`), desde el botón del panel izquierdo (`left_hardware_panel.py:323-326`) y Ctrl+0 (`window.py:550-553`) | Parcial; ver defectos abajo |
| b | `spectrum_control.py:272-280`: salvaguarda automática (`:249-270`: EM a 0 y cierre de obturadores) | No verifica nada; panel oculto |
| c | `calibration_dock.py:712-718`: `ShamrockGotoZeroOrder` directo | Ninguna |
| d | Panel izquierdo, λ central 0-2000 nm y "Ir a λ" (`left_hardware_panel.py:204-214`, `:319-321`) | Ninguna |
| e | **Nuevo:** combo de red del panel izquierdo, opción "Espejo (Mirror)", que refleja especularmente como el orden cero (`:170-175`, `:309-312`) | Ninguna; sólo `spectrum_control` protege el espejo (`:219-223`) |
| f | **Nuevo, por física:** cualquier λ central con \|λ_c\| menor que media ventana. Con 150 l/mm la ventana mide ≈ 103 nm, así que λ_c = 40 nm pone el orden cero **sobre el chip** (el detector cubre −11 a 91 nm). Con 1200 l/mm el umbral es ≈ 5.8 nm | [I, geometría del eje: λ(píxel) ≈ λ_c ± W/2]. El umbral `wl <= 0.05` de `spectrum_control.py:228` no lo cubre |

**Defectos del diálogo (a)** [V-código + V-SDK]:

- `SetEMCCDGain` devuelve `DRV_ACQUIRING` si hay una adquisición en curso [V-SDK p.270]. Si Live de Exploración o Live Raman están corriendo, `_apply_gain_off()` falla **en silencio**: no mira el retorno (`zero_order_dialog.py:130-132`, `andor_ccd_driver.py:469-483`). La red va a orden cero con la ganancia alta. Lo mismo pasa con `SetExposureTime` [V-SDK p.272].
- `_read_em_gain` con el driver real toma `val[1]` sin mirar `val[0]`. Una lectura fallida devuelve `(DRV_NOT_INITIALIZED, 0)` (`andor_ccd_driver.py:485-494`) y el diálogo muestra "🟢 Ganancia EM: 0x (segura)".
- `close_all_shutters()` devuelve si el cierre se confirmó, pero su retorno se ignora (`zero_order_dialog.py:127-128`). Según DEC-036, un cierre no confirmado equivale a abierto.
- Existe "Ignorar y Continuar (Override Experto)" (`:116-119`, `:150-156`).
- La E-STOP de PySpectrum cierra obturadores y aborta la cámara, pero no baja la ganancia EM (`hardware_session.py:134-158`).

**Legado [V-legado]:** `Spectrum_ps.py:222-226` llama directo a `ShamrockGotoZeroOrder`, sin diálogo. Según el investigador (R2-11), la ganancia EM no se bajaba porque el orden cero casi no se usaba.

**Física del riesgo** [V-SDK p.270, V-DS-iXon p.1, I]:

- El SDK advierte que ganancias altas con más de "tens of photons per pixel" aceleran el envejecimiento del sensor.
- La hoja de datos del 885 afirma "negligible EM gain ageing" y "non-ageing" (p.1).
- Conclusión [I]: en este cabezal, el daño irreversible por envejecimiento es menos probable que en un EMCCD genérico. El riesgo real inmediato es saturar el registro de multiplicación. Sin ganancia EM, la reflexión especular satura y produce blooming, que no daña el CCD salvo con flujos focalizados muy altos, que no cuantifiqué. Mantengo la severidad **alta** por la decisión del investigador y porque un daño sería irreversible.

### 1.4 Calibración (offsets y eje λ)

**3.0 [V-código]:**

- **Setters directos:** `set_grating_offset`, `set_detector_offset` y `set_slit_zero_position` escriben sin diálogo, sin releer y sin guardar el valor previo (`calibration_dock.py:737-779`).
- **Archivo de calibración:** `save_calibration_to_txt` (`:1025-1109`) escribe siempre "13.0 µm", "1002x1002" y `estado = CALIBRADO_VALIDADO`, con la hora actual como "fecha_calibracion". Lo llaman `save_slit_pixel` y `auto_calibrate_slit` (`:788-827`), así que cualquier ajuste de ranura vuelve a sellar como "validados" los offsets inventados. En el próximo arranque, esos offsets se escriben al equipo.
- **`auto_calibrate_slit`** ajusta una gaussiana sobre `get_most_recent_image()` sin iniciar una adquisición (`:797-827`). En hardware ese cuadro sale en ceros (DRV_NO_NEW_DATA, [V-SDK p.180]) o es viejo.
- **Dos fuentes del eje λ, que pueden no coincidir:**

  | Fuente | Dónde se usa |
  | :--- | :--- |
  | `ShamrockGetCalibration(1004)` | El legado siempre (`Spectrum_ps.py:234`, `StepandGlue_ps.py:628`). En 3.0: luminiscencia, crecimiento, dímeros, hiperespectral, verificación con agua |
  | Polinomio de `ShamrockGetPixelCalibrationCoefficients` evaluado con p = 0…N−1 (`shamrock_driver.py:754-762`) | En 3.0: Step & Glue (`step_and_glue.py:341-344`, `:512-515`, `:574-577`), escaneo lineal (`linescan_spectroscopy.py:659-662`), Raman y control de espectro con `SHAMROCK_USE_FACTORY_EEPROM = True` (`config.py:110`) |

  - Los comentarios de 3.0 presentan esos coeficientes como la "calibración de fábrica certificada de la EEPROM". El docstring del SDK dice sólo "Gets pixel calibration coefficients" y remite a `ShamrockSetGratingOffset` y `ShamrockGetCalibration` [2ª-Shamrock, `Shamrock_ps.py:1351-1390`]. No dice que vengan de la EEPROM, y la referencia a los offsets sugiere que dependen del estado actual.
  - No sabemos si el polinomio espera el píxel desde 0 o desde 1, ni para qué número de píxeles vale [REQ-manual-Shamrock].
  - Una nota de versión del SDK dice: "Fixed issue with Shamrock SDK if the focal plane tilt was 0 then all calibration coefficients data was 0" [V-SDK p.14].
- **`get_calibration`** devuelve un eje falso `linspace(400, 700)` junto con un código de error cuando falla (`shamrock_driver.py:625-635`). Casi todos los consumidores ignoran el código; `measured_window_nm` es la excepción.
- **No encontré una rutina de calibración con 532 nm + filtro de densidad en PySpectrum 3.0** (consulta de graphify; lo único parecido es `Laser532Window`, en `modules/camera.py`, que pertenece a PyPrinting).

**Legado [V-legado]:** calibración = offsets a mano más `ShamrockGetCalibration`. No hay rutina automática en `Spectrum_ps.py`.

**Geometría [V-legado + V-código]:**

- El legado le informa **1002** píxeles al Shamrock y recorta la imagen a las columnas 0-1001 (`Camera_ps.py:40, 570`). 3.0 informa 1004.
- Con la misma posición de la red, los ejes difieren en ≈ 1 px: ≈ 0.10 nm con 150 l/mm y ≈ 0.012 nm con 1200 l/mm. Es BANCO-14.
- **Consecuencia nueva para los offsets** [I]: si el 85 de la red de 150 l/mm (R4-3, EXPERIMENTAL) se ajustó mirando un eje de 1002 px, copiarlo tal cual a 3.0 deja un corrimiento sistemático de ≈ 0.1 nm. Eso es más del doble de la exactitud nominal del Shamrock, **0.04 nm**, con repetibilidad de **10 pm** [V-DS-SR500 p.1; el texto extraído desalinea la tabla, y leo "Wavelength accuracy 0.04 nm, repeatability 10 pm" por el orden de las filas]. Ver Q1.

### 1.5 Step & Glue

**3.0 [V-código]** (`step_and_glue.py:526-659`):

1. **Planificación.** Lee la red y la ventana medida (`measured_window_nm`, que usa el eje cúbico) y calcula los centros.
2. **Por cada ventana:**
   - `abort_acquisition()`;
   - `_settle_wavelength()`, que llama a `ShamrockSetWavelength` **sin mirar el retorno** (`:418`) y espera mientras `is_moving()`. Ese `is_moving()` es un **temporizador**: `time.time() < _settling_until`, con 0.3 s tras un `SetWavelength` exitoso (`shamrock_driver.py:348-351`, `:475-483`). La espera renueva `heartbeat_shutter(30.0)` con un argumento explícito (`:423`, `:428`);
   - lee el eje;
   - **lee el cuadro sin haberlo adquirido**: `get_most_recent_image()` o `get_1d_spectrum()` (`:580-583`). **No hay `StartAcquisition` ni espera del fin de la exposición.** El SDK devuelve `DRV_NO_NEW_DATA` si no hay datos nuevos [V-SDK p.180], y el driver lo convierte en un cuadro de ceros (`andor_ccd_driver.py:520-532`). Si el SDK conserva un cuadro anterior, en cambio, el cosido mezcla un cuadro viejo con el eje nuevo [I: cuál de los dos pasa en el equipo lo resuelve BANCO-10].
3. **Hilo.** La rutina corre en el **hilo de la GUI**: el backend no se mueve a un `QThread` (`window.py:602-603`). Mientras dura, Stop y E-STOP no se procesan, porque no hay `processEvents` y no se consulta `hardware_session.is_emergency_stopped`. Sin embargo, la rutina **sí renueva el latido**, así que el watchdog tampoco cortaría un láser abierto a mano (ver §4.4).
4. **No toca obturadores láser ni el espejo `line7`.** Con la lámpara halógena está bien. Con luminiscencia por pasos, a 532 nm, el camino óptico queda indefinido.
5. **Los datos crudos por ventana quedan sólo en memoria** hasta "Exportar HDF5" (`:650-655`).
6. **Modo de lectura.** La rama 1D se elige con `_read_mode in (0, 1)` (`:505`). El código trata el 1 como Single-Track, pero en el SDK el 1 es **Multi-Track** [V-SDK p.305]. **C-05 queda confirmado con fuente primaria:** 0 FVB, 1 Multi-Track, 2 Random-Track, 3 Single-Track, 4 Image.

**Legado [V-legado]** (`StepandGlue_ps.py:623-712`, `:1149-1227`). Por cada centro:

1. `ShamrockSetWavelength`, sin espera explícita;
2. `ShamrockGetWavelength` y `GetCalibration(1002)`;
3. `set_acquisition_mode='single'` (probablemente anulado por la asignación, ítem A de la sonda), `set_exposure`, `setup_shutter('open', 1)`;
4. `start_acquisition()`, `wait_for_frame()`, `read_oldest_image()`, `stop_acquisition()`.

Guarda en disco la imagen y la calibración de cada paso. Las ventanas son fijas: 103 nm o 12 nm (`:1062-1073`).

- [I] Que el legado mida bien sin esperar después de `SetWavelength` sugiere que `ShamrockSetWavelength` **bloquea hasta terminar el giro**. Si no bloqueara, el primer segundo de exposición integraría con la red en movimiento. No está confirmado [REQ-manual-Shamrock]; lo resuelven BANCO-08 y BANCO-39.

---

## 2. Riesgos físicos y de hardware del primer arranque, por severidad

| # | Sev. | Qué pasa | Qué se daña o se pierde | ¿Persiste? ¿Es reversible? |
| :-- | :--- | :--- | :--- | :--- |
| R1 | **CRÍTICA** | Offsets inventados escritos al abrir (§1.1-5): red 150 = 12 (debería ser 85, EXPERIMENTAL), red 1200 = −35 (hoy 0), espejo = 0, detector = 5 (hoy 0), cero de ranura = 0. 3.0 no lee antes de escribir | El eje λ de **todas** las mediciones posteriores queda corrido: (12 − 85) = −73 pasos en la red de 150 y −35 en la de 1200, multiplicados por k nm/paso, que es **desconocido** (BANCO-40). Con un k del orden de 0.01-0.1 nm/paso [I, sin fuente] serían de décimas a varios nm. Afecta también a **Solis y al legado**, que comparten el equipo | [I] **Persiste fuera del proceso:** el legado nunca reescribía los offsets y sin embargo medía calibrado, así que viven en el Shamrock (EEPROM) o en un archivo del host. No sé en cuál de los dos [REQ-manual-Shamrock], y eso lo resuelve BANCO-37. **Es reversible sólo si antes se respaldan los valores (BANCO-25)**; si no, hay que recalibrar. Los espectros tomados mientras tanto se pueden corregir sólo si su metadato registra el offset vigente, y hoy no lo registra |
| R1b | **ALTA** | Cero de ranura escrito en 0. El rango válido es −200 a 0 [2ª-Shamrock, `Shamrock_ps.py:2670`] | Si el cero de fábrica no es 0, cada ancho comandado queda corrido: la resolución y el throughput reales difieren de los que se registran. [I, REQ-manual-Shamrock] Con anchos chicos las mordazas podrían llegar al tope | Igual que R1 |
| R2 | **ALTA** | Mock silencioso fuera de SAFE_MODE (`andor_ccd_driver.py:748-750`, `shamrock_driver.py:785-787`, y además `:376-378` si falta la DLL). En el primer arranque es probable que falle `Initialize`: Solis o el legado con la cámara tomada, un `SPECTROG.INI` en otra ruta, versiones de DLL distintas | El operador ve **espectros sintéticos** como si fueran reales, con eje de mock y "cámara" enfriándose. Puede quedar una mezcla de cámara real con Shamrock simulado. Contradice DEC-036 y la memoria *no-silent-mock-in-production* | Pérdida de datos y de tiempo, sin daño físico. Reversible |
| R3 | **ALTA** | Orden cero o espejo con ganancia EM activa (§1.3): cinco caminos sin protección y un diálogo cuya salvaguarda falla en silencio si la cámara adquiere | Saturación del registro EM y posible envejecimiento. La hoja de datos lo minimiza para el 885; el SDK lo advierte en general. Ver §1.3 | Un daño sería **irreversible** |
| R4 | **ALTA (dato)** | Step & Glue sin exposición (§1.5): ceros o cuadros viejos, `SetWavelength` sin verificar, eje falso 400-700 si falla la calibración, GUI y E-STOP congelados durante todo el barrido | Barridos enteros inválidos que parecen válidos, porque el cosido de ceros "funciona" | No persiste; reversible |
| R5 | **MEDIA-ALTA** | Rendija con firma equivocada (C-06, re-verificado: `shamrock_driver.py:488-512`, llamada desde `calibration_dock.py:683, 723`, `left_hardware_panel.py:316-317`, `spectrum_control.py:236-239` y `step_and_glue.py:460`) | `GetSlit`: violación de acceso, y [I] posible cuelgue de la DLL. `SetSlit`: la DLL lee el ancho de XMM1, un registro que el llamador no cargó [I, convención x64]. La ranura va a un ancho indeterminado o la llamada se rechaza. El recorte a 10-2500 µm no tiene efecto porque el valor recortado no llega | Reversible: basta mover de nuevo con la función correcta. Los datos tomados en el medio quedan con una ranura desconocida |
| R6 | **MEDIA** | Constantes de modo de lectura corridas (C-05, confirmado [V-SDK p.305]) | Elegir "Single-Track" configura Multi-Track. `get_1d_spectrum` pide 1004 píxeles, que no es el tamaño del cuadro, y el SDK responde "Array size is incorrect" [V-SDK p.180]: salen ceros | Reversible |
| R7 | **MEDIA** | `pi.connect()` al abrir PySpectrum (§1.1-4) | Home y liberación del interlock sin que el operador lo pida. Los obturadores se cierran antes, así que no hay láser sobre la muestra, pero la posición se pierde y la rutina de PyPrinting que había quedado en pausa se desalinea | Reversible; es una violación de política |
| R8 | **MEDIA** | Cámara a medio inicializar (§1.1-1): enfriador apagado aunque la GUI diga ON, VS speed, ventilador y modo de adquisición en los valores por defecto del SDK, que no están documentados ahí | Corriente oscura alta si se mide sin enfriar. Datos no comparables con el legado (VS 1.9 µs, ventilador bajo). Sin daño | Reversible |
| R9 | **MEDIA** | Unidades de la ganancia EM: en el modo por defecto, `SetEMCCDGain` recibe un valor de DAC de 0 a 255 [V-SDK p.271]. 3.0 nunca fija el modo, acota a 0-1000 y aplica una "salvaguarda de 5×" (`andor_ccd_driver.py:469-483`) | La salvaguarda no significa lo que dice. Un valor fuera de rango devuelve P1INVALID, que se ignora | Reversible |
| R10 | **MEDIA** | Amplificador "Convencional" (1) disponible en el panel (`left_hardware_panel.py:113-116`). El SDK lo admite en iXon [V-SDK p.298], pero la hoja de datos del 885 lista sólo velocidades "through EMCCD amplifier" (p.2), en línea con D-18 | Error del SDK o un modo que el cabezal no tiene, y después combos poblados con datos inconsistentes | Reversible; `GetNumberAmp` lo resuelve (BANCO-38) |
| R11 | **BAJA** | `GetStatus` fallido se informa como `DRV_IDLE` (`andor_ccd_driver.py:602-611`) | Un lazo de espera que confíe en él daría por terminada una exposición que no terminó | Reversible |
| R12 | **BAJA** | Puertos: `ShamrockSetFlipper`/`GetFlipper` no existen en la DLL (C-07, re-verificado: `shamrock_driver.py:539-557`) | La GUI muestra un puerto falso y no puede cambiarlo. El espejo mecánico conserva su posición. Si el chasis fuera un B2, que sólo tiene entrada lateral, el selector de entrada no tendría hardware detrás [V-DS-SR500 p.3]. El modelo "SR-500i-B2-R" sale del archivo de calibración inventado, así que **no está confirmado** | No persiste |

**Respuesta directa: ¿qué se pierde si se escriben offsets equivocados?**

- **Se pierde la exactitud del eje λ** de todas las mediciones siguientes, en PySpectrum 3.0, en Solis y en el legado. Todos arrancan con el estado del equipo.
- **Se pierde el valor anterior**, porque 3.0 no lo lee antes. Ése es el único dato irrecuperable.
- **¿Persiste en el equipo?** La inferencia fuerte, apoyada en el legado, es que sí, fuera del proceso. Si queda en la EEPROM o en un archivo del host es [REQ-manual-Shamrock], y lo resuelve BANCO-37.
- Mientras exista un respaldo leído del equipo y se registre qué valor estuvo vigente en cada medición, el daño **es reversible**.

---

## 3. Semántica del SDK que el diseño necesita, y cómo confirmarla sin riesgo

### 3.1 Resuelto con el manual del SDK de cámaras (v2.104)

| Pregunta | Respuesta | Fuente |
| :--- | :--- | :--- |
| Códigos de `SetReadMode` | 0 FVB, 1 Multi, 2 Random, 3 Single, 4 Image. C-05 confirmado; coincide con `ccd_ps.py:891-892` | [V-SDK p.305] |
| Fin de exposición | `WaitForAcquisitionTimeOut(ms)` devuelve `DRV_NO_NEW_DATA` al vencer y se puede cortar con `CancelWait`. El evento llega "at the end of a Single Scan Acquisition" | [V-SDK p.326, 329, 105] |
| Exposición real | `SetExposureTime` redondea hacia arriba y el valor real se lee con `GetAcquisitionTimings` | [V-SDK p.272, 117] |
| `GetMostRecentImage` | El buffer debe ser "exactly the same size as the complete image". Devuelve `DRV_NO_NEW_DATA` si no hay dato nuevo | [V-SDK p.180] |
| Setters durante una adquisición | `SetEMCCDGain`, `SetExposureTime`, `SetReadMode`, `SetVSSpeed`, `SetShutter` y `SetOutputAmplifier` devuelven `DRV_ACQUIRING`. **Toda salvaguarda tiene que abortar primero y verificar IDLE** | [V-SDK p.270, 272, 305, 323, 309, 298] |
| Ganancia EM | Modo 0 = DAC 0-255 (por defecto), 1 = 0-4095, 2 = lineal, 3 = Real Gain. Más de ×300 sólo con `SetEMAdvanced` y "tens of photons per pixel". **Ganancia EM apagada al inicializar** (nota de versión) | [V-SDK p.271, 270, 25] |
| Ventilador | 0 full, 1 low, 2 off | [V-SDK p.273] |
| Cooler y apagado | `SetCoolerMode(0)` deja volver a ambiente en `ShutDown`. El requisito de estar por encima de −20 °C antes de `ShutDown` es para Classic/ICCD, no para iXon | [V-SDK p.247, 323] |
| Obturador de la cámara | `SetShutter(typ, mode, …)`: typ 1 = TTL alto abre; modos 0 auto, 1 abierto, 2 cerrado. Hay `IsInternalMechanicalShutter`. En modos de imagen, con luz continua, un obturador que no cierra antes de la lectura da "smeared image" | [V-SDK p.309, 211, 70] |
| VS speed | `GetNumberVSSpeeds`/`GetVSSpeed(i)` dan la tabla y `GetFastestRecommendedVSSpeed` la más rápida sin subir el voltaje. La hoja de datos dice 0.5-1.9 µs | [V-SDK p.189, 205, 163; V-DS-iXon p.2] |

### 3.2 Pendiente del manual del Shamrock SDK [REQ-manual-Shamrock]

Evidencia secundaria: docstrings del wrapper legado.

1. **¿`ShamrockSetGratingOffset` y `ShamrockSetDetectorOffset` persisten en la EEPROM, en un archivo del host o sólo en la sesión?**
   - *Pregunta al manual o a Andor:* "Are grating/detector offsets set with ShamrockSetGratingOffset/ShamrockSetDetectorOffset stored in the spectrograph EEPROM, and do they survive a power cycle?"
   - Única pista en el manual de cámaras: "Fixed issue where Shamrock precision was lost after power cycle" [V-SDK p.17]. No lo aclara.
2. **Unidades y signo del offset** (nm por paso, sentido del corrimiento) y **si `SetGratingOffset` mueve el motor** o sólo cambia el cálculo.
   - Los docstrings dicen "(steps)" [2ª-Shamrock, `:2363-2395`, `:2056-2085`].
   - Topes: `SHAMROCK_GRAT_OFFSET_MAX = 20000` y `SHAMROCK_DET_OFFSET_MAX = 240000` (`Shamrock_ps.py:47-48`).
3. **Semántica del offset del detector frente a los puertos.**
   - Existen `ShamrockGet/SetDetectorOffsetEx(entrancePort, exitPort)`, con cuatro combinaciones, y `…Port2` [2ª-Shamrock, `:754-800`, `:2087-2127`].
   - Con entrada *Side* y salida *Direct* (R2-11), el offset que rige podría ser el `Ex(1, 0)` y no el simple. Hay que saberlo antes de idear el protocolo del detector (§5.4).
4. **¿`ShamrockSetWavelength` y `ShamrockSetGrating` bloquean hasta terminar el movimiento?** No hay ningún getter tipo "IsMoving" en el wrapper. Sí existe `ShamrockAtZeroOrder` [2ª-Shamrock, `:99-131`].
5. **Convención de `GetPixelCalibrationCoefficients`:** origen del índice de píxel, relación con `SetNumberPixels` y dependencia de los offsets.
6. **Rendija:** las funciones correctas son `ShamrockSetAutoSlitWidth(device, index, width)` y `ShamrockGetAutoSlitWidth(device, index, &w)`, con `index` 1 = entrada lateral [2ª-Shamrock, `:2016`, `:611-650`, `:40-45`]. Es lo que usaba el legado (`Spectrum_ps.py:206`).
7. **Orden de cierre:** "Fixed issue with Shamrock SDK closing the camera, now only closes camera if it initialised it" [V-SDK p.14]. Con una DLL del Shamrock vieja, `ShamrockClose` podría cerrar la cámara, algo relevante para `hardware_manager.py:291-307`. Hay que conocer la versión instalada (BANCO-23).

### 3.3 Cómo confirmarlo sin riesgo

- **Sólo getters, con el legado abierto y en reposo**, extendiendo la sección D de `tools/bench/legacy_console_probe.py` (el objeto `mySpectrometer` del legado ya expone los Get*). Leer los offsets **antes** que cualquier otra cosa, y leer los de la cámara con la cámara IDLE, porque varios getters devuelven `DRV_ACQUIRING`.
- **Leer los archivos de Solis y del host, sin abrirlos para escribir**: `SPECTROG.INI` en las dos rutas de Program Files, su fecha y si contiene campos de offset. Eso ayuda a decidir entre EEPROM y host.
- **Solis** también muestra los offsets vigentes en su diálogo de calibración del espectrógrafo, pero conviene no usarlo en la misma sesión que la sonda: dos programas sobre el mismo USB.
- **Las pruebas de escritura** (unidades del offset, bloqueo de `SetWavelength`) mueven actuadores. Son de bajo riesgo con la ganancia EM en 0, los láseres cerrados y la cámara IDLE, pero **requieren aprobación explícita** y un respaldo previo (BANCO-25).

### 3.4 Ítems nuevos propuestos para `docs/evidence/PRUEBAS_BANCO_PENDIENTES.md`

No edité ese archivo; esta es la propuesta.

- **BANCO-36 — Lectura ampliada del Shamrock** (legado abierto; sólo lectura). Agregar a la sección D de la sonda:
  - `ShamrockGetDetectorOffsetEx(dev, e, x)` para (0,0), (0,1), (1,0) y (1,1), y `ShamrockGetDetectorOffsetPort2`;
  - `ShamrockGetWavelengthLimits(dev, g)` para g = 1, 2, 3, y `ShamrockAtZeroOrder`;
  - `ShamrockFlipperMirrorIsPresent` y `ShamrockGetFlipperMirror` para 1 y 2;
  - `ShamrockAutoSlitIsPresent` y `ShamrockGetAutoSlitWidth` para 1 a 4;
  - `ShamrockShutterIsPresent` y `ShamrockGetShutter`;
  - `ShamrockEepromGetOpticalParams`;
  - en el mismo estado, `ShamrockGetCalibration` con 1002 y con 1004 junto con `GetPixelCalibrationCoefficients`, para comparar los dos ejes (§1.4).

  *Resuelve:* qué offset del detector rige, qué accesorios hay (modelo del chasis), si el eje cúbico coincide con `GetCalibration` y los límites de λ para el interlock de orden cero.
- **BANCO-37 — Dónde persisten los offsets** (sólo lectura). Leer los offsets con la sonda, cerrar todo, apagar y encender el Shamrock (y la PC), y volver a leerlos. Registrar la ubicación, la fecha y el contenido de `SPECTROG.INI`.

  *Resuelve:* EEPROM frente a host, que decide si escribir un offset afecta a otra PC u otra instalación de Solis (§3.2-1).
- **BANCO-38 — Lectura ampliada de la cámara** (legado abierto, cámara IDLE; sólo getters por la DLL de la sesión ya abierta):
  - `GetNumberAmp`, `GetAmpDesc` y `GetNumberHSSpeeds` por amplificador (resuelve D-18 y R10);
  - `GetEMGainRange`, `GetEMCCDGain` y `GetCapabilities` (modos de ganancia; R9);
  - `GetNumberVSSpeeds`, `GetVSSpeed(i)` y `GetFastestRecommendedVSSpeed` (qué índice es 1.9 µs);
  - `GetTemperatureRange` (opción de enfriamiento DV o DU, pendiente en `lab-invariants` §3);
  - `IsInternalMechanicalShutter`;
  - `GetAcquisitionTimings`;
  - `GetStatus`.
- **BANCO-39 — ¿Bloquean `ShamrockSetWavelength` y `ShamrockSetGrating`?** (**acciona actuadores; requiere aprobación**; sin láser, ganancia EM 0, cámara IDLE). Medir la duración de cada llamada para saltos de 20, 200 y 500 nm y para un cambio de red, y leer `GetWavelength`/`GetGrating` al volver. Se puede combinar con BANCO-08 (estabilidad óptica del pico).

  *Resuelve:* si alcanza con el retorno de la llamada o hace falta una espera real (§4.1).
- **BANCO-40 — Pasos → nm y signo del offset de red** (**escritura reversible; requiere aprobación y BANCO-25 hecho**).
  - Con una línea conocida (lámpara o 532 atenuado, ganancia EM 0) y la red de 150 l/mm: leer O₀, escribir O₀ + ΔO (p. ej. +20), medir el corrimiento del pico, **restaurar O₀ y releerlo**.
  - Anotar además si `SetGratingOffset` hace girar el motor (se oye o se ve).

  *Resuelve:* la conversión que necesita la rutina de calibración (§5.4).
- **BANCO-41 — Ganancia EM durante una adquisición** (sin luz, con la tapa puesta, ganancia 0). Con Live de 3.0 activo, pedir `SetEMCCDGain(0)` y anotar el código. Se espera `DRV_ACQUIRING` [V-SDK p.270].

  *Resuelve:* confirma en el equipo que la salvaguarda de orden cero tiene que abortar primero.
- **BANCO-42 — Desde qué λ central entra el orden cero al chip** (**acciona la red; requiere aprobación**; ganancia EM 0, lámpara atenuada). Con 150 l/mm, λ_c en 70, 60, 50, 45 y 40 nm: registrar el λ_c en el que aparece la imagen especular. Se espera ≈ W/2 ≈ 52 nm [I].

  *Resuelve:* el umbral del interlock (§1.3, camino f).

---

## 4. Timing

### 4.1 Asentamiento de la red y de λ

- **Hoy [V-código]:** todo el asentamiento es una espera por reloj.
  - `set_grating`, `set_wavelength` y `set_slit` fijan `_settling_until = now + 4.0 / 0.3 / 0.8 s` **sólo si el retorno fue SUCCESS**, e `is_moving()` compara con ese instante (`shamrock_driver.py:348-360`, `:451-512`).
  - Ninguna consulta al hardware respalda esos valores. `lab-invariants` §3 ya marca los 4.0 s como una espera del software, no como un tiempo medido.
  - Como `_settle_wavelength` no mira el retorno, un `SetWavelength` fallido "asienta" al instante (`step_and_glue.py:413-429`).
- **¿Qué contaría como confirmación real?**
  1. **Retorno SUCCESS de la llamada**, si la llamada bloquea hasta terminar (hipótesis [I] apoyada por el legado; BANCO-39).
  2. **Relectura** de `GetGrating`/`GetWavelength` igual a lo pedido. Sirve como coherencia, **no como medición**: el motor es paso a paso a lazo abierto y el SDK probablemente devuelve su propio objetivo [I].
  3. **Confirmación óptica**: el pico de una línea conocida está quieto entre dos cuadros (BANCO-08). Es la única confirmación física, y sólo sirve en calibración o en el banco, no en cada paso de una rutina.
- **Propuesta conceptual:** la confirmación válida es (1) + (2), más un margen fijo sólo si BANCO-39 muestra que la llamada no bloquea. Un fallo en (1) o (2) aborta el paso, conserva lo adquirido y lo informa, igual que un `False` de `wait_on_target()` en la platina (DEC-036).

### 4.2 Fin de exposición

- **Hoy:** no existe. No hay `WaitForAcquisition` en todo 3.0 (grep).
- **Esquema del legado y de R4-5:** una exposición por nodo, que se inicia, se espera y se lee.
- **Esquema propuesto:**
  1. verificar IDLE con un `GetStatus` que **no** traduzca una falla en IDLE (R11);
  2. `SetAcquisitionMode(1)` (Single Scan, [V-SDK p.240]);
  3. `SetExposureTime` y leer la exposición real con `GetAcquisitionTimings`;
  4. `StartAcquisition` con el retorno verificado;
  5. esperar con `WaitForAcquisitionTimeOut` **en tramos** de, por ejemplo, 200-500 ms, con un tope total de exposición real + lectura + margen. En cada tramo: latido, Stop y E-STOP;
  6. `GetAcquiredData` con el tamaño exacto del modo de lectura, rechazando todo código distinto de SUCCESS. Nunca ceros de relleno.
- **Duración de la lectura [I]:** un cuadro completo de ≈ 1.0 Mpx a 13 MHz tarda ≈ 0.08 s (la hoja de datos da 31.4 fps a cuadro completo en el modo más rápido, p.2). Es despreciable frente a 10 s.

### 4.3 Watchdog durante Step & Glue con ventanas de hasta 10 s

- **Presupuesto por ventana [I]:** cambio de λ (≤ 0.3 s según el driver; real: BANCO-39), más exposición (≤ 10 s, R4-4), más lectura (≈ 0.1 s), más cosido y guardado (≪ 1 s). Da **< 12 s**, con un margen de 2.5× frente a los 30 s. Si la ventana incluye un cambio de red, se suman 4 s y el total sigue en < 16 s.
- **Duración total [I]:**
  - 400-900 nm con 150 l/mm y 20 % de solape: 6-7 ventanas, **≈ 1.3 min**;
  - con 1200 l/mm (ventana ≈ 11.6 nm): ≈ 54 ventanas, **≈ 10 min**. Con la rutina en el hilo de la GUI, eso son 10 min sin E-STOP. Hace falta un worker en `QThread` que consulte `hardware_session.is_emergency_stopped`, según `exemplars/pyqt_routine_concurrency_gold.md`.
- **Riesgo de que el watchdog corte una rutina sana:**
  - aparece si la espera de la exposición es un único bloqueo largo (`WaitForAcquisition` sin tope) y la exposición se acerca a 30 s;
  - el panel permite exposiciones de hasta **60 s** (`left_hardware_panel.py:143`);
  - la espera en tramos con latido en cada tramo lo elimina sin depender de la duración.
- **Violación de C-29 hoy:** `heartbeat_shutter(30.0)` con argumento explícito (`step_and_glue.py:423, 428`) vuelve a armar un corte de 30 s aunque el operador haya elegido "Sin límite". Tiene que ser `heartbeat_shutter()` sin argumento.
- **Problema de política** [V-código `core/nidaq.py:204-216` + I]:
  - el latido es **global al proceso**, y PySpectrum y PyPrinting comparten proceso (R4-2);
  - un Step & Glue con lámpara no abre ningún obturador DAQ, pero su latido **mantiene vivo cualquier obturador que otro haya dejado abierto** y desactiva la protección de obturador abandonado;
  - propuesta: que una rutina sólo emita el latido mientras **ella** tiene un obturador abierto. Queda para la fase 6.2 (liveness beat), que **no está exenta de Rondas 1 y 2**.

---

## 5. Opciones de arquitectura (sin código)

### 5.1 Dónde vive el archivo de calibraciones

| Opción | A favor | En contra |
| :--- | :--- | :--- |
| A. En el repo, versionado (p. ej. `pyspectrum/calibration/`) | Historial de git y auditoría | Un `git pull` o un checkout en otra máquina pisa la calibración del banco. El archivo actual es justamente un ejemplo inventado que llegó así |
| B. Local a la PC del banco, fuera de git (carpeta de datos del usuario o `config/` ignorado), con una **plantilla** versionada | Cada banco tiene su calibración y git no la toca | Necesita una copia de respaldo aparte |
| C. **B más un registro append-only**: cada calibración y cada escritura al equipo agrega una línea con fecha, método, operador, número de serie del Shamrock, red, puerto, valor previo, valor nuevo, λ de referencia, residuo y versión de software | Trazabilidad completa y reversión a cualquier punto | Un poco más de código |

**Recomiendo C.**

- Cada entrada indexada por **número de serie del Shamrock + red + combinación de puertos**, porque el offset de detector depende del puerto (§3.2-3).
- Los valores sin procedencia se marcan explícitamente: el 85 como EXPERIMENTAL / "dato del investigador"; los que vengan de la sonda, como "leído del equipo, fecha".

### 5.2 Cuándo se escribe al equipo

- **Nunca al arrancar.** Sólo con la acción "Aplicar al Shamrock", que:
  1. lee los valores vigentes del equipo;
  2. los muestra en un diff contra el archivo;
  3. los respalda en el registro;
  4. escribe;
  5. **relee y confirma que coinciden** (patrón DEC-014/DEC-036). Una escritura que la relectura no confirma se informa como "estado desconocido".
- Todos los setters directos del dock (`calibration_dock.py:737-779`) pasan por esa misma puerta.
- **Alternativa D, corrección en software:** no escribir nunca los offsets al equipo, dejar el valor vigente y corregir píxel ↔ λ en software a partir de la calibración con 532.
  - *A favor:* no toca el estado que comparten Solis y el legado, es 100 % reversible y el archivo es la única fuente.
  - *En contra:* el eje de 3.0 diverge del de Solis. El centrado mecánico de la ventana no se corrige, aunque con 0.04 nm de exactitud y solape del 10-20 % es irrelevante [I]. Además, el investigador pidió escribir al Shamrock con una acción explícita (R4-3).
  - *Posible híbrido:* offsets de red escritos con acción explícita y offset del detector fijo en el equipo, con corrección en software (ver Q2).

### 5.3 Cómo detectar que el equipo tiene otros offsets que el archivo

- Al arrancar se hace **sólo lectura** (`GetGratingOffset` de las 3 redes, `GetDetectorOffset` y sus variantes `Ex`, cero de ranura) y se compara con el archivo.
- Si difieren, aparece un aviso persistente y no bloqueante: "El Shamrock tiene offsets distintos del archivo (red 1: equipo 85, archivo 12)". Las opciones son:
  - adoptar los del equipo en el archivo, con procedencia "leído del equipo";
  - aplicar los del archivo (la acción de §5.2);
  - seguir sin cambiar nada.
- **Cada archivo de datos registra en su metadato** los offsets vigentes leídos del equipo, λ_c, la red, la geometría informada al SDK (1004 × 8 µm) y la fuente del eje (GetCalibration o cúbico). Es lo que permite corregir después un espectro tomado con offsets equivocados.

### 5.4 Protocolo de calibración de offsets con 532 nm (concepto)

1. **Preparación, con cada paso confirmado o la rutina aborta:**
   - ganancia EM 0, leída de vuelta;
   - filtro de densidad arriba con `up_flipper()`. Es un pulso dirigido, no un conmutador;
   - espejo `line7` **abajo**. Es un conmutador sin realimentación (R2-4/5, C-08): no se puede confirmar, así que el operador confirma o la rutina verifica que llegue luz (siguiente punto);
   - obturador de 532 abierto con latido.
2. **Adquisición:** una exposición corta con el esquema de §4.2, sin saturar (pico por debajo de ~70 % del fondo de escala, lo que conviene verificar antes del ajuste). Si el pico no supera un umbral de SNR, la rutina aborta con el mensaje "¿espejo arriba o láser cerrado?".
3. **Medición del error:** ajuste gaussiano → píxel del centroide → error Δλ = λ_eje(px) − 532.0 (λ del láser: dato a confirmar).
4. **Conversión:** Δλ → Δpasos con k de BANCO-40, y un nuevo offset propuesto.
5. **Cierre:** se muestra el valor sugerido, el operador aplica con §5.2 y se remide. El resultado entra al registro con fecha y método.

- **Offset del detector** [I, por identificabilidad]:
  - si los dos offsets son aditivos en pasos (el docstring los pone en pasos a los dos), medir una sola línea por red da un sistema degenerado: con una medición por red **no se puede separar** G_red de D;
  - incluso con dos redes quedan tres incógnitas (G₁, G₂, D) y dos ecuaciones. D sólo se fija por **convención**, o si su semántica fuera otra (p. ej. un desplazamiento lateral del detector, que escala con la dispersión de cada red, [REQ-manual-Shamrock]);
  - propuesta: **fijar D por convención (0 hoy) y absorber todo en los offsets por red**. D se toca sólo si cambia la posición de la cámara o el puerto de salida, cuando un mismo corrimiento común explica el error de todas las redes y del espejo;
  - la imagen de la ranura en orden cero o con el espejo (red 3), con ganancia EM 0, sirve como **control** de centrado: el centroide debería caer en el píxel ≈ 501.5. No sirve para separar D.
- **La red de 1200 l/mm** se calibra con el mismo 532. La ventana de 11.6 nm contiene la línea si λ_c ≈ 532.
- **Advertencia [I]:** si en el camino de detección hay un notch o un filtro de borde para 532 (típico para Raman), la línea del láser llega atenuada o no llega. Ver Q4.

### 5.5 Un único camino al orden cero

- **Dónde vive el interlock:**
  - *Opción 1:* un **servicio de seguridad del espectrógrafo** en el núcleo de PySpectrum, por el que pasan **todas** las órdenes de λ, red y orden cero: diálogo, panel, dock, `spectrum_control`, atajos y rutinas. Los widgets no tocan el driver.
  - *Opción 2:* la regla va **dentro de los drivers**: `ShamrockDriver.set_wavelength`/`set_grating(3)`/`goto_zero_order` rechazan el movimiento si la cámara no confirmó ganancia 0, y la cámara rechaza `set_emccd_gain > 0` mientras el espectrógrafo esté en condición especular.
  - *A favor de la opción 2:* nada la esquiva, ni una rutina nueva ni un test manual.
  - *En contra de la opción 2:* acopla dos drivers.
  - *Mi preferencia:* **opción 1 para la orquestación y opción 2 como red de seguridad mínima**, que es la misma idea que el recorte de la platina dentro de `MOV`, más allá de lo que hagan las rutinas.
- **Condición especular:** red 3 (espejo), o |λ_c| < W(red)/2 + margen, o `ShamrockAtZeroOrder == 1`.
- **Secuencia:**
  1. abortar la cámara y verificar IDLE;
  2. `SetEMCCDGain(0)` y relectura igual a 0;
  3. `close_all_shutters()` con retorno `True`;
  4. opcional: cerrar el obturador del Shamrock y registrarlo;
  5. mover y verificar el retorno;
  6. mientras dure la condición especular, la ganancia EM queda **bloqueada en 0**. Salir de la condición no la restituye sola: el operador la vuelve a subir.
  - Si un paso falla, **no se mueve**. Si la lectura de la ganancia falla, cuenta como "ganancia desconocida", no como 0.
- **Override experto:** propongo eliminarlo o limitarlo a ganancia 0 con láser abierto, para alinear con el haz. Ver Q3.

### 5.6 Inicialización de la Andor y del Shamrock

- **Sin mock fuera de SAFE_MODE.** Si `Initialize` o `ShamrockInitialize` fallan, el dispositivo se marca "no conectado", con el código, y todo lo que dependa de él queda bloqueado. Es lo mismo que DEC-036 hizo con la DAQ.
- **Configuración explícita al conectar, con cada retorno verificado:**
  - `SetAcquisitionMode(1)`;
  - `SetReadMode(4)` (Image, como el legado);
  - `SetImage` a cuadro completo, 1004 × 1002;
  - `SetEMCCDGain(0)` con el modo de ganancia fijado explícitamente;
  - `SetVSSpeed` al índice de 1.9 µs que dé BANCO-38;
  - `SetFanMode(1)`, bajo, como el legado;
  - `SetShutter` según BANCO-09/38.
  - El setpoint y el enfriador, según Q7.
- **Estado mostrado:** la GUI muestra lo que se **leyó** del equipo, nunca el valor por defecto del widget.
- **Geometría:** se informa 1004 × 8 µm (ya se hace). El cambio frente a los 1002 del legado se documenta en el metadato (BANCO-14).

---

## 6. Preguntas para el investigador

1. **¿El 85 de la red de 150 l/mm se midió con Solis o con el legado?**
   - El legado le informa 1002 píxeles al Shamrock y recorta la imagen a 1002 columnas. Quiero saber también con qué línea y qué λ central se midió.
   - *Desbloquea:* si el 85 se copia tal cual al archivo o se re-verifica con la geometría de 3.0 (1004 px, ≈ 0.1 nm de diferencia) antes de escribirlo.
2. **¿Acepta fijar por convención el offset del detector (0) y absorber toda la corrección en los offsets por red?**
   - El detector sólo se tocaría si se mueve la cámara o cambia el puerto.
   - *Desbloquea:* el "protocolo del detector", que con una línea por red no es identificable (§5.4).
3. **¿Para qué se usa el orden cero, o el espejo de la torreta? ¿Alguna vez hace falta ganancia EM > 0 en esa condición?**
   - *Desbloquea:* un bloqueo duro de ganancia 0 en condición especular, y si el "Override experto" se elimina o se limita.
4. **¿Hay un filtro notch o de borde para 532 fijo en el camino al espectrómetro? ¿Qué filtro de densidad (OD), dónde está y qué potencia llega? ¿La "rutina actual de láser + filtro de densidad" es de Solis, del legado o manual?**
   - *Desbloquea:* el diseño de la rutina de calibración con 532, es decir si hay que retirar el notch, el nivel de saturación y el tiempo de exposición.
5. **En Step & Glue, ¿la luz es siempre la lámpara halógena (no controlada por la DAQ) o a veces un láser (luminiscencia por pasos)? ¿La rutina tiene que bajar el espejo `line7` sola?**
   - *Desbloquea:* si Step & Glue abre obturadores y emite latido, y cómo trata el espejo sin realimentación.
6. **¿El archivo de calibraciones queda local a la PC del banco (fuera de git) o versionado en el repo? ¿Cualquier operador puede escribir offsets al Shamrock, o hace falta una confirmación doble?**
   - *Desbloquea:* §5.1 y §5.2.
7. **Arranque de la cámara: ¿el enfriador y el setpoint (−60 °C del SOP) se encienden solos al abrir, o a mano? ¿Ventilador en "low" y VS speed de 1.9 µs como el legado?**
   - *Desbloquea:* la configuración explícita de §5.6.
8. **¿Solis o el legado van a seguir usándose en el mismo banco?**
   - *Desbloquea:* si escribir offsets al equipo es aceptable, porque afecta a los tres programas, o conviene la corrección en software (§5.2, opción D).

---

## Veredicto

**`SAFETY_VIOLATION` para el primer arranque tal como está el código.** Los motivos son:

- escribe offsets inventados al abrir, sin leer antes (R1);
- cae en mocks silenciosos fuera de SAFE_MODE (R2);
- tiene cinco caminos sin protección a la condición especular y un diálogo cuya salvaguarda falla en silencio con la cámara adquiriendo (R3);
- Step & Glue no expone (R4);
- la rendija se llama con una firma equivocada (R5);
- `pi.connect()` reconecta y manda a home al abrir (R7).

**Requisito previo para cualquier corrida:** hacer BANCO-25 (respaldo de offsets, sólo lectura), idealmente junto con BANCO-36, BANCO-37 y BANCO-38.
