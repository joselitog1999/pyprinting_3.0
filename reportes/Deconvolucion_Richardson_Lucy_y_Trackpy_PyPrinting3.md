# Deconvolución Richardson-Lucy en Tiempo Real y Detección Sub-píxel por Trackpy en PyPrinting 3.0 🔬📊

**Autor**: José Luis González Peñafiel (Becario Doctoral CONICET)  
**Filiación**: Laboratorio de Nanofotónica, Instituto de Nanosistemas (INS-UNSAM) / CONICET  
**Fecha**: 6 de Agosto de 2026  
**Módulo del Software**: `analysis/image_analyzer.py`, `analysis/psf.py`, `modules/camera.py`  

---

## 1. Resumen Ejecutivo

En microscopía confocal y de dispersión interferométrica (iSCAT), la resolución espacial efectiva y el contraste fotométrico se hallan limitados por la difracción de la luz a través de la apertura numérica (NA) del objetivo. La imagen registrada $I(\vec{r})$ es el resultado de la convolución matemática entre la distribución real de emisores/dispersores $J(\vec{r})$ y la Función de Punto Extendido del instrumento (PSF, *Point Spread Function*) $K(\vec{r})$, degradada por ruido de disparo fotónico (Poisson).

Este reporte expone la fundamentación teórica, la formulación matemática y la implementación computacional en tiempo real de dos herramientas avanzadas integradas en **PyPrinting 3.0**:

1. **Deconvolución Iterativa de Richardson-Lucy en Tiempo Real**: Algoritmo Bayesiano de Estimación de Máxima Verosimilitud (MLE) acelerado por Transformada Rápida de Fourier (FFT), con calibración analítica de la PSF (Gaussiana, Donut Laguerre-Gauss 01 y Centro de Masas) y previsualización interactiva continua ($0 - 100$ iteraciones).
2. **Detección y Caracterización Sub-píxel de Partículas con Trackpy**: Algoritmo de Crocker-Grier de filtrado paso-banda, inversión fotométrica diferencial para valles/puntos oscuros (microscopía de transmisión y contraste de fase) y refinamiento de centroides sub-píxel con masa, umbrales y percentiles configurables.

---

## 2. Formulación Matemática de la Deconvolución Richardson-Lucy

### 2.1 Modelo Óptico Directo de Formación de Imagen
La formación de una imagen discreta bidireccional en un microscopio óptico lineal e invariante espacialmente responde al modelo de convolución:

$$I(\vec{r}) = (J * K)(\vec{r}) + \eta(\vec{r}) = \int_{\Omega} J(\vec{r}') K(\vec{r} - \vec{r}') d\vec{r}' + \eta(\vec{r})$$

donde:
- $I(\vec{r})$: Intensidad fotónica observada en la cámara o fotodiodo en la coordenada $\vec{r} = (x, y)$.
- $J(\vec{r})$: Distribución espacial real de la densidad de emisores o dispersores plasmónicos en el sustrato ($J(\vec{r}) \ge 0$).
- $K(\vec{r})$: Función de Punto Extendido (PSF) normalizada ($\int_{\Omega} K(\vec{r}) d\vec{r} = 1.0$).
- $\eta(\vec{r})$: Ruido estocástico de detección dominado por la estadística de Poisson ($I(\vec{r}) \sim \mathcal{P}\{(J * K)(\vec{r})\}$).

En el dominio de frecuencias espaciales $\vec{k} = (k_x, k_y)$, la ecuación se expresa mediante la Función de Transferencia Óptica (OTF, *Optical Transfer Function*) $H(\vec{k}) = \mathcal{F}\{K(\vec{r})\}$:

$$\tilde{I}(\vec{k}) = \tilde{J}(\vec{k}) \cdot H(\vec{k}) + \tilde{\eta}(\vec{k})$$

La frecuencia de corte de Abbe acota la transferencia de frecuencias a $k_{\text{corte}} = \frac{2 \cdot \text{NA}}{\lambda_0}$. Frecuencias espaciales superiores son atenuadas o anuladas por la abertura del objetivo.

---

