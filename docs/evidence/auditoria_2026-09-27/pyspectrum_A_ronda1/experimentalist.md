# PySpectrum 3.0 · Bloque A · Ronda 1: la mirada del experimentalista

> Calibración del espectrómetro, orden cero y Step & Glue, vistos desde el banco.
> Ronda conceptual (CLAUDE.md §5): no hay código y nada se ejecutó contra el hardware.
> Autor: subagente `experimentalist`, 2026-09-28.

## 0. Cómo leer estas notas

**Rótulos:**

| Rótulo | Qué significa |
|---|---|
| **RESPALDADO** | Lo dice una fuente primaria, citada con su página. |
| **DERIVADO** | Cuenta propia hecha a partir de valores respaldados. Se muestra la cuenta. |
| **INFERENCIA** | Razonamiento físico sin una fuente que lo confirme. Hay que verificarlo. |
| **EXPERIMENTAL** | Dato del investigador que no está publicado. |

**Fuentes usadas:**

| Clave | Fuente | Dónde está |
|---|---|---|
| [DS-SR500] | Hoja de datos del Andor Shamrock 500i | `docs/bibliografia/andor-shamrock-500-specifications.pdf` |
| [DS-iXon] | Hoja de datos del Andor iXon3 885 | `docs/bibliografia/Andor_iXon3_885_Specifications.pdf` |
| [SDK2] | Andor SDK2 User's Guide v2.104 (2023). Es el SDK de las **cámaras**: no trae las funciones del Shamrock | `docs/bibliografia/Software Development Kit.pdf` |
| [M24] | Tesis de L. Martínez (hecha en el CIBION) | `docs/bibliografia/Tesis Luciana Martinez.pdf` |
| [G17] | Tesis de J. Gargiulo (2017) | `docs/bibliografia/Julian_Gargiulo_2017.pdf` |
| [SR303] | Manual del Shamrock 303i (Andor, v4.2, 2024) | web, no está en `docs/bibliografia/`: https://andor.oxinst.com/downloads/uploads/Andor_Shamrock-303_Manual.pdf |
| [AN-cal] | Nota de Andor "Shamrock and Kymera Wavelength Calibration" | web: https://andor.oxinst.com/learning/view/article/shamrock-and-kymera-wavelength-calibration |
| [FAQ055] | Nota técnica de Andor FAQ055, sobre cambiar la torreta de un SR-500/750 | web: https://andor.oxinst.com/assets/uploads/andor-support-resources/FAQ055.pdf |
| [NIST-Hg] | Líneas fuertes del Hg I, NIST | web: https://physics.nist.gov/PhysRefData/Handbook/Tables/mercurytable2.htm |
| [ASTM-E1840] | Guía de patrones de corrimiento Raman | web: https://www.astm.org/Standards/E1840.htm |

**Límites de las fuentes:**
- **No hay un manual primario de las funciones del Shamrock** en `docs/bibliografia/` (el coordinador lo confirmó).
  - Los docstrings de `scratch/pyspectrum-legacy/Shamrock_ps.py` son evidencia secundaria.
  - El manual del SR-303 describe el mismo control de offsets de Solis, pero corresponde a **otro modelo** (distancia focal de 303 mm, píxel de 26 µm). Todo valor numérico que se tome de él vale sólo como orden de magnitud.
- Las páginas de las hojas de datos y de las tesis son las del PDF.

---

## 1. Qué representa físicamente cada offset

### 1.1 Lo que dicen las fuentes

**Unidades.** Los dos offsets se escriben en **pasos del motor** (RESPALDADO, secundario):
- docstrings de `ShamrockSetGratingOffset` y `ShamrockSetDetectorOffset` en `Shamrock_ps.py:2056-2085` y `2363-2395`;
- el mismo archivo define `SHAMROCK_DET_OFFSET_MAX = 240000` y `SHAMROCK_GRAT_OFFSET_MAX = 20000` (`Shamrock_ps.py:49-50`).

**Offset de detector.** Es **global** (RESPALDADO, [SR303] p. 42).
- Corrige cualquier cambio mecánico que desplace el espectro de su posición calibrada: sacar y volver a montar la cámara o la torreta. Según [SR303] p. 27, también sacar la rueda de filtros o el conjunto de la ranura.
- Cita: *"any offset (measured in pixels) will be independent of the grating being used"*.
- La nota [AN-cal] lo confirma: *"will apply to all gratings"*.

**Offset de red.** Hace la misma corrección, pero **sólo para la red seleccionada** (RESPALDADO, [SR303] p. 42 y [AN-cal]).
- Corrige el *yaw* de esa red en la torreta, es decir, dónde queda su posición cero ([SR303] p. 30).
- [DS-SR500] p. 6: al cambiar la torreta *"only a simple offset adjustment is required"*.

**Qué corrigen y qué no.** Los offsets corrigen el **corrimiento de la longitud de onda central**, no la dispersión (RESPALDADO, [FAQ055]).
- [FAQ055] separa las dos cosas: *"Correcting for centre wavelength offsets should be done using the Offset Adjustment tool"*; la dispersión se reoptimiza con otra herramienta (*Dispersion Optimiser*).

**Dónde se guardan.** Quedan en la **EEPROM del Shamrock** y se aplican en cada encendido (RESPALDADO, [AN-cal] y [SR303] p. 43).
- Por eso una escritura equivocada **persiste**, y la ven también Solis y el legado.

**Escala.** Regla práctica de [SR303] p. 43 para el 303i: *"approx. 3 units will offset the spectral line by 1 pixel (26 micron wide pixel)"*. Para el 500i no hay dato.

### 1.2 Qué error produce cada uno en el eje λ

**Sobre el eje λ, los dos producen un corrimiento rígido del espectro sobre el detector.**

**Offset de detector (DERIVADO de [SR303] p. 42).**
- Corre el espectro δ_D píxeles, con δ_D igual para todas las redes.
- En longitud de onda, el error es Δλ = δ_D · (dλ/dx)_red, así que depende de la red:
  - con 150 l/mm, 1 px ≈ 0.103 nm (12.83 nm/mm × 8 µm; `lab-invariants` §3);
  - con 1200 l/mm, 1 px ≈ 0.0115 nm (1.44 nm/mm × 8 µm).
- Dentro de una misma red, depende sólo de forma débil de λ central, a través de la variación de la dispersión.

**Offset de red (INFERENCIA con cuenta propia).**
- Si el offset es un corrimiento del ángulo de la red (pasos del mismo motor), sobre el detector produce un corrimiento Δx ≈ f·Δφ·(1 + cos α / cos β).
  - α y β son los ángulos de incidencia y de difracción, y f = 500 mm.
- En orden cero (α = β) el factor vale 2, como en un espejo.
- En orden 1:
  - con 150 l/mm los ángulos son chicos y el factor se aparta de 2 menos de ~1 %;
  - con 1200 l/mm a 532 nm, en aproximación de Littrow (sin el ángulo de desviación del instrumento, que no está en la hoja de datos), el factor baja un ~4 %, y a 800 nm un ~7-8 %.
