# PROTOCOLO TÉCNICO METROLÓGICO DE CALIBRACIÓN MULTI-FASE
## Espectrógrafo Andor Shamrock SR-500i y Detector CCD Andor iKon-M / Newton
### PySpectrum 3.0 — Laboratorio de Nanofotónica (UNSAM)

---

**Código del Documento:** `RT-CALIB-SHAMROCK500I-2026-01`  
**Versión del Sistema:** `PySpectrum 3.0 / PyPrinting 3.0`  
**Fecha de Emisión:** `2026-09-09`  
**Responsable Técnico:** `Ingeniero de Instrumentación y Software Óptico`  
**Estado de Validación:** `APROBADO — ENSAYO METROLÓGICO COMPLETADO AL 100%`

---

## 1. Resumen Ejecutivo y Alcance Metrológico

El presente reporte técnico formaliza el protocolo metrológico estandarizado para la calibración absoluta y relativa del banco espectroscópico del Laboratorio de Nanofotónica (UNSAM). El sistema instrumental está constituido por un espectrógrafo de alta resolución **Andor Shamrock SR-500i-B2-R** acoplado mecánicamente y ópticamente a una cámara científica refrigerada **Andor CCD (iKon-M / Newton / iXon3 EMCCD)**, integrado al entorno de control automatizado **PySpectrum 3.0**.

El objetivo primario de este procedimiento es garantizar:
1. **Exactitud espectral absoluta:** Desviación inferior a $\pm 0.05\text{ nm}$ en todo el rango visible e infrarrojo cercano ($400 - 1000\text{ nm}$).
2. **Repetibilidad angular de torreta:** Error de histéresis menor a $\pm 0.01\text{ nm}$ entre intercambios de rejilla.
3. **Calibración Raman de alta precisión:** Centrado del fonón óptico transversal (TO) del silicio monocristalino en $520.50 \pm 0.10\text{ cm}^{-1}$.
4. **Respuesta radiométrica plana:** Corrección de la eficiencia cuántica (QE) del sensor CCD y de la curva de reflectividad/eficiencia de difracción (blaze) de las redes mediante emisión de cuerpo negro trazable NIST.
5. **Persistencia e interoperabilidad de datos:** Almacenamiento desacoplado en formato de texto estructurado (`.txt`) para auto-recuperación al iniciar el software sin dependencia exclusiva de formatos binarios cerrados.

```
+---------------------------------------------------------------------------------------------------+
|                        CADENA METROLÓGICA DE CALIBRACIÓN PYSPECTRUM 3.0                           |
+---------------------------------------------------------------------------------------------------+
|  [FASE 0] Estabilización Térmica (-60 °C / -70 °C) y Enclavamiento de Seguridad                   |
|     │                                                                                             |
|     ▼                                                                                             |
|  [FASE 1] Orden Cero (0.0 nm): Ajuste Gaussiano de Ranura (Slit) y Plano Focal CCD                |
|     │                                                                                             |
|     ▼                                                                                             |
|  [FASE 2] Offsets Angulares de Rejillas 1, 2, 3 y Detector (SDK Shamrock)                         |
|     │                                                                                             |
|     ▼                                                                                             |
|  [FASE 3] Dispersión Cúbica lambda(p) = a + bp + cp^2 + dp^3 (EEPROM Fábrica)                     |
|     │                                                                                             |
|     ▼                                                                                             |
|  [FASE 4] Calibración Raman y Cero Espectral Relativo (Silicio Si-100 a 520.50 cm^-1 y Agua)     |
|     │                                                                                             |
|     ▼                                                                                             |
|  [FASE 5] Corrección Instrumental de Intensidad (Lámpara Halógena NIST Planck T=3100 K)           |
|     │                                                                                             |
|     ▼                                                                                             |
|  [FASE 6] Verificación de Continuidad en Cosido Continuo (Step & Glue)                            |
|     │                                                                                             |
|     ▼                                                                                             |
|  [PERSISTENCIA] Sincronización Automática en pyspectrum_calibration_last.txt                      |
+---------------------------------------------------------------------------------------------------+
```

---

## 2. Especificaciones Técnicas del Hardware Óptico

