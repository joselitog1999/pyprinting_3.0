# CAT-306 [FIS]: Metrología Óptica de Difracción de Bragg y Perfiles de Línea en Redes 2D
## Anatomía de Picos en el Plano Focal Posterior (BFP), Ancho Radial vs Transversal y Matriz Diagnóstica

---

**Signatura Bibliotecaria:** `CAT-306`  
**Clasificación Temática:** `[FIS]` Fenomenología Física y Metrología Experimental  
**Pilar:** III — Cristalografía 2D, Espacio Recíproco y Metrología de Desorden  
**Autoría:** José Luis González Peñafiel (INS-UNSAM / CONICET) — PyPrinting 3.0  
**Fecha de Publicación:** Septiembre 2026  
**Estado:** Producción / Consolidado  
**Documentos Vinculados:**  
- [[CAT-305_Derivacion_Matematica_Factor_Estructura_Debye_Waller]] (Deducción formal de $S(\mathbf{q})$, von Laue y vacancias $(1-p)^2$)  
- [[CAT-307_Computacion_NUFFT_Factor_Estructura_Optimizacion_BLAS]] (Cómputo numérico de alta velocidad en espacio recíproco)  
- [[CAT-308_Metrologia_Analitica_Directa_Picos_Bragg_Fourier_2D]] (Inversión cerrada del cociente $H_2/H_1$)  
- [[CAT-309_Teoria_Paracristal_Hosemann_Perdida_Orden_2D]] (Discriminación de desorden Tipo I vs Tipo II)  

---

> [!NOTE] Fundamentación Matemática Formal
> Las deducciones analíticas rigurosas del factor de estructura continuo, la atenuación exponencial de Debye-Waller y la influencia de las vacancias $(1-p)^2$ provienen de:  
> 👉 **[[CAT-305_Derivacion_Matematica_Factor_Estructura_Debye_Waller]]**  
> **Resultado gobernante asumido:** La intensidad espectral se descompone en $I(\mathbf{q}) = I_{\text{Bragg}}(\mathbf{q}) + I_{\text{difuso}}(\mathbf{q})$. En este reporte se analiza la manifestación óptica experimental de estos términos en el plano focal posterior (BFP), la morfología de los cortes de línea y el protocolo de diagnóstico metrológico en laboratorio.

---

### Resumen Ejecutivo

En la caracterización óptica de redes periódicas de nanopartículas plasmónicas o dieléctricas, el espectro de difracción en el espacio de Fourier ($\mathbf{q} \in \mathbb{R}^2$) reproduce fielmente la distribución de intensidad en el plano focal posterior (*Back Focal Plane*, BFP) del objetivo de inmersión.

Este reporte formaliza la anatomía óptica de los picos de difracción de Bragg para redes 2D. Se detalla la descomposición de los perfiles de línea en sus componentes ortogonales: el **ensanchamiento radial ($\Delta q_\parallel$)**, que cuantifica la longitud de coherencia traslacional finita ($\xi$), y el **ensanchamiento transversal en arco ($\Delta q_\perp$)**, que codifica el desorden orientacional o estructura de mosaico angular. Asimismo, se expone el tratamiento experimental de la fuga de frecuencia cero (DC bleed), el deslumbrado espectral por borde de ventana y se consolida la **Matriz Diagnóstica de Toma de Decisiones** implementada en la suite **PyPrinting 3.0**.

---

## 1. Anatomía Óptica del Espacio Recíproco 2D

El plano de difracción generado por la transformada continua de Fourier (NUFFT-1) descompone simultáneamente todas las escalas espaciales de la muestra:

```
                       PLANO DE DIFRACCIÓN RECÍPROCO 2D (BFP)
                       
              q_y ^
                  |           * H_02 (0, 2q_1)  [Armónico Axial]
                  |
                  |         * H_01 (0, q_1)     * H_11 (q_1, q_1)  [Diagonal]
                  |          \                 /
                  |           \  Ancho Transversal Δq_⊥ (Mosaico)
                  |            \             /
                  |             \           /
                  |         H_00 * (0,0)  * H_10 (q_1, 0)
                  +------------------------------------------> q_x
                                 |        |
                                 |<------>|
                              Posición Radial |q_1| = 2pi / a
                              Ancho Radial Δq_∥ (Coherencia ξ)
```

### Correspondencia de Rasgos Espectrales:
1. **Pico Central DC ($\mathbf{q} = \mathbf{0}$):**  
   Intensidad proporcional al cuadrado del número de partículas presentes ($I_0 \propto M^2$). Su ancho espacial refleja la envolvente de la ventana de escaneo ($L_x \times L_y$).
