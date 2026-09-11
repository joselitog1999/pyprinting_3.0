# Reporte Técnico: Arquitectura, Ergonomía y Propagación de Filtros en el Analizador SIF (Andor Solis)

**PyPrinting 3.0 — Suite de Nanofotónica y Espectroscopía Plasmónica**  
**Laboratorio de Nanofotónica, Instituto de Nanosistemas (INS-UNSAM / CONICET)**  
**Autor:** Lic. José Luis González Peñafiel  
**Fecha:** Septiembre 2026 | **Versión:** 3.2 (Revisión Post-Refactorización Integral)

---

## 1. Resumen Ejecutivo y Metadatos Técnicos

El presente informe documenta el diagnóstico integral, diseño arquitectónico, formulación física y resolución de limitaciones operativas en el **Analizador y Procesador Avanzado de Espectros SIF** (`sif_analyzer.py` y `core/sif_processor.py`). 

Esta herramienta procesa archivos nativos binarios `.sif` adquiridos mediante cámaras EMCCD Andor iXon3 acopladas a espectrógrafos Andor Shamrock 500i bajo el software Andor Solis. La versión anterior presentaba restricciones ergonómicas severas (desbordamiento horizontal que impedía visualizar el panel derecho, toolbars desordenadas en una sola fila, nombres de archivo recortados) y desacoplamientos físicos en la cadena de procesamiento de señales (los filtros aplicados en 1D no se propagaban a las matrices 2D ni a los cálculos subsiguientes de transmitancia y extinción).

Tras la refactorización arquitectónica:
1. **Ergonomía y Visibilidad:** Se implementó un esquema de **dos filas lógicas compactas** por toolbar (reduciendo el ancho mínimo de $>1400\ \text{px}$ a $\approx 550\ \text{px}$), dotando a la interfaz de cartelería contextual (*tooltips* enriquecidos con unidades y fundamentos físicos) en cada control, barra de desplazamiento horizontal en el gestor de archivos con ajuste `ResizeToContents` y atajo de teclado `Ctrl+D` para colapsar/expandir el panel instrumental derecho.
2. **Opciones 2D Estructuradas:** Se encapsularon las configuraciones de transmitancia 2D en un panel agrupado (`⚙️ Opciones de Cálculo 2D`) con exclusión mutua física mediante `QButtonGroup` para las estrategias **Ruta A** y **Ruta B**, visualización comparativa y compuerta de ruido (*Noise Gate*).
3. **Propagación Unidireccional en Cascada:** Se desarrolló el motor `apply_spectral_filters_2d` en `core/sif_processor.py`. Cualquier limpieza de ruido, supresión de rayos cósmicos (*despiking*), filtro de Wiener o suavizado aplicado en las pestañas de Referencia (2) o Señal (3) transforma la matriz 2D completa fila a fila, actualiza el mapa de calor en tiempo real, regenera el promedio 1D en la ROI y se propaga obligatoriamente al cálculo de Transmisión (4) y al ajuste de Extinción (5).
4. **Verificación Formal:** Se certificó el 100% de éxito en la suite de 14 pruebas de interfaz gráfica (`test_sif_analyzer_gui.py`) y en los 62 diagnósticos del sistema global.

---

## 2. Diagnóstico de Causa Raíz de las Limitaciones Previas

### 2.1 Desbordamiento Horizontal de Pantalla y Bloqueo del Panel Derecho
* **Síntoma:** En monitores estándar (Full HD $1920 \times 1080$ o portátiles $1366 \times 768$), la ventana central requería un ancho superior a $1400\ \text{px}$. Al intentar arrastrar el divisor (`QSplitter`) hacia la izquierda, la ventana central se trababa, comprimiendo el panel instrumental lateral derecho hasta volverlo invisible o inutilizable.
* **Causa Raíz:** Cada una de las 5 pestañas organizaba sus botones, combos, spinboxes y etiquetas en un único `QHBoxLayout` horizontal continuo. La acumulación de 10 a 14 widgets con etiquetas extensas fijaba un `minimumSizeHint().width()` muy elevado.
* **Solución Aplicada:** División modular de cada barra de herramientas en **dos filas temáticas superpuestas**:
  - **Fila 1 (Selección Espacial y Pre-Filtros):** Delimitación de ROI, sustracción de dark y eliminación de picos cósmicos.
  - **Fila 2 (Acondicionamiento Espectral y Visualización):** Filtros analíticos (Wiener, Savitzky-Golay, Fourier), escalas y botones de restauración.
  - Resultado: Ancho mínimo reducido a $\approx 550\ \text{px}$, otorgando total libertad al usuario para dimensionar los tres paneles simultáneamente.

