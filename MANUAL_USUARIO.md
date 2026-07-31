# Manual de Usuario: PyPrinting 3.0 🔬
**Sistema de Control, Espectroscopía Confocal y Nanofabricación Óptica**
*UNSAM — Nanofotónica*

---

## 📖 Índice

1. [Introducción y Arquitectura General](#1-introducción-y-arquitectura-general)
2. [Modos de Operación: Producción vs. Seguro](#2-modos-de-operación-producción-vs-seguro)
3. [Estructura de la Menú Bar Principal](#3-estructura-de-la-menú-bar-principal)
4. [Flujos de Trabajo Experimentales (Protocolos Paso a Paso)](#4-flujos-de-trabajo-experimentales-protocolos-paso-a-paso)
   - [4.1 Mapeo Confocal 2D/3D y Ajuste de Partículas (PSF)](#41-mapeo-confocal-2d3d-y-ajuste-de-partículas-psf)
   - [4.2 Impresión Automatizada de Redes/Grillas de Nanopartículas](#42-impresión-automatizada-de-redesgrillas-de-nanopartículas)
   - [4.3 Fabricación Guiada de Nanodímeros Plasmónicos](#43-fabricación-guiada-de-nanodímeros-plasmónicos)
   - [4.4 Medición con Cámara y Alineación Óptica](#44-medición-con-cámara-y-alineación-óptica)
   - [4.5 Adquisición de Trazas Temporales y Calibración de Potencia BS](#45-adquisición-de-trazas-temporales-y-calibración-de-potencia-bs)
5. [Descripción Detallada de Docks, Ventanas y Controles](#5-descripción-detallada-de-docks-ventanas-y-controles)
   - [5.1 Dock: Confocal](#51-dock-confocal)
   - [5.2 Dock: Trace (Trazas Dobles y Ventana Power BS)](#52-dock-trace-trazas-dobles-y-ventana-power-bs)
   - [5.3 Dock: Focus z](#53-dock-focus-z)
   - [5.4 Dock: Shutters / Flipper / Láser 532](#54-dock-shutters--flipper--láser-532)
   - [5.5 Dock: Nanopositioning](#55-dock-nanopositioning)
   - [5.6 Ventana de Mediciones (Printing & Dimers)](#56-ventana-de-mediciones-printing--dimers)
   - [5.7 Ventana de Cámara Réflex Canon EOS 500D](#57-ventana-de-cámara-réflex-canon-eos-500d)
   - [5.8 Ventana de Analizador de Imágenes Estáticas](#58-ventana-de-analizador-de-imágenes-estáticas)
6. [Tabla de Atajos de Teclado (Shortcuts)](#6-tabla-de-atajos-de-teclado-shortcuts)
7. [Preguntas Frecuentes (FAQ)](#7-preguntas-frecuentes-faq)
   - [7.1 ¿Cómo se determina el centro de la partícula al realizar un escaneo confocal?](#71-cómo-se-determina-el-centro-de-la-partícula-al-realizar-un-escaneo-confocal)
   - [7.2 ¿Qué sucede exactamente en el sistema al ejecutar un escaneo desde el widget Confocal?](#72-qué-sucede-exactamente-en-el-sistema-al-ejecutar-un-escaneo-desde-el-widget-confocal)

---

## 1. Introducción y Arquitectura General

**PyPrinting 3.0** es una suite de software científico desarrollada en **Python 3 / PyQt6** diseñada para laboratorios de nanofotónica. El sistema automatiza experimentos de:
* **Microscopía Confocal Láser**: Barridos 2D y 3D con lectura síncrona por disparo de hardware.
* **Impresión Óptica (Fototérmica / Transferencia dirigida por radiación)**: Deposición controlada de nanopartículas individuales (oro, plata, dieléctricos) organizada en matrices predefinidas.
* **Ensamblado Plasmónico de Dímeros**: Impresión precisa de pares de nanopartículas a separaciones nanométricas para generar hot-spots de campo cercano.
* **Estabilización de Foco Z**: Corrección activa de deriva térmica mediante autocorrelación de señal luminosa.
* **Visión por Computadora & Microscopía de Transmisión**: Transmisión Live View desde cámaras réflex Canon EOS con paletas LUT, balance de blancos, contraste CLim, calibración espacial ($\mu\text{m/píxel}$) y seguimiento dinámico de nanopartículas (`trackpy`).

La interfaz principal utiliza un sistema modular de **Docks** dinámicos basados en `pyqtgraph.dockarea`, permitiendo al operador desacoplar, mover o reorganizar todos los paneles de control según las necesidades del experimento.

---

## 2. Modos de Operación: Producción vs. Seguro

El sistema cuenta con dos modos de arranque configurables:

### 🔴 Modo Producción (Hardware Real)
Conecta directamente con la platina piezoeléctrica **Physik Instrumente (PI E-517/E-736)** vía USB, la tarjeta **National Instruments (NI-DAQmx PCIe/USB-6353)** y la cámara física Canon EOS por SDK.
```powershell
.\.venv\Scripts\python.exe app.py
```

### 🟢 Modo Seguro (`SAFE_MODE` — Simulación)
Permite ejecutar el 100% de la interfaz gráfica, botones, ventanas y algoritmos de mediciones/impresión en cualquier computadora sin hardware conectado.
* **Platina PI**: Emulada con actualización coherente de coordenadas.
* **NI-DAQ**: Generación de señales analógicas sintéticas con ruido gaussiano.
* **Cámara**: Transmisión sintética Live View ($1056 \times 704$) a 25 FPS con patrón en movimiento.
```powershell
$env:PYPRINTING_SAFE="1"
.\.venv\Scripts\python.exe app.py
```

---

## 3. Estructura de la Menú Bar Principal

La barra superior de menús proporciona accesos directos globales a la gestión de archivos, herramientas avanzadas, mediciones y personalización de interfaz:

| Menú | Opción | Atajo | Función / Descripción |
|---|---|---|---|
| **Files** | `Seleccionar directorio` | `Ctrl + A` | Abre un cuadro de diálogo para seleccionar la carpeta base de trabajo donde se guardarán todos los datos. |
| **Files** | `Crear directorio diario` | `Ctrl + S` | Crea automáticamente una subcarpeta nombrada con la fecha actual (`YYYY-MM-DD`) dentro del directorio de datos. |
| **Files** | `Abrir directorio` | `Ctrl + D` | Abre la carpeta de trabajo actual directamente en el Explorador de archivos de Windows. |
| **Files** | `Cargar última posición` | — | Lee el archivo de sesión previa y posiciona la platina PI en las últimas coordenadas $(X, Y, Z)$ registradas. |
| **Tools** | `Cámara` | — | Despliega la ventana flotante de control Live View de la cámara Réflex Canon EOS 500D (`CameraWindow`). |
| **Tools** | `Analizador de Imágenes` | — | Abre la ventana flotante independiente del Analizador de Imágenes estáticas (`ImageAnalyzerWindow`). |
| **Tools** | `Láser 532` | — | Despliega la ventana de control analógico de potencia/voltaje DAC para el láser verde de 532 nm. |
| **Tools** | `Load Grid` | — | Importa un archivo de coordenadas de grilla personalizada (`.txt`) para secuencias de impresión. |
| **Measurements** | `Printing` | — | Abre la ventana flotante de control de impresión automatizada de nanopartículas individuales. |
| **Measurements** | `Dimers` | — | Abre la ventana flotante para fabricación guiada de nanodímeros plasmónicos con barridos pre/post. |
| **Docks** | `Guardar configuración` | — | Memoriza la disposición geométrica y posiciones de todos los docks en la pantalla actual. |
| **Docks** | `Restaurar configuración` | — | Restablece los docks a su diseño y proporciones predeterminadas de fábrica. |

---

## 4. Flujos de Trabajo Experimentales (Protocolos Paso a Paso)

### 4.1 Mapeo Confocal 2D/3D y Ajuste de Partículas (PSF)

```
[Seleccionar Láser] ──> [Definir Rango X/Y y Píxeles] ──> [Start Scan] ──> [Cálculo CM / Gauss 2D] ──> [Go to NP1]
```

1. **Seleccionar Línea de Excitación**: En el panel **Confocal**, elija el láser deseado (`532 nm (green)` o `637 nm (red)`).
2. **Configurar Parámetros del Barrido**:
   * Ajuste el tamaño del área a escanear en `Range x (µm)` y `Range y (µm)` (ejemplo: $2 \times 2\ \mu\text{m}$).
   * Ingrese la resolución espacial en `Pixels x` y `Pixels y` (ejemplo: $34 \times 34$ píxeles).
3. **Seleccionar Modo de Escaneo y Proyección**:
   * `Scan Mode`: `Ramp` (barrido continuo por hardware) o `Step by step` (paso a paso).
   * `PSF Mode`: `x/y` (plano horizontal focal), `x/z`, `y/x`, `y/z` (cortes axiales).
4. **Ejecutar el Barrido**: Haga clic en **`Start Scan`**. La imagen fotónica se construirá en tiempo real en la pantalla central (`Viewbox`).
5. **Localizar el Centro de la Nanopartícula**:
   * En `method of center`, seleccione `center of gauss` o `center of mass`.
   * Presione **`Go to NP1`**. La platina piezoeléctrica moverá el haz láser exactamente a las coordenadas sub-nanométricas del pico ajustado.

---

### 4.2 Impresión Automatizada de Redes/Grillas de Nanopartículas

```
[Establecer Coordenada Ref.] ──> [Crear Grilla] ──> [Configurar Umbral e Intensidad] ──> [Imprimir] ──> [Ciclo Automatizado]
```

1. **Definir Posición de Origen (Referencia)**:
   * Mueva la platina al área limpia del sustrato donde comenzará la grilla.
   * Abra la ventana **Measurements** (`Measurements` $\rightarrow$ `Printing`).
   * En el Dock *Reference pos*, presione **`Set reference`**.
2. **Crear o Cargar la Grilla**:
   * **Opción A (Crear)**: En el Dock *Grid*, especifique `NPs/col` (ej. 5), `Columns` (ej. 5), `Dist NP (µm)` (ej. 5.0) y `Dist col (µm)` (ej. 5.0). Haga clic en **`Create Grid`**.
   * **Opción B (Cargar)**: Presione **`Load Grid`** o use la barra de menú `Tools` $\rightarrow$ `Load Grid` para importar una matriz `.txt`.
3. **Configurar Parámetros en el Panel Multicolumna (`Printing control`)**:
   * Defina el incremento de señal en `Umbral` (ej. `1.2` para un salto del 20%).
   * Defina el umbral inferior en `Umbral down` (para detectar desprendimiento o fotoblanqueamiento).
   * Ingrese el tiempo máximo en `T max (s)` (ej. `20` s).
   * Ingrese los puntos de promedio móvil en `Steps before` (ej. `10`) y `Steps after` (ej. `10`).
   * Active `Scan pre-print?` si requiere mapa confocal previo en cada celda.
4. **Iniciar la Secuencia Automática**:
   * Presione **`Imprimir folder`** para definir el directorio y luego **`Play ►`**.
   * El sistema ejecutará automáticamente para cada nodo:
     1. Movimiento a la celda objetivo.
     2. Ciclo de **Autofoco Z** para compensar deriva térmica.
     3. Apertura del obturador y trazado continuo.
     4. Cierre del obturador al detectar el salto de intensidad por encima del umbral.
     5. Conteo y salto automático al siguiente índice (`Next index ►`).

---

### 4.3 Fabricación Guiada de Nanodímeros Plasmónicos

```
[Mapear Partícula 1 (Pre-Scan)] ──> [Ajustar Centro Gaussiano] ──> [Aplicar Off-Set (dx, dy)] ──> [Imprimir Partícula 2] ──> [Post-Scan Caracterización]
```

1. Abra la ventana de mediciones en modo Dímeros (`Measurements` $\rightarrow$ `Dimers`).
2. Defina el desplazamiento requerido entre la primera y la segunda partícula en `dx (µm)` y `dy (µm)` (ej. $dx = 0.08\ \mu\text{m} = 80\ \text{nm}$).
3. Active `Scan pre-print?` (Pre-scan) y `Post scan?`.
4. Inicie el protocolo pulsando **`Dimers folder`** $\rightarrow$ **`Play ►`**.
5. **Flujo Interno Automatizado**:
   * **Center-Scan**: Barrido de la partícula inicial y cálculo de su centro $(x_1, y_1)$.
   * **Off-set Nanométrico**: Movimiento de la platina a $(x_1 + dx, y_1 + dy)$.
   * **Pre-Scan**: Mapeo de la zona previa.
   * **Impresión**: Exposición láser hasta detectar la unión de la segunda nanopartícula.
   * **Post-Scan**: Mapeo confocal final revelando el nanodímero plasmónico.

---

### 4.4 Medición con Cámara y Alineación Óptica

1. Abra la ventana flotante de cámara desde la barra de menú: `Tools` $\rightarrow$ `Cámara`.
2. **Seleccionar Modo de Imagen**:
   * `Color RGB`: Transmisión estándar en color para alineación óptica.
   * `Grises (Transmisión)`: Modo especializado en microscopía de transmisión con ajuste de contraste **CLim (Mín/Máx)** y falso color **LUT** (*Gris*, *Thermal*, *Viridis*, *Plasma*, *Inferno*, *Jet*).
3. **Control Live View & Captura**:
   * Haga clic en **`Iniciar Cámara`**.
   * Ajuste `ISO` (Auto, 100-3200) y tiempo de exposición `Obturación (Tv)`.
   * Presione **`Capturar Foto`** para guardar una imagen de alta resolución de 15 MP descargada a la PC.
4. **Seguimiento de Partículas (Tracking)**:
   * Abra el cuadro de diálogo de detección `trackpy`, ingrese el tamaño de partícula en $\mu\text{m}$ (convertido internamente a píxeles impares $\ge 3$) y ejecute el conteo en tiempo real.

---

### 4.5 Adquisición de Trazas Temporales y Calibración de Potencia BS

1. **Lectura de Trazas Dobles Simultáneas**:
   - En el Dock **Trace** (ubicado abajo de todo a todo el ancho):
     - Seleccione **Láser 1** (ej. `532 nm (green)`).
     - Seleccione **Láser 2** (ej. `637 nm (red)` o `"None"`).
     - Presione **`► Play / ■ Stop`** (o tecla **`F1`**).
     - Al presionar Play se abrirán en simultáneo los obturadores de los lásers seleccionados y se graficarán ambas trazas en paralelo.
     - Presione **`■ Stop`** (o **`F2`**). Los obturadores se cerrarán automáticamente y los datos se guardarán en `.txt`.
2. **Calibración de Potencia en el Plano Focal Trasero (`PowerBSWindow`)**:
   - Haga clic en el botón **`View Power BS`**. Se abrirá la ventana flotante de calibración.
   - Mientras la ventana permanezca abierta, la medición de potencia BS estará **activa automáticamente**.
   - Ingrese los mW medidos comercialmente en `High (mW)` y `Low (mW)` y presione **`Set High`** y **`Set Low`**.
   - Haga clic en **`Set Calibration`**. El sistema calculará `Slope` (mW/V) e `Intercept` (mW) y actualizará la lectura digital en mW e integrará el gráfico continuo **`Trace on BS`** abajo de los controles.

---

## 5. Descripción Detallada de Docks, Ventanas y Controles

### 5.1 Dock: Confocal (`ConfocalFrontend`)

| Elemento | Tipo | Función / Descripción |
|---|---|---|
| **Láser Combo** | `QComboBox` | Selecciona la línea de excitación láser (`532 nm (green)`, `637 nm (red)`). |
| **Scan Mode Combo** | `QComboBox` | Selecciona entre barrido continuo `Ramp` o barrido paso a paso `Step by step`. |
| **PSF Mode Combo** | `QComboBox` | Selecciona el plano de proyección del barrido (`x/y`, `x/z`, `y/x`, `y/z`), ubicado al lado de `scan_mode`. |
| **Range x (µm)** | `QLineEdit` | Tamaño del campo de visión en el eje horizontal ($\mu\text{m}$). |
| **Range y (µm)** | `QLineEdit` | Tamaño del campo de visión en el eje vertical ($\mu\text{m}$). |
| **Pixels x / y** | `QLineEdit` | Resolución de la imagen (número de puntos por fila/columna). Recomendado: múltiplos de 16. |
| **`Start Scan`** | `QPushButton` | Inicia el barrido confocal síncrono en el plano y modo seleccionados. |
| **`Stop`** | `QPushButton` | Interrumpe inmediatamente el escaneo en curso y cierra el obturador láser. |
| **`Save Frame`** | `QPushButton` | Guarda las matrices de la imagen actual (`.tiff` y `.txt`) en el directorio de trabajo. |
| **`Go to NP1`** | `QPushButton` | Posiciona la platina en las coordenadas del pico ajustado para la Nanopartícula 1. |
| **`Go to NP2`** | `QPushButton` | Posiciona la platina en las coordenadas calculadas para la Nanopartícula 2 (si aplica). |
| **Auto CM** | `QCheckBox` | Si está activo, tras un escaneo el piezo se desplaza automáticamente al centro de masa. |
| **Scan Image Combo** | `QComboBox` | Define el contraste dinámico (`NPs maximum`, `NPs minimum`, `choose`). |
| **Method Center Combo**| `QComboBox` | Algoritmo de ajuste de centro (`center of mass`, `center of gauss`, `two NP: center of gauss`). |
| **`DRIFT measurement`**| `QPushButton` | Inicia la medición periódica de deriva espacial ajustando la posición Gaussiana a intervalos regulables. |

---

### 5.2 Dock: Trace (`TraceFrontend` — Trazas Dobles y Ventana Power BS)

| Elemento | Tipo | Función / Descripción |
|---|---|---|
| **Láser 1 Combo** | `QComboBox` | Selecciona la primera línea de excitación láser a monitorear. |
| **Láser 2 Combo** | `QComboBox` | Selecciona la segunda línea de excitación o `"None"` (al seleccionar None desactiva el 2do obturador y canal). |
| **`► Play / ■ Stop`** | `QPushButton` | Abre los obturadores de los lásers seleccionados e inicia/detiene el trazado simultáneo (Atajos **F1** / **F2**). |
| **PointLabel** | `QLabel` | Muestra en tiempo real las intensidades numéricas instantáneas en Volts ($I_{L1} \mid I_{L2}$). |
| **`Save trace`** | `QPushButton` | Guarda manualmente la traza temporal de ambos canales en un archivo `.txt`. |
| **`View Power BS`** | `QPushButton` | Abre la ventana flotante independiente de calibración de potencia y monitoreo `PowerBSWindow`. |
| **`Active Power BS`** | `QPushButton` *(En PowerBSWindow)* | Botón de alternancia de medición activa en tiempo real (mantenido encendido automáticamente al abrir la ventana). |
| **`High/Low (mW)`** | `QLineEdit` *(En PowerBSWindow)* | Ingreso de lecturas del medidor de potencia comercial para calibración de 2 puntos. |
| **`Set High/Low`** | `QPushButton` *(En PowerBSWindow)* | Asigna la lectura actual del fotodiodo BS al punto de calibración alto o bajo. |
| **`Set Calibration`**| `QPushButton` *(En PowerBSWindow)* | Calcula la pendiente `Slope` (mW/V) e intersección `Intercept` (mW). |
| **`Trace on BS`** | Plot *(En PowerBSWindow)* | Gráfica temporal continua dedicada del fotodiodo divisor colocada abajo de los controles. |

---

### 5.3 Dock: Focus z (`FocusFrontend`)

| Elemento | Tipo | Función / Descripción |
|---|---|---|
| **`Go to maximum (F8)`**| `QPushButton` | Realiza un barrido rápido en Z y desplaza la platina al pico de máxima intensidad óptica. |
| **`Lock Focus (F9)`** | `QPushButton` | Registra y congela el perfil de intensidad Z actual como firma de referencia de enfoque. |
| **`Autocorrelation ×2 (F10)`**| `QPushButton` | Correlaciona la señal Z actual con el perfil locked y ajusta el foco a la coincidencia óptima. |

---

### 5.4 Dock: Shutters / Flipper / Láser 532 (`ShuttersFrontend`)

| Elemento | Tipo | Función / Descripción |
|---|---|---|
| **Shutter 532 nm** | `QCheckBox` | Abre o cierra el obturador digital del láser verde de 532 nm (Canal DO 12, PD ai0). |
| **Shutter 637 nm** | `QCheckBox` | Abre o cierra el obturador digital del láser rojo de 637 nm (Canal DO 11, PD ai1). |
| **Shutter 592 nm** | `QCheckBox` | Abre o cierra el obturador digital del láser amarillo de 592 nm (Canal DO 10, PD ai3). |
| **Low power** | `QCheckBox` | Activa/Desactiva el atenuador óptico de baja potencia. |
| **Mirror up** | `QCheckBox` | Levanta o baja el espejo escamotearle del filtro Notch de 532 nm (*Flipper*). |
| **Láser 532 Voltage**| `QSlider` / `QDoubleSpinBox` | Control de voltaje analógico DAC ($1.0 - 5.0\ \text{V}$) para ajustar la potencia del láser verde continuo. |

---

### 5.5 Dock: Nanopositioning (`NanoFrontend`)

| Elemento | Tipo | Función / Descripción |
|---|---|---|
| **`Read position`** | `QPushButton` | Lee y actualiza la posición actual en tiempo real de los ejes X, Y, Z de la platina PI. |
| **Flechas $x, y, z$** | `QPushButton` | Movimientos incrementales relativos en dirección positiva o negativa ($\times 1$ y $\times 10$). |
| **step x/y [µm]** | `QLineEdit` | Tamaño del paso incremental para movimientos en el plano XY ($\mu\text{m}$). |
| **step z [µm]** | `QLineEdit` | Tamaño del paso incremental para el eje Z ($\mu\text{m}$). |
| **`Set reference`** | `QPushButton` | Guarda las coordenadas actuales como origen de referencia para el panel *Go to*. |
| **`Go to`** | `QPushButton` | Mueve la platina de forma absoluta a las coordenadas $(X, Y, Z)$ ingresadas en las casillas. |

---

### 5.6 Ventana de Mediciones (`MeasFrontend` — Printing & Dimers)

El panel **Printing control** cuenta con una disposición matricial de 4 columnas para máxima claridad visual:

| Elemento / Columna | Tipo | Función / Descripción |
|---|---|---|
| **`Imprimir/Dimers folder`** | `QPushButton` | Abre el cuadro de diálogo para definir la carpeta destino del experimento. |
| **NameDirValue** | `QLabel` | Muestra el estado del directorio (en verde si está listo, en rojo si falta configurar). |
| **Láser** | `QComboBox` | Selecciona la línea láser de excitación utilizada para la impresión óptica. |
| **Umbral** | `QLineEdit` | Factor multiplicativo del salto de intensidad para detectar la deposición ($I_{new} > \text{Umbral} \cdot I_{old}$). |
| **Umbral down** | `QLineEdit` | Umbral inferior de caída de señal para detectar desprendimiento o fotoblanqueamiento. |
| **T max (s)** | `QLineEdit` | Tiempo máximo de exposición láser permitido por celda antes de abortar. |
| **Steps before** | `QLineEdit` | Número de puntos promediados pre-exposición para calcular la línea base ($I_{old}$). |
| **Steps after** | `QLineEdit` | Número de puntos promediados tras el punto actual para evaluar la condición de umbral ($I_{new}$). |
| **Scan pre-print?** | `QCheckBox` | Habilita un barrido confocal de confirmación previa antes de abrir el obturador. |
| **Post scan?** *(Dimers)* | `QCheckBox` | Habilita un barrido confocal caracterizador tras completar la unión de la 2da partícula. |
| **`Play ►`** | `QPushButton` | Inicia la secuencia automatizada de impresión paso a paso a lo largo de la grilla. |
| **`Pause`** | `QPushButton` | Pausa temporalmente el avance automático manteniendo el índice actual. |
| **`Next index ►`** | `QPushButton` | Omite la celda actual y salta directamente al siguiente objetivo de la matriz. |
| **Total targets** | `QLabel` | Muestra el número total de partículas/nodos a fabricar en la grilla actual. |
| **Target Index** | `QLineEdit` | Muestra o permite editar manualmente el índice de partícula objetivo en ejecución. |
| **`Set reference` / `Go reference`** | `QPushButton` | Guarda o desplaza la platina al origen de coordenadas $(X_{ref}, Y_{ref}, Z_{ref})$. |
| **Autofocus every N** | `QLineEdit` | Frecuencia de ciclos de enfoque Z automático (ej. ejecutar autofoco cada 2 celdas). |
| **Shift x / y (µm)** | `QLineEdit` | Desplazamiento fino del haz óptico respecto al centro del mapa confocal. |
| **dx / dy (µm)** *(Dimers)* | `QLineEdit` | Separación nanometrada deseada entre la primera y la segunda nanopartícula del dímero. |

---

### 5.7 Ventana de Cámara Réflex Canon EOS 500D (`canon_test.py` / `canon_edsdk.py`)

| Elemento | Tipo | Función / Descripción |
|---|---|---|
| **`Iniciar Cámara`** | `QPushButton` | Abre la sesión EDSDK USB e inicia el flujo Live View nativo a 25 FPS ($1056 \times 704$). |
| **Modo Imagen** | `QComboBox` | Conmuta entre `Color RGB` y `Grises (Transmisión)` para microscopía de transmisión. |
| **Mín / Máx (CLim)** | `QSlider` | Deslizadores de intensidad mínima y máxima para ajustar el rango dinámico en modo grises. |
| **Colormap (LUT)** | `QComboBox` | Aplica paletas de falso color en tiempo real (*Gris Estándar*, *Thermal*, *Viridis*, *Plasma*, *Inferno*, *Jet*). |
| **Ganancia R / G / B** | `QSlider` | Deslizadores de balance de blancos para multiplicar canales cromáticos en modo RGB ($<1\text{ ms}$). |
| **ISO Speed** | `QComboBox` | Ajusta la sensibilidad ISO del sensor Canon (Auto, 100, 200, 400, 800, 1600, 3200). |
| **Obturación (Tv)** | `QComboBox` | Ajusta el tiempo de exposición del obturador mecánico (desde 1/10s hasta 10s). |
| **Zoom Mode** | `QComboBox` | Conmuta entre zoom digital ($1\times, 2\times$) y zoom por hardware ($5\times, 10\times$). |
| **`Capturar Foto`** | `QPushButton` | Dispara el obturador de 15 MP, descarga la imagen a la PC y reactiva el Live View sin bloqueos. |

---

### 5.8 Ventana de Analizador de Imágenes Estáticas (`image_analyzer.py`)

| Elemento | Tipo | Función / Descripción |
|---|---|---|
| **`📁 Abrir Foto`** | `QPushButton` | Carga archivos de imagen estáticos (`.png`, `.jpg`, `.bmp`, `.tif`, `.tiff` de 8/16/32 bits). |
| **Indicador de Escala** | `QLabel` | Muestra en **verde** (`Escala configurada: X.XXXXX µm/px`) o en **rojo** (`Escala no configurada`). |
| **`Configurar Escala`** | `QPushButton` | Abre el diálogo gráfico para trazar un trazo de longitud conocida en $\mu\text{m}$. |
| **`ROI detect`** | `QPushButton` | Permite definir un rectángulo de región de interés para restringir el análisis de partículas. |
| **`Detectar Partículas`**| `QPushButton` | Ejecuta el algoritmo `trackpy` especificando masa y diámetro en $\mu\text{m}$/píxeles. |
| **`Medir`** | `QPushButton` | Activa la herramienta de medición entre 2 puntos con soporte para Snap magnético (`Shift`). |
| **Reglas Tri-estado** | `QPushButton` | Alterna entre reglas invisibles, 1er par de ejes graduados y 2do par de ejes graduados en $\mu\text{m/px}$. |
| **`📷 Exportar Foto`** | `QPushButton` | Renderiza la imagen procesada junto a todas las capas de overlay y la guarda en disco. |

---

## 6. Tabla de Atajos de Teclado (Shortcuts)

| Tecla de Acceso Directo | Función Asociada | Módulo / Dock |
|---|---|---|
| **`Ctrl + A`** | Seleccionar directorio de trabajo base | Menú principal (`Files`) |
| **`Ctrl + S`** | Crear directorio diario automático (`YYYY-MM-DD`) | Menú principal (`Files`) |
| **`Ctrl + D`** | Abrir la carpeta del directorio actual en Explorer | Menú principal (`Files`) |
| **`Shift + Click/Arrastrar`** | Activar Snap magnético a partículas/referencia en mediciones | Cámara / Analizador de Imágenes |
| **`F1`** | Iniciar captura de Trazas dobles en tiempo real (Play) | Dock: Trace |
| **`F2`** | Detener captura de Trazas dobles y guardar datos (Stop) | Dock: Trace |
| **`F8`** | Ejecutar Autofoco Z (Go to maximum) | Dock: Focus z |
| **`F9`** | Congelar perfil de intensidad Z (Lock Focus) | Dock: Focus z |
| **`F10`** | Ejecutar corrección por autocorrelación Z ($\times 2$) | Dock: Focus z |

---

## 7. Preguntas Frecuentes (FAQ)

### 7.1 ¿Cómo se determina el centro de la partícula al realizar un escaneo confocal?

El cálculo del centro de la nanopartícula durante y al finalizar un escaneo confocal en **PyPrinting 3.0** (`confocal.py` y `psf.py`) se realiza mediante un pipeline de 4 pasos continuos:

1. **Normalización de la Imagen (`_norm_image`)**:
   Al completarse la matriz de fotodetector $Z$ ($N_x \times N_y$), el sistema normaliza la imagen entre $0.0$ y $1.0$:
   $$Z_n = \frac{Z - Z_{\min}}{Z_{\max} - Z_{\min}}$$
   Dependiendo de la opción en el combo `Scan Image`:
   - **`NPs maximum`**: Mantiene nanopartículas brillantes (dispersión/fluorescencia).
   - **`NPs minimum`**: Invierte la matriz ($|Z_n - 1|$) para nanopartículas oscuras (absorción).

2. **Filtrado por Umbral de Ruido (`_filter_image`)**:
   Para evitar que el ruido del fondo desvíe la localización del centro, se aplica un filtro umbral de intensidad al **30%** ($0.30$):
   $$\text{Si } Z_n < 0.30 \implies Z_f = 0.0$$
   Esto conserva únicamente el perfil luminoso correspondiente a la respuesta de la partícula (PSF).

3. **Algoritmo de Ajuste del Centro (Combo `method_center`)**:
   - **`center of mass` (Centro de Masa Ponderado)**: Utiliza `scipy.ndimage.measurements.center_of_mass(Zf)`. Calcula el centroide ponderado en píxeles:
     $$x_o = \frac{\sum x \cdot Z_f(x,y)}{\sum Z_f(x,y)}, \quad y_o = \frac{\sum y \cdot Z_f(x,y)}{\sum Z_f(x,y)}$$
   - **`center of gauss` (Ajuste Gaussiano 2D Sub-píxel — Recomendado)**: Toma el centro de masa como semilla e integra un ajuste por mínimos cuadrados no lineales (`scipy.optimize.curve_fit`):
     $$G(x,y) = Z_{\text{offset}} + A \cdot \exp\left(-\left[a(x-x_0)^2 + 2b(x-x_0)(y-y_0) + c(y-y_0)^2\right]\right)$$
     Devuelve las coordenadas $(x_0, y_0)$ con precisión sub-nanométrica.
   - **`two NP: center of gauss` (Doble Partícula / Nanodímeros)**: Identifica los dos picos locales mediante `skimage.feature.peak_local_max` y ajusta una función de dos gaussianas 2D superpuestas (`two_gaussian2D`) para obtener la posición exacta de ambas partículas $(x_1, y_1)$ y $(x_2, y_2)$.

4. **Conversión a Coordenadas Físicas ($\mu\text{m}$) (`_coords`)**:
   Convierte las coordenadas en píxeles $(x_o, y_o)$ a la posición absoluta en micrómetros de la platina piezoeléctrica **Physik Instrumente (PI)**:
   $$X_{\text{físico}} = X_{\text{origen}} - \frac{\text{Range}_x}{2} + \frac{dx}{2} + (x_o \cdot dx)$$
   $$Y_{\text{físico}} = Y_{\text{origen}} - \frac{\text{Range}_y}{2} + \frac{dy}{2} + (y_o \cdot dy)$$
   donde $dx = \frac{\text{Range}_x}{N_x}$ y $dy = \frac{\text{Range}_y}{N_y}$.

**Acciones Automatizadas Tras la Detección**:
- **Si `Auto CM` está activo**: La platina PI se desplaza automáticamente (`_moveto`) al centro exacto $(X_{\text{físico}}, Y_{\text{físico}})$ apenas termina el escaneo.
- **Botón `Go to NP1` / `Go to NP2`**: Mueve manualmente el piezo al centro calculado de la partícula 1 o 2 en cualquier momento.

---

### 7.2 ¿Qué sucede exactamente en el sistema al ejecutar un escaneo desde el widget Confocal?

Al hacer clic en **`Start Scan`** en el widget **Confocal**, la interfaz (`Frontend`) y el hilo de control (`Backend`) ejecutan una secuencia coordinada de 4 etapas:

1. **Preparación e Inicio**:
   - Oculta los marcadores de centro de masa/gaussiano de escaneos anteriores en el visor central (`Viewbox`).
   - Captura el láser seleccionado (532 nm o 637 nm), el rango de escaneo (`Range x/y` en $\mu\text{m}$), la resolución (`Pixels x/y`), el modo de escaneo (`Ramp` o `Step by step`) y la proyección (`x/y`, `x/z`, `y/x`, `y/z`).
   - Llama a `start_scan_routines` en el backend.

2. **Adquisición de Datos y Barrido Óptico**:
   - **En modo `Ramp` (Barrido continuo por hardware — Alta velocidad)**:
     - Registra las coordenadas de origen $(X_{pos}, Y_{pos}, Z_{pos})$ de la platina PI.
     - Configura en el controlador PI un movimiento de rampa lineal síncrono para el eje rápido ($X$).
     - Llama a `open_shutter(laser)` activando la línea de excitación en la tarjeta National Instruments (NI-DAQ).
     - Ejecuta un bucle por líneas: mueve el eje lento ($Y$), dispara la rampa en $X$, lee síncronamente el fotodiodo mediante el reloj de hardware NI-DAQmx, construye la fila de imagen y emite `dataSignal` para actualizar la pantalla térmica en tiempo real.
   - **En modo `Step by step` (Barrido discreto punto por punto)**:
     - Mueve el piezo a cada par $(x_i, y_j)$, abre el obturador, lee $N$ muestras analógicas del fotodiodo, promedia el valor y actualiza el píxel.

3. **Cierre de Dispositivos y Cálculo del Centro**:
   - Al completar la última fila/píxel, detiene los timers de reloj y llama a `close_shutter(laser)` para proteger la muestra.
   - Ejecuta el cálculo de centro de partícula `_CMmeasure()` (normalización, umbral al 30%, ajuste gaussiano/CM y conversión a $\mu\text{m}$).
   - Coloca una marca gráfica (cruz o punto rojo) sobre el visor central en la posición exacta calculada.

4. **Posicionamiento Final y Guardado (`_post_scan_dispatch`)**:
   - **Posicionamiento PI**: Si `Auto CM` está marcado, mueve automáticamente la platina PI al centro calculado de la nanopartícula; de lo contrario, regresa el piezo al centro original del área escaneada $(X_{pos}, Y_{pos})$.
   - **Guardado**: Exporta automáticamente la imagen procesada a disco en formato `.tiff` dentro de la carpeta de trabajo.
   - **Notificación**: Emite `scandoneSignal` informando que el escaneo concluyó con éxito.

---

*Manual de Usuario de PyPrinting 3.0 — UNSAM Nanofotónica.*
