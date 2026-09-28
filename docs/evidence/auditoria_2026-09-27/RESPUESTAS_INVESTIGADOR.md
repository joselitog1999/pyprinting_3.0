# Respuestas del investigador a la auditoría

**Fuente:** investigador responsable del laboratorio, 2026-09-27. Son información de primera mano sobre el banco y el protocolo de INS-UNSAM y **prevalecen sobre `CONSOLIDADO.md`** donde lo contradigan. Cada punto indica qué hallazgos cambia. Lo marcado **[A CONFIRMAR]** es una interpretación nuestra que todavía no validó el investigador.

## 1. Placa NI y conexionado

- **Dato:** el manual de la placa está en `docs/bibliografia/` (`BNC-2110.pdf`); hay **dos BNC-2110 acopladas**.
- **Implica:** la regleta no es una SCB-68 (L2 202-11).
  - **[A CONFIRMAR]** El PCIe-6353 tiene dos conectores de 68 pines, y P0.8–P0.11 (los obturadores) están en el conector 1 (L2 202-01). Entonces cada BNC-2110 cubriría un conector, y los obturadores irían en la segunda.

## 2. Ruteo óptico y actuadores

- **Dato — espejo de detección:** el espejo up/down conmuta la detección.
  - **up**: detección confocal y cámara Canon.
  - **down**: espectrómetro.
- **Dato — filtro de densidad:** lo que figura como "flipper notch 532" es un **error de notación de la versión legacy 1.0**. Es un filtro de densidad para **todos** los láseres que conmuta la potencia entre alta y baja (escaneos confocales, autofoco, etc.). El recorrido del objetivo al espectrómetro, pasando por un beamsplitter, está descrito en algún reporte.
- **Mapeo a canales — CONFIRMADO.** El legado de PyPrinting rotula `line7` como "Mirror" y comenta "#Ahora es un espejo" (`printing2/Shutters_pp.py:63`). La segunda ronda (R2-4) fija el sentido: el espectrómetro sólo recibe luz con el espejo abajo. El mapeo, deducido primero del código legacy de PySpectrum:
  - **`Dev1/ao0` / `ao1`** (`upFlipper` / `downFlipper`; en 3.0, `up_flipper` / `down_flipper`) es el **filtro de densidad**: `down` = potencia alta, `up` = potencia baja. Así lo dice el comentario de `scratch/pyspectrum-legacy/Shutters_ps.py:187-189`, y así lo usa `modules/measurements.py` al imprimir (alta para la traza, baja para escaneos y autofoco).
  - **`Dev1/port0/line7`** ("Flipper Notch 532"; en 3.0, `flipper_notch532`) es el **espejo de detección**: `Luminescence_ps.py` y `Growth_ps.py` lo bajan al adquirir espectros y lo suben al terminar.
- **Implica, si se confirma:**
  - "Notch 532" es un nombre equivocado en `core/nidaq.py`, `core/shutters.py`, `luminescence.py`, `lab-invariants.md`, `SYS-305` §5.2 (redactada el 2026-09-27 con ese nombre), CAT-251, MANUAL y SYS-202.
  - La premisa de C-08 ("el filtro protege al EMCCD de la línea Rayleigh") no aplica. Sí sigue en pie que el estado del actuador vive sólo en memoria y nadie comanda su posición al arrancar.

## 3. Protocolo de sustrato

- **Dato:** el protocolo actual es **PDDA / PSS**.
- **Implica:**
  - Se confirma S-4: las menciones de APTES como protocolo del laboratorio son incorrectas (CAT-110, MOD-14, CAT-100, `lab-invariants` §6 y los prompts de `physicist`, `colloidal-chemist` y `experimentalist`).
  - Sigue abierto si se conserva la limpieza Piranha.

## 4. Fuerza iónica

- **Dato:** la fuerza iónica de trabajo varía entre **0.5 y 1.5 mM**.
- **Implica:** la longitud de Debye va de ≈ 13.6 nm a ≈ 7.9 nm. Se calculó para un electrolito 1:1 a 25 °C con κ⁻¹ = 0.304 nm / √I[M] (Israelachvili, *Intermolecular and Surface Forces*); en el medio del rango, 1.0 mM da ≈ 9.6 nm.
  - El valor "0.75 mM / 11 nm" de `lab-invariants` cae **dentro** del rango: no es falso, pero debe expresarse como rango y no como valor único.
  - El 1.5 mM de Gargiulo es el extremo superior.

## 5. Richardson-Lucy antes de Picasso

- **Dato:** **permitido, con advertencia.**
- **Implica:**
  - Se conserva el comportamiento del código. CAT-206 debe dejar de decir que está prohibido.
  - Hay que verificar que la advertencia exista en la GUI.
  - C-19 (fotones y `lpx` de Picasso sin significado físico tras RL) sigue en pie como advertencia metrológica.

## 6. Estado de uso de cada programa

- **Dato:**
  - **PyPrinting 3.0 y la cámara fueron probados en el banco y funcionan** en general, con detalles.
  - **PySpectrum 3.0 no fue probado.**
  - El **microscopio contrapropagante** tiene fallas de lógica, porque usa las mismas herramientas pero **duplicadas**.
- **Implica:**
  - Corrige lo que se había registrado en `DEC-036` ("PyPrinting 3.0 todavía no se usa en el banco").
  - C-01 (traza de impresión) debe re-examinarse a la luz de que la impresión funcionó en el banco (pregunta abierta: ¿se imprimió con 3.0 después del commit `6abbbfc` del 2026-09-19, que introdujo la tarea continua?).
  - El contrapropagante (C-21, C-41) es candidato a reutilizar los módulos de confocal e impresión en vez de duplicarlos.

## 7. Offsets del Shamrock

