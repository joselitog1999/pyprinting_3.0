# CAT-315 [FIS/MAT]: Espacio Recíproco de Redes Hexagonales y Honeycomb: Factor de Estructura, Subredes y Anisotropías
## Formalismo Diatómico, Interferencia Constructiva/Destructiva, Ruptura de Simetría Subred $A/B$, Tensor de Covarianza $\mathbf{\Sigma}_{\text{pos}}$ y Metrología de Picos

---

**Signatura Bibliotecaria:** `CAT-315`  
**Clasificación Temática:** `[FIS]` / `[MAT]` Física del Estado Sólido, Cristalografía 2D y Óptica de Fourier  
**Pilar:** Pilar III — Cristalografía 2D, Espacio Recíproco y Metrología de Desorden  
**Autoría:** José Luis González Peñafiel (*INS-UNSAM / CONICET*), Comité Científico PyPrinting 3.0  
**Fecha de Publicación:** Septiembre 2026  
**Estado:** Producción / Consolidado  
**Módulos Asociados:** `core/lattice_generator.py`, `core/lattice_disorder.py` (`compute_hexagonal_bragg_indexing`, `extract_honeycomb_peak_profile_metrics`, `run_hexagonal_monte_carlo_calibration`), `analysis/lattice_disorder_gui.py` (Pestañas 3-4)  
**Documentos Vinculados:**  
- [[CAT-300_Fundamentos_Cristalografia_Bidimensional_y_Fisica_Desorden_2D]] (Tratado rector: redes de Bravais, simetría y desorden 2D)  
- [[CAT-305_Derivacion_Matematica_Factor_Estructura_Debye_Waller]] (Formalismo estocástico de Bernoulli y atenuación coherente)  
- [[CAT-306_Metrologia_Optica_Difraccion_Bragg_y_Perfiles_Redes_2D]] (Física óptica de difracción en el plano focal posterior BFP)  
- [[CAT-307_Computacion_NUFFT_Factor_Estructura_Optimizacion_BLAS]] (Computación tensorial rápida de $S(\mathbf{q})$ con BLAS-3)  
- [[CAT-308_Metrologia_Analitica_Directa_Picos_Bragg_Fourier_2D]] (Inversión analítica directa $H_2/H_1$ para redes cuadradas)  
- [[CAT-310_Derivacion_Matematica_Paracristal_2D_Hosemann_Anisotropo]] (Acoplamientos tensoriales y desorden anisotrópico)  
- [[CAT-314_Cristalografia_Computacional_2D_Bases_Poliatomicas_y_Fronteras]] (Parametrización de bases poliatómicas y celda unidad)  

---

> [!IMPORTANT] Propósito del Documento
> Este reporte provee la fundamentación física y matemática exhaustiva del espacio recíproco de las dos morfologías trigonales fundamentales: la **red triangular/hexagonal monoatómica** ($Z=6$) y la **red honeycomb diatómica** ($Z=3$, grafeno coloidal). Se deduce en forma cerrada el factor de estructura continuo $S(\mathbf{q})$, el factor de forma de la base $|F_{\text{basis}}(\mathbf{G})|^2$, el impacto de vacancias independientes en subredes $A$ y $B$, el efecto de tensiones de red (*strain*) y covarianzas anisotrópicas de impresión $\mathbf{\Sigma}_{\text{pos}}$, y se derivan las ecuaciones analíticas exactas para la inversión metrológica de desorden mediante cocientes de Bragg ($H_2 / H_1$).

---

## 1. Resumen Ejecutivo y Motivación Física

En la nanofabricación fototérmica y autoensamblado coloidal guiado por luz, el control de geometrías no ortogonales es crucial para el diseño de metamateriales plasmónicos, cristales fotónicos y simuladores cuánticos coloidales. Mientras que la red cuadrada está unívocamente descrita por una red de Bravais simple con un único parámetro métrico $a$, las geometrías hexagonales introducen una dualidad estructural crítica:

1. **Red Triangular / Hexagonal Monoatómica ($Z=6$):** Es una auténtica red de Bravais donde cada sitio posee seis primeros vecinos a distancia $a$. Su celda primitiva contiene exactamente un emisor ($N_b = 1$). El espacio recíproco exhibe simetría de orden 6 ($C_6$) y todos los picos de difracción de una misma concha recíproca tienen idéntico factor de forma geométrico.
2. **Red Honeycomb / Panal de Abejas ($Z=3$):** **No es una red de Bravais**. Se trata de una red de Bravais triangular subyacente decorada con una **base diatómica** de dos sitios ($A$ y $B$) por celda primitiva ($N_b = 2$), cada uno con coordinación $Z=3$ a distancia de primer vecino $d_{\text{nn}} = a/\sqrt{3}$.

```
      Red Triangular (Monoatómica, Z=6)               Red Honeycomb (Base Diatómica, Z=3)
                 *       *                                    A --- B
                / \     / \                                  /       \
               * - * - * - *                                B         A
                \ /     \ /                                  \       /
                 *       *                                    A --- B
      [Bravais directa: 1 átomo/celda]               [Bravais triangular + base {A, B}]
```

