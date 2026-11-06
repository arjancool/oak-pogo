"""Over https the session and CSRF cookies carry the __Host- prefix (issue #55)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.auth.sessions import CSRF_COOKIE, SESSION_COOKIE, cookie_names
from app.core.config import Settings
from app.main import create_app
from tests.conftest import PASSWORD


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
