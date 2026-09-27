# Auditoría documental L2 — Seguridad y control de hardware

**Repositorio:** PyPrinting 3.0 / PySpectrum 3.0 (`C:\Users\josel\Documents\Obsidian_Vault\printing3`)
**Fecha:** 2026-09-26 · **Alcance:** SYS-102, SYS-103, SYS-201, SYS-202, SYS-203, SYS-204, SYS-205, MOD-04, MOD-05, MOD-13
**Método:** afirmaciones contrastadas contra el código real (`core/nidaq.py`, `core/shutters.py`, `config.py`, `core/nanopositioning.py`, `core/hardware_manager.py`, módulos y tests citados), contra las fuentes primarias locales (tesis de Gargiulo 2017 y Martinez, BNC-2110.pdf, SDK de Canon en `ESDK_CANON/`, tablas de error de los paquetes oficiales `nidaqmx` y `pipython 2.13.0.2` instalados en `.venv`) y contra documentación del fabricante en la web. No se modificó ningún archivo del repositorio.

**Veredictos:** CONFIRMADO / CONTRADICHO / SIN FUENTE / CITA ERRÓNEA / REQUIERE BANCO.
**Severidad:** CRÍTICA (seguridad, código o mediciones) · ALTA (número o fórmula científica errónea) · MEDIA (cita o afirmación sin respaldo usada como base) · BAJA (imprecisión menor).

## Hechos de referencia establecidos en esta auditoría (usados en varias filas)

| Hecho | Evidencia |
| :--- | :--- |
| Obturadores en `Dev1/port0/line11, line8, line9, line10` (532, 637, 592, 808 nm), **no** `line0:3` | `config.py:65-67` (`SHUTTER_CHANNELS = [11, 8, 9, 10]`), `core/nidaq.py:238-241` (`f"{NIDAQ_DEVICE}/port0/line{ch}"`) |
| Polaridad: 532 nm activa en BAJO (abrir = `False`, cerrar = `True`/ALTO); 637/592/808 nm activas en ALTO | `config.py:67` (`SHUTTER_POLARITY`), `core/nidaq.py:333,360` |
| Flipper notch 532 es **digital** en `Dev1/port0/line7`, pulso de 3 ms | `config.py:69` (`FLIPPER_532_CHAN = 7`), `core/nidaq.py:311-313,489-492` |
| Flipper de potencia: `ao0` = Up/Low, `ao1` = Down/High, pulso de **5 V durante 5 ms** | `config.py:70-71`, `core/nidaq.py:423,433,459,469` (`time.sleep(0.005)`) |
| Láser 532 en `Dev1/ao2`, recortado a **1.0–5.0 V** por software | `config.py:49-51`, `core/nidaq.py:556` |
| Placa DAQ: **NI PCIe-6353** (una sola fuente primaria local); consistente con `RATE_SINGLE_CHANNEL = 1.25e6` y `RATE_MULTICHANNEL = 1.0e6` de `config.py:62-63` | Tesis L. Martinez, §3.4 ("placa de adquisición DAQ (National Instrument PCIe-6353)") |
| Láseres del montaje: 405 nm Cobolt, **532 nm Laser Quantum Ventus**, 592 nm MPB, **640 nm MPB**, 808 nm Thorlabs + Lumics | Tesis Martinez §3.1; Gargiulo 2017 §4.1 (405 Cobolt, 532 "Laser Ventus", 640 MPB) |
| Platina **PI P-545** con controlador **PI E-517**; recorrido 200 µm en XY (Z: 200 µm según Gargiulo, 50 µm según Martinez) | Gargiulo 2017 §4.1 y §4.2 ("PI P-545 ... range of 200 µm in the three axes"; "control driver (PI E-517)"); Martinez §3.1 ("P-545 ... 200 µm en XY y 50 µm en Z") |
| Objetivo: Olympus LUMPLFLN 60XW, inmersión en **agua, NA = 1.0** (alternativa: aire 20x, NA = 0.5) | Tesis Martinez §3.1 |
| DAQmx `-200088` = `INVALID_TASK` ("Task specified is invalid or does not exist"); "resource is reserved" es `-50103` | `.venv/.../nidaqmx/error_codes.py:1515,1739`; NI KB kA00Z0000004AE6SAM y kA00Z000000P8kmSAC |
| GCS `-1004` = "Controller sent unexpected response"; "Position out of limits" es el error **7**; pipython lanza `GCSError` también para `-7` COM_TIMEOUT y para `-1004` generado por bytes corruptos en el bus | `.venv/.../pipython/pidevice/gcserror.py:12-19,86,227,1043`; `gcsmessages.py:113,213,230` |

---

## SYS-201 — Seguridad óptica, watchdog y obturadores

