# Manual de Usuario Exhaustivo: PyPrinting 3.0 🔬
**Suite de Control, Espectroscopía Confocal, Caracterización de PSF y Nanofabricación Óptica**
*Laboratorio de Nanofotónica — Instituto de Nanosistemas (INS-UNSAM)*
*Autor Principal: José Luis González Peñafiel (Becario Doctoral CONICET)*

---

## 📖 Índice General

1. [Panel de Inicio Principal (`main.py` — "Bienvenidos al printing")](#1-panel-de-inicio-principal-mainpy--bienvenidos-al-printing)
   - [1.1 Visión General, Filosofía de Diseño y Arquitectura Multihilo](#11-visión-general-filosofía-de-diseño-y-arquitectura-multihilo)
   - [1.2 Selección Global de Modo Seguro (`SAFE_MODE`) vs. Modo Laboratorio Real](#12-selección-global-de-modo-seguro-safe_mode-vs-modo-laboratorio-real)
   - [1.3 Navegación e Índice de Módulos en Grilla Simétrica $3 \times 3$](#13-navegación-e-índice-de-módulos-en-grilla-simétrica-3-times-3)
2. [Fundamentos Físicos, Formulación Matemática & Mapeo de Hardware](#2-fundamentos-físicos-formulación-matemática--mapeo-de-hardware)
   - [2.1 Impresión Óptica Fototérmica de Nanopartículas Coloidales](#21-impresión-óptica-fototérmica-de-nanopartículas-coloidales)
   - [2.2 Ensamblado Guiado de Nanodímeros Plasmónicos y Campo Cercano](#22-ensamblado-guiado-de-nanodímeros-plasmónicos-y-campo-cercano)
   - [2.3 Modelo Analítico Gaussiano 2D Anisotrópico de 7 Parámetros](#23-modelo-analítico-gaussiano-2d-anisotrópico-de-7-parámetros)
   - [2.4 Modelo Analítico Haz Vortex / Donut (Laguerre-Gauss $LG_{01}$)](#24-modelo-analítico-haz-vortex--donut-laguerre-gauss-lg_01)
   - [2.5 Métricas Analíticas y Alineación Sub-nanométrica de PSF](#25-métricas-analíticas-y-alineación-sub-nanométrica-de-psf)
   - [2.6 Operación de Umbralización No Lineal de Ruido ($P\%$)](#26-operación-de-umbralización-no-lineal-de-ruido-p)
   - [2.7 Algoritmo de Estabilización Z Axial por Autocorrelación de Pearson](#27-algoritmo-de-estabilización-z-axial-por-autocorrelación-de-pearson)
   - [2.8 Mapeo Físico de Coordenadas y Calibración de Platina Piezoeléctrica PI](#28-mapeo-físico-de-coordenadas-y-calibración-de-platina-piezoeléctrica-pi)
3. [Módulo 1: Microscopio Derecho (`app.py` — PyPrinting 3.0 Suite Completa)](#3-módulo-1-microscopio-derecho-apppy--pyprinting-30-suite-completa)
   - [3.1 Menú Principal (`Files`, `Tools`, `Measurements`, `Help`)](#31-menú-principal-files-tools-measurements-help)
   - [3.2 Dock: Confocal (Mapeo 2D/3D & Algoritmos de Centrado)](#32-dock-confocal-mapeo-2d3d--algoritmos-de-centrado)
   - [3.3 Dock: Trace (Trazas Temporales & Calibración Power BS)](#33-dock-trace-trazas-temporales--calibración-power-bs)
   - [3.4 Dock: Focus z (Autofoco Axial Dinámico)](#34-dock-focus-z-autofoco-axial-dinámico)
   - [3.5 Dock: Shutters / Flipper / Láser 532](#35-dock-shutters--flipper--láser-532)
   - [3.6 Dock: Nanopositioning (Platina Piezoeléctrica PI)](#36-dock-nanopositioning-platina-piezoeléctrica-pi)
   - [3.7 Ventana de Mediciones (Printing Automatizado de Grillas & Dímeros)](#37-ventana-de-mediciones-printing-automatizado-de-grillas--dímeros)
4. [Módulo 2: PySpectrum *(En Construcción)*](#4-módulo-2-pyspectrum-en-construcción)
5. [Módulo 3: Microscopio Contrapropagante](#5-módulo-3-microscopio-contrapropagante)
6. [Módulo 4: PyPrinting 2 (Legacy — `PyPrinting_UNSAM.py`)](#6-módulo-4-pyprinting-2-legacy--pyprinting_unsampy)
7. [Módulo 5: Cámara Live View (`camera.py` — Suite Canon EDSDK & Microfotónica)](#7-módulo-5-cámara-live-view-camerapy--suite-canon-edsdk--microfotónica)
   - [7.1 Motor de Transmisión Live View Adaptativo a 25 FPS](#71-motor-de-transmisión-live-view-adaptativo-a-25-fps)
   - [7.2 Captura Fotográfica 15.1 MP Multi-Formato & Nombres Únicos](#72-captura-fotográfica-151-mp-multi-formato--nombres-únicos)
   - [7.3 Transferencia en RAM MemoryStream (Inmune a Errores 0x000000AB)](#73-transferencia-en-ram-memorystream-inmune-a-errores-0x000000ab)
   - [7.4 Navegación Panorámica FOV (Ejes X / Y) & Ajustes de Imagen](#74-navegación-panorámica-fov-ejes-x--y--ajustes-de-imagen)
   - [7.5 Capa OverlayWidget: Reglas µm, Platina PI, ROI Confocal & Tracking](#75-capa-overlaywidget-reglas-µm-platina-pi-roi-confocal--tracking)
   - [7.6 Visor Emergente Desplegable de Diagnóstico EDSDK (`EDSDKLogDialog`)](#76-visor-emergente-desplegable-de-diagnóstico-edsdk-edsdklogdialog)
8. [Módulo 6: Modulación Láser 532 nm (`Laser532Window`)](#8-módulo-6-modulación-láser-532-nm-laser532window)
9. [Módulo 7: PSF Analyzer (`psf_analyzer.py`)](#9-módulo-7-psf-analyzer-psf_analyzerpy)
10. [Módulo 8: Analizador de Imágenes Estáticas (`image_analyzer.py`)](#10-módulo-8-analizador-de-imágenes-estáticas-image_analyzerpy)
11. [Módulo 9: Documentación y Créditos del Autor](#11-módulo-9-documentación-y-créditos-del-autor)
12. [Tabla Completa de Parámetros Globales (`config.py`)](#12-tabla-completa-de-parámetros-globales-configpy)
13. [Flujos de Trabajo Experimentales (Protocolos Paso a Paso)](#13-flujos-de-trabajo-experimentales-protocolos-paso-a-paso)
14. [Tabla de Atajos de Teclado (Shortcuts)](#14-tabla-de-atajos-de-teclado-shortcuts)
15. [Guía de Resolución de Problemas y Diagnóstico (Troubleshooting)](#15-guía-de-resolución-de-problemas-y-diagnóstico-troubleshooting)
16. [Preguntas Frecuentes (FAQ)](#16-preguntas-frecuentes-faq)

---

## 1. Panel de Inicio Principal (`main.py` — "Bienvenidos al printing")

### 1.1 Visión General, Filosofía de Diseño y Arquitectura Multihilo
La suite **PyPrinting 3.0** está construida sobre una arquitectura modular desacoplada basada en **Python 3 / PyQt6** y **`pyqtgraph`**. Para evitar cuelgues de la interfaz gráfica durante operaciones de hardware de alta frecuencia, la aplicación utiliza un patrón **Frontend / Backend** con hilos dedicados (`QThread` y `moveToThread`).

---

## 7. Módulo 5: Cámara Live View (`camera.py` — Suite Canon EDSDK & Microfotónica)

El botón **`📷 Iniciar Cámara Live View`** (Fila 2, Columna 2 del lanzador `main.py`) o el comando `python camera.py` ejecutan la suite integrada de visión réflex nativa y herramientas de microfotónica:

### 7.1 Motor de Transmisión Live View Adaptativo a 25 FPS
- **Warm-up de 5 Segundos**: Durante los primeros 5 segundos tras presionar `Iniciar Cámara Canon`, las consultas masivas de ISO y Tv se bloquean temporalmente mientras el hardware réflex inicializa el espejo y la salida de video. El sistema emite la lista completa de propiedades para asegurar disponibilidad inmediata en la UI.
- **Temporización Monodisparo Adaptativa (`_fetch_frame_adaptive`)**:
  Utiliza marcas de tiempo en microsegundos (`time.perf_counter()`) para calcular dinámicamente el tiempo de descanso:
  $$\text{delay\_ms} = \max\left(1, \text{int}(40.0 - t_{\text{procesamiento\_ms}})\right)$$
  Esto garantiza una velocidad constante de **25.0 FPS (40.0 ms por cuadro)** sin acumulación de cuadros en el búfer USB, eliminando congelamientos o aceleraciones bruscas.

### 7.2 Captura Fotográfica 15.1 MP Multi-Formato & Nombres Únicos
- **Resolución Nivel Réflex de 15.1 Megapíxeles (4752×3168)**:
  Permite seleccionar el formato de salida deseado mediante el desplegable `Formato de Salida`:
  - **JPG**: Máxima resolución nativa del sensor (comprimido JPEG de alta calidad).
  - **PNG**: Formato sin pérdida de calidad para metrología digital.
  - **TIFF**: Formato cuantitativo sin pérdida de 15.1 MP.
  - **BMP**: Mapa de bits sin comprimir.
- **Pausa Automática del Stream Live View**: Al obturar, la emisión EVF se pausa automáticamente durante 350 ms para liberar recursos del chip DIGIC 4 y evitar bloqueos en el espejo mecánico réflex.
- **Garantía de Nombres Únicos (`get_unique_save_path`)**:
  Las fotos se nombran con fecha y hora (`CANON_EOS500D_YYYYMMDD_HHMMSS.[ext]`). Si ya existe un archivo con ese nombre en la carpeta seleccionada, el algoritmo añade automáticamente un prefijo contador (`_01`, `_02`), impidiendo la sobreescritura accidental.

### 7.3 Transferencia en RAM MemoryStream (Inmune a Errores `0x000000AB` y `0x00000061`)
- **Descarga Directa a Memoria RAM**: En lugar de requerir que el SDK de Canon abra y cree archivos de disco (lo cual provocaba errores de formato de ruta `0x000000AB` en Windows de 64 bits), la imagen se descarga directamente desde la cámara réflex a un `EdsCreateMemoryStream` en la memoria RAM del sistema.
- **Escritura Binaria Nativa en Python**: Python lee el arreglo de bytes de la RAM (`ctypes.string_at`) y escribe el archivo directamente en el disco duro (`open(save_path, "wb").write(raw_bytes)`), garantizando un 100% de confiabilidad en la transferencia de archivos.
- **Firma de Punteros de 64 Bits (`ctypes.c_wchar_p`)**: Se definieron firmas explícitas para la DLL C++ de Canon, evitando la truncación de punteros de memoria de 64 bits (`OverflowError`) y corrigiendo la excepción de tipos `c_char_p`.

### 7.4 Navegación Panorámica FOV (Ejes X / Y) & Ajustes de Imagen
- **Zoom Digital / Hardware (1x, 2x, 5x, 10x)**: Permite ampliar regiones de interés en tiempo real.
- **Navegación FOV (Sliders X / Y)**: Permite desplazar el centro de visión ($cx, cy \in [0.0, 1.0]$) a cualquier coordenada del sensor de 15.1 MP para inspeccionar nanopartículas fuera del centro.
- **Ajustes de Imagen en Vivo**:
  - **Modo Color RGB**: Deslizadores de ganancia para Rojo, Verde y Azul.
  - **Modo Grises (Transmisión)**: Deslizadores de corte de intensidad `CLim Mín / Máx`.
  - **Paletas LUT Falso Color**: Aplica mapas cromáticos en tiempo real (*Gris Estándar*, *Thermal*, *Viridis*, *Plasma*, *Inferno*, *Jet*).

### 7.5 Capa OverlayWidget: Reglas µm, Platina PI, ROI Confocal & Tracking
- **Reglas H/V en µm**: Reglas orientables en pantalla calibradas en micrómetros según `PIXEL_SIZE_UM`.
- **Cursor de Platina PI (`Cursor_pp`)**: Muestra en tiempo real la posición del cursor de la platina nano-posicionadora PI sobre la imagen.
- **Medición 2 Puntos**: Muestra la distancia proyectada ($\mu\text{m}$) y el ángulo ($\theta^\circ$) entre dos clics en pantalla.
- **ROI → Confocal**: Permite dibujar un rectángulo de interés y enviarlo directamente como coordenadas de escaneo al módulo confocal (`sendRoiSignal`).
- **Detección de Partículas**: Integra detección puntual (`psf.py` / `trackpy`) y tabla interactiva de coordenadas ($x, y, \sigma$).
- **Control Láser 532 nm**: Botón que abre la ventana flotante `Laser532Window` para modulación de voltaje DAC ($1.0 - 5.0\ \text{V}$) y obturación verde.

### 7.6 Visor Emergente Desplegable de Diagnóstico EDSDK (`EDSDKLogDialog`)
- El panel de mensajes de diagnóstico EDSDK se aloja en una ventana modal emergente desplegable que no ocupa espacio en el panel principal. Se abre presionando el botón **`📜 Ver Log de Diagnóstico EDSDK`**.

---

## 15. Guía de Resolución de Problemas y Diagnóstico (Troubleshooting)

### 15.1 La cámara réflex Canon no inicia Live View o arroja error de sesión
* **Causa**: La cámara se apaga automáticamente por ahorro de energía o la sesión USB EDSDK se cerró incorrectamente.
* **Solución**: Apague y encienda la cámara Canon EOS 500D, verifique que el dial esté en modo **M (Manual)** y vuelva a presionar **`Iniciar Cámara Canon`**.

### 15.2 La foto tomada reporta un aviso pero se guarda en disco
* **Causa**: El sensor réflex tardó en liberar el evento de creación de archivo USB.
* **Solución**: El módulo unificado `camera.py` ejecuta automáticamente la exploración directa del volumen de la cámara réflex (`_download_newest_photo_from_camera`) y recupera la foto nativa en la PC sin pérdida de datos.

### 15.3 Al disparar una foto, el video en vivo se acelera brevemente
* **Causa**: Reinicio abrupto del reloj de cuadros en el hilo de trabajo.
* **Solución**: La versión actual resetea `_connect_time` y aplica una pausa de 400 ms post-captura, asegurando que la transmisión retome suavemente a 25 FPS sin ráfagas de aceleración.

---

*Manual de Usuario Exhaustivo de PyPrinting 3.0 — Laboratorio de Nanofotónica, Instituto de Nanosistemas (INS-UNSAM).*
*Autor Principal: José Luis González Peñafiel (Becario Doctoral CONICET).*
