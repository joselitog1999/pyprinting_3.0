# -*- coding: utf-8 -*-
"""Confirmación a baja potencia de un nodo expuesto sin decisión (C-01 Ronda 4, R4-3 / R4-17 fase 6;
`ronda2_architecture.md` §4.8, §5.6; `c01_ronda4/experimentalist.md` §2-§3; DEC-051).

Numpy puro, sin Qt. **Entra apagada** (`ConfirmConfig.enabled = False`): se habilita sólo después de BANCO-65 A y B,
de la revisión de metrología y con otra entrada en el DECISION_LOG. Mientras tanto todo nodo "interrupted" queda en
revisión.

Sin BS ([INV-R4] 7): B = V − D (la lectura menos el oscuro, con el obturador cerrado y las mismas luces) y
R = mediana de los bloques de B / B_base. La base es la meseta de alta potencia previa a la captura, dividida por la
atenuación del filtro de densidad medida en la sesión (respuesta Q-5 (b), 2026-10-02; sujeta a BANCO-65 A). Sin
atenuación medida no hay base, y el resultado es "no sé".

| Resultado | Condición (`experimentalist.md` §3.1) |
|---|---|
| `SEEN` (la ve) | R ≥ u_c y s_R ≤ s_max |
| `NOT_SEEN` (no la ve) | R ≤ 1 + δ, δ = máx(3·σ_R, δ_min), s_R ≤ s_max y R ≥ el piso |
| `UNKNOWN` (no sé) | cualquier otro caso: entre los dos, s_R > s_max, R < 0.85, sin base |

El "no sé" nunca se trata como "no la ve": un falso "no la ve" reimprime sobre una NP fija (hasta T_max a alta
potencia), que es peor que una vacancia.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import NamedTuple, Optional, Tuple

import numpy as np


class ConfirmBase(str, Enum):
    SAME_SITE_LOW_PRE = "same_site_low_pre"      # opción (a) de Q-5: una lectura a baja potencia antes de exponer
    HIGH_PLATEAU_SCALED = "high_plateau_scaled"  # opción (b), la elegida: la meseta de alta / la atenuación
    NONE = "none"                                 # opción (c): sin base, todo va a revisión


class ConfirmOutcome(str, Enum):
    SEEN = "seen"
    NOT_SEEN = "not_seen"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ConfirmConfig:
    enabled: bool = False                    # hasta BANCO-65 A y B y la revisión de metrología
    read_ms: float = 100.0
    block_ms: float = 20.0                   # 5 bloques; múltiplo de 20 ms por el zumbido de 50 Hz
    dark_read_ms: float = 100.0
    settle_after_open_ms: float = 50.0       # hasta BANCO-30
    ratio_seen_min: float = 1.20             # u_c, hasta la calibración de la sesión (§3.2)
    delta_min: float = 0.05
    sigma_r: Optional[float] = None          # σ_R de la sesión (§3.2); sin medir, δ = δ_min
    spread_max: float = 0.05                 # s_R
    ratio_floor: float = 0.85                # R menor: la base bajó (foco, alineación, espejo)
    max_reads: int = 2
    base_source: ConfirmBase = ConfirmBase.HIGH_PLATEAU_SCALED
    attenuation: Optional[float] = None      # alta / baja, medida en la sesión (BANCO-65 A); None: sin base

    @property
    def n_blocks(self) -> int:
        return max(1, int(round(self.read_ms / self.block_ms)))


class ConfirmReading(NamedTuple):
    outcome: ConfirmOutcome
    ratio: float
    spread: float
    v: float
    dark: float
    v_base: Optional[float]
    n_blocks: int
    reasons: Tuple[str, ...]


def base_from_high_plateau(plateau_high_v: Optional[float], dark_v: float,
                           attenuation: Optional[float]) -> Optional[float]:
    """V_base a baja potencia (V) a partir de la meseta de alta potencia previa a la captura: el oscuro más la señal de
    la meseta dividida por la atenuación. None si falta la meseta o la atenuación (sin BANCO-65 A)."""
    if plateau_high_v is None or attenuation is None or not np.isfinite(plateau_high_v) or attenuation <= 0:
        return None
    return float(dark_v + (float(plateau_high_v) - float(dark_v)) / float(attenuation))


def classify(v_blocks, dark: float, v_base: Optional[float], cfg: ConfirmConfig = ConfirmConfig()) -> ConfirmReading:
    """Clasifica una lectura: `v_blocks` son las medias de los bloques (V), `dark` el oscuro (V) y `v_base` la base a
    baja potencia (V), o None."""
    blocks = np.asarray(v_blocks, dtype=float).ravel()
    n = int(blocks.size)
    v = float(np.median(blocks)) if n else float("nan")
    reasons = []
    if v_base is None or not np.isfinite(v_base):
        reasons.append("sin base (falta la atenuación medida en la sesión)")
        return ConfirmReading(ConfirmOutcome.UNKNOWN, float("nan"), float("nan"), v, float(dark), None, n,
                              tuple(reasons))
    b_base = float(v_base) - float(dark)
    if n == 0 or not np.all(np.isfinite(blocks)) or b_base <= 0:
        reasons.append("lectura o base inválida")
        return ConfirmReading(ConfirmOutcome.UNKNOWN, float("nan"), float("nan"), v, float(dark), float(v_base), n,
                              tuple(reasons))
    r_blocks = (blocks - float(dark)) / b_base
    ratio = float(np.median(r_blocks))
    q75, q25 = np.percentile(r_blocks, [75, 25])
    spread = float((q75 - q25) / 1.35)
    delta = max(3.0 * cfg.sigma_r, cfg.delta_min) if cfg.sigma_r is not None else cfg.delta_min
    if spread > cfg.spread_max:
        reasons.append(f"dispersión s_R = {spread:.3f} > {cfg.spread_max}")
    if ratio < cfg.ratio_floor:
        reasons.append(f"R = {ratio:.2f} < {cfg.ratio_floor}: la base bajó (foco, alineación o espejo)")
    if not reasons and ratio >= cfg.ratio_seen_min:
        outcome = ConfirmOutcome.SEEN
    elif not reasons and ratio <= 1.0 + delta:
        outcome = ConfirmOutcome.NOT_SEEN
    else:
        if not reasons:
            reasons.append(f"R = {ratio:.2f}, entre 1 + δ = {1 + delta:.2f} y u_c = {cfg.ratio_seen_min:.2f}")
        outcome = ConfirmOutcome.UNKNOWN
    return ConfirmReading(outcome, ratio, spread, v, float(dark), float(v_base), n, tuple(reasons))