La interferencia de fase entre las dos subredes $A$ y $B$ introduce un **factor de base geométrico** $F_{\text{basis}}(\mathbf{q})$ que modula fuertemente las intensidades de Bragg:
- Ciertos picos experimentan interferencia destructiva parcial, resultando en intensidades atenuadas relativas.
- Otros picos experimentan interferencia constructiva total, manifestándose con intensidades amplificadas por un factor de hasta 4.
- Pequeñas distorsiones en la posición de la base $\boldsymbol{\tau}$ o en las poblaciones relativas de vacancias $p_A \ne p_B$ **rompen la degeneración de las conchas de difracción**, generando anisotropías espectrales observables en el factor de estructura $S(\mathbf{q})$.

---

## 2. Geometría en Espacio Real y Espacio Recíproco

### 2.1 Vectores Primitivos Directos
Adoptando el convenio cristalográfico estándar con $\mathbf{a}_1$ horizontal y ángulo inter-axial $\gamma = 60^\circ$ (o equivalentemente $\gamma = 120^\circ$ bajo cambio de base canónico):

$$\mathbf{a}_1 = a \begin{pmatrix} 1 \\ 0 \end{pmatrix}, \quad \mathbf{a}_2 = a \begin{pmatrix} \cos 60^\circ \\ \sin 60^\circ \end{pmatrix} = a \begin{pmatrix} 1/2 \\ \sqrt{3}/2 \end{pmatrix}$$

El área de la celda unidad primitiva de Bravais es:
$$\Omega = \|\mathbf{a}_1 \times \mathbf{a}_2\| = a^2 \sin 60^\circ = \frac{\sqrt{3}}{2} a^2$$

### 2.2 Vectores Primitivos Recíprocos
Los vectores de la base recíproca $\{\mathbf{b}_1, \mathbf{b}_2\}$ satisfacen la condición ortonormal de von Laue:
$$\mathbf{a}_i \cdot \mathbf{b}_j = 2\pi \delta_{ij}$$

Invirtiendo algebraicamente la matriz de red directa $\mathbf{A} = [\mathbf{a}_1, \mathbf{a}_2]$:
$$\mathbf{B} = 2\pi (\mathbf{A}^{-1})^T = 2\pi \begin{pmatrix} a & a/2 \\ 0 & a\sqrt{3}/2 \end{pmatrix}^{-T} = \frac{2\pi}{a} \begin{pmatrix} 1 & 0 \\ -1/\sqrt{3} & 2/\sqrt{3} \end{pmatrix}$$

Por lo tanto:
$$\mathbf{b}_1 = \frac{2\pi}{a} \begin{pmatrix} 1 \\ -1/\sqrt{3} \end{pmatrix} = \frac{4\pi}{\sqrt{3}a} \begin{pmatrix} \sqrt{3}/2 \\ -1/2 \end{pmatrix}, \quad \mathbf{b}_2 = \frac{2\pi}{a} \begin{pmatrix} 0 \\ 2/\sqrt{3} \end{pmatrix} = \frac{4\pi}{\sqrt{3}a} \begin{pmatrix} 0 \\ 1 \end{pmatrix}$$

El módulo fundamental de los vectores recíprocos de la primera concha es:
$$b = \|\mathbf{b}_1\| = \|\mathbf{b}_2\| = \frac{4\pi}{\sqrt{3}a}$$
En unidades de frecuencia espacial ordinaria ($f = q / 2\pi$):
$$f_1 = \frac{b}{2\pi} = \frac{2}{\sqrt{3}a} \approx \frac{1.1547}{a}$$

> [!NOTE] Rotación de la Red Recíproca
> La red recíproca de una red triangular con $\mathbf{a}_1$ a $0^\circ$ es otra red triangular cuyos nodos principales yacen rotados a $30^\circ$ y $90^\circ$ respecto a la horizontal. Esto explica por qué en los difractogramas 2D de redes hexagonales los picos principales aparecen rotados $30^\circ$ respecto a las filas de impresión directas.

---

## 3. Factor de Estructura Complejo y Factor de Base Diatómico

### 3.1 Densidad Microscópica de Dispersión
Para un cristal bidimensional confinado compuesto por $N$ celdas unidad de Bravais con vectores de red $\mathbf{R}_j = m_j \mathbf{a}_1 + n_j \mathbf{a}_2$, cada celda contiene $N_b$ emisores ubicados en $\mathbf{R}_j + \boldsymbol{\tau}_\alpha$ ($\alpha \in \{1, \dots, N_b\}$):

$$\rho(\mathbf{r}) = \sum_{j=1}^N \sum_{\alpha=1}^{N_b} c_{j,\alpha} f_\alpha \, \delta\left( \mathbf{r} - \mathbf{R}_j - \boldsymbol{\tau}_\alpha - \mathbf{u}_{j,\alpha} \right)$$

donde:
- $c_{j,\alpha} \in \{0, 1\}$ es la variable estocástica de ocupación del sitio (vacancias).
- $f_\alpha$ es el factor de dispersión o peso fotométrico de la especie atómica $\alpha$.
- $\boldsymbol{\tau}_\alpha$ es el vector interno de base dentro de la celda unidad.
- $\mathbf{u}_{j,\alpha}$ es el desplazamiento aleatorio respecto a la posición de equilibrio ideal (desorden térmico o imprecisión de impresión).

### 3.2 Descomposición de von Laue: Red $\times$ Motivo
La Transformada de Fourier espacial continua de la densidad $\rho(\mathbf{r})$ es:

$$\mathcal{F}\{\rho\}(\mathbf{q}) = \int_{\mathbb{R}^2} \rho(\mathbf{r}) e^{-i \mathbf{q} \cdot \mathbf{r}} \, d\mathbf{r} = \sum_{j=1}^N \sum_{\alpha=1}^{N_b} c_{j,\alpha} f_\alpha e^{-i \mathbf{q} \cdot (\mathbf{R}_j + \boldsymbol{\tau}_\alpha + \mathbf{u}_{j,\alpha})}$$

