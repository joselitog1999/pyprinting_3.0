# PySpectrum 3.0, bloque A — Ronda 2, instrumentación: contratos exactos con el hardware

- **Fecha:** 2026-09-28. **Agente:** `instrumentation`. **Estado:** completo (§0-§9 y veredicto).
- **Alcance:** secuencia de arranque, servicio de orden cero, escritura de offsets, calibración automática (lado hardware), Step & Glue (lado hardware), parámetros de la Andor, timing y watchdog, ítems de banco.
- **Método:** sólo lectura. No se ejecutó nada contra hardware y no se escribió código de producción: las firmas y secuencias de este documento son **contratos a implementar en la Ronda 4**, no código existente.
- **Vinculante:** `RESPUESTAS_INVESTIGADOR.md` §R4, §R4-A y §R4-2b. Base: `pyspectrum_A_ronda1/` (README e `instrumentation.md`).
- **Graphify:** se consultó primero (`graphify query` sobre arranque, orden cero y offsets del Shamrock/Andor). Después se leyeron sólo `andor_ccd_driver.py`, `shamrock_driver.py`, `step_and_glue.py`, `core/nidaq.py` y las partes del legado señaladas.

## 0. Rótulos de evidencia

| Rótulo | Significado |
| :--- | :--- |
| **[SDK p.N]** | Andor SDK2 User's Guide v2.104 (`docs/bibliografia/Software Development Kit.pdf`), página N del PDF (coincide con el "Page N" impreso). Es el SDK de **cámaras**; la versión del banco puede ser otra (BANCO-23). |
| **[DS-iXon p.N]** / **[DS-SR500 p.N]** | Hojas de datos `Andor_iXon3_885_Specifications.pdf` y `andor-shamrock-500-specifications.pdf`. |
| **[2ª-Shamrock]** | Docstring del wrapper legado `scratch/pyspectrum-legacy/Shamrock_ps.py` (línea). **Fuente secundaria**: no hay manual del Shamrock SDK. |
| **[2ª-SR303]** | *Shamrock 303i User Guide* v4.2 (otro modelo; copia en el scratchpad de la sesión, no en `docs/bibliografia/`). Secundaria y de otro equipo. |
| **[2ª-pylablib]** | `pylablib/devices/Andor/AndorSDK2.py`, rama `master` en GitHub, leída el 2026-09-28. Es la biblioteca que usa el legado para la cámara; **la versión instalada en el banco no se conoce**. |
| **[V-código]** / **[V-legado]** | Lectura del código actual / de la copia local del legado (su cableado DAQ puede estar viejo). |
| **[I]** | Inferencia mía, con el razonamiento a la vista. |
| **[BANCO-n]** | Se resuelve en el ítem de banco indicado (§8). |

**Códigos de retorno usados abajo** (valores de `andor_ccd_driver.py:19-26` y del mapa del legado `ccd_ps.py:41-111`; la tabla primaria es [SDK p.331], cuyo texto extraído sale desalineado): `DRV_SUCCESS` 20002, `DRV_NO_NEW_DATA` 20024 ("No acquisition has taken place"), `DRV_TEMP_OFF` 20034, `DRV_TEMP_NOT_STABILIZED` 20035, `DRV_TEMP_STABILIZED` 20036, `DRV_TEMP_NOT_REACHED` 20037, `DRV_TEMP_DRIFT` 20040, `DRV_P1INVALID` 20066, `DRV_ACQUIRING` 20072, `DRV_IDLE` 20073, `DRV_NOT_INITIALIZED` 20075. Shamrock: `SHAMROCK_SUCCESS` 20202, `SHAMROCK_COMMUNICATION_ERROR` 20201, `SHAMROCK_P1INVALID`…`P5INVALID` 20266-20270, `SHAMROCK_NOT_INITIALIZED` 20275, `SHAMROCK_NOT_AVAILABLE` 20292 [2ª-Shamrock l. 28-36; `shamrock_driver.py:54-60`].

**Regla general de todos los contratos:** cada llamada a la DLL devuelve un código, y el contrato es ese código. Una excepción de ctypes, un código distinto del esperado o un valor de relleno cuentan como **falla** (patrón DEC-034/DEC-036). Ninguna función del driver convierte una falla en un valor "seguro" aparente (hoy `get_status` convierte una falla en `DRV_IDLE`, `andor_ccd_driver.py:602-611`, y `get_emccd_gain` devuelve `(DRV_NOT_INITIALIZED, 0)`, que un llamador descuidado lee como "ganancia 0").

---

## 1. Secuencia de arranque

### 1.1 Principios

1. **Orden:** cámara primero y Shamrock después, como el legado (`PySpectrum_UNSAM.py:785-791`) y como 3.0 hoy (`window.py:471-472`). Cierre en orden inverso: `ShamrockClose` y después `ShutDown` de la cámara. Motivo: [SDK p.14], nota de 2.101.30001: *"Fixed issue with Shamrock SDK closing the camera, now only closes camera if it initialised it"*. Con una DLL del Shamrock anterior a esa versión, `ShamrockClose` podría cerrar la cámara; con la del repo (2.103, R1 §0) no debería, pero el orden inverso es correcto en cualquier caso [I].
2. **Al arrancar, el Shamrock no se mueve.** Nada de `SetGrating`, `SetWavelength`, `GotoZeroOrder`, `SetFlipperMirror`, `SetAutoSlitWidth` ni escrituras de offsets. Sólo getters, más la geometría del detector (`SetNumberPixels`/`SetPixelWidth`), que es configuración de cálculo, no un actuador. El legado movía la torreta a 150 l/mm y forzaba los puertos en cada arranque (`Spectrum_ps.py:157-166`); 3.0 no lo hace porque es un movimiento que el operador no pidió, y el operador lo tiene a un clic.
3. **Al arrancar, la cámara sí se configura** (parámetros electrónicos, no actuadores ópticos), cada uno con **escritura → relectura → comparación**, más el enfriador y el ventilador que el investigador pidió (R4-A 6).
4. **Sin mock fuera de SAFE_MODE** (DEC-036, memoria *no-silent-mock-in-production*). Si un dispositivo no inicializa, queda "no conectado" con su código, y lo que depende de él queda bloqueado. Nunca se reemplaza por `_MockAndorCCD`/`_MockShamrock` (hoy sí: `andor_ccd_driver.py:748-750`, `shamrock_driver.py:785-787`).
5. **Estado mostrado = estado leído.** Todo indicador de la GUI se llena con la relectura; si la relectura falla, muestra "falló la lectura (código)", nunca el valor por defecto del widget.

### 1.2 Cámara Andor iXon3 885

Firma propuesta del paso completo (driver, `pyspectrum/drivers/andor_ccd_driver.py`):

```python
def connect_and_configure(self, profile: CameraBaseProfile) -> CameraStartupReport: ...
```

`CameraBaseProfile` es inmutable y sale del archivo de configuración local (R4-A 5), con estos valores por defecto: `acquisition_mode=1`, `read_mode=4`, `image=(1,1,1,1004,1,1002)`, `em_gain_mode=0`, `em_gain=0`, `em_advanced=0`, `output_amplifier=0`, `hs_speed_index=<BANCO-38>`, `preamp_index=0`, `vs_speed_index=2` (esperado 1.9 µs, §6.1), `fan_mode=1`, `cooler_setpoint_c=-60`, `cooler_on=True`, `cooler_mode_on_shutdown=0`, `shutter=(typ, mode, 0, 0)` según BANCO-09/38. `CameraStartupReport` lista, por cada paso, la llamada, el código devuelto, el valor pedido y el releído.

| # | Llamada | Argumentos | Retorno esperado | Relectura | Si falla |
| :-- | :--- | :--- | :--- | :--- | :--- |
| C0 | `LoadLibrary(atmcd64d.dll)` | ruta del driver | carga | — | "Cámara: DLL no encontrada/no carga". Fin |
| C1 | `Initialize` | `b""` (como hoy y como el legado) | `DRV_SUCCESS` [SDK p.210] | — | "Cámara no conectada (código)". Causas documentadas: `DRV_USBERROR`, `DRV_ERROR_NOCAMERA`, `DRV_ERROR_ACK`… [SDK p.210]. Causa práctica frecuente: **Solis o el legado tienen la cámara abierta** [I; lo prueba P2 del abogado del diablo]. Fin, sin mock |
| C2 | `GetCameraSerialNumber`, `GetHeadModel`, `GetDetector` | — | `DRV_SUCCESS` [SDK p.123, 168, 159] | `GetDetector` = 1004 × 1002 [DS-iXon p.1] | Si `GetDetector` ≠ 1004 × 1002: **no conectar** (geometría inesperada; DEC-033) |
| C3 | `GetStatus` | — | `DRV_SUCCESS` y estado `DRV_IDLE` [SDK p.198] | — | Si no está IDLE justo después de `Initialize`, algo inesperado: `AbortAcquisition` una vez y releer; si sigue, "no conectada" |
| C4 | `SetCoolerMode` | `0` (vuelve a ambiente al cerrar) [SDK p.247] | `DRV_SUCCESS` | — (no hay getter documentado) | Aviso no bloqueante; se registra |
| C5 | `SetAcquisitionMode` | `1` (Single Scan) [SDK p.240] | `DRV_SUCCESS` | — (no hay `GetAcquisitionMode` en SDK2 [I, búsqueda en el manual]); se registra lo enviado | Bloquea adquisiciones |
| C6 | `SetReadMode` | `4` (Image) [SDK p.305] | `DRV_SUCCESS` | — (sin getter); se registra | Bloquea adquisiciones |
| C7 | `SetImage` | `1,1,1,1004,1,1002` (coordenadas **desde 1**, inclusivas [SDK p.285]) | `DRV_SUCCESS` | — | Bloquea adquisiciones |
| C8 | `SetOutputAmplifier` | `0` (registro EMCCD) [SDK p.298] | `DRV_SUCCESS` | `GetNumberAmp` [SDK p.183] (≥ 1) | Bloquea adquisiciones |
| C9 | `SetHSSpeed` | `0, idx` [SDK p.284] | `DRV_SUCCESS` | `GetHSSpeed(0, 0, idx)` → MHz [SDK p.169] (valor de la tabla; no hay getter del índice vigente) | Bloquea adquisiciones |
| C10 | `SetPreAmpGain` | `0` [SDK p.303] | `DRV_SUCCESS` | `GetCurrentPreAmpGain` = índice 0 [SDK p.147] | Bloquea adquisiciones. Nota de versión: *"acquisition failing unless pre amp gain is set before starting an acquisition"* [SDK p.16]: **este paso no es opcional** |
| C11 | `SetVSSpeed` | `2` (§6.1) [SDK p.323] | `DRV_SUCCESS` | `GetVSSpeed(2)` ≈ 1.9 µs [SDK p.205] | Si `GetVSSpeed(2)` no da 1.9 ± 0.05 µs: **no fijar** el índice a ciegas; aviso y bloqueo hasta BANCO-38 |
| C12 | `SetEMAdvanced` | `0` [SDK p.270] | `DRV_SUCCESS` o `DRV_NOT_AVAILABLE` | `GetEMAdvanced` = 0 [SDK p.160] | `DRV_NOT_AVAILABLE` es aceptable (no hay ganancia avanzada) |
| C13 | `SetEMGainMode` | `0` (DAC 0-255) [SDK p.271] | `DRV_SUCCESS` | `GetEMGainRange` [SDK p.162] → (lo, hi) | Bloquea adquisiciones |
| C14 | `SetEMCCDGain` | `0` [SDK p.270] | `DRV_SUCCESS` | `GetEMCCDGain` = 0 [SDK p.160] | **Bloquea todo**: sin ganancia 0 confirmada no hay adquisición |
| C15 | `SetExposureTime` | exposición de reposo (p. ej. 0.05 s) [SDK p.272] | `DRV_SUCCESS` | `GetAcquisitionTimings` [SDK p.117] | Bloquea adquisiciones |
| C16 | `SetShutter` (o `SetShutterEx`) | según BANCO-09/38 | `DRV_SUCCESS` o `DRV_NOT_SUPPORTED` | `IsInternalMechanicalShutter` [SDK p.211] | Se registra; ver §5.4 |
| C17 | `SetFanMode` | `1` (low) [SDK p.273] | `DRV_SUCCESS` | — (sin getter) | Aviso; el ventilador queda en el estado por defecto, que el manual no documenta |
| C18 | `GetTemperatureRange` | — | `DRV_SUCCESS` [SDK p.201] | (min, max) | Si −60 queda fuera de (min, max), no se fija y se avisa |
| C19 | `SetTemperature` | `-60` [SDK p.316] | `DRV_SUCCESS` | — | Aviso persistente "enfriador no configurado" |
| C20 | `CoolerON` | — [SDK p.107] | `DRV_SUCCESS` | `IsCoolerOn` = 1 [SDK p.211] | Aviso persistente |
| C21 | `GetTemperature` | — [SDK p.200] | uno de `DRV_TEMP_*` | °C + estado | Ver §6.3 |

