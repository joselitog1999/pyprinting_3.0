# Reporte de Matriz de Intercambio de Archivos y Compatibilidad Multimaterial (PyPrinting 3.0) 📄

**Laboratorio de Nanofotónica — Instituto de Nanosistemas (INS-UNSAM / CONICET)**  
**Autor Principal**: José Luis González Peñafiel (*Becario Doctoral CONICET*)  
**Fecha de Publicación**: 11 de Agosto de 2026  
**Ubicación del Reporte**: `reportes/sistema/Matriz_de_Intercambio_de_Archivos_PyPrinting3.md`  

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
