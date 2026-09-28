# PySpectrum 3.0, bloque A — Ronda 3: diseño de GUI y ergonomía (líder: `scientific-gui-designer`)

- **Fecha:** 2026-09-28. **Agente:** `scientific-gui-designer`. **Ronda:** 3 ("Human-in-the-Loop", `CLAUDE.md` §5).
- **Alcance:** pasos 7, 8, 10, 11, 12 y 14 de la Ronda 2 (`../pyspectrum_A_ronda2/README.md` §4): panel de estado del espectrómetro, "espejo rápido" (orden cero), pestaña Calibraciones (rutina automática, escritura de offsets, historial), Step & Glue (y escaneo lineal sobre el mismo motor), aviso de arranque "equipo difiere del archivo", aviso de "Reconectar cámara".
- **Método:** Graphify primero; después, lectura de los archivos de GUI señalados. Nada contra hardware. **Sin código de producción**: mockups ASCII, inventario de widgets, textos y pseudocódigo de señales.
- **Vinculante:** `RESPUESTAS_INVESTIGADOR.md` §R4, §R4-A, §R4-B; `../pyspectrum_A_ronda2/` (README, `software_architect.md` §2, §5, §6; `instrumentation.md` §1-§5; `metrology.md` §4).

> Estado del documento: **completo** (§0-§9). Los números de los mockups son ilustrativos salvo los que citan su fuente.

## Rótulos

| Rótulo | Significado |
| :--- | :--- |
| **[PROPUESTA]** | Diseño de esta ronda, a aprobar por el investigador. |
| **[R2-arq] / [R2-inst] / [R2-met]** | Contrato de la Ronda 2 (`software_architect.md`, `instrumentation.md`, `metrology.md`). |
| **[R4-x]** | Decisión del investigador en `RESPUESTAS_INVESTIGADOR.md`. |
| **[V-código]** | Verificado leyendo el código actual (archivo:línea) en esta ronda. |
| **[FALTA-CONTRATO]** | La GUI necesita algo que la Ronda 2 no definió; va a la reconciliación (§6). |
| **[I]** | Inferencia mía. |

---

## 0. Hechos de la GUI actual que condicionan el diseño

Leídos en esta ronda [V-código]. Cada uno es un defecto que el diseño nuevo tiene que hacer imposible, no sólo corregir.

### 0.1 El panel izquierdo muestra lo que el widget cree, no lo que el equipo dice

| # | Hecho | Dónde | Consecuencia de diseño |
| :-- | :--- | :--- | :--- |
| G-01 | "Enfriador: ON" es el estado inicial del botón (`setChecked(True)`), sin haber enviado nada | `left_hardware_panel.py:104-107` | El botón del enfriador pasa a ser un **reflejo de `IsCoolerOn`**; su texto nunca lo pone el clic (§1.3) |
| G-02 | El setpoint arranca en −65 °C en el widget; R4-A 6 pide −60 °C | `:97-99` | El setpoint se muestra "enviado: −60 °C" desde el `BaselineReport` |
| G-03 | La temperatura se pinta "Enfriando…" ante **cualquier** código distinto de `DRV_TEMP_STABILIZED`, incluidos `DRV_TEMP_OFF`, `DRV_ACQUIRING` y errores | `:331-337` | El estado `DRV_TEMP_*` se traduce en palabras, uno por uno (§5.3, T-CAM-2) |
| G-04 | Cambiar el combo de red **mueve la torreta en el acto** (`currentIndexChanged` → `ShamrockSetGrating`), sin puerta ni hilo. La rueda del ratón sobre el combo basta para girarla | `:171-175`, `:310-313` | Ningún combo de hardware actúa al cambiar: se elige y se pulsa **Ir**. Los combos de hardware ignoran la rueda (§2.1-3) |
| G-05 | Los combos de puertos llaman a `ShamrockSetFlipper` (función inexistente, C-07) al cambiar | `:186-197` | Los puertos se muestran leídos; hay un solo botón "Fijar Side/Direct" (§1.3) |
| G-06 | "Ir a λ" acepta 0-2000 nm y llama directo a `ShamrockSetWavelength`: 40 nm con la red de 150 es condición especular sin protección | `:205-215`, `:320-322` | Todo movimiento va por `SpectrographWorker` → puerta; el campo muestra en vivo si el destino es especular (§3.3) |
| G-07 | El tooltip de la ganancia describe la "salvaguarda de 5×" que la Ronda 2 elimina, y el rango es 0-1000 "×" cuando el modo 0 es DAC 0-255 | `:120-124` | Rango desde `GetEMGainRange`; unidad "DAC" (T-CAM-4) |
| G-08 | Exposición 1e-4 a 60 s en el panel; la Ronda 2 fija 10 s para rutinas y 60 s como tope del driver (R4-B 9) | `:140-146` | Dos topes visibles y rotulados (§2.2) |
| G-09 | La λ mostrada se llama "λ actual"; el SDK probablemente devuelve su propio objetivo, no una medición [R2-inst §4.4] | `:339-341` | Rótulo "λc (SDK)" y tooltip que lo aclara (T-SPEC-2) |

### 0.2 El orden cero tiene hoy un diálogo que se volvería rutina

- `ZeroOrderSafetyDialog` (`zero_order_dialog.py:32-169`) muestra cinco botones en cada entrada al orden cero, incluido "Ignorar y Continuar (Override Experto)", que mueve con ganancia > 0 y láseres abiertos (`:150-156`).
- Lee la ganancia con `val[1]` sin mirar el código (`:23-29`): una lectura fallida se ve como "🟢 Ganancia EM: 0x (segura)".
- `SAFE_EXPOSURE_TIME_S = 0.01` (`:43`) es un literal local; la Ronda 2 lo lleva a `config.SPECULAR_MAX_EXPOSURE_S` (provisorio 10 ms, BANCO-43).
- Ctrl+0 abre ese diálogo (`window.py:577-580`), el dock de Calibraciones tiene su propio botón "Mover a Orden Cero" (`calibration_dock.py:150-157`) y el dock legado otro camino. **Tres botones, tres comportamientos.**
- **Consecuencia:** el diálogo se retira (R4-A 3, R4-B 3). Queda un único control, "Espejo rápido", con el mismo resultado desde cualquier lugar (§1.4).

### 0.3 La pestaña Calibraciones escribe al equipo con un clic

| # | Hecho | Dónde |
| :-- | :--- | :--- |
| G-10 | "Escribir Rejilla", "Escribir Detector" y "Escribir SDK" (cero de ranura) escriben sin diff, sin respaldo y sin confirmación, con rangos ±50 000 y ±10 000 pasos (el tope del SDK es 20 000 para la red, [R2-inst §3.1]) | `calibration_dock.py:223-275` |
| G-11 | "Cargar Calibración" y "Cargar Última Calibración" también escriben offsets (V10 de la Ronda 2) | `:369-383` → `:1010-1017` |
| G-12 | La red 3 (espejo) figura como calibrable, con el tooltip "Reflexión especular directa para microscopía confocal" | `:243-251` |
| G-13 | Tooltips sin fuente o contradichos: "memoria no volátil" (la persistencia no está confirmada, BANCO-37), "p = 0 a 1001" (el eje tiene 1004 píxeles), "40-50 µm: ~1 Airy Disk del objetivo 100x" (sin fuente), "Blaze 800 / 500 nm" escrito a mano (se lee con `GetGratingInfo`) | `:166-171`, `:243-251`, `:262`, `:293` |
| G-14 | "Perfil halógeno: Modelo Planck Activo (T=3100 K)" como estado por defecto: un perfil sintético presentado como calibración | `:333-336` |
| G-15 | "Pixel X Central del Slit" arranca en 501.25 px, un valor escrito en el código (`spectroscopy_context.py:47`), y se muestra como si fuera una medición | `:194-203` |

**Consecuencia:** la pestaña se reorganiza (§1.6). Ninguna escritura sale de un botón directo; los offsets sólo se escriben desde la rutina, con la transacción (R4-B 1). El detector y el cero de ranura quedan de sólo lectura (R2-inst §3.2).

### 0.4 Step & Glue

| # | Hecho | Dónde |
| :-- | :--- | :--- |
| G-16 | Campos de texto libres (`QLineEdit`) para λ y exposición: "abc" se ignora en silencio (`except ValueError: pass`) | `step_and_glue.py:103-146`, `:274-297` |
| G-17 | Rango por defecto 450-950 nm; el uso real es 500-900 nm (R4-A 4) | `:132-140` |
| G-18 | "Normalizar con Lámpara Halógena" tildado por defecto, y sin archivo de lámpara normaliza con el cuerpo negro sintético de G-14 | `:170-173` |
| G-19 | "Detener" promete "de manera inmediata y segura", pero la rutina corre en el hilo GUI y no hay E-STOP efectivo durante la exposición (V7) | `:218-222` |
| G-20 | Los datos quedan en memoria hasta "Exportar HDF5" (R1-I §1.5-5) | `:250-254` |
| G-21 | La barra de progreso sólo dice "Paso i / n": no hay plan visible antes de arrancar (cuántas ventanas, cuánto tarda) | `:225-230` |

### 0.5 Exploración, tablero y cierre

- **Overlay de la ranura en Exploración:** el ancho en píxeles es `ancho_µm / 8 µm` (`exploration_tab.py:324-328`), es decir, supone una magnificación 1:1 de la ranura al detector. **Esa magnificación no está verificada** para el SR-500i [I]. El centro sale del 501.25 inventado de G-15. El diseño dibuja la banda **medida** en la imagen y deja la calculada como guía rotulada (§3.2).
- **Tablero de hardware:** "Re-scan" "re-escanea y reconecta en caliente" (`hardware_dashboard.py:117-119`), que con Andor y Shamrock es un `ShutDown` que apaga el enfriador (V5). Además, cada equipo tiene una casilla "Aislar (Mock)" (`:163-164`): fuera de SAFE_MODE eso es un simulador silencioso en producción (memoria *no-silent-mock-in-production*). El diseño la deshabilita para Andor y Shamrock fuera de SAFE_MODE (§1.12).
- **Cierre de PySpectrum:** "¿Desea cerrar la sesión de PySpectrum y apagar cámaras y láseres?" (`window.py:771-776`) no dice qué pasa con la platina ni con el enfriador. R4-B 6 fija (50, 50, 10) µm (§1.13).

### 0.6 Lo que ya funciona y se conserva

- La barra superior con E-STOP (`Ctrl+E`, `F12`, `lab-invariants` §4) y "Rearmar Sistema" (`window.py:241-285`).
- El `LinearRegionItem` de ROI vertical en Exploración, que ya propaga a `spectroscopy_context` (`exploration_tab.py:205-211`).
- El patrón `blockSignals` del colormap y de la ranura (`left_hardware_panel.py:296-306`).
- `ScientificWikiBrowserDialog.navigate_to(note_id, anchor)` (`analysis/scientific_wiki_browser.py:954`), ya usado por `lattice_disorder_gui.py:2744`. Sólo descubre notas `CAT-`, `SYS-` y `MOD-` (`:109-132`), así que los `[Ayuda]` de esta ronda apuntan a esas carpetas (§5.4).

## 1. Arquitectura de la información [PROPUESTA]

### 1.1 Principios

1. **Lo que se ve es lo leído.** Cada valor de hardware lleva una marca de procedencia en texto y color, nunca sólo en color:

   | Marca | Significado | Estilo |
   | :--- | :--- | :--- |
   | `[L]` leído | `Reading.status == READ_OK`; muestra la edad si pasa de 3 s ("hace 12 s") | texto `#cdd6f4`, marca `#a6e3a1` |
   | `[E]` enviado | el SDK no tiene getter (modo de lectura, de adquisición, ventilador, modo de ganancia; README R2 §1): sólo consta el `DRV_SUCCESS` de la escritura | texto `#cdd6f4`, marca `#74c7ec` |
   | `[!]` falló | `READ_FAILED`: "—" y el código ("falló la lectura, 20075") | marca y texto `#f38ba8` |
   | `[?]` sin leer | `NOT_READ` (p. ej. el Shamrock mientras una rutina tiene la sesión, antes de su primera publicación) | `#6c7086` |
   | `[X]` no conectado | `NOT_CONNECTED`: el sub-panel entero se deshabilita y muestra el motivo | banda `#f38ba8` sobre `#181825` |
   | `[D]` derivado | calculado de lecturas (condición especular, Δ con el archivo) | marca `#cba6f7` |

   Un valor viejo nunca se muestra como leído: si la lectura siguiente falla, el campo pasa a `[!]` y el valor anterior queda sólo en el tooltip ("último leído: −59.8 °C, hace 40 s").
2. **Un solo control por acción peligrosa.** "Espejo rápido", "Ir" (red y λ), "Escribir offset" y "Reconectar" existen **una vez** cada uno. Los atajos y los botones de otras pestañas **invocan el mismo control** (el mismo `QAction`, no una copia), así que su estado, habilitado o no, es único.
3. **Sin diálogos rutinarios.** Un diálogo modal sólo aparece para acciones raras e irreversibles o con costo: escribir un offset, reconectar la cámara, cerrar el programa, y la advertencia del espejo en Step & Glue. El orden cero, que es frecuente, no tiene diálogo (R4-A 3).
4. **Estado de seguridad siempre a la vista.** La condición especular, la E-STOP, la sesión de hardware y el latido del watchdog se ven en la barra superior desde cualquier pestaña.
5. **Lo provisorio se ve como provisorio.** Los criterios K1-K7 y los topes que esperan una prueba de banco llevan el rótulo `PROVISORIO` y el ítem de banco que los fija. Ninguna calibración de esta fase se pinta de verde por su validez metrológica: el verde queda para "la escritura se releyó igual" (un hecho de hardware), no para "la calibración es buena" (§4.4).
6. **Paleta:** base `#181825`, superficie `#1e1e2e`, overlay `#313244`, lavanda `#cba6f7`, zafiro `#74c7ec`, azul `#89b4fa` (el que ya usan los paneles), verde `#a6e3a1`, amarillo `#f9e2af`, durazno `#fab387`, rojo `#f38ba8`. **Durazno = condición especular** (un modo de operación, no una falla); **rojo = falla o E-STOP**; **amarillo = con reserva o advertencia**.

### 1.2 Barra superior y franja de avisos

```
┌─ Barra de seguridad (existente, se amplía) ───────────────────────────────────────────────────────────┐
│ [PARADA DE EMERGENCIA (E-STOP)] [Rearmar] │ Sesión: libre │ ESPECULAR · EM 0 bloqueada · exp ≤ 10 ms │
│ Latido: Step & Glue │ Platina: (50.0, 50.0, 10.0) µm      [Obturadores] [Tablero Hardware] [Ayuda]  │
├─ Franja de avisos persistentes (nueva; una fila por aviso; se apila; no modal) ───────────────────────┤
│ [!] Offsets del equipo distintos del archivo: red 1 (150 l/mm) 87, archivo 85.                         │
│     Corrección fina de la red 1 suspendida.                                                            │
│     [Ver diferencias] [Registrar lo leído en el archivo] [Ir a Calibraciones] [Recordar al próximo inicio]│
│ [X] Cámara Andor no conectada: no respondió (código 20992). ¿Solis o el PySpectrum legado abiertos?   │
│     [Reintentar] [Ayuda]                                                                               │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

- **Insignia ESPECULAR** (durazno `#fab387`, texto `#181825`): aparece con `SpectrometerSnapshot.spectrograph.specular` verdadero, incluido el caso "estado desconocido cuenta como especular" (R2-inst §2.1-4), que se rotula "ESPECULAR (estado del Shamrock desconocido)". Clic → foco al control "Espejo rápido" del panel izquierdo.
- **Insignia de latido** (nueva): dice qué rutina renueva el latido del watchdog, si alguna lo hace ("Latido: Calibración λ", "Latido: Step & Glue"). Existe porque el latido es global al proceso (R2-inst §7.3): mientras una rutina lo renueva, el watchdog no cierra un obturador olvidado en el satélite PyPrinting. Sin rutina no se muestra.
- **Franja de avisos:** `QFrame` bajo la barra, una fila por aviso activo. Cada fila tiene gravedad (rojo o amarillo), texto, acciones y una cruz que la **oculta hasta que el hecho cambie**; no la borra: si el hecho persiste en la próxima lectura o el próximo arranque, vuelve. Reemplaza a los `statusBar().showMessage(..., 4000)` de hoy, que desaparecen a los 4 s.