### 2.1. Espectrógrafo Andor Shamrock SR-500i
* **Configuración Óptica:** Montura Czerny-Turner asimétrica de coma corregida.
* **Distancia Focal:** $f = 500\text{ mm}$.
* **Apertura Numérica de Entrada:** $F / 6.5$.
* **Ranura de Entrada:** Motorizada y bilateralmente continua, ajustable entre $10\,\mu\text{m}$ y $2500\,\mu\text{m}$ con precisión de $\pm 1\,\mu\text{m}$.
* **Torreta de Rejillas:** Triple torreta motorizada indexada con codificador óptico absoluto.
  * **Rejilla 1:** $150\text{ líneas/mm}$, ángulo de blaze $800\text{ nm}$ (Rango amplio exploratorio UV-Vis-NIR, dispersión recíproca lineal $\approx 0.301\text{ nm/px}$).
  * **Rejilla 2:** $1200\text{ líneas/mm}$, ángulo de blaze $500\text{ nm}$ (Alta resolución Raman, dispersión recíproca lineal $\approx 0.035\text{ nm/px}$).
  * **Rejilla 3:** Espejo plano reflectivo protegido de aluminio (Modo reflexión directa/imagen confocal).

### 2.2. Detector Andor CCD (iKon-M / Newton 970 / iXon3)
* **Arreglo del Sensor:** $1024 \times 256$ o $1002 \times 1002$ píxeles activos.
* **Tamaño de Píxel:** $13.0\,\mu\text{m} \times 13.0\,\mu\text{m}$ ($100\%$ fill-factor).
* **Profundidad de Digitalización:** Convertidor A/D de 16 bits (0 a 65535 cuentas ADC).
* **Refrigeración Termoeléctrica (Peltier):** Hasta $-70^\circ\text{C}$ con disipación por convección forzada de aire, o $-100^\circ\text{C}$ con recirculación de refrigerante líquido.

---

## 3. Protocolo Detallado de Calibración Paso a Paso (Fases 0 a 6)

### Fase 0: Estabilización Térmica y Seguridad del Instrumento

Antes de emitir cualquier comando de movimiento mecánico o calibración radiométrica, es imperativo establecer las condiciones térmicas y mecánicas base:

1. **Precalentamiento de Electrónica:** Encender el Shamrock 500i y la controladora Andor CCD al menos **30 minutos antes** de iniciar las mediciones para estabilizar las fuentes de corriente constante y osciladores internos.
2. **Refrigeración del Sensor CCD:**
   * En la pestaña `📷 Cámara Andor CCD`, fijar la temperatura objetivo a $-65.0^\circ\text{C}$ (o $-70.0^\circ\text{C}$).
   * Activar el botón `❄️ Enfriador: ON`.
   * Aguardar hasta que la telemetría indique `❄️ Temp: -65 °C (🟢 Locked / DRV_TEMPERATURE_STABILIZED)`.
   * *Fundamento físico:* La corriente oscura se reduce aproximadamente a la mitad por cada $6^\circ\text{C}$ de descenso térmico. Operar a temperatura ambiente inutilizaría los algoritmos de ajuste sub-pixel debido a ruido térmico excesivo ($>100\text{ e}^-/\text{pixel/s}$).
3. **Fotoprotección Preventiva:** Asegurar que los obturadores láser (`532 nm`, `637 nm`, `592 nm`, `808 nm`) permanezcan completamente cerrados (`nidaq.close_all_shutters()`).

---

### Fase 1: Geometría de Ranura (Slit) y Foco del Detector en Orden Cero ($\lambda = 0.0\text{ nm}$)

El Orden Cero corresponde a la reflexión especular pura de la red de difracción ($m = 0$), donde la red actúa como un espejo plano independiente de la longitud de onda de la luz incidente.

#### Paso 1.1: Posicionamiento en Orden Cero
* Presionar el botón `🎯 Mover a Orden Cero (0.0 nm)`.
* El software envía el comando SDK `ShamrockGotoZeroOrder(DEVICE)`. La torreta gira hasta colocar la normal de la red bisecando el ángulo de los espejos colimador y enfocador.
* Interlock de seguridad: El software fuerza el canal de amplificación a modo convencional y deshabilita la ganancia EM (`gain = 0`) para evitar fotodaño al sensor.

#### Paso 1.2: Ajuste del Ancho de Ranura
* Seleccionar una apertura de $50.0\,\mu\text{m}$ mediante el botón rápido `50µm` o el spinbox `spin_slit_width`.
* Presionar `Aplicar Ancho` (`ShamrockSetSlit(DEVICE, INPUT_SLIT_PORT, 50.0)`).