- **Consecuencia:** medido en píxeles, un offset de red también es casi independiente de λ.

### 1.3 Consecuencia práctica: con una sola línea no se separan los dos offsets

**Para cada red sólo es observable la suma "offset de detector + offset de red".** Con una línea conocida y una red se mide un corrimiento, que es esa suma en píxeles.
- Con dos redes se miden dos sumas, que tienen tres incógnitas (D, G150, G1200).
- La dependencia en λ del efecto del offset de red (§1.2) es de pocos por ciento: no permite separarlos en la práctica, porque exigiría resolver fracciones de píxel sobre desplazamientos de pocos píxeles.
- Rótulo: DERIVADO.

**El procedimiento de Andor elige una convención** (RESPALDADO como procedimiento, [SR303] p. 43 y [AN-cal]):
1. primero se centra la línea con el offset de detector, usando una red;
2. después se ajusta cada red con su propio offset.

**Propuesta para el banco (INFERENCIA; la decisión es del investigador, pregunta P2):**
- **D = 0 queda fijo como referencia.** Desde fábrica, o desde el último montaje, D representa la posición mecánica de la cámara y de la entrada.
- Toda corrección rutinaria (la de cada ~2 meses con 532 nm) va a los **offsets de red**.
- **"Calibrar el offset de detector" pasa a ser un diagnóstico de modo común** (§2.4). Sólo se toca D cuando las dos redes, y la imagen de orden cero de cada una, muestran **el mismo** corrimiento en píxeles después de un evento mecánico (cámara, ranura o torreta).
- Así el historial de cada red no se contamina con un evento que no le corresponde.

### 1.4 Lo que no se sabe todavía (medir en el banco)

- **La sensibilidad de cada offset**, en píxeles por unidad.
  - Si el 500i tuviera la misma resolución angular por unidad que el 303i, 1 unidad movería ~1.8 px de 8 µm. Cuenta: 26 µm / 3 × 500/303.
  - Con esa escala, el 85 de la red de 150 equivaldría a ~150 px (~15 nm), demasiado para un equipo calibrado de fábrica. Eso sugiere que la unidad del 500i es más fina.
  - Hay que **medirla** (BANCO-A1). De ella depende la cuantización: si una unidad vale más de ~0.5 px, lo que queda por debajo de una unidad tiene que guardarse como corrección por software, en píxeles, en el archivo de calibración.
- **Si una escritura en la EEPROM toma efecto al instante** o recién con el próximo `SetWavelength`. Rótulo: INFERENCIA; se verifica en BANCO-A1.
- **A qué geometría pertenece el 85.** El legado declaraba 1002 píxeles al SDK (`Instrument_Shamrock_ps.py:22`, `Spectrum_ps.py:157`); 3.0 declara 1004.
  - Si el 85 se ajustó con el eje del legado, en 3.0 queda corrido ~1 px (≈ 0.10 nm con 150 l/mm; BANCO-14).
  - Si se ajustó en Solis, que conoce los 1004 px, no hay corrimiento. Pregunta P1.

---

## 2. Protocolo de calibración de offsets con el láser de 532 nm y el filtro de densidad

### 2.0 Principio

Se usa como patrón el láser de 532, en la **misma trayectoria de detección** que las medidas.
- La calibración incluye así todo lo que corre el espectro: el offset mecánico y la posición de la imagen del spot sobre la ranura (ver §6.2).
- Es la práctica del grupo: calibración de fábrica más un valor de corrección que *"se verifica con la incidencia de dos láseres distintos"* ([M24] p. 60, CIBION; RESPALDADO como práctica).

### 2.1 Condiciones previas (todas obligatorias)

1. **Respaldo.** Leer y anotar los offsets actuales de las dos redes, del espejo, del detector y del cero de la ranura con el legado o con Solis (BANCO-25). Mientras C-04 siga abierto, PySpectrum 3.0 no debe arrancar contra el Shamrock.
2. **Térmica.**
   - El EMCCD, estabilizado a su temperatura de trabajo: `GetTemperature` debe devolver el estado estabilizado ([SDK2] p. ~200, `GetTemperature`).
   - La sala, estable. [SR303] p. 6 pide *"keep room temperature as stable as possible"*; [DS-SR500] p. 15, *"stable ambient"*.
   - Esperar al menos 30 min desde el encendido del Shamrock y de la cámara. El tiempo es INFERENCIA; se ajusta con BANCO-A5.
3. **Óptica.**
   - Los filtros de la detección, en la configuración de uso: notch dentro o fuera (pregunta P1).
   - La ranura, en el **ancho con que se va a medir**. Si la ranura es unilateral, la posición de la línea depende del ancho (§6.3, BANCO-A4).
   - Polarizadores y láminas de onda, como en la medida.
4. **Detector** (seguridad y linealidad):
   - **Ganancia EM apagada** (o ×1), por dos razones:
     - la línea de 532 es brillante, y [SDK2] p. 270 (`SetEMAdvanced`) advierte que por encima de x300, con más de *"tens of photons per pixel"*, hay *"accelerated ageing of the sensor"*;
     - un desborde del registro de ganancia (80 000 e⁻, [DS-iXon] p. 1) arrastra carga **en la dirección del registro serie, que es el eje espectral**, y sesga el centroide. Rótulo: INFERENCIA sobre el mecanismo.
   - **Exposición inicial mínima.** Duplicarla hasta que el pico, restado el bias, quede entre ~20 % y ~50 % del fondo de escala del ADC. El ADC es de 14 bit, 16 383 cuentas ([DS-iXon] p. 2); el código supone 16 bit (C-25), así que el criterio va en cuentas de 14 bit.
   - No se conoce la conversión e⁻/cuenta, así que no se sabe qué satura primero: el pozo de 32 000 e⁻ ([DS-iXon] p. 1) o el ADC. Por eso la linealidad se comprueba con la prueba de duplicar la exposición (§2.5).
5. **Láser.**
   - **Filtro de densidad arriba**, es decir, potencia baja (`ao0`; `lab-invariants` §2).
   - Espejo de detección `line7` abajo. No tiene realimentación: se confirma con el criterio del fotodiodo del BS (`lab-invariants` §2).
   - Obturador de 532 (activo en bajo) abierto sólo durante las adquisiciones, con el heartbeat renovado en cada iteración.
   - Una estimación de por qué hace falta tanta atenuación (INFERENCIA): una reflexión de ~1 nW en la ranura son ~2.7·10⁹ fotones/s. En 10 ms, ~10⁷ e⁻ concentrados en pocos píxeles: **varios órdenes por encima del pozo**. Hace falta la fuga a través de los notch, o una atenuación equivalente de ~10⁻⁶, además del filtro de densidad. [M24] p. 72 confirma que la línea del láser se ve *"incluso teniendo dos filtros Notch"*.