### 1.3 Panel izquierdo: estado del espectrómetro

Reemplaza a `LeftHardwarePanel` (paso 8). Ancho mínimo 300 px. Tres grupos plegables, en el orden de uso en el banco.

```
┌─ Espectrógrafo Shamrock 500i ── [L] conectado · serie SR5-xxxx ──────────────── [Ayuda] ┐
│ ┌─ ESPEJO RÁPIDO ──────────────────────────────────────────────────────────────────────┐ │
│ │ [ Orden cero (red actual) ▾ ]   Ctrl+0     Estado: PRIMER ORDEN [D]                  │ │
│ │ Volver a: 150 l/mm · 650.00 nm  [ Volver ]   (sólo en especular)                     │ │
│ └──────────────────────────────────────────────────────────────────────────────────────┘ │
│ Red            [L] 1 · 150 l/mm · blaze 800 nm           [ 150 l/mm ▾ ]                   │
│ λc (SDK)       [L] 650.00 nm                             [ 650.00 nm ] [ Ir ]             │
│                destino: primer orden (umbral 56.7 nm) [D]                                 │
│ Ranura entrada [L] 100.0 µm                              [ 100.0 µm ]  [ Fijar ]          │
│ Puertos        [L] entrada Side · salida Direct          [ Fijar Side/Direct ]            │
│ Offsets        [L] red 1: 85 · red 2: 0 · detector: 0    archivo: = [D]                   │
│ Corrección fina  red 1: +0.31 px (sólo PySpectrum) · CON RESERVA · 2026-10-02             │
│ Geometría      [L] 1004 px × 8.0 µm                                                       │
├─ Cámara Andor iXon3 885 ── [L] conectada · DU8285_VP ─────────────────────────── [Ayuda] ┤
│ Temperatura    [L] −59.8 °C · estabilizada                setpoint [E] −60 °C [ −60 °C ]  │
│ Enfriador      [L] encendido                              [ Apagar enfriador ]            │
│ Ventilador     [E] low                                    (•) low  ( ) high               │
│ Ganancia EM    [L] 0 DAC  (modo [E] DAC 0-255)            [ 0 ] [ Aplicar ]               │
│ Exposición     [L] 0.0500 s (real)                        [ 0.0500 s ] [ Aplicar ]        │
│ Lectura        [E] Image · [E] Single Scan                                                │
│ Velocidades    [L] VS 1.9 µs · [L] HS 13 MHz · [L] pre-amp índice 0   [ 13 MHz ▾ ]        │
├─ Espejo de detección ── (sin sensor de posición) ─────────────────────────────── [Ayuda] ┤
│ Posición       ABAJO (espectrómetro), según el software, desde 14:02 · fuente: comandado  │
│                                                           [ Bajar ] [ Subir ]             │
└───────────────────────────────────────────────────────────────────────────────────────────┘
```

- **Columna izquierda = lo leído; columna derecha = lo que el operador pide.** Nunca comparten widget. El spinbox de la ganancia no "es" la ganancia: es el pedido. Lo que la cámara tiene está en la etiqueta `[L]`. Esto elimina G-01, G-02 y la duda de "¿este número es lo que puse o lo que hay?".
- **"Ir", "Fijar" y "Aplicar"** envían el pedido al `SpectrographWorker` (red, λ, ranura, puertos) o al servicio de la cámara. Mientras corre, el botón dice "Moviendo…" y se deshabilita; la etiqueta leída cambia sólo con la relectura.
- **"destino: …"** es una línea derivada que se recalcula mientras se escribe la λ o se elige la red: "primer orden (umbral 56.7 nm)" o, en durazno, "ESPECULAR: se entra por el espejo rápido". En ese caso "Ir" cambia a "Ir (espejo rápido)" y llama al mismo servicio que el botón de orden cero (§3.3). No hay un segundo camino.
- **Offsets:** sólo lectura. El `=` o `≠` contra el archivo es el `CalibrationDiff`. Clic en la fila → sub-pestaña "Offsets e historial" (§1.8).
- **Corrección fina:** `c_sw` en píxeles, su veredicto y su fecha, o "suspendida" con el motivo (§4.6). Nunca un número sin veredicto.
- **Equipo no conectado:** todo el grupo en gris, con una banda roja arriba ("no conectado: <motivo>") y [Reintentar] (`DeviceRegistry.reconnect`, §1.12). Ningún campo muestra un valor por defecto.
- **Durante una rutina** (sesión tomada): la columna derecha se deshabilita con el tooltip "Controlado por <rutina> (sesión de hardware)". La columna leída sigue viva con lo que publica la rutina (`publish_reading`) y la marca `[L] publicado por Step & Glue`. Esto reemplaza al `set_context(tab_index)` de hoy (`left_hardware_panel.py:246-253`), que deshabilitaba λ según la **pestaña** y no según quién tiene el hardware.
- **Espejo de detección:** la posición es una **creencia** (`MirrorBelief`, R2-arq §2.10). El rótulo dice siempre "según el software" y la fuente (persistido, comandado, resincronizado, ninguna). Con `unknown`: "DESCONOCIDA: el software no sabe dónde está", en amarillo. "Bajar" y "Subir" son el mismo `QAction` que el diálogo de obturadores.

### 1.4 Espejo rápido (orden cero y red espejo)

Un único control con dos estados. Reemplaza al `ZeroOrderSafetyDialog`, al botón del dock de Calibraciones y al combo "Espejo" como caminos separados (paso 7).

**Estado PRIMER ORDEN.** Botón principal "Orden cero (red actual)", con menú desplegable:
- "Orden cero (red actual)" → `enter_specular("zero_order")`. Es el "espejo rápido" del investigador (R4-A 3): no cambia de red, así que es lo más rápido.
- "Red espejo (posición 3 de la torreta)" → `enter_specular("mirror")`.
- La última elegida queda como acción principal (preferencia por usuario en `QSettings`).

Antes de moverse, el control **recuerda** la red y la λ de primer orden **leídas**, que aparecen en "Volver a: …".

**Durante la entrada** ("Moviendo a orden cero…"), una lista de pasos se completa dentro del propio control, sin ventana aparte:

```
 ✓ Live pausado                   ✓ Cámara detenida (IDLE leído)
 ✓ Ganancia EM 0 (releída)        ✓ Exposición acotada (real 0.0100 s)
 ✓ Obturadores cerrados (confirmado)   … girando la torreta
```

Se muestra porque cada paso puede fallar y el operador tiene que ver cuál. Si todo sale bien, la lista se pliega sola a los 2 s.

**Si un paso falla**, la red no se mueve y la lista queda abierta, con el paso en rojo y el texto de `MotionResult.detail` ("Ganancia leída 12, no 0: no se movió la red"). Acciones: [Reintentar] y [Ayuda]. No hay "Continuar de todos modos": el Override Experto desaparece (R4-A 3).

**Estado ESPECULAR.**
- Insignia durazno en la barra superior y en el control.
- El spinbox de la ganancia EM se deshabilita con el rótulo "bloqueada en 0: condición especular".
- El spinbox de exposición se acota a `SPECULAR_MAX_EXPOSURE_S`, rotulado "tope en especular: 10 ms (PROVISORIO, BANCO-43)".
- El botón pasa a "Volver a 150 l/mm · 650.00 nm", con una flecha para editar el destino antes de volver.
- **Obturadores:** al entrar se cerraron todos (R4-B 3). El operador los abre a voluntad desde [Obturadores]. El control muestra "Obturadores abiertos en especular: 532" (`get_open_shutter_names`), para que la luz que llega al detector tenga nombre. La política con el filtro de densidad en potencia alta es la pregunta Q2 (§7).
- **Saturación:** en especular, el visor muestra pico − bias del cuadro como fracción del ADC de 14 bit ("pico: 38 % del ADC"). Por encima del 50 % (R2-inst §2.2, Z10) el indicador se pone rojo: "saturación en orden cero: reducir luz o ranura". No mueve la red ni detiene el Live; sólo informa (el Z10 de la Ronda 2 aborta: ver D-06 en §6.2).

**Volver.** `Ctrl+0` o el botón llaman a `leave_specular(red, λ)`. Si sale bien:
- la insignia desaparece;
- la ganancia **no** vuelve sola (R4-B 4). Junto al spinbox aparece una pastilla "antes del orden cero: 150 DAC · [Restituir 150]". Es un clic explícito del operador, no una restitución automática; desaparece cuando el operador toca la ganancia, o a los 5 min;
- la exposición queda en el valor acotado hasta que el operador la cambie (tampoco vuelve sola), con la misma pastilla de restitución.

**Atajo.** `Ctrl+0` alterna: entra desde primer orden y vuelve desde especular. Hay que actualizar la fila "Diálogo de orden cero" de `lab-invariants` §4 a "Espejo rápido: entrar / volver".

### 1.5 Live en cualquier configuración

R4-B 4: el Live tiene que poder verse en orden cero, en espejo y con cualquier red.
- El Live de Exploración y el de Static Raman **nunca** se deshabilitan por la configuración del espectrógrafo. Sólo por cámara no conectada, E-STOP o una rutina con la sesión.
- **Tras el espejo rápido** el Live se reanuda solo si estaba corriendo (R4-B 4). Si no, el control del espejo rápido ofrece [Iniciar Live] en su propia línea: quien entra al orden cero casi siempre quiere ver la imagen.
- La barra del visor dice siempre en qué configuración está la imagen: "orden cero · red 1 · exp 10 ms · EM 0" o "150 l/mm · 650.00 nm · exp 50 ms · EM 0". Una captura del Live queda autodescriptiva.
- **Eje X del visor:** en primer orden, eje λ arriba (del `GetCalibration` leído) y píxel abajo; en especular, sólo píxel, con el rótulo "sin dispersión (especular)". Nunca un eje λ en orden cero.
- `Ctrl+Space` (alternar Live) funciona igual en especular.

### 1.6 Pestaña 5, "Calibraciones"

Tres sub-pestañas. La primera es la del bloque A; las otras conservan lo que ya existe, sin escrituras directas.

