# C-01 Ronda 2 — Panelista de metrología: criterio de detección de impresión en unidades de tiempo

Fecha: 2026-09-27. Árbol: `main` (con el paso 0 de `DEC-037` aplicado en el árbol de trabajo). Referencia de
producción: `7f5d10a`, el commit que corre la PC del banco. Sólo lectura: el único archivo escrito es este.

Marcas: **[CÓDIGO]** leído en la línea citada · **[MEDIDO]** medido (Ronda 1) · **[DERIVADO]** cálculo propio
a partir de lo anterior, reproducible · **[SUPUESTO]** hipótesis de modelo no medida en el banco ·
**[INVESTIGADOR]** respuesta de `RESPUESTAS_INVESTIGADOR.md`, "R3 — C-01".

Estado: COMPLETO (secciones 1-7 y veredicto).

---

## 1. El criterio actual, exacto, desde el código

### 1.1 Qué es un "punto" de la traza

- **[CÓDIGO]** `trace.py:501-502`: `rate = RATE_MULTICHANNEL/100 = 1·10⁴ S/s` por canal y `N = 10`.
  - `trace.py:658-661`: cada tick crea una tarea **finita**, lee 10 muestras y la cierra (paso 0, idéntico a `7f5d10a:trace.py:638`).
  - Cada punto x_j es el promedio de 10 muestras, una ráfaga de ≈ 1 ms.
- **[MEDIDO]** Los ticks llegan cada T ≈ 47.5 ms, no 35 ms (QTimer Coarse, `timer_probe.py`). El ciclo útil es ≈ 1/47 ≈ 2 %.
  - Hay un punto por tick. El eje `timeaxis` es `time.time()` después de leer (`trace.py:699`).
- Un error de lectura se registra como x_j = 0.0 V (`trace.py:692-694`). Un error no da NaN.

### 1.2 El estadístico u(t) = I_new / I_old

**[CÓDIGO]** `trace.py:705-717`, idéntico a `7f5d10a:trace.py:685-697`. Sea n el número de puntos acumulados en el nodo.

- M = `steps_after`. El cableado es Frontend `steps_afterEdit` → `params[9]` → `Backend.steps_after` (`measurements.py:1921`) → `stepsParametersSignal.emit([steps_after, steps_before])` (`:1963`) → `trace.parameters` (`app.py:489-490`, `trace.py:611-614`: `steps_after = steps[0]`).
- M2 = `steps_before`, por el mismo camino (`params[8]`, `steps[1]`).
- La señal se emite en cada `grid_parameters`, es decir, al arrancar una grilla. Por defecto M = M2 = 10 (`config.py:155-156`).

Régimen estacionario, n ≥ M + M2:

$$I_{\text{new}}(n)=\frac1M\sum_{j=n-M}^{n-1}x_j,\qquad I_{\text{old}}(n)=\frac1{M_2}\sum_{j=n-M-M_2}^{n-M-1}x_j,\qquad R(n)=\frac{I_{\text{new}}}{I_{\text{old}}}$$

- Son dos ventanas **contiguas y deslizantes**: la "nueva" son los últimos M puntos y la "vieja" los M2 puntos anteriores.
- I_old **no** es una línea de base fija tomada al abrir el obturador. Es una ventana que avanza, así que un escalón persistente termina entrando en I_old y R vuelve a 1.
- **Los tooltips de la GUI son falsos** (`measurements.py:685, 687`):
  - "Steps before" no son "muestras adquiridas antes de abrir el obturador".
  - "Steps after" no son "muestras adicionales tras cerrarlo".
  - Son las dos ventanas de R, contadas en ticks.

Arranque del nodo, n < M + M2 (≈ 0.95 s a 47.5 ms):

| n | I_new | I_old | Efecto |
|---|---|---|---|
| n < min(M, M2) | media de todo | media de todo | R ≡ 1: ciego |
| n = M | media de x_0…x_{M−1} | `mean(x[0:0])` = **NaN** | toda comparación es falsa: ciego |
| M < n < M + M2 | últimos M | media de x_0…x_{n−M−1} (ventana creciente) | la base son los **primeros** puntos, justo los del transitorio de apertura del obturador |

- **[DERIVADO]** Si el obturador (casero, tiempo de apertura no medido: "R3 — C-01") todavía no está del todo abierto en los primeros puntos, I_old sale baja y R sale alta. Eso produce un **"success" espurio alrededor de n ≈ M + N_hold (≈ 0.6 s)**.
  - La traza arranca unos 57 ms después de la orden de apertura: `sleep(0.01)` en `measurements.py:2319` más el primer tick.
  - Que el investigador vea capturas entre 1 y 20 s sugiere que esto no pasa a menudo. No está verificado (pregunta 5).

### 1.3 Decisión por tick (modos legacy = 0 y "umbral + valor absoluto" = 1)

**[CÓDIGO]** `measurements.py:2358-2418`, idéntico a `7f5d10a:measurements.py:2111-2160`. En `7f5d10a` el Modo 0 se rotula "Legacy" y el Modo 1 "Salto Relativo + Umbral Absoluto (V) & Anti-Paso". El preset del investigador es el Modo 1.

1. c_rel = (I_old > 0) ∧ (I_new > u·I_old), con u = `umbral` (1.5 en uso). La desigualdad es **estricta**: R = u no dispara.
2. c_abs = I_new > V_abs, con V_abs = `umbral_abs_v` (default de la GUI 2.5 V; valor en uso **desconocido**, pregunta 1).
3. Condición del Modo 1: c = c_rel **∨** c_abs.
   - El umbral absoluto es un **O**, no un Y: hace la parada más fácil, no más estricta.
   - El "Y" es el "Umbral Mín (V)" (`slope_min`, `:2388, :2402`): si es > 0 y I_new < slope_min, no se para. La GUI lo inicia en 0.000, así que está inactivo salvo que el preset lo fije.
4. Anti-paso (sólo en los modos ≠ 0, `:2395-2399`):
   - `hold_counter` suma 1 en cada tick con c verdadera y vuelve a 0 en cuanto c es falsa.
   - Se para cuando `hold_counter ≥ N_hold`.
   - **N_hold = 3 significa 3 evaluaciones consecutivas verdaderas.** Entre la primera y la última pasan (N_hold − 1)·T ≈ 95 ms.
   - En el Modo 0 se para en el primer tick verdadero.
