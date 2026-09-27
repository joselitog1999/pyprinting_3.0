# Auditoría L6 — Espectroscopía y quimiometría

**Estado del informe:** COMPLETO (2026-09-27). Se cubrieron los cinco documentos.

**Conteo.** Se auditaron 85 afirmaciones; S306-01 es un duplicado de C207 y no se suma.

| Veredicto | Cantidad |
|---|---|
| CONTRADICHO | 50 (incluye contradicciones parciales y menores) |
| CONFIRMADO | 24 |
| SIN FUENTE | 7 |
| CITA ERRÓNEA | 4 |
| REQUIERE BANCO (como veredicto principal) | 0 (seis afirmaciones requieren confirmación en el banco; ver la sección final) |

| Severidad | Cantidad |
|---|---|
| CRÍTICA | 3 |
| ALTA | 7 |
| MEDIA | 15 |
| BAJA | 40 |
| Sin severidad (confirmadas) | 20 |

**Alcance:** CAT-205, CAT-207, CAT-250, SYS-306, MOD-11.

**Método.**
1. Orientación con Graphify (`graphify query` / `graphify explain`).
2. Lectura del código: `core/raman_engine.py`, `analysis/multi_spectrum_widget.py`, `analysis/raman_analyzer.py`, `pyspectrum/modules/hyperspectral_confocal.py`, `pyspectrum/drivers/andor_ccd_driver.py`, `config.py`.
3. Verificación externa: artículos con DOI, normas, hojas de datos.
4. Pruebas numéricas en el scratchpad (`scratchpad/auditoria/l6_tests.py`), importando el motor con `PYTHONDONTWRITEBYTECODE=1` para no escribir nada en el repositorio.

**Referencias locales usadas como fuente:**
- `.claude/shared/lab-invariants.md` (sólo filas ✅) y DEC-033.
- `docs/bibliografia/Andor_iXon3_885_Specifications.pdf` y `andor-shamrock-500-specifications.pdf`.
- Tesis de L. Martínez, texto ya extraído en `scratchpad/tesis/martinez.txt`.

**Geometría de referencia (DEC-033).** Detector de 1004 × 1002 px, con píxeles de 8 µm. Dispersión nominal: 12.83 nm/mm (150 l/mm) y 1.44 nm/mm (1200 l/mm). Eso equivale a:

| Red | nm/px | cm⁻¹/px a 545 nm | cm⁻¹/px a 850 nm | Ventana por posición de red |
|---|---|---|---|---|
| 150 l/mm | 0.1026 | ≈ 3.46 | ≈ 1.42 | ≈ 103 nm |
| 1200 l/mm | 0.01152 | ≈ 0.39 | ≈ 0.16 | ≈ 11.6 nm |

La tesis de Martínez (líneas 2176-2200 de `martinez.txt`) registra la práctica real del laboratorio: Shamrock 500i con red de 150 l/mm, "resolución de la red de difracción es de 1 nm", rango de 103 nm, y "calibración … proporcionada por el fabricante … se ajusta con un valor de corrección que se verifica con la incidencia de dos láseres". Líneas láser del laboratorio: 532, 592, 637 y 808 nm (`config.py:65`); la tesis agrega 405 y 640 nm (línea 2001). Ninguna de las dos fuentes menciona 785 nm.

**Pruebas numéricas propias (resumen).**
- AsLS (`baseline_asls`): mediana de 11.8 ms con N = 1004 y 17.8 ms con N = 2048, en esta estación de trabajo.
- Filtro de rayos cósmicos sobre picos Raman genuinos (gaussianos, amplitud 2000 y ruido de σ = 10): con FWHM de 1.5 a 4 px pierde entre el 10 % y el 80 % del área del pico; con FWHM de 6 px pierde menos del 6 %. En todos los casos marca 2 o más píxeles como "rayo cósmico".
- Parser (`parse_andor_solis_file`): funciona con tabulación y decimal punto o coma. Falla con `ValueError` en CSV delimitados por coma, por coma más espacio y por punto y coma.
- Termometría: si los datos siguen la ley de conteo de fotones (ω³), el código, que aplica ω⁴, subestima T. Con 532 nm: −6.5 K a 300 K, −11.5 K a 400 K y −21.5 K a 550 K. Con 808 nm: −9.8 K, −17.2 K y −32 K. El sesgo no depende de Ω.

---

## CAT-205 — Mapeo hiperespectral SERS confocal automatizado

`reportes/cientificos/CAT-205_Mapeo_Hiperespectral_SERS_Confocal_Automatizado.md`

