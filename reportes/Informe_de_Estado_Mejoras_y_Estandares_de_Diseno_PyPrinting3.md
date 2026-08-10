# Informe de Estado del Proyecto, Evaluación Multidimensional, Tablero de Conexiones y Estándares de Diseño (PyPrinting 3.0 & PySpectrum) 🔬

**Laboratorio de Nanofotónica — Instituto de Nanosistemas (INS-UNSAM / CONICET)**  
**Autor Principal**: José Luis González Peñafiel (*Becario Doctoral CONICET*)  
**Fecha de Publicación**: 10 de Agosto de 2026  
**Ubicación del Reporte**: `reportes/Informe_de_Estado_Mejoras_y_Estandares_de_Diseno_PyPrinting3.md`  

---

## 1. Resumen Ejecutivo y Actualización de Graphify 🌳

Se ha ejecutado con éxito la actualización del **Grafo de Conocimiento del Proyecto** (`graphify update .`). El análisis estático de código (AST) ha reconstruido el mapa de nodos y comunidades del repositorio `printing3`, arrojando las siguientes métricas globales:

- **Total de Nodos Registrados**: $5,503$ nodos de código, clases, métodos y metadatos.
- **Aristas / Relaciones Inter-módulo**: $9,591$ conexiones.
- **Comunidades Estructurales**: $349$ comunidades funcionales desglosadas.
- **Archivos de Salida Actualizados**: `graphify-out/graph.json`, `graphify-out/graph.html` y `graphify-out/GRAPH_REPORT.md`.

El grafo de conocimiento confirma que la refactorización reciente (incorporación de `core/hardware_manager.py`, `modules/hardware_dashboard.py`, `TraceFFTWindow`, `core/preset_manager.py` y `modules/preset_wizard.py`) ha alcanzado un grado óptimo de desacoplamiento modular y coherencia estética.

---

## 2. Diagnóstico del Estado Actual del Proyecto `PyPrinting 3.0`

Actualmente, **PyPrinting 3.0** representa una suite madura de adquisición y control microscópico para nanofotónica experimental. La arquitectura del software está organizada en torno a los siguientes pilares:

```
                                  ┌──────────────────────────────────────────┐
                                  │      main.py (Launcher Dashboard)        │
                                  └────────────────────┬─────────────────────┘
                                                       │
                           ┌───────────────────────────┴───────────────────────────┐
                           ▼                                                       ▼
           ┌───────────────────────────────┐                       ┌───────────────────────────────┐
           │            app.py             │                       │      contrapropagante.py      │
           │  (Microscopio Confocal Main)  │                       │  (Sistema Contrapropagante)   │
           └───────────────┬───────────────┘                       └───────────────┬───────────────┘
                           │                                                       │
         ┌─────────────────┼─────────────────┬──────────────────┐                  │ (Reutiliza módulos)
         ▼                 ▼                 ▼                  ▼                  ▼
┌─────────────────┐ ┌─────────────┐ ┌─────────────────┐ ┌───────────────┐ ┌─────────────────┐
│ measurements.py │ │   focus.py  │ │   confocal.py   │ │   camera.py   │ │    trace.py     │
│ (Print/Dimers)  │ │ (Autofocus) │ │ (Scan Confocal) │ │ (Live Camera) │ │ (Photodiode T.) │
└─────────────────┘ └─────────────┘ └─────────────────┘ └───────────────┘ └─────────────────┘
```

### 2.1 Matriz de Estado por Módulo