**Relecturas que el SDK2 no permite.** El manual v2.104 no tiene `GetAcquisitionMode`, `GetReadMode`, `GetFanMode` ni `GetEMGainMode` (búsqueda de las firmas en el texto del manual, sin resultados; sí existen `GetEMAdvanced` p.160, `GetCurrentPreAmpGain` p.147, `GetHSSpeed` p.169 y `GetEMGainRange` p.162). Para esos cuatro parámetros la única garantía es el `DRV_SUCCESS` de la escritura: el driver guarda lo último enviado con éxito y la GUI lo rotula "enviado", no "leído". La falsación P3 del abogado del diablo pide `GetEMGainMode`, que no existe; se reemplaza por `GetEMGainRange` (que depende del modo vigente).

**Qué resetea el SDK al inicializar:** el manual de cámaras **no documenta** los valores por defecto de ventilador, velocidad vertical, modo de adquisición o enfriador después de `Initialize` [SDK p.210, búsqueda sin resultados]. Lo único documentado es la nota de versión *"Fixed default EM gain - Set to off when system initialized"* [SDK p.25]. Por eso la secuencia fija y relee todo lo que importa, en vez de confiar en valores por defecto. En particular, **no se asume** que el enfriador esté apagado ni encendido tras `Initialize`: se lee `IsCoolerOn` antes de C19 y se registra (si Solis dejó la cámara fría con `SetCoolerMode(1)`, puede estar encendido [I]).

**Qué hacía el legado** [2ª-pylablib, V-legado]: `AndorSDK2Camera(temperature=10, fan_mode="low")` → al abrir, pylablib llama `set_temperature(10, enable_cooler=True)` (setpoint +10 °C, recortado al rango, y `CoolerON`), `set_fan_mode("low")` = 1, `setup_shutter("closed")`, `set_trigger_mode("int")`, `set_exposure(0)` y `set_acquisition_mode("cont")`. Después, `set_camera_parameters` fija `setup_image_mode(0,1002,0,1002)`, pre-amp 0, `set_EMCCD_gain(0)` y `set_vsspeed(2)` (`Camera_ps.py:566-607`). El operador bajaba la temperatura a mano con "Set temperature" (`Camera_ps.py:485-500`). 3.0 cambia el setpoint inicial a −60 °C por pedido del investigador (R4-A 6).

### 1.3 Shamrock 500i

Firma propuesta (`pyspectrum/drivers/shamrock_driver.py`):

```python
def connect_and_read(self, calib_store: CalibrationStore) -> SpectrographStartupReport: ...
```

| # | Llamada | Argumentos | Retorno esperado | Qué se hace con el resultado | Si falla |
| :-- | :--- | :--- | :--- | :--- | :--- |
| S0 | `LoadLibrary(ShamrockCIF.dll)` | ruta del driver | carga | — | "Espectrógrafo: DLL no encontrada". Fin |
| S1 | `ShamrockInitialize` | ruta de `SPECTROG.INI` de Solis (como el legado, `PySpectrum_UNSAM.py:790`) | `SHAMROCK_SUCCESS`; el docstring lista `SHAMROCK_COMMUNICATION_ERROR` = *"Can't read Shamrock EEPROM"* [2ª-Shamrock l. 1781-1810] | — | "Espectrógrafo no conectado (código)". Sin mock |
| S2 | `ShamrockGetNumberDevices` | — | ≥ 1 [2ª-Shamrock l. 1230] | se usa `DEVICE = 0` | "no conectado" si 0 |
| S3 | `ShamrockGetSerialNumber` | 0 | éxito | **clave del archivo de calibraciones** (§3.1) | "no conectado": sin serie no se puede comparar calibración |
| S4 | `ShamrockEepromGetOpticalParams` | 0 | éxito | se registra (f, ángulo, tilt); sólo lectura | aviso |
| S5 | `ShamrockGetNumberGratings`, `GetGratingInfo(g)` para g = 1..3 | — | éxito | l/mm y blaze por red, contra el archivo | aviso si difieren |
| S6 | `ShamrockGetGrating`, `GetWavelength`, `AtZeroOrder` | — | éxito | **estado inicial del interlock de orden cero** (§2.4) | si fallan, el estado espectral queda "desconocido" y la ganancia EM queda bloqueada en 0 hasta una lectura válida |
| S7 | `ShamrockGetWavelengthLimits(g)` para g = 1..3 | — | éxito | se registran; `SetWavelength` fuera de ellos lo rechaza el propio SDK con `P2INVALID` [2ª-Shamrock l. 2728-2759] | aviso |
| S8 | `ShamrockGetGratingOffset(g)` g = 1..3; `GetDetectorOffset`; `GetDetectorOffsetEx(e,x)` para (0,0),(0,1),(1,0),(1,1) | — | éxito | **comparación con el archivo** (§3.3). Nunca escribe | aviso persistente si difieren; lectura fallida = "offset desconocido", nunca el valor viejo del archivo |
| S9 | `ShamrockAutoSlitIsPresent(i)`, `GetAutoSlitWidth(i)` para i = 1..4 | — | éxito | ancho de la ranura de entrada lateral (índice 1) | aviso |
| S10 | `ShamrockGetSlitZeroPosition(i)` | — | éxito | se registra; **nunca** se escribe | aviso |
| S11 | `ShamrockFlipperMirrorIsPresent(f)`, `GetFlipperMirror(f)` f = 1, 2 | — | éxito | se esperan entrada *Side* (1) y salida *Direct* (0), como forzaba el legado | **aviso**, no se corrige solo. El operador tiene "Fijar puertos Side/Direct" |
| S12 | `ShamrockShutterIsPresent`, `GetShutter` | — | éxito; modo −1 = "no fijado todavía" [2ª-Shamrock l. 1485-1518] | estado del obturador del Shamrock (§5.4) | aviso |
| S13 | `ShamrockSetNumberPixels(1004)`, `SetPixelWidth(8.0)` + relectura | — | éxito y relectura igual | como hoy (`shamrock_driver.py:612-623`) | bloquea el eje λ |
| S14 | `ShamrockGetCalibration(1004)` y `GetPixelCalibrationCoefficients` | — | éxito | eje λ inicial y control cruzado de los dos ejes | eje "desconocido" |

Si la cámara conecta y el Shamrock no: las adquisiciones en píxeles se permiten (con el eje rotulado "px"), pero **toda función que dependa de λ queda bloqueada** y la ganancia EM queda en 0 sin posibilidad de subirla, porque el interlock de orden cero no puede saber dónde está la red (§2.4). Si el Shamrock conecta y la cámara no, no se adquiere nada.

### 1.4 Qué **nunca** se llama al arrancar

- `ShamrockSetGratingOffset`, `ShamrockSetDetectorOffset`, `ShamrockSetDetectorOffsetEx`, `ShamrockSetDetectorOffsetPort2`, `ShamrockSetSlitZeroPosition` (hoy C-04 los escribe desde el constructor del dock de Calibraciones, `calibration_dock.py:1010-1017`).
- `ShamrockEepromSetOpticalParams` (existe desde [SDK p.13]). Nunca, en ningún camino de 3.0: la guía del SR-303 advierte que guardar parámetros ópticos en la EEPROM *"is not reversible"* [2ª-SR303 p. 52].
- `ShamrockSetAutoSlitCoefficients`, `ShamrockSetSlitCoefficients`, `ShamrockWavelengthReset`, `ShamrockSlitReset`, `ShamrockAutoSlitReset`, `ShamrockFlipperMirrorReset` (reset = movimiento a una posición de fábrica).
- `ShamrockSetGrating`, `ShamrockSetWavelength`, `ShamrockGotoZeroOrder`, `ShamrockSetFlipperMirror`, `ShamrockSetAutoSlitWidth`.
- En la cámara: `SetEMAdvanced(1)`, `SetEMCCDGain(>0)`, `SetOutputAmplifier(1)` (el 885 lista velocidades sólo "through EMCCD amplifier", [DS-iXon p.2]; R10 de la Ronda 1), `SetHighCapacity`, `SetVSAmplitude(>0)`.
- Test en CI: un driver espía que registra cada llamada; el arranque completo en SAFE_MODE no debe contener ninguna de estas (ver la falsación P1 del abogado del diablo).

### 1.5 Otros efectos del arranque que no son del driver

- **Platina a home al abrir PySpectrum:** el investigador lo acepta "como hoy" (R4-A 10). Contrato mínimo: `pi.connect()` cierra los obturadores y los confirma **antes** del home (ya lo hace, `config.py:414-448`), y la espera del home pasa por `wait_on_target()` con `False` = "platina no en home" (hoy sale a los 3 s sin error, `config.py:421-425`; R1 §1.1-4).
- **Tablero de hardware:** abrirlo no debe llamar `get_andor_ccd(reset=True)` ni `get_shamrock(reset=True)`, que hacen `ShutDown`/`ShamrockClose` e inicializan de nuevo (R1 §2, punto 9, a verificar; P7 del abogado del diablo). Un `ShutDown` con `SetCoolerMode(0)` lleva la cámara a ambiente [SDK p.247].

