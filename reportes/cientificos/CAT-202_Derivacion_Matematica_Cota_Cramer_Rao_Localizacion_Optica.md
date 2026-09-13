# CAT-202 [MAT]: Derivación Matemática de la Cota Inferior de Cramér-Rao en Localización Óptica Sub-píxel
## Matrices de Información de Fisher, Ruido Mixto Poisson-Gaussiano y Cotas Fundamentales para Haces Gaussianos y Donut LG01

---

**Signatura Bibliotecaria:** `CAT-202`  
**Clasificación Temática:** `[MAT]` Fundamentos Matemáticos y Derivaciones Analíticas  
**Pilar:** II — Super-Resolución Óptica, Detección Sub-píxel y Curación Espacial  
**Autoría:** José Luis González Peñafiel (INS-UNSAM / CONICET) — PyPrinting 3.0  
**Fecha de Publicación:** Septiembre 2026  
**Estado:** Producción / Consolidado  
**Documentos Vinculados:**  
- [[CAT-203_Presupuesto_Incertidumbre_Metrologica_ISOGUM_Microscopia]] (Aplicación física experimental, balances ISO/GUM e instrumentación)  
- [[CAT-201_Deconvolucion_Optica_Richardson_Lucy_y_Tracking_Trackpy]] (Algoritmo de seguimiento centroidal y deconvolución)  
- [[CAT-204_Curacion_Fotometrica_Desacople_MultiGaussiano_Consistencia]] (Desacople de multímeros y reglas de consistencia)  

---

> [!TIP] Aplicación e Impacto en Metrología Óptica Experimental
> Para consultar la manifestación física de esta deducción matemática en los 5 objetivos del microscopio, filtrado por pinholes confocales (0.46 AU), deriva térmica experimental y presupuesto ISO/GUM de incertidumbre expandida ($k=2$), consulte la nota física vinculada:  
> 👉 **[[CAT-203_Presupuesto_Incertidumbre_Metrologica_ISOGUM_Microscopia]]**

---

### Resumen Ejecutivo

La determinación de la posición central $(x_0, y_0)$ de nanopartículas plasmónicas o moléculas individuales mediante microscopía óptica de campo lejano está limitada en última instancia por la fluctuación cuántica en el arribo de fotones (ruido de disparo de Poisson) y el ruido electrónico de lectura del sensor (ruido gaussiano del detector sCMOS/EMCCD).

Este reporte formaliza la deducción analítica rigurosa de la **Cota Inferior de Cramér-Rao (CRLB)** para la localización espacial de emisores individuales. Se formula la Matriz de Información de Fisher (FIM) bajo un modelo estocástico de ruido mixto Poisson-Gaussiano, deduciendo la expresión asintótica para un perfil emisor Gaussiano bidimensional integrado sobre píxeles finitos, y extendiendo la derivación a haces estructurados en forma de dona (vórtices ópticos Laguerre-Gauss $LG_{01}$). Asimismo, se deduce analíticamente la varianza de cuantización espacial de píxel ($\Delta x^2 / 12$) y se calcula la matriz de covarianza de parámetros $\mathbf{PCov}$ en el ajuste no lineal de mínimos cuadrados ponderados.

---

## 1. Modelo Estocástico de Formación de la Imagen Óptica

Consideremos un detector de píxeles discretos (cámara sCMOS o matriz de muestreo confocal de la tarjeta NI-DAQmx). La señal esperada en el píxel $k$-ésimo con centro en $(x_k, y_k)$ y área $\Delta x \times \Delta y$ producida por un emisor ubicado en $(x_0, y_0)$ viene dada por:

$$\mu_k(\mathbf{\theta}) = N \int_{x_k - \Delta x / 2}^{x_k + \Delta x / 2} \int_{y_k - \Delta y / 2}^{y_k + \Delta y / 2} \text{PSF}(x - x_0, y - y_0) \, dx \, dy + b_k$$

