# Reporte Científico Canónico: Inferencia Bayesiana y MCMC para Desorden de Paracristal 2D 🎲📊

**Biblioteca Científica Canónica — Pilar III: Cristalografía 2D, Espacio Recíproco y Metrología de Desorden**  
**Signatura Canónica**: `CAT-311` | **Clúster**: `[CMP]` (Computacional)  
**Laboratorio de Nanofotónica — Instituto de Nanosistemas (INS-UNSAM / CONICET)**  
**Autor Principal**: José Luis González Peñafiel (*Físico EPN, Becario Doctoral CONICET, INS-UNSAM*)  
**Fecha de Publicación**: Septiembre 2026 | **Estado**: Vigente y Certificado por QA  
**Módulos del Sistema Asociados**: `core/lattice_disorder.py`, `analysis/lattice_disorder_gui.py`  
**Referencias Cruzadas**: `[[CAT-203_Presupuesto_Incertidumbre_Metrologica_ISOGUM_Microscopia]]`, `[[CAT-301_Algoritmos_Espacio_Real_KDTree_Asignacion_Monte_Carlo]]`, `[[CAT-305_Derivacion_Matematica_Factor_Estructura_Debye_Waller]]`, `[[CAT-307_Computacion_NUFFT_Factor_Estructura_Optimizacion_BLAS]]`, `[[CAT-308_Metrologia_Analitica_Directa_Picos_Bragg_Fourier_2D]]`, `[[CAT-309_Teoria_Paracristal_Hosemann_Perdida_Orden_2D]]`, `[[CAT-310_Derivacion_Matematica_Paracristal_2D_Hosemann_Anisotropo]]`

---

## 1. Resumen Ejecutivo

La determinación experimental de los tensores de desorden en redes plasmónicas 2D mediante ajuste de mínimos cuadrados convencional presenta severas limitaciones: alta correlación entre los parámetros de período de red y desorden, presencia de múltiples óptimos locales en el espacio de parámetros, e incapacidad para garantizar analíticamente que las matrices de fluctuación reticular estimadas sean **estrictamente definidas positivas** ($\det \mathbf{\Sigma} > 0$).

Este reporte formaliza el desarrollo del motor de **Inferencia Bayesiana mediante Cadenas de Markov Monte Carlo (MCMC)** para la caracterización cuantitativa del Paracristal 2D de Hosemann anisótropo (`[[CAT-310_Derivacion_Matematica_Paracristal_2D_Hosemann_Anisotropo]]`): la parametrización de Cholesky de los tensores de fluctuación, la construcción de *priors* informativos basados en las tolerancias optomecánicas del microscopio, el muestreo de ensambles invariantes afines (Goodman & Weare / `emcee`), el análisis de convergencia por autocorrelación y la estimación de distribuciones de probabilidad a posteriori para desacoplar inequívocamente la anisotropía inducida por la platina piezoeléctrica frente a las fluctuaciones térmicas o coloidales.

---

## 2. Marco Bayesiano y Parametrización de Cholesky

De acuerdo con el Teorema de Bayes, la distribución de probabilidad a posteriori de los parámetros de red $\mathbf{\Theta}$ condicionados a las observaciones del factor de estructura experimental $\mathbf{D} = \{ S_{\text{exp}}(\mathbf{q}_i) \}_{i=1}^M$ se expresa como:

$$P(\mathbf{\Theta} | \mathbf{D}) = \frac{P(\mathbf{D} | \mathbf{\Theta}) \cdot P(\mathbf{\Theta})}{P(\mathbf{D})} \propto \exp\left( \ln \mathcal{L}(\mathbf{\Theta}) + \ln P(\mathbf{\Theta}) \right)$$

### 2.1 Garantía de Tensores Semidefinidos Positivos
Para que las matrices de covarianza de enlace $\mathbf{\Sigma}_{10}$ y $\mathbf{\Sigma}_{01}$ representen distribuciones de probabilidad gaussianas físicamente admisibles, deben ser simétricas y estrictamente definidas positivas. Parametrizar directamente los elementos individuales $\{\sigma_{11}, \sigma_{22}, \sigma_{12}\}$ conduce a propuestas MCMC no físicas donde $\sigma_{11}\sigma_{22} - \sigma_{12}^2 \le 0$.

Para resolver esto de forma rigurosa, se implementa la **descomposición triangular de Cholesky**:

$$\mathbf{\Sigma} = \mathbf{L} \mathbf{L}^T, \quad \mathbf{L} = \begin{pmatrix} l_{11} & 0 \\ l_{21} & l_{22} \end{pmatrix}$$

Multiplicando matricialmente:

$$\mathbf{\Sigma} = \begin{pmatrix} l_{11}^2 & l_{11} l_{21} \\ l_{11} l_{21} & l_{21}^2 + l_{22}^2 \end{pmatrix}$$

El determinante resulta:

$$\det \mathbf{\Sigma} = (\det \mathbf{L})^2 = (l_{11} l_{22})^2 > 0 \iff l_{11} > 0 \land l_{22} > 0$$

Muestreando en el espacio no acoplado $\mathbf{\theta}_L = \{ \ln l_{11}, l_{21}, \ln l_{22} \} \in \mathbb{R}^3$, la matriz $\mathbf{\Sigma}$ es **garantizada analíticamente como definida positiva para cualquier valor numérico propuesto**.

```
                           PARAMETRIZACIÓN DE CHOLESKY Y ESPACIO MCMC
                 
           Espacio Libre Incondicionado                Espacio Físico de Matrices
                  (theta in R^3)                         (Sigma in Sym^+_2(R))
           ┌────────────────────────────┐                ┌────────────────────────────┐
           │ u_1 = ln(l_11)  in (-inf, +inf)             │ Sigma_11 = exp(2*u_1) > 0  │
           │ l_21            in (-inf, +inf)   ──────►   │ det(Sigma) = exp(2u_1+2u_2)│
           │ u_2 = ln(l_22)  in (-inf, +inf)             │ 100% Definida Positiva     │
           └────────────────────────────┘                └────────────────────────────┘
```

---

## 3. Asignación de Distribuciones a Priori (*Priors*) Físicos

El vector completo de 10 parámetros a inferir es:

$$\mathbf{\Theta} = \left( a_1, a_2, \gamma, \ln l_{11}^{(10)}, l_{21}^{(10)}, \ln l_{22}^{(10)}, \ln l_{11}^{(01)}, l_{21}^{(01)}, \ln l_{22}^{(01)}, \ln \sigma_{\text{noise}} \right)$$

Se asignan *priors* basados en el conocimiento previo del diseño de la red y la instrumentación:
1. **Parámetros Geométricos de Red**:
   $$a_1 \sim \mathcal{U}(a_{\text{nom}} - 50\ \text{nm}, a_{\text{nom}} + 50\ \text{nm})$$
   $$a_2 \sim \mathcal{U}(a_{\text{nom}} - 50\ \text{nm}, a_{\text{nom}} + 50\ \text{nm})$$
   $$\gamma \sim \mathcal{N}(\gamma_{\text{nom}}, (2.0^\circ)^2)$$
2. **Componentes de Fluctuación**:
   $$l_{11}, l_{22} \sim \text{Log-Normal}(\mu = \ln(8.0\ \text{nm}), \sigma = 1.0)$$
   $$l_{21} \sim \mathcal{N}(0, (10.0\ \text{nm})^2)$$
3. **Nivel de Ruido Experimental**:
   $$\ln \sigma_{\text{noise}} \sim \mathcal{U}(-4.0, 2.0)$$

---

## 4. Algoritmo de Muestreo de Ensamble Invariante Afín (`emcee`)

Para explorar eficientemente espacios de parámetros con correlaciones no lineales, se utiliza el muestreador de ensambles propuesto por Goodman & Weare (2010):

Se inicializa un ensamble de $K = 32$ o $64$ caminantes (*walkers*). En cada paso $t$, la posición de un caminante $\mathbf{X}_k$ se actualiza proponiendo un salto hacia otro caminante aleatorio $\mathbf{X}_j$ ($j \ne k$):

$$\mathbf{Y} = \mathbf{X}_j + Z \left( \mathbf{X}_k - \mathbf{X}_j \right)$$

donde $Z$ es una variable aleatoria con densidad $g(z) \propto \frac{1}{\sqrt{z}}$ para $z \in [1/a_s, a_s]$ (con escala estándar $a_s = 2.0$). El salto se acepta con probabilidad de Metropolis:

$$\alpha = \min\left( 1, Z^{N_{\text{dim}}-1} \frac{P(\mathbf{Y}|\mathbf{D})}{P(\mathbf{X}_k|\mathbf{D})} \right)$$

```
                         DIAGNÓSTICO DE CONVERGENCIA MCMC
        
        Log-Likelihood
              ▲
              │          Walkers calentándose (Burn-in)           Régimen Estacionario
              │               ╭───╮  ╭─────╮                       (Muestreo Posterior)
              │        ╭──────╯   ╰──╯     ╰──────────────────────────────────────────
              │      ╭─╯                     t_burn > 5 * tau_auto
              │  ╭───╯
              └──┴──────────────────────────────────────────────────────► Pasos MCMC
```

### 4.1 Criterio de Convergencia por Autocorrelación
La cadena se considera convergida cuando el número total de iteraciones $N_{\text{steps}}$ supera con creces el tiempo de autocorrelación integrado $\tau_{\text{int}}$:

$$N_{\text{steps}} > 50 \cdot \max_i (\tau_{\text{int}, i})$$

y el factor de reducción de escala potencial de Gelman-Rubin satisface $\hat{R} < 1.05$.

---

## 5. Extracción de Elipses de Desorden y Desacople Instrumental

