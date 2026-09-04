# 🌈 Módulo 09: PySpectrum 3.0 — Espectroscopía & Mapeo Hiperespectral (`pyspectrum.py`)

**Laboratorio de Nanofotónica — Instituto de Nanosistemas (INS-UNSAM / CONICET)**  
**Archivo Fuente**: [`pyspectrum.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/pyspectrum.py) | Paquete: [`pyspectrum/`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/pyspectrum/)  
**Lanzador Rápido**: Botón 2 en [`main.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/main.py) o `python pyspectrum.py`

---

## 1. 🏷️ Resumen y Rol en el Sistema

El módulo **PySpectrum 3.0** es la estación central de **espectroscopía óptica, cosido espectral continuo (*Step and Glue*) y caracterización hiperespectral 2D/3D** de la suite PyPrinting 3.0.

Integra de forma multihilo y desacoplada (`PyQt6` + `pyqtgraph.dockarea`):
- **Control de Espectrógrafo Andor Shamrock (SR-303i / SR-500i)**: Selección de red de difracción (150 l/mm, 1200 l/mm, espejo), longitud de onda central $\lambda_{center}$, ranuras micrométricas motorizadas (*slits*) y conmutación de puertos (*flippers*).
- **Cámara Andor CCD / EMCCD (Newton / iDus)**: Control de enfriamiento termoeléctrico Peltier ($-10\ ^\circ\text{C}$), tiempo de integración, ganancia EMCCD, visualización 2D en falso color y *binning* vertical automático para perfil 1D.
- **Algoritmo *Step & Glue* de Banda Ancha**: Adquisición concatenada de múltiples rangos espectrales (ej. $450 - 950\ \text{nm}$) con solapamiento suave ponderado y normalización por lámpara halógena de calibración.
- **Mapeo Confocal Hiperespectral $(X, Y, \lambda)$**: Coordinación del escaneo piezoeléctrico PI cerrado con la captura espectral por píxel para generar hipercubos de datos tridimensionales.
- **Rutinas Especializadas**:
  - *Fotoluminiscencia y Anti-Stokes*: Registro temporal $I(\lambda, t)$ bajo excitación láser.
  - *Cinética de Crecimiento de Nanopartículas*: Detección y seguimiento continuo del máximo plasmónico $\lambda_{max}(t)$ mediante ajuste polinomial.
  - *Caracterización de Dímeros*: Análisis de acoplamiento plasmónico y anisotropía por polarización (paralela vs perpendicular).

---

## 2. 🖼️ Maqueta de la Interfaz Visual (ASCII Layout)

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│  PySpectrum 3.0 — Espectroscopía & Mapeo Hiperespectral  [UNSAM Nanofotónica]                         -  □  ×    │
├──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│  📁 Archivo    🔧 Herramientas    🧪 Rutinas                                                                      │
├───────────────────────────────────────────────────────────────────────┬──────────────────────────────────────────┤
│  DOCK: CÁMARA ANDOR CCD (Detector 2D & Perfil 1D)                     │  DOCK: ESPECTROSCOPÍA & STEP AND GLUE    │
│  [ ▶ Iniciar Live View ]  [ ❄️ Temp: -10.0 °C (Estabilizado) ]        │  Tiempo Exp: [ 1.0 ] s  λ Centro: [ 532 ]│
│  Exp: [ 0.05 ] s  Set T: [ -10 ] °C  EM Gain: [ 0 ]                   │  [ 🔬 Medir Espectro Simple ]            │
│  ┌─────────────────────────────────────────────────────────────────┐ │  ┌─────────────────────────────────────┐  │
│  │                                                                 │ │  │ Parámetros Step & Glue (Cosido)     │  │
│  │   [ Imagen 2D de la Ranura del Espectrógrafo / CCD ]            │ │  │ λ Inicial: [ 450.0 ] nm             │  │
│  │   Resolución: 1002 x 1002 px                                    │ │  │ λ Final:   [ 950.0 ] nm             │  │
│  │   ROI Horizontal: y = 480 .. 520 px                             │ │  │ Solapamiento: [ 0.20 ]              │  │
│  │                                                                 │ │  │ ☑ Normalizar con Lámpara Halógena   │  │
│  └─────────────────────────────────────────────────────────────────┘ │  │ ☑ Ajuste Polinomial SPR (λ_max)      │  │
│  ┌─────────────────────────────────────────────────────────────────┐ │  │ ☐ Ajuste Raman Agua (3300 cm⁻¹)     │  │
│  │ Perfil 1D Binnizado: [ Espectro en Vivo / ADC Counts ]          │ │  │ [ 🧩 Ejecutar Step and Glue ]       │  │
│  └─────────────────────────────────────────────────────────────────┘ │  └─────────────────────────────────────┘  │
├───────────────────────────────────────────────────────────────────────┼──────────────────────────────────────────┤
│  DOCK: ESPECTRÓGRAFO ANDOR SHAMROCK                                   │  DOCK: MAPEO CONFOCAL HIPERESPECTRAL     │
│  Red: [ 150 líneas/mm ▼ ]   λ Central: [ 532.00 ] nm                  │  X Min/Max: [ 45.0 ] [ 55.0 ] µm Step: 1 │
│  Ranura Entrada: [ 50.0 ] µm  Puerto: [ Port 0: Fibra ▼ ]             │  Y Min/Max: [ 45.0 ] [ 55.0 ] µm Exp:0.05│
│  [ 🟢 Obturador Espectrógrafo: ABIERTO ]                              │  [ 🚀 Iniciar Escaneo Hiperespectral ]   │
│  Rango en detector: 356.2 nm — 708.4 nm                               │  [ Matriz: 11x11 pts ] [ Barra Progreso ]│
├───────────────────────────────────────────────────────────────────────┴──────────────────────────────────────────┤
│  🟢 PySpectrum 3.0 Listo | Carpeta de trabajo: C:/Users/josel/Documents/Data_PySpectrum | Temp: -10.0 °C         │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

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
| **🧪 Rutinas** | Luminiscencia & Anti-Stokes | Abre la ventana de seguimiento de fotoluminiscencia temporal $I(\lambda, t)$. |
| **🧪 Rutinas** | Cinética de Crecimiento | Abre la ventana de monitoreo de crecimiento in-situ de nanopartículas. |
| **🧪 Rutinas** | Dímeros Plasmónicos | Abre la ventana de espectroscopía de dímeros y anisotropía de polarización. |

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

