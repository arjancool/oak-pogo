"""Authentication, sessions, CSRF and account isolation (spec §21)."""

from __future__ import annotations

import threading
import time
from datetime import timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.passwords import hash_password
from app.models import AuditLog, User, UserSession
from tests.conftest import PASSWORD, Api


def test_setup_once_and_status(api: Api) -> None:
    assert api.get("/api/v1/auth/status").json()["setup_required"] is True
    api.setup()
    status = api.get("/api/v1/auth/status").json()
    assert status["authenticated"] and status["user"]["role"] == "owner" and not status["setup_required"]
    second = api.client.post("/api/v1/auth/setup", json={"username": "nog1", "password": PASSWORD})
    assert second.status_code == 409


def test_cookie_flags(api: Api) -> None:
    response = api.client.post("/api/v1/auth/setup", json={"username": "eigenaar", "password": PASSWORD})
    cookies = response.headers.get_list("set-cookie")
    session_cookie = next(c for c in cookies if c.startswith("oak_session="))
    assert "HttpOnly" in session_cookie and "SameSite=lax" in session_cookie
    csrf_cookie = next(c for c in cookies if c.startswith("oak_csrf="))
    assert "HttpOnly" not in csrf_cookie


def test_password_policy(api: Api) -> None:
    response = api.client.post("/api/v1/auth/setup", json={"username": "eigenaar", "password": "kort"})
    assert response.status_code == 422


def test_login_logout_and_change_password(owner: Api) -> None:
    assert owner.post("/api/v1/auth/logout").status_code == 204
    assert owner.get("/api/v1/auth/me").status_code == 401
    assert owner.login("eigenaar", "fout wachtwoord!").status_code == 401
    assert owner.login("EIGENAAR").status_code == 200  # usernames are case-insensitive
    changed = owner.post(
        "/api/v1/auth/change-password",
        {"current_password": PASSWORD, "new_password": "een heel nieuw wachtwoord"},
    )
    assert changed.status_code == 204
    owner.post("/api/v1/auth/logout")
    assert owner.login("eigenaar").status_code == 401
    assert owner.login("eigenaar", "een heel nieuw wachtwoord").status_code == 200


def test_login_throttling(owner: Api, container: Any) -> None:
    owner.post("/api/v1/auth/logout")
    for _ in range(container.settings.login_max_attempts):
        assert owner.login("eigenaar", "verkeerd wachtwoord").status_code == 401
    blocked = owner.login("eigenaar")
    assert blocked.status_code == 429 and "Retry-After" in blocked.headers


def test_csrf_required_for_changes(owner: Api) -> None:
    response = owner.client.post("/api/v1/accounts", json={"nickname": "x"})
    assert response.status_code == 403 and response.json()["error"]["code"] == "CSRF_FAILED"
    response = owner.client.post("/api/v1/accounts", json={"nickname": "x"}, headers={"x-csrf-token": "fout"})
    assert response.status_code == 403
    assert owner.post("/api/v1/accounts", {"nickname": "x"}).status_code == 201


def test_session_idle_expiry(owner: Api, container: Any) -> None:
    from app.models import UserSession

    with container.db.transaction() as session:
        for record in session.query(UserSession):
            record.last_seen_at = record.last_seen_at - timedelta(hours=container.settings.session_idle_hours + 1)
    assert owner.get("/api/v1/auth/me").status_code == 401


def test_registration_closed_by_default(api: Api) -> None:
    api.setup()
    response = api.client.post("/api/v1/auth/register", json={"username": "nieuw", "password": PASSWORD})
    assert response.status_code == 403