| ID | Documento:línea | Afirmación | Veredicto | Severidad | Fuentes | Corrección propuesta |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 201-01 | SYS-201:29, 31, 109 | "Watchdog de Hardware / Software" que protege ante "bloqueo del hilo de la GUI, congelamiento del sistema operativo" | CONTRADICHO | CRÍTICA | `core/nidaq.py:127-153` | Sólo existe un hilo Python (`daemon=True`) dentro del mismo proceso. No hay watchdog de hardware DAQmx. No actúa si el proceso muere, si una extensión C retiene el GIL o si el SO se cuelga; en esos casos las líneas quedan en su último valor. Reescribir como "watchdog de software" y declarar sus límites. Evaluar el temporizador watchdog de hardware de la serie X (REQUIERE BANCO). |
| 201-02 | SYS-201:100 | Cierre de emergencia = "Escritura Digital Ceros: line0:3 = 0" | CONTRADICHO | CRÍTICA | `config.py:66-67`; `core/nidaq.py:360,384-390` | Las líneas son port0/line11, 8, 9 y 10. Cerrar el 532 nm escribe ALTO (`True`), no 0. Poner las líneas a cero *abriría* el obturador de 532 nm. |
| 201-03 | SYS-201:205 | Obturadores en "`Dev1/port0/line0:3`" | CONTRADICHO | CRÍTICA | `config.py:66`; `core/nidaq.py:238-241` | Reemplazar por `port0/line11,8,9,10` con la tabla láser→línea→polaridad. El mismo error figura como 📄 en `.claude/shared/lab-invariants.md` §2 y en el prompt del agente `instrumentation` ("shutter lines drop to ground"). |
| 201-04 | SYS-201:312 | "La interfaz refleja fielmente el estado real de la tarjeta NI en todo momento" | CONTRADICHO | CRÍTICA | `core/nidaq.py:333-352, 360-381`; `core/shutters.py:240-258`; `core/hardware_manager.py:101-109` | (a) `_shutter_signal` se cambia **antes** de escribir, y si la escritura falla sólo se imprime el error. (b) `close_shutter` anula el deadline del watchdog aunque la escritura haya fallado, y el watchdog se desarma con el láser físicamente abierto. (c) Con "NI-DAQmx (Dev1)" aislado, `close_shutter`/`close_all_shutters` no escriben nada (L365-367). (d) La etiqueta del dock calcula `any_open` desde sus casillas, no desde `_shutter_signal`, así que no ve los obturadores que abre una rutina. Corregir el código (estado sólo tras escritura confirmada, reintento, no desarmar si falla) y documentar. |
| 201-05 | SYS-201:97-103 | El watchdog llama a `_emergency_shutdown` y así preserva el flipper | CONTRADICHO | MEDIA | `core/nidaq.py:137, 215-222` | El watchdog llama a `close_all_shutters()`. `_emergency_shutdown` es el hook `atexit` y **sí** llama a `up_flipper()` (pasa a Low Power al salir). Corregir el diagrama. |
| 201-06 | SYS-201:109 | `threading.Thread(target=self._run, daemon=True)` | CONTRADICHO | BAJA | `core/nidaq.py:152` | Es `threading.Thread(target=_watchdog_loop, daemon=True, name="ShutterWatchdog")`, a nivel de módulo, no una clase. |
| 201-07 | SYS-201:91 | Poll cada 100 ms | CONFIRMADO | — | `core/nidaq.py:130`; lab-invariants ✅ | — |
| 201-08 | SYS-201:116 | El heartbeat extiende el plazo: `deadline = max(deadline, t + ext)` | CONTRADICHO | MEDIA | `core/nidaq.py:168` | El código **sobrescribe** (`deadline = now + max(0.1, eff)`), así que un heartbeat corto puede *acortar* un plazo largo. Documentar la semántica real o cambiar el código. |
| 201-09 | SYS-201:117 | El heartbeat no escribe en la tarjeta | CONFIRMADO | — | `core/nidaq.py:156-168` | — |
| 201-10 | SYS-201:123, 128-158 | Política global `_default_timeout_s = 30.0`, centinela `_SENTINEL`, `set_default_shutter_timeout` y `heartbeat_shutter` (fragmentos) | CONFIRMADO | — | `core/nidaq.py:104-168`; lab-invariants ✅ | — |
| 201-11 | SYS-201:164-175 | `Backend.set_autoclose_timeout` propaga a la política global y re-arma si hay algo abierto | CONFIRMADO | — | `core/shutters.py:411-425` | — |
| 201-12 | SYS-201:186-192 | Opciones 30/60/300/600 s y "Sin límite" (None) | CONFIRMADO (valores) | BAJA | `core/shutters.py:350-355` | Las etiquetas reales son "30 s (Predeterminado)" y "Sin límite (Alineación)". Falta documentar la casilla "Auto-cierre": desmarcada equivale a None (L220-223). |
| 201-13 | SYS-201:195-198 | Indicadores "🛡️ ACTIVO (29s)", aviso "⚠️ CIERRA EN: 5s" con menos de 10 s, "🔓 ALINEACIÓN CONTINUA" | CONTRADICHO | MEDIA | `core/shutters.py:240-258` | No existe el aviso de menos de 10 s. Los textos reales son "⏱️ Auto-cierre en: N s", "⏱️ Auto-cierre armado (30 s)" y "⚠️ MODO ALINEACIÓN (Sin auto-cierre)". Además, la línea 198 está truncada ("Indica explícitamente### 4.3"). |
| 201-14 | SYS-201:200-202 | Puente `register_watchdog_callback` → `watchdog_triggered_signal` → `_on_watchdog_triggered` con `blockSignals` | CONFIRMADO | — | `core/shutters.py:63-96` | — |
| 201-15 | SYS-201:205 | Flipper con filtro ND de "OD = 2.0–3.0" | SIN FUENTE | BAJA | Tesis Martinez §3.1 (sólo "filtro neutro") | Medir o citar el filtro instalado. |
| 201-16 | SYS-201:208 | El watchdog cierra sólo obturadores y no toca el flipper | CONFIRMADO | — | `core/nidaq.py:133-150` | — |
| 201-17 | SYS-201:209 | Los callbacks del flipper están protegidos por `_flipper_lock` (reentrante) | CONTRADICHO | MEDIA | `core/nidaq.py:96, 198-207, 402-409` | No existe `_flipper_lock`: la lista es un `list` sin lock. Además, `up_flipper`/`down_flipper` notifican a la GUI y fijan `_flipper_high_power` **antes** de escribir en la tarjeta (estado optimista). |
| 201-18 | SYS-201:210 | `powerbutton.clicked` y `update_power_ui` sin recursión | CONFIRMADO | — | `core/shutters.py:163-170, 296` | — |
| 201-19 | SYS-201:225-235 | La traza renueva `heartbeat_shutter(30.0)` cada 30 cuadros; F2 cierra el obturador | CONFIRMADO | — | `modules/trace.py:612, 680-681` | — |
| 201-20 | SYS-201:249-254 | Cobertura de heartbeat en confocal, focus y contrapropagante | CONFIRMADO | — | `modules/confocal.py:548,795,1007,1035,1055,1077`; `modules/focus.py:240,266,325,379`; `contrapropagante.py:766,791,815,842` | El latido del reintento `while flag` vive en `_ramp_lin_with_retry_cap` (focus.py:240), no en `_focus_autocorr_lin`. |
| 201-21 | SYS-201:260 | "Todas las renovaciones periódicas nuevas usan `heartbeat_shutter(30.0)` explícito" | CONTRADICHO | BAJA | `modules/confocal.py:548...`; `contrapropagante.py:766` | Confocal y contrapropagante usan `heartbeat_shutter()` sin argumento (política global, ANOM-CONFOCAL-02); sólo focus y trace usan 30.0. Actualizar la nota. |
| 201-22 | SYS-201:286 | La prueba verifica el corte "en tiempo estricto (±50 ms)" | CONTRADICHO | MEDIA | `tests/test_concurrency_watchdog.py:55-71` | La prueba abre con 0.5 s y comprueba a los 0.8 s: tolerancia de +300 ms, en SAFE_MODE y sólo sobre el flag en memoria, no sobre la línea física. |
| 201-23 | SYS-201:284-285 | "1.000 operaciones... 0 colisiones, 0 excepciones, 0 deadlocks" | CONTRADICHO (garantía) | MEDIA | `tests/test_concurrency_watchdog.py:22-53` | Bajo pytest la función devuelve `False` en vez de fallar con `assert`, así que no puede fallar nunca. Además corre con mocks (SAFE_MODE) y no ejercita el flipper. Convertir a `assert not errors`. |
| 201-24 | SYS-201:297 | Pulso del flipper "5 V × 100 ms" | CONTRADICHO | ALTA | `core/nidaq.py:423,433,459,469` | El código emite 5 ms. Ver SYS-202 (202-09/10) para el requisito real de la montura. |
| 201-25 | SYS-201:303 | Suite integral "49 / 49" | CONTRADICHO (inconsistente) | BAJA | SYS-103:297 afirma "56/56" para la misma suite | Quitar los conteos fijos o regenerarlos al publicar. |
| 201-26 | SYS-201:43-45 | Objetivo de aceite con NA = 1.3–1.4; $w_0 \approx 0.61\lambda/\text{NA} \approx 250$ nm | CONTRADICHO | ALTA | Tesis Martinez §3.1 (60XW, agua, NA = 1.0) | $0.61\lambda/\text{NA}$ es el radio del primer mínimo de Airy, no la cintura gaussiana $1/e^2$. Con NA = 1.0 la cintura es mayor (Martinez: haces de ~300 nm de diámetro) y la irradiancia de §2.1 sale ≈1.7× sobreestimada. Rehacer con el objetivo real. |
| 201-27 | SYS-201:48-52 | $A = \pi w_0^2 = 1.96\times10^{-9}$ cm²; $I_0 = 2P/(\pi w_0^2) = 1.02\times10^7$ W/cm² | CONFIRMADO (aritmética) | — | cálculo propio | La aritmética es correcta dadas las premisas; la premisa de NA es la que falla (201-26). |
| 201-28 | SYS-201:62-65 | $\Delta T = P_{abs}/(4\pi\kappa R)$ ≈ 1350 K | CONFIRMADO (fórmula y aritmética) | — | Govorov & Richardson, *Nano Today* 2, 30 (2007), doi:10.1016/S1748-0132(07)70017-8; Baffou & Quidant, *Laser Photon. Rev.* 7, 171 (2013), doi:10.1002/lpor.201200003 (ambas citas verificadas) | Fórmula estacionaria estándar (NP aislada en un medio homogéneo; ignora el sustrato de vidrio y el cambio de fase). La aritmética es correcta. |
| 201-29 | SYS-201:55 | $\sigma_{abs}(60\ \text{nm Au}, 532\ \text{nm}) \approx 3\times10^{-15}$ m² | CONTRADICHO (cálculo propio, confianza media) | ALTA | Mie propio (serie completa, script en `scratchpad/mie_check.py`), Au Johnson & Christy interpolado a 532 nm (n ≈ 0.54 + 2.23i; el índice se tomó de memoria, no de la tabla), agua n = 1.333: $Q_{abs}$ ≈ 3.5–3.9 → $\sigma_{abs}$ ≈ 1.0–1.1 × 10⁻¹⁴ m². Con el σ_ext resultante (1.3–1.4 × 10⁻¹⁴ m²) el coeficiente de extinción molar da ~3–3.6 × 10¹⁰ M⁻¹cm⁻¹, del mismo orden que el tabulado comercialmente para 60 nm | El valor citado es ~3.5× menor (≈ πR², es decir Q ≈ 1). Recalcular con una tabla dieléctrica citada. Con el valor corregido el ΔT de §2.2 sale todavía mayor, y la conclusión (vaporización) se refuerza. |
| 201-30 | SYS-201:67 | Tras "más de unos cientos de milisegundos" de irradiación se supera el espinodal | CONTRADICHO (física) | ALTA | Difusión térmica: $\tau \sim R^2/D_{agua} \approx (30\ \text{nm})^2/1.4\times10^{-7}\ \text{m}^2/\text{s} \approx 6$ ns | El estacionario térmico de la NP se alcanza en nanosegundos, no en cientos de ms. El watchdog (30 s) no protege contra sobrecalentamiento instantáneo, sólo contra exposición desatendida prolongada. Reformular la justificación. |
| 201-31 | SYS-201:67 | Espinodal del agua ≈ 300 °C a 1 atm | SIN FUENTE (valor plausible) | BAJA | — | Citar la fuente (p. ej. límite de sobrecalentamiento ~0.9 T_c). |

---

## SYS-205 — Resiliencia de la platina PI E-517 y tolerancia a fallas

