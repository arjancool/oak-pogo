"""Timestamp helpers. OAK stores UTC and converts to the configured zone only for display."""

from __future__ import annotations

from datetime import UTC, datetime

MS_PER_SECOND = 1000


def from_epoch_ms(value: object) -> datetime | None:
    if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
        return None
    try:
        return datetime.fromtimestamp(value / MS_PER_SECOND, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