## 8. ⚠️ Límites de Validez y Modos de Falla

| Condición de Borde (Fallo Espectroscópico / Hardware) | Firma Experimental (Espectro 1D / Imagen CCD) | Acción Correctiva Física (Procedimiento en Laboratorio) |
| :--- | :--- | :--- |
| **Saturación del Convertidor ADC de la Cámara CCD Andor** ($I \ge 65535\ \text{ADU}$). | Picos truncados planos en $65535\ \text{cuentas}$ y desbordamiento de carga (*blooming*) horizontal en el sensor CCD. | Reducir el tiempo de exposición (ej. de $1.0\ \text{s}$ a $0.1\ \text{s}$) o cerrar el ancho de las ranuras micrométricas de entrada del espectrógrafo a $\le 50\ \mu\text{m}$. |
| **Descalibración por Holgura Mecánica en Torreta de Redes (*Grating Backlash*)**. | El pico elástico del láser de 532 nm aparece desplazado en la escala de longitudes de onda calculada ($\Delta \lambda > 2\ \text{nm}$). | Ejecutar la rutina de calibración espectral con lámpara atómica de Mercurio-Argón (Hg-Ar) o corregir el offset con el pico de scattering elástico de 532.0 nm. |
| **Condensación en la Ventana Óptica por Falla de Refrigeración Peltier**. | Pérdida abrupta de intensidad luminosa y aumento drástico del nivel de ruido térmico basal de la CCD. | Comprobar el flujo de agua en el recirculador térmico / ventilador de la CCD y asegurar que el vacío interno esté estable con temperatura nominal de $-10\ ^\circ\text{C}$ a $-60\ ^\circ\text{C}$. |
| **Discontinuidades en el Cosido Espectral (*Step & Glue*)**. | Saltos de intensidad escalonados en las zonas de unión/solapamiento entre ventanas espectrales contiguas. | Adquirir un nuevo espectro de calibración con la lámpara halógena de referencia para normalizar la respuesta cromática de la rejilla de difracción y del sensor. |

---

## 9. 🔗 Referencias Cruzadas
- [📘 Reporte de Sistema Shamrock 500i, iXon3 y Óptica Confocal](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/reportes/sistema/Reporte_Sistema_Espectrometro_Shamrock500i_iXon3_PySpectrum.md)
- [📘 Manual de Usuario Principal — Sección 4: PySpectrum 3.0](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/docs/MANUAL_USUARIO.md#4-módulo-2-pyspectrum-30-pyspectrumpy--espectroscopía-step--glue-y-mapeo-hiperespectral)
- [🔬 Fundamentos Físicos & Nanomateriales (Módulo 00)](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/docs/modulos/00_Fundamentos_Fisicos_Optical_Printing_y_Nanomateriales.md)
- [📋 Protocolos y SOP de Laboratorio (Módulo 12)](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/docs/modulos/12_Protocolos_Operacion_Paso_a_Paso_Laboratorio.md)