---

## 2. Servicio de orden cero ("espejo rápido")

El investigador lo usa **seguido** para pasar rápido a primer orden (R4-A 3), así que la protección es automática sobre el detector y **no hay diálogo**. El `ZeroOrderSafetyDialog` y su "Override experto" desaparecen del camino normal.

### 2.1 Qué es "condición especular"

La red está en condición especular si se cumple cualquiera de:

1. red activa = 3 (espejo de la torreta, `GRATING_MIRROR = 3`, `shamrock_driver.py:23`);
2. `ShamrockAtZeroOrder` devuelve 1 [2ª-Shamrock l. 99-131];
3. |λc| < W(red)/2 + margen, con W la ventana del detector de esa red.
   - W nominal: 103.05 nm (150 l/mm) y 11.57 nm (1200 l/mm), de la dispersión de la hoja de datos por 1004 × 8 µm (`shamrock_driver.py:37-44`).
   - W real: la mide el propio eje (`measured_window_nm`), y el umbral por red se confirma en BANCO-42.
   - Margen propuesto: 10 % de W [I], es decir **umbral de 56.7 nm con 150 l/mm y 6.4 nm con 1200 l/mm**. Nota: con la red de 150 el orden cero ya entra al chip por el borde con λc ≈ 51.5 nm [I, geometría λ(px) ≈ λc ± W/2]; el margen cubre el ancho de la imagen de la ranura y el error del eje.
4. el estado del Shamrock es **desconocido** (falló la lectura de red o λ): cuenta como especular (falla cerrada).

### 2.2 Precondiciones y secuencia de entrada

Firma (servicio de PySpectrum, p. ej. `pyspectrum/core/spectrograph_safety.py`):

```python
class SpectrographSafetyService:
    def enter_specular(self, target: Literal["zero_order", "mirror"],
                       *, restart_live: bool = True) -> SpecularResult: ...
    def leave_specular(self, grating: int, wavelength_nm: float) -> MoveResult: ...
    def move(self, grating: int | None, wavelength_nm: float | None) -> MoveResult: ...  # todo cambio de λ o red
```

`SpecularResult` = `(ok: bool, step_failed: str | None, code: int | None, gain_confirmed: int | None, exposure_real_s: float | None, shutters_closed: bool)`.

Secuencia (cada paso con retorno verificado; **si un paso falla, no se mueve la red** y se informa qué paso y con qué código):

| # | Paso | Llamada | Criterio de éxito |
| :-- | :--- | :--- | :--- |
| Z1 | Tomar la sesión de hardware | `hardware_session.acquire_session("Orden cero", auto_pause_live=True)` | concedida; pausa los Live registrados |
| Z2 | Detener la cámara | `GetStatus`; si `DRV_ACQUIRING`: `CancelWait` (si hay un hilo esperando) + `AbortAcquisition` | `AbortAcquisition` → `DRV_SUCCESS` o `DRV_IDLE` [SDK p.105]; después `GetStatus` = `DRV_IDLE`, reintentado hasta 500 ms |
| Z3 | Ganancia EM a 0 | `SetEMCCDGain(0)` | `DRV_SUCCESS` [SDK p.270]. Si devuelve `DRV_ACQUIRING`, Z2 no funcionó: falla |
| Z4 | Confirmarla | `GetEMCCDGain` | retorno `DRV_SUCCESS` **y** valor 0 [SDK p.160]. Retorno ≠ éxito = "ganancia desconocida" = falla |
| Z5 | Acotar la exposición | `SetExposureTime(min(t_actual, T_SPEC_MAX))` + `GetAcquisitionTimings` | éxito y exposición real ≤ `T_SPEC_MAX` [SDK p.272, 117]. `T_SPEC_MAX` provisorio = 10 ms, a fijar con BANCO-A7 |
| Z6 | Obturadores láser | ver §2.3 | según la política elegida |
| Z7 | Mover | `ShamrockGotoZeroOrder(0)` (orden cero) o `ShamrockSetGrating(0, 3)` (espejo) | `SHAMROCK_SUCCESS` |
| Z8 | Releer | `ShamrockAtZeroOrder` = 1 (orden cero) o `GetGrating` = 3 (espejo) | coincide; si no, estado "desconocido" (sigue especular por la regla 4) |
| Z9 | Armar el bloqueo | `specular_lock = True` en **los dos drivers** (§2.5) | — |
| Z10 | Primer cuadro | si `restart_live`: Live con la exposición acotada; se revisa el primer cuadro: pico − bias < 50 % de 16 383 cuentas (14 bit, [DS-iXon p.2]) | si lo supera: `AbortAcquisition` y aviso "saturación en orden cero: reducir luz o ranura" (no se sale de orden cero, no se toca la red) |

**Fricción:** Z2-Z6 son llamadas de software de microsegundos a milisegundos, salvo `AbortAcquisition` (termina la lectura en curso, ≤ ~0.1 s para un cuadro completo [I, R1 §4.2]). El tiempo dominante es el giro de la torreta (Z7), que existe igual con o sin protección. El operador ve un único botón o `Ctrl+0` y un indicador **"ESPECULAR — ganancia EM bloqueada en 0"**. No hay nada que confirmar.

### 2.3 Obturadores: cuáles y cuándo

- **Durante el giro (Z7):** la luz no daña con ganancia 0 y exposición acotada [I, R1 §1.3 "física del riesgo"], pero en orden cero pasan **todos** los láseres a la vez (E, R1 §3.2).
- **Propuesta A (la más simple, recomendada):** Z6 = `close_all_shutters()` con retorno `True` (DEC-036: un cierre no confirmado es abierto → falla y no se mueve). El operador reabre el láser que necesite **después**, desde el panel de obturadores. Costo: un clic cuando se alinea con el haz.
- **Propuesta B (menos fricción, pregunta al investigador):** no cerrar si **todos** los láseres abiertos están con el filtro de densidad en potencia baja (`not is_flipper_high_power()`, `core/nidaq.py:315`) y cerrar sólo si está en alta. Limitación: `is_flipper_high_power()` es el último pulso enviado, no una medición (el flipper se puede mover a mano).
- **En los dos casos**, mientras dure la condición especular, abrir un láser con el filtro en **potencia alta** queda rechazado por un interlock condicional (`set_shutter_interlock("Orden cero", …)` existe, `core/nidaq.py:276`, pero hoy bloquea **todas** las aperturas; hace falta una variante "bloquear sólo con filtro en alta", o aplicar el chequeo en el servicio). Esto es cambio de política de obturadores: **no exento de Rondas 1-2** (ya estamos en la 2; queda para aprobación explícita).
- **Obturador del Shamrock:** si existe (BANCO-09), se **deja como está**. Cerrarlo en orden cero haría inútil el "espejo rápido" (el operador quiere ver la imagen). No es una protección necesaria con la ganancia en 0.

### 2.4 Salida a primer orden

```text
leave_specular(grating, λc):
  1. precondición: |λc| ≥ umbral(grating) (§2.1-3); si no, se rechaza ("seguiría especular")
  2. move(): acercamiento desde abajo (§4.3) si es la rutina de calibración; en uso manual, directo
  3. ShamrockSetGrating(g) si cambia → SHAMROCK_SUCCESS; ShamrockSetWavelength(λc) → SHAMROCK_SUCCESS
  4. relectura GetGrating = g, GetWavelength ≈ λc (±0.01 nm), AtZeroOrder = 0
  5. specular_lock = False en los dos drivers
  6. la ganancia EM NO se restituye sola: queda en 0 y el operador la sube (R1 §5.5-6; E §3.3-5)
```

Si 3 o 4 fallan, el estado queda "desconocido" y, por la regla 4 de §2.1, el bloqueo sigue armado.

### 2.5 Topes que viven **en los drivers** (red de seguridad mínima)

La orquestación está en el servicio; los drivers tienen una red mínima que ningún widget, rutina nueva ni script puede esquivar (misma idea que `clamp_axis_um()` dentro de `_PIController.MOV()`):

1. **`AndorCCDDriver.set_emccd_gain(g)`:** si `g > 0` y `spectrograph_state.is_specular_or_unknown()` → devuelve `DRV_P1INVALID` sin llamar a la DLL, y registra "bloqueado por condición especular". El estado espectral se inyecta como un objeto compartido de sólo lectura (un `SpecularState` con `threading.Lock`), no importando el driver del Shamrock (evita el acoplamiento circular).
2. **`ShamrockDriver.set_wavelength(λ)`, `set_grating(g)`, `goto_zero_order()`:** si el destino es especular (§2.1) y `camera_state.em_gain_confirmed_zero()` no es `True` (lectura `GetEMCCDGain` exitosa = 0 **hecha en los últimos N ms** o bloqueo ya armado), devuelven `SHAMROCK_P2INVALID` sin llamar a la DLL. El driver del Shamrock no llama a la cámara: consulta el estado que publica el driver de la cámara.
3. **Rango de ganancia:** `set_emccd_gain` recorta a `GetEMGainRange()` del modo vigente (hoy recorta a 0-1000 y aplica una "salvaguarda de 5×" que en modo 0 son 5 unidades de DAC, `andor_ccd_driver.py:469-483`; R1 R9). Se elimina esa salvaguarda y se reemplaza por el rango real.
4. **Exposición:** `set_exposure_time` recorta a `T_MAX_S` global (10 s por R4-4, con margen hasta lo que decida el investigador; el panel hoy permite 60 s, `left_hardware_panel.py:143`) y, en condición especular, a `T_SPEC_MAX`.
5. **E-STOP:** además de cerrar obturadores y abortar la cámara, pone `SetEMCCDGain(0)` y lo relee (hoy no, `hardware_session.py:134-158`).
6. **Caminos que tienen que pasar por el servicio** (C-03 y R1 §1.3): el botón y `Ctrl+0`; `spectrum_control.py:272-280`; `calibration_dock.py:712-718`; "Ir a λ" del panel izquierdo con 0-2000 nm; el combo "Espejo"; cualquier λc bajo el umbral; Step & Glue y escaneo lineal con un centro bajo el umbral.

---

## 3. Escritura de offsets

### 3.1 Qué se sabe y qué no