def test_user_isolation(app: Any, owner: Api, container: Any, gamedata: Any, export: dict[str, Any]) -> None:
    account_a = owner.account("A")
    owner.upload(account_a, export)
    container.runner.drain()
    pokemon_id = owner.get("/api/v1/pokemon", account_id=account_a, page_size=1).json()["items"][0]["id"]
    import_id = owner.get("/api/v1/imports", account_id=account_a).json()["items"][0]["id"]
    assert owner.post("/api/v1/users", {"username": "gebruikerb", "password": PASSWORD}).status_code == 201

    with TestClient(app) as other_client:
        b = Api(other_client)
        assert b.login("gebruikerb").status_code == 200
        assert b.get("/api/v1/accounts").json() == []
        for path, params in (
            (f"/api/v1/accounts/{account_a}", {}),
            ("/api/v1/pokemon", {"account_id": account_a}),
            (f"/api/v1/pokemon/{pokemon_id}", {}),
            (f"/api/v1/pokemon/{pokemon_id}/analysis", {}),
            (f"/api/v1/imports/{import_id}", {}),
            ("/api/v1/imports", {"account_id": account_a}),
            ("/api/v1/sync/status", {"account_id": account_a}),
            ("/api/v1/cleanup/recommendations", {"account_id": account_a}),
            ("/api/v1/dashboard", {"account_id": account_a}),
            ("/api/v1/inventory/items", {"account_id": account_a}),
            ("/api/v1/export/metadata", {"account_id": account_a}),
        ):
            assert b.get(path, **params).status_code == 404, path
        assert b.patch(f"/api/v1/pokemon/{pokemon_id}/metadata", {"protected": True}).status_code == 404
        assert (
            b.post(
                "/api/v1/pokemon/bulk",
                {"account_id": account_a, "ids": [pokemon_id], "action": "protect"},
            ).status_code
            == 404
        )
        assert b.post(f"/api/v1/accounts/{account_a}/webhook").status_code == 404
        own = b.account("B")
        bad = b.post("/api/v1/pokemon/bulk", {"account_id": own, "ids": [pokemon_id], "action": "protect"})
        assert bad.status_code == 422
        assert b.get("/api/v1/users").status_code == 403
        assert b.post("/api/v1/gamedata/update").status_code == 403


def test_account_deletion_requires_confirmation(owner: Api) -> None:
    account = owner.account("Weg")
    assert owner.delete(f"/api/v1/accounts/{account}", {"confirm_nickname": "weg"}).status_code == 422
    assert owner.delete(f"/api/v1/accounts/{account}", {"confirm_nickname": "Weg"}).status_code == 204
    assert owner.get(f"/api/v1/accounts/{account}").status_code == 404


def test_account_deletion_removes_stored_exports(
    owner: Api, container: Any, gamedata: Any, export: dict[str, Any]
) -> None:
    imports_dir = container.settings.imports_dir
    unrelated = imports_dir / "unrelated.json.gz"
    unrelated.write_bytes(b"")
    account = owner.account("Weg")
    assert owner.upload(account, export).status_code == 202
    container.runner.drain()
    stored = {p.name for p in imports_dir.glob("*.json.gz")} - {unrelated.name}
    assert len(stored) == 1

    assert owner.delete(f"/api/v1/accounts/{account}", {"confirm_nickname": "Weg"}).status_code == 204
    assert {p.name for p in imports_dir.glob("*.json.gz")} == {unrelated.name}


def test_security_headers(owner: Api) -> None:
    response = owner.get("/api/v1/auth/me")
    for header in (
        "Content-Security-Policy",
        "X-Content-Type-Options",
        "Referrer-Policy",
        "X-Frame-Options",
    ):
        assert header in response.headers
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["Cache-Control"] == "no-store"


def test_failed_login_is_audited_once_without_secrets(owner: Api, container: Any) -> None:
    assert owner.login("eigenaar", "een verkeerd wachtwoord").status_code == 401
    with container.db.read() as session:
        rows = session.scalars(select(AuditLog).where(AuditLog.action == "login_failed")).all()
        assert len(rows) == 1
        stored = f"{rows[0].target} {rows[0].details}"
    assert "verkeerd" not in stored and PASSWORD not in stored


def test_registration_waits_for_the_owner(api: Api, container: Any) -> None:
    container.settings.allow_registration = True
    early = api.client.post("/api/v1/auth/register", json={"username": "vroeg", "password": PASSWORD})
    assert early.status_code == 409 and early.json()["error"]["code"] == "SETUP_REQUIRED"
    assert api.client.get("/api/v1/auth/status").json()["setup_required"] is True
    api.setup()
    assert api.client.get("/api/v1/auth/status").json()["setup_required"] is False


def test_setup_recovers_an_installation_without_owner(api: Api, container: Any) -> None:
    # An installation where a user registered before the owner existed (before audit A09).
    now = container.clock.now()
    with container.db.transaction() as session:
        session.add(
            User(
                username="vroeg",
                password_hash=hash_password(PASSWORD),
                role="user",
                status="active",
                preferences={},
                created_at=now,
                password_changed_at=now,
            )
        )
    assert api.client.get("/api/v1/auth/status").json()["setup_required"] is True
    owner = api.setup()
    assert owner["user"]["role"] == "owner"


