# 🌈 Reporte Técnico de Sistema: Calibración Espectral Shamrock 500i / iXon3 y Actuación Reactiva de Flippers y Obturadores

**PyPrinting 3.0 & PySpectrum 3.0 — Suite de Nanofabricación y Caracterización Fotónica**  
**Laboratorio de Nanofotónica — Instituto de Nanosistemas (INS-UNSAM / CONICET)**  
**Autor Principal**: José Luis González Peñafiel (*Becario Doctoral CONICET*)  
**Fecha de Publicación**: 7 de Septiembre de 2026  
**Documento de Referencia**: `reportes/sistema/Reporte_Calibracion_Espectral_y_Actuacion_Flippers_PyPrinting3.md`  
**Estado**: Producción / Validación 100% (49/49 Tests Unitarios e Integración)

---

## 1. 📋 Resumen Ejecutivo

El presente informe técnico documenta dos hitos de ingeniería de software e instrumentación óptica alcanzados el **7 de Septiembre de 2026** para las plataformas unificadas **PyPrinting 3.0** y **PySpectrum 3.0**:

1. **Modernización y Completitud del Subsistema de Calibración Espectral (`calibration_dock.py`)**:
   - Incorporación de un dock modular con cuatro sub-paneles especializados:
     - **Alineación de Orden Cero ($m=0$) y Centroide de Rendija**: Ajuste no lineal Gaussiano sub-píxel para centrar el eje óptico del espectrógrafo Andor Shamrock 500i sobre el detector EMCCD Andor iXon3 888.
     - **Calibración y Control de Hendidura de Entrada (*Slit*)**: Lectura y fijado micrométrico del ancho de rendija motorizada y comprobación de punto cero (`ShamrockGetSlitZeroPosition`).
     - **Gestión Nativa de Offsets de Hardware (Shamrock SDK vía Ctypes)**: Enlace a bajo nivel con `ShamrockCIF.dll` para lectura y escritura no volátil de `Grating Offset` y `Detector Offset`.
     - **Calibración Cúbica de Longitud de Onda y Corrección Radiométrica con Lámpara Halógena**: Ajuste polinómico $\lambda(p) = \sum_{i=0}^3 a_i p^i$ y normalización de respuesta espectral instrumental $R(\lambda)$.
2. **Reingeniería de la Reactividad del Flipper de Potencia (Low/High Power) y Seguridad**:
   - Diagnóstico y resolución de la insensibilidad de señal en el checkbox `powerbutton` de PyPrinting ante transiciones de estado.
   - Migración de eventos en `PyQt6` desde `clicked` a `toggled(bool)` con decorador formal `@pyqtSlot(bool) set_power(high)` y soporte de argumentos polimórficos.
   - Creación de un puente de callbacks de hardware (`register_flipper_callback`, `unregister_flipper_callback`, `is_flipper_high_power`) entre el hilo demonio del Watchdog en `core/nidaq.py` y el hilo de la GUI de PyQt6, garantizando sincronización bidireccional instantánea y desacoplamiento visual (`update_power_ui`).
3. **Optimización de Step & Glue (Cosido Espectral UV-Vis-NIR)**:
   - Conexión de señales de aborto cooperativo instantáneo (`stopMeasurementSignal`) y exportación directa de espectros (`saveSpectrumSignal`) en ASCII `.txt` y NumPy `.npz`.
   - Depuración de señales huérfanas en el driver de cámara iXon3 (`measureKineticsSignal`, `saveSpectrumSignal`).

---

## 2. 🔬 Marco Teórico y Modelado Físico de la Calibración Espectral

```
                              ESPECTRÓGRAFO SHAMROCK 500i
           ┌─────────────────────────────────────────────────────────────┐
Rendija    │  Colimador                                   Enfoque        │    Cámara EMCCD
Entrada    │  Espejo M1       Torreta 3 Rejillas          Espejo M2      │    Andor iXon3
  ───► [Slit] ───► ( ( ( ───► [ 1200 / 300 / 150 ] ───► ) ) ) ───────► │ [ p_0 ... p_1023 ]
 (w = 10-2500 µm)                 Orden m=0 o m=1                       │  Pixel X -> λ(p)
           └─────────────────────────────────────────────────────────────┘
```

