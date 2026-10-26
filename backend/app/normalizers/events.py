"""Read the event calendar of LeekDuck.com, as published by ScrapedDuck (ADR-0021). Pure code.

The feed is a JSON list. Every event has ``eventID``, ``name``, ``eventType``, ``start`` and
``end``; times without a trailing ``Z`` are wall-clock time, the same in every time zone, and
OAK reads them in ``OAK_TIMEZONE``. Featured Pokémon and bonuses sit in ``extraData`` and differ
per type. Only what the rules need is kept; images are left out (ADR-0020).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

MAX_EVENTS = 2000
MAX_TEXT = 200


class EventFeedError(ValueError):
    """The download is not a usable event calendar. The stored events stay as they are.

    ``code`` and ``data`` let the interface show the message in another language (ADR-0025).
    """

    def __init__(self, code: str, message: str, **data: Any) -> None:
        super().__init__(message)
        self.code = code
        self.data = data


@dataclass(frozen=True, slots=True)
class ParsedEvent:
    external_id: str
    name: str
    kind: str
    starts_at: datetime
    ends_at: datetime
    local_time: bool
    link: str | None
    featured: list[str] = field(default_factory=list)
    bonuses: list[str] = field(default_factory=list)


def parse_time(value: Any, tz: ZoneInfo) -> tuple[datetime, bool] | None:
    """A feed time in UTC, and whether it was wall-clock time. None if it is not a time."""
    if not isinstance(value, str) or not value:
        return None
    text = value.strip()
    utc = text.endswith(("Z", "z"))
    try:
        moment = datetime.fromisoformat(text[:-1] + "+00:00" if utc else text)
    except ValueError:
        return None
    if moment.tzinfo is None:
        return moment.replace(tzinfo=tz).astimezone(UTC), True
    return moment.astimezone(UTC), False


def _text(value: Any) -> str | None:
    return value.strip()[:MAX_TEXT] if isinstance(value, str) and value.strip() else None


def _names(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    return [name for item in items if isinstance(item, Mapping) and (name := _text(item.get("name")))]


def _details(kind: str, extra: Any) -> tuple[list[str], list[str]]:
    """Featured Pokémon and bonus texts for the event types the rules use."""
    if not isinstance(extra, Mapping):
        return [], []
    if kind == "community-day" and isinstance(extra.get("communityday"), Mapping):
        day = extra["communityday"]
        bonuses = [text for b in day.get("bonuses") or [] if isinstance(b, Mapping) and (text := _text(b.get("text")))]
        return _names(day.get("spawns")), bonuses
    if kind == "pokemon-spotlight-hour" and isinstance(extra.get("spotlight"), Mapping):
        spot = extra["spotlight"]
        names = _names(spot.get("list")) or [n for n in [_text(spot.get("name"))] if n]
        bonus = _text(spot.get("bonus"))
        return names, [bonus] if bonus else []
    return [], []


def parse_events(raw: Any, tz: ZoneInfo) -> tuple[list[ParsedEvent], int]:
    """The usable events and the number of entries that were skipped.

    Raises :class:`EventFeedError` when the download as a whole is not an event calendar, so a
    broken download never replaces good data.
    """
    if not isinstance(raw, list):
        raise EventFeedError("FEED_NOT_A_LIST", "De eventkalender is geen lijst.")
    if len(raw) > MAX_EVENTS:
        raise EventFeedError("FEED_TOO_LARGE", f"De eventkalender bevat meer dan {MAX_EVENTS} events.", max=MAX_EVENTS)
    events: list[ParsedEvent] = []
    skipped = 0
    seen: set[str] = set()
    for entry in raw:
        if not isinstance(entry, Mapping):
            skipped += 1
            continue
        external_id = _text(entry.get("eventID"))
        name = _text(entry.get("name"))
        kind = _text(entry.get("eventType"))
        start = parse_time(entry.get("start"), tz)
        end = parse_time(entry.get("end"), tz)
        if not external_id or not name or not kind or start is None or end is None or end[0] < start[0]:
            skipped += 1
            continue
        if external_id in seen:
            skipped += 1
            continue
        seen.add(external_id)
        link = _text(entry.get("link"))
        featured, bonuses = _details(kind, entry.get("extraData"))
        events.append(
            ParsedEvent(
                external_id=external_id,
                name=name,
                kind=kind,
                starts_at=start[0],
                ends_at=end[0],
                local_time=start[1],
                link=link if link and link.startswith("https://") else None,
                featured=featured,
                bonuses=bonuses,
            )
        )
    if raw and not events:
        raise EventFeedError("FEED_NOTHING_USABLE", "Geen enkel event in de kalender is bruikbaar.")
    return events, skipped
