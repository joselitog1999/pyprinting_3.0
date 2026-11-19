# C-01 Ronda 4 — mini Ronda 1 de R4-3 — Panel experimental

Estado: COMPLETO (2026-10-01). Ronda de análisis: no se tocó código ni tests, no se ejecutó nada
contra hardware. Árbol: `main` @ `7aab0d8`.

Marcas: **[CÓDIGO]** leído en la línea citada · **[LEGADO]** `Obsidian_Vault/printing2/` (copia
local: vale para algoritmos y tiempos, no para cableado, [INV6] BANCO-35) · **[FUENTE]**
bibliografía de `docs/bibliografia/`, página **física** del PDF · **[INV]** `RESPUESTAS_INVESTIGADOR.md`
· **[DERIVADO]** cálculo propio con insumos citados · **[SUPUESTO]** sin respaldo, se mide ·
**[BANCO]** se decide en el banco.

---

## Resumen

1. **La lectura a baja potencia es viable y no es nueva.** El banco ya expone cada nodo a baja
   potencia en el autofoco (≈ 1.5-2 s de obturador abierto por autofoco, `focus_autocorr_lin_x2`)
   y P0 recibe un escaneo de ≈ 4 s en cada corrección de deriva. Si eso no imprime ni daña (lo dicen
   [M24] p. 69, [P25] p. 38 y [G17] p. 60, y el legado lo hizo así durante años), una lectura de
   0.1-0.2 s tampoco. El antecedente directo es el paso de confirmación de [AN17] p. 5 (folio E):
   bloquear los haces 1 s y volver a interrogar con el haz de detección solo.
2. **Lo que se mide es una razón, no un voltaje.** Con detección lineal, el contraste iSCAT
   R = I_NP/I_sustrato no depende de la potencia. Pero sólo si se resta el **oscuro** (obturador
   cerrado, mismas luces y misma ganancia): a baja potencia el offset del PDA36A y la luz de la
   lámpara de campo oscuro pueden ser comparables a la señal y comprimen R hacia 1. Con
   offset = señal, un escalón real de ×1.5 se lee ×1.25.
3. **Referencia recomendada:** el mismo punto, antes de la exposición, **normalizado por el BS**,
   que mide después del obturador y del filtro de densidad ([INV] Q14, R9 P-c). Para el corte
   inmediato alcanza con la meseta previa a la captura de la propia traza a alta potencia,
   dividida por el BS, si el banco confirma la linealidad PD/BS entre las dos potencias (BANCO-65 A).
   La deriva no importa en los ≈ 1.5 s que pasan (≤ 1 nm); sí importa después de una pausa: a
   partir de ≈ 60 s hace falta recentrar en P0 y reenfocar antes de leer.
4. **Criterio con tres salidas:** "ve la NP" (R ≥ u_c), "no la ve" (R ≤ 1 + δ) y "no sé". El "no
   sé" **no** cuenta como "no la ve": reimprimir sobre una NP ya fija es el peor error, porque la
   calienta a alta potencia hasta T_max (50 s en el Healing Pass) sin escalón que corte. u_c se
   calibra en la sesión con "Medir escalón" más una lectura a baja potencia de la NP recién
   impresa y otra sobre vacío: u_c = 1 + máx(5·σ_R, ½·(r_baja,mín − 1)), que con r ≈ 1.4 da 1.20,
   el valor por defecto de la GUI.
5. **Secuencia sin mover la platina:** obturador ya cerrado → filtro a baja → espera (que cubre el
   segundo de [AN17]) → oscuro → abrir → **chequeo del filtro por el BS** → lectura → cerrar. Costo
   ≈ 0.8-1.3 s por nodo. El BS es, de hecho, el único sensor de posición del filtro de densidad,
   que es **casero** y no un MFF101 (el MFF101 es el espejo de detección, BANCO-21/22).
6. **N-3 (topes):** el tope de distancia solo **no alcanza**. `_norm_image` normaliza min-max, así
   que una imagen oscura igual da un centro de masa, y cae cerca del centro del escaneo, o sea,
   dentro de cualquier tope razonable. Hace falta un tope de amplitud además del de distancia. El
   autofoco de la grilla no es el `argmax` del perfil (eso es `focus_go_to_maximum`) sino el de una
   **correlación** con el perfil bloqueado (`focus_autocorr_lin_x2`). Sobre oscuridad puede saltar
   hasta ±3 µm en Z. Propongo topes de amplitud, distancia y coherencia para los dos (§5).
7. **Banco:** propongo **BANCO-65**: primero sin coloide (atenuación, linealidad, oscuro, ruido,
   tiempo del filtro casero), después con coloide (r_baja contra r_alta, seguridad a baja potencia,
   matriz de confusión contra campo oscuro) y repetibilidad de la deriva y del foco con los
   escaneos hechos a oscuras.

Veredicto: **MODIFICATION_REQUIRED**. Es factible en el banco con la secuencia y el criterio de abajo;
no se habilita hasta pasar BANCO-65.

---

## 0. Hechos de partida

