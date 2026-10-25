"""Synchronisation end to end through the HTTP API and the worker (spec §24.2)."""

from __future__ import annotations

import copy
import json
import threading
from typing import Any

import pytest
from sqlalchemy import func, select, text

from app.models import BackgroundJob, ImportJob, Pokemon, PokemonChangeEvent, SyncRun
from tests.conftest import Api


def _pokemon(export: dict[str, Any]) -> list[dict[str, Any]]:
    return [p for p in export["pokemons"] if not p.get("isEgg")]


def _box(api: Api, account_id: int, **params: Any) -> dict[str, Any]:
    response = api.get("/api/v1/pokemon", account_id=account_id, page_size=500, **params)
    assert response.status_code == 200, response.text
    return response.json()


def _import(
    api: Api, container: Any, account_id: int, export: dict[str, Any], path: str | None = None
) -> dict[str, Any]:
    if path:
        response = api.client.post(path, content=json.dumps(export), headers={"content-type": "application/json"})
        assert response.status_code in (202, 400), response.text
        import_id = response.json()["import_id"]
    else:
        response = api.upload(account_id, export)
        assert response.status_code == 202, response.text
        import_id = response.json()["id"]
    container.runner.drain()
    return api.get(f"/api/v1/imports/{import_id}").json()


def test_first_import_via_webhook(owner: Api, container: Any, gamedata: Any, export: dict[str, Any]) -> None:
    account = owner.account()
    path = owner.webhook_path(account)
    result = _import(owner, container, account, export, path)
    assert result["status"] == "succeeded"
    assert result["classification"] == "full"
    assert result["sync_run"]["new_count"] == 67
    assert result["sync_run"]["eggs"] == 3
    box = _box(owner, account)
    assert box["total"] == 67
    ids = {p["source_pokemon_id"] for p in box["items"]}
    assert ids == {str(p["id"]) for p in _pokemon(export)}  # IDs exact, as strings
    assert all(isinstance(p["source_pokemon_id"], str) for p in box["items"])
    status = owner.get("/api/v1/sync/status", account_id=account).json()
    assert status["state"] == "connected"


def test_identical_second_import_is_duplicate(
    owner: Api, container: Any, gamedata: Any, export: dict[str, Any]
) -> None:
    account = owner.account()
    _import(owner, container, account, export)
    second = _import(owner, container, account, export)
    assert second["status"] == "duplicate"
    assert _box(owner, account)["total"] == 67
    with container.db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(SyncRun)) == 1


def test_changes_are_recorded_with_identity(owner: Api, container: Any, gamedata: Any, export: dict[str, Any]) -> None:
    account = owner.account()
    _import(owner, container, account, export)
    changed = copy.deepcopy(export)
    changed["time"] = "2026-10-21 09:30:00 CEST"
    records = _pokemon(changed)
    magikarp = next(p for p in records if p["pokemonId"] == 129)
    magikarp_id = str(magikarp["id"])
    magikarp["pokemonId"] = 130  # evolution keeps the ID
    magikarp["pokemonDisplay"]["formName"] = "GyaradosNormal"
    powered = records[1]
    powered["cp"] += 100
    powered["cpMultiplier"] += 0.01
    fav = records[2]
    fav["favorite"] = not fav["favorite"]
    result = _import(owner, container, account, changed)
    assert result["status"] == "succeeded"
    assert result["sync_run"]["changed_count"] == 3
    assert result["sync_run"]["new_count"] == 0
    box = _box(owner, account, q="gyarados")
    evolved = next(p for p in box["items"] if p["source_pokemon_id"] == magikarp_id)
    history = owner.get(f"/api/v1/pokemon/{evolved['id']}/history").json()
    assert history[0]["type"] == "CHANGED" and "evolved" in history[0]["labels"]
    assert history[-1]["type"] == "APPEARED"


def test_missing_pokemon_on_full_import(owner: Api, container: Any, gamedata: Any, export: dict[str, Any]) -> None:
    account = owner.account()
    _import(owner, container, account, export)
    smaller = copy.deepcopy(export)
    smaller["time"] = "2026-10-21 09:30:00 CEST"
    removed = _pokemon(smaller)[:5]
    smaller["pokemons"] = [p for p in smaller["pokemons"] if p not in removed]
    result = _import(owner, container, account, smaller)
    assert result["classification"] == "full"
    assert result["sync_run"]["missing_count"] == 5
    assert _box(owner, account)["total"] == 62
    gone = _box(owner, account, status="not_in_inventory")
    assert {p["source_pokemon_id"] for p in gone["items"]} == {str(p["id"]) for p in removed}
    assert all(p["inventory_status"] == "not_in_inventory" for p in gone["items"])
    back = copy.deepcopy(export)
    back["time"] = "2026-10-22 09:30:00 CEST"
    again = _import(owner, container, account, back)
    assert again["sync_run"]["reappeared_count"] == 5


