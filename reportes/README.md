# Índice General de Reportes y Documentación Técnica (PyPrinting 3.0) 📑

**Laboratorio de Nanofotónica — Instituto de Nanosistemas (INS-UNSAM / CONICET)**  
**Autor Principal**: José Luis González Peñafiel (*Becario Doctoral CONICET*)  
**Ubicación del Índice**: `reportes/README.md`  

---

## 📖 Estructura de Clasificación de la Documentación

En concordancia con el **Estándar 5 de Diseño (Conservación de la Información, Valor del Conocimiento Generado y Autosuficiencia Pedagógica)**, todo el acervo documental del proyecto **PyPrinting 3.0** se encuentra organizado en dos vertientes especializadas:

```
reportes/
├── ⚙️ sistema/          # Reportes de Estado del Sistema, Arquitectura e Ingeniería
└── 🔬 cientificos/       # Reportes Científicos, Fundamentos Físicos y Protocolos
```

---

## ⚙️ 1. Reportes de Estado del Sistema y Mantenimiento Técnico (`reportes/sistema/`)

*Útiles para mantenimiento de software, consulta del funcionamiento profundo de hilos, auditoría de hardware, diagnóstico I/O, telemetría y seguimiento de estándares.*

| Documento / Reporte | Descripción y Enfoque Técnico | Enlace Directo |
|---|---|---|
| **Informe de Estado y Estándares** | Estado actual del sistema, matriz por módulo, métricas de Graphify, Tablero de Conexiones y los 5 Estándares de Diseño. | [Informe_de_Estado_Mejoras_y_Estandares_de_Diseno_PyPrinting3.md](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/reportes/sistema/Informe_de_Estado_Mejoras_y_Estandares_de_Diseno_PyPrinting3.md) |
| **Arquitectura de Hilos** | Desglose completo de la concurrencia multihilo PyQt6 (`instrumentThread`, `confocalThread`, `cameraThread`) y patrones `QThread`. | [Arquitectura_de_Hilos_y_Concurrencia_PyPrinting3.md](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/reportes/sistema/Arquitectura_de_Hilos_y_Concurrencia_PyPrinting3.md) |
| **Diagnóstico de Señales y Conexiones** | Matriz de señales PyQt6 (`pyqtSignal` / `@pyqtSlot`), mapeo de fotodiodos NI-DAQmx y temporización de triggers. | [Diagnostico_de_Senales_y_Conexiones_PyPrinting3.md](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/reportes/sistema/Diagnostico_de_Senales_y_Conexiones_PyPrinting3.md) |
| **Diagnóstico Integral Comparativo** | Evaluación profunda frente a la versión histórica PyPrinting 2, flujos de trabajo e integridad lógica. | [Diagnostico_Integral_y_Comparativo_PyPrinting3.md](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/reportes/sistema/Diagnostico_Integral_y_Comparativo_PyPrinting3.md) |
| **Reporte de Bugs y Plan de Acción** | Auditoría histórica de correcciones, excepciones resueltas y plan de acción de desarrollo. | [Reporte_de_Bugs_y_Errores_Rutina_Printing_PyPrinting3.md](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/reportes/sistema/Reporte_de_Bugs_y_Errores_Rutina_Printing_PyPrinting3.md) |
| **Matriz de Intercambio de Archivos** | Mapa completo de lectura/escritura de archivos entre programas (`.tiff`, `.npy`, `.csv`, `.txt`, presets, last position). | [Matriz_de_Intercambio_de_Archivos_PyPrinting3.md](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/reportes/sistema/Matriz_de_Intercambio_de_Archivos_PyPrinting3.md) |
| **Evaluación Arquitectónica Graphify** | Respuestas al análisis estático AST de Graphify, desacoplamiento y topología de nodos/comunidades. | [Respuestas_Graphify_y_Evaluacion_Arquitectonica_PyPrinting3.md](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/reportes/sistema/Respuestas_Graphify_y_Evaluacion_Arquitectonica_PyPrinting3.md) |
| **Módulo Cámara Canon EOS 500D** | Arquitectura nativa EDSDK C++/Python, búferes RAM MemoryStream y simulación de exposición EVF. | [Modulo_Camara_Canon_EOS500D_PyPrinting3.md](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/reportes/sistema/Modulo_Camara_Canon_EOS500D_PyPrinting3.md) |

