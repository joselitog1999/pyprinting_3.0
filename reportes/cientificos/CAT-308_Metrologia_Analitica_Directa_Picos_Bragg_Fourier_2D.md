# Metrología Analítica Directa de Picos de Bragg en Espacio Recíproco 2D
## Inversión Analítica en Forma Cerrada, Cancelación de Parámetros Instrumentales y Límites de Inestabilidad

---

**Autoría:** Equipo de Metrología Cuántica, Cristalografía Computacional y Fotónica — PyPrinting 3.0  
**Fecha:** Septiembre 2026  
**Clasificación:** Reporte Científico Especializado / Cristalografía y Óptica de Fourier  
**Estado:** Producción / Consolidado  
**Documentos Vinculados:**  
- [[CAT-305_Derivacion_Matematica_Factor_Estructura_Debye_Waller]] (Derivación fundamental de $S(\mathbf{q})$ y atenuación exponencial)  
- [[CAT-307_Computacion_NUFFT_Factor_Estructura_Optimizacion_BLAS]] (Cálculo no equiespaciado de alto rendimiento $O(M \log M)$)  
- [[CAT-309_Teoria_Paracristal_Hosemann_Perdida_Orden_2D]] (Desorden acumulativo Tipo II vs Tipo I)  
- [[CAT-304_Metrologia_Experimental_Conchas_Coordinacion_gr_Redes_2D]] (Contrapeso en espacio real: $g(r)$ y $\sigma_{\text{rdf}} = \sigma_{\text{pos}}\sqrt{2}$)  

---

### Resumen Ejecutivo

En la caracterización metrológica de nanopatrones periódicos 2D mediante microscopía óptica de super-resolución (SMLM, PALM/STORM) o microscopía electrónica/fuerza atómica (AFM), la cuantificación del desorden posicional térmico o estocástico ($\sigma_{\text{pos}}$) tradicionalmente ha dependido de **curvas de calibración sintéticas** mediante simulaciones de Monte Carlo. Aunque dicho método numérico es el estándar de oro para geometrías arbitrarias y regímenes de fuerte desorden, introduce una dependencia computacional pesada que impide diagnósticos en tiempo real durante la síntesis óptica.

Este reporte formaliza las **soluciones analíticas en forma cerrada** que emergen al estudiar las relaciones algebraicas entre las intensidades de los picos de difracción de Bragg en el factor de estructura $S(\mathbf{q})$. Se demuestra rigurosamente cómo el cociente de intensidades entre armónicos axiales ($H_2 / H_1$) y el cociente axial-diagonal ($H_{\text{diag}} / H_1$) eliminan algebraicamente la población total de emisores ($N_{\text{total}}$), el número de localizaciones detectadas ($N_{\text{det}}$) y la fracción de vacancias ($p$), permitiendo la extracción determinística de $\sigma_{\text{pos}}$ sin calibración previa. Asimismo, se evalúa la inestabilidad patológica del cociente $H_1 / H_0$, se desarrolla la regresión multilogarítmica (Gráfico de Wilson 2D) para desacoplar $p$ y $\sigma_{\text{pos}}$, y se fijan los criterios de corte de relación señal-ruido ($\text{SNR}$) y desorden crítico ($\sigma_{\text{pos}} / a \le 0.15$) donde la aproximación analítica debe ceder ante el ajuste estocástico Monte Carlo.

---

```
                       ESPACIO RECÍPROCO 2D (BRAGG)
                       
              q_y ^
                  |         H_2 (0, 2q_1)
                  |           *
                  |           |
                  |         H_1 (0, q_1)    H_diag (q_1, q_1)
                  |           * -------------- *
                  |           |              /
                  |           |             /
                  |         H_0 (0,0)      /
                  +-----------*-----------*------> q_x
                              |         H_1 (q_1, 0)
                              |
     Relaciones Analíticas:
       * H_2 / H_1       --> Cancela N y p  ==>  sigma_pos determinístico
       * H_diag / H_1    --> Valida isotropía espacial
       * H_1 / H_0       --> Inestable (mezcla p con sigma y sufre ruido DC)
       * Wilson Plot     --> Regresión multiorigen (desacopla p de sigma)
```

