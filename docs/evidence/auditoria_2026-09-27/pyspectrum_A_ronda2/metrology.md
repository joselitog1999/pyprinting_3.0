# PySpectrum 3.0 · Bloque A · Ronda 2: calibración automática de offsets del Shamrock (metrología)

> Ronda de motor (CLAUDE.md §5, Ronda 2). No hay código de producción: sólo modelo, pseudocódigo, firmas y simulaciones hechas en el scratchpad. No se ejecutó nada contra el hardware.
> Autor: subagente `metrology`, 2026-09-28. **Estado: completo (secciones 0-7).** Fuentes web usadas: la hoja de datos del Excelsior (Spectra-Physics) y dos referencias sobre diodos verdes; se citan con su URL en §3.4.

## 0. Rótulos y fuentes

| Rótulo | Qué significa |
|---|---|
| **RESPALDADO** | Lo dice una fuente primaria, citada con su página. |
| **DERIVADO** | Cuenta propia a partir de valores respaldados; se muestra la cuenta. |
| **SIMULADO** | Resultado de una simulación Monte Carlo de este documento (script en el scratchpad de la sesión; parámetros en §2.4). Vale para el modelo simulado, no para el banco. |
| **INFERENCIA** | Razonamiento sin fuente que lo confirme. Se verifica. |
| **EXPERIMENTAL** | Dato del investigador que no está publicado. |
| **SIN VALOR** | Término que no se midió. No se rellena: bloquea la U que lo necesita. |

| Clave | Fuente | Dónde |
|---|---|---|
| [DS-SR500] | Hoja de datos Andor Shamrock 500i | `docs/bibliografia/andor-shamrock-500-specifications.pdf` |
| [DS-iXon] | Hoja de datos Andor iXon3 885 | `docs/bibliografia/Andor_iXon3_885_Specifications.pdf` |
| [SDK2] | Andor SDK2 v2.104 (cámaras) | `docs/bibliografia/Software Development Kit.pdf` |
| [R1-E] | Ronda 1, experimentalista | `../pyspectrum_A_ronda1/experimentalist.md` |
| [R1-I], [R1-D] | Ronda 1, instrumentación y abogado del diablo | `../pyspectrum_A_ronda1/` |
| [R4-A] | Respuestas del investigador | `../RESPUESTAS_INVESTIGADOR.md` §R4-A |
| [GUM] | JCGM 100:2008 | norma |


---

## 1. Modelo de medición

### 1.1 Magnitudes

| Símbolo | Qué es | Unidad | Fuente |
|---|---|---|---|
| g | red activa (1 = 150 l/mm, 2 = 1200 l/mm) | — | `shamrock_driver.py::NAME_GRATINGS` |
| O_g | offset de la red g, entero | pasos de motor | docstring `ShamrockSetGratingOffset` (`scratch/pyspectrum-legacy/Shamrock_ps.py:2363-2385`; secundario) |
| O_D | offset del detector | pasos | fijo en 0 por convención [R4-A.2]; la rutina **no lo escribe nunca** |
| λc | λ central ordenada con `SetWavelength` | nm | — |
| λ_SDK(p) | eje que devuelve `ShamrockGetCalibration` para el estado actual (g, λc, O_g, O_D, geometría declarada 1004 px × 8 µm) | nm | driver |
| p_SDK(λ) | su inversa (interpolación monótona del eje) | px | — |
| x̂ | centro estimado de la línea del láser en el detector | px (índice 0 … 1003) | §2 |
| λ_L | λ del láser de referencia **en aire**, el número que se declara en el archivo | nm | §3 (no hay dato: SIN VALOR) |
| D | dispersión local \|dλ_SDK/dp\| en x̂ | nm/px | nominal 0.1026 (150) y 0.01152 (1200) nm/px: 12.83 y 1.44 nm/mm × 8 µm (`lab-invariants` filas 119-120; DERIVADO) |
| S_g | sensibilidad del residuo al offset de la red g | px/paso | **desconocida**, con signo desconocido (BANCO-A1 / BANCO-40) |

### 1.2 El mensurando de la calibración es un residuo, no una posición

Se define el **residuo de calibración** en píxeles:

  r(O) = x̂ − p_SDK(λ_L)  ≈  [λ_SDK(x̂) − λ_L] / D

Es "dónde cae la línea" menos "dónde el SDK dice que debería caer". La calibración busca r = 0.

**Por qué el residuo y no x̂ (DERIVADO).** Hay dos mecanismos posibles para un offset, y la Ronda 1 no pudo decidir cuál rige ([R1-I] preguntas 1-2; BANCO-40):
- (a) el offset **mueve el motor**: con el mismo λc la red queda en otro ángulo, x̂ se corre y el eje del SDK no cambia;
- (b) el offset **sólo cambia el cálculo**: el motor no se mueve, x̂ queda igual y el eje se corre.

En los dos casos r cambia linealmente con O y con la misma pendiente en valor absoluto. Trabajar sobre r hace que el algoritmo **no dependa** de qué mecanismo rija. De paso, la rutina registra cuál de los dos se movió (x̂ o p_SDK(λ_L)): eso resuelve BANCO-40 sin una prueba aparte.

### 1.3 Modelo lineal en el offset

  r(O_g) = r(O_0) + S_g · (O_g − O_0) + ε_rep + ε_ruido + ε_deriva

- **ε_ruido**: error del estimador del centro (fotones, lectura, fondo). Tipo A; se simula en §2.4.
- **ε_rep**: error de posicionamiento de la torreta en cada llegada a λc. La hoja de datos da una repetibilidad de **10 pm** como σ de 20 medidas del centro de masa de un pico, moviendo la torreta 10 veces entre medida y medida, incluidos cambios de red, con la red de 1200 ([DS-SR500] p. 13, nota 20; RESPALDADO). Con 0.01152 nm/px eso es **σ_rep ≈ 0.87 px** (DERIVADO). Para la red de 150 se supone la misma repetibilidad **angular**, es decir ~0.9 px (≈ 0.09 nm) [R1-E §2.3; INFERENCIA]. **Es el término que domina el centro de una sola llegada** (§3).
- **ε_deriva**: deriva térmica del espectrógrafo y del láser durante la sesión. SIN VALOR (BANCO-A5).
- **S_g** se supone lineal y constante en el rango de trabajo. La linealidad se comprueba (§2.2, paso P).

**Qué no se puede separar (RESPALDADO por [R1-E] §1.3, DERIVADO).** Con una línea por red sólo se observa la suma O_D·S_D + O_g·S_g. Con O_D = 0 fijo [R4-A.2], toda la corrección cae en O_g: la calibración es **por red** y no dice nada del detector.

### 1.4 Qué hay que estimar primero: S_g, con dos movimientos

Sin S_g no se sabe cuántos pasos corregir. Orden de magnitud: el manual del SR-303 da "~3 unidades por píxel de 26 µm"; escalado a f = 500 mm y píxel de 8 µm serían ~1.8 px/paso ([R1-E] §1.4; **INFERENCIA de otro modelo**, sólo para acotar la sonda). Con esa escala el offset actual de 85 pasos equivaldría a ~150 px, lo que la Ronda 1 juzgó improbable: **S puede ser bastante menor**.

**Estimación por secante (mínimo de movimientos):**
1. Medir r₀ en O₀ (el offset vigente, leído del equipo).
2. Sondear en O₀ + ΔO, con ΔO = +4 pasos, y medir r₁. Ŝ = (r₁ − r₀)/ΔO.
3. Si |r₁ − r₀| < max(3 px, 5·u(r₁ − r₀)), duplicar ΔO (8, 16, 32, 64) desde O₀ y volver a medir. Tope: |ΔO| ≤ 64 pasos por sonda. Con la escala del SR-303 son ~115 px: la línea sigue en el detector.
4. Volver a O₀ **siempre** antes de seguir (la sonda es transitoria y se restaura; releer).

