# Plan de correcciones — auditoría documental del 2026-09-27

**Estado:** PROPUESTA para aprobación del investigador. Nada de este plan se ejecutó todavía.

**Insumos:**
- `CONSOLIDADO.md` (hallazgos C-, D-, S-, V-);
- `TRIAGE_TEORICO.md` (T-, contraste con `docs/bibliografia/`);
- `TRIAGE_SISTEMA_VS_LEGADO.md` (contraste con el legado; hallazgos CP-, ACT-, AND, X-01, C-01b);
- `RESPUESTAS_INVESTIGADOR.md` (rondas 1 y 2, que prevalecen sobre todo lo anterior).

## Reglas que gobiernan el plan

1. **Orden de consulta.**
   - En temas teóricos: la bibliografía cargada, después el investigador, después la web.
   - En temas de sistema: el legado funcionaba, así que es la referencia de funcionamiento.
2. **Alcance del protocolo (`CLAUDE.md` §5.0).**
   - Exentas: la documentación pura y los bugs que parten de un test que falla, siempre que no toquen fórmulas, unidades ni incertidumbres.
   - Nunca exentos:
     - mover la platina;
     - obturadores, potencia o tiempos;
     - la política del watchdog;
     - fórmulas;
     - contratos de GUI (estos llevan además Ronda 3);
     - agentes nuevos.
3. **Watchdog:** nunca debe cortar una rutina sana. La protección ante una rutina colgada se hará con un latido de vida de la propia rutina (R2-8).
4. **Documentos que describen código inexistente:** se archivan como *implementables* o *desconocidos* (R1-11); no se borran ni se reescriben.
5. **Métodos en desarrollo** (el Monte Carlo de Debye-Waller): se rotulan **experimentales**, sin presentarlos como validados.

---

## Fase 0 — Medidas inmediatas (hoy, sin código)

| # | Medida | Motivo |
|---|---|---|
| 0.1 | **No desplegar `main` en la PC del laboratorio**, que sigue en `7f5d10a`, hasta corregir C-01 y pasar el Grupo E de `PRUEBAS_BANCO_PENDIENTES.md`. | C-01 (la traza se desborda y lee 0 V) existe sólo en `main` (R2-2). |
| 0.2 | **Anotar el respaldo de offsets del Shamrock:** detector 0, red 87. Falta saber a qué red corresponde el 87 y el offset de la otra. | Prerrequisito del primer arranque de PySpectrum 3.0, que hoy escribe offsets inventados (C-04). |
| 0.3 | Mantener PySpectrum 3.0 **bloqueado contra el hardware**, y sumar al bloqueo el orden cero (C-03) y el espejo de detección (C-08). | Nunca se probó en el banco (R1-6). |
| 0.4 | No usar para resultados publicables las métricas señaladas en `CONSOLIDADO.md` §5.0.3: σ_MC, p de Wilson, ξ, T anti-Stokes absoluta, FWHM con Filtro > 0, coordenadas de Picasso con "+box/2", escala µm/px del Analizador SIF, `t_print_s` del `.h5`. | Defectos confirmados C-11 a C-20. |

## Fase 1 — Fuente única de verdad (`lab-invariants.md`) — exenta

Todo lo demás se apoya en esto, así que va primero. Se hace con `agent-trainer`, porque `lab-invariants.md` es parte del corpus de prompts, y con cada fila acompañada de su fuente.

- **Inventario de hardware**, filas 📄 con la fuente:

  | Componente | Valor |
  |---|---|
  | Placa | PCIe-6353 con dos BNC-2110 |
  | Obturadores | líneas 11/8/9/10; sólo la 11 invertida (R2-1, ✅ ya verificado por el gate) |
  | Espejo de detección | `line7`: *up* = confocal/Canon, *down* = espectrómetro |
  | Filtro de densidad | `ao0`/`ao1`: *up* = baja, *down* = alta |
  | Platina y controlador | P-517.3CD con E-517 |
  | Láser verde | Excelsior-532-150-CDRH |
  | Objetivos | agua NA 1.0 (60x); aire NA 0.5 |
  | Detección confocal | pinhole 50 µm con lente 150 mm, ≈ 1.5 AU |
  | Shamrock | entrada lateral |
  | Calibración λ | con 532 nm cada ~2 meses |
  | Muestras de referencia Raman | Si (sólo verificación) y benzenotiol |

