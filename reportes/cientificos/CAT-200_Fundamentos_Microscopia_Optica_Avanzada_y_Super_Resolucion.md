# CAT-200: Fundamentos de Microscopía Óptica Avanzada: Del Límite de Difracción a la Super-Resolución e Interferometría (iSCAT)
## Tratado Rector de Óptica de Fourier, Función de Dispersión de Punto (PSF), Microscopía Confocal, Detección Interferométrica y Cota Cramér-Rao

---

**Signatura Bibliotecaria:** `CAT-200`  
**Clasificación Temática:** `[FIS]` / `[MAT]` Documento Rector de Microscopía Óptica, Difracción y Metrología Sub-píxel  
**Pilar:** Pilar II — Super-Resolución Óptica, Detección Sub-píxel y Espectrometría (NODO RECTOR)  
**Autoría:** José Luis González Peñafiel (*Becario Doctoral CONICET*), Comité Científico PyPrinting 3.0  
**Fecha de Publicación:** Septiembre 2026  
**Estado:** Producción / Consolidado  
**Módulos Asociados:** `analysis/lattice_disorder_gui.py`, `analysis/psf_analyzer.py`, `analysis/image_analyzer.py`, `modules/camera.py`, `contrapropagante.py`  
**Documentos Vinculados:**  
- [[CAT-108_Teoria_Optica_Telescopio_Rele_4f_y_Canales_Confocales]] (Telescopio relé 4f, pinholes y acoplamiento)  
- [[CAT-201_Deconvolucion_Optica_Richardson_Lucy_y_Tracking_Trackpy]] (Deconvolución iterativa y tracking)  
- [[CAT-202_Derivacion_Matematica_Cota_Cramer_Rao_Localizacion_Optica]] (Derivación analítica formal del CRLB)  
- [[CAT-203_Presupuesto_Incertidumbre_Metrologica_ISOGUM_Microscopia]] (Balance ISO/GUM, uc=6.55 nm)  
- [[CAT-204_Curacion_Fotometrica_Desacople_MultiGaussiano_Consistencia]] (Desacople multi-gaussiano y monómeros)  
- [[CAT-206_Pipeline_SMLM_Picasso_Algoritmos_y_Deconvolucion]] (Picasso GaussMLE vs Trackpy+RL y ruido Poisson)  
- [[CAT-209_Morfologia_Matematica_Watershed_y_Fotometria_Apertura]] (Morfología matemática y cruce por cero LoG)  
- [[CAT-114_Pinzas_Opticas_Contrapropagantes_y_Microscopia_iSCAT]] (Microscopía interferométrica iSCAT)  

---

## 1. Resumen Ejecutivo

La microscopía óptica es la técnica metrológica fundamental en PyPrinting 3.0: permite inspeccionar la superficie de silanización, alinear láseres con precisión sub-micrométrica, monitorear en tiempo real la captura de coloides y reconstruir con resolución atómica efectiva las posiciones de las nanoestructuras impresas. Sin embargo, en el régimen nanoscópico, la imagen que llega al sensor no es una réplica fiel del objeto real, sino el resultado de convolucionar la distribución de materia con la **Función de Dispersión de Punto (Point Spread Function - PSF)** impuesta por la naturaleza ondulatoria de la luz.

Este reporte actúa como el **Nodo Rector y Nota Paraguas del Pilar II**. Establece el marco físico y matemático unificado que conecta todas las técnicas ópticas del laboratorio. Se analizan los límites clásicos de difracción (Abbe, Rayleigh y Sparrow), se compara la formación de imágenes coherente frente a incoherente, se detalla la física de la microscopía confocal y la supresión de luz fuera de foco por pinholes sub-Airy, se formaliza el principio de detección interferométrica sin marcadores **iSCAT**, y se demuestra cómo la Microscopía de Localización de Molécula Única (**SMLM**) elude la barrera de difracción mediante el desacople temporal de emisores, quedando acotada exclusivamente por la relación señal-ruido fotónica y la **Cota de Cramér-Rao (CRLB)**.

---

## 2. La Barrera Clásica de Difracción en Sistemas Ópticos

