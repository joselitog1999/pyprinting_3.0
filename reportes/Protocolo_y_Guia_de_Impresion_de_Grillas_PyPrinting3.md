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
1. Ejecutar el lanzador principal `main.py` o presionar el acceso directo **`🚀 Iniciar Microscopio Derecho (app.py)`**.
2. En la barra superior de menús, ir a **`Files` $\rightarrow$ `Create Daily Dir (Ctrl+S)`**.
3. Seleccionar la carpeta raíz de trabajo (ej. `C:/Data`). El sistema creará automáticamente la subcarpeta del día con formato `YYYY-MM-DD` (ej. `C:/Data/2026-08-06`).

---

### Paso 2: Acomodación Óptica Manual y Enfoque en Vidrio
1. En el dock **`Shutters / Flipper / Láser 532`**, seleccionar la línea láser de excitación (ej. `532 nm`).
2. Ajustar el atenuador de potencia a **`Low Power`** y posteriormente buscar una zona ideal para impresion de forma manual.
3. Mediante el micrométrico manual del objetivo y la cámara réflex Live View (`camera.py`), enfocar nítidamente la superficie del sustrato de vidrio.
4. Una vez identificada la zona, ajustar el atenuador de potencia a **`High Power`** para lograr la intensidad necesaria de presión de radiación para realizar la impresion.

---

### Paso 3: Escaneo Confocal y Centrado de Partícula
1. En el dock **`Confocal`**, configurar el área de escaneo (ej. `Range x/y` = $5.0\ \mu\text{m}$, `Pixels x/y` = $100 \times 100$).
2. Presionar **`Start Scan`** para registrar la imagen confocal 2D de la nanopartícula de referencia.
3. Seleccionar el método de centrado analítico `method_center` = `center of mass` o `center of gauss`.
4. Con la casilla **`Auto CM`** marcada, el sistema moverá automáticamente la platina piezoeléctrica PI al centroide exacto de la partícula.

---

### Paso 4: Ajuste Axial Z (`Go to maximum`) y Congelado de Referencia (`Lock focus`)
1. En el dock **`Focus z`**, presionar **`Go to maximum (F8)`**. La platina ejecutará un barrido rápido en $Z$ y se ubicará en la cima de máxima fotoluminiscencia.
2. Repetir el paso 3 y el paso 4.1 hasta obtener un buen centrado de la partícula y máximo fotoluminiscencia.
3. En el dock **`Nanopositioning`**, desplazar lateralmente la platina $\approx 2.0\ \mu\text{m}$ en $X$ hacia una zona de vidrio limpio libre de partículas.
4. Presionar **`Lock Focus (F9)`** para registrar el perfil axial de referencia $I_{\text{ref}}(z)$ de la interfaz sustrato-solución.
5. Regresar la platina a la coordenada central de la partícula en $X$ e $Y$.
6. Asegurarse de que el atenuador de potencia se encuentre en **`High Power`** pero el obturador cerrado, de modo que el sistema este listo para depositar una particula.

---

### Paso 5: Apertura de la Ventana `Printing` y Fijado de Origen (`Set reference`)
1. En el menú superior, seleccionar **`Measurements` $\rightarrow$ `Printing`**. Se desplegará la ventana modular `Frontend` de impresión.
2. Presionar el botón naranja **`Set reference`**:
   - El sistema leerá inmediatamente las coordenadas capacitivas reales de la platina PI ($X_0, Y_0, Z_0$) y las mostrará en las etiquetas `X ref`, `Y ref`, `Z ref`.
   - Todas las posiciones futuras de la grilla se calcularán relativas a este punto origen.

---

### Paso 6: Configuracion del Focus shift & drift
1. En la pestaña **`Focus drift`**, configurar los parámetros de impresión. Los parámetros son:
- **`Autofocus every N`**: Indica cada cuántas nanopartículas se realizará un autofocus. Por ejemplo, si se establece en 5, se realizará un autofocus después de imprimir la 5ª, 10ª, 15ª nanopartícula, etc.
- **`Shift x/y (um)`**: Desplazamiento lateral para garantizar una zona vacia donde ejecutar autofoco. Recomendable 2 um
- **`Drift Correction`**: Activa o desactiva la corrección de deriva por partícula ancla. Cambia la posicion de P0 como particula in-array o particula de referencia.
- **`Start X/Y (um)`**: Posicion inicial de la grilla de impresion con respecto a P0. Recomendable 2 um

---

### Paso 7: Generación o Carga de la Grilla de Posiciones
- **Opción A: Generar Grilla Regular (`Create grid`)**:
  1. En la pestaña **`Grid`**, ingresar:
     - **`NPs/col`**: Cantidad de nanopartículas por columna (ej. `4`).
     - **`Columns`**: Cantidad de columnas (ej. `4`).
     - **`Dist NP (µm)`**: Espaciamiento entre nanopartículas en la misma columna (ej. `3.0`).
     - **`Dist col (µm)`**: Espaciamiento entre columnas (ej. `3.0`).
  2. Presionar **`Create grid`**. El casillero `Total targets` actualizará el conteo (ej. `16`) y desplegará el gráfico 2D de la grilla.

- **Opción B: Cargar Grilla Personalizada (`Load grid (.txt)`)**:
  1. Presionar **`Load grid (.txt)`** y seleccionar un archivo `.txt` conteniendo 2 columnas $(X, Y)$ en micrómetros.

---

