"""Small improvements from the audit of 2 November (issue #55)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import Api


def test_an_error_500_has_the_security_headers(settings: Any) -> None:
    app = create_app(settings)

    def boom() -> None:
        raise RuntimeError("synthetic failure")

    app.add_api_route("/api/v1/test-boom", boom)
    # Before the catch-all route of the frontend.
    app.router.routes.insert(0, app.router.routes.pop())

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/test-boom")
    assert response.status_code == 500
    for header in ("x-content-type-options", "x-frame-options", "content-security-policy", "cache-control"):
        assert header in response.headers, header
    assert "synthetic failure" not in response.text


def test_logout_always_clears_the_cookies(owner: Api, container: Any, app: Any) -> None:
    from sqlalchemy import update

    from app.auth.sessions import CSRF_COOKIE, SESSION_COOKIE
    from app.models import UserSession

    with container.db.transaction() as session:
        session.execute(update(UserSession).values(expires_at=container.clock.now() - timedelta(days=1)))
    response = owner.client.post("/api/v1/auth/logout")
    assert response.status_code == 204
    cookies = response.headers.get_list("set-cookie")
    assert any(c.startswith(f"{SESSION_COOKIE}=") and "Max-Age=0" in c for c in cookies)
    assert any(c.startswith(f"{CSRF_COOKIE}=") and "Max-Age=0" in c for c in cookies)


def test_logout_of_a_live_session_needs_the_csrf_token(owner: Api) -> None:
    assert owner.client.post("/api/v1/auth/logout").status_code == 403
    assert owner.get("/api/v1/auth/me").status_code == 200, "still logged in"
    assert owner.post("/api/v1/auth/logout").status_code == 204


def test_login_ends_the_session_the_browser_still_had(owner: Api, app: Any) -> None:
    from app.auth.sessions import SESSION_COOKIE

    old = owner.client.cookies.get(SESSION_COOKIE)
    assert owner.login("eigenaar").status_code == 200
    stale = TestClient(app)
    stale.cookies.set(SESSION_COOKIE, old or "")
    assert stale.get("/api/v1/auth/me").status_code == 401


def test_backups_odd_names_and_deletion(owner: Api, container: Any) -> None:
    from sqlalchemy import select

    from app.models import AuditLog

    for name in ("oak-..db", "oak-a%00b.db", "oak-x.db.bak", "other.db"):
        assert owner.get(f"/api/v1/backups/{name}").status_code == 404, name
    created = owner.post("/api/v1/backups").json()["name"]
    assert owner.delete(f"/api/v1/backups/{created}").status_code == 204
    assert owner.delete(f"/api/v1/backups/{created}").status_code == 404
    with container.db.read() as session:
        actions = list(session.scalars(select(AuditLog.action).where(AuditLog.target == created)))
    assert "backup_deleted" in actions


def test_only_https_cup_links_are_kept() -> None:
    from app.gamedata.cups import _https_link

    assert _https_link("https://pvpoke.com/battle/") == "https://pvpoke.com/battle/"
    for bad in ("javascript:alert(1)", "http://pvpoke.com", None, 5):
        assert _https_link(bad) is None


def test_a_game_data_file_name_is_checked(container: Any) -> None:
    with pytest.raises(ValueError, match="Ongeldige bestandsnaam"):
        container.gamedata._path("../oak.db")
    assert container.gamedata._path("oak-gamedata-12.json.gz").name == "oak-gamedata-12.json.gz"


def test_an_import_of_a_disabled_user_is_not_processed(owner: Api, container: Any, export: dict[str, Any]) -> None:
    from sqlalchemy import update

    from app.models import User

    job_id = owner.upload(owner.account(), export).json()["id"]
    with container.db.transaction() as session:
        session.execute(update(User).values(status="disabled"))
    container.runner.drain()
    with container.db.transaction() as session:
        session.execute(update(User).values(status="active"))
    job = owner.get(f"/api/v1/imports/{job_id}").json()
    assert job["status"] == "failed" and job["error_code"] == "USER_DISABLED"
