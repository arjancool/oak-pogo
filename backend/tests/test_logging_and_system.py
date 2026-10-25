"""Logging redaction, health and system endpoints."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi.testclient import TestClient

from app.core.logging import JsonFormatter, RedactingFilter, configure_logging, redact
from app.main import create_app

TOKEN = "oakwh_AbCdEfGhIj_s3cr3t-T0k3n_value"


def test_redact_token_in_path_and_text() -> None:
    assert TOKEN not in redact(f"POST /api/v1/ingest/pgsharp/{TOKEN} 202")
    assert TOKEN not in redact(f"token {TOKEN} gezien")


def test_formatter_never_emits_token() -> None:
    record = logging.LogRecord("t", logging.INFO, __file__, 1, "request %s", (f"/api/v1/ingest/pgsharp/{TOKEN}",), None)
    RedactingFilter().filter(record)
    assert TOKEN not in JsonFormatter().format(record)


def test_webhook_request_log_is_redacted(owner: Any, caplog: Any) -> None:
    account = owner.account()
    path = owner.webhook_path(account)
    token = path.rsplit("/", 1)[1]
    with caplog.at_level(logging.INFO):
        owner.client.post(path, content=b"{}")
    joined = "\n".join(JsonFormatter().format(r) for r in caplog.records if RedactingFilter().filter(r))
    assert token not in joined


def test_uvicorn_access_log_stays_off() -> None:
    configure_logging("INFO")
    access = logging.getLogger("uvicorn.access")
    assert access.disabled and not access.propagate and not access.handlers
    assert logging.getLogger("uvicorn.error").propagate


def test_health_and_version(client: Any) -> None:
    assert client.get("/health/live").json() == {"status": "ok"}
    ready = client.get("/health/ready")
    assert ready.status_code == 200 and ready.json()["status"] == "ok"
    assert client.get("/api/v1/system/version").json()["version"] == "2.0.0"


def test_system_status_and_backup(owner: Any) -> None:
    status = owner.get("/api/v1/system/status").json()
    assert status["database"]["status"] == "ok" and status["secret_key_source"] == "environment"
    created = owner.post("/api/v1/backups")
    assert created.status_code == 201
    name = created.json()["name"]
    listing = owner.get("/api/v1/backups").json()
    assert any(b["name"] == name for b in listing)
    download = owner.get(f"/api/v1/backups/{name}")
    assert download.status_code == 200 and download.content[:15] == b"SQLite format 3"
    assert owner.get("/api/v1/backups/..%2Foak.db").status_code == 404


def test_sprite_setting_changes_csp(owner: Any) -> None:
    before = owner.get("/api/v1/settings").json()
    assert before["sprite_source"] == "none"
    response = owner.put("/api/v1/settings", {"sprite_source": "pokeapi"})
    assert response.status_code == 200
    csp = owner.get("/api/v1/settings").headers["Content-Security-Policy"]
    assert "https://raw.githubusercontent.com" in csp
    bad = owner.put("/api/v1/settings", {"sprite_source": "custom", "sprite_url_template": "http://x/{dex}"})
    assert bad.status_code == 422


def test_production_publishes_no_api_docs_or_schema(settings: Any) -> None:
    production = settings.model_copy(update={"env": "production"})
    with TestClient(create_app(production)) as client:
        for path in ("/api/docs", "/api/redoc", "/api/openapi.json"):
            assert client.get(path).status_code == 404, path


def test_openapi_lists_spec_endpoints(client: Any) -> None:
    paths = set(json.loads(client.get("/api/openapi.json").text)["paths"])
    for path in (
        "/api/v1/auth/login",
        "/api/v1/auth/logout",
        "/api/v1/auth/me",
        "/api/v1/auth/change-password",
        "/api/v1/accounts",
        "/api/v1/accounts/{account_id}",
        "/api/v1/ingest/pgsharp/{token}",
        "/api/v1/imports/upload",
        "/api/v1/imports",
        "/api/v1/imports/{import_id}",
        "/api/v1/imports/{import_id}/errors",
        "/api/v1/sync/status",
        "/api/v1/sync/history",
        "/api/v1/pokemon",
        "/api/v1/pokemon/{pokemon_id}",
        "/api/v1/pokemon/{pokemon_id}/analysis",
        "/api/v1/pokemon/{pokemon_id}/evolutions",
        "/api/v1/pokemon/{pokemon_id}/powerups",
        "/api/v1/pokemon/{pokemon_id}/metadata",
        "/api/v1/pokemon/compare",
        "/api/v1/cleanup/recommendations",
        "/api/v1/cleanup/duplicates",
        "/api/v1/cleanup/analyze",
        "/api/v1/cleanup/rules",
        "/api/v1/cleanup/action-list",
        "/api/v1/cleanup/export",
        "/api/v1/battles/leagues",
        "/api/v1/battles/pokemon/{pokemon_id}",
        "/api/v1/battles/team-builder",
        "/api/v1/battles/teams",
        "/api/v1/battles/raid-counters",
        "/api/v1/battles/rocket-counters",
        "/api/v1/battles/max-counters",
        "/api/v1/gamedata/status",
        "/api/v1/gamedata/update",
        "/api/v1/gamedata/sources",
        "/api/v1/system/version",
    ):
        assert path in paths, path