| ID | Documento:línea | Afirmación | Veredicto | Severidad | Fuentes | Corrección propuesta |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 205-01 | SYS-205:30, 40 | Platina "E-517 (0.0–100.0 µm por eje)"; interlock físico [0, 100] µm | CONTRADICHO / REQUIERE BANCO | CRÍTICA | Gargiulo 2017 §4.1–4.2 (P-545 + E-517, 200 µm en los tres ejes); Martinez §3.1 (P-545, 200 µm XY y **50 µm Z**); ficha PI P-545.xC8S/xR8S (200×200×200 µm): https://www.physikinstrumente.com/en/products/nanopositioning-piezo-flexure-stages/pifoc-objective-pinano-sample-scanners-for-microscopy/p-545xc8s-pinano-cap-xyz-piezo-system-2015241/ | El E-517 es el controlador; la platina es una P-545. 100 µm es un límite de software (`config.py:57`), no el recorrido físico. Si el eje Z tiene 50 µm (Martinez), el recorte [0, 100] **no** protege Z. Consultar `TMN?`/`TMX?` por eje en el banco y usar límites por eje. |
| 205-02 | SYS-205:33, 64, 102-103, 146 | Un `GCSError` es un rechazo de firmware y, "por definición", prueba que la controladora está viva | CONTRADICHO | CRÍTICA | `pipython/pidevice/gcserror.py:12-19` (-1 COM_ERROR, -2 SEND, -3 REC, -4 NOT_CONNECTED, -7 COM_TIMEOUT); `gcsmessages.py:113,213` (`raise GCSError(...COM_TIMEOUT...)`); `interfaces/gcsdll.py:210ss` (errores del DLL como `GCSError`) | pipython reporta como `GCSError` los timeouts y las fallas de comunicación. Con `except GCSError` (`config.py:463,474,512`) una pérdida real de USB se clasifica como "conexión intacta": el `MOV` se descarta en silencio y `_pos` queda en el objetivo (L505-507). Así la pausa de §5 nunca se dispara y la grilla sigue con láseres. Distinguir por código: ≥ 0 = controladora; negativos de interfaz = comunicación. |
| 205-03 | SYS-205:66-68, 139 (test) | "`GCSError -1004` ('Position out of limits')" | CITA ERRÓNEA | CRÍTICA | `pipython/pidevice/gcserror.py:86,227,1043` | -1004 = "Controller sent unexpected response" (`PI_UNEXPECTED_RESPONSE`), que pipython genera ante respuestas corruptas del bus (`gcsmessages.py:230,291,339`). "Position out of limits" es el error **7**. Toda la justificación (y `tests/test_pi_stage_resilience.py:139`) parte de un código mal identificado. |
| 205-04 | SYS-205:109, 167, 199 | La única vía de desconexión es un `MOV` que falla tras la reconexión | CONTRADICHO | CRÍTICA | `config.py:318-320` (`is_physically_connected`), `533-539` (`qIDN`), `389-393` (`connect`) | `qIDN()` y `is_physically_connected()` también ponen `_connected = False` ante cualquier excepción. Como `qIDN()` se llama en cada lectura de posición (205-05), un solo fallo de `*IDN?` pasa a modo virtual. |
| 205-05 | SYS-205:35, 85-87, 169-185 | "Eliminación del spam de `*IDN?`" | CONTRADICHO | CRÍTICA | `core/nanopositioning.py:737, 750-751, 813`; `config.py:533-537` | `Backend.read_pos()` hace `pi.qIDN()` en **cada** lectura, y `move()` llama a `read_pos()` dos veces por paso. La consulta por USB sigue ocurriendo en cada refresco. Cachear el IDN al conectar. |
| 205-06 | SYS-205:185 | `IsConnected()` "verifica si el socket/handle USB sigue abierto" | CONFIRMADO en parte | MEDIA | PI GCS2 DLL SM151E (`PI_IsConnected`: "checks if there is a controller with an ID"): https://www.le.infn.it/~chiodini/allow_listing/pi/Manuals/PIGCS_2_0_DLL_SM151E210.pdf ; `pipython/.../gcsdll.py:363-365` | No genera tráfico (confirmado), pero por lo mismo no detecta un desenchufe físico: sólo valida que el ID exista en el DLL. `is_physically_connected()` no hace lo que su nombre promete. REQUIERE BANCO (desenchufar y observar). |
| 205-07 | SYS-205:187-199 | La auto-reconexión "reintenta el `MOV` original una vez" | CONTRADICHO (omisión) | CRÍTICA | `config.py:366-374, 440-450, 519-523` | `try_auto_reconnect()` → `connect()` ejecuta `SVO` + `MOV(PI_AXES, PI_HOME_POS = [50, 50, 10])` y espera hasta 3 s. Durante un escaneo, la platina salta al home y vuelve **con el obturador abierto**. Documentarlo y cerrar los obturadores antes de reconectar, o separar reconectar de homing. |
| 205-08 | SYS-205:118, 276 | "`pipython` no está instalado en el entorno de desarrollo/CI, por lo que `pi` siempre resuelve a `_MockPI`" | CONTRADICHO | BAJA | `.venv/Lib/site-packages/pipython` 2.13.0.2; `config.py:566` | `pi` depende de `SAFE_MODE`, no de pipython, y pipython está instalado. |
| 205-09 | SYS-205:120-133 | Recorte incondicional en `_PIController.MOV` y `_MockPI.MOV` | CONFIRMADO | — | `config.py:232-239, 496-503` | — |
| 205-10 | SYS-205:163-166 | Ante falla persistente, `qPOS` devuelve "la última posición conocida" y `qONT` asume on-target | CONFIRMADO (código) / riesgo no declarado | MEDIA | `config.py:476-481, 505-507` | La "última posición conocida" es el **objetivo comandado**: se escribe antes de que el `MOV` se ejecute y aunque sea rechazado. Asumir on-target habilita lecturas ópticas con la platina en movimiento. Declararlo como riesgo de medición. |
| 205-11 | SYS-205:150-163 | `_retry_read`: 2 reintentos a 20 ms | CONFIRMADO | — | `config.py:424-438` | — |
| 205-12 | SYS-205:207-222 | Pre-flight con δ = 3.0 µm, aborta antes de láser y platina, emite `gridRangeErrorSignal` | CONFIRMADO | BAJA | `modules/measurements.py:1979-2031` | Sólo verifica X e Y; no Z ni los `dx`/`dy` de dímeros. La corrección de deriva posterior puede superar el margen (el recorte del driver lo absorbe en silencio). |
| 205-13 | SYS-205:228-270 | Máquina de pausa/reanudación que preserva `i_global` y los logs | CONFIRMADO (código) | MEDIA | `modules/measurements.py:2087-2131` | Existe, pero su disparador (`pi.connected == False`) casi nunca se alcanza ante fallas reales (205-02). La reanudación vía `pi.connect()` re-homea la platina (obturadores ya cerrados en ese punto). |
| 205-14 | SYS-205:299 | Para mediciones nocturnas "no es necesario ningún cambio: las capas de defensa operan de forma transparente" | CONTRADICHO | CRÍTICA | `modules/measurements.py:2141-2147` | `_grid_move()` espera `pi.qONT()` **sin timeout** (`while not all(...): sleep(0.01)`): un eje que nunca llega a destino cuelga la rutina de impresión. Esto se suma a 205-02 y 205-07. Acotar el sondeo, como ya se hizo en `nanopositioning.py:776-780`. |
| 205-15 | SYS-205:50 | Commits `8644d40`, `4a22652` | CONFIRMADO | — | `git log` | — |
| 205-16 | SYS-205:276-287 | 18 pruebas en `tests/test_pi_stage_resilience.py` | CONFIRMADO (conteo) | MEDIA | `tests/test_pi_stage_resilience.py:139-197` | El doble de prueba simula la desconexión USB con `OSError` y el timeout con `OSError("bus busy")`, pero pipython real lanza `GCSError` (205-02). Las pruebas codifican el modelo de falla equivocado y por eso pasan. |
| 205-17 | SYS-205:288 | "Suite completa: 204 pruebas superadas" | SIN FUENTE | BAJA | — | Cifra no reproducible desde el documento; no se ejecutó pytest en esta auditoría (sólo lectura). |

---

## SYS-202 — Actuación del flipper de potencia y ciclo de vida DAQmx

Fuentes adicionales usadas en esta sección: manual Thorlabs *MFF101 and MFF102 Motorized Filter Flippers User Guide* (ETN012604-D03), https://www.thorlabs.com/images/TabImages/ETN012604-D02.pdf (copia leída: https://www.oxxius.ru/upload/iblock/735/6a5o210vdlz1qdno79fb2xjzme2js1jq/ETN012604_D03.pdf). Es una sola fuente primaria y **no está probado que el flipper instalado sea un MFF101**: las tesis sólo dicen "flipper motorizado". Además: ficha NI 6353 (374592d), https://download.ni.com/support/manuals/374592d.pdf, y `docs/bibliografia/BNC-2110.pdf`.