| Tema | Lo que hay | Fuente | Estado |
| :--- | :--- | :--- | :--- |
| Firmas | `ShamrockSetGratingOffset(int device, int Grating, int offset)`, `ShamrockGetGratingOffset(int device, int Grating, int* offset)`, `ShamrockSetDetectorOffset(int device, int offset)`, `ShamrockSetDetectorOffsetEx(int device, int entrancePort, int exitPort, int offset)` y los `Get` correspondientes | [2ª-Shamrock l. 1160, 2363, 723, 2056, 754, 2087] | Secundaria |
| Unidades | "(steps)", enteros, para los dos | [2ª-Shamrock l. 2066, 2373] | Secundaria. **Cuánto corre la línea un paso no está documentado** para el SR-500i. El SR-303 da "≈ 3 unidades ≈ 1 píxel de 26 µm" [2ª-SR303 p. 43], que no se traslada a este equipo. Se mide en BANCO-40/A1 |
| Rangos | `SHAMROCK_GRAT_OFFSET_MAX = 20000`, `SHAMROCK_DET_OFFSET_MAX = 240000` | [2ª-Shamrock l. 47-48] | Secundaria; se interpretan como \|offset\| ≤ máx. [I] |
| Semántica | Detector: global, corrige un corrimiento mecánico (cámara o torreta desmontada y vuelta a montar). Red: vale sólo para la red respectiva | [2ª-SR303 p. 42] | Secundaria, otro modelo |
| `Ex` y puertos | `Ex` se usa "if the system has 4 ports"; (entrada, salida) = (0,0) D-D, (0,1) D-S, (1,0) S-D, (1,1) S-S | [2ª-Shamrock l. 2087-2105] | Secundaria. Con entrada Side y salida Direct, si el chasis tuviera 4 puertos regiría `Ex(1,0)`; si no, el simple. El modelo del chasis **no está confirmado** (R1 R12) |
| ¿Escribir mueve el motor? | Nota de versión: *"Fix for Detector Offset Adjustment not moving the shamrock turret if using any of the side ports"* | [SDK p.16] | **Primaria**: ajustar el offset del detector **mueve la torreta**, al menos desde esa versión. Para el offset de red no hay dato [I: probablemente igual]. Consecuencia de diseño: **una escritura de offset es una orden de movimiento** y pasa por las mismas precondiciones que un cambio de λ (§2.5; cámara IDLE y ganancia 0 confirmada) |
| Versiones | *"Fixed issue with ShamrockGetDetectorOffsetEx not returning the correct value"* (2.99.x) | [SDK p.16] | Primaria. Con una DLL anterior a 2.99 la lectura `Ex` no es confiable. La del repo es 2.103 (R1 §0); la del banco se ve en BANCO-23 |
| Persistencia | (a) `ShamrockInitialize` falla con *"Can't read Shamrock EEPROM"* [2ª-Shamrock l. 1797]: la inicialización lee la EEPROM. (b) El SR-303 habla de *"the detector offset value stored in the spectrograph memory"* [2ª-SR303 p. 27]. (c) El legado nunca reescribía los offsets y medía calibrado; Solis leyó 85 / 0 / 0 un mes después de calibrar (R4-4) | varias | **Inferencia fuerte, no confirmada:** los offsets viven en la EEPROM del Shamrock y sobreviven al cierre del programa. Falta confirmar: (1) si sobreviven a un ciclo de energía del Shamrock; (2) si `SetGratingOffset` escribe la EEPROM en el acto o sólo cambia la sesión; (3) si hace falta volver a mandar `SetWavelength` para que el offset nuevo tome efecto (E, A1) |

**Consecuencia directa:** escribir un offset afecta a **Solis y al legado**, que siguen en uso (R4-A 7). Por eso la escritura es una acción explícita, con doble confirmación (R4-A 5) y registro.

### 3.2 Alcance de la escritura en el bloque A

- **Sólo offsets de red:** red 1 = 150 l/mm y red 2 = 1200 l/mm.
- El offset del detector queda **fijo en 0 por convención** (R4-A 2). El bloque A **no expone escritura** del detector, de `Ex` ni de `Port2`: se leen y se registran. Si algún día hace falta (la cámara ya se desmontó una vez, R4-A 7), se agrega con otra ronda.
- **Nunca** se escriben el cero de ranura ni la red 3 (espejo).

### 3.3 Secuencia leer → diff → respaldo → escribir → releer

Firma (en el servicio, no en un widget):

```python
def apply_grating_offset(self, grating: Literal[1, 2], new_offset: int, *,
                         source: CalibrationRecord, confirm_token: DoubleConfirmToken) -> OffsetWriteResult: ...
```

`OffsetWriteResult = (ok, before: int | None, requested: int, after: int | None, code_write: int, code_read: int, log_entry_id: str)`.

| # | Paso | Llamadas | Criterio |
| :-- | :--- | :--- | :--- |
| O1 | Precondiciones | `GetStatus` = IDLE (si no, `AbortAcquisition`); `GetEMCCDGain` = 0 confirmado; `close_all_shutters()` = `True`, porque la escritura puede mover la torreta (§3.1) | todas; si falta una, no se escribe |
| O2 | Leer lo vigente | `ShamrockGetSerialNumber`; `ShamrockGetGratingOffset(0, g)`; `ShamrockGetDetectorOffset(0)` | éxito. Si el número de serie no coincide con el del archivo, **no se escribe** ("otro espectrógrafo") |
| O3 | Diff | sin llamadas: muestra `vigente → propuesto`, Δ en pasos y procedencia de `new_offset` (método, fecha, residuo) | Δ ≠ 0; \|new\| ≤ `OFFSET_ABS_MAX` y \|Δ\| ≤ `OFFSET_STEP_MAX` (abajo) |
| O4 | Doble confirmación | GUI: el operador confirma el diff y después confirma otra vez escribiendo el número de red (R4-A 5) | `DoubleConfirmToken` válido, de un solo uso, que vence a los 60 s |
| O5 | Respaldo | registro *append-only* local, fuera de git (R4-A 5): serie, red, puertos, valor vigente **leído**, fecha, operador y versión del software | el registro se escribe y se relee **antes** de tocar el equipo (con `fsync`); si falla, no se escribe |
| O6 | Escribir | `ShamrockSetGratingOffset(0, g, new_offset)` | `SHAMROCK_SUCCESS` |
| O7 | Releer | `ShamrockGetGratingOffset(0, g)` | igual a `new_offset`. Si difiere o falla: "estado desconocido", entrada en el registro, aviso persistente, y se ofrece restaurar el valor de O2 con esta misma secuencia |
| O8 | Reposicionar | si la red escrita es la activa: `ShamrockSetWavelength(0, λc_actual)` y relectura | éxito. [I] Por si el offset recién toma efecto con el movimiento siguiente; A1 dirá si hace falta |
| O9 | Registrar | entrada "aplicado": antes, después, códigos y fuente | — |

**Topes en el driver, no sólo en la GUI.** `ShamrockDriver.set_grating_offset` rechaza con `SHAMROCK_P3INVALID`, sin llamar a la DLL, si:
- `grating ∉ {1, 2}`;
- `|offset| > OFFSET_ABS_MAX`. Valor provisorio: **2000 pasos** [I: un orden de magnitud por encima del 85 vigente y muy por debajo de 20000]. Se ajusta con BANCO-40;
- `|offset − valor leído en esta sesión| > OFFSET_STEP_MAX`. Valor provisorio: **300 pasos** [I]. Protege contra un error de signo o de unidades de la rutina automática.

Además, en el bloque A el driver público **no tiene** setter del detector, de `Ex`, de `Port2` ni del cero de ranura: quedan sólo los getters.

### 3.4 Cómo confirmar la persistencia con el menor riesgo

- **BANCO-37 (sólo lectura):** leer los offsets y `SPECTROG.INI`, apagar y encender el Shamrock, y releer. Confirma que **los valores actuales** (85 / 0 / 0) sobreviven a un ciclo de energía, sin escribir nada.
- **Escritura:** no se hace una escritura "de prueba". La primera escritura real es la que **ya hace falta**: el offset de la red de 1200 l/mm, que vale 0 y nunca se calibró (R4-3).
  1. Aplicarlo con §3.3.
  2. Cerrar 3.0, abrir Solis y leer el valor en su diálogo de calibración.
  3. Apagar y encender el Shamrock; releer con 3.0 y con Solis.
  4. Si no persistiera, se restaura 1200 = 0 con la misma secuencia y el hallazgo va al registro.
  - Requiere aprobación, porque puede accionar la torreta (§8, BANCO-37b).
- Mientras tanto, la escritura sólo se habilita después de BANCO-25 (respaldo leído del equipo).

---

## 4. Calibración automática, lado hardware

Protocolo base: el del experimentalista (R1 E §2), ajustado a R4-A.
- **Fuente:** la leve emisión de 532 nm que deja pasar el notch (R4-A 1), con el láser de 532 **atenuado por el filtro de densidad** en potencia baja.
- No hay lámpara de calibración (R4-A 8).
- El ajuste lo diseña `metrology`; acá va lo que se mueve y la interfaz que `metrology` necesita.

### 4.1 Estado previo, una vez por corrida

| # | Qué | Cómo | Confirmación |
| :-- | :--- | :--- | :--- |
| K1 | Sesión de hardware | `acquire_session("Calibración λ")` | concedida |
| K2 | Cámara | `GetStatus` IDLE; `SetEMCCDGain(0)` + `GetEMCCDGain` = 0; `SetAcquisitionMode(1)`; `SetReadMode(4)` o FVB (lo decide `metrology`: Image permite elegir las filas de la imagen de la ranura); `SetImage` completo | retornos y relecturas (§1.2) |
| K3 | Temperatura | `GetTemperature` = `DRV_TEMP_STABILIZED` a −60 °C (§6.3) | si no está estable: aviso "calibración con el CCD sin estabilizar". No bloquea: el eje no depende del CCD, pero el bias sí |
| K4 | Filtro de densidad en baja | `up_flipper()` = `True` (`Dev1/ao0`; pulso *up* → potencia baja, `lab-invariants` §2) | `is_flipper_high_power()` = `False` después. Es el último pulso enviado, no una medición |
| K5 | Espejo de detección abajo | `flipper_notch532("down")` (`Dev1/port0/line7`; *down* → espectrómetro) | **no tiene realimentación** (C-08). Se confirma por la luz, en K8 |
| K6 | Ranura | `ShamrockGetAutoSlitWidth(0, 1)` y se registra. No se cambia sola. La ranura es bilateral (R4-A 8); A4 lo confirma | lectura |
| K7 | Obturador de 532 | `open_shutter("532")` **sin argumento de timeout** (política global, C-29). Es `Dev1/port0/line11`, **activa en BAJO**: abrir = escribir LOW. La polaridad la resuelve `core/nidaq.py` con `SHUTTER_POLARITY`; la rutina nunca escribe niveles | retorno `True` (DEC-036). Si da `False`, aborta |
| K8 | Luz presente | una exposición corta (§4.2) con λc = 532 y la red 1: pico − bias por encima de un umbral de SNR (lo fija `metrology`) | si no: cierra el 532 y aborta con "¿espejo arriba, notch que no deja pasar nada o láser apagado?" |

### 4.2 Una adquisición