| # | Hecho | Fuente |
|---|---|---|
| H1 | El filtro de densidad se conmuta con `up_flipper()` (ao0, baja) y `down_flipper()` (ao1, alta): un pulso de 5 V, sin realimentación. 3.0 espera 0.5-1 s después de cada pulso (`measurements.py:2252, 2263, 2300, 2311, 2318, 2444, 2501, 2520`); el legado espera **1 s** siempre (`Printing_pp.py:749-751, 768-769, 818-819, 830-831`) con pulso de 3 ms | [CÓDIGO], [LEGADO] |
| H2 | El flipper del filtro de densidad es **de fabricación casera**; el MFF101 es el del espejo de detección | BANCO-22 y BANCO-21 (2026-09-28) |
| H3 | Fotodiodos Thorlabs PDA36A (ganancia conmutable). La ganancia de cada uno no está anotada | BANCO-22 |
| H4 | El BS (ai6) ve la luz después del obturador y del filtro; el espejo de detección no lo afecta | [INV] Q14, R9 P-c |
| H5 | El autofoco de la grilla es `focus_autocorr_lin_x2` (`app.py:504`): dos rampas en Z con el obturador abierto, cada una de ≈ 0.6 s (10 kS/s, rampa de 3.33 Hz, ida y vuelta), correlación con el perfil bloqueado y `argmax` de la correlación (`focus.py:358-419`). No valida la señal | [CÓDIGO], [DERIVADO] |
| H6 | El escaneo de deriva sobre P0 reemplaza `startX/startY` por el centro de masa sin ningún tope (`measurements.py:2462-2466`). El centro de masa sale de una imagen normalizada min-max con umbral del 30 % (`confocal.py:1144-1168`) | [CÓDIGO] |
| H7 | Escaneo típico de 2 × 2 µm, 34 × 34 px: la rampa de 8.33 Hz da ≈ 0.12 s por línea, ≈ 4 s por imagen (`confocal.py:641-646`) | [DERIVADO del código] |
| H8 | Existe un escaneo posterior a la detección ("Scan", `scanbool`): sube el filtro, escanea y lo baja (`measurements.py:2441-2446, 2517-2521`; legado `Printing_pp.py:815-831`). Hoy no reclasifica el nodo | [CÓDIGO] |
| H9 | El Healing Pass reintenta sólo los nodos `"timeout"` y hace autofoco in situ, a baja potencia, en cada uno (`measurements.py:2826-2880`) | [CÓDIGO] |
| H10 | Captura: escalón hacia arriba de ×1.4 a ×2; captura de 1 a 20 s; T_max = 40 s (50 s en el Healing Pass) | [INV] R3, Q-2; `measurements.py:2860` |
| H11 | El sustrato tiene el mismo signo de carga que las NP: sin luz, una NP no se adsorbe sola | [G17] p. 40; [AN17] p. 2; [M24] p. 37 |
| H12 | Foco y escaneos se hacen con el filtro neutro activo "lo cual garantiza que no se imprimirán NPs" y que las impresas "tampoco serán dañadas al escanearlas" | [M24] p. 69; [P25] p. 38; [G17] p. 60 |
| H13 | Confirmación de [AN17]: fuera de resonancia, NP "momentarily trapped in the confocal volume"; tras detectar, los dos haces se bloquean 1 s y se interroga con el haz de detección solo; el haz de detección ejerce < 10 % de la fuerza del de impresión | [AN17] p. 5 (folio E) |
| H14 | Deriva XY: 30 nm/min en promedio, pero el texto dice **800 nm en un eje y 400 nm en el otro en 20 min**: 40 nm/min (0.67 nm/s) en el eje peor. Es algo más que el "caso peor de 0.5 nm/s por eje" de `lab-invariants` §6. La deriva en Z se estima por el cambio de cintura (Fig. 3.16b), sin número | [M24] p. 75 (CIBION) |
| H15 | Cintura w₀ ≈ 266-278 nm con 532 nm y NA 1.0; error de impresión ≈ 50 nm RMS radial (≈ 35 nm por componente) | [NL17] p. 2; [M24] p. 41, p. 129 (CIBION) |

> **Observación para `lab-invariants` §6 (no la corrijo acá):** si "0.5 nm/s por eje" se usa como
> caso peor, [M24] p. 75 da 0.67 nm/s en un eje. Para los topes de §5 uso 1 nm/s por eje, con margen.

---

## 1. Qué se mide en la lectura a baja potencia

### 1.1 Física

La señal confocal de reflexión es iSCAT: I_d = I_r + I_sca + 2√(I_r·I_sca)·cos φ ([M24] p. 57).
Todos los términos escalan con la potencia incidente P. Entonces, **con el oscuro restado**,

  R = (V_NP − D) / (V_sust − D)

es independiente de P. Es el mismo r de la traza, salvo dos correcciones de banco:

- **Offset y luz que no escala con P.** D incluye el offset del PDA36A, la luz de la lámpara de
  campo oscuro que pasa el filtro del canal de 532 y la luz ambiente. A alta potencia D es
  despreciable frente a la señal; a baja potencia, quizá no. Si no se resta, se mide
  R_med = (r·S + D)/(S + D). Con D = S y r = 1.5 queda R_med = 1.25, y con u_c = 1.20 eso ya es
  marginal. **Medir D con el obturador cerrado en cada confirmación es obligatorio**, y es gratis
  porque se hace durante la espera del filtro (§4).
- **La NP impresa está fría a baja potencia y caliente a alta.** A alta potencia, la NP de Au está a
  cientos de grados ([M24] p. 112). El agua alrededor cambia de índice (lente térmica) y la
  permitividad del Au cambia con T, así que r_alta y r_baja pueden diferir. No conozco una medición:
  **[SUPUESTO]**, el factor k = (r_baja − 1)/(r_alta − 1) se mide en BANCO-65 B1. Por eso u_c se
  calibra contra r_baja, no contra el escalón de la traza.

### 1.2 ¿El fotodiodo ve la NP a baja potencia?

**Sí, por construcción del banco.** El legado imprime grillas con autofoco y escaneos a baja
potencia, y los escaneos confocales a baja potencia muestran la NP impresa con contraste suficiente
para calcular su centro de masa (H8, H12; es lo que alimenta `printing_error_*.txt`). Una lectura
puntual de 100 ms promedia ≈ 40 veces más tiempo que un píxel del escaneo (≈ 2.6 ms/px, H7), así que
tiene ≈ √40 ≈ 6 veces menos ruido de detector que la imagen que ya funciona. **[DERIVADO]**

### 1.3 Relación señal/ruido (órdenes de magnitud)

- **Ruido de disparo:** irrelevante. Aun con P_baja ~ 10 µW, la reflexión vidrio-agua (≈ 0.4 %)
  devuelve ~ 40 nW, unas 10¹¹ fotones/s antes de pérdidas. **[DERIVADO]**
