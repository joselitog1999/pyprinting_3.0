# 🔬 Módulo 06: Analizador de Imágenes Estáticas (`analysis/image_analyzer.py`)

**Laboratorio de Nanofotónica — Instituto de Nanosistemas (INS-UNSAM / CONICET)**  
**Archivo Fuente**: [`analysis/image_analyzer.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/analysis/image_analyzer.py)  
**Lanzador Rápido**: Botón 8 en [`main.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/main.py) o `Tools -> Analizador de Imágenes` desde `app.py`

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

La restauración de imagen busca estimar la escena verdadera $u(x, y)$ a partir de la imagen observada borrosa $d(x, y)$ y la PSF del objetivo $h(x, y)$ mediante el esquema iterativo multiplicativo:

$$u_{k+1}(x, y) = u_k(x, y) \cdot \left[ \left( \frac{d(x, y)}{u_k(x, y) * h(x, y)} \right) * h^*(-x, -y) \right]$$

donde $*$ denota la **convolución 2D espacial**, calculada eficientemente en el dominio de Fourier mediante el Teorema de Convolución:
$$f * g = \mathcal{F}^{-1}\left\{ \mathcal{F}\{f\} \cdot \mathcal{F}\{g\} \right\}$$

- **Protección contra división por cero**: Se incorpora un $\epsilon = 10^{-12}$ en el denominador para evitar inestabilidades numéricas en regiones oscuras del fondo.

---

## 7. ⚠️ Límites de Validez y Modos de Falla

| Condición de Borde (Fallo de Procesamiento / Algoritmo) | Firma Experimental (Imagen Deconvolucionada / Localización) | Acción Correctiva Física (Procedimiento en Laboratorio) |
| :--- | :--- | :--- |
| **Artefactos de Anillo (*Ringing*) por Sobredesconvolución** ($N_{\text{iter}} > 50$). | Halos oscuros concéntricos artificiales y amplificación de ruido granular de alta frecuencia alrededor de partículas brillantes. | Reducir el número de iteraciones de Richardson-Lucy a $15 - 25$ y aplicar filtrado gaussiano previo de baja frecuencia ($\sigma = 1.0\ \text{px}$). |
| **Falsos Duplicados en Localización Trackpy/Picasso** (`min_mass` o `separation` muy bajos). | Una única nanopartícula física es etiquetada erróneamente como dos o tres centroides a distancias irreales sub-50 nm. | Incrementar el parámetro de separación mínima en la ventana de detección y ajustar el umbral de masa mínima (`min_mass`) por encima del ruido de fondo. |
| **Desajuste de la PSF Experimental Empleada en Deconvolución**. | Deformación o elongación artificial de las partículas en la imagen restaurada (apariencia astigmática falsa). | Adquirir un mapa confocal 2D fresco de una nanopartícula aislada de Au 60 nm para extraer la PSF experimental real del día antes de deconvolucionar. |

---

## 8. 🔗 Referencias Cruzadas
- [📘 Manual de Usuario — Sección 6: Analizador de Imágenes y Deconvolución](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/docs/MANUAL_USUARIO.md#6-analizador-de-imágenes-y-deconvolución-richardson-lucy)
- [📑 Reporte Científico de Deconvolución y SMLM (`reportes/cientificos/Deconvolucion_Richardson_Lucy_y_Trackpy_PyPrinting3.md`)](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/reportes/cientificos/Deconvolucion_Richardson_Lucy_y_Trackpy_PyPrinting3.md)