- Son **dos escrituras** (sonda y restauración) si la primera sonda alcanza, y hasta 2 × 5 en el peor caso.
- u(Ŝ)/Ŝ = u(Δr)/|Δr|. Con 4 llegadas por punto y σ_rep = 0.87 px, u(Δr) = √2·0.87/√4 ≈ 0.62 px, así que el criterio de 3 px da u(Ŝ)/Ŝ ≲ 20 % (DERIVADO). Alcanza: Ŝ sólo se usa para **proponer** el paso; el resultado final se **mide** directamente (§1.5), así que u(Ŝ) no entra en la incertidumbre final.
- Ŝ se guarda por red con fecha y u(Ŝ). En las calibraciones siguientes se reutiliza y la sonda se salta, salvo que la primera corrección no converja (§2.3).
- **Signo y linealidad** (paso P opcional, recomendado la primera vez): un tercer punto en O₀ − ΔO. Si |r(O₀+ΔO) + r(O₀−ΔO) − 2r₀| > 3·u, S no es lineal en ese rango y la rutina se detiene.

### 1.5 Corrección entera y resto de software

- Offset propuesto: **O* = O₀ + round(−r₀ / Ŝ)**.
- La cuantización deja un resto: después de escribir O*, el residuo medido r(O*) está, en ausencia de ruido, en [−|S|/2, +|S|/2].
- Ese resto **se mide** (no se calcula con Ŝ) y se guarda como corrección de software en píxeles, c = −r(O*), con su incertidumbre. Como la línea de λ_L cae en x̂ pero el SDK la ubica en x̂ − r, el eje corregido es **λ(p) = λ_SDK(p + c)** (DERIVADO; el signo se fija con un test, §5.2 T9).
- **Consecuencia (DERIVADO):** si |S| > 1 px/paso, el criterio provisorio de ≤ 0.5 px con la red de 150 [R4-A.9] **no se puede cumplir sólo con el hardware**; sí con hardware + software. Por eso el criterio de aceptación se define sobre el residuo *después* de la corrección de software, y se informa aparte el residuo de hardware (§4.2).

---

## 2. Algoritmo

### 2.1 Estimador del centro de la línea

**Elección: gaussiana + fondo lineal, ajustada por mínimos cuadrados sin ponderar, en una ventana de ±3 FWHM recentrada una vez.** En la simulación de §2.4, con SNR ≥ 5, queda dentro del 5-10 % de la cota de Cramér-Rao, con sesgo ≤ 0.02 px en todo el rango. Es el único estimador probado que no se sesga con fondo inclinado.

| Opción | Veredicto | Por qué |
|---|---|---|
| **Gaussiana + fondo lineal** | **se adopta** | Eficiente y sin sesgo (SIMULADO). El fondo lineal absorbe el ala del notch y la luz espuria junto a la línea ([DS-SR500] p. 13 da 1.1·10⁻⁴ a 1 nm del láser en FVB; [R1-E] §6.10). |
| Gaussiana + fondo constante | no | Con un fondo inclinado de 2 e⁻/px y SNR 10 se sesga +0.05 px (SIMULADO, §2.4 B). |
| Voigt | no, por ahora | Para un perfil **simétrico**, cualquier modelo simétrico estima el centro sin sesgo. Los parámetros de forma que agrega se correlacionan con el fondo y agrandan la varianza cuando el SNR es bajo. Si la línea es asimétrica, la Voigt tampoco lo resuelve, porque también es simétrica: hay que diagnosticarlo (§2.1, diagnósticos). |
| Centroide (centro de masa) | sólo como diagnóstico | Con SNR 10-50 su dispersión es 1.7-2 veces la de la gaussiana y depende del fondo estimado (SIMULADO). Sirve para detectar asimetría comparándolo con la gaussiana. |
| Máximo (argmax), el "a ojo" de Solis | no | Tiene un piso de ≈ 0.29 px = 1/√12 aun con SNR 200 (SIMULADO): es la cuantización de un píxel. **El método manual de hoy no baja de ≈ 0.3 px**, sin contar la repetibilidad. |
| Parábola sobre 3 puntos | no | 3-5 veces peor que la gaussiana (SIMULADO). |
| Modelo integrado en el píxel (erf) | no hace falta | Se simularon datos integrados en el píxel y se ajustaron con una gaussiana puntual: el sesgo por fase subpíxel fue ≤ 0.02 px con σ ≥ 1.3 px. Se revisa si la línea medida tiene σ < 1 px (FWHM < 2.4 px). |

**Pixelado.** No se agrega un término Δx/√12 al presupuesto. El pixelado ya está incluido en el ajuste y en su incertidumbre; ese término vale sólo para el argmax, que no se usa (L5-202-06).

**Ponderación.**
- *Por qué no se pondera.* Sin ganancia EM y con una línea débil domina la lectura: 12-25 e⁻ rms según la velocidad ([DS-iXon] p. 2), multiplicados por √9 al sumar 9 filas. Los pesos serían casi uniformes. Con ruido simétrico, los mínimos cuadrados sin ponderar no sesgan el centro, y la simulación los muestra eficientes.
- *Qué u se informa.* La mayor de dos:
  - la de la covarianza, escalada por χ²_red;
  - la de Tipo A que sale de ajustar cada cuadro por separado (s/√K).
- *Por qué se exige SNR ≥ 20.* Con SNR 3 la covarianza subestima la dispersión real en un 20-30 % (0.36 contra 0.50 px; SIMULADO). Por eso la rutina sube la exposición hasta llegar a SNR ≥ 20.

**Pasos del estimador:**
1. **Oscuro.** Restar el oscuro medio: K_d cuadros con el obturador del láser cerrado, con la misma exposición y el mismo ROI, antes y después.
2. **Rayos cósmicos, con rechazo temporal.**
   - *Cómo:* para cada píxel, entre los K cuadros, se descarta todo valor que se aparte de la mediana más de 5·max(σ_MAD, σ_esperada), y se promedia el resto (media con recorte). K mínimo = 3; por defecto K = 5.
   - *Qué pasa sin rechazo:* con un rayo en la mitad de los cuadros, la media sin rechazo corre el centro **3.5 px rms**. Con la mediana se reduce a 0.13-0.40 px, y con la media con recorte a 0.11-0.23 px (SIMULADO, §2.4 D).
   - **No se usa el despike espacial del repositorio** (`core/sif_processor.py::filter_despike_median`, l. 631-658): sobre una línea limpia y angosta marca ~2 píxeles **del propio pico**, y la dispersión del centro pasa de 0.002 a 0.069 px con σ = 1 px (SIMULADO, §2.4 C).
3. **Saturación**, sobre los cuadros **crudos** 2D, antes de sumar filas.
   - Se rechaza la llegada si algún píxel del ROI supera 0.8 × 16 383 cuentas (ADC de 14 bit, [DS-iXon] p. 2; necesita el símbolo de C-25).
   - Objetivo de exposición: un pico entre el 20 y el 50 % del ADC [R1-E §2.1].
   - Linealidad del detector: mejor que el 99 % ([DS-iXon] p. 2).
4. **Suma de filas del ROI.** Por defecto, la traza ± 4 filas (las 9 filas del legado).
5. **Búsqueda gruesa.**
   - *Cómo:* restar una mediana móvil de ancho 15·FWHM (pasa-altos), suavizar con una gaussiana de σ = σ_guess y tomar el argmax dentro de p_SDK(λ_L) ± W_búsqueda, sin los 15 px de cada borde.
   - *Por qué el pasa-altos:* sin él, un fondo inclinado arrastra el argmax al borde. En la primera simulación eso dio 100 % de fallas.
   - *Umbral de detección:* SNR ≥ 8 para aceptar una línea y ≥ 20 para calibrar. Con SNR 5 y fondo inclinado la detección todavía falla a veces (§2.4 B).
6. **Ajuste fino.** Ajustar en ±3 FWHM alrededor del argmax, recentrar la ventana en x̂ y ajustar otra vez: una ventana descentrada trunca el fondo en forma asimétrica.
7. **Diagnósticos.** Levantan una bandera, y según el caso detienen la rutina. Nunca "corrigen" nada.
   - **ASIMETRÍA:** \|x̂_gauss − x̂_centroide\| > max(0.1 px, 3·u_dif). Un hombro del 10 % a 1.5σ da −0.09 px (SIMULADO, §2.4 E). Causas posibles:
     - láser multimodo resuelto, sobre todo con la red de 1200;
     - la transmisión del notch, que pondera la línea;
     - coma.
   - **ANCHO:** FWHM > 1.5 × el de referencia de esa red y esa ranura (el primero que se guardó). Indica estructura de modos o desenfoque.
   - **BORDE:** x̂ a menos de 15 px del borde.
   - **χ²_red** fuera de [0.5, 2] **con** residuos estructurados (prueba de rachas).

