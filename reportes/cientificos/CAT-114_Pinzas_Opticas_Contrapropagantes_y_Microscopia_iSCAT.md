# CAT-114: Pinzas Ópticas Contrapropagantes y Microscopía iSCAT de Alta Sensibilidad
## Anulación Analítica de Fuerzas de Dispersión Axiales, Interferencia de Onda Estacionaria y Detección Volumétrica d^3 de Nanopartículas Metálicas

---

**Signatura Bibliotecaria:** `CAT-114`  
**Clasificación Temática:** `[FIS]` / `[MAT]` Trampeo Óptico, Fuerzas de Radiación y Microscopía Interferométrica  
**Pilar:** Pilar I — Nanofabricación Óptica, Control de Posición y Termoplasmónica  
**Autoría:** José Luis González Peñafiel (*Becario Doctoral CONICET*), Comité Científico PyPrinting 3.0  
**Fecha de Publicación:** Septiembre 2026  
**Estado:** Producción / Consolidado  
**Módulos Asociados:** `contrapropagante.py`, `modules/camera.py`, `analysis/psf_analyzer.py`  
**Documentos Vinculados:**  
- [[CAT-108_Teoria_Optica_Telescopio_Rele_4f_y_Canales_Confocales]] (Óptica de difracción, relé 4f e iSCAT)  
- [[CAT-109_Electrodinamica_Fuerzas_Opticas_y_Termoplasmonica_Printing]] (Fuerzas ópticas y termoplasmónica)  
- [[CAT-103_Control_Lazo_Cerrado_Fototermico_y_Sintesis_Dimeros]] (Control de parada de impresión)  

---

## 1. Resumen Ejecutivo

En las pinzas ópticas monohaz convencionales (trampa de Ashkin), la captura estable tridimensional de una partícula exige que la fuerza de gradiente atractiva $\mathbf{F}_{\text{grad}}$ supere a la fuerza desestabilizadora de dispersión radiativa $\mathbf{F}_{\text{scat}}$, lo que requiere objetivos de inmersión en aceite de apertura numérica extrema ($\text{NA} \ge 1.30$). Para nanopartículas plasmónicas metálicas (Au/Ag), la sección eficaz de dispersión y absorción es órdenes de magnitud superior a la de esferas dieléctricas, provocando que la presión de radiación empuje a la partícula en la dirección de propagación del haz hacia el sustrato o fuera de la trampa.

El módulo `contrapropagante.py` supera esta limitación física mediante una **geometría óptica de dos haces contrapropagantes coaxiales** enfocados por dos objetivos idénticos enfrentados. Este reporte formaliza el balance de fuerzas analítico que permite la **anulación neta de la fuerza de dispersión axial**, deduce la formación de trampas de onda estacionaria con rigidez modulable por desfase de Gouy, y fundamenta la técnica de **Microscopía de Dispersión Interferométrica (iSCAT)**, demostrando su escalado volumétrico $d^3$ que posibilita el seguimiento ultra-rápido de coloides sub-20 nm a miles de fotogramas por segundo sin fotoblanqueo.

---

## 2. Balances de Fuerzas Ópticas en Geometría Contrapropagante

Considérense dos haces gaussianos monocromáticos coherentes o incoherentes entre sí que se propagan en sentidos opuestos a lo largo del eje óptico $\hat{\mathbf{z}}$ con potencias $P_1$ y $P_2$:

```
Objetivo Superior (Obj 1)  -----> Haz 1 (↓ k_1 = +k z^)
                                    │
                                 [ Foco ]  <--- Nanopartícula coloidal
                                    │
Objetivo Inferior (Obj 2)  <----- Haz 2 (↑ k_2 = -k z^)
```

### 2.1 Anulación de la Fuerza de Dispersión Axial
En el régimen de Rayleigh ($d \ll \lambda$), la fuerza de dispersión óptica experimentada por un coloide de polarizabilidad $\alpha$ ante un haz $j$ es proporcional al vector de Poynting $\mathbf{S}_j$:

$$\mathbf{F}_{\text{scat}, j} = \frac{n_{\text{medio}} \, \sigma_{\text{scat}}}{c} \, \mathbf{S}_j = \frac{n_{\text{medio}} \, \sigma_{\text{scat}}}{c} \, I_j(\mathbf{r}) \, \hat{\mathbf{k}}_j$$

Dado que $\hat{\mathbf{k}}_1 = +\hat{\mathbf{z}}$ y $\hat{\mathbf{k}}_2 = -\hat{\mathbf{z}}$, la fuerza de dispersión neta total en el eje óptico es:

$$\mathbf{F}_{\text{scat}, \text{tot}}(z) = \frac{n_{\text{medio}} \, \sigma_{\text{scat}}}{c} \left[ I_1(z) - I_2(z) \right] \hat{\mathbf{z}}$$

Cuando las potencias y alineaciones de ambos objetivos se balancean simétricamente en el plano focal común ($I_1(0) = I_2(0)$):
$$\mathbf{F}_{\text{scat}, \text{tot}}(0) = \mathbf{0}$$