- **Dato:** el offset se mide cada cierto tiempo y se actualiza. Debe ser un **valor dinámico**:
  - que se pueda cargar desde la configuración;
  - que se pueda modificar;
  - que se pueda **calibrar con un láser, un filtro de densidad y el espectrómetro** (λ conocida, ajuste gaussiano de la emisión, píxel ↔ λ).
- **Implica:** C-04 no se resuelve eliminando la escritura, sino con un parámetro con procedencia (fecha y método de la última calibración) que se escribe al Shamrock sólo cuando corresponde. Es parte del bloque de PySpectrum.

## 8. Bibliografía de referencia

- **Dato:** la bibliografía de impresión, termometría, pinzas ópticas y temas afines está en `docs/bibliografia/`.
- **Implica:** para una inconsistencia teórica, el orden de consulta es:
  1. los artículos cargados;
  2. el investigador;
  3. la web.

## 9. Monte Carlo de Debye-Waller

- **Dato:** es un **método en desarrollo**; no hay bibliografía propia publicada. Se pide reunir bibliografía sobre error posicional y factor de Debye-Waller estático.
- **Implica:**
  - CAT-307, la Pestaña 3 y los valores σ_MC deben rotularse **experimentales**.
  - C-11 (σ = 0 por estimadores distintos) es un defecto de un método en desarrollo, no de uno validado.
  - La bibliografía va a `docs/bibliografia/Debye-Waller estatico y desorden posicional/`.

## 10. Política del watchdog

- **Dato:** el watchdog **nunca debe dispararse en medio de una rutina**, para no arruinarla.
- **Implica:**
  - Resuelve la intención de la decisión 8 del consolidado.
  - Sigue pendiente, a deliberar (nunca exento), cómo proteger ante una rutina **colgada** sin cortar una sana.

## 11. Documentos que describen código inexistente

- **Dato:** deben **archivarse y catalogarse** como:
  - **implementables**: una mejora que se planteó y se puede hacer;
  - **desconocidos**: no sabemos su origen ni su razón.
- **Implica:** resuelve la decisión 9 del consolidado (D-41, S-8).

## 12. Referencia para inconsistencias del sistema

- **Dato:** PySpectrum legacy y PyPrinting legacy funcionaban con normalidad; tenían bugs, pero no eran bloqueantes.
- **Implica:** ante una inconsistencia de sistema o de hardware, el comportamiento del legado es la referencia de funcionamiento. Una afirmación de la auditoría que implique que el legado no podía funcionar debe revisarse antes de aceptarse.

---

# Segunda ronda (2026-09-27, después de `TRIAGE_TEORICO.md` y `TRIAGE_SISTEMA_VS_LEGADO.md`)

Mismo criterio: son datos de primera mano y prevalecen sobre el informe y sobre los triages.

## R2-1. Líneas de obturadores (X-01)

- **Dato:** la configuración vigente del banco es:
  - 532 nm → `line11`;
  - 637 nm → `line8`;
  - 592 nm → `line9`;
  - 808 nm → `line10`.

  Sólo la línea 11 tiene la polaridad invertida.
- **Implica:** coincide exactamente con `config.py` (`SHUTTER_CHANNELS`, `SHUTTER_POLARITY`) desde `b91c743` (2026-08-27).
  - Los mapas de los dos legados (637 nm en `line11`) corresponden a un cableado anterior.
  - X-01 queda **cerrado**: 3.0 opera el láser que dice operar.

## R2-2. Versión en producción

- **Dato:** la PC del laboratorio corre el commit **`7f5d10a`** (2026-09-09).
- **Implica:**
  - `7f5d10a` es **anterior** a `6abbbfc` (2026-09-19), que introdujo la tarea continua de la traza. **C-01 no está en producción**: la traza del banco hace una lectura finita por tick, la que funciona, y eso explica que "PyPrinting 3.0 imprime bien".
  - C-01 existe sólo en `main`, que lleva 47 commits sin desplegar.
  - **Regla: no desplegar `main` en la PC del laboratorio hasta corregir C-01** y pasar el Grupo E de `PRUEBAS_BANCO_PENDIENTES.md` (bloque `DEC-036`).

## R2-3. Obturador de 532 nm al encender (C-09, `BANCO-16`)

- **Dato:** el controlador tiene una sola conexión BNC (se supone que no tiene alimentación aparte). Al encender todo, el obturador parece quedar cerrado; el investigador lo confirma en el banco.
- **Implica:** `BANCO-16` sigue abierto, pero la observación previa es favorable. Queda por explicar cómo un servo activo en BAJO queda cerrado con la línea sin manejar, que cae a BAJO por el pull-down de 50 kΩ; el banco lo aclara.

## R2-4. Espejo de detección (`line7`)

- **Dato:** el espectrómetro **sólo recibe luz con el espejo abajo**.
- **Implica:**
  - Cualquier adquisición de espectro exige el espejo en *down*; la detección confocal y la Canon exigen *up*.
  - `Luminescence_ps` (baja el espejo para medir) es el uso correcto.
  - `Growth_ps` y `Luminescence_steps_ps`, que lo suben, sólo funcionaban si el estado guardado en archivo estaba invertido respecto de la posición real.

## R2-5. Estado del espejo desincronizado

- **Dato:** a veces el control del espejo queda "atrasado", sobre todo cuando el programa se cuelga y se cierra a la fuerza; con dos clics se regulariza.
- **Implica:**
  - Confirma que el actuador es un **conmutador** (el mismo pulso cambia de posición) y que el software no conoce la posición real.
  - C-08, reformulado sin la premisa del notch, sigue en pie: hace falta persistir el estado (el legado lo guardaba en `flipper_notch532_status.txt`; 3.0 lo perdió) y ofrecer una resincronización explícita.

## R2-6. Canal `ai3` (C-44)

