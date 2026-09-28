# Invariantes de Laboratorio — Fuente Única de Verdad para Valores Volátiles

**Propósito**: este archivo es la referencia canónica de los números y rutas que los prompts de
agentes y skills citan sobre el hardware real, el protocolo de muestra y las convenciones de
análisis. Existe porque el corpus de prompts documentó durante días
un watchdog de "500 ms" que en el código nunca existió (`DEC-023`), y la causa no fue descuido
sino estructura: cada archivo
transcribía el valor por su cuenta y nada lo verificaba.

**Cómo usarlo**: las reglas de *comportamiento* siguen viviendo inline en cada agente — un
subagente arranca con su propio contexto y necesita la regla a mano, no un puntero que quizá no
abra. Lo que se centraliza acá son los **valores**, porque el comportamiento no deriva y los
números sí. Si necesitás citar una cifra en un prompt, tomala de esta tabla **con su rótulo de
respaldo**; si la cifra no está acá, verificala contra el código o la fuente primaria antes de
escribirla.

**Garantía mecánica**: las filas marcadas ✅ las verifica
`tests/test_prompt_corpus_integrity.py::test_lab_invariants_match_code` contra el símbolo real
del código en cada corrida de `pytest`: un número (`<ruta>.py::<SIMBOLO>`, o una entrada de
diccionario `<ruta>.py::<SIMBOLO>["clave"]["campo"]`) o una cadena (el primer valor entre backticks de
la columna Valor). Si alguien cambia el código y no esta tabla, el suite falla y nombra la fila.
Las filas marcadas 📄 no son derivables del código y se verifican leyendo la fuente citada. Una
fila 📄 que anota un valor **equivocado** del código pasa al gate cuando se corrige el defecto que
nombra.

**Revisión del 2026-09-27** (fase 1 de `docs/evidence/auditoria_2026-09-27/PLAN_CORRECCIONES.md`):
reescrito contra la bibliografía cargada en `docs/bibliografia/` y las respuestas del investigador
(`RESPUESTAS_INVESTIGADOR.md`). Los valores que la auditoría refutó quedan anotados donde se
reemplazaron, para que no vuelvan a copiarse.

## 0. Rótulos de respaldo

Cada fila declara qué la respalda. **Un documento del propio repositorio (CAT, SYS, MOD, manual,
ledger o prompt) nunca cuenta como respaldo**: la auditoría del 2026-09-27 encontró en ellos
valores sin fuente y valores falsos que se copiaban de un documento a otro.

| Rótulo | Qué significa | Cómo se cita |
| :--- | :--- | :--- |
| **RESPALDADO** | Bibliografía cargada con página, DOI, hoja de datos o código | clave de §9 + "p. N" (página **física** del PDF), o `<ruta>.py::<SIMBOLO>` |
| **DERIVADO** | Cálculo propio a partir de valores respaldados | la fórmula y los insumos, en la misma fila |
| **EXPERIMENTAL** | Dato del investigador sin publicar, o método propio en desarrollo | "investigador, 2026-09-27" + punto de `RESPUESTAS_INVESTIGADOR.md` (R1-n: primera ronda; R2-n: segunda) |
| **SIN FUENTE** | No hay respaldo | no se cita como valor: se mide o se busca la fuente |

"(CIBION)" marca una fuente que describe el microscopio de CIBION y no el banco de INS-UNSAM: sirve
como referencia, no como dato del banco. Las fuentes hechas en el banco de INS-UNSAM son [P25] y
[A25] (este último, en otro microscopio).

---

## 1. Seguridad de hardware y actuación

| Invariante | Valor | Fuente | Respaldo | Gate |
| :--- | :--- | :--- | :--- | :--- |
| Límite de recorrido de la platina, ejes X e Y | `100.0` µm | `config.py::PI_STAGE_RANGE_UM` | RESPALDADO (código) | ✅ |
| Límite de recorrido de la platina, eje Z | `20.0` µm | `config.py::PI_Z_RANGE_UM` | RESPALDADO (código) | ✅ |
| Modelo de la platina y del controlador | PI P-517.3CD (100 × 100 × 20 µm) con controlador E-517 | `README.md` (l. 99) y `DEC-036`; la hoja de datos de PI **no** está en `docs/bibliografia/`. La P-545 de 200 µm de las tesis es la de CIBION ([G17] p. 49) | EXPERIMENTAL hasta BANCO-17 (`qIDN`, `qTMN`/`qTMX`; `tools/bench/pi_stage_probe.py`) | 📄 |
| Incertidumbre del piezo en lazo cerrado | **sin valor** | El 1.50 nm de CAT-203 §3.1 no tiene datos, método ni tipo GUM (L5-203-06). Medir: lectura del sensor a posición fija durante ≥ 10 min, desviación estándar con sus grados de libertad (Tipo A) | SIN FUENTE | 📄 |
| Deadline por defecto del watchdog de obturadores | `30.0` s | `core/nidaq.py::_default_timeout_s` | RESPALDADO (código) | ✅ |
| Intervalo de poll del hilo `ShutterWatchdog` | `0.1` s (100 ms) | `core/nidaq.py::_watchdog_loop` (`time.sleep`) | RESPALDADO (código) | ✅ |
| Política "Sin límite" (modo alineación) | `_default_timeout_s = None` | `core/nidaq.py`; `DEC-010`, `SYS-201` | RESPALDADO (código) | 📄 |

