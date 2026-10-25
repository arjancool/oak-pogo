"""SQLite engine, sessions and transaction control (ADR-0014).

Every connection enables foreign keys, WAL journaling and a busy timeout. pysqlite's implicit
transaction handling is switched off so SQLAlchemy decides when a transaction starts. Writers
take the database write lock up front with ``BEGIN IMMEDIATE`` instead of failing halfway
through on a lock upgrade.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session, sessionmaker

BUSY_TIMEOUT_MS = 30_000
BEGIN_OPTION = "oak_begin"


def create_sqlite_engine(url: str) -> Engine:
    engine = create_engine(
        url,
        connect_args={"check_same_thread": False, "timeout": BUSY_TIMEOUT_MS / 1000},
        pool_pre_ping=True,
    )

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection: Any, _record: Any) -> None:
        dbapi_connection.isolation_level = None
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
        cursor.close()

    @event.listens_for(engine, "begin")
    def _on_begin(conn: Connection) -> None:
        mode = conn.get_execution_options().get(BEGIN_OPTION, "DEFERRED")
        conn.exec_driver_sql(f"BEGIN {mode}")

    return engine


class Database:
    """``transaction()`` is for work that writes and starts with ``BEGIN IMMEDIATE``: in WAL mode a
    deferred transaction that reads first and writes later fails at once with "database is
    locked" when another writer committed in between, and no busy timeout helps there.
    ``read()`` is for read-only work and never blocks writers."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self._deferred = sessionmaker(bind=engine, expire_on_commit=False)
        self._immediate = sessionmaker(
            bind=engine.execution_options(**{BEGIN_OPTION: "IMMEDIATE"}),
            expire_on_commit=False,
        )

    def session(self, *, write: bool = True) -> Session:
        return self._immediate() if write else self._deferred()

    @contextmanager
    def transaction(self) -> Iterator[Session]:
        with self._immediate() as session, session.begin():
            yield session

    @contextmanager
    def read(self) -> Iterator[Session]:
        with self._deferred() as session, session.begin():
            yield session

    # Kept as an explicit name where the lock matters most (imports, projections).
    immediate_transaction = transaction