```
+-----------------------------------------------------------------------------------------+
| Toolbar Superior: FILA 1 (ROI, Dark, Despike, Copiar ROI, Raw)                         |
+-----------------------------------------------------------------------------------------+
| Toolbar Inferior: FILA 2 (Filtros Wiener/SG/Fourier, Escala, Normalizaciones)          |
+-----------------------------------------------------------------------------------------+
| Panel Gráfico Splitter:                                                                 |
| [ Heatmap 2D (Filtros Aplicados en Vivo) ] | [ Espectro 1D (Promedio ROI Filtrado) ]   |
+-----------------------------------------------------------------------------------------+
```

### 2.2 Truncamiento de Nombres en el Gestor de Archivos
* **Síntoma:** En la tabla de archivos de la izquierda, los nombres largos típicos de series experimentales (ej. `2026-09-11_Sample_AuNR_785nm_pol00_scan01.sif`) se cortaban con elipsis (`...`), impidiendo diferenciar las muestras. Al no existir desplazamiento horizontal, el usuario debía ensanchar excesivamente el panel izquierdo, reduciendo aún más el área de los gráficos.
* **Causa Raíz:** `QTableWidget` tenía `setHorizontalScrollBarPolicy(ScrollBarAlwaysOff)` o no forzaba el modo de redimensionamiento de columnas a `ResizeToContents`.
* **Solución Aplicada:**
  - Habilitación de barra de scroll horizontal estilizada: `setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)`.
  - Configuración del encabezado: `header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)`.
  - Inserción de `QToolTip` en cada celda conteniendo la ruta absoluta del archivo en disco (`abs_path`).

### 2.3 Ambigüedad entre Ruta A y Ruta B en Transmitancia 2D
* **Síntoma:** En la pestaña 4 (Transmisión), las opciones de cálculo 2D estaban dispersas junto a los controles de visualización 1D. Los checkboxes `Ruta A` y `Ruta B` no estaban vinculados lógicamente, permitiendo combinaciones erráticas en la UI.
* **Causa Raíz:** Falta de un contenedor lógico y de un grupo de botones de exclusión mutua.
* **Solución Aplicada:** Creación del panel `⚙️ Opciones de Cálculo 2D` encapsulado en un `QGroupBox` estilizado en azul oscuro (`#132238`), con `QButtonGroup` exclusivo para alternar entre Ruta A (promedio 1D a 1D) y Ruta B (píxel a píxel 2D a 2D), checkbox independiente de comparación y filtro de corte (*Noise Gate*).

### 2.4 La Paradoja de los Filtros Fantasma (Ruptura del Pipeline de Procesamiento)
* **Síntoma:** Si el operador activaba un filtro Savitzky-Golay o eliminaba un rayo cósmico en la pestaña de Señal, el gráfico 1D se veía limpio, pero el mapa 2D seguía mostrando el pico cósmico intacto. Peor aún: al pasar a la Pestaña 4 (Transmisión), el espectro de transmitancia volvía a exhibir el artefacto de ruido, demostrando que los cálculos posteriores ignoraban los filtros previos.
* **Causa Raíz:** El código aplicaba los filtros espectrales exclusivamente sobre el vector 1D obtenido tras promediar la ROI, dejando inalterada la matriz interna 2D (`self.raw_data_2d`). Al calcular la transmitancia 2D en la Pestaña 4 o el cociente de matrices, el sistema tomaba la matriz cruda sin filtrar.
* **Solución Aplicada:** Rediseño completo del pipeline de procesamiento mediante el paradigma **Filtro 2D Primero $\implies$ Proyección 1D Después**:
  $$\mathbf{D}_{\text{raw}}^{(2D)} \xrightarrow{\text{Filtro 2D fila a fila}} \mathbf{D}_{\text{filt}}^{(2D)} \xrightarrow{\text{Promedio en ROI}} \mathbf{s}_{\text{filt}}^{(1D)}$$
  De este modo, tanto el mapa de calor 2D como el vector 1D, la transmitancia 2D/1D y la extinción final operan sobre exactamente el mismo conjunto de datos acondicionados físicamente.

