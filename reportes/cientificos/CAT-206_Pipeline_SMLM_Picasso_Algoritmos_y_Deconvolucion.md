# CAT-206: Pipeline SMLM — Picasso (GaussLQ/GaussMLE) vs. Trackpy+Richardson-Lucy, y la Incompatibilidad Fundamental entre Deconvolución Iterativa y Estimación de Máxima Verosimilitud

**Proyecto:** PyPrinting 3.0 — Nanofotónica y Fabricación Óptica
**Laboratorio:** Nanofotónica — Instituto de Nanosistemas (INS-UNSAM / CONICET)
**Autor:** José Luis González Peñafiel (*Becario Doctoral CONICET*)
**Módulos Asociados:** `modules/camera.py` (`TrackpyDialog`), `analysis/lattice_disorder_gui.py`, `core/localization_pipeline.py`
**Pilares Wiki:**
- [[CAT-201_Deconvolucion_Optica_Richardson_Lucy_y_Tracking_Trackpy]] — formulación completa de Richardson-Lucy y Trackpy en `analysis/image_analyzer.py`
- [[CAT-202_Derivacion_Matematica_Cota_Cramer_Rao_Localizacion_Optica]] — derivación formal de la cota de Cramér-Rao (CRLB)
- [[CAT-204_Curacion_Fotometrica_Desacople_MultiGaussiano_Consistencia]] — consumo de las localizaciones curadas río abajo

---

## 1. Resumen Ejecutivo

PyPrinting 3.0 ofrece dos motores de localización de partículas mutuamente exclusivos en la Pestaña 1 del Analizador de Desorden 2D (`combo_motor`): **Picasso** (`GaussLQ`/`GaussMLE`, diseñado para microscopía de localización de molécula única — SMLM/PALM/STORM/DNA-PAINT) y **Trackpy** (Crocker-Grier, diseñado para seguimiento de partículas en campo claro o dispersión). Ambos motores conviven en el mismo software porque resuelven el mismo problema —encontrar centroides sub-píxel— bajo modelos estadísticos de ruido radicalmente distintos, y esa diferencia tiene una consecuencia metrológica estricta: **la deconvolución iterativa de Richardson-Lucy (RL) puede aplicarse como pre-filtro antes de Trackpy, pero JAMÁS antes de Picasso**, porque RL destruye la independencia estadística inter-píxel que la estimación de máxima verosimilitud (MLE) de Picasso asume por construcción — invalidando tanto el resultado como la propia cota de Cramér-Rao (CRLB) que motiva usar MLE en primer lugar.

Esta regla no es solo una recomendación operativa: está **impuesta arquitectónicamente** en el software (§5) — la casilla de deconvolución RL (`chk_rl`) sólo existe físicamente en la página de controles de Trackpy del `QStackedWidget` de la Pestaña 1; al seleccionar Picasso, esa página (y la casilla) desaparece de la interfaz, y la rama de código de detección para Picasso nunca la consulta.

---

## 2. Dos Modelos de Ruido, Dos Familias de Algoritmos

### 2.1 Trackpy (Crocker-Grier): Detección de Máximos Sobre Imagen Pre-procesada

Trackpy no asume un modelo estadístico explícito por píxel. Opera en dos etapas desacopladas:
1. **Filtrado paso-banda** (`bpass`): resta un fondo de baja frecuencia y suaviza ruido de alta frecuencia — una operación puramente determinística sobre la matriz de intensidad, agnóstica de cómo se generó esa matriz.
2. **Localización de máximos + refinamiento de centroide** (`locate`): identifica máximos locales sobre la imagen filtrada y refina su posición mediante el centro de masas fotométrico local.

Ninguna de las dos etapas invoca una función de verosimilitud por píxel ni una matriz de información de Fisher — Trackpy nunca declara una hipótesis sobre la *distribución estadística* del ruido de cada píxel, solo sobre su *forma espacial* (un pico suave sobre un fondo suave). Por eso, **cualquier pre-procesamiento determinístico que preserve o realce esa forma espacial —incluida la deconvolución RL— es compatible con Trackpy sin invalidar ningún supuesto subyacente** (ver [[CAT-201_Deconvolucion_Optica_Richardson_Lucy_y_Tracking_Trackpy]] §4 para la inversión de imagen de valles y los parámetros de filtrado).

### 2.2 Picasso (GaussLQ / GaussMLE): Estimación de Máxima Verosimilitud Bajo Ruido de Poisson Explícito