2. **Picos Axiales Fundamentales ($\mathbf{G}_{10}, \mathbf{G}_{01}$):**  
   Ubicados a la distancia radial $q_1 = \frac{2\pi}{a}$. La altura neta sobre el fondo $H_1$ cuantifica el factor de Debye-Waller combinado con la fracción de vacancias $(1-p)^2$.
3. **Picos Diagonales ($\mathbf{G}_{11}$):**  
   Ubicados a $q_{\text{diag}} = \sqrt{2} q_1 = \sqrt{2} \frac{2\pi}{a}$. Evalúan la ortogonalidad estricta entre los ejes $X$ e $Y$ y la coherencia de fase bidimensional.
4. **Picos Armónicos de Segundo Orden ($\mathbf{G}_{20}, \mathbf{G}_{02}$):**  
   Ubicados a $q_2 = 2 q_1 = \frac{4\pi}{a}$. Su atenuación respecto al primer orden ($H_2 / H_1$) permite la inversión determinista de $\sigma_{\text{pos}}$ ([[CAT-308_Metrologia_Analitica_Directa_Picos_Bragg_Fourier_2D]]).
5. **Meseta Difusa Subyacente (Diffuse Scattering):**  
   Fondo continuo e incoherente que revela la energía fotónica dispersada por fluctuaciones térmicas locales y vacancias puntuales.

---

## 2. Morfología y Descomposición de Perfiles de Línea

Para cualquier reflexión de Bragg centrada en $\mathbf{G}_{hk}$, definimos un sistema de coordenadas curvilíneo local centrado en el pico:
- **Dirección Radial / Longitudinal ($\hat{\mathbf{q}}_\parallel$):** Paralela al vector recíproco $\mathbf{G}_{hk}$.
- **Dirección Transversal / Azimutal ($\hat{\mathbf{q}}_\perp$):** Perpendicular al vector $\mathbf{G}_{hk}$ (a lo largo del arco circular de radio constante $|\mathbf{G}|$).

```
  CORTE RADIAL Δq_∥ (Coherencia):          CORTE TRANSVERSAL Δq_⊥ (Mosaico):
  
  I(q_∥) ^                                 I(q_⊥) ^
         |        /\                              |       /----\
         |       /  \                             |      /      \
         |      /    \                            |     /        \
         +-----*------*------> q_∥                +----*----------*----> q_⊥
               |<---->|                                |<-------->|
                Δq_∥ = 2pi / ξ                          Δq_⊥ = |G| · Δθ
```

---

### 2.1 Ancho Radial ($\Delta q_\parallel$) y Longitud de Coherencia Espacial ($\xi$)
El perfil de intensidad a lo largo del radio vector experimenta un ensanchamiento gobernado por el tamaño finito del dominio cristalino y la correlación traslacional:

$$\Delta q_\parallel \approx \frac{2\pi}{\xi}$$

- **Límite de Tamaño Finito (Scherrer 2D):**  
  En un cristal perfecto sin desorden de tamaño finito $L_x$:
  $$\Delta q_{\text{Scherrer}} \approx \frac{2\pi \cdot 0.886}{L_x}$$
- **Longitud de Coherencia Traslacional ($\xi$):**  
  Si la red presenta desorden acumulativo o fronteras de grano, $\Delta q_\parallel$ se ensancha, permitiendo extraer la distancia máxima sobre la cual la red mantiene memoria de fase:
  $$\xi = \frac{2\pi}{\sqrt{\Delta q_\parallel^2 - \Delta q_{\text{Scherrer}}^2}}$$

---

### 2.2 Ancho Transversal ($\Delta q_\perp$) y Estructura de Mosaico Angular ($\Delta \theta$)
El corte transversal mide la dispersión angular de los ejes cristalográficos de la muestra:

$$\Delta q_\perp = |\mathbf{G}_{hk}| \cdot \Delta \theta_{\text{mosaico}}$$

- **Si $\Delta q_\perp \approx \Delta q_\parallel$:** El pico es circular e isotrópico. La muestra es un mono-dominio cristalino coherente sin desorientación angular.
- **Si $\Delta q_\perp \gg \Delta q_\parallel$:** El pico se deforma adoptando la forma de un **arco circular concéntrico**. Esto diagnostica una **estructura de mosaico**: la red está dividida en micro-dominios o granos levemente rotados entre sí por un desvío estándar angular $\Delta \theta_{\text{mosaico}} = \Delta q_\perp / |\mathbf{G}|$.

