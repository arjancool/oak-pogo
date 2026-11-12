"""Argon2 runs while no transaction holds the database write lock (issue #40)."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select

from app.api.v1 import auth
from app.models import User
from tests.conftest import PASSWORD, Api


def _write_lock_free(database: Path) -> bool:
    """Whether another writer gets the write lock right away."""
    connection = sqlite3.connect(database, timeout=0.05, isolation_level=None)
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("ROLLBACK")
        return True
    except sqlite3.OperationalError:
        return False
    finally:
        connection.close()


class LockWatch:
    def __init__(self, container: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        self.database = container.settings.data_dir / "oak.db"
        self.seen: list[tuple[str, bool]] = []
        self._monkeypatch = monkeypatch

    def watch(self, name: str) -> None:
        original = getattr(auth, name)

        def watching(*args: Any) -> Any:
            self.seen.append((name, _write_lock_free(self.database)))
            return original(*args)

        self._monkeypatch.setattr(auth, name, watching)


@pytest.fixture
def lock(container: Any, monkeypatch: pytest.MonkeyPatch) -> LockWatch:
    return LockWatch(container, monkeypatch)


def test_setup_hashes_without_the_write_lock(api: Api, lock: LockWatch) -> None:
    lock.watch("hash_password")
    api.setup()
    assert lock.seen == [("hash_password", True)]


def test_login_verifies_without_the_write_lock(owner: Api, lock: LockWatch) -> None:
    owner.post("/api/v1/auth/logout")
    lock.watch("verify_password")
    assert owner.login("eigenaar", "verkeerd wachtwoord").status_code == 401
    assert owner.login("eigenaar").status_code == 200
    assert lock.seen == [("verify_password", True), ("verify_password", True)]


def test_a_rehash_happens_without_the_write_lock(
    owner: Api, container: Any, lock: LockWatch, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner.post("/api/v1/auth/logout")
    with container.db.read() as session:
        before = session.scalars(select(User.password_hash).where(User.username == "eigenaar")).one()
    monkeypatch.setattr(auth, "needs_rehash", lambda _hash: True)
    lock.watch("hash_password")
    assert owner.login("eigenaar").status_code == 200
    assert lock.seen == [("hash_password", True)]
    with container.db.read() as session:
        after = session.scalars(select(User.password_hash).where(User.username == "eigenaar")).one()
    assert after != before
    assert owner.login("eigenaar").status_code == 200, "the new hash works"


def test_registration_hashes_without_the_write_lock(owner: Api, container: Any, lock: LockWatch) -> None:
    container.settings.allow_registration = True
    lock.watch("hash_password")
    response = owner.client.post("/api/v1/auth/register", json={"username": "nieuw", "password": PASSWORD})
    assert response.status_code == 201, response.text
    assert lock.seen == [("hash_password", True)]
    taken = owner.client.post("/api/v1/auth/register", json={"username": "nieuw", "password": PASSWORD})
    assert taken.status_code == 409
    assert len(lock.seen) == 1, "a taken username costs no hash"


def test_a_second_setup_costs_no_hash(owner: Api, lock: LockWatch) -> None:
    lock.watch("hash_password")
    again = owner.client.post("/api/v1/auth/setup", json={"username": "ander", "password": PASSWORD})
    assert again.status_code == 409
    assert lock.seen == []


@pytest.mark.parametrize("change", ["password", "status"])
def test_a_change_during_the_check_wins(
    owner: Api, container: Any, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    owner.post("/api/v1/auth/logout")
    original = auth.verify_password

    def changing(stored: str | None, password: str) -> bool:
        result = original(stored, password)
        # Another request changes the user while this one checks the password.
        with container.db.transaction() as session:
            user = session.scalars(select(User).where(User.username == "eigenaar")).one()
            if change == "password":
                user.password_hash = auth.hash_password("een heel ander wachtwoord")
            else:
                user.status = "disabled"
        return result

    monkeypatch.setattr(auth, "verify_password", changing)
    assert owner.login("eigenaar").status_code == 401
