# CAT-305 [MAT]: Derivación Matemática del Factor de Estructura 2D y Formalismo de Debye-Waller con Vacancias
## Proceso Estocástico de Bernoulli, Amplitud de von Laue, Atenuación Coherente $(1-p)^2$ y Gráfico de Wilson 2D

---

**Signatura Bibliotecaria:** `CAT-305`  
**Clasificación Temática:** `[MAT]` Fundamentos Matemáticos y Derivaciones Analíticas  
**Pilar:** III — Cristalografía 2D, Espacio Recíproco y Metrología de Desorden  
**Autoría:** José Luis González Peñafiel (INS-UNSAM / CONICET) — PyPrinting 3.0  
**Fecha de Publicación:** Septiembre 2026  
**Estado:** Producción / Consolidado  
**Documentos Vinculados:**  
- [[CAT-306_Metrologia_Optica_Difraccion_Bragg_y_Perfiles_Redes_2D]] (Física óptica de difracción, perfiles de pico y diagnóstico experimental)  
- [[CAT-307_Computacion_NUFFT_Factor_Estructura_Optimizacion_BLAS]] (Evaluación numérica no equiespaciada mediante BLAS-3)  
- [[CAT-308_Metrologia_Analitica_Directa_Picos_Bragg_Fourier_2D]] (Inversión analítica exacta $H_2/H_1$ sin curvas de calibración)  
- [[CAT-309_Teoria_Paracristal_Hosemann_Perdida_Orden_2D]] (Desorden acumulativo Tipo II vs Tipo I)  

---

> [!TIP] Aplicación e Impacto en Metrología Óptica Experimental
> Para consultar la manifestación física de esta deducción matemática en el plano focal posterior (BFP), la descomposición de perfiles radiales y transversales, el filtrado de fuga DC y la matriz de diagnóstico de laboratorio, consulte la nota física vinculada:  
> 👉 **[[CAT-306_Metrologia_Optica_Difraccion_Bragg_y_Perfiles_Redes_2D]]**

---

### Resumen Ejecutivo

En la difracción de ondas electromagnéticas o cálculo del factor de estructura estático en nanoestructuras 2D, la presencia simultánea de **desorden posicional estocástico** ($\sigma_{\text{pos}}$) y **defectos puntuales (vacancias de red con probabilidad $p$)** modula drásticamente la distribución espectral de intensidad.

Este reporte formaliza la deducción analítica paso a paso desde el proceso puntual microscópico hasta el factor de estructura continuo $S(\mathbf{q})$. Se modela la ocupación de red mediante variables de Bernoulli independientes, demostrando rigurosamente que la intensidad coherente de los picos de Bragg decae estrictamente con el factor **$(1-p)^2 \cdot e^{-q^2 \sigma_{\text{pos}}^2}$**, mientras que la energía estocástica removida de los picos se conserva transfiriéndose a una meseta difusa incoherente subyacente. Asimismo, se deducen las ecuaciones de von Laue para redes finitas $N_x \times N_y$ y la formulación multivariable del Gráfico de Wilson 2D.

---

## 1. Modelo del Proceso Puntual en el Espacio Continuo

Sea una red bidimensional finita definida sobre un dominio $\Omega \subset \mathbb{R}^2$ con $N_{\text{sitios}} = N_x \times N_y$ posiciones de red ideales:
$$\mathbf{R}_{mn} = m \mathbf{a}_1 + n \mathbf{a}_2, \quad m \in \{0, \dots, N_x - 1\}, \; n \in \{0, \dots, N_y - 1\}$$
donde para una red cuadrada ortogonal $\mathbf{a}_1 = (a, 0)$ y $\mathbf{a}_2 = (0, a)$.

Cada sitio físico presenta dos grados de libertad estocásticos:
1. **Ocupación de Bernoulli ($c_j$):** Variable discreta con probabilidad de vacancia $p \in [0, 1)$:
   $$c_j \in \{0, 1\}, \quad \mathbb{P}(c_j = 1) = 1 - p, \quad \mathbb{P}(c_j = 0) = p$$
   Propiedades de momentos estocásticos:
   $$\langle c_j \rangle = 1 - p, \quad \langle c_j^2 \rangle = 1 - p$$
   $$\langle c_j c_k \rangle = (1 - p)^2 \quad (\forall j \ne k)$$