6. **Controles.**
   - Un cuadro oscuro (obturador del láser cerrado) con la misma exposición y el mismo ROI, antes y después.
   - Un cuadro con el láser abierto y el espejo **arriba**: tiene que salir oscuro. Es el control de que la luz viene por el camino previsto.

### 2.2 Adquisición y ajuste (igual para las dos redes)

1. **Posicionar.** Llevar la red a λc = λ_ref, siempre **acercándose desde abajo**: primero a λ_ref − 20 nm con 150 l/mm, o λ_ref − 3 nm con 1200 l/mm, y después a λ_ref. Así se neutraliza una posible histéresis de la torreta (BANCO-A3).
2. **Adquirir.** Tomar N = 5 cuadros en modo Imagen, que evita binnear en el chip una línea brillante. Usar un ROI de filas sobre la traza del spot; el legado usaba 9 filas (`StepandGlue_ps.py:832-841`; [M24] p. 60). Restar el oscuro.
3. **Ajustar.** Ajuste gaussiano + fondo lineal en ±3 FWHM de la línea. El ajuste da el centroide x̂ en píxeles y su incertidumbre.
   - La precisión estadística es ~σ_línea/√N_e. Con ~10⁵ e⁻ y un σ de ~2.5 px sale ~0.01 px (DERIVADO): **dominan los sistemáticos**.
4. **Calcular el residuo.** Leer el eje λ(x) del SDK **en esa posición** (`ShamrockGetCalibration` con 1004 px y 8 µm), evaluarlo en x̂ y calcular el residuo r = λ(x̂) − λ_ref.
   - Pasado a píxeles: r_px = r / (dλ/dx).
   - **No hace falta suponer cuál es el "píxel central"**: con este método desaparece la ambigüedad entre 501.5, 502 y 500.5.
5. **Convertir a unidades.** Δunidades = −r_px / S, donde S es la sensibilidad en px/unidad medida en BANCO-A1, redondeado al entero.
6. **Escribir y releer.** Escribir sólo con una acción explícita del operador (R4-3), releer, volver a llevar la red a λ_ref desde abajo y repetir los pasos 2-4.
7. **Guardar.** Lo que quede por debajo de una unidad va al archivo de calibración como corrección de software en píxeles, con su signo.

### 2.3 Criterios de aceptación

**Referencia de la hoja de datos** ([DS-SR500] p. 13 y notas 19-20 en p. 15; RESPALDADO): exactitud de 0.04 nm y repetibilidad de 10 pm, ambas medidas con la red de 1200 l/mm.
- La repetibilidad es la σ de 20 medidas en las que la torreta se mueve 10 veces entre medida y medida, **incluidos cambios de red**.
- Pasada a píxeles con 1200 l/mm: 10 pm ≈ 0.9 px y 0.04 nm ≈ 3.5 px (DERIVADO).
- **La repetibilidad es angular** (INFERENCIA): con la red de 150 debería rondar también ~1 px, o sea ~0.1 nm. Para este banco, "1 px" es el piso realista para las dos redes.

**Criterios propuestos** (a ajustar con la tolerancia que pide el grupo, pregunta P8):

| Magnitud | 150 l/mm | 1200 l/mm |
|---|---|---|
| Residuo en la línea de calibración, después de corregir (hardware + software) | ≤ 0.5 px (≈ 0.05 nm) | ≤ 1 px (≈ 0.012 nm) |
| Repetibilidad: σ en 10 ciclos ida y vuelta, con cambios de red | ≤ 1 px | ≤ 1 px |
| Verificación en líneas lejanas (§2.6), sin volver a ajustar | ≤ 1 px en el centro; ≤ 2 px en los bordes | ≤ 3.5 px (0.04 nm, la exactitud de la hoja de datos) |
| Linealidad: pico con exposición T y con 2T | cociente 2.00 ± 0.04; centroide igual ± 0.05 px | ídem |
| Deriva en la sesión (BANCO-A5) | anotar px/h; si pasa 0.5 px/h, recalibrar antes de medir | ídem |

### 2.4 Cómo se separan el offset de red y el de detector (modo común)

1. Medir r_px con la red de 150 y con la de 1200 en la misma línea (532 nm), con las condiciones de §2.1.
2. Medir también, en orden cero, la posición del centro de la imagen de la ranura para cada red y compararla con la de referencia guardada en la última calibración (§3.2). Esto no necesita ningún patrón de λ.
3. **Decidir:**
   - **Si r_px(150) ≈ r_px(1200) ≈ corrimiento en orden cero** (diferencias ≤ 0.5 px) y hubo un evento mecánico, es modo común: se corrige **D** con una sola escritura y los G quedan como estaban.
   - **Si no,** se corrige cada G por separado.
4. Hace falta la sensibilidad S_D del offset de detector, medida aparte en BANCO-A1. [SR303] p. 43 sugiere que es distinta de S_G.

**¿Hace falta una segunda línea conocida?**
- **Para el offset, no:** una línea por red alcanza.
- **Para validar que el offset sirve lejos de 532, y para verificar la dispersión, sí.** Por orden de preferencia:

**(a) Recorrer el detector con una sola línea** (*line walk*; INFERENCIA, método propio). Es lo que más rinde sin comprar nada.
- Con la línea de 532, llevar λc a:
  - con 150 l/mm: 532, 532 ± 20 y 532 ± 40 nm;
  - con 1200 l/mm: 532, 532 ± 2 y 532 ± 4 nm.
- Registrar x̂ en función de λc.
- **La pendiente es la dispersión medida en px/nm.** Los residuos, comparados con el eje del SDK, dan la no linealidad del eje en los bordes.
- **El signo de la pendiente confirma que el eje no está invertido** (§6.9).
- La exactitud del motor (0.04 nm) entra en el resultado, pero es chica frente a lo que se busca.

**(b) Lámpara atómica** (Hg-Ar o Ne en lápiz), el método que recomienda Andor ([SR303] p. 43, [AN-cal]). Da líneas exactas:
- Hg: 404.656, 435.833, 546.074, 576.960 y 579.066 nm en aire ([NIST-Hg]);
- Ne: 703.24 nm ([SR303] p. 43).
- **Un tubo fluorescente de techo emite las mismas líneas del Hg.** Es una alternativa gratuita si hay uno que pueda iluminar la ranura. Rótulo: INFERENCIA, práctica común; pregunta P3.
- Con 150 l/mm, un centro de 560 nm (508-612 nm) muestra **en un mismo cuadro** 532, 546.07 y el doblete 576.96/579.07: la dispersión se verifica sin mover la torreta.

