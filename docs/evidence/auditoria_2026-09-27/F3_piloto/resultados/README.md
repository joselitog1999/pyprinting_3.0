# Piloto F3 del verificador de procedencia: resultados (2026-09-28)

**Estado:** corridas terminadas y adjudicadas (2026-09-28): el investigador aceptó las ocho recomendaciones de §4. **Adopción rechazada** por M2 y M3 (§7 de `../README.md`). El agente se retiró y su prompt quedó archivado en `../provenance-verifier_v1_retirado.md`. La v2 queda pendiente (`DEC-038`).
**Decisión:** `DEC-038`, en `docs/decisions/DECISION_LOG.md`.
**Commit en que corrió el piloto:** `14c0ea7`. El índice tenía *staged* un arreglo de sintaxis del frontmatter (`: ` → ` — ` en las descripciones de `provenance-verifier` y `agent-trainer`). Sin ese arreglo el agente no se registraba; no cambia su comportamiento.
**Modelo:** el mismo que usa el asistente principal (Opus). El archivo del agente no declara `model:`.

## 1. Corridas

| Corrida | Objeto | Informe | Validez | M9 (tokens / min / usos de herramientas) |
| :--- | :--- | :--- | :--- | :--- |
| Paso 1 | `tests/test_source_marks.py` | — | 82/82 ✅ | — |
| SYS-202 | modo documento | `informes/SYS-202.md` | válida | 208k / 16.0 / 15 |
| CAT-207 A | modo documento | `informes/CAT-207_A_contaminada.md` | **inválida para M8** | — |
| CAT-207 B | modo documento | `informes/CAT-207_B_parcial_contaminada.md` | **inválida** (incompleta) | — |
| CAT-207 C | modo documento, aislada | `informes/CAT-207_C.md` | válida | 235k / 18.3 / 53 |
| CAT-207 D | modo documento, aislada | `informes/CAT-207_D.md` | válida | 251k / 22.4 / 62 |
| CAT-308 | modo documento | `informes/CAT-308.md` | válida con salvedad (fuga de grep) | 203k / 13.9 / 12 |
| Paso 3 | diff sintético en un worktree fuera del repo | `informes/diff_sintetico.md` | válida con salvedad (fuga de grep, **incluye la clave**) | 172k / 13.3 / 17 |

Las cifras de M9 corresponden a la notificación final de cada agente. Las primeras cinco corridas se cortaron por el límite de sesión y se reanudaron en su contexto, así que su costo real es algo mayor.

**Por qué A y B no son independientes.** Las dos corridas escribían en el mismo archivo del scratchpad, y es un error de orquestación. Tras el corte, B escribió sus filas primero. A las tomó como propias "de la sesión previa" y las fusionó con las suyas. Después B leyó el archivo ya mezclado. Por eso se lanzaron C y D, cada una con un archivo exclusivo, con prohibición de leer los demás y con `grep` obligado a excluir `docs/evidence/`.

**Fugas por grep.** CAT-308 y el diff corrieron `git grep` sin filtro de ruta. Su salida mostró líneas de rutas vedadas:
- en CAT-308: `esperado/L8_CAT-308.md`, l. 24 y 55; `lotes/L8`; y `reproduccion/`;
- en el diff: `esperado/diff_sintetico_esperado.md`, que es la clave, y otras.

Ninguno de los dos abrió esos archivos con Read, los dos lo declararon y sus veredictos se apoyan en fuentes propias. En la única fila filtrada de CAT-308, el agente se apartó de la línea que vio. C tuvo una fuga menor, que declaró: 4 líneas de `reproduccion/l6_tests.py`, sin veredictos. D no tuvo ninguna. §2 del README dice que se invalida la corrida que *leyó* una ruta prohibida; si una salida de grep cuenta como lectura, **lo adjudica el investigador** (A-7 abajo).

## 2. Métricas (contra la auditoría; provisionales)

Se usan SYS-202, CAT-207 C (D como réplica) y CAT-308: 21 + 28 + 20 = 69 filas.

| Métrica | Umbral | Resultado | Estado |
| :--- | :--- | :--- | :--- |
| M1: respaldos fabricados | 0 | check-report con exit 0 en todas las corridas de documento. En el diff, 9 avisos de "falta el índice por página": M10 impedía construirlo en el worktree, y el agente abrió cada página. 10 filas RESPALDADO al azar abiertas a mano: 10/10 resuelven y dicen lo que se afirma | ✅ 0 |
| M2: omisiones entre las 14 CRÍTICA o ALTA | ≤ 1, ninguna CRÍTICA | SYS-202: 0/4. CAT-207 C: 0/6 (D también), con C207-03 a adjudicar. **CAT-308: 4/4** (308-01 CRÍTICA DERIVADO; 308-02 y 308-03 DERIVADO/RESPALDADO; 308-04 no extraída) | ❌ **4 (1 CRÍTICA)** |
| M3: falsa seguridad | 0 en CRÍTICA o ALTA; ≤ 5 % del total | **3 en CRÍTICA o ALTA** (308-01, 308-02, 308-03). De severidad menor: 308-06, 308-07 (MEDIA); 202-15 (MEDIA); 202-14 y 202-17 (BAJA). En total 8/69 = 11.6 % | ❌ |
| M4: cobertura | ≥ 85 % (59/69) | 18 + 26 + 15 = 59/69 = 85.5 % (60/69 con D) | ✅ justo |
| M5: ruido | ≤ 20 % | Las filas del agente sin fila en la auditoría son afirmaciones verificables. No se detectan duplicados ni filas inverificables | ✅ (estimado) |
| M6: estructural en SYS-202 | ninguna RESPALDADO | SCB-68: C. MFF101: EAV. 12 V: EAV. 100 ms: C. τ y OD: SF. Mecánica: EAV y SF | ✅ |
| M7: orden de consulta | 100 % | SYS-202, CAT-207 C y D, y el diff siguieron el orden. **CAT-308 no abrió `lab-invariants` ni `RESPUESTAS_INVESTIGADOR`** (ahí R2-17 resolvía 308-01) | ❌ en CAT-308 |
| M8: estabilidad C ↔ D | ≥ 90 % | 25/27 = 92.6 %. Difieren en C207-06 (C no la extrajo) y C207-26 (SF en C, C en D). C207-09 no aparece en ninguna de las dos | ✅ |
| M9: costo | se registra | 170–250k tokens y 13–22 min por documento | — |
| M10: escritura | hash idéntico | `ab3064b1…` antes de la primera corrida, después de cada una y al final | ✅ |
| Paso 3 | ≥ 12/13, sin M1 ni M3 | **13/13**, M1 = 0, M3 = 0; las 3 CRÍTICAS detectadas (salvedad: la fuga de la clave) | ✅ |

