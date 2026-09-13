# Reporte Científico Canónico: Electrodinámica de Pinzas Ópticas, Fuerzas de Radiación y Termoplasmónica en Optical Printing 🔬

**Biblioteca Científica Canónica — Pilar I: Nanofísica y Óptica Teórica**  
**Signatura Canónica**: `CAT-109` | **Clúster**: `[FIS]` (Física)  
**Laboratorio de Nanofotónica — Instituto de Nanosistemas (INS-UNSAM / CONICET)**  
**Autor Principal**: José Luis González Peñafiel (*Becario Doctoral CONICET*)  
**Fecha de Publicación**: Septiembre 2026 | **Estado**: Vigente y Certificado por QA  
**Módulos del Sistema Asociados**: `modules/measurements.py`, `Laser532Window`, `contrapropagante.py`, `app.py`, `pyspectrum.py`  
**Referencias Cruzadas**: `[[CAT-101_Protocolo_Operativo_Impresion_Fototermica_Grillas_2D]]`, `[[CAT-108_Teoria_Optica_Telescopio_Rele_4f_y_Canales_Confocales]]`, `[[CAT-110_Fisicoquimica_Coloides_DLVO_y_Funcionalizacion_Superficies]]`, `[[SYS-101_Arquitectura_Hilos_Concurrencia_QThread]]`, `[[SYS-201_Seguridad_Optica_Watchdog_y_Obturadores]]`, `[[MOD-02_Measurements_Printing_y_Dimeros]]`, `[[MOD-05_Modulacion_Laser_Potencias]]`

---

## 1. Resumen Ejecutivo

El presente reporte científico formaliza los primeros principios electrodinámicos, electromagnéticos y térmicos que gobiernan la nanofabricación asistida por luz mediante **Impresión Óptica Fototérmica (*Optical Printing*)** en la suite **PyPrinting 3.0**.

A diferencia de una pinza óptica convencional conservativa (donde se busca confinar de manera tridimensional y estacionaria un dieléctrico en el foco), el *Optical Printing* aprovecha deliberadamente la resonancia plasmónica localizada (LSPR) de nanopartículas metálicas para romper la simetría de fuerzas axiales: la **presión de radiación ($\mathbf{F}_{\text{scat+abs}}$)** propulsa a la nanopartícula hacia el sustrato a velocidades de cientos de micrómetros por segundo, mientras que la **fuerza de gradiente ($\mathbf{F}_{\text{grad}}$)** la confina lateralmente con resolución sub-difracción. Simultáneamente, la absorción óptica casi unitaria induce calentamiento termoplasmónico localizado ($\Delta T \sim 50 - 100\ ^\circ\text{C}$), el cual activa fenómenos hidrodinámicos de termoforesis y convección interfacial. 

Este documento establece la formulación rigurosa de polarizabilidad dipolar con corrección de reacción de radiación, el balance vectorial de fuerzas, la ecuación estacionaria de difusión térmica en interfases asimétricas vidrio-agua, las fuerzas interparticulares de campo cercano para el ensamble de nanodímeros y los límites de seguridad experimental para evitar la cavitación destructiva por microburbujas.

---

## 2. Electrodinámica de Pinzas Ópticas y Fuerzas de Radiación

Las pinzas ópticas y el *Optical Printing* se fundamentan en la transferencia de momento lineal entre los fotones de un haz láser enfocado y una nanopartícula dieléctrica o metálica suspendida en un fluido dieléctrico (agua ultra-pura, $n_m = 1.333$).

```
               Haz Láser Enfocado (Gaussiano TEM00, NA >= 1.0)
                     \                 /
                      \               /
                       \             /
                   ─────▼───────────▼─────  Plano Focal (Cintura w0)
                         ░░░░░░░░░
                        ░░ Nanopart ░░  ──► F_grad (Hacia el foco |E|^2)
                         ░░░░░░░░░
                             │
                             ▼ F_scat / F_abs (Empuje en dirección k)
                   ───────────────────────  Sustrato de Vidrio Funcionalizado
```

### 2.1 Régimen de Rayleigh vs. Régimen de Mie

La respuesta electromagnética depende del parámetro de tamaño $x = k_m R = \frac{2\pi n_m R}{\lambda_0}$:

