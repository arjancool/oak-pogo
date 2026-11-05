"""Search strings for the in-game Pokémon box, bundled and checked against the collection.

Pokémon GO has no parentheses: a comma means "or" and ``&`` means "and". A bundle such as
``653,659&cp569,cp435`` therefore finds every Pokémon of one of those species with one of
those CPs, also a second Fennekin that happens to have CP 435. OAK knows the whole collection
and only puts a Pokémon in a bundle when the bundle then finds exactly its members, according
to the last sync. Pokémon caught after that sync are unknown, so the player still checks in
the game what the search selects.

Pure domain code: the caller supplies the Pokémon of the box.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

MAX_BUNDLE = 10

# Terms that make a search extra safe, in the order they appear in the search string. A bundle
# leaves out a term that would hide one of its own members, such as "!favorite" for a
# favorite the player confirmed.
SAFETY_TERMS = ("favorite", "shiny", "lucky", "4*", "legendary", "mythical", "shadow", "costume")


@dataclass(frozen=True, slots=True)
class BoxPokemon:
    """A Pokémon in the box as the search sees it.

    ``has`` holds the safety terms the Pokémon certainly matches. ``maybe`` also holds the
    terms OAK cannot rule out because a value is unknown; it always contains ``has``.
    """

    id: int
    species_id: int
    cp: int
    has: frozenset[str] = frozenset()
    maybe: frozenset[str] = frozenset()


@dataclass(slots=True)
class Bundle:
    excluded: tuple[str, ...]
    members: list[BoxPokemon] = field(default_factory=list)
    # Pokémon the search finds that are not among the members (only for a bundle of one species
    # and one CP, when another Pokémon with that species and CP passes the safety terms too).
    other_matches: int = 0

    @property
    def species_ids(self) -> list[int]:
        return sorted({p.species_id for p in self.members})

    @property
    def cps(self) -> list[int]:
        return sorted({p.cp for p in self.members})

    @property
    def query(self) -> str:
        return ",".join(map(str, self.species_ids)) + "&" + ",".join(f"cp{cp}" for cp in self.cps)

    @property
    def suffix(self) -> str:
        return "".join(f"&!{term}" for term in self.excluded)

    @property
    def search(self) -> str:
        return self.query + self.suffix


class _Box:
    def __init__(self, box: Iterable[BoxPokemon]) -> None:
        self._by_key: dict[tuple[int, int], list[BoxPokemon]] = defaultdict(list)
        for pokemon in box:
            self._by_key[(pokemon.species_id, pokemon.cp)].append(pokemon)

    def found(self, species: Iterable[int], cps: Iterable[int], excluded: Iterable[str]) -> set[int]:
        """The IDs a search finds. A Pokémon counts as found unless it certainly matches an
        excluded term, so an unknown value never hides a Pokémon from the check."""
        excluded_terms = frozenset(excluded)
        cp_list = list(cps)
        return {
            pokemon.id
            for dex in species
            for cp in cp_list
            for pokemon in self._by_key.get((dex, cp), [])
            if not pokemon.has & excluded_terms
        }


def bundle(listed: Sequence[BoxPokemon], box: Iterable[BoxPokemon], limit: int = MAX_BUNDLE) -> list[Bundle]:
    """Group the listed Pokémon into search strings of at most ``limit`` Pokémon.

    ``box`` is every Pokémon in the inventory of the account, the listed ones included. A
    Pokémon joins a bundle only when the bundle then finds exactly its members. Otherwise it
    starts a new bundle.
    """
    everything = _Box(box)
    bundles: list[Bundle] = []
    for pokemon in sorted(listed, key=lambda p: (p.species_id, p.cp, p.id)):
        excluded = tuple(term for term in SAFETY_TERMS if term not in pokemon.maybe)
        for current in bundles:
            if current.excluded != excluded or len(current.members) >= limit:
                continue
            members = {p.id for p in current.members} | {pokemon.id}
            species = {p.species_id for p in current.members} | {pokemon.species_id}
            cps = {p.cp for p in current.members} | {pokemon.cp}
            # The same string, so it finds nothing new: a twin with the same species and CP
            # joins the bundle that already finds it, instead of a second identical string.
            same_search = species == set(current.species_ids) and cps == set(current.cps)
            if same_search or everything.found(species, cps, excluded) == members:
                current.members.append(pokemon)
                break
        else:
            bundles.append(Bundle(excluded=excluded, members=[pokemon]))
    for current in bundles:
        members = {p.id for p in current.members}
        found = everything.found(current.species_ids, current.cps, current.excluded)
        current.other_matches = len(found - members)
    return bundles
