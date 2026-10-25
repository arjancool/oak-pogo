"""Cleanup Manager through the API: scores, filters, confirmations and recomputation (ADR-0019)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.jobs.tasks import schedule_outdated_analyses
from app.models import AnalysisRun, BackgroundJob, PlannedAction, Pokemon

SAMPLE_POKEMON = 67
SAMPLE_FAVORITES = 7
SAMPLE_VINTAGE = 13


def _all(owner: Any, account: int, **params: Any) -> list[dict[str, Any]]:
    data = owner.get("/api/v1/cleanup/recommendations", account_id=account, page_size=500, **params).json()
    return data["items"]


def _imported(owner: Any, container: Any, export: dict[str, Any]) -> int:
    account = owner.account()
    owner.upload(account, export)
    container.runner.drain()
    return account


def test_every_pokemon_is_scored_and_explained(
    owner: Any, container: Any, gamedata: Any, export: dict[str, Any]
) -> None:
    account = _imported(owner, container, export)
    data = owner.get("/api/v1/cleanup/recommendations", account_id=account, page_size=500).json()
    assert data["total"] == SAMPLE_POKEMON and data["analysis"]["stale"] is False
    assert data["analysis"]["engine_version"] == "cleanup-2.1"
    for item in data["items"]:
        assert item["reasons"], item["status"]
        assert item["keep_score"] is not None
        assert item["scores"]["keep"]["parts"]
        assert item["pokemon"]["cleanup"]["keep_score"] == item["keep_score"]
        if item["status"] != "UNKNOWN":
            assert item["battle_score"] is not None and item["scores"]["battle"]["parts"]


def test_favorites_are_not_protected_for_being_favorite(
    owner: Any, container: Any, gamedata: Any, export: dict[str, Any]
) -> None:
    account = _imported(owner, container, export)
    favorites = _all(owner, account, favorite="true")
    assert len(favorites) == SAMPLE_FAVORITES
    for item in favorites:
        assert "FAVORITE" not in {r["code"] for r in item["protection_reasons"]}
        assert item["status"] != "TRANSFER_CANDIDATE"
        if item["status"] == "PROTECT":
            assert item["protection_reasons"], "PROTECT needs a hard reason"
        if item["status"] == "REVIEW":
            assert item["warnings"][0]["code"] == "FAVORITE"


def test_vintage_pokemon_are_analysed_but_protected(
    owner: Any, container: Any, gamedata: Any, export: dict[str, Any]
) -> None:
    account = _imported(owner, container, export)
    vintage = _all(owner, account, vintage="true")
    assert len(vintage) == SAMPLE_VINTAGE
    for item in vintage:
        year = item["pokemon"]["caught_year"]
        assert 2016 <= year <= 2019 and item["pokemon"]["vintage_year"] == year
        assert item["status"] == "PROTECT"
        assert item["protection_reasons"][0]["code"] == "VINTAGE"
        assert item["scores"]["battle"]["parts"], "vintage Pokémon are analysed too"
    others = _all(owner, account, vintage="false")
    assert len(others) == SAMPLE_POKEMON - SAMPLE_VINTAGE
    transfers = _all(owner, account, status="TRANSFER_CANDIDATE")
    assert all(item["pokemon"]["vintage_year"] is None for item in transfers)
    box = owner.get("/api/v1/pokemon", account_id=account, vintage="true").json()
    assert box["total"] == SAMPLE_VINTAGE
    search = owner.get("/api/v1/pokemon", account_id=account, q="vintage").json()
    assert search["total"] == SAMPLE_VINTAGE
    dashboard = owner.get("/api/v1/dashboard", account_id=account).json()
    assert dashboard["cards"]["vintage"] == SAMPLE_VINTAGE


def test_sorting_and_rules(owner: Any, container: Any, gamedata: Any, export: dict[str, Any]) -> None:
    account = _imported(owner, container, export)
    items = _all(owner, account, sort="-keep")
    scores = [i["keep_score"] for i in items]
    assert scores == sorted(scores, reverse=True)
    rules = owner.get("/api/v1/cleanup/rules", account_id=account).json()
    assert "protect_favorites" not in rules["rules"] and rules["rules"]["keep_points_favorite"] == 25
    assert any(f["code"] == "VINTAGE" for f in rules["fixed"])
    changed = owner.put(f"/api/v1/cleanup/rules?account_id={account}", {"rules": {"keep_points_favorite": 40}})
    assert changed.status_code == 200 and changed.json()["rules"]["keep_points_favorite"] == 40
    bad = owner.put(f"/api/v1/cleanup/rules?account_id={account}", {"rules": {"review_threshold": 90}})
    assert bad.status_code == 422


def test_action_list_needs_confirmation_for_favorites(
    owner: Any, container: Any, gamedata: Any, export: dict[str, Any]
) -> None:
    account = _imported(owner, container, export)
    favorite = _all(owner, account, favorite="true", vintage="false")[0]["pokemon"]
    first = owner.post("/api/v1/cleanup/action-list", {"account_id": account, "ids": [favorite["id"]]}).json()
    assert first["count"] == 0
    assert first["needs_confirmation"][0]["pokemon_id"] == favorite["id"]
    assert "favorite" in first["needs_confirmation"][0]["kinds"]
    confirmed = owner.post(
        "/api/v1/cleanup/action-list",
        {"account_id": account, "ids": [favorite["id"]], "confirmed_ids": [favorite["id"]]},
    ).json()
    assert confirmed["count"] == 1 and not confirmed["needs_confirmation"]


def test_action_list_checks_protection_again_on_every_read(
    owner: Any, container: Any, gamedata: Any, export: dict[str, Any]
) -> None:
    account = _imported(owner, container, export)
    candidate = _all(owner, account, status="TRANSFER_CANDIDATE", favorite="false")[0]["pokemon"]
    favorite = _all(owner, account, favorite="true", vintage="false")[0]["pokemon"]
    pid, fid = candidate["id"], favorite["id"]
    owner.post("/api/v1/cleanup/action-list", {"account_id": account, "ids": [pid]})
    owner.post("/api/v1/cleanup/action-list", {"account_id": account, "ids": [fid], "confirmed_ids": [fid]})

    def listed() -> dict[str, Any]:
        return owner.get("/api/v1/cleanup/action-list", account_id=account).json()

    items = {i["pokemon"]["id"]: i for i in listed()["items"]}
    assert items[pid]["executable"] and items[fid]["executable"], "a confirmed favorite stays executable"
    assert len(listed()["search_hint"]["queries"]) >= 1

    # Protection that appears after the Pokémon was listed takes it out of everything executable.
    assert owner.patch(f"/api/v1/pokemon/{pid}/metadata", {"protected": True}).status_code == 200
    data = listed()
    item = next(i for i in data["items"] if i["pokemon"]["id"] == pid)
    assert not item["executable"] and item["blocked"] == "Handmatig beschermd"
    assert f"cp{candidate['cp']}" not in " ".join(q["query"] for q in data["search_hint"]["queries"])
    done = owner.post("/api/v1/cleanup/action-list", {"account_id": account, "ids": [pid], "mode": "done"}).json()
    assert done["skipped"][0]["reason"] == "Handmatig beschermd"
    csv = owner.get("/api/v1/cleanup/export", account_id=account).text
    assert "Handmatig beschermd" in csv
    checklist = owner.get("/api/v1/cleanup/export", account_id=account, format="html").text
    assert candidate["source_pokemon_id"] not in checklist and "staan hier niet op" in checklist

    # Lifting the protection makes it executable again.
    assert owner.patch(f"/api/v1/pokemon/{pid}/metadata", {"protected": False}).status_code == 200
    assert next(i for i in listed()["items"] if i["pokemon"]["id"] == pid)["executable"]


def test_unconfirmed_protection_on_a_list_asks_again(
    owner: Any, container: Any, gamedata: Any, export: dict[str, Any]
) -> None:
    account = _imported(owner, container, export)
    favorite = _all(owner, account, favorite="true", vintage="false")[0]["pokemon"]
    fid = favorite["id"]
    owner.post("/api/v1/cleanup/action-list", {"account_id": account, "ids": [fid], "confirmed_ids": [fid]})
    # Simulate a list entry from before confirmations were stored.
    with container.db.transaction() as session:
        session.scalars(select(PlannedAction).where(PlannedAction.pokemon_id == fid)).one().confirmed = []
    item = owner.get("/api/v1/cleanup/action-list", account_id=account).json()["items"][0]
    assert not item["executable"] and "favorite" in item["needs_confirmation"]["kinds"]
    again = owner.post(
        "/api/v1/cleanup/action-list", {"account_id": account, "ids": [fid], "confirmed_ids": [fid]}
    ).json()
    assert again["items"][0]["executable"]


def test_confirmation_covers_the_concrete_reasons_of_that_moment(
    owner: Any, container: Any, gamedata: Any, export: dict[str, Any]
) -> None:
    # Re-check of 24 October (A03): a confirmation names the tags and rules it covered.
    account = _imported(owner, container, export)
    pid = _all(owner, account, status="TRANSFER_CANDIDATE", favorite="false")[0]["pokemon"]["id"]
    with container.db.transaction() as session:
        pokemon = session.get(Pokemon, pid)
        assert pokemon is not None
        pokemon.tag_ids = ["999", "1000"]

    def label(tag_id: str, name: str, protects: bool) -> None:
        body = {"account_id": account, "tag_id": tag_id, "label": name, "protects": protects}
        assert owner.put("/api/v1/pokemon/tags/labels", body).status_code == 200

    def item() -> dict[str, Any]:
        return owner.get("/api/v1/cleanup/action-list", account_id=account).json()["items"][0]

    label("999", "Ruilvoorraad", True)
    label("1000", "Familie", True)
    owner.post("/api/v1/cleanup/action-list", {"account_id": account, "ids": [pid], "confirmed_ids": [pid]})
    with container.db.read() as session:
        stored = session.scalars(select(PlannedAction).where(PlannedAction.pokemon_id == pid)).one().confirmed
    assert set(stored) == {"protected:TAG:999", "protected:TAG:1000"}

    # A reason that disappears asks for nothing new.
    label("1000", "Familie", False)
    assert item()["executable"]
    # The same tag protecting again was part of the confirmation.
    label("1000", "Familie", True)
    assert item()["executable"]
    # A rule that starts to apply is a new reason, and the question names it. Nicknames are
    # protected by default.
    with container.db.transaction() as session:
        pokemon = session.get(Pokemon, pid)
        assert pokemon is not None
        pokemon.nickname = "Bijnaam"
    current = item()
    assert not current["executable"]
    assert current["needs_confirmation"]["new_reasons"] == ["Heeft een bijnaam"]
    again = owner.post(
        "/api/v1/cleanup/action-list", {"account_id": account, "ids": [pid], "confirmed_ids": [pid]}
    ).json()
    assert again["items"][0]["executable"]


def test_confirmations_from_before_concrete_reasons_ask_again_for_rules_only(
    owner: Any, container: Any, gamedata: Any, export: dict[str, Any]
) -> None:
    account = _imported(owner, container, export)
    favorite = _all(owner, account, favorite="true", vintage="false")[0]["pokemon"]["id"]
    shiny = next(
        i["pokemon"]["id"]
        for i in _all(owner, account, vintage="false", favorite="false")
        if any(r["code"] == "SHINY" for r in i["protection_reasons"]) and i["pokemon"]["catch_date_known"]
    )
    for pid in (favorite, shiny):
        owner.post("/api/v1/cleanup/action-list", {"account_id": account, "ids": [pid], "confirmed_ids": [pid]})
    # What an action list stored before this change: kinds only.
    with container.db.transaction() as session:
        for action in session.scalars(select(PlannedAction)):
            action.confirmed = ["favorite"] if action.pokemon_id == favorite else ["protected"]
    items = {
        i["pokemon"]["id"]: i for i in owner.get("/api/v1/cleanup/action-list", account_id=account).json()["items"]
    }
    assert items[favorite]["executable"]
    assert not items[shiny]["executable"] and items[shiny]["needs_confirmation"]["new_reasons"] == ["Shiny"]


def test_vintage_needs_an_explicit_override(owner: Any, container: Any, gamedata: Any, export: dict[str, Any]) -> None:
    account = _imported(owner, container, export)
    pokemon = _all(owner, account, vintage="true")[0]["pokemon"]
    pid = pokemon["id"]
    blocked = owner.post("/api/v1/cleanup/action-list", {"account_id": account, "ids": [pid], "confirmed_ids": [pid]})
    assert blocked.json()["count"] == 0 and "Vintage" in blocked.json()["skipped"][0]["reason"]
    bulk = owner.post(
        "/api/v1/pokemon/bulk",
        {"account_id": account, "ids": [pid], "action": "add_to_list", "confirmed_ids": [pid]},
    ).json()
    assert bulk["updated"] == 0 and "bulk" in bulk["skipped"][0]["reason"]

    refused = owner.patch(f"/api/v1/pokemon/{pid}/metadata", {"override_status": "TRANSFER_CANDIDATE"})
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "VINTAGE_CONFIRMATION_REQUIRED"
    accepted = owner.patch(
        f"/api/v1/pokemon/{pid}/metadata",
        {"override_status": "TRANSFER_CANDIDATE", "confirm_vintage_override": True},
    )
    assert accepted.status_code == 200
    container.runner.drain()
    item = next(i for i in _all(owner, account, vintage="true") if i["pokemon"]["id"] == pid)
    assert item["status"] == "TRANSFER_CANDIDATE" and item["warnings"][0]["code"] == "VINTAGE_OVERRIDE"

    unconfirmed = owner.post("/api/v1/cleanup/action-list", {"account_id": account, "ids": [pid]}).json()
    assert unconfirmed["count"] == 0 and "vintage" in unconfirmed["needs_confirmation"][0]["kinds"]
    listed = owner.post(
        "/api/v1/cleanup/action-list", {"account_id": account, "ids": [pid], "confirmed_ids": [pid]}
    ).json()
    assert listed["count"] == 1


def test_manual_protection_and_notes_survive_reanalysis(
    owner: Any, container: Any, gamedata: Any, export: dict[str, Any]
) -> None:
    account = _imported(owner, container, export)
    item = _all(owner, account, vintage="false")[0]["pokemon"]
    owner.patch(f"/api/v1/pokemon/{item['id']}/metadata", {"protected": True, "notes": "Bewaren voor ruil"})
    owner.post(f"/api/v1/cleanup/analyze?account_id={account}")
    container.runner.drain()
    detail = owner.get(f"/api/v1/pokemon/{item['id']}").json()
    assert detail["metadata"]["protected"] is True and detail["metadata"]["notes"] == "Bewaren voor ruil"
    assert detail["cleanup"]["status"] == "PROTECT"
    result = owner.post("/api/v1/cleanup/action-list", {"account_id": account, "ids": [item["id"]]}).json()
    assert result["count"] == 0 and result["skipped"][0]["reason"] == "Handmatig beschermd"


def test_new_engine_version_recomputes_all_analyses(
    owner: Any, container: Any, gamedata: Any, export: dict[str, Any]
) -> None:
    account = _imported(owner, container, export)
    with container.db.transaction() as session:
        run = session.scalars(select(AnalysisRun).where(AnalysisRun.trainer_account_id == account)).first()
        assert run is not None
        run.engine_version = "cleanup-1.0"
    assert schedule_outdated_analyses(container) == 1
    with container.db.read() as session:
        queued = session.scalars(
            select(BackgroundJob).where(BackgroundJob.kind == "analysis", BackgroundJob.status == "queued")
        ).all()
        assert [job.trainer_account_id for job in queued] == [account]
    container.runner.drain()
    assert schedule_outdated_analyses(container) == 0