def test_partial_import_keeps_previous_state(owner: Api, container: Any, gamedata: Any, export: dict[str, Any]) -> None:
    account = owner.account()
    _import(owner, container, account, export)
    broken = copy.deepcopy(export)
    broken["time"] = "2026-10-21 09:30:00 CEST"
    records = _pokemon(broken)
    records[0]["id"] = "kapot"
    broken["pokemons"] = [p for p in broken["pokemons"] if p is not records[1]]
    result = _import(owner, container, account, broken)
    assert result["status"] == "partial"
    assert result["sync_run"]["missing_count"] == 0
    assert result["sync_run"]["missing_unconfirmed_count"] >= 1
    assert _box(owner, account)["total"] == 67
    assert result["confirmable"] is False


def test_suspicious_drop_requires_confirmation(
    owner: Api, container: Any, gamedata: Any, export: dict[str, Any]
) -> None:
    account = owner.account()
    owner.patch(
        f"/api/v1/accounts/{account}",
        {"completeness": {"max_drop_fraction": 0.1, "max_drop_absolute": 3}},
    )
    _import(owner, container, account, export)
    smaller = copy.deepcopy(export)
    smaller["time"] = "2026-10-21 09:30:00 CEST"
    drop = _pokemon(smaller)[:20]
    smaller["pokemons"] = [p for p in smaller["pokemons"] if p not in drop]
    result = _import(owner, container, account, smaller)
    assert result["status"] == "partial" and result["confirmable"]
    assert _box(owner, account)["total"] == 67
    confirmed = owner.post(f"/api/v1/imports/{result['id']}/confirm-full")
    assert confirmed.status_code == 202, confirmed.text
    container.runner.drain()
    final = owner.get(f"/api/v1/imports/{confirmed.json()['id']}").json()
    assert final["status"] == "succeeded" and final["sync_run"]["missing_count"] == 20
    assert _box(owner, account)["total"] == 47


def test_metadata_survives_imports(owner: Api, container: Any, gamedata: Any, export: dict[str, Any]) -> None:
    account = owner.account()
    _import(owner, container, account, export)
    target = _box(owner, account)["items"][0]
    response = owner.patch(
        f"/api/v1/pokemon/{target['id']}/metadata",
        {"protected": True, "notes": "Niet weggooien", "tags": ["pvp"]},
    )
    assert response.status_code == 200
    changed = copy.deepcopy(export)
    changed["time"] = "2026-10-21 09:30:00 CEST"
    record = next(p for p in _pokemon(changed) if str(p["id"]) == target["source_pokemon_id"])
    record["cp"] += 10
    _import(owner, container, account, changed)
    after = owner.get(f"/api/v1/pokemon/{target['id']}").json()
    assert after["metadata"]["protected"] is True
    assert after["metadata"]["notes"] == "Niet weggooien"
    assert after["metadata"]["tags"] == ["pvp"]


def test_wrong_account_is_rejected(owner: Api, container: Any, gamedata: Any, export: dict[str, Any]) -> None:
    first = owner.account("Een")
    second = owner.account("Twee")
    _import(owner, container, first, export)
    response = owner.upload(second, export)
    assert response.status_code == 202  # second account is not linked yet: accepted
    other = copy.deepcopy(export)
    other["account"]["obfuscatedPlayerId"] = "a-different-player"
    rejected = owner.upload(first, other)
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "ACCOUNT_MISMATCH"
    path = owner.webhook_path(first)
    via_webhook = owner.client.post(path, content=json.dumps(other))
    container.runner.drain()
    job = owner.get(f"/api/v1/imports/{via_webhook.json()['import_id']}").json()
    assert job["status"] == "rejected" and job["error_code"] == "ACCOUNT_MISMATCH"
    assert _box(owner, first)["total"] == 67