- **Dato:** el investigador no está seguro; lo revisa en el banco. Pendiente de banco.

## R2-7. Contrapropagante

- **Dato:**
  - TOP y BOT son los fotodiodos **del láser elegido**.
  - El objetivo es que un solo movimiento de la platina dé dos escaneos, uno con cada fotodiodo.
  - Se hará lo más práctico.
- **Implica:** reutilizar los módulos de confocal, traza y foco en vez de duplicarlos, con la lectura de los dos fotodiodos del láser elegido en una sola pasada. Corrige CP-1, en el que el trigger indexado por canal físico lee el fotodiodo del BS.

## R2-8. Rutina colgada

- **Dato:** preferencia por la opción **(b)**: la rutina emite su propio latido de vida, y el watchdog corta sólo si ese latido se detiene.
- **Implica:** el mecanismo se diseña en la tanda b1 (política del watchdog, nunca exento).

## R2-9. Offsets del Shamrock

- **Dato:**
  - Offset del detector = **0**; offset de la red = **87**.
  - Sería ideal modificar la rutina actual de láser + filtro de densidad para calibrar los dos offsets.
- **Implica:**
  - Es el respaldo previo al primer arranque de PySpectrum 3.0. Contrasta con los valores inventados que el código escribe en cada arranque: red 1 = 12, red 2 = −35, detector 5 (C-04).
  - **Falta saber a qué red corresponde el 87** y cuál es el offset de la otra.

## R2-10. Calibración de λ

- **Dato:** se calibra con el láser de **532 nm**, aproximadamente **cada 2 meses**.

## R2-11. Uso del Shamrock en el legado

- **Dato:**
  - La ganancia EM no se bajaba a mano antes de ir a orden cero, porque el orden cero casi nunca se usaba.
  - **Sí se usa la entrada lateral.**
- **Implica:** C-03 (caminos al orden cero sin diálogo) es de riesgo bajo en la práctica, pero sigue siendo un defecto. El puerto de entrada *Side* coincide con el registro de Solis (C-07).

## R2-12. Termometría (C-12)

- **Dato:** **sí**, la termometría S/AS se calcula siempre relativa a un espectro de referencia a una T₀ conocida.
- **Implica:**
  - Con el cociente de cocientes, el prefactor (ω³ o ω⁴) y la respuesta del instrumento η(λ) se cancelan para la misma banda. El punto (a) de C-12 deja de ser un sesgo **si el código implementa el método relativo**.
  - La auditoría encontró que `calculate_photothermal_temperature` calcula una T absoluta con ω⁴. El código debe implementar el método del laboratorio (relativo a T₀), además de corregir el error de nombres de `static_raman.py:698`.

## R2-13. Deriva

- **Dato:** se usa el valor de Martínez, **30 nm/min** (§3.5, p. 75, medido con PyPrinting), hasta volver a medir en el banco.

## R2-14. Fuerza iónica

- **Dato:** **0.5 mM es el protocolo más actual**; 1.5 mM es el publicado.
- **Implica:** la longitud de Debye es ≈ 13.6 nm con el protocolo actual y ≈ 7.9 nm con el publicado. Los documentos deben citar ambos, indicando cuál es el vigente.

## R2-15. Honeycomb impreso

- **Dato:** hay muestras honeycomb impresas con la base **(⅓, ⅓)**, diseñadas con la herramienta de esta suite, y salieron bastante bien.
- **Implica:**
  - La base canónica del generador es (⅓, ⅔), en `core/lattice_generator.py:59-70`, igual en `7f5d10a` y en `main`, y con γ = 60° arma dímeros. La GUI permite editar u y v, así que esas muestras se hicieron con la base corregida a mano.
  - **No hace falta revalidarlas.**
  - Hay que corregir la base canónica y los presets (C-02), en coherencia con la bibliografía: Guo, Hakala y Törmä, *PRB* 95, 155423 (2017).

## R2-16. Longitud de correlación

- **Dato:** **se adopta** ξ = 1/(π·FWHM_f), en frecuencia espacial ordinaria y con la resta del ensanchamiento por tamaño finito, como definición única (C-14, S-5).

## R2-17. Vacancias

- **Dato:** **p se reporta por conteo**, como "eficiencia de impresión", para impresiones de una pasada sin regresar a rellenar.
- **Implica:** se retira el estimador de Wilson `p_wilson_est` (C-15).

## R2-18. Silicio

- **Dato:** es **sólo verificación**, no patrón de calibración. También se usa **benzenotiol** como muestra de referencia.
- **Implica:** el valor certificado del Si no bloquea nada. Hay que documentar el benzenotiol como referencia Raman.

## R2-19. Rango de validación del Monte Carlo

- **Dato:** de **0 al límite de Lindemann, 0.3·a**, que es la zona que tiene sentido estudiar.
- **Implica:** el test de extremo a extremo de C-11 debe cubrir σ ∈ [0, 0.3·a]. El método sigue rotulado **experimental** (§9).

## R2-20. Inventario óptico

- **Datos:**
  - El objetivo de aire tiene **NA 0.5** (el código dice 0.40).
  - El láser verde es el **Excelsior-532-150-CDRH**.
  - El pinhole es de **50 µm con lente de 150 mm** (no 50 mm).
- **Implica:**
  - Con el objetivo de agua 60x, NA 1.0 (f = 3 mm con tubo de 180 mm), la magnificación al pinhole es 50 y el disco de Airy mide 32.5 µm a 532 nm: **el pinhole es ≈ 1.5 AU** (≈ 1.3 AU a 637 nm). Los 4.6 AU que resultan de la bibliografía corresponden a la lente de 50 mm.
  - D-11 se resuelve a favor de SYS-203 (Excelsior).

---

# Tercera ronda (2026-09-27): Ronda 1 de C-01, fase 1 y Ronda 2 del verificador