---

## 3. Tratamiento Experimental de la Fuga de Frecuencia Cero (DC Bleed) y Deslumbrado Espectral

En la Transformada de Fourier discreta o continua de imágenes con pedestal luminoso positivo, el lóbulo central en $\mathbf{q}=\mathbf{0}$ contiene varios órdenes de magnitud más energía que los picos de difracción útiles ($I(0) \approx M^2$).

### Efectos Adversos de la Fuga DC:
1. **Deslumbrado Espectral (Spectral Glare):** Las colas de difracción de Airy del pico DC se propagan hacia frecuencias intermedias, sumergiendo los picos fundamentales de primer orden en un fondo artificial decreciente tipo $1/q^2$.
2. **Sesgo en la Altura de Pico:** Si no se resta la cola DC, la altura aparente del primer armónico $H_1$ se sobreestima, introduciendo un error de subestimación en el desorden de Debye-Waller $\sigma_{\text{pos}}$.

### Solución Implementada en PyPrinting 3.0:
1. **Sustracción de Media de Densidad:** Antes de evaluar la NUFFT, se elimina el promedio del proceso puntual dentro de la ROI:
   $$\tilde{\rho}(\mathbf{r}) = \rho(\mathbf{r}) - \bar{\rho} \cdot \mathbf{1}_{\Omega}(\mathbf{r})$$
2. **Apodización por Ventana de Hann / Tukey:** Atenúa suavemente los bordes del área de análisis a cero, suprimiendo los lóbulos de difracción en cruz originados por los bordes rectangulares de la ROI.
3. **Filtro Pasa-Altos Gaussiano en el Espacio Recíproco:**
   $$I_{\text{filtrado}}(\mathbf{q}) = I(\mathbf{q}) \cdot \left[ 1 - \exp\left( -\frac{|\mathbf{q}|^2}{2 q_{\text{corte}}^2} \right) \right]$$
   donde $q_{\text{corte}} \approx 0.35 \cdot \frac{2\pi}{a}$, eliminando por completo el pico central sin perturbar los armónicos de Bragg.

---

## 4. Matriz Diagnóstica de Toma de Decisiones en Laboratorio

El siguiente protocolo de diagnóstico espectral guía la toma de decisiones en el control de calidad de nano-impresión:

| Síntoma Espectral Observado | Diagnóstico Físico de la Muestra | Acción Correctiva en PyPrinting 3.0 |
| :--- | :--- | :--- |
| **Picos $H_{10} \neq H_{01}$** | Anisotropía en el desorden posicional ($\sigma_x \neq \sigma_y$). Deriva uniaxial durante el escaneo. | Activar compensación piezoeléctrica en bucle cerrado y autofoco periódico F10. |
| **Picos elípticos en arco ($\Delta q_\perp > 2\Delta q_\parallel$)** | Desorden de mosaico / desorientación angular entre parches impresos. | Calibrar repetibilidad angular de los galvo-espejos y corregir distorsión de campo. |
| **Pico $H_2$ ausente o sumergido** | Desorden fuerte ($\sigma_{\text{pos}} / a > 0.15$). Ruptura del método analítico directo. | Conmutar automáticamente a simulación Monte Carlo de ensamble ([[CAT-301_Algoritmos_Espacio_Real_KDTree_Asignacion_Monte_Carlo]]). |
| **Meseta difusa elevada $I_{\text{difuso}} \gg 0$** | Alta fracción de vacancias ($p > 10\%$) o polidispersividad severa en el tamaño de las partículas. | Revisar dosis de energía del láser y umbral de fotodiodo en `modules/confocal.py`. |
| **Picos de orden superior ensanchados cuadráticamente ($\text{FWHM}_2 \approx 4\,\text{FWHM}_1$)** | Desorden acumulativo Tipo II (Paracristal de Hosemann). No hay red fija de fondo. | Consultar modelo de Hosemann ([[CAT-309_Teoria_Paracristal_Hosemann_Perdida_Orden_2D]]). |

---

## 5. Conclusiones

1. **Riqueza Metrológica:** El espacio recíproco desacopla en rasgos ortogonales independientes la periodicidad ($q_1$), el desorden traslacional ($H_1, H_2$), la longitud de coherencia ($\Delta q_\parallel$) y la orientación angular ($\Delta q_\perp$).
2. **Inspección de Calidad Instantánea:** La matriz diagnóstica permite al operador calificar la viabilidad de una metasuperficie en milisegundos mediante la inspección del mapa recíproco antes de proceder a mediciones espectroscópicas de alta resolución.
