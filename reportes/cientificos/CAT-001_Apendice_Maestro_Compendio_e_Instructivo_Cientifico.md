# CAT-001: Apéndice Maestro, Compendio Metrológico e Instructivo de la Base de Conocimiento
## Guía Oficial del Sistema Bibliotecario Científico, Cristalografía 2D, Fotónica y Métodos Computacionales — PyPrinting 3.0

---

**Signatura Bibliotecaria:** `CAT-001`  
**Clasificación Temática:** `[MET]` Documento Rector, Compendio Metrológico y Estándares Metodológicos  
**Pilar:** Marco Transversal — Base de Conocimiento Científico PyPrinting 3.0  
**Autoría:** Comité Científico y de Arquitectura de Software (INS-UNSAM / CONICET)  
**Fecha de Publicación:** Septiembre 2026  
**Estado:** Producción / Consolidado  
**Índice General:** [[README]] (`printing3/reportes/README.md`)  

---

## 1. Filosofía del Sistema Bibliotecario Científico PyPrinting 3.0

El ecosistema de reportes científicos de **PyPrinting 3.0** constituye la base teórica, metrológica y algorítmica que sustenta las capacidades del software: desde el control de hardware optomecánico en tiempo real y la super-resolución óptica sub-píxel, hasta el análisis cristalográfico de redes cuánticas 2D en espacio real y recíproco.

Para asegurar la máxima agilidad de consulta, modularidad y legibilidad (impidiendo que los documentos se vuelvan monolíticos o pesados de leer), la base de conocimiento se estructura bajo un **sistema de signaturas bibliotecarias canónicas (`CAT-XXX`)**, donde cada nota se clasifica en uno de los 4 Pilares del Conocimiento y responde a un eje temático específico:
- `[MAT]` **Fundamentos Matemáticos:** Deducciones analíticas completas paso a paso, álgebra tensorial, matrices de Fisher y mecánica estadística.
- `[FIS]` **Fenomenología Física:** Óptica de difracción, microscopía confocal/iSCAT, perfiles de intensidad y física del estado sólido.
- `[CMP]` **Métodos Computacionales:** Algoritmos de grafos, indexación espacial, aceleración BLAS y ensambles de Monte Carlo.
- `[PRT]` **Protocolos Operativos:** Guías prácticas de laboratorio ("DO PRINTING"), calibración de hardware y recetas experimentales.

---

## 2. Compendio Metrológico General de las 33 Notas Canónicas

```
                                SISTEMA BIBLIOTECARIO PYPRINTING 3.0
                                
       [PILAR I: NANOFABRICACIÓN Y CONTROL]         [PILAR II: SUPER-RESOLUCIÓN Y ESPECTROMETRÍA]
       - CAT-101 [PRT] Impresión Grillas 2D          - CAT-201 [CMP] Deconvolución y Trackpy
       - CAT-102 [MAT] Redes 2D y Ancla P0           - CAT-202 [MAT] Cota Cramér-Rao (CRLB)
       - CAT-103 [FIS] Parada y Dímeros              - CAT-203 [FIS] Presupuesto ISO/GUM
       - CAT-104 [FIS] Confocal Tilt y Healing       - CAT-204 [CMP] Curación Fotométrica
       - CAT-105 [FIS] Deriva Térmica P0             - CAT-205 [FIS] Mapeo Hiperespectral SERS
       - CAT-106 [CMP] Autofoco Adaptativo
       - CAT-107 [FIS] Cinética Time-Volt
       - CAT-108 [FIS] Telescopio Relé 4f e iSCAT
       - CAT-109 [FIS] Electrodinámica y Fuerzas
       - CAT-110 [FIS] Fisicoquímica y DLVO
       - CAT-111 [FIS] Nanotermometría DLS
       - CAT-112 [FIS] Lente Térmica y Marangoni
       - CAT-113 [CMP] Lazo Cerrado Metrológico
                             \                             /
                              \                           /
                               v                         v
                       [PILAR III: CRISTALOGRAFÍA 2D Y ESPACIO RECÍPROCO]
                       - CAT-301 [CMP] KDTree Acotado y Monte Carlo
                       - CAT-302 [FIS] Física de Defectos y Orden psi_4/6
                       - CAT-303 [MAT] Deducción Radial g(r) y Factor sqrt(2)
                       - CAT-304 [FIS] Metrología Conchas g(r) y Difracción
                       - CAT-305 [MAT] Factor Estructura y Debye-Waller
                       - CAT-306 [FIS] Óptica de Difracción y Perfiles
                       - CAT-307 [CMP] NUFFT 2D y Aceleración BLAS-3
                       - CAT-308 [MAT] Inversión Analítica Picos Bragg
                       - CAT-309 [FIS] Paracristal Hosemann (Tipo I vs II)
                       - CAT-310 [MAT] Paracristal 2D Anisótropo Analítico
                       - CAT-311 [CMP] Inferencia Bayesiana MCMC
                       - CAT-312 [CMP] Aceleración Tensorial GPU/CUDA
                                         |
                                         v
                         [PILAR IV: ARQUITECTURA DE DATOS]
                         - CAT-401 [CMP] Serialización HDF5 (.h5)
                         - CAT-402 [CMP] Estandarización NeXus y Datos FAIR
```

