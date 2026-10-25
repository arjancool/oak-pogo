"""PvP cups from PvPoke: which formats exist and which Pokémon may enter them (ADR-0027).

PvPoke lists the formats it currently shows in ``formats`` and describes each cup in ``cups``
with include and exclude filters. OAK applies those filters the way PvPoke's
``GameMaster.generateFilteredPokemonList`` does, once, when a Game Data version is built. The
result is a list of PvPoke species IDs per cup. Two of PvPoke's own choices are left out on
purpose, because they are not game rules: the minimum stat product (``excludeLowPokemon``) and
the Little Cup rule for Shadow Pokémon below level 8.

A cup with a filter type OAK does not know is not offered at all. Guessing who may enter would
look like an answer without being one.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

# Formats that are not a cup to play: PvPoke's free-form "Custom" format.
SKIPPED_CUPS = frozenset({"custom"})
NO_CAP = 10_000
GREAT_LEAGUE_CP = 2_500  # PvPoke's greatLeagueIneligible list applies below this cap
MAX_CUPS = 30
SUPPORTED_FILTERS = frozenset({"type", "dex", "tag", "cost", "distance", "evolution", "id", "move", "moveType"})


def cup_id(cup: str, cp: int) -> str:
    return f"{cup}-{cp}"


def _evolution_stage(entry: Mapping[str, Any]) -> int:
    family = entry.get("family") or {}
    evolves, parent = bool(family.get("evolutions")), bool(family.get("parent"))
    if evolves and not parent:
        return 1
    if evolves and parent:
        return 2
    if parent:
        return 3
    return 0


class _Species:
    def __init__(self, entry: Mapping[str, Any], move_types: Mapping[str, str]) -> None:
        self.id = str(entry["speciesId"])
        self.dex = entry.get("dex")
        self.types = [t for t in entry.get("types", []) if t and t != "none"]
        self.tags = set(entry.get("tags") or [])
        self.stage = _evolution_stage(entry)
        self.third_move_cost = entry.get("thirdMoveCost")
        self.buddy_distance = entry.get("buddyDistance")
        self.fast = [str(m) for m in entry.get("fastMoves", [])]
        self.charged = [str(m) for m in entry.get("chargedMoves", [])]
        self.move_types = move_types

    def knows_move(self, move_id: str) -> bool:
        wanted = move_id.upper()
        return wanted in self.fast or wanted in self.charged

    def knows_move_type(self, move_type: str) -> bool:
        fast = any(self.move_types.get(m) == move_type and "HIDDEN_POWER" not in m for m in self.fast)
        return fast or any(self.move_types.get(m) == move_type for m in self.charged)


def _matches(species: _Species, flt: Mapping[str, Any], include: bool, filters: int) -> tuple[int, bool]:
    """How many matches ``flt`` adds, and whether it is an explicit species include."""
    values = list(flt.get("values") or [])
    kind = flt.get("filterType")
    if kind == "type":
        return int(any(t in values for t in species.types)), False
    if kind == "dex":
        for low, high in zip(values[::2], values[1::2], strict=False):
            if species.dex is not None and low <= species.dex <= high:
                return 1, False
        return 0, False
    if kind == "tag":
        return sum(1 for tag in values if tag in species.tags), False
    if kind == "cost":
        return int(species.third_move_cost in values), False
    if kind == "distance":
        return int(species.buddy_distance in values), False
    if kind == "evolution":
        return int(species.stage in values), False
    if kind == "id":
        test = species.id
        if not include or flt.get("includeShadows"):
            test = test.replace("_shadow", "").replace("_xs", "")
        if test in values or species.id in values:
            return filters, include
        return 0, False
    if kind == "move":
        return sum(1 for move in values if species.knows_move(str(move))), False
    if kind == "moveType":
        return sum(1 for move_type in values if species.knows_move_type(str(move_type))), False
    raise ValueError(kind)


def allowed(species: _Species, cup: Mapping[str, Any], cp: int) -> bool:
    is_allowed = False
    explicit = False
    for include, filters in ((True, cup.get("include") or []), (False, cup.get("exclude") or [])):
        matched = 0
        required = len(filters)
        for flt in filters:
            leagues = flt.get("leagues")
            if leagues and cp not in leagues:
                required -= 1
                continue
            if flt.get("filterType") == "id" and include and len(filters) > 1:
                required -= 1
            count, explicit_include = _matches(species, flt, include, len(filters))
            matched += count
            explicit = explicit or explicit_include
        if include and matched >= required:
            is_allowed = True
        if not include and matched > 0 and not explicit:
            is_allowed = False
    return is_allowed


LISTED_FILTERS = frozenset({"id", "move"})  # long lists: only their size is kept


def conditions(cup: Mapping[str, Any], cp: int) -> list[dict[str, Any]]:
    """The cup's rules as data, for a description in the user's language."""
    result: list[dict[str, Any]] = []
    for include, filters in ((True, cup.get("include") or []), (False, cup.get("exclude") or [])):
        for flt in filters:
            leagues = flt.get("leagues")
            values = list(flt.get("values") or [])
            if (leagues and cp not in leagues) or not values:
                continue
            kind = str(flt.get("filterType"))
            listed = kind in LISTED_FILTERS
            result.append(
                {
                    "include": include,
                    "kind": kind,
                    "values": [] if listed else values,
                    "count": len(values),
                    "alone": len(filters) == 1,
                }
            )
    return result


def _supported(cup: Mapping[str, Any]) -> bool:
    filters = [*(cup.get("include") or []), *(cup.get("exclude") or [])]
    return all(f.get("filterType") in SUPPORTED_FILTERS for f in filters)


def build_cups(pvpoke: Mapping[str, Any] | None) -> tuple[list[dict[str, Any]], list[str]]:
    """The cups PvPoke shows, with their eligible species. Returns the cups and notes about
    formats that were left out."""
    if not pvpoke:
        return [], []
    cups = {c.get("name"): c for c in pvpoke.get("cups", []) if isinstance(c, Mapping)}
    move_types = {
        str(m["moveId"]): str(m.get("type"))
        for m in pvpoke.get("moves", [])
        if isinstance(m, Mapping) and "moveId" in m
    }
    species = [
        _Species(entry, move_types)
        for entry in pvpoke.get("pokemon", [])
        if isinstance(entry, Mapping) and entry.get("speciesId") and entry.get("released")
    ]
    ineligible = set(pvpoke.get("greatLeagueIneligible") or [])
    result: list[dict[str, Any]] = []
    notes: list[str] = []
    for fmt in pvpoke.get("formats", []):
        if not isinstance(fmt, Mapping) or not fmt.get("showFormat") or fmt.get("hideRankings"):
            continue
        name, cp = fmt.get("cup"), fmt.get("cp")
        if name in SKIPPED_CUPS or not isinstance(name, str) or not isinstance(cp, int):
            continue
        identifier = cup_id(name, cp)
        if any(c["id"] == identifier for c in result):
            continue
        cup = cups.get(name)
        if cup is None:
            notes.append(f"{fmt.get('title', name)}: PvPoke beschrijft deze cup niet")
            continue
        if not _supported(cup):
            notes.append(f"{fmt.get('title', name)}: regels die OAK niet kan toepassen")
            continue
        eligible = sorted(
            s.id for s in species if allowed(s, cup, cp) and not (cp < GREAT_LEAGUE_CP and s.id in ineligible)
        )
        level_cap = cup.get("levelCap")
        result.append(
            {
                "id": identifier,
                "cup": name,
                "name": str(fmt.get("title") or cup.get("title") or name),
                "max_cp": None if cp >= NO_CAP else cp,
                "level_cap": float(level_cap) if isinstance(level_cap, int | float) else None,
                "party_size": cup.get("partySize"),
                "rules": [str(r) for r in fmt.get("rules", []) if isinstance(r, str)],
                "conditions": conditions(cup, cp),
                "link": cup.get("link") if isinstance(cup.get("link"), str) else None,
                "eligible": eligible,
            }
        )
        if len(result) >= MAX_CUPS:
            break
    return result, notes


def ranking_downloads(cups: Iterable[Mapping[str, Any]]) -> dict[str, tuple[str, int]]:
    """Source ID per cup ranking file: ``pvpoke-rankings-<cup id>`` → (cup, cp)."""
    return {f"pvpoke-rankings-{c['id']}": (str(c["cup"]), int(c["max_cp"] or NO_CAP)) for c in cups}
