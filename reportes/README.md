# Índice General y Base de Conocimiento Científico-Técnica (PyPrinting 3.0) 📑

**Laboratorio de Nanofotónica — Instituto de Nanosistemas (INS-UNSAM / CONICET)**  
**Autor Principal**: José Luis González Peñafiel (*Becario Doctoral CONICET*)  
**Ubicación del Índice**: `reportes/README.md`  
**Última Reestructuración Bibliotecaria**: Septiembre 2026 (Consolidación Q1, Sistema Canónico CAT-XXX y SYS-XXX, Desacoplamiento Modular y Auditoría Integral)

---

## 📖 Estructura Bibliotecaria de la Documentación

En concordancia con el **Estándar 5 de Diseño (Conservación de la Información, Valor del Conocimiento Generado y Autosuficiencia Pedagógica)**, todo el acervo documental del proyecto **PyPrinting 3.0** y **PySpectrum 3.0** se encuentra rigurosamente clasificado en dos bibliotecas canónicas interconectadas:

```
reportes/
├── ⚙️ sistema/          # Biblioteca de Sistema, Hardware e Ingeniería (22 documentos, SYS-001 a SYS-403)
│   ├── [Cluster SYS-000] Arquitectura Rectoral y Gobernanza de Software (SYS-001 y SYS-002)
│   ├── [Cluster SYS-100] Concurrencia, Señales y Cinemática de Hardware (SYS-101 a SYS-106)
│   ├── [Cluster SYS-200] Instrumentación Óptica, Actuadores y Seguridad Hardware (SYS-201 a SYS-204)
│   ├── [Cluster SYS-300] Espectrometría, Bancos Ópticos y Procesamiento Instrumental (SYS-301 a SYS-306)
│   └── [Cluster SYS-400] Auditorías de Código, Verificación y Diagnóstico Integral (SYS-401 a SYS-403)
└── 🔬 cientificos/       # Biblioteca Científica, Cristalografía 2D, Óptica y Modelos Analíticos (46 documentos)
    ├── 📘 CAT-001 [MET] Documento Rector, Compendio Metrológico e Instructivo Maestro
    ├── [Pilar I]   Nanofabricación Óptica, Control de Posición y Termoplasmónica (CAT-101 a CAT-113)
    ├── [Pilar II]  Super-Resolución Óptica, Detección Sub-píxel y Espectrometría (CAT-201 a CAT-205)
    ├── [Pilar III] Cristalografía 2D, Espacio Recíproco y Metrología de Desorden (CAT-301 a CAT-312)
    └── [Pilar IV]  Arquitectura de Datos, Serialización y Ecosistema FAIR (CAT-401 a CAT-402)
```

---

## 📘 Documento Rector del Sistema Bibliotecario

> [!IMPORTANT]
> Para consultar el **Glosario Canónico Unificado**, el **Grafo de Interconexión Metrológica** y la **Guía Oficial para Redactar e Integrar Nuevas Notas Científicas**, consulte el documento rector:  
> 👉 **[[CAT-001_Apendice_Maestro_Compendio_e_Instructivo_Cientifico]]** ([Ver archivo](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/reportes/cientificos/CAT-001_Apendice_Maestro_Compendio_e_Instructivo_Cientifico.md))

---

## 🔬 1. Biblioteca de Conocimiento Científico (`reportes/cientificos/`)

Esta vertiente compendia las deducciones formales desde primeros principios, cotas fundamentales de incertidumbre cuántica/óptica, fenomenología experimental y formulación matemática analítica.

### 🏛️ Pilar I: Nanofabricación Óptica, Control de Posición y Estabilidad Optomecánica