---

### PILAR I: Nanofabricación Óptica, Control de Posición y Estabilidad Optomecánica

| Signatura | Documento | Eje | Ecuación / Modelo Fundamental | Módulo Vinculado |
|---|---|:---:|---|---|
| **`CAT-101`** | [[CAT-101_Protocolo_Operativo_Impresion_Fototermica_Grillas_2D]] | `[PRT]` | Protocolo experimental "DO PRINTING", calibración de potencias y recetas. | `gui/printing_routine.py` |
| **`CAT-102`** | [[CAT-102_Sintesis_Cristalografica_Redes_2D_y_Particula_Ancla]] | `[MAT]` | $d^2(m,n) = m^2 a^2 + n^2 b^2 + 2mn ab \cos\gamma \ge d_{\text{min}}^2$ (15 familias 2D). | `core/lattice_generator.py` |
| **`CAT-103`** | [[CAT-103_Control_Lazo_Cerrado_Fototermico_y_Sintesis_Dimeros]] | `[FIS]` | $\Delta V(t) = V(t) - V(t - \Delta t) \ge V_{\text{umbral}}$, 5 modos de parada por fotodiodo. | `hardware/photodiode_monitor.py` |
| **`CAT-104`** | [[CAT-104_Compensacion_Inclinacion_Z_Confocal_y_Healing_Pass]] | `[FIS]` | $Z(x,y) = Z_0 + \alpha x + \beta y$, manteniendo error $|\delta Z| \ll z_R = \frac{\pi w_0^2}{\lambda}$. | `motion/tilt_compensator.py` |
| **`CAT-105`** | [[CAT-105_Compensacion_Deriva_Termomecanica_Particula_Ancla_P0]] | `[FIS]` | $\vec{D}(t) = \mathbf{r}_{P0}(t) - \mathbf{r}_{P0}(0)$, corrección piezoeléctrica sustractiva. | `hardware/drift_tracker.py` |
| **`CAT-106`** | [[CAT-106_Control_Adaptativo_Frecuencia_Autofoco_Gradiente_Deriva]] | `[CMP]` | $N_{\text{adaptive}} = \text{clip}\left( \frac{\tau_{\text{safe}}}{\|\vec{v}_{\text{drift}}\|\Delta t}, N_{\text{min}}, N_{\text{max}} \right)$. | `hardware/adaptive_autofocus.py` |
| **`CAT-107`** | [[CAT-107_Cinetica_Captura_Fotodiodo_Time_Volt_Filtro_Nhold]] | `[FIS]` | Ajuste sigmoidal no lineal de 4 parámetros y filtro anti-paso $N_{\text{hold}}$. | `analysis/time_volt_analyzer.py` |
| **`CAT-108`** | [[CAT-108_Teoria_Optica_Telescopio_Rele_4f_y_Canales_Confocales]] | `[FIS]` | Matriz relé 4f ($\Gamma=1.25\times$), $AU$ ($50/100\,\mu\text{m}$), Nyquist, iSCAT ($d^3$), PSF $TEM_{00}$ y $LG_{01}$. | `core/nidaq.py` / `psf_analyzer.py` |
| **`CAT-109`** | [[CAT-109_Electrodinamica_Fuerzas_Opticas_y_Termoplasmonica_Printing]] | `[FIS]` | Sección eficaz Mie/Rayleigh, gradiente $\mathbf{F}_{\text{grad}}$, dispersión $\mathbf{F}_{\text{scat}}$, calentamiento Joule y nanotermometría. | `modules/measurements.py` |
| **`CAT-110`** | [[CAT-110_Fisicoquimica_Coloides_DLVO_y_Funcionalizacion_Superficies]] | `[FIS]` | Potencial DLVO $V_{\text{tot}} = V_{\text{vdW}} + V_{\text{EDL}}$, potencial $\zeta$, monocapa APTES ($-\text{NH}_3^+$) e inmovilización. | `docs/modulos/MOD-14_Protocolos_Laboratorio_SOP.md` |
| **`CAT-111`** | [[CAT-111_Nanotermometria_DLS_y_Dinamica_Fluctuaciones_Brownianas]] | `[FIS]` | Nanotermometría local $D(T) = \frac{k_B T}{6\pi \eta(T) R_h}$, modelo VFT del agua e inversión analítica de $T_{\text{nano}}$. | `analysis/time_volt_analyzer.py` |
| **`CAT-112`** | [[CAT-112_Teoria_Lente_Termica_Gradientes_Indice_y_Marangoni]] | `[FIS]` | Gradiente termo-óptico $\Delta n = (dn/dT)\Delta T$, señal pinhole $\Delta I/I_0 \approx 2\theta$, convección de Marangoni $\mathbf{\tau}_M = -\beta_T \nabla_\parallel T$. | `modules/measurements.py` |
| **`CAT-113`** | [[CAT-113_Lazo_Cerrado_Metrologico_InSitu_y_Control_Predictivo]] | `[CMP]` | Control predictivo RLS $\mathbf{r}_{\text{cmd}} = \hat{\mathbf{A}}^{-1}(\mathbf{r}_{\text{ideal}} - \hat{\mathbf{b}})$, reducción RMS de red a $<4\ \text{nm}$. | `core/nanopositioning.py` |

