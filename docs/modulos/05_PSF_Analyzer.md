# 🔬 Módulo 05: Analizador de PSF 2D (`analysis/psf_analyzer.py`)

**Laboratorio de Nanofotónica — Instituto de Nanosistemas (INS-UNSAM / CONICET)**  
**Archivo Fuente**: [`analysis/psf_analyzer.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/analysis/psf_analyzer.py) / [`analysis/psf.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/analysis/psf.py)  
**Lanzador Rápido**: Botón 7 en [`main.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/main.py) o `Tools -> PSF Analyzer` desde `app.py`

---

## 1. 🏷️ Resumen y Rol en el Sistema

El módulo **PSF Analyzer** es la herramienta analítica de metrología óptica encargada de caracterizar la **Función de Dispersión de Punto (*Point Spread Function*, PSF)** de los haces de excitación láser y la respuesta de emisión de nanopartículas individuales.

Capacidades destacadas:
- **Ajuste No Lineal Gaussiano 2D Completo (7 Parámetros)**: Calcula centroide sub-nanométrico $(x_0, y_0)$, amplitudes, anchos espaciales $(\sigma_x, \sigma_y)$, ángulo de rotación elíptica $\theta$, fondo constante $z_0$ y $\text{FWHM} = 2\sqrt{2\ln 2}\sigma \approx 2.355\sigma$.
- **Modelado de Haces Donut ($LG_{01}$)**: Ajusta el perfil anular de modos Laguerre-Gaussianos utilizados en microscopía de super-resolución y manipulación óptica.
- **Visualizador Triple Sincronizado**: Presenta lado a lado la **Imagen Original**, el **Modelo Ajustado** y el **Mapa de Residuales** ($\text{Original} - \text{Modelo}$) con escala de color unificada.
- **Perfiles 1D Intersectados por el Centroide**: Gráficos instantáneos de cortes transversales en X e Y con superposición de la curva teórica.
- **Métricas de Calidad Óptica**: Cálculo automático del coeficiente de determinación $R^2$, relación señal-ruido ($\text{SNR}$ en $\text{dB}$) y porcentaje de elipticidad $\epsilon = 1 - \sigma_{\min}/\sigma_{\max}$.

---

## 2. 🖼️ Maqueta de la Interfaz Visual (ASCII Layout)

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│  PyPrinting 3.0 — Analizador de Función de Dispersión de Punto (PSF 2D Analyzer)                      -  □  ×    │
├──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│  PANEL DE CONFIGURACIÓN Y CARGA DE DATOS                                                                         │
│  [ 📂 Cargar Imagen / Scan ]  [ 💾 Exportar Reporte ]  │ Modelo: [ Gaussiano 2D (Elíptico) ▼]  Tamaño: [ 5.0 ] µm│
│  [X] Invertir Intensidad (Valles a Picos)  │ Píxel Scale: [ 0.0833 ] µm/px  │ [ 🎯 Ajustar Automático (Fit) ]     │
├──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│  VISUALIZADOR TRIPLE 2D (Original | Ajuste Teórico | Residuales)                                                 │
│  ┌───────────────────────────────┬───────────────────────────────┬───────────────────────────────┐               │
│  │ 1. IMAGEN ORIGINAL            │ 2. MODELO AJUSTADO            │ 3. MAPA DE RESIDUALES         │               │
│  │ ┌───────────────────────────┐ │ ┌───────────────────────────┐ │ ┌───────────────────────────┐ │               │
│  │ │          ...              │ │ │          ...              │ │ │          ...              │ │               │
│  │ │        .:::::.            │ │ │        .:::::.            │ │ │        . : .              │ │               │
│  │ │       .::::::: .          │ │ │       .:::::::.           │ │ │       .     .             │ │               │
│  │ │        .:::::.            │ │ │        .:::::.            │ │ │        . : .              │ │               │
│  │ │          ...              │ │ │          ...              │ │ │          ...              │ │               │
│  │ └───────────────────────────┘ │ └───────────────────────────┘ │ └───────────────────────────┘ │               │
│  │ Pico: 8.45 V | Fondo: 0.12 V│ │ R²: 0.9942 | SNR: 24.8 dB  │ │ RMS Residual: 0.042 V       │               │
│  └─────────────────────────────┴─┴─────────────────────────────┴─┴─────────────────────────────┘               │
├─────────────────────────────────────────────────────────────────┬────────────────────────────────────────────────┤
│  PERFILES CORTADOS 1D (Cortes X / Y por el Centroide)           │  TABLA DE PARÁMETROS METROLÓGICOS              │
│  ┌───────────────────────────────────────────────────────────┐  │  • Centroide X:  +2.458 ± 0.003 µm             │
│  │ 8.0|      /█\    ── Datos Experimentales                  │  │  • Centroide Y:  +2.512 ± 0.003 µm             │
│  │    |     / █ \   ── Curva de Ajuste No Lineal             │  │  • FWHM X:       278.4 ± 1.8 nm                │
│  │ 4.0|    /  █  \                                           │  │  • FWHM Y:       286.1 ± 1.9 nm                │
│  │    |   /   █   \                                          │  │  • Elipticidad:  2.69 % (Simetría casi pura)   │
│  │ 0.0└──/────█────\──────────────────────────────── X / Y   │  │  • Ángulo θ:     14.2°                         │
│  └───────────────────────────────────────────────────────────┘  │  • Amplitud A:   8.33 V  |  Fondo z0: 0.12 V   │
├─────────────────────────────────────────────────────────────────┴────────────────────────────────────────────────┤
│  🟢 Ajuste convergente (Levenberg-Marquardt) en 14 iteraciones | R² = 0.9942 | FWHM_promedio = 282.2 nm          │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. 🎛️ Arquitectura Bi-Modal y Catálogo de Controles

A partir de la versión 3.0, la ventana principal **`PSFAnalyzerWindow`** adopta una estructura de navegación por pestañas:

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│  [ 📸 Foto Única & Líneas de Corte ]       [ 🔬 Co-Alineación Dual Confocal ]                   │
└─────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 3.1 Pestaña 1: Foto Única & Líneas de Corte 1D (`SingleImageProfileWidget`)
Especialmente concebida para la caracterización rápida de imágenes microscópicas independientes (campo claro, fluorescencia, scattering de nanopartículas, perfiles de haz láser de cámara o barridos confocales individuales):

- **Líneas de Corte 2D Interactivas**:
  - **Línea Libre de 2 Puntos (Arrastrable)**: Manipulación manual de los extremos de corte directamente sobre el visor bidimensional utilizando `pyqtgraph.LineSegmentROI`.
  - **Atajos Ortogonales de 1-Clic**:
    - **Corte Horizontal**: Pasa a través del centroide o máximo de intensidad.
    - **Corte Vertical**: Pasa a través del centroide o máximo de intensidad.
    - **Diagonales a 45° y 135°**: Para evaluación de astigmatismo óptico.
    - **Perfil Radial Promediado 360°**: Muestrea circunferencias concéntricas alrededor del centro para evaluar simetría azimutal.
  - **Espesor de Corte Transversal Promediado (1 a 31 píxeles)**:
    - Promedia $N$ franjas perpendiculares a lo largo del segmento de corte, reduciendo drásticamente el ruido Poisson/shot noise sin deformar la función de dispersión.

- **Metrología y Ajuste Gaussiano 1D**:
  - Ajusta los datos experimentales del corte $I(s)$ a la función analítica:
    $$I(s) = I_0 + A \cdot \exp\left( -\frac{(s - s_0)^2}{2\sigma^2} \right)$$
  - **Parámetros Reportados en Tiempo Real**:
    - **$\text{FWHM}$ Experimental**: En micrómetros ($\mu\text{m}$) y en píxeles: $\text{FWHM} = 2\sqrt{2\ln 2}\,\sigma \approx 2.35482\,\sigma$.
    - **Posición Central ($s_0$)**: Centroide del haz a lo largo de la línea de corte.
    - **Amplitud Neta ($A$) y Fondo ($I_0$)**: Altura de pico y nivel base de offset.
    - **Relación Señal/Fondo (SBR)**: $A / I_0$.
    - **Bondad de Ajuste ($R^2$)**: Coeficiente de determinación.
    - **Comparación Difractiva de Abbe**:
      $$\text{FWHM}_{\text{teórico}} = \frac{0.51 \lambda}{\text{NA}}$$
      Al ingresar la longitud de onda ($\lambda$ en nm) y la apertura numérica del objetivo ($\text{NA}$), el software calcula instantáneamente el porcentaje de ensanchamiento respecto al límite teórico de difracción.

- **Reglas Verticales Duales (Cursores A y B)**:
  - Posicionamiento arrastrable para medir distancias locales $\Delta X$, diferencia de cuentas $\Delta Y$ e integral de área bajo la curva entre ambos cursores.

- **Exportación 1-Clic**:
  - **Copiar TSV al Portapapeles**: Listo para pegar directamente en **OriginLab**, **Excel** o **Prism**.
  - **Exportar CSV**: Guarda la tabla de corte $(s[\mu\text{m}], I(s))$ con encabezados metrológicos.

---

### 3.2 Pestaña 2: Co-Alineación Dual Confocal (`PSFAnalyzerWidget`)
Conserva todas las capacidades de análisis comparativo entre los dos canales confocales del sistema ($Z_1$ y $Z_2$), ajustando simultáneamente los modelos gaussianos 2D elípticos de 7 parámetros y generando el mapa de residuales y la distancia de separación entre centroides.

---

## 4. 📥 Archivos de Entrada que Solicita

1. **Mapas Confocales PyPrinting (`NPscan_*.tiff`, `.npy`, `.csv`)**:
   - Matrices flotantes o enteras de $N \times M$ píxeles.
2. **Fotografías de Cámara Réflex o CMOS (`Foto_*.tiff`, `.jpg`, `.png`)**:
   - Si la imagen es RGB, el analizador extrae automáticamente la luminancia monocromática ($Y = 0.299R + 0.587G + 0.114B$).

---

## 5. 📤 Archivos de Salida que Genera

1. **Reporte Metrológico de Ajuste (`psf_fit_results_YYYYMMDD_HHMMSS.txt`)**:
   - *Estructura*:
     ```
     ============================================================
     PyPrinting 3.0 — REPORTE METROLÓGICO DE AJUSTE DE PSF 2D
     ============================================================
     Fecha y Hora:        2026-08-26 15:45:00
     Modelo Empleado:     Gaussiano 2D Elíptico (7 Parámetros)
     Bondad de Ajuste R²: 0.9942
     Relación Señal/Ruido: 24.8 dB
     ------------------------------------------------------------
     PARÁMETROS ÓPTICOS ESTIMADOS:
     • Centroide X (x0):  +2.4580 ± 0.0032 µm
     • Centroide Y (y0):  +2.5120 ± 0.0031 µm
     • Amplitud Pico (A):  8.3320 ± 0.0450 V
     • Fondo (z0):         0.1210 ± 0.0080 V
     • Sigma X (σx):       118.20 ± 0.85 nm
     • Sigma Y (σy):       121.50 ± 0.90 nm
     • FWHM X:             278.40 ± 1.80 nm
     • FWHM Y:             286.10 ± 1.90 nm
     • Elipticidad:        2.69 %
     • Ángulo Rotación θ:  14.2°
     ============================================================
     ```
2. **Figura Triple de Publicación (`psf_fit_triple_view.png`)**:
   - Imagen de alta resolución ($300\ \text{DPI}$) conteniendo los tres paneles y perfiles 1D.

---

## 6. ⚙️ Formulación Matemática del Ajuste 2D

El modelo **Gaussiano 2D Elíptico con Rotación** implementado en [`analysis/psf.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/analysis/psf.py) se define como:

$$I(x, y) = z_0 + A \cdot \exp\left( -\left[ a(x - x_0)^2 + 2b(x - x_0)(y - y_0) + c(y - y_0)^2 \right] \right)$$

donde los coeficientes tensoriales dependen del ángulo de rotación $\theta$:
$$a = \frac{\cos^2\theta}{2\sigma_x^2} + \frac{\sin^2\theta}{2\sigma_y^2}, \quad b = -\frac{\sin(2\theta)}{4\sigma_x^2} + \frac{\sin(2\theta)}{4\sigma_y^2}, \quad c = \frac{\sin^2\theta}{2\sigma_x^2} + \frac{\cos^2\theta}{2\sigma_y^2}$$

El ancho a mitad de altura ($\text{FWHM}$) en cada eje principal se calcula rigurosamente como:
$$\text{FWHM}_x = 2\sqrt{2\ln 2}\,\sigma_x \approx 2.35482\,\sigma_x, \qquad \text{FWHM}_y = 2\sqrt{2\ln 2}\,\sigma_y \approx 2.35482\,\sigma_y$$

---

## 7. ⚠️ Límites de Validez y Modos de Falla

| Condición de Borde (Fallo Óptico / Ajuste) | Firma Experimental (Mapa 2D / Residuales / Fit) | Acción Correctiva Física (Procedimiento en Laboratorio) |
| :--- | :--- | :--- |
| **Aberración Esférica por Espesor Incorrecto de Cubreobjetos** ($t \ne 170\ \mu\text{m}$). | PSF 2D asimétrica con anillos difractivos pronunciados; ensanchamiento de $\text{FWHM} > 380\ \text{nm}$ en $532\ \text{nm}$ (límite difractivo $\approx 280\ \text{nm}$). | Ajustar el collar de corrección de espesor en el objetivo de inmersión en aceite ($100\times / 1.4\ \text{NA}$) a la marca `#1.5` ($170\ \mu\text{m}$) y limpiar el aceite viejo con papel de óptica. |
| **No Convergencia del Ajuste Gaussiano por Baja SNR** ($SNR < 3$). | El algoritmo Levenberg-Marquardt devuelve parámetros `NaN` o valores irreales de ancho ($\sigma_x > 2\ \mu\text{m}$); matriz de covarianza singular. | Incrementar el tiempo de integración del fotodiodo o aumentar ligeramente la potencia del láser de barrido confocal ($P_{\text{scan}} \sim 0.2 - 0.5\ \text{mW}$) sin exceder el umbral térmico. |
| **Astigmatismo por Desalineación del Expansor de Haz**. | Elipticidad de la PSF $> 15\%$ con ejes principales rotados a $45^\circ$; desdoblamiento de focos en $X$ e $Y$. | Realinear el telescopio colimador / expansor de haz monomodo a la entrada del microscopio para asegurar frente de onda plano TEM00 sin inclinación. |

---

## 8. 🔗 Referencias Cruzadas
- [📘 Manual de Usuario — Sección 7: Ajuste de PSF y Metrología Óptica](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/docs/MANUAL_USUARIO.md#7-ajuste-de-psf-y-metrología-óptica)
- [📑 Reporte Científico de PSF (`reportes/cientificos/Deconvolucion_Richardson_Lucy_y_Trackpy_PyPrinting3.md`)](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/reportes/cientificos/Deconvolucion_Richardson_Lucy_y_Trackpy_PyPrinting3.md)
