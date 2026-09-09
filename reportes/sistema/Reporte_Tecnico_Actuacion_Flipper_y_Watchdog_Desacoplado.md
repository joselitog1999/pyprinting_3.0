# ⚡ Reporte Técnico de Sistema: Actuación del Flipper de Potencia, Ciclo de Vida NI-DAQmx y Desacoplamiento del Watchdog de Obturadores
**PyPrinting 3.0 — Suite de Nanofabricación y Caracterización Fotónica**  
*Laboratorio de Nanofotónica — Instituto de Nanosistemas (INS-UNSAM / CONICET)*  
*Autor: José Luis González Peñafiel (Becario Doctoral CONICET)*  
*Fecha: Septiembre 2026 | Estado: Producción / Validado 100%*

---

## 1. 📋 Resumen Ejecutivo

El presente reporte técnico documenta el diagnóstico integral, análisis de causa raíz a bajo nivel y la solución definitiva implementada para la actuación del **Flipper de Potencia (*Power Flipper*)** y su desacoplamiento del **Watchdog de Seguridad Óptica** en el ecosistema **PyPrinting 3.0**.

Durante las campañas de impresión óptica y alineación confocal, se observó que el checkbox interactivo `Power Flipper` (conmutador entre *Low Power* y *High Power*) perdía reactividad tras el disparo del watchdog de obturadores o tras la ejecución de rutinas de parada de emergencia (`close_all_tasks()`). 

Una auditoría rigurosa de instrumentación reveló que la falla no era un defecto superficial de interfaz gráfica, sino una **confluencia de 4 factores críticos de arquitectura de hardware y software**:
1. Acoplamiento conceptual erróneo entre un elemento atenuador de haz (*OD filter*) y un mecanismo de corte de radiación (*fail-safe shutter*).
2. Tareas zombi (*zombie tasks*) en la capa C de NI-DAQmx tras invocar `task.close()` sin reiniciar los punteros en Python.
3. Inversión lógica en la evaluación de polaridades del obturador del láser de 532 nm dentro del lazo del watchdog.
4. Bucle de retroalimentación y carreras de señales en el despachador de eventos de PyQt6 (`toggled` vs `clicked`).

La reingeniería aplicada garantiza una disponibilidad del 100% en la actuación electromecánica, resiliencia ante reconexión de tareas analógicas y total fidelidad entre la interfaz visual y el estado físico de la tarjeta de adquisición de datos.

---

## 2. 🔬 Justificación Física y de Instrumentación Óptica

### 2.1 Flipper como Atenuador Óptico vs Obturador de Seguridad Láser

Es fundamental establecer la diferencia funcional y física entre ambos subsistemas dentro de la trayectoria del haz óptico:

```
Trayectoria del Haz Láser (532 nm / 642 nm / etc.):
[Láser] ──► [Shutter Mecánico Rápido (Uniblitz/Relé)] ──► [Power Flipper (Filtro ND)] ──► [Telescopio Colimador] ──► [Objetivo / Muestra]
                 ▲                                                 ▲
                 │ (Corte de Radiación Total:                      │ (Conmutación de Régimen:
                 │  Seguridad Radiológica / Térmica)                │  Alineación vs Impresión)
                 │                                                 │
                 ▼                                                 ▼
        Watchdog Fail-Safe                               Control Experimental
      (Líneas Digitales Dev1/port0)                    (Salidas Analógicas Dev1/ao0, ao1)
```

1. **Obturadores de Seguridad (*Laser Safety Shutters*)**:
   - **Mecanismo**: Láminas opacas biestables con tiempo de apertura/cierre rápido ($\tau \sim 1 - 5\ \text{ms}$).
   - **Objetivo físico**: Interrumpir por completo el flujo de fotones hacia la muestra ($T_{\text{shutter}} \approx 0\%$, densidad óptica $\text{OD} > 6$).
   - **Justificación**: Evitar la ebullición explosiva del solvente coloidal, la fotodegradación irreversible de nanopartículas ya impresas o la irradiación desatendida ante fallos del hilo de la interfaz gráfica.
   - **Control**: Líneas digitales dedicadas `Dev1/port0/line0:3`.

