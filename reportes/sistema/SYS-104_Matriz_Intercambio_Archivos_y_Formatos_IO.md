# SYS-104: Matriz de Intercambio de Archivos, Formatos I/O e Interoperabilidad 📄

**PyPrinting 3.0 / PySpectrum 3.0 — Suite de Nanofotónica y Control Instrumental**  
**Laboratorio de Nanofotónica — Instituto de Nanosistemas (INS-UNSAM / CONICET)**  
**Autor Principal:** José Luis González Peñafiel (*Becario Doctoral CONICET*)  
**Código del Documento:** `SYS-104` | **Eje Temático:** `[DAT] (Arquitectura de Datos e Interoperabilidad de Archivos)`  
**Fecha de Emisión:** Septiembre 2026 | **Estado:** Aprobado / Producción

---

## 🔗 Matriz de Referencias Cruzadas

- **Reportes de Sistema Conexos:**
  - `[[SYS-103_Regimenes_Coordenadas_e_Invariancia_Cinematica]]`
  - `[[SYS-304_Arquitectura_Analizador_SIF_y_Filtros_Cascada]]`
- **Fundamentos Científicos Asociados:**
  - `[[CAT-401_Estandar_Serializacion_Jerarquica_Contenedor_HDF5]]`
- **Módulos de Código Fuente:** `core/preset_manager.py`, `modules/measurements.py`, `image_analyzer.py`, `psf_analyzer.py`

---

## 1. Resumen Ejecutivo y Evaluación de Compatibilidad

En atención a la directiva del laboratorio, se realizó una auditoría completa del **flujo de intercambio de archivos** entre todos los programas y módulos de la suite **PyPrinting 3.0** (`main.py`, `app.py`, `measurements.py`, `image_analyzer.py`, `psf_analyzer.py`, `camera.py`, `preset_manager.py`).

Se ha verificado rigurosamente que la **nueva exportación multimaterial** (`.tiff`, `.npy`, `.csv`):
1. **Conserva 100% la compatibilidad hacia atrás**: Mantiene intacto el archivo primario `NPscan_XXX.tiff` (formato 16-bit uint) y las matrices de texto `NPscan_rescaled_XXX.txt`, garantizando que programas como `image_analyzer.py` y `psf_analyzer.py` sigan consumiendo estos datos sin ninguna modificación ni ruptura de contrato.
2. **Amplía las capacidades de interoperabilidad**: Añade archivos secundarios adyacentes (`.npy` binario NumPy y `.csv` tabular delimitado por comas) para su análisis inmediato en scripts externos de Python, MATLAB, R o OriginPro.

---

## 2. Matriz Completa de Intercambio de Archivos entre Programas

