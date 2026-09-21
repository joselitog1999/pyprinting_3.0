# CAT-208: Electrodinámica de Nanocavidades Plasmónicas, Resonancia SLR y Espectroscopía SERS Cuantitativa
## Acoplamiento Capacitivo en Nanogaps, Resonancias de Red Superficial (SLR), Cuantificación de Factores de Realce |E/E0|^4 y Mapeo Hiperespectral 3D

---

**Signatura Bibliotecaria:** `CAT-208`  
**Clasificación Temática:** `[FIS]` / `[MAT]` Nanofotónica, Plasmónica de Superficie y Espectroscopía Vibracional Cuantitativa  
**Pilar:** Pilar II — Super-Resolución Óptica, Detección Sub-píxel y Espectrometría  
**Autoría:** José Luis González Peñafiel (*Becario Doctoral CONICET*), Comité Científico PyPrinting 3.0  
**Fecha de Publicación:** Septiembre 2026  
**Estado:** Producción / Consolidado  
**Módulos Asociados:** `raman_analyzer.py`, `core/raman_engine.py`, `grid_generator.py`, `analysis/multi_spectrum_widget.py`  
**Documentos Vinculados:**  
- [[CAT-205_Mapeo_Hiperespectral_SERS_Confocal_Automatizado]] (Mapeo hiperespectral confocal)  
- [[CAT-207_Quimiometria_Procesamiento_Espectral_AsLS_Voigt_Calibracion]] (Procesamiento quimiométrico y perfiles Voigt)  
- [[CAT-109_Electrodinamica_Fuerzas_Opticas_y_Termoplasmonica_Printing]] (Electrodinámica y calentamiento Joule)  
- [[CAT-306_Metrologia_Optica_Difraccion_Bragg_y_Perfiles_Redes_2D]] (Difracción de Bragg en redes planas)  

---

## 1. Resumen Ejecutivo

La espectroscopía Raman amplificada por superficie (SERS) permite la detección ultrasensible de analitos químicos hasta el límite de molécula única. Esta ganancia colosal de señal no es homogénea en el espacio, sino que surge de confinamientos nanométricos extremos de campo electromagnético denominados **puntos calientes (hot-spots)**. En PyPrinting 3.0, la síntesis óptica controlada de dímeros de oro/plata con espaciados sub-5 nm y la fabricación de redes periódicas bidimensionales permiten explotar tanto el acoplamiento capacitivo de campo cercano como las **Resonancias de Red Superficial (Surface Lattice Resonances - SLR)**.

Este reporte formaliza la electrodinámica clásica de nanocavidades plasmónicas acopladas, deduciendo la regla de escalado $|E_{\text{loc}}/E_0|^4$ para el factor de realce electromagnético. Se modela la hibridación plasmónica en nanodímeros, se deduce la condición analítica de Bragg para la excitación de modos SLR colectivos en redes 2D con estrechamiento del ancho de línea espectral ($Q > 100$), y se definen los protocolos metrológicos para calcular el **Factor de Realce Analítico (AEF)** y el **Factor de Realce SERS Sustrato-Específico (EF)** sobre cubos de datos hiperespectrales $\mathcal{H}(X, Y, \lambda)$.

---

## 2. El Mecanismo Electromagnético SERS y la Ley $|E/E_0|^4$

La potencia total de dispersión Raman inelástica emitida por una molécula localizada en la posición $\mathbf{r}_0$ a una frecuencia Stokes $\omega_S = \omega_L - \Omega$ es:

$$P_{\text{SERS}}(\omega_S) \propto \sigma_{\text{Raman}}^{\text{free}} \, |\mathbf{E}_{\text{loc}}(\mathbf{r}_0, \omega_L)|^2 \, |\mathbf{E}_{\text{loc}}(\mathbf{r}_0, \omega_S)|^2$$

