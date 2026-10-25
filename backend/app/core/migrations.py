"""Running Alembic migrations at startup, with a backup before any schema change (spec §22.5)."""

from __future__ import annotations

import logging
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine

from app.core.config import Settings

log = logging.getLogger("oak.migrations")
BACKEND_DIR = Path(__file__).resolve().parents[2]


def alembic_config(settings: Settings) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    return cfg


def pending_revisions(engine: Engine, cfg: Config) -> tuple[str | None, str | None]:
    script = ScriptDirectory.from_config(cfg)
    head = script.get_current_head()
    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
    return current, head


def backup_database(settings: Settings, label: str) -> Path | None:
    source = settings.database_path
    if not source.exists() or source.stat().st_size == 0:
        return None
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = settings.backups_dir / f"oak-{label}-{stamp}.db"
    # closing(): a sqlite3 connection's own context manager ends the transaction, not the
    # connection (audit F10 of 25 October).
    with closing(sqlite3.connect(source)) as src, closing(sqlite3.connect(target)) as dst:
        src.backup(dst)
    return target


def migrate(settings: Settings, engine: Engine) -> None:
    cfg = alembic_config(settings)
    current, head = pending_revisions(engine, cfg)
    if current == head:
        return
    if current is not None:
        backup = backup_database(settings, f"pre-migration-{current}")
        log.info(
            "database backup before migration",
            extra={"backup": str(backup), "from": current, "to": head},
        )
    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "head")
    log.info("database migrated", extra={"from": current, "to": head})
