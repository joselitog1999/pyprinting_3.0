# Reporte Científico Canónico: Fisicoquímica de Coloides, Potencial DLVO y Funcionalización de Superficies 🧪

**Biblioteca Científica Canónica — Pilar I: Nanofísica y Óptica Teórica**  
**Signatura Canónica**: `CAT-110` | **Clúster**: `[FIS]` (Física)  
**Laboratorio de Nanofotónica — Instituto de Nanosistemas (INS-UNSAM / CONICET)**  
**Autor Principal**: José Luis González Peñafiel (*Becario Doctoral CONICET*)  
**Fecha de Publicación**: Septiembre 2026 | **Estado**: Vigente y Certificado por QA  
**Módulos del Sistema Asociados**: `modules/measurements.py`, `grid_generator.py`, `app.py`, `modules/camera.py`  
**Referencias Cruzadas**: `[[CAT-101_Protocolo_Operativo_Impresion_Fototermica_Grillas_2D]]`, `[[CAT-105_Compensacion_Deriva_Termomecanica_Particula_Ancla_P0]]`, `[[CAT-109_Electrodinamica_Fuerzas_Opticas_y_Termoplasmonica_Printing]]`, `[[SYS-101_Arquitectura_Hilos_Concurrencia_QThread]]`, `[[SYS-104_Matriz_Intercambio_Archivos_y_Formatos_IO]]`, `[[MOD-02_Measurements_Printing_y_Dimeros]]`, `[[MOD-14_Protocolos_Laboratorio_SOP]]`

---

## 1. Resumen Ejecutivo

El éxito nanométrico de la nanofabricación por **Impresión Óptica Fototérmica (*Optical Printing*)** depende de la interacción interfacial entre la nanopartícula metálica coloidal y el sustrato portamuestra. Mientras que el campo electromagnético del láser enfocado proporciona la fuerza motriz direccional ($\mathbf{F}_{\text{scat+abs}}$, detallada en `[[CAT-109_Electrodinamica_Fuerzas_Opticas_y_Termoplasmonica_Printing]]`), la **inmovilización permanente, irreversible y termodinámicamente estable** de la nanopartícula sobre el vidrio requiere el control de las fuerzas electrostáticas e interfaciales de superficie.

Este reporte formaliza la fisicoquímica coloidal del sistema: la estructura de la doble capa eléctrica (EDL), la longitud de apantallamiento de Debye ($\kappa_D^{-1}$), el potencial total de interacción según la **teoría DLVO (Derjaguin-Landau-Verwey-Overbeek)**, los protocolos de funcionalización covalente por silanización con **APTES (3-aminopropiltrietoxisilano)** y la **cinética estocástica de arribo browniano de Smoluchowski/Poisson**, proporcionando la justificación analítica del parámetro de temporización máxima $T_{\text{max}} = 20.0\ \text{s}$ implementado en el software. Asimismo, se formaliza la cinemática de marcos de referencia y la correspondencia optomecánica entre los ejes de la platina piezoeléctrica Physik Instrumente E-517 y el sensor de la cámara réflex Canon EOS 500D.

---

## 2. Doble Capa Eléctrica y Longitud de Apantallamiento de Debye

Cuando una nanopartícula metálica o un sustrato dieléctrico se sumerge en agua, los grupos químicos ionizables superficiales se disocian o adsorben iones del medio, adquiriendo una carga superficial neta $\sigma_0$ y un potencial electrostático de superficie $\psi_0$.

```
    Superficie Vidrio / AuNP       Capa de Stern       Capa Difusa (Gouy-Chapman)
          [Sólido]                   (Iones fijos)         (Contraiones móviles)
    ─────────────────────┬──────────────────────────┬─────────────────────────────►
                         │                          │      Potencial ψ(x)
      Carga negativa     │   Contraiones adsorbidos │         ▲
      (Si-O- / Citrato)  │   rígidamente (x = d)    │         │  ψ0
                         │                          │         │ ╭─────────
                         │                          │         │ │         ╰────── ψ(x) ~ exp(-κ x)
                         │   Plano Interno / Externo│         └─┴────────────────► Distancia x
                         │   de Helmholtz           │           │◄── κ_D⁻¹ ──►│
```

### 2.1 Ecuación de Poisson-Boltzmann y Longitud de Debye ($\kappa_D^{-1}$)

En el régimen de potenciales electrocinéticos moderados ($|\psi| < 25\ \text{mV}$ a temperatura ambiente), la ecuación no lineal de Poisson-Boltzmann se linealiza según la aproximación de Debye-Hückel:

$$\nabla^2 \psi = \kappa_D^2 \psi \implies \psi(x) = \psi_0 \exp(-\kappa_D x)$$

donde la escala espacial de decaimiento del apantallamiento electrostático (la **longitud de Debye $\kappa_D^{-1}$**) está determinada por la fuerza iónica $I_s$ del medio acuoso:

$$\kappa_D^{-1} = \sqrt{\frac{\epsilon_0 \epsilon_r k_B T}{2 e^2 I_s}}$$

con la fuerza iónica definida como $I_s = \frac{1}{2} \sum_i c_i z_i^2$, donde $c_i$ es la concentración molar del ion $i$ y $z_i$ su valencia.

#### Dependencia Experimental con la Fuerza Iónica en PyPrinting 3.0:
* **Agua ultra-pura Milli-Q ($I_s \sim 10^{-5}\ \text{M}$, $\text{pH} \approx 6.0$)**: $\kappa_D^{-1} \approx 96 - 100\ \text{nm}$. La repulsión electrostática es de muy largo alcance; las partículas no se adhieren espontáneamente sin asistencia de fuerzas ópticas.
* **Medio con buffer salino diluido ($I_s \sim 1\ \text{mM}$)**: $\kappa_D^{-1} \approx 9.6\ \text{nm}$. Régimen óptimo de trabajo: previene la coagulación coloidal en la celda y permite la fijación óptica controlada.
* **Medio de alta fuerza iónica ($I_s \ge 100\ \text{mM}$)**: $\kappa_D^{-1} < 0.96\ \text{nm}$. El apantallamiento es casi total, anulando la barrera electrostática y provocando agregación espontánea inespecífica sobre el vidrio (*fouling*).

---

## 3. Teoría Interfacial DLVO y Atrapamiento en el Pozo Primario

El balance energético total de interacción $V_{\text{DLVO}}(D)$ entre una nanoesfera de radio $R$ y un sustrato plano en función de la distancia de separación $D$ resulta de la superposición de dos fuerzas opuestas:

$$V_{\text{DLVO}}(D) = V_{\text{vdW}}(D) + V_{\text{EDL}}(D)$$

```
       Potencial Total V(D)
          ▲
          │                Barrera de Activación E_b (Repulsión EDL)
          │                     ╭───────╮
          │                    ╭╯       ╰────────────────  D (Distancia)
          │  ─────────────────╯──────────────────────────►
          │                  │
          │                  ▼ F_laser (Supera la barrera E_b)
          │           Pozo Primario Van der Waals (Contacto Íntimo D < 1 nm)
          │           (Profundidad > 100 k_B T — Inmovilización Irreversible)
```

### 3.1 Componente Atractiva de Van der Waals ($V_{\text{vdW}}$)

Proviene de las correlaciones fluctuantes dipolo-dipolo cuánticas y electrodinámicas (fuerzas de London-Lifshitz). Para una esfera de radio $R$ frente a un semi-espacio plano a distancia $D \ll R$:

$$V_{\text{vdW}}(D) = -\frac{A_H R}{6 D}$$

donde $A_H$ es la constante de Hamaker efectiva del sistema combinado (Nanopartícula de Oro – Agua – Vidrio):
$$A_H \approx \left(\sqrt{A_{\text{Au}}} - \sqrt{A_{\text{agua}}}\right)\left(\sqrt{A_{\text{vidrio}}} - \sqrt{A_{\text{agua}}}\right) \approx 1.5 - 2.5 \times 10^{-19}\ \text{J} \approx 35 - 60\ k_B T$$

### 3.2 Componente Repulsiva Electrostática ($V_{\text{EDL}}$)

Para superficies cargadas con potenciales $\psi_1$ (AuNP) y $\psi_2$ (sustrato) con $\kappa_D D > 1$:

$$V_{\text{EDL}}(D) \approx 64 \pi \epsilon_0 \epsilon_r R \left(\frac{k_B T}{e}\right)^2 \gamma_1 \gamma_2 \exp(-\kappa_D D)$$

donde $\gamma_i = \tanh\left(\frac{e \psi_i}{4 k_B T}\right)$. Si ambas superficies poseen carga del mismo signo ($\psi_1 \psi_2 > 0$), $V_{\text{EDL}} > 0$, generando una **barrera de potencial electrostático $E_b \sim 10 - 50\ k_B T$** que impide la colisión espontánea.

### 3.3 Mecanismo de Fijación Irreversible en Optical Printing

