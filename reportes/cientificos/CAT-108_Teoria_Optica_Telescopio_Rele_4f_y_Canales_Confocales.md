# CAT-108: Teoría Óptica del Telescopio Relé 4f, Acoplamiento de Etendue y Canales Confocales 🔬

**PyPrinting 3.0 — Suite de Nanofabricación, Microscopía Confocal y Espectroscopía Plasmónica**  
**Laboratorio de Nanofotónica — Instituto de Nanosistemas (INS-UNSAM / CONICET)**  
**Autor Principal:** José Luis González Peñafiel (*Becario Doctoral CONICET*)  
**Código de Catalogación:** `CAT-108` | **Eje Temático:** `[FIS]` (Física Teórica y Óptica de Fourier)  
**Fecha de Emisión:** Septiembre 2026 | **Estado:** Documento Maestro de Referencia Óptica

---

## 🔗 Matriz de Referencias Cruzadas

- **Documentos Científicos Relacionados (Pilar I y II):**
  - `[[CAT-101_Protocolo_Operativo_Impresion_Fototermica_Grillas_2D]]`: Protocolo experimental y acoplamiento de haz de impresión 532 nm.
  - `[[CAT-103_Control_Lazo_Cerrado_Fototermico_y_Sintesis_Dimeros]]`: Criterio de parada fototérmica y monitoreo confocal multicanal.
  - `[[CAT-107_Cinetica_Captura_Fotodiodo_Time_Volt_Filtro_Nhold]]`: Dinámica de respuesta temporal y señales de fotodiodo.
  - `[[CAT-202_Derivacion_Matematica_Cota_Cramer_Rao_Localizacion_Optica]]`: Cota CRLB para perfiles Gaussiano fundamental y haz vórtice Donut $LG_{01}$.
  - `[[CAT-203_Presupuesto_Incertidumbre_Metrologica_ISOGUM_Microscopia]]`: Balances de incertidumbre experimental Tipo A/B con pinholes de $0.46\,AU$.
- **Reportes de Sistema e Instrumentación Asociados:**
  - `[[SYS-305_Arquitectura_Optomecanica_Microscopio_Derecho_y_Ruteo_Espectral]]`: Layout optomecánico del banco, torreta de 5 objetivos y cableado NI-DAQmx.
  - `[[SYS-204_Modulo_Camara_Canon_EDSDK_y_Buffer_RAM]]`: Proyección física sobre el sensor CMOS APS-C y control EDSDK.
  - `[[SYS-301_Sistema_Espectrometro_Shamrock500i_iXon3]]`: Espectrógrafo Shamrock 500i y detector iXon3 EMCCD.

---

## 1. 📋 Resumen y Fundamento Físico

El presente informe constituye la **formulación analítica rigurosa y modelo ondulatorio/difractivo** de la cadena óptica del Microscopio Derecho del Laboratorio de Nanofotónica (INS-UNSAM).

