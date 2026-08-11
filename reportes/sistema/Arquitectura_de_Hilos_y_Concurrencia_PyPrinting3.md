# Reporte Técnico: Arquitectura de Hilos, Concurrencia Asíncrona y Prevención de Bloqueos en PyPrinting 3.0 ⚡

**Laboratorio de Nanofotónica — Instituto de Nanosistemas (INS-UNSAM)**  
**Autor Principal**: José Luis González Peñafiel (*Becario Doctoral CONICET*)  
**Fecha de Publicación**: 11 de Agosto de 2026  
**Documento de Referencia**: `reportes/sistema/Arquitectura_de_Hilos_y_Concurrencia_PyPrinting3.md`  
**Módulos de Implementación**: `app.py`, `contrapropagante.py`, `modules/camera.py`, `modules/measurements.py`, `modules/trace.py`, `modules/hardware_dashboard.py`, `core/hardware_manager.py`

---

## 1. Resumen Ejecutivo

El presente reporte técnico describe en detalle la topología de hilos, el esquema de concurrencia y la estrategia de comunicación inter-proceso de **PyPrinting 3.0**. La suite ha sido diseñada para ejecutar rutinas intensivas de caracterización y nanofabricación (como la **Impresión Óptica Fototérmica** y la **Ensamblado de Nanodímeros Plasmónicos**) mientras se realiza de forma simultánea la **Adquisición Analógica Multicanal a 10 kHz (NI-DAQmx)** y la **Visualización en Vivo de Alta Resolución (Cámara Canon EOS 500D)**.

El objetivo primario de esta arquitectura es **garantizar una respuesta de interfaz de usuario de 0 ms de latencia perceptible (No UI Freezing)** y **evitar condiciones de carrera (*Race Conditions*) o bloqueos mutuos (*Deadlocks*)**, aislando las cargas de procesamiento en hilos independientes coordinados por el Event Loop de PyQt6.

---

## 2. Mapa Global de Hilos de Ejecución

El sistema opera mediante una estructura jerárquica compuesta por **4 hilos de alto nivel en Python/PyQt6** (1 Hilo de Interfaz + 3 Hilos de Fondo `QThread`) y **2 a 3 hilos nativos C++ en segundo plano** gestionados por las bibliotecas dinámicas DLL de los fabricantes (`EDSDK.dll` y `nicaiu.dll`).

```
                               ┌──────────────────────────────────────────────────────────┐
                               │   Main UI Thread (PyQt6 Event Loop)                      │
                               │   - Renderizado GUI (QMainWindow, PyQtGraph, Qt Widgets)│
                               │   - Entrada de Usuario (Teclado, Mouse, Menús)          │
                               └────────────────────────────┬─────────────────────────────┘
                                                            │
         ┌──────────────────────────────────────────────────┼──────────────────────────────────────────────────┐
         ▼                                                  ▼                                                  ▼
┌──────────────────────────────┐          ┌──────────────────────────────────┐          ┌──────────────────────────────┐
│ cameraThread (QThread)       │          │ confocalThread (QThread)         │          │ instrumentThread (QThread)   │
│ - CanonWorker                │          │ - printingWorker (MeasBackend)   │          │ - nanoWorker (NanoBackend)   │
│ - Stream EVF (kEdsPropID_Evf)│          │ - dimersWorker (MeasBackend)     │          │ - shuttersWorker (Shutters)  │
│ - Denoise (Median 3x3)       │          │ - traceWorker (TraceBackend)     │          │ - laser532Backend            │
│ - Noise Floor Threshold      │          │ - confocalWorker (ConfocalBackend│          │ - Comunicación Serie RS-232  │
│ - Miniatura PiP (1x Crop)    │          │ - focusWorker (FocusBackend)     │          │   con Platina Piezo PI E-517 │
└──────────────┬───────────────┘          └────────────────┬─────────────────┘          └──────────────────────────────┘
               │                                           │
               ▼                                           ▼
┌──────────────────────────────┐          ┌──────────────────────────────────┐
│ EDSDK.dll (Hilo C++ Nativo)  │          │ nicaiu.dll (Hilo C++ Nativo)     │
│ - Pila USB / PTP de Canon    │          │ - Buffers DMA Hardware Anillo    │
│ - Polling Buffer Sensor      │          │ - Transferencia Directa a RAM    │
└──────────────────────────────┘          └──────────────────────────────────┘
```

---

## 3. Matriz Metrológica de Hilos