---

### PILAR II: Super-Resolución Óptica, Detección Sub-píxel y Espectrometría

| Signatura | Documento | Eje | Ecuación / Modelo Fundamental | Módulo Vinculado |
|---|---|:---:|---|---|
| **`CAT-201`** | [[CAT-201_Deconvolucion_Optica_Richardson_Lucy_y_Tracking_Trackpy]] | `[CMP]` | $I^{(k+1)} = I^{(k)} \cdot \left[ \frac{I_{\text{exp}}}{I^{(k)} \ast \text{PSF}} \ast \text{PSF}^{\vee} \right]$ y seguimiento Trackpy. | `analysis/deconvolution_tracker.py` |
| **`CAT-202`** | [[CAT-202_Derivacion_Matematica_Cota_Cramer_Rao_Localizacion_Optica]] | `[MAT]` | $\sigma_{x,\text{CRLB}} \approx \frac{\text{FWHM}_{\text{psf}}}{2.355 \sqrt{N}}$, matrices de Fisher y cota para Donut $LG_{01}$. | `analysis/cramer_rao_bound.py` |
| **`CAT-203`** | [[CAT-203_Presupuesto_Incertidumbre_Metrologica_ISOGUM_Microscopia]] | `[FIS]` | $u_c(x_0) = \sqrt{u_{\text{piezo}}^2 + u_{\text{pix}}^2 + u_{\text{fit}}^2 + u_{\text{drift}}^2 + u_{\text{ph}}^2} = \mathbf{6.55\,nm}$ (60xW). | `analysis/uncertainty_model.py` |
| **`CAT-204`** | [[CAT-204_Curacion_Fotometrica_Desacople_MultiGaussiano_Consistencia]] | `[CMP]` | Huella monómero $(V_0, A_0, \sigma_{\text{psf}})$, $M_{\text{curado}} + n_{\text{vac}} \le N_{\text{total}}(1 + \text{margen}/100)$. | `analysis/photometric_curation.py` |
| **`CAT-205`** | [[CAT-205_Mapeo_Hiperespectral_SERS_Confocal_Automatizado]] | `[FIS]` | Realce $EF \approx |E_{\text{loc}}/E_0|^4$, trayectoria meandro TSP, hipercubo $\mathcal{H}(X, Y, \lambda)$ y MCR-ALS. | `pyspectrum.py` / `raman_analyzer.py` |

