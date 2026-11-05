"""Search strings on the action list: bundles of at most ten Pokémon that find nothing outside the
list, according to the last sync (issue #27)."""

from __future__ import annotations

import random
from typing import Any

from sqlalchemy import select, update

from app.domain.search_strings import MAX_BUNDLE, SAFETY_TERMS, BoxPokemon, bundle
from app.models import Pokemon
from tests.conftest import Api


def matches(search: str, pokemon: BoxPokemon) -> bool:
    """How Pokémon GO reads a search string: groups split by "&" must all hold, a comma inside
    a group means "or" and "!" negates. Only the terms OAK writes are known here."""
    for group in search.split("&"):
        if group.startswith("!"):
            if group[1:] in pokemon.has:
                return False
            continue
        options = group.split(",")
        if options[0].startswith("cp"):
            if pokemon.cp not in {int(option[2:]) for option in options}:
                return False
        elif pokemon.species_id not in {int(option) for option in options}:
            return False
    return True


def found(search: str, box: list[BoxPokemon]) -> set[int]:
    return {p.id for p in box if matches(search, p)}


def test_a_bundle_never_finds_a_pokemon_outside_the_list() -> None:
    # The case from the issue: a second Fennekin with a CP of the other listed Pokémon.
    fennekin = BoxPokemon(id=1, species_id=653, cp=569)
    froakie = BoxPokemon(id=2, species_id=656, cp=592)
    other_fennekin = BoxPokemon(id=3, species_id=653, cp=592)
    box = [fennekin, froakie, other_fennekin]
    bundles = bundle([fennekin, froakie], box)
    assert len(bundles) == 2, "together they would also find the second Fennekin"
    for each in bundles:
        assert found(each.search, box) == {p.id for p in each.members}
        assert each.other_matches == 0
    # Without that Fennekin they share one string.
    together = bundle([fennekin, froakie], [fennekin, froakie])
    assert [b.query for b in together] == ["653,656&cp569,cp592"]


def test_at_most_ten_pokemon_per_bundle() -> None:
    listed = [BoxPokemon(id=n, species_id=100 + n, cp=500 + n) for n in range(25)]
    bundles = bundle(listed, listed)
    assert [len(b.members) for b in bundles] == [MAX_BUNDLE, MAX_BUNDLE, 5]
    assert sorted(p.id for b in bundles for p in b.members) == list(range(25))
    assert bundles[0].search.endswith("".join(f"&!{term}" for term in SAFETY_TERMS))


def test_the_same_species_and_cp_cannot_be_separated() -> None:
    listed = BoxPokemon(id=1, species_id=453, cp=530)
    twin = BoxPokemon(id=2, species_id=453, cp=530)
    shiny_twin = BoxPokemon(id=3, species_id=453, cp=530, has=frozenset({"shiny"}), maybe=frozenset({"shiny"}))
    unknown_twin = BoxPokemon(id=4, species_id=453, cp=530, maybe=frozenset({"shiny"}))
    only = bundle([listed], [listed, twin])
    assert only[0].other_matches == 1, "the player is told the string finds one more"
    # "!shiny" hides a shiny twin, but a Pokémon whose shine is unknown still counts.
    assert bundle([listed], [listed, shiny_twin])[0].other_matches == 0
    assert bundle([listed], [listed, unknown_twin])[0].other_matches == 1
    # Both twins on the list: one string, and it finds exactly them.
    both = bundle([listed, twin], [listed, twin])
    assert len(both) == 1 and both[0].other_matches == 0


def test_a_confirmed_favorite_is_found_by_its_string() -> None:
    plain = BoxPokemon(id=1, species_id=10, cp=100)
    favorite = BoxPokemon(id=2, species_id=11, cp=200, has=frozenset({"favorite"}), maybe=frozenset({"favorite"}))
    other_favorite = BoxPokemon(id=3, species_id=10, cp=100, has=frozenset({"favorite"}), maybe=frozenset({"favorite"}))
    box = [plain, favorite, other_favorite]
    bundles = bundle([plain, favorite], box)
    by_member = {b.members[0].id: b for b in bundles}
    assert "!favorite" not in by_member[2].search and found(by_member[2].search, box) == {2}
    assert "!favorite" in by_member[1].search and found(by_member[1].search, box) == {1}


