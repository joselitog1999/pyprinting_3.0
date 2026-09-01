# 📐 Módulo 11: Diseñador Universal de Redes Cristalinas 2D (`grid_generator.py`)

**Suite PyPrinting 3.0 — Laboratorio de Nanofotónica (INS-UNSAM / CONICET)**  
*Documento de Referencia Técnica y Manual Operativo N° 11*  
*Autor: José Luis González Peñafiel (Becario Doctoral CONICET)*  
*Ubicación*: `docs/modulos/11_Disenador_Redes_2D_Grid_Generator.md`

---

## 📖 Índice del Manual
1. [Visión General y Propósito del Módulo](#1-visión-general-y-propósito-del-módulo)
2. [Maqueta Visual de la Interfaz de Usuario (ASCII Layout)](#2-maqueta-visual-de-la-interfaz-de-usuario-ascii-layout)
3. [Catálogo Exhaustivo de Controles y Parámetros por Panel](#3-catálogo-exhaustivo-de-controles-y-parámetros-por-panel)
   - 3.1 Pestaña 1: Capas Cristalográficas y Base Atómica
   - 3.2 Pestaña 2: Geometría Contenedora (Máscaras de Recorte)
   - 3.3 Pestaña 3: Partícula Ancla ($P_0$) & Cuadratura Multi-Paso
   - 3.4 Pestaña 4: Estrategia de Recorrido de la Platina PI
   - 3.5 Panel Izquierdo Inferior: Visualizador de la Celda Unidad en Tiempo Real
   - 3.6 Panel Derecho: Visualizador 2D `pyqtgraph`, Modos de Trayectoria y Telemetría
4. [Catálogo Cristalográfico de las 15 Redes 2D Soportadas](#4-catálogo-cristalográfico-de-las-15-redes-2d-soportadas)
5. [Restricción Física de Distancia Mínima de Impresión ($d_{\text{min}}$)](#5-restricción-física-de-distancia-mínima-de-impresión-d_min)
6. [Formato de Archivos y Generación de Recetas Multi-Paso](#6-formato-de-archivos-y-generación-de-recetas-multi-paso)
   - 6.1 Archivo `.txt` Unificado para `Measurements`
   - 6.2 Paquete Multi-Paso con Metadatos JSON
7. [Protocolo de Operación Paso a Paso (Guía Rápida para el Operador)](#7-protocolo-de-operación-paso-a-paso-guía-rápida-para-el-operador)

---

## 1. Visión General y Propósito del Módulo

El **Diseñador Universal de Redes Cristalinas 2D** (`grid_generator.py`) es una aplicación visual y un motor cristalográfico analítico diseñado para sintetizar **cualquier arreglo periódico 2D de nanopartículas coloidales** para su nanofabricación óptica secuencial en PyPrinting 3.0.

### Capacidades Principales:
1. **Generación Cristalográfica Universal**: Permite parametrizar las 5 redes de Bravais 2D clásicas y más de 10 redes complejas de interés en física cuántica y metamateriales (Grafeno, Kagome, Lieb, Dice, TMD $\text{MoS}_2$, etc.).
2. **Control Paramétrico Total**: Vectores primitivos $\mathbf{a}_1$ y $\mathbf{a}_2$ independientes, ángulo $\gamma$ ajustable mediante deslizador interactivo ($5^\circ - 175^\circ$), y posiciones atómicas fraccionales $(u_j, v_j)$ libremente desplazables para simular deformaciones (strain), dimerizaciones o superredes.
3. **Restricción Física de Exclusión ($d_{\text{min}}$)**: Filtra automáticamente partículas candidatas cuya distancia mutua sea inferior al límite de resolución óptica o de coalescencia térmica ($< d_{\text{min}}$).
4. **Soporte Multimaterial y Multi-Paso**: Permite asignar hasta 3 tipos de nanopartículas (e.g., Au 60nm, Ag 40nm, Au 100nm) a diferentes átomos de la celda o capas sobrepuestas, exportando automáticamente recetas multi-paso con registro espacial estricto mediante **Partícula Ancla ($P_0$)**.
5. **Optimización de Trayectoria de Platina PI**: Algoritmos de ordenamiento (Snake, Espiral, TSP) para minimizar la fatiga mecánica y la acumulación de deriva durante la impresión.

---

## 2. Maqueta Visual de la Interfaz de Usuario (ASCII Layout)

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 📐 Diseñador Universal de Redes Cristalinas 2D — PyPrinting 3.0                                            │
├──────────────────────────────────────────────┬──────────────────────────────────────────────────────────────┤
│ 📚 Presets: [ 🐝 Grafeno en Disco (R=5.0) ▼] │ 🌐 Vista: [ ✨ Rutas Separadas ▼] [x] Trayectoria [ ] Núm    │
├──────────────────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ ┌── Pestañas de Parámetros ────────────────┐ │ ┌── Lienzo Gráfico 2D Interactivo (pyqtgraph) ─────────────┐ │
│ │ 🔹 Capas │ 📐 Geometría │ ⭐ Ancla │ 🛤️ │ │ │  y(µm) ▲                                                │ │
│ ├──────────────────────────────────────────┤ │ │        │            · · · · ·                              │ │
│ │ Capa: [ Capa 1 (Primaria) ▼] [x] Habilit │ │ │        │          ·   🟢     ·                             │ │
│ │ Red:  [ Grafeno / Honeycomb (2 átom)  ▼] │ │ │        │        ·   🔷   🔷   ·                            │ │
│ │ a₁ (a): [ 2.500] µm  a₂ (b): [ 2.500] µm │ │ │        │       ·  🟢   P0⭐  🟢 ·                          │ │
│ │ Ángulo γ: [ 60.0]°  ══════[●]═══════════ │ │ │        │        ·   🔷   🔷   ·                            │ │
│ │ Distancia Mínima d_min: [ 0.500] µm      │ │ │        │          ·   🟢     ·                             │ │
│ │ ┌── ⚛️ Base Atómica (2 átomos) ────────┐ │ │ │        │            · · · · ·                              │ │
│ │ │ A1: u:[ 0.000] v:[ 0.000] [Mat 1-Au▼]│ │ │ │   ───┼─────────────────────────────────────────► x(µm) │ │
│ │ │ A2: u:[ 0.333] v:[ 0.667] [Mat 2-Ag▼]│ │ │ │      -8             0              +8                     │ │
│ │ │ [ ➕ Añadir ] [ ➖ Quitar ] [ 🔄 Res ] │ │ │ └────────────────────────────────────────────────────────┘ │
│ │ └──────────────────────────────────────┘ │ │ ┌── Telemetría Dinámica de Impresión ──────────────────────┐ │
│ │ Rotación θ: [ 0.0]°  OffX:[0.0] OffY:[0] │ │ │ N Total: 34 (con Ancla P0⭐) | Mat 1: 17 | Mat 2: 17       │ │
│ └──────────────────────────────────────────┘ │ │ Dim: 8.66 × 8.66 µm | Trayectoria Paso 1: 0.284 mm (17 n) │ │
│ ┌── 🔬 Celda Unidad de la Capa Activa ─────┐ │ └────────────────────────────────────────────────────────────┘ │
│ │    a2 ▲ 🟢 A2 (0.33, 0.67)               │                                                                │
│ │       │  · · · · · ┐                     │                                                                │
│ │       └──🔷 A1 ────► a1  (a=2.5, b=2.5)  │                                                                │
│ └──────────────────────────────────────────┘                                                                │
│ ┌── 💾 Exportación ────────────────────────┐                                                                │
│ │ Lote: [ Graphene_Bicolor_Disk_R5um     ] │                                                                │
│ │ [ 💾 Exportar .txt Unificado           ] │                                                                │
│ │ [ 📦 Paquete Receta Multi-Paso (P0)    ] │                                                                │
│ └──────────────────────────────────────────┘                                                                │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Catálogo Exhaustivo de Controles y Parámetros por Panel

### 3.1 Pestaña 1: Capas Cristalográficas y Base Atómica

| Control / Widget | Tipo | Rango / Opciones | Descripción y Comportamiento Físico |
| :--- | :---: | :---: | :--- |
| **`Capa Activa`** | `QComboBox` | Capa 1, Capa 2, Capa 3 | Selecciona la capa cristalográfica que se está editando. Permite superponer hasta 3 redes independientes para formar superredes Moiré. |
| **`Habilitada`** | `QCheckBox` | Checked / Unchecked | Incluye o excluye los nodos de esta capa en la síntesis final del cristal. |
| **`Tipo de Red`** | `QComboBox` | 15 tipos de red | Carga los parámetros canónicos y la base de átomos estándar (ver Tabla en Sección 4). |
| **`Vector a₁ (a µm)`** | `QDoubleSpinBox`| $0.100 - 50.000\ \mu\text{m}$ | Longitud física $|\mathbf{a}_1| = a$ del primer vector de red primitivo. |
| **`Vector a₂ (b µm)`** | `QDoubleSpinBox`| $0.100 - 50.000\ \mu\text{m}$ | Longitud física $|\mathbf{a}_2| = b$ del segundo vector de red primitivo. |
| **`Ángulo γ (°)`** | `QDoubleSpinBox`| $5.0^\circ - 175.0^\circ$ | Ángulo geométrico entre $\mathbf{a}_1$ y $\mathbf{a}_2$. Sincronizado bidireccionalmente con el deslizador. |
| **`Deslizador γ`** | `QSlider` | $50 - 1750$ ($0.1^\circ$ res) | Permite arrastrar suavemente el ángulo intervectorial para observar la deformación en vivo de la celda y la red. |
| **`Distancia Mínima d_min`**| `QDoubleSpinBox`| $0.000 - 25.000\ \mu\text{m}$ | Límite físico de exclusión: descarta partículas a distancia $< d_{\text{min}}$ de cualquier otra ya existente. Si es `0.0`, está desactivada. |
| **`Coordenada u (A_j)`** | `QDoubleSpinBox`| $-2.0000 - 2.0000$ | Coordenada fraccional a lo largo de $\mathbf{a}_1$ ($\mathbf{r}_j = u_j \mathbf{a}_1 + v_j \mathbf{a}_2$). |
| **`Coordenada v (A_j)`** | `QDoubleSpinBox`| $-2.0000 - 2.0000$ | Coordenada fraccional a lo largo de $\mathbf{a}_2$. |
| **`Material Asignado (A_j)`**| `QComboBox` | Material 1, 2, 3 | Asigna el tipo de nanopartícula coloidal (Material 1 = Cian/Au 60nm, Material 2 = Verde/Ag 40nm, Material 3 = Rosa/Au 100nm). |
| **`➕ Añadir Átomo`** | `QPushButton` | — | Añade un nuevo átomo a la base de la celda unidad (hasta 6 átomos por celda). |
| **`➖ Quitar Átomo`** | `QPushButton` | — | Elimina el último átomo de la base (mínimo 1 átomo). |
| **`🔄 Resetear Base`** | `QPushButton` | — | Restaura la base canónica ideal correspondiente al tipo de red seleccionado. |
| **`Rotación θ (°)`** | `QDoubleSpinBox`| $-360.0^\circ - 360.0^\circ$| Aplica una rotación de cuerpo rígido a la capa completa alrededor del origen $(0,0)$ para generar patrones Moiré. |
| **`Offset X / Y (µm)`** | `QDoubleSpinBox`| $-100.0 - 100.0\ \mu\text{m}$ | Desplaza la capa completa $(\Delta x, \Delta y)$ respecto al origen. |

---

### 3.2 Pestaña 2: Geometría Contenedora (Máscaras de Recorte)

Define los límites físicos exteriores del cristal periódico:

1. **Hexágono Regular por Apotema ($a_p$)**:
   - Delimita el cristal dentro de un hexágono con distancia centro-lado $a_p$ en $\mu\text{m}$.
   - Condición analítica: $|y| \le a_p \land |0.5 y \pm \frac{\sqrt{3}}{2}x| \le a_p$.
2. **Hexágono Regular por Radio Exterior ($R$)**:
   - Delimita por el radio circunscrito ($a_p = R \frac{\sqrt{3}}{2}$).
3. **Círculo / Disco ($R$)**:
   - Condición analítica: $x^2 + y^2 \le R^2$.
4. **Rectángulo / Cuadrado ($L_x, L_y$)**:
   - Condición analítica: $|x| \le L_x/2 \land |y| \le L_y/2$.
5. **Corona Circular / Anillo ($R_{\text{in}}, R_{\text{out}}$)**:
   - Condición analítica: $R_{\text{in}}^2 \le x^2 + y^2 \le R_{\text{out}}^2$.
6. **Triángulo Equilátero ($L$)**:
   - Delimita el cristal dentro de un triángulo equilátero de lado $L$.
7. **Celdas Unidad ($N_x \times N_y$)**:
   - Sin recorte analítico; genera exactamente $N_x$ celdas a lo largo de $\mathbf{a}_1$ y $N_y$ celdas a lo largo de $\mathbf{a}_2$.

---

### 3.3 Pestaña 3: Partícula Ancla ($P_0$) & Cuadratura Multi-Paso

La **Partícula Ancla ($P_0$)** es el elemento más crítico para la nanofabricación en multi-paso (impresión secuencial con diferentes coloides o en días distintos):

- **`Habilitar Partícula Ancla (P0)`**: Inserta una partícula de referencia óptica que se imprime en la posición número 0.
- **Modos de Ubicación de $P_0$**:
  - **`Offset Exterior (Seguridad)`**: Ubica $P_0$ fuera del cristal periódico a una distancia segura $(\Delta X_0, \Delta Y_0)$ de la esquina inferior izquierda. *Recomendado para no alterar la simetría del cristal.*
  - **`Centro Geométrico (0,0)`**: Ubica $P_0$ en el origen exacto del cristal.
  - **`Primer Nodo de la Red`**: Utiliza el primer átomo del cristal como ancla de referencia.
  - **`Coordenada Personalizada`**: Permite ingresar $(X_0, Y_0)$ manuales.

---

### 3.4 Pestaña 4: Estrategia de Recorrido de la Platina PI

| Algoritmo | Comportamiento del Recorrido | Beneficio Experimental |
| :--- | :--- | :--- |
| **`Serpiente / Zig-Zag`** *(Recomendado)* | Ordena los nodos en filas alternadas ($\rightarrow, \leftarrow, \rightarrow$). | Minimiza los saltos diagonales largos de la platina piezoeléctrica PI, reduciendo la histéresis y la acumulación de deriva térmica. |
| **`Espiral`** | Recorre los nodos desde el centro geométrico hacia el borde exterior. | Ideal para estructuras circulares o discos, asegurando que el centro quede impreso antes de que ocurra deriva. |
| **`TSP Euclidiano`** | Algoritmo del Viajante (Vecino más cercano). | Minimiza la distancia total de recorrido en milímetros ($\sum d_i$). |
| **`Sin Ordenar`** | Orden natural de generación $(n_1, n_2)$. | Para pruebas sintéticas. |

---

### 3.5 Panel Izquierdo Inferior: Visualizador de la Celda Unidad

Muestra un gráfico en tiempo real de la celda unidad microscópica:
- **Línea Discontinua Dorada**: Perímetro del paralelogramo delimitado por $(0,0) \to \mathbf{a}_1 \to \mathbf{a}_1+\mathbf{a}_2 \to \mathbf{a}_2 \to (0,0)$.
- **Flechas Primitivas**: Vector $\mathbf{a}_1$ (azul cian) y Vector $\mathbf{a}_2$ (verde) con sus etiquetas $a_1, a_2$.
- **Átomos de la Base**: Dibuja cada átomo $A_j$ con el color de su material asignado y etiqueta de coordenadas $(u_j, v_j)$.
- **Telemetría de Celda**: Muestra $a$, $b$, $\gamma$ y la lista completa de átomos y materiales en tiempo real.

---

### 3.6 Panel Derecho: Visualizador 2D, Modos de Trayectoria y Telemetría

- **Selector de Vista de Trayectoria**:
  - `🌐 Todas las Capas (Trayectoria Global)`: Muestra todos los nodos y la ruta continua total.
  - `✨ Rutas Multi-Paso Separadas`: Dibuja una línea de color diferente para cada material saliendo desde $P_0$.
  - `🔷 Solo Paso 1 (Material 1)`: Resalta únicamente los nodos del Material 1 y atenúa el resto.
  - `🟢 Solo Paso 2 (Material 2)`: Resalta únicamente los nodos del Material 2.
  - `🌸 Solo Paso 3 (Material 3)`: Resalta únicamente los nodos del Material 3.
- **Casilla `🔢 Números de Orden`**: Muestra sobre cada nodo su número de secuencia de impresión $(1, 2, 3\dots)$.
- **Barra de Telemetría Dinámica**:
  - `N Total`: Cantidad total de partículas a imprimir (indicando si incluye $P_0$ ⭐).
  - `⚠️ Excluidos por d_min`: Muestra cuántas partículas candidatas fueron descartadas por violar el límite de distancia mínima.
  - `Mat 1 / Mat 2 / Mat 3`: Conteo individual por material.
  - `Dim X × Y`: Dimensiones físicas del cristal en $\mu\text{m}$.
  - `Longitud de Trayectoria`: Distancia total de desplazamiento de la platina en $\text{mm}$.

---

## 4. Catálogo Cristalográfico de las 15 Redes 2D Soportadas

| N° | Tipo de Red | Base Canónica $(u_j, v_j)$ | Ángulo $\gamma$ | Propiedades Físicas y Aplicaciones |
|:---:|---|---|:---:|---|
| **1** | **Hexagonal / Triangular** | $A_1=(0,0)$ | $60.0^\circ$ | Red compacta estándar de máxima densidad. |
| **2** | **Cuadrada (Square 90°)** | $A_1=(0,0)$ | $90.0^\circ$ | Red cuadrada de 4 ejes de simetría. |
| **3** | **Grafeno / Honeycomb** | $C_1=(0,0), C_2=(1/3, 2/3)$ | $60.0^\circ$ | 2 subredes triangulares entrelazadas. Conos de Dirac fotónicos. |
| **4** | **Nitruro de Boro (h-BN)** | $B=(0,0) \text{ [M1]}, N=(1/3, 2/3) \text{ [M2]}$ | $60.0^\circ$ | Red hexagonal con inversión de simetría rota (gap óptico). |
| **5** | **Red Kagome** | $K_1=(0,0), K_2=(1/2, 0), K_3=(0, 1/2)$ | $60.0^\circ$ | Triángulos por vértices compartidos. Bandas planas y frustración. |
| **6** | **Red de Lieb** | $L_1=(0,0), L_2=(1/2, 0), L_3=(0, 1/2)$ | $90.0^\circ$ | Vértices y centros de aristas de un cuadrado. Banda plana exacta. |
| **7** | **Red de Dice / $T_3$** | $D_1=(0,0), D_2=(1/3, 2/3), D_3=(2/3, 1/3)$ | $60.0^\circ$ | Hub central con coordinación 6 + orbitales. Fermiones de pseudospin-1. |
| **8** | **Monocapa TMD ($\text{MoS}_2$)**| $Mo=(0,0), S_1=(1/3, 2/3), S_2=(2/3, 1/3)$ | $60.0^\circ$ | Metamateriales dicalcogenuros de metales de transición. |
| **9** | **Cuadrada Centrada** | $C_1=(0,0), C_2=(1/2, 1/2)$ | $90.0^\circ$ | Red tipo tablero de ajedrez (Checkerboard). |
| **10**| **Rectangular Centrada**| $R_1=(0,0), R_2=(1/2, 1/2)$ | $90.0^\circ$ | Red birrefringente anisótropa con $a \ne b$. |
| **11**| **Triangular Decorada** | $D_1=(0,0), D_2=(1/2, 1/2)$ | $60.0^\circ$ | Superred hexagonal con sitios intersticiales. |
| **12**| **Rectangular Simple** | $A_1=(0,0)$ | $90.0^\circ$ | Red rectangular primitiva ($a \ne b$). |
| **13**| **Rómbica / Inclinada** | $A_1=(0,0)$ | $\gamma \ne 90^\circ$ | Red centrada con $a=b$. |
| **14**| **Oblicua General** | $A_1=(0,0)$ | $\gamma \ne 90^\circ$ | Red de menor simetría ($a \ne b, \gamma \ne 90^\circ$). |
| **15**| **Personalizada / Libre** | $1 \text{ a } 6 \text{ átomos configurables}$ | Libre | Diseños experimentales arbitrarios y metamoléculas. |

---

## 5. Restricción Física de Distancia Mínima de Impresión ($d_{\text{min}}$)

En nanolitografía óptica de nanopartículas coloidales, cuando dos partículas se imprimen a una distancia mutua inferior a la cintura del haz focal ($d < w_0 \approx 250\ \text{nm}$):
1. La segunda partícula es atraída hacia la primera por fuerzas de gradiente óptico y fuerzas térmicas de acoplamiento, provocando **coalescencia o desalineación**.
2. La absorción simultánea de ambas partículas puede superar el umbral de cavitación generando microburbujas.

```
       Partícula 1               Distancia d < d_min           Candidata Partícula 2
      ┌───────────┐                 ◄─────────►                 ┌───────────┐
      │   AuNP    │                 ░░░░░░░░░░░                 │   AuNP    │
      │  (Fijada) │                 ░ COLISIÓN ░                │(DESCARTADA│
      └───────────┘                 ░░░░░░░░░░░                 └───────────┘
```

El parámetro **`Distancia Mínima d_min (µm)`**:
- Evalúa la distancia euclídea $d = \sqrt{(x_i - x_j)^2 + (y_i - y_j)^2}$ entre todo par de partículas.
- Descarta automáticamente cualquier partícula que quede a una distancia $d < d_{\text{min}}$ de otra ya aceptada.
- Funciona de forma **universal sin importar el material** (compara partículas de la misma capa o de capas diferentes sobrepuestas).

---

## 6. Formato de Archivos y Generación de Recetas Multi-Paso

### 6.1 Archivo `.txt` Unificado para `Measurements`

El botón **`💾 Exportar .txt Unificado`** genera un archivo de texto estándar de dos columnas delimitadas por tabulador listo para cargar en la ventana de **Measurements** (`modules/measurements.py`):

```text
# PyPrinting 3.0 - Grid Recipe File
# Batch: Graphene_Lattice_Disk_R5um
# Date: 2026-09-01 10:30:00
# Total targets: 25
# X_um	Y_um
-4.3300	-2.5000
-4.3300	0.0000
-2.1650	-3.7500
-2.1650	-1.2500
0.0000	-2.5000
0.0000	0.0000
...
```

---

### 6.2 Paquete Multi-Paso con Metadatos JSON

El botón **`📦 Paquete Receta Multi-Paso (P0)`** detecta automáticamente cuántos materiales distintos existen en la red y crea una carpeta estructurada con archivos independientes para cada pase de impresión:

```
📁 Graphene_Bicolor_Package/
├── 📄 Pass1_Material_1_ref_P0.txt    <-- Archivo para Coloide 1 (Au 60nm)
├── 📄 Pass2_Material_2_ref_P0.txt    <-- Archivo para Coloide 2 (Ag 40nm)
├── 📄 Full_Grid_Unified.txt          <-- Estructura completa de referencia
└── 📑 Recipe_Metadata.json           <-- Metadatos de cuadratura y hardware
```

#### Estructura de cada archivo de pase (`Pass1_Material_1_ref_P0.txt`):
La primera fila contiene estrictamente las coordenadas de la **Partícula Ancla $P_0$**:

```text
# PyPrinting 3.0 - Multi-Pass Sub-Recipe
# Material ID: 1 (Au 60nm)
# Pass: 1 of 2
# Node 0 (Row 1) is Anchor Particle P0
# X_um	Y_um
-6.5000	-6.5000    <-- PARTÍCULA ANCLA P0 (Nodo 0)
-4.3300	-2.5000    <-- Primer nodo del Material 1
-2.1650	-3.7500
0.0000	-2.5000
...
```

#### Archivo de Metadatos (`Recipe_Metadata.json`):
```json
{
  "generator": "PyPrinting 3.0 Grid Designer",
  "batch_name": "Graphene_Bicolor_Disk_R5um",
  "has_anchor": true,
  "anchor_coords_um": [-6.5, -6.5],
  "materials_present": [1, 2],
  "total_nodes": 34,
  "min_distance_um": 0.5,
  "bounding_shape": "circle",
  "bounding_params": {"radius": 5.0},
  "passes": {
    "1": {"material_id": 1, "material_name": "Material 1 (Au 60nm)", "nodes_count": 17, "path_length_mm": 0.284},
    "2": {"material_id": 2, "material_name": "Material 2 (Ag 40nm)", "nodes_count": 17, "path_length_mm": 0.284}
  }
}
```

---

## 7. Protocolo de Operación Paso a Paso

1. **Seleccionar o Crear la Red**:
   - Elegir un preset en la barra superior o seleccionar el `Tipo de Red` (e.g. *Grafeno*).
   - Ajustar los espaciamientos $a$ y $b$ en $\mu\text{m}$.
   - Arrastrar el deslizador de ángulo $\gamma$ si se desea deformar la celda.
2. **Configurar los Materiales de la Base**:
   - En el panel `⚛️ Base Atómica`, elegir si cada átomo ($A_1, A_2\dots$) tiene el mismo material o materiales diferentes.
   - Ajustar las coordenadas fraccionales $(u, v)$ si se desea desplazar algún átomo.
3. **Fijar la Restricción $d_{\text{min}}$**:
   - Colocar `Distancia Mínima d_min` en $0.4\ \mu\text{m}$ (o el límite óptico deseado) para evitar que partículas sobrepuestas colisionen.
4. **Definir la Máscara y la Partícula Ancla**:
   - En la pestaña `Geometría`, seleccionar la figura (e.g. *Círculo de radio 5.0 µm*).
   - En la pestaña `Partícula Ancla`, verificar que esté habilitada con `Offset Exterior`.
5. **Exportar la Receta**:
   - Escribir el nombre del lote en `Nombre Lote`.
   - Si la red es de un solo material: hacer clic en **`💾 Exportar .txt Unificado`**.
   - Si la red es multi-material: hacer clic en **`📦 Paquete Receta Multi-Paso (P0)`**.
6. **Cargar en Measurements para Impresión**:
   - Abrir `Measurements` en PyPrinting 3.0 (`Ctrl+M`).
   - Cargar el archivo `.txt` con el botón `Load grid` y comenzar la nanofabricación.