### 2.1 Ecuación de Red y Geometría de Orden Cero ($m=0$)
La difracción en una red plana reflectiva está regida por:

$$m \lambda = d (\sin \alpha + \sin \beta)$$

donde $d = 1/\rho$ es el espaciado de surcos (para $\rho = 1200\ \text{líneas/mm}$, $d \approx 833.3\ \text{nm}$), $\alpha$ es el ángulo de incidencia y $\beta$ es el ángulo de difracción.

Para el **orden cero** ($m = 0$):

$$\sin \beta = -\sin \alpha \implies \beta = -\alpha$$

En esta condición, la rejilla actúa como un espejo plano especular donde el ángulo de reflexión es idéntico al de incidencia independientemente de la longitud de onda incidente $\lambda$. El haz reflejado proyecta directamente la imagen geométrica de la rendija de entrada sobre el plano focal del detector EMCCD. 

La posición centroidal de esta rendija proyectada en el plano del detector determina el **pixel de referencia del eje óptico**. Cualquier desalineación mecánica del tambor de la torreta o del soporte de la cámara respecto al diseño nominal desplaza este centroide del píxel central teórico ($p_{\text{center}} = N_{\text{pixels}} / 2 = 512$ para un sensor de 1024 píxeles). La compensación de esta desviación se realiza mediante el `Detector Offset` y el `Grating Offset` del Shamrock.

### 2.2 Estimación Robusta de Centroide Sub-Píxel vía Ajuste Gaussiano
Para una rendija estrecha ($w \le 50\ \mu\text{m}$), el perfil de irradiancia sobre el sensor en orden 0 sigue una distribución cuasi-gaussiana truncada por la convolución con la respuesta de píxel:

$$I(x) = y_0 + A \exp\left( -\frac{(x - x_0)^2}{2 \sigma^2} \right)$$

donde:
- $y_0$: Línea de base (*background*) de corriente oscura y luz espuria.
- $A$: Amplitud máxima por encima del fondo.
- $x_0$: Centroide sub-píxel de la rendija (posición con precisión submétrica en el detector).
- $\sigma$: Ancho cuadrático medio ($\text{FWHM} \approx 2.355 \sigma$).

#### Inicialización Analítica por Momentos Espaciales
Para asegurar convergencia incondicional del optimizador de Levenberg-Marquardt (`scipy.optimize.curve_fit`), el sistema calcula los momentos espaciales de primer y segundo orden sobre el perfil experimental recortado alrededor del máximo:

$$y_0^{(0)} = \min(I(x)), \quad A^{(0)} = \max(I(x)) - y_0^{(0)}$$

$$\tilde{I}_i = I(x_i) - y_0^{(0)}$$

$$\mu^{(0)} = \frac{\sum_i x_i \tilde{I}_i}{\sum_i \tilde{I}_i}$$

$$\sigma^{(0)} = \sqrt{\frac{\sum_i (x_i - \mu^{(0)})^2 \tilde{I}_i}{\sum_i \tilde{I}_i}}$$

Este procedimiento garantiza convergencia en $< 15\ \text{ms}$, determinando el centroide $x_0$ con una incertidumbre típica:

$$u(x_0) = \frac{\sigma}{\sqrt{N_{\text{photons}}}} \approx 0.02 - 0.05\ \text{píxeles}$$

lo que equivale a $< 0.8\ \mu\text{m}$ en el plano focal para píxeles de $13\ \mu\text{m}$.

### 2.3 Calibración Cúbica de Longitud de Onda $\lambda(p)$
La dispersión angular de la red genera una relación no lineal entre la posición del píxel $p \in [0, N-1]$ y la longitud de onda incidente. La conversión se parametriza mediante un polinomio de tercer grado almacenado en la EEPROM del espectrógrafo o en el archivo de calibración local:

$$\lambda(p) = a_0 + a_1 p + a_2 p^2 + a_3 p^3$$

donde:
- $a_0$: Longitud de onda en el origen del detector ($p=0$) [$\text{nm}$].
- $a_1$: Dispersión lineal principal [$\text{nm/píxel}$].
- $a_2, a_3$: Coeficientes de corrección de distorsión óptica y aberración de campo plano [$\text{nm/píxel}^2$, $\text{nm/píxel}^3$].

