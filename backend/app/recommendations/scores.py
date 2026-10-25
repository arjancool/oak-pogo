"""Battle score and keep score (ADR-0019). Pure and deterministic.

Battle score (0–100)
    What this individual can do in battle, from facts only: its IV rank for the species it
    can become, how competitive that species is (PvPoke rankings), whether it can get the
    moves that make it good, and where it would rank as a raid attacker. Favorite status,
    catch year and other collector traits never enter it.

    Every league and the raid analysis give a value from 0 to 100. The battle score is the
    highest of them, not the sum: the same IVs show up in every league, and adding the values
    up would count them more than once. The parts list shows every value.

Keep score (0–100)
    How much reason there is to keep this individual: a configurable share of the battle
    score, being the best copy of its kind, collector traits, favorite status and the user's
    own plans. Each property counts once, in one part. IVs count only through the battle score.

Hard protections (vintage, manual, rules) are not part of either score. A vintage Pokémon
with a keep score of 5 is still protected.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from app.analysis.league import LeagueTarget
from app.recommendations.model import PokemonView
from app.recommendations.rules import IV_RANK_MAX, SCORE_MAX, CleanupRules

LEAGUE_LABELS = {"great": "Great League", "ultra": "Ultra League", "master": "Master League"}
# A target whose best moves need an Elite TM the user does not have, or a legacy move this
# Pokémon does not know, is worth less: the moveset OAK can recommend instead is weaker.
MOVESET_PENALTY = 0.9
PLAN_ACTIONS_THAT_KEEP = {"keep", "evolve", "power_up", "trade", "purify", "tm", "mega", "buddy"}
TYPE_LABELS = {
    "normal": "Normaal",
    "fighting": "Vechten",
    "flying": "Vliegend",
    "poison": "Gif",
    "ground": "Grond",
    "rock": "Gesteente",
    "bug": "Insect",
    "ghost": "Geest",
    "steel": "Staal",
    "fire": "Vuur",
    "water": "Water",
    "grass": "Gras",
    "electric": "Elektrisch",
    "psychic": "Psychisch",
    "ice": "IJs",
    "dragon": "Draak",
    "dark": "Duister",
    "fairy": "Fee",
}


@dataclass(slots=True)
class Score:
    score: int | None
    parts: list[dict[str, Any]] = field(default_factory=list)
    basis: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"score": self.score, "basis": self.basis, "parts": self.parts}


@dataclass(frozen=True, slots=True)
class GroupPosition:
    """Place of a Pokémon within its group (same form and Shadow status), best first."""

    rank: int
    size: int


def _part(code: str, text: str, value: float, **data: Any) -> dict[str, Any]:
    return {"code": code, "text": text, "value": round(value, 1), **({"data": data} if data else {})}


def iv_quality(rank: int) -> float:
    """1.0 for IV rank 1, 0.5 for rank 64, 0.0 for rank 4096: a logarithmic scale, because the
    difference between rank 1 and 10 matters far more than between 3000 and 3010."""
    return max(0.0, 1.0 - math.log(max(rank, 1)) / math.log(IV_RANK_MAX))


def species_weight(species_rank: int | None, rules: CleanupRules) -> float:
    if species_rank is None or species_rank >= rules.meta_rank_threshold:
        return 0.0
    if species_rank <= rules.species_rank_full:
        return 1.0
    return (rules.meta_rank_threshold - species_rank) / (rules.meta_rank_threshold - rules.species_rank_full)


def moveset_factor(view: PokemonView, target: LeagueTarget) -> tuple[float, str | None]:
    advice = target.moveset
    if advice is None or advice.source != "pvpoke_usage_filtered":
        return 1.0, None
    special = [*advice.elite_moves, *advice.unavailable]
    if not target.is_evolution and special and all(move in view.moves for move in special):
        return 1.0, "kent de speciale aanval al"
    return MOVESET_PENALTY, "de beste aanvallen zijn niet beschikbaar"


def raid_value(rank: int, rules: CleanupRules) -> float:
    return max(0.0, 1.0 - (rank - 1) / rules.raid_top_n)


def battle_score(view: PokemonView, rules: CleanupRules) -> Score:
    parts: list[dict[str, Any]] = []
    for league, label in LEAGUE_LABELS.items():
        target = view.primary.get(league)
        if target is None:
            continue
        weight = species_weight(target.species_rank, rules)
        quality = iv_quality(target.rank)
        factor, note = moveset_factor(view, target)
        value = SCORE_MAX * weight * quality * factor
        species = f"soortrang {target.species_rank}" if target.species_rank is not None else "geen PvPoke-ranking"
        text = f"{label}: {target.target_name}, {species}, IV-rang {target.rank}"
        if note:
            text += f", {note}"
        parts.append(
            _part(
                league.upper(),
                text,
                value,
                target=target.target_name,
                species_rank=target.species_rank,
                iv_rank=target.rank,
                species_weight=round(weight, 3),
                iv_quality=round(quality, 3),
                moveset_factor=factor,
            )
        )
    if view.raid is not None:
        raid = view.raid
        value = SCORE_MAX * raid_value(raid.rank, rules)
        type_label = TYPE_LABELS.get(raid.type, raid.type)
        parts.append(
            _part(
                "RAID",
                f"Raids: {raid.target_name} zou #{raid.rank} van alle {type_label}-aanvallers zijn",
                value,
                target=raid.target_name,
                type=raid.type,
                rank=raid.rank,
                dps=raid.dps,
            )
        )
    if not parts:
        return Score(0, [_part("NO_BATTLE_ROLE", "Geen league- of raidwaarde gevonden", 0.0)], None)
    best = max(parts, key=lambda p: p["value"])
    return Score(round(best["value"]), parts, best["code"])


def group_positions(members: list[PokemonView], battle: dict[int, Score]) -> dict[int, GroupPosition]:
    ordered = sorted(members, key=lambda m: comparison_key(m, battle[m.id]))
    return {m.id: GroupPosition(index + 1, len(members)) for index, m in enumerate(ordered)}


def comparison_key(view: PokemonView, battle: Score) -> tuple[Any, ...]:
    """Best first: battle score, then IV percentage, then CP. The id makes it deterministic."""
    return (-(battle.score if battle.score is not None else -1), -(view.iv_percent or 0), -(view.cp or 0), view.id)


def _traits(view: PokemonView, rules: CleanupRules) -> list[tuple[str, str, int]]:
    traits: list[tuple[str, str, int]] = []
    if view.shiny:
        traits.append(("SHINY", "Shiny", rules.keep_points_shiny))
    if view.lucky:
        traits.append(("LUCKY", "Lucky", rules.keep_points_lucky))
    if view.species_class in ("legendary", "mythical", "ultra_beast"):
        label = {"legendary": "Legendary", "mythical": "Mythical", "ultra_beast": "Ultra Beast"}[view.species_class]
        traits.append(("RARITY", label, rules.keep_points_rarity))
    if view.costume:
        traits.append(("COSTUME", "Kostuum", rules.keep_points_costume))
    if view.location_card:
        traits.append(("LOCATION_CARD", "Speciale achtergrond", rules.keep_points_location_card))
    if view.event:
        traits.append(("EVENT", "Event-Pokémon", rules.keep_points_event))
    if view.gigantamax or view.dynamax:
        traits.append(("MAX", "Gigantamax" if view.gigantamax else "Dynamax", rules.keep_points_max))
    if view.mega_progress:
        traits.append(("MEGA", "Mega-voortgang", rules.keep_points_mega))
    return traits


def keep_score(view: PokemonView, battle: Score, position: GroupPosition | None, rules: CleanupRules) -> Score:
    parts: list[dict[str, Any]] = []
    if battle.score is None:
        parts.append(_part("BATTLE", "Bruikbaarheid onbekend", 0.0))
    else:
        points = battle.score * rules.keep_weight_battle / SCORE_MAX
        parts.append(
            _part("BATTLE", f"Bruikbaarheid {battle.score} × {rules.keep_weight_battle}%", points, battle=battle.score)
        )
    if position is not None and position.rank == 1:
        text = f"Beste van {position.size} exemplaren"
        if position.size == 1:
            text = "Enige exemplaar van deze soort en vorm"
        parts.append(_part("BEST_COPY", text, rules.keep_points_best_copy, size=position.size))
    traits = _traits(view, rules)
    if traits:
        total = sum(points for _, _, points in traits)
        capped = min(total, rules.keep_traits_cap)
        names = ", ".join(name for _, name, _ in traits)
        text = f"Bijzonder: {names}" + (f" (maximaal {rules.keep_traits_cap})" if capped < total else "")
        parts.append(_part("TRAITS", text, capped, traits=[code for code, _, _ in traits]))
    if view.favorite:
        parts.append(_part("FAVORITE", "Favoriet", rules.keep_points_favorite))
    if view.nicknamed:
        parts.append(_part("NICKNAME", "Heeft een bijnaam", rules.keep_points_nickname))
    if view.planned_action in PLAN_ACTIONS_THAT_KEEP:
        parts.append(_part("PLANNED", "Je hebt een plan voor deze Pokémon", rules.keep_points_planned))
    total = sum(p["value"] for p in parts)
    return Score(round(min(SCORE_MAX, max(0.0, total))), parts)