| Programa Productor (Origen) | Archivo / Formato Generado | Programa Consumidor (Destino) | Estructura de Datos y Uso | Garantía de Compatibilidad |
|---|---|---|---|---|
| **`measurements.py`** (`Printing`/`Dimers`) | `NPscan_XXX.tiff`<br>`gone_NPscan_XXX.tiff`<br>`back_NPscan_XXX.tiff` | `image_analyzer.py`<br>`psf_analyzer.py`<br>Visores Externos | Imagen raster confocal 2D en formato TIFF uint 16-bit rescalado [0, 65535]. | 🟢 **100% Compatible**. Nombre, dimensiones y tipo uint16 preservados. |
| **`measurements.py`** (`Printing`/`Dimers`) | `NPscan_XXX.npy`<br>`NPscan_XXX.csv` *(Nuevo)* | Scripts Externos (Python, MATLAB, R, Origin) | Matriz 2D de intensidades crudas en formato binario (.npy) y tabular (.csv). | 🟢 **Aditivo**. Se guardan como archivos sidecar sin interferir con la lectura del TIFF. |
| **`measurements.py`** (`Printing`/`Dimers`) | `NPscan_rescaled_XXX.txt`<br>`NPscan_rescaled_XXX.tiff` | `psf_analyzer.py`<br>Scripts de Calibración | Matriz 2D en texto plano (`fmt=%.4e`) y TIFF correspondiente a la intensidad corregida en Modo 3. | 🟢 **100% Compatible**. Mantiene el estándar numérico previo. |
| **`measurements.py`** (`Printing`/`Dimers`) | `NP_XXX.txt` | Módulos de Traza / Análisis Temporal | Tabla de 3 columnas `[Tiempo (s), Fotodiodo L1 (V), Fotodiodo BS (V)]` (`fmt=%.3e`). | 🟢 **100% Compatible**. |
| **`grid_generator.py`** *(Diseñador 2D)* | `*.txt` (Unificado)<br>`PassX_Material_Y_ref_P0.txt`<br>`Recipe_Metadata.json` | `measurements.py` (`Load grid`)<br>Simuladores Cuánticos / FDTD | Recetas de impresión cristalográfica 2D ordenadas, coordenadas de Partícula Ancla P0 y metadatos JSON. | 🟢 **100% Compatible**. Consumido directamente por `Load grid`. |
| **`pyspectrum.py`** *(PySpectrum 3.0)* | `Spectrum_*.txt`<br>`StepAndGlue_*.txt`<br>`Hyperspectral_*.npy` | `analysis/`<br>OriginPro / Python | Espectros ópticos calibrados con lámpara halógena, espectro oscuro y cubos de datos 3D $(X, Y, \lambda)$. | 🟢 **100% Compatible**. |
| **`measurements.py`** (`Printing`/`Dimers`) | `grid_info.txt` | `app.py`<br>Gestor de Sesión | Metadatos de la grilla impresa (coordenadas, referencia X/Y, número de partículas). | 🟢 **100% Compatible**. Escrito de forma segura previa verificación de directorio. |
| **`measurements.py`** (`Printing`/`Dimers`) | `Last_position.txt` (`LAST_POS_FILE`) | `app.py`<br>`measurements.py` | Estado de auto-recuperación ante fallos eléctricos (`i_global`, `startX`, `startY`). | 🟢 **100% Compatible**. Actualizado nodo a nodo. |
| **`preset_manager.py`** / **`preset_wizard.py`** | `presets/*.txt` | `measurements.py` (`MeasFrontend`) | Archivos `.txt` con formato clave-valor para la carga de presets experimentales. | 🟢 **100% Compatible**. Gestor dinámico con soporte de carga directa `QFileDialog`. |
| **`camera.py`** / **`modules/camera.py`** | `camera_snapshot_*.png` / `.tiff` | `image_analyzer.py`<br>Reportes | Capturas estáticas del campo óptico de la cámara Canon EOS 500D (15.1 MP) o Thorlabs/USB. | 🟢 **100% Compatible**. |
| **`image_analyzer.py`** | `tracking_results.csv`<br>Imágenes Procesadas | `reportes/`<br>Publicaciones | Resultados de centrado de masa y seguimiento de trayectorias trackpy. | 🟢 **100% Compatible**. |
| **`psf_analyzer.py`** | `psf_fit_results.txt` | `reportes/`<br>Publicaciones | Parámetros del ajuste Gaussiano 2D / Donut LG01 y mapa de residuales. | 🟢 **100% Compatible**. |

---

## 3. Esquema de Flujo de Datos e Interoperabilidad

```
                               ┌──────────────────────────────────────────────┐
                               │           core/preset_manager.py             │
                               │           (presets/*.txt)                    │
                               └──────────────────────┬───────────────────────┘
                                                      │ (Lee/Escribe presets)
                                                      ▼
┌──────────────────────┐                       ┌──────────────────────────────┐
│  grid_info.txt /     │ ────────────────────► │       measurements.py        │
│  Last_position.txt   │ ◄──────────────────── │   (Print / Dimers Worker)    │
└──────────────────────┘                       └──────────────┬───────────────┘
                                                              │
                                        ┌─────────────────────┼─────────────────────┐
                                        ▼                     ▼                     ▼
                               ┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
                               │  NPscan_XXX.tiff│   │  NPscan_XXX.npy │   │  NPscan_XXX.csv │
                               │ (TIFF Primario) │   │  (NumPy Binary) │   │ (CSV Tabular)   │
                               └────────┬────────┘   └─────────────────┘   └─────────────────┘
                                        │
                         ┌──────────────┴──────────────┐
                         ▼                             ▼
              ┌────────────────────┐        ┌────────────────────┐
              │ image_analyzer.py  │        │  psf_analyzer.py   │
              │ (Tracking 2D)      │        │ (Ajuste Gaussiano) │
              └────────────────────┘        └────────────────────┘
```

---

## 4. Conclusión

La arquitectura de almacenamiento multimaterial de **PyPrinting 3.0** garantiza una **compatibilidad total sin fisuras** con los programas analizadores existentes (`image_analyzer.py`, `psf_analyzer.py`), al tiempo que enriquece la suite con soporte binario `.npy` y tabular `.csv` para investigación avanzada.

---

