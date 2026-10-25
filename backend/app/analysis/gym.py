"""Gym defenders: how much damage a Pokémon absorbs before it faints. Documented in
``docs/ANALYSIS_ENGINE.md``, section "Gymverdedigers".

bulk              = effective Defense · HP
effective Defense = (base Defense + Defense IV) · CPM · (Shadow defense multiplier)
HP                = floor((base Stamina + Stamina IV) · CPM)

Damage per hit grows with attack / defense, so the number of hits an attacker needs grows with
Defense times HP. The defender's own attacks and the loss of motivation over time are left out.
"""

from __future__ import annotations

from app.analysis.stats import BaseStats, IVs, hit_points

FULL_VALUE = 100


def effective_defense(base: BaseStats, ivs: IVs, cpm: float, defense_multiplier: float = 1.0) -> float:
    return (base.defense + ivs.defense) * cpm * defense_multiplier


def defender_bulk(base: BaseStats, ivs: IVs, cpm: float, defense_multiplier: float = 1.0) -> float:
    return effective_defense(base, ivs, cpm, defense_multiplier) * hit_points(base, ivs, cpm)


def defender_value(bulk: float, reference: float) -> int | None:
    """0 to 100, where 100 is the strongest defender the Game Data allows in a gym."""
    if reference <= 0:
        return None
    return min(FULL_VALUE, round(FULL_VALUE * bulk / reference))
