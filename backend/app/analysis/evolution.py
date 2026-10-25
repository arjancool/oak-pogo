"""Evolution paths and their effect on CP and league eligibility (spec §10.3, §15.2)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

MAX_CHAIN_DEPTH = 3


@dataclass(frozen=True, slots=True)
class EvolutionStep:
    from_key: str
    to_key: str
    candy: int | None
    candy_purified: int | None
    item: str | None
    item_cost: int | None
    lure: str | None
    buddy_km: float | None
    conditions: list[str]
    quest: str | None
    no_candy_cost_via_trade: bool


@dataclass(frozen=True, slots=True)
class EvolutionPath:
    target_key: str
    steps: list[EvolutionStep] = field(default_factory=list)

    @property
    def total_candy(self) -> int | None:
        total = 0
        for step in self.steps:
            if step.candy is None:
                return None
            total += step.candy
        return total


def path_candy(steps: list[EvolutionStep], *, purified: bool) -> int | None:
    """Candy for the whole path. A Purified Pokémon pays the lower cost where the Game Master has one."""
    if any(s.candy is None for s in steps):
        return None
    return sum(s.candy_purified if purified and s.candy_purified is not None else (s.candy or 0) for s in steps)


def _conditions(evo: Mapping[str, Any]) -> list[str]:
    result: list[str] = []
    for flag in (
        "must_be_buddy",
        "only_day",
        "only_night",
        "only_full_moon",
        "only_dusk",
        "only_upside_down",
    ):
        if evo.get(flag):
            result.append(flag)
    if evo.get("gender"):
        result.append(f"gender:{evo['gender']}")
    if evo.get("move_requirement"):
        result.append("move_requirement")
    return result


def evolution_paths(forms: Mapping[str, Mapping[str, Any]], start_key: str) -> list[EvolutionPath]:
    """Every reachable evolution of ``start_key``, as complete paths, nearest first."""
    paths: list[EvolutionPath] = []

    def walk(key: str, steps: list[EvolutionStep], depth: int) -> None:
        if depth >= MAX_CHAIN_DEPTH:
            return
        form = forms.get(key)
        if not form:
            return
        for evo in form.get("evolutions", []):
            target = evo["to"]
            if target not in forms:
                base = target.split(":")[0] + ":"
                if base not in forms:
                    continue
                target = base
            if any(s.to_key == target for s in steps) or target == key:
                continue
            step = EvolutionStep(
                from_key=key,
                to_key=target,
                candy=evo.get("candy"),
                candy_purified=evo.get("candy_purified"),
                item=evo.get("item"),
                item_cost=evo.get("item_cost"),
                lure=evo.get("lure"),
                buddy_km=evo.get("buddy_km"),
                conditions=_conditions(evo),
                quest=evo.get("quest"),
                no_candy_cost_via_trade=bool(evo.get("no_candy_cost_via_trade")),
            )
            new_steps = [*steps, step]
            paths.append(EvolutionPath(target, new_steps))
            walk(target, new_steps, depth + 1)

    walk(start_key, [], 0)
    paths.sort(key=lambda p: len(p.steps))
    return paths
