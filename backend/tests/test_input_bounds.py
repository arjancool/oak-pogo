"""Bounds on page numbers, ids, preferences, completeness settings and team members: a 422,
never a 500 or storage without a bound (issue #53)."""

from __future__ import annotations

from typing import Any

import pytest

from tests.conftest import Api

HUGE = 2**70


@pytest.mark.parametrize(
    "path",
    ["/api/v1/pokemon", "/api/v1/imports", "/api/v1/sync/history", "/api/v1/cleanup/recommendations"],
)
def test_a_huge_page_number_is_refused(owner: Api, path: str) -> None:
    response = owner.get(path, account_id=owner.account(), page=HUGE)
    assert response.status_code == 422, (path, response.text)


@pytest.mark.parametrize("path", ["/api/v1/imports/{id}", "/api/v1/pokemon/{id}", "/api/v1/accounts/{id}"])
def test_a_huge_id_is_refused(owner: Api, path: str) -> None:
    response = owner.get(path.format(id=HUGE))
    assert response.status_code in (404, 422), (path, response.status_code, response.text)


def test_preferences_have_types_and_bounds(owner: Api) -> None:
    for bad in ({"page_size": 10**9}, {"box_columns": 0}, {"theme": "x" * 1000}, {"active_account_id": HUGE}):
        assert owner.put("/api/v1/auth/me/preferences", {"preferences": bad}).status_code == 422, bad
    ok = owner.put("/api/v1/auth/me/preferences", {"preferences": {"page_size": 50, "unknown": "x" * 10_000}})
    assert ok.status_code == 200
    assert ok.json()["preferences"] == {"page_size": 50}, "unknown keys are not stored"


def test_completeness_takes_only_its_two_settings(owner: Api) -> None:
    account = owner.account()
    extra = {"max_drop_fraction": 0.5, **{f"k{i}": 1 for i in range(100)}}
    assert owner.patch(f"/api/v1/accounts/{account}", {"completeness": extra}).status_code == 422
    good = owner.patch(f"/api/v1/accounts/{account}", {"completeness": {"max_drop_fraction": 0.5}})
    assert good.status_code == 200, good.text
    assert good.json()["completeness"] == {"max_drop_fraction": 0.5}


def test_a_team_member_without_a_pokemon_is_refused(owner: Api, container: Any) -> None:
    account = owner.account()
    response = owner.post(
        "/api/v1/battles/teams", {"account_id": account, "name": "Team", "members": [{"role": "lead"}]}
    )
    assert response.status_code == 422, response.text
