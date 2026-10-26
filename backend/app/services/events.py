"""The event calendar: download, store and prepare it for the cleanup rules (ADR-0021).

Feed events come from LeekDuck.com, published as JSON by ScrapedDuck. They belong to the
installation and are replaced as a whole by a newer download that passed the checks. Events a
user adds belong to one trainer account, as does the list of feed events that account ignores.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import Iterable
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.db import Database
from app.gamedata.fetch import USER_AGENT
from app.gamedata.model import GameData
from app.gamedata.transform import norm_key
from app.models import GameEvent, TrainerAccount
from app.normalizers.events import EventFeedError, parse_events
from app.recommendations.events import MANUAL, EventInfo, relevant
from app.recommendations.rules import CleanupRules
from app.repositories.settings import get_setting, set_setting

log = logging.getLogger("oak.events")

FEED = "leekduck"
FEED_SOURCE = "LeekDuck.com via ScrapedDuck"
MANUAL_SOURCE = "Eigen event"
FEED_KEY = "events.feed"
IGNORED_KEY = "ignored_events"
HTTP_NOT_MODIFIED = 304
REGIONAL = re.compile(r"^(alolan|galarian|hisuian|paldean)\s+", re.IGNORECASE)


# --- download -------------------------------------------------------------------------------


def update_events(settings: Settings, db: Database, now: datetime, content: bytes | None = None) -> dict[str, Any]:
    """Download (or take ``content``), check and store the calendar. Never raises for a bad
    download: the previous events stay and the error is recorded."""
    with db.read() as session:
        previous = get_setting(session, FEED_KEY) or {}
    etag = None
    try:
        if content is None:
            with httpx.Client(
                timeout=settings.gamedata_timeout_seconds,
                headers={"User-Agent": USER_AGENT},
                follow_redirects=True,
            ) as client:
                headers = {"If-None-Match": previous["etag"]} if previous.get("etag") else {}
                response = client.get(settings.events_url, headers=headers)
                if response.status_code == HTTP_NOT_MODIFIED:
                    return _record(db, previous, now, status="unchanged")
                response.raise_for_status()
                content, etag = response.content, response.headers.get("etag")
        sha = hashlib.sha256(content).hexdigest()
        if sha == previous.get("sha256"):
            return _record(db, {**previous, "etag": etag or previous.get("etag")}, now, status="unchanged")
        events, skipped = parse_events(json.loads(content), ZoneInfo(settings.timezone))
    except (httpx.HTTPError, ValueError) as exc:
        if isinstance(exc, EventFeedError):
            text = {"code": exc.code, "text": str(exc), "data": exc.data}
        else:
            name = type(exc).__name__
            text = {
                "code": "FEED_UNAVAILABLE",
                "text": f"Eventkalender niet bruikbaar of niet bereikbaar: {name}",
                "data": {"error": name},
            }
        log.warning("event calendar update failed", extra={"error": text["text"][:300]})
        return _record(db, previous, now, status="failed", error=text)
    with db.transaction() as session:
        session.execute(delete(GameEvent).where(GameEvent.source == FEED))
        for event in events:
            session.add(
                GameEvent(
                    source=FEED,
                    external_id=event.external_id,
                    trainer_account_id=None,
                    name=event.name,
                    kind=event.kind,
                    starts_at=event.starts_at,
                    ends_at=event.ends_at,
                    local_time=event.local_time,
                    link=event.link,
                    featured=event.featured,
                    featured_dex=[],
                    bonuses=event.bonuses,
                    feed_version=sha,
                    created_at=now,
                )
            )
    feed = {"sha256": sha, "etag": etag, "fetched_at": now.isoformat(), "count": len(events), "skipped": skipped}
    log.info("event calendar updated", extra={"events": len(events), "skipped": skipped})
    return _record(db, feed, now, status="updated")


def _record(
    db: Database, feed: dict[str, Any], now: datetime, *, status: str, error: dict[str, Any] | None = None
) -> dict[str, Any]:
    """``error`` is a server text: {code, text, data} (ADR-0025). The Dutch text is kept as
    ``error`` and the whole text as ``error_text``."""
    message = error["text"] if error else None
    state = {**feed, "checked_at": now.isoformat(), "error": message, "error_text": error, "url_source": FEED_SOURCE}
    with db.transaction() as session:
        set_setting(session, FEED_KEY, state)
    return {"status": status, "count": feed.get("count", 0), "error": message}


def feed_status(session: Session, settings: Settings) -> dict[str, Any]:
    state = get_setting(session, FEED_KEY) or {}
    return {
        "source": FEED_SOURCE,
        "url": settings.events_url,
        "auto_update": settings.events_auto_update,
        "version": (state.get("sha256") or "")[:12] or None,
        "fetched_at": state.get("fetched_at"),
        "checked_at": state.get("checked_at"),
        "count": state.get("count", 0),
        "skipped": state.get("skipped", 0),
        # A server text; a failure recorded before OAK kept its code has only the Dutch text.
        "error": state.get("error_text") or ({"text": state["error"]} if state.get("error") else None),
    }


# --- events for one account -----------------------------------------------------------------


def ignored_events(account: TrainerAccount) -> set[str]:
    return {str(v) for v in (account.settings or {}).get(IGNORED_KEY, [])}


def account_events(session: Session, account_id: int) -> list[GameEvent]:
    """Feed events and the account's own events, earliest first."""
    return list(
        session.scalars(
            select(GameEvent)
            .where(or_(GameEvent.trainer_account_id.is_(None), GameEvent.trainer_account_id == account_id))
            .order_by(GameEvent.starts_at, GameEvent.id)
        )
    )


