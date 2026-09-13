# Teoría del Paracristal de Hosemann y Pérdida de Orden de Largo Alcance en Redes 2D
## Discriminación Espectral entre Desorden Térmico/Local (Tipo I) y Desorden Acumulativo de Red (Tipo II)

---

**Autoría:** Equipo de Metrología Cuántica, Cristalografía Computacional y Fotónica — PyPrinting 3.0  
**Fecha:** Septiembre 2026  
**Clasificación:** Reporte Científico Especializado / Cristalografía Teórica y Óptica de Difracción  
**Estado:** Producción / Consolidado  
**Documentos Vinculados:**  
- [[CAT-305_Derivacion_Matematica_Factor_Estructura_Debye_Waller]] (Factor de Debye-Waller y $S(\mathbf{q})$ bajo desorden Tipo I)  
- [[CAT-308_Metrologia_Analitica_Directa_Picos_Bragg_Fourier_2D]] (Inversión analítica directa de picos de Bragg)  
- [[CAT-304_Metrologia_Experimental_Conchas_Coordinacion_gr_Redes_2D]] (Función de distribución radial y amortiguamiento de picos en espacio real)  
- [[CAT-307_Computacion_NUFFT_Factor_Estructura_Optimizacion_BLAS]] (Cómputo numérico de difracción no equiespaciada)  

---

### Resumen Ejecutivo

En la nanofabricación óptica basada en polimerización por dos fotones (2PP), litografía coloidal o autoensamblado de nanopartículas, las imperfecciones de la red cristalina 2D se han catalogado comúnmente bajo un único parámetro de dispersión posicional ($\sigma_{\text{pos}}$). Sin embargo, desde los fundamentos de la física del estado sólido y la cristalografía cuántica, existe una distinción crucial entre dos regímenes físicos con consecuencias radicalmente divergentes sobre la propagación de fotones y la apertura de bandas prohibidas (bandgaps fotónicos):

1. **Desorden de Tipo I (Desorden de Debye-Waller):** Fluctuaciones de cada emisor en torno a una red ideal subyacente fija. Preserva estrictamente la correlación de fase y el orden de largo alcance ($r \to \infty$). Los picos de Bragg conservan su agudeza de difracción limitada únicamente por el tamaño finito del cristal ($\Delta q \sim 2\pi/L$), pero sufren una atenuación exponencial de su altura $H \propto e^{-q^2 \sigma^2}$.
2. **Desorden de Tipo II (Paracristal de Hosemann):** Fluctuaciones estocásticas acumulativas entre vecinos inmediatos (camino aleatorio del vector de base $\mathbf{a}_i$). Destruye irreversiblemente el orden de largo alcance, introduciendo una longitud de correlación espacial finita $\xi$. Los picos de Bragg no solo atenúan su amplitud, sino que **se ensanchan cuadráticamente con el orden de difracción** ($\Delta q(m) \propto m^2$).

Este reporte establece el marco analítico riguroso del paracristal bidimensional de Hosemann (1962), deduce el factor de estructura $S(\mathbf{q})$ bajo matrices de distorsión gaussianas, formula el criterio experimental para distinguir Tipo I vs Tipo II a partir de los anchos a media altura ($\text{FWHM}_q$) de los picos de Bragg en el módulo NUFFT de PyPrinting 3.0, y analiza el impacto en dispositivos de fotónica integrada.

---

```
                       ESPACIO REAL: COMPARATIVA DE REDES
                       
   (A) Cristal Ideal:         (B) Desorden Tipo I:       (C) Desorden Tipo II (Paracristal):
   R_n = n*a                  r_n = n*a + delta_n         r_n = sum(a_k)  (a_k estocástico)
   
   o---o---o---o---o          .   .     .   .   .          .      .       .        .       .
   |   |   |   |   |           o   o   o   o   o            o       o        o
   o---o---o---o---o          .   .     .   .   .                         o       o      o
   |   |   |   |   |           o   o   o   o   o              o      o          o
   o---o---o---o---o                                                   o       o         o
   
   Orden: Infinito (Fijo)     Orden: Infinito (Promedio)  Orden: Corto Alcance (Decae ~ exp(-r/xi))
   Ancho Pico: Constante      Ancho Pico: Constante       Ancho Pico: Crece cuadráticamente ~ m^2
```

---

## 1. Clasificación Físico-Matemática de los Regímenes de Desorden

Consideremos un conjunto de sitios en un cristal 2D denotados por $\mathbf{r}_n$.