---

## 🔬 2. Reportes Científicos, Físicos y Protocolos Experimentales (`reportes/cientificos/`)

*Útiles para comprender la física subyacente, derivaciones matemáticas, modelos analíticos, metrología de incertidumbre y protocolos paso a paso para laboratorios.*

| Documento / Reporte | Descripción y Enfoque Técnico | Enlace Directo |
|---|---|---|
| **Protocolo de Impresión de Grillas** | Guía paso a paso ("DO PRINTING") para alineación, enfoque, fijado de origen, presets y ejecución de grillas regular y personalizada. | [Protocolo_y_Guia_de_Impresion_de_Grillas_PyPrinting3.md](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/reportes/cientificos/Protocolo_y_Guia_de_Impresion_de_Grillas_PyPrinting3.md) |
| **Diseño de Redes Cristalinas 2D** | Síntesis cristalográfica (15 familias), bases fraccionales $(u, v)$, deslizador de $\gamma$, restricción física $d_{\text{min}}$ y Partícula Ancla $P_0$. | [Diseno_y_Generacion_de_Redes_Cristalinas_2D_PyPrinting3.md](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/reportes/cientificos/Diseno_y_Generacion_de_Redes_Cristalinas_2D_PyPrinting3.md) |
| **Incertidumbre Metrológica ISO/GUM** | Modelo estocástico de propagación de errores, ajuste Gaussiano 2D / Donut LG01 y resolución sub-píxel ($\approx 0.35\ \text{nm}$). | [Incertidumbre_Metrologica_PyPrinting3.md](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/reportes/cientificos/Incertidumbre_Metrologica_PyPrinting3.md) |
| **Algoritmo de Parada Printing y Dímeros** | Formulación matemática detallada de los 5 criterios de parada (Modos 0 a 4) y ensamblado guiado de nanodímeros sub-100 nm. | [Algoritmo_Printing_y_Dimers_PyPrinting3.md](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/reportes/cientificos/Algoritmo_Printing_y_Dimers_PyPrinting3.md) |
| **Corrección de Deriva Termomecánica** | Fundamentación física y algoritmo de compensación $X-Y$ en tiempo real mediante partícula ancla P0 (*Drift Correction*). | [Correccion_de_Deriva_Termomecanica_Drift_Correction_PyPrinting3.md](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/reportes/cientificos/Correccion_de_Deriva_Termomecanica_Drift_Correction_PyPrinting3.md) |
| **Control Adaptativo de Autofoco y Deriva** | Lazo cerrado de modulación de frecuencia de autofoco ($N_{\text{adaptive}}, \tau_{\text{safe}}$) según la velocidad de deriva instantánea $\vec{v}_{\text{drift}}$. | [Control_Adaptativo_de_Frecuencia_de_Autofoco_y_Deriva_PyPrinting3.md](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/reportes/cientificos/Control_Adaptativo_de_Frecuencia_de_Autofoco_y_Deriva_PyPrinting3.md) |
| **Análisis Time-Volt y Tracking Avanzado** | Ajuste cinético no lineal de trazas de fotodiodo ($V_{\text{low}}, V_{\text{high}}, \Delta V, t_{\text{step}}$), latencias y reportes estadísticos. | [Analisis_Time_Volt_y_Tracking_Avanzado_PyPrinting3.md](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/reportes/cientificos/Analisis_Time_Volt_y_Tracking_Avanzado_PyPrinting3.md) |
| **Deconvolución y Trackpy** | Fundamento físico de la Deconvolución Richardson-Lucy en imágenes confocales y seguimiento centroidal con Trackpy. | [Deconvolucion_Richardson_Lucy_y_Trackpy_PyPrinting3.md](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/reportes/cientificos/Deconvolucion_Richardson_Lucy_y_Trackpy_PyPrinting3.md) |