---

### PILAR III: Cristalografía 2D, Espacio Recíproco y Metrología de Desorden

| Signatura | Documento | Eje | Ecuación / Modelo Fundamental | Módulo Vinculado |
|---|---|:---:|---|---|
| **`CAT-301`** | [[CAT-301_Algoritmos_Espacio_Real_KDTree_Asignacion_Monte_Carlo]] | `[CMP]` | Bounded KDTree ($r_{\text{cut}} = a/2$), asignación Húngara y ensambles Monte Carlo. | `analysis/lattice_disorder_gui.py` |
| **`CAT-302`** | [[CAT-302_Caracterizacion_Fisica_Desorden_Defectos_Redes_SMLM]] | `[FIS]` | Orden orientacional $\psi_n = \frac{1}{N} \sum e^{i n \theta_{jk}}$, pares 5-7 de Voronoi y modos SLR. | `core/lattice_disorder.py` |
| **`CAT-303`** | [[CAT-303_Derivacion_Matematica_Distribucion_Radial_gr_Correccion_Borde]] | `[MAT]` | Prueba formal $\sigma_{\text{rdf}} = \frac{\sigma_{\text{peak}}}{\sqrt{2}}$, cuadratura 2D y corrección de Green. | `analysis/radial_distribution.py` |
| **`CAT-304`** | [[CAT-304_Metrologia_Experimental_Conchas_Coordinacion_gr_Redes_2D]] | `[FIS]` | Corte de difracción ($r < 250\,\text{nm}$), ventana de defectos sub-red e invariancia $\theta$. | `core/lattice_disorder.py` |
| **`CAT-305`** | [[CAT-305_Derivacion_Matematica_Factor_Estructura_Debye_Waller]] | `[MAT]` | $I_{\text{Bragg}} = (1-p)^2 e^{-q^2 \sigma_{\text{pos}}^2} \frac{(2\pi)^2}{a^2}\sum\delta(\mathbf{q}-\mathbf{G})$, Wilson Plot 2D. | `analysis/fourier_peaks.py` |
| **`CAT-306`** | [[CAT-306_Metrologia_Optica_Difraccion_Bragg_y_Perfiles_Redes_2D]] | `[FIS]` | Anatomía BFP, perfiles radiales $\Delta q_\parallel$ (coherencia $\xi$) y transversales $\Delta q_\perp$. | `analysis/fourier_peaks.py` |
| **`CAT-307`** | [[CAT-307_Computacion_NUFFT_Factor_Estructura_Optimizacion_BLAS]] | `[CMP]` | NUFFT Tipo 1 tensorial $M = E_y E_x^T$, spreading BLAS-3 y velocidad $\mathcal{O}(M\log M)$. | `analysis/nufft_structure_factor.py` |
| **`CAT-308`** | [[CAT-308_Metrologia_Analitica_Directa_Picos_Bragg_Fourier_2D]] | `[MAT]` | Inversión cerrada $\sigma_{\text{pos}} = \frac{a}{2\pi\sqrt{3}}\sqrt{\ln(H_1/H_2)}$ (cancela $N$ y $p$). | `analysis/direct_bragg_metrology.py` |
| **`CAT-309`** | [[CAT-309_Teoria_Paracristal_Hosemann_Perdida_Orden_2D]] | `[FIS]` | Discriminación Tipo I vs II: $\eta_H = \frac{\text{FWHM}_2}{\text{FWHM}_1} \approx 4.0$ (Hosemann). | `analysis/hosemann_paracrystal.py` |
| **`CAT-310`** | [[CAT-310_Derivacion_Matematica_Paracristal_2D_Hosemann_Anisotropo]] | `[MAT]` | $S(\mathbf{q}) = \text{Re}\{\frac{1+\mathbf{\Phi}_{10}}{1-\mathbf{\Phi}_{10}}\}\text{Re}\{\frac{1+\mathbf{\Phi}_{01}}{1-\mathbf{\Phi}_{01}}\}$, log-verosimilitud analítica. | `core/lattice_disorder.py` |
| **`CAT-311`** | [[CAT-311_Inferencia_Bayesiana_MCMC_Desorden_Paracristal]] | `[CMP]` | Cholesky $\mathbf{\Sigma} = \mathbf{L}\mathbf{L}^T$, ensamble `emcee`, corner plots y elipses de covarianza. | `core/lattice_disorder.py` |
| **`CAT-312`** | [[CAT-312_Computacion_Tensorial_GPU_CUDA_NUFFT_y_Deconvolucion]] | `[CMP]` | Spreading en shared memory GPU, cuFFT 2D batched $<12\ \text{ms}$ a $>60\ \text{fps}$ y fallback CPU. | `core/lattice_disorder.py` |