def test_random_boxes_give_exact_bundles() -> None:
    rng = random.Random(27)
    for _round in range(200):
        box = [
            BoxPokemon(
                id=n,
                species_id=rng.randint(1, 8),
                cp=rng.choice([10, 20, 30, 40, 50, 60]),
                has=frozenset(t for t in ("shiny", "lucky") if rng.random() < 0.2),
            )
            for n in range(rng.randint(1, 40))
        ]
        box = [BoxPokemon(p.id, p.species_id, p.cp, p.has, p.has) for p in box]
        listed = rng.sample(box, rng.randint(1, len(box)))
        bundles = bundle(listed, box)
        assert sorted(p.id for b in bundles for p in b.members) == sorted(p.id for p in listed)
        for each in bundles:
            members = {p.id for p in each.members}
            hits = found(each.search, box)
            assert len(members) <= MAX_BUNDLE and members <= hits
            assert len(hits - members) == each.other_matches
            if each.other_matches:
                assert len(each.members) == 1, "only a Pokémon on its own can find more"


def _imported(owner: Api, container: Any, export: dict[str, Any]) -> int:
    account = owner.account()
    owner.upload(account, export)
    container.runner.drain()
    return account


def _box(container: Any, account: int) -> list[Pokemon]:
    with container.db.read() as session:
        return list(
            session.scalars(
                select(Pokemon).where(Pokemon.trainer_account_id == account, Pokemon.inventory_status == "in_inventory")
            ).all()
        )


def test_the_action_list_separates_a_pokemon_with_the_same_species_and_a_listed_cp(
    owner: Api, container: Any, gamedata: Any, export: dict[str, Any]
) -> None:
    account = _imported(owner, container, export)
    items = owner.get(
        "/api/v1/cleanup/recommendations",
        account_id=account,
        page_size=500,
        status="TRANSFER_CANDIDATE",
        favorite="false",
        vintage="false",
    ).json()["items"]
    plain = ("shiny", "lucky", "shadow", "hundo", "costume", "pokemon_class")
    candidates = [i["pokemon"] for i in items if not any(i["pokemon"][flag] for flag in plain)]
    box = _box(container, account)
    first, twin = next((c, p) for c in candidates for p in box if p.species_id == c["species_id"] and p.id != c["id"])
    second = next(p for p in candidates if p["species_id"] != first["species_id"] and p["cp"] != first["cp"])
    # The unlisted Pokémon gets the species of the first and the CP of the second, without
    # anything the safety terms would exclude.
    with container.db.transaction() as session:
        session.execute(
            update(Pokemon)
            .where(Pokemon.id == twin.id)
            .values(
                cp=second["cp"],
                favorite=False,
                shiny=False,
                lucky=False,
                alignment=0,
                costume_id=0,
                costume_form=False,
                iv_attack=0,
            )
        )
    ids = [first["id"], second["id"]]
    response = owner.post("/api/v1/cleanup/action-list", {"account_id": account, "ids": ids, "confirmed_ids": ids})
    assert response.status_code == 200, response.text
    queries = response.json()["search_hint"]["queries"]
    assert {i for q in queries for i in q["pokemon_ids"]} == set(ids)
    for query in queries:
        assert query["search"] == query["query"] + "".join(f"&!{t}" for t in SAFETY_TERMS)
        assert len(query["pokemon_ids"]) <= MAX_BUNDLE
        assert not (first["species_id"] in query["species_ids"] and f"cp{second['cp']}" in query["query"]), query
        assert query["other_matches"] == 0