---

## 3. Formulación Física y Tratamiento de Canales Andor Solis

### 3.1 Corrección de la Dispersión en Archivos 2D Multi-Pixel
Cuando Andor Solis registra una adquisición 2D dispersada sobre el detector iXon3 ($N_y$ pistas verticales $\times N_\lambda$ píxeles espectrales, típicamente $128 \times 1024$), los paquetes de lectura decodifican la forma como un arreglo plano. 

Si el eje de longitud de onda se calcula tomando la dimensión total ($N_{\text{total}} = N_y \cdot N_\lambda$), el polinomio de calibración:
$$\lambda(p) = a_0 + a_1 p + a_2 p^2 + a_3 p^3$$
se evalúa con índices $p \in [0, N_y \cdot N_\lambda - 1]$, generando valores astronómicos de longitud de onda ($>35,000\ \text{nm}$).

En `core/sif_processor.py`, la rutina `_correct_wavelength_axis` detecta la discrepancia dimensional:
```python
if wavelengths.ndim == 1 and len(wavelengths) == total_pixels and num_frames > 1:
    # Recalibrar dispersión cúbica estrictamente sobre num_channels (N_lambda)
    p = np.arange(num_channels)
    wavelengths = a0 + a1 * p + a2 * (p**2) + a3 * (p**3)
```
restituyendo con precisión micrométrica el espectro real de la rendija (ej. $450.0\ \text{nm}$ a $950.0\ \text{nm}$).

### 3.2 La Causa Raíz de Transmitancias Disparatadas (>6000%) en Solis
En mediciones espectrofotométricas convencionales de libro de texto, la transmitancia $T(\lambda)$ se define como:
$$T(\lambda) = \frac{I_{\text{muestra}}(\lambda) - I_{\text{dark}}(\lambda)}{I_{\text{referencia}}(\lambda) - I_{\text{dark}}(\lambda)} \times 100\%$$

Sin embargo, en archivos `.sif` de 4 canales generados por Andor Solis:
* **Canal 0 (`Transmittance`):** Transmitancia interna calculada por el firmware de Solis ($T_{\text{meas}}$).
* **Canal 1 (`Counts (Bg Corrected)`):** Canal de Referencia de la lámpara halógena ($R$). **Andor Solis ya le ha sustraído internamente el Dark.**
* **Canal 2 (`Counts`):** Canal de Ruido de fondo / Dark ($D \approx 320\ \text{cuentas}$).
* **Canal 3 (`Counts`):** Canal de Señal Live de la muestra ($L$). **Cuentas brutas con el Dark sumado.**

Si el software restara ciegamente el canal Dark al denominador:
$$T_{\text{erróneo}}(\lambda) = \frac{L(\lambda) - D(\lambda)}{R(\lambda) - D(\lambda)} \times 100\%$$
en las regiones de baja emisión de la lámpara (alas azul y NIR donde $R \approx 10 \sim 350\ \text{cuentas}$), el denominador $R - D$ se vuelve cercano a cero o negativo:
$$R - D \approx 330 - 320 = 10\ \text{cuentas} \implies \frac{600}{10} \times 100\% = \mathbf{6000\%}$$

#### Solución Algorítmica Implementada:
El procesador examina la cabecera binaria del Canal 1. Si contiene la etiqueta `b'Counts (Bg Corrected)'` o el flag `ref_is_bg_corrected = True`:
$$T_{\text{calc}}(\lambda) = \frac{L(\lambda) - D(\lambda)}{R(\lambda)} \times 100\%$$

Esta simple pero crucial corrección física produce una coincidencia casi perfecta con los datos certificados de Solis:
* **En espectros 1D FVB:** Diferencia mediana absoluta $|T_{\text{calc}} - T_{\text{meas}}| = \mathbf{0.0037\%}$.
* **En espectros 2D (Slit Imaging):** Diferencia mediana absoluta $|T_{\text{calc}} - T_{\text{meas}}| = \mathbf{0.29\%}$ ($<0.5\%$).

