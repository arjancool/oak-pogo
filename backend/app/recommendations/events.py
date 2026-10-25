"""Cleanup rules for upcoming events (ADR-0021). Deterministic and pure.

* A transfer candidate from the evolution family of a Pokémon with a Community Day within the
  configured number of days becomes KEEP until that event ends. During a Community Day an
  evolution often gets a special move, so the Pokémon may be worth more then.
* An event the user added for the account holds the families of its Pokémon the same way.
* A remaining transfer candidate gets a tip when an event with double Transfer Candy is near.

A decision the user recorded (an override) always wins. Every reason names the event, its
period, the source and the version of the event data.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

COMMUNITY_DAY = "community-day"
MANUAL = "manual"
HOLD_KINDS = frozenset({COMMUNITY_DAY, MANUAL})
TRANSFER_CANDY = re.compile(r"transfer\s+candy", re.IGNORECASE)
MONTHS = ("jan", "feb", "mrt", "apr", "mei", "jun", "jul", "aug", "sep", "okt", "nov", "dec")


@dataclass(frozen=True, slots=True)
class EventInfo:
    id: str
    name: str
    kind: str
    starts_at: datetime
    ends_at: datetime
    link: str | None
    source: str
    version: str | None
    families: frozenset[str] = frozenset()
    bonuses: tuple[str, ...] = ()

    @property
    def transfer_bonus(self) -> str | None:
        return next((b for b in self.bonuses if TRANSFER_CANDY.search(b)), None)


def relevant(events: Iterable[EventInfo], now: datetime, horizon_days: int) -> list[EventInfo]:
    """Events that have not ended and start within the horizon, earliest first."""
    limit = now + timedelta(days=horizon_days)
    return sorted((e for e in events if e.ends_at > now and e.starts_at <= limit), key=lambda e: e.starts_at)


def hold_for(family: str | None, events: Iterable[EventInfo]) -> EventInfo | None:
    if family is None:
        return None
    return next((e for e in events if e.kind in HOLD_KINDS and family in e.families), None)


def transfer_tip(events: Iterable[EventInfo]) -> EventInfo | None:
    return next((e for e in events if e.transfer_bonus), None)


def period(event: EventInfo, tz: ZoneInfo) -> str:
    """'8 nov 14:00–17:00', or with both dates when the event spans days."""
    start, end = event.starts_at.astimezone(tz), event.ends_at.astimezone(tz)

    def day(moment: datetime) -> str:
        return f"{moment.day} {MONTHS[moment.month - 1]}"

    if start.date() == end.date():
        return f"{day(start)} {start:%H:%M}–{end:%H:%M}"
    return f"{day(start)} {start:%H:%M} tot {day(end)} {end:%H:%M}"


def _data(event: EventInfo) -> dict[str, Any]:
    return {
        "event_id": event.id,
        "until": event.ends_at.isoformat(),
        "link": event.link,
        "source": event.source,
        "version": event.version,
    }


def hold_reason(event: EventInfo, tz: ZoneInfo) -> dict[str, Any]:
    if event.kind == COMMUNITY_DAY:
        text = (
            f"Bewaren tot na {event.name} ({period(event, tz)}): Community Day voor deze evolutielijn. Evolueren "
            "tijdens een Community Day geeft vaak een speciale aanval. Bekijk de eventdetails."
        )
    else:
        text = f"Bewaren tot na {event.name} ({period(event, tz)}), een event dat je zelf toevoegde."
    return {"code": "EVENT_HOLD", "text": text, "data": _data(event)}


def tip_reason(event: EventInfo, tz: ZoneInfo) -> dict[str, Any]:
    text = f"Wacht met overzetten tot {event.name} ({period(event, tz)}): {event.transfer_bonus}."
    return {"code": "TRANSFER_TIMING", "text": text, "data": _data(event)}
