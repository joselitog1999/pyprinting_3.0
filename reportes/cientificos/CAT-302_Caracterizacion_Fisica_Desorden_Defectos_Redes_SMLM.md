# CAT-302 [FIS]: Caracterización Física de Defectos y Desorden Reticular en Nanoestructuras SMLM
## Mecanismos de Falla en Impresión Óptica, Topología de Defectos, Parámetros de Orden ($\psi_4, \psi_6$) e Impacto en Plasmónica

---

**Signatura Bibliotecaria:** `CAT-302`  
**Clasificación Temática:** `[FIS]` Fenomenología Física y Metrología Experimental  
**Pilar:** III — Cristalografía 2D, Espacio Recíproco y Metrología de Desorden  
**Autoría:** José Luis González Peñafiel (INS-UNSAM / CONICET) — PyPrinting 3.0  
**Fecha de Publicación:** Septiembre 2026  
**Estado:** Producción / Consolidado  
**Documentos Vinculados:**  
- [[CAT-301_Algoritmos_Espacio_Real_KDTree_Asignacion_Monte_Carlo]] (Algoritmos de correspondencia KDTree y simulación Monte Carlo)  
- [[CAT-306_Metrologia_Optica_Difraccion_Bragg_y_Perfiles_Redes_2D]] (Manifestación espectral de defectos en difracción de Fourier)  
- [[CAT-309_Teoria_Paracristal_Hosemann_Perdida_Orden_2D]] (Pérdida de orden de largo alcance y teoría de Hosemann)  
- [[CAT-103_Control_Lazo_Cerrado_Fototermico_y_Sintesis_Dimeros]] (Control de procesos de deposición óptica y parada)  

---

> [!NOTE] Fundamentación Algorítmica y Computacional
> Los métodos numéricos de emparejamiento reticular espacial (Bounded KDTree) y la formulación estocástica de ensambles provienen de:  
> 👉 **[[CAT-301_Algoritmos_Espacio_Real_KDTree_Asignacion_Monte_Carlo]]**  
> **Resultado gobernante asumido:** Las posiciones observadas $\mathbf{r}_j$ se desacoplan en nodos ideales $\mathbf{R}_{mn}$ y residuos $\mathbf{\delta}_j$ libres de sesgo de frontera. A partir de esta base geométrica, este reporte analiza la física del estado sólido subyacente, la clasificación topológica de defectos y las consecuencias electromagnéticas en metasuperficies ópticas.

---

### Resumen Ejecutivo

En la nanofabricación óptica basada en trampa fototérmica (*optical printing*) o litografía de super-resolución (SMLM), las redes 2D sintetizadas se desvían del cristal perfecto debido a fenómenos termomecánicos, hidrodinámicos y estocásticos intrínsecos a la escala nanométrica. 

Este reporte clasifica y modela físicamente la génesis de imperfecciones en redes bidimensionales periódicas: desde defectos puntuales (vacancias generadas por desorción térmica o falta de captura coloidal) y defectos topológicos (pares de disclinaciones 5-7 en teselaciones de Voronoi), hasta perturbaciones elásticas globales (cizalle por deriva uniaxial de platina piezoeléctrica). Se formalizan los **parámetros de orden orientacional hexático ($\psi_6$) y tetrático ($\psi_4$)**, se analiza el decaimiento de las resonancias plasmónicas de retículo (*Lattice Plasmon Resonances*) frente al desorden $\sigma_{\text{pos}}$, y se fijan los criterios de aceptación y rechazo metrológico para dispositivos fotónicos en **PyPrinting 3.0**.

---

## 1. Génesis Física de Defectos en Impresión Óptica Fototérmica

Durante el atrapamiento y fijación de nanopartículas metálicas (Au, Ag de $d \approx 60 - 100\,\text{nm}$) asistido por gradientes ópticos y fuerzas termoforéticas, se manifiestan tres mecanismos físicos de perturbación:

```
                  MECANISMOS FÍSICOS DE DESORDEN EN NANO-IMPRESIÓN
                  
       (A) Movimiento Browniano Residual:          (B) Micro-Cavidades Térmicas:
       F_gradiente vs Fluctuación Térmica          Sobrecalentamiento local
       
              Láser Focalizado                            Vapor / Marangoni
                  \     /                                    .~~~~~.
                   \   /                                    ( Gotícula )
                    \v/                                      `~~~~~'
                 o (Au NP)                                  o   o (Eyección)
              ~~~~~~~~~~~~~~~ cubreobjetos               ~~~~~~~~~~~~~~~ cubreobjetos
              sigma_browniano ~ sqrt(k_B T / k_trampa)   Genera Vacancias o Satélites