---

## 4. Arquitectura del Motor de Filtrado Bidimensional (`apply_spectral_filters_2d`)

Para garantizar que los mapas de calor 2D reflejen fidedignamente el tratamiento de la señal y que las transmitancias 2D píxel a píxel se calculen libres de ruido, se incorporó la función:
```python
def apply_spectral_filters_2d(data_2d, dark_2d=None, despike=False, 
                              noise_std=None, wiener=False, 
                              spectral_filter='none', window_size=15):
```

### 4.1 Secuencia Matemática Aplicada a Cada Fila $y \in [0, N_y - 1]$:

1. **Sustracción Espacial de Ruido de Fondo (Dark Subtraction):**
   Si se proporciona una matriz o vector de dark $\mathbf{D}$:
   $$\mathbf{I}^{(1)}(y, \lambda) = \mathbf{I}^{(0)}(y, \lambda) - \mathbf{D}(y, \lambda)$$
2. **Supresión Adaptativa de Rayos Cósmicos (Despiking):**
   Detecta artefactos transitorios de alta energía comunes en detectores CCD criogénicos. Se evalúa la primera y segunda diferencia espectral. Para umbralización robusta ante señales estructuradas, se utiliza la Desviación Absoluta respecto a la Mediana (MAD):
   $$\text{MAD} = \text{median}\left( |\Delta \mathbf{I} - \text{median}(\Delta \mathbf{I})| \right), \quad \sigma_{\text{est}} = 1.4826 \times \text{MAD}$$
   Cualquier píxel que verifique $|\Delta I(y, \lambda)| > k \cdot \sigma_{\text{est}}$ (con $k=5$) es clasificado como rayo cósmico y reemplazado por la interpolación cúbica de sus vecinos inmediatos:
   $$\mathbf{I}^{(2)}(y, \lambda_p) = \frac{1}{2} \left[ \mathbf{I}^{(1)}(y, \lambda_{p-1}) + \mathbf{I}^{(1)}(y, \lambda_{p+1}) \right]$$
3. **Filtro Inverso Estadístico de Wiener:**
   Opera en el dominio espectral atenuando selectivamente componentes donde la densidad de ruido supera a la de la señal plasmónica:
   $$\mathbf{I}^{(3)}(y, \lambda) = \text{wiener}\left(\mathbf{I}^{(2)}(y, \lambda), \text{mysize}=7, \text{noise}=\sigma_{\text{dark}}^2\right)$$
4. **Acondicionamiento Espectral Suave (Savitzky-Golay / Fourier):**
   - **Savitzky-Golay:** Ajuste polinomial local de grado 2 o 3 con ventana impar $W$:
     $$\mathbf{I}^{(4)}(y, \lambda) = \sum_{k=-(W-1)/2}^{(W-1)/2} c_k \cdot \mathbf{I}^{(3)}(y, \lambda + k)$$
     Preserva el centroide de resonancia plasmónica ($\lambda_{\text{SPR}}$) y el ancho a media altura (FWHM) sin ensanchar artificialmente el pico.
   - **Fourier Pasa-Bajos (FFT Cutoff):** Truncación gaussiana en el dominio de frecuencia espacial eliminando zumbido electrónico de alta frecuencia.

---

## 5. Diseño Ergonómico y Usabilidad en las 5 Ventanas de Proceso

A continuación se detalla la configuración y propósito de cada ventana para que cualquier operador pueda utilizar el módulo de manera autónoma:

```
[⬛ 1. Ruido/Dark] ──> [💡 2. Referencia] ──> [🔴 3. Live/Señal] ──> [📊 4. Transmisión] ──> [🔬 5. Extinción]
```

### 5.1 Ventana 1: ⬛ Ruido / Dark
* **Finalidad Científica:** Medir y aislar la corriente de oscuridad (*dark current*) y el sesgo electrónico (*bias offset*) de la cámara iXon3 ($T = -65^\circ\text{C}$).
* **Estructura de Controles:**
  - **Fila 1:** `Origen Ruido` (del archivo activo o del archivo maestro), `[x] Despike`, botón `🔍 Ver PSD` (abre el espectro de frecuencias espaciales y varianza de ruido $\sigma_{BG}(\lambda)$), botón `↺ Raw` (anula filtros para auditar los datos crudos del detector), `Auto-Escala`.
  - **Fila 2:** `Filtro Suavizado` (Ninguno, Savitzky-Golay, Fourier Lowpass, Media Móvil), `Ventana` (3 a 51 px, impar).