| Signatura | Eje | Documento / Reporte | Enfoque Físico-Matemático y Metrología | Enlace Directo |
|:---:|:---:|---|---|---|
| `CAT-100` | `[FIS]` | **Marco Unificado de Nanofabricación Óptica y Termoplasmónica** | Tratado Rector: Cadena causal multifísica, DLVO, convección de Marangoni y lazo cerrado. | [[CAT-100_Marco_Unificado_Nanofabricacion_Optica_y_Termoplasmonica]] |
| `CAT-101` | `[PRT]` | **Protocolo Operativo de Impresión de Grillas** | Protocolo experimental "DO PRINTING", alineación óptica, calibración de potencias y recetas. | [[CAT-101_Protocolo_Operativo_Impresion_Fototermica_Grillas_2D]] |
| `CAT-102` | `[MAT]` | **Síntesis Cristalográfica de Redes 2D y Ancla $P_0$** | Formalización matemática de las 15 familias 2D, coordenadas $(u,v)$, parámetro $\gamma$ y exclusión $d_{\text{min}}$. | [[CAT-102_Sintesis_Cristalografica_Redes_2D_y_Particula_Ancla]] |
| `CAT-103` | `[FIS]` | **Control en Lazo Cerrado y Síntesis de Dímeros** | Ecuaciones de parada en lazo cerrado (Modos 0-4), filtro $N_{\text{hold}}$ y nanodímeros plasmónicos. | [[CAT-103_Control_Lazo_Cerrado_Fototermico_y_Sintesis_Dimeros]] |
| `CAT-104` | `[FIS]` | **Compensación de Inclinación Z y Healing Pass** | Geometría 3D de inclinación $Z(x,y)$, rango de Rayleigh y pasada de autocompletitud *Healing Pass*. | [[CAT-104_Compensacion_Inclinacion_Z_Confocal_y_Healing_Pass]] |
| `CAT-105` | `[FIS]` | **Compensación de Deriva Térmica con Ancla $P_0$** | Fundamento físico del anclaje $P_0$, cálculo de deriva $\vec{D}(t)$ y corrección piezoeléctrica activa. | [[CAT-105_Compensacion_Deriva_Termomecanica_Particula_Ancla_P0]] |
| `CAT-106` | `[CMP]` | **Control Adaptativo de Frecuencia de Autofoco** | Modulación adaptativa del lazo cerrado de autofoco en función del gradiente $\|\vec{v}_{\text{drift}}\|$. | [[CAT-106_Control_Adaptativo_Frecuencia_Autofoco_Gradiente_Deriva]] |
| `CAT-107` | `[FIS]` | **Cinética de Captura por Fotodiodo Time-Volt** | Modelado no lineal de trazas de fotodiodo, ajuste sigmoidal cuádruple y latencias de obturador. | [[CAT-107_Cinetica_Captura_Fotodiodo_Time_Volt_Filtro_Nhold]] |
| `CAT-108` | `[FIS]` | **Teoría Óptica del Telescopio Relé 4f e iSCAT** | Matriz relé 4f ($\Gamma = 1.25\times$), difracción Abbe/Rayleigh, $AU$ en pinholes ($50/100\,\mu\text{m}$), Nyquist, acoplamiento $f/\#$, iSCAT ($d^3$ vs $d^6$) y PSFs. | [[CAT-108_Teoria_Optica_Telescopio_Rele_4f_y_Canales_Confocales]] |
| `CAT-109` | `[FIS]` | **Electrodinámica, Fuerzas Ópticas y Termoplasmónica** | Sección eficaz de extinción Mie/Rayleigh, fuerzas de gradiente y dispersión, disipación Joule fototérmica y cavitación. | [[CAT-109_Electrodinamica_Fuerzas_Opticas_y_Termoplasmonica_Printing]] |
| `CAT-110` | `[FIS]` | **Fisicoquímica de Coloides, Potencial DLVO y Silanización** | Teoría DLVO, potencial zeta, funcionalización con APTES ($-\text{NH}_3^+$), química Piranha y cinética de adhesión irreversible. | [[CAT-110_Fisicoquimica_Coloides_DLVO_y_Funcionalizacion_Superficies]] |
| `CAT-111` | `[FIS]` | **Nanotermometría por Variaciones DLS y Fluctuaciones Brownianas** | Fluctuaciones brownianas locales $D(T) = \frac{k_B T}{6\pi\eta(T)R_h}$, modelo VFT del agua e inversión de temperatura local $T_{\text{nano}}$. | [[CAT-111_Nanotermometria_DLS_y_Dinamica_Fluctuaciones_Brownianas]] |
| `CAT-112` | `[FIS]` | **Teoría de Lente Térmica Fototérmica y Convección de Marangoni** | Gradiente termo-óptico $\nabla n = (dn/dT)\nabla T$, señal pinhole $\Delta I/I_0 \approx 2\theta$, convección termocapilar $\mathbf{\tau}_M = -\beta_T \nabla_\parallel T$. | [[CAT-112_Teoria_Lente_Termica_Gradientes_Indice_y_Marangoni]] |
| `CAT-113` | `[CMP]` | **Lazo Cerrado Metrológico In-Situ y Control Predictivo** | Control predictivo RLS con factor de olvido, compensación feedforward $\mathbf{r}_{\text{cmd}} = \hat{\mathbf{A}}^{-1}(\mathbf{r}_{\text{ideal}} - \hat{\mathbf{b}})$, reducción RMS $< 4\ \text{nm}$. | [[CAT-113_Lazo_Cerrado_Metrologico_InSitu_y_Control_Predictivo]] |
| `CAT-114` | `[FIS]` | **Pinzas Ópticas Contrapropagantes y Microscopía iSCAT** | Anulación axial de fuerzas de dispersión, trampas de onda estacionaria y microscopía iSCAT ($d^3$). | [[CAT-114_Pinzas_Opticas_Contrapropagantes_y_Microscopia_iSCAT]] |

---

### 🔬 Pilar II: Super-Resolución Óptica, Detección Sub-píxel y Espectrometría

