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
  - `[[SYS-002_Evaluacion_Arquitectonica_AST_y_Metricas_Graphify]]`
  - `[[SYS-305_Arquitectura_Optomecanica_Microscopio_Derecho_y_Ruteo_Espectral]]`
- **Fundamentos Científicos Asociados:**
  - `[[CAT-108_Teoria_Optica_Telescopio_Rele_4f_y_Canales_Confocales]]`
  - `[[CAT-201_Deconvolucion_Optica_Richardson_Lucy_y_Tracking_Trackpy]]`
  - `[[CAT-203_Presupuesto_Incertidumbre_Metrologica_ISOGUM_Microscopia]]`
- **Módulos de Código Fuente:** `core/canon_edsdk.py`, `modules/camera.py`

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

## 6. Documentación Relacionada y Red de Reportes

- **Manual Principal de Usuario**: [Manual de Usuario PyPrinting 3.0 (docs/MANUAL_USUARIO.md)](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/docs/MANUAL_USUARIO.md)
- **Visión General y Árbol**: [README PyPrinting 3.0 (README.md)](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/README.md)
- **Reportes Técnicos Vinculados**:
  - 🧵 [[SYS-101_Arquitectura_Hilos_Concurrencia_QThread|Arquitectura de Hilos y Concurrencia]]
  - 🔌 [[SYS-102_Senales_Slots_PyQt6_y_Temporizacion_DAQmx|Diagnóstico de Señales y Conexiones]]