- **Protocolo:**
  - PDDA/PSS con Hellmanex y plasma (T-); Piranha + APTES queda sólo para sustratos SERS (Arias).
  - Fuerza iónica 0.5 mM vigente y 1.5 mM publicada, con κ⁻¹ ≈ 13.6 / 7.9 nm.
  - Deriva 30 nm/min (Martínez §3.5) hasta medir.
  - A_H ≈ 2.1 × 10⁻²⁰ J.
- **Tabla de convenciones canónicas** (corta S-1 y S-5):

  | Magnitud | Convención |
  |---|---|
  | σ | por componente |
  | Debye-Waller estático | en intensidad, exp(−q²σ²) en 2D (bibliografía nueva: Gabrielli 2004, Klatt 2020; la versión en amplitud, de Paddison 2019, se convierte) |
  | ξ | 1/(π·FWHM_f), con la resta del tamaño finito (R2-16) |
  | Unidad de Airy | en diámetro, 1.22λM/NA |
  | p | por conteo (R2-17) |
  | Validación del Monte Carlo | σ ∈ [0, 0.3·a] (R2-19) |

  Cada convención queda atada por el gate a la función que la implementa, cuando la función exista.
- **Gate:**
  - filas ✅ nuevas: bits del ADC (14), `sif_processor` pitch 8 µm, NA de los objetivos en `MICROSCOPE_OBJECTIVES`;
  - un test que rechace los literales "13.0 µm" y "65535" en `pyspectrum/` y `core/` (S-2).

## Fase 2 — Corrección del corpus de agentes (`agent-trainer`) — exenta

- **Prompts a corregir:**
  - `physicist`, `colloidal-chemist` y `experimentalist`: APTES, 0.75 mM como único valor, A_H = 2.5 × 10⁻¹⁹ J;
  - residuos de `instrumentation`;
  - el ejemplar pendiente `metrology_uncertainty_budget_gold.md`.
- **Auditoría sistemática** de todos los prompts, skills y ejemplares. Ningún lote lo hizo (`CONSOLIDADO.md` §6.2.1), y la revisión de hoy ya encontró un ejemplar que enseñaba una espera que nunca espera.
- **Reglas a sembrar en los agentes:** el orden de consulta de fuentes, el legado como referencia, la política del watchdog y el archivado de documentos.

## Fase 3 — Agente verificador nuevo — requiere Rondas 1 y 2

Un agente nuevo nunca está exento. Esta sección es la base de su **Ronda 1**.

- **Propósito:** controlar, **en el momento de escribir**, que todo contenido nuevo o editado en CAT, SYS, MOD, el manual, los ledgers o el corpus de agentes sea veraz y tenga respaldo. Si no lo tiene, se marca **experimental** o **sin fuente**, y no se deja pasar como establecido.
- **Veredictos por afirmación:**

  | Veredicto | Significado |
  |---|---|
  | RESPALDADO | Con fuente: archivo de `docs/bibliografia/` y página, DOI, hoja de datos, código (`archivo:línea`) o dato del investigador con fecha. |
  | EXPERIMENTAL | Método o valor propio en desarrollo. |
  | SIN FUENTE | Bloquea hasta que se agregue la fuente o se rotule. |
  | CONTRADICHO | Bloquea. |

- **Jerarquía de fuentes:** bibliografía cargada, después el investigador, después la web (DOI verificado contra Crossref). Para el comportamiento del sistema: código actual y legado.
- **Qué lo diferencia de lo que ya existe:**
  - `scientific-reviewer` es un árbitro sobre trabajo terminado;
  - `devil-advocate` es adversarial sobre decisiones en curso;
  - la skill `literature-crosscheck` es un procedimiento.

  El nuevo agente es el **control de publicación** de cada texto, con un formato de salida verificable.
- **Complemento automático, a evaluar:** un test del gate que exija que toda cifra física de un CAT o SYS "Implementado" tenga una marca de fuente o de *experimental* (S-8, S-9, S-14).
- **Preguntas de la Ronda 1 para el investigador:**
  1. ¿Debe **bloquear** (obligatorio antes de cada commit que toque documentación) o sólo **advertir**?
  2. ¿Revisa también los comentarios y docstrings del código, o sólo los documentos?
  3. ¿Qué formato de marca de fuente preferís en los `.md`: nota al pie, etiqueta en línea (`[fuente: …]`) o columna en las tablas?
  4. ¿Un dato tuyo sin publicar ("dato del investigador, 2026-09-27") cuenta como RESPALDADO o como EXPERIMENTAL?

