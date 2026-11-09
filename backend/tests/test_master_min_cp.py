"""A lower bound in CP for leagues and cups without a CP cap, such as the Master League.

The battle pages and the Team Builder only take Pokémon from ``master_min_cp`` on (2500 by
default): the CP now for the team as the Pokémon are now, the CP after the upgrades for the
other teams and the best CP on the league page. 0 means no lower bound."""

from __future__ import annotations

from typing import Any

import pytest

from app.recommendations.rules import CleanupRules
from tests.conftest import Api

FLOOR = 2500


@pytest.fixture
def account(owner: Api, container: Any, gamedata: Any, export: dict[str, Any]) -> int:
    account_id = owner.account()
    owner.upload(account_id, export)
    container.runner.drain()
    return account_id


def _rules(owner: Api, account: int, **rules: Any) -> Any:
    return owner.put("/api/v1/cleanup/rules", {"rules": rules}, params={"account_id": account})


def _variants(owner: Api, account: int, league: str) -> dict[str, Any]:
    built = owner.post("/api/v1/battles/team-builder", {"account_id": account, "league": league})
    assert built.status_code == 200, built.text
    return built.json()


def _league(owner: Api, account: int, league: str) -> dict[str, Any]:
    response = owner.get(f"/api/v1/battles/league/{league}", account_id=account, limit=500)
    assert response.status_code == 200, response.text
    return response.json()


def test_the_lower_bound_is_a_rule_of_2500_cp() -> None:
    assert CleanupRules().master_min_cp == FLOOR
    assert CleanupRules(master_min_cp=0).validate().master_min_cp == 0


@pytest.mark.parametrize("value", [-1, 10_001])
def test_the_lower_bound_has_a_range(owner: Api, account: int, value: int) -> None:
    response = _rules(owner, account, master_min_cp=value)
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["data"] == {"field": "master_min_cp", "min": 0, "max": 10_000, "context": "out_of_range"}


def test_every_team_in_the_master_league_plays_from_2500_cp(owner: Api, account: int) -> None:
    built = _variants(owner, account, "master")
    assert built["min_cp"] == FLOOR
    variants = {v["mode"]: v for v in built["variants"]}
    now = variants["now"]["team"]
    assert now, "the sample has Pokémon of five species above 2500 CP"
    assert all(m["cp"] >= FLOOR for m in now), "the CP now"
    for mode in ("limited", "future"):
        for member in variants[mode]["team"] or []:
            assert member["goal_cp"] >= FLOOR, f"{mode}: the CP after the upgrades"


def test_the_league_page_leaves_out_pokemon_below_2500_cp(owner: Api, account: int) -> None:
    page = _league(owner, account, "master")
    assert page["min_cp"] == FLOOR
    assert page["items"] and all(i["best_cp"] >= FLOOR for i in page["items"])
    for item in page["items"]:
        if item["cp"] is None or item["cp"] < FLOOR:
            assert item["percent_now"] is None and item["suitability_now"] is None
    assert any(i["percent_now"] is not None for i in page["items"])


def test_zero_means_no_lower_bound(owner: Api, account: int) -> None:
    bounded = _league(owner, account, "master")
    assert _rules(owner, account, master_min_cp=0).status_code == 200
    free = _league(owner, account, "master")
    assert free["min_cp"] is None and _variants(owner, account, "master")["min_cp"] is None
    assert free["total"] >= bounded["total"]
    assert any(i["cp"] is not None and i["cp"] < FLOOR and i["percent_now"] is not None for i in free["items"])


def test_a_league_with_a_cap_has_no_lower_bound(owner: Api, account: int) -> None:
    assert _league(owner, account, "great")["min_cp"] is None
    assert _variants(owner, account, "ultra")["min_cp"] is None
