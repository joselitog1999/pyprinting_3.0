# PySpectrum 3.0, bloque A (primer arranque seguro): Ronda 1

**Fecha:** 2026-09-28.
**Panel:** `instrumentation` (`instrumentation.md`, veredicto SAFETY_VIOLATION), `experimentalist` (`experimentalist.md`, MODIFICATION_REQUIRED) y `devil-advocate` (`devil_advocate.md`, HIGH_RISK_ASSUMPTIONS).
**Fuentes primarias usadas:**
- `docs/bibliografia/Software Development Kit.pdf`: Andor SDK2 v2.104, de cámaras;
- hojas de datos del Shamrock 500 y del iXon3 885;
- las tesis de Martínez y Gargiulo.

**Falta** el manual del SDK del Shamrock. Lo que se dice de los offsets, la ranura y su persistencia sale de los docstrings del legado (`Shamrock_ps.py`) y de documentación web de otro modelo (SR-303): es inferencia o fuente secundaria.

No se ejecutó nada contra el hardware.

## 1. Qué se entendió (paráfrasis)

"Funcional para el banco", en el bloque A, significa cuatro cosas:
1. PySpectrum 3.0 arranca contra el Shamrock y la Andor reales **sin cambiar nada del equipo** que el operador no haya pedido.
2. Muestra el estado **leído** del equipo, no el que el software cree.
3. Ofrece un camino seguro al orden cero y una calibración de offsets y del eje λ con procedencia.
4. Hace Step & Glue con una adquisición real por ventana, sin cortar la rutina con el watchdog.

El orden de prioridad es del investigador: orden cero, calibración, Step & Glue.

## 2. Hallazgos verificados

Cada punto dice cómo se verificó y quién lo informó (I = instrumentación, E = experimentalista, D = abogado del diablo).

### Críticos

1. **C-04, verificado por el orquestador.** El constructor del dock de Calibraciones (`calibration_dock.py:634`, `:1010-1017`) **escribe** al Shamrock:
   - red 1 = 12 y red 2 = −35;
   - detector = 5;
   - cero de ranura = 0.

   No chequea el retorno. El commit del banco, `7f5d10a`, hace lo mismo (l. 526 y 800-801). **PySpectrum 3.0 nunca se abrió en esa PC**, así que el equipo está intacto.
2. **Lectura rota, informado por I y D.** `read_initial_values` llama primero a `ShamrockGetSlit` con tres argumentos, cuando la función tiene dos (C-06). La DLL escribe en una dirección inválida antes de leer los offsets. Si una lectura falla, se muestra el valor viejo como si fuera leído.
3. **Simulador silencioso fuera de SAFE_MODE, verificado.** Si falla la inicialización, la Andor y el Shamrock caen al mock con un `print` (`andor_ccd_driver.py:748-750`, `shamrock_driver.py:785-787`). El operador vería espectros sintéticos como si fueran reales, y eso contradice DEC-036. Ocurre, por ejemplo, **con Solis abierto**.

### Altos

4. **Caminos a la reflexión especular** (I, D).
   - *Cuántos hay:* no son tres sino cinco o seis. Se suman el combo "Espejo" del panel izquierdo y **cualquier λ central menor que media ventana**: ≈ 52 nm con la red de 150 y ≈ 5.8 nm con la de 1200.
   - *Cuánto concentra:* el orden cero junta ~10³ (150) a ~10⁴ (1200) veces más luz que el modo dispersado, y deja pasar todos los láseres (E).
   - *Por qué no protege la salvaguarda:* la de `spectrum_control.py:250-270` **traga las excepciones**, así que falla abierta. Además, `SetEMCCDGain` devuelve `DRV_ACQUIRING` si la cámara está adquiriendo (SDK, p. 270), y ese retorno se ignora.
5. **Ganancia EM en unidades de DAC** (I, D). En el modo por defecto va de 0 a 255 (SDK, p. 271). La "salvaguarda de 5×" y el tope de 1000 no significan lo que dicen.
6. **C-05, confirmado con fuente primaria** (SDK, p. 305): 1 = Multi-Track y 3 = Single-Track. Al corregirlo hay que corregir también el literal `in (0, 1)` de `step_and_glue.py:505` (D).
7. **Step & Glue no sirve contra el hardware** (I, E, D).
   - *Adquisición:* lee el último cuadro sin iniciar ni esperar una exposición (`step_and_glue.py:565-584`). El resultado es un cuadro viejo con aspecto válido, o ceros. El legado esperaba el cuadro (`StepandGlue_ps.py:656-657`).
   - *Retornos:* no chequea el de `SetWavelength`. Si falla la calibración, usa un eje falso de 400-700 nm.
   - *Hilo:* corre en el hilo de la GUI (`window.py:605`), así que Stop y E-STOP no responden. Un barrido con la red de 1200 dura ≈ 10 min.
   - *Watchdog:* llama a `heartbeat_shutter(30.0)` (C-29).
   - *Huecos:* recorta 15 px en cada unión (≈ 4 nm sin medir al 10 % de solapamiento), y con la red de 1200 quedan huecos en el rojo.
   - *Fondo y lámpara:* resta un solo cuadro de fondo para todas las ventanas. Si falta el archivo de la lámpara, usa un cuerpo negro sintético.
   - *Obturador:* pausar el Live cierra el obturador del Shamrock y nadie lo reabre.
