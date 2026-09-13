# Reporte Científico Canónico: Deducción Matemática del Paracristal 2D de Hosemann Anisótropo 📐💎

**Biblioteca Científica Canónica — Pilar III: Cristalografía 2D, Espacio Recíproco y Metrología de Desorden**  
**Signatura Canónica**: `CAT-310` | **Clúster**: `[MAT]` (Matemáticas)  
**Laboratorio de Nanofotónica — Instituto de Nanosistemas (INS-UNSAM / CONICET)**  
**Autor Principal**: José Luis González Peñafiel (*Físico EPN, Becario Doctoral CONICET, INS-UNSAM*)  
**Fecha de Publicación**: Septiembre 2026 | **Estado**: Vigente y Certificado por QA  
**Módulos del Sistema Asociados**: `core/lattice_disorder.py`, `analysis/lattice_disorder_gui.py`  
**Referencias Cruzadas**: `[[CAT-303_Derivacion_Matematica_Distribucion_Radial_gr_Correccion_Borde]]`, `[[CAT-305_Derivacion_Matematica_Factor_Estructura_Debye_Waller]]`, `[[CAT-306_Metrologia_Optica_Difraccion_Bragg_y_Perfiles_Redes_2D]]`, `[[CAT-307_Computacion_NUFFT_Factor_Estructura_Optimizacion_BLAS]]`, `[[CAT-308_Metrologia_Analitica_Directa_Picos_Bragg_Fourier_2D]]`, `[[CAT-309_Teoria_Paracristal_Hosemann_Perdida_Orden_2D]]`, `[[CAT-311_Inferencia_Bayesiana_MCMC_Desorden_Paracristal]]`

---

## 1. Resumen Ejecutivo

En la física del estado sólido y la nanolitografía óptica, la pérdida de periodicidad traslacional en redes 2D puede originarse por dos mecanismos físicamente distintos:
1. **Desorden de Sitio o Tipo I (Debye-Waller)**: Cada partícula fluctúa independientemente alrededor de un nodo de red ideal fijo en el espacio (`[[CAT-305_Derivacion_Matematica_Factor_Estructura_Debye_Waller]]`). El orden de largo alcance persiste intacto y los picos de Bragg conservan un ancho a media altura ($\text{FWHM}$) independiente del orden de difracción $(h, k)$.
2. **Desorden Acumulativo o Tipo II (Paracristal de Hosemann)**: Cada partícula se posiciona con respecto a sus vecinas inmediatas mediante un vector de enlace estocástico. Las desviaciones se acumulan cuadráticamente con la distancia, destruyendo exponencialmente el orden de largo alcance y ensanchando progresivamente los picos de difracción de orden superior ($\text{FWHM}_h \propto h^2$, `[[CAT-309_Teoria_Paracristal_Hosemann_Perdida_Orden_2D]]`).

Este reporte formaliza la **deducción analítica rigurosa del Factor de Estructura Estático 2D para un Paracristal Anisótropo Bidimensional**, extendiendo la teoría unidimensional clásica de Rolf Hosemann (1950) hacia mallas cristalinas continuas con tensores de fluctuación de segundo orden $\mathbf{\Sigma}_{10}$ y $\mathbf{\Sigma}_{01}$, derivando sus límites asintóticos, la estabilidad numérica ante polos singulares y la formulación formal de la función de log-verosimilitud para inferencia Bayesiana.

---

## 2. Definición Estocástica de la Red Paracristalina 2D

Sea una red bidimensional cuyos nodos se indexan mediante el par entero $(m, n) \in \mathbb{Z}^2$. La posición del nodo $(m, n)$ con respecto al origen $(0, 0)$ es el resultado de la suma convolutiva de $m$ pasos a lo largo del eje fundamental 1 y $n$ pasos a lo largo del eje fundamental 2:

$$\mathbf{R}_{m, n} = \sum_{i=1}^m \mathbf{a}_{1}^{(i)} + \sum_{j=1}^n \mathbf{a}_{2}^{(j)}$$