| Identificador de Hilo | Entorno de Ejecución | Trabajadores (Workers) Asignados | Tarea Principal | Prioridad / Latencia | Mecanismo de Sincronización |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Main UI Thread** | Python / Qt Event Loop | `Frontend` (`QMainWindow`), Docks, `CameraWindow` | Renderizado gráfico, actualización de trazas a 100 Hz, recepción de eventos de usuario. | Alta / $< 10\ \text{ms}$ | Qt Event Loop Queue |
| **`cameraThread`** | PyQt6 `QThread` | `cameraWorker` (`CanonWorker`) | Captura de frames EVF, filtro mediano $3\times 3$, umbral de ruido, emisión `fullFrameSignal`. | Media-Alta / $30\ \text{fps}$ | `QueuedConnection` (Señales Qt) |
| **`confocalThread`** | PyQt6 `QThread` | `printingWorker`, `dimersWorker`, `confocalWorker`, `traceWorker`, `focusWorker` | Orquestación de bucle de grilla, criterio de parada multimodo, muestreo de fotodiodos a 10 kHz y autofoco Z. | Crítica / $< 1\ \text{ms}$ | `QueuedConnection` + Mutex NI |
| **`instrumentThread`**| PyQt6 `QThread` | `nanoWorker`, `shuttersWorker`, `laser532Backend` | Comunicación serie/USB RS-232 con platina piezoeléctrica PI E-517 (`pi.MOV()`, `pi.qPOS()`) y relés. | Media / $\approx 50\ \mu\text{s}$ servo | `QMutex` interno de driver PI |
| **Hilo Nativo EDSDK** | C++ DLL (`EDSDK.dll`) | `CanonCamera` C-API | Gestión del protocolo USB/PTP de la Canon EOS 500D y vaciado del buffer de sensor. | Hardware | Eventos C++ Win32 (`EdsObjectEventHandler`) |
| **Hilo Nativo NI-DAQ**| C++ DLL (`nicaiu.dll`)| Task NI-DAQmx | Transferencia de datos DMA desde la tarjeta NI USB-6343 a la memoria RAM de la PC. | Hardware Real-Time | Anillo DMA circular por hardware |

---

## 4. Análisis de Concurrencia Durante Impresión Simultánea con Cámara Live View

Cuando el usuario inicia una rutina de **Impresión Óptica** mientras monitorea el campo con la **Cámara Canon EOS 500D en vivo**, el sistema ejecuta **6 a 7 hilos concurrentes**. La estabilidad del sistema se fundamenta en tres pilares de ingeniería de software:

### 4.1 Desacoplamiento CPU entre Procesamiento de Imagen e Impresión
- La cámara procesa frames de $15.1\ \text{MP}$ en `cameraThread`. Aunque el usuario active el **Filtro Mediano 3x3** o la **Supresión de Ruido de Fondo**, todo el cómputo matricial NumPy/OpenCV ocurre en `cameraThread`.
- La rutina de impresión en `confocalThread` evalúa los criterios de parada (saltos de fotodiodo en `ai0/ai1/ai6`) **sin competir por tiempos de ciclo** con el bucle de la cámara.

### 4.2 Comunicación Inter-Hilo Asíncrona mediante Señales `QueuedConnection`
La transferencia de fotogramas y datos de fotodiodos entre los hilos y la interfaz gráfica no utiliza variables globales compartidas con bloqueos (`locks`), sino el sistema de señales de Qt:

```python
# Conexión asíncrona de señales (QueuedConnection por defecto entre hilos distintos)
self.frameSignal.connect(window._update_frame)
self.fullFrameSignal.connect(window._update_full_frame)
self.liveParamsSignal.connect(self.set_live_adjustments)
```

Al emitir `frameSignal.emit(frame)`, Qt deposita una referencia al arreglo NumPy en la cola de mensajes del hilo receptor. El hilo emisor continúa inmediatamente sin esperar a que la GUI termine de repintar la pantalla.

### 4.3 Buffers por Hardware DMA de NI-DAQmx y Canon EDSDK
- **NI-DAQmx**: La tarjeta NI USB-6343 utiliza canales DMA que escriben las muestras analógicas de $10\text{ kHz}$ en la memoria RAM en segundo plano sin intervención del procesador.
- **Canon EDSDK**: La cámara transfiere bloques de compresión JPEG Live View vía USB bulk transfer directamente a buffers de la DLL de Canon, minimizando la carga en el bus de sistema.

---

## 5. Prevención de Bloqueos (*Deadlocks*) y Consumo de CPU

1. **Ausencia de Llamadas Bloqueantes en el Hilo Principal**:
   - Ningún método invocado desde la GUI realiza esperas pasivas (`time.sleep()`) ni lecturas sincrónicas en bucles infinitos.
2. **Cierre de Emergencia de Hardware Físico (`atexit`)**:
   - `core/canon_edsdk.py` registra la función `_emergency_shutter_cleanup()` en `atexit` para forzar el retorno mecánico del obturador y el cierre de la sesión USB en caso de finalización imprevista de la aplicación.
3. **Consumo de Recursos Computacionales**:
   - En procesadores multi-núcleo modernos (4 a 8 núcleos), la carga total distribuida de CPU se mantiene entre el **5% y el 12%**, garantizando una estabilidad operacional continua durante extensas jornadas de fabricación.

---

## 6. Documentación Relacionada y Red de Reportes

- **Manual Principal de Usuario**: [Manual de Usuario PyPrinting 3.0 (docs/MANUAL_USUARIO.md)](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/docs/MANUAL_USUARIO.md)
- **Visión General y Árbol**: [README PyPrinting 3.0 (README.md)](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/README.md)
- **Reportes Técnicos Vinculados**:
  - 📷 [Módulo Cámara Canon EOS 500D (reportes/Modulo_Camara_Canon_EOS500D_PyPrinting3.md)](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/reportes/Modulo_Camara_Canon_EOS500D_PyPrinting3.md)
  - 🔌 [Diagnóstico de Señales y Conexiones (reportes/Diagnostico_de_Senales_y_Conexiones_PyPrinting3.md)](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/reportes/Diagnostico_de_Senales_y_Conexiones_PyPrinting3.md)
  - 🧮 [Algoritmo de Parada e Impresión de Grillas (reportes/Algoritmo_Printing_y_Dimers_PyPrinting3.md)](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/reportes/Algoritmo_Printing_y_Dimers_PyPrinting3.md)
