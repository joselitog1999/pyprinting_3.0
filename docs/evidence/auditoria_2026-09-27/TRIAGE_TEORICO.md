# Triage teórico contra la bibliografía cargada (paso 1 del orden de consulta)

**Fecha:** 2026-09-27. **Revisor:** subagente revisor científico (sólo lectura del repositorio; único archivo escrito: éste).
**Insumos:** `CONSOLIDADO.md` y `RESPUESTAS_INVESTIGADOR.md` de esta carpeta (las respuestas prevalecen); los PDFs de `docs/bibliografia/`, leídos por extracción de texto (`pdftotext`) y confirmados con Read sobre el PDF en las citas que deciden un veredicto.
**Orden de consulta fijado por el investigador:** (1) bibliografía cargada → (2) investigador → (3) web. Este documento cubre sólo (1). La web no se usó.

**Convención de páginas.** "p. N" es la página **física del PDF** (la que muestra el visor), no el folio impreso, salvo que se indique "folio". Las citas textuales van entre comillas y en el idioma del original.

**Veredictos.** RESUELTO POR BIBLIOGRAFÍA (a favor del valor indicado) · PARCIAL (la bibliografía acota o resuelve una parte) · NO CUBIERTO (la bibliografía cargada no lo trata).

**Estado:** COMPLETO (2026-09-27). 26 ítems (T-01…T-26) y hallazgos colaterales al final. Se extrajo el texto de los 107 PDFs de `docs/bibliografia/` y se lo recorrió con búsquedas por término; quedaron fuera los dos `.docx` (el SI de Violi y el borrador de la tesis de Martínez, cuya versión PDF sí se usó). Las citas que deciden un veredicto se confirmaron sobre el PDF (Read con `pages`).

**Aviso de alcance.** Las tesis de Gargiulo (2017) y Martínez (2024) describen el microscopio de **CIBION**. Las únicas fuentes cargadas hechas en el banco de **INS-UNSAM** son Pereyra (Lic., 2025; impresión de redes) y Arias (Doc., 2025; un microscopio Raman distinto, de 785 nm). Donde un valor sólo proviene de CIBION, se lo indica.

## Tabla resumen

| ID | Tema | Veredicto | ¿Pregunta al investigador? |
|---|---|---|---|
| T-01 · C-12 / D-20 | Termometría anti-Stokes (ω³/ω⁴, η(λ), áreas, factor A en SERS, espinodal, PL del Au) | PARCIAL: (b), (d) y (f) resueltos; espinodal = 594 K; (a) y (c) no cubiertos | Sí |
| T-02 · D-31 / dec. 2 | Deriva a citar | PARCIAL: 30 nm/min medido con PyPrinting (Martínez §3.5), rango 5-50; "~1 nm/min" falso | Sí |
| T-03 · D-27 / S-4 / dec. 3 | Fuerza iónica y longitud de Debye | PARCIAL: la bibliografía da sólo 1.5 mM NaCl (κ⁻¹ ≈ 7.9-8 nm); 0.5 mM sin fuente | Sí |
| T-04 · S-4 / D-02 / D-03 / dec. 1 | Sustrato y limpieza | RESUELTO: Hellmanex + plasma + PDDA(/PSS), mismo signo; Piranha + APTES sólo en el protocolo SERS de Arias | Sí |
| T-05 · D-27 | Constante de Hamaker | RESUELTO: ≈ 2.1 × 10⁻²⁰ J (fórmula y parámetros de *ACS Nano* 2017) | No |
| T-06 · dec. 4 / D-19 / C-36 | Referencia del Si | NO CUBIERTO (el grupo calibra con láseres) | Sí |
| T-07 · D-33 / C-02 / dec. 6 | Convención honeycomb | RESUELTO: (⅓, ⅓) con γ = 60° (Guo *et al.*, *PRB* 2017); la base del código queda refutada | Sí |
| T-08 · S-5 / C-14 / D-36 / dec. 5a | Definición de ξ | NO CUBIERTO | Sí |
| T-09 · C-15 / D-35 / dec. 5b | Estimador de p | PARCIAL: el grupo cuenta ("eficiencia de impresión", Pereyra) | Sí |
| T-10 · D-37 / D-38 | Debye-Waller ½, (1−p)², paracristal, KTHNY, Friedel | NO CUBIERTO | Sí |
| T-11 · C-11 / D-34 | Inversión MC de σ | NO CUBIERTO (método en desarrollo); control externo: σ real ~ 35-65 nm | Sí |
| T-12 · D-23 / D-24 | Fuerzas, σ_abs, β, ΔT, τ | RESUELTO a favor de la auditoría | No |
| T-13 · D-25 / S-7 | Objetivo y cintura del haz | RESUELTO: agua NA 1.0 (LUMPLFLN60XW), w₀ ≈ 265-278 nm | Sí (20x: NA 0.50) |
| T-14 · D-26 | Unidad de Airy y pinhole | RESUELTO: AU en diámetro, 1.22λM/NA; confocal relajado (≈ 4.6 AU) | Sí |
| T-15 · D-28 | Burbujas y espinodal | PARCIAL: cota de 594 K; umbral de ~200 °C sin fuente cargada | Sí |
| T-16 · D-29 | Dímeros | PARCIAL: 300 nm en vidrio, sin efecto de la polarización; 0.2·D no cubierto | Sí |
| T-17 · D-30 / S-11 | "Sub-nanométrico" | RESUELTO: ≈ 50 nm RMS de impresión | No |
| T-18 · D-32 / S-9 | Citas | PARCIAL: tesis de Martínez (2024) y *ACS Photonics* 2019 (Zaza) fijados | Sí |
| T-19 · S-1 | Factores 2 de convención | PARCIAL: resueltos los ópticos, no los cristalográficos | Sí |
| T-20 · D-39 | Localización y GUM | NO CUBIERTO (salvo la forma del CRLB y RL → Picasso) | Sí |
| T-21 · C-17 | `Filtro (%)` del PSF | PARCIAL: el método del grupo no usa umbral | Sí |
| T-22 · C-23 / C-24 | Fotometría LoG | NO CUBIERTO | Sí |
| T-23 · C-40 | "Anisotropía" | NO CUBIERTO | Sí |
| T-24 · C-47 | Rayos cósmicos | NO CUBIERTO | Sí |
| T-25 · C-52 | ψ_n local frente a global | NO CUBIERTO | Sí |
| T-26 · D-40 / D-41 | Formatos e implementaciones | FUERA DE ALCANCE (no teórico) | No |

**Conteo:** RESUELTO 7 · PARCIAL 9 · NO CUBIERTO 9 · fuera de alcance 1 (26 ítems).

### Preguntas al investigador, por prioridad (una línea cada una)

1. **T-01:** ¿La termometría Raman S/AS debe calcularse siempre relativa a un espectro de referencia a T₀ conocida, lo que cancela ω³/ω⁴ y η(λ)? (sí/no)
2. **T-02:** ¿El banco de INS-UNSAM es el mismo microscopio (platina y montura) en el que Martínez midió 30 nm/min (§3.5)? (sí/no)
3. **T-03:** ¿El extremo de 0.5 mM corresponde a un protocolo local distinto del publicado (1.5 mM NaCl + Tween)? (sí/no; si sí, ¿cuál?)
4. **T-04:** ¿Piranha + APTES queda sólo para sustratos SERS por inmersión (Arias) y se elimina de todo documento de impresión? (sí/no)
5. **T-07:** ¿Hay muestras honeycomb, hBN, kagomé o dice impresas con el Diseñador de PyPrinting 3.0 que haya que re-validar? (sí/no)
6. **T-08:** ¿Se adopta ξ = 1/(π·FWHM_f), en frecuencia ordinaria y con resta del tamaño finito, como definición única? (sí/no)
7. **T-09:** ¿p se reporta por conteo, como 1 − (NP en sitios programados)/(sitios programados)? (sí/no)
8. **T-06:** ¿El Si será patrón de calibración del eje Raman, y no sólo verificación? (sí/no; si sí, pasar al paso 3 para el valor certificado)
9. **T-11:** ¿La validación de extremo a extremo del MC debe cubrir σ = 20-80 nm por componente? (sí/no)
10. **T-13:** ¿El objetivo de aire montado es el Olympus 20x con NA = 0.50, y no 0.40 como en el código? (sí/no)
11. **Colateral 1 (D-11):** ¿El láser verde del banco de INS-UNSAM es el Excelsior-532-150-CDRH que describe Pereyra (2025)? (sí/no)
12. **T-14:** ¿El canal confocal del banco conserva el pinhole de 50 µm con lente de 50 mm (≈ 4.6 AU)? (sí/no)
13. **T-15:** ¿Se incorpora Baffou *et al.* 2014 (*J. Phys. Chem. C* 118, 4890) y se adopta ~200 °C como umbral operativo de burbuja? (sí/no)
14. **T-21:** ¿`Filtro (%) = 0` como valor por defecto del PSF Analyzer y del confocal? (sí/no)
15. **T-19:** ¿Se crea en `lab-invariants` la tabla de convenciones ópticas (σ por componente, AU en diámetro, cintura a 1/e², r en amplitud)? (sí/no)
16. **T-18:** ¿La cita "Martínez *et al.*, *ACS Photonics* 2019" se reemplaza por Zaza *et al.*, *ACS Photonics* 6, 815 (2019)? (sí/no; si no corresponde, se elimina)
17. **T-16:** ¿Se incorpora Jain, Huang & El-Sayed, *Nano Lett.* 7, 2080 (2007), para fijar el decaimiento 0.2·D? (sí/no)
18. **T-10:** ¿La carpeta de Debye-Waller incluirá un texto de cristalografía (Warren o Guinier) para fijar exp(−G²σ²)? (sí/no)
19. **T-20:** ¿Se incorpora una referencia de CRLB para EMCCD con fondo (Mortensen 2010 o Rieger & Stallinga 2014)? (sí/no)
20. **T-22:** ¿Se retira el método LoG de la GUI hasta tener un test de extremo a extremo? (sí/no)
21. **T-23:** ¿El observable del Analizador SIF es el grado de polarización lineal P = (I∥−I⊥)/(I∥+I⊥)? (sí/no)
22. **T-24:** ¿Los rayos cósmicos se remueven por comparación entre adquisiciones repetidas, y no por mediana? (sí/no)
23. **T-25:** ¿Se reporta |⟨ψ_n⟩| global y se retiran las tablas de fase de CAT-313? (sí/no)