| ID | Documento:línea | Afirmación | Veredicto | Severidad | Fuentes | Corrección propuesta |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 202-01 | SYS-202:55, 62 | Obturadores en "Líneas digitales `Dev1/port0/line0:3`" | CONTRADICHO | CRÍTICA | `config.py:66`; ficha NI 6353 (pinout: P0.8–P0.11 están en el **conector 1**) | port0/line11, 8, 9, 10. Documentar también qué conector y qué bornera los exponen. |
| 202-02 | SYS-202:48, 109; 258 | Láseres "532 / 642 nm"; "obturadores estándar (488, 561, 642 nm)"; test P3 "cierra 532/642" | CONTRADICHO | ALTA | `config.py:65`; Martinez §3.1; Gargiulo §4.1 | En el laboratorio no hay láseres de 488 ni 561 nm. Los obturadores configurados son 532/637/592/808 nm (tesis: 640 nm MPB). La tabla de polaridades de seguridad debe usar las longitudes de onda reales. |
| 202-03 | SYS-202:110 | 532 nm con lógica invertida (BAJO = abierto) | CONFIRMADO (código) / REQUIERE BANCO | CRÍTICA | `config.py:67`; ficha NI 6353 ("Pull-down resistor 50 kΩ typical") | La polaridad coincide con el código, pero **no es a prueba de fallos**. Tras un reinicio o encendido de la placa, las líneas quedan como entradas con pull-down de 50 kΩ (nivel BAJO), y un driver activo en BAJO abriría el obturador de 532 nm. Verificar en el banco el estado del obturador con la PC apagada, con la placa reseteada (`Reset Device` en NI-MAX) y tras un cuelgue. Si se confirma, invertir el cableado o agregar un pull-up. |
| 202-04 | SYS-202:59-60 | Obturadores con τ ≈ 1–5 ms y OD > 6 | SIN FUENTE | BAJA | — | Modelo de obturador no identificado (las tesis dicen "obturadores mecánicos"). |
| 202-05 | SYS-202:65 | Flipper "Thorlabs MFF101 o equivalente accionado por pulsos de tensión" | SIN FUENTE | MEDIA | Martinez §3.4, Gargiulo §4.2 (sin modelo) | Identificar el modelo en el banco; §4.3 y §6 dependen de ello. |
| 202-06 | SYS-202:66, 269 | Low Power 10–50 µW; High Power 5–25 mW; "unos pocos microwatts" | SIN FUENTE | BAJA | — | Medir con potenciómetro y citar la medición. |
| 202-07 | SYS-202:67 | `ao0` = Up/Low Power, `ao1` = Down/High Power | CONFIRMADO | — | `config.py:70-71`; `core/nidaq.py:279-282, 402-470` | — |
| 202-08 | SYS-202:81-85, 132-139 | "Se eliminó por completo la llamada a `up_flipper()` dentro de `_emergency_shutdown()`" | CONTRADICHO | MEDIA | `core/nidaq.py:215-222` | `_emergency_shutdown` (hook `atexit`) **sigue** llamando a `up_flipper()`. Lo que cambió es que el watchdog no llama a `_emergency_shutdown`. Los fragmentos usan `self`/`logger`, que no existen en ese módulo. |
| 202-09 | SYS-202:188-190, 201-214 | Pulso de 5 V con $\tau_{pulse}$ = 100 ms "óptimo"; con τ < 30 ms el espejo no completa los 90°; un nivel DC sobrecalienta "el solenoide" | CONTRADICHO | ALTA | `core/nidaq.py:423,433,459,469` (pulso real 5 ms); manual MFF101 §5.1, §6.3 y Apéndice B | El código emite 5 ms. En el MFF101 el movimiento lo hace un motor con "Transition Time ... 300 ms to 2800 ms" (flip time 500–2800 ms). El disparo es un flanco TTL ("a LO to HI edge causes flipper to toggle") y la unidad ignora disparos durante el movimiento. La duración del pulso no fija el recorrido y no hay solenoide. Borrar la justificación de 100 ms y documentar el modo de entrada configurado. REQUIERE BANCO: en modo "Go to Position", con un pulso 0→5→0 el flanco de bajada se ignora durante el movimiento. |
| 202-10 | SYS-202:276 | "Verifique la alimentación externa de 12 V del controlador Thorlabs MFF101" | CONTRADICHO | CRÍTICA | Manual MFF101 §4.2.1: "The unit must be connected only to a 15 V DC supply. Connection to a supply of a different rating may cause damage" | Corregir a 15 V DC. El procedimiento actual puede llevar a conectar una fuente equivocada. |
| 202-11 | SYS-202:277 | "Cables BNC conectados a `ao0` y `ao1` de la regleta SCB-68" | CONTRADICHO (interno) / REQUIERE BANCO | BAJA | `docs/bibliografia/BNC-2110.pdf` (BNC para AO0/AO1; bornes sólo para P0.<0..7>); ficha NI 6353 (AO2 y P0.8–31 en el conector 1) | La SCB-68 es de bornes a tornillo, sin BNC. La BNC-2110 sí tiene BNC para AO0/AO1. Los obturadores (P0.8–11) y `ao2` requieren un accesorio en el conector 1. Relevar el cableado real. |
| 202-12 | SYS-202:88 | "La tarjeta National Instruments PCIe/USB" | CONFIRMADO en parte | BAJA | Martinez §3.4 (PCIe-6353); ficha NI 6353 | Nombrar el modelo: PCIe-6353. |
| 202-13 | SYS-202:104-105 | `-200088` = "Task specified is invalid or does not exist" | CONFIRMADO | — | `nidaqmx/error_codes.py:1515` (`INVALID_TASK = -200088`); NI KB https://knowledge.ni.com/KnowledgeArticleDetails?id=kA00Z0000004AE6SAM | `write_analog_scalar_f64` es de la API C/PyDAQmx; el código usa `nidaqmx.Task.write`. |
| 202-14 | SYS-202:115-118, 219-227 | Fragmentos con `nidaq._shutter_states` y `nidaq.set_autoclose_timeout(...)` | CONTRADICHO (código actual) | BAJA | `core/shutters.py:421-423` | El código real usa la lista `_shutter_signal` y `heartbeat_shutter(timeout_val)`. La versión "previa" no es verificable. |
| 202-15 | SYS-202:143-161 | `close_all_tasks()` resetea los punteros bajo `_flipper_lock` | CONFIRMADO en parte | MEDIA | `core/nidaq.py:576-589` | Pone a `None` las 5 tareas (confirmado), pero **sin ningún lock**: no existe `_flipper_lock` y no toma `_nidaq_lock`. También cierra la tarea de **obturadores**. Una escritura concurrente del watchdog puede caer sobre una tarea cerrada (-200088 impreso, estado "cerrado", deadline desarmado). Tomar `_nidaq_lock` en `close_all_tasks`. |
| 202-16 | SYS-202:163-183 | `_get_flipper_tasks()` valida con `is_task_done()` y recrea | CONFIRMADO | — | `core/nidaq.py:259-286` | Sin lock ni logger, a diferencia del fragmento. |
| 202-17 | SYS-202:185-199 | El reintento llama a `close_all_tasks()` y recrea | CONTRADICHO (detalle) | BAJA | `core/nidaq.py:424-435, 460-471` | Cierra sólo la tarea del flipper afectado (mejor que cerrar todas). |
| 202-18 | SYS-202:229-245 | `clicked` para el usuario; `update_power_ui` sin eventos | CONFIRMADO (lógica) | BAJA | `core/shutters.py:163-170, 296` | El fragmento omite `blockSignals` y usa otros colores. |
| 202-19 | SYS-202:246 | Se quitó `update_power_ui(False)` de `_on_watchdog_triggered` | CONFIRMADO | — | `core/shutters.py:88-96` | — |
| 202-20 | SYS-202:260-261 | P5 "1.000 operaciones... piezo, obturación **y flipper**"; P6 "49/49" | CONTRADICHO | MEDIA | `tests/test_concurrency_watchdog.py:20-53` | El test importa `up_flipper`/`down_flipper` pero no los usa, y no puede fallar bajo pytest (201-23). |
| 202-21 | SYS-202:36 | "Total fidelidad entre la interfaz visual y el estado físico" | CONTRADICHO | MEDIA | `core/nidaq.py:402-409, 438-445` | `_flipper_high_power` y el callback a la GUI se actualizan **antes** de escribir, y un fallo sólo se imprime. |

---

## SYS-203 — Control de láseres, RS-232/SCPI y modulación

Fuentes usadas: *OBIS LX/LS Laser Operator's Manual* (Coherent), https://www.coherent.com/resources/manuals/lasers/obis-lx-ls-operators-manual.pdf (Tabla 4-4 y §9); adaptador MPB de Micro-Manager, https://raw.githubusercontent.com/micro-manager/mmCoreAndDevices/main/DeviceAdapters/MPBLaser/MPBLaser.h y `MPBLaser.cpp` (driver de terceros, no manual del fabricante); 21 CFR 1040.10, https://www.law.cornell.edu/cfr/text/21/1040.10 ; tesis de Martinez §3.1 y de Gargiulo §4.1.

