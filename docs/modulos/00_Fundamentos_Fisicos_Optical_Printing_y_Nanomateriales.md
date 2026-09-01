# 🔬 Fundamentos Físicos, Nanomateriales y Mecanismos de Optical Printing

**Suite PyPrinting 3.0 — Laboratorio de Nanofotónica (INS-UNSAM / CONICET)**  
*Documento de Referencia Técnica y Teórica N° 00*  
*Autor: José Luis González Peñafiel (Becario Doctoral CONICET)*  
*Ubicación*: `docs/modulos/00_Fundamentos_Fisicos_Optical_Printing_y_Nanomateriales.md`

---

## 📖 Índice del Documento
1. [Electrodinámica de Pinzas Ópticas y Fuerzas de Radiación de Presión](#1-electrodinámica-de-pinzas-ópticas-y-fuerzas-de-radiación-de-presión)
   - 1.1 Régimen de Rayleigh vs. Régimen de Mie
   - 1.2 Polarizabilidad Compleja y Resonancia Plasmónica Localizada (LSPR)
   - 1.3 Separación Vectorial: Fuerza de Gradiente vs. Fuerza de Dispersión / Absorción
2. [Termoplasmónica y Fenómenos Térmicos en la Nanoescala](#2-termoplasmónica-y-fenómenos-térmicos-en-la-nanoescala)
   - 2.1 Disipación de Calor y Ecuación de Difusión Estacionaria
   - 2.2 Termoforesis Coloidal y Convección de Marangoni
   - 2.3 Umbral Crítico de Cavitación por Microburbujas
3. [Química de Superficies, Potencial Electrocinético y Teoría DLVO](#3-química-de-superficies-potencial-electrocinético-y-teoría-dlvo)
   - 3.1 Doble Capa Eléctrica y Longitud de Apantallamiento de Debye
   - 3.2 Funcionalización del Sustrato (Limpieza Piranha, Silanización con APTES, Polilisina)
   - 3.3 Coloides Plasmónicos: Nanopartículas de Oro (AuNPs), Plata (AgNPs) y Ligandos (CTAB, Citrato)
4. [Mecanismos de Impresión Óptica (*Optical Printing*) vs. Trampa 3D Estacionaria](#4-mecanismos-de-impresión-óptica-optical-printing-vs-trampa-3d-estacionaria)
   - 4.1 Eyección Fototérmica Dirigida hacia el Sustrato
   - 4.2 Atrapamiento Irreversible en el Pozo de Van der Waals
   - 4.3 Nanodímeros Plasmónicos, Hibridación de Modos y *Hot Spots* de Campo Cercano
5. [Tabla Maestra de Propiedades Físicas de Nanomateriales y Parámetros del Setup](#5-tabla-maestra-de-propiedades-físicas-de-nanomateriales-y-parámetros-del-setup)

---

## 1. Electrodinámica de Pinzas Ópticas y Fuerzas de Radiación de Presión

Las pinzas ópticas y la nanofabricación por *Optical Printing* se basan en la transferencia de momento lineal entre fotones de un haz láser fuertemente enfocado y una nanopartícula dieléctrica o metálica suspendida en un medio fluido (típicamente agua, $n_m = 1.333$).

```
               Haz Láser Enfocado (Gaussiano TEM00)
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

### 1.1 Régimen de Rayleigh vs. Régimen de Mie
Dependiendo de la relación entre el diámetro de la partícula ($2R$) y la longitud de onda de la radiación incidente en el medio ($\lambda_m = \lambda_0 / n_m$):

- **Régimen de Rayleigh ($2R \ll \lambda_m$, típicamente $2R < 100\ \text{nm}$)**:
  La partícula experimenta un campo eléctrico espacialmente uniforme en su volumen en cada instante de tiempo. Se modela rigurosamente como un **dipolo puntual inducido** de momento dipolar $\mathbf{p}(t) = \epsilon_0 \epsilon_m \alpha(\omega) \mathbf{E}_0 e^{-i\omega t}$.
- **Régimen de Mie ($2R \sim \lambda_m$ o $2R > \lambda_m$)**:
  Aparecen efectos de retardo de fase electromagnética y multipolos de orden superior (cuadrupolos, octupolos magnéticos y eléctricos). Requiere la solución analítica exacta de las ecuaciones de Maxwell con condiciones de contorno esféricas.

En **PyPrinting 3.0**, las partículas estándar de trabajo (AuNPs de $60\ \text{nm}$, $80\ \text{nm}$, $100\ \text{nm}$ y AgNPs de $40\ \text{nm}$) operan en el límite de Rayleigh con correcciones por dispersión de radiación (*Radiation Reaction Correction*).

---

### 1.2 Polarizabilidad Compleja y Resonancia Plasmónica Localizada (LSPR)

La polarizabilidad dipolar electrostática de una esfera metálica de radio $R$ con permitividad dieléctrica compleja $\epsilon_p(\omega) = \epsilon_p'(\omega) + i\epsilon_p''(\omega)$ inmersa en un dieléctrico de permitividad $\epsilon_m = n_m^2$ está dada por:

$$\alpha_0(\omega) = 4\pi R^3 \frac{\epsilon_p(\omega) - \epsilon_m}{\epsilon_p(\omega) + 2\epsilon_m}$$

Incluyendo la corrección de reacción de radiación de segundo orden (fundamental para metales con fuerte dispersión):

$$\alpha(\omega) = \frac{\alpha_0(\omega)}{1 - i \frac{k_m^3}{6\pi} \alpha_0(\omega)}$$

donde $k_m = \frac{2\pi n_m}{\lambda_0}$ es el vector de onda en el medio.

#### Condición de Fröhlich y Resonancia Plasmónica (LSPR):
La resonancia dipolar plasmónica ocurre cuando el denominador de $\alpha_0$ se minimiza:

$$\text{Re}\{\epsilon_p(\omega_{\text{LSPR}})\} = -2\epsilon_m = -2 n_m^2 \approx -2(1.333)^2 = -3.55$$

- **Oro (Au)**: $\lambda_{\text{LSPR}} \approx 530 - 550\ \text{nm}$ (en agua). El láser verde de **$532\ \text{nm}$** excita de forma casi resonante el plasmón, generando una absorción óptica gigantesca ($\sigma_{\text{abs}} \gg \sigma_{\text{scat}}$) ideal para **impresión fototérmica rápida**.
- **Plata (Ag)**: $\lambda_{\text{LSPR}} \approx 405 - 420\ \text{nm}$. A $532\ \text{nm}$ se encuentra en el ala no resonante con menor absorción y alta dispersión.
- **Láser IR ($808\ \text{nm}$ / $1064\ \text{nm}$)**: Muy alejado del LSPR del oro esférico. La absorción es baja ($\epsilon_p''$ bajo), predominando el atrapamiento conservativo estable sin sobrecalentamiento.

---

### 1.3 Separación Vectorial: Fuerza de Gradiente vs. Fuerza de Dispersión / Absorción

La fuerza óptica total promediada en el tiempo $\langle \mathbf{F} \rangle$ sobre la nanopartícula se descompone rígidamente en dos contribuciones físicas ortogonales:

$$\langle \mathbf{F} \rangle = \mathbf{F}_{\text{grad}} + \mathbf{F}_{\text{scat}} + \mathbf{F}_{\text{abs}}$$

#### 1. Fuerza de Gradiente ($\mathbf{F}_{\text{grad}}$ — Fuerza Conservativa):
Proviene de la interacción del dipolo inducido en fase con el gradiente de intensidad del campo electromagnético. Atrae partículas dieléctricas de alto índice o nanopartículas metálicas (por debajo de resonancia) hacia el punto de máxima intensidad (foco láser):

$$\mathbf{F}_{\text{grad}} = \frac{1}{4} \epsilon_0 \epsilon_m \text{Re}\{\alpha(\omega)\} \nabla |\mathbf{E}(\mathbf{r})|^2$$

Para un haz Gaussiano enfocado con cintura $w_0$:
$$I(r, z) = I_0 \left(\frac{w_0}{w(z)}\right)^2 \exp\left(-\frac{2r^2}{w(z)^2}\right)$$
La fuerza lateral restaura la partícula hacia el centro del haz como un resorte óptico lineal: $F_{\text{grad}, r} \approx -\kappa_{\text{trap}} r$.

#### 2. Fuerza de Dispersión y Absorción ($\mathbf{F}_{\text{scat+abs}}$ — Fuerza No Conservativa / Presión de Radiación):
Proviene de la transferencia directa de momento fotónico debida a la extinción óptica total ($\sigma_{\text{ext}} = \sigma_{\text{abs}} + \sigma_{\text{scat}}$). Empuja la partícula a lo largo de la dirección de propagación del haz ($\hat{\mathbf{z}}$):

$$\mathbf{F}_{\text{scat+abs}} = \frac{n_m}{c} \sigma_{\text{ext}}(\omega) \langle \mathbf{S}(\mathbf{r}) \rangle = \frac{n_m}{c} \left( \sigma_{\text{abs}} + \sigma_{\text{scat}} \right) I(\mathbf{r}) \hat{\mathbf{z}}$$

donde $\langle \mathbf{S} \rangle$ es el vector de Poynting y las secciones eficaces son:
$$\sigma_{\text{abs}}(\omega) = k_m \text{Im}\{\alpha(\omega)\}, \quad \sigma_{\text{scat}}(\omega) = \frac{k_m^4}{6\pi} |\alpha(\omega)|^2$$

> [!IMPORTANT]
> **El Secreto del Optical Printing**: En un microscopio convencional de pinzas ópticas 3D, se requiere que $F_{\text{grad}, z} > F_{\text{scat}, z}$ para atrapar en 3D en el foco. En **Optical Printing**, se utiliza un haz enfocado hacia abajo (o con alta absorción $\sigma_{\text{abs}}$ resonante), de modo que la fuerza de presión de radiación $\mathbf{F}_{\text{scat+abs}}$ domina axialmente y **empuja activamente la nanopartícula hacia el sustrato de vidrio inferior**, logrando la deposición y fijación en milisegundos.

---

## 2. Termoplasmónica y Fenómenos Térmicos en la Nanoescala

Cuando una nanopartícula de oro coloidal de $60\ \text{nm}$ es iluminada a $\lambda = 532\ \text{nm}$ con una irradiancia focal $I_0 \sim 1 - 10\ \text{mW}/\mu\text{m}^2$, los electrones de la banda de conducción oscilan colectivamente y decaen de forma no radiativa mediante dispersión electrón-electrón ($100\ \text{fs}$) y electrón-fonón ($1 - 5\ \text{ps}$), convirtiendo casi el 100% de la energía luminosa absorbida en calor localizado.

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

### 2.1 Disipación de Calor y Ecuación de Difusión Estacionaria
La potencia térmica total generada por la partícula es $Q = \sigma_{\text{abs}} I_0$. La temperatura en el fluido a una distancia $r \ge R$ del centro de la partícula sigue la solución esférica de la ecuación de Fourier en régimen estacionario ($\nabla^2 T = 0$):

$$\Delta T(r) = T(r) - T_\infty = \frac{\sigma_{\text{abs}} I_0}{4\pi \kappa_{\text{medio}} r} \quad (r \ge R)$$

En la superficie de la partícula ($r = R$):
$$\Delta T_{\text{NP}} = \frac{\sigma_{\text{abs}} I_0}{4\pi \kappa_{\text{medio}} R}$$

Para agua ($\kappa_{\text{medio}} = 0.6\ \text{W}/(\text{m}\cdot\text{K})$), una AuNP de $60\ \text{nm}$ con $I_0 = 5\ \text{mW}/\mu\text{m}^2$ alcanza un $\Delta T_{\text{NP}} \approx 40 - 120\ ^\circ\text{C}$ en régimen estacionario (que se establece en menos de $10\ \text{ns}$).

---

### 2.2 Termoforesis Coloidal y Convección de Marangoni

El gradiente térmico extremo ($\nabla T \sim 10^8\ \text{K}/\text{m}$) en las proximidades del foco láser altera la hidrodinámica del fluido:

1. **Termoforesis (Efecto Soret)**:
   Las partículas suspendidas en la solución experimentan una fuerza termodependiente proporcional al gradiente térmico:
   $$\mathbf{v}_T = -D_T \nabla T = -D_0 S_T \nabla T$$
   donde $S_T = D_T / D_0$ es el coeficiente de Soret. Para AuNPs estabilizadas por citrato o CTAB, $S_T > 0$ (termófobas), lo que tiende a expulsar partículas vecinas del núcleo súper caliente, evitando la agregación descontrolada de múltiples partículas durante el disparo láser.
2. **Fuerzas Termoeléctricas**:
   Los iones del electrolito (e.g., $\text{Na}^+$, $\text{Cl}^-$, $\text{CTA}^+$) tienen diferentes coeficientes de Seebeck térmico. Esto genera un campo eléctrico macroscópico inducido por calor $\mathbf{E}_{\text{termo}} = S_{\text{ión}} \nabla T$ que confina o repele iones alrededor del foco.

---

### 2.3 Umbral Crítico de Cavitación por Microburbujas

Si la potencia láser supera el límite de sobrecalentamiento spinodal del agua ($T_{\text{spinodal}} \approx 280 - 300\ ^\circ\text{C}$):
1. Se produce una nucleación explosiva de vapor de agua alrededor de la nanopartícula.
2. Se forma una **microburbuja plasmónica de vapor**.
3. La tensión superficial en la interfaz líquido-gas genera un flujo de convección Marangoni ultra-rápido ($\mathbf{u} \propto \nabla \gamma_{\text{LV}}$) que succiona violentamente partículas coloidales masivas y las colapsa en el sustrato.

> [!CAUTION]
> **Riesgo Experimental de Cavitación**:
> Si en el software **PyPrinting 3.0** se observa una caída abrupta a cero en la señal de fotodiodo o un salto gigantesco no reversible en la traza temporal con deformación visual en la cámara réflex, se ha sobrepasado el umbral de cavitación. La burbuja puede arrancar el recubrimiento de silano y degradar la calidad del objetivo. Reducir de inmediato la potencia del láser 532 nm (ajustar spinner de voltaje AO2 a $< 1.5\ \text{V}$).

---

## 3. Química de Superficies, Potencial Electrocinético y Teoría DLVO

El éxito de la inmovilización espacial sub-nanométrica depende del balance fisicoquímico entre la superficie de la nanopartícula y el sustrato de vidrio.

```
       Potencial V(D)
          ▲
          │           Barrera Electrostática E_b (Repulsión)
          │                ╭───────╮
          │               ╭╯       ╰───────────────  D (Distancia)
          │  ────────────╯────────────────────────►
          │             │
          │             │
          │             ▼
          │      Pozo Primario Van der Waals (Fijación Irreversible, prof > 100 k_B T)
```

### 3.1 Doble Capa Eléctrica y Longitud de Apantallamiento de Debye

Cuando un coloide se suspende en solución acuosa, las cargas superficiales atraen contraiones formando la **doble capa eléctrica (EDL)** de Stern y Gouy-Chapman. La escala de decaimiento del potencial electrostático viene dada por la **longitud de Debye ($\kappa_D^{-1}$)**:

$$\kappa_D^{-1} = \sqrt{\frac{\epsilon_0 \epsilon_r k_B T}{2 e^2 I_s}}$$

donde $I_s = \frac{1}{2} \sum c_i z_i^2$ es la fuerza iónica del medio.
- En agua ultra-pura Milli-Q ($I_s \sim 10^{-5}\ \text{M}$): $\kappa_D^{-1} \approx 100\ \text{nm}$ (repulsión de largo alcance).
- En medio salino moderado ($I_s \sim 1\ \text{mM}$): $\kappa_D^{-1} \approx 9.6\ \text{nm}$.
- En medio de alta salinidad ($I_s \sim 100\ \text{mM}$): $\kappa_D^{-1} \approx 0.96\ \text{nm}$ (el apantallamiento permite contacto íntimo).

---

### 3.2 Funcionalización del Sustrato (Limpieza Piranha, Silanización con APTES, Polilisina)

El vidrio portaobjetos desnudo posee grupos silanol superficiales ($\text{Si-OH}$) que en agua neutra ($\text{pH} \approx 6.5 - 7.0$) se desprotonan a silanoato ($\text{Si-O}^-$), confiriéndole un potencial Zeta negativo ($\zeta_{\text{vidrio}} \approx -40\ \text{a} -70\ \text{mV}$).

```
[Vidrio Puro (Negativo)] ──► [Silanización APTES] ──► [Superficie Positiva (-NH3+)]
   ─Si─O⁻                      ─Si─O─Si─(CH2)3─NH3⁺             ▲
   ─Si─O⁻                      ─Si─O─Si─(CH2)3─NH3⁺             │ Atrae AuNP-Citrato (-)
```

#### Métodos de Modificación:
1. **Silanización con APTES (3-Aminopropiltrietoxisilano)**:
   - Los grupos etoxi ($\text{-O-CH}_2\text{CH}_3$) reaccionan con los silanoles del vidrio formando enlaces covalentes $\text{Si-O-Si}$.
   - Expone grupos amino terminales ($\text{-NH}_2$) que en agua se protonan a **$\text{-NH}_3^+$**, invirtiendo el potencial de superficie a **$\zeta \approx +30\ \text{a} +50\ \text{mV}$**.
   - **Mecanismo de Fijación**: Atrae con extrema fuerza electrostática a las nanopartículas de oro sintetizadas por método de Turkevich (estabilizadas con citrato, con carga fuertemente negativa $\zeta_{\text{NP}} \approx -35\ \text{mV}$).
2. **Recubrimiento con Poli-L-Lisina (PLL)**:
   - Polímero policatiónico que se adsorbe físicamente en el vidrio creando una película de alta densidad de carga positiva.
3. **Sustratos Pasivados con PEG (Polietilenglicol)**:
   - Utilizados para evitar la adsorción inespecífica cuando se imprimen coloides funcionalizados con biomoléculas (ADN, anticuerpos).

---

### 3.3 Coloides Plasmónicos: Nanopartículas de Oro (AuNPs), Plata (AgNPs) y Ligandos

| Coloide / Nanomaterial | Diámetro Típico | Plasmón $\lambda_{\text{LSPR}}$ | Carga Superficial ($\zeta$) | Ligando / Estabilizante | Uso en PyPrinting 3.0 |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **AuNPs Citrato (Material 1)** | $60\ \text{nm}$ | $535\ \text{nm}$ | $-35\ \text{mV}$ (Negativa) | Citrato trisódico | Impresión resonante estándar (532 nm) |
| **AgNPs Citrato (Material 2)** | $40\ \text{nm}$ | $410\ \text{nm}$ | $-40\ \text{mV}$ (Negativa) | Citrato | Dímeros híbridos Au-Ag y nanoantenas |
| **AuNPs Grandes (Material 3)** | $100\ \text{nm}$ | $570\ \text{nm}$ | $-30\ \text{mV}$ (Negativa) | Citrato / PVP | Resonadores plasmónicos de alta dispersión |
| **AuNPs CTAB (Positivas)** | $60\ \text{nm}$ | $540\ \text{nm}$ | $+45\ \text{mV}$ (Positiva) | Bromuro de cetiltrimetilamonio | Requiere sustrato de vidrio sin tratar ($\text{Si-O}^-$) |

---

## 4. Mecanismos de Impresión Óptica (*Optical Printing*) vs. Trampa 3D

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SECUENCIA TEMPORAL DE UN EVENTO DE IMPRESIÓN              │
│                                                                             │
│  1. Difusión Browniana   2. Captura Óptica       3. Colisión & Fijación     │
│     (Obturador Abierto)     (F_scat hacia abajo)    (Fijación Van der Waals) │
│                                                                             │
│         O (AuNP libre)          │                        │                  │
│          \                      │                        │                  │
│           \                     ▼ F_scat                 ▼                  │
│  ──────────\────────────────────●────────────────────────█────────────────  │
│             Sustrato Funcionalizado (APTES -NH3+)        Impresión Éxito    │
│                                                                             │
│  Traza Fotodiodo:                                                           │
│  Voltaje ▲                          Salto Abrupto (Escalón)                 │
│          │  Ruido Base              ┌─────────────────────────────────────  │
│          │ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─│  Nivel Post-Impresión (Dispersión)    │
│          └──────────────────────────┴────────────────────────────────────► t│
│                                   Disparo Criterio Parada (Cierre Shutter)  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.1 Eyección Fototérmica Dirigida hacia el Sustrato
1. Una nanopartícula en movimiento Browniano entra en el cono de luz enfocado por el objetivo de alta apertura numérica ($\text{NA} \ge 1.0$).
2. Al ingresar en la región de alta intensidad, la **fuerza de gradiente lateral $\mathbf{F}_{\text{grad}, r}$** tira de la partícula hacia el eje óptico central ($r=0$).
3. Simultáneamente, la **fuerza de dispersión y absorción $\mathbf{F}_{\text{scat+abs}}$** empuja la partícula a alta velocidad ($v_z \sim 100\ \mu\text{m}/\text{s} - 1\ \text{mm}/\text{s}$) directamente contra el cubreobjetos.

### 4.2 Atrapamiento Irreversible en el Pozo de Van der Waals
A distancias sub-nanométricas ($D < 1\ \text{nm}$):
1. La fuerza electrostática atractiva (entre el citrato negativo de la AuNP y los grupos $-\text{NH}_3^+$ del APTES) supera la barrera hidrodinámica.
2. La partícula cae en el **pozo potencial primario de Van der Waals**, cuya profundidad energética supera $100 - 1000\ k_B T$.
3. La inmovilización es **termodinámicamente irreversible**: la partícula queda permanentemente soldada al vidrio en la posición exacta $(x, y)$ donde incidió el haz, incluso después de cerrar el obturador láser.

---

### 4.3 Nanodímeros Plasmónicos, Hibridación de Modos y *Hot Spots*

Cuando se imprime una segunda nanopartícula (Partícula B) a una distancia controlada $s \sim 1 - 20\ \text{nm}$ de una primera nanopartícula fija (Partícula A), los plasmones de superficie de ambas partículas se acoplan fuertemente por interacción dipolar de campo cercano (Teoría de Hibridación Plasmónica):

```
       Partícula A              Gap (s)             Partícula B
      ┌───────────┐          ◄─────────►          ┌───────────┐
      │   AuNP    │          ░░░░░░░░░░░          │   AuNP    │
      │  (Fija)   │          ░░ HOT SPOT ░        │ (Impresa) │
      │  ( +  - ) │          ░░ E^2 > 10³░        │  ( +  - ) │
      └───────────┘          ░░░░░░░░░░░          └───────────┘
```

1. **Modo Enlazante Dipolar ($\omega_-$)**:
   Las oscilaciones de carga en ambas esferas están en fase $(+- \quad +-)$. El campo eléctrico en el gap interparticular se amplifica en órdenes de magnitud ($|\mathbf{E}/\mathbf{E}_0|^2 > 10^3 - 10^5$), creando un **Hot Spot plasmónico** de confinamiento sub-difracción.
2. **Desplazamiento Espectral al Rojo (Redshift)**:
   A medida que la distancia interparticular $s$ disminuye, la longitud de onda de resonancia LSPR del dímero experimenta un corrimiento espectral hacia el infrarrojo ($\Delta \lambda \propto \exp(-s / 0.2 R)$), observable directamente en tiempo real con el módulo **PySpectrum 3.0**.
3. **Aplicaciones**: Espectroscopía Raman Amplificada por Superficie (SERS monomolecular), nanoantenas emisoras de fotón único, catálisis plasmónica y detección de birrefringencia óptica.

---

## 5. Tabla Maestra de Propiedades Físicas de Nanomateriales y Parámetros del Setup

| Parámetro Físico | Símbolo | Valor Típico en Setup PyPrinting | Unidades | Significado e Impacto Experimental |
| :--- | :---: | :---: | :---: | :--- |
| **Longitud de Onda Láser Impresión** | $\lambda_0$ | $532.0$ | $\text{nm}$ | Láser verde resonante con LSPR de AuNPs |
| **Longitud de Onda Láser Atrapamiento IR** | $\lambda_{\text{IR}}$ | $808.0\ \text{o}\ 1064.0$ | $\text{nm}$ | Pinzas ópticas no resonantes (bajo calentamiento) |
| **Apertura Numérica del Objetivo** | $\text{NA}$ | $1.40\ \text{o}\ 1.49$ | Adimensional | $\text{NA} = n \sin\theta$; determina el foco Airy $w_0 \approx 0.61\lambda/\text{NA}$ |
| **Índice Aceite de Inmersión** | $n_{\text{oil}}$ | $1.518$ | Adimensional | Emparejado con cubreobjetos de vidrio borosilicato ($n=1.52$) |
| **Índice Medio Acuoso** | $n_m$ | $1.333$ | Adimensional | Medio de suspensión coloidal Milli-Q |
| **Cintura del Haz Focal** | $w_0$ | $\approx 230 - 260$ | $\text{nm}$ | Radio $1/e^2$ de intensidad del foco difractivo |
| **Potencia Óptica en Muestra** | $P_{\text{sample}}$ | $0.5 - 15.0$ | $\text{mW}$ | Controlada por voltaje analógico AO2 ($0-5\ \text{V}$) en NI-DAQmx |
| **Sección Eficaz de Absorción Au 60nm**| $\sigma_{\text{abs}}$ | $\approx 3.5 \times 10^{-15}$ | $\text{m}^2$ | Determina la velocidad de conversión fototérmica |
| **Sección Eficaz de Dispersión Au 60nm**| $\sigma_{\text{scat}}$ | $\approx 4.0 \times 10^{-16}$ | $\text{m}^2$ | Determina el salto de fotodiodo en el criterio de parada |
| **Fuerza Óptica Axial Típica** | $F_z$ | $5 - 80$ | $\text{pN}$ | Empuje vertical hacia el sustrato de vidrio |
| **Tiempo de Tránsito y Fijación** | $\tau_{\text{print}}$ | $2 - 50$ | $\text{ms}$ | Tiempo transcurrido desde captura hasta soldadura |
| **Rigidez de Trampa Lateral** | $\kappa_{\text{trap}}$ | $0.05 - 0.50$ | $\text{pN}/(\text{nm}\cdot\text{mW})$ | Determina la precisión de posicionamiento lateral $(\sigma_{xy} < 10\ \text{nm})$ |