**(c) Otros láseres del banco** (592, 637 y 808 nm).
- Si son diodos, su λ depende de la temperatura y de la corriente, con variaciones del orden del nm (INFERENCIA; pregunta P4). Sirven para verificar la dispersión dentro de un cuadro (532 y 592 caben juntos con 150 l/mm), no como patrón absoluto.
- Pueden servir como patrón secundario si antes se miden con la red de 150 ya calibrada.

**(d) Patrones Raman** (§2.6): dan corrimientos, no λ absolutas.

**(e) Segundo orden del 532** (INFERENCIA).
- Con 150 l/mm, el 532 en orden 2 cae donde caería 1064 nm en orden 1.
- Dejaría verificar el offset con un ángulo de red muy distinto, usando la misma fuente.
- Requiere más exposición: el QE a 1064 es bajo. Es opcional.

### 2.5 Controles y pruebas propias del protocolo

- **Linealidad:** exposición T y 2T (criterio en §2.3).
- **Repetibilidad:** 10 ciclos 532 → 600 → 532 y 150 → 1200 → 150, siempre acercándose desde abajo (BANCO-A3).
- **Histéresis:** 5 veces desde abajo contra 5 veces desde arriba. Si la diferencia pasa 0.5 px, el Step & Glue tiene que acercarse siempre desde el mismo lado (§4).
- **Oscuro y espejo arriba:** los controles de §2.1-6.

### 2.6 Qué λ centrales usar y por qué

**Red de 150 l/mm** (dispersión de campo oscuro, 450-950 nm; [M24] p. 60):

| λc | Para qué |
|---|---|
| 532 nm | calibra el offset |
| 532 ± 20 y ± 40 nm | recorrido del detector (dispersión y signo) |
| Una λ azul-verde y otra roja-NIR, por ejemplo Hg 435.83 y Ne 703.24, o 808 si se conoce su λ | verifican que un solo offset sirve en todo el rango de uso |

- Justificación: el offset corrige un ángulo, y el modelo del SDK lo propaga a todas las λ. **Hay que confirmar que el modelo es correcto en los extremos que se usan.**
- Mínimo: 3 λc.

**Red de 1200 l/mm** (nunca calibrada; se usa sobre todo en Raman, entre 532 y ~600 nm):
- **λc = 532** calibra el offset; el recorrido va a 532 ± 2 y ± 4 nm.
- **Verificación en la región Raman**, que es donde se usa la red:
  - Hg 546.07, 576.96 y 579.07 nm;
  - Si: 520.7 cm⁻¹ → 547.2 nm con bombeo de 532 (DERIVADO: 1/λ = 1/532 − 520.7·10⁻⁷ nm⁻¹);
  - ciclohexano ~802 cm⁻¹ → 555.7 nm ([ASTM-E1840]; los otros valores hay que tomarlos de la norma);
  - benzenotiol ~1000 cm⁻¹ → ~562 nm.
  - Mínimo: 3 λc.
- **El benzenotiol en SERS no sirve como patrón** (INFERENCIA): sus picos se corren algunos cm⁻¹ según el sustrato y la adsorción. Como patrón conviene el líquido puro; [A25] cita a Aggarwal *et al.*, *Appl. Spectrosc.* 66, 740 (2012), con valores a verificar. El Si calienta con el láser y su fonón se corre hacia el rojo con la temperatura, así que se mide a potencia baja (INFERENCIA).

**La λ exacta del láser no es crítica para el Raman, si el cálculo es coherente** (DERIVADO).
- Si se calibra el eje suponiendo que el láser está en 532.00 nm y los corrimientos se calculan con ese mismo 532.00, un error real de 0.1 nm en la λ del láser produce, a 1000 cm⁻¹, un error de sólo **~0.37 cm⁻¹**.
  - Cuenta: 0.1 nm × (1/532² − 1/561.9²) nm⁻² = 3.7·10⁻⁸ nm⁻¹.
- Si en cambio se calibra con una lámpara y se usa 532.00 nominal en la fórmula, el error sube a **~3.5 cm⁻¹**.
- **Regla:** la λ del láser que se usa al calibrar y la que se usa en la fórmula de corrimiento tienen que ser el mismo número, guardado en el archivo de calibración.
- Para las λ absolutas, por ejemplo el máximo plasmónico, 0.1 nm es irrelevante.
- Distinción aire/vacío (INFERENCIA; Andor usa líneas en aire): 532 nm en aire son ~0.15 nm menos que en vacío. Hay que fijar la convención, aire, y registrarla.

### 2.7 Qué registrar en cada calibración (procedencia; R4-3)

- **Cuándo y cómo:** fecha y hora; operador; método (§2.2, recorrido, lámpara).
- **Configuración óptica:** red; λc; λ_ref y la convención aire/vacío; ancho de ranura; filtros en la detección; filas del ROI.
- **Detector:** exposición; ganancia EM; temperatura del CCD y su estado; bias.
- **Ambiente:** temperatura de la sala, si hay termómetro.
- **Offsets:** los valores antes y después (red, detector, espejo); la sensibilidad S; el residuo en px, con la corrección de software; la σ de repetibilidad.
- **Software:** la geometría declarada al SDK (1004 px, 8 µm) y el programa con su versión.

---

## 3. Orden cero

### 3.1 Para qué se usa en la práctica

Casi nunca se usa (R2-11; EXPERIMENTAL). Los usos legítimos son:

1. **Alinear y enfocar la ranura:** foco del detector, posición vertical de la traza, *roll* y *tilt* de la red. [SR303] p. 30-31 usa el orden cero con ese fin (RESPALDADO como práctica de Andor).
2. **Calibrar el ancho de la ranura contra píxeles** (BANCO-13).
3. **Ver la muestra con el EMCCD para elegir la fila de partículas que entra en la ranura.**
   - [G17] p. 54 lo hace con la **posición espejo de la torreta**: *"If the mirror is chosen in the torrete, dark field imaging … is possible. The entrance slit is closed to select a row of particles"*.
   - El legado también tiene el espejo como red 3 (`Instrument_Shamrock_ps.py:13-15`). Para ver la muestra, el espejo es la opción natural, no el orden cero de una red.
4. **Chequeo rápido de la salud de los offsets sin patrón de λ** (§2.4): la posición de la imagen de la ranura en orden cero, comparada con la guardada.

### 3.2 Qué riesgo tiene para el EMCCD

**En orden cero no hay dispersión: toda la banda que deja pasar la óptica cae sobre la imagen de la ranura** (DERIVADO).
- Con luz de banda ancha, el aumento de irradiancia por columna respecto del modo dispersado es ~B/(s·δλ).
  - B es la banda; s, el ancho de la imagen de la ranura en px; δλ, la dispersión en nm/px.
  - Magnificación ~1 ([DS-SR500] p. 2 da 1 en vertical; que en horizontal también sea ~1 es INFERENCIA).
- Con B ≈ 600 nm (la lámpara, entre 400 y 1000 nm) y una ranura de 50 µm (s ≈ 6 px):
  - **~10³ veces con 150 l/mm y ~10⁴ con 1200 l/mm.**