| ID | Documento:línea | Afirmación | Veredicto | Severidad | Fuentes | Corrección propuesta |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 203-01 | SYS-203:20 | Módulos de código: `core/lasers.py`, `modules/hardware_dashboard.py` | CONTRADICHO | MEDIA | `core/lasers.py` no existe (verificado con `ls`); tampoco `modules/laser_532.py` ni `instruments/` (citados en SYS-102:66) | Quitar la referencia. Ningún archivo de código nombra un modelo de láser. |
| 203-02 | SYS-203:96-160, 168 | Láser verde = **Spectra-Physics Excelsior 532-150-CDRH** (pin 8 analógico conectado a `ao2`, pin 2 On/Off, KTP, placa base 15–35 °C, retardo CDRH 5 s) | CONTRADICHO / REQUIERE BANCO | CRÍTICA | Martinez §3.1: "532 nm (Laserquantum Ventus)"; Gargiulo §4.1: "532nm (Laser Ventus)"; MOD-05:123 también dice "Ventus" | Las dos tesis del laboratorio identifican un Laser Quantum Ventus. Toda la §3 (pinout, rango analógico, protocolo de encendido y apagado, límites térmicos) describe otro equipo, y alimenta el control de potencia `ao2` (1–5 V). Leer la etiqueta del cabezal y reescribir con el manual del Ventus/MPC. |
| 203-03 | SYS-203:24-52, 168 | Láser rojo = **Coherent OBIS 637-160C** (637 nm, 160 mW) | CONTRADICHO / REQUIERE BANCO | ALTA | Martinez §3.1 y Gargiulo §4.1: "640 nm (MPB)"; `config.py:65` nombra "637 nm (red)" sin modelo | Las tesis dicen MPB 640 nm. Si hubo un reemplazo posterior, documentarlo con número de serie; si no, la §1 no aplica. |
| 203-04 | SYS-203:31 | OBIS: "Baud Rate 9600 (predeterminado de fábrica) o 115200" | CONTRADICHO | MEDIA | Manual OBIS LX/LS, Tabla 4-4 ("Baud 115200, Parity None, Data Bits 8, Stop Bits 1, Flow Control None") | El valor por defecto es 115200 8N1. |
| 203-05 | SYS-203:45 | `SOURce:POWer:NOMinal?` "devuelve la potencia óptica medida en tiempo real" | CONTRADICHO | ALTA | Manual OBIS §9: "Returns the nominal CW laser output power in watts"; la medida es `SOURce:POWer:LEVel?` ("present laser output power measured in watts") | Usar `SOURce:POWer:LEVel?` para telemetría. Con el comando citado, una futura telemetría leería siempre la potencia nominal. |
| 203-06 | SYS-203:50-51 | `SYSTem:DIODe:CURRent?` y `SYSTem:TEMPerature:BASE?` | CONTRADICHO | MEDIA | Manual OBIS §9: `SOURce:POWer:CURRent?`, `SOURce:TEMPerature:BASeplate?` | Corregir la sintaxis. |
| 203-07 | SYS-203:41, 42-44, 46-49 | `*IDN?`, `SYSTem:INFormation:MODel?`, `SOURce:AM:STATe`, `...AMPLitude`, `LIMit:LOW?/HIGH?`, `AM:INTernal CWP`, `AM:EXTernal DIGital/ANALog` | CONFIRMADO | — | Manual OBIS §9 (índice de comandos) | "`?SYSTem:...`" tiene un "?" inicial espurio. |
| 203-08 | SYS-203:67-90 | Protocolo MPB: `\r`, prompt " >", prefijo `D`/`F`, `setldenable`, `powerenable`, `setpower 0`, `getpower 0`, `getpowersetptlim 0`, códigos de `getlaserstate` 0/6/7/8/20/31/41/42, `getinput 2` | CONFIRMADO (una fuente, de terceros) | — | `MPBLaser.h`/`.cpp` de Micro-Manager | Falta el manual MPB para cerrarlo con fuente primaria. |
| 203-09 | SYS-203:69, 92 | MPB 9600 baud; `getshgtemp`/`gettectemp` | SIN FUENTE | BAJA | El adaptador de Micro-Manager no fija baud ni usa esos comandos | Verificar con el manual MPB. |
| 203-10 | SYS-203:141 | 150 mW supera "el límite de emisión accesible de la córnea por un factor mayor a 10 000" | CONTRADICHO | ALTA | 21 CFR 1040.10: límite Clase II (visible CW) "1.0 × 10⁻³ W"; Clase IIIb hasta "5 × 10⁻¹ W" | 150 mW equivale a ~150× el límite de Clase 2 (~385× el de Clase 1 a 532 nm), no a >10 000×. El riesgo es real (Clase 3B); corregir el número. |
| 203-11 | SYS-203:98 | 150 mW a 532 nm es Clase 3B | CONFIRMADO | — | 21 CFR 1040.10 (IIIb ≤ 0.5 W) | — |
| 203-12 | SYS-203:144 | "Retraso forzado por hardware de 5 s" exigido por CDRH | CONTRADICHO (como requisito) | BAJA | 21 CFR 1040.10: sólo exige una señal "sufficiently prior to emission" | El valor de 5 s depende del modelo (y el modelo es otro, 203-02). |
| 203-13 | SYS-203:143 | El interlock corta la corriente en < 10 ms | SIN FUENTE | BAJA | — | Depende del modelo real. |
| 203-14 | SYS-203:142 | Gafas EN 207 con OD > 5 a 532 nm | SIN FUENTE | MEDIA | — | La especificación EN 207 se expresa en escala LB y depende de potencia y diámetro del haz. Pedir el cálculo al responsable de seguridad láser. |
| 203-15 | SYS-203:129, 173, 193 | 532 → canal digital 11; 592 → canal 9; 637 → canal 8; 532 analógico `ao2` 1–5 V | CONFIRMADO | — | `config.py:49-51, 65-66` | Única sección de SYS-203 que coincide con el código de canales. |
| 203-16 | SYS-203:202 | Fotodiodo del divisor de haz = `Dev1/ai6` (`PD_CHAN_BS`) | CONFIRMADO | — | `config.py:73-75` | — |
| 203-17 | SYS-203:209 | "El sistema de seguridad `OpticalWatchdog`" | CONTRADICHO | BAJA | `core/nidaq.py:152` | El hilo se llama `ShutterWatchdog`. |
| 203-18 | SYS-203:171 | MPB 592 nm "500–2000 mW" | SIN FUENTE | BAJA | — | Citar la placa del equipo. |

---

## SYS-204 — Controlador Canon EDSDK, simulación EVF y búferes RAM

Fuentes: `ESDK_CANON/EDSDK_v13.20.21_Windows/EDSDK_API_EN.pdf` (§1.3 Supported Cameras, §5.2.55), `EDSDKTypes.h`, `EDSDKErrors.h`, `EDSDK.h`; `ESDK_CANON/EDSDK_v13.20.10_Raw_Win/Sample/CSharp/.../DownloadEvfCommand.cs`; folleto Canon EOS 500D, https://www2.canon.com.hk/myContent/Product_Tab/DigitalCamera/DigitalSLRCamera/Brochure/EOS_500D_Eng.pdf ; tesis Martinez §3.2 y Gargiulo §4.1 (confirman la cámara Canon EOS-500D).

| ID | Documento:línea | Afirmación | Veredicto | Severidad | Fuentes | Corrección propuesta |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 204-01 | SYS-204:29 | EDSDK v13.20 de 64 bits con EOS 500D; 15.1 MP; 4752 × 3168 px | CONFIRMADO | — | EDSDK_API_EN.pdf §1.3 ("EOS Kiss X3 / EOS REBEL T1i / EOS 500D", sin restricción *1); folleto Canon ("approx. 15.10-Megapixel", "(4752 x 3168)") | — |
| 204-02 | SYS-204:39-54 | Al habilitar el live view se fija `kEdsPropID_Evf_Mode = 1` = "Simulación de Exposición", que desactiva la ganancia EVF y elimina el ruido | CONTRADICHO | ALTA | EDSDK_API_EN.pdf §5.2.55: "kEdsPropID_Evf_Mode — Gets/sets live view function settings. 0 Disable, 1 Enable"; `core/canon_edsdk.py:136, 483-493` | Según el SDK, `Evf_Mode` sólo activa o desactiva la función de live view; no es simulación de exposición. Además, `enable_live_view()` **no** escribe `Evf_Mode`: sólo fija `Evf_OutputDevice = PC`. La constante está definida y no se usa. Borrar §2.1 o reemplazarla por lo que realmente hace el código. |
| 204-03 | SYS-204:47 | `kEdsPropID_Evf_Mode = 0x00000501` | CONFIRMADO | — | `EDSDKTypes.h:315` | — |
| 204-04 | SYS-204:57-60 | `Evf_Zoom` = 1 / 5 / 10; 1× = "campo completo 4752 × 3168 px" | CONFIRMADO (valores) / REQUIERE BANCO | MEDIA | `EDSDKTypes.h:1196-1199` (`kEdsEvfZoom_Fit = 1`, `x5 = 5`, `x10 = 10`); folleto ("5x/10x magnification") | El cuadro EVF no sale a 4752 × 3168. La posición de zoom se expresa en `kEdsPropID_Evf_CoordinateSystem` (0x540), que el código **no lee**: fija 4752 × 3168 a mano (`canon_edsdk.py:596-622`). Leer esa propiedad en el banco con la 500D. |
| 204-05 | SYS-204:62-73 | `EdsPoint` vía `kEdsPropID_Evf_ZoomPosition` | CONFIRMADO | — | `EDSDKTypes.h:322` | — |
| 204-06 | SYS-204:83 | `_edsdk_lock` pasó de `Lock` a `RLock` (ANOM-CAM-01) | CONFIRMADO | — | `core/canon_edsdk.py:78` | — |
| 204-07 | SYS-204:86 | UILock/UIUnLock "verificados contra `EDSDKTypes.h:468-469`" | CONFIRMADO (con salvedad) | BAJA | v13.20.10 `EDSDKTypes.h:468-469`; en v13.20.21 están en L444-445; valores 0/1; `canon_edsdk.py:167-168` | Indicar la versión del SDK. |
| 204-08 | SYS-204:91-100 | Stream inicial de 2 MiB = el valor del ejemplo de Canon; `EDSDK.h` dice que el buffer se extiende solo | CONFIRMADO | — | `DownloadEvfCommand.cs:41` (`UInt64 bufferSize = 2 * 1024 * 1024;`, v13.20.10); `EDSDK.h:833-834`; `canon_edsdk.py:533` | — |
| 204-09 | SYS-204:89 | `nanopositioning.py::move()/_moveto()` ya tienen timeout de sondeo | CONFIRMADO | — | `core/nanopositioning.py:761-801` | El mismo patrón sin timeout sigue en `modules/measurements.py:2144` (ver 205-14). |
| 204-10 | SYS-204:111 | Cuadro de live view de 1280 × 840 px | SIN FUENTE | BAJA | — | Medir el tamaño real del JPEG EVF de la 500D. |
| 204-11 | SYS-204:110-122 | Mediana 3×3 y umbral de piso de ruido por máximo de canal | CONFIRMADO | BAJA | `modules/camera.py:440-446` | Se atribuye a "rayos cósmicos", que son irrelevantes en un CMOS con exposiciones de ms; los responsables son los píxeles calientes. Advertir que el piso de ruido altera intensidades si se usan para medir. |
| 204-12 | SYS-204:15, 147 | Detalle matemático en "SYS-103 §8" | CONTRADICHO | BAJA | SYS-103 §7 | La sección correcta es §7. |
| 204-13 | SYS-204:151 | Bucle de video a 25 fps | CONFIRMADO | — | `modules/camera.py:264` (40 ms) | — |

---

## MOD-04 — Cámara Live View (Canon EOS EDSDK)

