"""Trainer accounts, webhook credentials, trainer statistics and inventory."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONText, UTCDateTime


class TrainerAccount(Base):
    __tablename__ = "trainer_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    nickname: Mapped[str] = mapped_column(String(64))
    source_nickname: Mapped[str | None] = mapped_column(String(64))
    # HMAC-SHA256 of PGSharp's obfuscatedPlayerId, keyed with the installation secret. The raw
    # identifier is never stored. Used only to detect an export from a different account.
    source_fingerprint: Mapped[str | None] = mapped_column(String(64))
    trainer_level: Mapped[int | None] = mapped_column(Integer)
    experience: Mapped[int | None] = mapped_column(BigInteger)
    stardust: Mapped[int | None] = mapped_column(BigInteger)
    pokecoins: Mapped[int | None] = mapped_column(BigInteger)
    team: Mapped[int | None] = mapped_column(Integer)
    max_pokemon_storage: Mapped[int | None] = mapped_column(Integer)
    max_item_storage: Mapped[int | None] = mapped_column(Integer)
    stats: Mapped[dict[str, Any] | None] = mapped_column(JSONText)
    last_successful_sync_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_export_time: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_import_attempt_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    sync_status: Mapped[str] = mapped_column(String(16), default="waiting")
    settings: Mapped[dict[str, Any]] = mapped_column(JSONText, default=dict)
    diagnostics_until: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)


class WebhookCredential(Base):
    __tablename__ = "webhook_credentials"

    id: Mapped[int] = mapped_column(primary_key=True)
    trainer_account_id: Mapped[int] = mapped_column(ForeignKey("trainer_accounts.id", ondelete="CASCADE"), index=True)
    token_identifier: Mapped[str] = mapped_column(String(16), unique=True)
    token_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    last_used_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | revoked


class ItemInventory(Base):
    __tablename__ = "item_inventory"

    trainer_account_id: Mapped[int] = mapped_column(
        ForeignKey("trainer_accounts.id", ondelete="CASCADE"), primary_key=True
    )
    item_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_name: Mapped[str | None] = mapped_column(String(80))
    count: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)


class InventorySnapshot(Base):
    __tablename__ = "inventory_snapshots"
    __table_args__ = (Index("ix_inventory_snapshots_account", "trainer_account_id", "id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    trainer_account_id: Mapped[int] = mapped_column(ForeignKey("trainer_accounts.id", ondelete="CASCADE"))
    sync_run_id: Mapped[int] = mapped_column(ForeignKey("sync_runs.id", ondelete="CASCADE"))
    items: Mapped[dict[str, int]] = mapped_column(JSONText)
    trainer: Mapped[dict[str, Any]] = mapped_column(JSONText)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)


class ManualResource(Base):
    """Resources PGSharp does not export (species candy, XL candy, mega energy)."""

    __tablename__ = "manual_resources"

    trainer_account_id: Mapped[int] = mapped_column(
        ForeignKey("trainer_accounts.id", ondelete="CASCADE"), primary_key=True
    )
    kind: Mapped[str] = mapped_column(String(16), primary_key=True)  # candy | xl_candy | mega
    key: Mapped[str] = mapped_column(String(64), primary_key=True)  # family id
    quantity: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)


class TagLabel(Base):
    """User-chosen names for PGSharp tag IDs. The export carries IDs, not tag names."""

    __tablename__ = "tag_labels"

    trainer_account_id: Mapped[int] = mapped_column(
        ForeignKey("trainer_accounts.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[str] = mapped_column(String(24), primary_key=True)
    label: Mapped[str] = mapped_column(String(64))
    # A Pokémon carrying a protecting tag is never proposed as a transfer candidate.
    protects: Mapped[bool] = mapped_column(Boolean, default=False)