- Para una línea láser angosta, la concentración es ~1: la línea ya era una imagen de la ranura. El riesgo de verdad está en:
  - la lámpara de campo oscuro, la iluminación de la cámara Canon y la luz de la sala;
  - **todos los láseres a la vez**: en orden cero no hay ventana espectral que deje afuera al 592, al 637 o al 808. Los notch de 532, si están, bloquean sólo el 532.

**Con ganancia EM alta** se aplica la advertencia de envejecimiento acelerado ([SDK2] p. 270). También puede desbordar el registro de ganancia (80 000 e⁻, [DS-iXon] p. 1).
- Nota: `SetSaturationEvent`, el aviso de saturación dañina del driver, existe **sólo con la placa PCI CCI-23** ([SDK2] p. 307). No hay que contar con él sin confirmar qué placa hay.

### 3.3 Condiciones mínimas que debería imponer el programa

1. **Un único camino al orden cero y a la posición espejo, con la misma salvaguarda:**
   - Hoy `calibration_dock.py:715-721` (`goto_zero_order`) **no tiene ninguna salvaguarda**.
   - `spectrum_control.py:250-270` la tiene, pero **traga las excepciones con `pass`**: si no puede bajar la ganancia, sigue igual. Tiene que fallar cerrado.
2. **Antes de mover** (orden cero, λ ≤ ~1 nm o la posición espejo):
   - ganancia EM apagada y **confirmada por relectura**;
   - obturadores de los láseres cerrados y confirmados (DEC-036);
   - si existe, el obturador del Shamrock cerrado (BANCO-09);
   - exposición en un valor seguro, del orden de 1-10 ms, a definir con BANCO-A7.
3. **El primer cuadro al llegar se revisa:** pico, restado el bias, menor que ~50 % del ADC. Si lo supera, se cierra y se avisa.
   - No se deja subir la ganancia EM mientras se está en orden cero sin una confirmación explícita, y nunca por encima de x300 ([SDK2] p. 270).
4. **Abrir un láser en orden cero** exige el filtro de densidad arriba y la confirmación del operador.
5. **Al salir no se restaura la ganancia sola:** la vuelve a poner el operador.
6. **La ranura en orden cero:** avisar si está abierta más de un valor seguro, por ejemplo más de 100 µm. El valor es INFERENCIA; se ajusta con BANCO-A7.

---

## 4. Step & Glue: qué tiene que ser cierto en el banco

**R1. Cada ventana es un cuadro nuevo, adquirido después del asentamiento.**
- **El legado lo hace:** `start_acquisition` + `wait_for_frame` por ventana (`StepandGlue_ps.py:656-657`; R4-5).
- **3.0 no lo hace, y es el hallazgo más grave de este bloque:** en `step_and_glue.py:565-584` aborta la adquisición, mueve la red y lee `get_most_recent_image()` / `get_1d_spectrum()` **sin iniciar ni esperar una exposición nueva**. Lo mismo pasa en el espectro único (`step_and_glue.py:505-508`) y en "Lock sustrato" (`step_and_glue.py:399-407`).
- En el hardware, `GetMostRecentImage` devuelve el último cuadro que haya en el buffer, que puede ser de **antes** del movimiento, y cuando falla devuelve **ceros sin avisar** (`andor_ccd_driver.py:520-532` y `579-594`).
- Resultado: ventanas con el eje λ nuevo y los datos viejos. Eso produce saltos, rasgos duplicados y ventanas en cero.
- Rótulo: lectura del código, no ejecutado. Se verifica con BANCO-A9.

**R2. La ventana real cubre la planificada, más el recorte, en todo el rango.**
- **Red de 150 l/mm:** ≈ 103 nm ([M24] p. 60), prácticamente constante entre 450 y 950 nm (los ángulos son chicos; DERIVADO).
- **Red de 1200 l/mm:** ≈ 11.6 nm cerca de 500 nm, pero la ventana **se achica hacia el rojo**, porque la dispersión va como cos β.
  - En aproximación de Littrow, cae ~8 % a 800 nm y ~12 % a 900 nm: entre ~10.2 y 10.7 nm. Son cotas superiores: el ángulo de desviación real reduce el efecto (INFERENCIA).
  - **3.0 planifica con la ventana medida en la posición actual** (`step_and_glue.py:539-547`, `halogen_lamp.py:297-323`), no con la del rango que se va a barrer.
  - Ejemplo: parado en 532 y barriendo 800-900 nm al 10 % (1.16 nm), la pérdida de 0.8-1.3 nm, más 2 × 0.17 nm de recorte, **deja huecos probables**. Al 20 % todavía cierra.
  - Propuesta: planificar con la ventana **mínima** del rango, o calcularla en cada centro.
- **Recorte repetido en el cosido de 3.0** (lectura del código, no ejecutado; confirmar con un test):
  - `sigmoidal_step_and_glue` (`halogen_lamp.py:232-241`) vuelve a recortar 15 px de **los dos extremos del espectro acumulado** en cada unión.
  - Por eso el comienzo del rango pierde 15 px por cada unión: con 7 ventanas de 150 l/mm, ~90 px ≈ 9.2 nm.
  - El margen de inicio es 0.5·p·W: 10.3 nm al 20 % (cierra justo) y **5.2 nm al 10 % (hueco de ~4 nm)**.
  - `coverage_gaps_nm` no lo detecta, porque trabaja con los ejes crudos (`step_and_glue.py:596-602`).

**R3. Posicionamiento, histéresis y registro entre ventanas.**
- El eje de cada ventana sale del λ **ordenado**, no del real. El error de posicionamiento (~1 px de σ, §2.3) no aparece en el eje, así que en el solapamiento las dos ventanas pueden quedar desregistradas por ~1 px.
  - Con 150 l/mm, en plasmones de decenas de nm, es irrelevante.
  - En líneas Raman con 1200 l/mm, ensancha o duplica los picos.
- Mitigaciones:
  - **ir primero por debajo del primer centro** y barrer siempre en sentido creciente (el legado barre creciente, `StepandGlue_ps.py:1160-1180`, pero no hace ese paso previo);
  - si hay histéresis, que el barrido nunca invierta el sentido;
  - opcional: medir el corrimiento en el solapamiento por correlación cruzada y registrarlo como control de calidad.

