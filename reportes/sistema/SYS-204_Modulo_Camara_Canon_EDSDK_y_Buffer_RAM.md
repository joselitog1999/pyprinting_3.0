# SYS-204: Controlador Canon EDSDK, Simulación EVF y Búferes RAM 📷

**PyPrinting 3.0 / PySpectrum 3.0 — Suite de Nanofotónica y Control Instrumental**  
**Laboratorio de Nanofotónica — Instituto de Nanosistemas (INS-UNSAM / CONICET)**  
**Autor Principal:** José Luis González Peñafiel (*Becario Doctoral CONICET*)  
**Código del Documento:** `SYS-204` | **Eje Temático:** `[INS] (Instrumentación de Visión y Drivers SDK)`  
**Fecha de Emisión:** Septiembre 2026 | **Estado:** Aprobado / Producción

---

## 🔗 Matriz de Referencias Cruzadas

- **Reportes de Sistema Conexos:**
  - `[[SYS-101_Arquitectura_Hilos_Concurrencia_QThread]]`
  - `[[SYS-103_Regimenes_Coordenadas_e_Invariancia_Cinematica]]` — cinemática `StageCameraTransform` (§7 de este reporte, detalle completo en SYS-103 §8)
  - `[[SYS-002_Evaluacion_Arquitectonica_AST_y_Metricas_Graphify]]`
  - `[[SYS-305_Arquitectura_Optomecanica_Microscopio_Derecho_y_Ruteo_Espectral]]`
- **Fundamentos Científicos Asociados:**
  - `[[CAT-108_Teoria_Optica_Telescopio_Rele_4f_y_Canales_Confocales]]`
  - `[[CAT-201_Deconvolucion_Optica_Richardson_Lucy_y_Tracking_Trackpy]]`
  - `[[CAT-203_Presupuesto_Incertidumbre_Metrologica_ISOGUM_Microscopia]]`
- **Decisiones de Arquitectura:** `DEC-014` (`docs/decisions/DECISION_LOG.md`) — auditoría de estabilidad, cinemática y sincronización espacial bidireccional.
- **Módulos de Código Fuente:** `core/canon_edsdk.py`, `modules/camera.py`, `core/stage_camera_transform.py`, `core/stage_camera_calibration.py`

---

## 1. Resumen Ejecutivo

El presente reporte técnico documenta en detalle la arquitectura del módulo de visión de alta resolución de **PyPrinting 3.0**, basado en la integración nativa C++ ctypes del SDK **Canon EOS Digital Software Development Kit (EDSDK v13.20 64-bit)** para la cámara **Canon EOS 500D** (sensor APS-C CMOS de $15.1\ \text{MP}$, $4752 \times 3168\ \text{px}$).

Se describen las innovaciones metrológicas desarrolladas para resolver la degradación por ruido de patrón coloreado a baja señal, el control de zoom óptico/hardware nativo (`1x`, `5x`, `10x`), el procesamiento matricial en vivo con filtro mediano antiruido y umbral de piso de ruido (*noise floor*), y la miniatura interactiva **Picture-in-Picture (PiP)** con recuadro cian dinámico para la navegación espacial por el sustrato de impresión.

---

## 2. Arquitectura del Controlador Nativo EDSDK (`core/canon_edsdk.py`)

La comunicación con la cámara Canon EOS 500D se realiza directamente a través de llamadas de bajo nivel en C (`ctypes`) sobre `EDSDK.dll`, evitando wrappers de terceros o librerías desacopladas.

### 2.1 Simulación de Exposición en Live View (`Evf_Mode = 1`)
- **Problema de Ruido en Baja Luz**: Al operar en entornos de dispersión de baja iluminación, el flujo por defecto de la cámara activaba el control automático de brillo EVF (*Gain Boost*), amplificando el ruido de lectura de los canales de color del sensor y generando ruido de patrón pixelado coloreado.
- **Solución Implementada**: Al habilitar la vista previa en vivo (`enable_live_view()`), el controlador asigna la propiedad nativa:

```python
# Activar Simulación de Exposición (Exposure Simulation) en Live View
err = edsdk.EdsSetPropertyData(
    self._camera_ref,
    kEdsPropID_Evf_Mode, # 0x00000501
    0,
    ctypes.sizeof(ctypes.c_uint32),
    ctypes.byref(ctypes.c_uint32(1))
)
```

- **Efecto Físico**: Al fijar `kEdsPropID_Evf_Mode = 1`, la cámara desactiva la ganancia de brillo EVF y fuerza al sensor a renderizar el stream en vivo **sintonizado exactamente con los parámetros manuales del usuario** (ISO 3200, velocidad de obturación $T_v$ y apertura $A_v$). Esto elimina por completo el ruido artificial de ganancia.

### 2.2 Control de Zoom Hardware EDSDK y Coordenadas de Sensor
El SDK de Canon soporta niveles de magnificación en Live View a nivel de hardware/crop de sensor:
- `kEdsPropID_Evf_Zoom` = `1` ($1\times$ - Campo Completo $4752 \times 3168\ \text{px}$).
- `kEdsPropID_Evf_Zoom` = `5` ($5\times$ - Recorte de Hardware).
- `kEdsPropID_Evf_Zoom` = `10` ($10\times$ - Recorte Máximo de Enfoque).

Para desplazar el centro del zoom dentro del sensor, se envía la estructura `EdsPoint` mediante `kEdsPropID_Evf_ZoomPosition`:

```python
point = EdsPoint(x=int(center_x_px), y=int(center_y_px))
edsdk.EdsSetPropertyData(
    self._camera_ref,
    kEdsPropID_Evf_ZoomPosition,
    0,
    ctypes.sizeof(EdsPoint),
    ctypes.byref(point)
)
```

---

### 2.3 Estabilidad y Concurrencia (Auditoría Adversarial, `DEC-014` Fase A)

El módulo había recibido múltiples parches sin lograr estabilidad total en sesiones prolongadas de laboratorio. Ante instrucción explícita del usuario ("no te confíes de las implementaciones previas"), se ejecutó una auditoría adversarial dedicada de `core/canon_edsdk.py` + `modules/camera.py` que encontró y corrigió:

| Hallazgo | Causa Raíz | Corrección |
| :--- | :--- | :--- |
| **Auto-deadlock determinístico** (`ANOM-CAM-01`) | `_edsdk_lock` era `threading.Lock` (no reentrante). `set_live_view_zoom()` lo adquiría y, sin liberarlo, llamaba internamente a `_apply_zoom_position_from_center()` → `set_live_view_zoom_position()`, que intentaba readquirir el **mismo** lock en el **mismo** hilo. | `threading.RLock()` + reestructuración para que el llamado anidado ocurra fuera del `with` externo. Reproducido y verificado con un hilo separado + `join(timeout=3.0)` en `tests/test_canon_camera_stability.py`. |
| **Cierre cruzado de hilo sin marshalling** (`ANOM-CAM-02`/`02b`) | `CameraWindow.closeEvent()` y `app.py::Backend.close_all()` llamaban a métodos del worker de cámara directamente desde el hilo GUI, pese a que el worker vive en su propio `QThread`. | `QMetaObject.invokeMethod(worker, "stop_camera", Qt.ConnectionType.BlockingQueuedConnection)` en ambos sitios. |
| **Definición duplicada de `OverlayWidget.set_zoom_level()`** (`ANOM-CAM-06`) | Python silenciosamente sólo ejecutaba la segunda definición (con lógica de congelado de PiP); la primera, muerta, carecía de esa lógica — explica por qué parches de zoom anteriores no surtían efecto completo. | Eliminada la definición muerta. |
| **Constantes UILock/UIUnLock indefinidas** (`ANOM-CAM-04`) | El fallback NonAF de `take_photo()` las usaba sin declarar, produciendo un `NameError` silenciado por `except Exception: pass`. | Definidas con los valores oficiales verificados contra `ESDK_CANON/.../EDSDKTypes.h:468-469`. |
| **Fuga de handles EDSDK en camino de error** (`ANOM-CAM-05`) | `_download_newest_photo_from_camera()` liberaba `vol_ref`/`folder_ref`/`last_item` inline en el camino feliz — una excepción a mitad del recorrido saltaba los releases pendientes. | `try/finally` anidado por cada handle adquirido. |

