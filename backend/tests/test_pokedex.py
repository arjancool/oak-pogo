"""Pokédex: any species from the Game Data, and what the own collection can evolve into it."""

from __future__ import annotations

from typing import Any

from app.analysis.pokedex import evolves_from, paths_into, search_key, search_species, species_forms
from app.gamedata.model import GameData
from tests.conftest import Api

DRATINI, DRAGONAIR, DRAGONITE = 147, 148, 149


def test_search_by_name_number_and_without_accents(gamedata: GameData) -> None:
    assert [hit.name for hit in search_species(gamedata, "drag")] == ["Dragonair", "Dragonite"]
    assert [hit.dex for hit in search_species(gamedata, "#149")] == [DRAGONITE]
    assert [hit.name for hit in search_species(gamedata, "nite")] == ["Dragonite"]
    assert search_species(gamedata, "   ") == []
    assert search_key("Flabébé") == "FLABEBE" and search_key("Mr. Mime") == "MRMIME"


def test_base_template_and_normal_form_are_one_pokemon(gamedata: GameData) -> None:
    forms = species_forms(gamedata, DRAGONITE)
    assert forms == [f"{DRAGONITE}:DRAGONITENORMAL"]
    assert evolves_from(gamedata, f"{DRAGONITE}:") == [f"{DRAGONAIR}:DRAGONAIRNORMAL"]


def test_paths_into_a_form_cover_the_whole_chain(gamedata: GameData) -> None:
    starts = paths_into(gamedata, f"{DRAGONITE}:DRAGONITENORMAL")
    from_dratini = starts[f"{DRATINI}:DRATININORMAL"][0]
    assert [step.to_key for step in from_dratini.steps] == [
        f"{DRAGONAIR}:DRAGONAIRNORMAL",
        f"{DRAGONITE}:DRAGONITENORMAL",
    ]
    assert from_dratini.total_candy == 125
    assert f"{DRAGONAIR}:DRAGONAIRNORMAL" in starts
    assert not paths_into(gamedata, f"{DRATINI}:DRATININORMAL"), "nothing evolves into the first stage"


def _imported(owner: Api, container: Any, export: dict[str, Any]) -> int:
    account = owner.account()
    owner.upload(account, export)
    container.runner.drain()
    return account


def test_species_page_shows_game_data_and_the_own_collection(
    owner: Api, container: Any, gamedata: GameData, export: dict[str, Any]
) -> None:
    account = _imported(owner, container, export)
    response = owner.get(f"/api/v1/pokedex/{DRAGONITE}", account_id=account)
    assert response.status_code == 200, response.text
    page = response.json()
    assert page["name"] == "Dragonite" and page["form"]["types"] == ["dragon", "flying"]
    assert [row["level"] for row in page["cp_table"]] == [20.0, 25.0, 40.0, gamedata.max_level]
    assert all(row["cp"] > 0 for row in page["cp_table"])
    assert page["gym"]["rank"] >= 1 and not page["gym"]["is_evolution"]
    assert {league["league"] for league in page["leagues"]} == {"great", "ultra", "master"}
    assert page["evolves_from"][0]["dex"] == DRAGONAIR

    collection = page["collection"]
    dratini = [p for p in export["pokemons"] if p.get("pokemonId") == DRATINI and not p.get("isEgg")]
    assert collection["owned_total"] == sum(1 for p in export["pokemons"] if p.get("pokemonId") == DRAGONITE)
    assert collection["candidate_total"] == len(dratini)
    candidate = collection["candidates"][0]
    assert candidate["total_candy"] == 125 and len(candidate["steps"]) == 2
    assert candidate["cp_after"] is None or candidate["cp_after"] > candidate["pokemon"]["cp"]
    cps = [c["cp_after"] for c in collection["candidates"] if c["cp_after"] is not None]
    assert cps == sorted(cps, reverse=True), "the strongest result first"
    assert collection["candy"] == {"family": "FAMILY_DRATINI", "quantity": None}, "candy is unknown, not zero"


def test_species_page_without_account_and_with_bad_input(owner: Api, gamedata: GameData) -> None:
    page = owner.get("/api/v1/pokedex/133").json()
    assert page["collection"] is None
    assert {step["to_name"] for step in page["evolves_to"]} >= {"Vaporeon", "Jolteon", "Flareon"}
    assert owner.get("/api/v1/pokedex/133", form="133:EEVEEGOFEST2024MTIARA").status_code == 200
    assert owner.get("/api/v1/pokedex/133", form="149:").status_code == 404
    assert owner.get("/api/v1/pokedex/9999").status_code == 404
    assert owner.get("/api/v1/pokedex/search", q="").status_code == 422


def test_species_page_reads_only_own_accounts(owner: Api, gamedata: GameData) -> None:
    account = owner.account()
    member = owner.post("/api/v1/users", {"username": "dexmember", "password": "correct horse battery staple"})
    assert member.status_code == 201
    assert owner.login("dexmember", "correct horse battery staple").status_code == 200
    assert owner.get(f"/api/v1/pokedex/{DRAGONITE}", account_id=account).status_code == 404
    assert owner.get(f"/api/v1/pokedex/{DRAGONITE}").status_code == 200


def test_pokedex_needs_a_login(client: Any) -> None:
    assert client.get("/api/v1/pokedex/search", params={"q": "drag"}).status_code == 401