| ID | Documento:línea | Afirmación | Veredicto | Severidad | Fuentes | Corrección propuesta |
|---|---|---|---|---|---|---|
| C205-01 | CAT-205:69-70 | Por nodo: "b. Esperar tiempo de asentamiento mecánico (t_settle = 35 ms) … d. Adquirir espectro con Andor iXon3 EMCCD (t_int = 50 - 500 ms)" | CONTRADICHO | CRÍTICA | `pyspectrum/modules/hyperspectral_confocal.py:261` (QTimer de 20 ms), `:341` `pi.MOV(...)`, `:344` `camera.get_most_recent_image()` inmediatamente después; `pyspectrum/drivers/andor_ccd_driver.py:520-532` (`GetMostRecentImage`, no bloqueante) | El código no espera asentamiento, no verifica on-target y no espera a que termine la exposición: toma el último cuadro del buffer 20 ms después de mandar el movimiento. Con exposiciones de 50–500 ms, el espectro asignado a (x, y) corresponde a un cuadro adquirido antes o durante el movimiento, así que el mapa queda mal registrado. Corregir primero el código (esperar on-target, disparar una adquisición por nodo y esperar a que termine) y después documentar el asentamiento medido. |
| C205-02 | CAT-205:66, 77-82, 146-165 | "Ordenamiento Topológico TSP / meandro (serpentina)"; clase `SERSHyperspectralMapper` como "Implementación Computacional" | CONTRADICHO | ALTA | `hyperspectral_confocal.py:359-363` (raster con retorno de carro); `SERSHyperspectralMapper`, "meander" y "serpentin" no aparecen en ningún `.py` versionado (`git ls-files`) | Aclarar que el módulo real hace un raster simple y que §5 es pseudocódigo que no existe en el repo, o implementarlo. |
| C205-03 | CAT-205:69, 71 | "c. Abrir obturador … e. Cerrar obturador" en cada nodo | CONTRADICHO | MEDIA | `hyperspectral_confocal.py:311` (se abre una vez en `start_scan`), `:322` (se cierra en `stop_scan`), `:335` (`heartbeat_shutter()` por punto) | El obturador queda abierto durante todo el mapa; la protección contra el fotoblanqueamiento de §6.1 no existe. Documentar el ciclo real. |
| C205-04 | CAT-205:92 | "N_λ = 1024 (canales espectrales del sensor EMCCD)" | CONTRADICHO | ALTA | `lab-invariants.md` §3 ✅ `DETECTOR_WIDTH_PX = 1004`; `hyperspectral_confocal.py:295` (`ShamrockGetCalibration(DEVICE, 1004)`); hoja de datos del iXon3 885 ("Active pixels 1004 x 1002"); DEC-033 | N_λ = 1004. Es el mismo tipo de error de geometría que DEC-033. |
| C205-05 | CAT-205:35, 69, 139 | Excitación "785 nm / 532 nm"; `laser_wavelength_nm = 785.0` por defecto | CONTRADICHO | MEDIA | `config.py:65` (532/637/592/808 nm); tesis Martínez, línea 2001 (405/532/592/640/808 nm) | No hay línea de 785 nm. Si se usa el valor por defecto de 785 nm con datos adquiridos a 808 nm, el eje Raman queda corrido unos 360 cm⁻¹. Usar las líneas reales y exigir λ_láser explícita. |
| C205-06 | CAT-205:68 | "platina piezoeléctrica PI E-709" | CONTRADICHO | BAJA | `lab-invariants.md` §1 ✅ (PI E-517); CLAUDE.md §4 | PI E-517. |
| C205-07 | CAT-205:82 | "v_piezo ≈ 200 µm/s … sin excitar resonancias" | SIN FUENTE | BAJA | No hay símbolo en el código ni fila en las invariantes | Citar la hoja de datos de la platina o eliminar el valor. En paso-y-adquisición dominan el asentamiento y la exposición. |
| C205-08 | CAT-205:17, 113-121 | Reconstrucción "mediante MCR-ALS y SVD" como capacidad integrada | CONTRADICHO (implementación) | MEDIA | No hay MCR ni NNLS en ningún `.py` versionado; sólo PCA/SVD (`core/raman_engine.py:1153`). La formulación D = C Sᵀ + E con no negatividad es la estándar (Tauler 1995, DOI 10.1016/0169-7439(95)00047-X) | Marcar MCR-ALS como propuesta, no como funcionalidad. |
| C205-09 | CAT-205:191-199 | `compute_band_integrated_map`: "integrando sobre una banda" | CONTRADICHO (menor) | BAJA | Código del propio documento: `np.sum(...)` sin peso Δν | El eje en cm⁻¹ no es uniforme cuando el detector es lineal en λ. Usar `np.trapezoid(..., raman_shifts[band_mask])`. |
| C205-10 | CAT-205:8 | Módulos asociados (`pyspectrum.py`, `raman_analyzer.py`, `sif_analyzer.py`, `measurements.py`) | CONTRADICHO (parcial) | BAJA | Graphify: el mapeo real está en `pyspectrum/modules/hyperspectral_confocal.py`, que no figura en la lista | Agregarlo como módulo principal. |
| C205-11 | CAT-205:206 | "de varias horas a pocos minutos" | SIN FUENTE | BAJA | — | Reemplazar por N·(t_settle + t_exp) o por una medición. |
| C205-12 | CAT-205:23 | σ_Raman ~ 10⁻³⁰–10⁻²⁸ cm²/molécula | CONFIRMADO (orden de magnitud) | — | Le Ru, Blackie, Meyer y Etchegoin, *J. Phys. Chem. C* 111, 13794 (2007) (PDF del autor): secciones eficaces diferenciales de 1.8×10⁻³¹ cm²/sr (metanol) y 5.4×10⁻³⁰ cm²/sr (2B2MP); ×8π/3 ≈ 10⁻³⁰–10⁻²⁹ cm². Los colorantes en pre-resonancia llegan a 10⁻²⁸–10⁻²⁶ cm²/sr. Una sola fuente leída | Aclarar si es sección total o diferencial (cm²/sr) y que el rango vale para moléculas no resonantes. |
| C205-13 | CAT-205:43-45 | EF = \|E(ω_L)/E₀\|²·\|E(ω_R)/E₀\|² ≈ \|E/E₀\|⁴ | CONFIRMADO | — | Le Ru y Etchegoin, *Chem. Phys. Lett.* 423, 63–66 (2006) (ScienceDirect PII S0009261406003642): \|E\|⁴ es una aproximación de la fórmula de reciprocidad; Le Ru et al. 2007 | Para corrimientos grandes (> 1000 cm⁻¹) sobre resonancias angostas, usar la forma producto y no \|E\|⁴. |
| C205-14 | CAT-205:37, 47-52 | Tabla de EF: monómero 10³–10⁴; dímero con gap de 5 nm 10⁶–10⁷; gap de 1.5 nm 5×10⁸–10⁹ = "SM-SERS"; SLR 10⁵–10⁶ | SIN FUENTE (compatible en orden de magnitud) | MEDIA | Le Ru et al. 2007: "EFs on the order of 10⁷–10⁸ are … sufficient for the detection of SM-SERS", "maximum SERS EFs are on the order of 10¹⁰ … at most 10¹²". Ninguna fila de la tabla tiene cita propia | Citar la fuente de cada fila (o simulaciones propias, CAT-208) y aclarar que el EF depende de su definición (SSEF, SMEF o AEF, según Le Ru 2007). |