| Signatura | Eje | Documento / Reporte | Enfoque Físico-Matemático y Metrología | Enlace Directo |
|:---:|:---:|---|---|---|
| `CAT-200` | `[FIS]` | **Fundamentos de Microscopía Óptica Avanzada y Super-Resolución** | Tratado Rector: Límites de difracción (Abbe/Rayleigh), confocal, SMLM y cota CRLB. | [[CAT-200_Fundamentos_Microscopia_Optica_Avanzada_y_Super_Resolucion]] |
| `CAT-250` | `[FIS]` | **Marco Unificado de Espectroscopía Óptica, SERS y Quimiometría** | Tratado Rector: Dispersión Raman, resonancias SERS/SLR, AsLS/AirPLS y desmezclado MCR-ALS. | [[CAT-250_Marco_Unificado_Espectroscopia_Optica_SERS_y_Quimiometria]] |
| `CAT-201` | `[CMP]` | **Deconvolución Óptica y Tracking Trackpy** | Restauración por máxima verosimilitud (Richardson-Lucy Poissoniano) y localización centroidal sub-píxel. | [[CAT-201_Deconvolucion_Optica_Richardson_Lucy_y_Tracking_Trackpy]] |
| `CAT-202` | `[MAT]` | **Derivación Matemática de la Cota Cramér-Rao** | Deducción analítica de matrices de Fisher, cota CRLB para perfiles Gaussiano y Donut $LG_{01}$, y varianza $\Delta x^2/12$. | [[CAT-202_Derivacion_Matematica_Cota_Cramer_Rao_Localizacion_Optica]] |
| `CAT-203` | `[FIS]` | **Presupuesto de Incertidumbre Metrológica ISO/GUM** | Balances de incertidumbre experimental Tipo A/B, cadena de 5 objetivos, pinholes super-confocales ($0.46\,AU$) y $u_c = 6.55\,\text{nm}$. | [[CAT-203_Presupuesto_Incertidumbre_Metrologica_ISOGUM_Microscopia]] |
| `CAT-204` | `[CMP]` | **Curación Fotométrica y Desacople Multi-Gaussiano** | Huella monomérica $(V_0, A_0, \sigma_{\text{psf}})$, ajuste Levenberg-Marquardt y verificación húngara ($M + n_{\text{vac}} \le N_{\text{total}}$). | [[CAT-204_Curacion_Fotometrica_Desacople_MultiGaussiano_Consistencia]] |
| `CAT-205` | `[FIS]` | **Mapeo Hiperespectral SERS Confocal Automatizado** | Factor de realce de campo cercano $EF \approx |E_{\text{loc}}/E_0|^4$, trayectoria meandro TSP, hipercubo 3D $\mathcal{H}(X,Y,\lambda)$ y desmezclado MCR-ALS. | [[CAT-205_Mapeo_Hiperespectral_SERS_Confocal_Automatizado]] |
| `CAT-206` | `[CMP]` | **Pipeline SMLM: Picasso vs Trackpy+RL y Ruido Poisson** | Estimación MLE Poisson de Picasso vs Trackpy+RL, ruptura de independencia estadística y cota CRLB. | [[CAT-206_Pipeline_SMLM_Picasso_Algoritmos_y_Deconvolucion]] |
| `CAT-207` | `[CMP]` | **Quimiometría Espectral, AsLS y Perfiles Voigt/BWF** | Corrección de línea de base AsLS/AirPLS, perfiles Pseudo-Voigt/BWF y termometría Anti-Stokes/Stokes. | [[CAT-207_Quimiometria_Procesamiento_Espectral_AsLS_Voigt_Calibracion]] |
| `CAT-208` | `[FIS]` | **Electrodinámica de Nanocavidades Plasmónicas y SLR** | Hot-spots en nanogaps sub-5 nm, resonancias de red superficial SLR y factor de realce $|E/E_0|^4$. | [[CAT-208_Electrodinamica_Nanocavidades_Plasmicas_SLR_y_SERS]] |
| `CAT-209` | `[CMP]` | **Morfología Matemática, Watershed y Fotometría Apertura** | Cruce por cero LoG ($r_0=\sqrt{2}\sigma$), Watershed con marcadores, inclusión `pointPolygonTest` y fondo perimetral. | [[CAT-209_Morfologia_Matematica_Watershed_y_Fotometria_Apertura]] |

---

### 🌐 Pilar III: Cristalografía 2D, Espacio Recíproco y Metrología de Desorden

