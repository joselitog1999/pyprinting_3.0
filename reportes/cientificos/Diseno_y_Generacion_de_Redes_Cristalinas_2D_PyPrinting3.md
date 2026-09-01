# Síntesis, Geometría y Nanofabricación de Redes Cristalinas 2D con Cuadratura por Partícula Ancla ($P_0$) y Límite Físico de Exclusión ($d_{\text{min}}$) en PyPrinting 3.0

**Autor**: Equipo de Desarrolladores & Investigadores de Nanofotónica (INS-UNSAM / CONICET)  
**Fecha de Publicación**: 1 de Septiembre de 2026  
**Módulos**: [`grid_generator.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/grid_generator.py), [`core/lattice_generator.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/core/lattice_generator.py), [`modules/measurements.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/modules/measurements.py)  
**Versión de Software**: PyPrinting 3.0  
**Ubicación del Reporte**: `reportes/cientificos/Diseno_y_Generacion_de_Redes_Cristalinas_2D_PyPrinting3.md`

---

## 📖 Índice del Reporte
1. [Resumen Ejecutivo y Planteo del Problema](#1-resumen-ejecutivo-y-planteo-del-problema)
2. [Fundamentos Cristalográficos 2D y Catálogo de 15 Familias](#2-fundamentos-cristalográficos-2d-y-catálogo-de-15-familias)
   - 2.1 Formulación Vectorial Irrestricta ($\mathbf{a}_1, \mathbf{a}_2, \gamma$)
   - 2.2 Deslizador Continuo de Ángulo $\gamma$ y Tensor de Deformación (*Strain*)
   - 2.3 Catálogo Completo de Redes de Bravais y Redes Complejas
   - 2.4 Editor Paramétrico de Base Atómica $(u_j, v_j)$ y Asignación Multimaterial
3. [Restricción Física de Exclusión por Distancia Mínima ($d_{\text{min}}$)](#3-restricción-física-de-exclusión-por-distancia-mínima-d_min)
4. [Máscaras Geométricas Analíticas de Delimitación Espacial](#4-máscaras-geométricas-analíticas-de-delimitación-espacial)
5. [Protocolo de Cuadratura Sub-Nanométrica con Partícula Ancla ($P_0$)](#5-protocolo-de-cuadratura-sub-nanométrica-con-partícula-ancla-p_0)
6. [Optimizador de Trayectoria para Platina Piezoeléctrica (PI)](#6-optimizador-de-trayectoria-para-platina-piezoeléctrica-pi)
7. [Guía de Integración y Operación en PyPrinting 3.0](#7-guía-de-integración-y-operación-en-pyprinting-30)

---

## 1. Resumen Ejecutivo y Planteo del Problema

La nanofabricación óptica basada en impresión fototérmica (*optical printing*) permite el posicionamiento espacial de nanoestructuras metálicas y dieléctricas individuales con resolución nanométrica. Para aplicaciones avanzadas en metasuperficies plasmónicas, cristales fotónicos bidimensionales, aisladores topológicos y física de superredes de Moiré, es indispensable generar arreglos geométricos y redes cristalinas 2D arbitrarias con control estricto de:

1. **Cristalografía y Bases Atómicas Universales**: Las 5 redes de Bravais 2D clásicas junto con celdas complejas multimaterial (Grafeno, Nitruro de Boro h-BN, redes de Kagome y Lieb con bandas planas, redes Dice $T_3$, dicalcogenuros $\text{MoS}_2$ y redes centradas).
2. **Control Paramétrico Total y Deformación (*Strain*)**: Longitudes $|\mathbf{a}_1|=a$ y $|\mathbf{a}_2|=b$ independientes y ángulo $\gamma \in [5.0^\circ, 175.0^\circ]$ continuamente ajustable mediante un deslizador interactivo acoplado a un spinbox numérico.
3. **Límite Físico de Exclusión por Distancia Mínima ($d_{\text{min}}$)**: Algoritmo de filtrado espacial que previene colisiones coloidales, coalescencia térmica o cavitación al suprimir automáticamente nodos cuya distancia euclídea mutua sea inferior al límite de resolución óptica ($< d_{\text{min}}$).
4. **Superposición Multicapa y Patrones Moiré**: Coexistencia de múltiples sub-redes con diferentes diámetros/materiales de nanopartículas (e.g., Au 60 nm, Ag 40 nm, Au 100 nm) y rotaciones angulares relativas ($\theta$) para inducir periodicidades gigantes de Moiré.
5. **Delimitación por Figuras Geométricas Reales**: Restricción del cristal a polígonos cerrados de escala micrométrica (e.g., hexágonos de apotema definida $a_p = 5.0\ \mu\text{m}$, discos, triángulos equiláteros o anillos).
6. **Cuadratura y Alineación Multi-Paso mediante Partícula Ancla ($P_0$)**: En procesos de fabricación secuencial (donde se imprime una capa, se lava la celda de fluido, se inyecta un nuevo coloide y se imprime la siguiente capa), la deriva y el cambio físico de celda desalinean el origen. Es obligatorio contar con una **Partícula Ancla de Referencia ($P_0$)** que actúe como hito óptico de recentrado confocal sub-nanométrico.

---

## 2. Fundamentos Cristalográficos 2D y Catálogo de 15 Familias

### 2.1 Formulación Vectorial Irrestricta ($\mathbf{a}_1, \mathbf{a}_2, \gamma$)

Cualquier red cristalina periódica en dos dimensiones queda descrita por el conjunto de vectores de traslación de red $\mathbf{R}_{\mathbf{n}}$:
$$\mathbf{R}_{\mathbf{n}} = n_1 \mathbf{a}_1 + n_2 \mathbf{a}_2, \quad n_1, n_2 \in \mathbb{Z}$$

En el motor cristalográfico [`core/lattice_generator.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/core/lattice_generator.py), los vectores primitivos se definen de forma totalmente paramétrica e independiente:
$$\mathbf{a}_1 = (a, 0), \quad \mathbf{a}_2 = (b \cos\gamma, b \sin\gamma)$$
donde $a = |\mathbf{a}_1|$, $b = |\mathbf{a}_2|$ y $\gamma = \angle(\mathbf{a}_1, \mathbf{a}_2)$.