1. **Vencimiento de la Barrera por Presión de Radiación**: La fuerza axial de scattering del láser $\mathbf{F}_{\text{scat}}$ ($10 - 80\ \text{pN}$) realiza un trabajo mecánico $W_{\text{laser}} = \int F_{\text{scat}} dD > E_b$, forzando a la partícula a atravesar la barrera de repulsión.
2. **Caída en el Pozo Primario**: Al alcanzar $D < 1\ \text{nm}$, la atracción de Van der Waals diverge asintóticamente, atrapando a la nanopartícula en un pozo energético de profundidad $|V| > 100 - 1000\ k_B T$.
3. **Estabilidad Térmica Permanente**: La inmovilización es **termodinámicamente irreversible**. Ni el cierre del obturador láser ni el flujo hidrodinámico posterior de lavado pueden desorber la partícula de la superficie.

---

## 4. Funcionalización Química del Sustrato: Protocolo APTES

El vidrio de borosilicato sin tratar posee grupos silanol superficiales ($\text{Si-OH}$). En agua neutra ($\text{pH} \approx 6.5 - 7.0$), estos grupos se desprotonan a silanoato ($\text{Si-O}^-$), otorgándole un potencial zeta negativo $\zeta_{\text{vidrio}} \approx -40\ \text{a} -70\ \text{mV}$. Como las AuNPs estándar estabilizadas por citrato también están cargadas negativamente ($\zeta_{\text{NP}} \approx -35\ \text{mV}$), la repulsión mutua es máxima.

Para garantizar fijación ultra-firme y evitar rebotes mecánicos, se modifica químicamente la superficie mediante **APTES (3-aminopropiltrietoxisilano)**:

```
[Vidrio Hidroxilado (Si-OH)] ──► [Silanización APTES] ──► [Superficie Positiva (-NH3+)]
       ─Si─OH                       ─Si─O─Si─(CH2)3─NH3⁺             ▲
       ─Si─OH                       ─Si─O─Si─(CH2)3─NH3⁺             │ Atrae AuNP-Citrato (-)
```

### 4.1 Mecanismo Covalente de Silanización:
1. **Limpieza Piranha**: Inmersión en solución $3:1\ \text{H}_2\text{SO}_4 (98\%) : \text{H}_2\text{O}_2 (30\%)$ a $80\ ^\circ\text{C}$ durante $45\ \text{min}$. Remueve contaminantes orgánicos y satura la superficie de grupos hidroxilo reactivos ($\text{Si-OH}$).
2. **Condensación de APTES**: Los grupos etoxi ($\text{-O-CH}_2\text{CH}_3$) se hidrolizan y condensan con los silanoles del vidrio formando enlaces covalentes $\text{Si-O-Si}$ altamente estables.
3. **Inversión del Potencial Zeta**: Los grupos amino terminales ($\text{-NH}_2$) se protonan en medio acuoso a **$\text{-NH}_3^+$**, invirtiendo el potencial de superficie a **$\zeta_{\text{sustrato}} \approx +30\ \text{a} +50\ \text{mV}$**.
4. **Acoplamiento Electrostático Fuerte**: La atracción culombiana directa entre el citrato negativo de la nanopartícula y el amonio positivo del silano guía la fijación con precisión sub-nanométrica.

---

## 5. Cinética de Transporte Difusivo y Estadística de Arribo de Poisson

En PyPrinting 3.0 no se requiere confinar previamente nanopartículas en una trampa 3D: el proceso opera mediante **captura probabilística estocástica en flujo browniano libre**.

```
       Suspensión Coloidal Diluida (C ~ 10^9 - 10^10 NP/mL)
       ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
            ○ (Difusión Browniana D = k_B T / 6πηa)
               \
                \     ┌───────────────┐  Volumen de Captura Óptica
                 └──► │ V_cap ~ 1 µm³ │  (F_scat > F_browniana)
                      └───────┬───────┘
                              ▼  Fijación instantánea en APTES (-NH3+)
```

### 5.1 Condición de Partícula Única (Ocupación Monomolecular)

La concentración coloidal se ajusta experimentalmente a $C \approx 5 \times 10^9\ \text{partículas/mL}$ ($8.3\ \text{pM}$). A esta dilución, el número medio de nanopartículas en el volumen focal difractivo ($V_{\text{focal}} \approx 1\ \mu\text{m}^3 = 10^{-12}\ \text{mL}$) es:

$$\langle N \rangle = C \cdot V_{\text{focal}} \approx 5 \times 10^{-3} \ll 1$$

La probabilidad de encontrar dos o más partículas simultáneamente dentro del cono de captura sigue la distribución de Poisson:

$$P(N \ge 2) = 1 - e^{-\langle N \rangle} - \langle N \rangle e^{-\langle N \rangle} \approx \frac{\langle N \rangle^2}{2} \approx \frac{(5 \times 10^{-3})^2}{2} \approx 1.25 \times 10^{-5}$$