---

### PILAR IV: Arquitectura de Datos, Serialización y Ecosistema de Software

| Signatura | Documento | Eje | Ecuación / Modelo Fundamental | Módulo Vinculado |
|---|---|:---:|---|---|
| **`CAT-401`** | [[CAT-401_Estandar_Serializacion_Jerarquica_Contenedor_HDF5]] | `[CMP]` | Serialización jerárquica HDF5 (`/raw`, `/curated`, `/reciprocal`), compresión `shuffle+gzip`. | `io/hdf5_exporter.py` |
| **`CAT-402`** | [[CAT-402_Estandar_Datos_FAIR_y_Serializacion_NeXus_HDF5]] | `[CMP]` | Ontología NeXus (`NXdata`, `NXsample`, `NXinstrument`), procedencia criptográfica SHA-256 y datos FAIR. | `core/hdf5_container.py` |

---

## 3. Glosario Canónico de Variables y Notación Físico-Matemática

| Símbolo | Significado Físico Canónico | Unidades | Ecuación / Definición | Documento Rector |
| :---: | :--- | :---: | :--- | :--- |
| $\mathbf{q}, q$ | Vector / magnitud de onda recíproco | $\text{nm}^{-1}$ | $q = 2\pi f = 2\pi / \lambda$ | [[CAT-305_Derivacion_Matematica_Factor_Estructura_Debye_Waller]] |
| $a$ | Constante de red (período espacial) | $\text{nm}$ | $a = 2\pi / q_1$ | [[CAT-305_Derivacion_Matematica_Factor_Estructura_Debye_Waller]] |
| $\sigma_{\text{pos}}$ | Desorden posicional gaussiano de sitio | $\text{nm}$ | $\langle \mathbf{u}^2 \rangle = 2\sigma_{\text{pos}}^2$ (2D) | [[CAT-305_Derivacion_Matematica_Factor_Estructura_Debye_Waller]] |
| $\sigma_{\text{rdf}}$ | Dispersión de concha de pares en $g(r)$ | $\text{nm}$ | $\sigma_{\text{rdf}} = \sigma_{\text{peak}}/\sqrt{2} \equiv \sigma_{\text{pos}}$ | [[CAT-303_Derivacion_Matematica_Distribucion_Radial_gr_Correccion_Borde]] |
| $p$ | Fracción de sitios vacantes (vacancias) | Adimensional | $p = 1 - (M / N_{\text{sitios}})$ | [[CAT-305_Derivacion_Matematica_Factor_Estructura_Debye_Waller]] |
| $N_{\text{sitios}}$ | Número total de sitios teóricos nominales | Adimensional | $N_{\text{sitios}} = N_x \times N_y$ | [[CAT-301_Algoritmos_Espacio_Real_KDTree_Asignacion_Monte_Carlo]] |
| $M$ | Número de nanopartículas reales detectadas | Adimensional | $M = (1 - p) N_{\text{sitios}}$ | [[CAT-204_Curacion_Fotometrica_Desacople_MultiGaussiano_Consistencia]] |
| $S(\mathbf{q})$ | Factor de estructura estático continuo | Adimensional | $S(\mathbf{q}) = \frac{1}{\sqrt{N}} \sum c_j e^{-i \mathbf{q}\cdot\mathbf{r}_j}$ | [[CAT-307_Computacion_NUFFT_Factor_Estructura_Optimizacion_BLAS]] |
| $H_1, H_2$ | Alturas netas de picos de Bragg axial 1 y 2 | Adimensional | $H_2/H_1 = e^{-3 q_1^2 \sigma_{\text{pos}}^2}$ | [[CAT-308_Metrologia_Analitica_Directa_Picos_Bragg_Fourier_2D]] |
| $\text{FWHM}_q$ | Ancho a media altura en espacio recíproco | $\text{nm}^{-1}$ | $\text{FWHM}_q = 2\sqrt{2\ln 2} \, \sigma_q$ | [[CAT-306_Metrologia_Optica_Difraccion_Bragg_y_Perfiles_Redes_2D]] |
| $\eta_H$ | Cociente diagnóstico de Hosemann | Adimensional | $\eta_H = \text{FWHM}_2 / \text{FWHM}_1$ | [[CAT-309_Teoria_Paracristal_Hosemann_Perdida_Orden_2D]] |
| $\xi$ | Longitud de coherencia espacial traslacional | $\text{nm}$ | $\xi = 2\pi / \Delta q_\parallel$ | [[CAT-306_Metrologia_Optica_Difraccion_Bragg_y_Perfiles_Redes_2D]] |
| $\sigma_{x,\text{CRLB}}$ | Cota Inferior de Cramér-Rao en localización | $\text{nm}$ | $\sigma_{x,\text{CRLB}} \approx \frac{\sigma_{\text{psf}}}{\sqrt{N}}$ | [[CAT-202_Derivacion_Matematica_Cota_Cramer_Rao_Localizacion_Optica]] |
| $u_c$ | Incertidumbre estándar combinada ISO/GUM | $\text{nm}$ | $u_c = \sqrt{\sum u_i^2}$ | [[CAT-203_Presupuesto_Incertidumbre_Metrologica_ISOGUM_Microscopia]] |
| $\mathbf{\Sigma}_{10}, \mathbf{\Sigma}_{01}$ | Tensores de fluctuación reticular de Hosemann | $\text{nm}^2$ | $\mathbf{\Sigma} = \mathbf{L}\mathbf{L}^T$ (Cholesky definido positivo) | [[CAT-310_Derivacion_Matematica_Paracristal_2D_Hosemann_Anisotropo]] |
| $\mathbf{\Phi}_{10}, \mathbf{\Phi}_{01}$ | Transformada de Fourier de enlaces de red | Adimensional | $\mathbf{\Phi}(\mathbf{q}) = \exp(-i \mathbf{q}\cdot\mathbf{a} - \frac{1}{2}\mathbf{q}^T\mathbf{\Sigma}\mathbf{q})$ | [[CAT-310_Derivacion_Matematica_Paracristal_2D_Hosemann_Anisotropo]] |
| $T_{\text{nano}}$ | Temperatura nanométrica local por DLS | $\text{K}$ | $D(T) = k_B T / [6\pi \eta(T) R_h]$ (Modelo VFT) | [[CAT-111_Nanotermometria_DLS_y_Dinamica_Fluctuaciones_Brownianas]] |
| $\theta$ | Parámetro de corrimiento de lente térmica | Adimensional | $\theta = P_{\text{abs}}(dn/dT) / (\lambda_0 \kappa)$ | [[CAT-112_Teoria_Lente_Termica_Gradientes_Indice_y_Marangoni]] |
| $\mathbf{\tau}_M$ | Esfuerzo tangencial de Marangoni | $\text{N/m}^2$ | $\mathbf{\tau}_M = \nabla_s \gamma = -\beta_T \nabla_\parallel T$ | [[CAT-112_Teoria_Lente_Termica_Gradientes_Indice_y_Marangoni]] |
| $EF_{\text{SERS}}$ | Factor de realce electromagnético SERS | Adimensional | $EF \approx \|E_{\text{loc}}/E_0\|^4$ (Ley de 4ta potencia) | [[CAT-205_Mapeo_Hiperespectral_SERS_Confocal_Automatizado]] |
| $\mathbf{\mathcal{H}}$ | Hipercubo tensorial hiperespectral 3D | $\text{Cuentas}$ | $\mathbf{\mathcal{H}} \in \mathbb{R}^{N_x \times N_y \times N_\lambda}$ | [[CAT-205_Mapeo_Hiperespectral_SERS_Confocal_Automatizado]] |

