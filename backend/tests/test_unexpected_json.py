"""Valid but unexpected JSON is a rejected import or a failed version, never an error 500
(issue #47)."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select

from app.gamedata import store as gamedata_store
from app.models import GameDataVersion
from app.services import events as event_service
from tests.conftest import Api
from tests.test_server_texts_sync import _check, _server


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ('{"pokemons": [{"id": "1", "nickname": "\\ud800"}]}', "ENCODING_INVALID"),
        ('{"pokemons": [{"id": "1", "\\udfff": 1}]}', "ENCODING_INVALID"),
        ('{"pokemons": [{"id": "1", "cp": NaN}]}', "NUMBER_INVALID"),
        ('{"pokemons": [{"id": "1", "cp": -Infinity}]}', "NUMBER_INVALID"),
        ('{"pokemons": [{"id": "1", "heightM": 1e999}]}', "NUMBER_INVALID"),
        ('{"pokemons": [], "x": ' + "[" * 5000 + "]" * 5000 + "}", "STRUCTURE_TOO_LARGE"),
        ('{"pokemons": [], "x": ' + "9" * 5000 + "}", "STRUCTURE_TOO_LARGE"),
    ],
)
def test_unexpected_json_is_a_rejected_import(owner: Api, container: Any, body: str, code: str) -> None:
    response = owner.post(
        "/api/v1/imports/upload",
        files={"file": ("PGSStats.json", body.encode(), "application/json")},
        data={"account_id": str(owner.account())},
    )
    assert response.status_code == 202, response.text
    job = response.json()
    assert job["status"] == "rejected" and job["error_code"] == code
    _check("imports", {"code": job["error_code"], "data": job["error_data"]}, _server())
    assert list(container.settings.imports_dir.iterdir()) == [], "no file stays behind"


def test_valid_surrogate_pairs_and_ordinary_text_still_work(owner: Api, export: dict[str, Any]) -> None:
    export["pokemons"][0]["nickname"] = "Pika😀é"
    assert owner.upload(owner.account(), export).json()["status"] == "queued"


def test_an_unexpected_game_data_structure_is_a_failed_version(
    owner: Api, container: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    def odd(*_args: Any, **_kwargs: Any) -> Any:
        raise AttributeError("'list' object has no attribute 'get'")

    monkeypatch.setattr(gamedata_store, "build_dataset", odd)
    result = container.gamedata.update_from_upload({"pokeminers": b"[]"})
    assert result.status == "failed"
    with container.db.read() as session:
        failed = session.scalars(select(GameDataVersion).where(GameDataVersion.status == "failed")).all()
    assert len(failed) == 1 and "attribute" in (failed[0].error or "")


def test_an_unexpected_event_calendar_is_a_failed_update(container: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    def odd(*_args: Any, **_kwargs: Any) -> Any:
        raise AttributeError("unexpected")

    monkeypatch.setattr(event_service, "parse_events", odd)
    result = event_service.update_events(container.settings, container.db, container.clock.now(), content=b"[1]")
    assert result["status"] == "failed" and result["error"]