2. **Desplazamiento Posicional Gaussiano ($\mathbf{u}_j$):** Variable continua independiente:
   $$\mathbf{u}_j = (u_{jx}, u_{jy}) \sim \mathcal{N}(\mathbf{0}, \sigma_{\text{pos}}^2 \mathbf{I})$$
   $$\langle \mathbf{u}_j \rangle = \mathbf{0}, \quad \langle u_{jx}^2 \rangle = \langle u_{jy}^2 \rangle = \sigma_{\text{pos}}^2, \quad \langle \mathbf{u}_j \cdot \mathbf{u}_k \rangle = 2\sigma_{\text{pos}}^2 \delta_{jk}$$

La densidad microscópica de dispersión del cristal en el plano $\mathbf{r} \in \mathbb{R}^2$ es:
$$\rho(\mathbf{r}) = \sum_{j=1}^{N_{\text{sitios}}} c_j \, \delta\left( \mathbf{r} - \mathbf{R}_j - \mathbf{u}_j \right)$$

---

## 2. Transformada de Fourier Continua y Factor de Estructura Complejo

La Transformada de Fourier espacial continua de la densidad evaluada en el vector recíproco $\mathbf{q} = (q_x, q_y) \in \mathbb{R}^2$ es:
$$\mathcal{F}\{\rho\}(\mathbf{q}) = \int_{\mathbb{R}^2} \rho(\mathbf{r}) \, e^{-i \mathbf{q} \cdot \mathbf{r}} \, d\mathbf{r} = \sum_{j=1}^{N_{\text{sitios}}} c_j \, e^{-i \mathbf{q} \cdot (\mathbf{R}_j + \mathbf{u}_j)}$$

Definimos el **Factor de Estructura Complejo Normalizado** $S(\mathbf{q})$:
$$S(\mathbf{q}) = \frac{1}{\sqrt{N_{\text{sitios}}}} \sum_{j=1}^{N_{\text{sitios}}} c_j \, e^{-i \mathbf{q} \cdot (\mathbf{R}_j + \mathbf{u}_j)}$$

El espectro de potencia o intensidad de difracción observable es:
$$I(\mathbf{q}) = |S(\mathbf{q})|^2 = S(\mathbf{q}) \cdot S^*(\mathbf{q})$$

Expandiendo el producto de sumas:
$$I(\mathbf{q}) = \frac{1}{N_{\text{sitios}}} \sum_{j=1}^{N_{\text{sitios}}} \sum_{k=1}^{N_{\text{sitios}}} c_j c_k \, e^{-i \mathbf{q} \cdot (\mathbf{R}_j - \mathbf{R}_k)} \, e^{-i \mathbf{q} \cdot (\mathbf{u}_j - \mathbf{u}_k)}$$

Separando la suma en términos diagonales ($j = k$) y términos cruzados ($j \ne k$):
$$\bbox[10px,border:1px solid #2563eb,background:#eff6ff]{
I(\mathbf{q}) = \frac{1}{N_{\text{sitios}}} \sum_{j=1}^{N_{\text{sitios}}} c_j^2 + \frac{1}{N_{\text{sitios}}} \sum_{j \ne k}^{N_{\text{sitios}}} c_j c_k \, e^{-i \mathbf{q} \cdot (\mathbf{R}_j - \mathbf{R}_k)} \, e^{-i \mathbf{q} \cdot (\mathbf{u}_j - \mathbf{u}_k)}
}$$

---

## 3. Deducción Analítica del Factor de Debye-Waller con Vacancias

Tomando la esperanza matemática sobre el ensamble estocástico de vacancias y desplazamientos gaussianos:
$$\langle I(\mathbf{q}) \rangle = \frac{1}{N_{\text{sitios}}} \sum_{j=1}^{N_{\text{sitios}}} \langle c_j^2 \rangle + \frac{1}{N_{\text{sitios}}} \sum_{j \ne k}^{N_{\text{sitios}}} \langle c_j c_k \rangle \, e^{-i \mathbf{q} \cdot (\mathbf{R}_j - \mathbf{R}_k)} \, \langle e^{-i \mathbf{q} \cdot (\mathbf{u}_j - \mathbf{u}_k)} \rangle$$

### 3.1 Evaluación del Promedio de Fase Gaussiano:
La variable aleatoria $\Delta \mathbf{u}_{jk} = \mathbf{u}_j - \mathbf{u}_k$ para $j \ne k$ es una combinación lineal de dos gaussianas independientes:
$$\Delta \mathbf{u}_{jk} \sim \mathcal{N}(\mathbf{0}, 2\sigma_{\text{pos}}^2 \mathbf{I})$$