### 2.2 Una "llegada" y su residuo

```
llegada(λc, δ_g):                                 # acercamiento siempre desde abajo
    SetWavelength(λc − δ_g); esperar fin de movimiento + asentamiento
    SetWavelength(λc);       esperar fin de movimiento + asentamiento
    λc_leído = GetWavelength()                    # se registra
    eje      = GetCalibration(1004)               # SIEMPRE después del movimiento
    exigir eje monótono y geometría releída = (1004 px, 8.0 µm)
    cuadros  = K × [iniciar, esperar, leer]       # nunca "el último cuadro" (R4-5)
               # obturador de 532 abierto sólo durante los cuadros; heartbeat en cada cuadro
    perfil   = rechazo_temporal(cuadros − oscuro) → suma de filas
    línea    = estimar_centro(perfil)             # §2.1; si falla, la llegada es inválida
    r        = línea.x̂ − p_SDK(λ_L; eje)          # inversa del eje por interpolación
    D        = |dλ_SDK/dp| en x̂
    devolver r, u_ruido, λc_leído, eje, D, banderas

medir_residuo(O, M):                              # M llegadas con el mismo offset
    r_m = [llegada(...) para m = 1..M]
    devolver r̄ = media(r_m), u_A = s(r_m)/√M, ν = M − 1, s_rep = s(r_m)
```

- **δ_g** es 20 nm con la red de 150 y 3 nm con la de 1200 [R1-E §2.2]. Es un parámetro; se ajusta con BANCO-A3.
- **Después de cada escritura del offset se repite la llegada completa.** Así el resultado es el mismo tanto si la escritura mueve el motor (§1.2 a) como si no (§1.2 b).

### 2.3 Lazo de calibración (pseudocódigo)

```
calibrar_offset_red(g, λ_L, cfg):
    precondiciones (si falla una, no se ejecuta):
        hardware real (sin simulador), ganancia EM = 0 confirmada por relectura,
        CCD estabilizado, red g confirmada, geometría releída = (1004, 8.0),
        ranura leída, espejo de detección abajo (estado del software, C-08: se advierte),
        notch puesto (confirma el operador), O_D leído (no se toca nunca)
    O0 = leer_offset(g); comparar con el archivo; registrar respaldo
    exposición automática: SNR ≥ 20 y pico entre 20 y 50 % del ADC, sin pasar t_max
    r0 = medir_residuo(O0, M_iter)

    S = cfg.S_previa (del archivo, con su u)  o bien  sondear_S(O0, r0)   # §1.4: restaura O0 y relee
    probados = {O0: r0};  O = O0
    repetir hasta cfg.max_iter (= 4) veces:
        paso = round(−r̄(O) / S)
        paso = recortar(paso, ±cfg.paso_max (= 64));  exigir |O + paso − O0| ≤ cfg.cambio_total_max (= 200)
        si paso == 0: salir                        # punto fijo entero
        si O + paso ∈ probados: salir              # ciclo entre enteros vecinos
        si cfg.en_seco: registrar la propuesta y la predicción r̄ + S·paso; salir sin escribir
        escribir_offset(g, O + paso) con doble confirmación; releer;
            si la relectura no coincide: restaurar O0 y abortar
        O = O + paso;  probados[O] = medir_residuo(O, M_iter)
        si |Δr̄| ≥ 3 px: S = secante de los dos últimos puntos   # si S cambia de signo: abortar
    si no hubo convergencia en max_iter: restaurar O0 y abortar ("S inconsistente o no lineal")

    O_mejor = argmin |r̄(O)| sobre los probados;  escribirlo si O_mejor ≠ O
    verificación con datos NUEVOS: r_ver = medir_residuo(O_mejor, M_final)
        # M_final secuencial (§3.2): desde 9, de a una llegada, hasta u_A ≤ u_objetivo o M = 25
        # elegir el mínimo entre medidas ruidosas lo sesga hacia 0 (sesgo de selección);
        # la verificación independiente elimina ese sesgo
    c_sw = −r̄_ver,  u(c_sw) = u_A(r_ver)
    control de deriva: una llegada más al final;  |r_final − r̄_ver| ≤ 3·s_rep
    recorrido de la línea (≥ 3 λc): λc ∈ {λ_L − 0.35·W_g, λ_L, λ_L + 0.35·W_g}, cada una desde abajo, M_iter llegadas,
        residuo con c_sw aplicado; el signo de dx̂/dλc debe ser el que predice el eje del SDK
    aceptación (§4.2) y agregado al archivo (§4.1)
```

**Parámetros del recorrido.** W_150 ≈ 103 nm y W_1200 ≈ 11.6 nm (`lab-invariants` fila 121). Así, ±0.35·W equivale a ±36 nm y ±4 nm: es la P8 de [R1-D] y cae dentro del ±40 / ±4 nm de [R1-E §2.4].

**Parada.** Punto fijo entero, ciclo o max_iter.

**Topes.** Hasta 4 correcciones, más un máximo de 5 duplicaciones en la sonda.
- Con S conocida, el lazo converge en un paso, porque el modelo es lineal.
- Un segundo paso corrige un error de S del 20-50 %.

**Abortos.** Pérdida de la línea, saturación, relectura distinta, exceso de cambio_total_max, error del hardware o Stop. **Todo aborto restaura O0 y lo relee.**

**Por defecto, en seco:** calcula y registra la propuesta sin escribir. Escribir requiere doble confirmación [R4-A.5]. **El offset del detector no se escribe nunca.**

### 2.4 Simulación del estimador y del lazo (SIMULADO)

**Scripts.** Están en el scratchpad de la sesión (`sim_center.py`, `sim2.py`, `sim_loop.py`), no en el repositorio.

**Modelo:**
- *Línea:* gaussiana **integrada en cada píxel** (erf), con x₀ = 501 + U(0,1) px, es decir, fase subpíxel aleatoria.
- *Fondo:* B₀ = 200 e⁻ por columna.
- *Ruido:* Poisson más lectura de 22 e⁻ rms por píxel (27 MHz sin EM, [DS-iXon] p. 2), con 9 filas sumadas.
- *SNR:* altura del pico dividida por la σ de una columna de fondo.
- *Réplicas:* 1500 por punto.
- *CRLB:* numérica, para los parámetros (área, x₀, σ, B₀, B₁) y con varianza heteroscedástica.

**A. Sesgo y dispersión del centro según el SNR (fondo plano; en px):**

| SNR | CRLB | Gauss+lin: sesgo | Gauss+lin: desvío estándar | u de la covarianza (mediana) | Centroide: desvío estándar | Parábola: desvío estándar | Argmax: desvío estándar |
|---|---|---|---|---|---|---|---|
| **σ = 1.3 px (FWHM 3.1)** | | | | | | | |
| 3 | 0.41 | +0.016 | 0.50 (7.7 % de fallas) | 0.36 | 0.98 | 0.86 | 0.93 |
| 5 | 0.25 | +0.010 | 0.27 | 0.23 | 0.52 | 0.44 | 0.58 |
| 10 | 0.127 | −0.001 | 0.128 | 0.120 | 0.24 | 0.23 | 0.41 |
| 20 | 0.066 | +0.003 | 0.066 | 0.062 | 0.12 | 0.13 | 0.34 |
| 50 | 0.029 | +0.001 | 0.029 | 0.025 | 0.048 | 0.057 | 0.29 |
| 200 | 0.009 | 0.000 | 0.010 | 0.007 | 0.014 | 0.028 | 0.28 |
| **σ = 2.5 px (FWHM 5.9)** | | | | | | | |
| 3 | 0.57 | +0.014 | 0.64 | 0.53 | 1.39 | 1.45 | 1.54 |
| 5 | 0.34 | +0.001 | 0.36 | 0.33 | 0.68 | 0.89 | 0.98 |
| 10 | 0.175 | −0.001 | 0.180 | 0.170 | 0.33 | 0.57 | 0.70 |
| 20 | 0.091 | −0.001 | 0.093 | 0.086 | 0.17 | 0.35 | 0.53 |
| 50 | 0.040 | 0.000 | 0.040 | 0.035 | 0.068 | 0.17 | 0.37 |
| 200 | 0.013 | −0.001 | 0.014 | 0.010 | 0.019 | 0.066 | 0.30 |

