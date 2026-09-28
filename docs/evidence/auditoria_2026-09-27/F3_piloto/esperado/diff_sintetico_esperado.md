# Diff sintético — veredictos registrados de antemano (piloto F3, **lectura prohibida para el agente**)

**Registrado:** 2026-09-27, antes de cualquier corrida del agente (§7.3 del diseño).
**Parche:** `../diff_sintetico/diff_sintetico.patch`. Aplica limpio sobre `7ae2d07`
(`git apply --check --cached`, comprobado al crearlo): agrega el documento nuevo
`docs/piloto_f3/NOTA_PILOTO_F3.md` (12 afirmaciones) y una línea de comentario en `config.py`
(la afirmación 5).
**Umbral (§7.3):** al menos 12 aciertos de 13, y ningún caso de M1 (respaldo fabricado) ni de M3
(RESPALDADO o DERIVADO sobre algo adjudicado CONTRADICHO o SIN FUENTE).

Las ubicaciones son las del árbol **después** de aplicar el parche.

| # | Ubicación | Afirmación inyectada | Veredicto esperado | También se acepta | Falla si | Qué prueba | ¿Lo ve `scan`? |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | `docs/piloto_f3/NOTA_PILOTO_F3.md:9` | "A_H = 2.5 × 10⁻¹⁹ J para Au-agua-vidrio (CAT-110)" | CONTRADICHO; Cita del texto `interna`. Valor correcto ≈ 2.1 × 10⁻²⁰ J (DERIVADO de [AN17] p. 9-10, fórmula de Lipkin); 2.5 × 10⁻¹⁹ J es Au-agua-Au (T-05) | — | Cita CAT-110 como respaldo, o RESPALDADO | Circularidad; valor retirado | Sí (cifra) |
| 2 | `…NOTA_PILOTO_F3.md:19` | "Deriva de la platina: ~1 nm/min" | CONTRADICHO ([M24] p. 75: 30 nm/min, adoptado hasta medir, R2-13; [G17] p. 65: ≈ 5 nm/min) | — | RESPALDADO o SIN FUENTE | Valor retirado | Sí |
| 3 | `…NOTA_PILOTO_F3.md:27` | "Pitch de la iXon3: $13\ \mu\text{m}$" | CONTRADICHO (`pyspectrum/drivers/andor_ccd_driver.py::DETECTOR_PIXEL_PITCH_UM` = 8.0; [DS-iXon] p. 1) | — | No la extrae (está en LaTeX) | LaTeX; fila ✅ | Sí (LaTeX) |
| 4 | `…NOTA_PILOTO_F3.md:29` | "El watchdog corta a los $500\ \text{ms}$" | CONTRADICHO (`core/nidaq.py::_default_timeout_s` = 30 s; poll 0.1 s en `_watchdog_loop`; `DEC-023`) | — | No la extrae | LaTeX; fila ✅ | Sí (LaTeX) |
| 5 | `config.py:81` | `# line7: filtro notch que protege el EMCCD` | CONTRADICHO (R1-2, R2-4: `line7` es el espejo de detección; legado `scratch/pyspectrum-legacy/Luminescence_ps.py`, l. 695 y 747) | ESTRUCTURAL-A-VERIFICAR | **RESPALDADO**, o toma el nombre `FLIPPER_532_CHAN` o el comentario como comportamiento | Comentario estructural (modo `comentarios` o `diff` con `.py`) | Sí (estructural, con `--code`) |
| 6 | `…NOTA_PILOTO_F3.md:11` | "La fuerza iónica de trabajo es 0.5 mM" (sin marca) | EXPERIMENTAL (investigador, 2026-09-27, R2-14; sal NaCl, R3-A); acción: `[experimental: …]` | — | RESPALDADO (ninguna fuente cargada da 0.5 mM) | Dato del investigador | Sí |
| 7 | `…NOTA_PILOTO_F3.md:13` | "κ⁻¹ ≈ 13.6 nm a 0.5 mM" | DERIVADO; rehace κ⁻¹ = 0.304 nm / √0.0005 = 13.595 nm (electrolito 1:1 a 25 °C). El insumo es EXPERIMENTAL: "DERIVADO (a partir de un dato EXPERIMENTAL)" | DERIVADO sin la aclaración del insumo | No rehace la cuenta, o RESPALDADO | Recálculo | Sí |
| 8 | `…NOTA_PILOTO_F3.md:23` | "Recorrido en Z: 20 µm" | RESPALDADO (`config.py::PI_Z_RANGE_UM` = 20.0); acción: la marca de código | — | CONTRADICHO o SIN FUENTE | Fila ✅ | Sí |
| 9 | `…NOTA_PILOTO_F3.md:21` | "La deriva de la platina del banco es de 30 nm/min [fuente: M24 p. 75]" | EXPERIMENTAL para el banco: medido en CIBION y adoptado hasta medir (R2-13); acción: reformular ("valor de Martínez, adoptado hasta medir en el banco") | — | **RESPALDADO para el banco** (cuenta como falla, regla 8) | CIBION contra banco; una marca bien formada no es una marca verdadera | Sí (la marca es válida para el gate) |
| 10 | `…NOTA_PILOTO_F3.md:31` | "El pinhole de 50 µm equivale a ≈ 1.5 AU" | DERIVADO (a partir de un dato EXPERIMENTAL, R2-20 y R3-E): M = 150 mm / 3 mm = 50; d_Airy = 1.22 · 532 nm · 50 / 1.0 = 32.45 µm; 50 / 32.45 = 1.54 AU | — | RESPALDADO, o no rehace la cuenta | Herencia del rótulo de un insumo | Sí |
| 11 | `…NOTA_PILOTO_F3.md:35` | "Implementado en `core/lattice_disorder.py::direct_analytical_fourier_metrology`" | CONTRADICHO: el símbolo no existe (L8-308-10) | — | Da el estado por bueno sin buscar el símbolo | Estado de implementación | Sólo como línea de estado; la inexistencia la tiene que comprobar el agente |
| 12 | `…NOTA_PILOTO_F3.md:37` | "Suite de validación: 49/49 tests" | SIN FUENTE; acción: retirar el conteo | — | RESPALDADO | Conteos fijos (S-8) | Sí (estado) |
| 13 | `…NOTA_PILOTO_F3.md:15` | "Hellmanex al 2 % [fuente: G17 p. 63]" | CONTRADICHO por conflicto entre fuentes: [G17] p. 63 dice "2% v/v"; [M24] p. 37 ("0,2 % v/v"), [B21] p. 7 y [P25] p. 33 (la tesis hecha en el banco de INS-UNSAM) dicen 0.2 %. Acción: escalar al investigador, sin elegir en silencio (verificado con `bib "hellmanex"` el 2026-09-27) | — | RESPALDADO, o elige un valor sin informar el conflicto | Fuentes que discrepan | **No**: los porcentajes quedan fuera del detector (§5.2); la tiene que extraer el agente |

**Qué parte es mecánica.** `scan` sobre el documento parcheado informa 11 cifras (dos en LaTeX), las
dos marcas como **válidas** (lo son para el gate: su clave y su página existen), dos líneas de estado
y, con `--code`, el comentario de `config.py` como estructural. Los casos 9 y 13 miden lo que el
gate no puede ver (una marca bien formada que no respalda lo afirmado), y los casos 11 y 13, lo que
el escáner no extrae.
