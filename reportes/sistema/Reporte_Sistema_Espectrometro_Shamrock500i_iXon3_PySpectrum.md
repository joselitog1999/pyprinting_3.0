# 📑 Reporte de Sistema: Espectrómetro Andor Shamrock SR-500i, Cámara iXon3 EMCCD y Acople Óptico en PySpectrum 3.0

**Laboratorio de Nanofotónica — Instituto de Nanosistemas (INS-UNSAM / CONICET)**  
**Autor Principal**: José Luis González Peñafiel (*Becario Doctoral CONICET*)  
**Fecha de Emisión**: Septiembre 2026 | Versión: 3.0  
**Ubicación de Archivo**: `reportes/sistema/Reporte_Sistema_Espectrometro_Shamrock500i_iXon3_PySpectrum.md`

---

## 1. 🔬 Arquitectura Óptica Completa del Montaje Experimental

El banco óptico de espectroscopía de alta sensibilidad y caracterización de nanoestructuras integra una cadena óptica optimizada para combinar **resolución espacial confocal sub-micrométrica** con **resolución espectral vibracional (< 2 cm⁻¹)**.

> [!NOTE]
> Para consultar el modelo analítico completo de los 5 objetivos, el telescopio relé de lentes ($f_1 = 250\,\text{mm} \to f_2 = 200\,\text{mm}$), los tres canales confocales y la cámara réflex Canon, remítase al informe maestro:  
> [Reporte Maestro de Arquitectura Óptica (`reportes/sistema/Reporte_Arquitectura_Optica_Microscopio_Derecho_y_Espectrometria.md`)](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/reportes/sistema/Reporte_Arquitectura_Optica_Microscopio_Derecho_y_Espectrometria.md).

```
                                ESPECTRÓMETRO ANDOR SHAMROCK SR-500i (Czerny-Turner f = 500 mm)
                                ┌────────────────────────────────────────────────────────────┐
Muestra (Sustrato)              │                                                            │
      │                         │     M1 (Colimador Esférico)      Torrecilla de Redes       │
      ▼                         │          f = 500 mm              • 150 l/mm (Blaze 800nm)  │
[Objetivo Olympus 20x]          │              │                   • 1200 l/mm (Blaze 500nm) │
(Aire, NA=0.50, f=9mm)          │              │                   • Espejo (Orden Cero / Im)│
      │                         │              ▼                               │             │
[Lente de Tubo Microscopio]     │    [ Rendija Motorizada ] ──────────────▶  M2 (Enfoque)    │
      │                         │      (10 µm a 2500 µm)                       f = 500 mm    │
[Filtro Notch/Edge 532nm]       │                                              │             │
      │                         └──────────────────────────────────────────────┼─────────────┘
      ▼                                                                        ▼
[Lente Acople f = 250 mm] ──────────────────────────────────────────▶ [ Detector iXon3 EMCCD ]
                                                                      (Enfriamiento -80°C | EM)
```

---

## 2. 📐 Formulación Óptica y Acoplamiento Espacial

### 2.1 Objetivo de Medición: Olympus UPLFLN 20x (Aire, $\text{NA} = 0.50$)
Para todas las caracterizaciones espectrales (Raman, SERS, Anti-Stokes, fotoluminiscencia y extinción plasmónica), se utiliza el objetivo de aire **Olympus UPLFLN 20x** (el objetivo $60\times$ de inmersión en agua $\text{NA}=1.0$ se reserva exclusivamente para las rutinas de Optical Printing en celda líquida):
- **Apertura Numérica ($\text{NA}$)**: $0.50$ en aire ($n = 1.0$).
- **Semi-ángulo Máximo de Colección ($\theta_{\max}$)**:
  $$\text{NA} = n \sin\theta_{\max} \implies \theta_{\max} = \arcsin(0.50) = 30.0^\circ \quad (\text{Cono total } 2\theta_{\max} = 60.0^\circ)$$