---

## Ítems

### T-01 · C-12 / D-20 — Termometría anti-Stokes (Raman S/AS y PL del Au)

**Qué afirma la documentación / el código.** `core/raman_engine.py:834-872` calcula T con I_AS/I_S = [(ν₀+ν)/(ν₀−ν)]⁴·exp(−hcν/k_BT), sin η(λ), sin notch, con alturas puntuales; SYS-301 §5.1 (l. 220-228) escribe la misma ecuación con ω⁴ y un término η(λ) que el código no tiene, y promete "±2 K"; SYS-301 §5.2 (l. 234-241) dice que la PL anti-Stokes del Au sigue una cola de **Fermi-Dirac** cuya pendiente da T "sin requerir parámetros instrumentales calibrados". El consolidado (D-20) propone: ω³ para cuentas, corrección de respuesta, áreas, factor A en SERS, espinodal ≈ 578 K y el modelo de Carattino (2018) para la PL del Au.

**Qué dice la bibliografía cargada**, sub-punto por sub-punto:

- **(a) ω⁴ frente a ω³ (prefactor de frecuencia).** Ningún texto cargado escribe el prefactor del cociente Raman S/AS. Lo que sí está es la vía que lo vuelve irrelevante: Martinez, Mina Villarreal, …, Violi, Gargiulo, *ACS Sens.* 9, 1049 (2024), `Articulos del grupo/2024 - thermometries-for-single-nanoparticles-heated-with-light.pdf`, p. 5-6 (folios 1053-1054): *"Because the anti-Stokes/Stokes ratio is proportional to a Boltzmann distribution, it is not necessary to calibrate it at the entire temperature range, and it is sufficient with a reference value taken at a known temperature."* Con una referencia R(T₀) medida con el mismo instrumento y el mismo modo, el prefactor (sea ω³ o ω⁴) y η(λ) se cancelan en R(T)/R(T₀) = exp[−(hcΩ/k_B)(1/T − 1/T₀)] (inferencia algebraica mía, no cita).
- **(b) Corrección de respuesta espectral.** Martínez, tesis doctoral, `Tesis del grupo/Tesis Luciana Martinez.pdf`, p. 88 (§4.2.3), sobre el método de cocientes de espectros anti-Stokes a la **misma** longitud de onda: *"Una segunda ventaja de hacer cocientes es que las mediciones se independizan de la transmisión óptica del instrumento de adquisición."* Es decir, el grupo evita η(λ) comparando la misma banda espectral a dos temperaturas. El cociente S/AS del código compara dos longitudes de onda distintas y no goza de esa cancelación: el defecto (b) queda respaldado.
- **(c) Áreas frente a alturas.** No cubierto: ninguna fuente cargada discute alturas contra áreas para el cociente S/AS.
- **(d) SERS: factor de asimetría.** *ACS Sens.* 2024, p. 6 (folio 1054): *"In this latter case, the anti-Stokes/Stokes ratio is convoluted with the wavelength dependent plasmonic enhancement, which may cause artifacts in the temperature calculation if it is not taken into account."* Y en el mismo párrafo: con bombeo vibracional, *"temperature calculations based on Boltzmann-distributed anti-Stokes signals deliver very high 'fictive temperatures'"*. Baffou, *ACS Nano* 15, 5785 (2021), `Termometria/baffou-2021-…pdf`, p. 6 (folio 5790): la termometría SERS con moléculas *"require[s] calibration, induce[s] instability, and yield[s] a temperature that is not necessarily the same as that of the nanoparticles"*.
- **Incertidumbre prometida (±2 K, ±4.2 K).** *ACS Sens.* 2024, p. 6: *"Anti-Stokes Raman cross sections are small, which limits the sensitivity of the method to about 10 °C."* Para la PL del Au, Martínez p. 94: el método hiperespectral *"recupera β con una precisión del 4 %"*.
- **(e) Espinodal del agua.** Gargiulo, tesis doctoral (2017), `Tesis del grupo/Julian_Gargiulo_2017.pdf`, p. 97 (folio 96): *"water can be superheated beyond the boiling point up to the spinodal decomposition temperature 594 °K in such small volumes"*. La bibliografía del grupo da **594 K**, no los 550 K de la documentación ni los ≈ 578 K que propuso la auditoría.
- **(f) PL anti-Stokes del Au.** Barella *et al.*, *ACS Nano* 15, 2458 (2021), `Articulos del grupo/2021 - In Situ Photothermal Response of Single Gold.pdf`, p. 3: *"n(T) is well described by a Bose−Einstein (BE) distribution"*; Martínez p. 85: el término FD *"sólo es necesario para describir la emisión anti-Stokes con cambios de energía superiores a 0,25 eV (2000 cm-1)"*. Baffou 2021, p. 6, Ec. 5: I(ω,T) = C·I_LPR(ω)·ρ·f(ħ(ω−ω_L),T), y *"I_LPR is highly wavelength dependent … and thus significantly distorts the original exponential-like temperature-dependent emission"*. El método del grupo es el de cocientes a varias irradiancias con T = T₀ + βI (Martínez Ecs. 4.6 y 4.11-4.12, p. 86-89; Barella 2021). Martínez p. 87 descarta el enfoque de Carattino para esferas: *"estas aproximaciones no son válidas para nanoesferas de Au"*.

**Veredicto.** **PARCIAL.**
- (b) y (d) quedan **resueltos a favor de la auditoría**: hace falta corregir la respuesta y tener en cuenta el realce plasmónico dependiente de λ.
- (e) queda **resuelto a favor de 594 K** (Gargiulo), ni 550 ni 578 K.
- (f) queda **resuelto a favor del método del grupo**, no del modelo de Carattino: BE y cocientes con T = T₀ + βI, y es falso que la pendiente dé T "sin parámetros". Lo que corresponde es el método de Barella 2021 / Martínez cap. 4.
- La incertidumbre prometida es falsa por bibliografía: la sensibilidad Raman S/AS ronda los 10 °C.
- (a) y (c) **no están cubiertos**. Existe una salida que los hace irrelevantes, la referencia a T₀ conocida, pero la bibliografía no decide qué convención de detección aplicar sin referencia.

**Pregunta al investigador.** ¿La termometría Raman S/AS de PySpectrum debe calcularse **siempre relativa a un espectro de referencia a T₀ conocida** (lo que cancela ω³/ω⁴ y η(λ)), sí/no? Si la respuesta es no, ¿se asume ω³ para cuentas de fotones?

### T-02 · D-31 / decisión 2 — Deriva mecánica a citar (5 frente a 30 nm/min)

**Qué afirma la documentación.** `lab-invariants.md:124` da 15-25 nm/min atribuidos a CAT-105/CAT-203, que no los respaldan. CLAUDE.md §6 y CAT-100:85 dan "~1 nm/min". El consolidado (V-36) propone citar 5 nm/min (Gargiulo) y 30 nm/min (Martínez §3.5).

**Qué dice la bibliografía cargada.**
- **Gargiulo 2017 (tesis), p. 65 (folio 64), §5.2:** *"errors due to mechanical drift of the microscope are negligible, because acquiring an image takes less than ten seconds and the microscope drift is about 5nm/min."* Es un valor de referencia en una frase, sin figura de medición.
- **Gargiulo, Violi, Cerrota, Chvátal, Cortés, Perassi, Diaz, Zemánek, Stefani, *ACS Nano* (2017), DOI 10.1021/acsnano.7b04136** (el PDF cargado es la versión ASAP, sin volumen ni páginas), `Articulos del grupo/2017-Accuracy and Mechanistic Details….pdf`, p. 3: *"errors due to mechanical drift of the microscope, typically below 10 nm/min, are negligible because acquiring an image takes <10 s."*
- **Martínez (tesis), p. 75, §3.5 "Deriva mecánica del dispositivo experimental":**
  - *"Típicamente estas derivas toman valores de entre 10 a 50 nm por minuto."*
  - Medición con el botón "Drift Measurement" de PyPrinting, sobre una NP de Au de 60 nm con imágenes iSCAT: *"durante un período de 20 min revela que la NP experimenta un desplazamiento de 800 nm en un eje y 400 nm en el otro, con una velocidad promedio de 30 nm/min, equivalente a 0.5 nm/s."*
  - La Fig. 3.16b muestra además deriva en Z, leída como una caída de la cintura aparente ω de ≈ 260 a ≈ 210-240 nm en 20 min.
- **Martínez, p. 141:** *"la deriva lateral se determinó en 0.45 nm/s"*, es decir ≈ 27 nm/min.
- **Martínez, Apéndice A.2, p. 161:** *"consideremos una deriva mecánica máxima de 0.5 nm/s en el plano XY como la que se midió experimentalmente en el laboratorio."*

**Veredicto.** **PARCIAL.**

*Lo que la bibliografía sí resuelve:*
- "~1 nm/min" es falso: ninguna fuente baja de 5 nm/min.
- El valor medido más reciente, y el único medido con PyPrinting y documentado con figura, es **30 nm/min (0.5 nm/s) en XY**, con 0.45 nm/s en otra medición.
- El rango citable es **5-50 nm/min**: 5 como valor de referencia de Gargiulo, < 10 como cota del artículo de 2017 y 10-50 como rango típico en Martínez.
- El 15-25 nm/min de `lab-invariants` cae dentro de ese rango, pero con una atribución falsa.

*Lo que no resuelve:* qué valor rige en el banco de INS-UNSAM. Las dos tesis describen el microscopio de CIBION (L4, §6.1).