5. Parada de cualquier modo (`:2408`): should_stop ∨ (I_new < d·I_old) ∨ (t > T_max).
   - Con d = `umbral_down` = 0.5 y T_max = 40 s.
   - **"success" sólo si should_stop.** La rama de caída y la de T_max se rotulan **"timeout"**.
   - d = 0.5 **no está inactivo**: una caída de R por debajo de 0.5 cierra el obturador y rotula "timeout". Hoy no dispara porque el escalón sube.
6. T_max se mide con reloj de pared desde `timer_inicio` (`:2320, :2346`). Es la única magnitud del criterio que ya está en segundos.

Consecuencia que cruza las secciones siguientes: con **Healing Pass** activo, todo nodo "timeout" se reimprime con T_max + 10 s (`measurements.py:2826-2860`).
- Una captura real rotulada "timeout" se vuelve a exponer 50 s.
- Esa captura puede ser un escalón que el criterio no alcanza (§2.3) o una captura con contraste negativo que cae por la rama d (§5).
- El resultado es una segunda NP o daño.

---

## 2. Reexpresión en ms que conserva el comportamiento de los presets

### 2.1 Modelo determinista en tiempo continuo [DERIVADO]

Nivel b antes del escalón y r·b después, en t_s. Las ventanas son W_new, W_old (ms), el umbral u y la persistencia τ_hold: la condición tiene que estar verdadera sin interrupción durante τ_hold.

- **Primer cruce.** Con I_old todavía limpia, R(t) = 1 + (r−1)·min(t − t_s, W_new)/W_new. R cruza u en

  $$t_c = W_{\text{new}}\,\frac{u-1}{r-1}\qquad(\text{exige } r>u).$$

- **Duración de la condición verdadera** cuando I_old sigue viva (el escalón termina entrando en I_old):

  $$D_{\text{true}} = \Big(W_{\text{new}} + \frac{W_{\text{old}}}{u}\Big)\frac{r-u}{r-1}.$$

- **Se detecta** si D_true ≥ τ_hold. Eso da el escalón mínimo detectable, con A = W_new + W_old/u:

  $$r_{\min} = \frac{uA-\tau_{\text{hold}}}{A-\tau_{\text{hold}}}.$$

- **Latencia del criterio:** L = t_c + τ_hold + δ_q + t_proc.
  - δ_q ~ U(0, T_eval) es la fase del escalón respecto de la evaluación.
  - t_proc es el procesamiento, la escritura DO y la mecánica del obturador (aparte).
- **Transitorio** de duración D y razón r_p, como una NP de paso o un atrapamiento momentáneo. Se lo toma por captura si:
  - D > c_p = W_new(u−1)/(r_p−1), y
  - R se mantiene por encima de u durante ≥ τ_hold. Aproximación: D + W_new − 2c_p ≥ τ_hold, para D < W_new.
  - Si r_p ≤ u, **nunca** se lo toma por captura, dure lo que dure.
- **Cota causal:** un criterio que decide con latencia L no puede separar un escalón de un transitorio de igual amplitud que dure más que L. Hasta el instante de la decisión, los datos son idénticos.
  - Rechazar atrapamientos transitorios de duración D cuesta una latencia ≥ D.
  - **Ninguna elección de ventanas escapa a esto** (se usa en §3-§4).

### 2.2 Las ventanas de hoy, en ms

**[MEDIDO]** El Coarse de 35 ms da T = 47.05 ms de media en la PC de desarrollo. La cadencia en la PC del banco **no está medida** (`BANCO-2x`, M2 de instrumentación R1).

| Parámetro | Ticks en uso [INVESTIGADOR] | ms a 47 ms (3.0, banco) | ms a ≈ 10 ms (legado `start(0)`) | Lectura |
|---|---|---|---|---|
| M = `steps_after` (ventana de I_new) | 10 (default; confirmar, pregunta 2) | **470 ms** | 100 ms | promedio de 10 ráfagas de 1 ms repartidas en 470 ms (ciclo útil 2 %) |
| M2 = `steps_before` (ventana de I_old) | 10 | **470 ms** | 100 ms | ídem |
| N_hold | 3 | **94 ms de persistencia** (N_hold − 1)·T; 141 ms de cobertura N_hold·T | 20 / 30 ms | lo que suma a la latencia y filtra transitorios es la **persistencia**, (N_hold − 1)·T |
| u | 1.5 | — (adimensional) | — | la desigualdad es estricta |
| d = `umbral_down` | 0.5 | — | — | activo: rotula "timeout" |
| T_max | 40 s | 40 s | 40 s | ya estaba en segundos |

- Los presets del repo (`presets/*.txt`, N_hold = 5) equivalen a 188 ms de persistencia a 47 ms.
- **No son el preset del banco**: ninguno tiene u = 1.5, N_hold = 3 ni T_max = 40 s. El preset real está en la PC del banco (pregunta 1).

### 2.3 Qué hace hoy el preset del investigador (Modo 1, u = 1.5, N_hold = 3, M = M2 = 10 ticks)

- **[DERIVADO]** Fórmula de §2.1 con W = 470 ms y τ_hold = 94 ms: **r_min ≈ 1.57**.
- **[DERIVADO, simulado]** Script `c01_criterion_sim.py` (scratchpad de la sesión; se puede copiar a `c01_ronda2/`):
  - ticks N(47.05, 2.5) ms recortados a [31, 63] (la distribución medida en R1);
  - ráfagas de 1 ms, σ = 2 % por ráfaga, escalón en fase aleatoria;
  - 300-600 ensayos por punto.

| r (escalón) | 1.40 | 1.50 | 1.55 | 1.60 | 1.80 | 2.00 |
|---|---|---|---|---|---|---|
| P_det por la rama relativa | **0** | **0** | **0.00** | **0.79** | 1.00 | 1.00 |
| latencia mediana / p95 del criterio (ms) | — | — | — | 491 / 522 | 400 / 424 | 329 / 372 |