Es el mismo contrato que Step & Glue (§5.2): `acquire_single(exposure_s) -> Frame`, con
`Frame = (data: np.ndarray[int32], exposure_real_s, t_start, t_end, frame_index, read_mode, image_rect, em_gain, temperature_c, temp_status)`.

### 4.3 Qué se mueve en cada iteración

```text
para cada red g en (1, 2):                      # 150 y después 1200; nunca la 3
    move_grating(g)          (si cambia)        # ShamrockSetGrating → SUCCESS → GetGrating = g
    para cada λc en plan(g):                    # ≥ 3 λc por red que recorran el detector (E §2):
                                                #   532 − 0.35 W, 532, 532 + 0.35 W
        approach_from_below(g, λc)              # SetWavelength(λc − Δ_g) y después SetWavelength(λc);
                                                #   Δ_1 = 20 nm, Δ_2 = 3 nm (E §2, INFERENCIA; BANCO-A3)
        confirm_position(λc)                    # GetWavelength = λc ± 0.01 nm; AtZeroOrder = 0
        settle()                                # §4.4
        heartbeat_shutter()                     # sin argumento
        auto_exposure()                         # §4.5
        frames = [acquire_single(t) for _ in range(N)]   # N = 5 (E §2); latido entre cuadros
        check_saturation(frames)                # §4.5
        emit(CalibrationPoint(...))             # a metrology, §4.6
close_shutter("532") → True                     # la ganancia EM sigue en 0
# dentro del lazo nunca se escribe un offset: la corrida es "en seco"
```

- **Los λc del plan están lejos del umbral especular** (532 nm ≫ 56.7 nm), así que ningún paso activa el interlock de orden cero. El servicio lo verifica igual (§2.5).
- **Offsets:** la corrida **no los escribe**. Produce una propuesta; el operador la aplica con §3.3 y después puede lanzar una corrida de verificación, la misma rutina, que confirma el residuo con el offset nuevo.

### 4.4 Asentamiento: confirmación real frente a espera por reloj

**Hoy**, `is_moving()` es un reloj: `time.time() < _settling_until`, con 0.3 s después de `SetWavelength` y 4.0 s después de `SetGrating` (`shamrock_driver.py:24-26`, `:348-351`). El SDK no tiene un getter tipo "IsMoving" [2ª-Shamrock, índice de funciones].

**Contrato propuesto:**
1. **Retorno de la llamada.** La hipótesis es que `ShamrockSetWavelength` y `ShamrockSetGrating` **bloquean** hasta terminar el giro [I, apoyada en que el legado mide bien sin esperar, `StepandGlue_ps.py:623-712`]; se confirma en BANCO-39.
   - El driver mide y registra la duración de cada llamada (`time.perf_counter()` antes y después). Es el dato que necesita BANCO-39, y se junta gratis en cada uso.
2. **Relectura** de `GetWavelength`/`GetGrating`. Es coherencia, no medición: el motor es paso a paso a lazo abierto y el SDK probablemente devuelve su propio objetivo [I].
3. **Margen fijo** `SETTLE_EXTRA_S` después del retorno. Provisorio: 0.3 s para λ y 4.0 s para la red (los valores de hoy) **hasta** BANCO-39. Si la llamada bloquea, el margen baja a lo que haga falta para la vibración residual, que mide BANCO-08.
4. **Sólo en la calibración, confirmación óptica:** entre el primero y el último de los N = 5 cuadros, el centroide no se mueve más de 0.1 px [I]. Si se mueve, se descarta la serie y se repite una vez. Es la única confirmación física, y no cuesta nada porque los cuadros se toman igual.

Un fallo en 1 o 2 aborta el punto, conserva lo adquirido y lo informa (el patrón de `wait_on_target()` de la platina). Durante el margen: `heartbeat_shutter()` cada ≤ 0.5 s, porque el obturador de 532 está abierto.

### 4.5 Ganancia, exposición y saturación

- **Ganancia EM = 0 en toda la corrida.** Con una línea láser la señal sobra, y así la corrida nunca pasa por el riesgo de §2. `set_emccd_gain` no se llama, salvo para confirmar 0.
- **ADC de 14 bit: 16 383 cuentas** [DS-iXon p.2; fila del ADC en `lab-invariants`]. El código de análisis todavía supone 16 bit (C-25). La rutina usa una constante del driver, `ADC_MAX_COUNTS = 16383`, no la de `sif_analyzer.py`.
- **Auto-exposición:**
  - empieza en `T0` = 1 ms y duplica mientras pico − bias < 20 % de 16 383, hasta `T_CAL_MAX` = 1 s [I];
  - si con `T_CAL_MAX` no llega, aborta ("luz insuficiente");
  - si con 1 ms ya pasa del 50 %, aborta ("demasiada luz: ¿el filtro de densidad está arriba?");
  - el objetivo es 20-50 % del ADC (E §2; R1 README §3);
  - cada cambio es `SetExposureTime` + `GetAcquisitionTimings`, y se usa la exposición **real**.
- **Saturación por cuadro:** si algún píxel llega a ≥ 16 000 cuentas, el cuadro se marca saturado y no entra al ajuste.
  - Con ganancia EM 0, el pozo que importa es el del píxel activo: 32 000 e⁻ [DS-iXon p.1]. Una línea que llena el ADC no necesariamente llena el pozo, así que la saturación que se ve es la del ADC [I].
- **Fondo:** para cada λc, la rutina guarda un cuadro con el obturador de 532 **cerrado** (`close_shutter("532")` → `True`) y la misma exposición. `metrology` decide si lo usa.

### 4.6 Interfaz para `metrology`

```python
@dataclass(frozen=True)
class CalibrationPoint:
    serial: str                       # ShamrockGetSerialNumber
    grating: int                      # 1 | 2
    lambda_c_requested_nm: float
    lambda_c_read_nm: float           # GetWavelength
    approach: Literal["from_below"]
    grating_offset_read: int          # GetGratingOffset(g) vigente durante la medición
    detector_offset_read: int         # GetDetectorOffset
    geometry: tuple[int, float]       # (1004, 8.0), leído con GetNumberPixels / GetPixelWidth
    axis_getcalibration: np.ndarray   # ShamrockGetCalibration(1004), nm por píxel
    axis_coefficients: tuple[float, float, float, float]  # GetPixelCalibrationCoefficients
    frames: tuple[Frame, ...]         # N cuadros crudos, int32, sin restar nada
    dark: Frame | None                # misma exposición, obturador de 532 cerrado
    slit_um: float                    # GetAutoSlitWidth(1)
    read_mode: int
    image_rect: tuple[int, int, int, int, int, int]
    exposure_real_s: float
    em_gain: int                      # siempre 0
    ccd_temp_c: int
    ccd_temp_status: int
    settle: dict                      # duración de SetWavelength, margen aplicado, Δcentroide 1.º-último
    lambda_ref_nm: float              # 532.0 nominal, con procedencia (ver abajo)

@dataclass(frozen=True)
class OffsetProposal:                 # lo devuelve metrology
    grating: int
    current: int
    proposed: int | None
    residual_px: float
    residual_nm: float
    steps_per_px: float | None        # de BANCO-40/A1
    accepted: bool                    # provisorio: ≤ 0.5 px (150) y ≤ 1 px (1200), R4-A 9
```

- **Sin `steps_per_px` medido (BANCO-40/A1), la rutina mide el residuo pero no puede proponer un offset en pasos.** La propuesta sale como "residuo medido, conversión pendiente", `proposed = None`, y el botón "Aplicar" queda deshabilitado.
- **λ del láser:** es de diodo (R4-A 8), con una contradicción documental (Excelsior DPSS en BANCO-22). Un diodo puede estar corrido de 532.0 nm y depender de la temperatura [I]. La referencia se confirma en la etiqueta y, si se puede, contra otra referencia. La interfaz la lleva como parámetro con procedencia, nunca como constante.
- **Solis tiene "Auto Adjust"** del offset con una línea conocida [2ª-SR303 p. 42]. No se usa, pero sirve como control cruzado de la primera corrida de 3.0 si el investigador quiere [I].

---

## 5. Step & Glue, lado hardware

Uso real: **lámpara, típicamente 500-900 nm** (R4-A 4). La lámpara no pasa por la DAQ, así que la rutina no abre ningún obturador láser.

### 5.1 Precondiciones (una vez por barrido)

| # | Qué | Cómo | Si falla |
| :-- | :--- | :--- | :--- |
| G1 | Worker propio | la rutina corre en un `QThread` (no en el hilo de la GUI, como hoy `window.py:602-603`) y consulta `hardware_session.is_emergency_stopped` en cada tramo (`exemplars/pyqt_routine_concurrency_gold.md`) | — |
| G2 | Sesión | `acquire_session("Step & Glue", auto_pause_live=True)` | no arranca |
| G3 | Plan | centros ascendentes (así cada ventana se aproxima desde abajo, §4.3); **ningún centro por debajo del umbral especular** (§2.1); `ShamrockGetWavelengthLimits(g)` contiene todos los centros | se rechaza el plan antes de mover nada |
| G4 | Espejo de detección | `get_detection_mirror_state()` ∈ {`"down"`, `"up"`, `"unknown"`} (estado **del software**, sin realimentación; C-08). Si ≠ `"down"`: aviso con tres opciones: "Bajar espejo" (el operador lo ordena: `flipper_notch532("down")`), "Ya está abajo, confirmo" o "Cancelar" (R4-A 4) | — |
| G5 | Ranura | `ShamrockGetAutoSlitWidth(0, 1)`; se registra en el metadato. Sólo se cambia si el operador pidió un ancho, con `ShamrockSetAutoSlitWidth` (§5.5) | "ranura desconocida" en el metadato |
| G6 | Obturador del Shamrock | si `ShamrockShutterIsPresent` = 1: `ShamrockGetShutter`; si ≠ 1 (0 o −1 "no fijado"), `ShamrockSetShutter(0, 1)` y relectura = 1 | aborta: "obturador del espectrógrafo sin confirmar" |
| G7 | Cámara | IDLE; `SetAcquisitionMode(1)`; modo de lectura elegido (FVB 0, Single-Track 3 o Image 4, con las constantes corregidas, §5.5); `SetEMCCDGain` al valor del operador **sólo si** ningún centro es especular (G3 lo garantiza); `SetExposureTime(t)` + `GetAcquisitionTimings` | aborta |
| G8 | Luz presente | la primera ventana se revisa: si el máximo − bias no supera un umbral, aviso "¿espejo arriba o lámpara apagada?" y pausa (no aborta, no descarta) | — |

