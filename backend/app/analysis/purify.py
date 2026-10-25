"""What a Shadow Pokémon becomes after purification (ADR-0022). Pure code.

The level and IV rules come from ``mechanics.purification`` in the active dataset, the cost
from the form's ``shadow`` record in the Game Master.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

from app.analysis.league import Subject
from app.analysis.stats import IVs
from app.domain.pokemon import IV_MAX


@dataclass(frozen=True, slots=True)
class Purified:
    subject: Subject
    level: float
    ivs: IVs
    stardust: int | None
    candy: int | None
    # Set when the trainer level is unknown and OAK assumes it does not limit the level.
    assumption: str | None
    source: str | None


def purify(subject: Subject, form: Mapping[str, Any] | None, rules: Mapping[str, Any] | None) -> Purified | str:
    """The purified Pokémon, or the reason it cannot be calculated."""
    if not subject.shadow:
        return "Alleen een Shadow Pokémon kan worden gepurifyd."
    if not rules or not isinstance(rules.get("min_level"), int | float) or not isinstance(rules.get("iv_bonus"), int):
        return "De regels voor purify ontbreken in deze Game Data-versie."
    if subject.ivs is None or subject.level is None:
        return "IV's of level onbekend."
    floor = float(rules["min_level"])
    assumption = None
    if rules.get("capped_by_trainer_level"):
        if subject.trainer_level is None:
            assumption = f"Trainerlevel onbekend. OAK gaat uit van trainerlevel {int(floor)} of hoger."
        else:
            floor = min(floor, float(subject.trainer_level))
    bonus = int(rules["iv_bonus"])
    ivs = IVs(
        min(IV_MAX, subject.ivs.attack + bonus),
        min(IV_MAX, subject.ivs.defense + bonus),
        min(IV_MAX, subject.ivs.stamina + bonus),
    )
    level = max(subject.level, floor)
    shadow = (form or {}).get("shadow") or {}
    return Purified(
        subject=replace(subject, ivs=ivs, level=level, cp=None, shadow=False, purified=True),
        level=level,
        ivs=ivs,
        stardust=shadow.get("purify_stardust"),
        candy=shadow.get("purify_candy"),
        assumption=assumption,
        source=rules.get("source"),
    )