| Signatura | Eje | Documento / Reporte | Enfoque Físico-Matemático y Metrología | Enlace Directo |
|:---:|:---:|---|---|---|
| `CAT-300` | `[MAT]` | **Fundamentos de Cristalografía Bidimensional y Redes de Bravais** | Tratado Rector: 5 redes planas de Bravais, Teorema de Mermin-Wagner y dualidad Tipo I vs II. | [[CAT-300_Fundamentos_Cristalografia_Bidimensional_y_Fisica_Desorden_2D]] |
| `CAT-301` | `[CMP]` | **Algoritmos en Espacio Real: KDTree y Monte Carlo** | Bounded KDTree ($r_{\text{cut}} = a/2$), eliminación del sesgo histórico del $35\%$, asignación Húngara y ensamble estocástico. | [[CAT-301_Algoritmos_Espacio_Real_KDTree_Asignacion_Monte_Carlo]] |
| `CAT-302` | `[FIS]` | **Caracterización Física de Defectos en Redes SMLM** | Física de vacancias, pares 5-7 de Voronoi, parámetros de orden orientacional $\psi_4, \psi_6$ e impacto en modos plasmónicos SLR. | [[CAT-302_Caracterizacion_Fisica_Desorden_Defectos_Redes_SMLM]] |
| `CAT-303` | `[MAT]` | **Derivación Matemática de la Función Radial $g(r)$** | Prueba analítica de $\sigma_{\text{rdf}} = \sigma_{\text{peak}}/\sqrt{2}$ (error del $+41.4\%$ por omisión), cuadratura 2D y corrección de Green. | [[CAT-303_Derivacion_Matematica_Distribucion_Radial_gr_Correccion_Borde]] |
| `CAT-304` | `[FIS]` | **Metrología Experimental de Conchas $g(r)$** | Corte de difracción confocal ($r < 250\,\text{nm}$), ventana sub-red de satélites/dímeros, e invariancia cinemática ante rotación. | [[CAT-304_Metrologia_Experimental_Conchas_Coordinacion_gr_Redes_2D]] |
| `CAT-305` | `[MAT]` | **Derivación del Factor de Estructura y Debye-Waller** | Modelo estocástico de Bernoulli, atenuación coherente $(1-p)^2 \cdot e^{-q^2 \sigma_{\text{pos}}^2}$, meseta difusa y Gráfico de Wilson 2D. | [[CAT-305_Derivacion_Matematica_Factor_Estructura_Debye_Waller]] |
| `CAT-306` | `[FIS]` | **Metrología Óptica de Difracción de Bragg y Perfiles** | Anatomía del plano BFP, descomposición de cortes radiales $\Delta q_\parallel$ (coherencia $\xi$) y transversales $\Delta q_\perp$ (mosaico $\Delta \theta$). | [[CAT-306_Metrologia_Optica_Difraccion_Bragg_y_Perfiles_Redes_2D]] |
| `CAT-307` | `[CMP]` | **Computación NUFFT 2D y Optimización BLAS** | Formulación tensorial continua Tipo 1 $M = E_y E_x^T$, spreading matricial BLAS-3 y aceleración $\mathcal{O}(M\log M)$ en milisegundos. | [[CAT-307_Computacion_NUFFT_Factor_Estructura_Optimizacion_BLAS]] |
| `CAT-308` | `[MAT]` | **Metrología Analítica Directa de Picos de Bragg 2D** | Inversión analítica exacta $\sigma_{\text{pos}} = \frac{a}{2\pi\sqrt{3}}\sqrt{\ln(H_1/H_2)}$ sin calibración Monte Carlo, Gráfico de Wilson y SNR. | [[CAT-308_Metrologia_Analitica_Directa_Picos_Bragg_Fourier_2D]] |
| `CAT-309` | `[FIS]` | **Teoría del Paracristal de Hosemann y Pérdida de Orden** | Discriminación espectral Tipo I (Debye-Waller) vs Tipo II (Paracristal), cociente de Hosemann $\eta_H \approx 4.0$ y longitud $\xi$. | [[CAT-309_Teoria_Paracristal_Hosemann_Perdida_Orden_2D]] |
| `CAT-310` | `[MAT]` | **Deducción Matemática del Paracristal 2D Anisótropo** | Factor analítico cerrado $S(\mathbf{q}) = \text{Re}\{\frac{1+\mathbf{\Phi}_{10}}{1-\mathbf{\Phi}_{10}}\}\text{Re}\{\frac{1+\mathbf{\Phi}_{01}}{1-\mathbf{\Phi}_{01}}\}$ y función de verosimilitud exacta. | [[CAT-310_Derivacion_Matematica_Paracristal_2D_Hosemann_Anisotropo]] |
| `CAT-311` | `[CMP]` | **Inferencia Bayesiana y MCMC para Paracristal 2D** | Parametrización de Cholesky $\mathbf{\Sigma} = \mathbf{L}\mathbf{L}^T$, muestreo ensemble `emcee`, corner plots y desacople anisotrópico. | [[CAT-311_Inferencia_Bayesiana_MCMC_Desorden_Paracristal]] |
| `CAT-312` | `[CMP]` | **Aceleración Tensorial GPU/CUDA para NUFFT 2D y SMLM** | Kernel de spreading en memoria compartida GPU, cuFFT 2D batched $<12\ \text{ms}$ a $>60\ \text{fps}$ y fallback automático a BLAS CPU. | [[CAT-312_Computacion_Tensorial_GPU_CUDA_NUFFT_y_Deconvolucion]] |
| `CAT-313` | `[FIS]` | **Transiciones de Fase 2D, Teoría KTHNY y Orden $\psi_n$** | Fusión KTHNY en 2D, disociación de dipolos 5-7, fase hexática y parámetros de orden $\psi_4, \psi_6, \psi_3$. | [[CAT-313_Transiciones_Fase_2D_Teoria_KTHNY_y_Orden_Orientacional]] |
| `CAT-314` | `[MAT]` | **Cristalografía Computacional 2D y Fronteras Poligonales** | Álgebra tensorial de redes, bases honeycomb $(1/3, 1/3)$, polígonos por Winding Number y filtro $d_{\text{min}}$. | [[CAT-314_Cristalografia_Computacional_2D_Bases_Poliatomicas_y_Fronteras]] |
| `CAT-315` | `[FIS]` | **Espacio Recíproco de Redes Hexagonales y Honeycomb** | Factor de estructura diatómico, interferencia constructiva/destructiva, vacancias $A/B$, tensor $\mathbf{\Sigma}_{\text{pos}}$ y metrología. | [[CAT-315_Espacio_Reciproco_Redes_Hexagonales_Honeycomb_y_Factor_Estructura]] |


---

### 💾 Pilar IV: Arquitectura de Datos, Serialización y Ecosistema de Software

