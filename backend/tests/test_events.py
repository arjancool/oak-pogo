"""Upcoming events: the calendar feed, the cleanup rules and the API (ADR-0021)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.jobs.tasks import schedule_event_analyses
from app.models import BackgroundJob, GameEvent
from app.normalizers.events import EventFeedError, parse_events
from app.recommendations.events import EventInfo, hold_for, period, relevant, transfer_tip
from app.repositories.settings import get_setting
from app.services.analysis import AnalysisService
from app.services.events import FEED_KEY, update_events
from tests.conftest import PASSWORD, Api

AMS = ZoneInfo("Europe/Amsterdam")


def _local(moment: datetime) -> str:
    """Wall-clock time as the feed writes it: no zone, no 'Z'."""
    return moment.astimezone(AMS).replace(tzinfo=None).isoformat(timespec="milliseconds")


def community_day(event_id: str, species: str, starts_in: timedelta, hours: int = 3) -> dict[str, Any]:
    start = datetime.now(UTC) + starts_in
    return {
        "eventID": event_id,
        "name": f"{species} Community Day",
        "eventType": "community-day",
        "heading": "Community Day",
        "link": f"https://leekduck.com/events/{event_id}/",
        "image": "https://cdn.leekduck.com/x.png",
        "start": _local(start),
        "end": _local(start + timedelta(hours=hours)),
        "extraData": {
            "communityday": {
                "spawns": [{"name": species, "image": "https://cdn.leekduck.com/y.png"}],
                "bonuses": [{"text": "3× Catch Stardust", "image": "z"}],
            }
        },
    }


def spotlight(event_id: str, species: str, starts_in: timedelta, bonus: str) -> dict[str, Any]:
    start = datetime.now(UTC) + starts_in
    return {
        "eventID": event_id,
        "name": f"{species} Spotlight Hour",
        "eventType": "pokemon-spotlight-hour",
        "link": f"https://leekduck.com/events/{event_id}/",
        "start": _local(start),
        "end": _local(start + timedelta(hours=1)),
        "extraData": {"spotlight": {"name": species, "canBeShiny": True, "bonus": bonus, "list": [{"name": species}]}},
    }


def feed(*events: dict[str, Any]) -> bytes:
    return json.dumps(list(events)).encode()


def _imported(owner: Api, container: Any, export: dict[str, Any]) -> int:
    account = owner.account()
    owner.upload(account, export)
    container.runner.drain()
    return account


def _items(owner: Api, account: int) -> list[dict[str, Any]]:
    return owner.get("/api/v1/cleanup/recommendations", account_id=account, page_size=500).json()["items"]


def _candidate_species(owner: Api, account: int) -> tuple[str, list[int]]:
    """A species with transfer candidates in the sample, and their ids."""
    items = _items(owner, account)
    first = next(i for i in items if i["status"] == "TRANSFER_CANDIDATE")
    species = first["pokemon"]["species_name"]
    ids = [
        i["pokemon"]["id"]
        for i in items
        if i["pokemon"]["species_name"] == species and i["status"] == "TRANSFER_CANDIDATE"
    ]
    return species, ids


def _publish(container: Any, content: bytes) -> dict[str, Any]:
    return update_events(container.settings, container.db, container.clock.now(), content=content)


def _reanalyse(owner: Api, container: Any, account: int) -> None:
    owner.post("/api/v1/cleanup/analyze", params={"account_id": account})
    container.runner.drain()


# --- the feed ---------------------------------------------------------------------------------


def test_feed_times_and_details() -> None:
    raw = [
        community_day("cd", "Pawniard", timedelta(days=3)),
        spotlight("sh", "Gastly", timedelta(days=1), "2× Transfer Candy"),
        {
            "eventID": "utc",
            "name": "Global",
            "eventType": "event",
            "start": "2026-11-01T10:00:00.000Z",
            "end": "2026-11-01T12:00:00.000Z",
            "link": "http://insecure.example/",
        },
        {"eventID": "broken", "name": "No times", "eventType": "event"},
        "not an event",
    ]
    events, skipped = parse_events(raw, AMS)
    assert skipped == 2
    by_id = {e.external_id: e for e in events}
    assert by_id["cd"].featured == ["Pawniard"] and by_id["cd"].bonuses == ["3× Catch Stardust"]
    assert by_id["cd"].local_time is True
    assert by_id["sh"].featured == ["Gastly"] and by_id["sh"].bonuses == ["2× Transfer Candy"]
    utc = by_id["utc"]
    assert utc.local_time is False and utc.starts_at == datetime(2026, 11, 1, 10, tzinfo=UTC)
    assert utc.link is None  # only https links are kept


def test_wall_clock_times_follow_the_configured_zone() -> None:
    raw = [
        {
            "eventID": "x",
            "name": "X",
            "eventType": "event",
            "start": "2026-11-08T14:00:00.000",
            "end": "2026-11-08T17:00:00.000",
        }
    ]
    event = parse_events(raw, AMS)[0][0]
    assert event.starts_at == datetime(2026, 11, 8, 13, tzinfo=UTC)  # 14:00 in Amsterdam, winter time


@pytest.mark.parametrize("raw", [{"events": []}, [{"eventID": "x"}], "text"])
def test_an_unusable_feed_is_refused(raw: Any) -> None:
    with pytest.raises(EventFeedError):
        parse_events(raw, AMS)


def test_update_keeps_the_previous_events_when_a_download_is_bad(container: Any) -> None:
    good = feed(community_day("cd", "Magikarp", timedelta(days=2)))
    assert _publish(container, good)["status"] == "updated"
    assert _publish(container, good)["status"] == "unchanged"
    bad = _publish(container, b"<html>rate limited</html>")
    assert bad["status"] == "failed" and bad["error"]
    with container.db.read() as session:
        assert [e.external_id for e in session.scalars(select(GameEvent))] == ["cd"]
        state = get_setting(session, FEED_KEY)
        assert state["count"] == 1 and state["error"] and len(state["sha256"]) == 64


# --- the rules --------------------------------------------------------------------------------


def _info(event_id: str, starts_in: timedelta, *, kind: str = "community-day", **extra: Any) -> EventInfo:
    now = datetime(2026, 11, 1, 12, tzinfo=UTC)
    return EventInfo(
        id=event_id,
        name=event_id,
        kind=kind,
        starts_at=now + starts_in,
        ends_at=now + starts_in + timedelta(hours=3),
        link=None,
        source="test",
        version=None,
        **extra,
    )


def test_rules_pick_events_within_reach() -> None:
    now = datetime(2026, 11, 1, 12, tzinfo=UTC)
    near = _info("near", timedelta(days=3), families=frozenset({"FAMILY_X"}))
    far = _info("far", timedelta(days=20), families=frozenset({"FAMILY_X"}))
    over = _info("over", timedelta(days=-1), families=frozenset({"FAMILY_X"}))
    candy = _info("candy", timedelta(days=1), kind="pokemon-spotlight-hour", bonuses=("2× Transfer Candy",))
    events = relevant([far, over, near, candy], now, 14)
    assert [e.id for e in events] == ["candy", "near"]
    hold = hold_for("FAMILY_X", events)
    assert hold is not None and hold.id == "near"
    assert hold_for("FAMILY_Y", events) is None
    assert hold_for("FAMILY_X", [candy]) is None  # a Spotlight Hour holds nothing
    tip = transfer_tip(events)
    assert tip is not None and tip.id == "candy"
    assert period(near, AMS) == "4 nov 13:00–16:00"


# --- the cleanup advice -----------------------------------------------------------------------


def test_community_day_holds_the_family_until_it_ends(
    owner: Api, container: Any, gamedata: Any, export: dict[str, Any]
) -> None:
    account = _imported(owner, container, export)
    species, ids = _candidate_species(owner, account)
    _publish(container, feed(community_day("cd-near", species, timedelta(days=3))))
    _reanalyse(owner, container, account)
    held = {i["pokemon"]["id"]: i for i in _items(owner, account) if i["pokemon"]["id"] in ids}
    for item in held.values():
        assert item["status"] == "KEEP", item["reasons"]
        reason = item["reasons"][0]
        assert reason["code"] == "EVENT_HOLD" and f"{species} Community Day" in reason["text"]
        assert reason["data"]["source"] == "LeekDuck.com via ScrapedDuck" and reason["data"]["version"]
        assert item["confidence"] != "high"

    events = owner.get("/api/v1/events", account_id=account).json()
    listed = next(e for e in events["events"] if e["external_id"] == "cd-near")
    assert listed["in_reach"] and listed["held"] == len(ids)
    assert listed["species"] and not listed["unknown_names"]
    assert events["feed"]["source"] == "LeekDuck.com via ScrapedDuck"

    # Ignoring the event ends the hold.
    assert owner.put("/api/v1/events/cd-near/ignore", {"account_id": account, "ignored": True}).status_code == 200
    container.runner.drain()
    statuses = {i["pokemon"]["id"]: i["status"] for i in _items(owner, account)}
    assert all(statuses[pid] == "TRANSFER_CANDIDATE" for pid in ids)


@pytest.mark.parametrize("starts_in", [timedelta(days=30), timedelta(days=-2)])
def test_no_hold_for_events_out_of_reach_or_over(
    owner: Api, container: Any, gamedata: Any, export: dict[str, Any], starts_in: timedelta
) -> None:
    account = _imported(owner, container, export)
    species, ids = _candidate_species(owner, account)
    _publish(container, feed(community_day("cd", species, starts_in)))
    _reanalyse(owner, container, account)
    statuses = {i["pokemon"]["id"]: i["status"] for i in _items(owner, account)}
    assert all(statuses[pid] == "TRANSFER_CANDIDATE" for pid in ids)


def test_events_can_be_switched_off_and_an_override_wins(
    owner: Api, container: Any, gamedata: Any, export: dict[str, Any]
) -> None:
    account = _imported(owner, container, export)
    species, ids = _candidate_species(owner, account)
    _publish(container, feed(community_day("cd", species, timedelta(days=2))))
    override = owner.patch(f"/api/v1/pokemon/{ids[0]}/metadata", {"override_status": "TRANSFER_CANDIDATE"})
    assert override.status_code == 200, override.text
    _reanalyse(owner, container, account)
    statuses = {i["pokemon"]["id"]: i["status"] for i in _items(owner, account)}
    assert statuses[ids[0]] == "TRANSFER_CANDIDATE"  # the user's own decision
    assert all(statuses[pid] == "KEEP" for pid in ids[1:])

    switched = owner.put("/api/v1/cleanup/rules", {"rules": {"use_events": False}}, params={"account_id": account})
    assert switched.status_code == 200, switched.text
    container.runner.drain()
    statuses = {i["pokemon"]["id"]: i["status"] for i in _items(owner, account)}
    assert all(statuses[pid] == "TRANSFER_CANDIDATE" for pid in ids)


def test_transfer_candy_bonus_gives_a_timing_tip(
    owner: Api, container: Any, gamedata: Any, export: dict[str, Any]
) -> None:
    account = _imported(owner, container, export)
    _publish(container, feed(spotlight("sh", "Gastly", timedelta(days=1), "2× Transfer Candy")))
    _reanalyse(owner, container, account)
    candidates = [i for i in _items(owner, account) if i["status"] == "TRANSFER_CANDIDATE"]
    assert candidates
    for item in candidates:
        tip = item["reasons"][-1]
        assert tip["code"] == "TRANSFER_TIMING" and "2× Transfer Candy" in tip["text"]


def test_an_event_of_your_own_holds_its_species(
    owner: Api, container: Any, gamedata: Any, export: dict[str, Any]
) -> None:
    account = _imported(owner, container, export)
    _species, ids = _candidate_species(owner, account)
    dex = next(i["pokemon"]["species_id"] for i in _items(owner, account) if i["pokemon"]["id"] == ids[0])
    start = datetime.now(UTC) + timedelta(days=1)
    body = {
        "account_id": account,
        "name": "Ruilavond",
        "starts_at": start.isoformat(),
        "ends_at": (start + timedelta(hours=2)).isoformat(),
        "species": [dex],
    }
    created = owner.post("/api/v1/events/manual", body)
    assert created.status_code == 201, created.text
    container.runner.drain()
    item = next(i for i in _items(owner, account) if i["pokemon"]["id"] == ids[0])
    assert item["status"] == "KEEP" and "Ruilavond" in item["reasons"][0]["text"]

    bad = owner.post("/api/v1/events/manual", {**body, "ends_at": body["starts_at"]})
    assert bad.status_code == 422
    event_id = created.json()["id"]
    assert owner.delete(f"/api/v1/events/manual/{event_id}", params={"account_id": account}).status_code == 204
    container.runner.drain()
    item = next(i for i in _items(owner, account) if i["pokemon"]["id"] == ids[0])
    assert item["status"] == "TRANSFER_CANDIDATE"


def test_events_of_one_account_stay_with_that_account(
    app: Any, owner: Api, container: Any, gamedata: Any, export: dict[str, Any]
) -> None:
    account = _imported(owner, container, export)
    start = datetime.now(UTC) + timedelta(days=1)
    created = owner.post(
        "/api/v1/events/manual",
        {
            "account_id": account,
            "name": "Privé",
            "starts_at": start.isoformat(),
            "ends_at": (start + timedelta(hours=1)).isoformat(),
            "species": [129],
        },
    ).json()
    assert owner.post("/api/v1/users", {"username": "andere", "password": PASSWORD}).status_code == 201
    with TestClient(app) as other_client:
        other = Api(other_client)
        assert other.login("andere").status_code == 200
        own = other.account("Eigen")
        assert other.get("/api/v1/events", account_id=account).status_code == 404
        names = [e["name"] for e in other.get("/api/v1/events", account_id=own).json()["events"]]
        assert "Privé" not in names
        assert other.delete(f"/api/v1/events/manual/{created['id']}", params={"account_id": own}).status_code == 404
        assert other.post("/api/v1/events/update").status_code == 403


def test_a_change_of_events_within_reach_queues_new_analyses(
    owner: Api, container: Any, gamedata: Any, export: dict[str, Any]
) -> None:
    account = _imported(owner, container, export)
    service = AnalysisService(container.settings, container.db, container.gamedata, container.clock)
    schedule_event_analyses(container, service)
    with container.db.read() as session:
        assert session.scalar(select(BackgroundJob).where(BackgroundJob.status == "queued")) is None
    _publish(container, feed(community_day("cd", "Magikarp", timedelta(days=2))))
    schedule_event_analyses(container, service)
    with container.db.read() as session:
        queued = session.scalars(select(BackgroundJob).where(BackgroundJob.status == "queued")).all()
        assert [(j.kind, j.trainer_account_id) for j in queued] == [("analysis", account)]