```
┌─ 5. Calibraciones ─────────────────────────────────────────────────────────────────────────────── [Ayuda] ┐
│ [ Calibración de λ (automática) ] [ Offsets e historial ] [ Ranura, cúbica, lámpara, agua, oscuro ]       │
├───────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ ┌─ Preparación ─────────────────────────┐ ┌─ Perfil de la línea (red 2 · 1200 l/mm · llegada 7) ───────┐ │
│ │ Redes  [x] 1 · 150 l/mm               │ │ cuentas                              λ (SDK) →             │ │
│ │        [x] 2 · 1200 l/mm              │ │  ▲         ╭╮     datos (zafiro)                            │ │
│ │ Fuente (•) fuga del 532 por el notch  │ │  │        ╭╯╰╮    ajuste gauss + fondo lineal (lavanda)     │ │
│ │        ( ) 532 atenuado, sin notch    │ │  │ ─ ─ ─ ─┼──┼─ ─ fondo lineal                           │ │
│ │ λ ref. [ 532.000 ] nm (en aire)       │ │  │ ░░░░░░░│░░│░░░ ventana ±3 FWHM                         │ │
│ │ origen [ nominal, sin medir ▾]        │ │  │        x̂   p_SDK(λref)                                 │ │
│ │ u(λref)[ — ] nm (sin dato)            │ │  │        │←r→│  r = +2.41 px = +0.028 nm                  │ │
│ │ Confirmo:                             │ │  └──────────────────────────────▶ píxel                    │ │
│ │ [ ] notch puesto                      │ │ residuo (datos − ajuste) con banda ±1σ                     │ │
│ │ [ ] espejo de detección abajo         │ ├─ Llegadas (residuo por llegada, px) ────────────────────────┤ │
│ │ Automático (preflight):               │ │  ● ●  ●  ● ●  ●  ●     media +2.38 · u_A 0.29 · M = 7      │ │
│ │  filtro de densidad en baja  ✓        │ │  ── banda K1 ±0.43 px (PROVISORIO) ──                      │ │
│ │  ganancia EM 0 (releída)     ✓        │ ├─ Resultado por red ─────────────────────────────────────────┤ │
│ │  CCD −60 °C estabilizada     ✓        │ │ Red   Offset  r_hw (px)     c_sw (px)  K1…K7    Veredicto   │ │
│ │ Modo: SÓLO MEDIR                      │ │ 150   85      +0.12 ± 0.29  −0.12      ✓✓✓✓✓✓✓ CON RESERVA │ │
│ │  (la escritura se habilita tras       │ │ 1200  0       +2.38 ± 0.29  —          ✓✓✓·✓✓✓ EN SECO     │ │
│ │   BANCO-40)                           │ │ [Aplicar corrección fina] [Proponer offset…] [Verificar]    │ │
│ │ [Avanzado ▸]                          │ │ Proponer offset: deshabilitado, falta px/paso (BANCO-40)    │ │
│ │ [ Iniciar calibración ] [ Cancelar ]  │ └─────────────────────────────────────────────────────────────┘ │
│ │ Red 2 · λc 532.00 · llegada 7 de ≤ 25 │                                                                 │
│ │ ▓▓▓▓▓▓▓▓▓▓░░░░ ~2 min restantes       │                                                                 │
│ └───────────────────────────────────────┘                                                                 │
└───────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

**Preparación (columna izquierda, 320 px).**
- **Redes:** dos casillas, 150 y 1200. La red 3 (espejo) no figura (G-12). El orden de medición es siempre 150 → 1200 (R2-inst §4.3).
- **Fuente:** la fuga del 532 por el notch (la práctica en Solis, R4-A 1) o el 532 atenuado sin notch (R4-B 11). La elección va a `filters` del registro (R2-met §4.1) y cambia el texto de la casilla de confirmación ("notch puesto" o "notch retirado, 532 atenuado").
- **λ de referencia:** spinbox en nm, 3 decimales, con el medio **aire** fijo en el rótulo (R2-met §5.1: `lambda_ref_medium = "air"`). Al lado, el origen del valor ("nominal, sin medir", "etiqueta del láser", "medida con…", texto libre) y la u opcional, que por defecto es "— (sin dato)". Con "nominal, sin medir", el resultado lleva siempre la nota "exactitud absoluta = la de λ_ref, que no tiene valor" (R2-met §3.4).
- **Confirmaciones del operador:** el notch y el espejo de detección. El software no puede leer el notch (R2-arq §2.7) y el espejo es una creencia (R2-arq §2.10). Las casillas **se destildan al terminar** cada corrida: no se recuerdan. La del espejo arranca tildada sólo si la creencia es `down`, con el rótulo "según el software".
- **Automático:** tres líneas de sólo lectura que la rutina fija y relee en su preflight (R2-inst §4.1, K2-K4). Un `✓` por relectura correcta; un paso fallido aparece en rojo después de "Iniciar", y la rutina no arranca.
- **Modo:** "SÓLO MEDIR", fijo mientras no exista px/paso medido (R4-B 1; paso 14; BANCO-40). No hay casilla en la GUI para cambiarlo.

**Perfil de la línea (arriba a la derecha).** Vista principal durante la corrida; ver §3.1.

**Llegadas (centro a la derecha).** Un punto por llegada, en píxeles. Muestra cómo crece M (secuencial de 9 a 25, R2-met §3.2), la media, u_A y la banda de K1 **rotulada PROVISORIO**. Es donde se ve que manda la repetibilidad de la torreta y no el estimador.

**Resultado por red (abajo a la derecha).** Una fila por red de la corrida, con los siete criterios K como iconos; el tooltip de cada uno da la regla y el valor medido (T-CAL-8). Veredictos y colores en §4.4.
- **[Aplicar corrección fina]** agrega una entrada al archivo con el `c_sw` de esa red. **No escribe al equipo**: la corrección fina es sólo de PySpectrum (R4-B 2). Se habilita con ACEPTADA o CON RESERVA; nunca con RECHAZADA ni EN SECO sin verificación.
- **[Proponer offset…]** abre el diálogo de escritura (§1.7). Deshabilitado mientras no haya px/paso, con el motivo escrito bajo el botón.
- **[Verificar]** corre la misma rutina en modo sólo-medir con el estado actual del equipo (R2-arq §2.7, "Cierre del lazo").

La tercera sub-pestaña conserva ranura, coeficientes cúbicos (sólo lectura), lámpara, agua y oscuro. Pierde el "Mover a Orden Cero" propio (lo reemplaza el mismo `QAction` del espejo rápido), el "Escribir SDK" del cero de ranura (G-10) y el estado "Modelo Planck Activo" (G-14), que pasa a "sin perfil de lámpara cargado".

### 1.7 Diálogo de escritura de offsets (transacción)

Diálogo modal, mínimo 560 × 420 px. Conduce la máquina de estados de `OffsetWriteTransaction` (R2-arq §2.6) y **no decide nada por sí mismo**: cada botón es una transición y el diálogo sólo refleja el estado que devuelve la transacción. Cinco páginas (`QStackedWidget`) con una barra de pasos arriba.

```
┌─ Escribir offset en el Shamrock (serie SR5-xxxx) ─────────────────────────────────────────────┐
│  1 Leer ✓   2 Diferencias ●   3 Respaldo   4 Escribir   5 Releer                              │
│                                                                                               │
│  Red 2 · 1200 l/mm · entrada Side · salida Direct                                             │
│                     Leído ahora            Propuesto     Cambio                               │
│  Offset de red      0 pasos [L 14:31:05]   −3 pasos      −3 pasos (≈ −0.05 nm; S 1.4 px/paso) │
│  Offset detector    0 (no se toca)                                                            │
│                                                                                               │
│  Origen: calibración automática 2026-10-02 14:20, r = +2.38 ± 0.29 px, CON RESERVA            │
│  Efecto: Solis y el PySpectrum legado también verán este valor. Escribir puede girar la       │
│  torreta: antes se cierran los obturadores y se confirma la ganancia EM en 0.                 │
│                                                                                               │
│                                [ Cancelar ]   [ Confirmo estas diferencias → ]                │
└───────────────────────────────────────────────────────────────────────────────────────────────┘
```

- **Página 1, Leer:** automática al abrir (`prepare`). Si falla una lectura: "No se pudo leer el offset de la red 2 (código …). No se escribe nada", y sólo [Cerrar].
- **Página 2, Diferencias. Primera confirmación** (`confirm_diff`). Lo leído **con la hora**, el valor propuesto, el cambio en pasos y el cambio estimado en nm con la S usada (R4-B 10). Si el número de serie no es el del archivo, no se puede seguir ("otro espectrógrafo", R2-inst §3.3, O2).
- **Página 3, Respaldo.** Automática después de la primera confirmación: registra `PRE_WRITE` y lo muestra ("Respaldo guardado: 0 pasos, 14:31:09, entrada n.º 212 del archivo"). Si el registro falla, termina ahí sin escribir (`BACKUP_FAILED`).
- **Página 4, Escribir. Segunda confirmación** (`confirm_write`). "Escribir en el equipo" está deshabilitado hasta que el operador **escribe el número de líneas de la red** ("1200") en un campo (R2-inst §3.3, O4). Es deliberadamente distinto de un segundo clic, que se da por reflejo.
  - **Tercera confirmación** si |cambio| > 50 pasos (R4-B 10): además, una casilla "Entiendo que el cambio es de 312 pasos (≈ 4.9 nm con la red de 150): la línea se corre ≈ 48 px" (ejemplo con una S hipotética de 0.15 px/paso). Cambio en nm y en píxeles con S y D: Δλ ≈ ΔO · S · D. Sin S no hay estimación, pero en esa fase "Proponer offset" ya está deshabilitado (§1.6).
  - El token vence a los 60 s (R2-inst §3.3, O4). Una cuenta regresiva dice "esta confirmación vence en 42 s"; al vencer, el diálogo vuelve a la página 1 y relee.
- **Página 5, Releer.** Resultado con los colores de §4.4: CONFIRMADO (verde), NO COINCIDE o DESCONOCIDO (rojo), ESCRITURA FALLIDA (rojo). En los rojos ofrece [Restaurar el valor anterior (0)…], que abre **esta misma transacción** con el valor del respaldo como propuesta.
- **Token obsoleto** (`STALE_TOKEN`): "El equipo cambió entre la lectura y la escritura: la red 2 tenía 0 y ahora tiene 4. No se escribió nada. [Volver a leer]".
- **Cancelar** antes de la página 4 no escribe nada. Si ya hubo respaldo, la entrada `PRE_WRITE` queda en el archivo (append-only) y el historial la muestra como "respaldo sin escritura (cancelado)".

### 1.8 Sub-pestaña "Offsets e historial"

```
┌─ Offsets e historial ───────────────────────────────────────────────────────────── [Ayuda] ┐
│ Estado de referencia por red (lo que PySpectrum espera encontrar en el equipo)             │
│  Red        Equipo [L]   Referencia          Origen de la referencia          Δ            │
│  1 · 150    85           85                  MANUAL_ENTRY (Solis, 2026-08-28) =            │
│  2 · 1200   0            —                   sin referencia                   —            │
│  Detector   0            0 (por convención)  R4-A 2                           =            │
│  [ Releer el equipo ]  [ Registrar un valor leído en Solis… ]                              │
│                                                                                            │
│ Historial (archivo local, sólo se agregan entradas)   Tipo [Todas ▾]  Red [Todas ▾]        │
│  Fecha             Tipo        Red    Valor     Resultado / veredicto   Operador            │
│  2026-10-02 14:31  APPLIED     1200   −3        CONFIRMADO              jgonzalez           │
│  2026-10-02 14:31  PRE_WRITE   1200   0         respaldo                jgonzalez           │
│  2026-10-02 14:20  PROPOSED    1200   −3        CON RESERVA             jgonzalez           │
│  2026-10-02 09:12  OBSERVED    todas  85/0/0    arranque                jgonzalez           │
│  … (≥ 10 filas visibles; alto mínimo 300 px)                                                │
│ Detalle de la fila: todos los campos del registro y el presupuesto, con los términos null. │
└────────────────────────────────────────────────────────────────────────────────────────────┘
```

- **Sin escritura directa.** "Escribir Rejilla", "Escribir Detector" y "Escribir SDK" desaparecen (G-10). El detector y el cero de ranura se muestran leídos.
- **[Registrar un valor leído en Solis…]:** agrega una entrada `MANUAL_ENTRY` con `provenance: EXPERIMENTAL` (R2-arq §2.5). **No toca el equipo.** Así queda constancia del 85 de la red de 150 (R4-3).
- **Menú contextual del historial:** "Ver detalle", "Copiar como JSON", "Abrir datos crudos (HDF5)" y, sólo en `PRE_WRITE` y `APPLIED`, "Restaurar este valor en el equipo…", que abre la transacción de §1.7 con ese valor. Si esto se permite fuera de la rutina es la pregunta Q4 (§7).
- **Tabla append-only:** cada entrada nueva se inserta arriba sin reconstruir la tabla (§4.1). Nunca `setRowCount(0)`.
- Las flechas (`currentCellChanged`) actualizan el detalle igual que el clic.

### 1.9 Step & Glue

```
┌─ 3. Step & Glue ───────────────────────────────────────────────────────────────────────────── [Ayuda] ┐
│ ┌─ Barrido ───────────────────────────┐ ┌─ Plan y espectro ─────────────────────────────────────────┐ │
│ │ Red        [L] 150 l/mm (actual)    │ │  │█ v1 █│▒│█ v2 █│▒│█ v3 █│▒│█ v4 █│▒│█ v5 █│              │ │
│ │ Desde      [ 500.0 ] nm  (arrastrable│ │ 500          ▒ = solapamiento (20 %)           900 nm     │ │
│ │ Hasta      [ 900.0 ] nm   en el plot)│ │ ░░ fuera de los límites de la red ░░   ▓▓ especular ▓▓    │ │
│ │ Solape     [ 20 ] %                 │ │ crudo por ventana (colores alternados) · cosido (lavanda) │ │
│ │ Exposición [ 1.000 ] s  (≤ 10 s)    │ │                                                           │ │
│ │ Luz        (•) lámpara  ( ) láser   │ │                                                           │ │
│ │ Plan: 5 ventanas · paso ≈ 82 nm     │ ├─ Ventanas ────────────────────────────────────────────────┤ │
│ │       ≈ 0.5 min (1 s por ventana)   │ │ #  λc pedida  λc leída  exp real  estado       archivo    │ │
│ │       ventana medida 103.0 nm [L]   │ │ 1  541.2      541.20    1.000 s   ✓ en disco   sg_…_01    │ │
│ │ Espejo: ABAJO (según el software)   │ │ 2  623.6      623.60    1.000 s   ✓ en disco   sg_…_02    │ │
│ │ [ ] Normalizar con lámpara [archivo…]│ │ 3  706.0      —         —         adquiriendo            │ │
│ │ [ ] Verificar banda del agua        │ │ 4  788.4      —         —         pendiente              │ │
│ │ [Avanzado ▸]                        │ │ 5  870.8      —         —         pendiente              │ │
│ │ [ Iniciar ]   [ Stop ]              │ │ (alto mínimo 260 px)                                      │ │
│ │ Ventana 3 de 5 · exposición 0.4/1 s │ └───────────────────────────────────────────────────────────┘ │
│ │ ▓▓▓▓▓▓▓▓▓░░░░░ ~20 s restantes      │                                                               │
│ └─────────────────────────────────────┘                                                               │
└───────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

(Los centros del mockup son ilustrativos; los calcula `compute_step_centers`.)

- **Plan antes de arrancar (G-21):** ventanas, paso, duración estimada y ventana usada (medida `[L]` o nominal: `plan.window_source`, DEC-033) se recalculan con cada cambio, con `StepGlueEngine.plan(request, snapshot)`, que es puro y rápido. El plan se dibuja en el gráfico (§3.4).
- **Red:** la leída del snapshot. Se cambia en el panel izquierdo (un solo control, §1.1-2). `StepGlueRequest` no tiene red (D-09, §6.2).
- **Luz:** lámpara o láser. Cambia el latido y el texto del preflight (R4-B 5; pregunta Q3).
- **Espejo de detección:** línea de sólo lectura con la creencia; amarilla si no es "abajo" (§1.9.1).
- **Normalizar con lámpara:** destildado por defecto (G-18). Tildado sin archivo, "Iniciar" se deshabilita con el motivo: "falta el archivo de lámpara; no se normaliza con un perfil sintético" (bloqueante del motor, R2-arq §2.9).
- **Tabla de ventanas:** una fila por ventana planificada, alto mínimo 260 px. La fila en curso en azul; las adquiridas con "en disco" y el archivo, porque cada ventana se escribe al terminar (R2-arq §2.9). Clic o flechas en una fila resaltan esa ventana en el gráfico.

#### 1.9.1 Preflight de Step & Glue

Al pulsar **Iniciar**, `StepGlueEngine.preflight` devuelve bloqueantes y advertencias (R2-arq §2.9).
- **Con bloqueantes:** no se abre ningún diálogo. La lista aparece en rojo sobre el botón y "Iniciar" queda deshabilitado hasta que algo cambie ("ventana 1 en condición especular: λc 45 nm < 56.7 nm"; "falta el archivo de lámpara"; "cámara no conectada").
- **Advertencia sobre el espejo:** es la única que abre un diálogo, porque equivocarse cuesta minutos de barrido sin luz.

```
┌─ Step & Glue: espejo de detección ───────────────────────────────────────────────┐
│ El software cree que el espejo de detección está ARRIBA (comandado a las 13:40). │
│ El espejo no tiene sensor: esto es lo último que ordenó el software.             │
│ Con el espejo arriba, la luz no llega al espectrómetro.                          │
│                                                                                  │
│ [ Bajar el espejo y seguir ]  [ Ya está abajo: confirmo y sigo ]  [ Cancelar ]   │
└──────────────────────────────────────────────────────────────────────────────────┘
```

  Son las tres opciones de R2-inst §5.1 (G4). "Ya está abajo" registra la confirmación del operador como resincronización de la creencia (D-10, §6.2). Con `unknown`, el texto dice "El software no sabe dónde está el espejo".
- **Las demás advertencias** ("offsets del equipo distintos del archivo", "calibración con procedencia EXPERIMENTAL") se listan en amarillo sobre el botón, sin diálogo, y el barrido arranca.
- **Primera ventana sin luz** (R2-inst §5.1, G8): el worker pausa y la GUI muestra, en la tabla y sobre el botón, "Ventana 1: sin señal por encima del fondo. ¿Espejo arriba o lámpara apagada?", con [Seguir] y [Stop]. La ventana no se descarta.

#### 1.9.2 Durante el barrido

- **Stop** (rojo `#f38ba8`) está habilitado mientras corre y responde en ≤ 250 ms más `AbortAcquisition` (R2-inst §5.2). Al pulsarlo pasa a "Deteniendo…" hasta la señal `finished`.
- Los parámetros quedan visibles y deshabilitados; no se resetea nada.
- La barra de progreso tiene dos niveles: la ventana ("3 de 5") y la exposición en curso ("0.4 / 1 s"). Con exposiciones de 10 s, una barra que sólo avanza por ventana parece colgada.
- La E-STOP de la barra superior sigue siendo la parada global.

### 1.10 Escaneo lineal

El escaneo lineal pasa a usar `StepGlueEngine.run_windows` (paso 12). En la GUI, el bloque "Barrido" de §1.9 (red leída, desde, hasta, solape y el gráfico del plan) se extrae como un widget reutilizable, `SpectralRangePlanWidget`, que el escaneo lineal embebe en su modo "Step & Glue" (SYS-301 §7.4 describe hoy un modo dual propio). Así los dos planifican y se ven igual. El cosido que queda lo decide `metrology` (R2-arq §7.4); la GUI muestra cuál se usó ("cosido: sigmoidal") en el metadato y en la leyenda.

### 1.11 Aviso "el equipo difiere del archivo" al arrancar

- **Forma:** fila amarilla persistente en la franja de avisos (§1.2), **no modal**. El arranque no se detiene y nada se escribe (R4-B 1).
- **Texto:** "Offsets del equipo distintos del archivo de calibraciones: red 1 (150 l/mm): equipo 87, archivo 85. Corrección fina de la red 1 suspendida." La última frase aparece sólo si había corrección fina para esa red (§4.6).
- **Acciones:**
  - [Ver diferencias]: abre "Offsets e historial" con la fila resaltada;
  - [Registrar lo leído en el archivo]: agrega una entrada `MANUAL_ENTRY` con el valor del equipo y la nota "adoptado del equipo al arrancar". No toca el equipo;
  - [Ir a Calibraciones]: para correr la rutina;
  - [Recordar al próximo inicio]: oculta la fila hasta el próximo arranque.
