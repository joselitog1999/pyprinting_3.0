# MOD-06: PySpectrum 3.0 — Espectroscopía y Mapeo Hiperespectral (pyspectrum.py) 🌈

**PyPrinting 3.0 — Suite de Nanofotónica y Control Instrumental**  
**Laboratorio de Nanofotónica — Instituto de Nanosistemas (INS-UNSAM / CONICET)**  
**Manual de Usuario Canónico** | **Código:** `MOD-06` | **Nivel de Usuario:** Intermedio / Operador / Experto  
**Archivo Fuente**: [`pyspectrum.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/pyspectrum.py) | Paquete: [`pyspectrum/`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/pyspectrum/)  
**Lanzador Rápido**: Botón 2 en [`main.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/main.py) o `python pyspectrum.py`

---

## 🔗 Matriz de Referencias Cruzadas

* **Reportes de Sistema Conexos:**
  * `[[SYS-301_Sistema_Espectrometro_Shamrock500i_iXon3]]`
  * `[[SYS-302_Calibracion_Espectral_y_Sincronizacion_Flippers]]`
  * `[[SYS-305_Arquitectura_Optomecanica_Microscopio_Derecho_y_Ruteo_Espectral]]`
  * `[[SYS-306_Arquitectura_Motor_Raman_y_Quimiometria_Multiespectral]]`
  * `[[SYS-402_Auditoria_Comparativa_Andor_Solis_vs_PySpectrum]]`
  * `[[SYS-104_Matriz_Intercambio_Archivos_y_Formatos_IO]]`
* **Fundamentos Científicos Asociados:**
  * `[[CAT-103_Control_Lazo_Cerrado_Fototermico_y_Sintesis_Dimeros]]`
  * `[[CAT-108_Teoria_Optica_Telescopio_Rele_4f_y_Canales_Confocales]]`
  * `[[CAT-109_Electrodinamica_Fuerzas_Opticas_y_Termoplasmonica_Printing]]`
  * `[[CAT-401_Estandar_Serializacion_Jerarquica_Contenedor_HDF5]]`
* **Manuales de Usuario Conexos:**
  * `[[MOD-01_Microscopio_Derecho_App]]`
  * `[[MOD-02_Measurements_Printing_y_Dimeros]]`
  * `[[MOD-11_Raman_Analyzer_Suite_Quimiometria]]`
  * `[[MOD-12_Analizador_SIF_Andor_Solis]]`
  * `[[MOD-14_Protocolos_Laboratorio_SOP]]`
* **Decisiones Arquitectónicas (Escaneo Lineal Espectral):** `[[DECISION_LOG#DEC-006]]`, `[[DECISION_LOG#DEC-007]]`, `[[DECISION_LOG#DEC-008]]`

---

## 1. 🏷️ Resumen y Rol en el Sistema

El módulo **PySpectrum 3.0** es la estación central de **espectroscopía óptica, cosido espectral continuo (*Step and Glue*) y caracterización hiperespectral 2D/3D** de la suite PyPrinting 3.0.

> **Fase 1 del Rework Arquitectónico (`[[DECISION_LOG#DEC-015]]`)**: desde esta fase, la ventana principal reemplaza el antiguo `DockArea` flotante por un **shell de 6 pestañas de flujo de trabajo** (`QTabWidget`) con un **Panel Izquierdo Permanente y Dinámico** (`LeftHardwarePanel`, ~1/3 del ancho) que centraliza el control de la cámara Andor EMCCD y el espectrógrafo Shamrock 500i. Ver §12 para el detalle completo.

Integra de forma multihilo y desacoplada (`PyQt6`):
- **Control de Espectrógrafo Andor Shamrock (SR-303i / SR-500i)**: Selección de red de difracción (150 l/mm, 1200 l/mm, espejo), longitud de onda central $\lambda_{center}$, ranuras micrométricas motorizadas (*slits*) y conmutación de puertos (*flippers*).
- **Cámara Andor iXon3 EMCCD**: Control de refrigeración criogénica Peltier multi-etapa ($-65^\circ\text{C}$ a $-80^\circ\text{C}$), doble canal de amplificación (EMCCD alta sensibilidad y Convencional bajo ruido), ganancia EM ($0$ a $1000\times$), tiempo de exposición, visualización 2D en vivo ($1002 \times 1002$ px, píxel $13.0\,\mu\text{m}$), binning vertical hardware FVB y Single Track.
- **Algoritmo *Step & Glue* de Banda Ancha**: Adquisición concatenada de múltiples rangos espectrales (ej. $450 - 950\ \text{nm}$) con solapamiento suave ponderado y normalización por lámpara halógena de calibración.
- **Mapeo Confocal Hiperespectral $(X, Y, \lambda)$**: Coordinación del escaneo piezoeléctrico PI cerrado con la captura espectral por píxel para generar hipercubos de datos tridimensionales.
- **Rutinas Especializadas**:
  - *Fotoluminiscencia y Anti-Stokes*: Registro temporal $I(\lambda, t)$ bajo excitación láser.
  - *Cinética de Crecimiento de Nanopartículas*: Detección y seguimiento continuo del máximo plasmónico $\lambda_{max}(t)$ mediante ajuste polinomial.
  - *Caracterización de Dímeros*: Análisis de acoplamiento plasmónico y anisotropía por polarización (paralela vs perpendicular).

---

## 2. 🖼️ Maqueta de la Interfaz Visual (ASCII Layout, post-Fase 1)

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│  PySpectrum 3.0 — Espectroscopía & Mapeo Hiperespectral  [UNSAM Nanofotónica]           🚨 E-STOP  🔄 Rearmar    │
├──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│  📁 Archivo    🔧 Herramientas    🧪 Rutinas                                                                      │
├────────────────────────────────┬───────────────────────────────────────────────────────────────────────────────┤
│  PANEL IZQUIERDO PERMANENTE     │ [🔭1.Exploración][🔬2.Raman][🧩3.Step&Glue][🌱4.Cinética][🎯5.Calib][🧬6.Confocal]│
│  (~1/3, siempre visible)        ├───────────────────────────────────────────────────────────────────────────────┤
│  📷 Cámara Andor EMCCD (iXon3)  │                                                                                │
│   🟢 Temp: -65.0 °C  Set T:[-65]│         Contenido de la pestaña activa                                        │
│   ❄️ Enfriador: ON              │         (visor 2D/1D, controles de rutina, gráficos, tablas)                  │
│   Amplificador: [EMCCD ▼]       │                                                                                │
│   EM Gain: [ 0 ]                │                                                                                │
│   Pre-Amp Gain: [ 1.0x ▼ ]      │                                                                                │
│   Velocidad Lectura: [5.0MHz▼]  │                                                                                │
│   Exposición (s): [ 0.05 ]      │                                                                                │
│   Obturador Cámara: [ Auto ▼ ]  │                                                                                │
│  🌈 Espectrógrafo Shamrock 500i │                                                                                │
│   Red: [ 150 líneas/mm ▼ ]      │                                                                                │
│   Ranura Entrada: [ 50.0 ] µm   │                                                                                │
│   Puerto Entrada/Salida: [..▼]  │                                                                                │
│   λ actual: 532.00 nm           │                                                                                │
│   λ Central: [ 532.00 ] [➡️Ir]  │                                                                                │
│   [ 🪞 Ir a Orden Cero (0 nm) ] │                                                                                │
├────────────────────────────────┴───────────────────────────────────────────────────────────────────────────────┤
│  🟢 PySpectrum 3.0 Listo | Carpeta de trabajo: C:/Users/josel/Documents/Data_PySpectrum                          │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