## R3 — C-01 (traza de impresión)

- **Producción:**
  - La PC del banco corre `7f5d10a`, y ahí la traza no cae a 0 V.
  - "Imprime bien" se refiere a 3.0 en ese commit.
  - Los nodos terminan en su mayoría en SUCCESS y algunos en TIMEOUT, lo que es típico por la distribución de probabilidad de captura.
  - No se vieron nodos salteados ni escaneos duplicados.
- **Paso 0:** **aprobada la reversión** de la traza y de Power BS a la lectura finita por tick de producción → `DEC-037`.
- **Diseño:**
  - La Ronda 2 diseña la **opción E**, con C como alternativa.
  - Las ventanas del criterio pasan a **segundos o ms**, no ticks.
- **Señal:** la captura da un escalón **hacia arriba**, de ≈ **×1.4 a ×2**.
- **Práctica de impresión:**
  - Preset "umbral + valor absoluto", modo legacy o legacy + voltaje absoluto.
  - Umbral 1.5, N_hold 3.
  - Umbral de caída 0.5: no se usa, pero se deja en 0.5.
  - Tiempo máximo 40 s.
  - Una captura tarda entre 1 s y 20 s en las peores condiciones.
- **Durante la impresión:** la cámara está en vivo y la traza se activa por defecto en su widget, lo que resulta útil así. Power BS se usa poco.
- **Hardware:**
  - La placa es PCIe.
  - Los obturadores son de fabricación propia, sin tiempo de respuesta medido.
  - Modelo y ganancia de los fotodiodos: pendiente de banco.
  - Hay canales analógicos libres.
  - Python 3.11.13; las demás versiones y el Δt entre filas se confirman en el banco.
  - Todo lo pendiente quedó reunido en el grupo F y el grupo G de `PRUEBAS_BANCO_PENDIENTES.md`.
- **Pregunta 2 (objetivo de latencia):** el investigador pidió que se la explique mejor. Sigue abierta.

## R3 — Fase 1 (`lab-invariants`)

- **A.** La sal del protocolo vigente de 0.5 mM es **NaCl**.
- **B.** El límite 0.3·a del Monte Carlo se toma **por componente** por ahora. Hay un experimento planificado para definirlo.
- **C.** Vacancias: p = (partículas planificadas − partículas contadas) / planificadas. No hay asignación a sitios ni radio de tolerancia.
- **D.** El iXon3 opera entre **−60 y −80 °C** (rango aceptable).
- **E.** Las impresiones y los escaneos confocales se hacen con el objetivo de agua (NA 1.0) con tubo Olympus, f = 3 mm. Confirma el ≈ 1.5 AU.

Aplicado en `lab-invariants.md` (filas del setpoint del Peltier, fuerza iónica, pinhole, p y Monte Carlo).

## R3 — Ronda 2 del verificador (fase 3)

1. **Nombre:** `provenance-verifier`, confirmado.
2. **Formato de marca:** `[fuente: …]` en línea más columna en las tablas, aceptado.
3. **Test de validez de marcas:** **falla**.
4. **Test de cobertura:** **sólo advierte**.
5. **Textos de la GUI:** **sí**, se revisan.
6. **Hook `pre-commit`:** **no** por ahora, pero queda **asentado para cambiarlo en el futuro**.
7. **Modelo del piloto:** el mismo que usa el asistente.
8. **Desacuerdos del piloto:** los resuelve el investigador.
9. **Modelo del flipper (¿MFF101?):** se verifica en el banco (`BANCO-22`).

**Regla del investigador:** toda respuesta que quede "para verificar en el banco" va junto a la batería de pruebas de banco (`docs/evidence/PRUEBAS_BANCO_PENDIENTES.md`), para resolver todas las dudas en una sola visita.

---

# Cuarta ronda (2026-09-27): Ronda 2 de C-01

## Decisiones de diseño

- **Q1, objetivo de latencia en dos niveles:** **sí**. El sistema garantiza ≤ 20 ms. La latencia del proceso la fija la ventana del preset: se arranca en P0 y se afina con datos de banco.
- **Q2, confirmación después de cortar:** **sí**. Se acepta cortar ante un posible transitorio y confirmar después con una lectura a baja potencia, a cambio de ventanas cortas.
- **Q3, signo del contraste:** lo **elige cada preset**.
- **Q4, falla de adquisición en un nodo:** respuesta "sí" a una pregunta de dos opciones (pausar la grilla o seguir al próximo nodo y reintentar en el Healing Pass). **Falta aclarar cuál.**
- **Q5, latido de vida (plazo 1.0 s) y liberación del bloqueo tras un corte:** "debería ser automático". Se interpreta que el bloqueo se libera solo, sin intervención del operador, cuando la rutina cortada terminó de limpiar. **A confirmar**, junto con el plazo de 1.0 s.
- **Q6, foco y confocal manuales:** bloqueados **mientras se imprime**; con la grilla **en pausa** sí se pueden usar.
- **Q7, tamaño de bloque:** **10 ms**.
- **Q8, N_hold en la GUI:** como persistencia **en ms**.
- **Q9, camino viejo de adquisición:** se borra después de **10 grillas sin incidentes**.
- **Q10, datos crudos:** **sí**. El ideal es guardar las trazas de impresión, los voltajes y las correcciones de deriva, para optimizar después las condiciones (por ejemplo, variando la concentración de NaCl) con PCA u otra herramienta. Queda como requisito de persistencia de datos (relacionado con C-20) y como herramienta de análisis futura.

## Práctica y hardware