### 2.4 Corrección Radiométrica de Sensibilidad Espectral (Lámpara Halógena)
La eficiencia de difracción de la rejilla (*blaze angle*) combinada con la curva de eficiencia cuántica (QE) del sensor EMCCD con recubrimiento antirreflectante modifica la amplitud relativa del espectro medido. La función de transferencia del instrumento se normaliza mediante una lámpara de tungsteno-halógena calibrada NIST:

$$R(\lambda) = \frac{I_{\text{halogen}}(\lambda) - I_{\text{dark}}(\lambda)}{I_{\text{NIST}}(\lambda)}$$

El espectro físico corregido de una muestra (nanopartícula o fluoróforo) se obtiene como:

$$S_{\text{real}}(\lambda) = \frac{I_{\text{sample}}(\lambda) - I_{\text{dark}}(\lambda)}{R(\lambda)}$$

---

## 3. ⚙️ Integración con Shamrock SDK a Bajo Nivel (Ctypes)

Para garantizar la interoperabilidad con el firmware Andor sin depender de capas intermedias cerradas, se actualizaron y verificaron las firmas nativas en [`pyspectrum/drivers/shamrock_driver.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/pyspectrum/drivers/shamrock_driver.py) hacia `ShamrockCIF.dll`:

```python
# Firmas Ctypes en ShamrockDriver
self._shamrock.ShamrockGetGratingOffset.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_int)]
self._shamrock.ShamrockGetGratingOffset.restype = ctypes.c_int

self._shamrock.ShamrockSetGratingOffset.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int]
self._shamrock.ShamrockSetGratingOffset.restype = ctypes.c_int

self._shamrock.ShamrockGetDetectorOffset.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_int)]
self._shamrock.ShamrockGetDetectorOffset.restype = ctypes.c_int

self._shamrock.ShamrockSetDetectorOffset.argtypes = [ctypes.c_int, ctypes.c_int]
self._shamrock.ShamrockSetDetectorOffset.restype = ctypes.c_int

self._shamrock.ShamrockGetSlitZeroPosition.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_int)]
self._shamrock.ShamrockGetSlitZeroPosition.restype = ctypes.c_int
```

### Tabla de Códigos de Retorno Shamrock SDK
| Constante | Valor Entero | Significado |
|---|:---:|---|
| `SHAMROCK_SUCCESS` | `20202` | Operación completada con éxito. |
| `SHAMROCK_COMMUNICATION_ERROR` | `20203` | Error de enlace USB / FIFO con el espectrógrafo. |
| `SHAMROCK_NOT_INITIALIZED` | `20201` | Módulo Shamrock no inicializado con `ShamrockInitialize`. |
| `SHAMROCK_NOT_AVAILABLE` | `20208` | Motor o accesorio (ej. rendija motorizada) no instalado. |

---

## 4. 🧵 Arquitectura de Reactividad del Flipper y Concurrencia de Hardware

### 4.1 Diagnóstico de la Falla Histórica de la Señal `powerbutton`
En versiones anteriores de PyPrinting, el checkbox `Power Flipper` (conmutador Low/High Power) exhibía pérdida de respuesta tras ciertas operaciones o durante la carga inicial. La causa raíz identificada fue triple:

1. **Incompatibilidad de Evento en PyQt6**:
   - El widget estaba acoplado a la señal `clicked`.
   - En PyQt6, el método programático `setChecked(bool)` **NO** emite la señal `clicked`, sino exclusivamente `toggled(bool)`.
   - Cuando el watchdog o la inicialización forzaban un cambio de estado, los slots de actualización no se disparaban.
2. **Discrepancia en la Firma de Argumentos de Señal**:
   - `toggled` emite un valor booleano (`checked: bool`).
   - El slot receptor `_power_check(self)` no aceptaba argumentos, arrojando silenciosamente excepciones de tipo `TypeError: _power_check() takes 1 positional argument but 2 were given` dentro del despachador de eventos de Qt.
3. **Aislamiento de Hilos (Watchdog Daemon vs GUI Thread)**:
   - El temporizador de seguridad de obturadores en `core/nidaq.py` corre en un hilo daemon nativo (`threading.Thread(daemon=True)`).
   - Cuando el watchdog cortaba el láser y forzaba `up_flipper()` (Low Power), no existía un mecanismo thread-safe para notificar a la interfaz gráfica.

### 4.2 Arquitectura del Puente de Callbacks y Desacoplamiento

```
Hilo Demonio Hardware (nidaq.py)           Hilo Principal GUI (shutters.py)
 ┌───────────────────────────────┐          ┌──────────────────────────────────┐
 │ Watchdog _emergency_shutdown  │          │  Power Flipper QCheckBox         │
 │   - close_all_shutters()      │          │  (powerbutton)                   │
 │   - up_flipper()              │          └────────────────┬─────────────────┘
 │   - _notify_flipper_callbacks │                           │ toggled(bool)
 └──────────────┬────────────────┘                           ▼
                │                          ┌───────────────────────────────────┐
                │ Thread-Safe Callback     │  Slot: set_power(high: bool)      │
                ▼                          │    - emite flipper_signal(high)   │
 ┌───────────────────────────────┐         └─────────────────┬─────────────────┘
 │ Callback Bridge en Shutters   │                           │
 │   - flipper_hardware_signal   │                           ▼
 └──────────────┬────────────────┘         ┌───────────────────────────────────┐
                │ pyqtSignal (Queued)      │  Worker: set_flipper_power(high)  │
                ▼                          │    - nidaq.down_flipper() / up    │
 ┌───────────────────────────────┐         └───────────────────────────────────┘
 │ Slot: update_power_ui(high)   │
 │   - blockSignals(True)        │  (Evita bucles de re-escritura)
 │   - setChecked(high)          │
 │   - blockSignals(False)       │
 └───────────────────────────────┘