| Signatura | Eje | Documento / Reporte | Enfoque Físico-Matemático y Metrología | Enlace Directo |
|:---:|:---:|---|---|---|
| `CAT-400` | `[CMP]` | **Gobernanza de Datos Científicos, Trazabilidad y Principios FAIR** | Tratado Rector: Principios FAIR, jerarquía HDF5/NeXus, procedencia SHA-256 y metrología gráfica. | [[CAT-400_Gobernanza_Datos_Cientificos_Metrologia_y_Ecosistema_FAIR]] |
| `CAT-401` | `[CMP]` | **Estándar de Serialización Jerárquica HDF5 (.h5)** | Esquema jerárquico de grupos (`/raw`, `/curated`, `/reciprocal`), compresión sin pérdidas `shuffle+gzip` y preservación metrológica. | [[CAT-401_Estandar_Serializacion_Jerarquica_Contenedor_HDF5]] |
| `CAT-402` | `[CMP]` | **Estandarización NeXus / HDF5 y Principios FAIR** | Ontología formal `NXdata`, `NXsample`, `NXinstrument`, trazabilidad criptográfica SHA-256 e interoperabilidad para repositorios abiertos. | [[CAT-402_Estandar_Datos_FAIR_y_Serializacion_NeXus_HDF5]] |
| `CAT-403` | `[MET]` | **Estándares de Visualización Científica y Gráficos Vectoriales** | Principios de Edward Tufte, colormaps Cividis/Viridis accesibles, SVG editable `<text>` y PDF Type 42. | [[CAT-403_Estandares_Visualizacion_Cientifica_y_Graficos_Vectoriales]] |

---

## ⚙️ 2. Biblioteca de Sistema, Hardware e Instrumentación (`reportes/sistema/`)

Esta vertiente documenta la ingeniería de software, arquitectura de hilos, gestión de memoria, integración de hardware NI-DAQmx, drivers de comunicación serie, protocolos de calibración instrumental y auditorías de código.

### 🏛️ Cluster SYS-000: Arquitectura Rectoral y Gobernanza de Software

| Signatura | Eje | Documento / Reporte Técnico | Enfoque de Ingeniería y Hardware | Enlace Directo |
|:---:|:---:|---|---|---|
| `SYS-001` | `[EST]` | **Estándares de Diseño y Arquitectura PyPrinting 3.0** | Documento rector de software: los 5 estándares de diseño obligatorios, métricas Graphify (5,532 nodos) y estado modular. | [[SYS-001_Estandares_Diseno_Arquitectura_PyPrinting3]] |
| `SYS-002` | `[ARQ]` | **Evaluación Arquitectónica AST y Métricas Graphify** | Análisis estático de código (AST), centralidad de intermediación de módulos C++/Python y desacoplamiento de clases. | [[SYS-002_Evaluacion_Arquitectonica_AST_y_Metricas_Graphify]] |

---

### 🧵 Cluster SYS-100: Concurrencia, Señales y Cinemática de Hardware

| Signatura | Eje | Documento / Reporte Técnico | Enfoque de Ingeniería y Hardware | Enlace Directo |
|:---:|:---:|---|---|---|
| `SYS-101` | `[ARQ]` | **Arquitectura de Hilos, Concurrencia y QThread** | Desglose multihilo en PyQt6 (`instrumentThread`, `confocalThread`, `cameraThread`), colas asíncronas y prevención de deadlocks. | [[SYS-101_Arquitectura_Hilos_Concurrencia_QThread]] |
| `SYS-102` | `[INS]` | **Mapeo de Señales/Slots PyQt6 y Temporización DAQmx** | Matriz de señales y slots, temporización de muestreo analógico/digital en NI-DAQmx y eliminación de bucles de señal. | [[SYS-102_Senales_Slots_PyQt6_y_Temporizacion_DAQmx]] |
| `SYS-103` | `[ARQ]` | **Regímenes de Coordenadas e Invariancia Cinemática** | Arquitectura reactiva tri-régimen (`Legacy`, `Laser Ref`, `Sample Ref`), diccionario canónico e invariancia sobre platina PI E-517. | [[SYS-103_Regimenes_Coordenadas_e_Invariancia_Cinematica]] |
| `SYS-104` | `[DAT]` | **Matriz de Intercambio de Archivos y Formatos I/O** | Mapa exhaustivo de lectura/escritura (.tiff, .npy, .csv, .json, .sif, presets, last_position) y compatibilidad hacia atrás. | [[SYS-104_Matriz_Intercambio_Archivos_y_Formatos_IO]] |
| `SYS-105` | `[DAT]` | **Pipeline Unificado de Localización Super-Resolución (SMLM)** | Arquitectura de `core/localization_pipeline.py`, integración GaussMLE/Trackpy, desconvolución Richardson-Lucy y reescalado uint16. | [[SYS-105_Pipeline_Unificado_Localizacion_Super_Resolucion]] |
| `SYS-106` | `[ARQ]` | **Extensión a Procesamiento GPU y Descongestión de Hilos** | Aceleración en GPU (Fase 2) para NUFFT 2D, Monte Carlo Debye-Waller, AsLS hiperespectral y ajustes PSF, con perspectivas de OpenGL (Fase 1.2) y Numba JIT (Fase 1.3). | [[SYS-106_Extension_Procesamiento_GPU_Operaciones_Matematicas_y_Descongestion_Hilos]] |

---

### 🛡️ Cluster SYS-200: Instrumentación Óptica, Actuadores y Seguridad Hardware

