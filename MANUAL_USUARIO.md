# Manual de Usuario: PyPrinting 3.0 🔬
**Suite de Control, Espectroscopía Confocal, Caracterización de PSF y Nanofabricación Óptica**
*UNSAM — Nanofotónica*

---

## 📖 Índice

1. [Panel de Inicio Principal (`main.py` — "Bienvenidos al printing")](#1-panel-de-inicio-principal-mainpy--bienvenidos-al-printing)
   - [1.1 Visión General y Selección de Modo Seguro (`SAFE_MODE`)](#11-visión-general-y-selección-de-modo-seguro-safe_mode)
   - [1.2 Navegación e Índice de Módulos en Grilla $3 \times 3$](#12-navegación-e-índice-de-módulos-en-grilla-3-times-3)
2. [Fundamentos Físicos, Formulación Matemática & Mapeo de Hardware](#2-fundamentos-físicos-formulación-matemática--mapeo-de-hardware)
   - [2.1 Impresión Óptica Fototérmica y Ensamblado de Dímeros Plasmónicos](#21-impresión-óptica-fototérmica-y-ensamblado-de-dímeros-plasmónicos)
   - [2.2 Modelo Analítico Gaussiano 2D de 7 Parámetros](#22-modelo-analítico-gaussiano-2d-de-7-parámetros)
   - [2.3 Modelo Analítico Haz Vortex / Donut (Laguerre-Gauss $LG_{01}$)](#23-modelo-analítico-haz-vortex--donut-laguerre-gauss-lg_01)
   - [2.4 Métricas de Caracterización y Alineación Sub-nanométrica de PSF](#24-métricas-de-caracterización-y-alineación-sub-nanométrica-de-psf)
   - [2.5 Algoritmo de Estabilización Z por Autocorrelación](#25-algoritmo-de-estabilización-z-por-autocorrelación)
   - [2.6 Mapeo Físico de Coordenadas Piezoeléctricas PI](#26-mapeo-físico-de-coordenadas-piezoeléctricas-pi)
3. [Módulo 1: Microscopio Derecho (`app.py` — PyPrinting 3.0 Suite Completa)](#3-módulo-1-microscopio-derecho-apppy--pyprinting-30-suite-completa)
   - [3.1 Dock: Confocal (Mapeo 2D/3D & Centrado Sub-píxel)](#31-dock-confocal-mapeo-2d3d--centrado-sub-píxel)
   - [3.2 Dock: Trace (Trazas Temporales & Calibración BS)](#32-dock-trace-trazas-temporales--calibración-bs)
   - [3.3 Dock: Focus z (Autofoco Dinámico)](#33-dock-focus-z-autofoco-dinámico)
   - [3.4 Dock: Shutters / Flipper / Láser 532](#34-dock-shutters--flipper--láser-532)
   - [3.5 Dock: Nanopositioning (Platina PI)](#35-dock-nanopositioning-platina-pi)
   - [3.6 Ventana de Mediciones (Printing Automatizado & Dímeros)](#36-ventana-de-mediciones-printing-automatizado--dímeros)
4. [Módulo 2: PySpectrum *(En Construcción)*](#4-módulo-2-pyspectrum-en-construcción)
5. [Módulo 3: Microscopio Contrapropagante *(En Construcción)*](#5-módulo-3-microscopio-contrapropagante-en-construcción)
6. [Módulo 4: PyPrinting 2 (Legacy — `PyPrinting_UNSAM.py`)](#6-módulo-4-pyprinting-2-legacy--pyprinting_unsampy)
7. [Módulo 5: Cámara Live View (`camera.py`)](#7-módulo-5-cámara-live-view-camerapy)
8. [Módulo 6: Modulación Láser 532 nm (`Laser532Window`)](#8-módulo-6-modulación-láser-532-nm-laser532window)
9. [Módulo 7: PSF Analyzer (`psf_analyzer.py`)](#9-módulo-7-psf-analyzer-psf_analyzerpy)
10. [Módulo 8: Analizador de Imágenes (`image_analyzer.py`)](#10-módulo-8-analizador-de-imágenes-image_analyzerpy)
11. [Módulo 9: Documentación y Créditos del Autor](#11-módulo-9-documentación-y-créditos-del-autor)
12. [Flujos de Trabajo Experimentales (Protocolos Paso a Paso)](#12-flujos-de-trabajo-experimentales-protocolos-paso-a-paso)
13. [Tabla de Atajos de Teclado & Preguntas Frecuentes (FAQ)](#13-tabla-de-atajos-de-teclado--preguntas-frecuentes-faq)

---

## 1. Panel de Inicio Principal (`main.py` — "Bienvenidos al printing")

### 1.1 Visión General y Selección de Modo Seguro (`SAFE_MODE`)
El punto de entrada unificado de la suite de software es **`main.py`**. Al ejecutar `python main.py`, se despliega el panel de inicio **"Bienvenidos al printing"**, diseñado para centralizar el acceso a todas las herramientas experimentales, utilidades de visión por computadora y proyectos de desarrollo futuro en el Laboratorio de Nanofotónica de la Universidad Nacional de San Martín (UNSAM).

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│ 🏠 Bienvenidos al printing                                                              │
│ UNSAM — Nanofotónica | Suite de Control, Espectroscopía Confocal y Nanofabricación Óptica │
│                                                      [☑ Modo Seguro (Simulación)]       │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

* **Casillero `Modo Seguro (Simulación)`**:
  - Ubicado en la esquina superior derecha del banner.
  - Al estar marcado (`PYPRINTING_SAFE=1`), activa el entorno de simulación completa sin requerir instrumentos físicos conectados (platina PI simulada, lectura sintética NI-DAQmx a 1.0 MS/s y cámara sintética OpenCV).
  - Al desmarcarlo, el sistema pasa a modo laboratorio real requiriendo la inicialización de la controladora PI E-517/E-736 y la tarjeta National Instruments DAQmx.

---

### 1.2 Navegación e Índice de Módulos en Grilla $3 \times 3$
Las herramientas del sistema están dispuestas en una grilla simétrica de 9 paneles ordenados en 3 filas:

```
┌─────────────────────────┬─────────────────────────┬─────────────────────────┐
│ 🔬 1. Microscopio       │ 🔮 2. PySpectrum        │ 🔍 3. M. Contra-        │
│    Derecho (app.py)     │    (En construcción)    │    propagante (En const)│
├─────────────────────────┼─────────────────────────┼─────────────────────────┤
│ 🏛️ 4. PyPrinting 2      │ 📷 5. Cámara Live View  │ ⚡ 6. Modulación Láser   │
│    (Legacy)             │    (camera.py)          │    532 nm               │
├─────────────────────────┼─────────────────────────┼─────────────────────────┤
│ 🧬 7. PSF Analyzer      │ 🖼️ 8. Analizador de     │ 📚 9. Documentación     │
│    (psf_analyzer.py)    │    Imágenes             │    y Créditos           │
└─────────────────────────┴─────────────────────────┴─────────────────────────┘
```

---

## 2. Fundamentos Físicos, Formulación Matemática & Mapeo de Hardware

### 2.1 Impresión Óptica Fototérmica y Ensamblado de Dímeros Plasmónicos
La **impresión óptica** logra la deposición espacialmente controlada de nanopartículas metálicas (Au, Ag) sobre sustratos dieléctricos impulsada por fuerzas ópticas de presión de radiación. Al iluminar una nanopartícula en su resonancia plasmónica ($LSPR$), la fuerza de gradiente $\mathbf{F}_{\text{grad}}$ domina atrayendo la partícula al foco focalizado:

$$\mathbf{F}_{\text{grad}} = \frac{1}{4} \varepsilon_m \operatorname{Re}(\alpha) \nabla |\mathbf{E}|^2$$

En el **ensamblado de nanodímeros plasmónicos**, la deposición de una segunda nanopartícula a distancias de sub-100 nm genera una fuerte acoplamiento fotónico de campo cercano (*hot-spot* plasmónico), intensificando la emisión Raman (SERS) y la fluorescencia local.

---

### 2.2 Modelo Analítico Gaussiano 2D de 7 Parámetros
Para caracterizar el perfil de excitación en el plano focal horizontal ($XY$), el sistema ajusta la distribución de intensidad normalizada $Z_n$ mediante una función Gaussiana 2D no lineal de 7 parámetros orientada en un ángulo $\theta$ (`scipy.optimize.curve_fit`):

$$G(x, y) = Z_{\text{offset}} + A \cdot \exp\left( -\left[ a(x - x_0)^2 + 2b(x - x_0)(y - y_0) + c(y - y_0)^2 \right] \right)$$

donde los coeficientes anisotrópicos son:

$$a = \frac{\cos^2\theta}{2\sigma_x^2} + \frac{\sin^2\theta}{2\sigma_y^2}, \quad b = -\frac{\sin(2\theta)}{4\sigma_x^2} + \frac{\sin(2\theta)}{4\sigma_y^2}, \quad c = \frac{\sin^2\theta}{2\sigma_x^2} + \frac{\cos^2\theta}{2\sigma_y^2}$$

El Ancho Completo a la Mitad del Máximo (FWHM) para cada eje principal es:

$$\text{FWHM}_x = 2\sqrt{2\ln 2} \cdot \sigma_x \approx 2.35482 \cdot \sigma_x, \quad \text{FWHM}_y = 2.35482 \cdot \sigma_y$$

---

### 2.3 Modelo Analítico Haz Vortex / Donut (Laguerre-Gauss $LG_{01}$)
Para caracterizar haces de fase espiral o donas de depleción en microscopía STED/confocal, se ajusta el perfil analítico Laguerre-Gauss $LG_{01}$:

$$I_{\text{donut}}(x, y) = Z_{\text{offset}} + A \cdot r_n^2(x, y) \cdot \exp\left( - r_n^2(x, y) \right)$$

donde la distancia radial elíptica normalizada es:

$$r_n^2(x, y) = \frac{(x - x_0)^2}{2\sigma_x^2} + \frac{(y - y_0)^2}{2\sigma_y^2}$$

---

### 2.4 Métricas de Caracterización y Alineación Sub-nanométrica de PSF
El módulo de análisis calcula las métricas de alineación entre canales de excitación y dona:

1. **Desalineación Vectorial Dual ($\Delta r_{\text{nm}}$)**:
   $$\Delta r_{\text{nm}} = \sqrt{(x_1 - x_2)^2 + (y_1 - y_2)^2} \times 1000 \quad [\text{nm}]$$
2. **Elipticidad del Donut ($a/b$)**: Relación entre los semi-ejes mayor $a$ y menor $b$. Un valor de $1.000$ representa simetría circular perfecta.
3. **Calidad del Cero Central ($I_{\min}/I_{\max}$)**: Intensidad residual en el nulo central dividida por la intensidad máxima del anillo.
4. **Uniformidad Angular ($\sigma_{\theta}/\bar{I}$)**: Desviación estándar de intensidad a lo largo del anillo del donut dividida por la intensidad media.

---

### 2.5 Algoritmo de Estabilización Z por Autocorrelación
Para corregir la deriva térmica axial en tiempo real, el sistema ejecuta la autocorrelación de Pearson entre la señal instantánea de perfil Z $I(z)$ y el perfil de referencia congelado $I_{\text{ref}}(z)$:

$$R(\Delta z) = \frac{\sum_{i} (I(z_i + \Delta z) - \bar{I}) (I_{\text{ref}}(z_i) - \bar{I}_{\text{ref}})}{\sqrt{\sum_{i} (I(z_i + \Delta z) - \bar{I})^2 \sum_{i} (I_{\text{ref}}(z_i) - \bar{I}_{\text{ref}})^2}}$$

El desplazamiento $\Delta z_{\text{óptimo}}$ que maximiza $R(\Delta z)$ se aplica a la platina PI en el eje Z.

---

### 2.6 Mapeo Físico de Coordenadas Piezoeléctricas PI
La conversión entre coordenadas en píxeles $(x_p, y_p)$ y la posición absoluta en micrómetros $(\mu\text{m})$ de la platina **Physik Instrumente (PI)** es:

$$X_{\text{físico}} = X_{\text{origen}} - \frac{\text{Range}_x}{2} + \frac{dx}{2} + (x_p \cdot dx)$$
$$Y_{\text{físico}} = Y_{\text{origen}} - \frac{\text{Range}_y}{2} + \frac{dy}{2} + (y_p \cdot dy)$$

donde $dx = \frac{\text{Range}_x}{N_x}$ y $dy = \frac{\text{Range}_y}{N_y}$.

---

## 3. Módulo 1: Microscopio Derecho (`app.py` — PyPrinting 3.0 Suite Completa)

El botón **`🚀 Iniciar Microscopio Derecho`** (Fila 1, Columna 1) abre la aplicación principal orquestadora basada en `QMainWindow` y `pyqtgraph.dockarea`.

### 3.1 Dock: Confocal (Mapeo 2D/3D & Centrado Sub-píxel)
* **Controles de Escaneo**:
  - `Laser`: Selecciona entre $532\ \text{nm}$ (verde) y $637\ \text{nm}$ (rojo).
  - `Range x / Range y (µm)`: Rango físico de escaneo ($0.1 - 100.0\ \mu\text{m}$).
  - `Pixels x / Pixels y`: Resolución de la matriz (típicamente $50 \times 50$ o $100 \times 100$).
  - `Scan mode`: `Ramp` (barrido continuo por hardware a alta velocidad) o `Step by step` (paso a paso discreto).
  - `Scan projection`: Plano de corte `x/y`, `x/z` o `y/z`.
  - `Scan Image`: `NPs maximum` (brillantes) o `NPs minimum` (inversión de absorción).
  - `method_center`: Algoritmo de centrado (`center of mass`, `center of gauss`, `two NP: center of gauss`, `donut (Laguerre-Gauss)`).
  - `Auto CM`: Al marcarse, desplaza automáticamente la platina al centro de masa o gaussiano calculado tras el escaneo.
  - `Filtro (%)`: Umbral de filtrado de ruido ($P\%$).

---

### 3.2 Dock: Trace (Trazas Temporales & Calibración BS)
* **Trazas de Fotoluminiscencia**:
  - Gráfica temporal continua con atajos **F1** (Iniciar captura) y **F2** (Detener y guardar).
  - `Laser 1 Combo` / `Laser 2 Combo`: Selección de líneas láser a monitorear.
  - `View Power BS`: Abre la ventana flotante `PowerBSWindow` para la calibración de 2 puntos del fotodiodo divisor (*Beam Splitter*) en $\text{mW/V}$.

---

### 3.3 Dock: Focus z (Autofoco Dinámico)
* **Controles de Enfoque**:
  - **`Go to maximum (F8)`**: Barrido axial rápido en Z para posicionarse en el pico máximo de señal.
  - **`Lock Focus (F9)`**: Congela el perfil Z de referencia.
  - **`Autocorrelation ×2 (F10)`**: Corrección de deriva axial por autocorrelación.

---

### 3.4 Dock: Shutters / Flipper / Láser 532
* **Obturadores & Atenuadores**:
  - `Shutter 532 nm`: Obturador digital del láser verde.
  - `Shutter 637 nm`: Obturador digital del láser rojo.
  - `Shutter 592 nm`: Obturador digital del láser amarillo.
  - `Low power`: Atenuador óptico de baja potencia.
  - `Mirror up`: Espejo escamotearle del filtro Notch de 532 nm (*Flipper*).
  - `Láser 532 Voltage`: Control de voltaje DAC ($1.0 - 5.0\ \text{V}$).

---

### 3.5 Dock: Nanopositioning (Platina PI)
* **Control Manual de la Platina Piezoeléctrica**:
  - Lectura en tiempo real de coordenadas $(X, Y, Z)$ en $\mu\text{m}$.
  - Flechas de movimiento incremental relativo ($\times 1$ y $\times 10$).

---

### 3.6 Ventana de Mediciones (Printing Automatizado & Dímeros)
* **Impresión de Grillas (`Printing`) & Ensamblado de Nanodímeros (`Dimers`)**:
  - Creación y carga de matrices de deposición en sustrato (`Create Grid` / `Load Grid`).
  - Configuración de umbrales de salto de intensidad `Umbral` ($I_{\text{new}} > \text{Umbral} \cdot I_{\text{old}}$), tiempo máximo `T max (s)` y promedios móviles `Steps before` / `Steps after`.
  - Secuencia automatizada con autofoco dinámico inter-nodo y post-escaneo confocal.

---

## 4. Módulo 2: PySpectrum *(En Construcción)*

El botón **`🔮 En Desarrollo Futuro`** (Fila 1, Columna 2) está reservado para la suite de espectrometría avanzadas:

> 🚧 **ESTADO: EN CONSTRUCCIÓN**
> 
> **Funcionalidades Planificadas**:
> - Integración y manejo directo de espectrómetros de rejilla CCD/EMCCD (reemplazo extendido de *Andor Solis*).
> - Rutinas automatizadas de **nano-termometría fotónica** por fluorescencia/luminiscencia dependiente de la temperatura.
> - Adquisición de espectros de dispersión (*scattering*) sobre nanopartículas individuales.
> - Lectura síncrona de espectros acoplada al escaneo de platinas piezoeléctricas y excitación láser.

---

## 5. Módulo 3: Microscopio Contrapropagante *(En Construcción)*

El botón **`🔍 En Desarrollo Futuro`** (Fila 1, Columna 3) está reservado para la arquitectura de microscopía dual:

> 🚧 **ESTADO: EN CONSTRUCCIÓN**
> 
> **Funcionalidades Planificadas**:
> - Adaptación de la arquitectura PyPrinting 3.0 para microscopía con doble iluminación y detección.
> - Observación simultánea coordinada mediante objetivo superior e invertido.
> - Excitación mediante haces láser contrapropagantes para pinzas ópticas y trampas fotónicas.

---

## 6. Módulo 4: PyPrinting 2 (Legacy — `PyPrinting_UNSAM.py`)

El botón **`🏛️ Iniciar PyPrinting 2`** (Fila 2, Columna 1) ejecuta la versión previa del software de impresión situada en `../printing2/PyPrinting_UNSAM.py`. Permite abrir la interfaz histórica para consulta de rutinas antiguas y comparación directa de protocolos experimentales.

---

## 7. Módulo 5: Cámara Live View (`camera.py`)

El botón **`📷 Iniciar Cámara Live View`** (Fila 2, Columna 2) lanza de forma independiente la ventana de transmisión de cámara en tiempo real:

* **Características Principales**:
  - **Soporte Réflex Canon EOS 500D (EDSDK 64-bit)** y **Webcams USB OpenCV**.
  - **Modos de Visualización**: `Color RGB` y `Grises (Transmisión)`.
  - **Ajuste de Contraste Dinámico (CLim Mín/Máx)** en escala de grises.
  - **Paletas LUT de Falso Color**: *Gris Estándar*, *Thermal*, *Viridis*, *Plasma*, *Inferno*, *Jet*.
  - **Ajustes Réflex**: Sensibilidad `ISO` (100–3200) y velocidad de `Obturación (Tv)`.
  - **Captura Fotográfica de Alta Resolución**: Foto limpia de 15 MP guardada en disco sin interrumpir el Live View.

---

## 8. Módulo 6: Modulación Láser 532 nm (`Laser532Window`)

El botón **`⚡ Iniciar Control Láser 532`** (Fila 2, Columna 3) lanza la ventana flotante independiente para el control del láser verde:

* **Funciones del Panel**:
  - **Deslizador y SpinBox de Voltaje**: Ajuste continuo de voltaje analógico DAC entre $1.0\ \text{V}$ y $5.0\ \text{V}$ (Canal NI-DAQ `Dev1/ao2`).
  - **Botones Preset**: Acceso directo con un solo clic a $1.0\text{V}$, $2.0\text{V}$, $3.0\text{V}$, $4.0\text{V}$ y $5.0\text{V}$.
  - **Botón Conmutador del Obturador (Shutter 532 nm)**:
    - **`► Abrir Shutter 532 nm (Cerrado)`** (Verde `#2e7d32`): Ejecuta `open_shutter("532 nm (green)")`.
    - **`■ Cerrar Shutter 532 nm (Abierto)`** (Rojo `#c62828`): Ejecuta `close_shutter("532 nm (green)")`.

---

## 9. Módulo 7: PSF Analyzer (`psf_analyzer.py`)

El botón **`📊 Iniciar PSF Analyzer`** (Fila 3, Columna 1) lanza la herramienta de caracterización analítica de la Función de Punto de Dispersión (PSF):

* **Características Principales**:
  - **Visualización Dual Vertical**: Carga independiente de imágenes `.tiff` para el Canal 1 (excitación verde, arriba) y Canal 2 (donut rojo, abajo).
  - **Modelos de Ajuste 2D**: `Gaussiana 2D` (7 parámetros) y `Donut (Laguerre-Gauss LG01)`.
  - **Filtro (%) de Ruido de Fondo**: Campo de texto interactivo. Al ingresar un valor y presionar **`Enter`** o hacer clic en **`Aplicar`**, el sistema recalcula en tiempo real las matrices filtradas $Z_f$, los fits 2D, las mapas de residuales ($|Z_n - Z_{\text{fit}}|$) y las métricas.
  - **Vistas Triples con Escala Z Dinámica**: Despliega por cada canal la imagen Original/Filtrada, el Modelo Ajustado y el Mapa de Residuales con barras de color Z dinámicas (`ColorBarItem`).
  - **Cortes de Perfil 1D Pasantes por el Centro**: Gráficos interactivos 1D configurables por canal (`Confocal 1`, `Confocal 2`, `Ambas superpuestas`) y dirección de corte pasante por $(x_0, y_0)$: `Horizontal`, `Vertical`, `Diagonal 45°` o `Diagonal 135°`.
  - **Falso Color RGB**: Superposición cromática configurable sobre `Imágenes Originales`, `Originales con Filtro` o `Modelos Ajustados (Fits)`.
  - **Informe de Métricas Completo**: Tabla con coordenadas sub-píxel $(x_0, y_0)$, radio $r_0$, elipticidad $a/b$, ángulo de orientación $\theta$, calidad del cero $I_{\min}/I_{\max}$, uniformidad angular $\sigma_{\theta}/\bar{I}$, bondad de ajuste ($R^2$, Error RMS, $\chi^2_{\text{red}}$) y desalineación dual $\Delta r_{\text{nm}}$.

---

## 10. Módulo 8: Analizador de Imágenes (`image_analyzer.py`)

El botón **`📐 Iniciar Analizador de Imágenes`** (Fila 3, Columna 2) abre la herramienta gráfica para imágenes estáticas:

* **Funciones Principales**:
  - Carga de imágenes en formato `.png`, `.jpg`, `.bmp`, `.tif`, `.tiff` (8, 16 y 32 bits).
  - **Calibración de Escala en $\mu\text{m/px}$**: Diálogo gráfico interactivo trazando una línea de referencia conocida.
  - **Reglas Tri-estado**: Conmutador para ocultar reglas, mostrar 1er par de ejes graduados o 2do par de ejes graduados sobre la imagen.
  - **Herramienta de Medición**: Medición directa de distancias con Snap magnético (`Shift`).
  - **Detección y Tracking de Partículas (`trackpy`)**: Identificación automática de centroides por masa y diámetro dentro de una ROI configurada.

---

## 11. Módulo 9: Documentación y Créditos del Autor

El panel de la Fila 3, Columna 3 agrupa la documentación y la información institucional del proyecto:

* **Botón `📘 Manual`**: Abre directamente este archivo de manual de usuario ([MANUAL_USUARIO.md](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/MANUAL_USUARIO.md)).
* **Botón `📖 README`**: Abre la documentación técnica general del repositorio ([README.md](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/README.md)).
* **Botón `🎓 Créditos`**: Despliega el diálogo modal con la información académica e institucional:
  - **Autor Principal**: José Luis González Peñafiel
  - **Cargo**: Becario Doctoral CONICET
  - **Institución**: Instituto de Nanosistemas (INS-UNSAM)
  - **Ubicación**: San Martín, Buenos Aires, Argentina
  - **Contacto**: `jose.lito.g.1999@gmail.com`
  - **GitHub**: `https://github.com/joselitog1999/pyprinting_3.0`

---

## 12. Flujos de Trabajo Experimentales (Protocolos Paso a Paso)

### 12.1 Mapeo Confocal 2D/3D y Ajuste de Partículas
1. Inicie **Microscopio Derecho** desde `main.py`.
2. En el Dock **Confocal**, configure `Range x/y` (ej. $10\ \mu\text{m}$) y `Pixels x/y` (ej. $50 \times 50$).
3. Seleccione `Scan mode: Ramp` y `method_center: center of gauss`.
4. Haga clic en **`Start Scan`**. Al concluir, el sistema ajustará la gaussiana 2D y moverá la platina PI al centro si `Auto CM` está activo.

### 12.2 Impresión Automatizada de Grillas
1. Desplace la platina a la región limpia del sustrato.
2. Abra `Measurements` $\rightarrow$ `Printing`, marque **`Set reference`** y configure las dimensiones de la grilla (`NPs/col`, `Columns`, `Dist NP`).
3. Configure `Umbral` (ej. `1.2`), `T max` (ej. `20` s) y `Steps before/after`.
4. Presione **`Imprimir folder`** para definir la carpeta y luego **`Play ►`**.

### 12.3 Fabricación Guiada de Nanodímeros Plasmónicos
1. Abra `Measurements` $\rightarrow$ `Dimers`.
2. Ingrese los valores de separación nanometrada `dx (µm)` y `dy (µm)`.
3. Ejecute el escaneo de localización de la partícula 1; el sistema aplicará el offset de posición e imprimirá la partícula 2 de forma automatizada.

---

## 13. Tabla de Atajos de Teclado & Preguntas Frecuentes (FAQ)

### Atajos de Teclado (Shortcuts)
| Tecla | Función | Módulo / Dock |
|---|---|---|
| **`Ctrl + A`** | Seleccionar directorio de trabajo base | Menú principal (`Files`) |
| **`Ctrl + S`** | Crear directorio diario automático (`YYYY-MM-DD`) | Menú principal (`Files`) |
| **`Ctrl + D`** | Abrir la carpeta del directorio actual en Explorer | Menú principal (`Files`) |
| **`Shift + Click`** | Snap magnético a partículas en mediciones | Cámara / Analizador de Imágenes |
| **`F1`** | Iniciar captura de Trazas dobles (Play) | Dock: Trace |
| **`F2`** | Detener captura de Trazas dobles (Stop) | Dock: Trace |
| **`F8`** | Ejecutar Autofoco Z (Go to maximum) | Dock: Focus z |
| **`F9`** | Congelar perfil de intensidad Z (Lock Focus) | Dock: Focus z |
| **`F10`** | Corrección por autocorrelación Z ($\times 2$) | Dock: Focus z |

---

### FAQ Rápida
* **¿Cómo ajustar el filtro de ruido en PSF Analyzer?**: Ingrese el porcentaje en el campo `Filtro (%)` y presione **`Enter`** o haga clic en **`Aplicar`**. Todo valor por debajo de ese porcentaje pico-a-fondo se forzará a cero recalculando la gaussiana 2D y residuales.
* **¿Cómo conmutar el obturador verde en Modulación Láser 532 nm?**: En la ventana `Laser532Window`, presione el botón **`► Abrir Shutter 532 nm`** (verde) o **`■ Cerrar Shutter 532 nm`** (rojo).

---

*Manual de Usuario de PyPrinting 3.0 — UNSAM Nanofotónica.*
