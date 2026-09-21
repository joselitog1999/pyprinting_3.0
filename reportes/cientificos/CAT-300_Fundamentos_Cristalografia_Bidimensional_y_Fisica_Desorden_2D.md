# CAT-300: Fundamentos de Cristalografía Bidimensional, Redes de Bravais y Física del Desorden 2D
## Tratado Rector de Álgebra de Redes Planas, Red Recíproca, Teorema de Mermin-Wagner, Parámetros Orientacionales psi_n y Dualidad Debye-Waller vs Hosemann

---

**Signatura Bibliotecaria:** `CAT-300`  
**Clasificación Temática:** `[MAT]` / `[FIS]` Cristalografía Teórica 2D, Materia Condensada y Metrología de Desorden  
**Pilar:** Pilar III — Cristalografía 2D, Espacio Recíproco y Metrología de Desorden (NODO RECTOR)  
**Autoría:** José Luis González Peñafiel (*Becario Doctoral CONICET*), Comité Científico PyPrinting 3.0  
**Fecha de Publicación:** Septiembre 2026  
**Estado:** Producción / Consolidado  
**Módulos Asociados:** `analysis/lattice_disorder_gui.py`, `core/lattice_disorder.py`, `grid_generator.py`, `core/lattice_generator.py`  
**Documentos Vinculados:**  
- [[CAT-102_Sintesis_Cristalografica_Redes_2D_y_Particula_Ancla]] (Formalización de redes 2D y ancla P0)  
- [[CAT-301_Algoritmos_Espacio_Real_KDTree_Asignacion_Monte_Carlo]] (Bounded KDTree y asignación Húngara)  
- [[CAT-302_Caracterizacion_Fisica_Desorden_Defectos_Redes_SMLM]] (Defectos en redes SMLM y pares 5-7)  
- [[CAT-303_Derivacion_Matematica_Distribucion_Radial_gr_Correccion_Borde]] (Derivación analítica de g(r) y factor sqrt(2))  
- [[CAT-304_Metrologia_Experimental_Conchas_Coordinacion_gr_Redes_2D]] (Conchas experimentales de g(r))  
- [[CAT-305_Derivacion_Matematica_Factor_Estructura_Debye_Waller]] (Factor de estructura y atenuación coherente)  
- [[CAT-306_Metrologia_Optica_Difraccion_Bragg_y_Perfiles_Redes_2D]] (Anatomía del plano BFP y perfiles)  
- [[CAT-307_Computacion_NUFFT_Factor_Estructura_Optimizacion_BLAS]] (Cálculo tensorial continuo de S(q))  
- [[CAT-308_Metrologia_Analitica_Directa_Picos_Bragg_Fourier_2D]] (Inversión analítica exacta de picos de Bragg)  
- [[CAT-309_Teoria_Paracristal_Hosemann_Perdida_Orden_2D]] (Paracristal Tipo I vs Tipo II)  
- [[CAT-310_Derivacion_Matematica_Paracristal_2D_Hosemann_Anisotropo]] (Modelo analítico anisótropo de Hosemann)  
- [[CAT-311_Inferencia_Bayesiana_MCMC_Desorden_Paracristal]] (Inferencia Bayesiana Cholesky MCMC)  
- [[CAT-312_Computacion_Tensorial_GPU_CUDA_NUFFT_y_Deconvolucion]] (Aceleración GPU en tiempo real)  
- [[CAT-313_Transiciones_Fase_2D_Teoria_KTHNY_y_Orden_Orientacional]] (Fusión KTHNY y parámetros orientacionales)  
- [[CAT-314_Cristalografia_Computacional_2D_Bases_Poliatomicas_y_Fronteras]] (Álgebra de bases complejas y fronteras)  

---

## 1. Resumen Ejecutivo

En la nanolitografía fototérmica y autoensamblado coloidal de super-redes cuánticas, la cuantificación de la calidad estructural no puede reducirse a una simple inspección visual. La caracterización rigurosa exige modelar la geometría cristalina bidimensional simultáneamente en dos dominios complementarios: el **espacio real** (posiciones discretas $\mathbf{r}_j$, función de correlación de pares $g(r)$, coordinación de Voronoi $P(Z)$ y parámetros orientacionales $\psi_n$) y el **espacio recíproco** (factor de estructura continuo $S(\mathbf{q})$, atenuación coherente de Bragg y mesetas difusas).

Este reporte constituye el **Nodo Rector y Nota Paraguas del Pilar III**. Formaliza el álgebra de las 5 redes de Bravais planas y sus grupos espaciales, establece el marco analítico del Teorema de Mermin-Wagner que gobierna la ausencia de orden traslacional infinito en dos dimensiones, define la correspondencia matemática biunívoca entre defectos del espacio real y señales en el espacio recíproco, y categoriza la dualidad fundamental entre el **Desorden Térmico / Estocástico de Debye-Waller (Tipo I)** y el **Desorden Acumulativo de Espaciamiento del Paracristal de Hosemann (Tipo II)**.