A partir de las muestras estacionarias de la distribución a posteriori, se extraen las matrices medias $\langle \mathbf{\Sigma}_{10} \rangle$ y $\langle \mathbf{\Sigma}_{01} \rangle$. Diagonalizando cada tensor:

$$\mathbf{\Sigma} = \mathbf{V} \begin{pmatrix} \sigma_{\text{mayor}}^2 & 0 \\ 0 & \sigma_{\text{menor}}^2 \end{pmatrix} \mathbf{V}^T$$

* **Grado de Anisotropía**: $\eta_{\text{aniso}} = \sigma_{\text{mayor}} / \sigma_{\text{menor}}$.
* **Orientación del Desorden**: $\theta_{\text{aniso}} = \arctan(V_{21} / V_{11})$.

Si $\theta_{\text{aniso}}$ coincide con el eje de desplazamiento rápido de la platina piezoeléctrica PI ($X_{\text{piezo}}$) y $\eta_{\text{aniso}} > 1.5$, la fuente primaria del desorden se atribuye a **ruido de arrastre piezoeléctrico**. Por el contrario, si $\eta_{\text{aniso}} \approx 1.0$, el desorden proviene de **fluctuaciones térmicas y flotación coloidal isotrópica**.

---

## 6. Implementación Computacional en Python

```python
"""
CAT-311: Inferencia Bayesiana MCMC para Desorden Paracristalino 2D.
Muestreo ensemble affine-invariant sobre tensores parametrizados por Cholesky.
"""
from typing import Tuple, Dict
import numpy as np
from CAT_310_Derivacion_Matematica_Paracristal_2D_Hosemann_Anisotropo import AnisotropicParacrystal2D

class BayesianParacrystalInference:
    def __init__(self, qx: np.ndarray, qy: np.ndarray, s_exp: np.ndarray, s_err: np.ndarray):
        self.qx = qx
        self.qy = qy
        self.s_exp = s_exp
        self.s_err = s_err

    def unpack_parameters(self, theta: np.ndarray) -> Tuple[AnisotropicParacrystal2D, float]:
        """Convierte vector MCMC (10,) a modelo físico con descomposición de Cholesky."""
        a1_val, a2_val, gamma_rad = theta[0], theta[1], theta[2]
        
        # Vectores de red medios
        a1 = (a1_val, 0.0)
        a2 = (a2_val * np.cos(gamma_rad), a2_val * np.sin(gamma_rad))
        
        # Cholesky tensor 10: [ln_l11, l21, ln_l22]
        l11_10, l21_10, l22_10 = np.exp(theta[3]), theta[4], np.exp(theta[5])
        sig10 = (l11_10**2, l21_10**2 + l22_10**2, l11_10 * l21_10)
        
        # Cholesky tensor 01: [ln_l11, l21, ln_l22]
        l11_01, l21_01, l22_01 = np.exp(theta[6]), theta[7], np.exp(theta[8])
        sig01 = (l11_01**2, l21_01**2 + l22_01**2, l11_01 * l21_01)
        
        sigma_noise = np.exp(theta[9])
        model = AnisotropicParacrystal2D(a1, a2, sig10, sig01)
        return model, sigma_noise

    def log_prior(self, theta: np.ndarray) -> float:
        """Calcula el log-prior no acoplado."""
        a1, a2, gamma = theta[0], theta[1], theta[2]
        if not (400.0 <= a1 <= 600.0 and 400.0 <= a2 <= 600.0 and 1.2 <= gamma <= 1.9):
            return -np.inf
        # Priors suaves sobre factores Cholesky
        if np.any(np.abs(theta[3:9]) > 6.0):
            return -np.inf
        return 0.0

    def log_likelihood(self, theta: np.ndarray) -> float:
        """Evalúa la log-verosimilitud analítica."""
        model, sigma_noise = self.unpack_parameters(theta)
        s_theo = model.compute_structure_factor_2d(self.qx, self.qy)
        total_var = self.s_err**2 + sigma_noise**2
        chi2 = np.sum((self.s_exp - s_theo)**2 / total_var + np.log(2.0 * np.pi * total_var))
        return -0.5 * chi2

    def log_posterior(self, theta: np.ndarray) -> float:
        lp = self.log_prior(theta)
        if not np.isfinite(lp):
            return -np.inf
        return lp + self.log_likelihood(theta)
```

---

## 7. Conclusiones y Conexión Metrológica

1. La inferencia MCMC provee no sólo una estimación puntual, sino la **matriz completa de covarianzas de incertidumbre**, satisfaciendo plenamente los requerimientos de la Guía ISO/GUM (`[[CAT-203_Presupuesto_Incertidumbre_Metrologica_ISOGUM_Microscopia]]`).
2. El desacople entre las elipses de covarianza de enlace permite diagnosticar de forma no invasiva si un ensanchamiento de Bragg se debe a desgaste de la platina o a inestabilidad coloidal.