def test_get_requests_touch_and_expire_sessions(owner: Api, container: Any) -> None:
    now = container.clock.now()
    with container.db.transaction() as session:
        session.scalars(select(UserSession)).one().last_seen_at = now - timedelta(minutes=6)
    assert owner.get("/api/v1/auth/me").status_code == 200
    with container.db.read() as session:
        assert session.scalars(select(UserSession)).one().last_seen_at >= now - timedelta(seconds=5)
        idle = timedelta(hours=container.settings.session_idle_hours + 1)
    with container.db.transaction() as session:
        session.scalars(select(UserSession)).one().last_seen_at = now - idle
    assert owner.get("/api/v1/auth/me").status_code == 401
    with container.db.read() as session:
        assert session.scalars(select(UserSession)).one().revoked_at is not None


def test_get_during_a_concurrent_write_succeeds_and_keeps_both_writes(owner: Api, container: Any) -> None:
    # The full path of audit A10: a GET that must touch its session while another writer holds
    # the lock. The touch waits for the writer instead of failing inside the read snapshot.
    now = container.clock.now()
    with container.db.transaction() as session:
        session.scalars(select(UserSession)).one().last_seen_at = now - timedelta(minutes=6)
    started = threading.Event()

    def writer() -> None:
        with container.db.transaction() as session:
            user = session.scalars(select(User)).one()
            started.set()
            time.sleep(0.3)
            user.preferences = {"theme": "dark"}

    thread = threading.Thread(target=writer)
    thread.start()
    assert started.wait(5)
    response = owner.get("/api/v1/auth/me")
    thread.join(5)
    assert response.status_code == 200, response.text
    with container.db.read() as session:
        assert session.scalars(select(User)).one().preferences == {"theme": "dark"}
        assert session.scalars(select(UserSession)).one().last_seen_at >= now - timedelta(seconds=5)


def test_owner_resets_a_forgotten_password(app: Any, owner: Api, container: Any) -> None:
    created = owner.post("/api/v1/users", {"username": "vergeetachtig", "password": PASSWORD})
    assert created.status_code == 201
    user_id = created.json()["id"]
    new_password = "een heel nieuw wachtwoord"

    with TestClient(app) as other_client:
        user = Api(other_client)
        assert user.login("vergeetachtig").status_code == 200
        assert user.get("/api/v1/auth/me").status_code == 200
        # A user cannot reset passwords, not even their own, through the owner's route.
        assert user.patch(f"/api/v1/users/{user_id}", {"password": new_password}).status_code == 403

        assert owner.patch(f"/api/v1/users/{user_id}", {"password": "kort"}).status_code == 422
        reset = owner.patch(f"/api/v1/users/{user_id}", {"password": new_password})
        assert reset.status_code == 200, reset.text
        # The reset ends every session of that user.
        assert user.get("/api/v1/auth/me").status_code == 401
        assert user.login("vergeetachtig").status_code == 401
        assert user.login("vergeetachtig", new_password).status_code == 200

    with container.db.read() as session:
        row = session.scalars(select(AuditLog).where(AuditLog.action == "user_updated")).all()[-1]
        assert row.details and row.details.get("password_reset") is True
        assert new_password not in f"{row.target} {row.details}"


def test_owner_changes_own_password_only_with_the_current_one(owner: Api) -> None:
    own_id = owner.get("/api/v1/auth/me").json()["id"]
    response = owner.patch(f"/api/v1/users/{own_id}", {"password": "een heel nieuw wachtwoord"})
    assert response.status_code == 422
    assert owner.login("eigenaar").status_code == 200


def test_language_is_saved_with_the_user(owner: Api) -> None:
    response = owner.put("/api/v1/auth/me/preferences", {"preferences": {"language": "en"}})
    assert response.status_code == 200, response.text
    assert response.json()["preferences"]["language"] == "en"
    assert owner.get("/api/v1/auth/status").json()["user"]["preferences"]["language"] == "en"
    for wrong in ("english", "EN", 3, "e"):
        response = owner.put("/api/v1/auth/me/preferences", {"preferences": {"language": wrong}})
        assert response.status_code == 422, wrong
    assert owner.get("/api/v1/auth/me").json()["preferences"]["language"] == "en"
