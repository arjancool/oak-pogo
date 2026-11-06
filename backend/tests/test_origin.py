"""Where a Pokémon came from: only values checked against a real export get a name (issue #32)."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import update

from app.domain.pokemon import VERIFIED_ORIGINS, origin_kind
from app.models import Pokemon
from tests.conftest import Api


@pytest.mark.parametrize(("case", "kind"), [(2, "egg"), (3, "raid"), (6, "rocket")])
def test_checked_values_have_a_name(case: int, kind: str) -> None:
    assert origin_kind(case) == kind


@pytest.mark.parametrize("case", [None, 0, 1, 4, 5, 9, 13, 99, -1])
def test_other_values_are_never_guessed(case: int | None) -> None:
    assert origin_kind(case) is None


def test_only_checked_values_are_named() -> None:
    # Wild (1), research (4) and GO Battle League (5) follow the community order, but nothing in
    # the export confirms them; see docs/PGSHARP_INTEGRATION.md before adding one here.
    assert set(VERIFIED_ORIGINS) == {2, 3, 6}


def test_the_detail_page_gets_the_origin(owner: Api, container: Any, export: dict[str, Any]) -> None:
    account = owner.account()
    owner.upload(account, export)
    container.runner.drain()
    items = owner.get("/api/v1/pokemon", account_id=account, page_size=500).json()["items"]
    first, second, third = (i["id"] for i in items[:3])
    with container.db.transaction() as session:
        for pid, case in ((first, 2), (second, 4), (third, None)):
            session.execute(update(Pokemon).where(Pokemon.id == pid).values(origin_case=case))

    def details(pid: int) -> dict[str, Any]:
        return owner.get(f"/api/v1/pokemon/{pid}").json()["details"]

    assert (details(first)["origin"], details(first)["origin_case"]) == ("egg", 2)
    assert (details(second)["origin"], details(second)["origin_case"]) == (None, 4), "shown as onbekend, code 4"
    assert (details(third)["origin"], details(third)["origin_case"]) == (None, None)