---

## 4. Instructivo Maestro: Protocolo para Crear e Integrar Nuevas Notas Científicas

Cuando se desarrolle un nuevo modelo, algoritmo o técnica física en PyPrinting 3.0, el autor debe seguir rigurosamente los siguientes cinco pasos:

### Paso 1: Asignación de Signatura Bibliotecaria
1. Seleccionar el Pilar temático (`CAT-100`, `CAT-200`, `CAT-300` o `CAT-400`).
2. Asignar el número secuencial disponible (e.g. `CAT-310`).
3. Definir la etiqueta de eje: `[MAT]` si es derivación formal, `[FIS]` si es física/metrología, `[CMP]` si es algoritmo, o `[PRT]` si es protocolo.
4. Nombrar el archivo bajo la sintaxis: `CAT-XXX_Nombre_Descriptivo_Sin_Sufijos_Redundantes.md`.

### Paso 2: Desacoplamiento de Ejes (Regla Antimonolítica)
Si el tema requiere demostraciones matemáticas de más de 3 páginas y a la vez involucra protocolos experimentales de calibración, **divida el trabajo en un par gemelo**:
- `CAT-XXX [MAT]`: Deducción analítica completa.
- `CAT-YYY [FIS]`: Aplicación experimental, límites de validez y protocolos.
Conecte ambos documentos mediante los bloques de enlace contextual estandarizados.

