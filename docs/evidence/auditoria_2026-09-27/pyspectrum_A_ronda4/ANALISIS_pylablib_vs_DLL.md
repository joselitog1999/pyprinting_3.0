# ¿pylablib o drivers propios sobre las DLL de Andor? Análisis para PySpectrum 3.0

**Fecha:** 2026-09-28.
**Pedido del investigador:** un análisis completo de si conviene controlar la cámara (iXon3 885) y el espectrógrafo (Shamrock 500i) con pylablib o con las DLL de cada uno.
**Estado:** recomendación. **Decide el investigador.**

## 1. Respuesta corta

Las dos opciones usan **las mismas DLL**. pylablib no es otro SDK: es una biblioteca de Python que llama a `atmcd64d.dll` y `ShamrockCIF.dll` por ctypes, igual que los drivers propios. La elección no es qué SDK usar, sino **quién escribe y mantiene la capa de Python sobre ese SDK**.

**Recomendación:** drivers propios para los dos equipos (opción A), con dos refuerzos:
1. declarar los tipos de argumento de todas las funciones de la cámara;
2. usar pylablib en el banco como **oráculo de comparación**. Una prueba toma el mismo cuadro con pylablib, en el entorno del legado, y con el driver de 3.0, y compara.

Si esa prueba muestra diferencias difíciles de corregir, la opción C (cámara con pylablib, como el legado) queda como plan B, con un costo conocido.

## 2. Hechos verificados

**R** = verificado en el repositorio o en la DLL; **W** = documentación web de pylablib; **I** = inferencia.

### 2.1 Las DLL que tiene el laboratorio (R)

| DLL | Versión | Arquitectura | Copias |
| :-- | :-- | :-- | :-- |
| `atmcd64d.dll` (cámara) | 2.104.33065.0, la misma del manual cargado | x64 | idénticas en el repo y en el legado (SHA-256) |
| `ShamrockCIF.dll` y `atshamrock.dll` | 2.103.30023.0 | x64 | idénticas en el repo y en el legado |

El Python del proyecto es de 64 bits. `SPECTROG.INI` lo trae la instalación de Solis en la PC del banco.

### 2.2 pylablib (W)

- **Versión y licencia:**
  - última versión 1.4.5; las anteriores son 1.4.4 (mayo de 2024), 1.4.2 (octubre de 2023) y 1.4.1 (octubre de 2022);
  - declara soporte de Python 3.6 a 3.14;
  - licencia **GPLv3**.
- **Instalación:** no está en el entorno del proyecto ni en la carpeta del legado. Es un paquete de pip. La versión instalada en el banco es desconocida (BANCO-23).
- **Cámara (`AndorSDK2Camera`):**
  - probada por el autor con iXon, Luca y Newton;
  - API completa: modos de lectura (FVB, single-track, multi-track, random-track, image), modos de adquisición, `set_EMCCD_gain`, `set_cooler`, `set_temperature`, `set_fan_mode`, `set_vsspeed`, `set_amp_mode`, `setup_shutter`, `snap`, `wait_for_frame(timeout=…)`, `read_oldest_image`, y un búfer de cuadros con contador.
  - **Al conectar, escribe valores por defecto:** ROI completa, exposición mínima, obturador cerrado, disparo interno, "la velocidad vertical más rápida recomendada" y ganancia EM 0. Además, `fan_mode` vale `"off"` salvo que se pase otro.
  - No puede leer los parámetros de la DLL, porque el SDK no tiene esos getters: sus `get_read_mode()` y `get_fan_mode()` devuelven lo que pylablib recuerda haber escrito. Es la misma limitación que D-15.
- **Espectrógrafo (`ShamrockSpectrograph`):**
  - API completa: red, offset de red, offset de detector, λ, orden cero, ranura, flipper, obturador, filtro, espejo de foco y calibración con geometría de píxeles.
  - Según su código fuente (leído por un resumen web; fuente secundaria), la conexión llama a `ShamrockInitialize("")` y no escribe nada.
  - **Probado sólo con un Kymera 328i conectado por I²C a través de una Newton.** La documentación recomienda abrir la cámara antes.
  - Advierte casos de "valores sin sentido" con una conexión corrupta, y estados que requieren apagar y encender el equipo.
  - Nuestro Shamrock va por USB propio (R4-A-8), así que ese camino no está probado por el autor.

### 2.3 Qué usaba realmente el legado en el banco (R)