Picasso resuelve el problema inverso de forma completamente distinta: postula un modelo generativo explícito del conteo de fotones en cada píxel del parche $\Omega$ alrededor de un candidato,

$$I(x_i, y_j) \sim \mathcal{P}\big(\lambda(x_i, y_j;\, \boldsymbol{\theta})\big), \qquad \lambda(x,y;\boldsymbol{\theta}) = b + A \exp\!\left(-\frac{(x-x_0)^2+(y-y_0)^2}{2\sigma^2}\right)$$

donde $\boldsymbol{\theta}=(x_0, y_0, A, \sigma, b)$ son los parámetros del emisor y $\lambda$ es la tasa esperada de fotones (parámetro de la distribución de Poisson) en cada píxel. **La independencia estadística entre píxeles es un supuesto explícito y necesario**: la verosimilitud conjunta del parche completo se factoriza como el producto de las verosimilitudes individuales,

$$\mathcal{L}(\boldsymbol{\theta}) = \prod_{(i,j)\in\Omega} P\big(I(x_i,y_j) \mid \lambda(x_i,y_j;\boldsymbol{\theta})\big) = \prod_{(i,j)\in\Omega} \frac{\lambda(x_i,y_j;\boldsymbol{\theta})^{I(x_i,y_j)} e^{-\lambda(x_i,y_j;\boldsymbol{\theta})}}{I(x_i,y_j)!}$$

Esta factorización **sólo es válida si los conteos de fotones en píxeles distintos son variables aleatorias independientes** — una hipótesis físicamente razonable para fotones que llegan al detector directamente desde la óptica del microscopio (cada fotón se registra en un único píxel del sensor, sin mezclarse con sus vecinos por ningún proceso posterior), pero que dejará de sostenerse si la imagen se somete a cualquier operación que mezcle intensidad entre píxeles vecinos después de la adquisición (§3).

#### 2.2.1 GaussMLE — Maximización Directa de la Log-Verosimilitud de Poisson

Tomando el logaritmo de $\mathcal{L}(\boldsymbol{\theta})$ y descartando el término $\ln(I!)$ (independiente de $\boldsymbol{\theta}$), GaussMLE maximiza numéricamente

$$\hat{\boldsymbol{\theta}}_{\text{MLE}} = \arg\max_{\boldsymbol{\theta}} \sum_{(i,j)\in\Omega} \Big[ I(x_i,y_j)\ln\lambda(x_i,y_j;\boldsymbol{\theta}) - \lambda(x_i,y_j;\boldsymbol{\theta}) \Big]$$

mediante un esquema iterativo de Newton-Raphson (o Levenberg-Marquardt adaptado a Poisson) implementado en Picasso con vectorización BLAS. Este es el estimador que, bajo la hipótesis de independencia píxel-a-píxel, **alcanza asintóticamente la cota de Cramér-Rao** — el límite de precisión fundamental derivado en [[CAT-202_Derivacion_Matematica_Cota_Cramer_Rao_Localizacion_Optica]] a partir de la matriz de información de Fisher $\mathcal{I}(\boldsymbol{\theta}) = \mathbb{E}\left[-\partial^2 \ln\mathcal{L}/\partial\boldsymbol{\theta}^2\right]$, cuya derivación **también asume explícitamente independencia entre píxeles** para poder sumar la información de Fisher de cada píxel individualmente.

#### 2.2.2 GaussLQ — Mínimos Cuadrados Ponderados (Aproximación Rápida)

GaussLQ resuelve en cambio un problema de mínimos cuadrados ponderados,

$$\hat{\boldsymbol{\theta}}_{\text{LQ}} = \arg\min_{\boldsymbol{\theta}} \sum_{(i,j)\in\Omega} \frac{\big[I(x_i,y_j) - \lambda(x_i,y_j;\boldsymbol{\theta})\big]^2}{\lambda(x_i,y_j;\boldsymbol{\theta})}$$

(el peso $1/\lambda$ aproxima la varianza local de una variable de Poisson, $\text{Var}[I]=\lambda$). Esta es una **aproximación Gaussiana a la verosimilitud de Poisson exacta**, válida asintóticamente cuando $\lambda$ es suficientemente grande (régimen de alto conteo fotónico, donde la distribución de Poisson tiende a una Gaussiana por el teorema central del límite) — computacionalmente más barata que GaussMLE (no requiere iterar la verosimilitud exacta), a costa de una precisión ligeramente sub-óptima frente al CRLB a bajo SNR. **Este método hereda el mismo supuesto de independencia inter-píxel** que GaussMLE, por la misma razón: el peso $1/\lambda$ por píxel sólo tiene sentido como una aproximación de varianza LOCAL e independiente.

