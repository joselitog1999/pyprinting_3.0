# Curación Fotométrica, Desacople Multi-Gaussiano y Reglas de Consistencia Reticular en Redes 2D

**Proyecto:** PyPrinting 3.0 — Nanofotónica y Fabricación Óptica  
**Laboratorio:** Nanofotónica — Instituto de Nanosistemas (INS - UNSAM / CONICET)  
**Autor:** José Luis González Peñafiel (*Becario Doctoral CONICET*)  
**Fecha de Publicación:** Septiembre 2026  
**Módulos Asociados:** `core/lattice_disorder.py`, `core/localization_pipeline.py`, `analysis/lattice_disorder_gui.py`  
**Pilares Wiki:** [[CAT-201_Deconvolucion_Optica_Richardson_Lucy_y_Tracking_Trackpy]], [[CAT-307_Computacion_NUFFT_Factor_Estructura_Optimizacion_BLAS]]  
**Notas Relacionadas:**  
- [[CAT-301_Algoritmos_Espacio_Real_KDTree_Asignacion_Monte_Carlo]]  
- [[CAT-201_Deconvolucion_Optica_Richardson_Lucy_y_Tracking_Trackpy]]  
- [[CAT-206_Pipeline_SMLM_Picasso_Algoritmos_y_Deconvolucion]]  
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

### 4.2 Criterio de Binarización: del Umbral de Intensidad Plano al Laplaciano de Gaussiana (LoG)

**Actualización (unificación de criterios):** la inspección de punto sospechoso (`inspect_single_spot_photometry()`) delimitaba originalmente el contorno de iso-intensidad mediante un corte biseccional de intensidad plano, $I_{\text{th}} = I_{\text{bg}} + \theta(I_{\max}-I_{\text{bg}})$ (§4, ecuación de $I_{\text{th}}$ arriba) — un criterio geométrico que ignora por completo la forma de la PSF calibrada. El detector de aglomerados multi-partícula (`detect_clusters_and_chains()`, método `'laplacian'`) ya usaba en cambio un criterio distinto y más robusto: el **operador Laplaciano de Gaussiana** ($-\nabla^2$, LoG),

$$\Lambda(x,y) = -\nabla^2\big[G_\sigma * I\big](x,y) = -\,\text{gaussian\_laplace}\!\big(I(x,y);\,\sigma_{\text{psf}}\big)$$

que actúa como filtro adaptado (*matched filter*) a la escala espacial de un emisor puntual difraccional: su respuesta es máxima exactamente sobre el centro de una mancha gaussiana de ancho $\sigma_{\text{psf}}$ y decae/cambia de signo hacia afuera, delimitando naturalmente la extensión física real del emisor en vez de un corte arbitrario de intensidad.

**Ambos criterios están unificados desde esta revisión**: `inspect_single_spot_photometry()` ahora aplica el mismo operador LoG sobre el parche local, binarizando por cruce por cero ($\Lambda > 0$, equivalente a `threshold_pct<=0`) o por un umbral porcentual del pico del LoG — exactamente el mismo criterio, con los mismos parámetros de control, que `detect_clusters_and_chains()` ya usaba para cúmulos. El área de referencia del monómero se unificó en consecuencia:

$$A_0 = 2\pi\,\sigma_{\text{psf}}^2$$

la misma fórmula que `detect_clusters_and_chains()` usa internamente (`A_lap_0`), reemplazando la convención previa y distinta $A_0 = \pi(2\sigma_{\text{psf}})^2 = 4\pi\sigma_{\text{psf}}^2$ que sólo existía en la inspección de punto sospechoso. **Nota metrológica**: una derivación puramente analítica del cruce por cero del LoG aplicado a un blob gaussiano YA convolucionado (varianzas que se suman) da $r_0 = 2\sigma_{\text{psf}}$, distinto del cruce por cero del kernel LoG puro ($r_0=\sqrt{2}\sigma_{\text{psf}}$); se optó deliberadamente por mantener el criterio $A_0=2\pi\sigma_{\text{psf}}^2$ ya validado y en producción en el detector de cúmulos como referencia única del software, en vez de introducir una segunda convención "más pura" analíticamente pero divergente del resto del código — la trazabilidad de una única convención consistente en todo el módulo prevalece sobre la elección entre dos derivaciones igualmente defendibles.

---

## 5. Algoritmo de Desacople Multi-Gaussiano con Enmascaramiento Estricto y Cotas Físicas

Cuando un punto sospechoso o aglomerado es identificado con multiplicidad $n \ge 2$, se resuelve el problema inverso de desacoplar los centros individuales $(x_j, y_j)$ de cada emisor mediante optimización no lineal (Levenberg-Marquardt o Truncated Newton con cotas de caja).