- **Q11, presets:** los umbrales absoluto y relativo **se calibran con la traza** y dependen del tipo de partícula y del estado del setup (alineación). **Steps before/after están en 20/20**, no en 10/10.
  - Recalculado con `c01_ronda2/c01_criterion_sim.py` (umbral 1.5, N_hold 3, ticks de 47 ms, 20/20):
    - ×2: 100 % detectado, latencia mediana ≈ 0.60 s;
    - ×1.6: 100 %, ≈ 0.88 s;
    - ×1.4-1.5: la rama relativa no los detecta.
  - Con 10/10 las cifras eran ≈ 0.33 s y ≈ 0.49 s.
- **Q12, Healing Pass:** **sí**, ahora se usa.
- **Q13, otros láseres o contraste negativo:** **no**, hasta ahora.
- **Q14, fotodiodo BS:** mide **después** del obturador y del filtro, así que ve la apertura y el cierre.
- **Q15, TTL del obturador casero:** ¿va a un microcontrolador que genera el PWM? **Para verificar en el banco**, agregado a `BANCO-22`.
- **Q16, dos programas sobre la misma placa:** **sí**, corren a la vez. PySpectrum son **los ojos** (mediciones espectrales) y PyPrinting **el cuerpo** (mover la muestra para alinear al fino, el foco, los confocales, etc.).
  - En 3.0 está prevista la apertura de PyPrinting como ventana satélite dentro del proceso de PySpectrum (DEC-019).
  - Como PySpectrum 3.0 no se probó, en el banco probablemente corren PySpectrum **legacy** y PyPrinting 3.0 como dos procesos. El legado de PySpectrum usa el **cableado viejo** de obturadores. Agregado como `BANCO-35`.

## Aclaraciones (quinta ronda, 2026-09-27)

1. **Falla de adquisición en un nodo:** opción **(b)**. Se sigue con el próximo nodo, y el fallido se reintenta en el Healing Pass.
2. **Liberación del bloqueo tras un corte del watchdog:** **automática**, cuando la rutina cortada terminó de limpiar y los obturadores quedaron confirmados cerrados. El plazo de latido de **1.0 s** queda aceptado.
3. **Programas en uso:**
   - **Hoy el banco trabaja con PySpectrum legacy + PyPrinting legacy.**
   - PyPrinting 3.0 se probó por separado (R3).
   - PySpectrum 3.0 todavía no se probó, y tampoco la combinación PySpectrum 3.0 + PyPrinting 3.0.
   - **Pregunta abierta de seguridad:** ¿los legados que corren en el banco tienen los canales del cableado vigente?
     - En las copias que están en el repositorio y en `Obsidian_Vault/printing2/`:
       - PyPrinting legacy usa 532 → `line12` y 637 → `line11` (activo en BAJO).
       - PySpectrum legacy usa 532 → `line9`, 594 → `line10`, 637 → `line11` y 808 → `line12`.
     - Con el cableado vigente (R2-1: 532 → `line11`, activo en BAJO), el botón "637" de esas copias abriría el obturador de **532 nm**.
     - Se verifica en `BANCO-35`.

---

# Sexta ronda (2026-09-27): Ronda 3 de C-01 (GUI)

- **P1:** los 20/20 **se calibraron en el legado**, cuya cadencia es de ≈ 10 ms, así que equivalen a ventanas de ≈ 200 ms. Con 10/10 la detección de un evento no funcionaba siempre. **Habrá que volver a calibrar con los nuevos modelos de parada.** P0 reproduce el legado, no 3.0 a 47 ms por tick.
- **P2:** el preset se carga con un valor, pero el umbral **siempre se calibra con la traza**: se imprime una NP a mano y se mide el escalón con la traza. Esto respalda la herramienta "Medir escalón".
- **P3:** **no** se pausa por fallas de adquisición seguidas; para eso está el Healing Pass. Se mantienen las pausas de seguridad de `DEC-036`: interlock activo y cierre sin confirmar.
- **P4:** se acepta la recomendación. Una falla con el obturador ya abierto se reintenta en el Healing Pass sólo si la lectura a baja potencia no ve la NP.
- **P5:** **sí**. Con el Healing Pass apagado, el diálogo de fin ofrece reintentar las fallas.
- **P6:** sólo los valores; no se dibuja el objetivo de latencia en el gráfico.
- **P7:** **sí**. Mientras se imprime se bloquean los movimientos manuales de la platina y "Go/Set reference"; en la pausa quedan habilitados.
- **P8:** después de un corte del watchdog, la grilla queda en pausa y **se reanuda a mano**.
- **P9:** **sí**. El software cuenta las 10 grillas sin incidentes con un registro de salud, y el investigador lo firma.
- **P10:** **sí**. Por defecto se guardan los bloques de 10 ms; las muestras completas a 10 kS/s quedan como opción.
- **P11:** "voltajes" se refiere a los **del fotodiodo**. El de modulación del láser no hace falta si se guarda el del BS.
- **P12:** **sí**. "Extra info" pasa a campos tipados: NP y diámetro, NaCl en mM, sustrato, potencia en mW.
- **P13:** se acepta la recomendación. La confirmación a baja potencia viene activada por defecto sólo en los presets de ventana corta.
- **P14:** los campos que el modo no usa quedan **deshabilitados pero visibles**.
- **P15:** **sí**. El tope de `T_max` es de 60 s, y de 70 s en el Healing Pass.
- **Seguridad (BANCO-35):** **los legados que corren en el banco tienen los obturadores actualizados.** Las copias locales (`scratch/pyspectrum-legacy/`, `Obsidian_Vault/printing2/`) son más viejas que las del banco, al menos en los canales de obturadores. Sirven como referencia de algoritmos y comportamiento, pero no de configuración de hardware.
- El investigador commiteó todo lo anterior.

---

# Séptima ronda (2026-09-27): auditoría qa-ux de la Ronda 3 de C-01