## 5. Contenedor HDF5 del Escaneo Lineal Espectral

### 5.1 Fila de Matriz (consistente con la Sección 2)

| Programa Productor (Origen) | Archivo / Formato Generado | Programa Consumidor (Destino) | Estructura de Datos y Uso | Garantía de Compatibilidad |
|---|---|---|---|---|
| **`linescan_spectroscopy.py`** (`LineScanSpectroscopyWorker`) → `core/hdf5_container.py::write_linescan_spectroscopy_hdf5` | `data_linescan_spectroscopy/linescan_AAAAMMDD_HHMMSS.h5` | Ninguno interno todavía (sin analizador dedicado en el repositorio); consumido directamente por h5py / MATLAB / OriginPro. *(`analysis/figure_export_studio.py` solo exporta la curva en vivo del widget, no lee este `.h5`.)* | Contenedor jerárquico HDF5 (`shuffle`+`gzip`-4, mismo criterio que `BatchHDF5Container`, ver `CAT-401`) con transmitancia/extinción espacio-espectral 1D+2D, referencia cruda y metadatos de trazabilidad del umbral de ruido. Detalle en §5.2. | 🟢 **Esquema jerárquico propio** (`metadata/coordinates/wavelengths/reference/raw_data/processed`), independiente de `BatchHDF5Container` y de los formatos sueltos `Spectrum_*.txt`/`Hyperspectral_*.npy` — no rompe ningún contrato existente. |

### 5.2 Detalle de Grupos y Datasets

- **`/metadata`** *(solo atributos)*: `timestamp`, `t_exp_1d_s`, `t_exp_2d_s`, `roi_ymin`/`roi_ymax`, `acquisition_mode` (`single_window`|`step_and_glue`), `extinction_formula` (`"-log10(T)"`), `acquisition_readout_margin_s`, `noise_threshold_1d`; + `glue_start_wl_nm`/`glue_end_wl_nm`/`glue_overlap_pct` si Step & Glue.
- **`/coordinates/x_positions_um`** `(N_pasos,)` float64 — posiciones X absolutas de la platina PI E-517 (µm).
- **`/wavelengths/lambda_nm`** `(N_λ,)` float64 — grilla espectral común; fija (≤1004 px, sensor nativo) en Ventana Única, o emergente de `glue_steps()` (>1004, fijada por la primera adquisición de Referencia) en Step & Glue, con todo punto espacial posterior interpolado (`np.interp`) a esa misma grilla.
- **`/reference/{signal,background}_1d`** `(N_λ,)` float32; **`{signal,background}_2d`** `(ROI_alto,N_λ)` float32 — señal/fondo crudos de Fase A. **`sigma_dark_1d`** `(N_λ,)` float32 (escalar `std(bg_1d)` difundido a vector) y **`sigma_dark_2d`** `(ROI_alto,)` float32 (`std(bg_2d,axis=1)`, por fila) — base del umbral `mult·σ_dark`.
- **`/raw_data/sample_1d`** `(N_pasos,N_λ)`, **`sample_2d`** `(N_pasos,ROI_alto,N_λ)`, float32 — espectro/imagen crudos por paso espacial. **`native_length_mismatch`** `(N_pasos,)` bool — solo no-trivial en Step & Glue: `True` si la longitud nativa emergente de `glue_steps()` en ese paso difirió de la grilla de referencia común antes de interpolar.
- **`/processed/transmission_{1d,2d}`** — mismo shape que `raw_data`, float64. $T(\lambda,x)$ **sin clampear** (puede contener residuales negativos cerca de $T\approx0$, ruido dark simétrico legítimo); `NaN` donde $(I_{ref}-I_{ref\_bg}) \le$ `noise_threshold`.
- **`/processed/transmission_{1d,2d}_physical`** — ídem shape, float64. Derivado `clip(T,0,None)`; atributos `clipping_applied=True`, `rationale="positividad fisica, no correccion metrologica"`. Ver `DEC-008` (`docs/decisions/DECISION_LOG.md`) para una nota de trazabilidad: `extinction_*` en esta versión se calcula desde `T` cruda, no desde este dataset derivado.
- **`/processed/extinction_{1d,2d}`** — ídem shape, float64. $E=-\log_{10}(T)$; atributo `formula="-log10(T)"` en el propio dataset.

Compresión uniforme `shuffle`+`gzip` nivel 4 en todos los datasets (criterio `CAT-401`), verificada en `tests/test_linescan_h5.py` (9/9 passing).