- **Lo que domina:** el ruido electrónico del PDA36A a la ganancia de uso, el zumbido de 50 Hz, la
  cuantización del ADC y la vibración axial, que el iSCAT convierte en fase (≈ 1-2 % p-p de la base
  en las trazas de CIBION, [M24] Fig. 3.9).
  - La hoja de datos del PDA36A no está en `docs/bibliografia/`. El ruido RMS es del orden de
    décimas de mV a ~ 1 mV según la ganancia **[SUPUESTO, verificar]**.
  - Con 1000 muestras (100 ms a 10 kS/s) y ruido blanco, σ de la media ~ 10-30 µV.
  - El rango de entrada no se fija en `channels_photodiodos()` (`nidaq.py:843-847`), así que rige
    el de `nidaqmx` (±5 V, a confirmar en BANCO-26): un paso de ≈ 0.15 mV. Con ruido mayor que el
    paso, promediar funciona.
- **Requisito que propongo:** σ_R ≤ 0.02 en una lectura, es decir, separar con ≥ 10 σ un escalón
  de ×1.2 (la mitad del ×1.4 más chico observado). Hace falta:
  - **base a baja potencia, sin oscuro, de al menos ~ 2-5 mV** **[DERIVADO]**, con 30 µV de ruido
    de la media y ~ 1 % de ruido técnico relativo;
  - si BANCO-65 A da menos de eso, hay tres salidas: alargar la lectura a 200 ms, subir la ganancia
    del PDA para la lectura (cambia todas las escalas en V: no lo recomiendo), o usar una tarea con
    rango ±1 V sólo para la confirmación (decisión de instrumentación y metrología).
- **Tiempo de integración recomendado: 100 ms**, partido en 10 bloques de 10 ms, con ventanas
  múltiplo de 20 ms para cancelar el 50 Hz. Usar 200 ms si la base a baja es chica. La mediana de
  bloques descarta el pico de 1-10 ms de una NP que cruza el foco.

### 1.4 Riesgos a baja potencia

| Riesgo | Estimación | Juicio |
|---|---|---|
| Imprimir otra NP | Debajo de P_th, la fuerza no supera la barrera DLVO ([AN17]: P_th ≈ 1.0 mW para Au de 60 nm a 532 nm). En [AN17] un haz de detección con < 10 % de la fuerza quedó superpuesto todo el tiempo sin imprimir. El filtro "garantiza que no se imprimirán NPs" en un autofoco de ≈ 1.5-2 s (H5, H12). La lectura dura 0.1-0.2 s, unas 10 veces menos | despreciable **si** la atenuación es ≥ 10 (OD ≥ 1). **La OD del filtro casero no está medida** → BANCO-65 A1 y B3 |
| Calentar o dañar la NP impresa | ΔT ≈ β·I. Con β = 55 K·µm²/mW e I_impresión = 10 mW/µm² ([M24] p. 112), a OD 2 son ≈ 5 K y a OD 1 ≈ 55 K, durante 0.1-0.2 s. El daño publicado aparece a 4 mW/µm² y 300 s ([M24] p. 78-79) | despreciable para Au esférica; para Ag o no esféricas, igual de chico que un escaneo |
| Mover la NP impresa | La NP fija está adherida por van der Waals sobre el polielectrolito; la fuerza a baja potencia es ≤ 10 % de la de impresión | despreciable |
| Atrapar una NP de paso durante la lectura | A 532 con Au en resonancia es raro; fuera de resonancia (Ag a 532) es el modo de falla de [AN17] | lo cubre la mediana de bloques y el chequeo de dispersión (§3) |
| NP en vuelo al cortar | Sin luz difunde (D ≈ 7 µm²/s: √(6Dt) ≈ 6 µm en 1 s) y no se adsorbe, porque el sustrato tiene su mismo signo (H11). No hay "impresión diferida" | la espera de ≥ 1 s la resuelve |
| Burbuja persistente sobre una NP muy caliente | **[SUPUESTO]** posible a la temperatura de impresión. Una burbuja de gas que queda puede reflejar fuerte y dar un falso "ve la NP" | se ve en la cámara; está en la matriz de confusión de BANCO-65 B4 |

---

## 2. Referencia: contra qué se compara

### 2.1 Opciones

| Opción | Ventajas | Problemas | Juicio |
|---|---|---|---|
| (a) **Mismo punto, antes de la exposición, a baja potencia** | La comparación más limpia: misma XY, misma Z, mismo sustrato | Cuesta un ciclo extra del filtro por nodo (≈ 1-2 s), salvo en los nodos con autofoco in situ, donde el filtro ya está arriba | ideal, pero cara en todos los nodos |
| (b) **Mismo punto, meseta previa a la captura de la traza a alta potencia, normalizada por el BS** | Gratis: la traza ya la mide (la ventana de armado). El BS mide la atenuación real que vio la muestra, después del filtro (H4) | Supone que el PD y el BS son lineales entre las dos potencias (k_lin = 1). Si la captura fue antes del armado, la base ya tiene la NP: el resultado sería un falso "no la ve" | **recomendada** para el corte inmediato, con k_lin medido y una guarda de base sospechosa |
| (c) Punto vacío vecino, ahora | Mide el sustrato en el mismo instante | Hay que mover la platina; el sustrato varía en µm (polielectrolito, inclinación); en grillas densas no hay vacío garantizado | control, no referencia principal |
| (d) Mediana de las bases de los nodos anteriores de la grilla | Detecta una base sospechosa | Incluye la variación del sustrato (σ_sust, sin medir) | guarda, no referencia |

### 2.2 Recomendación

- **Magnitud común a todas:** B = (V_PD − D_PD)/(V_BS − D_BS), con los oscuros medidos con el
  obturador cerrado y las mismas luces.