### 2.1 Deducción del Doble Realce
1. **Realce de Excitación**: La nanopartícula plasmónica actúa como una nanoantena óptica receptora, concentrando el campo incidente plano $E_0(\omega_L)$ en la nanocavidad:
   $$G_{\text{exc}}(\omega_L) = \frac{|\mathbf{E}_{\text{loc}}(\mathbf{r}_0, \omega_L)|^2}{|E_0(\omega_L)|^2}$$
2. **Realce de Emisión**: La molécula polarizada induce un dipolo oscilante $\mathbf{p}(\omega_S) = \hat{\alpha} \cdot \mathbf{E}_{\text{loc}}(\omega_L)$. A su vez, la presencia de la superficie metálica incrementa la densidad local de estados fotónicos (LDOS / Efecto Purcell), aumentando la tasa de emisión radiativa hacia el campo lejano:
   $$G_{\text{em}}(\omega_S) = \frac{|\mathbf{E}_{\text{loc}}(\mathbf{r}_0, \omega_S)|^2}{|E_0(\omega_S)|^2}$$

Dado que el corrimiento Raman típico $\Omega \sim 500 - 1600\ \text{cm}^{-1}$ es pequeño en comparación con el ancho espectral de la resonancia plasmónica ($\,\hbar\Gamma_{\text{LSPR}} \sim 200 - 400\ \text{meV}$), podemos aproximar $\omega_L \approx \omega_S$:

$$EF_{\text{EM}}(\mathbf{r}_0) \approx \left| \frac{\mathbf{E}_{\text{loc}}(\mathbf{r}_0)}{\mathbf{E}_0} \right|^4$$

Si el campo eléctrico local se intensifica por un factor modesto de $30\times$ en un nanogap plasmónico, el factor de realce SERS alcanza:
$$EF_{\text{EM}} \approx 30^4 = 8.1 \times 10^5$$
alcanzando hasta $10^8 - 10^{10}$ en nanouniones de dímeros con gaps sub-2 nm.

---

## 3. Acoplamiento Capacitivo en Nanodímeros Plasmónicos

Para dos nanopartículas esféricas de radio $R$ separadas por un nanogap de ancho $g \ll R$, bajo polarización paralela al eje del dímero, la acumulación de cargas de signo opuesto a través del gap genera una fuerza restauradora reducida y un desplazamiento al rojo de la resonancia plasmónica (hibridación plasmónica):

```
       Nanopartícula 1             Nanopartícula 2
         (Radio R)                   (Radio R)
        /---------\     Gap (g)     /---------\
       |   (+) (-) | <-----------> | (+) (-)   |
        \---------/                 \---------/
            ▲                           ▲
            └─────── E_0 (Polariz.) ────┘
                         |E_loc| >> |E_0| en el Gap
```

En el límite cuasi-estático, la amplificación del campo eléctrico en el centro exacto del nanogap escala inversamente con el tamaño de la separación:
$$\frac{E_{\text{loc}}}{E_0} \approx \frac{R}{g}$$
$$EF_{\text{dimero}} \sim \left( \frac{R}{g} \right)^4$$

Para $R = 40\ \text{nm}$ y $g = 2\ \text{nm}$:
$$EF_{\text{dimero}} \sim \left( \frac{40}{2} \right)^4 = 20^4 = 1.6 \times 10^5$$

---

## 4. Resonancias de Red Superficial (SLR) en Arreglos Periódicos 2D

Cuando las nanopartículas metálicas no están aisladas sino dispuestas en una red periódica 2D con constante de red $a_x, a_y$ (diseñada mediante `grid_generator.py`), ocurre un fenómeno de interferencia constructiva de largo alcance: **las Resonancias de Red Superficial (SLR)**.

### 4.1 Condición de Acoplamiento Coherente de Difracción
Una anomalía de Rayleigh en el plano ocurre cuando un orden difractado de Bragg viaja rasante a lo largo de la superficie del sustrato (vector de onda en plano $k_{\parallel} = k_{\text{sustrato}} = n_{\text{sust}} k_0$):