```
            y ▲                   a2 = (b*cos γ, b*sin γ)
              │                 ▲
              │                /
              │               / 
              │              /  Ángulo γ (5.0° - 175.0°)
              │             / )
              └────────────┴──────────────────────► x
                         (0,0)      a1 = (a, 0)
```

---

### 2.2 Deslizador Continuo de Ángulo $\gamma$ y Tensor de Deformación (*Strain*)

La interfaz gráfica [`grid_generator.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/grid_generator.py) incorpora un control interactivo continuo `QSlider` bidireccionalmente sincronizado con un `QDoubleSpinBox` con resolución de $0.1^\circ$.

Físicamente, alterar $\gamma$ manteniendo $a, b$ fijos equivale a inducir una **deformación por esfuerzo cortante puro (*shear strain*)** en el cristal fotónico. El tensor de deformación infinitesimal $\boldsymbol{\varepsilon}$ asociado a transformar una red ortogonal ($\gamma_0 = 90^\circ$) a un ángulo $\gamma = 90^\circ - \phi$ está dado por:

$$\boldsymbol{\varepsilon} = \begin{pmatrix} \varepsilon_{xx} & \varepsilon_{xy} \\ \varepsilon_{yx} & \varepsilon_{yy} \end{pmatrix} = \begin{pmatrix} 0 & \frac{1}{2}\tan\phi \\ \frac{1}{2}\tan\phi & 0 \end{pmatrix}$$

Esto permite a los investigadores modelar y sintetizar de forma interactiva nanoestructuras sometidas a deformaciones mecánicas artificiales para sintonizar conos de Dirac o bandas planas fotónicas.

---

### 2.3 Catálogo Completo de 15 Redes Soportadas

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

### 2.4 Editor Paramétrico de Base Atómica $(u_j, v_j)$ y Asignación Multimaterial

Para celdas complejas con $M$ partículas en la base ($M \le 6$), la posición de cada átomo $j \in \{1, \dots, M\}$ viene dada por:
$$\mathbf{r}_{\mathbf{n}, j} = \mathbf{R}_{\mathbf{n}} + u_j \mathbf{a}_1 + v_j \mathbf{a}_2, \quad u_j, v_j \in [-2.0, 2.0]$$

Cada átomo cuenta con controles dedicados:
- **Spinners fraccionales $(u_j, v_j)$**: Ajustables a 4 cifras decimales.
- **Selector de Material Coloidal**: Material 1 (Au 60 nm, Cian), Material 2 (Ag 40 nm, Verde) o Material 3 (Au 100 nm, Rosa).
- **Botones Dinámicos**: `[➕ Añadir Átomo]`, `[➖ Quitar Átomo]` y `[🔄 Resetear Base]`.

---

## 3. Restricción Física de Exclusión por Distancia Mínima ($d_{\text{min}}$)

En litografía óptica de nanopartículas coloidales, cuando dos partículas se imprimen a una distancia mutua inferior al radio del haz focal ($d < w_0 \approx 250\ \text{nm}$):
1. Las fuerzas de gradiente óptico y la termoforesis cruzada atraen a la partícula entrante hacia la ya depositada, causando **coalescencia coloidal o defectos de alineación**.
2. La absorción óptica conjunta puede superar el umbral de sobrecalentamiento spinodal ($T > 280\ ^\circ\text{C}$), induciendo **microburbujas de vapor explosivas**.

```
       Partícula A (Fijada)          Distancia d < d_min           Candidata B (Descarta)
      ┌───────────────────┐             ◄─────────►              ┌────────────────────┐
      │  AuNP Aceptada    │             ░░░░░░░░░░░              │  AuNP CANDIDATA    │
      │  Posición (x1,y1) │             ░ COLISIÓN ░             │  (SUPRIMIDA)       │
      └───────────────────┘             ░░░░░░░░░░░              └────────────────────┘
```

### Algoritmo de Exclusión:
El compositor [`CrystalGridComposer`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/core/lattice_generator.py) aplica el siguiente filtro secuencial sobre cada nodo candidato $\mathbf{p}_{\text{cand}}$:

$$\min_{j \in \text{Aceptados}} \|\mathbf{p}_{\text{cand}} - \mathbf{p}_j\| \ge \max(d_{\text{min}}, \epsilon_{\text{col}})$$

donde $\epsilon_{\text{col}} = 80\ \text{nm}$ es la tolerancia numérica básica de colisión y $d_{\text{min}}$ es el umbral físico configurado por el usuario ($0.0 - 25.0\ \mu\text{m}$).

- Si la distancia es menor a $d_{\text{min}}$, el nodo candidato se descarta automáticamente.
- La barra de telemetría de la GUI informa en tiempo real: `⚠️ Excluidos por d_min: K`.

---

## 4. Máscaras Geométricas Analíticas de Delimitación Espacial

El motor evalúa la pertenencia estricta de cada nodo $(\mathbf{r}')$ a la figura geométrica seleccionada:

### 4.1 Hexágono Regular Delimitado por Apotema ($a_p$)
Un hexágono regular horizontal centrado en el origen con apotema $a_p$ queda determinado por la intersección de tres bandas simétricas:
$$|y| \le a_p \quad \land \quad \left| \frac{1}{2}y + \frac{\sqrt{3}}{2}x \right| \le a_p \quad \land \quad \left| \frac{1}{2}y - \frac{\sqrt{3}}{2}x \right| \le a_p$$
El radio exterior del hexágono a sus vértices es $R = \frac{a_p}{\cos 30^\circ} = \frac{2}{\sqrt{3}}a_p$.

### 4.2 Corona Circular / Anillo ($R_{\text{in}} < r \le R_{\text{out}}$)
Permite sintetizar resonadores en anillo o metasuperficies concéntricas:
$$R_{\text{in}}^2 \le x^2 + y^2 \le R_{\text{out}}^2$$

### 4.3 Rectángulo / Caja ($L_x \times L_y$), Disco ($R$) y Triángulo Equilátero ($L$)
- **Rectángulo**: $|x| \le \frac{L_x}{2} \land |y| \le \frac{L_y}{2}$.
- **Disco**: $x^2 + y^2 \le R^2$.
- **Triángulo Equilátero**: $y \ge -\frac{H}{3} \land y \le H - \sqrt{3}|x|$, donde $H = L \frac{\sqrt{3}}{2}$.

---

## 5. Protocolo de Cuadratura Sub-Nanométrica con Partícula Ancla ($P_0$)

```
             ┌────────────────────────────────────────────────────────┐
             │       PROTOCOLO DE FABRICACIÓN MULTI-PASO (P0)         │
             └────────────────────────────────────────────────────────┘

    [Paso 1: Coloide A (Au 60nm)]
         │
         ├──> Platina PI se mueve a P0 (-2 µm, -2 µm)
         ├──> IMPRIME PARTÍCULA ANCLA P0 (Nodo 0) ⭐
         ├──> Imprime Capa 1 completa (Material 1)
         │
    [Intermedio: Lavado y Cambio de Solución]
         │
         ├──> Se retira el líquido de la celda de flujo
         ├──> Se inyecta Coloide B (Ag 40nm)
         │
    [Paso 2: Coloide B (Ag 40nm)]
         │
         ├──> Platina PI se desplaza a las cercanías de P0
         ├──> Escaneo Confocal 2D Centering sobre P0 (Drift Check)
         ├──> Corrección de Origen: Δx, Δy ajustados a cero
         └──> Imprime Capa 2 (Material 2) en perfecta cuadratura con Capa 1
```

### Arquitectura de Exportación Multi-Paso
El botón **`📦 Paquete Receta Multi-Paso (P0)`** genera una estructura de archivos limpia:
1. `Pass1_Material_1_ref_P0.txt`: Contiene $P_0$ en la primera fila como blanco inicial, seguido de todos los nodos del Material 1.
2. `Pass2_Material_2_ref_P0.txt`: Contiene $P_0$ en la primera fila (para recentrado óptico) seguido de los nodos del Material 2 en coordenadas relativas idénticas a $P_0$.
3. `Full_Grid_Unified.txt`: Archivo maestro con todos los nodos para verificación y metrología global.
4. `Recipe_Metadata.json`: Almacena la configuración cristalográfica, rotaciones $\theta$, dimensiones, métricas de trayectoria y coordenadas de $P_0$.

---

## 6. Optimizador de Trayectoria para Platina Piezoeléctrica (PI)

Para minimizar la fatiga mecánica, la histéresis piezoeléctrica y la acumulación de deriva termomecánica durante la impresión, el módulo implementa cuatro modos de ordenamiento de trayectoria:

1. **Serpiente / Zig-Zag (Snake — Recomendado)**: Agrupa los nodos por filas horizontales (con tolerancia $\delta_y = 50\text{ nm}$) e invierte la dirección de recorrido en filas impares ($\rightarrow, \leftarrow, \rightarrow, \leftarrow$).
2. **Espiral (Centro $\rightarrow$ Borde)**: Ordena los nodos radialmente para imprimir desde el núcleo del cristal hacia la periferia, ideal para estructuras circulares o discos.
3. **TSP Euclidiano (Nearest Neighbor)**: Resuelve el problema del viajante de comercio mediante aproximación voraz por mínima distancia euclidiana ($\sum \|\Delta \mathbf{r}_i\|$).
4. **Sin Ordenar**: Conserva el orden natural de generación $(n_1, n_2)$.

---

## 7. Guía de Integración y Operación en PyPrinting 3.0

1. **Abrir el Diseñador**:
   - Desde el **Lanzador Principal** ([`main.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/main.py)): Hacer clic en la tarjeta `📐 Diseñador de Redes 2D`.
   - Desde el **Microscopio Principal** ([`app.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/app.py)): Menú `Tools -> Diseñador de Redes 2D` o presionar `Ctrl+G`.
   - Desde el panel de **Measurements**: Clic en el botón `📐 Diseñador 2D` en el dock de Grilla.
2. **Seleccionar o Crear la Estructura**:
   - Escoger un preset (e.g. *🔷 Red Hexagonal en Hexágono (ap=5.0 µm, a=2.0 µm)* o *🌀 Superred Moiré Rotada*).
   - Ajustar parámetros de celda ($a, b, \gamma$) mediante los spinners numéricos y el deslizador de ángulo.
3. **Configurar Base Atómica y Distancia Mínima**:
   - En el panel `⚛️ Base Atómica`, ajustar las coordenadas fraccionales $(u_j, v_j)$ y los materiales de cada átomo.
   - Fijar `Distancia Mínima d_min` en $0.4 - 0.5\ \mu\text{m}$ para prevenir colisiones ópticas.
4. **Configurar Partícula Ancla ($P_0$)**:
   - Dejar marcada la opción `Habilitar Partícula Ancla (P0)` (recomendado offset de seguridad $-2.0\ \mu\text{m}, -2.0\ \mu\text{m}$).
5. **Exportar la Grilla**:
   - **Para impresión directa monomaterial**: Clic en `💾 Exportar .txt Unificado` y cargarlo en `Measurements -> Load grid (.txt)`.
   - **Para nanofabricación secuencial multimaterial**: Clic en `📦 Paquete Receta Multi-Paso (P0)` para obtener las recetas individuales por coloide con $P_0$.