- **Corte inmediato** (preset de ventana corta, `acq_fault` con exposición): R = B_ahora / B_pre,
  con B_pre de la opción (b). Guarda: si B_pre supera 1.2 veces la mediana de las B_pre de la
  grilla, la base es sospechosa y el resultado es "no sé".
- **Nodos con autofoco in situ:** B_pre se toma a baja potencia (opción a) al terminar el autofoco.
  Cuesta sólo 100-200 ms de obturador, porque el filtro ya está arriba. Así, además, se acumula en
  cada sesión una medida de k_lin sin costo.
- **Confirmación diferida** (Healing Pass, después de "Cerrar todos", de una pausa o de una parada
  de emergencia): R = B_ahora / B_pre, leído **después** de la corrección de deriva en P0 y del
  autofoco in situ que el Healing Pass ya hace (H9). El filtro ya está arriba y no hay ciclo extra.
  Control opcional: B en la zona limpia del ancla (−1, −1) µm de P0, ahora y al principio, para
  corregir un cambio global de alineación de la detección.

### 2.3 Deriva entre la base y la lectura

Modelo de pérdida de contraste con el corrimiento r entre la NP y el centro del haz: el término de
interferencia escala con el campo de iluminación por la PSF de amplitud de detección, ≈ exp(−2r²/w₀²)
con w₀ ≈ 270 nm (es conservador: el pinhole de 1.5 AU ensancha la detección). **[DERIVADO]**

| Corrimiento r | Factor sobre (R − 1) | Con r_baja = 1.4 |
|---|---|---|
| 50 nm (error típico de impresión) | 0.93 | 1.37 |
| 100 nm | 0.76 | 1.30 |
| 150 nm | 0.54 | 1.22 (marginal) |
| 200 nm | 0.33 | 1.13 → "no sé" |
| 300 nm | 0.08 | 1.03 → falso "no la ve" |

- **Corte inmediato (≈ 1-1.5 s entre corte y lectura):** a 0.67-1 nm/s se corre ≤ 1.5 nm. El efecto
  es nulo. En Z, sin número de fuente (H14); con la misma escala, unos nm, frente a un FWHM axial de
  ≈ 1 µm. Despreciable.
- **El error de impresión ya está adentro:** con σ ≈ 35 nm por componente (H15), P(r > 100 nm) ≈
  1.7 % y P(r > 150 nm) ≈ 10⁻⁴ **[DERIVADO, con datos de CIBION]**.
- **Pausa sin recentrar:** a 40 nm/min (H14), en 1 min el corrimiento es ≈ 40 nm (factor 0.96); en
  5 min, ≈ 200 nm (0.33); en 10 min, ≈ 400 nm (0.01).
  - El modo de falla es peligroso: falso "no la ve", reimpresión en la coordenada vieja y una
    segunda NP a ~ 300 nm de la primera, es decir, un defecto tipo dímero ([P25] p. impresa 18-19, según la Ronda 1).
  - **Regla que propongo:** si pasaron más de **60 s** desde que se cerró el nodo, primero se
    corrige la deriva en P0 y se hace autofoco in situ, y después se lee. Es lo que ya hace el
    Healing Pass; la reanudación tras una pausa o un rearme tiene que hacer lo mismo.
- **Foco:** la reflexión del sustrato está en un máximo cerca del foco (primer orden insensible a
  Z). La fase φ de la NP, en cambio, depende de Z. Leer después del autofoco in situ deja a la NP en
  la misma condición axial que durante la impresión, que también se hizo después de un autofoco.

---

## 3. Criterio

### 3.1 Propuesta

Lectura de 100 ms en 10 bloques. R = mediana de los bloques de B, dividida por B_pre.
Dispersión s_R = rango intercuartil de los bloques dividido por 1.35.

| Resultado | Condición | Qué pasa con el nodo |
|---|---|---|
| **Ve la NP** | R ≥ u_c y s_R ≤ 0.05 | "impresa (verificada)", no se reexpone |
| **No la ve** | R ≤ 1 + δ (δ = máx(3·σ_R, 0.05)) y s_R ≤ 0.05 | "pendiente", el Healing Pass la reintenta (regla P4) |
| **No sé** | 1 + δ < R < u_c; o s_R > 0.05; o R < 0.85 (base que bajó: foco, alineación, espejo); o falló el chequeo del BS o del oscuro (§4); o base sospechosa (§2.2) | **una** segunda lectura de 100 ms; si sigue igual, "en revisión" |

- **El "no sé" nunca se trata como "no la ve".** Las dos fallas no son simétricas:
  - **falso "ve la NP"** → queda una vacancia (sube p, [P25] p. 51);
  - **falso "no la ve"** → se reimprime sobre una NP fija. Esa NP ya está en la base, así que no hay
    escalón que corte, y el nodo se queda hasta T_max a alta potencia: 50 s a la temperatura de
    impresión. Es la escala en la que [M24] p. 78-79 ve entierro y halo en el polielectrolito. Es
    peor que la vacancia, y por eso el "no sé" va a "en revisión" (coherente con P4).
- **R < 0.85 con el BS normal** indica que el fotodiodo de detección perdió luz: espejo de
  detección abajo o detección desalineada (N-11, [INV] R9 P-c). Corta y avisa con el mismo texto
  que la regla de N-11.

### 3.2 Calibración en la sesión, con "Medir escalón"

El flujo de [INV6] P2 (imprimir una NP a mano y medir el escalón) se extiende con dos lecturas:

1. Imprimir a mano, cortar con F2 y aplicar "Medir escalón" para obtener r_alta (como hoy).
2. **"Leer a baja potencia" sobre esa misma NP**, con la secuencia de §4. Da r_baja y
   k = (r_baja − 1)/(r_alta − 1).
3. **"Leer a baja potencia" sobre un punto vacío**, unas 5 veces sobre puntos distintos. Da σ_R,
   que incluye la variación del sustrato.