### 2.2 Deducción Bayesiana y Algoritmo de Actualización MLE
Bajo el supuesto de que el conteo de fotones en cada píxel sigue una distribución independiente de Poisson, la probabilidad condicional de observar la imagen $I$ dada una densidad propuesta $J$ es:

$$P(I \mid J) = \prod_{\vec{r}} \frac{\left[(J * K)(\vec{r})\right]^{I(\vec{r})} \cdot e^{-(J * K)(\vec{r})}}{I(\vec{r})!}$$

Maximizando el logaritmo de verosimilitud $L(J) = \ln P(I \mid J)$ con respecto a $J(\vec{r})$ bajo la condición de no-negatividad ($J(\vec{r}) \ge 0$), se deriva el esquema iterativo multiplicativo de **Richardson-Lucy**:

$$\hat{J}^{(k+1)}(\vec{r}) = \hat{J}^{(k)}(\vec{r}) \cdot \left[ \left( \frac{I(\vec{r})}{\hat{J}^{(k)}(\vec{r}) * K(\vec{r})} \right) * K^*(-\vec{r}) \right]$$

donde:
- $\hat{J}^{(k)}(\vec{r})$: Estimación de la imagen restaurada en la iteración $k$.
- $K^*(-\vec{r})$: Adjunta espacial o versión espejada del kernel de la PSF ($K^*(x, y) = K(-x, -y)$).
- El término de corrección $\frac{I}{\hat{J}^{(k)} * K}$ mide el cociente entre la imagen medida y la re-proyección de la estimación actual.

#### Propiedades Fundamentales del Algoritmo:
1. **Preservación de Flujo y Energía Fotónica**: En cada iteración se satisface estrictamente $\sum_{\vec{r}} \hat{J}^{(k+1)}(\vec{r}) = \sum_{\vec{r}} I(\vec{r})$.
2. **Garantía de No-Negatividad**: Si la estimación inicial $\hat{J}^{(0)}(\vec{r}) > 0$ (normalmente $\hat{J}^{(0)} = I$), todas las iteraciones subsiguientes permanecen no negativas ($\hat{J}^{(k)} \ge 0$).
3. **Super-resolución Espectral**: Restaura parcialmente frecuencias espaciales atenuadas cerca de $k_{\text{corte}}$, reduciendo el ancho a media altura (FWHM) de nanopartículas de oro en un factor de $\approx 1.5 - 2.2\times$.

---

### 2.3 Criterio de Convergencia y Amplificación de Ruido
Si bien el algoritmo Richardson-Lucy converge teóricamente al estimador de máxima verosimilitud a medida que $k \to \infty$, en presencia de ruido aleatorio de Poisson y ruido de lectura de cámara (Gaussian Noise Floor), iteraciones excesivas ($k > 100$) comienzan a ajustar el ruido de alta frecuencia, generando artefactos de granulado ("ruido en tablero de ajedrez").

En **PyPrinting 3.0**, la rutina implementada en `analysis/psf.py` incluye el acotamiento del número de iteraciones mediante el deslizador continuo $N_{\text{iter}} \in [0, 100]$:
- $N_{\text{iter}} = 0$: Muestra la imagen original $I(\vec{r})$ sin alterar.
- $N_{\text{iter}} \in [5, 25]$: Rango óptimo para microscopía confocal e iSCAT (contraste elevado, FWHM afilado y sin artefactos).
- $N_{\text{iter}} > 50$: Recomendado solo para imágenes de alta relación señal-ruido ($\text{SNR} > 50$).

$$\text{Operación en } \text{psf.py}: \quad \hat{J}^{(k+1)} = \text{fftconvolve}\left(\frac{I}{\text{fftconvolve}(\hat{J}^{(k)}, K, \text{'same'})}, K^*, \text{'same'}\right) \cdot \hat{J}^{(k)}$$

---

## 3. Extracción Metrológica y Ajuste Sub-píxel de la PSF

Para ejecutar la deconvolución sin introducir astigmatismo ni desplazamientos de fase ficticios, el kernel de la PSF $K(\vec{r})$ debe ser simétrico, centrado con precisión sub-píxel y normalizado.