| Signatura | Eje | Documento / Reporte Técnico | Enfoque de Ingeniería y Hardware | Enlace Directo |
|:---:|:---:|---|---|---|
| `SYS-201` | `[SEG]` | **Seguridad Óptica Activa, Watchdog y Obturadores** | Fail-safe activo con latido (*heartbeat*), conmutación de obturadores en NI-DAQmx (`line0:3`), interlocks y parada de emergencia. | [[SYS-201_Seguridad_Optica_Watchdog_y_Obturadores]] |
| `SYS-202` | `[INS]` | **Actuación de Flipper de Potencia y Ciclo DAQmx** | Ciclo de vida de tareas en NI-DAQmx C-API, generación de pulsos de 5V, supresión de tareas zombi y cleanup de hardware. | [[SYS-202_Actuacion_Flipper_y_Ciclo_Vida_DAQmx]] |
| `SYS-203` | `[INS]` | **Control de Fuentes Láser, Protocolos RS-232/SCPI** | Comunicación serie y USB-VCP con láseres Spectra-Physics Excelsior, Coherent OBIS y MPBC, control analógico y modulación. | [[SYS-203_Control_Comunicaciones_Laseres_RS232_SCPI]] |
| `SYS-204` | `[INS]` | **Controlador Canon EDSDK, Simulación EVF y RAM** | Wrapper ctypes para Canon EDSDK 13.20, modo EVF sin ruido de ganancia, descarga en memoria RAM y Picture-in-Picture (PiP). | [[SYS-204_Modulo_Camara_Canon_EDSDK_y_Buffer_RAM]] |

---

### 🌈 Cluster SYS-300: Espectrometría, Bancos Ópticos y Procesamiento Instrumental

| Signatura | Eje | Documento / Reporte Técnico | Enfoque de Ingeniería y Hardware | Enlace Directo |
|:---:|:---:|---|---|---|
| `SYS-301` | `[INS]` | **Hardware Espectrógrafo Shamrock 500i y Cámara iXon3** | Arquitectura Czerny-Turner, motorización de rendija, torreta de redes (150 y 1200 l/mm), DLLs C y refrigeración Peltier a $-70^\circ\text{C}$. | [[SYS-301_Sistema_Espectrometro_Shamrock500i_iXon3]] |
| `SYS-302` | `[CAL]` | **Calibración Espectral Shamrock y Flippers Reactivos** | Ajuste Gaussiano sub-píxel de rendija en orden cero ($m=0$), offsets Shamrock SDK, reactividad flipper Qt y *Step & Glue*. | [[SYS-302_Calibracion_Espectral_y_Sincronizacion_Flippers]] |
| `SYS-303` | `[PRT]` | **Protocolo Metrológico de Calibración de Espectrógrafo** | Protocolo SOP multi-fase (0 a 6): lámparas Ne/Ar, fonón de silicio Si-100 a $520.50\,\text{cm}^{-1}$, corrección radiométrica NIST y archivo persistente. | [[SYS-303_Protocolo_Metrologico_Calibracion_Espectrometro]] |
| `SYS-304` | `[DAT]` | **Arquitectura Analizador SIF, Filtros 2D y Ergonomía** | Ingeniería inversa del formato binario `.sif` de Andor Solis, pipeline de filtrado en cascada 2D $\to$ 1D, noise gate y toolbars compactas. | [[SYS-304_Arquitectura_Analizador_SIF_y_Filtros_Cascada]] |
| `SYS-305` | `[INS]` | **Arquitectura Optomecánica del Microscopio y Ruteo** | Trazado físico del banco, torreta de 5 objetivos, conmutador flipper hacia Shamrock/confocal, líneas DAQmx (`ai0:2`, `line0:3`) y matriz para 10 experimentos. | [[SYS-305_Arquitectura_Optomecanica_Microscopio_Derecho_y_Ruteo_Espectral]] |
| `SYS-306` | `[DAT]` | **Arquitectura del Motor Raman y Quimiometría Multiespectral** | Arquitectura de `core/raman_engine.py` y `analysis/multi_spectrum_widget.py`, desespicado MAD, AsLS/AirPLS/ModPoly y PCA SVD. | [[SYS-306_Arquitectura_Motor_Raman_y_Quimiometria_Multiespectral]] |

---

### ⚖️ Cluster SYS-400: Auditorías de Código, Verificación y Diagnóstico Integral

| Signatura | Eje | Documento / Reporte Técnico | Enfoque de Ingeniería y Hardware | Enlace Directo |
|:---:|:---:|---|---|---|
| `SYS-401` | `[AUD]` | **Auditoría Comparativa: PyPrinting 2 vs PyPrinting 3** | Diagnóstico exhaustivo de paridad funcional, migración a PyQt6, benchmarking de latencias de hardware y reducción de deuda técnica. | [[SYS-401_Auditoria_Comparativa_PyPrinting_v2_vs_v3]] |
| `SYS-402` | `[AUD]` | **Auditoría Comparativa: Andor Solis vs PySpectrum 3.0** | Auditoría feature-by-feature frente a la suite propietaria Andor Solis, ventajas de calibración abierta, velocidad de adquisición y roadmap. | [[SYS-402_Auditoria_Comparativa_Andor_Solis_vs_PySpectrum]] |
| `SYS-403` | `[AUD]` | **Registro de Incidencias Críticas y Debugging de Printing** | Matriz de excepciones históricas en impresión óptica, análisis de causa raíz (RCA), resolución de carreras piezoeléctricas y tests. | [[SYS-403_Registro_Bugs_Causa_Raiz_Rutina_Printing]] |