4. Con n ≥ 5 NP impresas en la sesión:
   **u_c = 1 + máx(5·σ_R, ½·(mín r_baja − 1))**, y δ = máx(3·σ_R, 0.05).
   - Con r_baja = 1.4 y σ_R = 0.02 da u_c = 1.20, el valor por defecto de la GUI ([v1 §2.4]).
   - Si 5·σ_R > ½·(mín r_baja − 1), las poblaciones no se separan: la confirmación se **deshabilita**
     en esa sesión, con aviso, y los nodos expuestos sin decisión vuelven a "en revisión".
   - u_c se guarda con la sesión, junto a la potencia en la pupila ([INV7] P-L).

### 3.3 Falsos positivos y negativos esperados

| Tipo | Causa | Mitigación |
|---|---|---|
| Falso "ve la NP" | NP atrapada que no se fue (Ag fuera de resonancia) | la espera de ≥ 1 s antes de leer ([AN17]); mediana de bloques |
| Falso "ve la NP" | Burbuja persistente o basura en el sitio | dispersión de bloques; cámara; BANCO-65 B4 |
| Falso "ve la NP" | Otra NP o agregado pegado cerca (nodo vecino con doblete) | sólo lo ve la cámara o un escaneo; es raro con el sustrato del mismo signo |
| Falso "no la ve" | **Oscuro sin restar** (compresión de R) | oscuro obligatorio en cada lectura |
| Falso "no la ve" | Deriva después de una pausa larga | la regla de 60 s (§2.3) |
| Falso "no la ve" | NP impresa lejos del centro (> 150 nm) | rara (10⁻⁴); u_c a la mitad del contraste mínimo |
| Falso "no la ve" | Captura antes del armado (base con la NP) | la guarda de base sospechosa → "no sé" |
| Falso "no la ve" | r_baja < r_alta por efecto fototérmico | se calibra con r_baja (k medido) |
| "No sé" | Filtro casero a medio camino, obturador lento, base de pocos mV | el chequeo del BS (§4); alargar la lectura |

**Lo que espero en números [SUPUESTO, BANCO-65 B4]:** para Au a 532 en resonancia con σ_R ≤ 0.02,
menos del 1 % de falsos en las dos direcciones y menos del 5 % de "no sé". Para Ag a 532 (fuera de
resonancia: contraste chico o negativo, [AN17] p. 5) no doy cifra: hay que medirlo antes de usar la
confirmación con ese preset.

---

## 4. Secuencia en el banco

### 4.1 Corte inmediato (sin mover la platina, sin tocar el espejo)

| Paso | Acción | Espera | Por qué |
|---|---|---|---|
| 0 | El criterio decide y cierra el obturador (ya ocurre) | — | — |
| 1 | `up_flipper()` (filtro a **baja**) con el obturador **cerrado** | t_flip: **1.0 s** hasta medirlo (el legado usa 1 s; BANCO-65 A4 puede bajarlo a 0.5 s) | el filtro es casero y sin realimentación (H2). Abrir antes de que llegue expondría a alta potencia |
| 2 | Durante esa espera, leer el **oscuro** D_PD y D_BS (100 ms) | dentro de t_flip | gratis; con las mismas luces (lámpara de campo oscuro) y la misma ganancia |
| 3 | Comprobar que pasó **≥ 1 s desde el cierre** | ya cubierto por t_flip | una NP atrapada se va ([AN17] p. 5) |
| 4 | `open_shutter` y renovar el latido | t_settle hasta la meseta del BS (≈ 50 ms; se fija con BANCO-30) | el obturador casero no tiene tiempo medido |
| 5 | **Chequeo del filtro por el BS** (primeros 20-30 ms): (V_BS − D_BS) / (V_BS,alta − D_BS) ≈ 1/A dentro de ±30 % | — | el BS es el único sensor de posición del filtro. Si está ≈ en el nivel de alta, el filtro no se movió: **se cierra en el acto** (≤ 30 ms más a alta potencia, dentro de la latencia del legado de 10-100 ms, [M24] p. 112), el nodo queda "no sé" y la grilla se **pausa**, porque el autofoco y los escaneos siguientes también serían a alta potencia. Si está ≈ en el oscuro, el obturador no abrió: "no sé" |
| 6 | Lectura de 100 ms (10 bloques) | 100 ms | §1.3 |
| 7 | `close_shutter` | — | — |
| 8 | **No** bajar el filtro acá | — | el nodo siguiente lo pide explícitamente: el autofoco lo quiere arriba y `_grid_trace` hace `down_flipper()` y espera 0.5 s (`measurements.py:2318`). Ahorra un ciclo cuando sigue un autofoco |

- **Costo:** ≈ 1.0 s (t_flip) + 0.05 + 0.03 + 0.1 ≈ **1.2 s** por nodo confirmado; ≈ 0.7 s si
  BANCO-65 A4 permite t_flip = 0.5 s. Frente a capturas de 1-20 s es un 5-50 %. Sólo se paga en los
  presets de ventana corta ([INV6] P13).
- **Platina:** no se mueve. **Espejo de detección:** tiene que estar arriba (detección confocal), y
  no se toca. Si está abajo, el paso 5 lo detecta (BS con luz, PD sin luz).
- **Si "Scan" está activo** (H8): el escaneo posterior ya sube el filtro y mira el sitio a baja
  potencia. En ese caso la imagen **es** la confirmación (contraste del pico contra la mediana del
  sustrato), sin costo extra. Recomiendo que la lectura puntual sea el camino por defecto y el
  escaneo, cuando está activo, la reemplace.
- **Desgaste:** el filtro casero suma un ciclo por nodo confirmado. Lo anoto para inventario, no lo
  considero un bloqueo.

### 4.2 Nodos expuestos sin decisión ("Cerrar todos", pausa, parada de emergencia, watchdog)

- **No** recomiendo confirmar en el acto después de "Cerrar todos": el operador cerró por algo, y
  reabrir solo contradice su intención. Además, en la pausa y en la parada de emergencia pueden pasar
  minutos.