**R4. La respuesta del instrumento es la misma a ambos lados de cada unión.**
- Una misma λ se ve en el píxel ~900 de una ventana y en el ~100 de la siguiente, **con otro ángulo de red**.
- Cambian: el viñeteo hacia los bordes, la eficiencia de la red (que depende de la polarización; [DS-SR500] p. 7 da curvas a 45°) y los posibles anomalías de Wood en polarización TM (INFERENCIA).
- El sensor VP del 885 es *front-illuminated* ([DS-iXon] p. 2), así que el *etaloning* en el NIR debería ser menor que en un sensor retroiluminado (INFERENCIA).
- **Remedio del legado, que hay que conservar:** normalizar por una lámpara medida con **el mismo plan de ventanas**. La carpeta `lamparaIR_450-950_overlap0.2` lo delata (`Lampara_ps.py:14`). También se puede normalizar ventana por ventana con la lámpara medida en los mismos centros, antes de coser.
- **Consecuencias para 3.0:**
  - 3.0 planifica los centros con margen (`halogen_lamp.py:297-323`): no coinciden con los del legado, y **la lámpara heredada no sirve**.
  - Hay que volver a medirla en este banco, con la misma ranura, polarización, ROI y objetivo, y guardar la lista de centros junto con el archivo.
  - Controlar la polarización como en [G17] p. 55: una lámina de onda y un polarizador fijo dejan la polarización paralela a los surcos. [M24] p. 59 hace lo mismo.
- La lámpara halógena necesita calentarse antes (INFERENCIA; BANCO-A8).

**R5. La muestra y la excitación no cambian durante el barrido.**
- **Duración:** 7 ventanas × (10 s + ~0.3 s de asentamiento + ~0.03 s de lectura) ≈ 73 s (DERIVADO).
- **Deriva:** con 30 nm/min ([M24] p. 75; `lab-invariants` §6) son ~37 nm durante el barrido.
- **Efecto sobre una NP excitada con el láser enfocado** (DERIVADO, con INFERENCIA sobre el haz):
  - para 532 nm y NA 1.0, el radio 1/e² es w ≈ 230 nm;
  - con la NP centrada, la intensidad cambia **~5 %**; a 100 nm del centro, **~25 %**;
  - las dos cifras superan el 3 % de BANCO-07.
- Mitigaciones:
  - recentrar sobre la NP justo antes;
  - **repetir la primera ventana al final** como control;
  - para excitación láser, normalizar cada ventana por la lectura del **fotodiodo del BS** (`ai6`), que mide después del obturador y del filtro (`lab-invariants` §2).
- En campo oscuro con lámpara la excitación es uniforme, y lo que pesa es la posición de la imagen de la NP en la ranura.
- Con el láser abierto en todo el barrido hay que vigilar también el **reshaping térmico** de las NP de Au. La ventana repetida al final lo detecta.

**R6. El fondo es de cada ventana.**
- **El legado resta filas de fondo del mismo cuadro** (`StepandGlue_ps.py:843-861`): el oscuro, el bias, la luz espuria y el sustrato se restan a la vez, a la misma λ. Hay que conservarlo.
- **3.0 fija un solo cuadro de "sustrato"**, además viejo (R1), y lo resta píxel a píxel **en todas las ventanas** (`step_and_glue.py:571-579`). Sólo sería válido para el bias y el oscuro, no para un fondo que depende de λ (fluorescencia del vidrio, Raman del agua).

**R7. El segundo orden no contamina el NIR.**
- Con 150 l/mm y una fuente de banda ancha, la luz de 450 nm en orden 2 cae donde cae 900 nm en orden 1. Por encima de ~800-900 nm hace falta un filtro de corte (pasa-largos) que ordene los órdenes, o hay que acotar el rango (INFERENCIA; pregunta P6).
- El legado recortaba la normalización a 500-850 nm (`StepandGlue_ps.py:949`), quizá en parte por esto.

### 4.1 Cómo se verificaría (controles del propio barrido)

1. **Solapamiento, en cada unión:** mediana del cociente entre las dos ventanas en la zona común igual a 1 ± 3 % (el criterio Δ_stitch de BANCO-07), y corrimiento por correlación ≤ 0.5 px.
2. **Primera ventana repetida al final:** cociente 1 ± 3 %. Si no, hubo deriva, blanqueo o reshaping.
3. **Barrido invertido** (de rojo a azul) contra el directo: detecta la histéresis y separa la deriva de los efectos del orden.
4. **Lámpara sobre lámpara:** una raya de diamante o una muestra blanca ([M24] p. 60), cosida y dividida por la referencia, tiene que dar 1 ± 2 % sin escalones.
5. **Una línea angosta en el solapamiento** (Hg, o la fuga del 532): aparece una sola vez, con un FWHM que no crece más de 10 %.
6. **Cobertura:** calcularla **después** del recorte, no con los ejes crudos.

---

## 5. Qué conservar del legado y qué era frágil

### 5.1 Conservar tal cual

| Qué | Dónde |
|---|---|
| Un cuadro nuevo por ventana: iniciar, esperar, leer | `StepandGlue_ps.py:656-657` |
| El eje del SDK leído **después** de cada movimiento, con `ShamrockGetCalibration` (y no con los coeficientes cúbicos) | `StepandGlue_ps.py:623-632`, `Spectrum_ps.py:229-240` |
| Guardar el eje λ de cada adquisición junto al dato | `StepandGlue_ps.py:725-734`, `Confocal_Spectrum_ps.py:783-792` |
| Fondo de filas del mismo cuadro | `StepandGlue_ps.py:843-861` |
| Recortar 15 px por lado para evitar los bordes del detector | `Lampara_ps.py:33-35` |
| Lámpara de referencia medida con el mismo plan de Step & Glue (el nombre de la carpeta lo dice) | `Lampara_ps.py:14` |
| Recortar la normalización a la zona buena de la lámpara | `StepandGlue_ps.py:949` |
| Barrido en sentido creciente | `StepandGlue_ps.py:1160-1180` |
| Offsets escritos sólo con un botón | `Spectrum_ps.py:69-70` |
| Entrada lateral y salida directa al iXon | `Spectrum_ps.py:160-163`; R2-11 |

### 5.2 Frágil

**Offsets:**
- Un solo botón escribe **a la vez** el offset de la red *seleccionada en ese momento* (con 100 por defecto) y el del detector (con 0 por defecto): `Spectrum_ps.py:65-68`, `121-125`, `211-220`. Si alguien lo apretó con la de 1200 seleccionada, esa red quedó en 100. Por eso BANCO-25 tiene que leer los valores reales.

**Geometría:**
- El legado declaraba 1002 píxeles al SDK: `Instrument_Shamrock_ps.py:22`, `Spectrum_ps.py:157-158` (SW-004, BANCO-14).

**Orden cero y espejo sin ninguna salvaguarda:**
- `Spectrum_ps.py:199-200` y `223-226`.