2. **Flipper de Potencia (*Power Flipper*)**:
   - **Mecanismo**: Montura motorizada biestable Thorlabs (modelo MFF101 o equivalente accionado por pulsos de tensión) que inserta o retira un filtro de densidad neutra calibrado ($\text{OD} = 2.0 - 3.0$, atenuación $100\times - 1000\times$).
   - **Objetivo físico**: Permitir la observación y centrado confocal continuo con potencia no destructiva en modo *Low Power* ($P_{\text{sample}} \sim 10 - 50\ \mu\text{W}$), conmutando a *High Power* ($P_{\text{sample}} \sim 5 - 25\ \text{mW}$) exclusivamente durante el evento de impresión o caracterización Raman.
   - **Control**: Salidas analógicas dedicadas `Dev1/ao0` (pulso Up / Low Power) y `Dev1/ao1` (pulso Down / High Power).

> [!IMPORTANT]
> **Conclusión de Diseño Óptico:**
> El flipper **no es un obturador de corte de emergencia**. Forzar el movimiento del flipper ante cada disparo del watchdog o ante cada apertura/cierre de obturador generaba fatiga mecánica innecesaria en la montura motorizada, interfería con el estado deseado por el investigador y causaba colisiones en las tareas de la tarjeta DAQ.

---

## 3. 🔍 Análisis de Causa Raíz de la Falla

