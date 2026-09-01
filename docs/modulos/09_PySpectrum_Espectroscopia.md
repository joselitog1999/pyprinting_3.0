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

## 6. 🔗 Referencias Cruzadas
- [📘 Manual de Usuario Principal — Sección 4: PySpectrum 3.0](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/docs/MANUAL_USUARIO.md#4-módulo-2-pyspectrum-30-pyspectrumpy--espectroscopía-step--glue-y-mapeo-hiperespectral)
- [🔬 Fundamentos Físicos & Nanomateriales (Módulo 00)](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/docs/modulos/00_Fundamentos_Fisicos_Optical_Printing_y_Nanomateriales.md)
- [📋 Protocolos y SOP de Laboratorio (Módulo 12)](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/docs/modulos/12_Protocolos_Operacion_Paso_a_Paso_Laboratorio.md)

