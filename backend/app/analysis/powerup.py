"""Power-up costs between two levels (spec §15.1).

Costs per half level come from the dataset (``mechanics.upgrade``). Shadow and Purified
multipliers apply to Stardust and Candy, the Lucky discount to Stardust only. The game does
not document how fractional Candy is rounded; OAK rounds up, which can only overstate a cost.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

HALF_LEVEL = 0.5


@dataclass(frozen=True, slots=True)
class Cost:
    stardust: int
    candy: int
    xl_candy: int
    power_ups: int


def power_up_cost(
    mechanics: Mapping[str, Any],
    from_level: float,
    to_level: float,
    *,
    shadow: bool = False,
    purified: bool = False,
    lucky: bool = False,
) -> Cost | None:
    """Return the cost, or ``None`` when the dataset lacks a value for part of the range."""
    if to_level <= from_level:
        return Cost(0, 0, 0, 0)
    upgrade = mechanics.get("upgrade", {})
    stardust_table: list[int] = upgrade.get("stardust", [])
    candy_table: list[int] = upgrade.get("candy", [])
    xl_table: list[int] = upgrade.get("xl_candy", [])
    xl_from = upgrade.get("xl_min_pokemon_level")

    dust_factor = 1.0
    candy_factor = 1.0
    if shadow:
        dust_factor *= _factor(upgrade, "shadow_stardust_multiplier")
        candy_factor *= _factor(upgrade, "shadow_candy_multiplier")
    if purified:
        dust_factor *= _factor(upgrade, "purified_stardust_multiplier")
        candy_factor *= _factor(upgrade, "purified_candy_multiplier")
    if lucky:
        dust_factor *= _factor(upgrade, "lucky_stardust_multiplier")
    if math.isnan(dust_factor) or math.isnan(candy_factor):
        return None

    stardust = candy = xl_candy = steps = 0
    level = from_level
    while level < to_level - 1e-9:
        index = int(level) - 1
        if index < 0 or index >= len(stardust_table):
            return None
        stardust += math.ceil(stardust_table[index] * dust_factor - 1e-9)
        if xl_from is not None and level >= xl_from:
            xl_index = int(level) - int(xl_from)
            if xl_index >= len(xl_table):
                return None
            xl_candy += math.ceil(xl_table[xl_index] * candy_factor - 1e-9)
        else:
            if index >= len(candy_table):
                return None
            candy += math.ceil(candy_table[index] * candy_factor - 1e-9)
        steps += 1
        level += HALF_LEVEL
    return Cost(stardust, candy, xl_candy, steps)


def _factor(upgrade: Mapping[str, Any], key: str) -> float:
    value = upgrade.get(key)
    return float(value) if isinstance(value, int | float) else math.nan


def reachable_max_level(mechanics: Mapping[str, Any], trainer_level: int | None, *, best_buddy: bool) -> float:
    """Highest level a power-up can reach for this trainer, including the Best Buddy boost."""
    maximum = float(mechanics.get("max_normal_level") or 0)
    above = mechanics.get("allowed_levels_above_player")
    if trainer_level is not None and isinstance(above, int | float):
        maximum = min(maximum, float(trainer_level + above))
    if best_buddy:
        maximum += float(mechanics.get("best_buddy_bonus_levels") or 0)
    return maximum
