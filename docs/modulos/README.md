# 📑 Catálogo Canónico de Módulos y Manuales de Operación — PyPrinting 3.0

**Laboratorio de Nanofotónica — Instituto de Nanosistemas (INS-UNSAM / CONICET)**  
**Auditoría de Calidad y Metrología Instrumental** | **Secuencia Canónica:** `MOD-01` al `MOD-15`  
**Ubicación**: [`docs/modulos/README.md`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/docs/modulos/README.md)  
**Manual Maestro Integrador**: [`docs/MANUAL_USUARIO.md`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/docs/MANUAL_USUARIO.md)

---

## 📖 Visión General del Sistema Modular

La carpeta `docs/modulos/` contiene los **manuales de usuario estandarizados, operativos y de instrumentación** para cada uno de los 15 subsistemas que componen la plataforma **PyPrinting 3.0**. 

Cada manual de usuario (`MOD-01` a `MOD-15`) cumple rigurosamente con el estándar de documentación técnica del laboratorio:
1. **🔗 Matriz de Referencias Cruzadas**: Enlaces bidireccionales tipo wiki hacia los reportes de sistema (`SYS-XXX`), reportes científicos (`CAT-XXX`) y manuales de usuario conexos.
2. **🖼️ Maqueta visual ASCII**: Diagramación esquemática de la interfaz de usuario.
3. **🎛️ Catálogo de Controles**: Especificación de botones, sliders, cajas de texto y atajos de teclado.
4. **📥 Archivos de Entrada y 📤 Salida**: Formatos numéricos, columnas físicas, cabeceras comentadas `#` y metadatos JSON.
5. **⚙️ Operatoria Paso a Paso**: Protocolo de ejecución guiada para el investigador o técnico.
6. **⚠️ Tabla de Límites de Validez y Modos de Falla**: Condiciones de borde físicas y computacionales, firma experimental y procedimiento correctivo de laboratorio.

> [!NOTE] Desacoplamiento de Fundamentos Teóricos y Fisicoquímicos
> De acuerdo con la auditoría de control de calidad, los tratados teóricos y electrodinámicos anteriormente presentes en `00_Fundamentos_Fisicos...` fueron desacoplados hacia la biblioteca científica:
> - **Electrodinámica y Fuerzas Ópticas**: `[[CAT-109_Electrodinamica_Fuerzas_Opticas_y_Termoplasmonica_Printing|CAT-109: Electrodinámica, Fuerzas Ópticas y Termoplasmónica]]`
> - **Fisicoquímica de Coloides y Silanización**: `[[CAT-110_Fisicoquimica_Coloides_DLVO_y_Funcionalizacion_Superficies|CAT-110: Fisicoquímica de Coloides, DLVO y Silanización]]`
> La carpeta `docs/modulos/` se reserva exclusivamente para manuales de usuario e instructivos operativos de software y hardware.

---

## 🗂️ Matriz Canónica de Módulos (MOD-01 al MOD-15)

### Bloque A: Adquisición, Nanofabricación y Control Instrumental en Tiempo Real

| Código | Módulo / Archivo Fuente | Descripción Operativa y Funcional | Enlace Canónico |
| :---: |---|---|:---:|
| **MOD-01** | **Microscopio Derecho**<br>[`app.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/app.py) | Suite principal de microscopía confocal: mapeo 2D/3D, trazas fotodiodo 10 kHz, autofoco Z, compensación *Confocal Tilt* en 4 esquinas y orquestación multihilo. | [[MOD-01_Microscopio_Derecho_App\|MOD-01: Microscopio Derecho]] |
| **MOD-02** | **Measurements & Dímeros**<br>[`modules/measurements.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/modules/measurements.py) | Motor de nanofabricación fototérmica: grillas $N \times M$, 5 criterios de parada, *Healing Pass*, corrección de deriva adaptativa sobre $P_0$ y cálculo de ETA. | [[MOD-02_Measurements_Printing_y_Dimeros\|MOD-02: Measurements & Dímeros]] |
| **MOD-03** | **Microscopio Contrapropagante**<br>[`contrapropagante.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/contrapropagante.py) | Excitación óptica dual síncrona TOP/BOT (60x Agua NA=1.0), ajuste Gauss/Donut y cálculo de desalineación vectorial $\mathbf{r}_{\text{TOP}} - \mathbf{r}_{\text{BOT}}$. | [[MOD-03_Microscopio_Contrapropagante\|MOD-03: Contrapropagante]] |
| **MOD-04** | **Cámara Live View EDSDK**<br>[`modules/camera.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/modules/camera.py) | Visión réflex Canon EOS nativa (EDSDK 64-bit), simulación EVF, PiP confocal, calibración micrométrica y tracking SMLM (Picasso/Trackpy). | [[MOD-04_Camara_Live_View_Canon_EDSDK\|MOD-04: Cámara Live View]] |
| **MOD-05** | **Modulación Láser de Potencias**<br>[`Laser532Window`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/app.py) | Control de atenuación analógica AO2 NI-DAQmx ($0-5\ \text{V}$), calibración no lineal mW vs V y disparo coordinado de obturadores TTL. | [[MOD-05_Modulacion_Laser_Potencias\|MOD-05: Modulación Láser]] |

---

### Bloque B: Espectroscopía Óptica y Síntesis Cristalográfica

