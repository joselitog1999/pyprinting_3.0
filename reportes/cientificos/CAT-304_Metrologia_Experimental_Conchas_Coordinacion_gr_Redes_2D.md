# CAT-304 [FIS]: Metrología Experimental de Conchas de Coordinación y Función $g(r)$ en Redes 2D
## Límites de Difracción Óptica ($r_{\text{diff}} \approx 250\text{ nm}$), Detección de Defectos Sub-Red e Invariancia Cinemática

---

**Signatura Bibliotecaria:** `CAT-304`  
**Clasificación Temática:** `[FIS]` Fenomenología Física y Metrología Experimental  
**Pilar:** III — Cristalografía 2D, Espacio Recíproco y Metrología de Desorden  
**Autoría:** José Luis González Peñafiel (INS-UNSAM / CONICET) — PyPrinting 3.0  
**Fecha de Publicación:** Septiembre 2026  
**Estado:** Producción / Consolidado  
**Documentos Vinculados:**  
- [[CAT-303_Derivacion_Matematica_Distribucion_Radial_gr_Correccion_Borde]] (Deducción formal de $\sigma_{\text{rdf}} = \sigma_{\text{peak}}/\sqrt{2}$ y cuadratura)  
- [[CAT-306_Metrologia_Optica_Difraccion_Bragg_y_Perfiles_Redes_2D]] (Análisis de Fourier en espacio recíproco)  
- [[CAT-204_Curacion_Fotometrica_Desacople_MultiGaussiano_Consistencia]] (Desacople de multímeros previo al cómputo de pares)  
- [[CAT-301_Algoritmos_Espacio_Real_KDTree_Asignacion_Monte_Carlo]] (Correspondencia cartesiana con red ideal)  

---

> [!NOTE] Fundamentación Matemática Formal
> La demostración analítica rigurosa del factor de desconvolución $\sigma_{\text{rdf}} = \sigma_{\text{peak}}/\sqrt{2}$ y el algoritmo de normalización de cuadratura 2D provienen de:  
> 👉 **[[CAT-303_Derivacion_Matematica_Distribucion_Radial_gr_Correccion_Borde]]**  
> **Resultado gobernante asumido:** La dispersión radial convoluciona dos fluctuaciones gaussianas independientes. En este reporte se examina cómo interpretar experimentalmente los regímenes de difracción, la presencia de gotas satélites y la física de las conchas de coordinación en el laboratorio.

---

### Resumen Ejecutivo

En la caracterización metrológica de nanoestructuras periódicas obtenidas mediante impresión óptica fototérmica (*optical printing*) o litografía coloidal, la determinación del desorden posicional puede verse afectada por la desalineación angular de la muestra respecto al escáner confocal o por incertidumbres en el origen de fase. 

La **Función de Distribución Radial de Pares $g(r)$** resuelve estas limitaciones al depender exclusivamente de las distancias inter-partículas relativas $\|\mathbf{r}_i - \mathbf{r}_j\|$, conformando una métrica **rigurosamente invariante ante traslaciones globales y rotaciones de muestra**. Este reporte define los tres regímenes físicos de $g(r)$ en microscopía óptica de campo lejano, formaliza el límite de exclusión por difracción instrumental ($r_{\text{diff}} \approx 250\,\text{nm}$), establece la ventana sub-red para la auditoría cuantitativa de partículas satélite y valida el método sobre datos experimentales reales de una red $30 \times 30$ de nanopartículas de oro.

---

## 1. Los Tres Regímenes Físicos de la Curva $g(r)$ en Microscopía Óptica

```
   g(r) ↑
        │                                  Primer Pico de Red (r ≈ a)
        │                                             ▲
        │                                            / \
        │                                           /   \        Segundo Pico (r ≈ √2·a)
        │                                          /     \           ▲
        │                                         /       \         / \            Tercer Pico (r ≈ 2·a)
        │                                        /         \       /   \               ▲
        │               Ventana de Defectos     /           \     /     \             / \
 g(r)=1 ┼- - - - - - - - (Satélites/Dímeros) - / - - - - - - \ - / - - - \ - - - - - / - \ - - - (Gas Ideal)
        │                   ┌──────────┐      /               \_/         \_________/     \____
        │   g(r) = 0        │ g(r) > 0 │     /
        │  (Difracción)     │(Defectos)│    /
        └─────────|─────────┴──────────┴───|──────────────|──────────────|──────────────|─────► r (nm)
                r = 0                   r_diff ≈ 250    r = a         r = √2·a        r = 2·a
```