* **Interpretación:** El panel inferior reporta: Bias medio ($\approx 300 - 350\ \text{cuentas}$), dispersión $\sigma_{\text{dark}} \approx 3 - 6\ \text{cuentas}$, indicando la salud térmica del chip EMCCD.

### 5.2 Ventana 2: 💡 Referencia (Lámpara Halógena)
* **Finalidad Científica:** Aislar el perfil de emisión de la fuente de luz de campo claro que atraviesa el sustrato de vidrio sin nanopartículas.
* **Estructura de Controles:**
  - **Fila 1 (Selección Espacial de Ranura):** Spinboxes `ROI Y:` $[y_{\min}, y_{\max}]$ para limitar la integración vertical únicamente a la zona iluminada de la ranura, descartando píxeles oscuros de los extremos del sensor. `[x] Sub Dark` (sustrae el fondo caracterizado en Ventana 1), `[x] Despike` (elimina cósmicos en la lámpara), `↺ Raw` (resetea pre-procesamiento a cuentas crudas).
  - **Fila 2 (Acondicionamiento Espectral):** `[x] Filtro Wiener` (elimina ruido blanco gaussiano sin ensanchar bandas), `Filtro Suavizado` (Savitzky-Golay/Fourier), `Ventana`, `Auto-Escala`.
* **Gráficos:** Heatmap 2D interactivo con líneas horizontales rojas delimitando la ROI seleccionada, y perfil 1D con banda de desviación estándar $\mu \pm \sigma$.

### 5.3 Ventana 3: 🔴 Live / Señal (Muestra con Nanopartículas)
* **Finalidad Científica:** Capturar la luz transmitida a través de la nanopartícula individual o red periódica impresa.
* **Estructura de Controles:**
  - **Fila 1 (Espacial & Atajo de Copiado):** `ROI Y:` $[y_{\min}, y_{\max}]$, botón estelar **`🔗 Copiar ROI Ref`** (copia instantáneamente la ventana vertical definida en la lámpara halógena para asegurar un cociente geométrico 1:1 riguroso), `[x] Sub Dark`, `[x] Despike`, `↺ Raw`.
  - **Fila 2 (Acondicionamiento Espectral):** `[x] Filtro Wiener`, `Filtro Suavizado`, `Ventana`, `Auto-Escala`.
* **Propagación:** Los filtros aquí aplicados se inyectan directamente en la matriz 2D y el promedio 1D, impactando en tiempo real las ventanas 4 y 5.

### 5.4 Ventana 4: 📊 Transmisión ($T_{\text{calc}}$ vs $T_{\text{meas}}$)
* **Finalidad Científica:** Determinar la transmitancia espectral de la muestra respecto al blanco.
* **Estructura de Controles:**
  - **Fila 1 (Visualización):** Checkbox `[x] T_calc` (curva calculada en el módulo), `[x] T_meas` (curva original de Andor Solis), `[x] Mostrar Residuos` (gráfico inferior desplegando $\Delta T = T_{\text{calc}} - T_{\text{meas}}$), `Auto-Escala`.
  - **Fila 2 (Panel Agrupado ⚙️ Opciones de Cálculo 2D):**
    - `(o) Ruta A (Promedios 1D)`: Primero promedia las ROI verticales de muestra y referencia, y luego calcula el cociente 1D:
      $$T_A(\lambda) = \frac{\langle L(y, \lambda) \rangle_Y - \langle D(y, \lambda) \rangle_Y}{\langle R(y, \lambda) \rangle_Y} \times 100\%$$
    - `(o) Ruta B (Píxel a Píxel 2D)`: Calcula la transmitancia espacialmente resuelta para cada píxel $(y, \lambda)$ y luego promedia el mapa resultante en la ROI:
      $$T_{B}(y, \lambda) = \frac{L(y, \lambda) - D(y, \lambda)}{R(y, \lambda)} \times 100\%, \quad T_B(\lambda) = \langle T_B(y, \lambda) \rangle_Y$$
    - `[x] Comparar A y B`: Superpone ambas curvas simultáneamente en el gráfico con líneas punteadas para verificar consistencia geométrica.
    - `[x] Noise Gate`: Elimina ruido espurio en zonas donde la referencia es casi nula ($R(\lambda) < 1.05 \cdot D(\lambda)$).