> El watchdog **no** es de 500 ms. Ese valor viene de `DEC-002` (2026-08-20), superada por
> `DEC-010` (2026-09-17) y anotada como tal. Ver `DEC-023` para el árbol causal completo.
>
> El recorrido de Z **no** es de 100 µm. Hasta `DEC-036` los tres ejes se acotaban a 100 µm,
> pero la P-517.3CD da 20 µm en Z. Se adoptó la cota más restrictiva hasta confirmarla con el
> controlador.
>
> **Política del investigador (R1-10, R2-8):** el watchdog nunca debe cortar una rutina sana. La
> protección ante una rutina colgada será un latido de vida emitido por la propia rutina; su diseño
> está pendiente (fase 6.2 del plan, nunca exento) y hasta entonces rige el deadline de la tabla.

## 2. Canales DAQmx y actuadores ópticos

| Invariante | Valor | Fuente | Respaldo | Gate |
| :--- | :--- | :--- | :--- | :--- |
| Placa de adquisición | NI PCIe-6353 con **dos BNC-2110** acopladas | PCIe-6353: [G17] p. 55 y [M24] p. 64 (CIBION); `README.md` (l. 38). Dos BNC-2110: investigador (R1-1); guía [BNC] | EXPERIMENTAL para el banco de INS-UNSAM (confirmar en NI MAX). Qué BNC-2110 lleva qué líneas: sin confirmar (R1-1) | 📄 |
| Obturadores digitales | 532 nm `Dev1/port0/line11` (**activo en BAJO**), 637 nm `line8`, 592 nm `line9`, 808 nm `line10` | `config.py::SHUTTER_CHANNELS`, `SHUTTER_POLARITY`; es el cableado vigente según el investigador (R2-1; X-01 cerrado) | RESPALDADO (código) | ✅ (`test_shutter_lines_match_config`) |
| Espejo de detección (*up/down*) | línea `7` (`Dev1/port0/line7`): *up* → detección confocal y cámara Canon; *down* → espectrómetro, que **sólo** recibe luz con el espejo abajo | `config.py::FLIPPER_532_CHAN`; semántica: investigador (R1-2, R2-4) y legado `scratch/pyspectrum-legacy/Luminescence_ps.py` (lo baja para adquirir, l. 695; lo sube al terminar, l. 747) | RESPALDADO (canal) · EXPERIMENTAL (sentido *up/down*) | ✅ |
| Filtro de densidad, pulso *up* | `Dev1/ao0` → potencia **baja** (escaneos confocales, autofoco) | `config.py::FLIPPER_AO_UP`, pulsado por `up_flipper()` en `core/nidaq.py`; semántica: [P25] p. 38, investigador (R1-2), legado `scratch/pyspectrum-legacy/Shutters_ps.py` (l. 187-189) | RESPALDADO | ✅ |
| Filtro de densidad, pulso *down* | `Dev1/ao1` → potencia **alta** (traza de impresión) | `config.py::FLIPPER_AO_DOWN`, pulsado por `down_flipper()` en `core/nidaq.py`; misma semántica y fuentes | RESPALDADO | ✅ |
| Modulación analógica del láser de 532 nm | `Dev1/ao2` | `config.py::LASER_532_CHANNEL` | RESPALDADO (código) | ✅ |
| Tensión mínima que el software acepta en esa salida | `1.0` V | `config.py::LASER_532_V_MIN`, aplicada por `set_laser532_voltage()` en `core/nidaq.py` | RESPALDADO (código) | ✅ |
| Tensión máxima que el software acepta en esa salida | `5.0` V | `config.py::LASER_532_V_MAX` | RESPALDADO (código) | ✅ |
| Fotodiodos (entradas analógicas) | 532 nm `ai0`, 592 nm `ai1`, 637 nm `ai2`, 808 nm `ai3`, divisor de haz `ai6` | `config.py::PD_CHANNELS` | RESPALDADO (código) | 📄 |
| Posición del fotodiodo del divisor de haz (`ai6`) | en el beamsplitter, ve la emisión transmitida del láser y la mide **después** del obturador y del filtro de densidad; el espejo de detección **no** lo afecta. Con el obturador abierto, "BS con luz y fotodiodo de detección sin luz" indica espejo abajo o detección desalineada | investigador (R4 Q14, R9 P-c, 2026-09-27) | EXPERIMENTAL | 📄 |
| Triggers de posición de la platina | X `ai4`, Y `ai5`, Z `ai3` | `config.py::TRIGGER_CHANNELS` | RESPALDADO (código). **Conflicto:** `ai3` figura a la vez como fotodiodo de 808 nm y como trigger Z (C-44); lo que está cableado se revisa en el banco (R2-6) | 📄 |
| Canales de láser configurados | 532 / 637 / 592 / 808 nm | `config.py::SHUTTERS` | RESPALDADO (código) | 📄 |

