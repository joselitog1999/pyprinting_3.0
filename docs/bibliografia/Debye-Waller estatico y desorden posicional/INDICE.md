# Debye-Waller estático y desorden posicional — índice bibliográfico

Carpeta de apoyo al método Monte Carlo del laboratorio (INS-UNSAM / CONICET) que busca cuantificar el
desorden posicional de redes 2D de nanopartículas de Au/Ag impresas ópticamente (cuadradas, hexagonales, honeycomb)
a partir del factor de estructura y la atenuación de los picos de Bragg, con un factor de Debye-Waller **estático**
(desplazamientos congelados).

**Criterios.** Cada referencia se verificó contra Crossref (`api.crossref.org/works/<DOI>`) y, cuando corresponde,
contra la API de arXiv. El estado de acceso abierto se consultó en OpenAlex. Sólo se descargaron PDFs de acceso
abierto legítimo (arXiv, repositorios institucionales, versión libre del editor). Cada archivo descargado se comprobó
por su cabecera `%PDF`. Cuando un trabajo es de acceso abierto pero el servidor bloquea la descarga automática
con una verificación anti-bot, se indica "sin PDF local (OA, descargar a mano)" con el enlace.

Temas: **1** Debye-Waller estático · **2** desorden tipo I frente a tipo II (paracristal) · **3** error de
localización · **4** vacancias · **5** desorden en redes plasmónicas (SLR) · **6** Monte Carlo / inversión de σ.

---

## Nota sobre la convención del Debye-Waller estático

Relación común a las fuentes leídas que dan la fórmula ([1] Ec. 27, [2] Ec. 6, [3] Ecs. 10 y 26), para
desplazamientos independientes e idénticamente distribuidos con densidad de probabilidad f(**u**):

- La **amplitud** de cada pico de Bragg se multiplica por la función característica f̃(**q**) = ⟨exp(i **q**·**u**)⟩ y la
  **intensidad** por |f̃(**q**)|². La fracción que se pierde, 1 − |f̃(**q**)|², reaparece como fondo difuso
  (con la normalización de [2], S(q) → 1 para q grande).
- Gaussiana isótropa con varianza σ² **por componente cartesiana** (⟨u_x²⟩ = ⟨u_y²⟩ = σ²): f̃(**q**) = exp(−q²σ²/2), y la
  intensidad se atenúa por **exp(−q²σ²)**. Es la forma que da [1] en la Sec. VIII (1D: exp[−k²G(0)], con G(0) la
  varianza).
- En función del desplazamiento cuadrático medio **total** ⟨|**u**|²⟩ = d·σ², la misma atenuación es
  exp(−q²⟨|**u**|²⟩/d): exp(−q²⟨|**u**|²⟩/2) en 2D y exp(−q²⟨|**u**|²⟩/3) en 3D. Es la forma de [1], Ec. (24), a orden q².

Tres maneras de introducir un factor ½ (o 2/3) espurio; las convenciones en juego aparecen en la literatura reunida: (a) confundir la
amplitud ([3], T(G)) con la intensidad ([1], [2]), lo que cambia el exponente en un factor 2; (b) usar σ² por componente
donde corresponde ⟨|**u**|²⟩ total, o al revés (factor 2 en 2D), o aplicar el ÷3 de la fórmula isótropa 3D a una red 2D
(factor 2/3); (c) confundir la varianza de **un sitio** con la de la **separación de un par** de sitios, que es el doble
(de ahí el ensanchamiento √2·σ de g(r) en [5]).

Convención que usa cada fuente leída:

| Fuente | Qué cantidad usa | Factor sobre la intensidad de Bragg |
| :--- | :--- | :--- |
| Gabrielli 2004 [1] (Sec. VIII) | G(0) = varianza del desplazamiento en 1D (**por componente**); en d dimensiones, matriz G_μν | exp[−k²G(0)] = \|p̂(k)\|², con amplitud p̂ = exp[−k²G(0)/2] |
| Gabrielli 2004 [1] (Ec. 24) | ⟨u²⟩ **total** de un desplazamiento isótropo en d dimensiones | a orden k²: \|p̂\|² ≈ 1 − k²⟨u²⟩/d (coincide con lo anterior si ⟨u²⟩ = d·G(0)) |
| Klatt et al. 2020 [2] (Ec. 6) | función característica f̃ de la distribución completa (sin suponer gaussiana) | \|f̃(k)\|² |
| Paddison 2019 [3] (Ec. 26) | promedio empírico ⟨exp(iG·u)⟩ sobre la supercélula (**amplitud**) | \|T(G)\|² |
| Veatch et al. 2012 [5] (Ec. 1) | σ = desviación estándar **por componente** del error de localización (PSF gaussiana 2D) | no trata Bragg; g(r) se convoluciona con una gaussiana de varianza 2σ² por componente |
| Dullens y Petukhov 2007 [10] | no da fórmula; atribuyen al Debye-Waller la caída del **área** de los picos. Su red de referencia usa un módulo de desplazamiento uniforme en [0, 0,2 µm] con dirección al azar (⟨\|u\|²⟩ = (0,2 µm)²/3 total) | — |
| Zakomirnyi et al. 2019 [8] | desplazamiento uniforme e independiente por eje (varianza δ²/3 si el intervalo es [−δ, δ]) | — (cálculo óptico, no de difracción) |
| Kravets et al. 2018 [7] (Fig. 10, tomada de [15]) | desorden expresado como "desviación" en % del período, sin especificar distribución ni si es por componente | — |
| Trueblood et al. 1996 [19] | autoridad de la IUCr sobre U y B; **no leído** | pendiente |