---

## 1. Fundamentos del Factor de Estructura con Desorden Gaussiano y Vacancias

Sea un cristal bidimensional ideal definido por una red de Bravais periódica:
$$\mathbf{R}_{mn} = m a\,\hat{\mathbf{x}} + n b\,\hat{\mathbf{y}}, \quad m,n \in \mathbb{Z}$$
donde para una red cuadrada homogénea consideramos constante de red $a = b$.

En un sistema real sujeto a perturbaciones térmicas, vibracionales o estocásticas de fabricación (polimerización óptica por dos fotones, autoensamblado o nanolitografía), cada sitio ocupado experimenta un desplazamiento aleatorio $\mathbf{\delta}_{mn} = (\delta x_{mn}, \delta y_{mn})$. Asumiendo desorden posicional isotrópico de tipo Gaussiano no correlacionado (Desorden de Debye-Waller o Tipo I):
$$\langle \delta x \rangle = \langle \delta y \rangle = 0, \quad \langle \delta x^2 \rangle = \langle \delta y^2 \rangle = \sigma_{\text{pos}}^2, \quad \langle \mathbf{\delta}^2 \rangle = 2\sigma_{\text{pos}}^2$$

Adicionalmente, se modela la presencia de defectos puntuales (vacancias o sitios no funcionalizados) mediante variables de ocupación de Bernoulli $c_{mn} \in \{0, 1\}$, con probabilidad de vacancia $p \in [0, 1)$ y probabilidad de ocupación $(1-p)$:
$$\langle c_{mn} \rangle = 1 - p, \quad \langle c_{mn} c_{m'n'} \rangle = \begin{cases} 1-p & \text{si } (m,n)=(m',n') \\ (1-p)^2 & \text{si } (m,n)\neq (m',n') \end{cases}$$

El factor de estructura experimental $S(\mathbf{q})$ normalizado por el número total de sitios detectados $N_{\text{det}} = (1-p)N_{\text{total}}$ está dado por:
$$S(\mathbf{q}) = \frac{1}{N_{\text{det}}} \left| \sum_{j=1}^{N_{\text{det}}} e^{-i \mathbf{q} \cdot \mathbf{r}_j} \right|^2$$

Al promediar sobre el ensamble estocástico de desplazamientos y ocupaciones, la función se descompone exactamente en dos componentes:
$$\langle S(\mathbf{q}) \rangle = S_{\text{Bragg}}(\mathbf{q}) + S_{\text{difuso}}(\mathbf{q})$$

donde:
$$S_{\text{Bragg}}(\mathbf{q}) = (1-p) \, e^{-|\mathbf{q}|^2 \sigma_{\text{pos}}^2} \frac{1}{N_{\text{total}}} \left| \sum_{mn} e^{-i \mathbf{q} \cdot \mathbf{R}_{mn}} \right|^2$$
$$S_{\text{difuso}}(\mathbf{q}) = 1 - (1-p) \, e^{-|\mathbf{q}|^2 \sigma_{\text{pos}}^2}$$

En el límite termodinámico de red infinita, la suma de fases converge a un peine de Dirac en los vectores de la red recíproca $\mathbf{G} \in \Lambda^*$:
$$\frac{1}{N_{\text{total}}} \left| \sum_{mn} e^{-i \mathbf{q} \cdot \mathbf{R}_{mn}} \right|^2 \longrightarrow \frac{(2\pi)^2}{\Omega_{\text{celda}}} \sum_{\mathbf{G}} \delta(\mathbf{q} - \mathbf{G})$$
donde $\Omega_{\text{celda}} = a^2$. En un cristal finito de dimensiones $L_x = N_x a, L_y = N_y a$, los deltas de Dirac se ensanchan como funciones de difracción finita tipo $\left[\frac{\sin(q_x L_x / 2)}{q_x a / 2}\right]^2$, cuya altura máxima en resonancia escala proporcionalmente con el número de sitios del cristal.

