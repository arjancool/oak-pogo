"""PvP cups from PvPoke: who may enter, the analysis per cup and the battle pages (ADR-0027)."""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest

from app.analysis.league import Subject, analyze_leagues
from app.analysis.stats import IVs
from app.gamedata.cups import build_cups
from app.gamedata.model import GameData
from tests.conftest import FIXTURES, Api

FANTASY, LITTLE = "fantasy-1500", "little-500"


@pytest.fixture(scope="module")
def pvpoke() -> dict[str, Any]:
    return json.loads((FIXTURES / "gamedata" / "pvpoke-subset.json").read_text())


def _cup(pvpoke: dict[str, Any], cup_id: str) -> dict[str, Any]:
    cups, _notes = build_cups(pvpoke)
    return next(c for c in cups if c["id"] == cup_id)


def test_fantasy_cup_takes_only_steel_dragon_and_fairy(pvpoke: dict[str, Any]) -> None:
    cup = _cup(pvpoke, FANTASY)
    assert cup["name"] == "Fantasy Cup" and cup["max_cp"] == 1500
    eligible = set(cup["eligible"])
    assert {"dragonite", "dragonite_shadow", "registeel", "azumarill", "sylveon", "perrserker"} <= eligible
    assert not {"machamp", "eevee", "gyarados"} & eligible
    assert "dragonite_mega" not in eligible, "Mega Evolutions are excluded"


def test_little_cup_takes_first_stages_only_and_caps_the_level(pvpoke: dict[str, Any]) -> None:
    cup = _cup(pvpoke, LITTLE)
    assert cup["max_cp"] == 500 and cup["level_cap"] == 50.0
    eligible = set(cup["eligible"])
    assert {"dratini", "machop", "azurill"} <= eligible
    assert not {"dragonair", "dragonite", "marill", "mew"} & eligible, "evolved, or not evolving at all"


def test_explicit_species_include_wins_over_an_exclude(pvpoke: dict[str, Any]) -> None:
    data = copy.deepcopy(pvpoke)
    fantasy = next(c for c in data["cups"] if c["name"] == "fantasy")
    fantasy["include"].append({"filterType": "id", "values": ["machamp"]})
    fantasy["exclude"].append({"filterType": "type", "values": ["fighting"]})
    eligible = set(_cup(data, FANTASY)["eligible"])
    assert "machamp" in eligible and "dragonite" in eligible


def test_a_filter_for_another_cap_is_ignored(pvpoke: dict[str, Any]) -> None:
    data = copy.deepcopy(pvpoke)
    fantasy = next(c for c in data["cups"] if c["name"] == "fantasy")
    fantasy["exclude"].append({"filterType": "id", "values": ["dragonite"], "leagues": [2500]})
    assert "dragonite" in _cup(data, FANTASY)["eligible"]


def test_a_cup_with_unknown_rules_is_left_out_with_a_note(pvpoke: dict[str, Any]) -> None:
    data = copy.deepcopy(pvpoke)
    fantasy = next(c for c in data["cups"] if c["name"] == "fantasy")
    fantasy["include"].append({"filterType": "weather", "values": ["rain"]})
    cups, notes = build_cups(data)
    assert FANTASY not in {c["id"] for c in cups}
    assert notes == ["Fantasy Cup: regels die OAK niet kan toepassen"]


def test_cup_eligibility_follows_shadow_and_unknown_forms(gamedata: GameData) -> None:
    dragonite = gamedata.forms["149:DRAGONITENORMAL"]
    machamp = gamedata.forms["68:MACHAMPNORMAL"]
    assert gamedata.cup_allows(FANTASY, dragonite, shadow=False) is True
    assert gamedata.cup_allows(FANTASY, dragonite, shadow=True) is True
    assert gamedata.cup_allows(FANTASY, machamp, shadow=False) is False
    assert gamedata.cup_allows(FANTASY, {"pvpoke_id": None}, shadow=False) is None, "unknown, not 'no'"
    assert gamedata.cup_allows("unknown-1500", dragonite, shadow=False) is None