- **Consecuencia 1: una parte del rango físico nunca se detecta.** Con el preset en uso, los escalones de ×1.4 a ≈ ×1.57 (la parte baja del rango ×1.4-2 que informa el operador) **no los detecta nunca la rama relativa**.
  - Sólo los puede atrapar c_abs (V_abs desconocido).
  - Si c_abs tampoco los atrapa, el nodo queda con el láser abierto hasta T_max = 40 s y se rotula "timeout".
  - **Hipótesis que hay que descartar:** que parte de los TIMEOUT "esperables" sean capturas reales no detectadas y no la estadística de captura. Con Healing Pass activo, esos nodos se reexponen 50 s (§1.3).
  - Se contrasta con las preguntas 3-4 y con el test T-5 (§6).
- **Consecuencia 2: la detección depende de la fase en el borde.** Entre r = 1.55 y 1.62, detectar o no depende de la fase del escalón respecto de los ticks y del jitter del QTimer. Es azar de la cadencia, no del ruido: con σ = 2 %, σ_R ≈ 0.9 % (§3).
- **Consecuencia 3: ruido y latencia.** La ventana de 470 ms no hace falta contra el ruido (§3). Es un **filtro de transitorios**:
  - un transitorio de r_p = 2 se toma por captura sólo si dura ≳ 240 ms (simulado: P_FP = 0.11 a 200 ms y 1.00 a 300 ms; §3.3);
  - lo mismo fija una latencia de 330-500 ms, 7-10 veces el objetivo.

### 2.4 Propuesta P0: preset heredado reexpresado en ms, equivalente a hoy

**Regla de conversión** para cualquier preset guardado en ticks, con T_ref = la cadencia con la que se ajustó el preset:
- W_new = `steps_after`·T_ref;
- W_old = `steps_before`·T_ref;
- τ_hold = (N_hold − 1)·T_ref.

T_ref vale 47 ms para los presets de 3.0 y ≈ 10 ms para los que vienen del legado. **El preset migrado tiene que guardar T_ref** (p. ej. `t_ref_ms = 47`) y la migración tiene que ser explícita, nunca silenciosa. Hay que medir T_ref en la PC del banco antes de migrar.

**P0 para el preset del investigador:**

| Parámetro | Valor |
|---|---|
| W_new | 470 ms |
| W_old | 470 ms |
| τ_hold | 90 ms (múltiplo del bloque de 10 ms más cercano a 94) |
| u | 1.5 |
| I_old | viva (no se congela), como hoy |
| Evaluación | al final de cada bloque de 10 ms |
| Rama de caída d = 0.5 y T_max = 40 s | sin cambios |

- Con bloques de 10 ms, W = 470 ms deja pasar 1.4 % de la amplitud de 50 Hz (|sinc(π·50·0.47)| = 1/(23.5π)). Es despreciable, así que no hace falta forzar múltiplos de 20 ms en ventanas tan largas.
- **Simulado** (`c01_criterion_sim2.py`, 470 / 470 / 90 ms, σ = 2 %, 400-600 ensayos). Latencia mediana / p95 del criterio:

  | r | P0 | Hoy |
  |---|---|---|
  | 1.6 | P = 1.00; 487 / 492 ms | 491 / 522 ms (P = 0.79) |
  | 1.8 | 389 / 394 ms | 400 / 424 ms |
  | 2.0 | 330 / 335 ms | 329 / 372 ms |
  | ≤ 1.56 | P = 0 | P = 0 |

  - **La mediana coincide con la de hoy dentro de ≈ 10 ms.**
  - Cambian dos cosas, y las dos son mejoras. Primera: el p95 baja, porque ya no hay jitter del QTimer. Segunda: el borde de detección queda nítido, P_det(1.57) ≈ 0.6 y P_det(1.58) = 1, y ya no depende de la fase ni del jitter. Hoy el borde va de P = 0.17 a 0.96 entre r = 1.57 y 1.62 (§6, T-3).
- **Para qué sirve P0:**
  1. Es el **control de paridad**: la opción E con P0 tiene que dar en el banco la misma tasa de SUCCESS y los mismos t_print que `7f5d10a` (criterio B de devil-advocate R1).
  2. Es el preset de respaldo "como hoy".
- **No** cumple el objetivo de latencia y **hereda el hueco r ∈ [1.4, 1.57]**.

---

## 3. Promediar bloques de 10-20 ms: ruido, falsos positivos y falsos negativos

### 3.1 Modelo de ruido [SUPUESTO, declarado]

- **Interpretación de "ruido 1-2 %".** Se toma como **rms relativo por ráfaga de 1 ms**, σ_1ms = 1-2 % de la base.
  - Es la lectura **conservadora**.
  - La cifra de R1 (experimentalist §2) es "1-2 % **p-p**" leída de Martínez Fig. 3.9. Si es p-p gaussiano, el rms es ≈ p-p/5 ≈ 0.2-0.4 %, y todos los márgenes de abajo son unas 5 veces mayores.
- **Componente blanca.** Independiente entre muestras a 10 kS/s. Sólo vale si el ancho de banda del PDA es ≳ 5 kHz, y el modelo y la ganancia del PDA están pendientes de banco (grupo F).
  - Si el ancho de banda B es menor, el número efectivo de muestras independientes en un bloque de duración T es ≈ 2BT, no f·T.
- **Componente correlacionada** (intensidad del láser, vibración axial convertida en fase por el iSCAT, 1/f). Se modela como Ornstein-Uhlenbeck con τ_c = 100 ms y σ_c de 2 % y 5 % (prueba de estrés).
  - Promediar no la reduce.
  - La mitiga la **normalización por el BS** (ai6), que cancela el ruido de intensidad del láser común a los dos caminos (experimentalist R1 §1). No mitiga la vibración.

### 3.2 Ruido del estadístico R, en reposo (sin evento)

Para ruido blanco, σ_R = σ_1ms·√(1/n_new + 1/n_old), con n_new y n_old el número de ms independientes en cada ventana. Hoy n = M ráfagas; en continuo, n = W/1 ms.