En el límite de cristal ideal ($c_{j,\alpha} \equiv 1$, $\mathbf{u}_{j,\alpha} \equiv \mathbf{0}$, partículas idénticas $f_\alpha = 1$), la amplitud se factoriza exactamente en el producto de la **amplitud de la red de Bravais** $A_{\text{Bravais}}(\mathbf{q})$ y el **factor de forma de la base** $F_{\text{basis}}(\mathbf{q})$:

$$\mathcal{F}\{\rho\}(\mathbf{q}) = \left( \sum_{j=1}^N e^{-i \mathbf{q} \cdot \mathbf{R}_j} \right) \cdot \left( \sum_{\alpha=1}^{N_b} e^{-i \mathbf{q} \cdot \boldsymbol{\tau}_\alpha} \right) = A_{\text{Bravais}}(\mathbf{q}) \cdot F_{\text{basis}}(\mathbf{q})$$

El factor de estructura macroscópico por celda unidad es:
$$S(\mathbf{q}) = \frac{1}{N N_b} \left| \mathcal{F}\{\rho\}(\mathbf{q}) \right|^2 = \frac{1}{N_b} S_{\text{Bravais}}(\mathbf{q}) \cdot |F_{\text{basis}}(\mathbf{q})|^2$$

Para un vector recíproco de Bragg $\mathbf{G}_{hk} = h \mathbf{b}_1 + k \mathbf{b}_2$, la red de Bravais satisface $e^{-i \mathbf{G}_{hk} \cdot \mathbf{R}_j} = 1$, con lo cual $S_{\text{Bravais}}(\mathbf{G}_{hk}) = N$. Por ende, la intensidad de difracción en cada nodo de Bragg está **gobernada unívocamente por el módulo cuadrado del factor de base**:

$$I(\mathbf{G}_{hk}) \propto |F_{\text{basis}}(\mathbf{G}_{hk})|^2$$

---

## 4. Análisis Espectral Comparativo: Hexagonal Monoatómica vs. Honeycomb Canónica

### 4.1 Red Hexagonal Monoatómica ($N_b = 1$)
Al contener un único sitio por celda ubicado en el origen ($\boldsymbol{\tau}_1 = \mathbf{0}$):
$$F_{\text{basis}}^{\text{hex}}(\mathbf{q}) = e^{-i \mathbf{q} \cdot \mathbf{0}} = 1 \implies |F_{\text{basis}}^{\text{hex}}(\mathbf{G}_{hk})|^2 \equiv 1 \quad (\forall h, k \in \mathbb{Z})$$
**Todos los picos de Bragg de la red de Bravais están permitidos con igual peso geométrico.**

### 4.2 Red Honeycomb Canónica ($N_b = 2$, Base $(1/3, 1/3)$)
En la red honeycomb, la celda unidad contiene dos sitios:
- Subred $A$: $\boldsymbol{\tau}_A = \mathbf{0} = (0, 0)$
- Subred $B$: $\boldsymbol{\tau}_B = u_2 \mathbf{a}_1 + v_2 \mathbf{a}_2$

En la configuración canónica con simetría $D_{6h}$ / $C_{3v}$ plena:
$$u_2 = \frac{1}{3}, \quad v_2 = \frac{1}{3}$$
El producto escalar con el vector de Bragg $\mathbf{G}_{hk} = h \mathbf{b}_1 + k \mathbf{b}_2$ es:
$$\mathbf{G}_{hk} \cdot \boldsymbol{\tau}_B = (h \mathbf{b}_1 + k \mathbf{b}_2) \cdot \left(\frac{1}{3} \mathbf{a}_1 + \frac{1}{3} \mathbf{a}_2\right) = \frac{2\pi}{3} (h + k)$$

El factor de base complejo es:
$$F_{\text{basis}}(\mathbf{G}_{hk}) = 1 + e^{-i \frac{2\pi}{3}(h+k)}$$

Calculando su módulo al cuadrado:
$$|F_{\text{basis}}(\mathbf{G}_{hk})|^2 = \left| 1 + \cos\left(\frac{2\pi(h+k)}{3}\right) - i \sin\left(\frac{2\pi(h+k)}{3}\right) \right|^2 = 2 + 2\cos\left(\frac{2\pi(h+k)}{3}\right)$$

Utilizando la identidad trigonométrica $\cos(2\theta) = 2\cos^2\theta - 1$:
$$|F_{\text{basis}}(\mathbf{G}_{hk})|^2 = 4 \cos^2\left( \frac{\pi}{3}(h+k) \right)$$

### 4.3 Clasificación Exacta por Conchas Recíprocas

Dependiendo del valor de $(h+k) \pmod 3$, surgen tres regímenes espectrales exactos:

| $(h+k) \pmod 3$ | Argumento $\frac{\pi(h+k)}{3}$ | $\cos\left(\frac{\pi(h+k)}{3}\right)$ | $|F_{\text{basis}}|^2$ | Tipo de Interferencia |
|:---:|:---:|:---:|:---:|:---:|
| **$0$** | $0, \pi, 2\pi, \dots$ | $\pm 1$ | **$4$** | **Constructiva Total ($4\times$)** |
| **$1$ ó $2$** | $\pi/3, 2\pi/3, 4\pi/3, \dots$ | $\pm 1/2$ | **$1$** | **Destructiva Parcial ($1\times$)** |

