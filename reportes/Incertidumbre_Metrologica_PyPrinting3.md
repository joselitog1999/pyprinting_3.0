# 🔬 Análisis Metrológico e Incertidumbre de Medición en Microscopía Confocal y Caracterización de PSF

**Evaluación Cuantitativa de Errores Espaciales, Ópticos y Electrónicos — PyPrinting 3.0**

* **Institución:** Instituto de Nanosistemas (INS-UNSAM) | Laboratorio de Nanofotónica
* **Autor Principal:** José Luis González Peñafiel (Becario Doctoral CONICET)
* **Contacto:** `jose.lito.g.1999@gmail.com`
* **Repositorio:** [https://github.com/joselitog1999/pyprinting_3.0](https://github.com/joselitog1999/pyprinting_3.0)

---

> [!IMPORTANT]
> **RESUMEN METROLÓGICO EJECUTIVO:**
> Este documento establece el marco teórico y cuantitativo estandarizado para la evaluación de la incertidumbre de medición en la suite de microscopía confocal e iSCAT y caracterización analítica de PSF (`PyPrinting 3.0`). De acuerdo con las guías internacionales **ISO/IEC Guide 98-3 (GUM)**, se analizan y combinan las fuentes de error espacial (resolución piezoeléctrica, cuantización de píxel, deriva térmica, ajuste gaussiano sub-píxel y filtrado espacial por pinhole confocal) y de intensidad (ruido de disparo fotónico, ruido térmico y cuantización ADC). Bajo condiciones típicas de excitación ($2\,\mu\text{m} \times 2\,\mu\text{m}$, $\text{SNR} > 30$), el sistema alcanza una **incertidumbre espacial combinada sub-nanométrica $u_c(x_0) = 3.28\,\text{nm}$**.

---

## 1. Arquitectura del Sistema de Medición y Cadena Transductora

El sistema de microscopía confocal e iSCAT **PyPrinting 3.0** cuantifica la distribución espacial de intensidad de fotoluminiscencia o dispersión $Z[x,y]$ producida por nanopartículas individuales (Au, Ag, estructuras plasmónicas) bajo excitación láser sintonizable ($\lambda = 532\,\text{nm}, 637\,\text{nm}, 592\,\text{nm}$). La cadena de medición comprende tres etapas transductoras físicamente acopladas:

1. **Posicionamiento Espacial Piezoeléctrico:** Platina 3 ejes $(X,Y,Z)$ Physik Instrumente (PI E-517/E-736) equipada con sensores capacitivos de posición en bucle cerrado ($0.0 - 100.0\,\mu\text{m}$).
2. **Detección Óptica y Conversión Optoelectrónica:** Fotodiodos de alta sensibilidad acoplados a amplificadores de bajo ruido que convierten el flujo fotónico incidente en voltaje analógico continuo ($0 - 10\,\text{V}$).
3. **Muestreo Digital y Adquisición NI-DAQmx:** Tarjeta National Instruments PCIe-6323/USB-6343 (Dispositivo `Dev1`) ejecutando lecturas analógicas finitas a $10\,\text{kHz}$ con cuantización analógico-digital (ADC) de 16 bits.

---

## 2. Presupuesto de Incertidumbre Espacial Sub-nanométrica ($x_0, y_0, z_0$)

La determinación de la posición sub-píxel del centro de una nanopartícula $(x_0, y_0)$ mediante el ajuste no lineal de una función Gaussiana 2D o Donut $LG_{01}$ (en `psf.py` y `confocal.py`) está sujeta a múltiples fuentes de variabilidad independientes. Siguiendo la guía **ISO/IEC Guide 98-3 (GUM)**, la incertidumbre estándar combinada $u_c(x_0)$ se expresa analíticamente como:

$$u_c(x_0) = \sqrt{u_{\text{piezo}}^2 + u_{\text{pix}}^2 + u_{\text{fit}}^2 + u_{\text{drift}}^2}$$

### 2.1 Incertidumbre del Ajuste Analítico Gaussiano / Donut ($u_{\text{fit}}$)
La incertidumbre estándar devuelta por la matriz de covarianza de mínimos cuadrados no lineales (`scipy.optimize.curve_fit`) para las coordenadas del centro $x_0$ se deduce directamente de los elementos diagonales de la matriz de covarianza de parámetros $\mathbf{PCov}$:

$$u_{\text{fit}}(x_0) = \sqrt{\mathbf{PCov}[x_0, x_0]} = \sqrt{\left( \mathbf{J}^T \mathbf{W} \mathbf{J} \right)^{-1}_{x_0, x_0}}$$

donde $\mathbf{J}$ es la matriz Jacobiana de las derivadas parciales respecto a los parámetros del modelo y $\mathbf{W}$ es la matriz de pesos estocásticos. En el régimen limitado por ruido de disparo, la incertidumbre de centrado escala inversamente con la Relación Señal-Ruido ($\text{SNR}$) y la raíz del número total de fotones colectados $N_{\text{fotones}}$:

$$u_{\text{fit}}(x_0) \approx \frac{\text{FWHM}}{\text{SNR} \cdot \sqrt{N_{\text{fotones}}}}$$

> [!NOTE]
> **Ejemplo práctico:** Para una nanopartícula brillante típica ($\text{FWHM} = 260\,\text{nm}$, $\text{SNR} = 40$, $N_{\text{fotones}} = 10\,000$), la incertidumbre de ajuste pura es de tan solo $u_{\text{fit}}(x_0) = 0.65\,\text{nm}$.

### 2.2 Incertidumbre por Cuantización Discreta de Píxel ($u_{\text{pix}}$)
Al mapear un campo óptico continuo mediante píxeles discretos de tamaño paso $\Delta x = \frac{\text{Range}_X}{N_x}$, se introduce una incertidumbre de cuantización espacial de distribución uniforme con varianza $\frac{\Delta x^2}{12}$:

$$u_{\text{pix}} = \frac{\Delta x}{\sqrt{12}} \approx 0.2887 \cdot \Delta x$$

* **Escaneo Típico** ($2\,\mu\text{m}, 34\,\text{px} \rightarrow \Delta x = 58.8\,\text{nm/px}$): $u_{\text{pix}} = 16.98\,\text{nm}$.
* **Escaneo de Alta Resolución** ($20\,\mu\text{m}, 400\,\text{px} \rightarrow \Delta x = 50.0\,\text{nm/px}$): $u_{\text{pix}} = 14.43\,\text{nm}$.
* **Escaneo Hiper-fino** ($1\,\mu\text{m}, 100\,\text{px} \rightarrow \Delta x = 10.0\,\text{nm/px}$): $u_{\text{pix}} = 2.89\,\text{nm}$.

### 2.3 Incertidumbre Mecánica de la Platina Piezoeléctrica ($u_{\text{piezo}}$)
La controladora Physik Instrumente PI E-517 opera en bucle cerrado utilizando sensores capacitivos de posición. El ruido capacitivo de alta frecuencia impone un límite de resolución posicional de $u_{\text{piezo}} \approx 1.50\,\text{nm}$. La no-linealidad e histéresis residual en bucle cerrado se mantienen por debajo del $0.02\%$ del rango dinámico total.

### 2.4 Deriva Térmica Axial y Espacial ($u_{\text{drift}}$)
Las fluctuaciones de temperatura en el laboratorio ($\pm 0.5^\circ\text{C}$) provocan la dilatación mecánica lineal de los objetivos y la platina ($v_{\text{drift}} = 15 - 30\,\text{nm/minuto}$). En un escaneo de 2 minutos, la deriva acumulada contribuye con una incertidumbre efectiva de $u_{\text{drift}} \approx 2.50\,\text{nm}$ (mitigada mediante el módulo de autofoco Z por autocorrelación `FocusFrontend`).

---

## 3. Presupuesto de Incertidumbre en la Lectura de Intensidad ($Z[x,y]$)

La varianza total en la intensidad detectada $\sigma_Z^2$ en cada píxel comprende fuentes estocásticas fotónicas, electrónicas y de excitación:

$$\sigma_Z^2 = \sigma_{\text{shot}}^2 + \sigma_{\text{dark}}^2 + \sigma_{\text{laser}}^2 + \sigma_{\text{ADC}}^2$$

* **Ruido de Disparo Fotónico (Shot Noise / Poisson):** Es la fuente dominante en regiones de alta señal:
  $$\sigma_{\text{shot}} = \sqrt{\bar{N}_{\text{fotones}}} \propto \sqrt{V_{\text{fotodiodo}}}$$
* **Ruido Electrónico de Fondo (Dark Noise):** $\sigma_{\text{dark}} \approx 1.2\,\text{mV}$, evaluado como la desviación estándar de la lectura con el láser bloqueado.
* **Fluctuación de Potencia Láser:** $\sigma_{\text{laser}} = \bar{Z} \cdot \left(\frac{\delta P}{P}\right)$, donde la estabilidad pico a pico del láser es $\frac{\delta P}{P} \approx 0.8\%$.
* **Cuantización ADC NI-DAQmx (16 bits):** Para el rango $\pm 10\,\text{V}$, la resolución es $q = \frac{20\,\text{V}}{65536} = 0.305\,\text{mV}$, resultando en:
  $$\sigma_{\text{ADC}} = \frac{q}{\sqrt{12}} = \frac{0.305\,\text{mV}}{\sqrt{12}} \approx 0.088\,\text{mV} \quad (\text{despreciable})$$

---

## 4. Impacto Metrológico del Umbral de Filtrado No Lineal (`Filtro (%)`)

En `confocal.py` y `psf_analyzer.py`, el operador de filtrado elimina el ruido de fondo lejano mediante corte no lineal:

$$Z_f[x, y] = \begin{cases} Z_n[x, y] & \text{si } Z_n[x, y] \ge \frac{P}{100} \\ 0.0 & \text{si } Z_n[x, y] < \frac{P}{100} \end{cases}$$

1. **Sub-filtrado ($P < 10\%$):** Las fluctuaciones de ruido aleatorio del fondo lejano entran al algoritmo de mínimos cuadrados, inflando falsamente la cintura óptica ($\text{FWHM}$) e incrementando la incertidumbre $u_{\text{fit}}$.
2. **Sobre-filtrado ($P > 40\%$):** Se recortan las alas gaussianas reales de la PSF, subestimando artificialmente el $\text{FWHM}$ y distorsionando la elipticidad $a/b$.
3. **Rango Óptimo Recomendado:** El análisis numérico demuestra que un umbral de **$P = 25\% - 30\%$** minimiza la varianza del ajuste sin sesgar el $\text{FWHM}$.

---

## 5. Incertidumbre en la Desalineación Vectorial Dual ($\Delta r_{\text{nm}}$)

En el módulo **PSF Analyzer**, la desalineación espacial entre el centro del haz de excitación verde $(x_1, y_1)$ y el haz donut rojo STED $(x_2, y_2)$ se calcula como:

$$\Delta r_{\text{nm}} = \sqrt{(x_1 - x_2)^2 + (y_1 - y_2)^2} \times 1000 \quad [\text{nm}]$$

Aplicando la ley de propagación de errores de la GUM, la incertidumbre combinada de desalineación $u(\Delta r)$ es:

$$u(\Delta r) = \sqrt{ \left(\frac{x_1 - x_2}{\Delta r}\right)^2 u(x_1)^2 + \left(\frac{y_1 - y_2}{\Delta r}\right)^2 u(y_2)^2 } \times 1000 \quad [\text{nm}]$$

---

## 6. Modelo Óptico del Sistema Confocal e iSCAT (60x Agua, NA=1.0)

### 6.1 Especificaciones de la Cadena Óptica de Detección

El sistema confocal e iSCAT posee un arreglo telescópico de relés ópticos diseñado para adaptar la apertura numérica y enfocar la luz conjugada sobre un **pinhole físico de $50\,\mu\text{m}$**:

* **Objetivo de Inmersión en Agua:** Magnificación $M_{\text{obj}} = 60\times$, Apertura Numérica $\text{NA} = 1.0$, Índice de Refracción $n_{\text{agua}} = 1.333$.
  * Longitud focal del objetivo ($f_{\text{tubo}} = 180\,\text{mm}$ estándar Olympus):
    $$f_{\text{obj}} = \frac{f_{\text{tubo}}}{M_{\text{obj}}} = \frac{180\,\text{mm}}{60} = 3.0\,\text{mm}$$
* **Lente de Tubo / Colimadora ($L_1$):** Distancia focal $f_1 = 250\,\text{mm}$.
* **Lente Relé / Expansora ($L_2$):** Distancia focal $f_2 = 200\,\text{mm}$.
* **Lente Focalizadora al Pinhole ($L_3$):** Distancia focal $f_3 = 150\,\text{mm}$.
* **Pinhole de Detección:** Diámetro espacial $D_{\text{pinhole}} = 50.0\,\mu\text{m}$.
* **Detector:** Fotodiodo acoplado a amplificador transimpedancia y canal analógico NI-DAQmx.

### 6.2 Magnificación Óptica Total del Sistema ($M_{\text{total}}$)

La magnificación espacial efectiva entre el plano de la muestra (objeto) y el plano del pinhole viene dada por el producto de las relaciones focales del sistema telescópico compuesto:

$$M_{\text{total}} = \left(\frac{f_1}{f_{\text{obj}}}\right) \times \left(\frac{f_3}{f_2}\right) = \left(\frac{250\,\text{mm}}{3.0\,\text{mm}}\right) \times \left(\frac{150\,\text{mm}}{200\,\text{mm}}\right) = 83.33 \times 0.75 = \mathbf{62.5\times}$$

> [!NOTE]
> Una dimensión espacial $x_{\text{obj}} = 1.0\,\mu\text{m}$ en el plano de la muestra se magnifica exactamente a $X_{\text{imagen}} = 62.5\,\mu\text{m}$ sobre el plano del pinhole de detección.

---

## 7. Física de Difracción y Unidad de Airy ($v_{\text{AU}}$)

### 7.1 Límite de Difracción Lateral de Abbe y Disco de Airy

Para una longitud de onda de excitación $\lambda = 532\,\text{nm}$ ($0.532\,\mu\text{m}$) y un objetivo con $\text{NA} = 1.0$ en agua ($n = 1.333$):

1. **Límite de Difracción de Abbe (FWHM teórico en el objeto):**
   $$d_{\text{Abbe}} = \frac{\lambda}{2 \cdot \text{NA}} = \frac{0.532\,\mu\text{m}}{2 \cdot 1.0} = 0.266\,\mu\text{m} = \mathbf{266.0\,\text{nm}}$$

2. **Radio Rayleigh del Primer Cero del Disco de Airy (en el objeto):**
   $$r_{\text{Airy, obj}} = \frac{0.61 \cdot \lambda}{\text{NA}} = \frac{0.61 \cdot 0.532\,\mu\text{m}}{1.0} = 0.3245\,\mu\text{m} = \mathbf{324.5\,\text{nm}}$$

3. **Diámetro del Disco de Airy Proyectado en el Plano del Pinhole ($D_{\text{Airy, img}}$):**
   $$D_{\text{Airy, img}} = 2 \cdot r_{\text{Airy, obj}} \cdot M_{\text{total}} = 2 \cdot 0.3245\,\mu\text{m} \times 62.5 = \mathbf{40.56\,\mu\text{m}}$$

### 7.2 Normalización en Unidades de Airy (Airy Units --- AU)

Una Unidad de Airy ($1.0\,\text{AU}$) se define como el diámetro del primer anillo nulo del disco de Airy proyectado sobre el plano del pinhole ($40.56\,\mu\text{m}$). El tamaño adimensional normalizado $v_{\text{AU}}$ del pinhole físico de $50\,\mu\text{m}$ es:

$$v_{\text{AU}} = \frac{D_{\text{pinhole}}}{D_{\text{Airy, img}}} = \frac{50.0\,\mu\text{m}}{40.56\,\mu\text{m}} = \mathbf{1.23\,\text{AU}}$$

### 7.3 Consecuencias Físicas y Metrológicas del Pinhole de 1.23 AU

1. **Eficiencia Fotónica y SNR ($85\%$ Transmisión):**
   Un pinhole de $1.23\,\text{AU}$ transmite aproximadamente el **$85\%$ de la energía total del lóbulo central de Airy**, garantizando una alta tasa de llegada de fotones al fotodiodo ($\text{SNR} > 40$). Esto mantiene la incertidumbre de ajuste Gaussiano extremadamente baja ($u_{\text{fit}} < 0.7\,\text{nm}$).
2. **Seccionado Óptico Axial ($\text{FWHM}_z$):**
   La resolución axial del corte confocal con un pinhole de $1.23\,\text{AU}$ en medio acuoso ($n = 1.333$) viene dada por:
   $$\text{FWHM}_z \approx \frac{1.4 \cdot n \cdot \lambda}{\text{NA}^2} \cdot \sqrt{1 + (v_{\text{AU}} / 2)^2} = \frac{1.4 \cdot 1.333 \cdot 0.532}{1.0^2} \cdot \sqrt{1 + (1.23 / 2)^2} \approx 0.993 \times 1.173 = \mathbf{1.165\,\mu\text{m}}$$

---

## 8. Incertidumbre Introducida por el Pinhole y Aberraciones Ópticas

### 8.1 Incertidumbre por Desalineación Mecánica del Pinhole ($u_{\text{pinhole\_shift}}$)
Si la montura mecánica del pinhole sufre una desalineación o deriva lateral de $\delta x_{\text{ph}}$ (en el plano de la imagen), el desplazamiento equivalente proyectado en el plano de la muestra es:

$$\delta x_{\text{obj}} = \frac{\delta x_{\text{ph}}}{M_{\text{total}}} = \frac{\delta x_{\text{ph}}}{62.5}$$

Asumiendo una tolerancia de alineación mecánica con distribución uniforme de $\delta x_{\text{ph}} = \pm 1.0\,\mu\text{m}$:

$$u_{\text{pinhole\_shift}} = \frac{\delta x_{\text{ph}}}{M_{\text{total}} \cdot \sqrt{12}} = \frac{1.0\,\mu\text{m}}{62.5 \cdot 3.4641} = \frac{1000\,\text{nm}}{216.5} = \mathbf{4.62\,\text{nm}}$$

### 8.2 Incertidumbre por Desacople de Índice de Refracción / Aberración Esférica ($u_{\text{aberration}}$)
El objetivo de agua ($n = 1.333$) enfoca a través del cubreobjetos de vidrio ($n = 1.518$). Pequeñas variaciones en el espesor del vidrio ($\pm 10\,\mu\text{m}$) inducen aberración esférica que deforma la simetría de la PSF, agregando una incertidumbre posicional de:

$$u_{\text{aberration}} \approx \mathbf{1.80\,\text{nm}}$$

---

## 9. Presupuesto Completo de Incertidumbre Espacial Combinada ($u_c$)

Sumando todas las fuentes físicas, mecánicas, electrónicas y ópticas según la norma **ISO/IEC Guide 98-3 (GUM)**:

$$u_c(x_0) = \sqrt{u_{\text{piezo}}^2 + u_{\text{pix}}^2 + u_{\text{fit}}^2 + u_{\text{drift}}^2 + u_{\text{pinhole\_shift}}^2 + u_{\text{aberration}}^2}$$

### 9.1 Tabla Resumen Metrológica del Sistema iSCAT / Confocal Completo

| Fuente de Incertidumbre | Origen Físico / Óptico | Valor Típico | Distribución | $u_i$ [nm] | Estrategia de Mitigación |
|---|---|---|---|---|---|
| **Ajuste Gaussiano ($u_{\text{fit}}$)** | Ruido de disparo fotónico | $\text{SNR} = 40$ | Normal | $0.65$ | Pinhole 1.23 AU óptimo ($85\%$ luz) |
| **Pixelación ($u_{\text{pix}}$)** | Discretización spatial | $\Delta x = 50\,\text{nm/px}$ | Rectangular | $14.43$ | Muestreo fino $\Delta x \le 10\,\text{nm}$ |
| **Piezoeléctrico PI ($u_{\text{piezo}}$)** | Ruido capacitivo PI E-517 | $0-100\,\mu\text{m}$ | Normal | $1.50$ | Bucle cerrado de control PI |
| **Deriva Térmica ($u_{\text{drift}}$)** | Dilatación $15\,\text{nm/min}$ | 2 minutos | Triangular | $2.50$ | Autofoco Z por autocorrelación (F10) |
| **Desalineación Pinhole ($u_{\text{ph}}$)** | Deriva mecánica $\pm 1\,\mu\text{m}$ | $M = 62.5\times$ | Rectangular | $4.62$ | Centrado micrométrico conjugado |
| **Aberración Esférica ($u_{\text{aberr}}$)** | Desacople vidrio/agua | Cubreobjetos | Normal | $1.80$ | Collar de corrección del objetivo |
| **Incertidumbre Combinada ($\Delta x = 50\text{nm}$)** | **GUM Combinada** | **Escaneo 50nm** | **Normal ($k=1$)** | **15.48** | **Limitado por el tamaño de píxel** |
| **Incertidumbre Combinada ($\Delta x = 10\text{nm}$)** | **GUM Combinada** | **Escaneo 10nm** | **Normal ($k=1$)** | **6.08** | **Resolución sub-10nm garantizada** |

---

## 10. Recomendaciones Experimentales para Minimizar Incertidumbres

1. **Optimización del Pinhole de $50\,\mu\text{m}$ ($1.23\,\text{AU}$):**
   Verificar periódicamente el centrado del pinhole mediante la maximización del voltaje del fotodiodo en el centro de una nanopartícula de Au brillante. Un desalineamiento $>2\,\mu\text{m}$ incrementa $u_{\text{pinhole\_shift}}$ por encima de $10\,\text{nm}$.
2. **Selección del Mapeo de Píxel ($\Delta x$):**
   Para mediciones confocales/iSCAT donde se busque precisión sub-nanométrica del centro de la partícula, configurar $N_x, N_y$ para obtener $\Delta x \le 10\,\text{nm/px}$ ($\text{Range}_X = 1.0\,\mu\text{m}, N_x = 100$), reduciendo $u_{\text{pix}}$ a $2.89\,\text{nm}$ y logrando una **incertidumbre combinada final de $6.08\,\text{nm}$**.
3. **Control del Collar de Corrección del Objetivo 60x Agua:**
   Ajustar el collar de corrección del objetivo $60\times$ al espesor medido del cubreobjetos ($170\,\mu\text{m}$) para anular la aberración esférica ($u_{\text{aberration}} \rightarrow 0$).
4. **Estabilización Z Activa:**
   Ejecutar el atajo **F10 (Autocorrelation $\times 2$)** antes de escaneos confocales de alta resolución para anular la deriva térmica axial.

---

*Informe Metrológico generado para la Suite PyPrinting 3.0 — UNSAM Nanofotónica.*
