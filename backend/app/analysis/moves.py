"""How a move can be obtained, and what a moveset change would need (spec §12.4)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class Availability(StrEnum):
    NORMAL_TM = "normal_tm"
    ELITE_TM = "elite_tm"
    LEGACY = "legacy"
    SPECIAL = "special"  # Frustration (Shadow) and Return (Purified)
    NOT_LEARNABLE = "not_learnable"


def availability(form: Mapping[str, Any], move_key: str) -> Availability:
    if move_key in form.get("fast_moves", []) or move_key in form.get("charged_moves", []):
        return Availability.NORMAL_TM
    if move_key in form.get("elite_fast", []) or move_key in form.get("elite_charged", []):
        return Availability.ELITE_TM
    shadow = form.get("shadow") or {}
    if move_key in (shadow.get("shadow_move"), shadow.get("purified_move")):
        return Availability.SPECIAL
    if move_key in form.get("legacy_moves", []):
        return Availability.LEGACY
    return Availability.NOT_LEARNABLE


@dataclass(frozen=True, slots=True)
class MoveNeed:
    slot: str  # fast | charged | unlock
    current: str | None
    target: str | None
    availability: Availability | None
    # none | fast_tm | charged_tm | elite_fast_tm | elite_charged_tm | unlock | impossible
    action: str
    # Moves a normal TM can roll. A normal TM picks at random from the pool minus the current
    # move, so more than one TM can be needed. An Elite TM lets the player choose.
    pool_size: int | None = None


def moveset_needs(
    form: Mapping[str, Any],
    current_fast: str | None,
    current_charged: list[str],
    target: list[str],
    *,
    second_move_unlocked: bool,
) -> list[MoveNeed]:
    """Steps from the current moveset to ``target`` = [fast, charged, (charged)]."""
    if not target:
        return []
    needs: list[MoveNeed] = []
    fast_target = target[0]
    fast_availability = availability(form, fast_target)
    if current_fast == fast_target:
        needs.append(MoveNeed("fast", current_fast, fast_target, fast_availability, "none"))
    else:
        needs.append(
            MoveNeed(
                "fast",
                current_fast,
                fast_target,
                fast_availability,
                _tm(fast_availability, "fast"),
                len(form.get("fast_moves", [])),
            )
        )
    charged_targets = target[1:]
    if len(charged_targets) > len(current_charged) and not second_move_unlocked:
        needs.append(MoveNeed("unlock", None, None, None, "unlock"))
    for move in charged_targets:
        move_availability = availability(form, move)
        if move in current_charged:
            needs.append(MoveNeed("charged", move, move, move_availability, "none"))
        else:
            needs.append(
                MoveNeed(
                    "charged",
                    None,
                    move,
                    move_availability,
                    _tm(move_availability, "charged"),
                    len(form.get("charged_moves", [])),
                )
            )
    return needs


def _tm(value: Availability, kind: str) -> str:
    if value is Availability.NORMAL_TM:
        return f"{kind}_tm"
    if value is Availability.ELITE_TM:
        return f"elite_{kind}_tm"
    return "impossible"