*Recomendación, si no hay medición B-06:* citar "30 nm/min (0.5 nm/s) medido con PyPrinting [Martínez 2024, §3.5]; rango típico 5-50 nm/min [Gargiulo 2017; Martínez 2024]". Usar 0.5 nm/s como caso peor para dimensionar recentrados, como hace el propio Apéndice A.2.

**Pregunta al investigador.** ¿El banco de INS-UNSAM es el mismo microscopio (mismas platina y montura) en el que Martínez midió 30 nm/min en su §3.5, sí/no?

### T-03 · D-27 / S-4 / decisión 3 — Fuerza iónica de trabajo y longitud de Debye

**Qué afirma la documentación.** `lab-invariants.md:119-123` y los prompts de `physicist`, `colloidal-chemist` y `experimentalist` dan 0.75 mM → κ⁻¹ ≈ 11 nm, con atribución a CAT-110 (que no lo contiene). El consolidado propone 1.5 mM NaCl (κ⁻¹ ≈ 7.9 nm). El investigador dice que la fuerza iónica de trabajo **varía entre 0.5 y 1.5 mM**.

**Qué dice la bibliografía cargada.** Todas las fuentes del grupo que declaran el medio de dilución de las NP para imprimir coinciden:

| Fuente | Medio de dilución |
|---|---|
| Gargiulo (tesis), p. 65 (folio 64) | *"diluted to a concentration of C ≈ 2·10⁹ particles/ml using a solution of 1,5 mM NaCl"* (Au y Ag citrato) |
| *ACS Nano* 2017 (DOI 10.1021/acsnano.7b04136), p. 9 | *"Original colloids were diluted in NaCl 1.5 mM, to a final concentration of 2 × 10⁹ NPs/mL"* |
| *ACS Nano* 2017, p. 10 (parámetros DLVO) | *"κ = 1/8 nm"*, es decir κ⁻¹ = 8 nm, coherente con 1.5 mM (0.304/√0.0015 = 7.85 nm) |
| SI de nl5b04542 (Nano Lett. 2016, *Connecting…*), p. 2 | Au: *"NaCl 1.5 mM and Tween® 20 0.1%"*; Ag: *"1mM sodium citrate"* |
| SI de nl6b03174 (Nano Lett., crecimiento dirigido por polarización), p. 2 | *"the supernatant was diluted in NaCl 1.5 mM"* |
| *Adv. Opt. Mater.* 2022 (*Fine Tuning…*), p. 6 | *"diluted 4 times in a 1.5 mm* [sic, mM] *NaCl solution"* |
| Barella *ACS Nano* 2021, p. 7 | NP positivas (CTAB): *"diluted using a 2 mM CTAB solution"*; NP negativas de 64 nm: *"a 1.5 mM NaCl solution"* |
| Chiarelli (Lic. 2017), p. 35; Cerrotta (Lic. 2016), p. 58 | *"NaCl 1,5 mM"* (Cerrotta: más Tween 0,1 % para Au; Ag en *"CitNa3 1 mM"*) |

- **Ninguna fuente cargada menciona 0.5 mM ni 0.75 mM** como medio de impresión.
- Observación propia: el citrato trisódico 1 mM de los protocolos de Ag, si está totalmente disociado, aporta I = ½Σcᵢzᵢ² = 6 mM (κ⁻¹ ≈ 3.9 nm). Es mayor que el rango del investigador, pero sólo se usa para Ag.
- Fuente externa cargada en `Pinzas opticas - Fuerzas opticas/`: Reynolds & Crane, *Nano Lett.* (DOI 10.1021/acs.nanolett.5c06116), p. 2-5, imprime TiO₂ en NaCl de 0 a 17.1 mM y muestra que la sal cambia el signo del efecto de la irradiancia sobre la precisión. Confirma que la fuerza iónica es un parámetro de proceso, no una constante.

**Veredicto.** **PARCIAL.**
- La bibliografía **confirma 1.5 mM NaCl (κ⁻¹ ≈ 7.9 nm)** como el protocolo publicado para Au citrato. Es el extremo superior del rango que dio el investigador y el valor que usa el propio modelo DLVO del grupo (κ⁻¹ = 8 nm).
- **No respalda** el extremo inferior de 0.5 mM ni el valor puntual de 0.75 mM. El rango 0.5-1.5 mM sólo tiene como fuente la respuesta del investigador.
- Redacción sugerida: "0.5-1.5 mM (investigador, 2026-09-27; κ⁻¹ ≈ 13.6-7.9 nm); protocolo publicado: 1.5 mM NaCl [Gargiulo 2017; *ACS Nano* 2017]".

**Pregunta al investigador.** ¿El extremo de 0.5 mM corresponde a un protocolo del banco de INS-UNSAM distinto del publicado (otra sal, NP de CTAC/CTAB o un coloide sin Tween), sí/no? Si es así, ¿cuál?

### T-04 · S-4 / D-02 / D-03 / decisión 1 — Protocolo de sustrato (PDDA/PSS) y limpieza (Hellmanex frente a Piranha)

**Qué afirma la documentación.** CAT-110 §4, MOD-14:86-101, CAT-100:66 y `lab-invariants.md:123` prescriben limpieza **Piranha 3:1** seguida de **silanización APTES** (con curado a 110 °C), para un sustrato positivo que "fija" AuNP de citrato. El investigador confirma que el protocolo actual es PDDA/PSS y deja abierto si se conserva Piranha.

**Qué dice la bibliografía cargada.**

*Impresión óptica: sustrato del mismo signo que las NP.* Lo dicen **todas** las fuentes del grupo:
- Gargiulo (tesis), p. 40: *"Spontaneous adsorption of the NPs onto the substrate was avoided by preparing the substrate to be charged with the same sign as the NPs."*
- *ACS Nano* 2017, p. 2: *"A substrate with the same sign of charge as the NPs is used. A DLVO potential between NPs and substrate prevents spontaneous binding."*
- Martínez (tesis), p. 37 (§2.2.2): *"Para su uso en impresión óptica se les confirió una carga del mismo signo que las NPs. Para depositar NPs electrostáticamente, se los preparó con el signo opuesto de carga que las NPs."*
- Chiarelli (Lic.), p. 10, y Cerrotta (Lic.), p. 15, dicen lo mismo.

*Protocolo de limpieza y funcionalización publicado, casi idéntico en ocho fuentes:*
- Gargiulo tesis p. 63; *ACS Nano* 2017 p. 9; *ACS Photonics* 2019 (Si) p. 3; Barella 2021 p. 7; *Adv. Opt. Mater.* 2022 p. 6; SI nl2c05109 (nanoestrellas) p. 3; Martínez p. 37; Chiarelli p. 37.
- Pasos:
  1. Sonicación 10 min en **Hellmanex 0.2 % v/v**.
  2. Enjuague Milli-Q.
  3. Enjuague con acetona.
  4. Secado a 80 °C (85 °C durante 2 h en Barella 2021 y 2022; 130 °C en el SI de nl6b03174).
  5. **Plasma cleaning 3 min** (Diener Zepto, 75 W, 0.5 mbar, en Barella 2021 y 2022).
  6. **PDDA** (Mw 400-500 k) 1 mg/mL en NaCl 0.5 M, 15 min; enjuague.
  7. **PSS** (Mw 70 k) 1 mg/mL en NaCl 0.5 M, 15 min, para las NP negativas; enjuague.
  8. Guardado en agua (Barella 2021: *"no longer than 1 week"*).
- Para NP positivas (CTAB/CTAC) se usa sólo PDDA: Barella 2021 p. 7, *"Positively charged substrates were used to print the CTAB-capped Au NPs."*
- ψ de la capa PDDA-PSS = −37 mV: *ACS Nano* 2017 p. 10 y Gargiulo p. 111.
- Discrepancia interna: la tesis de Gargiulo (p. 63) escribe *"Hellmanex (2% v/v)"*, y todos los artículos, 0.2 %.
- Variante antigua: el SI de nl5b04542 (p. 2) sólo sonica en Milli-Q 20 min, sin Hellmanex ni plasma.

*Piranha y APTES sí existen en un protocolo del INS, pero para otra cosa.*
- Arias (tesis doctoral, INS-UNSAM, 2025, codirigida por Gargiulo), `Tesis del grupo/ARIAS_Ayelen_TesisFinal_11_11.pdf`, p. 46 (folio 34, §2.2.1 "Inmovilización de AuNPs"): *"se activaron mediante el tratamiento con una solución piraña (mezcla 3:1 de H2SO4 concentrado y H2O2 30%) durante 30 minutos"*, luego *"una solución de APTES al 1% v/v en etanol por 12 h"*, y la inmersión en el coloide *"durante 12 h con agitación suave"*.
- Es una **deposición electrostática masiva** (signo opuesto) para sustratos SERS, no impresión óptica. No hay curado a 110 °C (se seca con N₂) ni bloque de seguridad para la Piranha.

**Veredicto.** **RESUELTO POR BIBLIOGRAFÍA.**
- **Impresión óptica:** Hellmanex 0.2 % → Milli-Q → acetona → 80 °C → plasma 3 min → PDDA (→ PSS para NP negativas). Sustrato del mismo signo que las NP. No usa Piranha ni APTES.
- **Origen del error documental:** la combinación Piranha + APTES es real en el INS, pero corresponde al protocolo SERS de inmovilización por inmersión de Arias (signo opuesto). La documentación la trasplantó a la impresión, donde invierte el mecanismo (consolidado V-33).
- **El curado a 110 °C** de `lab-invariants` no aparece en ninguna fuente cargada.
- **Sobre Piranha**, la bibliografía no decide si el banco de impresión la conserva. Sólo dice que ningún protocolo de impresión publicado la usa. Si se documenta como opción del protocolo SERS, faltaría el bloque de seguridad (Arias tampoco lo incluye).

**Pregunta al investigador.** ¿La Piranha + APTES se conserva **sólo** como protocolo de sustratos SERS por inmersión (Arias) y se elimina de todo documento de impresión óptica, sí/no?

### T-05 · D-27 (resto) — Constante de Hamaker y demás constantes coloidales de `lab-invariants` §6