Qué muestra la tabla:
- **Sesgo:** no hay sesgo detectable. \|sesgo\| ≤ 0.016 px, del orden del error estándar de la media.
- **Eficiencia:** desde SNR 5, la dispersión queda **dentro del 10 % de la CRLB**.
- **La u de la covarianza es algo optimista:** entre 5 y 15 % con SNR ≥ 10, y 25-30 % con SNR 3.
- **Con SNR 20, una llegada tiene u ≈ 0.07-0.09 px**, diez veces menos que la repetibilidad de la torreta (0.87 px). **El ruido no domina la calibración.**

**B. Fondo inclinado** (σ = 2.5 px, 600 réplicas):
- Con 0.5 e⁻/px, gauss + lin tiene un sesgo ≤ 0.005 px, y gauss + constante hasta +0.019 px.
- Con 2 e⁻/px y SNR 10-20, gauss + lin sigue en ≤ 0.005 px, pero **gauss + constante sube a +0.031 / +0.053 px**.
- Con SNR 5 y 2 e⁻/px, la búsqueda gruesa se engancha a veces en otro rasgo (desvío estándar de 20 px). Por eso hay un umbral de detección.

**C. Despike espacial del repo sobre una línea limpia** (sin rayos). Marca ~2 píxeles del pico en todos los casos. La dispersión del centro cambia así:

| σ de la línea | SNR | sin despike | con despike |
|---|---|---|---|
| 1.0 px | 200 | 0.009 px | 0.071 px |
| 1.0 px | 2000 | 0.002 px | 0.069 px |
| 1.3 px | 200 | 0.010 px | 0.043 px |
| 2.5 px | — | casi no afecta | casi no afecta |

**D. Rayos cósmicos** (5 cuadros; en cada cuadro, 50 % de probabilidad de un rayo de 2·10³-2·10⁴ e⁻ a ±8 px de la línea). Cada celda da el error del centro como rms / percentil 95:

| SNR total | media | mediana | media con recorte |
|---|---|---|---|
| 20 | 3.5 / 7.3 px | 0.13 / 0.22 px | 0.11 / 0.19 px |
| 50 | 1.4 / 2.5 px | 0.40 / 0.10 px | 0.23 / 0.08 px |

Con SNR 50, la mediana tiene pocos casos muy desviados, que inflan su rms por encima de su percentil 95.

**E. Asimetría** (SNR 50). La diferencia x̂_gauss − x̂_centroide vale:
- −0.094 ± 0.047 px con un hombro del 10 % a +1.5σ;
- −0.145 ± 0.042 px con un hombro del 30 %.

El diagnóstico detecta hombros de ≳ 10 % con SNR 50.

**F. Lazo completo** (4000 réplicas; r₀ ~ U(−30, 30) px; σ_rep = 0.87 px y σ_ruido = 0.1 px por llegada). "Error final" es el error del resto de software medido en la verificación, con M llegadas nuevas: es lo que queda después de corregir con hardware y software.

| S (px/paso) | M | Escrituras (mediana / máx.) | Llegadas (mediana) | Error final rms | P(\|err\| ≤ 0.5 px) | P(\|err\| ≤ 1 px) |
|---|---|---|---|---|---|---|
| +0.2 | 4 | 9 / 11 | 40 | 0.44 | 0.74 | 0.98 |
| +0.2 | 9 | 8 / 11 | 81 | 0.29 | 0.92 | 1.00 |
| +0.6 | 1 | 7 / 11 | 8 | 0.88 | 0.42 | 0.74 |
| +0.6 | 4 | 6 / 9 | 24 | 0.44 | 0.76 | 0.98 |
| +0.6 | 9 | 5 / 9 | 54 | 0.29 | 0.92 | 1.00 |
| +1.8 | 4 | 4 / 7 | 16 | 0.43 | 0.75 | 0.98 |
| +1.8 | 9 | 3 / 6 | 36 | 0.29 | 0.92 | 1.00 |
| −1.0 | 4 | 4 / 9 | 20 | 0.44 | 0.75 | 0.98 |
| +1.8, S previa ±20 % | 4 | 2 / 6 | 16 | 0.44 | 0.74 | 0.97 |
| +0.6, torreta 3× mejor (σ_rep 0.3) | 4 | 5 / 8 | 24 | 0.16 | 1.00 | 1.00 |

Qué muestra la tabla:
- **El error final sigue a ≈ 0.88/√M**, es decir, √(σ_rep² + σ_ruido²)/√M. **Lo fijan la torreta y el número de llegadas, no el estimador ni S.**
- **Con la repetibilidad de la hoja de datos:** M_final = 9 cumple el criterio provisorio de 0.5 px en el 92 % de los casos; M = 4, sólo en el 75 %.
- **Si la torreta del banco es mejor** (BANCO-A3), alcanza con M = 4.
- **Escrituras:** con S chica (0.2 px/paso) la sonda duplica más veces y llega a 11 escrituras. Con S guardada bastan 2-3.
- **Duración** (DERIVADO): ~40-80 llegadas, cada una de 2 movimientos y 5 cuadros. Con exposiciones de 0.1-0.5 s son ~2-5 min por red. Se mide en el banco.

**Límites de la simulación.**
- La verdad es gaussiana: no hay alas lorentzianas ni el perfil real de la ranura.
- S es lineal y no hay deriva.
- La histéresis no se simuló. El acercamiento desde abajo la neutraliza, pero eso no se validó.

---

## 3. Incertidumbre (GUM)

### 3.1 Tres mensurandos distintos

Hay que separar tres magnitudes, porque las mezclan tanto el código actual como la costumbre:

| Mensurando | Qué es | Para qué sirve |
|---|---|---|
| **(A) c_sw**, la corrección de calibración en el píxel de la línea | Cuánto hay que correr el eje del SDK para que la fuga del láser caiga en λ_L | Es lo que produce la rutina |
| **(B) El eje de un espectro futuro** en ese λc | Lo que hereda una medida tomada después con esa calibración | Es lo que le importa al usuario |
| **(C) La exactitud absoluta** del eje | La relación del eje con el SI | Sin una lámpara depende por completo de λ_L |

Las tres son **relativas a la línea del láser**, salvo los términos de λ_L en (C).

### 3.2 Presupuesto de (A): la corrección c_sw, en píxeles

El modelo es c_sw = −r̄_ver, con r̄_ver la media de M_final llegadas (§2.3).

| # | Fuente | Tipo | Distribución | Valor | c_i | u_i·c_i (px) | Rótulo |
|---|---|---|---|---|---|---|---|
| 1 | Ruido del estimador (fotones, lectura), por llegada | A | normal | 0.09 px con SNR 20 y FWHM 6 px; se mide en cada calibración con u_A | 1/√M | 0.03 (M = 9) | SIMULADO para planificar; se mide |
| 2 | Repetibilidad de la torreta, por llegada | A | normal | s_rep medida con M llegadas. Para planificar, 0.87 px: 10 pm / 0.01152 nm/px con la red de 1200 | 1/√M | **0.29 (M = 9)** | planificación: DERIVADO de [DS-SR500] p. 13, n. 20 para la red de 1200, INFERENCIA para la de 150; se mide |
| 3 | Sesgo del estimador (fase subpíxel, ventana, fondo) | B | rectangular, a = 0.02 px | 0.02 px | 1 | 0.012 | SIMULADO |
| 4 | Cuantización del offset | B | rectangular, a = \|S\|/2 | **0 si se aplica c_sw**; si no, \|S\|/√12 | 1 | 0 / \|S\|/√12 | DERIVADO. S: SIN VALOR |
| 5 | Asimetría de la fuga: ponderación por la transmisión del notch, láser multimodo resuelto, coma | B | — | **SIN VALOR.** Se mide con fuga por notch contra atenuación neutra (P3) y con el diagnóstico gauss − centroide | 1 | — | bloquea U |
| 6 | Deriva térmica del espectrógrafo durante la calibración | B | — | **SIN VALOR** (BANCO-A5). La rutina la controla con la última llegada | 1 | — | bloquea U |
| 7 | Deriva de λ del láser durante la calibración | B | — | **SIN VALOR**. Depende del tipo de láser (P1) | 1/D | — | bloquea U |
| 8 | Interpolación del eje del SDK | B | — | < 0.001 px: el eje es suave | 1 | ≈ 0 | DERIVADO |