---

## CAT-207 — Quimiometría: AsLS, Voigt, calibración y termometría

`reportes/cientificos/CAT-207_Quimiometria_Procesamiento_Espectral_AsLS_Voigt_Calibracion.md`

| ID | Documento:línea | Afirmación | Veredicto | Severidad | Fuentes | Corrección propuesta |
|---|---|---|---|---|---|---|
| C207-01 | CAT-207:179 | `calculate_photothermal_temperature` "aplica corrección espectral por la eficiencia cuántica del detector η(λ) y transmitancia del filtro notch" | CONTRADICHO | CRÍTICA | `core/raman_engine.py:834-872`: sólo recibe `shift_cm1`, `I_S`, `I_AS` y `laser_nm`; no hay corrección alguna | La T informada no está corregida por la respuesta espectral, y como Stokes y anti-Stokes caen en λ distintas, el sesgo es sistemático. Implementar la corrección con una curva de respuesta medida (lámpara halógena calibrada; existe `pyspectrum/calibration/halogen_lamp.py`) o documentar que no existe. |
| C207-02 | CAT-207:165-176 (y código `raman_engine.py:844, 859`) | Cociente I_AS/I_S con factor [(ω_L+Ω)/(ω_L−Ω)]⁴ | CONTRADICHO | CRÍTICA | Zani, Pedron, Pilot y Signorini, *Biosensors* 11, 102 (2021), DOI 10.3390/bios11040102 (PMC8066910): "A frequency dependence to the third power … is needed as the detection system is based on photon counting (CCD), whereas if the detection is energy-based, a fourth power dependence is more appropriate" (cita a Tuschel y Adar, *Spectroscopy* 31, 8–13, 2016). También se deduce directamente: tasa de fotones = P/ħω_s ∝ ω_s³. Prueba propia: −6.5 K a 300 K y −21.5 K a 550 K con 532 nm; −9.8 K y −32 K con 808 nm | Usar exponente 3 para cuentas CCD, tanto en la fórmula del documento como en `raman_engine.py:859`. |
| C207-03 | CAT-207:156-176 | T_nano en el hot spot a partir de I_AS/I_S "rigurosa" | CONTRADICHO (validez) | ALTA | Maher, Etchegoin, Le Ru y Cohen, arXiv:physics/0511097 (versión publicada: *J. Phys. Chem. B*, DOI 10.1021/jp056466r): ρ = A·[τσ_S I_L/ħω_L + e^(−ħω_v/k_BT)], con "A ≡ σ_aS/σ_S … asymmetry parameter … in SERS σ_aS ≠ σ_S … due to … plasmon resonances", además del bombeo vibracional | En SERS hace falta el factor de asimetría A y descartar el bombeo; sin eso, la T que se obtiene no es termodinámica. Restringir la fórmula a Raman no resonante (sustrato o solvente) o incluir A. |
| C207-04 | CAT-207:180, 211 | "u(T) = ±4.2 K"; "U(T) = ±8.4 K" | CONTRADICHO | ALTA | `raman_engine.py:839, 872` devuelve sólo `(T_K, T_C)`; `analysis/raman_analyzer.py:1638` muestra "T = xxx.x K" sin incertidumbre | No existe presupuesto alguno que produzca ±4.2 K, y los sesgos de C207-01/02/03 ya lo superan. Eliminar el número o derivarlo con la GUM (Poisson, u(Ω), u(λ_L), u(respuesta)). |
| C207-05 | CAT-207:180 | "T_spinodal ≈ 550 K" (agua) | CONTRADICHO | ALTA | Wang et al., *PNAS* (2018), arXiv:1903.04403: "water spinodal temperature Ts = 578.2 K" a 1 atm; Carlson, Green y Richardson, *Nano Lett.* 12, 1534 (2012), DOI 10.1021/nl2043503: "spinodal decomposition temperature at 594 ± 17 K" | Usar ≈ 578 K (teórico, 1 atm) y citar la fuente. Con 550 K, el umbral de "ebullición explosiva" queda ~30–45 K por debajo. |
| C207-06 | CAT-207:170 | "cociente riguroso de intensidades **integradas**" | CONTRADICHO | MEDIA | `raman_analyzer.py:1625-1635`: usa `np.interp` en los cursores A y B (alturas puntuales) | Documentar que se usan alturas o pasar a áreas ajustadas. |
| C207-07 | CAT-207:120-127 | Rayos cósmicos: "filtro Laplaciano"; σ_MAD = 1.4826·MAD; k = 5.0; reemplazo por "interpolación cúbica" | CONTRADICHO (parcial) | MEDIA | `raman_engine.py:211-245`: residuo respecto de una mediana móvil (w = 5); 0.6745 = 1/1.4826 ✓; umbral por defecto 6.0; reemplazo por mediana local; sin Laplaciano ni interpolación cúbica. Umbrales efectivos: 5.5 (`raman_analyzer.py:1368`) y 5.0 (`multi_spectrum_widget.py:1497`) | Describir el algoritmo real y unificar o documentar los tres umbrales. |
| C207-08 | CAT-207:145-147 | Pseudo-Voigt A[η·L + (1−η)·G] con FWHM común | CONFIRMADO (código) | — | `raman_engine.py:602-620`: la forma algebraica coincide (normalizada por altura) | — |
| C207-09 | CAT-207:145-147 | "La Integral de Voigt carece de forma analítica cerrada"; pseudo-Voigt "Aproximación Analítica Óptima"; "η … cuantifica el grado de amortiguamiento homogéneo" | CONTRADICHO (parcial) | MEDIA | Ida, Ando y Toraya, *J. Appl. Cryst.* 33, 1311 (2000) (reimpresión del autor): el Voigt se expresa con la función de error compleja w(z) (Faddeeva); el pseudo-Voigt con FWHM común se desvía hasta 0.77 % de la altura. Thompson, Cox y Hastings (1987): η = 1.36603(f_L/f) − 0.47719(f_L/f)² + 0.11116(f_L/f)³, es decir, una relación no lineal. Documentación de Mantid, PseudoVoigt | η no es la fracción del ancho homogéneo. Para separar el ensanchamiento homogéneo del inhomogéneo, ajustar un Voigt (`scipy.special.voigt_profile`) o convertir η con TCH. |
| C207-10 | CAT-207:137-142 | Gaussiana y Lorentziana normalizadas por área (A = área) | CONTRADICHO (parametrización) | BAJA | `raman_engine.py:602-611`: normalizadas por altura, con la FWHM como parámetro; el área se calcula aparte (`:670, :681`, fórmulas correctas) | Aclarar que `amplitude` es la altura. |
| C207-11 | CAT-207:26, 149-152 | BWF "implementado en `core/raman_engine.py`" | CONTRADICHO | MEDIA | Sin BWF ni Fano en `raman_engine.py`; sólo existe `model_fano` en `core/sif_processor.py:1457` (LSPR) | Quitar BWF del motor Raman o implementarlo. La forma (1+ε/q)²/(1+ε²) es correcta si Γ es la HWHM. |
| C207-12 | CAT-207:26, 195-200 | MCR-ALS/NNLS en el pipeline "implementado" | CONTRADICHO | MEDIA | No hay MCR ni NNLS en ningún `.py` versionado | Marcarlo como trabajo futuro. |
| C207-13 | CAT-207:76, 208 | "p = 10⁻³ a 10⁻⁴"; tabla p ∈ [10⁻⁴, 10⁻²]; λ = 10⁴–10⁷ | CONTRADICHO (parcial: p) / CONFIRMADO (λ) | BAJA | Baek, Park, Ahn y Choo, *Analyst* 140, 250 (2015), DOI 10.1039/C4AN01061B: "The asymmetry parameter p is recommended to set between 0.001 and 0.1", con λ recorrido de 10² a 10⁸ y citando a Eilers y Boelens (2005) y a Eilers (2003). Los paquetes R `baseline` y `alkahest` dan 10² ≤ λ ≤ 10⁹ | p = 10⁻⁴ queda fuera del rango recomendado. Usar 10⁻³ ≤ p ≤ 10⁻¹. |
| C207-14 | CAT-207:26 | "sistema disperso **tridiagonal** … factorización de **Cholesky**" | CONTRADICHO (menor) | BAJA | `raman_engine.py:309-316`: W + λDᵀD es pentadiagonal; `spsolve` usa SuperLU (LU) | "Pentadiagonal, LU disperso". |
| C207-15 | CAT-207:82 | "D … matriz penta-diagonal" | CONTRADICHO (menor) | BAJA | D tiene tres diagonales no nulas; la pentadiagonal es DᵀD | Corregir. |
| C207-16 | CAT-207:99 | Convergencia "max \|Δw\| < tol" | CONTRADICHO (menor) | BAJA | `raman_engine.py:320`: ‖Δw‖₂/‖w‖₂ < 10⁻⁴, con máximo 20 iteraciones | Documentar el criterio real. |
| C207-17 | CAT-207:105 | "< 15 ms para N = 2048" | CONTRADICHO (marginal; depende de la máquina) | BAJA | Prueba propia: mediana de 17.8 ms con N = 2048 y 11.8 ms con N = 1004 (el detector real tiene 1004 px) | Informar el tiempo medido con N = 1004 y la máquina en que se midió. |
| C207-18 | CAT-207:110 | Pesos de AirPLS exp(k(yᵢ − zᵢ)/\|d\|), con exponente negativo | CONTRADICHO | BAJA | Documentación de pybaselines (Whittaker): "the absolute value within the weighting was mistakenly omitted in the original publication, as specified by the author"; código del autor (github.com/zmzhang/airPLS, `airPLS.py`): `w[d<0]=np.exp(i*np.abs(d[d<0])/dssn)`; coincide con `raman_engine.py:358` | Usar exp(t\|yᵢ − zᵢ\|/\|d\|), como SYS-306. Además: el código usa otro criterio de parada (el autor usa dssn < 0.001·Σ\|x\|) y no trata los pesos de los extremos. |
| C207-19 | CAT-207:118 | Rayos cósmicos con "FWHM ≤ 1.5 canales" | SIN FUENTE | BAJA | — | Citar o medir; en espectros FVB, un evento puede ocupar varios canales. |
| C207-20 | CAT-207:158 | Banda del Si a 520.7 cm⁻¹ | CONFIRMADO (dentro de la incertidumbre; valor no óptimo) | BAJA | Itoh y Shirono, NMIJ CRM 5606-a: 520.45 ± 0.28 cm⁻¹ (resumen en ResearchGate); borrador CEN CWA1 (2024): "silicon peak at 520.45 cm-1"; Itoh, *J. Raman Spectrosc.* (2024), DOI 10.1002/jrs.6630 (varía según oblea, dopaje y orientación); coeficiente térmico ≈ −0.022 cm⁻¹/K. El Si no figura en ASTM E1840 | Usar 520.45 ± 0.28 cm⁻¹ (k = 2) a temperatura ambiente e indicar la dependencia térmica. |
| C207-21 | CAT-207:209 | "Calibración Espectral 400 - 900 nm (0 - 4000 cm⁻¹), Polinomio de grado 3 (Hg/Ar), u_c(Δω) = ±0.35 cm⁻¹" | CONTRADICHO | ALTA | Tesis Martínez (líneas 2198-2200 de `martinez.txt`): calibración del fabricante más un offset verificado "con la incidencia de dos láseres", y "resolución … 1 nm" (≈ 34 cm⁻¹ a 545 nm). DEC-033: ventana de 103 / 11.6 nm, no de 400–900 nm. `calibration_dock.py` no tiene ninguna lámpara Hg/Ar; `fit_polynomial.py` ajusta la LSPR, no el eje. Además, 0–4000 cm⁻¹ con 532 nm corresponde a 532–679 nm y con 808 nm a 808–1204 nm | Describir la calibración real (SDK del Shamrock más offset, o el protocolo SYS-303 si existe). Estimar u_c en cm⁻¹ con los residuos medidos; ±0.35 cm⁻¹ equivale a ~1/10 de píxel con la red de 150 l/mm y no está respaldado. |
| C207-22 | CAT-207:208, 210 | "δA_band/A < 1.8 %"; ajuste pseudo-Voigt "δω₀ = ±0.08 cm⁻¹" | SIN FUENTE | MEDIA | `fit_peak_profile` (`raman_engine.py:663-691`) descarta `pcov` (`popt, _ = curve_fit(...)`), así que el código no calcula ninguna incertidumbre de ω₀ | Propagar `pcov` (√diag, escalado por χ²_red) y documentar la incertidumbre por espectro en lugar de un número fijo. |
| C207-23 | CAT-207:190-193 | PCA en `compute_spectral_pca`, X = T Pᵀ + E | CONFIRMADO | — | `raman_engine.py:1153-1182` | — |
| C207-24 | CAT-207:217 | Eilers y Boelens (2005), "Leiden University Medical Centre Report, 1(1), 5" | CITA ERRÓNEA (parcial) | BAJA | Baek et al. 2015 (ref. 14) la cita como manuscrito web de 2005; en ResearchGate figura como informe o preprint del 21 de octubre de 2005 | Citarla como manuscrito no publicado (Leiden University Medical Centre, 21 de octubre de 2005). El "1(1), 5" es espurio. |
| C207-25 | CAT-207:218 | Zhang, Chen y Liang (2010), *Analyst* 135(5), 1138–1146, DOI 10.1039/B922045C | CONFIRMADO | — | pubs.rsc.org (artículo b922045c); Semantic Scholar | — |
| C207-26 | CAT-207:219 | Le Ru y Etchegoin (2008), Elsevier, ISBN 978-0-444-53385-2 | CITA ERRÓNEA | BAJA | ScienceDirect (libro 9780444527790); AbeBooks: Elsevier 2009, ISBN 978-0-444-52779-0 | Corregir el año (2009) y el ISBN. |
| C207-27 | CAT-207:220 | Baffou (2020), *Thermoplasmonics*, CUP, DOI 10.1017/9781108289801 | CITA ERRÓNEA (año) | BAJA | Cambridge Core / Google Books: CUP, octubre de 2017; ISBN en línea 9781108289801 | Año 2017. |
| C207-28 | CAT-207:221 | Tauler (1995), *Chemom. Intell. Lab. Syst.* 30(1), 133–146 | CONFIRMADO | — | ScienceDirect (PII 016974399500047X), DOI 10.1016/0169-7439(95)00047-X | Agregar el DOI. |