donde:
- $\mathbf{\theta} = (x_0, y_0, N, b)^T$ es el vector de parámetros a estimar.
- $N$ es el número total de fotones colectados provenientes del emisor.
- $b_k$ es el número de fotones de fondo promedio por píxel (autofluorescencia o dispersión parasitaria).
- $\text{PSF}(x, y)$ es la función de dispersión de punto normalizada unitariamente: $\iint_{\mathbb{R}^2} \text{PSF}(x, y) \, dx \, dy = 1$.

### Estadística Mixta de Detección:
El número de electrones o cuentas digitales registradas en el píxel $k$, denotado $I_k$, sigue una distribución de Poisson convolucionada con el ruido de lectura gaussiano de la electrónica:

$$I_k \sim \mathcal{P}(\mu_k(\mathbf{\theta})) + \mathcal{N}(0, \sigma_{\text{read}}^2)$$

La función de log-verosimilitud para el conjunto de $K$ píxeles independientes en el régimen dominado por fotones ($\mu_k \gg \sigma_{\text{read}}^2$) es:

$$\ln \mathcal{L}(\mathbf{I} | \mathbf{\theta}) = \sum_{k=1}^K \left[ I_k \ln \mu_k(\mathbf{\theta}) - \mu_k(\mathbf{\theta}) - \ln(I_k!) \right]$$

---

## 2. Deducción de la Matriz de Información de Fisher (FIM)

La **Matriz de Información de Fisher** $\mathbf{F} \in \mathbb{R}^{4 \times 4}$ cuantifica la cantidad de información estocástica que la imagen observada contiene respecto al vector de parámetros $\mathbf{\theta}$:

$$F_{ij} = \mathbb{E}\left[ \left( \frac{\partial \ln \mathcal{L}}{\partial \theta_i} \right) \left( \frac{\partial \ln \mathcal{L}}{\partial \theta_j} \right) \right] = - \mathbb{E}\left[ \frac{\partial^2 \ln \mathcal{L}}{\partial \theta_i \partial \theta_j} \right]$$

Calculando las derivadas de la log-verosimilitud:

$$\frac{\partial \ln \mathcal{L}}{\partial \theta_i} = \sum_{k=1}^K \left( \frac{I_k}{\mu_k} - 1 \right) \frac{\partial \mu_k}{\partial \theta_i}$$

Dado que $\mathbb{E}[I_k] = \mu_k$ y $\text{Cov}(I_k, I_m) = \mu_k \delta_{km}$:

$$F_{ij} = \sum_{k=1}^K \sum_{m=1}^K \frac{1}{\mu_k \mu_m} \mathbb{E}\left[ (I_k - \mu_k)(I_m - \mu_m) \right] \frac{\partial \mu_k}{\partial \theta_i} \frac{\partial \mu_m}{\partial \theta_j}$$

$$F_{ij} = \sum_{k=1}^K \frac{1}{\mu_k(\mathbf{\theta})} \left( \frac{\partial \mu_k(\mathbf{\theta})}{\partial \theta_i} \right) \left( \frac{\partial \mu_k(\mathbf{\theta})}{\partial \theta_j} \right)$$

---

## 3. Cota Inferior de Cramér-Rao para Perfiles Gaussianos 2D

Para una función de punto gaussiana bidimensional simétrica con cintura $\sigma_{\text{psf}}$:

$$\text{PSF}(x - x_0, y - y_0) = \frac{1}{2\pi \sigma_{\text{psf}}^2} \exp\left[ -\frac{(x - x_0)^2 + (y - y_0)^2}{2\sigma_{\text{psf}}^2} \right]$$

### 3.1 Régimen Límite de Píxel Infinitesimal ($\Delta x \to 0$, Sin Ruido de Fondo $b=0$)
En el límite continuo sin fondo:
$$\mu(\mathbf{r}) = N \, \text{PSF}(\mathbf{r} - \mathbf{r}_0)$$
$$\frac{\partial \mu(\mathbf{r})}{\partial x_0} = -N \frac{\partial \text{PSF}}{\partial x} = N \frac{(x - x_0)}{\sigma_{\text{psf}}^2} \text{PSF}(\mathbf{r} - \mathbf{r}_0)$$

El elemento de Fisher para la coordenada $x_0$ resulta:

$$F_{x_0, x_0} = \int_{\mathbb{R}^2} \frac{1}{N \, \text{PSF}(\mathbf{r})} \left[ N \frac{(x - x_0)}{\sigma_{\text{psf}}^2} \text{PSF}(\mathbf{r}) \right]^2 d^2r = \frac{N}{\sigma_{\text{psf}}^4} \int_{\mathbb{R}^2} (x - x_0)^2 \text{PSF}(\mathbf{r}) d^2r$$

Puesto que $\int (x - x_0)^2 \text{PSF}(\mathbf{r}) d^2r = \sigma_{\text{psf}}^2$:

$$F_{x_0, x_0} = \frac{N}{\sigma_{\text{psf}}^4} \cdot \sigma_{\text{psf}}^2 = \frac{N}{\sigma_{\text{psf}}^2}$$

Por el **Teorema de Cramér-Rao**, la varianza de cualquier estimador insesgado $\hat{x}_0$ está acotada inferiormente por la inversa del elemento de Fisher:

$$\text{Var}(\hat{x}_0) \ge \left[ \mathbf{F}^{-1} \right]_{x_0, x_0} \implies \bbox[12px,border:2px solid #2563eb,background:#eff6ff]{
\sigma_{x,\text{CRLB}} = \frac{\sigma_{\text{psf}}}{\sqrt{N}} = \frac{\text{FWHM}_{\text{psf}}}{2\sqrt{2\ln 2} \sqrt{N}} \approx \frac{\text{FWHM}_{\text{psf}}}{2.355 \sqrt{N}}
}$$

---

### 3.2 Corrección por Cuantización de Píxel y Ruido de Fondo Homogéneo ($b > 0$)

Cuando los píxeles poseen un tamaño finito $\Delta x$ y coexiste un fondo de fotones $b$ por píxel, Mortensen et al. (2010) y Thompson et al. (2002) derivaron analíticamente la corrección perturbativa de segundo orden:

$$\sigma_{x,\text{CRLB}}^2 = \frac{\sigma_{\text{psf}}^2 + \frac{\Delta x^2}{12}}{N} \left[ 1 + 4\tau + \sqrt{\frac{2\tau}{1 + 4\tau}} \right]$$

donde el parámetro adimensional de ruido de fondo $\tau$ está definido por:

$$\tau = \frac{2\pi \sigma_{\text{psf}}^2 \, b}{N \, \Delta x^2}$$

#### Interpretación de los Componentes:
1. $\frac{\sigma_{\text{psf}}^2}{N}$: Límite fotónico fundamental de Abbe/Poisson.
2. $\frac{\Delta x^2}{12 N}$: Término de ensanchamiento por integración espacial sobre el área del píxel finito.
3. El término entre corchetes $[\dots]$: Factor de degradación no lineal debido a la varianza de fondo $b$. Para $b \to 0 \implies \tau \to 0$, el término converge a $1.0$.

---

## 4. Deducción de la Varianza de Cuantización Espacial ($\Delta x^2 / 12$)

Cuando un centroide continuo $x_0 \in \mathbb{R}$ se muestrea mediante un píxel de paso espacial $\Delta x$, la coordenada registrada se mapea al entero más próximo $x_k = k \Delta x$. El error de cuantización espacial es una variable aleatoria uniforme:

$$\epsilon_x = x_0 - x_k \sim \mathcal{U}\left( -\frac{\Delta x}{2}, +\frac{\Delta x}{2} \right)$$

La función de densidad de probabilidad es $p(\epsilon_x) = \frac{1}{\Delta x}$ para $\epsilon_x \in [-\Delta x/2, \Delta x/2]$.  
Calculando la esperanza y la varianza:

$$\mathbb{E}[\epsilon_x] = \int_{-\Delta x/2}^{+\Delta x/2} \epsilon_x \frac{1}{\Delta x} d\epsilon_x = 0$$

$$\text{Var}(\epsilon_x) = \int_{-\Delta x/2}^{+\Delta x/2} \epsilon_x^2 \frac{1}{\Delta x} d\epsilon_x = \frac{1}{\Delta x} \left[ \frac{\epsilon_x^3}{3} \right]_{-\Delta x/2}^{+\Delta x/2} = \frac{1}{\Delta x} \left( \frac{\Delta x^3}{24} - \left(-\frac{\Delta x^3}{24}\right) \right) = \frac{\Delta x^2}{12}$$