| Criterio | Ventanas | σ_R con σ_1ms = 1 % / 2 % | z = (u − 1)/σ_R | Falsa alarma por evaluación |
|---|---|---|---|---|
| Hoy (10 + 10 ráfagas, u = 1.5) | 470 / 470 ms, ciclo útil 2 % | 0.45 / 0.89 % | 112 / 56 | ≪ 10⁻³⁰⁰ |
| P0 continuo (u = 1.5) | 470 / 470 ms, 100 % | 0.065 / 0.13 % | 770 / 385 | ≪ 10⁻³⁰⁰ |
| P1 (u = 1.2) | 20 / 200 ms | 0.23 / 0.47 % | 85 / 43 | ≪ 10⁻³⁰⁰ |
| P2 (u = 1.25) | 40 / 400 ms | 0.17 / 0.33 % | 150 / 75 | ≪ 10⁻³⁰⁰ |

- **Ruido correlacionado.** No se promedia dentro de ventanas más cortas que τ_c, así que σ_R ≈ σ_c·√(2(1 − ρ)), con ρ la correlación entre las dos ventanas contiguas.
  - Es del orden de σ_c. Las ventanas contiguas correlacionadas se restan en parte, así que √2·σ_c es la cota superior.
  - Con σ_c = 2 % y P1, z ≳ 7 → < 10⁻¹² por evaluación, sobre 4000 evaluaciones por nodo de 40 s.
  - Con σ_c = 5 %, z ≈ 3-4.
- **Simulado.** Fracción de nodos de 40 s **sin evento** que paran igual (100 nodos):

  | Ruido | Hoy | P0 | P1 | P2 |
  |---|---|---|---|---|
  | blanco 2 % | 0 | 0 | 0 | 0 |
  | blanco 2 % + OU 2 % | 0 | 0 | 0 | 0 |
  | blanco 2 % + OU 5 % | 0 | 0 | **0.02** | 0 |

- **El piso de u con ventanas cortas lo pone el ruido correlacionado, no el blanco.** Con P1, u no debería bajar de ≈ 1.2 mientras σ_c no esté medido (T-6, `BANCO`).

**Conclusión sobre el ruido.** Con escalones de ×1.4-2, ΔI/σ es ≥ 20 aun en el caso más conservador. **El ruido no gobierna ni los falsos positivos ni los falsos negativos del criterio, ni hoy ni con bloques.** Promediar bloques de 10-20 ms (√10 ≈ 3.2 y √20 ≈ 4.5 menos σ por punto que una ráfaga de 1 ms, si el ruido es blanco) cambia cinco cosas:

1. **El borde de detección.** Hoy el paso de P_det = 0.1 a 0.9 va de r ≈ 1.57 a 1.61 y lo fija la **fase del escalón respecto de los ticks** más el jitter. Es un falso negativo aleatorio que no viene del ruido. Con P0 continuo el borde mide < 0.01 en r (T-3).
2. **La visibilidad de las NP de paso** (1-10 ms). Hoy una NP de paso cae dentro de una ráfaga con probabilidad ≈ (D + 1 ms)/47 ms, entre 4 y 23 %. En continuo se integra **siempre**, con peso D/W_new.
   - En promedio el aporte es el mismo, (r_p − 1)·D/W.
   - Con ventanas largas es inofensivo: con P0, ≤ 2 % de R para D ≤ 10 ms.
   - Con ventanas cortas puede disparar (§3.3).
3. **50 Hz.** Las ráfagas de 1 ms cada 47 ms pliegan los 50 Hz a ≈ 7 Hz sin atenuarlos. Una ventana de 20 ms (o un múltiplo) los anula.
   - Con W_new = 20 ms el nulo está en la ventana, sea el bloque de 10 o de 20 ms. Por eso T_b sólo fija la cadencia de evaluación.
4. **El margen para bajar u.** Bajar u a ≈ 1.2-1.25 permite detectar ×1.4 con margen, sin que el ruido blanco dé falsas alarmas.
5. **El acortamiento de W_new.** Es lo que permite bajar la latencia (§4).

### 3.3 Falsos positivos por transitorios físicos (lo que sí gobierna la especificidad)

Pulso rectangular de duración D y razón r_p, con σ = 2 %. Es P(parada) en `c01_criterion_sim.py`, con 150 ensayos para el modelo de ticks y 400 para los bloques.

| Criterio | r_p | 2 ms | 5 | 10 | 20 | 50 | 100 | 200 | 300 | 500 ms |
|---|---|---|---|---|---|---|---|---|---|---|
| Hoy | 1.2 / 1.5 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Hoy | 2.0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.11 | **1** | **1** |
| P0 | 1.2 / 1.5 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| P0 | 2.0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **1** | **1** |
| P1 | 1.2 | 0 | 0 | 0 | 0 | 0.06 | 0.08 | 0.07 | 0.07 | 0.06 |
| P1 | 1.5 | 0 | 0 | 0 | 0.40 | **1** | **1** | **1** | **1** | **1** |
| P1 | 2.0 | 0 | 0 | 0.19 | **1** | **1** | **1** | **1** | **1** | **1** |
| P2 | 1.2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| P2 | 1.5 | 0 | 0 | 0 | 0 | 0 | **1** | **1** | **1** | **1** |
| P2 | 2.0 | 0 | 0 | 0 | 0 | 0.98 | **1** | **1** | **1** | **1** |

Lectura:
- **NP de paso (1-10 ms).** Ningún criterio las toma por captura salvo P1 con r_p = 2 y D = 10 ms (0.19). Si hace falta, se corrige con τ_hold = 30 ms, a +10 ms de latencia.
- **Atrapamiento transitorio (cientos de ms).**
  - Hoy y con P0 se rechaza **si** r_p ≤ u = 1.5, dure lo que dure.
  - Si r_p ≈ 2, se rechaza hasta ≈ 240 ms (c_p = 470·0.5/1).
  - P1 y P2 lo toman por captura siempre que r_p > u. Es la cota causal de §2.1: una latencia de 30-90 ms no puede rechazar transitorios de igual amplitud que duren más de 30-90 ms.