- **Distancia Focal del Objetivo ($f_{\text{obj}}$)**:
  En el estándar infinito de Olympus ($f_{\text{tubo}} = 180\text{ mm}$):
  $$f_{\text{obj}} = \frac{f_{\text{tubo}}}{M} = \frac{180\text{ mm}}{20} = 9.0\text{ mm}$$
- **Límites Difractivos en el Foco a $\lambda = 532\text{ nm}$**:
  - Diámetro del Disco de Airy (primer mínimo):
    $$d_{\text{Airy}} = \frac{1.22 \lambda}{\text{NA}} = \frac{1.22 \times 0.532\ \mu\text{m}}{0.50} \approx 1.30\ \mu\text{m}$$
  - Ancho a Mitad de Altura ($\text{FWHM}$ difractivo):
    $$\text{FWHM}_{\text{difr}} = \frac{0.51 \lambda}{\text{NA}} = \frac{0.51 \times 0.532\ \mu\text{m}}{0.50} \approx 0.54\ \mu\text{m}$$

### 2.2 La Lente Colimadora / Acople de 250 mm y la Rendija Motorizada de $10\ \mu\text{m}$ a $2500\ \mu\text{m}$
La lente de $f_{\text{lente}} = 250\text{ mm}$ acopla la salida colimada del microscopio con la rendija de entrada motorizada del espectrógrafo, la cual cuenta con un **rango de apertura continuo de $10\ \mu\text{m}$ hasta $2500\ \mu\text{m}$ ($2.5\text{ mm}$)**:

1. **Magnificación Óptica Total Muestra $\rightarrow$ Rendija**:
   $$M_{\text{acople}} = \frac{f_{\text{lente}}}{f_{\text{obj}}} = \frac{250\text{ mm}}{9.0\text{ mm}} \approx 27.78\times$$

2. **Mapeo Espacial entre Rendija y Muestra**:
   El ancho de campo de la muestra aceptado por la rendija viene dado por:
   $$w_{\text{muestra}} = \frac{w_{\text{rendija}}}{M_{\text{acople}}} = \frac{w_{\text{rendija}}}{27.78}$$

   Analizando los regímenes característicos de apertura:
   - **$w_{\text{rendija}} = 10\ \mu\text{m}$ (Mínimo mecánico)**:
     $$w_{\text{muestra}} = \frac{10\ \mu\text{m}}{27.78} \approx 0.36\ \mu\text{m} \quad (< d_{\text{Airy}})$$
     *Régimen sub-difractivo*: Se corta parte del disco de Airy. Reduce el flujo pero maximiza el rechazo espacial de fondo fuera de foco.
   - **$w_{\text{rendija}} = 36.1\ \mu\text{m}$ (Acople Difractivo Exacto - 1 Airy Unit)**:
     $$w_{\text{muestra}} = \frac{36.1\ \mu\text{m}}{27.78} \approx 1.30\ \mu\text{m} = d_{\text{Airy}}$$
     *Transmisión difractiva óptima*: Transmite el $\sim 84\%$ de la potencia fotónica total del lóbulo central de Airy.
   - **$w_{\text{rendija}} = 50\ \mu\text{m}$ (Régimen Confocal de Rutina)**:
     $$w_{\text{muestra}} = \frac{50\ \mu\text{m}}{27.78} \approx 1.80\ \mu\text{m}$$
     *Transmisión fotónica $>95\%$*: Actúa como un **pinhole confocal ideal** que captura la totalidad de la emisión de una nanopartícula individual bloqueando reflexiones parásitas del sustrato.
   - **$w_{\text{rendija}} = 100\ \mu\text{m} - 500\ \mu\text{m}$ (Régimen de Alto Flujo / "Photon Bucket")**:
     $$w_{\text{muestra}} = 3.6\ \mu\text{m} \text{ a } 18.0\ \mu\text{m}$$
     Inmune a pequeñas derivas mecánicas o térmicas. Ideal para cinética de crecimiento de nanopartículas y fotoluminiscencia muy débil.
   - **$w_{\text{rendija}} = 2500\ \mu\text{m}$ ($2.5\text{ mm}$ - Máxima Apertura Mecánica)**:
     $$w_{\text{muestra}} = \frac{2500\ \mu\text{m}}{27.78} \approx \mathbf{90.0\ \mu\text{m}}$$
     > [!IMPORTANT]
     > **Alineación con el Rango de la Platina Piezoeléctrica PI E-517 ($100\ \mu\text{m} \times 100\ \mu\text{m}$)**:
     > Al abrir la ranura a su valor máximo de $2500\ \mu\text{m}$, la ventana espacial en la muestra abarca **$90\ \mu\text{m}$**, cubriendo prácticamente el **$90\%$ de todo el campo de escaneo piezoeléctrico**. Esto permite capturar la señal luminosa de arreglos enteros de nanopartículas impresas sin mover micrométricamente la muestra.

