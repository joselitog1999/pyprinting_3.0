# Invariantes de Laboratorio — Fuente Única de Verdad para Valores Volátiles

**Propósito**: este archivo es la referencia canónica de los números y rutas que los prompts de
agentes y skills citan sobre el hardware real. Existe porque el corpus de prompts documentó
durante días un watchdog de "500 ms" que en el código nunca existió (`DEC-023`), y la causa no
fue descuido sino estructura: cada archivo transcribía el valor por su cuenta y nada lo
verificaba.

**Cómo usarlo**: las reglas de *comportamiento* siguen viviendo inline en cada agente — un
subagente arranca con su propio contexto y necesita la regla a mano, no un puntero que quizá no
abra. Lo que se centraliza acá son los **valores**, porque el comportamiento no deriva y los
números sí. Si necesitás citar una cifra de hardware en un prompt, tomala de esta tabla; si la
cifra no está acá, verificala contra el código antes de escribirla.

**Garantía mecánica**: las filas marcadas ✅ las verifica
`tests/test_prompt_corpus_integrity.py::test_lab_invariants_match_code` contra el símbolo real
del código en cada corrida de `pytest`. Si alguien cambia el código y no esta tabla, el suite
falla y nombra la fila. Las filas marcadas 📄 no son derivables del código (son constantes
físicas medidas, documentadas en un monográfico) y se verifican leyendo la fuente citada.

---

## 1. Seguridad de hardware y actuación

| Invariante | Valor | Fuente autoritativa | Gate |
| :--- | :--- | :--- | :--- |
| Límite de recorrido de la platina, ejes X e Y | `100.0` µm | `config.py::PI_STAGE_RANGE_UM` | ✅ |
| Límite de recorrido de la platina, eje Z | `20.0` µm | `config.py::PI_Z_RANGE_UM` | ✅ |
| Modelo de la platina | PI P-517.3CD (100 × 100 × 20 µm) con controlador E-517 | README, hoja de datos PI; confirmar con BANCO-17 | 📄 |
| Deadline por defecto del watchdog de obturadores | `30.0` s | `core/nidaq.py::_default_timeout_s` | ✅ |
| Intervalo de poll del hilo `ShutterWatchdog` | `0.1` s (100 ms) | `core/nidaq.py::_watchdog_loop` (`time.sleep`) | ✅ |
| Política "Sin límite" (modo alineación) | `_default_timeout_s = None` | `DEC-010`, `SYS-201` | 📄 |

> El watchdog **no** es de 500 ms. Ese valor viene de `DEC-002` (2026-08-20), superada por
> `DEC-010` (2026-09-17) y anotada como tal. Ver `DEC-023` para el árbol causal completo.
>
> El recorrido de Z **no** es de 100 µm. Hasta `DEC-036` los tres ejes se acotaban a 100 µm,
> pero la hoja de datos de la P-517.3CD da 20 µm en Z. Se adoptó la cota más restrictiva hasta
> confirmarla con el controlador.

## 2. Canales DAQmx

| Invariante | Valor | Fuente autoritativa | Gate |
| :--- | :--- | :--- | :--- |
| Obturadores digitales | 532 nm `Dev1/port0/line11` (**activo en BAJO**), 637 nm `line8`, 592 nm `line9`, 808 nm `line10` | `config.py::SHUTTER_CHANNELS`, `SHUTTER_POLARITY` | ✅ (`test_shutter_lines_match_config`) |
| Flipper notch 532 | `Dev1/port0/line7` | `config.py::FLIPPER_532_CHAN` | ✅ |
| Flippers de potencia (analógicos, desacoplados) | `Dev1/ao0`, `Dev1/ao1` | `core/nidaq.py`, `DEC-001` | 📄 |
| Fotodiodo (entrada analógica) | `Dev1/ai0`, ≤ 10 kHz | `core/nidaq.py`, `SYS-203` | 📄 |
| Canales de láser configurados | 532 / 637 / 592 / 808 nm | `config.py::SHUTTERS` | 📄 |

## 3. Detector y espectrógrafo

| Invariante | Valor | Fuente autoritativa | Gate |
| :--- | :--- | :--- | :--- |
| Ancho del sensor (eje espectral) | `1004` px | `pyspectrum/drivers/andor_ccd_driver.py::DETECTOR_WIDTH_PX` | ✅ |
| Alto del sensor | `1002` px | `pyspectrum/drivers/andor_ccd_driver.py::DETECTOR_HEIGHT_PX` | ✅ |
| Pitch de píxel del detector | `8.0` µm/px | `pyspectrum/drivers/andor_ccd_driver.py::DETECTOR_PIXEL_PITCH_UM` | ✅ |
| Dispersión nominal, red 150 l/mm (blaze 800) | `12.83` nm/mm | `pyspectrum/drivers/shamrock_driver.py::NOMINAL_DISPERSION_150_NM_PER_MM` | ✅ |
| Dispersión nominal, red 1200 l/mm (blaze 500) | `1.44` nm/mm | `pyspectrum/drivers/shamrock_driver.py::NOMINAL_DISPERSION_1200_NM_PER_MM` | ✅ |
| Ventana espectral del detector (150 / 1200 l/mm) | ≈ `103` / ≈ 11.6 nm | dispersión × 1004 px × 8 µm; `DEC-033` | 📄 |
| Modelo del detector | iXon3 885, cabezal `DU8285_VP`, sensor TI TC285SPD | encabezado de los `.sif` de Solis, `DEC-033` | 📄 |
| Capacidad de enfriamiento del Peltier | hasta `−80` °C | `SYS-301` §4.2 | 📄 |
| Setpoint operativo del Peltier (SOP Raman) | `−60` °C | `CAT-251` §2 | 📄 |
| Latencia de conmutación de red de difracción | ≈ `4` s (homing) | `instrumentation.md` §5 | 📄 |

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

## 6. Constantes fisicoquímicas del protocolo (documentales)

Estas no viven en el código: son condiciones experimentales medidas. La fuente citada manda.

| Invariante | Valor | Fuente | Gate |
| :--- | :--- | :--- | :--- |
| Fuerza iónica de trabajo | `0.75` mM NaCl/KCl | `CAT-110` | 📄 |
| Longitud de apantallamiento de Debye | ≈ `11` nm (a 0.75 mM) | `CAT-110` | 📄 |
| Potencial zeta (Au citrato) | ≈ `−35` mV | `CAT-110` | 📄 |
| Constante de Hamaker (Au-agua-vidrio) | ≈ `2.5 × 10⁻¹⁹` J | `CAT-110` | 📄 |
| Curado de APTES | `110` °C | `CAT-101`, `CAT-110` | 📄 |
| Deriva termomecánica de la platina | `15 – 25` nm/min | `CAT-105`, `CAT-203` §3.4 | 📄 |
| Incertidumbre del piezo (lazo cerrado) | `1.50` nm | `CAT-203` §3.1 | 📄 |

---

## Al agregar una fila

1. Verificá el valor contra la fuente **antes** de escribirlo; no lo copies de otro prompt.
2. Si el valor vive en un símbolo de código, citalo como `<ruta>/<archivo>.py::<SIMBOLO>` y marcá ✅ —
   el gate lo va a verificar automáticamente, sin trabajo extra.
3. Si no es derivable del código, marcá 📄 y citá el monográfico o la decisión que lo fija.
4. Si descubrís que dos fuentes se contradicen, **no elijas una en silencio**: documentá el
   conflicto como en §3 y escalalo. Una escala física equivocada es un evento de laboratorio.
