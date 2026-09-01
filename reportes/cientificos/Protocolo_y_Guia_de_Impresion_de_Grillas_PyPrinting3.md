# Reporte Técnico y Guía Protocolar Exhaustiva: Impresión Óptica Fototérmica de Grillas de Nanopartículas en PyPrinting 3.0 🔬

**Laboratorio de Nanofotónica — Instituto de Nanosistemas (INS-UNSAM / CONICET)**  
**Autor Principal**: José Luis González Peñafiel (*Becario Doctoral CONICET*)  
**Fecha de Publicación**: 6 de Agosto de 2026  
**Documento de Referencia**: `reportes/Protocolo_y_Guia_de_Impresion_de_Grillas_PyPrinting3.md`  
**Módulos del Sistema**: `main.py`, `app.py`, `modules/measurements.py`, `modules/confocal.py`, `modules/focus.py`, `modules/trace.py`

---

## 1. Resumen Ejecutivo

El presente documento constituye la **Guía Protocolar Estandarizada Operativa** para la nanofabricación asistida por luz mediante **Impresión Óptica Fototérmica de Nanopartículas Coloidales Metálicas** (Au, Ag) utilizando la suite **PyPrinting 3.0**.

Este protocolo detalla paso a paso la secuencia física y de software requerida para acomodar ópticamente el sistema, alinear la partícula origen en el sustrato, fijar la referencia nanométrica de origen, definir la geometría del arreglo (matriz $n \times N$), configurar los criterios de parada en tiempo real y ejecutar la impresión automatizada nodo a nodo.

 Cualquier investigador, estudiante o técnico del laboratorio puede reproducir de manera idéntica y confiable la impresión de redes ordenadas de nanopartículas siguiendo las instrucciones de este reporte.

---

## 2. Fundamentos Físicos de la Impresión Óptica y Arquitectura del Sistema

```
                                    ┌────────────────────────┐
                                    │ Excitación Láser (High)│
                                    │  (Verde 532 / Rojo 637)│
                                    └───────────┬────────────┘
                                                │
                                                ▼
┌────────────────────────┐         ┌────────────────────────┐
│ Solución Coloidal AuNPs│         │ Objetivo Inmersión Agua│
│ (Sustrato + PDDA/PSS)  │ <────── │ (60x NA=1.0 / 100x)   │
└────────────────────────┘         └───────────┬────────────┘
                                                │
                                                ▼
                                   ┌────────────────────────┐
                                   │ Platina Piezoeléctrica │
                                   │  PI E-517 (Sens. Cap.) │
                                   └────────────────────────┘
```

La impresión óptica se basa en la transferencia dirigida de nanopartículas coloidales desde la solución hacia la interfaz del sustrato funcionalizado (vidrio recubierto con polielectrolitos como PDDA/PSS).

1. **Fuerza de Gradiente Óptico ($\mathbf{F}_{\text{grad}}$)**: La cintura del haz focalizado mediante un objetivo de alta apertura numérica ($\text{NA} \ge 1.0$) atrae la nanopartícula metálica hacia el centro del foco fototérmico.
2. **Presión de Radiación ($\mathbf{F}_{\text{scat}}$)**: Empuja la partícula contra la superficie hasta lograr la adhesión electrostática irreversible.
3. **Monitoreo por Fotoluminiscencia (Trazas $10\ \text{kHz}$)**: Al abrir el obturador, la señal analógica del fotodiodo registra el incremento de dispersión/fotoluminiscencia. Al gatillarse el salto de señal, el sistema cierra el obturador en $< 1\ \text{ms}$, fija la partícula en el sustrato y desplaza la platina PI al siguiente nodo.

---

## 3. Protocolo Paso a Paso para la Impresión de Grillas ("DO PRINTING")

### Paso 1: Configuración Inicial de Entorno y Directorio Diario
1. **Selección del Microscopio**:
   - Para el **Microscopio Derecho (Monomodo)**: Ejecutar `main.py` y presionar **`🚀 Iniciar Microscopio Derecho (app.py)`**.
   - Para el **Microscopio Contrapropagante (Excitación Dual TOP/BOT)**: Ejecutar `main.py` y presionar **`🔍 Microscopio Contrapropagante (contrapropagante.py)`**.
     > [!NOTE]
     > El microscopio contrapropagante (`contrapropagante.py`) cuenta con la misma suite de software que `app.py` (tablero de seguridad, presets `.txt`, wizard, FFT de trazas y auto-recuperación), permitiendo la impresión idéntica de grillas pero con iluminación y adquisición confocal síncrona superior e inferior.
