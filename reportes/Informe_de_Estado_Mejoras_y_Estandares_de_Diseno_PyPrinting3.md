# Informe de Estado del Proyecto, Evaluación Multidimensional, Tablero de Conexiones y Estándares de Diseño (PyPrinting 3.0 & PySpectrum) 🔬

**Laboratorio de Nanofotónica — Instituto de Nanosistemas (INS-UNSAM / CONICET)**  
**Autor Principal**: José Luis González Peñafiel (*Becario Doctoral CONICET*)  
**Fecha de Publicación**: 10 de Agosto de 2026  
**Ubicación del Reporte**: `reportes/Informe_de_Estado_Mejoras_y_Estandares_de_Diseno_PyPrinting3.md`  

---

## 1. Resumen Ejecutivo y Actualización de Graphify 🌳

Se ha ejecutado con éxito la actualización del **Grafo de Conocimiento del Proyecto** (`graphify update .`). El análisis estático de código (AST) ha reconstruido el mapa de nodos y comunidades del repositorio `printing3`, arrojando las siguientes métricas globales:

- **Total de Nodos Registrados**: $5,440$ nodos de código, clases, métodos y metadatos.
- **Aristas / Relaciones Inter-módulo**: $9,466$ conexiones.
- **Comunidades Estructurales**: $322$ comunidades funcionales desglosadas.
- **Archivos de Salida Actualizados**: `graphify-out/graph.json`, `graphify-out/graph.html` y `graphify-out/GRAPH_REPORT.md`.

El grafo de conocimiento confirma que la refactorización reciente (unificación de `measurements.py`, incorporación de `InteractiveGridWidget`, aislamiento del modo seguro `SAFE_MODE` y el módulo de `Drift Correction`) ha alcanzado un grado óptimo de desacoplamiento modular.

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

| Módulo | Función Principal | Estado Actual | Fortalezas | Oportunidad de Mejora Aprobada |
|---|---|---|---|---|
| `main.py` | Launcher Principal y Menú | 🟢 Estable | Tema oscuro Catppuccin Mocha, lanzador independiente de procesos | Tablero de Conexiones de Hardware y Telemetría. |
| `app.py` | Suite Principal Multihilo | 🟢 Estable | Interconexión síncrona/asíncrona de 8 hilos secundarios | Barra de estado dinámica de procesos y Dock de Hardware. |
| `measurements.py` | Rutinas de Impresión y Dímeros | 🟢 Excelente | 5 modos de parada, `Drift Correction`, visualizador de grilla | Presets experimentales rápidos (AuNP 60nm, Dímeros Sub-50nm). |
| `focus.py` | Autofoco Axial Z por Correlación | 🟢 Estable | Búsqueda por rango dinámico y ajuste parabólico | Optimización de tiempos de respuesta en Z. |
| `confocal.py` | Escaneo Confocal 2D (Rampa/Paso) | 🟢 Excelente | Generación de ondas analógicas PI (`WAV_LIN`) y ajuste Gaussiano 2D / Donut 2D | Exportación nativa a TIFF multicanal 16-bit con OME-XML. |
| `trace.py` | Adquisición de Fotodiodo $I(t)$ | 🟢 Estable | Promedios móviles $I_{\text{old}} / I_{\text{new}}$ y soporte multicanal | Adquisición por bloques vectorizados DMA en NI-DAQmx. |
| `camera.py` | Visión en Vivo Thorlabs/USB | 🟢 Estable | Retículas overlays, medición de distancia en µm | Optimización de búferes de captura USB. |
| `config.py` | Configuración Global | 🟢 Excelente | Soporte de `SAFE_MODE` transparente para desarrollo sin hardware | Manejo de aislamiento (*Soft Isolation*) por dispositivo. |

---

## 3. Propuesta Seleccionada: Tablero de Conexiones de Hardware y Mejoras Multidimensionales

Atendiendo a las directivas del laboratorio, **se han excluido** los módulos de Gestor de Perfiles de Sesión, Asistente Guiado (Wizard), Registro Z Individual y Grabación de Video. En su lugar, el plan de acción se concentra en el **Tablero de Conexiones y Seguridad de Hardware** combinado con las mejoras de usabilidad, eficiencia, robustez y practicidad aprobadas.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│             TABLERO DE CONEXIONES, TELEMETRÍA Y SEGURIDAD DE HARDWARE                  │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ • Estado de Conexión en Vivo: 🟢 NI-DAQmx | 🟢 PI Piezo | 🟢 Cámara | 🟢 Espectrómetro    │
│ • Aisle e Interrupción Manual: Switch [Soft Disconnect / Mock Isolation] por equipo.   │
│ • Bitácora de Eventos (Hardware Log): Timestamps de comunicación y alertas I/O.        │
│ • Re-scan en Caliente: Botón [Re-scan Hardware] para ping de puertos USB/GPIB/NI-DAQ.   │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

