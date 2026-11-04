"""Stored exports are purged only when no import that uses them still needs them (issue #35)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import select, update

from app.jobs.tasks import purge_payloads
from app.models import ImportJob
from tests.conftest import Api


def _age(container: Any, job_ids: list[int], days: int) -> None:
    with container.db.transaction() as session:
        session.execute(
            update(ImportJob)
            .where(ImportJob.id.in_(job_ids))
            .values(received_at=container.clock.now() - timedelta(days=days))
        )


def _set_status(container: Any, job_id: int, status: str) -> None:
    with container.db.transaction() as session:
        session.execute(update(ImportJob).where(ImportJob.id == job_id).values(status=status))


def _jobs(container: Any) -> list[ImportJob]:
    with container.db.read() as session:
        return list(session.scalars(select(ImportJob).order_by(ImportJob.id)).all())


def test_a_retry_keeps_the_export_it_uses(owner: Api, container: Any, gamedata: Any, export: dict[str, Any]) -> None:
    account = owner.account()
    original = owner.upload(account, export).json()["id"]
    container.runner.drain()
    _set_status(container, original, "failed")
    retry = owner.post(f"/api/v1/imports/{original}/retry")
    assert retry.status_code == 202, retry.text
    retry_id = retry.json()["id"]
    container.runner.drain()

    days = container.settings.raw_import_retention_days
    _age(container, [original], days + 1)
    purge_payloads(container)
    stored = container.settings.imports_dir / str(_jobs(container)[0].payload_file)
    assert stored.exists(), "the newer retry still counts"
    assert all(job.payload_purged_at is None for job in _jobs(container))

    # Another try from the retry works, because its export is still there.
    _set_status(container, retry_id, "partial")
    again = owner.post(f"/api/v1/imports/{retry_id}/retry")
    assert again.status_code == 202, again.text
    container.runner.drain()
    last = owner.get(f"/api/v1/imports/{again.json()['id']}").json()
    assert last["status"] != "failed" and last["error_code"] != "PAYLOAD_UNREADABLE", last


def test_an_export_goes_when_every_import_using_it_is_old(
    owner: Api, container: Any, gamedata: Any, export: dict[str, Any]
) -> None:
    account = owner.account()
    original = owner.upload(account, export).json()["id"]
    container.runner.drain()
    _set_status(container, original, "failed")
    retry_id = owner.post(f"/api/v1/imports/{original}/retry").json()["id"]
    container.runner.drain()

    _age(container, [original, retry_id], container.settings.raw_import_retention_days + 1)
    purge_payloads(container)
    jobs = _jobs(container)
    assert not (container.settings.imports_dir / str(jobs[0].payload_file)).exists()
    assert all(job.payload_purged_at is not None for job in jobs), "every import that used it says so"
    _set_status(container, retry_id, "failed")
    refused = owner.post(f"/api/v1/imports/{retry_id}/retry")
    assert refused.status_code != 202, "a retry without its export is refused with a clear message"


def test_an_export_in_use_is_never_purged(owner: Api, container: Any, gamedata: Any, export: dict[str, Any]) -> None:
    account = owner.account()
    job_id = owner.upload(account, export).json()["id"]
    _age(container, [job_id], container.settings.raw_import_retention_days + 1)
    purge_payloads(container)
    job = _jobs(container)[0]
    assert job.status == "queued" and job.payload_purged_at is None
    assert (container.settings.imports_dir / str(job.payload_file)).exists()