- **Offset no leído** (lectura fallida): en rojo, "Offset de la red 2 desconocido (falló la lectura, código …): no se puede comparar con el archivo". La corrección fina de esa red se suspende.
- **Sin archivo** (primer uso): fila informativa azul, "No había archivo de calibraciones: se creó uno con lo leído del equipo (entrada OBSERVED)". Se cierra con la cruz y no vuelve.

### 1.12 "Reconectar cámara" en el tablero de hardware

R4-B 7: se mantiene, con aviso. Es la única acción de esta ronda que apaga el enfriador, así que lleva un diálogo aunque sea poco frecuente.

```
┌─ Reconectar la cámara Andor ──────────────────────────────────────────────────┐
│ Reconectar cierra la cámara (ShutDown) y la vuelve a abrir.                   │
│ Al cerrarla, el enfriador deja de enfriar y el sensor se calienta hacia la    │
│ temperatura ambiente. Al reabrirla, el arranque lo vuelve a poner a −60 °C.   │
│                                                                               │
│ Temperatura ahora: −59.8 °C (estabilizada) [L]                                │
│ Volver a −60 °C puede tardar varios minutos (no medido en este equipo).       │
│                                                                               │
│                      [ Cancelar ]   [ Reconectar y volver a enfriar ]         │
└───────────────────────────────────────────────────────────────────────────────┘
```

- **Deshabilitado** con una sesión activa, con la E-STOP activa o con el Live corriendo; el motivo va en el tooltip (R2-arq §4.1).
- El tiempo de reenfriado no tiene valor en el repositorio: el texto dice "varios minutos (no medido)". Se sugiere anotarlo en la batería de banco (BANCO-45).
- **Shamrock:** el mismo botón no apaga nada, pero pierde lo leído. El diálogo dice "después de reconectar se vuelven a leer la red, la λ y los offsets; no se mueve nada".
- **"Re-scan"**, en un proceso con `DeviceRegistry`, refresca estados sin reiniciar (R2-arq §4.3). Se renombra "Refrescar estado" y pierde el tooltip "reconecta en caliente".
- **"Aislar (Mock)"** para Andor y Shamrock se deshabilita fuera de SAFE_MODE, con el tooltip "Sin simulador fuera del modo seguro: un equipo que no inicializa aparece como no conectado (DEC-036)".

### 1.13 Cierre de PySpectrum

El diálogo de cierre existente (`window.py:771-776`) pasa a decir qué va a pasar:

> **¿Cerrar PySpectrum?**
> Se cierran todos los obturadores, la platina va a (50, 50, 10) µm y la cámara se cierra: el enfriador deja de enfriar.
> [Cancelar] [Cerrar PySpectrum]

- La posición sale de `config.PI_HOME_POS` (R4-B 6), no de un literal en el texto.
- Con el satélite PyPrinting abierto, una línea más: "PyPrinting (abierto desde aquí) también se cierra, sin mover la platina". Es un solo diálogo: el segundo diálogo modal de hoy es parte del deadlock V3 (R2-arq §1).

## 2. Inventario de grados de libertad [PROPUESTA]

### 2.1 Reglas generales de los widgets

1. **Números con spinbox, nunca `QLineEdit`** (G-16). Unidad en el sufijo (`" nm"`, `" s"`, `" µm"`, `" °C"`, `" DAC"`, `" pasos"`, `" %"`). Límites leídos del equipo cuando el SDK los da (`GetEMGainRange`, `GetTemperatureRange`, `GetWavelengthLimits`); si no, de `config.py`, **nunca** literales en el widget.
2. **`editingFinished` o botón explícito, nunca `valueChanged`**, para todo lo que actúa sobre hardware. `valueChanged` sólo recalcula vistas (el plan de Step & Glue, la línea "destino").
3. **Combos de hardware sin rueda:** `setFocusPolicy(StrongFocus)` y un filtro de eventos que ignora `Wheel` sin foco (G-04).
4. **Tope visible:** si el valor pedido se recorta (tope del driver, tope en especular), el spinbox se pinta amarillo un segundo y el tooltip dice cuál tope actuó.
5. **Valor por defecto = el de la Ronda 2 o el del investigador**, con la fuente en el tooltip. Si no hay fuente, el campo no tiene default y el botón que lo necesita está deshabilitado (p. ej. el archivo de lámpara).

### 2.2 Panel de estado (pasos 7 y 8)

| Parámetro | Capa | Widget | Unidad · paso | Rango | Default | Fuente del default |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Red pedida | 2 | `QComboBox` (1, 2, 3) + **Ir** | — | redes de `GetNumberGratings`/`GetGratingInfo` | la leída | snapshot |
| λc pedida | 2 | `QDoubleSpinBox` + **Ir** | nm · 0.01 (1 con Shift, 10 con Ctrl) | `GetWavelengthLimits(red)` | la leída | snapshot |
| Ranura de entrada | 2 | `QDoubleSpinBox` + **Fijar**; atajos 10 / 50 / 100 / 500 µm (existentes) | µm · 1 | 10-2500 (`SHAMROCK_SLITWIDTHMIN/MAX`, R2-inst §5.5) | la leída | snapshot |
| Puertos | 2 | un botón "Fijar Side/Direct" | — | — | — | R2-inst §1.3, S11 |
| Espejo rápido: destino | 2 | botón con menú (orden cero / red espejo) | — | — | orden cero | R4-A 3 |
| Setpoint de temperatura | 2 | `QSpinBox` | °C · 1 | `GetTemperatureRange` | −60 | R4-A 6 |
| Enfriador | 2 | botón que **refleja** `IsCoolerOn` | — | — | encendido al arrancar | R4-A 6 |
| Ventilador | 2 | dos `QRadioButton` low / high (sin "off") | — | low = `FanMode.LOW` (1); high = `FanMode.FULL` (0) | low | R4-A 6; R2-inst §6.2 |
| Velocidad horizontal | 2 | `QComboBox` de la tabla `GetHSSpeed` | MHz | tabla del equipo | 13 MHz | R4-B 8 |
| Ganancia EM | 2 | `QSpinBox` + **Aplicar**; deshabilitado en especular | DAC · 1 | `GetEMGainRange` del modo 0 (0-255 esperado) | 0 | R4-A 6; R2-inst §6.4 |
| Exposición (Live) | 2 | `QDoubleSpinBox` + **Aplicar**, escala logarítmica en el paso | s · ×2 con flechas | 1e-4 a 60 s (tope del driver); en especular, hasta `SPECULAR_MAX_EXPOSURE_S` | 0.05 s | R4-B 9; R2-inst §1.2, C15 |
| Amplificador | 3 | `QComboBox`; oculto si `GetNumberAmp` = 1 | — | — | EMCCD (0) | R2-inst §6.5 |
| Pre-amp | 0 | sólo lectura | índice | — | 0 | R2-inst §1.2, C10 |
| VS speed | 0 | sólo lectura | µs | — | 1.9 µs (índice de tabla) | R4-A 6; R2-arq §6.2 |
| Modos de lectura y de adquisición | 0 | sólo lectura `[E]` | — | — | Image, Single Scan | R2-arq §6.2 |
| Espejo de detección | 2 | "Bajar" / "Subir" (el `QAction` existente) | — | — | — | C-08 |

**Vínculos:**
- En especular, ganancia = 0 fija y exposición ≤ tope (interlock en el driver, R2-arq §2.8). La GUI refleja el interlock; no lo implementa.
- La red elegida en el combo cambia en vivo el rango del spinbox de λ y el umbral de la línea "destino".
- La velocidad horizontal cambia la estimación de lectura del plan de Step & Glue (≈ 0.08 s a 13 MHz, R2-inst §7.1).

### 2.3 Calibración automática (paso 14)

Contrato: `OffsetCalibrationConfig` (R2-met §5.1) y `AutoCalibrationPlan` (R2-arq §2.7). Ver D-01 a D-04 en §6.2.

| Parámetro | Capa | Widget | Unidad · paso | Rango | Default | Fuente |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Redes | 2 | dos `QCheckBox` | — | {1, 2} | ambas | R4-B 1 |
| Fuente de referencia | 2 | dos `QRadioButton` | — | fuga por notch / atenuado sin notch | fuga por notch | R4-A 1, R4-B 11 |
| λ de referencia | 2 | `QDoubleSpinBox` | nm (aire) · 0.001 | 500-560 | 532.000 | R2-met §5.1 (`lambda_ref_nm`); valor nominal, SIN VALOR medido |
| Origen de λ_ref | 2 | `QComboBox` editable | — | texto | "nominal, sin medir" | R2-met §4.1 (`lambda_ref_source`) |
| u(λ_ref) | 2 | `QDoubleSpinBox` con estado vacío "—" | nm · 0.001 | 0-1 | vacío (null) | R2-met §4.1 |
| Notch puesto (o retirado) | 2 | `QCheckBox`, obligatorio | — | — | destildado | R2-arq §2.7 |
| Espejo abajo | 2 | `QCheckBox`, obligatorio | — | — | tildado sólo si la creencia es `down` | R2-met §2.3 |
| Recorrido de la línea (±0.35 W) | 3 | `QCheckBox` | — | — | tildado | R2-met §2.3; K4 |
| Cuadros por llegada | 3 | `QSpinBox` | · 1 | 3-10 | 5 | R2-met §5.1 |
| Cuadros de oscuro | 3 | `QSpinBox` | · 1 | 3-10 | 5 | R2-met §5.1 |
| Llegadas por iteración | 3 | `QSpinBox` | · 1 | 2-9 | 4 | R2-met §5.1 |
| Llegadas finales, mínimo / máximo | 3 | dos `QSpinBox` vinculados (mín ≤ máx) | · 1 | 3-50 | 9 / 25 | R2-met §3.2 |
| u objetivo | 3 | `QDoubleSpinBox` por red | px · 0.01 | 0.05-2 | 0.22 (150) / 0.43 (1200) | R2-met §4.2, K1 |
| Exposición | 3 | "automática" (casilla) o `QDoubleSpinBox` | s | 1e-3 a tope (ver D-02) | automática | R2-inst §4.5; R2-met §5.1 |
| Filas del ROI | 3 | dos `QSpinBox` vinculados al ROI del Live (§3.2) | fila | 0-1001 | traza ± 4 | R2-met §2.1 |
| Acercamiento desde abajo (δ) | 3 | `QDoubleSpinBox` por red | nm · 0.5 | 1-50 | 20 (150) / 3 (1200) | R2-met §2.2; BANCO-A3 |
| Aplicar corrección de software | 0 | no se expone | — | — | sí | R4-B 2 |
| `dry_run` | 0 | no se expone: "SÓLO MEDIR" fijo hasta BANCO-40 | — | — | `True` | R4-B 1 |
| Estimador, ventana ±3 FWHM, rechazo 5σ, SNR ≥ 20 | 0 | no se exponen; se muestran en el detalle del registro | — | — | R2-met §2.1 | R2-met §2.1 |
| px/paso previa (S) | 0 | sólo lectura, desde el archivo | px/paso | — | — | R2-met §1.4 |

**Por qué casi todo es Capa 3 o 0.** La rutina existe para reemplazar un ajuste manual iterativo; cada parámetro expuesto en la vista principal es una oportunidad de que dos corridas no sean comparables. En la vista principal quedan sólo lo que el software no puede saber (fuente, λ_ref con su origen, confirmaciones) y la elección de redes.

**Nombres que dicen la verdad:** "SÓLO MEDIR" y no "en seco" (jerga); "corrección fina (sólo PySpectrum)" y no "c_sw"; "residuo" con su definición en el tooltip.

### 2.4 Diálogo de escritura (paso 10)

| Parámetro | Capa | Widget | Unidad | Default | Fuente |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Offset propuesto | 0 | sólo lectura (viene de la propuesta o del respaldo) | pasos | — | R2-arq §2.6 |
| Confirmación 1 | — | botón "Confirmo estas diferencias" | — | — | R4-A 5 |
| Confirmación 2 | — | campo "escriba el número de líneas de la red" + botón | — | vacío | R2-inst §3.3, O4 |
| Confirmación 3 (\|Δ\| > 50) | — | casilla con el cambio en pasos, nm y px | — | destildada | R4-B 10 |
| Umbral de la tercera | 0 | `config` (50 pasos) | pasos | 50 | R4-B 10; se ajusta con BANCO-40 |
| Vencimiento del token | 0 | cuenta regresiva visible | s | 60 | R2-inst §3.3 |

No hay campo para teclear un offset arbitrario: R4-B 1 dice que el entero se escribe sólo desde la rutina.

### 2.5 Step & Glue (pasos 11 y 12)

Contrato: `StepGlueRequest` (R2-arq §2.9).

| Parámetro | Capa | Widget | Unidad · paso | Rango | Default | Fuente |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Desde / Hasta | 2 | dos `QDoubleSpinBox` + dos líneas arrastrables en el gráfico (§3.4) | nm · 1 | `GetWavelengthLimits(red)`; desde < hasta − 1 nm | 500 / 900 | R4-A 4 |
| Solape | 2 | `QSpinBox` | % · 5 | 10-50 | 20 | código actual; R2-arq §2.9 (`0 < overlap < 1`) |
| Exposición por ventana | 2 | `QDoubleSpinBox` | s · ×2 con flechas | 1e-4 a `MAX_ROUTINE_EXPOSURE_S` (10 s) | 1.0 | R4-4; R2-arq §2.9 |
| Luz | 2 | dos `QRadioButton` lámpara / láser | — | — | lámpara | R4-A 4; R4-B 5 |
| Normalizar con lámpara | 2 | `QCheckBox` + selector de archivo | — | — | destildado | G-18; R2-arq §2.9 |
| Verificar banda del agua | 2 | `QCheckBox` | — | — | destildado | código actual (`check_water`) |
| Ventana fija legada (103 / 12 nm) | 3 | `QCheckBox` | — | — | destildado | `use_optical_core`; DEC-033 |
| Fondo | 3 | `QComboBox` | — | "un cuadro para todas" (hoy); "por ventana" cuando `metrology` lo decida | un cuadro | R2-arq §2.9 (`BackgroundPolicy`) |
| Modo de lectura | 0 | sólo lectura, del snapshot | — | — | el vigente | R2-arq §2.9 (C-05) |
| Red | 0 | sólo lectura, del snapshot | — | — | la vigente | D-09 |
| Ganancia EM del barrido | 0 | sólo lectura: la del panel | DAC | — | la vigente | D-11 |

**Vínculos:**
- Desde, hasta, solape y exposición recalculan el plan (ventanas, paso, duración) en vivo, sin tocar hardware.
- La ventana usada viene medida del eje (`measured_window_nm`) o nominal; si la geometría no está verificada, el plan dice "ventana nominal (geometría no verificada)" en amarillo y el preflight lo bloquea (R2-arq §2.9).
- En el escaneo lineal, el mismo widget con los mismos vínculos (§1.10).

### 2.6 Escalera de personalización (skill `interactive-tool-design`)

| Capa | Qué ve el operador | Dónde |
| :--- | :--- | :--- |
| **0, automática** | índice de VS por tabla; ventana medida; clasificación especular y su umbral; reanudación del Live; diff al arrancar; estimador y criterios; `dry_run` | nada editable; se muestra en tooltips y en el detalle del registro |
| **1, visual** | marcas `[L]/[E]/[!]/[?]/[X]/[D]`, colores de veredicto, insignias, franja de avisos | siempre |
| **2, paramétrica** | los parámetros "Capa 2" de §2.2-2.5 | vista principal |
| **3, experta** | los "Capa 3" de §2.3 y §2.5 | desplegable **[Avanzado ▸]** cerrado por defecto; un cambio respecto del default se marca con un punto lavanda en el título del desplegable, para que un parámetro experto cambiado no quede oculto |