**El defecto del obturador (R1):** hoy `acquire_session(auto_pause_live=True)` llama al `stop_live` de Exploración, que ejecuta `ShamrockSetShutter(DEVICE, 0)` (`exploration_tab.py:98-105`), y ninguna rutina lo reabre. G6 lo corrige en el lugar correcto: la rutina que necesita el obturador abierto lo abre y lo **relee**, en vez de depender de lo que dejó otro módulo. Queda sin resolver si el obturador lo mueve el Shamrock o la cámara: el legado lo abre de dos maneras, `ShamrockSetShutter(DEVICE, 1)` al arrancar (`PySpectrum_UNSAM.py:793`) y `setup_shutter('open', 1)` de la cámara antes de cada exposición, con el comentario "abre shutter camera y shamrock" (`Camera_ps.py:657`, `StepandGlue_ps.py:651`). Lo resuelve BANCO-09 ampliado (§8).

### 5.2 Una exposición por ventana: `acquire_single`

Contrato común a Step & Glue, calibración y (después) a las rutinas de AND-1 (R4-5):

```python
def acquire_single(self, *, timeout_extra_s: float = 2.0, slice_ms: int = 250,
                   should_abort: Callable[[], bool], on_tick: Callable[[], None]) -> AcquireResult: ...
# AcquireResult = (ok, frame: Frame | None, reason: Literal["ok","aborted","timeout","sdk_error","estop"], code: int | None)
```

```text
A1  GetStatus → DRV_SUCCESS y estado DRV_IDLE                         [SDK p.198]
    (si ACQUIRING: AbortAcquisition → SUCCESS/IDLE y releer; si sigue, sdk_error)
A2  GetAcquisitionTimings → (exp, acc, kin)                           [SDK p.117]
    t_total = kin (o exp + lectura estimada) + timeout_extra_s        # tope duro
A3  n0 = GetTotalNumberImagesAcquired (opcional, para el contador)    [SDK p.201]
A4  StartAcquisition → DRV_SUCCESS                                    [SDK p.324]
A5  bucle:
      r = WaitForAcquisitionTimeOut(slice_ms)                         [SDK p.329]
      on_tick()                        # latido (si corresponde, §7), progreso a la GUI
      si r == DRV_SUCCESS: salir a A6
      # r == DRV_NO_NEW_DATA significa timeout **o** CancelWait: el SDK no los distingue [SDK p.329]
      si should_abort() o E-STOP: AbortAcquisition; devolver "aborted"/"estop" (sin leer datos)
      s = GetStatus
      si s == DRV_IDLE: salir a A6    # terminó antes de que empezara la espera: evento no capturado [I]
      si s ∉ {DRV_ACQUIRING}: AbortAcquisition; "sdk_error" (GetStatus aborta solo ante ACQ_BUFFER, etc. [SDK p.198])
      si now > t_start + t_total: AbortAcquisition; "timeout"
A6  GetAcquiredData(arr, n) con n exacto del modo:                    [SDK p.114]
      Image 1004×1002 = 1 006 008; FVB y Single-Track 1004
    → sólo DRV_SUCCESS es válido. DRV_NO_NEW_DATA / P2INVALID ("Array size is incorrect") = sdk_error.
    Nunca ceros de relleno: sin datos, el Frame es None.
A7  Frame con exposure_real, t_start, t_end, n0+1 (índice), modo, rect, ganancia y temperatura
```

- **Por qué `GetAcquiredData` y no `GetMostRecentImage`:** en Single Scan el cuadro válido es exactamente el de esta adquisición; `GetMostRecentImage` puede devolver un cuadro previo en otros modos y hoy su falla se convierte en ceros (`andor_ccd_driver.py:520-532`). Es el esquema del legado (iniciar, esperar, leer ese cuadro; R4-5).
- **El driver no retiene su `RLock` durante `WaitForAcquisitionTimeOut`.** Si lo retuviera, el `QTimer` de 1 s del panel (`GetTemperature`) y, sobre todo, `CancelWait`/`AbortAcquisition` desde otro hilo quedarían bloqueados hasta el fin del tramo. El lock se toma sólo alrededor de cada llamada corta. `GetTemperature` durante la adquisición puede devolver `DRV_ACQUIRING` [SDK p.200]: el panel lo muestra como "adquiriendo (último valor: …)", no como falla.
- **Cancelación:** Stop pone `should_abort`; como la espera es en tramos de 250 ms, la latencia máxima es 250 ms + `AbortAcquisition`. `CancelWait` [SDK p.105] sólo hace falta si se usan tramos largos; con 250 ms se prescinde de él y se evita la ambigüedad `DRV_NO_NEW_DATA`.
- **Dos procesos:** si Solis o el legado tienen la cámara, `Initialize` ya falló (§1.2); dentro del proceso, `hardware_session` impide dos dueños.

### 5.3 Por ventana

```text
para cada centro λi (ascendente):
    si should_abort(): salir conservando lo adquirido
    r = safety.move(grating=None, wavelength_nm=λi)          # §2.5: pasa por el servicio
        → ShamrockSetWavelength(0, λi) == SHAMROCK_SUCCESS   # C-05bis: hoy no se mira (step_and_glue.py:418)
        → GetWavelength ≈ λi (±0.01 nm); AtZeroOrder == 0
        → margen SETTLE_EXTRA_S con on_tick cada ≤ 0.5 s (§4.4)
      si falla: abortar el barrido, conservar ventanas previas, informar λi y código
    eje_i = ShamrockGetCalibration(0, 1004)  == SHAMROCK_SUCCESS; si no: abortar (nunca el eje falso 400-700,
            shamrock_driver.py:625-635)
    f_i = acquire_single(...)                                 # §5.2
      si no ok: abortar (o reintentar 1 vez si reason == "timeout")
    guardar YA en disco: f_i crudo + eje_i + λi leído + offsets leídos + ranura + T y estado del CCD
    emitir a la GUI (decimado; la GUI nunca bloquea al worker)
```

- **Datos por ventana a disco en el momento**, no sólo en memoria hasta "Exportar HDF5" (hoy `step_and_glue.py:650-655`): el legado guardaba cada paso (`StepandGlue_ps.py:704-705`).
- **Fondo:** el hardware ofrece `acquire_dark()` = `ShamrockSetShutter(0, 0)` → relectura 0 → `acquire_single` → `ShamrockSetShutter(0, 1)` → relectura 1, si el obturador existe (BANCO-09). Si el fondo va por ventana o uno solo lo decide `metrology`.
- **Duración [I]:** 500-900 nm con 150 l/mm (W ≈ 103 nm, 20 % de solape, paso ≈ 82 nm): 5-6 ventanas, < 1.5 min con 10 s. Con 1200 l/mm (W ≈ 11.6 nm, paso ≈ 9.3 nm): ≈ 44 ventanas, ≈ 8-9 min con 10 s.

### 5.4 Obturador interno de la cámara

`SetShutter(typ, mode, closingtime, openingtime)`: typ 0 = TTL bajo abre, 1 = TTL alto abre; mode 0 auto, 1 abierto, 2 cerrado [SDK p.309]. Hoy el driver usa `SetShutter(1, mode, …)` (`andor_ccd_driver.py:676-681`). Si el cabezal tiene obturador interno (`IsInternalMechanicalShutter` [SDK p.211]) y la capacidad `AC_FEATURES_SHUTTEREX`, hay que usar `SetShutterEx` [SDK p.309 nota 2]. Con luz continua en modo Image, un obturador que no cierra antes de la lectura produce *smear* [SDK p.70; R1 §3.1]. Propuesta: modo 0 (auto) con los tiempos que dé `GetShutterMinTimes` [SDK p.196], si hay obturador; si no hay, el tiempo de lectura (≈ 0.08 s) frente a 10 s de exposición hace el *smear* despreciable (< 1 %) [I]. Se decide con BANCO-38.

### 5.5 Corrección de C-05 y C-06

- **C-05 (modos de lectura):** las constantes de `andor_ccd_driver.py:36-40` están mal: dicen `SINGLE_TRACK = 1`, `MULTI_TRACK = 2`, `RANDOM_TRACK = 3`. Según [SDK p.305]: **0 FVB, 1 Multi-Track, 2 Random-Track, 3 Single-Track, 4 Image**. Se corrigen las constantes y **todos** los literales:
  - `step_and_glue.py:505`: `getattr(self.camera, "_read_mode", 4) in (0, 1)` → `in (READ_MODE_FVB, READ_MODE_SINGLE_TRACK)`, es decir `(0, 3)`, **por símbolo, nunca por número**;
  - un test de corpus que prohíba literales numéricos de modo de lectura fuera del driver.
  - Single-Track requiere además `SetSingleTrack(centre, height)` [SDK p.311] con retorno verificado; el tamaño de `GetAcquiredData` es 1004.
- **C-06 (ranura):** hoy `ShamrockGetSlit(device, index)` y `ShamrockSetSlit(device, index, width)` se llaman con 3 argumentos sobre funciones de 2, sin `argtypes` (`shamrock_driver.py:488-514`). Se reemplazan por las del legado (`Spectrum_ps.py:206`):
  - `ShamrockAutoSlitIsPresent(int device, int index, int* present)` con `index = 1` (entrada lateral) [2ª-Shamrock l. 132, 40-45];
  - `ShamrockSetAutoSlitWidth(int device, int index, float width)` [2ª-Shamrock l. 2016-2055];
  - `ShamrockGetAutoSlitWidth(int device, int index, float* width)` [2ª-Shamrock l. 611-650];
  - con `argtypes`/`restype` declarados (`c_int, c_int, c_float` y `c_int, c_int, POINTER(c_float)`), recorte a 10-2500 µm (`SHAMROCK_SLITWIDTHMIN/MAX`, [2ª-Shamrock l. 43-44]) **antes** de la llamada, relectura igual al pedido ± 1 µm [I], y margen de 0.8 s (valor actual) hasta que BANCO-39 mida la ranura;
  - el test `TestSlitSynchronization` pasa a verificar la firma con un doble de la DLL que rechace aridad incorrecta.
- **Declarar `argtypes` en toda función del Shamrock y de la cámara** que reciba punteros o `float`: la llamada de C-06 corrompió memoria porque ctypes no tenía cómo detectarla.

---

## 6. Parámetros de la Andor

### 6.1 Velocidad vertical

- **Legado:** `set_vsspeed(2)` con el comentario "2 for 1.9 us" (`Camera_ps.py:607`), e imprime `get_vsspeed_period()` (l. 609), así que el operador veía el valor. Hoja de datos: 0.5 a 1.9 µs, variable [DS-iXon p.2].
- **Contrato:** al arrancar, `GetNumberVSSpeeds` [SDK p.189] y `GetVSSpeed(i)` [SDK p.205] para todo i; se elige el índice cuyo valor es **1.9 ± 0.05 µs** (se espera el 2, como el legado). Si el índice no es 2, aviso "la tabla difiere del legado" y se usa el que da 1.9 µs. Si ninguno da 1.9 µs, no se fija y se bloquea hasta BANCO-38.
- `GetFastestRecommendedVSSpeed` [SDK p.163] se registra. 1.9 µs es la más lenta, así que nunca requiere subir la amplitud: `SetVSAmplitude` queda en 0 (normal) [SDK p.322].
- La relectura es la tabla (`GetVSSpeed(índice)`); no hay getter del índice vigente.