- **La especificidad de hoy frente a atrapamientos no viene de N_hold.** Viene de la ventana de 470 ms más el umbral alto, y es la misma ventana que causa la latencia de 330-500 ms y el hueco r < 1.57.
- **Qué transitorios hay en este banco no está medido.** La única referencia es el banco CIBION (Martínez Fig. 3.9): picos de ≈ +17 % (r_p ≈ 1.17) de 1-2 puntos, y una caída de 0.76 durante ≈ 0.3 s (Fig. 3.6b).
  - Si en este banco los transitorios fueran de r_p ≲ 1.2, un umbral u = 1.25 los separaría **por amplitud**, sin costo de latencia.
  - Si llegan a r_p ≥ 1.5 con D ≥ 50 ms, hace falta una **confirmación posterior al cierre** (§4.3).
  - Decidir esto exige trazas de banco (Fase B del experimentalist R1; pregunta 7).

---

## 4. Latencia de detección contra el objetivo (mediana ≤ 50 ms, p95 ≤ 100 ms; no confirmado)

### 4.1 Qué es la latencia y por qué importa (para la pregunta 2 abierta del investigador)

**Latencia** es el tiempo entre el instante en que la NP queda fija (el escalón físico) y el instante en que el haz de impresión queda bloqueado. Tiene cuatro términos:

$$L = \underbrace{t_c + \tau_{\text{hold}} + \delta_q}_{\text{criterio (esta sección)}} + \underbrace{t_{\text{lectura}} + t_{\text{proc}}}_{\text{software}} + \underbrace{t_{\text{DO}}}_{\text{orden al obturador}} + \underbrace{t_{\text{mec}}}_{\text{carrera del obturador}}$$

Durante L la NP ya impresa sigue en el centro del haz a temperatura plena. Por eso L importa por dos razones:

- **Dosis térmica.** Es proporcional a L.
  - El legado cortaba en 10-100 ms (Martínez p. 112).
  - Hoy el término del criterio solo ya es de 330-500 ms (§2.3), 3 a 50 veces más.
- **Segunda NP.** Si llega a razón λ, P(2.ª NP) ≈ 1 − e^{−λL}.
  - Con λ ≈ ln 2/4.7 s ≈ 0.15 s⁻¹ (Gargiulo 2017, otro banco) da ≈ 5-7 % a 330-500 ms y ≈ 0.5-1.5 % a 35-100 ms.
  - [DERIVADO] Es una cota superior: la repulsión termoforética después de la primera NP baja λ.

El objetivo "mediana ≤ 50 ms, p95 ≤ 100 ms" es la envolvente del legado (experimentalist R1, R-lat) y vale **de punta a punta**. Hay dos términos que no son míos y **no están medidos**:
- **t_mec:** obturador casero, sin tiempo de respuesta medido. Si es un servo, puede ser de decenas de ms o más.
- **t_DO:** incluye la confirmación de `DEC-036`.

Si t_mec ≳ 50 ms, **ninguna** elección de ventanas cumple el objetivo. Por eso propongo repartirlo así:
- criterio ≤ 40 ms de mediana;
- software ≤ 5 ms;
- t_DO + t_mec medidos aparte (instrumentación R1, M4).

### 4.2 Latencia del criterio por propuesta [DERIVADO + simulado, σ = 2 %]

Predicción de la fórmula de §2.1: L_crit ∈ [t_c + τ_hold, t_c + τ_hold + T_b]. Coincide con la simulación dentro de ±2 ms en todas las propuestas por bloques, y eso es una verificación cruzada del modelo. El modelo de ticks de hoy es discreto y se simula directamente.

| Propuesta | T_b | W_new / W_old | u | τ_hold | Base | r = 1.4 | 1.5 | 1.6 | 1.8 | 2.0 | ¿Cumple? |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Hoy** (ticks de 47 ms) | — | 10 / 10 ticks | 1.5 | 3 ticks | viva | no detecta | no detecta | 491 / 522 (P = 0.79) | 400 / 424 | 329 / 372 | **no** |
| **P0** equivalente | 10 ms | 470 / 470 ms | 1.5 | 90 ms | viva | no detecta | no detecta | 487 / 492 | 389 / 394 | 330 / 335 | **no** (paridad) |
| **P1** latencia | 10 ms | 20 / 200 ms | 1.2 | 20 ms | congelada | 35 / 40 | 33 / 38 | 32 / 36 | 30 / 34 | 29 / 34 | **sí** (deja ≈ 15 ms de mediana y ≈ 60 ms de p95 para software, t_DO y t_mec) |
| P1 con bloque de 20 ms | 20 ms | 20 / 200 ms | 1.2 | 20 ms | congelada | 40 / 49 | 38 / 47 | — | — | 34 / 43 | **sí** |
| **P2** compromiso | 10 ms | 40 / 400 ms | 1.25 | 60 ms | congelada | 90 / 95 | 85 / 89 | 81 / 86 | 78 / 82 | 75 / 79 | mediana no, p95 sí (sin margen para t_mec) |

Cada celda de r es "mediana / p95" en ms.

- **Base congelada.** Al primer tick verdadero, I_old se fija y ya no absorbe el escalón. Así, **todo escalón persistente con r > u se detecta**, sin el límite D_true de §2.1.
  - Simulado con P0 congelada: detecta r ≥ 1.55, frente a 1.57 con base viva. En P0 la ganancia es chica.
  - En P1 y P2 es la que permite u bajo sin perder escalones.
  - Si la condición cae, la base se libera.
- **Armado.** No se evalúa hasta que W_old esté llena con datos posteriores a la apertura **confirmada** del obturador más un asentamiento t_settle (a medir con el flanco del BS).
  - Evita el "success" espurio de §1.2.
  - Cuesta W_old + t_settle al inicio del nodo: ≈ 0.2-0.4 s con P1 y P2, 0.94 s con P0 (igual que hoy). Frente a capturas de 1-20 s es despreciable.

### 4.3 Recomendación para el motor (sujeta a la Ronda 2 conjunta)

1. **El motor acepta parámetros en ms:**
   - W_new_ms, W_old_ms, u (y u_down, §5), tau_hold_ms, freeze_baseline, sign ∈ {+1, −1};
   - t_settle_ms, T_max_s;
   - T_b sólo como cadencia de evaluación. **Las ventanas se calculan sobre muestras** (sumas acumuladas por bin de 1 ms), no sobre bloques, así que no dependen de T_b.