---

## 2. Definición y Amplitud de los Picos de Bragg Observables

Los vectores fundamentales de la red recíproca para la red cuadrada son:
$$\mathbf{b}_1 = \left(\frac{2\pi}{a}, 0\right), \quad \mathbf{b}_2 = \left(0, \frac{2\pi}{a}\right)$$
con magnitud fundamental:
$$q_1 = |\mathbf{b}_1| = |\mathbf{b}_2| = \frac{2\pi}{a}$$

Definimos las alturas netas de los picos de Bragg (descontando el fondo difuso incoherente) evaluadas en las frecuencias de resonancia:

| Orden de Reflexión | Índices de Miller $(h, k)$ | Vector Recíproco $\mathbf{G}_{hk}$ | Cuadrado de Momento $|\mathbf{G}|^2$ | Notación de Altura |
| :--- | :---: | :---: | :---: | :---: |
| **Central (DC)** | $(0, 0)$ | $(0, 0)$ | $0$ | $H_0$ |
| **Primer Orden (Axial)** | $(\pm 1, 0), (0, \pm 1)$ | $(\pm q_1, 0), (0, \pm q_1)$ | $q_1^2 = \left(\frac{2\pi}{a}\right)^2$ | $H_1$ |
| **Primer Orden Diagonal** | $(\pm 1, \pm 1)$ | $(\pm q_1, \pm q_1)$ | $2 q_1^2 = 2\left(\frac{2\pi}{a}\right)^2$ | $H_{\text{diag}}$ |
| **Segundo Orden (Axial)** | $(\pm 2, 0), (0, \pm 2)$ | $(\pm 2q_1, 0), (0, \pm 2q_1)$ | $4 q_1^2 = 4\left(\frac{2\pi}{a}\right)^2$ | $H_2$ |

Evaluando la amplitud en el centro de cada pico (restando el fondo difuso local $S_{\text{difuso}}(\mathbf{G})$):
$$H_0 = N_{\text{det}} (1-p)$$
$$H_1 = N_{\text{det}} (1-p) \, \exp\left[-q_1^2 \sigma_{\text{pos}}^2\right] = N_{\text{det}} (1-p) \, \exp\left[-\left(\frac{2\pi}{a}\right)^2 \sigma_{\text{pos}}^2\right]$$
$$H_{\text{diag}} = N_{\text{det}} (1-p) \, \exp\left[-2 q_1^2 \sigma_{\text{pos}}^2\right] = N_{\text{det}} (1-p) \, \exp\left[-2\left(\frac{2\pi}{a}\right)^2 \sigma_{\text{pos}}^2\right]$$
$$H_2 = N_{\text{det}} (1-p) \, \exp\left[-4 q_1^2 \sigma_{\text{pos}}^2\right] = N_{\text{det}} (1-p) \, \exp\left[-4\left(\frac{2\pi}{a}\right)^2 \sigma_{\text{pos}}^2\right]$$

---

## 3. Relaciones Algebraicas y Eliminación de Factores Instrumentales

### 3.1 El Cociente Armónico Axial $H_2 / H_1$ (Solución Óptima Cerrada)

Al formar el cociente entre la altura del armónico de segundo orden $H_2$ y el primer orden $H_1$:
$$\frac{H_2}{H_1} = \frac{N_{\text{det}} (1-p) \, \exp\left[-4 q_1^2 \sigma_{\text{pos}}^2\right]}{N_{\text{det}} (1-p) \, \exp\left[-q_1^2 \sigma_{\text{pos}}^2\right]}$$