### 1.1 Desorden de Debye-Waller (Tipo I)
Los sitios están ligados a una referencia euclídea absoluta $\mathbf{R}_n = n_1 \mathbf{a}_1 + n_2 \mathbf{a}_2$:
$$\mathbf{r}_n = \mathbf{R}_n + \mathbf{\delta}_n, \quad \langle \mathbf{\delta}_n \rangle = \mathbf{0}, \quad \langle \mathbf{\delta}_n \cdot \mathbf{\delta}_{n'} \rangle = 2\sigma_{\text{pos}}^2 \delta_{nn'}$$

La función de densidad de pares en el límite de grandes distancias $|n - n'| \to \infty$ no pierde la memoria de fase:
$$\lim_{|n - n'| \to \infty} \langle e^{-i \mathbf{q} \cdot (\mathbf{r}_n - \mathbf{r}_{n'})} \rangle = e^{-|\mathbf{q}|^2 \sigma_{\text{pos}}^2} e^{-i \mathbf{q} \cdot (\mathbf{R}_n - \mathbf{R}_{n'})} \neq 0$$
Por ende, las reflexiones de Bragg son matemáticamente singulares (deltas de Dirac ensanchadas únicamente por la convolución de forma $L$ de la muestra).

### 1.2 Desorden Paracristalino de Hosemann (Tipo II)
En el modelo de Hosemann, no existe una red de referencia global. Cada posición de red se construye iterativamente sumando vectores de traslación estocásticos entre primeros vecinos:
$$\mathbf{r}_n = \mathbf{r}_0 + \sum_{k=1}^{n} \mathbf{a}_k$$
donde cada vector $\mathbf{a}_k$ es una variable aleatoria independiente e idénticamente distribuida (i.i.d.) con distribución de probabilidad $H(\mathbf{x})$:
$$\langle \mathbf{a}_k \rangle = \mathbf{a}_0 = a\,\hat{\mathbf{x}}, \quad \text{Cov}(\mathbf{a}_k) = \sigma_a^2 \mathbf{I}$$

La distancia relativa entre el sitio $0$ y el sitio $n$ es la suma de $n$ variables independientes:
$$\mathbf{r}_n - \mathbf{r}_0 = \sum_{k=1}^{n} \mathbf{a}_k \implies \text{Var}(\mathbf{r}_n - \mathbf{r}_0) = n \, \sigma_a^2$$

A medida que nos alejamos de un sitio de referencia, la incertidumbre posicional **diverge linealmente con la distancia de red** ($n$). Esto provoca una pérdida exponencial de la correlación de fase:
$$\langle e^{-i q (r_n - r_0)} \rangle = \prod_{k=1}^n \langle e^{-i q a_k} \rangle = \left[ F(q) \right]^n$$
donde $F(q)$ es la función característica de $H(\mathbf{x})$. Puesto que $|F(q)| < 1$ para todo $q \neq 0$:
$$\lim_{n \to \infty} \left[ F(q) \right]^n = 0$$
En consecuencia, el orden de largo alcance colapsa a cero para cualquier frecuencia recíproca finita.

---

## 2. Derivación del Factor de Estructura Paracristalino en 2D

Consideremos una red bidimensional con direcciones cristalográficas desacopladas $x$ e $y$ con parámetros de distorsión paracristalina:
$$g_x = \frac{\sigma_{a_x}}{a_x}, \quad g_y = \frac{\sigma_{a_y}}{a_y}$$

La función de distribución de vecinos para una componente unidimensional bajo perturbación gaussiana es:
$$H(x) = \frac{1}{\sqrt{2\pi}\sigma_a} \exp\left[-\frac{(x - a)^2}{2\sigma_a^2}\right]$$
Su transformada de Fourier (función característica) es:
$$F(q_x) = \int_{-\infty}^{\infty} H(x) e^{-i q_x x} dx = \exp\left[-i q_x a - \frac{1}{2} q_x^2 \sigma_a^2\right]$$

El factor de estructura de una cadena paracristalina infinita viene dado por la relación clásica de Hosemann-Zernike:
$$S(q_x) = 1 + 2 \, \text{Re} \left\{ \sum_{n=1}^{\infty} [F(q_x)]^n \right\} = \text{Re} \left\{ \frac{1 + F(q_x)}{1 - F(q_x)} \right\}$$

Sustituyendo $F(q_x) = |F| e^{-i \phi}$, donde $|F| = e^{-\frac{1}{2} q_x^2 \sigma_a^2}$ y $\phi = q_x a$:
$$S(q_x) = \frac{1 - |F|^2}{1 - 2|F|\cos(q_x a) + |F|^2} = \frac{1 - e^{-q_x^2 \sigma_a^2}}{1 - 2 e^{-\frac{1}{2}q_x^2 \sigma_a^2}\cos(q_x a) + e^{-q_x^2 \sigma_a^2}}$$

Para una red 2D ortogonal cuyos desplazamientos paracristalinos en $X$ e $Y$ son estadísticamente independientes:
$$\bbox[12px,border:2px solid #2563eb,background:#eff6ff]{
S(\mathbf{q}) = S(q_x) \cdot S(q_y) = \text{Re}\left\{ \frac{1 + F(q_x)}{1 - F(q_x)} \right\} \cdot \text{Re}\left\{ \frac{1 + F(q_y)}{1 - F(q_y)} \right\}
}$$

---

## 3. Comportamiento Espectral de los Picos de Difracción: Amplitud y Ancho $\text{FWHM}_q$

Para estudiar la forma de las líneas de difracción en torno al armónico de orden $m \in \{1, 2, 3, \dots\}$, expandimos en serie de Taylor alrededor de la frecuencia de resonancia $q_x = q_m + \Delta q$, con $q_m = m \frac{2\pi}{a}$:

### 3.1 Amortiguamiento Paracristalino Débil ($g \ll 1$)
Cuando el parámetro de distorsión $g = \sigma_a / a \le 0.1$, evaluamos $|F|$ en el pico $m$:
$$|F(q_m)| = \exp\left[-\frac{1}{2} \left(m \frac{2\pi}{a}\right)^2 \sigma_a^2\right] = \exp\left[-2\pi^2 m^2 g^2\right] \approx 1 - 2\pi^2 m^2 g^2$$

Expandiendo el término del denominador:
$$1 - 2|F|\cos(\Delta q \cdot a) + |F|^2 \approx (1 - |F|)^2 + |F| (a\,\Delta q)^2 \approx (2\pi^2 m^2 g^2)^2 + a^2 \Delta q^2$$

Sustituyendo en la expresión de $S(q_x)$:
$$S(\Delta q) \approx \frac{4\pi^2 m^2 g^2}{(2\pi^2 m^2 g^2)^2 + a^2 \Delta q^2} = \frac{1}{a} \left[ \frac{\Gamma_m}{\Gamma_m^2 + \Delta q^2} \right]$$
donde:
$$\Gamma_m = \frac{2\pi^2 m^2 g^2}{a}$$

### 3.2 Ancho a Media Altura ($\text{FWHM}_q$): Ley Cuadrática de Hosemann
La función de línea de difracción resultante en un paracristal puro es una **Lorentziana**, cuyo ancho total a media altura ($\text{FWHM}_q = 2\Gamma_m$) está dado por:
$$\bbox[12px,border:2px solid #dc2626,background:#fef2f2]{
\text{FWHM}_q(m) = \frac{4\pi^2 m^2 g^2}{a} = \frac{4\pi^2}{a^3} m^2 \sigma_a^2
}$$

#### Consecuencia Fundamental:
- **Orden 1 ($m=1$):** $\text{FWHM}_q(1) = \frac{4\pi^2 g^2}{a}$
- **Orden 2 ($m=2$):** $\text{FWHM}_q(2) = 4 \times \text{FWHM}_q(1)$
- **Orden 3 ($m=3$):** $\text{FWHM}_q(3) = 9 \times \text{FWHM}_q(1)$

En un cristal real con desorden Tipo II, **el segundo armónico es 4 veces más ancho que el primero**, y el tercer armónico es 9 veces más ancho. Esto contrasta frontalmente con el desorden Tipo I (Debye-Waller), donde el ancho a media altura es **estrictamente idéntico para todos los órdenes de difracción**, gobernado por el factor geométrico de Scherrer $\text{FWHM}_q \approx \frac{2\pi \cdot 0.9}{L_x}$.

```
  FACTOR DE ESTRUCTURA S(q) : DESORDEN TIPO I vs TIPO II
  
  Tipo I (Debye-Waller): Ancho FWHM constante, Altura decae exp(-q^2)
  S(q) ^
       |      | m=1
       |      |
       |      |            | m=2
       |      |            |
       +------*------------*---------> q
            FWHM_1  =    FWHM_2
            
  Tipo II (Paracristal): Ancho FWHM crece cuadráticamente (m^2), Área se conserva
  S(q) ^
       |     / \ m=1
       |    /   \
       |   /     \            /-----\ m=2
       +--*-------*----------*-------*--> q
            FWHM_1             FWHM_2 = 4 * FWHM_1
```

---

## 4. Criterio de Diagnóstico Experimental en PyPrinting 3.0

Para determinar unívocamente si una muestra nanolitografiada o coloidal padece desorden térmico local (Tipo I) o desorden acumulativo de espaciado (Tipo II), PyPrinting 3.0 implementa el siguiente protocolo de prueba de hipótesis:

### Algoritmo de Decisión:
1. Se calculan los perfiles radiales o cortes axiales de $S(\mathbf{q})$ mediante la rutina optimizada [[CAT-307_Computacion_NUFFT_Factor_Estructura_Optimizacion_BLAS]].
2. Se ajustan funciones pseudo-Voigt a los picos de Bragg $m=1$ en $(q_1, 0)$ y $m=2$ en $(2q_1, 0)$, extrayendo sus anchos a media altura $\text{FWHM}_1$ y $\text{FWHM}_2$.
3. Se define el **Cociente de Diagnóstico de Hosemann**:
   $$\eta_H = \frac{\text{FWHM}_2}{\text{FWHM}_1}$$

| Valor de $\eta_H$ | Diagnóstico Físico | Modelo Válido en PyPrinting 3.0 |
| :--- | :--- | :--- |
| **$0.9 \le \eta_H \le 1.15$** | **Desorden Puro Tipo I (Debye-Waller):** No hay pérdida de fase acumulativa. La dispersión es local. | [[CAT-308_Metrologia_Analitica_Directa_Picos_Bragg_Fourier_2D]] ($H_2/H_1$ analítico exacto) |
| **$1.15 < \eta_H < 3.5$** | **Desorden Mixto (Tipo I + Tipo II Parcial):** Coexisten fluctuaciones térmicas locales con distorsión de espaciado. | Calibración Numérica Monte Carlo con generador estocástico de paso |
| **$3.5 \le \eta_H \le 4.5$** | **Paracristal Puro de Hosemann (Tipo II):** El orden de largo alcance está destruido por acumulación de errores de paso. | Modelo de Hosemann analítico ($g = \frac{\sqrt{a \cdot \text{FWHM}_1}}{2\pi}$) |
| **Pico $m=2$ ausente** | **Régimen de Líquido 2D / Amorfo:** Longitud de correlación inferior a dos constantes de red ($\xi < 2a$). | Análisis de distribución radial $g(r)$ y factor de empaquetamiento |

---

## 5. Longitud de Correlación Espacial ($\xi$) y Criterio de Límite de Red

En presencia de desorden Tipo II, la función de correlación espacial de la densidad $G(\mathbf{r}) = \langle \rho(\mathbf{0})\rho(\mathbf{r}) \rangle$ decae exponencialmente para distancias largas:
$$G(r) - \rho_0^2 \propto \exp\left[-\frac{r}{\xi}\right] \cos\left(\frac{2\pi r}{a}\right)$$

La **longitud de correlación traslacional** $\xi$ se relaciona directamente con el ancho lorentziano del primer pico de difracción:
$$\bbox[12px,border:2px solid #059669,background:#ecfdf5]{
\xi = \frac{2}{\text{FWHM}_q(1)} = \frac{a}{2\pi^2 g^2}
}$$

### Número Máximo de Planos Coherentes ($N_{\text{max}}$):
Hosemann demostró que un cristal pierde toda apariencia de estructura periódica cuando el ancho del pico $m$ iguala la separación entre picos consecutivos ($q_1 = 2\pi / a$):
$$\text{FWHM}_q(m^*) \approx \frac{2\pi}{a} \implies \frac{4\pi^2 (m^*)^2 g^2}{a} = \frac{2\pi}{a} \implies m^* \approx \frac{1}{\sqrt{2\pi} \, g} \approx \frac{0.4}{g}$$

Si un sistema de nanofotónica tiene un desorden de paso del $g = 8\% = 0.08$, entonces:
$$m^* \approx \frac{0.4}{0.08} = 5$$
Esto significa que a partir del 5to orden de difracción no existen picos de Bragg discernibles, fundiéndose toda la intensidad en un continuo difuso similar al de un vidrio o líquido sobreenfriado.

---

## 6. Impacto en Fotónica Cuántica y Cristales Fotónicos 2D

La distinción entre desorden Tipo I y Tipo II es crítica para el diseño de dispositivos ópticos fabricados en PyPrinting 3.0:

1. **Apertura de Bandgaps Fotónicos (PBG):**
   - En redes con **Desorden Tipo I**, el bandgap fotónico se estrecha progresivamente debido a la atenuación de los componentes de Fourier del dieléctrico $\epsilon(\mathbf{G})$, pero el borde de banda se mantiene abrupto y el guiado de luz por defecto lineal sigue siendo monomodo y de baja pérdida.
   - En redes con **Desorden Tipo II (Paracristal)**, la fluctuación del espaciado introduce estados localizados de cola en el interior del bandgap (estados de Lifshitz/Urbach tail). La densidad de estados fotónica (DOS) pierde el gap completo, provocando **pérdidas por radiación severas** y transición hacia localización de Anderson.

2. **Guías de Onda y Resonadores de Alto Factor de Calidad ($Q$):**
   - Si $\eta_H > 1.2$, el sistema de control optomecánico de PyPrinting 3.0 (e.g. [[CAT-105_Compensacion_Deriva_Termomecanica_Particula_Ancla_P0]] y [[CAT-101_Protocolo_Operativo_Impresion_Fototermica_Grillas_2D]]) está introduciendo un error acumulativo de paso (deriva en la integración de encoders piezoeléctricos o histéresis no compensada). Corregir este desorden exige calibración del lazo cerrado de posición y no un simple ajuste de dosis de exposición óptica.

---

## 7. Módulo de Evaluación en Python (PyPrinting 3.0)

```python
import numpy as np

def hosemann_disorder_diagnostic(fwhm_q1: float, fwhm_q2: float, a: float) -> dict:
    """
    Diagnostica el régimen de desorden cristalográfico (Tipo I vs Tipo II) en una red 2D.
    
    Parámetros:
      fwhm_q1: Ancho a media altura (FWHM) del pico de Bragg m=1 (en nm^-1).
      fwhm_q2: Ancho a media altura (FWHM) del pico de Bragg m=2 (en nm^-1).
      a: Constante de red media en nm.
      
    Retorna:
      Diccionario con el cociente de Hosemann eta_H, parámetro de distorsión g,
      longitud de correlación xi y diagnóstico textual.
    """
    if fwhm_q1 <= 0 or fwhm_q2 <= 0:
        return {"valid": False, "error": "Los anchos FWHM deben ser estrictamente positivos."}
        
    eta_H = fwhm_q2 / fwhm_q1
    
    # Estimación del parámetro g bajo hipótesis de paracristal puro
    # FWHM_1 = (4 * pi^2 * g^2) / a  ==> g = sqrt(a * FWHM_1) / (2 * pi)
    g_paracrystal = np.sqrt(a * fwhm_q1) / (2.0 * np.pi)
    
    # Longitud de correlación espacial xi
    xi_correlation_nm = 2.0 / fwhm_q1
    
    # Diagnóstico de régimen
    if eta_H < 1.25:
        regime = "Tipo I (Debye-Waller Puro)"
        explanation = "Desorden térmico/local sin pérdida de fase acumulativa. FWHM independiente del orden m."
    elif 1.25 <= eta_H < 3.2:
        regime = "Mixto (Tipo I + Tipo II Parcial)"
        explanation = "Coexistencia de fluctuación local con deriva acumulativa en las distancias inter-partículas."
    elif 3.2 <= eta_H <= 4.8:
        regime = "Tipo II (Paracristal de Hosemann)"
        explanation = "Desorden acumulativo puro (camino aleatorio de paso). FWHM escala cuadráticamente ~ m^2."
    else:
        regime = "Anómalo / Amorfización Severa"
        explanation = "Pérdida crítica de periodicidad espacial o distorsión instrumental severa."
        
    return {
        "valid": True,
        "eta_H": float(eta_H),
        "regime": regime,
        "explanation": explanation,
        "paracrystal_g_parameter": float(g_paracrystal),
        "correlation_length_xi_nm": float(xi_correlation_nm),
        "max_discernible_order_m": int(np.floor(0.4 / max(g_paracrystal, 1e-4)))
    }
```

---

## 8. Conclusiones

1. **Ruptura de la Degeneración Metrológica:**  
   La medición aislada del factor de estructura en un único orden de difracción no puede discernir entre desorden térmico de Debye-Waller y desorden paracristalino. El análisis comparativo multiorigen ($m=1$ vs $m=2$) a través del cociente $\eta_H = \text{FWHM}_2 / \text{FWHM}_1$ es la única vía analítica concluyente.

2. **Inclusión en la Suite de PyPrinting 3.0:**  
   El módulo de espacio recíproco queda equipado con la métrica $\eta_H$. Si el sistema opera en régimen Tipo I ($\eta_H \approx 1$), se habilita la inversión analítica ultrarrápida descrita en [[CAT-308_Metrologia_Analitica_Directa_Picos_Bragg_Fourier_2D]]. Si $\eta_H > 1.3$, el software alerta al operador sobre desviaciones acumulativas en el sistema de barrido optomecánico.