## Fase 4 — Documentación (tandas a1-a8 del consolidado) — exenta, con el verificador como control

Se ejecuta después de las fases 1-3, en el orden de riesgo del consolidado §5.1, con estas actualizaciones:

- **a1 — Procedimientos que causan daño:** latencias "< 1 ms" (Pereyra: ventana de 10-100 ms), APTES → PDDA/PSS, mapa DAQ (ya hecho en SYS-305 y MOD-13; faltan MOD-03, MANUAL §5.1 y MOD-14:234), orden cero, "notch" → espejo de detección en todos los documentos, AO2 = 0 V, Slope Min, flipper.
- **Archivado:** los ~20 documentos que describen código inexistente (D-41) van a `reportes/archivo/implementables/` o `reportes/archivo/desconocidos/`, con un índice y las referencias cruzadas corregidas. **Se presenta la lista con la categoría propuesta para cada uno antes de mover nada.**
- **a3:** el pinhole pasa a ≈ 1.5 AU y el objetivo de aire a NA 0.5.
- **a6:** honeycomb (⅓, ⅓) con γ = 60°, ξ, p y Debye-Waller según la tabla de convenciones. CAT-307, la Pestaña 3 y MOD-08 se rotulan **experimentales**.
- **a7 — Ledgers:**
  - PHY-002 (APTES), PHY-005 ((1−p)²) y los residuos de PHY-009;
  - registrar V-02b (termometría de `static_raman`) y X-01 (cerrado).

## Fase 5 — Código exento (b0: bug con test que falla primero)

| ID | Corrección |
|---|---|
| C-21 | Gauss/Donut del contrapropagante con `xo, yo` (se resuelve también dentro de la refactorización de la fase 6, si se hace antes). |
| C-20 | HDF5: no pisar `t_print_s`; un dataset por escaneo. |
| C-16 | Pitch 8 µm en `sif_processor` (fase pendiente de `DEC-033`). |
| C-22 | Planificador de 240 nm del escaneo lineal → `compute_step_centers` (fase pendiente de `DEC-033`). |
| C-35 | Default de Slope Min en 0. |
| C-43 | `LAST_POS_FILE`: usarlo o retirarlo. |
| C-48 | Parser de CSV. |
| C-12 (bug) | Nombres de argumentos en `static_raman.py:698`. **Sólo si** se corrige junto con el método relativo de la fase 7; si no, mostraría una T con la fórmula absoluta. |

## Fase 6 — Código de hardware y seguridad (b1) — Rondas 1 y 2 (Ronda 3 donde hay GUI)

En orden de prioridad:

1. **C-01 — Traza de impresión.** Bloquea el despliegue de `main`. Opciones:
   - volver a la lectura finita por tick que funciona en producción;
   - leer lo disponible, o la muestra más reciente, de la tarea continua.

   En ambos casos, recuperar la cadencia de ≈ 10 ms del legado (C-01b) y agregar un test con un doble que **modele el buffer de DAQmx**.
2. **Latido de vida de las rutinas** (R2-8), que reemplaza al `heartbeat_shutter(30.0)` repartido (C-29). El watchdog corta sólo si la rutina deja de latir.
3. **Espejo de detección** (C-08 reformulado, R2-4, R2-5):
   - persistir el estado;
   - posición requerida por cada rutina (espectro → *down*; confocal/Canon → *up*);
   - un botón de resincronización explícito;
   - renombrar `flipper_notch532` en código y GUI.
4. **Contrapropagante** (R2-7): reutilizar confocal, traza y foco en lugar de la copia; dos escaneos, uno por fotodiodo del láser elegido, en una sola pasada. Corrige CP-1, CP-3, CP-4, CP-6, CP-7 (el 532 fijo en BOT), CP-8 (sin `wait_on_target`) y CP-9/10/13 (botones sin conectar).
5. **Rutinas de grilla de PySpectrum:**
   - ACT-N1: que conmuten potencia y espejo como el legado;
   - AND: que esperen el fin de la exposición;
   - C-10: mapa hiperespectral con `wait_on_target`, una adquisición por nodo y persistencia del cubo.