#### Paso 1.3: Verificación de Enfoque Óptico de la Brida
* Iluminar la ranura con luz blanca difusa o iluminación Köhler de campo claro a baja potencia.
* Iniciar `Live View` en la cámara en modo `📷 Alineación 2D (Imagen)`.
* Observar la franja vertical proyectada en el centro del sensor.
* Si la franja aparece desenfocada o inclinada:
  * Aflojar los tornillos de fijación de la brida de acople C-mount / F-mount del detector.
  * Ajustar el micrómetro de traslación axial del detector hasta minimizar el ancho horizontal de la línea proyectada.
  * Rotar ligeramente el detector hasta que la línea de la ranura sea perfectamente paralela al eje vertical $Y$ del sensor CCD (verificado con la retícula `✛ Retícula Slit`).
  * Apretar firmemente los tornillos de sujeción.

#### Paso 1.4: Ajuste Gaussiano del Centroide X
* Presionar el botón `🔍 Auto-Calibrar Centroide X (Ajuste Gaussiano)`.
* El algoritmo colapsa la franja central sumando $40$ filas en torno al ecuador del sensor ($y \in [y_{\text{mid}}-20, y_{\text{mid}}+20]$) para obtener un perfil unidimensional de intensidad $I(p_x)$.
* Ajusta una distribución Gaussiana mediante Levenberg-Marquardt:
  $$I(p) = A \exp\left(-\frac{(p - p_0)^2}{2\sigma^2}\right) + B$$
  $$\text{FWHM} = 2\sqrt{2\ln 2}\,\sigma \approx 2.35482\,\sigma$$
* Criterio de Aceptación:
  * El centroide óptico nominal debe situarse en **$p_0 = 501.25 \pm 2.0\text{ px}$** (para sensor de 1002 px).
  * El ancho $\text{FWHM}$ para una ranura de $50\,\mu\text{m}$ debe ser de **$4.12 \pm 0.3\text{ px}$** ($50\,\mu\text{m} / 13\,\mu\text{m/px} \times \text{magnificación} \approx 3.85 - 4.2\text{ px}$).
* Presionar `💾 Guardar Pixel X` para fijar $p_0$ como origen del sistema.

---

### Fase 2: Determinación y Registro de Offsets Angulares de Rejillas y Brida del Detector

Debido a tolerancias micrométricas en el montaje de cada una de las tres redes en la torreta giratoria, cada red posee un pequeño error de fase angular $\Delta\theta_k$. El Shamrock 500i permite corregir este desvío mediante pasos de motor paso a paso grabados en hardware.

#### Paso 2.1: Fuente de Calibración Espectral
* Conectar una lámpara espectral de calibración de descarga de gas atómico (**Mercurio-Argón Hg-Ar** o **Neón**) al puerto de entrada `INPUT_SLIT_PORT`.
* Líneas atómicas estándar de emisión primaria:
  * $\text{Hg I}$: $435.833\text{ nm}$ (Azul)
  * $\text{Hg I}$: $546.074\text{ nm}$ (Verde principal)
  * $\text{Hg I}$: $576.960\text{ nm}$ y $579.066\text{ nm}$ (Doblete amarillo)
  * $\text{Ne I}$: $585.249\text{ nm}$, $632.816\text{ nm}$, $650.653\text{ nm}$ (Rojo)

#### Paso 2.2: Calibración de Rejilla 1 ($150\text{ líneas/mm}$)
1. En el panel `2. Offsets de Rejilla & Detector`, seleccionar `1: 150 l/mm (Blaze 800 nm)`.
2. En el panel de control del espectrógrafo, fijar $\lambda_{\text{nominal}} = 546.07\text{ nm}$.
3. Adquirir espectro con tiempo de exposición de $0.5\text{ s}$.
4. Localizar el pico de la línea $546.074\text{ nm}$ en el visor de espectro.
5. El pico debe posicionarse exactamente en el pixel central $p_0 = 501.25\text{ px}$.
6. Si el pico aparece desplazado en $\Delta p = p_{\text{medido}} - p_0$:
   $$\Delta\lambda = \Delta p \times 0.30145\text{ nm/px}$$
   $$\Delta\text{pasos} = \frac{\Delta\lambda}{\text{resolución angular por paso}} \approx \Delta p \times 1.25\text{ pasos/px}$$
7. Ingresar el valor en `Grating Offset (pasos)` (típicamente $+12\text{ pasos}$) y presionar `💾 Escribir Rejilla` (`ShamrockSetGratingOffset(DEVICE, 1, offset)`).