2. En la barra superior de menús, ir a **`Files` $\rightarrow$ `Create Daily Dir (Ctrl+S)`**.
3. Seleccionar la carpeta raíz de trabajo (ej. `C:/Data`). El sistema creará automáticamente la subcarpeta del día con formato `YYYY-MM-DD` (ej. `C:/Data/2026-08-06`).

---

### Paso 2: Acomodación Óptica Manual y Enfoque en Vidrio
1. En el dock **`Shutters / Flipper / Láser 532`**, seleccionar la línea láser de excitación (ej. `532 nm`).
2. Ajustar el atenuador de potencia a **`Low Power`** y posteriormente buscar una zona ideal para impresión de forma manual.
3. Mediante el micrométrico manual del objetivo y la cámara réflex Live View (`camera.py`), enfocar nítidamente la superficie del sustrato de vidrio.
4. Una vez identificada la zona, ajustar el atenuador de potencia a **`High Power`** para lograr la intensidad necesaria de presión de radiación para realizar la impresión.

---

### Paso 3: Escaneo Confocal y Centrado de Partícula
1. En el dock **`Confocal`** (o **`Confocal Contrapropagante Dual`** en `contrapropagante.py`), configurar el área de escaneo (ej. `Range x/y` = $5.0\ \mu\text{m}$, `Pixels x/y` = $100 \times 100$).
2. Presionar **`Start Scan`** para registrar la imagen confocal 2D de la nanopartícula de referencia.
3. Seleccionar el método de centrado analítico `method_center` = `center of mass` o `center of gauss`. En `contrapropagante.py`, seleccionar también la referencia deseada (`Ref. Preference`: TOP o BOT).
4. Con la casilla **`Auto CM`** marcada, el sistema moverá automáticamente la platina piezoeléctrica PI al centroide exacto de la partícula.

---

### Paso 4: Ajuste Axial Z (`Go to maximum`) y Congelado de Referencia (`Lock focus`)
1. En el dock **`Focus z`**, presionar **`Go to maximum (F8)`**. La platina ejecutará un barrido rápido en $Z$ y se ubicará en la cima de máxima fotoluminiscencia.
2. Repetir el paso 3 y el paso 4.1 hasta obtener un buen centrado de la partícula y máxima fotoluminiscencia.
3. En el dock **`Nanopositioning`**, desplazar lateralmente la platina $\approx 2.0\ \mu\text{m}$ en $X$ hacia una zona de vidrio limpio libre de partículas.
4. Presionar **`Lock Focus (F9)`** para registrar el perfil axial de referencia $I_{\text{ref}}(z)$ de la interfaz sustrato-solución.
5. Regresar la platina a la coordenada central de la partícula en $X$ e $Y$.
6. Asegurarse de que el atenuador de potencia se encuentre en **`High Power`** pero el obturador cerrado, de modo que el sistema esté listo para depositar una partícula.

---

### Paso 5: Apertura de la Ventana `Printing` y Carga de Presets (`Preset Manager / Wizard`)
1. En el menú superior, seleccionar **`Measurements` $\rightarrow$ `Printing`**. Se desplegará la ventana modular `Frontend` de impresión.
2. Presionar el botón naranja **`Set reference`**:
   - El sistema leerá inmediatamente las coordenadas capacitivas reales de la platina PI ($X_0, Y_0, Z_0$) y las mostrará en las etiquetas `X ref`, `Y ref`, `Z ref`.
   - Todas las posiciones futuras de la grilla se calcularán relativas a este punto origen.
3. **Carga o Creación de Presets Experimentales**:
   - **Opción A (Preset desde Archivo `.txt`)**: Seleccionar un perfil predeterminado en el menú desplegable **Preset** (ej. `AuNP_60nm_ImpresionRapida.txt` o `AgNP_80nm_Nanodimeros.txt`).
   - **Opción B (Asistente Guiado `🧙 Wizard`)**: Presionar **`🧙 Wizard`** para abrir el asistente de 5 pasos y configurar el criterio de parada, umbrales, tiempos $T_{\text{max}}$ y autofoco, guardando automáticamente el nuevo preset en `presets/`.

---

### Paso 6: Configuración de Focus Shift y Corrección de Deriva
1. En la pestaña **`Focus drift`**, verificar los parámetros del preset cargado:
- **`Autofocus every N`**: Indica cada cuántas nanopartículas se realizará un autofocus (ej. cada 5 nodos).
- **`Shift x/y (µm)`**: Desplazamiento lateral para garantizar una zona limpia donde ejecutar el autofoco Z (recomendado: $2.0\,\mu\text{m}$).
- **`Drift Correction`**: Activa la corrección de deriva por partícula ancla $X-Y$ en tiempo real.
- **`Start X/Y (µm)`**: Posición inicial del arreglo respecto a la partícula ancla P0 (recomendado: $2.0\,\mu\text{m}$).

