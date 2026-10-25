"""Import jobs, import issues, sync runs and the background job queue."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONText, UTCDateTime


class ImportJob(Base):
    __tablename__ = "import_jobs"
    __table_args__ = (
        Index("ix_import_jobs_account_received", "trainer_account_id", "received_at"),
        Index("ix_import_jobs_account_hash", "trainer_account_id", "payload_sha256"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    trainer_account_id: Mapped[int] = mapped_column(ForeignKey("trainer_accounts.id", ondelete="CASCADE"))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    source: Mapped[str] = mapped_column(String(16))  # webhook | upload | retry
    status: Mapped[str] = mapped_column(String(16))
    stage: Mapped[str | None] = mapped_column(String(32))
    progress: Mapped[int] = mapped_column(Integer, default=0)
    payload_sha256: Mapped[str] = mapped_column(String(64))
    payload_size: Mapped[int] = mapped_column(Integer)
    payload_file: Mapped[str | None] = mapped_column(String(64))
    payload_purged_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    filename: Mapped[str | None] = mapped_column(String(120))
    request_meta: Mapped[dict[str, Any] | None] = mapped_column(JSONText)
    schema_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONText)
    fingerprint: Mapped[str | None] = mapped_column(String(64))
    export_time: Mapped[datetime | None] = mapped_column(UTCDateTime)
    classification: Mapped[str | None] = mapped_column(String(16))
    confirm_full: Mapped[bool] = mapped_column(Boolean, default=False)
    retry_of_id: Mapped[int | None] = mapped_column(ForeignKey("import_jobs.id", ondelete="SET NULL"))
    duplicate_of_id: Mapped[int | None] = mapped_column(ForeignKey("import_jobs.id", ondelete="SET NULL"))
    sync_run_id: Mapped[int | None] = mapped_column(ForeignKey("sync_runs.id", ondelete="SET NULL", use_alter=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(48))
    error_message: Mapped[str | None] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(UTCDateTime)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class ImportIssue(Base):
    """A validation error or warning found while processing an import (spec entity ImportError)."""

    __tablename__ = "import_errors"

    id: Mapped[int] = mapped_column(primary_key=True)
    import_job_id: Mapped[int] = mapped_column(ForeignKey("import_jobs.id", ondelete="CASCADE"), index=True)
    severity: Mapped[str] = mapped_column(String(8))  # error | warning | info
    code: Mapped[str] = mapped_column(String(48))
    message: Mapped[str] = mapped_column(Text)
    path: Mapped[str | None] = mapped_column(String(200))
    source_pokemon_id: Mapped[str | None] = mapped_column(String(24))


class SyncRun(Base):
    __tablename__ = "sync_runs"
    __table_args__ = (Index("ix_sync_runs_account_applied", "trainer_account_id", "applied_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    trainer_account_id: Mapped[int] = mapped_column(ForeignKey("trainer_accounts.id", ondelete="CASCADE"))
    import_job_id: Mapped[int | None] = mapped_column(ForeignKey("import_jobs.id", ondelete="SET NULL"))
    source: Mapped[str] = mapped_column(String(16))
    classification: Mapped[str] = mapped_column(String(16))  # full | partial
    export_time: Mapped[datetime | None] = mapped_column(UTCDateTime)
    applied_at: Mapped[datetime] = mapped_column(UTCDateTime)
    total_pokemon: Mapped[int] = mapped_column(Integer, default=0)
    eggs: Mapped[int] = mapped_column(Integer, default=0)
    new_count: Mapped[int] = mapped_column(Integer, default=0)
    changed_count: Mapped[int] = mapped_column(Integer, default=0)
    unchanged_count: Mapped[int] = mapped_column(Integer, default=0)
    missing_count: Mapped[int] = mapped_column(Integer, default=0)
    missing_unconfirmed_count: Mapped[int] = mapped_column(Integer, default=0)
    reappeared_count: Mapped[int] = mapped_column(Integer, default=0)
    items_changed: Mapped[bool] = mapped_column(Boolean, default=False)
    warnings: Mapped[list[dict[str, Any]]] = mapped_column(JSONText, default=list)
    previous_sync_run_id: Mapped[int | None] = mapped_column(ForeignKey("sync_runs.id", ondelete="SET NULL"))


class BackgroundJob(Base):
    __tablename__ = "background_jobs"
    __table_args__ = (Index("ix_background_jobs_status", "status", "id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16))  # queued | running | done | failed
    trainer_account_id: Mapped[int | None] = mapped_column(ForeignKey("trainer_accounts.id", ondelete="CASCADE"))
    ref_id: Mapped[int | None] = mapped_column(Integer)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONText)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