| ID | Documento:línea | Afirmación | Veredicto | Severidad | Fuentes | Corrección propuesta |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| M04-01 | MOD-04:77-78 | Atajos: `LIVE VIEW` = **F1**, `SNAP` = **F8** | CONTRADICHO | CRÍTICA | `modules/camera.py` (sin `QShortcut` ni `setShortcut`); `modules/trace.py:332` (F1 = iniciar traza, que **abre el obturador**); `modules/focus.py:50` (F8 = ir al máximo de foco con láser) | Un operador que siga el manual y pulse F1 en la ventana principal abre un láser. Quitar esos atajos del manual, o implementarlos sin colisión y documentarlo. |
| M04-02 | MOD-04:34, 49, 129-132 | "Simulación de Exposición EVF: curvas gamma y ganancia digital en software"; controles "Brillo +1.2 EV" y "Gamma 1.4" | CONTRADICHO | MEDIA | `modules/camera.py` (no hay procesamiento gamma); SYS-204 §2.1 lo presenta como propiedad de hardware (204-02) | Los dos documentos se contradicen entre sí y ninguno coincide con el código. Describir sólo la mediana y el piso de ruido existentes. |
| M04-03 | MOD-04:33, 67, 127 | 25–30 FPS; "28.5 FPS"; "28 FPS" | CONTRADICHO | BAJA | `modules/camera.py:264` (40 ms = 25 FPS como máximo) | Usar 25 FPS como máximo. |
| M04-04 | MOD-04:30, 33, 102 | 15.1 MP, 4752 × 3168 | CONFIRMADO | — | Folleto Canon EOS 500D | — |
| M04-05 | MOD-04:79 | ISO 100–12800 | CONFIRMADO (con salvedad) | BAJA | Folleto: ISO 100–3200, ampliable a 6400 (H1) y 12800 (H2) | Marcar 6400/12800 como ampliadas. |
| M04-06 | MOD-04:80 | Tv 1/4000 a 30 s y Bulb | CONFIRMADO | — | Folleto ("1/4000 to 30 sec., bulb") | — |
| M04-07 | MOD-04:81 | Zoom "digital óptico nativo" 1× / 5× / 10× | CONFIRMADO (valores) | BAJA | `EDSDKTypes.h:1196-1199` | Es una ampliación de live view (recorte), no zoom óptico. |
| M04-08 | MOD-04:141 | `EDSDK_ERR_DEVICE_BUSY 0x82` | CONTRADICHO | BAJA | `EDSDKErrors.h:101` (`EDS_ERR_DEVICE_BUSY 0x00000081L`) | 0x81. |
| M04-09 | MOD-04:174 | `EDS_ERR_INVALID_PARAMETER (0x07)` | CONTRADICHO | BAJA | `EDSDKErrors.h:91` (`0x00000060L`) | 0x60. |
| M04-10 | MOD-04:154 | Throttle del centro de zoom: 80 ms (≈12.5 Hz) | CONFIRMADO | — | `modules/camera.py:1384-1387` | — |
| M04-11 | MOD-04:157-159 | `_frame_timer` de 40 ms con guarda `_is_fetching` | CONFIRMADO | — | `modules/camera.py:259-308` | — |
| M04-12 | MOD-04:166 | Antirrebote de resize de 50 ms | CONFIRMADO | — | `modules/camera.py:1378-1381` | — |
| M04-13 | MOD-04:169-171 | Apagado con `kEdsEvfOutputDevice_Off`; handler `atexit` | CONFIRMADO | — | `core/canon_edsdk.py:343, 500` | — |
| M04-14 | MOD-04:174 | Recorte de coordenadas de zoom dentro de 4752 × 3168 | CONFIRMADO (código) / REQUIERE BANCO | MEDIA | `core/canon_edsdk.py:608-622` | Ver 204-04: el sistema de coordenadas EVF real no se consulta. |
| M04-15 | MOD-04:210 | ROI → Confocal bloqueado fuera de 0–100 µm | CONFIRMADO (código) | MEDIA | `modules/camera.py:2578-2582` | Hereda el límite de 100 µm, que no es el recorrido físico (205-01). |
| M04-16 | MOD-04:102 | TIFF RGB de "24 o 48 bits" | SIN FUENTE | BAJA | — | La 500D graba RAW de 14 bits o JPEG de 8 bits por canal; 48 bits sólo tras revelar el RAW. |
| M04-17 | MOD-04:143 | Objetivos "60× o 100×" | CONTRADICHO en parte | BAJA | Martinez §3.1 (60× agua NA 1.0; 20× aire NA 0.5) | No hay constancia de un 100×. |

---

## MOD-05 — Modulación y control de láseres de excitación

| ID | Documento:línea | Afirmación | Veredicto | Severidad | Fuentes | Corrección propuesta |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| M05-01 | MOD-05:40, 57-62, 77-78, 84-114; también SYS-201:274 | `Laser532Window` ofrece calibración P(mW) ↔ V, campo "Potencia Edit" en mW, carga y guardado de `Calibration_Power_532nm.txt` con R² y ajuste cuadrático | CONTRADICHO | ALTA | `modules/camera.py:3686-3780` | La ventana real sólo tiene slider y spinbox de voltaje, presets de 1 a 5 V y el botón del obturador. No hay conversión a mW ni E/S de calibración. Un operador que crea trabajar "en mW reales" está en voltios sin calibrar. Retirar §3–§6 o marcarlas como "no implementado". |
| M05-02 | MOD-05:38, 55, 75-76 | Rango de `ao2`: 0.00–5.00 V (slider y spinbox de 0.000 a 5.000 V) | CONTRADICHO | MEDIA | `config.py:50-51`; `modules/camera.py:3705-3715`; `core/nidaq.py:556` | El mínimo es **1.0 V** (`LASER_532_V_MIN`), tanto en la GUI como en el recorte del driver. Por software no se puede comandar 0 V, y la calibración "0 a 5 V" de L124 no es realizable. |
| M05-03 | MOD-05:8 | `core/shutters.py` implementa "control serie RS-232" | CONTRADICHO | BAJA | `core/shutters.py` (sin serie) | En el repositorio no hay control RS-232 de láseres. |
| M05-04 | MOD-05:39 | Obturador TTL con respuesta < 1 ms | SIN FUENTE | BAJA | — | Modelo de obturador no identificado. |
| M05-05 | MOD-05:52, 74 | El botón del obturador 532 refleja ABIERTO/CERRADO | CONTRADICHO (sincronía) | MEDIA | `modules/camera.py:3728-3758` | El botón no se registra en `register_watchdog_callback`: si el watchdog cierra el obturador, el botón sigue diciendo "Abierto" (desincronía GUI↔hardware). Registrar el callback. |
| M05-06 | MOD-05:109-114 | $P = c_2V^2 + c_1V + c_0$ y su inversa con la raíz "+" | CONFIRMADO (álgebra) con condición | BAJA | cálculo propio | Vale sólo si $c_2 > 0$ y en la rama creciente; si $c_2 \to 0$ la fórmula diverge. Irrelevante mientras no esté implementada (M05-01). |
| M05-07 | MOD-05:123 | Láser "DPSS Ventus 532 nm"; cristal LBO; calentamiento de 20 min | CONFIRMADO (modelo) / SIN FUENTE (LBO, 20 min) | MEDIA | Martinez §3.1, Gargiulo §4.1 (Ventus) | El modelo coincide con las tesis y **contradice SYS-203** (Excelsior, KTP). Unificar y citar el manual del Ventus para el tiempo de calentamiento. |
| M05-08 | MOD-05:122 | Recorte por software a 5.00 V "(o 4.50 V)" | CONFIRMADO (5.0 V) / SIN FUENTE (4.50) | BAJA | `config.py:51` | Quitar el "(o 4.50 V)". |
| M05-09 | MOD-05:88, 124 | Medidor Thorlabs PM100D | SIN FUENTE | BAJA | — | Citar el equipo de inventario. |

---

## MOD-13 — Tablero de seguridad de hardware y asistente de presets