2. **Secuencia de despliegue:**
   - primero **P0** como preset de paridad (el mismo comportamiento que hoy, en ms, verificable en el banco);
   - después **P1** (o P2) como preset objetivo.
3. **P1 sólo es aceptable si se cumple una de dos condiciones:**
   - las trazas de banco muestran que los transitorios de este banco tienen r_p < u o D < 20 ms; o
   - se agrega una **confirmación después del cierre**. Ese es el antecedente de Gargiulo et al., ACS Nano 2017, p. E-F: bloquear 1 s y reinterrogar con el haz de detección.
4. **Cómo sería la confirmación.** Al cerrar, una lectura corta a **baja potencia** (flipper arriba) compara el nivel con una base a baja potencia tomada antes del nodo.
   - Una NP impresa conserva R ≈ r: el cociente no depende de la potencia si la detección es lineal.
   - Una NP atrapada se va en ms cuando desaparece la trampa.
   - Si no hay NP, el nodo vuelve a la cola **sin** rotularse "success".
   - Esto saca el rechazo de atrapamientos de la ruta de la latencia.
   - Otra opción: el escaneo confocal posterior que ya existe (`grid_scan`, `measurements.py:2442-2446`, "Scan pre-print?", corre después de la detección). No verifiqué si `on_scan_finished` puede reclasificar el nodo.
   - **EXPERIMENTAL**: el costo por nodo (≈ 1-1.5 s de flipper) y la linealidad los tienen que evaluar experimentalist e instrumentation.
5. **Prueba de estabilidad de la meseta.** Una NP atrapada se mueve en 3D y el iSCAT convierte z en fase, así que su señal debería fluctuar más que la meseta de una NP fija. Una prueba de σ(x) en W_new frente a σ de la base podría separarlas sin latencia extra.
   - Es una **hipótesis sin datos**: se prueba con trazas de banco antes de usarla.

---

## 5. Escalón negativo (contraste negativo con otros láseres o fuera de resonancia)

### 5.1 Física y estado actual

- **Por qué puede bajar la señal.** I_d = I_r + I_sca + 2√(I_r·I_sca)·cos φ (Martínez p. 57). Con Au 80 nm el contraste es máximo a 532 nm y **mínimo a 808 nm**. Fuera de resonancia la señal puede bajar (ACS Nano 2017 p. E-F).
- **El contraste está acotado de un solo lado:** C = R − 1 ≥ −1, pero no tiene techo hacia arriba. Para un dispersor débil C ≈ 2√(I_sca/I_r)·cos φ, lineal en el campo.
- **Hoy [CÓDIGO]** una caída sólo entra por la rama d (`measurements.py:2408`): I_new < d·I_old con d = 0.5.
  - Una captura negativa con R < 0.5 cierra el obturador, pero se rotula **"timeout"**. El Healing Pass la reexpone (§1.3).
  - Una captura negativa con 0.5 < R < 1 **nunca** se detecta: el láser sigue 40 s.
- En este banco no se informó impresión con 592, 637 u 808 nm. El tamaño de un contraste negativo acá es **desconocido** (pregunta 9).

### 5.2 Diseño propuesto: el signo es un parámetro a priori del preset, no una detección bilateral

1. **Signo por preset.** `sign ∈ {+1, −1}` es el "contraste esperado". Lo elige el preset según láser, NP y λ. Default +1, la práctica actual.
   - Con sign = −1, la condición es R < u_down.
   - u_down es un parámetro **propio**. Default 1/u (simétrico en log: 0.667 para u = 1.5 y 0.833 para u = 1.2).
   - No se reusa el u de subida, porque la asimetría física de C hace que "×1.5 arriba" y "×0.5 abajo" no sean equivalentes.
   - La persistencia τ_hold, la base congelada y el armado se aplican igual.
   - **Hay una sola prueba por evaluación**, igual que hoy. Por eso la tasa de falsos positivos por ruido **no cambia**, y la de transitorios cambia sólo porque se miran transitorios del otro signo.
2. **La rama d se separa en dos cosas distintas:**
   - con sign = −1, la caída es la **detección** y termina en "success";
   - la **pérdida de señal** (láser caído, obturador que cierra solo, lectura inválida) se detecta con el canal BS (I_BS/I_BS,0 < umbral) y con la validez de la lectura. Da "falla de adquisición" o "falla de láser" y **nunca** "timeout" ni "success";
   - la rama `I_new < d·I_old` del PD deja de existir como "timeout" silencioso.
3. **Normalizar por el BS** para las dos polaridades: R' = (I_new/BS_new)/(I_old/BS_old).
   - Una caída de potencia del láser mueve PD y BS por igual y R' no cambia. Es la principal fuente de caídas espurias.
   - Hace falta confirmar en el banco que el BS toma la potencia **después** del obturador y del flipper (pregunta 13).
4. **Veto de lectura.** Un bloque con error es NaN y pasa a la ruta de falla con cierre (`DEC-037`, pendiente). **Nunca** cuenta como caída ni como subida.

### 5.3 Por qué no la detección bilateral automática [DERIVADO + simulado]

- **Ruido:** dos pruebas duplican la tasa de falsas alarmas. Con z > 40 sigue siendo despreciable. El problema no es el ruido.
- **Transitorios del otro signo:** la bilateral suma sus falsos positivos, y el único transitorio documentado es justamente una **caída** (Martínez Fig. 3.6b: R ≈ 0.76 durante ≈ 0.3 s, origen no documentado). Simulado, P(parada) ante esa caída:

  | Criterio negativo | D = 10 ms | 50 ms | 100 ms | 300 ms | 500 ms |
  |---|---|---|---|---|---|
  | P1(−), u_down = 0.833 | 0 | **1** | **1** | **1** | **1** |
  | P2(−), u_down = 0.8 | 0 | 0 | **1** | **1** | **1** |
  | P0(−), u_down = 0.667 | 0 | 0 | 0 | 0 | 0 |