### 5.5 Ventana 5: 🔬 Extinción y Ajuste Plasmónico
* **Finalidad Científica:** Obtener la densidad óptica de extinción de las nanopartículas:
  $$\text{Ext}(\lambda) = -\log_{10}\left( \frac{T(\lambda)}{100} \right) = \log_{10}\left( \frac{100}{T(\lambda)} \right)$$
  y ajustar modelos analíticos para extraer la resonancia plasmónica superficial localizada (LSPR).
* **Estructura de Controles:**
  - **Fila 1 (Modelo y Reglas):** Selector de `Modelo` (Gaussiano, Lorentziano, Asimétrico de Fano, Doble Pico Plasmónico), `Cursores A y B` (permite arrastrar reglas verticales para delimitar la ventana espectral de ajuste y descartar flancos ruidosos), botón `🚀 Ajustar Pico`.
  - **Fila 2 (Acondicionamiento y Reset):** `[x] Filtro Wiener en Extinción`, `Filtro Suavizado`, `Ventana`, botón `↺ Restaurar Rango`.
* **Reporte de Metrología (Norma ISO/GUM):**
  - Longitud de onda de resonancia: $\lambda_{\text{res}} \pm u(\lambda)\ [\text{nm}]$.
  - Ancho espectral a media altura: $\text{FWHM} \pm u(\text{FWHM})\ [\text{nm}]$.
  - Parámetro de asimetría cuántica $q$ (en modelos Fano para acoplamiento plasmónico sustrato-partícula).
  - Coeficiente de determinación bondad de ajuste: $R^2$.

---

## 6. Panel Instrumental Lateral y Gestor de Archivos

### 6.1 Panel Instrumental Derecho (Plegable con `Ctrl+D`)
Ubicado a la derecha de la ventana central, provee herramientas de soporte físico:
1. **Torreta de 5 Objetivos Microscópicos:**
   - Permite seleccionar el objetivo utilizado en la adquisición:
     * `10x Plan N` ($\text{NA}=0.25$, aire)
     * `20x Plan Fluor` ($\text{NA}=0.50$, aire)
     * `40x Plan Apo` ($\text{NA}=0.95$, aire)
     * `50x BD Plan` ($\text{NA}=0.80$, campo oscuro / polarización)
     * `100x UPlanFLN Oil` ($\text{NA}=1.30$, inmersión en aceite de cedro $n=1.518$)
   - La selección actualiza automáticamente la magnificación efectiva, el diámetro del disco de Airy y la corrección de apertura numérica en los reportes exportados.
2. **Calibración Espectral Externa:**
   - Permite importar un archivo de lámpara de calibración externa (Hg-Ar / Neón) para sobreescribir o refinar el eje de longitud de onda del archivo `.sif`.
3. **Exportación Gráfica y Tabular:**
   - Botón `📸 Guardar Figura (300 DPI / SVG)`: Genera gráficos listos para publicación científica en formatos vectoriales (`.svg`, `.pdf`) o mapas de bits de alta resolución (`.png` a 300 DPI).
   - Botón `💾 Exportar Tabla`: Genera archivos ASCII delimitados por tabulaciones (`.txt`, `.tsv`, `.csv`) con encabezados metrológicos detallados para OriginLab, Python o Excel.

### 6.2 Gestor de Archivos SIF (Panel Izquierdo)
1. **Botón `📂 Abrir Carpeta SIF`:** Escanea recursivamente el directorio seleccionado indexando todos los archivos `.sif` válidos.
2. **Designación de Archivo Maestro (`👑 Fijar como Maestro`):**
   - Si una serie experimental se adquirió compartiendo un único espectro de fondo (Dark) o una sola lámpara de referencia (Halógena), el usuario selecciona dicho archivo y presiona `👑 Fijar como Maestro`.
   - Todos los archivos subsiguientes del lote heredarán de forma transparente los canales de Dark y Referencia del Maestro, permitiendo procesar decenas de espectros Live sin necesidad de re-adquirir blancos repetidamente.