| ID | Documento:línea | Afirmación | Veredicto | Severidad | Fuentes | Corrección propuesta |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| M13-01 | MOD-13:38, 112 | "Aislar (Soft Mock)" deja simular un subsistema "sin afectar a los demás"; "bloquea el acceso físico al driver" | CONTRADICHO (omisión de seguridad) | CRÍTICA | `core/nidaq.py:339-344, 365-367`; `core/hardware_manager.py:101-109, 351-372` | Con "NI-DAQmx (Dev1)" aislado, `open_shutter`/`close_shutter`/`close_all_shutters`, el watchdog y el botón "Cerrar Todos" **dejan de escribir en la placa**. Un obturador abierto antes de aislar queda físicamente abierto mientras el software lo da por cerrado. Documentar la advertencia, y cerrar los obturadores (o impedir el aislamiento) si hay alguno abierto. |
| M13-02 | MOD-13:61 | "Canales AI: 0..3 · AO: 0..2 · DO: port0/line0:7" | CONTRADICHO | CRÍTICA | `config.py:66, 69, 73-76` | DO: line7 (notch) y line8–11 (obturadores), fuera de 0:7. AI: 0–3, 6 (divisor de haz) y 3/4/5 (triggers Z/X/Y; AI 3 se comparte con el fotodiodo de 808 nm). |
| M13-03 | MOD-13:36, 60 | Placa "PCIe-6323 / USB-6343" | CONTRADICHO | ALTA | Martinez §3.4 (PCIe-6353); ficha NI 6353; `config.py:62-63` (1.25 MS/s y 1.00 MS/s, las tasas exactas del 6353) | Corregir a PCIe-6353. |
| M13-04 | MOD-13:36, 67 | Espectrógrafo "Andor Shamrock SR-303i" | CONTRADICHO | ALTA | Martinez §3.2 ("Shamrock 500i"); Gargiulo §4.1; `docs/bibliografia/andor-shamrock-500-specifications.pdf`; `lab-invariants.md` §3 | Es el 500i (500 mm). Con un 303i las dispersiones serían otras. |
| M13-05 | MOD-13:39 | "Eliminación total de falsos positivos `Conectado`" | CONTRADICHO | MEDIA | `core/hardware_manager.py:158-168, 208-217, 133-139` | NI-DAQmx figura "conectado" si existe **cualquier** dispositivo NI (`"Dev1" in devs or len(devs) > 0`). El "Láser 532 nm" figura conectado sólo porque la DAQ lo está, sin consultar el láser. El PI usa `IsConnected()`, que no detecta desenchufes (205-06). |
| M13-06 | MOD-13:210 | "`DAQError -200088: Resource already reserved`" → pulsar `Reset DAQ Tasks` en el Tablero | CITA ERRÓNEA / CONTRADICHO | MEDIA | `nidaqmx/error_codes.py:1515, 1739`; NI KB kA00Z0000004AE6SAM y kA00Z000000P8kmSAC; `modules/hardware_dashboard.py:117-160` | -200088 es "Task specified is invalid or does not exist"; "resource is reserved" es -50103. Además, el Tablero no tiene un botón "Reset DAQ Tasks": sólo "Re-scan", "Limpiar Bitácora" y "Conectar". |
| M13-07 | MOD-13:75, 114 | Botones "RECONECTAR TODO" y "MODO SEGURO GLOBAL" | CONTRADICHO | MEDIA | `modules/hardware_dashboard.py:117-160` | No existen. `SAFE_MODE` sólo se fija por variable de entorno al arrancar (`config.py:41`). |
| M13-08 | MOD-13:211 | `preset_manager.py` rechaza valores fuera de cota y restaura `factory_defaults.json` | CONTRADICHO | MEDIA | `core/preset_manager.py:113-131` | `load_preset_file` sólo parsea `clave = valor`, sin validar rangos, y no existe `factory_defaults.json`. La protección real la dan el recorte del driver y el pre-flight (205-09/12). |
| M13-09 | MOD-13:143 | El badge verifica la comunicación con `qIDN()` | CONFIRMADO (código) | MEDIA | `core/nanopositioning.py:737, 750-751` | Es cierto, y es justamente el tráfico `*IDN?` por lectura que SYS-205 dice eliminado (205-05). |
| M13-10 | MOD-13:126-129 | Perfiles `pyprinting` / `pyspectrum` / `all` / `camera` | CONFIRMADO (con salvedad) | BAJA | `core/hardware_manager.py:41-64` | El dispositivo del perfil `camera` es "Cámara USB/Thorlabs": prueba primero OpenCV (índice 1) y después Canon. |
| M13-11 | MOD-13:40, 150-152 | Detección de puerto USB ocupado | CONFIRMADO en parte | BAJA | `core/hardware_manager.py:149-151` | Es una heurística por texto del error (`already`/`busy`/`open`/`in use`/`access`) y sólo existe para el PI, no para Canon. |
| M13-12 | MOD-13:42, 196-201 | Asistente `QWizard` de 5 pasos | CONFIRMADO (conteo) | BAJA | `modules/preset_wizard.py:255-260` | Las páginas reales son Intro, StoppingMode, Timing, FocusAndDrift y Preview; el paso 3 no es "Geometría de Grilla". |
| M13-13 | MOD-13:7 | Atajo `Ctrl+H` | CONFIRMADO | — | `app.py:142` | Abre el "Tablero de Conexiones". |
| M13-14 | MOD-13:36 | "PI E-517/E-727" | SIN FUENTE (E-727) | BAJA | Gargiulo §4.2 (E-517); `core/hardware_manager.py:33` | Las tesis sólo mencionan el E-517 (con platina P-545). |
| M13-15 | MOD-13:188-189 | Genera `hardware_diagnostic_report.txt` | SIN FUENTE | BAJA | `modules/hardware_dashboard.py` (no aparece) | Verificar o quitar. |

---

## SYS-102 — Señales/slots PyQt6 y temporización DAQmx

| ID | Documento:línea | Afirmación | Veredicto | Severidad | Fuentes | Corrección propuesta |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 102-01 | SYS-102:175 | Del dato NI-DAQmx a la decisión de parada, la cadena tiene "latencia inferior a 1.0 ms, garantizando el cierre inmediato del obturador al adherirse la NP" | CONTRADICHO | CRÍTICA | `modules/trace.py:500-502` (`rate = 1e6/100 = 10 kHz`, `N = 10`), `:633` (`pointtimer.start(35)`), `:776` (`data_printingSignal.emit`); `app.py:473` (`_dispatch_trace`, señal encolada entre hilos) | La traza se muestrea en un `QTimer` de 35 ms: cada tick lee 10 muestras (1 ms de señal) y emite una señal Qt hacia el worker de impresión, que recién entonces cierra el obturador. La latencia mínima es del orden del período del timer (hasta ~35 ms) más la cola de eventos, más de un orden de magnitud por encima de 1 ms. Hay que medirla en el banco (TTL del obturador contra el fotodiodo) y documentar el valor real. |
| 102-02 | SYS-102:58, 64, 117 | Traza "Adquisición 10 kHz" | CONTRADICHO (engañoso) / REQUIERE BANCO | CRÍTICA | `modules/trace.py:500-502, 627-633, 696-701, 734-736`; `core/nidaq.py:525-529` | 10 kHz es sólo la tasa dentro de cada bloque. La serie guardada tiene un punto cada ~35 ms (media de 10 muestras) con marca de tiempo del host (`time.time()`), no del reloj de hardware. En modo continuo el buffer es de `max(10·10, 1000)` = 1000 muestras, se producen ~350 por tick y se leen 10: con el modo por defecto de DAQmx (no sobrescribir) el buffer se desborda en ~0.1 s (error -200279). Cada error se registra como **0.0 V** (L734-736), lo que puede disparar o enmascarar el criterio de parada. Verificar en el banco y corregir la lectura (leer todo lo disponible, o `RelativeTo.MOST_RECENT_SAMPLE`). |
| 102-03 | SYS-102:30 | "100 % de las señales críticas conectadas, verificadas y funcionales" | CONTRADICHO en parte | BAJA | ver 102-04 a 102-07 | Sólo se revisaron algunas conexiones: las de §3.1 existen (`app.py:450-458, 464-504`). Varias señales listadas en §3.7 no existen. |
| 102-04 | SYS-102:135 | `core/shutters.py` expone `watchdog_timeout_signal` | CONTRADICHO | BAJA | `core/shutters.py:46-56` | La señal es `autoclose_timeout_signal`. Falta `shutter3_signal` (808 nm). |
| 102-05 | SYS-102:60 | Shutters & Flippers: 7 señales de frontend y 3 de backend | CONTRADICHO | BAJA | `core/shutters.py:46-56, 404-405` | 11 de frontend y 2 de backend. |
| 102-06 | SYS-102:56 | Confocal: "Mapeo galvo 2D" | CONTRADICHO | BAJA | Martinez §3.4 (escaneo con la platina piezo en rampa); `modules/confocal.py` (`WAV_LIN`) | No hay galvanómetros: el barrido lo hace la platina. |
| 102-07 | SYS-102:62-66 | Filas duplicadas o corruptas; módulo `modules/laser_532.py` / `instruments/` | CONTRADICHO | BAJA | `ls` (no existen) | Limpiar la tabla. El control del 532 está en `modules/camera.py::Laser532Window`. |
| 102-08 | SYS-102:31 | Se removieron `measureKineticsSignal` y `saveSpectrumSignal` y se "conectó formalmente" `saveSpectrumSignal` | CONTRADICHO (interno) | BAJA | — | La frase se contradice a sí misma. |
| 102-09 | SYS-102:76-87 | Conexiones entre backends (`gotomaxdone`/`lockdone`/`autodone`/`scandone` → `nanoWorker.read_pos`, ciclo de impresión) | CONFIRMADO | — | `app.py:450-458, 464-504` | `data_printingSignal` pasa por `_dispatch_trace` (`app.py:473`), no va directo a `grid_trace_detect`. Cada `read_pos` genera un `*IDN?` (205-05). |
| 102-10 | SYS-102:111, 119 | Atajos F8/F9/F10 (foco) y F1/F2 (traza) | CONFIRMADO | — | `modules/focus.py:50-52`; `modules/trace.py:332-334` | Colisiona con MOD-04 (M04-01). |
| 102-11 | SYS-102:59 | Cámara: live view a 25 FPS, foto de 15 MP | CONFIRMADO | — | `modules/camera.py:264`; folleto Canon | — |

---

## SYS-103 — Regímenes de coordenadas e invariancia cinemática

