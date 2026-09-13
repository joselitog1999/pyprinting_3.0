# Curación Fotométrica, Desacople Multi-Gaussiano y Reglas de Consistencia Reticular en Redes 2D

**Proyecto:** PyPrinting 3.0 — Nanofotónica y Fabricación Óptica  
**Laboratorio:** Nanofotónica — Instituto de Nanosistemas (INS - UNSAM / CONICET)  
**Autor:** José Luis González Peñafiel (*Becario Doctoral CONICET*)  
**Módulos Asociados:** `core/lattice_disorder.py`, `core/localization_pipeline.py`, `analysis/lattice_disorder_gui.py`  
**Pilares Wiki:** [[CAT-201_Deconvolucion_Optica_Richardson_Lucy_y_Tracking_Trackpy]], [[CAT-307_Computacion_NUFFT_Factor_Estructura_Optimizacion_BLAS]]  
**Notas Relacionadas:**  
- [[CAT-301_Algoritmos_Espacio_Real_KDTree_Asignacion_Monte_Carlo]]  
- [[CAT-201_Deconvolucion_Optica_Richardson_Lucy_y_Tracking_Trackpy]]  
- [[CAT-305_Derivacion_Matematica_Factor_Estructura_Debye_Waller]]  
- [[CAT-203_Presupuesto_Incertidumbre_Metrologica_ISOGUM_Microscopia]]  

---

## 1. Resumen Ejecutivo y Motivación Física

En la caracterización metrológica de redes periódicas nanoprintadas mediante microscopía de localización óptica (SMLM o confocal de barrido), la suposición ingenua de que **cada mancha brillante de difracción corresponde exactamente a un único emisor individual (monómero)** introduce errores críticos en la cuantificación de vacancias y desorden:
1. **Falsas Vacancias por Coalescencia:** Dos nanopartículas impresas a distancias sub-difraccionales ($d < \lambda / 2\text{NA} \approx 250\ \text{nm}$) aparecen como un único punto de dispersión difractivo elongado o brillante (dímero/trímero). Un algoritmo ciego registrará una sola partícula en lugar de dos, deduciendo falsamente que falta una partícula contigua (vacancia espuria).
2. **Desviación Artificial del Baricentro:** Si un dímero o cúmulo se localiza mediante un ajuste monogaussiano estándar, su baricentro caerá en el centro geométrico entre ambas partículas, falseando la posición reticular real y elevando artificialmente el desorden medido $\sigma_{\text{pos}}$.
3. **Puntos Satélite Espurios:** Fluctuaciones térmicas, restos de surfactante CTAB o partículas en tránsito pueden detectarse como emisores adicionales fuera de los nodos de la red.

Esta nota técnica establece los fundamentos matemáticos y físicos del **Módulo de Curación Fotométrica y Desacople de Cúmulos** implementado en la Pestaña 1 de PyPrinting 3.0, cubriendo:
- La **firma estequiométrica del monómero** ($V_0, A_0, \sigma_{\text{psf}}$).
- La extracción de contornos de iso-intensidad por el **Teorema de Green**.
- El desacople de emisores solapados mediante **ajuste no lineal n-Gaussiano (Levenberg-Marquardt)** con PSF acotada.
- La **regla de conservación y consistencia reticular**:
  $$M + n_{\text{vac}} \le N^2 \cdot (1 + \text{margen}/100)$$

---

## 2. Firma Fotométrica del Monómero Aislado

Para distinguir analíticamente entre partículas individuales y aglomerados sin recurrir a microscopía electrónica de barrido (SEM), se aprovecha la linealidad de la respuesta fotónica en régimen no saturado.

### 2.1 Definición de Parámetros Fotométricos
Dado un emisor individual aislado $i$ centrado en $(x_i, y_i)$, la función de brillo sobre la cámara en un parche de píxeles $\Omega_i$ se modela como una Gaussiana 2D sobre un pedestal local de fondo:

$$I(x, y) = I_{\text{bg}} + I_0 \exp\left( -\frac{(x - x_i)^2 + (y - y_i)^2}{2 \sigma_{\text{psf}}^2} \right)$$