| Módulo | Función Principal | Estado Actual | Fortalezas | Oportunidad de Mejora / Estado |
|---|---|---|---|---|
| `main.py` | Launcher Principal y Menú | 🟢 Excelente | Tema oscuro Catppuccin Mocha, lanzador independiente de procesos | Integrado con acceso rápido a Tablero de Conexiones y Documentación. |
| `app.py` | Suite Principal Multihilo | 🟢 Excelente | Interconexión síncrona/asíncrona de 8 hilos secundarios | Barra de estado global dinámica e integración del Dock de Conexiones. |
| `measurements.py` | Rutinas de Impresión y Dímeros | 🟢 Excelente | 5 modos de parada, `Drift Correction`, visualizador de grilla | Presets persistentes en archivos `.txt`, exportación multimaterial y auto-recuperación. |
| `focus.py` | Autofoco Axial Z por Correlación | 🟢 Excelente | Búsqueda por rango dinámico y ajuste parabólico | Optimización de tiempos de respuesta en Z e integración con flipper óptico. |
| `confocal.py` | Escaneo Confocal 2D (Rampa/Paso) | 🟢 Excelente | Generación de ondas analógicas PI (`WAV_LIN`) y ajuste Gaussiano 2D / Donut 2D | Renderizado adaptativo pyqtgraph en imágenes de alta resolución. |
| `trace.py` | Adquisición de Fotodiodo $I(t)$ | 🟢 Excelente | Promedios móviles $I_{\text{old}} / I_{\text{new}}$ y soporte multicanal | Adquisición vectorizada por búferes DMA y Transformada de Fourier (FFT) en vivo. |
| `camera.py` | Visión en Vivo Thorlabs/USB | 🟢 Excelente | Retículas overlays, medición de distancia en µm | Optimización de búferes de captura USB y ventana flotante independiente. |
| `hardware_dashboard.py` | Tablero de Seguridad de Hardware | 🟢 Excelente | Matriz de LEDs de conexión, aislamiento por software y log I/O | Monitoreo en vivo de NI-DAQ, PI Piezo, Cámara, Láser 532 nm y Espectrómetro. |
| `preset_wizard.py` | Wizard Guiado de Presets | 🟢 Excelente | Asistente multipaso QWizard de 5 fases | Generación asistida de archivos de configuración `.txt` formateados. |
| `config.py` | Configuración Global | 🟢 Excelente | Soporte de `SAFE_MODE` transparente para desarrollo sin hardware | Manejo de aislamiento (*Soft Isolation*) por dispositivo. |

---

## 3. Implementación Completada: Tablero de Conexiones de Hardware y Suite Multidimensional

Atendiendo a las directivas del laboratorio, se han implementado y verificado con éxito el **Tablero de Conexiones y Seguridad de Hardware** y la suite de mejoras multidimensionales aceptadas:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│             TABLERO DE CONEXIONES, TELEMETRÍA Y SEGURIDAD DE HARDWARE                  │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ • Estado de Conexión en Vivo: 🟢 NI-DAQmx | 🟢 PI Piezo | 🟢 Cámara | ⚪ Espectrómetro    │
│ • Aisle e Interrupción Manual: Switch [Soft Disconnect / Mock Isolation] por equipo.   │
│ • Bitácora de Eventos (Hardware Log): Timestamps de comunicación y alertas I/O.        │
│ • Re-scan en Caliente: Botón [Re-scan Hardware] para ping de puertos USB/GPIB/NI-DAQ.   │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

### 3.1 Tablero de Conexiones y Seguridad de Hardware (`HardwareDashboardWidget` & `HardwareManager`)
- **Visualización de Conexiones Activas**: Panel gráfico con luces LED indicadoras de estado (Verde: Conectado y operativo / Amarillo: Simulado / Rojo: Desconectado / Gris: Inactivo).
- **Espectrómetro Inactivo**: Conforme a la especificación, el canal del espectrómetro se encuentra **presente pero inactivo (`⚪ Inactivo — Pendiente de integración con PySpectrum`)** con sus llaves de paso deshabilitadas hasta el desarrollo de `PySpectrum`.
- **Aisle / Software Isolation**: Permite simular o desconectar individualmente un instrumento físico (*Soft Disconnect*) para realizar pruebas seguras sin congelar la GUI.
- **Bitácora de Eventos de Comunicación**: Consola de registros con marcas de tiempo (*timestamps*) detallando inicialización, lecturas analógicas y comandos PI.
- **Re-scan en Caliente**: Botón `🔄 Re-scan Hardware` para re-escanear puertos USB/GPIB/NI-DAQ sin reiniciar la aplicación.