| ID | Documento:línea | Afirmación | Veredicto | Severidad | Fuentes | Corrección propuesta |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 103-01 | SYS-103:41-43, 340 | El cambio de régimen modifica **sólo** etiquetas y tooltips, "sin alterar en un solo nanómetro la cinemática"; se puede alternar "sin riesgo ... ni alterar secuencias" | CONTRADICHO en parte | MEDIA | `core/nanopositioning.py:222-241, 301-317` (`DIRECTION_MAP`) | Vale para los campos numéricos (casilla i = eje i), pero **no** para los botones de flecha ni las teclas: en Legacy "→" mueve el eje 1 (+); en Laser Ref, el eje 2 (+); en Sample Ref, el eje 2 (−). Al cambiar de régimen, la misma tecla mueve otro eje u otro sentido. Documentarlo como tal. |
| 103-02 | SYS-103:55-71, 36-37 | Tabla de signos: Eje 1 (+) → láser abajo; Eje 2 (+) → láser a la derecha; Sample Ref invertido | CONFIRMADO (código) / REQUIERE BANCO | MEDIA | `config.py:130-132`; `core/nanopositioning.py:229-240` | El código es coherente con la tabla. El sentido físico en cámara depende del tren óptico y del montaje: verificarlo con un paso conocido (también es la base de `KNOWN_SIGN_PATTERN`). |
| 103-03 | SYS-103:29 | Controladora "PI E-517/E-736" | SIN FUENTE (E-736) | BAJA | Gargiulo §4.2 (E-517); `hardware_manager.py:33` dice "E-517/E-727" | Unificar en E-517 (platina P-545, 205-01). |
| 103-04 | SYS-103:50 | Objetivo de inmersión con NA = 1.40 / 1.49 | CONTRADICHO | BAJA | Martinez §3.1 (60XW agua, NA = 1.0; 20× aire NA = 0.5) | Corregir. |
| 103-05 | SYS-103:87-181 | Diccionario `COORDINATE_NOMENCLATURE` (claves `axis_1_name`, `step_xy_label: "Step X-Y (µm):"`, `confocal_range_x`, ...) | CONTRADICHO | BAJA | `core/nanopositioning.py:39-181` | Las claves reales son `axis1_name`, `axis1_display`, `confocal_range_1`, `print_ref_1`, etc., y los textos difieren. Reemplazar por un extracto real o por una referencia al símbolo. |
| 103-06 | SYS-103:202 | `register_regime_listener` invoca al callback de inmediato con el régimen vigente | CONTRADICHO | BAJA | `core/nanopositioning.py:184-187` | Sólo lo agrega a la lista. |
| 103-07 | SYS-103:204 | `set_global_coordinate_regime` actualiza la variable global en `config.py` | CONTRADICHO | BAJA | `core/nanopositioning.py:196-210` | Recorre `_ACTIVE_FRONTENDS` y `_REGIME_LISTENERS`; no toca `config.py`. |
| 103-08 | SYS-103:209-217 | `PSF_MODES` canónico y emisión por índice | CONFIRMADO | — | `modules/confocal.py:51, 177-180` | — |
| 103-09 | SYS-103:231 | Flechas y PageUp/PageDown mueven 1 paso; ±0.1 / ±1 / ±10 µm | CONFIRMADO en parte | BAJA | `core/nanopositioning.py:464-495` | El paso es el del campo `Step` (Shift ×10); los valores ±0.1/1/10 son ejemplos, no constantes. |
| 103-10 | SYS-103:286-294 | 6 pruebas de nomenclatura | CONFIRMADO (conteo) | — | `tests/test_coordinate_nomenclature_sync.py` (6 `def test_`) | — |
| 103-11 | SYS-103:297-299 | 56/56 diagnósticos; latencia de conmutación < 2.0 ms | SIN FUENTE / inconsistente | BAJA | SYS-201:303 dice 49/49; `tests/run_all_diagnostics.py:36-57` (el conteo incluye verificaciones de importación de bibliotecas) | No hay medición de la latencia. |
| 103-12 | SYS-103:313, 319 | Calibración en píxeles de sensor 4752 × 3168; `det < 0` (reflexión) esperada por `cv2.rotate(90° CW)` + `cv2.flip(1)` | CONFIRMADO | — | `modules/camera.py:382-383, 414-415`; álgebra: una rotación (det = +1) seguida de una reflexión (det = −1) da det = −1 | El recorte de zoom depende del sistema de coordenadas EVF no leído (204-04). |
| 103-13 | SYS-103:320 | `matches_known_sign_pattern(tolerance_deg=30.0)` | CONFIRMADO | — | `core/stage_camera_transform.py:204-230` | — |
| 103-14 | SYS-103:323 | Persistencia `DEFAULT_DATA_PATH/stage_camera_calibration_{rig_id}.json` | CONFIRMADO | — | `core/stage_camera_transform.py:101` | — |
| 103-15 | SYS-103:334 | 15 + 13 pruebas | CONFIRMADO (conteo) | — | `tests/test_stage_camera_transform.py` (15), `tests/test_stage_camera_calibration.py` (13) | — |
| 103-16 | SYS-103:16 | "§8 de este reporte" para la cámara | CONTRADICHO | BAJA | SYS-103 §7 | La sección correcta es §7. |

---

## Afirmaciones que requieren banco

Ordenadas por prioridad de seguridad. Ninguna se ejecutó: esta auditoría fue sólo de lectura.

1. **Estado de los obturadores tras apagar, resetear o colgar la PC** (202-03, 201-01). El obturador de 532 nm es activo en BAJO y el NI 6353 deja sus DIO con pull-down de 50 kΩ al encender. Verificar con un medidor de potencia si el obturador de 532 nm **se abre** con la PC apagada, tras `Reset Device` en NI-MAX y tras matar el proceso con el obturador abierto.
2. **Recorrido real por eje de la platina P-545 + E-517** (205-01). Consultar `TMN?`/`TMX?` por eje. Las tesis dan 200 µm en XY y 200 o 50 µm en Z, y el código recorta todos los ejes a 100 µm. Si Z tiene 50 µm, el recorte no protege Z.
3. **Qué excepción lanza pipython al desenchufar el USB o apagar el E-517 en pleno `MOV`/`qPOS`** (205-02, 205-06). Si es `GCSError` (-1/-4/-7), la reconexión y la pausa nunca se disparan. Verificar también si `IsConnected()` sigue en `True` tras desenchufar.
4. **Salto al home durante la auto-reconexión** (205-07). Provocar un fallo de bus durante un escaneo con el obturador cerrado y observar si la platina va a (50, 50, 10) µm.
5. **Latencia real traza → cierre del obturador** (102-01). Medir con osciloscopio el TTL del obturador contra el fotodiodo.
6. **Desborde del buffer continuo de la traza** (102-02). Correr la traza en hardware 10 s y buscar errores -200279 o valores 0.0 V en `trace.txt`.
7. **Escritura sobre la tarea cerrada** tras `close_all_tasks()` mientras el watchdog cierra (202-15); estado de las líneas DO tras cerrar la tarea.
8. **Modelo y configuración del flipper de potencia** (202-05, 202-09, 202-10): etiqueta, fuente (¿15 V?), modo de entrada ("Toggle" o "Go to Position") y respuesta a un pulso de 5 ms en `ao0`/`ao1`.
9. **Identidad de los láseres** (203-02, 203-03): etiquetas de los cabezales de 532 nm (¿Ventus o Excelsior?) y del rojo (¿MPB 640 o OBIS 637?), más el pinout real de la entrada analógica conectada a `ao2`.
10. **Sistema de coordenadas EVF de la EOS 500D** (204-04, M04-14): leer `kEdsPropID_Evf_CoordinateSystem` y el tamaño del JPEG EVF.
11. **Signos físicos de los ejes en cámara** (103-02) y **accesorio o bornera real** de los conectores 0/1 del 6353 (202-11).

## Documentos sin hallazgos relevantes

**Ninguno.** Los 10 documentos del lote tienen al menos un hallazgo MEDIA o superior. Los que quedan más cerca de ser correctos son SYS-103 (sólo un MEDIA: 103-01, más imprecisiones BAJA) y SYS-204 (un ALTA: 204-02; el resto de sus citas al SDK de Canon se confirmaron línea por línea).

## Efecto sobre las fuentes locales "confiables"

- `.claude/shared/lab-invariants.md` §2, fila 📄 "Obturadores digitales `Dev1/port0/line0:3`": **contradicha por `config.py:66`**. Los obturadores están en line11/8/9/10. Conviene convertir la fila en ✅ contra `config.py::SHUTTER_CHANNELS` y agregar `SHUTTER_POLARITY`.
- `lab-invariants.md` §2, fila 📄 "Fotodiodo `Dev1/ai0`, ≤ 10 kHz": la tasa intra-bloque es 10 kHz (`trace.py:501`), pero la serie efectiva es de ~28 Hz (102-02).
- `lab-invariants.md` §1, fila ✅ "Límite de recorrido 100 µm": verificada contra el código, pero **no** contra el hardware (205-01). El ✅ sólo garantiza coherencia entre prompt y código, no con la física.
- El prompt del agente `instrumentation` (§1 "shutter lines drop to ground (fail-safe close)", §3 regla 3 "GCSError ≠ IOError") repite 201-02 y 205-02.
- DEC-011 (base de SYS-205) parte de la misma premisa errónea sobre -1004 (205-03). Recomiendo registrar un DEC correctivo.

## Resumen de conteos

168 afirmaciones auditadas. Veredicto principal: 76 CONTRADICHO, 72 CONFIRMADO (incluye "en parte"), 18 SIN FUENTE, 2 CITA ERRÓNEA. Otras 9 llevan además la marca REQUIERE BANCO.
Severidad: 20 CRÍTICA, 13 ALTA, 33 MEDIA, 56 BAJA, 46 sin severidad (confirmadas).