**Qué afirma la documentación.** `lab-invariants` §6 y `colloidal-chemist.md` dan A_H = 2.5 × 10⁻¹⁹ J. El consolidado sostiene que ese valor corresponde a Au-agua-Au y que Au-agua-vidrio es ≈ (2-5) × 10⁻²⁰ J.

**Qué dice la bibliografía cargada.** Ninguna fuente da un valor numérico de A_H, pero el grupo publica la fórmula y los parámetros.
- *ACS Nano* 2017, p. 9-10: para *"a dielectric and a metal interacting through a liquid"*, H = (3/(8√2))·[(n₁² − n₃²)/(n₁² + n₃²)]·h√(ν₁ν₃)ν_m / (√(ν₁ν₃) + ν_m/√(n₁² − n₃²)) (Lipkin *et al.*), con *"n1 = 1.45; n3 = 1.33; ν1 = 3.2 × 10^15 s−1; ν3 = 3 × 10^15 s−1; νm = 6.2 × 10^15 s−1 for Au"*.
  - El PDF imprime los exponentes como 10⁻¹⁵ s⁻¹, un error tipográfico evidente.
  - El denominador está impreso con "ν₂": lo leo como ν_m.
- La misma fórmula aparece en Chiarelli (Lic.), p. 11. Gargiulo (tesis, p. 42) usa la forma de fuerza F_LvdW = 2Aa³/[3z²(z+2a)²], sin valor numérico.
- **Cálculo propio con esos parámetros:** H ≈ **2.1 × 10⁻²⁰ J** (Au-agua-vidrio).

**Veredicto.** **RESUELTO POR BIBLIOGRAFÍA**, por cálculo con la fórmula y los parámetros publicados por el grupo: A_H(Au-agua-vidrio) ≈ 2 × 10⁻²⁰ J, dentro del rango de la auditoría. El 2.5 × 10⁻¹⁹ J de `lab-invariants` y del prompt es un orden de magnitud mayor y no corresponde a la geometría NP-sustrato. El curado de APTES y los 0.75 mM se tratan en T-03 y T-04.

**Pregunta al investigador.** Ninguna.

### T-06 · Decisión 4 / D-19 / C-36 — Referencia del Si en Raman (520.45 frente a 520.7 cm⁻¹)

**Qué afirma la documentación / el código.**
- El código usa 520.7 cm⁻¹ en `calibration_dock` y `raman_engine`.
- El consolidado propone 520.45 ± 0.28 cm⁻¹ (NMIJ CRM 5606-a) y señala que el modo "stokes" con la red de 1200 l/mm deja el pico fuera de la ventana (C-36).

**Qué dice la bibliografía cargada.**
- Ninguna fuente cargada da un valor de referencia con incertidumbre para el fonón del Si. El único número es nominal: *ACS Sens.* 2024, p. 7 (folio 1055), sobre Zograf *et al.*: *"the 520 cm−1 Raman line of a 350 nm silicon NP … The peak shifts up to 509 cm−1, which corresponds to a temperature increase of approximately 600"* [K].
  - Consecuencia para la calibración (inferencia mía): la línea se corre ≈ −0.02 cm⁻¹/K. Un patrón de Si calentado por el láser desplaza la referencia más que la diferencia 520.45/520.7, así que hay que medirlo a baja irradiancia.
- **Práctica de calibración del grupo:** no usa Si. Martínez, p. 60: *"La calibración de la red espectral viene proporcionada por el fabricante del equipo; antes de su uso, se ajusta con un valor de corrección que se verifica con la incidencia de dos láseres distintos."* Coincide con la respuesta 7 del investigador (offset calibrado con láser, filtro de densidad y ajuste gaussiano).
- **Redes instaladas en el banco de INS-UNSAM**, según Pereyra (Lic., INS-UNSAM, 2025), `Tesis del grupo/Licenciatura/2025_Tesis Abril J. Pereyra.pdf`, p. 33 (folio 32): *"La torreta permite seleccionar entre dos rejillas de difracción diferentes (150 y 1200 líneas/mm) o un espejo."* Esto respalda D-19 en cuanto a que no hay red de 300.

**Veredicto.** **NO CUBIERTO** para el valor de referencia (520.45 frente a 520.7). La bibliografía sí aporta dos datos útiles:
1. El grupo calibra λ con líneas láser, no con Si.
2. La deriva térmica de la línea del Si (≈ −0.02 cm⁻¹/K) obliga a medir el patrón a baja potencia.

**Pregunta al investigador.** ¿El Si se usará como patrón de calibración del eje Raman (y no sólo como verificación semanal), sí/no? Si la respuesta es sí, hace falta el paso (3): fijar el valor certificado por la web.

### T-07 · D-33 / C-02 / decisión 6 — Convención honeycomb

**Qué afirma la documentación / el código.** `core/lattice_generator.py:59-70` usa la base (0,0) + (⅓, ⅔) con γ = 60°, lo que genera dímeros a a/3 (V-06). CAT-314 y MOD-07 describen esa base como "grafeno/honeycomb/hBN". El consolidado propone (⅓, ⅓) con γ = 60°, o bien (⅓, ⅔) con γ = 120°.

**Qué dice la bibliografía cargada.**
- Guo, Hakala y Törmä, *Phys. Rev. B* 95, 155423 (2017), `redes plasmonicas/2017. Geometry dependence of surface lattice resonances….pdf`, p. 6, subsección "E. Honeycomb lattice": *"a honeycomb structure is constituted of a hexagonal lattice with two particles within each unit cell. The envelope factors from these two particles to the six lowest DOs are 1/2 + √3/2i for (1,0), (0,1), (−1,−1) and 1/2 − √3/2i for (1,1), (−1,0), (0,−1), respectively. Both factors have unity magnitude"*.
- La Fig. 7a (p. 6) lista (±1,0), (0,±1) y ±(1,1) como los seis órdenes más bajos. Eso sólo ocurre con vectores primitivos a γ = 60° (con γ = 120° el sexto par sería ±(1,−1)).
- La p. 7 mide una red honeycomb con *"a nearest particle separation of 250 nm"* (la distancia a primeros vecinos es a/√3).

*Verificación algebraica propia* de F(G) = 1 + exp(2πi(h·x₂ + k·y₂)):
- Con la base **(⅓, ⅓) a 60°**, los seis órdenes dan exactamente 1/2 ± (√3/2)i con los signos que publica el artículo, y |F| = 1 en todos.
- Con la base **(⅓, ⅔) a 60°** (la del código), el orden (1,1) da |F| = 2 y el (0,1) cambia de signo. **Contradice el artículo.** Además, geométricamente es un dímero (coordinación 1; V-06).

**Veredicto.** **RESUELTO POR BIBLIOGRAFÍA** a favor de **(0,0) + (⅓, ⅓) con γ = 60°**, equivalente a (0,0) + (⅓, ⅔) con γ = 120°. Distancia a primeros vecinos: a/√3; coordinación: 3. La base actual del código queda refutada por los factores de estructura publicados.

**Pregunta al investigador.** ¿Hay muestras honeycomb, hBN, kagomé o dice ya impresas con el Diseñador de PyPrinting 3.0 que haya que re-validar, sí/no?

### T-08 · S-5 / C-14 / D-36 / decisión 5a — Definición de ξ (longitud de correlación)

**Qué afirma la documentación / el código.** El código usa tres fórmulas de ξ (2π/FWHM_f en honeycomb, 1/(2π·FWHM_f) en la red cuadrada y 2π/FWHM en el tooltip), y la documentación agrega 1/(π·FWHM) y 2/FWHM_q, sin resta de Scherrer. El consolidado propone la lorentziana ξ = 1/(π·FWHM_f) con resta del tamaño finito.

**Qué dice la bibliografía cargada.**
- Ninguna fuente cargada define ξ a partir del ancho de un pico del factor de estructura, ni trata el ensanchamiento de Scherrer o el paracristal de Hosemann. La búsqueda sobre los 107 textos no da ninguna coincidencia para "Scherrer", "paracrystal", "Hosemann" ni "Debye-Waller".
- Las únicas apariciones de "coherence length" son de otra naturaleza:
  - la coherencia espacial del modo SLR (*"coherence lengths L of 6–10 µm"*, `Reviews/2018 - The rich photonic world…`, p. 6);
  - la coherencia del haz de iluminación, *"about λ/NA"* (`narrow-collective-plasmon-resonances…`, p. 7).
- Los trabajos coloidales de redes (Volk *et al.*, *Adv. Mater. Interfaces* 2021, p. 3; *Langmuir* 2020, p. 5) caracterizan el orden con FFT y g(r) (*"g(r) shows at least six to seven clearly distinguishable peaks, indicating large crystalline domain sizes"*), sin fórmula de ξ.
- El único análisis de desorden de redes **impresas en el grupo** (Pereyra, p. 48-50, §3.1.3) no usa ξ. Usa el coeficiente de variación de las distancias a primeros vecinos, CV = σ/μ (0.17 y 0.15 para a = 500 y 550 nm).

**Veredicto.** **NO CUBIERTO.** Las tres o cuatro fórmulas del código no pueden decidirse por la bibliografía cargada. Queda como decisión de convención (ADR) con fuentes a incorporar a la nueva carpeta `docs/bibliografia/Debye-Waller estatico y desorden posicional/`. La métrica de desorden que el grupo efectivamente publicó es el CV de primeros vecinos (Pereyra), que el código podría ofrecer como observable validado en lugar de ξ.

**Pregunta al investigador.** ¿Se adopta ξ = 1/(π·FWHM_f), con FWHM en frecuencia ordinaria (nm⁻¹) y con resta del ensanchamiento por tamaño finito, como definición única, sí/no?

### T-09 · C-15 / D-35 / C-49 / decisión 5b — Estimador de la fracción de vacancias p

**Qué afirma la documentación / el código.** La GUI informa "Vacancias estimadas" a partir de la ordenada de Wilson (`core/lattice_disorder.py:1178-1324`). Con normalización 1/N_det, ese valor no depende de p: da ≈ 25 % constante (V-05). CAT-308 y CAT-305 hablan de un "desacoplamiento completo". El consolidado propone obtener p por conteo.

