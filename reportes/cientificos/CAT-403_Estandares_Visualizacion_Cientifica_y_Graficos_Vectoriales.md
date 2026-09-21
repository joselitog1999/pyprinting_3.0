# CAT-403: Estándares de Visualización Científica, Metrología Gráfica y Representación Vectorial
## Principios de Edward Tufte, Paletas Accesibles para Daltonismo, Exportación SVG/PDF con Texto Editable y Escalado de Resolución Editorial

---

**Signatura Bibliotecaria:** `CAT-403`  
**Clasificación Temática:** `[MET]` / `[CMP]` Metrología Gráfica, Comunicación Visual de la Ciencia y Estándares Editoriales  
**Pilar:** Pilar IV — Arquitectura de Datos, Serialización y Ecosistema de Software  
**Autoría:** José Luis González Peñafiel (*Becario Doctoral CONICET*), Comité Científico PyPrinting 3.0  
**Fecha de Publicación:** Septiembre 2026  
**Estado:** Producción / Consolidado  
**Módulos Asociados:** `analysis/figure_export_studio.py`, `analysis/lattice_disorder_gui.py`, `analysis/raman_analyzer.py`  
**Documentos Vinculados:**  
- [[CAT-401_Estandar_Serializacion_Jerarquica_Contenedor_HDF5]] (Persistencia de datos crudos)  
- [[CAT-402_Estandar_Datos_FAIR_y_Serializacion_NeXus_HDF5]] (Principios FAIR de reproducibilidad)  
- [[SYS-001_Estandares_Diseno_Arquitectura_PyPrinting3]] (Estándares de software e interfaces)  

---

## 1. Resumen Ejecutivo

En la investigación científica rigurosa, un gráfico no es una mera ilustración estética: es un **documento metrológico visual**. La elección inapropiada de colormaps (como el perjudicial *Rainbow/Jet*), la pérdida de texto vectorial al rasterizar prematuramente figuras, o la falta de cumplimiento de los estándares de resolución tipográfica provocan rechazos editoriales en revistas internacionales (Nature, APS, ACS) e introducen sesgos cognitivos que distorsionan la interpretación cuantitativa de los datos.

Este reporte formaliza los fundamentos de diseño y arquitectura de software implementados en el **Estudio de Exportación Científica Universal** (`analysis/figure_export_studio.py`). Se formalizan los principios de maximización del cociente dato-tinta (*Data-Ink Ratio*) de Edward Tufte, se establece el uso obligatorio de mapas de color perceptualmente uniformes y accesibles para deuteranopía/protanopía (Viridis, Cividis, Catppuccin Mocha), se detallan las configuraciones vectoriales estrictas para preservar texto editable en SVG (`svg.fonttype = 'none'`) y fuentes incrustadas Type 42 en PDF (`pdf.fonttype = 42`), y se deducen las relaciones de escala física para exportaciones raster a 300, 600 y 1200 DPI.

---

## 2. Filosofía del Diseño de Información: Edward Tufte & Cleveland

En `analysis/figure_export_studio.py`, toda representación gráfica responde a tres leyes cardinales de la metrología visual:

### 2.1 El Cociente Dato-Tinta (Data-Ink Ratio)
Tufte (1983) define el cociente dato-tinta como la proporción de tinta gráfica dedicada a la visualización directa de información no redundante:

$$\text{Data-Ink Ratio} = \frac{\text{Tinta dedicada a los datos}}{\text{Tinta total utilizada en el gráfico}} \longrightarrow 1.0$$

- **Eliminación de Basura Gráfica (*Chartjunk*)**: Se eliminan fondos coloreados con degradados artificiales, bordes decorativos innecesarios, cajas 3D en datos 2D y sombras que distorsionen los límites de los picos.
- **Micro-rejillas tenues**: Las líneas de retícula auxiliar deben ser sutiles (`#313244` con transparencia $\alpha = 0.4$), colocadas detrás de los datos para servir de guía sin competir con las curvas físicas.

### 2.2 Factor de Distorsión Visual (Lie Factor)
El factor de distorsión visual cuantifica si la representación gráfica magnifica o reduce artificialmente un efecto físico:

$$\text{Lie Factor} = \frac{\text{Magnitud del efecto visual en el gráfico [\%]}}{\text{Magnitud real en los datos numéricos [\%]}} \approx 1.0$$

Cualquier gráfico con $\text{Lie Factor} \neq 1.0$ (por ejemplo, truncar el eje $Y$ para simular un cambio drástico en una reflectividad que solo varió un $0.5\%$) se clasifica como metodológicamente inaceptable.

---

## 3. Percepción Cromática y Accesibilidad Universal

### 3.1 El Peligro del Colormap Rainbow / Jet
Históricamente, muchos software científicos han utilizado el mapa de color *Rainbow/Jet*. Estudios psicofísicos rigurosos han demostrado que este mapa es **cognitivamente tóxico**:
1. **No es monotónico en luminosidad**: Presenta picos artificiales de brillo aparente en el amarillo y cian que el cerebro humano interpreta erróneamente como bordes o transiciones de fase inexistentes.
2. **Excluye al 8% de la población masculina**: Para personas con daltonismo (deuteranopía o protanopía), el rojo y el verde se perciben idénticos, anulando la legibilidad.