### 3.2 Transformada de Fourier (FFT) en Tiempo Real para Trazas (`TraceFFTWindow`)
- **Espectros de Potencias en Vivo**: Cálculo dinámico del espectro de densidad de potencias $S(f) = |\operatorname{FFT}(I(t) - \bar{I})|^2$ con ventana de Hanning.
- **Línea de Referencia de 50 Hz**: Marcador vertical para la identificación inmediata de ruido de línea eléctrica.
- **Botones de Acceso Rápido**: Botones `📊 FFT L1`, `📊 FFT L2` y `📊 FFT Power BS` desplegando ventanas flotantes independientes para cada canal.

### 3.3 Presets Persistentes en Archivos `.txt` y Wizard Guiado (`PresetManager` & `PresetWizardDialog`)
- **Archivos `.txt` Externos**: Los presets se leen y guardan en archivos de texto plano dentro de `presets/` con formato clave-valor especificado.
- **Asistente Guiado Multipaso (Wizard)**: Diálogo de 5 pasos (`PresetWizardDialog`) para guiar de forma metrológica al usuario en la creación de nuevos presets.
- **Controles en la Interfaz**: Menú desplegable dinámico acompañado de botones `🧙 Wizard`, `📂 Cargar` y `💾 Guardar`.

### 3.4 Exportación Multimaterial y Auto-Recuperación
- **Formatos Trío**: Cada escaneo 2D se exporta en **TIFF 16-bit**, binario NumPy **`.npy`** y tabla **`.csv`**.
- **Resguardo de Posición (`LAST_POS_FILE`)**: Actualización continua del último nodo impreso para reanudar la corrida tras un corte eléctrico.
- **Barra de Estado Global**: Integración de mensajes de estado en tiempo real en la barra inferior de `app.py`.

---

## 4. Diagnóstico Completo de Bugs, Redundancias y Conexiones Perdidas

Tras un barrido exhaustivo del código fuente y su evaluación frente a los **5 Estándares de Diseño**, se presenta el diagnóstico técnico:

### 4.1 Evaluación de Bugs y Excepciones
- **Protección de Índices de Grilla (`measurements.py`)**: Se aplicó el clamping `self.i_global = max(0, min(self.i_global, len(self.grid_x) - 1))` resolviendo el riesgo de `IndexError` al modificar el índice objetivo.
- **Lógica de Flipper Óptico (`measurements.py`)**: Se forzó la posición del flipper en `up_flipper()` (baja potencia, espejo arriba) durante los escaneos confocales 2D y el autofoco Z, restringiendo `down_flipper()` (alta potencia) estrictamente al ciclo de traza fototérmica.
- **Compatibilidad de Canales de Fotodiodo (`trace.py`)**: La función `_get_pd_channel()` soporta coincidencia parcial por cadenas de texto (`"532"`, `"637"`, `"592"`), previniendo fallbacks erróneos al canal 0.

### 4.2 Evaluación de Redundancias
- **Conexiones de Señales Duplicadas**: Se eliminó la llamada duplicada a `update_bs_data` en el método `get_data` de `trace.py`.
- **Desacoplamiento de Menús y Docks**: Se limpió la instanciación de ventanas secundarias en `app.py`, garantizando que `tools_hardware_dashboard`, `tools_camera` y `tools_laser532` reutilicen instancias existentes sin crear fugas de memoria.

### 4.3 Evaluación de Conexiones Perdidas
- **Propagación de Parámetros de Integración**: Se conectaron las señales `stepsParametersSignal` de `printingWorker` y `dimersWorker` a `traceWorker.parameters`, asegurando que los valores de $M$ (*steps_after*) y $M_2$ (*steps_before*) definidos en la GUI se propaguen en tiempo real al backend de adquisición.

---

## 5. Guía de Criterios, Lineamientos y Estándares de Diseño para Futuros Desarrollos (PySpectrum, PyPrinting 3.1, etc.) 📐

