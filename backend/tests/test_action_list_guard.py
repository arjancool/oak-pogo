"""The action list asks for a confirmation before a Pokémon the advice says to keep, or the last
copy of a species, can go (the Croagunk case of 4 November)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import update

from app.models import PokemonAnalysis
from tests.conftest import Api


def _imported(owner: Api, container: Any, export: dict[str, Any]) -> int:
    account = owner.account()
    owner.upload(account, export)
    container.runner.drain()
    return account


def _group(owner: Api, account: int) -> tuple[int, list[int]]:
    """A group with one copy to keep and at least one transfer candidate, without favorites or
    other confirmations: the kept copy and the candidates."""
    groups = owner.get("/api/v1/cleanup/duplicates", account_id=account).json()["groups"]
    for group in groups:
        members = [m for m in group["members"] if not m["favorite"] and m["catch_date_known"]]
        if len(members) != group["count"] or group["shadow"]:
            continue
        kept = [m["id"] for m in members if m["recommendation"]["status"] == "KEEP"]
        candidates = [m["id"] for m in members if m["recommendation"]["status"] == "TRANSFER_CANDIDATE"]
        if len(kept) == 1 and candidates and len(kept) + len(candidates) == len(members):
            return kept[0], candidates
    raise AssertionError("the sample export has such a group")


def _post(owner: Api, account: int, ids: list[int], confirmed: list[int] | None = None) -> dict[str, Any]:
    body = {"account_id": account, "ids": ids, "confirmed_ids": confirmed or []}
    response = owner.post("/api/v1/cleanup/action-list", body)
    assert response.status_code == 200, response.text
    return response.json()


def _items(owner: Api, account: int) -> dict[int, dict[str, Any]]:
    data = owner.get("/api/v1/cleanup/action-list", account_id=account).json()
    return {i["pokemon"]["id"]: i for i in data["items"]}


def test_a_pokemon_to_keep_needs_a_confirmation(
    owner: Api, container: Any, gamedata: Any, export: dict[str, Any]
) -> None:
    account = _imported(owner, container, export)
    kept, candidates = _group(owner, account)
    result = _post(owner, account, candidates)
    assert result["needs_confirmation"] == [], "transfer candidates go on without a question"
    asked = _post(owner, account, [kept])["needs_confirmation"]
    assert [a["pokemon_id"] for a in asked] == [kept]
    assert set(asked[0]["kinds"]) == {"advice", "last_copy"}
    assert kept not in _items(owner, account), "nothing is added without the confirmation"
    _post(owner, account, [kept], confirmed=[kept])
    assert _items(owner, account)[kept]["executable"]


def test_the_last_copy_is_held_back_until_confirmed(
    owner: Api, container: Any, gamedata: Any, export: dict[str, Any]
) -> None:
    account = _imported(owner, container, export)
    kept, candidates = _group(owner, account)
    _post(owner, account, candidates)
    # Through a bulk action in the Box, which does not look at the advice.
    bulk = owner.post(
        "/api/v1/pokemon/bulk",
        {"account_id": account, "ids": [kept], "action": "add_to_list", "value": "cleanup"},
    )
    assert bulk.status_code == 200, bulk.text
    assert [a["pokemon_id"] for a in bulk.json()["needs_confirmation"]] == [kept]


def test_advice_that_changes_after_adding_holds_the_pokemon_back(
    owner: Api, container: Any, gamedata: Any, export: dict[str, Any]
) -> None:
    account = _imported(owner, container, export)
    _kept, candidates = _group(owner, account)
    _post(owner, account, candidates)
    assert all(_items(owner, account)[c]["executable"] for c in candidates)
    with container.db.transaction() as session:
        session.execute(
            update(PokemonAnalysis).where(PokemonAnalysis.pokemon_id == candidates[0]).values(status="KEEP")
        )
    item = _items(owner, account)[candidates[0]]
    assert not item["executable"] and item["needs_confirmation"]["kinds"] == ["advice"]


def test_every_copy_on_the_list_holds_back_only_the_best(
    owner: Api, container: Any, gamedata: Any, export: dict[str, Any]
) -> None:
    account = _imported(owner, container, export)
    kept, candidates = _group(owner, account)
    _post(owner, account, [*candidates, kept], confirmed=[kept])
    items = _items(owner, account)
    assert items[kept]["executable"], "confirmed for both reasons"
    assert all(items[c]["executable"] for c in candidates), "the others need no question"
    owner.post("/api/v1/cleanup/action-list", {"account_id": account, "ids": [kept], "mode": "remove"})
    assert all(_items(owner, account)[c]["executable"] for c in candidates)
