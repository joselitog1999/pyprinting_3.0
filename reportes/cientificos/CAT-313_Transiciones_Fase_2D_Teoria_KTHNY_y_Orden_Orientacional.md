# CAT-313: Transiciones de Fase en Redes 2D: Teoría KTHNY, Fusión de Defectos y Parámetros Orientacionales $\psi_n$
## Desacople Topológico de Dislocaciones/Disclinaciones, Pérdida de Orden Cuasi-Largo Alcance y Métricas Orientacionales Cuadradas, Hexagonales y Honeycomb

---

**Signatura Bibliotecaria:** `CAT-313`  
**Clasificación Temática:** `[FIS]` / `[MAT]` Física de la Materia Condensada, Transiciones Topológicas y Mecánica Estadística 2D  
**Pilar:** Pilar III — Cristalografía 2D, Espacio Recíproco y Metrología de Desorden  
**Autoría:** José Luis González Peñafiel (*Becario Doctoral CONICET*), Comité Científico PyPrinting 3.0  
**Fecha de Publicación:** Septiembre 2026  
**Estado:** Producción / Consolidado  
**Módulos Asociados:** `analysis/lattice_disorder_gui.py`, `core/lattice_disorder.py`, `grid_generator.py`  
**Documentos Vinculados:**  
- [[CAT-302_Caracterizacion_Fisica_Desorden_Defectos_Redes_SMLM]] (Defectos de Voronoi y orden local)  
- [[CAT-309_Teoria_Paracristal_Hosemann_Perdida_Orden_2D]] (Paracristal vs Debye-Waller)  
- [[CAT-308_Metrologia_Analitica_Directa_Picos_Bragg_Fourier_2D]] (Firma en espacio recíproco)  
- [[CAT-303_Derivacion_Matematica_Distribucion_Radial_gr_Correccion_Borde]] (Correlación radial g(r))  

---

## 1. Resumen Ejecutivo

La caracterización de redes periódicas bidimensionales generadas por nanolitografía óptica o ensamblado coloidal enfrenta una frontera física fundamental: **en dos dimensiones no existe orden posicional de verdadero largo alcance a temperatura finita**. Según el Teorema de Mermin-Wagner, las fluctuaciones fonónicas acústicas de gran longitud de onda divergen logarítmicamente con el tamaño del sistema, destruyendo la periodicidad infinita clásica. En su lugar, el estado sólido en 2D se describe como un cristal con **orden traslacional de cuasi-largo alcance** (con decaimiento algebraico de correlaciones) y **orden orientacional de enlace de verdadero largo alcance**.

Este reporte fundamenta rigurosamente el mecanismo de fusión bidimensional mediado por defectos topológicos según la **Teoría KTHNY** (Kosterlitz-Thouless-Halperin-Nelson-Young). Se demuestra matemáticamente cómo el desacople de pares ligados de dislocaciones (dipolos 5-7 de Voronoi) genera la **fase hexática**, un estado intermedio de la materia que preserva memoria angular sin rigidez traslacional, y cómo su posterior disociación en disclinaciones libres induce la fase líquida isótropa. Asimismo, se deduce la formulación analítica de los parámetros de orden orientacional de enlace locales y globales $\psi_4$ (redes cuadradas), $\psi_6$ (redes hexagonales/triangulares) y $\psi_3$ (redes honeycomb/grafeno de base biatómica), gobernando la lógica de diagnóstico y conmutación dinámica implementada en el Visor 3 de `analysis/lattice_disorder_gui.py`.

---

## 2. La Singularidad de la Materia en Dos Dimensiones: Mermin-Wagner

### 2.1 Divergencia de Fluctuaciones Acústicas
Considérese una red periódica 2D con vector de desplazamiento térmico/estocástico $\mathbf{u}(\mathbf{r})$. En la aproximación elástica armónica continua, la energía libre elástica está dominada por los coeficientes de Lamé $\mu$ (módulo de corte) y $\lambda$ (módulo de compresión):

