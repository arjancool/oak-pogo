"""Game Data versions and application settings."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONText, UTCDateTime


class GameDataVersion(Base):
    __tablename__ = "game_data_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(String(16))  # ready | active | failed | archived
    origin: Mapped[str] = mapped_column(String(16))  # download | upload
    schema_version: Mapped[int] = mapped_column(Integer)
    content_sha256: Mapped[str | None] = mapped_column(String(64))
    file_name: Mapped[str | None] = mapped_column(String(80))
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JSONText, default=list)
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSONText)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    activated_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class GameEvent(Base):
    """An event from the calendar feed, or one a user added for a trainer account (ADR-0021)."""

    __tablename__ = "game_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(16))  # leekduck | manual
    external_id: Mapped[str] = mapped_column(String(160))
    # Only for events a user added. Feed events belong to the installation.
    trainer_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("trainer_accounts.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(40))
    starts_at: Mapped[datetime] = mapped_column(UTCDateTime)
    ends_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    # Times in the feed without a 'Z' are wall-clock time, the same everywhere.
    local_time: Mapped[bool] = mapped_column(Boolean, default=False)
    link: Mapped[str | None] = mapped_column(String(300))
    featured: Mapped[list[str]] = mapped_column(JSONText, default=list)
    featured_dex: Mapped[list[int]] = mapped_column(JSONText, default=list)
    bonuses: Mapped[list[str]] = mapped_column(JSONText, default=list)
    feed_version: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSONText)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)