- **Detección de escalones negativos persistentes:**
  - P1(−): r = 0.8 → P = 1.00, 41 ms; r = 0.6 → 34 ms.
  - P2(−): r = 0.76 → 98 ms; r = 0.8 → P = 0.03, porque está justo en u_down = 0.8.
  - r = 0.9 no se detecta con ninguna.
- **Conclusión:** una bilateral con ventanas cortas convierte en "success" toda caída transitoria de ≥ 50-100 ms.
  - Con signo a priori, esas caídas sólo importan en los presets de contraste negativo.
  - Ahí valen la misma confirmación posterior al cierre (§4.3) y la normalización por el BS.
  - Si alguna vez se necesita la bilateral (contraste de signo desconocido), tiene que ir **siempre** con esa confirmación.

---

## 6. Tests con verdad conocida

### 6.1 Contrato para que sea testeable

- **El detector es una función pura**, sin Qt ni DAQ:
  - acumula muestras (o bins de 1 ms) con su marca de reloj de muestreo;
  - devuelve (índice de decisión, etiqueta ∈ {success, timeout, falla_adquisicion, falla_laser});
  - recibe los parámetros de §4.3.
  - El hilo de adquisición (opción E) sólo la alimenta. Así los tests corren en `SAFE_MODE`, sin temporizadores, y son deterministas con semilla fija.
- **Referencia de hoy:** una implementación de referencia del criterio en ticks, copia fiel de `trace.py:705-717` más `measurements.py:2358-2418`, **sólo en los tests**, para medir la paridad (T-2) y documentar el comportamiento actual (T-5, T-8).
- **Generador sintético** (a 10 kS/s o en bins de 1 ms; `c01_criterion_sim.py` es el prototipo):
  - base b;
  - escalón r en t_s, con fase aleatoria respecto del bloque;
  - pulsos (D, r_p);
  - rampa de apertura del obturador t_open;
  - ruido blanco σ_1ms y OU (σ_c, τ_c);
  - 50 Hz de amplitud a_h;
  - caída de potencia común a PD y BS;
  - bloques NaN.
- **Tolerancias estadísticas:** con n = 400 ensayos, ±0.05 en proporciones (≈ 2σ binomial). Las latencias se comparan contra la fórmula de §2.1 con ±1 ms, o ±T_b cuando interviene la fase.

### 6.2 Batería

| ID | Señal (verdad) | Qué se exige | Valor esperado |
|---|---|---|---|
| T-1 | Sin ruido. Barrido: r ∈ {1.3, 1.4, 1.5, 1.6, 2, 2.5}; u ∈ {1.2, 1.5}; W_new ∈ {20, 40, 470} ms; τ_hold ∈ {0, 20, 90} ms; T_b ∈ {10, 20} ms; 10 fases de t_s dentro del bloque | latencia dentro de [t_c + τ_hold, t_c + τ_hold + T_b]; detecta sii r > r_min (base viva) o r > u (congelada) | fórmulas de §2.1 exactas |
| T-2 | Paridad: σ = 2 %; r ∈ {1.6, 1.8, 2.0}; referencia de ticks a 47 ms frente a P0 (470/470/90) | diferencia de medianas ≤ 20 ms; r_min(P0) ∈ [1.56, 1.58] | hoy 491/400/329, P0 487/389/330 ms |
| T-3 | **Curva de detección** P_det(r), σ = 1 % y 2 % | la tabla de §6.3, ±0.05 | §6.3 |
| T-4 | Pulsos D ∈ {2, 5, 10, 20, 50, 100, 200, 300, 500} ms; r_p ∈ {1.2, 1.5, 2} | la tabla de §3.3, ±0.05. Documenta el costo de cada preset, no es una propiedad deseada | P0: (2.0, 200 ms) → 0 y (2.0, 300 ms) → 1; P1: (1.5, 50 ms) → 1 |
| T-5 | **Hueco del preset actual:** escalón r = 1.45 en t_s = 5 s; T_max = 40 s | referencia y P0: sin "success", cierre por T_max rotulado "timeout" (control negativo). P1: "success" en < 50 ms | referencia y P0: t = 40 s; P1: ≈ 35 ms |
| T-6 | Nodo sin evento de 40 s; 100 nodos; blanco 2 % + OU 2 % (τ_c = 100 ms) | 0 paradas con todas las propuestas | 0/100. Estrés con OU 5 %: P1 ≤ 5 % (simulado 2 %) |
| T-7 | Signo: r = 0.6 con sign = −1; r = 0.6 con sign = +1; caída del 50 % de la potencia **común** a PD y BS | sign = −1: "success" (P1 ≈ 34 ms). sign = +1: nunca "success" ni "timeout" por la rama d. Caída común: sin detección con R' normalizado; "falla_laser" si I_BS cae bajo su umbral | — |
| T-8 | Rampa de apertura t_open ∈ {0, 20, 50, 100, 200} ms, sin evento | con armado: 0 paradas. Referencia de ticks: con t_open ≥ ≈ 100 ms reproduce el "success" espurio de §1.2 a n ≈ M + N_hold (documenta) | — |
| T-9 | Un bloque NaN en una posición al azar; y 3 seguidos | ni detección ni falso "timeout" por ese bloque; 3 seguidos → "falla_adquisicion" con cierre. Nunca un 0.0 sustituido en el payload | — |
| T-10 | 50 Hz de amplitud 5 % sobre la base | P1 (W_new = 20 ms): 0 paradas en 40 s; la latencia cambia < T_b | — |
| T-11 | Base viva frente a congelada: r = 1.52, u = 1.5, P0 | viva: no detecta; congelada: detecta | simulado: P0' detecta r ≥ 1.55 |
| T-12 | Marca de tiempo: escalón inyectado en la muestra k_s | latencia medida con el reloj de muestreo (t_k = (k + ½)·N_b/f) igual a la inyectada ± 1 ms, **no** con `time.time()` | — |
| T-13 | Escalón en los primeros W_old ms después del armado (captura inmediata) | se detecta con latencia acotada, o se marca "captura durante el armado" (no se pierde en silencio) | define el comportamiento en el borde |

### 6.3 Curva de detección esperada (T-3) [simulado, `c01_criterion_sim2.py`]