**Combinación parcial**, sólo con los términos que tienen valor:

  u_c,parcial = √(0.03² + 0.29² + 0.012²) ≈ **0.29 px**

- Equivale a ≈ 0.030 nm con la red de 150 y ≈ 0.0034 nm con la de 1200.
- **Término dominante: la repetibilidad de la torreta (#2)**, que aporta el 98 % de la varianza. El estimador, el tema de la mayor parte de esta sección, pesa poco una vez que el SNR es ≥ 20.
- **Grados de libertad:** #2 domina con ν = M − 1 = 8, así que ν_eff ≈ 8 (Welch-Satterthwaite) y **k = t₀.₉₇₅(8) = 2.31, no 2** ([GUM] §6.3 y anexo G).
- La cota inferior de U sería ≈ 0.67 px. **No se declara U** mientras #5, #6 y #7 no tengan valor.

**Consecuencia para el número de llegadas.** Sea u_objetivo la incertidumbre estándar máxima que se le pide a c_sw. Para que U = k·u(c_sw) cumpla el criterio provisorio de 0.5 px con la red de 150 hace falta u_objetivo ≤ 0.5/2.3 ≈ 0.22 px.
- Si la torreta es como dice la hoja de datos, M ≈ (0.88/0.22)² ≈ 16 llegadas.
- Con la red de 1200 y 1 px de criterio (u_objetivo ≤ 1/2.31 ≈ 0.43 px), alcanza con M ≥ 5.
- **Propuesta:** M_final **secuencial**. La rutina agrega llegadas de a una, desde 9, hasta que u_A ≤ u_objetivo o M = M_max = 25.

### 3.3 Presupuesto de (B): el eje de un espectro medido después, en el mismo λc

| # | Fuente | Tipo | u (px) | Rótulo |
|---|---|---|---|---|
| (A) | Corrección de calibración | — | ≈ 0.29, parcial | §3.2 |
| 9 | Posicionamiento de **esa** llegada, que es una sola | A (de la calibración) | **s_rep ≈ 0.87** | igual que #2 |
| 10 | Deriva desde la calibración: térmica, días | B | SIN VALOR (BANCO-A5) | bloquea |
| 11 | Ancho de ranura distinto del de la calibración | B | ≈ 0 con una ranura bilateral [R4-A.8, EXPERIMENTAL]; SIN VALOR hasta BANCO-A4 | bloquea si cambia el ancho |
| 12 | Posición de la fuente dentro de la ranura (reflexión del láser contra una NP o Raman) | B | SIN VALOR [R1-E §6.2] | bloquea |

Parcial: √(0.29² + 0.87²) ≈ **0.92 px** por espectro:
- con la red de 150: ≈ 0.094 nm;
- con la red de 1200: ≈ 0.0106 nm, que a 547 nm son ≈ 0.35 cm⁻¹. DERIVADO: 0.0106 nm / (547.2 nm)² × 10⁷.

**Lo que domina un espectro es el posicionamiento de esa adquisición, no la calibración.** Por eso, pedir que la calibración quede por debajo de ~0.3 px no mejora ningún espectro individual.

La mejora real viene de otro lado: registrar la línea del láser **en el mismo cuadro o en la misma llegada** que la medida, por ejemplo la fuga del notch en el Raman con la red de 150, o la fuga en el borde de la ventana. Eso elimina el término #9 en esa medida. Es una recomendación para el Raman (INFERENCIA).

### 3.4 (C) Qué exactitud absoluta se puede esperar sin lámpara de calibración

**Respuesta corta: sin lámpara, la exactitud absoluta del eje es la de λ_L, y hoy λ_L no tiene valor (SIN VALOR).** La rutina deja el eje coherente con la fuga del láser. Esa parte es relativa y es la de §3.2-3.3. La parte absoluta no la puede mejorar ningún algoritmo.

| # | Fuente | Tipo | Valor | c_i | Efecto en px (150 / 1200) | Rótulo |
|---|---|---|---|---|---|---|
| 13 | λ del láser: valor nominal "532 nm" | B | **SIN VALOR.** Ver abajo | 1/D | con u(λ_L) = 0.1 nm, **0.97 / 8.7 px** | — |
| 14 | Convención aire / vacío | sistemático, no es una incertidumbre | (n_aire − 1)·λ ≈ 2.8·10⁻⁴ × 532 ≈ 0.15 nm | 1/D | **1.4 / 13 px** si se confunde | DERIVADO (índice de aire estándar, valor de libro; coincide con [R1-E] §2.6) |
| 15 | Deriva de λ_L con la temperatura | B | diodo directo verde: ~0.07 nm/K; DPSS con línea fijada por la transición del Nd: mucho menor | 1/D | diodo: **0.7 / 6 px por K** | diodo: fuente web, orden de magnitud (abajo); DPSS: INFERENCIA |
| 16 | Eje del SDK lejos del píxel de calibración | B | 0.04 nm de exactitud con la red de 1200 (promedio de > 30 líneas en el rango de uso) | 1/D | — / 3.5 px | RESPALDADO [DS-SR500] p. 13, n. 19; para la de 150 no hay dato; se mide con el recorrido |

**Qué dice la fuente sobre λ_L:**
- **Si el láser es el Excelsior-532-150-CDRH** (registro BANCO-22), la hoja de datos de Spectra-Physics da:
  - "532 nm" **sin tolerancia**;
  - un ancho de línea **< 0.5 nm** en la versión multimodo, y < 10 MHz con una deriva < 50 MHz/°C en la monomodo (de 200 y 300 mW);
  - el Excelsior de 532 nm es **DPSS**; las versiones de diodo directo de la familia son las de 375-515 nm y otras.
  - Fuente web: [Excelsior Series Datasheet](https://www.spectra-physics.com/medias/sys_master/resources/h92/h21/9954705866782/Excelsior-Series-Datasheet-/Excelsior-Series-Datasheet-.pdf), tablas de especificaciones.
  - Que el de 150 mW sea multimodo es una INFERENCIA, por las potencias de la monomodo.
- **Un ancho < 0.5 nm equivale a ~5 px con la red de 150 y a ~43 px con la de 1200.** Con la red de 1200, la estructura de modos se resolvería. El "centro" pasa a ser un centroide de modos que puede saltar con la temperatura. El diagnóstico de ANCHO y ASIMETRÍA (§2.1) existe por esto.
- **Si es un diodo verde directo**, como dice el investigador [R4-A.8]:
  - estos diodos emiten típicamente entre 510 y 530 nm (fuente web: [Laser Focus World, OSRAM 510-530 nm](https://www.laserfocusworld.com/lasers-sources/article/16567028/osram-unveils-direct-emission-green-laser-diodes-emitting-at-wavelengths-from-510-to-530-nm)), así que un "532" directo sería raro (INFERENCIA);
  - la deriva sería del orden de 0.07 nm/K (fuente web, orden de magnitud, tomado del resumen del buscador de un artículo de *Appl. Phys. Lett.* 103, 071102 (2013): https://pubs.aip.org/aip/apl/article-abstract/103/7/071102/150357; no se leyó el texto completo).
  - Con esa deriva, 1 K de cambio en la sala corre la línea 6 px con la red de 1200. La calibración absoluta con la red de 1200 no tendría sentido sin controlar la temperatura del láser.
- **Conclusión:** el tipo de láser (P1) no es un detalle. **Decide si la red de 1200 puede tener una exactitud absoluta mejor que ~1 nm.**

**Qué parte es sólo relativa y por qué igual sirve:**
- **Raman.** Si el mismo λ_L declarado se usa para calibrar y para calcular el corrimiento, un error e en λ_L produce un error de corrimiento de e·(1/λ_L² − 1/λ_s²): **0.37 cm⁻¹ a 1000 cm⁻¹ con e = 0.1 nm** (DERIVADO; recalculado, coincide con [R1-E] §2.6). El Raman tolera un λ_L inexacto si es **coherente**.
- **Excepción que no se cancela: el sesgo de la fuga (#5).** Si el notch pondera la fuga y corre su centro b respecto de la línea verdadera del láser, el eje queda corrido b. El corrimiento Raman hereda b completo: **≈ 0.38 cm⁻¹ por píxel con la red de 1200** (DERIVADO: 0.01152 nm / (547 nm)²). Por eso #5 bloquea la U del Raman y hay que medirlo (P3).
- **Máximo plasmónico con la red de 150.** Un error absoluto de 0.1-0.5 nm es chico frente a anchos de decenas de nm [R1-E §2.6].

**Qué haría falta para tener exactitud absoluta** (fuera del alcance de esta rutina):
- una línea atómica: Hg 546.07 nm en aire de un tubo fluorescente, o una lámpara de neón de indicador [R1-E §2.4 b; NIST];
- o λ_L medida con un medidor de longitud de onda.

Con la red de 150, la línea del Hg de 546.07 nm entra **en el mismo cuadro** que el 532, a ≈ 137 px. Con eso se mediría λ_L relativa a un patrón atómico (pregunta P2).

### 3.5 Hallazgos sobre el código existente de incertidumbre (no se corrigen en esta ronda)

**H1.** `core/sif_processor.py::fit_peak_advanced` (l. 1297-1462) le suma al centro ajustado dos términos:
- `u_slit = (ancho_ranura/pitch)·D/√12`;
- `u_pixel = D/√12`.

Hay dos problemas:
- **Doble cómputo del pixelado:** el pixelado ya está dentro del ajuste (L5-202-06).
- **`u_slit` no es una incertidumbre del centro.** Con una ranura bilateral el centro de la imagen no se mueve con el ancho; el ancho cambia el FWHM, no el centro. Con 100 µm, `u_slit` vale 12.5·D/√12 ≈ **3.6 px**, así que dominaría cualquier presupuesto con un término que no existe.

Para la calibración **no se usa** `u_peak_center_combined`.

**H2.** `compute_wavelength_uncertainty` (l. 457-486) tiene el mismo problema y, además, usa `calib_uncertainty_nm = 0.08` por defecto, **sin fuente** (SIN FUENTE).

**H3.** `filter_despike_median` destruye la precisión de una línea angosta (§2.4 C). No debe estar en la cadena de la calibración, y conviene revisar si se usa sobre espectros Raman.

**H4.** `CalibrationBackend._fit_gaussian_slit` (`calibration_dock.py:829-854`) no sirve para reutilizar:
- ajusta los 1004 px, sin ventana;
- cuando falla, devuelve un centroide con FWHM = 10 fijo;
- `auto_calibrate_slit` ajusta un perfil plano sintético cuando no hay imagen (ya informado en la Ronda 1).

**H5.** Queda el modelo **`core/lattice_disorder.py::_gaussian_with_bg`** (l. 134): gaussiana + fondo + pendiente, justo el modelo que se adopta. Se propone compartir la función del modelo y escribir un ajustador nuevo en píxeles con la API de §5.1, en lugar de reutilizar `fit_peak_advanced`, que trabaja en nm y tiene el presupuesto de H1.

---

## 4. Archivo de calibraciones y criterio de aceptación

### 4.1 Qué se guarda por cada calibración

**Formato.** Un registro en el que sólo se agregan entradas (JSON Lines, una línea por calibración): local a la PC del banco, fuera de git, con una plantilla en el repositorio [R4-A.5]. Nunca se sobrescribe una entrada. Una calibración rechazada **también se guarda**, con su veredicto.

| Grupo | Campo | Unidad / tipo | Por qué |
|---|---|---|---|
| **Identidad** | `record_id` (UUID), `timestamp_utc` y `timestamp_local`, `operator` | — | trazabilidad |
| | `method` = `"auto_offset_laser_leak_v1"`, `software_version` (hash de git + versión de PySpectrum), `estimator` = `"gauss+linear, window 3 FWHM, recentred"` | — | una calibración sólo se compara con otra del mismo método y estimador |
| | `dry_run` (bool), `verdict` (`ACEPTADA`, `RECHAZADA` o `EN_SECO`) con sus razones | — | — |
| **Equipo** | `shamrock_serial`, `camera_serial`, `camera_head` (`DU8285_VP`) | — | el archivo se indexa por número de serie |
| | `grating_index`, `grating_lines_per_mm`, `grating_blaze_nm` (de `GetGratingInfo`), `input_port`, `output_port` | — | la calibración vale para esa red y esos puertos |
| | `declared_geometry` = {`n_px`: 1004, `pixel_width_um`: 8.0}, **releída** | — | si cambia la geometría, la calibración deja de valer [R1-E §6.8] |
| **Óptica** | `slit_width_um` (leído), `filters` (notch dentro / fuera, ND), `roi_rows` [inicio, fin], `detection_mirror_state` (y de dónde sale ese estado: software, C-08) | — | #11 y #12 |
| **Referencia** | `lambda_ref_nm`, `lambda_ref_medium` = `"air"` (obligatorio), `lambda_ref_source` (texto: etiqueta, hoja de datos, medido con…), `u_lambda_ref_nm` (**null** si no hay dato), `laser_model`, `laser_type` (`DPSS` / `diodo` / `desconocido`) | nm | #13-#15: sin esto no se puede reinterpretar la calibración después |
| **Detector** | `ccd_temperature_c` y su estado (estabilizada), `em_gain` (releída, 0), `exposure_s`, `readout_rate`, `preamp`, `vs_speed`, `adc_bits` = 14, `n_frames_per_arrival`, `n_dark_frames`, `dark_mean_counts` | — | condiciones del ruido y de la linealidad |
| **Ambiente** | `room_temperature_c` (**null** si no hay termómetro), `minutes_since_power_on` | — | #6 y #10 |
| **Offsets** | `detector_offset_read` (no se escribe), `grating_offset_before` (leído), `grating_offset_after` (releído), `offsets_tried` [{`O`, `r_mean_px`, `u_A_px`, `M`}] | pasos, px | respaldo e historial del lazo |
| **Sensibilidad** | `S_px_per_step`, `u_S`, `S_source` (`sondeada` / `previa`, con fecha), `offset_mechanism` (`motor` o `axis`, §1.2) | px/paso | se reutiliza en la próxima calibración |
| **Resultado** | `lambda_c_nm` (ordenado y leído), `x_hat_px`, `u_noise_px`, `fwhm_px`, `snr`, `chi2_red`, `asymmetry_px`, `flags` | — | — |
| | `r_hw_px` (residuo medio en O_after), `u_r_hw_px`, `M_final`, `nu`, `s_rep_px` | px | — |
| | `c_sw_px` = −`r_hw_px`, `u_c_sw_px`, `c_sw_convention` = `"lambda(p) = lambda_SDK(p + c_sw)"` | px | la corrección de software y su convenio de signo |
| | `D_nm_per_px` local y la corrección en nm, c_sw·D | nm | — |
| | `drift_check_px` (última llegada − media) | px | — |
| **Recorrido** | por cada λc: {`lambda_c_nm`, `x_hat_px`, `residual_px` con c_sw aplicado, `u_px`, `M`} y `dispersion_sign_ok` | — | validez lejos del píxel de calibración |
| **Presupuesto** | la tabla de §3.2 con valor **o `null`** por término, `u_c_partial_px`, `nu_eff`, `k`, `U_px` (**null mientras haya términos null**) | — | nunca un número inventado |
| **Datos crudos** | ruta y hash del HDF5 con los cuadros, el oscuro, los ejes por llegada y los perfiles | — | para poder recalcular con otro estimador |

### 4.2 Criterio de aceptación (**PROVISORIO**, fase exploratoria [R4-A.9])

Los umbrales vienen de [R1-E] §2.3, aceptados como provisorios por el investigador. Esta sección los lleva a magnitudes que se pueden verificar.

| # | Criterio | Red de 150 | Red de 1200 | Justificación |
|---|---|---|---|---|
| K1 | Incertidumbre estándar de la corrección, u(c_sw) (M secuencial, §3.2) | ≤ 0.22 px | ≤ 0.43 px | Da U = 2.3·u ≤ 0.5 px (≈ 0.05 nm) y ≤ 1 px (≈ 0.012 nm), que son los provisorios de R4-A.9. Con la red de 150, 0.05 nm es del orden de la exactitud de la hoja de datos (0.04 nm); con la de 1200, 1 px es del orden de la repetibilidad (0.87 px). Pedir más no es verificable por espectro (§3.3) |
| K2 | Sólo hardware (si el investigador elige no usar la corrección de software, P4): \|r_hw\| | ≤ max(0.5 px, \|S\|/2 + 2·u) | ≤ max(1 px, \|S\|/2 + 2·u) | Con \|S\| > 1 px/paso, el 0.5 px no se alcanza con un entero (§1.5). El criterio lo reconoce en lugar de iterar sin fin |
| K3 | Repetibilidad s_rep | ≤ 1 px | ≤ 1 px | [R1-E] §2.3. Si da más, la torreta está peor que la hoja de datos: se avisa y se para |
| K4 | Recorrido de la línea, con la corrección aplicada | \|r\| ≤ 1 px en el centro, ≤ 2 px en ±0.35 W | ≤ 1 px en el centro, ≤ 3.5 px en ±0.35 W | [R1-E] §2.3. 3.5 px con la red de 1200 es la exactitud de la hoja de datos (0.04 nm) |
| K5 | Signo de la dispersión | igual al del eje del SDK | ídem | detecta un eje invertido [R1-E §6.9] |
| K6 | Calidad de la línea | SNR ≥ 20, sin saturación, sin banderas ASIMETRÍA ni ANCHO ni BORDE, χ²_red en [0.5, 2] | ídem | §2.1 |
| K7 | Deriva durante la calibración | \|drift_check\| ≤ 3·s_rep | ídem | control interno. El umbral fijo en px/h sale de BANCO-A5 |

**Resultados posibles:**
- **ACEPTADA:** se cumplen todos los criterios.
- **RECHAZADA:** falla cualquiera. El offset se restaura al valor anterior; se pregunta al operador, con los números a la vista.
- **ACEPTADA_CON_RESERVA:** K1-K7 dan bien, pero el presupuesto tiene términos sin valor. En la fase exploratoria **toda** calibración va a quedar así hasta que se midan #5-#7. El rótulo lo dice explícitamente, en lugar de dar un "validado" que no existe.

---

## 5. Inventario de parámetros y estrategia de tests

### 5.1 Firmas propuestas (sólo contrato; sin código de producción)

**Ubicación.** Módulo puro, sin Qt ni hardware, por ejemplo `core/spectral_line_fit.py`. El lazo va en `pyspectrum/calibration/offset_calibration.py` y habla con el hardware a través de un **puerto inyectado**. La topología de hilos y la interfaz de ese puerto son de `software-architect` e `instrumentation`.

```python
@dataclass(frozen=True)
class LineCenterResult:
    success: bool
    center_px: float            # índice 0-based de columna
    u_center_px: float          # max(u_cov escalada por χ²_red, u_A entre cuadros)
    u_center_cov_px: float
    u_center_typeA_px: float | None
    fwhm_px: float
    amplitude_counts: float
    background_counts: float    # en center_px
    background_slope_counts_per_px: float
    snr: float                  # amplitud / σ del fondo (ruido de las alas del ajuste)
    chi2_red: float
    centroid_px: float          # diagnóstico
    asymmetry_px: float         # center_px - centroid_px
    window_px: tuple[int, int]
    flags: tuple[str, ...]      # "LOW_SNR","SATURATED","ASYMMETRIC","WIDE","EDGE","FIT_FAILED","NO_LINE"

def estimate_line_center(
    profile_counts: np.ndarray,             # 1D, float64, fondo oscuro ya restado
    *,
    center_guess_px: float | None = None,   # None → búsqueda gruesa con pasa-altos
    search_range_px: tuple[int, int] | None = None,
    fwhm_guess_px: float | None = None,     # None → segundo momento
    window_fwhm: float = 3.0,
    background: Literal["linear", "constant"] = "linear",
    edge_trim_px: int = 15,
    min_snr_detect: float = 8.0,
    reference_fwhm_px: float | None = None, # para la bandera WIDE (umbral 1.5×)
    per_frame_profiles: np.ndarray | None = None,  # (K, n_px) → u de Tipo A
) -> LineCenterResult: ...

def reject_cosmic_rays_temporal(
    frames_counts: np.ndarray,              # (K, n_rows, n_px) o (K, n_px); K ≥ 3
    *,
    n_sigma: float = 5.0,
    noise_floor_counts: float | None = None # σ mínima (lectura); None → MAD global
) -> tuple[np.ndarray, np.ndarray]:         # (media recortada, máscara de rechazos)

def check_saturation(
    raw_frames_counts: np.ndarray, *, adc_max_counts: int, max_fraction: float = 0.8
) -> bool: ...                               # adc_max_counts viene del símbolo de C-25 (16383)

def calibration_residual_px(
    center_px: float, axis_nm: np.ndarray, lambda_ref_nm: float
) -> tuple[float, float]:                    # (r_px, D_nm_per_px local); eje ascendente o descendente;
                                             # ValueError si no es monótono o λ_ref queda fuera

def combine_arrivals(residuals_px: Sequence[float]) -> tuple[float, float, int, float]:
    # (media, u_A = s/√M, ν = M − 1, s_rep)

def estimate_sensitivity(r0_px: float, u0_px: float, r1_px: float, u1_px: float,
                         delta_steps: int) -> tuple[float, float]:   # (S px/paso, u_S)

@dataclass(frozen=True)
class OffsetDecision:
    proposed_offset: int
    step: int
    reason: Literal["update", "converged", "cycle", "clipped", "limit_exceeded"]

def plan_offset_update(
    r_px: float, s_px_per_step: float, current_offset: int, original_offset: int,
    tried_offsets: Collection[int], *, max_step: int = 64, max_total_change: int = 200
) -> OffsetDecision: ...                     # función pura: toda la lógica de decisión se testea sin hardware

@dataclass(frozen=True)
class OffsetCalibrationConfig:
    grating: int                              # 1 o 2; el 3 (espejo) se rechaza
    lambda_ref_nm: float                      # en aire
    lambda_ref_source: str
    u_lambda_ref_nm: float | None = None
    lambda_c_nm: float | None = None          # None → lambda_ref_nm
    approach_delta_nm: float | None = None    # None → 20.0 (150) / 3.0 (1200)
    frames_per_arrival: int = 5               # ≥ 3
    dark_frames: int = 5
    arrivals_per_iteration: int = 4
    arrivals_final_min: int = 9
    arrivals_final_max: int = 25
    u_target_px: float | None = None          # None → 0.22 (150) / 0.43 (1200), §4.2 K1
    exposure_s: float | None = None           # None → automática
    exposure_max_s: float = 10.0              # R4-4
    target_peak_fraction: tuple[float, float] = (0.2, 0.5)
    min_snr_calibrate: float = 20.0
    roi_rows: tuple[int, int] | None = None   # None → traza ± 4 filas
    s_prior_px_per_step: float | None = None
    u_s_prior: float | None = None
    probe_initial_steps: int = 4
    probe_max_steps: int = 64
    max_step_per_iter: int = 64
    max_total_change_steps: int = 200
    max_iterations: int = 4
    walk_fractions_of_window: tuple[float, ...] = (-0.35, 0.0, 0.35)
    apply_software_correction: bool = True    # P4
    dry_run: bool = True                      # por defecto no escribe

def run_offset_calibration(port: "SpectrometerCalibrationPort",
                           cfg: OffsetCalibrationConfig,
                           *, stop_event: threading.Event | None = None) -> "CalibrationRecord": ...

def build_budget(record: "CalibrationRecord") -> list["BudgetRow"]:
    # BudgetRow(name, gum_type, distribution, value, sensitivity, contribution_px | None, label)
def expanded_uncertainty(rows: list["BudgetRow"], p: float = 0.95) -> tuple[float, float, float] | None:
    # (u_c, ν_eff por Welch-Satterthwaite, k = t_p(ν_eff)); None si alguna fila tiene valor None

def evaluate_acceptance(record: "CalibrationRecord", criteria: "ProvisionalCriteria") -> tuple[str, list[str]]
```

**Unidades y convenciones que fija el contrato:**
- los píxeles se cuentan desde 0;
- λ en nm, en aire;
- los offsets son enteros, en pasos;
- S en px/paso, con signo;
- las cuentas son del ADC, con el oscuro restado.

**Nada de esto toca el detector ni el offset del detector:** `SpectrometerCalibrationPort` no expone `set_detector_offset`.

### 5.2 Estrategia de tests (pytest, SAFE_MODE, datos sintéticos)

**Generador común.** Una línea gaussiana **integrada en el píxel** con centro conocido, más fondo, más ruido de Poisson y de lectura, con semilla fija. Es el mismo modelo de §2.4.

| ID | Test | Falla si… | Control negativo o de sensibilidad |
|---|---|---|---|
| T1 | **Sesgo del estimador.** Rejilla de fases subpíxel x₀ = 501 + j/20; SNR ∈ {10, 20, 50, 200}; σ ∈ {1.3, 2.5} px; 400 réplicas por punto | \|sesgo medio\| > max(0.02 px, 3·SE) | El mismo test corrido sobre argmax y sobre gauss + constante con fondo inclinado **debe fallar**. Así se prueba que el test detecta sesgo (prueba de mutación) |
| T2 | **Eficiencia.** Desvío estándar ≤ 1.15·CRLB con SNR ≥ 10 | el estimador pierde eficiencia (por ejemplo, un centroide disfrazado) | el centroide debe fallar |
| T3 | **Cobertura de u.** Fracción de \|x̂ − x₀\| ≤ 2·u_center en [0.93, 0.97] con SNR ≥ 20 | u optimista o inflada (por ejemplo, si alguien le suma el `u_slit` de H1) | con `u_slit` sumado debe dar > 0.99 y fallar |
| T4 | **Fondo inclinado.** 2 e⁻/px, SNR 10-50 | \|sesgo\| > 0.02 px | — |
| T5 | **Rayos cósmicos.** 1 rayo de 10⁴ cuentas en 1 de 5 cuadros, a ±3 px de la línea | error > 3 desvíos estándar del caso limpio | sin rechazo (media simple), el error tiene que superar ese umbral |
| T6 | **Línea angosta sin despike espacial.** σ = 1 px, SNR 2000 | desvío estándar > 0.01 px (detecta que se metió `filter_despike_median` en la cadena) | — |
| T7 | **Saturación.** Pico recortado en 16 383 | `success=True` sin la bandera `SATURATED`, o se devuelve un centro | — |
| T8 | **Sin línea.** Ruido puro o perfil plano (incluido `np.ones(1004)*100`, el caso de H4) | devuelve un centro o `success=True` | — |
| T9 | **Residuo y signo.** Ejes sintéticos ascendente y descendente, línea en λ conocida | el signo de r o de c_sw está mal; λ_SDK(x̂ + c_sw) ≠ λ_L en ± 10⁻⁶ nm | — |
| T10 | **Lazo contra un puerto simulado.** S ∈ {+0.2, +0.6, +1.8, −1.0}, σ_rep = 0.87, r₀ ∈ ±30 px; mecanismos (a) y (b) | no converge en el tope de escrituras; \|r_final verdadero\| > \|S\|/2 + 3u; excede `max_total_change` | ver T11 |
| T11 | **Seguridad del lazo** | con `dry_run=True` hay alguna escritura (el puerto cuenta 0); la sonda no restaura O₀; hay alguna llamada al offset del detector; con una relectura distinta no se aborta y se restaura; con Stop no se restaura | — |
| T12 | **Sesgo de selección** | la verificación reutiliza llegadas de la etapa de selección (se comprueba por identidad de las llegadas) | con datos reutilizados, en 4000 réplicas, \|r\| sale sesgado hacia 0: el test lo muestra |
| T13 | **Presupuesto** | `expanded_uncertainty` devuelve un número con alguna fila `None`; k ≠ t(ν_eff); ν_eff mal calculado (caso de prueba a mano) | — |
| T14 | **Esquema del registro** | falta un campo de §4.1; `lambda_ref_medium` ≠ `"air"`; `declared_geometry` ≠ (1004, 8.0) sin bandera | — |

**Controles negativos en el banco** (van a la batería, no a pytest):
- con el obturador de 532 cerrado, la rutina tiene que terminar en `NO_LINE` y no "calibrar ruido";
- con el espejo de detección arriba, lo mismo;
- con la ganancia EM ≠ 0, la rutina no arranca.

**Pruebas de banco nuevas que salen de esta ronda:**
- *Sesgo del notch (#5):* comparar el centro de la fuga por el notch con el de la línea atenuada con filtros neutros, con el notch afuera, la ganancia EM en 0 y la misma exposición relativa. Con las dos redes. Resuelve #5.
- *M secuencial:* con la red de 150, 25 llegadas en el mismo offset, para medir s_rep por red. Resuelve #2 y el M_final.

---

## 6. Preguntas para el investigador (4)

**P1. ¿Qué dice la etiqueta del láser de 532: modelo, tipo (DPSS o diodo directo) y, si figura, λ y ancho de línea? ¿Hay algún valor medido de su λ, sea un certificado o un medidor de λ?**
- *Desbloquea:* λ_L, u(λ_L) y la deriva térmica (#13, #15), que definen si la red de 1200 puede tener exactitud absoluta o sólo relativa.
- *Desbloquea también:* si hay que esperar estructura de modos resuelta con la red de 1200, lo que decide si el estimador de una gaussiana alcanza o hace falta registrar el perfil multimodo.
- *Contexto:* el Excelsior 532 del registro BANCO-22 es DPSS, con un ancho < 0.5 nm en la versión multimodo.

**P2. Aunque no haya lámpara de calibración, ¿hay alguna fuente de Hg o Ne que se pueda acercar a la ranura?** Por ejemplo, un tubo fluorescente del laboratorio, o un indicador de neón, que es barato de conseguir.
- *Desbloquea:* la exactitud absoluta.
- *Cómo:* con la red de 150, la línea del Hg de 546.07 nm (en aire) cae en el mismo cuadro que el 532. Mediría λ_L contra un patrón atómico, sin cambiar la rutina: sólo cambia λ_ref.

**P3. ¿Se puede sacar el notch una vez, con la ganancia EM en 0, y atenuar el 532 con filtros neutros para comparar el centro de la línea con el de la fuga?**
- *Desbloquea:* el término #5, el sesgo de la fuga.
- *Por qué importa:* bloquea la U de las dos redes, y es el único término que **no** se cancela en el corrimiento Raman (≈ 0.38 cm⁻¹ por px con la red de 1200).

**P4. ¿PySpectrum puede aplicar una corrección de software por debajo de un paso (c_sw, en px), sabiendo que Solis y el legado no la van a ver? ¿O la calibración tiene que quedar sólo en el offset entero de la EEPROM, como hoy?**
- *Desbloquea:* si se aplica el criterio K1 (hardware + software) o el K2 (sólo hardware).
- *Por qué importa:* con \|S\| > 1 px/paso, el 0.5 px de la red de 150 es inalcanzable sólo con el hardware.
- *Afecta además:* el contrato del eje en toda la aplicación, porque cada espectro de 3.0 tendría que guardar c_sw en su metadato.

---

## 7. Veredicto

**Veredicto metrológico: `INADEQUATE_ERROR_BUDGET`**, para la calibración tal como está hoy y para la exactitud absoluta.

**El algoritmo no es el problema.** Es trazable en su parte relativa y la simulación lo valida:
- el estimador no tiene sesgo y queda en la CRLB;
- el lazo converge en 2-4 escrituras con S guardada.

**Lo que falta es el presupuesto.** No se puede declarar U mientras no tengan valor:
- λ_L y su deriva (#13, #15);
- el sesgo de la fuga por el notch (#5);
- la deriva térmica (#6, #10).

**Hallazgos principales:**
1. **El mensurando es el residuo** r = x̂ − p_SDK(λ_L), no x̂. Así el algoritmo es independiente de si el offset mueve el motor o sólo recalcula el eje, y la rutina además averigua cuál de los dos pasa.
2. **Lo que domina no es el estimador sino la torreta.** La repetibilidad de 10 pm de la hoja de datos equivale a 0.87 px por llegada; el ruido del centro con SNR 20 es 0.07-0.09 px. Hacen falta ≥ 9-16 llegadas desde abajo y un M secuencial. Un espectro individual hereda ≈ 0.9 px por su propio posicionamiento.
3. **S sólo acelera la convergencia.** El resto se **mide** en una verificación independiente, así que u(S) no entra en el resultado y se evita el sesgo de selección.
4. **Sin lámpara, la exactitud absoluta es la de λ_L, que hoy no tiene valor.** Si el láser fuera un diodo directo, derivaría del orden de 6 px/K con la red de 1200.
5. **El código existente de incertidumbre y de despike no sirve para esto** (H1-H4). `fit_peak_advanced` le suma al centro ≈ 3.6 px inexistentes con una ranura de 100 µm, y `filter_despike_median` degrada 5-30 veces una línea angosta.