Nótese la cancelación analítica simultánea de tres cantidades críticas:
1. El factor de escala poblacional $N_{\text{det}}$ (sensible a la ventana de observación del microscopio o ROI).
2. La fracción de defectos o vacancias $(1-p)$.
3. Factores instrumentales multiplicativos de eficiencia cuántica del detector CCD/sCMOS.

El cociente se reduce idénticamente a:
$$\frac{H_2}{H_1} = \exp\left[-(4 - 1) q_1^2 \sigma_{\text{pos}}^2\right] = \exp\left[-3 q_1^2 \sigma_{\text{pos}}^2\right]$$

Tomando el logaritmo natural en ambos miembros:
$$\ln\left(\frac{H_2}{H_1}\right) = -3 q_1^2 \sigma_{\text{pos}}^2 = -3 \left(\frac{2\pi}{a}\right)^2 \sigma_{\text{pos}}^2$$
$$\ln\left(\frac{H_1}{H_2}\right) = 3 \left(\frac{2\pi}{a}\right)^2 \sigma_{\text{pos}}^2 = 12 \frac{\pi^2}{a^2} \sigma_{\text{pos}}^2$$

Despejando analíticamente $\sigma_{\text{pos}}$:
$$\bbox[12px,border:2px solid #2563eb,background:#eff6ff]{
\sigma_{\text{pos}} = \frac{a}{2\pi\sqrt{3}} \sqrt{\ln\left(\frac{H_1}{H_2}\right)} \approx 0.09189 \, a \sqrt{\ln\left(\frac{H_1}{H_2}\right)}
}$$

#### Implicancia Metrológica:
Esta ecuación representa una **inversión analítica exacta**. No requiere simular ninguna red en Monte Carlo, no requiere conocer si la muestra tiene $0\%$ o $40\%$ de vacancias, y es independiente del tamaño de la imagen analizada siempre que la convolución por ventana no distorsione las áreas relativas.

---

### 3.2 El Cociente Axial-Diagonal $H_{\text{diag}} / H_1$ (Test de Isotropía)

En una red 2D físicamente homogénea, las direcciones cristalográficas $[1, 0]$ y $[1, 1]$ deben compartir el mismo tensor de dispersión de Debye-Waller si el desorden es isotrópico. Evaluando el cociente:
$$\frac{H_{\text{diag}}}{H_1} = \frac{N_{\text{det}} (1-p) \, \exp\left[-2 q_1^2 \sigma_{\text{pos}}^2\right]}{N_{\text{det}} (1-p) \, \exp\left[-q_1^2 \sigma_{\text{pos}}^2\right]} = \exp\left[-q_1^2 \sigma_{\text{pos}}^2\right]$$

Tomando logaritmo:
$$\ln\left(\frac{H_1}{H_{\text{diag}}}\right) = q_1^2 \sigma_{\text{pos}}^2 = \left(\frac{2\pi}{a}\right)^2 \sigma_{\text{pos}}^2$$
$$\bbox[12px,border:2px solid #059669,background:#ecfdf5]{
\sigma_{\text{pos}} = \frac{a}{2\pi} \sqrt{\ln\left(\frac{H_1}{H_{\text{diag}}}\right)} \approx 0.15915 \, a \sqrt{\ln\left(\frac{H_1}{H_{\text{diag}}}\right)}
}$$

#### Consistencia Cruzada entre Direcciones:
Comparando las ecuaciones anteriores, en un sistema perfectamente isotrópico y elástico se debe cumplir la relación invariante:
$$\ln\left(\frac{H_1}{H_2}\right) = 3 \, \ln\left(\frac{H_1}{H_{\text{diag}}}\right) \iff \frac{H_1}{H_2} = \left(\frac{H_1}{H_{\text{diag}}}\right)^3 \iff H_2 \cdot H_1^2 = H_{\text{diag}}^3$$

Cualquier desviación significativa de esta igualdad revela anisotropía en el desorden (e.g. deformación uniaxial por deriva térmica en el eje $X$ durante la escritura láser o astigmatismo óptico en la PSF).

---