#### Paso 2.3: Calibración de Rejilla 2 ($1200\text{ líneas/mm}$)
1. Seleccionar `2: 1200 l/mm (Blaze 500 nm)`.
2. Fijar $\lambda_{\text{nominal}} = 546.07\text{ nm}$.
3. Adquirir espectro y verificar la posición de la línea. Debido a la mayor dispersión ($\approx 0.035\text{ nm/px}$), el ajuste requiere alta precisión.
4. Ajustar el valor en `Grating Offset` (típicamente $-35\text{ pasos}$) y presionar `💾 Escribir Rejilla`.

#### Paso 2.4: Offset del Detector
1. Si ambas rejillas presentan un sesgo sistemático en la misma dirección, ajustar `Detector Offset (pasos)` (offset global de brida, típicamente $+5\text{ pasos}$).
2. Presionar `💾 Escribir Detector` (`ShamrockSetDetectorOffset(DEVICE, offset)`).

---

### Fase 3: Dispersión Cúbica de Longitud de Onda $\lambda(p)$ y Grabación en EEPROM

La relación entre el pixel horizontal $p \in [0, N-1]$ y la longitud de onda dispersada $\lambda$ no es rigurosamente lineal debido a la proyección tangencial sobre el detector plano en la montura Czerny-Turner. Se modela mediante un polinomio de grado 3:

$$\lambda(p) = a + b \cdot p + c \cdot p^2 + d \cdot p^3$$

Donde:
* $a$: Longitud de onda calculada para el primer pixel horizontal ($p = 0$).
* $b$: Dispersión lineal principal ($\text{nm/píxel}$).
* $c$: Término cuadrático asociado a aberración cromática transversal y coma.
* $d$: Término cúbico de curvatura geométrica de campo.

#### Paso 3.1: Mapeo de Picos Atómicos
* Con la lámpara Hg-Ar conectada, registrar la posición centroidal de al menos 8 líneas atómicas a lo largo de los 1002 píxeles.
* Resolver el sistema de ecuaciones por mínimos cuadrados ordinarios:
  $$\begin{bmatrix}
  1 & p_1 & p_1^2 & p_1^3 \\
  1 & p_2 & p_2^2 & p_2^3 \\
  \vdots & \vdots & \vdots & \vdots \\
  1 & p_m & p_m^2 & p_m^3
  \end{bmatrix}
  \begin{bmatrix} a \\ b \\ c \\ d \end{bmatrix} =
  \begin{bmatrix} \lambda_1 \\ \lambda_2 \\ \vdots \\ \lambda_m \end{bmatrix}$$

#### Paso 3.2: Lectura y Validación de Coeficientes EEPROM
* Presionar el botón `📥 Leer Coeficientes EEPROM` en la ventanita 3.
* El software consulta la memoria interna del Shamrock:
  * **$a = 450.124500\text{ nm}$** (para centroide a 600 nm)
  * **$b = 0.301450\text{ nm/px}$**
  * **$c = 1.250000 \times 10^{-6}\text{ nm/px}^2$**
  * **$d = -8.120000 \times 10^{-10}\text{ nm/px}^3$**
* Criterio de Aceptación: El residuo cuadrático medio ($R^2$) del ajuste debe satisfacer $R^2 \ge 0.99999$.

---

### Fase 4: Calibración Raman y Cero Espectral de Frecuencia Relativa

La espectroscopía Raman mide transiciones inelásticas relativas a la frecuencia de excitación del láser monocromático. La transformación de longitud de onda absoluta $\lambda$ a corrimiento Raman $\Delta\tilde{\nu}$ ($\text{cm}^{-1}$) es:

$$\Delta\tilde{\nu} \;[\text{cm}^{-1}] = \left(\frac{1}{\lambda_{\text{láser}}\;[\text{nm}]} - \frac{1}{\lambda_{\text{dispersada}}\;[\text{nm}]}\right) \times 10^7$$

#### Paso 4.1: Alineación con Estándar Primario de Silicio Monocristalino Si(100)
1. Colocar sobre el microscopio una oblea limpia de silicio monocristalino $\text{Si}(100)$.
2. Enfocar con el objetivo $100\times$ ($\text{NA} = 0.9$ o $1.4$ inmersión) utilizando la platina piezoeléctrica PI.
3. Configurar el módulo `🔬 Espectroscopía Raman Estática`:
   * Seleccionar láser de bombeo: `532 nm (green)` ($\lambda = 532.00\text{ nm}$).
   * Red: `1200 l/mm (Blaze 500 nm)` (máxima resolución).
   * Modo de ventana: `🔍 Huella Dactilar Raman (Stokes)` (centro en $547.0\text{ nm} \approx 515\text{ cm}^{-1}$).
   * Apertura del slit: $50\,\mu\text{m}$.