| Código | Módulo / Archivo Fuente | Descripción Operativa y Funcional | Enlace Canónico |
| :---: |---|---|:---:|
| **MOD-06** | **PySpectrum 3.0**<br>[`pyspectrum.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/pyspectrum.py) | Estación espectroscópica: Andor Shamrock 500i + iXon3 CCD, cosido *Step & Glue*, mapeo hiperespectral 3D $(X,Y,\lambda)$ y calibraciones en hardware. | [[MOD-06_PySpectrum_Espectroscopia_Shamrock\|MOD-06: PySpectrum 3.0]] |
| **MOD-07** | **Diseñador de Redes 2D**<br>[`grid_generator.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/grid_generator.py) | Síntesis analítica de redes cristalinas (15 tipos de red), bases atómicas $(u,v)$, exclusión física $d_{\text{min}}$, partícula ancla $P_0$ y exportación multi-paso. | [[MOD-07_Disenador_Redes_2D_Grid_Generator\|MOD-07: Diseñador de Redes 2D]] |

---

### Bloque C: Análisis Cuantitativo, Diagnóstico, Auditoría y Protocolos

| Código | Módulo / Archivo Fuente | Descripción Operativa y Funcional | Enlace Canónico |
| :---: |---|---|:---:|
| **MOD-08** | **Analizador de Desorden en Redes 2D**<br>[`analysis/lattice_disorder_gui.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/analysis/lattice_disorder_gui.py) | Metrología cristalográfica: SMLM, difracción continua NUFFT 2D, KDTree acotado, residuos cartesianos, $g(r)$, Debye-Waller $(1-p)^2$ y exportación HDF5. | [[MOD-08_Analizador_Desorden_Redes_2D\|MOD-08: Analizador de Desorden 2D]] |
| **MOD-09** | **PSF Analyzer & Óptica de Difracción**<br>[`analysis/psf_analyzer.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/analysis/psf_analyzer.py) | Caracterización de aberraciones: ajuste Levenberg-Marquardt de perfiles Airy, Gauss 2D (7 parámetros) y Donut $LG_{01}$ para alineación confocal. | [[MOD-09_PSF_Analyzer_Optica_Difraccion\|MOD-09: PSF Analyzer]] |
| **MOD-10** | **Analizador de Imágenes y Tracking**<br>[`analysis/image_analyzer.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/analysis/image_analyzer.py) | Procesamiento de micrografías TIFF: Deconvolución Richardson-Lucy en tiempo real acelerada por 2D-FFT, reglas interactivas y conteo sub-píxel. | [[MOD-10_Image_Analyzer_Tracking\|MOD-10: Analizador de Imágenes]] |
| **MOD-11** | **Raman Analyzer Suite**<br>[`raman_analyzer.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/raman_analyzer.py) | Espectroscopía vibracional Raman/SERS: desespicado MAD, sustracción tri-modal de línea base (AsLS/AirPLS/ModPoly), PCA SVD y gráficos 600 DPI. | [[MOD-11_Raman_Analyzer_Suite_Quimiometria\|MOD-11: Raman Analyzer Suite]] |
| **MOD-12** | **Analizador de Espectros SIF**<br>[`sif_analyzer.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/sif_analyzer.py) | Procesador de archivos Andor Solis: corrección de longitud de onda 2D, transmitancia exacta multi-canal (Ruta B sin doble resta) y ajuste Fano/Lorentz. | [[MOD-12_Analizador_SIF_Andor_Solis\|MOD-12: Analizador SIF Solis]] |
| **MOD-13** | **Tablero de Seguridad y Presets**<br>[`modules/hardware_dashboard.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/modules/hardware_dashboard.py) | Telemetría de hardware, aislamiento de dispositivos (*Soft Mock Isolation*), re-escaneo USB y Asistente Guiado `QWizard` de recetas experimentales. | [[MOD-13_Hardware_Dashboard_y_Presets\|MOD-13: Tablero de Seguridad & Presets]] |
| **MOD-14** | **Protocolos Estandarizados (SOP)**<br>Laboratorio INS-UNSAM | Procedimientos Operativos Estandarizados: verificación pre-vuelo, preparación coloidal, montaje microfluídico, impresión paso a paso y apagado. | [[MOD-14_Protocolos_Laboratorio_SOP\|MOD-14: Protocolos de Laboratorio SOP]] |
| **MOD-15** | **PyPrinting 2 Legacy**<br>`PyPrinting_UNSAM.py` | Módulo monolítico histórico: guía de compatibilidad retrospectiva, validación cruzada algorítmica e instrucciones de migración a arquitectura 3.0. | [[MOD-15_PyPrinting2_Legacy_Compatibilidad\|MOD-15: PyPrinting 2 Legacy]] |

---

## 🌐 Enlaces Centrales del Repositorio
- [[MANUAL_USUARIO|📘 Manual de Usuario Integral (docs/MANUAL_USUARIO.md)]]
- [[SYS-001_Estandares_Diseno_Arquitectura_PyPrinting3|🏛️ SYS-001: Estándares de Diseño y Arquitectura PyPrinting 3.0]]
- [[CAT-001_Apendice_Maestro_Compendio_e_Instructivo_Cientifico|🔬 CAT-001: Apéndice Maestro de Reportes Científicos]]
- [📑 Índice General de Reportes (`reportes/README.md`)](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/reportes/README.md)