@pytest.mark.parametrize("change", ["empty_account", "no_time"])
def test_unverifiable_export_never_marks_pokemon_as_gone(
    owner: Api, container: Any, gamedata: Any, export: dict[str, Any], change: str
) -> None:
    account = owner.account()
    _import(owner, container, account, export)
    smaller = copy.deepcopy(export)
    removed = _pokemon(smaller)[0]["id"]
    smaller["pokemons"] = [p for p in smaller["pokemons"] if p["id"] != removed]
    smaller["time"] = "2026-10-23 12:00:00 CEST"
    if change == "empty_account":
        smaller["account"] = {}
    else:
        del smaller["time"]
    result = _import(owner, container, account, smaller)
    assert result["status"] == "partial" and result["classification"] == "partial"
    assert _box(owner, account)["total"] == 67
    assert _box(owner, account, status="not_in_inventory")["total"] == 0

    confirmed = owner.post(f"/api/v1/imports/{result['id']}/confirm-full")
    assert confirmed.status_code == 202, confirmed.text
    container.runner.drain()
    assert _box(owner, account)["total"] == 66
    assert _box(owner, account, status="not_in_inventory")["total"] == 1


def test_stale_export_is_not_applied(owner: Api, container: Any, gamedata: Any, export: dict[str, Any]) -> None:
    account = owner.account()
    _import(owner, container, account, export)
    old = copy.deepcopy(export)
    old["time"] = "2025-01-01 10:00:00 CET"
    old["pokemons"] = old["pokemons"][:10]
    result = _import(owner, container, account, old)
    assert result["status"] == "rejected" and result["error_code"] == "EXPORT_OLDER_THAN_CURRENT"
    assert _box(owner, account)["total"] == 67


def test_invalid_json_and_bad_tokens(owner: Api, container: Any, export: dict[str, Any]) -> None:
    account = owner.account()
    path = owner.webhook_path(account)
    bad = owner.client.post(path, content=b"{niet json")
    assert bad.status_code == 400 and bad.json()["error"] == "INVALID_JSON"
    assert owner.client.post("/api/v1/ingest/pgsharp/oakwh_AAAAAAAAAA_verkeerd", content=b"{}").status_code == 404
    assert owner.client.post("/api/v1/ingest/pgsharp/zomaar", content=b"{}").status_code == 404