- **Confirmación diferida:** en el Healing Pass, o al reanudar ese nodo:
  1. corrección de deriva en P0, si pasaron más de 60 s desde el cierre (§2.3);
  2. llegar al nodo y hacer el autofoco in situ (el filtro ya está arriba; H9);
  3. pasos 2 y 4 a 7 de §4.1 (oscuro, abrir, chequeo del BS, lectura, cerrar);
  4. con "no la ve", `down_flipper()` y la traza de impresión, como hoy.
  - **Costo extra:** ≈ 0.3 s, porque el ciclo del filtro ya lo pagaba el autofoco.
- **`acq_fault` con exposición:** inmediata (§4.1), sólo si la entrada analógica está disponible.
  Si la falla es de la placa, la lectura tampoco se puede hacer, y el nodo queda "en revisión".

---

## 5. Topes de plausibilidad (N-3)

### 5.1 Corrección de deriva sobre P0 (`on_scan_finished`, `drift_scan`)

**Por qué el tope de distancia solo no alcanza.**
- `_norm_image` lleva la imagen a [0, 1] por min-max y `_filter_image` corta al 30 %. Con una imagen
  **oscura** (obturador cerrado por "Cerrar todos", filtro trabado, P0 perdida), el resultado es el
  centro de masa del ruido umbralizado.
- Ese centro cae cerca del centro del escaneo, es decir, a pocos cientos de nm o menos de la posición
  anterior: **pasa cualquier tope de distancia razonable**.
- **[DERIVADO]**, a verificar con el escaneo oscuro de BANCO-65 C2.

**Topes que propongo (todos tienen que pasar para aplicar la corrección):**

| Tope | Valor | Justificación |
|---|---|---|
| T1 · obturador y luz | BS ≥ 0.7·BS_baja,ref durante todo el escaneo | P-a ([INV] R9): no se aplica una corrección calculada sobre oscuridad |
| T2 · amplitud | (máx − mediana)/σ_fondo ≥ 10 y amplitud del pico entre 0.5 y 2 veces la de la primera imagen de P0 de la sesión (`set_reference`) | descarta la imagen oscura, P0 perdida o dañada, y un doblete |
| T3 · ancho | ancho gaussiano entre 0.7 y 1.5 veces el de referencia (≈ 270 nm, H15) | ancho de más = desenfoque o dos objetos; ancho de menos = ruido |
| T4 · borde | centro a más de w₀ del borde del escaneo | un centro en el borde es un objeto a medias |
| T5 · paso | \|Δ\| respecto de la corrección anterior ≤ **50 nm + 2 nm/s·Δt**, por eje, con un techo de **500 nm** | 1 nm/s por eje de deriva (1.5 veces el peor eje de [M24] p. 75) más el doble de margen, y 50 nm de ruido de centro de masa y de error del escaneo. Ejemplos: Δt = 60 s → 170 nm; 300 s → 500 nm (techo). El techo es ~2 w₀: más allá, el problema no es deriva |
| T6 · acumulado | \|startX − xref\|, \|startY − yref\| ≤ **3 µm** | coherente con el margen de deriva de 3 µm que usa la verificación previa de rango (`measurements.py:1989`): más allá, la grilla puede salirse del recorrido verificado |

- **Si falla T1:** se repite el paso entero (P-a), sin contarlo como falla.
- **Si fallan T2 a T5:**
  1. no se aplica; se conserva `startX/startY` anterior y no se actualiza la velocidad de deriva
     (`_update_drift_velocity` con un centro absurdo da v enorme y N_eff = 1);
  2. se repite una vez, con el autofoco en la zona limpia del ancla;
  3. si vuelve a fallar, **pausa** con el banner "Corrección de deriva no plausible en P0: Δ = …,
     permitido …, amplitud …".
  - Recomiendo pausar y no sólo avisar, a diferencia de las rachas ([INV7] P-D): un error de deriva
    corre **todos** los nodos siguientes de forma sistemática, y el Healing Pass no lo arregla.
- **Si falla T6:** pausa siempre.
- **Después de una pausa larga**, T5 se evalúa con el Δt real (incluye la pausa) y el techo de
  500 nm sigue. Una deriva genuina de más de 500 nm en una pausa (≥ 8-12 min a 40-60 nm/min) la
  tiene que ver el operador.

### 5.2 Autofoco de la grilla (`focus_autocorr_lin_x2`)

**Hecho de código (H5):** no es el `argmax` del perfil (eso es `focus_go_to_maximum`, la ruta manual,
`focus.py:291-297`) sino el `argmax` de la **correlación** del perfil nuevo con el bloqueado, sobre
una rampa de 6 µm y repetido dos veces. Sobre un perfil oscuro, el máximo de la correlación del ruido
con el perfil bloqueado puede caer en cualquier lugar de la rampa: **un salto de hasta ±3 µm en Z**,
tres veces el FWHM axial.

FWHM axial de la intensidad focal con NA 1.0 en agua a 532 nm:
≈ 0.88·λ/(n − √(n² − NA²)) ≈ 0.88 · 0.532/(1.333 − 0.881) ≈ **1.0 µm** **[DERIVADO]**.

| Tope | Valor | Justificación |
|---|---|---|
| F1 · luz | BS ≥ 0.7·BS_baja,ref durante las rampas | P-a; igual que T1 |
| F2 · calidad | coeficiente de correlación normalizado (Pearson) entre el perfil nuevo desplazado y el bloqueado ≥ **0.8** **[SUPUESTO, BANCO-65 C3]** y pico del perfil ≥ 10 σ sobre su mediana | descarta perfil oscuro, perfil deformado por una NP o burbuja, y salto a un lóbulo lateral |
| F3 · coherencia interna | la segunda iteración corrige \|Δz₂\| ≤ **50 nm** | el `x2` ya trae la prueba: si el primer movimiento fue bueno, el segundo es ≈ 0. Un segundo movimiento grande es un pico ambiguo |
| F4 · paso | \|Δz\| respecto del último autofoco aceptado, menos lo que predice la inclinación (CAT-104 si está activa), ≤ **100 nm + 2 nm/s·Δt**, con techo de **300 nm** | sin dato de deriva en Z (H14), uso la misma escala que en XY. El techo de 300 nm es ~ ⅓ del FWHM axial y menor que el corrimiento a un lóbulo lateral (≳ 0.4 µm). La inclinación típica no está medida **[SUPUESTO]**: con 5 mrad y 10 µm de paso son 50 nm |
| F5 · borde | argmax fuera del 10 % extremo de la rampa | un máximo en el borde no es un máximo |

