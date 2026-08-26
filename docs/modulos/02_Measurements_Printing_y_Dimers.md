# 🔬 Módulo 02: Rutinas de Impresión y Dímeros (`modules/measurements.py`)

**Laboratorio de Nanofotónica — Instituto de Nanosistemas (INS-UNSAM / CONICET)**  
**Archivo Fuente**: [`modules/measurements.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/modules/measurements.py)  
**Acceso en GUI**: Menú `Measurements -> Printing` o `Measurements -> Dimers` desde [`app.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/app.py) o [`contrapropagante.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/contrapropagante.py)

---

## 1. 🏷️ Resumen y Rol en el Sistema

El módulo **Measurements** es el motor principal de **nanofabricación óptica y ensamblado coloidal guiado por luz**. Permite imprimir matrices regulares $N \times M$ de nanopartículas individuales o pares de nanopartículas (*dímeros plasmonicos*) con control nanométrico, incorporando:
- **5 Criterios de Parada Seleccionables**: Salto relativo legacy, umbral absoluto, derivada $dI/dt$, calibración confocal raw e híbrido tri-factor.
- **Protección Anti-Partículas de Paso ($N_{\text{hold}}$)**: Conteo consecutivo para evitar falsas paradas por partículas flotantes en tránsito.
- **Auto-Corrección Activa de Deriva Térmica (*Drift Correction*)**: Mapeo periódico en baja potencia sobre la Partícula Ancla $P_0$ para compensar la deriva en nanómetros ($\Delta x_{\text{nm}}, \Delta y_{\text{nm}}$).
- **Gestor de Presets Experimentales (`.txt`)**: Carga y guardado de recetas precalibradas y Asistente Guiado multipaso.
- **Widget de Grilla Interactiva 2D (`InteractiveGridWidget`)**: Visualización en tiempo real orientada a $+90^\circ$ con retroalimentación por nodo (*Pendiente*, *Activo*, *Impreso*, *Fallo*).

---

## 2. 🖼️ Maqueta de la Interfaz Visual (ASCII Layout)

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│  PyPrinting 3.0 — Estación de Impresión de Nanopartículas (Printing / Dimers)                         -  □  ×    │
├──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│  Preset: [ 📄 Oro_60nm_532nm_Absoluto ▼ ]  [ 🧙 Lanzar Asistente ]  [ 📂 Cargar .txt ]  [ 💾 Guardar .txt ]       │
├───────────────────────────────────────┬───────────────────────────────────────┬──────────────────────────────────┤
│  DOCK: GRILLA DE IMPRESIÓN            │  DOCK: CRITERIO Y PARÁMETROS          │  DOCK: AUTOFOCO & DRIFT          │
│  Columnas n: [ 5 ]  Filas N: [ 5 ]    │  Criterio: [ Modo 1: Salto+Abs+Hold▼] │  Autofoco cada: [ 5 ] partes.    │
│  Paso dx: [ 3.0 ] µm  dy: [ 3.0 ] µm  │  Umbral Relativo:   [ 1.50 ]          │  Shift X: [ 2.0 ] µm  Y: [ 2.0 ] │
│  Offset X0: [ 2.0 ] µm Y0: [ 2.0 ] µm │  Umbral Abs (V):    [ 2.50 ]          │  [X] Scan pre-print? (ON)        │
│  Partículas Totales: 26 (1 Ancla+25)  │  N hold steps:      [ 5 ]             │  [X] Activar Corrección Drift?   │
│  [ 📐 Crear Grilla ] [ 📂 Load Grid ] │  Slope Min (V):     [ 0.00 ]          │  Deriva: [ (+12.4, -8.1) nm ]    │
│  Índice Actual: [ 1 ]  Partícula: 1/26│  Tiempo Máximo:     [ 20.0 ] s        │  [ 🔍 Test Drift P0 ]            │
├───────────────────────────────────────┴───────────────────────────────────────┴──────────────────────────────────┤
│  DOCK: GRILLA INTERACTIVA 2D (Orientación física de platina: Eje X horizontal, Eje Y vertical)                   │
│  ┌────────────────────────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │    Y (µm)                                                                                                  │  │
│  │    12.0|   ⚪ (P21)    ⚪ (P22)    ⚪ (P23)    ⚪ (P24)    ⚪ (P25)                                          │  │
│  │     9.0|   🟢 (P16)    🟢 (P17)    🟢 (P18)    🟢 (P19)    ⚪ (P20)                                          │  │
│  │     6.0|   🟢 (P11)    🟢 (P12)    🟢 (P13)    🟢 (P14)    🟢 (P15)                                          │  │
│  │     3.0|   🟢 (P6)     🟢 (P7)     🟢 (P8)     🟢 (P9)     🟢 (P10)     Leyenda de Nodos:                    │  │
│  │     0.0|   ⭐ (P0 Ancla) 🟢 (P1)   🟢 (P2)     🟢 (P3)     🟢 (P4)      ⭐ Ancla | 🟢 Impreso | 🔵 Activo   │  │
│  │        └────────────────────────────────────────────────────────── X(µm) ⚪ Pendiente | 🔴 Fallo          │  │
│  │           0.0         3.0         6.0         9.0        12.0                                              │  │
│  └────────────────────────────────────────────────────────────────────────────────────────────────────────────┘  │
│  Progreso: [████████████████████████████████████░░░░░░░░░░░░] 76% (19/25 partículas completadas)                │
│  [ 🚀 START PRINTING ]     [ ⏸ PAUSE / STEP ]     [ ⏹ STOP PRINTING ]     [ 💾 Save Extra Info ]                │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. 🎛️ Catálogo de Botones y Controles de la Interfaz

| Control / Parámetro | Widget | Rango / Opciones | Descripción Técnica |
|---|---|---|---|
| `Preset Combo` | `QComboBox` | Presets `.txt` disponibles | Carga instantáneamente todos los parámetros numéricos y opciones. |
| `Wizard Presets` | `QPushButton` | Diálogo multipaso | Abre el Asistente Guiado para crear nuevas recetas experimentales. |
| `Criterio Parada` | `QComboBox` | Modos 0, 1, 2, 3, 4 | Conmuta la visibilidad dinámica y el algoritmo evaluador en el Backend. |
| `Umbral Relativo` | `QLineEdit` | $1.05 - 10.0$ | Factor multiplicador de salto de señal respecto a la línea base previa ($I_{\text{new}} / I_{\text{old}}$). |
| `Umbral Abs (V)` | `QLineEdit` | $0.05 - 10.0\ \text{V}$ | Nivel absoluto en Volts para detección instantánea al abrir el obturador ($t=0$). |
| `N hold steps` | `QLineEdit` | $1 - 50\ \text{pasos}$ | Número de muestras continuas que deben satisfacer el criterio para validar la parada. |
| `Slope Flat` | `QLineEdit` | $0.001 - 1.0\ \text{V/s}$ | Pendiente máxima permitida para detectar meseta en Modo 2 e Híbrido ($|dI/dt| < \text{Slope\_Flat}$). |
| `Ratio K (P_print/P_scan)`| `QLineEdit` | $1.0 - 500.0$ | Relación de potencias entre impresión y escaneo para reescalar mapa confocal en Modo 3. |
| `Umbral (%)` | `QLineEdit` | $1.0 - 100.0\ \%$ | Porcentaje de la intensidad máxima confocal reescalada fijado como corte de voltaje. |
| `Drift Check` | `QCheckBox` | `ON / OFF` | Activa la generación de la Partícula Ancla $P_0$ y el escaneo periódico de deriva. |
| `START PRINTING` | `QPushButton` | — | Inicia la secuencia automatizada de nanoposicionamiento, autofoco e impresión. |

---

## 4. 📥 Archivos de Entrada que Solicita

1. **Archivos de Preset de Impresión (`presets/*.txt`)**:
   - *Formato*: Archivo de texto plano clave-valor estándar `key=value` o `clave: valor`.
   - *Ejemplo*:
     ```ini
     name=Oro_60nm_532nm_Absoluto
     stop_mode=1
     umbral_rel=1.50
     umbral_abs=2.50
     n_hold=5
     tmax=20.0
     autofocus_every=5
     drift_correction=True
     ```
2. **Archivos de Grilla de Coordenadas Externa (`Load_grid`)**:
   - *Formato*: Archivo de texto (`.txt`) con matriz $2 \times N$ de posiciones $[X_i, Y_i]$ en $\mu\text{m}$.

---

## 5. 📤 Archivos de Salida que Genera

Por cada lote o sesión de nanofabricación, el módulo crea una carpeta dedicada fechada:  
`YYYYMMDD-HHMMSS_Printing_5x5_drift_3.0umx3.0um/` que contiene:

1. **Trazas de Impresión de Cada Partícula (`NP_00i.txt`)**:
   - *Formato*: Archivo de texto con 4 columnas temporales a $10\ \text{kHz}$:
     ```
     # Tiempo(s)    Fotodiodo(V)    Fotodiodo_Filtrado(V)    BS_Power(V)
     0.00010        0.12450         0.12480                  0.54320
     0.00020        0.12510         0.12495                  0.54315
     ...
     ```
2. **Escaneo Confocal Pre/Post-Impresión (`NPscan_00i.tiff`, `.npy`, `.csv`)**:
   - Si `Scan pre-print?` está activo, guarda el mapa confocal 2D de confirmación óptica.
3. **Escaneo Confocal Reescalado (`NPscan_rescaled_00i.txt` / `.tiff`)** *(Modo 3)*:
   - Guarda la matriz reescalada por $K_{\text{scale}}$ con el umbral absoluto calculado en la cabecera.
4. **Metadatos y Parámetros Experimentales (`grid_info.txt`)**:
   - Registra fecha, tipo de nanopartícula, sustrato, potencia BFP, criterio de parada y derivas medidas.
5. **Subcarpetas en Modo Dímeros**:
   - `Pree_Scan/`: Escaneos de la primera partícula del par coloidal.
   - `Dimer_Scan/`: Escaneos del dímero ensamblado final.

---

## 6. ⚙️ Algoritmos de los 5 Criterios de Parada

```mermaid
graph TD
    A[Señal Fototérmica I_new, I_old, dI/dt] --> B{Selección de Criterio}
    
    B -->|Modo 0: Legacy| C[I_new > I_old * Umbral_Rel]
    B -->|Modo 1: Rel+Abs+Hold| D[I_new > I_old * Umbral_Rel Ó I_new > Umbral_Abs]
    B -->|Modo 2: Derivada dI/dt| E[|dI/dt| < Slope_Flat Y I_new > I_old + 0.1V]
    B -->|Modo 3: Confocal Raw| F[I_new > V_thresh_rescaled Y I_new > I_old * Umbral_Rel]
    B -->|Modo 4: Híbrido Tri-Factor| G[Evalúa Relativo Ó Derivada Ó Absoluto]
    
    C --> H{¿Cumple Slope Min?}
    D --> I{¿Sostenido N_hold pasos?}
    E --> I
    F --> I
    G --> I
    
    I -- Sí --> H
    I -- No --> J[Incrementar hold_counter / Reset]
    
    H -- Sí --> K[CIERRE INMEDIATO DE SHUTTER < 1 ms]
    H -- No --> L[Continuar Adquisición]
```

- **Máquina de Estados de Corrección de Deriva**:
  1. Si $i \pmod{\text{autofoc}} == 0$: ejecuta autofoco axial Z con flipper arriba (baja potencia).
  2. Si `drift_correction == True`: desplaza la platina a la Partícula Ancla $P_0$, realiza un microescaneo confocal de $2 \times 2\ \mu\text{m}$, calcula el centro de masa 2D y actualiza el vector acumulado $\Delta \mathbf{r}$.
  3. Desplaza la platina a la posición compensada $\mathbf{r}_i + \Delta \mathbf{r}$, conmuta el flipper hacia abajo (alta potencia) y dispara la traza de impresión.

---

## 7. 🔗 Referencias Cruzadas
- [📘 Manual de Usuario — Sección 4.6: Ejecución de Impresión](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/docs/MANUAL_USUARIO.md#46-ejecución-de-un-patrón-de-impresión-nanofabricación)
- [📘 Manual de Usuario — Sección 5: Criterios de Parada](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/docs/MANUAL_USUARIO.md#5-criterios-de-parada-y-detección-de-nanopartículas)
- [📑 Reporte Algorítmico (`reportes/sistema/Algoritmo_Printing_y_Dimers_PyPrinting3.md`)](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/reportes/sistema/Algoritmo_Printing_y_Dimers_PyPrinting3.md)
- [📑 Reporte Metrológico de Deriva (`reportes/cientificos/Analisis_Metrologico_Deriva_Termica_P0.md`)](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/reportes/cientificos/Analisis_Metrologico_Deriva_Termica_P0.md)