def _name_index(gd: GameData) -> dict[str, int]:
    index: dict[str, int] = {}
    for dex, record in gd.species.items():
        for value in (record.get("key"), record.get("name")):
            if isinstance(value, str):
                index.setdefault(norm_key(value), int(dex))
    return index


def species_for(names: Iterable[str], gd: GameData) -> tuple[list[int], list[str]]:
    """Pokédex numbers for featured names, and the names the Game Data does not know."""
    index = _name_index(gd)
    found: list[int] = []
    unknown: list[str] = []
    for name in names:
        plain = REGIONAL.sub("", name.split("(")[0]).strip()
        dex = index.get(norm_key(plain))
        if dex is None:
            unknown.append(name)
        elif dex not in found:
            found.append(dex)
    return found, unknown


def families_for(dex_numbers: Iterable[int], gd: GameData) -> frozenset[str]:
    families = {(gd.species_record(dex) or {}).get("family") for dex in dex_numbers}
    return frozenset(f for f in families if isinstance(f, str))


def event_info(event: GameEvent, gd: GameData | None) -> EventInfo:
    dex = list(event.featured_dex) if event.source == MANUAL else []
    if gd is not None and event.source != MANUAL:
        dex, _unknown = species_for(event.featured, gd)
    return EventInfo(
        id=event.external_id,
        name=event.name,
        kind=MANUAL if event.source == MANUAL else event.kind,
        starts_at=event.starts_at,
        ends_at=event.ends_at,
        link=event.link,
        source=MANUAL_SOURCE if event.source == MANUAL else FEED_SOURCE,
        version=(event.feed_version or "")[:12] or None,
        families=families_for(dex, gd) if gd is not None else frozenset(),
        bonuses=tuple(event.bonuses),
    )


def event_infos(session: Session, account: TrainerAccount, gd: GameData | None) -> tuple[EventInfo, ...]:
    ignored = ignored_events(account)
    return tuple(
        event_info(e, gd)
        for e in account_events(session, account.id)
        if e.source == MANUAL or e.external_id not in ignored
    )


def event_key(events: Iterable[EventInfo], now: datetime, rules: CleanupRules) -> str:
    """What the rules see of the events right now. A change means the advice may change."""
    if not rules.use_events:
        return "off"
    active = relevant(events, now, rules.event_hold_days)
    payload = [
        [e.id, e.starts_at.isoformat(), e.ends_at.isoformat(), sorted(e.families), e.transfer_bonus] for e in active
    ]
    return hashlib.sha256(json.dumps(payload).encode()).hexdigest()
