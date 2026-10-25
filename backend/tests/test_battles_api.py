"""League tables through the API: sorting on every column."""

from __future__ import annotations

from typing import Any

import pytest

from app.services.battles import LEAGUE_SORTS
from tests.conftest import Api


def _league(owner: Api, account: int, **params: Any) -> dict[str, Any]:
    response = owner.get("/api/v1/battles/league/great", account_id=account, limit=500, **params)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def account(owner: Api, container: Any, gamedata: Any, export: dict[str, Any]) -> int:
    account_id = owner.account()
    owner.upload(account_id, export)
    container.runner.drain()
    return account_id


def test_default_order_is_suitability(owner: Api, account: int) -> None:
    data = _league(owner, account)
    assert data["sort"] == "-suitability"
    scores = [i["suitability"] for i in data["items"]]
    assert len(scores) >= 3
    assert scores == sorted(scores, reverse=True)


@pytest.mark.parametrize(
    ("sort", "value"),
    [
        ("iv_rank", lambda i: i["iv_rank"]),
        ("-percent", lambda i: i["percent"]),
        ("species_rank", lambda i: i["species_rank"]),
        ("-cp", lambda i: i["cp"]),
        ("best_cp", lambda i: i["best_cp"]),
        ("stardust", lambda i: i["cost"]["stardust"]),
        ("name", lambda i: (i["name"] or "").lower() or None),
    ],
)
def test_sort_by_column(owner: Api, account: int, sort: str, value: Any) -> None:
    items = _league(owner, account, sort=sort)["items"]
    values = [value(i) for i in items]
    known = [v for v in values if v is not None]
    assert known == sorted(known, reverse=sort.startswith("-"))
    assert values[: len(known)] == known  # unknown values come last


def test_every_sort_key_is_accepted_and_keeps_all_items(owner: Api, account: int) -> None:
    total = _league(owner, account)["total"]
    for key in LEAGUE_SORTS:
        for sort in (key, f"-{key}"):
            data = _league(owner, account, sort=sort)
            assert data["total"] == total and len(data["items"]) == total, sort


def test_unknown_sort_is_rejected(owner: Api, account: int) -> None:
    response = owner.get("/api/v1/battles/league/great", account_id=account, sort="geheim")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "UNKNOWN_SORT"