- **Cámara: pylablib**, desde el 18/07/24. Las llamadas activas son de la API de pylablib:
  - `setup_image_mode`;
  - `start_acquisition` / `stop_acquisition`;
  - `wait_for_frame`, `read_oldest_image`;
  - `set_exposure`, `set_EMCCD_gain`, `set_amp_mode`, `set_vsspeed`;
  - `set_temperature`, `set_cooler`.

  Las del driver anterior (`ccd_ps.py`) están **todas comentadas**: 23 de `shutter`, 23 de `wait_for_acquisition`, 20 de `abort_acquisition` y 10 de `set_exposure_time`.
  - El legado usaba **sólo el modo Image** (`setup_image_mode(0,1002,0,1002)`). **FVB y Single-Track con pylablib nunca corrieron en el banco**, y son los que PySpectrum 3.0 necesita para Step & Glue y Raman.
  - Tiene un defecto conocido: `self.myAndor.set_acquisition_mode = 'cont'` **pisa el método** de pylablib en lugar de llamarlo (BANCO-02, hipótesis del Live congelado).
  - Conectaba con `AndorSDK2Camera(temperature=10, fan_mode="low")`, o sea, enfriador a +10 °C.
- **Shamrock: no usaba pylablib.** Usaba `Shamrock_ps.py`, el envoltorio ctypes de Andor sobre `ShamrockCIF.dll`. **El camino probado en el banco para el espectrógrafo es ctypes directo.**

### 2.4 Estado de los drivers propios de 3.0 (R)

- **Defectos corregidos hoy** (DEC-040):
  - códigos de modo de lectura equivocados (C-05);
  - la lectura de la ranura con la firma equivocada, que corrompía memoria (C-06);
  - funciones del flipper que no existen (C-07);
  - `SetRandomTrack` en lugar de `SetRandomTracks`;
  - una falla de `GetStatus` leída como "terminó";
  - ceros ante una falla;
  - simulador silencioso.

  **Cinco de estos siete son errores de escribir a mano la capa ctypes**, el tipo de error que una capa generada desde los encabezados del SDK, como la de pylablib, no tiene.
- **Defensas actuales:**
  - `tests/test_driver_dll_exports.py`: cada función llamada existe en la DLL (lectura estática);
  - un doble del SDK con estado debajo del driver real (paso 6);
  - pruebas de contrato del SDK: 8 + 18 + 15 tests;
  - `argtypes` declarados en 4 funciones del Shamrock, y **en ninguna de la cámara todavía**.
- **Superficie que depende de la API del driver de la cámara:**
  - 16 módulos de producción (por ejemplo, 21 llamadas a `get_most_recent_image` y 16 a `set_exposure_time`);
  - 21 archivos de test que usan el simulador.

## 3. Opciones

| | Cámara | Shamrock | En una línea |
| :-- | :-- | :-- | :-- |
| **A** | driver propio | driver propio | lo aprobado en la Ronda 2 |
| **B** | pylablib | pylablib | todo pylablib |
| **C** | pylablib | driver propio | lo mismo que el legado en el banco |
| **D** | fachada propia sobre las funciones de bajo nivel de pylablib | driver propio | la API y las pruebas de 3.0, con la capa ctypes de pylablib debajo (a verificar: que esa capa se pueda usar sola, con qué API) |

## 4. Comparación por criterio