La función característica de una variable gaussiana unidimensional $X \sim \mathcal{N}(0, \sigma_X^2)$ es $\mathbb{E}[e^{-i q X}] = e^{-\frac{1}{2} q^2 \sigma_X^2}$.  
Para la variable escalar $U = \mathbf{q} \cdot \Delta \mathbf{u}_{jk} = q_x \Delta u_x + q_y \Delta u_y$:
$$\text{Var}(U) = q_x^2 (2\sigma_{\text{pos}}^2) + q_y^2 (2\sigma_{\text{pos}}^2) = 2 |\mathbf{q}|^2 \sigma_{\text{pos}}^2$$

Por lo tanto:
$$\langle e^{-i \mathbf{q} \cdot (\mathbf{u}_j - \mathbf{u}_k)} \rangle = \exp\left[ -\frac{1}{2} \text{Var}(U) \right] = \exp\left[ -\frac{1}{2} (2 |\mathbf{q}|^2 \sigma_{\text{pos}}^2) \right] = e^{-|\mathbf{q}|^2 \sigma_{\text{pos}}^2}$$

### 3.2 Términos Cruzados y Factor de Ocupación:
Sustituyendo $\langle c_j c_k \rangle = (1 - p)^2$ y el promedio de fase gaussiano:
$$\sum_{j \ne k}^{N_{\text{sitios}}} \langle c_j c_k \rangle e^{-i \mathbf{q} \cdot (\mathbf{R}_j - \mathbf{R}_k)} \langle e^{-i \mathbf{q} \cdot \Delta \mathbf{u}} \rangle = (1 - p)^2 e^{-|\mathbf{q}|^2 \sigma_{\text{pos}}^2} \sum_{j \ne k}^{N_{\text{sitios}}} e^{-i \mathbf{q} \cdot (\mathbf{R}_j - \mathbf{R}_k)}$$

Reincorporando el término diagonal faltante $j = k$ (que vale $1$):
$$\sum_{j \ne k}^{N_{\text{sitios}}} e^{-i \mathbf{q} \cdot (\mathbf{R}_j - \mathbf{R}_k)} = \left| \sum_{j=1}^{N_{\text{sitios}}} e^{-i \mathbf{q} \cdot \mathbf{R}_j} \right|^2 - N_{\text{sitios}}$$

Sustituyendo en la expresión completa de la intensidad:
$$\langle I(\mathbf{q}) \rangle = (1 - p) + \frac{(1 - p)^2 e^{-|\mathbf{q}|^2 \sigma_{\text{pos}}^2}}{N_{\text{sitios}}} \left[ \left| \sum_{j=1}^{N_{\text{sitios}}} e^{-i \mathbf{q} \cdot \mathbf{R}_j} \right|^2 - N_{\text{sitios}} \right]$$

Reordenando en dos términos con significado físico directo:
$$\bbox[12px,border:2px solid #2563eb,background:#eff6ff]{
\langle I(\mathbf{q}) \rangle = I_{\text{Bragg}}(\mathbf{q}) + I_{\text{difuso}}(\mathbf{q})
}$$

donde:
$$\bbox[10px,border:1px solid #059669,background:#ecfdf5]{
I_{\text{Bragg}}(\mathbf{q}) = (1 - p)^2 \, e^{-|\mathbf{q}|^2 \sigma_{\text{pos}}^2} \frac{1}{N_{\text{sitios}}} \left| \sum_{j=1}^{N_{\text{sitios}}} e^{-i \mathbf{q} \cdot \mathbf{R}_j} \right|^2
}$$
$$\bbox[10px,border:1px solid #dc2626,background:#fef2f2]{
I_{\text{difuso}}(\mathbf{q}) = (1 - p) \left[ 1 - (1 - p) \, e^{-|\mathbf{q}|^2 \sigma_{\text{pos}}^2} \right]
}$$

---

## 4. Teorema de Truncamiento Espacial y Función de Interferencia de von Laue

Para la red finita ideal de $N_x \times N_y$ sitios, el factor geométrico de red es exactamente separable:
$$\sum_{j=1}^{N_{\text{sitios}}} e^{-i \mathbf{q} \cdot \mathbf{R}_j} = \left( \sum_{m=0}^{N_x - 1} e^{-i q_x m a} \right) \left( \sum_{n=0}^{N_y - 1} e^{-i q_y n a} \right)$$

Cada sumatoria es una serie geométrica finita cerrada:
$$\sum_{m=0}^{N_x - 1} e^{-i q_x m a} = e^{-i \frac{q_x (N_x - 1) a}{2}} \cdot \frac{\sin\left( \frac{N_x q_x a}{2} \right)}{\sin\left( \frac{q_x a}{2} \right)}$$