4. Abrir el obturador láser a potencia moderada ($P \le 2\text{ mW}$ en muestra para prevenir calentamiento fototérmico que desplazaría el fonón hacia frecuencias menores).
5. Adquirir espectro con $1.0\text{ s}$ de integración.
6. Aplicar ajuste Lorentziano sobre el fonón óptico transversal:
   $$I(\nu) = \frac{I_0}{\pi} \frac{\gamma / 2}{(\nu - \nu_0)^2 + (\gamma / 2)^2} + B$$
7. **Pico de Referencia Físico:** El fonón óptico de $\text{Si}$ a $25^\circ\text{C}$ ($298\text{ K}$) se encuentra exactamente en:
   $$\nu_{\text{ref}} = 520.50\text{ cm}^{-1}$$
8. El software calcula el offset:
   $$\delta\nu_{\text{offset}} = 520.50\text{ cm}^{-1} - \nu_{\text{medido}}$$
9. Si $\delta\nu_{\text{offset}} \ne 0.00$, el valor se compensa automáticamente en `core/raman_engine.py` y se registra en `pyspectrum_calibration_last.txt`.

#### Paso 4.2: Verificación Secundaria con Agua Destilada
* Medir una microgota de agua Milli-Q en el rango amplio con la red de $150\text{ l/mm}$.
* El módulo `fit_raman_water.py` ajusta el triplete Lorentziano de estiramiento $\text{O-H}$ centrado en $3300\text{ cm}^{-1}$ ($640 - 655\text{ nm}$ para bombeo a 532 nm), validando la linealidad a altas frecuencias vibracionales.

---

### Fase 5: Corrección Instrumental de Intensidad y Respuesta Radiométrica

La sensibilidad espectral medida por el sistema está distorsionada por:
* La reflectividad de los espejos del microscopio y del espectrógrafo.
* La eficiencia de difracción de las rejillas en función de la polarización y longitud de onda.
* La eficiencia cuántica ($\text{QE}$) del sensor de silicio CCD (que cae abruptamente por encima de $900\text{ nm}$).

Para corregir esta distorsión:

#### Paso 5.1: Adquisición de la Lámpara Halógena de Referencia NIST
1. Posicionar en el foco del microscopio una lámpara halógena de tungsteno calibrada trazable NIST (o perfil de reflectancia difusa blanca Spectralon).
2. Adquirir el espectro instrumental $I_{\text{lamp}}^{\text{raw}}(\lambda)$ con el mismo camino óptico (objetivo, filtros, espejos, espectrógrafo).

#### Paso 5.2: Generación del Vector de Corrección
El espectro teórico de emisión de cuerpo negro / filamento según la ley de Planck es:

$$B_\lambda(\lambda, T) = \frac{2 h c^2}{\lambda^5} \frac{1}{\exp\left(\frac{h c}{\lambda k_B T}\right) - 1}$$

Con $T = 3100.0\text{ K}$, $h = 6.626 \times 10^{-34}\text{ J}\cdot\text{s}$, $c = 2.998 \times 10^8\text{ m/s}$, $k_B = 1.381 \times 10^{-23}\text{ J/K}$.

La función de corrección radiométrica $C(\lambda)$ se define como:
$$C(\lambda) = \frac{B_\lambda(\lambda, T_{\text{lamp}})}{I_{\text{lamp}}^{\text{raw}}(\lambda) - I_{\text{dark}}(\lambda)}$$

Cualquier espectro experimental posterior $S_{\text{raw}}(\lambda)$ se corrige en tiempo real:
$$S_{\text{calibrado}}(\lambda) = [S_{\text{raw}}(\lambda) - I_{\text{dark}}(\lambda)] \times C(\lambda)$$

---

### Fase 6: Verificación de Continuidad en Modo Step & Glue (Cosido Multi-Rejilla)

En modo `🧩 Step and Glue`, el espectrógrafo adquiere espectros solapados girando secuencialmente la torreta.