---

## 3. Por Qué Richardson-Lucy Rompe la Independencia Estadística Que Picasso Necesita

Richardson-Lucy es, en sí mismo, un algoritmo de **estimación de máxima verosimilitud bajo ruido de Poisson**, aplicado no a un puñado de parámetros $(x_0,y_0,A,\sigma,b)$ sino a la imagen COMPLETA vista como un campo de intensidad desconocido $J(\vec r)$ (ver [[CAT-201_Deconvolucion_Optica_Richardson_Lucy_y_Tracking_Trackpy]] §2.2 para la derivación bayesiana completa). Cada iteración,

$$\hat{J}^{(k+1)}(\vec r) = \hat{J}^{(k)}(\vec r) \cdot \left[ \left( \frac{I(\vec r)}{\hat{J}^{(k)} * K(\vec r)} \right) * K^*(-\vec r) \right]$$

**redistribuye intensidad entre píxeles vecinos ponderada por el kernel de la PSF** $K$: el valor de salida en un píxel dado depende explícitamente de los valores de entrada en TODOS los píxeles dentro del soporte espacial de $K$ centrado en su vecindad (típicamente varios píxeles de radio, $\sim 2$-$3\,\sigma_{\text{psf}}$). Esto introduce **covarianza entre píxeles de salida igual al soporte de autocorrelación de la PSF**:

$$\text{Cov}\big[\hat{J}(\vec r_1), \hat{J}(\vec r_2)\big] \neq 0 \quad \text{siempre que } |\vec r_1 - \vec r_2| \lesssim \text{soporte}(K)$$

incluso si el ruido de entrada $I(\vec r)$ era estadísticamente independiente píxel-a-píxel antes de deconvolucionar. Esto **no es un defecto de implementación** — es una consecuencia matemática inevitable de cualquier operación de deconvolución que use información de vecindad espacial, y es exactamente el mecanismo por el cual RL logra su propósito (recuperar frecuencias espaciales atenuadas por la difracción): al hacerlo, mezcla información entre píxeles vecinos por diseño.

### 3.1 Consecuencia sobre Picasso

Si se alimenta la imagen post-RL a GaussMLE/GaussLQ:

1. **La factorización de la verosimilitud deja de ser válida.** $\mathcal{L}(\boldsymbol{\theta}) = \prod_{(i,j)} P(I_{ij} \mid \lambda_{ij})$ asumía píxeles independientes; con covarianza inducida, la verosimilitud CORRECTA requeriría la distribución conjunta completa (una Poisson multivariada correlacionada, computacionalmente intratable y que Picasso no calcula). Picasso sigue maximizando la factorización INCORRECTA como si los píxeles fueran independientes — el resultado $\hat{\boldsymbol{\theta}}$ ya no es el estimador de máxima verosimilitud de los datos reales.
2. **El CRLB reportado queda sesgado optimistamente.** La matriz de información de Fisher que Picasso calcula para reportar la incertidumbre de cada localización se deriva, igual que la verosimilitud, bajo el supuesto de independencia — con covarianza real no nula pero no modelada, la información de Fisher aparente es sistemáticamente MAYOR que la información real disponible en los datos, así que el $\sigma_{\text{CRLB}}$ reportado es **artificialmente más chico** de lo que la precisión real permite. El resultado combina un centro potencialmente sesgado con una incertidumbre reportada que subestima el error real — la peor combinación posible desde el punto de vista metrológico: parece más preciso de lo que es, sin ninguna señal de alerta visible en la interfaz.
3. **Trackpy no sufre este problema** porque nunca invoca una verosimilitud por píxel ni una matriz de información de Fisher — su noción de "centroide" es un momento fotométrico determinístico, robusto frente a cualquier redistribución suave de intensidad entre vecinos (de hecho, esa es precisamente la propiedad que hace útil combinar RL con Trackpy: RL afila el pico, Trackpy encuentra su centroide, sin que ninguna de las dos etapas dependa de independencia estadística inter-píxel).

---

## 4. Cuadro Comparativo