Se definen tres magnitudes primarias:
1. **Volumen Fotométrico Integrado ($V$):** La integral continua de intensidad fotónica neta por encima del fondo local:
   $$V = \iint_{\Omega_i} [I(x, y) - I_{\text{bg}}] \, dx \, dy = 2\pi I_0 \sigma_{\text{psf}}^2$$
2. **Área Proyectada ($A$):** La superficie en píxeles del contorno donde la intensidad supera una fracción $\theta$ (típicamente $20\%$) de la intensidad máxima sobre el fondo:
   $$A = \iint_{\Omega_i} \Theta(I(x, y) - I_{\text{th}}) \, dx \, dy, \quad I_{\text{th}} = I_{\text{bg}} + \theta (I_{\text{max}} - I_{\text{bg}})$$
3. **Ancho Óptico ($\sigma_{\text{psf}}$):** La dispersión espacial de la Point Spread Function, calibrada experimentalmente o aproximada por difracción:
   $$\sigma_{\text{psf}} \approx \frac{0.21 \lambda}{\text{NA}}$$

### 2.2 Calibración de la Firma de Referencia $(V_0, A_0)$
En una red con separación nominal $a \approx 400 - 500\ \text{nm}$, la mayoría de las posiciones corresponden a nanopartículas aisladas bien separadas. La firma del monómero $(V_0, A_0)$ se obtiene mediante la **mediana estadística robusta** evaluada sobre las partículas con distancia al vecino más cercano $d_{\text{NN}} > 0.75 a$:

$$V_0 = \text{mediana}\left(\{ V_i \mid d_{\text{NN}, i} > 0.75 a \}\right)$$
$$A_0 = \text{mediana}\left(\{ A_i \mid d_{\text{NN}, i} > 0.75 a \}\right)$$

La utilización de la mediana (en lugar de la media aritmética) confiere un punto de ruptura (*breakdown point*) del $50\%$, inmunizando la calibración ante la presencia de dímeros o polímeros en la muestra.

---

## 3. Clasificación Estequiométrica y Detección de Aglomerados

Con la firma unitaria $(V_0, A_0)$ establecida, cualquier mancha candidata $k$ se evalúa mediante sus razones estequiométricas adimensionales:

$$r_V = \frac{V_k}{V_0}, \qquad r_A = \frac{A_k}{A_0}$$

### 3.1 Criterio de Multiplicidad y Tolerancia Porcentual
Bajo una tolerancia de variación fotométrica $\tau$ (típicamente $\tau = 20\%$):
- **Monómero ($n = 1$):**
  $$1 - \tau \le r_V \le 1 + \tau \quad \text{y} \quad r_A \le 1.3$$
- **Dímero ($n = 2$):**
  $$2(1 - \tau) \le r_V \le 2(1 + \tau) \quad \text{o} \quad (r_V > 1.6 \text{ y } r_A > 1.4)$$
- **Trímero ($n = 3$):**
  $$3(1 - \tau) \le r_V \le 3(1 + \tau)$$
- **Cúmulo / Polímero ($n \ge 4$):**
  $$r_V > 3.6$$

El número estimado de partículas discretas ocultas bajo el perfil de intensidad se asigna por redondeo estequiométrico:
$$n_{\text{est}} = \max\left(1, \text{round}(r_V)\right)$$

---

## 4. Delineación de Contornos de Iso-intensidad mediante el Teorema de Green

Para inspeccionar visualmente la morfología de un aglomerado sin discretización rectangular, se extrae el polígono cerrado de contorno a nivel de umbral $I_{\text{th}}$ utilizando el algoritmo de Marching Squares.

### 4.1 Cálculo del Área y Baricentro del Contorno
Dado el polígono cerrado con vértices nanométricos ordenados $\{(x_m, y_m)\}_{m=0}^{K-1}$ (con $(x_K, y_K) = (x_0, y_0)$), el área proyectada y el centro geométrico se calculan de manera exacta por el **Teorema de Green en el plano**:

$$A_{\text{polygon}} = \frac{1}{2} \sum_{m=0}^{K-1} (x_m y_{m+1} - x_{m+1} y_m)$$
$$x_{\text{center}} = \frac{1}{6 A_{\text{polygon}}} \sum_{m=0}^{K-1} (x_m + x_{m+1}) (x_m y_{m+1} - x_{m+1} y_m)$$
$$y_{\text{center}} = \frac{1}{6 A_{\text{polygon}}} \sum_{m=0}^{K-1} (y_m + y_{m+1}) (x_m y_{m+1} - x_{m+1} y_m)$$