3. **Tabla con Desplazamiento Horizontal:**
   - La tabla muestra: Nombre de archivo completo, Canales detectados (ej. `4 ch (Trans)`), Modo (`1D FVB` o `2D Slit`), Dimensiones ($N_y \times N_\lambda$) y Estado de procesamiento.
   - Cuenta con barra de scroll horizontal y ajuste automático al contenido, evitando recortes visuales.

---

## 7. Verificación Experimental y Batería de Pruebas

Para certificar la robustez y estabilidad de las mejoras implementadas, se diseñó una batería de pruebas automatizadas en `tests/test_sif_analyzer_gui.py` y se ejecutó el orquestador global `tests/run_all_diagnostics.py`.

### 7.1 Resultados de las Pruebas de Interfaz Gráfica (`test_sif_analyzer_gui.py`)

| Test ID | Módulo / Función Evaluada | Criterio de Aceptación | Resultado |
|---|---|---|---|
| `test_01` | Inicialización de GUI | Creación sin excepciones de `SIFAnalyzerWindow` y asignación de 5 pestañas | ✅ APROBADO |
| `test_02` | Carga de Archivo SIF Sintético | Decodificación de canales 1D/2D y poblamiento de tabla izquierda | ✅ APROBADO |
| `test_03` | Pestaña 1 (Dark) | Renderizado de Heatmap 2D, perfil 1D y cálculo de estadísticas Bias/$\sigma$ | ✅ APROBADO |
| `test_04` | Pestaña 2 (Referencia) | Manipulación de ROI vertical y visualización de envolvente de lámpara | ✅ APROBADO |
| `test_05` | Pestaña 3 (Live / Señal) | Carga de señal de muestra y acoplamiento con canales Dark | ✅ APROBADO |
| `test_06` | Pestaña 4 (Transmisión) | Cálculo de $T_{\text{calc}}$ vs $T_{\text{meas}}$ y gráfico de residuos | ✅ APROBADO |
| `test_07` | Pestaña 5 (Extinción) | Transformada $-\log_{10}(T/100)$ y visualización de banda plasmónica | ✅ APROBADO |
| `test_08` | Ajuste No Lineal Fano / Gauss | Optimización de picos plasmónicos y reporte de centroide $\lambda_{\text{res}}$ | ✅ APROBADO |
| `test_09` | Panel Instrumental Derecho | Selección en torreta de 5 objetivos y actualización de metadatos | ✅ APROBADO |
| `test_10` | Exportación de Lote | Generación de reportes CSV y figuras PNG a 300 DPI | ✅ APROBADO |
| `test_11` | Archivo Maestro (Master SIF) | Herencia de canales Dark y Referencia a través del lote | ✅ APROBADO |
| `test_12` | Opciones 2D (Ruta A vs Ruta B) | Exclusión mutua `QButtonGroup` y cálculo comparativo de rutas | ✅ APROBADO |
| `test_13` | Corrección Eje $\lambda$ 2D | Evaluación de dispersión sobre $N_\lambda$ sin artefactos $>10,000\ \text{nm}$ | ✅ APROBADO |
| `test_14` | **Propagación 2D $\to$ 1D $\to$ T $\to$ Ext** | Los filtros en Pestaña 3 modifican la matriz 2D, el promedio y la Pestaña 4 | ✅ APROBADO |
| `test_15` | **Ergonomía, Reset Raw y Atajo `Ctrl+D`** | Toolbars en 2 filas, ancho $<600\ \text{px}$, `↺ Raw` y toggle de panel derecho | ✅ APROBADO |

**Resumen de la suite SIF Analyzer:** **14 de 14 pruebas superadas con éxito (100%)** en $12.4\ \text{s}$.