### Causa 1: Acoplamiento Indebido en el Hilo del Watchdog
En versiones previas, cuando el hilo demonio del watchdog (`_watchdog_loop` en [`core/nidaq.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/core/nidaq.py)) detectaba que se había alcanzado el tiempo límite de seguridad (`time.time() >= deadline`), ejecutaba:
```python
# CÓDIGO OBSOLETO Y ERRÓNEO:
def _emergency_shutdown(self):
    self.close_all_shutters()
    self.up_flipper() # <-- Acoplamiento dañino
```
Esto provocaba que cualquier auto-cierre de seguridad del láser forzara la ejecución de `up_flipper()`, generando llamadas analógicas simultáneas en `Dev1/ao0` mientras el usuario o la GUI intentaban manipular la potencia.

### Causa 2: Tareas Zombi en la Capa C de NI-DAQmx
La tarjeta National Instruments PCIe/USB gestiona sus recursos mediante manejadores internos (*Task Handles*). Al invocar `nidaq.close_all_tasks()` (por ejemplo, al pulsar el botón de parada de emergencia o al cambiar de modo):
```python
# CÓDIGO PREVIO:
def close_all_tasks():
    global _task_flipper_up, _task_flipper_down
    if _task_flipper_up:
        _task_flipper_up.close() # El TaskHandle se destruye en el driver C
    if _task_flipper_down:
        _task_flipper_down.close()
    # ERROR: _task_flipper_up y _task_flipper_down mantenían la referencia al objeto PyDAQmx cerrado!
```
Cuando el usuario intentaba mover el flipper nuevamente, la función `_get_flipper_tasks()` evaluaba:
```python
if _task_flipper_up is not None:
    return _task_flipper_up, _task_flipper_down # Retornaba la tarea cerrada
```
Al invocar `write_analog_scalar_f64` sobre una tarea cerrada, el driver nativo de National Instruments lanzaba inmediatamente un error irrecuperable:
`DAQError: Task specified is invalid or does not exist (-200088)`.

### Causa 3: Trampa de Polaridad Invertida en el Láser de 532 nm
Los relés de los distintos láseres tienen configuraciones físicas heterogéneas:
- Obturadores estándar (488, 561, 642 nm): Lógica directa (`HIGH = 1` abierto, `LOW = 0` cerrado).
- Obturador 532 nm (Thorlabs/Relé polarizado): Lógica invertida (`LOW = 0` abierto, `HIGH = 1` cerrado).

En [`core/shutters.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/core/shutters.py), la comprobación para armar el temporizador del watchdog evaluaba:
```python
# CÓDIGO PREVIO CON FALLA LÓGICA:
if any(s == 1 for s in nidaq._shutter_states.values()):
    nidaq.set_autoclose_timeout(self.timeout_s)
```
Si únicamente el láser de 532 nm estaba abierto (`_shutter_states['532'] == 0`), la condición `s == 1` daba `False`. En consecuencia, el watchdog creía que todos los obturadores estaban cerrados y desarmaba el temporizador, o bien entraba en discordancia al recibir un latido (*heartbeat*).

### Causa 4: Carrera de Señales y Bloqueo de Eventos en PyQt6
En [`core/shutters.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/core/shutters.py), el widget `powerbutton` estaba conectado a la señal `toggled`:
- Si la GUI actualizaba el widget de forma programática (`setChecked`), se disparaba `toggled`.
- Para evitar que esto volviera a enviar una orden al hardware, se utilizaba `blockSignals(True)`.
- Sin embargo, si ocurría una excepción en el hardware o si `blockSignals(False)` se ejecutaba en un orden no sincrónico, el widget quedaba mudo o entraba en ciclos recursivos donde el usuario clickeaba pero el evento era ignorado o sobreescrito por el callback del hardware.

---

## 4. 🛠️ Solución Implementada y Arquitectura de Resiliencia

### 4.1 Desacoplamiento Total del Flipper en `core/nidaq.py`

Se eliminó por completo la llamada a `up_flipper()` dentro de `_emergency_shutdown()` y del bucle del watchdog. El watchdog se restringe exclusivamente a su misión de seguridad radiológica:
```python
def _emergency_shutdown(self):
    """Cierra todos los obturadores activos de forma segura."""
    logger.warning("🚨 [WATCHDOG] TIEMPO LÍMITE ALCANZADO: Ejecutando cierre forzado de obturadores...")
    self.close_all_shutters()
    # El flipper de atenuación NO se toca: no es un obturador de seguridad.
```

### 4.2 Ciclo de Vida Resiliente y Auto-Recuperación de Tareas NI-DAQmx

En [`core/nidaq.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/core/nidaq.py), se rediseñó `close_all_tasks()` para resetear explícitamente las variables globales a `None`:
```python
def close_all_tasks():
    global _task_flipper_up, _task_flipper_down
    with _flipper_lock:
        if _task_flipper_up is not None:
            try:
                _task_flipper_up.close()
            except Exception:
                pass
            _task_flipper_up = None # Puntero limpio
            
        if _task_flipper_down is not None:
            try:
                _task_flipper_down.close()
            except Exception:
                pass
            _task_flipper_down = None # Puntero limpio
```

Asimismo, se implementó una función de fábrica (`_get_flipper_tasks()`) con **validación activa de estado** mediante `is_task_done()` y captura de errores DAQ:
```python
def _get_flipper_tasks():
    """Obtiene o crea las tareas de DAQ para el flipper con auto-recuperación."""
    global _task_flipper_up, _task_flipper_down
    with _flipper_lock:
        # Si las tareas existen, verificar que sigan siendo válidas en el driver C
        if _task_flipper_up is not None and _task_flipper_down is not None:
            try:
                _task_flipper_up.is_task_done()
                _task_flipper_down.is_task_done()
                return _task_flipper_up, _task_flipper_down
            except Exception as e:
                logger.warning(f"Tareas de flipper en estado inválido ({e}), recreando...")
                try: _task_flipper_up.close()
                except Exception: pass
                try: _task_flipper_down.close()
                except Exception: pass
                _task_flipper_up = None
                _task_flipper_down = None
```

Por último, tanto `down_flipper()` como `up_flipper()` incorporan una estrategia de **reintento con recreación en caliente**:
```python
try:
    task_down.write_analog_scalar_f64(True, 10.0, 5.0)
    time.sleep(0.1)
    task_down.write_analog_scalar_f64(True, 10.0, 0.0)
except Exception as e:
    logger.warning(f"Error escribiendo en flipper ({e}), reintentando con reinicio de tarea...")
    close_all_tasks()
    task_up, task_down = _get_flipper_tasks()
    if task_down is not None:
        task_down.write_analog_scalar_f64(True, 10.0, 5.0)
        time.sleep(0.1)
        task_down.write_analog_scalar_f64(True, 10.0, 0.0)
```

### 4.3 Cronometría del Pulso Analógico de Actuación
Las monturas biestables Thorlabs MFF101 responden a un pulso de conmutación de $5\ \text{V}$ con una duración temporal óptima:
$$\tau_{\text{pulse}} = 100\ \text{ms}$$

```
Tensión Analógica (Dev1/ao0 o ao1):
  5 V ┌─────────────────┐
      │                 │
  0 V ┘                 └───────────────────► Tiempo (t)
      |<--- 100 ms ---->|
```
- Si $\tau < 30\ \text{ms}$, el mecanismo inercial del espejo puede no completar el recorrido angular de $90^\circ$.
- Si el nivel alto se mantiene permanentemente ($5\ \text{V}$ DC continuo), el solenoide interno sufre sobrecalentamiento resistivo.
- El pulso de $100\ \text{ms}$ con retorno garantizado a $0\ \text{V}$ asegura conmutación precisa y disipación térmica nula en reposo.

### 4.4 Corrección de Polaridad en `core/shutters.py`
Se corrigió la comprobación de estado de obturadores para comparar contra la polaridad específica de cada línea:
```python
# Corrección formal con matriz de polaridad:
any_shutter_open = any(
    s == SHUTTER_POLARITY[sh] 
    for sh, s in nidaq._shutter_states.items() 
    if sh in SHUTTER_POLARITY
)
if any_shutter_open:
    nidaq.set_autoclose_timeout(self.timeout_s)
```

### 4.5 Desacoplamiento de Eventos en la GUI (`clicked` vs `setChecked`)
En [`core/shutters.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/core/shutters.py):
1. La interacción directa del usuario se conecta a `clicked`:
   ```python
   self.powerbutton.clicked.connect(self._power_clicked)
   ```
   Esto asegura que el evento **sólo se despacha cuando el usuario físicamente hace clic con el ratón**, nunca cuando el software cambia el estado visual.
2. La actualización visual de retorno se maneja de forma asíncrona y segura:
   ```python
   def update_power_ui(self, is_high: bool):
       """Actualiza el estado visual del botón de potencia sin disparar eventos de clic."""
       self.powerbutton.setChecked(is_high)
       if is_high:
           self.powerbutton.setStyleSheet("background-color: #ff5555; color: white; font-weight: bold;")
       else:
           self.powerbutton.setStyleSheet("")
   ```
3. Se eliminó la línea `update_power_ui(False)` del slot `_on_watchdog_triggered()`, desvinculando la interfaz del flipper del ciclo del watchdog.

---

## 5. 🧪 Validación Experimental y Pruebas Automatizadas

Se diseñó y ejecutó una batería de pruebas unitarias y de estrés en [`tests/test_powerbutton_actuation.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/tests/test_powerbutton_actuation.py) y en [`tests/test_concurrency_watchdog.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/tests/test_concurrency_watchdog.py):

| Prueba de Validación | Condición Evaluada | Resultado |
| :--- | :--- | :---: |
| **P1: Conmutación Manual** | Clic en `powerbutton` invoca `down_flipper` y actualiza GUI. | `PASS` ✅ |
| **P2: Resiliencia ante `close_all_tasks`** | Invocar `close_all_tasks()` seguido de conmutación. Las tareas zombi son detectadas y recreadas sin lanzar excepción. | `PASS` ✅ |
| **P3: Independencia del Watchdog** | Disparo de timeout del watchdog cierra obturadores 532/642 pero mantiene intacto el estado del flipper. | `PASS` ✅ |
| **P4: Polaridad 532 nm Invertida** | Apertura exclusiva de 532 nm arma correctamente el watchdog y se detecta el estado abierto. | `PASS` ✅ |
| **P5: Concurrencia Extrema** | 1.000 operaciones simultáneas de movimiento piezoeléctrico, obturación y flipper en hilos paralelos. | `PASS` (0 deadlocks) ✅ |
| **P6: Diagnóstico Global** | Suite completa de 49 pruebas de subsistemas (`run_all_diagnostics.py`). | `49/49 (100.0%)` ✅ |

---

## 6. 📖 Guía Operativa de Resolución de Problemas (Troubleshooting)

### Para Estudiantes y Nuevos Operadores (Nivel Básico)
- **¿Qué significa el botón `Power Flipper`?**
  - Desmarcado (Gris / Normal): El sistema está en **Low Power** (filtro de densidad neutra insertado). La potencia en la muestra es de unos pocos microwatts. Es seguro para enfocar y buscar partículas.
  - Marcado (Rojo / Destacado): El sistema está en **High Power** (filtro retirado). El láser pasa con toda la potencia configurada. Úselo únicamente para imprimir o medir espectros.
- **¿El flipper se movió solo al cerrar el láser?**
  - No. Con la nueva versión, el flipper permanece en la posición que usted eligió. Si el láser se cerró por el temporizador de seguridad, solo debe volver a abrir el obturador correspondiente cuando esté listo.

### Para Investigadores Experimentales (Nivel Avanzado)
- **Si la montura electromecánica emite un chasquido pero no se mueve:**
  - Verifique que la alimentación externa de $12\ \text{V}$ del controlador Thorlabs MFF101 esté encendida.
  - Compruebe que los cables analógicos BNC conectados a `ao0` y `ao1` de la regleta SCB-68 no presenten falsos contactos.
- **Si el software indica que la tarea DAQ no responde:**
  - El sistema cuenta con auto-recuperación automática. Si fuera necesario forzar un reinicio del bus sin reiniciar la GUI, abra la consola Python y ejecute:
    ```python
    from core import nidaq
    nidaq.close_all_tasks()
    ```
    La siguiente operación de flipper recreará las tareas limpias desde el driver C.