Por lo tanto, la incertidumbre estándar pura de pixelación es:

$$\bbox[10px,border:1px solid #059669,background:#ecfdf5]{
u_{\text{pix}} = \frac{\Delta x}{\sqrt{12}} \approx 0.2887 \cdot \Delta x
}$$

---

## 5. Cota de Cramér-Rao para Haces Estructurados Donut ($LG_{01}$)

En técnicas avanzadas de súper-resolución confocal y nano-impresión inversa (MINFLUX, STED o alineación óptica con modos de vórtice), se emplea un haz con perfil toroidal o "dona" (modo Laguerre-Gauss $LG_{01}$):

$$\text{PSF}_{\text{donut}}(\mathbf{r}) = \frac{2}{\pi w_0^4} r^2 \exp\left( -\frac{2r^2}{w_0^2} \right)$$

donde $r^2 = (x - x_0)^2 + (y - y_0)^2$ y $w_0$ es el radio de cintura del haz.

### Información de Fisher en el Nulo Central ($r \to 0$):
En torno al cero de intensidad central, la derivada espacial es:

$$\frac{\partial \text{PSF}_{\text{donut}}}{\partial x_0} = -\frac{2}{\pi w_0^4} \left[ -2(x - x_0) \right] e^{-2r^2/w_0^2} \approx \frac{4 (x - x_0)}{\pi w_0^4}$$

Calculando el integrando de Fisher cerca del nulo:

$$\frac{1}{\text{PSF}_{\text{donut}}} \left( \frac{\partial \text{PSF}_{\text{donut}}}{\partial x_0} \right)^2 \approx \frac{\pi w_0^4}{2 r^2} \left[ \frac{16 (x - x_0)^2}{\pi^2 w_0^8} \right] = \frac{8}{\pi w_0^4} \frac{(x - x_0)^2}{r^2}$$

Promediando angularmente $\langle (x - x_0)^2 / r^2 \rangle = 1/2$:

$$F_{x_0, x_0}^{\text{donut}} \propto \frac{N}{w_0^2}$$

#### Ventaja Cuántica Fundamental del Haz Donut:
A diferencia del haz gaussiano convencional donde los fotones del pico central aportan información débil sobre el desplazamiento (ya que la derivada en el vértice de la campana es nula, $\partial \text{PSF}/\partial x|_{r=0} = 0$), en el haz donut la tasa fraccionaria de variación cerca del nulo diverge:

$$\lim_{r \to 0} \frac{1}{\text{PSF}} \left(\frac{\partial \text{PSF}}{\partial r}\right)^2 \to \infty$$

Esto permite que un emisor ubicado en las inmediaciones del nulo alcance una resolución nanométrica con **un orden de magnitud menos fotones colectados**:

$$\sigma_{x,\text{donut}} \approx \frac{L_{\text{donut}}}{2\sqrt{N_{\text{donut}}}}$$
donde $L_{\text{donut}} \ll \text{FWHM}_{\text{psf}}$ es el diámetro eficaz del pozo de intensidad.

---

## 6. Matriz de Covarianza en Ajuste Numérico de Mínimos Cuadrados ($\mathbf{PCov}$)

En el software `psf_analyzer.py` y `modules/confocal.py`, el ajuste del perfil se realiza mediante optimización no lineal de Levenberg-Marquardt (`scipy.optimize.curve_fit`), resolviendo el sistema:

$$\hat{\mathbf{\theta}} = \arg\min_{\mathbf{\theta}} \sum_{k=1}^K w_k \left[ I_k - f(x_k, y_k; \mathbf{\theta}) \right]^2$$

Linealizando en torno al mínimo óptimo mediante la matriz Jacobiana $J_{ki} = \frac{\partial f(x_k, y_k)}{\partial \theta_i}$, la matriz de covarianza de los parámetros ajustados es:

$$\mathbf{PCov} = \left( \mathbf{J}^T \mathbf{W} \mathbf{J} \right)^{-1}$$

donde $\mathbf{W} = \text{diag}(w_k)$ es la matriz de ponderación estadística.  
Si los pesos se asignan de acuerdo a la inversa de la varianza de Poisson $w_k = 1 / \sigma_k^2 \approx 1 / I_k$, entonces:

$$\left[ \mathbf{J}^T \mathbf{W} \mathbf{J} \right]_{ij} = \sum_{k=1}^K \frac{1}{I_k} \frac{\partial f_k}{\partial \theta_i} \frac{\partial f_k}{\partial \theta_j} \equiv F_{ij}$$

La matriz de covarianza de mínimos cuadrados ponderados **satura asintóticamente la Cota Inferior de Cramér-Rao**:

$$\mathbf{PCov} = \mathbf{F}^{-1} \implies \bbox[10px,border:1px solid #b91c1c,background:#fef2f2]{
u_{\text{fit}}(x_0) = \sqrt{\mathbf{PCov}[x_0, x_0]} \ge \sigma_{x,\text{CRLB}}
}$$

---

## 7. Implementación de Referencia en Python (PyPrinting 3.0)

```python
import numpy as np

def compute_cramer_rao_bound(fwhm_nm: float, n_photons: float, 
                              pixel_size_nm: float, bg_photons_per_pixel: float) -> dict:
    """
    Calcula analíticamente la Cota Inferior de Cramér-Rao (CRLB) para un emisor Gaussiano 2D.
    
    Parámetros:
      fwhm_nm: Ancho a media altura de la PSF óptica en nm.
      n_photons: Número total de fotones colectados del emisor (N).
      pixel_size_nm: Tamaño de píxel de muestreo en nm (Delta x).
      bg_photons_per_pixel: Fotones promedio de fondo por píxel (b).
      
    Retorna:
      Diccionario con crlb_puro_nm, crlb_corregido_nm, u_pixel_nm y factor_tau.
    """
    sigma_psf = fwhm_nm / (2.0 * np.sqrt(2.0 * np.log(2.0)))
    
    # 1. CRLB puro (límite continuo sin fondo)
    crlb_puro = sigma_psf / np.sqrt(n_photons)
    
    # 2. Varianza de pixelación espacial
    u_pix = pixel_size_nm / np.sqrt(12.0)
    
    # 3. Parámetro adimensional de fondo tau
    tau = (2.0 * np.pi * (sigma_psf**2) * bg_photons_per_pixel) / (n_photons * (pixel_size_nm**2))
    
    # 4. CRLB completo corregido por píxel y fondo (Mortensen et al.)
    noise_factor = 1.0 + 4.0 * tau + np.sqrt(2.0 * tau / (1.0 + 4.0 * tau))
    var_crlb = ((sigma_psf**2 + (pixel_size_nm**2) / 12.0) / n_photons) * noise_factor
    crlb_corregido = np.sqrt(var_crlb)
    
    return {
        "sigma_psf_nm": float(sigma_psf),
        "crlb_puro_nm": float(crlb_puro),
        "u_pix_nm": float(u_pix),
        "tau_parameter": float(tau),
        "crlb_total_nm": float(crlb_corregido)
    }
```

---

## 8. Conclusiones

1. **Límite Teórico Fundamental:** La incertidumbre de localización óptica no puede ser arbitrariamente pequeña; está acotada por $\sigma_{\text{psf}} / \sqrt{N}$. Para $10^4$ fotones y $\text{FWHM} = 284\,\text{nm}$, la cota cuántica fundamental es $\approx 1.2\,\text{nm}$.
2. **Impacto de la Pixelación:** La discretización espacial introduce un suelo de error uniforme $\Delta x / \sqrt{12}$, que exige pasos de muestreo $\Delta x \le 25\,\text{nm}$ para alcanzar precisión sub-nanométrica.
3. **Consistencia con Mínimos Cuadrados:** El estimador no lineal de Gauss ponderado por Poisson en `PyPrinting 3.0` es asintóticamente eficiente, alcanzando el límite de Cramér-Rao cuando el fondo se modela adecuadamente.