donde cada vector de enlace elemental $\mathbf{a}_1^{(i)}$ y $\mathbf{a}_2^{(j)}$ es una variable aleatoria continua bidimensional independiente e idénticamente distribuida (i.i.d.) gobernada por las densidades de probabilidad $P_{10}(\mathbf{r})$ y $P_{01}(\mathbf{r})$, respectivamente.

```
                              ESQUEMA DE ACUMULACIÓN PARACRISTALINA
                 
                 (0,2) o───────────────o (1,2) ──────────────o (2,2)
                       │   a_2         │                     │
                       │               │   a_2               │
                 (0,1) o───────────────o (1,1) ──────────────o (2,1)
                       │   a_2         │                     │  ▲ Desviación
                       │       a_1     │       a_1           │  │ acumulada
                 (0,0) ●───────────────o (1,0) ──────────────o (2,0)
                       Origen                                   sigma^2 ~ m + n
```

Bajo la hipótesis de fluctuaciones gaussianas anisótropas alrededor de los vectores de red medios $\langle \mathbf{a}_1 \rangle = \mathbf{a}_1^0$ y $\langle \mathbf{a}_2 \rangle = \mathbf{a}_2^0$:

$$P_{10}(\mathbf{r}) = \frac{1}{2\pi \sqrt{\det \mathbf{\Sigma}_{10}}} \exp\left( -\frac{1}{2} (\mathbf{r} - \mathbf{a}_1^0)^T \mathbf{\Sigma}_{10}^{-1} (\mathbf{r} - \mathbf{a}_1^0) \right)$$

$$P_{01}(\mathbf{r}) = \frac{1}{2\pi \sqrt{\det \mathbf{\Sigma}_{01}}} \exp\left( -\frac{1}{2} (\mathbf{r} - \mathbf{a}_2^0)^T \mathbf{\Sigma}_{01}^{-1} (\mathbf{r} - \mathbf{a}_2^0) \right)$$

donde $\mathbf{\Sigma}_{10}$ y $\mathbf{\Sigma}_{01}$ son tensores simétricos definidos positivos de dimensión $2 \times 2$:

$$\mathbf{\Sigma}_{10} = \begin{pmatrix} \sigma_{11}^{(10)} & \sigma_{12}^{(10)} \\ \sigma_{12}^{(10)} & \sigma_{22}^{(10)} \end{pmatrix}, \quad \mathbf{\Sigma}_{01} = \begin{pmatrix} \sigma_{11}^{(01)} & \sigma_{12}^{(01)} \\ \sigma_{12}^{(01)} & \sigma_{22}^{(01)} \end{pmatrix}$$

---

## 3. Factor de Estructura de Red y Transformadas de Fourier de Coordinación

El factor de interferencia total de la red paracristalina infinita se define en mecánica estadística como la transformada de Fourier de la función de distribución de densidad de pares:

$$Z(\mathbf{q}) = \sum_{m=-\infty}^{\infty} \sum_{n=-\infty}^{\infty} \langle \exp\left( -i \mathbf{q} \cdot \mathbf{R}_{m, n} \right) \rangle$$

Dado que las fluctuaciones en direcciones ortogonales son estocásticamente independientes en el modelo de Hosemann decoupled:

$$\langle \exp\left( -i \mathbf{q} \cdot \mathbf{R}_{m, n} \right) \rangle = \langle \exp\left( -i \mathbf{q} \cdot \sum_{i=1}^m \mathbf{a}_1^{(i)} \right) \rangle \cdot \langle \exp\left( -i \mathbf{q} \cdot \sum_{j=1}^n \mathbf{a}_2^{(j)} \right) \rangle$$

Por el teorema del producto para variables aleatorias independientes, el valor esperado de la suma es el producto de las funciones características individuales:

$$\langle \exp\left( -i \mathbf{q} \cdot \sum_{i=1}^m \mathbf{a}_1^{(i)} \right) \rangle = \left[ \mathbf{\Phi}_{10}(\mathbf{q}) \right]^m \quad (m \ge 0)$$

$$\langle \exp\left( -i \mathbf{q} \cdot \sum_{i=1}^{|m|} (-\mathbf{a}_1^{(i)}) \right) \rangle = \left[ \mathbf{\Phi}_{10}^*(\mathbf{q}) \right]^{|m|} \quad (m < 0)$$

### 3.1 Transformadas de Fourier de Enlace $\mathbf{\Phi}_{10}(\mathbf{q})$ y $\mathbf{\Phi}_{01}(\mathbf{q})$
Aplicando la propiedad de la transformada de Fourier de densidades normales multivariadas:

$$\mathbf{\Phi}_{10}(\mathbf{q}) = \int_{\mathbb{R}^2} P_{10}(\mathbf{r}) e^{-i \mathbf{q} \cdot \mathbf{r}} d^2\mathbf{r} = \exp\left( -i \mathbf{q} \cdot \mathbf{a}_1^0 - \frac{1}{2} \mathbf{q}^T \mathbf{\Sigma}_{10} \mathbf{q} \right)$$

$$\mathbf{\Phi}_{01}(\mathbf{q}) = \int_{\mathbb{R}^2} P_{01}(\mathbf{r}) e^{-i \mathbf{q} \cdot \mathbf{r}} d^2\mathbf{r} = \exp\left( -i \mathbf{q} \cdot \mathbf{a}_2^0 - \frac{1}{2} \mathbf{q}^T \mathbf{\Sigma}_{01} \mathbf{q} \right)$$

Notemos que debido a la positividad estricta de los tensores de covarianza, para cualquier $\mathbf{q} \ne 0$:

$$|\mathbf{\Phi}_{10}(\mathbf{q})| = \exp\left( -\frac{1}{2} \mathbf{q}^T \mathbf{\Sigma}_{10} \mathbf{q} \right) < 1$$

$$|\mathbf{\Phi}_{01}(\mathbf{q})| = \exp\left( -\frac{1}{2} \mathbf{q}^T \mathbf{\Sigma}_{01} \mathbf{q} \right) < 1$$

---

## 4. Sumación Geométrica Completa y Expresión Analítica Cerrada

Separando la sumatoria doble sobre $m$ y $n$ en tres componentes (nodo central $m=0$, semieje positivo $m>0$ y semieje negativo $m<0$):

$$K_1(\mathbf{q}) \equiv \sum_{m=-\infty}^{\infty} \left[ \mathbf{\Phi}_{10}(\mathbf{q}) \right]^m = 1 + \sum_{m=1}^{\infty} \mathbf{\Phi}_{10}^m(\mathbf{q}) + \sum_{m=1}^{\infty} (\mathbf{\Phi}_{10}^*(\mathbf{q}))^m$$

Como $|\mathbf{\Phi}_{10}(\mathbf{q})| < 1$, las series geométricas infinitas convergen absolutamente:

$$\sum_{m=1}^{\infty} \mathbf{\Phi}_{10}^m(\mathbf{q}) = \frac{\mathbf{\Phi}_{10}(\mathbf{q})}{1 - \mathbf{\Phi}_{10}(\mathbf{q})}$$

Sumando los términos conjugados:

$$K_1(\mathbf{q}) = 1 + \frac{\mathbf{\Phi}_{10}}{1 - \mathbf{\Phi}_{10}} + \frac{\mathbf{\Phi}_{10}^*}{1 - \mathbf{\Phi}_{10}^*} = \frac{1 - |\mathbf{\Phi}_{10}|^2}{|1 - \mathbf{\Phi}_{10}|^2} = \text{Re}\left\{ \frac{1 + \mathbf{\Phi}_{10}(\mathbf{q})}{1 - \mathbf{\Phi}_{10}(\mathbf{q})} \right\}$$