---

## CAT-250 — Marco unificado de espectroscopía, SERS y quimiometría

`reportes/cientificos/CAT-250_Marco_Unificado_Espectroscopia_Optica_SERS_y_Quimiometria.md`

| ID | Documento:línea | Afirmación | Veredicto | Severidad | Fuentes | Corrección propuesta |
|---|---|---|---|---|---|---|
| C250-01 | CAT-250:27 | Pseudo-Voigt / **BWF** y **MCR-ALS** "implementado en `core/raman_engine.py`" | CONTRADICHO | MEDIA | No hay BWF ni MCR en `raman_engine.py` (ver C207-11 y C207-12); el Fano de `sif_processor.py:1457` es para LSPR | Listar sólo lo implementado: Gauss, Lorentz, pseudo-Voigt, PCA. |
| C250-02 | CAT-250:27 | AsLS = "splines penalizados asimétricos" | CONTRADICHO (menor) | BAJA | Eilers, *Anal. Chem.* 75, 3631 (2003): el suavizador de Whittaker usa mínimos cuadrados penalizados por diferencias, no una base de splines; Baek et al. 2015, ec. (5) | "Mínimos cuadrados penalizados asimétricos (suavizador de Whittaker)". |
| C250-03 | CAT-250:33 | "uno de cada 10⁷ fotones **incidentes**" intercambia un cuanto vibracional | CONTRADICHO (formulación) | BAJA | La cifra de ~1 en 10⁷ que circula en textos de divulgación (Wikipedia, DoITPoMS; no son fuentes primarias) se refiere a fotones **dispersados**. La fracción de fotones incidentes es N·σ·L y depende de la muestra: para una monocapa, con σ ~ 10⁻²⁹ cm² (Le Ru 2007), es ≪ 10⁻⁷ | "~1 de cada 10⁶–10⁸ fotones **dispersados**", o dar N·σ·L. |
| C250-04 | CAT-250:35-41 | Desarrollo de la polarizabilidad α(t)E(t) → bandas ω_L ± Ω | CONFIRMADO | — | Identidad trigonométrica estándar (cos a·cos b = ½[cos(a−b) + cos(a+b)]) | — |
| C250-05 | CAT-250:63-72 | Pipeline: calibración → rayos cósmicos ("Laplaciano") → AsLS → deconvolución → PCA / termometría | CONFIRMADO (orden) / CONTRADICHO (Laplaciano) | BAJA | `raman_analyzer.py:1216-1307`: recorte → despike por mediana → suavizado → línea base → corrección | Quitar "Laplaciano" y agregar la etapa de suavizado. |
| C250-06 | CAT-250:27 | Shamrock 500i = espectrómetro Czerny-Turner | CONFIRMADO | — | `docs/bibliografia/andor-shamrock-500-specifications.pdf` ("Czerny-Turner Spectrographs", "500 mm focal length") | — |
| C250-07 | CAT-250:96 | Raman y Krishnan (1928), *Nature* 121(3048), 501–502, DOI **10.1038/121501a0** | CITA ERRÓNEA (DOI) | BAJA | nature.com/articles/121501c0; ADS 1928Natur.121..501R; mindat (ref. 2141867): DOI 10.1038/121501c0 | DOI 10.1038/121501c0. |
| C250-08 | CAT-250:97 | Moskovits (1985), *Rev. Mod. Phys.* 57, 783–826, DOI 10.1103/RevModPhys.57.783 | CONFIRMADO | — | Resultados bibliográficos coincidentes (ACS "Celebrating 50 Years of SERS", 2024) | — |
| C250-09 | CAT-250:98 | Eilers (2003), *Anal. Chem.* 75(14), 3631–3636, DOI 10.1021/ac034100m | CONFIRMADO | — | Baek et al. 2015, ref. 16 (*Anal. Chem.* 2003, 75, 3631-3636) | — |
| C250-10 | CAT-250:12 | Módulos `raman_analyzer.py`, `sif_analyzer.py`, `pyspectrum.py` | CONFIRMADO | — | Existen en la raíz del repo; además, `analysis/raman_analyzer.py` | — |