```
Luminosidad L* (Escala Perceptual Humana):
100 |          /\               /\            Viridis (Monotónica creciente lineal)
    |         /  \             /  \           ------------------------------------
 50 |  Jet   /    \___________/    \          
    |  (Oscila caóticamente)        \
  0 +-------------------------------------> Longitud de onda / Valor normalizado
```

### 3.2 Estándares Perceptualmente Uniformes en PyPrinting 3.0
El software impone mapas monotónicos lineales en el espacio de color CAM02-UCS:
- **`Viridis`**: Estándar general de alta luminosidad para mapas de intensidad óptica.
- **`Plasma` / `Inferno`**: Para densidades de potencia fototérmica y gradientes de temperatura.
- **`Cividis`**: Optimizado matemáticamente para ser **100% idéntico** en visión tricromática y dicromática (apto para daltónicos).
- **Paleta Catppuccin Mocha**: Utilizada para elementos discretos y estados de interfaz (resuelto `#a6e3a1`, error `#f38ba8`, advertencia `#f9e2af`, acento `#cba6f7`).

---

## 4. Arquitectura de Gráficos Vectoriales para Edición y Publicación

En `analysis/figure_export_studio.py`, la exportación vectorial aplica configuraciones globales de Matplotlib antes de instanciar el backend:

```python
import matplotlib
matplotlib.use('Agg')
matplotlib.rcParams['svg.fonttype'] = 'none'
matplotlib.rcParams['pdf.fonttype'] = 42
matplotlib.rcParams['ps.fonttype'] = 42
```

### 4.1 SVG Vectorial con Nodos de Texto Editables (`svg.fonttype = 'none'`)
Por defecto, muchos motores de renderizado convierten las letras a polígonos cerrados (`<path>`), impidiendo que un autor pueda corregir tipografías, tamaños de fuente o símbolos LaTeX en Inkscape o Adobe Illustrator.  
Con `svg.fonttype = 'none'`, el archivo SVG generado contiene etiquetas semánticas nativas `<text x="..." y="..." font-family="DejaVu Sans">... </text>`, permitiendo la edición tipográfica directa con texto vivo sin alterar la geometría de las curvas numéricas.

### 4.2 PDF para LaTeX con Fuentes Type 42 (`pdf.fonttype = 42`)
Las normas de envío a editoriales de élite (American Physical Society - Physical Review, American Chemical Society, Nature Portfolio) rechazan manuscritos PDF cuyas figuras utilicen fuentes rasterizadas Type 3.  
Configurando `pdf.fonttype = 42`, las fuentes tipográficas se incrustan como vectores **TrueType / Type 42**, garantizando que el documento compile en pdfLaTeX / XeLaTeX sin advertencias de fuentes faltantes.

---

## 5. Metrología de Exportación Raster y Dimensionamiento en DPI

Cuando se requiere un formato rasterizado (PNG, TIFF) para microscopía, el dimensionamiento físico se calcula según la ecuación de densidad de píxeles:

$$N_{\text{pixels}} = W_{\text{pulgadas}} \times \text{DPI}$$

| Nivel de Publicación | Resolución (DPI) | Caso de Uso Editorial | Ancho Típico (1 Columna, 3.5 in) |
| :--- | :--- | :--- | :--- |
| **Borrador / Web** | $150 - 300\ \text{DPI}$ | Pre-visualización rápida, presentaciones de diapositivas | $525 - 1050\ \text{px}$ |
| **Publicación Regular** | $600\ \text{DPI}$ | Estándar obligatorio de revistas para figuras a color/escala de grises | $2100\ \text{px}$ |
| **Arte de Línea Puro** | $1200\ \text{DPI}$ | Gráficos blanco y negro de alto contraste (sin antialiasing borroso) | $4200\ \text{px}$ |

---

## 6. Referencias Bibliográficas Primarias

1. **Tufte, E. R.** (1983). *The Visual Display of Quantitative Information*. Graphics Press, Cheshire, Connecticut.
2. **Cleveland, W. S.** (1994). *The Elements of Graphing Data*. Hobart Press, Summit, New Jersey.
3. **Nuñez, J. R., Anderton, C. R., & Renslow, R. S.** (2018). *Optimizing colormaps with recognition of color vision deficiency*. PLoS ONE, 13(7), e0199239. [DOI: 10.1371/journal.pone.0199239](https://doi.org/10.1371/journal.pone.0199239)
4. **Crameri, F., Shephard, G. E., & Heron, P. J.** (2020). *The misuse of colour in science communication*. Nature Communications, 11, 5444. [DOI: 10.1038/s41467-020-19160-7](https://doi.org/10.1038/s41467-020-19160-7)
