"""Over https the session and CSRF cookies carry the __Host- prefix (issue #55)."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from app.auth.sessions import CSRF_COOKIE, SESSION_COOKIE, cookie_names
from app.core.config import Settings
from app.main import create_app
from tests.conftest import PASSWORD, Api


def test_cookie_names() -> None:
    assert cookie_names(False) == (SESSION_COOKIE, CSRF_COOKIE)
    assert cookie_names(True) == ("__Host-oak_session", "__Host-oak_csrf")


def test_https_uses_host_cookies_and_ignores_plain_ones(settings: Settings) -> None:
    settings.base_url = "https://oak.example"
    with TestClient(create_app(settings), base_url="https://testserver") as client:
        response = client.post("/api/v1/auth/setup", json={"username": "eigenaar", "password": PASSWORD})
        assert response.status_code == 201, response.text
        headers = response.headers.get_list("set-cookie")
        session_header = next(h for h in headers if h.startswith("__Host-oak_session="))
        assert "Secure" in session_header and "Path=/" in session_header and "Domain" not in session_header
        assert any(h.startswith("__Host-oak_csrf=") for h in headers)
        assert not any(h.startswith(f"{SESSION_COOKIE}=") for h in headers)
        assert client.get("/api/v1/auth/me").status_code == 200

        token = client.cookies.get("__Host-oak_session")
        assert token
        plain = TestClient(client.app, base_url="https://testserver")
        plain.cookies.set(SESSION_COOKIE, token)
        assert plain.get("/api/v1/auth/me").status_code == 401, "a cookie without the prefix does not count"

        csrf = client.cookies.get("__Host-oak_csrf") or ""
        logout = client.post("/api/v1/auth/logout", headers={"x-csrf-token": csrf})
        assert logout.status_code == 204
        cleared = logout.headers.get_list("set-cookie")
        for name in ("__Host-oak_session", "__Host-oak_csrf", SESSION_COOKIE, CSRF_COOKIE):
            assert any(h.startswith(f"{name}=") for h in cleared), name
        assert all("Secure" in h for h in cleared if h.startswith("__Host-"))


def test_http_keeps_the_plain_names(client: TestClient) -> None:
    response = client.post("/api/v1/auth/setup", json={"username": "eigenaar", "password": PASSWORD})
    names = {h.split("=", 1)[0] for h in response.headers.get_list("set-cookie")}
    assert names == {SESSION_COOKIE, CSRF_COOKIE}


def test_status_puts_a_stale_csrf_cookie_right(settings: Settings) -> None:
    """A browser with only a plain CSRF cookie from before the __Host- names sent that one, and
    every write was refused, logging out too. The status the interface asks for on every visit
    sets the right cookie again and clears the plain ones."""
    settings.base_url = "https://oak.example"
    with TestClient(create_app(settings), base_url="https://testserver") as client:
        assert client.post("/api/v1/auth/setup", json={"username": "eigenaar", "password": PASSWORD}).status_code == 201
        right = client.cookies.get("__Host-oak_csrf")
        client.cookies.delete("__Host-oak_csrf")
        client.cookies.set(CSRF_COOKIE, "oud-token")
        refused = client.post("/api/v1/accounts", json={"nickname": "Test"}, headers={"x-csrf-token": "oud-token"})
        assert refused.status_code == 403 and refused.json()["error"]["code"] == "CSRF_FAILED"

        status = client.get("/api/v1/auth/status")
        assert status.status_code == 200 and status.json()["csrf_token"] == right
        headers = status.headers.get_list("set-cookie")
        fresh = next(h for h in headers if h.startswith("__Host-oak_csrf="))
        assert f"__Host-oak_csrf={right};" in fresh and "Secure" in fresh and "Path=/" in fresh
        assert "HttpOnly" not in fresh, "the interface reads it"
        assert any(h.startswith(f"{CSRF_COOKIE}=") and "Max-Age=0" in h for h in headers), "the plain one is cleared"
        assert not any(h.startswith("__Host-oak_session=") for h in headers), "the session stays as it is"

        token = client.cookies.get("__Host-oak_csrf") or ""
        assert token == right
        created = client.post("/api/v1/accounts", json={"nickname": "Test"}, headers={"x-csrf-token": token})
        assert created.status_code == 201, created.text


def test_status_follows_a_changed_secret_key(api: Api, container: Any) -> None:
    """The session survives a new secret key, its CSRF token does not. The status gives the new
    token and cookie, so writing works again without logging in."""
    api.setup()
    old = api.csrf
    container.secret = "een-andere-geheime-sleutel-van-voldoende-lengte"
    assert api.post("/api/v1/accounts", {"nickname": "Test"}).status_code == 403
    status = api.get("/api/v1/auth/status").json()
    assert status["authenticated"] and status["csrf_token"] not in (None, old)
    assert api.client.cookies.get(CSRF_COOKIE) == status["csrf_token"]
    api.csrf = status["csrf_token"]
    assert api.post("/api/v1/accounts", {"nickname": "Test"}).status_code == 201


def test_status_without_a_session_sets_no_cookie(client: TestClient) -> None:
    status = client.get("/api/v1/auth/status")
    assert status.json()["csrf_token"] is None
    assert status.headers.get_list("set-cookie") == []