@pytest.mark.parametrize(
    ("body", "headers"),
    [
        (b"", {}),
        (b"test", {"content-type": "text/plain"}),
        (b"test=1", {"content-type": "application/x-www-form-urlencoded"}),
        (
            b'--x\r\nContent-Disposition: form-data; name="test"\r\n\r\n1\r\n--x--\r\n',
            {"content-type": "multipart/form-data; boundary=x"},
        ),
        (b'{"test": true}', {"content-type": "application/json"}),
    ],
)
def test_connection_test_is_answered_without_import(owner: Api, body: bytes, headers: dict[str, str]) -> None:
    account = owner.account()
    path = owner.webhook_path(account)
    response = owner.client.post(path, content=body, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "connection_test"
    assert owner.get("/api/v1/imports", account_id=account).json()["total"] == 0
    assert owner.get(f"/api/v1/accounts/{account}").json()["webhook"]["last_used_at"] is not None


def test_large_non_export_is_not_a_connection_test(owner: Api) -> None:
    account = owner.account()
    path = owner.webhook_path(account)
    response = owner.client.post(path, content=b"x" * 5000)
    assert response.status_code == 400 and response.json()["error"] == "INVALID_JSON"
    assert owner.get("/api/v1/imports", account_id=account).json()["total"] == 1


def test_token_rotation_and_revocation(owner: Api, container: Any, gamedata: Any, export: dict[str, Any]) -> None:
    account = owner.account()
    old_path = owner.webhook_path(account)
    new_path = owner.webhook_path(account)
    assert old_path != new_path
    assert owner.client.post(old_path, content=json.dumps(export)).status_code == 404
    assert owner.client.post(new_path, content=json.dumps(export)).status_code == 202
    assert owner.delete(f"/api/v1/accounts/{account}/webhook").status_code == 204
    assert owner.client.post(new_path, content=json.dumps(export)).status_code == 404


def test_gzip_payload(owner: Api, container: Any, gamedata: Any, export: dict[str, Any]) -> None:
    import gzip

    account = owner.account()
    path = owner.webhook_path(account)
    body = gzip.compress(json.dumps(export).encode())
    response = owner.client.post(path, content=body, headers={"content-encoding": "gzip"})
    assert response.status_code == 202
    container.runner.drain()
    assert _box(owner, account)["total"] == 67


def test_impossible_export_date_never_leaves_an_import_processing(
    owner: Api, container: Any, gamedata: Any, export: dict[str, Any]
) -> None:
    account = owner.account()
    first = copy.deepcopy(export)
    first["time"] = "2026-99-23 12:00:00 UTC"
    result = _import(owner, container, account, first)
    # Nothing to replace yet, so the first import may be full, with a warning about the date.
    assert result["status"] == "succeeded"
    issues = owner.get(f"/api/v1/imports/{result['id']}/errors").json()
    assert "EXPORT_TIME_INVALID" in {i["code"] for i in issues}
    again = copy.deepcopy(export)
    again["time"] = "2026-10-32 12:00:00 +25:00"
    second = _import(owner, container, account, again)
    assert second["status"] == "partial"


def test_unexpected_normalizer_error_fails_the_import(
    owner: Api, container: Any, export: dict[str, Any], monkeypatch: Any
) -> None:
    def broken(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr("app.ingestion.processor.normalize_export", broken)
    result = _import(owner, container, owner.account(), export)
    assert result["status"] == "failed" and result["error_code"] == "NORMALIZATION_FAILED"


def test_truncated_gzip_is_refused(owner: Api, container: Any, export: dict[str, Any]) -> None:
    import gzip

    path = owner.webhook_path(owner.account())
    body = gzip.compress(json.dumps(export).encode())
    for broken in (body[:-8], body[:-4], body + b"trailing"):
        response = owner.client.post(path, content=broken, headers={"content-encoding": "gzip"})
        assert response.status_code == 415, response.text


def test_payload_size_limit(owner: Api, container: Any, settings: Any) -> None:
    account = owner.account()
    path = owner.webhook_path(account)
    container.settings.max_import_mb = 1
    response = owner.client.post(path, content=b"x" * (1024 * 1024 + 10))
    assert response.status_code == 413


def test_concurrent_imports_do_not_corrupt(owner: Api, container: Any, gamedata: Any, export: dict[str, Any]) -> None:
    account = owner.account()
    path = owner.webhook_path(account)
    bodies = []
    for i in range(4):
        variant = copy.deepcopy(export)
        variant["time"] = f"2026-10-2{i} 09:30:00 CEST"
        bodies.append(json.dumps(variant))
    statuses: list[int] = []

    def send(body: str) -> None:
        statuses.append(owner.client.post(path, content=body).status_code)

    threads = [threading.Thread(target=send, args=(b,)) for b in bodies]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert statuses == [202] * 4
    container.runner.drain()
    assert _box(owner, account)["total"] == 67
    with container.db.transaction() as session:
        rows = session.scalar(select(func.count()).select_from(Pokemon))
        assert rows == 67


def test_restart_during_processing_is_recovered(
    owner: Api, container: Any, gamedata: Any, export: dict[str, Any]
) -> None:
    account = owner.account()
    response = owner.upload(account, export)
    import_id = response.json()["id"]
    with container.db.transaction() as session:
        session.get(ImportJob, import_id).status = "processing"
        for job in session.scalars(select(BackgroundJob)):
            job.status = "running"
    assert container.runner.recover() == 1
    container.runner.drain()
    assert owner.get(f"/api/v1/imports/{import_id}").json()["status"] == "succeeded"


def test_retry_failed_import(owner: Api, container: Any, gamedata: Any, export: dict[str, Any]) -> None:
    account = owner.account()
    response = owner.upload(account, export)
    import_id = response.json()["id"]
    original = container.processor.process
    container.processor.process = lambda _id: (_ for _ in ()).throw(RuntimeError("boom"))  # type: ignore[method-assign]
    container.runner.drain()
    container.processor.process = original  # type: ignore[method-assign]
    with container.db.transaction() as session:
        job = session.get(ImportJob, import_id)
        job.status = "failed"
    retried = owner.post(f"/api/v1/imports/{import_id}/retry")
    assert retried.status_code == 202
    container.runner.drain()
    assert owner.get(f"/api/v1/imports/{retried.json()['id']}").json()["status"] == "succeeded"


def test_change_history_is_immutable(owner: Api, container: Any, gamedata: Any, export: dict[str, Any]) -> None:
    import pytest
    from sqlalchemy.exc import IntegrityError, OperationalError

    account = owner.account()
    _import(owner, container, account, export)
    with pytest.raises((IntegrityError, OperationalError)), container.db.transaction() as session:
        session.execute(text("UPDATE pokemon_change_events SET event_type = 'X'"))
    with container.db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(PokemonChangeEvent)) == 67


def test_stored_payload_is_sanitized(owner: Api, container: Any, gamedata: Any, export: dict[str, Any]) -> None:
    import gzip

    account = owner.account()
    response = owner.upload(account, export)
    with container.db.transaction() as session:
        job = session.get(ImportJob, response.json()["id"])
        stored = gzip.decompress((container.settings.imports_dir / job.payload_file).read_bytes()).decode()
    for secret in ("capturedS2CellId", "obfuscatedPlayerId", "Ruilvriend", "synthetic-poi-id"):
        assert secret not in stored