> **"Flipper notch 532" es un nombre equivocado**, un error de notación del legado 1.0 (R1-2):
> `line7` no mueve ningún filtro notch, conmuta el **espejo de detección**. El código todavía lo
> llama `FLIPPER_532_CHAN` / `flipper_notch532()`; el renombre es la fase 6.3. El actuador es un
> **conmutador**: el mismo pulso de 3 ms lo cambia de posición en ambos sentidos y el software no
> conoce la posición real, porque el estado vive sólo en memoria y se desincroniza tras un cierre
> forzado (C-08, R2-5). El filtro notch de 532 nm **fijo** del camino de detección sí existe
> ([P25] p. 30, Fig. 2.1) y no se renombra.
>
> **Filtro de densidad**: un solo filtro de densidad neutra en el camino de excitación, común a
> todos los láseres (R1-2; [M24] p. 55 describe el mismo montaje en CIBION). Cada cambio es un
> pulso de 5 V durante 5 ms en la salida correspondiente (`_pulse_flipper()`), y sus tareas deben
> quedar desacopladas de las de los obturadores (`DEC-001`).
>
> **Salida del 532 nm**: como el software acota la tensión a [1.0, 5.0] V, "bajar la salida a
> 0 V" no es una acción ejecutable; para cortar la luz se cierra el obturador (D-08). La curva
> tensión → potencia en la muestra no está medida (B-03).
>
> La cadencia de la traza de impresión **no** es un invariante: en `main` la tarea continua se
> desborda (C-01) y se rediseña en la fase 6.1. No citar "10 kHz" como tasa efectiva (D-01).

## 3. Detector y espectrógrafo

| Invariante | Valor | Fuente | Respaldo | Gate |
| :--- | :--- | :--- | :--- | :--- |
| Ancho del sensor (eje espectral) | `1004` px | `pyspectrum/drivers/andor_ccd_driver.py::DETECTOR_WIDTH_PX` | RESPALDADO (código; [DS-iXon] p. 1) | ✅ |
| Alto del sensor | `1002` px | `pyspectrum/drivers/andor_ccd_driver.py::DETECTOR_HEIGHT_PX` | RESPALDADO (código; [DS-iXon] p. 1) | ✅ |
| Pitch de píxel del detector | `8.0` µm/px | `pyspectrum/drivers/andor_ccd_driver.py::DETECTOR_PIXEL_PITCH_UM` | RESPALDADO (código; [DS-iXon] p. 1) | ✅ |
| Pitch de píxel en el Analizador SIF | `8.0` µm/px | `core/sif_processor.py::CCD_PIXEL_PITCH_UM`: copia literal de la constante del driver, que no se importa porque cerraría un import circular (C-16, `DEC-039`); `test_detector_pitch_is_single_valued` exige que ambas valgan lo que dice la hoja de datos | RESPALDADO (código; [DS-iXon] p. 1) | ✅ |
| Digitalización (ADC) | 14 bit (16 383 cuentas por lectura) a 35, 27 y 13 MHz | [DS-iXon] p. 2 | RESPALDADO. El código supone 16 bit / 65 535 en `sif_analyzer.py` (l. 2499, 3331, 3347) y no tiene un símbolo de profundidad del ADC (C-25) | 📄 (pasa al gate cuando la corrección de C-25 cree el símbolo) |
| Dispersión nominal, red 150 l/mm (blaze 800) | `12.83` nm/mm | `pyspectrum/drivers/shamrock_driver.py::NOMINAL_DISPERSION_150_NM_PER_MM` | RESPALDADO (código) | ✅ |
| Dispersión nominal, red 1200 l/mm (blaze 500) | `1.44` nm/mm | `pyspectrum/drivers/shamrock_driver.py::NOMINAL_DISPERSION_1200_NM_PER_MM` | RESPALDADO (código) | ✅ |
| Ventana espectral del detector (150 / 1200 l/mm) | ≈ 103 / ≈ 11.6 nm | dispersión × 1004 px × 8 µm (`DEC-033`); [M24] p. 60 mide 103 nm (CIBION) | DERIVADO | 📄 |
| Modelo del detector | iXon3 885, cabezal `DU8285_VP`, sensor TI TC285SPD | encabezado de los `.sif` de Solis, `DEC-033` | RESPALDADO | 📄 |
| Enfriamiento mínimo del Peltier | opción DV: −70 °C (aire) / −80 °C (recirculador) / −85 °C (chiller); opción DU: −80 / −90 / −95 °C; máximo −95 °C | [DS-iXon] p. 1-2 | RESPALDADO. **Qué opción está instalada no está confirmado** (placa del cabezal o `GetTemperatureRange`) | 📄 |
| Setpoint operativo del Peltier (SOP Raman) | rango de operación aceptable: −60 a −80 °C (el SOP de CAT-251 §2 usa −60 °C; Solis registró −65 °C) | investigador (R3-D, 2026-09-27); CAT-251 §2; lote L1 de la auditoría | EXPERIMENTAL (investigador): es una elección de procedimiento, no una propiedad del equipo | 📄 |
| Espectrógrafo y torreta | Andor Shamrock 500i (Czerny-Turner) con torreta de **dos redes, 150 y 1200 l/mm, y un espejo** | [P25] p. 33 | RESPALDADO | 📄 |
| Espera que impone el driver tras cambiar de red | `4.0` s | `pyspectrum/drivers/shamrock_driver.py::GRATING_SETTLING_TIME_S` | RESPALDADO (código). Es la espera del software, **no** una medición del giro de la torreta: [DS-SR500] no da ese tiempo | ✅ |
| Puerto de entrada del Shamrock | lateral (*Side*) | investigador (R2-11); coincide con el registro de Solis (C-07); [DS-SR500] p. 4 y p. 8 lo ofrecen como opción de chasis | EXPERIMENTAL | 📄 |
| Offsets del Shamrock (valores del 2026-09-28) | red de 150 l/mm: 85 (el 87 del 2026-09-27 quedó reemplazado); red de 1200 l/mm: 0, **nunca calibrado, a medir en el banco**; detector: 0, **falta un protocolo de calibración** | investigador, leído en Solis el 2026-09-28; calibración de ≈ 2026-08-28 (`RESPUESTAS_INVESTIGADOR.md`, R4-3; antes R2-9) | EXPERIMENTAL | 📄 |
| Calibración del eje λ | con el láser de 532 nm, aproximadamente cada 2 meses: ajuste gaussiano de la línea, atenuada con el filtro de densidad, y relación píxel ↔ λ | investigador (R2-10, R1-7). Práctica del grupo: calibración de fábrica más una corrección verificada con dos láseres ([M24] p. 60, CIBION) | EXPERIMENTAL | 📄 |
| Muestras de referencia Raman | silicio: **sólo verificación**, no patrón de calibración; benzenotiol: muestra de referencia | investigador (R2-18) | EXPERIMENTAL. No se adoptó un valor certificado del fonón del Si: el código usa 520.7 cm⁻¹ (`core/raman_engine.py`, `pyspectrum/modules/calibration_dock.py`) | 📄 |