---

## SYS-306 — Arquitectura del motor Raman y quimiometría multiespectral

`reportes/sistema/SYS-306_Arquitectura_Motor_Raman_y_Quimiometria_Multiespectral.md`

| ID | Documento:línea | Afirmación | Veredicto | Severidad | Fuentes | Corrección propuesta |
|---|---|---|---|---|---|---|
| S306-01 | SYS-306:57 | "Termometría Anti-Stokes/Stokes" en el análisis individual | CONTRADICHO (heredado) | CRÍTICA (se cuenta en C207-01/02; no se suma aquí) | Ver C207-01, C207-02, C207-03 | Remitir a la corrección de C207. |
| S306-02 | SYS-306:95 | Reemplazo por mediana "preservando intacto el ancho y área de los picos Raman físicos reales" | CONTRADICHO (condicional) | MEDIA | Prueba propia (`l6_tests.py`): con umbrales de 6.0, 5.5 y 5.0, los picos genuinos de alta SNR con FWHM de 1.5–4 px pierden entre el 10 % y el 80 % del área; con FWHM de 6 px, menos del 6 %. Con 150 l/mm y 1 nm de resolución (≈ 10 px), el riesgo es bajo; con rendijas angostas, alto | Advertir que el filtro erosiona bandas angostas cuya FWHM sea ≤ ~4 px. Excluir las regiones de picos conocidos o usar despike temporal (varios cuadros). |
| S306-03 | SYS-306:87-94 | Z modificado con MAD (0.6745), w = 5, umbral por defecto 6.0, condición d > 0, reemplazo por mediana | CONFIRMADO (motor) | BAJA (nota) | `raman_engine.py:211-245`; la GUI usa 5.5 (`raman_analyzer.py:1368`) y 5.0 (`multi_spectrum_widget.py:1497`) | Documentar los umbrales efectivos de la GUI. |
| S306-04 | SYS-306:32 | "cinco algoritmos … (AsLS, AirPLS, ModPoly, Rolling Ball, Splines)" | CONTRADICHO (menor) | BAJA | `raman_engine.py:298-460`: seis, contando `baseline_derivative` | Listar los seis. |
| S306-05 | SYS-306:43, 8 | `parse_andor_solis_file`: "Tolerancia a separador decimal (, y .)" | CONFIRMADO (parcial) | BAJA | Prueba propia: funciona con tabulación o espacio más decimal coma; falla con CSV delimitados por coma o por punto y coma (ver M11-03) | Aclarar que sólo tolera la coma decimal cuando el delimitador es espacio o tabulación. |
| S306-06 | SYS-306:52 | "ModPoly (Lieber 2003)" | CONFIRMADO | — | Lieber y Mahadevan-Jansen, *Appl. Spectrosc.* 57(11), 1363–1367 (2003), DOI 10.1366/000370203322554518; `raman_engine.py:368-395` coincide | — |
| S306-07 | SYS-306:79 | E = Δν̃ × 1.23984193×10⁻⁴ eV | CONFIRMADO | — | hc = 1.239841984×10⁻⁶ eV·m (CODATA); `raman_engine.py:36` | — |
| S306-08 | SYS-306:108 | CSC + `spsolve` | CONFIRMADO | — | `raman_engine.py:309-316` | — |
| S306-09 | SYS-306:111-112 | AirPLS: w = 0 si y ≥ z; w = exp(t\|y − z\|/\|d_neg\|₁) si y < z | CONFIRMADO | — | Código del autor (`zmzhang/airPLS.py`); nota de pybaselines; `raman_engine.py:351-359` | — |
| S306-10 | SYS-306:113 | "garantizando una línea base que jamás erosione picos estrechos ni mesetas anchas" | CONTRADICHO | BAJA | Baek et al. 2015: "AsLS and airPLS methods give a boosted baseline corrected spectrum, when a spectrum is corrupted with additive noise" | Quitar "jamás"; mencionar el sesgo con ruido y la alternativa arPLS. |
| S306-11 | SYS-306:120 | Grilla común sobre la "intersección o unión", con "interpolación lineal o cúbica" | CONTRADICHO | MEDIA | `raman_engine.py:990-1016`: usa la intersección y, **sólo si no hay solapamiento**, la unión con `np.interp` (extrapolación constante en los bordes); siempre interpolación lineal | Documentarlo y advertir que, sin solapamiento, se inventan tramos planos que contaminan PCA y el promedio. Conviene bloquear ese caso. |
| S306-12 | SYS-306:134, 137 | λ_k = σ_k²/(N − 1); scores T = UΣ | CONFIRMADO | — | `raman_engine.py:1168-1175`: el porcentaje explicado sale de σ_k²/Σσ²; scores = U·S | — |
| S306-13 | SYS-306:148 | "permitiendo graficar la constante de velocidad fototérmica k_reac directamente en la interfaz" | CONTRADICHO | BAJA | `extract_band_kinetics` (`raman_engine.py:1109-1150`) sólo devuelve alturas, áreas y posiciones; no hay `curve_fit` en `multi_spectrum_widget.py` | Quitar la mención o implementar el ajuste cinético con incertidumbre. |