### 1.1 Régimen 1: Límite de Difracción Óptica Instrumental ($r < r_{\text{diff}} \approx 250\,\text{nm}$)
En microscopía confocal estándar ($\lambda = 532\,\text{nm}$, objetivo Nikon 100x Oil con $\text{NA} = 1.30$), el radio de difracción de Rayleigh es:
$$r_{\text{Rayleigh}} = \frac{0.61 \cdot \lambda}{\text{NA}} \approx \frac{0.61 \cdot 532\,\text{nm}}{1.30} \approx 249.6\,\text{nm} \approx 250\,\text{nm}$$

Dos nanopartículas situadas a una distancia $r < r_{\text{diff}}$ emiten dentro de la misma función de dispersión de punto ($\text{PSF}$), fusionándose en un único lóbulo luminoso. En campo lejano sin técnicas de super-resolución estocástica temporal, **el microscopio no puede resolver dos centroides separados por menos de $250\,\text{nm}$**.  
Por lo tanto, cualquier pico detectado por debajo de $250\,\text{nm}$ en una imagen sin curar es un artefacto espurio de sobre-segmentación (*over-splitting*) inducido por ruido en la cresta de la PSF.  
PyPrinting 3.0 fija **$g(r) \equiv 0$ para $r < r_{\text{diff}}$** como una restricción impuesta por la óptica de Fourier del instrumento.

---

### 1.2 Régimen 2: Ventana Sub-Red de Defectos de Fabricación ($r_{\text{diff}} \le r < a_{\text{nominal}}$)
Para distancias entre $250\,\text{nm}$ y la constante de red nominal $a$, las partículas sí son ópticamente resolubles como entidades individuales.  
En una red teórica perfecta, esta zona estaría vacía ($g(r) = 0$). Sin embargo, **como software de evaluación metrológica, PyPrinting 3.0 no anula artificialmente esta región**. Si el proceso de fotodeposición eyectó gotas secundarias, partículas satélite o dímeros a distancias intermedias (e.g. $300 - 420\,\text{nm}$), el software cuantifica estos eventos mediante el **Índice de Defectos Sub-Red**:
$$\eta_{\text{defectos}} = \frac{N_{\text{pares}}(r_{\text{diff}} \le r < 0.75 \cdot a)}{N_{\text{pares}}^{\text{totales}}}$$

---

### 1.3 Régimen 3: Conchas Cristalinas de Coordinación ($r \ge a$)
- **Primer Pico ($r = a$):** Corresponde a los 4 primeros vecinos inmediatos en $(\pm a, 0)$ y $(0, \pm a)$. La posición del máximo determina el período experimental real ($a_{\text{exp}}$) y su anchura gaussiana $\sigma_{\text{peak}}$ codifica el desorden posicional.
- **Segundo Pico ($r = \sqrt{2}a$):** Vecinos diagonales $(\pm a, \pm a)$.
- **Tercer Pico ($r = 2a$):** Segundos vecinos axiales $(\pm 2a, 0)$ y $(0, \pm 2a)$.
- **Límite Asintótico:** Para grandes distancias ($r \gg a$), la memoria de correlación de red se amortigua y la función converge asintóticamente al continuo del gas ideal: $\lim_{r \to \infty} g(r) = 1.0$.

---

## 2. Validación Experimental en Muestra Confocal Real (`reserva/30x30_500.tiff`)

Se aplicó el módulo de distribución radial sobre una red cuadrada de nanopartículas de oro de $100\,\text{nm}$ sintetizada por trampa óptica fototérmica ($30 \times 30$ sitios nominales, $a = 500\,\text{nm}$):

```text
=== Resultados en reserva/30x30_500.tiff ===
Partículas en ROI: 838 de 900 sitios (Vacancias: 7.1%)
Límite de difracción aplicado r_diff: 250.0 nm ➔ g(r < 250 nm) = 0.0
Artefactos sub-difracción detectados: 13 pares (sobre-detección óptica por ruido en PSF)
Defectos sub-red (250 nm ≤ r < 375 nm): 2.4% de pares totales (partículas fuera de nodo)
Primer pico detectado r_pk: 481.25 nm (Período nominal: 500 nm)
Amplitud del pico g(r_pk): 1.99
Ancho de pico medido σ_peak: 93.7 nm
Desorden desconvolucionado σ_rdf = σ_peak / √2: 66.3 nm
```