### 6.2 Ventilador

- `SetFanMode(mode)`: **0 = full, 1 = low, 2 = off** [SDK p.273]. Arranque en **1 (low)**, como el legado y R4-A 6. La opción "high" de la GUI es el **0 (full)**.
- **"Off" no se expone:** el manual dice que con el sistema enfriado el ventilador sólo se apaga "for short periods" y que el cuerpo puede calentarse hasta que suene el zumbador [SDK p.273].
- `SetFanMode` devuelve `DRV_ACQUIRING` durante una adquisición [SDK p.273]: el cambio low ↔ high se aplica entre adquisiciones (el servicio espera IDLE, no aborta una rutina por esto).
- [I] Las temperaturas mínimas de la hoja de datos (DV aire −70 °C, DU −80 °C [DS-iXon p.2]) son probablemente con ventilador a pleno; con "low", −60 °C debería alcanzarse, pero si `GetTemperature` queda en `DRV_TEMP_NOT_REACHED` más de ~15 min, la GUI sugiere pasar a "high". Qué opción de enfriamiento hay (DV o DU) sigue pendiente (`lab-invariants` §3; BANCO-38 con `GetTemperatureRange`).

### 6.3 Enfriador

| Paso | Llamada | Nota |
| :--- | :--- | :--- |
| Rango | `GetTemperatureRange(&min, &max)` [SDK p.201] | −60 debe estar en [min, max]; si no, no se fija |
| Setpoint | `SetTemperature(-60)` [SDK p.316] | `DRV_P1INVALID` fuera de rango; `DRV_ACQUIRING` durante una adquisición |
| Encendido | `CoolerON()` [SDK p.107] | vuelve enseguida; la bajada es gradual "to ensure no thermal stresses" |
| Confirmación | `IsCoolerOn(&s)` = 1 [SDK p.211] | |
| Seguimiento | `GetTemperature(&t)` cada 1 s [SDK p.200] | **el código de retorno es el estado**: `DRV_TEMP_OFF` 20034, `DRV_TEMP_NOT_REACHED` 20037, `DRV_TEMP_NOT_STABILIZED` 20035, `DRV_TEMP_STABILIZED` 20036, `DRV_TEMP_DRIFT` 20040, o `DRV_ACQUIRING` / `DRV_NOT_INITIALIZED` / `DRV_ERROR_ACK`. No devuelve `DRV_SUCCESS` |
| Cierre | `SetCoolerMode(0)` (ya al arrancar) y `ShutDown` | vuelve a ambiente. El requisito de estar por encima de −20 °C antes de `ShutDown` es sólo para Classic/ICCD [SDK p.106, 323] |

- La GUI muestra "Enfriador: ON/OFF" desde `IsCoolerOn`, y la temperatura con el estado en palabras. Hoy muestra "ON" y "−65 °C" sin haber enviado nada (`left_hardware_panel.py:99-106`).
- `is_hardware_alive()` hoy acepta `DRV_SUCCESS` como estado de temperatura válido (`andor_ccd_driver.py:365-373`); los estados válidos son los cinco `DRV_TEMP_*` y `DRV_ACQUIRING`.

### 6.4 Ganancia EM

- Modo fijado explícitamente a **0: DAC 0-255** [SDK p.271], que además es el modo por defecto. La GUI la rotula **"unidades DAC (0-255)"**, no "×". El rango real sale de `GetEMGainRange` [SDK p.162], que depende del modo **y de la temperatura del sensor**; se relee al cambiar la temperatura de estado.
- `SetEMAdvanced(0)` [SDK p.270]: sin acceso a > ×300 (la advertencia de envejecimiento acelerado es para ese régimen).
- La hoja de datos ofrece RealGain 1-1000× [DS-iXon p.2]; el legado dice en un comentario "'RealGain' is not supported in our camera iXon+ 885" (`Camera_ps.py:587-588`). Hay una contradicción (¿iXon+ o iXon3?; el comentario puede estar viejo) que resuelve `GetCapabilities` en BANCO-38. El bloque A **no** usa el modo 3.
- **Por qué fijar el modo importa para el orden cero:** en un modo cuyo mínimo no es 0 (p. ej. Real Gain, donde el mínimo es ×1 [I]), `SetEMCCDGain(0)` devolvería `DRV_P1INVALID` y la salvaguarda fallaría. Con el modo 0 fijado y releído por `GetEMGainRange` (lo = 0), la ganancia 0 es válida.
- La "salvaguarda de 5×" de `set_emccd_gain`/`set_exposure_time` (`andor_ccd_driver.py:469-510`) se elimina: en modo 0 son 5 unidades de DAC, no ×5, y además `set_exposure_time` **cambia la ganancia** como efecto lateral de fijar una exposición.

### 6.5 Amplificador, velocidad horizontal y preamplificador

- `SetOutputAmplifier(0)`: registro EMCCD [SDK p.298]. La hoja de datos del 885 da velocidades sólo "through EMCCD amplifier" (35, 27 y 13 MHz, todas a 14 bit) [DS-iXon p.2]. La opción "Convencional (1)" del panel (`left_hardware_panel.py:113-116`) se oculta si `GetNumberAmp` = 1 (BANCO-38).
- **Velocidad horizontal:** el legado la tenía **comentada** (`Camera_ps.py:600-603`, "index 2 = 13 MHz"), así que corría con el valor que dejara pylablib, que no se conoce. Propuesta: **13 MHz** (el menor ruido de lectura de la tabla, [DS-iXon p.2]; con 10 s de exposición la velocidad de lectura no importa). Se elige por valor (`GetHSSpeed(0, 0, i)` = 13 MHz), no por índice. Es una decisión nueva: **pregunta al investigador** (§9).
- **Preamplificador:** índice 0, como el legado (`Camera_ps.py:573`), con relectura `GetCurrentPreAmpGain` [SDK p.147]. `GetPreAmpGain(0)` da el factor [SDK p.192].
- `SetFrameTransferMode(0)` explícito [SDK p.278]: en Single Scan con exposiciones largas no aporta, y fija un estado conocido [I].

---

## 7. Timing y watchdog

### 7.1 Presupuesto por ventana (10 s de exposición)

| Tramo | Duración | Fuente |
| :--- | :--- | :--- |
| `SetWavelength` + margen | ≤ 0.3 s + duración real de la llamada | driver actual; BANCO-39 |
| Cambio de red (sólo si cambia) | + 4.0 s | `GRATING_SETTLING_TIME_S`, espera del software (`lab-invariants` §3) |
| Exposición | ≤ 10 s | R4-4 |
| Lectura de un cuadro completo | ≈ 0.08 s a 13 MHz [I: 1.006 Mpx / 13 MHz] | [DS-iXon p.2] |
| `GetAcquiredData` + guardado | ≪ 1 s | [I] |
| **Total** | **< 12 s** (< 16 s con cambio de red) | |

El deadline por defecto del watchdog es 30 s, con poll de 100 ms (`lab-invariants` §1). Aun así, **ningún tramo depende del margen 12 s < 30 s**: el latido se emite en cada tramo de ≤ 250-500 ms, así que la rutina es segura con cualquier exposición que acepte el driver (y el panel hoy permite 60 s, `left_hardware_panel.py:143`).

### 7.2 Dónde va cada `heartbeat_shutter()`

Siempre **sin argumento** (C-29): así rige la política del operador, incluido "Sin límite". Hoy `step_and_glue.py:423, 428` pasa `30.0` y vuelve a armar un corte fijo aunque el operador haya elegido "Sin límite".

| Rutina | ¿Tiene un obturador láser abierto? | Latido |
| :--- | :--- | :--- |
| Calibración (§4) | **Sí**, el de 532, desde K7 hasta el cierre | en `on_tick` de cada tramo de `acquire_single` (≤ 250 ms), en cada tick del margen de asentamiento (≤ 0.5 s), entre cuadros, y justo después de abrir |
| Step & Glue con lámpara (§5) | **No** | **ninguno** (ver 7.3) |
| Step & Glue con láser (si algún día se usa) | Sí | igual que la calibración, y sólo mientras la rutina tenga ese obturador abierto |
| Orden cero (§2) | No (propuesta A cierra todos) | ninguno |

### 7.3 El latido es global al proceso y el satélite PyPrinting comparte proceso

- `heartbeat_shutter()` mueve un único `_watchdog_deadline` del módulo (`core/nidaq.py:204-216`). Con R4-2b, PyPrinting sólo se abre desde el menú Herramientas de PySpectrum, **dentro del mismo proceso**: los dos programas comparten el watchdog.
- **Riesgo:** si Step & Glue con lámpara latiera (como hoy), mantendría vivo cualquier obturador que alguien hubiera dejado abierto en el satélite, y anularía la protección de obturador abandonado mientras dure el barrido (≈ 9 min con 1200 l/mm).
- **Contrato dentro de la política vigente (sin cambiar el watchdog):** una rutina **sólo late mientras ella misma tiene un obturador abierto**. Step & Glue con lámpara no late. Si el operador abrió a mano un láser durante el barrido y nadie lo renueva, el watchdog lo cierra a los 30 s: es el caso para el que existe (obturador ocioso), y **no corta la rutina**, que no usa ese láser. Esto cumple R1-10/R2-8 ("el watchdog nunca corta una rutina sana").
- **Pregunta** (§9): ¿hay algún uso de Step & Glue con un láser abierto a mano, por ejemplo luminiscencia por pasos? Si lo hay, ese modo tiene que abrir el obturador desde la rutina (y entonces late), no a mano.
- **Lo que no se resuelve acá:** dos rutinas en el mismo proceso, cada una con su obturador, comparten un solo deadline; si una se cuelga y la otra late, el obturador de la colgada queda vivo. Eso es el *liveness beat* por rutina de la fase 6.2, que es cambio de política del watchdog y **no está exento** de Rondas 1-2. El bloque A no lo necesita, porque `hardware_session` ya impide dos rutinas de PySpectrum a la vez; el satélite PyPrinting sí podría correr una rutina propia en paralelo (BANCO-35).
- **Proceso colgado o muerto:** si el proceso muere, nadie escribe las líneas; la de 532 (`line11`, activa en BAJO) sin excitación cae a LOW por el pull-down de la placa, que para el 532 es **abierto** (`lab-invariants` §2; BANCO-16). La calibración es la única rutina del bloque A que abre el 532: dura pocos minutos y con el filtro de densidad en baja, pero el riesgo no es cero. No se afirma un fail-safe de hardware que no se midió.

### 7.4 Hilos y bloqueos