El desplegable recuerda su estado abierto o cerrado por usuario (`QSettings`), pero **los valores de Capa 3 vuelven al default en cada inicio**: un default viejo olvidado en una sesión anterior no debe contaminar la calibración de hoy. Cada registro guarda los valores usados.

## 3. Manipulación directa y micro-interacciones [PROPUESTA]

### 3.1 Calibración: la línea, su ajuste y el residuo

Gráfico principal de la calibración (`pg.PlotWidget` con dos `ViewBox` apilados, el de abajo vinculado en X):

| Elemento | Item de PyQtGraph | Estilo | Qué muestra |
| :--- | :--- | :--- | :--- |
| Perfil medido | `PlotDataItem` | zafiro `#74c7ec`, 1.5 px, pasos (`stepMode="center"`) | suma de filas del ROI, con el oscuro restado y el rechazo temporal aplicado (R2-met §2.1, pasos 1-4). En escalones, porque son píxeles, no una curva continua |
| Píxeles rechazados por rayo cósmico | `ScatterPlotItem` | cruces rojas `#f38ba8` | los valores descartados por el rechazo temporal, en el cuadro donde ocurrieron |
| Ajuste | `PlotDataItem` | lavanda `#cba6f7`, 2 px, rayas | gaussiana + fondo lineal, evaluada con resolución de 0.1 px |
| Fondo lineal | `PlotDataItem` | `#6c7086`, 1 px, puntos | el término lineal solo |
| Ventana de ajuste | `LinearRegionItem`, no movible | relleno `#cba6f7` al 10 % | ±3 FWHM, recentrada (R2-met §2.1, paso 6) |
| Centro ajustado x̂ | `InfiniteLine` vertical | lavanda, 2 px | con etiqueta "x̂ = 503.62 ± 0.09 px" |
| Donde el SDK pone λ_ref | `InfiniteLine` vertical | verde `#a6e3a1`, 2 px, rayas | p_SDK(λ_ref), con etiqueta "532.000 nm según el eje del SDK" |
| Residuo | `ArrowItem` doble + `TextItem` entre las dos líneas | amarillo `#f9e2af` | "r = +2.41 px = +0.028 nm" (r en px y r·D en nm, R2-met §1.2) |
| Tope de saturación | `InfiniteLine` horizontal | rojo, rayas | 0.8 × 16 383 cuentas del ADC (R2-met §2.1, paso 3); se ve sólo si el pico supera el 50 % |
| Eje superior | `AxisItem` con ticks en nm | — | λ del SDK en esa llegada; con la corrección fina aplicada (verificación), una segunda fila de ticks "corregido" |
| Residuo del ajuste (abajo) | `PlotDataItem` + `FillBetweenItem` | zafiro + banda ±1σ `#313244` | datos − ajuste en la ventana; estructura visible = asimetría o multimodo |

**Interacciones:**
- **Hover** sobre el perfil: píxel, cuentas, λ del SDK en ese píxel.
- **Clic en una llegada** del gráfico de llegadas (o flechas ↑/↓ con el foco en ese gráfico): el gráfico principal muestra el perfil y el ajuste de **esa** llegada. La llegada seleccionada se resalta; las demás quedan como puntos. Mientras corre la rutina, el gráfico sigue a la última llegada salvo que el operador haya seleccionado otra; un botón [Seguir la última] vuelve al seguimiento.
- **Búsqueda asistida por clic (click-to-seed), sólo Capa 3 o con la bandera `NO_LINE`:** si el estimador no encontró la línea, el gráfico muestra el perfil crudo y el texto "No se detectó la línea. Haga clic sobre ella para indicarle al ajuste dónde buscar". El clic fija `center_guess_px` y el `search_range_px` = clic ± 3·FWHM estimado, dibujado como una región arrastrable (`LinearRegionItem`, borde lavanda). **La corrida no se reanuda sola:** el botón [Reintentar esta llegada con la semilla] lo hace. La semilla queda en el registro (`window_px`, y una bandera `SEEDED_BY_OPERATOR`, D-05), porque un centro buscado a mano no es comparable con uno automático.
- **Menú contextual:** "Exportar esta llegada (CSV)", "Copiar números", "Mostrar todos los cuadros de la llegada", "Mostrar el centroide (diagnóstico de asimetría)". Este último agrega una tercera línea vertical punteada en x̂_centroide, para ver la bandera ASIMETRÍA (R2-met §2.1, paso 7).

### 3.2 Orden cero: la banda de la ranura y el punto del láser

En el visor 2D de Exploración, con la condición especular activa, se agregan tres elementos (y se ocultan al volver a primer orden):

| Elemento | Item | Estilo | Cómo se calcula |
| :--- | :--- | :--- | :--- |
| Banda de la ranura **medida** | `LinearRegionItem` vertical, no movible | relleno durazno `#fab387` al 15 %, bordes sólidos | bordes a media altura del perfil de columnas del cuadro, en las filas del ROI. Es la imagen de la ranura que ve el detector, no un cálculo |
| Banda de la ranura **esperada** | `LinearRegionItem` vertical, no movible | sin relleno, bordes punteados `#6c7086` | el overlay actual: ancho leído ÷ 8 µm, **rotulado "suponiendo imagen 1:1 (no verificado)"** (§0.5). Sirve para ver cuánto difiere de la medida |
| Punto del láser | `TargetItem` (cruz con círculo) | verde `#a6e3a1` | centroide del máximo local dentro de un `RectROI` arrastrable que el operador ubica sobre el punto. Etiqueta: "láser: x = 503.2 px · Δ = +1.9 px del centro de la ranura" |
| Centro de la ranura | `InfiniteLine` vertical | durazno, rayas | centro de la banda medida |

**Uso (R4-B 3: centrar el láser en la ranura).**
- El operador abre el 532 con el filtro de densidad (desde [Obturadores]) y ve la cruz. Mueve la óptica hasta que Δ ≈ 0; la etiqueta se actualiza con cada cuadro del Live.
- **Arrastrar el `RectROI`** cambia dónde se busca el punto; **doble clic** sobre el punto lo centra ahí.
- **Menú contextual del punto:** "Usar esta fila como traza (ROI de espectro)". Mueve el ROI horizontal existente (`exploration_tab.py:205-211`) para centrarlo en la fila del punto, con la misma altura que tenía. Es el vínculo directo entre alinear en orden cero y medir en primer orden.
- La banda medida no se dibuja si el perfil de columnas no tiene un escalón claro (contraste < 3·σ del fondo): se lee "imagen de la ranura no detectada", en vez de una banda inventada.

**Ninguno de estos elementos escribe al equipo ni a la calibración.** El "Pixel X central" de la tercera sub-pestaña (G-15) deja de tener un default escrito en el código: vale lo último medido aquí, con fecha, o "sin medir".

### 3.3 La línea "destino" y el campo λ

- Mientras el operador escribe en el spinbox de λ o cambia el combo de red, la línea derivada recalcula `SpectrographMotionEngine.classify(MotionTarget(...))` (pura, sin hardware) y muestra:
  - "primer orden · umbral de la red 1: 56.7 nm" en `#6c7086`, o
  - "ESPECULAR (λc < 56.7 nm): se entra por el espejo rápido" en durazno.
- Con destino especular, **Ir** cambia su texto a "Ir (espejo rápido)" y llama al mismo `ZeroOrderService.enter_specular` con esa red y esa λ. No hay confirmación extra: es la misma entrada protegida.
- El umbral mostrado es el que usa el motor (`window_nm(red)` medido o nominal); la GUI no tiene su propio número.

### 3.4 Step & Glue: el plan sobre el espectro

| Elemento | Item | Estilo | Interacción |
| :--- | :--- | :--- | :--- |
| Desde / Hasta | dos `InfiniteLine` verticales, **movibles** | lavanda, 2 px | arrastrar = editar el spinbox (bidireccional, §3.7) |
| Ventana i | `LinearRegionItem` no movible | contorno zafiro; relleno al 10 % pendiente, 30 % adquirida, azul pulsante la actual | clic = selecciona la fila en la tabla de ventanas |
| Solapamiento | `LinearRegionItem` no movible entre ventanas vecinas | trama amarilla `#f9e2af` al 20 % | tooltip con el ancho en nm y en % |
| Fuera de los límites de la red | dos `LinearRegionItem` en los extremos | gris `#313244` al 60 % | arrastrar "Desde" o "Hasta" dentro de esa zona lo recorta al límite, con el aviso del tope (§2.1-4) |
| Zona especular | `LinearRegionItem` [0, umbral] | durazno al 25 % | sólo se ve si el eje la incluye (en la práctica, con la red de 1200 y λ bajas) |
| Crudo por ventana | un `PlotDataItem` por ventana | colores alternados zafiro / azul | aparece al llegar `windowAcquired` |
| Cosido | `PlotDataItem` | lavanda, 2 px | al llegar `finished` |

- **Antes de arrancar**, el gráfico muestra sólo el plan: se ve cuántas ventanas hay y dónde se solapan, sin haber movido nada.
- **Durante el barrido**, Desde y Hasta se bloquean (`movable=False`) y se ven en gris.
- **Menú contextual del gráfico:** "Repetir el plan desde esta λ" (fija Desde en la λ del clic), "Exportar crudos", "Mostrar sólo el cosido".

### 3.5 Tablas: teclado y menús

| Tabla | Flechas ↑/↓ (`currentCellChanged`) | Menú contextual |
| :--- | :--- | :--- |
| Resultado por red (Calibraciones) | muestra el perfil y las llegadas de esa red | "Ver criterios K", "Aplicar corrección fina", "Proponer offset…" (con los mismos habilitados que los botones), "Copiar" |
| Historial | actualiza el detalle | §1.8 |
| Ventanas (Step & Glue) | resalta la ventana en el gráfico y muestra su crudo | "Mostrar crudo", "Abrir archivo de la ventana", "Copiar λc leída" |

- `Enter` sobre una fila = la acción principal del menú (ver detalle).
- Las tablas conservan la selección al agregar filas (§4.1).

### 3.6 Atajos

| Atajo | Acción | Cambio respecto de hoy |
| :--- | :--- | :--- |
| `Ctrl+0` | espejo rápido: entrar / volver | hoy abre el diálogo (`window.py:577-580`) |
| `Ctrl+E`, `F12` | E-STOP | sin cambios (`lab-invariants` §4, ✅) |
| `Ctrl+Space` | alternar Live | sin cambios; funciona en especular |
| `Ctrl+R` | medir en la pestaña activa (en Calibraciones: Iniciar calibración; en Step & Glue: Iniciar) | se extiende a las dos pestañas |
| `Esc` con una rutina corriendo y el foco en su pestaña | Stop de esa rutina | nuevo; **no** es la E-STOP |

La tabla de `lab-invariants` §4 se actualiza en la Ronda 4 junto con el código.

### 3.7 Señales: bloqueo bidireccional y flujo

Pseudocódigo de diseño (no es código de producción).

**Estado leído → widgets** (el servicio publica; los widgets de pedido no se tocan salvo que el operador no los esté editando):

```python
# PanelEstado, conectado a SpectrometerStateService.snapshotChanged(object)
def on_snapshot(self, snap):
    self._paint_reading(self.lbl_grating, snap.spectrograph.grating)       # sólo etiquetas [L]/[E]/[!]
    self._paint_reading(self.lbl_wavelength, snap.spectrograph.wavelength_nm)
    self._paint_reading(self.lbl_cooler, snap.camera.cooler_on)
    # el botón del enfriador refleja lo leído sin disparar su slot
    with blocked(self.btn_cooler):                                           # blockSignals(True/False) en try/finally
        self.btn_cooler.setChecked(snap.camera.cooler_on.value is True)
    # el spinbox de λ sólo se sincroniza si el operador no lo está editando
    wl = snap.spectrograph.wavelength_nm
    if wl.status is ReadStatus.READ_OK and not self.spin_wavelength.hasFocus() and not self._pending_request:
        with blocked(self.spin_wavelength):                                  # una lectura fallida no toca el pedido
            self.spin_wavelength.setValue(wl.value)
    self._set_specular_ui(snap.spectrograph.specular)                       # candado de ganancia, tope de exposición
```

`blocked(w)` es un administrador de contexto con `try/finally`, para que una excepción no deje un widget con las señales bloqueadas para siempre.

**Gráfico ↔ spinbox, sin bucle** (Step & Glue, Desde y Hasta):

```python
line_start.sigPositionChangeFinished.connect(on_line_start_moved)   # al soltar, no en cada píxel
spin_start.editingFinished.connect(on_spin_start_edited)

def on_line_start_moved(line):
    v = clamp(line.value(), limits.lo, spin_end.value() - 1.0)
    with blocked(spin_start):
        spin_start.setValue(v)
    with blocked(line):                        # re-coloca la línea si hubo recorte
        line.setValue(v)
    replan()                                   # puro: StepGlueEngine.plan(request, snapshot)

def on_spin_start_edited():
    with blocked(line_start):
        line_start.setValue(spin_start.value())
    replan()
```

Durante el arrastre (`sigPositionChanged`), sólo se redibuja el plan en modo "borrador" (contornos punteados), sin tocar el spinbox. Así no hay cascada de `editingFinished`.

**Pedido de movimiento → worker → resultado:**

```python
# GUI
btn_go.clicked -> self._request_move()
def _request_move(self):
    target = MotionTarget(grating=self.cmb_grating.currentData(), wavelength_nm=self.spin_wavelength.value())
    self._pending_request = target
    self._set_busy(True, "Moviendo…")
    self.spectrograph_worker.requestMove.emit(target)          # QueuedConnection al hilo del espectrógrafo

# worker (hilo del espectrógrafo) emite moveFinished(object) con el MotionResult
def on_move_finished(self, result):
    self._pending_request = None
    self._set_busy(False)
    if not result.ok:
        self.warnings.show(severity="error", text=explain(result))   # fila en la franja o en el control
    # no se escribe ningún valor en los widgets de pedido: el próximo snapshot trae lo leído
```

**Rutina → GUI (Step & Glue):** `progress(int, int, float)` actualiza las dos barras; `windowAcquired(object)` agrega la curva y marca la fila (nunca reconstruye la tabla); `finished(object)` dibuja el cosido y habilita Iniciar; `failed(str)` deja todo lo adquirido y muestra el motivo. Todas con `QueuedConnection`. Ningún slot de la GUI llama al driver.

**Transacción de offsets:** el diálogo emite `confirmDiff(token)` y `confirmWrite(token)` al hilo del espectrógrafo y espera `transactionState(object)`. Los botones se deshabilitan entre la emisión y la respuesta, para que un doble clic no emita dos veces.

## 4. Resiliencia del estado [PROPUESTA]

### 4.1 Qué nunca se borra por una acción local

| Acción | Qué cambia | Qué se conserva |
| :--- | :--- | :--- |
| Una llegada nueva en la calibración | se agrega un punto y se recalcula la media | todas las llegadas previas, la selección del operador |
| Calibración de una red termina | su fila en "Resultado por red" | las filas de las otras redes de la corrida y de corridas anteriores de la sesión |
| Nueva entrada en el archivo | se inserta **una** fila arriba del historial (`insertRow(0)`) | la selección (por `record_id`, no por índice de fila), el filtro, el desplazamiento |
| Aplicar corrección fina | una entrada nueva; el panel izquierdo muestra la nueva | la corrección anterior sigue en el historial |
| Una ventana nueva de Step & Glue | su curva y su fila | las curvas de las ventanas previas, el plan |
| Editar un parámetro de Step & Glue después de un barrido | se recalcula el plan | el resultado del barrido anterior queda dibujado en gris hasta el próximo Iniciar, con la leyenda "barrido anterior (14:05)" |
| Espejo rápido | el estado especular y la exposición | la red y la λ de primer orden (para volver), la ganancia previa (para la pastilla de restitución), la ROI del Live |
| E-STOP | todo se detiene | resultados parciales, archivos ya escritos, parámetros de todas las pestañas |
| Reconectar un equipo | el snapshot de ese equipo | los parámetros de las pestañas; la corrida en curso no existe, porque reconectar se rechaza con una sesión activa |

