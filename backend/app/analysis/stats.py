"""Pokémon GO stat formulas. Pure functions; mechanics values come from the active dataset.

CP = max(10, floor((Atk+IVa) · √(Def+IVd) · √(Sta+IVs) · CPM² / 10))
HP = max(10, floor((Sta+IVs) · CPM))
Stat product = (Atk+IVa)·CPM · (Def+IVd)·CPM · HP
"""

from __future__ import annotations

import math
from dataclasses import dataclass

MIN_CP = 10
MIN_HP = 10
CP_DIVISOR = 10


@dataclass(frozen=True, slots=True)
class BaseStats:
    attack: int
    defense: int
    stamina: int


@dataclass(frozen=True, slots=True)
class IVs:
    attack: int
    defense: int
    stamina: int


def combat_power(base: BaseStats, ivs: IVs, cpm: float) -> int:
    value = (
        (base.attack + ivs.attack)
        * math.sqrt(base.defense + ivs.defense)
        * math.sqrt(base.stamina + ivs.stamina)
        * cpm**2
        / CP_DIVISOR
    )
    return max(MIN_CP, math.floor(value))


def hit_points(base: BaseStats, ivs: IVs, cpm: float) -> int:
    return max(MIN_HP, math.floor((base.stamina + ivs.stamina) * cpm))


def stat_product(base: BaseStats, ivs: IVs, cpm: float) -> float:
    attack = (base.attack + ivs.attack) * cpm
    defense = (base.defense + ivs.defense) * cpm
    return attack * defense * hit_points(base, ivs, cpm)


def base_stats_of(form: dict | None) -> BaseStats | None:  # type: ignore[type-arg]
    if not form:
        return None
    stats = form.get("stats") or {}
    try:
        return BaseStats(int(stats["atk"]), int(stats["def"]), int(stats["sta"]))
    except (KeyError, TypeError, ValueError):
        return None