### Paso 8: Creación de la Carpeta del Lote Experimental (`PRINTING folder`)
1. Presionar el botón **`PRINTING folder`**.
2. El sistema creará automáticamente una subcarpeta fechada con el nombre de la grilla en el directorio del día:
   `C:/Data/2026-08-06/20260806-120000_Printing_4x4_3umx3um/`
3. El indicador se tornará **verde** mostrando la ruta del lote activo.
4. Llenar Extra info (opcional) con informacion relevante del experimento.

---

### Paso 9: Configuración del Criterio de Parada y Parámetros
Seleccionar el algoritmo deseado en el desplegable **`Criterio Parada`**:

| Modo de Parada | Nombre en UI | Cuándo Utilizarlo | Parámetros a Configurar |
|---|---|---|---|
| **Modo 0** | `Legacy (Salto Relativo Estándar)` | Impresiones estándar con alto contraste de dispersión. | `Umbral` ($1.20$), `T max (s)` ($20$), `Steps before/after`. |
| **Modo 1** | `Salto Relativo + Umbral Absoluto & Anti-Paso` | Evita falsos disparos por nanopartículas flotantes de paso. | `Umbral`, `Umbral Abs (V)` ($2.5\text{ V}$), `N hold steps` ($5$). |
| **Modo 2** | `Derivada Temporal dI/dt & Aplanamiento` | Detención inmediata al alcanzar la meseta fototérmica post-pico. | `Slope Min` ($15\text{ V/s}$), `Slope Flat` ($2\text{ V/s}$). |
| **Modo 3** | `Calibración Confocal Raw & Reescalado` | Calibración fotométrica absoluta sobre la señal de vidrio. | `Ratio K (P/S)` ($10$), `Umbral (%)` ($50\%$). |
| **Modo 4** | `Criterio Híbrido Tri-Factor (All-In-One)` | Máxima precisión metrológica y triple verificación. | Todos los parámetros activos. |

---

### Paso 9: Ejecución de la Impresión Automatizada (`Play ►`)
1. Presionar el botón **`Play ►`**.
2. El sistema ejecutará automáticamente la secuencia ciclo a ciclo:
   $$\text{Mover a Nodo } i \longrightarrow \text{Autofoco Z (si corresponde)} \longrightarrow \text{Abrir Shutter \& Grabar Traza} \longrightarrow \text{Detección Parada} \longrightarrow \text{Cerrar Shutter \& Guardar } \texttt{NP\_iii.txt} \longrightarrow \text{Pre-Scan (Opción)} \longrightarrow \text{Mover a } i+1$$
3. Para pausar en cualquier instante, presionar **`Pause`**. Para forzar el salto al siguiente nodo, presionar **`Next index ►`**.

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
| **`Scan pre-print?`** | `QCheckBox` | `ON` / `OFF` | Habilita escaneo confocal de verificación previa en cada nodo. |
| **`Set reference`** | `QPushButton` | Exec | Congela las coordenadas capacitivas actuales de la PI como $(X_0, Y_0, Z_0)$. |
| **`PRINTING folder`** | `QPushButton` | Exec | Crea la carpeta fechada `YYYYMMDD-HHMMSS_Printing_<GridName>` en disco. |
| **`Play ►`** | `QPushButton` | Exec | Inicia el motor secuencial de impresión de la grilla. |

---

## 5. Salida de Datos en Disco y Verificación Metrológica

Al finalizar la impresión, la carpeta del lote experimental contendrá:

1. **`NP_00i.txt`**: Trazas temporales de intensidad por nodo a $10\ \text{kHz}$ conteniendo 3 columnas: `Tiempo (s)`, `Señal Fotodiodo (V)`, `Potencia BS (V)`.
2. **`NPscan_00i.tiff`**: Escaneos confocales 2D de las partículas impresas (si `Scan pre-print?` estaba activo).
3. **`printing_error_timestamp.txt`**: Matriz de residuos de posicionamiento en nanómetros $(\Delta x_{\text{nm}}, \Delta y_{\text{nm}})$ entre el centroide real y la coordenada teórica.
4. **`grid_info.txt`**: Resumen completo de metadatos (Láser, Criterio, Umbrales, Potencia BFP, Sustrato y Comentarios).

---

## 6. Documentación Relacionada y Red de Reportes

- **Manual Principal de Usuario**: [Manual de Usuario PyPrinting 3.0 (docs/MANUAL_USUARIO.md)](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/docs/MANUAL_USUARIO.md)
- **Visión General y Árbol**: [README PyPrinting 3.0 (README.md)](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/README.md)
- **Reportes Técnicos Vinculados**:
  - 📍 [Corrección de Deriva Termomecánica por Partícula Ancla (reportes/Correccion_de_Deriva_Termomecanica_Drift_Correction_PyPrinting3.md)](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/reportes/Correccion_de_Deriva_Termomecanica_Drift_Correction_PyPrinting3.md)
  - 🧮 [Algoritmo de Parada e Impresión de Grillas y Dímeros (reportes/Algoritmo_Printing_y_Dimers_PyPrinting3.md)](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/reportes/Algoritmo_Printing_y_Dimers_PyPrinting3.md)
  - 🔌 [Diagnóstico de Señales y Conexiones (reportes/Diagnostico_de_Senales_y_Conexiones_PyPrinting3.md)](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/reportes/Diagnostico_de_Senales_y_Conexiones_PyPrinting3.md)
  - 📊 [Incertidumbre Metrológica ISO/GUM (reportes/Incertidumbre_Metrologica_PyPrinting3.md)](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/reportes/Incertidumbre_Metrologica_PyPrinting3.md)