1. **Régimen Cuasi-Estático de Rayleigh ($2R \ll \lambda_m$, típicamente $2R < 100\ \text{nm}$)**:
   La nanopartícula experimenta un campo eléctrico espacialmente uniforme en todo su volumen. Se modela como un **dipolo puntual inducido** de momento dipolar:
   $$\mathbf{p}(t) = \epsilon_0 \epsilon_m \alpha(\omega) \mathbf{E}_0 e^{-i\omega t}$$
2. **Régimen de Mie ($2R \sim \lambda_m$ o $2R > \lambda_m$)**:
   Aparecen efectos de retardo de fase electromagnética y contribuciones multipolares de orden superior (cuadrupolos, octupolos magnéticos y eléctricos). Requiere resolver analíticamente las ecuaciones de Maxwell con condiciones de contorno de Mie.

En **PyPrinting 3.0**, las nanopartículas típicas de trabajo (AuNPs de $60\ \text{nm}$, $80\ \text{nm}$, $100\ \text{nm}$ y AgNPs de $40\ \text{nm}$) operan en el límite de Rayleigh con correcciones de segundo orden por reacción de radiación (*Radiation Reaction Correction*).

---

### 2.2 Polarizabilidad Compleja y Resonancia Plasmónica Localizada (LSPR)

La polarizabilidad electrostática dipolar de una nanoesfera metálica de radio $R$ con permitividad dieléctrica compleja $\epsilon_p(\omega) = \epsilon_p'(\omega) + i\epsilon_p''(\omega)$ en un medio de permitividad $\epsilon_m = n_m^2$ está dada por:

$$\alpha_0(\omega) = 4\pi R^3 \frac{\epsilon_p(\omega) - \epsilon_m}{\epsilon_p(\omega) + 2\epsilon_m}$$

Al incluir la reacción de radiación para conservar la energía de dispersión electromagnética:

$$\alpha(\omega) = \frac{\alpha_0(\omega)}{1 - i \frac{k_m^3}{6\pi} \alpha_0(\omega)}$$

donde $k_m = \frac{2\pi n_m}{\lambda_0}$ es el vector de onda en el medio.

#### Condición de Fröhlich y Resonancia Plasmónica:
La resonancia dipolar plasmónica ocurre cuando se minimiza el denominador de $\alpha_0$:

$$\text{Re}\{\epsilon_p(\omega_{\text{LSPR}})\} = -2\epsilon_m = -2 n_m^2 \approx -2(1.333)^2 \approx -3.55$$

* **Oro (Au)**: $\lambda_{\text{LSPR}} \approx 530 - 550\ \text{nm}$ (en agua). El láser verde de **$532\ \text{nm}$** excita de forma casi resonante el plasmón dipolar, induciendo una absorción óptica gigantesca ($\sigma_{\text{abs}} \gg \sigma_{\text{scat}}$), ideal para **impresión fototérmica ultrarrápida**.
* **Plata (Ag)**: $\lambda_{\text{LSPR}} \approx 405 - 420\ \text{nm}$. A $532\ \text{nm}$ se sitúa en el ala no resonante, con menor absorción y alta dispersión.
* **Láser Infrarrojo ($808\ \text{nm}$ / $1064\ \text{nm}$)**: Muy alejado del LSPR del oro esférico. La parte imaginaria $\epsilon_p''$ es baja, predominando el atrapamiento óptico conservativo tradicional sin sobrecalentamiento.

---

### 2.3 Separación Vectorial: Fuerza de Gradiente vs. Fuerza de Dispersión y Absorción

La fuerza óptica total promediada temporalmente $\langle \mathbf{F} \rangle$ sobre la nanopartícula se descompone rigurosamente en dos contribuciones ortogonales:

$$\langle \mathbf{F} \rangle = \mathbf{F}_{\text{grad}} + \mathbf{F}_{\text{scat+abs}}$$

#### 1. Fuerza de Gradiente ($\mathbf{F}_{\text{grad}}$ — Conservativa):
Proviene de la interacción de la parte en fase del dipolo inducido con el gradiente de intensidad del campo electromagnético. Confina la nanopartícula hacia el foco óptico ($|\mathbf{E}|^2$ máximo):

$$\mathbf{F}_{\text{grad}} = \frac{1}{4} \epsilon_0 \epsilon_m \text{Re}\{\alpha(\omega)\} \nabla |\mathbf{E}(\mathbf{r})|^2$$

