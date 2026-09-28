# C-01 — Ronda 3 — Auditoría QA/UX del diseño de GUI (`qa-ux-auditor`)

Estado: EN CURSO (2026-09-27). Se escribe sección por sección.

Objeto auditado: `c01_ronda3/gui_design.md` (autor: `scientific-gui-designer`). Esta auditoría es
el segundo par de ojos, independiente: señala defectos, riesgos y omisiones con severidad y
propuesta concreta. **No rediseña.** No se modificó ningún archivo del repositorio salvo este.

**Marcas.**
- **[CÓDIGO]**: leído por mí en la línea citada (printing3 `main`, salvo que diga `printing2/`).
- **[DISEÑO §n]**: sección de `gui_design.md`.
- **[R2-ARQ]**, **[R2-MET]**, **[R2-INS]**: `c01_ronda2/architecture.md`, `metrology.md`,
  `instrumentation.md`.
- **[INV]**: `RESPUESTAS_INVESTIGADOR.md` (rondas 3 a 5). Vinculante.
- **[DERIVADO]**: cálculo mío, con el script indicado.

Severidad:
- **CRÍTICA**: puede abrir un obturador, dejarlo abierto, mover la platina bajo el haz o registrar
  como válido un dato que no lo es, sin que el operador lo vea.
- **ALTA**: induce a error al operador en una decisión de impresión, o pierde datos.
- **MEDIA**: fricción ergonómica o inconsistencia que un operador atento detecta.
- **BAJA**: pulido.

---

## 0. Pendiente

(secciones en redacción)