---

### Paso 7: Generación o Carga de la Grilla de Posiciones
- **Opción A: Generar Grilla Regular (`Create grid`)**:
  1. En la pestaña **`Grid`**, ingresar:
     - **`NPs/col`**: Cantidad de nanopartículas por columna (ej. `4`).
     - **`Columns`**: Cantidad de columnas (ej. `4`).
     - **`Dist NP (µm)`**: Espaciamiento entre nanopartículas en la misma columna (ej. `3.0`).
     - **`Dist col (µm)`**: Espaciamiento entre columnas (ej. `3.0`).
  2. Presionar **`Create grid`**. El casillero `Total targets` actualizará el conteo (ej. `16`) y desplegará el gráfico 2D interactivo `Grid Pattern & Path Viewer 🗺️`.

- **Opción B: Cargar Grilla Personalizada (`Load grid (.txt)`)**:
  1. Presionar **`Load grid (.txt)`** y seleccionar un archivo `.txt` conteniendo 2 columnas $(X, Y)$ en micrómetros.

- **Opción C: Diseñar Red Cristalográfica Avanzada con el Diseñador 2D (`📐 Diseñador 2D`)**:
  1. En el dock de Grilla, hacer clic en **`📐 Diseñador 2D`** (o presionar `Ctrl+G`) para abrir [`grid_generator.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/grid_generator.py).
  2. Seleccionar entre las 15 familias de redes 2D (Grafeno, Kagome, Lieb, Moiré, Hexagonal, TMD $\text{MoS}_2$, etc.).
  3. Ajustar los vectores $\mathbf{a}_1, \mathbf{a}_2$, el deslizador de ángulo $\gamma \in [5^\circ, 175^\circ]$, las posiciones fraccionales $(u_j, v_j)$, y la restricción física $d_{\text{min}}$.
  4. Exportar el archivo `.txt` unificado o el paquete multi-paso con Partícula Ancla $P_0$ y cargarlo directamente con `Load grid (.txt)`.

---

### Paso 8: Creación de la Carpeta del Lote Experimental (`PRINTING folder`)
1. Presionar el botón **`PRINTING folder`** o ingresar un nombre en **`Custom Name`**.
2. El sistema creará automáticamente una subcarpeta fechada con el nombre del lote en el directorio del día:
   `C:/Data/2026-08-06/20260806-120000_Printing_4x4_3umx3um/`
3. El indicador se tornará **verde** mostrando la ruta del lote activo.
4. Llenar `Extra info` con la metainformación de la muestra (tipo de nanopartícula, ligando, sustrato funcionalizado).

---

### Paso 9: Configuración del Criterio de Parada y Parámetros
El algoritmo de interrupción en tiempo real se cargará automáticamente desde el preset o se podrá seleccionar manualmente en **`Criterio Parada`**:

| Modo de Parada | Nombre en UI | Cuándo Utilizarlo | Parámetros a Configurar |
|---|---|---|---|
| **Modo 0** | `Legacy (Salto Relativo Estándar)` | Impresiones estándar con alto contraste de dispersión. | `Umbral` ($1.20$), `T max (s)` ($20$), `Steps before/after`. |
| **Modo 1** | `Salto Relativo + Umbral Absoluto & Anti-Paso` | Evita falsos disparos por nanopartículas flotantes de paso. | `Umbral`, `Umbral Abs (V)` ($2.5\text{ V}$), `N hold steps` ($5$). |
| **Modo 2** | `Derivada Temporal dI/dt & Aplanamiento` | Detención inmediata al alcanzar la meseta fototérmica post-pico. | `Slope Min` ($15\text{ V/s}$), `Slope Flat` ($2\text{ V/s}$). |
| **Modo 3** | `Calibración Confocal Raw & Reescalado` | Calibración fotométrica absoluta sobre la señal de vidrio. | `Ratio K (P/S)` ($10$), `Umbral (%)` ($50\%$). |
| **Modo 4** | `Criterio Híbrido Tri-Factor (All-In-One)` | Máxima precisión metrológica y triple verificación. | Todos los parámetros activos. |

---

### Paso 10: Ejecución de la Impresión Automatizada (`Play ►`), Healing Pass y Monitoreo de ETA
1. Presionar el botón **`Play ►`**.
2. El sistema ejecutará automáticamente la secuencia ciclo a ciclo:
   $$\text{Mover a Nodo } i \longrightarrow \text{Autofoco Z (si corresponde)} \longrightarrow \text{Abrir Shutter \& Grabar Traza} \longrightarrow \text{Detección Parada} \longrightarrow \text{Cerrar Shutter \& Guardar } \texttt{NP\_iii.txt} \longrightarrow \text{Pre-Scan (Opción)} \longrightarrow \text{Mover a } i+1$$
3. **Telemetría y Estimador de Tiempo Restante (ETA)**:
   - En la parte superior de la ventana, frente al casillero `Total targets`, el sistema actualiza en tiempo real el tiempo estimado restante:
     $$\text{ETA}(k) = \langle t_{\text{raw}} \rangle \cdot (N_{\text{total}} - k) + N_{\text{AF\_rem}} \cdot t_{\text{AF}}$$
     donde $\langle t_{\text{raw}} \rangle$ se calcula como el promedio acumulativo de las impresiones anteriores (tomando 15 s por defecto para el nodo 0).
4. **Autocompletitud Inteligente de Redes (`Healing Pass`)**:
   - Si la opción `🔄 Autocompletitud (Healing Pass)` está activada: al concluir el barrido primario de la grilla, el sistema no finaliza el lote si detecta nodos con estado `TIMEOUT` (no impresos).
   - El algoritmo entra automáticamente en el **Healing Pass**:
     1. Reúne la cola de nodos fallidos: $\mathcal{Q}_{\text{healing}} = \{k_1, k_2, \dots, k_M\}$.
     2. Cambia el estado visual en el visor interactivo a **`retrying`** (anillo naranja `#fab387`).
     3. Desplaza la platina al sitio de cada nodo fallido y ejecuta un **Autofoco axial *in-situ*** directo sobre el sustrato.
     4. Concede una ventana temporal de exposición extendida: $T_{\text{max\_effective}} = T_{\text{max}} + 10.0\ \text{s}$.
     5. Preserva la cadencia periódica de corrección de deriva XY en la Partícula 0 cada $N$ intentos totales.
     6. Al recuperarse la partícula, estampa el metadato `# Status: SUCCESS (Healing Pass - Retry, t_print=XX.Xs)` y actualiza el nodo a 🟢 **`success`**.
5. La **Barra de Estado Global** informará en vivo el progreso, la velocidad de deriva instantánea $\vec{v}_{\text{drift}}$ y el visor **Grid Pattern & Path Viewer 🗺️** cambiará el color de los nodos impresos a 🟢 **Impresa**, 🟠 **Reintento** o 🔴 **Timeout**.
6. Para pausar en cualquier instante, presionar **`Pause`**. Para forzar el salto al siguiente nodo, presionar **`Next index ►`**.

---

## 4. Descripción Exhaustiva de Parámetros y Tooltips de la Interfaz

| Control / Casillero | Tipo de Dato | Rango Recomendado | Descripción Explicativa y Función Metrológica |
|---|---|---|---|
| **`Láser`** | `QComboBox` | `532 nm`, `637 nm`, `592 nm` | Selector de la línea láser fototérmica enviada al objetivo. |
| **`Criterio Parada`** | `QComboBox` | Modos `0` a `4` | Algoritmo matemático para detener la exposición al adherirse la NP. |
| **`Umbral rel`** | `QLineEdit` | $1.05 - 2.00$ | Ratio $I_{\text{new}}/I_{\text{old}}$. Un valor de `1.20` indica un salto del $20\%$ sobre la línea base. |
| **`Umbral Abs (V)`** | `QLineEdit` | $0.500 - 5.000\ \text{V}$ | Nivel absoluto en Volts necesario para validar el evento de adhesión. |
| **`N hold steps`** | `QLineEdit` | $1 - 20$ muestras | Muestras continuas de confirmación para filtrar partículas de paso. |
| **`Slope Min (V/s)`** | `QLineEdit` | $5.0 - 50.0\ \text{V/s}$ | Pendiente $dI/dt$ mínima requerida en la fase ascendente del pulso. |
| **`Slope Flat (V/s)`**| `QLineEdit` | $0.5 - 5.0\ \text{V/s}$ | Pendiente $dI/dt$ máxima permitida en la meseta para cerrar el shutter. |
| **`Umbral down`** | `QLineEdit` | $0.0 - 0.5$ | Caída mínima de señal para abortar impresión por photobleaching. |
| **`T max (s)`** | `QLineEdit` | $1.0 - 60.0\ \text{s}$ | Tiempo límite por nodo antes de abortar por falta de evento. |
| **`Steps before`** | `QLineEdit` | $5 - 50$ muestras | Muestras analógicas antes de abrir el obturador para fijar $I_{\text{old}}$. |
| **`Steps after`** | `QLineEdit` | $5 - 50$ muestras | Muestras adicionales post-cierre para registrar la meseta $I_{\text{final}}$. |
| **`Autofocus every`** | `QLineEdit` | $1 - 100$ nodos | Frecuencia de nodos entre correcciones axiales Z por autocorrelación. |
| **`Shift x / y (µm)`**| `QLineEdit` | $0.0 - 20.0\ \mu\text{m}$ | Vector offset lateral para ejecutar el autofoco Z en zona sin partículas. |
| **`Autocompletitud (Healing)`** | `QCheckBox` | `ON` / `OFF` | Reintenta automáticamente nodos no impresos con autofoco in-situ y $+10\ \text{s}$. |
| **`Inclinación Z Confocal`** | `QCheckBox` | `ON` / `OFF` | Mide el plano en las 4 esquinas del área confocal y corrige $Z(x,y)$ en vivo. |
| **`Scan pre-print?`** | `QCheckBox` | `ON` / `OFF` | Habilita escaneo confocal de verificación previa en cada nodo. |
| **`Set reference`** | `QPushButton` | Exec | Congela las coordenadas capacitivas actuales de la PI como $(X_0, Y_0, Z_0)$. |
| **`PRINTING folder`** | `QPushButton` | Exec | Crea la carpeta fechada `YYYYMMDD-HHMMSS_Printing_<GridName>` en disco. |
| **`Play ►`** | `QPushButton` | Exec | Inicia el motor secuencial de impresión de la grilla. |

---

## 5. Salida de Datos en Disco y Verificación Metrológica

Al finalizar la impresión, la carpeta del lote experimental contendrá:

1. **`NP_00i.txt`**: Trazas temporales de intensidad por nodo a $10\ \text{kHz}$ conteniendo 3 columnas: `Tiempo (s)`, `Señal Fotodiodo (V)`, `Potencia BS (V)`. Incluye encabezado con estado metrológico (`SUCCESS (Primary Pass)` o `SUCCESS (Healing Pass - Retry)`).
2. **`NPscan_00i.tiff`**: Escaneos confocales 2D de las partículas impresas (si `Scan pre-print?` estaba activo).
3. **`printing_error_timestamp.txt`**: Matriz de residuos de posicionamiento en nanómetros $(\Delta x_{\text{nm}}, \Delta y_{\text{nm}})$ entre el centroide real y la coordenada teórica.
4. **`grid_info.txt`**: Resumen completo de metadatos (Láser, Criterio, Umbrales, Potencia BFP, Sustrato, Estado de Healing Pass y Comentarios).
5. **`drift_tracking_xy.txt` / `drift_tracking_z.txt`**: Historial numérico de deriva con velocidades instantáneas.
6. **`reporte_parametros_<nombre_red>.txt`**: Informe estadístico Time-Volt con cinética de adhesión, desglose de pases primario y Healing Pass, y tasa de éxito global consolidada.

---

## 6. Documentación Relacionada y Red de Reportes

- **Manual Principal de Usuario**: [Manual de Usuario PyPrinting 3.0 (docs/MANUAL_USUARIO.md)](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/docs/MANUAL_USUARIO.md)
- **Compendio Teórico**: [Fundamentos Físicos & Nanomateriales (Módulo 00)](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/docs/modulos/00_Fundamentos_Fisicos_Optical_Printing_y_Nanomateriales.md)
- **Reportes Técnicos Vinculados**:
  - 📐 [Diseño y Generación de Redes Cristalinas 2D](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/reportes/cientificos/Diseno_y_Generacion_de_Redes_Cristalinas_2D_PyPrinting3.md)
  - 📍 [Corrección de Deriva Termomecánica por Partícula Ancla](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/reportes/cientificos/Correccion_de_Deriva_Termomecanica_Drift_Correction_PyPrinting3.md)
  - 🧠 [Control Adaptativo de Frecuencia de Autofoco y Deriva](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/reportes/cientificos/Control_Adaptativo_de_Frecuencia_de_Autofoco_y_Deriva_PyPrinting3.md)
  - 📊 [Análisis Time-Volt y Tracking Avanzado](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/reportes/cientificos/Analisis_Time_Volt_y_Tracking_Avanzado_PyPrinting3.md)
  - 🧮 [Algoritmo de Parada e Impresión de Grillas y Dímeros](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/reportes/cientificos/Algoritmo_Printing_y_Dimers_PyPrinting3.md)
  - 📊 [Incertidumbre Metrológica ISO/GUM](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/reportes/cientificos/Incertidumbre_Metrologica_PyPrinting3.md)