Para un haz Gaussiano enfocado ($TEM_{00}$) con cintura $w_0$:
$$I(r, z) = I_0 \left(\frac{w_0}{w(z)}\right)^2 \exp\left(-\frac{2r^2}{w(z)^2}\right)$$
La fuerza lateral restaura la partícula hacia el eje óptico central según un resorte lineal: $F_{\text{grad}, r} \approx -\kappa_{\text{trap}} r$.

#### 2. Fuerza de Dispersión y Absorción ($\mathbf{F}_{\text{scat+abs}}$ — No Conservativa / Presión de Radiación):
Proviene de la transferencia de momento fotónico debida a la sección eficaz de extinción total ($\sigma_{\text{ext}} = \sigma_{\text{abs}} + \sigma_{\text{scat}}$). Empuja la partícula a lo largo del eje óptico de propagación ($\hat{\mathbf{z}}$):

$$\mathbf{F}_{\text{scat+abs}} = \frac{n_m}{c} \sigma_{\text{ext}}(\omega) \langle \mathbf{S}(\mathbf{r}) \rangle = \frac{n_m}{c} \left( \sigma_{\text{abs}} + \sigma_{\text{scat}} \right) I(\mathbf{r}) \hat{\mathbf{z}}$$

donde $\langle \mathbf{S} \rangle$ es el vector de Poynting y las secciones eficaces son:
$$\sigma_{\text{abs}}(\omega) = k_m \text{Im}\{\alpha(\omega)\}, \quad \sigma_{\text{scat}}(\omega) = \frac{k_m^4}{6\pi} |\alpha(\omega)|^2$$

---

### 2.4 Dependencia Espectral de Fuerzas y Precisión de Posicionamiento

El balance vectorial entre empuje axial ($F_z$) y confinamiento lateral ($F_r$) cambia drásticamente según la sintonía espectral entre la longitud de onda de iluminación ($\lambda_0$) y la resonancia plasmónica ($\lambda_{\text{LSPR}}$):

```
        En Resonancia Plasmónica (LSPR)           Fuera de Resonancia (Off-Resonance)
        (Ej: Au 60 nm con Láser 532 nm)           (Ej: Ag 60 nm con Láser 532 nm o Au a 808 nm)
              │                                                │
         Fr ◄─┼─► Fr (Débil)                              Fr ◄─┼─► Fr (Moderada)
              │                                                │
              ▼▼▼▼▼ Fz (Dominante, Fz ~ 10 Fr)                 ▼ Fz (Fz ~ Fr)
```

1. **Régimen Resonante (Au $60\ \text{nm}$ con Láser $532\ \text{nm}$ | $\lambda_0 \approx \lambda_{\text{LSPR}}$)**:
   * La fuerza axial de presión de radiación se incrementa fuertemente: $F_z \approx 10 \times F_r$.
   * La nanopartícula es propulsada axialmente a gran velocidad ($v_z \sim 100\ \mu\text{m/s}$), reduciendo su tiempo de residencia en el cono focal a unos pocos milisegundos.
   * **Precisión Lateral ($\sigma_{\text{print}}$)**: El mínimo tiempo de tránsito reduce la excursión browniana lateral en el plano $X-Y$, alcanzando una **precisión de posicionamiento sub-difracción $\sigma_{\text{print}} \approx 30 - 35\ \text{nm}$**.
2. **Régimen No Resonante (Ag $60\ \text{nm}$ con Láser $532\ \text{nm}$ | $\lambda_0 \gg \lambda_{\text{LSPR}} = 405\ \text{nm}$)**:
   * La absorción cae y las magnitudes de fuerza axial y radial se igualan ($F_z \sim F_r \approx 2 - 5\ \text{pN}$).
   * La partícula experimenta un atrapamiento tridimensional transitorio antes de ser empujada contra el vidrio.
   * **Precisión Lateral ($\sigma_{\text{print}}$)**: La mayor permanencia en difusión térmica incrementa la dispersión espacial a **$\sigma_{\text{print}} \approx 50 - 65\ \text{nm}$**.