Evaluemos explícitamente las tres primeras conchas recíprocas de la red de Bravais:

#### A. Primera Concha Recíproca ($q_1 = \frac{4\pi}{\sqrt{3}a}$, radio $f_1 = \frac{2}{\sqrt{3}a}$)
La primera concha está formada por los 6 vectores más cercanos al origen:
$$\mathbf{G} \in \left\{ \pm \mathbf{b}_1, \pm \mathbf{b}_2, \pm (\mathbf{b}_1 + \mathbf{b}_2) \right\}$$
Analizando sus índices de Miller $(h, k)$ y su suma $h+k$:
1. $(1, 0) \implies h+k = 1 \implies |F|^2 = 4 \cos^2(\pi/3) = 4(1/4) = \mathbf{1}$
2. $(-1, 0) \implies h+k = -1 \implies |F|^2 = 4 \cos^2(-\pi/3) = 4(1/4) = \mathbf{1}$
3. $(0, 1) \implies h+k = 1 \implies |F|^2 = 4 \cos^2(\pi/3) = 4(1/4) = \mathbf{1}$
4. $(0, -1) \implies h+k = -1 \implies |F|^2 = 4 \cos^2(-\pi/3) = 4(1/4) = \mathbf{1}$
5. $(1, 1) \implies h+k = 2 \implies |F|^2 = 4 \cos^2(2\pi/3) = 4(-1/2)^2 = \mathbf{1}$
6. $(-1, -1) \implies h+k = -2 \implies |F|^2 = 4 \cos^2(-2\pi/3) = 4(-1/2)^2 = \mathbf{1}$

> [!NOTE] Hallazgo Fundamental de la 1ª Concha en Honeycomb
> Para los 6 picos de la primera concha de Bragg, la interferencia entre subredes es **destructiva parcial** ($|F|^2 = 1$). Las ondas dispersadas por la subred B interfieren con un desfase de $120^\circ$ ($2\pi/3$) respecto a la subred A, reduciendo la intensidad a la cuarta parte de lo que sería una interferencia puramente en fase ($|F|^2 = 4$).

#### B. Segunda Concha Recíproca ($q_2 = \sqrt{3} q_1 = \frac{4\pi}{a}$, radio $f_2 = \frac{2}{a}$)
Corresponde a los picos ortogonales a las direcciones de la primera concha (rotados $30^\circ$, que caen en los ejes transversales):
$$\mathbf{G} \in \left\{ \pm (\mathbf{b}_1 - \mathbf{b}_2), \pm (2\mathbf{b}_1 + \mathbf{b}_2), \pm (\mathbf{b}_1 + 2\mathbf{b}_2) \right\}$$
Evaluando sus índices:
1. $(1, -1) \implies h+k = 0 \implies |F|^2 = 4 \cos^2(0) = \mathbf{4}$
2. $(-1, 1) \implies h+k = 0 \implies |F|^2 = 4 \cos^2(0) = \mathbf{4}$
3. $(2, 1) \implies h+k = 3 \implies |F|^2 = 4 \cos^2(\pi) = 4(-1)^2 = \mathbf{4}$
4. $(-2, -1) \implies h+k = -3 \implies |F|^2 = 4 \cos^2(-\pi) = \mathbf{4}$
5. $(1, 2) \implies h+k = 3 \implies |F|^2 = 4 \cos^2(\pi) = \mathbf{4}$
6. $(-1, -2) \implies h+k = -3 \implies |F|^2 = 4 \cos^2(-\pi) = \mathbf{4}$

> [!TIP] Hallazgo Fundamental de la 2ª Concha en Honeycomb
> Todos los 6 picos de la segunda concha satisfacen $h+k \equiv 0 \pmod 3$. La diferencia de camino óptico es un múltiplo exacto de $2\pi$. La interferencia es **100% constructiva** ($|F|^2 = 4$). **¡La segunda concha de Bragg es inherentemente 4 veces más brillante que la primera!**

```
                     ESPACIO RECÍPROCO HONEYCOMB
                     
                                 q_y ^
                                     |    |F|^2 = 4 (Constructivo)
                                     |         * (0, 4pi/a)
                           *         |         *
                       (|F|^2=1)     |     (|F|^2=1)
                                     |
                       *             |             * (|F|^2=4)
                    (|F|^2=4)        |
           --------------------------+--------------------------> q_x
                                     |
                       *             |             * (|F|^2=1)
                   (|F|^2=1)         |
                                     |         * (|F|^2=4)
                           *         |
                       (|F|^2=4)     |
```

---

## 5. Teoría Rigurosa de Vacancias: Globales vs. Desacopladas por Subred ($A$ y $B$)

En experimentos de nanofabricación fototérmica, las vacancias no siempre se distribuyen de forma estequiométrica. Pueden surgir sesgos por orden de impresión (por ejemplo, imprimir todos los sitios A y luego todos los sitios B con una pequeña deriva térmica o desensibilización del sustrato), desorción selectiva por polarización óptica, o funcionalización química diferencial.

### 5.1 Formalismo Estocástico Bipartito
Modelamos la ocupación de cada celda unidad $j \in \{1, \dots, N\}$ mediante dos variables aleatorias discretas de Bernoulli independientes:
- Subred $A$: $c_j^A \in \{0, 1\}$ con probabilidad de ocupación $p_A = 1 - f_{\text{vac}, A}$.
- Subred $B$: $c_j^B \in \{0, 1\}$ con probabilidad de ocupación $p_B = 1 - f_{\text{vac}, B}$.