$$\mathcal{F} = \frac{1}{2} \int d^2 r \left[ 2\mu \, u_{ij}^2 + \lambda \, (u_{kk})^2 \right]$$

Descomponiendo los desplazamientos en modos de Fourier $\mathbf{u}(\mathbf{q})$, el teorema de equipartición establece que la varianza media de las fluctuaciones térmicas espaciales a temperatura $T$ está dada por:

$$\langle |\mathbf{u}(\mathbf{q})|^2 \rangle = \frac{k_B T}{\mu \, q^2}$$

Integrando en el espacio bidimensional de vectores de onda $\mathbf{q}$:

$$\langle \mathbf{u}^2 \rangle = \frac{k_B T}{(2\pi)^2} \int_{q_{\text{min}}}^{q_{\text{max}}} \frac{2\pi q \, dq}{\mu \, q^2} = \frac{k_B T}{2\pi \mu} \ln\left( \frac{q_{\text{max}}}{q_{\text{min}}} \right)$$

En el límite termodinámico de tamaño de sistema infinito ($L \to \infty$), el corte infrarrojo se anula ($q_{\text{min}} = 2\pi / L \to 0$), provocando una **divergencia logarítmica**:

$$\langle \mathbf{u}^2 \rangle \propto \frac{k_B T}{\mu} \ln\left( \frac{L}{a} \right) \xrightarrow[L \to \infty]{} \infty$$

Esta divergencia implica que el desplazamiento relativo cuadrático medio entre dos partículas separadas por una distancia espacial $r$ escala como:

$$\langle [\mathbf{u}(\mathbf{r}) - \mathbf{u}(\mathbf{0})]^2 \rangle \sim \frac{k_B T}{\pi \mu} \ln\left(\frac{r}{a}\right)$$

### 2.2 Decaimiento Algebraico de la Correlación Traslacional
A diferencia de un cristal 3D donde la función de correlación traslacional para un vector de red recíproca $\mathbf{G}$ converge a una constante finita no nula:
$$C_{\mathbf{G}}(\mathbf{r}) = \langle e^{i \mathbf{G} \cdot [\mathbf{u}(\mathbf{r}) - \mathbf{u}(\mathbf{0})]} \rangle \xrightarrow[r\to\infty]{} \text{constante} > 0 \quad (D=3)$$

en dos dimensiones la correlación decae algebraicamente como una ley de potencias (orden de cuasi-largo alcance):

$$C_{\mathbf{G}}(\mathbf{r}) = \exp\left( -\frac{1}{2} |\mathbf{G}|^2 \langle [\mathbf{u}(\mathbf{r}) - \mathbf{u}(\mathbf{0})]^2 \rangle \right) \sim \left( \frac{a}{r} \right)^{\eta_{\mathbf{G}}}$$

con un exponente crítico:
$$\eta_{\mathbf{G}} = \frac{k_B T}{4\pi \mu} \frac{3\mu + \lambda}{2\mu + \lambda} |\mathbf{G}|^2$$

---

## 3. El Escenario KTHNY de Fusión en Dos Etapas

A diferencia de la fusión tridimensional clásica (una transición discontinua de primer orden con calor latente), la fusión en 2D ocurre típicamente a través de **dos transiciones continuas sucesivas tipo Kosterlitz-Thouless**, mediadas por el desacople térmico o inducido por desorden de defectos topológicos:

```
[SÓLIDO 2D] 
  Orden traslacional: Cuasi-largo alcance (C_G(r) ~ r^-eta)
  Orden orientacional: Verdadero largo alcance (g_n(r) ~ const)
  Defectos: Pares ligados de dislocaciones (Dipolos 5-7 neutros)
       │
       ▼  Transición Sólido -> Hexática (Desacople de Dislocaciones a T_m)
[FASE HEXÁTICA]
  Orden traslacional: Corto alcance exponencial (C_G(r) ~ exp(-r/xi_T))
  Orden orientacional: Cuasi-largo alcance (g_n(r) ~ r^-eta_n, con eta_n <= 1/4)
  Defectos: Dislocaciones libres aisladas (b != 0)
       │
       ▼  Transición Hexática -> Líquido (Disociación en Disclinaciones a T_i)
[LÍQUIDO ISÓTROPO]
  Orden traslacional: Corto alcance (exp(-r/xi))
  Orden orientacional: Corto alcance exponencial (g_n(r) ~ exp(-r/xi_n))
  Defectos: Disclinaciones libres aisladas (Anillos Voronoi 5 y 7 sueltos)
```

---

## 4. Clasificación Topológica de Defectos en Redes Planas

El análisis local de vecinos mediante la **Teselación de Voronoi** asigna a cada partícula un polígono cuyos lados representan la mediatriz con sus vecinos más cercanos.

### 4.1 Disclinaciones Libres (Vórtices de Orientación)
Una disclinación representa una rotación de los enlaces cristalinos al rodear un circuito cerrado. En una red triangular/hexagonal de coordinación nominal $Z_0 = 6$:
- **Disclinación Positiva**: Celda pentagonal ($Z = 5$). Introduce un defecto de ángulo de $+60^\circ$ ($+\pi/3$). Corresponde a un exceso local de materia (carga topológica $q = +1$).
- **Disclinación Negativa**: Celda heptagonal ($Z = 7$). Introduce un defecto de ángulo de $-60^\circ$ ($-\pi/3$). Corresponde a un déficit local de materia (carga topológica $q = -1$).

### 4.2 Dislocaciones (Dipolos 5-7 Neutros)
Una **dislocación** con vector de Burgers $\mathbf{b}$ equivale topológicamente a un par estrechamente ligado de una celda pentagonal ($Z=5$) y una celda heptagonal ($Z=7$) en contacto directo:
$$q_{\text{tot}} = (+1) + (-1) = 0$$

La energía libre de un par ligado dislocación-antidislocación separado por una distancia $d$ es:
$$\mathcal{F}_{\text{par}} = 2 E_{\text{core}} + \frac{\mu (\mu + \lambda)}{\pi (2\mu + \lambda)} |\mathbf{b}|^2 \ln\left( \frac{d}{a} \right) - 2 k_B T \ln\left( \frac{d}{a} \right)$$

A la temperatura crítica de fusión $T_m$:
$$k_B T_m = \frac{\mu (\mu + \lambda)}{2\pi (2\mu + \lambda)} |\mathbf{b}|^2$$
la entropía supera la energía elástica logarítmica, provocando la proliferación espontánea de dislocaciones libres y destruyendo el orden traslacional.

---

## 5. Formulación Analítica de los Parámetros de Orden Orientacional de Enlace

Aun cuando el orden traslacional se destruya ($C_{\mathbf{G}}(r) \to e^{-r/\xi}$), las orientaciones angulares de los enlaces moleculares pueden permanecer correlacionadas en distancias macrométricas. Para cuantificar este orden, se definen los **Parámetros de Orden Orientacional de Enlace (Bond-Orientational Order Parameters)**.

### 5.1 Parámetro Local de Partícula
Para una partícula centrada en $\mathbf{r}_j$, con $Z_j$ vecinos inmediatos coordinados determinados por la teselación de Voronoi:

$$\psi_n(\mathbf{r}_j) = \frac{1}{Z_j} \sum_{k=1}^{Z_j} \exp\left( i \, n \, \theta_{jk} \right)$$

donde:
- $n$: Grado de simetría angular de la red cristalina ($n=4, 6, 3$).
- $Z_j$: Número de vecinos inmediatos de la celda de Voronoi.
- $\theta_{jk}$: Ángulo azimutal en el plano $(x, y)$ del enlace que une la partícula $j$ con su vecino $k$, respecto al eje de referencia horizontal:
  $$\theta_{jk} = \text{atan2}(y_k - y_j, \, x_k - x_j)$$