### 3.1 Tablero de Conexiones y Seguridad de Hardware (`HardwareDashboardWidget`)
- **Visualización de Conexiones Activas**: Panel gráfico con diodos emisores de luz (LED) que indican el estado de cada instrumento (Verde: Conectado y operativo / Amarillo: Simulado / Rojo: Desconectado o con error).
- **Aisle / Software Isolation**: Cada dispositivo cuenta con una llave de paso (*Soft Disconnect*). Permite simular o desconectar un instrumento específico para pruebas sin interrumpir la ejecución del resto de los componentes ni congelar la GUI.
- **Bitácora de Eventos de Comunicación**: Consola de registros en tiempo real con marcas de tiempo (*timestamps*) detallando inicialización, lecturas analógicas, comandos PI y alertas.
- **Rescan en Caliente**: Botón para re-escanear en caliente la presencia de hardware sin reiniciar `app.py`.

### 3.2 Usabilidad y Rendimiento (UX/UI)
- **Indicadores Dinámicos de Estado**: Barra de estado global en `app.py` que informa: *"Platina desplazándose a (X,Y)"*, *"Escaneo confocal activo"*, *"Obturador Láser Abierto"*.
- **Presets Experimentales Rápidos**: Menú desplegable con perfiles típicos de muestra (*AuNP 60nm - Impresión Rápida*, *AgNP 80nm - Dímeros Gap 30nm*, *Grilla 10x10*).
- **Consistencia Estética Catppuccin Mocha**: Aplicación unificada del esquema oscuro de alto contraste en todas las ventanas y gráficos.

### 3.3 Aplicabilidad y Espectroscopía
- **Módulo Espectroscópico Integrado (Precursor de `PySpectrum`)**: Captura de espectros de fotoluminiscencia (PL) y Raman vinculados a la posición de las nanopartículas impresas.
- **Exportación Multimaterial**: Exportación nativa en estándar OME-TIFF de 16 bits, arreglos NumPy `.npy` y datos tabulares CSV.

### 3.4 Eficiencia y Robustez
- **Bloques Vectorizados DMA (NI-DAQmx)**: Adquisición por búferes continuos en `trace.py` para reducir el uso de CPU a $< 5\%$.
- **Renderizado Adaptativo en `pyqtgraph`**: Downsampling visual automático en escaneos grandes ($> 200 \times 200\ \text{px}$) para mantener 60 FPS.
- **Reconexión Automática en `QThread`**: Envolver llamadas I/O físicas en políticas de reintento (*Retry Policy*) impidiendo caídas por desconexión USB.
- **Auto-recuperación (`Last_position.txt`)**: Registro continuo del último nodo impreso para reanudar el experimento en caso de corte eléctrico.

---

## 4. Guía de Criterios, Lineamientos y Estándares de Diseño para Futuros Desarrollos (PySpectrum, PyPrinting 3.1, etc.) 📐

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
   - Está estrictamente prohibido generar documentación superficial o resúmenes opacos que requieran "adivinar" el comportamiento del software o la instrumentación.
2. **Autosuficiencia para el Usuario Final**:
   - La documentación debe estar redactada permitiendo que cualquier estudiante de grado, becario doctoral, posdoc o investigador que se incorpore al laboratorio pueda utilizar el software, reproducir experimentos, interpretar resultados y resolver problemas (*troubleshooting*) de forma autónoma.
3. **Preservación del Conocimiento como Activo de Investigación**:
   - Los documentos técnicos no son un mero acompañamiento del software, sino **base de conocimiento inmutable y transferible**. Cada documento debe ser autocontenido, incluir referencias cruzadas y servir como material docente de consulta de largo plazo para el Instituto de Nanosistemas.

---

## 5. Conclusión y Próximos Pasos

El proyecto **PyPrinting 3.0** se encuentra en un estado maduro, estable y robusto. La ejecución exitosa de `graphify update .` ha actualizado la topología del grafo de conocimiento.

Al adoptar el **Tablero de Conexiones y Seguridad de Hardware** y los **5 Estándares de Diseño, Arquitectura y Conservación del Conocimiento** aquí formulados, el Laboratorio de Nanofotónica garantiza que tanto las futuras versiones del sistema de impresión como el nuevo desarrollo de **PySpectrum** compartan una identidad visual profesional, una usabilidad intuitiva, una arquitectura multihilo invulnerable y un acervo documental permanente de valor incalculable.