Momentos estocásticos de primer y segundo orden:
$$\mathbb{E}[c_j^A] = p_A, \quad \text{Var}(c_j^A) = p_A(1 - p_A)$$
$$\mathbb{E}[c_j^B] = p_B, \quad \text{Var}(c_j^B) = p_B(1 - p_B)$$
$$\mathbb{E}[c_j^A c_k^A] = p_A^2 + p_A(1 - p_A) \delta_{jk}$$
$$\mathbb{E}[c_j^B c_k^B] = p_B^2 + p_B(1 - p_B) \delta_{jk}$$
$$\mathbb{E}[c_j^A c_k^B] = p_A p_B \quad (\forall j, k)$$

### 5.2 Descomposición en Intensidad Coherente de Bragg y Meseta Difusa
La intensidad esperada en el detector $\langle I(\mathbf{q}) \rangle = \mathbb{E}[|\mathcal{F}\{\rho\}(\mathbf{q})|^2]$ se separa analíticamente en una componente coherente de picos delta de Bragg y una componente incoherente difusa continua:

$$\langle I(\mathbf{q}) \rangle = I_{\text{Bragg}}(\mathbf{q}) + I_{\text{diffuse}}(\mathbf{q})$$

#### A. Componente Coherente de Bragg
Emerge del valor esperado de la amplitud microscópica:
$$I_{\text{Bragg}}(\mathbf{q}) = \left| \mathbb{E}\left[ \mathcal{F}\{\rho\}(\mathbf{q}) \right] \right|^2 = e^{-\mathbf{q}^T \mathbf{\Sigma}_{\text{pos}} \mathbf{q}} \left| \sum_{j=1}^N e^{-i \mathbf{q} \cdot \mathbf{R}_j} \right|^2 \cdot \left| p_A + p_B e^{-i \mathbf{q} \cdot \boldsymbol{\tau}} \right|^2$$

En un vector de la red recíproca $\mathbf{q} = \mathbf{G}_{hk}$, la suma sobre la red de Bravais vale $N$, obteniéndose:
$$I_{\text{Bragg}}(\mathbf{G}_{hk}) = N^2 e^{-\mathbf{G}_{hk}^T \mathbf{\Sigma}_{\text{pos}} \mathbf{G}_{hk}} \cdot |F_{\text{eff}}(\mathbf{G}_{hk})|^2$$

donde el **factor de base efectivo modulado por vacancias** es:
$$|F_{\text{eff}}(\mathbf{G})|^2 = |p_A + p_B e^{-i \mathbf{G} \cdot \boldsymbol{\tau}}|^2 = p_A^2 + p_B^2 + 2 p_A p_B \cos(\mathbf{G} \cdot \boldsymbol{\tau})$$

Reescribiendo mediante identidades trigonométricas fundamentales:
$$|F_{\text{eff}}(\mathbf{G})|^2 = (p_A - p_B)^2 + 4 p_A p_B \cos^2\left( \frac{\mathbf{G} \cdot \boldsymbol{\tau}}{2} \right)$$

#### B. Componente Incoherente Difusa (Fondo de Fluctuaciones)
Emerge de la varianza estocástica de los emisores y preserva la conservación total de energía dispersada (Teorema de Parseval):
$$I_{\text{diffuse}}(\mathbf{q}) = N \Big[ p_A(1 - p_A) + p_B(1 - p_B) \Big] + N (p_A^2 + p_B^2) \left( 1 - e^{-\mathbf{q}^T \mathbf{\Sigma}_{\text{pos}} \mathbf{q}} \right)$$

### 5.3 Consecuencias Físicas de la Asimetría $p_A \ne p_B$

1. **Régimen Simétrico / Vacancias Globales ($p_A = p_B = p_{\text{occ}} = 1 - f_{\text{vac}}$):**
   $$|F_{\text{eff}}(\mathbf{G})|^2 = p_{\text{occ}}^2 \left[ 4 \cos^2\left(\frac{\mathbf{G} \cdot \boldsymbol{\tau}}{2}\right) \right] = (1 - f_{\text{vac}})^2 |F_{\text{ideal}}(\mathbf{G})|^2$$
   - Todos los picos de Bragg decaen uniformemente con $(1 - f_{\text{vac}})^2$.
   - **Los cocientes de Bragg entre conchas ($H_2 / H_1$) son matemáticamente inmunes a vacancias globales**, permitiendo desacoplar desorden posicional sin sesgo por defectos puntuales.