```

1. **Movimiento Browniano Residual en la Trampa Óptica:**  
   Antes de hacer contacto con la superficie silanizada del sustrato, la partícula fluctúa dentro del pozo de potencial óptico tridimensional con una varianza térmica gobernada por el teorema de equipartición:
   $$\frac{1}{2} k_{\text{trampa}} \langle \delta x^2 \rangle = \frac{1}{2} k_B T \implies \sigma_{\text{browniano}} = \sqrt{\frac{k_B T}{k_{\text{trampa}}}}$$
   Para rigideces típicas de trampa $k_{\text{trampa}} \approx 0.5 - 2.0\,\text{pN/nm}$ a $T = 300\,\text{K}$, el límite inferior fundamental de desorden térmico es $\sigma_{\text{browniano}} \approx 1.5 - 3.0\,\text{nm}$.
2. **Fuerzas Termoforéticas y Flujos de Marangoni:**  
   La disipación óptica genera gradientes de temperatura locales ($\Delta T \sim 10 - 50\,\text{K}$) que inducen micro-corrientes convectivas en la interfase líquido-sustrato, desplazando lateralmente la nanopartícula durante el aterrizaje.
3. **Deriva Termomecánica Uniaxial de la Platina:**  
   Durante escrituras prolongadas (e.g. mallas de $30 \times 30$ sitios con tiempos de impresión de $\sim 10 - 30\,\text{minutos}$), la dilatación del estativo introduce una deformación homogénea elástica sobre el parámetro de red:
   $$\mathbf{R}_{mn}' = \mathbf{R}_{mn} + \mathbf{v}_{\text{drift}} \cdot t_{mn}$$

---

## 2. Tipología y Clasificación Topológica de Imperfecciones

Siguiendo la teoría de Kosterlitz-Thouless-Halperin-Nelson-Young (KTHNY) para transiciones de fase en sistemas 2D, las imperfecciones de red se clasifican en:

```
  (A) Vacancia Puntual          (B) Par 5-7 (Dislocación)         (C) Deformación Uniaxial
      o   o   o   o                 o   o   o   o   o                 o     o     o
      o   .   o   o                 o   o \ / o   o                   o     o     o
      o   o   o   o                 o   o / \ o   o                   o     o     o
  c_mn = 0 (Falta átomo)         Disclinación (Heptágono-Pentágono)   a_x != a_y (Cizalle)
```

| Tipo de Defecto | Firma Geométrica | Métrica de Detección en PyPrinting 3.0 | Impacto Óptico |
| :--- | :--- | :--- | :--- |
| **Vacancia Puntual** | Sitio nominal no ocupado ($c_{mn} = 0$) | Asignación nula en Bounded KDTree | Atenuación del factor de Bragg por $(1-p)^2$ |
| **Impureza Intersticial** | Nanopartícula fuera de nodo nominal | Partícula huérfana ($d > r_{\text{cut}}$) | Incremento del fondo difuso $S_{\text{difuso}}$ |
| **Multímero / Agregado** | Coalescencia de 2 o más partículas | Huella fotométrica $V > 1.5 V_0$ | Pérdida de simetría y despolarización |
| **Dislocación de Borde** | Fila extra de plano cristalográfico | Teselación Voronoi con vecinos $N_c \neq 4$ | Rotura de fase y ensanchamiento de Bragg |
| **Deriva Elástica** | Deformación afín del cristal | Tensor de distorsión $\epsilon_{xx}, \epsilon_{yy}, \epsilon_{xy}$ | Desplazamiento asimétrico de picos recíprocos |

---

## 3. Cuantificación del Orden Orientacional: Parámetros $\psi_4$ y $\psi_6$

Para distinguir entre desorden puramente traslacional (donde los enlaces conservan su orientación angular) y desorden rotacional de mosaico (fase hexática o desorientación de micro-granos), se computa el **Parámetro de Orden Orientacional Local**:

$$\psi_n(\mathbf{r}_j) = \frac{1}{N_j} \sum_{k=1}^{N_j} e^{i n \theta_{jk}}$$

donde:
- $n = 4$ para redes cuadradas, $n = 6$ para redes hexagonales / triangulares.
- $N_j$ es el número de primeros vecinos inmediatos de la partícula $j$ (obtenidos mediante triangulación de Delaunay o corte radial $r \le 1.25 a$).
- $\theta_{jk}$ es el ángulo del vector de enlace $\mathbf{r}_k - \mathbf{r}_j$ respecto al eje horizontal cartesiano $X$.

### Parámetro Global del Cristal:
$$\Psi_n = \left| \frac{1}{M} \sum_{j=1}^M \psi_n(\mathbf{r}_j) \right| \in [0, 1]$$

- **$\Psi_n = 1.0$:** Red perfectamente orientada sin distorsión angular.
- **$0.7 \le \Psi_n < 0.95$:** Cristal con desorden térmico isotrópico moderado.
- **$\Psi_n < 0.5$:** Pérdida severa de alineación angular (transición vítrea o líquido 2D).

---

## 4. Impacto Electromagnético: Resonancias Plasmónicas de Retículo (SLRs)

En arreglos periódicos de nanopartículas metálicas, la difracción rasante en el plano de la muestra (anomalías de Wood) interactúa fuertemente con la resonancia de plasmón superficial localizado (LSPR) de cada elemento, generando **Modos Colectivos Plasmónicos de Retículo (Surface Lattice Resonances - SLRs)**.

### Ecuación de Acoplamiento y Factor de Calidad ($Q$):
El ancho de línea espectral $\Gamma_{\text{SLR}}$ y el factor de calidad $Q = \omega_0 / \Gamma_{\text{SLR}}$ de la resonancia colectiva dependen directamente de la coherencia de fase entre emisores:

$$\Gamma_{\text{SLR}}(\sigma_{\text{pos}}) = \Gamma_{\text{rad}} \cdot (1 - p) \cdot e^{-\left(\frac{2\pi}{a}\right)^2 \sigma_{\text{pos}}^2} + \Gamma_{\text{incoh}} \left[ 1 - (1-p)e^{-\left(\frac{2\pi}{a}\right)^2 \sigma_{\text{pos}}^2} \right] + \Gamma_{\text{ohmico}}$$

```
  FACTOR DE CALIDAD Q DE RESONANCIA COLECTIVA vs DESORDEN
  
  Q ^
    |  * Cristal Ideal (Q_max ~ 150)
    |   \
    |    \
    |     \  Régimen Aceptable Fotónica (Q > 80)
    |      \
    |-------*---------------------------------- Umbral Crítico Metrológico
    |        \
    |         \   Régimen Ruptura de Resonancia (LSPR aislada, Q ~ 10)
    |          *--------------------
    +-------------------------------------------> sigma_pos / a
    0         0.05       0.10       0.15