6. **Driver del Shamrock y la Andor** (C-04 a C-07):
   - offsets como **parámetro dinámico con procedencia** (fecha y método), cargable desde la configuración, editable y **calibrable con la rutina de láser de 532 nm + filtro de densidad**, extendida para calibrar la red y el detector (R2-9, R2-10);
   - rendija con la función vigente y `argtypes`;
   - `ShamrockSetFlipperMirror` con la entrada lateral y relectura;
   - modos de lectura según el SDK (Single-Track = 3).
7. **Resto:**
   - C-03: un solo camino protegido al orden cero;
   - C-30: E-STOP a nivel de aplicación;
   - C-31: inclinación por cuatro esquinas en baja potencia;
   - C-33/C-34: sincronía de la GUI con el watchdog;
   - C-45, C-46;
   - C-44 (`ai3`), después del banco.

## Fase 7 — Código con fórmula científica (b2) — Rondas 1 y 2

| ID | Corrección |
|---|---|
| C-12 | **Termometría por el método del laboratorio:** cocientes S/AS relativos a un espectro de referencia a T₀ conocida (R2-12), con lo que el prefactor y η(λ) se cancelan. Además, áreas ajustadas, u(T) por GUM (la sensibilidad realista es ≈ 10 °C) y el factor A en SERS. |
| C-11 | Monte Carlo con **el mismo estimador** que la medición; test de extremo a extremo σ conocido → σ recuperado en [0, 0.3·a]; rótulo experimental. Cubrir también el caso hexagonal/honeycomb, que ningún lote auditó. |
| C-14 | ξ único según la tabla de convenciones. |
| C-15 | Se retira el p de Wilson y se reporta p por conteo. |
| C-02 | Base canónica honeycomb/hBN (⅓, ⅓) con γ = 60° y presets con b y γ explícitos. Lleva Ronda 3, porque cambia los presets de la GUI. |
| Picasso y localización | C-13 (sin "+box/2" por defecto) y C-19 (`camera_info` real y F² del EMCCD; RL permitido **con advertencia**, R1-5). |
| Resto | C-17, C-18, C-23 a C-28, C-36 a C-40, C-47 y C-50 a C-52, según el consolidado §5.2. |

## Fase 8 — Banco (con aprobación, primero con los láseres apagados)

Orden de las sesiones:

1. **Seguridad:**
   - estado del 532 al encender, con la placa reseteada y con el proceso terminado a la fuerza (`BANCO-16`, R2-3);
   - mapeo línea ↔ obturador (`BANCO-15`, que R2-1 ya adelanta);
   - pérdida de comunicación con la platina (`BANCO-19`).
2. **Cableado:** qué hay en `ai3` (R2-6) y posición del espejo al encender.
3. **Traza:** después de corregir C-01, cadencia y latencia con osciloscopio (B-01, B-07).
4. **Espectrómetro:** respaldar los offsets de las dos redes y después el Grupo C de `PRUEBAS_BANCO_PENDIENTES.md`.
5. **Metrología:** deriva (≥ 1 h tras termalizar), para reemplazar el valor de Martínez.

## Secuencia propuesta

```
Fase 0 (hoy)
   │
   ├─► Fase 1 (invariantes) ─► Fase 2 (agentes) ─► Fase 3 (verificador: Rondas 1-2)
   │                                                     │
   │                                  ┌──────────────────┴──────────────────┐
   │                                  ▼                                     ▼
   │                        Fase 4 (documentación)               Fase 5 (código exento)
   │
   └─► Fase 6.1 (C-01, Rondas 1-2) en paralelo: bloquea el despliegue de main
              │
              ▼
        Fase 6 (resto) ─► Fase 7 ─► despliegue de main en el laboratorio (tras el Grupo E del banco)
```

## Lo que necesito del investigador para arrancar

1. Aprobación del plan, o cambios en el orden.
2. Las cuatro preguntas de la Ronda 1 del verificador (fase 3).
3. El offset de cada red del Shamrock (Fase 0.2).
4. Si la Ronda 1 de C-01 puede arrancar ya, en paralelo con la fase 1.
