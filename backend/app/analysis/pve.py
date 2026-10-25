"""A simple, documented PvE damage model for raids (spec §13.1). Documented in
``docs/ANALYSIS_ENGINE.md``.

damage per hit = floor(0.5 · power · attack / defense · STAB · effectiveness) + 1
attack         = (base attack + attack IV) · CPM · (Shadow bonus)
cycle DPS      = (n · fast damage + charged damage) / (n · fast duration + charged duration),
                 n = charged energy cost / fast energy gain

The model ignores energy gained from taking damage, dodging, weather and the boss's own
moves. It ranks attackers against one another; it does not predict a battle outcome.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

MS_PER_SECOND = 1000.0
# Raid bosses are modelled with 15 Defense IV at this CP multiplier (roughly level 40). The
# boss defence is the same for every attacker, so the choice only shifts absolute numbers.
BOSS_CPM_ASSUMPTION = 0.7903
BOSS_IV = 15


@dataclass(frozen=True, slots=True)
class DpsResult:
    dps: float
    fast: str
    charged: str | None
    effectiveness_fast: float
    effectiveness_charged: float | None


def hit_damage(power: float, attack: float, defense: float, stab: float, effectiveness: float) -> int:
    return math.floor(0.5 * power * attack / defense * stab * effectiveness) + 1


def moveset_dps(
    gd_moves: Mapping[str, Mapping[str, Any]],
    fast_key: str,
    charged_key: str | None,
    *,
    attack: float,
    defense: float,
    attacker_types: list[str],
    effectiveness: Any,
    stab_multiplier: float,
) -> DpsResult | None:
    fast = gd_moves.get(fast_key)
    if fast is None or not fast.get("pve") or fast["pve"]["duration_ms"] <= 0:
        return None
    f_eff = effectiveness(fast["type"])
    f_stab = stab_multiplier if fast["type"] in attacker_types else 1.0
    f_dmg = hit_damage(fast["pve"]["power"], attack, defense, f_stab, f_eff)
    f_dur = fast["pve"]["duration_ms"] / MS_PER_SECOND
    f_energy = max(fast["pve"]["energy"], 0)
    best = DpsResult(f_dmg / f_dur, fast_key, None, f_eff, None)
    charged = gd_moves.get(charged_key) if charged_key else None
    if charged is not None and charged.get("pve") and f_energy > 0:
        cost = -charged["pve"]["energy"]
        c_dur = charged["pve"]["duration_ms"] / MS_PER_SECOND
        if cost > 0 and c_dur > 0:
            c_eff = effectiveness(charged["type"])
            c_stab = stab_multiplier if charged["type"] in attacker_types else 1.0
            c_dmg = hit_damage(charged["pve"]["power"], attack, defense, c_stab, c_eff)
            n = cost / f_energy
            cycle = (n * f_dmg + c_dmg) / (n * f_dur + c_dur)
            if cycle > best.dps:
                best = DpsResult(cycle, fast_key, charged_key, f_eff, c_eff)
    return best


def boss_defense(base_defense: int) -> float:
    return (base_defense + BOSS_IV) * BOSS_CPM_ASSUMPTION
