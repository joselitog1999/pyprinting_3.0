# Módulo 12 — Analizador y Procesador Espectral SIF (Andor Solis)

## 1. Descripción General
El **Analizador y Procesador de Archivos SIF** (`sif_analyzer.py` y `core/sif_processor.py`) es un módulo avanzado diseñado específicamente para cargar, procesar, analizar y exportar archivos espectrales `.sif` adquiridos con el software **Andor Solis** y espectrómetros Czerny-Turner (Andor Shamrock SR-500i con detector EMCCD iXon3).

El módulo soporta tanto adquisiciones binnadas verticalmente (**1D Full Vertical Binning - FVB**) como adquisiciones resueltas espacialmente a lo largo de la ranura de entrada (**2D Multi-pixel / Slit Imaging**), permitiendo operar archivos individuales o **Sets de archivos** completos con propagación rigurosa de errores fotónicos e instrumentales.

---

## 2. Tipos de Archivos y Modos de Adquisición

| Tipo de Adquisición | Dimensiones | Descripción y Procesamiento |
|---|---|---|
| **1D Binned (FVB)** | `(1, 1, N_λ)` | Un único vector de intensidades vs longitud de onda $\lambda$. Proviene de la integración física de cargas en el chip CCD (`ybin > 1`, ej. 53 px). |
| **2D Multi-pixel (Slit Image)** | `(1, N_y, N_λ)` | Matriz espacialmente resuelta (ej. 71 píxeles verticales en el eje $Y$ vs 5020 puntos de $\lambda$). Permite selección de ROI interactivo y cálculo pixel-contra-pixel. |

### Corrección de Calibración de Longitud de Onda
En archivos 2D multi-pixel, la librería estándar `sif-parser` presenta una anomalía al interpretar `ImageLength` total ($N_y \times N_\lambda$) como el ancho espectral, generando ejes erróneos de hasta 35,000 nm.
El motor `core/sif_processor.py` corrige esta discrepancia evaluando el polinomio de dispersión cúbica de Shamrock directamente sobre el ancho de dispersión $N_\lambda = \text{size}[0]$, restituyendo con precisión sub-nanométrica el rango óptico experimental (ej. 400.0 nm a 900.0 nm).

---

## 3. Flujo de Trabajo con Conjuntos de Archivos (Sets)

En experimentos de nanofotónica y plasmónica, los espectros se agrupan en **Sets**:
1. **Archivo 0 (Maestro / Calibración)**:
   - Contiene la información de **Fondo del detector** (*Background - BG*) y **Lámpara de Referencia** (*Reference - Ref*).
2. **Archivos 1..N (Muestras)**:
   - Contienen la señal de cada nanoestructura, partícula o área irradiada (*Sample / Signal*).
3. **Casos especiales de compensación de deriva**:
   - Muestras que incluyen su propia referencia intercalada.

### Asignación Reactiva de Roles
El usuario puede asignar o alternar el rol semántico de cualquier archivo directamente en la tabla de la izquierda:
- `Muestra (Signal)`: Espectro bajo estudio.
- `Referencia (Ref)`: Emisión de la lámpara halógena/IR.
- `Fondo (BG)`: Corriente oscura o fondo ambiental.
- `Transmisión Medida (T_meas)`: Transmitancia calculada nativamente en Andor Solis.
- `Desactivado`: Excluido temporalmente del procesamiento.

El botón **"Auto-Roles"** escanea heurísticamente los nombres de archivo (`bg`, `dark`, `ref`, `lampara`, `trans`) y asigna automáticamente los roles iniciales.

---

## 4. Álgebra Espectral y Rutas de Cálculo 2D

### Ecuación de Transmitancia con Covarianza de Fondo
$$\text{Transmitancia } T(\lambda) = \frac{S(\lambda) - BG(\lambda)}{R(\lambda) - BG(\lambda)} \times 100\%$$

### Opciones de Ruta Espacial en Matrices 2D:
- **Ruta A (Pixel-a-Pixel en 2D $\to$ Promediar ROI)** *(Recomendada / Predeterminada)*:
  Normaliza canal por canal vertical en la ranura ($T(y, \lambda) = \frac{S(y, \lambda)-BG(y, \lambda)}{R(y, \lambda)-BG(y, \lambda)}$) para cancelar las aberraciones de curvatura del slit y gradientes gaussianos de iluminación antes de promediar las filas del ROI.