- **Si falla F1:** se repite el autofoco (P-a).
- **Si fallan F2 a F5:**
  1. **no se mueve Z**: vuelve a z_antes (`_focus_autocorr_lin` ya conoce `z_before`) o a la
     predicción por inclinación;
  2. se repite una vez;
  3. si falla otra vez, **pausa** con el banner "Autofoco no plausible en el nodo N".
  - El argumento es el de §5.1. Un desenfoque de 300 nm no impide imprimir, pero empeora la
    precisión, y uno de µm hace que todos los nodos terminen en T_max a alta potencia.
- **Estado de foco:** el Z final de cada autofoco aceptado se registra (ya existe
  `drift_history_z`); el rechazado, aparte, con su motivo.

---

## 6. Qué medir antes de habilitar esto: BANCO-65

### ☐ BANCO-65 — Confirmación a baja potencia y topes de deriva y foco ⚠️ láser de 532 nm (baja potencia; alta sólo sin coloide), con aprobación

**Requisitos:** BANCO-30 (tiempo de los obturadores) hecho o en la misma sesión; ganancia de los
PDA36A anotada (BANCO-22); espejo de detección arriba y confirmado (BANCO-64); potencia en la pupila
medida en la sesión; operador presente con la cámara en vivo.

**A. Sin coloide** (agua sobre PDDA/PSS; no hay NP que imprimir):
- **A1. Atenuación del filtro:** con el obturador abierto, V_BS en alta y en baja, 10 veces cada
  una, con el oscuro restado: A = (V_BS,alta − D)/(V_BS,baja − D). Anotar la OD.
  - **Criterio de seguridad:** A ≥ 10. Si es menor, la lectura a baja potencia **no** se habilita
    sin una deliberación nueva.
- **A2. Linealidad:** en el mismo punto, B = (V_PD − D_PD)/(V_BS − D_BS) en alta y en baja, a la
  ganancia de uso: k_lin = B_baja/B_alta.
  - **Aceptación:** 1.00 ± 0.03; si no, la opción (b) de §2 no se puede usar.
- **A3. Oscuro:** D_PD y D_BS con el obturador cerrado, 10 lecturas de 100 ms, con la lámpara de
  campo oscuro **encendida y apagada**. Anotar cuánto suma la lámpara.
- **A4. Ruido y sustrato:**
  - 30 lecturas de 100 ms en el mismo punto (σ_R en un punto);
  - 30 en puntos distintos a ≥ 2 µm (σ_R entre puntos, que incluye σ_sust);
  - las mismas 30 lecturas en un punto a lo largo de 30 min (la estabilidad de B para la
    confirmación diferida).
  - **Aceptación:** σ_R ≤ 0.02 en una lectura; base sin oscuro ≥ 2 mV.
- **A5. Tiempo del filtro casero:** con el obturador abierto, registrar el BS a 10 kS/s durante 10
  ciclos de `up_flipper()` y 10 de `down_flipper()`. Sin coloide, la exposición a alta potencia de
  los ciclos no tiene consecuencia.
  - **Aceptación:** p99 del tiempo de tránsito más 200 ms define t_flip. Si queda ≤ 0.5 s, la
    espera se baja.
  - Anotar si alguna vez queda a medio camino (nivel intermedio del BS).

**B. Con coloide** (Au de 60-100 nm, 0.5 mM NaCl, potencia de impresión habitual):
- **B1. r_baja contra r_alta:** imprimir 10 NP a mano (flujo de "Medir escalón"). En cada una:
  - r_alta, de la traza;
  - r_baja, con la secuencia de §4.1 a 1 s del corte, y otra vez a 10 s, 60 s y 300 s sin tocar
    nada;
  - un escaneo de 2 × 2 µm a baja potencia, para medir el corrimiento NP-haz.
  - **Da:** k, la curva de pérdida por deriva (contrastar con la tabla de §2.3) y u_c de la sesión.
- **B2. Vacíos con coloide:** 50 lecturas de 100 ms sobre puntos vacíos, a baja potencia. Contar las
  lecturas con un bloque fuera de 3 σ (NP de paso) y si alguna termina en "ve la NP" (falso
  positivo).
- **B3. Seguridad a baja potencia:** un punto vacío con el obturador abierto a baja potencia
  durante **60 s** (≈ 300 lecturas, 30 autofocos).
  - **Aceptación:** ninguna NP impresa (cámara y escaneo final). Confirma con un margen de ×300 que
    la lectura no imprime.
- **B4. Matriz de confusión:** 20 nodos a alta potencia cortados con "Cerrar todos" en instantes al
  azar, unos antes y otros después de la captura. La cámara da la verdad. Después, la confirmación
  diferida de §4.2.
  - **Aceptación:**
    - **ningún** nodo impreso clasificado "no la ve" (es el error que reimprime sobre una NP);
    - ≤ 1/20 vacíos clasificados "ve la NP";
    - ≤ 2/20 "no sé".
  - Repetir con 5 nodos en pausa de 5 min (prueba la regla de 60 s).
- **B5 (sólo si se va a usar):** lo mismo con Ag a 532 nm, fuera de resonancia.