De forma completamente análoga para el eje 2:

$$K_2(\mathbf{q}) \equiv \sum_{n=-\infty}^{\infty} \left[ \mathbf{\Phi}_{01}(\mathbf{q}) \right]^n = \text{Re}\left\{ \frac{1 + \mathbf{\Phi}_{01}(\mathbf{q})}{1 - \mathbf{\Phi}_{01}(\mathbf{q})} \right\}$$

Multiplicando ambas dimensiones independientes, el **Factor de Estructura Canónico del Paracristal 2D de Hosemann** se formula como:

$$S_{\text{paracrystal}}(\mathbf{q}) = K_1(\mathbf{q}) \cdot K_2(\mathbf{q}) = \text{Re}\left\{ \frac{1 + \mathbf{\Phi}_{10}(\mathbf{q})}{1 - \mathbf{\Phi}_{10}(\mathbf{q})} \right\} \cdot \text{Re}\left\{ \frac{1 + \mathbf{\Phi}_{01}(\mathbf{q})}{1 - \mathbf{\Phi}_{01}(\mathbf{q})} \right\}$$

Desglosando en parte real e imaginaria con $\mathbf{\Phi} = |\mathbf{\Phi}| e^{-i \phi}$, donde $\phi = \mathbf{q} \cdot \mathbf{a}^0$:

$$K_j(\mathbf{q}) = \frac{1 - |\mathbf{\Phi}_j|^2}{1 - 2 |\mathbf{\Phi}_j| \cos(\mathbf{q} \cdot \mathbf{a}_j^0) + |\mathbf{\Phi}_j|^2}$$

---

## 5. Análisis Asintótico y Límites Físicos Fundamentales

### 5.1 Límite de Red Cristalina Perfecta ($\mathbf{\Sigma} \to 0$)
Cuando las fluctuaciones paracristalinas se anulan: $|\mathbf{\Phi}_j| \to 1$. El denominador se anula en las condiciones de Bragg $\mathbf{q} \cdot \mathbf{a}_j^0 = 2\pi h$ ($h \in \mathbb{Z}$), recuperando mediante la representación de Poisson el peine de deltas de Dirac periódicas del cristal ideal:

$$\lim_{\mathbf{\Sigma} \to 0} S(\mathbf{q}) = \frac{(2\pi)^2}{A_{\text{celda}}} \sum_{h, k} \delta(\mathbf{q} - \mathbf{G}_{hk})$$

### 5.2 Límite Asintótico de Alto Momento Recíproco ($|\mathbf{q}| \to \infty$)
Para vectores de onda grandes, el factor gaussiano se extingue exponencialmente: $|\mathbf{\Phi}_j(\mathbf{q})| \to 0$. En consecuencia:

$$\lim_{|\mathbf{q}| \to \infty} K_1(\mathbf{q}) = 1, \quad \lim_{|\mathbf{q}| \to \infty} K_2(\mathbf{q}) = 1 \implies \lim_{|\mathbf{q}| \to \infty} S(\mathbf{q}) = 1$$

El sistema pierde toda correlación espacial y se comporta macroscópicamente como un **gas coloidal totalmente desordenado**, confirmando la autoconsistencia termodinámica de la teoría.

---

## 6. Formulación de la Función de Verosimilitud (Log-Likelihood) para Inferencia

Dada una medición experimental del factor de estructura $S_{\text{exp}}(\mathbf{q}_i)$ discretizada en $M$ puntos de espacio recíproco mediante la NUFFT 2D (`[[CAT-307_Computacion_NUFFT_Factor_Estructura_Optimizacion_BLAS]]`), con incertidumbre fotométrica normal e independiente $\sigma_i$:

$$S_{\text{exp}}(\mathbf{q}_i) = S_{\text{paracrystal}}(\mathbf{q}_i; \mathbf{\Theta}) + \epsilon_i, \quad \epsilon_i \sim \mathcal{N}(0, \sigma_i^2)$$

