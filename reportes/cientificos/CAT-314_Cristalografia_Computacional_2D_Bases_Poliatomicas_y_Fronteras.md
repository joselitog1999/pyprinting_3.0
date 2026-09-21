# CAT-314: Cristalografía Computacional 2D: Mallas, Bases Poliatómicas y Fronteras Poligonales
## Álgebra Tensorial de Redes Planas, Parametrización de Subredes Honeycomb/Kagome/Lieb, Algoritmos de Acotamiento Poligonal y Criterio de Exclusión d_min

---

**Signatura Bibliotecaria:** `CAT-314`  
**Clasificación Temática:** `[MAT]` / `[CMP]` Cristalografía Computacional, Métodos Geométricos y Simulación Numérica 2D  
**Pilar:** Pilar III — Cristalografía 2D, Espacio Recíproco y Metrología de Desorden  
**Autoría:** José Luis González Peñafiel (*Becario Doctoral CONICET*), Comité Científico PyPrinting 3.0  
**Fecha de Publicación:** Septiembre 2026  
**Estado:** Producción / Consolidado  
**Módulos Asociados:** `grid_generator.py`, `core/lattice_generator.py`, `core/lattice_disorder.py` (`generate_ideal_lattice_template`)  
**Documentos Vinculados:**  
- [[CAT-102_Sintesis_Cristalografica_Redes_2D_y_Particula_Ancla]] (Formalización de redes 2D y ancla P0)  
- [[CAT-301_Algoritmos_Espacio_Real_KDTree_Asignacion_Monte_Carlo]] (Bounded KDTree y asignación de grilla)  
- [[CAT-313_Transiciones_Fase_2D_Teoria_KTHNY_y_Orden_Orientacional]] (Simetría orientacional y parámetros psi_n)  

---

## 1. Resumen Ejecutivo

La síntesis fototérmica de redes bidimensionales y su posterior metrología de desorden requieren una definición algorítmica unificada e invariante de la geometría cristalina. Mientras que la teoría de sólidos elemental asume redes periódicas infinitas, los experimentos en nanotecnología operan sobre **dominios finitos confinados** (discos, hexágonos o rectángulos de unos pocos micrómetros) decorados con bases atómicas complejas (como grafeno/honeycomb, kagomé o Lieb) y sujetos a restricciones mecánicas estrictas de proximidad coloidal para evitar agregación incontrolada.

Este reporte formaliza el motor cristalográfico de `core/lattice_generator.py` y su puente en `core/lattice_disorder.py`. Se deducen las matrices de transformación métrica entre coordenadas fraccionales y cartesianas, se explicita la parametrización de bases poliatómicas (específicamente la convención de laboratorio $(u_2, v_2) = (1/3, 1/3)$ para redes honeycomb), se formalizan los algoritmos continuos de acotamiento poligonal mediante el número de bobinado (*Winding Number*), y se demuestra el algoritmo de exclusión por vecindad $d_{\text{min}}$ acelerado por árbol KDTree.

---

## 2. Álgebra Tensorial de Redes Planas de Bravais

Toda red de Bravais periódica en dos dimensiones se construye a partir de dos vectores primitivos $\mathbf{a}_1, \mathbf{a}_2 \in \mathbb{R}^2$. Eligiendo $\mathbf{a}_1$ sobre el eje de abscisas:

$$\mathbf{a}_1 = \begin{pmatrix} a \\ 0 \end{pmatrix}, \quad \mathbf{a}_2 = \begin{pmatrix} b \cos\gamma \\ b \sin\gamma \end{pmatrix}$$

donde $a, b > 0$ son las constantes de red y $\gamma \in (0, \pi)$ es el ángulo inter-axial.

### 2.1 Matriz Generatriz y Tensor Métrico
La matriz generatriz de red $\mathbf{A} \in \mathbb{R}^{2 \times 2}$ mapea índices enteros o fraccionales $(u, v)^T$ a posiciones cartesianas $(x, y)^T$:

$$\mathbf{r} = \mathbf{A} \begin{pmatrix} u \\ v \end{pmatrix} = \begin{pmatrix} a & b \cos\gamma \\ 0 & b \sin\gamma \end{pmatrix} \begin{pmatrix} u \\ v \end{pmatrix}$$

El tensor métrico de la celda unidad covariante es:
$$g_{ij} = \mathbf{a}_i \cdot \mathbf{a}_j = \begin{pmatrix} a^2 & ab \cos\gamma \\ ab \cos\gamma & b^2 \end{pmatrix}$$
El área de la celda unidad primitiva es $\Omega = \sqrt{\det(g)} = ab \sin\gamma$.

---

## 3. Parametrización de Bases Poliatómicas