### 5.2 Parámetro de Orden Global
El orden orientacional macroscópico de toda la muestra se obtiene promediando sobre las $N$ partículas evaluadas:

$$\Psi_n = \frac{1}{N} \sum_{j=1}^N \psi_n(\mathbf{r}_j)$$

El módulo $|\Psi_n| \in [0, 1]$ es el parámetro de orden escalar:
- $|\Psi_n| = 1.0$: Cristal perfecto con alineación angular idéntica en toda la red.
- $|\Psi_n| \approx 0.0$: Líquido isótropo o desorden amorfo completo.

---

## 6. Mapeo por Familias Cristalográficas en PyPrinting 3.0

En `analysis/lattice_disorder_gui.py` y `core/lattice_disorder.py`, el motor adapta automáticamente la simetría $n$ y la coordinación nominal de Voronoi $Z_{\text{nom}}$ según la familia cristalina seleccionada:

### 6.1 Red Cuadrada y Rectangular ($n = 4$, $Z_{\text{nom}} = 4$)
En una red cuadrada ideal, los cuatro enlaces inmediatos se ubican en ángulos $\theta_k = \theta_0 + k \frac{\pi}{2}$ ($k = 0, 1, 2, 3$). Multiplicando por $n = 4$:
$$4 \theta_k = 4\theta_0 + 2\pi k \equiv 4\theta_0 \pmod{2\pi}$$
$$\psi_4(\mathbf{r}_j) = \frac{1}{4} \sum_{k=1}^4 e^{i 4 \theta_0} = e^{i 4 \theta_0} \implies |\psi_4| = 1.0$$

### 6.2 Red Hexagonal y Triangular ($n = 6$, $Z_{\text{nom}} = 6$)
Para la red hexagonal monatómica de Bravais, los seis vecinos forman ángulos en múltiplos de $60^\circ$ ($\pi/3$):
$$6 \theta_k = 6\theta_0 + 2\pi k \equiv 6\theta_0 \pmod{2\pi}$$
$$\psi_6(\mathbf{r}_j) = \frac{1}{6} \sum_{k=1}^6 e^{i 6 \theta_0} = e^{i 6 \theta_0} \implies |\psi_6| = 1.0$$
En la fase hexática, el decaimiento espacial de la correlación orientacional es algebraico:
$$g_6(r) = \langle \psi_6(\mathbf{r}) \psi_6^*(\mathbf{0}) \rangle \sim r^{-\eta_6}, \quad \eta_6 \le \frac{1}{4}$$

### 6.3 Red Honeycomb / Grafeno ($n = 3$, $Z_{\text{nom}} = 3$, Base Biatómica)
La red honeycomb no es una red de Bravais monatómica, sino una red triangular con base biatómica (Subred A y Subred B). Cada átomo posee exactamente $Z_{\text{nom}} = 3$ primeros vecinos a $120^\circ$ ($2\pi/3$):
$$3 \theta_k = 3\theta_0 + 2\pi k \equiv 3\theta_0 \pmod{2\pi}$$
$$\psi_3(\mathbf{r}_j) = \frac{1}{3} \sum_{k=1}^3 e^{i 3 \theta_0} = e^{i 3 \theta_0} \implies |\psi_3| = 1.0$$

> [!NOTE]
> **Conmutación Dinámica en la GUI**:
> En el Visor 3 del Analizador de Desorden (`analysis/lattice_disorder_gui.py`), el histograma de Voronoi y el cálculo orientacional leen dinámicamente el `n_fold` de los datos: conmuta a $|\psi_4|$ para cuadrada, $|\psi_6|$ para hexagonal y $|\psi_3|$ para honeycomb, resaltando la barra $Z_{\text{nom}}$ con el color de éxito `#a6e3a1`.