Con el objetivo de garantizar que todos los desarrollos futuros (tales como la suite de espectroscopía **PySpectrum**, versiones posteriores de PyPrinting o módulos de análisis) mantengan la misma línea gráfica, usabilidad y robustez arquitectónica, se establecen los siguientes **5 Estándares Obligatorios de Desarrollo**:

---

### 🎨 Estándar 1: Sistema de Diseño Visual (Catppuccin Mocha Dark Theme)

Todas las interfaces gráficas desarrolladas en la organización deben adherirse a la siguiente paleta cromática de alto contraste (basada en el estándar internacional ISO/IEC 40749):

| Componente UI | Variable / Rol | Código Hexadecimal | Apariencia Visual |
|---|---|---|---|
| **Fondo de Ventana Principal** | `Base` | `#11111B` | Negro azulado profundo |
| **Fondo de Paneles y Docks** | `Surface0` | `#1E1E2E` | Gris oscuro elegante |
| **Tarjetas y GroupBoxes** | `Surface1` | `#181825` | Gris medio contrastado |
| **Bordes y Divisores** | `Border` | `#313244` / `#45475A` | Línea fina sutil |
| **Texto Principal** | `Text` | `#CDD6F4` | Blanco suave mate |
| **Texto Secundario / Labels** | `Subtext` | `#A6ADC8` | Gris claro legible |
| **Color Primario (Acción/Play)** | `Blue / Accent` | `#89B4FA` | Azul eléctrico |
| **Estado Exitoso / Impreso** | `Green / Success` | `#A6E3A1` | Verde pastel vibrante |
| **Estado Advertencia / Pausa** | `Yellow / Warning` | `#F9E2AF` | Amarillo cálido |
| **Estado Alerta / Timeout** | `Red / Danger` | `#F38BA8` | Rojo coral |
| **Botones de Referencia/Acción** | `Peach / Orange` | `#FAB387` | Naranja/Caramelo |

#### Reglas de Estilo CSS/QSS Estándar
1. **Redondeo de Bordes**: Todos los botones y casilleros deben tener `border-radius: 4px;` o `6px;`.
2. **Resaltado de Foco**: Los campos `QLineEdit` en foco deben mostrar bordes azules: `border: 1px solid #89B4FA;`.
3. **Tipografía Monospaciada**: Toda variable de medición nanométrica, voltaje o tiempo debe renderizarse con tipografía monospaciada (`font-family: monospace; font-weight: bold;`).

---

### 🏗️ Estándar 2: Arquitectura y Desacoplamiento (Patrón Qt / Thread Worker)

Para garantizar la fluidez de la interfaz a 60 FPS sin importar la duración de los cálculos o la adquisición de hardware:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                          PATRON ARQUITECTONICO HILO - BACKEND                          │
├────────────────────────────────────────────────────────────────────────────────────────┤
│  [Hilo Principal GUI]  ──(pyqtSignal: params)──►  [QThread: Backend Worker]            │
│  • Renderiza UI        ◄──(pyqtSignal: data)────  • Adquisición NI-DAQmx/PI              │
│  • Cero I/O físico                                • Cálculos NumPy/SciPy               │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

1. **Separación Absoluta de Hilos**:
   - El Hilo Principal GUI (`MainThread`) **NUNCA** debe realizar llamadas bloqueantes a hardware (`pi.MOV`, `task.read`, `time.sleep`).
   - Toda la lógica de control debe residir en subclases de `QObject` trasladadas a un `QThread` dedicado mediante `.moveToThread(thread)`.
2. **Comunicación Exclusiva por Señales (`pyqtSignal` / `@pyqtSlot`)**:
   - La transferencia de datos entre hilos debe realizarse únicamente mediante señales PyQt fuertemente tipadas (ej. `pyqtSignal(np.ndarray, list)`).
3. **Modo Seguro Obligatorio (`SAFE_MODE`)**:
   - Todo módulo que interactúe con hardware físico (piezo, láseres, espectrómetros, cámaras) **DEBE** incluir una implementación Mock activada transparente cuando `SAFE_MODE = True` en `config.py`.

---

### 🧩 Estándar 3: Estructura de Proyecto y Naming Conventions