Las filas de [7], [8] y [10] muestran que el "grado de desorden" publicado para redes plasmónicas y coloidales suele darse
con distribuciones uniformes o como porcentaje del período, **no** como σ gaussiana. Para comparar con el σ del
laboratorio hay que convertir a varianza por componente y recordar que, para distribuciones no gaussianas, la
atenuación de Bragg no es exp(−q²σ²): puede incluso anularse y reaparecer al crecer el desorden ([2], Fig. 4).

---

## Entradas

### 1. Gabrielli (2004) — Point processes and stochastic displacement fields

- **Cita:** A. Gabrielli, "Point processes and stochastic displacement fields", *Physical Review E* **70**, 066131 (2004).
- **DOI / arXiv:** [10.1103/PhysRevE.70.066131](https://doi.org/10.1103/PhysRevE.70.066131) · arXiv:[cond-mat/0409594](https://arxiv.org/abs/cond-mat/0409594)
- **Acceso abierto:** https://arxiv.org/pdf/cond-mat/0409594 (preprint arXiv)
- **Archivo local:** `2004_Gabrielli_stochastic-displacement-fields.pdf`
- **Tema:** 1, 2
- **Relevancia:** Derivación exacta (sin aproximación de desplazamientos pequeños) del espectro de potencia de una red
  "barajada" (*shuffled lattice*) por desplazamientos independientes, y también por un campo de desplazamientos
  gaussiano **correlacionado**. Es la base teórica más limpia del modelo tipo I del laboratorio y muestra cómo aparece
  la correlación entre desplazamientos (el paso hacia el tipo II) en el término G(0) − G(x).
- **Ecuaciones clave (leídas):** Ec. (27): S(k) = n₀[1 − |p̂(k)|²] + (2π)^d n₀² Σ_{H≠0} |p̂(H)|² δ(k − H), con p̂ la
  función característica de la densidad de un desplazamiento (Bragg modulado por |p̂|², el resto pasa al difuso).
  Sec. VIII (campo gaussiano): para desplazamientos no correlacionados f̂(k,−k;0) = exp[−k²G(0)] = |p̂(k)|² con
  p̂(k) = exp[−k²G(0)/2], donde G(0) es la varianza del desplazamiento (1D, es decir **por componente**). En d
  dimensiones el factor de pares es exp{−k_μk_ν[G_μν(0) − G_μν(x)]}. Ec. (24) (p. 7, verificada sobre la página
  renderizada): para desplazamientos isótropos de varianza finita, p̂(k) ≈ 1 − Bk² con **B = ⟨u²⟩/(2d)**, donde ⟨u²⟩ es el
  desplazamiento cuadrático medio **total** en d dimensiones; de ahí 1 − |p̂|² ≈ k²⟨u²⟩/d. Misma página: tras m
  aplicaciones sucesivas de desplazamientos no correlacionados, S_m = n₀(1 − |p̂|^{2m}) + |p̂|^{2m} S_in. Fig. 3 verifica la
  Ec. (27) con simulación.

### 2. Klatt, Kim y Torquato (2020) — Cloaking the underlying long-range order of randomly perturbed lattices

- **Cita:** M. A. Klatt, J. Kim, S. Torquato, "Cloaking the underlying long-range order of randomly perturbed lattices", *Physical Review E* **101**, 032118 (2020).
- **DOI / arXiv:** [10.1103/PhysRevE.101.032118](https://doi.org/10.1103/PhysRevE.101.032118) · arXiv:[2001.08161](https://arxiv.org/abs/2001.08161)
- **Acceso abierto:** https://arxiv.org/pdf/2001.08161
- **Archivo local:** `2020_Klatt_randomly-perturbed-lattices.pdf`
- **Tema:** 1, 6
- **Relevancia:** Fórmula general del factor de estructura de una red de Bravais con desplazamientos i.i.d. de
  distribución arbitraria, verificada con simulaciones 2D de 10⁴ puntos. Advierte que para distribuciones no
  gaussianas (p. ej. uniforme en la celda) el peso de Bragg |f̃(k)|² **no decae monótonamente** con la intensidad del
  desorden: puede anularse y reaparecer. Es una advertencia directa para invertir σ a partir de la atenuación de un
  solo orden si no se conoce la forma de la distribución.
- **Ecuaciones clave (leídas):** Ec. (6): S(k) = 1 − |f̃(k)|² + |f̃(k)|² S_L(k), con S_L el factor de estructura de la
  red perfecta y f̃ la función característica (derivación en el Apéndice A). Fig. 4: pesos de los tres primeros
  picos de Bragg en 2D en función de la intensidad de perturbación uniforme.

### 3. Paddison (2019) — Ultrafast calculation of diffuse scattering from atomistic models

- **Cita:** J. A. M. Paddison, "Ultrafast calculation of diffuse scattering from atomistic models", *Acta Crystallographica Section A* **75**, 14–24 (2019).
- **DOI / arXiv:** [10.1107/S2053273318015632](https://doi.org/10.1107/S2053273318015632) · arXiv:[1809.07088](https://arxiv.org/abs/1809.07088)
- **Acceso abierto:** https://arxiv.org/pdf/1809.07088
- **Archivo local:** `2019_Paddison_diffuse-scattering-calculation.pdf`
- **Tema:** 6, 1, 4
- **Relevancia:** Receta computacional para calcular la intensidad de Bragg y difusa de configuraciones Monte Carlo con
  FFT, promediando sobre muchas supercélulas. Discute los artefactos de tamaño finito y muestra que una muestra con
  **bordes abiertos** (como una red impresa finita) pondera los pares con una función de corte triangular, lo que
  ensancha los picos: hay que modelar este efecto antes de atribuir el ancho al desorden.
- **Ecuaciones clave (leídas):** Ec. (9)–(10): I = (1/N)|⟨F⟩|² + (1/N)⟨|F − ⟨F⟩|²⟩ (Bragg a partir del promedio, difuso a partir
  de la varianza). Ec. (26): factor de Debye-Waller empírico T(G) = (1/n₁n₂n₃) Σ_R (1 + a_R) exp(iG·u_R), es decir,
  promedio sobre la supercélula de exp(iG·u) a nivel de **amplitud** (sin suponer gaussianidad), que incluye la
  ocupación a_R. Ec. (27)–(29): desorden de ocupación (vacancias). Sec. V A: sub-cajas y corte triangular.

### 4. Welberry y Goossens (2014) — Diffuse scattering and partial disorder in complex structures

- **Cita:** T. R. Welberry, D. J. Goossens, "Diffuse scattering and partial disorder in complex structures", *IUCrJ* **1**, 550–562 (2014).
- **DOI:** [10.1107/S205225251402065X](https://doi.org/10.1107/S205225251402065X) (acceso abierto dorado, CC BY 2.0 UK; también en PMC4224473)
- **Acceso abierto:** https://journals.iucr.org/m/issues/2014/06/00/zx5002/zx5002.pdf
- **Archivo local:** `2014_Welberry_diffuse-scattering-partial-disorder.pdf`
- **Tema:** 6, 1
- **Relevancia:** Reseña de referencia sobre cómo se modela la dispersión difusa con simulaciones Monte Carlo y cómo se
  **refinan** los parámetros del modelo contra los datos (mínimos cuadrados, algoritmos evolutivos, MC inverso). Es el
  marco metodológico más cercano al método que el laboratorio está desarrollando: simular configuraciones, calcular
  el patrón y comparar con un factor R.
- **Secciones clave (leídas):** Sec. 3.1 (Monte Carlo con constantes de resorte; tamaño típico de simulación
  64 × 64 × 64 celdas y ~5000 ciclos MC, Sec. 3.1.3); Sec. 3.1.2 (desorden de ocupación y relajación por efecto de
  tamaño); Sec. 3.4 (estrategias de refinamiento, pasos 1–6 del bucle "modelo → patrón → R → nuevos parámetros", y
  advertencia de que la definición del R y el criterio para decidir qué píxeles pertenecen al pico de Bragg
  condicionan el resultado).

### 5. Veatch et al. (2012) — Correlation functions quantify super-resolution images and estimate apparent clustering due to over-counting

- **Cita:** S. L. Veatch, B. B. Machta, S. A. Shelby, E. N. Chiang, D. A. Holowka, B. A. Baird, "Correlation Functions Quantify Super-Resolution Images and Estimate Apparent Clustering Due to Over-Counting", *PLoS ONE* **7**, e31457 (2012).
- **DOI / arXiv:** [10.1371/journal.pone.0031457](https://doi.org/10.1371/journal.pone.0031457) · arXiv:[1106.6068](https://arxiv.org/abs/1106.6068) (acceso abierto dorado, CC BY 4.0)
- **Acceso abierto:** https://journals.plos.org/plosone/article/file?id=10.1371/journal.pone.0031457&type=printable
- **Archivo local:** `2012_Veatch_pair-correlation-localization-error.pdf`
- **Tema:** 3
- **Relevancia:** Muestra explícitamente cómo el error de localización gaussiano (desviación σ por componente) convoluciona
  la función de correlación de pares medida: como la separación entre dos posiciones ruidosas tiene varianza 2σ² por
  componente, g(r) queda suavizada por una gaussiana de ancho √2·σ. Es el análogo en espacio real de la atenuación de
  Bragg por error de medición, y permite separar el ruido de localización del desorden real si σ_loc se calibra aparte.
- **Ecuaciones clave (leídas):** PSF gaussiana de desviación σ, con g_psf(r) = exp(−r²/4σ²)/(4πσ²). Ec. (1):
  g_meas(r) = exp(−r²/4σ²)/(4πσ²ρ) + g(r>0) ⊛ g_psf(r) (el primer término es el sobreconteo, ∝ 1/ρ). Ec. (2): caso de
  moléculas al azar. La deducción completa está en *Materials and Methods*.

### 6. Filippi et al. (2026) — Sinusoidal displacement describes disorder in CsPbBr₃ nanocrystal superlattices

- **Cita:** U. Filippi, S. Toso, M. G. Ferreira, L. Tallarini, Y. P. Ivanov, F. Scattarella, S. Lauciello, V. Haghighat, H. Chen, M. Landberg, G. Divitini, J. Wallentin, C. Giannini, L. Manna, D. Baranov, "Sinusoidal Displacement Describes Disorder in CsPbBr₃ Nanocrystal Superlattices", *ACS Nano* **20**(4), 3867–3877 (2026).
- **DOI / arXiv:** [10.1021/acsnano.5c20745](https://doi.org/10.1021/acsnano.5c20745) · arXiv:[2509.10849](https://arxiv.org/abs/2509.10849) (versión del editor CC BY 4.0; también PMC12874646)
- **Acceso abierto:** https://arxiv.org/pdf/2509.10849 (se descargó el preprint arXiv; la versión publicada es libre en el sitio de ACS)
- **Archivo local:** `2026_Filippi_cumulative-disorder-superlattices.pdf` (preprint arXiv)
- **Tema:** 2
- **Relevancia:** Trabajo reciente sobre superredes de nanopartículas coloidales que usa el criterio clásico para distinguir
  desorden **acumulativo** (tipo II, paracristal: el ancho del pico crece con el orden de difracción) de desorden
  "térmico", no correlacionado (tipo I: ancho constante, limitado por la resolución). Muestra además un caso mixto en el
  que un modelo de desplazamiento sinusoidal (análogo a un fonón acústico congelado) conecta ambos regímenes.
- **Secciones clave (leídas):** Fig. 2f–h y el párrafo "GISAXS Evidence of Cumulative Disorder": ancho de pico Δq_z en
  función del orden (crece con el orden en todas las muestras salvo la menos blanda, que queda limitada por la
  resolución). Ecs. (1)–(4): modelo de desplazamientos longitudinal y transversal sinusoidales. Cita a Eads y Millane
  (2001) y a Vegso et al. (2014) para el modelo paracristalino.

### 7. Kravets, Kabashin, Barnes y Grigorenko (2018) — Plasmonic surface lattice resonances: a review of properties and applications

- **Cita:** V. G. Kravets, A. V. Kabashin, W. L. Barnes, A. N. Grigorenko, "Plasmonic Surface Lattice Resonances: A Review of Properties and Applications", *Chemical Reviews* **118**(12), 5912–5951 (2018).
- **DOI:** [10.1021/acs.chemrev.8b00243](https://doi.org/10.1021/acs.chemrev.8b00243) (ACS AuthorChoice, acceso abierto; también PMC6026846)
- **Acceso abierto:** https://amu.hal.science/hal-02137917v1/file/chem%20rev%202019%20Kabashin.pdf (HAL; es el PDF del editor con licencia AuthorChoice)
- **Archivo local:** `2018_Kravets_surface-lattice-resonances-review.pdf`
- **Tema:** 5
- **Relevancia:** Reseña de referencia sobre resonancias de red superficiales (SLR). Tiene secciones dedicadas al efecto
  del tamaño finito del arreglo y del desorden posicional y de tamaño, que conectan la magnitud física que el
  laboratorio quiere medir (σ) con la calidad de la resonancia colectiva que se busca en las redes impresas.
- **Secciones clave (leídas):** Sec. 3.4 (tamaño del arreglo: según el modelo de dipolos acoplados de Rodriguez et al.,
  el factor Q de la SLR crece con el tamaño y "satura para arreglos de unos pocos cientos de partículas"; la Fig. 9 lo
  grafica en función del número N de partículas por lado). Sec. 3.5.1 (desorden posicional, pp. 5922–5923; Fig. 10: al aumentar el
  desplazamiento aleatorio, el pico estrecho se debilita y se corre al azul, reproducido con un modelo de dipolos
  acoplados de 441 dipolos). Sec. 3.5.2 (desorden de tamaño, Fig. 11).

### 8. Zakomirnyi, Karpov, Ågren y Rasskazov (2019) — Collective lattice resonances in disordered and quasi-random all-dielectric metasurfaces

- **Cita:** V. I. Zakomirnyi, S. V. Karpov, H. Ågren, I. L. Rasskazov, "Collective lattice resonances in disordered and quasi-random all-dielectric metasurfaces", *Journal of the Optical Society of America B* **36**(7), E21 (2019).
- **DOI:** [10.1364/JOSAB.36.000E21](https://doi.org/10.1364/JOSAB.36.000E21)
- **Acceso abierto:** https://elib.sfu-kras.ru/bitstream/2311/128875/1/355522.pdf (repositorio institucional de la Universidad Federal de Siberia; manuscrito de autor)
- **Archivo local:** `2019_Zakomirnyi_disordered-metasurfaces-CLR.pdf` (manuscrito de autor, puede diferir en detalles de la versión publicada)
- **Tema:** 5, 4
- **Relevancia:** Estudio con dipolos acoplados de redes 2D con tres tipos de imperfección que el laboratorio necesita
  distinguir: desorden posicional (por eje x o y), desorden de tamaño y **eliminación aleatoria de partículas**
  (vacancias). Aunque las partículas son de Si, el formalismo y las conclusiones para el dipolo eléctrico son
  trasladables a Au/Ag; el resultado de que la resonancia colectiva sobrevive a la eliminación de hasta el 84 % de las
  partículas es un contraste útil con la sensibilidad al desorden posicional.
- **Secciones clave (leídas):** Sec. 2 (ecuaciones de dipolos acoplados, Ecs. 1–6). Sec. 4 y Fig. 3: desorden posicional
  generado con **distribución uniforme** e independiente por partícula (si el intervalo es [−δ, δ], la varianza por
  componente es δ²/3; no es gaussiana); desorden de tamaño; Sec. 4 D "Quasi-random arrays": red de 30 × 30 a la que se
  le quitan 171, 459 o 756 partículas. Cada configuración se simuló una sola vez, sin promedio de ensamble.

### 9. De Zuani et al. (2017) — Large-area two-dimensional plasmonic meta-glasses and meta-crystals: a comparative study

- **Cita:** S. De Zuani, M. Rommel, R. Vogelgesang, J. Weis, B. Gompf, M. Dressel, A. Berrier, "Large-Area Two-Dimensional Plasmonic Meta-Glasses and Meta-Crystals: a Comparative Study", *Plasmonics* **12**(5), 1381–1390 (2017).
- **DOI:** [10.1007/s11468-016-0397-9](https://doi.org/10.1007/s11468-016-0397-9) (acceso abierto, CC BY 4.0; también PMC5599453)
- **Acceso abierto:** https://link.springer.com/content/pdf/10.1007/s11468-016-0397-9.pdf
- **Archivo local:** `2017_DeZuani_plasmonic-metaglasses-metacrystals.pdf`
- **Tema:** 5
- **Relevancia:** Compara experimentalmente arreglos de discos de Au periódicos y aleatorios de igual densidad y muestra que
  la respuesta óptica lejos de los efectos difractivos depende sobre todo de la densidad y de la función de distribución
  radial. Da la forma en que la suma dipolar ("factor de estructura" óptico) de un arreglo desordenado se escribe con
  g(r), lo que permite conectar una medición de g(r) o de σ con el corrimiento y el ancho de la resonancia.
- **Ecuaciones clave (leídas):** Ec. (3): suma dipolar retardada S_per sobre los pares de una red periódica. Ec. (4)
  (formulación de Antosiewicz y Tarkowski): la misma suma para un arreglo aleatorio como integral sobre la función de
  distribución radial G(r).

### 10. Dullens y Petukhov (2007) — Second-type disorder in colloidal crystals

- **Cita:** R. P. A. Dullens, A. V. Petukhov, "Second-type disorder in colloidal crystals", *Europhysics Letters (EPL)* **77**, 58003 (2007).
- **DOI:** [10.1209/0295-5075/77/58003](https://doi.org/10.1209/0295-5075/77/58003)
- **Acceso abierto:** https://dspace.library.uu.nl/handle/1874/26635 (repositorio de la Universidad de Utrecht; PDF del editor)
- **Archivo local:** `2007_Dullens_second-type-disorder-colloidal-crystals.pdf`
- **Tema:** 2, 6, 3
- **Relevancia:** Es el antecedente metodológico más parecido al del laboratorio: parten de **coordenadas medidas en
  espacio real** (microscopía confocal de la primera capa, bidimensional, de cristales coloidales de esferas y
  poliedros), calculan S(q) numéricamente, ajustan los picos (h0)
  con lorentzianas y usan el FWHM en función del orden para separar desorden de primera especie (Debye-Waller: cae el
  área del pico, no el ancho) de desorden de segunda especie (el ancho crece con q) y de efectos de tamaño finito
  (ensanchamiento independiente de q). Validan el análisis con una "red de referencia" simulada con vacancias y
  desorden de tipo I sobre las mismas coordenadas, que es exactamente un control Monte Carlo.
- **Ecuaciones y secciones clave (leídas):** Ec. (1): g(**r**) bidimensional. Ec. (2): S(**q**) = (1/N)|Σₙ exp(i**q**·**r**ₙ)|²
  calculado sobre una grilla con paso π/L (L = tamaño de la imagen; verificado sobre la página renderizada), con ruido de speckle y franjas por tamaño finito.
  Fig. 2: perfiles radiales y ajuste lorentziano; el FWHM relativo Δq/q₍₁₀₎ de las esferas pasa de 0,018 en (10) a 0,033
  en (30). Fig. 3 y 4: "red de referencia" (red hexagonal perfecta ajustada a los datos, con vacancias, y desplazamiento de
  módulo **uniforme en [0, 0,2 µm] con dirección aleatoria**, que no es una gaussiana isótropa) y FWHM frente al orden.
  Clasificación de Guinier del desorden (1ª especie, 2ª especie, tamaño finito) en la introducción.

### 11. Millane y Eads (2000) — Diffraction by one-dimensional paracrystals and perturbed lattices

- **Cita:** R. P. Millane, J. L. Eads, "Diffraction by one-dimensional paracrystals and perturbed lattices", *Acta Crystallographica Section A* **56**(5), 497–506 (2000).
- **DOI:** [10.1107/S0108767300008138](https://doi.org/10.1107/S0108767300008138)
- **Acceso abierto:** no (OpenAlex: cerrado).
- **Archivo local:** sin PDF (muro de pago)
- **Tema:** 2
- **Relevancia:** Comparación detallada, en 1D, del paracristal (desorden acumulativo, tipo II) y de la red perturbada
  (desorden no acumulativo, tipo I). Según el resumen, si al paracristal se le suma desorden térmico ambos modelos dan
  difracciones parecidas pero no idénticas, coinciden en los límites de correlación fuerte o débil, y para cristalitos
  pequeños con parámetros adecuados dan difracción prácticamente idéntica; derivan una relación empírica entre los
  parámetros de ambos modelos. Es la advertencia central para el laboratorio: en redes impresas **finitas**, tipo I y
  tipo II pueden ser difíciles de distinguir sólo por el ensanchamiento.
- **Leído:** no (sólo resumen).

### 12. Eads y Millane (2001) — Diffraction by the ideal paracrystal

- **Cita:** J. L. Eads, R. P. Millane, "Diffraction by the ideal paracrystal", *Acta Crystallographica Section A* **57**(5), 507–517 (2001).
- **DOI:** [10.1107/S0108767301006341](https://doi.org/10.1107/S0108767301006341)
- **Acceso abierto:** no (OpenAlex: cerrado).
- **Archivo local:** sin PDF (muro de pago)
- **Tema:** 2
- **Relevancia:** Análisis de la estadística y la difracción de un paracristal ideal **bidimensional y finito**, con los casos
  particulares de redes **cuadrada y hexagonal**, y de cómo varía el ancho de los picos con el ángulo de dispersión según
  la dirección en el espacio recíproco (según el resumen). Es la referencia más directa para las geometrías que imprime
  el laboratorio; es citada por Filippi et al. [6] como base del criterio ancho-frente-a-orden.
- **Leído:** no (sólo resumen).

### 13. Rivnay, Noriega, Kline, Salleo y Toney (2011) — Quantitative analysis of lattice disorder and crystallite size in organic semiconductor thin films

- **Cita:** J. Rivnay, R. Noriega, R. J. Kline, A. Salleo, M. F. Toney, "Quantitative analysis of lattice disorder and crystallite size in organic semiconductor thin films", *Physical Review B* **84**, 045203 (2011).
- **DOI:** [10.1103/PhysRevB.84.045203](https://doi.org/10.1103/PhysRevB.84.045203)
- **Acceso abierto:** no (OpenAlex: cerrado; no se encontró preprint en arXiv).
- **Archivo local:** sin PDF (muro de pago)
- **Tema:** 2, 6
- **Relevancia:** Separación cuantitativa entre tamaño de cristalito y desorden acumulativo con el método de Warren-Averbach,
  **con propagación de errores e intervalos de confianza**, y un análisis más simple basado en la tendencia del ancho de
  pico y de la componente lorentziana de un ajuste pseudo-Voigt en función del orden de difracción (según el resumen).
  Es el tratamiento metrológico más completo encontrado del problema "ancho por tamaño finito frente a ancho por
  desorden".
- **Leído:** no (sólo resumen). La reseña de los mismos autores, Rivnay et al., *Chem. Rev.* **112**, 5488–5519 (2012),
  DOI [10.1021/cr3001109](https://doi.org/10.1021/cr3001109), también es de acceso cerrado.

### 14. Kim y Torquato (2018) — Effect of imperfections on the hyperuniformity of many-body systems

- **Cita:** J. Kim, S. Torquato, "Effect of imperfections on the hyperuniformity of many-body systems", *Physical Review B* **97**, 054105 (2018).
- **DOI:** [10.1103/PhysRevB.97.054105](https://doi.org/10.1103/PhysRevB.97.054105)
- **Acceso abierto:** no (OpenAlex: cerrado; no se encontró la versión en arXiv).
- **Archivo local:** sin PDF (muro de pago)
- **Tema:** 4, 1
- **Relevancia:** Deriva fórmulas explícitas de S(k) a número de onda pequeño para tres tipos de imperfección de una red:
  defectos puntuales no correlacionados (**vacancias** e intersticiales), desplazamientos estocásticos y excitaciones
  térmicas armónicas, y las compara con simulaciones (según el resumen). Es la referencia para tratar a la vez
  vacancias y desplazamientos en el mismo factor de estructura, que es el caso de una red impresa con sitios fallidos.
- **Leído:** no (sólo resumen).

### 15. Auguié y Barnes (2009) — Diffractive coupling in gold nanoparticle arrays and the effect of disorder

- **Cita:** B. Auguié, W. L. Barnes, "Diffractive coupling in gold nanoparticle arrays and the effect of disorder", *Optics Letters* **34**(4), 401–403 (2009).
- **DOI:** [10.1364/OL.34.000401](https://doi.org/10.1364/OL.34.000401)
- **Acceso abierto:** OpenAlex lo marca como libre en el sitio del editor (https://opg.optica.org/ol/abstract.cfm?uri=ol-34-4-401), pero el servidor exige JavaScript y la descarga automática devolvió HTML.
- **Archivo local:** sin PDF local (descargar a mano desde el sitio de Optica)
- **Tema:** 5
- **Relevancia:** El experimento de referencia sobre el efecto del desorden posicional **controlado** (ocupación constante)
  y del desorden de tamaño en la resonancia de red de arreglos 2D de Au, interpretado con un modelo de dipolos
  acoplados. Es exactamente el tipo de dato que conecta σ medido con la calidad de la SLR. Su contenido está resumido
  en la reseña de Kravets et al. [7], Sec. 3.5 y Figs. 10–11.
- **Leído:** no directamente (resumen y la descripción en [7]).

### 16. Schokker y Koenderink (2015) — Statistics of randomized plasmonic lattice lasers

- **Cita:** A. H. Schokker, A. F. Koenderink, "Statistics of Randomized Plasmonic Lattice Lasers", *ACS Photonics* **2**(9), 1289–1297 (2015).
- **DOI:** [10.1021/acsphotonics.5b00226](https://doi.org/10.1021/acsphotonics.5b00226)
- **Acceso abierto:** no (OpenAlex: cerrado).
- **Archivo local:** sin PDF (muro de pago)
- **Tema:** 5, 4
- **Relevancia:** Parte de una red cuadrada difractiva de nanopartículas de Ag y aumenta el desorden **quitando partículas
  y desplazándolas**; la emisión láser en la condición de Bragg de segundo orden persiste aun con el 99 % de las
  partículas eliminadas, y clasifica el patrón de Fourier con cálculos de factor de estructura (según el resumen).
  Separa explícitamente vacancias de desplazamientos en una red plasmónica, igual que necesita el laboratorio.
- **Leído:** no (sólo resumen).

### 17. Savin y Doyle (2005) — Static and dynamic errors in particle tracking microrheology

- **Cita:** T. Savin, P. S. Doyle, "Static and Dynamic Errors in Particle Tracking Microrheology", *Biophysical Journal* **88**(1), 623–638 (2005).
- **DOI:** [10.1529/biophysj.104.042457](https://doi.org/10.1529/biophysj.104.042457)
- **Acceso abierto:** sí (archivo abierto de Biophys. J. y PMC1305040: https://pmc.ncbi.nlm.nih.gov/articles/PMC1305040/). El PDF de PMC y el del editor están detrás de una verificación anti-bot.
- **Archivo local:** sin PDF local (OA, descargar a mano). Se leyó la versión HTML de PMC.
- **Tema:** 3
- **Relevancia:** Formaliza el "error estático" de localización como un desplazamiento aleatorio de media nula y varianza ε²,
  independiente de la posición verdadera, y muestra cómo sesga las magnitudes derivadas. Propone medir ε con
  **partículas inmovilizadas** filmadas repetidamente y advierte que la calibración sólo es transferible si las
  condiciones de ruido y señal son idénticas. Es el protocolo que el laboratorio necesita para separar σ_loc de σ real.
- **Secciones clave (leídas en HTML):** "Theory — Static error", Ecs. (1)–(5): posición medida = verdadera + χ(t), con
  ⟨χ⟩ = 0 y ⟨χ²⟩ = ε² (Ec. 1); corrección de la autocorrelación y del desplazamiento cuadrático medio (Ecs. 2–5; en la
  versión HTML las ecuaciones son imágenes, verificar la forma exacta en el PDF). Fig. 5: ε medido con perlas fijas en
  función de la relación ruido/señal.

### 18. Endesfelder, Malkusch, Fricke y Heilemann (2014) — A simple method to estimate the average localization precision of a single-molecule localization microscopy experiment

- **Cita:** U. Endesfelder, S. Malkusch, F. Fricke, M. Heilemann, "A simple method to estimate the average localization precision of a single-molecule localization microscopy experiment", *Histochemistry and Cell Biology* **141**(6), 629–638 (2014).
- **DOI:** [10.1007/s00418-014-1192-3](https://doi.org/10.1007/s00418-014-1192-3) · PMID 24522395
- **Acceso abierto:** no (OpenAlex: cerrado).
- **Archivo local:** sin PDF (muro de pago)
- **Tema:** 3
- **Relevancia:** Método NeNA: estima la precisión de localización promedio a partir del análisis de vecinos más cercanos
  entre localizaciones, aplicable a datos 2D y 3D (según el resumen de PubMed). Aplicado a dos imágenes sucesivas de la
  misma red impresa, daría σ_loc de manera independiente del desorden de la red, que es justamente lo que hay que
  restar.
- **Leído:** no (sólo resumen).

### 19. Trueblood et al. (1996) — Atomic displacement parameter nomenclature

- **Cita:** K. N. Trueblood, H.-B. Bürgi, H. Burzlaff, J. D. Dunitz, C. M. Gramaccioli, H. H. Schulz, U. Shmueli, S. C. Abrahams, "Atomic Displacement Parameter Nomenclature. Report of a Subcommittee on Atomic Displacement Parameter Nomenclature", *Acta Crystallographica Section A* **52**(5), 770–781 (1996). (El título registrado en Crossref contiene la errata "Dispacement".)
- **DOI:** [10.1107/S0108767396005697](https://doi.org/10.1107/S0108767396005697)
- **Acceso abierto:** sí según OpenAlex (libre en IUCr: https://journals.iucr.org/a/issues/1996/05/00/es0238/es0238.pdf), pero el servidor devolvió una verificación anti-bot.
- **Archivo local:** sin PDF local (OA, descargar a mano)
- **Tema:** 1
- **Relevancia:** Informe oficial de la IUCr sobre la nomenclatura de los parámetros de desplazamiento atómico, que según su
  resumen cubren desplazamientos **dinámicos o estáticos**, se derivan de la función densidad de probabilidad y tratan
  tanto el caso gaussiano como el no gaussiano. Es la autoridad a la que remitirse para fijar la convención (U, B,
  varianza por dirección o total) y cerrar el problema del factor ½ del laboratorio.
- **Leído:** no (sólo resumen). **Pendiente:** leerlo antes de citar su convención.

### 20. Wilson (1942) — Determination of absolute from relative X-ray intensity data

- **Cita:** A. J. C. Wilson, "Determination of Absolute from Relative X-Ray Intensity Data", *Nature* **150**, 152 (1942).
- **DOI:** [10.1038/150152a0](https://doi.org/10.1038/150152a0)
- **Acceso abierto:** no (OpenAlex: cerrado).
- **Archivo local:** sin PDF (muro de pago)
- **Tema:** 6, 1
- **Relevancia:** Origen del "gráfico de Wilson", el procedimiento clásico para obtener a la vez el factor de escala y un
  factor de temperatura global a partir de cómo decaen las intensidades de Bragg con el ángulo. Es el antecesor directo de
  estimar σ ajustando la atenuación de **varios** órdenes a la vez (en lugar de un solo pico), lo que además cancela la
  normalización absoluta desconocida.
- **Leído:** no. La descripción del método corresponde a su uso estándar en cristalografía y no se verificó contra el
  texto de la carta.

---

## Puntos abiertos que el laboratorio debería resolver

1. **Varianza por componente o total.** Fijar por escrito que el σ del método es la desviación por componente
   cartesiana, y que la atenuación de intensidad en 2D es exp(−q²σ²) = exp(−q²⟨|u|²⟩/2). Cerrarlo contra
   Trueblood et al. [19] (no leído, OA en IUCr) antes de citar la convención cristalográfica de U y B.
2. **Distribución de los desplazamientos.** Los trabajos de redes plasmónicas y coloidales ([7], [8], [10]) usan
   distribuciones uniformes o porcentajes del período. Si el Monte Carlo del laboratorio supone gaussiana, hay que decir
   cómo se comparan esos números, y comprobar que la inversión no depende de la forma de la distribución ([2], Fig. 4).
3. **Error de medición.** Las varianzas del error de localización y del desorden real se suman si son independientes
   ([17], Ec. 1), y en g(r) el error aparece con varianza 2σ_loc² ([5]). Falta en esta carpeta una fuente abierta
   leída que trate explícitamente el efecto del ruido de localización sobre la intensidad de los picos de Bragg de una red;
   la conclusión de que multiplica la intensidad por exp(−q²σ_loc²) es una consecuencia directa de [1]–[3], no algo
   leído en una fuente.
4. **Vacancias.** Con N sitios ocupados cada uno con probabilidad 1 − p y sin correlación, el promedio de la amplitud es
   (1 − p) veces la de la red llena. Por lo tanto la intensidad de Bragg **normalizada por partícula presente** se reduce
   en (1 − p) y aparece un fondo plano de valor p (derivación propia a partir de las Ecs. 27–29 de [3]; contrastar con
   las fórmulas de Kim y Torquato [14], no leídas). Si en cambio se normaliza por sitio de la red, el factor de Bragg es
   (1 − p)². Hay que declarar cuál normalización usa el método.
5. **Ancho de pico y longitud de correlación.** Ninguna de las fuentes leídas fija una convención entre FWHM y longitud
   de correlación. Dullens y Petukhov [10] ajustan lorentzianas y reportan FWHM relativo. Para una lorentziana
   1/[1 + (Δq·ξ)²] el FWHM vale 2/ξ; con otras definiciones (semiancho, 2π/FWHM, anchura integral) cambia el
   prefactor. Rivnay et al. [13] (no leído) es la fuente más probable para cerrar este punto.
6. **Tamaño finito.** En una red impresa de pocos cientos de partículas el ancho instrumental y el de tamaño finito
   (función de corte triangular de una muestra con bordes abiertos, [3] Sec. V A) pueden dominar sobre el
   ensanchamiento por desorden, y según Millane y Eads [11] tipo I y tipo II son casi indistinguibles en cristalitos
   pequeños. Conviene simular la red perfecta del mismo tamaño como referencia, como hacen Dullens y Petukhov [10].

---

## Resumen

- **Trabajos:** 20. **Con PDF local:** 10 (entradas 1–10). **Acceso abierto sin PDF local** (el servidor exige
  verificación anti-bot o JavaScript; descargar a mano): 3 (entradas 15, 17 y 19). **Sin PDF por muro de pago:** 7
  (entradas 11–14, 16, 18 y 20).
- **Por tema:** 1 → [1], [2], [3], [4], [14], [19], [20]; 2 → [1], [6], [10], [11], [12], [13]; 3 → [5], [10], [17], [18];
  4 → [3], [8], [14], [16]; 5 → [7], [8], [9], [15], [16]; 6 → [2], [3], [4], [10], [13], [20].
- **Revisado:** 2026-09-27.

