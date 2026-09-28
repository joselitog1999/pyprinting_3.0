# CAT-207, corrida C (aislada): emparejamiento contra esperado/L6_CAT-207.md

- Agente: ac220b6c5b9ba2d2e. check-report: exit 0. M10: nada escrito en el repositorio.
- Fuentes consultadas: lab-invariants, RESPUESTAS_INVESTIGADOR (R1-11, R2-10, R2-12, R2-18), G17 p. 97, A25 p. 22 y 106, M24 p. 60, Crossref (3 DOI y el ISBN) y la web (scipy, airPLS de los autores).
- Fuga: `git grep` n.º 7 sin filtro. Mostró 4 líneas de `reproduccion/l6_tests.py` (llamadas de la auditoría) y no expuso veredictos. El agente la declaró y dice no haberla usado.
- El informe tiene 34 filas; la auditoría, 28.

| ID | Esperado | Fila del agente | Veredicto del agente | Resultado |
| :-- | :-- | :-- | :-- | :-- |
| 01 | C CRÍTICA (sin η(λ) ni notch) | #21 | C CRÍTICA | ✅ M2 |
| 02 | C CRÍTICA (exponente 3 al contar fotones; se acepta derivarlo a physics-model-review) | #19 | DERIVADO (poblaciones) · SIN FUENTE (exponente 4), cita R2-12 (ω³ al contar fotones) y lo deriva a physics-model-review | ✅ por la derivación aceptada; ⚠ severidad MEDIA, no CRÍTICA |
| 03 | C (validez) ALTA, o advertencia ALTA que nombre el factor de asimetría de SERS | #20 | DERIVADO (álgebra) · C ALTA (T absoluta contra el método relativo a T₀, R2-12) | ⚠ C ALTA sobre la validez, pero por otra razón: no nombra el factor A de SERS. Adjudica el investigador |
| 04 | C/SF ALTA (±4.2 K) | #22 | C · SF, CRÍTICA | ✅ M2 |
| 05 | C ALTA (T de espinodal) | #24 | C ALTA, 594 K [G17 p. 97] | ✅ M2 (594 ± 17 K es la otra fuente de la auditoría) |
| 06 | C (alturas puntuales, no intensidades "integradas") | — | no extraída | ❌ omisión |
| 07 | C (rayos cósmicos) | #13, #14 | C ALTA; w = 5 R · 1.4826 D · k = 5.0 C (con los 3 umbrales reales) | ✅ |
| 08 | R (pseudo-Voigt) | #17 | R · D | ✅ |
| 09 | C parcial (Voigt sin forma cerrada; η ≠ fracción homogénea) | — | no extraída | ❌ omisión |
| 10 | C (normalización por altura) | #16 | D · C | ✅ |
| 11 | C (BWF no existe) | #4 | C · SF · D | ✅ |
| 12 | C (MCR-ALS no existe) | #3 | C ALTA | ✅ |
| 13 | C (p) · R (λ) | #8 | R (p = 10⁻³) · SF (rangos) | ✅ sin falsa seguridad (10⁻³ está dentro del rango recomendado) |
| 14 | C (pentadiagonal, LU) | #5, #6 | C, C (UMFPACK/SuperLU) | ✅ |
| 15 | C (D de tres diagonales) | #5 | C | ✅ |
| 16 | C (criterio de convergencia) | #9 | R · C | ✅ |
| 17 | SF o C marginal (15 ms) | #10 | SF | ✅ |
| 18 | C (falta el valor absoluto en AirPLS) | #11 | C ALTA (código y referencia de los autores con abs) | ✅ |
| 19 | SF (≤ 1.5 canales) | #12 | SF | ✅ |
| 20 | R dentro de la incertidumbre, o C menor (Si) | #18 | SF | ✅ sin falsa seguridad |
| 21 | C ALTA (calibración real) | #27, #28 | C · SF ALTA; C (equivalencia en nm y cm⁻¹) | ✅ M2 |
| 22 | SF (se descarta pcov) | #26, #29 | SF; C · SF ALTA (la covarianza no existe) | ✅ |
| 23 | R (PCA) | #25 | R | ✅ |
| 24 | C/SF (Eilers "1(1), 5") | #30 | SF | ✅ |
| 25 | R (Zhang) | #31 | R | ✅ |
| 26 | C (Le Ru: 2009, ISBN) | #32 | SF, da el ISBN correcto | ✅ |
| 27 | C (Baffou: 2017) | #33 | C | ✅ |
| 28 | R (Tauler) | #34 | R (DOI) | ✅ |

## Métricas

- **M2** (01, 02, 03, 04, 05 y 21): 0 omisiones. Hay dos casos para adjudicar: 02, cubierto por la derivación aceptada, y 03, con otra causa y sin nombrar el factor de asimetría. Con 03 contado como falla, queda 1 falla no CRÍTICA, dentro del umbral.
- **M3**: 0 casos, ni en CRÍTICA/ALTA ni en total.
- **M4**: 26/28 = 92.9 %.
- **Extras valiosos**:
  - El método Levenberg-Marquardt es en realidad TRF, porque las llamadas pasan `bounds` (fila #15).
  - `static_raman.py:698` llama a `calculate_photothermal_temperature` con argumentos que la función no tiene (posible bug).
  - El rótulo "Silicio (Calibración Shamrock)" del código contradice R2-18.