Adicionalmente, e independientemente del alcance de esta auditoría, se encontró que `core/nanopositioning.py::Backend.move()`/`_moveto()` sondeaban `pi.qONT()` sin timeout (mismo patrón ya corregido en `focus.py` por `DEC-013`) — corregido con un parámetro `timeout_s`.

### 2.4 Tamaño Inicial Fijo del Stream de Memoria Live View (`DEC-014` Fase E)

`get_live_view_frame()` creaba el `EdsStreamRef` receptor de cada cuadro JPEG con `EdsCreateMemoryStream(0, ...)` — reasignación desde tamaño cero en cada uno de los hasta 25 cuadros por segundo, candidata plausible a la inestabilidad reportada. Corregido a un tamaño inicial fijo de **2 MiB**:

```python
# core/canon_edsdk.py::get_live_view_frame()
err = edsdk.EdsCreateMemoryStream(2 * 1024 * 1024, ctypes.byref(stream))
```

El valor no fue elegido arbitrariamente: es la constante exacta que usa el propio ejemplo oficial de Canon para este mismo llamado (`ESDK_CANON/.../Sample/CSharp/CameraControl/CameraControl/Command/EVF/DownloadEvfCommand.cs:41`). `EDSDK.h` documenta que el stream sigue extendiéndose automáticamente si el frame real excede el tamaño inicial ("In the case of writing in excess of the allocated buffer size, the memory is automatically extended"), de modo que el fix no introduce un límite duro — sólo elimina la reasignación repetida desde cero. Se descartó deliberadamente reutilizar un único handle de stream entre frames, por tratarse de un comportamiento del SDK no verificado documentalmente.

---

## 3. Procesamiento de Imagen en Vivo y Supresión de Ruido

Los fotogramas adquiridos en `cameraThread` ingresan a la función `process_frame_live_adjustments`:

```
┌───────────────────────────┐     ┌───────────────────────────┐     ┌───────────────────────────┐
│ Frame Raw RGB (Sensor)    │ ──> │ Filtro Mediano 3x3        │ ──> │ Umbral Noise Floor (0-50) │
│ (1280x840 px Live View)   │     │ (cv2.medianBlur, ksize=3) │     │ (Pixels < NoiseFloor -> 0)│
└───────────────────────────┘     └───────────────────────────┘     └─────────────┬─────────────┘
                                                                                  │
┌───────────────────────────┐     ┌───────────────────────────┐                   │
│ Renderizado Final GUI     │ <── │ Transformación LUT / RGB  │ <─────────────────┘
│ (Visor PyQtGraph + PiP)   │     │ (Gris / Thermal / RGB)    │
└───────────────────────────┘     └───────────────────────────┘
```

1. **Filtro Mediano Morfológico 3x3 (`denoise`)**: Remueve los picos aislados de ruido de tipo sal y pimienta producidos por rayos cósmicos o píxeles defectuosos del sensor.
2. **Piso de Ruido (*Noise Floor Threshold* $0-50$)**: Filtra todas las variaciones de lectura de fondo forzando a cero absoluto $(0,0,0)$ los píxeles cuya intensidad máxima no alcance el umbral seleccionado en el panel.

---

## 4. Miniatura PiP (Picture-in-Picture) e Interacción Espacial

En `modules/camera.py`, el componente `OverlayWidget` incluye un canvas de navegación multinivel:

1. **Captura de Vista Completa Unzoomed (`fullFrameSignal`)**: El worker transmite en paralelo el fotograma completo a $1\times$ para alimentar la miniatura PiP sin importar qué nivel de zoom tenga el visor principal.
2. **Recuadro Dinámico Cian (Bounding Box)**: En la esquina inferior del visor, se calcula el bounding box en tiempo real:

$$\text{width}_{\text{box}} = \frac{1}{\text{ZoomLevel}} \cdot W_{\text{pip}}, \quad \text{height}_{\text{box}} = \frac{1}{\text{ZoomLevel}} \cdot H_{\text{pip}}$$

3. **Navegación Interactiva por Mouse**: Al hacer clic o arrastrar dentro del recuadro de la miniatura, se re-calculan las coordenadas relativas $(c_x, c_y)$ y se emite la señal `setZoomCenterSignal` para centrar suavemente el visor principal en el punto deseado.

---

## 5. Delimitación Estricta de Paneles y Centrado Flush

- **Parenting en Viewport**: `OverlayWidget` se vincula a `self._view.viewport()`, asegurando que los eventos de repintado de Qt coincidan punto a punto con la superficie interna de `GraphicsLayoutWidget`.
- **Restricciones de Splitter**: Los paneles laterales (`left_panel` y `right_panel`) cuentan con anchos mínimos y máximos fijos, y la propiedad `setCollapsible(1, False)` garantiza que la sección central del visor nunca sea colapsada ni invadida por el panel de mediciones al cambiar el tamaño de la ventana.

---

## 6. Cinemática Platina ↔ Cámara (`StageCameraTransform`)

Desde `DEC-014`, la cámara comparte una cinemática calibrada con el Confocal y las rutinas de Impresión/Dímeros a través de `core/stage_camera_transform.py::StageCameraTransform` — el detalle matemático completo (formulación matricial, verificación de reflexión vs. rotación, chequeo de patrón de signo conocido) vive en `[[SYS-103_Regimenes_Coordenadas_e_Invariancia_Cinematica]]` §8, por ser la extensión natural del Principio de Invariancia ya documentado allí. Resumen relevante a este módulo:

- **Calibrada en píxeles de sensor completo** ($4752\times3168$), no por nivel de zoom óptico — `core/stage_camera_calibration.py::sensor_px_to_display_fraction()` compone aparte, sólo al proyectar a pantalla, la ventana de recorte de zoom vigente (misma geometría que `_apply_zoom_position_from_center()`, §2.2).
- **Dos herramientas de calibración expuestas en la GUI** (`StageCalibrationWizardDialog`, `FiducialValidationDialog`) — ver `[[MOD-04_Camara_Live_View_Canon_EDSDK]]` §10.2 para el flujo de usuario.
- **Overlays proyectados** (caja de escaneo confocal, grilla de impresión) recalculados sólo ante la señal upstream relevante — nunca dentro del bucle de refresco de video a 25 fps (§2 de este reporte).

---

## 7. Documentación Relacionada y Red de Reportes

- **Manual Principal de Usuario**: [Manual de Usuario PyPrinting 3.0 (docs/MANUAL_USUARIO.md)](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/docs/MANUAL_USUARIO.md)
- **Visión General y Árbol**: [README PyPrinting 3.0 (README.md)](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/README.md)
- **Decisión de Arquitectura**: `DEC-014` (`docs/decisions/DECISION_LOG.md`) — auditoría de estabilidad, cinemática y sincronización espacial bidireccional.
- **Reportes Técnicos Vinculados**:
  - 🧵 [[SYS-101_Arquitectura_Hilos_Concurrencia_QThread|Arquitectura de Hilos y Concurrencia]]
  - 🧭 [[SYS-103_Regimenes_Coordenadas_e_Invariancia_Cinematica|Regímenes de Coordenadas e Invariancia Cinemática]]
  - 🔌 [[SYS-102_Senales_Slots_PyQt6_y_Temporizacion_DAQmx|Diagnóstico de Señales y Conexiones]]
