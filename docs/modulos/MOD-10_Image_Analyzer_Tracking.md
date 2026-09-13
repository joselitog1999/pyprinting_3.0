# MOD-10: Analizador de Imágenes Estáticas y Tracking Sub-Píxel 🔍

**PyPrinting 3.0 — Suite de Nanofotónica y Control Instrumental**  
**Laboratorio de Nanofotónica — Instituto de Nanosistemas (INS-UNSAM / CONICET)**  
**Manual de Usuario Canónico** | **Código:** `MOD-10` | **Nivel de Usuario:** Básico / Operador / Experto  
**Archivo Fuente**: [`analysis/image_analyzer.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/analysis/image_analyzer.py)  
**Lanzador Rápido**: Botón 8 en [`main.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/main.py) o `Tools -> Analizador de Imágenes` desde `app.py`

---

## 🔗 Matriz de Referencias Cruzadas

* **Reportes de Sistema Conexos:**
  * `[[SYS-105_Pipeline_Unificado_Localizacion_Super_Resolucion]]`
  * `[[SYS-104_Matriz_Intercambio_Archivos_y_Formatos_IO]]`
* **Fundamentos Científicos Asociados:**
  * `[[CAT-201_Deconvolucion_Optica_Richardson_Lucy_y_Tracking_Trackpy]]`
  * `[[CAT-202_Derivacion_Matematica_Cota_Cramer_Rao_Localizacion_Optica]]`
  * `[[CAT-108_Teoria_Optica_Telescopio_Rele_4f_y_Canales_Confocales]]`
* **Manuales de Usuario Conexos:**
  * `[[MOD-01_Microscopio_Derecho_App]]`
  * `[[MOD-04_Camara_Live_View_Canon_EDSDK]]`
  * `[[MOD-08_Analizador_Desorden_Redes_2D]]`
  * `[[MOD-09_PSF_Analyzer_Optica_Difraccion]]`
  * `[[MOD-14_Protocolos_Laboratorio_SOP]]`

---

## 1. 🏷️ Resumen y Rol en el Sistema

El **Analizador de Imágenes (`image_analyzer.py`)** es una estación de trabajo fotónica completa para el procesamiento avanzado y análisis cuantitativo de micrografías ópticas estáticas (cámara réflex Canon, cámaras CMOS o escaneos confocales exportados).

Herramientas principales:
- **Deconvolución Iterativa Richardson-Lucy en Tiempo Real**: Algoritmo de restauración de imágenes acelerado por Transformadas Rápidas de Fourier 2D (`scipy.fft` / NumPy) para revertir el ensanchamiento óptico por difracción impuesto por la PSF del microscopio. Soporta imágenes monocromáticas y RGB independientes.
- **Calibración de Escala Micrométrica (`SetScaleDialog`)**: Conversión interactiva de píxeles a micrómetros reales mediante patrones de calibración o reglas sobre el canvas.
- **Suite de Reglas y Mediciones Geométricas**: Cálculo de distancias punto a punto ($L_{\mu\text{m}}$), ángulos y perfiles de intensidad sobre líneas arbitrarias.
- **Motor Dual de Detección y Conteo de Nanopartículas**:
  - **Trackpy**: Algoritmo de centrado por momentos ponderados de brillo y separación espacial mínima.
  - **Picasso (SMLM / DNA-PAINT)**: Ajuste sub-píxel por **Máxima Verosimilitud (GaussMLE)**, Mínimos Cuadrados (GaussLQ) y Centro de Masas (Avg), con reporte de fotones y desviaciones estándar.

---