donde $\mathbf{\Theta} = \{ \mathbf{a}_1^0, \mathbf{a}_2^0, \mathbf{\Sigma}_{10}, \mathbf{\Sigma}_{01} \}$ es el vector de 9 parámetros fundamentales de red. La función de log-verosimilitud analítica se define como:

$$\ln \mathcal{L}(\mathbf{\Theta} | S_{\text{exp}}) = -\frac{1}{2} \sum_{i=1}^M \left[ \frac{\left( S_{\text{exp}}(\mathbf{q}_i) - S_{\text{paracrystal}}(\mathbf{q}_i; \mathbf{\Theta}) \right)^2}{\sigma_i^2} + \ln(2\pi \sigma_i^2) \right]$$

---

## 7. Implementación Computacional en Python

```python
"""
CAT-310: Factor de Estructura Analítico de Paracristal 2D de Hosemann Anisótropo.
Evaluación vectorizada numéricamente estable en espacio recíproco continuo.
"""
from typing import Tuple
import numpy as np

class AnisotropicParacrystal2D:
    def __init__(
        self,
        a1_nm: Tuple[float, float],
        a2_nm: Tuple[float, float],
        sigma10_nm2: Tuple[float, float, float],  # (s11, s22, s12)
        sigma01_nm2: Tuple[float, float, float],  # (s11, s22, s12)
    ):
        self.a1 = np.array(a1_nm, dtype=np.float64)
        self.a2 = np.array(a2_nm, dtype=np.float64)
        
        # Construir tensores de covarianza 2x2
        self.S10 = np.array([
            [sigma10_nm2[0], sigma10_nm2[2]],
            [sigma10_nm2[2], sigma10_nm2[1]]
        ], dtype=np.float64)
        
        self.S01 = np.array([
            [sigma01_nm2[0], sigma01_nm2[2]],
            [sigma01_nm2[2], sigma01_nm2[1]]
        ], dtype=np.float64)

    def _eval_factor_k(self, qx: np.ndarray, qy: np.ndarray, a_vec: np.ndarray, sigma_mat: np.ndarray) -> np.ndarray:
        """Calcula K_j(q) = (1 - |Phi|^2) / (1 - 2|Phi|cos(q*a) + |Phi|^2) de forma estable."""
        phase = qx * a_vec[0] + qy * a_vec[1]
        q_dot_sigma_q = qx**2 * sigma_mat[0, 0] + 2.0 * qx * qy * sigma_mat[0, 1] + qy**2 * sigma_mat[1, 1]
        
        mod_phi = np.exp(-0.5 * q_dot_sigma_q)
        # Limitar mod_phi para evitar división por cero en polos ideales
        mod_phi = np.clip(mod_phi, 1e-12, 1.0 - 1e-12)
        
        numerator = 1.0 - mod_phi**2
        denominator = 1.0 - 2.0 * mod_phi * np.cos(phase) + mod_phi**2
        return numerator / np.maximum(denominator, 1e-12)

    def compute_structure_factor_2d(self, qx_grid: np.ndarray, qy_grid: np.ndarray) -> np.ndarray:
        """Evalúa S_paracrystal(qx, qy) sobre una malla 2D continua."""
        k1 = self._eval_factor_k(qx_grid, qy_grid, self.a1, self.S10)
        k2 = self._eval_factor_k(qx_grid, qy_grid, self.a2, self.S01)
        return k1 * k2
```

---

## 8. Conclusiones y Conexión Metrológica

1. La formulación matricial cerrada de Hosemann 2D proporciona la base analítica exacta para discriminar entre el desorden de posicionamiento local y la deriva cumulativa de red.
2. Al estar completamente vectorizada en espacio recíproco continuo, la función analítica se utiliza directamente en el motor de muestreo probabilístico de `[[CAT-311_Inferencia_Bayesiana_MCMC_Desorden_Paracristal]]`.
