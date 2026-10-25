"""Shared fixtures: an isolated data directory, the app, a small Game Data set and the
synthetic PGSharp sample export."""

from __future__ import annotations

import copy
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.gamedata.fetch import Downloaded
from app.gamedata.validate import ValidationLimits
from app.main import create_app

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures"
SAMPLE_EXPORT = FIXTURES / "pgsharp" / "PGSStats.sample.json"
TEST_LIMITS = ValidationLimits(min_species=10, min_forms=20, min_moves=20, min_cpm_entries=80)
PASSWORD = "correct horse battery staple"


def gamedata_files() -> dict[str, bytes]:
    base = FIXTURES / "gamedata"
    return {
        "pokeminers": (base / "pokeminers-subset.json").read_bytes(),
        "pvpoke": (base / "pvpoke-subset.json").read_bytes(),
        "pvpoke-rankings-great": (base / "pvpoke-rankings-great-subset.json").read_bytes(),
        "pvpoke-rankings-ultra": (base / "pvpoke-rankings-ultra-subset.json").read_bytes(),
        "pvpoke-rankings-master": (base / "pvpoke-rankings-master-subset.json").read_bytes(),
    }


def downloads(files: dict[str, bytes] | None = None) -> dict[str, Downloaded]:
    return {
        sid: Downloaded(
            id=sid,
            url=f"test://{sid}",
            content=content,
            etag=f'"{sid}"',
            retrieved_at="2026-10-23T00:00:00+00:00",
        )
        for sid, content in (files or gamedata_files()).items()
    }


@pytest.fixture(scope="session")
def sample_export() -> dict[str, Any]:
    return json.loads(SAMPLE_EXPORT.read_text())


@pytest.fixture
def export(sample_export: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(sample_export)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        env="test",
        data_dir=tmp_path / "data",
        start_worker=False,
        log_level="WARNING",
        secret_key="test-secret-key-that-is-long-enough-123456",
        gamedata_auto_update=False,
        events_auto_update=False,
    )


@pytest.fixture
def app(settings: Settings) -> Any:
    return create_app(settings)


@pytest.fixture
def client(app: Any) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def container(client: TestClient, app: Any) -> Any:
    return app.state.container


@pytest.fixture
def gamedata(container: Any) -> Any:
    container.gamedata.limits = TEST_LIMITS
    result = container.gamedata.update_from_downloads(downloads(), origin="upload")
    assert result.status == "activated", result.message
    return container.gamedata.active()


class Api:
    """Small helper around the test client that keeps the CSRF header."""

    def __init__(self, client: TestClient) -> None:
        self.client = client
        self.csrf: str | None = None

    @property
    def headers(self) -> dict[str, str]:
        return {"x-csrf-token": self.csrf} if self.csrf else {}

    def setup(self, username: str = "eigenaar") -> dict[str, Any]:
        response = self.client.post("/api/v1/auth/setup", json={"username": username, "password": PASSWORD})
        assert response.status_code == 201, response.text
        self.csrf = response.json()["csrf_token"]
        return response.json()

    def login(self, username: str, password: str = PASSWORD) -> Any:
        response = self.client.post("/api/v1/auth/login", json={"username": username, "password": password})
        if response.status_code == 200:
            self.csrf = response.json()["csrf_token"]
        return response

    def get(self, path: str, **params: Any) -> Any:
        return self.client.get(path, params=params)

    def post(self, path: str, json: Any = None, **kwargs: Any) -> Any:
        return self.client.post(path, json=json, headers=self.headers, **kwargs)

    def put(self, path: str, json: Any = None, **kwargs: Any) -> Any:
        return self.client.put(path, json=json, headers=self.headers, **kwargs)

    def patch(self, path: str, json: Any = None) -> Any:
        return self.client.patch(path, json=json, headers=self.headers)

    def delete(self, path: str, json: Any = None, **kwargs: Any) -> Any:
        return self.client.request("DELETE", path, json=json, headers=self.headers, **kwargs)

    def account(self, nickname: str = "Testaccount") -> int:
        response = self.post("/api/v1/accounts", {"nickname": nickname})
        assert response.status_code == 201, response.text
        return int(response.json()["id"])

    def webhook_path(self, account_id: int) -> str:
        response = self.post(f"/api/v1/accounts/{account_id}/webhook")
        assert response.status_code == 201, response.text
        return "/" + response.json()["url"].split("/", 3)[3]

    def upload(self, account_id: int, data: Any) -> Any:
        body = json.dumps(data).encode()
        return self.post(
            "/api/v1/imports/upload",
            files={"file": ("PGSStats.json", body, "application/json")},
            data={"account_id": str(account_id)},
        )


@pytest.fixture
def api(client: TestClient) -> Api:
    return Api(client)


@pytest.fixture
def owner(api: Api) -> Api:
    api.setup()
    return api