**Qué dice la bibliografía cargada.**
- Ninguna fuente trata el estimador de Wilson ni la dependencia (1−p) frente a (1−p)² de la altura de Bragg.
- El único trabajo del grupo que cuantifica vacancias en redes impresas lo hace **por conteo**. Pereyra, p. 51 (folio 50): *"Otro dato que se obtiene de este análisis es el porcentaje de partículas impresas, o eficiencia de impresión. Para la red de 500 nm tenemos una eficiencia de impresión del 93 %, mientras que para la red de 550 nm se obtuvo una del 99 %."* Las posiciones salen de Picasso sobre imágenes confocales (p. 49, folio 48).
- Zundel, May y Manjavacas, *ACS Photonics* 8, 360 (2021) (`redes plasmonicas/Teoricos/`), tratan vacancias **periódicas**, que inducen nuevas resonancias de red, no vacancias aleatorias. No sirven como estimador.

**Veredicto.** **PARCIAL.** La bibliografía respalda la propuesta del consolidado: la práctica publicada del grupo es p = 1 − (eficiencia de impresión), obtenida por conteo. No valida ni refuta el estimador de Wilson; su falla es un resultado matemático de la auditoría (V-05). C-49 (que f_vac incluya satélites) tampoco está cubierto.

**Pregunta al investigador.** ¿p se reporta como 1 − (NP localizadas en sitios de la red programada)/(sitios programados), como la "eficiencia de impresión" de Pereyra §3.1.3, sí/no?

### T-10 · D-37 / D-38 / S-1 (parte cristalográfica) — Debye-Waller (factor ½), (1−p)², FWHM paracristalino, KTHNY, ψ_n y Friedel

**Qué afirma la documentación.**
- CAT-300, CAT-315 §6.3, MOD-08 y el EVIDENCE_LEDGER (PHY-005, PHY-009) cargan un factor ½ en exp(−½G²σ²) y una dependencia (1−p)².
- CAT-300:117 da un FWHM paracristalino dimensionalmente incorrecto; CAT-313 da T_m (KTHNY) y el sesgo de ψ_n por jitter con factores 2 dudosos, y fases de ψ sin fuente.
- CAT-308:369 invoca Friedel.

**Qué dice la bibliografía cargada.**
- Nada. La búsqueda de "Debye-Waller", "paracrystal/Hosemann", "Scherrer", "KTHNY/hexatic", "bond-orientational/ψ₆" y "Friedel" en los 107 textos no devuelve ningún pasaje pertinente (la única coincidencia de "orientational order" es sobre la orientación de nanoestrellas, `Colloidal/2025- ACS NANO -Scalable-Manufacturing…`, p. 4).
- Esto concuerda con la respuesta 9 del investigador: el Monte Carlo de Debye-Waller es un método en desarrollo, sin bibliografía propia.

**Veredicto.** **NO CUBIERTO.** Todo el bloque S-1 cristalográfico (½ de DW, (1−p)², 4π²m²σ²/a³, 2/a, T_m ×2, sesgo de ψ_n ×2, |Ψ₃| en honeycomb, Friedel) depende de la bibliografía que el investigador pidió reunir en `docs/bibliografia/Debye-Waller estatico y desorden posicional/`. Hasta que esa carpeta exista, las correcciones de D-37/D-38 sólo pueden apoyarse en la derivación de la auditoría. Deberían rotularse "derivación propia, sin fuente cargada".

**Pregunta al investigador.** ¿Se acepta que la carpeta de Debye-Waller incluya como mínimo un texto de cristalografía (p. ej., Warren, *X-ray Diffraction*, o Guinier) para fijar el factor exp(−G²σ²) con σ por componente, sí/no?

### T-11 · C-11 / D-34 — Inversión Monte Carlo de σ (σ_MC = 0) y σ_dw = 15.6 nm

**Qué afirma la documentación / el código.** CAT-307 y MOD-08 presentan una calibración MC "de exactitud absoluta" y σ_dw = 15.6 nm (CAT-304). El código devuelve σ = 0 para σ real de 5 a 40 nm con 256 bins, porque usa estimadores distintos para el MC y para el experimento (V-04). El investigador aclara que el MC es un método **en desarrollo**, sin bibliografía propia.

**Qué dice la bibliografía cargada.**
- No hay fuente sobre el método (ver T-10).
- Sí hay datos independientes del **orden de magnitud** del desorden posicional real, útiles como control de cordura del MC:
  - *Nano Lett.* 17, 5747 (2017), `Articulos del grupo/2017-Understanding and reducing Photothermal Forces.pdf`, p. 2: *"The process has a typical average positional accuracy of 50 nm."*
  - Martínez, p. 41: *"el 90 % de las NPs se imprime dentro de los 100 nm del objetivo deseado, con una desviación cuadrática media radial del orden de 50 nm"*. En p. 129: R90 = 89 nm, R66 = 63 nm y R33 = 38 nm para esferas de 60 nm a 532 nm.
  - Pereyra (banco de INS-UNSAM), p. 50 (folio 49), Cuadro 3.1: desviación estándar de las distancias a primeros vecinos σ_d = 92.6 nm (a = 500 nm) y 88.8 nm (a = 550 nm), con NP de 100 nm y localización Picasso sobre imágenes confocales de 158 nm/px.
- Con errores independientes por sitio, la varianza de la distancia a lo largo del enlace es 2σ_x², de modo que σ_x ≈ σ_d/√2 ≈ 63-65 nm (inferencia mía). Incluye el error de localización y posibles defectos, así que es una cota superior.

**Veredicto.** **NO CUBIERTO** en cuanto al método, lo que es coherente con que esté "en desarrollo".

La bibliografía aporta en cambio un **control externo**: el desorden posicional esperado para una red impresa ronda σ ~ 35-65 nm por componente (≈ 50 nm RMS radial según el grupo; ≈ 63-65 nm como cota por Pereyra). De ahí dos consecuencias:
- el rango de validación de la auditoría (σ = 5-40 nm) queda por debajo del caso real;
- el σ_dw = 15.6 nm de CAT-304 es incompatible con la precisión de impresión publicada. Debe retirarse o rotularse "experimental".

**Pregunta al investigador.** ¿La validación de extremo a extremo del MC debe cubrir σ = 20-80 nm por componente (el rango de la precisión de impresión publicada), sí/no?

### T-12 · D-23 / D-24 — Magnitudes de fuerza, absorción, β, ΔT y tiempos térmicos (Au 60 nm, 532 nm, agua)

**Qué afirma la documentación.** CAT-109, CAT-110, CAT-111, CAT-112, SYS-201 y CAT-114 dan:
- F_z = 5-80 pN;
- σ_abs = 3-3.5 × 10⁻¹⁵ m²;
- τ térmico de cientos de ms;
- σ_scat en la presión de radiación;
- r = 0.004;
- un "límite de 12 mW en `config.py`" con ΔT < 45 K (CAT-112:166).

La auditoría propone F_z ≈ 0.3-2 pN, σ_abs ≈ 1.1 × 10⁻¹⁴ m², ΔT ≈ 170-240 K a 5 mW/µm², τ del orden de ns, σ_ext y r = 0.066 (amplitud).

**Qué dice la bibliografía cargada.**
- **Fuerzas.**
  - Gargiulo (tesis), p. 94: *"the maximum calculated forces are F = 0.36 pN with Lorenz–Mie theory and F = 0.31 pN with Rayleight-Kuwata model"* (60 nm Au, 532 nm, P = 1 mW, w₀ = 265 nm).
  - *ACS Nano* 2017, p. 7: *"the electrostatic barrier is around 2kBT, and the maximum repulsive force is Fth = 0.47 pN for Au NPs"*.
  - Las fuerzas escalan linealmente con P: a pocos mW son del orden de 1 pN, **no** de decenas de pN.
- **σ_abs.**
  - Gargiulo, p. 19 (Fig. 1.2b, Au 60 nm en agua): el máximo de σ_abs cerca de 530 nm está en ≈ 1.05-1.08 × 10⁴ nm² (≈ 1.1 × 10⁻¹⁴ m²), lectura propia de la figura.
  - Barella 2021, p. 6, y Martínez, p. 99, para Au 80 nm sobre vidrio: *"σabs (at λ = 532 nm) was estimated to be 16.9 × 10³ nm2 on glass"*.
- **σ_ext en la presión de radiación.** Gargiulo, p. 19, Ec. 1.9: σ_ext = k·Im[α]. Las fuerzas de *ACS Nano* 2017 (p. 9) ponen α″ = Im α en F_scat, es decir, extinción y no σ_scat.
- **β y ΔT.**
  - Barella 2021, p. 5: *"⟨β⟩ = 63 K μm2/mW … The standard deviation of the 10 measurements was 3 K μm2/mW (4%)"* (Au 80 nm/vidrio/agua); p. 6: ⟨β⟩_vidrio = 62 ± 1 K µm²/mW.
  - Challenges, *J. Chem. Phys.* 156, 034201 (2022), p. 14: *"a 60 nm Au NP may reach temperatures of up to 645 K"* durante la impresión.
- **Tiempo térmico.** Martínez, p. 28: *"El tiempo necesario para alcanzar la estabilidad térmica de la NP, es decir, la red, es de alrededor de 1 ns."*
- **Coeficiente de reflexión.** Cerrotta (Lic.), p. 52, sobre la detección interferométrica: *"Er = rEi e^(−iπ/2), donde r es el coeficiente de reflexión"*. En la señal entra la **amplitud** r. Ninguna fuente da su valor numérico.
- **κ_trap y el "límite de 12 mW".** No cubiertos. El segundo es un hecho de código (V-35).

**Veredicto.** **RESUELTO POR BIBLIOGRAFÍA**, a favor de los valores de la auditoría:
- F ~ 0.3-0.5 pN/mW (umbral 0.47 pN);
- σ_abs ≈ 1.1 × 10⁻¹⁴ m² (60 nm);
- σ_ext (Im α) en la presión de radiación;
- β ≈ 62-63 K·µm²/mW (80 nm/vidrio), es decir ΔT = β·I de cientos de K a pocos mW/µm²;
- τ ~ 1 ns;
- r como amplitud.