---

## 7. Función de Correlación Orientacional $g_n(r)$

La función de correlación espacial orientacional normalizada se calcula como:

$$g_n(r) = \frac{\langle \psi_n(\mathbf{r}_i) \, \psi_n^*(\mathbf{r}_j) \rangle}{\langle |\psi_n|^2 \rangle}, \quad r = |\mathbf{r}_i - \mathbf{r}_j|$$

| Régimen Físico | Estado de la Materia | Comportamiento Asintótico de $g_n(r)$ | Parámetro Global $|\Psi_n|$ |
| :--- | :--- | :--- | :--- |
| **Sólido 2D** | Cristal perfecto / elástico | $g_n(r) \to \text{constante} > 0$ | $|\Psi_n| \approx 0.85 - 1.0$ |
| **Fase Hexática / Orientacional** | Fusión traslacional con orden de enlace | $g_n(r) \sim r^{-\eta_n} \quad (\eta_n \le 1/4)$ | $|\Psi_n| \approx 0.40 - 0.85$ |
| **Líquido Isótropo** | Desorden topológico completo | $g_n(r) \sim \exp(-r / \xi_n)$ | $|\Psi_n| < 0.20$ |

---

## 8. Presupuesto Metrológico y Criterios de Calidad en SMLM

Al procesar coordenadas de super-resolución ópticas (SMLM):
1. **Ruido de Localización (Jitter)**: La imprecisión de localización $\sigma_{\text{loc}} \approx 6.55\ \text{nm}$ (ver [[CAT-203_Presupuesto_Incertidumbre_Metrologica_ISOGUM_Microscopia]]) introduce un aparente decremento de $|\psi_n|$:
   $$|\psi_n|_{\text{aparente}} \approx |\psi_n|_{\text{real}} \left( 1 - \frac{n^2 \sigma_{\text{loc}}^2}{2 a^2} \right)$$
2. **Efecto de Borde de Confinamiento**: En patrones acotados de tamaño $L \sim 5\ \mu\text{m}$, las partículas perimetrales carecen de celdas de Voronoi cerradas. Por ello, el software excluye estrictamente las celdas de frontera (`voronoi['is_internal']`), evitando subestimar la fracción de coordinación regular $P(Z_{\text{nom}})$.

---

## 9. Referencias Bibliográficas Primarias

1. **Mermin, N. D., & Wagner, H.** (1966). *Absence of Ferromagnetism or Antiferromagnetism in One- or Two-Dimensional Isotropic Heisenberg Models*. Physical Review Letters, 17(22), 1133–1136. [DOI: 10.1103/PhysRevLett.17.1133](https://doi.org/10.1103/PhysRevLett.17.1133)
2. **Kosterlitz, J. M., & Thouless, D. J.** (1973). *Ordering, metastability and phase transitions in two-dimensional systems*. Journal of Physics C: Solid State Physics, 6(7), 1181–1203. [DOI: 10.1088/0022-3719/6/7/010](https://doi.org/10.1088/0022-3719/6/7/010)
3. **Halperin, B. I., & Nelson, D. R.** (1978). *Theory of Two-Dimensional Melting*. Physical Review Letters, 41(2), 121–124. [DOI: 10.1103/PhysRevLett.41.121](https://doi.org/10.1103/PhysRevLett.41.121)
4. **Young, A. P.** (1979). *Melting and the vector Coulomb gas in two dimensions*. Physical Review B, 19(4), 1855–1866. [DOI: 10.1103/PhysRevB.19.1855](https://doi.org/10.1103/PhysRevB.19.1855)
5. **Gasser, U., Weeks, E. R., Schofield, A., Pusey, P. N., & Weitz, D. A.** (2001). *Real-space imaging of nucleation and growth in colloidal crystallization*. Science, 292(5515), 258–262. [DOI: 10.1126/science.1058457](https://doi.org/10.1126/science.1058457)
