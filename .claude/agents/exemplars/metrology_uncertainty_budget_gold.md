# Gold Exemplar: Presupuesto de Incertidumbre ISO/GUM — localización confocal, auditado

Referenciado por `metrology.md` y por la skill `metrology-review`. Es el presupuesto de `CAT-203`
para la localización lateral de una nanopartícula, tal como quedó después de la auditoría del
2026-09-27 (lote L5). La versión anterior de este ejemplar copiaba ese presupuesto con todas sus
cifras: la suma en cuadratura cerraba ($u_c = 6.55$ nm), pero el modelo de medición contaba dos
veces la pixelación, el término de ajuste violaba la cota de Cramér-Rao y cuatro de los cinco
valores no tenían respaldo. **Que la suma cierre no prueba que el presupuesto sea correcto.**

Igualar esta estructura: ecuación de medición, fuentes clasificadas y con respaldo, control contra
la cota física, combinación sólo con lo que existe, término dominante comprobado.

## Caso: localización lateral $x_0$ de una NP en una imagen confocal

Barrido de la platina con detección por fotodiodo, objetivo Olympus 60x de agua, 532 nm. Los
valores salen de `.claude/shared/lab-invariants.md`, con su rótulo de respaldo:

| Parámetro | Valor | Respaldo |
| :--- | :--- | :--- |
| Apertura numérica | NA = 1.0 | RESPALDADO ([P25] p. 30; `MICROSCOPE_OBJECTIVES`) |
| $\sigma$ de la imagen de una NP | 133 nm $= w_0/2$ con $w_0 = 266 \pm 3$ nm ([NL17] p. 2); 139 nm con $w_0 = 278$ nm ([M24] p. 129) | DERIVADO, medido en CIBION: $I \propto e^{-2r^2/w_0^2}$ implica $\sigma = w_0/2$ |
| Magnificación al pinhole | $M = 50$ (lente de 150 mm, objetivo de $f = 3$ mm) | DERIVADO de un dato EXPERIMENTAL (§7) |
| Deriva en XY sin compensar | 30 nm/min ([M24] p. 75) hasta medirla en el banco | RESPALDADO (CIBION) |
| Paso de barrido $a$ | 15 nm/px | parámetro del ejemplo (lo elige el operador) |
| Fotones detectados $N$ | $10^4$ | **supuesto del ejemplo**, no medido |

## 1. Ecuación de medición

$$\hat{x}_0 = x_{\text{fit}} + \delta_{\text{piezo}} + \delta_{\text{drift}} + c_{\text{ph}}\,\delta_{\text{ph}}
\qquad\Longrightarrow\qquad
u_c^2 = u_{\text{fit}}^2 + u_{\text{piezo}}^2 + u_{\text{drift}}^2 + c_{\text{ph}}^2\,u^2(\delta_{\text{ph}})$$

* **No hay término de píxel aparte.** En un ajuste sub-píxel la pixelación ya está dentro de
  $u_{\text{fit}}$, como $a^2/12$ en $\sigma_a^2$ (sección 3). $\Delta x/\sqrt{12}$ sólo describe un
  estimador que devuelve el píxel más cercano.
* **La independencia es una afirmación física**, no una conveniencia algebraica. Si el recentrado en
  $P_0$ y la deriva compartieran una causa, habría un término $2\,c_i c_j\,u(x_i, x_j)$.
* **Declarar el mensurando.** $\delta_{\text{ph}}$ desplaza la imagen entera: entra en una posición
  absoluta, pero se cancela en las distancias entre partículas, que son lo que usan las métricas de
  red.

## 2. Fuentes, con tipo, sensibilidad y respaldo