---

## 🔗 3. Matriz de Interconexión Software $\leftrightarrow$ Física

La siguiente matriz conecta los módulos y reportes del sistema con los fundamentos teóricos y metrológicos que los sustentan:

| Componente / Módulo de Software | Reporte de Sistema (`SYS-XXX`) | Fundamento Científico Vinculado (`CAT-XXX`) | Principio Físico o Algorítmico Implementado |
|---|:---:|:---:|---|
| **`core/shutters.py` / `core/nidaq.py`** | `[[SYS-201_Seguridad_Optica_Watchdog_y_Obturadores]]` | `[[CAT-107_Cinetica_Captura_Fotodiodo_Time_Volt_Filtro_Nhold]]` | Tiempos de apertura mecánica del obturador y latencias analógicas de corte. |
| **`modules/measurements.py`** | `[[SYS-101_Arquitectura_Hilos_Concurrencia_QThread]]` | `[[CAT-103_Control_Lazo_Cerrado_Fototermico_y_Sintesis_Dimeros]]` | Criterio de parada por fotodiodo y control en lazo cerrado para dímeros plasmónicos. |
| **`core/nanopositioning.py`** | `[[SYS-103_Regimenes_Coordenadas_e_Invariancia_Cinematica]]` | `[[CAT-102_Sintesis_Cristalografica_Redes_2D_y_Particula_Ancla]]`<br>`[[CAT-105_Compensacion_Deriva_Termomecanica_Particula_Ancla_P0]]` | Geometría 2D de redes, parámetro $\gamma$ y corrección sustractiva de deriva térmica con $P_0$. |
| **`modules/focus.py`** | `[[SYS-102_Senales_Slots_PyQt6_y_Temporizacion_DAQmx]]` | `[[CAT-106_Control_Adaptativo_Frecuencia_Autofoco_Gradiente_Deriva]]` | Frecuencia de muestreo adaptativa en lazo cerrado según $\|\vec{v}_{\text{drift}}\|$. |
| **`modules/confocal.py`** | `[[SYS-305_Arquitectura_Optomecanica_Microscopio_Derecho_y_Ruteo_Espectral]]` | `[[CAT-104_Compensacion_Inclinacion_Z_Confocal_y_Healing_Pass]]`<br>`[[CAT-108_Teoria_Optica_Telescopio_Rele_4f_y_Canales_Confocales]]` | Compensación planar $Z(x,y)$, filtrado espacial super-confocal ($0.46\,AU$) y física iSCAT. |
| **`modules/camera.py` / `core/canon_edsdk.py`** | `[[SYS-204_Modulo_Camara_Canon_EDSDK_y_Buffer_RAM]]` | `[[CAT-108_Teoria_Optica_Telescopio_Rele_4f_y_Canales_Confocales]]`<br>`[[CAT-203_Presupuesto_Incertidumbre_Metrologica_ISOGUM_Microscopia]]` | Muestreo de Nyquist ($>2.9\times$), escala de píxel proyectado ($45.1\,\text{nm/px}$) y balance ISO/GUM. |
| **`psf_analyzer.py`** | `[[SYS-104_Matriz_Intercambio_Archivos_y_Formatos_IO]]` | `[[CAT-108_Teoria_Optica_Telescopio_Rele_4f_y_Canales_Confocales]]`<br>`[[CAT-202_Derivacion_Matematica_Cota_Cramer_Rao_Localizacion_Optica]]` | Ajuste Gaussiano 2D anisótropo y perfil Laguerre-Gauss $LG_{01}$ (Donut). |
| **`pyspectrum/docks/calibration_dock.py`** | `[[SYS-302_Calibracion_Espectral_y_Sincronizacion_Flippers]]`<br>`[[SYS-303_Protocolo_Metrologico_Calibracion_Espectrometro]]` | `[[CAT-108_Teoria_Optica_Telescopio_Rele_4f_y_Canales_Confocales]]` | Acoplamiento $f/9.7$ libre de viñeteo y ajuste gaussiano del centroide en orden cero ($m=0$). |
| **`sif_analyzer.py` / `core/sif_processor.py`** | `[[SYS-304_Arquitectura_Analizador_SIF_y_Filtros_Cascada]]` | `[[CAT-401_Estandar_Serializacion_Jerarquica_Contenedor_HDF5]]` | Procesamiento 2D $\to$ 1D en cascada y exportación en formatos estructurados. |
| **`analysis/lattice_disorder_gui.py`** | `[[SYS-104_Matriz_Intercambio_Archivos_y_Formatos_IO]]` | `[[CAT-301_Algoritmos_Espacio_Real_KDTree_Asignacion_Monte_Carlo]]` a `[[CAT-309_Teoria_Paracristal_Hosemann_Perdida_Orden_2D]]` | Cuantificación completa de desorden cristalográfico 2D en espacio real ($g(r)$) y recíproco ($S(\mathbf{q})$). |
| **`core/localization_pipeline.py`** | `[[SYS-105_Pipeline_Unificado_Localizacion_Super_Resolucion]]` | `[[CAT-201_Deconvolucion_Optica_Richardson_Lucy_y_Tracking_Trackpy]]`<br>`[[CAT-202_Derivacion_Matematica_Cota_Cramer_Rao_Localizacion_Optica]]` | Pipeline unificado de super-resolución SMLM (GaussMLE / Trackpy) y deconvolución RL. |
| **`core/raman_engine.py` / `MultiSpectrumWidget`** | `[[SYS-306_Arquitectura_Motor_Raman_y_Quimiometria_Multiespectral]]` | `[[CAT-203_Presupuesto_Incertidumbre_Metrologica_ISOGUM_Microscopia]]` | Quimiometría Raman multiespectral, sustracción adaptativa de línea base y PCA por SVD. |
| **`core/accelerators.py`** | `[[SYS-106_Extension_Procesamiento_GPU_Operaciones_Matematicas_y_Descongestion_Hilos|SYS-106]]` | `[[CAT-301_Factor_Estructura_Estatico_y_NUFFT_2D]]`<br>`[[CAT-207_Quimiometria_Procesamiento_Espectral_AsLS_Voigt_Calibracion]]` | Despachador híbrido CPU/GPU, NUFFT 2D masiva, Monte Carlo y AsLS pentadiagonal por lotes. |
| **Preparación de Muestra & Termoplasmónica** | `[[SYS-101_Arquitectura_Hilos_Concurrencia_QThread]]` | `[[CAT-109_Electrodinamica_Fuerzas_Opticas_y_Termoplasmonica_Printing]]`<br>`[[CAT-110_Fisicoquimica_Coloides_DLVO_y_Funcionalizacion_Superficies]]` | Fuerzas ópticas de gradiente, conversión fototérmica y ensamblado por potencial DLVO / APTES. |