> [!IMPORTANT]
> **Diferencia Fundamental con las Pinzas Ópticas Clásicas**:
> En una pinza óptica 3D conservativa se requiere que $F_{\text{grad}, z} > F_{\text{scat}, z}$ para atrapar en el foco. En **Optical Printing**, se opera en el régimen resonante hacia abajo, donde $\mathbf{F}_{\text{scat+abs}}$ domina axialmente y **empuja activamente la nanopartícula hacia el sustrato de vidrio**, permitiendo su captura por las fuerzas interfaciales en milisegundos.

---

## 3. Termoplasmónica y Fenómenos Térmicos en la Nanoescala

Al iluminar una AuNP de $60\ \text{nm}$ a $\lambda = 532\ \text{nm}$ con una irradiancia $I_0 \sim 1 - 10\ \text{mW}/\mu\text{m}^2$, los electrones de la banda de conducción oscilan colectivamente y decaen de forma no radiativa por dispersión electrón-electrón ($100\ \text{fs}$) y electrón-fonón ($1 - 5\ \text{ps}$), convirtiendo prácticamente el $100\%$ de la potencia absorbida en calor localizado.

```
                    Disipación Térmica Local
                           ▲  ▲  ▲
                      ┌─────────────┐
                      │    AGUA     │  T_inf = 293 K
               ───────┴─────────────┴───────
                      │  AuNP 60 nm │  T_NP = 350 - 450 K
                      │  Q_abs      │
               ───────┬─────────────┬───────
                      │   VIDRIO    │
                      └─────────────┘
```

### 3.1 Disipación de Calor y Ecuación de Difusión Estacionaria

La potencia térmica generada por la nanoesfera es $Q = \sigma_{\text{abs}} I_0$. La temperatura en el fluido a distancia $r \ge R$ del centro sigue la solución de la ecuación estacionaria de Fourier ($\nabla^2 T = 0$):

$$\Delta T(r) = T(r) - T_\infty = \frac{\sigma_{\text{abs}} I_0}{4\pi \kappa_{\text{medio}} r} \quad (r \ge R)$$

En la superficie de la partícula ($r = R$):

$$\Delta T_{\text{NP}} = \frac{\sigma_{\text{abs}} I_0}{4\pi \kappa_{\text{medio}} R}$$

Para agua ($\kappa_{\text{medio}} = 0.60\ \text{W}/(\text{m}\cdot\text{K})$), una AuNP de $60\ \text{nm}$ con $I_0 = 5\ \text{mW}/\mu\text{m}^2$ alcanza un incremento $\Delta T_{\text{NP}} \approx 40 - 120\ ^\circ\text{C}$ en régimen estacionario (el cual se establece en menos de $10\ \text{ns}$).

---

### 3.2 Disipación Asimétrica en la Interfase Vidrio-Agua ($\kappa_{\text{eff}}$)

Durante la deposición, la nanopartícula disipa calor en la interfase asimétrica entre dos medios térmicamente disímiles: agua ($\kappa_w = 0.60\ \text{W/(m}\cdot\text{K)}$) y vidrio de borosilicato ($\kappa_g = 1.10\ \text{W/(m}\cdot\text{K)}$):

1. **Conductividad Térmica Efectiva ($\kappa_{\text{eff}}$)**:
   $$\kappa_{\text{eff}} = \frac{\kappa_w + \kappa_g}{2} \approx \frac{0.60 + 1.10}{2} = 0.85\ \text{W}/(\text{m}\cdot\text{K})$$
   $$\Delta T_{\text{NP, interfase}} = \frac{\sigma_{\text{abs}} I_0}{4\pi \kappa_{\text{eff}} R}$$
   El sustrato de vidrio actúa como un disipador térmico preferencial, canalizando aproximadamente el **$60\%$ del flujo de calor conductivo** hacia el portaobjetos.
2. **Cinética de Enfriamiento Ultrarrápido post-Obturación**:
   La constante de tiempo de relajación térmica de una esfera de $60\ \text{nm}$ en contacto con el vidrio es:
   $$\tau_{\text{relax}} \approx \frac{\rho_{\text{Au}} c_{\text{Au}} R^2}{3 \kappa_{\text{eff}}} \approx 0.5 - 2.0\ \text{ns}$$
   Al activarse el criterio de parada y cerrarse el obturador láser (`close_shutter()`), la nanopartícula y el fluido circundante regresan a temperatura ambiente ($T_\infty = 293\ \text{K}$) en **menos de $1\ \mu\text{s}$**, congelando la posición sin recocido ni deformación residual.