**Step & Glue:**
- Ventana fija de 103 o 12 nm (`StepandGlue_ps.py:1062-1073`). La de 1200 supera la real, ~11.6 nm o menos en el rojo. **Funcionaba porque el solapamiento por defecto era 0.2** (`StepandGlue_ps.py:129`).
- En la unión emparejaba por índice, no por λ (`Lampara_ps.py:77-85`). No importa para plasmones; sí para líneas angostas. 3.0 interpola por λ, y eso es una mejora.
- Remuestreaba todo el espectro cosido a 1002 puntos: ~0.5 nm por punto para 450-950 nm (`Lampara_ps.py:102` y `113`). Pierde resolución en Raman.
- Suavizado Savitzky-Golay de orden 0 antes de dividir (`StepandGlue_ps.py:955-956`). Está bien para dispersión; no se debe aplicar a Raman.
- La ruta de la lámpara estaba escrita a mano en el código (`Lampara_ps.py:12-16`).
- No había cuadro oscuro ni control temporal entre ventanas.

### 5.3 Frágil en 3.0 (además de C-04 y R1-R6)

- **Calibración de la ranura.** `auto_calibrate_slit` (`calibration_dock.py:802-822`):
  - si no hay imagen, ajusta un perfil **plano** sintético (`np.ones(1004)*100`) y **guarda** el centroide resultante;
  - además usa un cuadro viejo y no revisa la saturación.
- **Eje λ con los coeficientes cúbicos.** `SHAMROCK_USE_FACTORY_EEPROM = True` (`config.py:110`) hace que el eje salga de `ShamrockGetPixelCalibrationCoefficients` (`shamrock_driver.py:754-762`), **que el legado nunca usó** (grep en `scratch/pyspectrum-legacy/`).
  - No hay documentación primaria sobre si esos coeficientes se recalculan con λc y con los offsets.
  - **Si fueran fijos, todas las ventanas tendrían el mismo eje.** Se verifica en BANCO-A2.
- **Lámpara sintética silenciosa.** Si falta el archivo de la lámpara, se usa sin avisar un cuerpo negro de 3000 K marcado como "cargado" (`halogen_lamp.py:52-67`). Contradice la regla de no usar simulaciones silenciosas en producción.
- **Normalización.** No enmascara el rango válido, y el archivo tiene ceros (por ejemplo en 452.0 nm) que se reemplazan por 1.0 (`halogen_lamp.py:73-79`). Eso produce picos espurios en los bordes.

---

## 6. Casos borde y fuentes de error no obvias

1. **Temperatura del espectrógrafo.**
   - La posición de la línea deriva con la sala ([SR303] p. 6; [DS-SR500] p. 15 piden un ambiente estable). No hay un valor de la magnitud: **se mide** en BANCO-A5.
   - Si la calibración de cada ~2 meses se hace a otra temperatura que las medidas, el error puede superar 1 px.
2. **Dónde cae el spot o la NP dentro de la ranura** (INFERENCIA, geometría).
   - Cuando la ranura es más ancha que la imagen del spot, la λ la fija **dónde cae la imagen dentro de la ranura**: Δλ = Δx_ranura · δλ, con M ≈ 1.
   - Una NP corrida media ranura de 50 µm (≈ 3 px) da 0.3 nm con 150 l/mm y 0.035 nm con 1200 l/mm (~1 cm⁻¹).
   - **Cualquier realineación de la detección obliga a recalibrar.** Para el Raman, conviene referir a la línea del láser medida en la misma configuración.
3. **Ranura unilateral.**
   - Si una sola mordaza se mueve, al cambiar el ancho se corre el centro de la imagen: de 10 a 100 µm serían ~45 µm ≈ 5.6 px (~0.6 nm con 150 l/mm). Rótulo: INFERENCIA; BANCO-A4 y pregunta P7.
   - En ese caso, la calibración vale sólo para el ancho con que se hizo.
4. **Ganancia EM y centroide.** Un desborde del registro de ganancia arrastra carga en el eje espectral (§2.1). Por eso se calibra sin ganancia.
5. **Rayos cósmicos en exposiciones de 10 s.**
   - El filtro de rayos cósmicos del SDK compara *"consecutive scans in an accumulation"* ([SDK2] p. ~277, `SetFilterMode`): **con una sola exposición por nodo no actúa**.
   - Para la calibración, tomar la mediana de 5 cuadros.
   - En Step & Glue, un pico espurio en el solapamiento se mezcla con la otra ventana: hace falta rechazarlo por software.
6. **Temperatura del CCD.**
   - Oscuro de 0.01 e⁻/px/s a −85 °C ([DS-iXon] p. 2): despreciable en 10 s.
   - Pero el QE en el extremo rojo depende de la temperatura del silicio (INFERENCIA), y el bias puede derivar.
   - Hay que medir con el CCD estabilizado y considerar el *baseline clamp* (`SetBaselineClamp`, [SDK2] p. ~242).
   - La opción de enfriamiento instalada (DV o DU) no está confirmada (`lab-invariants` §3).
7. **La EEPROM es compartida.**
   - Solis y el legado pueden cambiar los offsets sin que 3.0 se entere.
   - Al arrancar, 3.0 debe **leer y comparar** con el último valor del archivo y avisar si no coinciden. **Nunca debe escribir** al arrancar (C-04).
8. **Cambio de geometría, de 1002 a 1004 px.**
   - Recalibrar después de cambiarla, aunque el offset "no haya cambiado".
   - Los datos viejos quedan ~1 px corridos (BANCO-14).
9. **Signo del eje.**
   - Si la lectura de la cámara estuviera espejada respecto de lo que supone el SDK, una línea en el centro saldría bien y las de los bordes mal, con el signo invertido.
   - El recorrido del detector (§2.4 a) lo detecta.
   - El legado ordenaba el eje (`StepandGlue_ps.py:936-940`), cosa que podía esconder una inversión.
10. **Luz espuria cerca del láser.** La hoja de datos da 1.1·10⁻⁴ a 1 nm del láser en FVB ([DS-SR500] p. 13): el fondo sube junto a la línea. El fondo del ajuste tiene que ser local.
11. **El espejo `line7` no tiene realimentación** (C-08).
    - Si PyPrinting imprime a potencia alta (filtro abajo) con el espejo abajo, el espectrómetro recibe el haz de impresión.
    - Si en ese momento el EMCCD tiene ganancia alta, es un riesgo **entre programas**. Hace falta un interbloqueo en la sesión de hardware.
12. **Polarización.** Con señales polarizadas (nanobastones, dímeros), la eficiencia de la red cambia con λ y con el ángulo, y aparecen escalones en las uniones que la lámpara despolarizada no corrige. La lámpara de referencia tiene que medirse con la misma polarización (R4).

---

## 7. Preguntas para el investigador (8)

**P1. ¿Cómo se hace hoy la calibración con 532?**
- De dónde sale la luz: reflexión en el cubreobjetos o dispersión.
- Si los notch quedan puestos (¿hay notch en la detección de este banco?).
- Qué ancho de ranura se usa, en qué programa (Solis o el legado), y si el resultado se escribió como offset o se corrigió por software.
- *Desbloquea:* reproducir el método, definir la atenuación segura del §2.1 y saber si el 85 corresponde a la geometría de 1002 o de 1004 px.