- **Ruta B (Promediar ROI en 1D $\to$ Operar)**:
  Reduce primero espacialmente la señal, referencia y fondo a vectores 1D y luego ejecuta la división.
  > [!WARNING]
  > **Advertencia de la Ruta B**: Al promediar verticalmente antes de normalizar, se asume iluminación espacial homogénea a lo largo del slit. Si el haz de iluminación o de referencia posee perfiles Gaussianos o aberraciones de curvatura espectral, la Ruta B puede introducir sesgos de normalización. La interfaz despliega un banner de advertencia explícito al seleccionar esta ruta.

### Noise Gate ($\epsilon$) contra Divergencias Asintóticas
En las regiones de corte de la lámpara (UV $< 420\text{ nm}$ o NIR $> 880\text{ nm}$), $R(\lambda) - BG(\lambda) \to 0$. El control **Noise Gate** enmascara automáticamente los puntos donde $R - BG \le \epsilon$, evitando divergencias infinitas que distorsionen la escala del gráfico.

---

## 5. Estadística de Promediado y Propagación de Errores

El software reporta estadísticas y propaga incertidumbres en 3 modalidades:
1. **Solo ROI (Espacial)**:
   - Media $\bar{I}_{\text{ROI}}(\lambda)$, Desviación estándar espacial $\sigma_{\text{ROI}}(\lambda)$, Error estándar de la media $\text{SEM} = \frac{\sigma}{\sqrt{N_y}}$.
2. **Solo Set (Temporal / Inter-medición)**:
   - Media $\bar{I}_{\text{set}}(\lambda)$, Desviación estándar del conjunto $\sigma_{\text{set}}(\lambda)$, $\text{SEM} = \frac{\sigma}{\sqrt{M}}$.
3. **ROI y Set**:
   - Varianza combinada que suma la dispersión entre muestras del set con la varianza media intra-ROI.

### Propagación Analítica en Transmitancia:
$$\sigma_T(\lambda) = |T(\lambda)| \cdot \sqrt{ \frac{\sigma_S^2 + \sigma_{BG}^2}{(S-BG)^2} + \frac{\sigma_R^2 + \sigma_{BG}^2}{(R-BG)^2} - 2\frac{\sigma_{BG}^2}{(S-BG)(R-BG)} }$$

### Torreta Real de 5 Objetivos del Laboratorio y Tren Óptico Relé 4f
El microscopio cuenta con un sistema relé afocal 4f ($f_1 = 250\,\text{mm}, f_2 = 200\,\text{mm} \implies \Gamma = 1.25\times$) acoplado a una lente de inyección de $f_{\text{spec}} = 250\,\text{mm}$ hacia la ranura del Shamrock 500i.
La magnificación efectiva en la ranura es $M_{\text{spec}} = \frac{312.5\,\text{mm}}{f_{\text{obj}}}$:

| Objetivo | NA | Inmersión | $f_{\text{obj}}$ | $M_{\text{spec}}$ | Escala Espacial Real |
|---|---|---|---|---|---|
| **Olympus MPLN 10x** | 0.25 | Aire ($n=1.0$) | 18.00 mm | $17.361\times$ | **0.7488 µm/px** |
| **Olympus 20x** | 0.40 | Aire ($n=1.0$) | 9.00 mm | $34.722\times$ | **0.3744 µm/px** |
| **Nikon CFI S Plan Fluor 40x** | 0.60 | Aire (Collar 0-2 mm) | 5.00 mm | $62.500\times$ | **0.2080 µm/px** |
| **Olympus LUMPlanFLN 60x W** | 1.00 | Agua ($n=1.333$) | 3.00 mm | $104.167\times$ | **0.1248 µm/px** |
| **Nikon S Plan Fluor 100x Oil** | 1.30 | Aceite ($n=1.515$) | 2.00 mm | $156.250\times$ | **0.0832 µm/px** |

El checkbox **"Calcular y Mostrar Área de Error"** dibuja un área semitransparente continua (*Error Ribbon*) entre $T - \sigma_T$ y $T + \sigma_T$ sin sobrecargar visualmente el trazado.

