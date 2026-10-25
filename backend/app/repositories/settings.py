"""Key/value application settings."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models import AppSetting


def get_setting(session: Session, key: str, default: Any = None) -> Any:
    row = session.get(AppSetting, key)
    return default if row is None else row.value


def set_setting(session: Session, key: str, value: Any) -> None:
    row = session.get(AppSetting, key)
    now = datetime.now(UTC)
    if row is None:
        session.add(AppSetting(key=key, value=value, updated_at=now))
    else:
        row.value = value
        row.updated_at = now