---

## MOD-11 — Raman Analyzer Suite (manual de usuario)

`docs/modulos/MOD-11_Raman_Analyzer_Suite_Quimiometria.md`

| ID | Documento:línea | Afirmación | Veredicto | Severidad | Fuentes | Corrección propuesta |
|---|---|---|---|---|---|---|
| M11-01 | MOD-11:247 | Saturación del CCD a "I ≥ 65535 cuentas" / "meseta horizontal plana a 65535 ADU" | CONTRADICHO | ALTA | `docs/bibliografia/Andor_iXon3_885_Specifications.pdf`: "Digitization … 14 bit @ 35, 27 & 13 MHz readout rate", o sea, un máximo de 16383 cuentas por lectura; pozos de 32 000 e⁻ (activo) y 80 000 e⁻ (registro de ganancia). No hay detección de saturación en `pyspectrum/` | El operador buscaría una meseta en 65535 que nunca aparece: la saturación está en ≤ 16383 cuentas (o antes, por el pozo con ganancia EM). Corregir el valor y agregar un aviso automático de saturación. |
| M11-02 | MOD-11:35 | Hardware "Andor Shamrock SR-303i y cámaras CCD/EMCCD Andor Newton/Idon" | CONTRADICHO | MEDIA | `lab-invariants.md` §3 (iXon3 885, DEC-033); tesis Martínez, líneas 2177-2178 ("Shamrock 500i", "Andor Ixon EM+ 885") | Shamrock 500i con iXon3 885. El 65535 de M11-01 corresponde a esas cámaras de 16 bits, no a la del laboratorio. |
| M11-03 | MOD-11:40 | "Detección automática de delimitadores (tabulaciones, comas, punto y coma, espacios)" | CONTRADICHO | MEDIA | Prueba propia: `parse_andor_solis_file` falla con `ValueError` en `532.10,100.5`, `532.10, 100.5`, `532.10;100.5` y `532,10;100,5`; el código reemplaza "," por "." y divide sólo por espacios (`raman_engine.py:118-119, 147-148`) | Implementar la detección (por ejemplo con `csv.Sniffer`) o documentar que sólo acepta espacio o tabulación. |
| M11-04 | MOD-11:64 | AsLS: p ≈ 0.001–0.01; λ ≈ 10⁴–10⁷ | CONFIRMADO | — | Baek et al. 2015 (p entre 0.001 y 0.1; λ de 10² a 10⁸ o 10⁹) | — |
| M11-05 | MOD-11:248 | "Reducir … p a 10⁻³ o 10⁻⁴" | CONTRADICHO (parcial) | BAJA | Baek et al. 2015: p recomendado ≥ 0.001 | Recomendar p en [10⁻³, 10⁻²]. |
| M11-06 | MOD-11:180 | Rango de p en la GUI: "10⁻⁴ – 0.5" | CONTRADICHO | BAJA | `multi_spectrum_widget.py:416` (`setRange(0.0001, 0.1)`) | 10⁻⁴ – 0.1. |
| M11-07 | MOD-11:180-183 | λ 10²–10⁹; ModPoly 1–8; Rolling Ball 5–500 pts | CONFIRMADO | — | `multi_spectrum_widget.py:409, 424, 431` | — |
| M11-08 | MOD-11:66 | AirPLS "a partir del error cuadrático medio" | CONTRADICHO | BAJA | `raman_engine.py:351-358`: norma L1 de los residuos negativos (Zhang 2010; código del autor) | Corregir. |
| M11-09 | MOD-11:71 | "Tercera Derivada … & Spline Cúbico" | CONTRADICHO (menor) | BAJA | `raman_engine.py:424, 460`: `np.interp`, es decir, interpolación lineal | "Interpolación lineal". |
| M11-10 | MOD-11:76 | FFT pasa-bajos con "corte gaussiana o Fermi-Dirac" | CONTRADICHO | BAJA | `raman_engine.py:493`: rampa de coseno elevado | Corregir. |
| M11-11 | MOD-11:78-80 | Despike por "derivada discreta" Z = \|Δyᵢ − med(Δy)\|/MAD, con interpolación "suave" | CONTRADICHO | BAJA | `raman_engine.py:228-243`: residuo respecto de una mediana móvil, z modificado de un solo lado y reemplazo por la mediana | Describir el algoritmo real (como SYS-306 §3.2). |
| M11-12 | MOD-11:85-86 | Lorentziana (A/π)(γ/2)/(…), normalizada por área | CONTRADICHO (parametrización) | BAJA | `raman_engine.py:608-611`: normalizada por altura | Ver C207-10. |
| M11-13 | MOD-11:117 | Límite de recorte por defecto "[150.0 - 3200]" | CONTRADICHO | BAJA | `multi_spectrum_widget.py:301, 309` (0.0–4000.0) | Actualizar el diagrama. |
| M11-14 | MOD-11:138-142 | Presets de láser 532 / 632.8 / 637 / 785 / 592 nm | CONFIRMADO (código) / incompleto | BAJA | `multi_spectrum_widget.py:217-222, 1069`; la línea IR real del laboratorio es de 808 nm (`config.py:65`) y no figura entre los presets | Agregar el preset de 808 nm (y 640 nm). |
| M11-15 | MOD-11:147, 152 | E = Δν̃·1.239841984×10⁻⁴ eV; 150 cm⁻¹ ≈ 536.3 nm (con láser de 532 nm) ≈ 0.0186 eV | CONFIRMADO | — | Cálculo propio: 1/(1/532 − 1.5×10⁻⁵) = 536.28 nm; 150 × 1.23984×10⁻⁴ = 0.01860 eV | — |
| M11-16 | MOD-11:188 | "modo de estiramiento del sustrato a 1078 cm⁻¹" | CONTRADICHO | BAJA | Espectros SERS de 4-MBA: ~1074–1084 cm⁻¹ = respiración del anillo ν12 + ν(C–S) de la **molécula sonda** (*Spectrochim. Acta A*, estudio DFT del 4-MBA, PubMed 25913136; *Nanomaterials* 15, 421, 2025); `RAMAN_REFERENCE_STANDARDS` en `raman_engine.py:45-46` | "Modo de respiración del anillo del 4-MBA (ν12 + ν(C–S))". |
| M11-17 | MOD-11:189 | Área unitaria ∫Y dν = 1 | CONTRADICHO (menor) | BAJA | `raman_engine.py:1075`: ∫\|Y\| | Documentar el uso de \|Y\|. |
| M11-18 | MOD-11:190 | SNV "escalado por la varianza" | CONTRADICHO (texto) | BAJA | `raman_engine.py:1084` (desviación estándar); la fórmula del propio documento usa s | "por la desviación estándar". |
| M11-19 | MOD-11:249 | Excepción `DimensionMismatch`; se requiere "≥ 80 % de solapamiento" | SIN FUENTE / CONTRADICHO | BAJA | No existe esa excepción en el código; sin solapamiento, el motor extrapola de forma constante (ver S306-11) | Documentar el comportamiento real y justificar o quitar el 80 %. |
| M11-20 | MOD-11:126, 131 | Valores por defecto AsLS λ = 1e5 y pico de referencia 1078.0 | CONFIRMADO | — | `raman_engine.py:298`; `multi_spectrum_widget.py:109, 493` | — |
| M11-21 | MOD-11:39 | "~50 líneas" de encabezado de Solis | SIN FUENTE | BAJA | `raman_engine.py:111-129` detecta el inicio de los datos sin asumir un número de líneas | Quitar el número. |

