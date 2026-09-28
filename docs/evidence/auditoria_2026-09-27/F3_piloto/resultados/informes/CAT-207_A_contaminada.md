# CAT-207 corrida A — veredictos (transcripción compacta del handback del agente a28a23b9a899596ea)

**Validez:** CONTAMINADA para M8. El agente declaró que al reanudar encontró en el scratchpad un
`informe_CAT-207.md` de 37 filas "de la sesión previa", lo conservó y le aplicó una sola mejora
propia (fila 26). Ese archivo lo compartía con la corrida B, que escribió primero, así que las
dos corridas no son independientes. check-report: exit 0. M10: repo intacto. Las filas 32 y 33
vienen del archivo compartido y el agente no las reverificó en esta corrida.

| # | Ubicación | Afirmación (breve) | Veredicto | Sev. |
| :-- | :-- | :-- | :-- | :-- |
| 1 | :11 | Estado Producción/Consolidado | CONTRADICHO | MEDIA |
| 2 | :12 | Módulos asociados existen | RESPALDADO | — |
| 3 | :26 | Cholesky / tridiagonal (real: spsolve, pentadiagonal) | CONTRADICHO | MEDIA |
| 4 | :26 | Pseudo-Voigt y BWF (BWF no existe) | RESPALDADO·CONTRADICHO | ALTA |
| 5 | :26 | PCA y MCR-ALS (MCR-ALS no existe) | RESPALDADO·CONTRADICHO | ALTA |
| 6 | :70 | Funcional AsLS con pesos p/1−p | RESPALDADO | — |
| 7 | :105 | O(N), <15 ms, N=2048 | SIN FUENTE | MEDIA |
| 8 | :105 | W+λDᵀD pentadiagonal | RESPALDADO | — |
| 9 | :110 | Pesos AirPLS (Zhang 2010); el código usa el signo opuesto | RESPALDADO (+ nota de bug) | — |
| 10 | :118 | FWHM de rayo cósmico ≤1.5 canales | SIN FUENTE | BAJA |
| 11 | :120 | "Filtro Laplaciano" (real: Z-score por MAD) | RESPALDADO·CONTRADICHO | MEDIA |
| 12 | :121 | Mediana móvil w=5 | RESPALDADO | — |
| 13 | :124 | σ_MAD=1.4826·MAD | RESPALDADO | — |
| 14 | :126 | k_sigma=5.0 (código: 6.0) | CONTRADICHO | ALTA |
| 15 | :127 | Interpolación cúbica (código: mediana local) | CONTRADICHO | ALTA |
| 16 | :138 | FWHM_G=2.3548σ | RESPALDADO | — |
| 17 | :142 | FWHM_L=γ | RESPALDADO | — |
| 18 | :146 | Fórmula pseudo-Voigt | RESPALDADO | — |
| 19 | :151 | Perfil BWF implementado | CONTRADICHO | ALTA |
| 20 | :158 | Si 520.7 cm⁻¹ | RESPALDADO | — |
| 21 | :167 | Stokes/anti-Stokes ∝ n(Ω), exponente 4 | RESPALDADO | — |
| 22 | :176 | Fórmula de T_nano | RESPALDADO | — |
| 23 | :179 | Corrección por QE del CCD y notch (no existe) | CONTRADICHO | ALTA |
| 24 | :180 | u(T)=±4.2 K (no se calcula) | CONTRADICHO | ALTA |
| 25 | :180 | T_b≈373 K | RESPALDADO | — |
| 26 | :180 | T_spinodal≈550 K (G17 p.97: 594 K) | CONTRADICHO | ALTA |
| 27 | :187 | Despliegue del hipercubo X∈R^(M×P) | RESPALDADO | — |
| 28 | :191 | PCA en compute_spectral_pca | RESPALDADO | — |
| 29 | :197 | MCR-ALS/NNLS | CONTRADICHO | ALTA |
| 30 | :208 | δA/A<1.8 % (k=2) | SIN FUENTE | MEDIA |
| 31 | :209 | 400–900 nm (0–4000 cm⁻¹) | RESPALDADO (+ nota nm↔cm⁻¹) | — |
| 32 | :209 | Polinomio grado 3 (sí) con Hg/Ar (no: láser 532, R2-10) | RESPALDADO·CONTRADICHO | MEDIA |
| 33 | :209 | u_c(Δω)=±0.35 cm⁻¹ | SIN FUENTE | MEDIA |
| 34 | :210 | δω0=±0.08 cm⁻¹ | SIN FUENTE | MEDIA |
| 35 | :211 | U(T)=±8.4 K | SIN FUENTE | MEDIA |
| 36 | :218 | DOI de Zhang 2010 | RESPALDADO | — |
| 37 | :220 | Baffou 2020 (Crossref: 2017) | RESPALDADO·CONTRADICHO | BAJA |

Resumen del agente: 17 R · 0 D · 0 E · 6 SF · 14 C · 0 EAV. Sin CRÍTICAS (fila 24 en el límite).
M9 (acumulado de las corridas, incluida la reanudación): sin registro separado; lo da la notificación final.