Esto certifica que **más del $99.99\%$ de los eventos de impresión corresponden con certeza metrológica a una única nanopartícula aislada**.

### 5.2 Tiempo Medio de Espera ($\langle \tau_{\text{wait}} \rangle$) — Ley de Smoluchowski

El tiempo medio de difusión necesario para que una nanopartícula arribe al radio de captura óptica $R_{\text{cap}} \approx w_0 \approx 250\ \text{nm}$ por movimiento browniano puro sigue la teoría de Smoluchowski:

$$\langle \tau_{\text{wait}} \rangle = \frac{1}{4\pi D C R_{\text{cap}}}$$

donde el coeficiente de difusión de Einstein-Stokes para una nanoesfera de radio $a = 30\ \text{nm}$ en agua a $20\ ^\circ\text{C}$ ($\eta = 1.0 \times 10^{-3}\ \text{Pa}\cdot\text{s}$) es:

$$D = \frac{k_B T}{6\pi \eta a} \approx \frac{(1.38 \times 10^{-23}\ \text{J/K})(293\ \text{K})}{6\pi (1.0 \times 10^{-3}\ \text{Pa}\cdot\text{s})(30 \times 10^{-9}\ \text{m})} \approx 7.15 \times 10^{-12}\ \text{m}^2/\text{s}$$

Para la concentración estándar $C = 5 \times 10^9\ \text{NP/mL} = 5 \times 10^{15}\ \text{NP/m}^3$:

$$\langle \tau_{\text{wait}} \rangle = \frac{1}{4\pi (7.15 \times 10^{-12}) (5 \times 10^{15}) (250 \times 10^{-9})} \approx 8.9\ \text{segundos}$$

### 5.3 Justificación Analítica del Parámetro $T_{\text{max}} = 20.0\ \text{s}$

El valor predeterminado configurado en la GUI de PyPrinting 3.0 (`T_max = 20.0 s`) se seleccionó exactamente como:

$$T_{\text{max}} \approx 2.25 \times \langle \tau_{\text{wait}} \rangle$$

La probabilidad acumulada de éxito en la captura dentro de la ventana de espera es:

$$P(\text{captura} \le T_{\text{max}}) = 1 - \exp\left(-\frac{T_{\text{max}}}{\langle \tau_{\text{wait}} \rangle}\right) \approx 1 - e^{-2.25} \approx 0.894 \implies \mathbf{89.4\%}$$

Si transcurridos $20\ \text{s}$ no se detecta el escalón fotométrico de impresión en el fotodiodo, el sistema aborta el nodo por *timeout* y el pase de autocompletitud (*Healing Pass*) programa su reintento automático al final de la red.

---

## 6. Cinemática de Microscopía y Mapeo Optomecánico

### 6.1 Formulación Cinemática de Marcos de Referencia:
* **Marco del Laboratorio / Láser ($\mathcal{R}_{\text{lab}}$)**: El objetivo y el punto focal del láser $\mathbf{r}_{\text{laser}}$ son estacionarios en la mesa óptica. Al mover la platina piezoeléctrica Physik Instrumente $\mathbf{r}_{\text{stage}}(t)$, la muestra experimenta una trayectoria $\mathbf{r}_{\text{sample}}(t) = \mathbf{r}_{\text{stage}}(t)$. El punto de impacto relativo del láser sobre el sustrato se desplaza con velocidad:
  $$\mathbf{v}_{\text{laser}/\text{sample}} = -\mathbf{v}_{\text{stage}/\text{lab}} = -\frac{d\mathbf{r}_{\text{stage}}}{dt}$$
* **Marco de la Muestra ($\mathcal{R}_{\text{sample}}$)**: Solidario al portaobjetos con APTES. Describe las coordenadas intrínsecas de las nanopartículas impresas $(x_i, y_i)$, coincidente con las mediciones por AFM o SEM.

### 6.2 Correspondencia con la Cámara Réflex Canon EOS 500D:
* **Eje Horizontal de la Cámara ($+X_{\text{cam}}$, derecha)**: Mover el láser a la derecha en pantalla se logra desplazando la platina física en sentido negativo de su segundo canal ($\mathbf{v}_{\text{sample}} \propto -\hat{\mathbf{y}}_{\text{PI}}$), gobernado por el **Eje 2 de la platina PI E-517**.
* **Eje Vertical de la Cámara ($+Y_{\text{cam}}$, abajo)**: Mover el láser hacia abajo en pantalla se logra desplazando la platina en sentido positivo de su primer canal ($\mathbf{v}_{\text{sample}} \propto +\hat{\mathbf{x}}_{\text{PI}}$), gobernado por el **Eje 1 de la platina PI E-517**.
* **Eje Axial Óptico ($+Z_{\text{cam}}$, hacia el interior del fluido)**: Gobernado unívocamente por el **Eje 3 de la platina PI**.