**C. Topes de N-3** (pueden ir con BANCO-33, deriva):
- **C1. Ruido del centro de masa:** 20 escaneos seguidos sobre P0 en 2 min: σ_CM por eje, ancho
  gaussiano y amplitud de referencia.
- **C2. Escaneo oscuro:** un escaneo de deriva con el obturador cerrado (y otro con el filtro
  trabado arriba). Anotar qué centro de masa devuelve, para verificar que T5 solo no lo detecta y
  T2 sí.
- **C3. Autofoco:** 20 autofocos en el mismo sitio (σ_z, Δz₂ de la segunda iteración, coeficiente
  de correlación); uno con el obturador cerrado (cuánto saltaría Z). Este último **sólo** con la
  platina en el centro de su recorrido en Z y el operador mirando: el salto puede ser de µm.
- **C4. Inclinación:** las cuatro esquinas de una grilla de 20 × 20 µm (CAT-104), para fijar la
  predicción de F4.

**Registro:** los valores medidos (A, k_lin, D, σ_R, t_flip, k, u_c, σ_CM, σ_z) se anotan con fecha
y ganancia de los PDA, y pasan a `lab-invariants` como EXPERIMENTAL del banco.

---

## 7. Supuestos marcados

| # | Supuesto | Cómo se cierra |
|---|---|---|
| S1 | La atenuación del filtro casero es ≥ 10 (OD ≥ 1) | BANCO-65 A1 |
| S2 | El PD de detección y el BS son lineales entre alta y baja (k_lin ≈ 1) | BANCO-65 A2 |
| S3 | La base a baja potencia es ≥ 2-5 mV sobre el oscuro, a la ganancia de uso | BANCO-65 A4 |
| S4 | r_baja ≈ r_alta (k ≈ 1) para Au a 532 | BANCO-65 B1 |
| S5 | Ruido RMS del PDA36A del orden de décimas de mV a 1 mV (hoja de datos no cargada) | hoja de datos de Thorlabs y BANCO-65 A4 |
| S6 | La deriva en Z es del mismo orden que en XY (sin número de fuente) | BANCO-33 y BANCO-65 C3 |
| S7 | Inclinación de la muestra ~ mrad | BANCO-65 C4 |
| S8 | Una imagen oscura da un centro de masa cercano al centro del escaneo | BANCO-65 C2 |
| S9 | Los valores de CIBION (w₀, error de 50 nm RMS, β, P_th) valen como orden de magnitud para el banco | tienen el rótulo (CIBION) en `lab-invariants` |

---

## 8. Preguntas conceptuales para el investigador

1. **Filtro de densidad.** ¿Sabés qué densidad óptica tiene el filtro del flipper casero?
   - (a) OD 1 (×10); (b) OD 2 (×100); (c) OD 3 o más; (d) no se sabe.
   - **Recomiendo** medirla igual en BANCO-65 A1 (el BS da la atenuación real). Si es menor que
     OD 1, la lectura a baja potencia necesita otra deliberación: ya no es "más corta que un
     autofoco que no imprime".
2. **Cuándo se confirma un nodo cortado por "Cerrar todos", una pausa o una parada de emergencia.**
   - (a) En el acto, antes de mover la platina, reabriendo el obturador sin que el operador lo pida.
   - (b) Diferida: en el Healing Pass o al reanudar ese nodo, después de la corrección de deriva y
     del autofoco in situ.
   - **Recomiendo (b)** para esos casos: respeta la intención del operador, cuesta ≈ 0.3 s porque el
     filtro ya está arriba por el autofoco, y después de una pausa la deriva obliga a recentrar
     igual. Para el corte por criterio en los presets de ventana corta y para `acq_fault` con
     exposición, en el acto (§4.1).
3. **"No sé".** Si la lectura queda entre "ve" y "no ve" después de dos intentos:
   - (a) "en revisión", decide el operador mirando la cámara;
   - (b) se reintenta igual;
   - (c) se marca impresa.
   - **Recomiendo (a).** Reimprimir sobre una NP fija la tiene hasta 50 s a alta potencia sin
     escalón que corte el nodo, y es el error más caro.
4. **Corrección de deriva o autofoco no plausibles** (después de repetirlos una vez):
   - (a) pausar la grilla con un banner;
   - (b) avisar, conservar la corrección anterior y seguir.
   - **Recomiendo (a).** A diferencia de las rachas de nodos sin captura ([INV7] P-D), un error de
     deriva o de foco afecta en forma sistemática a todos los nodos siguientes, y el Healing Pass no
     lo corrige.
5. **El escaneo posterior a la impresión ("Scan").** ¿Lo usan en las grillas de hoy?
   - (a) Sí, siempre; (b) a veces; (c) no.
   - **Recomiendo** que, cuando está activo, la imagen reemplace a la lectura puntual como
     confirmación (no cuesta nada extra), y que la lectura puntual sea el camino por defecto.
6. **Filtro trabado.** Si el chequeo del BS muestra que el filtro no subió (§4.1, paso 5):
   - (a) cortar el nodo y pausar la grilla;
   - (b) cortar y avisar.
   - **Recomiendo (a).** Si el filtro no sube, el autofoco y los escaneos siguientes serían a alta
     potencia, es decir, impresión durante el foco.

---

## Veredicto

**MODIFICATION_REQUIRED.**

La confirmación a baja potencia es físicamente sólida: el contraste es una razón que no depende de
la potencia, el banco ya expone a baja potencia más tiempo en cada autofoco, y tiene un antecedente
publicado ([AN17] p. 5). Para habilitarla hacen falta tres cosas:
- resta del oscuro y normalización por el BS en cada lectura;
- el chequeo del filtro por el BS antes de leer;
- BANCO-65, que mide la atenuación del filtro casero, la linealidad, σ_R y k, y da la matriz de
  confusión contra la cámara.

Los topes de N-3 no dependen de R4-3. Se pueden diseñar ya, con el dato de que el autofoco de la
grilla usa correlación, y de que el tope de distancia solo no detecta un escaneo oscuro.
