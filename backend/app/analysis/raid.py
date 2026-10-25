"""Raid potential of one Pokémon: where it would rank among all attackers of one type.

Pure code on top of :class:`GameData`, documented in ``docs/ANALYSIS_ENGINE.md``.

Reference field
    For every form in the active dataset (duplicates by species, types and stats removed)
    and every attacking type, the best neutral DPS with a fast and a charged move of that
    type, at the dataset's maximum normal level with 15 Attack IV. All moves the species can
    have count, including Elite TM and legacy moves. Mega and Primal forms are not separate
    forms in the dataset and are not part of the field.
    Species that exist as Shadow Pokémon are in the field twice: regular and Shadow, because
    both are used as raid attackers.

This Pokémon
    The same DPS for the Pokémon itself and every form it can evolve into, with its own
    Attack IV, the Shadow attack bonus when it applies and the moves it can actually get:
    its current moves (only while it does not evolve), the normal TM pool, and the Elite TM
    pool when the user has Elite TMs.

The result is a rank: 1 means no other species of that type would deal more damage. Other
forms of the same species are not counted, so a Pokémon is never compared with itself.
"""

from __future__ import annotations

import bisect
import statistics
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from threading import Lock
from typing import Any

from app.analysis.evolution import evolution_paths
from app.analysis.pve import boss_defense, moveset_dps
from app.gamedata.model import GameData

REFERENCE_ATTACK_IV = 15


@dataclass(frozen=True, slots=True)
class RaidPotential:
    type: str
    rank: int
    dps: float
    target_key: str
    target_name: str
    is_evolution: bool
    fast: str
    charged: str


@dataclass(frozen=True, slots=True)
class _TypeField:
    ascending: list[float]
    by_dex: dict[int, list[float]]

    def rank(self, dps: float, own_dex: int) -> int:
        higher = len(self.ascending) - bisect.bisect_right(self.ascending, dps)
        same_species = sum(1 for value in self.by_dex.get(own_dex, ()) if value > dps)
        return 1 + higher - same_species


@dataclass(frozen=True, slots=True)
class _Reference:
    fields: dict[str, _TypeField]
    defense: float