### 3.3 El Cociente $H_1 / H_0$ y su Inestabilidad Patológica

Un impulso común consiste en normalizar la altura del primer pico frente al pico central $H_0$:
$$\frac{H_1}{H_0} = \frac{N_{\text{det}} (1-p) e^{-q_1^2 \sigma_{\text{pos}}^2}}{N_{\text{det}} (1-p)} = e^{-q_1^2 \sigma_{\text{pos}}^2}$$

Aparentemente, $\sigma_{\text{pos}} = \frac{a}{2\pi}\sqrt{\ln(H_0/H_1)}$. Sin embargo, en la práctica experimental de PyPrinting 3.0 este cociente es **severamente inestable y sesgado** por tres razones fundamentales:

1. **Efecto de Vacancias no Descontadas en DC:**
   Si la normalización se realiza respecto a la energía total $S(\mathbf{0})$, el valor en el origen no solo contiene la coherencia de red sino el término de varianza de ocupación:
   $$S(\mathbf{0})_{\text{total}} = N_{\text{det}} (1-p) + p$$
   Por lo tanto, la presencia de vacancias altera la base del cociente salvo que $p \equiv 0$.

2. **Ruido de Fondo de Frecuencia Cero (Filtro Pasa-Altos y DC Leakage):**
   Cualquier modulación espacial lenta de la iluminación fluorescente, fluorescencia de fondo de la resina o gradiente de autofluorescencia colapsa exactamente en $\mathbf{q} = \mathbf{0}$, elevando artificialmente $H_0$ en varios órdenes de magnitud sobre su valor teórico.

3. **Convolución por Ventana de Apodización (Efecto de Tamaño Finito):**
   La transformada de una ventana rectangular o circular de tamaño $L$ genera un lóbulo central cuya energía residual se desborda en frecuencias bajas pero no afecta a los picos de alta frecuencia ($H_1, H_2$). 

Por ello, el cociente $H_1 / H_0$ se clasifica en PyPrinting 3.0 como **métrico inestable no recomendado** para metrología directa.

---

## 4. Regresión Multiorigen: El Gráfico de Wilson Bidimensional (Wilson Plot 2D Anisótropo)

Cuando se dispone de múltiples reflexiones observables de orden superior $\{\mathbf{G}_{hk}\}$, en lugar de depender exclusivamente de un único cociente de dos picos, es metodológicamente superior formular una regresión lineal multivariada.

Linealizando la intensidad de los picos en función de la norma del vector de Bragg al cuadrado $|\mathbf{G}|^2$:
$$H(\mathbf{G}) = I_0 \, e^{-\sigma_{\text{pos}}^2 |\mathbf{G}|^2}$$
donde $I_0 = N_{\text{det}} (1-p)$. Aplicando logaritmo:
$$\ln[H(\mathbf{G})] = \ln[N_{\text{det}} (1-p)] - \sigma_{\text{pos}}^2 |\mathbf{G}|^2$$

### 4.1 Desacoplamiento Anisótropo en Dimensiones Cartesianas ($X$ e $Y$)
En nanopatrones fabricados mediante litografía láser o barrido piezoeléctrico, las fluctuaciones posicionales presentan anisotropía intrínseca ($\sigma_x \ne \sigma_y$) debido a asimetrías en el perfil del haz láser o derivas mecánicas unidireccionales.

PyPrinting 3.0 descompone la regresión de Wilson en dos ajustes lineales ortogonales independientes:

1. **Eje X (Familia $\{h, 0\}$):**
   $$\ln[H(G_x)] = c_x + m_x G_x^2 \implies \sigma_{w, x} = \sqrt{-m_x}$$
2. **Eje Y (Familia $\{0, k\}$):**
   $$\ln[H(G_y)] = c_y + m_y G_y^2 \implies \sigma_{w, y} = \sqrt{-m_y}$$

El pico diagonal cruzado $(1, 1)$ a $G_{\text{diag}}^2 = G_x^2 + G_y^2$ se incluye como testigo de consistencia 2D.