2. **Régimen Asimétrico de Subred ($p_A \ne p_B$):**
   - **Aparición de Intensidad Residual:** Si una reflexión satisficiera la condición de extinción total $\cos^2(\mathbf{G}\cdot\boldsymbol{\tau}/2) = 0$, con $p_A \ne p_B$ la intensidad **no se anula**, sino que exhibe un piso residual proporcional a $(p_A - p_B)^2$.
   - **Alteración de los Cocientes de Conchas:**
     - Primera concha ($\cos^2 = 1/4$):
       $$|F_{\text{eff}}(\mathbf{G}_1)|^2 = (p_A - p_B)^2 + p_A p_B = p_A^2 - p_A p_B + p_B^2$$
     - Segunda concha ($\cos^2 = 1$):
       $$|F_{\text{eff}}(\mathbf{G}_2)|^2 = (p_A - p_B)^2 + 4 p_A p_B = (p_A + p_B)^2$$
     - El cociente efectivo de base entre la concha 2 y la concha 1 es:
       $$\mathcal{R}_{\text{basis}} = \frac{|F_{\text{eff}}(\mathbf{G}_2)|^2}{|F_{\text{eff}}(\mathbf{G}_1)|^2} = \frac{(p_A + p_B)^2}{p_A^2 - p_A p_B + p_B^2}$$
       - Si $p_A = p_B$: $\mathcal{R}_{\text{basis}} = \frac{4 p^2}{p^2} = \mathbf{4}$.
       - Si $p_B \to 0$ (colapso completo de la subred B, la red se transforma en una red triangular pura de subred A):
         $$\mathcal{R}_{\text{basis}} \to \frac{p_A^2}{p_A^2} = \mathbf{1}$$
       El cociente espectral varía suavemente entre 4 y 1 como función cuadrática de la desestequiometría de subred, constituyendo un **metrónomo espectral directo del desbalance químico o fototérmico entre subredes**.

---

## 6. Ruptura de Simetría: Deformaciones Mecánicas ($\boldsymbol{\epsilon}$), Desplazamientos de Base ($\delta \boldsymbol{\tau}$) y Anisotropía de Ruido ($\mathbf{\Sigma}_{\text{pos}}$)

En nanofabricación real sobre sustratos de vidrio o silicio, las fuentes de anisotropía se clasifican rigurosamente en dos categorías físicas: **determinísticas** (distorsión de la geometría ideal) y **estocásticas** (asimetría en la dispersión posicional del haz láser o los actuadores piezoeléctricos).

### 6.1 Desplazamiento Arbitrario del Segundo Sitio de Base ($\boldsymbol{\tau} = (u_2, v_2)$)
En sistemas experimentales donde la posición del segundo átomo no está rígidamente fijada en $(1/3, 1/3)$ (por ejemplo, dímeros sintetizados con acoplamiento plasmónico asimétrico, o dímeros bajo campos ópticos vectoriales), la posición fraccional es:
$$\boldsymbol{\tau} = (1/3 + \delta u) \mathbf{a}_1 + (1/3 + \delta v) \mathbf{a}_2$$

El argumento del coseno en $|F(\mathbf{G}_{hk})|^2 = 4 \cos^2(\pi(h u_2 + k v_2))$ se convierte en:
$$\phi(h, k) = \frac{\pi}{3}(h+k) + \pi (h \delta u + k \delta v)$$

**Impacto Espectacular sobre la Primera Concha ($|F|^2 = 1$ en canónico):**
Los seis picos de la primera concha de Bragg, antes degenerados en intensidad, **se separan en tres parejas de intensidades disímiles**:
1. Picos $(\pm 1, 0)$: $|F|^2 = 4 \cos^2\left(\frac{\pi}{3} + \pi \delta u\right) \approx 1 - 2\sqrt{3}\pi \delta u$
2. Picos $(0, \pm 1)$: $|F|^2 = 4 \cos^2\left(\frac{\pi}{3} + \pi \delta v\right) \approx 1 - 2\sqrt{3}\pi \delta v$
3. Picos $(\pm 1, \pm 1)$: $|F|^2 = 4 \cos^2\left(\frac{2\pi}{3} + \pi(\delta u + \delta v)\right) \approx 1 + 2\sqrt{3}\pi (\delta u + \delta v)$

> [!WARNING] Sensibilidad Sub-Nanométrica a la Base
> Para una red con constante $a = 500\,\text{nm}$, un desplazamiento de la subred B de apenas $5\,\text{nm}$ ($\delta u \approx 0.01$) produce una variación relativa de intensidad de Bragg del $\sim 11\%$ entre los ejes de difracción. ¡El factor de estructura funciona como un interferómetro heterodino de ultra-resolución para medir la simetría de la celda unidad!

### 6.2 Deformación Continua de Red (Tensor de Deformación / Strain $\boldsymbol{\epsilon}$)
Si el sustrato sufre una contracción o elongación elástica uniaxial:
$$\mathbf{r}' = (\mathbf{I} + \boldsymbol{\epsilon}) \mathbf{r}, \quad \boldsymbol{\epsilon} = \begin{pmatrix} \epsilon_{xx} & \epsilon_{xy} \\ \epsilon_{xy} & \epsilon_{yy} \end{pmatrix}$$
Por dualidad contra-gradiente, los vectores del espacio recíproco se transforman mediante:
$$\mathbf{G}' = (\mathbf{I} - \boldsymbol{\epsilon}^T) \mathbf{G}$$
- Un strain uniaxial $\epsilon_{xx} \ne \epsilon_{yy}$ transforma el anillo hexagonal de Bragg en una elipse.
- Las posiciones radiales de los picos en los cortes 1D se desplazan según:
  $$f_i' = f_i \left( 1 - \hat{\mathbf{n}}_i^T \boldsymbol{\epsilon} \hat{\mathbf{n}}_i \right)$$
  donde $\hat{\mathbf{n}}_i$ es el vector unitario en la dirección del corte azimutal.

### 6.3 Tensor de Covarianza Posicional Anisótropo ($\mathbf{\Sigma}_{\text{pos}}$)
En la técnica de nanofabricación fototérmica confocal descrita en [[CAT-101_Protocolo_Operativo_Impresion_Fototermica_Grillas_2D]] y [[CAT-105_Compensacion_Deriva_Termomecanica_Particula_Ancla_P0]], el error de localización y posicionamiento no es estrictamente circular-isótropo. La presencia de deriva termomecánica unidireccional sobre la platina piezoeléctrica o asimetrías de astigmatismo en la PSF láser genera un tensor de covarianza bidimensional completo:

$$\mathbf{\Sigma}_{\text{pos}} = \begin{pmatrix} \sigma_x^2 & \sigma_{xy} \\ \sigma_{xy} & \sigma_y^2 \end{pmatrix}$$

El factor de atenuación de Debye-Waller continuo en el espacio recíproco deja de ser radialmente simétrico:
$$\text{DW}(\mathbf{q}) = \exp\left( -\frac{1}{2} \mathbf{q}^T \mathbf{\Sigma}_{\text{pos}} \mathbf{q} \right) = \exp\left( -\frac{1}{2} \left[ q_x^2 \sigma_x^2 + 2 q_x q_y \sigma_{xy} + q_y^2 \sigma_y^2 \right] \right)$$

Para un corte 1D evaluado a lo largo de un ángulo azimutal $\theta$:
$$\mathbf{q}(\theta) = q \begin{pmatrix} \cos\theta \\ \sin\theta \end{pmatrix}$$
$$\text{DW}(q, \theta) = \exp\left( -\frac{1}{2} q^2 \sigma_{\text{eff}}^2(\theta) \right)$$
donde la dispersión aparente proyectada es:
$$\sigma_{\text{eff}}^2(\theta) = \sigma_x^2 \cos^2\theta + \sigma_y^2 \sin^2\theta + 2 \sigma_{xy} \sin\theta \cos\theta$$

> [!TIP] Desacople Metrológico de la Matriz de Covarianza
> Midiendo $\sigma_{\text{eff}}^2(\theta)$ a lo largo de al menos 3 ángulos independientes (por ejemplo, $\theta = 0^\circ, 60^\circ, 120^\circ$), el sistema lineal $3 \times 3$ resultante se invierte en forma cerrada para reconstruir unívocamente el tensor completo $\mathbf{\Sigma}_{\text{pos}} = (\sigma_x^2, \sigma_y^2, \sigma_{xy})$.

---

## 7. Fórmulas de Inversión Analítica en Forma Cerrada para Red Honeycomb

> [!CAUTION] Corrección Numérica (verificada durante la implementación del Paquete A, ver `core/lattice_disorder.py::compute_hexagonal_bragg_indexing` y `tests/test_honeycomb_reciprocal_metrology.py::TestClosedFormSigmaInversion`)
> La versión original de esta sección citaba la convención Debye-Waller de [[CAT-308_Metrologia_Analitica_Directa_Picos_Bragg_Fourier_2D]] con un factor $1/2$ espurio en el exponente ($e^{-q^2\sigma^2/2}$). El [[CAT-308_Metrologia_Analitica_Directa_Picos_Bragg_Fourier_2D|CAT-308]] §3.1 **original** (ya implementado y validado en `core/lattice_disorder.py::compute_analytical_bragg_relations`, `factor_h2h1_x = a_x/(2\pi\sqrt{3})`) usa en cambio $H(\mathbf{G}) \propto e^{-|\mathbf{G}|^2\sigma_{\text{pos}}^2}$, **sin** el $1/2$. Verificado numéricamente sobre redes hexagonales/honeycomb sintéticas con desorden gaussiano de amplitud conocida ($\sigma_{\text{in}}=12$–$40\,\text{nm}$, $a=500\,\text{nm}$): la convención sin $1/2$ reproduce el decaimiento medido de $H_{\text{axis1}}(\sigma)/H_{\text{axis1}}(0)$ dentro de $<1\%$ en todo el barrido, mientras que la convención con $1/2$ sobreestima $H$ hasta $\sim 40\%$ a $\sigma=60\,\text{nm}$. Las fórmulas de esta sección quedan corregidas en consecuencia (factor adicional $1/2$ dentro de la raíz respecto a la versión previamente publicada).

En [[CAT-308_Metrologia_Analitica_Directa_Picos_Bragg_Fourier_2D]] se demostró que para redes cuadradas monoatómicas, el cociente entre el segundo y primer orden axial elimina exactamente la población $N$ y las vacancias globales:
$$\left( \frac{H_2}{H_1} \right)_{\text{cuadrada}} = \frac{e^{-q_2^2 \sigma^2}}{e^{-q_1^2 \sigma^2}} = e^{-(4q_1^2 - q_1^2)\sigma^2} = e^{-3 q_1^2 \sigma^2}$$

### 7.1 Inversión Exacta en Red Honeycomb
En la red honeycomb, la relación entre el pico principal de la primera concha y el pico ortogonal constructivo de la segunda concha involucra dos modulaciones simultáneas:
1. **Diferencia de Radios Recíprocos:**
   $$q_1 = \frac{4\pi}{\sqrt{3}a}, \quad q_2 = \sqrt{3} q_1 = \frac{4\pi}{a}$$
   $$q_2^2 - q_1^2 = 3 q_1^2 - q_1^2 = 2 q_1^2 = \frac{32\pi^2}{3 a^2}$$
2. **Relación de Factores de Base Geométricos:**
   $$\frac{|F(\mathbf{G}_2)|^2}{|F(\mathbf{G}_1)|^2} = \frac{4}{1} = 4$$