Considérese una lente o sistema de objetivos de microscopio de distancia focal $f$ y apertura de salida circular de radio $a$. Según la teoría de difracción escalar de Kirchhoff y la aproximación de campo lejano de Fraunhofer, la amplitud del campo eléctrico en el plano focal para una fuente puntual en el origen es la transformada de Fourier de la función de pupila circular $P(\rho)$:

$$E(r) \propto \int_0^a \rho \, J_0(k \rho r / f) \, d\rho = a^2 \frac{J_1(k a r / f)}{k a r / f}$$

donde $k = 2\pi n / \lambda$ es el vector de onda en el medio y $J_1$ es la función de Bessel de primer orden y primera especie. La distribución espacial de intensidad corresponde al célebre **Patrón de Difracción de Airy**:

$$I(r) = I_0 \left[ \frac{2 J_1(\pi \, d / \lambda \cdot \text{NA})}{\pi \, d / \lambda \cdot \text{NA}} \right]^2$$

donde $\text{NA} = n \sin\alpha$ es la apertura numérica del objetivo.

```
Patrón de Intensidad de Airy (Corte 1D):
                I_0
                 ▲
                / \\
               /   \\
              /     \\             Primer mínimo (Cero de difracción)
             /   |   \\                     |
  ---------/-----|-----\\-------------------v----------------- Intensidad
         /       |       \\                 .
   __   /        |        \\   __         .   .
  /  \\_/         |         \\_/  \\_______/     \\________
 -r_Airy        r=0         +r_Airy
```

### 2.1 Criterios de Resolución Clásicos
El primer mínimo nulo del patrón de Airy ocurre en el primer cero de la función de Bessel, $z_0 \approx 3.8317$:
$$\frac{2\pi}{\lambda} \text{NA} \, r_{\text{Airy}} = 3.8317 \implies r_{\text{Airy}} = \frac{3.8317}{\pi} \frac{\lambda}{2\text{NA}} \approx 1.22 \frac{\lambda}{2\text{NA}} = \frac{0.61 \lambda}{\text{NA}}$$

A partir de este perfil, surgen tres criterios clásicos para discernir dos emisores puntuales incoherentes:
1. **Límite de Abbe (1873)**: Frecuencia espacial de corte máxima en campo lejano transmitida por la pupila:
   $$d_{\text{Abbe}} = \frac{\lambda}{2 \text{NA}}$$
   Para $\lambda = 532\ \text{nm}$ y objetivo de inmersión en agua 60x ($\text{NA} = 1.20$), $d_{\text{Abbe}} = 221.7\ \text{nm}$.
2. **Criterio de Rayleigh (1896)**: El máximo central de una fuente coincide con el primer mínimo de la otra (caída de intensidad central del $\sim 19\%$):
   $$d_{\text{Rayleigh}} = 0.61 \frac{\lambda}{\text{NA}} \approx 270.4\ \text{nm}$$
3. **Criterio de Sparrow (1916)**: Desaparición del mínimo local central (segunda derivada nula $d^2 I / dx^2 = 0$):
   $$d_{\text{Sparrow}} \approx 0.50 \frac{\lambda}{\text{NA}} \approx 221.6\ \text{nm}$$

---

## 3. Taxonomía de Modalidades Ópticas en PyPrinting 3.0

Para seleccionar la técnica adecuada en cada fase experimental, el laboratorio clasifica sus microscopías según el mecanismo físico de generación de contraste:

| Modalidad Óptica | Mecanismo Físico de Contraste | Resolución Típica | Caso de Uso Principal en el Software |
| :--- | :--- | :---: | :--- |
| **Campo Claro / Contraste de Fase** | Absorción lineal y dispersión hacia campo lejano | $\sim 250 - 300\ \text{nm}$ (Difracción) | Visualización macroscópica de la muestra, alineación gruesa y tracking centroidal en `modules/camera.py`. |
| **Microscopía Confocal** | Rechazo espacial de luz fuera de foco mediante pinholes conjugados | $\sim 180 - 220\ \text{nm}$ lateral, $\sim 500\ \text{nm}$ axial | Mapeo 2D de fluorescencia y dispersión, control de inclinación $Z$ y espectroscopía SERS puntual. |
| **Interferometría de Dispersión (iSCAT)** | Interferencia homodina en campo común entre reflexión de sustrato y dispersión | $\sim 200\ \text{nm}$ (Difracción, pero sensibilidad a coloides sub-10 nm) | Detección libre de marcadores a kHz en `contrapropagante.py` (escalado $d^3$). |
| **Super-Resolución SMLM (PALM/STORM/DNA-PAINT)** | Desacople temporal de emisores estocásticos + ajuste Gauss-MLE | **$\mathbf{5 - 15\ nm}$ (Sub-difracción)** | Metrología cristalográfica de redes impresas en `analysis/lattice_disorder_gui.py`. |
| **Haces Estructurados (Donut / Vortex $LG_{01}$)** | Singularidad de fase óptica helicoidal $e^{i\ell\phi}$ con nulo de intensidad en el eje | $\sim 200\ \text{nm}$ (Perfil anular) | Alineación optomecánica y trampa óptica en `analysis/psf_analyzer.py`. |

---

## 4. Microscopía Confocal y Filtrado por Pinhole

En microscopía confocal de barrido láser, la iluminación y la detección están enfocadas sobre el mismo punto del plano focal de la muestra. La luz recolectada atraviesa un diafragma estenopeico circular (**pinhole**) conjugado ópticamente con el foco.

### 4.1 La Unidad Airy (Airy Unit - AU)
El tamaño del pinhole se normaliza universalmente en **Unidades Airy ($AU$)**, definidas como el diámetro del disco central de Airy proyectado en el plano del pinhole tras la magnificación total $\Gamma$:

$$d_{\text{Airy}}^{\text{pinhole}} = \Gamma \times \left( 1.22 \frac{\lambda}{\text{NA}} \right)$$

- **Régimen Estándar ($1.0\ AU$)**: Transmite el $83.8\%$ de la energía del disco central de Airy, equilibrando señal fotométrica y rechazo de fondo fuera de foco.
- **Régimen Super-Confocal ($0.4 - 0.6\ AU$)**: Utilizado en PyPrinting 3.0 con pinhole de $50\ \mu\text{m}$ ($\sim 0.46\ AU$, ver [[CAT-203_Presupuesto_Incertidumbre_Metrologica_ISOGUM_Microscopia]]). Estrecha la PSF lateral efectiva por un factor $\sqrt{2}$:
  $$\text{PSF}_{\text{confocal}}(\mathbf{r}) = \text{PSF}_{\text{iluminación}}(\mathbf{r}) \times \text{PSF}_{\text{detección}}(\mathbf{r})$$
  reduciendo el ancho FWHM efectivo a $\sim 160 - 180\ \text{nm}$.

---

## 5. Superando la Barrera de Difracción: El Paradigma SMLM

¿Cómo es posible medir la posición de dos nanopartículas separadas por $50\ \text{nm}$ si el disco de difracción mide $250\ \text{nm}$?

La microscopía de localización de molécula única (**SMLM**) no intenta estrechar el disco de difracción por medios físicos ópticos, sino que **desacopla temporalmente a los emisores**:
1. Si dos partículas emiten fotones simultáneamente a menos de $250\ \text{nm}$, sus perfiles se solapan y la óptica los fusiona en un cúmulo indistinguible.
2. Si los emisores se encienden y apagan estocásticamente de modo que en cada cuadro de video sólo emite una única partícula aislada dentro de un radio de difracción, el problema de difracción se convierte en un **problema de estimación estadística de parámetros**: encontrar el centro $(\mu_x, \mu_y)$ de una distribución de probabilidad conocida.

```
Emisión Simultánea (Límite de Difracción):      Emisión Desacoplada (SMLM):
      Partícula A     Partícula B                     Frame 1: Solo A      Frame 2: Solo B
           *               *                                *                   (apagada)
            \\             /                                  \\
             v           v                                     v
         ( Perfil Fusionado )                              Centro (x_A)        Centro (x_B)
         Incierto: ¿1 o 2?                                 Precisión: 5 nm     Precisión: 5 nm
```

---

## 6. Límite Fundamental de Precisión: La Cota de Cramér-Rao (CRLB)