| Criterio | A (propios) | B (todo pylablib) | C (cámara pylablib) | D (fachada sobre pylablib) |
| :--- | :--- | :--- | :--- | :--- |
| **Evidencia de banco** | Shamrock: el mismo camino que el legado. Cámara: sin evidencia | Cámara: sólo el modo Image. Shamrock: **ninguna** (el autor lo probó por I²C, no por USB) | Cámara: modo Image. Shamrock: como el legado | como A para el Shamrock; la cámara usa código de pylablib probado en Image |
| **Riesgo de errores de firma o códigos** | el más alto; mitigado por la verificación de exportaciones y los dobles, y falta declarar `argtypes` en la cámara | bajo, porque la capa se genera desde los encabezados | bajo en la cámara | bajo en la cámara |
| **Control de lo que se escribe al conectar** (nada de calibración; lista blanca con relectura) | total | la cámara escribe sus valores por defecto al conectar (ventilador apagado si no se indica; velocidad vertical "la más rápida", no la del legado) y hay que corregirlos después. El Shamrock no escribe | como B para la cámara | total |
| **Transacción de offsets con doble confirmación** | ya diseñada | posible sobre `set_grating_offset` | igual que A | igual que A |
| **Modo seguro, tests y el doble del SDK** | ya hechos (paso 6) | hay que rehacer el simulador y los dobles al nivel de la API de pylablib | ídem para la cámara | se conservan; cambia sólo la capa de abajo |
| **Hilos** (la espera no bloquea la lectura de temperatura ni el Stop) | ya garantizado y probado | pylablib no documenta ser *thread-safe*; habría que envolverlo con un lock propio y verificar que `wait_for_frame` no lo retenga (I) | ídem en la cámara | se controla en la fachada |
| **Registro de llamadas para BANCO-A3** | directo | hay que interceptar la biblioteca | ídem | directo |
| **Dependencia y licencia** | ninguna | pylablib en pip, con versión fijada a la del banco; **GPLv3**, sin problema para uso interno del laboratorio, pero condiciona una distribución pública del código (el proyecto no tiene archivo de licencia) | ídem | ídem |
| **Mantenimiento** | nuestro | de un autor principal, con versiones cada 1-2 años | ídem | mixto |
| **Costo de migración** | ninguno (ya está) | alto: reescribir los pasos 5 y 6 de los dos equipos, 16 módulos y 21 archivos de test | medio-alto: cámara, simulador y tests | medio: reescribir el interior del driver de la cámara conservando su API |
| **Encaje con lo aprobado en las Rondas 2-4** | total | requiere nuevas Rondas 1-2 (cambio de arquitectura) | ídem | parcial: Ronda 2 corta |

## 5. Riesgos de cada opción

- **A.** Que quede algún error de firma o de semántica del SDK que ni los dobles ni la verificación de exportaciones detecten (por ejemplo, el tipo de un `float*`, o el orden de inicialización). Se mitiga así:
  - declarar `argtypes` en todas las funciones de la cámara, a partir de los prototipos del manual (paso mecánico);
  - la prueba de comparación con pylablib en el banco (§6).
- **B.** El Shamrock por USB con pylablib no tiene ninguna evidencia, y es el equipo que guarda la calibración (offsets en EEPROM). Es el mayor costo de migración, y los valores por defecto al conectar chocan con el arranque "sin escrituras salvo la lista blanca".
- **C.** Reproduce el legado, pero con los modos FVB y Single-Track que el legado nunca corrió. Hay que fijar la versión de pylablib, no pisar sus métodos (el defecto del legado) y envolverlo para los hilos. Pierde parte del trabajo de hoy en la cámara.
- **D.** Depende de que la capa de bajo nivel de pylablib se pueda usar sola y de forma estable entre versiones, y eso hay que verificarlo antes de decidir. Tiene la dependencia y la licencia de B y C.

## 6. Recomendación y cómo validarla en el banco

1. **Shamrock: driver propio.** Es el camino que ya funcionó en el banco (ctypes directo, como `Shamrock_ps.py`). Sus 26 funciones están verificadas contra la DLL, y la escritura de offsets tiene que pasar por la transacción propia. pylablib no aporta evidencia para un Shamrock por USB.
2. **Cámara: driver propio**, con dos refuerzos:
   - **ahora:** `argtypes` y `restype` en todas las funciones de la cámara, desde los prototipos del manual, más un test que compare cada declaración con las funciones exportadas;
   - **en el banco (prueba nueva, BANCO-55):** con Solis cerrado y sin láser, primero el legado con pylablib y después 3.0, con la misma configuración:
     - un cuadro en FVB y uno en Image, 0.1 s, ganancia 0, tapa puesta;
     - comparar el tamaño, el nivel de bias, el ruido de lectura y el tiempo real de exposición;
     - leer lo que pylablib escribe al conectar (ventilador, velocidad vertical) para ver si el banco tenía otro estado.

     **Criterio:** si los dos drivers coinciden dentro del ruido, A queda validada. Si difieren en algo que no sepamos corregir, se pasa a C o D con la diferencia ya identificada.
3. **Cuándo cambiaría la recomendación:**
   - si BANCO-55 o BANCO-45 muestran diferencias de comportamiento del SDK que el driver propio no explique;
   - si más adelante hacen falta muchas funciones del SDK que hoy no se usan (cinéticas, spooling, disparo externo);
   - si el grupo prefiere depender de una biblioteca mantenida por terceros antes que mantener la capa ctypes.

## 7. Lo que decide el investigador

- Qué opción adopta: A (recomendada), B, C o D.
- Si se agrega BANCO-55 a la batería. En cualquier opción sirve para conocer el estado real de la cámara.
- La versión de pylablib instalada en el banco (BANCO-23). Hace falta para C y D, y para interpretar BANCO-55.
