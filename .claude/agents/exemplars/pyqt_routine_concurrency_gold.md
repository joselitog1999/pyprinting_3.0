# Gold Exemplar: Elegir la Topología de Concurrencia de una Rutina PySpectrum

Referenciado por `software-architect.md`, `instrumentation.md`. Consultar **antes** de escribir
una rutina nueva en `pyspectrum/modules/routines/`, porque esta decisión es difícil de revertir:
una vez que los slots asumen un hilo, moverlos después toca cada `connect()`.

## La convención por defecto: `QTimer` en el hilo GUI

La mayoría de las rutinas de pyspectrum **no** usan `moveToThread`. Corren su
`Backend(QObject)` en el hilo GUI y avanzan encadenando pasos cortos:

```python
# Patrón canónico — la forma de pyspectrum/modules/routines/growth_kinetics.py, corregida
from config import pi, clamp_axis_um, wait_on_target
from core.nidaq import heartbeat_shutter

def _process_next_node(self):
    if self._abort or self._idx >= len(self._nodes):
        return self._finish()

    node = self._nodes[self._idx]
    heartbeat_shutter()                        # en CADA paso, sin argumento: rige la política del operador
    pi.MOV([1, 2], [clamp_axis_um(1, node["x"]), clamp_axis_um(2, node["y"])])
    if not wait_on_target([1, 2], on_tick=heartbeat_shutter):   # acotada; False = no llegó
        return self._abort_cleanly("la platina no confirmó la llegada")   # cierra obturadores
    self._idx += 1

    QTimer.singleShot(0, self._process_next_node)   # cede el control al event loop
```

Ceder el control en cada paso es lo que mantiene vivos el heartbeat del watchdog y el botón
E-STOP. `wait_on_target()` suele volver en milisegundos, pero en el peor caso bloquea el hilo GUI
hasta su timeout: está acotada y termina en aborto, y si una rutina encadena varias esperas así,
el criterio de abajo la manda a un `QThread`. `singleShot(0)` sirve para encadenar pasos sin
cadencia propia; un tick de adquisición que necesita cadencia usa un período explícito
(`software-architect.md` §5).

**El archivo real todavía no es así** (hallazgo del 2026-09-27): usa `heartbeat_shutter(30.0)`, que
pisa la política del operador (ver abajo), y `move_stage_to()` de
`pyspectrum/modules/optical_support.py`, que espera con su propio bucle de `qONT()` sin renovar el
heartbeat y, si vence el tiempo, devuelve la posición actual como si la platina hubiera llegado. No
copiar esas dos llamadas. Cuando un paso necesita esperar de verdad, se usa un `QEventLoop` anidado **acotado**
en vez de `time.sleep()`, que congelaría el hilo GUI:

```python
loop = QEventLoop()
timer = QTimer()
timer.setSingleShot(True)
timer.timeout.connect(loop.quit)
timer.start(int(wait_ms))
loop.exec()
```

## El criterio de decisión

| Si un paso individual… | Topología | Por qué |
| :--- | :--- | :--- |
| dura pocos ms y no bloquea | **`QTimer` en hilo GUI** (por defecto) | Sin costo de sincronización, sin riesgo de tocar widgets desde otro hilo |
| bloquea cientos de ms o más | **`QThread` real** (`moveToThread`) | En el hilo GUI, un `sleep`/poll largo deja sin respuesta el heartbeat y el E-STOP |

El umbral no es estético: es **si el heartbeat de obturadores puede vencer durante el paso**.

## Las tres excepciones documentadas

Sólo tres componentes usan `QThread` real. Cada uno tiene una razón registrada; si una rutina
nueva no encaja en ninguna de estas formas, la respuesta por defecto es `QTimer`.

| Componente | Ubicación | Razón registrada |
| :--- | :--- | :--- |
| Escaneo lineal espectral | `pyspectrum/modules/routines/linescan_spectroscopy.py` | Un punto en modo Step & Glue encadena varios movimientos de red, cada uno con su settle, más la exposición: segundos a minutos (`DEC-006`, `DEC-007`) |
| Mapeo confocal hiperespectral | `pyspectrum/window.py` | Cada punto bloquea con un `pi.MOV()` más una exposición/lectura CCD completa, cientos o miles de veces por mapa (`ANOM-HYPERSPEC-01`) |
| Live View de Exploración | `pyspectrum/ui/exploration_tab.py` | Sostener 20-30 fps continuos sin bloquear el hilo GUI ni el E-STOP |

## La trampa de seguridad específica del `QThread` real

Esta es la parte que no es obvia y que motivó `DEC-006`:

> Un worker en un `QThread` real **no puede confiar en `emergencyStopSignal` para
> interrumpirlo** mientras está bloqueado. Una señal de Qt se entrega sólo cuando el hilo
> receptor vuelve a su event loop — y un worker bloqueado, por definición, no volvió.

```python
# INCORRECTO — la señal nunca llega durante el bloqueo
hardware_session.emergencyStopSignal.connect(self._abort)   # no interrumpe un sleep/poll

# CORRECTO — consultar la propiedad thread-safe entre cada sub-paso bloqueante
for target in positions:
    if hardware_session.is_emergency_stopped:               # protegida por RLock, sin event loop
        return self._abort_cleanly()
    self._move_and_settle(target)
```

El `QTimer` en hilo GUI no tiene este problema: como cede el control en cada paso, la señal
llega. Es una razón más para que sea el caso por defecto.

## Reglas que valen en ambas topologías

* `heartbeat_shutter()` en **cada iteración** de cualquier espera, no una vez por paso: una sola
  exposición larga puede agotar el deadline del watchdog (`.claude/shared/lab-invariants.md` §1).
  Sin argumento: un `heartbeat_shutter(30.0)` explícito pisa la política global y rearma un corte
  fijo aun en modo "Sin límite" (C-29), que es lo que hacen hoy las rutinas de PySpectrum.
* El watchdog nunca debe cortar una rutina sana (investigador, R1-10). La protección contra una
  rutina **colgada** será un latido de vida emitido por la propia rutina, y el watchdog cortará sólo
  si ese latido se detiene (R2-8). El diseño está pendiente y es política del watchdog, así que
  nunca es exento: no inventar el mecanismo dentro de una rutina nueva.
* Todo poll de hardware va **acotado por timeout**, nunca `while True`
  (ver `exemplars/hardware_timing_and_safety_gold.md`).
* Los widgets se tocan sólo desde el hilo GUI. Un worker en `QThread` emite `pyqtSignal` con
  arrays o dataclasses; no llama a `setText()` ni a `setData()`.
* En abortar: cerrar obturadores y liberar la sesión de hardware de forma incondicional e
  idempotente, sin asumir en qué punto del ciclo se estaba.

## Checklist de falsificación antes de aceptar una rutina nueva

1. ¿Cuál es el paso más largo, medido y no estimado? Si supera unos pocos ms, ¿por qué no es un
   `QThread`?
2. Si es `QThread`: ¿dónde se consulta `is_emergency_stopped`, y cuál es el intervalo máximo
   entre dos consultas consecutivas?
3. ¿Hay algún camino —abortar, excepción, fin normal— que salga sin cerrar obturadores?
4. ¿Algún `emit()` manda una matriz 2D completa por tick? (`DEC-013`: satura el event loop y los
   usuarios lo reportan como que el programa se cuelga.)