- **P-H ("Cerrar Todos" durante un nodo):** **no pausa la grilla**. Interpretación: "Cerrar Todos" cierra los obturadores sin detener la rutina, y la parada es la **parada de emergencia** (P-E). La GUI debe dejar explícita la diferencia (rótulo, tooltip y manual), para que nadie espere que "Cerrar Todos" frene la grilla (QA-02). Un nodo interrumpido así sigue la regla P4: se reintenta en el Healing Pass sólo si la lectura a baja potencia no ve la NP.
- **P-E:** **sí**. Después de una parada de emergencia en PyPrinting, la grilla queda **detenida** y el bloqueo lo reconoce el operador. PyPrinting tiene que tener su **propia parada de emergencia** (Ctrl+E / F12), que hoy sólo existe en PySpectrum (QA-01, QA-03).
- **P-C:** en el legado el Umbral es **1.5** y el Umbral down **0.5**, igual que en 3.0.
- **P-D:** se acepta la recomendación. Con **5 nodos seguidos sin captura** se muestra un aviso, sin pausar.
- **P-F:** los presets "AgNP 80 nm — Nanodímeros" y "Grilla Extensa 10×10" (`stop_mode = 3`) son el modo **Confocal reescalado**.
- **P-G:** **hoy no** se ajustan la potencia del 532, el filtro ni el espejo durante una grilla. Se bloquean durante el nodo y quedan libres en la pausa, igual que la platina.
- **P-J (separador decimal):** **punto**, por el teclado numérico, independientemente de la configuración regional de Windows (QA-12).
- **P-K:** el modo dímeros **no se usa hace mucho**. Queda fuera del rediseño de C-01: se conserva y no se rediseña.
- **P-L:**
  - La **concentración de NaCl** es de cada lote, pero **se ingresa en cada impresión**.
  - La **potencia en la pupila** se mide **en cada sesión**: se ingresa una vez por sesión y vale para toda la sesión.

---

# Octava ronda (2026-09-27): preguntas de la versión 2 del diseño de la GUI de C-01

- **Q-1:** la cadencia real, sacada de los `NP_xxx.txt`, se mide **en el banco**. Queda en `BANCO-24`, ampliado a los archivos del legado y de 3.0.
- **Q-2:** el tiempo máximo en el legado es **40 s**.
- **Q-3:** las rachas de nodos que terminan por caída de señal o sin escalón dan un **aviso**, sin pausar.
- **Q-4:** después de rearmar tras una parada de emergencia, la grilla se **retoma desde el nodo pendiente**.
- **Q-5:** **sí**. Cuando PyPrinting corre como satélite de PySpectrum hay **una sola parada de emergencia** para los dos programas.

---

# Novena ronda (2026-09-27): segunda pasada de qa-ux sobre la v2 del diseño de la GUI de C-01

- **P-a:** si "Cerrar todos" cae durante el autofoco o el escaneo de deriva entre nodos, ese paso **se repite** antes de imprimir. Una corrección calculada sobre oscuridad no se aplica (N-3).
- **P-b:** se acepta la recomendación: una **espera visible de 3 s** antes de que abra el nodo siguiente, con Pausa y Parada a mano en el aviso. La grilla sigue igual (N-5).
- **P-c:** aclaración física: **el fotodiodo del BS está en el beamsplitter y ve la emisión transmitida**. El espejo de detección no lo afecta; sólo lo afecta el filtro de densidad.
  - Por eso la prueba de N-11 es válida: si el BS ve luz y el fotodiodo de detección no, el espejo está abajo o la detección está desalineada.
  - Qué hacer cuando pasa (cortar y avisar, o además pausar) no quedó contestado. El diseño lleva la recomendación (**cortar el nodo y pausar la grilla**), **a confirmar** en la Ronda 4.
- **P-d:** P0 **detecta las capturas tempranas**; no reproduce la demora de arranque del legado (N-7). La paridad con el legado vale para el régimen, no para el arranque.

## R4 — PySpectrum 3.0 para el banco (2026-09-28)

El investigador prioriza que PySpectrum 3.0 quede funcional para el banco. La v2 del verificador (DEC-038) y la Ronda 4 de C-01 quedan después.

1. **Orden de prioridad de las funciones:**
   - orden cero;
   - calibración;
   - Step & Glue;
   - Raman;
   - escaneo lineal 1D (que incluye Step & Glue);
   - luminiscencia;
   - después, las demás.
2. **Combinación en el banco:** PySpectrum 3.0 con PyPrinting 3.0.
   - En el código hay dos caminos. El lanzador `main.py` los arranca como **procesos separados**; sólo impide abrir juntos PyPrinting y el contrapropagante (`main.py:655`). PySpectrum, en cambio, abre PyPrinting **como ventana satélite dentro de su propio proceso** (`pyspectrum/window.py:208`, DEC-019).
   - El bus de subyugación es un objeto de Qt en memoria, así que sólo coordina el segundo camino.
   - Qué camino se usa queda **a confirmar** con el investigador.
3. **Offsets:** se guardan en un archivo, por ejemplo la configuración, y se escriben al Shamrock sólo con una acción explícita. Valores actuales:
   - **red de 150 l/mm = 85**. Reemplaza al 87 de R2-9;
   - **red de 1200 l/mm = 0**, hay que medirlo en el banco;
   - **detector = 0**. Hay que idear un protocolo para calibrarlo.
4. **Exposición más larga:** hasta **10 s**, en Raman.
   - **Procedencia (2026-09-28):**
     - **PySpectrum 3.0 nunca se abrió en la PC del banco**, así que el equipo no recibió los offsets inventados que escribe su arranque (C-04, presente también en `7f5d10a`).
     - Los valores (150 = 85, 1200 = 0, detector = 0) se **leyeron en Solis**. Corresponden a una calibración hecha hace ≈ 1 mes (≈ 2026-08-28).
     - El 85 reemplaza al 87 que se dio el 2026-09-27.