def test_cup_analysis_only_offers_targets_the_cup_allows(gamedata: GameData) -> None:
    def targets(form_key: str) -> dict[str, list[Any]]:
        subject = Subject(form_key, IVs(1, 15, 15), 10.0, None, False, False, False, 40)
        return analyze_leagues(
            gamedata,
            subject,
            max_level=50,
            include_best_buddy=False,
            ready_cp_fraction=0.9,
            elite_tm_available=True,
            leagues=(FANTASY, LITTLE),
        )

    eevee = targets("133:EEVEENORMAL")
    assert {t.target_name for t in eevee[FANTASY]} == {"Sylveon"}, "only the Fairy evolution may enter"
    assert {t.target_name for t in eevee[LITTLE]} == {"Eevee"}, "Little Cup takes the first stage"
    assert all(t.best_level <= 50 for t in eevee[LITTLE])
    assert targets("66:MACHOPNORMAL")[FANTASY] == []


def _imported(owner: Api, container: Any, export: dict[str, Any]) -> int:
    account = owner.account()
    owner.upload(account, export)
    container.runner.drain()
    return account


def test_cups_are_listed_after_the_leagues(owner: Api, gamedata: GameData) -> None:
    listed = owner.get("/api/v1/battles/leagues").json()
    assert [entry["id"] for entry in listed[:3]] == ["great", "ultra", "master"]
    fantasy = next(entry for entry in listed if entry["id"] == FANTASY)
    assert fantasy["kind"] == "cup" and fantasy["max_cp"] == 1500 and fantasy["ranked_species"]
    assert {"kind": "type", "include": True, "values": ["steel", "dragon", "fairy"]}.items() <= fantasy["conditions"][
        0
    ].items()
    little = next(entry for entry in listed if entry["id"] == LITTLE)
    assert little["ranked_species"] is None and little["level_cap"] == 50.0


def test_cup_page_lists_only_pokemon_that_may_enter(
    owner: Api, container: Any, gamedata: GameData, export: dict[str, Any]
) -> None:
    account = _imported(owner, container, export)
    page = owner.get(f"/api/v1/battles/league/{FANTASY}", account_id=account).json()
    assert page["info"]["name"] == "Fantasy Cup" and page["items"]
    for item in page["items"]:
        form = next(f for f in gamedata.forms.values() if f["name"] == item["target"].split(" (")[0])
        assert set(form["types"]) & {"steel", "dragon", "fairy"}, item["target"]
        assert item["best_cp"] <= 1500

    unranked = owner.get(f"/api/v1/battles/league/{LITTLE}", account_id=account).json()
    assert unranked["items"] and "geen ranglijst" in unranked["method"]
    assert all(item["species_rank"] is None for item in unranked["items"])

    assert owner.get("/api/v1/battles/league/bogus-1500", account_id=account).status_code == 404


def test_cleanup_advice_ignores_cups(owner: Api, container: Any, gamedata: GameData, export: dict[str, Any]) -> None:
    account = _imported(owner, container, export)
    items = owner.get("/api/v1/cleanup/recommendations", account_id=account, page_size=500).json()["items"]
    leagues = {r.get("league") for item in items for r in item["roles"]}
    assert leagues <= {None, "great", "ultra", "master"}


def test_team_builder_and_saved_teams_take_a_cup(
    owner: Api, container: Any, gamedata: GameData, export: dict[str, Any]
) -> None:
    account = _imported(owner, container, export)
    built = owner.post("/api/v1/battles/team-builder", {"account_id": account, "league": FANTASY})
    assert built.status_code == 200, built.text
    assert built.json()["league"] == FANTASY
    assert owner.post("/api/v1/battles/team-builder", {"account_id": account, "league": "bogus-1"}).status_code == 404
    assert (
        owner.post("/api/v1/battles/team-builder", {"account_id": account, "league": "Fantasy Cup"}).status_code == 422
    )
    saved = owner.post(
        "/api/v1/battles/teams",
        {"account_id": account, "name": "Fantasy", "kind": "pvp", "league": "battlefrontiermaster-10000"},
    )
    assert saved.status_code == 201, saved.text
    assert saved.json()["league"] == "battlefrontiermaster-10000"