P_det por r, σ_1ms = 1 % / 2 %:

| r | 1.18 | 1.19 | 1.20 | 1.21 | 1.22 | 1.23 | 1.25 |
|---|---|---|---|---|---|---|---|
| **P1** (u = 1.2, base congelada) | 0 / 0 | 0 / 0 | 0.04 / 0.05 | 0.78 / 0.59 | 1.00 / 0.97 | 1 / 1 | 1 / 1 |

| r | 1.54 | 1.55 | 1.56 | 1.57 | 1.58 | 1.59 | 1.60 | 1.62 | 1.65 |
|---|---|---|---|---|---|---|---|---|---|
| **P0** (470/470/90, viva) | 0 / 0 | 0 / 0 | 0 / 0 | 0.65 / 0.60 | 1 / 1 | — | 1 / 1 | — | — |
| **Hoy** (ticks) | — | — | 0.00 / 0.04 | 0.01 / 0.17 | 0.15 / 0.34 | 0.61 / 0.51 | 0.89 / 0.77 | 1.00 / 0.96 | 1 / 1 |

Lectura:
- **Hoy**, el borde de 10 a 90 % va de r ≈ 1.58 a 1.61 con σ = 1 %, y de ≈ 1.565 a 1.62 con σ = 2 %.
  - Lo dominan la fase del escalón respecto de los ticks y el jitter, y el ruido lo ensancha.
- **Con P0** el borde mide ≈ 0.01 en r y queda en r_min = 1.57, el valor de la fórmula.
- **Con P1** el borde queda en u + 0.01. Se desplaza del u nominal porque la base congelada y la persistencia de 3 evaluaciones piden que R supere u en las tres.

---

## 7. Preguntas para el investigador (una línea cada una)

1. En el preset "umbral + valor absoluto", ¿qué valen el **umbral absoluto (V)** y el **Umbral Mín (V)**? ¿Qué voltajes típicos tienen la base y la meseta en ai0?
2. En ese preset, ¿"Steps before" y "Steps after" siguen en 10 y 10?
3. En los nodos TIMEOUT, ¿el escaneo o la imagen posterior muestra una NP impresa? Si la muestra, pesa la hipótesis del hueco r < 1.57 (§2.3).
4. En la traza guardada de un nodo TIMEOUT, ¿se ve un escalón de ×1.4-1.55 que no se detectó?
5. ¿Hay nodos SUCCESS con t_print < 1 s (≈ 0.6 s)? Sería el artefacto de apertura del obturador (§1.2).
6. ¿Usás el Healing Pass (autocompletar) en la práctica?
7. ¿Se ven en las trazas subidas transitorias que no terminan en impresión? ¿De cuánto (×) y cuánto duran (ms)?
8. ¿Aceptás cerrar el obturador ante un transitorio y **verificar después** (lectura a baja potencia o escaneo posterior), a cambio de una latencia ≤ 50 ms?
9. ¿Imprimís, o vas a imprimir, con 592, 637 u 808 nm, o con NPs de contraste negativo? ¿De cuánto es la caída?
10. ¿El signo del contraste se elige a priori en el preset (recomendado) o preferís detección bilateral con confirmación obligatoria?
11. Objetivo de latencia (§4.1): ¿"mediana ≤ 50 ms, p95 ≤ 100 ms" desde el escalón hasta el haz bloqueado sirve como meta, o hay otro límite (dosis, 2.ª NP)?
12. En la GUI, ¿N_hold se expresa como **persistencia en ms** (cuánto tiene que sostenerse la condición; recomendado) o como cantidad de evaluaciones?
13. ¿El fotodiodo BS (ai6) mide la potencia **después** del obturador y del flipper, de modo que ve la apertura y el cierre?

---

## Veredicto: `ALGORITHMICALLY_OPTIMIZABLE`

- El criterio es un cociente de dos ventanas contiguas en ticks. Su comportamiento se reexpresa exactamente en ms con la regla de §2.4:
  - W_new = 470 ms, W_old = 470 ms, τ_hold = 90 ms, a T = 47 ms.
  - La paridad simulada está dentro de ≈ 10 ms de la mediana.
- **Hallazgo principal [DERIVADO, simulado; falta confirmarlo en el banco].** Con el preset en uso (u = 1.5, N_hold = 3, M = M2 = 10) la rama relativa **no detecta nunca** escalones de ×1.4 a ≈ ×1.57, la parte baja del rango que informa el operador.
  - Esos nodos dependen de V_abs o terminan en T_max = 40 s como "timeout". Si el Healing Pass está activo, los reexpone.
  - Para los escalones que sí detecta, la latencia del criterio solo es de 330-500 ms.
- **El ruido no limita.** Con 1-2 % de ruido y escalones ×1.4-2, z ≥ 40.
  - Promediar bloques de 10-20 ms (opción E) no cambia las tasas de falsos positivos y negativos por ruido. Afina el borde de detección, anula los 50 Hz y **habilita ventanas cortas**.
- **Lo que decide es la especificidad frente a transitorios, y tiene una cota causal:** con latencia L no se puede rechazar un transitorio de igual amplitud que dure más que L.
  - Cumplir el objetivo de latencia (P1: 33 / 38 ms a r = 1.5) exige una de dos cosas: que los transitorios de este banco sean de amplitud menor que u, o una confirmación después del cierre.
  - Ninguna de las dos está medida.
- **Escalón negativo:** signo a priori por preset, u_down propio, la rama de caída separada de la de pérdida de señal (esta por el BS) y normalización por el BS. No detección bilateral.

## Reproducibilidad

Los scripts están en el scratchpad de la sesión:
- `...\scratchpad\c01_criterion_sim.py`: escalones y pulsos, §2-§4;
- `...\scratchpad\c01_criterion_sim2.py`: curvas de detección, falsas alarmas por ruido, bloque de 20 ms y escalón negativo, §3, §5 y §6.

Semillas fijas: 20260927 y 7. Corren con el `.venv` del repo en ≈ 1 min.

**No se copiaron** a esta carpeta, por la regla de sólo lectura de esta ronda. Si se quieren como evidencia, conviene copiarlos junto a `c01_ronda1/*.py`.