Regla para la Ronda 4: **ningún `clear()`, `setRowCount(0)` ni reasignación de listas de resultados fuera del botón "Iniciar"** de la propia rutina. La verificación manual lo comprueba en M-08 y M-12 (§8).

### 4.2 Cancelar la calibración a mitad

- **Modo SÓLO MEDIR (el único del bloque A):**
  - "Cancelar" pide la detención; el worker aborta la exposición en curso (≤ 250 ms más `AbortAcquisition`, R2-inst §5.2) y cierra el 532, que la rutina abrió (R2-inst §4.1, K7).
  - Nada se escribió, así que nada se restaura.
  - Las llegadas ya medidas **se guardan**: el registro de esa red queda con el veredicto CANCELADA y sus crudos en el HDF5 (D-03: el veredicto no existe en el contrato). La fila de la red se pinta en gris con "cancelada tras 7 llegadas".
  - Las redes no empezadas no generan registro.
- **Cuando la escritura se habilite (después de BANCO-40):** si se cancela entre una sonda o una escritura y su medición, el motor restaura O₀ y relee (R2-met §2.3, "Todo aborto restaura O0 y lo relee"). La GUI lo muestra en la fila: "cancelada · offset restaurado a 85 (releído 85)". Si la relectura no coincide: aviso rojo persistente, "offset de la red 1 en estado desconocido tras cancelar: se pidió 85, se releyó 89", con [Restaurar 85…] (la transacción de §1.7).
- **E-STOP durante la calibración:** igual que Cancelar, pero el motivo es "E-STOP" y el obturador se cierra por la E-STOP misma.
- **Cierre de la ventana durante la calibración:** el diálogo de cierre agrega "Hay una calibración en curso: se cancela y se guarda lo medido".

### 4.3 Cancelar Step & Glue

- **Stop:** el worker aborta, entrega `StepGlueResult(complete=False, stop_reason=USER_STOP)` con las ventanas terminadas, que ya están en disco (R2-arq §2.9).
- En el gráfico, las ventanas adquiridas quedan con relleno; las pendientes, sólo con contorno y "no adquirida". **No se cose** un resultado incompleto automáticamente: un botón [Coser lo adquirido] lo hace a pedido y rotula el resultado "incompleto (ventanas 1-2 de 5)".
- La ventana interrumpida a mitad de exposición no se guarda como dato: su fila dice "interrumpida (sin datos)", nunca un cuadro de ceros (R4-5).
- Los parámetros quedan como estaban, para repetir con un clic.

### 4.4 Cómo se ven los veredictos

Dos ejes separados: el del **hardware** (¿la escritura quedó?) y el de la **metrología** (¿la calibración es buena?). Nunca se mezclan en un solo color.

| Veredicto | Eje | Color | Texto en la fila | Qué se habilita |
| :--- | :--- | :--- | :--- | :--- |
| ACEPTADA | metrología | verde apagado `#a6e3a1` con borde, sin relleno | "ACEPTADA (criterios PROVISORIOS)" | corrección fina; proponer offset (si hay S) |
| ACEPTADA_CON_RESERVA | metrología | amarillo `#f9e2af` | "CON RESERVA: U no declarada (faltan #5, #6, #7)" | ídem |
| EN_SECO / sólo medir | metrología | azul `#89b4fa` | "SÓLO MEDIDA: residuo r = +2.38 ± 0.29 px; conversión a pasos pendiente (BANCO-40)" | corrección fina si pasa K1-K7 |
| RECHAZADA | metrología | rojo `#f38ba8` | "RECHAZADA: K3 (repetibilidad 1.4 px > 1 px), K6 (ASIMETRÍA)" | nada; [Ver criterios] |
| CANCELADA | metrología | gris `#6c7086` | "cancelada tras 7 llegadas" | [Ver lo medido] |
| CONFIRMADO | hardware | verde `#a6e3a1` lleno | "escrito 85 → releído 85" | — |
| NO COINCIDE / DESCONOCIDO | hardware | rojo lleno | "se pidió 12, se releyó 0" | [Restaurar valor anterior…] |
| ESCRITURA FALLIDA | hardware | rojo lleno | "SetGratingOffset devolvió 20201; releído 85 (sin cambio)" | [Reintentar…] |

- En la fase exploratoria, **toda** calibración va a quedar CON RESERVA hasta que se midan los términos #5-#7 (R2-met §4.2). El diseño lo hace explícito en el texto, en vez de dejar que el amarillo parezca un problema del operador.
- El tooltip de cada veredicto lista los criterios K1-K7 con su valor, su umbral y la marca PROVISORIO (T-CAL-8).
- La palabra "validado" no aparece en ninguna parte de la GUI de calibración.

### 4.5 Cómo se restaura el valor original

1. **El valor original siempre está en el archivo.** El `OBSERVED` de cada arranque y el `PRE_WRITE` de cada transacción guardan lo leído antes de tocar nada (R2-arq §2.5).
2. **Restaurar es una escritura más**, con la misma transacción, las mismas confirmaciones y el mismo respaldo. No hay un "deshacer" de un clic: restaurar mal es tan grave como escribir mal.
3. **Caminos a la restauración:**
   - desde la página 5 del diálogo, si la escritura no coincidió (§1.7);
   - desde el historial, en una entrada `PRE_WRITE` o `APPLIED` (§1.8);
   - desde el aviso rojo de estado desconocido (§4.2).
   Los tres abren el mismo diálogo con la propuesta prellenada y la procedencia "restauración del respaldo del 2026-10-02 14:31". Si la restauración fuera de la rutina se permite es la pregunta Q4.
4. **Corrección fina:** "restaurarla" es aplicar la anterior desde el historial ("Usar esta corrección fina"). Es un cambio sólo de PySpectrum y no pasa por la transacción.

### 4.6 Validez de la corrección fina al arrancar

La corrección fina `c_sw` se midió **con un offset entero dado** (R2-met §1.5). Si el equipo tiene otro offset, esa corrección no corresponde.
- **Regla propuesta:** al arrancar, la corrección fina de una red se aplica sólo si el offset leído de esa red es igual a `grating_offset_after` del registro que la produjo, y el número de serie, los puertos y la geometría también coinciden. Si no, queda **suspendida**, con el motivo en el panel y en el aviso de arranque (§1.11).
- **Mostrada siempre**, con su veredicto y su fecha, en el panel izquierdo y en el metadato de cada espectro guardado (`c_sw_px`, `c_sw_convention`, `record_id`), porque Solis y el legado no la ven (R4-B 2) y un espectro sin ella no se puede reinterpretar.
- Esta regla no está en el contrato de la Ronda 2 (D-04).

## 5. Pedagogía: tooltips y ayuda [PROPUESTA]

### 5.1 Reglas

1. Cada tooltip responde, en este orden: **qué magnitud es** (con unidad), **de dónde sale** (leído, enviado, derivado, y de qué llamada), **cuál es el valor de referencia** y **qué hacer si se ve mal**.
2. Una fórmula aparece con sus números de este equipo, no sólo en símbolos.
3. Todo número del tooltip sale de la Ronda 2, de `lab-invariants` o del código, con la fuente entre corchetes al final. Un número sin fuente no entra (memoria *verify-docs-against-primary-sources*).
4. Lo provisorio lo dice: "PROVISORIO (fase exploratoria, R4-A 9)" o "provisorio hasta BANCO-n".
5. Máximo unas 8 líneas. Lo que no entra va al `[Ayuda]`.
6. Los tooltips con números que dependen de la red se generan con los valores de la red activa (el umbral, la dispersión, la ventana), no con los de las dos redes a la vez.

### 5.2 Espectrógrafo y espejo rápido

**T-SPEC-1 · Condición especular (insignia y línea "destino")**
> La red está en **condición especular** cuando refleja la luz hacia el detector sin dispersarla: orden cero, la red espejo, o una λc tan chica que el orden cero entra al chip.
> Umbral con esta red (150 l/mm): |λc| < 1.1 · W/2 = 1.1 · 103.05 nm / 2 = **56.7 nm**. Con la de 1200: 1.1 · 11.57 / 2 = **6.4 nm**.
> W = dispersión × ancho del detector = 12.83 nm/mm × (1004 × 8 µm) = 103.05 nm (150 l/mm); 1.44 nm/mm × 8.032 mm = 11.57 nm (1200 l/mm).
> El 1.1 es un margen de seguridad provisorio; BANCO-42 mide dónde aparece de verdad la imagen especular.
> En especular la ganancia EM queda bloqueada en 0 y la exposición acotada.
> [R2-inst §2.1; `lab-invariants` filas 119-121]

**T-SPEC-2 · λc (SDK)**
> Longitud de onda central **que informa el Shamrock** (`ShamrockGetWavelength`), en nm.
> Es la λ que el SDK calcula para la posición ordenada: el motor es paso a paso, sin sensor de ángulo, así que no es una medición independiente.
> Repetibilidad de la torreta: 10 pm según la hoja de datos (≈ 0.87 px con la red de 1200). [DS-SR500 p. 13, n. 20; R2-met §1.3]

**T-SPEC-3 · Offsets**
> Offsets de la torreta, en **pasos de motor**, leídos del Shamrock. Corrigen dónde cae cada λ en el detector.
> Uno por red (150 y 1200) y uno del detector, que por convención del laboratorio vale 0 (R4-A 2).
> Solis y el PySpectrum legado ven estos mismos valores.
> Cuántos píxeles corre un paso no está medido en este equipo (BANCO-40). Se escriben sólo desde la pestaña Calibraciones.

**T-SPEC-4 · Corrección fina**
> Corrección por debajo de un paso, en píxeles, que **sólo aplica PySpectrum** (R4-B 2): el eje queda λ(p) = λ_SDK(p + c).
> Vale para el offset entero con que se midió. Si el equipo tiene otro offset, se suspende.
> Cada espectro guardado la registra en su metadato. [R2-met §1.5]

**T-ZO-1 · Botón Espejo rápido (primer orden)**
> Lleva la red a orden cero (o a la red espejo) para ver la muestra o centrar el láser en la ranura.
> Antes de girar: detiene la cámara, fija la ganancia EM en 0 y la relee, acota la exposición y cierra todos los obturadores (confirmado). Si algo de eso no se confirma, no gira.
> Después reanuda el Live si estaba corriendo. Podés abrir los obturadores que necesites.
> Ctrl+0 entra y vuelve.

**T-ZO-2 · Tope de exposición en especular**
> En especular la luz no se dispersa: toda cae en la imagen de la ranura. El tope evita saturar el detector.
> Tope actual: 10 ms, **provisorio** hasta BANCO-43 (exposición segura en orden cero con cada red).
> El indicador de saturación usa el ADC de 14 bit: 16 383 cuentas; avisa por encima del 50 %. [R2-inst §2.2, Z5 y Z10]

**T-ZO-3 · Ganancia antes del orden cero (pastilla)**
> La ganancia EM no vuelve sola al salir del orden cero (R4-B 4): así un error en la salida nunca deja ganancia alta con la red en especular.
> Este botón la restituye con un clic, si querés.

### 5.3 Cámara

**T-CAM-1 · Marcas [L] [E] [!]**
> [L] leído del equipo · [E] enviado: el SDK no permite leerlo, sólo consta que el equipo aceptó el valor · [!] falló la lectura (código del SDK) · [?] todavía sin leer · [X] equipo no conectado.
> Los modos de lectura, de adquisición, de ganancia y el ventilador no tienen función de lectura en el SDK2 v2.104. [README R2 §1]

**T-CAM-2 · Temperatura**
> Temperatura del sensor, en °C, con el estado que devuelve `GetTemperature`: estabilizada · enfriando, todavía no llega · llegó pero no se estabilizó · deriva · enfriador apagado · adquiriendo (se muestra el último valor).
> Setpoint de arranque: −60 °C (R4-A 6). El SOP Raman usa −60 °C; Solis registró −65 °C (`lab-invariants` fila 124).
> Si no llega en ~15 min con el ventilador en low, probá high. [R2-inst §6.2-6.3]

**T-CAM-3 · Ventilador**
> low (arranque, R4-A 6) o high (= "full" del SDK). "Apagado" no se ofrece: con el sensor frío, el manual lo permite sólo por períodos cortos. [SDK p. 273]
> No se puede cambiar durante una adquisición: se aplica al terminar la exposición en curso.

**T-CAM-4 · Ganancia EM**
> Ganancia del registro multiplicador, en **unidades DAC** (modo 0, 0-255), no en "×". Rango leído del equipo con `GetEMGainRange`.
> Con una línea láser o la lámpara la señal sobra: la calibración y el orden cero la usan en 0.
> En condición especular queda bloqueada en 0. [R2-inst §6.4]

**T-CAM-5 · Exposición**
> Tiempo de integración pedido; al lado, el **real** que informa `GetAcquisitionTimings`.
> Tope del driver: 60 s (R4-B 9). Las rutinas aceptan hasta 10 s (R4-4). En especular, el tope provisorio de T-ZO-2.

**T-CAM-6 · Velocidad horizontal**
> Velocidad de lectura del registro, de la tabla del equipo. 13 MHz por defecto (R4-B 8): el menor ruido de lectura de las tres (35, 27, 13 MHz, todas de 14 bit). [DS-iXon p. 2]

### 5.4 Calibración de λ

**T-CAL-1 · Qué hace la rutina**
> Reemplaza el ajuste manual en Solis (mover el offset hasta que el pico caiga en 532 nm).
> Por cada red: mira la línea del 532, ajusta su centro y mide el **residuo** r: cuánto dista la línea de donde el eje del SDK dice que debería estar.
> En esta fase **sólo mide**: no escribe nada al Shamrock. La escritura se habilita cuando BANCO-40 mida cuántos píxeles corre un paso.

**T-CAL-2 · Residuo**
> r = x̂ − p_SDK(λ_ref) ≈ [λ_SDK(x̂) − λ_ref] / D, en píxeles.
> x̂: centro ajustado de la línea. p_SDK(λ_ref): píxel donde el eje del SDK pone λ_ref. D: dispersión local (≈ 0.1026 nm/px con 150 l/mm; ≈ 0.01152 nm/px con 1200).
> r = 0 es la calibración perfecta. Ejemplo: r = +2.41 px con 1200 l/mm son +0.028 nm. [R2-met §1.2]

**T-CAL-3 · Ajuste de la línea**
> Gaussiana + fondo lineal en una ventana de ±3 FWHM, recentrada una vez. El fondo lineal absorbe el ala del notch.
> Antes: se resta el oscuro y se descartan rayos cósmicos comparando cuadros (no con el filtro de picos espacial, que deforma una línea angosta).
> Se rechaza la llegada si algún píxel supera 0.8 × 16 383 cuentas. [R2-met §2.1]

**T-CAL-4 · Llegadas**
> Una "llegada" es llevar la torreta a la λc siempre desde abajo, esperar y tomar 5 cuadros.
> Cada llegada cae un poco distinto: la repetibilidad de la torreta (10 pm ≈ 0.87 px con 1200) domina la incertidumbre, no el ajuste.
> Por eso se promedian de 9 a 25 llegadas, hasta que u_A llegue al objetivo. [R2-met §3.2]

