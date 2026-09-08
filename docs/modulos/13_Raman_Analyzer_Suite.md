# 🔬 Módulo 13: Suite de Análisis Espectral y Quimiometría Raman (`raman_analyzer.py`)

**Laboratorio de Nanofotónica — Instituto de Nanosistemas (INS-UNSAM / CONICET)**  
**Archivos Fuente**: 
- [`analysis/raman_analyzer.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/analysis/raman_analyzer.py) (Ventana Principal y Modo Espectro Individual)
- [`analysis/multi_spectrum_widget.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/analysis/multi_spectrum_widget.py) (Suite Multi-Espectro & Series Temporales / SERS)
- [`core/raman_engine.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/core/raman_engine.py) (Motor Matemático Puro y Procesamiento Numérico)
- [`raman_analyzer.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/raman_analyzer.py) (Lanzador Raíz)

**Lanzador Rápido**: Botón dedicado en [`main.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/main.py) o ejecución directa con `python raman_analyzer.py`.

---

## 1. 🏷️ Resumen y Alcance Científico

El módulo **Raman Analyzer** es una suite completa de procesamiento, calibración, de-noising, corrección de fondo, ajuste multipico y quimiometría diseñada específicamente para espectroscopía Raman y dispersión Raman mejorada por superficie (SERS) adquirida con espectrógrafos **Andor Shamrock SR-303i** y cámaras CCD/EMCCD **Andor Newton/Idon** (software Andor Solis), así como espectrómetros comerciales en formatos estándar (`.asc`, `.txt`, `.csv`, `.dat`).

### Capacidades Principales
- **Importador Inteligente Andor Solis**:
  - Salto automático del encabezado de metadatos (~50 líneas de condiciones de adquisición: temperatura, tiempo de integración, red de difracción, centro de longitud de onda).
  - Detección automática de delimitadores (tabulaciones, comas, punto y coma, espacios).
- **Conversión Fotónica de Unidades en Tiempo Real**:
  - Longitud de onda ($\text{nm}$).
  - Desplazamiento Raman ($\text{cm}^{-1}$ o *Raman shift*), calibrado con la longitud de onda de excitación láser ($\lambda_{\text{laser}}$ configurable: 532 nm, 632.8 nm, 785 nm o valor arbitrario):
    $$\Delta\tilde{\nu} = \left(\frac{1}{\lambda_{\text{laser}}[\text{nm}]} - \frac{1}{\lambda[\text{nm}]}\right) \times 10^7$$
  - Energía fotónica ($\text{eV}$).
- **Herramientas de Recorte Interactivo (Trimming)**:
  - Recorte de bordes ruidosos arrastrando las reglas verticales A y B.
  - Atajo *"Recortar Rayleigh"* para purgar dispersión elástica residual por debajo de $150\text{ cm}^{-1}$.
  - Historial de restauración *"Restaurar Original"*.
- **Arquitectura Bi-Modal**:
  1. **Modo Espectro Individual**: Inspección de alta resolución, reglas duales A/B con integración de área, búsqueda de picos, deconvolución de picos y sustracción de línea base.
  2. **Modo Multi-Espectro (Series Temporales & Lotes)**: Análisis simultáneo de colecciones de espectros, normalizaciones matriciales, cinéticas de banda y descomposición por componentes principales (PCA).

---

## 2. 🧮 Algoritmos Numéricos y Fundamento Matemático

### 2.1 Corrección de Línea Base y Fondo de Fluorescencia
La fluorescencia de fondo suele superar la débil señal Raman inelástica por órdenes de magnitud. El motor implementa 5 métodos complementarios:

1. **AsLS (*Asymmetric Least Squares Smoothing*)**:
   Minimiza la función de costo asimétrica ponderada:
   $$F(z) = \sum_{i} w_i (y_i - z_i)^2 + \lambda \sum_{i} (\Delta^2 z_i)^2$$
   donde $w_i = p$ si $y_i > z_i$ (picos espectrales) y $w_i = 1-p$ si $y_i \le z_i$ (fondo), con $p \approx 0.001 - 0.01$ y parámetro de suavizado $\lambda \approx 10^4 - 10^7$.
2. **AirPLS (*Adaptive Iteratively Reweighted Penalized Least Squares*)**:
   Calcula pesos de forma adaptativa e iterativa a partir del error cuadrático medio sin requerir umbrales arbitrarios.
3. **Polinomio Modificado ModPoly (Lieber & Mahadevan-Jansen)**:
   Ajuste iterativo de mínimos cuadrados donde los puntos que caen por encima del polinomio en la iteración $k$ son reemplazados por el valor polinomial, eliminando la contribución de los picos Raman en la estimación del polinomio de grado $n$ (típicamente $n = 3 - 6$).
4. **Rolling Ball (*Esfera Rodante*)**:
   Filtro morfológico que simula una bola rodando por debajo del espectro, ideal para líneas base con ondulaciones topológicas complejas.
5. **Tercera Derivada / Mínimos Locales & Spline Cúbico**:
   Detección de puntos libres de picos mediante derivadas impares e interpolación de fondo por splines.

### 2.2 Suavizado, Filtrado y Limpieza de Rayos Cósmicos
- **Filtro Savitzky-Golay**: Ajuste polinomial local convolutivo que preserva la altura y la anchura a media altura ($\text{FWHM}$) de los picos estrechos mucho mejor que las medias móviles tradicionales.
- **Filtro Pasa-Bajos Fourier (FFT)**: Atenuación suave en el dominio de frecuencia mediante función de corte gaussiana o Fermi-Dirac.
- **Limpieza de Rayos Cósmicos (*Cosmic Ray Despiking*)**:
  Detección estadística por derivada discreta y mediana modificada (MAD):
  $$Z_i = \frac{| \Delta y_i - \text{mediana}(\Delta y) |}{\text{MAD}}$$
  Los eventos transitorios de alta energía causados por rayos cósmicos sobre el chip CCD son extirpados e interpolados suavemente con sus vecinos sin alterar las bandas Raman reales.

### 2.3 Metrología de Picos y Deconvolución
- **Find Peaks Adaptativo**: Búsqueda automática basada en prominencia relativa, ancho mínimo y distancia mínima entre picos.
- **Ajuste No Lineal Multi-Pico**: Deconvolución en el intervalo $[A, B]$ seleccionado por los cursores mediante perfiles:
  - **Gaussiano**: Dispersión instrumental o inhomogeneidades: $I(\nu) = A \exp\left(-\frac{(\nu-\nu_0)^2}{2\sigma^2}\right)$.
  - **Lorentziano**: Ensanchamiento homogéneo por tiempo de vida finito de fonones: $I(\nu) = \frac{A}{\pi} \frac{\gamma/2}{(\nu-\nu_0)^2 + (\gamma/2)^2}$.
  - **Pseudo-Voigt**: Combinación lineal ponderada de Gauss y Lorentz.
- **Cálculo de Parámetros**: Centro $\nu_0$, FWHM, altura neta, área integrada, residuo RMS y $R^2$.

---

## 3. 📊 Suite Multi-Espectro & Series Temporales (`MultiSpectrumWidget`)

Diseñada para experimentos de cinética química, series temporales SERS, mapeos puntuales y comparación de sustratos:

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│  PyPrinting 3.0 — Suite Raman Multi-Espectro & Series Temporales                            -  □  ×    │
├────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│  [ 📂 Cargar Espectros (Lote) ]  [ 🧪 Cargar Serie Demo ]  [ 📋 Copiar TSV ]  [ 💾 Guardar Matriz ]     │
├─────────────────────────────────┬──────────────────────────────────────────────────────────────────────┤
│  🔬 LÁSER DE EXCITACIÓN         │  VISUALIZADOR GRÁFICO CIENTÍFICO                                     │
│  Láser: [ 532.0 nm (Verde)   ▼] │  (•) Superpuesto (Overlay)  ( ) Cascada (Waterfall)  ( ) Heatmap 2D  │
│  Custom:[ 532.0 ] nm            │  Offset Cascada: ──[===|======]── 35 %                               │
│  [X] Sincronizar c/ Individual  │  ┌────────────────────────────────────────────────────────────────┐  │
├─────────────────────────────────┤  │                                                                │  │
│  TABLA DE ESPECTROS EN LOTE     │  │  Región A-B Arrastrable [░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░]     │  │
│  [X] #1  Muestra_A_t00.txt  🎨 │  │               /\        /\                  /\                │  │
│  [X] #2  Muestra_A_t05.txt  🎨 │  │        /\    /  \      /  \        /\      /  \               │  │
│  [X] #3  Muestra_A_t10.txt  🎨 │  │       /  \  /    \    /    \      /  \    /    \              │  │
│  [X] #4  Muestra_A_t15.txt  🎨 │  │  ____/____\/______\__/______\____/____\__/______\_______      │  │
├─────────────────────────────────┤  └────────────────────────────────────────────────────────────────┘  │
│  ✂️ RECORTE DE RANGO (ROI)      │  Raman Shift (cm⁻¹)                                                  │
│  [✂️ Recortar a Cursores A-B]   │                                                                      │
│  [⚡ Recortar Rayleigh <150 cm⁻¹]│  HERRAMIENTAS CUANTITATIVAS                                          │
│  [↺ Restaurar Rango Completo]   │  [ μ ± σ Promedio ]  [ Cinética de Banda ]  [ PCA Quimiométrico ]    │
│  [X] Límite: [ 150.0 - 3200 ]   │                                                                      │
│  Podar CCD: [ 0 ] izq  [ 0 ] der│                                                                      │
├─────────────────────────────────┤                                                                      │
│  📉 SUSTRACCIÓN DE LÍNEA BASE   │                                                                      │
│  Modo: [ 1: Archivo Referencia▼]│                                                                      │
│  [📂 Cargar Archivo Fondo...]   │                                                                      │
│  Fondo: [ blanco_sustrato.asc ] │                                                                      │
│  Blanco lote: [ (Ninguno)    ▼] │                                                                      │
│  -- O MODO 2: INDIVIDUAL --     │                                                                      │
│  Algoritmo: [ AsLS (λ=1e5)   ▼] │                                                                      │
├─────────────────────────────────┤                                                                      │
│  NORMALIZACIÓN Y FILTROS        │                                                                      │
│  Filtro:     [ Savitzky-Golay▼] │                                                                      │
│  Normalizar: [ Pico Referencia] │                                                                      │
│  Pico Ref:   [ 1078.0 ] cm⁻¹    │                                                                      │
│  Paleta:     [ Viridis       ▼] │                                                                      │
└─────────────────────────────────┴──────────────────────────────────────────────────────────────────────┘
```

### 3.1 Calibración del Láser de Excitación ($\lambda_{\text{laser}}$) y Selector de Unidades Espectrales
- **Selector Directo de Longitudes de Onda**:
  - `532.0 nm` (Verde DPSS / Nd:YAG frecuencialmente doblado)
  - `632.8 nm` (Rojo He-Ne)
  - `637.0 nm` (Rojo Diodo Láser)
  - `785.0 nm` (NIR Infrarrojo Cercano)
  - `592.0 nm` (Amarillo)
  - `Personalizado...` (habilita spinbox de alta precisión con pasos de $0.1\text{ nm}$).
- **Selector Tri-Modal de Unidades Espectrales Eje X**:
  - `Corrimiento Raman (cm⁻¹)`: Desplazamiento Raman inelástico calibrado respecto a $\lambda_{\text{laser}}$.
  - `Longitud de Onda (nm)`: Coordenada óptica absoluta directa registrada por el detector.
  - `Energía Relativa (eV)`: Conversión cuántica $E = \Delta\tilde{\nu} \cdot 1.239841984\times 10^{-4}\text{ eV}$.
- **Conmutación Universal e Instantánea**:
  - Actualiza dinámicamente las etiquetas y escalas del eje X en los 4 gráficos clave: Superposición/Cascada (`plot_multi`), Espectro Promedio (`plot_mean`), Mapa de Calor 2D (`plot_heatmap`) y Cargas PCA (`plot_pca_loadings`).
  - Adapta automáticamente los sufijos y la resolución decimal de los campos numéricos de recorte (`spin_crop_xmin`, `spin_crop_xmax`) y pico de referencia (`spin_ref_peak`) a 4 decimales en modo $\text{eV}$ y 1 decimal en $\text{cm}^{-1}$ y $\text{nm}$.
  - Convierte transparentemente el espectro de fondo (Modo 1) al sistema de coordenadas activo para una sustracción coherente en cualquier unidad.
  - Adapta el atajo rápido Rayleigh al umbral físico equivalente en la unidad elegida ($150\text{ cm}^{-1}$, $\approx 536.3\text{ nm}$ para láser 532 nm, o $\approx 0.0186\text{ eV}$).
- **Recálculo Espectral Dinámico**:
  Al cambiar el láser activo o la unidad, el motor recalcula instantáneamente la grilla común (`common_x`) y refresca en vivo los modos Overlay, Cascada, Heatmap, Promedio, Cinética y PCA.
- **Sincronización Bidireccional**: La casilla `[X] Sincronizar con Espectro Individual` propaga tanto los cambios de láser como las unidades seleccionadas entre la pestaña individual (`RamanAnalyzerWindow`) y la suite multi-espectro (`MultiSpectrumWidget`) de manera instantánea.
- **Auto-Detección desde Metadatos**: Al importar archivos con metadatos Andor Solis (ej. `Laser Wavelength: 785 nm`), el widget auto-selecciona el láser correspondiente.

### 3.2 Selección de Región de Interés (ROI) y Poda de Bordes
Permite eliminar de forma uniforme en toda la colección los extremos espurios y zonas de artefactos:
- **Recorte Interactivo a Cursores A y B**:
  - Arrastrando las reglas verticales A y B (o la región sombreada intermedia `LinearRegionItem`), el usuario delimita visualmente la zona analítica y presiona **`✂️ Recortar a Cursores A y B`**. La grilla común se restringe exactamente a dicho intervalo $[\min(A,B), \max(A,B)]$.
- **Atajo Rayleigh (`⚡ Recortar Láser/Rayleigh (< 150 cm⁻¹)`)**:
  - Elimina la subida exponencial del filtro de borde (*edge filter*) o dispersión elástica en el inicio del espectro, evitando que AsLS o polinomios se distorsionen.
- **Poda de Bordes del Sensor CCD (*Edge Trimming*)**:
  - Campos numéricos para podar $N$ píxeles en el inicio (`izq`) y $M$ píxeles en el fin (`der`) del detector para descartar píxeles ciegos o viñeteo óptico.
- **Restauración Rápida (`↺ Restaurar Rango Completo`)**:
  - Restablece el 100% de la extensión espectral original de los datos brutos sin ninguna pérdida.
- **Impacto Quimiométrico**:
  - Al descartar el ruido de bordes y la cola del Rayleigh, el análisis de componentes principales (**PCA**) y el espectro promedio $\mu \pm \sigma$ reflejan exclusivamente las bandas vibracionales moleculares genuinas.

### 3.3 Sistema Bi-Modal de Sustracción de Línea Base
A diferencia del procesamiento simple, la suite ofrece dos modos analíticos diferenciados:
1. **Modo 1: Sustracción de Archivo de Referencia / Blanco de Sustrato**:
   - **Archivo Externo de Fondo**: Permite cargar un espectro de referencia (`.asc`, `.txt`, `.csv`, `.dat`) representativo del blanco (ej. silicio, vidrio, solvente o sustrato SERS limpio).
   - **Calibración e Interpolación de Fondo**: El espectro de fondo se convierte dinámicamente a Raman shift usando el láser activo y se interpola exactamente sobre la grilla común del lote (`common_x`), sustrayéndolo de manera uniforme de todas las curvas del lote.
   - **Blanco Seleccionado del Lote**: Alternativamente, permite designar cualquiera de los espectros cargados en el lote como blanco/referencia para restarlo del resto.
2. **Modo 2: Cálculo Individual Adaptativo por Espectro**:
   - Calcula una línea base matemática independiente para cada curva individual del lote, adaptándose a variaciones espaciales de fluorescencia, photobleaching o derivas térmicas que cambien de un espectro a otro.
   - **Algoritmos Disponibles**:
     - *AsLS*: Parámetros ajustables $\log_{10}(\lambda)$ ($10^2 - 10^9$) y $p$ ($10^{-4} - 0.5$).
     - *AirPLS*: Ponderación adaptativa libre de umbrales con control de $\log_{10}(\lambda)$.
     - *ModPoly*: Grado de polinomio Lieber ($1 - 8$).
     - *Rolling Ball*: Radio de esfera rodante ($5 - 500\text{ pts}$).
3. **Modo 3: Sin Corrección**: Visualización directa de cuentas espectrales brutas sin restar fondo.

### 3.3 Normalizaciones Espectroscópicas
1. **A Máximo Global (0 - 1)**: Escala cada espectro dividiendo por su intensidad máxima ($Y / Y_{\max}$).
2. **A Pico de Referencia Seleccionado**: Fija una banda analítica interna (por ejemplo, el modo de estiramiento del sustrato a $1078\text{ cm}^{-1}$ o el cursor A) a intensidad $1.0$, permitiendo comparar intensidades relativas directas.
3. **Por Área Unitaria**: Normaliza la integral total a la unidad ($\int Y \, d\nu = 1$), corrigiendo variaciones de potencia láser o fluctuaciones de enfoque.
4. **SNV (*Standard Normal Variate*)**: Centrado en la media y escalado por la varianza ($z = (y - \bar{y}) / s$).

### 3.4 Pestaña de Espectros Crudos & Líneas de Base (`📉 Crudos & Línea Base`)
Permite inspeccionar visualmente los datos originales antes del preprocesamiento y comprobar la precisión del modelo de línea base:
- **Visualización Simultánea de Crudos**:
  Todos los espectros del lote se dibujan en sus intensidades brutas originales sobre la grilla espectral común.
- **Regla Estricta para Modo 1 (Referencia / Blanco)**:
  Cuando se selecciona corregir con el archivo de fondo de referencia, **se dibuja exclusivamente una única curva de línea base** (la del archivo de fondo interpolada, resaltada en línea punteada `#F38BA8` de grosor 2.6). Esto evita la sobrecarga visual y permite verificar de un vistazo cómo se relaciona el fondo de referencia con toda la serie.
- **Visualización en Modo 2 (Cálculo Individual)**:
  Cada espectro del lote muestra su propia línea base algorítmica estimada (AsLS, AirPLS, ModPoly o Rolling Ball) con línea punteada en el color asignado a dicho espectro.
- **Modo 3 (Sin corrección)**:
  Muestra únicamente los espectros crudos sin curvas de fondo superpuestas.

### 3.5 Herramientas Cuantitativas
- **Espectro Promedio $\pm \sigma$ & RSD%**:
  Traza la curva promedio $\mu(\nu)$ junto a un intervalo de confianza sombreado semitransparente $\pm \sigma(\nu)$. Calcula la **Desviación Estándar Relativa porcentual ($\text{RSD}\% = 100 \cdot \sigma / \mu$)** global y puntual en la posición del cursor A, evaluando la reproducibilidad lote a lote.
- **Cinética de Banda**:
  Extrae y grafica la evolución temporal de la altura máxima y el área integrada en el rango $[A, B]$ a través de toda la serie cronológica.
- **Quimiometría PCA (*Principal Component Analysis*)**:
  Descomposición espectral por valores singulares (SVD) con centrado en la media:
  $$X = U \Sigma V^T$$
  Genera el gráfico bidimensional de **Scores** ($\text{PC1}$ vs $\text{PC2}$) para agrupamiento no supervisado (*clustering*) de muestras y el espectro de **Loadings** (cargas) para identificar las bandas vibracionales responsables de la varianza.

### 3.6 Sistema de Exportación Dinámica y Contextual (PNG 600 DPI, CSV, TSV)
Tanto la suite multi-espectro (`MultiSpectrumWidget`) como la pestaña individual (`RamanAnalyzerWindow`) cuentan con barras de exportación de 1-click adaptadas a publicaciones científicas:
- **Botones Dinámicos en Multi-Espectro**:
  La barra superior adapta automáticamente su texto, tooltips y formato según la pestaña activa:
  1. `📉 Crudos & Línea Base`: Exporta gráfico PNG y CSV con columnas `[X, Raw_1, ..., Raw_N, Baseline_Ref]` (Modo 1) o `[X, Raw_1, Base_1, ..., Raw_N, Base_N]` (Modo 2).
  2. `📈 Espectros (Overlay / Cascada)`: Exporta figura PNG a 2400 px y matriz normalizada completa en CSV.
  3. `📊 Promedio ± Desvío`: Exporta gráfico de banda de dispersión a 2400 px y CSV con `Mean_Intensity, Std_Dev, Minus_1Sigma, Plus_1Sigma, RSD_Percent`.
  4. `⏱️ Cinética de Banda`: Exporta gráfico de tendencia y CSV con altura máxima y área integrada entre reglas A-B para cada espectro.
  5. `🗺️ Mapa de Calor 2D`: Exporta mapa 2D a PNG y matriz CSV tiempo vs. coordenada espectral.
  6. `🧬 Análisis PCA`: Exporta una **figura científica combinada a 2400 px** ensamblando lado a lado el Score Plot y los Loadings mediante renderizado compuesto de alta resolución, y un CSV estructurado con bloques de Scores y Cargas espectrales.
- **Copiado al Portapapeles (TSV)**:
  El botón `📋 Copiar TSV` envía los datos tabulados directamente al portapapeles listos para pegar en OriginLab, GraphPad Prism o Microsoft Excel con formato y encabezados completos.
- **Exportación Rápida en Espectro Individual**:
  Barra superior sobre los gráficos sincronizados con botones directos: `📸 Exportar Gráfico (PNG 600 DPI)`, `💾 Exportar CSV` y `📋 Copiar TSV`.

### 3.7 🌓 Deslizador de Tema Claro / Oscuro para Visualización y Exportación
Para satisfacer los requerimientos de edición de publicaciones científicas y compatibilidad con diapositivas o reportes impresos, tanto `MultiSpectrumWidget` como `RamanAnalyzerWindow` incorporan un **deslizador de fondo estricto**:
- **Selector Discreto (Solo 0 y 100, sin intermedios)**:
  Un control deslizante físico (`QSlider` horizontal) con tope estricto en los extremos `0` (🌙 Oscuro) y `100` (☀️ Claro). Al desplazarse o hacer clic, chasquea automáticamente sin admitir valores intermedios.
- **Tema Oscuro (`0: #181825`)**:
  Paleta Catppuccin Mocha con fondo oscuro de alto contraste, curvas pasteles fluorescentes y tipografía `#CDD6F4`, ideal para pantallas de laboratorio y microscopía.
- **Tema Claro (`100: #FFFFFF`)**:
  Fondo blanco puro editorial con ejes, textos y leyendas en negro carbón `#11111B`, etiquetas de picos en violeta profundo `#7C3AED`, y curvas de alto contraste cromático (`#1E66F5` azul real, `#15803D` verde esmeralda, `#D97706` ámbar y `#D20F39` carmesí).
- **Sincronización Bidireccional**:
  Alternar el deslizador en la vista individual actualiza en tiempo real los 7 paneles gráficos de multi-espectro y viceversa.
- **Exportación Fiel de Imágenes (PNG 600 DPI / 2400 px)**:
  Las imágenes exportadas respetan con fidelidad absoluta el fondo seleccionado (blanco editorial `#FFFFFF` o modo oscuro `#181825`), incluyendo la composición integrada de la pestaña PCA.