## 2. 🖼️ Maqueta de la Interfaz Visual (ASCII Layout)

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│  PyPrinting 3.0 — Analizador de Imágenes y Deconvolución Richardson-Lucy                              -  □  ×    │
├──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│  BARRA DE HERRAMIENTAS PRINCIPAL                                                                                 │
│  [ 📂 Abrir Foto ]  [ 💾 Guardar Imagen ]  [ 📐 Set Scale ]  [ 📏 Nueva Regla ]  [ 🔍 Detectar ]  [ 🧹 Limpiar ]  │
│  [ 🔄 Deconvolución Richardson-Lucy ]  │ Escala: [ 0.08420 µm/px ]  │ Zoom: [───●─────] 100%  [ 🔄 Reset Zoom ]  │
├───────────────────────────────────────────────────────────────────────┬──────────────────────────────────────────┤
│  CANVAS GRÁFICO INTERACTIVO (PyQt6 GraphicsView + Overlay)            │  PANEL DE MEDICIONES Y PARTÍCULAS        │
│  ┌─────────────────────────────────────────────────────────────────┐ │  TABLA DE REGLAS / DISTANCIAS:           │
│  │                                                                 │ │  ┌────┬──────────┬──────────┬──────────┐  │
│  │   [ Micrografía Óptica Cargada / Deconvolucionada ]             │ │  │ #  │ L (µm)   │ L (px)   │ Ángulo   │  │
│  │                                                                 │ │  ├────┼──────────┼──────────┼──────────┤  │
│  │   ┌────────────────────────┐                                    │ │  │ 1  │ 3.012 µm │ 35.77 px │ 0.0°     │  │
│  │   │ Recorte ROI Deconv     │  ├── 3.01 µm ──┤ [Regla #1]        │ │  │ 2  │ 5.985 µm │ 71.08 px │ 90.2°    │  │
│  │   │ 🟢 NP #1 (25.4, 30.1)  │                                    │ │  └────┴──────────┴──────────┴──────────┘  │
│  │   │ 🟢 NP #2 (28.4, 30.1)  │                                    │ │  TABLA DE PARTÍCULAS (PICASSO / TRACKPY): │
│  │   │ 🟢 NP #3 (31.4, 30.1)  │                                    │ │  ┌────┬──────────┬──────────┬──────────┐  │
│  │   └────────────────────────┘                                    │ │  │ #  │ x (µm)   │ y (µm)   │ Photons  │  │
│  │                                                                 │ │  ├────┼──────────┼──────────┼──────────┤  │
│  │                                                                 │ │  │ 1  │ 25.412   │ 30.150   │ 48520.0  │  │
│  │                                                                 │ │  │ 2  │ 28.420   │ 30.148   │ 51200.0  │  │
│  │  ├── 10.0 µm ──┤ [Escala Calibrada]                             │ │  │ 3  │ 31.405   │ 30.155   │ 49800.0  │  │
│  └─────────────────────────────────────────────────────────────────┘ │  └────┴──────────┴──────────┴──────────┘  │
│  [ 💾 Exportar Tabla CSV ]  [ 💾 Exportar Imagen Anotada ]           │  Total: 3 partículas | Dist. Media: 3.00 µm│
├───────────────────────────────────────────────────────────────────────┴──────────────────────────────────────────┤
│  🟢 Imagen: Foto_20260826_153000.tiff (4752x3168 RGB) | Deconvolución: 20 iteraciones (PSF σ=1.5 px) | Listo    │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. 🎛️ Catálogo de Botones y Controles

| Control / Botón | Tipo de Widget | Rango / Opciones | Descripción Técnica |
|---|---|---|---|
| `Abrir Foto` | `QPushButton` | Archivos `.tiff, .jpg, .png, .bmp` | Carga una imagen de microscopía en memoria preservando el rango dinámico. |
| `Set Scale` | `QPushButton` | Diálogo modal | Define la relación $\mu\text{m}/\text{px}$ trazando una línea sobre un patrón conocido. |
| `Deconvolución R-L` | `QPushButton` | Diálogo interactivo | Abre el cuadro de diálogo para parametrizar la PSF sintética y número de iteraciones. |
| `Nueva Regla` | `QPushButton` | Clic y arrastre | Permite trazar líneas de medición métrica punto a punto sobre el canvas. |
| `Detectar Partículas`| `QPushButton` | Trackpy / Picasso | Abre el asistente de localización sub-píxel para contabilizar partículas en toda la foto o ROI. |
| `Exportar CSV` | `QPushButton` | Archivo `.csv` | Guarda la tabla de distancias o de centroides de partículas detectadas. |
| `Exportar Anotada` | `QPushButton` | Archivo `.png / .jpg` | Guarda la imagen combinada con todas las reglas, etiquetas, cruces y barras de escala. |

---

## 4. 📥 Archivos de Entrada que Solicita

1. **Micrografías de Entrada (`*.tiff`, `*.tif`, `*.jpg`, `*.jpeg`, `*.png`, `*.bmp`)**:
   - Soporta imágenes monocromáticas (8 y 16 bits) e imágenes RGB color (24 y 48 bits).

---

## 5. 📤 Archivos de Salida que Genera

1. **Imagen Deconvolucionada (`*_deconv_RL.tiff`)**:
   - Imagen restaurada en formato TIFF de 16 bits sin pérdidas de compresión.
2. **Imagen Anotada con Mediciones (`*_annotated.png`)**:
   - Render gráfico de alta resolución conteniendo las reglas, marcas de partículas y escala física.
3. **Tabla de Mediciones y Coordenadas (`measurements_table.csv`)**:
   - *Estructura*:
     ```csv
     # PyPrinting 3.0 Image Analyzer Export
     # File: Foto_20260826_153000.tiff | Scale: 0.0842 um/px
     Type,ID,X_start_um,Y_start_um,X_end_um,Y_end_um,Length_um,Length_px,Angle_deg
     Ruler,1,25.40,30.15,28.41,30.15,3.01,35.77,0.0
     Particle,1,25.41,30.15,-,-,-,-,-
     Particle,2,28.42,30.15,-,-,-,-,-
     ```

---

## 6. ⚙️ Algoritmo de Deconvolución Richardson-Lucy

> [!NOTE] Deducción Teórica Rigurosa y Análisis de Convergencia
> Para la demostración formal por máxima verosimilitud de Poisson, criterios de parada por gradiente conjugado y regularización de Tikhonov-Total Variation, consultar el reporte científico canónico:
> **[[CAT-201_Deconvolucion_Optica_Richardson_Lucy_y_Tracking_Trackpy|CAT-201: Deconvolución Richardson-Lucy y Tracking]]** y la arquitectura de pipeline **[[SYS-105_Pipeline_Unificado_Localizacion_Super_Resolucion|SYS-105: Pipeline Unificado de Localización Super-Resolución]]**.

La restauración de imagen busca estimar la escena verdadera $u(x, y)$ a partir de la imagen observada borrosa $d(x, y)$ y la PSF del objetivo $h(x, y)$ mediante el esquema iterativo multiplicativo:

$$u_{k+1}(x, y) = u_k(x, y) \cdot \left[ \left( \frac{d(x, y)}{u_k(x, y) * h(x, y) + \epsilon} \right) * h^*(-x, -y) \right]$$

donde $*$ denota la convolución 2D espacial, calculada eficientemente en el dominio de Fourier mediante 2D-FFT con regularización de fondo $\epsilon = 10^{-12}$.

---

## 7. ⚠️ Límites de Validez y Modos de Falla

| Condición de Borde (Fallo de Procesamiento / Algoritmo) | Firma Experimental (Imagen Deconvolucionada / Localización) | Acción Correctiva Física (Procedimiento en Laboratorio) |
| :--- | :--- | :--- |
| **Artefactos de Anillo (*Ringing*) por Sobredesconvolución** ($N_{\text{iter}} > 50$). | Halos oscuros concéntricos artificiales y amplificación de ruido granular de alta frecuencia alrededor de partículas brillantes. | Reducir el número de iteraciones de Richardson-Lucy a $15 - 25$ y aplicar filtrado gaussiano previo de baja frecuencia ($\sigma = 1.0\ \text{px}$). |
| **Falsos Duplicados en Localización Trackpy/Picasso** (`min_mass` o `separation` muy bajos). | Una única nanopartícula física es etiquetada erróneamente como dos o tres centroides a distancias irreales sub-50 nm. | Incrementar el parámetro de separación mínima en la ventana de detección y ajustar el umbral de masa mínima (`min_mass`) por encima del ruido de fondo. |
| **Desajuste de la PSF Experimental Empleada en Deconvolución**. | Deformación o elongación artificial de las partículas en la imagen restaurada (apariencia astigmática falsa). | Adquirir un mapa confocal 2D fresco de una nanopartícula aislada de Au 60 nm para extraer la PSF experimental real del día antes de deconvolucionar. |

---

## 8. 🔗 Referencias Cruzadas
- [[SYS-105_Pipeline_Unificado_Localizacion_Super_Resolucion|🔬 SYS-105: Pipeline Unificado de Localización Super-Resolución]]
- [[SYS-104_Matriz_Intercambio_Archivos_y_Formatos_IO|📑 SYS-104: Matriz de Intercambio de Archivos y Formatos I/O]]
- [[CAT-201_Deconvolucion_Optica_Richardson_Lucy_y_Tracking_Trackpy|📐 CAT-201: Deconvolución Richardson-Lucy y Tracking Trackpy]]
- [[CAT-202_Derivacion_Matematica_Cota_Cramer_Rao_Localizacion_Optica|🎯 CAT-202: Cota de Cramér-Rao en Localización Óptica]]
- [[MOD-08_Analizador_Desorden_Redes_2D|📊 MOD-08: Analizador de Desorden en Redes 2D]]
- [[MOD-09_PSF_Analyzer_Optica_Difraccion|🔬 MOD-09: PSF Analyzer & Óptica de Difracción]]
- [[MANUAL_USUARIO|📘 Manual de Usuario Principal]]