Esta formulación proporciona una precisión de sub-píxel en la medición del área sin verse afectada por el efecto escalera (*aliasing*) de los píxeles discretos.

---

## 5. Algoritmo de Desacople Multi-Gaussiano (Nonlinear Least Squares)

Cuando un punto sospechoso o aglomerado es identificado con multiplicidad $n \ge 2$, se resuelve el problema inverso de desacoplar los centros individuales $(x_j, y_j)$ de cada emisor mediante optimización no lineal.

### 5.1 Función Objetivo
Se extrae un recorte local de la imagen $I(x, y)$ de tamaño $(2k+1) \times (2k+1)$ píxeles centrado en la mancha. El modelo óptico teórico para $n$ emisores con amplitudes $A_j$ y ancho óptico fijado por la PSF ($\sigma_{\text{psf}}$) es:

$$I_{\text{model}}(x, y; \boldsymbol{\theta}) = I_{\text{bg}} + \sum_{j=1}^n A_j \exp\left( -\frac{(x - x_j)^2 + (y - y_j)^2}{2 \sigma_{\text{psf}}^2} \right)$$

donde el vector de parámetros a optimizar es:
$$\boldsymbol{\theta} = \left[ I_{\text{bg}}, A_1, x_1, y_1, A_2, x_2, y_2, \dots, A_n, x_n, y_n \right] \in \mathbb{R}^{3n + 1}$$

La función de pérdida cuadrática ponderada (*chi-cuadrado*) a minimizar es:

$$\chi^2(\boldsymbol{\theta}) = \sum_{u, v \in \Omega} \left[ I(x_u, y_v) - I_{\text{model}}(x_u, y_v; \boldsymbol{\theta}) \right]^2$$

### 5.2 Inicialización Heurística Robusta (k-Means Fotométrico)
Dado que la optimización no lineal mediante el algoritmo de **Levenberg-Marquardt** es propensa a quedar atrapada en mínimos locales si se inicializa aleatoriamente, los centros iniciales $(x_j^{(0)}, y_j^{(0)})$ se determinan calculando los momentos de inercia y autovectores del tensor de segundo orden de la mancha:

$$T = \begin{bmatrix} \mu_{xx} & \mu_{xy} \\ \mu_{xy} & \mu_{yy} \end{bmatrix}, \quad \mu_{xx} = \frac{\iint (x - x_c)^2 I(x, y) dx dy}{\iint I(x, y) dx dy}$$

Los autovectores de $T$ definen el eje de elongación del dímero/trímero. Las posiciones iniciales se colocan simétricamente a lo largo de este eje principal espaciadas a una distancia inicial $d_0 \approx 0.5 \sigma_{\text{psf}}$, y las amplitudes iniciales se fijan en $A_j^{(0)} = I_{\text{max}} / n$.

### 5.3 Restricciones Físicas de Optimización
Para evitar divergencias numéricas:
1. **Positividad de Amplitud:** $A_j > 0$.
2. **Confinamiento Espacial:** $(x_j, y_j) \in \Omega$ (los emisores no pueden escapar de la caja de ajuste).
3. **Separación Mínima:** Si dos centros resueltos colapsan a una distancia $d_{12} < 0.1 \sigma_{\text{psf}}$, el algoritmo fusiona automáticamente las soluciones para evitar sobredimensionamiento paramétrico (*overfitting*).

---

## 6. Métodos Alternativos de Resolución de Cúmulos

PyPrinting 3.0 proporciona tres estrategias seleccionables por el usuario según el objetivo del análisis:

```
                  ┌─────────────────────────────────────┐
                  │      Cúmulo Detectado (n >= 2)      │
                  └──────────────────┬──────────────────┘
                                     │
         ┌───────────────────────────┼───────────────────────────┐
         ▼                           ▼                           ▼
┌──────────────────┐       ┌──────────────────┐       ┌──────────────────┐
│  Multi-Gaussiano │       │  Conservar Nodo  │       │   Fusión Baric.  │
│  (Fit n-Gauss)   │       │  (Nearest Ideal) │       │      (COM)       │
├──────────────────┤       ├──────────────────┤       ├──────────────────┤
│ Resuelve n       │       │ Mantiene el emi- │       │ Condensa el      │
│ emisores indivi- │       │ sor más cercano  │       │ cúmulo en su     │
│ duales con pre-  │       │ al nodo ideal y  │       │ centro de masa   │
│ cisión sub-px.   │       │ purga satélites. │       │ ponderado.       │
│ Óptimo para re-  │       │ Óptimo para fil- │       │ Óptimo para es-  │
│ cuperar vacan-   │       │ trar agregados   │       │ tudios globales  │
│ cias reales.     │       │ de fondo parásito│       │ conservadores.   │
└──────────────────┘       └──────────────────┘       └──────────────────┘
```

1. **Desacople Multi-Gaussiano (`_on_resolve_selected_cluster_gaussian`):** Reemplaza el cúmulo por los $n$ emisores individuales calculados en la optimización. Es el método más riguroso para recuperar vacancias legítimas.
2. **Conservar Nodo de Red (`_on_resolve_selected_cluster_nearest`):** Identifica el nodo ideal $(X_u, Y_v)$ de la red periódica más cercano al cúmulo y conserva únicamente la partícula con menor distancia euclidiana:
   $$j^* = \arg\min_j \| \mathbf{r}_j - \mathbf{R}_{\text{ideal}} \|$$
   descartando los emisores restantes como impurezas de impresión o satélites espurios.
3. **Fusión en Centro de Masa (`_on_resolve_selected_cluster_com`):** Fusiona todas las partículas del grupo en un único punto ponderado por su brillo fotométrico:
   $$\mathbf{r}_{\text{COM}} = \frac{\sum_j I_j \mathbf{r}_j}{\sum_j I_j}$$

---

## 7. Fase 4: Ajuste de Cuadrícula Óptima, Vacancias y Regla de Consistencia

Una vez curadas y desacopladas las partículas, se procede al ajuste de la red cristalina en el espacio real para catalogar qué sitios están ocupados y cuáles corresponden a vacancias reales.

### 7.1 Algoritmo de Ajuste de Cuadrícula Bounded
Dadas las $M$ partículas curadas con coordenadas $\{\mathbf{r}_k\}_{k=1}^M$, se optimizan el origen de la red $(x_0, y_0)$ y la rotación angular $\theta$:

$$\min_{x_0, y_0, \theta} \sum_{k=1}^M \min_{u, v} \| \mathbf{r}_k - \mathbf{R}_{u, v}(x_0, y_0, \theta) \|^2$$

donde los sitios ideales de la red cuadrada son:
$$\mathbf{R}_{u, v} = \begin{bmatrix} x_0 \\ y_0 \end{bmatrix} + \begin{bmatrix} \cos\theta & -\sin\theta \\ \sin\theta & \cos\theta \end{bmatrix} \begin{bmatrix} u \cdot a_x \\ v \cdot a_y \end{bmatrix}, \quad u, v \in \{0, 1, \dots, N-1\}$$

### 7.2 Localización Biyectiva de Vacancias (KDTree Acotado)
Para cada uno de los $N^2$ sitios teóricos $\mathbf{R}_{u, v}$:
1. Se consulta el árbol KDTree de partículas curadas buscando vecinos en un radio máximo de captura acotado a la mitad de la celda unitaria:
   $$r_{\text{capture}} = \frac{a_{\text{mean}}}{2}$$
2. Si un nodo $\mathbf{R}_{u, v}$ **no posee ninguna partícula dentro de $r_{\text{capture}}$**, se declara formalmente como **Vacancia Reticular**:
   $$\text{Sitio } (u, v) \in \mathcal{V}_{\text{vacancies}} \iff \min_{k} \| \mathbf{r}_k - \mathbf{R}_{u, v} \| > \frac{a_{\text{mean}}}{2}$$
3. La fracción de vacancias experimental $f_{\text{vac}}$ es:
   $$f_{\text{vac}} = p = \frac{|\mathcal{V}_{\text{vacancies}}|}{N^2}$$