La trampa óptica queda gobernada puramente por la **fuerza de gradiente conservativa**:
$$\mathbf{F}_{\text{grad}} = \frac{1}{4} \varepsilon_0 \varepsilon_m \text{Re}(\alpha) \nabla \left( |\mathbf{E}_1 + \mathbf{E}_2|^2 \right)$$
permitiendo atrapar nanopartículas metálicas fuertemente absorbentes y dispersoras con objetivos de apertura numérica moderada ($\,\text{NA} \approx 0.6 - 0.9$) y largas distancias de trabajo.

---

## 3. Trampa de Onda Estacionaria y Fase de Gouy

Si ambos haces son mutuamente coherentes (provenientes del mismo láser divisor), la superposición genera un patrón de interferencia axial de **onda estacionaria**:

$$E(z, t) = E_0 e^{i(kz - \omega t)} + E_0 e^{i(-kz - \omega t + \phi)} = 2 E_0 \cos\left( kz - \frac{\phi}{2} \right) e^{-i(\omega t - \phi/2)}$$
$$I(z) \propto 4 E_0^2 \cos^2\left( kz - \frac{\phi}{2} \right) = 2 E_0^2 \left[ 1 + \cos(2kz - \phi) \right]$$

La periodicidad espacial de las trampas ópticas axiales es:
$$\Lambda_{\text{trampa}} = \frac{\lambda}{2 n_{\text{medio}}}$$
creando una serie de microtrampas ultrarrígidas espaciadas cada $\sim 200\ \text{nm}$ en el foco, con rigideces axiales $\kappa_z$ que superan en más de un orden de magnitud a las de una trampa monohaz convencional.

---

## 4. Microscopía de Dispersión Interferométrica (iSCAT)

La visualización de nanopartículas de oro individuales en `contrapropagante.py` no requiere fluorescencia. Utiliza **iSCAT**, una técnica interferométrica homodina en campo común.

### 4.1 La Ecuación Interferométrica de Señal
El detector registra la superposición coherente del campo de referencia reflejado en la interfaz vidrio-agua ($E_{\text{ref}} = r E_{\text{inc}}$) y el campo elásticamente dispersado por la nanopartícula ($E_{\text{scat}} = s E_{\text{inc}}$):

$$I_{\text{det}} = |E_{\text{ref}} + E_{\text{scat}}|^2 = |E_{\text{ref}}|^2 + |E_{\text{scat}}|^2 + 2 |E_{\text{ref}}| |E_{\text{scat}}| \cos\theta$$

donde $\theta$ es la diferencia de fase óptica entre la reflexión y la dispersión (incluyendo la fase de Gouy y la distancia axial $z$).

### 4.2 Escalado Volumétrico $d^3$ vs $d^6$
En microscopía de campo oscuro convencional (Dark-Field), el término de referencia se bloquea ($E_{\text{ref}} = 0$), detectando únicamente:
$$I_{\text{DF}} = |E_{\text{scat}}|^2 \propto \sigma_{\text{scat}} \propto d^6$$
Para una partícula de $20\ \text{nm}$, la señal de campo oscuro decae por un factor de $(20/100)^6 \approx 6.4 \times 10^{-5}$ frente a una de $100\ \text{nm}$, volviéndose indetectable ante el ruido del sensor.

En cambio, en **iSCAT**, para un sustrato de vidrio con reflectividad $r \approx 0.004$ ($|E_{\text{ref}}| \gg |E_{\text{scat}}|$), el segundo término cuadrático es despreciable y la señal diferencial neta es:
$$\frac{\Delta I}{I_{\text{ref}}} = \frac{I_{\text{det}} - |E_{\text{ref}}|^2}{|E_{\text{ref}}|^2} \approx 2 \frac{|E_{\text{scat}}|}{|E_{\text{ref}}|} \cos\theta \propto \frac{\alpha}{r} \propto d^3$$

El contraste iSCAT decae únicamente como $d^3$:
$$\left(\frac{20}{100}\right)^3 = 8 \times 10^{-3}$$
¡Una señal **125 veces más intensa** que en campo oscuro!, permitiendo filmar nanopartículas de oro sub-20 nm a relaciones señal-ruido $>15$ con frecuencias de adquisición de kilohertz.

---

## 5. Referencias Bibliográficas Primarias

1. **Ashkin, A.** (1970). *Acceleration and Trapping of Particles by Radiation Pressure*. Physical Review Letters, 24(4), 156–159. [DOI: 10.1103/PhysRevLett.24.156](https://doi.org/10.1103/PhysRevLett.24.156)
2. **Ortega Arroyo, J., & Kukura, P.** (2016). *Interferometric scattering microscopy (iSCAT): unlabelled tracking and imaging of colloidal and biological matter*. Physical Chemistry Chemical Physics, 18(13), 8858–8873. [DOI: 10.1039/C6CP00010A](https://doi.org/10.1039/C6CP00010A)
3. **Zemánek, P., et al.** (2003). *Optical trapping of nanoparticles and microparticles by a counter-propagating dual-beam trap*. Optics Communications, 220(4-6), 401–412.