---

## Afirmaciones que requieren banco

1. **Registro espacial del mapa (C205-01).** Después de corregir el código (esperar on-target, adquisición disparada y espera de la exposición), medir el asentamiento real de la platina controlada por el E-517 para los pasos usados, y validar con una muestra de posiciones conocidas (grilla impresa) que el espectro de (x, y) corresponde a ese nodo. Antes de la corrección, un mapa de prueba con exposición ≥ 100 ms debería mostrar espectros repetidos o corridos entre nodos.
2. **Nivel de saturación del iXon3 885 (M11-01).** Adquirir un cuadro deliberadamente saturado en el modo de lectura y la ganancia usados, y registrar la cuenta máxima. La hoja de datos predice ≤ 16383; confirmar también el límite por pozo con ganancia EM.
3. **FWHM instrumental en píxeles (S306-02).** Medir el ancho de una línea atómica o de la línea láser, para cada rendija y red, y así saber si el despike por mediana (w = 5) erosiona bandas reales.
4. **Respuesta espectral y termometría (C207-01/02/03).** Medir la curva de respuesta (lámpara halógena calibrada) a través de los filtros notch en las longitudes de onda Stokes y anti-Stokes. Validar el método con exponente 3 y corrección de respuesta sobre una referencia de temperatura conocida (Si a temperatura ambiente, o una platina calefaccionada). Para hot spots SERS, estimar el factor de asimetría A.
5. **Incertidumbre de la calibración del eje (C207-21/22).** Medir los residuos de la calibración real (SDK más offset) con una fuente de líneas o con patrones ASTM E1840 (ciclohexano, poliestireno) y con Si (520.45 cm⁻¹), para ambas redes. Recién entonces fijar u_c en cm⁻¹.
6. **Velocidad y asentamiento de la platina (C205-07).** Medir la respuesta de la platina para decidir si 200 µm/s o 35 ms tienen algún sentido.

## Documentos sin hallazgos relevantes

Ninguno. Los cinco documentos del lote tienen al menos un hallazgo de severidad MEDIA o superior. Las afirmaciones confirmadas son sobre todo las fórmulas de conversión, AsLS en forma matricial, la PCA por SVD, el perfil pseudo-Voigt, \|E\|⁴ y las referencias de Zhang, Tauler, Moskovits, Eilers (2003) y Lieber.

## Observaciones de código fuera del lote (para el orquestador)

- `core/raman_engine.py:41-42`: describe el Si 520.7 como "estándar internacional de calibración". No figura en ASTM E1840; el valor certificado es 520.45 ± 0.28 cm⁻¹ (NMIJ CRM 5606-a).
- `core/raman_engine.py:663, 685`: `fit_peak_profile` descarta `pcov`, así que ningún ajuste de pico informa incertidumbre.
- `pyspectrum/drivers/andor_ccd_driver.py:520-532`: `get_most_recent_image` hace `reshape` fijo a (1002, 1004). En modo FVB (una sola fila) la forma no coincide, y si la llamada falla devuelve ceros en silencio. No se verificó en el banco.