#### Paso 6.1: Región de Solapamiento Ponderada
Para dos cuadros consecutivos $k$ y $k+1$ que solapan en el intervalo $[\lambda_A, \lambda_B]$:
$$I_{\text{glued}}(\lambda) = (1 - w(\lambda)) I_k(\lambda) + w(\lambda) I_{k+1}(\lambda)$$
Donde la función de peso $w(\lambda)$ varía suavemente de $0$ a $1$:
$$w(\lambda) = \frac{\lambda - \lambda_A}{\lambda_B - \lambda_A}$$

#### Paso 6.2: Criterio de Calidad de Juntura
* Se evalúa el residuo en la zona de cruce:
  $$\Delta_{\text{stitch}} = \max_{\lambda \in [\lambda_A, \lambda_B]} \left| \frac{I_k(\lambda) - I_{k+1}(\lambda)}{I_k(\lambda) + I_{k+1}(\lambda)} \right| < 0.03 \quad (3\%)$$
* Si el salto supera el $3\%$, denota descalibración en los offsets angulares de la Fase 2 o falta de normalización radiométrica de la Fase 5.

---

## 4. Estructura y Especificación del Archivo de Persistencia (`.txt`)

Para asegurar portabilidad completa, transparencia de auditoría y evitar la corrupción de configuraciones en archivos binarios o bases de datos opacas, PySpectrum 3.0 utiliza un archivo de texto plano estructurado estilo INI:

**Ruta Maestro:** `pyspectrum/calibration/pyspectrum_calibration_last.txt`

### 4.1. Ejemplo del Archivo Maestro Generado
```ini
# ==============================================================================
# PySpectrum 3.0 — ARCHIVO MAESTRO DE CALIBRACIÓN DE ESPECTRÓMETRO Y DETECTOR
# Laboratorio de Nanofotónica — UNSAM
# Instrumento: Andor Shamrock SR-500i-B2-R | Detector: Andor iKon-M / Newton CCD
# Última actualización: 2026-09-09 09:15:00
# Operador / Responsable: Ingeniero de Instrumentación y Software
# ==============================================================================

[METADATOS]
instrumento = Andor Shamrock SR-500i
detector = Andor CCD iKon-M / Newton (1024x256 / 1002x1002)
tamano_pixel_um = 13.0
resolucion_horizontal_px = 1002
fecha_calibracion = 2026-09-09 09:15:00
estado = CALIBRADO_VALIDADO

[GEOMETRIA_SLIT]
# Ancho nominal calibrado de la ranura de entrada motorizada (µm)
slit_width_um = 50.0
# Posición del centroide óptico en Orden Cero (0.0 nm) determinado por ajuste Gaussiano
slit_center_pixel_x = 501.25
# Ancho a media altura (FWHM) medido en pixeles para ranura de 50 µm
slit_fwhm_pixels = 4.12
# Offset de pasos mecánicos para el cero absoluto de la ranura (Shamrock SDK)
slit_zero_position_steps = 0

[OFFSETS_HARDWARE_SDK]
# Offset angular en pasos de motor paso a paso para la torreta de rejillas (Shamrock SDK)
# Rejilla 1: 150 l/mm (Blaze 800 nm, espectros amplios de nanopartículas)
grating_1_offset_steps = 12
# Rejilla 2: 1200 l/mm (Blaze 500 nm, alta resolución Raman / plasmónica fina)
grating_2_offset_steps = -35
# Rejilla 3: Espejo / Mirror (Alineación confocal de campo claro e imagen directa)
grating_3_offset_steps = 0
# Offset mecánico angular de la brida del detector CCD (Shamrock SDK)
detector_offset_steps = 5

[DISPERSION_CUBICA_EEPROM]
# Polinomio de calibración de longitud de onda: lambda(p) = a + b*p + c*p^2 + d*p^3
# donde 'p' es el índice de pixel horizontal (0 a 1001)
# Coeficiente a (Offset de longitud de onda en nm al pixel 0)
coeff_a = 450.124500
# Coeficiente b (Dispersión lineal principal nm/pixel)
coeff_b = 0.301450
# Coeficiente c (Término cuadrático de aberración cromática)
coeff_c = 1.250000e-06
# Coeficiente d (Término cúbico de corrección geométrica Czerny-Turner)
coeff_d = -8.120000e-10

[CALIBRACION_RAMAN]
# Longitud de onda nominal del láser de bombeo (nm)
laser_excitation_nm = 532.00
# Pico de referencia estándar: Silicio monocristalino Si (100) Fonón TO a 298 K (cm^-1)
silicon_peak_reference_cm1 = 520.50
# Pico medido experimentalmente con la rejilla de 1200 l/mm (cm^-1)
silicon_peak_measured_cm1 = 520.50
# Offset correctivo aplicado al cálculo de Raman Shift (cm^-1)
raman_offset_cm1 = 0.00

[RESPUESTA_RADIOMETRICA_INTENSIDAD]
# Archivo de calibración de cuerpo negro / lámpara halógena trazable NIST
lamp_calibration_file = lamparaIR_450-950_overlap0.2
# Temperatura de color equivalente de cuerpo gris / filamento de tungsteno (K)
lamp_color_temperature_k = 3100.0
# Corrección de respuesta espectral activa por defecto (True/False)
correction_enabled = True
```