8. **La GUI no refleja la cámara** (I, D). Muestra "Enfriador ON, −65 °C" sin haberle enviado nada, y no hay ningún `SetAcquisitionMode`. El legado fijaba `vsspeed = 2` (1.9 µs) y el ventilador en "low"; 3.0 no fija ninguno de los dos.
9. **Efectos laterales al abrir** (verificado el primero).
   - `pi.connect()` (`window.py:586`) cierra los obturadores y **manda la platina a home** con `MOV`.
   - Según D, abrir el tablero de hardware reinicia la cámara y el Shamrock (`hardware_dashboard.py:95` → `hardware_manager.py:223, 247`) y apaga el enfriador. Falta verificarlo.
10. **Satélite PyPrinting en el mismo proceso** (D, inferencias a verificar).
    - Cerrar el satélite desconecta la platina compartida (`app.py:601`).
    - PyPrinting cambia el perfil global (`app.py:429`).
    - Cerrar PySpectrum con el satélite abierto probablemente cuelga la aplicación.
    - El latido del watchdog es global al proceso (I).

### Offsets (E e I, con fuente secundaria)

- **Qué son.** Se expresan en pasos de motor y corrigen el corrimiento de la λ central, no la dispersión.
  - El del **detector** es global.
  - El de **red** vale sólo para la red seleccionada.
- **Persistencia.** Según el SR-303 y dos notas de Andor, se guardan en la EEPROM, así que los ven Solis y el legado.
- **No se pueden separar.** Con una sola línea por red sólo se mide la suma detector + red.
- **Diferencia de geometría.** El legado le informa 1002 px al Shamrock; 3.0 le informa 1004. Una calibración hecha con 1002 px quedaría corrida ≈ 1 px (≈ 0.1 nm) en 3.0.

## 3. Dirección que propone el panel (a aprobar)

- **Archivo de calibraciones:**
  - local a la PC del banco, con una plantilla en el repo;
  - un registro que sólo agrega entradas, indexado por número de serie, red y puerto, con fecha y método.
- **Al arrancar:**
  - **nunca** escribir constantes de calibración: leer, comparar con el archivo y avisar si difieren;
  - **sí** fijar un estado operativo base con relectura, como hacía el legado: modo de lectura y de adquisición, velocidad vertical, ventilador, ganancia EM 0 y puertos.
- **Escribir offsets:** sólo con una acción explícita, en cinco pasos: leer, mostrar la diferencia, respaldar, escribir y releer. Si la relectura no coincide, se avisa.
- **Offset del detector:** fijarlo por convención en 0 y poner las correcciones en cada red. Se toca sólo si las dos redes y el orden cero muestran el mismo corrimiento tras un evento mecánico. Esto reemplaza "idear un protocolo".
- **Protocolo con 532 + filtro de densidad** (E, §2):
  - ganancia EM apagada y exposición creciente hasta llevar el pico al 20-50 % del ADC;
  - acercarse a la λ siempre desde abajo, 5 cuadros, ajuste gaussiano;
  - al menos 3 λ centrales por red, recorriendo el detector;
  - aceptación ≤ 0.5 px con la red de 150 y ≤ 1 px con la de 1200;
  - primero en seco, sin escribir.
- **Orden cero:** un único servicio que falle cerrado (ganancia 0 confirmada, exposición corta, revisión del primer cuadro) y un tope en los drivers para |λc| < W/2.
- **Sin simulador fuera de SAFE_MODE:** si la Andor o el Shamrock no inicializan, se informan como "no conectados", igual que la NI-DAQ en DEC-036.
- **Step & Glue:**
  - en un worker propio;
  - una exposición por ventana, con espera acotada y latido en cada tramo;
  - `AbortAcquisition` al pulsar Stop;
  - chequeo de cada retorno.

## 4. Preguntas para el investigador

Ver la respuesta en el chat del 2026-09-28. Las respuestas se registran en `RESPUESTAS_INVESTIGADOR.md` §R4.

## 5. Pruebas de banco propuestas (se unifican en la Ronda 2)

- I: BANCO-36 a BANCO-42.
- E: A1 a A9.
- D: P0 a P8, y sobre todo P8, "la línea que camina": una línea conocida con λc en λ₀ − 0.35W, λ₀ y λ₀ + 0.35W, por red.

Se incorporan a `PRUEBAS_BANCO_PENDIENTES.md` al cerrar la Ronda 2, sin duplicados.