El factor de interferencia de von Laue resultante es:
$$\frac{1}{N_{\text{sitios}}} \left| \sum_{j=1}^{N_{\text{sitios}}} e^{-i \mathbf{q} \cdot \mathbf{R}_j} \right|^2 = \frac{1}{N_x N_y} \left[ \frac{\sin^2\left( \frac{N_x q_x a}{2} \right)}{\sin^2\left( \frac{q_x a}{2} \right)} \right] \left[ \frac{\sin^2\left( \frac{N_y q_y a}{2} \right)}{\sin^2\left( \frac{q_y a}{2} \right)} \right]$$

### Evaluación en el Vector de la Red Recíproca $\mathbf{G}_{hk} = (h \frac{2\pi}{a}, k \frac{2\pi}{a})$:
Aplicando la regla de L'Hôpital:
$$\lim_{q_x \to h \frac{2\pi}{a}} \frac{\sin\left( \frac{N_x q_x a}{2} \right)}{\sin\left( \frac{q_x a}{2} \right)} = N_x$$
Por consiguiente, la altura máxima del pico de Bragg coherente en resonancia escala proporcionalmente con el número de sitios del cristal:
$$\text{Altura}_{\text{Bragg}}(\mathbf{G}_{hk}) = N_{\text{sitios}} (1 - p)^2 \, e^{-|\mathbf{G}_{hk}|^2 \sigma_{\text{pos}}^2}$$

---

## 5. Formalismo del Gráfico de Wilson Bidimensional (Wilson Plot 2D)

Al estudiar la atenuación diferencial a través de múltiples órdenes de difracción $\{\mathbf{G}_{hk}\}$, se linealiza la altura de pico tomando logaritmo natural:
$$H(\mathbf{G}_{hk}) = I_0 \, e^{-|\mathbf{G}_{hk}|^2 \sigma_{\text{pos}}^2}, \quad I_0 = N_{\text{sitios}} (1 - p)^2$$

$$\bbox[12px,border:2px solid #6366f1,background:#f5f3ff]{
\ln\left[ H(\mathbf{G}_{hk}) \right] = \ln\left[ N_{\text{sitios}} (1 - p)^2 \right] - \sigma_{\text{pos}}^2 |\mathbf{G}_{hk}|^2
}$$

Definiendo la variable independiente $u = |\mathbf{G}_{hk}|^2 = \left(\frac{2\pi}{a}\right)^2 (h^2 + k^2)$ y $y = \ln H$:
$$y = A - B u$$
- **Pendiente de la recta:** $B = \sigma_{\text{pos}}^2 \implies \sigma_{\text{pos}} = \sqrt{B}$.
- **Intersección en el origen:** $A = \ln\left[ N_{\text{sitios}} (1 - p)^2 \right]$.

```
  ln[H(G)] ^
           |  * G=(0,0)  [Intercepto = ln(N(1-p)^2)]
           |   \
           |    \
           |     * {1,0}, {0,1}  (u = (2pi/a)^2)
           |      \
           |       * {1,1}        (u = 2(2pi/a)^2)
           |        \
           |         \
           |          * {2,0}, {0,2}  (u = 4(2pi/a)^2)
           |           \
           +----------------------------------------> |G|^2
                         Pendiente = - sigma_pos^2
```

### Extracción Simultánea de la Fracción de Vacancias ($p$):
Conocido el número de sitios teóricos de la red nominal $N_{\text{sitios}} = N_x \times N_y$:
$$(1 - p)^2 = \frac{e^A}{N_{\text{sitios}}} \implies 1 - p = \frac{e^{A/2}}{\sqrt{N_{\text{sitios}}}} \implies \bbox[10px,border:1px solid #059669,background:#ecfdf5]{
p = 1 - \frac{e^{A/2}}{\sqrt{N_{\text{sitios}}}}
}$$
Esto permite desacoplar analíticamente el desorden térmico $\sigma_{\text{pos}}$ de la fracción de vacancias $p$ mediante una única regresión lineal sobre el plano de difracción.

---

## 6. Conclusiones

1. **Efecto Cuadrático de Vacancias:** La intensidad de difracción coherente decae como $(1-p)^2$, penalizando severamente la altura de pico ante defectos de ocupación.
2. **Conservación de Intensidad:** Toda la energía fotónica que desaparece de los picos de Bragg no se pierde; se redistribuye exactamente en el fondo difuso incoherente $I_{\text{difuso}}(\mathbf{q})$.
3. **Poder del Gráfico de Wilson 2D:** La regresión multiorigen sobre $|\mathbf{G}|^2$ otorga una metodología independiente de curvas de calibración para extraer tanto $\sigma_{\text{pos}}$ como $p$.