5. **Adquisición por nodo en el legado:** **(a) una adquisición por nodo.** Cada espectro de una rutina de grilla era una sola exposición, tomada con el láser abierto; la rutina espera a que termine y lee ese mismo cuadro. Nunca se toma el último cuadro de la cámara corriendo en continuo.
   - **Implica:** las rutinas de 3.0 que leen el último cuadro sin esperar el fin de la exposición (AND-1: luminiscencia, crecimiento, dímeros, y C-10 en el mapa hiperespectral) se corrigen al esquema del legado: iniciar, esperar el cuadro y leerlo. Ese cuadro no puede ser uno de ceros por falla del driver.

**R4-A — Respuestas a la Ronda 1 del bloque A de PySpectrum (2026-09-28; `pyspectrum_A_ronda1/README.md`).**

1. **Calibración de λ.**
   - *Cómo se hace hoy:* en **Solis**, con el filtro notch puesto, mirando la leve emisión de 532 que el notch deja pasar (una gaussiana). Se mueve **a mano** el offset de cada red hasta que el pico coincida con 532 nm.
   - *Pedido:* una **rutina automática** que haga esto red por red.
   - No hay protocolo de calibración del detector.
2. **Offset del detector:** fijo en 0 por convención, y toda la corrección va en el offset de cada red. Es como se trabaja hoy.
3. **Orden cero:** se usa como **"espejo rápido"**. Pasar del orden cero al primer orden y medir es más rápido que hacerlo desde la posición espejo.
   - *Actualiza R2-11 ("casi nunca se usaba"):* es un uso **frecuente**.
   - *Implica:* la protección tiene que ser automática sobre el detector (ganancia EM 0 confirmada, exposición acotada) y no un diálogo de confirmación, que se volvería rutina.
4. **Step & Glue:**
   - *Uso:* con la **lámpara**, típicamente entre **500 y 900 nm**.
   - *Espejo:* lo sube y lo baja el operador, pero la rutina tiene que **leer el estado del espejo y advertir** si no está en la posición de medición (abajo).
   - *Salvedad técnica:* el espejo no tiene realimentación, así que "leer el estado" es leer el estado que lleva el software. Eso requiere la persistencia y la resincronización de C-08.
5. **Archivo de calibraciones:** se aceptan las dos cosas. Queda local a la PC del banco, fuera de git, con un registro histórico. Escribir offsets al equipo requiere confirmación doble.
6. **Arranque de la cámara:**
   - el enfriador se enciende solo, a **−60 °C**;
   - ventilador en **low**, con una **opción para pasarlo a high**;
   - velocidad vertical como el legado (`vsspeed` 2, 1.9 µs).
7. **Convivencia y cambios:**
   - Solis y el legado siguen en uso **por ahora**. La meta es abandonar los dos, combinando en 3.0 los experimentos del legado con la versatilidad de Solis.
   - **La cámara se desmontó alguna vez.**
8. **Hardware:**
   - el Shamrock va por **USB propio**;
   - la ranura es **bilateral** (cierra hacia el centro);
   - **no** hay lámpara de calibración;
   - el láser de 532 nm es de **diodo**.
     - *Contradicción:* `PRUEBAS_BANCO_PENDIENTES.md` (BANCO-22, D-11) lo registra como Excelsior-532-150-CDRH, un modelo que es DPSS. La descripción del investigador prevalece. Se anota para confirmarlo en la etiqueta: el tipo de láser define cuán estable es su λ como referencia.
   - Obturador propio del Shamrock u obturador interno del iXon: sin respuesta, va al inventario (BANCO-22).
9. **Exactitud requerida:** no hay criterio todavía, porque es una fase exploratoria. Se usan como provisorios los del experimentalista (≤ 0.5 px con la red de 150, ≤ 1 px con la de 1200) y se los rotula así.
10. **Platina al abrir PySpectrum:** va a home, como hoy.
11. **Orden de las pruebas:** primero el Grupo E con los láseres apagados (BANCO-15 a BANCO-19) sobre `main`, y después el bloque A en el banco.

**R4-B — Respuestas a la Ronda 2 del bloque A (2026-09-28; `pyspectrum_A_ronda2/README.md`).**

1. **Calibración automática.**
   - Es una **rutina independiente** que se ejecuta desde la pestaña Calibraciones.
   - Guarda los valores, y **PySpectrum los lee en cada inicio**.
   - *Interpretación, **confirmada por el investigador**:* "leer al inicio" significa cargar el archivo, compararlo con el equipo y aplicar la corrección fina por software, no escribir al Shamrock al arrancar. El offset entero se escribe al equipo sólo desde la rutina, con la transacción de doble confirmación.
2. **Corrección por debajo de un paso:** se acepta la recomendación. El offset entero va al equipo, que es lo que ven todos los programas. El resto se guarda sólo en PySpectrum, marcado como corrección por software.
3. **Orden cero:**
   - *Uso:* ver las muestras para ubicarse espacialmente, y ver la posición del láser (con filtro de densidad o notch) para centrarlo en la ranura.
   - *Obturadores:* al entrar al orden cero se **cierran todos**, pero el operador **puede abrir a voluntad** los que necesite. La ganancia EM sigue bloqueada en 0 mientras la red esté en condición especular.
4. **Live y ganancia al pasar por el orden cero:** se acepta la propuesta. El Live se reanuda solo con ganancia 0 y exposición acotada, y la ganancia no vuelve sola al primer orden.
   - *Aclaración:* el Live tiene que poder verse **en cualquier configuración**: orden cero, espejo o cualquier red.
