"""The system status, the Game Data check and the version per role (issue #52)."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.conftest import PASSWORD, Api
from tests.test_password_lock import _write_lock_free


def test_status_per_role(owner: Api, app: Any) -> None:
    full = owner.get("/api/v1/system/status").json()
    assert {"database", "storage", "secret_key_source", "jobs", "failed_imports"} <= set(full)
    assert owner.post("/api/v1/users", {"username": "gebruiker", "password": PASSWORD}).status_code == 201
    with TestClient(app) as other_client:
        user = Api(other_client)
        assert user.login("gebruiker").status_code == 200
        own = user.get("/api/v1/system/status").json()
        assert set(own) == {"failed_imports", "last_successful_sync", "game_data"}
        assert user.post("/api/v1/gamedata/check").status_code == 403
        assert user.get("/api/v1/system/version").status_code == 200


def test_version_needs_a_login(client: TestClient, owner: Api) -> None:
    anonymous = TestClient(client.app)
    assert anonymous.get("/api/v1/system/version").status_code == 401
    assert owner.get("/api/v1/system/version").status_code == 200


def test_the_check_asks_outside_without_the_write_lock(
    owner: Api, container: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The requests to the sources run outside any transaction; only the result is written,
    afterwards, so the page can keep showing it (issues #52 and #28)."""
    database = container.settings.data_dir / "oak.db"
    seen: list[bool] = []

    def etags(_settings: Any) -> dict[str, str]:
        seen.append(_write_lock_free(database))
        return {"pokeminers": "a", "pvpoke": "b"}

    monkeypatch.setattr("app.gamedata.store.remote_etags", etags)
    assert owner.get("/api/v1/gamedata/check").status_code in (404, 405), "no GET that writes"
    response = owner.post("/api/v1/gamedata/check")
    assert response.status_code == 200 and response.json()["available"] is True
    assert seen == [True]
    assert owner.get("/api/v1/gamedata/status").json()["remote_check"]["available"] is True