**Adopción (§7):** exige M1 = 0, M3 = 0 en CRÍTICA o ALTA, M2 y M6 dentro del umbral, M10 idéntico y el paso 3 dentro del umbral. **Con las adjudicaciones provisionales, falla por M2 y M3, las dos en CAT-308.**

## 3. Causa de la falla (CAT-308)

Las tres causas se pueden atribuir al prompt:

1. **DERIVADO sobre premisas sin respaldo.** El prompt (§4) exige que el DERIVADO se rehaga a partir de insumos respaldados. El agente rehízo el álgebra desde las premisas del propio documento, que no cita fuentes externas y cuyos wikilinks no cuentan por la regla 2. Así certificó derivaciones autoconsistentes que parten de una normalización falsa.
2. **No siguió el orden de consulta.** Las corridas C y D de CAT-207, con el mismo prompt, sí lo siguieron, y pasaron M2 y M3 en un documento con 6 CRÍTICA o ALTA.
3. **Afirmaciones físicas sin cifra, sin cita y sin estado** (por ejemplo, la ley de Friedel en 308-04) quedaron fuera de la extracción.

Un patrón menor en SYS-202: con una afirmación compuesta, el agente verifica la parte verdadera y no ve el detalle contradicho (202-14, 202-15, 202-17).

## 4. Adjudicaciones del investigador (2026-09-28: se aceptaron todas las recomendaciones)

| # | Fila | Pregunta | Adjudicación |
| :--- | :--- | :--- | :--- |
| A-1 | 308-01, 308-02 y 308-03 | ¿Se confirman como CONTRADICHO (normalización por N_det; la MC normaliza por N_occ; p no sale del intercepto de Wilson)? De eso depende M3. 308-01 ya lo respalda R2-17 | Sí: las tres son CONTRADICHO. Falla M3 |
| A-2 | 308-04 | ¿Se confirma la ley de Friedel: I(G) = I(−G), sin simetría de intensidad 3-fold? | Sí: se cumple Friedel; omisión M2 |
| A-3 | C207-03 | C y D dan CONTRADICHO en la validez de la T absoluta (método relativo a T₀, R2-12), pero no nombran el factor de asimetría de SERS. ¿Cuenta como acierto? | Acierto; la v2 nombra la asimetría de SERS |
| A-4 | C207-02 | C y D dan SIN FUENTE para el exponente 4 y lo derivan a `physics-model-review`, con severidad MEDIA y no CRÍTICA. ¿Se acepta? (la clave lo admite) | Acierto; severidad baja, se anota para la v2 |
| A-5 | 202-10 | EAV con severidad ALTA, donde se esperaba CRÍTICA. ¿Es un problema de severidad para `agent-trainer`? | Sí: es un problema de severidad (regla 14) |
| A-6 | diff n.º 9 | "RESPALDADO (valor, CIBION) · EXPERIMENTAL (para el banco)" para la deriva de 30 nm/min. ¿Es acierto? (no cae en la condición de falla) | Acierto; la v2 da un veredicto por afirmación |
| A-7 | fugas | ¿La salida de un grep sin filtro cuenta como "leer" una ruta prohibida (§2)? Si cuenta, se invalidan CAT-308 y el paso 3 | Cuenta como exposición e invalida sólo los aciertos que pudo favorecer. CAT-308 vale; el paso 3 se repite en la v2 |
| A-8 | 202-14, 202-15 y 202-17 | ¿Cuentan para el 5 % de M3? Son de severidad MEDIA y BAJA, por grano grueso | Sí: cuentan (8/69 = 11.6 %) |

## 5. Hallazgos de código del piloto (fuera de su alcance, para el plan)

- `core/nidaq.py::close_all_tasks` (l. 814) sigue sin tomar `_nidaq_lock` y cierra también la tarea de obturadores (202-15 sigue abierta).
- `pyspectrum/modules/static_raman.py:698` llama a `calculate_photothermal_temperature` con nombres de argumento que la función no tiene (corrida C).
- `core/raman_engine.py:41` rotula al silicio "Calibración Shamrock", en contra de R2-18.
- El ajuste de picos corre con TRF (hay `bounds`), no con Levenberg-Marquardt; el ajuste descarta `pcov`.
