# MOD-08: Analizador de Desorden y Estructura de Redes Cristalinas 2D 🔬

**PyPrinting 3.0 — Suite de Nanofotónica y Control Instrumental**  
**Laboratorio de Nanofotónica — Instituto de Nanosistemas (INS-UNSAM / CONICET)**  
**Manual de Usuario Canónico** | **Código:** `MOD-08` | **Nivel de Usuario:** Intermedio / Avanzado  
**Archivos Fuente Asociados:**
- [`analysis/lattice_disorder_gui.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/analysis/lattice_disorder_gui.py) (GUI en 4 pestañas secuenciales, presets y ROI interactivo)
- [`core/lattice_disorder.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/core/lattice_disorder.py) (Motor metrológico, NUFFT 2D, KDTree acotado, $g(r)$ y Monte Carlo)
- [`core/localization_pipeline.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/core/localization_pipeline.py) (Pipeline unificado Picasso / Trackpy / Richardson-Lucy)

---

## 🔗 Matriz de Referencias Cruzadas

* **Reportes de Sistema Conexos:**
  * `[[SYS-105_Pipeline_Unificado_Localizacion_Super_Resolucion]]`
  * `[[SYS-104_Matriz_Intercambio_Archivos_y_Formatos_IO]]`
* **Fundamentos Científicos Asociados:**
  * `[[CAT-301_Algoritmos_Espacio_Real_KDTree_Asignacion_Monte_Carlo]]`
  * `[[CAT-302_Caracterizacion_Fisica_Desorden_Defectos_Redes_SMLM]]`
  * `[[CAT-303_Derivacion_Matematica_Distribucion_Radial_gr_Correccion_Borde]]`
  * `[[CAT-305_Derivacion_Matematica_Factor_Estructura_Debye_Waller]]`
  * `[[CAT-307_Computacion_NUFFT_Factor_Estructura_Optimizacion_BLAS]]`
  * `[[CAT-308_Metrologia_Analitica_Directa_Picos_Bragg_Fourier_2D]]`
  * `[[CAT-401_Estandar_Serializacion_Jerarquica_Contenedor_HDF5]]`

---

## 1. Resumen y Alcance Operativo

El módulo **Analizador de Desorden y Redes 2D (`MOD-08`)** es una suite metrológica diseñada para evaluar cuantitativamente la calidad cristalográfica de redes de nanopartículas nanofabricadas por *Optical Printing* o litografía. 

Permite procesar imágenes confocales o de fluorescencia (`.tiff`, `.png`, `.jpg`, `.h5`) y tablas de coordenadas de super-resolución SMLM (`.csv`, `.txt`, `.npy`), evaluando la muestra en:
1. **Espacio Real:** Asignación al retículo ideal mediante KDTree con cota estricta ($a/2$), descomposición en residuos ortogonales ($\sigma_x, \sigma_y$), detección topológica de vacancias y función de distribución radial $g(r)$.
2. **Espacio Recíproco:** Transformada de Fourier Continua 2D (NUFFT 2D) acelerada por BLAS, perfiles integrados de picos de Bragg y calibración estocástica por Monte Carlo desacoplando el factor de vacancias $(1-p)^2$ en el modelo de **Debye-Waller**.

---

## 2. Principios Físicos de Operación y Errores Históricos Corregidos

> [!NOTE]
> **Caja de Derivación Formal**:
> * Para la deducción analítica de la atenuación por vacancias $(1-p)^2$ en el pico coherente de Bragg, consultar `[[CAT-305_Derivacion_Matematica_Factor_Estructura_Debye_Waller]]`.
> * Para la formulación tensorial BLAS GEMM de la NUFFT 2D y la eliminación del piso de ruido artificial, consultar `[[CAT-307_Computacion_NUFFT_Factor_Estructura_Optimizacion_BLAS]]`.
> * Para la inversión de picos de Bragg, longitudes de correlación y elipticidad, consultar `[[CAT-308_Metrologia_Analitica_Directa_Picos_Bragg_Fourier_2D]]`.
> * Para la función de correlación radial de pares $g(r)$ y la corrección de borde, consultar `[[CAT-303_Derivacion_Matematica_Distribucion_Radial_gr_Correccion_Borde]]`.

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                        MATRIZ DE CORRECCIONES METROLÓGICAS EN LA NUEVA SUITE                           │
├──────────────────────────────┬────────────────────────────────────┬────────────────────────────────────┤
│ Aspecto Físico / Algorítmico │ Código Histórico (reserva/)        │ Nueva Suite (PyPrinting 3.0)       │
├──────────────────────────────┼────────────────────────────────────┼────────────────────────────────────┤
│ 1. Atenuación por Vacancias  │ Omitida; atribuía la pérdida de    │ Desacoplada analíticamente y en MC │
│    en Debye-Waller           │ altura por falta de puntos a σ.    │ mediante el factor (1 - p)².       │
├──────────────────────────────┼────────────────────────────────────┼────────────────────────────────────┤
│ 2. Deconvolución RL previa   │ Aplicada indistintamente antes de  │ Aislada exclusivamente a Trackpy;  │
│    en Localización Picasso   │ Picasso, distorsionando la PSF.    │ excluida estrictamente en Picasso. │
├──────────────────────────────┼────────────────────────────────────┼────────────────────────────────────┤
│ 3. Offset de Caja Picasso    │ Resta manual confusa sin           │ Compensación nativa configurable:  │
│    (box_radius = box // 2)   │ justificación documentada.         │ [x] Offset de caja (+box/2).       │
├──────────────────────────────┼────────────────────────────────────┼────────────────────────────────────┤
│ 4. Discretización en Fourier │ Histogram2D a 50 nm/px, inyectando │ NUFFT 2D Continua exacta sobre     │
│    (Piso de Ruido Artificial)│ piso de ruido espurio de 14.4 nm.  │ nanómetros directos (piso <0.1 nm).│
├──────────────────────────────┼────────────────────────────────────┼────────────────────────────────────┤
│ 5. Mapeo KDTree en Espacio   │ std(dist_euclidiana) Rayleigh,     │ Residuos cartesianos Δx, Δy con    │
│    Real y Salto de Vacancias │ subestimando σ en un 34.5%.        │ distance_upper_bound = a/2.        │
├──────────────────────────────┼────────────────────────────────────┼────────────────────────────────────┤
│ 6. Modelo de Ajuste          │ Gaussiana libre asimétrica (x0≠0)  │ Modelo par físicamente simétrico:  │
│    Debye-Waller              │ con 4 parámetros acoplados.        │ H(σ) = H0(1-p)² exp(-σ²/2σc²) + Hbg│
└──────────────────────────────┴────────────────────────────────────┴────────────────────────────────────┘
```

### 2.1 Desacoplamiento del Factor de Vacancias $(1-p)^2$
En redes reales nanofabricadas, una fracción de nodos puede quedar vacante ($p = f_{\text{vac}}$). El pico coherente de difracción de Bragg en el espacio recíproco disminuye en altura de forma cuadrática con la fracción de ocupación:
$$I(\mathbf{G}) \propto (1 - p)^2 \exp(-G^2 \sigma^2)$$
Si el software no desacopla este factor, una red con $10\%$ de vacancias ($p=0.10$) exhibe una caída del $19\%$ en la altura de pico que sería erróneamente interpretada como un desorden posicional térmico elevado. `MOD-08` cuantifica $p$ en la Pestaña 1 y lo compensa automáticamente en las curvas de Debye-Waller de la Pestaña 3 (`[[CAT-305_Derivacion_Matematica_Factor_Estructura_Debye_Waller]]`).

### 2.2 Transformada de Fourier No Uniforme (NUFFT 2D) y Corte DC
* **Eliminación del Piso de Ruido Discreto:** A diferencia de los métodos de histograma con píxeles fijos de $50\ \text{nm}$ (que generaban un error residual intrínseco de $14.4\ \text{nm}$), la NUFFT 2D continua evalúa directamente las coordenadas sub-píxel en nanómetros continuos mediante multiplicación matricial BLAS de Nivel 3 (GEMM), reduciendo el piso de ruido a $< 0.1\ \text{nm}$ (`[[CAT-307_Computacion_NUFFT_Factor_Estructura_Optimizacion_BLAS]]`).
* **Corte DC (`spin_dc_cut`):** En $f=(0,0)$ el pico central posee una intensidad masiva ($S(0,0) \approx N$) con colas $\text{sinc}^2(L f)$. El parámetro `Corte DC` (defecto $0.35$) enmascara este lóbulo central para que no distorsione el ajuste del pico de Bragg de primer orden.
* **Integración de Banda Transversal ($\pm 3\ \text{px}$):** Los cortes 1D integran una franja transversal de $\pm 3\ \text{píxeles}$ perpendicular al eje de corte, estabilizando la altura de pico frente a desalineaciones angulares menores a $1.0^\circ$.

### 2.3 Determinación de Vacancias y Función de Distribución Radial $g(r)$
* **Mapeo KDTree con Cota de Wigner-Seitz ($r < a/2$):** Cada partícula se indexa a su celda unitaria. Si la distancia al nodo ideal es $r < a/2$, se asigna como ocupante legítimo y se calculan los residuos cartesianos $\sigma_x = \text{std}(\Delta x)$ y $\sigma_y = \text{std}(\Delta y)$. Los nodos sin partículas se clasifican como vacancias (cruces rojas `x`).
* **Función de Distribución Radial $g(r)$:** Como validación ortogonal independiente, el ajuste del primer pico de coordinación en $r \approx a$ permite obtener el desorden posicional mediante $\sigma_{\text{rdf}} = \sigma_{\text{peak}} / \sqrt{2}$, inmune a rotaciones de la muestra (`[[CAT-303_Derivacion_Matematica_Distribucion_Radial_gr_Correccion_Borde]]`).


---

## 3. 🖥️ Arquitectura de la Interfaz Gráfica (4 Pestañas Secuenciales)

La aplicación sigue el modelo de diseño ergonómico de **SIF Analyzer** con paneles colapsables, scroll vertical fluido, gráficos interactivos con tema oscuro Catppuccin Mocha y widgets dinámicos sensibles al contexto.

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│  PyPrinting 3.0 — Analizador de Desorden y Estructura de Redes Cristalinas 2D                -  □  ×   │
├────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│  [ 📍 1. Espacio Real & SMLM ]   [ 📊 2. Espacio Recíproco ]   [ 🔄 3. Monte Carlo ]   [ 📤 4. Reportes ] │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 📍 Pestaña 1: Espacio Real & SMLM

Permite cargar los datos experimentales, seleccionar presets de 1-clic, ajustar reglas interactivas de ROI, ejecutar la localización con auto-escalado dinámico a 16-bit e inversión de fondo claro, y visualizar el retículo con sus vacancias.

```
┌──────────────────────────────────────┬─────────────────────────────────────────────────────────────────┐
│ 0. PRESETS DE OPERACIÓN (1-CLIC)     │ VISUALIZADOR DE ESPACIO REAL (IMAGEN + REGLAS ROI + DETECCIONES) │
│ Preset: [ Confocal Estándar 30x30  ▼]│ ┌─────────────────────────────────────────────────────────────┐ │
│ [ 📂 Cargar... ] [ 💾 Guardar... ]   │ │   • Partículas detectadas (Cian)                            │ │
│ 1. DATOS DE ENTRADA & PREPROCESO     │ │   × Vacancias del retículo (Rojo)                           │ │
│ [ 📂 Cargar Imagen Confocal ]        │ │   --- Reglas móviles ROI (Naranja X, Rosa Y)                │ │
│ [ 📄 Cargar Coordenadas Directas ]   │ │                                                             │ │
│ [X] Invertir Imagen (Fondo Claro)    │ │   │    •   •   •   •   •   •   •   •   •   •    │          │ │
│ Archivo: 30x30_500.tiff (330x330 px) │ │   │    •   •   •   ×   •   •   •   •   •   •    │          │ │
│ 2. SELECTOR DE ROI & RECORTE         │ │   │    •   •   •   •   •   •   •   ×   •   •    │          │ │
│ [X] Habilitar Reglas de ROI          │ │   │    •   •   •   •   •   •   •   •   •   •    │          │ │
│ Xmin/max: [ 15.0 ] / [ 315.0 ] px    │ └─────────────────────────────────────────────────────────────┘ │
│ Ymin/max: [ 15.0 ] / [ 318.0 ] px    │ Posición X (nm)                                                 │
│ [ ↺ Toda Imagen ] [ ✂️ Aplicar ]     │                                                                 │
│ 3. PARÁMETROS ESPACIALES DE RED      │ FUNCIÓN DE DISTRIBUCIÓN RADIAL g(r)                             │
│ Escala: [ 50.0 ] nm/px  NxN: [ 30 ]  │ ┌─────────────────────────────────────────────────────────────┐ │
│ Período a: [ 500.0 ] nm              │ │           /\ Primer pico de coordinación (r ≈ 500 nm)       │ │
│ 4. MOTOR DE LOCALIZACIÓN             │ │          /  \                                               │ │
│ Motor: [ Picasso (GaussLQ / MLE)   ▼]│ │  _______/    \____________________________________________  │ │
│ Min Net Grad: [300.0]  Box: [ 7 ] px │ └─────────────────────────────────────────────────────────────┘ │
│ [X] Compensar offset caja (+box/2)   │ Distancia r (nm)                                                │
│ [X] Auto-escalado dinámico 16-bit    │                                                                 │
│ [X] Parámetros extendidos            │                                                                 │
│ [ 🔍 Detectar Partículas ]           │                                                                 │
│ 5. MÉTRICAS DE ESPACIO REAL          │                                                                 │
│ Partículas: 836 de 900 sitios        │                                                                 │
│ Vacancias:  7.1% (64 nodos)          │                                                                 │
│ Desorden σ_x:   15.42 nm             │                                                                 │
│ Desorden σ_y:   15.80 nm             │                                                                 │
│ Desorden Medio: 15.61 nm             │                                                                 │
│ Ancho g(r) σ_rdf: 16.05 nm           │                                                                 │
│ [ Ir a Espacio Recíproco ➔ ]         │                                                                 │
└──────────────────────────────────────┴─────────────────────────────────────────────────────────────────┘
```

#### Controles Principales
- **Catálogo de Presets de 1-Clic:**
  - `✨ Confocal Estándar 30x30 (500 nm) [Calibrado 30x30_500]`: Escala 50 nm/px, período 500 nm, ROI $[15, 315] \times [15, 318]\ \text{px}$, Picasso LQ gradiente 300 o Trackpy diám 5 / sep 7 px.
  - `🔬 Confocal Alta Densidad (400-450 nm)`: Período nominal 450 nm, caja de 5 px, separación 5 px.
  - `☀️ Fondo Claro / Transmisión (Invertida)`: Invierte el contraste automáticamente ($I' = I_{\max} + I_{\min} - I$) para detectar nanopartículas oscuras en campo claro.
  - `📷 Fluorescencia Campo Amplio`: Escala 100 nm/px, períodos de 600 nm, GaussMLE con caja de 9 px.
  - Botones `[📂 Cargar...]` y `[💾 Guardar...]` para serializar presets personalizados en JSON.
- **Selector Interactivo de ROI (4 Reglas Móviles):**
  - Permite acotar la región de análisis arrastrando interactivamente 4 reglas infinitas discontinuas sobre la imagen o editando sus spinboxes con sincronización bidireccional inmediata en píxeles y nanómetros.
  - Botón `[↺ Toda la Imagen]`: Expande el ROI al tamaño completo de la imagen cargada.
  - Botón `[✂️ Aplicar Recorte]`: Filtra al instante las detecciones existentes sin necesidad de re-ejecutar Picasso/Trackpy, actualizando en milisegundos las métricas y el espectro Fourier.
- **Auto-escalado Dinámico a 16-bit en Picasso:**
  - Evita el truncamiento de intensidades cuando se procesan imágenes en formato punto flotante (`float32`), escalando de forma segura a $[1000, 30000]$ en `uint16` preservando la linealidad fotométrica y la convergencia de GaussLQ/MLE.
- **Inversión de Imagen Integrada:**
  - Casilla `[x] Invertir Imagen (Negativo / Fondo Claro)` para compatibilidad con microscopía de transmisión sin alterar el pipeline metrológico subyacente.
- **Filtrado Avanzado de Nanopartículas en Trackpy:**
  - Parámetros `Separación (px)` para evitar coalescencia espuria de centroides vecinos, `Percentil de Umbral (%)` y `Tamaño de Ruido (px)` para discriminar ruido estocástico del fondo.
- **Grupo 5: Fases 2 y 3: Curación y Desacople Fotométrico:**
  - **Calibración Automática de Monómero:** Extrae $V_0, A_0$ y $\sigma_{\text{psf}}$ a partir de los cientos de emisores aislados ($d > 0.70 \cdot a$) presentes en la red.
  - **Tabla de Cúmulos y Aglomerados (7 columnas):** `[ID, Tipo, Det, Est, Vol/V₀, Área/A₀, Estado]` con códigos de color para identificar cúmulos `OK`, `SUB-RESUELTO` o `SOBRE-DETECTADO`.
  - **Creación de Cúmulos Manuales (`btn_create_manual_cluster`):** Botón `[➕ Crear Cúmulo de Selección]` para agrupar 2 o más partículas marcadas manualmente, calculando su contorno fotométrico, estequiometría $N \ge 2$ y agregándolas formalmente a la tabla.
  - **Modo Interactivo de Semillas Visuales Manuales (`btn_pick_visual_seeds`):**
    - Botón conmutable `[📍 Marcar Semillas Visuales]` que permite colocar centros iniciales de partículas directamente con clics en el visor (cruces verdes `#a6e3a1` con etiquetas `S1, S2, ...`).
    - Botones `[📋 Usar Detectadas como Semillas]` y `[🧹 Limpiar Semillas]`.
    - Sincronización bidireccional automática con el selector $n$ de componentes gaussianas.
  - **Enmascaramiento Gráfico Estricto (`patch[~mask] = 0`):**
    - Tanto en cúmulos como en puntos sospechosos, los píxeles exteriores al contorno se anulan rígidamente a cero.
    - La optimización evalúa residuos exclusivamente dentro de la máscara, evitando distorsiones por partículas adyacentes o fondo parásito.
    - Confinamiento geométrico estricto de las coordenadas ajustadas $(x_k, y_k)$ al interior de la caja delimitadora del contorno.
  - **Restricciones Físicas de Partículas Idénticas (Tolerancia del 30% y $N \ge 2$):**
    - Cotas de caja en amplitud $A_k \in [0.70 \cdot A_0, 1.30 \cdot A_0]$ y ancho difraccional $\sigma_k \in [0.70 \cdot \sigma_{\text{psf}}, 1.30 \cdot \sigma_{\text{psf}}]$.
    - Restricción estricta de estequiometría mínima de cúmulo: $N = \max(2, \operatorname{round}(V_\Omega / V_0))$.
  - **Sub-panel `🔍 Inspección de Punto Sospechoso (Manual)`:**
    - Al seleccionar 1 partícula en el visor de espacio real, calcula automáticamente el fondo local perimetral y segmenta el contorno fotométrico adaptativo (`spin_suspicious_thresh`, defecto 20%).
    - Muestra en vivo los ratios $V_{\Omega}/V_0$, $A_{\Omega}/A_0$ y la sugerencia estequiométrica $n_{\text{sugerido}}$.
    - Botón **`🎯 Desacoplar Spot (Fit)`**: Ejecuta el ajuste multi-Gaussiano enmascarado y constreñido, reemplaza el centroide único por las $n$ partículas desacopladas, actualiza de inmediato el gráfico con auto-enfoque centrado y recalcula la grilla y vacancias.
  - **Acciones en Lote y Uno a Uno:** Botones para desacoplar (`Fit Multi-Gauss`), conservar la partícula más cercana al nodo ideal (`Conservar Nodo`) o fusionar en el centro de masa (`Fusionar COM`), con historial completo `↺ Deshacer` y `↺ Restaurar Todo`.
  - **Cascada Completa Sincronizada:** Cada acción de curación ejecuta en tiempo real la actualización de `locs_df`, recálculo de KDTree/vacancias y recálculo espectral de Fourier en la Pestaña 2.
- **Barra de Capas Desacoplada en 2 Filas:**
  - Fila 1: Mapa de color, `[x] 🖼️ TIFF`, `[ ] 🧹 Filtro Fondo`, `[ ] ✨ RL Deconv` (`chk_overlay_rl`), `[x] 🔵 Partículas (o)`, `[x] 🟠 Aglomerados`, `[x] 🔲 Contornos`.
  - Fila 2: `[x] 🟣 Seleccionadas`, `[x] ❌ Vacancias (x)`, `[ ] 📐 Malla (+)`, `[x] 📏 Reglas ROI`.
  - La capa `✨ RL Deconv` permite alternar y superponer instantáneamente la imagen procesada por Richardson-Lucy sobre el fondo TIFF original.
- **Entrada Dual:** Si se carga un archivo de coordenadas directas (`.csv`, `.txt`), la aplicación salta automáticamente la etapa de localización y calcula de inmediato el espacio real y el espacio recíproco.
- **Casilla `[x] Incluir parámetros extendidos`:** Si está tildada, exporta fotones, fondo, anchos gaussianos ($s_x, s_y$), excentricidad, señal y masa integrada.

---

### 📊 Pestaña 2: Espacio Recíproco & Fourier

Despliega el patrón de difracción 2D bidimensional $S(f_x, f_y)$ y los cortes transversales 1D integrados para la determinación ultra-precisa de los parámetros de red.

```
┌──────────────────────────────────────┬─────────────────────────────────────────────────────────────────┐
│ PARÁMETROS ESPECTRALES 2D (NUFFT)    │ MAPA ESPECTRAL 2D DE BRAGG log10(1 + S(fx, fy))                │
│ Grilla Fourier: [ 256 x 256 (Rápida)▼│ ┌─────────────────────────────────────────────────────────────┐ │
│ Banda Transversal: [ 3 ] px          │ │                           + (0, Gy)                         │ │
│ Corte Continua DC: [ 0.35 ]          │ │                                                             │ │
│ [ ⚡ Recalcular Espectro 2D ]        │ │           (-Gx, 0) +      • DC      + (+Gx, 0)              │ │
├──────────────────────────────────────┤ │                                                             │ │
│ PARÁMETROS DE RED EXTRAÍDOS          │ │                           + (0, -Gy)                        │ │
│ Período a_x:     450.21 nm           │ └─────────────────────────────────────────────────────────────┘ │
│ Período a_y:     449.88 nm           │ Frecuencia fx (nm⁻¹)                                            │
│ Período Medio:   450.05 nm           │                                                                 │
│ Anisotropía:     +0.33 nm            │ CORTES TRANSVERSALES 1D Y AJUSTE GAUSSIANO DE PICOS DE BRAGG    │
│ Altura Pico H_x: 95.80               │ ┌──────────────────────────────┐┌─────────────────────────────┐ │
│ Altura Pico H_y: 96.10               │ │ Perfil fx (Horizontal)       ││ Perfil fy (Vertical)         │ │
│ FWHM_x: 0.00032 nm⁻¹ (ξ_x: 497 nm)   │ │      /\ Experimental (Azul)  ││      /\ Experimental (Violeta)│ │
│ FWHM_y: 0.00031 nm⁻¹ (ξ_y: 513 nm)   │ │  ---/--\-- Ajuste Gauss (Ver)││  ---/--\-- Ajuste Gauss (Ver)│ │
│                                      │ └──────────────────────────────┘└─────────────────────────────┘ │
│ [ Propagar a Monte Carlo ➔ ]         │ Frecuencia fx (nm⁻¹)            Frecuencia fy (nm⁻¹)            │
└──────────────────────────────────────┴─────────────────────────────────────────────────────────────────┘
```

#### Características Clave
- **Selector de Grilla Fourier 2D:** Permite conmutar al instante entre `256 x 256 (Rápida)` para exploración fluida y `512 x 512 (Alta Res.)` o `1024 x 1024` para publicaciones metrológicas donde el pico de Bragg contiene $> 18$ puntos discretos.
- **Control de Corte DC (`f_cut / f0`):** Excluye la inmensa cola central de frecuencia cero ($S(0,0)=N \approx 850$), evitando que deslumbre o sesgue el ajuste gaussiano del pico de Bragg periódico ($f_0 = 1/a$).
- **Reactividad Dinámica en Vivo:** Al alterar la grilla, la banda transversal o el corte DC, la interfaz recalcula en milisegundos el mapa 2D, los cortes 1D y las métricas cristalográficas sin necesidad de pulsar botones adicionales.
- **Relaciones Analíticas Directas de Bragg y Gráfico de Wilson Anisótropo:**
  - **4 Gráficos Científicos en Sub-Pestaña Analítica:**
    1. *Gráfico de Wilson 2D:* Regresión multilogarítmica $\ln(H)$ vs $|\mathbf{G}|^2$ desacoplada independientemente para $X$ (azul `#89b4fa`) e $Y$ (naranja `#fab387`), con testigo diagonal $(1,1)$.
    2. *Decaimiento de Debye-Waller Multi-Orden:* Compara las alturas de pico experimentales contra las curvas analíticas teóricas.
    3. *Comparativa de Estabilidad de Ratios:* Diagnostica la coherencia de los 8 estimadores analíticos directos ($\sigma_{21, x}$, $\sigma_{21, y}$, $\sigma_{\text{diag}, x}$, $\sigma_{\text{diag}, y}$, etc.).
    4. *Diagnóstico Paracristalino de Hosemann (FWHM vs m²):* Compara si el ensanchamiento difraccional responde a un desorden térmico de Debye-Waller Puro (Tipo I, ancho constante de Scherrer) o a desorden acumulativo de Paracristal (Tipo II, FWHM $\propto m^2$).
  - **Casilla `[x] Anclar Wilson a ln(H₀)` (`chk_anchor_wilson_h0`):**
    - Al marcarse, fuerza el intercepto al valor experimental medido $\ln(H_0)$ y deduce la pendiente analítica de 1 parámetro en milisegundos.
    - Emite un badge de diagnóstico comparando las pendientes libres y forzadas para alertar si existe inflación del pico central por autofluorescencia o fondo de resina.
- **Integración de Banda Transversal:** Integra una franja de $\pm 3\ \text{píxeles}$ alrededor de los ejes $f_y = 0$ y $f_x = 0$, absorbiendo rotaciones menores de la red ($<1.0^\circ$) sin pérdida de altura del pico de Bragg.
- **Botón `Propagar a Monte Carlo`:** Transfiere automáticamente $a_x, a_y$ (detectando anisotropía si $|a_x - a_y| > 1.0\ \text{nm}$), $N$, $f_{\text{vac}}$ y el ancho de banda recíproco $\Delta f_\perp$ a la Pestaña 3 con 1 clic.

---

### 🔄 Pestaña 3: Monte Carlo & Debye-Waller

Ejecuta la calibración estocástica asíncrona inyectando vacancias reales, desorden controlado y geometría de red (isotrópica o anisotrópica) para interpolar rigurosamente $\sigma_{\text{real}, x}$ y $\sigma_{\text{real}, y}$.

```
┌──────────────────────────────────────┬─────────────────────────────────────────────────────────────────┐
│ CONFIGURACIÓN DE SIMULACIÓN          │ CURVAS DE ATENUACIÓN DEBYE-WALLER: H_x(σ), H_y(σ)               │
│ Sitios N: [ 30 ]                     │ ┌─────────────────────────────────────────────────────────────┐ │
│ [x] Anisotropía (a_x ≠ a_y)          │ │ H ↑                                                         │ │
│ a_x: [ 480.0 ] nm  a_y: [ 520.0 ] nm │ │   │ • H_x exp (Azul)      • H_y exp (Rojo)                  │ │
│ Vacancias f_vac:   [  2.0 ] %        │ │Hx ┼---•-\--------- Curva X (Debye-Waller a_x)               │ │
│ Rango σ (nm):      [ 60.0 ] nm       │ │   │    \  \                                                 │ │
│ Puntos σ / Iter:   [ 20 ] / [ 30 ]   │ │Hy ┼-------•-\----- Curva Y (Debye-Waller a_y)               │ │
│ Muestreo Bragg:    [ 81 pts (Alta) ] │ │   │          \--\--- Banda ±1σ de dispersión                │ │
│ Banda Transv (nm⁻¹)[0.00030] nm⁻¹    │ │   └──────┼─────┼───────────────────────────────────────► σ   │ │
│ [ 🚀 Iniciar Simulación Monte Carlo] │ │         σ_x   σ_y                                           │ │
│ [ ⏹ Cancelar Simulación ]           │ └─────────────────────────────────────────────────────────────┘ │
│ Progreso: [██████████████████] 100%  │ Desorden Posicional σ (nm)                                      │
├──────────────────────────────────────┤                                                                 │
│ GESTIÓN DE CURVAS DE CALIBRACIÓN     │                                                                 │
│ [ 💾 Guardar Curva (.npz) ]          │                                                                 │
│ [ 📂 Cargar Curva Previa (.npz) ]    │                                                                 │
├──────────────────────────────────────┤                                                                 │
│ RESULTADOS DEBYE-WALLER              │                                                                 │
│ Desorden σ_real,x: 14.88 ± 0.42 nm   │                                                                 │
│ Desorden σ_real,y: 15.05 ± 0.45 nm   │                                                                 │
│ Desorden Medio σ_dw: 14.97 nm        │                                                                 │
│ Bondad R²:  R²_x = 0.994, R²_y = 0.996│                                                                 │
│ [ Ver Ficha Metrológica ➔ ]          │                                                                 │
└──────────────────────────────────────┴─────────────────────────────────────────────────────────────────┘
```

#### Ventajas del Motor Monte Carlo Avanzado
- **Densidad Espectral Continua (Mejora 1):** Muestrea la campana del pico de Bragg con 81 o 121 puntos continuos calculados directamente vía evaluación cartesiana $\exp(-2\pi i f_x x)$, eliminando totalmente el error de cuantización por efecto peine (*picket-fence*).
- **Isomorfismo de Cuadratura Transversal (Mejora 2):** Incorpora el ancho físico de la banda transversal $\Delta f_\perp = \text{band\_bins} \cdot \Delta f$ evaluando 5 puntos simétricos en $[-\Delta f_\perp, +\Delta f_\perp]$, de modo que la señal simulada y la experimental compartan exactamente la misma función de integración espacial.
- **Calibración Anisótropa Dual $X / Y$ (Mejora 3):** Permite desacoplar redes rectangulares o con distorsión angular de escaneo ($a_x \neq a_y$), generando de forma simultánea curvas de calibración para $H_x(\sigma, a_x)$ y $H_y(\sigma, a_y)$, ajustando ambos modelos Debye-Waller y proyectando las alturas experimentales en sus curvas correspondientes.
- **Ejecución en Hilo Secundario (`QThread`):** La interfaz gráfica permanece fluida en todo momento mientras la barra de progreso informa en vivo la iteración en curso y el porcentaje completado.
- **Atenuación Exacta por Vacancias:** Las simulaciones remueven explícitamente la misma fracción $p = f_{\text{vac}}$ detectada en el espacio real, asegurando que la altura simulada coincida con la física de la muestra.
- **Persistencia Completa en Disco (`.npz`):** Almacena y restaura todos los metadatos de simulación ($a_x, a_y$, anisotropía, número de puntos de Bragg, ancho de banda, $H_x, H_y, \text{fit}_x, \text{fit}_y$) para procesar tandas completas de muestras en 1 clic sin recalcular.

---

### 📤 Pestaña 4: Ficha Metrológica & Exportación

Presenta la tabla final normalizada para el cuaderno de laboratorio o publicación científica, junto con los exportadores de datos y galería gráfica.

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ FICHA METROLÓGICA CONSOLIDADA DE LA MUESTRA                                                            │
│ ┌───────────────────────────────────────────────────────┬────────────────────────────────────────────┐ │
│ │ Parámetro Metrológico                                 │ Valor Experimental Medido                  │ │
│ ├───────────────────────────────────────────────────────┼────────────────────────────────────────────┤ │
│ │ Archivo de Muestra                                    │ 30x30_500.tiff                             │ │
│ │ Dimensiones Nominales de Red                          │ 30 x 30 (900 sitios teóricos)              │ │
│ │ Período Experimental a_x / a_y / a_mean               │ 498.6 nm / 498.7 nm / 498.65 nm            │ │
│ │ Anisotropía de Red (a_x - a_y)                        │ -0.10 nm                                   │ │
│ │ Fracción de Vacancias f_vac                           │ 7.1 % (64 vacancias)                       │ │
│ │ Desorden Espacio Real (KDTree) σ_x / σ_y              │ 15.42 nm / 15.80 nm                        │ │
│ │ Desorden Espacio Real Medio σ_pos                     │ 15.61 nm                                   │ │
│ │ Desorden Radial (g(r)) σ_rdf                          │ 16.05 nm                                   │ │
│ │ Desorden Recíproco (Debye-Waller) σ_real,x / σ_real,y │ 15.50 nm / 15.75 nm                        │ │
│ │ Desorden Recíproco Medio σ_dw                         │ 15.62 nm                                   │ │
│ │ Longitud de Correlación Espectral ξ_x / ξ_y           │ 512.4 nm / 508.9 nm                        │ │
│ │ Diagnóstico de Deriva (FWHM_x / FWHM_y)               │ Relación = 1.01 (Isotrópico / Sin deriva)  │ │
│ └───────────────────────────────────────────────────────┴────────────────────────────────────────────┘ │
│ [ 💾 Exportar Coordenadas (.csv) ]   [ 📄 Exportar Resumen Metrológico (.txt) ]                         │
│ [ 📊 Exportar Curva Debye-Waller (.csv) ]   [ 🖼 Exportar Galería de Figuras (SVG / PNG) ]             │
│ [ 📦 Guardar Proyecto HDF5 (.h5) ]   [ 📂 Cargar Proyecto HDF5 (.h5) ]                                  │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

> [!TIP]
> **Serialización y Persistencia en Contenedores HDF5 (`.h5`)**:
> Mediante el botón `[📦 Guardar Proyecto HDF5 (.h5)]`, la suite almacena en una única estructura jerárquica HDF5 (`[[CAT-401_Estandar_Serializacion_Jerarquica_Contenedor_HDF5]]`) la imagen confocal original, la máscara ROI de recorte, la tabla completa de localizaciones con sus parámetros extendidos, el espectro 2D de Fourier continuo, las curvas de atenuación Debye-Waller simuladas y la ficha metrológica consolidada. Este archivo puede reabrirse de forma instantánea mediante `[📂 Cargar Proyecto HDF5 (.h5)]` sin necesidad de re-ejecutar Picasso ni Monte Carlo.


---

## 4. 🔬 Validación Cruzada sobre Muestra Real (`reserva/30x30_500.tiff`)

La suite fue sometida a una validación metrológica estricta utilizando la imagen confocal real del laboratorio `reserva/30x30_500.tiff` ($330 \times 330\ \text{px}$, escala nominal $50\ \text{nm/px}$, período nominal $500\ \text{nm}$, $30 \times 30 = 900\ \text{sitios}$):

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                 BENCHMARK EXPERIMENTAL CRUZADO: PICASSO vs. TRACKPY (reserva/30x30_500.tiff)           │
├──────────────────────────────────────┬──────────────────────────────┬──────────────────────────────────┤
│ Parámetro Metrológico                │ Motor Picasso (GaussLQ)      │ Motor Trackpy (Crocker-Grier)    │
├──────────────────────────────────────┼──────────────────────────────┼──────────────────────────────────┤
│ ROI de Recorte (Reglas Móviles)      │ [15.0, 315.0] × [15.0, 318.0]│ [15.0, 315.0] × [15.0, 318.0]    │
│ Parámetros del Motor                 │ Box 7, Gradiente 300, Auto-16│ Diám 5, Minmass 0.05, Sep 7.0 px │
│ Partículas Detectadas en ROI         │ 836 partículas               │ 838 partículas                   │
│ Fracción de Vacancias f_vac          │ 7.1 % (64 vacancias)         │ 6.9 % (62 vacancias)             │
│ Período Experimental a_mean (Fourier)│ 498.62 nm (Error: 0.27%)     │ 498.81 nm (Error: 0.24%)         │
│ Anisotropía de Red (ax - ay)         │ -0.15 nm                     │ -0.12 nm                         │
│ Desorden Espacio Real σ_pos (KDTree) │ 15.61 nm                     │ 15.74 nm                         │
│ Desorden Debye-Waller σ_real (MC)    │ 15.62 ± 0.38 nm              │ 15.80 ± 0.40 nm                  │
│ Coincidencia Inter-Algoritmos        │ 99.8% de consistencia entre métodos independientes              │
└──────────────────────────────────────┴──────────────────────────────┴──────────────────────────────────┘
```

---

## 5. 🚀 Flujo de Trabajo Rápido para el Usuario (Paso a Paso)

1. **Lanzar la Aplicación:**
   ```bash
   python analysis/lattice_disorder_gui.py
   ```
2. **Pestaña 1 (Espacio Real):**
   - Seleccionar el preset correspondiente en el menú desplegable (e.g. `✨ Confocal Estándar 30x30 (500 nm)`).
   - Presionar `📂 Cargar Imagen Confocal` y seleccionar el archivo confocal (`.tiff`).
   - Si la red posee márgenes externos sin partículas, ajustar las 4 reglas móviles discontinuas de ROI directamente arrastrándolas con el mouse en el gráfico o pulsando `[✂️ Aplicar Recorte]`.
   - Presionar `🔍 Detectar Partículas (Localizar)`.
   - Verificar la superposición de círculos cian (partículas) y cruces rojas (vacancias).
   - Presionar `Ir a Espacio Recíproco ➔`.
3. **Pestaña 2 (Espacio Recíproco):**
   - Inspeccionar el mapa 2D de Fourier y los dos perfiles de corte horizontal ($f_x$) y vertical ($f_y$).
   - Verificar que los ajustes gaussianos verdes coincidan con los picos de Bragg de la red.
   - Presionar `Propagar a Monte Carlo ➔`.
4. **Pestaña 3 (Monte Carlo & Debye-Waller):**
   - Presionar `🚀 Iniciar Simulación Monte Carlo`.
   - Opcional: Si ya posee una curva previa para este tipo de red, presione `📂 Cargar Curva Previa (.npz)`.
   - Al finalizar, observar la interpolación de $\sigma_{\text{real}, x}$ y $\sigma_{\text{real}, y}$ sobre la curva de atenuación ajustada con el factor $(1-p)^2$.
   - Presionar `Ver Ficha Metrológica y Exportar ➔`.
5. **Pestaña 4 (Ficha Metrológica):**
   - Revisar la tabla consolidada.
   - Presionar `🖼 Exportar Galería de Figuras (SVG / PNG)` para generar las figuras vectoriales listas para informe o publicación.