### Modelo Metrológico de Incertidumbre en Longitud de Onda $u_c(\lambda)$
Combina en cuadratura la apertura geométrica de la ranura de entrada ($w_{\text{slit}}$), la discretización del detector CCD ($13\,\mu\text{m}$) y el error residual del polinomio de calibración:
$$u_c(\lambda) = \sqrt{ \left(\frac{\Delta \lambda_{\text{slit}}}{\sqrt{12}}\right)^2 + \left(\frac{\delta \lambda_{\text{px}}}{\sqrt{12}}\right)^2 + u_{\text{calib}}^2 }$$
donde $\Delta \lambda_{\text{slit}} = \left(\frac{w_{\text{slit}}}{p_{\text{pixel}}}\right) \delta \lambda_{\text{px}}$. El valor de $u_c(\lambda)$ se reporta en el panel métrico y se exporta en las columnas de datos.

### Calibración Externa de Longitud de Onda
El botón **"📥 Cargar Calib (.txt)"** permite cargar archivos externos de calibración:
- Archivos Shamrock EEPROM / INI (como `pyspectrum_calibration_last.txt` con $\lambda(p) = a + bp + cp^2 + dp^3$).
- Tablas ASCII de 2 columnas `[pixel, lambda]` o 1 columna `[lambda]`.
- Listas de 4 coeficientes polinomiales.

---

## 6. Pipeline de Filtrado: Técnicas Tradicionales y Limpieza Adaptativa de Fondo

El analizador provee dos rutas de filtrado claramente diferenciadas y seleccionables:

### 1. Limpieza Adaptativa de Ruido de Fondo (Wiener / $\sigma_{BG}$) *(Opcional / Checkbox)*
- **Caracterización Empírica**: Extrae automáticamente del archivo de Fondo (*Background*) el offset térmico continuo, la varianza espacial vertical $\sigma_{BG}(\lambda)$ y la **Densidad Espectral de Potencia (PSD)** del ruido de lectura + disparo.
- **Filtro de Wiener Adaptativo**: En el dominio de Fourier, calcula la función de transferencia:
  $$H(f) = \frac{\max(0, P_Y(f) - \alpha \cdot P_N(f))}{P_Y(f)}$$
  Atenúa selectivamente las frecuencias espaciales donde domina el ruido de la cámara sin ensanchar los picos plasmónicos estrechos ni desplazar sus resonancias.
- **Despiking Adaptativo**: Reemplaza rayos cósmicos cuando $y(\lambda) - \text{mediana}(y) > k \cdot \sigma_{BG}(\lambda)$.
- **Inspector de PSD**: El botón **"🔍 Ver PSD"** abre un diálogo interactivo con la curva de densidad espectral de potencia y el desvío estándar local del sensor.

### 2. Técnicas Tradicionales (si la opción adaptativa está inactiva)
- **Savitzky-Golay**: Ajuste polinomial por tramos con preservación de momentos de área.
- **Fourier Low-Pass (FFT)**: Atenuación suave por filtro Butterworth de orden 3 con eliminación de fugas en bordes.
- **Media Móvil**: Convolución uniforme con corrección de extremos.
- **Despike Mediana Robusto**: Basado en MAD (Median Absolute Deviation).

---

## 7. Comparador de Sets y Residuos

- **Pestaña "Comparador de Sets"**: Superpone todas las curvas del set con paleta de colores distinguible, opciones de normalización a $[0, 1]$ o al máximo, y curva de Media del Set con banda de $\pm 1\sigma$.
- **Pestaña "Residuos"**: Calcula $T_{\text{meas}} - T_{\text{calc}}$ punto a punto con reporte estadístico de Media, Desvío Estándar y RMS de la discrepancia.

---

## 8. Exportación Científica

- **💾 Exportar Curvas (.dat / .txt / .csv)**:
  Genera archivos con encabezados comentados (`#`) legibles directamente por `np.loadtxt(..., comments='#')` y OriginLab, conteniendo:
  - Longitud de onda $\lambda$ [nm]
  - $T_{\text{calc}}$ [%] y $\sigma_T$ [%]
  - Extinción óptica $A$
  - Residuos $T_{\text{meas}} - T_{\text{calc}}$
  - Incertidumbre de longitud de onda $u_c(\lambda)$ [nm]
  - Metadatos experimentales completos (exposición, ranura, objetivo, escala $\mu\text{m/px}$, calibración de origen).
- **📦 Exportar Todo el Set (Batch)**:
  Procesa todas las muestras del conjunto y exporta sus tablas a una carpeta de destino con 1 solo clic.
- **📷 Guardar Imagen (PNG / SVG)**:
  Exporta la figura en alta resolución (PNG a 300 DPI / 2400 px de ancho) o en vectores SVG listos para publicación.