| Fuente | Tipo | Distribución | $c_i$ | $u_i$ | Estado |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Ajuste de la PSF, $u_{\text{fit}}$ | A (repetición sobre la misma partícula) | — | 1 | **≥ 1.33 nm** (cota, no valor) | El código descarta la covarianza del ajuste (`analysis/psf_analyzer.py`, `popt, _ = curve_fit(...)`): se mide por repetición |
| Piezo en lazo cerrado, $u_{\text{piezo}}$ | A | — | 1 | **sin valor** | SIN FUENTE. Medir: lectura del sensor a posición fija durante ≥ 10 min, desviación estándar con sus grados de libertad (`lab-invariants` §1) |
| Deriva residual, $u_{\text{drift}}$ | A | — | 1 | **sin valor** | Sale del residuo **medido** tras cada recentrado en $P_0$. Sin compensar, 30 nm/min durante 2 min son 60 nm, y eso es un sesgo que deforma la imagen, no un ruido. El autofoco es axial y no corrige $x_0$ |
| Desalineación del pinhole, $\delta_{\text{ph}}$ | B | rectangular de semiancho $\delta$: $u = \delta/\sqrt{3}$ | no es $1/M$: en un confocal la imagen es el producto de las PSF de excitación y de detección, y el pinhole corre sólo la segunda. Con dos gaussianas, $c_{\text{ph}} = \frac{1}{M}\,\frac{\sigma_e^2}{\sigma_e^2 + \sigma_d^2}$ (DERIVADO, a verificar) | **sin valor** | La cota de ±1.0 µm de `CAT-203` no tiene fuente |

**Tipo A** = evaluada estadísticamente a partir de observaciones repetidas. **Tipo B** = de
especificación, geometría o juicio científico. La distinción fija de dónde salen los grados de
libertad: una Tipo A con $n$ repeticiones tiene $\nu = n - 1$.

## 3. Cota de Cramér-Rao: el control que la versión anterior no pasaba

Rieger & Stallinga (2014), Ec. 7 (doi:10.1002/cphc.201300711), la misma forma que `metrology.md`:

$$\sigma_{\text{CRLB}}^2 = \frac{\sigma_a^2}{N}\left(1 + 4\tau + \sqrt{\frac{2\tau}{1+4\tau}}\right),
\qquad \sigma_a^2 = \sigma^2 + \frac{a^2}{12}, \qquad \tau = \frac{2\pi b\,\sigma_a^2}{N a^2}$$

Con $\sigma = 133$ nm, $a = 15$ nm, $N = 10^4$ y **sin fondo** ($b = 0$, el caso más favorable,
porque todo fondo sube la cota):

$$\sigma_a^2 = 133^2 + \frac{15^2}{12} = 17\,707.75\ \text{nm}^2
\qquad \sigma_{\text{CRLB}} = \sqrt{17\,707.75 / 10^4} = \mathbf{1.33\ nm}\quad(1.39\ \text{nm con}\ \sigma = 139\ \text{nm})$$

* La pixelación aporta $\sqrt{15^2/12/10^4} = 0.043$ nm. La versión anterior la sumaba aparte como
  $15/\sqrt{12} = 4.33$ nm: cien veces más, y era su término dominante.
* El $u_{\text{fit}} = 0.55$ nm de la versión anterior está 2.4 veces **por debajo** del piso con
  $N = 10^4$. Ningún estimador insesgado lo alcanza: era un error de cálculo, no una precisión.
* **Supuesto de detección.** La fórmula supone conteo de fotones (Poisson). El canal confocal usa un
  fotodiodo analógico: $N$ no se cuenta, hay que convertir la señal con la responsividad y la
  ganancia, y el ruido electrónico se suma. Por eso esta cota es un piso optimista, que es justo lo
  que hace falta para refutar una precisión menor. El factor $F^2 = 2$ corresponde a datos de
  EMCCD, no al fotodiodo.

## 4. Qué se puede afirmar hoy

Tres de los cuatro términos no tienen valor, así que **no hay $u_c$ ni $U$ que reportar**. Lo
defendible es:

$$u_c(x_0) \ge 1.33\ \text{nm}\quad (N = 10^4\ \text{supuesto},\ b = 0),\qquad
\text{sin cota superior hasta medir}\ u_{\text{piezo}}\ \text{y}\ u_{\text{drift}}\ \text{y acotar}\ \delta_{\text{ph}}$$