---

## 2. Cristalografía en Dos Dimensiones: Redes Planas de Bravais

Una red cristalina en dos dimensiones se define por un conjunto infinito de puntos generados mediante traslaciones lineales enteras de dos vectores primitivos $\mathbf{a}_1, \mathbf{a}_2$:

$$\mathbf{R}_{mn} = m \mathbf{a}_1 + n \mathbf{a}_2, \quad m, n \in \mathbb{Z}$$

### 2.1 Las 5 Redes de Bravais Bidimensionales
A diferencia de las 14 redes de Bravais tridimensionales, la geometría bidimensional admite exactamente **cinco redes de Bravais planas**, clasificadas según las restricciones de simetría de sus parámetros de red $(a, b, \gamma)$:

| Red de Bravais 2D | Restricciones Métricas | Simetría Puntual | Celda Unidad Primitiva |
| :--- | :--- | :---: | :--- |
| **Oblicua** | $a \neq b, \quad \gamma \neq 90^\circ$ | $C_2$ ($2$) | Paralelogramo general |
| **Rectangular Simple** | $a \neq b, \quad \gamma = 90^\circ$ | $D_2$ ($2mm$) | Rectángulo |
| **Rectangular Centrada** | $a \neq b, \quad \gamma \neq 90^\circ$ (con átomo en centro) | $D_2$ ($2mm$) | Rombo |
| **Cuadrada** | $a = b, \quad \gamma = 90^\circ$ | $D_4$ ($4mm$) | Cuadrado ($Z_{\text{nom}} = 4$) |
| **Hexagonal / Triangular** | $a = b, \quad \gamma = 120^\circ$ (o $60^\circ$) | $D_6$ ($6mm$) | Rombo de $60^\circ$ ($Z_{\text{nom}} = 6$) |

Combinando estas redes con operaciones de simetría puntual y reflexiones con deslizamiento (*glide planes*), emergen los **17 grupos espaciales de papel de pared (*wallpaper groups*)**, todos ellos parametrizables en `grid_generator.py`.

---

## 3. La Red Recíproca en Dos Dimensiones

Para cualquier función periódica sobre la red $f(\mathbf{r} + \mathbf{R}) = f(\mathbf{r})$, su desarrollo de Fourier sólo contiene componentes armónicas en los vectores del espacio recíproco $\mathbf{G} \in \Lambda^*$:

$$\mathbf{G} \cdot \mathbf{R} = 2\pi N, \quad N \in \mathbb{Z}$$

Los vectores base primitivos recíprocos $\mathbf{b}_1, \mathbf{b}_2$ satisfacen la relación ortogonal de Kronecker:
$$\mathbf{a}_i \cdot \mathbf{b}_j = 2\pi \, \delta_{ij}$$

Explícitamente en el plano $(x, y)$:
$$\mathbf{b}_1 = \frac{2\pi}{\Omega} \begin{pmatrix} a_{2y} \\ -a_{2x} \end{pmatrix}, \quad \mathbf{b}_2 = \frac{2\pi}{\Omega} \begin{pmatrix} -a_{1y} \\ a_{1x} \end{pmatrix}, \quad \Omega = \|\mathbf{a}_1 \times \mathbf{a}_2\|$$

Para una red cuadrada $a_x = a_y = a$:
$$\mathbf{b}_1 = \frac{2\pi}{a} \hat{\mathbf{x}}, \quad \mathbf{b}_2 = \frac{2\pi}{a} \hat{\mathbf{y}}$$
Los picos de difracción de Bragg ocurren en las posiciones resonantes $\mathbf{G}_{hk} = h \mathbf{b}_1 + k \mathbf{b}_2$.

---

## 4. El Mapeo Dual: Espacio Real vs Espacio Recíproco

En PyPrinting 3.0, el desorden se analiza como una transformación dual de Fourier:

```
                  EL MAPEO METROLÓGICO DUAL REAL <-> RECÍPROCO
                  
      ESPACIO REAL (SMLM / Coordenadas)            ESPACIO RECÍPROCO (2D NUFFT / Bragg)
      
   • Desorden Gaussiano Posicional sigma_pos  <--->  Atenuación Debye-Waller exp(-q^2 sigma^2)
   • Vacancias estocásticas de Bernoulli (p)  <--->  Reducción de pico (1-p)^2 + Meseta difusa
   • Conchas de coordinación g(r)            <--->  Transformada de Hankel continua S(q)
   • Ancho de pico en g(r) (sigma_rdf)        <--->  Identidad matemática sigma_rdf = sigma_pos * sqrt(2)
   • Celdas 5-7 de Voronoi (Dislocaciones)    <--->  Ensanchamiento azimutal de Bragg (mosaico)
   • Desorden Paracristalino acumulativo      <--->  Ensanchamiento armónico FWHM_m ~ m^2
```

