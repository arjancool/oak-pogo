"""A limit on manual imports per user, and at most one waiting import per account (issue #45)."""

from __future__ import annotations

from typing import Any

from tests.conftest import Api


def test_one_waiting_import_per_account(owner: Api, container: Any, export: dict[str, Any]) -> None:
    account = owner.account()
    assert owner.upload(account, export).json()["status"] == "queued"
    second = owner.upload(account, dict(export, time="2026-11-04 10:00:00 UTC"))
    assert second.status_code == 409 and second.json()["error"]["code"] == "IMPORT_QUEUED"
    assert len(list(container.settings.imports_dir.iterdir())) == 1, "the refused copy is not kept"
    other = owner.account("Ander account")
    assert owner.upload(other, export).status_code == 202, "another account has its own place"
    container.runner.drain()
    assert owner.upload(account, dict(export, time="2026-11-04 10:00:00 UTC")).status_code == 202


def test_manual_imports_per_user_are_limited(owner: Api, container: Any) -> None:
    for _ in range(container.imports_by_user.limit):
        container.imports_by_user.hit("user:1")
    response = owner.upload(owner.account(), {"pokemons": []})
    assert response.status_code == 429 and "Retry-After" in response.headers
    assert response.json()["error"]["data"]["context"] == "imports"
    assert list(container.settings.imports_dir.iterdir()) == [], "the body is not even read"


def test_a_retry_waits_for_the_queue(owner: Api, container: Any, export: dict[str, Any]) -> None:
    from sqlalchemy import update

    from app.models import ImportJob

    account = owner.account()
    job_id = owner.upload(account, export).json()["id"]
    container.runner.drain()
    with container.db.transaction() as session:
        session.execute(update(ImportJob).where(ImportJob.id == job_id).values(status="failed"))
    assert owner.post(f"/api/v1/imports/{job_id}/retry").status_code == 202
    again = owner.post(f"/api/v1/imports/{job_id}/retry")
    assert again.status_code == 409 and again.json()["error"]["code"] == "IMPORT_QUEUED"