---

### 3.3 Termoforesis y Umbral de Cavitación por Microburbujas

El gradiente térmico extremo ($\nabla T \sim 10^8\ \text{K}/\text{m}$) induce:
1. **Termoforesis Coloidal (Efecto Soret)**:
   $$\mathbf{v}_T = -D_T \nabla T = -D_0 S_T \nabla T$$
   Para AuNPs estabilizadas por citrato o CTAB, $S_T > 0$ (comportamiento termófobo). Las partículas vecinas en la solución son expulsadas radialmente del núcleo caliente, evitando la llegada simultánea de múltiples nanopartículas durante el pulso óptico.
2. **Cavitación por Microburbujas (Límite de Destrucción)**:
   Si la potencia óptica supera el límite spinodal del agua ($T_{\text{spinodal}} \approx 280 - 300\ ^\circ\text{C}$), se produce la nucleación explosiva de una microburbuja plasmónica de vapor. La tensión superficial genera convección de Marangoni violenta ($\mathbf{u} \propto \nabla \gamma_{\text{LV}}$), succionando agregados masivos y despegando el recubrimiento de silano.

> [!CAUTION]
> **Protocolo ante Cavitación**: Si la señal de fotodiodo satura abruptamente a $10\ \text{V}$ o cae a $0\ \text{V}$ con deformación visual en la cámara Canon, se ha superado el umbral de cavitación. Se debe reducir de inmediato la potencia del láser 532 nm (voltaje AO2 $< 1.5\ \text{V}$) y purgar la celda microfluídica.

---

## 4. Nanodímeros Plasmónicos y Fuerzas de Campo Cercano

Cuando se imprime una segunda nanopartícula (B) a distancia nanométrica $s \sim 1 - 20\ \text{nm}$ de una nanopartícula previa fija (A), sus plasmones se acoplan según la **Teoría de Hibridación Plasmónica**:

```
       Partícula A              Gap (s)             Partícula B
      ┌───────────┐          ◄─────────►          ┌───────────┐
      │   AuNP    │          ░░░░░░░░░░░          │   AuNP    │
      │  (Fija)   │          ░░ HOT SPOT ░        │ (Impresa) │
      │  ( +  - ) │          ░░ E^2 > 10³░        │  ( +  - ) │
      └───────────┘          ░░░░░░░░░░░          └───────────┘
```

1. **Modo Enlazante Dipolar ($\omega_-$)**: Oscilaciones de carga en fase $(+- \quad +-)$. El campo eléctrico local en el gap interparticular se amplifica en órdenes de magnitud ($|\mathbf{E}/\mathbf{E}_0|^2 > 10^3 - 10^5$), creando un **Hot Spot plasmónico** para SERS monomolecular.
2. **Corrimiento Espectral al Rojo (Redshift)**: La longitud de onda LSPR se desplaza hacia el infrarrojo según $\Delta \lambda \propto \exp(-s / 0.2 R)$, detectable en tiempo real mediante `pyspectrum.py` (`[[MOD-06_PySpectrum_Espectroscopia_Shamrock]]`).
3. **Fuerzas Ópticas Dipolo-Dipolo y Control de Polarización**:
   $$\mathbf{F}_{\text{inter}}(s) \propto \frac{\text{Re}\{\alpha_A \alpha_B^*\}}{s^4} \left[ 3(\hat{\mathbf{p}}_A \cdot \hat{\mathbf{r}}_{AB})\hat{\mathbf{p}}_B + 3(\hat{\mathbf{p}}_B \cdot \hat{\mathbf{r}}_{AB})\hat{\mathbf{p}}_A - 2(\hat{\mathbf{p}}_A \cdot \hat{\mathbf{p}}_B)\hat{\mathbf{r}}_{AB} \right]$$
   * **Polarización Paralela ($\mathbf{E} \parallel \hat{\mathbf{r}}_{AB}$)**: Los dipolos oscilan colinealmente. La fuerza interparticular es **atractiva**, favoreciendo el ensamble de gaps sub-10 nm.
   * **Polarización Perpendicular ($\mathbf{E} \perp \hat{\mathbf{r}}_{AB}$)**: La fuerza es **repulsiva**, desviando lateralmente la nanopartícula B.
   * **Regla Operativa**: Para ensamblar dímeros con gap mínimo, orientar la placa $\lambda/2$ de modo que la polarización lineal coincida con el eje de impresión $(\Delta x, \Delta y)$.