**P2. ¿Se sacó alguna vez la cámara, la torreta o el conjunto de la ranura? ¿Se usa Solis en este banco?**
- *Desbloquea:* la convención D = 0 como referencia (§1.3), y si la EEPROM puede cambiar a espaldas de 3.0.

**P3. ¿Hay una lámpara de calibración (Hg-Ar o Ne en lápiz) o un tubo fluorescente que pueda iluminar la ranura?**
- *Desbloquea:* la verificación absoluta de λ y de la dispersión de la red de 1200. Sin ninguna de las dos, el protocolo depende del recorrido del detector y de los patrones Raman.

**P4. ¿Qué tipo de láser es el de 532 (DPSS, su λ nominal y su ancho de línea)? ¿Y los de 592, 637 y 808 (¿diodos?)?**
- *Desbloquea:* si sirven como líneas secundarias, y qué λ del láser se fija en el archivo de calibración (§2.6).

**P5. ¿Para qué se usó el orden cero cuando se usó? Para ver la muestra, ¿se usa la posición espejo de la torreta?**
- *Desbloquea:* si alcanza con la posición espejo con salvaguarda o hace falta el orden cero de cada red, y los valores seguros de exposición y ranura del §3.3.

**P6. ¿Cómo se usa típicamente el Step & Glue?**
- Qué fuente (lámpara de campo oscuro o láser), qué rango, qué solapamiento.
- Si hay un filtro de corte para el segundo orden, polarizadores en el camino, y cada cuánto se vuelve a medir la lámpara.
- *Desbloquea:* normalizar ventana por ventana o con la lámpara cosida, R4 y R7, y si hay que volver a medir la referencia en este banco.

**P7. ¿La ranura motorizada es unilateral o bilateral? ¿Con qué ancho se calibra y con cuál se mide?**
- *Desbloquea:* si la calibración se guarda por ancho de ranura (§6.3).

**P8. ¿Qué exactitud necesita el grupo? Por ejemplo, en cm⁻¹ para el Raman con la red de 1200 y en nm para el máximo plasmónico con la de 150.**
- *Desbloquea:* los criterios de aceptación del §2.3, que hoy son una propuesta mía.

---

## 8. Ítems propuestos para la batería de banco

**Van listados, no se editó `PRUEBAS_BANCO_PENDIENTES.md`.** La numeración A1-A9 es provisoria.
- Todas se hacen **después de BANCO-25** (el respaldo de los offsets) y con C-04 cerrado. Si no, con el legado o con Solis.
- Donde hay láser, van con el filtro de densidad arriba, la ganancia EM apagada y la aprobación del investigador.
- Complementan BANCO-04 a 08, 13, 14 y 25, sin repetirlos.

| ID | Prueba | Procedimiento resumido | Aceptación o resultado |
|---|---|---|---|
| **A1** | Sensibilidad y persistencia de los offsets | Con la línea de 532 centrada, cambiar el offset de la red en −20, −10, +10 y +20 unidades, y lo mismo con el del detector. Medir el corrimiento de la línea. Probar si hace falta volver a enviar `SetWavelength`. Restaurar los valores. Apagar y prender, y releer. | S_G y S_D en px/unidad, para cada red; ¿es lineal?; ¿persiste? Restaurado exacto al valor de BANCO-25 |
| **A2** | Recorrido del detector y origen del eje | Con 150 l/mm: λc = 532, ±20 y ±40 nm. Con 1200 l/mm: 532, ±2 y ±4 nm. En cada λc, anotar x̂ de la línea y comparar el eje de `ShamrockGetCalibration` con el cúbico (`get_wavelength_axis_cubic`). | Signo de la dispersión correcto; px/nm contra el valor nominal ±2 %; los dos ejes coinciden y **los dos siguen a λc** (si no, `SHAMROCK_USE_FACTORY_EEPROM` es inválido) |
| **A3** | Repetibilidad e histéresis de la torreta | 10 ciclos 532 → 600 → 532 y 150 → 1200 → 150, acercándose desde abajo; después, 5 desde abajo contra 5 desde arriba. | σ ≤ 1 px; diferencia entre los dos sentidos ≤ 0.5 px (si no, el Step & Glue siempre desde abajo) |
| **A4** | Línea contra ancho de ranura | Centroide del 532 con ranuras de 10, 25, 50, 100 y 200 µm. | Corrimiento ≤ 0.5 px (si no, la ranura es unilateral: calibrar por ancho) |
| **A5** | Deriva temporal del eje λ | Línea de 532 cada 5 min durante 2 h desde el encendido, anotando la temperatura de la sala y la del CCD. | px/h y tiempo de termalización; fija la espera del §2.1 y la frecuencia de recalibración |
| **A6** | Linealidad y saturación en la calibración | Exposiciones T, 2T y 4T con la línea en ~15-50 % del ADC; anotar el bias. | Cociente 2.00 ± 0.04; centroide ± 0.05 px; fija la exposición de trabajo |
| **A7** | Orden cero seguro y de referencia | Con los láseres cerrados, la ganancia EM apagada y la lámpara al mínimo: 1 ms en orden cero con cada red y con el espejo. Medir las cuentas por ms y el centro de la imagen de la ranura. | Exposición y ranura seguras para el §3.3; píxel de referencia del orden cero de cada red para el diagnóstico de modo común |
| **A8** | Control de calidad de las uniones en Step & Glue | Con 150 l/mm y la lámpara sobre una muestra blanca: 450-950 nm al 20 % y al 10 %, con la primera ventana repetida al final y un barrido invertido. Con 1200 l/mm: 800-900 nm al 10 % y al 20 %. | Cociente en cada solapamiento 1 ± 3 %; ventana repetida 1 ± 3 %; **sin hueco al comienzo al 10 %** (recorte repetido, R2); sin huecos en el rojo con 1200 al 10 % |
| **A9** | Cada ventana es un cuadro nuevo | Step & Glue con una línea (la fuga del 532, o Hg) en un rango donde aparece en ventanas conocidas; guardar la marca de tiempo y el contador de cuadros. | La línea aparece sólo donde debe, cada ventana tiene un cuadro distinto y ninguna ventana está en cero (valida la corrección de R1) |

---

## 9. Veredicto

**MODIFICATION_REQUIRED.**
- La calibración con 532 y el filtro de densidad es **factible en el banco** y alcanza para los offsets de las dos redes, con el protocolo del §2.
- El offset de detector no se puede separar del de red con una sola configuración. Se propone la convención D = 0 y un diagnóstico de modo común.
- Para el orden cero hace falta un camino único que falle cerrado.
- El Step & Glue de 3.0 **no puede ir al hardware** sin cuatro cambios:
  - un cuadro nuevo por ventana (R1);
  - la cobertura calculada después del recorte y con la ventana mínima del rango (R2);
  - el fondo de cada ventana (R6);
  - una lámpara de referencia medida en este banco con el mismo plan (R4).