Al presionar **`🪞 Ir a Orden Cero (0 nm)`** se abre el diálogo modal `ZeroOrderSafetyDialog` (§12.3), que **nunca** mueve el espectrógrafo directamente. En la pestaña **Step & Glue**, el campo λ Central y el botón `➡️ Ir a λ` del panel izquierdo se inhabilitan automáticamente (la receta de cosido comanda la red).

---

## 3. 🎛️ Catálogo de Botones y Controles

### Menús Superiores
| Menú | Acción | Función Técnica |
|---|---|---|
| **📁 Archivo** | Seleccionar Directorio | Define la carpeta base de almacenamiento mediante `QFileDialog`. |
| **📁 Archivo** | Crear Carpeta del Día | Genera automáticamente una subcarpeta `AAAA-MM-DD` para la sesión activa. |
| **📁 Archivo** | Abrir Carpeta de Datos | Abre el directorio activo en el Explorador de Windows mediante `os.startfile`. |
| **🔧 Herramientas** | Platina Nanoposicionamiento | Abre el diálogo flotante del controlador de la platina PI E-517. |
| **🔧 Herramientas** | Obturadores & Flippers | Abre el diálogo flotante de control de obturadores láser (532, 637, 592, 808 nm). |
| **🔧 Herramientas** | Tablero de Conexiones | Abre el Tablero de Seguridad de Hardware ([`modules/hardware_dashboard.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/modules/hardware_dashboard.py)). |
| **🔧 Herramientas** | Control Legado del Espectrógrafo | Abre `spectrum_control.py::Frontend` en un diálogo de compatibilidad (Fase 1): mismos controles ya disponibles en el Panel Izquierdo permanente. |
| **🧪 Rutinas** | Luminiscencia & Anti-Stokes | Abre la ventana de seguimiento de fotoluminiscencia temporal $I(\lambda, t)$. |
| **🧪 Rutinas** | Dímeros Plasmónicos | Abre la ventana de espectroscopía de dímeros y anisotropía de polarización. |
| **🧪 Rutinas** | Escaneo Lineal Espectral | Abre la rutina de escaneo lineal con la platina PI E-517 (§10). |

> Desde la Fase 1, **Cinética de Crecimiento** dejó de ser un ítem de este menú: ahora vive embebida como Pestaña 4 (`🌱 4. Cinética`) del shell principal. `GrowthKineticsWidget` (el diálogo standalone previo) sigue existiendo por retrocompatibilidad, envolviendo internamente el mismo `GrowthKineticsPanel` que se embebe en la pestaña.

---

## 4. 📂 Archivos de Entrada y Salida

### Archivos Requeridos (Entrada)
- **DLLs del Sistema** (en [`pyspectrum/drivers/libs/`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/pyspectrum/drivers/libs/)):
  - `ShamrockCIF.dll` y `atshamrock.dll` (Andor Shamrock SDK).
  - `atmcd64d.dll` (Andor SDK 2 para cámaras CCD).
- **Espectro de Calibración de Lámpara Halógena**:
  - `pyspectrum/calibration/data/lamparaIR_450-950_overlap0.2/lamparaIR_grade_2.txt` (curva de referencia instrumental).

### Archivos Generados (Salida)
| Formato | Contenido | Ejemplo de Nombre |
|---|---|---|
| `.txt` (ASCII 2 col) | Longitud de onda ($\text{nm}$) e Intensidad (cuentas/norm) | `Spectrum_532nm_1s_2026-08-28.txt` |
| `.txt` (Multi col) | Espectros concatenados Step & Glue | `StepAndGlue_450-950nm_norm.txt` |
| `.npy` (NumPy 3D) | Cubo hiperespectral de datos $(N_x, N_y, N_{\lambda})$ | `Hyperspectral_10x10um_cube.npy` |
| `.png` / `.tiff` | Gráficos espectrales exportados y mapas 2D en falso color | `Growth_Kinetics_Lmax_trace.png` |

---

## 5. 🛡️ Resiliencia y Modo Simulación

- Si los instrumentos físicos (Shamrock o cámara Andor) no están conectados o `SAFE_MODE = True`, el sistema activa de forma transparente **`_MockShamrock`** y **`_MockAndorCCD`**.
- La cámara virtual genera un cuadro sintético realista con ruido Gaussiano, perfil de ranura y resonancia plasmónica centrada, permitiendo ensayar algoritmos de cosido, ajustes y escaneos hiperespectrales en cualquier computadora.

---

## 6. 🔬 Espectroscopía Raman Estática & Termometría Fototérmica (`static_raman.py`)

El módulo de **Raman Estático** permite la captura instantánea (Single-Shot y Live Raman continuo) sin necesidad de traslación mecánica de la red durante la medición, maximizando la relación señal/ruido y la velocidad temporal.

### 6.1. Especificaciones de Redes y Dispersión Física (Shamrock 500i, $f = 500\ \text{mm}$)
- **Red 1: 150 líneas/mm (Blaze 800 nm)** *(Por defecto - Exploratoria)*:
  - Dispersión recíproca lineal: $\approx 13.33\ \text{nm/mm} \implies \mathbf{0.175\ \text{nm/px}}$ (detector Andor iXon3 de $1002\ \text{px}$, paso $13\ \mu\text{m}$).
  - Ventana espectral abarcada en una única toma: $\mathbf{\Delta\lambda \approx 175\ \text{nm}}$.
  - A excitación de $532\ \text{nm}$: cubre simultáneamente desde $-3700\ \text{cm}^{-1}$ (Anti-Stokes) hasta $+2650\ \text{cm}^{-1}$ (Stokes).
- **Red 2: 1200 líneas/mm (Blaze 500 nm)** *(Alta Resolución)*:
  - Dispersión recíproca lineal: $\approx 1.67\ \text{nm/mm} \implies \mathbf{0.022\ \text{nm/px}}$.
  - Ventana espectral abarcada en una toma: $\mathbf{\Delta\lambda \approx 22\ \text{nm}}$.
  - A excitación de $532\ \text{nm}$ en modo simétrico: cubre $-400\ \text{cm}^{-1}$ a $+380\ \text{cm}^{-1}$ con resolución ultra-fina para fonones acústicos y termometría Anti-Stokes de baja energía.

### 6.2. Modos de Ventana Espectral Preconfigurados
1. **Huella Dactilar Raman (Stokes)**: Centra automáticamente el espectrógrafo en $\approx 565\ \text{nm}$ (a $532\ \text{nm}$) para cubrir óptimamente el rango vibracional orgánico e inorgánico ($+500$ a $+2500\ \text{cm}^{-1}$).
2. **Stokes + Anti-Stokes Simétrico (Termometría)**: Centra exactamente en la longitud de onda de la línea láser ($\lambda_{laser}$), permitiendo registrar en simultáneo las ramas Stokes y Anti-Stokes con idéntica transmitancia instrumental.
3. **Manual**: El operador define arbitrariamente el centro espectral en nanómetros o $\text{cm}^{-1}$.

### 6.3. Procesamiento en Vivo (`core/raman_engine.py`)
- **Despiking de Rayos Cósmicos**: Algoritmo por gradiente espacial y filtrado de mediana deslizante sobre ventana de 5 píxeles.
- **Sustracción de Línea Base**:
  - *AsLS* (Asymmetric Least Squares): $\lambda = 10^5$, $p = 0.001$.
  - *AirPLS* (Adaptive Iteratively Reweighted Penalized Least Squares): $\lambda = 10^5$.
  - *ModPoly* (Polynomial Modified): Orden 4.
- **Suavizado Savitzky-Golay**: Ajuste polinomial local de orden 3 con ventana seleccionable (5 a 51 puntos).
- **Telemetría y Termometría Anti-Stokes / Stokes**: Cursores interactivos A y B calculan en tiempo real la relación de intensidades y la temperatura local absoluta según la distribución de Boltzmann:
  $$T = \frac{h c |\Delta\tilde{\nu}|}{k_B \ln\left[ \frac{I_S}{I_{AS}} \left(\frac{\nu_0 - \Delta\tilde{\nu}}{\nu_0 + \Delta\tilde{\nu}}\right)^4 \right]}$$

---

## 7. ❄️ Control Térmico y Ganancia EMCCD de la Cámara Andor iXon3

- **Refrigeración Termoeléctrica Automática**: Al ingresar un setpoint térmico (típico: $-65\ ^\circ\text{C}$ o $-80\ ^\circ\text{C}$), el controlador invoca automáticamente `CoolerON()` en la biblioteca `atmcd64d.dll`, eliminando el riesgo de que el refrigerador Peltier permanezca inactivo.
- **Selector de Amplificador de Salida**:
  - *Modo Convencional (Bajo Ruido CCD)*: Desactiva el registro de ganancia EM para mediciones con alta señal donde prima el mínimo ruido de lectura.
  - *Modo EMCCD (Multiplicador de Electrones)*: Habilita el control interactivo de ganancia.
- **Control Dual de EM Gain**:
  - Slider horizontal acoplado a casilla numérica (`QSpinBox`) al lado para ingreso numérico directo.
  - Código de color de seguridad:
    - 🟢 **Verde** ($0 - 100\times$): Régimen seguro de rutina.
    - 🟡 **Amarillo** ($101 - 300\times$): Alta sensibilidad, precaución con saturación.
    - 🔴 **Rojo** ($> 300\times$): Alerta de envejecimiento acelerado del sensor por fotocorriente excesiva.

---

## 8. 🎯 Pestaña Modular: Calibraciones del Sistema (`calibration_dock.py`)

Integrada en el `DockArea` principal (junto a Step & Glue y Raman) y accesible desde el menú **`🔧 Herramientas → 🎯 Calibraciones del Sistema`**, centraliza la calibración físico-óptica del espectrómetro Andor Shamrock 500i y detector CCD:

### 8.1 Ranura de Entrada (Slit) y Centroide Óptico X
- **Botón `🎯 Mover a Orden Cero (0.0 nm)`**: Desplaza el goniómetro a dispersión nula para visualización especular de la ranura.
- **Ancho Micrométrico de Ranura**: Ajuste dinámico de 10 a 2500 µm con botones rápidos de 10, 50, 100 y 500 µm.
- **Pixel Central X (`SLIT_CENTER_PIXEL_X`)**: Ajuste del pixel central donde focaliza la rendija (predeterminado: 501.0 px).
- **Auto-Calibración de Centroide X**: Ajuste gaussiano no lineal de la proyección horizontal en orden cero:
  $$I(x) = A \exp\left(-\frac{(x - x_0)^2}{2\sigma^2}\right) + y_0$$
  calcula con precisión subpíxel el centroide $x_0$ y el ancho a media altura (FWHM).

### 8.2 Offsets de Rejilla & Detector en Hardware (SDK Oficial)
Enlace nativo Ctypes con la biblioteca `ShamrockCIF.dll`:
- **`ShamrockGetGratingOffset` / `ShamrockSetGratingOffset`**: Lectura y escritura de pasos de motor de compensación para cada red independiente (150 l/mm, 1200 l/mm, Espejo).
- **`ShamrockGetDetectorOffset` / `ShamrockSetDetectorOffset`**: Lectura y escritura del offset de montaje del plano focal del detector CCD.
- **`ShamrockGetSlitZeroPosition` / `ShamrockSetSlitZeroPosition`**: Calibración del punto cero de apertura mecánica de ranura.

### 8.3 Calibración Cúbica de Longitud de Onda y Respuesta Halógena
- **Coeficientes EEPROM ($a, b, c, d$)**: Inspección directa de la relación $\lambda(p) = a + bp + cp^2 + dp^3$.
- **Lámpara Halógena Trazable**: Carga de perfil patrón para corrección cromática instrumental.

### 8.4 Mejoras en Step & Glue (`step_and_glue.py`)
- **Botón `⏹ Detener Escaneo`**: Interrupción cooperativa limpia entre centros de banda sin dejar la torreta en estado indeterminado.
- **Botón `💾 Guardar Espectro...`**: Exportación directa del espectro cosido a formato tabular ASCII (`.txt`, `.csv`) o contenedor NumPy comprimido (`.npz`).

---

## 9. ⚠️ Límites de Validez y Modos de Falla

| Condición de Borde (Fallo Espectroscópico / Hardware) | Firma Experimental (Espectro 1D / Imagen CCD) | Acción Correctiva Física (Procedimiento en Laboratorio) |
| :--- | :--- | :--- |
| **Saturación del Convertidor ADC de la Cámara CCD Andor** ($I \ge 65535\ \text{ADU}$). | Picos truncados planos en $65535\ \text{cuentas}$ y desbordamiento de carga (*blooming*) horizontal en el sensor CCD. | Reducir el tiempo de exposición (ej. de $1.0\ \text{s}$ a $0.1\ \text{s}$) o cerrar el ancho de las ranuras micrométricas de entrada del espectrógrafo a $\le 50\ \mu\text{m}$. |
| **Descalibración por Holgura Mecánica en Torreta de Redes (*Grating Backlash*)**. | El pico elástico del láser de 532 nm aparece desplazado en la escala de longitudes de onda calculada ($\Delta \lambda > 2\ \text{nm}$). | Usar la pestaña **🎯 Calibraciones del Sistema** para ajustar el offset de rejilla con `ShamrockSetGratingOffset` o aplicar compensación por pico elástico a 532.0 nm. |
| **Condensación en la Ventana Óptica por Falla de Refrigeración Peltier**. | Pérdida abrupta de intensidad luminosa y aumento drástico del nivel de ruido térmico basal de la CCD. | Comprobar el flujo de agua en el recirculador térmico / ventilador de la CCD y asegurar que el vacío interno esté estable con temperatura nominal de $-10\ ^\circ\text{C}$ a $-60\ ^\circ\text{C}$. |
| **Discontinuidades en el Cosido Espectral (*Step & Glue*)**. | Saltos de intensidad escalonados en las zonas de unión/solapamiento entre ventanas espectrales contiguas. | Adquirir un nuevo espectro de calibración con la lámpara halógena de referencia para normalizar la respuesta cromática de la rejilla de difracción y del sensor. |

---

## 10. 📏 Escaneo Lineal Espectral (Transmisión/Extinción)

Rutina de escaneo horizontal 1D con la platina PI E-517 ($X_{\text{start}} \to X_{\text{end}}$, paso $\Delta X$), implementada en `pyspectrum/modules/routines/linescan_spectroscopy.py` y accesible desde `🧪 Rutinas → Escaneo Lineal Espectral (Transmisión/Extinción)`. A diferencia de las demás rutinas de este módulo, corre su motor de adquisición en un `QThread` real (ver `[[DECISION_LOG#DEC-006]]`/`[[DECISION_LOG#DEC-007]]`), ya que un solo paso puede bloquear desde cientos de ms (modo Ventana Única) hasta varios minutos (modo Espectro Completo / Step & Glue).

**Doble modalidad de lectura CCD** por posición: bineo de hardware acotado al ROI vertical de la mancha confocal (`READ_MODE_SINGLE_TRACK`, evita el FVB puro de 1002 filas que degradaría el SNR al sumar filas oscuras sin luz — detalle cuantitativo en `[[SYS-301_Sistema_Espectrometro_Shamrock500i_iXon3#7.2]]`) y modo pixel-a-pixel 2D (`READ_MODE_IMAGE`) sobre el mismo ROI, para diagnóstico de heterogeneidad espacial, aberración cromática y alineación en la rendija.

**Protocolo**: referencia fija ($I_{ref}$, $I_{ref\_bg}$ con lámpara abierta/cerrada, ambos modos) seguida de un barrido de señal $I_{sig}(x)$ sin ciclar obturadores en cada punto; $T(\lambda,x)$ y $E(\lambda,x)=-\log_{10}T(\lambda,x)$ se calculan con las mismas funciones que el analizador SIF (`core/sif_processor.py`). Persistencia nativa en HDF5 comprimido (`shuffle`+`gzip`-4), esquema detallado en `[[SYS-104_Matriz_Intercambio_Archivos_y_Formatos_IO#5. Contenedor HDF5 del Escaneo Lineal Espectral]]`.

Procedimiento paso a paso completo: `[[MANUAL_USUARIO#4.5 Procedimiento Operativo Estandarizado (SOP del Escaneo Lineal Espectral)]]`.

### 10.1 ⚠️ Límites de Validez y Modos de Falla — Escaneo Lineal Espectral

| Condición Límite / Caso de Borde | Manifestación en la GUI | Mitigación Inmediata del Operador |
| :--- | :--- | :--- |
| Saturación del ADC del iXon3 durante la adquisición de Referencia (lámpara abierta). | Meseta plana en el valor máximo de cuentas en la vista previa/espectro; no dispara el banner de señal débil (que solo vigila el extremo bajo, $<3\sigma$). | Reducir **`Exp. 1D (s)`**/**`Exp. 2D (s)`** y repetir **`📥 Tomar Referencia (Fase A)`**; verificar en **`🔍 Vista Previa del Sensor`** antes de reintentar. |
| $T(\lambda)$ indefinida en los bordes UV/NIR donde la emisión de la lámpara halógena cae a cero. | Picos espurios o ruido amplificado en los extremos del plot 1D y en las columnas límite del heatmap 2D; el motor aplica `noise_threshold` para evitar la división exacta por cero, pero el resultado carece de significado físico. | Acotar λ Inicial/λ Final al rango con emisión útil; subir el Multiplicador σ_dark en **`⚙️ Avanzado`**; recortar los bordes al exportar con **`🎨 Exportar Curva`**. |
| Pérdida de paso piezoeléctrico o intento de posicionar fuera de $0$–$100\ \mu\text{m}$ en la platina PI E-517. | Los spinboxes clampean automáticamente al límite físico; si el asentamiento no confirma on-target dentro del timeout, el escaneo se detiene con diálogo "Error en Escaneo Lineal" (timeout de piezo). | Inspeccionar mecánicamente la platina, presionar **`📍 Tomar Posición Actual`** para releer la posición real y reajustar la recta antes de reintentar **`🚀 Iniciar Escaneo`**. |
| Señal de referencia débil: $(I_{ref}-BG_{ref}) < 3\sigma$ en más del 50% del espectro. | Banner ámbar no modal bajo la cabecera; **`🚀 Iniciar Escaneo`** permanece deshabilitado aunque ya se haya presionado Tomar Referencia. | Confirmar que **`Fuente (Lámpara)`** corresponda al obturador real, reencuadrar el ROI en la vista previa y repetir la Referencia. |
| Timeout de asentamiento de la red de difracción entre centros espectrales (modo "Espectro Completo — Step & Glue"). | El escaneo se detiene, la barra de progreso deja de avanzar y aparece un diálogo de error con la longitud de onda afectada. | Verificar que la torreta de redes no esté obstruida y reintentar; si persiste, reducir el rango λ o el Solapamiento para disminuir la cantidad de saltos de red por punto. |

---

## 12. 🏗️ Fase 1 del Rework Arquitectónico — Shell de Pestañas y Panel Izquierdo Permanente

Ver `[[DECISION_LOG#DEC-015]]` para el registro formal de la decisión. Resumen técnico:

### 12.1 Shell principal (`pyspectrum/window.py`)
El `DockArea` flotante fue reemplazado por un `QSplitter` horizontal: `LeftHardwarePanel` (~1/3) + `QTabWidget` de 6 pestañas (~2/3). Índices fijos exportados como constantes de módulo (`TAB_EXPLORATION=0`, `TAB_STATIC_RAMAN=1`, `TAB_STEP_AND_GLUE=2`, `TAB_GROWTH_KINETICS=3`, `TAB_CALIBRATION=4`, `TAB_CONFOCAL=5`). `tabs_workflow.currentChanged` dispara `LeftHardwarePanel.set_context(idx)`.

| Pestaña | Widget embebido | Origen |
|---|---|---|
| 🔭 1. Exploración | `camera_andor.py::Frontend` (`cam_widget`) | Reusado tal cual; Fase 2 reemplaza su ROI por el ligado a `SpectroscopyContext` |
| 🔬 2. Static Raman | `static_raman.py::StaticRamanWidget` | Sin cambios |
| 🧩 3. Step & Glue | `step_and_glue.py::Frontend` (`sandg_widget`) | Sin cambios |
| 🌱 4. Cinética | `growth_kinetics.py::GrowthKineticsPanel` (nuevo) | Extraído de `GrowthKineticsWidget` (ver §12.2) |
| 🎯 5. Calibraciones | `calibration_dock.py::CalibrationFrontend` | Sin cambios (antes en Dock) |
| 🧬 6. Mapeo Confocal | `hyperspectral_confocal.py::Frontend` | Sin cambios (antes en Dock; sigue en `QThread` propio, `ANOM-HYPERSPEC-01`) |

`spectrum_control.py::Frontend` (`spec_widget`) se mantiene 100% instanciado y wireado (cero regresión) pero relocalizado a un diálogo de compatibilidad vía `🔧 Herramientas` (§3), al ser 100% redundante con el sub-panel Shamrock del panel izquierdo.

### 12.2 `LeftHardwarePanel` (`pyspectrum/ui/left_hardware_panel.py`)
Widget único (no hay un segundo par cámara/espectrógrafo con el que multiplexar), combina UI y despacho directo al driver, con `QTimer` propio de 1 Hz para refrescar temperatura y λ actual — mismo patrón que `camera_andor.py::Backend._read_temperature`. Sub-panel Andor: temperatura/enfriador, amplificador, EM Gain, **Pre-Amp Gain** y **Velocidad de Lectura (HSSpeed)** (ambos poblados dinámicamente desde el driver — `get_number_preamp_gains()`/`get_preamp_gain(i)`, `get_number_hs_speeds()`/`get_hs_speed(i)`), exposición, **modo de obturador interno de cámara** (Auto/Siempre Abierto/Siempre Cerrado). Sub-panel Shamrock: red, ranura, flippers IN/OUT, λ central + `➡️ Ir a λ`, `🪞 Ir a Orden Cero`. `set_context(tab_index)` inhabilita el campo manual de λ y `Ir a λ` únicamente en la pestaña Step & Glue (la receta de cosido comanda la red); Orden Cero permanece siempre disponible como acción manual explícita.

### 12.3 `ZeroOrderSafetyDialog` (`pyspectrum/ui/zero_order_dialog.py`)
Interlock modal disparado desde el botón `🪞 Ir a Orden Cero` del panel izquierdo. Inspecciona `EM Gain` (`get_emccd_gain()`) y obturadores láser realmente abiertos (`core/nidaq.py::get_open_shutter_names()` — **no** `is_watchdog_armed()`, que puede estar desarmado con un shutter físicamente abierto en Modo Alineación) y exige una de 5 acciones explícitas: `🛡️ Cerrar Láser y Apagar EM Gain` (recomendado), `🔴 Solo Cerrar Láser`, `🔻 Solo Apagar EM Gain`, `⚠️ Ignorar y Continuar (Override Experto)` (deja advertencia explícita en consola) o `✖ Cancelar` (no mueve nada). Sólo tras una acción no cancelada se invoca `spectrometer.goto_zero_order()`. No reemplaza ni modifica el safeguard silencioso preexistente de `spectrum_control.py::Backend.goto_zero_order()` (usado sólo por el diálogo legado de compatibilidad).

### 12.4 Transición Segura de Modos de Lectura (`pyspectrum/ui/acquisition_setup_dialog.py`)
`compute_buffer_shape(read_mode, width, height, n_tracks)` y `transition_read_mode(camera, new_mode, **kwargs)` son funciones puras (sin Qt) que implementan: abortar adquisición → esperar `DRV_IDLE` (`camera.get_status()`, nuevo en el driver) → `SetReadMode` + configuración específica (`SetSingleTrack`/`SetMultiTrack`/`SetRandomTrack`/`SetImage`) → forma exacta del nuevo buffer NumPy. `AcquisitionSetupDialog` es un indicador visual no bloqueante (`QProgressBar` indeterminado) que envuelve la llamada vía `.run(fn, *args)`.

### 12.5 `andor_ccd_driver.py` — Pre-Amp Gain, HSSpeed, Multi/Random-Track
Nuevas constantes `PREAMP_GAINS_MOCK=[1.0, 2.0, 4.3]`, `HSSPEEDS_MHZ_MOCK=[5.0, 3.0, 1.0]`. Métodos nuevos en `_MockAndorCCD` y `AndorCCDDriver` (con el mismo patrón `try/except → DRV_NOT_INITIALIZED` que el resto del archivo): `get_status()`, `get_number_preamp_gains()`/`get_preamp_gain()`/`set_preamp_gain()`, `get_number_hs_speeds()`/`get_hs_speed()`/`set_hs_speed()`, `set_shutter_mode()`/`get_shutter_mode()`, `set_multi_track()`/`get_multi_track()`, `set_random_track()`, `get_tracks_2d_spectrum()` (frame sintético `(NumTracks, Width)` realista para Multi/Random-Track).

### 12.6 `SpectroscopyContext` (`pyspectrum/modules/spectroscopy_context.py`)
Singleton (mismo patrón `get_instance()` que `HardwareSessionManager`) con 4 señales: `verticalRoiChanged(y_min, y_max, y_center, y_height)`, `readModeChanged(mode)`, `spectrographMoved(wavelength_nm, grating)`, `subjugatedModeChanged(active)`. En Fase 1 sólo `LeftHardwarePanel` publica `spectrographMoved` en cada refresco; el consumo pleno (ROI vertical interactivo de Tab 1, subyugación de `contrapropagante.py`/`app.py`) llega en Fases 2-3.

### 12.7 Tests nuevos
`tests/test_pyspectrum_shell_and_panel.py` (15), `tests/test_zero_order_safety.py` (8), `tests/test_andor_read_modes_transition.py` (16) — 39 tests nuevos. Full suite: 0 regresiones nuevas contra las fallas preexistentes ya registradas en `DEC-010`/`DEC-013`/`DEC-014`.

### 12.8 Fase 2 — `ExplorationTabWidget`: Live View 2D y ROI Vertical Automático (`[[DECISION_LOG#DEC-016]]`)

La Pestaña 1 (`🔭 1. Exploración`) reemplaza definitivamente a `camera_andor.py::Frontend` por `pyspectrum/ui/exploration_tab.py::ExplorationTabWidget`, sin ningún control de hardware duplicado con el Panel Izquierdo (§12.2) — sólo visor y herramientas de imagen.

**Visor**: `pg.PlotItem` + `pg.ImageItem` (no `pg.ImageView`) con `pg.HistogramLUTWidget` lateral fijo (110 px). Colormaps intercambiables: **Viridis**, **Inferno**, **Greys**, **Jet** — los dos últimos resueltos vía `pg.colormap.get(name, source='matplotlib')`, con una implementación de respaldo hecha a mano si el backend matplotlib no estuviera disponible en el entorno. Herramientas de cabecera: `🔍 Auto-Rango` (encuadra la imagen completa), `🎚️ Auto-Contraste` (percentiles robustos 1–99% del cuadro actual, reutilizando `core/sif_processor.py::compute_robust_contrast_levels` — mismo algoritmo que el Analizador SIF), `✛ Retícula` (guía central de alineación).

**ROI Vertical Automático**: `pg.LinearRegionItem` horizontal sobre la imagen. A diferencia del ROI de `camera_andor.py::Frontend` (que sólo propaga al soltar el mouse, `sigRegionChangeFinished`), este propaga de forma **continua** durante el arrastre (`sigRegionChanged`) a `spectroscopy_context.set_vertical_roi(y_min, y_max)` — sin botones de Importar/Guardar. Un indicador discreto en la cabecera (`ROI Slit: [Y_min : Y_max] (Centro: Y_c, Alto: H px)`) refleja el estado en todo momento.

**`ExplorationWorker` — tercera excepción `QThread` del proyecto** (junto a Escaneo Lineal Espectral `[[DECISION_LOG#DEC-006]]` y Mapeo Confocal `ANOM-HYPERSPEC-01`): sostiene Live View a ~28 fps (mismo intervalo de 35 ms que la convención previa) sin bloquear el hilo GUI ni el botón E-STOP. Su `QTimer` interno se crea de forma perezosa dentro de `start_live()` para quedar correctamente afín al hilo del worker tras `moveToThread()`.

### 12.9 Tests nuevos (Fase 2)
`tests/test_pyspectrum_exploration_tab.py` (18): ausencia de controles de hardware duplicados, formateo del indicador de ROI (incl. límites invertidos), propagación automática a `SpectroscopyContext` + emisión de `verticalRoiChanged`, resolución de los 4 colormaps requeridos, auto-contraste robusto a outliers, `ExplorationWorker` (adquisición + `set_live()`), incrustación completa como Pestaña 0 del shell real. Full suite: 0 regresiones nuevas.

### 12.10 Fase 3 — Static Raman: Selector de Modos de Lectura, Herencia de ROI e Inspector 2D (`[[DECISION_LOG#DEC-017]]`)

La Pestaña 2 (`🔬 2. Static Raman`) ahora aloja `pyspectrum/ui/static_raman_container.py::StaticRamanTabContainer`, que divide el contenido en un `QTabWidget` interno de 2 sub-pestañas:

**Sub-pestaña A — 📊 Espectro 1D & Análisis** (`static_raman.py::StaticRamanWidget`, sin cambios de comportamiento en su pipeline de procesamiento): se agregó un **selector de Modo de Lectura** (`FVB` / `Single-Track (Hardware ROI)` / `Multi-Track` / `Imagen 2D`) en la cabecera de "Configuración Óptica & Ventana Espectral". Al seleccionar **Single-Track**, el widget lee inmediatamente `spectroscopy_context.vertical_roi` (heredado de la Pestaña 1: Exploración) y muestra `ROI heredado: [Y_min:Y_max] (Centro: Y_c, Alto: H px)`, manteniéndose sincronizado en vivo si el operador mueve el ROI en Exploración mientras Raman permanece abierto. En Multi-Track aparece un spinbox `N Pistas` (2-8). Cada cambio de modo dispara la transición segura (`transition_read_mode()` de la Fase 1, envuelta en `AcquisitionSetupDialog`) en `StaticRamanBackend.set_read_mode()`, que resuelve el centro/alto del ROI por sí mismo (única fuente de verdad para la transición de hardware). La sustracción de línea base AsLS/AirPLS/ModPoly y la termometría fototérmica Stokes/Anti-Stokes (`core/raman_engine.py`) quedaron completamente intactas — verificado corriendo primero los tests preexistentes sin modificar antes de escribir código nuevo.

**Enrutamiento de adquisición robusto a cambios de otras pestañas**: `StaticRamanBackend._acquire_and_emit()` consulta `self.camera.get_read_mode()` (el estado real del driver) en cada adquisición, no un valor cacheado por este widget — la cámara es un singleton compartido con `LeftHardwarePanel`/`ExplorationTabWidget`, así que confiar en un campo cacheado se desincronizaría si otra pestaña cambiara el modo mientras tanto. FVB/Single-Track emiten `spectrumAcquiredSignal` (1D, hacia el gráfico principal); Multi-Track/Imagen 2D emiten `frame2DAcquiredSignal(wl_axis, frame2d, read_mode_name)` hacia el Inspector 2D.

**Sub-pestaña B — 🗺️ Resultado Medición / Inspector 2D** (`pyspectrum/ui/raman_2d_inspector.py::Raman2DInspectorWidget`, nuevo): se activa automáticamente (`frameReceivedSignal` → `StaticRamanTabContainer` conmuta el `QTabWidget` interno) al llegar un cuadro 2D. Visor `pg.PlotItem`+`pg.ImageItem` con `pg.InfiniteLine` horizontal arrastrable, sincronizada bidireccionalmente (con `blockSignals`) con un `QSlider` vertical que recorre las filas $Y \in [0, H{-}1]$; etiqueta `Fila Y: [idx] (Cuentas pico: [val])`. Conmutador `☑ Promedio Espacial ROI ± σ`: calcula $\mu(\lambda)$/$\sigma(\lambda)$ sobre las filas del ROI heredado (`compute_roi_mean_std()`) y dibuja la banda sombreada con `pg.FillBetweenItem`.

**Exportación estructurada**: botón `💾 Exportar` con menú TXT/CSV (columnas $[\lambda, I]$ de la fila actual, o $[\lambda, \mu, \sigma]$ en modo promedio) y HDF5 estructurado (`export_raman_2d_to_hdf5()`: `/raw_2d`, `/spectrum_mean`, `/std`, `/wavelengths` + atributos de ROI/láser/red/timestamp; mismo patrón `H5PY_AVAILABLE` + `gzip`+`shuffle` que `core/sif_processor.py::export_sif_session_to_hdf5`).

### 12.11 Tests nuevos (Fase 3)
`tests/test_pyspectrum_static_raman_modes.py` (14): selector de modo, herencia y sincronización en vivo del ROI en Single-Track, transición de los 4 modos vía backend, enrutamiento de adquisición por estado real de cámara, preservación de AsLS y termometría. `tests/test_pyspectrum_raman_2d_inspector.py` (17): inyección de matriz sintética $1002\times1004$, slider↔línea guía bidireccional, $\mu$/$\sigma$ verificados contra NumPy directo, exportación TXT/HDF5 (incl. degradación sin h5py). Full suite: 0 regresiones nuevas.

### 12.12 Fase 4 — Step & Glue: Cosido Raised-Cosine, Multimodal 1D/2D y Referencia de Agua (`[[DECISION_LOG#DEC-018]]`)

La Pestaña 3 (`🧩 3. Step & Glue`) mantiene su widget (`step_and_glue.py::Frontend`/`Backend`, sin cambios de incrustación en `window.py`), pero su motor de cosido fue renovado por completo.

**Segundo algoritmo de cosido, no un reemplazo**: `pyspectrum/calibration/halogen_lamp.py::glue_steps()` (blending logístico preexistente, usado sin cambios por `linescan_spectroscopy.py`) convive con el nuevo **raised-cosine** ($w_1=\cos^2\theta$, $w_2=\sin^2\theta$, $\theta=\frac{\pi}{2}\frac{\lambda-\lambda_a}{\lambda_b-\lambda_a}$) en `raised_cosine_weights()`/`glue_pair_sigmoidal()`/`sigmoidal_step_and_glue()` (1D)/`sigmoidal_step_and_glue_2d()` (2D, fila por fila), con $w_1+w_2=1$ exacto en todo punto (verificado a precisión de punto flotante). La región de solapamiento $[\lambda_a,\lambda_b]$ se deriva de la intersección **real** de los ejes calibrados de dos pasos consecutivos, no de un ancho de píxeles fijo.

**Cálculo de centros espectrales corregido para depender de la red activa**: `compute_step_centers(start_wl, end_wl, overlap_pct, grating, num_pixels)` usa la dispersión real del Shamrock 500i (150 l/mm: 0.175 nm/px; 1200 l/mm: 0.022 nm/px — mismas constantes que `shamrock_driver.py`) en vez del ancho fijo de 240 nm que usaba la implementación anterior sin distinguir red. SpinBox `Solapamiento (%): [20]` en el rango 10-50%, ligado a `compute_step_centers()`.

**Soporte multimodal 1D/2D automático**: igual que en Static Raman (Fase 3), `Backend` lee `camera.get_read_mode()` real en cada barrido — `READ_MODE_IMAGE` activa el cosido 2D fila-por-fila (matriz $[H\times W_{total}]$, cacheada íntegra en `self._last_frame_2d` para exportación HDF5 completa, mientras el gráfico 1D muestra el promedio de filas); cualquier otro modo usa el cosido 1D estándar. La normalización por lámpara halógena (`HalogenLampCalibration.normalize_spectrum()`) funciona sin modificación en ambos casos gracias al *broadcasting* de NumPy.

**Ciclo de adquisición seguro por paso**: por cada $\lambda_{c,i}$: abortar adquisición residual → mover Shamrock y esperar asentamiento real (`_settle_wavelength`, sin sleep fijo) → adquirir → emitir `stepProgressSignal(i, N, λc)` hacia la barra de progreso no bloqueante (`Paso [i/N] (λ_c = X nm)`). **Cancelación resiliente**: `⏹ Detener` marca `_abort_requested`; el bucle corta limpio y el cosido se ejecuta igual sobre los pasos ya adquiridos (nunca se descartan datos parciales).

**Referencia Raman de Agua**: el checkbox `☑ Verificar Referencia Raman Agua (banda O-H, ~3400 cm⁻¹)` — presente en la UI desde antes de esta fase pero sin ninguna señal conectada — ahora dispara `_check_water_reference()`, que reutiliza `pyspectrum/calibration/fit_raman_water.py::fit_signal_raman()` sin modificarlo y reporta la amplitud de la banda O-H ajustada como diagnóstico textual (✅/⚠️) bajo la barra de progreso.

**Exportación HDF5 estructurada** (`export_step_and_glue_to_hdf5()`): `/glued_spectrum` (matriz 2D completa si el barrido fue en modo Imagen, vector 1D en caso contrario), `/wavelengths`, grupo `/raw_steps/step_NN` por cada paso crudo, atributos `grating`, `grating_name`, `slit_width_um`, `n_steps`, `timestamp` — mismo patrón `H5PY_AVAILABLE` + `gzip`+`shuffle` establecido en fases anteriores.

### 12.13 Tests nuevos (Fase 4)
`tests/test_pyspectrum_step_and_glue.py` (26 originales + 12 de la corrección de alineación legacy = 38): suma de pesos raised-cosine y continuidad de la transición cosida, encadenamiento secuencial de N pasos, cálculo de centros para 20%/30%/red 1200 l/mm, ejecución completa con mocks y verificación de progreso, cosido 2D en modo Imagen, cancelación anticipada con entrega de cosido parcial, normalización halógena (incl. 2D), exportación TXT/NPZ/HDF5, SpinBox de solapamiento, recorte de borde, zona óptica central y resta de sustrato. Full suite: 0 regresiones nuevas.

### 12.14 Corrección de Alineación con Legacy — Recorte de Borde, Zona Óptica Central y Lock de Sustrato (`[[DECISION_LOG#DEC-018]]`, punto de corrección)

El código legado real (`pyspectrum-legacy/StepandGlue_ps.py` + `Lampara_ps.py`, Luciana/CIBION — fuera de este repositorio, no localizable por la búsqueda inicial de la Fase 4) fue leído directamente para verificar 3 refinamientos experimentales pedidos por corrección, en vez de confiar en su paráfrasis:

- **Recorte de 15 píxeles de borde** (`glue_pair_sigmoidal(..., edge_crop_pixels=15)`, ahora el default): confirmado exacto contra `Lampara_ps.py::glue_steps()` (`n_skip_points=30` → `n=15` por lado, recortado de AMBOS extremos de cada paso individual antes de calcular la intersección de solapamiento), evita la aberración de coma en los bordes del CCD Andor. Guarda defensiva: arreglos cortos (donde `2×crop ≥ len`) degradan a "sin recorte" en vez de vaciarse.
- **Zona Óptica Central** (`compute_step_centers(..., use_optical_core=True)`): confirmado exacto contra `StepandGlue_ps.py::set_wavelength_window()` (líneas 1062-1072) — 103 nm para 150 l/mm, 12 nm para 1200 l/mm. Es una cantidad física **distinta** del span de dispersión teórico completo ya usado por defecto (~176 nm / ~22 nm, §12.12) — una ventana "usable" deliberadamente más conservadora, no un error en el cálculo de dispersión. Disponible como opción explícita (checkbox `🎯 Usar Zona Óptica Central`), no reemplaza el default.
- **Lock de Sustrato** (`btn_lock_substrate` "🔒 Fijar Fondo Sustrato" + `chk_sub_substrate` "Restar Fondo de Sustrato"): reproduce el modelo de resta indexada por píxel (no por longitud de onda) de `taking_signal_sustrate()`/`signal_sustrate_ON()`, generalizado a 1D y 2D según el modo de lectura real de la cámara en el momento de fijar el fondo. `Backend.lock_substrate()` memoriza `self._substrate_signal`; `measure_step_and_glue()` lo resta de cada paso crudo (antes de la normalización y el cosido) si `subtract_substrate=True`, ignorando la resta con una advertencia en consola (sin lanzar excepción) si la forma no coincide con la del barrido actual.

### 12.15 Fase 5 — Arquitectura Master-Slave: Subyugación de Ventanas Satélite y Puente de Soporte Óptico (`[[DECISION_LOG#DEC-019]]`)

PySpectrum 3.0 es la aplicación maestra del laboratorio. `contrapropagante.py` (microscopio contrapropagante dual) y `app.py` (microscopio simple) pueden abrirse como **ventanas satélite subyugables**: cuando PySpectrum tiene el control exclusivo del hardware, se subyugan automáticamente a Modo Solo Monitoreo.

**Acceso**: menú `🔧 Herramientas → Microscopio Contrapropagante (Ventana Satélite Subyugada)` (`Ctrl+M`), o `pyspectrum/window.py::_open_contrapropagante()`. Internamente usa `contrapropagante.py::create_contrapropagante_satellite(parent)` — la misma lógica de `main()` extraída a una función reutilizable, sin crear un `QApplication` propio ni bloquear con `app.exec()`, con sus 3 `QThread` (instrumento/confocal/cámara) detenidos automáticamente al cerrar la ventana. `app.py::create_app_satellite()` es el equivalente para el microscopio simple.

**Protocolo de subyugación**: `ContrapropaganteMainWindow`/`app.py::Frontend` se conectan a `spectroscopy_context.subjugatedModeChanged(bool)` **y** a `hardware_session.sessionChangedSignal(str, bool)`. `sessionChangedSignal` es el driver primario y atómico (trae nombre del dueño + estado juntos, evitando una condición de carrera de orden de señales entre ambos bus detectada durante el desarrollo). Banner ámbar (`#FAB387`/`#11111B`, 28px) `🔒 SUBJUGADO A {master} — Modo Solo Monitoreo`. `set_actuators_enabled(bool)` en cada Frontend compartido (`core/nanopositioning.py`, `core/shutters.py`, `modules/focus.py`, `modules/confocal.py`, `contrapropagante.py::ConfocalDualFrontend`) deshabilita únicamente los actuadores manuales — **excepciones de seguridad deliberadas**: `btn_close_all` (shutters) y `scanButtonstop`/`saveimageButton` (confocal) permanecen siempre habilitados (vías de escape); los displays de telemetría (posición PI, traza de fotodiodo, imagen confocal) **nunca** se deshabilitan.

**Wiring central único**: `pyspectrum/window.py::_setup_threads_and_backends()` conecta `hardware_session.sessionChangedSignal → spectroscopy_context.set_subjugated(busy)` **una sola vez** — todas las rutinas de PySpectrum ya pasan por el mismo singleton `hardware_session`, así que Step & Glue, Mapeo Confocal, Cinética, etc. subyugan/liberan automáticamente sin wiring individual. Indicador en la barra de herramientas: `🔗 Platina PI: Conectada [Libre/Subyugada]`.

**Módulo puente `pyspectrum/modules/optical_support.py`** (testeable sin GUI):
- `run_z_autofocus(laser_color, timeout_s, backend=None) -> bool`: invoca `FocusBackend.focus_autocorr_lin_x2()` vía `QMetaObject.invokeMethod(QueuedConnection)` + `QEventLoop` local con timeout y `heartbeat_shutter()` periódico — seguro sin importar en qué hilo real viva el `FocusBackend` provisto.
- `run_confocal_centering(range_um, pixels, method) -> (x, y)`: micro-raster síncrono propio (no reutiliza el escaneo por rampa asíncrono de `modules/confocal.py::Backend`), aplica `center_of_mass` siempre y `center_of_gauss2D` (`analysis/psf.py`) opcionalmente con fail-soft.
- `get_stage_coordinates() -> (x, y, z)`: `pi.qPOS()` directo.

**Bug real encontrado y corregido**: `modules/focus.py::focus_autocorr_lin_x2()` crasheaba con `UnicodeEncodeError` (emoji ⚠️ + em-dash bajo cp1252 de Windows) en su primera línea siempre que el foco no estuviera ya bloqueado — el error quedaba silenciado por el manejo de excepciones de Qt en slots vía cola, así que `run_z_autofocus()` sólo veía un timeout, nunca el error real. Corregido con el mismo patrón `try/except UnicodeEncodeError` ya establecido en `spectrum_control.py`.

### 12.16 Tests nuevos (Fase 5)
`tests/test_hardware_session_master_slave.py` (24): transición a Modo Solo Monitoreo y restauración en los 4 grupos de widgets subyugables (incl. excepciones de seguridad), telemetría confirmada siempre activa, paridad `app.py`, wiring central del bus, E-STOP (cierra shutters, libera sesión, libera la ventana satélite), `run_z_autofocus`/`run_confocal_centering`/`get_stage_coordinates` en `SAFE_MODE` sin colisiones de hilos. Full suite: 0 regresiones nuevas.

---

## 13. 🔗 Referencias Cruzadas
- [[SYS-301_Sistema_Espectrometro_Shamrock500i_iXon3|📘 SYS-301: Shamrock 500i, iXon3 y Óptica Confocal]]
- [[SYS-302_Calibracion_Espectral_y_Sincronizacion_Flippers|📑 SYS-302: Calibración Espectral, Offsets Ctypes y Flippers]]
- [[SYS-305_Arquitectura_Optomecanica_Microscopio_Derecho_y_Ruteo_Espectral|🔬 SYS-305: Arquitectura Optomecánica y Ruteo Espectral]]
- [[SYS-306_Arquitectura_Motor_Raman_y_Quimiometria_Multiespectral|🧪 SYS-306: Arquitectura Motor Raman y Quimiometría Multiespectral]]
- [[SYS-402_Auditoria_Comparativa_Andor_Solis_vs_PySpectrum|📊 SYS-402: Auditoría Comparativa Andor Solis vs PySpectrum 3.0]]
- [[CAT-103_Control_Lazo_Cerrado_Fototermico_y_Sintesis_Dimeros|🎯 CAT-103: Control en Lazo Cerrado Fototérmico y Síntesis de Dímeros]]
- [[CAT-109_Electrodinamica_Fuerzas_Opticas_y_Termoplasmonica_Printing|⚡ CAT-109: Electrodinámica, Fuerzas Ópticas y Termoplasmónica]]
- [[MOD-11_Raman_Analyzer_Suite_Quimiometria|🧪 MOD-11: Suite Raman Analyzer & Quimiometría]]
- [[MOD-12_Analizador_SIF_Andor_Solis|📈 MOD-12: Analizador y Procesador Avanzado de Espectros SIF]]
- [[MOD-14_Protocolos_Laboratorio_SOP|📋 MOD-14: Procedimientos Operativos Estandarizados (SOP)]]
- [[MANUAL_USUARIO|📘 Manual de Usuario Principal]]