---

## 5. Tabla Maestra de Propiedades Físicas de Nanomateriales

| Parámetro Físico | Símbolo | Valor Típico en PyPrinting | Unidades | Significado e Impacto Experimental |
| :--- | :---: | :---: | :---: | :--- |
| **Longitud de Onda Impresión** | $\lambda_0$ | $532.0$ | $\text{nm}$ | Resonancia casi perfecta con LSPR de AuNPs |
| **Longitud de Onda Atrapamiento IR** | $\lambda_{\text{IR}}$ | $808.0\ \text{o}\ 1064.0$ | $\text{nm}$ | Régimen conservativo no resonante (bajo $\Delta T$) |
| **Apertura Numérica del Objetivo** | $\text{NA}$ | $1.40\ \text{o}\ 1.49$ | — | Cintura focal difractiva $w_0 \approx 0.61\lambda/\text{NA} \approx 230 - 260\ \text{nm}$ |
| **Índice Aceite de Inmersión** | $n_{\text{oil}}$ | $1.518$ | — | Emparejado con cubreobjetos de vidrio borosilicato ($n=1.52$) |
| **Índice Medio Acuoso** | $n_m$ | $1.333$ | — | Medio de dispersión coloidal Milli-Q |
| **Potencia Óptica en Muestra** | $P_{\text{sample}}$ | $0.5 - 15.0$ | $\text{mW}$ | Controlada por voltaje DAC AO2 ($0-5\ \text{V}$) en NI-DAQmx |
| **Sección Eficaz Absorción Au 60nm** | $\sigma_{\text{abs}}$ | $\approx 3.5 \times 10^{-15}$ | $\text{m}^2$ | Velocidad de conversión fototérmica a calor |
| **Sección Eficaz Dispersión Au 60nm**| $\sigma_{\text{scat}}$ | $\approx 4.0 \times 10^{-16}$ | $\text{m}^2$ | Salto de señal en fotodiodo para parada en tiempo real |
| **Fuerza Axial de Radiación** | $F_z$ | $5 - 80$ | $\text{pN}$ | Propulsión hacia el sustrato funcionalizado |
| **Tiempo de Tránsito y Fijación** | $\tau_{\text{print}}$ | $2 - 50$ | $\text{ms}$ | Intervalo entre captura óptica y anclaje químico |
| **Rigidez de Trampa Lateral** | $\kappa_{\text{trap}}$ | $0.05 - 0.50$ | $\text{pN/(nm}\cdot\text{mW)}$ | Confinamiento lateral sub-difracción ($\sigma_{xy} < 35\ \text{nm}$) |

---

## 6. Referencias Bibliográficas Fundacionales

1. **Gargiulo, Julián** (2017). *Impresión óptica de nanopartículas metálicas*. Tesis Doctoral, FCEN-UBA / CIBION-CONICET. Capítulos 2, 5 y 6.
2. **Martínez, Luciana** (2019). *Impresión óptica de nanopartículas y nanoestructuras: ensamblado guiado, nanotermometría y plasmónica*. Tesis Doctoral, INS-UNSAM / CONICET. Capítulos 2 y 4.
3. **Urban, A. S., Lutich, A. A., Sannomiya, T., et al.** (2010). *Laser printing of single gold nanoparticles*. Nano Letters, 10(12), 4794–4798.
4. **Gargiulo, J., Brick, T., Violi, I. L., et al.** (2017). *Understanding and optimizing the printing accuracy of isolated gold and silver nanoparticles*. Nano Letters, 17(9), 5747–5755.
5. **Martínez, L. D., Gargiulo, J., Violi, I. L., & Stefani, F. D.** (2019). *Real-time temperature mapping and sub-diffraction assembly of metallic nanodimers by optical printing*. ACS Photonics, 6(11), 2682–2688.
6. **Bohren, C. F., & Huffman, D. R.** (1983). *Absorption and Scattering of Light by Small Particles*. John Wiley & Sons.
