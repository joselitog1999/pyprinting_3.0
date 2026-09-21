# CAT-400: Gobernanza de Datos Científicos, Trazabilidad Metrológica y Ecosistema FAIR
## Tratado Rector de Arquitectura de Datos, Serialización Jerárquica HDF5 / NeXus, Preservación Criptográfica y Visualización Vectorial para Publicación

---

**Signatura Bibliotecaria:** `CAT-400`  
**Clasificación Temática:** `[CMP]` / `[MET]` Gobernanza de Datos Científicos, Serialización FAIR y Metrología Gráfica  
**Pilar:** Pilar IV — Arquitectura de Datos, Serialización y Ecosistema de Software (NODO RECTOR)  
**Autoría:** José Luis González Peñafiel (*Becario Doctoral CONICET*), Comité Científico PyPrinting 3.0  
**Fecha de Publicación:** Septiembre 2026  
**Estado:** Producción / Consolidado  
**Módulos Asociados:** `core/hdf5_container.py`, `analysis/figure_export_studio.py`, `config.py`, `io/`  
**Documentos Vinculados:**  
- [[CAT-401_Estandar_Serializacion_Jerarquica_Contenedor_HDF5]] (Jerarquía HDF5 y compresión gzip)  
- [[CAT-402_Estandar_Datos_FAIR_y_Serializacion_NeXus_HDF5]] (Ontología formal NeXus y datos FAIR)  
- [[CAT-403_Estandares_Visualizacion_Cientifica_y_Graficos_Vectoriales]] (Metrología visual, SVG/PDF editorial)  
- [[SYS-001_Estandares_Diseno_Arquitectura_PyPrinting3]] (Arquitectura software general)  
- [[SYS-104_Matriz_Intercambio_Archivos_y_Formatos_IO]] (Formatos de entrada/salida)  

---

## 1. Resumen Ejecutivo

En la investigación física moderna, los datos experimentales y los análisis derivados no pueden ser archivos huérfanos sin trazabilidad. Un resultado publicado en una revista científica internacional debe ser **completamente reproducible desde primeros principios**, permitiendo que cualquier investigador audite la cadena de custodia completa: desde las señales analógicas crudas del fotodiodo y las imágenes de cámara, hasta las coordenadas de super-resolución y los parámetros de ajuste de redes.

Este reporte actúa como el **Nodo Rector y Nota Paraguas del Pilar IV**. Define la política de gobernanza y persistencia de datos en PyPrinting 3.0, garantizando el cumplimiento estricto de los **Principios FAIR (Findable, Accessible, Interoperable, Reusable)**. Se formaliza el contenedor jerárquico unificado **HDF5** (`core/hdf5_container.py`), la integración con el estándar internacional de instrumentación **NeXus**, la preservación de la cadena de custodia mediante **firmas criptográficas SHA-256**, y los estándares de **metrología visual y representación gráfica vectorial** en `analysis/figure_export_studio.py`.

---

## 2. Los Principios FAIR Aplicados a la Nanofabricación Óptica

| Principio FAIR | Requisito en Nanociencias | Implementación Concreta en PyPrinting 3.0 | Documento Canónico |
| :--- | :--- | :--- | :--- |
| **Findable** (Encontrable) | Datos y metadatos identificables inequívocamente con esquemas universales. | Identificador único de muestra, metadatos estructurados en la raíz `/metadata` y hash SHA-256. | [[CAT-401_Estandar_Serializacion_Jerarquica_Contenedor_HDF5]] |
| **Accessible** (Accesible) | Protocolos abiertos y libres de dependencias de software propietario cerrado. | Formato abierto HDF5 (RFC ISO/IEC 11578), inspeccionable con Python (`h5py`), C++, Julia o HDFView. | [[CAT-401_Estandar_Serializacion_Jerarquica_Contenedor_HDF5]] |
| **Interoperable** (Interoperable) | Ontologías consensuadas por la comunidad internacional. | Ontología NeXus (`NXdata`, `NXsample`, `NXinstrument`), estándar de sincrotrones y laboratorios de neutrones. | [[CAT-402_Estandar_Datos_FAIR_y_Serializacion_NeXus_HDF5]] |
| **Reusable** (Reutilizable) | Preservación de toda la cadena de parámetros experimentales y procedencia. | Registro inmutable de potencias láser, frecuencias de muestreo, modelos de cámara y versiones de software. | [[CAT-402_Estandar_Datos_FAIR_y_Serializacion_NeXus_HDF5]] |

---

## 3. Jerarquía Canónica del Contenedor HDF5 (`.h5`)

En `core/hdf5_container.py`, todos los flujos de una campaña se encapsulan en un árbol jerárquico único:

```
archivo_campana.h5
├── /metadata                (Parámetros globales, autor, laboratorio, timestamp, hash SHA-256)
├── /raw                     (Imágenes directas del sensor, trazas de fotodiodo a 10 kHz)
├── /curated                 (Coordenadas sub-píxel post-Picasso/Trackpy y curación fotométrica)
├── /reciprocal              (Mapas 2D de factor de estructura S(q), perfiles BFP y cortes radiales)
└── /nexus                   (Vistas canónicas compatibles con visualizadores NeXus)
```

---

## 4. Mapa de Navegación del Pilar IV

```
                                  MAPA DE NAVEGACIÓN — PILAR IV
                                                
                                   CAT-400 (ESTE DOCUMENTO)
                                        [NODO RECTOR]
                                              │
         ┌────────────────────────────────────┼────────────────────────────────────┐
         ▼                                    ▼                                    ▼
    [CONTENEDOR HDF5]                    [ESTÁNDAR FAIR / NEXUS]              [METROLOGÍA GRÁFICA]
      CAT-401 (Serialización HDF5)         CAT-402 (Ontología NeXus)            CAT-403 (Exportación Editorial)
      SYS-104 (Formatos I/O)                                                    SYS-001 (Estándares de Diseño)
```

---

## 5. Referencias Bibliográficas Primarias

1. **Wilkinson, M. D., et al.** (2016). *The FAIR Guiding Principles for scientific data management and stewardship*. Scientific Data, 3, 160018. [DOI: 10.1038/sdata.2016.18](https://doi.org/10.1038/sdata.2016.18)
2. **Könnecke, M., et al.** (2015). *The NeXus data format*. Journal of Applied Crystallography, 48(1), 301–305. [DOI: 10.1107/S1600576714027575](https://doi.org/10.1107/S1600576714027575)
3. **The HDF Group** (2000-2026). *Hierarchical Data Format, version 5*. [https://www.hdfgroup.org/HDF5/](https://www.hdfgroup.org/HDF5/)