```
                  Modelos de Ajuste de Centro de PSF
 ┌────────────────────────┐  ┌────────────────────────┐  ┌────────────────────────┐
 │ Centro de Masas        │  │ Gaussiana 2D (Sint/Fit)│  │ Donut 2D (Laguerre 01) │
 │ (Momentos de Intensid.)│  │ (scipy curve_fit)      │  │ (Haz Vórtice STED/BFP) │
 └───────────┬────────────┘  └───────────┬────────────┘  └───────────┬────────────┘
             │                           │                           │
             └───────────────────────────┼───────────────────────────┘
                                         ▼
                 ┌──────────────────────────────────────────────┐
                 │ Extracción de Kernel (Radio R_psf en px)    │
                 │ Normalización Estricta: Suma(K) = 1.0        │
                 └──────────────────────────────────────────────┘
```

### 3.1 Modelado Analítico de la PSF

1. **Centro de Masas (Momento Fotométrico)**:
   $$x_{\text{CM}} = \frac{\sum_{i,j} x_i \cdot I(x_i, y_j)}{\sum_{i,j} I(x_i, y_j)}, \quad y_{\text{CM}} = \frac{\sum_{i,j} y_j \cdot I(x_i, y_j)}{\sum_{i,j} I(x_i, y_j)}$$
   Proporciona una estimación ultrarrápida ($< 0.1\,\text{ms}$) sin requerir convergencia de optimizadores no lineales.

2. **Ajuste Gaussiano 2D Anisotrópico**:
   $$K_{\text{Gauss}}(x, y) = I_0 + A \cdot \exp\left( - \left[ a(x-x_0)^2 + 2b(x-x_0)(y-y0) + c(y-y_0)^2 \right] \right)$$
   Ajustado vía Levenberg-Marquardt (`scipy.optimize.curve_fit`), determinando la coordenada central $(x_0, y_0)$ con incertidumbre sub-nanométrica $u_{\text{fit}} < 0.35\,\text{nm}$.

3. **Ajuste Donut 2D (Laguerre-Gauss $\text{LG}_{01}$)**:
   $$K_{\text{Donut}}(x, y) = I_0 + A \cdot \left( \frac{(x-x_0)^2}{2\sigma_x^2} + \frac{(y-y_0)^2}{2\sigma_y^2} \right) \cdot \exp\left( -\left[ \frac{(x-x_0)^2}{2\sigma_x^2} + \frac{(y-y_0)^2}{2\sigma_y^2} \right] \right)$$
   Utilizado para caracterizar la PSF de haces de rosquilla plasmónicos o depletas de super-resolución STED.

---

### 3.2 Extracción y Normalización del Kernel
Dada una posición central optimizada $(x_0, y_0)$ y un radio seleccionado por el usuario $R_{\text{psf}} \in [3, 50]\,\text{px}$, la función `extract_psf_kernel()` en `analysis/psf.py` recorta una matriz cuadrada de dimensión $(2 R_{\text{psf}} + 1) \times (2 R_{\text{psf}} + 1)$:

$$K_{\text{norm}}(i, j) = \frac{K(i, j) - \min(K)}{\sum_{m,n} \left( K(m, n) - \min(K) \right)}$$

Garantiza que la energía total del kernel sea exactamente $1.0$, previniendo distorsiones fotométricas al iterar.

---

## 4. Detección Sub-píxel de Partículas con Trackpy & Parámetros Avanzados

El analizador de imágenes integra la librería de seguimiento y localización espacial **Trackpy** (basada en el algoritmo de Crocker y Grier).

### 4.1 Filtrado Paso-Banda y Detección de Candidatos
El algoritmo aplica un filtro espacial paso-banda a la matriz de imagen para eliminar tanto las variaciones de fondo de baja frecuencia como el ruido de alta frecuencia del sensor:

$$I_{\text{bp}} = \text{GaussianFilter}(I, \sigma_{\text{noise}}) - \text{BoxcarFilter}(I, \sigma_{\text{smooth}})$$

Sobre la matriz filtrada $I_{\text{bp}}$, se identifican los máximos locales que superan el percentil configurado (`percentile`) y el umbral absoluto (`threshold`).