$$\mathbf{k}_{\parallel} = \mathbf{k}_0 \sin\theta \pm m \mathbf{G}_x \pm n \mathbf{G}_y, \quad \mathbf{G}_x = \frac{2\pi}{a_x}\hat{\mathbf{x}}, \quad \mathbf{G}_y = \frac{2\pi}{a_y}\hat{\mathbf{y}}$$

Para incidencia normal ($\theta = 0$) en una red cuadrada $a_x = a_y = a$:
$$\lambda_{\text{SLR}}^{(m,n)} = \frac{n_{\text{sust}} \, a}{\sqrt{m^2 + n^2}}$$

### 4.2 Supresión de Pérdidas Radiativas y Estrechamiento de Línea
La interferencia destructiva entre las ondas radiadas al campo lejano cancela el amortiguamiento radiativo de los dipolos plasmónicos individuales. Como consecuencia:
- El ancho de línea FWHM se reduce de $\sim 80\ \text{nm}$ (plasmón localizado LSPR individual) a $\le 3 - 5\ \text{nm}$ (modo SLR coherente).
- El factor de calidad óptico se multiplica drásticamente: $Q_{\text{SLR}} = \lambda / \Delta\lambda > 100$.
- Los campos locales se extienden homogéneamente sobre miles de celdas unitarias, permitiendo reproducibilidad macroscópica en mediciones SERS sin fluctuaciones erráticas de hot-spots individuales.

---

## 5. Cuantificación Rigurosa del Factor de Realce SERS

En `core/raman_engine.py` y `analysis/raman_analyzer.py`, la cuantificación de SERS rechaza factores empíricos arbitrarios y exige el cálculo del **Factor de Realce SERS Sustrato-Específico (EF)**:

$$EF = \frac{I_{\text{SERS}} / N_{\text{SERS}}}{I_{\text{Raman}} / N_{\text{Raman}}}$$

donde:
1. $I_{\text{SERS}}$ e $I_{\text{Raman}}$ son las intensidades integradas de una banda diagnóstico específica (ej. modo anillo bencénico de 4-MBA a $1078\ \text{cm}^{-1}$ o rodamina 6G a $1509\ \text{cm}^{-1}$).
2. $N_{\text{Raman}}$ es el número de moléculas en el volumen focal del solvente en ausencia de nanopartículas:
   $$N_{\text{Raman}} = C_{\text{bulk}} \cdot V_{\text{focal}} \cdot N_A$$
   con volumen focal confocal gaussiano $V_{\text{focal}} = \pi^{3/2} w_0^2 z_R$.
3. $N_{\text{SERS}}$ es el número de moléculas adsorbidas en la superficie metálica dentro del foco:
   $$N_{\text{SERS}} = \rho_{\text{monocapa}} \cdot A_{\text{metálica}} \cdot f_{\text{foco}}$$
   con densidad de empaquetamiento de monocapa clásica para tioles $\rho_{\text{monocapa}} \approx 0.5\ \text{nm}^{-2}$ ($5 \times 10^{14}\ \text{moléculas/cm}^2$).

---

## 6. Referencias Bibliográficas Primarias

1. **Le Ru, E. C., & Etchegoin, P. G.** (2008). *Principles of Surface-Enhanced Raman Spectroscopy*. Elsevier. [ISBN: 978-0-444-53385-2]
2. **Kravets, V. G., Kabashin, A. V., Barnes, W. L., & Grigorenko, A. N.** (2018). *Plasmonic Surface Lattice Resonances: A Review of Properties and Applications*. Chemical Reviews, 118(12), 5912–5951. [DOI: 10.1021/acs.chemrev.8b00243](https://doi.org/10.1021/acs.chemrev.8b00243)
3. **Nordlander, P., Oubre, C., Prodan, E., Li, K., & Stockman, M. I.** (2004). *Plasmon Hybridization in Nanoparticle Dimers*. Nano Letters, 4(5), 899–903. [DOI: 10.1021/nl049681c](https://doi.org/10.1021/nl049681c)
4. **Schatz, G. C., & Van Duyne, R. P.** (2002). *Electromagnetic mechanism of surface-enhanced spectroscopy*. Handbook of Vibrational Spectroscopy.