### 5.1 Enmascaramiento Gráfico Estricto ($\text{patch}[\sim\text{mask}] = 0$)
En versiones preliminares, el ajuste multi-gaussiano operaba sobre una caja rectangular delimitadora $\Omega = [-W, W] \times [-H, H]$. Si existían colas difraccionales de partículas vecinas o fluctuaciones del fondo fuera del cúmulo, el ajuste se distorsionaba desplazando artificialmente los centros ajustados.

Para garantizar aislamiento fotométrico absoluto, el algoritmo aplica una **máscara binaria cerrada $\mathcal{M}(x, y) \in \{0, 1\}$** obtenida a partir del contorno de iso-intensidad segmentado:

$$I_{\text{masked}}(x, y) = \begin{cases} I(x, y) & \text{si } (x, y) \in \mathcal{M} \\ 0 & \text{si } (x, y) \notin \mathcal{M} \end{cases}$$

La función de pérdida cuadrática minimizada se restringe exclusivamente a los píxeles interiores al contorno:

$$\chi^2(\boldsymbol{\theta}) = \sum_{(u, v) \in \mathcal{M}} \left[ I(x_u, y_v) - I_{\text{model}}(x_u, y_v; \boldsymbol{\theta}) \right]^2$$

Cualquier señal fuera de la región gráficamente marcada queda estrictamente anulada a cero, erradicando la influencia de partículas adyacentes y fondos espurios.

### 5.2 Restricciones Físicas de Partículas Idénticas (Tolerancia del 30% y $N \ge 2$)
Dado que todas las nanopartículas impresas sobre el sustrato provienen del mismo lote coloidal monodisperso y del mismo proceso litográfico fototérmico, sus propiedades ópticas nominales son físicamente idénticas:
- Amplitud máxima de pico monomérica: $A_0$
- Volumen fotométrico integrado del monómero: $V_0 = 2\pi A_0 \sigma_{\text{psf}}^2$
- Ancho difraccional de la Point Spread Function: $\sigma_{\text{psf}}$

En presencia de la firma calibrada (`signature_dict`), el optimizador impone **cotas rígidas de caja (*box constraints*) del 30%** sobre los parámetros de cada partícula individual $j$:

$$A_j \in [0.70 \cdot A_0, \; 1.30 \cdot A_0]$$
$$\sigma_j \in [0.70 \cdot \sigma_{\text{psf}}, \; 1.30 \cdot \sigma_{\text{psf}}] \quad (\text{o fijado a } \sigma_{\text{psf}})$$

Asimismo, por estricta definición física, **un cúmulo u aglomerado consiste forzosamente en dos o más nanopartículas**:
$$N_{\text{particles}} = \max\left(2, \; \operatorname{round}\left(\frac{V_\Omega}{V_0}\right)\right)$$
Se elimina categóricamente la posibilidad de que un cúmulo colapse matemáticamente a $N=1$.

### 5.3 Confinamiento Geométrico de Centros al Interior del Polígono
Para evitar que algún emisor sea proyectado fuera del área física del cúmulo, se impone la condición de confinamiento geométrico:
$$(x_j, y_j) \in \operatorname{Polygon}(\mathcal{M})$$
acotando los límites de búsqueda en $x$ e $y$ a los extremos del polígono $[x_{\text{min}}^{\text{poly}}, x_{\text{max}}^{\text{poly}}] \times [y_{\text{min}}^{\text{poly}}, y_{\text{max}}^{\text{poly}}]$.

### 5.4 Inicialización Heurística y Semillas Visuales Manuales
La convergencia de la optimización no lineal depende fuertemente de los valores iniciales $\boldsymbol{\theta}^{(0)}$. PyPrinting 3.0 ofrece dos modos de inicialización:
1. **Inicialización Automática (Tensor de Momentos):**
   Calcula los momentos centrales de segundo orden de la mancha:
   $$\mu_{xx} = \frac{\iint_{\mathcal{M}} (x - x_c)^2 I(x, y) dx dy}{\iint_{\mathcal{M}} I(x, y) dx dy}$$
   y distribuye los $N$ centros a lo largo del autovector principal de máxima inercia.
2. **Semillas Visuales Manuales (`manual_visual_seeds_nm`):**
   El operador puede activar el modo **"📍 Marcar Semillas Visuales"** en la GUI y hacer clic directamente sobre los máximos visuales en el visor de espacio real. Las coordenadas marcadas se inyectan directamente como centros iniciales $(x_j^{(0)}, y_j^{(0)})$, permitiendo resolver con alta fidelidad cúmulos complejos con morfología no lineal (p. ej. trímeros en ángulo o cadenas compactas).

---

## 6. Métodos Alternativos, Creación Manual y Actualización Unitaria de Cúmulos

PyPrinting 3.0 proporciona estrategias integrales para la gestión y resolución de cúmulos:

```
                  ┌─────────────────────────────────────┐
                  │      Cúmulo Detectado (n >= 2)      │
                  │   (Automático o Creación Manual)    │
                  └──────────────────┬──────────────────┘
                                     │
         ┌───────────────────────────┼───────────────────────────┐
         ▼                           ▼                           ▼
┌──────────────────┐       ┌──────────────────┐       ┌──────────────────┐
│  Multi-Gaussiano │       │ Marcar Resuelto  │       │   Fusión Baric.  │
│  (Fit n-Gauss)   │       │    (Usuario)     │       │      (COM)       │
├──────────────────┤       ├──────────────────┤       ├──────────────────┤
│ Resuelve n       │       │ Preserva las     │       │ Condensa el      │
│ emisores indivi- │       │ partículas TAL   │       │ cúmulo en su     │
│ duales con pre-  │       │ COMO ESTÁN, sin  │       │ centro de masa   │
│ cisión sub-px y  │       │ modificar datos  │       │ ponderado.       │
│ cotas del 30%.   │       │ — sólo confirma  │       │ Óptimo para es-  │
│ Óptimo para re-  │       │ revisión visual. │       │ tudios globales  │
│ cuperar vacan-   │       │                  │       │ conservadores.   │
│ cias reales.     │       │                  │       │                  │
└──────────────────┘       └──────────────────┘       └──────────────────┘
```

1. **Desacople Multi-Gaussiano (`_on_resolve_selected_cluster_gaussian` / `_on_resolve_all_clusters_gaussian`):** Reemplaza el cúmulo por los $N$ emisores individuales desacoplados.
2. **Marcar como Resuelto por Usuario (`_on_mark_cluster_resolved_manual`, menú contextual de la tabla de cúmulos):** Confirma la revisión visual de un cúmulo **sin modificar ninguna partícula** — reemplazó a la acción "Conservar Nodo de Red" de versiones anteriores (que dependía de un ajuste de grilla `kdtree_results` todavía inexistente en esta etapa temprana del flujo de trabajo, en la Pestaña 1: medir distancia a un nodo ideal en $(0,0)$ carecía de sentido físico antes de ajustar la red). El operador que quiera efectivamente filtrar satélites contra una red ya ajustada dispone de `resolve_clusters_dataframe(action='keep_nearest')` como función de `core/lattice_disorder.py` reutilizable desde otros flujos, aunque ya no está expuesta como acción de UI en esta pestaña.
3. **Descartar Cúmulo (`_on_discard_cluster`, menú contextual):** Remueve el agrupamiento de la tabla sin tocar `locs_df` — las partículas siguen existiendo, sólo dejan de estar agrupadas (reaparecerán si se repite la detección).
4. **Creación de Cúmulo Manual (`create_manual_cluster`):**
   Permite al usuario seleccionar arbitrariamente 2 o más partículas que no fueron agrupadas por el análisis de grafos y forzar su condensación en un cúmulo analítico con contorno fotométrico, cálculo de estequiometría $N \ge 2$ y representación en la tabla de aglomerados.
5. **Superposición de Deconvolución Richardson-Lucy (RL):**
   La imagen deconvolucionada se proyecta como una capa interactiva superpuesta en el visor de espacio real (`self.img_item_rl`, $z=2$) gobernada por la casilla `chk_overlay_rl`. Esto permite al usuario contrastar visualmente los centros atómicos resueltos frente a los picos de difracción re-enfocados antes y después del desacople. **Nunca combinar con el motor de localización Picasso** — ver [[CAT-206_Pipeline_SMLM_Picasso_Algoritmos_y_Deconvolucion]] para la justificación estadística completa (la deconvolución rompe la independencia inter-píxel que la verosimilitud de Poisson de Picasso requiere).

### 6.1 Actualización Unitaria: IDs de Partícula Estables

Las acciones de resolución individual (ítems 1-3 arriba) **ya no anulan la tabla completa de cúmulos** al resolver uno solo. Cada partícula recibe un `particle_id` monótono asignado una única vez, al cargar/detectar el conjunto RAW completo — nunca reutilizado, ni siquiera tras eliminar una partícula o deshacer una acción (el ID queda reservado hasta que una restauración lo trae de vuelta con el mismo valor). Los cúmulos referencian sus miembros por `particle_id` en vez de por posición dentro del DataFrame, de modo que sobreviven correctamente a los reindexados de `resolve_clusters_dataframe()`/`resolve_single_spot_multi_gaussian()` (que siempre reconstruyen el DataFrame agregando las partículas nuevas al final). El cúmulo resuelto se marca visualmente en verde y se traslada al final de la tabla, dejando los pendientes al principio para permitir curación continua sin perder el resto del trabajo de detección ya realizado.

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