### 4.2 Anclaje Forzado del Intercepto a $\ln(H_0)$ (Regresión de 1 Parámetro)
La interfaz incluye la opción conmutable **`[x] Anclar Wilson a ln(H₀)`** (`chk_anchor_wilson_h0`):

1. **Modo Libre (Default / 2 Parámetros):**
   Se ajustan pendiente $m$ e intercepto $c$ mediante Mínimos Cuadrados Ordinarios (OLS). Es inmune a la sobreelevación del pico central $H_0$ debida a autofluorescencia o fondo difuso.
2. **Modo Anclado (1 Parámetro):**
   Se fuerza el intercepto al logaritmo natural de la altura del pico central medido:
   $$c_x = c_y = \ln(H_0)$$
   Las pendientes forzadas se deducen analíticamente en forma cerrada:
   $$m_x = \frac{\sum_i G_{xi}^2 \left[ \ln(H_{xi}) - \ln(H_0) \right]}{\sum_i G_{xi}^4}, \quad \sigma_{w, x} = \sqrt{-m_x}$$
   $$m_y = \frac{\sum_i G_{yi}^2 \left[ \ln(H_{yi}) - \ln(H_0) \right]}{\sum_i G_{yi}^4}, \quad \sigma_{w, y} = \sqrt{-m_y}$$

#### Criterio Diagnóstico de Inflación de Fondo:
El sistema compara automáticamente las pendientes ancladas con las deducidas a partir de los cocientes puros de alta frecuencia ($H_2 / H_1$). Si se detecta una discrepancia significativa:
$$|c_{\text{libre}} - \ln(H_0)| > \tau_{\text{metrológica}}$$
el software emite un dictamen alertando de que el pico directo $H_0$ está inflado por fondo óptico continuo no estructurado, recomendando utilizar el modo libre para evitar subestimaciones del desorden real.