### 6.3 Desacoplamiento Ergonómico en PyPrinting 3.0:
1. **`Legacy`**: Preserva la convención histórica del laboratorio ($X = \text{Eje 1 PI}, Y = \text{Eje 2 PI}$).
2. **`Laser Ref`**: Alinea las etiquetas con la percepción de la cámara ($Y_{\text{Vert}} = \text{Eje 1}, X_{\text{Horiz}} = \text{Eje 2}$), con coincidencia 1:1 en el widget interactivo de grilla.
3. **`Sample Ref`**: Adopta el marco solidario a la muestra ($Y_{\text{Muestra}} = \text{Eje 1}, X_{\text{Muestra}} = \text{Eje 2}$).

---

## 7. Tabla de Propiedades de Coloides Plasmónicos y Ligandos

| Coloide / Nanomaterial | Diámetro | Plasmón $\lambda_{\text{LSPR}}$ | Potencial $\zeta$ | Ligando Químico | Rol en PyPrinting 3.0 |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **AuNPs Citrato (Mat. 1)** | $60\ \text{nm}$ | $535\ \text{nm}$ | $-35\ \text{mV}$ (Negativo) | Citrato trisódico | Impresión estándar resonante 532 nm |
| **AgNPs Citrato (Mat. 2)** | $40\ \text{nm}$ | $410\ \text{nm}$ | $-40\ \text{mV}$ (Negativo) | Citrato trisódico | Dímeros híbridos Au-Ag y nanoantenas |
| **AuNPs Grandes (Mat. 3)** | $100\ \text{nm}$ | $570\ \text{nm}$ | $-30\ \text{mV}$ (Negativo) | Citrato / PVP | Resonadores plasmónicos de alta dispersión |
| **AuNPs CTAB (Positivas)** | $60\ \text{nm}$ | $540\ \text{nm}$ | $+45\ \text{mV}$ (Positivo) | Bromuro de cetiltrimetilamonio | Requiere sustrato sin tratar ($\text{Si-O}^-$) |

---

## 8. Modos de Falla Fisicoquímica y Acciones Correctivas

| Condición Anómala | Firma Experimental en el Setup | Acción Correctiva Inmediata |
| :--- | :--- | :--- |
| **Desorción o Vencimiento del Silano APTES** | La partícula colisiona en el foco (salto en fotodiodo), pero rebota y no se fija al apagar el láser. | Descartar el cubreobjetos. Realizar limpieza Piranha fresca a $80\ ^\circ\text{C}$ y resilanizar con APTES al $1\%$ por $30\ \text{min}$. |
| **Concentración Coloidal Excesiva ($C > 10^{11}$)** | Múltiples escalones sucesivos en $< 500\ \text{ms}$; formación de agregados multímeros en confocal. | Diluir la suspensión coloidal con agua Milli-Q (factor $1:100$) hasta alcanzar $C \sim 5 \times 10^9\ \text{NP/mL}$. |
| **Fuerza Iónica Excesiva ($I_s > 100\ \text{mM}$)** | Adsorción inespecífica espontánea sobre todo el sustrato sin irradiación láser previa. | Disminuir la concentración salina; utilizar agua Milli-Q desionizada ($18.2\ \text{M}\Omega\cdot\text{cm}$) como solvente. |

---

## 9. Referencias Bibliográficas Fundacionales

1. **Gargiulo, Julián** (2017). *Impresión óptica de nanopartículas metálicas*. Tesis Doctoral, FCEN-UBA / CIBION-CONICET. Capítulo 3.
2. **Martínez, Luciana** (2019). *Impresión óptica de nanopartículas y nanoestructuras: ensamblado guiado, nanotermometría y plasmónica*. Tesis Doctoral, INS-UNSAM / CONICET. Capítulo 2.
3. **Israelachvili, J. N.** (2011). *Intermolecular and Surface Forces*. Academic Press (3rd Edition).
4. **Verwey, E. J. W., & Overbeek, J. T. G.** (1948). *Theory of the Stability of Lyophobic Colloids*. Elsevier.
5. **Smoluchowski, M.** (1917). *Versuch einer mathematischen Theorie der Koagulationskinetik kolloider Lösungen*. Zeitschrift für physikalische Chemie, 92, 129–168.