Cuando las filas tengan valor:
1. recalcular la cuadratura desde la tabla, sin confiar en el total escrito;
2. calcular $\nu_{\text{eff}}$ con Welch-Satterthwaite y elegir $k$ a partir de él. $k = 2$ da
   ≈ 95 % sólo con salida aproximadamente normal y $\nu_{\text{eff}}$ grande (JCGM 100:2008 §6.3,
   Anexo G);
3. ordenar las contribuciones a $u_c^2$ y nombrar el término dominante y su palanca;
4. reportar $x_0 = (\bar{x}_0 \pm U)$ nm con $k$ y el nivel de confianza al lado. Un número sin su
   factor de cobertura no es trazable.

## 5. Qué estaba mal en la versión anterior, y por qué la suma cerraba igual

| Término | Versión anterior | Problema | Hallazgo |
| :--- | :--- | :--- | :--- |
| $u_{\text{pix}}$ | $\Delta x/\sqrt{12} = 4.33$ nm, 44 % de $u_c^2$ | Doble conteo de la pixelación | L5-202-06, L5-203-04 |
| $u_{\text{fit}}$ | 0.55 nm, "de la matriz de covarianza" | Por debajo de la CRLB; el código no calcula esa matriz | L5-203-05 |
| $u_{\text{ph}}$ | $1000/(83.33\sqrt{12}) = 3.46$ nm | $M = 83.33$ no es la del banco (50); ±1.0 µm es un semiancho, así que va $/\sqrt{3}$ y no $/\sqrt{12}$; $c = 1/M$ sin derivar; cota sin fuente. Sólo corrigiendo el factor y la $M$, con esa misma cota, habría dado 11.5 nm | L5-203-08, `lab-invariants` §7 |
| $u_{\text{drift}}$ | 3.10 nm con 15-25 nm/min "compensada" | Tasa sin fuente (valor retirado); 3.10 sin derivación; el autofoco no corrige $x_0$ | L5-203-07, `lab-invariants` §6 |
| $u_{\text{piezo}}$ | 1.50 nm | Sin datos, método ni tipo GUM | L5-203-06, `lab-invariants` §1 |
| $U$ | 13.10 nm ($k = 2$, 95 %) | $k$ sin $\nu_{\text{eff}}$ | L5-203-10 |
| Verificación cruzada | Nikon 100× de aceite | Ese objetivo no está en el inventario del banco | `lab-invariants` §7 |

La conclusión de ingeniería de la versión anterior, "la palanca real es $\Delta x$", salía del
término contado dos veces. Un término dominante que es un artefacto del modelo manda a optimizar la
variable equivocada: la aritmética cerraba y la decisión era falsa.

## Checklist antes de aceptar un presupuesto

1. ¿Está escrita la ecuación de medición y declarado el mensurando (posición absoluta o distancia
   relativa)?
2. ¿Cada fuente dice tipo A o B, distribución, coeficiente de sensibilidad derivado y rótulo de
   respaldo? Uniforme de semiancho $a$ ⇒ $a/\sqrt{3}$; de ancho total $\Delta$ ⇒ $\Delta/\sqrt{12}$;
   certificado a $k=2$ ⇒ $U/2$.
3. ¿La pixelación entra una sola vez (dentro de $\sigma_a^2$ si el ajuste es sub-píxel)?
4. ¿$u_{\text{fit}}$ respeta la CRLB para el $N$ y el $b$ reales (con $F^2 = 2$ si son conteos
   verdaderos de un EMCCD)?
5. ¿Algún término sin datos tiene un número? Si lo tiene, se borra el número y el término bloquea $U$.
6. ¿La suma en cuadratura **cierra** al recalcularla?
7. ¿$k$ sale de $\nu_{\text{eff}}$ y está declarado junto a $U$?
8. ¿Se identificó el término dominante, y se comprobó que no es un artefacto del modelo?