- Worker en `QThread` para calibración y Step & Glue (Stop y E-STOP responden en ≤ 250 ms + `AbortAcquisition`).
- El panel izquierdo sigue consultando `GetTemperature`/`GetWavelength`/`GetGrating` cada 1 s (`left_hardware_panel.py:331-343`). Durante una rutina, las lecturas del Shamrock a mitad de un `SetWavelength` bloqueante se serializan con el `RLock` del driver; el panel no debe esperar más de un tick: si el lock está tomado, salta la lectura y muestra "ocupado" [I].
- Ninguna consulta de identidad (`GetSerialNumber`, `GetHeadModel`) en lazos: se leen una vez al conectar.

---

## 8. Ítems de banco consolidados

Ajustados a R4-A. Numeración propuesta a partir de mis BANCO-36 a 42 de la Ronda 1, fusionando los A1-A9 del experimentalista y los P0-P11 del abogado del diablo cuando piden lo mismo. **No se editó `PRUEBAS_BANCO_PENDIENTES.md`.** Orden de ejecución: primero el Grupo E con láseres apagados (BANCO-15 a 19) sobre `main`, después éstos (R4-A 11).

| ID | Qué resuelve | Procedimiento resumido | ¿Acciona algo? | ¿Aprobación? | Fusiona |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **BANCO-25** (existente) | Respaldo de offsets | sonda de lectura con el legado abierto | No | No | P0 |
| **BANCO-36** | Accesorios, límites y ejes del Shamrock | sonda, sólo getters: `GetDetectorOffsetEx` ×4, `Port2`, `GetWavelengthLimits(1..3)`, `AtZeroOrder`, `FlipperMirrorIsPresent`/`GetFlipperMirror(1,2)`, `AutoSlitIsPresent`/`GetAutoSlitWidth(1..4)`, `GetSlitZeroPosition`, `ShutterIsPresent`/`GetShutter`, `EepromGetOpticalParams`, `GetNumberGratings`/`GetGratingInfo`; `GetCalibration(1002)` y `(1004)` frente al cúbico en el mismo estado | No | No | parte de P8 (sólo lectura) |
| **BANCO-37** | Persistencia de los offsets vigentes | leer; apagar y encender el Shamrock; releer; fecha y contenido de `SPECTROG.INI` | No (ciclo de energía, sin escrituras) | No | A1 (persistencia) |
| **BANCO-37b** | Persistencia de un offset **escrito** | la primera escritura real (1200 l/mm) con §3.3; leer en Solis; ciclo de energía; releer | **Sí** (escritura y posible giro, §3.1) | **Sí**, y BANCO-25 hecho | A1 |
| **BANCO-38** | Tablas y capacidades de la cámara | legado abierto, cámara IDLE, sólo getters: `GetNumberAmp`, `GetAmpDesc`, `GetNumberHSSpeeds`/`GetHSSpeed` por amplificador, `GetEMGainRange` en modo 0, `GetCapabilities` (modos de ganancia, `AC_FEATURES_SHUTTEREX`), `GetNumberVSSpeeds`/`GetVSSpeed(i)` (qué índice es 1.9 µs), `GetFastestRecommendedVSSpeed`, `GetTemperatureRange` (DV o DU), `IsInternalMechanicalShutter`, `GetShutterMinTimes`, `IsCoolerOn` | No | No | P3 (parte) |
| **BANCO-39** | ¿Bloquean `SetWavelength`, `SetGrating` y `SetAutoSlitWidth`? | duración de cada llamada para saltos de 20, 200 y 500 nm, cambio de red, y ranura 50 → 100 → 50 µm; relectura al volver | **Sí** (torreta y ranura) | **Sí** (sin láser, EM 0, cámara IDLE) | BANCO-08 (combinable) |
| **BANCO-40** | Pasos por píxel y signo del offset de red | con la fuga de 532 (filtro de densidad en baja, EM 0) y cada red: leer O₀, escribir O₀ ± 10 y ± 20, medir el corrimiento, **restaurar O₀ y releer**; anotar si la torreta gira y si hace falta repetir `SetWavelength` | **Sí** (escritura reversible, láser de 532 atenuado) | **Sí**, y BANCO-25 hecho | A1 (sensibilidad) |
| **BANCO-41** | `SetEMCCDGain` durante una adquisición | tapa puesta, ganancia 0: con Live activo pedir `SetEMCCDGain(0)`; se espera `DRV_ACQUIRING` [SDK p.270] | No (sin luz, pide 0) | No | — |
| **BANCO-42** | Umbral especular por red | lámpara al mínimo, EM 0, 1 ms: con 150 l/mm λc = 70, 60, 55, 50, 45 nm; con 1200 l/mm λc = 8, 7, 6, 5 nm; anotar dónde aparece la imagen especular. Se espera ≈ W/2 (51.5 y 5.8 nm) [I] | **Sí** (torreta) | **Sí** | A7 (en parte) |
| **BANCO-43** | Exposición y ranura seguras en orden cero; píxel de referencia | láseres cerrados, EM 0, lámpara al mínimo: 1 ms en orden cero y en espejo con cada red; cuentas por ms y centro de la imagen de la ranura | **Sí** (torreta) | **Sí** | A7 |
| **BANCO-44** | Un cuadro nuevo por ventana, sin ceros | Step & Glue corregido con la fuga de 532 en un rango que la ponga en ventanas conocidas; contador `GetTotalNumberImagesAcquired` y marca de tiempo por ventana; dos cuadros oscuros seguidos no son idénticos bit a bit | **Sí** (torreta; 532 atenuado) | **Sí** | A9, P4, BANCO-10 |
| **BANCO-45** | Arranque sin escrituras ni mock | (a) 3.0 corregido en hardware con el log de llamadas: ninguna función de §1.4; los valores mostrados coinciden con BANCO-25 y dicen "leído". (b) Con Solis abierto: "Andor no conectada", adquisiciones bloqueadas, ningún espectro | No (el arranque sólo configura la cámara y enfría) | No, pero **después** de BANCO-25 | P1, P2, P3, P7 |
| **BANCO-46** | Stop y E-STOP bajo espera larga | Step & Glue con 10 s por ventana; Stop a los 2 s; en otra corrida E-STOP. Aborto en ≤ 0.25 s + lectura; E-STOP deja `GetEMCCDGain` = 0 | **Sí** (torreta, lámpara) | **Sí** | P5 |
| **BANCO-47** | Un solo camino al orden cero | λc = 30 nm con 150 l/mm, combo "Espejo", Step & Glue con un centro bajo el umbral, `Ctrl+0`, y `set_emccd_gain(50)` en condición especular: todo pasa por el servicio (log) y la ganancia queda en 0 | **Sí** (torreta) | **Sí** (EM 0, láseres cerrados) | P6 |
| **BANCO-48** | Repetibilidad e histéresis de la torreta | 10 ciclos 532 → 600 → 532 y 150 → 1200 → 150 desde abajo; 5 desde abajo contra 5 desde arriba | **Sí** | **Sí** (532 atenuado) | A3 |
| **BANCO-49** | "La línea que camina" | con la fuga de 532 (no hay lámpara de calibración, R4-A 8): λc = 532 − 0.35 W, 532, 532 + 0.35 W por red; la línea tiene que caer en la misma λ ± 1 px; comparar el eje de `GetCalibration` con el cúbico | **Sí** | **Sí** (532 atenuado) | P8, A2 |
| **BANCO-50** | Linealidad y saturación en la calibración | exposiciones T, 2T, 4T con la línea en 15-50 % del ADC (16 383) | **Sí** (532 atenuado) | **Sí** | A6 |
| **BANCO-51** | Deriva del eje λ en la sesión | la línea de 532 cada 5 min durante 2 h desde el encendido, con la temperatura de la sala y del CCD | **Sí** (532 atenuado) | **Sí** | A5 |
| **BANCO-52** | Línea contra ancho de ranura | centroide del 532 con 10, 25, 50, 100 y 200 µm; se espera ≤ 0.5 px porque la ranura es bilateral (R4-A 8) | **Sí** (ranura) | **Sí** | A4 |
| **BANCO-53** | Uniones de Step & Glue con la lámpara | 500-900 nm al 20 % y al 10 % con 150 l/mm, ventana repetida al final y barrido invertido; 800-900 nm con 1200 l/mm | **Sí** | **Sí** | A8, BANCO-07 |
| **BANCO-09** (ampliar) | Quién mueve el obturador del espectrógrafo | además de lo actual: `ShamrockShutterIsPresent`; ¿el `SetShutter` de la **cámara** también lo acciona (comentario del legado "abre shutter camera y shamrock")? | **Sí** (obturador) | No (sin láser) | — |
| **BANCO-21** (existente) | Estado del espejo `line7` al encender | — | — | — | G4 depende de C-08 |
| **BANCO-22** (existente) | Etiqueta del láser de 532 (diodo o DPSS) y su λ | ampliar: anotar la λ nominal y su tolerancia (referencia de la calibración) | No | No | — |
| **BANCO-23** (existente) | Versiones de DLL en el banco | ampliar: `atmcd64d.dll`, `ShamrockCIF.dll`, `atshamrock.dll`; y si pylablib está instalado, su versión | No | No | — |

Requisito previo de todo lo que escriba o mueva: BANCO-25 hecho (respaldo leído), ganancia EM 0 confirmada y láseres cerrados salvo el 532 atenuado cuando la prueba lo diga.

---

## 9. Preguntas al investigador (lado hardware)

1. **Obturadores al entrar en orden cero:** ¿propuesta A (cerrar todos; reabrir a mano) o B (dejar abiertos los que estén con el filtro de densidad en baja)? (§2.3)
2. **¿Se usa alguna vez Step & Glue con un láser abierto** (luminiscencia por pasos)? Decide si Step & Glue late. (§7.3)
3. **Velocidad horizontal:** el legado no la fijaba (código comentado). ¿Acepta 13 MHz (menor ruido) como estado base? (§6.5)
4. **Tope de exposición en el driver:** ¿10 s (R4-4) o más con margen? Hoy el panel permite 60 s. (§2.5-4)
5. **Topes de offset** (2000 pasos absoluto, 300 por escritura) hasta medir BANCO-40: ¿aceptables? (§3.3)

---

## Veredicto

**`TIMING_HAZARD` para el diseño de este documento, a cerrar en el banco; el código actual sigue en `SAFETY_VIOLATION` (Ronda 1).**

- Los contratos eliminan los caminos de daño conocidos: escrituras al arrancar, mock silencioso, orden cero sin ganancia 0 confirmada, cuadros sin exposición, firmas de ranura rotas, latido con argumento.
- Quedan dependencias temporales no medidas: si `SetWavelength`/`SetGrating` bloquean (BANCO-39), el asentamiento real (BANCO-08), la λ real del láser de 532 y la conversión pasos → píxeles (BANCO-40). Hasta medirlas, el diseño usa esperas del software rotuladas como tales y la calibración no propone offsets en pasos.
- Sin fail-safe de hardware medido para el 532 (activo en BAJO) si el proceso muere (BANCO-16).