Por consiguiente, el cociente de intensidades de Bragg corregidas por fondo es:
$$\frac{H_2}{H_1} = \frac{|F(\mathbf{G}_2)|^2}{|F(\mathbf{G}_1)|^2} \exp\left( -(q_2^2 - q_1^2) \sigma_{\text{pos}}^2 \right) = 4 \exp\left( -2 q_1^2 \sigma_{\text{pos}}^2 \right)$$

Despejando $\sigma_{\text{pos}}$ analíticamente:
$$\ln\left( \frac{H_2 / 4}{H_1} \right) = -2 q_1^2 \sigma_{\text{pos}}^2 \iff \ln\left( \frac{4 H_1}{H_2} \right) = 2 q_1^2 \sigma_{\text{pos}}^2$$

$$\sigma_{\text{pos}} = \frac{1}{q_1} \sqrt{ \frac{1}{2}\ln\left( \frac{4 H_1}{H_2} \right) } = \frac{\sqrt{3} a}{4\pi} \sqrt{ \frac{1}{2}\ln\left( \frac{4 H_1}{H_2} \right) }$$

> [!CAUTION] Criterio de Realidad Física y Límite Asintótico
> Para que el radicando sea positivo ($\sigma_{\text{pos}} \ge 0$), se requiere:
> $$\frac{4 H_1}{H_2} \ge 1 \iff H_2 \le 4 H_1$$
> - En un cristal perfectamente ordenado ($\sigma_{\text{pos}} = 0$), $H_2 = 4 H_1$.
> - A medida que el desorden térmico/estocástico aumenta, el término $e^{-2q_1^2 \sigma^2}$ suprime preferencialmente la concha de alta frecuencia $q_2$, reduciendo $H_2$ mucho más rápido que $H_1$, haciendo crecer el cociente $4 H_1 / H_2$.
> - Si experimentalmente se detecta $H_2 > 4 H_1$, el sistema evidencia una anomalía física severa: desestequiometría de subred ($p_A \ne p_B$) o un colapso en la posición de la base hacia una fase de dímeros compactos.

---

## 8. Arquitectura de Metrología Unitaria para la Pestaña 3 (Espacio Recíproco)

Para la implementación computacional en `analysis/fourier_analysis_tab.py`, la visualización y cuantificación de anisotropías en redes honeycomb requiere una interfaz especializada que presente de forma desacoplada cada dirección cristalográfica.

### 8.1 Cortes 1D Requeridos en Redes Hexagonales y Honeycomb
En concordancia con la simetría $C_{3v} / C_{6v}$:
- **Panel 1 (Ejes Principales del Sensor / Grilla):**
  - Corte $F_x$ ($\theta = 0^\circ$): Alineado con el eje cristalográfico $\mathbf{a}_1$.
  - Corte $F_y$ ($\theta = 90^\circ$): Eje transversal ortogonal.
- **Panel 2 (Direcciones Cristalográficas Tridimensionales):**
  - Corte $\theta = 60^\circ$: Dirección del vector primitivo $\mathbf{a}_2$.
  - Corte $\theta = 120^\circ$: Dirección conjugada $(-1, 1)$.
  - Corte $\theta = 150^\circ$: Dirección transversal ortogonal a $60^\circ$.

### 8.2 Anatomía del Box de Metrología Unitaria por Gráfica
Bajo cada uno de los gráficos 1D de difracción, se propone ubicar un contenedor compacto de metrología que compute y reporte en tiempo real:

```
+-----------------------------------------------------------------------------------+
|  [Gráfico 1D: Corte Azimutal theta = 0 deg / Fx]                                  |
|  (Curva de Intensidad vs Frecuencia Espacial [1/um])                              |
+-----------------------------------------------------------------------------------+
|  METROLOGÍA UNITARIA (0 deg):                                                     |
|  - Pico Principal H1:  f = 1.155 1/um | Tipo: Destructivo (|F|^2=1) | SNR = 42.1  |
|  - Pico Armónico H2:   f = 2.000 1/um | Tipo: Constructivo (|F|^2=4)| SNR = 18.4  |
|  - Relaciones:         H1/H0 = 0.084  | H2/H1 = 2.842                             |
|  - Desorden Analítico: sigma_pos(0 deg) = 14.8 nm (2.96% a)                       |
|  - Ancho & Coherencia: FWHM = 0.082 1/um | Longitud de Coherencia xi = 12.19 um   |
+-----------------------------------------------------------------------------------+
```

---

## 9. Conclusiones y Hoja de Ruta de Validación

1. **Dualidad Hexagonal vs Honeycomb:** La red hexagonal pura posee un factor de base idéntico a la unidad en todos sus picos de Bragg. La red honeycomb exhibe una modulación universal por el factor $4 \cos^2(\pi(h+k)/3)$, que atenúa la primera concha por interferencia destructiva parcial ($|F|^2 = 1$) y amplifica la segunda concha por interferencia constructiva total ($|F|^2 = 4$).
2. **Invariancia ante Vacancias Globales:** Las vacancias estocásticas independientes no modifican el cociente $H_2/H_1$, preservando la exactitud de la inversión analítica de desorden.
3. **Firma Espectral de la Ruptura de Subred ($A \ne B$):** La asimetría entre subredes introduce un piso residual $(p_A - p_B)^2$ y altera monótonamente el cociente de base entre 4 (estequiométrico) y 1 (colapso a red triangular).
4. **Desacople Tensorial:** Los cortes 1D a $0^\circ, 60^\circ, 120^\circ$ permiten resolver experimentalmente el tensor de covarianza completo $\mathbf{\Sigma}_{\text{pos}}$ del nanoensamblado óptico.
