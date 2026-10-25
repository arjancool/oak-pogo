"""Field-level comparison between the stored state and a new observation of one Pokémon.

Pure domain code.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from typing import Any

from app.domain.pokemon import NormalizedPokemon

# Changes worth a history entry. Each one maps to a label in the UI ("CP gewijzigd",
# "Geëvolueerd", ...).
SIGNIFICANT_FIELDS = (
    "species_id",
    "form_id",
    "form_name",
    "costume_id",
    "gender",
    "shiny",
    "alignment",
    "lucky",
    "favorite",
    "cp",
    "max_hp",
    "iv_attack",
    "iv_defense",
    "iv_stamina",
    "cp_multiplier",
    "additional_cp_multiplier",
    "move_fast",
    "move_charged_1",
    "move_charged_2",
    "num_upgrades",
    "nickname",
    "location_card",
    "bread_mode",
    "bread_moves",
    "has_mega_evolved",
    "mega_evolved_forms",
    "temp_evolution",
    "tag_ids",
    "traded_at",
    "purified_exclusive_move",
    "limited_identifier",
    "height_m",
    "weight_kg",
    "size_class",
)
# State that changes through normal play without saying anything about the Pokémon itself
# (current HP after a battle, buddy kilometres, battle counters). Updated silently.
QUIET_FIELDS = (
    "hp",
    "buddy_km_walked",
    "buddy_candy_awarded",
    "battles_attacked",
    "battles_defended",
    "extra",
    "caught_at",
    "hatched_from_egg",
    "in_gym",
    "from_fort",
    "origin_case",
    "origin_events",
    "pokeball",
)
STATE_FIELDS = tuple(f.name for f in fields(NormalizedPokemon) if f.name != "source_pokemon_id")


@dataclass(frozen=True, slots=True)
class Diff:
    significant: dict[str, list[Any]]
    quiet: dict[str, list[Any]]

    @property
    def has_changes(self) -> bool:
        return bool(self.significant or self.quiet)


def _comparable(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def diff_state(stored: Mapping[str, Any], observed: NormalizedPokemon) -> Diff:
    significant: dict[str, list[Any]] = {}
    quiet: dict[str, list[Any]] = {}
    for name in SIGNIFICANT_FIELDS:
        old, new = stored.get(name), getattr(observed, name)
        if _comparable(old) != _comparable(new):
            significant[name] = [_comparable(old), _comparable(new)]
    for name in QUIET_FIELDS:
        old, new = stored.get(name), getattr(observed, name)
        if _comparable(old) != _comparable(new):
            quiet[name] = [_comparable(old), _comparable(new)]
    return Diff(significant, quiet)


def snapshot_of(observed: NormalizedPokemon) -> dict[str, Any]:
    """Full state for an APPEARED event, so the history of one Pokémon is reconstructable."""
    return {name: _comparable(getattr(observed, name)) for name in STATE_FIELDS}


def change_labels(changes: Mapping[str, Any]) -> list[str]:
    labels: list[str] = []
    if "species_id" in changes:
        labels.append("evolved")
    if "cp" in changes or "cp_multiplier" in changes:
        labels.append("powered_up")
    if {"move_fast", "move_charged_1", "move_charged_2"} & changes.keys():
        labels.append("moves_changed")
    if "favorite" in changes:
        labels.append("favorite_changed")
    if "tag_ids" in changes:
        labels.append("tags_changed")
    if "lucky" in changes:
        labels.append("lucky_changed")
    if "alignment" in changes:
        labels.append("alignment_changed")
    if "nickname" in changes:
        labels.append("renamed")
    if {"temp_evolution", "has_mega_evolved", "mega_evolved_forms"} & changes.keys():
        labels.append("mega_changed")
    if "bread_moves" in changes or "bread_mode" in changes:
        labels.append("max_changed")
    if not labels:
        labels.append("other")
    return labels
