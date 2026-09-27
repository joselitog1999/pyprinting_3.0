# Auditoría escéptica de la documentación — 2026-09-27

**Qué es.** Contraste de 1377 afirmaciones de la documentación de PyPrinting 3.0 / PySpectrum 3.0 (monografías CAT, reportes SYS, manuales MOD, `MANUAL_USUARIO.md` y guías) contra el código, las hojas de datos, las tesis del grupo y la literatura primaria. La pidió el investigador responsable después de que tres reportes resultaran afirmar un pitch de detector de 13 µm, cuando las hojas de datos dicen 8 µm (`DEC-033`).

**Es una foto fechada.** Describe el repositorio del 2026-09-27, con los cambios de `DEC-033`, `DEC-034` y `DEC-036` en el árbol de trabajo. No se actualiza: las correcciones se registran en los documentos corregidos, en `docs/decisions/DECISION_LOG.md` y en `docs/evidence/EVIDENCE_LEDGER.md`. Por eso cita a propósito valores viejos (por ejemplo, líneas digitales que el código ya no usa), y esta carpeta queda fuera del gate `test_documents_cite_only_real_digital_lines`.

## Contenido

| Ruta | Qué contiene |
| :--- | :--- |
| `CONSOLIDADO.md` | Informe consolidado: conteos, defectos de código C-01…C-53, documentación crítica y alta deduplicada D-01…D-41, errores sistémicos S-1…S-15, plan en tandas, pendientes y verificación independiente de los críticos V-01…V-43. **Empezar por acá.** |
| `RESPUESTAS_INVESTIGADOR.md` | Precisiones del investigador posteriores al informe (dos rondas). **Prevalecen sobre el informe y los triages** donde los contradigan. |
| `TRIAGE_TEORICO.md` | Contraste de las inconsistencias teóricas con la bibliografía cargada en `docs/bibliografia/` (T-01…T-26). |
| `TRIAGE_SISTEMA_VS_LEGADO.md` | Contraste de los defectos de sistema con PyPrinting legacy (`Obsidian_Vault/printing2/`) y PySpectrum legacy (`scratch/pyspectrum-legacy/`). |
| `PLAN_CORRECCIONES.md` | Plan de correcciones en fases, armado con todo lo anterior. **Propuesta pendiente de aprobación.** |
| `lotes/L1…L10_*.md` | Los diez informes de lote, con cada afirmación, veredicto, severidad y fuente. |
| `reproduccion/` | Scripts que reproducen los hallazgos numéricos (`l6_tests.py`, `l7_mc_consistency.py`, `l8_check_*.py`) y sus salidas (`_out_*.txt`). Corren contra el código del repositorio en `SAFE_MODE`; no tocan hardware. |
| `fuentes/` | Artículos descargados durante la auditoría y citados en L6: Baek et al. 2015 (arPLS), Ida et al. 2000 (pseudo-Voigt), Wang et al. 2018 (temperatura espinodal del agua). |

## Estado de los hallazgos

- 14 filas críticas quedaron resueltas por `DEC-036` (líneas de obturadores, recorrido Z, `-1004` frente a `7`, reconexión automática, `qONT`, F1/F8, aislamiento de la DAQ). La revisión del consolidado encontró además que `DEC-036` había dado por corregidos `SYS-305`, el prompt de `instrumentation`, el ejemplar de oro y `MOD-13` sin estarlo; se corrigieron el mismo día (ver la nota de revisión en `DEC-036`).
- El resto está pendiente del plan de correcciones, que se arma con las respuestas del investigador.

## Veredictos y severidades

**Veredictos:** CONFIRMADO / CONTRADICHO / SIN FUENTE / CITA ERRÓNEA / REQUIERE BANCO (más DESACTUALIZADO e INEXISTENTE en L9 y L10). **Severidades:** CRÍTICA / ALTA / MEDIA / BAJA.