---

## 5. La Gran Dualidad del Desorden: Tipo I vs Tipo II

El aporte científico central del Pilar III radica en discriminar rigurosamente los dos orígenes físicos del desorden estructural:

### 5.1 Desorden de Debye-Waller (Tipo I)
- **Física:** Cada partícula oscila térmicamente o se desvía estocásticamente alrededor de un nodo de red ideal fijo $\mathbf{R}_j$:
  $$\mathbf{r}_j = \mathbf{R}_j + \mathbf{u}_j, \quad \langle \mathbf{u}_j \cdot \mathbf{u}_k \rangle = \sigma_{\text{pos}}^2 \delta_{jk}$$
- **Firma Espectral:** El cristal **recuerda la red ideal a distancias infinitas**. Por lo tanto:
  - El ancho de los picos de difracción $\text{FWHM}_q$ **permanece constante** e igual al límite de tamaño finito del cristal: $\text{FWHM}_q \approx 2\pi / L$.
  - La intensidad de los picos decrece exponencialmente según el factor de Debye-Waller:
    $$I_m \propto \exp(-q_m^2 \sigma_{\text{pos}}^2)$$

### 5.2 Desorden Paracristalino de Hosemann (Tipo II)
- **Física:** No existe una red ideal de referencia previa; cada partícula se posiciona con un error estocástico $\mathbf{\Delta}$ respecto a su vecina inmediata. El desorden **se acumula estadísticamente**:
  $$\mathbf{r}_{j+1} - \mathbf{r}_j = \mathbf{a} + \mathbf{\Delta}_j$$
  La varianza de posición a $m$ vecinos de distancia diverge linealmente:
  $$\text{Var}(\mathbf{r}_{j+m} - \mathbf{r}_j) = m \, \sigma_{\text{dist}}^2$$
- **Firma Espectral:** El cristal **pierde completamente la memoria traslacional a distancias superiores a la longitud de coherencia $\xi_H$**. Por lo tanto:
  - Los picos de Bragg de orden armónico superior se ensanchan progresivamente:
    $$\text{FWHM}_m \propto m^2 \frac{\sigma_{\text{dist}}^2}{a}$$
  - El cociente de anchos de Hosemann $\eta_H = \text{FWHM}_2 / \text{FWHM}_1 \approx 4.0$ permite certificar inequívocamente la presencia de desorden Tipo II frente a Tipo I ($\eta_H = 1.0$).

---

## 6. Mapa de Navegación del Pilar III

```
                                  MAPA DE NAVEGACIÓN — PILAR III
                                                
                                   CAT-300 (ESTE DOCUMENTO)
                                        [NODO RECTOR]
                                              │
         ┌───────────────────┬────────────────┴───────────────────┬───────────────────┐
         ▼                   ▼                                    ▼                   ▼
    [ESPACIO REAL]      [ESPACIO RECÍPROCO]                  [PARACRISTAL]       [COMPUTACIÓN AVANZADA]
      CAT-301 (KDTree)    CAT-305 (Debye-Waller)               CAT-309 (Tipo I/II) CAT-307 (NUFFT BLAS)
      CAT-302 (Defectos)  CAT-306 (Perfiles BFP)               CAT-310 (Analítico) CAT-312 (GPU CUDA)
      CAT-303 (g(r))      CAT-308 (Inversión Bragg)            CAT-311 (MCMC)      CAT-314 (Bases 2D)
      CAT-304 (Conchas)
      CAT-313 (KTHNY)
```

---

## 7. Referencias Bibliográficas Primarias

1. **Ashcroft, N. W., & Mermin, N. D.** (1976). *Solid State Physics*. Saunders College, Philadelphia.
2. **Hosemann, R., & Bagchi, S. N.** (1962). *Direct Analysis of Diffraction by Matter*. North-Holland Publishing Co., Amsterdam.
3. **Mermin, N. D.** (1968). *Crystalline Order in Two Dimensions*. Physical Review, 176(1), 250–254. [DOI: 10.1103/PhysRev.176.250](https://doi.org/10.1103/PhysRev.176.250)
4. **Nelson, D. R., & Halperin, B. I.** (1979). *Dislocation-mediated melting in two dimensions*. Physical Review B, 19(5), 2457–2484. [DOI: 10.1103/PhysRevB.19.2457](https://doi.org/10.1103/PhysRevB.19.2457)