### Paso 3: Rigor en Primeros Principios y Unidades
1. Deduzca paso a paso sin saltos algebraicos ni frases del tipo "se demuestra fácilmente que".
2. Emplee estrictamente los símbolos del Glosario Canónico de la Sección 3.
3. Incluya un bloque de código Python ejecutable con tipado estricto (`typing`) y NumPy vectorizado.

### Paso 4: Actualización del Grafo de Conocimiento Wiki
1. Inserte enlaces bidireccionales `[[...]]` hacia las notas precedentes.
2. Actualice la tabla de la Sección 2 de este documento (`CAT-001`).
3. Incorpore la nueva entrada en el índice general `reportes/README.md`.

---

## 5. Plantilla Oficial de Producción

```markdown
# CAT-XXX [EJE]: [Título Exhaustivo del Reporte Científico]
## [Subtítulo Descriptivo: Fenómeno Físico, Modelo Matemático o Técnica Computacional]

---

**Signatura Bibliotecaria:** `CAT-XXX`  
**Clasificación Temática:** `[MAT | FIS | CMP | PRT]` [Descripción del Eje]  
**Pilar:** [I | II | III | IV] — [Nombre del Pilar]  
**Autoría:** [Autor / Especialidad] — PyPrinting 3.0  
**Fecha de Publicación:** [Mes Año]  
**Estado:** Producción / Consolidado  
**Documentos Vinculados:**  
- [[CAT-001_Apendice_Maestro_Compendio_e_Instructivo_Cientifico]] (Glosario y estándares)  
- `[[CAT-YYY_Nota_Relacionada]]` (Vínculo contextual)  

---

### Resumen Ejecutivo
[1 a 2 párrafos concisos con el problema, el hallazgo físico/matemático y la repercusión en PyPrinting 3.0]

---

## 1. Marco Teórico y Primeros Principios
...
## 2. Derivación Matemática Paso a Paso
...
## 3. Análisis de Incertidumbre y Límites Físicos
...
## 4. Implementación de Referencia en Python (PyPrinting 3.0)
...
## 5. Conclusiones y Criterios Operativos
...
```
