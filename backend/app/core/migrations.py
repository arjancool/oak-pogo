"""Running Alembic migrations at startup, with a backup before any schema change (spec §22.5)."""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, Engine

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
    with engine.connect() as connection:
        run_without_foreign_keys(connection, lambda: command.upgrade(cfg, "head"), cfg)
    log.info("database migrated", extra={"from": current, "to": head})


def run_without_foreign_keys(connection: Connection, upgrade: Callable[[], None], cfg: Config) -> None:
    """Run migrations with foreign keys off, and check every one of them before committing.

    Rebuilding a table in batch mode drops the old table. With foreign keys on, SQLite would then
    delete or empty every row that points to it, such as all Pokémon of a trainer account. SQLite
    only switches foreign keys outside a transaction, so this happens on the driver connection
    before the migration transaction starts, and they are switched on again in any case."""
    raw = connection.connection.driver_connection
    if raw is None:  # pragma: no cover - a pooled SQLite connection always has one
        msg = "no driver connection for the migration"
        raise RuntimeError(msg)
    raw.execute("PRAGMA foreign_keys=OFF")
    try:
        with connection.begin():
            cfg.attributes["connection"] = connection
            upgrade()
            broken = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
            if broken:
                msg = f"foreign keys broken after the migration: {len(broken)} rows"
                raise RuntimeError(msg)
    finally:
        raw.execute("PRAGMA foreign_keys=ON")