5. **Latido en Step & Glue:** a veces se usa con un láser abierto, así que **la rutina renueva el latido**.
6. **Cierre de PySpectrum:** la platina va a **(50, 50, 10)**, que es `config.PI_HOME_POS`. Así, al volver a encenderse y conectarse, no se mueve. Cerrar el satélite PyPrinting no toca la platina (propuesta de la Ronda 2).
7. **"Reconectar cámara" del tablero:** se mantiene, **con aviso**.
8. **Velocidad horizontal de lectura:** 13 MHz por defecto, **modificable** dentro de lo que la cámara permita.
9. **Tope de exposición del driver:** 60 s.
10. **Topes de offset:** se acepta la recomendación. No hay tope rígido, porque la transacción ya protege: diff, doble confirmación, respaldo y relectura.
    - Un cambio de más de ±50 pasos respecto del valor actual pide una **tercera confirmación**, que muestra el cambio estimado en nm.
    - El umbral se ajusta cuando BANCO-40 mida cuántos píxeles mueve un paso.

**Ronda 2 del bloque A: APROBADA** (2026-09-28). Se implementan los pasos 1 a 3 (motor y seguridad, cada uno con un test que falla primero). En paralelo se convoca la Ronda 3 (GUI) para los pasos 7, 8, 10, 11, 12 y 14.
11. **Referencia de λ:** se puede **medir sin el notch**, con el 532 atenuado. Sirve para comparar la fuga por el notch con el láser atenuado.
    - Quedaron sin respuesta la λ medida del láser y la posibilidad de un tubo fluorescente (Hg 546.07 nm) en la ranura. Se anotan en el banco.

**R4-C — Respuestas a la Ronda 3 del bloque A (2026-09-28; `pyspectrum_A_ronda3/gui_design.md` §7).**

1. **Exposición para mirar la muestra en orden cero:**
   - en Solis se usa **de 0.1 s a 0.5 s**, pero depende mucho de la muestra y **no hay un valor estándar**;
   - *implica:* el "espejo rápido" no impone 10 ms. Arranca con un valor por defecto que el operador ajusta, y lo que queda fijo es la ganancia EM bloqueada en 0 mientras la red esté en condición especular.
2. **Abrir un láser con el filtro de densidad en potencia alta en condición especular:** **se avisa**, sin bloquear.
3. **Step & Glue con láser:** el obturador **lo abre el operador**, y la rutina no lo abre. La rutina renueva el latido (R4-B-5).
4. **Restaurar un offset anterior desde el historial:** **no**, para eso se vuelve a calibrar.
5. **Calibración automática:** **una escritura por confirmación**. Cada escritura pasa por la transacción completa, y no hay sesiones con varias escrituras autorizadas.
6. **Corrección fina (por debajo de un paso):** se guarda **aparte**, como metadato con procedencia, y no dentro del eje λ de cada espectro. El dato crudo queda intacto.

**R4-D — Respuestas a la auditoría QA/UX de la Ronda 3 (2026-09-28; `pyspectrum_A_ronda3/qa_ux_audit.md` §8).**

1. **Centrar el láser en la ranura en orden cero:** se mira con un **notch que el operador pone físicamente a la entrada**. No está automatizado, así que el software no puede saber si está puesto.
   - *Implica:* "Restituir ganancia" con un láser abierto le pide al operador que confirme "notch puesto" y no lo da por supuesto (H-05).
2. **Dos exposiciones recordadas por sesión**, una para orden cero y otra para primer orden, cada una restituida al cambiar de modo: **sí**. La primera entrada al orden cero de la sesión arranca en **0.1 s**. La ganancia sigue sin volver sola (R4-B-4).
3. **Escritura cuya relectura falla o no coincide:** **se recurre al historial**, es decir, se ofrece volver al último valor válido registrado, el respaldo de esa transacción.
   - Esa vuelta es una escritura más, con su transacción completa (R4-C-5).
   - Es el único caso en que se escribe un valor del historial, porque R4-C-4 excluye restaurarlo en cualquier otra situación.
4. **Calibración automática:**
   - exposición fija de **0.10 s**;
   - **duración máxima de 10 min** para la rutina completa;
   - si se alcanza el tope, la rutina se detiene, cierra el obturador y registra el resultado parcial como no aceptado.

**Ronda 3 del bloque A:** el diseño (`gui_design.md`) y su auditoría (`qa_ux_audit.md`, MINOR_UX_POLISH_NEEDED) quedan cerrados con las correcciones H-01 a H-34 y las respuestas R4-C y R4-D. Sigue la Ronda 4: primero la reconciliación, después la implementación.

**R4-2b — Lanzamiento (2026-09-28).** Si PySpectrum ya se lanzó, el lanzador `main.py` bloquea abrir PyPrinting, que sólo se abre desde el menú Herramientas de PySpectrum. La razón es evitar dos procesos sobre el mismo hardware.
- **Implementado** (`main.py::_HARDWARE_SCRIPTS`, `tests/test_launcher_process_exclusion.py`). En modo laboratorio corre uno solo de los tres programas de hardware (PySpectrum, Microscopio Derecho y Contrapropagante), y cada uno una sola vez.
- **Extensión:** además de lo pedido, también se bloquea lo inverso (PySpectrum con PyPrinting suelto abierto) y una segunda instancia del mismo programa. En los tres casos habría dos procesos sobre la misma placa.
- El modo seguro no bloquea nada.

## Decisiones que siguen abiertas después de la segunda ronda

- **Offsets:** resuelto en R4-3. La red de 150 l/mm vale 85. Faltan medir en el banco la red de 1200 l/mm y definir el protocolo del detector.
- **Banco:**
  - canal `ai3` (R2-6);
  - estado del obturador de 532 nm al encender (R2-3);
  - posición del espejo al encender;
  - deriva;
  - demás ítems de `PRUEBAS_BANCO_PENDIENTES.md`.
- **Autorización** de las sesiones de banco.