### 4.3 Extracción Simultánea de la Fracción de Vacancias ($p$):
Si el número de localizaciones $N_{\text{det}}$ se conoce mediante el conteo directo de centroides en espacio real curado (vía [[CAT-204_Curacion_Fotometrica_Desacople_MultiGaussiano_Consistencia]]), la intersección $c$ permite resolver $p$ en forma cerrada:
$$e^c = N_{\text{det}} (1-p) \implies 1 - p = \frac{e^c}{N_{\text{det}}} \implies \bbox[10px,border:1px solid #6366f1,background:#f5f3ff]{p = 1 - \frac{e^c}{N_{\text{det}}}}$$

Esto otorga un desacoplamiento completo y simultáneo de $\sigma_{\text{pos}}$ y $p$ usando únicamente la estructura de difracción en espacio recíproco.

---

## 5. Matriz de Propagación de Incertidumbre Analítica

Dado que las alturas de pico $H_1, H_2$ están contaminadas por fluctuaciones estocásticas de Poisson y ruido del detector con varianzas $\text{Var}(H_1) = \sigma_{H1}^2$ y $\text{Var}(H_2) = \sigma_{H2}^2$, aplicamos la ley gaussiana de propagación de errores a la función $\sigma_{\text{pos}}(H_1, H_2)$:

$$\sigma_{\text{pos}} = \frac{a}{2\pi\sqrt{3}} \left[ \ln H_1 - \ln H_2 \right]^{1/2}$$

Calculando las derivadas parciales respecto a las alturas:
$$\frac{\partial \sigma_{\text{pos}}}{\partial H_1} = \frac{a}{2\pi\sqrt{3}} \frac{1}{2 \sqrt{\ln(H_1/H_2)}} \frac{1}{H_1} = \frac{\sigma_{\text{pos}}}{2 \ln(H_1/H_2)} \frac{1}{H_1}$$
$$\frac{\partial \sigma_{\text{pos}}}{\partial H_2} = -\frac{a}{2\pi\sqrt{3}} \frac{1}{2 \sqrt{\ln(H_1/H_2)}} \frac{1}{H_2} = -\frac{\sigma_{\text{pos}}}{2 \ln(H_1/H_2)} \frac{1}{H_2}$$

La varianza metrológica de la estimación analítica es:
$$\sigma_{\sigma_{\text{pos}}}^2 \approx \left(\frac{\partial \sigma_{\text{pos}}}{\partial H_1}\right)^2 \sigma_{H1}^2 + \left(\frac{\partial \sigma_{\text{pos}}}{\partial H_2}\right)^2 \sigma_{H2}^2$$

Sustituyendo las relaciones de relación señal-ruido $\text{SNR}_1 = H_1 / \sigma_{H1}$ y $\text{SNR}_2 = H_2 / \sigma_{H2}$:
$$\bbox[12px,border:2px solid #b91c1c,background:#fef2f2]{
\frac{\sigma_{\sigma_{\text{pos}}}}{\sigma_{\text{pos}}} = \frac{1}{2 \ln(H_1/H_2)} \sqrt{\frac{1}{\text{SNR}_1^2} + \frac{1}{\text{SNR}_2^2}}
}$$

### Análisis de Sensibilidad y Singularidad:
1. **Régimen de Bajo Desorden ($\sigma_{\text{pos}} \to 0$):**
   Cuando el cristal es casi perfecto, $H_1 \approx H_2$, lo que hace que $\ln(H_1/H_2) \to 0$. El denominador de la incertidumbre relativa se aproxima a cero, provocando una explosión de la incertidumbre fraccionaria. En este régimen ($\sigma_{\text{pos}} < 0.02 a$), medir la atenuación diferencial de picos se vuelve muy insensible, siendo preferible medir directamente el ancho residual o la varianza en espacio real.
2. **Régimen de Alto Desorden ($\sigma_{\text{pos}} > 0.15 a$):**
   El pico $H_2$ sufre una atenuación exponencial cuadrática cuatro veces más rápida que $H_1$. Para $\sigma_{\text{pos}} \approx 0.18 a$, $H_2$ cae al orden de $e^{-4 (2\pi \cdot 0.18)^2} \approx e^{-5.1} \approx 0.006$ de su valor original, sumergiéndose por debajo del piso de ruido difuso incoherente ($\text{SNR}_2 \to 0$), invalidando la métrica.

---

## 6. Criterios de Selección: Método Analítico Directo vs Simulación Monte Carlo

La siguiente tabla establece la guía de decisión metrológica implementada en PyPrinting 3.0:

| Parámetro / Condición | Dominio del Método Analítico Directo ($H_2/H_1$) | Dominio de la Calibración Monte Carlo |
| :--- | :--- | :--- |
| **Rango de Desorden** | $0.03 \le \sigma_{\text{pos}} / a \le 0.15$ | Todo el rango ($0.005 \le \sigma_{\text{pos}} / a \le 0.40$) |
| **Relación Señal/Ruido** | $\text{SNR}_2 > 3.0$ (Pico $H_2$ distinguible del fondo difuso) | $\text{SNR}_2 \le 3.0$ (Pico $H_2$ sumergido en el ruido) |
| **Tiempo de Cómputo** | $< 1\,\text{ms}$ (Evaluación en tiempo real en GUI) | $0.5 - 5\,\text{s}$ (Simulación estocástica de ensamble) |
| **Tipo de Desorden** | Desorden Puro de Debye-Waller (Tipo I, sin pérdida de fase) | Admite desorden mixto Tipo I + Tipo II (Hosemann) |
| **Efectos de Borde** | Despreciables si $N_{\text{total}} \ge 20 \times 20$ sitios | Compensa rigurosamente tamaños pequeños ($5 \times 5$ a $15 \times 15$) |
| **Incertidumbre** | Gobernada por propagación analítica $\text{SNR}$ | Reducida asintóticamente mediante $N_{\text{ensambles}} \ge 20$ |

---

## 7. Implementación de Referencia en Python (PyPrinting 3.0)

```python
import numpy as np

def direct_analytical_fourier_metrology(H1: float, H2: float, H_diag: float, a: float, 
                                        snr1: float = 10.0, snr2: float = 5.0) -> dict:
    """
    Calcula el desorden posicional sigma_pos en forma cerrada sin curvas de calibración.
    
    Parámetros:
      H1: Altura neta del pico de Bragg de 1er orden axial.
      H2: Altura neta del pico de Bragg de 2do orden axial.
      H_diag: Altura neta del pico de Bragg de 1er orden diagonal.
      a: Constante de red en nm.
      snr1: Relación señal-ruido del pico H1.
      snr2: Relación señal-ruido del pico H2.
      
    Retorna:
      Diccionario con sigma_axial, sigma_diag, incertidumbre y flags de validez.
    """
    # 1. Criterio de viabilidad física (H1 debe ser mayor que H2)
    if H1 <= 0 or H2 <= 0 or H1 <= H2:
        return {
            "valid": False,
            "error": "Inversión no física: H1 debe ser estrictamente mayor que H2 y positivos."
        }
        
    ratio_axial = H1 / H2
    ln_axial = np.log(ratio_axial)
    
    # 2. Inversión analítica H2 / H1
    sigma_axial = (a / (2.0 * np.pi * np.sqrt(3.0))) * np.sqrt(ln_axial)
    
    # 3. Propagación de error analítico
    rel_error = (1.0 / (2.0 * ln_axial)) * np.sqrt((1.0 / snr1**2) + (1.0 / snr2**2))
    sigma_error = sigma_axial * rel_error
    
    # 4. Inversión diagonal para chequeo de isotropía
    sigma_diag = None
    isotropy_ratio = None
    if H_diag > 0 and H1 > H_diag:
        ln_diag = np.log(H1 / H_diag)
        sigma_diag = (a / (2.0 * np.pi)) * np.sqrt(ln_diag)
        isotropy_ratio = ln_axial / (3.0 * ln_diag)  # Debe ser ~1.0 en redes isotrópicas
        
    # 5. Evaluación de régimen metrológico
    monte_carlo_recommended = (sigma_axial / a > 0.15) or (snr2 < 3.0)
    
    return {
        "valid": True,
        "sigma_pos_axial_nm": float(sigma_axial),
        "sigma_pos_error_nm": float(sigma_error),
        "sigma_pos_fractional": float(sigma_axial / a),
        "sigma_pos_diag_nm": float(sigma_diag) if sigma_diag is not None else None,
        "isotropy_index": float(isotropy_ratio) if isotropy_ratio is not None else None,
        "monte_carlo_recommended": bool(monte_carlo_recommended)
    }
```

---

## 8. Conclusiones y Guía Operativa

1. **Autonomía Analítica Inmediata:**  
   El cociente $H_2 / H_1$ y el Gráfico de Wilson 2D otorgan a PyPrinting 3.0 un canal metrológico ultra-rápido ($< 1\,\text{ms}$) para estimar $\sigma_{\text{pos}}$ y descartar muestras inviables durante la adquisición experimental sin sobrecargar la CPU/GPU con simulaciones numéricas.

2. **Independencia de Vacancias:**  
   La prueba matemática demuestra que la fracción de vacancias $p$ se factoriza idénticamente en todos los picos de Bragg de orden superior, haciendo al cociente $H_2 / H_1$ inmune a la falta de material.

3. **Arquitectura Jerárquica en PyPrinting 3.0:**  
   El software debe emplear el cálculo analítico como **estimador de primer orden preliminar** en la GUI y desplegar automáticamente la simulación de ensamble de Monte Carlo si $\text{SNR}_2 < 3.0$ o $\sigma_{\text{pos}} / a > 0.15$, garantizando máxima velocidad sin comprometer el rigor en casos de alto desorden.