Quedan sin cubrir el valor numérico de r y κ_trap. La cifra de 12 mW / ΔT < 45 K cae por el β medido (Barella 2021), como calculó V-35.

**Pregunta al investigador.** Ninguna.

### T-13 · D-25 / S-7 — Objetivo de impresión y cintura del haz

**Qué afirma la documentación.** Doce documentos dan un objetivo de aceite NA 1.3-1.49 y w₀ = 230-300 nm o 0.61λ/NA "como cintura".

**Qué dice la bibliografía cargada.**
- **Objetivo.**
  - Gargiulo, p. 51: *"Imaging of the sample plane was performed using an water-immersion objective of NA=1"*.
  - Martínez, p. 55: *"se emplea un objetivo de inmersión de agua de 60x con una apertura numérica NA = 1 (Olympus LUMPLFLN 60XW), o un objetivo de aire 20x, NA = 0.5 (Olympus UPlanFL N 20x/0.50)"*.
  - **Banco de INS-UNSAM**, Pereyra, p. 30 (folio 29): *"pueden ser Olympus LUMPLFLN60XW para agua o Olympus Plan Fluorite 20x para aire"*, y p. 39: *"Olympus Plan Fluorite 20x, NA = 0.5"*.
  - Challenges, *J. Chem. Phys.* 2022, p. 4: *"Usually, a water immersion objective is used in direct contact with the colloidal suspension."*
- **Cintura medida.**
  - *Nano Lett.* 17, 5747 (2017), p. 2: *"The laser is focused to a Gaussian beam waist of (266 ± 3) nm"*.
  - Gargiulo, p. 73-75: w₀ = 265 nm (532 nm).
  - Martínez, p. 129: *"láser de 532 nm, cuya cintura del haz es de 278 nm"*.
  - La Fig. 3.16b de Martínez (p. 75) muestra ω ≈ 210-260 nm durante 20 min.
- **Definición de la cintura.** Martínez, p. 63-64 (§3.3): *"El parámetro ⍵ es la cintura del haz en el plano (z = 0) y representa el radio al cual el campo decae 1/e y la intensidad 1/e2"*, y *"Experimentalmente la cintura del haz ⍵ es determinada a partir de un ajuste gaussiano a imágenes iSCAT de NPs individuales"*. La irradiancia de pico es I = 2P′T/(πω²) (Ec. 3.2), con T la transmitancia del objetivo.
- **Radio de Airy.** Cerrotta, p. 50: *"el radio del disco de Airy, el cual es la distancia a la cual se anula por primera vez la PSF"*. Es un objeto distinto de la cintura gaussiana.