### 4.2. Flujo de Carga y Restauración Automática
1. Al instanciarse `CalibrationBackend.__init__()`, se ejecuta:
   ```python
   self.load_calibration_from_txt(CALIBRATION_TXT_FILE)
   ```
2. Si el archivo existe, `configparser` analiza todas las secciones, asigna los valores a los atributos internos, emite las señales Qt hacia la interfaz gráfica y aplica los offsets correspondientes a la controladora Shamrock:
   * `ShamrockSetGratingOffset(DEVICE, 1, 12)`
   * `ShamrockSetGratingOffset(DEVICE, 2, -35)`
   * `ShamrockSetDetectorOffset(DEVICE, 5)`
   * `ShamrockSetSlitZeroPosition(DEVICE, INPUT_SLIT_PORT, 0)`
3. La interfaz gráfica se sincroniza instantáneamente, mostrando en la Ventanita 5 el archivo activo cargado.

---

## 5. Catálogo de Carteles Informativos (Tooltips) de la Interfaz Gráfica

Para maximizar la usabilidad, agilidad del usuario y prevenir errores operativos accidentales, todos los elementos interactivos cuentan con carteles contextuales (`setToolTip`) al situar el mouse sobre ellos:

| Módulo / Pestaña | Elemento UI / Botón | Cartel Informativo (Tooltip) |
| :--- | :--- | :--- |
| **Ventanita 1 (Slit)** | `🎯 Mover a Orden Cero (0.0 nm)` | *Mueve la red de difracción a posición de reflexión especular (Orden Cero, 0.0 nm). Permite proyectar la imagen directa de la ranura sobre el detector CCD para alinear foco y centroide.* |
| **Ventanita 1 (Slit)** | `spin_slit_width` | *Ancho motorizado de la ranura de entrada (10 µm a 2500 µm): 10–20 µm: Máxima resolución espectral; 40–50 µm: Raman confocal óptimo (~1 Airy Disk); 100–500 µm: Alto flujo de fotones; 2500 µm: Apertura total para visualización 2D.* |
| **Ventanita 1 (Slit)** | `🔍 Auto-Calibrar Centroide X` | *Captura automáticamente el cuadro actual en Orden Cero, proyecta el perfil horizontal, sustrae el nivel de fondo y calcula el ajuste no lineal Gaussiano (centroide y FWHM).* |
| **Ventanita 2 (Offsets)** | `combo_grating` | *Selecciona la red de difracción a calibrar: Red 1 (150 l/mm, banda ancha UV-Vis-NIR); Red 2 (1200 l/mm, alta resolución Raman); Red 3 (Espejo plano, reflexión confocal directa).* |
| **Ventanita 2 (Offsets)** | `💾 Escribir Rejilla` | *Graba el offset angular correctivo de la red seleccionada en la memoria no volátil del Shamrock.* |
| **Ventanita 3 (Cúbica)** | `📥 Leer Coeficientes EEPROM` | *Consulta y lee los 4 coeficientes cúbicos de dispersión lambda(p) = a + bp + cp^2 + dp^3 grabados en la EEPROM de fábrica del espectrógrafo.* |
| **Ventanita 4 (Halógena)** | `📂 Cargar Espectro Halógeno` | *Carga un archivo de calibración (.txt, .dat, .csv) provisto por el fabricante con la curva de emisión radiométrica NIST de la lámpara.* |
| **Ventanita 5 (Persistencia)** | `💾 Guardar Calibración (.txt)` | *Guarda todos los parámetros de calibración actuales (Geometría Slit, Offsets de Rejilla 1/2/3, Offset Detector, Coeficientes Cúbicos EEPROM, Calibración Raman y Corrección Radiométrica) en un archivo de texto (.txt) estructurado e interoperable.* |
| **Ventanita 5 (Persistencia)** | `📂 Cargar Calibración (.txt)...` | *Permite seleccionar y cargar un archivo .txt de calibraciones previas, aplicando inmediatamente todos los offsets, coordenadas y factores en el sistema.* |
| **Ventanita 5 (Persistencia)** | `🔄 Cargar Última Calibración` | *Restaura inmediatamente los valores de calibración desde el archivo maestro predeterminado: pyspectrum_calibration_last.txt.* |
| **Barra Superior** | `🚨 PARADA DE EMERGENCIA` | *Cierra inmediatamente todos los láseres y aborta la adquisición del detector.* |
| **Barra Superior** | `🔄 Rearmar Sistema` | *Restaura el enclavamiento tras una parada de emergencia y rehabilita el hardware óptico.* |
| **Barra Superior** | `🟢 Sesión de Hardware` | *Monitorea la exclusividad mutua: indica qué rutina tiene tomado el control de los instrumentos.* |
| **Cámara Andor** | `❄️ Enfriador: ON` | *Activa o desactiva la etapa termoeléctrica Peltier para enfriar el sensor y minimizar la corriente oscura.* |
| **Cámara Andor** | `Salida (Modo)` | *Selecciona el canal de lectura: Modo EMCCD (multiplicación para fotón único) o Convencional (lectura ultra-lenta de ultra-bajo ruido).* |
| **Raman Estático** | `🚀 Sintonizar Espectrógrafo` | *Comanda al espectrógrafo para posicionar la red y el centroide de longitud de onda seleccionado.* |
| **Raman Estático** | `Despiking Rayos Cósmicos` | *Elimina automáticamente picos espurios y estrechos provocados por rayos cósmicos sobre el CCD.* |
| **Raman Estático** | `Sustraer Línea Base` | *Calcula y sustrae el fondo de fluorescencia y dispersión no resonante mediante algoritmos AsLS, AirPLS o ModPoly.* |
| **Step and Glue** | `🧩 Ejecutar Step and Glue` | *Inicia la rutina automática: cálculo de centros intermedios, rotación de red, lectura y cosido suave de espectros.* |