La precisión con la que se puede localizar el centro de una fuente puntual difractiva aislada no está limitada por $\lambda / 2\text{NA}$, sino por la **Cota Inferior de Cramér-Rao (CRLB)** (derivada analíticamente en [[CAT-202_Derivacion_Matematica_Cota_Cramer_Rao_Localizacion_Optica]]).

Dada una muestra de $N$ fotones recolectados de la nanopartícula y un fondo homogéneo de $b$ fotones por píxel, cualquier estimador insesgado de posición $\hat{x}_0$ satisface:

$$\text{Var}(\hat{x}_0) \ge \sigma_{\text{CRLB}}^2 \approx \frac{\sigma_{\text{psf}}^2 + \frac{a_{\text{pix}}^2}{12}}{N} \left( 1 + \frac{4\tau}{1 + \sqrt{2\tau}} \right)$$

donde:
- $\sigma_{\text{psf}} = \text{FWHM}_{\text{psf}} / 2.355 \approx 139\ \text{nm}$ es el ancho estándar de la PSF.
- $a_{\text{pix}}$ es el tamaño físico del píxel proyectado en muestra.
- $\tau = 2\pi \sigma_{\text{psf}}^2 b / (N a_{\text{pix}}^2)$ es el parámetro adimensional de ruido de fondo.

### Consecuencia Fundamental:
Para una nanopartícula metálica brillante que emite o dispersa $N = 10.000$ fotones bajo bajo fondo ($\tau \ll 1$):
$$\sigma_{\text{CRLB}} \approx \frac{\sigma_{\text{psf}}}{\sqrt{N}} = \frac{139\ \text{nm}}{\sqrt{10.000}} = \frac{139}{100} = \mathbf{1.39\ nm}$$

La super-resolución óptica no desafía la teoría cuántica de Maxwell ni el principio de incertidumbre: **convierte la física ondulatoria de difracción en metrología estadística fotónica**.

---

## 7. Mapa de Navegación del Pilar II

Para profundizar en los aspectos matemáticos, algorítmicos y experimentales, consulte las monografías canónicas vinculadas:

```
                                  MAPA DE NAVEGACIÓN — PILAR II
                                                
                                   CAT-200 (ESTE DOCUMENTO)
                                        [NODO RECTOR]
                                              │
         ┌───────────────────┬────────────────┴───────────────────┬───────────────────┐
         ▼                   ▼                                    ▼                   ▼
    [LOCALIZACIÓN]      [METROLOGÍA]                         [FOTOMETRÍA]       [ESPECTROMETRÍA]
      CAT-201 (RL)        CAT-202 (CRLB)                       CAT-204 (Curación)   CAT-250 (Hub SERS)
      CAT-206 (Picasso)   CAT-203 (ISO/GUM uc=6.55 nm)         CAT-209 (LoG/Morph)  CAT-205 (Mapeo SERS)
                                                                                    CAT-207 (AsLS/Voigt)
                                                                                    CAT-208 (SLR/Hot-spots)
```

---

## 8. Referencias Bibliográficas Primarias

1. **Abbe, E.** (1873). *Beiträge zur Theorie des Mikroskops und der mikroskopischen Wahrnehmung*. Archiv für Mikroskopische Anatomie, 9(1), 413–418.
2. **Rayleigh, Lord** (1896). *On the theory of optical images, with special reference to the microscope*. Philosophical Magazine, 42(255), 167–195.
3. **Betzig, E., et al.** (2006). *Imaging Intracellular Fluorescent Proteins at Nanometer Resolution*. Science, 313(5793), 1642–1645. [DOI: 10.1126/science.1127344](https://doi.org/10.1126/science.1127344)
4. **Thompson, R. E., Larson, D. R., & Webb, W. W.** (2002). *Precise nanometer localization analysis for individual fluorescent probes*. Biophysical Journal, 82(5), 2775–2783. [DOI: 10.1016/S0006-3495(02)75618-X](https://doi.org/10.1016/S0006-3495(02)75618-X)
5. **Mortensen, K. I., Churchman, L. S., Spudich, J. A., & Flyvbjerg, H.** (2010). *Optimized localization analysis for single-molecule tracking and super-resolution microscopy*. Nature Methods, 7(5), 377–381. [DOI: 10.1038/nmeth.1447](https://doi.org/10.1038/nmeth.1447)