| | **Trackpy + RL (opcional)** | **Picasso GaussLQ/GaussMLE** |
|---|---|---|
| Modelo de ruido asumido | Ninguno explícito (forma espacial only) | Poisson explícito, independiente por píxel |
| Compatible con pre-filtrado que mezcla vecinos (RL) | Sí — no invalida ningún supuesto | **No** — rompe la independencia que MLE/CRLB requieren |
| Estimador | Centroide fotométrico (momento) | Máxima verosimilitud (MLE) / mín. cuadrados ponderados (LQ) |
| Alcanza la cota de Cramér-Rao | No aplica (no es un estimador MLE) | Sí, **sólo si los píxeles son realmente independientes** |
| Caso de uso típico en el laboratorio | Campo claro, dispersión, valles de contraste de fase | SMLM/DNA-PAINT, fluorescencia de molécula única |

---

## 5. Guardarraíl Arquitectónico Ya Implementado en PyPrinting 3.0

La regla anterior no depende de la disciplina del operador — está **impuesta por la propia arquitectura de la interfaz** en `analysis/lattice_disorder_gui.py`:

- El selector de motor (`combo_motor`) alimenta un `QStackedWidget` (`stack_motor`) con una página independiente por motor (`_on_motor_changed()` simplemente hace `stack_motor.setCurrentIndex(idx)`).
- La casilla de deconvolución Richardson-Lucy (`chk_rl`, "Pre-filtrado Deconvolución Richardson-Lucy") se construye y se agrega **únicamente** a la página de Trackpy (`page_trackpy`/`lay_tp`) — al seleccionar Picasso, esa página completa queda fuera de vista y `chk_rl` es inalcanzable desde la interfaz.
- En la rama de despacho de detección, el bloque `if motor_idx == 0: # Picasso` nunca lee `self.chk_rl` en absoluto; sólo la rama `else: # Trackpy` lo consulta (`core/localization_pipeline.py::localize_trackpy` recibe `img_to_process`, que sólo se reemplaza por `self.image_rl` dentro de esa rama).

En consecuencia, no existe ningún camino de la interfaz por el cual un operador pueda, sin editar código, aplicar Richardson-Lucy y luego correr Picasso sobre el resultado — la combinación inválida está estructuralmente excluida, no sólo desaconsejada.

---

## 6. Conclusiones

1. Trackpy y Picasso coexisten en PyPrinting 3.0 porque resuelven regímenes experimentales distintos bajo modelos de ruido distintos — no son intercambiables ni jerárquicos, cada uno es la herramienta correcta para su régimen.
2. Richardson-Lucy es compatible con Trackpy (que no depende de independencia inter-píxel) y **fundamentalmente incompatible** con Picasso GaussLQ/GaussMLE (que sí depende de ella, tanto para la estimación como para el cálculo de la cota de Cramér-Rao que motiva su uso).
3. Esta incompatibilidad no es una cuestión de "buena práctica" sino una consecuencia matemática directa de qué supuestos estadísticos sostiene la verosimilitud que cada algoritmo maximiza — y está reflejada en la propia arquitectura de la interfaz, no sólo en la documentación.

---

## 7. Referencias

1. **Picasso (SMLM):** Schnitzbauer, J., Strauss, M. T., Schlichthaerle, T., Schueder, F., & Jungmann, R. (2017). *Super-resolution microscopy with DNA-PAINT and Exchange-PAINT.* Nature Protocols, 12(6), 1198-1228.
2. **Trackpy / Crocker-Grier:** Crocker, J. C., & Grier, D. G. (1996). *Methods of digital video microscopy for colloidal studies.* Journal of Colloid and Interface Science, 179(1), 298-310.
3. **Cramér-Rao para localización óptica:** Mortensen, K. I., Churchman, L. S., Spudich, J. A., & Flyvbjerg, H. (2010). *Optimized localization analysis for single-molecule tracking and super-resolution microscopy.* Nature Methods, 7(5), 377-381.
4. **Richardson-Lucy:** Richardson, W. H. (1972). *Bayesian-Based Iterative Method of Image Restoration.* J. Opt. Soc. Am., 62(1), 55-59. / Lucy, L. B. (1974). *An iterative technique for the rectification of observed distributions.* The Astronomical Journal, 79, 745.

---

*Reporte Técnico PyPrinting 3.0 — Laboratorio de Nanofotónica, Instituto de Nanosistemas (INS-UNSAM).*
*Autor Principal: José Luis González Peñafiel (Becario Doctoral CONICET).*