---

## 📘 4. Instructivo Maestro: Protocolo para Crear e Integrar Nuevos Reportes de Sistema (`SYS-XXX`)

Cuando se documente un nuevo módulo de hardware, driver, refactorización de concurrencia o auditoría en PyPrinting 3.0, el autor debe seguir el siguiente procedimiento:

### Paso 1: Asignación de Signatura Canónica (`SYS-XXX`)
1. Seleccionar el Cluster Temático correspondiente:
   - `SYS-000`: Estándares de Diseño y Gobernanza.
   - `SYS-100`: Concurrencia, Señales y Cinemática.
   - `SYS-200`: Instrumentación Óptica, Actuadores y Seguridad.
   - `SYS-300`: Espectrometría, Bancos Ópticos y Procesamiento.
   - `SYS-400`: Auditorías de Código y Benchmarking.
2. Asignar el siguiente identificador numérico libre dentro del cluster (ej. `SYS-205` o `SYS-306`).
3. Asignar la etiqueta de eje temático: `[EST]`, `[ARQ]`, `[INS]`, `[SEG]`, `[DAT]`, `[CAL]`, `[PRT]` o `[AUD]`.
4. Nombrar el archivo bajo la sintaxis: `SYS-XXX_Nombre_Descriptivo.md`.

### Paso 2: Desacoplamiento de Ejes (Regla Software vs Física)
- Si el reporte describe cómo funciona el código, la interacción con hardware, los hilos o las auditorías, pertenece a `reportes/sistema/` (`SYS-XXX`).
- Si el reporte contiene deducciones matemáticas formales paso a paso, teoremas físicos o modelos analíticos continuos, **desacople esa sección y cree una nota científica complementaria en `reportes/cientificos/` (`CAT-XXX`)**.
- Vincule ambos documentos bidireccionalmente mediante enlaces de Obsidian `[[...]]`.

### Paso 3: Encabezado y Matriz de Referencias Obligatoria
Todo reporte de sistema debe comenzar obligatoriamente con la plantilla institucional de encabezado:

```markdown
# SYS-XXX: [Título Descriptivo y Preciso del Reporte Técnico] ⚙️

**PyPrinting 3.0 / PySpectrum 3.0 — Suite de Nanofotónica y Control Instrumental**  
**Laboratorio de Nanofotónica — Instituto de Nanosistemas (INS-UNSAM / CONICET)**  
**Autor Principal:** [Nombre del Autor]  
**Código del Documento:** `SYS-XXX` | **Eje Temático:** `[ARQ/INS/SEG/DAT/CAL/PRT/AUD/EST]`  
**Fecha de Emisión:** [Mes Año] | **Estado:** [Borrador / Aprobado / Producción]

---

## 🔗 Matriz de Referencias Cruzadas

- **Reportes de Sistema Conexos:**
  - `[[SYS-YYY_...]]`: Relación funcional de software o hardware.
- **Fundamentos Científicos Asociados:**
  - `[[CAT-AAA_...]]`: Base física, modelo analítico o metrología de soporte.
- **Módulos de Código Fuente:** `core/...`, `modules/...`, `tests/...`

---
```

### Paso 4: Actualización del Índice Maestro
1. Insertar el nuevo reporte en la tabla del Cluster correspondiente en la Sección 2 de este documento (`reportes/README.md`).
2. Incorporar la fila respectiva en la **Matriz de Interconexión Software $\leftrightarrow$ Física** (Sección 3).
3. Ejecutar el script de validación de enlaces para asegurar consistencia del grafo documental.
