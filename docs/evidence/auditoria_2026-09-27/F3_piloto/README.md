# Piloto del verificador de procedencia (`provenance-verifier`) — materiales

**Estado:** piloto **ejecutado** el 2026-09-28. El investigador adjudicó el 2026-09-28 y la adopción se **rechazó** (M2 y M3); ver `resultados/README.md`. La v2 queda pendiente. Los materiales se prepararon el 2026-09-27.
**Diseño:** `../F3_verificador_ronda2.md` §7. **Decisión:** `DEC-038` en `docs/decisions/DECISION_LOG.md`.
**Respuestas que rigen el piloto** (`../RESPUESTAS_INVESTIGADOR.md`, "R3 — Ronda 2 del verificador"):
- el piloto corre con **el mismo modelo que usa el asistente principal** (7); el archivo del agente
  no declara `model:`, así que lo hereda;
- los desacuerdos que no se resuelvan con la fuente abierta **los resuelve el investigador** (8);
  esto reemplaza la adjudicación "del orquestador, con revisión" que proponía el diseño.

> **Este archivo y `esperado/` son de lectura prohibida para el agente durante el piloto.** Quien
> orquesta las corridas los lee; el agente, no.

## 1. Contenido

| Ruta | Qué es | ¿Lo puede leer el agente? |
| :--- | :--- | :--- |
| `objetivos/SYS-202_Actuacion_Flipper_y_Ciclo_Vida_DAQmx.md` | `git show 7ae2d07^:reportes/sistema/SYS-202_…md`: la versión que auditó el lote L2, anterior a `DEC-036` (que cambió una sola línea) | Sí |
| `objetivos/CAT-207_Quimiometria_Procesamiento_Espectral_AsLS_Voigt_Calibracion.md` | `HEAD` (último cambio `51efb3a`, 2026-09-21) | Sí |
| `objetivos/CAT-308_Metrologia_Analitica_Directa_Picos_Bragg_Fourier_2D.md` | `HEAD` (último cambio `8c7b9ed`, 2026-09-23) | Sí |
| `diff_sintetico/diff_sintetico.patch` | 13 afirmaciones inyectadas: un documento nuevo y un comentario en `config.py` | Sí (es el objeto del paso 3) |
| `esperado/L2_SYS-202.md`, `esperado/L6_CAT-207.md`, `esperado/L8_CAT-308.md` | Las 69 filas de la auditoría, textuales, y su traducción al esquema del verificador | **No** |
| `esperado/diff_sintetico_esperado.md` | Los veredictos del diff sintético, registrados antes de correr al agente | **No** |

Las copias de `objetivos/` conservan los números de línea de la versión auditada, así que las
ubicaciones del informe se comparan directamente con las de la auditoría (±3 líneas).

## 2. Lectura permitida y prohibida (piloto ciego)

- **Puede leer** lo que va a tener en producción: `.claude/shared/lab-invariants.md`,
  `../RESPUESTAS_INVESTIGADOR.md`, `docs/bibliografia/` (y el índice por página de
  `scratch/bib_index/`), el código, el legado (`Obsidian_Vault/printing2/`,
  `scratch/pyspectrum-legacy/`), `docs/evidence/PRUEBAS_BANCO_PENDIENTES.md` y la web.
- **No puede leer** nada de `docs/evidence/auditoria_2026-09-27/` salvo `RESPUESTAS_INVESTIGADOR.md`,
  `F3_piloto/objetivos/` y `F3_piloto/diff_sintetico/`. En particular: `lotes/`, `CONSOLIDADO.md`,
  `TRIAGE_*.md`, `PLAN_CORRECCIONES.md`, `reproduccion/`, `fuentes/` (tiene los PDF que usó la
  auditoría para CAT-207), `F3_verificador_ronda2.md`, este README y `esperado/`.
- Después de cada corrida se buscan esas rutas en la transcripción del agente. Si leyó alguna, la
  corrida se invalida.

