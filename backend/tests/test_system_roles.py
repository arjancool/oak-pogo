"""The system status, the Game Data check and the version per role (issue #52)."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.conftest import PASSWORD, Api


def test_status_per_role(owner: Api, app: Any) -> None:
    full = owner.get("/api/v1/system/status").json()
    assert {"database", "storage", "secret_key_source", "jobs", "failed_imports"} <= set(full)
    assert owner.post("/api/v1/users", {"username": "gebruiker", "password": PASSWORD}).status_code == 201
    with TestClient(app) as other_client:
        user = Api(other_client)
        assert user.login("gebruiker").status_code == 200
        own = user.get("/api/v1/system/status").json()
        assert set(own) == {"failed_imports", "last_successful_sync", "game_data"}
        assert user.get("/api/v1/gamedata/check").status_code == 403
        assert user.get("/api/v1/system/version").status_code == 200


def test_version_needs_a_login(client: TestClient, owner: Api) -> None:
    anonymous = TestClient(client.app)
    assert anonymous.get("/api/v1/system/version").status_code == 401
    assert owner.get("/api/v1/system/version").status_code == 200


def test_the_check_reads_without_a_write_transaction(
    owner: Api, container: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.gamedata.store.remote_etags", lambda _settings: {"pokeminers": "a", "pvpoke": "b"})

    def no_writes() -> Any:
        raise AssertionError("the check only reads")

    monkeypatch.setattr(container.db, "transaction", no_writes)
    response = owner.get("/api/v1/gamedata/check")
    assert response.status_code == 200 and response.json()["available"] is True