Una red cristalina general se define como la convolución de una red de Bravais de Bravais con una base finita de $N_b$ átomos:
$$\Lambda = \bigcup_{m, n \in \mathbb{Z}} \bigcup_{k=1}^{N_b} \left\{ m \mathbf{a}_1 + n \mathbf{a}_2 + \boldsymbol{\tau}_k \right\}$$
donde $\boldsymbol{\tau}_k = u_k \mathbf{a}_1 + v_k \mathbf{a}_2$ ($u_k, v_k \in [0, 1)$).

```
Red Triangular (Z=6)           Red Honeycomb / Grafeno (Z=3)
       *     *                        A --- B
      / \   / \                      /       \
     * --- * --- *                   B         A
      \ /   \ /                      \       /
       *     *                        A --- B
```

### 3.1 Red Honeycomb / Grafeno (Base Biatómica)
La red hexagonal honeycomb surge de una red de Bravais triangular con $a = b$ y $\gamma = 60^\circ$ ($\pi/3$) o $\gamma = 120^\circ$ ($2\pi/3$), decorada con dos átomos por celda:
- **Subred A**: $\boldsymbol{\tau}_1 = (u_1, v_1) = (0.0, 0.0)$.
- **Subred B**: $\boldsymbol{\tau}_2 = (u_2, v_2) = (1/3, 1/3)$ (convención de impresión del laboratorio, parametrizable en la GUI).
Cada sitio tiene coordinación nominal $Z=3$, formando hexágonos vacíos rodeados de enlaces alternados.

### 3.2 Red de Kagomé (Base Triatómica)
Red triangular con $\gamma = 60^\circ$ decorada con $N_b = 3$ sitios:
$$\boldsymbol{\tau}_1 = (0, 0), \quad \boldsymbol{\tau}_2 = \left(\frac{1}{2}, 0\right), \quad \boldsymbol{\tau}_3 = \left(0, \frac{1}{2}\right)$$
Genera triángulos y hexágonos entrelazados con coordinación $Z=4$, fundamental en física de bandas planas (*flat bands*).

---

## 4. Algoritmos de Acotamiento y Fronteras Poligonales

En `core/lattice_generator.py::BoundingGeometry`, se evalúa si un nodo candidato $\mathbf{r} = (x, y)$ se encuentra dentro del recinto físico de impresión o análisis:

### 4.1 Envolvente Circular
$$\mathbf{r} \in \Omega_{\text{circ}} \iff x^2 + y^2 \le R^2$$

### 4.2 Envolvente Hexagonal Regular
Para un hexágono regular de apotema o radio $R$:
$$\mathbf{r} \in \Omega_{\text{hex}} \iff \max\left( \sqrt{3}|x| + |y|, \, 2|y| \right) \le \sqrt{3} R$$

### 4.3 Polígono Convexo o No Convexo Arbitrario (Número de Bobinado)
Dado un polígono de vértices $\{V_0, V_1, \dots, V_m = V_0\}$, el número de bobinado $W(P)$ respecto a un punto $P(x, y)$ cuenta cuántas veces el contorno rodea al punto:
$$W(P) = \frac{1}{2\pi} \sum_{i=0}^{m-1} \arctan2\left( (x_i - x)(y_{i+1} - y) - (y_i - y)(x_{i+1} - x), \, (x_i - x)(x_{i+1} - x) + (y_i - y)(y_{i+1} - y) \right)$$
$$P \in \text{int}(\mathcal{P}) \iff W(P) \neq 0$$

---

## 5. Algoritmo de Exclusión Espacial $d_{\text{min}}$ por KDTree

En nanolitografía coloidal, si dos coordenadas objetivo se encuentran a una distancia $d < d_{\text{min}}$ (donde $d_{\text{min}} \sim 1.5 - 2.0 \times$ el diámetro de la nanopartícula), la captura fototérmica inducirá colisiones hidrodinámicas y coalescencia descontrolada.

En `core/lattice_generator.py`, se filtra la malla mediante indexación espacial:
```python
# Pseudocódigo del filtro de exclusión d_min
kdtree = KDTree(coordinates)
pairs_too_close = kdtree.query_pairs(r=d_min)
# Eliminación codiciosa (greedy) de sitios conflictivos
```
Garantiza que la plantilla sintética cumpla $\min_{i \neq j} \|\mathbf{r}_i - \mathbf{r}_j\| \ge d_{\text{min}}$ en tiempo $\mathcal{O}(N \log N)$.

---

## 6. Referencias Bibliográficas Primarias

1. **Ashcroft, N. W., & Mermin, N. D.** (1976). *Solid State Physics*. Holt, Rinehart and Winston. [Capítulos 4 y 5].
2. **Hormann, K., & Agathos, A.** (2001). *The point in polygon problem for arbitrary polygons*. Computational Geometry, 20(3), 131–144. [DOI: 10.1016/S0925-7721(01)00012-8](https://doi.org/10.1016/S0925-7721(01)00012-8)
3. **Manevitch, V. K., et al.** (2007). *Mathematical modeling of 2D lattice self-assembly*. Physical Review E, 76(5), 051602.