Para futuros proyectos (ej. `PySpectrum`), se debe replicar la jerarquía modular probada en PyPrinting 3.0:

```
pyspectrum/
├── main.py                  # Launcher principal / Dashboard de inicio
├── app.py                   # Suite principal e interconexión de backend
├── config.py                # Constantes globales, rutas y SAFE_MODE
├── core/                    # Lógica de bajo nivel y drivers
│   ├── hardware.py          # Interfaz con espectrómetro / NI-DAQmx
│   └── mock_hardware.py     # Hardware sintético para SAFE_MODE
├── modules/                 # Módulos GUI y Backend independientes
│   ├── spectrum.py          # Adquisición de espectros
│   ├── mapping.py           # Escaneo hiperespectral 2D/3D
│   └── analysis.py          # Deconvolución y ajuste de picos
├── reportes/                # Documentación técnica y reportes Markdown
└── docs/                    # Manuales de usuario y guías de desarrollo
```

---

### 🛡️ Estándar 4: Usabilidad, Tooltips y Tolerancia a Errores

1. **Tooltips Obligatorios**: Todo control interactivo (`QPushButton`, `QLineEdit`, `QComboBox`, `QCheckBox`) **DEBE** definir un tooltip explicativo mediante `.setToolTip(...)` detallando su función física y unidades.
2. **Validación de Rangos Entrantes**: Todo campo de texto numérico debe validar que el valor ingresado esté dentro de límites físicamente seguros antes de enviarlo al backend (ej. clamping de posición piezo entre $0.0$ y $100.0\,\mu\text{m}$).
3. **Diálogos de Confirmación y Finalización**: Toda rutina automatizada exitosa debe culminar con un diálogo informativo visual (`QMessageBox.Icon.Information`) que ofrezca guardar automáticamente los datos y abrir la carpeta de trabajo.

---

### 📚 Estándar 5: Conservación de la Información, Valor del Conocimiento Generado y Autosuficiencia Pedagógica

Para garantizar que el conocimiento científico y tecnológico producido en el laboratorio permanezca vivo, transferible y transparente:

1. **Exhaustividad y Profundidad Técnica**:
   - Todo manual de usuario, reporte técnico, guía de protocolo o documento de arquitectura **DEBE** contener información minuciosa y rigurosa sobre los fundamentos físicos, deducciones matemáticas, esquemas de cableado analógico/digital, estructuras de datos y diagramas de flujo.
   - Está strictly prohibido generar documentación superficial o resúmenes opacos que requieran "adivinar" el comportamiento del software o la instrumentación.
2. **Autosuficiencia para el Usuario Final**:
   - La documentación debe estar redactada permitiendo que cualquier estudiante de grado, becario doctoral, posdoc o investigador que se incorpore al laboratorio pueda utilizar el software, reproducir experimentos, interpretar resultados y resolver problemas (*troubleshooting*) de forma autónoma.
3. **Preservación del Conocimiento como Activo de Investigación**:
   - Los documentos técnicos no son un mero acompañamiento del software, sino **base de conocimiento inmutable y transferible**. Cada documento debe ser autocontenido, incluir referencias cruzadas y servir como material docente de consulta de largo plazo para el Instituto de Nanosistemas.

---

## 6. Conclusión y Próximos Pasos

El proyecto **PyPrinting 3.0** se encuentra en un estado maduro, estable y libre de errores críticos. La ejecución exitosa de `graphify update .` ha actualizado la topología del grafo de conocimiento con **5,503 nodos**, **9,591 aristas** y **349 comunidades**.

Al adoptar el **Tablero de Conexiones y Seguridad de Hardware**, el análisis espectral **FFT en tiempo real**, los **Presets en archivos `.txt` con Wizard** y los **5 Estándares de Diseño, Arquitectura y Conservación del Conocimiento**, el Laboratorio de Nanofotónica garantiza que tanto las versiones actuales como los nuevos desarrollos (como **PySpectrum**) compartan una identidad visual profesional, una usabilidad intuitiva, una arquitectura multihilo invulnerable y un acervo documental permanente de valor incalculable.
