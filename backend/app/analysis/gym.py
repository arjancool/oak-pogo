"""Gym defenders: how much damage a Pokémon absorbs before it faints. Documented in
``docs/ANALYSIS_ENGINE.md``, section "Gymverdedigers".

bulk              = effective Defense · HP
effective Defense = (base Defense + Defense IV) · CPM · (Shadow defense multiplier)
HP                = floor((base Stamina + Stamina IV) · CPM)

Damage per hit grows with attack / defense, so the number of hits an attacker needs grows with
Defense times HP. The defender's own attacks and the loss of motivation over time are left out.

Gym potential (for the cleanup advice)
    Like the raid position: the bulk this Pokémon, or a form it can evolve into, would have at
    the configured level, ranked among every form the Game Data allows in a gym at the dataset's
    maximum level with perfect Defense and HP IVs. Rank 1 means no other species would be a
    sturdier defender. Other forms of the same species are not counted.
"""

from __future__ import annotations

import bisect
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from threading import Lock
from typing import Any

from app.analysis.evolution import evolution_paths
from app.analysis.stats import BaseStats, IVs, base_stats_of, hit_points
from app.domain.pokemon import IV_MAX
from app.gamedata.model import GameData

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


@dataclass(frozen=True, slots=True)
class GymPotential:
    rank: int
    bulk: float
    target_key: str
    target_name: str
    is_evolution: bool


@dataclass(frozen=True, slots=True)
class _Field:
    ascending: list[float]
    by_dex: dict[int, list[float]]

    def rank(self, bulk: float, own_dex: int) -> int:
        higher = len(self.ascending) - bisect.bisect_right(self.ascending, bulk)
        same_species = sum(1 for value in self.by_dex.get(own_dex, ()) if value > bulk)
        return 1 + higher - same_species


def _build_field(gd: GameData) -> _Field | None:
    if any(form.get("deployable") is None for form in gd.forms.values()):
        return None  # a dataset from before gym eligibility was part of the Game Data
    cpm = gd.cpm(gd.max_level)
    if cpm is None:
        return None
    full = IVs(IV_MAX, IV_MAX, IV_MAX)
    seen: set[tuple[Any, ...]] = set()
    values: list[float] = []
    by_dex: dict[int, list[float]] = defaultdict(list)
    for form in gd.forms.values():
        base = base_stats_of(dict(form)) if form.get("deployable") else None
        if base is None:
            continue
        signature = (form["dex"], base.defense, base.stamina)
        if signature in seen:
            continue
        seen.add(signature)
        bulk = defender_bulk(base, full, cpm)
        values.append(bulk)
        by_dex[int(form["dex"])].append(bulk)
    return _Field(sorted(values), dict(by_dex))


class _FieldCache:
    """One reference field per Game Data version. Built on first use, then shared."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._cache: dict[int, _Field | None] = {}

    def get(self, gd: GameData) -> _Field | None:
        with self._lock:
            if gd.version_id not in self._cache:
                self._cache = {gd.version_id: _build_field(gd)}
            return self._cache[gd.version_id]


FIELD = _FieldCache()


def _display_name(form: Mapping[str, Any]) -> str:
    name = str(form.get("name") or form["key"])
    return f"{name} ({form['label']})" if form.get("label") else name


def gym_potential(
    gd: GameData,
    form_key: str,
    iv_defense: int,
    iv_stamina: int,
    *,
    level: float,
    shadow: bool,
) -> GymPotential | None:
    """The best rank this Pokémon, or an evolution of it, reaches among all gym defenders.
    None when no form it can be is allowed in a gym, or when the Game Data cannot tell."""
    form = gd.forms.get(form_key)
    reference = FIELD.get(gd)
    cpm = gd.cpm(level) or gd.cpm(gd.max_level)
    if form is None or reference is None or cpm is None:
        return None
    multiplier = float(gd.mechanics.get("pve", {}).get("shadow_defense") or 1.0) if shadow else 1.0
    ivs = IVs(0, iv_defense, iv_stamina)
    targets: list[tuple[Mapping[str, Any], bool]] = [(form, False)]
    for path in evolution_paths(gd.forms, form_key):
        target = gd.forms.get(path.target_key)
        if target is not None:
            targets.append((target, True))
    best: GymPotential | None = None
    for target, is_evolution in targets:
        base = base_stats_of(dict(target)) if target.get("deployable") else None
        if base is None:
            continue
        bulk = defender_bulk(base, ivs, cpm, multiplier)
        candidate = GymPotential(
            rank=reference.rank(bulk, int(target["dex"])),
            bulk=round(bulk, 1),
            target_key=str(target["key"]),
            target_name=_display_name(target),
            is_evolution=is_evolution,
        )
        if best is None or (candidate.rank, -candidate.bulk) < (best.rank, -best.bulk):
            best = candidate
    return best
