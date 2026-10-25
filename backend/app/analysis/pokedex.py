"""Pokédex: look up any species in the active Game Data, and find what evolves into it.

Searching
    By name or by Pokédex number. Names are compared without accents, case or punctuation, so
    ``flabebe`` finds Flabébé and ``mr mime`` finds Mr. Mime. A name that starts with the query
    comes before a name that only contains it.

Forms
    The Game Master has a base template (``668:``) next to the ``<SPECIES>NORMAL`` form
    (``668:PYROARNORMAL``) for many species. They are the same Pokémon, so the Pokédex shows one
    of them and treats both as the same evolution target.

What evolves into a form
    Every form that reaches it within ``MAX_CHAIN_DEPTH`` evolutions, found by walking the
    ``parents`` links upwards and then taking the real evolution paths downwards, so costs and
    conditions are exactly the ones the evolution planner shows.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.analysis.evolution import MAX_CHAIN_DEPTH, EvolutionPath, evolution_paths
from app.gamedata.model import GameData
from app.gamedata.transform import norm_key

MAX_RESULTS = 50


def search_key(value: str) -> str:
    """Upper case letters and digits only, without accents: ``Flabébé`` becomes ``FLABEBE``."""
    decomposed = unicodedata.normalize("NFKD", value)
    return norm_key("".join(c for c in decomposed if not unicodedata.combining(c)))


@dataclass(frozen=True, slots=True)
class SpeciesHit:
    dex: int
    name: str
    types: list[str]


def search_species(gd: GameData, query: str, limit: int = MAX_RESULTS) -> list[SpeciesHit]:
    text = query.strip().lstrip("#")
    if not text:
        return []
    wanted = search_key(text)
    starts: list[tuple[int, Mapping[str, Any]]] = []
    contains: list[tuple[int, Mapping[str, Any]]] = []
    for dex_text, record in gd.species.items():
        dex = int(dex_text)
        if text.isdigit():
            if dex == int(text):
                starts.append((dex, record))
            continue
        name = search_key(str(record["name"]))
        if name.startswith(wanted):
            starts.append((dex, record))
        elif wanted and wanted in name:
            contains.append((dex, record))
    hits = []
    for dex, record in [*sorted(starts, key=lambda x: x[0]), *sorted(contains, key=lambda x: x[0])][:limit]:
        main = default_form(gd, dex)
        hits.append(SpeciesHit(dex, str(record["name"]), list(main.get("types", [])) if main else []))
    return hits


def _normal_key(gd: GameData, dex: int) -> str | None:
    record = gd.species_record(dex)
    return f"{dex}:{norm_key(record['key'])}NORMAL" if record else None


def same_pokemon(gd: GameData, key: str) -> set[str]:
    """``key`` and the form the Game Master keeps as a duplicate of it (base and NORMAL)."""
    dex = int(key.partition(":")[0])
    base, normal = f"{dex}:", _normal_key(gd, dex)
    if key in (base, normal):
        return {k for k in (base, normal) if k is not None and k in gd.forms}
    return {key}


def shown_key(gd: GameData, key: str) -> str:
    """The key the Pokédex shows for ``key``: the NORMAL form instead of its base template."""
    dex = key.partition(":")[0]
    if key == f"{dex}:":
        normal = _normal_key(gd, int(dex))
        if normal is not None and normal in gd.forms:
            return normal
    return key


def species_forms(gd: GameData, dex: int) -> list[str]:
    """The forms to show for a species: the base template only when there is no NORMAL form."""
    record = gd.species_record(dex)
    if record is None:
        return []
    keys = [k for k in record.get("forms", []) if k in gd.forms]
    normal = _normal_key(gd, dex)
    if normal in keys:
        keys = [k for k in keys if k != f"{dex}:"]
    return sorted(keys, key=lambda k: (k not in (normal, f"{dex}:"), k))


def default_form(gd: GameData, dex: int) -> Mapping[str, Any] | None:
    keys = species_forms(gd, dex)
    return gd.forms.get(keys[0]) if keys else None


def paths_into(gd: GameData, target_key: str) -> dict[str, list[EvolutionPath]]:
    """Per starting form: the evolution paths that end in ``target_key`` (or its duplicate)."""
    targets = same_pokemon(gd, target_key)
    ancestors: set[str] = set()
    frontier = set(targets)
    for _ in range(MAX_CHAIN_DEPTH):
        parents = {p for key in frontier for p in gd.forms.get(key, {}).get("parents", [])}
        frontier = parents - ancestors - targets
        if not frontier:
            break
        ancestors |= frontier
    result: dict[str, list[EvolutionPath]] = {}
    for start in sorted(ancestors):
        paths = [p for p in evolution_paths(gd.forms, start) if p.target_key in targets]
        if paths:
            result[start] = paths
    return result


def evolves_from(gd: GameData, target_key: str) -> list[str]:
    """The forms that evolve directly into ``target_key``."""
    targets = same_pokemon(gd, target_key)
    found = {shown_key(gd, p) for key in targets for p in gd.forms.get(key, {}).get("parents", [])}
    return sorted(found - targets)
