"""Gym defenders in the cleanup advice: gym position, the best-defender role and Pokémon that
defend a gym right now (ADR-0026)."""

from __future__ import annotations

import copy
from typing import Any

from sqlalchemy import select

from app.analysis.gym import gym_potential
from app.gamedata.model import GameData
from app.jobs.tasks import enqueue
from app.models import Pokemon
from app.normalizers.pgsharp import normalize_export
from app.normalizers.sanitize import sanitize_export
from tests.conftest import Api

DRATINI = "147:"
DRAGONITE = "149:"
MEWTWO = "150:"


def test_gym_position_counts_the_evolution_that_may_defend(gamedata: GameData) -> None:
    potential = gym_potential(gamedata, DRATINI, 15, 15, level=50.0, shadow=False)
    assert potential is not None
    assert potential.target_key.startswith("149:") and potential.is_evolution
    assert potential.rank >= 1


def test_more_defense_and_hp_is_never_a_worse_position(gamedata: GameData) -> None:
    weak = gym_potential(gamedata, DRAGONITE, 0, 0, level=50.0, shadow=False)
    strong = gym_potential(gamedata, DRAGONITE, 15, 15, level=50.0, shadow=False)
    shadow = gym_potential(gamedata, DRAGONITE, 15, 15, level=50.0, shadow=True)
    assert weak is not None and strong is not None and shadow is not None
    assert strong.bulk > weak.bulk and strong.rank <= weak.rank
    assert shadow.bulk < strong.bulk


def test_no_gym_position_without_permission_or_data(gamedata: GameData) -> None:
    assert gym_potential(gamedata, MEWTWO, 15, 15, level=50.0, shadow=False) is None
    dataset = copy.deepcopy(dict(gamedata.dataset))
    for form in dataset["forms"].values():
        form.pop("deployable")
    old = GameData(dataset, gamedata.version_id + 1000)
    assert gym_potential(old, DRAGONITE, 15, 15, level=50.0, shadow=False) is None


def _imported(owner: Api, container: Any, export: dict[str, Any]) -> int:
    account = owner.account()
    owner.upload(account, export)
    container.runner.drain()
    return account


def _items(owner: Api, account: int) -> list[dict[str, Any]]:
    response = owner.get("/api/v1/cleanup/recommendations", account_id=account, page_size=500)
    assert response.status_code == 200, response.text
    return response.json()["items"]


def test_gym_value_counts_in_the_battle_score_and_keeps_the_best_defender(
    owner: Api, container: Any, gamedata: GameData, export: dict[str, Any]
) -> None:
    account = _imported(owner, container, export)
    items = _items(owner, account)
    gym_parts = [p for item in items for p in item["scores"]["battle"]["parts"] if p["code"] == "GYM"]
    assert gym_parts, "Pokémon that may defend a gym get a gym part"
    assert all(0 <= p["value"] <= 100 and p["data"]["rank"] >= 1 for p in gym_parts)
    roles = [r for item in items for r in item["roles"] if r["role"] == "best_gym"]
    assert roles, "the sturdiest defender per species keeps the gym role"
    assert len({r["target_key"] for r in roles}) == len(roles), "one best defender per species"

    response = owner.put("/api/v1/cleanup/rules", {"rules": {"keep_best_gym": False}}, params={"account_id": account})
    assert response.status_code == 200, response.text
    container.runner.drain()
    assert not [r for item in _items(owner, account) for r in item["roles"] if r["role"] == "best_gym"]


def test_a_pokemon_in_a_gym_is_never_a_transfer_candidate(
    owner: Api, container: Any, gamedata: GameData, export: dict[str, Any]
) -> None:
    account = _imported(owner, container, export)
    candidate = next(item for item in _items(owner, account) if item["status"] == "TRANSFER_CANDIDATE")
    with container.db.transaction() as session:
        pokemon = session.get(Pokemon, candidate["pokemon"]["id"])
        assert pokemon is not None
        pokemon.in_gym = True
    enqueue(container, "analysis", account)
    container.runner.drain()
    item = next(i for i in _items(owner, account) if i["pokemon"]["id"] == candidate["pokemon"]["id"])
    assert item["status"] == "REVIEW"
    assert item["reasons"][0]["code"] == "IN_GYM"


def test_in_gym_is_read_without_keeping_the_gym(export: dict[str, Any]) -> None:
    raw = copy.deepcopy(export)
    records = [p for p in raw["pokemons"] if not p.get("isEgg")]
    records[0]["deployedFortId"] = "synthetic-gym-id.16"
    records[1]["deployedFortId"] = ""
    records[2].pop("deployedFortId", None)
    by_id = {p.source_pokemon_id: p for p in normalize_export(raw).pokemon}
    assert by_id[str(records[0]["id"])].in_gym is True
    assert by_id[str(records[1]["id"])].in_gym is False
    assert by_id[str(records[2]["id"])].in_gym is None
    assert "synthetic-gym-id" not in str(sanitize_export(raw))


def test_gym_overview_marks_pokemon_in_a_gym(
    owner: Api, container: Any, gamedata: GameData, export: dict[str, Any]
) -> None:
    account = _imported(owner, container, export)
    defenders = owner.get("/api/v1/battles/gym-defenders", account_id=account).json()["defenders"]
    assert defenders and all("in_gym" in d for d in defenders)
    with container.db.transaction() as session:
        pokemon = session.scalars(select(Pokemon).where(Pokemon.id == defenders[0]["pokemon_id"])).one()
        pokemon.in_gym = True
    defenders = owner.get("/api/v1/battles/gym-defenders", account_id=account).json()["defenders"]
    assert next(d for d in defenders if d["pokemon_id"] == pokemon.id)["in_gym"] is True