**Veredicto.** **RESUELTO POR BIBLIOGRAFÍA.**
- Objetivo de impresión: **agua, NA 1.0 (Olympus LUMPLFLN 60XW)**, también en el banco de INS-UNSAM según Pereyra 2025.
- **w₀ ≈ 265-278 nm medido** por ajuste gaussiano a imágenes iSCAT.
- 0.61λ/NA es el radio de Airy (primer cero), no w₀.
- Discrepancia con el código (D-21): el objetivo de aire del banco es 20x/**0.50**, no "Olympus 20x 0.40".

**Pregunta al investigador.** ¿El objetivo de aire montado hoy es el Olympus UPlanFL N / Plan Fluorite 20x con NA = 0.50 (y no 0.40 como en `sif_processor.MICROSCOPE_OBJECTIVES`), sí/no?

### T-14 · D-26 / S-1 (óptica) — Unidad de Airy y tamaño de pinhole

**Qué afirma la documentación.** CAT-108 §5.2 usa d_Airy = 2.44λM/NA y concluye "0.46 AU super-confocal"; CAT-203 arrastra el valor. El consolidado propone d_Airy = 1.22λM/NA (AU = diámetro).

**Qué dice la bibliografía cargada.**
- **Radio de Airy como primer cero:** Cerrotta, p. 50 (cita en T-13). Para un sistema confocal *"Un buen compromiso es poner un pinhole con un tamaño del orden que el radio de un disco de Airy"* (p. 51).
- **Unidad de Airy expresada en diámetro:** Scocozza (Lic. 2016), p. 36-37: *"un pinhole confocal de 0.9 veces el diámetro del disco de Airy"*.
- **Pinholes reales del microscopio de impresión (CIBION):**
  - Chiarelli, p. 30: *"una lente de 50 mm de distancia focal, un pinhole de 50 µm y como detector un fotodiodo amplificador. Se usó una relación confocal bastante relajada. La imagen teórica del pinhole sobre la muestra es de 3 µm"*.
  - Cerrotta, p. 62, lo repite.
  - Con λ = 532 nm y NA = 1.0, el diámetro de Airy en la muestra es 1.22λ/NA ≈ 0.65 µm, de modo que ese pinhole equivale a ≈ 4.6 AU (cálculo propio). Es un pinhole relajado, no "super-confocal". Coincidencia llamativa, sin prueba de causalidad: 4.6 = 10 × 0.46.
- **Pinhole del banco de INS-UNSAM:** Pereyra, p. 30, sólo menciona *"un pinhole de 50µm en el plano focal de la primera lente del telescopio"* para limpiar el modo de excitación. No da el pinhole de detección.

**Veredicto.** **RESUELTO POR BIBLIOGRAFÍA** en cuanto a la convención: la AU se expresa en diámetro, 1.22λM/NA, y el radio de Airy es 0.61λ/NA. También resuelve que el confocal documentado del grupo es **relajado** (≈ 4-5 AU). La cifra de AU del banco de INS-UNSAM no está cubierta.

**Pregunta al investigador.** ¿El canal confocal del banco de INS-UNSAM conserva el pinhole de 50 µm con lente de 50 mm de Chiarelli y Cerrotta (≈ 4.6 AU), sí/no?

### T-15 · D-28 / D-20(e) — Nucleación de burbujas y espinodal del agua

**Qué afirma la documentación.** CAT-102:113, MOD-14:243, CAT-109:184 y CAT-112:164 fijan el umbral de burbuja en 280-300 °C. La auditoría propone ~200 °C (190-245 °C según el gas disuelto).

**Qué dice la bibliografía cargada.**
- Gargiulo, p. 97 (folio 96): *"water can be superheated beyond the boiling point up to the spinodal decomposition temperature 594 °K in such small volumes[78, 79, 80]. Another possibility is that a small bubbles form around the NP[81]."*
- Martínez, p. 124: β medido *"utilizando irradiancias que no produjeran deformación ni burbujas (I = 3.3 mW/µm2 e I = 2.2 mW/µm2, para 532 nm y 592 nm)"*. Es un criterio operativo para nanoestrellas, no un umbral de temperatura.
- Baffou *et al.*, *J. Phys. Chem. C* 118, 4890 (2014) (*"Super-Heating and Micro-Bubble Generation around Plasmonic Nanoparticles under cw Illumination"*) aparece **citado** en *ACS Sens.* 2024 (ref. 51) y en la reseña de ensamblado 2025, pero **no está cargado**.

**Veredicto.** **PARCIAL.** La bibliografía cargada fija una **cota superior**: la espinodal, 594 K ≈ 321 °C (T-01e). También reconoce que pueden formarse burbujas antes de alcanzarla. No da el umbral de nucleación de ~200 °C que propone la auditoría. El 280-300 °C de la documentación no tiene fuente cargada. La fuente que decidiría (Baffou 2014) está citada pero falta en la carpeta.

**Pregunta al investigador.** ¿Se incorpora Baffou *et al.*, *J. Phys. Chem. C* 118, 4890 (2014), a `docs/bibliografia/Termometria/` y se adopta su umbral de nucleación con gas disuelto (~200 °C) como umbral operativo, sí/no?

### T-16 · D-29 — Dímeros: distancia mínima, polarización y decaimiento del corrimiento

**Qué afirma la documentación.** CAT-103:18, MOD-02:324, CAT-102:111 y CAT-109:205-207 prometen dímeros "sub-100 nm" con "gap sub-20 nm" y "rotar λ/2 para atraer"; el decaimiento del corrimiento plasmónico va con 0.2·R.

**Qué dice la bibliografía cargada.**
- **Distancia mínima sobre vidrio.** *Nano Lett.* 17, 5747 (2017), p. 1 (resumen): *"for unclear causes it was not possible to print identical NPs closer to each other than 300 nm. Here, we show that the repulsion … arises from light absorption by the printed NPs and subsequent local heating."* Y a continuación: *"Using a reduced graphene oxide layer on a sapphire substrate, we demonstrate for the first time the optical printing of AuAu NP dimers."*
- **Polarización.**
  - Gargiulo, p. 94: *"These results indicate that the polarization of the beam does not have a major role in the light-induced repulsion."*
  - *Nano Lett.* 16, 1224 (2016) (*Connecting…*), p. 4: *"we have not observed any polarization dependency on the repulsion, as predicted by optical binding."*
  - Challenges 2022, p. 6: *"the laser polarization does not influence the printing precision."*
- **Dímeros heterogéneos.** *Nano Lett.* 2016 (*Connecting…*) y *Nano Lett.* 2017, p. 2: la repulsión se evita *"if the already printed NPs are transparent at the printing wavelength"* (Au-Ag) o disipando calor (zafiro/rGO, nanodiscos).
- **Decaimiento 0.2·D frente a 0.2·R.** Jain, Huang & El-Sayed, *Nano Lett.* 7, 2080 (2007), la "plasmon ruler equation", está **citado** en Vosshage *et al.* 2025 y en reseñas de redes (*Nature Rev. Mater.* 2025; *Nanophotonics* 2019), pero **no está cargado**.

**Veredicto.** **PARCIAL.**
- **Resuelto:**
  - sobre vidrio con polielectrolito, d_min ≈ 300 nm por repulsión fototérmica, independiente de la polarización. "Rotar λ/2 para atraer" es falso.
  - "Sub-100 nm" y "gap ≈ 0" sólo se logran con sustratos disipadores (zafiro/rGO) o con la primera NP transparente a la λ de impresión. No es la condición estándar del banco.
- **No cubierto:** el factor 0.2·D frente a 0.2·R, porque Jain 2007 no está cargado.

**Pregunta al investigador.** ¿Se incorpora Jain, Huang & El-Sayed, *Nano Lett.* 7, 2080 (2007), a la bibliografía para fijar la constante de decaimiento (≈ 0.2 × diámetro), sí/no?

### T-17 · D-30 / S-11 — Precisiones "sub-nanométricas" (impresión y localización)

**Qué afirma la documentación.** Diez documentos prometen precisión "sub-nm" de impresión o de localización (p. ej., 0.26 nm con N = 1000).

**Qué dice la bibliografía cargada.**
- **Precisión de impresión.**
  - *Nano Lett.* 2017, p. 2: *"The process has a typical average positional accuracy of 50 nm."*
  - Martínez, p. 41: *"el 90 % de las NPs se imprime dentro de los 100 nm del objetivo deseado, con una desviación cuadrática media radial del orden de 50 nm"*.
  - Martínez, p. 129: R90/R66/R33 = 89/63/38 nm para esferas de 60 nm.
  - En el banco de INS-UNSAM, Pereyra, p. 50: σ de las distancias a primeros vecinos ≈ 89-93 nm con NP de 100 nm (T-11).
- **Localización.** Richter (Lic. 2020, MINFLUX en el grupo), p. 51: *"5× fewer photons are required to reach 5 nm localization precision compared to a perfect camerabased detector with infinite SBR. For a camera-based localization technique and the same signal-to-background ratio as in our measurement, i.e. SBR = 24, 100× more photons are necessary to attain the 5 nm precision."* Con MINFLUX se alcanzan 1-2 nm (p. 10). En p. 21 define σ_CRB = √(½·tr Σ_CRB) como **media por componente**, una convención que S-1 exige declarar.

**Veredicto.** **RESUELTO POR BIBLIOGRAFÍA.** La precisión de impresión es ≈ 50 nm RMS radial, no sub-nm. Con cámara, una precisión de localización de pocos nm ya exige presupuestos de fotones altos, así que 0.26 nm con N = 1000 es incompatible con la bibliografía del grupo. El valor exacto del CRLB con fondo y F² del EMCCD (D-39) no está cubierto.

**Pregunta al investigador.** Ninguna.

### T-18 · D-32 / S-9 — Citas fabricadas o erróneas

**Qué afirma la documentación.**
- "Martínez *et al.*, *ACS Photonics* 6, 2682 (2019)".
- La tesis de Martínez con otro título y otro año.
- DOI 10.1039/C6CP00010A.
- Manevitch *PRE* 76, 051602.
- Normas "ISO/IEC 40749/11578/18262".

**Qué dice la bibliografía cargada.**
- **Tesis de Martínez**, portada (p. 1): *"Manipulación óptica, nanotermometría y crecimiento inducido por plasmónica de nanopartículas individuales"*, Doctorado UBA-FCEN, lugar de trabajo CIBION-CONICET, *"noviembre de 2024"*, director F. D. Stefani, directora adjunta I. L. Violi.
- Su lista de *"Publicaciones derivadas"* (p. 165) incluye Barella *ACS Nano* 2021, Violi *J. Chem. Phys.* 2022, Martinez *Adv. Opt. Mater.* 2022, Gargiulo *Nat. Commun.* 2023 y otras. **No hay** ningún "Martínez *et al.*, *ACS Photonics* 2019".
- El único artículo del grupo en *ACS Photonics* 2019 cargado es Zaza, Violi, Gargiulo *et al.*, *"Size-Selective Optical Printing of Silicon Nanoparticles through Their Dipolar Magnetic Resonance"*, *ACS Photonics* 6, 815−822 (2019).
- Ninguna fuente cargada contiene el DOI C6CP00010A, Manevitch ni las normas ISO citadas.

**Veredicto.** **PARCIAL.**
- **Resuelto:** título y año de la tesis de Martínez; la cita "Martínez *et al.*, *ACS Photonics* 6, 2682 (2019)" no corresponde a ninguna publicación del grupo, y el candidato real de ese año y revista es Zaza *et al.* 6, 815.
- **No cubierto:** los DOI externos y las normas ISO. Se verifican en el paso (3), la web, que el consolidado ya hizo.

**Pregunta al investigador.** ¿La afirmación que CAT-109/CAT-110 atribuyen a "Martínez *et al.*, *ACS Photonics* 2019" debe re-citarse a Zaza *et al.*, *ACS Photonics* 6, 815 (2019), sí/no? Si no corresponde, se elimina.

### T-19 · S-1 — Errores de factor 2 por convención: estado caso por caso

**Qué afirma el consolidado.** Hay un patrón de factores 2 por convenciones no declaradas: varianza por componente frente a total, amplitud frente a intensidad, semiancho frente a ancho, radio frente a diámetro.

**Qué dice la bibliografía cargada, caso por caso:**

| Caso | Estado | Fuente |
|---|---|---|
| d_Airy 2.44 frente a 1.22 (AU) | **Resuelto**: AU en diámetro, 1.22λM/NA | T-14 (Cerrotta p. 50; Scocozza p. 36-37) |
| 0.61λ/NA usado como cintura | **Resuelto**: es el radio de Airy; la cintura es el radio a 1/e² medido por ajuste gaussiano | T-13 (Martínez p. 63-64) |
| r en amplitud frente a intensidad | **Parcial**: la señal interferométrica usa la amplitud r; sin valor numérico | T-12 (Cerrotta p. 52) |
| σ por componente frente a total (CRLB) | **Parcial**: el grupo define σ_CRB = √(½·tr Σ), la media por componente | Richter (Lic.) p. 21 |
| Factor ½ de Debye-Waller; (1−p)² | No cubierto | T-10 |
| ξ = 1/(2π·FWHM) frente a 1/(π·FWHM) | No cubierto | T-08 |
| Prefactor 1/a frente a 2/a (CAT-309); T_m KTHNY ×2; jitter de ψ_n ×2 | No cubierto | T-10 |
| Pinhole a/√12 frente a a/√3 (CAT-203) | No cubierto | — |
| Normalización de la PSF de dona (CAT-202) | No cubierto. Richter (p. 17) usa I(r) = 4A₀e·(r²/ℓ²)·exp(−4r²/ℓ²), normalizada al pico A₀ y no a la potencia; no decide la normalización de CAT-202 | Richter p. 17 |
| 0.2·D frente a 0.2·R (dímero) | No cubierto (Jain 2007 no está cargado) | T-16 |

**Veredicto.** **PARCIAL.** Los casos ópticos quedan resueltos por la bibliografía: Airy, cintura y, en parte, r y σ. Los cristalográficos no están cubiertos. La recomendación del consolidado (una tabla de convenciones canónicas en `lab-invariants`) puede poblarse ya con las filas ópticas, citando las fuentes de T-13 y T-14.

**Pregunta al investigador.** ¿Se acepta crear en `lab-invariants` una tabla de convenciones, con σ por componente, AU en diámetro, cintura a 1/e² y r en amplitud, citando las tesis del grupo, sí/no?

### T-20 · D-39 — Localización y GUM (CRLB, EMCCD, ajuste ponderado, RL → Picasso)

**Qué afirma la documentación.** CAT-200 a CAT-206, SYS-105 y MOD-09 describen:
- un guardarraíl RL → Picasso inexistente;
- un CRLB sin fondo y sin el factor F² = 2 del EMCCD;
- un "suelo Δx/√12";
- ajustes ponderados que no existen.

**Qué dice la bibliografía cargada.**
- **Forma del CRLB.** Richter (MINFLUX, Lic. 2020), p. 21: el CRB se obtiene de la matriz de información de Fisher, Σ ≥ Σ_CRB = I⁻¹, y *"σCRB states the mean of the standard deviations in x and y"*. En p. 51 compara con el CRB de cámara con y sin fondo (SBR). No da la expresión de cámara con fondo ni el factor de exceso de ruido del EMCCD.
- **F² del EMCCD.** No está en la hoja de datos cargada (`Andor_iXon3_885_Specifications.pdf`), que confirma *"14 bit @ 35, 27 & 13 MHz readout rate"* (p. 2) y la geometría de 8 µm, ni en otra fuente.
- **Deconvolución antes de localizar.** Pereyra (banco de INS-UNSAM), p. 49 (folio 48), localiza con Picasso sobre imágenes confocales y escribe: *"En el futuro, esta limitación podría ser superada mediante la implementación de un algoritmo de deconvolución que permita obtener una representación más nítida de la estructura original."* Es coherente con la respuesta 5 del investigador: RL antes de Picasso está permitido, con advertencia.
- **Suelo Δx/√12, pinhole a/√3, ajuste ponderado, RL con `clip`, detección sobre la imagen de visualización, A₀ = 4πσ² y watershed:** no cubiertos.

**Veredicto.** **NO CUBIERTO** en lo sustancial, salvo la forma general del CRLB (Fisher, σ por componente) y la política RL → Picasso, que Pereyra respalda como línea del grupo y que el investigador ya decidió. Las correcciones de D-39 siguen apoyándose en la derivación de la auditoría y en literatura externa (Rieger & Stallinga, Mortensen; paso 3).

**Pregunta al investigador.** ¿Se incorpora a `docs/bibliografia/` una referencia de CRLB para EMCCD con fondo (p. ej., Mortensen *et al.*, *Nat. Methods* 2010, o Rieger & Stallinga 2014) como fuente canónica de la metrología de localización, sí/no?

### T-21 · C-17 — `Filtro (%)` del PSF Analyzer (truncamiento que sesga el FWHM)

**Qué afirma la documentación / el código.** `analysis/psf_analyzer.py:71-82` pone a cero los píxeles bajo el 30 % y ajusta la imagen truncada, lo que sesga el FWHM −15 a −17 % (V-40). CAT-203:201 recomienda 25-30 %.

**Qué dice la bibliografía cargada.** El procedimiento del grupo para medir la cintura es un ajuste gaussiano **sin umbral**:
- Martínez, p. 64 (§3.3): *"Experimentalmente la cintura del haz ⍵ es determinada a partir de un ajuste gaussiano a imágenes iSCAT de NPs individuales. Para tener una medición exacta deben utilizarse detección sin pinhole o con un pinhole amplio, y en NPs pequeñas."*
- Martínez, p. 67: *"Para caracterizar a la cintura del haz del láser, se realizan ajustes gaussianos sobre las imágenes de ida y/o vuelta."*
- Martínez, Apéndice A.2 (p. 161-163): la deriva deforma ω en el eje lento, y se recomienda usar la proyección sobre el eje rápido.
- Ninguna fuente usa un umbral previo al ajuste.

**Veredicto.** **PARCIAL.** La bibliografía no trata el sesgo por truncamiento, pero el método documentado del grupo (ajuste gaussiano de la imagen completa, pinhole amplio, NP pequeña, eje rápido) no incluye filtro. Eso respalda un valor por defecto de 0 %. El Apéndice A.2 agrega un criterio que el PSF Analyzer no aplica: medir ω sobre el eje rápido.

**Pregunta al investigador.** ¿Se fija `Filtro (%) = 0` como valor por defecto del PSF Analyzer y del confocal, sí/no?

### T-22 · C-23 / C-24 — Fotometría LoG (A₀ = 2πσ² frente a 4πσ²; máscaras distintas)

**Qué afirma el código.** Con menos de tres monómeros aislados, el área LoG de referencia es 2πσ² (debería ser 4πσ²), y cada monómero se clasifica como dímero (V-42). La firma y la inspección usan máscaras distintas, lo que sesga r_V en −20 %.

**Qué dice la bibliografía cargada.** Nada sobre clasificación de multiplicidad por LoG ni por fotometría de manchas. Los trabajos del grupo identifican dímeros por SEM o por espectroscopía de dispersión (Gargiulo cap. 6; *Nano Lett.* 2017). Pereyra (p. 51) cuenta partículas impresas sin clasificar multiplicidad.

**Veredicto.** **NO CUBIERTO.** El error de A₀ es una derivación matemática: el LoG de una gaussiana de σ, filtrada con σ, cruza por cero en r = 2σ. La bibliografía no la puede confirmar ni refutar.

**Pregunta al investigador.** ¿El método "LoG" puede retirarse de la GUI hasta que tenga un test de extremo a extremo, y dejarse sólo "Distancia + Fotometría", sí/no?

### T-23 · C-40 — "Anisotropía" g = 2(I∥ − I⊥)/(I∥ + 2I⊥)

**Qué afirma el código.** `core/sif_processor.py:1762-1797` usa una fórmula híbrida. El factor 2 del numerador viene del factor de disimetría de CD; el 2I⊥ del denominador, de la anisotropía de fluorescencia r.

**Qué dice la bibliografía cargada.**
- "Polarization anisotropy" aparece sólo como técnica de termometría con fluoróforos (Baffou *et al.*, *Opt. Express* 2009, citado en *ACS Sens.* 2024, p. 2, y en Barella 2021), **sin fórmula** en los textos cargados.
- El grupo mide dispersión polarizada de NP individuales (Gargiulo, Fig. 4.3d; *Nano Lett.* 2016, crecimiento dirigido por polarización) sin definir un índice de anisotropía.

**Veredicto.** **NO CUBIERTO.** La bibliografía no ofrece la definición. La elección depende del observable: el grado de polarización lineal de la dispersión, P = (I∥−I⊥)/(I∥+I⊥), o la anisotropía de emisión, r = (I∥−I⊥)/(I∥+2I⊥).

**Pregunta al investigador.** ¿El observable buscado en el Analizador SIF es el grado de polarización lineal de la dispersión, P = (I∥ − I⊥)/(I∥ + I⊥), sí/no?

### T-24 · C-47 — Filtro de rayos cósmicos por mediana (w = 5)

**Qué afirma el código.** `core/raman_engine.py:211-245` aplica una mediana de 5 píxeles que se come entre el 10 y el 80 % del área de bandas con FWHM ≤ 4 px.

**Qué dice la bibliografía cargada.** Arias (INS-UNSAM), p. 106 (folio 94), describe el preprocesamiento SERS del grupo. No especifica el método de remoción de rayos cósmicos, pero sí da los demás parámetros:
- Recorte a 600-1250 cm⁻¹.
- *"cuando corresponde, se eliminan los rayos cósmicos, señales espurias generadas por partículas de alta energía que impactan en la cámara CCD."*
- Suavizado Savitzky-Golay *"utilizando un polinomio de orden 5 y una ventana de 24 cm⁻¹"*.
- Línea de base por ALS *"con parámetros de suavidad λ = 10⁻² y ponderación asimétrica p = 0.001"*.

Además, ese equipo no es el del banco de impresión: es un Horiba iHR320 con láser de 785 nm (p. 56, folio 44).

**Veredicto.** **NO CUBIERTO** para el método de rayos cósmicos. De paso, Arias aporta parámetros de referencia del grupo para el suavizado y la línea de base, que pueden contrastarse con los valores por defecto de `raman_engine`.

**Pregunta al investigador.** ¿Los rayos cósmicos deben removerse por comparación entre adquisiciones repetidas (y no por mediana espectral), sí/no?

### T-25 · C-52 / D-38 — Parámetro de orden orientacional ψ_n (local frente a global)

**Qué afirma el código.** Se reporta ⟨|ψ_n|⟩ (local), que vale 0.37 para un gas ideal. La métrica global |⟨ψ₃⟩| vale 0 en una honeycomb perfecta, y las tablas de fase de CAT-313 no aplican.

**Qué dice la bibliografía cargada.** Nada. No aparece "bond-orientational", "ψ₆", "hexatic" ni "KTHNY". Los trabajos coloidales de redes cargados caracterizan el orden con FFT, g(r) o RDF (Volk *et al.* 2021, p. 3; *Langmuir* 2020, p. 5).

**Veredicto.** **NO CUBIERTO.**

**Pregunta al investigador.** ¿Se reporta la métrica global |⟨ψ_n⟩| junto con la local, y se retiran las tablas de fase de CAT-313 hasta tener fuente, sí/no?

### T-26 · D-40 / D-41 — Formatos de datos e implementaciones inexistentes

No son inconsistencias teóricas: son hechos de código y de estado de implementación. Quedan **FUERA DE ALCANCE** de este triage. D-41 ya tiene la política de la respuesta 11 del investigador: archivar como "implementable" o "desconocido".

---

## Hallazgos colaterales (no teóricos) que la bibliografía cargada permite fijar

Surgieron al leer las tesis y afectan hallazgos de hardware del consolidado. Se consignan porque la regla 12 del investigador pide revisar toda afirmación de la auditoría antes de aceptarla.

1. **D-11 (láser verde) queda en duda.**
   - El consolidado afirma "Laser Quantum Ventus (no Spectra-Physics Excelsior)" según las tesis. Pero Ventus (532) y MPB (640) son del microscopio de **CIBION**: Gargiulo, p. 49, *"532nm (Laser Ventus) and 640nm (MPB)"*.
   - La única tesis hecha en el banco de **INS-UNSAM**, Pereyra (2025), p. 30 (folio 29), dice: *"un láser verde Excelsior-532-150-CDRH"*, y agrega *"un láser rojo y uno IR"* sin identificarlos.
   - Es probable que SYS-203 (Excelsior) sea correcto para INS-UNSAM. Conviene confirmarlo con la placa del cabezal.
2. **Filtro de densidad (respuesta 2 del investigador).**
   - Pereyra, p. 38 (folio 37): *"Ambos procesos* [ajuste de foco y escaneo 2D posterior a cada impresión] *se ejecutan con un filtro de densidad neutra activo para irradiar la muestra a baja potencia. Esta precaución garantiza que no se impriman nuevas partículas durante el ajuste de foco"*. Confirma la semántica que da el investigador y la relevancia de C-31.
   - Martínez, p. 55, lo describe como *"flipper motorizado en el camino de la excitación para trabajar alternativamente con potencias más bajas"*.
   - En el esquema de Pereyra (Fig. 2.1, p. 30), el notch de 532 nm (NF 532) aparece **fijo** en el camino de detección, antes del canal confocal.
3. **Detección del evento de impresión (D-01).** Pereyra, p. 37 (folio 36), define el umbral como el cociente u = I(t₀+τ)/I(t₀), vigilado como *"un cociente móvil … donde dt es un intervalo de tiempo corto, típicamente entre 10 y 100 ms"*. Es otra evidencia contra la latencia "< 1 ms" de la documentación.
4. **Platina (BANCO-17).**
   - La P-545 de las tesis es la de CIBION: Gargiulo, p. 49, *"a range of 200 µm in the three axes"*; Chiarelli, p. 30, *"PI nano XYZ P-545"*.
   - Pereyra (INS) sólo dice que la platina piezoeléctrica se conecta por USB (p. 35, folio 34), sin modelo. La bibliografía no decide entre P-545 y P-517.3CD para el banco de INS-UNSAM.
5. **Microscopio Raman del INS distinto del banco de impresión.**
   - Arias (p. 55-56) describe *"un láser de diodo de 785 nm (IPS …)"*, un *"espectrómetro Horiba iHR320, acoplado a un detector CCD Synapse Plus"* y un objetivo Nikon 40x/0.60. Es un posible origen de las menciones a 785 nm y a otros equipos en la documentación (D-11).
   - La torreta "Nikon 40x 0.60" del código (D-21) coincide con ese objetivo de Arias, no con el banco de impresión.
6. **Ventana espectral.** Martínez, p. 60: *"La resolución de la red de difracción es de 1 nm, y el rango espectral que se proyecta en la cámara es de 103 nm"* (red usada para los espectros de dispersión). Es una confirmación independiente del pitch de 8 µm (DEC-033).