### Diagnóstico Físico del Valor Medido:
1. **Artefactos Sub-Difracción:** Se identificaron 13 pares espurios en $140 - 240\,\text{nm}$ producto de ruido electrónico en la cámara confocal. Al aplicar el corte físico $r_{\text{diff}}$, se previene que contaminen la estadística del cristal.
2. **Defectos Sub-Red ($2.4\%$):** El $2.4\%$ de pares entre $250\,\text{nm}$ y $375\,\text{nm}$ revela partículas coloidales físicas reales que cayeron fuera de pozo durante la deposición por láser pulsado.
3. **Contracción de Red ($a_{\text{exp}} = 481.25\,\text{nm}$):** El desplazamiento del centroide respecto a los $500\,\text{nm}$ programados evidencia una contracción del sustrato de polímero por fotopolimerización o histéresis de la platina piezoeléctrica.
4. **Ensanchamiento por Deriva Térmica:** La dispersión radial aparente $\sigma_{\text{rdf}} = 66.3\,\text{nm}$ resulta superior a la estimada en espacio recíproco ($\sigma_{\text{dw}} \approx 15.6\,\text{nm}$). Esto se debe a que el escaneo confocal tardó $\approx 45\,\text{segundos}$, acumulando una deriva lenta que dilata los ejes; al promediar todas las orientaciones en $g(r)$, la deriva térmica se proyecta isotrópicamente ensanchando la campana de pares.

---

## 3. Matriz de Triple Redundancia Metrológica

PyPrinting 3.0 integra tres canales metrológicos independientes para evaluar el desorden:

| Propiedad Metrológica | 1. Bounded KDTree (`CAT-301`) | 2. NUFFT 2D + Debye-Waller (`CAT-305`) | 3. Radial $g(r)$ (`CAT-304`) |
| :--- | :--- | :--- | :--- |
| **Espacio de Evaluación** | Real (Coordenadas cartesianas) | Recíproco (Momentos $\mathbf{q}$) | Real (Distancias relativas) |
| **¿Requiere Red Ideal?** | SÍ (Malla nominal $\mathbf{R}_{mn}$) | NO (Espectro de difracción) | NO (Completamente ciego) |
| **Sensibilidad a Rotación $\theta$** | ALTA (Sesga $\sigma_x, \sigma_y$) | MEDIA (Rotación de picos) | **NULA ($100\%$ Invariante)** |
| **Sensibilidad a Vacancias** | Asignación nula | Factor coherente $(1-p)^2$ | Despreciable en conchas |
| **Parámetro Extraído** | $\sigma_x, \sigma_y, \sigma_{\text{pos}}$ | $\sigma_{\text{dw}}, \sigma_{\text{analit}}$ | $\sigma_{\text{rdf}} = \sigma_{\text{peak}}/\sqrt{2}$ |
| **Diagnóstico Específico** | Mapa de residuos espaciales | Longitud de coherencia $\xi$ | Detección de satélites y multímeros |

---

## 4. Guía de Buenas Prácticas Metrológicas

1. **Uso Primario ante Muestras Rotadas:** Cuando una red nanofabricada se coloca en el portamuestras con una inclinación angular desconocida $\theta$ respecto a los ejes de la platina, **$g(r)$ debe ser la métrica primaria en espacio real**, al ser la única totalmente insensible a la rotación.
2. **Inspección de Contracción / Expansión de Red:** Si el primer pico se desplaza en $|r_{\text{pk}} - a| > 15\,\text{nm}$, ajustar el valor nominal en el control de software antes de ejecutar análisis de residuos en espacio real.
3. **Curación Fotométrica Previa:** Si existen agregados o multímeros, ejecutar la curación en la Pestaña 1 (desacoplando spots con $\sigma = \sigma_{\text{psf}}$) antes de computar $g(r)$ para evitar que las colas de emisión engrosen artificialmente $\sigma_{\text{peak}}$.