> ✅ **CONFLICTO DEL PITCH RESUELTO (`DEC-033`, 2026-09-26): 8 µm.**
>
> `DEC-031` había consolidado la geometría en un solo símbolo pero dejó abierto cuál era el
> número (13 µm vivo contra 8 µm en una constante muerta). Seis fuentes independientes zanjan
> que es 8 µm:
>
> | Fuente | Qué establece |
> | :--- | :--- |
> | Hoja de datos Andor iXon3 885 | 1004 × 1002 px, 8 × 8 µm, sensor "VP" (front-illuminated) |
> | Hoja de datos TI TC285SPD-30 | 1004 (H) × 1002 (V), píxeles de 8.0 µm |
> | `reserva/*.sif` (Solis lee la cámara) | cabezal `DU8285_VP`, 1004 × 1002 — `DU8285` no es un error de tipeo |
> | Legado, `Instrument_Shamrock_ps.py:22-24` | `#Camera Andor 885`, `PixelWidth = 8`, usado para calibrar λ desde 2020 |
> | Legado, `StepandGlue_ps.py:576` | ventana de 103 nm con 150 l/mm = 12.83 nm/mm × 8.032 mm |
> | Step & Glue de Solis en esos `.sif` | 5020 = 5 × 1004 puntos para 400–900 nm (~100 nm por ventana) |
>
> El 13 µm no tenía fuente, y no sólo afectaba el overlay: sus dispersiones (0.175 / 0.022 nm/px)
> planificaban el Step & Glue con ventanas de 176 / 22 nm contra 103 / 11.6 reales, lo que en
> hardware habría dejado ~30 % del rango sin medir. El mock usaba el mismo número y lo tapaba.
> `NUMBER_OF_PIXELS` del Shamrock es ahora un alias de `DETECTOR_WIDTH_PX` (por eso ya no tiene
> fila propia), y `get_shamrock()` le informa esta geometría al SDK y la relee antes de
> cualquier calibración. Confirmación opcional en el banco: `GetPixelSize` (sección C de
> `tools/bench/legacy_console_probe.py`; prueba BANCO-01 de `docs/evidence/PRUEBAS_BANCO_PENDIENTES.md`).
> **La consolidación no alcanzó al Analizador SIF**, que conservó su propia constante de 13 µm hasta
> `DEC-039` (C-16): sus escalas µm/px salían infladas ×1.625 y u_slit subestimada un 38 %. Ahora vale
> 8 µm, y un test del gate impide que las dos constantes vuelvan a diferir.
>
> **Offsets del Shamrock**: el código escribe al Shamrock, en cada arranque, offsets inventados
> (red 1 = 12, red 2 = −35, detector 5) desde `pyspectrum/modules/calibration_dock.py` (C-04), y
> por eso PySpectrum 3.0 sigue bloqueado contra el hardware. Los offsets pasarán a ser un
> parámetro con procedencia (fecha y método), calibrable con el láser de 532 nm y el filtro de
> densidad (fase 6.6; R1-7, R2-9).

## 4. Atajos de teclado globales (PySpectrum)

| Acción | Atajo | Fuente autoritativa | Gate |
| :--- | :--- | :--- | :--- |
| **Parada de emergencia** | `Ctrl+E`, `F12` | `pyspectrum/window.py::_setup_shortcuts` | ✅ |
| Alternar vista en vivo | `Ctrl+Space` | `pyspectrum/window.py::_setup_shortcuts` | 📄 |
| Disparar medición | `Ctrl+R` | idem | 📄 |
| Diálogo de orden cero | `Ctrl+0` | idem | 📄 |
| Ventana contrapropagante | `Ctrl+M` | `pyspectrum/window.py` | 📄 |
| Navegación de pestañas 1–7 | `Ctrl+1` … `Ctrl+7` | `pyspectrum/window.py::_setup_shortcuts` | 📄 |

> `Ctrl+Space` **no** es una tecla de pánico. Documentarla como tal fue un defecto real
> corregido en `DEC-023`; el gate lo impide ahora.

## 5. Rutas de registros institucionales