3. **Adaptación de Conos de Apertura ($F/\#$ Matching)**:
   El Shamrock SR-500i tiene una apertura geométrica interna de **$F/6.5$** ($f_{\text{int}} = 500\text{ mm}$, espejos colimadores $\varnothing \approx 77\text{ mm}$).
   - Para llenar al $100\%$ los espejos internos sin pérdidas ni desbordes:
     $$D_{\text{haz, óptimo}} = \frac{f_{\text{lente}}}{F/\#} = \frac{250\text{ mm}}{6.5} \approx 38.5\text{ mm}$$
   - Si el haz que emerge del microscopio tiene un diámetro de $\approx 12 - 15\text{ mm}$, el cono de entrada es $F/16 - F/20$ (**subllenado o *underfilling***). 
   - **Consecuencia física**: Se elimina totalmente la luz parásita rebotando en las paredes del chasis (fondo oscuro muy limpio), pero la red de difracción se ilumina en una fracción central de su ancho, reduciendo ligeramente el poder de resolución teórico respecto al límite de difracción instrumental.6.5} \approx 38.5\text{ mm}$$
   - Si el haz que emerge del microscopio tiene un diámetro de $\approx 12 - 15\text{ mm}$, el cono de entrada es $F/16 - F/20$ (**subllenado o *underfilling***). 
   - **Consecuencia física**: Se elimina totalmente la luz parásita rebotando en las paredes del chasis (fondo oscuro muy limpio), pero la red de difracción se ilumina en una fracción central de su ancho, reduciendo ligeramente el poder de resolución teórico respecto al límite de difracción instrumental.

---

## 3. 🌈 Espectrógrafo Andor Shamrock SR-500i (Czerny-Turner)

A diferencia de los monocromadores convencionales de $300\text{ mm}$, la distancia focal de **$500\text{ mm}$** otorga un brazo óptico largo con **alta dispersión angular y lineal**.

### 3.1 Las Dos Redes de Difracción Reales
El espectrógrafo cuenta con una torrecilla motorizada de doble red con especificaciones complementarias:

| Parámetro | Red 1: 150 líneas/mm | Red 2: 1200 líneas/mm |
|---|---|---|
| **Densidad de Ranuras ($N$)** | $150\ \text{l/mm}$ | $1200\ \text{l/mm}$ |
| **Longitud de Onda de Blaze ($\lambda_B$)** | **$800\ \text{nm}$ (Infrarrojo Cercano)** | **$500\ \text{nm}$ (Visible)** |
| **Rango de Máxima Eficiencia** | $600 - 1100\ \text{nm}$ ($\eta > 70\%$) | $400 - 750\ \text{nm}$ ($\eta > 75\%$) |
| **Dispersión Recíproca Nominal** | $\approx 13.33\ \text{nm/mm}$ | $\approx 1.67\ \text{nm/mm}$ |
| **Dispersión en Píxel de $16\ \mu\text{m}$** | **$0.213\ \text{nm/px}$** | **$0.0267\ \text{nm/px}$** |
| **Dispersión en Píxel de $13\ \mu\text{m}$** | **$0.173\ \text{nm/px}$** | **$0.0217\ \text{nm/px}$** |
| **Ventana Espectral Única (Sensor 512 px)** | $\approx 109\ \text{nm}$ | $\approx 13.7\ \text{nm}$ |
| **Ventana Espectral Única (Sensor 1024 px)** | $\approx 177\ \text{nm}$ | $\approx 22.2\ \text{nm}$ |
| **Resolución Raman a $532\ \text{nm}$ ($16\mu\text{m}$)** | $\approx 7.5\ \text{cm}^{-1}/\text{px}$ | **$\approx 0.88\ \text{cm}^{-1}/\text{px}$** |
| **Rol Experimental Principal** | Extinción LSPR, Step & Glue panorámico | **Raman de Alta Resolución, Anti-Stokes** |

### 3.2 Implicancia del Ángulo de Blaze
- **Red de 150 l/mm (Blaze 800 nm)**:
  Sus ranuras están talladas de modo que la reflexión especular constructiva ocurre en $800\text{ nm}$. Es la herramienta definitiva para medir la resonancia plasmónica longitudinal de nanorods de oro, dímeros plasmónicos acoplados en el infrarrojo cercano y fotoluminiscencia de defectos en silicio o sustratos dieléctricos.
- **Red de 1200 l/mm (Blaze 500 nm)**:
  Su máxima transmitancia coincide casi exactamente con la línea láser de excitación de **$532\text{ nm}$**. Entre $500$ y $600\text{ nm}$ (región Stokes para 532 nm correspondiente a $0 - 2150\text{ cm}^{-1}$), la eficiencia de difracción supera el $75\%$, maximizando la recolección de los débiles fotones inelásticos Raman y Anti-Stokes.

### 3.3 Impacto del Ancho de Rendija ($10\ \mu\text{m}$ a $2500\ \mu\text{m}$) en la Resolución Espectral Instrumental

El ancho físico de las cuchillas de entrada $w_{\text{rendija}}$ determina directamente el ensanchamiento instrumental geométrico $\delta\lambda_{\text{geom}}$ proyectado sobre el plano focal del detector:
$$\delta\lambda_{\text{geom}} = w_{\text{rendija}} \cdot D_{\text{linear}}$$
donde $D_{\text{linear}}$ es la dispersión recíproca lineal ($13.33\ \text{nm/mm} = 0.01333\ \text{nm}/\mu\text{m}$ para 150 l/mm; $1.67\ \text{nm/mm} = 0.00167\ \text{nm}/\mu\text{m}$ para 1200 l/mm).

La resolución espectral total efectiva $\delta\lambda_{\text{total}}$ resulta de la convolución cuadrática del ensanchamiento geométrico con la resolución discreta de píxel ($\delta\lambda_{\text{px}}$) y el límite difractivo del espectrógrafo ($\delta\lambda_{\text{difr}}$):
$$\delta\lambda_{\text{total}} = \sqrt{\delta\lambda_{\text{geom}}^2 + \delta\lambda_{\text{px}}^2 + \delta\lambda_{\text{difr}}^2}$$

A continuación se detalla la matriz de cálculo a través de todo el rango operativo de la ranura ($10\ \mu\text{m}$ a $2500\ \mu\text{m}$) evaluada a la línea láser de excitación de $532\ \text{nm}$:

| Ancho Ranura $w_{\text{rendija}}$ | Campo en Muestra $w_{\text{muestra}}$ | Red 150 l/mm: $\delta\lambda$ (nm) | Red 150 l/mm: $\delta\tilde{\nu}$ ($\text{cm}^{-1}$) | Red 1200 l/mm: $\delta\lambda$ (nm) | Red 1200 l/mm: $\delta\tilde{\nu}$ ($\text{cm}^{-1}$) | Aplicación Experimental Sugerida |
|---|---|---|---|---|---|---|
| **$10\ \mu\text{m}$** (mínimo) | $0.36\ \mu\text{m}$ | $0.175\ \text{nm}$ (límite px) | $6.2\ \text{cm}^{-1}$ | $0.022\ \text{nm}$ (límite px) | $0.77\ \text{cm}^{-1}$ | Máximo filtrado confocal sub-difractivo |
| **$36.1\ \mu\text{m}$** (Airy) | $1.30\ \mu\text{m}$ ($d_{\text{Airy}}$) | $0.48\ \text{nm}$ | $17.0\ \text{cm}^{-1}$ | $0.060\ \text{nm}$ | $2.1\ \text{cm}^{-1}$ | Acoplamiento difractivo óptimo (1 Airy Unit) |
| **$50.0\ \mu\text{m}$** (estándar) | $1.80\ \mu\text{m}$ | $0.67\ \text{nm}$ | $23.6\ \text{cm}^{-1}$ | $0.084\ \text{nm}$ | $2.9\ \text{cm}^{-1}$ | **Raman confocal de rutina y Anti-Stokes** |
| **$100\ \mu\text{m}$** | $3.60\ \mu\text{m}$ | $1.33\ \text{nm}$ | $47.0\ \text{cm}^{-1}$ | $0.167\ \text{nm}$ | $5.9\ \text{cm}^{-1}$ | Cinética de crecimiento y LSPR extinción |
| **$250\ \mu\text{m}$** | $9.00\ \mu\text{m}$ | $3.33\ \text{nm}$ | $117.7\ \text{cm}^{-1}$ | $0.417\ \text{nm}$ | $14.7\ \text{cm}^{-1}$ | SERS en agregados y dímeros amplios |
| **$500\ \mu\text{m}$** | $18.0\ \mu\text{m}$ | $6.67\ \text{nm}$ | $235.6\ \text{cm}^{-1}$ | $0.835\ \text{nm}$ | $29.5\ \text{cm}^{-1}$ | Fotoluminiscencia ultra-débil (*Photon Bucket*) |
| **$1000\ \mu\text{m}$** ($1.0\text{ mm}$) | $36.0\ \mu\text{m}$ | $13.33\ \text{nm}$ | $471.1\ \text{cm}^{-1}$ | $1.67\ \text{nm}$ | $59.0\ \text{cm}^{-1}$ | Ensayos de absorción transitoria macro |
| **$2500\ \mu\text{m}$** ($2.5\text{ mm}$) | $\mathbf{90.0\ \mu\text{m}}$ | $\mathbf{33.33\ \text{nm}}$ | $\mathbf{1177.8\ \text{cm}^{-1}}$ | $\mathbf{4.17\ \text{nm}}$ | $\mathbf{147.5\ \text{cm}^{-1}}$ | **Modo Imagen Directa / Alineación Óptica** |

### 3.4 Modo Microscopía de Imagen Directa / Orden Cero (Espejo) a Rendija Abierta ($2500\ \mu\text{m}$)

Una capacidad única de la arquitectura del Shamrock 500i con ranura motorizada de gran recorrido ($2500\ \mu\text{m}$) es el **Modo Microscopio de Imagen Directa**:

1. **Configuración Óptica**:
   - Red en posición de **Espejo / Orden Cero ($\lambda = 0\ \text{nm}$)**: Los espejos colimador y focalizador actúan como un relé óptico 1:1 sin dispersión cromática.
   - Rendija abierta a su máximo mecánico: **$w_{\text{rendija}} = 2500\ \mu\text{m}$ ($2.5\ \text{mm}$)**.
2. **Proyección en el Sensor iXon3 EMCCD ($1002 \times 1002\text{ px}$, píxel $13\ \mu\text{m}$)**:
   - Ancho activo proyectado en píxeles del detector:
     $$N_{\text{px, ancho}} = \frac{2500\ \mu\text{m}}{13\ \mu\text{m/px}} \approx 192\ \text{píxeles}$$
   - Alto activo proyectado (limitado por la altura física del sensor de $13.03\text{ mm}$):
     $$N_{\text{px, alto}} = 1002\ \text{píxeles}$$
   - **Campo visual directo sobre la muestra**:
     $$\text{FOV}_{\text{muestra}} = \frac{192 \times 13\ \mu\text{m}}{27.78} \times \frac{1002 \times 13\ \mu\text{m}}{27.78} \approx \mathbf{90.0\ \mu\text{m} \times 468.9\ \mu\text{m}}$$
3. **Casos de Uso Críticos en el Laboratorio**:
   - **Alineación Rápida del Spot Láser**: Permite observar en pantalla la imagen bidimensional del spot láser reflejado en el sustrato y centrarlo visualmente sobre el eje de las cuchillas con precisión micrométrica antes de cerrar la ranura a $40\ \mu\text{m}$.
   - **Búsqueda Visual de Nanopartículas Impresas**: Utilizando la ultra-alta sensibilidad de la ganancia EM, se pueden localizar nanopartículas individuales o dímeros impresos directamente en la imagen 2D sin necesidad de conmutar puertos ni usar cámaras de búsqueda secundarias.
   - **Enfoque Confocal en Tiempo Real**: Permite optimizar el eje piezoeléctrico $Z$ en vivo maximizando el contraste y la densidad de fotones en el perfil de la ranura.

---

## 4. 📷 Detector Andor iXon3 EMCCD: Física de la Ultra-Sensibilidad

La cámara **iXon3** no es un CCD convencional; incorpora una etapa de **ganancia por multiplicación de electrones (*Electron Multiplying*)** en estado sólido:

```
[ Matriz Fotosensible Activa (Back-Illuminated, QE > 90%) ]
                          │  (Transferencia vertical de carga)
                          ▼
[ Registro Serie Convencional ] ──▶ [ Registro EM de Ganancia (500+ etapas) ] ──▶ [ Amplificador EM ]
                                       (Alto voltaje ~40-50 V: Ionización)         Ruido < 0.1 e⁻
```

### 4.1 Modos de Lectura: Convencional vs. EM Gain
1. **Modo Convencional (EM Gain = 0)**:
   - La carga se transfiere directamente al amplificador de bajo ruido.
   - Ruido de lectura típico: $\sigma_{\text{read}} \approx 5 - 8\ \text{e}^-$.
   - **Regla**: Debe usarse cuando la señal es moderada o alta ($> 20\ \text{fotones/pixel}$), como en espectros de dispersión halógena o fotoluminiscencia brillante.
2. **Modo EMCCD (EM Gain $1\times - 1000\times$)**:
   - Los electrones atraviesan un registro de cientos de celdas con gradientes de alto voltaje ($40 - 50\ \text{V}$), provocando ionización por impacto secundaria.
   - La señal se amplifica por un factor $G$ antes de llegar al nodo de salida:
     $$\sigma_{\text{read, eff}} = \frac{\sigma_{\text{read}}}{G} < 0.1\ \text{e}^- \quad (\text{para } G > 100)$$
   - **El Factor de Ruido de Exceso ($F = \sqrt{2} \approx 1.41$)**: La multiplicación es estocástica, lo que añade un ruido multiplicativo que reduce la Eficiencia Cuántica Detectiva ($\text{DQE} \rightarrow \text{QE} / 2$).
   - **Regla de Laboratorio**: Usar ganancia EM **únicamente** cuando la señal esté dominada por el ruido de lectura (menos de $10\ \text{fotones/píxel}$), como en espectros Raman de baja concentración, fotólisis rápida y, fundamentalmente, en **Anti-Stokes**.

### 4.2 Enfriamiento Criogénico Peltier ($-80^\circ\text{C}$)
- A temperatura ambiente, la agitación térmica genera cientos de electrones de corriente oscura por segundo.
- Enfriando el sensor a **$-80^\circ\text{C}$** mediante el refrigerador Peltier multi-etapa, la corriente oscura colapsa a menos de **$0.0005\ \text{e}^-/\text{pixel/s}$**, permitiendo tiempos de integración prolongados ($10 - 60\ \text{s}$) en mediciones Raman sin elevar la línea base.

---

## 5. 🌡️ Termometría Anti-Stokes: Fundamentos y Métodos

Cuando un haz láser enfocado incide sobre una nanopartícula plasmónica, los electrones de conducción absorben fotones y se termalizan mediante colisiones electrón-electrón ($100 - 500\ \text{fs}$) y electrón-fonón ($1 - 5\ \text{ps}$), elevando drásticamente la temperatura local $\Delta T$ de la nanoestructura y su entorno dieléctrico inmediato.

### 5.1 Método 1: Razón de Intensidades Raman Stokes / Anti-Stokes
Para cualquier vibración molecular o modo de red con desplazamiento $\Delta\tilde{\nu}$ ($\text{cm}^{-1}$):
- **Stokes ($I_S$)**: El fotón láser cede energía para crear un fonón ($\nu_S = \nu_L - \Delta\nu$).
- **Anti-Stokes ($I_{AS}$)**: El fotón láser absorbe energía de un fonón preexistente térmicamente poblado ($\nu_{AS} = \nu_L + \Delta\nu$).

La población del estado vibracional excitado sigue estrictamente la distribución de Maxwell-Boltzmann:

$$\frac{I_{AS}(\Delta\tilde{\nu})}{I_S(\Delta\tilde{\nu})} = \left(\frac{\nu_L + \Delta\nu}{\nu_L - \Delta\nu}\right)^4 \cdot \exp\left( -\frac{h c \Delta\tilde{\nu}}{k_B T} \right) \cdot \frac{\sigma_{AS}(\lambda_{AS})}{\sigma_S(\lambda_S)} \cdot \frac{\eta(\lambda_{AS})}{\eta(\lambda_S)}$$

donde:
- $\left(\frac{\nu_L + \Delta\nu}{\nu_L - \Delta\nu}\right)^4$: Factor de radiación dipolar clásico de Rayleigh/Raman.
- $\exp\left(-\frac{h c \Delta\tilde{\nu}}{k_B T}\right)$: Factor de ocupación térmica de Boltzmann ($h c / k_B \approx 1.4388\ \text{cm}\cdot\text{K}$).
- $\eta(\lambda)$: Eficiencia cuántica y respuesta instrumental del sistema acoplado (red + iXon3 + filtros).

**Ecuación de Extracción de Temperatura**:
$$T = \frac{1.4388 \cdot \Delta\tilde{\nu}}{\ln\left[ \left(\frac{\nu_L + \Delta\nu}{\nu_L - \Delta\nu}\right)^4 \cdot \frac{I_S}{I_{AS}} \cdot C_{\text{inst}}(\Delta\tilde{\nu}) \right]} \quad [\text{K}]$$

> [!TIP]
> **Ventaja de la Red de 1200 l/mm a 532 nm**:
> A $\Delta\tilde{\nu} = 600\text{ cm}^{-1}$ y $T = 300\ \text{K}$, la intensidad Anti-Stokes es solo el $5.5\%$ de la Stokes. Con la iXon3 a EM Gain $= 100\times$, el pico Anti-Stokes emerge nítidamente por encima del piso de ruido, permitiendo determinar la temperatura absoluta con precisión de $\pm 2\ \text{K}$.

### 5.2 Método 2: Fotoluminiscencia Anti-Stokes de Oro (Fermi-Dirac de Electrones Calientes)
En nanopartículas de oro donde no hay moléculas adsorbidas con picos Raman definidos, se utiliza la **emisión continua de electrones calientes**:
- La absorción interbanda ($d \rightarrow sp$) y la desexcitación plasmónica generan una distribución cuasi-térmica de electrones por encima del nivel de Fermi $E_F$.
- Los electrones con energía $\hbar\omega > \hbar\omega_L$ pueden recombinarse radiativamente con huecos de la banda $d$, emitiendo fotones Anti-Stokes cuya distribución espectral reproduce la cola de Fermi-Dirac:
  $$I_{AS}(\hbar\omega) \propto \exp\left( -\frac{\hbar(\omega - \omega_L)}{k_B T_e} \right)$$
- Al graficar $\ln(I_{AS})$ en función de la energía fotónica transferida $\hbar\Delta\omega = \hbar(\omega - \omega_L)$, los datos forman una recta pura cuya pendiente es:
  $$\text{Pendiente } m = -\frac{1}{k_B T} \implies T = -\frac{1}{k_B \cdot m}$$
  ¡Permite medir la temperatura absoluta de la nanopartícula en tiempo real sin requerir parámetros instrumentales calibrados!

---

## 6. 🚀 Plan Detallado de Implementación: Mejoras 2 y 3

Para materializar estas capacidades en el software, se estructuran las siguientes dos fases de ingeniería sobre `pyspectrum`:

### Fase A: Mejora 2 — Parametrización Específica iXon3 y Shamrock 500i
1. **Actualización de Controladores de Hardware**:
   - En [`shamrock_driver.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/pyspectrum/drivers/shamrock_driver.py):
     - Configurar explícitamente las 2 redes reales: `150 l/mm (Blaze 800nm)` y `1200 l/mm (Blaze 500nm)` con sus ángulos de blaze y factores de dispersión correctos para $f = 500\text{ mm}$.
     - Actualizar la dispersión recíproca sintética y real en `ShamrockGetCalibration`.
   - En [`andor_ccd_driver.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/pyspectrum/drivers/andor_ccd_driver.py):
     - Enlazar las funciones nativas Ctypes de la DLL `atmcd64d.dll`: `SetEMCCDGain(int gain)`, `SetOutputAmplifier(int typ)` (0 = EMCCD, 1 = Convencional), `GetTemperatureF(float *temp)` y `SetCoolerMode(int mode)`.
     - Extender el mock `_MockAndorCCD` para simular con precisión el enfriamiento hasta $-80^\circ\text{C}$ y la respuesta no lineal de ganancia EM.
2. **Interfaz de Usuario de Cámara y Espectrógrafo**:
   - En [`camera_andor.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/pyspectrum/modules/camera_andor.py):
     - Reemplazar el casillero básico de EM Gain por un control dual interactivo: **Slider (0 a 1000) + SpinBox**, con código de colores de advertencia si supera 300 para proteger el sensor.
     - Selector de amplificador de salida: `[ Modo Convencional (Bajo Ruido) | Modo EMCCD (Alta Sensibilidad) ]`.
     - Selector de temperatura con soporte hasta $-80^\circ\text{C}$ y LED de estado Peltier (`🟢 Estabilizado`, `🟡 Enfriando`, `🔴 Deriva`).
   - En [`spectrum_control.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/pyspectrum/modules/spectrum_control.py):
     - Etiquetas dinámicas que reporten el rango espectral activo abarcado ($\Delta\lambda$ en nm) y la dispersión lineal resultante ($\text{nm/px}$ y $\text{cm}^{-1}\text{/px}$ calculados a la longitud de onda central).

### Fase B: Mejora 3 — Modo de Escaneo Raman Estático de Alta Velocidad
1. **Nuevo Módulo de Adquisición Raman Estática** ([`pyspectrum/modules/static_raman.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/pyspectrum/modules/static_raman.py)):
   - Operación estática: Posiciona la red de 1200 l/mm (o 150 l/mm) en un valor fijo de longitud de onda central optimizado para el láser activo (ej. 532 nm) sin mover motores mecánicos durante la adquisición.
   - Configuración de ventana espectral:
     - **Modo Stokes Completo**: Centrado desplazado para abarcar $150\text{ a }2200\text{ cm}^{-1}$.
     - **Modo Stokes + Anti-Stokes Simétrico**: Centrado exactamente en la línea láser para abarcar simultáneamente $-1000\text{ a }+1000\text{ cm}^{-1}$ (ideal para termometría).
2. **Integración con [`core/raman_engine.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/core/raman_engine.py)**:
   - Procesamiento en vivo por cuadro:
     - Conversión automática a Raman Shift ($\text{cm}^{-1}$) según $\lambda_{\text{laser}}$.
     - Sustracción de línea base en tiempo real seleccionable (AsLS, AirPLS, ModPoly o Ninguna).
     - Filtro Savitzky-Golay en vivo para visualización limpia.
     - Extirpación estadística de rayos cósmicos (*Cosmic Ray Despiking*).
3. **Integración en la Ventana Principal [`pyspectrum/window.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/pyspectrum/window.py)**:
   - Nuevo Dock modular: **`🔬 Espectroscopía Raman Estática & Termometría`** accesible desde la interfaz de PySpectrum 3.0.
   - Exportación directa 1-clic a formatos compatibles con `raman_analyzer.py` y OriginLab.