### 7.3 Regla Metrológica de Consistencia Física
Para garantizar que el algoritmo no genere ni destruya sitios reticulares de forma espuria, se define la **condición de cierre de conservación reticular**:

$$\boxed{M_{\text{curadas}} + n_{\text{vac}} \le N^2 \cdot \left(1 + \frac{\text{margen}}{100}\right)}$$

donde:
- $M_{\text{curadas}}$: Número de partículas físicas curadas activas en la muestra.
- $n_{\text{vac}}$: Número de vacancias detectadas mediante el KDTree acotado.
- $N^2$: Número total nominal de sitios en la red $N \times N$.
- $\text{margen}$: Margen de tolerancia admisible (por defecto $10\%$) para absorber efectos de borde o partículas satélite periféricas.

#### Dictamen de Consistencia en la GUI:
- **Consistente (Verde):** Si $M_{\text{curadas}} + n_{\text{vac}} \approx N^2$, el sistema certifica que cada nodo de la red ha sido clasificado biyectivamente como ocupado o vacante.
- **Inconsistente / Alerta (Rojo):** Si la suma excede el margen permitido ($M + n_{\text{vac}} \gg N^2$), el software alerta al usuario de que aún existen cúmulos no desacoplados, impurezas sin filtrar o que el tamaño nominal $N$ no coincide con la región analizada.

---

## 8. Impacto Metrológico en los Reportes y Pistas Cruzadas

La correcta ejecución de la curación fotométrica repercute de forma directa y decisiva en todos los análisis posteriores de la muestra:

1. **En la Función de Distribución Radial $g(r)$:**
   Al desacoplar dímeros sub-difraccionales, desaparecen los picos espurios a distancias $r < 250\ \text{nm}$, restaurando la meseta de exclusión estérica limpia ($g(r) \approx 0$ para $r < d_{\text{min}}$) requerida por el modelo físico (ver [[CAT-304_Metrologia_Experimental_Conchas_Coordinacion_gr_Redes_2D]]).
2. **En la Intensidad Coherente de Debye-Waller:**
   La determinación exacta de la fracción de vacancias $p$ es indispensable para calcular la curva de atenuación teórica $H(q) \propto (1 - p)^2 \exp(-q^2 \sigma^2)$. Una sobreestimación de vacancias deprimiría falsamente el factor $(1-p)^2$, llevando a subestimar el desorden real $\sigma$ (ver [[CAT-305_Derivacion_Matematica_Factor_Estructura_Debye_Waller]]).
3. **En el Estándar de Oro Analítico $H_2 / H_1$:**
   Al eliminar emisiones dobles y artefactos de centroide, los picos de difracción armónicos $(2, 0)$ y $(1, 0)$ reflejan el desorden genuino del cristal, permitiendo la inversión analítica instantánea sin desvíos sistemáticos (ver [[CAT-308_Metrologia_Analitica_Directa_Picos_Bragg_Fourier_2D]]).

---

## 9. Referencias y Literatura Especializada

1. **Picasso (Super-Resolution Software):** Schnitzbauer, J., Strauss, M. T., Schlichthaerle, T., Schueder, F., & Jungmann, R. (2017). *Super-resolution microscopy with DNA-PAINT and Exchange-PAINT.* Nature Protocols, 12(6), 1198-1228.
2. **Trackpy Particle Tracking:** Allan, D. B., Caswell, T., Keim, N. C., van der Wel, C. M., & Verweij, R. W. (2021). *Trackpy: Fast, Flexible Particle-Tracking Analysis in Python.* Zenodo.
3. **Algoritmo de Crocker-Grier:** Crocker, J. C., & Grier, D. G. (1996). *Methods of digital video microscopy for colloidal studies.* Journal of Colloid and Interface Science, 179(1), 298-310.
4. **Optimización de Levenberg-Marquardt:** Moré, J. J. (1978). *The Levenberg-Marquardt algorithm: implementation and theory.* In Numerical Analysis (pp. 105-116). Springer, Berlin, Heidelberg.
5. **Teorema de Green y Polígonos de Nivel:** Green, G. (1828). *An Essay on the Application of Mathematical Analysis to the Theories of Electricity and Magnetism.* Nottingham.