```

1. **Régimen de Coherencia Fuerte ($\sigma_{\text{pos}} / a \le 0.05$):**  
   Las pérdidas por radiación difusa fuera de plano son mínimas. El factor de calidad se mantiene elevado ($Q > 80$), permitiendo aplicaciones de sensado biosensible ultra-preciso y emisión láser DFB plasmónica.
2. **Régimen de Desacoplamiento ($\sigma_{\text{pos}} / a > 0.12$):**  
   La interferencia destructiva de Bragg se destruye. Los modos colectivos colapsan, y el sistema responde como una colección incoherente de nanopartículas aisladas con resonancia ancha ($Q \sim 8 - 15$).

---

## 5. Criterios Metrológicos de Aceptación / Rechazo en PyPrinting 3.0

Para el control de calidad automatizado en la suite de nanofabricación, se establecen los siguientes umbrales físicos rigurosos:

| Métrica | Nivel Excelente (Grado Cuántico) | Nivel Aceptable (Grado Fotónico) | Nivel Rechazado (Defectuoso) |
| :--- | :---: | :---: | :---: |
| **Desorden Relativo $\sigma_{\text{pos}} / a$** | $\le 3.5\%$ ($\sigma \le 17.5\,\text{nm}$ para $a=500\,\text{nm}$) | $3.5\% < \sigma_{\text{pos}}/a \le 8.0\%$ | $> 8.0\%$ ($\sigma > 40\,\text{nm}$) |
| **Fracción de Vacancias $p$** | $< 2.0\%$ | $2.0\% \le p \le 8.0\%$ | $> 8.0\%$ |
| **Fracción de Multímeros** | $< 1.0\%$ | $1.0\% \le f_{\text{multi}} \le 4.0\%$ | $> 4.0\%$ |
| **Orden Tetrático $\Psi_4$** | $\ge 0.92$ | $0.80 \le \Psi_4 < 0.92$ | $< 0.80$ |
| **Anisotropía de Ejes $|\sigma_x - \sigma_y|$** | $\le 2.0\,\text{nm}$ | $2.0\,\text{nm} < |\Delta \sigma| \le 6.0\,\text{nm}$ | $> 6.0\,\text{nm}$ (Deriva severa) |

---

## 6. Conclusiones

1. **Física Multiescala:** Las imperfecciones en redes nanofabricadas no son ruido numérico abstracto; cada defecto posee una firma física identificable y cuantificable en el espacio real y recíproco.
2. **Monitoreo en Tiempo Real:** El software PyPrinting 3.0 integra el cálculo de $\Psi_4 / \Psi_6$ y la clasificación de vacancias para permitir al operador rechazar o aceptar de forma inmediata una muestra antes de transferirla a experimentos de fotoluminiscencia o espectroscopía Raman.
