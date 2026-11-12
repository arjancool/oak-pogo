"""Changing the password: a limit on wrong current passwords, an audit entry for each, and a new
session afterwards (issues #41 and #42)."""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api.v1 import auth
from app.auth import passwords
from app.auth.sessions import CSRF_COOKIE, SESSION_COOKIE
from app.models import AuditLog
from tests.conftest import PASSWORD, Api
from tests.test_password_lock import _write_lock_free

NEW = "een heel nieuw wachtwoord"


def _change(owner: Api, current: str, new: str = NEW) -> Any:
    return owner.post("/api/v1/auth/change-password", {"current_password": current, "new_password": new})


def _failed_entries(container: Any) -> int:
    with container.db.read() as session:
        return (
            session.scalar(
                select(func.count()).select_from(AuditLog).where(AuditLog.action == "password_change_failed")
            )
            or 0
        )


def test_the_old_session_ends_and_a_new_one_works(owner: Api, app: Any) -> None:
    old_session = owner.client.cookies.get(SESSION_COOKIE)
    old_csrf = owner.client.cookies.get(CSRF_COOKIE)
    elsewhere = TestClient(app)
    other = Api(elsewhere)
    assert other.login("eigenaar").status_code == 200

    assert _change(owner, PASSWORD).status_code == 204
    new_session = owner.client.cookies.get(SESSION_COOKIE)
    new_csrf = owner.client.cookies.get(CSRF_COOKIE)
    assert new_session and new_session != old_session
    assert new_csrf and new_csrf != old_csrf

    assert owner.get("/api/v1/auth/me").status_code == 200, "the new session works"
    stolen = TestClient(app)
    stolen.cookies.set(SESSION_COOKIE, old_session or "")
    assert stolen.get("/api/v1/auth/me").status_code == 401, "a copy of the old cookie no longer works"
    assert elsewhere.get("/api/v1/auth/me").status_code == 401, "other sessions end too"

    owner.csrf = new_csrf
    assert owner.post("/api/v1/accounts", {"nickname": "Na de wijziging"}).status_code == 201


def test_wrong_current_passwords_are_logged_and_limited(owner: Api, container: Any) -> None:
    attempts = container.password_checks_by_user.limit
    for number in range(attempts):
        response = _change(owner, "verkeerd wachtwoord")
        assert response.status_code == 401, number
    assert _failed_entries(container) == attempts
    blocked = _change(owner, PASSWORD)
    assert blocked.status_code == 429 and "Retry-After" in blocked.headers
    assert blocked.json()["error"]["data"]["context"] == "change_password"
    assert _failed_entries(container) == attempts, "a refused attempt is not checked at all"


def test_a_successful_change_does_not_count(owner: Api, container: Any) -> None:
    attempts = container.password_checks_by_user.limit
    for _ in range(attempts - 1):
        assert _change(owner, "verkeerd wachtwoord").status_code == 401
    assert _change(owner, PASSWORD).status_code == 204
    owner.csrf = owner.client.cookies.get(CSRF_COOKIE)
    assert container.password_checks_by_user.blocked("user:1") is None


def test_an_invalid_new_password_costs_no_check(owner: Api, container: Any) -> None:
    response = _change(owner, PASSWORD, new="kort")
    assert response.status_code == 422
    assert len(container.password_checks_by_user) == 0


def test_the_check_runs_without_the_write_lock(owner: Api, container: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    database = container.settings.data_dir / "oak.db"
    seen: list[bool] = []
    original = auth.verify_password

    def watching(stored: str | None, password: str) -> bool:
        seen.append(_write_lock_free(database))
        return original(stored, password)

    monkeypatch.setattr(auth, "verify_password", watching)
    assert _change(owner, PASSWORD).status_code == 204
    assert seen == [True]


def test_argon2_runs_a_limited_number_at_a_time(monkeypatch: pytest.MonkeyPatch) -> None:
    running = 0
    highest = 0
    lock = threading.Lock()

    class SlowHasher:
        def verify(self, _stored: str, _password: str) -> bool:
            nonlocal running, highest
            with lock:
                running += 1
                highest = max(highest, running)
            time.sleep(0.05)
            with lock:
                running -= 1
            return True

    monkeypatch.setattr(passwords, "_hasher", SlowHasher())
    threads = [threading.Thread(target=passwords.verify_password, args=("hash", "pw")) for _ in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert highest == passwords.ARGON2_SLOTS