A partir de las ecuaciones fundamentales de Maxwell y la óptica de Fourier, se derivan:
1. **El operador de transferencia matricial $ABCD$ del telescopio relé intermedio $4f$** ($f_1 = 250\ \text{mm} \to f_2 = 200\ \text{mm}$), que introduce una magnificación intrínseca $\Gamma = 1.25\times$.
2. **Los límites de resolución difractiva lateral (Abbe y Rayleigh) y axial (profundidad de foco y espesor confocal FWHM)** para los 5 objetivos del microscopio a través del espectro visible e infrarrojo cercano ($532, 592, 637, 808\ \text{nm}$).
3. **El diámetro del disco de Airy proyectado sobre los pinholes espaciales** ($50\ \mu\text{m}$ y $100\ \mu\text{m}$), la función de transmisión analítica de Bessel $T(v_p) = 1 - J_0^2(v_p) - J_1^2(v_p)$ y la definición del régimen super-confocal ($AU < 1.0$).
4. **La proyección de imagen sobre el sensor CMOS Canon EOS 500D**, demostrando el cumplimiento incondicional del Criterio de Nyquist-Shannon con sobremuestreo sub-píxel ($> 2.9\times$).
5. **El balance de apertura numérica ($f/\#$-matching y conservación de etendue)** entre el cono colimado del microscopio y la apertura geométrica de entrada ($f/9.7$) del espectrógrafo Andor Shamrock 500i, certificando la ausencia absoluta de viñeteo (*underfilling condition*).
6. **El principio físico de microscopía iSCAT (Interferometric Scattering)**, demostrando la ganancia cuántica interferométrica homodina que escala con el volumen ($\Delta I \propto d^3$) en contraste con la dispersión elástica pura de Rayleigh ($\propto d^6$).
7. **Los modelos analíticos de Función de Dispersión de Punto (PSF)**: Gaussiano bidimensional anisótropo con ángulo de rotación $\theta$ y haz vórtice óptico Laguerre-Gauss $LG_{01}$ (Donut).

---

## 2. 📐 Matriz de Transferencia $ABCD$ del Tren de Relé Intermedio $4f$

En microscopía óptica moderna con objetivos corregidos a infinito, la imagen primaria se forma en el plano focal posterior de una lente de tubo. En la estación del Microscopio Derecho, el espacio físico entre el revólver de objetivos y los detectores finales aloja un telescopio relé intermedio para inyección y extracción de haces.

```
 Plano Muestra        Objetivo             Lente L1               Plano Intermedio              Lente L2              Haz Colimado
   [ Muestra ] ───► [ f_obj ] ───(inf)───► [ f1=250mm ] ───(f1)───► [ Foco Int ] ───(f2)───► [ f2=200mm ] ───(inf)───► [ Beamsplitter ]
```

El tren óptico post-objetivo consta de:
- Una primera lente intermedia $L_1$ con distancia focal $f_1 = 250\ \text{mm}$, que enfoca el haz colimado del objetivo en un plano focal intermedio.
- Una segunda lente colimadora $L_2$ con distancia focal $f_2 = 200\ \text{mm}$, colocada a distancia $f_1 + f_2 = 450\ \text{mm}$ de $L_1$, que re-colima el haz hacia el espacio infinito donde se ubican el Beamsplitter (BS), los filtros dicroicos y el conmutador Flipper.

### 2.1 Deducción Matricial $ABCD$

La matriz de transferencia de rayos paraxiales $\mathbf{M}_{\text{rele}}$ entre el plano anterior de $L_1$ y el plano posterior de $L_2$ (separados por la distancia $d = f_1 + f_2$) se calcula mediante el producto:

$$\mathbf{M}_{\text{rele}} = \begin{pmatrix} 1 & 0 \\ -\frac{1}{f_2} & 1 \end{pmatrix} \begin{pmatrix} 1 & f_1 + f_2 \\ 0 & 1 \end{pmatrix} \begin{pmatrix} 1 & 0 \\ -\frac{1}{f_1} & 1 \end{pmatrix}$$

Multiplicando las matrices intermedias:

$$\begin{pmatrix} 1 & f_1 + f_2 \\ 0 & 1 \end{pmatrix} \begin{pmatrix} 1 & 0 \\ -\frac{1}{f_1} & 1 \end{pmatrix} = \begin{pmatrix} 1 - \frac{f_1 + f_2}{f_1} & f_1 + f_2 \\ -\frac{1}{f_1} & 1 \end{pmatrix} = \begin{pmatrix} -\frac{f_2}{f_1} & f_1 + f_2 \\ -\frac{1}{f_1} & 1 \end{pmatrix}$$

Multiplicando por la matriz de refracción de $L_2$:

$$\mathbf{M}_{\text{rele}} = \begin{pmatrix} 1 & 0 \\ -\frac{1}{f_2} & 1 \end{pmatrix} \begin{pmatrix} -\frac{f_2}{f_1} & f_1 + f_2 \\ -\frac{1}{f_1} & 1 \end{pmatrix} = \begin{pmatrix} -\frac{f_2}{f_1} & f_1 + f_2 \\ \frac{1}{f_1} - \frac{1}{f_1} & -\frac{f_1 + f_2}{f_2} + 1 \end{pmatrix} = \begin{pmatrix} -\frac{f_2}{f_1} & f_1 + f_2 \\ 0 & -\frac{f_1}{f_2} \end{pmatrix}$$

Sustituyendo los valores focales $f_1 = 250\ \text{mm}$ y $f_2 = 200\ \text{mm}$:

$$\frac{f_2}{f_1} = \frac{200}{250} = 0.80, \quad \frac{f_1}{f_2} = \frac{250}{200} = 1.25$$

$$\mathbf{M}_{\text{rele}} = \begin{pmatrix} -0.80 & 450\ \text{mm} \\ 0 & -1.25 \end{pmatrix}$$

El elemento $C = 0$ certifica que el sistema es **afocal**: rayos paralelos a la entrada emergen colimados a la salida.  
El elemento angular $D = -f_1 / f_2 = -1.25$ determina que los ángulos de los rayos se amplifican en un factor $1.25\times$, lo que por conservación de etendue contrae el diámetro de haz colimado en un factor inverso:

$$D_{\text{haz, salida}} = D_{\text{haz, entrada}} \times \left( \frac{f_2}{f_1} \right) = 0.80 \times D_{\text{haz, entrada}}$$

### 2.2 Aumento Lateral Efectivo Total ($M_{\text{eff}}$)

Para cualquier subsistema de detección dotado de una lente focalizadora final $f_{\text{final}}$, el aumento lateral total respecto al plano de la muestra es:

$$M_{\text{eff}} = \left( \frac{f_1}{f_{\text{obj}}} \right) \times \left( \frac{f_{\text{final}}}{f_2} \right) = \left( \frac{f_1}{f_2} \right) \cdot \frac{f_{\text{final}}}{f_{\text{obj}}} = 1.25 \times \frac{f_{\text{final}}}{f_{\text{obj}}}$$

* **Para puertos con $f_{\text{final}} = 250\ \text{mm}$** (Cámara réflex Canon, Espectrómetro Shamrock 500i, Confocal Amarillo 592 nm y Confocal Rojo 637 nm):
  $$M_{\text{eff}} = 1.25 \times \frac{250\ \text{mm}}{f_{\text{obj}}} = \frac{312.5\ \text{mm}}{f_{\text{obj}}}$$

* **Para el puerto con $f_{\text{final}} = 200\ \text{mm}$** (Canal Confocal Verde 532 nm):
  $$M_{\text{eff}} = 1.25 \times \frac{200\ \text{mm}}{f_{\text{obj}}} = \frac{250.0\ \text{mm}}{f_{\text{obj}}}$$

---

## 3. 🎯 Matriz de Aumentos Efectivos Reales ($M_{\text{eff}}$)

Calculados para los 5 objetivos especializados del banco:

| Objetivo | Distancia Focal $f_{\text{obj}}$ | Apertura $\text{NA}$ | Inmersión ($n$) | Cámara Canon ($f=250\text{mm}$) | Confocal 532 nm ($f=200\text{mm}$) | Confocal 592 nm ($f=250\text{mm}$) | Confocal 637 nm ($f=250\text{mm}$) | Espectrómetro ($f=250\text{mm}$) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Olympus 20x** (PLN 20x) | $9.00\ \text{mm}$ | $0.40$ | Aire ($1.000$) | **$34.72\times$** | **$27.78\times$** | **$34.72\times$** | **$34.72\times$** | **$34.72\times$** |
| **Olympus 60x W** (LUMPlanFLN) | $3.00\ \text{mm}$ | $1.00$ | Agua ($1.333$) | **$104.17\times$** | **$83.33\times$** | **$104.17\times$** | **$104.17\times$** | **$104.17\times$** |
| **Olympus 10x** (MPLN 10x) | $18.00\ \text{mm}$ | $0.25$ | Aire ($1.000$) | **$17.36\times$** | **$13.89\times$** | **$17.36\times$** | **$17.36\times$** | **$17.36\times$** |
| **Nikon 100x Oil** (Iris $\text{NA}=1.30$) | $2.00\ \text{mm}$ | $1.30$ | Aceite ($1.515$) | **$156.25\times$** | **$125.00\times$** | **$156.25\times$** | **$156.25\times$** | **$156.25\times$** |
| **Nikon 100x Oil** (Iris $\text{NA}=0.50$) | $2.00\ \text{mm}$ | $0.50$ | Aceite ($1.515$) | **$156.25\times$** | **$125.00\times$** | **$156.25\times$** | **$156.25\times$** | **$156.25\times$** |
| **Nikon 40x Aire** (CFI S Plan) | $5.00\ \text{mm}$ | $0.60$ | Aire ($1.000$) | **$62.50\times$** | **$50.00\times$** | **$62.50\times$** | **$62.50\times$** | **$62.50\times$** |

> [!NOTE]
> En microscopios estándar con lente de tubo de referencia Olympus ($f_{\text{ref}} = 180\ \text{mm}$), el objetivo Olympus 60x W entrega un aumento nominal de $60\times$.  
> Sin embargo, debido al tren relé intermedio ($250/200 = 1.25\times$) y a la lente de salida de $250\ \text{mm}$, el **aumento efectivo real en el detector es de $104.17\times$**, lo que amplía la escala de proyección de imagen en un factor $+73.6\%$ respecto a la etiqueta del revólver.

---

## 4. 🔬 Límites de Resolución Difractiva Lateral y Axial

### 4.1 Ecuaciones Teóricas Fundamentales
- **Límite de Resolución Lateral de Abbe** (corte en frecuencia espacial $k_{\max} = 2\text{NA}/\lambda$):
  $$r_{\text{Abbe}} = \frac{\lambda}{2 \text{NA}}$$
- **Criterio de Resolución Lateral de Rayleigh** (caída del $26.5\%$ en la silla entre dos discos de Airy):
  $$r_{\text{Rayleigh}} = 0.61 \frac{\lambda}{\text{NA}} \approx 1.22 \frac{\lambda}{2 \text{NA}}$$
- **Rango de Rayleigh Axial en Medio de Inmersión $n$**:
  $$z_{\text{Rayleigh}} = \frac{2 n \lambda}{\text{NA}^2}$$
- **Espesor de Sección Óptica Confocal Axial (FWHM)**:  
  En régimen confocal con pinhole infinitesimal, la integración paraxial rigurosa de la PSF confocal tridimensional ($I_{\text{conf}}(u) = [\text{sinc}(u/4)]^4$) arroja:
  $$z_{\text{confocal}} \approx \frac{0.64 \lambda}{n - \sqrt{n^2 - \text{NA}^2}}$$
  En el límite paraxial ($\text{NA} \ll n$), esta expresión colapsa en la forma asintótica clásica $z_{\text{confocal}} \approx \frac{1.28 n \lambda}{\text{NA}^2} \approx 0.64\,z_{\text{Rayleigh}}$.

### 4.2 Tabla de Resoluciones Difractivas por Longitud de Onda

| Objetivo | Parámetro Metrológico | $\lambda = 532\ \text{nm}$ (Verde) | $\lambda = 592\ \text{nm}$ (Amarillo) | $\lambda = 637\ \text{nm}$ (Rojo) | $\lambda = 808\ \text{nm}$ (Infrarrojo) |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **Olympus 20x**<br>($\text{NA}=0.40, n=1.000$) | $r_{\text{Abbe}}$<br>$r_{\text{Rayleigh}}$<br>$z_{\text{confocal}}$ | $665.0\ \text{nm}$<br>$811.3\ \text{nm}$<br>$4.08\ \mu\text{m}$ | $740.0\ \text{nm}$<br>$902.8\ \text{nm}$<br>$4.54\ \mu\text{m}$ | $796.2\ \text{nm}$<br>$971.4\ \text{nm}$<br>$4.88\ \mu\text{m}$ | $1010.0\ \text{nm}$<br>$1232.2\ \text{nm}$<br>$6.19\ \mu\text{m}$ |
| **Olympus 60x W**<br>($\text{NA}=1.00, n=1.333$) | $r_{\text{Abbe}}$<br>$r_{\text{Rayleigh}}$<br>$z_{\text{confocal}}$ | **$266.0\ \text{nm}$**<br>**$324.5\ \text{nm}$**<br>**$0.75\ \mu\text{m}$** | $296.0\ \text{nm}$<br>$361.1\ \text{nm}$<br>$0.84\ \mu\text{m}$ | $318.5\ \text{nm}$<br>$388.6\ \text{nm}$<br>$0.90\ \mu\text{m}$ | $404.0\ \text{nm}$<br>$492.9\ \text{nm}$<br>$1.15\ \mu\text{m}$ |
| **Olympus 10x**<br>($\text{NA}=0.25, n=1.000$) | $r_{\text{Abbe}}$<br>$r_{\text{Rayleigh}}$<br>$z_{\text{confocal}}$ | $1064.0\ \text{nm}$<br>$1298.1\ \text{nm}$<br>$10.72\ \mu\text{m}$ | $1184.0\ \text{nm}$<br>$1444.5\ \text{nm}$<br>$11.93\ \mu\text{m}$ | $1274.0\ \text{nm}$<br>$1554.3\ \text{nm}$<br>$12.84\ \mu\text{m}$ | $1616.0\ \text{nm}$<br>$1971.5\ \text{nm}$<br>$16.29\ \mu\text{m}$ |
| **Nikon 100x Oil**<br>($\text{NA}=1.30, n=1.515$) | $r_{\text{Abbe}}$<br>$r_{\text{Rayleigh}}$<br>$z_{\text{confocal}}$ | **$204.6\ \text{nm}$**<br>**$249.6\ \text{nm}$**<br>**$0.46\ \mu\text{m}$** | $227.7\ \text{nm}$<br>$277.8\ \text{nm}$<br>$0.51\ \mu\text{m}$ | $245.0\ \text{nm}$<br>$298.9\ \text{nm}$<br>$0.55\ \mu\text{m}$ | $310.8\ \text{nm}$<br>$379.1\ \text{nm}$<br>$0.70\ \mu\text{m}$ |
| **Nikon 100x Oil (Iris 0.50)**<br>($\text{NA}=0.50, n=1.515$) | $r_{\text{Abbe}}$<br>$r_{\text{Rayleigh}}$<br>$z_{\text{confocal}}$ | $532.0\ \text{nm}$<br>$649.0\ \text{nm}$<br>$4.01\ \mu\text{m}$ | $592.0\ \text{nm}$<br>$722.2\ \text{nm}$<br>$4.46\ \mu\text{m}$ | $637.0\ \text{nm}$<br>$777.1\ \text{nm}$<br>$4.80\ \mu\text{m}$ | $808.0\ \text{nm}$<br>$985.8\ \text{nm}$<br>$6.09\ \mu\text{m}$ |
| **Nikon 40x Aire**<br>($\text{NA}=0.60, n=1.000$) | $r_{\text{Abbe}}$<br>$r_{\text{Rayleigh}}$<br>$z_{\text{confocal}}$ | $443.3\ \text{nm}$<br>$540.9\ \text{nm}$<br>$1.70\ \mu\text{m}$ | $493.3\ \text{nm}$<br>$601.9\ \text{nm}$<br>$1.89\ \mu\text{m}$ | $530.8\ \text{nm}$<br>$647.6\ \text{nm}$<br>$2.04\ \mu\text{m}$ | $673.3\ \text{nm}$<br>$821.5\ \text{nm}$<br>$2.59\ \mu\text{m}$ |

---

## 5. 🕳️ Diámetro de Disco de Airy en Pinholes y Unidades Airy ($AU$)

### 5.1 Función de Transmisión Analítica de Bessel

La distribución de intensidad del patrón de difracción de Fraunhofer producido por una pupila circular transparente es el patrón de Airy:

$$I(v) = I_0 \left[ \frac{2 J_1(v)}{v} \right]^2$$

donde $v$ es la coordenada óptica transversal adimensional normalizada:

$$v = \frac{2\pi}{\lambda} \cdot \frac{\text{NA}}{M_{\text{eff}}} \cdot r_{\text{pinhole}}$$

El primer mínimo nulo de difracción ocurre en la primera raíz positiva de la función de Bessel de primer orden, $J_1(v_1) = 0$, cuyo valor es $v_1 \approx 3.8317$. El diámetro físico del primer anillo oscuro en el plano del detector/pinhole es:

$$d_{\text{Airy}} = 2 \cdot r_1 = 2 \cdot \frac{v_1 \lambda M_{\text{eff}}}{2\pi \text{NA}} = \frac{3.8317}{\pi} \frac{\lambda M_{\text{eff}}}{\text{NA}} \approx 1.22 \frac{\lambda M_{\text{eff}}}{\text{NA}} \times 2 = 2.44 \frac{\lambda M_{\text{eff}}}{\text{NA}}$$

La fracción normalizada en **Unidades Airy ($AU$)** se define como el cociente entre el diámetro físico de la apertura mecánica del pinhole y el diámetro del disco de Airy:

$$AU = \frac{d_{\text{pinhole}}}{d_{\text{Airy}}}$$

Integrando la irradiancia sobre un pinhole circular de radio normalizado $v_p = \pi \cdot AU \cdot 1.22$, la fracción de potencia luminosa transmitida $T(v_p)$ viene dada por la identidad analítica de Lommel:

$$T(v_p) = \int_0^{v_p} \left[ \frac{2 J_1(v)}{v} \right]^2 v\,dv = 1 - J_0^2(v_p) - J_1^2(v_p)$$

### 5.2 Matriz de Rendimiento Super-Confocal

| Canal Confocal / Pinhole | Objetivo | Aumento $M_{\text{eff}}$ | Diámetro Airy ($d_{\text{Airy}}$) | Fracción Airy ($AU$) | Transmisión $T$ | Régimen Confocal y Rendimiento Físico |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| **Canal Verde 532 nm**<br>($f=200\text{ mm}$, $d_{\text{ph}}=50\ \mu\text{m}$) | Olympus 20x<br>**Olympus 60x W**<br>Olympus 10x<br>Nikon 100x (1.30)<br>Nikon 100x (0.50)<br>Nikon 40x | $27.8\times$<br>**$83.3\times$**<br>$13.9\times$<br>$125.0\times$<br>$125.0\times$<br>$50.0\times$ | $90.1\ \mu\text{m}$<br>**$108.2\ \mu\text{m}$**<br>$72.1\ \mu\text{m}$<br>$124.8\ \mu\text{m}$<br>$324.5\ \mu\text{m}$<br>$108.2\ \mu\text{m}$ | $0.55\ AU$<br>**$0.46\ AU$**<br>$0.69\ AU$<br>$0.40\ AU$<br>$0.15\ AU$<br>$0.46\ AU$ | $\approx 58\%$<br>**$\approx 47\%$**<br>$\approx 70\%$<br>$\approx 40\%$<br>$\approx 12\%$<br>$\approx 47\%$ | **Régimen Super-Confocal ($AU < 1.0$)**:  <br>Para el objetivo maestro 60x W, $AU = 0.46$ suprime el $92\%$ de la luz dispersada fuera del plano ($\Delta z > 1\ \mu\text{m}$), estrechando la PSF lateral efectiva en un factor $\approx 1.25\times$. Ideal para detección de anclaje de nanopartículas individuales e iSCAT. |
| **Canal Amarillo 592 nm**<br>($f=250\text{ mm}$, $d_{\text{ph}}=50\ \mu\text{m}$) | Olympus 20x<br>**Olympus 60x W**<br>Olympus 10x<br>Nikon 100x (1.30)<br>Nikon 100x (0.50)<br>Nikon 40x | $34.7\times$<br>**$104.2\times$**<br>$17.4\times$<br>$156.2\times$<br>$156.2\times$<br>$62.5\times$ | $125.4\ \mu\text{m}$<br>**$150.5\ \mu\text{m}$**<br>$100.3\ \mu\text{m}$<br>$173.6\ \mu\text{m}$<br>$451.4\ \mu\text{m}$<br>$150.5\ \mu\text{m}$ | $0.40\ AU$<br>**$0.33\ AU$**<br>$0.50\ AU$<br>$0.29\ AU$<br>$0.11\ AU$<br>$0.33\ AU$ | $\approx 40\%$<br>**$\approx 31\%$**<br>$\approx 52\%$<br>$\approx 26\%$<br>$\approx 7\%$<br>$\approx 31\%$ | **Filtrado Espacial Estricto**:  <br>Alta discriminación axial para aislar la emisión plasmónica de nanocavitades y puntos cuánticos frente al fondo de dispersión en el líquido. |
| **Canal Rojo 637 nm**<br>($f=250\text{ mm}$, $d_{\text{ph}}=100\ \mu\text{m}$) | Olympus 20x<br>**Olympus 60x W**<br>Olympus 10x<br>Nikon 100x (1.30)<br>Nikon 100x (0.50)<br>Nikon 40x | $34.7\times$<br>**$104.2\times$**<br>$17.4\times$<br>$156.2\times$<br>$156.2\times$<br>$62.5\times$ | $134.9\ \mu\text{m}$<br>**$161.9\ \mu\text{m}$**<br>$107.9\ \mu\text{m}$<br>$186.8\ \mu\text{m}$<br>$485.7\ \mu\text{m}$<br>$161.9\ \mu\text{m}$ | $0.74\ AU$<br>**$0.62\ AU$**<br>**$0.93\ AU$**<br>$0.54\ AU$<br>$0.21\ AU$<br>$0.62\ AU$ | $\approx 74\%$<br>**$\approx 65\%$**<br>$\approx 82\%$<br>$\approx 57\%$<br>$\approx 18\%$<br>$\approx 65\%$ | **Compromiso Fotométrico Óptimo**:  <br>Transmisión elevada ($T \ge 65\%$) requerida para detectar fotoluminiscencia de nanodímeros y señales Raman Stokes ultradébiles sin perder la capacidad de seccionamiento tridimensional. |

---

## 6. 📷 Proyección sobre Cámara Canon EOS 500D y Muestreo de Nyquist

El subsistema de visión directa y adquisición digital emplea una cámara réflex **Canon EOS 500D** equipada con un sensor CMOS APS-C ($22.3 \times 14.9\ \text{mm}$, matriz de $4752 \times 3168\ \text{píxeles}$).

- **Paso físico de píxel en el sensor**:
  $$p_{\text{sensor}} = \frac{22.3\ \text{mm}}{4752} \approx 4.70\ \mu\text{m}$$

- **Paso de píxel proyectado en el plano de la muestra**:
  $$p_{\text{proy}} = \frac{p_{\text{sensor}}}{M_{\text{eff}}}$$

- **Criterio de Muestreo de Nyquist-Shannon**:  
  Para que la frecuencia de corte espacial del microscopio ($f_c = 2\text{NA}/\lambda = 1/r_{\text{Abbe}}$) sea capturada fielmente sin solapamiento espectral (*aliasing* óptico), la frecuencia de muestreo del sensor ($f_s = 1/p_{\text{proy}}$) debe satisfacer:
  $$f_s \ge 2 f_c \iff p_{\text{proy}} \le \frac{r_{\text{Abbe}}}{2} \iff \text{Ratio Nyquist} = \frac{r_{\text{Abbe}}}{2 \cdot p_{\text{proy}}} \ge 1.0$$

### 6.1 Matriz de Muestreo y Campo de Visión (FOV)

| Objetivo | Aumento Total $M_{\text{eff}}$ | Campo de Visión ($FOV_x \times FOV_y$) | Píxel Proyectado ($p_{\text{proy}}$) | Ratio Nyquist ($\lambda = 532\ \text{nm}$) | Condición de Muestreo |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **Olympus 20x** | $34.72\times$ | $642.2\ \mu\text{m} \times 429.1\ \mu\text{m}$ | $135.4\ \text{nm/px}$ | **$2.46\times$** | **Cumple Nyquist** (Supera el límite difractivo). |
| **Olympus 60x W** | $104.17\times$ | $214.1\ \mu\text{m} \times 143.0\ \mu\text{m}$ | **$45.1\ \text{nm/px}$** | **$2.95\times$** | **Sobremuestreo Óptimo**: Permite localización sub-nanométrica por ajuste analítico de PSF en `psf_analyzer.py`. |
| **Olympus 10x** | $17.36\times$ | $1284.5\ \mu\text{m} \times 858.2\ \mu\text{m}$ | $270.7\ \text{nm/px}$ | **$1.97\times$** | **Cumple Nyquist**: Gran campo de navegación. |
| **Nikon 100x Oil (1.30)** | $156.25\times$ | $142.7\ \mu\text{m} \times 95.4\ \mu\text{m}$ | **$30.1\ \text{nm/px}$** | **$3.40\times$** | **Altísima Densidad Sub-píxel**: Excelente para correlación cruzada y seguimiento térmico. |
| **Nikon 40x Aire** | $62.50\times$ | $356.8\ \mu\text{m} \times 238.4\ \mu\text{m}$ | $75.2\ \text{nm/px}$ | **$2.95\times$** | **Cumple Nyquist**: Adecuado para fluorescencia general. |

---

## 7. 🌈 Acoplamiento de Apertura al Espectrógrafo Shamrock 500i ($f/\#$-Matching)

El espectrógrafo Czerny-Turner **Andor Shamrock 500i** posee una distancia focal colimadora $f_{\text{spec}} = 500\ \text{mm}$ y espejos toroidales de apertura libre $D_{\text{espejo}} \approx 51.5\ \text{mm}$, fijando un número f de entrada nominal de:

$$f/\#_{\text{shamrock}} = \frac{f_{\text{spec}}}{D_{\text{espejo}}} = \frac{500\ \text{mm}}{51.5\ \text{mm}} \approx f/9.7$$

Cualquier cono óptico focalizado sobre la rendija de entrada con $f/\#_{\text{in}} < 9.7$ sobre-ilumina los espejos colimadores (*overfilling*), produciendo:
1. Viñeteo y pérdida severa de fotones en los bordes de la red.
2. Difracción parásita y luz dispersada (*stray light*) que degrada la relación señal-fondo en Raman de baja frecuencia.

Por el contrario, si $f/\#_{\text{in}} > 9.7$, el haz sub-ilumina los espejos (*underfilling*), garantizando recolección total sin viñeteo.

### 7.1 Deducción del Cono de Entrada

1. El diámetro de la pupila de salida del objetivo en espacio infinito es:
   $$D_{\text{pupila}} = 2 \cdot f_{\text{obj}} \cdot \text{NA}$$

2. Al atravesar el telescopio relé afocal ($f_1 = 250\ \text{mm} \to f_2 = 200\ \text{mm}$), el diámetro del haz colimado que incide en la lente de acople al espectrómetro ($f_{\text{lente}} = 250\ \text{mm}$) es:
   $$D_{\text{haz}} = D_{\text{pupila}} \times \left( \frac{f_2}{f_1} \right) = 0.80 \cdot D_{\text{pupila}} = 1.6 \cdot f_{\text{obj}} \cdot \text{NA}$$

3. La lente de acople ($f_{\text{lente}} = 250\ \text{mm}$) focaliza este haz sobre la rendija, generando un cono de entrada de número f:
   $$f/\#_{\text{in}} = \frac{f_{\text{lente}}}{D_{\text{haz}}} = \frac{250\ \text{mm}}{1.6 \cdot f_{\text{obj}} \cdot \text{NA}}$$

### 7.2 Matriz de Acoplamiento Espectral

| Objetivo | $f_{\text{obj}}$ | $\text{NA}$ | $D_{\text{pupila}}$ | $D_{\text{haz}}$ (en Lente 250 mm) | Cono de Entrada ($f/\#_{\text{in}}$) | Condición Frente a $f/9.7$ del Shamrock |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **Olympus 20x** | $9.00\ \text{mm}$ | $0.40$ | $7.20\ \text{mm}$ | $5.76\ \text{mm}$ | **$f/43.4$** | **Sub-ilumina (Seguro)**: $f/43.4 \gg f/9.7$. Cero viñeteo. |
| **Olympus 60x W** | $3.00\ \text{mm}$ | $1.00$ | $6.00\ \text{mm}$ | $4.80\ \text{mm}$ | **$f/52.1$** | **Sub-ilumina (Seguro)**: $f/52.1 \gg f/9.7$. Haz concentrado. |
| **Olympus 10x** | $18.00\ \text{mm}$ | $0.25$ | $9.00\ \text{mm}$ | $7.20\ \text{mm}$ | **$f/34.7$** | **Sub-ilumina (Seguro)**: $f/34.7 \gg f/9.7$. Máxima transmisión. |
| **Nikon 100x Oil** (1.30) | $2.00\ \text{mm}$ | $1.30$ | $5.20\ \text{mm}$ | $4.16\ \text{mm}$ | **$f/60.1$** | **Sub-ilumina (Seguro)**: $f/60.1 \gg f/9.7$. Cono extremadamente colimado. |
| **Nikon 40x Aire** | $5.00\ \text{mm}$ | $0.60$ | $6.00\ \text{mm}$ | $4.80\ \text{mm}$ | **$f/52.1$** | **Sub-ilumina (Seguro)**: Idéntico al 60x W. |

> [!TIP]
> Dado que en todas las configuraciones $f/\#_{\text{in}} \ge f/34.7 > f/9.7$, el haz de luz entra holgadamente contenido dentro de la apertura de los espejos colimadores. Esto asegura que la función de dispersión espectral del Shamrock 500i trabaje en su régimen teórico nominal sin ensanchamiento instrumental por coma de borde ni luz difusa.

---

## 8. 🧬 Fundamento Físico de Microscopía iSCAT (Interferometric Scattering)

En microscopía estándar de campo oscuro y dispersión elástica de Rayleigh, la sección eficaz de dispersión de una nanopartícula metálica sub-longitud de onda ($d \ll \lambda$) en el régimen electrostático cuasiestático es:

$$\sigma_{\text{scat}} = \frac{8\pi}{3} k^4 |\alpha|^2 = \frac{8\pi^3}{3} \frac{1}{\lambda^4} \left| 3 V \frac{\varepsilon_{\text{metal}} - \varepsilon_m}{\varepsilon_{\text{metal}} + 2\varepsilon_m} \right|^2 \propto \frac{V^2}{\lambda^4} \propto \frac{d^6}{\lambda^4}$$

Para partículas coloidales pequeñas ($d \le 40\ \text{nm}$), la señal decae drásticamente con la sexta potencia del diámetro ($d^6$): una partícula de 30 nm dispersa $(60/30)^6 = 64$ veces menos luz que una de 60 nm, quedando sepultada por el ruido de disparo del fondo.

### 8.1 Detección Homodina Interferométrica en el Microscopio Derecho

En la arquitectura del Microscopio Derecho, el canal confocal verde opera bajo detección **iSCAT**:  
El campo eléctrico total que incide sobre el fotodiodo Thorlabs PDA (`Dev1/ai0`) es la superposición coherente del campo de referencia reflejado en la interfaz vidrio-agua del sustrato ($E_r = r \cdot E_0$) y el campo débilmente dispersado por la nanopartícula en el foco ($E_s = s \cdot E_0$):

$$I_{\text{det}} = |E_r + E_s|^2 = |E_r|^2 + |E_s|^2 + 2 |E_r| |E_s| \cos \phi$$

donde $\phi$ es la diferencia de fase Gouy/interferométrica entre el haz de referencia y el haz dispersado.

Dado que para nanopartículas individuales $|E_s| \ll |E_r|$, el término cuadrático de dispersión pura $|E_s|^2 \propto d^6$ es despreciable frente al término cruzado de batido interferométrico:

$$I_{\text{det}} \approx |E_r|^2 + 2 |E_r| |E_s| \cos \phi = I_{\text{ref}} \left[ 1 + 2 \frac{|s|}{|r|} \cos \phi \right]$$

El contraste interferométrico neto $\Delta I_{\text{iSCAT}}$ resulta:

$$\Delta I_{\text{iSCAT}} = I_{\text{det}} - I_{\text{ref}} = 2 \sqrt{I_{\text{ref}} I_{\text{scat}}} \cos \phi \propto |s| \propto \alpha \propto V \propto d^3$$

### 8.2 La Ganancia Cuántica de iSCAT

$$\frac{\text{Señal iSCAT}}{\text{Señal Rayleigh}} \propto \frac{d^3}{d^6} = \frac{1}{d^3}$$

Para una nanopartícula de oro de $d = 20\ \text{nm}$ frente a una de $60\ \text{nm}$, la señal Rayleigh pura decae en un factor $(60/20)^6 = 729\times$, mientras que la señal iSCAT decae únicamente en un factor $(60/20)^3 = 27\times$. Esta ganancia de **$\approx 27\times$ a $1000\times$** es la que permite al software `measurements.py` detectar la entrada de una nanopartícula sub-40 nm en la trampa óptica en tiempo real antes de que se fije mecánicamente al sustrato.

---

## 9. 📐 Modelado Analítico de PSF (Gaussiano 2D y Donut $LG_{01}$)

El módulo `psf_analyzer.py` procesa los mapas confocales bidimensionales ajustando los perfiles experimentales mediante dos funciones no lineales de alta exactitud:

### 9.1 Perfil Gaussiano 2D Anisótropo con Rotación ($TEM_{00}$)

Para haces fundamentales gaussianos enfocados por objetivos de alta apertura:

$$I(x, y) = I_0 + A \exp\left( -\left[ \frac{(x' - x_0')^2}{2 \sigma_x^2} + \frac{(y' - y_0')^2}{2 \sigma_y^2} \right] \right)$$

donde las coordenadas rotadas $(x', y')$ están vinculadas a las coordenadas del laboratorio $(x, y)$ por la matriz ortogonal de rotación en el plano:

$$\begin{pmatrix} x' \\ y' \end{pmatrix} = \begin{pmatrix} \cos\theta & \sin\theta \\ -\sin\theta & \cos\theta \end{pmatrix} \begin{pmatrix} x - x_0 \\ y - y_0 \end{pmatrix}$$

El ancho a mitad de altura ($\text{FWHM}$) en los ejes principales se calcula analíticamente:

$$\text{FWHM}_{x,y} = 2 \sqrt{2 \ln 2} \cdot \sigma_{x,y} \approx 2.35482 \cdot \sigma_{x,y}$$

La elipticidad del foco se cuantifica como $\varepsilon = \sigma_x / \sigma_y$.

### 9.2 Perfil de Haz Vortex Laguerre-Gauss $LG_{01}$ (Donut)

Para haces con carga topológica $\ell = 1$ producidos por placas de fase espiral (*spiral phase plates*) para pinzas ópticas donut o microscopía STED:

$$I_{\text{donut}}(r) = I_0 + A \left( \frac{2 r^2}{w_0^2} \right) \exp\left( -\frac{2 r^2}{w_0^2} \right)$$

donde $r = \sqrt{(x - x_0)^2 + (y - y_0)^2}$ es la distancia radial al vórtice central y $w_0$ es la cintura del haz subyacente.

Derivando respecto a $r$ e igualando a cero:

$$\frac{d I_{\text{donut}}}{dr} = A \left[ \frac{4 r}{w_0^2} - \frac{8 r^3}{w_0^4} \right] \exp\left( -\frac{2 r^2}{w_0^2} \right) = 0$$

$$1 - \frac{2 r^2}{w_0^2} = 0 \implies r_{\text{peak}} = \frac{w_0}{\sqrt{2}}$$

El radio del anillo brillante de máxima intensidad ocurre exactamente en $r_{\text{peak}} = w_0 / \sqrt{2}$, mientras que en el centro exacto $r = 0$ la intensidad cae al nulo teórico $I(0) = I_0$, propiedad utilizada en `align_donut.py` para centrado con incertidumbre sub-nanométrica.

---

## 10. 🎯 Conclusiones e Integración Metrológica

1. **Magnificación Efectiva Calibrada:** La magnificación real del microscopio sobre los detectores no es la nominal de los objetivos, sino que está escalada por el factor del telescopio relé ($\Gamma = 1.25\times$), alcanzando $104.17\times$ para el Olympus 60x W y $156.25\times$ para el Nikon 100x Oil.
2. **Filtrado Super-Confocal Cuantificado:** El pinhole de $50\ \mu\text{m}$ con el objetivo 60x W opera en $0.46\ AU$, logrando una sección óptica axial de $0.75\ \mu\text{m}$ y una transmisión del $47\%$ con rechazo del $92\%$ del fondo fuera de plano.
3. **Acoplamiento Espectral Libre de Viñeteo:** Todos los objetivos generan conos de entrada con $f/\#_{\text{in}} \ge f/34.7$, muy por encima de la cota $f/9.7$ del Shamrock 500i, certificando conservación del flujo fotónico sin luz difusa.
4. **Respaldo Teórico de Detección en Tiempo Real:** Las deducciones de iSCAT ($\Delta I \propto d^3$) y del ajuste analítico de PSF en $LG_{01}$ constituyen la base matemática que hace operativos los algoritmos en lazo cerrado de `measurements.py` y `psf_analyzer.py`.