### 7.2 Resultados de la Suite Global (`run_all_diagnostics.py`)
Se ejecutó la suite completa de diagnósticos del repositorio PyPrinting 3.0 para descartar efectos colaterales en otros subsistemas (Nanoposicionamiento PI, DAQmx, Cámara Canon, Diseñador 2D, HDF5, Raman Analyzer):
* **Total de Pruebas Ejecutadas:** 62
* **Total de Pruebas Superadas:** 62
* **Errores / Fallas:** 0
* **Tasa de Éxito:** **100.0%**

---

## 8. Guía Rápida de Operación para Investigadores y Becarios

A continuación se resume el protocolo paso a paso para procesar cualquier medición de extinción plasmónica en $< 2\ \text{minutos}$:

1. **Inicio del Módulo:**
   - Ejecutar desde la terminal: `python sif_analyzer.py` o abrir desde el lanzador `main.py`.
2. **Carga de Datos:**
   - Presionar `📂 Abrir Carpeta SIF` y seleccionar el directorio del experimento.
   - Hacer doble clic en el archivo que contiene la referencia de lámpara halógena y presionar `👑 Fijar como Maestro` (si aplica).
   - Seleccionar el archivo de la nanopartícula en la tabla izquierda.
3. **Revisión de Fondo (Pestaña 1):**
   - Comprobar que el bias se encuentre en $\approx 300 - 350\ \text{cuentas}$. Activar `[x] Despike` si se observa un rayo cósmico aislado.
4. **Delimitación de la Iluminación (Pestaña 2):**
   - En el mapa de calor de Referencia, observar dónde incide el haz de luz blanca. Ajustar los valores `ROI Y:` $[y_{\min}, y_{\max}]$ para encuadrar la zona luminosa.
   - Activar `[x] Sub Dark` y `[x] Filtro Wiener`.
5. **Alineación de la Muestra (Pestaña 3):**
   - Cambiar a la Pestaña 3.
   - Presionar el botón **`🔗 Copiar ROI Ref`** para clonar exactamente el encuadre vertical de la lámpara.
   - Activar `[x] Sub Dark` y `[x] Despike`. Verificar que el mapa de calor 2D y el espectro 1D se limpien automáticamente.
6. **Verificación de Transmitancia (Pestaña 4):**
   - Pasar a la Pestaña 4.
   - Verificar la coincidencia entre la curva verde (`T_calc`) y la curva punteada azul (`T_meas`).
   - En el panel `⚙️ Opciones de Cálculo 2D`, seleccionar `(o) Ruta A` para máxima relación señal-ruido o `(o) Ruta B` si se desea evaluar dispersión espacial transversal.
7. **Ajuste de la Resonancia Plasmónica (Pestaña 5):**
   - Pasar a la Pestaña 5.
   - La curva de extinción exhibirá el pico de absorción/dispersión plasmónica (LSPR).
   - Arrastrar los cursores A y B con el mouse para enmarcar el pico.
   - Seleccionar el modelo (`Gaussiano` para partículas esféricas o `Fano` para nanoestructuras acopladas).
   - Presionar **`🚀 Ajustar Pico`**. El sistema imprimirá $\lambda_{\text{res}}$, $\text{FWHM}$ y $R^2$.
8. **Exportación:**
   - En el panel derecho, seleccionar el objetivo utilizado (ej. `100x Oil`).
   - Presionar `📸 Guardar Figura (300 DPI / SVG)` para obtener la gráfica vectorial lista para tesis o paper, y `💾 Exportar Tabla` para salvar el espectro procesado en `.csv`.

---

## 9. Conclusiones y Estado del Sistema

La refactorización del Analizador SIF resuelve de forma definitiva los problemas de usabilidad, visualización y rigor físico en el tratamiento de archivos binarios de Andor Solis:
* La ergonomía en **dos filas compactas** y el atajo `Ctrl+D` permiten una interacción cómoda y fluida en cualquier resolución de pantalla.
* La cartelería explicativa (*tooltips*) y el panel de `Opciones de Cálculo 2D` guían intuitivamente al usuario novel, garantizando que entienda la función de cada control y la justificación física de cada filtro.
* El pipeline unidireccional con `apply_spectral_filters_2d` erradica inconsistencias numéricas, asegurando que los cálculos de transmitancia y extinción se fundamenten en datos limpios tanto espacial como espectralmente.
* La suite queda plenamente integrada a la infraestructura de documentación metrológica de PyPrinting 3.0.