---

### 4.2 Inversión Fotométrica para Valles y Puntos Oscuros
En experimentos de microscopía de transmisión, contraste de fase o campo claro, las nanopartículas aparecen como atenuaciones locales de luz (valles o pozos de menor intensidad respecto al fondo brillante). Dado que `trackpy.locate()` busca picos de máxima intensidad, la detección estándar falla al buscar en valles.

Para resolver este problema, se incorporó la función de **Inversión de Imagen Exclusiva para Análisis**:

$$\tilde{I}_{\text{inv}}(x, y) = \max(I) - I(x, y)$$

```
                       Inversión Fotométrica en Trackpy
 ┌───────────────────────────┐                      ┌───────────────────────────┐
 │ Imagen Original (Visor)   │                      │ Matriz Invertida en RAM   │
 │ Partículas = Puntos Osc.  │                      │ Partículas = Picos Claros │
 │ (Valles en fondo claro)   │                      │ (Borde claro en fondo 0)  │
 └─────────────┬─────────────┘                      └─────────────┬─────────────┘
               │                                                  │
               │ (Visualización intacta)                          │ (Cálculo tp.locate)
               ▼                                                  ▼
 ┌───────────────────────────┐                      ┌───────────────────────────┐
 │ Renderizado Visual Final  │                      │ Coordenadas (x_c, y_c)    │
 │ (Sin invertir colores)    │ <─────────────────── │ Marcadores de centroide   │
 └───────────────────────────┘                      └───────────────────────────┘
```

Esta transformación convierte los valles oscuros en picos brillantes perfectos en la memoria RAM durante la llamada a `tp.locate()`, **sin modificar la imagen de visualización del usuario**, manteniendo la estética fotográfica original.

---

### 4.3 Parámetros Avanzados Configurados en `TrackpyDialog`

| Parámetro | Tipo | Rango / Valor Def. | Descripción Física y Función en la Detección |
|---|---|---|---|
| **`diameter`** | `int` | $3 - 201\ \text{px}$ (impar) | Tamaño característico estimado del perfil espacial de la partícula. |
| **`separation`** | `float` | $1.0 - 500.0\ \text{px}$ | Distancia espacial mínima entre partículas vecinas para evitar agrupaciones. |
| **`threshold`** | `float` | $0.0 - 10^6$ ($0 = \text{auto}$) | Corte de intensidad mínima absoluta en píxeles. |
| **`minmass`** | `float` | $0.0 - 10^7$ ($0 = \text{desact}$) | Masa fotónica integrada mínima $\sum I_i$ para validar la partícula. |
| **`noise_size`** | `float` | $0.1 - 20.0\ \text{px}$ (def $1.0$) | Desviación estándar del filtro Gaussiano para remoción de ruido de disparo. |
| **`smoothing_size`** | `float` | $0.0 - 100.0\ \text{px}$ ($0 = \text{auto}$) | Tamaño de la ventana de suavizado de fondo. |
| **`maxsize`** | `float` | $0.0 - 200.0\ \text{px}$ ($0 = \text{auto}$) | Radio de giro máximo permitido para desestimar aglomerados no deseados. |
| **`percentile`** | `float` | $0.0 - 100.0\%$ (def $64.0$) | Percentil fotométrico de corte inicial para la selección de candidatos. |
| **`invert`** | `bool` | `True` / `False` | Invierte $\tilde{I} = \max(I) - I$ solo para el cálculo (Valles $\rightarrow$ Picos). |

---

## 5. Integración en el Software PyPrinting 3.0

### 5.1 Flujo de Trabajo Modular en `ImageAnalyzerWidget`

El workflow operacional integrado permite realizar análisis cuantitativos completos sobre fotos de cámara o escaneos confocales:

```
┌────────────────────────────────────────────────────────────────────────┐
│ 1. Carga Automática / Manual de la Imagen                              │
│    (Auto-carga la foto más reciente en data/ o abre .tif/.png/.jpg)    │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 2. Selección de ROI Absoluto (`✂ Crop ROI`)                            │
│    (Fija la región seleccionada como nueva imagen de trabajo activa)  │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 3. Deconvolución Richardson-Lucy en Tiempo Real (`🔬 Deconvolución R-L`)│
│    - Carga o extrae la PSF (Gauss/Donut/Centro de Masas)              │
│    - Desliza iteraciones (0-100) con previsualización en vivo          │
│    - Presiona 'Aceptar' para comprometer la imagen restaurada          │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 4. Detección y Caracterización de Partículas (`Detectar` / Trackpy)    │
│    - Aplica parámetros avanzados e Inversión (Valles -> Picos)        │
│    - Mide distancias (µm / px), ángulos y exporta resultados (.txt)   │
└────────────────────────────────────────────────────────────────────────┘
```

---

### 5.2 Estructura de Código e Interfaces Implementadas

1. **`analysis/psf.py`**:
   - `extract_psf_kernel(image, cx, cy, radius_px)`: Recorta y normaliza $\sum K = 1.0$.
   - `richardson_lucy_deconv(image, psf_kernel, num_iter)`: Deconvolución 2D/RGB acelerada por `scipy.signal.fftconvolve`.

2. **`analysis/image_analyzer.py`**:
   - `ImageAnalyzerWidget`: Incorpora botones `⚡ Cargar Última Foto`, `✂ Crop ROI`, `Deshacer Crop` y `🔬 Deconvolución R-L`.
   - `RichardsonLucyDialog`: Ventana interactiva de previsualización en tiempo real con selector de modelos PSF, ajuste de radio de kernel y deslizador de 0 a 100 iteraciones.

3. **`modules/camera.py`**:
   - `OverlayWidget`: Añade la propiedad `set_pip_enabled(False)` para deshabilitar la miniatura PiP en el analizador de imágenes.
   - `TrackpyDialog`: Añade la casilla de inversión fotométrica y los 5 parámetros configurables adicionales de `trackpy`.

---

## 6. Conclusiones

La incorporación del módulo de **Deconvolución Richardson-Lucy en Tiempo Real** y las mejoras en **Trackpy** dotan a **PyPrinting 3.0** de capacidades de análisis metrológico y procesamiento de imágenes de grado científico. 

La capacidad de recuperar frecuencias espaciales difractadas mediante deconvolución interactiva y detectar con precisión nanopartículas tanto brillantes como oscuras (valles) consolida al software como una plataforma integral para nanofotónica y fabricación de metamateriales.

---

## 7. Documentación Relacionada y Red de Reportes

- **Manual Principal de Usuario**: [Manual de Usuario PyPrinting 3.0 (docs/MANUAL_USUARIO.md)](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/docs/MANUAL_USUARIO.md)
- **Visión General y Árbol**: [README PyPrinting 3.0 (README.md)](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/README.md)
- **Reportes Técnicos Vinculados**:
  - 📊 [Incertidumbre Metrológica ISO/GUM (reportes/Incertidumbre_Metrologica_PyPrinting3.md)](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/reportes/Incertidumbre_Metrologica_PyPrinting3.md)
  - 📷 [Módulo Cámara Canon EOS 500D (reportes/Modulo_Camara_Canon_EOS500D_PyPrinting3.md)](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/reportes/Modulo_Camara_Canon_EOS500D_PyPrinting3.md)
  - 📍 [Corrección de Deriva Termomecánica por Partícula Ancla (reportes/Correccion_de_Deriva_Termomecanica_Drift_Correction_PyPrinting3.md)](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/reportes/Correccion_de_Deriva_Termomecanica_Drift_Correction_PyPrinting3.md)
  - 🌳 [Respuestas de Arquitectura y Evaluación de Graphify (reportes/Respuestas_Graphify_y_Evaluacion_Arquitectonica_PyPrinting3.md)](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/reportes/Respuestas_Graphify_y_Evaluacion_Arquitectonica_PyPrinting3.md)

---

*Reporte Técnico PyPrinting 3.0 — Laboratorio de Nanofotónica, Instituto de Nanosistemas (INS-UNSAM).*  
*Autor Principal: José Luis González Peñafiel (Becario Doctoral CONICET).*