class _ReferenceCache:
    """One reference field per Game Data version. Built on first use, then shared."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._cache: dict[int, _Reference] = {}

    def get(self, gd: GameData) -> _Reference:
        with self._lock:
            cached = self._cache.get(gd.version_id)
            if cached is None:
                cached = _build_reference(gd)
                self._cache = {gd.version_id: cached}
            return cached


REFERENCE = _ReferenceCache()


def _neutral(_: str) -> float:
    return 1.0


def _defense(gd: GameData) -> float:
    values = [int(f["stats"]["def"]) for f in gd.forms.values() if f.get("stats")]
    return boss_defense(int(statistics.median(values))) if values else boss_defense(0)


def _by_kind(gd: GameData, keys: Iterable[str]) -> tuple[set[str], set[str]]:
    fast: set[str] = set()
    charged: set[str] = set()
    for key in keys:
        move = gd.moves.get(key)
        if move is None or not move.get("pve"):
            continue
        (fast if move.get("kind") == "fast" else charged).add(key)
    return fast, charged


def _best_per_type(
    gd: GameData,
    fast_moves: set[str],
    charged_moves: set[str],
    *,
    attack: float,
    defense: float,
    attacker_types: list[str],
) -> dict[str, tuple[float, str, str]]:
    stab = float(gd.mechanics.get("pve", {}).get("stab") or 1.0)
    best: dict[str, tuple[float, str, str]] = {}
    for fast in sorted(fast_moves):
        move_type = gd.moves[fast]["type"]
        for charged in sorted(charged_moves):
            if gd.moves[charged]["type"] != move_type:
                continue
            result = moveset_dps(
                gd.moves,
                fast,
                charged,
                attack=attack,
                defense=defense,
                attacker_types=attacker_types,
                effectiveness=_neutral,
                stab_multiplier=stab,
            )
            if result is not None and (move_type not in best or result.dps > best[move_type][0]):
                best[move_type] = (result.dps, fast, charged)
    return best


def _all_moves(form: Mapping[str, Any]) -> list[str]:
    return [
        *form.get("fast_moves", []),
        *form.get("charged_moves", []),
        *form.get("elite_fast", []),
        *form.get("elite_charged", []),
        *form.get("legacy_moves", []),
    ]


def _build_reference(gd: GameData) -> _Reference:
    defense = _defense(gd)
    shadow_bonus = float(gd.mechanics.get("pve", {}).get("shadow_attack") or 1.0)
    cpm = gd.cpm(gd.max_level)
    if cpm is None:
        return _Reference({}, defense)
    seen: set[tuple[Any, ...]] = set()
    values: dict[str, list[float]] = defaultdict(list)
    by_dex: dict[str, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    for form in gd.forms.values():
        stats = form.get("stats")
        types = list(form.get("types") or [])
        if not stats or not types:
            continue
        signature = (form["dex"], tuple(types), stats["atk"], stats["def"], stats["sta"])
        if signature in seen:
            continue
        seen.add(signature)
        fast, charged = _by_kind(gd, _all_moves(form))
        attack = (int(stats["atk"]) + REFERENCE_ATTACK_IV) * cpm
        variants = [attack]
        if form.get("shadow"):
            variants.append(attack * shadow_bonus)
        for variant in variants:
            for move_type, (dps, _, _) in _best_per_type(
                gd, fast, charged, attack=variant, defense=defense, attacker_types=types
            ).items():
                values[move_type].append(dps)
                by_dex[move_type][int(form["dex"])].append(dps)
    fields = {
        move_type: _TypeField(sorted(dps_values), dict(by_dex[move_type])) for move_type, dps_values in values.items()
    }
    return _Reference(fields, defense)


def _display_name(form: Mapping[str, Any]) -> str:
    name = str(form.get("name") or form["key"])
    return f"{name} ({form['label']})" if form.get("label") else name


def raid_potential(
    gd: GameData,
    form_key: str,
    attack_iv: int,
    *,
    level: float,
    shadow: bool,
    current_moves: list[str],
    elite_tm_available: bool,
) -> RaidPotential | None:
    """The best rank this Pokémon (or an evolution of it) reaches in any attacking type."""
    form = gd.forms.get(form_key)
    cpm = gd.cpm(level) or gd.cpm(gd.max_level)
    if form is None or cpm is None:
        return None
    reference = REFERENCE.get(gd)
    defense = reference.defense
    shadow_bonus = float(gd.mechanics.get("pve", {}).get("shadow_attack") or 1.0) if shadow else 1.0
    targets: list[tuple[Mapping[str, Any], bool]] = [(form, False)]
    for path in evolution_paths(gd.forms, form_key):
        target = gd.forms.get(path.target_key)
        if target is not None:
            targets.append((target, True))

    best: RaidPotential | None = None
    for target, is_evolution in targets:
        stats = target.get("stats")
        types = list(target.get("types") or [])
        if not stats or not types:
            continue
        pool = [*target.get("fast_moves", []), *target.get("charged_moves", [])]
        if elite_tm_available:
            pool += [*target.get("elite_fast", []), *target.get("elite_charged", [])]
        if not is_evolution:
            pool += current_moves
        fast, charged = _by_kind(gd, pool)
        attack = (int(stats["atk"]) + attack_iv) * cpm * shadow_bonus
        for move_type, (dps, fast_key, charged_key) in _best_per_type(
            gd, fast, charged, attack=attack, defense=defense, attacker_types=types
        ).items():
            type_field = reference.fields.get(move_type)
            if type_field is None:
                continue
            rank = type_field.rank(dps, int(target["dex"]))
            candidate = RaidPotential(
                type=move_type,
                rank=rank,
                dps=round(dps, 2),
                target_key=str(target["key"]),
                target_name=_display_name(target),
                is_evolution=is_evolution,
                fast=fast_key,
                charged=charged_key,
            )
            if best is None or (candidate.rank, -candidate.dps) < (best.rank, -best.dps):
                best = candidate
    return best