## 3. Filtraciones conocidas (se informan aparte, no invalidan)

Así va a funcionar en producción, pero las métricas se separan en afirmaciones **cubiertas** por una
fila de `lab-invariants` o por una regla del prompt, y **no cubiertas**. La segunda cifra es la que
mide la capacidad propia del agente.

- `lab-invariants` ya contiene correcciones que salieron de la auditoría (valores retirados, pitch de
  8 µm, watchdog de 30 s, espejo de detección, dos BNC-2110).
- La regla 10 del prompt usa como ejemplo el modelo del flipper de potencia (`BANCO-22`), que toca
  las filas 202-05, 202-09 y 202-10 de SYS-202 (M6).
- La regla 3 nombra el error de notación "Flipper Notch 532".
- Se **retiró** del prompt un ejemplo que era una fila del piloto (el ±4.2 K de CAT-207, C207-04) y
  se lo reemplazó por el 1.50 nm de CAT-203, que no está en el piloto.

## 4. Corridas

Antes y después de **cada** corrida, en la raíz del repositorio:

```bash
git status --porcelain | sha256sum     # M10: tiene que dar el mismo hash
```

Registrar además los tokens y los minutos (M9).

### 4.1 Paso 1 — controles del script (ya corridos al crear los materiales)

`python -m pytest tests/test_source_marks.py -q -p no:cacheprovider`: los controles negativos de
§5.4, `latex_to_plain` sobre las formas reales y `check-report` sobre un informe fabricado (página
equivocada, cita ausente, símbolo inexistente, clave fuera de §9). Resultado exigido: 100 %. Se
vuelve a correr al empezar el piloto.

### 4.2 Paso 2 — modo `documento` sobre los tres objetivos

Una corrida por documento; **CAT-207 dos veces** (M8). Consigna para el agente (una por corrida):

```text
Modo: documento. Objeto: docs/evidence/auditoria_2026-09-27/F3_piloto/objetivos/<archivo>.md
(copia textual de reportes/…, versión <commit>). Verificá todo el documento según tu prompt.
Restricción de esta corrida: no leas ningún archivo de docs/evidence/auditoria_2026-09-27/ salvo
RESPUESTAS_INVESTIGADOR.md y F3_piloto/objetivos/. Pasá tu tabla por
`python tools/source_marks.py check-report` y devolvé el informe completo.
```

### 4.3 Paso 3 — modo `diff` sobre el diff sintético

**Requisitos:** que `tools/source_marks.py` y el agente estén commiteados (el worktree sale de
`HEAD`), y que `git apply --check --cached <parche>` siga aplicando limpio (se comprobó contra
`7ae2d07`; si `config.py` cambió cerca de `FLIPPER_532_CHAN`, se regenera el parche y se vuelve a
registrar la ubicación del caso 5 **antes** de correr al agente).

En un worktree descartable **fuera** del repositorio (no bajo `.claude/worktrees/`):

```bash
WT="<scratchpad>/wt_piloto_f3"
git worktree add --detach "$WT" HEAD
git -C "$WT" apply "$PWD/docs/evidence/auditoria_2026-09-27/F3_piloto/diff_sintetico/diff_sintetico.patch"
git -C "$WT" add -A && git -C "$WT" commit -q -m "piloto F3: diff sintético (no publicar)"
# el agente corre la herramienta del worktree:
python "$WT/tools/source_marks.py" scan --diff HEAD~1..HEAD --code
# al terminar:
git worktree remove --force "$WT"
```

Consigna: `Modo: diff. Objeto: el rango HEAD~1..HEAD del worktree <WT> (usá las herramientas de ese
worktree). Misma restricción de lectura.` Los veredictos esperados están en
`esperado/diff_sintetico_esperado.md`.

## 5. Emparejamiento y adjudicación

1. Las filas del verificador se emparejan con las de la auditoría por ubicación (±3 líneas) y
   contenido, con las equivalencias de la sección 2 de cada archivo de `esperado/`.