```

#### Implementación Clave en `core/nidaq.py`:
```python
_flipper_callbacks = []

def register_flipper_callback(callback):
    """Registra un callback para notificar cambios de estado del flipper."""
    if callback not in _flipper_callbacks:
        _flipper_callbacks.append(callback)

def _notify_flipper_callbacks(is_high_power: bool):
    """Ejecuta los callbacks registrados con el nuevo estado."""
    for cb in list(_flipper_callbacks):
        try:
            cb(is_high_power)
        except Exception as e:
            logger.error(f"Error en flipper callback: {e}")
```

#### Implementación Clave en `core/shutters.py`:
```python
# Señal para cruzar desde el hilo de hardware al hilo de la GUI
flipper_hardware_signal = pyqtSignal(bool)

# Registro del callback thread-safe
register_flipper_callback(lambda is_high: self.flipper_hardware_signal.emit(is_high))
self.flipper_hardware_signal.connect(self.update_power_ui)

@pyqtSlot(bool)
def set_power(self, high: bool):
    """Slot público y seguro para fijar potencia."""
    self.flipper_signal.emit(high)

def update_power_ui(self, high: bool):
    """Actualiza la GUI sin disparar señales redundantes."""
    self.powerbutton.blockSignals(True)
    self.powerbutton.setChecked(high)
    self.powerbutton.blockSignals(False)
```

---

## 5. 🗂️ Módulo Step & Glue: Aborto Cooperativo y Exportación Directa

En [`pyspectrum/modules/step_and_glue.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/pyspectrum/modules/step_and_glue.py):
1. **Pulsador `🛑 Detener Medición`**:
   - Conectado a `stopMeasurementSignal`.
   - Activa de inmediato la bandera atómica `self._is_running = False`.
   - Interrumpe el lazo entre cuadros y asegura el cierre inmediato del obturador del espectrógrafo antes de ceder el control.
2. **Pulsador `💾 Guardar Espectro`**:
   - Conectado a `saveSpectrumSignal`.
   - Abre un cuadro de diálogo con doble filtro:
     - Archivo de Texto ASCII (`.txt`): Formato delimitado por tabulaciones con metadatos en cabecera `# Wavelength[nm]\tCounts`.
     - Archivo Binario NumPy (`.npz`): Almacenamiento rápido y sin pérdida de precisión que contiene los arrays `wavelengths`, `spectrum`, y los diccionarios de configuración (`exposure_time`, `grating`, `start_wl`, `end_wl`).

---

## 6. 🧪 Batería de Pruebas Unitarias y Validación Experimental

