# Manual de Usuario: PyPrinting 3.0 🔬
**Sistema de Control, Espectroscopía Confocal y Nanofabricación Óptica**
*UNSAM — Nanofotónica*

---

## 📖 Índice

1. [Introducción y Arquitectura General](#1-introducción-y-arquitectura-general)
2. [Modos de Operación: Producción vs. Seguro](#2-modos-de-operación-producción-vs-seguro)
3. [Flujos de Trabajo Experimentales (Protocolos Paso a Paso)](#3-flujos-de-trabajo-experimentales-protocolos-paso-a-paso)
   - [3.1 Mapeo Confocal 2D/3D y Ajuste de Partículas (PSF)](#31-mapeo-confocal-2d3d-y-ajuste-de-partículas-psf)
   - [3.2 Impresión Automatizada de Redes/Grillas de Nanopartículas](#32-impresión-automatizada-de-redesgrillas-de-nanopartículas)
   - [3.3 Fabricación Guiada de Nanodímeros Plasmónicos](#33-fabricación-guiada-de-nanodímeros-plasmónicos)
   - [3.4 Medición con Cámara y Alineación Óptica](#34-medición-con-cámara-y-alineación-óptica)
   - [3.5 Adquisición de Trazas Temporales y Calibración de Potencia BS](#35-adquisición-de-trazas-temporales-y-calibración-de-potencia-bs)
4. [Descripción Detallada de Docks, Subprogramas y Botones](#4-descripción-detallada-de-docks-subprogramas-y-botones)
   - [4.1 Dock: Confocal](#41-dock-confocal)
   - [4.2 Dock: Trace](#42-dock-trace)
   - [4.3 Dock: Focus z](#43-dock-focus-z)
   - [4.4 Dock: Shutters / Flipper / Láser 532](#44-dock-shutters--flipper--láser-532)
   - [4.5 Dock: Nanopositioning](#45-dock-nanopositioning)
   - [4.6 Ventana de Mediciones (Printing & Dimers)](#46-ventana-de-mediciones-printing--dimers)
   - [4.7 Ventana de Cámara y Visión por Computadora](#47-ventana-de-cámara-y-visión-por-computadora)
5. [Tabla de Atajos de Teclado (Shortcuts)](#5-tabla-de-atajos-de-teclado-shortcuts)

---

## 1. Introducción y Arquitectura General

**PyPrinting 3.0** es una suite de software científico desarrollada en **Python 3 / PyQt6** diseñada para laboratorios de nanofotónica. El sistema automatiza experimentos de:
* **Microscopía Confocal Láser**: Barridos 2D y 3D con lectura síncrona por disparo de hardware.
* **Impresión Óptica (Fototérmica / Transferencia dirigida por radiación)**: Deposición controlada de nanopartículas individuales (oro, plata, dieléctricos) organizada en matrices predefinidas.
* **Ensamblado Plasmónico de Dímeros**: Impresión precisa de pares de nanopartículas a separaciones nanométricas para generar hot-spots de campo cercano.
* **Estabilización de Foco Z**: Corrección activa de deriva térmica mediante autocorrelación de señal luminosa.
* **Visión por Computadora**: Transmisión de video con calibración espacial ($\mu\text{m/píxel}$) y seguimiento dinámico de nanopartículas en suspensión.

La interfaz principal utiliza un sistema modular de **Docks** dinámicos basados en `pyqtgraph.dockarea`, permitiendo al operador desacoplar, mover o reorganizar todos los paneles de control según las necesidades del experimento.

---

## 2. Modos de Operación: Producción vs. Seguro

El sistema cuenta con dos modos de arranque configurables:

### 🔴 Modo Producción (Hardware Real)
Conecta directamente con la platina piezoeléctrica **Physik Instrumente (PI E-517/E-736)** vía USB, la tarjeta **National Instruments (NI-DAQmx PCIe/USB-6353)** y la cámara física.
```powershell
.\.venv\Scripts\python.exe app.py
```

### 🟢 Modo Seguro (`SAFE_MODE` — Simulación)
Permite ejecutar el 100% de la interfaz gráfica, botones y algoritmos en cualquier computadora sin hardware conectado.
* **Platina PI**: Emulada con actualización coherente de coordenadas.
* **NI-DAQ**: Generación de señales analógicas sintéticas con ruido gaussiano.
* **Cámara**: Transmisión RGB simulada con partículas fluorescentes en movimiento.
```powershell
$env:PYPRINTING_SAFE="1"
.\.venv\Scripts\python.exe app.py
```

---

## 3. Flujos de Trabajo Experimentales (Protocolos Paso a Paso)

### 3.1 Mapeo Confocal 2D/3D y Ajuste de Partículas (PSF)

```
[Seleccionar Láser] ──> [Definir Rango X/Y y Píxeles] ──> [Start Scan] ──> [Cálculo CM / Gauss 2D] ──> [Go to NP1]
```

1. **Seleccionar Línea de Excitación**: En el panel **Confocal**, elija el láser deseado (`532 nm (green)` o `637 nm (red)`).
2. **Configurar Parámetros del Barrido**:
   * Ajuste el tamaño del área a escanear en `Range x (µm)` y `Range y (µm)` (ejemplo: $2 \times 2\ \mu\text{m}$).
   * Ingrese la resolución espacial en `Pixels x` y `Pixels y` (ejemplo: $34 \times 34$ píxeles).
3. **Seleccionar Modo de Escaneo**:
   * `Ramp`: Barrido continuo síncrono de alta velocidad por disparo de hardware.
   * `Step by step`: Posicionamiento paso a paso mediante matriz en espiral.
4. **Ejecutar el Barrido**: Haga clic en **`Start Scan`**. La imagen fotónica se irá construyendo en tiempo real en la pantalla central (`Viewbox`).
5. **Localizar el Centro de la Nanopartícula**:
   * En `method of center`, seleccione `center of gauss` o `center of mass`.
   * Presione **`Go to NP1`**. La platina piezoeléctrica moverá el haz láser exactamente a las coordenadas sub-nanométricas del pico ajustado.

---

### 3.2 Impresión Automatizada de Redes/Grillas de Nanopartículas

```
[Establecer Coordenada Ref.] ──> [Crear Grilla] ──> [Configurar Umbral e Intensidad] ──> [Imprimir] ──> [Ciclo Automatizado]
```

1. **Definir Posición de Origen (Referencia)**:
   * Mueva la platina al área limpia del sustrato donde comenzará la grilla.
   * Abra la ventana **Measurements** (`Measurements` $\rightarrow$ `Printing`).
   * En el Dock *Reference pos*, presione **`Set reference`**.
2. **Crear o Cargar la Grilla**:
   * **Opción A (Crear)**: En el Dock *Grid*, especifique `NPs/col` (ej. 5), `Columns` (ej. 5), `Dist NP (µm)` (ej. 5.0) y `Dist col (µm)` (ej. 5.0). Haga clic en **`Create Grid`**.
   * **Opción B (Cargar)**: Presione **`Load Grid`** o use la barra de menú `Tools` $\rightarrow$ `Load Grid` para importar una matriz personalizada desde un archivo `.txt`.
3. **Configurar el Parámetro de Impresión**:
   * En el Dock *Printing control*, defina el salto de intensidad esperado al depositarse la partícula en `Umbral` (ejemplo: `1.2` para un incremento del 20%).
   * Ajuste el tiempo máximo de exposición por punto en `T max (s)` (ejemplo: `20` segundos).
   * Active la casilla `Scan check` si desea un mapa confocal de confirmación tras cada evento de impresión.
4. **Iniciar la Secuencia Automática**:
   * Presione **`Imprimir`** y luego **`Play`**.
   * El sistema ejecutará automáticamente para cada nodo de la matriz:
     1. Movimiento a la celda objetivo.
     2. Ciclo de **Autofoco Z** para compensar deriva térmica.
     3. Apertura del obturador láser y monitoreo de la traza de fotodiodo.
     4. Cierre automático del obturador al detectar el salto de intensidad por encima del umbral.
     5. Registro de tiempo de impresión e índice de éxito.

---

### 3.3 Fabricación Guiada de Nanodímeros Plasmónicos

```
[Mapear Partícula 1 (Pre-Scan)] ──> [Ajustar Centro Gaussiano] ──> [Aplicar Off-Set (dx, dy)] ──> [Imprimir Partícula 2] ──> [Post-Scan Caracterización]
```

1. Abra la ventana de mediciones en modo Dímeros (`Measurements` $\rightarrow$ `Dimers`).
2. Defina el desplazamiento requerido entre la primera y la segunda partícula en `dx (µm)` y `dy (µm)` (ejemplo: $dx = 0.08\ \mu\text{m} = 80\ \text{nm}$).
3. Active `Scan check` (Pre-scan) y `Post-scan check`.
4. Inicie el protocolo pulsando **`Imprimir`** $\rightarrow$ **`Play`**.
5. **Flujo Interno Automatizado**:
   * **Center-Scan**: El sistema realiza un barrido de la primera partícula y ajusta su centro exacto $(x_1, y_1)$.
   * **Off-set Nanométrico**: Mueve la platina a $(x_1 + dx, y_1 + dy)$.
   * **Pre-Scan**: Mapea la zona previa para guardar el estado óptico inicial.
   * **Impresión**: Activa el láser hasta detectar la unión de la segunda nanopartícula.
   * **Post-Scan**: Mapea la estructura final revelando el acoplamiento plasmónico del nanodímero.

---

### 3.4 Medición con Cámara y Alineación Óptica

1. Abra la ventana flotante de cámara desde la barra de menú: `Tools` $\rightarrow$ `Cámara`.
2. **Visualización e Integración espacial**:
   * Active la transmisión haciendo clic en **`Iniciar Cámara`**.
   * Presione **`Set Ref. Platina`** para vincular las coordenadas en píxeles de la cámara con las coordenadas nanométricas de la platina PI.
3. **Control de Excitación de 532 nm**:
   * Abra `Tools` $\rightarrow$ `Láser 532`.
   * Ajuste el voltaje del láser continuo mediante el slider o la casilla numérica entre **1.0 V** (mínimo/apagado) y **5.0 V** (máxima potencia).
4. **Seguimiento de Partículas (Tracking)**:
   * Ingrese el tamaño estimado de la partícula en píxeles (`Diámetro px`).
   * Haga clic en **`Detectar Partículas`** para ejecutar el algoritmo `trackpy`, el cual dibujará círculos de localización sobre las nanopartículas en suspensión.

---

### 3.5 Adquisición de Trazas Temporales y Calibración de Potencia BS

1. **Lectura de Traza en Tiempo Real**:
   * En el Dock **Trace**, seleccione el láser de excitación.
   * Presione **`► Play`** (o tecla **`F1`**). La gráfica mostrará la intensidad del fotodiodo de recolección y del fotodiodo divisor de haz (`Trace on BS`) frente al tiempo.
   * Presione **`■ Stop`** (o tecla **`F2`**). La traza se guardará automáticamente en la carpeta del día en formato `.txt`.
2. **Calibración de Potencia en el Plano Focal Trasero (BFP)**:
   * Haga clic en el botón **`View Power BS`**.
   * Conecte un medidor de potencia comercial en el objetivo y registre la potencia para dos niveles (alto y bajo).
   * Ingrese los mW medidos en `High (mW)` y `Low (mW)` y presione **`Set High`** y **`Set Low`**.
   * Haga clic en **`Set Calibration`**. El sistema calculará la pendiente (`Slope`) e intersección (`Intercept`) para mostrar en tiempo real la potencia óptica exacta en mW durante los experimentos.

---

## 4. Descripción Detallada de Docks, Subprogramas y Botones

### 4.1 Dock: Confocal (`ConfocalFrontend`)

| Elemento | Tipo | Función / Descripción |
|---|---|---|
| **Láser Combo** | `QComboBox` | Selecciona la línea de excitación láser (`532 nm (green)`, `637 nm (red)`). |
| **Scan Mode Combo** | `QComboBox` | Selecciona entre barrido continuo `Ramp` o barrido helicoidal `Step by step`. |
| **PSF Mode Combo** | `QComboBox` | Selecciona el plano de proyección del escaneo (`x/y`, `x/z`, `y/x`, `y/z`). |
| **Range x (µm)** | `QLineEdit` | Tamaño del campo de visión en el eje horizontal ($\mu\text{m}$). |
| **Range y (µm)** | `QLineEdit` | Tamaño del campo de visión en el eje vertical ($\mu\text{m}$). |
| **Pixels x / y** | `QLineEdit` | Resolución de la imagen (número de puntos por fila/columna). Recomendado: múltiplos de 16. |
| **`Start Scan`** | `QPushButton` | Inicia el barrido confocal en el plano y modo seleccionados. |
| **`Stop`** | `QPushButton` | Interrumpe inmediatamente el escaneo en curso y cierra el obturador. |
| **`Save Frame`** | `QPushButton` | Guarda las matrices de la imagen actual (`.tiff` y `.txt`) en el directorio de trabajo. |
| **`Go to NP1`** | `QPushButton` | Posiciona la platina en las coordenadas calculadas para la Nanopartícula 1. |
| **`Go to NP2`** | `QPushButton` | Posiciona la platina en las coordenadas calculadas para la Nanopartícula 2 (si aplica). |
| **Auto CM** | `QCheckBox` | Si está activo, tras un escaneo el piezo se mueve automáticamente al centro de masa calculado. |
| **Scan Image Combo** | `QComboBox` | Define el contraste de la imagen (`NPs maximum`, `NPs minimum`, `choose`, etc.). |
| **Method Center Combo**| `QComboBox` | Algoritmo de ajuste de centro (`center of mass`, `center of gauss`, `two NP: center of gauss`). |
| **`DRIFT measurement`**| `QPushButton` | Inicia la medición periódica de deriva espacial ajustando la posición Gaussiana a intervalos configurables. |

---

### 4.2 Dock: Trace (`TraceFrontend`)

| Elemento | Tipo | Función / Descripción |
|---|---|---|
| **`► Play / ■ Stop`** | `QPushButton` | Inicia/Detiene la captura de intensidad luminosa en tiempo real (Atajos **F1** / **F2**). |
| **Steps before umbral**| `QLineEdit` | Número de puntos promediados antes del punto actual para calcular la línea base ($I_{old}$). |
| **Steps after umbral** | `QLineEdit` | Número de puntos promediados tras el punto actual para evaluar la condición de salto ($I_{new}$). |
| **PointLabel** | `QLabel` | Muestra los valores numéricos actuales de intensidad en Volts ($I_{old} \mid I_{new}$). |
| **`Save trace`** | `QPushButton` | Guarda manualmente la traza temporal adquirida en un archivo `.txt`. |
| **`View Power BS`** | `QPushButton` | Abre la ventana secundaria de calibración de potencia en el fotodiodo divisor de haz. |

---

### 4.3 Dock: Focus z (`FocusFrontend`)

| Elemento | Tipo | Función / Descripción |
|---|---|---|
| **`Go to maximum (F8)`**| `QPushButton` | Realiza un barrido rápido en Z y desplaza la platina al pico de máxima intensidad del fotodiodo. |
| **`Lock Focus (F9)`** | `QPushButton` | Registra y congela el perfil de intensidad Z actual como referencia de enfoque. |
| **`Autocorrelation ×2 (F10)`**| `QPushButton` | Correlaciona la señal Z actual con el perfil locked y ajusta el foco a la coincidencia óptima. |

---

### 4.4 Dock: Shutters / Flipper / Láser 532 (`ShuttersFrontend`)

| Elemento | Tipo | Función / Descripción |
|---|---|---|
| **Shutter 532 nm** | `QCheckBox` | Abre o cierra el obturador digital del láser verde de 532 nm (Canal DO 12, PD ai0). |
| **Shutter 637 nm** | `QCheckBox` | Abre o cierra el obturador digital del láser rojo de 637 nm (Canal DO 11, PD ai1). |
| **Shutter 592 nm** | `QCheckBox` | Abre o cierra el obturador digital del láser amarillo de 592 nm (Canal DO 10, PD ai3). |
| **Low power** | `QCheckBox` | Activa/Desactiva el atenuador óptico de baja potencia. |
| **Mirror up** | `QCheckBox` | Levanta o baja el espejo escamotearle del filtro Notch de 532 nm (*Flipper*). |

---

### 4.5 Dock: Nanopositioning (`NanoFrontend`)

| Elemento | Tipo | Función / Descripción |
|---|---|---|
| **`Read position`** | `QPushButton` | Lee y actualiza la posición actual de los ejes X, Y, Z de la platina PI. |
| **Flechas $x, y, z$** | `QPushButton` | Movimientos incrementales relativos en dirección positiva o negativa ($\times 1$ y $\times 10$). |
| **step x/y [µm]** | `QLineEdit` | Tamaño del paso incremental para movimientos en el plano XY ($\mu\text{m}$). |
| **step z [µm]** | `QLineEdit` | Tamaño del paso incremental para el eje Z ($\mu\text{m}$). |
| **`Set reference`** | `QPushButton` | Guarda las coordenadas actuales como origen de referencia para el panel *Go to*. |
| **`Go to`** | `QPushButton` | Mueve la platina de forma absoluta a las coordenadas $(X, Y, Z)$ ingresadas en las casillas. |

---

### 4.6 Ventana de Mediciones (`MeasFrontend` — Printing & Dimers)

| Dock / Elemento | Tipo | Función / Descripción |
|---|---|---|
| **Reference pos** | Panel | Muestra las coordenadas de origen $(X_{ref}, Y_{ref}, Z_{ref})$. Incluye `Set reference` y `Go reference`. |
| **Grid** | Panel | Permite generar grillas paramétricas definiendo filas, columnas y espaciados nanométricos. |
| **Printing/Dimers control**| Panel | Botones globales `Imprimir`, `Play`, `Pause`, `Next`. Parámetros `Umbral`, `Umbral down` y `T max`. |
| **Focus shift** | Panel | Frecuencia de autofoco (`Autofocus every N`), desplazamientos de foco (`Shift x/y`) y offsets de dímero (`dx/dy`). |
| **Extra info** | Panel | Registro de datos del sustrato, tipo de nanopartícula, tasa de éxito (%) y botón `Save info`. |

---

### 4.7 Ventana de Cámara (`CameraWindow`) y Analizador de Imágenes (`image_analyzer.py`)

#### Módulo de Cámara (`camera.py`)
- **Panel Izquierdo (Detección & ROI)**: Botón `ROI detect`, `Detectar` (Trackpy), Tabla interactiva de partículas y `Limpiar Partículas`.
- **Panel Derecho (Mediciones)**: Botón `Medir`, `Guardar Medida`, Tabla de mediciones guardadas, `Exportar (.txt)` y `Limpiar Lista`.
- **Ajuste Automático (Snap con Shift)**: Al medir o fijar referencia manteniendo `Shift`, el cursor se engancha automáticamente a la partícula detectada o referencia más cercana.
- **Reglas Tri-estado**: Ocultas $\rightarrow$ 1er Par ($H_1, V_1$) $\rightarrow$ 2do Par ($H_1, V_1$ y $H_2, V_2$) $\rightarrow$ Ocultar todo.
- **Zoom In-Window ($1\times, 2\times, 4\times$)**: Botones `Zoom+`, `Zoom-` y `Home` con desplazamiento (*pan*) por arrastre. `Home` centra la imagen en la posición de referencia.
- **Limpiar Todo (Global Clear)**: Borra partículas, referencia, reglas y mediciones tras confirmación previa por diálogo.
- **Rutina ROI $\rightarrow$ Confocal**:
  - Mapeo de orientación: **$Y+$ hacia la derecha, $X+$ hacia abajo**.
  - Validación física en el rango $0.0 – 100.0\ \mu\text{m}$.
  - Solicitud de resolución en **nm/píxel**, cálculo de matriz de píxeles e inicio automático del barrido confocal.

#### Analizador de Imágenes Estáticas (`image_analyzer.py`)
- Módulo operable como **Dock** o aplicación independiente (`python image_analyzer.py`).
- Botón **`📁 Abrir Foto`**: Carga imágenes estáticas (`.png`, `.jpg`, `.tiff`).
- Botón **`📷 Exportar Foto`**: Renderiza la imagen junto con todas las capas de overlay (mediciones, partículas, reglas, referencia) y la guarda en disco.

---

## 5. Tabla de Atajos de Teclado (Shortcuts)

| Tecla de Acceso Directo | Función Asociada | Módulo / Dock |
|---|---|---|
| **`Ctrl + A`** | Seleccionar directorio de trabajo | Menú principal (`Files`) |
| **`Ctrl + S`** | Crear directorio diario automático (`YYYY-MM-DD`) | Menú principal (`Files`) |
| **`Ctrl + D`** | Abrir la carpeta del directorio actual en el explorador | Menú principal (`Files`) |
| **`Shift + Click/Arrastrar`** | Activar Snap magnético a partículas/referencia en mediciones | Cámara / Analizador de Imágenes |
| **`F1`** | Iniciar captura de Traza temporal (Play) | Dock: Trace |
| **`F2`** | Detener captura de Traza temporal y guardar (Stop) | Dock: Trace |
| **`F8`** | Ejecutar Autofoco Z (Go to maximum) | Dock: Focus z |
| **`F9`** | Congelar perfil de intensidad Z (Lock Focus) | Dock: Focus z |
| **`F10`** | Ejecutar corrección por autocorrelación Z ($\times 2$) | Dock: Focus z |

---

*Manual de Usuario de PyPrinting 3.0 — UNSAM Nanofotónica.*