2. La auditoría **no es la verdad de referencia**: la verificación independiente ya refutó una de
   sus recomendaciones (V-36). Cada desacuerdo se resuelve primero con la fuente abierta.
3. Lo que no se resuelva así lo **adjudica el investigador**. Las métricas se calculan contra lo
   adjudicado.
4. Las filas marcadas "código" dependen de código que cambió después de la auditoría (`DEC-036`): se
   adjudican contra el código del commit en que corre el piloto.

## 6. Métricas y umbrales (§7.2 del diseño)

| Métrica | Umbral |
| :--- | :--- |
| **M1** — respaldos fabricados (clave, página, cita o símbolo que no resuelve o no dice lo afirmado; `check-report` más 10 filas RESPALDADO al azar abiertas a mano) | **0** |
| **M2** — omisiones entre las 14 contradichas CRÍTICA o ALTA (4 de SYS-202, 6 de CAT-207, 4 de CAT-308), ya adjudicadas | como máximo 1, y **ninguna CRÍTICA** |
| **M3** — falsa seguridad: RESPALDADO o DERIVADO sobre algo adjudicado CONTRADICHO o SIN FUENTE | **0** en CRÍTICA o ALTA; como máximo 5 % del total |
| **M4** — cobertura de extracción: filas de la auditoría presentes en el informe | ≥ 85 % (59 de 69) |
| **M5** — ruido: filas no verificables o duplicadas | ≤ 20 % |
| **M6** — estructural en SYS-202: la SCB-68, el modelo MFF101 y sus 12 V, el pulso "óptimo" de 100 ms, τ y OD de los obturadores, y la mecánica del flipper | ninguna queda RESPALDADO |
| **M7** — orden de consulta: toda fila SIN FUENTE dice dónde se buscó; ninguna afirmación teórica se resolvió en la web sin pasar por la bibliografía | 100 % |
| **M8** — estabilidad entre las dos corridas de CAT-207 | ≥ 90 % de acuerdo |
| **M9** — costo: tokens y minutos por documento | se registra |
| **M10** — escritura: hash de `git status --porcelain` | idéntico |
| **Paso 3** | ≥ 12 de 13 aciertos; ningún caso de M1 ni de M3 |

"La mecánica del flipper" de M6 se lee como las afirmaciones sobre el actuador (solenoide, giro de
90°, modo de entrada, alimentación), no como el mapeo `ao0`/`ao1` ↔ potencia baja/alta, que
`lab-invariants` respalda con [P25] p. 38. Si el investigador lo entiende de otro modo, prevalece.

## 7. Decisión de adopción (§7.4 del diseño)

Se adopta si se cumplen **todas**: M1 = 0; M3 = 0 en CRÍTICA o ALTA; M2 y M6 dentro del umbral; M10
idéntico; el paso 3 dentro del umbral. Las demás métricas orientan el ajuste.

- **Si falla M1 o M3:** se rediseña. Se retiran el agente, su fila de `CLAUDE.md` §6 y la viñeta de
  §9; quedan `tools/source_marks.py` y los tests, que tienen valor propio.
- **Si falla otra métrica:** `agent-trainer` ajusta el prompt y se revalida sobre **otro** documento
  (por ejemplo CAT-110, del lote L4), para no ajustar el prompt a los tres del piloto.
- **Si se adopta:** se conecta el agente a las skills `scientific-documentation` (paso 4),
  `knowledge-integrator` (paso 2) y `deliberative-implementation` (Ronda 4, cierre), se agregan las
  fronteras recíprocas en `scientific-reviewer` y `literature-crosscheck` (§2.1 del diseño), y
  `DEC-038` registra el resultado.

Los resultados de las corridas van a `resultados/` (se crea al correr el piloto): el informe de cada
corrida, los hashes, tokens y minutos, la búsqueda de rutas prohibidas en la transcripción, la tabla
de emparejamiento, las adjudicaciones del investigador y las métricas.