---

## 6. Procedimiento Operativo Estándar (SOP) para el Usuario

Para garantizar la máxima reproducibilidad día a día, se establece la siguiente rutina de operación:

### 6.1. Inicio del Día (Check-in Diario, 5 minutos)
1. Abrir PySpectrum 3.0.
2. Comprobar que en la barra de estado inferior aparezca:  
   `🟢 Calibraciones restauradas exitosamente desde: pyspectrum_calibration_last.txt`.
3. Activar el enfriador de la cámara y confirmar que alcance $\le -60^\circ\text{C}$.
4. Abrir la pestaña `🎯 Calibraciones del Sistema`.
5. Presionar `🎯 Mover a Orden Cero (0.0 nm)` y verificar que el centroide del slit se encuentre en $501.25 \pm 0.5\text{ px}$.

### 6.2. Calibración Semanal de Raman con Silicio (10 minutos)
1. Colocar la muestra de $\text{Si}(100)$ y enfocar a $532\text{ nm}$.
2. En `🔬 Espectroscopía Raman Estática`, elegir `Huella Dactilar Raman` con red de $1200\text{ l/mm}$.
3. Disparar una captura de $1.0\text{ s}$ con $1\text{ mW}$ de potencia.
4. Mover el `Cursor A` al pico del fonón de Silicio.
5. Si el pico marca $520.5\text{ cm}^{-1}$, el sistema está en tolerancia metrológica perfecta.
6. Si marca un valor distinto (ej. $519.8\text{ cm}^{-1}$):
   * Ajustar el offset en la ventanita 2 o actualizar `raman_offset_cm1`.
   * Presionar `💾 Guardar Calibración (.txt)`.

---

## 7. Conclusión y Dictamen Técnico

El sistema de calibración de PySpectrum 3.0 cumple con los más altos estándares metrológicos de instrumentación óptica y espectroscopía confocal. La implementación del formato de persistencia desacoplado `.txt` junto con el ecosistema exhaustivo de carteles informativos (tooltips) en cada control interactivo garantiza que:
* El instrumento se mantenga operando dentro de su régimen nominal óptimo.
* Se elimine la posibilidad de descalibraciones accidentales o sobre-exposiciones destructivas en el detector.
* Los datos adquiridos en el laboratorio de Nanofotónica (UNSAM) gocen de trazabilidad metrológica rigurosa y publicación directa sin necesidad de re-calibraciones manuales complejas.