| Invariante | Ruta | Nota | Gate |
| :--- | :--- | :--- | :--- |
| Ledger de decisiones | `docs/decisions/DECISION_LOG.md` | **Un solo archivo append-only.** Nunca un `DEC-xxx_Titulo.md` por decisión. | ✅ |
| Ledger de evidencia | `docs/evidence/EVIDENCE_LEDGER.md` | Plantilla en `TEMPLATE_CLAIM.md` | ✅ |
| Monográficos científicos | `reportes/cientificos/CAT-xxx_*.md` | — | ✅ |
| Especificaciones de sistema | `reportes/sistema/SYS-xxx_*.md` | — | ✅ |
| Manuales de módulo | `docs/modulos/MOD-xx_*.md` | — | ✅ |

## 6. Protocolo de muestra y constantes fisicoquímicas

Son condiciones experimentales, no código. Esta sección reemplaza a la anterior, que prescribía
APTES, 0.75 mM, A_H = 2.5 × 10⁻¹⁹ J, curado a 110 °C y una deriva sin fuente (ver "Valores
retirados", al final).

| Invariante | Valor | Fuente | Respaldo | Gate |
| :--- | :--- | :--- | :--- | :--- |
| Signo de carga del sustrato de impresión | **el mismo** que el de las NP: la repulsión DLVO impide la adsorción espontánea, y la NP se fija sólo por la fuerza óptica | [G17] p. 40; [AN17] p. 2; [M24] p. 37 | RESPALDADO | 📄 |
| Limpieza del vidrio para impresión | sonicación 10 min en Hellmanex 0.2 % v/v → enjuague con Milli-Q → enjuague con acetona → secado a 80 °C → plasma 3 min | [M24] p. 37; [G17] p. 63 (escribe Hellmanex "2 %"; los artículos, 0.2 %); [B21] p. 7 | RESPALDADO | 📄 |
| Funcionalización para NP negativas (citrato) | PDDA 1 mg/mL en NaCl 0.5 M, 15 min, enjuague → PSS 1 mg/mL en NaCl 0.5 M, 15 min, enjuague; guardar en agua | [M24] p. 37; [G17] p. 63. Es el protocolo vigente del banco (investigador, R1-3) | RESPALDADO | 📄 |
| Funcionalización para NP positivas (CTAB/CTAC) | sólo PDDA (superficie positiva) | [M24] p. 37 (paso 2); [B21] p. 7 | RESPALDADO | 📄 |
| Piranha + APTES | **sólo** para sustratos SERS por inmersión, una deposición electrostática masiva con sustrato de signo **opuesto**: Piranha 3:1 H₂SO₄:H₂O₂ 30 min → APTES 1 % v/v en etanol 12 h → inmersión en el coloide. **No** es un protocolo de impresión óptica, y no lleva curado | [A25] p. 46 (INS-UNSAM) | RESPALDADO. Si se documenta, falta el bloque de seguridad de la Piranha, que [A25] tampoco incluye | 📄 |
| Fuerza iónica, protocolo **vigente** | 0.5 mM NaCl | investigador (R2-14, R3-A; rango de trabajo 0.5-1.5 mM, R1-4). Ninguna fuente cargada da 0.5 mM | EXPERIMENTAL (investigador, 2026-09-27) | 📄 |
| Fuerza iónica, protocolo **publicado** | 1.5 mM NaCl | [G17] p. 65; [AN17] p. 9 | RESPALDADO | 📄 |
| Longitud de Debye κ⁻¹ | ≈ 13.6 nm a 0.5 mM; ≈ 7.85 nm a 1.5 mM (el modelo DLVO del grupo usa κ⁻¹ = 8 nm) | κ⁻¹ = √(ε_r ε₀ k_B T / (2 N_A e² I)) para un electrolito 1:1 a 25 °C con ε_r = 78.4, es decir 0.304 nm / √(I [M]); [AN17] p. 10 (κ = 1/8 nm) | DERIVADO | 📄 |
| Potenciales de superficie del modelo DLVO del grupo | NP de Au −47 mV; NP de Ag −54 mV; capa PDDA-PSS −37 mV | [AN17] p. 10 | RESPALDADO como parámetros de modelo. **No** es una medición de ζ del lote en uso | 📄 |
| Constante de Hamaker, Au-agua-vidrio | ≈ 2.1 × 10⁻²⁰ J | fórmula de Lipkin *et al.* para dieléctrico-líquido-metal con los parámetros publicados por el grupo: n₁ = 1.45, n₃ = 1.33, ν₁ = 3.2 × 10¹⁵ s⁻¹, ν₃ = 3.0 × 10¹⁵ s⁻¹, ν_m = 6.2 × 10¹⁵ s⁻¹ para Au ([AN17] p. 9-10; el PDF imprime los exponentes como 10⁻¹⁵, un error tipográfico). Fórmula transcrita en `TRIAGE_TEORICO.md` (T-05) | DERIVADO (recalculado el 2026-09-27: 2.10 × 10⁻²⁰ J) | 📄 |
| Deriva mecánica en XY, valor a usar hasta medir en el banco | 30 nm/min (0.5 nm/s): NP de Au de 60 nm seguida durante 20 min con el botón "Drift Measurement" de PyPrinting. Para dimensionar recentrados, caso peor de 0.5 nm/s por eje | [M24] p. 75 (§3.5) y p. 161 (Apéndice A.2); adoptado por el investigador (R2-13) | RESPALDADO (CIBION). Falta la medición del banco de INS-UNSAM (fase 8) | 📄 |
| Deriva mecánica, rango publicado | 5-50 nm/min | [G17] p. 65 (≈ 5 nm/min); [AN17] p. 3 (< 10 nm/min); [M24] p. 75 (típico, 10-50 nm/min) | RESPALDADO (CIBION) | 📄 |

> Para las NP negativas la fuerza iónica corresponde a la sal agregada. No están declarados la sal
> del protocolo de 0.5 mM ni el aporte del citrato residual del coloide.
>
> **Valores retirados** (no reintroducir; auditoría del 2026-09-27, `TRIAGE_TEORICO.md` T-02 a T-05):
> - **APTES como sustrato de impresión** y su "curado a 110 °C": APTES da un sustrato de signo
>   opuesto al de las NP citrato, es decir, invierte el mecanismo de impresión; el curado no figura
>   en ninguna fuente cargada. APTES pertenece al protocolo SERS de [A25].
> - **0.75 mM / κ⁻¹ ≈ 11 nm** como valor único, atribuido a CAT-110, que no lo contiene. Cae dentro
>   del rango de trabajo, pero no es el valor de ningún protocolo.
> - **A_H = 2.5 × 10⁻¹⁹ J** como Au-agua-vidrio: es un orden de magnitud mayor y corresponde a
>   Au-agua-Au (L3-110-02).
> - **Potencial zeta de −35 mV** atribuido a CAT-110: reemplazado por los parámetros publicados de
>   [AN17].
> - **Deriva de "~1 nm/min"** (ninguna fuente baja de 5 nm/min) y de **15-25 nm/min** atribuida a
>   CAT-105 y CAT-203, que no la contienen; su origen probable son las tablas ilustrativas de
>   CAT-106.

## 7. Inventario óptico

| Invariante | Valor | Fuente | Respaldo | Gate |
| :--- | :--- | :--- | :--- | :--- |
| Láser verde (impresión) | Excelsior-532-150-CDRH | [P25] p. 30; investigador (R2-20) | RESPALDADO | 📄 |
| Objetivo de agua (impresión) | Olympus LUMPLFLN 60XW, 60x, NA 1.0 | [P25] p. 30; [M24] p. 55 | RESPALDADO | 📄 |
| Objetivo de aire | Olympus UPlanFL N 20x (Plan Fluorite), NA 0.5 | [P25] p. 30 y p. 39; [M24] p. 55; investigador (R2-20) | RESPALDADO | 📄 |
| NA del objetivo de agua en el código | `1.00` | `core/sif_processor.py::MICROSCOPE_OBJECTIVES["Olympus LUMPlanFLN 60x W (NA 1.00)"]["na"]` | RESPALDADO (código) | ✅ |
| NA del objetivo de aire en el código | 0.40 (**incorrecto**; debe ser 0.5) | `core/sif_processor.py`, entrada "Olympus 20x Aire (NA 0.40)" de `MICROSCOPE_OBJECTIVES` (D-21) | — | 📄 (pasa al gate al corregirlo) |
| Pinhole de detección confocal | 50 µm, con lente de 150 mm | investigador (R2-20) | EXPERIMENTAL (investigador, 2026-09-27) | 📄 |
| Tamaño del pinhole en unidades de Airy | ≈ 1.5 AU a 532 nm (≈ 1.3 AU a 637 nm) | M = 150 mm / 3 mm = 50 (objetivo de agua 60x con tubo Olympus, f = 3 mm, que es el que se usa para imprimir y para los escaneos confocales: investigador, R3-E); d_Airy = 1.22·λ·M/NA = 32.5 µm a 532 nm con NA 1.0; 50 µm / 32.5 µm = 1.54 | DERIVADO (a partir de un dato EXPERIMENTAL) | 📄 |

> El Laser Quantum Ventus (532 nm) y el MPB (640 nm) de las tesis son del microscopio de CIBION
> ([G17] p. 49). El láser rojo y el IR del banco no están identificados en la bibliografía ([P25]
> p. 30 los omite): se confirman con la placa del cabezal.
>
> `MICROSCOPE_OBJECTIVES` lista además un 10x/0.25, un Nikon 40x/0.60 y un 100x de aceite, que la
> bibliografía del banco no menciona. El Nikon 40x/0.60 coincide con el microscopio Raman de [A25],
> no con el de impresión. El inventario de objetivos se confirma en el banco (B-08).
>
> Los ≈ 4.6 AU que da la bibliografía corresponden a la lente de 50 mm del microscopio de CIBION
> ([Ch17] p. 30). El "0.46 AU super-confocal" de CAT-108 §5.2 sale de usar 2.44·λ·M/NA y es
> incorrecto (T-14).

## 8. Convenciones canónicas

Cortan la familia de errores de factor 2 por convenciones no declaradas (S-1) y la de ξ (S-5). Cada
convención quedará atada por el gate a la función que la implemente, cuando la función exista y
esté corregida.

| Magnitud | Convención | Fuente | Respaldo | Estado en el código | Gate |
| :--- | :--- | :--- | :--- | :--- | :--- |
| σ (desorden posicional o error de localización) | desviación estándar **por componente cartesiana**: ⟨u_x²⟩ = ⟨u_y²⟩ = σ². El desplazamiento cuadrático medio total en 2D es ⟨\|u\|²⟩ = 2σ², y la separación entre dos sitios independientes tiene varianza 2σ² por componente (ensancha g(r) en √2·σ) | [DW-1] p. 13 (Sec. VIII); [DW-5] Ec. 1; [R20] p. 21 (σ_CRB como media de las desviaciones en x e y) | RESPALDADO | sin auditar | 📄 |
| Debye-Waller estático | intensidad de Bragg × **exp(−q²σ²)** en 2D, con desplazamientos gaussianos independientes, σ por componente y q = \|G\| en rad/longitud; equivale a exp(−q²⟨\|u\|²⟩/2). La **amplitud** se atenúa por exp(−q²σ²/2). Paddison define T(G) sobre la amplitud ([DW-3] Ec. 26), así que su intensidad es \|T(G)\|². Con desplazamientos no gaussianos el factor es \|f̃(q)\|² y puede no decaer monótonamente ([DW-2] Ec. 6 y Fig. 4) | [DW-1] p. 13 y Ec. 24 (p. 7); [DW-2] Ec. 6; [DW-3] Ec. 26; nota de convenciones de [DW] | RESPALDADO | sin auditar; el ½ de exp(−½G²σ²) sobre la intensidad (PHY-009) es incorrecto y tiene residuos en CAT-300, CAT-315 §6.3 y MOD-08 (fase 4) | 📄 |
| ξ (longitud de correlación) | ξ = 1/(π·FWHM_f), con f la frecuencia espacial **ordinaria** (f = q/2π, en nm⁻¹) y FWHM_f corregido por el ensanchamiento de tamaño finito. Equivale a una lorentziana 1/[1 + (Δq·ξ)²], cuyo FWHM en q vale 2/ξ | adoptada por el investigador (R2-16). Ninguna fuente cargada fija la relación entre FWHM y ξ ([DW], punto abierto 5); [DW-10] usa la red perfecta simulada como referencia del ancho | EXPERIMENTAL (convención del laboratorio) | tres convenciones distintas en `core/lattice_disorder.py`, ninguna con la resta de tamaño finito (C-14) | 📄 (pasa al gate al corregir C-14) |
| Unidad de Airy (AU) | **diámetro** del disco de Airy en el plano del pinhole: d = 1.22·λ·M/NA. El radio de Airy (primer cero de la PSF) es 0.61·λ/NA en la muestra | [Ce16] p. 50 (radio = primer cero); [Sc16] p. 37 (pinhole expresado en diámetros de Airy) | RESPALDADO | — | 📄 |
| Cintura del haz w₀ | radio al que la intensidad cae a 1/e² (el campo, a 1/e), medido por ajuste gaussiano a imágenes de NP individuales; **no** es 0.61·λ/NA. Medida con 532 nm y NA 1.0: 266 ± 3 nm ([NL17] p. 2), 278 nm ([M24] p. 129) | [M24] p. 63 | RESPALDADO (CIBION) | — | 📄 |
| p (fracción de vacancias) | **por conteo**: p = (partículas planificadas − partículas contadas) / partículas planificadas, sin asignación a sitios ni radio de tolerancia. 1 − p es la "eficiencia de impresión", válida para impresiones de una pasada sin volver a rellenar | [P25] p. 51 (eficiencias de 93 % y 99 %); definición del investigador (R2-17, R3-C) | RESPALDADO | el estimador de Wilson `p_wilson_est` se retira (C-15) | 📄 (pasa al gate al corregir C-15) |
| Base honeycomb (y hBN) canónica | (0, 0) + (⅓, ⅓) con γ = 60°, equivalente a (0, 0) + (⅓, ⅔) con γ = 120°. Primeros vecinos a a/√3, coordinación 3 | [Guo17] p. 6 (factores de estructura de los seis órdenes más bajos); investigador (R2-15) | RESPALDADO | `core/lattice_generator.py` (l. 59-70) usa (⅓, ⅔) con γ = 60°, que arma dímeros a a/3 (C-02). Las muestras impresas con (⅓, ⅓) corregido a mano no se revalidan (R2-15) | 📄 (pasa al gate al corregir C-02) |
| Monte Carlo de Debye-Waller (inversión de σ) | método **en desarrollo**, sin bibliografía propia publicada (R1-9). Se valida de extremo a extremo en σ ∈ [0, 0.3·a], con σ **por componente** (límite de Lindemann según el investigador, R2-19; la definición por componente o RMS total queda para un experimento planificado, R3-B), con el **mismo** estimador para la curva MC y para la medición. Control de orden de magnitud: la precisión de impresión publicada ronda 50 nm RMS radial ([NL17] p. 2; [M24] p. 41), unos 35 nm por componente si es isótropa | investigador (R1-9, R2-19) | EXPERIMENTAL | σ_MC no es publicable (C-11; fase 0.4 del plan) | 📄 (pasa al gate con el test de extremo a extremo de C-11) |

> **Vacancias y Bragg**: si un modelo atenúa los picos de Bragg por vacancias, tiene que declarar
> la normalización. Con sitios ocupados al azar con probabilidad 1 − p, la intensidad normalizada
> **por partícula presente** cae en (1 − p), y **por sitio de la red** en (1 − p)². Es una
> derivación de [DW] (punto abierto 4, a partir de [DW-3] Ecs. 27-29), no contrastada con Kim y
> Torquato (2018): DERIVADO.

## 9. Claves de fuentes

Páginas: **página física del PDF** (la que muestra el visor), no el folio impreso.

| Clave | Referencia | Archivo en `docs/bibliografia/` | Equipo |
| :--- | :--- | :--- | :--- |
| [P25] | A. J. Pereyra, tesis de Licenciatura, 2025 | `Tesis del grupo/Licenciatura/2025_Tesis Abril J. Pereyra.pdf` | banco de INS-UNSAM |
| [A25] | A. Arias, tesis doctoral, 2025 | `Tesis del grupo/ARIAS_Ayelen_TesisFinal_11_11.pdf` | INS-UNSAM, microscopio Raman de 785 nm (no el de impresión) |
| [M24] | L. Martínez, tesis doctoral (UBA), noviembre de 2024 | `Tesis Luciana Martinez.pdf` | CIBION |
| [G17] | J. Gargiulo, tesis doctoral, 2017 | `Julian_Gargiulo_2017.pdf` | CIBION |
| [AN17] | Gargiulo *et al.*, *ACS Nano* (2017), DOI 10.1021/acsnano.7b04136 (versión ASAP) | `Articulos del grupo/2017-Accuracy and Mechanistic Details of Optical Printing of Single Au and Ag Nanoparticles.pdf` | CIBION |
| [NL17] | *Nano Lett.* 17, 5747 (2017), *Understanding and reducing photothermal forces…* | `Articulos del grupo/2017-Understanding and reducing Photothermal Forces.pdf` | CIBION |
| [B21] | Barella *et al.*, *ACS Nano* 15, 2458 (2021) | `Articulos del grupo/2021 - In Situ Photothermal Response of Single Gold.pdf` | CIBION |
| [Ce16] | S. Cerrotta, tesis de Licenciatura, 2016 | `Tesis del grupo/Licenciatura/Santiago_Cerrotta_2016.pdf` | CIBION |
| [Ch17] | G. Chiarelli, tesis de Licenciatura, 2017 | `Tesis del grupo/Licenciatura/German_Chiarelli_2017.pdf` | CIBION |
| [Sc16] | B. Scocozza, tesis de Licenciatura, 2016 | `Tesis del grupo/Licenciatura/Bruno_Scocozza_2016.pdf` | — |
| [R20] | L. Richter, tesis de Licenciatura, 2020 | `Tesis del grupo/Licenciatura/Lars_Richter_2020.pdf` | — |
| [Guo17] | Guo, Hakala y Törmä, *Phys. Rev. B* 95, 155423 (2017) | `redes plasmonicas/2017. Geometry dependence of surface lattice resonances in plasmonic nanoparticle arrays. Physical Review B, 95(15)..pdf` | — |
| [DW] | índice de la carpeta de Debye-Waller estático, con su nota de convenciones | `Debye-Waller estatico y desorden posicional/INDICE.md` | — |
| [DW-1] | A. Gabrielli, *Phys. Rev. E* 70, 066131 (2004) | `Debye-Waller estatico y desorden posicional/2004_Gabrielli_stochastic-displacement-fields.pdf` | — |
| [DW-2] | Klatt, Kim y Torquato, *Phys. Rev. E* 101, 032118 (2020) | `Debye-Waller estatico y desorden posicional/2020_Klatt_randomly-perturbed-lattices.pdf` | — |
| [DW-3] | J. A. M. Paddison, *Acta Cryst. A* 75, 14 (2019) | `Debye-Waller estatico y desorden posicional/2019_Paddison_diffuse-scattering-calculation.pdf` | — |
| [DW-5] | Veatch *et al.*, *PLoS ONE* 7, e31457 (2012) | `Debye-Waller estatico y desorden posicional/2012_Veatch_pair-correlation-localization-error.pdf` | — |
| [DW-10] | Dullens y Petukhov, *EPL* 77, 58003 (2007) | `Debye-Waller estatico y desorden posicional/2007_Dullens_second-type-disorder-colloidal-crystals.pdf` | — |
| [DS-iXon] | hoja de datos Andor iXon3 885 | `Andor_iXon3_885_Specifications.pdf` | hoja de datos |
| [DS-SR500] | hoja de datos Andor Shamrock 500 | `andor-shamrock-500-specifications.pdf` | hoja de datos |
| [BNC] | guía de instalación NI BNC-2110 | `BNC-2110.pdf` | hoja de datos |

Los códigos C-, D-, S-, V-, L-, T- y B- remiten a la auditoría de `docs/evidence/auditoria_2026-09-27/`
(`CONSOLIDADO.md`, `TRIAGE_TEORICO.md` y los lotes); BANCO-nn, a
`docs/evidence/PRUEBAS_BANCO_PENDIENTES.md`.

---

## Al agregar una fila

1. Verificá el valor contra la fuente **antes** de escribirlo; no lo copies de otro prompt ni de
   un CAT, SYS o MOD.
2. Poné el rótulo de §0. Un dato del investigador sin publicar va como **EXPERIMENTAL** con su
   fecha y su punto de `RESPUESTAS_INVESTIGADOR.md`; una cita a la bibliografía lleva la página física.
3. Si el valor vive en un símbolo de código, citalo como `<ruta>/<archivo>.py::<SIMBOLO>` (o
   `::SIMBOLO["clave"]["campo"]` para una entrada de diccionario), poné el valor como primer
   elemento entre backticks de la columna Valor y marcá ✅: el gate lo verifica sin trabajo extra.
   Marcá ✅ **sólo si el código ya tiene el valor correcto**; si no, la fila es 📄 y nombra el
   defecto que la hará pasar al gate.
4. No escribas el símbolo ✅ dentro de una fila 📄: el gate lee como verificable toda fila de
   tabla que lo contenga.
5. Si descubrís que dos fuentes se contradicen, **no elijas una en silencio**: documentá el
   conflicto como en §3 y escalalo. Una escala física equivocada es un evento de laboratorio.
