"""A form of an event, such as the goggles of 2026, counts like a costume: protected and with
keep points, also when the Game Master does not know the form or does not mark it as a costume."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select, update

from app.domain.pokemon import is_event_form
from app.models import Pokemon
from app.services.analysis import AnalysisService
from tests.conftest import Api


@pytest.mark.parametrize(
    "name",
    ["CharmanderGoggles2026", "CHARIZARD_GOGGLES_2026", "PikachuCopy2019", "PsyduckSwim2025", "DITTO_SPRING_2026_A"],
)
def test_a_year_in_the_form_name_is_an_event_form(name: str) -> None:
    assert is_event_form(name)


@pytest.mark.parametrize("name", [None, "", "CharmanderNormal", "3362", "SPINDA_19", "PIKACHU_FLYING_5TH_ANNIV"])
def test_other_forms_are_not(name: str | None) -> None:
    assert not is_event_form(name)


def _items(owner: Api, account: int) -> dict[int, dict[str, Any]]:
    data = owner.get("/api/v1/cleanup/recommendations", account_id=account, page_size=500).json()
    return {i["pokemon"]["id"]: i for i in data["items"]}


def test_an_event_form_is_protected_and_gets_points(
    owner: Api, container: Any, gamedata: Any, export: dict[str, Any]
) -> None:
    account = owner.account()
    owner.upload(account, export)
    container.runner.drain()
    before = _items(owner, account)
    candidate = next(
        i["pokemon"]
        for i in before.values()
        if i["status"] == "TRANSFER_CANDIDATE" and not i["pokemon"]["costume"] and not i["pokemon"]["favorite"]
    )
    with container.db.transaction() as session:
        species = session.scalar(select(Pokemon.species_name).where(Pokemon.id == candidate["id"])) or "Pokemon"
        session.execute(
            update(Pokemon)
            .where(Pokemon.id == candidate["id"])
            .values(form_name=f"{species.replace(' ', '')}Goggles2026")
        )
    AnalysisService(container.settings, container.db, container.gamedata, container.clock).run(account)

    item = _items(owner, account)[candidate["id"]]
    assert item["pokemon"]["event_form"] is True and not item["pokemon"]["costume"]
    assert item["status"] == "PROTECT"
    assert "EVENT_FORM" in {r["code"] for r in item["protection_reasons"]}
    traits = next(p for p in item["scores"]["keep"]["parts"] if p["code"] == "TRAITS")
    codes = {t["code"] for t in traits["data"]["traits"]}
    assert "EVENT_FORM" in codes and "COSTUME" not in codes, "counted once, as an event form"
    assert item["keep_score"] > before[candidate["id"]]["keep_score"]

    # Listed after a confirmation, its search string does not hide it behind !costume.
    owner.post(
        "/api/v1/cleanup/action-list",
        {"account_id": account, "ids": [candidate["id"]], "confirmed_ids": [candidate["id"]]},
    )
    hint = owner.get("/api/v1/cleanup/action-list", account_id=account).json()["search_hint"]
    searches = [q["search"] for q in hint["queries"] if candidate["id"] in q["pokemon_ids"]]
    assert all("!costume" not in s for s in searches)