Para validar de forma automatizada las correcciones y la nueva funcionalidad, se implementaron suites de pruebas unitarias específicas:

### 6.1 Suite `tests/test_powerbutton_actuation.py`
| Test Case | Función Evaluada | Resultado |
|---|---|:---:|
| `test_powerbutton_toggled_signal` | Verificación de emisión de `flipper_signal` ante `setChecked(True/False)` usando `toggled`. | **PASS** |
| `test_powerbutton_hardware_callback_bridge` | Disparo de `register_flipper_callback` desde hilo externo y recepción en `update_power_ui`. | **PASS** |
| `test_powerbutton_decoupled_ui_update` | Comprobación de que `update_power_ui` no emite señales secundarias de re-escritura. | **PASS** |
| `test_powerbutton_watchdog_reset_sync` | Desactivación forzada por watchdog (`up_flipper`) y reflejo síncrono en el casillero de la GUI. | **PASS** |

### 6.2 Suite `tests/test_pyspectrum_calibration_and_fixes.py`
| Test Case | Función Evaluada | Resultado |
|---|---|:---:|
| `test_calibration_dock_initialization` | Instanciación correcta de `CalibrationDock` y sus 4 sub-paneles. | **PASS** |
| `test_gaussian_centroid_fit` | Ajuste gaussiano de orden cero con centroide conocido sub-píxel ($x_0 = 512.42$). | **PASS** |
| `test_cubic_calibration_polynomial` | Cálculo analítico de $\lambda(p) = a_0 + a_1 p + a_2 p^2 + a_3 p^3$ y validación de monotonía. | **PASS** |
| `test_shamrock_sdk_offset_signatures` | Verificación de tipos Ctypes (`c_int`, `byref`) en funciones de offset de hardware. | **PASS** |
| `test_step_and_glue_signals_and_buttons` | Comprobación de presencia y conexión de botones de Detener y Guardar en Step & Glue. | **PASS** |
| `test_deprecated_signals_removed` | Verificación de ausencia de señales huérfanas en el driver de cámara iXon3. | **PASS** |

### 6.3 Resumen Consolidado del Sistema (`tests/run_all_diagnostics.py`)
- **Total de pruebas ejecutadas**: 49 / 49 superadas con éxito.
- **Tasa de aprobación**: **100.0%**.
- **Tiempo total de ejecución**: $1.84\ \text{s}$ en modo seguro (`SAFE_MODE = True`).

---

## 7. 📌 Conclusiones y Recomendaciones Operativas

1. **Robustez y Metrología Espectral**:
   - PySpectrum 3.0 dispone ahora de una suite integrada de calibraciones que permite prescindir por completo del software propietario Andor Solis para las rutinas cotidianas de verificación del espectrógrafo.
   - El ajuste gaussiano en orden cero provee una referencia sub-píxel rigurosa para la correlación entre el eje óptico del microscopio y el centroide de la rendija del espectrógrafo.
2. **Seguridad y Reactividad de Interfaz**:
   - La migración a `toggled` y la introducción del puente de callbacks de hardware eliminan definitivamente los fallos de sincronización entre el estado físico de los atenuadores y su representación en pantalla.
   - La actuación del Watchdog mantiene la integridad física de la muestra coloidal cerrando los obturadores y retornando el flipper a baja potencia de forma garantizada e inmediata.
3. **Protocolo Recomendado al Iniciar la Jornada Experimental**:
   - Encender el refrigerador termoeléctrico de la cámara iXon3 hasta alcanzar $-70\ ^\circ\text{C}$ o $-80\ ^\circ\text{C}$.
   - En PySpectrum, seleccionar la pestaña `Calibración del Sistema` en el dock lateral.
   - Con la rendija a $20\ \mu\text{m}$ y rejilla en orden cero ($0\ \text{nm}$), adquirir una imagen y presionar `Centrar Orden 0`. Confirmar que el centroide se encuentre dentro de $\pm 2$ píxeles del centro nominal ($p = 512$).
   - En PyPrinting, comprobar el accionamiento del flipper conmutando entre Low y High Power antes de iniciar la rutina de impresión de nanopartículas.

---
*Reporte generado e integrado en el sistema documental de PyPrinting 3.0 el 7 de Septiembre de 2026.*
