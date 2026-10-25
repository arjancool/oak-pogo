"""Game Data transform, validation, versioning and rollback (spec §6)."""

from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy import select

from app.gamedata.transform import build_dataset, norm_key
from app.gamedata.validate import DatasetInvalidError, validate_dataset
from app.jobs.tasks import schedule_gamedata_check
from app.models import BackgroundJob, GameDataVersion
from tests.conftest import TEST_LIMITS, downloads, gamedata_files


def _dataset() -> dict[str, Any]:
    files = gamedata_files()
    return build_dataset(
        json.loads(files["pokeminers"]),
        pvpoke=json.loads(files["pvpoke"]),
        rankings={"great": json.loads(files["pvpoke-rankings-great"])},
        sources=[],
        generated_at="x",
    )


def test_norm_key_matches_pgsharp_form_names() -> None:
    assert norm_key("SmolivNormal") == norm_key("SMOLIV_NORMAL")
    assert norm_key("RattataAlola") == norm_key("RATTATA_ALOLA")


def test_transform_contents() -> None:
    ds = _dataset()
    gyarados = ds["forms"]["130:GYARADOSNORMAL"]
    assert gyarados["types"] == ["water", "flying"]
    assert gyarados["pvpoke_id"] == "gyarados"
    assert "DRAGON_TAIL_FAST" in gyarados["elite_fast"]
    assert ds["forms"]["19:RATTATAALOLA"]["label"] == "Alola"
    assert ds["forms"]["150:"]["class"] == "legendary"
    assert ds["forms"]["151:"]["class"] == "mythical"
    assert ds["forms"]["793:"]["class"] == "ultra_beast"
    assert ds["type_chart"]["fire"]["grass"] == 1.6
    assert ds["type_chart"]["ghost"]["normal"] < 0.5
    assert {lg["id"]: lg["max_cp"] for lg in ds["leagues"]}["great"] == 1500
    cpm = dict(ds["mechanics"]["cpm"])
    assert cpm[1.0] == pytest.approx(0.094) and cpm[40.0] == pytest.approx(0.7903, abs=1e-4)
    assert ds["mechanics"]["max_normal_level"] == 50
    assert ds["moves"]["WATERFALL_FAST"]["pvp"]["turns"] >= 1


def test_validation_blocks_broken_datasets() -> None:
    ds = _dataset()
    assert validate_dataset(ds, TEST_LIMITS) is not None
    broken = dict(ds, mechanics={**ds["mechanics"], "cpm": ds["mechanics"]["cpm"][:10]})
    with pytest.raises(DatasetInvalidError):
        validate_dataset(broken, TEST_LIMITS)
    with pytest.raises(DatasetInvalidError):
        validate_dataset(ds)  # the subset is far below the production limits
    with pytest.raises(DatasetInvalidError):
        validate_dataset(dict(ds, schema_version=99), TEST_LIMITS)


def test_versions_unchanged_failed_and_rollback(owner: Any, container: Any) -> None:
    store = container.gamedata
    store.limits = TEST_LIMITS
    first = store.update_from_downloads(downloads(), origin="upload")
    assert first.status == "activated"
    assert store.update_from_downloads(downloads(), origin="download").status == "unchanged"
    files = gamedata_files()
    files["pokeminers"] = b"[]"
    failed = store.update_from_downloads(downloads(files), origin="upload")
    assert failed.status == "failed"
    assert store.active().version_id == first.version_id  # the working version stays active
    files = gamedata_files()
    files["pvpoke-rankings-great"] = b"[]"
    second = store.update_from_downloads(downloads(files), origin="upload")
    assert second.status == "activated" and store.active().version_id == second.version_id
    rollback = owner.post(f"/api/v1/gamedata/versions/{first.version_id}/activate")
    assert rollback.status_code == 200
    assert store.active().version_id == first.version_id
    status = owner.get("/api/v1/gamedata/status").json()
    assert status["active"]["id"] == first.version_id
    assert any(v["status"] == "failed" for v in status["versions"])


def test_network_failure_keeps_current(container: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    store = container.gamedata
    store.limits = TEST_LIMITS
    store.update_from_downloads(downloads(), origin="upload")

    def boom(_settings: Any) -> Any:
        raise OSError("offline")

    monkeypatch.setattr("app.gamedata.store.download_all", boom)
    result = store.update_from_network()
    assert result.status == "failed" and "niet bereikbaar" in result.message
    assert store.active() is not None


def test_missing_active_file_is_rebuilt_from_unchanged_sources(container: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    # Restoring only oak.db leaves an active version whose file is gone (audit A11).
    store = container.gamedata
    store.limits = TEST_LIMITS
    first = store.update_from_downloads(downloads(), origin="upload")
    with container.db.read() as session:
        record = session.get(GameDataVersion, first.version_id)
        assert record is not None
        (container.settings.gamedata_dir / record.file_name).unlink()
    assert store.load_active() is None

    monkeypatch.setattr("app.gamedata.store.remote_etags", lambda _settings: {})
    check = store.check_remote()
    assert check["available"] and check["repair_needed"]

    container.settings.gamedata_auto_update = True
    schedule_gamedata_check(container)  # the last check was just now, but nothing usable is active
    with container.db.read() as session:
        assert session.scalar(select(BackgroundJob).where(BackgroundJob.kind == "gamedata_update")) is not None

    result = store.update_from_downloads(downloads(), origin="download")
    assert result.status == "activated"
    assert store.active() is not None
    assert store.update_from_downloads(downloads(), origin="download").status == "unchanged"


def test_rederive_after_switch(owner: Any, container: Any, export: dict[str, Any]) -> None:
    account = owner.account()
    owner.upload(account, export)
    container.runner.drain()
    box = owner.get("/api/v1/pokemon", account_id=account, page_size=1).json()
    assert box["items"][0]["species_name"] is None and box["items"][0]["level"] is None  # no game data yet
    container.gamedata.limits = TEST_LIMITS
    container.gamedata.update_from_downloads(downloads(), origin="upload")
    from app.jobs.tasks import enqueue_rederive

    enqueue_rederive(container)
    container.runner.drain()
    item = owner.get("/api/v1/pokemon", account_id=account, page_size=1).json()["items"][0]
    assert item["species_name"] is not None and item["level"] is not None
    recs = owner.get("/api/v1/cleanup/recommendations", account_id=account).json()
    assert recs["analysis"]["game_data_version"] == container.gamedata.active().version_id