**T-CAL-5 · Incertidumbre**
> u_c ≈ 0.29 px con 9 llegadas (casi toda de la repetibilidad).
> U = k · u_c con **k = t₀.₉₇₅(ν_eff)**, no 2: con ν_eff ≈ 8, k = 2.31.
> **U no se declara** mientras falten términos sin valor: sesgo de la fuga por el notch (#5), deriva del espectrógrafo (#6) y del láser (#7). [R2-met §3.2]

**T-CAL-6 · λ de referencia**
> Longitud de onda del láser **en aire**, en nm. Hoy no tiene un valor medido: 532.000 es el nominal.
> Sin lámpara de calibración, la exactitud absoluta del eje es la de este número. La rutina deja el eje coherente con el láser; eso es relativo. [R2-met §3.4]
> Anotá de dónde sale el valor (etiqueta, medición) en "origen".

**T-CAL-7 · Corrección fina y offset**
> La corrección entera va al offset del Shamrock; lo que queda por debajo de un paso es la corrección fina, sólo de PySpectrum (R4-B 2).
> Offset propuesto: O* = O₀ + round(−r / S), con S en px/paso (medida en BANCO-40).
> Cambio estimado en nm: Δλ ≈ ΔO · S · D. [R2-met §1.4-1.5]

**T-CAL-8 · Criterios K1-K7 (PROVISORIOS)**
> K1 u(c) ≤ 0.22 px (150) / ≤ 0.43 px (1200) · K2 sólo hardware |r| ≤ max(0.5 px, |S|/2 + 2u) · K3 repetibilidad ≤ 1 px · K4 recorrido: ≤ 1 px en el centro y ≤ 2 px (150) / ≤ 3.5 px (1200) en ±0.35 W · K5 signo de la dispersión igual al del SDK · K6 SNR ≥ 20, sin saturación ni banderas · K7 deriva ≤ 3 × repetibilidad.
> Son **provisorios**: fase exploratoria (R4-A 9). Aunque se cumplan todos, la calibración queda CON RESERVA mientras la U no esté completa. [R2-met §4.2]

### 5.5 Escritura de offsets

**T-WR-1 · Por qué tantas confirmaciones**
> Escribir un offset cambia lo que ven Solis y el legado, y puede girar la torreta. Por eso: leer, mostrar las diferencias (1.ª confirmación), respaldar, escribir el número de la red (2.ª), escribir y releer.
> Con un cambio de más de ±50 pasos se pide una 3.ª confirmación, con el cambio estimado en nm (R4-B 10).

**T-WR-2 · Resultado**
> CONFIRMADO: el valor releído es el escrito. NO COINCIDE o DESCONOCIDO: el equipo no tiene lo que se pidió; se puede restaurar el valor anterior, que quedó en el respaldo.
> Que el valor sobreviva a apagar el Shamrock no está confirmado todavía (BANCO-37 y BANCO-37b).

### 5.6 Step & Glue

**T-SG-1 · Plan**
> Ventanas necesarias para cubrir el rango con el solapamiento pedido. Cada ventana cubre W nm (medido del eje de la red activa: ≈ 103 nm con 150 l/mm, ≈ 11.6 nm con 1200).
> Paso ≈ W · (1 − solape). Ejemplo: 500-900 nm con 150 l/mm y 20 % → paso ≈ 82 nm, 5-6 ventanas; con 1200 l/mm → paso ≈ 9.3 nm, ≈ 44 ventanas. [R2-inst §5.3]

**T-SG-2 · Duración estimada**
> Por ventana: movimiento (≤ 0.3 s más la llamada, provisorio hasta BANCO-39) + exposición + lectura (≈ 0.08 s a 13 MHz). Un cambio de red suma ~4 s. [R2-inst §7.1]

**T-SG-3 · Espejo de detección**
> El espejo que manda la luz al espectrómetro (abajo) o a la cámara (arriba) **no tiene sensor**: esto es lo último que ordenó el software. Si alguien lo movió a mano o se reinició la placa, puede no coincidir (C-08).

**T-SG-4 · Luz**
> Lámpara: la rutina no abre obturadores láser. Láser: [texto según la respuesta a Q3].
> Mientras el barrido renueva el latido del watchdog, un obturador olvidado abierto no se cierra por inactividad. La barra superior lo indica.

**T-SG-5 · Stop**
> Detiene el barrido en menos de un cuarto de segundo, también en medio de una exposición. Las ventanas terminadas ya están en disco. [R2-inst §5.2]

### 5.7 Botones [Ayuda]

`ScientificWikiBrowserDialog.navigate_to(note_id, anchor)` sólo abre notas `CAT-`, `SYS-` y `MOD-` (§0.6). Los documentos de la auditoría (`docs/evidence/`) no se pueden abrir desde ahí, así que la ayuda necesita notas nuevas o secciones nuevas.

| Botón | Destino | Estado del destino |
| :--- | :--- | :--- |
| Panel: Espectrógrafo | `MOD-06` §"Estado leído del espectrómetro" | **por crear** (Ronda 4, junto al código) |
| Panel: Espejo rápido | `MOD-06` §"Espejo rápido (orden cero)" | **por crear**. Reemplaza a §12.3 (`ZeroOrderSafetyDialog`), que describe el diálogo que se retira |
| Panel: Cámara | `MOD-06` §7 "Control térmico y ganancia" | **existe, a corregir**: hay que verificar sus números contra R2-inst §6 antes de enlazarla |
| Panel: Espejo de detección | `SYS-202` (flipper y DAQmx) | existe; **no verificado en esta ronda** para la parte del espejo `line7` |
| Calibraciones (pestaña) | **`CAT-252` "Calibración de λ del Shamrock con la línea del láser"** (nombre propuesto), anclas `#residuo`, `#llegadas-y-repetibilidad`, `#criterios-provisorios`, `#presupuesto`, `#exactitud-absoluta` | **por crear**, a partir de `pyspectrum_A_ronda2/metrology.md` §1-§4 |
| Diálogo de escritura | `MOD-06` §"Escritura de offsets" | **por crear** |
| Step & Glue | `MOD-06` §"Step & Glue" (hoy §8.4) | **existe, a reescribir** con el plan, el preflight y el Stop nuevos |
| Tablero: Reconectar | `MOD-13` | existe; agregar el aviso del enfriador |
| Insignia de latido | `SYS-201` §3.3 | existe, **con una contradicción**: §5.3 (l. 260) avala `heartbeat_shutter(30.0)` con argumento explícito, lo contrario de C-29. Corregir antes de enlazar |

**No se enlaza `SYS-303`** (protocolo de calibración): describe la persistencia en `.txt` que la Ronda 2 reemplaza, el estado `CALIBRADO_VALIDADO` del archivo inventado (l. 310) y la escritura en EEPROM de fase 3. Se archiva o se reescribe (memoria *archive-docs-describing-nonexistent-code*); tampoco `SYS-302` §2 sin revisarlo.

## 6. Reconciliación GUI ↔ motor (preliminar, para la Ronda 4)

### 6.1 Control de la GUI → parámetro del motor

Nombres del motor tal como están en la Ronda 2. "—" en el motor = [FALTA-CONTRATO] (ver §6.2).

| # | Control (GUI) | Parámetro del motor | Tipo | Unidad | Default GUI | Default motor | Estado |
| :-- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Panel de estado y espejo rápido** | | | | | | | |
| 1 | Red pedida + Ir | `MotionTarget.grating` → `SpectrographMotionEngine.move` | `int \| None` | índice | leída | `None` | OK |
| 2 | λc pedida + Ir | `MotionTarget.wavelength_nm` | `float \| None` | nm | leída | `None` | OK |
| 3 | Línea "destino" | `SpectrographMotionEngine.classify(target) -> SpecularCondition` | — | — | — | — | OK (pura) |
| 4 | Espejo rápido: orden cero / red espejo | `ZeroOrderService.enter_specular()` (R2-arq) vs `enter_specular(target: "zero_order" \| "mirror", restart_live=True)` (R2-inst) | — | — | orden cero | — | **D-08** |
| 5 | Volver | `leave_specular(grating, wavelength_nm)` | `int, float` | —, nm | la recordada | — | OK |
| 6 | Ranura + Fijar | `set_auto_slit_width(1, w_um)` en el driver; **sin camino por el worker** | `float` | µm | leída | — | **D-12** |
| 7 | Fijar Side/Direct | `set_flipper_mirror(f, port)` (driver) | `int, int` | — | — | Side / Direct (`SpectrographBaseline`) | **D-12** (mismo camino) |
| 8 | Setpoint de temperatura | `CameraBaseline.temperature_setpoint_c` (arranque) y `SetTemperature` en operación | `int` | °C | −60 | −60 | OK; falta el servicio de operación (**D-13**) |
| 9 | Enfriador | `cooler_on` (arranque); `CoolerON`/`CoolerOFF` en operación; se muestra `CameraState.cooler_on` | `bool` | — | leído | `True` | **D-13** |
| 10 | Ventilador low / high | `CameraBaseline.fan_mode: FanMode` (`LOW`=1, `FULL`=0) | `IntEnum` | — | low | `LOW` | OK; **D-13** en operación |
| 11 | Velocidad horizontal | `CameraBaseProfile.hs_speed_index` (R2-inst) | `int` | índice → MHz | 13 MHz por valor | `<BANCO-38>` | **D-14** |
| 12 | Ganancia EM + Aplicar | `set_emccd_gain(g)` (driver, con interlock) | `int` | DAC | 0 | 0 | OK |
| 13 | Exposición + Aplicar | `set_exposure_time(t)` (driver, recorte a `T_MAX_S` y a `SPECULAR_MAX_EXPOSURE_S`) | `float` | s | 0.05 | 0.05 (C15) | OK |
| 14 | Marcas [L]/[E]/[!]/[?]/[X] | `Reading.status: ReadStatus` + `DeviceStatus` | enum | — | — | — | **D-15** (falta `SENT`) |
| 15 | Corrección fina (panel) | `c_sw_px`, `verdict`, `grating_offset_after` del registro | `float` | px | — | — | **D-04** |
| 16 | Espejo de detección: posición | `MirrorBelief(position, source, since)` | dataclass | — | — | — | OK |
| **Calibración automática** | | | | | | | |
| 17 | Redes | `AutoCalibrationPlan.gratings` / `OffsetCalibrationConfig.grating` (una por config) | `tuple[int]` / `int` | — | (1, 2) | — | **D-01** |
| 18 | Fuente (notch / atenuado) | `filters` del registro (R2-met §4.1) | — | — | notch | — | **D-01** (no está en la config) |
| 19 | λ de referencia | `lambda_ref_nm` / `reference_nm` | `float` | nm (aire) | 532.000 | 532 nominal | OK (dos nombres, **D-01**) |
| 20 | Origen de λ_ref | `lambda_ref_source` | `str` | — | "nominal, sin medir" | obligatorio | OK |
| 21 | u(λ_ref) | `u_lambda_ref_nm` | `float \| None` | nm | `None` | `None` | OK |
| 22 | Notch confirmado | — (supuesto del método; R2-arq §2.7 dice "se le pregunta al operador") | `bool` | — | `False` | — | **D-01** |
| 23 | Espejo confirmado | — (advertencia del preflight) | `bool` | — | según creencia | — | **D-10** |
| 24 | Recorrido ±0.35 W | `walk_fractions_of_window` | `tuple[float]` | fracción de W | (−0.35, 0, 0.35) | ídem | OK (casilla = tupla vacía o no) |
| 25 | Cuadros por llegada | `frames_per_arrival` / `n_frames` | `int` | — | 5 | 5 | OK (dos nombres) |
| 26 | Cuadros de oscuro | `dark_frames` | `int` | — | 5 | 5 | OK |
| 27 | Llegadas por iteración | `arrivals_per_iteration` | `int` | — | 4 | 4 | OK |
| 28 | Llegadas finales mín / máx | `arrivals_final_min` / `arrivals_final_max` | `int` | — | 9 / 25 | 9 / 25 | OK |
| 29 | u objetivo | `u_target_px` | `float \| None` | px | 0.22 / 0.43 | `None` → 0.22 / 0.43 | OK |
| 30 | Exposición (automática o fija) | `exposure_s` (`None` = automática), `exposure_max_s` | `float \| None` | s | automática | `None`; máx 10 s (met) vs `T_CAL_MAX` 1 s (inst) | **D-02** |
| 31 | Filas del ROI | `roi_rows` | `tuple[int, int] \| None` | fila | traza ± 4 | `None` | OK |
| 32 | Acercamiento δ | `approach_delta_nm` / `approach_from_below_nm` | `float \| None` | nm | 20 / 3 | 20 / 3 | OK (dos nombres) |
| 33 | Modo SÓLO MEDIR | `dry_run` | `bool` | — | `True` fijo | `True` | OK |
| 34 | Semilla por clic | `estimate_line_center(center_guess_px, search_range_px)` | `float`, `tuple` | px | — | `None` | **D-05** (no llega desde el lazo) |
| 35 | Cancelar | `stop_event: threading.Event` / `should_abort` | — | — | — | — | OK (dos nombres) |
| 36 | Aplicar corrección fina | `CalibrationRepository.append(entry)` con `c_sw_px` | — | px | — | — | **D-04** (qué `kind`) |
| 37 | Veredicto por red | `verdict` ∈ {ACEPTADA, RECHAZADA, EN_SECO} + ACEPTADA_CON_RESERVA (R2-met §4.2) | enum | — | — | — | **D-03** |
| **Escritura y archivo** | | | | | | | |
| 38 | Abrir diálogo con la propuesta | `OffsetWriteTransaction.prepare(targets: Mapping[CalibrationKey, int])` | — | pasos | — | — | OK |
| 39 | Confirmo estas diferencias | `confirm_diff(token)` | `ConfirmationToken` | — | — | — | OK |
| 40 | Escribir (número de la red tecleado) | `confirm_write(token)` | `ConfirmationToken` | — | — | — | OK; el tecleo es GUI pura |
| 41 | 3.ª confirmación (> 50 pasos) | — | `int` umbral | pasos | 50 | — | **D-07** |
| 42 | Vencimiento del token | `DoubleConfirmToken` "vence a los 60 s" (R2-inst) | — | s | 60 | 60 | OK; falta leerlo del token (**D-07**) |
| 43 | Registrar valor leído en Solis | `append(MANUAL_ENTRY)` | — | pasos | — | — | OK |
| 44 | Registrar lo leído al arrancar | `append(MANUAL_ENTRY, note="adoptado…")` | — | — | — | — | OK |
| 45 | Restaurar desde el historial | `prepare({key: valor_respaldo})` | — | pasos | — | — | OK en el motor; **Q4** en la política |
| **Step & Glue** | | | | | | | |
| 46 | Desde / Hasta | `StepGlueRequest.start_nm` / `end_nm` | `float` | nm | 500 / 900 | — | OK |
| 47 | Solape | `overlap_frac` | `float` | fracción (GUI en %) | 20 % → 0.20 | — | OK (conversión en la GUI) |
| 48 | Exposición | `exposure_s` | `float` | s | 1.0 | ≤ `MAX_ROUTINE_EXPOSURE_S` (10) | OK |
| 49 | Luz lámpara / láser | — | enum | — | lámpara | — | **D-09b** (latido) |
| 50 | Normalizar + archivo | `normalize_with_lamp`, `lamp_file` | `bool`, `Path \| None` | — | `False`, `None` | — | OK |
| 51 | Verificar agua | `check_water` | `bool` | — | `False` | — | OK |
| 52 | Ventana fija legada | `use_optical_core` | `bool` | — | `False` | — | OK |
| 53 | Fondo | `background: BackgroundPolicy` | enum | — | un cuadro | — | OK (valores por definir con `metrology`) |
| 54 | Modo de lectura | `read_mode` (del snapshot) | `ReadMode` | — | vigente | — | OK |
| 55 | Red | — | — | — | leída | — | **D-09** |
| 56 | Ganancia EM del barrido | — (G7 de R2-inst: "al valor del operador") | `int` | DAC | la del panel | — | **D-11** |
| 57 | Plan (ventanas, duración) | `StepGlueEngine.plan(request, snapshot) -> StepGluePlan` | — | — | — | — | OK; la duración estimada no está en `StepGluePlan` (**D-16**) |
| 58 | Stop | `StepGlueWorker.request_stop()` | slot | — | — | — | OK |
| 59 | Progreso de la exposición | `progress(int, int, float)` | señal | — | — | — | **D-16** (falta la fracción de exposición) |
| 60 | Espejo: 3 opciones del preflight | `PreflightReport.warnings`; "Bajar" = `flipper_notch532("down")` | — | — | — | — | **D-10** |
| 61 | Seguir tras "ventana sin luz" | — (G8 de R2-inst: "pausa") | — | — | — | — | **D-17** |
| **Tablero y cierre** | | | | | | | |
| 62 | Reconectar cámara / Shamrock | `DeviceRegistry.reconnect(dev)` | — | — | — | — | OK |
| 63 | Refrescar estado | `HardwareManager.refresh_status()` | — | — | — | — | OK |
| 64 | Texto del cierre | `config.PI_HOME_POS` = (50, 50, 10) µm | lista | µm | — | [50.0, 50.0, 10.0] (`config.py:57`) | OK |

Cuenta: 64 controles; 36 sin observaciones y 28 con una discrepancia, un contrato faltante o una pregunta abierta (D-01 a D-17 y Q4).

### 6.2 Discrepancias que la Ronda 4 tiene que resolver antes de escribir código

| ID | Qué | Entre | Propuesta |
| :-- | :--- | :--- | :--- |
| **D-01** | Dos contratos para la misma rutina: `AutoCalibrationPlan` (arq: varias redes, `reference_nm`, `n_frames`, `approach_from_below_nm`, `centers_nm`) y `OffsetCalibrationConfig` (met: una red, `lambda_ref_nm`, `frames_per_arrival`, `approach_delta_nm`). Ninguno lleva la fuente (notch / atenuado), la confirmación del notch ni la del espejo | R2-arq §2.7 vs R2-met §5.1 | Un solo contrato: `AutoCalibrationPlan(configs: tuple[OffsetCalibrationConfig, ...], reference_mode: Literal["notch_leak", "attenuated_no_notch"], operator_confirmed: frozenset[str])`, con los nombres de `metrology` |
| **D-02** | Tope de exposición de la calibración: 1 s (`T_CAL_MAX`, inst §4.5) o 10 s (`exposure_max_s`, met §5.1) | inst vs met | Un símbolo en `config.py`; la GUI muestra el que quede |
| **D-03** | Veredictos: el registro tiene ACEPTADA / RECHAZADA / EN_SECO (§4.1); la sección de criterios agrega ACEPTADA_CON_RESERVA (§4.2); la GUI necesita además CANCELADA | met §4.1 vs §4.2 | Enum único con los cinco |
| **D-04** | Corrección fina: qué `kind` de entrada la registra (¿`PROPOSED`? ¿uno nuevo `SOFTWARE_CORRECTION`?) y la regla de validez al arrancar (§4.6) | R2-arq §2.5 no la trae | `kind = "SOFTWARE_CORRECTION"` con `record_id` de la calibración de origen; validez = mismo offset, serie, puertos y geometría |
| **D-05** | La semilla por clic no tiene camino desde el lazo (`run_offset_calibration` no acepta `center_guess_px`) ni bandera en el registro | met §5.1 | `retry_arrival(seed_px, search_range_px)` en el worker y la bandera `SEEDED_BY_OPERATOR` |
| **D-06** | Saturación en orden cero: Z10 aborta la adquisición; la GUI propone sólo avisar, porque el orden cero es para mirar y el operador baja la luz mirando | R2-inst §2.2 | Avisar sin abortar, con la ganancia en 0 y el tope de exposición (que ya protegen el detector). A confirmar con `instrumentation` |
| **D-07** | (a) Umbral especular: el texto de R2-inst §2.1 dice "margen 10 % de W", pero sus números (56.7 y 6.4 nm) son 1.1 · W/2, es decir, 10 % de W/2. Con 10 % de W serían 61.8 y 6.9 nm. (b) El umbral de la tercera confirmación (50 pasos, R4-B 10) no está en el contrato de la transacción. (c) R4-B 10 dice "no hay tope rígido", pero R2-inst §3.3 conserva en el driver 2000 pasos absolutos y 300 por escritura | inst vs sus propios números; R4-B 10 vs inst | (a) fijar la fórmula en `config.py` (`SPECULAR_MARGIN_FRAC` sobre W/2) y usar la misma en los tooltips; (b) `THIRD_CONFIRMATION_STEPS = 50` en `config.py`, leído por la transacción, que devuelve `needs_third_confirmation`; (c) preguntar a `instrumentation` si los topes del driver se quitan o quedan como red de seguridad por encima de la transacción |
| **D-08** | Firma del espejo rápido: `enter_specular()` sin argumentos (arq) vs `enter_specular(target, restart_live)` (inst) | arq vs inst | La de `instrumentation`, con `target` |
| **D-09** | `StepGlueRequest` no lleva la red: la rutina usa la vigente. (b) La luz (lámpara / láser) no existe en el contrato, y decide el latido | R2-arq §2.9; R4-B 5 | (a) agregar `grating: int` leído del snapshot, para que el preflight compruebe que no cambió; (b) `light_source: Literal["lamp", "laser"]` según Q3 |
| **D-10** | "Ya está abajo, confirmo" necesita escribir la creencia del espejo como resincronización del operador; `MirrorBelief.source` no tiene ese valor | R2-arq §2.10 | `source = "operator_confirmed"` y una función `confirm_detection_mirror_belief("down")` en `core/nidaq.py` (C-08) |
| **D-11** | Ganancia EM del barrido: G7 dice "al valor del operador", pero `StepGlueRequest` no la tiene | inst §5.1 vs arq §2.9 | agregar `em_gain: int` al request, tomado del panel y mostrado en el preflight |
| **D-12** | Ranura y puertos no pasan por `SpectrographWorker` (`MotionTarget` sólo tiene red, λ y orden cero), aunque la ranura es un motor (0.8 s) | arq §6.4 | agregar `slit_width_um` y `ports` a `MotionTarget`, o un `requestSlit` en el worker |
| **D-13** | No hay un servicio de operación de la cámara (setpoint, enfriador, ventilador después del arranque): la Ronda 2 sólo define `apply_operating_baseline` | arq §6.2 | `CameraControlService` con `set_temperature`, `set_cooler`, `set_fan_mode`, cada uno con relectura y aplicado entre adquisiciones (`SetFanMode` devuelve `DRV_ACQUIRING`, inst §6.2) |
| **D-14** | Pre-amp y velocidad horizontal: la lista blanca de arq §6.2 los deja **fuera**; inst §1.2 los fija (C9, C10: el pre-amp "no es opcional", SDK p. 16), y R4-B 8 decidió 13 MHz | arq vs inst y R4-B 8 | agregar `SetHSSpeed` y `SetPreAmpGain` a la lista blanca; elegir la HS por valor (13 MHz), no por índice |
| **D-15** | `ReadStatus` no tiene un estado "enviado" (`READ_OK`, `READ_FAILED`, `NOT_READ`, `NOT_CONNECTED`); `fan_mode` se describe como `Reading[int] \| None` | arq §2.4 | agregar `SENT_OK` (valor enviado con éxito, sin getter) para los cuatro parámetros sin getter |
| **D-16** | `StepGluePlan` no trae duración estimada, y `progress(int, int, float)` no trae la fracción de la exposición en curso | arq §6.6 | `StepGluePlan.estimated_duration_s` y `exposureProgress(float)` emitida en cada tramo de 250 ms |
| **D-17** | La pausa por "ventana sin luz" (G8) no tiene un slot para seguir | inst §5.1 | `StepGlueWorker.resume()` y un estado `PAUSED_NO_SIGNAL` |

### 6.3 Lo que esta ronda no decide

- El cosido que queda para Step & Glue y escaneo lineal (`metrology`, R2-arq §7.4).
- La política de fondo por ventana o único (`metrology`).
- Los valores de `SPECULAR_MAX_EXPOSURE_S`, `SPECULAR_MARGIN`, timeouts de movimiento y px/paso: salen del banco (BANCO-39, 40, 42, 43).
- El diseño de C-08 (persistencia del espejo); sólo se usa su interfaz.

## 7. Preguntas para el investigador

Seis, cada una con la decisión que desbloquea.

**Q1. En Solis, ¿con qué exposición mira la muestra y el punto del láser en orden cero?** (y con qué luz: lámpara del microscopio, láser con filtro de densidad).
- *Desbloquea:* el tope de exposición en especular. El diseño usa 10 ms provisorio (R2-inst §2.2, Z5). Si para ver la muestra hace falta más, con ese tope el "espejo rápido" mostraría una imagen oscura y no serviría para ubicarse. Define `SPECULAR_MAX_EXPOSURE_S` junto con BANCO-43.

**Q2. En orden cero, ¿abrir un láser con el filtro de densidad en potencia ALTA se bloquea, se avisa o se permite sin más?**
- *Contexto:* R4-B 3 dice "abrir a voluntad". En orden cero toda la luz cae concentrada en la imagen de la ranura; con ganancia 0 y 10 ms la cámara está protegida por el software, pero el filtro "en baja" es el último pulso enviado, no una medición (R2-inst §2.3).
- *Desbloquea:* si el panel de obturadores en especular sólo avisa (propuesta de esta ronda) o si hace falta el interlock condicional de R2-inst §2.3, que es un cambio de política de obturadores y necesita su propia aprobación.

**Q3. Cuando Step & Glue se usa con láser, ¿quién abre el obturador: usted a mano antes de iniciar, o la rutina?** ¿Y con lámpara, la rutina tiene que renovar el latido igual?
- *Contexto:* R4-B 5 pide que la rutina renueve el latido. Si lo renueva siempre, un obturador olvidado abierto en el satélite PyPrinting no se cierra por inactividad durante el barrido (hasta ≈ 9 min con 1200 l/mm, R2-inst §7.3).
- *Propuesta:* selector "Luz: lámpara / láser"; con "láser", la rutina lo abre, lo renueva y lo cierra al terminar; con "lámpara", no renueva. La insignia de latido lo muestra siempre.
- *Desbloquea:* D-09(b) y el texto de T-SG-4.

**Q4. ¿Se puede restaurar un offset anterior desde el historial (con la misma transacción de doble confirmación), o la única escritura permitida es la que sale de la rutina de calibración?**
- *Contexto:* R4-B 1 dice que el entero se escribe "sólo desde la rutina". Pero si una escritura sale mal (NO COINCIDE) o el equipo arranca con un valor inesperado (p. ej. alguien lo cambió en Solis), volver al valor respaldado sin correr la rutina entera es el camino más corto y seguro.
- *Desbloquea:* el menú "Restaurar este valor en el equipo…" (§1.8), la acción del aviso de estado desconocido (§4.2) y el paso de restauración de la página 5 del diálogo (§1.7).

**Q5. Cuando la escritura se habilite (después de BANCO-40): ¿acepta "una propuesta → una escritura con sus confirmaciones → una verificación", repitiendo el ciclo si hace falta un segundo paso?**
- *Contexto:* con px/paso conocido el modelo converge en una corrección (R2-met §2.3); un segundo paso corrige un error de S del 20-50 %. La alternativa es una "sesión autorizada" con una sola doble confirmación para varias escrituras (la Q1 de R2-arq §8.2, que quedó sin respuesta explícita).
- *Desbloquea:* si el botón "Proponer offset…" abre una transacción por paso (diseño actual) o un diálogo de sesión con varios pasos.

**Q6. ¿Qué tiene que decir el espectro guardado sobre la calibración?** En particular: ¿la corrección fina se aplica al eje guardado (y se anota), o se guarda el eje del SDK y la corrección aparte?
- *Contexto:* Solis y el legado no ven la corrección fina (R4-B 2). Si el eje guardado ya la incluye, un espectro de 3.0 y uno de Solis tomados igual difieren en una fracción de píxel; si no la incluye, el análisis posterior tiene que aplicarla.
- *Desbloquea:* el metadato de cada espectro (§4.6) y lo que el Live muestra en el eje λ superior (§1.5).

---

## 8. Verificación manual (Ronda 4, en SAFE_MODE y con los dobles del SDK)

| ID | Prueba | Resultado esperado |
| :-- | :--- | :--- |
| M-01 | Arrancar con `GetTemperature` fallando | la temperatura dice `[!]` con el código; el enfriador no dice "encendido" si `IsCoolerOn` no se leyó |
| M-02 | Arrancar con la cámara no disponible | grupo Cámara en gris con el motivo; Live, Calibraciones y Step & Glue con "Iniciar" deshabilitado y el motivo |
| M-03 | Girar la rueda del ratón sobre el combo de red sin foco | no pasa nada; la torreta no se mueve |
| M-04 | Escribir 40 nm con la red de 150 | la línea "destino" pasa a ESPECULAR; "Ir" dice "Ir (espejo rápido)" |
| M-05 | `Ctrl+0` con el Live corriendo y ganancia 150 | lista de pasos completa; insignia durazno; Live reanudado; ganancia 0 bloqueada; exposición ≤ tope |
| M-06 | `Ctrl+0` con `GetEMCCDGain` devolviendo 12 | la red no se mueve; paso "ganancia" en rojo con "leída 12, no 0" |
| M-07 | `Ctrl+0` otra vez desde especular | vuelve a la red y λ recordadas; aparece la pastilla "Restituir 150"; la ganancia sigue en 0 |
| M-08 | Correr la calibración, seleccionar la llegada 3 y dejar que lleguen más | la selección se mantiene; el historial agrega filas sin perder el desplazamiento |
| M-09 | Cancelar la calibración en la llegada 5 | fila CANCELADA en gris; el 532 se cierra; el archivo tiene la entrada con los crudos |
| M-10 | Abrir el diálogo de escritura, esperar 60 s en la página 4 | la confirmación vence y el diálogo relee |
| M-11 | Cambiar el offset en el doble entre la página 2 y la 4 | `STALE_TOKEN`: "no se escribió nada" |
| M-12 | Step & Glue: Stop en la ventana 3 de 5 | ventanas 1-2 en disco y dibujadas; 3 "interrumpida (sin datos)"; 4-5 "no adquirida"; nada se borra |
| M-13 | Step & Glue con la creencia del espejo en `up` | diálogo de tres opciones; "Cancelar" no arranca nada |
| M-14 | Arrastrar "Desde" a la zona fuera de los límites de la red | se recorta al límite, el spinbox se actualiza sin disparar `editingFinished` dos veces, el plan se recalcula |
| M-15 | Arrancar con el offset de la red 1 en 87 y el archivo en 85 | fila amarilla en la franja; corrección fina de la red 1 suspendida; nada escrito (registro de llamadas) |
| M-16 | "Reconectar cámara" con Step & Glue corriendo | botón deshabilitado con el motivo |
| M-17 | "Aislar (Mock)" de la Andor fuera de SAFE_MODE | deshabilitado con el tooltip de DEC-036 |

---

## 9. Veredicto de la ronda

**Diseño completo para los pasos 7, 8, 10, 11, 12 y 14**, con 17 discrepancias de contrato (D-01 a D-17) que la Ronda 4 tiene que cerrar antes de escribir código y 6 preguntas para el investigador (Q1-Q6). Ninguna discrepancia cambia una decisión de seguridad de la Ronda 2; varias (D-07c, D-14) son contradicciones internas de la propia Ronda 2 que esta ronda sólo hizo visibles.

Riesgo principal de la GUI: que el "espejo rápido" sea más lento o más oscuro que Solis y el operador vuelva a Solis para ubicarse. Lo mitigan la ausencia de diálogo, el Live que se reanuda solo y la pregunta Q1 sobre el tope de exposición.
